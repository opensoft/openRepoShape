# SPDX-License-Identifier: Apache-2.0
"""`shape-doctor.py`'s `pin_restore`: the copies a conflicted shape pin's
NEXT takes whole, and a leg pin put back from before its own bump (#547).

L2-8, PROVE AND TAKE (Brett Heap, 2026-10-14T23:54:30Z). Since #496 every
copy conflicted beside the shape pin went to a person, the copies two
`update-shape.py apply` runs to different targets wrote included, though
neither side had edited them. Now a copy whose two stages are each, byte
for byte, the standard's own file at the commit THAT side's pin names is
taken whole with the pin, in the one NEXT, and the `why` says so; every
other conflicted copy is still a person's to merge by hand. The proof
reads the standard from the checkout the doctor runs from, so the same
merge asked of a checkout short of a side's commit is a hand merge. The
`manifest kinds` row prints the same NEXT, and calls a copy under
`contracts/` that it takes `unmerged`, never `project`, as #485 has it call
one it leaves to a person. A copy whose mode one side changed, one a side
deleted, one the other side's pin has no row for, and every copy where the
standard's checkout is a partial clone, stay a person's (review of PR #586).
A copy only the other side's pin has a row for -- a row the kept pin lost,
or an add/add where one side's `apply --add` took a file the standard added
and the other wrote its own -- is never taken either, and the `why` and
`left_for_a_person` name it for a person (#687). Where one side deleted
it, the `why` says a person keeps or deletes it, as there are no hunks to
keep (review of PR #736). A side whose pin does not read is never taken:
the NEXT takes the side whose pin reads, and where no side's pin reads,
neither row names a NEXT (#752). A copy renamed on one side conflicts
under a name no pin has a row for; the `why` names it as renamed from that
copy, by the merge base's blob, and gives it to a person (#753). A copy
renamed on both sides is `DD` at its old name, never a merge of hunks:
the `why` names each new name a side's own commit holds the base's blob
at, or the bytes that commit's own pin row for the copy records, and says
where a side's is not proved (#783, review of PR #789).

L2-9. A slip amended into `bump-leg.py`'s own commit leaves the commit
before it holding the pin for the OLD leg commit. Putting that pin back is
still the NEXT, and its `why` now says to commit it and then run the
`bump-leg.py` line the `pins` row names; followed, the root is COMPLIANT.

EVERY STATE IS REAL GIT: the standard moved on by real commits, the
project re-pinned by the real `apply`, the merge git's own, and every
NEXT run as the reader's shell reads it (`pasted`). The root sits under a
directory whose name holds a blank and an apostrophe, so a line that is not
quoted for its shell fails here. Files are written as bytes and nothing is
fed to git as text, so no line ending differs between the three systems.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pytest

from conftest import (FILE_PROTOCOL, WINDOWS_SKIP, cloned_just_pushed, git,
                      run_script)
from test_shape_doctor import (  # noqa: F401
    DRIFT_TARGET, GIT_IDENTITY, PROJECT, SHAPE_PIN, SPEC_PIN,
    UPSTREAM_TARGET, assert_a_plain_next, break_the_pin, commit_all,
    commit_in, compliant_again, doctor, pasted, pin_with, project, rows_of,
    run_pasted, scaffolded_here, standard,
)
from test_update_shape_add import MATERIALIZER, name_in_list

#: The two copies these merges conflict, and the standard's file each is a
#: verbatim copy of.
MAKEFILE = "Makefile"
BOOTSTRAP = DRIFT_TARGET
BOOTSTRAP_SOURCE = f"templates/assembly-root/{DRIFT_TARGET}"

#: The lines each commit of the moved standard appends: comments, so every
#: copy still runs.
C2_LINE = b"# a line the standard gained at C2\n"
C3_LINE = b"# a line the standard gained at C3\n"
#: A line the project writes at the end of a copy, where the standard's
#: lines go too, so git cannot merge the two.
OWN_LINE = b"# a line the project wrote in its own copy\n"

#: What the `why` says of a copy it takes, and of one it gives a person.
TAKEN = "conflicted too and taken whole with the pin"
LEFT = "conflicted too. A copy can hold an edit of the project"


def under_an_awkward_name(project: Path, tmp_path: Path) -> Path:
    """The root moved under a directory whose name needs quoting in every
    shell: a blank, and an apostrophe."""
    root = tmp_path / "it's my work" / PROJECT
    root.parent.mkdir()
    shutil.move(str(project), str(root))
    return root.resolve()


def moved_on(moved: Path, label: str, *sources: str) -> str:
    """One commit in the standard `moved`, appending its own line to each
    of `sources`; its sha."""
    line = {"c2": C2_LINE, "c3": C3_LINE}[label]
    for source in sources:
        (moved / source).write_bytes((moved / source).read_bytes() + line)
    commit_all(moved, f"{label}: {', '.join(sources)} gain a line")
    return git("rev-parse", "HEAD", cwd=moved).stdout.strip()


def the_standard_moved(standard: Path, tmp_path: Path, *sources: str):
    """`(the standard moved on, C2, C3, a copy frozen at C2)`: two commits,
    each appending a line to every one of `sources`, so `apply --at C2` and
    `apply --at C3` re-copy each copy made from them, differently. A copy of
    the session's standard, with its `.git`, so that one is left as every
    other test finds it; and a second copy taken between the two commits,
    which holds C2 and not C3."""
    moved = tmp_path / "moved" / "openRepoShape"
    shutil.copytree(standard, moved, symlinks=True)
    c2 = moved_on(moved, "c2", *sources)
    frozen = tmp_path / "frozen-at-c2" / "openRepoShape"
    shutil.copytree(moved, frozen, symlinks=True)
    c3 = moved_on(moved, "c3", *sources)
    return moved, c2, c3, frozen


def apply_on(moved: Path, root: Path, commit: str, branch: str,
             *extra: str) -> None:
    """The real `update-shape.py apply --at <commit> --yes --branch
    <branch>`, and `extra`, from `main`."""
    git("checkout", "-q", "main", cwd=root)
    applied = run_script(moved / "update-shape.py", "apply", "--root",
                         str(root), "--upstream", str(moved), "--at", commit,
                         "--yes", "--branch", branch, *extra,
                         env=GIT_IDENTITY)
    assert applied.returncode == 0, applied.stdout + applied.stderr


def own_edit(root: Path, copy: str) -> None:
    """The project's own line at the end of `copy`, committed."""
    (root / copy).write_bytes((root / copy).read_bytes() + OWN_LINE)
    git("add", "--", copy, cwd=root)
    commit_in(root, f"the project's own line in {copy}")


def merge_a_into_b(root: Path) -> str:
    """shape/b merges shape/a, so `--ours` is shape/b's side and `--theirs`
    shape/a's. The merge must stop on a conflict; the status it leaves."""
    git("checkout", "-q", "shape/b", cwd=root)
    merged = subprocess.run(["git", "merge", "-q", "shape/a"], cwd=str(root),
                            capture_output=True, check=False,
                            env={**os.environ, **GIT_IDENTITY})
    assert merged.returncode != 0, merged.stdout + merged.stderr
    return git("status", "--porcelain=v1", cwd=root).stdout


def two_applies_merged(moved: Path, root: Path, c2: str, c3: str,
                       edited: dict | None = None) -> str:
    """The issue's flow: `apply --at C2` on shape/a and `apply --at C3` on
    shape/b, then shape/b merges shape/a. `edited` names, per branch, a
    copy the project then edits on that branch. The status the merge
    leaves."""
    for commit, branch in ((c2, "shape/a"), (c3, "shape/b")):
        apply_on(moved, root, commit, branch)
        if (edited or {}).get(branch):
            own_edit(root, edited[branch])
    return merge_a_into_b(root)


def stage_of(root: Path, number: int, rel: str) -> bytes:
    """Index stage `number` of `rel`, as bytes."""
    return subprocess.run(["git", "cat-file", "blob", f":{number}:{rel}"],
                          cwd=str(root), capture_output=True,
                          check=True).stdout


def standard_file(moved: Path, commit: str, source: str) -> bytes:
    return subprocess.run(["git", "show", f"{commit}:{source}"],
                          cwd=str(moved), capture_output=True,
                          check=True).stdout


