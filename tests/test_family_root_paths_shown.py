# SPDX-License-Identifier: Apache-2.0
"""Five refusal texts of `scripts/family.py` name the holder's path as
`shown_path` names it (#1317, its first part).

#1310 spells `family-unreadable` and `family-wrong-kind` in `Family.open`.
The refusals beside them still named the holder raw, so that a bidi override,
U+202E, in a `--family-root`'s name reordered the line, an ESC reached the
terminal as the control it is, and a line feed began a line of the path's
choosing:

- `family-root-missing`, in `Family.open` (`add`, `bump` and `remove`) and in
  `cmd_siblings` (`siblings`): `<holder>/family.yaml does not exist`;
- `family-members-unreadable`, both lines of `_checked_members_readable`
  (a `members:` that is not a list, and an entry that is not a mapping):
  `<holder>/family.yaml: ...`;
- `siblings-script-missing`'s message, which says `there is no
  <holder>/scripts/siblings.py`.

Each is spelled now, as `shown_path` spells a path: as it is, unless a
character in it is not printable, and then as `repr` spells it. A printable
holder is named byte for byte as it always was, and no word of any refusal
changes.

NOT IN THIS PART, and left as it was: `siblings-script-missing`'s remedy,
whose `update-shape.py check --root <holder>` is a line a person pastes, and
`member-unknown`'s lines. #1317 leaves them as a decision (#766 left such
lines raw on purpose), and one row pins the remedy as it is, so that a later
part that changes it changes the row. The family root's own `bootstrap.py` and
`validate-family.py` wait for #1310's `_shown` copies.

NO NETWORK AND NO GITHUB: temporary files, and the session's `gh` guard first
on PATH for every tool run.
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Callable, NamedTuple

import pytest

from conftest import (
    REPO, assert_shown_safe, named_as, run_script, unsafe_folder,
)
from test_load_yaml_refusals import A_COMMIT, NAMES, refused_lines

FAMILY = REPO / "scripts" / "family.py"
MANIFEST = "family.yaml"
SIBLINGS_SCRIPT = "scripts/siblings.py"

#: A `family.yaml` of the right kind, to which a row adds its `members:`.
HEAD = "kind: family-manifest\nname: Acme\norg: acme\n"

#: What each verb is run with, past `--family-root <holder>`. All of them
#: refuse before they fetch, mount or rewrite anything, so a dry run and a
#: real one reach the same line.
ADD = ("--member", "acme/Atlas", "--dry-run")
BUMP = ("--member", "Atlas", "--to", A_COMMIT, "--dry-run")
BUMP_REAL = ("--member", "Atlas", "--to", A_COMMIT)
REMOVE = ("--member", "Atlas", "--dry-run")
SIBLINGS = ("--dry-run",)


def holder_at(folder: Path, there: bool, text: str | None) -> Path:
    """The holder a run is pointed at: `folder` itself, holding `family.yaml`
    as `text` (or empty, where `text` is None), or, where `there` is false,
    a folder under `folder` that is never made."""
    root = folder if there else folder / "Acme"
    if text is not None:
        (root / MANIFEST).write_bytes(text.encode("utf-8"))
    return root


def run_of(verb: str, rest: tuple, *, there: bool = True,
           text: str | None = None, named: str = MANIFEST) -> Callable:
    """`family.py <verb> --family-root <holder> <rest>`, over a holder as
    `holder_at` makes it, and the file the refusal names (`named`, in it)."""
    def build(folder: Path) -> tuple:
        root = holder_at(folder, there, text)
        return root / named, (FAMILY, verb, "--family-root", str(root), *rest)
    return build


class Site(NamedTuple):
    """A refusal: its code, how one run reaches it, what it says before and
    after the path, how its `Remediation:` line begins, and whether that line
    names the holder in a command a person pastes."""
    code: str
    build: Callable
    before: str
    after: str
    remedy: str
    pasted: bool = False


#: What each refusal says around the path, in its own words.
ROOT_MISSING = " does not exist, so this is not a family root"
INIT_REMEDY = ("Remediation: `family.py init --org <org> --family <Name>` "
               "creates one")
NOT_A_LIST = ": `members:` is 5, expected a list"
NOT_A_MAPPING = ": a member is not a mapping: 5"
MEMBERS_REMEDY = ("Remediation: `members:` is the list of rows `family.py "
                  "add` writes")
NO_SCRIPT = ("family.py siblings needs scripts/siblings.py, which this "
             "holder does not have: there is no ")
NO_SCRIPT_AFTER = (". It runs the holder's own copy, as `make siblings` does, "
                   "and has no second implementation to fall back on, so "
                   "nothing was cloned or fetched.")
SCRIPT_REMEDY = ("Remediation: update-shape.py copies a changed Makefile but "
                 "adds a new file only on the human's word")

#: The issue's table, one row per site and way in, by an id that names the
#: code and the verb.
SITES = {
    "family-root-missing-add": Site(
        "family-root-missing", run_of("add", ADD), "", ROOT_MISSING,
        INIT_REMEDY + ". A PROJECT is scaffolded with"),
    "family-root-missing-bump": Site(
        "family-root-missing", run_of("bump", BUMP, there=False), "",
        ROOT_MISSING, INIT_REMEDY + ". A PROJECT is scaffolded with"),
    "family-root-missing-bump-real-run": Site(
        "family-root-missing", run_of("bump", BUMP_REAL), "", ROOT_MISSING,
        INIT_REMEDY + ". A PROJECT is scaffolded with"),
    "family-root-missing-remove": Site(
        "family-root-missing", run_of("remove", REMOVE), "", ROOT_MISSING,
        INIT_REMEDY + ". A PROJECT is scaffolded with"),
    "family-root-missing-siblings": Site(
        "family-root-missing", run_of("siblings", SIBLINGS), "", ROOT_MISSING,
        INIT_REMEDY + "; point --family-root at the HOLDER"),
    "family-root-missing-siblings-not-there": Site(
        "family-root-missing", run_of("siblings", (), there=False), "",
        ROOT_MISSING, INIT_REMEDY + "; point --family-root at the HOLDER"),
    "family-members-unreadable-add": Site(
        "family-members-unreadable",
        run_of("add", ADD, text=HEAD + "members: 5\n"), "", NOT_A_LIST,
        MEMBERS_REMEDY),
    "family-members-unreadable-bump": Site(
        "family-members-unreadable",
        run_of("bump", BUMP, text=HEAD + "members: 5\n"), "", NOT_A_LIST,
        MEMBERS_REMEDY),
    "family-members-unreadable-remove": Site(
        "family-members-unreadable",
        run_of("remove", REMOVE, text=HEAD + "members: 5\n"), "", NOT_A_LIST,
        MEMBERS_REMEDY),
    "family-members-unreadable-entry-add": Site(
        "family-members-unreadable",
        run_of("add", ADD, text=HEAD + "members: [5]\n"), "", NOT_A_MAPPING,
        MEMBERS_REMEDY),
    "family-members-unreadable-entry-bump": Site(
        "family-members-unreadable",
        run_of("bump", BUMP, text=HEAD + "members: [5]\n"), "",
        NOT_A_MAPPING, MEMBERS_REMEDY),
    "siblings-script-missing": Site(
        "siblings-script-missing",
        run_of("siblings", SIBLINGS, text=HEAD + "members: []\n",
               named=SIBLINGS_SCRIPT), NO_SCRIPT, NO_SCRIPT_AFTER,
        SCRIPT_REMEDY, pasted=True),
    "siblings-script-missing-real-run": Site(
        "siblings-script-missing",
        run_of("siblings", (), text=HEAD + "members: []\n",
               named=SIBLINGS_SCRIPT), NO_SCRIPT, NO_SCRIPT_AFTER,
        SCRIPT_REMEDY, pasted=True),
}


def typed_relative(argv: tuple, cwd: Path) -> tuple:
    """`argv`, its `--family-root` value written relative to `cwd`."""
    at = argv.index("--family-root") + 1
    return (*argv[:at], os.path.relpath(argv[at], cwd), *argv[at + 1:])


def refused_at(tmp_path: Path, site: str, name: str,
               relative: bool = False) -> tuple:
    """`(path, result)`: one run of `site`'s verb over a holder in a folder
    `name`, typed absolute or `relative` to the working folder, and what it
    must print: exit 2, no traceback, nothing on stdout, one `REFUSED` line
    that is exactly `REFUSED <code>: <before><the path, named as shown_path
    names it><after>`, a `Remediation:` line that begins as the code's does,
    and no U+202E, ESC or forged line in what the refusal says. A remedy that
    is a command to paste keeps the holder as it names it, so the message is
    held apart from it."""
    code, build, before, after, remedy, pasted = SITES[site]
    path, argv = build(unsafe_folder(tmp_path, name).resolve())
    if relative:
        argv = typed_relative(argv, tmp_path)
    result = run_script(*argv, cwd=tmp_path)
    output = result.stdout + result.stderr
    assert result.returncode == 2, ascii(output)
    assert "Traceback" not in output, ascii(output)
    assert refused_lines(result.stderr) == [
        f"REFUSED {code}: {before}{named_as(path, name)}{after}"], ascii(
            output)
    message, _, remedy_text = result.stderr.partition("\nRemediation: ")
    assert result.stdout == "", ascii(output)
    assert ("Remediation: " + remedy_text).startswith(remedy), ascii(output)
    seen = message if pasted else result.stderr
    assert chr(0x202E) not in seen, ascii(output)
    assert_shown_safe(result.stdout, seen)
    return path, result


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("site", sorted(SITES))
def test_each_refusal_names_the_holder_as_shown_path_names_it(
        tmp_path, site, name):
    """THE ISSUE'S PROBE, one real run per site: the holder's path as `repr`
    spells it where its folder's name holds U+202E, an ESC or a line feed, so
    nothing of that name reaches the terminal raw and the message stays one
    line. On main each named it raw. The printable row is the control, named
    byte for byte as before, with no quotes."""
    refused_at(tmp_path, site, name)


#: One site of each of the three codes, run with `--family-root` typed
#: relative to the working folder: both of `family-root-missing`'s functions,
#: `family-members-unreadable`'s `Family.open`, and `siblings`' script.
RELATIVE = ("family-root-missing-bump", "family-root-missing-siblings",
            "family-members-unreadable-bump", "siblings-script-missing")


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("site", RELATIVE)
def test_a_holder_typed_relative_is_named_absolute_and_spelled(
        tmp_path, site, name):
    """`--family-root` is read as `Path(...).expanduser().resolve()` first,
    so a holder typed relative to the working folder is named by its
    absolute path, as the folder it is, and that path is spelled where it
    holds one of the names: not the text as typed, and not the cwd's."""
    refused_at(tmp_path, site, name, relative=True)


@pytest.mark.parametrize("name", NAMES)
def test_siblings_script_missing_keeps_its_remedy_as_it_was(tmp_path, name):
    """NOT THIS PART (#1317's Scope): the remedy's `update-shape.py check
    --root <holder>` is a line a person pastes, and it names the holder
    through `shlex.join`, as it did. The message above it is spelled; this
    row holds the remedy to what it said, for every name, so a later part that
    spells it moves this row with it."""
    path, result = refused_at(tmp_path, "siblings-script-missing", name)
    root = path.parent.parent
    pasted = shlex.join(["python3", "update-shape.py", "check", "--root",
                         str(root)])
    remedy = result.stderr.partition("\nRemediation: ")[2]
    assert (f"From a checkout of openRepoShape run `{pasted}`, which "
            f"reports {SIBLINGS_SCRIPT} as upstream-added.") in remedy, ascii(
                result.stderr)
