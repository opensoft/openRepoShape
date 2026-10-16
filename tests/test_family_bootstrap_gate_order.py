# SPDX-License-Identifier: Apache-2.0
"""A holder's own bootstrap and gate after a clone, in every order and mode
(#648).

THE ISSUE'S THREE LINES, each reproduced on #639's head before this change:

- (a) `scripts/bootstrap.py` ended `family bootstrap ok`, exit 0, having
  checked no member out. In a fresh recursive clone of a holder whose HEAD
  lost `.gitmodules`, `git submodule update` exits 0, and it said "every
  member and leg fetched", `NOT CHECKED OUT; skipped` for each member, then
  ok. In a plain clone of that holder, or of #363's state (a member's
  gitlink recorded only at `Members/<P>`), git dies `No url found for
  submodule path` (exit 128), and it still ended ok. It fails now, saying
  which members no credential would check out and why, and names
  `validate-family.py`. A missing credential is still the skip it was.
- (b) In a plain clone of #363's state followed by `git submodule update
  --init --recursive`, as CI and `make bootstrap` run it, the update dies at
  `Members/<P>` before it checks out any member, so where that row is not
  the first, the gate refused `member-uninitialized` for an earlier row,
  naming that same update, and never reached the variant's refusal. Every
  row's gitlink is asked before any row's checkout now.
- (c) Under `--no-members`, the mode CI falls back to there,
  `member-gitlink-unnamed` for that gitlink printed no command. It prints
  the index move members mode prints now.

THE SAME FAMILY, OFFLINE RULES AND STATES as
`test_family_head_lost_gitmodules.py` (#611), whose helpers are imported.
Every remedy is typed as printed. The case-variant states are index records
and commits, never two directories whose names differ only in case, and
the holder's own are asked again with `core.ignorecase=true`. A clone's
checkout is git's: on a disk that folds case, `Members/<P>` IS the row's
directory, so the `mv` the text gives for a case-sensitive disk is typed
only where the disk holds the two apart, as the text says.
"""

from __future__ import annotations

import itertools
import os
import re
import shlex
import subprocess
from pathlib import Path

import pytest

from conftest import clone_just_pushed, git, run_script
from repo_shape import PYTHON
from test_family import NAME, family, validate  # noqa: F401
from test_family_add_refusals import holder, offline  # noqa: F401
from test_family_dry_run import isolated
from test_family_head_lost_gitmodules import (
    DISKS, assert_passes_in_every_mode, commit_all, head_lost, on_disk,
    pinned, recorded_at, variant_refused,
)
from test_family_member_path import MEMBER, OTHER, raw
from test_validate_family_unnamed_mounts import (
    GITLINK_SAID, VARIANT, WRONG_CASE, commands, findings, stage_gitlink,
)

#: The line `(a)` prints for the members it left NOT CHECKED OUT where no
#: credential would check them out, and the one the run then ends on.
NOT_FETCHED = ("  NOT CHECKED OUT, and not for want of a credential: {left}. "
               f"`{PYTHON} scripts/validate-family.py` names the cause and "
               "the commit that cures it.")
NO_SECTION = "no section of .gitmodules gives that path"
NO_GITLINK = "no gitlink is recorded at that path"
EXITED_0 = "git exited 0 and checked nothing out there"

#: Each test pushes a branch of its own into the module's family remote. Not
#: `tmp_path.name`: a passed test's directory is removed under
#: `tmp_path_retention_policy=failed`, and the next test is given its number.
BRANCHES = itertools.count()

#: What members mode's variant refusal says before the move it prints.
WRONG_CASE_LEAD = "Remediation: the member is recorded in the wrong case. "

#: `bootstrap.py --skip-members`'s stdout after its first line, in a clone
#: where every member was checked out, and where not every one was: the
#: second says nothing of (a)'s fetch on stdout, and ends on stderr.
FETCHED = ["", "(a) members and their legs", "  credential source: none",
           "  every member and leg fetched", "",
           "(b) each member's own `make bootstrap`",
           "  skipped (--skip-members)", "", "family bootstrap ok", ""]
NOT_ALL_FETCHED = ["", "(a) members and their legs",
                   "  credential source: none", "",
                   "(b) each member's own `make bootstrap`",
                   "  skipped (--skip-members)", "", ""]