def rows_from(shape: Path, root: Path) -> tuple[str, dict]:
    """The verdict and `{id: row}` of the doctor run out of `shape`."""
    result = doctor(shape, root, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    return json.loads(result.stdout)["verdict"], rows_of(result)


def assert_both_rows_name_it(rows: dict) -> dict:
    """The `shape currency` row reads the conflicted pin, and the `manifest
    kinds` row, which reaches the same helper for the same file, prints the
    same command and the same `why`. The `shape currency` row."""
    currency, kinds = rows["shape-currency"], rows["manifest-kinds"]
    assert currency["detail"]["error"] == "yaml-unparsable", currency
    assert currency["detail"]["restore"] == "unmerged", currency["detail"]
    assert kinds["detail"]["restore"] == {SHAPE_PIN: "unmerged"}, kinds
    assert kinds["next"] == currency["next"], (kinds, currency)
    assert kinds["why"] == currency["why"], (kinds, currency)
    assert kinds["detail"].get("left_for_a_person") \
        == currency["detail"].get("left_for_a_person"), (kinds, currency)
    assert_a_plain_next(currency)
    return currency


def merge_by_ours(root: Path, tmp_path: Path, name: str) -> None:
    """A person's merge of `name`: every conflicting hunk to the side the
    NEXT took, every clean one kept, over git's own three stages."""
    stages = []
    for number in (1, 2, 3):
        stages.append(tmp_path / f"{Path(name).name}.{number}")
        stages[-1].write_bytes(stage_of(root, number, name))
    subprocess.run(["git", "merge-file", "--ours", str(stages[1]),
                    str(stages[0]), str(stages[2])],
                   capture_output=True, check=True)
    (root / name).write_bytes(stages[1].read_bytes())


@pytest.fixture
def both_pure(standard, project, tmp_path) -> dict:
    """(a)'s merge: both copies re-copied by `apply` on each side and edited
    on neither, so each side's stage is the standard's own file at that
    side's commit."""
    root = under_an_awkward_name(project, tmp_path)
    moved, c2, c3, frozen = the_standard_moved(
        standard, tmp_path, UPSTREAM_TARGET, BOOTSTRAP_SOURCE)
    status = two_applies_merged(moved, root, c2, c3)
    for name in (SHAPE_PIN, MAKEFILE, BOOTSTRAP, "project.yaml"):
        assert f"UU {name}" in status, status
    return {"root": root, "moved": moved, "c2": c2, "c3": c3,
            "frozen": frozen}


# --- (a) both sides pure tool output: taken whole ----------------------------

def test_copies_neither_side_edited_are_taken_whole_with_the_pin(
        both_pure, tmp_path):
    """Each side holds both copies as the standard wrote them at its own
    pin, so the NEXT names them beside the pin, `--ours` and all, and no
    person is sent to merge them. `project.yaml` still is: its other lines
    are the project's. Run, each copy is the standard's file at the pin
    the NEXT keeps, and once the person's merge of `project.yaml` is
    committed the doctor, run out of the same standard, says COMPLIANT."""
    root, moved, c3 = both_pure["root"], both_pure["moved"], both_pure["c3"]
    verdict, rows = rows_from(moved, root)
    assert verdict == "INVALID (merge)", verdict
    currency = assert_both_rows_name_it(rows)
    argv = pasted(currency["next"])
    assert argv[:3] == ["git", "-C", str(root)], argv
    assert argv[3:] == ["checkout", "--ours", "--", SHAPE_PIN, MAKEFILE,
                        BOOTSTRAP], argv
    detail = currency["detail"]
    assert detail["taken_with_the_pin"] == [MAKEFILE, BOOTSTRAP], detail
    assert detail["left_for_a_person"] == ["project.yaml"], detail
    why = currency["why"]
    assert f"{MAKEFILE} and {BOOTSTRAP} are {TAKEN}: each side holds them " \
        "byte for byte as the standard wrote them at the commit that side's " \
        "pin names, so neither side holds an edit of the project" in why, why
    assert "Take one side of the pin whole and never a hand-merged pin" \
        in why, why
    assert "project.yaml is conflicted too" in why, why
    for words in ("copy conflicted too", "copies conflicted too",
                  "--accept-local"):
        assert words not in why, (words, why)
    run_pasted(currency["next"])
    for name, source in ((MAKEFILE, UPSTREAM_TARGET),
                         (BOOTSTRAP, BOOTSTRAP_SOURCE)):
        assert (root / name).read_bytes() == standard_file(moved, c3, source)
    assert b"<<<<<<<" in (root / "project.yaml").read_bytes()
    merge_by_ours(root, tmp_path, "project.yaml")
    git("add", "--", SHAPE_PIN, MAKEFILE, BOOTSTRAP, "project.yaml",
        cwd=root)
    commit_in(root, "merge shape/a")
    compliant_again(moved, root)


# --- (b) one side edited: a hand merge, as before ----------------------------

@pytest.mark.parametrize("edited_on", [
    pytest.param("shape/b", id="edited-on-the-side-ours-takes"),
    pytest.param("shape/a", id="edited-on-the-other-side"),
])
def test_a_copy_one_side_edited_is_left_to_a_person(standard, project,
                                                    tmp_path, edited_on):
    """The Makefile re-copied on both sides and then given a line of the
    project's own on ONE of them. That side's stage is not the standard's
    file, so nothing proves the copy holds no edit: the NEXT takes the pin
    alone, and the `why` gives the Makefile to a person, whichever side the
    edit is on. Run, the Makefile is as the merge left it."""
    root = under_an_awkward_name(project, tmp_path)
    moved, c2, c3, _frozen = the_standard_moved(standard, tmp_path,
                                                UPSTREAM_TARGET)
    status = two_applies_merged(moved, root, c2, c3, {edited_on: MAKEFILE})
    assert f"UU {MAKEFILE}" in status, status
    assert f"UU {SHAPE_PIN}" in status, status
    _verdict, rows = rows_from(moved, root)
    currency = assert_both_rows_name_it(rows)
    assert pasted(currency["next"])[3:] == [
        "checkout", "--ours", "--", SHAPE_PIN], currency["next"]
    detail = currency["detail"]
    assert "taken_with_the_pin" not in detail, detail
    assert detail["left_for_a_person"] == [MAKEFILE, "project.yaml"], detail
    why = currency["why"]
    assert f"{MAKEFILE} is a copy {LEFT}" in why, why
    assert TAKEN not in why, why
    held = (root / MAKEFILE).read_bytes()
    assert OWN_LINE in held, held[-300:]
    run_pasted(currency["next"])
    assert (root / MAKEFILE).read_bytes() == held, \
        "the NEXT took the edited copy whole"


# --- (c) a pinned commit absent from the standard's checkout -----------------

@pytest.mark.parametrize("short", [
    pytest.param("frozen", id="the-checkout-lacks-one-sides-commit"),
    pytest.param("standard", id="the-checkout-lacks-both-sides-commits"),
])
def test_a_side_whose_commit_the_checkout_lacks_is_a_hand_merge(
        standard, both_pure, short):
    """(a)'s very merge, asked of a checkout of the standard that does not
    hold C3 (frozen between the two commits), or holds neither. Nothing is
    fetched to prove a side, so neither copy is proved and both go to a
    person, and the NEXT takes the pin alone and leaves them as they are."""
    root = both_pure["root"]
    shape = both_pure["frozen"] if short == "frozen" else standard
    missing = git("cat-file", "-e", f"{both_pure['c3']}^{{commit}}",
                  cwd=shape, check=False)
    assert missing.returncode != 0, "the checkout holds C3"
    _verdict, rows = rows_from(shape, root)
    currency = assert_both_rows_name_it(rows)
    assert pasted(currency["next"])[3:] == [
        "checkout", "--ours", "--", SHAPE_PIN], currency["next"]
    detail = currency["detail"]
    assert "taken_with_the_pin" not in detail, detail
    assert detail["left_for_a_person"] == [MAKEFILE, "project.yaml",
                                           BOOTSTRAP], detail
    assert f"{MAKEFILE} and {BOOTSTRAP} are copies conflicted too" \
        in currency["why"], currency["why"]
    held = [(root / name).read_bytes() for name in (MAKEFILE, BOOTSTRAP)]
    run_pasted(currency["next"])
    assert [(root / name).read_bytes()
            for name in (MAKEFILE, BOOTSTRAP)] == held


# --- (d) a path the standard does not have at one side's commit --------------

def test_a_copy_the_standard_lacks_at_a_sides_commit_is_a_hand_merge(
        standard, project, tmp_path):
    """The standard's Makefile is gone at C3 and back at C4, with a line
    of its own. shape/a is re-pinned to C2; shape/b to C4, and then its
    pin names C3, a commit whose tree has no file for the Makefile. That
    side's stage IS the standard's file -- at C4 -- but nothing the
    standard holds at the commit its pin names matches it, so the copy is
    not proved and a person merges it."""
    root = under_an_awkward_name(project, tmp_path)
    moved = tmp_path / "moved" / "openRepoShape"
    shutil.copytree(standard, moved, symlinks=True)
    c2 = moved_on(moved, "c2", UPSTREAM_TARGET)
    at_c2 = (moved / UPSTREAM_TARGET).read_bytes()
    (moved / UPSTREAM_TARGET).unlink()
    commit_all(moved, "c3: the Makefile template is gone")
    c3 = git("rev-parse", "HEAD", cwd=moved).stdout.strip()
    (moved / UPSTREAM_TARGET).write_bytes(at_c2 + C3_LINE)
    commit_all(moved, "c4: the Makefile template is back, with a line")
    c4 = git("rev-parse", "HEAD", cwd=moved).stdout.strip()
    apply_on(moved, root, c2, "shape/a")
    apply_on(moved, root, c4, "shape/b")
    break_the_pin(root, pin_with(r'^commit: .*$', f'commit: "{c3}"'))
    git("add", "--", SHAPE_PIN, cwd=root)
    commit_in(root, "shape/b's pin names C3")
    status = merge_a_into_b(root)
    assert f"UU {MAKEFILE}" in status, status
    assert f"UU {SHAPE_PIN}" in status, status
    # The one fault is the path: against C4 the stage would be proved.
    assert stage_of(root, 2, MAKEFILE) == standard_file(moved, c4,
                                                        UPSTREAM_TARGET)
    assert stage_of(root, 3, MAKEFILE) == standard_file(moved, c2,
                                                        UPSTREAM_TARGET)
    _verdict, rows = rows_from(moved, root)
    currency = assert_both_rows_name_it(rows)
    assert pasted(currency["next"])[3:] == [
        "checkout", "--ours", "--", SHAPE_PIN], currency["next"]
    assert "taken_with_the_pin" not in currency["detail"], currency
    assert currency["detail"]["left_for_a_person"] == [
        MAKEFILE, "project.yaml"], currency["detail"]
    assert f"{MAKEFILE} is a copy {LEFT}" in currency["why"], currency


# --- (e) a mix: one copy taken, one left, and the `why` names both ----------

def test_a_mix_takes_the_proved_copy_and_leaves_the_edited_one(
        standard, project, tmp_path):
    """Both copies re-copied on both sides; shape/a also gives bootstrap.py
    a line of the project's own. The Makefile is proved and taken with the
    pin; bootstrap.py is not, and goes to a person; the `why` names each
    for what it is. Run, the Makefile is shape/b's standard file and
    bootstrap.py is as the merge left it."""
    root = under_an_awkward_name(project, tmp_path)
    moved, c2, c3, _frozen = the_standard_moved(
        standard, tmp_path, UPSTREAM_TARGET, BOOTSTRAP_SOURCE)
    status = two_applies_merged(moved, root, c2, c3, {"shape/a": BOOTSTRAP})
    for name in (SHAPE_PIN, MAKEFILE, BOOTSTRAP):
        assert f"UU {name}" in status, status
    _verdict, rows = rows_from(moved, root)
    currency = assert_both_rows_name_it(rows)
    assert pasted(currency["next"])[3:] == [
        "checkout", "--ours", "--", SHAPE_PIN, MAKEFILE], currency["next"]
    detail = currency["detail"]
    assert detail["taken_with_the_pin"] == [MAKEFILE], detail
    assert detail["left_for_a_person"] == ["project.yaml", BOOTSTRAP], detail
    why = currency["why"]
    assert f"{MAKEFILE} is {TAKEN}: each side holds it byte for byte as " \
        "the standard wrote it at the commit that side's pin names" in why, \
        why
    assert f"{BOOTSTRAP} is a copy {LEFT}" in why, why
    assert "update-shape.py apply --accept-local on that copy re-pins it " \
        "from the merge" in why, why
    assert why.index(MAKEFILE) < why.index(BOOTSTRAP), why
    held = (root / BOOTSTRAP).read_bytes()
    run_pasted(currency["next"])
    assert (root / MAKEFILE).read_bytes() == standard_file(moved, c3,
                                                           UPSTREAM_TARGET)
    assert (root / BOOTSTRAP).read_bytes() == held


# --- (g) the NEXT pasted into a POSIX shell ---------------------------------

@WINDOWS_SKIP
def test_the_next_that_takes_copies_runs_pasted_into_sh(both_pure):
    """The NEXT naming the pin and two copies, under a root whose name
    holds a blank and an apostrophe, run by `sh -c` exactly as printed:
    exit 0, and the pin and each copy are shape/b's stage, byte for
    byte."""
    root = both_pure["root"]
    _verdict, rows = rows_from(both_pure["moved"], root)
    line = rows["shape-currency"]["next"]
    ran = subprocess.run(["sh", "-c", line], capture_output=True,
                         check=False, stdin=subprocess.DEVNULL,
                         env={**os.environ, **GIT_IDENTITY})
    assert ran.returncode == 0, line + "\n" + ran.stdout.decode(
        "utf-8", "replace") + ran.stderr.decode("utf-8", "replace")
    for name in (SHAPE_PIN, MAKEFILE, BOOTSTRAP):
        assert (root / name).read_bytes() == stage_of(root, 2, name), name


# --- (f) L2-9: a leg pin broken in its bump's own commit --------------------

#: The branch of the spec leg's remote the new commit is pushed to.
ADVANCE = "pin-restore-advance"


@pytest.fixture(scope="module")
def advanced(scaffolded_here, tmp_path_factory) -> str:
    """A new commit on a branch of the spec leg's remote, as a merged pull
    request leaves one; its sha."""
    work = cloned_just_pushed(
        scaffolded_here["base"] / "remotes" / f"{PROJECT}-spec.git",
        tmp_path_factory.mktemp("spec-advance") / f"{PROJECT}-spec")
    (work / "requirements").mkdir(exist_ok=True)
    (work / "requirements" / "r547.md").write_bytes(b"# R547\n")
    git("add", "--", "requirements/r547.md", cwd=work)
    git("commit", "-qm", "Add R547", cwd=work)
    git("push", "-q", "origin", f"HEAD:refs/heads/{ADVANCE}", cwd=work)
    return git("rev-parse", "HEAD", cwd=work).stdout.strip()


def pin_commit_of(root: Path, rel: str) -> str:
    found = re.search(rb'(?m)^commit: "([0-9a-f]{40})"', (root / rel)
                      .read_bytes())
    assert found, rel
    return found.group(1).decode()


def run_from_elsewhere(line: str, tmp_path: Path) -> None:
    """A line a row named, run exactly as printed through the reader's
    shell's reading of it, from a directory that is not the root."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir(exist_ok=True)
    ran = subprocess.run(pasted(line), cwd=str(elsewhere),
                         capture_output=True, check=False,
                         stdin=subprocess.DEVNULL,
                         env={**os.environ, **GIT_IDENTITY,
                              "PYTHONDONTWRITEBYTECODE": "1"})
    assert ran.returncode == 0, line + "\n" + ran.stdout.decode(
        "utf-8", "replace") + ran.stderr.decode("utf-8", "replace")


@pytest.mark.parametrize("in_the_bump", [
    pytest.param(True, id="the-slip-amended-into-the-bump"),
    pytest.param(False, id="the-slip-in-a-commit-of-its-own"),
])
def test_a_leg_pin_put_back_from_before_its_bump_says_what_comes_next(
        standard, project, advanced, tmp_path, in_the_bump):
    """`bump-leg.py --to X` moves the spec leg's gitlink and pin to X in one
    commit, and a slip that stops the pin loading goes into the pin: AMENDED
    into that commit, as the issue's flow does, or as a commit of its own
    after it, the control.

    Amended, the commit before the break holds the pin for the OLD commit,
    so the NEXT that puts it back leaves the pin and the gitlink apart. The
    NEXT is still that one `checkout`, and its `why` now says to commit it,
    then run the `bump-leg.py` line the `pins` row names. Followed -- the
    NEXT, a commit, then the line that keeps the gitlink -- the doctor says
    COMPLIANT, where it said DRIFTED.

    In a commit of its own, the pin put back names X, the gitlink's commit,
    so the `why` says nothing of the kind, and the NEXT and a commit end
    COMPLIANT."""
    root = under_an_awkward_name(project, tmp_path)
    old = pin_commit_of(root, SPEC_PIN)
    git("checkout", "-q", "-b", "take-the-new-spec", cwd=root)
    git(*FILE_PROTOCOL, "fetch", "-q", "origin", ADVANCE, cwd=root / "spec")
    bumped = run_script(standard / "scripts" / "bump-leg.py", "--root",
                        str(root), "--leg", "spec", "--to", advanced,
                        env=GIT_IDENTITY)
    assert bumped.returncode == 0, bumped.stdout + bumped.stderr
    assert pin_commit_of(root, SPEC_PIN) == advanced
    pin = root / SPEC_PIN
    pin.write_bytes(pin.read_bytes() + b"\xff\n")
    git("add", "--", SPEC_PIN, cwd=root)
    breaking = commit_in(root, "bump the spec leg, with a slip in its pin",
                         *(("--amend",) if in_the_bump else ()))
    _verdict, rows = rows_from(standard, root)
    kinds = rows["manifest-kinds"]
    assert kinds["detail"]["restore"] == {SPEC_PIN: "committed"}, kinds
    assert pasted(kinds["next"])[3:] == [
        "checkout", f"{breaking}~1", "--", SPEC_PIN], kinds["next"]
    assert_a_plain_next(kinds)
    why = kinds["why"]
    assert why.startswith(f"the pin as it was before {breaking[:12]}, the "
                          "commit that broke it"), why
    said = (f"That pin names {old[:12]} and the root's gitlink for spec is "
            f"{advanced[:12]}, so commit it, then run the bump-leg.py line "
            "the pins row names for spec: --to the gitlink's "
            f"{advanced[:12]} keeps the move, and --to the pin's {old[:12]} "
            "undoes it")
    run_pasted(kinds["next"])
    commit_in(root, "the spec pin put back")
    if not in_the_bump:
        assert "That pin names" not in why, why
        compliant_again(standard, root)
        return
    assert why.endswith(". Commit that rather than editing the pin. " + said),\
        why
    verdict, rows = rows_from(standard, root)
    assert verdict.startswith("DRIFTED"), verdict
    assert rows["pins"]["status"] == "FINDING", rows["pins"]
    repairs = rows["pins"]["detail"]["gitlink_repairs"]
    assert [(leg["path"], leg["gitlink"], leg["pin"]) for leg in repairs] \
        == [("spec", advanced, old)], repairs
    run_from_elsewhere(repairs[0]["keep_gitlink"], tmp_path)
    compliant_again(standard, root)
    assert pin_commit_of(root, SPEC_PIN) == advanced


# --- (h) a copy under contracts/ taken whole, in the `manifest kinds` row ---

#: The one shape copy a root keeps under `contracts/`, copied from the
#: standard's own file at the same path.
NAMING_COPY = "contracts/repository-naming.yaml"


def test_a_naming_copy_taken_with_the_pin_is_unmerged_in_both_rows(
        standard, project, tmp_path):
    """The naming copy re-copied on both sides, edited on neither. Under
    `contracts/` and conflicted, it is a file the `manifest kinds` row
    cannot load, and while the shape pin does not read nothing calls it a
    copy. Taken whole by the command both rows print, its `restore` there
    is `unmerged`, the case it has once the pin reads, and not `project`,
    which says git was not asked about a file the NEXT overwrites (#485);
    and both rows list it as taken."""
    root = under_an_awkward_name(project, tmp_path)
    moved, c2, c3, _frozen = the_standard_moved(standard, tmp_path,
                                                NAMING_COPY)
    status = two_applies_merged(moved, root, c2, c3)
    assert f"UU {NAMING_COPY}" in status, status
    assert f"UU {SHAPE_PIN}" in status, status
    _verdict, rows = rows_from(moved, root)
    currency, kinds = rows["shape-currency"], rows["manifest-kinds"]
    assert pasted(currency["next"])[3:] == [
        "checkout", "--ours", "--", SHAPE_PIN, NAMING_COPY], currency["next"]
    assert kinds["next"] == currency["next"], (kinds, currency)
    assert kinds["why"] == currency["why"], (kinds, currency)
    assert currency["detail"]["taken_with_the_pin"] == [NAMING_COPY]
    assert kinds["detail"]["taken_with_the_pin"] == [NAMING_COPY], kinds
    assert kinds["detail"]["restore"] == {NAMING_COPY: "unmerged",
                                          SHAPE_PIN: "unmerged"}, kinds
    run_pasted(currency["next"])
    assert (root / NAMING_COPY).read_bytes() == standard_file(moved, c3,
                                                              NAMING_COPY)


# --- what else stays a hand merge (review of PR #586) -----------------------

def index_stages(root: Path, rel: str) -> dict:
    """`{stage: (mode, object)}` the index holds for `rel`, read as bytes."""
    listing = subprocess.run(["git", "ls-files", "-u", "-z", "--", rel],
                             cwd=str(root), capture_output=True,
                             check=True).stdout
    held = {}
    for record in listing.split(b"\0"):
        meta, _tab, path = record.partition(b"\t")
        if path == rel.encode():
            mode, oid, number = meta.decode("ascii").split(" ")
            held[int(number)] = (mode, oid)
    return held


def restaged(root: Path, rel: str, stages: dict) -> None:
    """`rel`'s stages in the index replaced by `stages`, `{stage: (mode,
    object)}`, through git's plumbing, as bytes on its stdin: the stage-0
    removal line first, then one line per stage."""
    data = f"0 {'0' * 40}\t{rel}\0".encode()
    for number, (mode, oid) in sorted(stages.items()):
        data += f"{mode} {oid} {number}\t{rel}\0".encode()
    subprocess.run(["git", "update-index", "-z", "--index-info"],
                   cwd=str(root), input=data, capture_output=True, check=True)


#: What the `why` says of the Makefile where the kept side's pin has its row.
A_COPY_LEFT = f"{MAKEFILE} is a copy {LEFT}"


def assert_only_bootstrap_is_taken(rows: dict, said: str = A_COPY_LEFT
                                   ) -> dict:
    """Both rows name the pin and `scripts/bootstrap.py`, taken; the
    Makefile goes to a person with `project.yaml`, and the `why` says
    `said` of it. The `shape currency` row."""
    currency = assert_both_rows_name_it(rows)
    assert pasted(currency["next"])[3:] == [
        "checkout", "--ours", "--", SHAPE_PIN, BOOTSTRAP], currency["next"]
    detail = currency["detail"]
    assert detail["taken_with_the_pin"] == [BOOTSTRAP], detail
    assert detail["left_for_a_person"] == [MAKEFILE, "project.yaml"], detail
    assert said in currency["why"], currency["why"]
    return currency


@pytest.mark.parametrize("on", [
    pytest.param("shape/b", id="mode-changed-on-the-side-ours-takes"),
    pytest.param("shape/a", id="mode-changed-on-the-other-side"),
])
def test_a_copy_whose_mode_one_side_changed_is_left_to_a_person(
        standard, project, tmp_path, on):
    """Both copies re-copied on both sides, edited on neither, but on ONE
    side the project makes its Makefile executable. Each stage's bytes are
    still the standard's file at that side's pin, and the mode is an edit
    no byte compare sees: taken whole, `--ours` kept one side's mode and
    dropped the other's, while the `why` said neither side held an edit.
    Now a copy whose two stages disagree on its mode is a person's, either
    side, and bootstrap.py is still taken.

    The x bit is set in the INDEX, which is what git merges and the doctor
    reads, so the state is the same on every system; the file's own mode is
    set too only where the file system keeps one."""
    root = under_an_awkward_name(project, tmp_path)
    moved, c2, c3, _frozen = the_standard_moved(
        standard, tmp_path, UPSTREAM_TARGET, BOOTSTRAP_SOURCE)
    for commit, branch in ((c2, "shape/a"), (c3, "shape/b")):
        apply_on(moved, root, commit, branch)
        if branch == on:
            git("update-index", "--chmod=+x", "--", MAKEFILE, cwd=root)
            if os.name != "nt":
                os.chmod(root / MAKEFILE, 0o755)
            commit_in(root, "the project's Makefile made executable")
    status = merge_a_into_b(root)
    assert f"UU {MAKEFILE}" in status, status
    held = index_stages(root, MAKEFILE)
    assert held[2][0] != held[3][0], held
    assert stage_of(root, 2, MAKEFILE) == standard_file(moved, c3,
                                                        UPSTREAM_TARGET)
    assert stage_of(root, 3, MAKEFILE) == standard_file(moved, c2,
                                                        UPSTREAM_TARGET)
    _verdict, rows = rows_from(moved, root)
    assert_only_bootstrap_is_taken(rows)


def a_pin_restaged(root: Path, number: int, changed) -> None:
    """Stage `number` of the conflicted shape pin restaged as `changed`
    makes it of the bytes the merge left there."""
    stages = index_stages(root, SHAPE_PIN)
    mode, oid = stages[number]
    blob = subprocess.run(["git", "cat-file", "blob", oid], cwd=str(root),
                          capture_output=True, check=True).stdout
    held = changed(blob)
    written = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                             cwd=str(root), input=held,
                             capture_output=True, check=True)
    stages[number] = (mode, written.stdout.decode("ascii").strip())
    restaged(root, SHAPE_PIN, stages)
    assert stage_of(root, number, SHAPE_PIN) == held


def a_pin_without_a_row(root: Path, number: int, rel: str) -> None:
    """Stage `number` of the conflicted shape pin restaged without `rel`'s
    `files:` row, and every other byte of it as the merge left it."""
    row = (rb'(?m)^  - path: ' + re.escape(rel.encode())
           + rb'\n    sha256: "[0-9a-f]{64}"\n')

    def without(blob: bytes) -> bytes:
        held, count = re.subn(row, b"", blob)
        assert count == 1, blob
        return held

    a_pin_restaged(root, number, without)


#: What the `why` says of the Makefile one side deleted where only the
#: other side's pin has its row (review of PR #736): no hunks to keep.
OTHER_SIDES_DELETED = (
    f"{MAKEFILE} is conflicted too, and the other side's pin calls it a "
    "copy where the pin taken here does not, and one side deleted it, so "
    "neither side is taken whole: once the merge is finished it is the "
    "project's own file if kept, and a person keeps or deletes it by hand. "
    "Then finish")


@pytest.mark.parametrize("kept_row", [
    pytest.param(True, id="the-kept-pin-has-its-row"),
    pytest.param(False, id="only-the-other-sides-pin-has-its-row"),
])
def test_a_copy_one_side_deleted_is_left_to_a_person(standard, project,
                                                     tmp_path, kept_row):
    """shape/a re-pins to C2 and then deletes its Makefile; shape/b
    re-pins to C3. Merged, the Makefile is a delete/modify conflict:
    stages 1 and 2, no stage 3, and shape/a's pin still has its row. No
    side's absence proves anything, so the Makefile is a person's -- taken
    whole as ours, the NEXT would drop the other side's deletion -- and
    bootstrap.py is still taken. Run, the NEXT leaves the Makefile
    unmerged, as the merge left it.

    With the kept side's pin restaged without the Makefile's row, only the
    other side's pin calls it a copy (#687), and the `why` says a person
    keeps or deletes it, since a deletion leaves no hunks to keep."""
    root = under_an_awkward_name(project, tmp_path)
    moved, c2, c3, _frozen = the_standard_moved(
        standard, tmp_path, UPSTREAM_TARGET, BOOTSTRAP_SOURCE)
    apply_on(moved, root, c2, "shape/a")
    git("rm", "-q", "--", MAKEFILE, cwd=root)
    commit_in(root, "the project's Makefile removed")
    apply_on(moved, root, c3, "shape/b")
    status = merge_a_into_b(root)
    assert f"UD {MAKEFILE}" in status, status
    assert f"UU {SHAPE_PIN}" in status, status
    assert sorted(index_stages(root, MAKEFILE)) == [1, 2]
    if not kept_row:
        a_pin_without_a_row(root, 2, MAKEFILE)
    _verdict, rows = rows_from(moved, root)
    currency = assert_only_bootstrap_is_taken(
        rows, A_COPY_LEFT if kept_row else OTHER_SIDES_DELETED)
    run_pasted(currency["next"])
    assert sorted(index_stages(root, MAKEFILE)) == [1, 2]


def test_a_copy_the_other_sides_pin_has_no_row_for_is_left_to_a_person(
        both_pure):
    """(a)'s merge, with the other side's pin restaged without the
    Makefile's `files:` row. That side then says the Makefile is not a
    shape copy, so whether it holds the project's edit is a person's
    question, though its bytes are the standard's: the Makefile is left,
    and bootstrap.py, which both pins name, is still taken."""
    root = both_pure["root"]
    a_pin_without_a_row(root, 3, MAKEFILE)
    _verdict, rows = rows_from(both_pure["moved"], root)
    assert_only_bootstrap_is_taken(rows)


#: What the `why` says of a conflicted file only the side NOT taken has a
#: `files:` row for (#687).
OTHER_SIDES = (f"{MAKEFILE} is conflicted too, and the other side's pin "
               "calls it a copy where the pin taken here does not, so "
               "neither side is taken whole: once the merge is finished it "
               "is the project's own file, and a person merges it by hand, "
               "keeping the hunks git merged")


def test_a_copy_only_the_other_sides_pin_has_a_row_for_is_named(both_pure):
    """The mirror of the test above (#687): (a)'s merge with the KEPT
    side's pin, stage 2, the one `checkout --ours` takes, restaged without
    the Makefile's `files:` row. That pin says the Makefile is not a shape
    copy, so nothing proves it unedited and the NEXT never takes it. The
    other side's pin calls it one, and its conflict holds that side's
    `apply` output, so it is a person's to merge and the `why` and
    `left_for_a_person` say so, where they said nothing of it before. No
    copy the kept pin has a row for is left, so the `why` sends nobody to
    `--accept-local`, which refuses a path that pin has no row for.
    bootstrap.py, which both pins name, is still taken. Run, the NEXT
    leaves the Makefile unmerged, as the merge left it."""
    root = both_pure["root"]
    a_pin_without_a_row(root, 2, MAKEFILE)
    _verdict, rows = rows_from(both_pure["moved"], root)
    currency = assert_only_bootstrap_is_taken(rows, OTHER_SIDES)
    assert "--accept-local" not in currency["why"], currency["why"]
    held = (root / MAKEFILE).read_bytes()
    run_pasted(currency["next"])
    assert sorted(index_stages(root, MAKEFILE)) == [1, 2, 3]
    assert (root / MAKEFILE).read_bytes() == held


#: Both copies conflicted beside the pin, by the conflict each is.
BOTH_COPIES = [MAKEFILE, "project.yaml", BOOTSTRAP]


def test_copies_only_the_other_sides_pin_has_rows_for_are_named_together(
        both_pure):
    """The mirror with both copies' rows gone from the kept side's pin:
    nothing is taken with the pin, and the `why` names the two in one
    sentence."""
    root = both_pure["root"]
    for rel in (MAKEFILE, BOOTSTRAP):
        a_pin_without_a_row(root, 2, rel)
    _verdict, rows = rows_from(both_pure["moved"], root)
    currency = assert_both_rows_name_it(rows)
    assert pasted(currency["next"])[3:] == [
        "checkout", "--ours", "--", SHAPE_PIN], currency["next"]
    assert currency["detail"]["left_for_a_person"] == BOTH_COPIES, \
        currency["detail"]
    assert f"{MAKEFILE} and {BOOTSTRAP} are conflicted too, and the other " \
        "side's pin calls them copies where the pin taken here does not, " \
        "so neither side is taken whole: once the merge is finished each " \
        "is the project's own file, and a person merges each by hand, " \
        "keeping the hunks git merged. Then finish" in currency["why"], \
        currency["why"]


# --- a side whose pin does not read is never taken (#752) -------------------

#: Bytes no pin reads as: a flow sequence nothing closes, RV-b's state.
UNREADABLE_PIN = b"files: [\n"


@pytest.mark.parametrize("broken, side", [
    pytest.param(2, "--theirs", id="ours-does-not-read"),
    pytest.param(3, "--ours", id="theirs-does-not-read"),
])
def test_the_side_taken_is_one_whose_pin_reads(both_pure, broken, side):
    """(a)'s merge with one side's pin restaged as bytes that do not read.
    `--ours` was taken wherever ours held a pin, and taken whole a pin that
    does not read left the pin as it was, so the doctor named the same
    line again (#752). Now the NEXT takes the side whose pin reads, and its
    `why` says only that side's pin reads, never offering the other. No
    copy is taken: the proof reads both sides' pins. Run as printed, the
    pin in the tree reads, and neither row names it unreadable again."""
    root, moved = both_pure["root"], both_pure["moved"]
    a_pin_restaged(root, broken, lambda _blob: UNREADABLE_PIN)
    _verdict, rows = rows_from(moved, root)
    currency = assert_both_rows_name_it(rows)
    assert pasted(currency["next"])[3:] == [
        "checkout", side, "--", SHAPE_PIN], currency["next"]
    assert "taken_with_the_pin" not in currency["detail"], currency
    assert currency["detail"]["left_for_a_person"] == BOTH_COPIES, currency
    assert currency["why"].startswith(
        "only that side's pin reads as one, and the other side taken whole "
        "would leave a pin that does not read. Take it whole and never a "
        "hand-merged pin. "), currency["why"]
    run_pasted(currency["next"])
    _verdict, after = rows_from(moved, root)
    assert "error" not in after["shape-currency"]["detail"], \
        after["shape-currency"]
    assert SHAPE_PIN not in after["manifest-kinds"]["detail"].get(
        "restore", {}), after["manifest-kinds"]


#: What the `why` says where no side's pin reads, by how many sides hold a
#: pin: no line puts back one that reads (#752).
NO_SIDE_READS = {
    "both": "neither side's pin reads as one",
    "one": "the one side of it that holds a pin holds one that does not "
           "read",
}


@pytest.mark.parametrize("held", sorted(NO_SIDE_READS))
def test_no_line_is_named_where_no_sides_pin_reads(both_pure, held):
    """(a)'s merge with both sides' pins restaged as bytes that do not
    read, or ours removed and theirs not reading. Either side taken whole
    leaves a pin that does not read, so both rows name no NEXT, and the
    same `why` says the merge is a person's call (#752). The doctor said
    `checkout --ours` before, again after it ran."""
    root = both_pure["root"]
    a_pin_restaged(root, 3, lambda _blob: UNREADABLE_PIN)
    if held == "both":
        a_pin_restaged(root, 2, lambda _blob: UNREADABLE_PIN)
    else:
        stages = index_stages(root, SHAPE_PIN)
        del stages[2]
        restaged(root, SHAPE_PIN, stages)
    _verdict, rows = rows_from(both_pure["moved"], root)
    currency, kinds = rows["shape-currency"], rows["manifest-kinds"]
    assert currency["next"] is None, currency
    assert kinds["next"] is None, kinds
    assert kinds["why"] == currency["why"], (kinds, currency)
    assert currency["detail"]["restore"] == "unmerged", currency["detail"]
    assert kinds["detail"]["restore"] == {SHAPE_PIN: "unmerged"}, kinds
    assert currency["why"] == (
        f"a merge left the pin conflicted, and {NO_SIDE_READS[held]}, so no "
        "side taken whole puts back a pin that reads, and this doctor would "
        "name the same line again. A pin is never mended by hand, so no line "
        "is named here: whether to finish the merge, or to abort it and "
        "first put back the pin a side broke, is a person's call"), \
        currency["why"]


def test_a_naming_copy_only_the_other_sides_pin_has_a_row_for_is_named(
        standard, project, tmp_path):
    """(h)'s merge, with the kept side's pin restaged without the naming
    copy's row (#687). Nothing takes the copy, both rows give it to a
    person, and the `manifest kinds` row calls it `unmerged` while the
    shape pin is conflicted, as it calls every file the `why` gives a
    person. Run, the NEXT leaves the copy as the merge left it, and once
    the pin taken here reads, with no row for it, the copy is the project's
    own file there, `project`, as the `why` said it would be."""
    root = under_an_awkward_name(project, tmp_path)
    moved, c2, c3, _frozen = the_standard_moved(standard, tmp_path,
                                                NAMING_COPY)
    status = two_applies_merged(moved, root, c2, c3)
    assert f"UU {NAMING_COPY}" in status, status
    a_pin_without_a_row(root, 2, NAMING_COPY)
    _verdict, rows = rows_from(moved, root)
    currency, kinds = rows["shape-currency"], rows["manifest-kinds"]
    assert pasted(currency["next"])[3:] == [
        "checkout", "--ours", "--", SHAPE_PIN], currency["next"]
    assert kinds["why"] == currency["why"], (kinds, currency)
    assert f"{NAMING_COPY} is conflicted too, and the other side's pin " \
        "calls it a copy" in currency["why"], currency["why"]
    assert kinds["detail"]["left_for_a_person"] == [
        NAMING_COPY, "project.yaml"], kinds["detail"]
    assert kinds["detail"]["restore"] == {NAMING_COPY: "unmerged",
                                          SHAPE_PIN: "unmerged"}, kinds
    held = (root / NAMING_COPY).read_bytes()
    run_pasted(currency["next"])
    assert (root / NAMING_COPY).read_bytes() == held
    _verdict, rows = rows_from(moved, root)
    assert rows["manifest-kinds"]["detail"]["restore"] == {
        NAMING_COPY: "project"}, rows["manifest-kinds"]


#: A file the standard adds to the assembly root's copy list, which one
#: side takes with `apply --add` and the other writes as its own.
ADDED = "SECURITY.md"


def test_an_add_add_only_one_sides_pin_calls_a_copy_is_named(
        standard, project, tmp_path):
    """#687's state by a natural flow. At C2 the standard adds SECURITY.md
    to the assembly root's copy list, as a pull request adding a template
    file does, and at C3 its Makefile gains a line. shape/a re-pins to C2
    and takes the new copy with `apply --add`; shape/b re-pins to C3
    without it, since `apply` adds nothing unasked, and writes a
    SECURITY.md of its own. Merged, SECURITY.md is an add/add conflict that
    only the other side's pin calls a copy: the NEXT takes the pin alone,
    and the `why` gives SECURITY.md to a person. Run, the NEXT leaves it
    unmerged; a person keeps the project's own, and once the merge is
    committed the doctor says COMPLIANT, the file the project's own, as the
    `why` said."""
    root = under_an_awkward_name(project, tmp_path)
    moved = tmp_path / "moved" / "openRepoShape"
    shutil.copytree(standard, moved, symlinks=True)
    (moved / "templates" / "assembly-root" / ADDED).write_bytes(
        b"# The standard's security policy.\n")
    source = moved / MATERIALIZER
    source.write_text(name_in_list(source.read_text(encoding="utf-8"),
                                   "COPIED_VERBATIM", ADDED),
                      encoding="utf-8")
    commit_all(moved, f"c2: the standard adds {ADDED}")
    c2 = git("rev-parse", "HEAD", cwd=moved).stdout.strip()
    c3 = moved_on(moved, "c3", UPSTREAM_TARGET)
    apply_on(moved, root, c2, "shape/a", "--add", ADDED)
    apply_on(moved, root, c3, "shape/b")
    (root / ADDED).write_bytes(b"# This project's own security policy.\n")
    git("add", "--", ADDED, cwd=root)
    commit_in(root, f"the project's own {ADDED}")
    status = merge_a_into_b(root)
    assert f"AA {ADDED}" in status, status
    assert f"UU {SHAPE_PIN}" in status, status
    _verdict, rows = rows_from(moved, root)
    currency = assert_both_rows_name_it(rows)
    assert pasted(currency["next"])[3:] == [
        "checkout", "--ours", "--", SHAPE_PIN], currency["next"]
    assert currency["detail"]["left_for_a_person"] == [
        ADDED, "project.yaml"], currency["detail"]
    assert OTHER_SIDES.replace(MAKEFILE, ADDED, 1) in currency["why"], \
        currency["why"]
    run_pasted(currency["next"])
    assert sorted(index_stages(root, ADDED)) == [2, 3]
    (root / ADDED).write_bytes(stage_of(root, 2, ADDED))
    merge_by_ours(root, tmp_path, "project.yaml")
    git("add", "--", SHAPE_PIN, ADDED, "project.yaml", cwd=root)
    commit_in(root, "merge shape/a")
    compliant_again(moved, root)


def test_a_partial_clone_of_the_standard_proves_nothing_and_fetches_nothing(
        both_pure, tmp_path):
    """(a)'s merge, asked of a `--filter=blob:none` clone of the standard,
    which holds the commits and not the blobs C2's copies were made from.
    A `git show` of one would fetch it from the clone's promisor remote,
    and Brett Heap's ruling is never to fetch. So nothing is proved, every
    copy is a person's, the `why` says why, and the two blobs are still
    missing afterwards (`rev-list --missing=print`, which never fetches)."""
    root, moved, c2 = both_pure["root"], both_pure["moved"], both_pure["c2"]
    git("config", "uploadpack.allowFilter", "true", cwd=moved)
    partial = tmp_path / "partial" / "openRepoShape"
    cloned = subprocess.run(
        ["git", *FILE_PROTOCOL, "clone", "-q", "--no-local",
         "--filter=blob:none", moved.as_uri(), str(partial)],
        capture_output=True, check=False)
    assert cloned.returncode == 0, cloned.stdout + cloned.stderr
    left_out = {git("rev-parse", f"{c2}:{source}", cwd=moved).stdout.strip()
                for source in (UPSTREAM_TARGET, BOOTSTRAP_SOURCE)}

    def missing() -> set:
        listed = subprocess.run(
            ["git", "rev-list", "--objects", "--missing=print", c2],
            cwd=str(partial), capture_output=True, check=True).stdout
        return {line[1:].decode("ascii") for line in listed.split()
                if line.startswith(b"?")}

    assert left_out <= missing(), "the clone holds C2's blobs"
    _verdict, rows = rows_from(partial, root)
    currency = assert_both_rows_name_it(rows)
    assert pasted(currency["next"])[3:] == [
        "checkout", "--ours", "--", SHAPE_PIN], currency["next"]
    detail = currency["detail"]
    assert "taken_with_the_pin" not in detail, detail
    assert detail["left_for_a_person"] == [MAKEFILE, "project.yaml",
                                           BOOTSTRAP], detail
    assert ("The checkout of the standard this doctor runs from is a "
            "partial clone, which fetches what it lacks on a read, so "
            "nothing was read from it to prove a copy unedited") \
        in currency["why"], currency["why"]
    assert left_out <= missing(), "the doctor fetched a blob"


# --- a copy renamed on one side (#753) --------------------------------------

#: The name one side gives its Makefile, which no pin has a row for.
RENAMED = "build.mk"


def renamed(old: str, new: str, line: bytes = b"", row: bool = False):
    """An act on a branch: `old` renamed to `new`, `line` appended there,
    and with `row` the shape pin's `files:` row for `old` moved to `new`,
    its sha256 kept, all in one commit."""
    def act(root: Path) -> None:
        git("mv", "--", old, new, cwd=root)
        if line:
            (root / new).write_bytes((root / new).read_bytes() + line)
            git("add", "--", new, cwd=root)
        if row:
            held = (root / SHAPE_PIN).read_bytes()
            at = f"  - path: {old}\n".encode()
            assert held.count(at) == 1, held
            (root / SHAPE_PIN).write_bytes(
                held.replace(at, f"  - path: {new}\n".encode()))
            git("add", "--", SHAPE_PIN, cwd=root)
        commit_in(root, f"{old} renamed to {new}")
    return act


def deleted(old: str):
    """An act on a branch: `old` removed, committed."""
    def act(root: Path) -> None:
        git("rm", "-q", "--", old, cwd=root)
        commit_in(root, f"{old} removed")
    return act


def edited(path: str, line: bytes):
    """An act on a branch: `line` appended to `path`, committed."""
    def act(root: Path) -> None:
        (root / path).write_bytes((root / path).read_bytes() + line)
        git("add", "--", path, cwd=root)
        commit_in(root, f"a line in {path}")
    return act


def merged_after(standard: Path, project: Path, tmp_path: Path, acts: dict,
                 own: tuple | None = None,
                 sources: tuple = (UPSTREAM_TARGET, BOOTSTRAP_SOURCE)
                 ) -> tuple:
    """`(root, the standard moved on)`: (a)'s two applies, each followed
    on its branch by `acts[branch]`, then shape/b merging shape/a. `own`,
    `(path, content, *lines)`, is a file of the project's own that main
    gains first: `content` where it is bytes, else the committed blob of
    the copy it names, byte for byte, then `lines`. `sources` are the
    standard's files C2 and C3 move on."""
    root = under_an_awkward_name(project, tmp_path)
    moved, c2, c3, _frozen = the_standard_moved(standard, tmp_path,
                                                *sources)
    if own:
        path, content, *lines = own
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_bytes(
            (content if isinstance(content, bytes)
             else blob_at(root, f"HEAD:{content}")) + b"".join(lines))
        git("add", "--", path, cwd=root)
        commit_in(root, f"the project's own {path}")
    for commit, branch in ((c2, "shape/a"), (c3, "shape/b")):
        apply_on(moved, root, commit, branch)
        if branch in acts:
            acts[branch](root)
    merge_a_into_b(root)
    return root, moved


def blob_at(root: Path, spec: str) -> bytes:
    """The blob `git cat-file` reads at `spec`, as bytes."""
    return subprocess.run(["git", "cat-file", "blob", spec], cwd=str(root),
                          capture_output=True, check=True).stdout


#: Each rename's merge: what each side does after its `apply`, the stages
#: the merge leaves at the new name, and what the `why` then says of it.
RENAMES = {
    "renamed-on-the-side-ours-takes": (
        {"shape/b": renamed(MAKEFILE, RENAMED)}, [1, 2, 3],
        "so neither side is taken whole: a person merges it by hand, "
        "keeping the hunks git merged"),
    "renamed-on-the-other-side": (
        {"shape/a": renamed(MAKEFILE, RENAMED)}, [1, 2, 3],
        "so neither side is taken whole: a person merges it by hand, "
        "keeping the hunks git merged"),
    "renamed-on-one-side-deleted-on-the-other": (
        {"shape/b": renamed(MAKEFILE, RENAMED), "shape/a": deleted(MAKEFILE)},
        [1, 2],
        "and one side alone holds it, so neither side is taken whole: a "
        "person keeps or deletes it by hand"),
}

#: What the `why` adds where the pin taken here lists the old name, and
#: what the doctor says once the merge is finished (review of PR #781).
STILL_LISTED = ("The pin taken here still lists Makefile, so this doctor "
                "reports it missing once the merge is finished, unless it is "
                "renamed back")


@pytest.mark.parametrize("merge", sorted(RENAMES))
def test_a_copy_renamed_on_one_side_is_named_for_a_person(
        standard, project, tmp_path, merge):
    """Both copies re-copied by `apply` on both sides, and on ONE side the
    project renames its Makefile to build.mk, while the other edits it, or
    deletes it. git takes the conflict to the new name, a path no pin has
    a row for, so the `why` and `left_for_a_person` said nothing of it, and
    only the `merge` row listed it (#753). Its stage 1 is the merge base's
    own Makefile, so the `why` now names build.mk as renamed from that copy
    and gives it to a person, and the NEXT never takes it; bootstrap.py is
    still taken. Run, the NEXT leaves build.mk as the merge left it.

    The pin taken here still lists the Makefile, and the `why` says what
    the doctor says once the merge is finished with build.mk kept: the
    Makefile missing (review of PR #781)."""
    acts, held, tail = RENAMES[merge]
    root, moved = merged_after(standard, project, tmp_path, acts)
    assert sorted(index_stages(root, RENAMED)) == held
    _verdict, rows = rows_from(moved, root)
    currency = assert_both_rows_name_it(rows)
    assert pasted(currency["next"])[3:] == [
        "checkout", "--ours", "--", SHAPE_PIN, BOOTSTRAP], currency["next"]
    assert currency["detail"]["left_for_a_person"] == [
        RENAMED, "project.yaml"], currency["detail"]
    assert f"{RENAMED}, renamed from the copy {MAKEFILE}, is conflicted " \
        f"too, and no pin has a row for it under its new name, {tail}. " \
        f"{STILL_LISTED}. Then finish" in currency["why"], currency["why"]
    before = (root / RENAMED).read_bytes()
    run_pasted(currency["next"])
    assert sorted(index_stages(root, RENAMED)) == held
    assert (root / RENAMED).read_bytes() == before
    assert finished_keeping(root, tmp_path, moved, RENAMED) \
        == "DRIFTED (1 copy-missing)"


def finished_keeping(root: Path, tmp_path: Path, moved: Path, name: str,
                     dropped: tuple = ()) -> str:
    """The merge, its NEXT run, finished by a person who keeps `name` as
    the side taken holds it, removes each of `dropped`, merges
    `project.yaml` and commits; the doctor's verdict then, out of the
    standard moved on."""
    (root / name).write_bytes(stage_of(root, 2, name))
    if dropped:
        git("rm", "-q", "--", *dropped, cwd=root)
    merge_by_ours(root, tmp_path, "project.yaml")
    git("add", "--", SHAPE_PIN, BOOTSTRAP, name, "project.yaml", cwd=root)
    commit_in(root, f"merge shape/a, {name} kept")
    return json.loads(doctor(moved, root, "--json").stdout)["verdict"]


def test_a_rename_the_kept_pin_has_no_row_for_says_nothing_is_missing(
        standard, project, tmp_path):
    """The Makefile renamed on the side `--ours` takes, and that side's pin
    restaged without the Makefile's row: only the other side's pin calls
    it a copy. build.mk is still named as renamed from it, but the pin
    taken here does not list it, so the `why` says nothing of it being
    reported missing; finished with build.mk kept, the merge is not
    `copy-missing` (round 3 of the review of PR #781)."""
    root, moved = merged_after(standard, project, tmp_path,
                               {"shape/b": renamed(MAKEFILE, RENAMED)})
    a_pin_without_a_row(root, 2, MAKEFILE)
    _verdict, rows = rows_from(moved, root)
    currency = assert_both_rows_name_it(rows)
    assert f"{RENAMED}, renamed from the copy {MAKEFILE}, is conflicted " \
        "too" in currency["why"], currency["why"]
    assert "still lists" not in currency["why"], currency["why"]
    run_pasted(currency["next"])
    verdict = finished_keeping(root, tmp_path, moved, RENAMED)
    assert "copy-missing" not in verdict, verdict
    assert verdict.startswith("COMPLIANT"), verdict


#: Bytes of a file of the project's own that no other path holds.
NOTES = b"# Notes this project keeps, in no copy of the standard.\n"

#: Renames the rule never calls a copy's (review of PR #781): a file of
#: the project's own, `(path, content)` as `merged_after` takes it, in
#: the merge base; the path the merge then conflicts at; and what each
#: side does. The own file renamed, with a copy's bytes or bytes of its
#: own, or the copy renamed beside an own file holding its bytes.
NOT_A_COPYS_RENAME = {
    "the-projects-own-file-renamed": (
        ("tools/bootstrap.py", BOOTSTRAP), "tools/boot.py",
        {"shape/a": edited("tools/bootstrap.py", C2_LINE),
         "shape/b": renamed("tools/bootstrap.py", "tools/boot.py",
                            C3_LINE)}),
    "the-copy-renamed-beside-its-twin": (
        ("tools/Makefile.orig", MAKEFILE), RENAMED,
        {"shape/b": renamed(MAKEFILE, RENAMED)}),
    "the-projects-own-unique-file-renamed": (
        ("docs/notes.md", NOTES), "docs/n.md",
        {"shape/a": edited("docs/notes.md", C2_LINE),
         "shape/b": renamed("docs/notes.md", "docs/n.md", C3_LINE)}),
}


@pytest.mark.parametrize("merge", sorted(NOT_A_COPYS_RENAME))
def test_a_rename_of_no_copy_names_nothing(standard, project, tmp_path,
                                           merge):
    """A file of the project's own, renamed on one side and edited on the
    other, conflicts under its new name with the base's blob of it as
    stage 1. Where that blob is a copy's too, #781's first head named the
    file a rename of the copy, though a file of the project's own is never
    named; the copy renamed beside such a twin holds a blob two paths share
    as well. One blob, two paths: neither is called a rename. And where no
    copy holds the blob, the one path holding it is no copy: nothing is
    called a rename either (review of PR #781, rounds 1 and 3)."""
    own, new, acts = NOT_A_COPYS_RENAME[merge]
    root, moved = merged_after(standard, project, tmp_path, acts, own)
    assert sorted(index_stages(root, new)) == [1, 2, 3]
    assert stage_of(root, 1, new) == blob_at(root, f"main:{own[0]}")
    _verdict, rows = rows_from(moved, root)
    currency = assert_both_rows_name_it(rows)
    assert new not in currency["detail"].get("left_for_a_person", []), \
        currency["detail"]
    assert new not in currency["why"], currency["why"]


# --- a copy renamed on both sides (#783) -------------------------------------

#: The names each side gives the Makefile: the side `--ours` takes, and the
#: other side.
OURS_NAME, THEIRS_NAME = "a.mk", "b.mk"

#: Both sides rename the Makefile, after `apply` runs that leave it as the
#: merge base holds it, unless the standard moves it too.
BOTH_RENAME = {"shape/a": renamed(MAKEFILE, THEIRS_NAME),
               "shape/b": renamed(MAKEFILE, OURS_NAME)}

#: Both, the Makefile edited on ours.
EDITED_ON_OURS = {**BOTH_RENAME,
                  "shape/b": renamed(MAKEFILE, OURS_NAME, OWN_LINE)}

#: The standard's files C2 and C3 move on where the Makefile moves too, so
#: neither side's commit holds the merge base's blob of it.
THE_MAKEFILE_MOVES = (UPSTREAM_TARGET, BOOTSTRAP_SOURCE)

#: A file of the project's own beside the Makefile: its twin, where main
#: gains it with the Makefile's bytes.
TWIN = "tools/Makefile.orig"


def in_step(path: str, like: str):
    """An act on a branch: `path` given `like`'s bytes, committed, as a
    project keeps its own twin of a copy in step with the copy."""
    def act(root: Path) -> None:
        (root / path).write_bytes((root / like).read_bytes())
        git("add", "--", path, cwd=root)
        commit_in(root, f"{path} in step with {like}")
    return act


def in_turn(*acts):
    """One act on a branch: each of `acts` in turn."""
    def act(root: Path) -> None:
        for each in acts:
            each(root)
    return act


#: Both sides rename the Makefile and the project's own twin of it, ours
#: keeping the twin in step with its a.mk first, so ours' commit holds
#: a.mk's bytes at two new names (review of PR #789, round 3).
TWIN_KEPT_IN_STEP = {
    "shape/a": in_turn(renamed(MAKEFILE, THEIRS_NAME),
                       renamed(TWIN, "tools/y.mk")),
    "shape/b": in_turn(renamed(MAKEFILE, OURS_NAME),
                       in_step(TWIN, OURS_NAME),
                       renamed(TWIN, "tools/x.mk")),
}


def both_proved(taken_here: str, other: str) -> str:
    """What the `why` says of the Makefile where each side's new name is
    proved, the side taken here's first."""
    return (f"renamed to {taken_here} on the side taken here and to {other} "
            "on the other side, and no pin lists the new names, so neither "
            "name is taken: a person keeps one name, or both, by hand")


def one_proved(name: str, on: str, unproved: str) -> str:
    """What the `why` says of the Makefile where one side's new name,
    `name`, is proved, on the side `on`, and `unproved`'s is not."""
    return (f"renamed to {name} on {on}, and no pin lists the new name; "
            f"where {unproved} put it is not proved here, so neither name is "
            "taken: a person settles where it goes, by hand")


#: What the `why` says of the Makefile where neither side's name is proved.
NONE_PROVED = ("and where either side put it is not proved here, so neither "
               "name is taken: a person settles where it goes, by hand")
TAKEN_HERE, OTHER_SIDE = "the side taken here", "the other side"


def ours_does_not_read(root: Path) -> None:
    """Ours' stage of the shape pin as bytes that do not read, so the NEXT
    takes `--theirs` (#752)."""
    a_pin_restaged(root, 2, lambda _blob: UNREADABLE_PIN)


def the_kept_pin_lacks_its_row(root: Path) -> None:
    """Ours' stage of the shape pin without the Makefile's row: only the
    other side's pin calls it a copy (#687)."""
    a_pin_without_a_row(root, 2, MAKEFILE)


def no_merge_head(root: Path) -> None:
    """MERGE_HEAD gone, as a cherry-pick or a rebase leaves its conflicts:
    git names no merge base."""
    git("update-ref", "-d", "MERGE_HEAD", cwd=root)


class Twice(NamedTuple):
    """A merge in which both sides rename the Makefile."""
    #: What each side does after its `apply`.
    acts: dict
    #: What the `why` says of the Makefile after "gone on both sides of the
    #: merge, ".
    said: str
    #: What is left to a person.
    left: list
    #: A file of the project's own main gains first, as `merged_after`
    #: takes it.
    own: tuple | None = None
    #: The standard's files C2 and C3 move on.
    sources: tuple = (BOOTSTRAP_SOURCE,)
    #: What is done to the merge before the doctor reads it.
    then: Callable | None = None
    #: The side the NEXT takes.
    side: str = "--ours"
    #: Whether the `why` says the pin taken here still lists the Makefile.
    listed: bool = True
    #: The verdict once the merge is finished keeping a.mk, where asked.
    finished: str | None = "DRIFTED (1 copy-missing)"


#: Each merge in which both sides rename the Makefile, by what proves each
#: new name: the merge base's blob of it, or the bytes the side's own pin
#: row records (review of PR #789), at the side's own commit, and at one
#: path of it (round 3).
TWICE = {
    "renamed-on-both-sides": Twice(
        BOTH_RENAME, both_proved(OURS_NAME, THEIRS_NAME),
        [MAKEFILE, OURS_NAME, THEIRS_NAME, "project.yaml"]),
    "renamed-on-both-sides-edited-on-ours": Twice(
        EDITED_ON_OURS, one_proved(THEIRS_NAME, OTHER_SIDE, TAKEN_HERE),
        [MAKEFILE, THEIRS_NAME, "project.yaml"]),
    "renamed-on-both-sides-beside-a-twin": Twice(
        BOTH_RENAME, NONE_PROVED, [MAKEFILE, "project.yaml"],
        own=(TWIN, MAKEFILE)),
    "renamed-on-both-sides-a-twin-kept-in-step": Twice(
        TWIN_KEPT_IN_STEP, one_proved(THEIRS_NAME, OTHER_SIDE, TAKEN_HERE),
        [MAKEFILE, THEIRS_NAME, "project.yaml"],
        own=(TWIN, MAKEFILE, OWN_LINE), finished=None),
    "renamed-on-both-sides-theirs-moving-its-row": Twice(
        {**BOTH_RENAME, "shape/a": renamed(MAKEFILE, THEIRS_NAME, row=True)},
        one_proved(OURS_NAME, TAKEN_HERE, OTHER_SIDE),
        [MAKEFILE, OURS_NAME, THEIRS_NAME, "project.yaml"]),
    "renamed-on-both-sides-theirs-taken": Twice(
        BOTH_RENAME, both_proved(THEIRS_NAME, OURS_NAME),
        [MAKEFILE, OURS_NAME, THEIRS_NAME, "project.yaml", BOOTSTRAP],
        then=ours_does_not_read, side="--theirs", finished=None),
    "renamed-on-both-sides-theirs-taken-edited-on-ours": Twice(
        EDITED_ON_OURS, one_proved(THEIRS_NAME, TAKEN_HERE, OTHER_SIDE),
        [MAKEFILE, THEIRS_NAME, "project.yaml", BOOTSTRAP],
        then=ours_does_not_read, side="--theirs", finished=None),
    "renamed-on-both-sides-the-kept-pin-without-its-row": Twice(
        BOTH_RENAME, both_proved(OURS_NAME, THEIRS_NAME),
        [MAKEFILE, OURS_NAME, THEIRS_NAME, "project.yaml"],
        then=the_kept_pin_lacks_its_row, listed=False,
        finished="COMPLIANT, SHAPE BEHIND (0 upstream-changed, "
                 "1 upstream-added)"),
    "renamed-on-both-sides-the-standard-moved": Twice(
        BOTH_RENAME, both_proved(OURS_NAME, THEIRS_NAME),
        [MAKEFILE, OURS_NAME, THEIRS_NAME, "project.yaml"],
        sources=THE_MAKEFILE_MOVES),
    "renamed-on-both-sides-the-standard-moved-beside-a-twin": Twice(
        BOTH_RENAME, both_proved(OURS_NAME, THEIRS_NAME),
        [MAKEFILE, OURS_NAME, THEIRS_NAME, "project.yaml"],
        own=(TWIN, MAKEFILE), sources=THE_MAKEFILE_MOVES),
    "renamed-on-both-sides-the-standard-moved-a-twin-kept-in-step": Twice(
        TWIN_KEPT_IN_STEP, one_proved(THEIRS_NAME, OTHER_SIDE, TAKEN_HERE),
        [MAKEFILE, THEIRS_NAME, "project.yaml"],
        own=(TWIN, MAKEFILE), sources=THE_MAKEFILE_MOVES, finished=None),
    "renamed-on-both-sides-the-standard-moved-the-base-holding-ours": Twice(
        BOTH_RENAME, one_proved(THEIRS_NAME, OTHER_SIDE, TAKEN_HERE),
        [MAKEFILE, THEIRS_NAME, "project.yaml"],
        own=("tools/Makefile.next", MAKEFILE, C2_LINE, C3_LINE),
        sources=THE_MAKEFILE_MOVES),
    "renamed-on-both-sides-the-standard-moved-no-merge-head": Twice(
        BOTH_RENAME, NONE_PROVED, [MAKEFILE, "project.yaml"],
        sources=THE_MAKEFILE_MOVES, then=no_merge_head, finished=None),
}


@pytest.mark.parametrize("merge", sorted(TWICE))
def test_a_copy_renamed_on_both_sides_is_named_for_a_person(
        standard, project, tmp_path, merge):
    """Both sides rename the Makefile, to a.mk on the side `--ours` takes
    and to b.mk on the other. git leaves the Makefile `DD`, stage 1 alone,
    and each new name added by one side alone, with no stage 1, so #781's
    rule saw neither, and the Makefile got the copies' sentence, keeping
    "the hunks git merged" where git merged none (#783).

    Now the Makefile is gone on both sides, and each new name is named
    where the commit of the side that made it holds there the merge base's
    blob of the Makefile, or the bytes that commit's own pin row for the
    Makefile records, and the base holds those bytes at no other path.
    Edited on ours, git writes its merge to both names and ours' commit
    holds the edit, so only b.mk is proved, and the `why` says ours' is
    not; beside a twin of the Makefile neither is. Where the standard
    moved the Makefile, neither commit holds the base's blob, and each
    side's pin row proves its name, a twin of the base's bytes beside it
    or not; a base holding ours' bytes at another path proves ours' name
    nothing, and with no MERGE_HEAD no base is named, so nothing is proved
    (review of PR #789). Where ours keeps its own twin of the Makefile in
    step with a.mk and both sides rename the twin too, ours' commit holds
    a.mk's bytes at two new names, and git pairs one with the twin: ours'
    name is not proved, the standard moved or not (round 3).

    A name a pin has a row for is named by that row alone: theirs, moving
    its row to b.mk, gets b.mk named once, as the other side's copy, and
    ours' a.mk proved. Taken `--theirs`, b.mk is the side taken here's.
    Where the kept pin has no row for the Makefile, both names are still
    named, nothing is said to go missing, and the merge finished keeping
    a.mk is no `copy-missing`; where it still lists the Makefile, the
    `why` says so, and the finished merge is `copy-missing`. Every name
    is said once, and only a copy left to a person is a merge of hunks."""
    case = TWICE[merge]
    root, moved = merged_after(standard, project, tmp_path, case.acts,
                               case.own, case.sources)
    if case.then:
        case.then(root)
    assert [sorted(index_stages(root, name))
            for name in (MAKEFILE, OURS_NAME, THEIRS_NAME)] \
        == [[1], [2], [3]]
    _verdict, rows = rows_from(moved, root)
    currency = assert_both_rows_name_it(rows)
    why, left = currency["why"], case.left
    left_whole = BOOTSTRAP in left
    assert pasted(currency["next"])[3:] == [
        "checkout", case.side, "--", SHAPE_PIN,
        *([] if left_whole else [BOOTSTRAP])], currency["next"]
    assert currency["detail"]["left_for_a_person"] == left, \
        currency["detail"]
    listed = f". {STILL_LISTED}" if case.listed else ""
    assert f"{MAKEFILE} is gone on both sides of the merge, {case.said}" \
        f"{listed}. Then finish" in why, why
    assert ("still lists" in why) == case.listed, why
    assert [why.count(name) for name in left if name != MAKEFILE] \
        == [1] * (len(left) - 1), why
    assert why.count("hunks") == int(left_whole), why
    run_pasted(currency["next"])
    if case.finished:
        assert finished_keeping(root, tmp_path, moved, OURS_NAME,
                                (MAKEFILE, THEIRS_NAME)) == case.finished
