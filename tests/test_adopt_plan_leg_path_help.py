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

Nothing here makes a leg or reaches `gh`: `plan` reads a local source and
writes a file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import ADOPT, make_source_repo, run_script, write_plan

BAD_SPELLING = "adopt-bad-leg-path"
COLLIDES = "adopt-leg-path-collides"

#: `(flag, the role it names, its default)`.
FLAGS = (("--spec-path", "spec", "spec"), ("--code-path", "code", "code"))


@pytest.fixture(scope="module")
def plan_help() -> str:
    result = run_script(ADOPT, "plan", "--help")
    assert result.returncode == 0, result.stderr + result.stdout
    return result.stdout


def option_help(text: str, flag: str) -> str:
    """The help `--help` prints for `flag`, its wrapped lines joined and its
    whitespace collapsed; `""` when it prints none.

    argparse indents an option by two spaces and its help by more, either on
    the option's own line, after the metavar, or on the lines below it. The
    usage block at the top names the flag too, so only a line that STARTS with
    the option is read.
    """
    lines = text.splitlines()
    for number, line in enumerate(lines):
        if not line.startswith(f"  {flag} "):
            continue
        # `--spec-path SPEC_PATH`, then whatever help shares the line.
        words = line.split(None, 2)[2:]
        for follower in lines[number + 1:]:
            if not follower.startswith("    "):
                break
            words.append(follower.strip())
        return " ".join(" ".join(words).split())
    raise AssertionError(f"`plan --help` does not list {flag}")


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
                  f"`{default}/`", f"`./{default}`", "`a//b`", "`..`"):
        assert named in help_text, f"{flag}'s help never names {named}"


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


#: `(the flags, the refusal `plan` prints for them)`. Every refusal the help
#: describes, once by each of its clauses: the SPELLING of the path first,
#: then the NAMES Git and Windows keep, then the two legs against each other,
#: then what the shape writes. A value is spelled as one argument, so a
#: backslash and a space reach `plan` as the person typed them.
REFUSED = (
    (("--spec-path", "spec/"), BAD_SPELLING),
    (("--spec-path", "./spec"), BAD_SPELLING),
    (("--code-path", "a//b"), BAD_SPELLING),
    (("--spec-path", "/spec"), BAD_SPELLING),
    (("--spec-path", "../spec"), BAD_SPELLING),
    (("--code-path", "legs\\code"), BAD_SPELLING),
    (("--spec-path", "a b"), BAD_SPELLING),
    (("--spec-path", ".git"), BAD_SPELLING),
    (("--code-path", "legs/CON"), BAD_SPELLING),
    # The other leg's path: the default `code` equals it, holds it, lies
    # inside it, and differs from it only in case.
    (("--spec-path", "code"), BAD_SPELLING),
    (("--spec-path", "code/x"), BAD_SPELLING),
    (("--spec-path", "Code"), BAD_SPELLING),
    (("--spec-path", "legs", "--code-path", "legs/x"), BAD_SPELLING),
    # A FILE the shape writes into the root, a path inside one, and a
    # directory that holds several.
    (("--spec-path", "project.yaml"), COLLIDES),
    (("--code-path", "project.yaml/x"), COLLIDES),
    (("--spec-path", "contracts"), COLLIDES),
    (("--code-path", "Contracts"), COLLIDES),
    (("--spec-path", ".github"), COLLIDES),
    # `shape/`, where `execute` writes its copy of a file the root holds.
    (("--spec-path", "shape"), COLLIDES),
    (("--code-path", "shape/x"), COLLIDES),
    (("--code-path", "SHAPE"), COLLIDES),
)


@pytest.mark.parametrize("flags, code", REFUSED,
                         ids=[" ".join(flags) for flags, _ in REFUSED])
def test_every_refusal_the_help_describes_is_the_one_plan_prints(
        plan_help, source, tmp_path, flags, code):
    result, out = plan_with(source, tmp_path, *flags)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(f"REFUSED {code}: "), result.stderr
    assert not out.exists(), "a refused plan must leave no file behind"
    for flag in flags[::2]:
        assert f"`{code}`" in option_help(plan_help, flag), (
            f"`plan` refuses {flags} as {code}, and {flag}'s help never "
            f"names it")


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
