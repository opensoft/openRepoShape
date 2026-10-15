# SPDX-License-Identifier: Apache-2.0
"""`bump-leg.py`, then `make bootstrap`: the leg ends on its tracking branch
AT the new pin (#475).

THE DEFECT. AGENTS.md's "Advancing a leg", README, the line `bump-leg.py`
prints and every project's `AGENTS-shape.md` say that `make bootstrap`
re-places a bumped leg on its tracking branch at the new pin. On a project
bootstrapped once, which is every project setup.sh makes, it did not: the
leg's `main` was still at the old pin, bootstrap moved no existing branch,
printed `not moving an existing branch`, exited 0 and left the leg DETACHED,
where the next commit made in it is on no branch. `tests/test_bump_leg.py`
never ran bootstrap after a bump, and its clone was never bootstrapped, so
it had no branch to lag.

THE SAME HARM ON THE FIRST DAY. A fresh `git clone --recurse-submodules`
makes each leg's `main` at its remote's tip and leaves the leg detached at the
pin. Where the leg's remote has moved past the pin, the ordinary state of an
active project, bootstrap met a `main` ahead of the pin and left the leg
detached under the same `not moving an existing branch`, which AGENTS.md's
section 3 says it does not do.

THE RULE NOW. A tracking branch whose tip is an ancestor of the pin is
fast-forwarded to it from the two checkouts that state comes in: detached at
the pin, which is what `bump-leg.py` leaves, and on the branch itself, where
`merge.autostash` is off for the one merge. A branch AHEAD of the pin with no
commit of its own (its tip IS its upstream's remote-tracking ref) is moved
back to the pin from a leg detached there, and the line names what still
holds those commits and the command that brings the branch forward. Any other
branch holding a commit the pin lacks, ahead or diverged, is still never moved
and keeps its message, byte for byte. A checkout that is neither is not moved
off. A move git refuses is said in git's words, without its blank lines, and
nothing else moves; a branch that moved before git refused the checkout is
said to have moved. A checkout is judged by where HEAD is afterwards, for a
branch already at the pin too: one git refused is never called `on main`,
and a failing post-checkout hook after HEAD moved is not called a refusal.
The command the move-back line prints is shell-quoted.

THE BRANCH AT THE PIN (#533). `bump-leg.py --to` a branch's own tip leaves
the leg detached AT the branch, and a commit made there is on no branch.
Bootstrap used to check the branch out regardless, printing `on main at
<pin>` over a commit held only by HEAD's reflog; a leg detached at a commit
that is not the pin is now left there and said, as the behind branch's is. A
checkout that exits non-zero with HEAD already on the branch at the pin (a
stale lock, a failing hook) had nothing to check out, and is said so rather
than as `checked out, and then git said:`, and never as `refused`. The same
rule covers a tracking branch that is not there: a leg detached off the pin
is not given a branch created at the pin over its commit. A leg detached at an
ancestor of the pin, or at `origin/main` past it, is left where it is too,
which bootstrap once placed. `not moving an existing branch` names where the
checkout stays, which is not always the pin: HEAD may be on the branch itself.

A LEG ON ANOTHER BRANCH (#603, D1). A tracking branch BEHIND the pin is
fast-forwarded from a third checkout too: HEAD on another branch. It was left
there under `which is neither`, while a tracking branch AT the pin was checked
out from the same checkout, and the difference was left to #458 to rule on. The
other branch keeps its commits, so the move loses no commit: `branch -f` moves
the tracking branch to the pin and the checkout puts the leg on it, as from the
pin; the other branch is not touched. One line under the `fast-forwarded` one
says the leg left that branch and that it keeps its commits (or has none yet),
since the next commit made in the leg is on the tracking branch now; no other
start prints it, and nor does a refusal. From another branch the checkout
changes files, so git can refuse it over a local edit or an untracked file,
which a checkout from the pin never meets: the branch is then left at the pin
and HEAD where it was, and the next run meets the branch-at-the-pin state. Two
things are NOT refused, as in the branch-at-the-pin and missing-branch cases
(#458's to rule on): an IGNORED file at a path the pin tracks is overwritten,
and a merge in progress on the other branch is ended, its `MERGE_HEAD` removed
and its staged result carried onto `main`. A leg detached at a commit that is
not the pin is still left, whatever it holds.

EACH TEST GOES THE WAY A PERSON DOES: a scaffold into bare repositories on
disk, cloned recursively and bootstrapped, so each leg is on `main` at its
pin; a new commit pushed to the spec leg's remote; a branch in the root,
`bump-leg.py`, then `bootstrap.py` again. The scaffold is this module's own,
not the session's, because every test pushes a commit to the spec remote,
each to a branch of its own so that no test sees another's. The fresh-clone
tests have a second scaffold of their own, whose spec remote's `main` HAS
moved past the pin, cloned recursively per test and never bootstrapped
before. No bash and no `gh`: every step is git or one of the Python tools, so
the module runs unchanged on Linux, macOS and Windows.
"""

from __future__ import annotations

import os
import shlex
import shutil
from pathlib import Path

import pytest

from conftest import (ORG, PROJECT, REPO, SCAFFOLD, cloned_just_pushed, git,
                      run_script)

BUMP = REPO / "scripts" / "bump-leg.py"
MAIN = "refs/heads/main"
NOT_MOVING = "not moving an existing branch"
REFUSED = "and git refused to move it:"
#: The file the new leg commit adds, and so the one an untracked copy of
#: blocks a fast-forward on.
ADDED = "NEW-CONTRACT.md"
#: A file the spec leg tracks, which a new leg commit can change too.
EDITED = "README.md"
#: The file the commit that moves the spec remote's `main` past the pin adds.
MOVED_ON = "MOVED-ON.md"


def not_moving(pin: str, tip: str, stays: str = "at the pin") -> str:
    """Step (a)'s refusal of a spec branch holding a commit the pin lacks,
    byte for byte as main prints it. `stays` is where the checkout is:
    `at the pin` (detached there), `on main at its tip`, or `at <sha12>
    (detached)` / `at <sha12> (on <branch>)` (#533)."""
    return (f"  [spec] spec: PIN {pin[:12]} != branch main tip {tip[:12]}\n"
            f"          not moving an existing branch. The checkout stays "
            f"{stays}; the recorded pin is authoritative and advancing it "
            "is an explicit commit in this repository.\n")


def moved_back(tip: str, pin: str, branch: str = "main", leg: str = "spec",
               command: str | None = None) -> str:
    """The one line step (a) prints when it moves the spec leg's branch
    back to the pin, `branch` and `leg` as they are spelled, and `command`
    as it is quoted when that is not the plain one."""
    command = command or f"git -C {leg} merge --ff-only origin/{branch}"
    return (f"  [spec] {leg}: branch {branch} moved back {tip[:12]} -> "
            f"{pin[:12]}, the pin; nothing is lost, origin/{branch} still "
            f"holds those commits, and `{command}` brings the branch forward")


def lock_index(leg: Path) -> Path:
    """A stale `index.lock` in the leg's gitdir, as a git that crashed
    leaves one. Returns it, for the test to remove."""
    gitdir = Path(git("rev-parse", "--absolute-git-dir",
                      cwd=leg).stdout.strip())
    (gitdir / "index.lock").write_bytes(b"")
    return gitdir / "index.lock"


def skip_validators(root: Path):
    """`bootstrap.py --skip-validators`: what these tests ask is step (a)."""
    return run_script(root / "scripts" / "bootstrap.py", "--skip-validators",
                      cwd=root)


def configured(key: str, value: str) -> dict:
    """`key` set to `value` for one run, as a person's `~/.gitconfig`
    would set it, through git's `GIT_CONFIG_COUNT`, `GIT_CONFIG_KEY_<n>`
    and `GIT_CONFIG_VALUE_<n>` (git 2.31), never `git config`. APPENDED to
    what the environment holds: the Windows job sets two entries already
    (`.github/workflows/tests.yml`), and a count of 1 would drop both."""
    held = int(os.environ.get("GIT_CONFIG_COUNT") or 0)
    return {"GIT_CONFIG_COUNT": str(held + 1),
            f"GIT_CONFIG_KEY_{held}": key,
            f"GIT_CONFIG_VALUE_{held}": value}


def failing_post_checkout(tmp_path: Path) -> dict:
    """A post-checkout hook that fails, through `core.hooksPath` in the
    command scope, never `git config`; a shebang script, which Git for
    Windows runs through its own `sh`. Returns the environment that sets
    it (`configured`)."""
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "post-checkout").write_bytes(
        b"#!/bin/sh\necho 'post-checkout hook failed' >&2\nexit 1\n")
    (hooks / "post-checkout").chmod(0o755)
    return configured("core.hooksPath", hooks.as_posix())


