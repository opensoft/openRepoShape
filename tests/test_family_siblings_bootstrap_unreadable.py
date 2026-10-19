# SPDX-License-Identifier: Apache-2.0
"""The family root's `scripts/siblings.py` and `scripts/bootstrap.py`: a
member's path this user cannot read is refused by name, never read as
absent (#430, slice F of lane 1's plan).

THE DEFECT. Each tool asked `Path.is_file()` or `Path.exists()` of a
member's path. Up to Python 3.13 those raise a refused `stat`
(`PermissionError`), so a `members/<Project>` this user cannot search ended
`make siblings` and `make bootstrap` in that traceback; from 3.14 they
answer False to ANY `OSError`, and the path read as not there:

- `siblings.py` `tracking_branch`: the pinned copy's `project.yaml` was "not
  checked out", and the working clone was made on the remote's DEFAULT
  branch, not the member's tracking branch, `siblings ok`;
- `project_id`: a clone's `project.yaml` was no id, so the clone was
  fetched into, or `make park` run in it, with its id never read;
- `run_member_bootstrap`: the member's `scripts/bootstrap.py` was "none", so
  its legs were never placed, `siblings ok`;
- `dispatch`: the clone's `Makefile` was "no Makefile";
- `_print_pinned_row`: a checked-out pinned copy was `not checked out`,
  `make bootstrap`;
- `bootstrap.py` `unfetchable` and `run_member_target`: the member was NOT
  CHECKED OUT, beside the advice to set a credential, or had no Makefile,
  skipped, and the run said `family bootstrap ok`;
- `members_of`: `family.yaml` "does not exist" (`family-manifest-missing`).

Each is now asked by `stat`ing the path (each file's own `_is_a`, as
`bump-leg.py`'s): nothing at the name (`ENOENT`, `ENOTDIR`, ...) is the
absent case it always was, and any other `OSError` is refused,
`member-unreadable` (`family-manifest-unreadable` for `family.yaml`),
`<path>: cannot be read (<reason>)`, exit 2, with `chmod` for a permission
and `validate-pins.py`'s `OTHER_REASON` for any other cause.

EACH SITE HAS THREE ROWS: nothing there (the control, unchanged); a refused
`stat` as Python 3.14 answers it, in process, on every platform and as root
(`refused_stat`); and a real mode, where one can be made (`needs_a_mode`:
not on Windows, not as root). A mode on `members/<Project>` reaches the
pinned copy, its `.git` and its `project.yaml` through the command itself;
a working clone's `Makefile`, a member's `Makefile` and `family.yaml` are
reached by a link into a folder at mode 000, the only way to refuse their
`stat` while the folder they are in, and its `.git`, can still be read.
"""

from __future__ import annotations

import errno
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from test_bump_leg_unopenable import (
    made_unopenable, needs_a_mode, refusal_of, refused_stat,
)
from test_doctor_unreadable_pin import IO_ERROR, refusing
from test_family import (  # noqa: F401
    NAME, allow_file_protocol, estate, family, holder, siblings,
)
from test_family_bootstrap_gate_order import bootstrap
from test_family_gitmodules_values import by_path
from test_family_siblings_placement import placement  # noqa: F401

DENIED = "Permission denied"
#: The two codes this slice refuses with.
MEMBER_UNREADABLE = "member-unreadable"
MANIFEST_UNREADABLE = "family-manifest-unreadable"
#: A row whose member is nowhere: the control's absent case.
NOBODY = {"project": "Nobody", "id": "nobody", "path": "members/Nobody"}
#: A row whose path runs through a file (`ENOTDIR`): absent too.
THROUGH_A_FILE = {"project": "Nobody", "id": "nobody",
                  "path": "family.yaml/Nobody"}
ABSENT_ROWS = pytest.mark.parametrize(
    "row", [NOBODY, THROUGH_A_FILE],
    ids=["no-such-path", "a-file-on-the-path"])
