# SPDX-License-Identifier: Apache-2.0
"""The `legs` and `members` NEXT cures the row it sits on, and needs no
script the root may lack (#276).

THE DEFECT. Both rows printed `python3 <root>/scripts/bootstrap.py
--root <root>` without asking whether the root had it, so a root that had lost
the file (the `shape currency` row says `copy-missing` for it) pasted `can't
open file`, exit 2. And where the file was there it did not cure the row:
bootstrap never initialises an empty mount (it prints `NOT INITIALIZED` and
stops) and never moves an existing branch whose tip is not the pin, so the
re-run doctor said the same thing.

WHAT THE LINE IS NOW is `git -C <root> submodule update --init --recursive
-- <paths>`, which needs no script and no `PYTHONPATH`. A lockstep fact no
checkout cures (no gitlink, no 40-hex pin, a gitlink that is not the pin, a
mount git cannot read a HEAD in) gets the lockstep gate instead, built the way
the `pins` and `family` rows build theirs. A holder's own bootstrap stays the
NEXT when it can run, because it carries the credential rewrite a private
member needs.

EVERY NEXT HERE IS PASTED AND RUN, from a directory that is not the root,
through `sh -c` exactly as the row printed it, and the row is asked again.
Those tests are `WINDOWS_SKIP`: `sh` is a POSIX shell, and on Windows the
reader's shell is PowerShell. The text-level assertions about what the line
IS run on every OS. A git paste gets the file protocol per subprocess through
`GIT_CONFIG_COUNT`, `GIT_CONFIG_KEY_0` and `GIT_CONFIG_VALUE_0` -- the
fixtures' remotes are bare repositories on disk, which git refuses as a
submodule URL by default -- and never `GIT_ALLOW_PROTOCOL`, which would
override git's `user` policy for the whole run.

WHAT IS ASSERTED IS WHAT THE COMMAND DOES, and the explanation after it is
read through `why_of` alone, so that moving the `   # ` tail into a field of
its own (#277) changes one helper here and not every test.

The fixtures are `test_shape_doctor`'s, imported rather than rebuilt: a
project or a holder made any other way would be a different one.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess

from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from conftest import WINDOWS_SKIP, git, rmtree
from test_shape_doctor import (  # noqa: F401
    FAMILY_MEMBER, FAMILY_NAME, GIT_IDENTITY, commit_all, doctor,
    doctor_module, holder, project, record_gitlink, rows_of,
    scaffolded_here, standard,
)

#: What every pasted git line runs under: the identity a commit needs (this
#: container has none, and neither does a fresh CI runner), the file
#: protocol for ONE process tree, and no `PYTHONPATH` from the person
#: running the suite -- a template line that needed one from the reader is
#: exactly what these tests are not allowed to depend on.
PASTE_ENV = {**{k: v for k, v in os.environ.items() if k != "PYTHONPATH"},
             **GIT_IDENTITY,
             "GIT_CONFIG_COUNT": "1",
             "GIT_CONFIG_KEY_0": "protocol.file.allow",
             "GIT_CONFIG_VALUE_0": "always",
             "PYTHONDONTWRITEBYTECODE": "1"}

#: The three characters between a NEXT's command and its explanation.
TAIL = "   # "


# --- reading a row ----------------------------------------------------------

def command_of(row: dict) -> str:
    """The command a row hands over, without its explanation."""
    return (row["next"] or "").partition(TAIL)[0]


def why_of(row: dict) -> str:
    """The sentence that explains the command: today the `   # ` tail, and
    the row's own `why` once #277 moves it there."""
    return row.get("why") or (row["next"] or "").partition(TAIL)[2]


def row_of(standard: Path, root: Path, row_id: str) -> dict:
    return rows_of(doctor(standard, root, "--json"))[row_id]


def paste(row: dict, cwd: Path) -> subprocess.CompletedProcess:
    """The row's NEXT exactly as it was printed, in a POSIX shell, from a
    directory that is not the root."""
    cwd.mkdir(exist_ok=True)
    return subprocess.run(["sh", "-c", row["next"]], cwd=str(cwd),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False, env=PASTE_ENV,
                          stdin=subprocess.DEVNULL)


def commit_in(leg: Path) -> str:
    """One commit made INSIDE a mount, which is how a leg walks off its pin;
    its sha."""
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m",
                    "work in the leg, past the pin"], cwd=str(leg),
                   capture_output=True, check=True,
                   env={**os.environ, **GIT_IDENTITY})
    return git("rev-parse", "HEAD", cwd=leg).stdout.strip()


# --- ways a root can be wrong -----------------------------------------------

