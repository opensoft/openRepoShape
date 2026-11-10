# SPDX-License-Identifier: Apache-2.0
"""A kept `Makefile/` DIRECTORY is no Makefile of the source's own (#1314).

`_root_keeps({"Makefile/"}, "Makefile")` is True, and rightly: the
directory takes the name, so `place` finds it there (`Path.exists()`) and
writes the shape's `Makefile` beside it as `shape/Makefile`, as it does
beside a kept `README.md/`, and `_predict_collisions` must name that copy.
But the words read it as a Makefile of the source's own:

  * the `CONTRACTS_DIR` line said "the source keeps a Makefile of its own at
    the root, so that block waits in `shape/Makefile` until the two are
    merged";
  * the collision line said "merge shape/Makefile into Makefile", and that
    the shape's make targets "arrive only with that merge";
  * NEXT's NOTE said they "arrive only once the follow-up merges the two";
  * and the split commit's message, which is also the pull request's body,
    carried the first two.

GNU make 4.3 at such a root exits 2 with `make: *** Makefile: Is a
directory.  Stop.`, and nothing merges a Makefile into a directory. Each
surface now says GNU make stops at the directory, in the words a kept
`GNUmakefile/` (#1207) and a kept `makefile/` (#1312) get, and none names a
merge of the Makefile. `_root_keeps` is unchanged: every other shape path
kept as a directory of its name gives the line it gave, and a kept
`Makefile` FILE reads as before.

And removing the directory is not enough (RV1314's SHOULD-1): the shape's
copy is at `shape/Makefile`, so with the directory gone `make bootstrap`
says `No rule to make target 'bootstrap'` until the copy is moved to
`Makefile`. Each surface says both, and the collision line says what
`update-shape.py check` then reports of the copy's pin row, `merged-away`,
as it says of a merged file. A real adoption's clone is taken through the
three steps below.

The tests that run `execute` need `git filter-repo` and skip without it, and
the ones that run `make` skip without it. No network and no GitHub: the legs
are bare repositories on disk, and `tests/conftest.py` keeps a `gh` guard
first on PATH.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, REPO, git, load_without_bytecode,
                      make_source_repo, printed_follow_ups, run_script,
                      write_plan)
from test_adopt_contracts_dir import (EDITS, OWN_MAKEFILE_FOLLOW_UP, PROJECT,
                                      SPLIT_BRANCH, TREE, needs_filter_repo)
from test_adopt_e2e import local_next, next_block, pasted
from test_adopt_make_bootstrap_followups import (COMMAND, EXPORTS, HEAD,
                                                 RUN_THERE, RUNS, TEMPLATE,
                                                 needs_make, next_said, stops)
from test_adopt_make_reads_first import (SHAPES, follow_ups_of, reads,
                                         stops_at, written_as)
from test_adopt_printed_sentences import entries_of, makefile_lines
from test_update_shape import next_line_of

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402


@pytest.fixture(scope="module")
def adopter():
    """`adopt-project.py` loaded as a module, for its helpers."""
    return load_without_bytecode(ADOPT, "adopt_kept_makefile_directory")


# --- the words, word for word ------------------------------------------------

#: Where the `CONTRACTS_DIR` line says the shape's Makefile is written beside
#: a kept `Makefile/`: in #1312's words for a kept `makefile/`, "where the
#: source's directory ... is that path", and with no merge.
PLACED = ("; it is written as `shape/Makefile`, and not as the root's "
          "`Makefile`, where the source's directory `Makefile/` is that path")
#: What brings the shape's targets to the root of a kept `Makefile/`: the
#: directory's removal is not enough, for the copy is at `shape/Makefile`
#: (RV1314's SHOULD-1).
MOVED = " and `shape/Makefile` is moved to `Makefile`"
#: The same where GNU make stops at another directory first, which it stops
#: at next once that one is gone.
MOVED_BESIDE = " or `Makefile/`, and `shape/Makefile` is moved to `Makefile`"
#: The `CONTRACTS_DIR` line for a root that keeps only `Makefile/`.
CONTRACTS_DIR_LINE = SHAPES + PLACED + stops_at("Makefile") + MOVED

#: What the collision line says reaches `make` at the root.
TARGETS = "(`bootstrap`, `validate`, `pins`, `park`, `resume`)"
REACH = f"the shape's make targets {TARGETS} reach `make` there"
#: How the collision line for a kept `Makefile/` opens: the copy is the
#: shape's Makefile, beside the directory, and nothing is merged or removed.
BESIDE = ("shape/Makefile is the shape's Makefile: the source repository "
          "already has a directory `Makefile/` of that name, so the shape's "
          "copy was written beside it and NOTHING was overwritten")
#: What the collision line says of the copy's pin row once it is moved, in
#: the words a merged file's follow-up uses.
PIN_ROW = (". Once shape/Makefile is moved to Makefile, `update-shape.py "
           "check` reports its pin row `merged-away`, and `apply` drops the "
           "row")
#: The collision line for a root that keeps only `Makefile/`.
COLLISION = (f"{BESIDE}. {stops('Makefile', REACH)}{MOVED}; until then "
             f"{COMMAND} is what the shape's `make bootstrap` runs{PIN_ROW}")

#: NEXT's NOTE for a root that keeps only `Makefile/`.
NOTE = (f"NOTE the shape's Makefile is shape/Makefile, and "
        f"{stops('Makefile', RUN_THERE)}{MOVED}{RUNS}")

#: What a surface says where it reads a kept `Makefile/` as a Makefile the
#: shape's is merged into.
MERGE_SAID = ("until the two are merged", "merge shape/Makefile into Makefile",
              "merges the two", "arrive only with that merge",
              "both merges are made", "a Makefile of its own",
              "keeps its own Makefile", "Then remove shape/Makefile")

#: The paths `execute` writes the shape's copies beside, as `place` finds
#: them for a root that keeps only `Makefile/`.
ASIDE = [("Makefile", "shape/Makefile")]


def collision_line(adopter, kept) -> str:
    """The Makefile's collision line `_predict_collisions` gives for a root
    that keeps `kept`."""
    (line,) = [said for said in adopter._predict_collisions(
        entries_of(*[(path, "root") for path in kept]))
        if said.startswith(("merge shape/Makefile into", "shape/Makefile is"))]
    return line


def merge_said(text: str) -> list:
    return [said for said in MERGE_SAID if said in text]


# --- `plan`, `check` and `execute`, end to end -------------------------------

#: A rule above the shipped ones (the first match wins) that sends a
#: `Makefile/` directory to the root, which no shipped rule does: their
#: `root-project-makefile` names the FILE.
ROOT_RULE = ("rules:\n"
             "  - id: test-makefile-directory\n"
             "    paths:\n"
             "      - \"Makefile/**\"\n"
             "    leg: root\n"
             "    review: false\n"
             "    reason: The source's make rules stay in the root.\n")


def policy_keeping_the_directory(base: Path) -> Path:
    shipped = (REPO / "contracts" / "path-classification.yaml").read_text(
        encoding="utf-8")
    assert shipped.count("\nrules:\n") == 1
    policy = base / "policy.yaml"
    policy.write_text(shipped.replace("\nrules:\n", "\n" + ROOT_RULE, 1),
                      encoding="utf-8")
    return policy


@pytest.fixture(scope="module")
def adopted(tmp_path_factory) -> dict:
    """One real adoption of a source holding `Makefile/rules.mk`, kept in
    the root by a `--path-policy` rule: `plan`, `check`, and `execute
    --local-remote-dir`."""
    base = tmp_path_factory.mktemp("kept-makefile-directory")
    source = make_source_repo(
        base / "Thing",
        {**TREE, "Makefile/rules.mk": "build:\n\t@echo source build\n"},
        edits=EDITS)
    plan = base / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT, extra=(
        "--path-policy", str(policy_keeping_the_directory(base))))
    assert written.returncode == 0, written.stderr + written.stdout
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    executed = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                          "--local-remote-dir", str(base / "remotes"),
                          "--work-dir", str(base / "work"))
    return {"base": base, "source": source,
            "planned": printed_follow_ups(written.stdout),
            "checked": checked, "executed": executed}


def checked_follow_ups(adopted) -> list:
    checked = adopted["checked"]
    assert checked.returncode == 0, checked.stderr + checked.stdout
    return [line[len("  follow-up: "):]
            for line in checked.stdout.splitlines()
            if line.startswith("  follow-up: ")]


@needs_filter_repo
def test_check_says_make_stops_at_the_directory_in_the_contracts_dir_line(
        adopted):
    """`check`'s follow-up line, worked out from the plan as it stands, as
    `plan` printed it: the shape's Makefile is written as `shape/Makefile`
    beside the source's directory `Makefile/`, and GNU make stops at that
    directory. It said the block "waits in `shape/Makefile` until the two
    are merged"."""
    (line,) = makefile_lines(checked_follow_ups(adopted))
    assert line == CONTRACTS_DIR_LINE
    assert makefile_lines(adopted["planned"]) == [line]
    assert merge_said(line) == []


