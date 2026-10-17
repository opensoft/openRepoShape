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

#662 wrote the rewrite those clones carry once (`insteadof_prefixes`, its
`(key, prefix)` entries and its `-c` arguments) and gave its other two users
the same list: `read_through_git`, which puts it in the environment of a
pasted line, and `submodule_update_through_git`, for the `--init` of a mount a
test brings up after the clone. The cases at the end ask git what each form
does to a plain path, with `git ls-remote --get-url`, which expands a URL as a
fetch would and talks to nothing.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from conftest import (FILE_PROTOCOL, PROJECT, assert_read_through_git,
                      assert_store_read_through_git, clone_just_pushed,
                      cloned_just_pushed, git, insteadof_args,
                      insteadof_entries, insteadof_prefixes, read_through_git,
                      submodule_update_through_git)


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


# --- the rewrite, written once (#662) ----------------------------------------

def spellings(directory: Path) -> set[str]:
    """The prefixes of an existing `directory` as a person would write them:
    the system's separator after it, and a slash. One on POSIX, two on
    Windows. Written out here and not read from the helper."""
    return {str(directory) + os.sep, directory.as_posix() + "/"}


def get_url(url: str, *config: str, env: dict | None = None,
            cwd: Path) -> str:
    """What git makes of `url` as a fetch would, `insteadOf` rewrites
    included, and talks to nothing."""
    return subprocess.run(["git", *config, "ls-remote", "--get-url", url],
                          cwd=str(cwd), capture_output=True, text=True,
                          check=True, env=env).stdout.strip()


@pytest.fixture
def remotes(tmp_path) -> Path:
    directory = tmp_path / "remotes"
    directory.mkdir()
    return directory


@pytest.mark.parametrize("typed", [False, True], ids=["resolved", "typed"])
@pytest.mark.parametrize("trailing", ["", "/", os.sep],
                         ids=["none", "slash", "separator"])
def test_a_directory_is_named_with_a_separator_after_it_given_or_not(
        remotes, typed, trailing):
    """The prefix ends with a separator whether the directory was given with
    one or without, so a rewrite of `<remotes>/` never reaches a neighbour
    that begins with the same text, and each spelling is listed once. A
    directory with no link in its path is typed and resolved at once."""
    prefixes = insteadof_prefixes(str(remotes) + trailing, typed=typed)
    assert set(prefixes) == spellings(remotes.resolve()), prefixes
    assert len(prefixes) == len(set(prefixes)), prefixes
    assert prefixes == insteadof_prefixes(remotes, typed=typed), prefixes


