# SPDX-License-Identifier: Apache-2.0
"""The Makefile follow-up names the root file GNU make reads first (#977).

#906 made the line say that a root `Makefile` the source keeps leaves the
block in `shape/Makefile`. It asks whether the source keeps `Makefile` byte
for byte (`_root_keeps`), and GNU make reads the first it finds of
`GNUmakefile`, `makefile` and `Makefile`, and only that one. So a source
that keeps `makefile` or `GNUmakefile` got "the root Makefile wires
`CONTRACTS_DIR`": the root's `Makefile` is the shape's, with the block, and
`make` there never reads it, so `make contracts-dir` answers `No rule to make
target` (r906's probe on #964, both names). And where the source keeps
`Makefile` beside one of them, the line said where the block waits and
nothing of the file `make` reads instead.

A disk that ignores case was never asked: there the source's `makefile` IS
`Makefile`, `place` finds the name taken, and the shape's goes beside it as
`shape/Makefile`, where the line said the root's `Makefile` holds it.

The line now says which file the shape's Makefile is written as, on each
disk, and names the source's file GNU make reads at the root wherever that
is not a `Makefile` the line already names. Each kept name in the rows below
has its own `which` target, so `make which` at the root of a real adoption
prints the name of the file GNU make read, and the line names that file.

Where the source keeps `Makefile` and `makefile` side by side (the rows
`Makefile+makefile` and `all-three`), the plan keeps a set of case twins in
the root. Since #1161 `check` names it as `plan-case-twins` on every disk and
exits 1, and `execute` refuses it before any leg exists, so those two rows ask
`check` for the finding beside the line and `execute` for its refusal, and
are in no clone: there is none to run `make` in.

README.md's sentence (#977's (b)) said "the root Makefile it materializes
exports `CONTRACTS_DIR`", untrue where the source keeps a `Makefile` of its
own. Its section is bound to the handbook's `adopt` section
(`tests/test_repo_hygiene.py`), whose marker moves with it.

The tests that run `execute` need `git filter-repo` and skip without it, and
the ones that run `make` skip without it. No network and no GitHub: the legs
are bare repositories on disk, and `tests/conftest.py` keeps a `gh` guard
first on PATH.
"""

from __future__ import annotations

import html
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, REPO, findings, git, load_without_bytecode,
                      make_source_repo, refused_before_any_leg, run_script,
                      write_plan)
from test_adopt_contracts_dir import (EDITS, MAKEFILE_FOLLOW_UP,
                                      OWN_MAKEFILE_FOLLOW_UP, PROJECT,
                                      SPEC_PATH, SPLIT_BRANCH, TREE,
                                      adopt_with_legs_mounted_away,
                                      contracts_dir_line, needs_filter_repo)
from test_adopt_printed_sentences import NAMES, entries_of, makefile_lines
from test_repo_hygiene import readme_fingerprint, readme_segments

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml  # noqa: E402

needs_make = pytest.mark.skipif(
    shutil.which("make") is None or sys.platform == "win32",
    reason="needs make, and a POSIX `$(CURDIR)` spelling")


@pytest.fixture(scope="module")
def adopter():
    """`adopt-project.py` loaded as a module, for its helpers."""
    return load_without_bytecode(ADOPT, "adopt_make_reads_first")


# --- the line, word for word -------------------------------------------------

#: What every form of the line says first, after whose Makefile it is.
WIRES = (
    "Makefile wires `CONTRACTS_DIR` to the `contracts/` of the spec leg, "
    "where the plan's `legs.spec_path` mounts it, and exports it, so the code "
    "leg's tooling takes the path from the environment instead of assuming "
    "it sits beside it")
SHAPES = f"the shape's {WIRES}"


