# SPDX-License-Identifier: Apache-2.0
"""The family holder's pinned `scripts/bootstrap.py`: `family bootstrap ok`
beside git's exit 128 where git's update died past the holder's own
records (#892).

THE ISSUE'S TWO LINES, each reproduced on #889's round-1 head (3b15de03)
before this change, on git 2.43.0, in the holder and in a plain clone:

- B5. A gitlink committed in `members/IRRS`'s own index that its own
  `.gitmodules` gives no url, at the commit the holder records for IRRS.
  Git's update said `No url found for submodule path
  'members/IRRS/vendor/nested'` and exited 128, and `bootstrap.py
  --skip-members` gave the credential advice and `family bootstrap ok`,
  exit 0. It fails now, naming that gitlink and its cure, with no advice.
- B4. IRSS's gitlink and pin moved by hand to a commit no branch of its
  remote holds. Git's fetch there reached the remote, its fetch of the
  commit said `not our ref`, and its update exited 128; bootstrap said
  `ok` with the advice (#648's credential skip). It fails now, naming the
  member and the commit, with no advice.

WHAT TELLS THEM FROM A MISSING CREDENTIAL, never git's words: for B5, the
member's own index, read as the holder's is (`init_stop`); for B4, a
commit the member's store lacks after the update, where git's own trace
of the run says its fetch there exited 0, or, with a token in use, whose
rewrite a trace would write, where `git fetch origin` made again there,
untraced, exits 0 and the commit is still absent after `git fetch origin
<commit>` (#996). The store alone tells
nothing: a member checked out before the run whose pin moved to a commit
its remote holds, fetched with no credential, is as short of it, which
was measured, and that is still the credential's skip, a control here,
beside a member checked out whole whose own nested gitlink has its url.

WHERE NEITHER TELLS, the run reads as before, the advice and ok, and a row
pins each: a member's own `.gitmodules` git cannot read, or reads only up
to a bad line; a stray git never came to, since a clone that failed ended
its update 1; a member git did not check out at its pin, refused (exit 1)
or dead on an `index.lock` (128), since git's update may have ended there,
even at a commit its store holds and no ref reaches, which git's fetch
does not stop at; a leg this user cannot search; and a member whose fetch
reached another member's remote but not its own. A gitlink git's update skips
(`update = none` in the member's config or its `.gitmodules`, or `active =
false`) is passed as git passes it, and a stop past it is named. B5 and B4
a level down, in a leg, are named up to the holder, and B5 is named before
a leg git never fetched.

GIT'S UPDATE ENDED ON A SIGNAL (#998), lane 5's P3 on #954: IRRS's own
`.gitmodules` gives its `code` leg a `branch` with no value, git 2.43.0's
update crashes in IRRS (`submodule--helper died of signal 11`), goes on
and exits 139, and bootstrap said `ok` with the credential advice. It
names the signal and the code now, gives no advice, and fails. P3 is
skipped where git does not crash; a wrapper `git` that answers (a)'s
update with 139, or is killed by SIGSEGV, holds both shapes on every git.
A code no signal gives, 128 or 255, reads as before.

A SIGNAL GIT'S UPDATE WENT ON PAST (#1056), lane 5's rv996 on #1045: git
keeps only the last code that is not 0, so a member's crash or kill
before a later gitlink's 128 or 1 left no signal in the update's code,
and bootstrap said ok with the advice. Git's own trace of the update
gives the dead git's `child_exit`, and the first is named now: P3, or
IRRS's `git checkout` killed by a `post-checkout` hook standing in for the
OOM killer, then IRSS's pin moved on with no credential, or IRSS's
checkout refused, or B4 at IRSS, which is named after the signal. A hook's
own 137 is no signal, and a git killed in an update that exits 0 is told
nowhere. With a token in use, the update is not traced, and a signal
before a later failure is still the credential's skip, a row pins that.

A CREDENTIAL IN USE (#996): B4 with `SHAPE_LEGS_TOKEN` or
`SHAPE_LEGS_APP_TOKEN` set said the advice to set the token that was set,
and ok. It is named now, and the token is in no output and no file under
TMPDIR, with every trace the person may ask for on; a wrapper `git` logs
the two fetches made again, their argv and their trace variables. With
the token's transport refused, the run is still the credential's skip.

THE SAME FAMILY, OFFLINE RULES AND HELPERS as
`tests/test_family_holder_remedies_compose.py` (#879). A missing credential
is git's refusal of the file transport to the fixture's local remotes, as
in `tests/test_family_holder_bootstrap_texts.py` (#839). A commit a test
makes in a member is pushed to a branch of the member's remote named for
it, so a plain clone fetches it, and the remote's `main` is not moved. A
commit made to be pushed nowhere names the clone it is made in, so no
other row's push puts it on a remote (`unpushed`).
"""

from __future__ import annotations

import itertools
import os
import re
import shlex
import shutil
from pathlib import Path

import pytest

from conftest import rmtree, run_script
from repo_shape import PYTHON
from test_family import FAMILY, SPARE, family, validate  # noqa: F401
from test_family_add_refusals import holder, offline  # noqa: F401
from test_bump_leg_unopenable import made_unopenable, needs_a_mode
from test_family_bootstrap_gate_order import (
    bootstrap, cloned, type_line, with_config,
)
from test_family_dry_run import isolated
from test_family_head_lost_gitmodules import (
    GITMODULES, assert_passes_in_every_mode, commit_all, committed_gitmodules,
    pinned,
)
from test_family_holder_bootstrap_texts import ALONE, OURS
from test_family_holder_remedies_compose import (
    OTHER_ROW, STOP_FAILED, cloning, valued,
)
from test_family_member_path import MEMBER, OTHER, raw
from test_validate_family_typed_states import ROW
from test_validate_family_unnamed_mounts import spare_commits, stage_gitlink

#: How (a)'s line begins where git's update died past the holder's own
#: records.
LEAD = "  UPDATE STOPPED, and not for want of a credential: "

#: How it begins where git's update ended on a signal (#998).
KILLED_LEAD = "  UPDATE KILLED, and not for want of a credential: "

#: What it says of a signal a git that git's update ran died of, which
#: git's code past 128 gives, and of one that killed git itself, which
#: Python gives as a negative code.
DIED_OF = ("git's update ended on signal {signum} ({name}, exit {code}), "
           "which a git it ran died of. Git's own words above say which git "
           "and where.")
KILLED_IT = ("git's update ended on signal {signum} ({name}, exit {code}), "
             "which killed it.")

#: The failure a run whose update ended on a signal ends on.
KILLED_FAILED = ("family bootstrap FAILED: git's update (ended on signal "
                 "{signum})")

#: What it says of a gitlink an `owner`'s own index records with no url
#: (B5), and what cures it, up to the gitlink `above` records for `owner`.
STRAY_SAID = (
    "git stopped at {path}, a gitlink {owner}'s own index records with no "
    "url. No clone of {owner} can check it out: `git -C {owner} rm --cached "
    "-- {rel}` takes it out of that index, or a section of its .gitmodules "
    "can give it its path and url; where its HEAD records it, commit that in "
    "{owner} and push it, then move the gitlink {above} records for {owner} "
    "to that commit{tail}")

#: What it says of a commit `owner` records that git's fetch, which
#: reached the remote, did not bring (B4), and what cures it.
ABSENT_SAID = (
    "git stopped at {path}, whose fetch reached its remote and did not bring "
    "{commit}, the commit {owner} records there. Push {commit} to that remote "
    "from a clone that holds it, or move the gitlink {owner} records there to "
    "a commit that remote holds{tail}")

#: How each ends where the holder records the gitlink, and where a member
#: does.
WITH_ITS_PIN = ", with its pin (`family.py bump`)."
BUMP_NAMED = (f": `{PYTHON} scripts/validate-family.py` names the `bump` that "
              "moves it with its pin.")
UP_TO_THE_HOLDER = ", and so on up to this holder."

#: The gitlink a member's own index records with no url (B5).
NESTED = "vendor/nested"

#: A token for the runs with a credential in use: the fixture's members are
#: local paths, which its rewrite of GitHub's urls never reaches.
TOKEN = "w892-a-token-no-forge-takes"


def said_after_the_fetch(result, source: str = "none") -> list[str]:
    """Bootstrap's own stderr lines after its fetch line, which names the
    credential's `source`, as `after_fetch_line` reads them, the line this
    change adds included."""
    ours = [line for line in result.stderr.splitlines()
            if line.startswith((*OURS, LEAD, KILLED_LEAD))]
    assert ours, result.stderr
    assert re.fullmatch(r"  FETCH INCOMPLETE \(git exit -?\d+\) using "
                        rf"credential source '{source}':", ours[0]), (
        result.stderr)
    return ours[1:]


