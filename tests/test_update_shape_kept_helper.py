# SPDX-License-Identifier: Apache-2.0
"""`apply --accept-local` keeping a copy that disagrees with a copy it
writes beside it on a name one imports from the other, in both directions:
a kept helper that lacks a name a written copy imports (#536), and a kept
copy that imports a name the written helper no longer defines (#604).

THE BREAK NOTHING REPORTED. Since #456 both roots' `bootstrap.py` import
`spelled` and `escape_unencodable_stdout` from `scripts/repo_shape.py`. A
project that kept its own edit of `repo_shape.py` with `--accept-local`
while `apply` copied the new `bootstrap.py` passed its validators, read
`unchanged` everywhere in the next `check`, and met an `ImportError` the
first time anybody ran `make bootstrap`. THE REVERSE BROKE THE SAME WAY: a
project that kept its own `bootstrap.py`, edited to import a name from
`repo_shape.py`, while `apply` copied a `repo_shape.py` that had dropped
it, got `pins ok`, `manifest ok`, and the same `ImportError`. `apply` now
refuses either run as `update-accept-local-missing-name`, before it asks
for a yes or writes a byte, and one refusal lists both kinds of line.

THE STANDARD'S NEXT COMMITS ARE REAL COMMITS IN A CLONE OF THIS REPOSITORY.
`Atlas` and the family holder `InkRouter` are cut at A, the clone's HEAD,
and each case is a branch off A, which is what a pull request to the
standard is:

  * `new-name`: `repo_shape.py` gains `NEW_NAME`, and the assembly root's
    `bootstrap.py` imports it: #536's case.
  * `no-new-name`: both files change and no name is added: the control.
  * `added`: `repo_shape.py` gains `NEW_NAME`, and a file the copy lists
    now name imports it, so it reaches a project only by `--add`.
  * `family`: `repo_shape.py` gains `NEW_NAME`, and the holder's
    `siblings.py` imports it.
  * `val-name`: `repo_shape.py` gains `NEW_NAME`, and the assembly root's
    `validate-manifest.py` imports it: a copy that is one of the root's
    validators, which would go red after the writes and be rolled back.

The reverse direction (#604) needs a project cut where `repo_shape.py`
still defines the name the standard then drops, so a second `Atlas` and
`InkRouter` are cut at `kept-base`, a branch off A where `repo_shape.py`
gains `DROPPED_NAME` and `STILL_NAME`, which no shipped copy imports. Off
`kept-base`:

  * `dropped`: `repo_shape.py` loses `DROPPED_NAME` again: #604's case.
  * `both-ways`: the same, and the holder's `siblings.py` imports a name
    its `bootstrap.py` gains, so a holder that keeps its own `bootstrap.py`
    meets both directions in one run.

The project's own edit is committed, as a project's is, so `check` reads
the edited copy as `both` or `locally-modified`, and `--branch` meets this
refusal rather than `update-branch-uncommitted`. The readers are also held,
in process, to the real importers on this checkout, to what they cannot
tell, and to what Python never runs (#675). Every file is written as BYTES,
so no platform's newline reaches a digest.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (ORG, REPO, WINDOWS_SKIP, cloned_just_pushed, git,
                      run_script)
#: The scaffold every update test starts from, and the in-process load of
#: `update-shape.py`, imported from the module that owns them; the fixture is
#: found by pytest here because it is imported.
from test_update_shape import (  # noqa: F401 (the `update_shape` fixture)
    PROJECT, UPDATE, pin_rows, scaffold_upstream_and_project, update_shape,
    verdicts,
)
#: How a pull request names a file in the copy lists, and commits it.
from test_update_shape_add import (FAMILY, MATERIALIZER, commit_all,
                                   name_in_list)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import file_sha256, load_yaml  # noqa: E402

REFUSAL = "update-accept-local-missing-name"
REPO_SHAPE = "scripts/repo_shape.py"
BOOTSTRAP = "scripts/bootstrap.py"
SIBLINGS = "scripts/siblings.py"
VALIDATE_MANIFEST = "scripts/validate-manifest.py"
#: What the refusal says only when no copy it names is one of the root's
#: validators: those import what they need, and would go red.
VALIDATORS_PASS = "though the validators, which never import it, pass"
#: Each exit the remediation gives, in the words that name the lines it
#: settles: the merge for a kept copy a `(kept) lacks` line names (#536),
#: and the change for one a `(written) no longer defines` line names (#604).
#: A refusal that holds both says "commit each".
LACKS_EXIT = "so it defines every name its `(kept) lacks` line names"
DROPS_EXIT = ("so it no longer takes any name its `(written) no longer "
              "defines` line names")
#: The file `added` names in the assembly root's copy lists.
ADDED_CHECK = "scripts/kept-helper-check.py"
BRANCH = "shape/update-kept-helper"

#: The name the standard's next commit adds to `repo_shape.py`.
NEW_NAME = "kept_helper_added_upstream"
NEW_DEFINITION = (b"\n\ndef kept_helper_added_upstream() -> str:\n"
                  b"    \"\"\"A name the standard's next commit adds.\"\"\"\n"
                  b"    return \"added upstream\"\n")
#: The line the importers gain, before their own `from repo_shape import (`.
NEW_IMPORT = (b"from repo_shape import kept_helper_added_upstream"
              b"  # noqa: E402\n")
ADDED_BODY = (b"#!/usr/bin/env python3\n"
              b"\"\"\"A check the standard's next commit adds.\"\"\"\n"
              b"import sys\n"
              b"from pathlib import Path\n\n"
              b"sys.path.insert(0, str(Path(__file__).resolve().parent))\n"
              + NEW_IMPORT +
              b"\nprint(kept_helper_added_upstream())\n")
#: An upstream change that adds no name, and the project's own edit.
NO_NAME_LINE = b"\n# An upstream change that adds no name.\n"
LOCAL_EDIT = b"\n# This project edited its own copy.\n"

#: The names `kept-base` adds to `repo_shape.py`, which no shipped copy
#: imports: `dropped` takes the first away again and keeps the second.
DROPPED_NAME = "kept_importer_dropped_upstream"
STILL_NAME = "kept_importer_still_defined"
#: A name `repo_shape.py` defines at no commit here.
NEVER_NAME = "kept_importer_never_defined"
#: The name `both-ways` adds to the holder's `bootstrap.py`, and has its
#: `siblings.py` import.
BOOT_NAME = "kept_bootstrap_added_upstream"
FAMILY_SCRIPTS = "templates/family-root/scripts"
VALIDATE_PINS_COPY = "scripts/validate-pins.py"

#: Every importer of `repo_shape` the standard ships into a root.
IMPORTERS = (
    "templates/assembly-root/scripts/bootstrap.py",
    "templates/assembly-root/scripts/validate-pins.py",
    "templates/assembly-root/scripts/validate-manifest.py",
    "scripts/validate-repository-naming.py",
    "templates/family-root/scripts/bootstrap.py",
    "templates/family-root/scripts/siblings.py",
    "templates/family-root/scripts/validate-family.py",
)
VALIDATE_PINS = "templates/assembly-root/scripts/validate-pins.py"


def defining_the_new_name(data: bytes) -> bytes:
    return data + NEW_DEFINITION


def importing_the_new_name(data: bytes) -> bytes:
    anchor = b"from repo_shape import ("
    assert anchor in data, "the importer no longer opens its import list"
    return data.replace(anchor, NEW_IMPORT + anchor, 1)


def adding_no_name(data: bytes) -> bytes:
    return data + NO_NAME_LINE


def definition(name: str) -> bytes:
    """A function named `name`, as a commit of the standard's adds one."""
    return (f"\n\ndef {name}() -> str:\n"
            f"    \"\"\"A name a commit of the standard's adds.\"\"\"\n"
            f"    return \"{name}\"\n").encode("utf-8")


def defining(*names: str):
    """An edit that appends a definition of each of `names`."""
    return lambda data: data + b"".join(definition(name) for name in names)


def dropping(name: str):
    """An edit that takes `definition(name)` out again."""
    def edit(data: bytes) -> bytes:
        assert definition(name) in data, f"{name} is not defined there"
        return data.replace(definition(name), b"", 1)
    return edit


def importing(name: str, module: str = "repo_shape"):
    """An edit that has a copy import `name` from `module`, on a line of
    its own before its own `from <module> import (`."""
    anchor = f"from {module} import (".encode("utf-8")
    line = f"from {module} import {name}  # noqa: E402\n".encode("utf-8")

    def edit(data: bytes) -> bytes:
        assert anchor in data, f"the copy no longer opens its {module} list"
        return data.replace(anchor, line + anchor, 1)
    return edit


def branch_off(upstream: Path, a: str, name: str, edits: dict) -> str:
    """`edits` (`{path: bytes -> bytes}`) as one commit on a branch off A."""
    git("checkout", "-q", "-b", name, a, cwd=upstream)
    for rel, edit in edits.items():
        path = upstream / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(edit(path.read_bytes() if path.exists() else b""))
    return commit_all(upstream, f"The standard's next commit: {name}",
                      list(edits))


def naming_the_added_check(data: bytes) -> bytes:
    return name_in_list(data.decode("utf-8"), "COPIED_VERBATIM",
                        ADDED_CHECK).encode("utf-8")


def cut_family(upstream: Path, base: Path) -> Path:
    """The holder `InkRouter`, cut under `base` from `upstream`'s HEAD."""
    created = run_script(
        upstream / "scripts" / "family.py", "init", "--org", FAMILY,
        "--family", FAMILY, "--created-by", "Test Human",
        "--created-on", "2026-09-04",
        "--local-remote-dir", str(base / "remotes"),
        "--work-dir", str(base / "fam"))
    assert created.returncode == 0, created.stderr + created.stdout
    return base / "fam" / FAMILY


def cut_project(upstream: Path, base: Path) -> Path:
    """`Atlas`, scaffolded under `base` from `upstream`'s HEAD, as a clone
    of what the scaffold pushed: `scaffold_upstream_and_project`'s cut, at
    a commit of this module's choosing."""
    made = run_script(
        upstream / "scaffold-project.py", "--org", ORG, "--project", PROJECT,
        "--elected-by", "Test Human", "--elected-on", "2026-09-02",
        "--local-remote-dir", str(base / "remotes"),
        "--work-dir", str(base / "work"))
    assert made.returncode == 0, made.stderr + made.stdout
    return cloned_just_pushed(base / "remotes" / f"{PROJECT}.git",
                              base / "clone" / PROJECT)