#: The words a permission's remedy and any other cause's begin with:
#: siblings.py's, whose clones sit outside the holder, and bootstrap.py's,
#: `validate-pins.py`'s `_unreadable_file` word for word.
CHMOD = "`chmod u+rx` on a directory (and on every directory above it)"
CHMOD_IN_ROOT = ("`chmod u+rx` on a directory (and on every directory above "
                 "it inside the root)")
OTHER_CAUSE = "Where the operating system gave another reason"
#: The summary `make siblings` ends on where it refused a path (#430).
SUMMARY_TAIL = "; nothing was moved and no existing clone was touched"
#: The `stat` errnos that mean nothing is there, Windows' errors that mean
#: the same ("not ready", "invalid name", "cannot resolve"), and every
#: other errno this platform names.
ABSENT_ERRNOS = [errno.ENOENT, errno.ENOTDIR, errno.EBADF, errno.ELOOP]
ABSENT_WINERRORS = [21, 123, 1921]
OTHER_ERRNOS = sorted(set(errno.errorcode) - set(ABSENT_ERRNOS))
BOTH_FILES = pytest.mark.parametrize("which", ["siblings", "bootstrap"])


@pytest.fixture(scope="module")
def boot():
    """The template's `bootstrap.py`, loaded by path, no bytecode."""
    return by_path("bootstrap.py", "unreadable_family_bootstrap")


def row_of(boot, root: Path, project: str) -> dict:
    """`project`'s row of the holder's `family.yaml`, as bootstrap reads it."""
    _, rows = boot.members_of(root)
    return next(row for row in rows if row.get("project") == project)


def refusal_line(code: str, named: str, reason: str = DENIED) -> str:
    return f"REFUSED {code}: {named}: cannot be read ({reason})"


def no_traceback(result) -> None:
    assert "Traceback" not in result.stderr, result.stderr


def flat_rows(stdout: str) -> list[str]:
    """Each line of a table, its runs of blanks made one."""
    return [" ".join(line.split()) for line in stdout.splitlines()]


def linked_into_locked(directory: Path, name: str) -> str:
    """`directory/name` made a link to `directory/locked/name`, its bytes
    moved there: once `locked` is at mode 000 the `stat` of `name` is
    refused while `directory` and its `.git` can still be read. Returns
    `locked`, relative to `directory`, for `made_unopenable`."""
    locked = directory / "locked"
    locked.mkdir()
    (directory / name).rename(locked / name)
    (directory / name).symlink_to(Path("locked") / name)
    return "locked"


@pytest.fixture(scope="module")
def placed_folder(family, tmp_path_factory) -> Path:
    """`<tmp>/InkRouter/` with the holder and both members placed beside it
    by the holder's own `make siblings`, once for the module."""
    folder = tmp_path_factory.mktemp("placed") / NAME
    folder.mkdir()
    shutil.copytree(family["root"], folder / NAME, symlinks=True)
    result = siblings(folder / NAME)
    assert result.returncode == 0, result.stdout + result.stderr
    return folder


@pytest.fixture
def placed(placed_folder, tmp_path) -> Path:
    """A private copy of `placed_folder`; returns its holder."""
    folder = tmp_path / NAME
    shutil.copytree(placed_folder, folder, symlinks=True)
    return folder / NAME


# --- siblings.py: `tracking_branch`, the pinned copy's project.yaml ----------

@ABSENT_ROWS
def test_a_pinned_copy_not_there_keeps_the_default_branch(placement, family,
                                                          row):
    """The control: no pinned copy is the default branch it always was."""
    assert placement.tracking_branch(family["root"], row) == (
        None, f"{row['path']}/project.yaml is not checked out, so its "
              "tracking branch is not known here (`make bootstrap` checks "
              "it out)")


def test_a_pinned_copy_whose_stat_is_refused_is_refused(placement, family,
                                                        monkeypatch):
    """On every Python: not the default branch, but `member-unreadable`,
    naming the copy's `project.yaml` relative to the holder."""
    row = row_of(placement, family["root"], "IRSS")
    refused_stat(monkeypatch, "project.yaml")
    refusal = refusal_of(placement, placement.tracking_branch,
                         family["root"], row)
    assert refusal.code == MEMBER_UNREADABLE
    assert refusal.detail == (f"members/IRSS/project.yaml: cannot be read "
                              f"({DENIED})")
    assert "nothing was cloned for it" in refusal.remediation
    assert CHMOD in refusal.remediation