def git_update(root: Path, env: dict):
    """Git's own `submodule update --init --recursive` in `root`, as (a)
    runs it, its exit code unchecked."""
    return raw(root, env, "submodule", "update", "--init", "--recursive",
               check=False)


def committed(checkout: Path, env: dict, message: str) -> str:
    """What is staged in `checkout` committed, an empty commit where
    nothing is. Returns the commit."""
    raw(checkout, env, "commit", "-q", "--allow-empty", "-m", message)
    return raw(checkout, env, "rev-parse", "HEAD").stdout.decode(
        "ascii").strip()


def pushed(checkout: Path, env: dict, remote: Path, commit: str) -> None:
    """`commit` pushed from `checkout` to a branch of `remote` named for
    it."""
    raw(checkout, env, "push", "-q", str(remote),
        f"{commit}:refs/heads/w892/{commit[:12]}")


def bumped(root: Path, env: dict, family, commit: str) -> None:
    """MEMBER's `commit`, made in the holder's mount, pushed to its remote
    and recorded with `family.py bump`, which moves the gitlink, the pin and
    the digest in one commit."""
    pushed(root / ROW, env, family["remotes"] / f"{MEMBER}.git", commit)
    result = run_script(FAMILY, "bump", "--family-root", str(root),
                        "--member", MEMBER, "--to", commit, env=env)
    assert result.returncode == 0, result.stdout + result.stderr


def stray_in(checkout: Path, family, env: dict) -> str:
    """B5's gitlink: SPARE's newer commit recorded at `NESTED` in
    `checkout`'s own index, which its `.gitmodules` gives no section, and
    committed there. Returns the commit."""
    stage_gitlink(checkout, NESTED, spare_commits(family)[1])
    return committed(checkout, env, "A gitlink its .gitmodules gives no url")


def b5(root: Path, env: dict, family) -> None:
    """B5 in the holder: MEMBER moved to a commit of its own whose index
    records the stray, by `family.py bump`, so the gate passes."""
    bumped(root, env, family, stray_in(root / ROW, family, env))


#: A number for each commit `unpushed` makes in this session.
MADE = itertools.count(1)


def unpushed(family, env: dict, tmp_path: Path,
             remote: str = OTHER) -> tuple[Path, str]:
    """A clone of the fixture's `remote` (OTHER's unless said) of the
    test's own and an empty commit made on its `main` there and never
    pushed: no store the holder reaches holds it, and its tree is that
    `main`'s. Returns both.

    ITS MESSAGE NAMES THE CLONE, a path no other row's clone has, so no
    other row makes the same commit. Under one message, every row's had
    the same parent, tree, author and message, and git dates a commit to
    the second, so two rows that made one in the same second made the
    same commit. The remotes are the module's: where the earlier row had
    pushed it (`pin_moved_on`, B4's cure), the later row's B4 commit was
    on the remote, git's fetch brought it, its update exited 1, not 128,
    and the walk never ran. CI, which runs these rows less than a second
    apart, failed the refused checkout's row so at 4f97fedb and the
    unreadable leg's at 938a83ef; a commit date fixed by
    `GIT_COMMITTER_DATE` and `GIT_AUTHOR_DATE` fails both on git 2.43.0.

    AND A NUMBER OF ITS OWN (`MADE`), since the clone's path alone is not
    one: under `tmp_path_retention_policy=failed` pytest removes a passed
    row's directory, and gives the next row whose name begins with the
    same 30 characters the same one. Two rows of #996 so named,
    `test_with_a_credential_in_use_0` both, made one commit in the same
    second, and the second row's commit was on a branch of the remote."""
    clone = tmp_path / f"unpushed-{remote}"
    raw(tmp_path, env, "clone", "-q", "--",
        str(family["remotes"] / f"{remote}.git"), str(clone))
    return clone, committed(clone, env, f"Made in {clone} and never pushed "
                                        f"({next(MADE)})")


def moved_by_hand(root: Path, env: dict, project: str, commit: str) -> None:
    """`project`'s gitlink and pin moved to `commit` by hand and committed,
    as no `family.py bump` moves them to a commit no branch of the member's
    remote reaches (`member-to-local-only`, #613)."""
    pin = pinned(root, project)
    raw(root, env, "update-index", "--cacheinfo",
        f"160000,{commit},members/{project}")
    manifest = root / "family.yaml"
    text = manifest.read_text(encoding="utf-8")
    assert text.count(pin) == 1, "fixture drift: the row's pin line"
    manifest.write_text(text.replace(pin, commit), encoding="utf-8")
    raw(root, env, "add", "--", "family.yaml")
    commit_all(root, env, f"{project} moved by hand")


def b4(root: Path, env: dict, family, tmp_path: Path) -> str:
    """B4 in the holder: OTHER's gitlink and pin at `unpushed`'s commit.
    Returns the commit."""
    _, commit = unpushed(family, env, tmp_path)
    moved_by_hand(root, env, OTHER, commit)
    return commit


def in_place(holder: Path, env: dict, family, tmp_path: Path) -> Path:
    """The holder itself, every member checked out."""
    return holder


def plain_clone(holder: Path, env: dict, family, tmp_path: Path) -> Path:
    """A plain clone of the holder, no member checked out."""
    return cloned(holder, env, family, tmp_path, recurse=False)


#: Where each state is asked: the holder, and a plain clone of it.
WHERE = {"holder": in_place, "plain-clone": plain_clone}


# --- B5: a gitlink a member's own index records with no url -----------------