def written_as(twin: str = "") -> str:
    """Where the shape's Makefile is written when the source keeps no
    `Makefile`: the root's `Makefile`, or, where the source keeps `twin`, a
    name a disk that ignores case reads as `Makefile`, `shape/Makefile`
    there."""
    if not twin:
        return "; it is written as the root's `Makefile`"
    return ("; it is written as the root's `Makefile`, or as "
            "`shape/Makefile` once case is ignored, as a macOS or Windows "
            f"disk does, where the source's `{twin}` is that path, until the "
            "two are merged")


def reads(name: str, joint: str = "; and") -> str:
    """The clause naming the source's file GNU make reads at the root."""
    return (f"{joint} GNU make at the root reads the source's `{name}`, the "
            "first of `GNUmakefile`, `makefile` and `Makefile` it finds, so "
            f"`make` there exports `CONTRACTS_DIR` only once `{name}` does, "
            "or includes a Makefile that does")


#: `(the root files the plan keeps, the line, the file GNU make reads first
#: at the root of a clone on a disk that keeps case)`.
ROWS = [
    pytest.param((), MAKEFILE_FOLLOW_UP, "Makefile", id="none"),
    pytest.param(("Makefile",), OWN_MAKEFILE_FOLLOW_UP, "Makefile",
                 id="Makefile"),
    pytest.param(("makefile",),
                 SHAPES + written_as("makefile") + reads("makefile"),
                 "makefile", id="makefile"),
    pytest.param(("GNUmakefile",),
                 SHAPES + written_as() + reads("GNUmakefile", ", but"),
                 "GNUmakefile", id="GNUmakefile"),
    pytest.param(("makefile", "GNUmakefile"),
                 SHAPES + written_as("makefile") + reads("GNUmakefile"),
                 "GNUmakefile", id="makefile+GNUmakefile"),
    pytest.param(("Makefile", "makefile"),
                 OWN_MAKEFILE_FOLLOW_UP + reads("makefile"),
                 "makefile", id="Makefile+makefile"),
    pytest.param(("Makefile", "GNUmakefile"),
                 OWN_MAKEFILE_FOLLOW_UP + reads("GNUmakefile"),
                 "GNUmakefile", id="Makefile+GNUmakefile"),
    pytest.param(("Makefile", "makefile", "GNUmakefile"),
                 OWN_MAKEFILE_FOLLOW_UP + reads("GNUmakefile"),
                 "GNUmakefile", id="all-three"),
]

#: The code of the finding #1161 adds and of `execute`'s refusal, and what
#: `check` says first of the one set the rows that keep `Makefile` and
#: `makefile` side by side hold.
PLAN_CASE_TWINS = "plan-case-twins"
TWINS_FINDING = (
    f"FINDING {PLAN_CASE_TWINS}: the plan keeps 1 set of case twins in the "
    "assembly root, 2 paths, the paths of a set differing only in case, or "
    "one naming in another case a folder above another: `Makefile` and "
    "`makefile`. A disk that ignores case")


def keeps_twins(kept: tuple) -> bool:
    """Whether the source keeps `Makefile` and `makefile` side by side."""
    return {"Makefile", "makefile"} <= set(kept)


#: The rows that keep both names, which `check` and `execute` meet as case
#: twins, by their kept names; and the rows `execute` splits that keep a
#: `Makefile` or one of the other two names, which a clone can run `make` in.
TWIN_ROWS = [pytest.param(row.values[0], id=row.id)
             for row in ROWS if keeps_twins(row.values[0])]
CLONE_ROWS = [row for row in ROWS[1:] if not keeps_twins(row.values[0])]

#: `(path, leg)` rows no shipped rule writes, which a `--path-policy` rule can
#: (a person's answer in the plan changes no follow-up): `MAKEFILE` kept in
#: the root, a name GNU make never reads where case is kept and one a disk
#: that ignores case takes for `Makefile`; and `makefile` and `GNUmakefile`
#: sent to the legs, which leaves the root nothing GNU make reads but the
#: shape's.
ANSWERED = [
    pytest.param((("MAKEFILE", "root"),), SHAPES + written_as("MAKEFILE"),
                 id="MAKEFILE"),
    pytest.param((("makefile", "code"), ("GNUmakefile", "spec")),
                 MAKEFILE_FOLLOW_UP, id="sent-to-legs"),
]