@needs_a_mode
@pytest.mark.parametrize("mode", [0o000, 0o444], ids=["000", "444"])
def test_make_siblings_clones_no_member_whose_pinned_copy_it_cannot_search(
        estate, mode):
    """`members/IRSS` at 000 or 444, nothing beside the holder yet: 3.12
    ended in a traceback after IRRS was cloned, and 3.14 cloned IRSS on
    its remote's default branch with `siblings ok`. Now IRSS is refused by
    name, nothing is cloned for it, IRRS is still placed, exit 2."""
    holder = estate["holder"]
    with made_unopenable(holder, "members/IRSS", mode=mode):
        result = siblings(holder)
    no_traceback(result)
    assert result.returncode == 2, result.stdout + result.stderr
    assert refusal_line(MEMBER_UNREADABLE, "members/IRSS/project.yaml") \
        in result.stderr
    assert "sibling IRSS CANNOT BE READ -" in flat_rows(result.stdout)
    assert not (estate["folder"] / "IRSS").exists()
    assert (estate["folder"] / "IRRS" / ".git").is_dir()
    assert "default branch" not in result.stdout


# --- siblings.py: `project_id`, a clone's own project.yaml -------------------

def test_a_clone_with_no_project_yaml_has_no_id(placement, tmp_path):
    """The control: no `project.yaml` is no id, as it always was."""
    assert placement.project_id(tmp_path) is None


def test_a_clone_whose_project_yaml_stat_is_refused_is_refused(
        placement, family, monkeypatch):
    """On every Python: no "no id", which let the clone be fetched into, or
    a verb run in it, with its id never read."""
    clone = family["root"] / "members" / "IRSS"
    refused_stat(monkeypatch, "project.yaml")
    refusal = refusal_of(placement, placement.project_id, clone)
    assert refusal.code == MEMBER_UNREADABLE
    assert refusal.detail == (f"{clone / 'project.yaml'}: cannot be read "
                              f"({DENIED})")
    assert "nothing was fetched or run there" in refusal.remediation


@needs_a_mode
def test_a_clone_it_cannot_search_is_refused_not_unidentified(placement,
                                                              holder):
    """A real mode, in process: the clone's folder at 000."""
    clone = holder / "members" / "IRSS"
    with made_unopenable(holder, "members/IRSS"):
        refusal = refusal_of(placement, placement.project_id, clone)
    assert refusal.detail == (f"{clone / 'project.yaml'}: cannot be read "
                              f"({DENIED})")


@pytest.mark.skipif(shutil.which("make") is None,
                    reason="needs `make` on PATH")
def test_make_park_refuses_every_clone_it_cannot_identify_and_goes_on(
        placement, placed_folder, monkeypatch, capsys):
    """Through `dispatch_all`, on every Python: each member is refused on
    its own row, the one after it is still tried, and the run exits 2."""
    holder = placed_folder / NAME
    _, rows = placement.members_of(holder)
    refused_stat(monkeypatch, "project.yaml")
    code = placement.dispatch_all(holder, NAME, rows, "park", [], True)
    said = capsys.readouterr()
    assert code == 2, said.out + said.err
    table = flat_rows(said.out)
    for project in ("IRRS", "IRSS"):
        assert f"sibling {project} CANNOT BE READ -" in table, said.out
    assert said.err.count(f"REFUSED {MEMBER_UNREADABLE}: ") == 2, said.err
    assert "0 of 2 member(s) ran" in said.err


# --- siblings.py: `run_member_bootstrap`, the clone's scripts/bootstrap.py ---

