# SPDX-License-Identifier: Apache-2.0
"""Fourteen missing, unreadable and wrong-kind refusals, and four more of
`update-shape.py`'s `check_pin`, name the path as `shown_path` names it
(#1288).

#1279 spelled the line after `load_yaml` in seven readers. These still
named the path raw, each a refusal of a file that is not there, does not
read as a mapping, or is of another kind: a bidi override, U+202E, in a
folder's name reordered the line, an ESC reached the terminal as the control
it is, and a line feed began a line of the path's choosing. Each is spelled
now:

- `bump-leg.py --root`: `bump-leg-root-not-a-project` and
  `bump-leg-wrong-kind`;
- an assembly root's own `validate-manifest.py`: `manifest-missing`;
- `family.py`: `family-unreadable` and `family-wrong-kind`;
- a family holder's `bootstrap.py`: `family-manifest-missing` and
  `family-manifest-unreadable`;
- its `siblings.py`: `family-manifest-unreadable`, reached only past a
  `bootstrap.py` whose `members_of` reads no `family.yaml`. The holder's own
  refuses a list first, in the same words, and a row runs that too;
- its `validate-family.py`: `shape-pin-missing`, `shape-pin-unreadable`,
  `family-manifest-missing` and `family-manifest-unreadable`;
- `update-shape.py check --root`: `update-pin-missing`, and each refusal of
  `check_pin` after #1279's `update-pin-unreadable`: `update-pin-commit`,
  `update-pin-digest-definition`, `update-pin-row` (two ways) and
  `update-pin-no-files`. `update-pin-row`'s remediation names the root in a
  `git -C` line, which is spelled too where the root does not print.

The tools a checkout of the standard runs import `shown_path`. A root's
`validate-manifest.py` and a holder's three scripts are copies, kept beside a
`scripts/repo_shape.py` that may be older than they are, so each spells with
a `_shown` of its own (`test_pinned_copy_text.py` holds each to
`shown_path`); the last rows run one refusal of each beside a library from
before #1168. A printable path is named byte for byte as it always was.

NO NETWORK AND NO GITHUB: temporary files, local repositories, and the
session's `gh` guard first on PATH for every tool run.
"""

from __future__ import annotations

import ast
import shlex
import shutil
import sys
from pathlib import Path
from typing import Callable, NamedTuple

import pytest

from conftest import (
    PRINTABLE_NAME, REPO, assert_shown_safe, git, named_as, run_script, spelt,
    unsafe_folder,
)
from test_load_yaml_refusals import (
    A_COMMIT, LIBRARY, NAMES, TEMPLATE_SCRIPTS, older_library, refused_lines,
)
from test_mapping_and_kind_refusals_shown import (
    A_LIST, ANOTHER_KIND, NOT_A_MAPPING, holding,
)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import TREE_DIGEST_DEFINITION  # noqa: E402

FAMILY_SCRIPTS = REPO / "templates" / "family-root" / "scripts"
BUMP_LEG = REPO / "scripts" / "bump-leg.py"
FAMILY = REPO / "scripts" / "family.py"
UPDATE_SHAPE = REPO / "update-shape.py"
SHAPE_PIN = "contracts/shape-pin.yaml"


def maybe(path: Path, text: str | None) -> Path:
    """`path`, holding `text`, or left absent where `text` is None."""
    return path if text is None else holding(path, text)


def a_repository(folder: Path, name: str, scripts: tuple,
                 library: bytes) -> Path:
    """A git repository at `<folder>/<name>` carrying each of `scripts` in
    its `scripts/`, beside `library` as `scripts/repo_shape.py`: a root or a
    holder as it carries its copies."""
    root = folder / name
    (root / "scripts").mkdir(parents=True)
    git("init", "-q", str(root), cwd=folder)
    for script in scripts:
        shutil.copyfile(script, root / "scripts" / script.name)
    (root / "scripts" / "repo_shape.py").write_bytes(library)
    return root


# --- how one run reaches each refusal ----------------------------------------
#
# Each builder takes the folder the name was made as and the library a copy
# is kept beside (ignored by a tool run from this checkout), and gives back
# `(the path the refusal names, the run's argv)`.