def unbootstrap(root: Path, mount: str) -> None:
    """An unbootstrapped clone's mount: empty, NOT registered, and with no
    gitdir to re-attach, so putting it right has to FETCH."""
    git("submodule", "deinit", "-q", "-f", "--", mount, cwd=root)
    modules = root / ".git" / "modules" / Path(mount)
    if modules.is_dir():
        rmtree(modules)


def make_empty_mount(root: Path) -> dict:
    unbootstrap(root, "code")
    return {"paths": ["code"], "off_pin": []}


def make_branch_past_the_pin(root: Path) -> dict:
    """A commit on the leg's own TRACKING BRANCH, which is the case the old
    NEXT could not cure even with the script there: bootstrap never moves an
    existing branch whose tip is not the pin, and leaves the leg where it
    is. (On any other branch it would have checked `main` out at the pin and
    cured it.)"""
    git("checkout", "-q", "-B", "main", cwd=root / "spec")
    return {"paths": ["spec"], "off_pin": [], "commit": commit_in(
        root / "spec"), "branch": "main"}


def make_detached_past_the_pin(root: Path) -> dict:
    """A fresh recursive clone leaves every leg DETACHED at its pin, so a
    commit made in one is on no branch."""
    return {"paths": ["spec"], "off_pin": ["spec"],
            "commit": commit_in(root / "spec")}


def make_script_absent(root: Path) -> dict:
    """The issue's own reproduction: the shape copy gone AND an empty mount."""
    git("rm", "-q", "scripts/bootstrap.py", cwd=root)
    unbootstrap(root, "spec")
    return {"paths": ["spec"], "off_pin": []}


def make_repo_shape_absent(root: Path) -> dict:
    """`scripts/bootstrap.py` is there but imports `repo_shape` from beside
    itself, so a root without that file has a bootstrap that dies on import:
    it is no more a script the NEXT may name than an absent one."""
    git("rm", "-q", "scripts/repo_shape.py", cwd=root)
    unbootstrap(root, "spec")
    return {"paths": ["spec"], "off_pin": []}


CHECKOUT_SCENARIOS = {
    "empty-mount": make_empty_mount,
    "branch-past-the-pin": make_branch_past_the_pin,
    "detached-past-the-pin": make_detached_past_the_pin,
    "bootstrap-absent": make_script_absent,
    "repo-shape-absent": make_repo_shape_absent,
}


def make_gitlink_moved(root: Path) -> dict:
    """HEAD and the gitlink agree with each other and not with the pin: a
    checkout lands on the gitlink, so it cannot make HEAD the pin."""
    record_gitlink(root, "spec", commit_in(root / "spec"))
    return {}


def make_pin_not_a_commit(root: Path) -> dict:
    pin = root / "contracts" / "spec-pin.yaml"
    text = pin.read_text(encoding="utf-8")
    edited, count = re.subn(r'(?m)^commit: "[0-9a-f]{40}"$', 'commit: "main"',
                            text)
    assert count == 1, text
    pin.write_text(edited, encoding="utf-8")
    return {}


def make_head_unreadable(root: Path) -> dict:
    """The mount keeps its files and its `.git` file; the gitdir it points at
    is gone, so git cannot read a HEAD in it."""
    rmtree(root / ".git" / "modules" / "spec")
    return {}


def make_mount_with_no_git_of_its_own(root: Path) -> dict:
    """A populated directory that is not a repository. Asked in it, git walks
    up and answers with the ROOT's HEAD, so the row reads a HEAD that is not
    the leg's; and with the gitdir gone too there is nothing for an update to
    re-attach."""
    (root / "spec" / ".git").unlink()
    rmtree(root / ".git" / "modules" / "spec")
    return {}


def make_no_gitlink(root: Path) -> dict:
    """The superproject records NO gitlink for `spec` -- in the index or in
    HEAD, which `recorded_gitlink` falls back to -- so it is not a submodule
    here at all, whatever sits in the directory."""
    git("rm", "-q", "--cached", "--", "spec", cwd=root)
    subprocess.run(["git", "commit", "-q", "-m", "unmount spec"],
                   cwd=str(root), capture_output=True, check=True,
                   env={**os.environ, **GIT_IDENTITY})
    return {}


LOCKSTEP_SCENARIOS = {
    "no-gitlink": make_no_gitlink,
    "gitlink-moved": make_gitlink_moved,
    "pin-not-a-commit": make_pin_not_a_commit,
    "head-unreadable": make_head_unreadable,
    "mount-with-no-git-of-its-own": make_mount_with_no_git_of_its_own,
}


def pins_gate(module, standard: Path, root: Path, own_copy: bool) -> str:
    """What `validator_command` makes of `validate-pins.py` for this root:
    the root's own copy, or the standard's template copy."""
    used = (root / "scripts" / "validate-pins.py" if own_copy else
            standard / "templates" / "assembly-root" / "scripts"
            / "validate-pins.py")
    return module.validator_command(standard, used, own_copy,
                                    ["--root", str(root.resolve())])


