# SPDX-License-Identifier: Apache-2.0
"""A scaffolded leg's path overlaps nothing the shape writes (#197).

`scaffold-project.py` writes the shape into the assembly root FIRST and mounts
the legs after it. On main through 20e13f0, `--spec-path contracts` and
`--code-path project.yaml` planned under `--dry-run` (exit 0). The real run
then created all three repositories, pushed both legs, left the assembly root
empty and exited 2 at `git submodule add`: `'contracts' already exists and is
not a valid git repo`. `--code-path Makefile/code` died the same way, and
`--spec-path Contracts` exited 0 with a gitlink beside the shape's
`contracts/`, which a macOS or Windows disk keeps as one path. Against GitHub,
each left three real repositories for a run that made no project.

The rule is #172's shape half, which both tools ask through ONE definition:
`shape_materialize.shape_path_collisions` over `assembly_root_paths()`. A leg
path that EQUALS, CONTAINS or LIES INSIDE a path the shape writes is refused,
whatever the case, before anything is created, and `--dry-run` refuses it
too. The scaffold hands the materializer no collision directory, so adopt's
`shape/` is not on its list.

A `--pin` adds a path: the materializer writes each declared pin at
`neutral_pin_path(product)`, `contracts/openglass-pin.yaml` for `openGlass`.
The refusal first asked about a list with no pin in it, so a leg on that file
planned and then made three repositories (#197's review, S1). The scaffold now
asks about `assembly_root_paths(<its --pin products>)`, the list the
materializer writes for that run.

Most tests call `main()` in this process with every process start refused,
which shows the refusal comes before git, before `gh` and before the work
directory. The end-to-end tests run the script against a local remote
directory, and one of them puts a recording `gh` on PATH.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from conftest import (ADOPT, ORG, REPO, SCAFFOLD, WINDOWS_SKIP, git,
                      run_script)

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402
from shape_materialize import (  # noqa: E402
    CASE_ASIDE, PLACEHOLDER_RE, assembly_root_paths, materialize_assembly_root,
    neutral_pin_path,
)

PROJECT = "Northwind"
UTF8 = "utf-8"
ROLES = ("spec", "code")
REFUSED = "REFUSED scaffold-leg-path-collides"
#: What every scaffold collision says after naming the overlap. The scaffold
#: builds the root before it mounts the legs; adopt's sentence says what
#: `execute` would do instead, and is
#: `tests/test_adopt_leg_path_collisions.py`'s.
SCAFFOLD_SAYS = ("The shape writes {them} into the assembly root before the "
                 "legs are mounted, and Git cannot mount a leg at a path the "
                 "root already holds, or beyond a file it holds on the way "
                 "there: choose another path for the leg.")
REMEDIATION_ENDS = "The defaults `spec` and `code` pass."
BASE_ARGS = ("--org", ORG, "--project", PROJECT, "--elected-by", "Test Human",
             "--elected-on", "2026-09-02")
#: The file `--pin openGlass@<sha>` writes beside the manifest, spelled out
#: here so the tests say what `neutral_pin_path` must return.
GLASS_PIN = "contracts/openglass-pin.yaml"
#: A commit for a `--pin` the refusal comes before: nothing reads its digest.
ANY_COMMIT = "1" * 40

#: `(role, value, relation, what it names)`: a directory the shape writes
#: into, at the top and nested, and a path beyond a FILE it writes. A path
#: the shape writes exactly is every row of `assembly_root_paths()` below.
RELATIONS = [
    pytest.param("spec", "contracts", "contains",
                 "`contracts/spec-pin.yaml` and 3 more", id="contracts"),
    pytest.param("code", "scripts", "contains",
                 "`scripts/validate-pins.py` and 4 more", id="scripts"),
    pytest.param("spec", ".github", "contains",
                 "`.github/workflows/validate.yml`", id="dot-github"),
    pytest.param("code", ".github/workflows", "contains",
                 "`.github/workflows/validate.yml`", id="dot-github-nested"),
    pytest.param("code", "Makefile/code", "is inside", "`Makefile`",
                 id="beyond-a-shape-file"),
    pytest.param("spec", "contracts/shape-pin.yaml/spec", "is inside",
                 "`contracts/shape-pin.yaml`", id="beyond-a-nested-file"),
]

#: The same overlaps with a capital letter in the way. `Contracts` is the
#: one main scaffolded to exit 0 on a case-sensitive disk.
CASE_ONLY = [
    pytest.param("Contracts", "contains", id="contracts-capital"),
    pytest.param("PROJECT.YAML", "is", id="project-yaml-capitals"),
    pytest.param("MAKEFILE/code", "is inside", id="beyond-a-file-capitals"),
]

#: Canonical paths that overlap nothing the scaffold writes, each asked as
#: `--spec-path` beside the default `--code-path code`. `project` and
#: `scripts/spec` share a name's prefix or a directory with the shape, and no
#: path. `shape` and `shape/spec` are refused by adopt, which writes its copy
#: of a file the source already holds there; the scaffold writes nothing
#: there, because it hands the materializer no collision directory. `code`
#: is not here: beside the default it is two legs at one path, which is
#: #179's refusal, not this one's. `GLASS_PIN` is clear WITHOUT a `--pin`:
#: nothing writes it then, and it lies inside a directory the shape writes
#: into, as `contracts/spec` does.
CLEAR = ["spec", "legs/spec", "legs/.github", "scripts/spec",
         "contracts/spec", ".github/spec", "Scripts/x", "project", "README",
         "Makefile.d/code", "shape", "shape/spec", GLASS_PIN]

#: `(value, relation, aside)` with `--pin openGlass@<sha>`: the pin's file,
#: a path beyond it, and the file with capitals in the way. The overlap is a
#: question about two strings, never about a disk, so the aside is said on
#: every platform: a case-insensitive disk would meet the pin there, and a
#: case-sensitive one would keep two paths that no other disk can.
PINNED = [
    pytest.param(GLASS_PIN, "is", "", id="the-pin-file"),
    pytest.param(f"{GLASS_PIN}/x", "is inside", "", id="beyond-the-pin-file"),
    pytest.param("Contracts/OpenGlass-pin.yaml", "is", CASE_ASIDE,
                 id="the-pin-file-capitals"),
]

#: The issue's reproductions, and the two more found probing it: each made
#: three repositories on main, and the last of them made a broken project.
REPRODUCED = [
    pytest.param("--spec-path", "contracts", id="contracts"),
    pytest.param("--code-path", "project.yaml", id="project-yaml"),
    pytest.param("--code-path", "Makefile/code", id="beyond-a-file"),
    pytest.param("--spec-path", "Contracts", id="case-only"),
]


@pytest.fixture(scope="module")
def scaffold():
    """`scaffold-project.py` loaded as a module, so `main()` runs here."""
    module_spec = importlib.util.spec_from_file_location(
        "scaffold_leg_path_collisions", SCAFFOLD)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def adopter():
    """`adopt-project.py` loaded as a module, the other tool asking."""
    module_spec = importlib.util.spec_from_file_location(
        "adopt_for_scaffold_collisions", ADOPT)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def glass(tmp_path_factory):
    """A local stand-in for `openGlass` and its commit, for `--pin-source`:
    a pinned run that gets past the refusal reads the pin's digest here."""
    path = tmp_path_factory.mktemp("glass") / "openGlass"
    path.mkdir()
    git("init", "-q", "-b", "main", cwd=path)
    (path / "README.md").write_text("# openGlass\n", encoding=UTF8)
    git("add", "-A", cwd=path)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "seed",
        cwd=path)
    return path, git("rev-parse", "HEAD", cwd=path).stdout.strip()


