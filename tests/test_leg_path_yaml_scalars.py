# SPDX-License-Identifier: Apache-2.0
"""A leg path the project would read back as another type is refused (#225).

The templates write a leg path BARE: `path: {{SPEC_PATH}}` in `project.yaml`
and `submodule_path: {{SPEC_PATH}}` in `contracts/spec-pin.yaml`, the same for
the code leg. The project reads them with its own copy of `repo_shape`'s YAML
reader, which takes `null`, `~`, `true`, `False`, `2026` and `1.5` as no value,
a boolean or a number. The leg-path rule from #179 (`leg_path_problem`)
passed every one of them, so `scaffold-project.py --spec-path 2026` exited 0
and created three repositories whose own `validate-manifest.py` then failed
`manifest-leg-path: leg 'spec': path is 2026`, and `adopt-project.py execute
--spec-path 2026` said `adoption verified` before `bootstrap FAILED`.

The one rule both tools ask now refuses such a value, before anything exists:
the scaffold under `--dry-run` alike, adopt's `plan`, `check` and `execute`.
WHAT IS REFUSED IS THE READER'S ANSWER, NOT A LIST. The tables below are what
today's reader says, `yes`, `0x1F`, `1e3` and `.inf` among the values it reads
as text (YAML 1.1 or 1.2 would read some of them otherwise), and one test
teaches the reader a new word to show the rule follows it with no edit.

THE RULE ASKS ITS OWN COPY OF THE TEMPLATE LINE (`LEG_PATH_LINE`), so one
test reads the templates themselves: it finds every YAML template line that
holds a leg path, renders each value into it, and holds the rule's verdict to
what the reader gives back. Quote those lines (#259 proposes it) and leave the
rule alone, and that test fails rather than the rule refusing `2026` in
silence over a line that reads it back.

Every scaffold here runs with `--local-remote-dir` (no network, no `gh`).
Only the `execute` test needs `git filter-repo`.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, FILE_PROTOCOL, ORG, REPO, SCAFFOLD, git,
                      make_source_repo, resolve, run_script, write_plan)

sys.path.insert(0, str(REPO / "scripts"))
import repo_shape  # noqa: E402
import shape_materialize  # noqa: E402
from repo_shape import double_quoted, load_yaml  # noqa: E402

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

SPEC, CODE = "--spec-path", "--code-path"
PLAN_SPEC = "legs.spec_path"
SCAFFOLD_REFUSAL = "REFUSED scaffold-bad-leg-path: "
PLAN_REFUSAL = "REFUSED adopt-bad-leg-path: "
CHECK_FINDING = "FINDING plan-bad-leg-path: "
EXECUTE_REFUSAL = "REFUSED plan-bad-leg-path: "
#: How the sentence begins after the value, and what it must never offer:
#: there is no other spelling of `2026` that names the same directory.
NOT_READ_BACK = "which the project would not read back as text: "
OFFER = "Write '"

NO_VALUE = "no value at all"
TRUE_READ, FALSE_READ = "the boolean true", "the boolean false"

#: `(value, what the project's reader makes of it)`, today. Each is a
#: canonical path in `checked_value`'s alphabet, so #179's rule passed it.
#: `007` and `1.50` are named by what was READ: the reader keeps no text.
REFUSED = [
    pytest.param("null", NO_VALUE, id="null"),
    pytest.param("Null", NO_VALUE, id="Null"),
    pytest.param("NULL", NO_VALUE, id="NULL"),
    pytest.param("~", NO_VALUE, id="tilde"),
    pytest.param("true", TRUE_READ, id="true"),
    pytest.param("True", TRUE_READ, id="True"),
    pytest.param("TRUE", TRUE_READ, id="TRUE"),
    pytest.param("false", FALSE_READ, id="false"),
    pytest.param("False", FALSE_READ, id="False"),
    pytest.param("FALSE", FALSE_READ, id="FALSE"),
    pytest.param("2026", "the number 2026", id="2026"),
    pytest.param("007", "the number 7", id="007"),
    pytest.param("0", "the number 0", id="0"),
    pytest.param("1.5", "the number 1.5", id="1.5"),
    pytest.param("1.50", "the number 1.5", id="1.50"),
]

#: One of each kind, for the places that start a process per value twice.
REFUSED_AT_THE_SITES = [
    pytest.param("null", NO_VALUE, id="null"),
    pytest.param("~", NO_VALUE, id="tilde"),
    pytest.param("true", TRUE_READ, id="true"),
    pytest.param("False", FALSE_READ, id="False"),
    pytest.param("2026", "the number 2026", id="2026"),
    pytest.param("1.5", "the number 1.5", id="1.5"),
]

#: Paths that LOOK like those and are text to the reader: the controls the
#: issue names, a keyword as one segment of a longer path, and a keyword
#: spelled in a case the reader does not take as one.
LOOKALIKES = ["spec", "legs/spec", "a..b", "v1.5", "1.5.2", "null-spec",
              "2026-docs", "legs/null", "legs/2026", "2026/spec", "nUll",
              "tRue"]

#: What YAML 1.1 or 1.2 would read as a boolean, a number or an infinity, and
#: `repo_shape`'s reader reads as text: the rule asks THAT reader, the one
#: the project ships, so these are paths.
TEXT_TO_THIS_READER = ["yes", "no", "on", "off", "0x1F", "0o17", "1e3",
                       ".inf", ".nan", "+1", ".5", "1_000"]

KEPT = LOOKALIKES + TEXT_TO_THIS_READER

#: Where the templates are, and the placeholders a leg path is rendered into.
TEMPLATES = REPO / "templates"
LEG_PATH_PLACEHOLDERS = ("SPEC_PATH", "CODE_PATH")


def template_lines_holding_a_leg_path() -> list[tuple[str, str]]:
    """Every line of every YAML template that holds a leg path, FOUND by
    reading `templates/` and not listed here: `(where, line)`, `where` being
    `<template>:<line number>`. A Markdown template's `{{SPEC_PATH}}/` is
    prose no YAML reader reads, so only `.yaml` and `.yml` files are asked."""
    found = []
    for path in sorted(TEMPLATES.rglob("*")):
        if path.suffix not in (".yaml", ".yml") or not path.is_file():
            continue
        where = path.relative_to(TEMPLATES).as_posix()
        lines = path.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, 1):
            if any("{{" + key + "}}" in line for key in LEG_PATH_PLACEHOLDERS):
                found.append((f"{where}:{number}", line))
    return found


TEMPLATE_LEG_PATH_LINES = template_lines_holding_a_leg_path()


def read_back(line: str, value: str):
    """What the project's reader makes of a template `line` once `value` is
    rendered into it, by the `render` the scaffold and `execute` use. The
    line is read on its own, dedented: a `key: value` line's scalar is read
    the same there as inside its block."""
    rendered = shape_materialize.render(
        line, {key: value for key in LEG_PATH_PLACEHOLDERS}, "test")
    read = repo_shape.parse_yaml(rendered.strip() + "\n")
    assert isinstance(read, dict) and len(read) == 1, (
        f"{line!r} is not one `key: value` line: teach read_back its form")
    return next(iter(read.values()))

#: Where a scaffold writes, under `tmp_path`, and the temporary directory the
#: tool would otherwise make its work directory in.
REMOTES, WORK, SCRATCH = "remotes", "work", "tmp"
IDENTITY = ["--org", ORG, "--project", "Northwind", "--elected-by",
            "Test Human", "--elected-on", "2026-09-02"]

#: Answered the way `test_adopt_leg_paths.py` answers them, so `check` passes.
ANSWERS = (("examples/", "spec"), (".claude/", "root"),
           ("release.yaml", "root"))


def sentence(what: str, value: str, reading: str) -> str:
    """The whole sentence the rule says, written out here as its oracle."""
    return (f"{what} is {value!r}, {NOT_READ_BACK}the assembly root's "
            "`project.yaml` and `contracts/<role>-pin.yaml` hold a leg path "
            f"unquoted (`path: {value}`), and the project's own YAML reader "
            f"reads that as {reading}, so its first bootstrap would fail.")


def scaffold(tmp_path: Path, *args: str):
    """One scaffold of `Northwind` into local bare remotes under `tmp_path`,
    with `TMPDIR` (and Windows' `TEMP` and `TMP`) at an empty directory of
    the test's, so a test sees whether the tool made a work directory."""
    scratch = tmp_path / SCRATCH
    scratch.mkdir(exist_ok=True)
    return run_script(
        SCAFFOLD, *IDENTITY, "--local-remote-dir", str(tmp_path / REMOTES),
        *args, env={"TMPDIR": str(scratch), "TMP": str(scratch),
                    "TEMP": str(scratch)})


def assert_nothing_was_created(tmp_path: Path) -> None:
    found = sorted(p.name for p in tmp_path.iterdir())
    assert found == [SCRATCH], f"a refused scaffold created something: {found}"
    assert list((tmp_path / SCRATCH).iterdir()) == [], (
        "a refused scaffold made a temporary work directory")


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    """One source repository and one ANSWERED plan against it, which `check`
    passes. `plan` and `check` only read the source, so the tests share it;
    a test that edits the plan edits a copy."""
    root = tmp_path_factory.mktemp("yaml-scalar-legs")
    source = make_source_repo(root / "Thing")
    plan = root / "adoption-plan.yaml"
    written = write_plan(source, plan)
    assert written.returncode == 0, written.stderr + written.stdout
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    return {"source": source, "plan": plan}


def carrying(plan: Path, out: Path, value: str) -> Path:
    """A copy of `plan` whose `legs.spec_path` is `value` AS TEXT: written
    double-quoted, so the plan's own reader gives back the string -- a plan
    edited by hand, or one a writer that quotes such values wrote. LF, as
    `plan` writes it."""
    text = plan.read_text(encoding="utf-8")
    line = "\n  spec_path: spec\n"
    assert line in text, "no default `spec_path:` line in the plan"
    with out.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.replace(
            line, f"\n  spec_path: {double_quoted(value)}\n", 1))
    return out


