# SPDX-License-Identifier: Apache-2.0
"""Three refusals name what a person changes again (#708).

Each named the value to change on main or in v1.0.1, and a v1.1.0 change
took that away:

- L4-151, from #635 (#392, #393). The YAML reader now refuses a plain value
  that opens with an indicator, so an adoption plan whose hand-written
  `resolution:` opens with a backtick (AGENTS.md asks for the reason in
  words) ended `adopt-project.py check` in `REFUSED yaml-unparsable:
  <plan>: <words>`, exit 2: no line among the hundreds a plan holds, and no
  remedy. The refusal now names the line, which the block reader records
  (`repo_shape._block_value`), and says to double-quote the value or reword
  it; the double-quoted twin checks clean. Every refusal with that remedy
  (`_indicator_refusal`'s) names its line; the others keep the words they
  had, and the words of `parse_yaml` are unchanged.
- L4-152, from #635. The reader refuses `repository: @x/Northwind`, so
  `plan --org @x` (a typo of `@opensoft`) no longer reached the validator,
  whose finding named `--org`, and the remedy said the words were the
  validator's. The value on the line the reader refuses is named again
  (`shape_materialize._unread_sentences`), in the sentence main had with the
  reader in the validator's place, under the reader's own remedy.
  `family.py init --org @x` stays refused.
- L4-127, from #644 (#455). `check` named one bad `tracking_branch` twice:
  `unsafe-value`, then the validator's `manifest-tracking-branch` with no
  plan key. The validator's sentence is left out where `unsafe-value` names
  the branch (`adopt-project.py`'s `_validator_ignores`).

NO NETWORK AND NO GITHUB: local sources, `--local-remote-dir`, `--dry-run`,
strings and temporary files, and the suite's `gh` guard.
"""

from __future__ import annotations

import functools
import re
import sys
from pathlib import Path

import pytest

from conftest import ADOPT, REPO, run_script, write_plan
from test_adopt_manifest_values import (  # noqa: F401 - fixtures
    INVALID, PROJECT, adopter, edited, execute, needs_filter_repo,
    no_leg_was_created, world)
from test_family_init_values import init, nothing_was_created
from test_scaffold_manifest_values import (
    INVALID as SCAFFOLD_INVALID, assert_nothing_was_created, assert_refused,
    scaffold)

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402
from repo_shape import (  # noqa: E402
    REMEDIATION, Refusal, YamlError, double_quoted, load_yaml, parse_yaml)

UTF8 = "utf-8"
OPENS = "a plain scalar cannot open with"
#: The reason a person wrote, which read as text before #392 and #393.
BACKTICKED = "`adopt-project.py` reads it"
#: How `conftest.resolve` writes an answer's reason.
ANSWERED = 'resolution: "answered by the test"'
READER_REFUSES = "which the project's own YAML reader refuses: "
NOT_THE_VALIDATORS = "the words after each value are the validator's own"


def remedy_for(text: str) -> str:
    """The remedy a plain value that opens with an indicator is given, in
    full: the value double-quoted as the reader takes it back."""
    return ("Remediation: unquoted, YAML does not read this value as text, "
            "so this reader refuses it rather than guess. Write it in double "
            f"quotes, as {double_quoted(text)}, or reword it so that it opens "
            "with another character, and run the command again.")


def line_of(path: Path, text: str) -> int:
    """The number of the one line of `path` that is `text`, from 1."""
    lines = path.read_bytes().decode(UTF8).splitlines()
    assert lines.count(text) == 1, f"{text!r} is not one line of {path}"
    return lines.index(text) + 1


def check(plan: Path):
    return run_script(ADOPT, "check", "--plan", str(plan))


# --- L4-151: the line, and what to do --------------------------------------

def test_a_resolution_opening_with_a_backtick_names_its_line_and_a_remedy(
        world):
    """The issue's case through `check`: exit 2, the plan's line, the
    reader's words as they were, and the remedy, and nothing else."""
    plan = edited(world, ANSWERED, f"resolution: {BACKTICKED}")
    line = line_of(plan, f"    resolution: {BACKTICKED}")
    result = check(plan)
    assert result.returncode == 2, result.stderr + result.stdout
    assert result.stderr == (
        f"REFUSED yaml-unparsable: {plan}: line {line}: {OPENS} a backtick, "
        f"which is reserved in YAML: {BACKTICKED!r}\n"
        f"{remedy_for(BACKTICKED)}\n")