# --- the legs row: what the line IS (every OS) -----------------------------

@pytest.mark.parametrize("scenario", sorted(CHECKOUT_SCENARIOS))
def test_a_leg_a_checkout_cures_is_handed_a_script_free_git_line(
        standard, project, scenario):
    """Five roots, one answer, and none of them names a script.

    The line is `git -C <root> submodule update --init --recursive -- <the
    legs>`: no interpreter, no path into the root's own `scripts/`, so a root
    that lost `bootstrap.py` (or `repo_shape.py`, which it imports) is
    handed something that can run.
    """
    made = CHECKOUT_SCENARIOS[scenario](project)
    module = doctor_module(standard)
    row = row_of(standard, project, "legs")
    assert row["status"] == "FINDING", row
    root = project.resolve()
    assert command_of(row) == (
        f"git -C {module.quote_arg(root)} submodule update --init "
        f"--recursive -- {' '.join(made['paths'])}"), row["next"]
    # (The equality above is the whole claim: a git line, no script. A
    # substring test of the command would read the TEST'S OWN tmp path.)


def test_a_legs_next_that_lists_two_legs_lists_both(standard, project):
    unbootstrap(project, "spec")
    unbootstrap(project, "code")
    module = doctor_module(standard)
    row = row_of(standard, project, "legs")
    assert command_of(row) == (
        f"git -C {module.quote_arg(project.resolve())} submodule update "
        "--init --recursive -- spec code"), row["next"]


def test_the_line_is_spelled_for_the_readers_shell(standard):
    """`quote_arg`'s two dialects, asked for on whichever host this runs on
    (the rule `copy_command` and `scaffold_command` already follow): a root
    with a space in it is single-quoted for `sh`, and PowerShell gets its own
    verbatim string, backslashes and all, in the line AND in the keep line
    the explanation names."""
    module = doctor_module(standard)
    posix_root = PurePosixPath("/srv/my atlas")
    line, why = module.submodule_update_next(
        posix_root, ["spec", "code"], [posix_root / "spec"], "leg",
        platform="posix")
    assert line == ("git -C '/srv/my atlas' submodule update --init "
                    "--recursive -- spec code"), line
    assert "git -C '/srv/my atlas/spec' branch NAME" in why, why
    nt_root = PureWindowsPath("C:/Work/My Atlas")
    line, why = module.submodule_update_next(
        nt_root, ["members/IRRS"], [nt_root / "members" / "IRRS"], "member",
        platform="nt")
    assert line == ("git -C 'C:\\Work\\My Atlas' submodule update --init "
                    "--recursive -- members/IRRS"), line
    assert "git -C 'C:\\Work\\My Atlas\\members\\IRRS' branch NAME" in why
    assert "a member on no branch" in why, why


# --- the explanation: the reflog note, when and only when ------------------

def test_the_reflog_note_is_printed_when_a_leg_is_detached_off_its_pin(
        standard, project):
    """A commit made on a detached HEAD is left only in the leg's reflog by
    the line, so the explanation says so in plain words and names the line
    that keeps it first: `git -C <leg> branch NAME`."""
    make_detached_past_the_pin(project)
    module = doctor_module(standard)
    why = why_of(row_of(standard, project, "legs"))
    leg = module.quote_arg((project / "spec").resolve())
    assert "reflog" in why, why
    assert "on no branch" in why, why
    assert f"git -C {leg} branch NAME" in why, why


@pytest.mark.parametrize("scenario", ["empty-mount", "branch-past-the-pin",
                                      "bootstrap-absent",
                                      "repo-shape-absent"])
def test_the_reflog_note_is_not_printed_when_nothing_is_detached_off_a_pin(
        standard, project, scenario):
    """Nothing can be lost in these four, so nothing is said: an empty mount
    has no commit, a commit on a branch stays on it, and a note printed
    where there is nothing to lose is a note nobody reads on the day there
    is."""
    CHECKOUT_SCENARIOS[scenario](project)
    why = why_of(row_of(standard, project, "legs"))
    assert why, "the line must say what it does"
    assert "reflog" not in why, why
    assert "branch NAME" not in why, why


def test_the_reflog_note_names_only_the_detached_leg(standard, project):
    """Two off-pin legs, one on a branch and one on a detached HEAD: only the
    detached one is named."""
    git("checkout", "-q", "-b", "work", cwd=project / "code")
    commit_in(project / "code")
    commit_in(project / "spec")
    module = doctor_module(standard)
    row = row_of(standard, project, "legs")
    assert command_of(row).endswith("-- spec code"), row["next"]
    why = why_of(row)
    assert f"git -C {module.quote_arg((project / 'spec').resolve())} " \
        "branch NAME" in why, why
    assert "code branch NAME" not in why, why
    assert why.count("branch NAME") == 1, why