def bump_leg(text: str | None) -> Callable:
    """`bump-leg.py --root <folder> --dry-run`, `project.yaml` holding
    `text`."""
    def build(folder: Path, _library: bytes) -> tuple:
        return maybe(folder / "project.yaml", text), (
            BUMP_LEG, "--root", str(folder), "--leg", "spec", "--to",
            A_COMMIT, "--dry-run")
    return build


def manifest_gate(folder: Path, library: bytes) -> tuple:
    """A root's own `validate-manifest.py`, over a root with no
    `project.yaml`."""
    root = a_repository(folder, "Atlas",
                        (TEMPLATE_SCRIPTS / "validate-manifest.py",), library)
    return root / "project.yaml", (root / "scripts" / "validate-manifest.py",
                                   "--root", str(root))


def family_bump(text: str) -> Callable:
    """`family.py bump --dry-run --family-root <folder>`, `family.yaml`
    holding `text`."""
    def build(folder: Path, _library: bytes) -> tuple:
        return holding(folder / "family.yaml", text), (
            FAMILY, "bump", "--dry-run", "--family-root", str(folder),
            "--member", "Atlas", "--to", A_COMMIT)
    return build


def holder_bootstrap(text: str | None) -> Callable:
    """A holder's own `bootstrap.py --no-fetch`, `family.yaml` holding
    `text`."""
    def build(folder: Path, library: bytes) -> tuple:
        root = a_repository(folder, "Acme", (FAMILY_SCRIPTS / "bootstrap.py",),
                            library)
        return maybe(root / "family.yaml", text), (
            root / "scripts" / "bootstrap.py", "--root", str(root),
            "--no-fetch")
    return build


def members_unread() -> str:
    """A holder's `bootstrap.py` whose `members_of` reads no `family.yaml`,
    with the holder's own beside it as `bootstrap_real.py` for every other
    name `siblings.py` imports from `bootstrap`: past it, `siblings.py`'s own
    read of `family.yaml` is the one that refuses. The names are read from
    `siblings.py`'s own `from bootstrap import ...`, by `ast`, so a name a
    later change adds is answered too and these rows keep testing what they
    say."""
    tree = ast.parse((FAMILY_SCRIPTS / "siblings.py").read_text(
        encoding="utf-8"))
    names = [alias.name
             for node in ast.walk(tree)
             if isinstance(node, ast.ImportFrom) and node.module == "bootstrap"
             for alias in node.names if alias.name != "members_of"]
    assert names, "siblings.py imports nothing but members_of from bootstrap?"
    return ("from bootstrap_real import (  # noqa: F401\n    "
            + ",\n    ".join(names) + ",\n)\n\n\n"
            "def members_of(root):\n"
            "    return 'Acme', []\n")


def holder_siblings(members_read: bool) -> Callable:
    """A holder's own `siblings.py --dry-run`, `family.yaml` a list, beside
    the holder's `bootstrap.py` (`members_read`), whose `members_of` refuses
    it first, or beside `members_unread()`'s, which does not."""
    def build(folder: Path, library: bytes) -> tuple:
        bootstrap = FAMILY_SCRIPTS / "bootstrap.py"
        root = a_repository(
            folder, "Acme", (FAMILY_SCRIPTS / "siblings.py",
                             *((bootstrap,) if members_read else ())), library)
        if not members_read:
            shutil.copyfile(bootstrap, root / "scripts" / "bootstrap_real.py")
            holding(root / "scripts" / "bootstrap.py", members_unread())
        return holding(root / "family.yaml", A_LIST), (
            root / "scripts" / "siblings.py", "--root", str(root),
            "--dry-run")
    return build


def holder_validator(text: str | None) -> Callable:
    """A holder's own `validate-family.py`, `family.yaml` holding `text`."""
    def build(folder: Path, library: bytes) -> tuple:
        root = a_repository(folder, "Acme",
                            (FAMILY_SCRIPTS / "validate-family.py",), library)
        return maybe(root / "family.yaml", text), (
            root / "scripts" / "validate-family.py", "--root", str(root))
    return build


#: A `family.yaml` that reads, so `validate-family.py` goes on to the pin.
A_FAMILY = "kind: family-manifest\nname: Acme\norg: acme\nmembers: []\n"


