# SPDX-License-Identifier: Apache-2.0
"""The holder gate's gitlink remedies, typed as printed in the state each
describes (#681).

THE ISSUE'S FOUR GITLINK LINES, each reproduced on #682's head (8b39cd19)
before this change:

- L20. `member-gitlink-unnamed` lists a gitlink HEAD records as well as one
  the index does, so after its printed `git rm -- members/IRQS`, staged and
  not committed, a re-run named the same gitlink and the same `git rm`,
  which then died `fatal: pathspec 'members/IRQS' did not match any files`,
  exit 128; a second path's `git rm --cached -- Members/IRRS` the same. It
  says the removal is staged and to commit it now, and prints no `git rm`.
- L2-38. `member-gitlink-absent` for a row kept with its gitlink and
  section taken out by `git rm` named `family.py add`, which refuses the
  row (`member-already-present`), and `family.py remove` dies at its `git
  submodule deinit`. It names the index line that puts the gitlink back at
  the commit the row pins and the lines that write the section back, as
  `member-gitmodules-absent` writes one, or the row taken out by hand
  (Brett Heap, 2026-10-16T14:11:42Z, "take all recommendations for #670
  and #681": the words-only direction).
- N-1. The variant move's `mv` moved a live submodule checkout out of the
  holder, whose `.git` file names `../../.git/modules/Members/<P>`, so
  `git -C ../Members-<P> status` said `fatal: not a git repository`. The
  line moves nothing where the directory holds a `.git` entry, and the text
  says where its commits are kept.
- N-2. The `mv`'s condition was stated by system ("On a case-sensitive
  disk, as Linux's usually is"), and on a Linux mount that folds case the
  `mv` moved the member's own checkout out. The line is guarded by `[
  <variant> -ef <path> ]`, which a POSIX shell runs.

THE SAME FAMILY AND OFFLINE RULES as `test_family_head_lost_gitmodules.py`
(#611), whose helpers are imported. A case-folding disk is EMULATED for
N-2: `Members` a symbolic link to `members`, so the two names are one
directory on this case-sensitive one, which is what `-ef` asks; no
case-folding mount is used. A state that needs a directory at a case
variant is skipped where the disk cannot hold one (`case_sensitive_disk`).
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path

import pytest

from conftest import git, rmtree, run_script
from test_family import (  # noqa: F401
    FAMILY, MEMBERS, ORG, SPARE, family, validate,
)
from test_family_add_refusals import holder, offline  # noqa: F401
from test_family_bootstrap_gate_order import fetching, type_line
from test_family_dry_run import isolated
from test_family_head_lost_gitmodules import (  # noqa: F401
    DISKS, GUARDED_MOVE, assert_passes_in_every_mode, case_sensitive_disk,
    commit_all, github_to, moved_as_printed, on_disk, pinned,
    pushed_and_cloned, recorded_at, refused_at, typed_in_sh,
)
from test_family_member_path import raw
from test_family_remove_gitmodules import verb_args
from test_family_tracking_branch import on_main  # noqa: F401
from test_validate_family_branch_step import BRANCH_LEFT
from test_validate_family_unnamed_mounts import (
    GITLINK_REMEDY, GITLINK_SAID, VARIANT, codes, commands, findings, removal,
    spare_commits, stage_gitlink, stage_unmerged_gitlink, take_out_as_printed,
    with_section,
)

MEMBER = MEMBERS[0]
HAND = f"members/{SPARE}"

#: What a gitlink whose removal is staged and not committed says in place of
#: a `git rm`, pinned as text: a holder's CI and a person read it.
STAGED = ("HEAD records it and the index holds nothing at that path, so its "
          "removal is staged and not committed, and no git rm is printed, "
          "since one fails there (pathspec ... did not match any files).")

#: What a hand mount's says after it, in place of the `git rm` step.
STAGED_HAND_MOUNT = (
    f" {STAGED} Commit that removal before family.py add, which refuses a "
    "path under another spelling of members/ that HEAD holds and the index "
    "no longer does, and on a branch, since family.py add refuses the "
    "holder's tracking branch: where the holder stands on it, the first "
    "command below makes one, taking the staged removal with it. If it was "
    "mounted by hand, then mount it with the second, from a checkout of "
    "openRepoShape: family.py add writes its row and its gitlink in one "
    "commit, and names the object store git rm leaves under .git/modules if "
    "one is still there. " + BRANCH_LEFT)


def head_gitlink(root: Path, env: dict, path: str) -> str:
    return raw(root, env, "rev-parse", f"HEAD:{path}").stdout.decode(
        "ascii").strip()


def added_as_printed(family, root: Path, env: dict, add: str):
    """The printed `family.py add`, `<org>` filled in, from a checkout of
    openRepoShape, reading the fixture's local remotes."""
    argv = [arg.replace("<org>", ORG) for arg in shlex.split(add)]
    assert argv[1:3] == ["scripts/family.py", "add"], add
    return run_script(FAMILY, *argv[2:], "--local-remote-dir",
                      str(family["remotes"]), env=env)