def a_link_to(directory: Path, tmp_path: Path) -> Path:
    """`tmp_path/link`, a symlink to `directory`, or a skip where this
    account cannot make one."""
    link = tmp_path / "link"
    try:
        link.symlink_to(directory, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this account cannot make a symlink")
    return link


def test_a_typed_directory_adds_the_spelling_it_was_given_first(tmp_path):
    """TYPED: a symlink kept, as a line a tool prints names a remote. The
    resolved directory is the one `.gitmodules` records, and stays."""
    real = tmp_path / "real"
    real.mkdir()
    link = a_link_to(real, tmp_path)
    resolved = spellings(real.resolve())
    typed = spellings(Path(os.path.abspath(link)))
    assert typed.isdisjoint(resolved), "premise: a link that is not its target"
    assert set(insteadof_prefixes(link)) == resolved
    prefixes = insteadof_prefixes(link, typed=True)
    assert set(prefixes[:len(typed)]) == typed, prefixes
    assert set(prefixes) == typed | resolved, prefixes
    assert len(prefixes) == len(set(prefixes)), prefixes
    # Both go to the one URL: the resolved directory's, where the legs are.
    uri = real.resolve().as_uri().rstrip("/") + "/"
    assert {key for key, _ in insteadof_entries(link, typed=True)} == {
        f"url.{uri}.insteadOf"}


def test_every_entry_sends_its_prefix_to_the_resolved_directorys_uri(
        remotes):
    uri = remotes.resolve().as_uri().rstrip("/") + "/"
    entries = insteadof_entries(remotes, typed=True)
    assert {key for key, _ in entries} == {f"url.{uri}.insteadOf"}, entries
    assert [prefix for _, prefix in entries] == insteadof_prefixes(
        remotes, typed=True)
    assert insteadof_args(remotes, typed=True) == [
        arg for key, prefix in entries for arg in ("-c", f"{key}={prefix}")]


def test_the_arguments_and_the_environment_send_a_plain_path_to_its_uri(
        remotes, tmp_path):
    """Both forms of the one rewrite do to a path under `remotes` what
    `clone_just_pushed` needs, and leave a neighbour's path as it is."""
    plain = str(remotes / f"{PROJECT}.git")
    neighbour = str(remotes) + f"-other/{PROJECT}.git"
    uri = (remotes.resolve() / f"{PROJECT}.git").as_uri()
    environ = {**os.environ, **read_through_git(remotes)}
    assert get_url(plain, *insteadof_args(remotes), cwd=tmp_path) == uri
    assert get_url(plain, env=environ, cwd=tmp_path) == uri
    assert get_url(neighbour, *insteadof_args(remotes),
                   cwd=tmp_path) == neighbour
    assert get_url(neighbour, env=environ, cwd=tmp_path) == neighbour


def test_the_environment_form_reads_a_path_typed_through_a_symlink(
        remotes, tmp_path):
    """`read_through_git` is the one user of `typed=True`: the line a tool
    prints names the remotes as the person typed them, a symlink and all, and
    only the TYPED spelling matches that path. Both go to the resolved
    directory's URI."""
    link = a_link_to(remotes, tmp_path)
    environ = {**os.environ, **read_through_git(link)}
    assert get_url(str(link / "A.git"), env=environ, cwd=tmp_path) == (
        remotes.resolve() / "A.git").as_uri()
    assert get_url(str(remotes / "A.git"), env=environ, cwd=tmp_path) == (
        remotes.resolve() / "A.git").as_uri()


def test_the_environment_form_keeps_what_the_environment_holds(
        remotes, tmp_path, monkeypatch):
    """APPENDED, as `appended_to_command_scope` appends the session's own
    settings: an entry the process already has is neither overwritten nor
    counted away, so the pasted line sees it as every other git does."""
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "url.held://base/.insteadOf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "held://")
    entries = read_through_git(remotes)
    assert "GIT_CONFIG_KEY_0" not in entries, entries
    assert entries["GIT_CONFIG_COUNT"] == str(
        1 + len(insteadof_prefixes(remotes, typed=True))), entries
    environ = {**os.environ, **entries}
    assert get_url("held://x", env=environ, cwd=tmp_path) == "held://base/x"
    assert get_url(str(remotes / "A.git"), env=environ, cwd=tmp_path) == (
        remotes.resolve() / "A.git").as_uri()


def test_an_init_of_an_empty_mount_is_read_through_git_by_the_wrapper(
        scaffolded, remote, tmp_path):
    """#662. The mount is empty and git keeps no repository for it, so its
    `--init` is a clone of the plain path `.gitmodules` records. Through
    `submodule_update_through_git` the leg arrives as one pack with no loose
    object, and the `submodule.<name>.url` git registers is still the plain
    path, as `-c` stores nothing. The same `--init` of the other leg, run
    plain, is git's local clone and leaves the remote's loose objects loose:
    the control that makes the first half mean something."""
    clone = cloned_just_pushed(remote, tmp_path / "clone", recurse=False)
    assert not any((clone / "spec").iterdir()), "premise: an empty mount"
    assert not any((clone / "code").iterdir()), "premise: an empty mount"

    submodule_update_through_git(clone, scaffolded["remotes"], "-q", "--init",
                                 "--", "spec")
    assert any((clone / "spec").iterdir()), "the leg was not checked out"
    assert_store_read_through_git(clone / "spec", "the leg, via the wrapper")
    registered = git("config", "--local", "--get", "submodule.spec.url",
                     cwd=clone).stdout.strip()
    assert registered.endswith(f"{PROJECT}-spec.git"), registered
    assert not registered.startswith("file:"), registered

    git(*FILE_PROTOCOL, "submodule", "update", "-q", "--init", "--", "code",
        cwd=clone)
    assert any((clone / "code").iterdir()), "the control was not checked out"
    with pytest.raises(AssertionError, match="loose objects"):
        assert_store_read_through_git(clone / "code", "the leg, plain")
