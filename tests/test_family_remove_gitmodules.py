# SPDX-License-Identifier: Apache-2.0
"""`family.py remove` and `add` commit only their own change to
`.gitmodules` (#407).

THE ISSUE. With the holder's work-tree `.gitmodules` deleted and the
deletion not committed, `remove` exited 0 and its commit deleted
`.gitmodules` from HEAD, and every other member's section with it. `git rm`
edits only a `.gitmodules` the work tree has, and the commit stages what the
work tree has. The holder it ran in still looked whole: its git config kept
the other registrations and `validate-family.py` passed. Once pushed, a
recursive clone exited 0 with each remaining member's directory empty, and the
clone's own gate refused `member-uninitialized`. `remove --dry-run` said no
section was removed and printed no registration, though `deinit` dropped one
(the review's N9).

NOW. `remove` refuses, before any git command that writes and under
`--dry-run` in the same words, a `.gitmodules` the index or HEAD holds and
the work tree lacks (`gitmodules-missing`). `remove` and `add` both refuse a
work tree's copy that is not the index's: modified (git's own answer, so a
copy that differs only in line endings counts), unmerged, or one whose
deletion is staged (`gitmodules-unstaged`). `add` committed such a change
beside the member's section. Each remedy is typed here as printed, and the
same command then runs. A change somebody STAGED still goes into the commit:
the remediations of #300 and #360 rely on it. `add` leaves a missing file to
`git submodule add`, which refuses it at the mount, as before.

THE SAME FAMILY, RULES AND OFFLINE ENVIRONMENT as `test_family_dry_run.py`.
Every file this module writes is written as bytes and every unmerged entry
is built in the index (`update-index --index-info`), so no test depends on
how a checkout writes a file. The one push goes to a branch of this
module's own copy of the family's remote, never to `main`, and the clone
after it reads holder and members through git (`clone_just_pushed`).
"""

from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path

import pytest

from conftest import clone_just_pushed, run_script
#: The family fixture, its names, the offline environment and the holder's
#: bytes, imported from the modules that own them rather than rebuilt.
from test_family import (  # noqa: F401
    FAMILY, NAME, ORG, SPARE, family, validate,
)
from test_family_add_refusals import holder, offline, refusal  # noqa: F401
from test_family_dry_run import isolated, objects, work_tree
from test_family_member_path import MEMBER, OTHER, raw

GITMODULES = ".gitmodules"
PATH = f"members/{MEMBER}"

#: What `gitmodules-missing` says, around where the file is still held.
MISSING = (
    "REFUSED gitmodules-missing: .gitmodules is not in the work tree, though "
    "{held}. `git rm` edits only a .gitmodules the work tree has, and "
    "`remove` commits .gitmodules as the work tree has it: committed as it "
    "stands, .gitmodules would leave HEAD, and every other member's section "
    "with it, so that a recursive clone of the holder leaves each of them "
    "empty. No git command that writes was run and nothing was written.")

#: What `gitmodules-unstaged` says, around the state and the verb.
UNSTAGED = (
    "REFUSED gitmodules-unstaged: {said}. `{verb}` edits the work tree's copy "
    "and commits .gitmodules with its own change in it, so the work tree's "
    "copy must be the one the index holds: a change nobody has staged is not "
    "this command's to commit. No git command that writes was run and "
    "nothing was written.")

MODIFIED = ("the work tree's .gitmodules is not the copy the index holds: git "
            "lists it as modified, a change nobody has staged")
KEEP_OR_DROP = (
    "Remediation: which change to keep is a person's to say. To commit the "
    "work tree's copy, changes and all, stage it first, `git add "
    ".gitmodules`; to drop its changes, put back the index's copy, `git "
    "checkout -- .gitmodules`. Then run the same command again.")


# --- the states --------------------------------------------------------------

def index_blob(root: Path, env: dict) -> str:
    return raw(root, env, "rev-parse", f":{GITMODULES}").stdout.decode(
        "ascii").strip()


def deleted(root: Path, env: dict) -> None:
    """THE ISSUE'S STATE: the work tree's copy deleted, not committed."""
    (root / GITMODULES).unlink()