# --- L20: a removal staged and not committed --------------------------------

def test_a_hand_mounts_staged_removal_is_committed_and_added_as_printed(
        family, holder, offline, tmp_path):
    """THE ISSUE'S L20, from a real hand mount. Its printed branch and `git
    rm` typed, the re-run before the commit names the gitlink again, as
    HEAD still records it, says the removal is staged, and prints the
    branch and the `add` with no `git rm`, which typed again fails, as
    before the change. Committed as it says, and the `add` typed as
    printed (after the object store it names, as before), the holder passes
    in every mode with the member mounted."""
    env = fetching(isolated(offline, tmp_path))
    raw(holder, env, "submodule", "add", "-q", "--",
        str(family["remotes"] / f"{SPARE}.git"), HAND)
    commit_all(holder, env, "Mount IRQS by hand")
    at = head_gitlink(holder, env, HAND)
    gitlink, _ = findings(validate(holder, "--no-members"))
    switch, rm, add = commands(gitlink)
    raw(holder.parent, env, *shlex.split(switch)[1:])
    raw(holder, env, *shlex.split(rm)[1:])

    again = validate(holder, "--no-members")

    assert again.returncode == 1, again.stdout + again.stderr
    assert findings(again) == [
        GITLINK_SAID.format(path=HAND, commit=at) + STAGED_HAND_MOUNT
        + f"\n    {switch}\n    {add}"]
    retyped = raw(holder, env, *shlex.split(rm)[1:], check=False)
    assert retyped.returncode == 128, retyped.stderr
    assert b"did not match any files" in retyped.stderr
    commit_all(holder, env, "Take the hand mount out, as printed")
    refused = added_as_printed(family, holder, env, add)
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert "REFUSED member-git-dir-cached: " in refused.stderr
    rmtree(holder / ".git" / "modules" / "members" / SPARE)
    added = added_as_printed(family, holder, env, add)
    assert added.returncode == 0, added.stdout + added.stderr
    assert_passes_in_every_mode(holder, 3)


def test_a_staged_removal_on_the_tracking_branch_goes_to_the_branch(
        family, on_main, offline, tmp_path):
    """Staged on the holder's tracking branch, where `add` refuses: the
    finding's first command, typed as printed, makes the branch and takes
    the staged removal there; committed, the `add` typed as printed mounts
    the member on that branch."""
    env = isolated(offline, tmp_path)
    _, tip = spare_commits(family)
    stage_gitlink(on_main, HAND, tip)
    commit_all(on_main, env, "A hand mount on main")
    raw(on_main, env, "rm", "-q", "--cached", "--", HAND)

    (finding,) = findings(validate(on_main, "--no-members"))

    switch, add = commands(finding)
    raw(on_main.parent, env, *shlex.split(switch)[1:])
    assert raw(on_main, env, "diff", "--cached", "--name-only").stdout == (
        f"{HAND}\n".encode())
    commit_all(on_main, env, "Take the hand mount out, as printed")
    added = added_as_printed(family, on_main, env, add)
    assert added.returncode == 0, added.stdout + added.stderr
    assert raw(on_main, env, "symbolic-ref", "--short",
               "HEAD").stdout.strip() == f"family/add-{SPARE.lower()}".encode()
    assert_passes_in_every_mode(on_main, 3)