def test_a_leg_at_its_pin_on_a_branch_has_no_finding_and_so_no_note(
        standard, project):
    """The control: detached is not the question when HEAD is the pin."""
    git("checkout", "-q", "-B", "tracking", cwd=project / "spec")
    row = row_of(standard, project, "legs")
    assert row["status"] == "ok", row
    assert row["next"] is None, row


@pytest.mark.parametrize("scenario", sorted(CHECKOUT_SCENARIOS))
def test_the_explanation_carries_no_character_a_pasted_tail_would_break_on(
        standard, project, scenario):
    """New tail text has none of `;`, `'`, a backtick or a parenthesis: a
    shell that does not read `#` as a comment reads each as syntax (the
    precedent of #267; #277 moves the text out of the NEXT)."""
    CHECKOUT_SCENARIOS[scenario](project)
    why = why_of(row_of(standard, project, "legs"))
    for character in (";", "'", "`", "(", ")"):
        assert character not in why, (character, why)


def test_the_bootstrap_sentence_is_said_only_where_the_script_can_run(
        standard, project, tmp_path):
    """`then make bootstrap puts each leg on its tracking branch` is what the
    old NEXT's tail said and the line now leaves to a script the root may
    not have. It is kept when the root has what bootstrap needs and left out
    when it has not -- a sentence that sends a reader to a command that
    cannot run is the defect over again."""
    make_empty_mount(project)
    assert "make bootstrap" in why_of(row_of(standard, project, "legs"))
    lost = tmp_path / "Lost"
    shutil.copytree(project, lost, symlinks=True)
    git("rm", "-q", "scripts/bootstrap.py", cwd=lost)
    assert "bootstrap" not in why_of(row_of(standard, lost, "legs"))
    lost_import = tmp_path / "LostImport"
    shutil.copytree(project, lost_import, symlinks=True)
    git("rm", "-q", "scripts/repo_shape.py", cwd=lost_import)
    assert "bootstrap" not in why_of(row_of(standard, lost_import, "legs"))


# --- the legs row: pasted, and the row asked again (POSIX shells) ----------

@WINDOWS_SKIP
@pytest.mark.parametrize("scenario", ["empty-mount", "branch-past-the-pin",
                                      "bootstrap-absent",
                                      "repo-shape-absent"])
def test_a_pasted_legs_next_exits_zero_and_the_legs_row_is_ok(
        standard, project, tmp_path, scenario):
    """The point of the whole change: paste what the row printed, from
    somewhere else, and the row is green. Four of the five roots of
    `CHECKOUT_SCENARIOS`; the detached one has a commit to keep first and is
    the next test."""
    made = CHECKOUT_SCENARIOS[scenario](project)
    row = row_of(standard, project, "legs")
    assert row["status"] == "FINDING", row
    result = paste(row, tmp_path / "elsewhere")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "can't open file" not in result.stdout + result.stderr
    after = row_of(standard, project, "legs")
    assert after["status"] == "ok", (after, result.stdout, result.stderr)
    assert after["next"] is None, after
    if scenario == "branch-past-the-pin":
        # A commit made on a branch stays on that branch.
        contains = git("branch", "--contains", made["commit"],
                       cwd=project / "spec").stdout
        assert made["branch"] in contains, contains


@WINDOWS_SKIP
def test_the_keep_line_in_the_explanation_keeps_a_detached_commit(
        standard, project, tmp_path):
    """The note's own advice is pasted too: run the `git -C <leg> branch
    NAME` it names BEFORE the line, and the commit is on that branch after
    the leg has moved. Without it the commit is reachable from no branch and
    is only in the reflog, which is what the note says."""
    made = make_detached_past_the_pin(project)
    row = row_of(standard, project, "legs")
    keep = re.search(r"git -C \S+ branch NAME", why_of(row))
    assert keep, why_of(row)
    kept = subprocess.run(["sh", "-c", keep.group(0).replace("NAME", "kept")],
                          capture_output=True, text=True, check=False,
                          env=PASTE_ENV)
    assert kept.returncode == 0, kept.stdout + kept.stderr
    result = paste(row, tmp_path / "elsewhere")
    assert result.returncode == 0, result.stdout + result.stderr
    assert row_of(standard, project, "legs")["status"] == "ok"
    assert "kept" in git("branch", "--contains", made["commit"],
                         cwd=project / "spec").stdout