def test_a_clone_with_no_bootstrap_is_left_as_it_is(placement, tmp_path,
                                                    capsys):
    """The control: a member with no `scripts/bootstrap.py` is cloned and
    left as it is, no finding."""
    sibling = placement.Sibling("Nobody", tmp_path)
    placement.run_member_bootstrap(tmp_path, sibling)
    assert "[Nobody] no scripts/bootstrap.py; cloned and left as it is." \
        in capsys.readouterr().out
    assert sibling.finding is None


def test_a_bootstrap_whose_stat_is_refused_is_refused_not_skipped(
        placement, family, monkeypatch):
    """On every Python: no "no scripts/bootstrap.py" and `siblings ok`. The
    remedy says the clone is there and how to run its bootstrap, since a
    second `make siblings` only fetches it."""
    clone = family["root"] / "members" / "IRSS"
    refused_stat(monkeypatch, "bootstrap.py")
    refusal = refusal_of(placement, placement.run_member_bootstrap, clone,
                         placement.Sibling("IRSS", clone))
    assert refusal.code == MEMBER_UNREADABLE
    assert refusal.detail == (f"{clone / 'scripts' / 'bootstrap.py'}: cannot "
                              f"be read ({DENIED})")
    assert (f"Then run `{placement.PYTHON} scripts/bootstrap.py` in that "
            "clone") in refusal.remediation
    assert "Then run the same command again" not in refusal.remediation


@needs_a_mode
def test_a_bootstrap_it_cannot_search_for_is_refused(placement, holder):
    """A real mode, in process: the clone's `scripts/` at 000."""
    clone = holder / "members" / "IRSS"
    with made_unopenable(clone, "scripts"):
        refusal = refusal_of(placement, placement.run_member_bootstrap,
                             clone, placement.Sibling("IRSS", clone))
    assert refusal.detail == (f"{clone / 'scripts' / 'bootstrap.py'}: cannot "
                              f"be read ({DENIED})")


# --- siblings.py: `dispatch`, the clone's Makefile ---------------------------

def dispatched(placement, holder: Path, project: str):
    """`dispatch` of `make park --dry-run` for `project`, in process."""
    row = row_of(placement, holder, project)
    return placement.dispatch(holder, row, placement.submodule_urls(holder),
                              "park", [], "make", True)


def test_a_clone_with_no_makefile_is_still_skipped_by_name(placement, placed):
    """The control: a clone with no `Makefile` is `SKIPPED no Makefile`."""
    sibling_dir = placed.parent / "IRSS"
    (sibling_dir / "Makefile").rename(sibling_dir / "Makefile.aside")
    sibling = dispatched(placement, placed, "IRSS")
    assert sibling.state == "SKIPPED no Makefile"
    assert "has no Makefile" in sibling.finding


def test_a_makefile_whose_stat_is_refused_is_refused_not_absent(
        placement, placed_folder, monkeypatch):
    """On every Python: no "has no Makefile"."""
    holder = placed_folder / NAME
    refused_stat(monkeypatch, "Makefile")
    refusal = refusal_of(placement, dispatched, placement, holder, "IRSS")
    assert refusal.code == MEMBER_UNREADABLE
    assert refusal.detail == (f"{placed_folder / 'IRSS' / 'Makefile'}: cannot "
                              f"be read ({DENIED})")
    assert "`make park` was not run in" in refusal.remediation


@needs_a_mode
def test_make_park_refuses_a_makefile_it_cannot_reach_and_runs_the_rest(
        placed):
    """A real mode: IRSS's `Makefile` a link into a folder at 000. 3.12
    ended `make park` in a traceback after IRRS, and 3.14 said IRSS `has no
    Makefile`. Now IRSS is refused by name, IRRS still runs, exit 2."""
    clone = placed.parent / "IRSS"
    with made_unopenable(clone, linked_into_locked(clone, "Makefile")):
        result = siblings(placed, "--make", "park", "--dry-run")
    no_traceback(result)
    assert result.returncode == 2, result.stdout + result.stderr
    named = placed.resolve().parent / "IRSS" / "Makefile"
    assert refusal_line(MEMBER_UNREADABLE, str(named)) in result.stderr
    assert "sibling IRRS would make park main" in flat_rows(result.stdout)
    assert "has no Makefile" not in result.stderr