@DISKS
def test_a_second_paths_staged_removal_says_commit_it(holder, offline,
                                                      tmp_path, ignorecase):
    """A second path to MEMBER's directory, `Members/IRRS`, committed: its
    printed `git rm --cached` typed, the re-run says the removal is staged
    and to commit it, with no command, where it printed the same `git rm
    --cached` again. Committed, the holder passes in every mode."""
    env = on_disk(isolated(offline, tmp_path), ignorecase)
    at = pinned(holder, MEMBER)
    stage_gitlink(holder, f"Members/{MEMBER}", at)
    commit_all(holder, env, "A second path to IRRS")
    (first,) = findings(validate(holder, "--no-members"))
    (rm,) = commands(first)
    raw(holder, env, *shlex.split(rm)[1:])

    (again,) = findings(validate(holder, "--no-members"))

    assert again == (GITLINK_SAID.format(path=f"Members/{MEMBER}", commit=at)
                     + VARIANT.format(row_path=f"members/{MEMBER}",
                                      project=MEMBER)
                     + f" {STAGED} Commit that removal.")
    commit_all(holder, env, "Commit the removal, as printed")
    assert_passes_in_every_mode(holder, 2)


def test_a_section_git_rm_cached_leaves_keeps_its_own_commands(
        family, holder, tmp_path):
    """A hand mount taken out with `git rm --cached`, which leaves its
    `.gitmodules` section: the gitlink prints no `git rm`, so its section's
    finding prints the lines that take it out, where it said "the git rm
    printed above takes this section out too". Typed as printed, the
    commit carries both, and the holder passes."""
    _, tip = spare_commits(family)
    stage_gitlink(holder, HAND, tip)
    with_section(holder, tmp_path, HAND, HAND, f"/nowhere/{SPARE}.git")
    git("rm", "-q", "--cached", "--", HAND, cwd=holder)
    assert HAND in (holder / ".gitmodules").read_text(encoding="utf-8"), (
        "premise: git rm --cached leaves the section")

    result = validate(holder, "--no-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert codes(result) == ["member-gitlink-unnamed",
                             "gitmodules-path-unnamed"]
    gitlink, section = findings(result)
    assert "git rm" not in "".join(gitlink.splitlines()[1:]), gitlink
    assert commands(section) == removal(HAND, "path", "url")
    assert "takes this section out too" not in result.stderr
    take_out_as_printed(holder, section)
    assert_passes_in_every_mode(holder, 2)


def test_an_unmerged_gitlink_keeps_its_git_rm(family, holder):
    """No misfire: a gitlink HEAD records that the index holds at the
    conflict stages is a conflict, not a staged removal. It keeps the `git
    rm` it had, which takes an unmerged path out, and committed, the holder
    passes."""
    older, newer = spare_commits(family)
    stage_gitlink(holder, HAND, older)
    git("commit", "-qm", "A gitlink no row names", cwd=holder)
    stage_unmerged_gitlink(holder, HAND, newer)

    (gitlink,) = findings(validate(holder, "--no-members"))

    assert gitlink.splitlines()[0] == GITLINK_SAID.format(
        path=HAND, commit=older) + GITLINK_REMEDY
    rm = commands(gitlink)[1]
    assert rm == f"git rm -- {HAND}"
    git(*shlex.split(rm)[1:], cwd=holder)
    git("commit", "-qm", "Take it out, as printed", cwd=holder)
    assert_passes_in_every_mode(holder, 2)


# --- L2-38: a row whose gitlink was taken out by hand ----------------------