@pytest.fixture(scope="module")
def standard(tmp_path_factory) -> dict:
    """A clone at A, `Atlas` and `InkRouter` cut from it, and five branches
    off A, one per case."""
    base, upstream, a, clone = scaffold_upstream_and_project(
        tmp_path_factory, "update-shape-kept-helper")
    holder = cut_family(upstream, base)

    assembly = "templates/assembly-root"
    commits = {"a": a}
    commits["new-name"] = branch_off(upstream, a, "new-name", {
        REPO_SHAPE: defining_the_new_name,
        f"{assembly}/{BOOTSTRAP}": importing_the_new_name})
    commits["no-new-name"] = branch_off(upstream, a, "no-new-name", {
        REPO_SHAPE: adding_no_name,
        f"{assembly}/{BOOTSTRAP}": adding_no_name})
    commits["added"] = branch_off(upstream, a, "added", {
        REPO_SHAPE: defining_the_new_name,
        f"{assembly}/{ADDED_CHECK}": lambda _: ADDED_BODY,
        MATERIALIZER: naming_the_added_check})
    commits["family"] = branch_off(upstream, a, "family", {
        REPO_SHAPE: defining_the_new_name,
        f"templates/family-root/{SIBLINGS}": importing_the_new_name})
    commits["val-name"] = branch_off(upstream, a, "val-name", {
        REPO_SHAPE: defining_the_new_name,
        f"{assembly}/{VALIDATE_MANIFEST}": importing_the_new_name})
    return {"upstream": upstream, "clone": clone, "holder": holder,
            **commits}


@pytest.fixture(scope="module")
def dropping_standard(standard, tmp_path_factory) -> dict:
    """The reverse direction (#604), in the same clone: `kept-base`, a
    branch off A whose `repo_shape.py` gains two names no shipped copy
    imports; `Atlas` and `InkRouter` cut from it; and `dropped` and
    `both-ways`, the two branches off it the module docstring names."""
    upstream = standard["upstream"]
    base = tmp_path_factory.mktemp("update-shape-kept-importer")
    kept_base = branch_off(upstream, standard["a"], "kept-base", {
        REPO_SHAPE: defining(DROPPED_NAME, STILL_NAME)})
    clone = cut_project(upstream, base)
    holder = cut_family(upstream, base)
    commits = {"kept-base": kept_base}
    commits["dropped"] = branch_off(upstream, kept_base, "dropped", {
        REPO_SHAPE: dropping(DROPPED_NAME)})
    commits["both-ways"] = branch_off(upstream, kept_base, "both-ways", {
        REPO_SHAPE: dropping(DROPPED_NAME),
        f"{FAMILY_SCRIPTS}/bootstrap.py": defining(BOOT_NAME),
        f"{FAMILY_SCRIPTS}/siblings.py": importing(BOOT_NAME, "bootstrap")})
    return {"upstream": upstream, "clone": clone, "holder": holder,
            **commits}


def kept_edit(source: Path, target: Path, rel: str = REPO_SHAPE,
              edit=lambda data: data + LOCAL_EDIT) -> Path:
    """A private copy of `source`, with its own `edit` to `rel` COMMITTED:
    by default to `repo_shape.py`, which `check` then reads as `both`
    against every branch off A."""
    shutil.copytree(source, target, symlinks=True)
    path = target / rel
    path.write_bytes(edit(path.read_bytes()))
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        f"The project edits its own {path.name}", "--", rel, cwd=target)
    return target


@pytest.fixture
def root(standard, tmp_path) -> Path:
    return kept_edit(standard["clone"], tmp_path / PROJECT)


@pytest.fixture
def holder(standard, tmp_path) -> Path:
    return kept_edit(standard["holder"], tmp_path / FAMILY)


def apply(root: Path, standard: dict, at: str, *extra: str):
    return run_script(UPDATE, "apply", "--root", str(root), "--yes",
                      "--upstream", str(standard["upstream"]),
                      "--at", standard[at], *extra)


def blob(standard: dict, at: str, path: str) -> bytes:
    return subprocess.run(["git", "show", f"{standard[at]}:{path}"],
                          cwd=str(standard["upstream"]), capture_output=True,
                          check=True).stdout


def snapshot(root: Path) -> dict:
    """Every file's bytes under `root` but git's own, and every ref and
    HEAD: a refused run must leave all of it as it found it."""
    files = {}
    for directory, dirs, names in os.walk(root):
        dirs[:] = [name for name in dirs if name != ".git"]
        for name in names:
            if name != ".git":
                path = Path(directory) / name
                files[path.relative_to(root).as_posix()] = path.read_bytes()
    refs = git("for-each-ref", "--format=%(refname) %(objectname)",
               cwd=root).stdout
    head = git("symbolic-ref", "-q", "HEAD", cwd=root, check=False).stdout
    return {"files": files, "refs": refs, "head": head}


def lacking_line(written: str) -> str:
    return (f"    {REPO_SHAPE} (kept) lacks {NEW_NAME}, which {written} "
            "imports from it")


def dropped_line(kept: str, name: str = DROPPED_NAME) -> str:
    """#604's line: the written `repo_shape.py` drops `name`, and the kept
    copy `kept` imports it."""
    return (f"    {REPO_SHAPE} (written) no longer defines {name}, which "
            f"{kept} (kept) imports from it")


def detail_lines(stderr: str) -> list[str]:
    """The refusal's lines, one per pair, between `REFUSED` and
    `Remediation:`."""
    detail = stderr.split(f"REFUSED {REFUSAL}:", 1)[1]
    return [line for line in detail.split("Remediation:", 1)[0].splitlines()
            if line.startswith("    ")]


def assert_refused_writing_nothing(result, root: Path, before: dict,
                                   line: str) -> None:
    """Exit 2 under this refusal, with `line`, which names the kept copy,
    the written one and the name; the tree, the refs and HEAD as they were;
    no `copied` line; and no NEXT line, which would be the tool passing
    `--accept-local` for the human."""
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"REFUSED {REFUSAL}:" in result.stderr, result.stderr
    assert line in detail_lines(result.stderr), result.stderr
    assert "--accept-local" in result.stderr.split("Remediation:", 1)[1]
    assert "NEXT" not in result.stdout + result.stderr
    assert not [said for said in result.stdout.splitlines()
                if said.split()[:1] == ["copied"]], result.stdout
    assert snapshot(root) == before, "a refused apply writes nothing at all"
    assert git("status", "--porcelain", cwd=root).stdout == ""


def assert_stops_on_the_import(beside: Path, copies: dict, name: str) -> None:
    """THE PREMISE, MEASURED: `bootstrap.py --help`, in a `scripts/` that
    holds `copies` (`{file name: bytes}`) and nothing else, stops on an
    `ImportError` that names `name`."""
    beside.mkdir(parents=True)
    for file, data in copies.items():
        (beside / file).write_bytes(data)
    started = run_script(beside / "bootstrap.py", "--help",
                         env={"PYTHONDONTWRITEBYTECODE": "1"})
    assert started.returncode != 0, started.stdout
    assert "ImportError" in started.stderr, (
        "bootstrap.py did not stop on an ImportError: " + started.stderr)
    assert name in started.stderr, (
        f"the ImportError does not name {name}: " + started.stderr)


# --- end to end --------------------------------------------------------------

def test_keeping_a_helper_that_lacks_a_name_bootstrap_imports_is_refused(
        root, standard):
    """The issue's case: `repo_shape.py` is `both`, `--accept-local` keeps
    it, and the new `bootstrap.py` this run would copy imports a name only
    the upstream's `repo_shape.py` defines. Refused before the yes, with the
    tree, the pin and the refs untouched.

    THE PREMISE IS MEASURED, NOT ASSUMED: the target's `bootstrap.py`
    beside the kept `repo_shape.py` dies on that import at `--help`, which
    is what the refusal saves the project from."""
    before = snapshot(root)
    assert load_yaml(root / "contracts" / "shape-pin.yaml")["commit"] \
        .lower() == standard["a"]
    checked = run_script(UPDATE, "check", "--root", str(root),
                         "--upstream", str(standard["upstream"]),
                         "--at", standard["new-name"])
    assert verdicts(checked.stdout)[REPO_SHAPE] == "both", checked.stdout
    assert verdicts(checked.stdout)[BOOTSTRAP] == "upstream-changed"

    result = apply(root, standard, "new-name", "--accept-local", REPO_SHAPE)
    assert_refused_writing_nothing(result, root, before,
                                   lacking_line(BOOTSTRAP))
    assert (f"`git show {standard['new-name']}:{REPO_SHAPE}` for "
            f"{REPO_SHAPE}") in result.stderr
    assert "`update-conflict`'s merge by hand again" in result.stderr
    assert VALIDATORS_PASS in result.stderr, (
        "bootstrap.py is none of the validators, and the refusal says so: "
        + result.stderr)

    assert_stops_on_the_import(root.parent / "beside" / "scripts", {
        "repo_shape.py": (root / REPO_SHAPE).read_bytes(),
        "bootstrap.py": blob(standard, "new-name",
                             f"templates/assembly-root/{BOOTSTRAP}")},
        NEW_NAME)


def test_keeping_a_helper_a_validator_imports_is_refused_without_the_clause(
        root, standard):
    """`validate-manifest.py` is a copy this run writes, and it imports the
    name the kept `repo_shape.py` lacks. That one the validators DO see:
    run after the writes, it goes red and the run is rolled back. So the
    refusal still comes first, before the yes and before a byte is
    written, and does not say the validators pass."""
    before = snapshot(root)
    result = apply(root, standard, "val-name", "--accept-local", REPO_SHAPE)
    assert_refused_writing_nothing(result, root, before,
                                   lacking_line(VALIDATE_MANIFEST))
    assert VALIDATORS_PASS not in result.stderr, (
        "validate-manifest.py is one of the validators, which would not "
        "pass: " + result.stderr)


def test_with_branch_it_is_refused_before_any_branch_exists(root, standard):
    """`--branch` meets the same refusal, before `git checkout -b`: no
    branch, HEAD where it was."""
    before = snapshot(root)
    result = apply(root, standard, "new-name", "--accept-local", REPO_SHAPE,
                   "--branch", BRANCH)
    assert_refused_writing_nothing(result, root, before,
                                   lacking_line(BOOTSTRAP))
    assert git("branch", "--list", BRANCH, cwd=root).stdout == ""


def test_a_kept_helper_that_defines_every_imported_name_applies(root,
                                                                standard):
    """The control: both files change upstream, no name is added, and the
    kept `repo_shape.py` still defines all `bootstrap.py` takes. `apply`
    copies `bootstrap.py`, keeps the edit, re-pins it from the local bytes,
    and the copy it wrote starts."""
    kept = (root / REPO_SHAPE).read_bytes()
    result = apply(root, standard, "no-new-name", "--accept-local",
                   REPO_SHAPE)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"  copied   {BOOTSTRAP}" in result.stdout
    assert (root / BOOTSTRAP).read_bytes() == blob(
        standard, "no-new-name", f"templates/assembly-root/{BOOTSTRAP}")
    assert (root / REPO_SHAPE).read_bytes() == kept
    assert pin_rows(root)[REPO_SHAPE] == file_sha256(root / REPO_SHAPE)
    started = run_script(root / BOOTSTRAP, "--help",
                         env={"PYTHONDONTWRITEBYTECODE": "1"})
    assert started.returncode == 0, started.stdout + started.stderr


def test_without_accept_local_the_both_row_is_refused_as_before(root,
                                                                standard):
    """The other control: with no `--accept-local` nothing is kept, and the
    `both` row meets `update-conflict` exactly as it did."""
    before = snapshot(root)
    result = apply(root, standard, "new-name")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED update-conflict:" in result.stderr
    assert f"    {REPO_SHAPE}: " in result.stderr
    assert REFUSAL not in result.stderr
    assert snapshot(root) == before


