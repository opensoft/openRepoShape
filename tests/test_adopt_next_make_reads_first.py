# SPDX-License-Identifier: Apache-2.0
"""`execute`'s NEXT runs the shape's bootstrap where GNU make reads another
file at the root (#1047).

GNU make reads the first it finds of `GNUmakefile`, `makefile` and
`Makefile`, and only that one. A source that keeps `GNUmakefile` or
`makefile` in the root has the shape's `Makefile` beside it, as the root's
`Makefile` or as `shape/Makefile`, and `make` at the root reads the source's
file and never the shape's. NEXT printed `make bootstrap` there, which exits 2
in the clone with `No rule to make target 'bootstrap'` (#977's writer, w977,
measured it). Where the source also kept a `Makefile`, NEXT's command was
`python3 scripts/bootstrap.py`, which runs, but its NOTE said the shape's
targets arrive once the two `Makefile`s are merged, and `make bootstrap`
after that merge still has no rule (r1046's NIT-B on #1046, which is
#1048's third box). And where the source kept its own `scripts/bootstrap.py`
too, the NOTE said to run `make bootstrap` after the merges, which reads
the same other file.

NEXT now prints `python3 scripts/bootstrap.py` wherever GNU make at the root
reads a file the source keeps, and its NOTE names that file in the words of
the Makefile follow-up (`_makefile_follow_up`), and says what it takes for
`make bootstrap` to run there. A root that keeps none of those files gets
the block it got before, byte for byte. Only the plan's root paths count: a
`GNUmakefile` the plan sends to the code leg, or drops, is no file at the
root, so NEXT keeps `make bootstrap` there, and it runs.

The end-to-end rows need `git filter-repo` and `make`, and skip without
them. No network and no GitHub: the legs are bare repositories on disk, and
`tests/conftest.py` keeps a `gh` guard first on PATH.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, load_without_bytecode, make_source_repo,
                      run_script, write_plan)
from test_adopt_contracts_dir import EDITS, TREE, needs_filter_repo
from test_adopt_e2e import (BOTH_ASIDE, kept_scripts, local_next, next_block,
                            pasted)
from test_adopt_make_reads_first import (disk_keeps_case, make, needs_make,
                                         own_makefile)

PROJECT = "Northwind"
SCRIPT = "scripts/bootstrap.py"


@pytest.fixture(scope="module")
def adopter():
    """`adopt-project.py` loaded as a module, for `_next_steps`."""
    return load_without_bytecode(ADOPT, "adopt_next_make_reads_first")


# --- the block, word for word ------------------------------------------------

#: The command NEXT prints wherever `make bootstrap` at the root does not
#: reach the shape's Makefile.
PYTHON = "    python3 scripts/bootstrap.py"
#: #480's NOTE, for a root that keeps only its own `Makefile`: unchanged.
OWN_MAKEFILE_NOTE = (
    "NOTE the root keeps its own Makefile and the shape's is shape/Makefile, "
    "so `make bootstrap` and the shape's other make targets arrive only once "
    "the follow-up merges the two; `python3 scripts/bootstrap.py` is what "
    "`make bootstrap` runs.")
#: #493's NOTE, for a root that keeps only its own `scripts/bootstrap.py`:
#: unchanged.
OWN_SCRIPT_NOTE = (
    "NOTE the root keeps its own scripts/bootstrap.py, and the shape's is "
    "shape/scripts/bootstrap.py, so neither `make bootstrap` nor `python3 "
    "scripts/bootstrap.py` runs the shape's bootstrap yet: merge "
    "shape/scripts/bootstrap.py into scripts/bootstrap.py first, and then "
    "run `make bootstrap`.")
RUNS = ("; `python3 scripts/bootstrap.py` is what the shape's `make "
        "bootstrap` runs.")


def reads(name: str) -> str:
    """The clause naming the source's file GNU make reads at the root, as
    the Makefile follow-up names it."""
    return (f"GNU make at the root reads the source's `{name}`, the first of "
            "`GNUmakefile`, `makefile` and `Makefile` it finds, so `make "
            "bootstrap` and the shape's other make targets run there only "
            f"once `{name}` has them, or includes a Makefile that does")


def only_it(name: str) -> str:
    """The NOTE where the shape's Makefile is the root's `Makefile`."""
    return (f"NOTE the shape's Makefile is the root's `Makefile`, but "
            f"{reads(name)}{RUNS}")


def beside_own(name: str) -> str:
    """The NOTE where the source keeps a `Makefile` of its own as well."""
    return ("NOTE the root keeps its own Makefile and the shape's is "
            f"shape/Makefile, and {reads(name)}{RUNS}")


def script_aside(name: str, makefile: bool) -> str:
    """The NOTE where the source keeps its own `scripts/bootstrap.py`: no
    command, the merges first, then the command that runs the shape's."""
    if makefile:
        kept = ("its own Makefile and scripts/bootstrap.py, and the shape's "
                "are shape/Makefile and shape/scripts/bootstrap.py")
        merges = ("shape/Makefile into Makefile and "
                  "shape/scripts/bootstrap.py into scripts/bootstrap.py")
    else:
        kept = ("its own scripts/bootstrap.py, and the shape's is "
                "shape/scripts/bootstrap.py")
        merges = "shape/scripts/bootstrap.py into scripts/bootstrap.py"
    return (f"NOTE the root keeps {kept}, so neither `make bootstrap` nor "
            "`python3 scripts/bootstrap.py` runs the shape's bootstrap yet: "
            f"merge {merges} first, and then run `python3 "
            f"scripts/bootstrap.py`; {reads(name)}.")