def put_back(commit: str, *, section: bool) -> list[str]:
    """`member-gitlink-absent`'s lines for MEMBER's row, whose gitlink is
    gone and, where `section`, its `.gitmodules` section too."""
    path = f"members/{MEMBER}"
    lines = [
        f"REFUSED member-gitlink-absent: no gitlink (mode 160000) recorded "
        f"at '{path}'. {MEMBER} is named in family.yaml but this repository "
        "does not record it as a submodule.",
        "Remediation: family.py add refuses the row, which is there "
        "(member-already-present), and family.py remove cannot take the "
        "member out, since its git submodule deinit finds no gitlink. If the "
        "member is to stay, put its gitlink back at the commit the row pins, "
        "in the index alone, which touches no file, with the first line "
        "below"
        + (", and its .gitmodules section back by hand, in a POSIX shell, as "
           "family.py add writes one, with the lines after it, then stage "
           ".gitmodules" if section else "")
        + ". Commit that, and `git submodule update --init --recursive`, or "
        f"`make bootstrap`, then checks the member out at {path}. If it is to "
        "go, take its row out of family.yaml by hand and commit that.",
        f"    git update-index --add --cacheinfo 160000,{commit},{path}"]
    if section:
        lines += [
            f"    git config -f .gitmodules submodule.{path}.path {path}",
            f"    git config -f .gitmodules submodule.{path}.url "
            f"https://github.com/{ORG}/{MEMBER}.git"]
    return lines


#: How the gitlink was taken out, and whether its section went with it.
TAKEN_OUT = {"git-rm": (("rm", "-r", "-q", "--"), True),
             "git-rm-cached": (("rm", "-r", "-q", "--cached", "--"), False)}


def taken_out(root: Path, env: dict, how: str) -> str:
    """MEMBER's gitlink taken out `how`, committed, its row kept. Returns
    the commit the row pins."""
    commit = pinned(root, MEMBER)
    raw(root, env, *TAKEN_OUT[how][0], f"members/{MEMBER}")
    commit_all(root, env, "Drop the gitlink but keep the row")
    return commit


def put_back_as_printed(root: Path, env: dict, lines: list[str]) -> None:
    """Every command line typed as printed, `.gitmodules` staged where a
    line writes it, and the commit the text says to make."""
    for line in lines[2:]:
        type_line(root, env, line)
    if len(lines) > 3:
        raw(root, env, "add", "--", ".gitmodules")
    commit_all(root, env, "Put the gitlink back, as printed")


@pytest.mark.parametrize("how", TAKEN_OUT)
def test_a_row_whose_gitlink_was_taken_out_is_put_back_as_printed(
        family, holder, offline, tmp_path, how):
    """THE ISSUE'S L2-38, with the section taken out too (`git rm`) and
    left (`git rm --cached`, whose section HEAD's `.gitmodules` still gives,
    so no line writes it). The `add` it named is refused, as before. Typed
    as printed and committed, `git submodule update --init --recursive`
    checks the member out, and the holder passes in every mode."""
    env = fetching(isolated(offline, tmp_path))
    commit = taken_out(holder, env, how)
    old_add = run_script(FAMILY, "add", "--family-root", str(holder),
                         "--member", f"{ORG}/{MEMBER}", "--local-remote-dir",
                         str(family["remotes"]), env=env)
    assert old_add.returncode == 2, old_add.stdout + old_add.stderr
    assert "REFUSED member-already-present: " in old_add.stderr

    refused = validate(holder)

    assert refused.returncode == 2, refused.stdout + refused.stderr
    lines = refused.stderr.splitlines()
    assert lines == put_back(commit, section=TAKEN_OUT[how][1])
    put_back_as_printed(holder, env, lines)
    raw(holder, env, "submodule", "update", "--init", "--recursive")
    assert_passes_in_every_mode(holder, 2)


