# SPDX-License-Identifier: Apache-2.0
"""The options of `clone_just_pushed` and `cloned_just_pushed` (#544).

#467 added `clone_just_pushed` for two fixtures. #544 moved every other test
that cloned a just-pushed local remote by its plain path onto it, and those
tests clone in the ways this file asks of the helper: without the submodules,
as a bare copy, with `-c` for the one command, with variables of their own,
and at a branch. Each case is one of those, and each case that makes a clone
asks the one thing the helper is for of it: the clone's store holds a pack and
no loose object, which a clone that walked the remote's own files would not
(`assert_store_read_through_git`). The option itself is asked of git beside
it, and the last case is the clone that fails.
"""

from __future__ import annotations

import os

import pytest

from conftest import (PROJECT, assert_read_through_git,
                      assert_store_read_through_git, clone_just_pushed,
                      cloned_just_pushed, git)


@pytest.fixture
def remote(scaffolded):
    """The bare remote the session's scaffold pushed the root to."""
    return scaffolded["remotes"] / f"{PROJECT}.git"


def test_a_recursive_clone_holds_the_root_and_both_legs_as_packs(remote,
                                                                 tmp_path):
    clone = cloned_just_pushed(remote, tmp_path / "clone")
    assert_read_through_git(clone)
    assert any((clone / "spec").iterdir()), "the mount was not checked out"


def test_without_the_submodules_the_mounts_stay_empty(remote, tmp_path):
    clone = cloned_just_pushed(remote, tmp_path / "clone", recurse=False)
    assert_store_read_through_git(clone, "the root")
    assert not any((clone / "spec").iterdir()), "the mount was checked out"
    assert not any((clone / "code").iterdir()), "the mount was checked out"


def test_a_bare_copy_is_bare_and_was_read_through_git(remote, tmp_path):
    copy = cloned_just_pushed(remote, tmp_path / "copy.git", bare=True)
    assert git("rev-parse", "--is-bare-repository",
               cwd=copy).stdout.strip() == "true"
    assert_store_read_through_git(copy, "the bare copy")


def test_a_branch_is_the_one_checked_out(remote, tmp_path):
    clone = cloned_just_pushed(remote, tmp_path / "clone", "main")
    assert_read_through_git(clone)
    assert git("rev-parse", "--abbrev-ref", "HEAD",
               cwd=clone).stdout.strip() == "main"


def test_a_branch_the_remote_lacks_fails_the_clone(remote, tmp_path):
    """`-b` reaches git: `main` is the default branch, so the case above
    passes without it, and a branch no remote has is refused only by git."""
    asked = clone_just_pushed(remote, tmp_path / "x", "no-such-branch")
    assert asked.returncode != 0, asked.stderr
    assert "no-such-branch" in asked.stderr, asked.stderr
    with pytest.raises(AssertionError, match="no-such-branch"):
        cloned_just_pushed(remote, tmp_path / "x", "no-such-branch")


def test_config_and_env_reach_the_one_command_and_nothing_is_stored(
        remote, tmp_path):
    """`clone.defaultRemoteName` is read by `git clone` and is the name its
    remote is given, so each of the two ways of passing it shows in the clone.
    The `url.<base>.insteadOf` the helper adds is a `-c` too, and must not be
    stored: the clone's `origin` keeps the plain path it was given."""
    by_config = cloned_just_pushed(
        remote, tmp_path / "by-config", recurse=False,
        config=["-c", "clone.defaultRemoteName=by-config"])
    assert_store_read_through_git(by_config, "the clone made with `config`")
    assert git("remote", cwd=by_config).stdout.split() == ["by-config"]
    # APPENDED to what the environment holds, as `command_scope` does in
    # `test_adopt_ignored_shape_files.py`: the Windows job sets two entries
    # of its own there, and `GIT_CONFIG_COUNT=1` would drop them.
    held = int(os.environ.get("GIT_CONFIG_COUNT") or 0)
    by_env = cloned_just_pushed(
        remote, tmp_path / "by-env", recurse=False,
        env={"GIT_CONFIG_COUNT": str(held + 1),
             f"GIT_CONFIG_KEY_{held}": "clone.defaultRemoteName",
             f"GIT_CONFIG_VALUE_{held}": "by-env"})
    assert_store_read_through_git(by_env, "the clone made with `env`")
    assert git("remote", cwd=by_env).stdout.split() == ["by-env"]
    stored = git("config", "--local", "--list", cwd=by_env).stdout
    assert "insteadof" not in stored.lower(), stored
    assert git("remote", "get-url", "by-env", cwd=by_env).stdout.strip() \
        == str(remote)


def test_a_clone_that_fails_fails_the_test_and_says_why(tmp_path):
    missing = tmp_path / "remotes" / "Nothing.git"
    assert clone_just_pushed(missing, tmp_path / "clone").returncode != 0
    with pytest.raises(AssertionError, match="git clone of .* failed"):
        cloned_just_pushed(missing, tmp_path / "clone")