#: `(what the root keeps, NEXT's lines after the clone, the file GNU make
#: reads first at the root on a disk that keeps case)`. `S` is the source's
#: own `scripts/bootstrap.py`, kept with `scripts/`.
ROWS = [
    pytest.param((), ["    make bootstrap"], "Makefile", id="none"),
    pytest.param(("Makefile",), [PYTHON, OWN_MAKEFILE_NOTE], "Makefile",
                 id="Makefile"),
    pytest.param(("makefile",), [PYTHON, only_it("makefile")], "makefile",
                 id="makefile"),
    pytest.param(("GNUmakefile",), [PYTHON, only_it("GNUmakefile")],
                 "GNUmakefile", id="GNUmakefile"),
    pytest.param(("makefile", "GNUmakefile"), [PYTHON, only_it("GNUmakefile")],
                 "GNUmakefile", id="makefile+GNUmakefile"),
    pytest.param(("Makefile", "makefile"), [PYTHON, beside_own("makefile")],
                 "makefile", id="Makefile+makefile"),
    pytest.param(("Makefile", "GNUmakefile"),
                 [PYTHON, beside_own("GNUmakefile")], "GNUmakefile",
                 id="Makefile+GNUmakefile"),
    pytest.param(("Makefile", "makefile", "GNUmakefile"),
                 [PYTHON, beside_own("GNUmakefile")], "GNUmakefile",
                 id="all-three"),
    pytest.param(("S",), [OWN_SCRIPT_NOTE], "Makefile", id="S"),
    pytest.param(("S", "Makefile"), [BOTH_ASIDE], "Makefile", id="S+Makefile"),
    pytest.param(("S", "GNUmakefile"), [script_aside("GNUmakefile", False)],
                 "GNUmakefile", id="S+GNUmakefile"),
    pytest.param(("S", "makefile"), [script_aside("makefile", False)],
                 "makefile", id="S+makefile"),
    pytest.param(("S", "Makefile", "GNUmakefile"),
                 [script_aside("GNUmakefile", True)], "GNUmakefile",
                 id="S+Makefile+GNUmakefile"),
]


def surviving(kept: tuple) -> list[str]:
    """The plan's root paths for `kept`, as `_leg_paths` lists them."""
    return ["README.md", *("scripts/" if name == "S" else name
                           for name in kept)]


def collisions(kept: tuple) -> list[tuple[str, str]]:
    """What the materializer reports on a disk that keeps case: the shape's
    `Makefile` and `scripts/bootstrap.py` go aside only where the source
    keeps that very name."""
    return [(path, f"shape/{path}")
            for path, held in (("Makefile", "Makefile" in kept),
                               (SCRIPT, "S" in kept)) if held]


def printed(adopter, capsys, kept: tuple) -> list[str]:
    """NEXT's lines after the clone line, as `execute` prints them."""
    adopter._next_steps({"assembly": PROJECT}, collisions(kept),
                        surviving=surviving(kept))
    lines = capsys.readouterr().out.splitlines()
    assert lines[:3] == ["", f"NEXT: review the pull request on {PROJECT}, "
                         "then", f"    git clone --recurse-submodules "
                         f"<{PROJECT} url>"], lines
    return lines[3:]