def bootstrap(root: Path):
    return run_script(root / "scripts" / "bootstrap.py", cwd=root)


def head_ref(leg: Path) -> str | None:
    """The branch HEAD is on, or None when it is detached."""
    proc = git("symbolic-ref", "--quiet", "HEAD", cwd=leg, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else None


def rev(repo: Path, name: str = "HEAD") -> str:
    return git("rev-parse", "--verify", name, cwd=repo).stdout.strip()


@pytest.fixture(scope="module")
def bootstrapped(tmp_path_factory) -> dict:
    """One scaffold, cloned recursively and bootstrapped ONCE, so each leg
    is on `main` at its pin: the state every later bootstrap meets."""
    base = tmp_path_factory.mktemp("bootstrap-after-bump")
    remotes = base / "remotes"
    made = run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                      "--elected-by", "Test Human", "--elected-on",
                      "2026-09-02", "--local-remote-dir", str(remotes),
                      "--work-dir", str(base / "work"))
    assert made.returncode == 0, made.stderr + made.stdout
    clone = cloned_just_pushed(remotes / f"{PROJECT}.git",
                               base / "clone" / PROJECT)
    first = bootstrap(clone)
    assert first.returncode == 0, first.stderr + first.stdout
    assert head_ref(clone / "spec") == MAIN, first.stdout
    return {"remotes": remotes, "clone": clone}


@pytest.fixture
def root(bootstrapped, tmp_path) -> Path:
    """A private copy of the bootstrapped clone. A leg's `.git` file and
    its config name `.git/modules/<leg>` relatively, so the copy is whole."""
    target = tmp_path / PROJECT
    shutil.copytree(bootstrapped["clone"], target, symlinks=True)
    return target


def advance(remotes: Path, tmp_path: Path, branch: str,
            touch: str | None = None) -> str:
    """A new commit on the spec leg's REMOTE. Returns it.

    The commit is pushed to `branch` rather than to `main`, so the remote's
    `main` stays where every copy of the clone has it; `bump-leg.py` asks
    only that some branch of the remote contains the commit. With `touch`,
    the commit also adds a line at the end of that tracked file.
    """
    work = cloned_just_pushed(remotes / f"{PROJECT}-spec.git",
                              tmp_path / "spec-work")
    (work / ADDED).write_bytes(b"# a contract the leg gained\n")
    git("add", "--", ADDED, cwd=work)
    if touch is not None:
        (work / touch).write_bytes((work / touch).read_bytes()
                                   + b"\nupstream line\n")
        git("add", "--", touch, cwd=work)
    git("commit", "-q", "-m", "Advance the spec leg", cwd=work)
    git("push", "-q", "origin", f"HEAD:refs/heads/{branch}", cwd=work)
    return rev(work)


def bump_spec(root: Path, remotes: Path, new: str):
    """`bump-leg.py` to `new` from a branch of the root, exactly as
    AGENTS.md has it. Returns the run, whose output is what a person reads."""
    git("checkout", "-q", "-b", "bump/spec", cwd=root)
    result = run_script(BUMP, "--root", str(root), "--leg", "spec", "--to",
                        new, "--local-remote-dir", str(remotes))
    assert result.returncode == 0, result.stderr + result.stdout
    assert head_ref(root / "spec") is None, "bump-leg.py leaves it detached"
    assert rev(root / "spec") == new
    return result


def bumped(root: Path, remotes: Path, tmp_path: Path, branch: str,
           touch: str | None = None) -> str:
    """A new commit on the spec leg's REMOTE (`advance`), then `bump-leg.py`
    to it (`bump_spec`). Returns the commit."""
    new = advance(remotes, tmp_path, branch, touch)
    bump_spec(root, remotes, new)
    return new


# --- behind the pin: fast-forwarded -----------------------------------------