def test_an_add_file_importing_a_name_the_kept_helper_lacks_is_refused(
        root, standard):
    """A file the standard ADDED, taken with `--add`, is a copy this run
    writes like any other: the same refusal names it, and it is not
    written."""
    before = snapshot(root)
    result = apply(root, standard, "added", "--accept-local", REPO_SHAPE,
                   "--add", ADDED_CHECK)
    assert_refused_writing_nothing(result, root, before,
                                   lacking_line(ADDED_CHECK))
    assert not (root / ADDED_CHECK).exists()


def test_a_family_holder_keeping_its_helper_is_refused_for_siblings(
        holder, standard):
    """The holder's `siblings.py` imports from the same `repo_shape.py`, and
    `make siblings`, `park` and `resume` would stop on it as `make
    bootstrap` does in a project."""
    before = snapshot(holder)
    result = apply(holder, standard, "family", "--accept-local", REPO_SHAPE)
    assert_refused_writing_nothing(result, holder, before,
                                   lacking_line(SIBLINGS))


# --- the readers, over the real importers on this checkout -------------------

def spelled_imports(text: str) -> list[set[str]]:
    """Each `from repo_shape import ...` statement's names, read as TEXT,
    independently of `ast`: one line, or a parenthesised list to its `)`,
    with `#` comments dropped."""
    statements = []
    for match in re.finditer(r"^[ \t]*from repo_shape import "
                             r"(\([^)]*\)|[^\n]*)", text, re.MULTILINE):
        body = re.sub(r"#[^\n]*", "", match.group(1)).strip("()")
        statements.append({part.split()[0]
                           for part in body.replace("\n", ",").split(",")
                           if part.strip()})
    return statements


@pytest.mark.parametrize("importer", IMPORTERS)
def test_every_name_a_shipped_importer_takes_is_found_defined(update_shape,
                                                               importer):
    """Every name each shipped importer takes from `repo_shape`, as its
    text spells it, is what `_names_imported` reads, and `_names_defined`
    finds each one in this checkout's `scripts/repo_shape.py`: the readers
    agree with the real forms (`# noqa`, parenthesised lists, single-name
    lines) and with the module they import."""
    data = (REPO / importer).read_bytes()
    spelled = set().union(*spelled_imports(data.decode("utf-8")))
    taken = update_shape._names_imported(data).get("repo_shape", set())
    assert spelled, f"{importer} no longer spells `from repo_shape import`"
    assert taken == spelled, sorted(taken ^ spelled)
    defined = update_shape._names_defined(REPO / REPO_SHAPE)
    assert defined is not None, f"{REPO_SHAPE} reads as one it cannot tell"
    assert taken <= defined, sorted(taken - defined)


def test_the_reader_finds_all_three_of_validate_pins_statements(update_shape):
    """`validate-pins.py` takes from `repo_shape` in three statements: one
    name, a parenthesised list, one name. All three are read."""
    data = (REPO / VALIDATE_PINS).read_bytes()
    statements = spelled_imports(data.decode("utf-8"))
    assert len(statements) == 3, statements
    taken = update_shape._names_imported(data)["repo_shape"]
    for names in statements:
        assert names <= taken, sorted(names - taken)


def test_what_siblings_takes_from_the_holders_bootstrap_is_found_defined(
        update_shape):
    """The other helper a shipped copy imports from: the holder's
    `siblings.py` takes five names from its `bootstrap.py`."""
    family = REPO / "templates" / "family-root" / "scripts"
    taken = update_shape._names_imported(
        (family / "siblings.py").read_bytes())["bootstrap"]
    defined = update_shape._names_defined(family / "bootstrap.py")
    assert taken, "siblings.py takes nothing from bootstrap"
    assert defined is not None, "the holder's bootstrap.py cannot be told"
    assert taken <= defined, sorted(taken - defined)


# --- the readers, in process -------------------------------------------------

#: One name per way a module binds a name at module scope, and the ways it
#: binds none there.
EVERY_BINDING = b"""\
import os.path
import json as decoding
from collections import OrderedDict as Ordered
from typing import NamedTuple


def plain():
    INSIDE_A_FUNCTION = 1


async def awaited():
    pass


class Shape:
    INSIDE_A_CLASS = 1


ASSIGNED = CHAINED = 1
first, (second, *rest) = 1, (2, 3)
[listed] = [4]
ANNOTATED: int = 5
ONLY_ANNOTATED: int
COUNTED = 0
COUNTED += 1
if ASSIGNED:
    IN_IF = 1
elif CHAINED:
    IN_ELIF = 1
else:
    IN_ELSE = 1
try:
    IN_TRY = 1
except ImportError as caught:
    IN_HANDLER = 1
else:
    IN_TRY_ELSE = 1
finally:
    IN_FINALLY = 1
with open(__file__) as opened:
    IN_WITH = 1
for looped in ():
    IN_FOR = 1
else:
    IN_FOR_ELSE = 1
while False:
    IN_WHILE = 1
"""
BOUND = {"os", "decoding", "Ordered", "NamedTuple", "plain", "awaited",
         "Shape", "ASSIGNED", "CHAINED", "first", "second", "rest", "listed",
         "ANNOTATED", "COUNTED", "IN_IF", "IN_ELIF", "IN_ELSE", "IN_TRY",
         "IN_HANDLER", "IN_TRY_ELSE", "IN_FINALLY", "opened", "IN_WITH",
         "looped", "IN_FOR", "IN_FOR_ELSE", "IN_WHILE"}
NOT_BOUND = {"INSIDE_A_FUNCTION", "INSIDE_A_CLASS", "ONLY_ANNOTATED",
             "caught", "path", "json", "OrderedDict"}


def imports(*names: str, module: str = "repo_shape") -> bytes:
    return f"from {module} import {', '.join(names)}\n".encode("utf-8")


def refusal(update_shape, root: Path, kept: dict, written: dict,
            added: dict | None = None, state: str = "both",
            accepted: set | None = None, writing: str = "upstream-changed",
            kind=None, current: dict | None = None):
    """`_refuse_kept_copies_missing_names` over rows made by hand: `kept`
    (`{path: bytes on disk}`) in `state`, `written` (`{path: target bytes}`)
    in `writing`, with `current` (`{path: bytes on disk}`) for those that
    have a file now, and `added` as `--add` files, in a root of `kind` (a
    project's unless one is given). The refusal, or None."""
    rows = []
    for path, data in {**(current or {}), **kept}.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_bytes(data)
    for path in kept:
        row = update_shape.Row(path, "")
        row.state, row.source = state, path
        rows.append(row)
    for path, data in written.items():
        row = update_shape.Row(path, "")
        row.state, row.source, row.target_bytes = writing, path, data
        rows.append(row)
    taking = [update_shape.Addition(
        update_shape.Copy(path, f"templates/assembly-root/{path}", False),
        False, data) for path, data in (added or {}).items()]
    try:
        update_shape._refuse_kept_copies_missing_names(
            root, rows, taking, set(kept) if accepted is None else accepted,
            "a" * 40, update_shape.PROJECT_KIND if kind is None else kind)
    except update_shape.Refusal as exc:
        return exc
    return None


def test_every_binding_at_module_scope_is_a_name_the_kept_copy_defines(
        update_shape, tmp_path):
    """`def`, `async def`, `class`, `=` (chained and unpacked), annotated and
    augmented `=`, `import` and `from ... import` aliases, and the same
    under a top-level `if`, `try`, `with`, `for` and `while`. Nothing a
    function or a class body binds, nor an annotation alone, nor the name an
    `except ... as` drops again."""
    path = tmp_path / "repo_shape.py"
    path.write_bytes(EVERY_BINDING)
    defined = update_shape._names_defined(path)
    assert defined is not None
    assert BOUND <= defined, sorted(BOUND - defined)
    assert not NOT_BOUND & defined, sorted(NOT_BOUND & defined)

    kept = {REPO_SHAPE: EVERY_BINDING}
    assert refusal(update_shape, tmp_path, kept,
                   {BOOTSTRAP: imports(*sorted(BOUND))}) is None
    refused = refusal(update_shape, tmp_path, kept,
                      {BOOTSTRAP: imports("ASSIGNED", "INSIDE_A_FUNCTION",
                                          "ONLY_ANNOTATED")})
    assert refused is not None, "two of the names are not bound there"
    assert refused.code == REFUSAL, refused.code
    assert (f"    {REPO_SHAPE} (kept) lacks INSIDE_A_FUNCTION, "
            f"ONLY_ANNOTATED, which {BOOTSTRAP} imports from it"
            in refused.detail), refused.detail


#: `match` and `type X =` are newer syntax than this suite's floor; a
#: Python that cannot parse them cannot import a copy that spells them.
MATCH = pytest.mark.skipif(sys.version_info < (3, 10),
                           reason="`match` is Python 3.10 syntax")
TYPE_STATEMENT = pytest.mark.skipif(sys.version_info < (3, 12),
                                    reason="`type X =` is Python 3.12 syntax")


@pytest.mark.parametrize("kept", [
    pytest.param(b"if (NEW := 1):\n    pass\n", id=":= at module scope"),
    pytest.param(b"_ = [x for x in [1] if (NEW := x)]\n",
                 id=":= in a module-level comprehension"),
    pytest.param(b"match 1:\n    case NEW:\n        pass\n",
                 id="a match capture", marks=MATCH),
    pytest.param(b"match [1]:\n    case [*NEW]:\n        pass\n",
                 id="a match star capture", marks=MATCH),
    pytest.param(b"match {}:\n    case {**NEW}:\n        pass\n",
                 id="the rest of a match mapping", marks=MATCH),
    pytest.param(b"match 1:\n    case 1:\n        NEW = 1\n",
                 id="an assignment in a case body", marks=MATCH),
    pytest.param(b"type NEW = int\n", id="a type alias", marks=TYPE_STATEMENT),
    pytest.param(b"def _init():\n    global NEW\n    NEW = 1\n\n\n_init()\n",
                 id="global in a function the module calls"),
    pytest.param(b"NEW = 1\ndel NEW\n",
                 id="bound and then deleted, a known false negative"),
])
def test_a_name_newer_syntax_binds_is_read_as_defined(update_shape, tmp_path,
                                                      kept):
    """`:=` (in a comprehension too, which binds it in the module), a
    `match` capture, `type X =`, and a `global` declared in a function: a
    kept copy that binds the name these ways imports, and is not refused.
    `del` is not read, so a name bound and then deleted reads as bound:
    the docstring names that false negative, and this pins it."""
    path = tmp_path / "repo_shape.py"
    path.write_bytes(kept)
    defined = update_shape._names_defined(path)
    assert defined is not None, "every one of these parses and is read"
    assert "NEW" in defined, sorted(defined)
    assert refusal(update_shape, tmp_path / "run", {REPO_SHAPE: kept},
                   {BOOTSTRAP: imports("NEW")}) is None