# --- the one rule ------------------------------------------------------------

@pytest.mark.parametrize("what", [SPEC, PLAN_SPEC, "legs.code_path"])
@pytest.mark.parametrize("value, reading", REFUSED)
def test_a_value_the_reader_reads_as_another_type_is_a_problem(
        what, value, reading):
    assert shape_materialize.leg_path_problem(what, value) == sentence(
        what, value, reading)


@pytest.mark.parametrize("value", KEPT)
def test_a_value_the_reader_reads_as_text_is_still_a_path(value):
    assert repo_shape.parse_yaml(f"path: {value}\n") == {"path": value}, (
        "this table is about today's reader, and it no longer agrees")
    assert shape_materialize.leg_path_problem(SPEC, value) is None


def test_the_template_lines_found_are_the_ones_the_sentence_names():
    """The search is not vacuous: it finds the leg-path lines of the files
    the rule's sentence names, `project.yaml` and both legs' pins."""
    found = {where.rsplit(":", 1)[0] for where, _ in TEMPLATE_LEG_PATH_LINES}
    assert {"assembly-root/project.yaml",
            "assembly-root/contracts/spec-pin.yaml",
            "assembly-root/contracts/code-pin.yaml"} <= found, (
        TEMPLATE_LEG_PATH_LINES)


