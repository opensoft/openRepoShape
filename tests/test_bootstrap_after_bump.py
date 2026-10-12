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

THE RULE NOW. A tracking branch whose tip is an ancestor of the pin is
fast-forwarded to it from the two checkouts that state comes in: detached at
the pin, which is what `bump-leg.py` leaves, and on the branch itself. A
branch holding a commit the pin lacks, ahead or diverged, is still never
moved and keeps its message. A checkout that is neither is not moved off. A
move git refuses is said in git's words, and nothing else moves.

EACH TEST GOES THE WAY A PERSON DOES: a scaffold into bare repositories on
disk, cloned recursively and bootstrapped, so each leg is on `main` at its
pin; a new commit pushed to the spec leg's remote; a branch in the root,
`bump-leg.py`, then `bootstrap.py` again. The scaffold is this module's own,
not the session's, because every test pushes a commit to the spec remote,
each to a branch of its own so that no test sees another's. No bash and no
`gh`: every step is git or one of the Python tools, so the module runs
unchanged on Linux, macOS and Windows.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from conftest import (FILE_PROTOCOL, ORG, PROJECT, REPO, SCAFFOLD, git,
                      run_script)

BUMP = REPO / "scripts" / "bump-leg.py"
MAIN = "refs/heads/main"
NOT_MOVING = "not moving an existing branch"
REFUSED = "and git refused to move it:"
#: The file the new leg commit adds, and so the one an untracked copy of
#: blocks a fast-forward on.
ADDED = "NEW-CONTRACT.md"


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
    clone = base / "clone" / PROJECT
    git(*FILE_PROTOCOL, "clone", "-q", "--recurse-submodules",
        str(remotes / f"{PROJECT}.git"), str(clone), cwd=base)
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


def bumped(root: Path, remotes: Path, tmp_path: Path, branch: str) -> str:
    """A new commit on the spec leg's REMOTE, then `bump-leg.py` to it from
    a branch of the root, exactly as AGENTS.md has it. Returns the commit.

    The commit is pushed to `branch` rather than to `main`, so the remote's
    `main` stays where every copy of the clone has it; `bump-leg.py` asks
    only that some branch of the remote contains the commit.
    """
    work = tmp_path / "spec-work"
    git("clone", "-q", str(remotes / f"{PROJECT}-spec.git"), str(work),
        cwd=tmp_path)
    (work / ADDED).write_bytes(b"# a contract the leg gained\n")
    git("add", "--", ADDED, cwd=work)
    git("commit", "-q", "-m", "Advance the spec leg", cwd=work)
    git("push", "-q", "origin", f"HEAD:refs/heads/{branch}", cwd=work)
    new = rev(work)
    git("checkout", "-q", "-b", "bump/spec", cwd=root)
    result = run_script(BUMP, "--root", str(root), "--leg", "spec", "--to",
                        new, "--local-remote-dir", str(remotes))
    assert result.returncode == 0, result.stderr + result.stdout
    assert head_ref(root / "spec") is None, "bump-leg.py leaves it detached"
    assert rev(root / "spec") == new
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
    assert text.count(b"tracking_branch: main\n") == 1, text
    manifest.write_bytes(text.replace(b"tracking_branch: main\n",
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