def deletion_staged(root: Path, env: dict) -> None:
    """`git rm .gitmodules`: gone from the work tree and the index."""
    raw(root, env, "rm", "-q", "--", GITMODULES)


def unmerged(root: Path, env: dict) -> None:
    """`.gitmodules` UNMERGED in the index, stages 1, 2 and 3 each the
    index's own copy, with no merge in progress: what a conflicted `git
    stash pop` leaves. The work tree's copy is left as it was."""
    blob = index_blob(root, env)
    records = (f"0 {'0' * 40}\t{GITMODULES}\n" + "".join(
        f"100644 {blob} {stage}\t{GITMODULES}\n" for stage in (1, 2, 3)))
    subprocess.run(["git", "update-index", "--index-info"], cwd=str(root),
                   input=records.encode("utf-8"), capture_output=True,
                   check=True)


def unmerged_and_deleted(root: Path, env: dict) -> None:
    unmerged(root, env)
    deleted(root, env)


def edited(root: Path, env: dict) -> None:
    """A hand edit nobody staged: OTHER's url moved in the work tree."""
    data = (root / GITMODULES).read_bytes()
    assert data.count(f"{OTHER}.git".encode("utf-8")) == 1, "fixture drift"
    (root / GITMODULES).write_bytes(data.replace(
        f"{OTHER}.git".encode("utf-8"), f"{OTHER}-moved.git".encode("utf-8")))


def crlf(root: Path, env: dict) -> None:
    """The index's copy with CRLF line endings: git lists it as modified
    (its size is not the one the index recorded), and `git rm` refused it."""
    data = raw(root, env, "show", f":{GITMODULES}").stdout
    (root / GITMODULES).write_bytes(data.replace(b"\n", b"\r\n"))


def index_lacks(root: Path, env: dict) -> None:
    """`git rm --cached .gitmodules`: its deletion staged, the file kept."""
    raw(root, env, "rm", "-q", "--cached", "--", GITMODULES)


# --- what a refusal leaves, and what a remedy does ---------------------------

def held(root: Path, env: dict) -> dict:
    """Everything a refusal leaves exactly as it was, as bytes, with
    `.gitmodules` None where the work tree has none: HEAD, `ls-files -s -z`,
    `status --porcelain=v1 -z`, `family.yaml`, `.gitmodules`, the holder's
    `.git/config` (its registrations), every byte of the work tree and the
    holder's own objects."""
    gitmodules = root / GITMODULES
    return {
        "HEAD": raw(root, env, "rev-parse", "HEAD").stdout,
        "index": raw(root, env, "ls-files", "-s", "-z").stdout,
        "status": raw(root, env, "status", "--porcelain=v1", "-z").stdout,
        "family.yaml": (root / "family.yaml").read_bytes(),
        GITMODULES: (gitmodules.read_bytes() if gitmodules.exists()
                     else None),
        ".git/config": (root / ".git" / "config").read_bytes(),
        "work tree": work_tree(root),
        "objects": objects(root),
    }


def assert_held(root: Path, env: dict, before: dict) -> None:
    """`root` is as `before` recorded it, key by key, so a failure names
    the first fact that moved."""
    now = held(root, env)
    for key, value in before.items():
        assert now[key] == value, f"{key} changed"


def verb_args(verb: str, root: Path, family) -> list[str]:
    """`remove` takes out MEMBER; `add` mounts SPARE from the fixture's
    local remotes."""
    if verb == "remove":
        return ["remove", "--family-root", str(root), "--member", MEMBER]
    return ["add", "--family-root", str(root), "--member", f"{ORG}/{SPARE}",
            "--local-remote-dir", str(family["remotes"])]


def refused_alike(root: Path, env: dict, args: list[str]) -> tuple[str, str]:
    """The real run and its dry run refuse in the same words, exit 2, with
    nothing on stdout and the holder byte for byte as it was after each.
    Returns `(the REFUSED line, the remediation)`."""
    before = held(root, env)
    real = run_script(FAMILY, *args, env=env)
    assert_held(root, env, before)
    dry = run_script(FAMILY, *args, "--dry-run", env=env)
    assert_held(root, env, before)
    assert real.returncode == 2, real.stdout + real.stderr
    assert dry.returncode == 2, dry.stdout + dry.stderr
    assert real.stdout == ""
    assert dry.stdout == ""
    assert dry.stderr == real.stderr
    return refusal(real.stderr)


