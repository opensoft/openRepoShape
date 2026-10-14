# SPDX-License-Identifier: Apache-2.0
"""`apply --accept-local` keeping a helper that a copy it writes imports a
name from, which the kept bytes do not define (#536).

THE BREAK NOTHING REPORTED. Since #456 both roots' `bootstrap.py` import
`spelled` and `escape_unencodable_stdout` from `scripts/repo_shape.py`. A
project that kept its own edit of `repo_shape.py` with `--accept-local`
while `apply` copied the new `bootstrap.py` passed its validators, read
`unchanged` everywhere in the next `check`, and met an `ImportError` the
first time anybody ran `make bootstrap`. `apply` now refuses that run as
`update-accept-local-missing-name`, before it asks for a yes or writes a
byte.

THE STANDARD'S NEXT COMMITS ARE REAL COMMITS IN A CLONE OF THIS REPOSITORY.
`Atlas` and the family holder `InkRouter` are cut at A, the clone's HEAD,
and each case is a branch off A, which is what a pull request to the
standard is:

  * `new-name`: `repo_shape.py` gains `NEW_NAME`, and the assembly root's
    `bootstrap.py` imports it: the issue's case.
  * `no-new-name`: both files change and no name is added: the control.
  * `added`: `repo_shape.py` gains `NEW_NAME`, and a file the copy lists
    now name imports it, so it reaches a project only by `--add`.
  * `family`: `repo_shape.py` gains `NEW_NAME`, and the holder's
    `siblings.py` imports it.

The project's own edit is committed, as a project's is, so `check` reads
`repo_shape.py` as `both` and `--branch` meets this refusal rather than
`update-branch-uncommitted`. The readers are also held, in process, to the
real importers on this checkout, and to what they cannot tell. Every file is
written as BYTES, so no platform's newline reaches a digest.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO, git, run_script
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


@pytest.fixture(scope="module")
def standard(tmp_path_factory) -> dict:
    """A clone at A, `Atlas` and `InkRouter` cut from it, and four branches
    off A, one per case."""
    base, upstream, a, clone = scaffold_upstream_and_project(
        tmp_path_factory, "update-shape-kept-helper")
    created = run_script(
        upstream / "scripts" / "family.py", "init", "--org", FAMILY,
        "--family", FAMILY, "--created-by", "Test Human",
        "--created-on", "2026-09-04",
        "--local-remote-dir", str(base / "remotes"),
        "--work-dir", str(base / "fam"))
    assert created.returncode == 0, created.stderr + created.stdout

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
    return {"upstream": upstream, "clone": clone,
            "holder": base / "fam" / FAMILY, **commits}


def kept_edit(source: Path, target: Path) -> Path:
    """A private copy of `source`, with its own edit to `repo_shape.py`
    COMMITTED: `check` reads that copy as `both` against every branch."""
    shutil.copytree(source, target, symlinks=True)
    path = target / REPO_SHAPE
    path.write_bytes(path.read_bytes() + LOCAL_EDIT)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        "The project edits its own repo_shape.py", "--", REPO_SHAPE,
        cwd=target)
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


def assert_refused_writing_nothing(result, root: Path, before: dict,
                                   written: str) -> None:
    """Exit 2 under this refusal, naming the kept copy, the copy that
    imports from it and the name; the tree, the refs and HEAD as they were;
    no `copied` line; and no NEXT line, which would be the tool passing
    `--accept-local` for the human."""
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"REFUSED {REFUSAL}:" in result.stderr, result.stderr
    assert lacking_line(written) in result.stderr, result.stderr
    assert "--accept-local" in result.stderr.split("Remediation:", 1)[1]
    assert "NEXT" not in result.stdout + result.stderr
    assert not [line for line in result.stdout.splitlines()
                if line.split()[:1] == ["copied"]], result.stdout
    assert snapshot(root) == before, "a refused apply writes nothing at all"
    assert git("status", "--porcelain", cwd=root).stdout == ""


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
    assert_refused_writing_nothing(result, root, before, BOOTSTRAP)
    assert (f"`git show {standard['new-name']}:{REPO_SHAPE}` for "
            f"{REPO_SHAPE}") in result.stderr
    assert "`update-conflict`'s merge by hand again" in result.stderr

    beside = root.parent / "beside" / "scripts"
    beside.mkdir(parents=True)
    (beside / "repo_shape.py").write_bytes((root / REPO_SHAPE).read_bytes())
    (beside / "bootstrap.py").write_bytes(
        blob(standard, "new-name", f"templates/assembly-root/{BOOTSTRAP}"))
    started = run_script(beside / "bootstrap.py", "--help",
                         env={"PYTHONDONTWRITEBYTECODE": "1"})
    assert started.returncode != 0, started.stdout
    assert "ImportError" in started.stderr and NEW_NAME in started.stderr


def test_with_branch_it_is_refused_before_any_branch_exists(root, standard):
    """`--branch` meets the same refusal, before `git checkout -b`: no
    branch, HEAD where it was."""
    before = snapshot(root)
    result = apply(root, standard, "new-name", "--accept-local", REPO_SHAPE,
                   "--branch", BRANCH)
    assert_refused_writing_nothing(result, root, before, BOOTSTRAP)
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
    assert_refused_writing_nothing(result, root, before, ADDED_CHECK)
    assert not (root / ADDED_CHECK).exists()


def test_a_family_holder_keeping_its_helper_is_refused_for_siblings(
        holder, standard):
    """The holder's `siblings.py` imports from the same `repo_shape.py`, and
    `make siblings`, `park` and `resume` would stop on it as `make
    bootstrap` does in a project."""
    before = snapshot(holder)
    result = apply(holder, standard, "family", "--accept-local", REPO_SHAPE)
    assert_refused_writing_nothing(result, holder, before, SIBLINGS)


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
    assert spelled and taken == spelled, sorted(taken ^ spelled)
    defined = update_shape._names_defined(REPO / REPO_SHAPE)
    assert defined is not None and taken <= defined, sorted(taken - defined)


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
    `siblings.py` takes four names from its `bootstrap.py`."""
    family = REPO / "templates" / "family-root" / "scripts"
    taken = update_shape._names_imported(
        (family / "siblings.py").read_bytes())["bootstrap"]
    defined = update_shape._names_defined(family / "bootstrap.py")
    assert taken and taken <= defined, sorted(taken - defined)


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
            accepted: set | None = None, writing: str = "upstream-changed"):
    """`_refuse_kept_copies_missing_names` over rows made by hand: `kept`
    (`{path: bytes on disk}`) in `state`, `written` (`{path: target bytes}`)
    in `writing`, and `added` as `--add` files. The refusal, or None."""
    rows = []
    for path, data in kept.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_bytes(data)
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
            "a" * 40)
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
    assert refused is not None and refused.code == REFUSAL
    assert (f"    {REPO_SHAPE} (kept) lacks INSIDE_A_FUNCTION, "
            f"ONLY_ANNOTATED, which {BOOTSTRAP} imports from it"
            in refused.detail), refused.detail


def test_a_function_level_import_counts(update_shape, tmp_path):
    """An import in a function fails when the function runs, which is
    still a copy that cannot do its job."""
    written = (b"def main():\n"
               b"    from repo_shape import " + NEW_NAME.encode() + b"\n")
    refused = refusal(update_shape, tmp_path, {REPO_SHAPE: b"OLD = 1\n"},
                      {BOOTSTRAP: written})
    assert refused is not None and NEW_NAME in refused.detail


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
])
def test_what_the_check_cannot_tell_or_is_answered_it_does_not_refuse(
        update_shape, tmp_path, kept, written):
    assert refusal(update_shape, tmp_path, {REPO_SHAPE: kept},
                   {BOOTSTRAP: written}) is None


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
    assert refused is not None and "lacks NEW" in refused.detail


@pytest.mark.parametrize("written, how", [
    pytest.param({"tools/bootstrap.py": imports("NEW")}, "upstream-changed",
                 id="an importer in another directory"),
    pytest.param({"Makefile": imports("NEW")}, "upstream-changed",
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
