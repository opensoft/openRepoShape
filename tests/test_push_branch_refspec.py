# SPDX-License-Identifier: Apache-2.0
"""The tracking branch is pushed by its FULL refname, so `--tracking-branch
+x` scaffolds and initialises instead of dying at the push (#421).

WHAT WAS WRONG. `scaffold-project.py` (each leg, then the assembly root) and
`scripts/family.py init` (the holder) pushed `git push -q -u origin <branch>`.
A bare `<branch>` there is a REFSPEC, and a leading `+` in a refspec means
FORCE, so `--tracking-branch +x`, a name `git check-ref-format --branch`
accepts and `git init -b` creates, was read as the forced push of a local
branch `x`:

    git push -q -u origin +x
    error: src refspec x does not match any

`checked_value`'s alphabet admits `+` and `branch_problem` (#283) asks git,
which accepts a leading one, so the name passed `--dry-run` (exit 0) and every
bare remote, or `gh repo create`'s repository, existed before the first push
died: three repositories with no commit, for the scaffold.

THE FIX the issue offered and this file holds: push `HEAD:refs/heads/<branch>`,
which names both sides in full (`adopt-project.py` already pushes that way).
The other, refusing a leading `+` in `branch_problem`, was measured too: it
refuses `+x`, `+main`, `+`, `++` and `+.inf`, which git creates and which
push without trouble by full refname, and its sentence ("not a branch name git
will create") is false for them. Pushing by full refname makes every name git
accepts work end to end, so `branch_problem` is untouched.

WHAT IS PINNED HERE, on the local route (`--local-remote-dir`, no `gh`, no
network), through the real tools:
  * every name that begins with `+`, and each control, leaves EVERY bare
    remote holding exactly `refs/heads/<name>`, HEAD on it, and each work
    clone tracking `origin/<name>` (`-u` is kept);
  * `--dry-run` still passes for `+x` and `+main` and creates nothing, and
    the real run after it now finishes: the pair the issue's table shows
    disagreeing;
  * the recursive clone the NEXT STEPS name checks out `+x` with both legs,
    and `scripts/bootstrap.py` there puts each leg on `+x` at its pin;
  * a name that merely LOOKS like a full refname (`refs/heads/x`) is still
    the branch of that name, nested, as before: the full-refname push does
    not take it for a ref;
  * `--reuse-empty-repo` into remotes created empty on `+x` pushes the same;
  * `--no-push` still makes no push.
The same through `family.py init`: the holder's remote, its work clone's
upstream, a clone of it, a dry run then a real run, and a reuse.
"""

from __future__ import annotations

import pytest

from conftest import cloned_just_pushed, git, run_script
from test_tracking_branch_ref import (assert_family_made_nothing,
                                      assert_nothing_was_made, family_init,
                                      scaffold)

#: Names git accepts that BEGIN with `+`: the issue's own `+x` and `+main`, the
#: one it names in the refusal option (`+.inf`), and the two that are nothing
#: but the plus, which share the rule and have no letter to hide behind.
PLUS_NAMES = ["+x", "+main", "+.inf", "+", "++"]

#: Names that worked before and must not move: the issue's controls, a plus
#: that does not begin the name (a refspec reads only a leading one), and a
#: name that looks like a full refname, which git keeps as a nested branch.
CONTROLS = ["x", "main", "a/+b", "x+y", "refs/heads/x"]

NAMES = [*PLUS_NAMES, *CONTROLS]

ROLES = {"assembly": "Atlas", "spec": "Atlas-spec", "code": "Atlas-code"}


def refs(bare) -> list[str]:
    """Every ref a bare remote holds, by full name."""
    return git("for-each-ref", "--format=%(refname)",
               cwd=bare).stdout.split()


def head_of(bare) -> str:
    return git("symbolic-ref", "HEAD", cwd=bare).stdout.strip()


def upstream(work) -> str:
    return git("rev-parse", "--abbrev-ref", "@{upstream}",
               cwd=work).stdout.strip()