@pytest.mark.parametrize("kept", [
    pytest.param(b"def assign():\n    return (NEW := 1)\n",
                 id=":= inside a function"),
    pytest.param(b"assign = lambda: (NEW := 1)\n", id=":= inside a lambda"),
    pytest.param(b"_ = [NEW for NEW in [1]]\n",
                 id="a comprehension's own target"),
    pytest.param(b"match 1:\n    case OTHER:\n        pass\n",
                 id="a match capturing another name", marks=MATCH),
])
def test_a_name_bound_in_another_scope_is_not_the_modules(update_shape,
                                                          tmp_path, kept):
    """The walk stays in the module's own scope: a function, a lambda and
    a comprehension's loop variable bind names of their own, and the
    importer still stops on an `ImportError`."""
    refused = refusal(update_shape, tmp_path, {REPO_SHAPE: kept},
                      {BOOTSTRAP: imports("NEW")})
    assert refused is not None, "the module itself binds no NEW"
    assert f"    {REPO_SHAPE} (kept) lacks NEW, which {BOOTSTRAP}" \
        in refused.detail, refused.detail


@pytest.mark.parametrize("kind, importers, said", [
    pytest.param("PROJECT_KIND", [BOOTSTRAP], True,
                 id="a project's bootstrap.py"),
    pytest.param("PROJECT_KIND", ["scripts/validate-pins.py"], False,
                 id="a project's validate-pins.py"),
    pytest.param("PROJECT_KIND", [BOOTSTRAP, VALIDATE_MANIFEST], False,
                 id="bootstrap.py and validate-manifest.py together"),
    pytest.param("FAMILY_KIND", [SIBLINGS], True,
                 id="a holder's siblings.py"),
    pytest.param("FAMILY_KIND", ["scripts/validate-family.py"], False,
                 id="a holder's validate-family.py"),
])
def test_the_validators_are_said_to_pass_only_when_none_imports_it(
        update_shape, tmp_path, kind, importers, said):
    """`kind.validators` are what runs after the writes. A copy among them
    that imports a name the kept copy lacks goes red there and is rolled
    back, so the refusal says the validators pass only when no copy it
    names is one of them: with one validator in the list, that clause
    would be false of it."""
    refused = refusal(update_shape, tmp_path, {REPO_SHAPE: b"OLD = 1\n"},
                      {path: imports("NEW") for path in importers},
                      kind=getattr(update_shape, kind))
    assert refused is not None, "every importer here lacks NEW"
    for path in importers:
        assert f"lacks NEW, which {path} imports from it" in refused.detail, \
            refused.detail
    assert (VALIDATORS_PASS in refused.detail) == said, refused.detail


BOM = b"\xef\xbb\xbf"


@pytest.mark.parametrize("kept, written, lacking", [
    pytest.param(BOM + b"OLD = 1\n", imports("NEW"), True,
                 id="a kept copy that starts with a BOM"),
    pytest.param(b"OLD = 1\n", BOM + imports("NEW"), True,
                 id="a written copy that starts with a BOM"),
    pytest.param(BOM + b"NEW = 1\n", imports("NEW"), False,
                 id="a kept copy with a BOM that defines the name"),
    pytest.param(b"# -*- coding: latin-1 -*-\nOLD = '\xe9'\n", imports("NEW"),
                 True, id="a kept copy in latin-1 under a coding cookie"),
])
def test_the_bytes_are_read_as_python_reads_them(update_shape, tmp_path,
                                                 kept, written, lacking):
    """A BOM, or a coding cookie, means what it means to Python's own
    import. Decoded as UTF-8 first, a BOM was a character no parser takes
    and a latin-1 byte did not decode, so a copy Python imports read as one
    this could not tell about, and #536's `ImportError` went unrefused. The
    kept copy is the project's own file, where a Windows editor puts a
    BOM."""
    refused = refusal(update_shape, tmp_path, {REPO_SHAPE: kept},
                      {BOOTSTRAP: written})
    if not lacking:
        assert refused is None, refused.detail
        return
    assert refused is not None, "the kept copy lacks NEW, and is read"
    assert f"    {REPO_SHAPE} (kept) lacks NEW, which {BOOTSTRAP}" \
        in refused.detail, refused.detail


def test_a_function_level_import_counts(update_shape, tmp_path):
    """An import in a function fails when the function runs, which is
    still a copy that cannot do its job."""
    written = (b"def main():\n"
               b"    from repo_shape import " + NEW_NAME.encode() + b"\n")
    refused = refusal(update_shape, tmp_path, {REPO_SHAPE: b"OLD = 1\n"},
                      {BOOTSTRAP: written})
    assert refused is not None, "a function-level import was not read"
    assert NEW_NAME in refused.detail, refused.detail


@pytest.mark.parametrize("kept, written", [
    pytest.param(b"OLD = 1\n", b"from repo_shape import *\n",
                 id="a star import of the kept module"),
    pytest.param(b"OLD = 1\n", b"import repo_shape\nrepo_shape.NEW()\n",
                 id="an import of the module and an attribute"),
    pytest.param(b"OLD = 1\n", b"\xff from repo_shape import NEW\n",
                 id="written bytes that are not UTF-8"),
    pytest.param(b"OLD = 1\n", b"from repo_shape import (NEW\n",
                 id="written bytes that do not parse"),
    pytest.param(b"def broken(:\n", b"from repo_shape import NEW\n",
                 id="a kept copy that does not parse"),
    pytest.param(b"\xff = 1\n", b"from repo_shape import NEW\n",
                 id="a kept copy that is not UTF-8"),
    pytest.param(b"OLD = 1\n", b"from repo_shape import NEW\x00\n",
                 id="written bytes with a null byte"),
    pytest.param(b"OLD = 1\x00\n", b"from repo_shape import NEW\n",
                 id="a kept copy with a null byte"),
    pytest.param(b"from elsewhere import *\n", b"from repo_shape import NEW\n",
                 id="a kept copy with a star import"),
    pytest.param(b"def __getattr__(name):\n    return name\n",
                 b"from repo_shape import NEW\n",
                 id="a kept copy with a module __getattr__"),
    pytest.param(b"OLD = 1\n",
                 b"try:\n    from repo_shape import NEW\n"
                 b"except ImportError:\n    NEW = None\n",
                 id="an import whose ImportError the copy catches"),
    pytest.param(b"OLD = 1\n",
                 b"try:\n    from repo_shape import NEW\n"
                 b"except (OSError, Exception):\n    NEW = None\n",
                 id="an import under a handler of a class above it"),
    pytest.param(b"OLD = 1\n",
                 b"from typing import TYPE_CHECKING\n"
                 b"if TYPE_CHECKING:\n    from repo_shape import NEW\n",
                 id="an import under TYPE_CHECKING"),
    pytest.param(b"OLD = 1\n",
                 b"import typing\n"
                 b"if typing.TYPE_CHECKING:\n    from repo_shape import NEW\n",
                 id="an import under typing.TYPE_CHECKING"),
    pytest.param(b"OLD = 1\n",
                 b"try:\n    from repo_shape import NEW\n"
                 b"except ImportError:\n    def NEW():\n        return None\n",
                 id="an import whose handler defines a fallback"),
    pytest.param(b"OLD = 1\n",
                 b"try:\n    from repo_shape import NEW as new\n"
                 b"except ImportError:\n    new = None\n",
                 id="an aliased import whose handler binds the alias"),
    pytest.param(b"OLD = 1\n",
                 b"try:\n    from repo_shape import NEW\n"
                 b"except ModuleNotFoundError:\n    raise\n"
                 b"except ImportError:\n    NEW = None\n",
                 id="the first handler that catches it binds a fallback"),
    pytest.param(b"OLD = 1\n",
                 b"try:\n    from repo_shape import NEW\n"
                 b"except ImportError:\n    from compat import *\n",
                 id="a handler whose star import may bind it"),
])
def test_what_the_check_cannot_tell_or_is_answered_it_does_not_refuse(
        update_shape, tmp_path, kept, written):
    assert refusal(update_shape, tmp_path, {REPO_SHAPE: kept},
                   {BOOTSTRAP: written}) is None


#: The guarded import the cases below share, before their handler's body.
GUARDED = b"try:\n    from repo_shape import NEW\nexcept ImportError:\n"


@pytest.mark.parametrize("written", [
    pytest.param(GUARDED + b"    raise SystemExit('needs a new repo_shape')\n",
                 id="the handler exits"),
    pytest.param(b"try:\n    from repo_shape import NEW\n"
                 b"except ImportError as exc:\n"
                 b"    raise RuntimeError('an old helper') from exc\n",
                 id="the handler re-raises"),
    pytest.param(GUARDED + b"    pass\nprint(NEW)\n", id="the handler passes"),
    pytest.param(GUARDED + b"    pass\nexcept Exception:\n    NEW = None\n",
                 id="only a later handler binds a fallback"),
    pytest.param(b"try:\n    from repo_shape import NEW as new\n"
                 b"except ImportError:\n    NEW = None\n",
                 id="the handler binds the name, not the alias"),
    pytest.param(b"try:\n    def main():\n        from repo_shape import NEW\n"
                 b"        return NEW\nexcept Exception:\n    pass\n",
                 id="a def inside the try"),
    pytest.param(b"try:\n    def main():\n        from repo_shape import NEW\n"
                 b"        return NEW\nexcept Exception:\n    NEW = None\n",
                 id="a def inside the try, the fallback outside it"),
    pytest.param(b"try:\n    try:\n        from repo_shape import NEW\n"
                 b"    except ImportError:\n        pass\n"
                 b"except ImportError:\n    NEW = None\n",
                 id="an inner handler passes, inside one that binds"),
    pytest.param(b"try:\n    pass\nexcept ImportError:\n    NEW = None\n"
                 b"else:\n    from repo_shape import NEW\n",
                 id="an import in the try's else, outside its guard"),
    pytest.param(b"try:\n    pass\nexcept ImportError:\n    NEW = None\n"
                 b"finally:\n    from repo_shape import NEW\n",
                 id="an import in the try's finally, outside its guard"),
    pytest.param(GUARDED + b"    if False:\n        NEW = None\n",
                 id="the handler's fallback under if False"),
    pytest.param(GUARDED + b"    raise SystemExit\n    NEW = None\n",
                 id="the handler's fallback after its raise"),
])
def test_a_guard_whose_first_handler_binds_no_fallback_still_refuses(
        update_shape, tmp_path, written):
    """A `try` that catches the `ImportError` answers a name only where
    the first handler that catches it binds that same local name itself:
    the copy's own fallback. A handler that exits, re-raises or passes
    leaves the copy stopping there, or on a `NameError` later, and so does
    one whose binding never runs (#675). A `def` in the `try` imports when
    it is called, outside the handler, and an import in the `try`'s `else`
    or `finally` runs outside its guard, where no handler of that `try`
    catches it (#675)."""
    refused = refusal(update_shape, tmp_path, {REPO_SHAPE: b"OLD = 1\n"},
                      {BOOTSTRAP: written})
    assert refused is not None, "nothing the copy runs binds NEW"
    assert f"    {REPO_SHAPE} (kept) lacks NEW, which {BOOTSTRAP}" \
        in refused.detail, refused.detail


