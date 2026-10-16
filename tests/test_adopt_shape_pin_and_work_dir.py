# SPDX-License-Identifier: Apache-2.0
"""What the root keeps at the shape's own pin, and a work directory this user
cannot write in, refused before any leg exists (#524).

Two of the v1.0.0 known limits on #457, L1-K1 and L1-K10, measured on main
8beb3d92 and again on bfed143, the v1.0.0 release commit:

- L1-K1. `_kept_pin_findings` (#273) asked whether the plan keeps a path
  where `execute` writes each DECLARED pin's file, and never asked it of the
  shape's own pin, `contracts/shape-pin.yaml`. A file the root kept there,
  with a pin or without, passed `check`, and so did a link there that leads
  to something: `contracts/shape-pin.yaml -> openglass-pin.yaml`, which finds
  the pin `place` writes first, or `-> README.md`. `execute` made and pushed
  both legs, wrote the shape's pin beside the source's file, under
  `shape/`, and failed its verification as `adopt-shape-pin-unreadable`,
  exit 1. Now the same rule asks it of the shape's pin, under #273's code,
  `plan-root-holds-pin`, its sentence naming the shape's pin.
- One link, one finding. A link there that leads nowhere was the walk's
  (#178, #183: `plan-root-symlink`), because the shape would write its pin
  through it. The kept-pin rule names it now, as it names a link AT a
  declared pin's file, and the walk does not say it again
  (`_links_at_a_pin`).
- L1-K10. `--work-dir` was made (`mkdir(exist_ok=True)`) and never written
  in before `_create_leg_remotes`. With `chmod 500` on it, `check --work-dir`
  said `plan ok`, and `execute --work-dir` made and pushed both legs and
  stopped `extracting the spec leg`, exit 2, with or without a link above a
  path the shape writes (`.github -> ci`). Now `execute` makes and removes a
  directory in it first, before it opens the source, and refuses as
  `adopt-work-dir-unwritable`, naming it; `check --work-dir` names the same
  as a finding, beside the plan's own, and refuses it as `execute` does
  where it would clone an `org/repo` source there.

`chmod` keeps neither root nor a Windows user from making a directory, so
the work-directory tests skip where it cannot (`unwritable_work`, as #183's
J4 test does).
"""

from __future__ import annotations

import errno
import os
import shutil
from pathlib import Path

import pytest

from conftest import ADOPT, run_script
from test_adopt_root_symlinks import (  # noqa: F401
    A_PIN, CASE_ASIDE, CONTRACTS, GITHUB, GLASS, PIN_FILE, PIN_NAME, README,
    REAL_CONTRACTS, REMOTES, ROOT, ROOT_HOLDS_PIN, SHAPE_PIN, WORK, WORK_FLAG,
    adopter, check, declare, execute_args, links_as_links,
    no_filter_repo_probe, no_leg_was_created, pin_row, planned, refused_by,
    ticked, unwritable_work,
)

WORK_DIR_UNWRITABLE = "adopt-work-dir-unwritable"
MINE = "mine: 1\n"
NOWHERE = "nowhere.yaml"
#: The two kinds of source entry the finding names here.
A_FILE, A_SYMLINK = "file", "symlink"
SHAPE_PIN_TWIN = "contracts/Shape-Pin.yaml"
#: The entry the source's `contracts/` is kept in the root under.
CONTRACTS_ENTRY = f"{CONTRACTS}/"


def finding_lines(result) -> list[str]:
    """Every FINDING `check` printed, whatever its code."""
    return [line for line in result.stderr.splitlines()
            if line.startswith("FINDING ")]


def held(kind: str, path: str, where: str = "at", aside: str = "") -> str:
    """The line `check` prints, and `execute`'s refusal carries, for the
    `kind` (`file`, `symlink`) at `path` that the plan keeps `where` the
    shape writes its own pin."""
    found = "directory" if where == "inside" else kind
    through = (", or written through it where it leads nowhere"
               if kind == A_SYMLINK else "")
    return (f"FINDING {ROOT_HOLDS_PIN}: the plan keeps the {kind} "
            f"{ticked(path)} in the assembly root under the entry "
            f"{ticked(CONTRACTS_ENTRY)}, {where} {ticked(SHAPE_PIN)}{aside}, "
            "where `execute` writes the shape's own pin: the openRepoShape "
            "commit the root's copies came from and each copy's digest, "
            "which `execute`'s verification, the root's own "
            "`validate-pins.py` and `make bootstrap` read at that path. The "
            f"split would hold the source's {found} there, and the shape's "
            f"pin beside it, under `shape/`{through}: send "
            f"{ticked(CONTRACTS_ENTRY)} to a leg, `drop` it, or rename it in "
            "the source and re-run `plan`.")