# --- siblings.py: `_print_pinned_row`, the pinned copy's .git --------------

def test_a_pinned_copy_not_there_is_still_not_checked_out(placement,
                                                          family, capsys):
    """The control: no mount is `not checked out`, `make bootstrap`."""
    placement._print_pinned_row(family["root"], NOBODY)
    assert "pinned members/Nobody not checked out make bootstrap" in \
        flat_rows(capsys.readouterr().out)


def test_a_pinned_mount_whose_stat_is_refused_is_refused(placement, family,
                                                         monkeypatch, capsys):
    """On every Python: no `not checked out` of a checked-out copy."""
    row = row_of(placement, family["root"], "IRSS")
    refused_stat(monkeypatch, ".git")
    pinned = placement._print_pinned_row(family["root"], row)
    assert pinned.state == "CANNOT BE READ"
    assert pinned.refusal.detail == (f"members/IRSS/.git: cannot be read "
                                     f"({DENIED})")
    assert "pinned members/IRSS CANNOT BE READ -" in flat_rows(
        capsys.readouterr().out)


@needs_a_mode
def test_make_siblings_refuses_a_pinned_copy_beside_a_placed_clone(placed):
    """A real mode, the members placed already: `members/IRSS` at 000. 3.12
    ended in a traceback at the layout table, and 3.14 said `not checked
    out`, `make bootstrap` and `siblings ok`. Now the pinned row is
    refused, the clones are still fetched, exit 2."""
    with made_unopenable(placed, "members/IRSS"):
        result = siblings(placed)
    no_traceback(result)
    assert result.returncode == 2, result.stdout + result.stderr
    assert refusal_line(MEMBER_UNREADABLE, "members/IRSS/.git") \
        in result.stderr
    assert "pinned members/IRSS CANNOT BE READ -" in flat_rows(result.stdout)
    assert "sibling IRSS present, fetched main" in flat_rows(result.stdout)
    assert "siblings ok" not in result.stdout
    assert result.stderr.splitlines()[-1] == (
        f"siblings: 1 path(s) this user cannot read{SUMMARY_TAIL}")


@pytest.mark.parametrize("findings, refusals, code, counted", [
    (1, 0, 1, "1 finding(s)"),
    (0, 2, 2, "2 path(s) this user cannot read"),
    (1, 2, 2, "1 finding(s) and 2 path(s) this user cannot read"),
], ids=["a-finding", "two-refusals", "both"])
def test_the_placement_summary_counts_what_it_could_not_read(
        placement, tmp_path, capsys, findings, refusals, code, counted):
    """`_report_placement`'s last line counts the findings, as it did, and
    the paths it could not read, a sibling's or a pinned copy's, and the
    run exits 2 where there is any."""
    rows = []
    for number in range(findings):
        row = placement.Sibling(f"F{number}", tmp_path)
        row.finding = f"F{number}: a finding"
        rows.append(row)
    pinned = []
    for number in range(refusals):
        row = placement.Sibling(f"members/R{number}", tmp_path)
        row.refusal = placement.member_unreadable(
            f"members/R{number}/.git",
            PermissionError(errno.EACCES, DENIED), "What was not done.")
        pinned.append(row)
    assert placement._report_placement(tmp_path, rows, False, pinned) == code
    assert capsys.readouterr().err.splitlines()[-1] == (
        f"siblings: {counted}{SUMMARY_TAIL}")


# --- bootstrap.py: `checked_out`, in `unfetchable` and `run_member_target` -

@ABSENT_ROWS
def test_a_member_not_there_is_still_not_checked_out(boot, family, row,
                                                     capsys):
    """The control: no mount, or a path through a file, is the member NOT
    CHECKED OUT it always was, in (a) and in (b)."""
    left, _, _ = boot.unfetchable(family["root"], [row], True)
    assert left == [(row, row["path"], boot.NO_GITLINK)]
    assert boot.run_member_target(family["root"], row, "help") is None
    assert "[Nobody] Nobody: NOT CHECKED OUT; skipped." in \
        capsys.readouterr().out


