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
`--dry-run` in the same words, a `.gitmodules` the index or HEAD holds and the
work tree lacks (`gitmodules-missing`), and prints the restore git takes in
that state, an unmerged one's included. `remove` and `add` both refuse a work
tree's copy that is not the index's (`gitmodules-unstaged`): modified (git's
own answer, so a copy that differs only in line endings counts, and the
refusal says the difference may be that alone), unmerged, one whose deletion
is staged, an edit the index's assume-unchanged mark hides, and an untracked
file where neither the index nor HEAD holds one. Both refuse a file a sparse
checkout leaves out (`gitmodules-sparse`), and `add` any the index marks
skip-worktree, which `git submodule add` cannot stage. A clean copy behind a
mark is not refused: `remove` commits one marked skip-worktree, and both verbs
one marked assume-unchanged, as before #407 (the re-review's nits 1 and 2).
`add` committed such a change beside the member's section. Each remedy is
typed here as printed, and the same command then runs. A change somebody
STAGED still goes into the commit: the remediations of #300 and #360 rely on
it, and so do `member-name-taken`'s and `gitmodules-unreadable`'s, which now
say to stage the file they have the person mend (the review's S1). `add`
leaves a missing file to `git submodule add`, which refuses it at the mount,
as before.

THE SAME FAMILY, RULES AND OFFLINE ENVIRONMENT as `test_family_dry_run.py`,
and the same reading of what a refusal leaves (`state`). Every file this
module writes is written as bytes, every unmerged entry is built in the index
(`update-index --index-info`), and every git command runs under the module's
own environment (`raw`), so no test depends on how a checkout writes a file
or on the configuration of whoever runs the suite. The one push goes to a
branch of this module's own copy of the family's remote, never to `main`, and
the clone after it reads holder and members through git (`clone_just_pushed`).
"""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path

import pytest

from conftest import clone_just_pushed, run_script
#: The family fixture, its names, the offline environment and the holder's
#: bytes, imported from the modules that own them rather than rebuilt.
from test_family import (  # noqa: F401
    FAMILY, NAME, ORG, SPARE, family, validate,
)
from test_family_add_excludes import RULES, empty_holder  # noqa: F401
from test_family_add_refusals import holder, offline, refusal  # noqa: F401
from test_family_dry_run import REMOVE_ORDER, assert_as_it_was, isolated, state
from test_family_member_path import MEMBER, OTHER, raw
from test_scaffold_ignored_shape_files import excluding

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
HELD_UNMERGED = "the index holds one unmerged and HEAD holds one"

#: What `gitmodules-unstaged` says, around the state and the verb.
UNSTAGED = (
    "REFUSED gitmodules-unstaged: {said}. `{verb}` edits the work tree's copy "
    "and commits .gitmodules with its own change in it, so the work tree's "
    "copy must be the one the index holds: a change nobody has staged is not "
    "this command's to commit. No git command that writes was run and "
    "nothing was written.")

MODIFIED = ("the work tree's .gitmodules is not the copy the index holds: git "
            "lists it as modified, a change nobody has staged")
#: What `gitmodules-unstaged` adds where `git add` would stage the index's
#: own blob from the work tree's copy (the review's N1).
LINE_ENDINGS = (", though `git add` would stage the index's own content "
                "from it: the difference may be its line endings alone")
ASSUMED = ("the work tree's .gitmodules is not the copy the index holds, a "
           "change nobody has staged, and git does not list it as modified: "
           "the index marks it assume-unchanged, so git does not compare it")
UNTRACKED = ("the work tree has a .gitmodules that neither the index nor HEAD "
             "holds: it is untracked, and nobody has staged it")


def keep_or_drop(stage: str) -> str:
    """The remediation of a copy that differs from the index's, around how
    the work tree's copy is staged."""
    return ("Remediation: which change to keep is a person's to say. To "
            f"commit the work tree's copy, changes and all, {stage}; to drop "
            "its changes, put back the index's copy, `git checkout -- "
            ".gitmodules`. Then run the same command again.")


KEEP_OR_DROP = keep_or_drop("stage it first, `git add .gitmodules`")
KEEP_OR_DROP_ASSUMED = keep_or_drop(
    "take the mark off and stage it first, `git update-index "
    "--no-assume-unchanged -- .gitmodules` and `git add .gitmodules`")
KEEP_OR_LEAVE_OUT = (
    "Remediation: whether it belongs in the holder is a person's to say. To "
    "keep it, stage it, `git add -f .gitmodules` (`-f`, since an operator's "
    "excludes may match it), and commit it on its own first if the command's "
    "commit should carry only its own change; to leave it out, move it out of "
    "the holder. Then run the same command again.")

#: What `gitmodules-sparse` says, around the verb, and its remediation.
SPARSE = (
    "REFUSED gitmodules-sparse: the index marks .gitmodules skip-worktree, as "
    "a sparse checkout that leaves it out does, so git neither compares the "
    "work tree's copy with the index's nor stages it, and `{verb}` edits "
    ".gitmodules and commits it as the work tree has it. No git command that "
    "writes was run and nothing was written.")
SPARSE_REMEDY = (
    "Remediation: bring it back into the work tree as git compares and "
    "stages it, `git sparse-checkout disable`, which brings back every path "
    "the sparse checkout leaves out and leaves a copy already there as it "
    "is, and run the same command again.")


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


def unmerged_at(*stages: int):
    """A set-up that leaves `.gitmodules` UNMERGED in the index at `stages`,
    each the index's own copy, with no merge in progress: 1, 2 and 3 are
    what a conflicted `git stash pop` leaves; 1 and 2 a modify/delete
    conflict whose other side deleted the file, 1 and 3 one whose own side
    did, and 1 alone both sides deleting it. The work tree's copy is left as
    it was."""
    def set_up(root: Path, env: dict) -> None:
        blob = index_blob(root, env)
        records = (f"0 {'0' * 40}\t{GITMODULES}\n" + "".join(
            f"100644 {blob} {stage}\t{GITMODULES}\n" for stage in stages))
        raw(root, env, "update-index", "--index-info",
            stdin=records.encode("utf-8"))
    return set_up


unmerged = unmerged_at(1, 2, 3)


def and_deleted(set_up):
    """`set_up`, then the work tree's copy deleted."""
    def both(root: Path, env: dict) -> None:
        set_up(root, env)
        deleted(root, env)
    return both


def edited(root: Path, env: dict) -> None:
    """A hand edit nobody staged: OTHER's url moved in the work tree."""
    data = (root / GITMODULES).read_bytes()
    assert data.count(f"{OTHER}.git".encode("utf-8")) == 1, "fixture drift"
    (root / GITMODULES).write_bytes(data.replace(
        f"{OTHER}.git".encode("utf-8"), f"{OTHER}-moved.git".encode("utf-8")))


def crlf(root: Path, env: dict) -> None:
    """The index's copy with CRLF line endings: git lists it as modified
    (its size is not the one the index recorded), and `git rm` refused it.
    The holder's attributes make `git add` stage the index's own blob from
    it."""
    data = raw(root, env, "show", f":{GITMODULES}").stdout
    (root / GITMODULES).write_bytes(data.replace(b"\n", b"\r\n"))


def linked(root: Path, env: dict) -> None:
    """A symbolic link to a file of the index's own bytes, outside the
    holder: git lists it as modified, and `git add` would stage the link,
    not those bytes, so nothing is said of line endings. Not on Windows,
    where git checks a link out as a plain file."""
    if os.name == "nt":
        pytest.skip("git checks a symbolic link out as a plain file here")
    copy = root.parent / "gitmodules-bytes"
    copy.write_bytes(raw(root, env, "show", f":{GITMODULES}").stdout)
    (root / GITMODULES).unlink()
    os.symlink(copy, root / GITMODULES)


def assumed_and_edited(root: Path, env: dict) -> None:
    """CODEX'S SECOND STATE: the index marks `.gitmodules` assume-unchanged,
    then OTHER's url is moved by hand. `git ls-files -m` lists nothing, and
    both verbs committed the edit."""
    raw(root, env, "update-index", "--assume-unchanged", "--", GITMODULES)
    edited(root, env)


def index_lacks(root: Path, env: dict) -> None:
    """`git rm --cached .gitmodules`: its deletion staged, the file kept."""
    raw(root, env, "rm", "-q", "--cached", "--", GITMODULES)


def left_out(root: Path, env: dict) -> None:
    """A sparse checkout that leaves `.gitmodules` out, made by git's own
    `sparse-checkout set` (`--no-cone`: a cone keeps every top-level file):
    the index marks it skip-worktree and the work tree has none. `git
    checkout -- .gitmodules` matches nothing there."""
    raw(root, env, "sparse-checkout", "set", "--no-cone", "/*",
        f"!/{GITMODULES}")
    assert not (root / GITMODULES).exists(), "premise: left out"


def hidden_by_skip_worktree(root: Path, env: dict) -> None:
    """The index marks `.gitmodules` skip-worktree by hand, then OTHER's url
    is moved: git lists nothing as modified, `remove` committed the edit and
    `add` failed at its mount."""
    raw(root, env, "update-index", "--skip-worktree", "--", GITMODULES)
    edited(root, env)


def marked(tag: bytes, *flags: str):
    """A set-up that marks `.gitmodules` in the index with `flags`, one `git
    update-index` call each (one call applies only its first flag), and
    leaves the file as the index has it. `tag` is the letter `git ls-files
    -v` must then print, the premise: `S` for skip-worktree, `h` for
    assume-unchanged (which `core.ignoreStat` sets on every file git writes),
    `s` for both."""
    def set_up(root: Path, env: dict) -> None:
        for flag in flags:
            raw(root, env, "update-index", flag, "--", GITMODULES)
        listed = raw(root, env, "ls-files", "-v", "--", GITMODULES).stdout
        assert listed.startswith(tag + b" "), f"premise: {listed!r}"
    return set_up


# --- what a refusal leaves, and what a remedy does ---------------------------

def verb_args(verb: str, root: Path, family) -> list[str]:
    """`remove` takes out MEMBER; `add` mounts SPARE from the fixture's
    local remotes."""
    if verb == "remove":
        return ["remove", "--family-root", str(root), "--member", MEMBER]
    return ["add", "--family-root", str(root), "--member", f"{ORG}/{SPARE}",
            "--local-remote-dir", str(family["remotes"])]


def refused_alike(root: Path, env: dict, args: list[str]) -> tuple[str, str]:
    """The real run and its dry run refuse in the same words, exit 2, with
    nothing on stdout and the holder byte for byte as it was after each, as
    `test_family_dry_run.state` reads it. Returns `(the REFUSED line, the
    remediation)`."""
    before = state(root, env)
    real = run_script(FAMILY, *args, env=env)
    assert_as_it_was(root, env, before, REMOVE_ORDER)
    dry = run_script(FAMILY, *args, "--dry-run", env=env)
    assert_as_it_was(root, env, before, REMOVE_ORDER)
    assert real.returncode == 2, real.stdout + real.stderr
    assert dry.returncode == 2, dry.stdout + dry.stderr
    assert real.stdout == ""
    assert dry.stdout == ""
    assert dry.stderr == real.stderr
    return refusal(real.stderr)


def typed_as_printed(root: Path, env: dict, remediation: str,
                     which: slice = slice(None)) -> list[str]:
    """Run the `git` commands the remediation prints, the `which` of them,
    exactly as printed: split as a POSIX shell splits them, no shell, under
    the module's environment (`raw`)."""
    commands = re.findall(r"`(git [^`]*)`", remediation)[which]
    for command in commands:
        raw(root, env, *shlex.split(command)[1:])
    return commands


def refused_then_typed(root: Path, env: dict, args: list[str],
                       expected: tuple[str, str],
                       which: slice = slice(None)) -> None:
    """Refused alike (`refused_alike`) in exactly the `expected` words, and
    then the remedy's `which` git commands typed as printed."""
    refused = refused_alike(root, env, args)
    assert refused == expected
    typed_as_printed(root, env, refused[1], which)


def head_paths(root: Path, env: dict) -> list[str]:
    """Every `path` HEAD's `.gitmodules` gives, in file order, as git
    lists them."""
    listed = raw(root, env, "config", "--blob", f"HEAD:{GITMODULES}",
                 "--list").stdout.decode("utf-8").splitlines()
    return [line.partition("=")[2] for line in listed
            if line.partition("=")[0].rpartition(".")[2] == "path"]


def committed_url(root: Path, env: dict) -> str:
    """The url HEAD's `.gitmodules` gives OTHER."""
    return raw(root, env, "config", "--blob", f"HEAD:{GITMODULES}",
               f"submodule.members/{OTHER}.url").stdout.decode(
                   "utf-8").strip()


def committed_paths(root: Path, env: dict) -> list[str]:
    """The paths HEAD's commit changes, as `git diff-tree` lists them."""
    return raw(root, env, "diff-tree", "--no-commit-id", "--name-only", "-r",
               "HEAD").stdout.decode("utf-8").split()


def ran(root: Path, env: dict, args: list[str]) -> None:
    """The same command, run again once the remedy is typed: exit 0."""
    result = run_script(FAMILY, *args, env=env)
    assert result.returncode == 0, result.stdout + result.stderr


# --- remove: a .gitmodules the work tree lacks -------------------------------

def side_restored(restore: str) -> str:
    """The remediation of an unmerged `.gitmodules` the work tree lacks
    whose restore takes one side's copy, or the copy both started from."""
    return (f"Remediation: {restore}, stage it, `git add .gitmodules`, and run "
            "the same command again.")


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
        and_deleted(unmerged), HELD_UNMERGED,
        "Remediation: write the conflicted file back, `git checkout --merge "
        "-- .gitmodules`, resolve it and stage the result, `git add "
        ".gitmodules`, and run the same command again."),
    "our side only, deleted": (
        and_deleted(unmerged_at(1, 2)), HELD_UNMERGED, side_restored(
            "the other side deleted it, so put back this side's copy, `git "
            "checkout --ours -- .gitmodules`")),
    "their side only, deleted": (
        and_deleted(unmerged_at(1, 3)), HELD_UNMERGED, side_restored(
            "this side deleted it, so put back the other side's copy, `git "
            "checkout --theirs -- .gitmodules`")),
    "neither side, deleted": (
        and_deleted(unmerged_at(1)), HELD_UNMERGED, side_restored(
            "both sides deleted it, so put back the copy they started from, "
            "`git checkout-index -f --stage=1 -- .gitmodules`")),
}