@WINDOWS_SKIP
def test_without_the_keep_line_the_detached_commit_is_in_no_branch(
        standard, project, tmp_path):
    """The other half of the note, so it is true and not merely printed: the
    row is cured and the commit is reachable from no branch."""
    made = make_detached_past_the_pin(project)
    result = paste(row_of(standard, project, "legs"), tmp_path / "elsewhere")
    assert result.returncode == 0, result.stdout + result.stderr
    assert row_of(standard, project, "legs")["status"] == "ok"
    assert git("branch", "--contains", made["commit"],
               cwd=project / "spec").stdout.strip() == ""
    # Still in the object store and the reflog: nothing was destroyed.
    assert git("cat-file", "-t", made["commit"],
               cwd=project / "spec").stdout.strip() == "commit"
    assert made["commit"] in git("reflog", cwd=project / "spec").stdout


# --- the legs row: what no checkout cures, and the lockstep gate -----------

@pytest.mark.parametrize("scenario", sorted(LOCKSTEP_SCENARIOS))
def test_a_leg_no_checkout_cures_is_handed_the_lockstep_gate(
        standard, project, scenario):
    """A checkout lands on the gitlink and never on the pin, so a gitlink
    that is not the pin, a pin that is not a commit, or a mount git cannot
    read a HEAD in is not cured by `submodule update` -- and the line that
    claims to is a NEXT that does not cure. They get `validate-pins.py`,
    through `validator_command`, which is what the `pins` row hands over for
    the same gate."""
    LOCKSTEP_SCENARIOS[scenario](project)
    module = doctor_module(standard)
    legs = row_of(standard, project, "legs")
    assert legs["status"] == "FINDING", legs
    assert command_of(legs) == pins_gate(module, standard, project, True), \
        legs["next"]
    assert " submodule update " not in command_of(legs), legs["next"]
    assert "scripts/bootstrap.py" not in command_of(legs), legs["next"]
    assert why_of(legs), "the line must say why it is not a checkout"


def test_the_lockstep_line_is_the_one_the_pins_row_hands_over(standard,
                                                              project):
    """One gate, built in two places from the same two functions: the
    `legs` row's command and the `pins` row's are the same string, so a
    reader told two things about one gate is told one."""
    make_gitlink_moved(project)
    rows = rows_of(doctor(standard, project, "--json"))
    assert rows["pins"]["status"] == "FINDING", rows["pins"]
    assert command_of(rows["legs"]) == command_of(rows["pins"]), (
        rows["legs"]["next"], rows["pins"]["next"])


def test_the_lockstep_line_names_the_template_copy_with_its_environment(
        standard, project):
    """A root without its own `scripts/validate-pins.py` falls back to the
    standard's template copy, which imports `repo_shape` from the standard
    and so needs the `PYTHONPATH` that `validator_command` prints (#238).
    The line is built by that function, not retyped."""
    git("rm", "-q", "scripts/validate-pins.py", cwd=project)
    make_gitlink_moved(project)
    module = doctor_module(standard)
    legs = row_of(standard, project, "legs")
    assert command_of(legs) == pins_gate(module, standard, project, False), \
        legs["next"]
    assert "PYTHONPATH" in command_of(legs), legs["next"]
    assert "templates" in command_of(legs), legs["next"]


@WINDOWS_SKIP
@pytest.mark.parametrize("own_copy", [True, False])
def test_a_pasted_lockstep_line_runs_and_prints_the_gate_finding(
        standard, project, tmp_path, own_copy):
    """Pasted from elsewhere, with no `PYTHONPATH` in the environment: the
    gate runs (the template's line carries what it needs), exits 1, and says
    which fact is wrong. It is a finding, as it was before the paste -- no
    command cures a lockstep fact, which is the reason it is not a git
    line -- and neither a missing file nor a missing import."""
    if not own_copy:
        git("rm", "-q", "scripts/validate-pins.py", cwd=project)
    make_gitlink_moved(project)
    row = row_of(standard, project, "legs")
    result = paste(row, tmp_path / "elsewhere")
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "pin-gitlink-mismatch" in output, output
    assert "can't open file" not in output
    assert "ModuleNotFoundError" not in output


def test_the_git_line_does_not_cure_a_mount_git_cannot_read_a_head_in(
        standard, project):
    """WHY `head-unreadable` IS THE LOCKSTEP GATE'S AND NOT THE GIT LINE'S,
    pinned by what git does so that the day it changes this says so. With the
    gitdir gone `submodule update` cannot get a repository handle, and with
    an orphan branch it cannot find a current revision: it exits non-zero and
    leaves the row exactly as it was. (The case the plan left unprobed.)"""
    make_head_unreadable(project)
    before = row_of(standard, project, "legs")
    assert "cannot read a HEAD" in before["reason"], before
    result = subprocess.run(
        ["git", "-C", str(project), "submodule", "update", "--init",
         "--recursive", "--", "spec"], capture_output=True, text=True,
        check=False, env=PASTE_ENV)
    assert result.returncode != 0, result.stdout + result.stderr
    after = row_of(standard, project, "legs")
    assert after["status"] == "FINDING", after
    assert "cannot read a HEAD" in after["reason"], after