def test_a_fresh_clone_of_it_is_put_back_and_checks_the_member_out(
        family, holder, offline, tmp_path):
    """The same state pushed and cloned, as CI checks it out: no object
    store of the member's in the clone. Typed as printed there, the update
    clones the member from the url the written section gives, and the
    clone's gate passes in every mode."""
    env = fetching(isolated(offline, tmp_path))
    commit = taken_out(holder, env, "git-rm")
    clone = pushed_and_cloned(holder, env, family, tmp_path, "w681/absent")
    assert not (clone / ".git" / "modules" / "members" / MEMBER).exists()

    refused = validate(clone)

    assert refused.returncode == 2, refused.stdout + refused.stderr
    lines = refused.stderr.splitlines()
    assert lines == put_back(commit, section=True)
    put_back_as_printed(clone, env, lines)
    raw(clone, env, *github_to(family["remotes"]), "submodule", "update",
        "--init", "--recursive")
    assert (clone / "members" / MEMBER / "project.yaml").is_file()
    assert_passes_in_every_mode(clone, 2)


def test_a_row_whose_member_is_to_go_is_taken_out_by_hand(holder, offline,
                                                          tmp_path):
    """The other way the refusal gives: the row taken out of `family.yaml`
    by hand and committed, and the holder passes in every mode with one
    member."""
    env = isolated(offline, tmp_path)
    taken_out(holder, env, "git-rm")
    rows = (holder / "family.yaml").read_bytes()
    start = rows.index(f"  - project: {MEMBER}\n".encode())
    end = rows.index(f"  - project: {MEMBERS[1]}\n".encode())
    (holder / "family.yaml").write_bytes(rows[:start] + rows[end:])
    raw(holder, env, "add", "--", "family.yaml")
    commit_all(holder, env, "IRRS is to go: its row taken out by hand")
    assert_passes_in_every_mode(holder, 1)


# --- N-1 and N-2: what the guarded `mv` moves ------------------------------

VARIANT_PATH = f"Members/{MEMBER}"
MOVED_TO = f"Members-{MEMBER}"


@pytest.mark.parametrize("layout", ["one-directory", "one-empty-directory",
                                    "apart"])
def test_the_move_moves_nothing_where_the_two_names_are_one_directory(
        holder, offline, tmp_path, case_sensitive_disk, layout):
    """THE ISSUE'S N-2. After the two lines and their commit, a directory
    at `Members/IRRS` that IS the row's own, as on a disk that folds case
    (emulated: `Members` a symbolic link to `members`): `-ef` is true, and
    the guarded line moves nothing, where the bare `mv` moved the member's
    checkout out of the holder. The row's own directory left empty, as a
    fresh clone leaves it before the update (here `git submodule deinit`):
    it holds no `.git` entry, so `-ef` alone keeps it in place. One apart
    from it, the empty one a fresh clone leaves at `Members/IRRS`: `-ef` is
    false, and the line moves it out. The holder passes in every mode
    every way."""
    env = fetching(isolated(offline, tmp_path))
    commit = recorded_at(holder, env, MEMBER, VARIANT_PATH)
    lines = refused_at(holder, commit, [VARIANT_PATH])
    moved_as_printed(holder, env, lines, [VARIANT_PATH])
    (move,) = GUARDED_MOVE.findall(lines[1])
    one = layout != "apart"
    own = holder / "members" / MEMBER
    if layout == "one-empty-directory":
        raw(holder, env, "submodule", "deinit", "-q", "-f", "--",
            f"members/{MEMBER}")
        assert own.is_dir() and not any(own.iterdir()), "premise: emptied"
    if one:
        try:
            os.symlink("members", holder / "Members", target_is_directory=True)
        except OSError as exc:
            pytest.skip(f"no symbolic link to emulate one directory: {exc}")
    else:
        (holder / VARIANT_PATH).mkdir(parents=True)
    checkout = typed_in_sh(holder, f"[ -e {VARIANT_PATH}/.git ]")

    test = typed_in_sh(holder, f"[ {VARIANT_PATH} -ef members/{MEMBER} ]")
    typed = typed_in_sh(holder, move)

    assert test.returncode == (0 if one else 1), test.stderr
    assert checkout.returncode == (0 if layout == "one-directory" else 1)
    assert typed.returncode == 0, typed.stderr
    assert own.is_dir()
    assert (tmp_path / MOVED_TO).exists() is not one
    if one:
        (holder / "Members").unlink()
    else:
        assert not (holder / VARIANT_PATH).exists()
    if layout == "one-empty-directory":
        raw(holder, env, "submodule", "update", "--init", "--",
            f"members/{MEMBER}")
    assert (own / "project.yaml").is_file()
    assert_passes_in_every_mode(holder, 2)