def with_config(env: dict, key: str, value: str) -> dict:
    """`env` with `key` set to `value`, one more `GIT_CONFIG_*` entry after
    the ones it already holds, for every git the run starts."""
    index = int(env.get("GIT_CONFIG_COUNT", "0"))
    return {**env, "GIT_CONFIG_COUNT": str(index + 1),
            f"GIT_CONFIG_KEY_{index}": key, f"GIT_CONFIG_VALUE_{index}": value}


def fetching(env: dict) -> dict:
    """`env` under which `git submodule update` may clone the fixture's
    local members: `protocol.file.allow`, as `test_family.py` gives the
    holder's own bootstrap."""
    return with_config(env, "protocol.file.allow", "always")


def variant(holder: Path, env: dict, project: str = OTHER) -> str:
    """#363's state: `project`'s gitlink recorded only at `Members/<P>`,
    committed, its row and section still `members/<P>`. OTHER is the
    second row, so a plain clone's update dies before the first row's
    checkout. Returns the commit."""
    return recorded_at(holder, env, project, f"Members/{project}")


def cloned(holder: Path, env: dict, family, tmp_path: Path,
           *, recurse: bool) -> Path:
    """HEAD pushed to a branch of the family's own remote that no other
    test pushes (`BRANCHES`), then a fresh clone of it, recursive or plain,
    which must exit 0."""
    remote = family["remotes"] / f"{NAME}.git"
    branch = f"w648/{next(BRANCHES)}"
    raw(holder, env, "push", "-q", str(remote), f"HEAD:refs/heads/{branch}")
    clone = tmp_path / "clone"
    made = clone_just_pushed(remote, clone, branch, recurse=recurse)
    assert made.returncode == 0, made.stdout + made.stderr
    return clone


def bootstrap(root: Path, env: dict, *extra: str):
    return run_script(root / "scripts" / "bootstrap.py", *extra, cwd=root,
                      env=env)


def not_fetched(*left: tuple[str, str]) -> str:
    """`NOT_FETCHED` naming each `(path, why)`."""
    return NOT_FETCHED.format(
        left=", ".join(f"{path} ({why})" for path, why in left))


def failed_on(*projects: str) -> str:
    return "family bootstrap FAILED: " + ", ".join(
        f"{project} (not checked out)" for project in projects)


def after_first_line(result) -> list[str]:
    """Bootstrap's stdout after its first line, which names the holder and
    its two members."""
    lines = result.stdout.split("\n")
    assert lines[0].startswith(f"bootstrap: {NAME} ("), result.stdout
    assert lines[0].endswith(" 2 member(s)"), result.stdout
    return lines[1:]


def other_older(family) -> str:
    """A commit of OTHER that is not the one the holder pins."""
    return git("rev-parse", "main~1",
               cwd=family["remotes"] / f"{OTHER}.git").stdout.strip()


def type_line(root: Path, env: dict, line: str) -> None:
    """One printed `git` line, typed as printed: split as a POSIX shell
    splits it, run with no shell."""
    argv = shlex.split(line)
    assert argv[0] == "git", line
    raw(root, env, *argv[1:])


def moved_out_where_apart(root: Path, remediation: str) -> None:
    """Each backticked `mv` the text gives for a case-sensitive disk, typed
    as printed where the disk holds its source apart from the row's own
    directory, as the text says; on a disk that folds case it is the row's
    directory, and the text says to leave it."""
    for move in re.findall(r"`(mv -- [^`]*)`", remediation):
        argv = shlex.split(move)
        source = root / argv[2]
        own = root / "members" / argv[2].split("/", 1)[1]
        if not source.exists() or (own.exists()
                                   and os.path.samefile(source, own)):
            continue
        subprocess.run(argv, cwd=str(root), check=True)
        assert not source.exists()


# --- (a) bootstrap -----------------------------------------------------------