def test_the_remedys_own_spelling_checks_clean(world):
    """Following the remedy is the fix: the line it spells, put in the
    plan's place, is the double-quoted twin, and `check` passes it."""
    spelled = re.search(r"as (\".*\"), or reword",
                        remedy_for(BACKTICKED)).group(1)
    assert spelled == f'"{BACKTICKED}"'
    result = check(edited(world, ANSWERED, f"resolution: {spelled}"))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "REFUSED" not in result.stderr
    assert "FINDING" not in result.stderr


@pytest.mark.parametrize("body", [
    "k: {@a: b}\n", "k: {`a`: b}\n", "k: {: a}\n", "k: {? a: b}\n",
    "k: [x, {%a: 1}]\n", "k: {#a: 1}\n"])
def test_a_flow_mapping_key_is_not_told_to_quote_the_whole_entry(body):
    """Lane 1's review of #817: an entry of a flow mapping opens its KEY, and
    the whole entry double-quoted (`{"@a: b"}`) reads as an entry without a
    key, refused again. So such a refusal carries no remedy, and no line."""
    with pytest.raises(YamlError) as caught:
        parse_yaml(body)
    assert caught.value.remediation == ""


#: `(file, the line the refusal names, the value its remedy is spelled for)`:
#: the opener in a block value, a sequence item, a nested value, a flow
#: entry and a lone `-`. A refusal with no remedy, its fix being no one edit
#: of the value, keeps the words it had and names no line (`None`, `None`):
#: the naming gate's `declared-unverified` reason and the root's
#: `validate-pins.py` print them whole.
LINED = [
    pytest.param("id: atlas\nresolution: `a`\n", 2, "`a`", id="backtick"),
    pytest.param("pins:\n  - x\n  - @y\n", 3, "@y", id="sequence-item"),
    pytest.param("a:\n  b:\n    c: -\n", 3, "-", id="nested-lone-dash"),
    pytest.param("x: 1\n\nk: [ok, %a]\n", 3, "%a", id="flow-entry"),
    pytest.param("- k: ]\n", 1, "]", id="mapping-in-a-sequence"),
    pytest.param("k: ?\n", 1, "?", id="lone-question-mark"),
    pytest.param("x: 1\nk: [a,,b]\n", None, None, id="empty-flow-entry"),
    pytest.param("x: 1\n\nk: *anchor\n", None, None, id="alias"),
    pytest.param("commit: [unclosed\n", None, None, id="unclosed-flow"),
]


@pytest.mark.parametrize("body, line, opener", LINED)
def test_a_refusal_with_a_remedy_names_its_line(tmp_path, body, line,
                                                opener):
    """Read the way every caller reads a file. The words are `parse_yaml`'s,
    unchanged, so a tool that asks about one line quotes no `line 1:`."""
    with pytest.raises(YamlError) as parsed:
        parse_yaml(body)
    words = str(parsed.value)
    assert not words.startswith("line "), words
    path = tmp_path / "file.yaml"
    path.write_bytes(body.encode(UTF8))
    with pytest.raises(Refusal) as caught:
        load_yaml(path)
    assert caught.value.code == "yaml-unparsable"
    where = "" if line is None else f"line {line}: "
    assert caught.value.detail == f"{path}: {where}{words}"
    assert caught.value.remediation == (
        "" if opener is None else remedy_for(opener))


def test_a_refusal_whose_words_name_their_line_names_it_once(tmp_path):
    path = tmp_path / "file.yaml"
    path.write_bytes(b"a:\n\tb: 1\n")
    with pytest.raises(Refusal) as caught:
        load_yaml(path)
    assert caught.value.detail == f"{path}: line 2: tab used for indentation"
    assert caught.value.remediation == ""


@pytest.mark.parametrize("value", [
    "`a`", "@a", "%a", "]", "}", ",", "-", ":", "?", "`a \"b\" \\c`"])
def test_each_spelling_a_remedy_gives_reads_back_as_the_value(value):
    with pytest.raises(YamlError) as caught:
        parse_yaml(f"k: {value}\n")
    spelled = re.search(r"as (\".*\"), or reword",
                        caught.value.remediation).group(1)
    assert parse_yaml(f"k: {spelled}\n") == {"k": value}