def follow_ups_of(adopter, monkeypatch, rows) -> list:
    """`follow_ups_for` over plan entries made of `(path, leg)` rows, beside
    a `contracts/` the spec leg holds, as `plan` calls it."""
    # The read-across lines are the `git grep`'s, which this asks nothing of.
    monkeypatch.setattr(adopter, "cross_leg_references",
                        lambda source, entries: [])
    entries = entries_of(("contracts/", "spec"), ("src/", "code"), *rows)
    return adopter.follow_ups_for(None, entries, NAMES,
                                  adopter._predict_collisions(entries))


@pytest.mark.parametrize("kept, said, first", ROWS)
def test_the_line_names_the_file_gnu_make_reads_first(
        adopter, monkeypatch, kept, said, first):
    """One line per plan, and it names the source's file GNU make reads
    before the shape's wherever that file is not the shape's `Makefile` or
    the source's own `Makefile`, which #906's line already names."""
    ups = follow_ups_of(adopter, monkeypatch,
                        [(name, "root") for name in kept])
    assert makefile_lines(ups) == [said]
    if first in ("makefile", "GNUmakefile"):
        assert f"reads the source's `{first}`, the first of" in said
    else:
        assert "GNU make" not in said


@pytest.mark.parametrize("rows, said", ANSWERED)
def test_a_name_only_a_disk_that_ignores_case_takes_for_makefile(
        adopter, monkeypatch, rows, said):
    """`MAKEFILE` is no name GNU make reads where case is kept, and the
    shape's `Makefile` is the root's there; where case is ignored `place`
    finds `Makefile` taken by it and writes the shape's to `shape/Makefile`.
    A name sent to a leg is in no root at all."""
    assert makefile_lines(follow_ups_of(adopter, monkeypatch, rows)) == [said]


@pytest.mark.parametrize("kept, said, first", ROWS)
def test_the_line_says_where_each_disk_writes_the_shapes_makefile(
        adopter, monkeypatch, kept, said, first):
    """One reading of the disk, `check`'s: `_KeptTree` answers for each disk
    whether the root holds `Makefile`, which is where `place` writes the
    shape's copy beside it, and the line says `shape/Makefile` for exactly
    the disks on which it does."""
    rows = [(name, "100644", name) for name in kept]
    held = {fold: adopter._KeptTree(rows, fold).holds("Makefile")
            for fold in (False, True)}
    line, = makefile_lines(follow_ups_of(
        adopter, monkeypatch, [(name, "root") for name in kept]))
    aside_where_case_is_kept = "so that block waits in `shape/Makefile`"
    aside_once_ignored = "or as `shape/Makefile` once case is ignored"
    assert (aside_where_case_is_kept in line) is held[False]
    assert (aside_once_ignored in line) is (held[True] and not held[False])
    assert ("the root Makefile wires" in line) is (
        not any(held.values()) and first == "Makefile")


# --- `plan` and `execute`, end to end ----------------------------------------

def own_makefile(name: str) -> str:
    """A root makefile the source keeps under `name`, with a `which` target
    that prints its own name: `make which` says which file GNU make read."""
    return (f"which:\n\t@echo {name}\n"
            "build:\n\t@echo the source's own build\n")


def tree_keeping(kept: tuple) -> dict:
    return {**TREE, **{name: own_makefile(name) for name in kept}}


def disk_keeps_case(directory: Path) -> bool:
    probe = directory / "Case-Probe"
    probe.write_text("", encoding="utf-8")
    return not (directory / "case-probe").exists()


