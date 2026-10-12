# SPDX-License-Identifier: Apache-2.0
"""`adopt-project.py plan --help` says what `--spec-path` and `--code-path`
are, and what `plan` refuses on them (#340).

Both flags had no `help=`, so `plan --help` and the generated `docs/cli.md`
printed each as a bare line, for the two values that choose where a leg is
mounted in the assembly root and what the plan records as `legs.spec_path` and
`legs.code_path`. `plan` refuses two kinds of value for them before it writes
anything: `adopt-bad-leg-path` (#169) and `adopt-leg-path-collides` (#172), and
a reader of the flag-level reference learned of neither.

`tests/test_cli_reference.py` holds `docs/cli.md` to `--help`, so it cannot say
the help is MISSING; it agrees with whatever the tool prints. These tests say
what the help must carry, and hold each claim to the tool: every refusal the
help names is the one `plan` prints for a value the help describes, and a value
the help does not describe as refused is one `plan` writes a plan for. A help
that claimed more or less than `plan` does would read as authority and be
wrong, which is worse than the bare line.

The help is read at ONE width and with no colour (`plan_help`), whatever the
shell that runs pytest exports: argparse wraps to `COLUMNS`, and `textwrap`
breaks a hyphenated word at a line end, which is how `adopt-leg-path-collides`
reached `docs/cli.md` as `adopt-leg-path-` and `collides` (an assistant that
greps the reference for the string `plan` prints would miss it).

Nothing here makes a leg or reaches `gh`: `plan` reads a local source and
writes a file.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import ADOPT, make_source_repo, run_script, write_plan

BAD_SPELLING = "adopt-bad-leg-path"
COLLIDES = "adopt-leg-path-collides"

#: `(flag, the role it names, its default)`.
FLAGS = (("--spec-path", "spec", "spec"), ("--code-path", "code", "code"))


#: The width `docs/cli.md` is rendered at (`scripts/render-cli-reference.py`
#: pins `COLUMNS` for the same reason), and no colour: Python 3.14's argparse
#: colours help when `FORCE_COLOR` is exported, and `NO_COLOR` beats it.
HELP_ENV = {"COLUMNS": "80", "NO_COLOR": "1"}


@pytest.fixture(scope="module")
def plan_help() -> str:
    result = run_script(ADOPT, "plan", "--help", env=HELP_ENV)
    assert result.returncode == 0, result.stderr + result.stdout
    return result.stdout


def option_lines(text: str, flag: str) -> list[str]:
    """The lines `--help` prints for `flag`, stripped: whatever shares the
    option's own line after the metavar, then the lines below it.

    argparse indents an option by two spaces and its help by more. The usage
    block at the top names the flag too, so only a line that STARTS with the
    option is read. Raises when `plan --help` lists no such option, and
    returns `[]` when it lists one with no description.
    """
    lines = text.splitlines()
    for number, line in enumerate(lines):
        if not line.startswith(f"  {flag} "):
            continue
        # `--spec-path SPEC_PATH`, then whatever help shares the line.
        words = [" ".join(line.split(None, 2)[2:])]
        for follower in lines[number + 1:]:
            if not follower.startswith("    "):
                break
            words.append(follower.strip())
        return [word for word in words if word]
    raise AssertionError(f"`plan --help` does not list {flag}")


def option_help(text: str, flag: str) -> str:
    """The help `--help` prints for `flag`, its wrapped lines joined and its
    whitespace collapsed; `""` when it prints none.

    A line `textwrap` ended at a hyphen inside a word (`adopt-leg-path-` and
    `collides`) is joined to the next without a space, so a phrase a test
    asserts reads the same wherever the wrap fell.
    `test_a_code_is_never_split_across_two_lines_of_the_help` is what says
    such a wrap, of a code, is a defect in its own right.
    """
    joined = ""
    for line in option_lines(text, flag):
        glue = "" if re.search(r"\w-$", joined) else " "
        joined = f"{joined}{glue}{line}" if joined else line
    return " ".join(joined.split())


@pytest.fixture(scope="module")
def source(tmp_path_factory) -> Path:
    """One local source, read by every `plan` run here and changed by none."""
    return make_source_repo(tmp_path_factory.mktemp("leg-path-help") / "Thing")


def plan_with(source: Path, tmp_path: Path, *flags: str):
    out = tmp_path / "plan.yaml"
    return write_plan(source, out, project="Northwind", extra=flags), out


@pytest.mark.parametrize("flag, role, default", FLAGS)
def test_each_leg_path_flag_says_what_it_is_and_what_plan_refuses(
        plan_help, flag, role, default):
    help_text = option_help(plan_help, flag)
    assert help_text, f"`plan --help` prints {flag} with no description"
    # What the flag is, the default it records and the key it records it at.
    assert f"where the {role} leg is mounted" in help_text
    assert f"(default: {default})" in help_text
    assert f"`legs.{role}_path`" in help_text
    # The two refusals `plan` makes, by the codes it prints, and what each
    # one is about.
    assert f"`{BAD_SPELLING}`" in help_text
    assert f"`{COLLIDES}`" in help_text
    for named in ("`project.yaml`", "`contracts`", "`shape/`", "`.git`",
                  f"`{default}/`", f"`./{default}`", "`a//b`", "`..`",
                  # Every clause a REFUSED row below exercises, by the words
                  # a reader would look for. The rows also name their own.
                  "a backslash", "`CON`", "Windows", "ASCII letters",
                  "begins with `-`", "ends in a dot", "is empty or `.`",
                  "longer than 255 characters",
                  "the other leg's path, whatever the case",
                  "`shape/`, whatever the case", "`Remediation:`"):
        assert named in help_text, f"{flag}'s help never names {named}"


@pytest.mark.parametrize("flag, role, default", FLAGS)
@pytest.mark.parametrize("code", (BAD_SPELLING, COLLIDES))
def test_a_code_is_never_split_across_two_lines_of_the_help(
        plan_help, flag, role, default, code):
    """`docs/cli.md` is the flag-level reference an assistant greps for the
    string `plan` prints. At 80 columns `textwrap` breaks a hyphenated word at
    a line end, so a code that falls at one reads `adopt-leg-path-` and then
    `collides`, and the grep finds nothing. Reword the help until each code
    sits whole on a line, for BOTH flags: their examples differ in length."""
    lines = option_lines(plan_help, flag)
    assert any(f"`{code}`" in line for line in lines), (
        f"`{code}` is split across lines of {flag}'s help at 80 columns:\n"
        + "\n".join(lines))


def test_the_two_flags_are_said_by_one_rule(plan_help):
    """`--code-path`'s help is `--spec-path`'s with the role and the default
    swapped. A rule said twice by hand is how the second copy goes stale."""
    spec = option_help(plan_help, "--spec-path")
    code = option_help(plan_help, "--code-path")
    assert spec and code, "a flag with no help is the same as another"
    swapped = (spec.replace("spec leg", "code leg")
               .replace("legs.spec_path", "legs.code_path")
               .replace("default: spec", "default: code")
               .replace("`spec/`", "`code/`").replace("`./spec`", "`./code`"))
    assert swapped == code


def an_id(flags) -> str:
    """A test id for a row, with a long value shortened."""
    return " ".join(f"<{len(word)} characters>" if len(word) > 40 else word
                    for word in flags)


def flag_of(argument: str) -> str:
    """`--spec-path` for `--spec-path=-x`: a value that begins with `-` is
    passed as one argument, because argparse reads a separate `-x` as an
    option of its own."""
    return argument.partition("=")[0]


#: `(the flags, the refusal `plan` prints for them, the words of the help that
#: carry the clause)`. Every refusal the help describes, once by each of its
#: clauses: the SPELLING of the path first, then the NAMES Git and Windows
#: keep, then the two legs against each other, then what the shape writes. A
#: value is spelled as one argument, so a backslash and a space reach `plan`
#: as the person typed them. The last column is what holds the HELP to the
#: tool: a clause that drops out of the help fails the row that exercises it,
#: where the code alone would still match.
REFUSED = (
    (("--spec-path", "spec/"), BAD_SPELLING, "is not in Git's own spelling"),
    (("--spec-path", "./spec"), BAD_SPELLING, "is not in Git's own spelling"),
    (("--code-path", "a//b"), BAD_SPELLING, "is not in Git's own spelling"),
    (("--spec-path", "/spec"), BAD_SPELLING, "is absolute"),
    (("--spec-path", "../spec"), BAD_SPELLING, "has a `..` segment"),
    (("--code-path", "legs\\code"), BAD_SPELLING, "a backslash"),
    (("--spec-path", "a b"), BAD_SPELLING,
     "a character outside ASCII letters, digits and `._/@+~-`"),
    # Not in the alphabet: ASCII only, whatever a person reads as a letter.
    (("--spec-path", "\u00e9"), BAD_SPELLING,
     "a character outside ASCII letters, digits and `._/@+~-`"),
    # What the alphabet allows is not all a leg path may begin or end with.
    (("--spec-path", "spec."), BAD_SPELLING, "a segment that ends in a dot"),
    (("--spec-path", "legs./code"), BAD_SPELLING,
     "a segment that ends in a dot"),
    (("--spec-path=-x",), BAD_SPELLING, "begins with `-`"),
    (("--spec-path=",), BAD_SPELLING, "is empty or `.`"),
    (("--spec-path=.",), BAD_SPELLING, "is empty or `.`"),
    (("--code-path", "a" * 256), BAD_SPELLING, "longer than 255 characters"),
    (("--spec-path", ".git"), BAD_SPELLING,
     "has a segment Git or Windows reserves (`.git`"),
    (("--code-path", "legs/CON"), BAD_SPELLING, "`.git`, `CON`)"),
    # The other leg's path: the default `code` equals it, holds it, lies
    # inside it, and differs from it only in case.
    (("--spec-path", "code"), BAD_SPELLING, "the other leg's path"),
    (("--spec-path", "code/x"), BAD_SPELLING, "the other leg's path"),
    (("--spec-path", "Code"), BAD_SPELLING,
     "the other leg's path, whatever the case"),
    (("--spec-path", "legs", "--code-path", "legs/x"), BAD_SPELLING,
     "the other leg's path"),
    # A FILE the shape writes into the root, a path inside one, and a
    # directory that holds several, in the case the shape spells them or not.
    (("--spec-path", "project.yaml"), COLLIDES,
     "a FILE the shape writes into the root (`project.yaml` is one"),
    (("--code-path", "project.yaml/x"), COLLIDES,
     "a FILE the shape writes into the root (`project.yaml` is one"),
    (("--spec-path", "contracts"), COLLIDES, "`contracts` holds several"),
    (("--code-path", "Contracts"), COLLIDES, "`contracts` holds several"),
    (("--spec-path", "Project.yaml"), COLLIDES,
     "`shape/`, whatever the case"),
    (("--code-path", "CONTRACTS"), COLLIDES, "`shape/`, whatever the case"),
    (("--spec-path", ".github"), COLLIDES, "a FILE the shape writes"),
    # `shape/`, where `execute` writes its copy of a file the root holds.
    (("--spec-path", "shape"), COLLIDES, "at or under `shape/`"),
    (("--code-path", "shape/x"), COLLIDES, "at or under `shape/`"),
    (("--code-path", "SHAPE"), COLLIDES, "`shape/`, whatever the case"),
    (("--spec-path", "Shape/x"), COLLIDES, "`shape/`, whatever the case"),
)


@pytest.mark.parametrize("flags, code, clause", REFUSED,
                         ids=[an_id(flags) for flags, _, _ in REFUSED])
def test_every_refusal_the_help_describes_is_the_one_plan_prints(
        plan_help, source, tmp_path, flags, code, clause):
    result, out = plan_with(source, tmp_path, *flags)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(f"REFUSED {code}: "), result.stderr
    assert not out.exists(), "a refused plan must leave no file behind"
    # The closing sentence: a refusal rewrites nothing, and its Remediation
    # states the rule.
    remediation = [line for line in result.stderr.splitlines()
                   if line.startswith("Remediation: ")]
    assert remediation and remediation[0].startswith(
        ("Remediation: nothing here rewrites",
         "Remediation: nothing here picks")), result.stderr
    for flag in {flag_of(argument) for argument in flags[::2]}:
        described = option_help(plan_help, flag)
        assert f"`{code}`" in described, (
            f"`plan` refuses {flags} as {code}, and {flag}'s help never "
            f"names it")
        assert clause in described, (
            f"`plan` refuses {an_id(flags)} as {code}, and {flag}'s help "
            f"does not carry the clause that says why: {clause!r}")


#: Values a project's YAML reader reads back as something other than text.
#: `plan` writes a plan for them today (#181) and refuses them once a leg path
#: is asked of the project's reader (#225). The help says neither, so it is
#: true whichever change lands first; what it DOES say of a refusal holds for
#: this one too: the code, no plan file, and a Remediation.
YAML_NOT_TEXT = ("null", "2026", "true", "1.5")


@pytest.mark.parametrize("value", YAML_NOT_TEXT)
def test_a_word_yaml_reads_as_not_text_is_planned_or_refused_as_the_help_says(
        plan_help, source, tmp_path, value):
    result, out = plan_with(source, tmp_path, "--spec-path", value)
    if result.returncode == 0:
        assert out.exists(), result.stdout + result.stderr
        return
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(f"REFUSED {BAD_SPELLING}: "), result.stderr
    assert not out.exists(), "a refused plan must leave no file behind"
    assert any(line.startswith("Remediation: ")
               for line in result.stderr.splitlines()), result.stderr
    assert f"`{BAD_SPELLING}`" in option_help(plan_help, "--spec-path")


#: Values the help does not describe as refused. `contracts/x` is the one a
#: reading of "holds" could get wrong: the SHAPE's file is `contracts/
#: spec-pin.yaml`, so `contracts` is refused and a path beside it is not.
#: `.specify` and `docs/spec` overlap only a source path the plan KEEPS in the
#: root, which `plan` notes and `check` reports, and refuses nothing for.
ACCEPTED = (
    ("--spec-path", "contracts/x"),
    ("--code-path", "legs/code"),
    ("--spec-path", "docs/spec"),
    ("--spec-path", ".specify"),
    ("--code-path", "project"),
    ("--code-path", "shapes"),
)


@pytest.mark.parametrize("flag, value", ACCEPTED,
                         ids=[f"{flag} {value}" for flag, value in ACCEPTED])
def test_a_value_the_help_does_not_describe_as_refused_is_planned_and_recorded(
        plan_help, source, tmp_path, flag, value):
    role = flag.removeprefix("--").removesuffix("-path")
    assert f"`legs.{role}_path`" in option_help(plan_help, flag)
    result, out = plan_with(source, tmp_path, flag, value)
    assert result.returncode == 0, result.stdout + result.stderr
    # Recorded in the `legs:` block, as the help says.
    legs = out.read_text(encoding="utf-8").split("\nlegs:\n", 1)[1]
    assert f"\n  {role}_path: {value}\n" in "\n" + legs.split("\n\n", 1)[0] + "\n"


def test_the_defaults_pass_and_are_the_ones_the_help_names(plan_help, source,
                                                           tmp_path):
    assert "The defaults `spec` and `code` pass." in option_help(
        plan_help, "--spec-path")
    result, out = plan_with(source, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    legs = out.read_text(encoding="utf-8").split("\nlegs:\n", 1)[1]
    block = "\n" + legs.split("\n\n", 1)[0] + "\n"
    assert "\n  spec_path: spec\n" in block
    assert "\n  code_path: code\n" in block