def test_the_roots_validate_pins_gives_the_remedy_and_not_the_lockstep(
        project):
    """THE COPY A PROJECT CARRIES. A pin's `commit:` edited to open with an
    indicator is the line and the quoting remedy, where the lockstep remedy
    `validate-pins.py` prints under a refusal that names none was printed:
    a syntax error is not a stale pin."""
    pin = project / "contracts" / "spec-pin.yaml"
    text = pin.read_bytes().decode(UTF8)
    old = re.search(r'^commit: "?[0-9a-f]{40}"?$', text, re.M).group(0)
    pin.write_bytes(text.replace(old, "commit: @x", 1).encode(UTF8))
    line = line_of(pin, "commit: @x")
    checked = run_script(project / "scripts" / "validate-pins.py", "--quiet",
                         cwd=project)
    assert checked.returncode == 2, checked.stderr + checked.stdout
    assert checked.stderr.splitlines() == [
        f"REFUSED yaml-unparsable: contracts/spec-pin.yaml: line {line}: "
        f"{OPENS} "
        "`@`, which is reserved in YAML: '@x'", remedy_for("@x")]
    assert REMEDIATION not in checked.stderr


# --- L4-152: the value named again, under the reader's remedy --------------

def reader_sentence(flag: str, org: str, project: str = PROJECT) -> str:
    """What `plan`, `check` and the scaffold say of `org` on main's pattern:
    one sentence naming the value, with the reader's words for each leg's
    `repository:` line."""
    return (f"{flag} is {org!r}, {READER_REFUSES}" + " ".join(
        f"{OPENS} `@`, which is reserved in YAML: '{org}/{name}'."
        for name in (project, f"{project}-spec", f"{project}-code")))


@pytest.mark.parametrize("org", ["@x", "@opensoft"])
def test_plan_names_org_again_with_the_readers_remedy(world, org):
    out = world["tmp"] / "org-plan.yaml"
    result = write_plan(world["source"], out, org=org)
    assert result.returncode == 2, result.stderr + result.stdout
    assert result.stderr == (
        f"REFUSED {INVALID}: {reader_sentence('--org', org)}\n"
        f"{shape_materialize.MANIFEST_UNREADABLE_REMEDIATION} "
        "No plan was written.\n")
    assert NOT_THE_VALIDATORS not in result.stderr
    assert not out.exists(), "a refused `plan` wrote a plan"


def test_check_names_a_hand_edited_org(world):
    """The same value edited into a plan: `check` names its key."""
    plan = edited(world, "org: testorg", 'org: "@x"')
    said = check(plan)
    assert said.returncode == 1, said.stderr + said.stdout
    lines = said.stderr.splitlines()
    assert [line for line in lines if line.startswith("FINDING ")] == [
        f"FINDING plan-manifest-invalid: {reader_sentence('org', '@x')}"]
    assert (f"{shape_materialize.MANIFEST_UNREADABLE_REMEDIATION} `execute` "
            "writes the plan's values into the project's `project.yaml` as "
            "they stand, so correct each one named here in the plan, or "
            "re-run `plan` with a value the validator accepts.") in lines
    assert NOT_THE_VALIDATORS not in said.stderr


@needs_filter_repo
def test_execute_refuses_a_hand_edited_org_before_any_leg(world):
    """`execute` refuses it in `check`'s words before any leg exists."""
    result = execute(world, edited(world, "org: testorg", 'org: "@x"'))
    assert result.returncode == 2, result.stderr + result.stdout
    assert (f"  FINDING plan-manifest-invalid: "
            f"{reader_sentence('org', '@x')}") in result.stderr.splitlines()
    assert NOT_THE_VALIDATORS not in result.stderr
    no_leg_was_created(world)


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "run"])
def test_the_scaffold_names_org_with_the_readers_remedy(tmp_path, dry_run):
    result = scaffold(tmp_path, "--org=@x",
                      *(["--dry-run"] if dry_run else []))
    assert_refused(result, SCAFFOLD_INVALID)
    assert (f"{SCAFFOLD_INVALID}: {reader_sentence('--org', '@x', 'Atlas')}\n"
            f"{shape_materialize.MANIFEST_UNREADABLE_REMEDIATION} Nothing "
            "was created, and `--dry-run` refuses the same.\n"
            ) in result.stderr
    assert_nothing_was_created(tmp_path)


