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


def run_adopt(*args: str) -> tuple[int, str, str]:
    """`(exit, stdout, stderr)` of one run of the tool, as text a byte that is
    not UTF-8 survives in (`surrogateescape`): the child's stdout is given
    `ENCODING`, so a path it prints raw reaches this process as the bytes it
    held."""
    env = blank_unnamed_pin_sources(
        {**os.environ, "LANES_LANE": "", "PYTHONIOENCODING": ENCODING}, {})
    for key, value in (("GIT_AUTHOR_NAME", IDENTITY_NAME),
                       ("GIT_AUTHOR_EMAIL", IDENTITY_EMAIL),
                       ("GIT_COMMITTER_NAME", IDENTITY_NAME),
                       ("GIT_COMMITTER_EMAIL", IDENTITY_EMAIL)):
        env.setdefault(key, value)
    proc = subprocess.run([sys.executable, str(ADOPT), *args],
                          capture_output=True, env=env,
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
MODE = "mode is 'new-root'; v0.2 implements `in-place` only"
NO_SOURCE = "`source:` names neither a local path nor a repository"
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


# --- `--local-remote-dir`: `bare`, the leg lines, `already exists`, `split` --

#: What each leg's line says before the url it ends with: an extracted leg's
#: (`_extract_leg`) and a seeded leg's (`_seed_leg`).
EXTRACTED = re.compile(r"  (?P<role>spec|code)\s+\d+ path\(s\) -> "
                       r"[0-9a-f]{12} \(\d+ commits kept\) -> (?P<url>.*)")
SEEDED = re.compile(r"  (?P<role>spec|code)\s+0 path\(s\) -> [0-9a-f]{12} "
                    r"\(SEEDED from [^)]*\) -> (?P<url>.*)")


def where_a_leg_is(tmp_path: Path, typed: str, spelled: str, leaf: str
                   ) -> str:
    """How the tool names `<remote dir>/<leaf>`, the remote dir being
    `re<typed>mote` beside `tmp_path`'s resolved path, or a plain `remote`."""
    base = os.path.realpath(tmp_path)
    if not typed:
        return f"{base}/remote/{leaf}"
    return f"`{base}/re{spelled}mote/{leaf}`"


@needs_filter_repo
@pytest.mark.parametrize("typed, spelled", CHARACTERS)
def test_a_remote_dir_is_named_in_the_bare_and_leg_lines_as_a_path_is(
        tmp_path, typed, spelled):
    """On main `bare  {path}` and each leg's `-> {url}` printed the typed
    `--local-remote-dir` as it was. The code leg is extracted and the spec
    leg is seeded (`--allow-empty-leg spec` over a source with no `specs/`),
    so `_extract_leg`'s line and `_seed_leg`'s are both said, once."""
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
    if typed not in ("", "\n"):
        assert typed not in stdout + stderr, stdout + stderr


#: A source directory `_shown` spells and `adopt-unwritable-value` lets
#: through: the parent holds U+200B, or the source's own name ends in a space.
SPLIT_SOURCES = [
    pytest.param("so\u200burce", "Thing", "so\\u200burce", "Thing",
                 id="zero-width-space"),
    pytest.param("source", "Thing ", "source", "Thing ",
                 id="name-ends-in-a-space"),
    pytest.param("source", "Thing", "source", "Thing", id="plain-control"),
]


@needs_filter_repo
@pytest.mark.parametrize("parent, name, spelled_parent, spelled_name",
                         SPLIT_SOURCES)
def test_the_split_line_names_the_source_as_a_path_is(
        tmp_path, parent, name, spelled_parent, spelled_name):
    """Under `--local-remote-dir` the split is pushed to the source itself, so
    `split <commit> on <branch> -> {url}` names the source's path. On main it
    was printed as it was: a zero-width space invisible in it, and a trailing
    space that reads as nothing. `NEXT:` names the same path as a person types
    it, through `shlex.quote`, and is not respelled."""
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