@pytest.mark.parametrize("value", [*(p.values[0] for p in REFUSED), *KEPT])
def test_the_rule_agrees_with_every_template_line_that_holds_a_leg_path(
        value):
    """THE TEMPLATES ARE READ, NOT THE RULE'S COPY OF THEIR LINE: `value` is
    rendered into every template line that holds a leg path, each is read
    back with the project's reader, and the rule must refuse `value` exactly
    when one of them does not give it back. Quote those lines, as #259
    proposes, and leave the rule alone, and this fails: the rule would go on
    refusing `2026`, which `path: "2026"` reads back, with a sentence saying
    the line is unquoted."""
    read = {where: read_back(line, value)
            for where, line in TEMPLATE_LEG_PATH_LINES}
    misread = {where: got for where, got in read.items() if got != value}
    problem = shape_materialize.leg_path_problem(SPEC, value)
    assert (problem is None) == (not misread), (
        f"the rule says {problem!r}, and the templates read {value!r} back "
        f"as {read!r}")


def test_the_rule_follows_the_reader_when_it_learns_a_word(monkeypatch):
    """No list of words: teach the reader the project ships that `yes` is a
    boolean, and the rule refuses `yes` with no edit of its own."""
    reads = repo_shape._scalar
    assert shape_materialize.leg_path_problem(SPEC, "yes") is None
    monkeypatch.setattr(repo_shape, "_scalar", lambda raw: True if (
        raw.strip() == "yes") else reads(raw))
    assert shape_materialize.leg_path_problem(SPEC, "yes") == sentence(
        SPEC, "yes", TRUE_READ)