@pytest.mark.parametrize("kept, said, first", ROWS)
def test_next_runs_the_shapes_bootstrap_whatever_make_reads_first(
        adopter, capsys, kept, said, first):
    """Each row, word for word. Where GNU make at the root reads a file the
    source keeps other than its own `Makefile`, NEXT's command is `python3
    scripts/bootstrap.py`, or, where the source's own script is
    `scripts/bootstrap.py`, the command named after the merges; and the NOTE
    names that file. The rows that keep neither `GNUmakefile` nor
    `makefile` print what they printed before."""
    lines = printed(adopter, capsys, kept)
    assert lines == said
    assert "    make bootstrap" not in lines[:-1]
    if first in ("GNUmakefile", "makefile"):
        assert "    make bootstrap" not in lines
        assert f"GNU make at the root reads the source's `{first}`, the " \
            "first of" in lines[-1]
    else:
        assert "GNU make" not in "\n".join(lines)


@pytest.mark.parametrize("rows", [
    pytest.param(("MAKEFILE",), id="MAKEFILE"),
    pytest.param(("makefile.am", "Makefile.in", "GNUmakefile.bak"),
                 id="longer-names"),
    pytest.param(("legs/GNUmakefile", "tools/makefile"), id="below-the-root"),
])
def test_a_name_gnu_make_never_reads_at_the_root_keeps_make_bootstrap(
        adopter, capsys, rows):
    """`MAKEFILE` is no name GNU make reads where case is kept, and a longer
    name, or one the root keeps below it, is none of the three at the root,
    so the shape's `Makefile` is what `make` there reads. NEXT keeps `make
    bootstrap`."""
    adopter._next_steps({"assembly": PROJECT}, [],
                        surviving=["README.md", *rows])
    assert capsys.readouterr().out.splitlines()[3:] == ["    make bootstrap"]


@pytest.mark.parametrize("kept, said, first", ROWS)
def test_next_names_the_file_the_makefile_follow_up_names(
        adopter, capsys, kept, said, first):
    """One reading of the root: the file NEXT says GNU make reads is the one
    the plan's Makefile follow-up names, for the same root paths."""
    lines = printed(adopter, capsys, kept)
    follow_up = adopter._makefile_follow_up(set(surviving(kept)))
    for text in (follow_up, "\n".join(lines)):
        named = [name for name in ("GNUmakefile", "makefile")
                 if f"reads the source's `{name}`" in text]
        assert named == ([first] if first != "Makefile" else [])


# --- `execute`, end to end, and the clone NEXT makes -------------------------


def make_run(argv: list, cwd: Path) -> subprocess.CompletedProcess:
    """Run one printed command in `cwd`, as a person pastes it."""
    return subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False)


def tree_keeping(kept: tuple) -> dict:
    tree = {**TREE, **{name: own_makefile(name) for name in kept
                       if name != "S"}}
    if "S" in kept:
        tree[SCRIPT] = "print('THE SOURCE OWN BOOTSTRAP')\n"
    return tree


def executed_and_cloned(tmp_path: Path, kept: tuple, answer=None):
    """A real `execute` of a source that keeps `kept` in its root, and the
    clone NEXT's own clone line makes when it is pasted. `answer`, where
    given, edits the plan `plan` wrote before `execute` reads it. Returns
    NEXT's lines and the clone."""
    source = make_source_repo(tmp_path / "src" / "Thing", tree_keeping(kept),
                              edits=EDITS)
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    if answer is not None:
        answer(plan)
    remotes = tmp_path / "src" / "remotes"
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    lines = next_block(result.stdout)
    assert lines[:2] == local_next(source), result.stdout
    (tmp_path / "here").mkdir()
    cloned = pasted(lines[1], tmp_path / "here", remotes)
    assert cloned.returncode == 0, cloned.stdout + cloned.stderr
    return lines[2:], tmp_path / "here" / source.name


@needs_filter_repo
@needs_make
@pytest.mark.parametrize("kept, said, first",
                         [row for row in ROWS if row.values[2] != "Makefile"])