@pytest.mark.parametrize("where", WHERE.values(), ids=WHERE)
def test_b5_a_gitlink_a_member_gives_no_url_fails_naming_it(
        family, holder, offline, tmp_path, where):
    """B5: git's update died at `members/IRRS/vendor/nested` (exit 128),
    and bootstrap said ok with the credential advice. It names the gitlink,
    the member whose index records it and the cure, gives no advice, and
    fails on that gitlink; git's own update exits 128 there, as it says."""
    env = cloning(offline, tmp_path, family)
    b5(holder, env, family)
    root = where(holder, env, family, tmp_path)

    result = bootstrap(root, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert said_after_the_fetch(result) == [
        LEAD + STRAY_SAID.format(path=f"{ROW}/{NESTED}", owner=ROW,
                                 rel=NESTED, above="this holder",
                                 tail=WITH_ITS_PIN),
        STOP_FAILED.format(path=f"{ROW}/{NESTED}")]
    assert git_update(root, env).returncode == 128


def test_b5_s_cure_typed_as_printed_ends_ok(family, holder, offline,
                                            tmp_path):
    """B5's cure: the `git -C` line typed as printed takes the gitlink out
    of the member's index; committed there, pushed, and recorded with
    `family.py bump`, the run checks every member and leg out and ends ok,
    and the gate passes in every mode."""
    env = cloning(offline, tmp_path, family)
    b5(holder, env, family)
    result = bootstrap(holder, env, "--skip-members")
    (line,) = re.findall(r"`(git -C [^`]*)`", result.stderr)

    type_line(holder, env, line)
    bumped(holder, env, family, committed(holder / ROW, env,
                                          "The gitlink taken out"))

    booted = bootstrap(holder, env, "--skip-members")
    assert booted.returncode == 0, booted.stdout + booted.stderr
    assert "  every member and leg fetched" in booted.stdout.splitlines()
    assert_passes_in_every_mode(holder, 2)


def test_b5_in_a_leg_is_named_up_to_the_holder(family, holder, offline,
                                               tmp_path):
    """B5 a level down: the gitlink in the own index of IRRS's `code` leg,
    which IRRS records and the holder records IRRS at. Git's update died
    there, and the line names it, the leg whose index records it, and the
    cure up to the holder."""
    env = cloning(offline, tmp_path, family)
    assert git_update(holder, env).returncode == 0
    leg = holder / ROW / "code"
    made = stray_in(leg, family, env)
    pushed(leg, env, family["remotes"] / f"{MEMBER}-code.git", made)
    raw(holder / ROW, env, "add", "--", "code")
    bumped(holder, env, family, committed(holder / ROW, env, "The leg moved"))

    result = bootstrap(holder, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert said_after_the_fetch(result) == [
        LEAD + STRAY_SAID.format(path=f"{ROW}/code/{NESTED}",
                                 owner=f"{ROW}/code", rel=NESTED, above=ROW,
                                 tail=UP_TO_THE_HOLDER),
        STOP_FAILED.format(path=f"{ROW}/code/{NESTED}")]


# --- B4: a member's commit git's fetch did not bring -------------------------

@pytest.mark.parametrize("where", WHERE.values(), ids=WHERE)
def test_b4_a_commit_the_fetch_did_not_bring_fails_naming_it(
        family, holder, offline, tmp_path, where):
    """B4: git's fetch in IRSS reached its remote and did not bring the
    commit the holder records, and its update exited 128; bootstrap said ok
    with the credential advice. It names the member, the commit and the
    cure, gives no advice, and fails on the member; git's own update exits
    128 there, and the run leaves no trace directory behind."""
    env = cloning(offline, tmp_path, family)
    commit = b4(holder, env, family, tmp_path)
    root = where(holder, env, family, tmp_path)

    result = bootstrap(root, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert said_after_the_fetch(result) == [
        LEAD + ABSENT_SAID.format(path=OTHER_ROW, commit=commit,
                                  owner="this holder", tail=BUMP_NAMED),
        STOP_FAILED.format(path=OTHER_ROW)]
    assert git_update(root, env).returncode == 128
    assert list(offline.temp.glob("bootstrap-trace-*")) == []


def test_b4_s_cures_as_printed(family, holder, offline, tmp_path):
    """B4's cures: the gate names the `bump` that moves the gitlink and the
    pin, as the line says; and the commit pushed from the clone that holds
    it, the run checks every member and leg out and ends ok, and the gate
    passes in every mode."""
    env = cloning(offline, tmp_path, family)
    clone, commit = unpushed(family, env, tmp_path)
    moved_by_hand(holder, env, OTHER, commit)

    gate = validate(holder)

    assert gate.returncode == 2, gate.stdout + gate.stderr
    assert "member-commit-unresolvable" in gate.stderr
    assert "scripts/family.py bump --family-root " in gate.stderr
    pushed(clone, env, family["remotes"] / f"{OTHER}.git", commit)
    booted = bootstrap(holder, env, "--skip-members")
    assert booted.returncode == 0, booted.stdout + booted.stderr
    assert "  every member and leg fetched" in booted.stdout.splitlines()
    assert_passes_in_every_mode(holder, 2)


def leg_moved(root: Path, env: dict, family, tmp_path: Path, *,
              stray: bool) -> str:
    """Every member and leg checked out by git's update; then IRRS's `code`
    leg recorded in IRRS's own index at `unpushed`'s commit of the leg's
    remote, with B5's stray beside it where `stray` says, committed in
    IRRS and recorded with `family.py bump`. Returns the leg's commit."""
    assert git_update(root, env).returncode == 0
    _, commit = unpushed(family, env, tmp_path, f"{MEMBER}-code")
    member = root / ROW
    raw(member, env, "update-index", "--cacheinfo", f"160000,{commit},code")
    bumped(root, env, family, stray_in(member, family, env) if stray
           else committed(member, env, "Its code leg moved by hand"))
    return commit


def test_b4_in_a_leg_is_named_up_to_the_holder(family, holder, offline,
                                               tmp_path):
    """B4 a level down (lane 5's P2 and R1 on #954): IRRS's `code` leg
    recorded in IRRS at a commit no branch of the leg's remote holds. Git's
    fetch there reached the remote and did not bring it, and its update
    exited 128. The whole line is named, the member that records the leg,
    and the cure up to the holder."""
    env = cloning(offline, tmp_path, family)
    commit = leg_moved(holder, env, family, tmp_path, stray=False)

    result = bootstrap(holder, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert said_after_the_fetch(result) == [
        LEAD + ABSENT_SAID.format(path=f"{ROW}/code", commit=commit,
                                  owner=ROW, tail=UP_TO_THE_HOLDER),
        STOP_FAILED.format(path=f"{ROW}/code")]
    assert git_update(holder, env).returncode == 128


def test_b5_is_named_before_a_leg_git_never_fetched(family, holder,
                                                    offline, tmp_path):
    """Git's order (lane 5's R6 on #954): B5's stray in IRRS's own index,
    and IRRS's `code` leg recorded beside it at a commit its store lacks.
    Git's init in IRRS dies at the stray before it updates any leg, so the
    leg's commit was never fetched, and B5 is what is named."""
    env = cloning(offline, tmp_path, family)
    leg_moved(holder, env, family, tmp_path, stray=True)

    result = bootstrap(holder, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert said_after_the_fetch(result) == [
        LEAD + STRAY_SAID.format(path=f"{ROW}/{NESTED}", owner=ROW,
                                 rel=NESTED, above="this holder",
                                 tail=WITH_ITS_PIN),
        STOP_FAILED.format(path=f"{ROW}/{NESTED}")]


# --- the credential's skip, as it was ----------------------------------------

def pin_moved_on(holder: Path, env: dict, family, tmp_path: Path) -> Path:
    """IRSS's gitlink and pin moved on to a commit a branch of its remote
    holds and its store does not, as pulling another's `family.py bump`
    leaves a holder whose members were checked out before."""
    clone, commit = unpushed(family, env, tmp_path)
    pushed(clone, env, family["remotes"] / f"{OTHER}.git", commit)
    moved_by_hand(holder, env, OTHER, commit)
    return holder


def beside_a_member_checked_out_whole(holder: Path, env: dict, family,
                                      tmp_path: Path) -> Path:
    """IRRS given a nested gitlink WITH its section and url, SPARE mounted
    by `git submodule add` and recorded with `family.py bump`, every member
    and leg then checked out whole by git's update, and IRSS's pin then
    moved on (`pin_moved_on`)."""
    raw(holder / ROW, env, "submodule", "add", "-q", "--",
        str(family["remotes"] / f"{SPARE}.git"), NESTED)
    bumped(holder, env, family, committed(holder / ROW, env,
                                          "A nested member with its url"))
    assert git_update(holder, env).returncode == 0
    assert (holder / ROW / NESTED / "project.yaml").is_file()
    return pin_moved_on(holder, env, family, tmp_path)


#: `(the state, git's update's exit code in it with no credential)`: every
#: member left unchecked out, a checked-out member whose pin moved on, and
#: that beside a member checked out whole.
CREDENTIAL_S = {
    "members-not-checked-out": (plain_clone, 1),
    "pin-moved-on": (pin_moved_on, 128),
    "beside-a-member-checked-out-whole": (beside_a_member_checked_out_whole,
                                          128),
}


@pytest.mark.parametrize("make, code", CREDENTIAL_S.values(),
                         ids=CREDENTIAL_S)
def test_the_credential_s_skip_is_as_it_was(family, holder, offline,
                                            tmp_path, make, code):
    """No misfire: where git cannot reach the members' remotes, as for want
    of a credential, the store lacks the commit as in B4, but no fetch git
    made reached a remote, and every gitlink a member's index records has
    its url. The advice stands alone, and the run ends ok, as before. With
    the credential, the same run checks every member and leg out."""
    env = cloning(offline, tmp_path, family)
    root = make(holder, env, family, tmp_path)
    without = isolated(offline, tmp_path)

    result = bootstrap(root, without, "--skip-members")

    assert result.returncode == 0, result.stdout + result.stderr
    assert said_after_the_fetch(result) == [ALONE]
    assert result.stdout.endswith("\nfamily bootstrap ok\n"), result.stdout
    assert git_update(root, without).returncode == code
    fetched = bootstrap(root, env, "--skip-members")
    assert fetched.returncode == 0, fetched.stdout + fetched.stderr
    assert "  every member and leg fetched" in fetched.stdout.splitlines()


def test_a_stray_git_never_came_to_is_not_said(family, holder, offline,
                                               tmp_path):
    """No misfire: B5 in IRRS, and IRSS's store gone, so git's update must
    clone IRSS first, which it cannot for want of a credential. A clone
    that fails ends git's update 1 before it checks out or enters any
    member, so it never came to the stray: the advice stands and the run
    ends ok, as before."""
    env = cloning(offline, tmp_path, family)
    b5(holder, env, family)
    raw(holder, env, "submodule", "deinit", "-q", "-f", "--", OTHER_ROW)
    rmtree(holder / ".git" / "modules" / OTHER_ROW)
    without = isolated(offline, tmp_path)

    result = bootstrap(holder, without, "--skip-members")

    assert result.returncode == 0, result.stdout + result.stderr
    assert said_after_the_fetch(result) == [ALONE]
    assert git_update(holder, without).returncode == 1


def test_a_member_s_gitmodules_git_cannot_read_is_read_as_before(
        family, holder, offline, tmp_path):
    """Where neither check tells: IRRS's own `.gitmodules` gives its `code`
    leg `update = None`, a value git dies on as it reads the file (#768),
    committed there and recorded by hand, since `family.py bump`'s own git
    dies reading it too. Git's update dies in IRRS (exit 128), but at no
    gitlink with no url and no commit a fetch did not bring, so nothing
    past the holder's records is said: the run reads as before, the advice
    and ok."""
    env = cloning(offline, tmp_path, family)
    member = holder / ROW
    (member / ".gitmodules").write_bytes(
        valued((member / ".gitmodules").read_bytes(), "code"))
    raw(member, env, "add", "--", ".gitmodules")
    moved_by_hand(holder, env, MEMBER,
                  committed(member, env, "A value git dies on"))

    result = bootstrap(holder, env, "--skip-members")

    assert result.returncode == 0, result.stdout + result.stderr
    assert said_after_the_fetch(result) == [ALONE]
    assert git_update(holder, env).returncode == 128


def refused_checkout(root: Path, env: dict, family, tmp_path: Path) -> None:
    """IRRS's checkout moved by hand to a commit of its own that changes
    `NOTES.md` and records B5's gitlink, with `NOTES.md` then edited and
    not committed, while the holder still records the pin; and B4 at IRSS.
    Git's checkout of the pin in IRRS refuses to overwrite the edit (`git
    checkout`'s own exit 1, which its update passes), and git dies at IRSS
    (exit 128)."""
    member = root / ROW
    (member / "NOTES.md").write_bytes(b"moved on by hand" + chr(10).encode())
    raw(member, env, "add", "--", "NOTES.md")
    stray_in(member, family, env)
    (member / "NOTES.md").write_bytes(b"edited" + chr(10).encode())
    b4(root, env, family, tmp_path)


def locked_checkout(root: Path, env: dict, family, tmp_path: Path) -> None:
    """IRRS's gitlink and pin moved by hand to its checkout's HEAD~1, which
    its store holds, with an `index.lock` left in that store; and B5's
    stray committed in IRSS's own index, which the holder records. Git's
    checkout in IRRS dies (`Unable to create ... index.lock`, exit 128),
    which ends its update there, before it comes to IRSS."""
    member = root / ROW
    older = raw(member, env, "rev-parse", "HEAD~1").stdout.decode().strip()
    moved_by_hand(root, env, MEMBER, older)
    locked_in(member, env)
    moved_by_hand(root, env, OTHER, stray_in(root / OTHER_ROW, family, env))


def held_and_locked(root: Path, env: dict, family, tmp_path: Path) -> None:
    """IRRS's gitlink and pin moved by hand to a commit its store holds
    and no ref of it reaches, made there with `git commit-tree` and pushed
    nowhere, with an `index.lock` left in that store. Git's fetch there
    reaches the remote, its fetch of the commit is answered from the store
    (exit 0), and its checkout dies (exit 128): no branch of the remote
    holds the commit, as in B4, but git did not stop for want of it."""
    member = root / ROW
    held = raw(member, env, "commit-tree", "HEAD^{tree}", "-p", "HEAD", "-m",
               "Held, and no ref reaches it").stdout.decode().strip()
    moved_by_hand(root, env, MEMBER, held)
    locked_in(member, env)


def locked_in(checkout: Path, env: dict) -> None:
    """An empty `index.lock` left in the store `checkout` reads."""
    lock = raw(checkout, env, "rev-parse", "--git-path",
               "index.lock").stdout.decode().strip()
    (checkout / lock).write_bytes(b"")


#: A checkout git did not make at the commit recorded for it, its own
#: refusal (exit 1, which git's update passes) or its death (exit 128, which
#: ends git's update), with a stop past it that the walk named before round
#: 1: B4 at IRSS, and B5 at IRSS, which git never came to; and a death at a
#: commit the store holds and no ref reaches, which the walk named B4.
NOT_CHECKED_OUT_THERE = {"refused": refused_checkout,
                         "index-lock": locked_checkout,
                         "held-commit-index-lock": held_and_locked}


@pytest.mark.parametrize("make", NOT_CHECKED_OUT_THERE.values(),
                         ids=NOT_CHECKED_OUT_THERE)
def test_a_member_git_did_not_check_out_is_untold(family, holder, offline,
                                                  tmp_path, make):
    """A checkout at another commit than the one recorded is untold, and
    nothing past it is asked: whether git's checkout there refused, which
    git passes, or died, which ends its update, is not told, and with an
    `index.lock` in IRRS round 0's walk named B5's stray in IRSS, where git
    never came (measured for lane 5's index.lock case on #954), and, at a
    commit IRRS's store holds and no ref reaches, B4 at IRRS, whose fetch
    git's update did not die of. The run reads as before #954, the advice
    and ok, while git's update exits 128."""
    env = cloning(offline, tmp_path, family)
    make(holder, env, family, tmp_path)

    result = bootstrap(holder, env, "--skip-members")

    assert result.returncode == 0, result.stdout + result.stderr
    assert said_after_the_fetch(result) == [ALONE]
    assert git_update(holder, env).returncode == 128


def update_none_in_config(root: Path, env: dict) -> None:
    """`update = none` for IRRS in the holder's own config (lane 5's P1)."""
    raw(root, env, "config", f"submodule.{ROW}.update", "none")


def update_none_in_gitmodules(root: Path, env: dict) -> None:
    """`update = none` in IRRS's section of HEAD's `.gitmodules`, which
    git's init copies into the config, committed."""
    data = raw(root, env, "show", f"HEAD:{GITMODULES}").stdout
    line = f"\tpath = {ROW}\n".encode()
    assert data.count(line) == 1, data
    committed_gitmodules(root, env,
                         data.replace(line, line + b"\tupdate = none\n"))


def as_it_is(root: Path, env: dict) -> None:
    """Nothing more in the holder."""


def as_given(env: dict) -> dict:
    """`env` as it is."""
    return env


def inactive(env: dict) -> dict:
    """`env` with `submodule.members/IRRS.active` false in git's command
    scope, above the local config git's init writes `true` in."""
    return with_config(env, f"submodule.{ROW}.active", "false")


#: `(the state, the environment it is read in)`: IRRS's update strategy
#: `none`, in the holder's config or its `.gitmodules`, and IRRS inactive.
SKIPPED_BY_GIT = {
    "update-none-in-config": (update_none_in_config, as_given),
    "update-none-in-gitmodules": (update_none_in_gitmodules, as_given),
    "inactive": (as_it_is, inactive),
}


@pytest.mark.parametrize("make, scoped", SKIPPED_BY_GIT.values(),
                         ids=SKIPPED_BY_GIT)
def test_a_member_git_s_update_skips_is_passed(family, holder, offline,
                                               tmp_path, make, scoped):
    """Lane 5's SHOULD 1 on #954 (P1): B5's stray in IRRS, which git's
    update skips without a look (`Skipping submodule`), and IRSS's pin
    moved on, with no credential. Git dies at IRSS for want of the
    credential (exit 128). The walk entered IRRS all the same and failed
    on the stray with no advice; it passes IRRS now, so the run is the
    credential's skip, the advice and ok, as before #954. With the
    credential, git skips IRRS, checks IRSS out and exits 0, and the run
    says every member and leg was fetched: git never comes to the stray."""
    env = cloning(offline, tmp_path, family)
    b5(holder, env, family)
    pin_moved_on(holder, env, family, tmp_path)
    make(holder, env)
    without = scoped(isolated(offline, tmp_path))

    result = bootstrap(holder, without, "--skip-members")

    assert result.returncode == 0, result.stdout + result.stderr
    assert said_after_the_fetch(result) == [ALONE]
    assert git_update(holder, without).returncode == 128
    fetched = bootstrap(holder, scoped(env), "--skip-members")
    assert fetched.returncode == 0, fetched.stdout + fetched.stderr
    assert "  every member and leg fetched" in fetched.stdout.splitlines()


@needs_a_mode
def test_a_leg_this_user_cannot_search_is_untold(family, holder, offline,
                                                 tmp_path):
    """Lane 5's SHOULD 2 on #954 (P7 and P9): IRRS's `code` leg made mode
    000, and B4 at IRSS. The walk's `stat` of the leg's `.git` is refused,
    which ended the run in a `PermissionError` traceback; that leg is
    untold now, nothing past it asked, and the run says what it said before
    #954, the advice and ok. Git's update in IRRS cannot clone the leg
    and exits 1 (`Failed to clone 'code' a second time, aborting`); the
    holder's update passes that, as it passes a checkout that refused,
    and dies at IRSS's B4 (exit 128), so the walk meets the leg. CI's
    exit 1 here at 938a83ef, read then as git 2.55.0 ending its update at
    the leg, was B4's commit already on the remote (`unpushed`): git
    2.43.0 ends with the same two lines, and exits 1, where it is."""
    env = cloning(offline, tmp_path, family)
    b4(holder, env, family, tmp_path)

    with made_unopenable(holder / ROW, "code"):
        result = bootstrap(holder, env, "--skip-members")
        update = git_update(holder, env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    assert said_after_the_fetch(result) == [ALONE]
    assert update.returncode == 128


def test_a_fetch_that_reached_another_member_s_remote_tells_nothing(
        family, holder, offline, tmp_path):
    """The fetch THERE (lane 5's R7 on #954): IRRS's pin moved on to a
    commit its remote holds, whose fetch reaches that remote, and B4's
    commit at IRSS, whose `origin` names no repository, so its fetch never
    reaches one. IRSS is untold, whatever IRRS's fetch reached: the advice
    and ok, as before #954."""
    env = cloning(offline, tmp_path, family)
    clone, commit = unpushed(family, env, tmp_path, MEMBER)
    pushed(clone, env, family["remotes"] / f"{MEMBER}.git", commit)
    moved_by_hand(holder, env, MEMBER, commit)
    b4(holder, env, family, tmp_path)
    raw(holder / OTHER_ROW, env, "remote", "set-url", "origin",
        str(tmp_path / "no-repository-here.git"))

    result = bootstrap(holder, env, "--skip-members")

    assert result.returncode == 0, result.stdout + result.stderr
    assert said_after_the_fetch(result) == [ALONE]
    assert git_update(holder, env).returncode == 128


def test_a_member_s_gitmodules_read_up_to_a_bad_line_is_read_as_before(
        family, holder, offline, tmp_path):
    """Where neither check tells (lane 5's R11 on #954): IRRS's own
    `.gitmodules` with a line git cannot parse before `code`'s section,
    committed there and recorded by hand, and the work tree's file then
    deleted. Git reads IRRS's index's file up to that line and dies at
    `code` (exit 128), whose section is past it, so a section written back
    would be a second one: nothing past the holder's records is said, and
    the run reads as before, the advice and ok."""
    env = cloning(offline, tmp_path, family)
    member = holder / ROW
    data = (member / GITMODULES).read_bytes()
    second = data.index(b"[submodule", 1)
    bad = (chr(9) + 'branch = "unterminated' + chr(10)).encode("ascii")
    committed_gitmodules(member, env, data[:second] + bad + data[second:])
    made = raw(member, env, "rev-parse", "HEAD").stdout.decode().strip()
    moved_by_hand(holder, env, MEMBER, made)
    (member / GITMODULES).unlink()

    result = bootstrap(holder, env, "--skip-members")

    assert result.returncode == 0, result.stdout + result.stderr
    assert said_after_the_fetch(result) == [ALONE]
    assert git_update(holder, env).returncode == 128


# --- git's update ended on a signal (#998) ----------------------------------

def p3(holder: Path, env: dict) -> None:
    """Lane 5's P3 on #954: IRRS's own `.gitmodules` gives its `code` leg
    a `branch` with no value, committed there and recorded by hand, as
    `family.py bump`'s own git reads that file too. Git 2.43.0's update
    crashes in IRRS (`submodule--helper died of signal 11`) and goes on
    to IRSS; from 2.43.1 git refuses that line as it refuses a `url` with
    none, and dies there (128)."""
    member = holder / ROW
    data = (member / GITMODULES).read_bytes()
    line = (chr(9) + "path = code" + chr(10)).encode()
    assert data.count(line) == 1, data
    bare = (chr(9) + "branch" + chr(10)).encode()
    (member / GITMODULES).write_bytes(data.replace(line, line + bare))
    raw(member, env, "add", "--", GITMODULES)
    moved_by_hand(holder, env, MEMBER,
                  committed(member, env, "A branch with no value"))


def test_p3_a_member_s_gitmodules_git_crashes_on_fails_naming_the_signal(
        family, holder, offline, tmp_path):
    """P3 (`p3`): git 2.43.0's update crashes in IRRS, goes on to IRSS,
    and exits 139; bootstrap said ok with the credential advice. It names
    the signal and the code now, gives no advice, and fails on git's
    update. Skipped where git does not crash so."""
    env = cloning(offline, tmp_path, family)
    p3(holder, env)

    result = bootstrap(holder, env, "--skip-members")
    update = git_update(holder, env)

    if update.returncode != 139:
        pytest.skip(f"this git's update exits {update.returncode} here, "
                    "where git 2.43.0's crashes (exit 139)")
    assert result.returncode == 1, result.stdout + result.stderr
    assert said_after_the_fetch(result) == [
        KILLED_LEAD + DIED_OF.format(signum=11, name="SIGSEGV", code=139),
        KILLED_FAILED.format(signum=11)]


#: A wrapper `git` here is a POSIX shell script, which Windows does not run
#: by its `#!` line.
POSIX_WRAPPER = pytest.mark.skipif(
    os.name == "nt", reason="a wrapper `git` here is a POSIX shell script, "
    "which Windows does not execute by its `#!` line")


#: The update (a) runs and the fetches the walk runs, as the wrapper's
#: `case` matches them among the commands bootstrap runs itself.
UPDATE_CASE = '*" submodule update --init --recursive "*'
FETCH_CASE = '*" fetch "*'


def wrapped(env: dict, tmp_path: Path, action: str = ":",
            log: Path | None = None) -> dict:
    """`env` with a wrapper `git` first on PATH, which runs `action`, a
    shell command, for the `git submodule update --init --recursive` that
    (a) runs, and the real git, by its absolute path, for every other
    command, bootstrap's own and the walk's; the gits git starts find its
    own first on their PATH. With `log`, it first writes a line there for
    that update and for each fetch: the command's arguments, a token in
    them masked as `<token>`, then the `GIT_TRACE*` variables and the
    `GIT_PROTOCOL_FROM_USER` its environment holds."""
    real = shutil.which("git", path=env["PATH"])
    assert real, env["PATH"]
    shim = tmp_path / "wrapper"
    shim.mkdir()
    script = shim / "git"
    logged = [] if log is None else [
        'case " $* " in', f"{UPDATE_CASE}|{FETCH_CASE})",
        'args=$(printf "%s" "$*" | sed '
        '"s/x-access-token:[^@]*@/x-access-token:<token>@/g")',
        'traces=$(env | grep -E "^(GIT_TRACE|GIT_PROTOCOL_FROM_USER)" '
        '| sort | paste -s -d " " -)',
        f'echo "$args | $traces" >> {shlex.quote(str(log))} ;;', "esac"]
    script.write_bytes(chr(10).join([
        "#!/bin/sh", *logged,
        'case " $* " in', f"{UPDATE_CASE}) {action} ;;", "esac",
        f'exec {shlex.quote(real)} "$@"', ""]).encode())
    script.chmod(0o755)
    return {**env, "PATH": str(shim) + os.pathsep + env["PATH"]}


#: `(what the wrapper answers (a)'s update with, what (a)'s line says of
#: it)`: 139, the code git's update ends with where a git it ran died of
#: SIGSEGV, as git 2.43.0's in P3; and the wrapper killed by SIGSEGV itself,
#: with no core file, whose code Python gives as -11.
KILLED_BY = {
    "exit-139": ("exit 139",
                 DIED_OF.format(signum=11, name="SIGSEGV", code=139)),
    "sigsegv": ("ulimit -c 0; kill -s SEGV $$",
                KILLED_IT.format(signum=11, name="SIGSEGV", code=-11)),
}


@POSIX_WRAPPER
@pytest.mark.parametrize("action, said", KILLED_BY.values(), ids=KILLED_BY)
def test_an_update_ended_on_a_signal_fails_naming_it(family, holder, offline,
                                                     tmp_path, action, said):
    """#998's two shapes on any git, every member checked out at its pin:
    git's update ended on SIGSEGV, a git it ran dead of it (139) or git
    itself killed by it (-11). Bootstrap said ok with the credential
    advice for both. It names the signal and the code now, gives no
    advice, and fails on git's update. The credential's own 128 keeps the
    advice and ok (`test_the_credential_s_skip_is_as_it_was`)."""
    env = cloning(offline, tmp_path, family)

    result = bootstrap(holder, wrapped(env, tmp_path, action),
                       "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert said_after_the_fetch(result) == [KILLED_LEAD + said,
                                            KILLED_FAILED.format(signum=11)]


#: What the wrapper answers (a)'s update with, where no signal gives the
#: code: git's own `die`, 128, which the walk past the holder's records
#: asks, and finds nothing in with every member checked out at its pin;
#: and 255, past every signal's `128 + N`, which git exits with where a
#: command of its returns -1.
NO_SIGNAL = {"exit-128": "exit 128", "exit-255": "exit 255"}


@POSIX_WRAPPER
@pytest.mark.parametrize("action", NO_SIGNAL.values(), ids=NO_SIGNAL)
def test_a_code_no_signal_gives_is_read_as_before(family, holder, offline,
                                                  tmp_path, action):
    """No misfire: where git's update exits with a code no signal gives,
    nothing is said of a signal, and the run reads as before, the advice
    and ok."""
    env = cloning(offline, tmp_path, family)

    result = bootstrap(holder, wrapped(env, tmp_path, action),
                       "--skip-members")

    assert result.returncode == 0, result.stdout + result.stderr
    assert said_after_the_fetch(result) == [ALONE]
    assert result.stdout.endswith("\nfamily bootstrap ok\n"), result.stdout


# --- a credential in use -----------------------------------------------------

def test_with_a_credential_in_use_b5_is_named_and_the_token_is_not(
        family, holder, offline, tmp_path):
    """B5 is read from the member's own index, which needs no trace, so it
    is named with a credential in use too, and the token is printed
    nowhere."""
    env = {**cloning(offline, tmp_path, family), "SHAPE_LEGS_TOKEN": TOKEN}
    b5(holder, env, family)

    result = bootstrap(holder, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert said_after_the_fetch(result, "SHAPE_LEGS_TOKEN") == [
        LEAD + STRAY_SAID.format(path=f"{ROW}/{NESTED}", owner=ROW,
                                 rel=NESTED, above="this holder",
                                 tail=WITH_ITS_PIN),
        STOP_FAILED.format(path=f"{ROW}/{NESTED}")]
    assert TOKEN not in result.stdout + result.stderr


#: The two variables a credential arrives in, the App's first.
CREDENTIALS = ("SHAPE_LEGS_APP_TOKEN", "SHAPE_LEGS_TOKEN")

#: The trace files `traced_by_the_caller` asks for that a run writes where
#: every remote is a local path: GIT_TRACE_CURL's is written for http only.
TRACES = ("trace.txt", "trace2-event.json", "trace2-normal.txt",
          "trace2-perf.txt")


def traced_by_the_caller(env: dict, offline, tmp_path: Path) -> dict:
    """`env` with every trace a person may ask for written under the run's
    TMPDIR: `GIT_TRACE`, `GIT_TRACE2_EVENT` and `GIT_TRACE_CURL` in the
    environment, and trace2's normal and perf targets in the global
    config, a copy of the one `env` names with `trace2.normalTarget` and
    `trace2.perfTarget` added."""
    temp = offline.temp
    config = tmp_path / "traced-gitconfig"
    config.write_bytes(
        Path(env["GIT_CONFIG_GLOBAL"]).read_bytes() + chr(10).join([
            "[trace2]",
            f'{chr(9)}normalTarget = "{(temp / TRACES[2]).as_posix()}"',
            f'{chr(9)}perfTarget = "{(temp / TRACES[3]).as_posix()}"',
            ""]).encode())
    return {**env, "GIT_CONFIG_GLOBAL": str(config),
            "GIT_TRACE": str(temp / TRACES[0]),
            "GIT_TRACE2_EVENT": str(temp / TRACES[1]),
            "GIT_TRACE_CURL": str(temp / "trace-curl.txt")}


def files_holding(temp: Path, text: str) -> list[str]:
    """Every file under `temp` whose bytes hold `text`, as a path relative
    to it."""
    return [path.relative_to(temp).as_posix()
            for path in sorted(temp.rglob("*"))
            if path.is_file() and text.encode() in path.read_bytes()]


@pytest.mark.parametrize("variable", CREDENTIALS)
def test_with_a_credential_in_use_b4_is_named_and_the_token_is_not(
        family, holder, offline, tmp_path, variable):
    """#996, lane 5's SHOULD 4 on #954: B4 at IRSS with a token in
    `variable`. Git's update, which carries the token's rewrite in its
    argv, is not traced, and the run gave the advice to set the token that
    was set, and ok. The two fetches git's update makes in IRSS are made
    again, untraced: the first reaches the remote, the commit is still
    absent after the second, and B4 is named, exit 1, with no advice.
    Every trace the person asked for is on, the environment's and the
    global config's, and the walk's own gits, which carry no token, write
    each; the token is in none of them, nor in any other file under
    TMPDIR, nor in the output. Before, git's update wrote it into
    `GIT_TRACE2_EVENT`'s file."""
    env = {**cloning(offline, tmp_path, family), variable: TOKEN}
    commit = b4(holder, env, family, tmp_path)

    result = bootstrap(holder, traced_by_the_caller(env, offline, tmp_path),
                       "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert said_after_the_fetch(result, variable) == [
        LEAD + ABSENT_SAID.format(path=OTHER_ROW, commit=commit,
                                  owner="this holder", tail=BUMP_NAMED),
        STOP_FAILED.format(path=OTHER_ROW)]
    assert TOKEN not in result.stdout + result.stderr
    assert files_holding(offline.temp, TOKEN) == []
    assert [name for name in TRACES
            if (offline.temp / name).is_file()] == list(TRACES)


#: The states the credential's skip is asked in with a token in use:
#: IRSS's pin moved on to a commit its remote holds, and B4 at IRSS.
WITH_A_TOKEN_REFUSED = {"pin-moved-on": pin_moved_on, "b4": b4}


@pytest.mark.parametrize("make", WITH_A_TOKEN_REFUSED.values(),
                         ids=WITH_A_TOKEN_REFUSED)
def test_with_a_credential_in_use_the_credential_s_skip_is_as_it_was(
        family, holder, offline, tmp_path, make):
    """No misfire with a token in use (#996): IRSS's pin moved on, or B4
    at IRSS, and a remote the token's transport cannot reach, the file
    transport refused. Git's update dies at IRSS (128), and the first
    fetch made again there fails as git's own did, since it is given only
    the transports git's update gives a url (`GIT_PROTOCOL_FROM_USER=0`),
    so it is the credential's skip: the advice and ok, as before, and the
    token is in no output and no file under TMPDIR."""
    env = cloning(offline, tmp_path, family)
    make(holder, env, family, tmp_path)
    without = {**isolated(offline, tmp_path), "SHAPE_LEGS_TOKEN": TOKEN}

    result = bootstrap(holder,
                       traced_by_the_caller(without, offline, tmp_path),
                       "--skip-members")

    assert result.returncode == 0, result.stdout + result.stderr
    assert said_after_the_fetch(result, "SHAPE_LEGS_TOKEN") == [ALONE]
    assert result.stdout.endswith("\nfamily bootstrap ok\n"), result.stdout
    assert TOKEN not in result.stdout + result.stderr
    assert files_holding(offline.temp, TOKEN) == []
    assert git_update(holder, without).returncode == 128


#: The token's two `-c`s, as the wrapper's log masks them, and the trace
#: variables a git given the token runs with: trace2's three targets off,
#: and no other; and for each fetch made again, `GIT_PROTOCOL_FROM_USER`
#: too, as `git submodule` gives every git it starts.
REWRITE_LOGGED = " ".join(
    f"-c url.https://x-access-token:<token>@github.com/.insteadOf={target}"
    for target in ("https://github.com/", "git@github.com:"))
UNTRACED = "GIT_TRACE2=0 GIT_TRACE2_EVENT=0 GIT_TRACE2_PERF=0"
REFETCHED = f"GIT_PROTOCOL_FROM_USER=0 {UNTRACED}"
UPDATE_ARGS = "submodule update --init --recursive"


def logged(log: Path) -> list[str]:
    """The wrapper's log, a line for each command it logged."""
    return log.read_bytes().decode().splitlines()


@POSIX_WRAPPER
def test_with_a_credential_in_use_the_two_fetches_are_made_again_untraced(
        family, holder, offline, tmp_path):
    """#996's fetches, as a wrapper `git` logs the commands bootstrap runs
    itself, B4 at IRSS with a token in use: git's update, then `git fetch
    origin` and `git fetch origin <commit>` in IRSS, as git's update makes
    them there, each with the token's rewrite in its argv, as the update
    was given it, and with `GIT_PROTOCOL_FROM_USER=0`. Every trace the
    person may ask for is on, and each of the three runs with no
    `GIT_TRACE*` variable but trace2's three targets set to 0."""
    env = {**cloning(offline, tmp_path, family), "SHAPE_LEGS_TOKEN": TOKEN}
    commit = b4(holder, env, family, tmp_path)
    log = tmp_path / "git-calls.log"
    traced = traced_by_the_caller(env, offline, tmp_path)

    result = bootstrap(holder, wrapped(traced, tmp_path, log=log),
                       "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert logged(log) == [
        f"{REWRITE_LOGGED} {UPDATE_ARGS} | {UNTRACED}",
        f"{REWRITE_LOGGED} fetch origin | {REFETCHED}",
        f"{REWRITE_LOGGED} fetch origin {commit} | {REFETCHED}"]


@POSIX_WRAPPER
def test_with_no_credential_the_walk_makes_no_fetch_of_its_own(
        family, holder, offline, tmp_path):
    """With no token, B4 is told by git's own trace of its update (#892),
    which the run asks for in a directory of its own under TMPDIR: the
    walk makes no fetch of its own (#996), and B4 is named."""
    env = cloning(offline, tmp_path, family)
    b4(holder, env, family, tmp_path)
    log = tmp_path / "git-calls.log"

    result = bootstrap(holder, wrapped(env, tmp_path, log=log),
                       "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    (update,) = logged(log)
    traced = f"{UPDATE_ARGS} | GIT_TRACE2_EVENT={offline.temp}"
    assert re.fullmatch(re.escape(traced + os.sep + "bootstrap-trace-")
                        + r"\S+", update), update


def pinned_off_branch(holder: Path, env: dict, family,
                      tmp_path: Path) -> Path:
    """IRSS's gitlink and pin moved on to a commit its remote holds at a
    ref that is no branch, `refs/pins/<commit>`: `git fetch origin`, which
    fetches its branches, does not bring it, and `git fetch origin
    <commit>` does, the remote advertising that ref."""
    clone, commit = unpushed(family, env, tmp_path)
    raw(clone, env, "push", "-q", str(family["remotes"] / f"{OTHER}.git"),
        f"{commit}:refs/pins/{commit[:12]}")
    moved_by_hand(holder, env, OTHER, commit)
    return holder


#: `(how IRSS's pin moved on, whether the second fetch is made)`: to a
#: commit on a branch of its remote, which the first fetch made again
#: brings, and to one at a ref that is no branch, which only the second
#: brings.
BROUGHT_BY = {"first-fetch": (pin_moved_on, False),
              "second-fetch": (pinned_off_branch, True)}


@POSIX_WRAPPER
@pytest.mark.parametrize("make, second", BROUGHT_BY.values(), ids=BROUGHT_BY)
def test_with_a_credential_in_use_a_commit_a_fetch_brings_is_untold(
        family, holder, offline, tmp_path, make, second):
    """Where a fetch made again brings the commit, nothing is said (#996):
    git's update dies before it fetches in IRSS, as the wrapper stands in
    for by answering it 128 having fetched nothing, and IRSS's pin moved
    on to a commit its remote holds. Where `git fetch origin` brings it,
    `git fetch origin <commit>` is not made; where only that second fetch
    brings it, it is made, and the commit is no B4. The run reads as
    before, the advice and ok."""
    env = {**cloning(offline, tmp_path, family), "SHAPE_LEGS_TOKEN": TOKEN}
    make(holder, env, family, tmp_path)
    commit = pinned(holder, OTHER)
    log = tmp_path / "git-calls.log"

    result = bootstrap(holder, wrapped(env, tmp_path, "exit 128", log),
                       "--skip-members")

    assert result.returncode == 0, result.stdout + result.stderr
    assert said_after_the_fetch(result, "SHAPE_LEGS_TOKEN") == [ALONE]
    assert logged(log) == [
        f"{REWRITE_LOGGED} {UPDATE_ARGS} | {UNTRACED}",
        f"{REWRITE_LOGGED} fetch origin | {REFETCHED}",
        *([f"{REWRITE_LOGGED} fetch origin {commit} | {REFETCHED}"]
          if second else [])]


# --- a signal git's update went on past (#1056) -----------------------------

#: What (a)'s line says of a signal a git that git's update ran died of,
#: where git's update went on past it and ended with another code, which
#: git's trace tells (#1056), and the failure such a run ends on.
WENT_ON = ("a git that git's update ran died of signal {signum} ({name}, "
           "exit {code}), and git's update went on and ended with exit "
           "{ended}. Git's own words above say which git and where.")
DIED_FAILED = ("family bootstrap FAILED: git's update (a git it ran died of "
               "signal {signum})")

#: A hook here is a POSIX shell script that signals the git running it.
POSIX_HOOK = pytest.mark.skipif(
    os.name == "nt", reason="a hook here sends a POSIX signal to the git "
    "that runs it, which Windows does not give")


def hooked(checkout: Path, env: dict, name: str, line: str) -> None:
    """A `name` hook in the store `checkout` reads, a shell script that
    runs `line`."""
    hooks = raw(checkout, env, "rev-parse", "--git-path",
                "hooks").stdout.decode().strip()
    hook = checkout / hooks / name
    hook.parent.mkdir(exist_ok=True)
    hook.write_bytes(chr(10).join(["#!/bin/sh", line, ""]).encode())
    hook.chmod(0o755)


def checkout_hooked(root: Path, env: dict, line: str,
                    project: str = MEMBER) -> None:
    """`project`'s gitlink and pin, IRRS's unless said, moved by hand to
    its checkout's HEAD~1, which its store holds and a ref reaches, so git's
    update fetches nothing there and runs `git checkout -q` of it; and a
    `post-checkout` hook in that store that runs `line`, after the
    checkout has moved HEAD."""
    member = root / "members" / project
    older = raw(member, env, "rev-parse", "HEAD~1").stdout.decode().strip()
    moved_by_hand(root, env, project, older)
    hooked(member, env, "post-checkout", line)


def killed_checkout(root: Path, env: dict) -> None:
    """IRRS's checkout killed (`checkout_hooked`): the hook sends SIGKILL
    to the `git checkout` that runs it, as the OOM killer would. Git's
    update says `checkout died of signal 9`, cannot check IRRS out (137,
    `git checkout`'s code) and goes on to IRSS."""
    checkout_hooked(root, env, "kill -s KILL $PPID")


def checkout_refused(root: Path, env: dict, family, tmp_path: Path) -> Path:
    """IRSS's checkout moved on by hand to a commit of its own that
    changes `NOTES.md`, then `NOTES.md` edited and not committed, while
    the holder still records the pin: git's checkout of the pin there
    refuses to overwrite the edit, `git checkout`'s own 1, which git's
    update passes and ends with."""
    member = root / OTHER_ROW
    (member / "NOTES.md").write_bytes(b"moved on by hand" + chr(10).encode())
    raw(member, env, "add", "--", "NOTES.md")
    committed(member, env, "NOTES.md moved on by hand")
    (member / "NOTES.md").write_bytes(b"edited" + chr(10).encode())
    return root


def without_the_credential(env: dict, offline, tmp_path: Path) -> dict:
    """The run's environment with the file transport refused, as for want
    of a credential."""
    return isolated(offline, tmp_path)


def with_the_credential(env: dict, offline, tmp_path: Path) -> dict:
    """The run's environment as the state was made in, the file transport
    allowed."""
    return env


@POSIX_HOOK
def test_a_killed_checkout_alone_is_named_as_before(family, holder, offline,
                                                    tmp_path):
    """The control: IRRS's checkout killed and nothing after it failing,
    with the credential. Git's update ends with the signal's 137, which
    its trace gives for IRRS's `git checkout` too, and the run names it as
    #998 does."""
    env = cloning(offline, tmp_path, family)
    killed_checkout(holder, env)

    result = bootstrap(holder, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert said_after_the_fetch(result) == [
        KILLED_LEAD + DIED_OF.format(signum=9, name="SIGKILL", code=137),
        KILLED_FAILED.format(signum=9)]


#: `(what fails in IRSS after IRRS's killed checkout, the run's
#: environment, git's update's exit code)`: IRSS's pin moved on with no
#: credential (128), and IRSS's checkout refused with the credential (1).
AFTER_THE_SIGNAL = {
    "pin-moved-on-no-credential": (pin_moved_on, without_the_credential,
                                   128),
    "checkout-refused-with-the-credential": (checkout_refused,
                                             with_the_credential, 1),
}


@POSIX_HOOK
@pytest.mark.parametrize("then, given, code", AFTER_THE_SIGNAL.values(),
                         ids=AFTER_THE_SIGNAL)
def test_a_killed_checkout_before_a_later_failure_fails_naming_it(
        family, holder, offline, tmp_path, then, given, code):
    """#1056: IRRS's checkout killed, then a failure at IRSS, which git's
    update comes to after it. Git keeps only its last code, so the later
    128 or 1 replaced the signal's 137, and bootstrap said ok with the
    advice. Git's trace gives the `child_exit` of IRRS's `git checkout`,
    137, and the run names that signal now, gives no advice, and fails on
    git's update."""
    env = cloning(offline, tmp_path, family)
    killed_checkout(holder, env)
    then(holder, env, family, tmp_path)

    result = bootstrap(holder, given(env, offline, tmp_path),
                       "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert said_after_the_fetch(result) == [
        KILLED_LEAD + WENT_ON.format(signum=9, name="SIGKILL", code=137,
                                     ended=code),
        DIED_FAILED.format(signum=9)]


def test_p3_before_a_later_failure_fails_naming_the_signal(
        family, holder, offline, tmp_path):
    """#1056, rv996's state: P3 in IRRS, then IRSS's pin moved on, and no
    credential. Git 2.43.0's update crashes in IRRS, goes on, and dies at
    IRSS for want of the credential (128); bootstrap said ok with the
    advice. Git's trace gives the `child_exit` of IRRS's own update, 139,
    and the run names SIGSEGV now, with no advice. Skipped where git does
    not crash in P3: with the credential, its update then exits 139 only
    where it does."""
    env = cloning(offline, tmp_path, family)
    p3(holder, env)
    pin_moved_on(holder, env, family, tmp_path)

    result = bootstrap(holder, isolated(offline, tmp_path), "--skip-members")
    update = git_update(holder, env)

    if update.returncode != 139:
        pytest.skip(f"this git's update exits {update.returncode} here, "
                    "where git 2.43.0's crashes (exit 139)")
    assert result.returncode == 1, result.stdout + result.stderr
    assert said_after_the_fetch(result) == [
        KILLED_LEAD + WENT_ON.format(signum=11, name="SIGSEGV", code=139,
                                     ended=128),
        DIED_FAILED.format(signum=11)]


@POSIX_HOOK
def test_a_signal_and_b4_after_it_are_both_named_the_signal_first(
        family, holder, offline, tmp_path):
    """IRRS's checkout killed, then B4 at IRSS, with the credential: git's
    update died at IRSS (128), and B4 alone was named. Both are named now,
    in git's order, the signal first, each with its failure line."""
    env = cloning(offline, tmp_path, family)
    killed_checkout(holder, env)
    commit = b4(holder, env, family, tmp_path)

    result = bootstrap(holder, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert said_after_the_fetch(result) == [
        KILLED_LEAD + WENT_ON.format(signum=9, name="SIGKILL", code=137,
                                     ended=128),
        LEAD + ABSENT_SAID.format(path=OTHER_ROW, commit=commit,
                                  owner="this holder", tail=BUMP_NAMED),
        DIED_FAILED.format(signum=9) + f", {OTHER_ROW} (git stopped at it)"]


def two_members(root: Path, env: dict) -> None:
    """IRRS's checkout killed by SIGKILL, then IRSS's by SIGTERM."""
    killed_checkout(root, env)
    checkout_hooked(root, env, "kill -s TERM $PPID", OTHER)


def two_legs(root: Path, env: dict) -> None:
    """Every member and leg checked out; then each of IRRS's two legs
    moved on by a commit of its own, so git's update in IRRS checks out
    the commit IRRS records there, `code`'s checkout killed by SIGKILL and
    then `spec`'s by SIGTERM. IRRS's own update ends 143, and git's update
    writes that `child_exit` after both, in a file of its own that comes
    first, since git's update started before IRRS's."""
    assert git_update(root, env).returncode == 0
    for leg, signame in (("code", "KILL"), ("spec", "TERM")):
        checkout = root / ROW / leg
        committed(checkout, env, "Moved on by hand")
        hooked(checkout, env, "post-checkout", f"kill -s {signame} $PPID")


#: Two signals, SIGKILL first, then SIGTERM, whose 143 git's update ends
#: with: at two members' checkouts, and at two legs' in IRRS.
TWO_SIGNALS = {"two-members": two_members, "two-legs": two_legs}


@POSIX_HOOK
@pytest.mark.parametrize("make", TWO_SIGNALS.values(), ids=TWO_SIGNALS)
def test_the_first_signal_is_named(family, holder, offline, tmp_path, make):
    """The first signal git's update met is named, SIGKILL, not SIGTERM,
    whose 143 it ended with and whose `child_exit` git's trace holds last
    in time, and first in its files where two legs' checkouts were
    killed."""
    env = cloning(offline, tmp_path, family)
    make(holder, env)

    result = bootstrap(holder, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert said_after_the_fetch(result) == [
        KILLED_LEAD + WENT_ON.format(signum=9, name="SIGKILL", code=137,
                                     ended=143),
        DIED_FAILED.format(signum=9)]


@POSIX_HOOK
def test_a_hook_s_own_code_is_no_signal(family, holder, offline, tmp_path):
    """No misfire: IRRS's `post-checkout` hook exits 137, whose
    `child_exit` git's trace holds for the hook, and `git checkout` exits
    1 over it; then IRSS's pin moved on, and no credential. Git's update
    dies at IRSS (128), no git it ran died of a signal, and the run reads
    as before, the advice and ok."""
    env = cloning(offline, tmp_path, family)
    checkout_hooked(holder, env, "exit 137")
    pin_moved_on(holder, env, family, tmp_path)

    result = bootstrap(holder, isolated(offline, tmp_path), "--skip-members")

    assert result.returncode == 0, result.stdout + result.stderr
    assert said_after_the_fetch(result) == [ALONE]
    assert result.stdout.endswith("\nfamily bootstrap ok\n"), result.stdout


@POSIX_HOOK
def test_a_git_killed_in_an_update_that_exits_0_is_not_said(
        family, holder, offline, tmp_path):
    """No misfire: IRSS's pin moved on, and a `reference-transaction` hook
    in IRSS's store that kills, once, the git whose ref update it sees
    committed: git's `fetch` there, after it wrote the branch that holds
    the commit. Git's update then finds the commit reached, checks it out
    and exits 0, though its trace holds the fetch's 137, and the run says
    every member and leg was fetched, as before."""
    env = cloning(offline, tmp_path, family)
    pin_moved_on(holder, env, family, tmp_path)
    once = tmp_path / "killed-once"
    hooked(holder / OTHER_ROW, env, "reference-transaction",
           f'if [ "$1" = committed ] && [ ! -e {shlex.quote(str(once))} ]; '
           f"then : > {shlex.quote(str(once))}; kill -s KILL $PPID; fi")

    result = bootstrap(holder, env, "--skip-members")

    assert result.returncode == 0, result.stdout + result.stderr
    assert once.is_file()
    assert "  every member and leg fetched" in result.stdout.splitlines()
    assert result.stdout.endswith("\nfamily bootstrap ok\n"), result.stdout


#: `(what follows IRRS's killed checkout, the run's environment, the
#: run's exit code, what (a) says after git's words)` with a token in use:
#: nothing, where git's update ends with the signal's 137, which is named
#: as before; and IRSS's pin moved on, the token's transport refused,
#: where it ends 128 and was not traced, so the signal is not told: the
#: advice and ok.
WITH_A_TOKEN_KILLED = {
    "alone": (in_place, with_the_credential, 1, [
        KILLED_LEAD + DIED_OF.format(signum=9, name="SIGKILL", code=137),
        KILLED_FAILED.format(signum=9)]),
    "then-pin-moved-on": (pin_moved_on, without_the_credential, 0, [ALONE]),
}


@POSIX_HOOK
@pytest.mark.parametrize("then, given, code, said",
                         WITH_A_TOKEN_KILLED.values(), ids=WITH_A_TOKEN_KILLED)
def test_with_a_credential_in_use_a_signal_is_told_only_from_git_s_code(
        family, holder, offline, tmp_path, then, given, code, said):
    """#1056's limit: with a token in use git's update is not traced
    (#996), and its own exit code is all that tells a signal. IRRS's
    checkout killed is named where git's update ends with its 137; where
    IRSS's failure after it ends the update 128, it is the credential's
    skip, as before, the advice and ok. The token is in no output and no
    file under TMPDIR, with every trace the person may ask for on."""
    env = cloning(offline, tmp_path, family)
    killed_checkout(holder, env)
    then(holder, env, family, tmp_path)
    token = {**given(env, offline, tmp_path), "SHAPE_LEGS_TOKEN": TOKEN}

    result = bootstrap(holder, traced_by_the_caller(token, offline, tmp_path),
                       "--skip-members")

    assert result.returncode == code, result.stdout + result.stderr
    assert said_after_the_fetch(result, "SHAPE_LEGS_TOKEN") == said
    assert TOKEN not in result.stdout + result.stderr
    assert files_holding(offline.temp, TOKEN) == []