def pinned(glass, *products: str) -> tuple[str, ...]:
    """`--pin <product>@<commit>` for each product, read from `glass`."""
    source, commit = glass
    pins = [arg for product in products
            for arg in ("--pin", f"{product}@{commit}")]
    return (*pins, "--pin-source", str(source))


class ProcessStarted(AssertionError):
    """A process was started where the refusal should already have come."""


@pytest.fixture
def no_process(monkeypatch):
    """Every command the scaffold runs, `git` and `gh` alike, starts through
    `subprocess.Popen`, which `subprocess.run` calls. While this holds,
    starting one fails the test and names the command, so a refusal that
    passes came before the first `git` or `gh` and before the work
    directory, on every platform."""
    def refuse(args, *_, **__):
        raise ProcessStarted(f"a process was started: {args!r}")
    monkeypatch.setattr(subprocess, "Popen", refuse)


def refusal_of(scaffold, capsys, *legs: str) -> str:
    """`main()` under `--dry-run` with `legs`: the refusal it printed."""
    code = scaffold.main([*BASE_ARGS, "--dry-run", *legs])
    out, err = capsys.readouterr()
    assert code == 2, out + err
    assert out == "", "the refusal comes before the plan is printed"
    assert err.startswith(f"{REFUSED}: "), err
    assert err.rstrip().endswith(REMEDIATION_ENDS), err
    return err