def assert_scaffold_pushed(tmp_path, name: str) -> None:
    """All three remotes hold the branch and nothing else; each work clone
    tracks it."""
    for role, repository in ROLES.items():
        bare = tmp_path / "remotes" / f"{repository}.git"
        assert refs(bare) == [f"refs/heads/{name}"], (
            f"{role} remote holds {refs(bare)}")
        assert head_of(bare) == f"refs/heads/{name}"
        assert upstream(tmp_path / "work" / repository) == f"origin/{name}", (
            f"{role} work clone does not track origin/{name}")


# --- scaffold-project.py ------------------------------------------------------

@pytest.mark.parametrize("name", NAMES)
def test_every_remote_holds_the_branch_and_each_clone_tracks_it(
        tmp_path, name):
    """THE ISSUE'S REPRODUCTION, `+x` and `+main` among the names: on `main`
    the real run exited 2 at `git push -q -u origin +x` (`+main`: `... origin
    +main`), the first leg's push, with three bare remotes holding no ref."""
    result = scaffold(tmp_path, f"--tracking-branch={name}")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "REFUSED" not in result.stderr
    assert_scaffold_pushed(tmp_path, name)


@pytest.mark.parametrize("name", ["+x", "+main"])
def test_a_dry_run_that_passes_is_followed_by_a_real_run_that_finishes(
        tmp_path, name):
    """The disagreement the issue's table shows: `--dry-run` exit 0, then the
    real run dead at the push. A dry run creates nothing; the run that follows
    it, with the same arguments, now ends as the dry run said it would."""
    planned = scaffold(tmp_path, f"--tracking-branch={name}", dry_run=True)
    assert planned.returncode == 0, planned.stderr + planned.stdout
    assert "--dry-run: nothing was created." in planned.stdout
    assert "push         yes" in planned.stdout
    assert_nothing_was_made(tmp_path)

    real = scaffold(tmp_path, f"--tracking-branch={name}")
    assert real.returncode == 0, real.stderr + real.stdout
    assert_scaffold_pushed(tmp_path, name)


def test_the_recursive_clone_of_a_plus_branch_checks_it_out_and_bootstraps(
        tmp_path):
    """What the scaffold's own NEXT STEPS tell a person to run: a recursive
    clone of the root, then `make bootstrap`. The clone lands on `+x` with
    both legs populated at the commits the root pins (a `-` before a
    submodule's commit in `git submodule status` is an empty mount), and
    bootstrap puts each leg on `+x` at its pin."""
    result = scaffold(tmp_path, "--tracking-branch=+x")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "puts each leg on `+x` AT its pinned commit" in result.stdout

    clone = cloned_just_pushed(tmp_path / "remotes" / "Atlas.git",
                               tmp_path / "clones" / "Atlas")
    assert git("rev-parse", "--abbrev-ref", "HEAD",
               cwd=clone).stdout.strip() == "+x"
    status = git("submodule", "status", cwd=clone).stdout.splitlines()
    assert len(status) == 2 and not any(line[0] in "-+U" for line in status), (
        status)

    booted = run_script(clone / "scripts" / "bootstrap.py", cwd=clone)
    assert booted.returncode == 0, booted.stderr + booted.stdout
    assert "bootstrap ok" in booted.stdout
    for leg in ("spec", "code"):
        assert f"[{leg}] {leg}: on +x at " in booted.stdout, booted.stdout


def test_a_full_refname_push_does_not_take_a_refname_looking_name_for_a_ref(
        tmp_path):
    """`refs/heads/x` is a branch name git accepts, and its branch is
    `refs/heads/refs/heads/x`. Pushed as `HEAD:refs/heads/refs/heads/x` it
    stays that, in every remote: not `refs/heads/x`, which a push that took it
    for a ref would have made."""
    result = scaffold(tmp_path, "--tracking-branch=refs/heads/x")
    assert result.returncode == 0, result.stderr + result.stdout
    for repository in ROLES.values():
        bare = tmp_path / "remotes" / f"{repository}.git"
        assert refs(bare) == ["refs/heads/refs/heads/x"]
        # `show-ref --verify` is exact; `rev-parse` would find the nested one.
        assert git("show-ref", "--verify", "-q", "refs/heads/x", cwd=bare,
                   check=False).returncode != 0