def test_a_fallback_answers_only_the_names_its_handler_binds(
        update_shape, tmp_path):
    """`NEW, OTHER` under one `try`, with a fallback for `NEW` alone: the
    copy still stops on `OTHER`, and the refusal names that one only."""
    written = (b"try:\n    from repo_shape import NEW, OTHER\n"
               b"except ImportError:\n    NEW = None\n")
    refused = refusal(update_shape, tmp_path, {REPO_SHAPE: b"OLD = 1\n"},
                      {BOOTSTRAP: written})
    assert refused is not None, "OTHER has no fallback"
    assert (f"    {REPO_SHAPE} (kept) lacks OTHER, which {BOOTSTRAP} "
            "imports from it") in refused.detail.splitlines(), refused.detail


#: An import guarded twice, for the cases where the inner handler's body
#: goes between `NESTED` and `OUTER_BINDS` or `OUTER_VALUE_ERROR`: the outer
#: `try` is the next one out.
NESTED = (b"try:\n    try:\n        from repo_shape import NEW\n"
          b"    except ImportError:\n")
OUTER_BINDS = b"except ImportError:\n    NEW = None\n"
OUTER_VALUE_ERROR = b"except ValueError:\n    NEW = None\n"
#: A `repo_shape.py` that lacks `NEW`, which every copy below imports.
LACKS_NEW = b"OLD = 1\n"


def run_beside_a_module_lacking_new(beside: Path, copy: bytes):
    """Python's own answer: `copy` run as a script in a folder whose
    `repo_shape.py` lacks `NEW`, so `from repo_shape import NEW` raises the
    `ImportError` the readers are asked about."""
    beside.mkdir(parents=True)
    (beside / "repo_shape.py").write_bytes(LACKS_NEW)
    (beside / "importer.py").write_bytes(copy)
    return run_script(beside / "importer.py",
                      env={"PYTHONDONTWRITEBYTECODE": "1"})


def last_line_of(stderr: str) -> str:
    return stderr.strip().splitlines()[-1]


@pytest.mark.parametrize("copy, taken, stopped_by", [
    pytest.param(GUARDED + b"    NEW = None\n    raise\n", True,
                 "ImportError",
                 id="at module scope, a handler that binds and re-raises"),
    pytest.param(NESTED + b"        NEW = None\n        raise\n" + OUTER_BINDS,
                 False, None,
                 id="nested, a handler that binds and re-raises to an outer "
                    "one that binds"),
    pytest.param(NESTED + b"        NEW = None\n"
                 b"        raise RuntimeError('an old helper')\n"
                 + OUTER_BINDS, True, "RuntimeError",
                 id="nested, a handler that binds and raises its own error"),
    pytest.param(NESTED + b"        NEW = None\n        raise\n"
                 + OUTER_VALUE_ERROR, True, "ImportError",
                 id="nested, a re-raise to an outer handler that does not "
                    "catch it"),
    pytest.param(b"try:\n    try:\n        try:\n"
                 b"            from repo_shape import NEW\n"
                 b"        except ImportError:\n            NEW = None\n"
                 b"            raise\n"
                 b"    except ImportError:\n        NEW = None\n"
                 b"        raise\n" + OUTER_BINDS, False, None,
                 id="two bare re-raises, and the outermost handler binds"),
    pytest.param(NESTED + b"        raise\n" + OUTER_BINDS, False, None,
                 id="nested, a handler that only re-raises, to one that "
                    "binds"),
    pytest.param(GUARDED + b"    NEW = None\n    raise\n    NEW = 2\n",
                 True, "ImportError",
                 id="a binding after the raise is never reached"),
    pytest.param(b"try:\n    if True:\n        try:\n"
                 b"            from repo_shape import NEW\n"
                 b"        except ImportError:\n            raise\n"
                 + OUTER_BINDS, False, None,
                 id="a re-raise through an if, to an outer handler "
                    "that binds"),
    pytest.param(GUARDED + b"    NEW = None\n", False, None,
                 id="control: a handler that only binds"),
    pytest.param(GUARDED + b"    pass\nprint(NEW)\n", True, "NameError",
                 id="control: a handler that only passes"),
])
def test_a_handler_that_raises_is_read_as_python_runs_it(
        update_shape, tmp_path, copy, taken, stopped_by):
    """A handler that binds `NEW` and then raises is no fallback (#897):
    Python leaves it by the `raise`. A bare `raise` hands the `ImportError`
    to the next `try` out, so what answers is that one's handler, and at
    module scope nothing does; any other `raise` answers nothing. Held to
    Python, as the issue's probe was: beside a `repo_shape.py` that lacks
    `NEW`, the copy the check keeps starts (exit 0), and the copy it
    refuses stops, on the `ImportError` itself, on the error the handler
    raised in its place, or on a `NameError` later."""
    imported = update_shape._names_imported(copy).get("repo_shape", set())
    assert ("NEW" in imported) is taken, imported
    refused = refusal(update_shape, tmp_path / "kept",
                      {REPO_SHAPE: LACKS_NEW}, {BOOTSTRAP: copy})
    assert (refused is not None) is taken
    if taken:
        assert f"    {REPO_SHAPE} (kept) lacks NEW, which {BOOTSTRAP}" \
            in refused.detail, refused.detail
    ran = run_beside_a_module_lacking_new(tmp_path / "beside", copy)
    if stopped_by is None:
        assert ran.returncode == 0, ran.stderr
    else:
        assert ran.returncode != 0, ran.stdout
        assert last_line_of(ran.stderr).startswith(f"{stopped_by}:"), \
            ran.stderr


@pytest.mark.skipif(sys.version_info < (3, 11),
                    reason="`except*` is Python 3.11 syntax")
def test_a_bare_raise_in_an_except_star_handler_answers_nothing(
        update_shape, tmp_path):
    """A bare `raise` in an `except*` handler re-raises an
    `ExceptionGroup`, which the plain `except ImportError:` outside does
    not catch (`ast.TryStar` is not an `ast.Try`), so it hands on nothing
    that outer handler answers: `NEW` is taken, and Python stops on the
    group, beside a `repo_shape.py` that lacks `NEW`."""
    copy = (b"try:\n    try:\n        from repo_shape import NEW\n"
            b"    except* ImportError:\n        raise\n"
            + OUTER_BINDS + b"print(NEW)\n")
    imported = update_shape._names_imported(copy).get("repo_shape", set())
    assert "NEW" in imported, imported
    refused = refusal(update_shape, tmp_path / "kept",
                      {REPO_SHAPE: LACKS_NEW}, {BOOTSTRAP: copy})
    assert refused is not None, "the copy stops on an ExceptionGroup"
    ran = run_beside_a_module_lacking_new(tmp_path / "beside", copy)
    assert ran.returncode != 0, ran.stdout
    assert "ExceptionGroup" in ran.stderr, ran.stderr


@pytest.mark.parametrize("raised", [
    pytest.param(b"        raise ImportError('an old helper')\n",
                 id="a new ImportError"),
    pytest.param(b"        raise exc\n", id="the caught error by its name"),
])
def test_a_raise_of_its_own_answers_nothing_though_an_outer_handler_catches_it(
        update_shape, tmp_path, raised):
    """The price of #897's rule, pinned: where the `raise` is not a bare
    one, whether the outer handler catches what it raises depends on that
    handler's exception list, which the reader does not read, so it answers
    nothing. `except ImportError` outside catches both of these, and Python
    starts the copy, which is refused: `a copy that starts may be refused,
    and one that stops is never kept`. Measured, beside a `repo_shape.py`
    that lacks `NEW`."""
    copy = (b"try:\n    try:\n        from repo_shape import NEW\n"
            b"    except ImportError as exc:\n        NEW = None\n"
            + raised + OUTER_BINDS)
    imported = update_shape._names_imported(copy).get("repo_shape", set())
    assert "NEW" in imported, imported
    ran = run_beside_a_module_lacking_new(tmp_path / "beside", copy)
    assert ran.returncode == 0, ran.stderr


@pytest.mark.parametrize("handler", [
    pytest.param(b"    NEW = None\n    if STRICT:\n        raise\n",
                 id="a raise under an if"),
    pytest.param(b"    NEW = None\n    sys.exit(1)\n",
                 id="a call that exits"),
    pytest.param(b"    NEW = None\n    with contextlib.nullcontext():\n"
                 b"        raise\n", id="a raise inside a with"),
])
def test_a_raise_in_a_block_or_a_call_that_exits_is_not_read_as_a_stop(
        update_shape, tmp_path, handler):
    """What #897 leaves alone, and says so. Only a `raise` among the
    handler's own statements (`_reached`) is read, so a handler that binds
    `NEW` and then raises under an `if`, inside a `with`, or exits by a call
    still answers it, since a call is not read as an exit, and what this
    cannot tell, it does not refuse. Each of these copies stops under
    Python all the same, with `STRICT` true: the false negatives that
    keep the copy, measured."""
    copy = (b"import contextlib\nimport sys\nSTRICT = True\n"
            + GUARDED + handler)
    imported = update_shape._names_imported(copy).get("repo_shape", set())
    assert "NEW" not in imported, imported
    ran = run_beside_a_module_lacking_new(tmp_path / "beside", copy)
    assert ran.returncode != 0, ran.stdout


@pytest.mark.parametrize("raised", [RecursionError, MemoryError])
def test_a_source_too_deep_to_parse_is_one_it_cannot_tell(update_shape,
                                                          tmp_path,
                                                          monkeypatch,
                                                          raised):
    """CPython answers a source nested too deep to build with a
    `RecursionError` or a `MemoryError` out of `ast.parse`, not a
    `SyntaxError`. Either reader takes it as a copy it cannot tell about,
    never a traceback out of `apply`. Raised by a stand-in, because how
    deep is too deep differs between versions and platforms."""
    def too_deep(*_args, **_kwargs):
        raise raised("too deep to build")

    path = tmp_path / "repo_shape.py"
    path.write_bytes(b"OLD = 1\n")
    monkeypatch.setattr(update_shape.ast, "parse", too_deep)
    assert update_shape._names_imported(imports("NEW")) == {}
    assert update_shape._names_defined(path) is None


def test_a_handler_that_misses_a_missing_name_still_refuses(update_shape,
                                                            tmp_path):
    """`ModuleNotFoundError` is what a missing MODULE raises; a missing NAME
    is a plain `ImportError`, which that handler does not catch."""
    written = (b"try:\n    from repo_shape import NEW\n"
               b"except ModuleNotFoundError:\n    NEW = None\n")
    refused = refusal(update_shape, tmp_path, {REPO_SHAPE: b"OLD = 1\n"},
                      {BOOTSTRAP: written})
    assert refused is not None, "ModuleNotFoundError was read as catching"
    assert "lacks NEW" in refused.detail, refused.detail