@pytest.mark.parametrize("kept, said, first", ROWS[2:])
def test_plan_writes_the_line_and_check_prints_it(tmp_path, kept, said,
                                                  first):
    """The rules keep each of GNU make's three names in the root
    (`root-project-makefile`), so `plan` writes the line for the source as
    it is, and `check` prints it as the plan holds it. Where the source
    keeps `Makefile` and `makefile` side by side, `check` also names them as
    case twins (`plan-case-twins`) and exits 1, on every disk."""
    if not disk_keeps_case(tmp_path):
        pytest.skip("this disk ignores case: it cannot hold the rows apart")
    source = make_source_repo(tmp_path / "Thing", tree_keeping(kept),
                              edits=EDITS)
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    follow_ups = [str(item) for item in load_yaml(plan)["follow_ups"]]
    assert makefile_lines(follow_ups) == [said]
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    if keeps_twins(kept):
        found = [line for line in checked.stderr.splitlines()
                 if line.startswith("FINDING ")]
        assert checked.returncode == 1, checked.stderr + checked.stdout
        assert len(found) == 1 and found[0].startswith(TWINS_FINDING), found
    else:
        assert checked.returncode == 0, checked.stderr + checked.stdout
    assert f"  follow-up: {said}" in checked.stdout


@pytest.mark.parametrize("kept", TWIN_ROWS)
def test_execute_refuses_makefile_beside_makefile_before_any_leg(
        adopter, monkeypatch, tmp_path, kept):
    """A disk that ignores case holds the root's `Makefile` and `makefile`
    as one name, so `execute` refuses them on every disk, as it does any set
    of case twins (#1161), before it makes a leg: no bare repository, no
    clone of the assembly or a leg in the work directory, and no split
    branch in the source. Before #1161 the same source was split and
    verified on a disk that keeps case, which left all three."""
    if not disk_keeps_case(tmp_path):
        pytest.skip("this disk ignores case: it cannot hold the rows apart")
    source = make_source_repo(tmp_path / "Thing", tree_keeping(kept),
                              edits=EDITS)
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    assert [code for code, _ in findings(plan)] == [PLAN_CASE_TWINS]
    refusal = refused_before_any_leg(adopter, monkeypatch, plan, tmp_path)
    assert refusal.code == PLAN_CASE_TWINS
    assert "`Makefile` and `makefile`" in refusal.detail
    assert git("branch", "--list", SPLIT_BRANCH,
               cwd=source).stdout.strip() == ""
    assert not list((tmp_path / "work").glob(f"{PROJECT}*"))


def make(clone: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["make", "--no-print-directory", "-s", *args], cwd=str(clone),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False)