@needs_filter_repo
def test_check_says_make_stops_at_the_directory_in_the_collision_line(
        adopted):
    """`check`'s collision line names the copy as the shape's Makefile,
    beside the directory, and no merge of it, no removal of it, and no
    targets that "arrive only with that merge"."""
    (line,) = [said for said in checked_follow_ups(adopted)
               if said.startswith(("merge shape/Makefile into",
                                   "shape/Makefile is"))]
    assert line == COLLISION
    assert line in adopted["planned"]
    assert merge_said(line) == []


@needs_filter_repo
@needs_make
def test_next_names_python3_where_make_stops_at_a_kept_makefile_directory(
        adopted):
    """NEXT names `python3 scripts/bootstrap.py` and says GNU make stops at
    the directory, where its NOTE said the targets "arrive only once the
    follow-up merges the two". In the clone NEXT's own clone line makes,
    `make -n bootstrap` stops at `Makefile/` and the printed command, run
    with this test's interpreter, exits 0."""
    executed = adopted["executed"]
    assert executed.returncode == 0, executed.stderr + executed.stdout
    said = next_block(executed.stdout)
    assert said == [*local_next(adopted["source"]),
                    "    python3 scripts/bootstrap.py", NOTE], executed.stdout
    assert merge_said(" ".join(said)) == []
    here = adopted["base"] / "here"
    here.mkdir()
    cloned = pasted(said[1], here, adopted["base"] / "remotes")
    assert cloned.returncode == 0, cloned.stdout + cloned.stderr
    clone = here / adopted["source"].name
    assert (clone / "Makefile" / "rules.mk").is_file()
    assert (clone / "shape" / "Makefile").is_file()
    made = subprocess.run(["make", "-n", "bootstrap"], cwd=str(clone),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False)
    assert made.returncode == 2, made.stdout + made.stderr
    assert "Makefile: Is a directory." in made.stderr
    ran = subprocess.run([sys.executable, *said[2].split()[1:]],
                         cwd=str(clone), capture_output=True, text=True,
                         encoding="utf-8", errors="replace", check=False)
    assert ran.returncode == 0, ran.stdout + ran.stderr