def test_the_printed_bootstrap_runs_in_the_clone_next_makes(
        tmp_path, kept, said, first):
    """The measurement, on a disk that keeps case. After a real `execute`,
    NEXT's lines are the row's; its own clone line, pasted, makes the clone;
    `make which` there prints the file the NOTE names, and `make -n
    bootstrap` has no rule, which is why NEXT does not print it.

    The command NEXT prints runs the shape's bootstrap there and exits 0.
    Where the source's own script is the root's, it runs once that script
    is merged, as the NOTE says (here the shape's replaces it).

    And the way out the NOTE names is real: once the file GNU make reads
    includes a Makefile holding the shape's targets (the root's `Makefile`,
    once the follow-up's merge is made where the source kept its own),
    `make -n bootstrap` runs the shape's recipe. The merge alone does not:
    that is what the NOTE said before."""
    if not disk_keeps_case(tmp_path):
        pytest.skip("this disk ignores case: it cannot hold the rows apart")
    lines, clone = executed_and_cloned(
        tmp_path, kept, kept_scripts if "S" in kept else None)
    assert lines == said, lines
    which = make(clone, "which")
    assert (which.returncode, which.stdout.strip()) == (0, first), \
        which.stderr
    unruled = make(clone, "-n", "bootstrap")
    assert unruled.returncode != 0, unruled.stdout
    assert "No rule to make target 'bootstrap'" in unruled.stderr

    if "S" in kept:
        shapes = (clone / "shape" / SCRIPT).read_bytes()
        (clone / SCRIPT).write_bytes(shapes)
        command = "python3 scripts/bootstrap.py"
    else:
        command = lines[0].strip()
    argv = shlex.split(command)
    assert argv[0] == "python3", command
    ran = make_run([sys.executable, *argv[1:]], clone)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert ran.stdout.rstrip().endswith("bootstrap ok"), ran.stdout

    if "Makefile" in kept:
        merged = (clone / "Makefile").read_text(encoding="utf-8") + (
            clone / "shape" / "Makefile").read_text(encoding="utf-8")
        (clone / "Makefile").write_text(merged, encoding="utf-8")
        after_the_merge = make(clone, "-n", "bootstrap")
        assert after_the_merge.returncode != 0, after_the_merge.stdout
    with (clone / first).open("a", encoding="utf-8") as handle:
        handle.write("include Makefile\n")
    included = make(clone, "-n", "bootstrap")
    assert included.returncode == 0, included.stderr
    assert included.stdout.strip().splitlines()[-1] == (
        "python3 scripts/bootstrap.py")


def sent_away(plan: Path, leg: str) -> None:
    """The plan's `GNUmakefile` answered `leg`, LF as `plan` wrote it."""
    text = plan.read_text(encoding="utf-8")
    sent = "  - path: GNUmakefile\n    leg: root\n"
    assert sent in text, text
    with plan.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.replace(sent, (
            f"  - path: GNUmakefile\n    leg: {leg}\n"
            "    resolution: \"a Makefile that only builds the code\"\n"),
            1))


@needs_filter_repo
@needs_make
@pytest.mark.parametrize("leg", ["code", "drop"])
def test_next_keeps_make_bootstrap_where_the_plan_sends_the_makefile_elsewhere(
        tmp_path, leg):
    """Only the root's paths count. The rule `root-project-makefile` sends a
    kept `GNUmakefile` to the root, and its reason says that moving a
    Makefile that only builds the implementation to the code leg "is a
    one-line edit of the plan". Where the plan sends it to the code leg, or
    drops it, the clone's root has no `GNUmakefile`, so GNU make there reads
    the shape's `Makefile`: NEXT keeps `make bootstrap`, and `make -n
    bootstrap` runs the shape's recipe. A NOTE naming a `GNUmakefile` the
    root does not have, and `python3` for `make`, is what `execute` printed
    when it was handed the code leg's and the dropped paths as well."""
    lines, clone = executed_and_cloned(
        tmp_path, ("GNUmakefile",), lambda plan: sent_away(plan, leg))
    assert lines == ["    make bootstrap"], lines
    assert not (clone / "GNUmakefile").exists()
    ran = make(clone, "-n", "bootstrap")
    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.strip().splitlines()[-1] == (
        "python3 scripts/bootstrap.py")
