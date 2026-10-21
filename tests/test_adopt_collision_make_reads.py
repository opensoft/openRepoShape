# SPDX-License-Identifier: Apache-2.0
"""The Makefile's collision follow-up and the pinned `AGENTS-shape.md` name
the file GNU make reads first (#1048).

#977 and #1046 corrected the `CONTRACTS_DIR` line and README: GNU make reads
the first of `GNUmakefile`, `makefile` and `Makefile` it finds, and only that
one, so a source that keeps `makefile` or `GNUmakefile` has a root where
`make` never reads the shape's `Makefile`. Two sentences still made the claim
#977 corrects (r1046's NIT-B):

  * the collision follow-up for a kept `Makefile` said the shape's make
    targets "arrive only with that merge". Where the root also keeps a
    `GNUmakefile` or a `makefile`, `cat shape/Makefile >> Makefile` leaves
    `make -n bootstrap` at the root exiting 2, "No rule to make target
    'bootstrap'", for `make` reads the other file;
  * the pinned `AGENTS-shape.md` said, of a kept `Makefile`, that the block
    "waits in `shape/Makefile` until the two are merged", and of a kept
    `makefile` or `GNUmakefile` nothing.

Both name the file `make` reads first now. The collision follow-up is told it
by `_predict_collisions` (`reads_first`), from the plan's root paths as the
`CONTRACTS_DIR` line reads them; the pinned file is one text for every
project, so it names the three names, in the order the code reads them. Where
the root keeps only the source's `Makefile` the collision follow-up is what it
was, byte for byte (`tests/test_adopt_e2e.py` pins it).

The tests that run `execute` need `git filter-repo` and skip without it, and
the ones that run `make` skip without it. No network and no GitHub: the legs
are bare repositories on disk, and `tests/conftest.py` keeps a `gh` guard
first on PATH.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from conftest import ADOPT, REPO, git, load_without_bytecode
from test_adopt_contracts_dir import (SPEC_PATH, SPLIT_BRANCH,
                                      adopt_with_legs_mounted_away,
                                      needs_filter_repo)
from test_adopt_make_reads_first import (disk_keeps_case, make, needs_make,
                                         tree_keeping)
from test_adopt_printed_sentences import NAMES, entries_of, makefile_lines
from test_pinned_copy_text import ADOPTED_SENTENCES, TEMPLATE_AGENTS, flat

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402
from shape_materialize import GNU_MAKE_READS, SHAPE_MAKE_TARGETS  # noqa: E402


@pytest.fixture(scope="module")
def adopter():
    """`adopt-project.py` loaded as a module, for its helpers."""
    return load_without_bytecode(ADOPT, "adopt_collision_make_reads")


#: The shape's make targets, as the collision follow-up names them.
TARGETS = ", ".join(f"`{name}`" for name in SHAPE_MAKE_TARGETS)
#: How the collision follow-up for the Makefile begins.
MERGE_MAKEFILE = "merge shape/Makefile into Makefile: "
LISTED = (", ".join(f"`{name}`" for name in GNU_MAKE_READS[:-1])
          + f" and `{GNU_MAKE_READS[-1]}`")
#: The last sentence of that follow-up where the root keeps no file GNU make
#: reads before `Makefile`: the merge is all it takes (#480).
MERGE_IS_ENOUGH = (
    f"The shape's make targets ({TARGETS}) arrive only with that merge; "
    "until then `python3 scripts/bootstrap.py` is what `make bootstrap` runs")
MEANWHILE = ("; until then `python3 scripts/bootstrap.py` is what the "
             "shape's `bootstrap` target runs")
SCRIPT_ASIDE = (
    "; and the root's scripts/bootstrap.py is the source's own until "
    "shape/scripts/bootstrap.py is merged into it as well, so neither `make "
    "bootstrap` nor `python3 scripts/bootstrap.py` runs the shape's "
    "bootstrap before both merges are made")


def reads_instead(first: str, then: str) -> str:
    """The last sentence of that follow-up where the root keeps `first`,
    which GNU make reads before `Makefile`; `then` is how it ends."""
    return (f"GNU make at the root reads the source's `{first}`, the first of "
            f"{LISTED} it finds, so the shape's make targets ({TARGETS}) "
            f"reach `make` there only once `{first}` holds them, or includes "
            f"a Makefile that does, and not with that merge alone{then}")


#: `(the root paths the plan keeps, the Makefile collision follow-up's last
#: sentence, the file GNU make reads first: None where it is `Makefile`)`.
COLLISIONS = [
    pytest.param(("Makefile",), MERGE_IS_ENOUGH, None, id="Makefile"),
    pytest.param(("Makefile", "makefile"),
                 reads_instead("makefile", MEANWHILE), "makefile",
                 id="Makefile+makefile"),
    pytest.param(("Makefile", "GNUmakefile"),
                 reads_instead("GNUmakefile", MEANWHILE), "GNUmakefile",
                 id="Makefile+GNUmakefile"),
    pytest.param(("Makefile", "makefile", "GNUmakefile"),
                 reads_instead("GNUmakefile", MEANWHILE), "GNUmakefile",
                 id="all-three"),
    # `scripts/` kept too: the source's `scripts/bootstrap.py` is the root's,
    # and neither command runs the shape's bootstrap before both merges.
    pytest.param(
        ("Makefile", "scripts/"),
        f"The shape's make targets ({TARGETS}) arrive only with that merge"
        + SCRIPT_ASIDE.replace("; and", ", and", 1), None,
        id="Makefile+scripts"),
    pytest.param(("Makefile", "GNUmakefile", "scripts/"),
                 reads_instead("GNUmakefile", SCRIPT_ASIDE), "GNUmakefile",
                 id="Makefile+GNUmakefile+scripts"),
]


def collisions_of(adopter, *kept: str) -> list:
    """`_predict_collisions` over root entries for each path in `kept`."""
    return adopter._predict_collisions(
        entries_of(*[(path, "root") for path in kept]))


@pytest.mark.parametrize("kept, tail, first", COLLISIONS)
def test_the_makefile_collision_names_the_file_gnu_make_reads_first(
        adopter, kept, tail, first):
    """THE MEASURED CLAIM (#1048, r1046's NIT-B). "The shape's make targets
    arrive only with that merge" holds where the merged `Makefile` is the
    file `make` reads. Where the root keeps `GNUmakefile` or `makefile`
    beside it, `make` reads that one, so the follow-up names it, and does not
    say the merge brings the targets. Where the root keeps only the source's
    `Makefile`, the sentence is what it was, byte for byte."""
    (line,) = [item for item in collisions_of(adopter, *kept)
               if item.startswith(MERGE_MAKEFILE)]
    assert line.endswith(". " + tail), line
    assert ("arrive only with that merge" in line) is (first is None)
    assert (f"reads the source's `{first}`, the first of {LISTED} it finds"
            in line) is (first is not None)


@pytest.mark.parametrize("kept, tail, first", COLLISIONS)
def test_the_two_makefile_lines_of_one_plan_name_the_same_file(
        adopter, monkeypatch, kept, tail, first):
    """The follow-up that says which Makefile wires `CONTRACTS_DIR` (#977)
    and the collision follow-up beside it, in the same plan, name the same
    file `make` reads, or one says `make` reads `GNUmakefile` and the next
    that the merge brings it the targets."""
    monkeypatch.setattr(adopter, "cross_leg_references",
                        lambda source, entries: [])
    entries = entries_of(("contracts/", "spec"), ("src/", "code"),
                         *[(path, "root") for path in kept])
    ups = adopter.follow_ups_for(None, entries, NAMES,
                                 adopter._predict_collisions(entries))
    (wires,) = makefile_lines(ups)
    (collision,) = [item for item in ups if item.startswith(MERGE_MAKEFILE)]
    clause = f"GNU make at the root reads the source's `{first}`, the first of"
    assert (clause in wires) is (first is not None)
    assert (clause in collision) is (first is not None)


@pytest.mark.parametrize("kept", [
    pytest.param(("makefile",), id="makefile"),
    pytest.param(("GNUmakefile",), id="GNUmakefile"),
    pytest.param(("makefile", "GNUmakefile"), id="makefile+GNUmakefile"),
    pytest.param((), id="none"),
    pytest.param(("MAKEFILE",), id="MAKEFILE"),
])
def test_no_makefile_collision_where_the_source_keeps_no_makefile(
        adopter, kept):
    """These names do not collide with the shape's `Makefile` where case is
    kept: it is written as the root's, and the follow-up that says `make`
    reads another file is the `CONTRACTS_DIR` line's (#977)."""
    assert [item for item in collisions_of(adopter, *kept)
            if item.startswith(MERGE_MAKEFILE)] == []


def test_a_name_in_a_leg_is_not_the_file_make_reads_at_the_root(adopter):
    """The names come from the plan's ROOT paths: a `GNUmakefile` the plan
    sends to a leg is in no root, so the merge is all it takes."""
    entries = entries_of(("Makefile", "root"), ("GNUmakefile", "spec"),
                         ("makefile", "code"))
    (line,) = [item for item in adopter._predict_collisions(entries)
               if item.startswith(MERGE_MAKEFILE)]
    assert line.endswith(". " + MERGE_IS_ENOUGH)


def test_the_two_lists_of_the_names_gnu_make_reads_are_one(adopter):
    """The materializer's `collision_follow_up` and `adopt-project.py`'s
    lookup each hold the tuple, and it is GNU make's own order: two lists
    that differ is how one sentence names `makefile` first and the next
    `GNUmakefile`."""
    assert adopter.GNU_MAKE_READS == shape_materialize.GNU_MAKE_READS
    assert GNU_MAKE_READS == ("GNUmakefile", "makefile", "Makefile")


def test_the_pinned_agent_file_names_every_file_the_code_reads_first():
    """#1048's second sentence. "Where the source kept a Makefile of its own,
    that block waits in `shape/Makefile` until the two are merged" said a
    kept `Makefile` is what holds the block back, and left out the
    `GNUmakefile` and the `makefile` GNU make reads first. The pinned file
    names the three, in the order the code reads them, and every one the code
    checks before the shape's `Makefile`: a name added to the tuple fails
    here until the file names it. It stays a verbatim copy."""
    said = flat(TEMPLATE_AGENTS)
    assert ADOPTED_SENTENCES in said
    assert (f"GNU make reads the first of {LISTED} it finds, and only that "
            "one.") in said
    before = [name for name in GNU_MAKE_READS if name != "Makefile"]
    kept = " or ".join(f"a `{name}`" for name in before)
    assert f"Where the source kept {kept}, " in said
    assert "$(CURDIR)" not in said and "{{" not in said


# --- the sentences, held to what `make` does in a real adoption's clone ------

#: `(the files the source keeps, the file GNU make reads first at the root of
#: a clone on a disk that keeps case: None where it is `Makefile`)`.
CLONES = [
    pytest.param(("Makefile",), None, id="Makefile"),
    pytest.param(("makefile",), "makefile", id="makefile"),
    pytest.param(("GNUmakefile",), "GNUmakefile", id="GNUmakefile"),
    pytest.param(("makefile", "GNUmakefile"), "GNUmakefile",
                 id="makefile+GNUmakefile"),
    pytest.param(("Makefile", "makefile"), "makefile",
                 id="Makefile+makefile"),
    pytest.param(("Makefile", "GNUmakefile"), "GNUmakefile",
                 id="Makefile+GNUmakefile"),
    pytest.param(("Makefile", "makefile", "GNUmakefile"), "GNUmakefile",
                 id="all-three"),
]


def appended(path: Path, text: str) -> None:
    """`text` at the end of `path`, as `cat >>` leaves it."""
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def copied(clone: Path, name: str) -> Path:
    """A copy of the whole clone, so each experiment starts from it."""
    shutil.copytree(clone, clone.parent / name, symlinks=True)
    return clone.parent / name


@needs_filter_repo
@needs_make
@pytest.mark.parametrize("kept, first", CLONES)
def test_the_sentences_are_true_of_what_make_does_in_the_clone(
        tmp_path, kept, first):
    """r1046's measurement, taken for each kept name (#1048). After a real
    `execute`: the split message says the shape's make targets arrive with
    the merge exactly where `make -n bootstrap` exits 0 after `cat
    shape/Makefile >> Makefile`, and names the file `make` reads where it
    does not. The pinned `AGENTS-shape.md` is in the clone, and what it says
    of a `GNUmakefile` or a `makefile` is what `make` does: `make
    contracts-dir` has no rule at the root until that file holds the block,
    or includes a Makefile that does, and then it prints the spec leg's
    `contracts/`."""
    if not disk_keeps_case(tmp_path):
        pytest.skip("this disk ignores case: it cannot hold the rows apart")
    adopted = adopt_with_legs_mounted_away(tmp_path, by_hand=False,
                                           tree=tree_keeping(kept))
    clone = adopted["clone"]
    message = " ".join(git("log", "-1", "--format=%B", SPLIT_BRANCH,
                           cwd=adopted["source"]).stdout.split())
    assert ADOPTED_SENTENCES in flat(clone / "AGENTS-shape.md")
    shapes = "shape/Makefile" if "Makefile" in kept else "Makefile"
    # Nothing at the root has the targets before an edit.
    assert make(clone, "-n", "bootstrap").returncode != 0
    assert make(clone, "-n", "contracts-dir").returncode != 0
    if "Makefile" in kept:
        # THE MERGE THE FOLLOW-UP ASKS FOR.
        appended(clone / "Makefile", (clone / shapes).read_text(
            encoding="utf-8"))
        brought = make(clone, "-n", "bootstrap")
        assert (brought.returncode == 0) is (first is None), (
            brought.stdout + brought.stderr)
        arrive = (f"The shape's make targets ({TARGETS}) arrive only with "
                  "that merge")
        assert (arrive in message) is (first is None)
        # Named once by the `CONTRACTS_DIR` line and once by the collision's.
        assert message.count(
            f"GNU make at the root reads the source's `{first}`, the "
            "first of") == (0 if first is None else 2)
        # `Makefile` now has the targets: `make -f` reads it.
        named = make(clone, "-f", "Makefile", "-n", "bootstrap")
        assert named.returncode == 0, named.stdout + named.stderr
    else:
        assert "make targets" not in message
    if first is not None:
        # THE FILE `make` READS: it holds the block, or includes a Makefile
        # that does.
        merged = copied(clone, "holds")
        appended(merged / first, (merged / shapes).read_text(
            encoding="utf-8"))
        including = copied(clone, "includes")
        appended(including / first, "\ninclude Makefile\n")
        for fixed in (merged, including):
            assert make(fixed, "-n", "bootstrap").returncode == 0
            printed = make(fixed, "contracts-dir")
            assert printed.returncode == 0, printed.stderr
            assert Path(printed.stdout.strip()) == (
                fixed.resolve() / SPEC_PATH / "contracts")