@needs_filter_repo
def test_the_split_message_says_make_stops_at_the_directory(adopted):
    """The split commit's message, which is also the pull request's body,
    carries both lines as `check` printed them, and nothing that reads the
    directory as a Makefile the shape's is merged into."""
    executed = adopted["executed"]
    assert executed.returncode == 0, executed.stderr + executed.stdout
    message = " ".join(git("log", "-1", "--format=%B", SPLIT_BRANCH,
                           cwd=adopted["source"]).stdout.split())
    assert CONTRACTS_DIR_LINE in message
    assert COLLISION in message
    assert merge_said(message) == []


def make_in(clone: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["make", *args], cwd=str(clone),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False)


def update_shape(*args: str) -> subprocess.CompletedProcess:
    return run_script(REPO / "update-shape.py", *args)


@needs_filter_repo
@needs_make
def test_the_directory_gone_is_not_enough_and_the_moved_copy_is(adopted):
    """RV1314's SHOULD-1, in the clone NEXT's own clone line makes. `make -n
    bootstrap` stops at `Makefile/`; with the directory out of the way it
    says `No rule to make target 'bootstrap'`, for the shape's copy is still
    at `shape/Makefile` and the pin row is `unchanged`; and only once the
    copy is moved to `Makefile` does it print the shape's bootstrap, `make -n
    contracts-dir` answer, and `update-shape.py check` call the copy's row
    `merged-away`, as it does for a merged file, with the NEXT line `apply`
    that drops the row and leaves nothing to do. The lines say all of it:
    NEXT names the two steps, and `check`'s collision line names the row's
    fate, before the steps are taken."""
    executed = adopted["executed"]
    assert executed.returncode == 0, executed.stderr + executed.stdout
    said = next_block(executed.stdout)
    assert said[-1].endswith(f"{MOVED}{RUNS}"), said[-1]
    (collision,) = [line for line in checked_follow_ups(adopted)
                    if line.startswith("shape/Makefile is")]
    assert collision.endswith(PIN_ROW), collision
    here = adopted["base"] / "steps"
    here.mkdir()
    cloned = pasted(said[1], here, adopted["base"] / "remotes")
    assert cloned.returncode == 0, cloned.stdout + cloned.stderr
    clone = here / adopted["source"].name
    root_arguments = ("--root", str(clone), "--upstream", str(REPO))

    stopped = make_in(clone, "-n", "bootstrap")
    assert stopped.returncode == 2, stopped.stdout + stopped.stderr
    assert "Makefile: Is a directory." in stopped.stderr

    # The directory out of the way, its rules under a name of their own.
    git("mv", "--", "Makefile", "source-make-rules", cwd=clone)
    gone = make_in(clone, "-n", "bootstrap")
    assert gone.returncode == 2, gone.stdout + gone.stderr
    assert "No rule to make target 'bootstrap'" in gone.stderr
    unmoved = update_shape("check", *root_arguments)
    assert unmoved.returncode == 0, unmoved.stdout + unmoved.stderr
    assert "merged-away" not in unmoved.stdout, unmoved.stdout
    assert ["unchanged", "shape/Makefile"] in [
        line.split() for line in unmoved.stdout.splitlines()]

    # The copy moved to the name the directory held.
    git("mv", "--", "shape/Makefile", "Makefile", cwd=clone)
    git("commit", "-q", "-m", "Rename the directory away and put the shape's "
        "Makefile in its place", cwd=clone)
    ran = make_in(clone, "-n", "bootstrap")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert ran.stdout.strip() == "python3 scripts/bootstrap.py"
    answered = make_in(clone, "-n", "contracts-dir")
    assert answered.returncode == 0, answered.stdout + answered.stderr
    moved = update_shape("check", *root_arguments)
    assert moved.returncode == 1, moved.stdout + moved.stderr
    assert ["merged-away", "shape/Makefile"] in [
        line.split() for line in moved.stdout.splitlines()], moved.stdout
    assert "merged into Makefile and removed" in moved.stdout, moved.stdout

    line = next_line_of(moved.stdout)
    argv = shlex.split(line[len("NEXT  "):])
    assert argv[1:3] == ["update-shape.py", "apply"], line
    applied = update_shape(*argv[2:])
    assert applied.returncode == 0, applied.stdout + applied.stderr
    assert "  dropped  shape/Makefile " in applied.stdout, applied.stdout
    done = update_shape("check", *root_arguments)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "nothing to do" in done.stdout, done.stdout


