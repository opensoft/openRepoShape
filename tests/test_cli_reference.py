# SPDX-License-Identifier: Apache-2.0
"""`docs/cli.md` is GENERATED, and this is what keeps it that way.

The file is a flag-level reference for an agent (#97, Brett Heap's *"add the
docs/cli.md"*), rendered from every shipped tool's own `--help` by
`scripts/render-cli-reference.py`. A generated document nobody re-generates is
a hand-written one with a misleading header, and the flags it lists then drift
exactly the way a hand-edited pin drifts — quietly, in front of whoever was not
looking. So: regenerate into a temporary path and compare BYTES.

WINDOWS. Two of the seventeen entry points are bash, and the windows job has no
bash it can use — `tests/conftest.py::WINDOWS_SKIP` says why at length (the
`bash.exe` on a stock Windows PATH is the WSL launcher, which `shutil.which`
finds and which answers a different question). The byte-equality test is
therefore `WINDOWS_SKIP`ped, and the ubuntu and macOS jobs — the two platforms
that have a bash, and the kind of machine the committed file is generated on —
are what carry it. The alternative, comparing a Windows-shortened rendering
against a subset of the committed file, would make this test assert a claim
about WHICH HALF MATTERS, written by whoever wrote the subset; that is the
objection `.github/workflows/tests.yml` already makes to running a
Windows-shaped subset of the suite at all.

What runs EVERYWHERE, windows included, is the rest of it: the header, the
derived-from-the-repository list of entry points that must each have a section,
and — the one with teeth on that platform —
`test_every_python_tools_help_is_the_text_the_file_carries`, which captures
each of the fifteen PYTHON tools' help for itself and asserts the committed
file carries that text. Real drift in any of them fails on all three runners;
only drift in `setup.sh` or `openRepoShape` needs one with a bash.

Rule 1 is not re-asserted here. `tests/test_repo_hygiene.py::test_no_committed_
file_names_a_host_absolute_path` walks every tracked file, this one included,
and the generator refuses to WRITE a rendering that carries one — a guard
before the file exists and a guard after it is committed, which is the right
number for the one file in this repository whose bytes come from running
programs on somebody's machine.
"""

from __future__ import annotations

import ast
import difflib
import importlib.util

import pytest

from conftest import REPO, WINDOWS_SKIP

REFERENCE = REPO / "docs" / "cli.md"
GENERATOR = REPO / "scripts" / "render-cli-reference.py"

#: THE SENTENCE THAT MUST SURVIVE, spelled here rather than imported from the
#: generator. Importing the constant would make this assertion agree with the
#: generator by construction, and the property is not "the two agree" — it is
#: that the file SAYS it is generated, says by what, and says which test to
#: run, so that somebody who opens it with an editor is told before they type.
#: Compared with whitespace collapsed on both sides, so re-wrapping the
#: paragraph is not a failure.
HEADER_SENTENCE = (
    "**GENERATED** by `scripts/render-cli-reference.py`; do not edit. "
    "The test that keeps it honest is `tests/test_cli_reference.py`.")

#: The command the failure messages name. One string, so the three of them
#: cannot start naming different ones.
REGENERATE = "python3 scripts/render-cli-reference.py"

#: NOT AN ENTRY POINT OF THE STANDARD, and the only name the derivation below
#: excuses. The generator is how this REPOSITORY maintains the reference, not
#: a command anybody runs to scaffold, adopt, update or diagnose anything —
#: and it is not undocumented either: `docs/cli.md`'s own header line names
#: it, which is how a reader finds it.
NOT_A_CLI_OF_THE_STANDARD = {"scripts/render-cli-reference.py"}