@pytest.mark.parametrize("copy, taken", [
    pytest.param(b"if False:\n    from repo_shape import NEW\n", False,
                 id="under if False"),
    pytest.param(b"if 0:\n    from repo_shape import NEW\n", False,
                 id="under if 0"),
    pytest.param(b"if None:\n    from repo_shape import NEW\n", False,
                 id="under if None"),
    pytest.param(b"try:\n    raise RuntimeError\n"
                 b"    from repo_shape import NEW\n"
                 b"except RuntimeError:\n    pass\n", False,
                 id="after a raise in a try body"),
    pytest.param(b"raise SystemExit\nfrom repo_shape import NEW\n", False,
                 id="after a raise at module scope"),
    pytest.param(b"if False:\n    pass\n"
                 b"else:\n    raise SystemExit\n"
                 b"    from repo_shape import NEW\n", False,
                 id="after a raise in the else of if False"),
    pytest.param(b"if False:\n    pass\n"
                 b"else:\n    from repo_shape import NEW\n", True,
                 id="in the else of if False"),
    pytest.param(b"if 1:\n    from repo_shape import NEW\n", True,
                 id="under a true constant"),
    pytest.param(b"from repo_shape import NEW\nraise SystemExit\n", True,
                 id="before a raise"),
])
def test_an_import_python_never_reaches_is_not_taken(update_shape, copy,
                                                     taken):
    """`_blocks_inside` (#675): Python starts a copy whose `from repo_shape
    import NEW` sits under `if False:`, `if 0:` or `if None:`, or after an
    unconditional `raise` in its block (a `try` body, the module's own, the
    `else` of `if False:`), whatever `repo_shape.py` defines, so that import
    is no name the copy takes, as one under `if TYPE_CHECKING:` was not
    already. What does run is still read: the `else` of `if False:`, a
    true constant's body, and the statements before a `raise`."""
    imported = update_shape._names_imported(copy).get("repo_shape", set())
    assert ("NEW" in imported) is taken, imported


@pytest.mark.parametrize("written, how", [
    pytest.param({"tools/bootstrap.py": imports("NEW")}, "upstream-changed",
                 id="an importer in another directory"),
    pytest.param({"scripts/notes.txt": imports("NEW")}, "upstream-changed",
                 id="a written copy that is not .py"),
    pytest.param({BOOTSTRAP: imports("NEW")}, "unchanged",
                 id="an importer this run leaves alone"),
    pytest.param({BOOTSTRAP: imports("NEW", module="bootstrap_helper")},
                 "upstream-changed", id="a module no kept copy is"),
])
def test_what_this_run_does_not_write_or_reach_is_not_asked(update_shape,
                                                             tmp_path,
                                                             written, how):
    assert refusal(update_shape, tmp_path, {REPO_SHAPE: b"OLD = 1\n"},
                   written, writing=how) is None


def test_a_copy_nobody_accepted_is_not_kept(update_shape, tmp_path):
    """Only a path `--accept-local` named is kept; `update-conflict` and
    `update-local-drift` answer for the others, first."""
    assert refusal(update_shape, tmp_path, {REPO_SHAPE: b"OLD = 1\n"},
                   {BOOTSTRAP: imports("NEW")}, accepted=set()) is None


def test_every_kept_copy_and_every_importer_is_named(update_shape, tmp_path):
    """Two kept helpers, an `--add` file and a dotted module: each pair is
    its own line, sorted, each with every name it lacks; a `both` copy is
    sent to `update-conflict`'s merge, and a `locally-modified` one is
    not."""
    kept = {REPO_SHAPE: b"OLD = 1\n", "scripts/helpers/paths.py": b"X = 1\n"}
    written = {BOOTSTRAP: imports("OLD", "NEW", "B") + imports(
        "Y", module="helpers.paths")}
    added = {ADDED_CHECK: imports("NEW")}
    refused = refusal(update_shape, tmp_path, kept, written, added=added,
                      state="locally-modified")
    assert refused is not None
    lines = [line for line in refused.detail.splitlines()
             if line.startswith("    ")]
    assert lines == [
        "    scripts/helpers/paths.py (kept) lacks Y, which "
        f"{BOOTSTRAP} imports from it",
        f"    {REPO_SHAPE} (kept) lacks B, NEW, which {BOOTSTRAP} imports "
        "from it",
        f"    {REPO_SHAPE} (kept) lacks NEW, which {ADDED_CHECK} imports "
        "from it",
    ], refused.detail
    assert "update-conflict" not in refused.remediation
    assert f"`git show {'a' * 40}:{REPO_SHAPE}` for {REPO_SHAPE}" \
        in refused.remediation
    both = refusal(update_shape, tmp_path / "both", {REPO_SHAPE: b"OLD = 1\n"},
                   {BOOTSTRAP: imports("NEW")})
    assert (f"{REPO_SHAPE} changed upstream too, so dropping the edit there "
            "is `update-conflict`'s merge by hand again") in both.remediation


# --- the reverse direction, end to end (#604) --------------------------------

def importing_root(dropping_standard: dict, tmp_path: Path,
                   rel: str = BOOTSTRAP, name: str = DROPPED_NAME) -> Path:
    """A private copy of the project cut at `kept-base`, whose own edit,
    committed, has `rel` import `name` from `repo_shape`."""
    return kept_edit(dropping_standard["clone"], tmp_path / PROJECT, rel,
                     importing(name))


@pytest.fixture
def importing_holder(dropping_standard, tmp_path) -> Path:
    """The holder cut at `kept-base`, whose own `bootstrap.py` imports
    `DROPPED_NAME`, committed."""
    return kept_edit(dropping_standard["holder"], tmp_path / FAMILY,
                     BOOTSTRAP, importing(DROPPED_NAME))


def test_keeping_a_copy_that_imports_a_name_the_run_drops_is_refused(
        dropping_standard, tmp_path):
    """#604's case: the project's committed edit has `bootstrap.py` import
    a name its pinned `repo_shape.py` defines, so that row is
    `locally-modified`, and the target drops the name, so `repo_shape.py`
    is `upstream-changed`. `--accept-local scripts/bootstrap.py` would keep
    the importer while the run writes a module that no longer defines what
    it takes. Refused before the yes, with the tree, the pin and the refs
    untouched; the row is not `both`, so `update-conflict` is not named.

    THE PREMISE IS MEASURED, NOT ASSUMED: the kept `bootstrap.py` beside
    the target's `repo_shape.py` dies on that import at `--help`."""
    standard = dropping_standard
    root = importing_root(standard, tmp_path)
    before = snapshot(root)
    checked = run_script(UPDATE, "check", "--root", str(root),
                         "--upstream", str(standard["upstream"]),
                         "--at", standard["dropped"])
    assert verdicts(checked.stdout)[BOOTSTRAP] == "locally-modified", \
        checked.stdout
    assert verdicts(checked.stdout)[REPO_SHAPE] == "upstream-changed"

    result = apply(root, standard, "dropped", "--accept-local", BOOTSTRAP)
    assert_refused_writing_nothing(result, root, before,
                                   dropped_line(BOOTSTRAP))
    remedy = result.stderr.split("Remediation:", 1)[1]
    assert (f"`git show {standard['dropped']}:templates/assembly-root/"
            f"{BOOTSTRAP}` for {BOOTSTRAP}") in remedy, remedy
    assert DROPS_EXIT in remedy, remedy
    assert LACKS_EXIT not in remedy, remedy
    assert "update-conflict" not in remedy, remedy
    assert VALIDATORS_PASS in result.stderr, (
        "bootstrap.py is none of the validators, and the refusal says so: "
        + result.stderr)

    assert_stops_on_the_import(tmp_path / "beside" / "scripts", {
        "repo_shape.py": blob(standard, "dropped", REPO_SHAPE),
        "bootstrap.py": (root / BOOTSTRAP).read_bytes()}, DROPPED_NAME)


def test_with_branch_a_dropped_name_is_refused_before_any_branch_exists(
        dropping_standard, tmp_path):
    """`--branch` meets the same refusal, before `git checkout -b`."""
    root = importing_root(dropping_standard, tmp_path)
    before = snapshot(root)
    result = apply(root, dropping_standard, "dropped", "--accept-local",
                   BOOTSTRAP, "--branch", BRANCH)
    assert_refused_writing_nothing(result, root, before,
                                   dropped_line(BOOTSTRAP))
    assert git("branch", "--list", BRANCH, cwd=root).stdout == ""


def test_a_kept_validator_importing_a_dropped_name_omits_the_clause(
        dropping_standard, tmp_path):
    """The one case the validators did catch: a kept `validate-pins.py`
    that imports the name runs after the writes, goes red, and the run is
    rolled back. It is refused first now, before the yes and before a byte
    is written, and the refusal does not say the validators pass, which
    would be false of it."""
    root = importing_root(dropping_standard, tmp_path, VALIDATE_PINS_COPY)
    before = snapshot(root)
    result = apply(root, dropping_standard, "dropped", "--accept-local",
                   VALIDATE_PINS_COPY)
    assert_refused_writing_nothing(result, root, before,
                                   dropped_line(VALIDATE_PINS_COPY))
    assert VALIDATORS_PASS not in result.stderr, result.stderr


@pytest.mark.parametrize("name, starts", [
    pytest.param(NEVER_NAME, False, id="a name the module lacked before too"),
    pytest.param(STILL_NAME, True,
                 id="a name the written module still defines"),
])
def test_a_kept_copy_importing_what_this_run_does_not_take_away_applies(
        dropping_standard, tmp_path, name, starts):
    """Only what THIS RUN takes away is refused. A name `repo_shape.py`
    lacked at the pin too stops the kept `bootstrap.py` before this run and
    after it, which is the project's doing, not the run's; a name the
    written `repo_shape.py` still defines is no disagreement at all. Both
    apply: `repo_shape.py` is copied, the kept edit is re-pinned from the
    local bytes, and the kept copy starts after the run exactly where it
    started before it."""
    root = importing_root(dropping_standard, tmp_path, name=name)
    kept = (root / BOOTSTRAP).read_bytes()

    def started() -> bool:
        return run_script(root / BOOTSTRAP, "--help",
                          env={"PYTHONDONTWRITEBYTECODE": "1"}).returncode == 0

    assert started() is starts, "the kept copy before the run"
    result = apply(root, dropping_standard, "dropped", "--accept-local",
                   BOOTSTRAP)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"  copied   {REPO_SHAPE}" in result.stdout
    assert (root / REPO_SHAPE).read_bytes() == blob(
        dropping_standard, "dropped", REPO_SHAPE)
    assert (root / BOOTSTRAP).read_bytes() == kept
    assert pin_rows(root)[BOOTSTRAP] == file_sha256(root / BOOTSTRAP)
    assert started() is starts, "the kept copy after the run"


def test_a_holder_keeping_a_bootstrap_that_imports_a_dropped_name_is_refused(
        dropping_standard, importing_holder):
    """The holder's own `bootstrap.py` imports from the same
    `repo_shape.py`, and `make bootstrap`, `make siblings`, `park` and
    `resume` would all stop on it."""
    before = snapshot(importing_holder)
    result = apply(importing_holder, dropping_standard, "dropped",
                   "--accept-local", BOOTSTRAP)
    assert_refused_writing_nothing(result, importing_holder, before,
                                   dropped_line(BOOTSTRAP))