# --- the words match the other two directories (#1207, #1312) ----------------

def clause(text: str, name: str) -> str:
    """The clause of `text` that says GNU make stops at the directory
    `name/`, with the name taken out."""
    opening = f"GNU make at the root stops at the source's directory `{name}/`"
    closing = "only once the root keeps no directory of that name"
    start = text.index(opening)
    end = text.index(closing, start) + len(closing)
    return (text[start:end].replace(f"`{name}/`", "`<name>/`")
            .replace(f"(`{name}: Is a directory.`)", "(`<name>: Is a "
                     "directory.`)"))


def test_the_words_match_a_kept_makefile_and_gnumakefile_directory(
        adopter, capsys):
    """For each surface, the clause a kept `Makefile/` gets is the one a
    kept `makefile/` gets (#1312) and a kept `GNUmakefile/` gets (#1207),
    with the name in it; the collision line, which only `Makefile/` has,
    says it of what reaches `make` there; and the `CONTRACTS_DIR` line
    names the directory in #1312's words for `makefile/`. Only a kept
    `Makefile/` goes on to say the shape's copy must be moved to `Makefile`
    too, for the copy of the other two is the root's `Makefile` already."""
    names = ("Makefile", "makefile", "GNUmakefile")
    lines = {name: adopter._makefile_follow_up({f"{name}/"})
             for name in names}
    notes = {name: next_said(adopter, capsys,
                             ASIDE if name == "Makefile" else [],
                             [f"{name}/", "src/"])
             for name in names}
    assert len({clause(lines[name], name) for name in names}) == 1, lines
    assert len({clause(notes[name], name) for name in names}) == 1, notes
    assert all(note.endswith(f"{RUNS}\n") for note in notes.values()), notes
    assert lines["Makefile"].endswith(MOVED), lines["Makefile"]
    assert notes["Makefile"].endswith(f"{MOVED}{RUNS}\n"), notes["Makefile"]
    assert collision_line(adopter, ["Makefile/"]).count(MOVED) == 1
    for name in ("makefile", "GNUmakefile"):
        assert MOVED not in lines[name] + notes[name], (lines[name],
                                                       notes[name])
    assert clause(collision_line(adopter, ["Makefile/"]), "Makefile") == \
        clause(lines["GNUmakefile"], "GNUmakefile").replace(EXPORTS, REACH)
    assert "where the source's directory `Makefile/` is that path" in \
        lines["Makefile"]
    assert "where the source's directory `makefile/` is that path" in \
        written_as("makefile", directory=True)
    assert "where the source's directory `makefile/` is that path" in \
        lines["makefile"]