def says(them: str) -> str:
    return SCAFFOLD_SAYS.format(them=them)


def listing(directory: Path) -> list[str]:
    return sorted(path.relative_to(directory).as_posix()
                  for path in directory.rglob("*"))


# --- the rule, at the scaffold's own command line ---------------------------

@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("path", assembly_root_paths())
def test_every_path_the_shape_writes_is_refused_as_either_leg(
        scaffold, no_process, capsys, role, path):
    err = refusal_of(scaffold, capsys, f"--{role}-path", path)
    assert err.startswith(
        f"{REFUSED}: --{role}-path {path!r} is `{path}`. {says('it')}\n"), err
    assert CASE_ASIDE not in err


@pytest.mark.parametrize("role, value, relation, named", RELATIONS)
def test_a_path_that_holds_or_lies_beyond_one_is_refused(
        scaffold, no_process, capsys, role, value, relation, named):
    err = refusal_of(scaffold, capsys, f"--{role}-path", value)
    them = "them" if " more" in named else "it"
    assert err.startswith(
        f"{REFUSED}: --{role}-path {value!r} {relation} {named}. "
        f"{says(them)}\n"), err


@pytest.mark.parametrize("value, relation", CASE_ONLY)
def test_a_collision_that_holds_only_without_case_says_so(
        scaffold, no_process, capsys, value, relation):
    err = refusal_of(scaffold, capsys, "--spec-path", value)
    assert f"--spec-path {value!r} {relation} `" in err
    assert f"{CASE_ASIDE}. The shape writes" in err


def test_both_legs_are_asked_and_named_in_order(scaffold, no_process,
                                                capsys):
    err = refusal_of(scaffold, capsys, "--code-path", "project.yaml",
                     "--spec-path", "contracts")
    detail = err.split("\n", 1)[0]
    assert detail == (
        f"{REFUSED}: --spec-path 'contracts' contains "
        f"`contracts/spec-pin.yaml` and 3 more. {says('them')} "
        f"--code-path 'project.yaml' is `project.yaml`. {says('it')}")


def test_the_remediation_lists_the_materializers_paths(scaffold, no_process,
                                                       capsys):
    err = refusal_of(scaffold, capsys, "--spec-path", "contracts")
    remediation = err.split("\n", 1)[1]
    assert remediation.startswith("Remediation: nothing was created")
    assert ("(" + ", ".join(f"`{path}`" for path in assembly_root_paths())
            + ")") in remediation


@pytest.mark.parametrize("value", CLEAR)
def test_a_path_that_overlaps_nothing_the_scaffold_writes_plans(
        scaffold, capsys, tmp_path, value):
    code = scaffold.main([*BASE_ARGS, "--dry-run", "--spec-path", value,
                          "--local-remote-dir", str(tmp_path / "remotes")])
    out, err = capsys.readouterr()
    assert code == 0, out + err
    assert REFUSED not in err
    assert f"legs mounted at {value}/ and code/" in out
    assert "--dry-run: nothing was created." in out


# --- a `--pin`'s file is a path the shape writes ----------------------------

