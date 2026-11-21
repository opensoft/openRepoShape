# SPDX-License-Identifier: Apache-2.0
"""Five places in `update-shape.py` that only name the root, or a path the
person typed, name it as `shown_path` names it (#1318).

#1288 spelled `update-pin-missing` and `update-pin-commit`, and #1310 the four
refusals of `check_pin` it read. These still printed a typed `--root` (or
`--upstream`) as it was typed: a bidi override, U+202E, in a folder's name
reordered the line, an ESC reached the terminal as the control it is, and a
line feed began a line of the path's choosing. Each is spelled now:

- `check`'s `root        <root>` header, on stdout (`report`);
- `update-root-missing`, `<root> is not a directory` (`prepare`);
- `update-branch-not-utf8`'s `REFUSED` text, `<root> is on the branch ...`
  (`current_branch`);
- `update-upstream-not-a-repo` for a typed `--upstream`, `--upstream <path>
  exists but is not a git repository` (`open_upstream`);
- `pin_source`'s `named`, which the pin's `source_repository:` refusals share:
  `update-upstream-not-a-repo`, `update-upstream-unresolvable` and, through
  `checked_value`, which is handed `named` as its `what`, `unsafe-value`.

A printable path is named byte for byte as it always was. The refusal codes
and every word but the path are as they were: each row holds the whole line.

WHAT IS NOT HERE. A line a person pastes still names the root as typed, in
shell quotes: `update-branch-not-utf8`'s own remedy, `check`'s NEXT line, and
the rest that #1318's Scope paragraph calls a decision to make, not a given
(#766 left such lines raw on purpose). So a row over `check` reads the header
and the report above the NEXT line, and a row over `update-branch-not-utf8`
reads the detail above its remedy, which is its `REFUSED` line alone, where
the remedy under it still holds the root as typed.

NO NETWORK AND NO GITHUB: temporary files, local repositories, and the
session's `gh` guard first on PATH for every tool run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, NamedTuple

import pytest

from conftest import (
    NOT_UTF_8_BRANCH_NAMED, assert_shown_safe, copied_under, named_as,
    on_a_branch_that_is_not_utf_8, refusal_detail, run_script, unsafe_folder,
)
from test_load_yaml_refusals import NAMES, refused_lines
from test_update_shape import UPDATE, upstream_and_project  # noqa: F401

SHAPE_PIN = "contracts/shape-pin.yaml"
#: The pin's line as the scaffold writes it; a row rewrites it by hand.
SCAFFOLDED = "source_repository: opensoft/openRepoShape\n"
BRANCH = "shape/update-1318"
#: What `update-branch-not-utf8` says after the root and the branch's bytes.
NOT_UTF_8_SAID = (
    ", whose name is not UTF-8, so no line this tool prints can name it: a "
    "line that named it would name a branch that is not there. Nothing was "
    "written.")


def project_under(standard: dict, tmp_path: Path, name: str) -> Path:
    """A private copy of the project as it was cut at A, in a folder `name`
    (`copied_under`), at the path `prepare` resolves it to."""
    return copied_under(standard["clone"], tmp_path, name)


def run(*args: str, cwd: Path):
    """`update-shape.py <args>`, from `cwd` (a folder that holds nothing a
    pin's `source_repository:` could name)."""
    return run_script(UPDATE, *args, cwd=cwd)


def assert_refused_as(result, code: str, line: str) -> None:
    """Exit 2, no traceback, no U+202E, ESC or forged line on either stream,
    and exactly one `REFUSED` line, `line`, as `REFUSED <code>: <line>`."""
    output = result.stdout + result.stderr
    assert result.returncode == 2, ascii(output)
    assert "Traceback" not in output, ascii(output)
    assert refused_lines(result.stderr) == [f"REFUSED {code}: {line}"], (
        ascii(output))
    assert chr(0x202E) not in output, ascii(output)
    assert_shown_safe(result.stdout, result.stderr)


@pytest.mark.parametrize("name", NAMES)
def test_check_names_the_root_in_its_header_as_shown_path_names_it(
        upstream_and_project, tmp_path, name):
    """`check`'s header over a root whose folder holds U+202E, an ESC or a
    line feed: the root as `repr` spells it, so the header is one line and
    nothing of the name reaches stdout raw. At #1310's head it printed it
    raw. The printable row is the control, named byte for byte as before,
    with no quotes. Exit 1, as before: the root is one commit behind."""
    standard = upstream_and_project
    root = project_under(standard, tmp_path, name)

    result = run("check", "--root", str(root), "--upstream",
                 str(standard["upstream"]), "--at", standard["b"],
                 cwd=tmp_path)

    assert result.returncode == 1, ascii(result.stdout + result.stderr)
    assert "\nNEXT  " in result.stdout, ascii(result.stdout)
    # The NEXT line is pasted, and names the root as typed (#1318's Scope).
    report = result.stdout.split("\nNEXT  ", 1)[0]
    assert report.splitlines()[0] == f"root        {named_as(root, name)}", (
        ascii(report))
    assert chr(0x202E) not in report, ascii(report)
    assert_shown_safe(report, result.stderr)
    assert result.stderr == ""


@pytest.mark.parametrize("name", NAMES)
def test_a_root_that_is_not_there_is_named_as_shown_path_names_it(
        tmp_path, name):
    """`update-root-missing` over a root that is not there, under a folder
    whose name holds U+202E, an ESC or a line feed."""
    root = unsafe_folder(tmp_path, name).resolve() / "gone"

    result = run("check", "--root", str(root), cwd=tmp_path)

    assert_refused_as(result, "update-root-missing",
                      f"{named_as(root, name)} is not a directory")


@pytest.mark.parametrize("name", NAMES)
def test_a_root_on_a_branch_that_is_not_utf8_is_named_as_shown_path_names_it(
        upstream_and_project, tmp_path, name):
    """`update-branch-not-utf8`'s `REFUSED` line over a root whose folder
    holds U+202E, an ESC or a line feed, with HEAD on `caf<0xE9>`. Exit 2
    before the first write, as before. The detail above the remedy is ONE
    line, the `REFUSED` line (`refusal_detail`): a second line that named the
    root raw would be a line the path chose (rv1329's X2). The remedy under
    it is a line a person pastes and names the root as typed, in shell
    quotes, so nothing is asserted about it (#1318's Scope paragraph)."""
    standard = upstream_and_project
    root = project_under(standard, tmp_path, name)
    on_a_branch_that_is_not_utf_8(root)

    result = run("apply", "--root", str(root), "--yes", "--upstream",
                 str(standard["upstream"]), "--at", standard["b"],
                 "--branch", BRANCH, cwd=tmp_path)

    detail = refusal_detail(result.stderr, "update-branch-not-utf8")
    assert result.returncode == 2, ascii(result.stdout + result.stderr)
    assert result.stdout == "", ascii(result.stdout)
    assert detail == [
        f"REFUSED update-branch-not-utf8: {named_as(root, name)} is on the "
        f"branch {NOT_UTF_8_BRANCH_NAMED}{NOT_UTF_8_SAID}"], ascii(detail)
    assert chr(0x202E) not in "".join(detail), ascii(detail)
    assert_shown_safe(*detail)


@pytest.mark.parametrize("name", NAMES)
def test_a_typed_upstream_that_is_no_repository_is_named_as_shown_path_does(
        upstream_and_project, tmp_path, name):
    """`update-upstream-not-a-repo` for a `--upstream` that is an existing
    folder with no `.git` and no `HEAD`: the flag's value, spelled as typed
    where it prints and as `repr` spells it where it does not. The root is a
    plain project folder: it is the `--upstream` that holds the name."""
    standard = upstream_and_project
    root = project_under(standard, tmp_path, "root")
    folder = unsafe_folder(tmp_path, name)

    result = run("check", "--root", str(root), "--upstream", str(folder),
                 cwd=tmp_path)

    assert_refused_as(
        result, "update-upstream-not-a-repo",
        f"--upstream {named_as(folder, name)} exists but is not a git "
        "repository")


@pytest.mark.parametrize("name", NAMES)
def test_a_relative_upstream_is_named_as_it_was_typed_and_spelled(
        upstream_and_project, tmp_path, name):
    """`update-upstream-not-a-repo` for a `--upstream` TYPED RELATIVE,
    `./<name>`, run from the folder that holds it: the line names the flag's
    value as typed, `./` and all, spelled as `shown_path` spells it, and not
    the absolute path `open_upstream` resolves it to (rv1329's X1). The row
    above types an absolute, resolved path, which both spellings give alike,
    so it cannot tell the two apart; here they differ."""
    standard = upstream_and_project
    root = project_under(standard, tmp_path, "root")
    unsafe_folder(tmp_path, name)
    typed = f"./{name}"

    result = run("check", "--root", str(root), "--upstream", typed,
                 cwd=tmp_path)

    assert_refused_as(
        result, "update-upstream-not-a-repo",
        f"--upstream {named_as(typed, name)} exists but is not a git "
        "repository")


class Source(NamedTuple):
    """A refusal of the pin's `source_repository:`: its code, the value the
    pin holds (given a scratch folder to name where it must exist), and
    what the refusal says after `source_repository:` is."""
    code: str
    value: Callable[[Path], str]
    after: Callable[[str], str]


def a_folder_that_is_no_repository(scratch: Path) -> str:
    """An existing folder with no `.git` and no `HEAD`, by its path."""
    folder = scratch / "norepo"
    folder.mkdir()
    return str(folder)


#: One refusal of each of `pin_source`'s three codes, by an id that names it.
SOURCES = {
    "update-upstream-not-a-repo": Source(
        "update-upstream-not-a-repo", a_folder_that_is_no_repository,
        lambda value: f"{value!r}, which exists but is not a git repository"),
    "update-upstream-unresolvable": Source(
        "update-upstream-unresolvable", lambda _scratch: "no-such-shape",
        lambda value: f"{value!r}, which is not an `owner/repo` name"),
    "unsafe-value": Source(
        "unsafe-value", lambda _scratch: "-a/b",
        lambda value: f"{value!r}, which is not a value this tool will put "
                      "on a `git` or `gh` command line"),
}


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("code", sorted(SOURCES))
def test_the_pin_is_named_as_shown_path_names_it_in_each_source_refusal(
        upstream_and_project, tmp_path, code, name):
    """THE THREE REFUSALS OF THE PIN'S `source_repository:`, one real run
    each, over a root whose folder holds U+202E, an ESC or a line feed:
    `named` spells the pin's path once, so `update-upstream-not-a-repo`,
    `update-upstream-unresolvable` and `unsafe-value` (which is
    `checked_value`'s, handed `named` as its `what`) all name it spelled.
    The value the pin holds is named as it was, as `repr` spells it."""
    standard = upstream_and_project
    source = SOURCES[code]
    root = project_under(standard, tmp_path, name)
    value = source.value(tmp_path)
    pin = root / SHAPE_PIN
    text = pin.read_text(encoding="utf-8")
    assert SCAFFOLDED in text, text
    pin.write_text(text.replace(
        SCAFFOLDED, f'source_repository: "{value}"\n'), encoding="utf-8")

    result = run("check", "--root", str(root), cwd=tmp_path)

    assert_refused_as(
        result, source.code,
        f"{named_as(pin, name)}: `source_repository:` is "
        f"{source.after(value)}")
