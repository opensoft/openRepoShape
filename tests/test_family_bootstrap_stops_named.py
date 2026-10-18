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
commit no ref of the member's store reaches after the update, where git's
own trace of the run says its fetch there exited 0. The store alone tells
nothing: a member checked out before the run whose pin moved to a commit
its remote holds, fetched with no credential, is as short of it, which
was measured, and that is still the credential's skip, a control here,
beside a member checked out whole whose own nested gitlink has its url.

WHERE NEITHER TELLS, the run reads as before, the advice and ok, and a row
pins each: a member's own `.gitmodules` git cannot read; a stray git never
came to, since a clone that failed ended its update 1; and B4 with a
credential in use, which is never traced. A member git could not check out
is passed as git passes it, and a stop past it is named. B5 a level down,
in a leg's own index, is named up to the holder.

THE SAME FAMILY, OFFLINE RULES AND HELPERS as
`tests/test_family_holder_remedies_compose.py` (#879). A missing credential
is git's refusal of the file transport to the fixture's local remotes, as
in `tests/test_family_holder_bootstrap_texts.py` (#839). A commit a test
makes in a member is pushed to a branch of the member's remote named for
it, so a plain clone fetches it, and the remote's `main` is not moved.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import rmtree, run_script
from repo_shape import PYTHON
from test_family import FAMILY, SPARE, family, validate  # noqa: F401
from test_family_add_refusals import holder, offline  # noqa: F401
from test_family_bootstrap_gate_order import bootstrap, cloned, type_line
from test_family_dry_run import isolated
from test_family_head_lost_gitmodules import (
    assert_passes_in_every_mode, commit_all, pinned,
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
            if line.startswith((*OURS, LEAD))]
    assert ours, result.stderr
    assert re.fullmatch(r"  FETCH INCOMPLETE \(git exit \d+\) using "
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


def unpushed(family, env: dict, tmp_path: Path) -> tuple[Path, str]:
    """A clone of OTHER's remote of the test's own and an empty commit made
    on its `main` there and never pushed: no store the holder reaches holds
    it, and its tree is the pinned one's. Returns both."""
    clone = tmp_path / "unpushed"
    raw(tmp_path, env, "clone", "-q", "--",
        str(family["remotes"] / f"{OTHER}.git"), str(clone))
    return clone, committed(clone, env, "Made and never pushed")


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


def test_a_member_git_could_not_check_out_is_passed_as_git_passes_it(
        family, holder, offline, tmp_path):
    """IRRS's checkout moved by hand to a commit of its own that changes
    `NOTES.md` and records B5's gitlink, with `NOTES.md` then edited and
    not committed, while the holder still records the pin; and B4 at IRSS.
    Git's checkout of the pin in IRRS refuses to overwrite the edit, which
    its update passes (`git checkout`'s exit 1), never entering IRRS, and
    it dies at IRSS (exit 128). The line names IRSS, not the gitlink in
    IRRS's index, which is not the pin's."""
    env = cloning(offline, tmp_path, family)
    member = holder / ROW
    (member / "NOTES.md").write_bytes(b"moved on by hand" + chr(10).encode())
    raw(member, env, "add", "--", "NOTES.md")
    stray_in(member, family, env)
    (member / "NOTES.md").write_bytes(b"edited" + chr(10).encode())
    commit = b4(holder, env, family, tmp_path)

    result = bootstrap(holder, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert said_after_the_fetch(result) == [
        LEAD + ABSENT_SAID.format(path=OTHER_ROW, commit=commit,
                                  owner="this holder", tail=BUMP_NAMED),
        STOP_FAILED.format(path=OTHER_ROW)]
    assert git_update(holder, env).returncode == 128


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


def test_with_a_credential_in_use_b4_is_read_as_before(family, holder,
                                                       offline, tmp_path):
    """What it cannot tell: a run with a credential in use is not traced,
    since trace2 writes a command's arguments and the credential is one, so
    B4 is the advice and ok, as before."""
    env = {**cloning(offline, tmp_path, family), "SHAPE_LEGS_TOKEN": TOKEN}
    b4(holder, env, family, tmp_path)

    result = bootstrap(holder, env, "--skip-members")

    assert result.returncode == 0, result.stdout + result.stderr
    assert said_after_the_fetch(result, "SHAPE_LEGS_TOKEN") == [ALONE]
    assert TOKEN not in result.stdout + result.stderr