@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("value, relation, aside", PINNED)
def test_a_pin_file_is_refused_as_either_leg(
        scaffold, glass, no_process, capsys, role, value, relation, aside):
    """With `--pin openGlass@<sha>` the shape writes `GLASS_PIN`, so a leg
    there is refused in the words every shape path gets, before the pin's
    digest is read from the `--pin-source`, and the remediation lists it."""
    err = refusal_of(scaffold, capsys, f"--{role}-path", value,
                     *pinned(glass, "openGlass"))
    assert err.startswith(
        f"{REFUSED}: --{role}-path {value!r} {relation} `{GLASS_PIN}`{aside}. "
        f"{says('it')}\n"), err
    remediation = err.split("\n", 1)[1]
    assert ("(" + ", ".join(f"`{path}`"
                            for path in assembly_root_paths(["openGlass"]))
            + ")") in remediation


def test_every_pin_s_file_is_refused_and_counted(scaffold, glass, no_process,
                                                 capsys):
    """A second `--pin` writes a second file, named by its product alone as
    the materializer names it, owner or not, and `contracts` then holds two
    more of the shape's paths."""
    pins = pinned(glass, "openGlass", "ExplicitOwner/openPane")
    err = refusal_of(scaffold, capsys, "--spec-path",
                     "contracts/openpane-pin.yaml", "--code-path", GLASS_PIN,
                     *pins)
    assert err.split("\n", 1)[0] == (
        f"{REFUSED}: --spec-path 'contracts/openpane-pin.yaml' is "
        f"`contracts/openpane-pin.yaml`. {says('it')} "
        f"--code-path {GLASS_PIN!r} is `{GLASS_PIN}`. {says('it')}")
    err = refusal_of(scaffold, capsys, "--spec-path", "contracts", *pins)
    assert err.startswith(
        f"{REFUSED}: --spec-path 'contracts' contains "
        f"`contracts/spec-pin.yaml` and 5 more. {says('them')}\n"), err


# --- one definition, asked by both tools -------------------------------------

def test_both_tools_ask_the_one_definition(adopter, scaffold):
    """The names each tool calls ARE `shape_materialize`'s, not copies.
    Adopt keeps `_shape_collisions` for the half only it has, `shape/`, and
    no relation or phrase of its own."""
    shared = shape_materialize.shape_path_collisions
    assert scaffold.shape_path_collisions is shared
    assert adopter.shape_path_collisions is shared
    listed = shape_materialize.assembly_root_paths
    assert scaffold.assembly_root_paths is listed
    assert adopter.assembly_root_paths is listed
    assert adopter._overlap is shape_materialize.path_overlap
    assert adopter._first_and_more is shape_materialize.first_and_more
    assert adopter.MOVE_THE_LEG is shape_materialize.MOVE_THE_LEG
    assert not hasattr(adopter, "CASE_ASIDE"), "a second CASE_ASIDE in adopt"
    assert scaffold.neutral_pin_path is shape_materialize.neutral_pin_path
    assert neutral_pin_path("openGlass") == GLASS_PIN


def test_both_tools_refuse_through_it(adopter, scaffold, no_process, capsys,
                                      monkeypatch):
    """And both CALL it, each with the collision directory and the pins it
    hands the materializer: adopt `shape` and none, the scaffold none and
    its `--pin` products."""
    asked = []

    def spy(what, value, collision_dir=None, *, neutral_pins=()):
        asked.append((what, value, collision_dir, tuple(neutral_pins)))
        return [f"{what} {value!r} spied."]

    monkeypatch.setattr(adopter, "shape_path_collisions", spy)
    monkeypatch.setattr(scaffold, "shape_path_collisions", spy)
    assert adopter.leg_path_collisions((("--spec-path", "x"),)) == [
        "--spec-path 'x' spied."]
    code = scaffold.main([*BASE_ARGS, "--dry-run", "--spec-path", "y",
                          "--pin", f"openGlass@{ANY_COMMIT}"])
    err = capsys.readouterr().err
    assert code == 2
    assert err.startswith(f"{REFUSED}: --spec-path 'y' spied. "
                          "--code-path 'code' spied.\n")
    assert asked == [("--spec-path", "x", adopter.COLLISION_DIR, ()),
                     ("--spec-path", "y", None, ("openGlass",)),
                     ("--code-path", "code", None, ("openGlass",))]