@pytest.mark.parametrize("value", ["2026/", "./null", "~/", "legs/../True",
                                   "True\\"])
def test_a_spelling_the_project_would_misread_is_not_offered(value):
    """Asked LAST, so a value another rule refuses keeps that rule's sentence,
    and the spelling it offers is one no rule refuses: `2026/` is not
    answered `Write '2026'.`, which would be refused in turn."""
    problem = shape_materialize.leg_path_problem(SPEC, value)
    assert problem.startswith(f"--spec-path is {value!r}, which is not a "
                              "canonical leg path")
    assert OFFER not in problem
    assert NOT_READ_BACK not in problem


def test_a_spelling_with_a_number_as_one_segment_is_still_offered():
    assert shape_materialize.leg_path_problem(SPEC, "legs\\2026").endswith(
        "Write 'legs/2026'.")


def test_the_remediation_says_what_the_reader_does_not_read_back():
    """A person refused for `2026` reads a remediation that names the rule
    they tripped, as it names every other one."""
    remediation = shape_materialize.LEG_PATH_REMEDIATION
    assert "reads it back as text where the project writes it" in remediation
    for word in ("`null`", "`~`", "`true`", "`False`", "`2026`", "`1.5`"):
        assert word in remediation, word


# --- scaffold-project.py -----------------------------------------------------

@pytest.mark.parametrize("value, reading", REFUSED)
def test_a_dry_run_refuses_the_spec_path_and_creates_nothing(
        tmp_path, value, reading):
    result = scaffold(tmp_path, "--dry-run", SPEC, value)
    assert result.returncode == 2, result.stderr + result.stdout
    assert result.stderr.startswith(SCAFFOLD_REFUSAL), result.stderr
    assert sentence(SPEC, value, reading) in result.stderr
    assert shape_materialize.LEG_PATH_REMEDIATION in result.stderr
    assert OFFER not in result.stderr
    assert result.stdout == "", "a dry run printed a plan it then refused"
    assert_nothing_was_created(tmp_path)


@pytest.mark.parametrize("value, reading", REFUSED_AT_THE_SITES)
def test_a_dry_run_refuses_the_code_path_and_creates_nothing(
        tmp_path, value, reading):
    result = scaffold(tmp_path, "--dry-run", CODE, value)
    assert result.returncode == 2, result.stderr + result.stdout
    assert sentence(CODE, value, reading) in result.stderr
    assert_nothing_was_created(tmp_path)


def test_both_legs_are_named_in_one_refusal(tmp_path):
    result = scaffold(tmp_path, "--dry-run", SPEC, "~", CODE, "2026")
    assert result.returncode == 2, result.stderr + result.stdout
    assert sentence(SPEC, "~", NO_VALUE) in result.stderr
    assert sentence(CODE, "2026", "the number 2026") in result.stderr
    assert_nothing_was_created(tmp_path)


@pytest.mark.parametrize("value", KEPT)
def test_a_dry_run_still_accepts_a_path_the_reader_reads_as_text(
        tmp_path, value):
    result = scaffold(tmp_path, "--dry-run", SPEC, value)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "REFUSED" not in result.stderr


def test_the_issues_scaffold_is_refused_and_nothing_exists(tmp_path):
    """The command from #225, unchanged and for real. On `main` it exited 0,
    pushed three remotes, and the new project's first bootstrap failed
    `manifest-leg-path`. Now no remote and no work directory exist."""
    result = run_script(SCAFFOLD, *IDENTITY, SPEC, "2026",
                        "--local-remote-dir", str(tmp_path / REMOTES),
                        "--work-dir", str(tmp_path / WORK))
    assert result.returncode == 2, result.stderr + result.stdout
    assert result.stderr.startswith(SCAFFOLD_REFUSAL), result.stderr
    assert not (tmp_path / REMOTES).exists()
    assert not (tmp_path / WORK).exists()