def test_both_directions_in_one_run_are_one_refusal(dropping_standard,
                                                     importing_holder):
    """`both-ways` drops the name the holder's kept `bootstrap.py` imports,
    AND has `siblings.py` import a name only the upstream's `bootstrap.py`
    defines: the kept copy is the module of one line and the importer of
    the other. One refusal names both, sorted by module, says the
    validators pass (none of the importers is `validate-family.py`), gives
    each exit in the words of the lines it settles, with "commit each", and
    sends the `both` row to `update-conflict`'s merge."""
    checked = run_script(UPDATE, "check", "--root", str(importing_holder),
                         "--upstream", str(dropping_standard["upstream"]),
                         "--at", dropping_standard["both-ways"])
    assert verdicts(checked.stdout)[BOOTSTRAP] == "both", checked.stdout
    before = snapshot(importing_holder)
    result = apply(importing_holder, dropping_standard, "both-ways",
                   "--accept-local", BOOTSTRAP)
    assert_refused_writing_nothing(result, importing_holder, before,
                                   dropped_line(BOOTSTRAP))
    assert result.stderr.count("REFUSED") == 1, result.stderr
    assert detail_lines(result.stderr) == [
        f"    {BOOTSTRAP} (kept) lacks {BOOT_NAME}, which {SIBLINGS} "
        "imports from it",
        dropped_line(BOOTSTRAP),
    ], result.stderr
    assert VALIDATORS_PASS in result.stderr, result.stderr
    remedy = result.stderr.split("Remediation:", 1)[1]
    for words in (LACKS_EXIT, DROPS_EXIT, ", commit each, and run this"):
        assert words in remedy, remedy
    assert (f"{BOOTSTRAP} changed upstream too, so dropping the edit there "
            "is `update-conflict`'s merge by hand again") in result.stderr


# --- the reverse direction, in process (#604) --------------------------------

#: A kept copy that imports `GONE` and `KEPT` from `repo_shape`; that
#: module's bytes on disk, which define both; and the bytes this run writes
#: there, which drop `GONE`.
TAKES_GONE = imports("GONE", "KEPT")
DEFINES_GONE = b"GONE = 1\nKEPT = 1\n"
DROPS_GONE = b"KEPT = 1\n"
GETATTR = b"def __getattr__(name):\n    return name\n"


def reverse(update_shape, root: Path, importer: bytes = TAKES_GONE,
            now: bytes = DEFINES_GONE, after: bytes = DROPS_GONE,
            state: str = "locally-modified"):
    """`refusal` over a kept `bootstrap.py` (`importer`, in `state`) and a
    written `repo_shape.py`: `now` on disk, `after` the bytes this run
    writes there."""
    return refusal(update_shape, root, {BOOTSTRAP: importer},
                   {REPO_SHAPE: after}, state=state,
                   current={REPO_SHAPE: now})


def test_a_kept_copy_importing_a_name_the_written_module_drops_is_refused(
        update_shape, tmp_path):
    """The reverse line names only what is taken away: `KEPT`, which the
    written bytes still define, is not in it. The remediation names
    `--accept-local` in prose, the upstream's own copy of the kept file,
    and `update-conflict` only for a `both` row."""
    refused = reverse(update_shape, tmp_path / "modified")
    assert refused is not None, "the written repo_shape.py drops GONE"
    assert refused.code == REFUSAL, refused.code
    assert [line for line in refused.detail.splitlines()
            if line.startswith("    ")] == [
        f"    {REPO_SHAPE} (written) no longer defines GONE, which "
        f"{BOOTSTRAP} (kept) imports from it"], refused.detail
    assert f"`git show {'a' * 40}:{BOOTSTRAP}` for {BOOTSTRAP}" \
        in refused.remediation, refused.remediation
    assert "--accept-local" in refused.remediation
    assert "update-conflict" not in refused.remediation
    both = reverse(update_shape, tmp_path / "both", state="both")
    assert (f"{BOOTSTRAP} changed upstream too, so dropping the edit there "
            "is `update-conflict`'s merge by hand again") in both.remediation


@pytest.mark.parametrize("importer, now, after", [
    pytest.param(TAKES_GONE + b"def broken(:\n", DEFINES_GONE, DROPS_GONE,
                 id="a kept importer that does not parse"),
    pytest.param(b"from repo_shape import *\n", DEFINES_GONE, DROPS_GONE,
                 id="a kept importer's star import"),
    pytest.param(b"import repo_shape\nrepo_shape.GONE()\n", DEFINES_GONE,
                 DROPS_GONE, id="a kept importer's import of the module"),
    pytest.param(b"try:\n    from repo_shape import GONE\n"
                 b"except ImportError:\n    GONE = None\n",
                 DEFINES_GONE, DROPS_GONE, id="a kept importer's fallback"),
    pytest.param(TAKES_GONE, DEFINES_GONE, b"def broken(:\n",
                 id="written bytes that do not parse"),
    pytest.param(TAKES_GONE, DEFINES_GONE, DROPS_GONE + b"\x00",
                 id="written bytes with a null byte"),
    pytest.param(TAKES_GONE, DEFINES_GONE,
                 DROPS_GONE + b"from elsewhere import *\n",
                 id="written bytes with a star import"),
    pytest.param(TAKES_GONE, DEFINES_GONE, DROPS_GONE + GETATTR,
                 id="written bytes with a module __getattr__"),
    pytest.param(TAKES_GONE, b"GONE = (\n", DROPS_GONE,
                 id="bytes on disk that do not parse"),
    pytest.param(TAKES_GONE, b"\xff = 1\n", DROPS_GONE,
                 id="bytes on disk that are not UTF-8"),
    pytest.param(TAKES_GONE, b"from elsewhere import *\n", DROPS_GONE,
                 id="bytes on disk with a star import"),
    pytest.param(TAKES_GONE, DEFINES_GONE + GETATTR, DROPS_GONE,
                 id="bytes on disk with a module __getattr__"),
    pytest.param(TAKES_GONE, DROPS_GONE, DROPS_GONE + b"OTHER = 1\n",
                 id="a name the bytes on disk lack too"),
    pytest.param(TAKES_GONE, DEFINES_GONE, DEFINES_GONE + b"OTHER = 1\n",
                 id="a name the written bytes still define"),
    pytest.param(b"if False:\n    from repo_shape import GONE\n",
                 DEFINES_GONE, DROPS_GONE,
                 id="a kept importer's import under if False"),
    pytest.param(TAKES_GONE, DEFINES_GONE,
                 DROPS_GONE + b"if False:\n    pass\nelse:\n    GONE = 1\n",
                 id="written bytes binding it in the else of if False"),
    pytest.param(TAKES_GONE, DEFINES_GONE,
                 DROPS_GONE + b"try:\n    GONE = 1\n    raise RuntimeError\n"
                 b"except RuntimeError:\n    pass\n",
                 id="written bytes binding it before a raise"),
    pytest.param(TAKES_GONE, DEFINES_GONE,
                 DROPS_GONE + b"while False:\n    GONE = 1\n",
                 id="written bytes binding it under while False, read as "
                    "running"),
])
def test_what_the_reverse_cannot_tell_or_the_run_keeps_it_does_not_refuse(
        update_shape, tmp_path, importer, now, after):
    """Ruling 3 of #604, the forward check's rule: what it cannot tell, it
    does not refuse, and the validators answer after the writes. And what
    this run does not take away is not its doing. A kept import Python
    never reaches takes nothing, a binding Python does run is one, and the
    rest of what never runs, `while False:` among it, is read as running:
    what this cannot tell, it does not refuse (#675)."""
    assert reverse(update_shape, tmp_path, importer, now, after) is None


def assert_the_written_module_drops_gone(update_shape, root: Path,
                                         binding: bytes) -> None:
    """The issue's case (#675): the bytes this run writes to
    `repo_shape.py` bind `GONE` only in `binding`, where Python never runs
    it, so the kept `bootstrap.py` that takes it is refused, on the line
    that says the written module no longer defines it."""
    refused = reverse(update_shape, root, after=DROPS_GONE + binding)
    assert refused is not None, "GONE is bound only where Python never runs"
    assert dropped_line(BOOTSTRAP, "GONE") in refused.detail.splitlines(), \
        refused.detail


@pytest.mark.parametrize("binding", [
    pytest.param(b"from typing import TYPE_CHECKING\n"
                 b"if TYPE_CHECKING:\n    GONE = 1\n", id="if TYPE_CHECKING"),
    pytest.param(b"import typing\nif typing.TYPE_CHECKING:\n    GONE = 1\n",
                 id="if typing.TYPE_CHECKING"),
    pytest.param(b"if False:\n    GONE = 1\n", id="if False"),
    pytest.param(b"if 0:\n    GONE = 1\n", id="if 0"),
    pytest.param(b"if None:\n    GONE = 1\n", id="if None"),
    pytest.param(b"if KEPT:\n    pass\nelif False:\n    GONE = 1\n",
                 id="elif False"),
])
def test_a_binding_under_an_if_that_never_runs_binds_nothing(update_shape,
                                                             tmp_path,
                                                             binding):
    """`_same_scope` (#675): the body of an `if` whose test is
    `TYPE_CHECKING` or a false constant never runs, so a binding there is
    not one. Read as one, the written module still defined `GONE`, and
    the kept importer's `ImportError` got through."""
    assert_the_written_module_drops_gone(update_shape, tmp_path, binding)


@pytest.mark.parametrize("binding", [
    pytest.param(b"try:\n    raise RuntimeError\n    GONE = 1\n"
                 b"except RuntimeError:\n    pass\n",
                 id="after a raise in a try body"),
    pytest.param(b"try:\n    if KEPT:\n        raise RuntimeError\n"
                 b"        GONE = 1\nexcept RuntimeError:\n    pass\n",
                 id="after a raise in a block inside a try"),
    pytest.param(b"try:\n    if False:\n        pass\n    else:\n"
                 b"        raise RuntimeError\n        GONE = 1\n"
                 b"except RuntimeError:\n    pass\n",
                 id="after a raise in the else of if False"),
])
def test_a_binding_after_a_raise_in_its_block_binds_nothing(update_shape,
                                                            tmp_path,
                                                            binding):
    """`_bound_at` (#675): a statement after an unconditional `raise` in
    its block never runs. In a `try` body whose handler catches what it
    raised, the module imports, and it does not bind `GONE`."""
    assert_the_written_module_drops_gone(update_shape, tmp_path, binding)


def test_a_module_this_run_adds_takes_nothing_away(update_shape, tmp_path):
    """An `--add` file has no bytes on disk yet, so it defines nothing a
    kept copy could lose: whatever the kept copy imports from it, it stops
    on that today, without this run."""
    assert refusal(update_shape, tmp_path,
                   {BOOTSTRAP: imports("GONE", module="added_helper")}, {},
                   added={"scripts/added_helper.py": DROPS_GONE},
                   state="locally-modified") is None


