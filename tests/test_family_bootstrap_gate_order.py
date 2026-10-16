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
  which members no credential would check out and why, and what cures
  them. So it does where git's init dies at a gitlink no section gives a
  url, a stray case variant, a member mounted by hand or a section that
  lost its url (rv648's S1, H1 and U1), and where git exits 0 over a member
  a subset clone or `update = none` leaves out, whose line prints the
  update that checks it out. A missing credential is still the skip it
  was, after a recursive clone too.
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
and commits, and no test makes two directories whose names differ only in
case; the holder's own are asked again with `core.ignorecase=true`. A
clone's checkout is git's: on a disk that folds case, `Members/<P>` IS the
row's directory, so the `mv` the text gives for a case-sensitive disk is
typed only where the disk holds the two apart, as the text says, and a
clone of a stray (`Members/<P>` beside `members/<P>`, rv648's S1) gets its
two empty mounts there as one directory, which no assertion reads.
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
from test_family import NAME, SPARE, family, validate  # noqa: F401
from test_family_add_refusals import holder, offline  # noqa: F401
from test_family_dry_run import isolated
from test_family_head_lost_gitmodules import (
    DISKS, GITMODULES, assert_passes_in_every_mode, commit_all,
    committed_gitmodules, head_lost, on_disk, pinned, recorded_at,
    variant_refused,
)
from test_family_member_path import MEMBER, OTHER, raw
from test_validate_family_unnamed_mounts import (
    GITLINK_SAID, VARIANT, WRONG_CASE, commands, findings, spare_commits,
    stage_gitlink,
)

#: The line `(a)` prints for the members it left NOT CHECKED OUT where no
#: credential would check them out, each with why, then what cures them;
#: the run then ends on `failed_on`.
NOT_FETCHED = ("  NOT CHECKED OUT, and not for want of a credential: {left}. "
               "{cure}")
NO_SECTION = "no section of .gitmodules gives that path"
NO_GITLINK = "no gitlink is recorded at that path"
EXITED_0 = "git exited 0 and checked nothing out there"
STOPPED = ("git stopped at {path}, a gitlink no section of .gitmodules "
           "gives a url")

#: What the line says cures each why: the validator for the first two; for
#: the gitlink git stopped at, the validator's `--no-members`, or, where a
#: row names that gitlink, its section written back; and for a member git
#: exited 0 over, the update that checks it out.
VALIDATOR_CURE = (f"`{PYTHON} scripts/validate-family.py` names the cause "
                  "and the commit that cures it.")
UNNAMED_CURE = (f"`{PYTHON} scripts/validate-family.py --no-members` names "
                "each gitlink in members/ that no row names, and the commit "
                "that cures it.")
SECTION_CURE = ("Write the section of .gitmodules for {path} back as "
                "`family.py add` writes one, with its path and url, and "
                "commit .gitmodules.")
CHECKOUT_CURE = ("`git submodule update --init --checkout --recursive -- "
                 "{path}` checks it out.")

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


def not_fetched(*left: tuple[str, str], cure: str = VALIDATOR_CURE) -> str:
    """`NOT_FETCHED` naming each `(path, why)`, then `cure`."""
    return NOT_FETCHED.format(
        left=", ".join(f"{path} ({why})" for path, why in left), cure=cure)


def stray(holder: Path, env: dict, family) -> str:
    """#361's STRAY: OTHER's gitlink recorded at `Members/<P>` too, at its
    pin, beside its own, and committed; no section gives the second. Index
    order puts it before every member's. Returns its path."""
    stage_gitlink(holder, f"Members/{OTHER}", pinned(holder, OTHER))
    commit_all(holder, env, "A stray case variant of OTHER's gitlink")
    return f"Members/{OTHER}"


def hand_mounted(holder: Path, env: dict, family) -> str:
    """SPARE's gitlink recorded at `members/<SPARE>` by hand, with no row
    and no section, and committed. Returns its path."""
    stage_gitlink(holder, f"members/{SPARE}", spare_commits(family)[1])
    commit_all(holder, env, "A member mounted by hand")
    return f"members/{SPARE}"


#: The two gitlinks no row names at which git's init dies in a plain clone
#: (rv648's S1 and H1).
UNNAMED_STOPS = {"stray": stray, "hand-mount": hand_mounted}


def without_url(data: bytes, project: str) -> bytes:
    """`.gitmodules` bytes with the `url` line of `project`'s section taken
    out, the rest as `family.py add` wrote it (rv648's U1). A checkout's
    copy may end its lines CRLF."""
    section = re.compile(rb'(\[submodule "members/' + project.encode()
                         + rb'"\]\r?\n(?:\t[^\n]*\n)*?)\turl = [^\n]*\n')
    edited, count = section.subn(rb"\1", data)
    assert count == 1, data
    return edited


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

#: `(set-up, flow, the members (a) names with why, the rows it fails on,
#: what it says cures them)`. In #363's plain clone git dies at the variant,
#: `Members/<P>`, before it checks out MEMBER, so MEMBER is named too, and
#: the variant is a gitlink no row names (rv648's M1).
UNFETCHED = {
    "head-lost-recursive": (
        head_lost, True,
        ((f"members/{MEMBER}", NO_SECTION), (f"members/{OTHER}", NO_SECTION)),
        (MEMBER, OTHER), VALIDATOR_CURE),
    "head-lost-plain": (
        head_lost, False,
        ((f"members/{MEMBER}", NO_SECTION), (f"members/{OTHER}", NO_SECTION)),
        (MEMBER, OTHER), VALIDATOR_CURE),
    "variant-recursive": (
        variant, True, ((f"members/{OTHER}", NO_GITLINK),), (OTHER,),
        VALIDATOR_CURE),
    "variant-plain": (
        variant, False,
        ((f"members/{MEMBER}", STOPPED.format(path=f"Members/{OTHER}")),
         (f"members/{OTHER}", NO_GITLINK)),
        (MEMBER, OTHER), f"{VALIDATOR_CURE} {UNNAMED_CURE}"),
}


@pytest.mark.parametrize("set_up, recurse, left, projects, cure",
                         UNFETCHED.values(), ids=UNFETCHED)
def test_bootstrap_fails_over_members_no_credential_would_check_out(
        family, holder, offline, tmp_path, set_up, recurse, left, projects,
        cure):
    """THE ISSUE'S (a), both of rv611b's states, after a recursive clone and
    after a plain one. Git exits 0 over a holder whose HEAD lost
    `.gitmodules` where the clone was recursive, and 128 (`No url found for
    submodule path`) where it was plain, and 128 over #363's state in a
    plain clone: the run said ok each time. It names the members no
    credential would check out, says why and what cures them, and fails;
    it never says every member was fetched."""
    env = isolated(offline, tmp_path)
    set_up(holder, env)
    clone = cloned(holder, env, family, tmp_path,
                   recurse=recurse)

    result = bootstrap(clone, fetching(env), "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert after_first_line(result) == NOT_ALL_FETCHED
    errors = result.stderr.splitlines()
    assert errors[-2:] == [not_fetched(*left, cure=cure),
                           failed_on(*projects)], result.stderr
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
    assert ("  every member and leg fetched"
            not in result.stdout.splitlines()), result.stdout
    for project in (MEMBER, OTHER):
        assert (f"  [{project}] {project}: NOT CHECKED OUT; skipped. See the "
                "fetch above.") in result.stdout.splitlines()
    assert result.stdout.endswith("\nfamily bootstrap ok\n"), result.stdout


def skip_by_update_none(clone: Path, env: dict) -> dict:
    """`submodule.<name>.update=none` for OTHER, set for every git the run
    starts, as a `.gitmodules` committed with `update = none` sets it."""
    return with_config(env, f"submodule.members/{OTHER}.update", "none")


def skip_by_subset(clone: Path, env: dict) -> dict:
    """`submodule.active` in the clone's own git config naming MEMBER alone,
    as `git clone --recurse-submodules=members/<P>` stores it."""
    raw(clone, env, "config", "submodule.active", f"members/{MEMBER}")
    return env


@pytest.mark.parametrize("skip", [skip_by_update_none, skip_by_subset],
                         ids=["update-none", "subset"])
def test_an_update_that_exits_0_and_skips_a_member_fails(family, holder,
                                                          offline, tmp_path,
                                                          skip):
    """Git exited 0, so it lacked nothing a credential gives, though the
    holder's records give OTHER: an `update = none`, or a clone that chose
    a subset of members, skips it (rv648's N1 and P1). (a) does not say
    every member was fetched, and the run fails on OTHER alone, printing
    the update that checks it out: `--init` with its path registers it, and
    `--checkout` overrides the `none`. `git submodule update --init
    --recursive`, `member-uninitialized`'s remedy, exits 0 there and checks
    nothing out. Typed as printed, the line lets the same run end ok."""
    env = fetching(isolated(offline, tmp_path))
    clone = cloned(holder, env, family, tmp_path,
                   recurse=False)
    env = skip(clone, env)

    result = bootstrap(clone, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert (clone / "members" / MEMBER / "project.yaml").is_file()
    assert "every member and leg fetched" not in result.stdout
    assert result.stderr.splitlines() == [
        not_fetched((f"members/{OTHER}", EXITED_0),
                    cure=CHECKOUT_CURE.format(path=f"members/{OTHER}")),
        failed_on(OTHER)]
    raw(clone, env, "submodule", "update", "--init", "--recursive")
    assert not (clone / "members" / OTHER / ".git").exists(), (
        "premise: the validator's remedy checks nothing out here")
    (line,) = re.findall(r"`(git submodule update [^`]*)`", result.stderr)
    type_line(clone, env, line)

    again = bootstrap(clone, env, "--skip-members")

    assert again.returncode == 0, again.stdout + again.stderr
    assert after_first_line(again) == FETCHED
    assert again.stderr == ""


@pytest.mark.parametrize("set_up", UNNAMED_STOPS.values(), ids=UNNAMED_STOPS)
def test_a_gitlink_no_row_names_that_stops_a_plain_clones_update_fails(
        family, holder, offline, tmp_path, set_up):
    """rv648's S1 and H1. In a plain clone of a holder that records a stray
    case variant of a member's gitlink, or a member mounted by hand, git's
    init dies at that gitlink (`No url found for submodule path`, exit 128)
    before it checks out any member, though every row's gitlink and section
    are there: the run said ok. It names both rows, says where git stopped,
    and names `--no-members`, which names that gitlink and the commit that
    cures it. Typed as printed (all but the hand mount's `family.py add`,
    which mounts it again) and committed, the same run checks both members
    out."""
    env = fetching(isolated(offline, tmp_path))
    stopper = set_up(holder, env, family)
    commit = raw(holder, env, "rev-parse",
                 f"HEAD:{stopper}").stdout.decode("ascii").strip()
    clone = cloned(holder, env, family, tmp_path, recurse=False)

    result = bootstrap(clone, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    why = STOPPED.format(path=stopper)
    assert result.stderr.splitlines()[-2:] == [
        not_fetched((f"members/{MEMBER}", why), (f"members/{OTHER}", why),
                    cure=UNNAMED_CURE),
        failed_on(MEMBER, OTHER)], result.stderr
    assert f"No url found for submodule path '{stopper}'" in result.stderr
    fallback = validate(clone, "--no-members")
    assert fallback.returncode == 1, fallback.stdout + fallback.stderr
    (finding,) = findings(fallback)
    assert finding.startswith(GITLINK_SAID.format(path=stopper,
                                                  commit=commit)), finding
    for line in commands(finding):
        if not line.startswith(f"{PYTHON} "):
            type_line(clone, env, line)
    commit_all(clone, env, "Take the gitlink out as printed")

    again = bootstrap(clone, env, "--skip-members")

    assert again.returncode == 0, again.stdout + again.stderr
    assert after_first_line(again) == FETCHED


def test_a_section_with_no_url_that_stops_the_update_says_to_write_it_back(
        family, holder, offline, tmp_path):
    """rv648's U1. OTHER's section lost its url, committed: in a plain
    clone git's init dies at OTHER's own gitlink, after MEMBER's and before
    it checks out either. The run said ok, and no mode of the validator
    names it. It names both rows and says to write that section back;
    written back as `family.py add` wrote it and committed, the same run
    checks both members out."""
    env = fetching(isolated(offline, tmp_path))
    data = raw(holder, env, "show", f"HEAD:{GITMODULES}").stdout
    committed_gitmodules(holder, env, without_url(data, OTHER))
    clone = cloned(holder, env, family, tmp_path, recurse=False)

    result = bootstrap(clone, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    why = STOPPED.format(path=f"members/{OTHER}")
    assert result.stderr.splitlines()[-2:] == [
        not_fetched((f"members/{MEMBER}", why), (f"members/{OTHER}", why),
                    cure=SECTION_CURE.format(path=f"members/{OTHER}")),
        failed_on(MEMBER, OTHER)], result.stderr
    assert (f"No url found for submodule path 'members/{OTHER}'"
            in result.stderr)
    (clone / GITMODULES).write_bytes(data)
    raw(clone, env, "add", "--", GITMODULES)
    commit_all(clone, env, "OTHER's section written back")

    again = bootstrap(clone, env, "--skip-members")

    assert again.returncode == 0, again.stdout + again.stderr
    assert after_first_line(again) == FETCHED


@pytest.mark.parametrize("set_up", UNNAMED_STOPS.values(), ids=UNNAMED_STOPS)
def test_a_recursive_clone_with_no_credential_is_still_the_skip(
        family, holder, offline, tmp_path, set_up):
    """No misfire. A recursive clone sets `submodule.active` (`.`), and
    git's init then asks only the gitlinks a section gives a path, so the
    stray or the hand mount stops nothing there, and git fails on the
    members' own fetch, as a private member with no token fails. The
    members are the credential's: skipped, and the run ends ok."""
    env = isolated(offline, tmp_path)
    set_up(holder, env, family)
    remote = family["remotes"] / f"{NAME}.git"
    branch = f"w648/{next(BRANCHES)}"
    raw(holder, env, "push", "-q", str(remote), f"HEAD:refs/heads/{branch}")
    clone = tmp_path / "clone"
    # The holder is fetched, as a person with access to it fetches it, and
    # its members are not: `user` refuses the file transport to the clones
    # git makes for submodules.
    made = clone_just_pushed(remote, clone, branch,
                             config=["-c", "protocol.file.allow=user"])
    assert made.returncode != 0, "premise: the members were not fetched"
    assert "transport 'file' not allowed" in made.stderr, made.stderr

    result = bootstrap(clone, env, "--skip-members")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "FETCH INCOMPLETE" in result.stderr
    assert "not for want of a credential" not in result.stderr


def test_a_url_an_earlier_init_registered_is_still_the_skip(family, holder,
                                                            offline,
                                                            tmp_path):
    """No misfire. `git submodule init` wrote each member's url into the
    clone's git config, then the work tree's section for OTHER lost its
    url: git's init reads the url it wrote and does not stop there, and git
    fails on the fetch for want of a credential. The members are skipped and
    the run ends ok."""
    env = isolated(offline, tmp_path)
    clone = cloned(holder, env, family, tmp_path, recurse=False)
    raw(clone, env, "submodule", "init")
    data = (clone / GITMODULES).read_bytes()
    (clone / GITMODULES).write_bytes(without_url(data, OTHER))

    result = bootstrap(clone, env, "--skip-members")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "FETCH INCOMPLETE" in result.stderr
    assert "not for want of a credential" not in result.stderr


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
    both rows, since git stopped at the variant before it checked out
    MEMBER, and the validator; the validator, members checked, names the
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
        not_fetched((f"members/{MEMBER}",
                     STOPPED.format(path=f"Members/{OTHER}")),
                    (f"members/{OTHER}", NO_GITLINK),
                    cure=f"{VALIDATOR_CURE} {UNNAMED_CURE}"),
        failed_on(MEMBER, OTHER)]
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