def test_a_checkout_wins_over_a_lockstep_fact_and_a_rerun_names_the_other(
        standard, project):
    """One leg a checkout cures (an empty mount) and one it does not (a
    gitlink that is not the pin): the line is the checkout, over the first
    leg only, and it says to run the doctor again. The re-run names the
    lockstep gate."""
    unbootstrap(project, "code")
    make_gitlink_moved(project)
    module = doctor_module(standard)
    first = row_of(standard, project, "legs")
    assert command_of(first) == (
        f"git -C {module.quote_arg(project.resolve())} submodule update "
        "--init --recursive -- code"), first["next"]
    assert "doctor again" in why_of(first), why_of(first)
    # The fix, applied by hand (no sh needed): the empty leg is now cured.
    git("-c", "protocol.file.allow=always", "submodule", "update", "--init",
        "--recursive", "--", "code", cwd=project)
    second = row_of(standard, project, "legs")
    assert second["status"] == "FINDING", second
    assert command_of(second) == pins_gate(module, standard, project, True), \
        second["next"]
    assert "doctor again" not in why_of(second), why_of(second)


def test_no_line_is_better_than_one_that_cannot_run(standard, tmp_path,
                                                    project):
    """If neither copy of the lockstep gate is readable the row prints no
    command: the `pins` row of the same report says so, and a NEXT that
    cannot run is the defect this row is being fixed for."""
    hollow = tmp_path / "hollow-standard"
    shutil.copytree(standard, hollow, symlinks=True)
    (hollow / "templates" / "assembly-root" / "scripts"
     / "validate-pins.py").unlink()
    git("rm", "-q", "scripts/validate-pins.py", cwd=project)
    make_gitlink_moved(project)
    rows = rows_of(doctor(hollow, project, "--json"))
    assert rows["legs"]["status"] == "FINDING", rows["legs"]
    assert rows["legs"]["next"] is None, rows["legs"]
    assert "neither" in rows["pins"]["reason"], rows["pins"]


# --- the members row -------------------------------------------------------

def holder_copy(holder, tmp_path) -> Path:
    root = tmp_path / FAMILY_NAME
    shutil.copytree(holder["root"], root, symlinks=True)
    return root


def member_unbootstrapped(root: Path) -> None:
    unbootstrap(root, f"members/{FAMILY_MEMBER}")


def holder_without(root: Path, *names: str) -> None:
    for name in names:
        git("rm", "-q", f"scripts/{name}", cwd=root)


def test_a_holder_that_can_run_its_own_bootstrap_keeps_it_as_the_next(
        standard, holder, tmp_path):
    """The holder's bootstrap does what the git line does AND carries the
    credential rewrite a PRIVATE member needs, so it stays the NEXT where it
    can run: `python3 <root>/scripts/bootstrap.py --root <root>`, with the
    explanation it always had."""
    root = holder_copy(holder, tmp_path)
    member_unbootstrapped(root)
    module = doctor_module(standard)
    row = row_of(standard, root, "members")
    assert row["status"] == "FINDING", row
    resolved = root.resolve()
    assert command_of(row) == (
        f"{module.PYTHON} "
        f"{module.quote_arg(resolved / 'scripts' / 'bootstrap.py')} "
        f"--root {module.quote_arg(resolved)}"), row["next"]
    assert " submodule update " not in command_of(row), row["next"]


@WINDOWS_SKIP
def test_a_pasted_members_next_with_the_holders_bootstrap_cures_the_row(
        standard, holder, tmp_path):
    root = holder_copy(holder, tmp_path)
    member_unbootstrapped(root)
    row = row_of(standard, root, "members")
    result = paste(row, tmp_path / "elsewhere")
    assert result.returncode == 0, result.stdout + result.stderr
    after = row_of(standard, root, "members")
    assert after["status"] == "ok", (after, result.stdout, result.stderr)


@pytest.mark.parametrize("lost", [("bootstrap.py",), ("repo_shape.py",),
                                  ("bootstrap.py", "repo_shape.py")])