@pytest.mark.parametrize("ask", ["unfetchable", "run_member_target"])
def test_a_mount_whose_stat_is_refused_is_refused(boot, family, monkeypatch,
                                                  ask):
    """On every Python, in (a) and in (b): no NOT CHECKED OUT, skipped."""
    row = row_of(boot, family["root"], "IRRS")
    refused_stat(monkeypatch, ".git")
    args = ([row], True) if ask == "unfetchable" else (row, "help")
    refusal = refusal_of(boot, getattr(boot, ask), family["root"], *args)
    assert refusal.code == MEMBER_UNREADABLE
    assert refusal.detail == f"members/IRRS/.git: cannot be read ({DENIED})"
    assert "the run stopped there" in refusal.remediation
    assert CHMOD_IN_ROOT in refusal.remediation


@pytest.mark.parametrize("exit_code", [1, 0], ids=["git-failed", "git-ok"])
def test_gits_own_words_come_before_a_mount_it_refuses(
        boot, family, monkeypatch, capsys, exit_code):
    """Where (a) refuses a mount and git's update did not exit 0, git's own
    words are printed first, with no credential advice, then the refusal;
    they were lost. Where git exited 0 there is nothing of git's to say.
    In process, with git's update stood in for, on every platform."""
    _, rows = boot.members_of(family["root"])
    real = subprocess.run

    def git_update(args, *more, **kwargs):
        if "submodule" in args:
            return subprocess.CompletedProcess(
                args, exit_code, "", "fatal: the update stopped here\n")
        return real(args, *more, **kwargs)

    for name in boot.CREDENTIAL_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(boot.subprocess, "run", git_update)
    refused_stat(monkeypatch, ".git")
    refusal = refusal_of(boot, boot.fetch_members, family["root"], rows)
    said = capsys.readouterr().err
    assert refusal.detail == f"members/IRRS/.git: cannot be read ({DENIED})"
    assert said == ("  FETCH INCOMPLETE (git exit 1) using credential "
                    "source 'none':\nfatal: the update stopped here\n"
                    if exit_code else "")


@needs_a_mode
@pytest.mark.parametrize("relative, mode, named", [
    ("members/IRSS", 0o000, "members/IRSS/.git"),
    ("members", 0o444, "members/IRRS/.git"),
], ids=["a-mount-at-000", "members-at-444"])
def test_make_bootstrap_refuses_a_mount_it_cannot_search(holder, relative,
                                                         mode, named):
    """A real mode: 3.12 ended (a) in a traceback, and 3.14 said NOT
    CHECKED OUT, set SHAPE_LEGS_TOKEN, and `family bootstrap ok`. Now (a)
    refuses the mount by name, no member's `make` is run, exit 2."""
    with made_unopenable(holder, relative, mode=mode):
        result = bootstrap(holder, allow_file_protocol())
    no_traceback(result)
    assert result.returncode == 2, result.stdout + result.stderr
    refused = refusal_line(MEMBER_UNREADABLE, named)
    assert refused in result.stderr
    assert "family bootstrap ok" not in result.stdout
    assert ": make bootstrap ---" not in result.stdout
    assert CHMOD_IN_ROOT in result.stderr
    assert "SHAPE_LEGS_TOKEN" not in result.stderr
    fetch = result.stderr.find("  FETCH INCOMPLETE (git exit ")
    assert -1 < fetch < result.stderr.index(refused), result.stderr


@needs_a_mode
def test_make_validates_member_half_refuses_a_mount_it_cannot_search(holder):
    """`make validate`'s second step, `--no-fetch`: (b) runs IRRS's target,
    then refuses IRSS's mount by name, exit 2, where 3.14 skipped it and
    said `family bootstrap ok`."""
    with made_unopenable(holder, "members/IRSS"):
        result = bootstrap(holder, allow_file_protocol(), "--no-fetch",
                           "--members-make", "help")
    no_traceback(result)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "--- IRRS: make help ---" in result.stdout
    assert refusal_line(MEMBER_UNREADABLE, "members/IRSS/.git") \
        in result.stderr