def holder_pin(text: str | None) -> Callable:
    """A holder's own `validate-family.py`, `family.yaml` reading and
    `contracts/shape-pin.yaml` holding `text`."""
    def build(folder: Path, library: bytes) -> tuple:
        _manifest, argv = holder_validator(A_FAMILY)(folder, library)
        root = Path(argv[2])
        policy = root / "contracts" / "repository-naming.yaml"
        policy.parent.mkdir()
        shutil.copyfile(REPO / "contracts" / "repository-naming.yaml", policy)
        return maybe(root / SHAPE_PIN, text), argv
    return build


def update_pin(text: str | None) -> Callable:
    """`update-shape.py check --root <folder>`, a repository whose shape pin
    holds `text`."""
    def build(folder: Path, _library: bytes) -> tuple:
        git("init", "-q", str(folder), cwd=folder.parent)
        return maybe(folder / SHAPE_PIN, text), (
            UPDATE_SHAPE, "check", "--root", str(folder))
    return build


def a_pin(*lines: str) -> str:
    """A shape pin whose `commit:` and `digest_definition:` read, then
    `lines`."""
    return "".join(f"{line}\n" for line in (
        f"commit: {A_COMMIT}", f"digest_definition: {TREE_DIGEST_DEFINITION}",
        *lines))


class Site(NamedTuple):
    """A refusal: its code, how one run reaches it, what it says after the
    path, and whether its remediation names the root in a `git -C` line."""
    code: str
    build: Callable
    after: str
    remedy: bool = False


#: What each refusal says after the path, in its own words.
MAPPING = f": {NOT_A_MAPPING}"
NOT_A_ROOT = (" does not exist, so this is not an assembly root of a project "
              "that has elected this shape")
NO_MANIFEST = (" does not exist. A project that has elected this schema "
               "declares it in `project.yaml`; a project that has not, does "
               "not run this validator.")
NO_MEMBERS = (" does not exist, so there is no declaration of which members "
              "to bootstrap")
NO_FAMILY = (" does not exist. A family holder declares itself in "
             "`family.yaml`; a repository without one is not a family and "
             "does not run this validator.")
NO_PIN = (" does not exist, so there is no record of which files were copied "
          "out of openRepoShape or which revision they came from. Nothing can "
          "be re-synced against nothing.")
NOT_HEX = (": `commit:` is 'nothex', not 40 hex, so there is no revision to "
           "compare the upstream against")
NOT_THIS_DIGEST = (
    f": digest_definition is 'other', and this tool recomputes "
    f"{TREE_DIGEST_DEFINITION!r}. Rewriting the tree digest under a "
    "definition the pin does not claim would record a number whose meaning "
    "nobody stated.")
FILES_NOT_A_LIST = (": `files:` is 5, not a list of `path:`/`sha256:` rows, "
                    "so no copied file can be read from it")
ROW_NOT_A_ROW = ": a `files:` row is not `path:`/`sha256:`"
NO_ROWS = (": no `files:` rows, so the pin asserts nothing about any copied "
           "file and there is nothing to re-sync")

#: The issue's table and its four read ones: each refusal, by an id that
#: names the code and, where two tools share one, the tool.
SITES = {
    "bump-leg-root-not-a-project": Site(
        "bump-leg-root-not-a-project", bump_leg(None), NOT_A_ROOT),
    "bump-leg-wrong-kind": Site(
        "bump-leg-wrong-kind", bump_leg(ANOTHER_KIND),
        ": kind is 'other', expected 'project-manifest'"),
    "manifest-missing": Site("manifest-missing", manifest_gate, NO_MANIFEST),
    "family-unreadable": Site(
        "family-unreadable", family_bump(A_LIST), MAPPING),
    "family-wrong-kind": Site(
        "family-wrong-kind", family_bump(ANOTHER_KIND),
        ": kind is 'other', expected 'family-manifest'"),
    "family-manifest-missing-bootstrap": Site(
        "family-manifest-missing", holder_bootstrap(None), NO_MEMBERS),
    "family-manifest-unreadable-bootstrap": Site(
        "family-manifest-unreadable", holder_bootstrap(A_LIST), MAPPING),
    "family-manifest-unreadable-siblings": Site(
        "family-manifest-unreadable", holder_siblings(False), MAPPING),
    "family-manifest-unreadable-siblings-members-of": Site(
        "family-manifest-unreadable", holder_siblings(True), MAPPING),
    "shape-pin-missing": Site(
        "shape-pin-missing", holder_pin(None), " does not exist"),
    "shape-pin-unreadable": Site(
        "shape-pin-unreadable", holder_pin(A_LIST), MAPPING),
    "family-manifest-missing-validate-family": Site(
        "family-manifest-missing", holder_validator(None), NO_FAMILY),
    "family-manifest-unreadable-validate-family": Site(
        "family-manifest-unreadable", holder_validator(A_LIST), MAPPING),
    "update-pin-missing": Site(
        "update-pin-missing", update_pin(None), NO_PIN),
    "update-pin-commit": Site(
        "update-pin-commit", update_pin("commit: nothex\n"), NOT_HEX),
    "update-pin-digest-definition": Site(
        "update-pin-digest-definition",
        update_pin(f"commit: {A_COMMIT}\ndigest_definition: other\n"),
        NOT_THIS_DIGEST),
    "update-pin-row-not-a-list": Site(
        "update-pin-row", update_pin(a_pin("files: 5")), FILES_NOT_A_LIST,
        remedy=True),
    "update-pin-row-entry": Site(
        "update-pin-row", update_pin(a_pin("files:", "  - 5")), ROW_NOT_A_ROW,
        remedy=True),
    "update-pin-no-files": Site(
        "update-pin-no-files", update_pin(a_pin("files: []")), NO_ROWS),
}