def test_a_holder_that_cannot_run_its_bootstrap_is_handed_the_git_line(
        standard, holder, tmp_path, lost):
    """Without `scripts/bootstrap.py`, or without the `repo_shape.py` it
    imports from beside itself, the holder's NEXT used to be a command that
    died with `can't open file` or on its import. It is the plain git line
    over the member's path, and the explanation says it carries no credential
    rewrite."""
    root = holder_copy(holder, tmp_path)
    holder_without(root, *lost)
    member_unbootstrapped(root)
    module = doctor_module(standard)
    row = row_of(standard, root, "members")
    assert row["status"] == "FINDING", row
    assert command_of(row) == (
        f"git -C {module.quote_arg(root.resolve())} submodule update --init "
        f"--recursive -- members/{FAMILY_MEMBER}"), row["next"]
    assert "scripts/bootstrap.py" not in command_of(row), row["next"]
    assert "credential" in why_of(row), why_of(row)
    for character in (";", "'", "`", "(", ")"):
        assert character not in why_of(row), (character, why_of(row))
    assert "reflog" not in why_of(row), why_of(row)


@WINDOWS_SKIP
def test_a_pasted_members_git_line_cures_the_row(standard, holder, tmp_path):
    root = holder_copy(holder, tmp_path)
    holder_without(root, "bootstrap.py")
    member_unbootstrapped(root)
    row = row_of(standard, root, "members")
    result = paste(row, tmp_path / "elsewhere")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "can't open file" not in result.stdout + result.stderr
    after = row_of(standard, root, "members")
    assert after["status"] == "ok", (after, result.stdout, result.stderr)


def test_the_members_reflog_note_is_printed_for_a_detached_member_only(
        standard, holder, tmp_path):
    """The git line moves a member's HEAD too: a commit made on its detached
    HEAD is left only in the reflog, and a commit made on a branch is not."""
    detached = holder_copy(holder, tmp_path / "detached")
    holder_without(detached, "bootstrap.py")
    member = detached / "members" / FAMILY_MEMBER
    head = git("rev-parse", "HEAD", cwd=member).stdout.strip()
    git("checkout", "-q", "--detach", head, cwd=member)
    commit_in(member)
    module = doctor_module(standard)
    why = why_of(row_of(standard, detached, "members"))
    assert "reflog" in why, why
    assert f"git -C {module.quote_arg(member.resolve())} branch NAME" in why

    branched = holder_copy(holder, tmp_path / "branched")
    holder_without(branched, "bootstrap.py")
    member = branched / "members" / FAMILY_MEMBER
    git("checkout", "-q", "-B", "local-work", cwd=member)
    commit_in(member)
    why = why_of(row_of(standard, branched, "members"))
    assert why, "the line must say what it does"
    assert "reflog" not in why, why


@WINDOWS_SKIP
def test_a_pasted_members_git_line_keeps_a_detached_commit_on_the_kept_branch(
        standard, holder, tmp_path):
    root = holder_copy(holder, tmp_path)
    holder_without(root, "bootstrap.py")
    member = root / "members" / FAMILY_MEMBER
    git("checkout", "-q", "--detach", "HEAD", cwd=member)
    commit = commit_in(member)
    row = row_of(standard, root, "members")
    keep = re.search(r"git -C \S+ branch NAME", why_of(row))
    assert keep, why_of(row)
    subprocess.run(["sh", "-c", keep.group(0).replace("NAME", "kept")],
                   capture_output=True, check=True, env=PASTE_ENV)
    result = paste(row, tmp_path / "elsewhere")
    assert result.returncode == 0, result.stdout + result.stderr
    assert row_of(standard, root, "members")["status"] == "ok"
    assert "kept" in git("branch", "--contains", commit, cwd=member).stdout


def make_member_pin_not_a_commit(root: Path) -> None:
    """The MEMBER's `pin.commit` becomes a branch name. `family.yaml` carries
    a `shape:` block with a 40-hex `commit:` of its own, above `members:`, and
    that one is left alone."""
    manifest = root / "family.yaml"
    text = manifest.read_text(encoding="utf-8")
    head, marker, rows = text.partition("\nmembers:\n")
    assert marker, text
    edited, count = re.subn(r'(?m)^(\s+commit: )"[0-9a-f]{40}"$',
                            r'\1"main"', rows, count=1)
    assert count == 1, rows
    manifest.write_text(head + marker + edited, encoding="utf-8")


def test_a_member_row_with_no_40_hex_pin_is_handed_the_family_gate(
        standard, holder, tmp_path):
    """No checkout gives a row a `pin.commit`, so the line is the family
    gate -- through `validator_command`, the way the `family` row builds its
    own -- and not a bootstrap that would fetch and still leave the row red.
    The holder HAS its bootstrap here: it does not matter."""
    root = holder_copy(holder, tmp_path)
    make_member_pin_not_a_commit(root)
    module = doctor_module(standard)
    rows = rows_of(doctor(standard, root, "--json"))
    members = rows["members"]
    assert members["status"] == "FINDING", members
    assert "pin.commit" in members["reason"], members
    resolved = root.resolve()
    gate = module.validator_command(
        standard, resolved / "scripts" / "validate-family.py", True,
        ["--root", str(resolved)])
    assert command_of(members) == gate, members["next"]
    assert "validate-family.py" in command_of(members)
    assert "scripts/bootstrap.py" not in command_of(members), members["next"]
    assert " submodule update " not in command_of(members), members["next"]
    assert rows["family"]["status"] == "FINDING", rows["family"]
    assert command_of(rows["family"]) == command_of(members), (
        rows["family"]["next"], members["next"])