# --- bootstrap.py: `run_member_target`, the member's Makefile ----------------

def test_a_member_with_no_makefile_is_still_skipped(boot, tmp_path, capsys):
    """The control: a mount with a `.git` and no `Makefile` is skipped."""
    (tmp_path / "members" / "Ghost").mkdir(parents=True)
    (tmp_path / "members" / "Ghost" / ".git").write_bytes(b"gitdir: x\n")
    row = {"project": "Ghost", "path": "members/Ghost"}
    assert boot.run_member_target(tmp_path, row, "help") is None
    assert "[Ghost] no Makefile; skipped." in capsys.readouterr().out


def test_a_member_makefile_whose_stat_is_refused_is_refused(boot, family,
                                                            monkeypatch):
    """On every Python: no "no Makefile; skipped"."""
    row = row_of(boot, family["root"], "IRSS")
    refused_stat(monkeypatch, "Makefile")
    refusal = refusal_of(boot, boot.run_member_target, family["root"], row,
                         "help")
    assert refusal.code == MEMBER_UNREADABLE
    assert refusal.detail == (f"members/IRSS/Makefile: cannot be read "
                              f"({DENIED})")
    assert "`make help` was not run in IRSS" in refusal.remediation


@needs_a_mode
def test_make_bootstrap_refuses_a_member_makefile_it_cannot_reach(holder):
    """A real mode: IRRS's `Makefile` a link into a folder at 000. 3.12
    ended in a traceback, and 3.14 said `no Makefile; skipped` and
    `family bootstrap ok`."""
    member = holder / "members" / "IRRS"
    with made_unopenable(member, linked_into_locked(member, "Makefile")):
        result = bootstrap(holder, allow_file_protocol(), "--no-fetch",
                           "--members-make", "help")
    no_traceback(result)
    assert result.returncode == 2, result.stdout + result.stderr
    assert refusal_line(MEMBER_UNREADABLE, "members/IRRS/Makefile") \
        in result.stderr
    assert "--- IRRS: make help ---" not in result.stdout


# --- bootstrap.py: `members_of`, family.yaml --------------------------------

def test_a_holder_with_no_family_yaml_is_still_missing(boot, tmp_path):
    """The control: no `family.yaml` is `family-manifest-missing`."""
    refusal = refusal_of(boot, boot.members_of, tmp_path)
    assert refusal.code == "family-manifest-missing"


def test_a_family_yaml_whose_stat_is_refused_is_not_called_missing(
        boot, family, monkeypatch):
    """On every Python: `family-manifest-unreadable`, never `does not
    exist` and its remedy for another kind of root."""
    refused_stat(monkeypatch, "family.yaml")
    refusal = refusal_of(boot, boot.members_of, family["root"])
    assert refusal.code == MANIFEST_UNREADABLE
    assert refusal.detail == f"family.yaml: cannot be read ({DENIED})"
    assert "`chmod u+r` on a file" in refusal.remediation


@needs_a_mode
@pytest.mark.parametrize("script", ["bootstrap.py", "siblings.py"])
def test_both_scripts_refuse_a_family_yaml_they_cannot_reach(holder, script):
    """A real mode: `family.yaml` a link into a folder at 000. Both scripts
    read it through `members_of`, and both refuse it by name, exit 2."""
    with made_unopenable(holder, linked_into_locked(holder, "family.yaml")):
        result = bootstrap(holder, allow_file_protocol()) \
            if script == "bootstrap.py" else siblings(holder)
    no_traceback(result)
    assert result.returncode == 2, result.stdout + result.stderr
    assert refusal_line(MANIFEST_UNREADABLE, "family.yaml") in result.stderr
    assert "family-manifest-missing" not in result.stderr


# --- the cause: a permission is told `chmod`, any other cause is not ---------

