# SPDX-License-Identifier: Apache-2.0
"""`check` and `execute` name the two paths the caller typed, `--plan` and
`--local-remote-dir`, as every other path in their report is named (#1152,
after #1115, which did the same for `plan --out` and `--work-dir`).

`N finding(s) in {plan.path}` and the refusals that begin `{plan.path}: ...`
printed the typed `--plan` as it was, and so did the lines `execute` says of
`--local-remote-dir`: `bare  {path}`, `... -> {url}` after each leg, the
`{bare} already exists` refusal and `split ... -> {url}`. A path holding
U+202E (a bidi override), an escape, a line feed or a byte that is not UTF-8
reached the terminal unspelled: the override reverses what is printed after
it, an escape starts a terminal sequence, a line feed splits the line, and a
byte that is not UTF-8 raised `UnicodeEncodeError` on a strict stdout. The
`source` line, the table and the follow-ups already name such a path with
`_shown` (#199, #900): as it is when every character in it is printable, and
otherwise between two backticks, each character as the plan's own `path:`
writes it. Every site below says it with `_shown` now.

WHAT EACH ROW IS. Each refusal family is run as a person runs it, as a child,
under `check` and under `execute --yes` (the same code, in the same words,
where both reach it), with the plan at a path that holds one of the four
characters above, and once at a plain path as the control. The control passes
on main as well: a path whose every character is printable is not respelled
and not wrapped in backticks.

THE SPLIT ROW CANNOT HOLD THOSE FOUR. Under `--local-remote-dir` `split ... ->`
names the SOURCE's own path, which `execute` refuses before any leg exists as
`adopt-unwritable-value` when it holds a bidi control, a control character, a
line break or a byte that is not UTF-8 (#255). What it lets through and
`_shown` spells is a character that is invisible and not unwritable (U+200B,
a `Cf`) and a name that ends in a space, which reads as nothing: those two
are the rows.

NO NETWORK AND NO GITHUB. A GitHub-mode `execute` row here is refused before
`_repository_urls` returns, so before anything is asked of `gh` (a plan that
names no source, a name or an `org:` GitHub will not hold, a topic it will not
set, a plan for another repository); the rows that go further run under
`--local-remote-dir`. A GitHub-mode `check` asks `gh repo view` of each leg,
which the session's `gh` guard (`tests/gh_guard.py`) answers as a `gh` with no
login does. A child that prints a byte that is not UTF-8 raw is read back with
`surrogateescape`, so main's raw byte is a lone surrogate here and the spelled
`\\udcff` is six ASCII characters. POSIX only: no Windows file name holds a
line feed, an escape or byte 0xff.

THE FOLLOW-UPS (#1195, from RV1177's review of #1177). Rows for what the
first 148 left to chance, each a mutant that passed all of them: a `--plan`
that `str.isprintable` passes, which #900's two rules spell or which is
relative; a PLACEMENT plan's `plan-wrong-kind`, and `adopt-org-too-long`;
a printable `--local-remote-dir` outside ASCII; and, in
`tests/test_adopt_github_exits.py`, the GitHub-mode `split` line. And two
routes that printed a path raw: a refused command's REFUSED block, which
now spells the remote and work directories, and `NEXT:`'s clone command,
before which a NOTE now says when the path in it holds a character a
terminal does not show as itself.

THE TEST SOURCE IS ASCII: every character that is not printable is written as
an escape.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, NamedTuple

import pytest

from conftest import (ADOPT, IDENTITY_EMAIL, IDENTITY_NAME,
                      blank_unnamed_pin_sources, git, make_source_repo,
                      skip_where_a_name_cannot_be_not_utf_8,
                      skip_where_the_environment_cannot_carry, write_plan)

pytestmark = pytest.mark.skipif(
    os.name == "nt",
    reason="no Windows file name holds a line feed, an escape or the byte "
           "0xff")

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

ORG = "testorg"
PROJECT = "Thing"
#: `plan` asks nothing of it: `README.md` stays in the root, `specs/` and
#: `src/` classify themselves.
TREE = {"README.md": "# Thing\n", "specs/001/spec.md": "# s\n",
        "src/main.py": "x = 1\n"}
#: The same without `specs/`, so `execute --allow-empty-leg spec` SEEDS the
#: spec leg and extracts the code leg, and says both lines.
NO_SPECS = {"README.md": "# Thing\n", "src/main.py": "x = 1\n"}
SPLIT_BRANCH = "adopt/three-repo-shape"
#: What a child's stdout is given: a byte that is not UTF-8 is written as
#: itself, which is what main did to the typed path.
ENCODING = "utf-8:surrogateescape"

#: Each character a terminal does not show as itself, and how `_shown` writes
#: it: the escape `repo_shape.double_quoted` writes for it in the plan. Then
#: the control, a path with none of them.
CHARACTERS = [
    pytest.param("\u202e", "\\u202e", id="bidi-override-U+202E"),
    pytest.param("\x1b", "\\x1b", id="escape"),
    pytest.param("\n", "\\n", id="line-feed"),
    pytest.param("\udcff", "\\udcff", id="byte-0xff-not-utf-8"),
    pytest.param("", "", id="plain-control"),
]


@pytest.fixture(scope="module")
def adopter():
    """`adopt-project.py` loaded as a module: `_create_leg_remote` has no
    command line."""
    module_spec = importlib.util.spec_from_file_location(
        "adopt_plan_and_remote_paths_spelled", ADOPT)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def skip_where_cannot_carry(typed: str, tmp_path: Path) -> None:
    """Skip where this system cannot make a file name holding `typed`."""
    skip_where_the_environment_cannot_carry(typed)
    if "\udc80" <= typed[:1] <= "\udcff":
        skip_where_a_name_cannot_be_not_utf_8(tmp_path)


def run_adopt(*args: str, cwd: Path | None = None,
              over: dict | None = None) -> tuple[int, str, str]:
    """`(exit, stdout, stderr)` of one run of the tool, as text a byte that is
    not UTF-8 survives in (`surrogateescape`): the child's stdout is given
    `ENCODING`, so a path it prints raw reaches this process as the bytes it
    held. `cwd` is where it runs, for a relative `--plan`, and `over` names
    variables set over its environment."""
    env = blank_unnamed_pin_sources(
        {**os.environ, "LANES_LANE": "", "PYTHONIOENCODING": ENCODING,
         **(over or {})}, {})
    for key, value in (("GIT_AUTHOR_NAME", IDENTITY_NAME),
                       ("GIT_AUTHOR_EMAIL", IDENTITY_EMAIL),
                       ("GIT_COMMITTER_NAME", IDENTITY_NAME),
                       ("GIT_COMMITTER_EMAIL", IDENTITY_EMAIL)):
        env.setdefault(key, value)
    proc = subprocess.run([sys.executable, str(ADOPT), *args],
                          capture_output=True, env=env, cwd=cwd,
                          stdin=subprocess.DEVNULL, check=False)
    return (proc.returncode,
            proc.stdout.decode("utf-8", "surrogateescape"),
            proc.stderr.decode("utf-8", "surrogateescape"))


class Planned(NamedTuple):
    """A source on disk and the plan `plan` wrote for it, as text."""
    source: Path
    text: str


def a_source_and_its_plan(base: Path, tree: dict | None = None) -> Planned:
    """`tree` committed once in `base/Thing`, and `plan` over it into
    `base/plan.yaml` (project `Thing`, `org: testorg`), read back."""
    source = make_source_repo(base / PROJECT, tree=tree or TREE, edits=())
    out = base / "plan.yaml"
    written = write_plan(source, out, project=PROJECT, org=ORG)
    assert written.returncode == 0, written.stdout + written.stderr
    return Planned(source, out.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def plain(tmp_path_factory) -> Planned:
    """A source with no remote of its own: `org:` and `legs.assembly` can be
    edited without the plan then naming another repository."""
    return a_source_and_its_plan(tmp_path_factory.mktemp("plain"))


@pytest.fixture(scope="module")
def github(tmp_path_factory) -> Planned:
    """A source whose `origin` is `testorg/Thing` on GitHub, set after `plan`
    (a plan reads nothing from it): a plan that names another repository is
    `plan-not-the-source`. The url is never fetched."""
    planned = a_source_and_its_plan(tmp_path_factory.mktemp("github"))
    git("remote", "add", "origin", f"https://github.com/{ORG}/{PROJECT}.git",
        cwd=planned.source)
    return planned


@pytest.fixture(scope="module")
def taken(tmp_path_factory) -> Planned:
    """A source that holds a branch `adopt`, which git cannot hold beside the
    split branch `adopt/three-repo-shape` (`plan-split-branch-taken`)."""
    planned = a_source_and_its_plan(tmp_path_factory.mktemp("taken"))
    git("branch", "adopt", cwd=planned.source)
    return planned


# --- the plans, edited ------------------------------------------------------

LEGS = ("legs:\n  assembly: Thing\n  spec: Thing-spec\n  code: Thing-code\n"
        "  spec_path: spec\n  code_path: code\n")


def replaced(text: str, old: str, new: str) -> str:
    """`text` with the one `old` in it replaced, which it must hold once."""
    assert text.count(old) == 1, (old, text)
    return text.replace(old, new)


def without_the_code_entry(text: str, source: Path) -> str:
    """`text` with the entry for `src/` taken out: `src/main.py` is then in
    the source and in no entry (`plan-uncovered`)."""
    lines = text.split("\n")
    start = lines.index("  - path: src/")
    end = start + 1
    while end < len(lines) and lines[end].startswith("    "):
        end += 1
    return "\n".join(lines[:start] + lines[end:])


EDITS: dict[str, Callable[[str, Path], str]] = {
    "mistyped": lambda text, source: replaced(text, LEGS, "legs: 5\n"),
    "uncovered": without_the_code_entry,
    "unchanged": lambda text, source: text,
    "wrong-kind": lambda text, source: replaced(
        text, "kind: adoption-plan\n", "kind: something-else\n"),
    "placement-kind": lambda text, source: replaced(
        text, "kind: adoption-plan\n", "kind: placement-plan\n"),
    "new-root": lambda text, source: replaced(
        text, "mode: in-place\n", "mode: new-root\n"),
    "a-list": lambda text, source: "- legs\n- paths\n",
    "no-source": lambda text, source: replaced(
        text, f'local_path: "{source}"\n', "local_path: null\n"),
    "spaced-id": lambda text, source: replaced(
        text, "id: thing\n", 'id: "North Wind"\n'),
    "numbered-id": lambda text, source: replaced(
        text, "id: thing\n", "id: 007\n"),
    "derived-id": lambda text, source: replaced(
        replaced(text, "id: thing\n", ""),
        "assembly: Thing\n", "assembly: North_Wind\n"),
    "device-name": lambda text, source: replaced(
        text, "assembly: Thing\n", "assembly: NUL\n"),
    "double-hyphen-org": lambda text, source: replaced(
        text, "org: testorg\n", "org: a--b\n"),
    "long-org": lambda text, source: replaced(
        text, "org: testorg\n", f"org: {'o' * 40}\n"),
    "long-id": lambda text, source: replaced(
        text, "id: thing\n", f"id: {'a' * 40}\n"),
    "another-repository": lambda text, source: replaced(
        text, "assembly: Thing\n", "assembly: Other\n"),
}

#: How a refusal or a finding reads its path: `how` is `=` for a line that is
#: exactly `text`, `^` for one that begins with it.
Line = tuple[str, str]


def is_line(text: str) -> Line:
    return "=", text


def begins(text: str) -> Line:
    return "^", text


class Row(NamedTuple):
    """One refusal family: the source it runs over, how the plan is edited,
    whether `execute` runs under `--local-remote-dir` (GitHub's own rows are
    refused before anything is asked of `gh`), and for each command that
    reaches it the exit and the lines it says, from the path as `_shown`
    writes it."""
    name: str
    source: str
    edit: str
    local: bool
    says: dict[str, tuple[int, Callable[[str], list[Line]]]]


def in_a_finding(shown: str) -> list[Line]:
    return [is_line(f"1 finding(s) in {shown}")]


def refused_as_check_prints(code: str) -> Callable[[str], list[Line]]:
    return lambda shown: [is_line(
        f"REFUSED {code}: 1 finding(s) in {shown}, as `check` prints them:")]


def a_refusal_naming_the_plan(code: str, then: str
                              ) -> Callable[[str], list[Line]]:
    """`REFUSED code: <path>: then ...` and no other line."""
    return lambda shown: [begins(f"REFUSED {code}: {shown}: {then}")]


def a_finding_naming_the_plan(code: str, then: str
                              ) -> Callable[[str], list[Line]]:
    """`FINDING code: <path>: then ...`, and the line that counts them."""
    return lambda shown: [begins(f"FINDING {code}: {shown}: {then}"),
                          *in_a_finding(shown)]


ID_PATTERN = "^[a-z0-9][a-z0-9-]*$"
KIND = "kind is 'something-else', expected 'adoption-plan'"
PLACEMENT_KIND = "kind is 'placement-plan', expected 'adoption-plan'"
MODE = "mode is 'new-root'; v0.2 implements `in-place` only"
NO_SOURCE = "`source:` names neither a local path nor a repository"
#: `org:` one character past GitHub's 39, cut in the middle as a refusal
#: cuts a long name.
LONG_ORG = "`org:` is oooooooooooo...oooooooooooo, 40 characters"
ROWS = [
    Row("mistyped-plan", "plain", "mistyped", False, {
        "check": (1, in_a_finding),
        "execute": (2, refused_as_check_prints("plan-bad-legs"))}),
    Row("uncovered-plan", "plain", "uncovered", True, {
        "check": (1, in_a_finding),
        "execute": (2, refused_as_check_prints("plan-uncovered"))}),
    Row("split-branch-taken", "taken", "unchanged", True, {
        "check": (1, in_a_finding),
        "execute": (2, lambda shown: [is_line(
            f"REFUSED plan-split-branch-taken: 1 finding(s) in {shown}:")])}),
    Row("plan-wrong-kind", "plain", "wrong-kind", False, {
        "check": (2, a_refusal_naming_the_plan("plan-wrong-kind", KIND)),
        "execute": (2, a_refusal_naming_the_plan("plan-wrong-kind", KIND))}),
    # A PLACEMENT plan is refused with a remediation of its own, after the
    # same detail (#1195).
    Row("plan-wrong-kind-a-placement-plan", "plain", "placement-kind", False, {
        "check": (2, a_refusal_naming_the_plan("plan-wrong-kind",
                                               PLACEMENT_KIND)),
        "execute": (2, a_refusal_naming_the_plan("plan-wrong-kind",
                                                 PLACEMENT_KIND))}),
    Row("plan-unsupported-mode", "plain", "new-root", False, {
        "check": (2, a_refusal_naming_the_plan("plan-unsupported-mode", MODE)),
        "execute": (2, a_refusal_naming_the_plan("plan-unsupported-mode",
                                                 MODE))}),
    Row("plan-unreadable", "plain", "a-list", False, {
        "check": (2, a_refusal_naming_the_plan("plan-unreadable",
                                               "not a mapping")),
        "execute": (2, a_refusal_naming_the_plan("plan-unreadable",
                                                 "not a mapping"))}),
    Row("plan-no-source", "plain", "no-source", False, {
        "check": (2, a_refusal_naming_the_plan("plan-no-source", NO_SOURCE)),
        "execute": (2, a_refusal_naming_the_plan("plan-no-source",
                                                 NO_SOURCE))}),
    Row("plan-bad-id-with-a-space", "plain", "spaced-id", False, {
        "check": (2, a_refusal_naming_the_plan(
            "plan-bad-id", f"`id:` is 'North Wind' and must match "
                           f"{ID_PATTERN}")),
        "execute": (2, a_refusal_naming_the_plan(
            "plan-bad-id", f"`id:` is 'North Wind' and must match "
                           f"{ID_PATTERN}"))}),
    Row("plan-bad-id-a-number", "plain", "numbered-id", False, {
        "check": (2, a_refusal_naming_the_plan(
            "plan-bad-id", "`id:` was read out of the plan as the number 7")),
        "execute": (2, a_refusal_naming_the_plan(
            "plan-bad-id",
            "`id:` was read out of the plan as the number 7"))}),
    # `execute` meets `naming-unclassified` before it asks the derived id.
    Row("plan-bad-id-derived", "plain", "derived-id", False, {
        "check": (2, a_refusal_naming_the_plan(
            "plan-bad-id", "id (not set in the plan, so legs.assembly "
                           "lowercased) is 'north_wind', which must match "
                           f"{ID_PATTERN}"))}),
    Row("assembly-a-windows-device-name", "plain", "device-name", False, {
        "check": (1, a_finding_naming_the_plan(
            "adopt-bad-project-name", "`legs.assembly` is 'NUL'")),
        "execute": (2, a_refusal_naming_the_plan(
            "adopt-bad-project-name", "`legs.assembly` is 'NUL'"))}),
    Row("org-with-two-hyphens", "plain", "double-hyphen-org", False, {
        "check": (1, a_finding_naming_the_plan(
            "adopt-bad-org", "`org:` is 'a--b'")),
        "execute": (2, a_refusal_naming_the_plan(
            "adopt-bad-org", "`org:` is 'a--b'"))}),
    # The other refusal of the same `org:` sentence, asked first (#1195).
    Row("org-too-long", "plain", "long-org", False, {
        "check": (1, a_finding_naming_the_plan("adopt-org-too-long",
                                               LONG_ORG)),
        "execute": (2, a_refusal_naming_the_plan("adopt-org-too-long",
                                                 LONG_ORG))}),
    Row("topic-too-long", "plain", "long-id", False, {
        "check": (1, a_finding_naming_the_plan(
            "adopt-topic-too-long", "`id:` is aaaaaaaaaaaa...aaaaaaaaaaaa, "
                                    "40 characters")),
        "execute": (2, a_refusal_naming_the_plan(
            "adopt-topic-too-long", "`id:` is aaaaaaaaaaaa...aaaaaaaaaaaa, "
                                    "40 characters"))}),
    Row("plan-not-the-source", "github", "another-repository", False, {
        "check": (1, in_a_finding),
        "execute": (2, a_refusal_naming_the_plan(
            "plan-not-the-source", "the plan's `org: testorg` with its "
                                   "`legs.assembly: Other` names "
                                   "testorg/Other"))}),
]
CASES = [pytest.param(row, command, id=f"{row.name}-{command}")
         for row in ROWS for command in row.says]


def where_the_plan_is(tmp_path: Path, typed: str, spelled: str
                      ) -> tuple[Path, str]:
    """`(the plan's path, how the tool names it)`: a plain path as it is, one
    that holds `typed` between backticks with `spelled` for it."""
    if not typed:
        path = tmp_path / "plan.yaml"
        return path, os.fspath(path)
    return (tmp_path / f"pl{typed}an.yaml",
            f"`{os.fspath(tmp_path)}/pl{spelled}an.yaml`")


def assert_the_lines(stream: str, wanted: list[Line]) -> None:
    lines = stream.split("\n")
    for how, text in wanted:
        found = (text in lines if how == "="
                 else any(line.startswith(text) for line in lines))
        assert found, f"no line {how} {text!r} in\n{stream}"


@pytest.mark.parametrize("typed, spelled", CHARACTERS)
@pytest.mark.parametrize("row, command", CASES)
def test_the_plan_is_named_as_a_path_is(request, tmp_path, row, command,
                                        typed, spelled):
    """On main every line below named `--plan` as it was typed: the control
    passes, and each unsafe path reached the terminal with its bidi override,
    its escape or its byte raw, or its line feed splitting the line. Now it
    is the one line `_shown` writes, between backticks."""
    skip_where_cannot_carry(typed, tmp_path)
    planned = request.getfixturevalue(row.source)
    path, shown = where_the_plan_is(tmp_path, typed, spelled)
    path.write_bytes(os.fsencode(EDITS[row.edit](planned.text,
                                                 planned.source)))
    arguments = [command, "--plan", str(path)]
    if command == "execute":
        arguments += ["--yes", "--work-dir", str(tmp_path / "work")]
    if row.local and command == "execute":
        arguments += ["--local-remote-dir", str(tmp_path / "remotes")]
    code, stdout, stderr = run_adopt(*arguments)
    exit_status, says = row.says[command]
    assert code == exit_status, stdout + stderr
    assert "Traceback" not in stderr, stderr
    assert_the_lines(stderr, says(shown))
    if typed not in ("", "\n"):
        assert typed not in stdout + stderr, stdout + stderr


#: A `--plan` whose every character is printable: `typed`, given whole
#: (`absolute`) or relative to the directory `check` runs in, and how `check`
#: names it, `{base}` standing for that directory. A name that ends in a
#: space, or begins and ends with a backtick, is spelled by #900's rules; any
#: other prints as it was typed, relative where it was, and `./` dropped as
#: `Path` drops it.
PRINTABLE_PLANS = [
    pytest.param("plan.yaml ", True, "`{base}/plan.yaml `",
                 id="ends-in-a-space"),
    pytest.param("`plan.yaml`", False, "`\\x60plan.yaml\\x60`",
                 id="relative-between-backticks"),
    pytest.param("plan.yaml", False, "plan.yaml", id="relative"),
    pytest.param("./plan.yaml", False, "plan.yaml", id="relative-from-dot"),
]


@pytest.mark.parametrize("typed, absolute, named", PRINTABLE_PLANS)
def test_a_printable_plan_is_named_as_typed_unless_900_spells_it(
        plain, tmp_path, typed, absolute, named):
    """The four characters above are not printable, and no row there asked
    of a name `str.isprintable` passes: one #900's two rules spell, or one
    given relative. So `check`'s count line could name `--plan` by
    `str.isprintable` alone, which printed the first two as they were
    typed, or as `plan.path.absolute()`, which printed the last two as
    `<D>/plan.yaml`, and every row passed (#1195, RV1177's K1 and K2)."""
    (tmp_path / typed).write_text(EDITS["uncovered"](plain.text, plain.source),
                                  encoding="utf-8")
    code, stdout, stderr = run_adopt(
        "check", "--plan", str(tmp_path / typed) if absolute else typed,
        cwd=tmp_path)
    assert code == 1, stdout + stderr
    assert "Traceback" not in stderr, stderr
    assert_the_lines(stderr,
                     in_a_finding(named.format(base=os.fspath(tmp_path))))


# --- `--local-remote-dir`: `bare`, the leg lines, `already exists`, `split` --

#: What each leg's line says before the url it ends with: an extracted leg's
#: (`_extract_leg`) and a seeded leg's (`_seed_leg`).
EXTRACTED = re.compile(r"  (?P<role>spec|code)\s+\d+ path\(s\) -> "
                       r"[0-9a-f]{12} \(\d+ commits kept\) -> (?P<url>.*)")
SEEDED = re.compile(r"  (?P<role>spec|code)\s+0 path\(s\) -> [0-9a-f]{12} "
                    r"\(SEEDED from [^)]*\) -> (?P<url>.*)")


def where_a_leg_is(tmp_path: Path, typed: str, spelled: str | None,
                   leaf: str) -> str:
    """How the tool names `<remote dir>/<leaf>`, the remote dir being
    `re<typed>mote` beside `tmp_path`'s resolved path, or a plain `remote`:
    as it is where `spelled` is None, `typed` being printable."""
    base = os.path.realpath(tmp_path)
    if not typed:
        return f"{base}/remote/{leaf}"
    if spelled is None:
        return f"{base}/re{typed}mote/{leaf}"
    return f"`{base}/re{spelled}mote/{leaf}`"


#: `CHARACTERS`, and a character outside ASCII that is printable, which
#: `_shown` prints as it is, with no backticks: `spelled` is None.
REMOTE_CHARACTERS = [
    *CHARACTERS,
    pytest.param("\u00e9", None, id="printable-U+00E9"),
]


@needs_filter_repo
@pytest.mark.parametrize("typed, spelled", REMOTE_CHARACTERS)
def test_a_remote_dir_is_named_in_the_bare_and_leg_lines_as_a_path_is(
        tmp_path, typed, spelled):
    """On main `bare  {path}` and each leg's `-> {url}` printed the typed
    `--local-remote-dir` as it was. The code leg is extracted and the spec
    leg is seeded (`--allow-empty-leg spec` over a source with no `specs/`),
    so `_extract_leg`'s line and `_seed_leg`'s are both said, once. A
    `re\\u00e9mote` prints as typed: with no row of it, the extracted leg's
    line could spell every url outside ASCII, and every row passed (#1195,
    RV1177's K6)."""
    skip_where_cannot_carry(typed, tmp_path)
    planned = a_source_and_its_plan(tmp_path / "src", NO_SPECS)
    plan = tmp_path / "plan.yaml"
    plan.write_text(planned.text, encoding="utf-8")
    remote = tmp_path / (f"re{typed}mote" if typed else "remote")
    code, stdout, stderr = run_adopt(
        "execute", "--plan", str(plan), "--yes", "--allow-empty-leg", "spec",
        "--local-remote-dir", str(remote), "--work-dir",
        str(tmp_path / "work"))
    assert code == 0, stdout + stderr
    spec = where_a_leg_is(tmp_path, typed, spelled, "Thing-spec.git")
    leg_code = where_a_leg_is(tmp_path, typed, spelled, "Thing-code.git")
    lines = stdout.split("\n")
    assert [line for line in lines if line.startswith("  bare  ")] == [
        f"  bare  {spec}", f"  bare  {leg_code}"], stdout
    extracted = {m["role"]: m["url"] for m in map(EXTRACTED.fullmatch, lines)
                 if m}
    seeded = {m["role"]: m["url"] for m in map(SEEDED.fullmatch, lines) if m}
    assert extracted == {"code": leg_code}, stdout
    assert seeded == {"spec": spec}, stdout
    if spelled and typed != "\n":
        assert typed not in stdout + stderr, stdout + stderr


#: A source directory `_shown` spells and `adopt-unwritable-value` lets
#: through: the parent holds U+200B or U+200F, or the source's own name ends
#: in a space. `noted`: whether `NEXT:` says its path holds a character a
#: terminal does not show as itself, which a trailing space is not.
SPLIT_SOURCES = [
    pytest.param("so\u200burce", "Thing", "so\\u200burce", "Thing", True,
                 id="zero-width-space"),
    pytest.param("so\u200furce", "Thing", "so\\u200furce", "Thing", True,
                 id="right-to-left-mark"),
    pytest.param("source", "Thing ", "source", "Thing ", False,
                 id="name-ends-in-a-space"),
    pytest.param("source", "Thing", "source", "Thing", False,
                 id="plain-control"),
]

#: What is said of such a path just before `NEXT:` and its clone command,
#: then the path as the `split` line names it (#1195).
UNSEEN = ("NOTE the path in the clone command below holds a character a "
          "terminal does not show as itself, so it can read as another path: "
          "it is ")


@needs_filter_repo
@pytest.mark.parametrize(
    "parent, name, spelled_parent, spelled_name, noted", SPLIT_SOURCES)
def test_the_split_line_names_the_source_as_a_path_is(
        tmp_path, parent, name, spelled_parent, spelled_name, noted):
    """Under `--local-remote-dir` the split is pushed to the source itself, so
    `split <commit> on <branch> -> {url}` names the source's path. On main it
    was printed as it was: a zero-width space invisible in it, and a trailing
    space that reads as nothing. `NEXT:` names the same path as a person types
    it, through `shlex.quote`, and is not respelled: a command to paste. So
    U+200B or U+200F reached the terminal raw there, inside the quotes, and
    the path read as `source/Thing`; a NOTE just before the block now says
    so and names it as the `split` line does (#1195, RV1177's N4). A
    trailing space shows between the quotes, and gets none."""
    skip_where_the_environment_cannot_carry(parent + name)
    base = tmp_path / parent
    source = make_source_repo(base / name, tree=TREE, edits=())
    plan = tmp_path / "plan.yaml"
    written = write_plan(source, plan, project=PROJECT, org=ORG)
    assert written.returncode == 0, written.stdout + written.stderr
    code, stdout, stderr = run_adopt(
        "execute", "--plan", str(plan), "--yes", "--local-remote-dir",
        str(tmp_path / "remote"), "--work-dir", str(tmp_path / "work"))
    assert code == 0, stdout + stderr
    where = f"{os.path.realpath(tmp_path)}/{parent}/{name}"
    named = (where if (parent, name) == ("source", "Thing") else
             f"`{os.path.realpath(tmp_path)}/{spelled_parent}/"
             f"{spelled_name}`")
    split = [line for line in stdout.split("\n")
             if line.startswith("  split ")]
    assert len(split) == 1, stdout
    assert re.fullmatch(
        rf"  split [0-9a-f]{{12}} on {SPLIT_BRANCH} -> {re.escape(named)}",
        split[0]), split
    assert (f"-b {SPLIT_BRANCH} {shlex.quote(where)}\n"
            in stdout), stdout
    said = [line for line in stdout.split("\n") if line.startswith(UNSEEN)]
    assert said == ([f"{UNSEEN}{named}, as the `split` line names it."]
                    if noted else []), stdout
    if noted:
        assert stdout.index(said[0]) < stdout.index("\nNEXT: "), stdout


@pytest.mark.parametrize("typed, spelled", CHARACTERS)
def test_a_leg_remote_already_there_is_named_as_a_path_is(
        adopter, tmp_path, typed, spelled):
    """`{bare} already exists`, which `_create_leg_remote` refuses when a leg
    appeared since `_refuse_what_stands_in_the_legs_way` asked (#798), so a
    child cannot reach it: it is called in this process with a directory that
    is already there. On main the refusal named it as it was typed."""
    skip_where_cannot_carry(typed, tmp_path)
    remote = tmp_path / (f"re{typed}mote" if typed else "remote")
    leg = remote / "Thing-spec.git"
    leg.mkdir(parents=True)
    with pytest.raises(adopter.Refusal) as caught:
        adopter._create_leg_remote(None, {}, {}, {"spec": str(leg)}, "main",
                                   True, "spec")
    assert caught.value.code == adopter.LEG_REMOTE_EXISTS
    shown = (os.fspath(leg) if not typed else
             f"`{os.fspath(tmp_path)}/re{spelled}mote/Thing-spec.git`")
    assert caught.value.detail == f"{shown} already exists"


# --- a refused command: `CommandFailed.loudly` (#1195) ----------------------

#: What the `pre-receive` hook says as it refuses a push.
HOOK_SAYS = "this remote takes no push"

#: The characters a refused command named raw, and the control. A line feed
#: is left out: git's own output names the remote with it, and the line
#: breaks in what a command printed are kept as line breaks.
REFUSED_CHARACTERS = [param for param in CHARACTERS
                      if param.id != "line-feed"]


def a_global_config_whose_hook_refuses_every_push(tmp_path: Path) -> Path:
    """A global git config holding the session's (`conftest`'s
    `no_auto_maintenance` writes it) and a `core.hooksPath` whose
    `pre-receive` hook refuses every push. Given as `GIT_CONFIG_GLOBAL`, it
    reaches the `receive-pack` a push to a local path starts, so the first
    leg push of an `execute` is refused, after both legs exist."""
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    hook = hooks / "pre-receive"
    hook.write_text(f"#!/bin/sh\necho '{HOOK_SAYS}' >&2\nexit 1\n",
                    encoding="utf-8", newline="\n")
    hook.chmod(0o755)
    session = os.environ["GIT_CONFIG_GLOBAL"]
    config = tmp_path / "gitconfig"
    config.write_text(f'[include]\n\tpath = "{session}"\n'
                      f'[core]\n\thooksPath = "{hooks}"\n', encoding="utf-8")
    return config


@needs_filter_repo
@pytest.mark.parametrize("typed, spelled", REFUSED_CHARACTERS)
def test_a_refused_command_names_the_remote_and_work_dirs_spelled(
        tmp_path, typed, spelled):
    """A refused leg push is said by `CommandFailed.loudly`: the command, the
    directory it ran in, and what it printed. Each was printed as it was, so
    under `--local-remote-dir <D>/re<U+202E>mote` the override reached the
    terminal three times, in the command and in git's own `To` and `error:`
    lines, where the `bare` lines above and the notice below spell it
    (#1195, RV1177's N3). Now each is spelled as `_first_said` spells gh's,
    with no backticks, and what it printed keeps its line breaks. The work
    directory holds the character too, for the `(in ...)` line. A byte that
    is not UTF-8 printed as `\\udcff` before as well, since stderr is
    `backslashreplace`; git's own lines hold U+FFFD for it, as `run`
    decodes what a command printed."""
    skip_where_cannot_carry(typed, tmp_path)
    planned = a_source_and_its_plan(tmp_path / "src", NO_SPECS)
    plan = tmp_path / "plan.yaml"
    plan.write_text(planned.text, encoding="utf-8")
    config = a_global_config_whose_hook_refuses_every_push(tmp_path)
    code, stdout, stderr = run_adopt(
        "execute", "--plan", str(plan), "--yes", "--allow-empty-leg", "spec",
        "--local-remote-dir", str(tmp_path / f"re{typed}mote"),
        "--work-dir", str(tmp_path / f"wo{typed}rk"),
        over={"GIT_CONFIG_GLOBAL": str(config)})
    assert code == 2, stdout + stderr
    assert "Traceback" not in stderr, stderr
    base = os.path.realpath(tmp_path)
    lines = stderr.split("\n")
    start = lines.index(
        "REFUSED pushing the seeded spec leg. THE EXACT COMMAND WAS:")
    assert lines[start + 1:start + 5] == [
        f"    git push -q {base}/re{spelled}mote/Thing-spec.git "
        "HEAD:refs/heads/main",
        f"    (in {base}/wo{spelled}rk/Thing-spec)",
        "    exit 1",
        "--- output ---"], stderr
    said = lines[start + 5:lines.index("--- end output ---", start)]
    assert f"remote: {HOOK_SAYS}" in [line.rstrip() for line in said], stderr
    if typed:
        assert typed not in stdout + stderr, stdout + stderr


def a_refused_push(adopter, typed: str):
    """A `CommandFailed` as a refused split push raises it, `typed` in the
    remote it was pushed to, the directory it ran in and what git said."""
    return adopter.CommandFailed(
        ["git", "push", "-q", f"/remotes/re{typed}mote/Thing.git",
         SPLIT_BRANCH], f"/work/wo{typed}rk/Thing", 1,
        f"To /remotes/re{typed}mote/Thing.git\n"
        " ! [remote rejected] (pre-receive hook declined)\n")


def the_block_of(step: str, typed: str, spelled: str) -> str:
    """The REFUSED block `a_refused_push` is said in: the command and the
    directory with `typed` spelled, and what git said with it spelled too,
    but a line feed kept as the line break it is there."""
    said = typed if typed == "\n" else spelled
    return (f"REFUSED {step}. THE EXACT COMMAND WAS:\n"
            f"    git push -q /remotes/re{spelled}mote/Thing.git "
            f"{SPLIT_BRANCH}\n"
            f"    (in /work/wo{spelled}rk/Thing)\n"
            "    exit 1\n"
            "--- output ---\n"
            f"To /remotes/re{said}mote/Thing.git\n"
            " ! [remote rejected] (pre-receive hook declined)\n"
            "--- end output ---")


@pytest.mark.parametrize("typed, spelled", CHARACTERS)
def test_a_late_refused_command_is_said_spelled(adopter, typed, spelled):
    """`_failed_loudly`, which says a command refused after both legs exist
    (a split push, the pull request, the topic), says it as the leg push's
    block is said, through `_loudly` (#1195)."""
    assert adopter._failed_loudly(
        "pushing the split", a_refused_push(adopter, typed)) == \
        the_block_of("pushing the split", typed, spelled)


@pytest.mark.parametrize("typed, spelled", CHARACTERS)
def test_a_refused_command_no_step_said_is_said_spelled(
        adopter, monkeypatch, capsys, tmp_path, typed, spelled):
    """A refused command no step has said reaches `main`, which says it as
    "a git or gh command failed", through `_loudly` as well (#1195)."""
    def refused(_args):
        raise a_refused_push(adopter, typed)

    monkeypatch.setattr(adopter, "cmd_check", refused)
    assert adopter.main(["check", "--plan", str(tmp_path / "plan.yaml")]) == 2
    assert capsys.readouterr().err == the_block_of(
        "a git or gh command failed", typed, spelled) + "\n"