@pytest.mark.parametrize("breakage", ["head-unreadable",
                                      "no-git-of-its-own"])
def test_a_member_git_cannot_read_a_head_in_is_handed_the_family_gate(
        standard, holder, tmp_path, breakage):
    """The `legs` row's second kind, for a member: the gitdir is gone (the
    mount's `.git` file points at nothing), or the mount is a populated
    directory with no `.git` at all -- where git walks up and answers with
    the HOLDER's HEAD (`member_state`). `submodule update` and the holder's
    own bootstrap, which runs it, cure neither, and the holder HAS its
    bootstrap here: it does not matter."""
    root = holder_copy(holder, tmp_path)
    member = root / "members" / FAMILY_MEMBER
    rmtree(root / ".git" / "modules" / "members" / FAMILY_MEMBER)
    if breakage == "no-git-of-its-own":
        (member / ".git").unlink()
    module = doctor_module(standard)
    row = row_of(standard, root, "members")
    assert row["status"] == "FINDING", row
    resolved = root.resolve()
    assert command_of(row) == module.validator_command(
        standard, resolved / "scripts" / "validate-family.py", True,
        ["--root", str(resolved)]), row["next"]
    assert "scripts/bootstrap.py" not in command_of(row), row["next"]
    assert " submodule update " not in command_of(row), row["next"]


def test_a_holder_missing_its_own_family_gate_gets_the_templates(
        standard, holder, tmp_path):
    root = holder_copy(holder, tmp_path)
    make_member_pin_not_a_commit(root)
    git("rm", "-q", "scripts/validate-family.py", cwd=root)
    module = doctor_module(standard)
    members = row_of(standard, root, "members")
    gate = module.validator_command(
        standard, standard / "templates" / "family-root" / "scripts"
        / "validate-family.py", False, ["--root", str(root.resolve())])
    assert command_of(members) == gate, members["next"]
    assert "PYTHONPATH" in command_of(members), members["next"]


def test_a_holder_with_no_readable_family_gate_gets_no_line(
        standard, holder, tmp_path):
    """The `legs` row's rule, for the `members` row: no command is better
    than one that cannot run."""
    hollow = tmp_path / "hollow-standard"
    shutil.copytree(standard, hollow, symlinks=True)
    (hollow / "templates" / "family-root" / "scripts"
     / "validate-family.py").unlink()
    root = holder_copy(holder, tmp_path / "holder")
    make_member_pin_not_a_commit(root)
    git("rm", "-q", "scripts/validate-family.py", cwd=root)
    rows = rows_of(doctor(hollow, root, "--json"))
    assert rows["members"]["status"] == "FINDING", rows["members"]
    assert rows["members"]["next"] is None, rows["members"]


@WINDOWS_SKIP
def test_a_pasted_family_gate_line_runs_and_prints_its_finding(
        standard, holder, tmp_path):
    root = holder_copy(holder, tmp_path)
    make_member_pin_not_a_commit(root)
    git("rm", "-q", "scripts/validate-family.py", cwd=root)
    row = row_of(standard, root, "members")
    result = paste(row, tmp_path / "elsewhere")
    output = result.stdout + result.stderr
    assert result.returncode in (1, 2), output
    assert "can't open file" not in output
    assert "ModuleNotFoundError" not in output


def test_an_empty_member_with_no_pin_is_still_a_checkout_first(
        standard, holder, tmp_path):
    """The members row keeps the legs row's precedence: what a checkout cures
    comes first. The fixture's holder has ONE member, so the two kinds are
    asserted on that one row, where `member_problem` reports the empty mount
    before the missing pin; the line is the checkout, and a re-run names the
    gate once the mount is there."""
    root = holder_copy(holder, tmp_path)
    make_member_pin_not_a_commit(root)
    holder_without(root, "bootstrap.py")
    member_unbootstrapped(root)
    module = doctor_module(standard)
    row = row_of(standard, root, "members")
    assert command_of(row) == (
        f"git -C {module.quote_arg(root.resolve())} submodule update --init "
        f"--recursive -- members/{FAMILY_MEMBER}"), row["next"]
    git("-c", "protocol.file.allow=always", "submodule", "update", "--init",
        "--recursive", "--", f"members/{FAMILY_MEMBER}", cwd=root)
    again = row_of(standard, root, "members")
    assert again["status"] == "FINDING", again
    assert "validate-family.py" in command_of(again), again["next"]