# --- each root that keeps `Makefile/` ----------------------------------------

@pytest.mark.parametrize("kept, first", [
    pytest.param(("Makefile/",), "Makefile/", id="Makefile-dir"),
    pytest.param(("Makefile",), None, id="Makefile-file"),
    pytest.param(("Makefile/", "GNUmakefile"), "GNUmakefile",
                 id="Makefile-dir+GNUmakefile"),
    pytest.param(("Makefile/", "GNUmakefile/"), "GNUmakefile/",
                 id="Makefile-dir+GNUmakefile-dir"),
    pytest.param(("Makefile/", "makefile/"), "makefile/",
                 id="Makefile-dir+makefile-dir"),
    pytest.param(("Makefile/", "scripts/"), "Makefile/",
                 id="Makefile-dir+scripts"),
    pytest.param(("Makefile/rules.mk",), None, id="only-deeper-entries"),
    pytest.param(("MAKEFILE/",), None, id="MAKEFILE-dir"),
])
def test_make_finds_a_kept_makefile_directory_last(adopter, kept, first):
    """GNU make's order, file or directory: a `Makefile/` is what it finds
    where the root keeps neither other name, and a `Makefile` FILE is the
    one #906's words name, so none. A directory kept only through deeper
    entries is not seen (#1206's case 2, a known limit), and `MAKEFILE/` is
    no name GNU make looks for where case is kept.

    `Makefile/` beside `makefile/` is a root `check` refuses, as
    `plan-case-twins` (the two paths differ only in case), and `execute`
    refuses it before any leg exists (measured, RV1314's NIT-5): only the
    unit surfaces are pinned for it here, which `check` never prints."""
    assert adopter._make_reads_first(set(kept)) == first