@pytest.mark.parametrize("set_up, where, remediation", LACKED.values(),
                         ids=LACKED)
def test_remove_refuses_a_gitmodules_the_work_tree_lacks(
        family, holder, offline, tmp_path, set_up, where, remediation):
    """`gitmodules-missing`, by `remove` and its dry run alike, naming
    where the file is still held, with nothing written: HEAD, the index,
    `family.yaml` and the registrations `deinit` would drop are as they
    were. Typed as printed, the remedy puts the file back: for an unmerged
    one, the restore git takes in that state, since `git checkout --merge`
    needs both sides' copies (the review's N2). The same `remove` then takes
    out MEMBER's section alone and passes the gate."""
    env = isolated(offline, tmp_path)
    set_up(holder, env)
    args = verb_args("remove", holder, family)

    refused_then_typed(holder, env, args,
                       (MISSING.format(held=where), remediation))

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
    typed_as_printed(holder, env, refused_alike(holder, env, args)[1])
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
#: commands the test types, the path HEAD's file gives OTHER's url ending)`.
NOT_STAGED = {
    "edited": (edited, MODIFIED, KEEP_OR_DROP, slice(0, 1),
               f"{OTHER}-moved.git"),
    "crlf": (crlf, MODIFIED + LINE_ENDINGS, KEEP_OR_DROP, slice(1, 2),
             f"{OTHER}.git"),
    "a link to the same bytes": (linked, MODIFIED, KEEP_OR_DROP, slice(1, 2),
                                 f"{OTHER}.git"),
    "assume-unchanged, edited": (
        assumed_and_edited, ASSUMED, KEEP_OR_DROP_ASSUMED, slice(0, 2),
        f"{OTHER}-moved.git"),
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
    (`edited`, whose `git add` keeps OTHER's moved url, and an edit behind
    assume-unchanged, staged once the mark is off), and one they put back
    does not. Only where `git add` would stage the index's own blob does
    the refusal say the difference may be line endings alone: CRLF, and
    not a link to the very same bytes (the review's N1)."""
    env = isolated(offline, tmp_path)
    set_up(holder, env)
    args = verb_args(verb, holder, family)

    refused_then_typed(holder, env, args,
                       (UNSTAGED.format(said=said, verb=verb), remediation),
                       typed)

    offline.assert_left_nothing()
    ran(holder, env, args)
    assert committed_url(holder, env).endswith(url)


#: `{id: (verb, set-up)}`: each state `gitmodules-sparse` refuses but the
#: edit `test_an_edit_skip_worktree_hides_is_refused_then_named_as_modified`
#: holds.
SPARSE_STATES = {
    "left out-remove": ("remove", left_out),
    "left out-add": ("add", left_out),
    "marked by hand, clean-add": ("add", marked(b"S", "--skip-worktree")),
    "marked both ways, clean-add": (
        "add", marked(b"s", "--skip-worktree", "--assume-unchanged")),
}


@pytest.mark.parametrize("verb, set_up", SPARSE_STATES.values(),
                         ids=SPARSE_STATES)
def test_a_gitmodules_a_sparse_checkout_leaves_out_is_refused(
        family, holder, offline, tmp_path, verb, set_up):
    """`gitmodules-sparse` (the review's N2): the printed restore of
    `gitmodules-missing`, `git checkout -- .gitmodules`, matches nothing in
    a sparse checkout that leaves the file out, and `add`'s own note's
    neither. `add` refuses a file the index marks skip-worktree even where
    it is on disk and clean, since `git submodule add` cannot stage it (on
    bfed143 it failed at the mount, after writing), and so where the index
    marks it assume-unchanged too, `ls-files -v`'s `s` (the re-review's
    X1). `git sparse-checkout disable` works in each, typed as printed, and
    the same command then runs."""
    env = isolated(offline, tmp_path)
    set_up(holder, env)
    args = verb_args(verb, holder, family)

    refused_then_typed(holder, env, args,
                       (SPARSE.format(verb=verb), SPARSE_REMEDY))

    ran(holder, env, args)
    assert committed_url(holder, env).endswith(f"{OTHER}.git")


@pytest.mark.parametrize("verb", ["remove", "add"])
def test_an_edit_skip_worktree_hides_is_refused_then_named_as_modified(
        family, holder, offline, tmp_path, verb):
    """CODEX'S SECOND STATE, SKIP-WORKTREE: an edit the mark hides from `git
    ls-files -m` is `gitmodules-sparse`, as a sparse checkout's file is,
    since git stages neither. Typed as printed, `git sparse-checkout
    disable` takes the mark off and keeps the edit, which the same command
    then names as modified; its restore typed, the command runs, and HEAD
    keeps OTHER's url."""
    env = isolated(offline, tmp_path)
    hidden_by_skip_worktree(holder, env)
    args = verb_args(verb, holder, family)

    refused_then_typed(holder, env, args,
                       (SPARSE.format(verb=verb), SPARSE_REMEDY))
    refused_then_typed(holder, env, args,
                       (UNSTAGED.format(said=MODIFIED, verb=verb),
                        KEEP_OR_DROP), slice(1, 2))

    ran(holder, env, args)
    assert committed_url(holder, env).endswith(f"{OTHER}.git")


#: `{id: (verb, the member it adds or removes, set-up)}`: a clean
#: `.gitmodules` behind a mark, which the verb commits rightly.
MARKED_CLEAN = {
    "skip-worktree-remove": ("remove", MEMBER,
                             marked(b"S", "--skip-worktree")),
    "assume-unchanged-remove": ("remove", MEMBER,
                                marked(b"h", "--assume-unchanged")),
    "assume-unchanged-add": ("add", SPARE, marked(b"h", "--assume-unchanged")),
}


@pytest.mark.parametrize("verb, member, set_up", MARKED_CLEAN.values(),
                         ids=MARKED_CLEAN)
def test_a_clean_gitmodules_behind_a_mark_is_committed_as_before(
        family, holder, offline, tmp_path, verb, member, set_up):
    """THE RE-REVIEW'S NITS 1 AND 2. A `.gitmodules` the index marks, whose
    work tree's copy is the index's, is not refused: `remove` committed one
    marked skip-worktree by hand rightly on bfed143 and still does, and both
    verbs commit one marked assume-unchanged. The dry run refuses nothing,
    and the commit changes exactly `.gitmodules`, `family.yaml` and the
    member's gitlink, with OTHER's url as it was and the gate passing."""
    env = isolated(offline, tmp_path)
    set_up(holder, env)
    args = verb_args(verb, holder, family)

    dry = run_script(FAMILY, *args, "--dry-run", env=env)

    assert dry.returncode == 0, dry.stdout + dry.stderr
    ran(holder, env, args)
    assert committed_paths(holder, env) == [
        GITMODULES, "family.yaml", f"members/{member}"]
    assert committed_url(holder, env).endswith(f"{OTHER}.git")
    assert validate(holder).returncode == 0


#: An operator with no global excludes, and one whose excludes match every
#: path (#242's `*`), where a plain `git add` refuses an untracked file.
OPERATOR_EXCLUDES = {"no excludes": b"", "*": RULES["*"]}


@pytest.mark.parametrize("rules", OPERATOR_EXCLUDES.values(),
                         ids=OPERATOR_EXCLUDES)
def test_add_refuses_an_untracked_gitmodules_in_a_holder_with_none(
        family, empty_holder, offline, tmp_path, rules):
    """CODEX'S FIRST STATE. In a holder with no member, neither the index nor
    HEAD holds a `.gitmodules`, and `git submodule add` writes its section
    into one the work tree has and stages all of it: `add` committed a file
    nobody staged. It is `gitmodules-unstaged` now, by both runs; staged as
    printed, `git add -f`, it goes into the commit with the member's
    section, under an operator's `*` too (the re-review's nit 3)."""
    env = {**isolated(offline, tmp_path),
           **excluding(tmp_path / "operator", rules)}
    note = b"# a note nobody staged\n"
    (empty_holder / GITMODULES).write_bytes(note)
    ignored = raw(empty_holder, env, "check-ignore", "-q", "--", GITMODULES,
                  check=False)
    assert (ignored.returncode == 0) == bool(rules), "premise"
    args = verb_args("add", empty_holder, family)

    refused_then_typed(empty_holder, env, args,
                       (UNSTAGED.format(said=UNTRACKED, verb="add"),
                        KEEP_OR_LEAVE_OUT))

    ran(empty_holder, env, args)
    assert raw(empty_holder, env, "show",
               f"HEAD:{GITMODULES}").stdout.startswith(note)
    assert head_paths(empty_holder, env) == [f"members/{SPARE}"]


def test_remove_refuses_an_untracked_gitmodules_in_a_holder_head_lost_it(
        family, holder, offline, tmp_path):
    """The same for `remove`, in the holder #407 leaves behind: HEAD lost
    `.gitmodules`, and its bytes are back in the work tree, untracked. `git
    rm` edits that file and stages it, so `remove` committed it. Staged as
    printed, the commit puts the file back in HEAD with MEMBER's section
    gone, and the gate passes."""
    env = isolated(offline, tmp_path)
    kept = (holder / GITMODULES).read_bytes()
    deletion_staged(holder, env)
    raw(holder, env, "commit", "-q", "-m", "The commit #407 describes")
    (holder / GITMODULES).write_bytes(kept)
    args = verb_args("remove", holder, family)

    refused_then_typed(holder, env, args,
                       (UNSTAGED.format(said=UNTRACKED, verb="remove"),
                        KEEP_OR_LEAVE_OUT))

    ran(holder, env, args)
    assert head_paths(holder, env) == [f"members/{OTHER}"]
    assert validate(holder).returncode == 0


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
    """Where none of the index, HEAD and the work tree holds a `.gitmodules`
    there is no copy to compare, and no `gitmodules-` refusal is made.

    THE REAL RUN STILL FAILS HERE, a known case from before #407 that goes
    with the gate's to #459: in a holder whose HEAD already lost the file,
    `remove` runs `deinit` and `git rm`, then dies at its commit's `git add
    -f -- .gitmodules family.yaml` and puts back only part of the unmount,
    while its dry run exits 0. So this pins only that #407's check asks
    nothing, and not the dry run's answer (the review's N3)."""
    env = isolated(offline, tmp_path)
    deletion_staged(holder, env)
    raw(holder, env, "commit", "-q", "-m", "The commit #407 describes")

    dry = run_script(FAMILY, *verb_args("remove", holder, family),
                     "--dry-run", env=env)

    assert "REFUSED gitmodules-" not in dry.stderr, dry.stderr


# --- the review's S1: a file mended by hand, then staged as printed ----------

def with_text(root: Path, env: dict, text: str) -> None:
    """`text` appended to `.gitmodules` and committed: a section somebody
    wrote by hand."""
    data = (root / GITMODULES).read_bytes() + text.encode("utf-8")
    (root / GITMODULES).write_bytes(data)
    raw(root, env, "commit", "-q", "-m", "A hand edit", "--", GITMODULES)


def name_taken(root: Path, env: dict) -> None:
    """A section NAMED for the spare's mount path, at another path."""
    with_text(root, env, f'[submodule "members/{SPARE}"]\n'
                         "\tpath = vendor/x\n\turl = /nowhere\n")


def renamed(root: Path, env: dict) -> None:
    """What `member-name-taken` asks for by hand: that section given a name
    of its own."""
    data = (root / GITMODULES).read_bytes()
    (root / GITMODULES).write_bytes(data.replace(
        f'[submodule "members/{SPARE}"]'.encode("utf-8"),
        b'[submodule "vendor/x"]'))


def unreadable(root: Path, env: dict) -> None:
    """A `.gitmodules` git cannot read, committed."""
    with_text(root, env, '[submodule "broken\n')


def mended(root: Path, env: dict) -> None:
    """What `gitmodules-unreadable` asks for by hand: a file git reads."""
    (root / GITMODULES).write_bytes(
        raw(root, env, "show", f"HEAD~1:{GITMODULES}").stdout)


#: `{code: (set-up, the hand edit its remediation asks for, which printed
#: command is the stage)}`.
HAND_MENDED = {
    "member-name-taken": (name_taken, renamed, slice(0, 1)),
    "gitmodules-unreadable": (unreadable, mended, slice(1, 2)),
}


@pytest.mark.parametrize("code, set_up, mend, typed",
                         [(code, *rest) for code, rest in HAND_MENDED.items()],
                         ids=HAND_MENDED)
def test_a_file_mended_by_hand_is_staged_as_printed_and_add_then_runs(
        family, holder, offline, tmp_path, code, set_up, mend, typed):
    """THE REVIEW'S S1. Each of these remediations has the person mend
    `.gitmodules` by hand and run `add` again; mended and not staged, the
    file was `gitmodules-unstaged` on the run again. Each now says to stage
    it, `git add .gitmodules`, as #300's and #360's do: mended, then typed
    as printed, the same `add` mounts the member."""
    env = isolated(offline, tmp_path)
    set_up(holder, env)
    args = verb_args("add", holder, family)
    first = run_script(FAMILY, *args, env=env)
    assert first.returncode == 2, first.stdout + first.stderr
    lines = first.stderr.splitlines()
    assert lines[0].startswith(f"REFUSED {code}: "), first.stderr

    mend(holder, env)

    assert typed_as_printed(holder, env, lines[-1], typed) == [
        f"git add {GITMODULES}"]
    ran(holder, env, args)
    assert f"members/{SPARE}" in head_paths(holder, env)