def typed_as_printed(root: Path, remediation: str,
                     which: slice = slice(None)) -> list[str]:
    """Run the `git` commands the remediation prints, the `which` of them,
    exactly as printed: split as a POSIX shell splits them, no shell."""
    commands = re.findall(r"`(git [^`]*)`", remediation)[which]
    for command in commands:
        subprocess.run(shlex.split(command), cwd=str(root), check=True,
                       capture_output=True)
    return commands


def head_paths(root: Path, env: dict) -> list[str]:
    """Every `path` HEAD's `.gitmodules` gives, in file order, as git
    lists them."""
    listed = raw(root, env, "config", "--blob", f"HEAD:{GITMODULES}",
                 "--list").stdout.decode("utf-8").splitlines()
    return [line.partition("=")[2] for line in listed
            if line.partition("=")[0].rpartition(".")[2] == "path"]


def ran(root: Path, env: dict, args: list[str]) -> None:
    """The same command, run again once the remedy is typed: exit 0."""
    result = run_script(FAMILY, *args, env=env)
    assert result.returncode == 0, result.stdout + result.stderr


# --- remove: a .gitmodules the work tree lacks -------------------------------

#: `(set-up, where the file is still held, the remediation)`.
LACKED = {
    "deleted": (
        deleted, "the index and HEAD each hold one",
        "Remediation: put back the index's copy, `git checkout -- "
        ".gitmodules`, and run the same command again."),
    "deletion staged": (
        deletion_staged, "HEAD holds one and its deletion is staged",
        "Remediation: put back HEAD's copy, in the index and the work tree, "
        "`git checkout HEAD -- .gitmodules`, and run the same command "
        "again."),
    "unmerged and deleted": (
        unmerged_and_deleted,
        "the index holds one unmerged and HEAD holds one",
        "Remediation: write the conflicted file back, `git checkout --merge "
        "-- .gitmodules`, resolve it and stage the result, `git add "
        ".gitmodules`, and run the same command again."),
}


@pytest.mark.parametrize("set_up, where, remediation", LACKED.values(),
                         ids=LACKED)
def test_remove_refuses_a_gitmodules_the_work_tree_lacks(
        family, holder, offline, tmp_path, set_up, where, remediation):
    """`gitmodules-missing`, by `remove` and its dry run alike, naming
    where the file is still held, with nothing written: HEAD, the index,
    `family.yaml` and the registrations `deinit` would drop are as they
    were. Typed as printed, the remedy puts the file back, and the same
    `remove` then takes out MEMBER's section alone and passes the gate."""
    env = isolated(offline, tmp_path)
    set_up(holder, env)
    args = verb_args("remove", holder, family)

    said, remedy = refused_alike(holder, env, args)

    assert said == MISSING.format(held=where)
    assert remedy == remediation
    typed_as_printed(holder, remedy)
    ran(holder, env, args)
    assert head_paths(holder, env) == [f"members/{OTHER}"]
    assert validate(holder).returncode == 0


def test_the_restored_holder_pushes_a_commit_a_recursive_clone_populates(
        family, holder, offline, tmp_path):
    """THE ISSUE'S CLONE. After the restore the refusal prints, `remove`
    commits MEMBER's removal and nothing else. Pushed, a fresh `clone
    --recurse-submodules` populates OTHER, holds no MEMBER, and the clone's
    own `validate-family.py` passes, where the commit the issue describes
    left OTHER empty and that gate refusing `member-uninitialized`."""
    env = isolated(offline, tmp_path)
    deleted(holder, env)
    args = verb_args("remove", holder, family)
    typed_as_printed(holder, refused_alike(holder, env, args)[1])
    ran(holder, env, args)
    remote = family["remotes"] / f"{NAME}.git"
    branch = "fam407/restored-then-removed"
    raw(holder, env, "push", "-q", str(remote), f"HEAD:refs/heads/{branch}")

    clone = tmp_path / "clone"
    cloned = clone_just_pushed(remote, clone, branch)

    assert cloned.returncode == 0, cloned.stdout + cloned.stderr
    assert (clone / "members" / OTHER / "project.yaml").is_file()
    assert not (clone / PATH).exists()
    gate = validate(clone)
    assert gate.returncode == 0, gate.stdout + gate.stderr