def test_a_refused_line_that_carries_no_value_names_none(world, adopter,
                                                         tmp_path,
                                                         monkeypatch):
    """Where the line the reader refuses carries none of the values, the
    sentence is the reader's refusal of the file, as before, and its
    remedy is still the reader's, never the validator's."""
    template = tmp_path / "template"
    template.mkdir()
    text = (shape_materialize.ASSEMBLY_TEMPLATE / "project.yaml").read_bytes()
    (template / "project.yaml").write_bytes(text + b"anchored: &anchor 1\n")
    naming = adopter.NamingPolicy.load(adopter.NAMING_POLICY)
    values = adopter._manifest_values(adopter.Plan.load(world["plan"]),
                                      naming)
    whole = ("the manifest this run would write is a file the project's own "
             "YAML reader refuses: anchors, aliases and tags are not "
             "supported: '&anchor 1'.")
    assert shape_materialize.manifest_value_problems(
        values, naming, adopter.MANIFEST_FLAGS, misreads=False,
        template_dir=template) == [("unreadable", whole)]
    monkeypatch.setattr(shape_materialize, "manifest_value_problems",
                        functools.partial(
                            shape_materialize.manifest_value_problems,
                            template_dir=template))
    with pytest.raises(Refusal) as caught:
        shape_materialize.refuse_manifest_values(
            "adopt", values, naming, adopter.MANIFEST_FLAGS,
            "No plan was written.", misreads=False)
    assert caught.value.code == INVALID
    assert caught.value.detail == whole
    assert caught.value.remediation == (
        f"{shape_materialize.MANIFEST_UNREADABLE_REMEDIATION} No plan was "
        "written.")


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "run"])
def test_family_init_still_refuses_org_at(tmp_path, dry_run):
    """Not this issue's to change: refused since #635, before anything is
    created, where main planned `@x/Orbit`."""
    result = init(tmp_path, "--org", "@x", dry_run=dry_run,
                  without=("--org",))
    assert result.returncode == 2, result.stderr + result.stdout
    assert any(line.startswith("REFUSED family-manifest-invalid: ")
               for line in result.stderr.splitlines()), result.stderr
    nothing_was_created(tmp_path)


# --- L4-127: one bad `tracking_branch`, one finding ------------------------

@pytest.mark.parametrize("spelled, value", [
    pytest.param('"a\\ud83db"', "a\ud83db", id="lone-surrogate"),
    pytest.param('"a\\x00b"', "a\x00b", id="nul"),
])
def test_check_names_a_bad_tracking_branch_once(world, spelled, value):
    result = check(edited(world, "tracking_branch: main",
                          f"tracking_branch: {spelled}"))
    assert result.returncode == 1, result.stderr + result.stdout
    assert [line for line in result.stderr.splitlines()
            if line.startswith("FINDING ")] == [
        f"FINDING unsafe-value: tracking_branch is {value!r}, which is not a "
        "value this tool will put on a `git` or `gh` command line"]
    assert "manifest-tracking-branch" not in result.stderr
    assert shape_materialize.MANIFEST_INVALID_REMEDIATION not in result.stderr


@pytest.mark.parametrize("line, left_out", [
    pytest.param("tracking_branch: main", False, id="a-good-branch"),
    pytest.param('tracking_branch: "a\\x00b"', True, id="unsafe-value"),
    # In the alphabet: git's `plan-bad-tracking-branch`, which the
    # validator does not find either.
    pytest.param("tracking_branch: a..b", False, id="git-refuses-it"),
])
def test_the_validators_sentence_is_left_out_where_unsafe_value_fires(
        adopter, world, line, left_out):
    plan = adopter.Plan.load(edited(world, "tracking_branch: main", line))
    assert adopter._validator_ignores(plan) == adopter.LEG_PATH_CODES + (
        adopter.TRACKING_BRANCH_CODES if left_out else ())


def test_adopt_gives_the_one_reader_remedy(adopter):
    """`check`'s remedy is the scaffold's and `plan`'s, not a second copy."""
    assert adopter.MANIFEST_UNREADABLE_REMEDIATION is (
        shape_materialize.MANIFEST_UNREADABLE_REMEDIATION)
    assert NOT_THE_VALIDATORS not in (
        shape_materialize.MANIFEST_UNREADABLE_REMEDIATION)