def test_a_lookalike_scaffolds_clones_and_bootstraps(tmp_path):
    """The accepted half, to the step the refused half failed at: two leg
    paths spelled like a number are mounted, written into the manifest and
    the pins as the text they are, and the project's first bootstrap is
    green."""
    spec_path, code_path = "2026-docs", "v1.5"
    result = run_script(SCAFFOLD, *IDENTITY, SPEC, spec_path, CODE, code_path,
                        "--local-remote-dir", str(tmp_path / REMOTES),
                        "--work-dir", str(tmp_path / WORK))
    assert result.returncode == 0, result.stderr + result.stdout
    clone = tmp_path / "clone"
    cloned = git(*FILE_PROTOCOL, "clone", "-q", "--recurse-submodules",
                 str(tmp_path / REMOTES / "Northwind.git"), str(clone),
                 cwd=tmp_path, check=False)
    assert cloned.returncode == 0, cloned.stderr
    manifest = load_yaml(clone / "project.yaml")
    assert [leg["path"] for leg in manifest["legs"]] == [".", spec_path,
                                                         code_path]
    for role, path in (("spec", spec_path), ("code", code_path)):
        pin = load_yaml(clone / "contracts" / f"{role}-pin.yaml")
        assert pin["submodule_path"] == path
    bootstrapped = run_script(clone / "scripts" / "bootstrap.py", cwd=clone)
    assert bootstrapped.returncode == 0, (bootstrapped.stderr
                                          + bootstrapped.stdout)
    assert "bootstrap ok" in bootstrapped.stdout


# --- adopt-project.py --------------------------------------------------------

@pytest.mark.parametrize("value, reading", REFUSED)
def test_plan_refuses_the_value_and_writes_nothing(world, tmp_path, value,
                                                   reading):
    out = tmp_path / "plan.yaml"
    result = write_plan(world["source"], out, extra=(SPEC, value))
    assert result.returncode == 2, result.stderr + result.stdout
    assert result.stderr.startswith(PLAN_REFUSAL), result.stderr
    assert sentence(SPEC, value, reading) in result.stderr
    assert not out.exists(), "a refused plan must leave no file behind"


@pytest.mark.parametrize("value, reading", REFUSED_AT_THE_SITES)
def test_plan_refuses_the_code_path_too(world, tmp_path, value, reading):
    out = tmp_path / "plan.yaml"
    result = write_plan(world["source"], out, extra=(CODE, value))
    assert result.returncode == 2, result.stderr + result.stdout
    assert sentence(CODE, value, reading) in result.stderr
    assert not out.exists()


@pytest.mark.parametrize("value, reading", REFUSED)
def test_check_reports_a_plan_carrying_the_value_as_text(world, tmp_path,
                                                         value, reading):
    """The plan's own reader gives the text back (it is quoted there), so
    `check` passed it on `main`; `execute` then writes it bare."""
    plan = carrying(world["plan"], tmp_path / "plan.yaml", value)
    result = run_script(ADOPT, "check", "--plan", str(plan))
    assert result.returncode == 1, result.stdout + result.stderr
    assert (f"{CHECK_FINDING}{sentence(PLAN_SPEC, value, reading)}"
            in result.stderr)
    assert "plan ok" not in result.stdout


@pytest.mark.parametrize("value", ["v1.5", "1.5.2", "null-spec", "2026-docs",
                                   "legs/null", "yes", "0x1F"])
def test_check_still_passes_a_lookalike(world, tmp_path, value):
    plan = carrying(world["plan"], tmp_path / "plan.yaml", value)
    result = run_script(ADOPT, "check", "--plan", str(plan))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "plan ok" in result.stdout


@needs_filter_repo
def test_execute_refuses_the_issues_plan_before_any_leg_exists(tmp_path):
    """The adopt half of #225: `execute --spec-path 2026` said `adoption
    verified` on `main`, and the clone's bootstrap failed. It is refused now
    before a leg repository or the split branch exists."""
    source = make_source_repo(tmp_path / "Thing")
    planned = tmp_path / "answered.yaml"
    assert write_plan(source, planned).returncode == 0
    for path, leg in ANSWERS:
        resolve(planned, path, leg)
    plan = carrying(planned, tmp_path / "plan.yaml", "2026")
    remotes = tmp_path / REMOTES
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / WORK))
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(EXECUTE_REFUSAL), result.stderr
    assert sentence(PLAN_SPEC, "2026", "the number 2026") in result.stderr
    assert "adoption verified" not in result.stdout
    assert not remotes.exists(), "no leg repository may exist after a refusal"
    assert git("branch", "--list", "adopt/three-repo-shape",
               cwd=source).stdout == "", "the source got no split branch"