# --- remove and add: a work tree's copy that is not the index's --------------

#: `(set-up, what the refusal says of it, its remediation, which printed
#: command the test types, the path HEAD's file gives OTHER's url ending)`.
NOT_STAGED = {
    "edited": (edited, MODIFIED, KEEP_OR_DROP, slice(0, 1),
               f"{OTHER}-moved.git"),
    "crlf": (crlf, MODIFIED, KEEP_OR_DROP, slice(1, 2), f"{OTHER}.git"),
    "unmerged": (
        unmerged, ".gitmodules is unmerged in the index",
        "Remediation: resolve the conflict in it and stage the result, `git "
        "add .gitmodules`, then run the same command again.", slice(None),
        f"{OTHER}.git"),
    "deletion staged, file kept": (
        index_lacks,
        "the work tree has a .gitmodules and the index does not: its "
        "deletion is staged",
        "Remediation: which copy to keep is a person's to say. To keep the "
        "work tree's, stage it, `git add .gitmodules`; to put back HEAD's, in "
        "the index and the work tree, `git checkout HEAD -- .gitmodules`. "
        "Then run the same command again.", slice(1, 2), f"{OTHER}.git"),
}


@pytest.mark.parametrize("verb", ["remove", "add"])
@pytest.mark.parametrize("set_up, said, remediation, typed, url",
                         NOT_STAGED.values(), ids=NOT_STAGED)
def test_a_work_tree_copy_that_is_not_the_indexs_is_refused(
        family, holder, offline, tmp_path, verb, set_up, said, remediation,
        typed, url):
    """`gitmodules-unstaged`, by the verb and its dry run alike, before
    `add` reads the member, with nothing written. Typed as printed, the
    remedy the test picks makes the work tree's copy the index's, and the
    same command then commits: a change the person STAGED goes in with it
    (`edited`, whose `git add` keeps OTHER's moved url), and one they put
    back does not."""
    env = isolated(offline, tmp_path)
    set_up(holder, env)
    args = verb_args(verb, holder, family)

    refused = refused_alike(holder, env, args)

    assert refused == (UNSTAGED.format(said=said, verb=verb), remediation)
    offline.assert_left_nothing()
    typed_as_printed(holder, remediation, typed)
    ran(holder, env, args)
    assert raw(holder, env, "config", "--blob", f"HEAD:{GITMODULES}",
               f"submodule.members/{OTHER}.url").stdout.decode(
                   "utf-8").strip().endswith(url)


def test_add_still_leaves_a_missing_gitmodules_to_git(family, holder,
                                                      offline, tmp_path):
    """`add` asks nothing of a `.gitmodules` the work tree lacks: `git
    submodule add` refuses to write one while the index or HEAD holds it,
    before it writes anything, and `add --dry-run` says so in a note and
    exits 0, as it did before #407."""
    env = isolated(offline, tmp_path)
    deleted(holder, env)

    dry = run_script(FAMILY, *verb_args("add", holder, family), "--dry-run",
                     env=env)

    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert ("\nnote         .gitmodules is in the index and HEAD but not in "
            "the work tree, where `git submodule add` refuses") in dry.stdout


def test_a_holder_whose_head_has_no_gitmodules_is_not_asked(
        family, holder, offline, tmp_path):
    """Where neither the index nor HEAD holds a `.gitmodules` there is no
    copy to compare the work tree's with, and nothing is refused for it:
    in a holder whose HEAD already lost the file, `remove --dry-run` says
    no section is removed, and names no registration, since `deinit` finds
    no name in any copy either."""
    env = isolated(offline, tmp_path)
    deletion_staged(holder, env)
    raw(holder, env, "commit", "-q", "-m", "The commit #407 describes")

    dry = run_script(FAMILY, *verb_args("remove", holder, family),
                     "--dry-run", env=env)

    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert (f"gitmodules   none: git reads no section of .gitmodules in the "
            f"work tree as giving {PATH}, so none is removed\n") in dry.stdout
    assert "\nregistration " not in dry.stdout