@pytest.mark.parametrize("kept, stop", [
    pytest.param(("Makefile/",), "Makefile", id="alone"),
    pytest.param(("Makefile/", "GNUmakefile"), None, id="beside-GNUmakefile"),
    pytest.param(("Makefile/", "GNUmakefile/"), "GNUmakefile",
                 id="beside-GNUmakefile-dir"),
    pytest.param(("Makefile/", "makefile/"), "makefile",
                 id="beside-makefile-dir"),
    pytest.param(("Makefile/", "scripts/"), "Makefile", id="beside-scripts"),
])
def test_no_surface_reads_a_kept_makefile_directory_as_a_makefile(
        adopter, monkeypatch, capsys, kept, stop):
    """Beside whatever else the root keeps, no surface says the shape's
    Makefile is merged into the directory, and the `CONTRACTS_DIR` line and
    NEXT say GNU make stops at the directory it finds first, where that is
    one. Where it is `Makefile/`, the collision line says it too.

    `Makefile/` beside `makefile/` is a root `check` refuses, as
    `plan-case-twins`, and `execute` refuses it before any leg exists
    (measured, RV1314's NIT-5): that row pins the unit surfaces alone."""
    ups = follow_ups_of(adopter, monkeypatch,
                        [(path, "root") for path in kept])
    (line,) = makefile_lines(ups)
    collision = collision_line(adopter, kept)
    aside = ASIDE + ([("scripts/bootstrap.py", "shape/scripts/bootstrap.py")]
                     if "scripts/" in kept else [])
    note = next_said(adopter, capsys, aside, list(kept))
    for said in (line, collision, note):
        assert merge_said(said) == [], said
    assert PLACED in line
    assert collision.startswith(f"{BESIDE}. "), collision
    assert note.startswith(HEAD), note
    if stop:
        stopped = f"stops at the source's directory `{stop}/`"
        assert stopped in line and stopped in note, (line, note)
        moved = MOVED if stop == "Makefile" else MOVED_BESIDE
        assert moved in line and moved in note, (line, note)
        if stop == "Makefile":
            # Beside another directory the collision line says GNU make
            # "reads" it, which #1240's item B is to correct: no row pins
            # that, as #1207's review asked.
            assert stopped in collision, collision


def test_beside_its_own_script_only_the_scripts_merge_comes_first(
        adopter, capsys):
    """Where the root keeps `scripts/` too, the script's merge is the one
    named, and NEXT names `python3 scripts/bootstrap.py` after it, as it
    does beside a kept `GNUmakefile/` (#1207's review, SHOULD-1); the
    collision line says what runs until then in the words it uses where
    `make` reads another file (#1105)."""
    script = ("scripts/bootstrap.py", "shape/scripts/bootstrap.py")
    assert next_said(adopter, capsys, [*ASIDE, script],
                     ["Makefile/", "scripts/"]) == (
        f"{HEAD}NOTE the root keeps its own scripts/bootstrap.py, and the "
        "shape's is shape/scripts/bootstrap.py, so neither `make bootstrap` "
        "nor `python3 scripts/bootstrap.py` runs the shape's bootstrap yet: "
        "merge shape/scripts/bootstrap.py into scripts/bootstrap.py first, "
        f"and then run {COMMAND}; {stops('Makefile', RUN_THERE)}{MOVED}.\n")
    assert collision_line(adopter, ["Makefile/", "scripts/"]) == (
        f"{BESIDE}. {stops('Makefile', REACH)}{MOVED}; and the root's "
        "scripts/bootstrap.py is the source's own until "
        "shape/scripts/bootstrap.py is merged into it as well, so neither "
        "`make bootstrap` nor `python3 scripts/bootstrap.py` runs the "
        f"shape's bootstrap until then, and then {COMMAND} runs it{PIN_ROW}")


def test_a_gnumakefile_beside_it_is_what_make_reads(adopter, capsys):
    """GNU make reads a kept `GNUmakefile` and never reaches `Makefile/`, so
    each surface says what it says of that file, as beside a kept
    `Makefile`, and names the directory only as where the shape's Makefile
    is written beside."""
    kept = {"Makefile/", "GNUmakefile"}
    assert adopter._makefile_follow_up(kept) == (
        SHAPES + PLACED + reads("GNUmakefile"))
    assert next_said(adopter, capsys, ASIDE, sorted(kept)) == (
        f"{HEAD}    python3 scripts/bootstrap.py\n"
        "NOTE the shape's Makefile is shape/Makefile, and GNU make at the "
        "root reads the source's `GNUmakefile`, the first of `GNUmakefile`, "
        f"`makefile` and `Makefile` it finds, so {RUN_THERE} only once "
        f"`GNUmakefile` has them, or includes a Makefile that does{RUNS}\n")
    assert collision_line(adopter, sorted(kept)) == (
        f"{BESIDE}. GNU make at the root reads the source's `GNUmakefile`, "
        "the first of `GNUmakefile`, `makefile` and `Makefile` it finds, so "
        f"{REACH} only once `GNUmakefile` has them, or includes a Makefile "
        f"that does; until then {COMMAND} is what the shape's `make "
        "bootstrap` runs")