def mounted_at_the_variant(family, root: Path, env: dict, commit: str,
                           kind: str) -> None:
    """A checkout at `Members/IRRS`, at `commit`, recorded there and no
    longer at `members/IRRS`, committed: a `git submodule add`, whose `.git`
    is a file naming this holder's `.git/modules/Members/IRRS`, the 574/3
    layout, or a plain `git clone`, whose `.git` is its own directory."""
    remote = str(family["remotes"] / f"{MEMBER}.git")
    if kind == "submodule":
        raw(root, env, "submodule", "add", "-q", "--force", "--", remote,
            VARIANT_PATH)
    else:
        stage_gitlink(root, VARIANT_PATH, commit)
        raw(root, env, "clone", "-q", "--no-checkout", remote, VARIANT_PATH)
    raw(root / VARIANT_PATH, env, "checkout", "-q", "--detach", commit)
    raw(root, env, "add", "--", VARIANT_PATH)
    raw(root, env, "rm", "-q", "--cached", "--", f"members/{MEMBER}")
    commit_all(root, env, "IRRS recorded at Members/IRRS, checked out there")


@pytest.mark.parametrize("kind", ["submodule", "clone"])
def test_a_checkout_at_the_variant_is_left_in_place_and_deleted_by_hand(
        family, holder, offline, tmp_path, case_sensitive_disk, kind):
    """THE ISSUE'S N-1. A checkout at `Members/IRRS` holding a commit of
    its own: after the two lines and their commit, the guarded line moves
    nothing, where the bare `mv` left a submodule's checkout saying `fatal:
    not a git repository`. It is still a working checkout, and a
    submodule's commits are where the text says, in
    `.git/modules/Members/IRRS`, and stay there once the directory is
    deleted by hand, as the text says to do when nothing it holds is
    needed. Then the holder passes in every mode, and SPARE is added past
    it, where `family.py add` refused the directory."""
    env = fetching(isolated(offline, tmp_path))
    commit = pinned(holder, MEMBER)
    mounted_at_the_variant(family, holder, env, commit, kind)
    checkout = holder / VARIANT_PATH
    raw(checkout, env, "commit", "-q", "--allow-empty", "-m", "Work there")
    work = raw(checkout, env, "rev-parse", "HEAD").stdout.decode(
        "ascii").strip()
    store = holder / ".git" / "modules" / "Members" / MEMBER
    if kind == "submodule":
        assert (checkout / ".git").read_bytes() == (
            b"gitdir: ../../.git/modules/Members/" + MEMBER.encode() + b"\n")
    lines = refused_at(holder, commit, [VARIANT_PATH])
    moved_as_printed(holder, env, lines, [VARIANT_PATH])
    (move,) = GUARDED_MOVE.findall(lines[1])

    typed = typed_in_sh(holder, move)

    assert typed.returncode == 0, typed.stderr
    assert not (tmp_path / MOVED_TO).exists()
    assert raw(checkout, env, "status", "--porcelain").returncode == 0
    if kind == "submodule":
        assert Path(raw(checkout, env, "rev-parse", "--absolute-git-dir")
                    .stdout.decode().strip()).resolve() == store.resolve()
        found = validate(holder)
        assert codes(found) == ["gitmodules-path-unnamed"], found.stderr
        take_out_as_printed(holder, findings(found)[0])
    rmtree(checkout)
    if kind == "submodule":
        kept = raw(holder, env, f"--git-dir={store}", f"--work-tree={holder}",
                   "cat-file", "-e", work, check=False)
        assert kept.returncode == 0, kept.stderr
    assert_passes_in_every_mode(holder, 2)
    added = run_script(FAMILY, *verb_args("add", holder, family), env=env)
    assert added.returncode == 0, added.stdout + added.stderr
    assert_passes_in_every_mode(holder, 3)
