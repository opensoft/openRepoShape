# SPDX-License-Identifier: Apache-2.0
"""The three `family-members-unreadable` refusals of a holder's own scripts
name `family.yaml` as the script's `_shown` names it (#1317, its second part).

#1310 gave a holder's `bootstrap.py` and `validate-family.py` a `_shown` of
their own (a path as it is, or as `repr` spells it where a character in it is
not printable: `repo_shape.shown_path`, which a holder's library may predate)
and spelled the refusals around these. The three lines beside them still
named the holder raw, so that a bidi override, U+202E, in a `--root`'s name
reordered the line, an ESC reached the terminal as the control it is, and a
line feed began a line of the path's choosing:

- `bootstrap.py`, `members_of`: a `members:` that is not a list (`members:
  5`) and an entry that is not a mapping (`members: [5]`). The holder's
  `siblings.py` imports `members_of`, so it reaches both too, and a row runs
  that;
- `validate-family.py`, `_run_checks`: a `members:` that is not a list. An
  entry that is not a mapping is a finding of its own there (`member-row`),
  not a refusal.

Each is spelled now, by the file's own `_shown`, and a printable holder is
named byte for byte as it always was. No word of any refusal changes, and
neither does any code.

NOT IN THIS PART, and left as it was: the lines a person pastes
(`siblings-script-missing`'s remedy, `member-unknown`'s lines and the like),
which #1317 leaves as a decision (#766 left such lines raw on purpose).

NO NETWORK AND NO GITHUB: temporary files, local repositories, and the
session's `gh` guard first on PATH for every tool run.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, NamedTuple

import pytest

from conftest import (
    REPO, assert_shown_safe, named_as, run_script, unsafe_folder,
)
from test_load_yaml_refusals import LIBRARY, NAMES, older_library
from test_refusal_paths_shown_more import FAMILY_SCRIPTS, a_repository

MANIFEST = "family.yaml"
CODE = "family-members-unreadable"

#: A `family.yaml` of the right kind, to which a row adds its `members:`.
HEAD = "kind: family-manifest\nname: Acme\norg: acme\n"


class Tool(NamedTuple):
    """A holder's script: the copies a holder carries for it, what it is run
    with past `--root <holder>`, and whether it reads the naming policy
    first (without `contracts/repository-naming.yaml` the run is refused
    `yaml-unreadable` before it reaches `members:`)."""
    script: str
    copies: tuple
    rest: tuple
    policy: bool = False


TOOLS = {
    "bootstrap": Tool("bootstrap.py", ("bootstrap.py",), ("--no-fetch",)),
    "siblings": Tool("siblings.py", ("siblings.py", "bootstrap.py"),
                     ("--dry-run",)),
    "validate-family": Tool("validate-family.py", ("validate-family.py",), (),
                            policy=True),
}


def holder_run(tool: str, text: str) -> Callable:
    """`<holder>/scripts/<tool> --root <holder> <rest>`, over a holder
    `Acme` in a git repository carrying the tool's copies beside `library`,
    `family.yaml` holding `text`. It gives back `(the file the refusal names,
    the run's argv)`."""
    script, copies, rest, policy = TOOLS[tool]

    def build(folder: Path, library: bytes) -> tuple:
        root = a_repository(folder, "Acme",
                            tuple(FAMILY_SCRIPTS / name for name in copies),
                            library)
        (root / MANIFEST).write_bytes(text.encode("utf-8"))
        if policy:
            naming = root / "contracts" / "repository-naming.yaml"
            naming.parent.mkdir()
            naming.write_bytes(
                (REPO / "contracts" / "repository-naming.yaml").read_bytes())
        return root / MANIFEST, (root / "scripts" / script, "--root",
                                 str(root), *rest)
    return build


class Site(NamedTuple):
    """A refusal: how one run reaches it, and what it says after the path."""
    build: Callable
    after: str


#: What each refusal says after the path, in its own words.
NOT_A_LIST = ": `members:` is 5, expected a list"
NOT_A_MAPPING = ": a member is not a mapping: 5"

#: The issue's three lines, and the ways in: `bootstrap.py`'s two, the same
#: two through `siblings.py`'s import of `members_of`, and
#: `validate-family.py`'s one.
SITES = {
    "bootstrap-not-a-list": Site(
        holder_run("bootstrap", HEAD + "members: 5\n"), NOT_A_LIST),
    "bootstrap-entry": Site(
        holder_run("bootstrap", HEAD + "members: [5]\n"), NOT_A_MAPPING),
    "siblings-not-a-list": Site(
        holder_run("siblings", HEAD + "members: 5\n"), NOT_A_LIST),
    "siblings-entry": Site(
        holder_run("siblings", HEAD + "members: [5]\n"), NOT_A_MAPPING),
    "validate-family-not-a-list": Site(
        holder_run("validate-family", HEAD + "members: 5\n"), NOT_A_LIST),
}


def typed_relative(argv: tuple, cwd: Path) -> tuple:
    """`argv`, its `--root` value written relative to `cwd`."""
    at = argv.index("--root") + 1
    return (*argv[:at], os.path.relpath(argv[at], cwd), *argv[at + 1:])


def refused_at(tmp_path: Path, site: str, name: str, library: bytes,
               relative: bool = False) -> Path:
    """The file the refusal names: one run of `site`'s script over a holder in
    a folder `name`, its `--root` typed absolute or `relative` to the working
    folder, and what it must print: exit 2, no traceback, nothing on stdout,
    and on stderr exactly one line, `REFUSED family-members-unreadable: <the
    path, named as the script's `_shown` names it><after>`, with no U+202E,
    ESC or forged line anywhere in the output."""
    build, after = SITES[site]
    path, argv = build(unsafe_folder(tmp_path, name).resolve(), library)
    if relative:
        argv = typed_relative(argv, tmp_path)
    result = run_script(*argv, cwd=tmp_path)
    output = result.stdout + result.stderr
    assert result.returncode == 2, ascii(output)
    assert "Traceback" not in output, ascii(output)
    assert result.stdout == "", ascii(output)
    assert result.stderr.splitlines() == [
        f"REFUSED {CODE}: {named_as(path, name)}{after}"], ascii(output)
    assert chr(0x202E) not in output, ascii(output)
    assert_shown_safe(result.stdout, result.stderr)
    return path


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("site", sorted(SITES))
def test_each_refusal_names_the_holder_as_shown_path_names_it(
        tmp_path, site, name):
    """THE ISSUE'S PROBE, one real run per refusal: the holder's
    `family.yaml` as `repr` spells it where the folder's name holds U+202E,
    an ESC or a line feed, so nothing of that name reaches the terminal raw
    and the detail stays one line. At #1310's head each named it raw. The
    printable row is the control, named byte for byte as before, with no
    quotes."""
    refused_at(tmp_path, site, name, LIBRARY.read_bytes())


#: One refusal of each script, run with `--root` typed relative to the
#: working folder.
RELATIVE = ("bootstrap-not-a-list", "siblings-entry",
            "validate-family-not-a-list")


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("site", RELATIVE)
def test_a_holder_typed_relative_is_named_absolute_and_spelled(
        tmp_path, site, name):
    """`--root` is read as `Path(...).resolve()` first, so a holder typed
    relative to the working folder is named by its absolute path, as the
    folder it is, and that path is spelled where it holds one of the names:
    not the text as typed, and not the cwd's."""
    refused_at(tmp_path, site, name, LIBRARY.read_bytes(), relative=True)


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("site", sorted(SITES))
def test_each_copy_spells_the_path_beside_an_older_library(
        tmp_path, site, name):
    """EACH COPY REFUSES WITH THE PATH SPELLED beside a `repo_shape.py` from
    before #1168, as a holder has one that kept its own
    (`update-shape.py apply --accept-local`): it runs, refuses by name, and
    spells the path as it does beside this checkout's library. That library
    (`51a9c5f10`) already defines `shown_path`, so these rows do not forbid a
    copy from importing it. The row that does is `test_pinned_copy_text.py`'s
    `test_no_pinned_script_imports_what_an_older_library_lacks`."""
    refused_at(tmp_path, site, name, older_library())