@pytest.mark.parametrize("path", assembly_root_paths())
def test_both_tools_name_the_same_overlap(adopter, scaffold, no_process,
                                          capsys, path):
    """Which path, which relation and which shape path, word for word; only
    what each tool would have done next differs."""
    head = ". The shape writes"
    adopt_said, = adopter.leg_path_collisions((("--spec-path", path),))
    err = refusal_of(scaffold, capsys, "--spec-path", path)
    detail = err[len(f"{REFUSED}: "):].split("\n", 1)[0]
    assert detail.split(head)[0] == adopt_said.split(head)[0]
    assert detail == " ".join(
        shape_materialize.shape_path_collisions("--spec-path", path))


def test_adopt_still_says_what_execute_would_write(adopter):
    """The tail the shared sentence takes for adopt, which the comparison
    above stops short of, word for word (#197's review, N3)."""
    said, = adopter.leg_path_collisions((("--spec-path", "project.yaml"),))
    assert said == (
        "--spec-path 'project.yaml' is `project.yaml`. The shape writes it "
        "into the assembly root, and `execute` would write it into the "
        "mounted leg or beside it under `shape/`, leaving the root without "
        "it: choose another path for the leg.")


@pytest.mark.parametrize("products", [
    pytest.param((), id="no-pin"),
    pytest.param(("openGlass",), id="one-pin"),
    pytest.param(("openGlass", "openPane"), id="two-pins"),
])
def test_the_paths_refused_are_the_paths_the_materializer_writes(
        scaffold, no_process, capsys, tmp_path, products):
    """NO SECOND LIST. Materialized into an empty directory, as
    `_build_assembly_root` does, with each pin handed over as it hands them,
    the root holds exactly `assembly_root_paths(products)`, in the order
    written: every file is refused as a leg path once the same `--pin`s are
    passed, and so is every directory they are written into."""
    template = REPO / "templates" / "assembly-root"
    values = {name[2:-2]: "x" for path in template.rglob("*") if path.is_file()
              for name in PLACEHOLDER_RE.findall(path.read_text(UTF8))}
    root = tmp_path / "root"
    root.mkdir()
    materialized = materialize_assembly_root(
        REPO, root, values, neutral_pins={product: {} for product in products})
    files = [path for path in listing(root) if (root / path).is_file()]
    directories = [path for path in listing(root) if (root / path).is_dir()]
    assert tuple(materialized.written) == assembly_root_paths(products)
    assert sorted(files) == sorted(assembly_root_paths(products))
    assert {neutral_pin_path(product) for product in products} <= set(files)
    assert directories, "the shape writes into directories, too"
    pins = [arg for product in products
            for arg in ("--pin", f"{product}@{ANY_COMMIT}")]
    for path in files:
        err = refusal_of(scaffold, capsys, "--spec-path", path, *pins)
        assert err.startswith(f"{REFUSED}: --spec-path {path!r} is `{path}`.")
    for path in directories:
        err = refusal_of(scaffold, capsys, "--code-path", path, *pins)
        assert err.startswith(
            f"{REFUSED}: --code-path {path!r} contains `{path}/"), err


def test_the_products_asked_about_are_the_ones_the_materializer_gets(
        scaffold, glass):
    """The refusal reads each `--pin`'s product before any digest exists,
    and `_build_assembly_root` hands the materializer `declared_pin_values`:
    the same products in the same order, an owner and a repeat included."""
    source, commit = glass
    args = argparse.Namespace(
        pin=[f"openGlass@{commit}", f"ExplicitOwner/openPane@{commit}",
             f"openGlass@{commit}"],
        pin_owner="opensoft", pin_source=source)
    products = scaffold.declared_pin_products(args)
    assert list(products) == list(scaffold.declared_pin_values(args))
    assert list(products) == ["openGlass", "openPane"]


# --- the order: before `_identity` and before `_declaration` ----------------