def test_bootstrap_after_a_bump_puts_the_leg_on_its_branch_at_the_new_pin(
        root, bootstrapped, tmp_path):
    """THE ISSUE'S OWN REPRODUCTION: bootstrapped, bumped, bootstrapped."""
    leg = root / "spec"
    old = rev(leg)
    new = bumped(root, bootstrapped["remotes"], tmp_path, "advance-detached")

    result = bootstrap(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (f"[spec] spec: branch main fast-forwarded {old[:12]} -> "
            f"{new[:12]}, the pin") in result.stdout, result.stdout
    assert NOT_MOVING not in result.stdout
    assert "the leg was " not in result.stdout, "detached at the pin"
    assert head_ref(leg) == MAIN, "the leg is on its tracking branch"
    assert rev(leg, MAIN) == new, "AT the new pin"
    assert rev(root, "HEAD:spec") == new, "and the pin is not moved"
    assert git("status", "--porcelain", cwd=root).stdout == "", (
        "the leg's checkout is the commit the root records")


def test_a_leg_on_its_branch_behind_the_pin_is_fast_forwarded_with_its_files(
        root, bootstrapped, tmp_path):
    """The other checkout a behind branch comes in: HEAD on the branch at
    the old pin. The working tree moves with it."""
    leg = root / "spec"
    old = rev(leg)
    new = bumped(root, bootstrapped["remotes"], tmp_path, "advance-on-main")
    git("checkout", "-q", "main", cwd=leg)
    assert not (leg / ADDED).exists()

    result = bootstrap(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"fast-forwarded {old[:12]} -> {new[:12]}" in result.stdout, (
        result.stdout)
    assert "the leg was " not in result.stdout, "HEAD was on `main`"
    assert head_ref(leg) == MAIN
    assert rev(leg, MAIN) == new
    assert (leg / ADDED).is_file(), "the pin's files are checked out"
    assert git("status", "--porcelain", cwd=leg).stdout == ""


# --- holding a commit the pin lacks: never moved ----------------------------

def test_a_branch_ahead_of_the_pin_is_not_moved(root):
    leg = root / "spec"
    pin = rev(root, "HEAD:spec")
    git("commit", "-q", "--allow-empty", "-m", "local work", cwd=leg)
    ahead = rev(leg)

    result = bootstrap(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"PIN {pin[:12]} != branch main tip {ahead[:12]}" in result.stdout
    assert NOT_MOVING in result.stdout
    assert not_moving(pin, ahead, "on main at its tip") in result.stdout, (
        "HEAD is on `main`, which is where the checkout stays")
    assert "fast-forwarded" not in result.stdout
    assert rev(leg, MAIN) == ahead
    assert head_ref(leg) == MAIN


def test_a_branch_that_diverged_from_the_pin_is_not_moved(
        root, bootstrapped, tmp_path):
    """A local commit on `main` that the new pin does not contain: moving
    `main` to the pin would drop it."""
    leg = root / "spec"
    pin = rev(root, "HEAD:spec")
    git("commit", "-q", "--allow-empty", "-m", "local work", cwd=leg)
    mine = rev(leg)
    # Back at the gitlink, as `git submodule update` leaves it, so the root
    # is clean for the bump; `main` keeps the local commit.
    git("checkout", "-q", "--detach", pin, cwd=leg)
    new = bumped(root, bootstrapped["remotes"], tmp_path, "advance-diverged")

    result = bootstrap(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"PIN {new[:12]} != branch main tip {mine[:12]}" in result.stdout
    assert NOT_MOVING in result.stdout
    assert not_moving(new, mine) in result.stdout, "detached at the pin"
    assert rev(leg, MAIN) == mine, "the local commit is still on main"
    assert head_ref(leg) is None and rev(leg) == new


# --- a checkout that is neither, and a move git refuses ---------------------

def test_a_commit_made_on_the_detached_leg_is_not_left_behind(
        root, bootstrapped, tmp_path):
    """Bumped, then a commit made in the leg before anybody bootstrapped:
    it is on no branch, and checking `main` out would leave it only in the
    reflog. Nothing moves."""
    leg = root / "spec"
    old = rev(leg)
    bumped(root, bootstrapped["remotes"], tmp_path, "advance-then-commit")
    git("commit", "-q", "--allow-empty", "-m", "made on the detached leg",
        cwd=leg)
    made = rev(leg)

    result = bootstrap(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (f"the checkout is at {made[:12]} (detached), which is neither"
            in result.stdout), result.stdout
    assert head_ref(leg) is None and rev(leg) == made
    assert rev(leg, MAIN) == old


def test_a_fast_forward_an_untracked_file_blocks_moves_nothing(
        root, bootstrapped, tmp_path):
    leg = root / "spec"
    old = rev(leg)
    bumped(root, bootstrapped["remotes"], tmp_path, "advance-blocked")
    git("checkout", "-q", "main", cwd=leg)
    (leg / ADDED).write_bytes(b"mine\n")

    result = bootstrap(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert REFUSED in result.stdout, result.stdout
    assert ADDED in result.stdout, "git's own words name the file in the way"
    assert head_ref(leg) == MAIN and rev(leg, MAIN) == old
    assert (leg / ADDED).read_bytes() == b"mine\n"


@pytest.mark.parametrize("autostash", [False, True],
                         ids=["plain", "merge.autostash"])
def test_a_local_edit_the_pin_changes_too_is_refused_and_nothing_moves(
        root, bootstrapped, tmp_path, autostash):
    """HEAD on `main` behind the pin, with a local edit to a tracked file
    the commits up to the pin change as well. Plain, `merge --ff-only`
    refuses. With `merge.autostash=true` in the person's config, git
    stashed the edit, fast-forwarded, applied the stash back into
    conflicts and exited 0, and bootstrap said `fast-forwarded` over an
    unmerged leg. Off for the one merge, it refuses the same way."""
    leg = root / "spec"
    old = rev(leg)
    bumped(root, bootstrapped["remotes"], tmp_path,
           f"advance-edit-{'autostash' if autostash else 'plain'}",
           touch=EDITED)
    git("checkout", "-q", "main", cwd=leg)
    edited = (leg / EDITED).read_bytes() + b"\nmy local line\n"
    (leg / EDITED).write_bytes(edited)

    result = run_script(root / "scripts" / "bootstrap.py", cwd=root,
                        env=configured("merge.autostash", "true")
                        if autostash else None)
    assert result.returncode == 0, result.stderr + result.stdout
    assert REFUSED in result.stdout, result.stdout
    assert f"          {EDITED}\n" in result.stdout, "git names the file"
    assert "fast-forwarded" not in result.stdout
    assert head_ref(leg) == MAIN and rev(leg, MAIN) == old
    assert git("stash", "list", cwd=leg).stdout == "", "nothing stashed"
    assert git("ls-files", "--unmerged", cwd=leg).stdout == "", "no conflict"
    assert (leg / EDITED).read_bytes() == edited, "the edit is as it was"


def test_a_checkout_refused_after_the_branch_moved_says_it_moved(
        root, bootstrapped, tmp_path):
    """A stale `index.lock` in the leg, KEPT across two runs. `branch -f`
    moves `main`, which touches no index, and the `checkout` dies on the
    lock. The line used to say git `refused to move it` over a branch it
    had moved, and printed the blank line in git's message as a line of
    spaces. The second run finds `main` at the pin and used to print `on
    main at`, over a leg still detached; it says git refused the checkout
    again. A run once the lock is gone checks the branch out."""
    leg = root / "spec"
    old = rev(leg)
    new = bumped(root, bootstrapped["remotes"], tmp_path, "advance-locked")
    lock = lock_index(leg)

    result = skip_validators(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (f"  [spec] spec: branch main moved {old[:12]} -> {new[:12]}, the "
            "pin, and git refused to check it out:\n") in result.stdout, (
        result.stdout)
    assert REFUSED not in result.stdout
    assert "index.lock" in result.stdout, "git's own words"
    assert [line for line in result.stdout.splitlines()
            if line and not line.strip()] == [], "no line of spaces"
    assert rev(leg, MAIN) == new and head_ref(leg) is None

    second = skip_validators(root)
    assert (f"  [spec] spec: branch main is at the pin {new[:12]}, and git "
            "refused to check it out:\n") in second.stdout, second.stdout
    assert "[spec] spec: on main at" not in second.stdout
    assert rev(leg, MAIN) == new and head_ref(leg) is None

    lock.unlink()
    again = skip_validators(root)
    assert f"  [spec] spec: on main at {new[:12]} (branch tip == pin)" in (
        again.stdout), again.stdout
    assert head_ref(leg) == MAIN


def test_a_branch_at_the_pin_git_will_not_check_out_is_not_called_on_it(
        root):
    """`main` IS the pin and the leg is detached there, with a stale
    `index.lock`. The checkout dies on the lock; bootstrap printed `on main
    at` all the same, and the leg stayed detached, where the next commit is
    on no branch. Now git's refusal is printed and nothing moves."""
    leg = root / "spec"
    pin = rev(leg)
    git("checkout", "-q", "--detach", pin, cwd=leg)
    lock = lock_index(leg)

    result = skip_validators(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (f"  [spec] spec: branch main is at the pin {pin[:12]}, and git "
            "refused to check it out:\n") in result.stdout, result.stdout
    assert "index.lock" in result.stdout, "git's own words"
    assert "[spec] spec: on main at" not in result.stdout
    assert head_ref(leg) is None and rev(leg) == pin and rev(leg, MAIN) == pin

    lock.unlink()
    again = skip_validators(root)
    assert f"  [spec] spec: on main at {pin[:12]} (branch tip == pin)" in (
        again.stdout), again.stdout
    assert head_ref(leg) == MAIN


def test_a_branch_another_worktree_has_checked_out_is_not_reset(
        root, bootstrapped, tmp_path):
    """`main` checked out in a second worktree of the leg. Resetting it
    there would leave that worktree's files behind its own HEAD, which
    `git checkout -B` does on git 2.43; bootstrap refuses instead."""
    leg = root / "spec"
    old = rev(leg)
    new = bumped(root, bootstrapped["remotes"], tmp_path, "advance-worktree")
    elsewhere = tmp_path / "elsewhere"
    git("worktree", "add", str(elsewhere), "main", cwd=leg)

    result = bootstrap(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert REFUSED in result.stdout, result.stdout
    assert rev(leg, MAIN) == old
    assert git("status", "--porcelain", cwd=elsewhere).stdout == "", (
        "the other worktree still matches its HEAD")
    assert head_ref(leg) is None and rev(leg) == new


# --- what it prints of the manifest is spelled (#391) -----------------------

def test_the_branch_is_spelled_in_the_lines_that_name_it(root):
    """A tracking branch git accepts and a terminal should not be handed
    raw (U+2028), in the two lines that name it here: the checkout that is
    neither, and the fast-forward. The validators are skipped, as in
    `tests/test_bootstrap_spelling.py`: they are not what is asked."""
    manifest = root / "project.yaml"
    text = manifest.read_bytes()
    assert text.count(b'tracking_branch: "main"\n') == 1, text
    manifest.write_bytes(text.replace(b'tracking_branch: "main"\n',
                                      b'tracking_branch: "tb\\u2028x"\n'))
    named = r"tb\u2028x"
    leg = root / "spec"
    old = rev(leg)

    def printed() -> str:
        result = run_script(root / "scripts" / "bootstrap.py",
                            "--skip-validators", cwd=root)
        assert result.returncode == 0, result.stderr + result.stdout
        assert "\u2028" not in result.stdout, result.stdout
        return result.stdout

    assert f"branch {named} created at {old[:12]}" in printed()
    # The bumped state by hand: a child of the pin, checked out detached and
    # staged as the gitlink, which is what the root answers for the pin.
    tree = rev(leg, f"{old}^{{tree}}")
    new = git("commit-tree", tree, "-p", old, "-m", "advance",
              cwd=leg).stdout.strip()
    git("checkout", "-q", "--detach", new, cwd=leg)
    git("add", "--", "spec", cwd=root)
    git("commit", "-q", "--allow-empty", "-m", "made on the detached leg",
        cwd=leg)
    made = rev(leg)
    assert (f"  [spec] spec: branch {named} tip {old[:12]} is behind the PIN "
            f"{new[:12]}, and the checkout is at {made[:12]} (detached), "
            "which is neither") in printed()

    git("checkout", "-q", "--detach", new, cwd=leg)
    assert (f"  [spec] spec: branch {named} fast-forwarded {old[:12]} -> "
            f"{new[:12]}, the pin") in printed()


def test_the_branch_and_its_upstream_are_spelled_in_the_move_back(root):
    """The line that moves a branch back names the branch, its upstream and
    a command with both in it; each is spelled (#391). The state is built
    by hand: a commit past the pin, a remote-tracking ref at it, the branch
    tracking that ref, and the leg detached at the pin."""
    manifest = root / "project.yaml"
    text = manifest.read_bytes()
    assert text.count(b'tracking_branch: "main"\n') == 1, text
    manifest.write_bytes(text.replace(b'tracking_branch: "main"\n',
                                      b'tracking_branch: "tb\\u2028x"\n'))
    raw = "tb\u2028x"
    leg = root / "spec"
    pin = rev(leg)
    tree = rev(leg, f"{pin}^{{tree}}")
    ahead = git("commit-tree", tree, "-p", pin, "-m", "the remote moved on",
                cwd=leg).stdout.strip()
    git("update-ref", f"refs/remotes/origin/{raw}", ahead, cwd=leg)
    git("branch", "-q", "--track", raw, f"origin/{raw}", cwd=leg)
    git("checkout", "-q", "--detach", pin, cwd=leg)

    result = skip_validators(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "\u2028" not in result.stdout, result.stdout
    command = r"git -C spec merge --ff-only 'origin/tb\u2028x'"
    assert moved_back(ahead, pin, r"tb\u2028x", command=command) in (
        result.stdout), result.stdout
    assert rev(leg, f"refs/heads/{raw}") == pin and rev(leg) == pin
    assert head_ref(leg) is not None


# --- a fresh clone of a leg whose remote moved past the pin -----------------

@pytest.fixture(scope="module")
def leg_main_ahead(tmp_path_factory) -> dict:
    """A scaffold whose spec remote's `main` is one commit PAST the pin, as
    an active project's is. Its own, because it moves the remote's `main`,
    which the scaffold above keeps where every copy of its clone has it."""
    base = tmp_path_factory.mktemp("leg-main-ahead")
    remotes = base / "remotes"
    made = run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                      "--elected-by", "Test Human", "--elected-on",
                      "2026-09-02", "--local-remote-dir", str(remotes),
                      "--work-dir", str(base / "work"))
    assert made.returncode == 0, made.stderr + made.stdout
    work = cloned_just_pushed(remotes / f"{PROJECT}-spec.git",
                              base / "spec-work")
    (work / MOVED_ON).write_bytes(b"# the leg's main moved on\n")
    git("add", "--", MOVED_ON, cwd=work)
    git("commit", "-q", "-m", "The leg moves on past the pin", cwd=work)
    git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=work)
    return {"remotes": remotes, "ahead": rev(work)}


@pytest.fixture
def fresh(leg_main_ahead, tmp_path) -> Path:
    """`git clone --recurse-submodules` of the root, as AGENTS.md has a
    person run it, never bootstrapped: git made the spec leg's `main` at
    the remote's tip and left the leg detached at the pin."""
    clone = cloned_just_pushed(leg_main_ahead["remotes"] / f"{PROJECT}.git",
                               tmp_path / PROJECT)
    leg = clone / "spec"
    assert head_ref(leg) is None and rev(leg) == rev(clone, "HEAD:spec")
    assert rev(leg, MAIN) == leg_main_ahead["ahead"]
    assert rev(leg, "refs/remotes/origin/main") == leg_main_ahead["ahead"]
    return clone


def test_a_fresh_clone_whose_leg_moved_on_puts_the_leg_on_main_at_the_pin(
        fresh, leg_main_ahead):
    """THE ONBOARDING FLOW, end to end: clone, bootstrap. The leg ends on
    `main` AT the pin, the root is clean, and the command the line names
    brings `main` forward to what origin holds."""
    leg = fresh / "spec"
    pin = rev(fresh, "HEAD:spec")
    ahead = leg_main_ahead["ahead"]

    result = bootstrap(fresh)
    assert result.returncode == 0, result.stderr + result.stdout
    assert moved_back(ahead, pin) in result.stdout, result.stdout
    assert NOT_MOVING not in result.stdout
    assert head_ref(leg) == MAIN, "the leg is on its tracking branch"
    assert rev(leg, MAIN) == pin, "AT the pin"
    assert rev(fresh, "HEAD:spec") == pin, "and the pin is not moved"
    assert git("status", "--porcelain", cwd=fresh).stdout == "", (
        "the root is clean")
    assert git("status", "--porcelain", cwd=leg).stdout == ""
    assert rev(leg, "refs/remotes/origin/main") == ahead, "origin holds it"
    assert git("rev-parse", "--symbolic-full-name", "main@{upstream}",
               cwd=leg).stdout.strip() == "refs/remotes/origin/main"

    git("-C", "spec", "merge", "--ff-only", "-q", "origin/main", cwd=fresh)
    assert head_ref(leg) == MAIN and rev(leg, MAIN) == ahead


def test_a_local_edit_in_a_fresh_leg_is_kept_when_main_moves_back(
        fresh, leg_main_ahead):
    """HEAD is detached AT the pin, so checking `main` out at the pin
    changes no file: a local edit is still there, uncommitted."""
    leg = fresh / "spec"
    pin = rev(leg)
    edited = (leg / EDITED).read_bytes() + b"\nmy local line\n"
    (leg / EDITED).write_bytes(edited)

    result = bootstrap(fresh)
    assert moved_back(leg_main_ahead["ahead"], pin) in result.stdout, (
        result.stdout)
    assert head_ref(leg) == MAIN and rev(leg, MAIN) == pin
    assert (leg / EDITED).read_bytes() == edited
    assert git("status", "--porcelain", cwd=leg).stdout == f" M {EDITED}\n"


def test_a_fresh_leg_main_with_a_commit_of_its_own_is_not_moved(
        fresh, leg_main_ahead):
    """`main` checked out, a commit made, and the leg put back at the pin
    as `git submodule update` does: `main` holds a commit origin does not,
    so moving it would lose that commit. The refusal is main's, byte for
    byte."""
    leg = fresh / "spec"
    pin = rev(leg)
    git("checkout", "-q", "main", cwd=leg)
    git("commit", "-q", "--allow-empty", "-m", "mine", cwd=leg)
    mine = rev(leg)
    git("checkout", "-q", "--detach", pin, cwd=leg)

    result = bootstrap(fresh)
    assert result.returncode == 0, result.stderr + result.stdout
    assert not_moving(pin, mine) in result.stdout, result.stdout
    assert "moved back" not in result.stdout
    assert rev(leg, MAIN) == mine, "the commit is still on main"
    assert head_ref(leg) is None and rev(leg) == pin


def without_upstream(leg: Path) -> None:
    git("branch", "-q", "--unset-upstream", "main", cwd=leg)


def upstream_ref_missing(leg: Path) -> None:
    git("update-ref", "-d", "refs/remotes/origin/main", cwd=leg)


def upstream_local(leg: Path) -> None:
    """The upstream a LOCAL branch at the tip (`branch.main.remote` of
    `.`): no remote holds anything on its behalf."""
    git("branch", "-q", "other", "main", cwd=leg)
    git("branch", "-q", "--set-upstream-to=other", "main", cwd=leg)


def on_main(leg: Path) -> None:
    git("checkout", "-q", "main", cwd=leg)


def pinned_beside_main(leg: Path) -> None:
    """A pin `main` does not contain: a commit beside it, checked out and
    staged as the gitlink, as a bump to it would record it."""
    pin = rev(leg)
    beside = git("commit-tree", rev(leg, f"{pin}^{{tree}}"), "-p", pin,
                 "-m", "beside main", cwd=leg).stdout.strip()
    git("checkout", "-q", "--detach", beside, cwd=leg)
    git("add", "--", leg.name, cwd=leg.parent)


@pytest.mark.parametrize(
    "make, stays",
    [(without_upstream, "at the pin"), (upstream_ref_missing, "at the pin"),
     (upstream_local, "at the pin"), (on_main, "on main at its tip"),
     (pinned_beside_main, "at the pin")],
    ids=["no upstream", "upstream ref missing", "upstream a local branch",
         "HEAD on main", "diverged from the pin"])
def test_a_fresh_leg_main_nothing_vouches_for_is_not_moved(
        fresh, leg_main_ahead, make, stays):
    """Ahead of the pin and moved by nothing: with no upstream, one whose
    remote-tracking ref is not there, or a local branch as the upstream,
    nothing says the commits past the pin are held on a remote; with HEAD
    on `main`, the move would change the files checked out; and a `main`
    that does not contain the pin has diverged from it rather than moved
    past it. Each refusal is main's, byte for byte, and says where the
    checkout stays: at the pin, or on `main` where HEAD is on it (#533)."""
    leg = fresh / "spec"
    ahead = leg_main_ahead["ahead"]
    make(leg)
    pin = rev(fresh, ":spec")
    head, where = rev(leg), head_ref(leg)

    result = run_script(fresh / "scripts" / "bootstrap.py",
                        "--skip-validators", cwd=fresh)
    assert result.returncode == 0, result.stderr + result.stdout
    assert not_moving(pin, ahead, stays) in result.stdout, result.stdout
    assert "moved back" not in result.stdout
    assert rev(leg, MAIN) == ahead
    assert rev(leg) == head and head_ref(leg) == where


def test_a_failing_post_checkout_hook_is_not_called_a_refused_checkout(
        fresh, leg_main_ahead, tmp_path):
    """A post-checkout hook's exit status is the checkout's own, so a hook
    that fails after HEAD has moved makes `git checkout` exit non-zero over
    a checkout that happened. The line said git refused it, over a leg on
    `main` at the pin. HEAD is what is read now: the move is said, and the
    hook's words follow it."""
    leg = fresh / "spec"
    pin = rev(leg)

    result = run_script(fresh / "scripts" / "bootstrap.py",
                        "--skip-validators", cwd=fresh,
                        env=failing_post_checkout(tmp_path))
    assert result.returncode == 0, result.stderr + result.stdout
    assert moved_back(leg_main_ahead["ahead"], pin) + (
        "\n          checked out, and then git said:\n"
        "          post-checkout hook failed\n") in result.stdout, (
        result.stdout)
    assert "refused" not in result.stdout
    assert head_ref(leg) == MAIN and rev(leg, MAIN) == pin


def test_the_command_that_brings_the_branch_forward_is_shell_quoted(
        fresh, leg_main_ahead):
    """A leg at a path with a space, which only a hand-written manifest
    holds (scaffold and adopt refuse one). The printed command quotes it, as
    `scripts/family.py` quotes the commands it prints, and split the way a
    POSIX shell splits it, it runs and brings `main` forward."""
    git("mv", "spec", "my spec", cwd=fresh)
    manifest = fresh / "project.yaml"
    text = manifest.read_bytes()
    assert text.count(b'path: "spec"\n') == 1, text
    manifest.write_bytes(text.replace(b'path: "spec"\n',
                                      b'path: "my spec"\n'))
    leg = fresh / "my spec"
    pin = rev(leg)
    ahead = leg_main_ahead["ahead"]

    result = skip_validators(fresh)
    assert result.returncode == 0, result.stderr + result.stdout
    line = moved_back(ahead, pin, leg="my spec",
                      command="git -C 'my spec' merge --ff-only origin/main")
    assert line in result.stdout, result.stdout
    assert head_ref(leg) == MAIN and rev(leg, MAIN) == pin

    command = shlex.split(line.split("`")[1])
    assert command[:3] == ["git", "-C", "my spec"], command
    git(*command[1:], cwd=fresh)
    assert rev(leg, MAIN) == ahead


# --- the branch IS the pin: a leg detached off it is left where it is (#533) -

def neither(pin: str, head: str, place: str = "detached") -> str:
    """The two lines step (a) prints for a leg whose branch IS the pin and
    whose checkout is somewhere else, byte for byte as main prints them."""
    return (f"  [spec] spec: branch main is at the pin {pin[:12]}, and the "
            f"checkout is at {head[:12]} ({place}), which is neither\n"
            "          not moving the checkout off it. Keep any commit made "
            "there on a branch, check out the pin or the branch in the leg, "
            "and run bootstrap again.\n")


def branch_at_the_new_pin(root: Path, remotes: Path, tmp_path: Path,
                          branch: str) -> tuple[Path, str]:
    """A bump to a commit, and the tracking branch brought to it as a pull
    in the leg would: the leg DETACHED at the pin over a `main` that IS the
    pin, which is what `bump-leg.py --to` a branch's own tip leaves."""
    new = bumped(root, remotes, tmp_path, branch)
    leg = root / "spec"
    git("branch", "-q", "-f", "main", new, cwd=leg)
    assert head_ref(leg) is None and rev(leg, MAIN) == new == rev(leg)
    return leg, new


def detached_at_a_held_commit(leg: Path, old: str, where: str) -> str:
    """Detach the leg at a commit that is not the pin but that something
    holds, and return it: an ANCESTOR of the pin (`old`, which the branch
    held), or `origin/main` past the pin (a remote-tracking ref made to hold
    it, as `git submodule update --remote` leaves a leg)."""
    if where == "ancestor":
        git("checkout", "-q", "--detach", old, cwd=leg)
        return old
    git("commit", "-q", "--allow-empty", "-m", "the remote moved on", cwd=leg)
    here = rev(leg)
    git("update-ref", "refs/remotes/origin/main", here, cwd=leg)
    return here


def no_branch(pin: str, head: str) -> str:
    """The two lines step (a) prints for a leg detached at `head`, which is
    not the pin, when the tracking branch is not there, byte for byte as main
    prints them."""
    return (f"  [spec] spec: branch main does not exist, and the checkout is "
            f"at {head[:12]} (detached), which is not the pin {pin[:12]}\n"
            "          not moving the checkout off it. Keep any commit made "
            "there on a branch, check out the pin in the leg, and run "
            "bootstrap again.\n")


def has_no_branch(leg: Path) -> bool:
    return git("rev-parse", "--verify", "--quiet", MAIN, cwd=leg,
               check=False).returncode != 0


def test_a_commit_made_on_a_leg_detached_at_its_branch_tip_is_not_stranded(
        root, bootstrapped, tmp_path):
    """THE ISSUE'S CASE: `bump-leg.py --to` the branch's own tip, a commit
    made on the leg while it is detached there, then bootstrap. It checked
    `main` out and printed `on main at <pin>`, and the commit was on no
    branch, held by HEAD's reflog alone, with nothing said. The leg is left
    where it is, said, and exits 0 as every refusal in step (a) does."""
    leg, new = branch_at_the_new_pin(root, bootstrapped["remotes"], tmp_path,
                                     "advance-branch-tip")
    git("commit", "-q", "--allow-empty", "-m", "made on the detached leg",
        cwd=leg)
    made = rev(leg)

    result = bootstrap(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert neither(new, made) in result.stdout, result.stdout
    assert "[spec] spec: on main at" not in result.stdout
    assert head_ref(leg) is None and rev(leg) == made, (
        "the leg is still detached at the commit")
    assert rev(leg, MAIN) == new, "`main` is not moved"
    assert git("rev-list", "--count", f"{new}..{made}",
               cwd=leg).stdout.strip() == "1", "the commit is held there"

    git("checkout", "-q", "--detach", new, cwd=leg)
    again = skip_validators(root)
    assert f"  [spec] spec: on main at {new[:12]} (branch tip == pin)" in (
        again.stdout), "the way out the lines name works"
    assert head_ref(leg) == MAIN


def test_a_leg_detached_at_its_branch_tip_with_nothing_made_is_put_on_it(
        root, bootstrapped, tmp_path):
    """THE CONTROL: the same state with no commit made. Detached AT the pin
    is a checkout of the branch that loses nothing, and it is made."""
    leg, new = branch_at_the_new_pin(root, bootstrapped["remotes"], tmp_path,
                                     "advance-control")

    result = bootstrap(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"  [spec] spec: on main at {new[:12]} (branch tip == pin)\n" in (
        result.stdout), result.stdout
    assert "neither" not in result.stdout
    assert head_ref(leg) == MAIN and rev(leg) == new


def test_a_leg_on_another_branch_with_its_own_branch_at_the_pin_is_as_it_was(
        root, bootstrapped, tmp_path):
    """HEAD on ANOTHER branch is left as it always was: that branch holds
    its commits, so checking `main` out strands nothing, and the checkout
    is made. `fast_forward_to_pin` did not do the same for a branch BEHIND
    the pin until #603 (D1, option A of its checklist triage) made the two
    one rule: the T7 tests at the end of this module are this test's twins
    for a branch behind the pin."""
    leg, new = branch_at_the_new_pin(root, bootstrapped["remotes"], tmp_path,
                                     "advance-other-branch")
    git("checkout", "-q", "-b", "elsewhere", cwd=leg)
    git("commit", "-q", "--allow-empty", "-m", "work on elsewhere", cwd=leg)

    result = bootstrap(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"  [spec] spec: on main at {new[:12]} (branch tip == pin)\n" in (
        result.stdout), result.stdout
    assert head_ref(leg) == MAIN and rev(leg) == new
    assert rev(leg, "refs/heads/elsewhere") != new, "its commit is on it"


def test_a_stale_lock_over_a_leg_on_its_branch_says_nothing_to_check_out(
        root):
    """HEAD already on `main` at the pin, and a stale `index.lock`: git
    exits non-zero over a checkout that would have changed nothing. The line
    said `checked out, and then git said:` over a checkout that never
    happened. Git's words still follow, because the same lock blocks the
    person's next commit."""
    leg = root / "spec"
    pin = rev(leg)
    assert head_ref(leg) == MAIN and rev(leg, MAIN) == pin
    lock = lock_index(leg)

    result = skip_validators(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (f"  [spec] spec: on main at {pin[:12]} (branch tip == pin)\n"
            "          nothing to check out, and then git said:\n"
            ) in result.stdout, result.stdout
    assert "checked out, and then git said" not in result.stdout
    assert "refused" not in result.stdout, "not a refusal of anything"
    assert "index.lock" in result.stdout, "git's own words"
    assert head_ref(leg) == MAIN and rev(leg) == pin

    lock.unlink()
    again = skip_validators(root)
    assert f"  [spec] spec: on main at {pin[:12]} (branch tip == pin)\n" in (
        again.stdout), "once the lock is gone, nothing more is said"
    assert "then git said" not in again.stdout


def test_a_failing_hook_after_a_real_checkout_still_says_checked_out(
        root, tmp_path):
    """The ride-along changes only a checkout that moved nothing. A
    post-checkout hook that fails after HEAD moved from the pin onto the
    branch keeps `checked out, and then git said:`: it was checked out."""
    leg = root / "spec"
    pin = rev(leg)
    git("checkout", "-q", "--detach", pin, cwd=leg)

    result = run_script(root / "scripts" / "bootstrap.py",
                        "--skip-validators", cwd=root,
                        env=failing_post_checkout(tmp_path))
    assert result.returncode == 0, result.stderr + result.stdout
    assert (f"  [spec] spec: on main at {pin[:12]} (branch tip == pin)\n"
            "          checked out, and then git said:\n"
            "          post-checkout hook failed\n") in result.stdout, (
        result.stdout)
    assert head_ref(leg) == MAIN and rev(leg) == pin


def test_a_failing_hook_over_a_leg_already_on_its_branch_is_not_a_refusal(
        root, tmp_path):
    """HEAD already on `main` at the pin, and a post-checkout hook that
    fails: git runs it for a checkout that changes nothing, and exits
    non-zero. The line said `git refused`, which a failing hook is not, and
    before that `checked out`, which nothing was. Every cause of a non-zero
    exit over that state gets the one line that is true of all of them."""
    leg = root / "spec"
    pin = rev(leg)
    assert head_ref(leg) == MAIN and rev(leg, MAIN) == pin

    result = run_script(root / "scripts" / "bootstrap.py",
                        "--skip-validators", cwd=root,
                        env=failing_post_checkout(tmp_path))
    assert result.returncode == 0, result.stderr + result.stdout
    assert (f"  [spec] spec: on main at {pin[:12]} (branch tip == pin)\n"
            "          nothing to check out, and then git said:\n"
            "          post-checkout hook failed\n") in result.stdout, (
        result.stdout)
    assert "refused" not in result.stdout
    assert "checked out, and then git said" not in result.stdout
    assert head_ref(leg) == MAIN and rev(leg) == pin


# --- a leg detached off the pin is left where it is, whatever holds it ------

@pytest.mark.parametrize(
    "where", ["ancestor", "remote"],
    ids=["ancestor of the pin", "origin/main past the pin"])
def test_a_leg_detached_at_a_commit_its_branch_or_remote_holds_is_not_moved(
        root, bootstrapped, tmp_path, where):
    """Detached at an ANCESTOR of the pin (the branch holds it), or at
    `origin/main` past the pin (a remote-tracking ref holds it, as `git
    submodule update --remote` leaves a leg), with `main` AT the pin.
    Bootstrap used to check `main` out from both. Neither loses a commit,
    but a leg detached at a commit that is not the pin is left where it is
    and said, as the behind branch's is (`fast_forward_to_pin`), so the rule
    has no exception to explain."""
    old = rev(root / "spec")
    leg, new = branch_at_the_new_pin(root, bootstrapped["remotes"], tmp_path,
                                     f"advance-held-{where}")
    here = detached_at_a_held_commit(leg, old, where)

    result = bootstrap(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert neither(new, here) in result.stdout, result.stdout
    assert "[spec] spec: on main at" not in result.stdout
    assert head_ref(leg) is None and rev(leg) == here, "HEAD stays"
    assert rev(leg, MAIN) == new, "`main` is not moved"


def test_a_missing_tracking_branch_is_not_made_over_a_detached_commit(
        root):
    """THE SAME STRAND ON THE CREATE PATH: no `main` in the leg (a tracking
    branch that is not the remote's default, or one deleted), a commit made
    on the leg detached at the pin, then bootstrap. `checkout -b main <pin>`
    left the commit on no branch under `branch main created at <pin>`. The
    leg is left where it is, and said, in words true of a branch that is not
    there. Detached AT the pin the branch is created, as on a fresh clone."""
    leg = root / "spec"
    pin = rev(leg)
    git("checkout", "-q", "--detach", pin, cwd=leg)
    git("branch", "-q", "-D", "main", cwd=leg)
    git("commit", "-q", "--allow-empty", "-m", "made on the detached leg",
        cwd=leg)
    made = rev(leg)

    result = skip_validators(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert no_branch(pin, made) in result.stdout, result.stdout
    assert "created at" not in result.stdout
    assert head_ref(leg) is None and rev(leg) == made, "HEAD stays"
    assert has_no_branch(leg), "no branch is made"

    git("checkout", "-q", "--detach", pin, cwd=leg)
    again = skip_validators(root)
    assert f"  [spec] spec: branch main created at {pin[:12]}" in (
        again.stdout), again.stdout
    assert head_ref(leg) == MAIN and rev(leg) == pin


@pytest.mark.parametrize(
    "where", ["ancestor", "remote"],
    ids=["ancestor of the pin", "origin/main past the pin"])
def test_a_missing_branch_is_not_made_over_a_leg_detached_at_a_held_commit(
        root, bootstrapped, tmp_path, where):
    """The create path's twins of the two cases above: NO `main` in the leg,
    and the leg detached at an ancestor of the pin, or at `origin/main` past
    it. `checkout -b main <pin>` moved the leg onto the pin and made the
    branch there, as bootstrap once did for a branch that exists. Nothing is
    lost either way, and the rule is one: a leg detached at a commit that is
    not the pin is left where it is, with no branch made."""
    old = rev(root / "spec")
    new = bumped(root, bootstrapped["remotes"], tmp_path,
                 f"advance-missing-{where}")
    leg = root / "spec"
    here = detached_at_a_held_commit(leg, old, where)
    git("branch", "-q", "-D", "main", cwd=leg)

    result = skip_validators(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert no_branch(new, here) in result.stdout, result.stdout
    assert "created at" not in result.stdout
    assert head_ref(leg) is None and rev(leg) == here, "HEAD stays"
    assert has_no_branch(leg), "no branch is made"


def test_a_leg_whose_gitdir_is_gone_is_not_said_to_be_detached_off_the_pin(
        root):
    """A leg whose `.git` file names a gitdir that is not there: git can read
    no HEAD, so there is no commit to keep and no place to say the checkout
    is at. The guard read that as `?` and a detached HEAD, and told the
    person to check out the pin. The branch cannot be made, and the line says
    it could not, as it always did."""
    leg = root / "spec"
    pin = rev(leg)
    # Delete the gitfile before rewriting it: Git for Windows marks `.git`
    # HIDDEN (`core.hideDotFiles=dotGitOnly`), a gitfile as much as a
    # directory, and Windows refuses to open an existing hidden file for
    # overwrite (`CreateFile` with `CREATE_ALWAYS` is ACCESS_DENIED), so
    # `write_bytes` over it raises `PermissionError` there. `unlink` works.
    (leg / ".git").unlink()
    (leg / ".git").write_bytes(b"gitdir: ../.git/modules/gone\n")

    result = skip_validators(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (f"  [spec] spec: could not create branch 'main' at the pin "
            f"{pin[:12]}; leaving detached\n") in result.stdout, result.stdout
    assert "does not exist" not in result.stdout
    assert "which is not the pin" not in result.stdout
    assert "(detached)" not in result.stdout


# --- `not moving an existing branch` names where the checkout stays (#533) --

@pytest.mark.parametrize("make, place", [("commit", "detached"),
                                         ("branch", "on elsewhere")],
                         ids=["detached off the pin", "on another branch"])
def test_the_not_moving_line_names_a_checkout_that_is_neither(
        root, bootstrapped, tmp_path, make, place):
    """`main` holds a commit the pin lacks, and the leg stands neither on it
    nor detached at the pin: detached at a commit made after the bump, or on
    another branch. The line said `The checkout stays at the pin` over a
    checkout that was not there; it names the commit and the place."""
    leg = root / "spec"
    pin = rev(root, "HEAD:spec")
    git("commit", "-q", "--allow-empty", "-m", "local work", cwd=leg)
    mine = rev(leg)
    git("checkout", "-q", "--detach", pin, cwd=leg)
    new = bumped(root, bootstrapped["remotes"], tmp_path,
                 f"advance-stays-{make}")
    if make == "branch":
        git("checkout", "-q", "-b", "elsewhere", cwd=leg)
    git("commit", "-q", "--allow-empty", "-m", "made after the bump", cwd=leg)
    head = rev(leg)

    result = bootstrap(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert not_moving(new, mine, f"at {head[:12]} ({place})") in (
        result.stdout), result.stdout
    assert "stays at the pin" not in result.stdout
    assert rev(leg, MAIN) == mine and rev(leg) == head


def test_the_bump_prints_that_bootstrap_places_the_leg_or_says_why_not(
        root, bootstrapped, tmp_path):
    """`bump-leg.py` said `make bootstrap in the root re-places it on its
    tracking branch AT the new pin` after every bump. Since #490 bootstrap
    leaves a leg alone where placing it would lose a commit, and says why;
    the line says the same."""
    new = advance(bootstrapped["remotes"], tmp_path, "advance-printed")

    result = bump_spec(root, bootstrapped["remotes"], new)
    assert (f"  spec/ is left DETACHED at {new[:12]}; `make bootstrap` in the "
            "root puts it on its tracking branch AT the new pin, or says "
            "why not\n") in result.stdout, result.stdout
    assert "re-places" not in result.stdout


# --- T7: behind the pin, HEAD on another branch is placed as P9 is (#603) ---

#: A file made on `elsewhere`, which the checkout of `main` takes out again.
MINE = "ELSEWHERE.md"
#: What the line a leg's move off another branch adds starts with (#603).
LEFT = "the leg was "
#: What step (a) prints under git's own lines when git refuses a move.
NOTHING_ELSE = ("          nothing else is tried; the recorded pin is "
                "authoritative. Deal with what git said and run bootstrap "
                "again.\n")


def fast_forwarded(old: str, new: str) -> str:
    """The line step (a) prints when the spec leg's `main` is fast-forwarded,
    byte for byte as main prints it. `origin/main` is where the scaffold left
    it, at `old`: `advance` pushes every new commit to a branch of its own."""
    return (f"  [spec] spec: branch main fast-forwarded {old[:12]} -> "
            f"{new[:12]}, the pin; origin/main is {old[:12]}, which the pin "
            "deliberately does NOT follow\n")


def left_branch(other: str = "elsewhere", orphan: bool = False) -> str:
    """The line the T7 path prints under the `fast-forwarded` one when HEAD
    started on another branch, byte for byte as main prints it (#603): the
    leg left `other`, which keeps its commits (or has none yet, `orphan`),
    and is on `main` now. Nothing else prints it."""
    kept = ("a branch with no commit yet" if orphan
            else "which keeps its commits")
    return f"          the leg was on {other}, {kept}; it is on main now\n"


def moved_and_refused(old: str, new: str) -> str:
    """The first line of what step (a) prints when `main` moved to the pin
    and git then refused to check it out."""
    return (f"  [spec] spec: branch main moved {old[:12]} -> {new[:12]}, the "
            "pin, and git refused to check it out:\n")


def leg_files(leg: Path) -> dict[str, tuple[bytes, int]]:
    """Every file the leg's working tree holds but `.git`, with its bytes and
    its mtime, so a checkout that rewrote one shows."""
    return {path.relative_to(leg).as_posix():
            (path.read_bytes(), path.stat().st_mtime_ns)
            for path in sorted(leg.rglob("*"))
            if path.is_file() and ".git" not in path.relative_to(leg).parts}


def test_a_leg_on_another_branch_behind_the_pin_is_put_on_main_at_the_pin(
        root, bootstrapped, tmp_path):
    """T7, THE STATE THE BUMP LEAVES PLUS WORK ON ANOTHER BRANCH: the leg
    detached at the new pin over `main` at the old one, then `git checkout -b
    elsewhere` and a commit there. Bootstrap printed `which is neither` and
    moved nothing, while a `main` AT the pin was checked out from the same
    checkout (#603, D1). `elsewhere` holds its commit, so the move loses
    nothing: `main` goes to the pin, the leg goes onto it, `elsewhere` is
    not touched. Its twin detached off the pin keeps `which is neither`:
    `test_a_commit_made_on_the_detached_leg_is_not_left_behind`."""
    leg = root / "spec"
    old = rev(leg)
    new = bumped(root, bootstrapped["remotes"], tmp_path, "advance-t7")
    git("checkout", "-q", "-b", "elsewhere", cwd=leg)
    (leg / MINE).write_bytes(b"work on elsewhere\n")
    git("add", "--", MINE, cwd=leg)
    git("commit", "-q", "-m", "work on elsewhere", cwd=leg)
    mine = rev(leg)

    result = bootstrap(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert fast_forwarded(old, new) + left_branch() in result.stdout, (
        result.stdout)
    assert "neither" not in result.stdout
    assert NOT_MOVING not in result.stdout
    assert head_ref(leg) == MAIN and rev(leg) == new == rev(leg, MAIN)
    assert rev(leg, "refs/heads/elsewhere") == mine, "`elsewhere` is untouched"
    assert git("rev-list", "--count", f"{new}..{mine}",
               cwd=leg).stdout.strip() == "1", "and holds its commit"
    assert not (leg / MINE).exists(), "the checkout took its file out"
    assert (leg / ADDED).is_file(), "and put the pin's files in"
    assert git("status", "--porcelain", cwd=leg).stdout == ""
    assert rev(root, "HEAD:spec") == new, "the pin is not moved"


def test_a_leg_on_another_branch_at_the_pin_is_put_on_main_and_changes_no_file(
        root, bootstrapped, tmp_path):
    """T7 with `elsewhere` EXACTLY AT THE PIN, no commit of its own: the same
    result, and as the checkout from `elsewhere` to `main` is between two
    trees that are one, no file in the leg is rewritten."""
    leg = root / "spec"
    old = rev(leg)
    new = bumped(root, bootstrapped["remotes"], tmp_path, "advance-t7-at-pin")
    git("checkout", "-q", "-b", "elsewhere", cwd=leg)
    assert rev(leg) == new == rev(leg, "refs/heads/elsewhere")
    before = leg_files(leg)

    result = bootstrap(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert fast_forwarded(old, new) + left_branch() in result.stdout, (
        result.stdout)
    assert "neither" not in result.stdout
    assert head_ref(leg) == MAIN and rev(leg) == new == rev(leg, MAIN)
    assert rev(leg, "refs/heads/elsewhere") == new, "`elsewhere` stays"
    assert leg_files(leg) == before, "no file in the leg changes"
    assert git("status", "--porcelain", cwd=leg).stdout == ""


def test_the_branch_a_leg_is_on_is_not_the_one_that_moves_to_the_pin(
        root, bootstrapped, tmp_path):
    """T7 from a branch that is ITSELF behind the pin: `elsewhere` made at
    the old pin, with `main`, and HEAD on it. The branch fast-forwarded is
    the TRACKING branch, which is a `branch -f`, and never the one HEAD is on,
    which a `merge --ff-only` from there would move: `elsewhere` stays at the
    old pin, as a person left it."""
    leg = root / "spec"
    old = rev(leg)
    new = bumped(root, bootstrapped["remotes"], tmp_path, "advance-t7-behind")
    git("checkout", "-q", "-b", "elsewhere", "main", cwd=leg)
    assert rev(leg) == old and not (leg / ADDED).exists()

    result = bootstrap(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert rev(leg, "refs/heads/elsewhere") == old, "`elsewhere` is not moved"
    assert fast_forwarded(old, new) + left_branch() in result.stdout, (
        result.stdout)
    assert head_ref(leg) == MAIN and rev(leg) == new == rev(leg, MAIN)
    assert (leg / ADDED).is_file(), "the pin's files are checked out"
    assert git("status", "--porcelain", cwd=leg).stdout == ""


def test_a_checkout_off_another_branch_git_refuses_leaves_main_at_the_pin(
        root, bootstrapped, tmp_path):
    """T7, REFUSED AFTER `branch -f` WORKED. From the pin the checkout of
    `main` changes no file, so a local edit never stops it; from `elsewhere`
    it changes the files the two differ in, and a local edit to one of them
    stops it. `elsewhere` is at the old pin here, so the edit is to a file
    the pin changes. `main` is left at the pin and never put back, HEAD stays
    on `elsewhere` with the edit intact, and the next run meets the branch AT
    the pin (`place_at_pin`), which refuses the same way until the edit is
    gone."""
    leg = root / "spec"
    old = rev(leg)
    new = bumped(root, bootstrapped["remotes"], tmp_path, "advance-t7-refused",
                 touch=EDITED)
    git("checkout", "-q", "-b", "elsewhere", "main", cwd=leg)
    edited = (leg / EDITED).read_bytes() + b"\nmy local line\n"
    (leg / EDITED).write_bytes(edited)

    result = skip_validators(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert moved_and_refused(old, new) in result.stdout, result.stdout
    assert f"          {EDITED}\n" in result.stdout, "git names the file"
    assert NOTHING_ELSE in result.stdout
    assert "fast-forwarded" not in result.stdout
    assert "neither" not in result.stdout
    assert LEFT not in result.stdout, "HEAD did not leave `elsewhere`"
    assert head_ref(leg) == "refs/heads/elsewhere" and rev(leg) == old
    assert rev(leg, MAIN) == new, "`main` stays at the pin"
    assert (leg / EDITED).read_bytes() == edited, "the edit is intact"
    assert git("status", "--porcelain", cwd=leg).stdout == f" M {EDITED}\n"

    second = skip_validators(root)
    assert (f"  [spec] spec: branch main is at the pin {new[:12]}, and git "
            "refused to check it out:\n") in second.stdout, second.stdout
    assert head_ref(leg) == "refs/heads/elsewhere" and rev(leg, MAIN) == new
    assert LEFT not in second.stdout

    git("checkout", "-q", "--", EDITED, cwd=leg)
    again = skip_validators(root)
    assert f"  [spec] spec: on main at {new[:12]} (branch tip == pin)\n" in (
        again.stdout), again.stdout
    assert LEFT not in again.stdout, "P9 says nothing of the branch it left"
    assert head_ref(leg) == MAIN and rev(leg) == new


def test_a_branch_another_worktree_has_checked_out_is_not_moved_from_elsewhere(
        root, bootstrapped, tmp_path):
    """T7 with `branch -f` REFUSED: `main` is checked out in a second
    worktree of the leg, and git will not move a branch another worktree
    holds. Nothing moves, HEAD stays on `elsewhere`, the other worktree still
    matches its HEAD, and the line is the one `main` has always printed."""
    leg = root / "spec"
    old = rev(leg)
    new = bumped(root, bootstrapped["remotes"], tmp_path, "advance-t7-wt")
    git("checkout", "-q", "-b", "elsewhere", cwd=leg)
    held = tmp_path / "held"
    git("worktree", "add", str(held), "main", cwd=leg)

    result = bootstrap(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (f"  [spec] spec: branch main tip {old[:12]} is behind the PIN "
            f"{new[:12]}, and git refused to move it:\n") in result.stdout, (
        result.stdout)
    assert NOTHING_ELSE in result.stdout
    assert "neither" not in result.stdout
    assert LEFT not in result.stdout, "nothing moved"
    assert rev(leg, MAIN) == old
    assert head_ref(leg) == "refs/heads/elsewhere" and rev(leg) == new
    assert head_ref(held) == MAIN and rev(held) == old
    assert git("status", "--porcelain", cwd=held).stdout == ""


@pytest.mark.parametrize(
    "where, blocked",
    [("behind", False), ("at", False), ("behind", True), ("at", True)],
    ids=["behind, free", "at the pin, free", "behind, a file in the way",
         "at the pin, a file in the way"])
def test_a_leg_on_a_branch_with_no_commit_yet_is_placed_as_on_any_branch(
        root, bootstrapped, tmp_path, where, blocked):
    """HEAD on a branch with NO COMMIT YET (`git switch --orphan`): there is
    no commit to keep, and `place_at_pin` checks `main` out from it, so a
    `main` behind the pin does the same (#603). The four lines side by side:
    free, `main` goes to the pin and the leg onto it, T7 says the leg left a
    branch with no commit yet and P9 says nothing of it; with an untracked
    file in the way, git refuses the checkout, HEAD stays on the unborn
    branch, `main` is at the pin and nothing is said of the leg leaving."""
    old = rev(root / "spec")
    advanced = f"advance-orphan-{where}-{'blocked' if blocked else 'free'}"
    if where == "behind":
        leg = root / "spec"
        new = bumped(root, bootstrapped["remotes"], tmp_path, advanced)
    else:
        leg, new = branch_at_the_new_pin(root, bootstrapped["remotes"],
                                         tmp_path, advanced)
    git("switch", "-q", "--orphan", "orphan", cwd=leg)
    assert head_ref(leg) == "refs/heads/orphan"
    assert git("rev-parse", "--verify", "--quiet", "HEAD", cwd=leg,
               check=False).returncode != 0, "no commit yet"
    if blocked:
        (leg / ADDED).write_bytes(b"mine\n")

    result = bootstrap(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "neither" not in result.stdout
    assert rev(leg, MAIN) == new
    if blocked:
        assert ((moved_and_refused(old, new) if where == "behind" else
                 f"  [spec] spec: branch main is at the pin {new[:12]}, and "
                 "git refused to check it out:\n") in result.stdout), (
            result.stdout)
        assert ADDED in result.stdout, "git's own words name the file"
        assert NOTHING_ELSE in result.stdout
        assert head_ref(leg) == "refs/heads/orphan"
        assert (leg / ADDED).read_bytes() == b"mine\n"
        assert LEFT not in result.stdout
    else:
        assert ((fast_forwarded(old, new) + left_branch("orphan", True)
                 if where == "behind" else
                 f"  [spec] spec: on main at {new[:12]} (branch tip == pin)\n")
                in result.stdout), result.stdout
        assert (LEFT in result.stdout) == (where == "behind")
        assert head_ref(leg) == MAIN and rev(leg) == new
        assert git("status", "--porcelain", cwd=leg).stdout == ""


def test_a_failing_hook_after_the_move_off_another_branch_is_said_after_it(
        root, bootstrapped, tmp_path):
    """T7 with a post-checkout hook that fails after HEAD has moved: `git
    checkout` exits non-zero over a checkout that happened, so the move is
    said, the line that says the leg left `elsewhere` follows it, and the
    hook's words follow that, as `place_at_pin`'s do (#533). Nothing is
    called a refusal. Without the `_say_after` of `fast_forward_to_pin`, the
    hook's words are not said at all, and no other test sees it."""
    leg = root / "spec"
    old = rev(leg)
    new = bumped(root, bootstrapped["remotes"], tmp_path, "advance-t7-hook")
    git("checkout", "-q", "-b", "elsewhere", "main", cwd=leg)
    assert rev(leg) == old

    result = run_script(root / "scripts" / "bootstrap.py",
                        "--skip-validators", cwd=root,
                        env=failing_post_checkout(tmp_path))
    assert result.returncode == 0, result.stderr + result.stdout
    assert (fast_forwarded(old, new) + left_branch()
            + "          checked out, and then git said:\n"
            "          post-checkout hook failed\n") in result.stdout, (
        result.stdout)
    assert "refused" not in result.stdout
    assert head_ref(leg) == MAIN and rev(leg) == new == rev(leg, MAIN)
    assert rev(leg, "refs/heads/elsewhere") == old


def test_the_branch_the_leg_left_is_spelled_in_the_line_that_names_it(
        root, bootstrapped, tmp_path):
    """The line that says the leg left a branch prints the BRANCH'S name, which
    is a person's, not the manifest's, and git accepts U+2028 in one (#391):
    it is spelled, as the tracking branch's is."""
    leg = root / "spec"
    old = rev(leg)
    new = bumped(root, bootstrapped["remotes"], tmp_path, "advance-t7-spelled")
    git("checkout", "-q", "-b", "el\u2028se", cwd=leg)

    result = bootstrap(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "\u2028" not in result.stdout, result.stdout
    assert fast_forwarded(old, new) + left_branch(r"el\u2028se") in (
        result.stdout), result.stdout
    assert head_ref(leg) == MAIN and rev(leg) == new