def reserve_empty(tmp_path, *repositories: str, branch: str) -> None:
    """Each bare repository named, made EMPTY with HEAD on `branch`: the
    reserved names `--reuse-empty-repo` takes."""
    for repository in repositories:
        git("init", "-q", "--bare", "-b", branch,
            str(tmp_path / "remotes" / f"{repository}.git"), cwd=tmp_path)


def test_a_reused_empty_remote_is_pushed_to_by_the_same_full_refname(tmp_path):
    """`--reuse-empty-repo` creates nothing, so the push is the only thing
    that can fail, and with the bare spelling it failed for `+x` exactly as it
    did without the flag."""
    (tmp_path / "remotes").mkdir()
    reserve_empty(tmp_path, *ROLES.values(), branch="+x")
    result = scaffold(tmp_path, "--tracking-branch=+x", "--reuse-empty-repo")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "(already there, zero commits)" in result.stdout
    assert_scaffold_pushed(tmp_path, "+x")


def test_no_push_still_pushes_nothing_for_a_plus_branch(tmp_path):
    """`--no-push` skips the three pushes, whatever the name: every remote
    exists, empty, with HEAD on the branch, and the work clones are on it."""
    result = scaffold(tmp_path, "--tracking-branch=+x", "--no-push")
    assert result.returncode == 0, result.stderr + result.stdout
    for repository in ROLES.values():
        bare = tmp_path / "remotes" / f"{repository}.git"
        assert refs(bare) == [] and head_of(bare) == "refs/heads/+x"
        assert git("rev-parse", "--abbrev-ref", "HEAD",
                   cwd=tmp_path / "work" / repository).stdout.strip() == "+x"


# --- scripts/family.py init ---------------------------------------------------

HOLDER = "Contoso"


def assert_family_pushed(tmp_path, name: str) -> None:
    bare = tmp_path / "remotes" / f"{HOLDER}.git"
    assert refs(bare) == [f"refs/heads/{name}"], (
        f"the holder holds {refs(bare)}")
    assert head_of(bare) == f"refs/heads/{name}"
    work = tmp_path / "into" / HOLDER / HOLDER
    assert upstream(work) == f"origin/{name}"


@pytest.mark.parametrize("name", NAMES)
def test_family_init_pushes_the_holder_on_the_branch_and_the_clone_tracks_it(
        tmp_path, name):
    """The issue's second route: on `main`, `family.py init
    --tracking-branch +x` exited 2 at `git push -q -u origin +x` once the
    holder's remote existed."""
    result = family_init(tmp_path, f"--tracking-branch={name}")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "REFUSED" not in result.stderr
    assert_family_pushed(tmp_path, name)


@pytest.mark.parametrize("name", ["+x", "+main"])
def test_a_family_dry_run_that_passes_is_followed_by_a_real_init_that_finishes(
        tmp_path, name):
    planned = family_init(tmp_path, f"--tracking-branch={name}", dry_run=True)
    assert planned.returncode == 0, planned.stderr + planned.stdout
    assert "--dry-run: nothing was created." in planned.stdout
    assert_family_made_nothing(tmp_path)

    real = family_init(tmp_path, f"--tracking-branch={name}")
    assert real.returncode == 0, real.stderr + real.stdout
    assert_family_pushed(tmp_path, name)


def test_a_clone_of_a_plus_holder_checks_out_the_branch(tmp_path):
    result = family_init(tmp_path, "--tracking-branch=+x")
    assert result.returncode == 0, result.stderr + result.stdout
    clone = cloned_just_pushed(tmp_path / "remotes" / f"{HOLDER}.git",
                               tmp_path / "clones" / HOLDER)
    assert git("rev-parse", "--abbrev-ref", "HEAD",
               cwd=clone).stdout.strip() == "+x"


def test_a_reused_empty_holder_is_pushed_to_by_the_same_full_refname(tmp_path):
    (tmp_path / "remotes").mkdir()
    reserve_empty(tmp_path, HOLDER, branch="+x")
    result = family_init(tmp_path, "--tracking-branch=+x",
                         "--reuse-empty-repo")
    assert result.returncode == 0, result.stderr + result.stdout
    holder = tmp_path / "remotes" / f"{HOLDER}.git"
    assert f"reuse {holder} (zero commits)" in result.stdout
    assert_family_pushed(tmp_path, "+x")