@pytest.mark.parametrize("name", ["GNUmakefile", "makefile"])
def test_beside_another_directory_both_conditions_are_named(adopter, capsys,
                                                            name):
    """GNU make stops at `name/` first, and at `Makefile/` once that one is
    gone, and with both gone the shape's copy is still at `shape/Makefile`,
    so the `CONTRACTS_DIR` line and NEXT name both directories and the move
    (RV1314's SHOULD-1). The collision line beside such a directory says
    GNU make "reads" it, #1240's item B, and is not pinned here.

    `makefile/` beside `Makefile/` is a root `check` refuses, as
    `plan-case-twins`, and `execute` refuses it before any leg exists
    (measured, RV1314's NIT-5): that row pins the unit surfaces alone."""
    kept = {"Makefile/", f"{name}/"}
    assert adopter._makefile_follow_up(kept) == (
        SHAPES + PLACED + stops_at(name) + MOVED_BESIDE)
    assert next_said(adopter, capsys, ASIDE, sorted(kept)) == (
        f"{HEAD}    python3 scripts/bootstrap.py\n"
        f"NOTE the shape's Makefile is shape/Makefile, and "
        f"{stops(name, RUN_THERE)}{MOVED_BESIDE}{RUNS}\n")


def top_level_shape_paths() -> list:
    """The shape's own root paths that sit at the top of the root, other than
    `Makefile`: each the name of a directory a source may keep."""
    return sorted(path for path in shape_materialize.assembly_root_paths()
                  if "/" not in path and path != "Makefile")


def test_the_top_level_shape_paths_are_the_ones_swept():
    """The row below is no empty sweep: `README.md`, `.gitignore`,
    `.gitattributes`, `AGENTS.md`, `CLAUDE.md`, `AGENTS-shape.md` and
    `project.yaml` are the top-level paths the shape writes."""
    paths = top_level_shape_paths()
    assert len(paths) >= 7 and {"README.md", ".gitignore"} <= set(paths)


@pytest.mark.parametrize("path", top_level_shape_paths())
def test_only_the_makefiles_follow_up_reads_a_directory(adopter, path):
    """A directory kept at any other top-level shape path's name is told what
    a file there is (#1314): `directory` is read for the Makefile alone, and
    `_predict_collisions` passes it for every path whose directory the root
    keeps. It was `directory = bool(directory)` that no row killed, RV1314's
    mutant M5."""
    as_a_file = adopter._predict_collisions(entries_of((path, "root")))
    as_a_directory = adopter._predict_collisions(
        entries_of((f"{path}/", "root")))
    assert len(as_a_file) == 1, as_a_file
    assert as_a_directory == as_a_file


# --- a kept `Makefile` FILE, and the names GNU make never looks for ----------

@pytest.mark.parametrize("kept, merged", [
    pytest.param("Makefile", True, id="a-file"),
    pytest.param("Makefile/", False, id="a-directory"),
])
def test_only_a_kept_makefile_file_is_merged_into(adopter, monkeypatch,
                                                  capsys, kept, merged):
    """A kept `Makefile` FILE is what the shape's is merged into, in #906's,
    #480's and the collision line's words as they were; a kept DIRECTORY
    `Makefile/` is none, and GNU make stops at it instead."""
    (line,) = makefile_lines(follow_ups_of(adopter, monkeypatch,
                                           [(kept, "root")]))
    collision = collision_line(adopter, [kept])
    note = next_said(adopter, capsys, ASIDE, [kept])
    assert (line == OWN_MAKEFILE_FOLLOW_UP) is merged
    assert collision.startswith(
        "merge shape/Makefile into Makefile: the source repository already "
        "has that name") is merged
    assert ("arrive only once the follow-up merges the two" in note) is merged
    stopped = "stops at the source's directory `Makefile/`"
    for said in (line, collision, note):
        assert (stopped in said) is (not merged), said