def refused_alone(adopter, base: Path, plan: Path, line: str) -> None:
    """`check` exits 1 with `line` and no other finding, and `execute`
    refuses with that line alone, before any leg exists."""
    checked = check(plan)
    assert checked.returncode == 1, checked.stderr + checked.stdout
    assert finding_lines(checked) == [line], checked.stderr
    refusal = refused_by(adopter, execute_args(base, plan))
    assert refusal.code == ROOT_HOLDS_PIN
    assert refusal.detail.splitlines()[1:] == [f"  {line}"], refusal.detail
    no_leg_was_created(base)


# ---------------------------------------------------------------------------
# L1-K1: a path the root keeps at the shape's own pin
# ---------------------------------------------------------------------------

#: `(the source's own file, the kind the finding names, where, aside)`.
KEPT_AT_THE_PIN = [
    pytest.param(SHAPE_PIN, "at", "", id="a-file"),
    pytest.param(SHAPE_PIN_TWIN, "at", CASE_ASIDE, id="a-case-twin"),
    pytest.param(f"{SHAPE_PIN}/notes.md", "inside", "", id="a-directory"),
]


@pytest.mark.parametrize("pinned", [
    pytest.param(False, id="no-pin"), pytest.param(True, id="a-pin")])
@pytest.mark.parametrize(("path", "where", "aside"), KEPT_AT_THE_PIN)
def test_a_path_kept_at_the_shapes_pin_is_found_and_refused_before_any_leg(
        adopter, no_filter_repo_probe, tmp_path, pinned, path, where,
        aside):
    """The source's `contracts/` answered `root` keeps its own
    `contracts/shape-pin.yaml`, a directory of that name, or a case twin of
    it. `place` finds the first two there and writes the shape's pin beside
    them, under `shape/`, so the root's `contracts/shape-pin.yaml` is the
    source's. It finds the twin there only on a disk that ignores case, as
    macOS's and Windows's do, and the assembly is cloned on those too; on a
    disk that keeps case the twin stands beside the shape's pin, which is
    why the finding says `once case is ignored` of it. With a pin declared
    or without, `check` names it once, and `execute` refuses with that line
    before any leg exists."""
    files, legs = REAL_CONTRACTS
    _, plan = planned(tmp_path, {**files, path: MINE}, {}, legs)
    if pinned:
        declare(plan, A_PIN)
    refused_alone(adopter, tmp_path, plan, held(A_FILE, path, where, aside))


#: `(the symlink, where it leads, whether a pin is declared, aside)`.
LINKS_AT_THE_PIN = [
    # The issue's own: `place` writes the pin's file first, so the link
    # finds a file and the shape's pin goes beside it.
    pytest.param(SHAPE_PIN, PIN_NAME, True, "",
                 id="to-the-pins-file-place-writes-first"),
    pytest.param(SHAPE_PIN, README, False, "", id="to-a-kept-file"),
    # The walk's before (#183): the shape would write its pin through it.
    pytest.param(SHAPE_PIN, NOWHERE, False, "", id="leading-nowhere"),
    pytest.param(SHAPE_PIN, NOWHERE, True, "",
                 id="leading-nowhere-with-a-pin"),
    pytest.param(SHAPE_PIN_TWIN, NOWHERE, False, CASE_ASIDE,
                 id="a-case-twin-leading-nowhere"),
]


@pytest.mark.parametrize(("link", "target", "pinned", "aside"),
                         LINKS_AT_THE_PIN)