def generator_module():
    """`scripts/render-cli-reference.py` imported as a module.

    The filename has a hyphen and cannot be imported by name;
    `tests/test_repo_hygiene.py::entry_point_module` does the same for
    `setup-project.py` for the same reason.
    """
    spec = importlib.util.spec_from_file_location("render_cli_reference",
                                                  GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def committed() -> str:
    assert REFERENCE.is_file(), (
        f"{REFERENCE.name} is not there; generate it with `{REGENERATE}`")
    return REFERENCE.read_bytes().decode("utf-8")


def _has_a_main(path) -> bool:
    """A module-level `def main(...)`, by AST rather than by grep.

    `scripts/repo_shape.py`, `scripts/shape_materialize.py` and
    `scripts/path_classify.py` are libraries the tools import and have none,
    which is exactly the line this draws: a file with a `main` is a file
    somebody can type at a shell, and every one of those belongs in the
    reference.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return False
    return any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
               and node.name == "main" for node in tree.body)


def entry_points() -> list:
    """Every entry point this repository has, DERIVED, never listed.

    Written down twice is written down once and remembered once. The
    candidates are the two bash front doors, the `bootstrap` shim (a Python
    file with no extension, so no glob finds it), and every `*.py` at the
    root, under `scripts/`, or under a root template's `scripts/` that has a
    `main`. A tool added tomorrow and forgotten here fails NAMING ITSELF.
    """
    found = ["setup.sh", "openRepoShape", "bootstrap"]
    directories = [REPO, REPO / "scripts",
                   REPO / "templates" / "assembly-root" / "scripts",
                   REPO / "templates" / "family-root" / "scripts"]
    for directory in directories:
        for path in sorted(directory.glob("*.py")):
            if _has_a_main(path):
                found.append(path.relative_to(REPO).as_posix())
    return [name for name in found if name not in NOT_A_CLI_OF_THE_STANDARD]


def test_the_header_says_the_file_is_generated_and_names_its_guard(committed):
    """The one sentence an editor must meet before they type anything."""
    assert " ".join(HEADER_SENTENCE.split()) in " ".join(committed.split()), (
        f"docs/cli.md must carry, in its header:\n    {HEADER_SENTENCE}")


def test_every_entry_point_of_this_repository_has_a_section(committed):
    """A new tool cannot be forgotten, because the list is not a list."""
    missing = [name for name in entry_points()
               if f"### `{name}`" not in committed]
    assert not missing, (
        f"docs/cli.md has no section for {missing}. Every entry point this "
        f"repository ships is in the reference; add the tool to `CHECKOUT_"
        f"TOOLS` or `PROJECT_TOOLS` in scripts/render-cli-reference.py, with "
        f"the one line saying what it is FOR, and regenerate: `{REGENERATE}`")


def test_both_groups_are_there_and_the_project_copies_say_where_they_run(
        committed):
    """The second group is the half a reader acts on wrongly.

    Six of the seventeen are COPIES that land in a scaffolded project or a
    family holder and are run from THERE. An agent who met them in one flat
    list would try to run `validate-pins.py` in a checkout of this standard,
    where there is no `project.yaml` to validate.
    """
    assert "## Run from a checkout of the standard" in committed
    assert "## Shipped into every project (copied, digest-pinned)" in committed
    for name in ("bootstrap.py", "validate-manifest.py", "validate-pins.py",
                 "siblings.py", "validate-family.py"):
        assert f"Run as `python3 scripts/{name}` from inside" in committed, (
            f"the reference does not say where scripts/{name} is run from")


def test_every_python_tools_help_is_the_text_the_file_carries(committed):
    """THE WINDOWS JOB'S TEETH, and a check the other two run as well.

    Fifteen of the seventeen entry points are Python and run on every
    platform this suite runs on. Each one's help is captured here, on this
    machine, and must be text the committed file already carries — so a flag
    added to `shape-doctor.py` without regenerating the reference fails on
    the windows runner too, where the byte-equality test below is skipped.
    """
    module = generator_module()
    stale = []
    for group in (module.CHECKOUT_TOOLS, module.PROJECT_TOOLS):
        for tool in group:
            if tool.runner != "python":
                continue
            body = module.capture_help(tool)
            if body not in committed:
                stale.append(tool.path)
                continue
            for name in module.subcommands(body):
                if module.capture_help(tool, name) not in committed:
                    stale.append(f"{tool.path} {name}")
    assert not stale, (
        f"docs/cli.md does not carry the help {stale} print(s) today. "
        f"Regenerate it: `{REGENERATE}`")


@WINDOWS_SKIP
def test_the_committed_reference_is_what_the_generator_produces(committed):
    """Byte for byte, bash entry points included. See the module docstring
    for why this one is the test the windows job does not run."""
    rendered = generator_module().render()
    if rendered == committed:
        return
    diff = "".join(difflib.unified_diff(
        committed.splitlines(keepends=True),
        rendered.splitlines(keepends=True),
        fromfile="a/docs/cli.md (committed)",
        tofile="b/docs/cli.md (what the generator produces now)"))
    pytest.fail(
        "docs/cli.md is not what scripts/render-cli-reference.py produces. "
        "It is GENERATED: do not edit it to make this pass — change the tool "
        "whose help moved, or the generator, and then run\n"
        f"    {REGENERATE}\n\n{diff}")


#: `family.py bump`'s usage line, AS PYTHON 3.12 AND PYTHON 3.14 SPELL IT.
#: The only difference between the two interpreters across all twenty-two
#: help texts, measured while writing this: 3.14's argparse keeps an option
#: and its metavar together and 3.12's does not, so the break lands either
#: side of `--to`. `.github/workflows/tests.yml` pins `python-version:
#: '3.x'`, which means the runner image decides which of these the byte
#: comparison above would see.
USAGE_AS_312 = (
    "usage: family.py bump [-h] --family-root FAMILY_ROOT --member PROJECT "
    "--to\n                      COMMIT\n\noptions:\n  -h, --help  show it\n")
USAGE_AS_314 = (
    "usage: family.py bump [-h] --family-root FAMILY_ROOT --member PROJECT\n"
    "                      --to COMMIT\n\noptions:\n  -h, --help  show it\n")


def test_child_env_pins_a_deterministic_locale(monkeypatch):
    """Copilot review, PR #98: `child_env()` used to copy `LANG`/`LC_*`
    straight from `os.environ`, so a runner whose inherited locale is not
    actually installed there made bash write a `setlocale` warning onto the
    stderr this script captures — noise that would then land in the
    committed reference on that one platform only. Every such variable must
    be gone, and `LC_ALL` must be the one value that replaces them all.
    """
    for name in ("LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE", "LC_MESSAGES",
                 "LC_COLLATE"):
        monkeypatch.setenv(name, "xx_XX.not-a-real-locale")
    module = generator_module()
    env = module.child_env()
    assert env["LC_ALL"] == "C"
    leaked = {name: value for name, value in env.items()
              if name != "LC_ALL"
              and (name == "LANG" or name == "LANGUAGE"
                   or name.startswith("LC_"))}
    assert not leaked, f"child_env() still passes through {leaked}"


def test_the_usage_block_normalises_the_same_on_either_python():
    """The version-proofing, asserted without a second interpreter.

    A test that needed 3.12 AND 3.14 installed to prove this would prove it
    on nobody's machine and in no CI job. Both real spellings are pinned
    above instead, and the property is that they normalise to ONE string —
    and that the string is still the same tokens, so the re-wrap is a
    re-break and never a rewrite.
    """
    module = generator_module()
    first = module.rewrap_usage(USAGE_AS_312)
    second = module.rewrap_usage(USAGE_AS_314)
    assert first == second, (
        "the two Python versions' usage lines do not normalise to the same "
        f"bytes:\n{first!r}\n{second!r}")
    assert first.split() == USAGE_AS_312.split() == USAGE_AS_314.split(), (
        "the re-wrap changed the TOKENS, not only the line breaks")
    assert all(len(line) <= module.WIDTH for line in first.split("\n")), (
        f"the re-wrapped usage block is wider than {module.WIDTH} columns")


#: A host-absolute path, SPELLED AS TWO PIECES so that this file does not
#: itself carry one — the same dodge `tests/test_repo_hygiene.py` uses for
#: the Claude scratchpad prefix, and for the same reason: the tree-wide guard
#: reads this file too.
_A_HOST_PATH = "/home/" + "somebody/projects/Thing"


def test_the_generators_host_absolute_pattern_matches_tests_test_repo_hygiene():
    """Copilot review, PR #98: the generator's own `HOST_ABSOLUTE` had drifted
    from `tests/test_repo_hygiene.py::HOST_ABSOLUTE_PATH` — it recognised
    neither a Claude Code scratchpad path nor the CI Windows runner's own
    `C:\\Users\\runneradmin\\` account — so a leaked scratchpad path would
    reach docs/cli.md and only the hygiene test, run separately, would ever
    catch it. Same four cases, checked against the generator's own pattern.
    """
    module = generator_module()
    # Every example below is SPELLED IN PIECES, like `_A_HOST_PATH` below and
    # `tests/test_repo_hygiene.py`'s own `_CLAUDE_TMP_PREFIX`: a contiguous
    # literal here would make this file the very thing
    # `test_no_committed_file_names_a_host_absolute_path` refuses.
    scratchpad = "/" + "tmp/claude-1000/-home-brett-projects-x/scratch"
    assert module.HOST_ABSOLUTE.search(scratchpad), (
        "HOST_ABSOLUTE does not recognise a Claude Code scratchpad path")
    windows_user = "C:" + r"\Users\dana\stuff"
    assert module.HOST_ABSOLUTE.search(windows_user), (
        "HOST_ABSOLUTE does not recognise a real Windows user path")
    windows_runner = "C:" + r"\Users\runneradmin\stuff"
    assert not module.HOST_ABSOLUTE.search(windows_runner), (
        "HOST_ABSOLUTE must not flag the GitHub Windows runner's own account")
    assert module.HOST_ABSOLUTE.search(_A_HOST_PATH), (
        "HOST_ABSOLUTE does not recognise a Linux/macOS home directory")


def test_the_generator_refuses_a_host_absolute_path():
    """Rule 1, before the file exists rather than after it is committed.

    No tool prints a `$HOME`-dependent default today — `scaffold-project.py`
    says `--work-dir` defaults to "a temporary directory" rather than naming
    one — so this asserts the machinery rather than a current output: the
    pattern SEES such a path, and the placeholder substitution is what a
    default under the generating machine's own home would meet on the way
    out.
    """
    module = generator_module()
    assert module.HOST_ABSOLUTE.search(_A_HOST_PATH), (
        "the generator's Rule 1 pattern does not recognise a host path")
    home = str(module.Path.home())
    assert not module.HOST_ABSOLUTE.search(
        module.placehold_host_paths(f"--work-dir {home}/scratch (default)")), (
        "a path under this machine's home directory survived the "
        "placeholder substitution")


@WINDOWS_SKIP
def test_the_generators_own_check_agrees_with_this_suite():
    """`--check` writes nothing and answers the question this file asks.

    It is what a person runs after changing a tool's help, and the failure
    messages above name it. A `--check` that disagreed with the test would
    send somebody round a loop.

    SKIPPED ON WINDOWS for the reason the byte comparison above is: `--check`
    compares against the WHOLE committed file, and a rendering made where the
    bash entry points cannot run is short two sections. The generator refuses
    the combination rather than answering it — `--check` there exits 3 and
    says to run it where there is a bash — so this test would be asserting
    the refusal rather than the agreement.
    """
    module = generator_module()
    assert module.main(["--check"]) == 0, (
        f"`{REGENERATE} --check` disagrees with this suite; one of the two "
        "is wrong")