def test_the_refusal_comes_before_git_is_asked_who_elected(
        scaffold, no_process, capsys, monkeypatch):
    """Without `--elected-by`, `_identity` asks `git config user.name`; the
    control shows it, so the refusal that starts no process came before it
    (#197's review, N3). `GIT_AUTHOR_NAME` answers first when it is set, and
    CI sets it, so it is unset here."""
    monkeypatch.delenv("GIT_AUTHOR_NAME", raising=False)
    unelected = ["--org", ORG, "--project", PROJECT,
                 "--elected-on", "2026-09-02", "--dry-run"]
    with pytest.raises(ProcessStarted, match="user.name"):
        scaffold.main(unelected)
    code = scaffold.main([*unelected, "--spec-path", "contracts"])
    out, err = capsys.readouterr()
    assert (code, out) == (2, ""), err
    assert err.startswith(f"{REFUSED}: --spec-path 'contracts' contains "), err


def test_the_refusal_comes_before_the_declaration_is_read(
        scaffold, no_process, capsys, monkeypatch):
    """`_declaration` reads each `--pin`'s digest, with `gh api` when no
    `--pin-source` is given. The `gh` stub below shows `gh` never runs, on
    POSIX only; this shows on every platform that `_declaration` is never
    called (#197's review, N3), and the control that the same command line
    reaches it once nothing collides."""
    called = []

    def declaration(args):
        called.append(list(args.pin))
        return {}, set(), (), {}

    monkeypatch.setattr(scaffold, "_declaration", declaration)
    asks_gh = ("--pin", f"openGlass@{ANY_COMMIT}", "--reuse-empty-repo")
    refusal_of(scaffold, capsys, "--spec-path", "contracts", *asks_gh)
    assert called == []
    with pytest.raises(ProcessStarted):
        scaffold.main([*BASE_ARGS, "--dry-run", *asks_gh])
    assert called == [[f"openGlass@{ANY_COMMIT}"]]


# --- end to end -------------------------------------------------------------

@pytest.mark.parametrize("legs", [
    pytest.param(("--spec-path", "contracts"), id="contracts"),
    pytest.param(("--code-path", "project.yaml"), id="project-yaml"),
    pytest.param(("--spec-path", "contracts", "--code-path", "project.yaml"),
                 id="both"),
])
def test_a_dry_run_refuses_exactly_as_the_real_run(tmp_path, legs):
    """On main the dry run said yes and the real run made three
    repositories. Now both say the same no, word for word."""
    remotes, work = tmp_path / "remotes", tmp_path / "work"
    args = (*BASE_ARGS, *legs, "--local-remote-dir", str(remotes),
            "--work-dir", str(work))
    dry = run_script(SCAFFOLD, *args, "--dry-run")
    real = run_script(SCAFFOLD, *args)
    assert (dry.returncode, real.returncode) == (2, 2), (
        dry.stdout + dry.stderr + real.stdout + real.stderr)
    assert dry.stderr == real.stderr
    assert dry.stdout == real.stdout == ""
    assert real.stderr.startswith(f"{REFUSED}: {legs[0]} {legs[1]!r} ")
    assert not remotes.exists() and not work.exists()


@pytest.mark.parametrize("flag, value", REPRODUCED)
def test_the_real_run_refuses_before_anything_exists(tmp_path, flag, value):
    """The remote directory is listed before and after and has not changed,
    and the default work directory, a temporary one, was never made: the
    temporary directory this run is given stays empty."""
    remotes = tmp_path / "remotes"
    remotes.mkdir()
    (remotes / "KEEP").write_text("here before the run\n", encoding=UTF8)
    before = listing(remotes)
    temporary = tmp_path / "tmp"
    temporary.mkdir()
    result = run_script(SCAFFOLD, *BASE_ARGS, flag, value,
                        "--local-remote-dir", str(remotes),
                        env={"TMPDIR": str(temporary), "TEMP": str(temporary),
                             "TMP": str(temporary)})
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(f"{REFUSED}: {flag} {value!r} ")
    assert "creating remotes" not in result.stdout
    assert listing(remotes) == before == ["KEEP"]
    assert list(temporary.iterdir()) == [], "no work directory was made"