def test_a_link_at_the_shapes_pin_is_one_finding_by_the_rule_that_sees_it(
        adopter, no_filter_repo_probe, links_as_links, tmp_path, link,
        target, pinned, aside):
    """A symlink kept AT the shape's pin is the kept-pin rule's, wherever it
    leads, as a symlink AT a declared pin's file is (#273). The walk follows
    the same path and, where the link leads nowhere, would refuse it too;
    it does not say the same link again: one link, one finding, and
    `execute` refuses with that line alone."""
    files, legs = REAL_CONTRACTS
    _, plan = planned(tmp_path, files, {link: target}, legs)
    if pinned:
        declare(plan, A_PIN)
    refused_alone(adopter, tmp_path, plan,
                  held(A_SYMLINK, link, aside=aside))


@pytest.mark.skipif(shutil.which("git-filter-repo") is None,
                    reason="`execute` refuses without git filter-repo first")
def test_execute_refuses_the_issues_link_and_makes_no_leg(tmp_path):
    """The issue's run, as a person makes it: with a pin, and
    `contracts/shape-pin.yaml -> openglass-pin.yaml` kept, `execute` made
    both legs and exited 1 with `adopt-shape-pin-unreadable`. It now exits 2
    with `plan-root-holds-pin`, and no leg repository exists."""
    files, legs = REAL_CONTRACTS
    _, plan = planned(tmp_path, files, {SHAPE_PIN: PIN_NAME}, legs)
    declare(plan, A_PIN)
    remotes = tmp_path / REMOTES
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(remotes),
                        WORK_FLAG, str(tmp_path / WORK))
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"\n  {held(A_SYMLINK, SHAPE_PIN)}\n" in result.stderr
    assert result.stderr.startswith(f"REFUSED {ROOT_HOLDS_PIN}: ")
    assert not remotes.exists()


# ---------------------------------------------------------------------------
# One kept file, one finding (#651: L1-06 and L1-07 of #457)
# ---------------------------------------------------------------------------

#: `(the source's file at a pin's path, the plan's pins, what the one
#: finding says `execute` writes there)`.
ONE_FILE_TWO_PINS = [
    pytest.param(SHAPE_PIN, "pins:\n" + pin_row("Shape"),
                 "the shape's own pin", id="a-product-named-shape"),
    pytest.param(PIN_FILE, "pins:\n" + pin_row(GLASS) + pin_row("OpenGlass"),
                 f"the pin the plan declares on `{GLASS}`",
                 id="two-products-one-file"),
]


@pytest.mark.parametrize(("kept", "block", "written"), ONE_FILE_TWO_PINS)
def test_a_kept_file_two_pins_are_written_at_is_named_once(
        adopter, no_filter_repo_probe, tmp_path, kept, block, written):
    """L1-06. A `pins:` edited to write two pins at one file is already
    `plan-pin-collides`: a product named `Shape`, whose file is the shape's
    own pin, or `openGlass` with `OpenGlass`. A file the root keeps there
    was named by `plan-root-holds-pin` once for each pin. It is one file,
    and one line names it, in `check` and in `execute`'s refusal."""
    files, legs = REAL_CONTRACTS
    _, plan = planned(tmp_path, {**files, kept: MINE}, {}, legs)
    declare(plan, block)
    checked = check(plan)
    assert checked.returncode == 1, checked.stderr + checked.stdout
    said = [line for line in finding_lines(checked)
            if line.startswith(f"FINDING {ROOT_HOLDS_PIN}: ")]
    assert len(said) == 1, checked.stderr
    assert f"where `execute` writes {written}" in said[0], said[0]
    refusal = refused_by(adopter, execute_args(tmp_path, plan))
    assert refusal.detail.count(f"FINDING {ROOT_HOLDS_PIN}: ") == 1, \
        refusal.detail
    no_leg_was_created(tmp_path)


def test_the_shapes_pin_and_its_copy_kept_are_one_finding(
        adopter, no_filter_repo_probe, tmp_path):
    """L1-07. The root keeps `contracts/shape-pin.yaml` and
    `shape/contracts/shape-pin.yaml`. The shape's pin would be written
    beside the first, at the second, so #262's `plan-root-blocks-shape-copy`
    named the second and `plan-root-holds-pin` the first: two findings, one
    cause. With the first gone the shape writes its pin at its own path and
    nothing at the second, so the one finding is the first's, and `execute`
    refuses with that line alone."""
    files, legs = REAL_CONTRACTS
    _, plan = planned(tmp_path,
                      {**files, SHAPE_PIN: MINE, f"shape/{SHAPE_PIN}": MINE},
                      {}, {**legs, "shape/": ROOT})
    refused_alone(adopter, tmp_path, plan, held(A_FILE, SHAPE_PIN))