@pytest.mark.parametrize("name", ["MAKEFILE", "MakeFile"])
def test_a_directory_make_never_looks_for_gets_no_clause(adopter, name):
    """#1312 left `MAKEFILE/` and `MakeFile/` to this issue. Where case is
    kept GNU make looks for neither and reads the shape's `Makefile`, and
    where it is ignored, whether it reads a name by its case is its build's
    to say: the line names the directory as the path a disk that ignores
    case takes for `Makefile`, as #1312 words it, and says nothing of GNU
    make, or of a merge."""
    line = adopter._makefile_follow_up({f"{name}/"})
    assert line == SHAPES + written_as(name, directory=True)
    assert "GNU make" not in line


@needs_make
def test_make_needs_each_directory_gone_and_the_copy_moved(adopter,
                                                          tmp_path):
    """The measurement behind "or `Makefile/`, and `shape/Makefile` is moved
    to `Makefile`" (RV1314's SHOULD-1), with the template's own `Makefile` as
    the shape's copy at `shape/Makefile`: GNU make stops at `GNUmakefile/`;
    with that gone, at `Makefile/`; with both gone, `No rule to make target
    'bootstrap'`; and it prints the shape's bootstrap only once the copy is
    moved to `Makefile`. The `CONTRACTS_DIR` line names those conditions."""
    assert adopter._makefile_follow_up({"Makefile/", "GNUmakefile/"}
                                       ).endswith(MOVED_BESIDE)
    for name in ("GNUmakefile", "Makefile"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "rules.mk").write_text("build:\n",
                                                  encoding="utf-8")
    (tmp_path / "shape").mkdir()
    (tmp_path / "shape" / "Makefile").write_bytes(
        (TEMPLATE / "Makefile").read_bytes())

    def said_by_make() -> subprocess.CompletedProcess:
        return make_in(tmp_path, "-n", "bootstrap")

    first = said_by_make()
    assert first.returncode == 2 and "GNUmakefile: Is a directory." in \
        first.stderr, first.stdout + first.stderr
    (tmp_path / "GNUmakefile").rename(tmp_path / "source-gnu-rules")
    second = said_by_make()
    assert second.returncode == 2 and "Makefile: Is a directory." in \
        second.stderr, second.stdout + second.stderr
    (tmp_path / "Makefile").rename(tmp_path / "source-make-rules")
    third = said_by_make()
    assert third.returncode == 2 and "No rule to make target 'bootstrap'" in \
        third.stderr, third.stdout + third.stderr
    (tmp_path / "shape" / "Makefile").rename(tmp_path / "Makefile")
    fourth = said_by_make()
    assert fourth.returncode == 0, fourth.stdout + fourth.stderr
    assert fourth.stdout.strip() == "python3 scripts/bootstrap.py"


@needs_make
def test_make_stops_at_a_kept_makefile_directory(tmp_path):
    """The measurement the words rest on, with the template's own
    `Makefile` as the shape's copy at `shape/Makefile`: beside a kept
    `Makefile/`, `make -n bootstrap` exits 2 at the directory; with a
    `GNUmakefile` that includes the copy, GNU make reads that file first,
    never reaches the directory, and prints the shape's recipe."""
    (tmp_path / "Makefile").mkdir()
    (tmp_path / "Makefile" / "rules.mk").write_text("build:\n",
                                                    encoding="utf-8")
    (tmp_path / "shape").mkdir()
    (tmp_path / "shape" / "Makefile").write_bytes(
        (TEMPLATE / "Makefile").read_bytes())

    def make() -> subprocess.CompletedProcess:
        return subprocess.run(["make", "-n", "bootstrap"], cwd=str(tmp_path),
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace", check=False)

    stopped = make()
    assert stopped.returncode == 2, stopped.stdout + stopped.stderr
    assert "Makefile: Is a directory." in stopped.stderr
    (tmp_path / "GNUmakefile").write_text("include shape/Makefile\n",
                                          encoding="utf-8")
    included = make()
    assert included.returncode == 0, included.stdout + included.stderr
    assert included.stdout.strip() == "python3 scripts/bootstrap.py"