@needs_filter_repo
@needs_make
@pytest.mark.parametrize("kept, said, first", CLONE_ROWS)
def test_the_split_message_names_the_file_make_reads_in_the_clone(
        tmp_path, kept, said, first):
    """The measurement the line rests on, on a disk that keeps case. After a
    real `execute`, the split commit's message holds the line; `make which`
    at the root of a recursive clone prints the name of the file the line
    says GNU make reads; `make contracts-dir` there has no rule, for that
    file is the source's; and the block is in the file the line says the
    shape's Makefile is written as, where the same target prints the spec
    leg's `contracts/`. The rows that keep `Makefile` and `makefile` side by
    side are not here: `execute` refuses them (#1161)."""
    if not disk_keeps_case(tmp_path):
        pytest.skip("this disk ignores case: it cannot hold the rows apart")
    adopted = adopt_with_legs_mounted_away(tmp_path, by_hand=False,
                                           tree=tree_keeping(kept))
    message = " ".join(git("log", "-1", "--format=%B", SPLIT_BRANCH,
                           cwd=adopted["source"]).stdout.split())
    clone = adopted["clone"]
    # Each kept name is the source's bytes.
    for name in kept:
        assert (clone / name).read_text(encoding="utf-8").splitlines() == \
            own_makefile(name).splitlines()
    # The file GNU make reads, as `make` itself says, is the one the split
    # message names: the source's `Makefile` by #906's words, any other by
    # name.
    which = make(clone, "which")
    assert which.returncode == 0, which.stderr
    read = which.stdout.strip()
    if read == "Makefile":
        assert "the source keeps a Makefile of its own at the root" in message
        assert "GNU make" not in message
    else:
        assert f"GNU make at the root reads the source's `{read}`, the " \
            "first of" in message
    assert read == first
    assert said in message
    assert MAKEFILE_FOLLOW_UP not in message
    at_the_root = make(clone, "contracts-dir")
    assert at_the_root.returncode != 0, at_the_root.stdout
    assert "No rule to make target 'contracts-dir'" in at_the_root.stderr
    # Where the line says the shape's Makefile is: the root's `Makefile`
    # where the source keeps none of that name, and `shape/Makefile` where
    # it does.
    shapes = "shape/Makefile" if "Makefile" in kept else "Makefile"
    assert (clone / "shape" / "Makefile").is_file() is ("Makefile" in kept)
    block = (clone / shapes).read_text(encoding="utf-8")
    assert contracts_dir_line(block) == (
        f"CONTRACTS_DIR ?= $(CURDIR)/{SPEC_PATH}/contracts")
    in_the_shapes = make(clone, "-f", shapes, "contracts-dir")
    assert in_the_shapes.returncode == 0, in_the_shapes.stderr
    assert Path(in_the_shapes.stdout.strip()) == (
        clone.resolve() / SPEC_PATH / "contracts")


# --- README.md and the handbook (#977's (b)) ---------------------------------

ADOPTING = "Adopting an existing repository"

#: The sentence, in r906's words as its re-check corrected them, with
#: `Makefile` spelled as the file it is: a source that keeps `makefile` has
#: the shape's Makefile written as the root's `Makefile` on a disk that
#: keeps case.
SENTENCE = (
    "the shape's Makefile exports `CONTRACTS_DIR`, pointing at the "
    "`contracts/` of the spec leg where the plan mounts it "
    "(`$(CURDIR)/spec/contracts` by default); it is the root's Makefile, or, "
    "where the source keeps a `Makefile` of its own, `shape/Makefile`, which "
    "holds the export until a person merges the two.")


def segment(name: str) -> str:
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    (text,) = [text for title, text in readme_segments(readme)
               if title == name]
    return text


def test_readme_says_which_makefile_exports_contracts_dir():
    """It said "the root Makefile it materializes exports `CONTRACTS_DIR`",
    and where the source keeps a `Makefile` of its own the root's is the
    source's, untouched, and the export is in `shape/Makefile` only."""
    said = " ".join(segment(ADOPTING).split())
    assert SENTENCE in said
    assert "the root Makefile it materializes" not in said


def test_the_handbook_reads_the_sentence_as_it_now_stands():
    """The handbook's `adopt` section reads README.md \u00a7 Adopting an
    existing repository, and says what the sentence leans on: a shape file
    whose name the source holds, `Makefile` among them, is written under
    `shape/`. Its marker records the section as it now stands, so the page
    was read against the new sentence."""
    page = (REPO / "docs" / "handbook.html").read_text(encoding="utf-8")
    section = page.split('<section id="adopt">', 1)[1].split("</section>",
                                                              1)[0]
    marker = re.search(rf"<!-- reads README\.md \u00a7 {re.escape(ADOPTING)}: "
                       r"blob ([0-9a-f]{40}) -->", section)
    assert marker is not None
    assert marker.group(1) == readme_fingerprint(segment(ADOPTING))
    text = " ".join(html.unescape(re.sub(r"<[^>]+>", "", section)).split())
    assert ("A shape file whose name the source already holds \u2014 "
            "README.md, Makefile, .gitignore \u2014 is written under "
            "shape/") in text