# ---------------------------------------------------------------------------
# L1-K10: a work directory this user cannot write in
# ---------------------------------------------------------------------------

FIX = ("Pass a --work-dir this user can write in, or none: without one, "
       "each run makes a new one.")

#: `(files, links, legs)`: a plan `check` passes, and the same with a link
#: above a path the shape writes, which `execute` asks `git` about in its
#: work directory (#183).
CHECKED_OK = [
    pytest.param(REAL_CONTRACTS[0], {}, REAL_CONTRACTS[1], id="no-link"),
    pytest.param({"ci/workflows/ci.yml": "on: push\n"}, {GITHUB: "ci"},
                 {"ci/": ROOT, GITHUB: ROOT}, id="a-link-above"),
]


def cannot_write(work: Path) -> str:
    """Why `--work-dir work` is refused, as `check` and `execute` say it."""
    return (f"--work-dir {ticked(str(work.resolve()))} cannot be written: "
            "making a directory in it, and removing it again, failed "
            f"({os.strerror(errno.EACCES)}), and `execute` builds the spec "
            "leg, the code leg and the split there, only after it has made "
            "both leg repositories")


@pytest.mark.parametrize(("files", "links", "legs"), CHECKED_OK)
def test_check_names_a_work_directory_it_cannot_write_in(
        tmp_path, unwritable_work, files, links, legs):
    """`check --work-dir` asks the directory as `execute` will: a writable
    one passes and is left as it was, and one this user cannot write in is
    a finding that names it, where it said `plan ok`."""
    _, plan = planned(tmp_path, files, links, legs)
    writable = tmp_path / "writable"
    passed = check(plan, WORK_FLAG, str(writable))
    assert passed.returncode == 0, passed.stderr + passed.stdout
    assert list(writable.iterdir()) == []
    checked = check(plan, WORK_FLAG, str(unwritable_work))
    assert checked.returncode == 1, checked.stderr + checked.stdout
    assert finding_lines(checked) == [
        f"FINDING {WORK_DIR_UNWRITABLE}: {cannot_write(unwritable_work)}. "
        f"{FIX}"], checked.stderr


def test_check_refuses_a_source_it_would_clone_into_that_directory(
        tmp_path, unwritable_work):
    """An `org/repo` source is cloned into the work directory to be read, so
    in one this user cannot write in `check` has no source to read: it
    refuses as `execute` does, where it ended in a PermissionError
    traceback. Nothing is cloned, so nothing asks `gh`."""
    files, legs = REAL_CONTRACTS
    _, plan = planned(tmp_path, files, {}, legs)
    checked = check(plan, "--source", "acme/thing",
                    WORK_FLAG, str(unwritable_work))
    assert checked.returncode == 2, checked.stderr + checked.stdout
    assert checked.stderr == (
        f"REFUSED {WORK_DIR_UNWRITABLE}: {cannot_write(unwritable_work)}\n"
        f"Remediation: {FIX}\n")


@pytest.mark.parametrize(("files", "links", "legs"), CHECKED_OK)
def test_execute_refuses_a_work_directory_it_cannot_write_in_before_any_leg(
        adopter, no_filter_repo_probe, tmp_path, unwritable_work, files,
        links, legs):
    """`execute` asks first, before it opens the source, so before any leg
    exists, and names the directory; from the command line too, where the
    refusal comes before it asks for `git filter-repo`. It made and pushed
    both legs and stopped `extracting the spec leg`."""
    _, plan = planned(tmp_path, files, links, legs)
    refusal = refused_by(adopter, execute_args(tmp_path, plan))
    assert refusal.code == WORK_DIR_UNWRITABLE
    assert refusal.detail == cannot_write(unwritable_work)
    assert refusal.remediation == (
        f"Remediation: no leg repository was created and nothing was "
        f"pushed. {FIX}")
    no_leg_was_created(tmp_path)
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(tmp_path / REMOTES),
                        WORK_FLAG, str(unwritable_work))
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr == f"{refusal}\n"
    no_leg_was_created(tmp_path)