@pytest.mark.parametrize("which", ["siblings", "bootstrap"])
def test_a_stat_that_fails_for_another_reason_is_refused_sans_chmod(
        placement, boot, family, monkeypatch, which):
    """An I/O error is no permission: the same refusal, the system's own
    reason on the line, and `validate-pins.py`'s `OTHER_REASON`, with no
    `chmod`, in each file's own copy of the words."""
    module = placement if which == "siblings" else boot
    pinned = row_of(boot, family["root"], "IRSS")
    refusing(monkeypatch, "stat", ".git", OSError(errno.EIO, IO_ERROR))
    if which == "siblings":
        refusal = placement._print_pinned_row(family["root"], pinned).refusal
    else:
        refusal = refusal_of(boot, boot.checked_out, family["root"], pinned)
    assert refusal.detail == (f"members/IRSS/.git: cannot be read "
                              f"({IO_ERROR})")
    assert OTHER_CAUSE in refusal.remediation
    assert "chmod" not in refusal.remediation
    assert module.OTHER_REASON in refusal.remediation


@BOTH_FILES
@pytest.mark.parametrize("code", ABSENT_ERRNOS,
                         ids=[errno.errorcode[code] for code in ABSENT_ERRNOS])
def test_each_errno_of_nothing_there_is_absent(placement, boot, monkeypatch,
                                               which, code):
    """Each file's own `_is_a` answers as `bump-leg.py`'s does: a `stat`
    that says nothing is at the name is False, as `is_file()` said it."""
    module = placement if which == "siblings" else boot
    assert tuple(ABSENT_ERRNOS) == module._ABSENT_ERRNOS
    refusing(monkeypatch, "stat", "probe", OSError(code, os.strerror(code)))
    assert module._is_a(Path("probe"), stat.S_ISREG) is False


@BOTH_FILES
@pytest.mark.parametrize("winerror", ABSENT_WINERRORS)
def test_each_windows_error_of_nothing_there_is_absent(
        placement, boot, monkeypatch, which, winerror):
    """So is a `stat` whose Windows error says nothing is there, whatever
    its errno: here `EINVAL`, which is raised without one. In process, on
    every platform."""
    module = placement if which == "siblings" else boot
    assert tuple(ABSENT_WINERRORS) == module._ABSENT_WINERRORS
    real = Path.stat

    def refused(self, *args, **kwargs):
        if self.name != "probe":
            return real(self, *args, **kwargs)
        error = OSError(errno.EINVAL, os.strerror(errno.EINVAL), str(self))
        error.winerror = winerror
        raise error

    monkeypatch.setattr(Path, "stat", refused)
    assert module._is_a(Path("probe"), stat.S_ISREG) is False


@BOTH_FILES
def test_every_other_errno_is_raised(placement, boot, monkeypatch, which):
    """And a `stat` refused with any other errno this platform names
    (`EACCES`, `EPERM`, `EIO`, `ENAMETOOLONG` and `EINVAL` among them) is
    raised, for the caller to refuse by name."""
    module = placement if which == "siblings" else boot
    raised = []
    for code in OTHER_ERRNOS:
        refusing(monkeypatch, "stat", "probe",
                 OSError(code, os.strerror(code)))
        try:
            module._is_a(Path("probe"), stat.S_ISREG)
        except OSError as exc:
            raised.append(exc.errno)
    assert raised == OTHER_ERRNOS


@BOTH_FILES
def test_a_name_the_system_cannot_take_is_no_file(placement, boot, family,
                                                  which):
    """A NUL in a name is a `ValueError` the system raises before any
    `stat`, and `_is_a` answers False, as `exists()` did: a row whose
    `path:` holds one reads as no member there, never a traceback."""
    module = placement if which == "siblings" else boot
    nul = chr(0)
    assert module._is_a(Path(f"a{nul}b"), stat.S_ISREG) is False
    row = {"project": "IRSS", "path": f"members/IR{nul}SS"}
    if which == "siblings":
        assert placement.tracking_branch(family["root"], row)[0] is None
    else:
        assert boot.checked_out(family["root"], row) is False