#: `(set-up, flow, the members (a) names with why, the rows it fails on)`.
UNFETCHED = {
    "head-lost-recursive": (
        head_lost, True,
        ((f"members/{MEMBER}", NO_SECTION), (f"members/{OTHER}", NO_SECTION)),
        (MEMBER, OTHER)),
    "head-lost-plain": (
        head_lost, False,
        ((f"members/{MEMBER}", NO_SECTION), (f"members/{OTHER}", NO_SECTION)),
        (MEMBER, OTHER)),
    "variant-recursive": (
        variant, True, ((f"members/{OTHER}", NO_GITLINK),), (OTHER,)),
    "variant-plain": (
        variant, False, ((f"members/{OTHER}", NO_GITLINK),), (OTHER,)),
}


@pytest.mark.parametrize("set_up, recurse, left, projects",
                         UNFETCHED.values(), ids=UNFETCHED)
def test_bootstrap_fails_over_members_no_credential_would_check_out(
        family, holder, offline, tmp_path, set_up, recurse, left, projects):
    """THE ISSUE'S (a), both of rv611b's states, after a recursive clone and
    after a plain one. Git exits 0 over a holder whose HEAD lost
    `.gitmodules` where the clone was recursive, and 128 (`No url found for
    submodule path`) where it was plain, and 128 over #363's state in a
    plain clone: the run said ok each time. It names the members no
    credential would check out, says why, names `validate-family.py`, and
    fails; it never says every member was fetched."""
    env = isolated(offline, tmp_path)
    set_up(holder, env)
    clone = cloned(holder, env, family, tmp_path,
                   recurse=recurse)

    result = bootstrap(clone, fetching(env), "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert after_first_line(result) == NOT_ALL_FETCHED
    errors = result.stderr.splitlines()
    assert errors[-2:] == [not_fetched(*left), failed_on(*projects)], (
        result.stderr)
    if not recurse:
        assert errors[0].startswith("  FETCH INCOMPLETE (git exit 128) "), (
            result.stderr)
        assert "No url found for submodule path" in result.stderr


def test_a_good_holder_bootstraps_as_it_did(family, holder, offline,
                                            tmp_path):
    """A GOOD HOLDER'S RUN IS KEPT: a fresh recursive clone checks every
    member out, (a) says every member and leg was fetched, and the run ends
    ok with nothing on stderr."""
    env = isolated(offline, tmp_path)
    clone = cloned(holder, env, family, tmp_path, recurse=True)

    result = bootstrap(clone, fetching(env), "--skip-members")

    assert result.returncode == 0, result.stdout + result.stderr
    assert after_first_line(result) == FETCHED
    assert result.stderr == ""


def test_a_missing_credential_is_still_the_skip_it_was(family, holder,
                                                       offline, tmp_path):
    """No misfire: a plain clone whose update git refuses for want of a
    credential (no `protocol.file.allow` for the local members, as a
    private member with no token is refused) records every gitlink at its
    row's path, and `.gitmodules` gives each. A credential is the cure, so
    the members are skipped, the run ends ok, and no line says otherwise."""
    env = isolated(offline, tmp_path)
    clone = cloned(holder, env, family, tmp_path,
                   recurse=False)

    result = bootstrap(clone, env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "FETCH INCOMPLETE" in result.stderr
    assert "not for want of a credential" not in result.stderr
    for project in (MEMBER, OTHER):
        assert (f"  [{project}] {project}: NOT CHECKED OUT; skipped. See the "
                "fetch above.") in result.stdout.splitlines()
    assert result.stdout.endswith("\nfamily bootstrap ok\n"), result.stdout


def test_an_update_that_exits_0_and_skips_a_member_fails(family, holder,
                                                          offline, tmp_path):
    """Git exited 0, so it lacked nothing a credential gives, though the
    holder's records give OTHER: here `submodule.<name>.update=none` set
    for the run skips it. (a) does not say every member was fetched, and
    the run fails on OTHER alone."""
    env = isolated(offline, tmp_path)
    clone = cloned(holder, env, family, tmp_path,
                   recurse=False)
    skip = with_config(fetching(env), f"submodule.members/{OTHER}.update",
                       "none")

    result = bootstrap(clone, skip, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert (clone / "members" / MEMBER / "project.yaml").is_file()
    assert "every member and leg fetched" not in result.stdout
    assert result.stderr.splitlines() == [
        not_fetched((f"members/{OTHER}", EXITED_0)), failed_on(OTHER)]


def test_a_row_written_twice_is_named_once(family, holder, offline,
                                           tmp_path):
    """OTHER's row written twice in a holder whose HEAD lost `.gitmodules`:
    one path, so one name in (a) and one failure."""
    env = isolated(offline, tmp_path)
    head_lost(holder, env)
    rows = (holder / "family.yaml").read_bytes()
    start = rows.index(f"  - project: {OTHER}\n".encode())
    (holder / "family.yaml").write_bytes(rows + rows[start:])
    raw(holder, env, "add", "--", "family.yaml")
    commit_all(holder, env, "OTHER's row written twice")
    clone = cloned(holder, env, family, tmp_path, recurse=True)

    result = bootstrap(clone, fetching(env), "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stderr.splitlines() == [
        not_fetched((f"members/{MEMBER}", NO_SECTION),
                    (f"members/{OTHER}", NO_SECTION)),
        failed_on(MEMBER, OTHER)]


# --- (a) and (b) together: the plain clone of #363's state, typed through ---

def test_a_plain_clone_of_a_case_variant_is_named_and_mended_as_printed(
        family, holder, offline, tmp_path):
    """The round trip a person makes. In a plain clone of #363's state, with
    the variant at the SECOND row, `make bootstrap`'s script fails naming
    OTHER and the validator; the validator, members checked, names the
    variant and the move, where it refused `member-uninitialized` for the
    first row before. Typed as printed in the clone, with the commit and
    the `mv` where the disk holds the two apart, the same script checks
    both members out and runs each one's own bootstrap, and the gate passes
    in every mode."""
    env = fetching(isolated(offline, tmp_path))
    commit = variant(holder, env)
    clone = cloned(holder, env, family, tmp_path, recurse=False)

    booted = bootstrap(clone, env)

    assert booted.returncode == 1, booted.stdout + booted.stderr
    assert booted.stderr.splitlines()[-2:] == [
        not_fetched((f"members/{OTHER}", NO_GITLINK)), failed_on(OTHER)]
    gate = validate(clone)
    assert gate.returncode == 2, gate.stdout + gate.stderr
    lines = gate.stderr.splitlines()
    assert lines == variant_refused(f"members/{OTHER}", commit,
                                    [f"Members/{OTHER}"],
                                    {f"Members/{OTHER}": commit})
    for line in lines[2:]:
        type_line(clone, env, line)
    commit_all(clone, env, "Move the gitlink as printed")
    moved_out_where_apart(clone, lines[1])

    again = bootstrap(clone, env)

    assert again.returncode == 0, again.stdout + again.stderr
    assert "  every member and leg fetched" in again.stdout.splitlines()
    for project in (MEMBER, OTHER):
        assert f"  --- {project}: make bootstrap ---" in again.stdout
    assert again.stdout.endswith("\nfamily bootstrap ok\n"), again.stdout
    assert_passes_in_every_mode(clone, 2)


# --- (b) the gate asks every row's gitlink before any row's checkout --------

@pytest.mark.parametrize("project", [MEMBER, OTHER], ids=["first", "second"])
def test_a_plain_clone_after_the_update_names_the_variant_in_any_row(
        family, holder, offline, tmp_path, project):
    """THE ISSUE'S (b), as CI and `make bootstrap` run it: a plain clone,
    then `git submodule update --init --recursive`, which dies at
    `Members/<P>` (exit 128) before it checks out either member. Members
    checked and `--pins` alike, the gate refuses the variant with the move,
    whichever row it is; for the second it refused `member-uninitialized`
    for the first row, naming that same update. Under `--no-members`, CI's
    fallback, the finding prints the same two lines (c); typed as printed in
    the clone and committed, the update checks both out and the gate
    passes."""
    env = fetching(isolated(offline, tmp_path))
    commit = variant(holder, env, project)
    clone = cloned(holder, env, family, tmp_path, recurse=False)
    update = raw(clone, env, "submodule", "update", "--init", "--recursive",
                 check=False)
    assert update.returncode == 128, update.stderr
    assert (f"No url found for submodule path 'Members/{project}'".encode()
            in update.stderr)
    expected = variant_refused(f"members/{project}", commit,
                               [f"Members/{project}"],
                               {f"Members/{project}": commit})

    for extra in ((), ("--pins",)):
        gate = validate(clone, *extra)
        assert gate.returncode == 2, (extra, gate.stdout + gate.stderr)
        assert gate.stderr.splitlines() == expected, extra
    fallback = validate(clone, "--no-members")
    assert fallback.returncode == 1, fallback.stdout + fallback.stderr
    (finding,) = findings(fallback)
    assert commands(finding) == [line.strip() for line in expected[2:]]

    for line in commands(finding):
        type_line(clone, env, line)
    commit_all(clone, env, "Move the gitlink as CI's gate printed")
    moved_out_where_apart(clone, finding)
    raw(clone, env, "submodule", "update", "--init", "--recursive")
    assert_passes_in_every_mode(clone, 2)


# --- (c) `--no-members` prints the move members mode prints -----------------

def unnamed_moved(variant_path: str, at: str, pin: str,
                  variants: list[str]) -> str:
    """`member-gitlink-unnamed` WHOLE for the gitlink at `variant_path` (at
    `at`), OTHER recorded only at `variants`: what every unnamed gitlink
    says, the row it is a variant of, and members mode's move to the pin,
    word for word."""
    path = f"members/{OTHER}"
    refused = variant_refused(path, pin, variants,
                              dict.fromkeys(variants, at))
    assert refused[1].startswith(WRONG_CASE_LEAD + "Move its gitlink "), (
        "premise: members mode's remedy text")
    return "\n".join([
        GITLINK_SAID.format(path=variant_path, commit=at)
        + VARIANT.format(row_path=path, project=OTHER)
        + " The member is recorded in the wrong case. "
        + refused[1][len(WRONG_CASE_LEAD):], *refused[2:]])


@DISKS
@pytest.mark.parametrize("spellings", [
    ("Members/{p}",), ("MEMBERS/{p}", "Members/{p}")], ids=["one", "two"])
def test_no_members_prints_the_move_members_mode_prints(
        family, holder, offline, tmp_path, ignorecase, spellings):
    """THE ISSUE'S (c). OTHER's only gitlink at a case variant (two, in the
    second case), at a commit that is not its pin. Under `--no-members` each
    variant's `member-gitlink-unnamed` printed no command; it prints the
    move members mode prints now, to the commit the row PINS, every variant
    taken out on one line. Typed as printed and committed, on either disk,
    the holder passes in every mode."""
    env = on_disk(isolated(offline, tmp_path), ignorecase)
    variants = sorted(spelling.format(p=OTHER) for spelling in spellings)
    at = other_older(family)
    pin = pinned(holder, OTHER)
    assert pin != at, "premise: the variant is not at the pin"
    raw(holder, env, "rm", "-q", "--cached", "--", f"members/{OTHER}")
    for spelling in variants:
        stage_gitlink(holder, spelling, at)
    commit_all(holder, env, f"{OTHER} recorded in another case")

    result = validate(holder, "--no-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert findings(result) == [unnamed_moved(path, at, pin, variants)
                                for path in variants]
    for line in commands(findings(result)[0]):
        type_line(holder, env, line)
    commit_all(holder, env, "Move the gitlink as printed")
    assert_passes_in_every_mode(holder, 2)


def test_a_row_whose_pin_is_no_commit_still_prints_no_command(
        holder, offline, tmp_path):
    """The move records the gitlink at the commit the row pins, so a row
    whose `pin.commit` is no 40-hex commit (members checked, the refusal
    `member-pin-commit`) gets the text it had, and no command."""
    env = isolated(offline, tmp_path)
    commit = variant(holder, env)
    rows = (holder / "family.yaml").read_bytes()
    line = f'      commit: "{commit}"\n'.encode()
    assert rows.count(line) == 1, "fixture drift: OTHER's pin line"
    (holder / "family.yaml").write_bytes(
        rows.replace(line, f'      commit: "{commit[:12]}"\n'.encode()))

    result = validate(holder, "--no-members")

    assert result.returncode == 1, result.stdout + result.stderr
    (finding,) = findings(result)
    assert finding == GITLINK_SAID.format(
        path=f"Members/{OTHER}", commit=commit) + WRONG_CASE.format(
            row_path=f"members/{OTHER}", project=OTHER, what="gitlink")
    assert "git rm" not in result.stderr, result.stderr