def test_a_pinned_run_refuses_before_anything_exists(tmp_path, glass):
    """On #197's first head this dry run said yes and the real run made
    three repositories. The control reads the pin from the local
    `--pin-source` and plans its file; with a leg on that file the dry run
    and the real run say the same no, and nothing exists afterwards."""
    remotes, work = tmp_path / "remotes", tmp_path / "work"
    remotes.mkdir()
    (remotes / "KEEP").write_text("here before the run\n", encoding=UTF8)
    args = (*BASE_ARGS, *pinned(glass, "openGlass"),
            "--local-remote-dir", str(remotes), "--work-dir", str(work))
    control = run_script(SCAFFOLD, *args, "--dry-run")
    assert control.returncode == 0, control.stdout + control.stderr
    assert f"-> {GLASS_PIN} (local-clone (" in control.stdout
    dry = run_script(SCAFFOLD, *args, "--spec-path", GLASS_PIN, "--dry-run")
    real = run_script(SCAFFOLD, *args, "--spec-path", GLASS_PIN)
    assert (dry.returncode, real.returncode) == (2, 2), (
        dry.stdout + dry.stderr + real.stdout + real.stderr)
    assert dry.stderr == real.stderr
    assert dry.stdout == real.stdout == ""
    assert real.stderr.startswith(
        f"{REFUSED}: --spec-path {GLASS_PIN!r} is `{GLASS_PIN}`. ")
    assert listing(remotes) == ["KEEP"]
    assert not work.exists()


@WINDOWS_SKIP  # the stub `gh` is a `#!` script; Windows executes none
def test_no_gh_command_runs_before_the_refusal(tmp_path):
    """Pointed at GitHub, with a `--pin` that `gh api` would read and a
    `--reuse-empty-repo` that `gh repo view` would ask about, the refusal
    comes first and `gh` is never run. The control is the same run with the
    default paths: it reaches `gh`, so the stub would have recorded a call."""
    bin_dir, log = tmp_path / "fakebin", tmp_path / "gh.log"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(textwrap.dedent("""\
        #!/usr/bin/env python3
        import os, sys
        with open(os.environ["GH_STUB_LOG"], "a", encoding="utf-8") as log:
            log.write(" ".join(sys.argv[1:]) + "\\n")
        print("HTTP 404: Not Found", file=sys.stderr)
        sys.exit(1)
        """), encoding=UTF8)
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
           "GH_STUB_LOG": str(log)}
    common = (*BASE_ARGS, "--pin", "openGlass@" + "1" * 40,
              "--reuse-empty-repo", "--work-dir", str(tmp_path / "work"))

    refused = run_script(SCAFFOLD, *common, "--spec-path", "contracts",
                         env=env)
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert refused.stderr.startswith(f"{REFUSED}: --spec-path 'contracts' ")
    assert not log.exists(), f"gh was run: {log.read_text(encoding=UTF8)}"
    assert not (tmp_path / "work").exists()

    control = run_script(SCAFFOLD, *common, env=env)
    assert control.returncode == 2, control.stdout + control.stderr
    assert "pin-unreadable" in control.stderr
    assert log.read_text(encoding=UTF8).startswith(
        "api repos/opensoft/openGlass")


def test_a_pair_that_collides_with_nothing_still_scaffolds(tmp_path):
    """Beside the shape, not over it: `project` beside `project.yaml`, and
    `scripts/code` among the shape's own scripts."""
    remotes = tmp_path / "remotes"
    result = run_script(SCAFFOLD, *BASE_ARGS, "--spec-path", "project",
                        "--code-path", "scripts/code",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 0, result.stdout + result.stderr
    tree = git("ls-tree", "-r", "main",
               cwd=remotes / f"{PROJECT}.git").stdout.splitlines()
    gitlinks = sorted(line.split("\t")[1] for line in tree
                      if line.startswith("160000"))
    assert gitlinks == ["project", "scripts/code"]
    paths = {line.split("\t")[1] for line in tree}
    assert {"project.yaml", "scripts/bootstrap.py"} <= paths