@pytest.mark.parametrize("kept, writing", [
    pytest.param({"tools/bootstrap.py": TAKES_GONE}, "upstream-changed",
                 id="a kept importer in another directory"),
    pytest.param({"scripts/notes.txt": TAKES_GONE}, "upstream-changed",
                 id="a kept copy that is not .py"),
    pytest.param({BOOTSTRAP: TAKES_GONE}, "unchanged",
                 id="a module this run leaves alone"),
    pytest.param({BOOTSTRAP: imports("GONE", module="other_helper")},
                 "upstream-changed", id="a module no written copy is"),
])
def test_a_module_this_run_does_not_write_is_not_asked_of_a_kept_importer(
        update_shape, tmp_path, kept, writing):
    assert refusal(update_shape, tmp_path, kept, {REPO_SHAPE: DROPS_GONE},
                   state="locally-modified", writing=writing,
                   current={REPO_SHAPE: DEFINES_GONE}) is None


@pytest.mark.parametrize("importer, said", [
    pytest.param("scripts/check.py", True, id="no importer is a validator"),
    pytest.param(VALIDATE_PINS_COPY, False,
                 id="the kept importer is a validator"),
])
def test_both_directions_are_one_refusal_with_every_pair_sorted(
        update_shape, tmp_path, importer, said):
    """A kept `repo_shape.py` lacking a name a written `bootstrap.py` takes
    (#536), and a kept copy taking a name a written `paths.py` drops
    (#604): one refusal, one line per pair, sorted by module, each saying
    which side is kept. The remediation gives each side's change and the
    upstream's copy of each kept file, and the validators clause is said
    only where no importer, written or kept, is one of them."""
    refused = refusal(
        update_shape, tmp_path,
        {REPO_SHAPE: b"OLD = 1\n", importer: imports("GONE", module="paths")},
        {BOOTSTRAP: imports("OLD", "NEW"), "scripts/paths.py": DROPS_GONE},
        state="locally-modified", current={"scripts/paths.py": DEFINES_GONE})
    assert refused is not None, "both pairs disagree"
    assert [line for line in refused.detail.splitlines()
            if line.startswith("    ")] == [
        f"    scripts/paths.py (written) no longer defines GONE, which "
        f"{importer} (kept) imports from it",
        f"    {REPO_SHAPE} (kept) lacks NEW, which {BOOTSTRAP} imports from "
        "it",
    ], refused.detail
    for words in (LACKS_EXIT, DROPS_EXIT, ", commit each, and run this"):
        assert words in refused.remediation, refused.remediation
    for path in (importer, REPO_SHAPE):
        assert f"`git show {'a' * 40}:{path}` for {path}" \
            in refused.remediation, refused.remediation
    assert (VALIDATORS_PASS in refused.detail) is said, refused.detail


#: A copy beside `bootstrap.py` that no shipped root carries: a written
#: importer of `NEW` below, and the kept module of the pastes at the end.
HELPER = "scripts/helper.py"


def validator_taking(*names: str, module: str = "repo_shape") -> dict:
    """`validate-pins.py`, one of a project's validators, taking `names`
    from `module`."""
    return {VALIDATE_PINS_COPY: imports(*names, module=module)}


@pytest.mark.parametrize("kept, written, current, said", [
    pytest.param({REPO_SHAPE: b"OLD = 1\n"}, {BOOTSTRAP: imports("NEW")},
                 validator_taking("OLD"), True,
                 id="a validator taking other names from the module"),
    pytest.param({REPO_SHAPE: b"OLD = 1\n"}, {BOOTSTRAP: imports("NEW")},
                 validator_taking("NEW"), False,
                 id="a validator taking the name the kept module lacks"),
    pytest.param({REPO_SHAPE: b"OLD = 1\n"}, {HELPER: imports("NEW")},
                 validator_taking("main", module="helper"), False,
                 id="a validator importing the written importer"),
    pytest.param({REPO_SHAPE: b"OLD = 1\n"},
                 {HELPER: imports("NEW"),
                  **validator_taking("main", module="helper")}, None, False,
                 id="a validator this run writes, importing the importer"),
    pytest.param({BOOTSTRAP: TAKES_GONE}, {REPO_SHAPE: DROPS_GONE},
                 {REPO_SHAPE: DEFINES_GONE, **validator_taking("GONE")},
                 False,
                 id="a validator taking the name the written module drops"),
    pytest.param({BOOTSTRAP: TAKES_GONE}, {REPO_SHAPE: DROPS_GONE},
                 {REPO_SHAPE: DEFINES_GONE,
                  **validator_taking("main", module="bootstrap")}, False,
                 id="a validator importing the kept importer"),
])
def test_the_validators_are_not_said_to_pass_where_one_meets_a_line(
        update_shape, tmp_path, kept, written, current, said):
    """`_validators_meet` (#675): no importer here is a validator, but a
    validator that takes a line's missing name from its module, or
    imports a line's importer at all, stops on that line's `ImportError`
    when it runs after the writes, as this run leaves it: on disk, or in
    the bytes this run writes there. The clause would be false of it. A
    validator that takes OTHER names from the module, as every shipped one
    takes from `repo_shape`, passes, and the clause is said."""
    refused = refusal(update_shape, tmp_path, kept, written,
                      state="locally-modified", current=current)
    assert refused is not None, "every line here disagrees"
    assert (VALIDATORS_PASS in refused.detail) is said, refused.detail


@pytest.mark.parametrize("kept, written, current, said, unsaid", [
    pytest.param({REPO_SHAPE: b"OLD = 1\n"}, {BOOTSTRAP: imports("NEW")},
                 None, LACKS_EXIT, DROPS_EXIT,
                 id="a kept copy that lacks a name (#536)"),
    pytest.param({BOOTSTRAP: TAKES_GONE}, {REPO_SHAPE: DROPS_GONE},
                 {REPO_SHAPE: DEFINES_GONE}, DROPS_EXIT, LACKS_EXIT,
                 id="a kept copy that imports a dropped name (#604)"),
])
def test_a_one_direction_refusal_gives_only_its_own_exit(
        update_shape, tmp_path, kept, written, current, said, unsaid):
    """A refusal that holds one kind of line gives that kind's exit alone:
    the other's words would name lines it does not list."""
    refused = refusal(update_shape, tmp_path, kept, written,
                      state="locally-modified", current=current)
    assert refused is not None, "the pair disagrees"
    assert said in refused.remediation, refused.remediation
    assert unsaid not in refused.remediation, refused.remediation


def test_a_path_it_cannot_read_is_one_it_cannot_tell(update_shape, tmp_path,
                                                     monkeypatch):
    """`_names_defined` answers None for a path whose bytes cannot be read,
    as it did before #604 split the parse out of it: a missing file, the
    `ValueError` a path holding a NUL raises, and a `MemoryError`, raised
    by a stand-in because no test can rely on running out of memory."""
    assert update_shape._names_defined(tmp_path / "missing.py") is None
    assert update_shape._names_defined(tmp_path / "a\x00b.py") is None
    path = tmp_path / "repo_shape.py"
    path.write_bytes(b"OLD = 1\n")

    def too_big(*_args, **_kwargs):
        raise MemoryError("too big to read")

    monkeypatch.setattr(type(path), "read_bytes", too_big)
    assert update_shape._names_defined(path) is None


# --- the upstream's bytes a remedy names, pasted (#675) ----------------------

#: Where a fork of the standard keeps a copy, with a blank and a `'` in the
#: path: printed bare, `git show` read two arguments and exited 128, or `sh`
#: met a quotation nothing closed.
AWKWARD_SOURCE = "templates/assembly-root/scripts/it's a helper.py"
AWKWARD_BYTES = b"AWKWARD = 1\n"


@pytest.fixture
def fork(tmp_path) -> tuple[Path, str]:
    """A fork of the standard, built for the test: one commit holding a
    copy at `AWKWARD_SOURCE`. Its path, and that commit."""
    standard = tmp_path / "fork"
    git("init", "-q", str(standard), cwd=tmp_path)
    (standard / AWKWARD_SOURCE).parent.mkdir(parents=True)
    (standard / AWKWARD_SOURCE).write_bytes(AWKWARD_BYTES)
    git("add", "--", AWKWARD_SOURCE, cwd=standard)
    git("commit", "-q", "-m", "A copy at an awkward path", cwd=standard)
    return standard, git("rev-parse", "HEAD", cwd=standard).stdout.strip()


def awkward_row(update_shape, target: str):
    """A `both` row for `HELPER`, whose source in the fork is
    `AWKWARD_SOURCE` at `target`."""
    row = update_shape.Row(HELPER, "")
    row.state, row.source, row.target = (update_shape.BOTH, AWKWARD_SOURCE,
                                         target)
    return row


def merge_remedy(update_shape, target: str) -> str:
    """`update-conflict`'s remedy for that row (`merge_by_hand`)."""
    return update_shape.merge_by_hand([awkward_row(update_shape, target)])


def missing_name_remedy(update_shape, target: str) -> str:
    """`update-accept-local-missing-name`'s remedy where that row is the
    kept module a written `bootstrap.py` takes `NEW` from."""
    pair = update_shape.Disagreement(HELPER, BOOTSTRAP, ["NEW"],
                                     update_shape.KEPT_MODULE)
    return update_shape._missing_name_remediation(
        [pair], {HELPER: awkward_row(update_shape, target)}, target)


def overwrite_remedy(update_shape, target: str) -> str:
    """`update-add-would-overwrite`'s remedy for an `--add` of `HELPER`,
    whose source in the fork is `AWKWARD_SOURCE`, where the root already
    has a file (`resolve_additions`)."""
    added = update_shape.Addition(
        update_shape.Copy(HELPER, AWKWARD_SOURCE, False), True, AWKWARD_BYTES)
    with pytest.raises(update_shape.Refusal) as refused:
        update_shape.resolve_additions([], [added], [HELPER], target)
    assert refused.value.code == "update-add-would-overwrite", refused.value
    return refused.value.remediation


@WINDOWS_SKIP
@pytest.mark.parametrize("remedy", [
    pytest.param(merge_remedy, id="update-conflict"),
    pytest.param(missing_name_remedy, id="update-accept-local-missing-name"),
    pytest.param(overwrite_remedy, id="update-add-would-overwrite"),
])
def test_the_git_show_a_remedy_names_pastes_and_runs(update_shape, fork,
                                                     remedy):
    """Each remedy that names the upstream's bytes prints `git show
    <target>:<source>` quoted, as #588 quoted the other printed paths: the
    one command a POSIX shell splits it into, and, pasted into `sh` in the
    fork, the copy's own bytes. A plain path prints exactly as it did,
    which `tests/test_update_shape_messages.py` and the `git show` lines
    above hold; `update-add-would-overwrite` printed `<commit>` where the
    target goes, and `tests/test_update_shape_add.py` holds its line."""
    root, commit = fork
    shows = re.findall(r"`(git show [^`]*)`", remedy(update_shape, commit))
    assert len(shows) == 1, shows
    assert shlex.split(shows[0]) == ["git", "show",
                                     f"{commit}:{AWKWARD_SOURCE}"], shows
    pasted = subprocess.run(["sh", "-c", shows[0]], cwd=str(root),
                            capture_output=True, check=False)
    assert pasted.returncode == 0, pasted.stderr
    assert pasted.stdout == AWKWARD_BYTES, pasted.stdout