def refused_at(tmp_path: Path, site: str, name: str, library: bytes) -> tuple:
    """`(path, result)`: one run of `site`'s tool over a folder `name`, and
    what it must print: exit 2, no traceback, one `REFUSED` line, exactly
    `REFUSED <code>: <the path, named as shown_path names it><after>`, and
    no U+202E, ESC or forged line anywhere in the output."""
    code, build, after, _remedy = SITES[site]
    path, argv = build(unsafe_folder(tmp_path, name).resolve(), library)
    result = run_script(*argv, cwd=tmp_path)
    output = result.stdout + result.stderr
    assert result.returncode == 2, ascii(output)
    assert "Traceback" not in output, ascii(output)
    assert refused_lines(result.stderr) == [
        f"REFUSED {code}: {named_as(path, name)}{after}"], ascii(output)
    assert chr(0x202E) not in output, ascii(output)
    assert_shown_safe(result.stdout, result.stderr)
    return path, result


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("site", sorted(SITES))
def test_each_refusal_names_the_path_as_shown_path_names_it(
        tmp_path, site, name):
    """THE ISSUE'S PROBE, one real run per refusal: the path as `repr`
    spells it where its folder's name holds U+202E, an ESC or a line feed,
    so nothing of that name reaches the terminal raw and the detail stays
    one line. At #1284's head each named it raw. The printable row is the
    control, named byte for byte as before, with no quotes.
    `update-pin-row`'s remediation names the root in its `git -C` line as
    `shown_path` does where the root does not print, and quoted for a POSIX
    shell, as `_by_hand` quotes it, where it does."""
    path, result = refused_at(tmp_path, site, name, LIBRARY.read_bytes())
    if SITES[site].remedy:
        root = path.parent.parent
        line = (shlex.join(["git", "-C", str(root), "log", "--", SHAPE_PIN])
                if name == PRINTABLE_NAME
                else f"git -C {spelt(root)} log -- {SHAPE_PIN}")
        assert f"(`{line}` names the commit that changed it)" in (
            result.stderr), ascii(result.stderr)


#: One refusal of each copy a root or a holder keeps beside its library.
COPIES = ("family-manifest-unreadable-bootstrap",
          "family-manifest-unreadable-siblings",
          "family-manifest-unreadable-validate-family", "manifest-missing")


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("site", COPIES)
def test_each_copy_spells_the_path_beside_an_older_library(
        tmp_path, site, name):
    """EACH COPY REFUSES WITH THE PATH SPELLED beside a `repo_shape.py` from
    before #1168, as a root or a holder has one that kept its own
    (`update-shape.py apply --accept-local`): it runs, refuses by name, and
    spells the path as it does beside this checkout's library. That library
    (`51a9c5f10`) already defines `shown_path`, so these rows do not forbid
    a copy from importing it. The row that does is
    `test_pinned_copy_text.py`'s
    `test_no_pinned_script_imports_what_an_older_library_lacks`."""
    refused_at(tmp_path, site, name, older_library())
