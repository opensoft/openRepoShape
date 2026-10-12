# SPDX-License-Identifier: Apache-2.0
"""What identity `tests/conftest.py`'s `git()` gives a commit, and what beats it (#279).

`git()` puts a default identity ahead of every verb as `-c` CONFIG. Two
properties make that the right mechanism, and neither was guarded by a test:

- the default EXISTS, so a commit, a tag or a merge made through the helper
  with no identity of its own does not die with `Author identity unknown` on a
  machine git cannot work one out on;
- the default is WEAK: a call site's own `-c user.name=...` (`as_human`, and
  the `-c user.name=t -c user.email=t@t` that most commits in this suite spell)
  and the four `GIT_AUTHOR_*` and `GIT_COMMITTER_*` variables, where exported,
  both beat it. A default exported through `env` instead would silently
  replace every call site's own.

CI exports an identity in all three jobs, so on CI the default is invisible and
a helper that lost it, put it in the environment, or placed it after a call
site's own `-c` would stay green. Each test here therefore REMOVES every
identity variable and isolates git's own config first, so it is identity-less
on every runner, CI included; it is the only thing in the suite that sees the
helper's precedence. It touches the helper alone: no other test is isolated.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import IDENTITY_EMAIL, IDENTITY_NAME, as_human, git

#: Every environment variable that can hand git an identity: the four a commit
#: reads, `EMAIL` (git's last fallback for the address), and the two that
#: inject config, so an ambient `-c` from a wrapping `git` cannot stand in for
#: one either.
IDENTITY_VARIABLES = ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL",
                      "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "EMAIL",
                      "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT")

#: `author name|author email|committer name|committer email`, the four fields
#: a test compares as one string.
DEFAULT = f"{IDENTITY_NAME}|{IDENTITY_EMAIL}|{IDENTITY_NAME}|{IDENTITY_EMAIL}"
OWN = "t|t@t|t|t@t"


@pytest.fixture
def idless(monkeypatch, tmp_path) -> Path:
    """An empty repository, in a process git can work NO identity out in.

    The four variables, `EMAIL` and the config injectors are removed; the
    global config is an empty file and the system config is off, so neither a
    developer's `~/.gitconfig` nor a runner's exported identity reaches the
    commit. `HOME` and `USERPROFILE`, the home directory on Windows, are moved
    too, because git older than 2.32 ignores `GIT_CONFIG_GLOBAL` and reads
    `~/.gitconfig` all the same.
    """
    for name in IDENTITY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    empty = tmp_path / "empty.gitconfig"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    repo = tmp_path / "repo"
    repo.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=repo)
    return repo


def who(repo: Path, rev: str = "HEAD") -> str:
    return git("log", "-1", "--format=%an|%ae|%cn|%ce", rev,
               cwd=repo).stdout.strip()


def commit_file(repo: Path, name: str, *identity: str) -> None:
    """A commit that adds `name`, as `identity` (`-c` pairs) if any is given."""
    (repo / name).write_text(name, encoding="utf-8")
    git("add", "--", name, cwd=repo)
    git(*identity, "commit", "-q", "-m", name, cwd=repo)


def test_a_call_with_no_identity_records_the_default(idless):
    git("commit", "-q", "--allow-empty", "-m", "x", cwd=idless)
    assert who(idless) == DEFAULT


def test_an_unrelated_dash_c_leaves_the_default_in_place(idless):
    """A leading `-c` that gives no identity does not turn the default off.

    `FILE_PROTOCOL`'s `-c protocol.file.allow=always`, `-c core.quotePath=...`
    and the like are the suite's other leading `-c` spellings. A helper that
    skipped the default whenever a call already carried a `-c`, on the guess
    that the call had given its own identity, would leave them identity-less.
    """
    git("-c", "core.protectNTFS=false", "commit", "-q", "--allow-empty",
        "-m", "x", cwd=idless)
    assert who(idless) == DEFAULT


def test_a_call_sites_own_dash_c_beats_the_default(idless):
    """The commonest spelling in the suite, `-c user.name=t -c user.email=t@t`.

    Fails when the default is exported through the environment, which outranks
    `user.name`, and when it is placed after the call's own `-c`, where the
    later pair wins.
    """
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
        "--allow-empty", "-m", "x", cwd=idless)
    assert who(idless) == OWN


def test_as_human_beats_the_default(idless):
    """`as_human`'s `Source Human`, the helper's other contested call site."""
    as_human("commit", "-q", "--allow-empty", "-m", "x", cwd=idless)
    assert who(idless) == ("Source Human|source@invalid.example|"
                           "Source Human|source@invalid.example")


def test_an_exported_identity_beats_both(idless, monkeypatch):
    """The four variables an operator or CI exports outrank the default AND a
    call's `-c`.

    That is git's own order, and it is why the default is safe to ship: it can
    only fill a gap, never override what a run was told. (An exported `EMAIL`
    is not among them: git reads it only where no `user.email` is set, so the
    default's address hides it.)
    """
    for name, value in (("GIT_AUTHOR_NAME", "EA"),
                        ("GIT_AUTHOR_EMAIL", "ea@e"),
                        ("GIT_COMMITTER_NAME", "EC"),
                        ("GIT_COMMITTER_EMAIL", "ec@e")):
        monkeypatch.setenv(name, value)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
        "--allow-empty", "-m", "x", cwd=idless)
    assert who(idless) == "EA|ea@e|EC|ec@e"
    git("commit", "-q", "--allow-empty", "-m", "y", cwd=idless)
    assert who(idless) == "EA|ea@e|EC|ec@e"


@pytest.fixture
def forked(idless) -> Path:
    """`main` at M, one commit past the root R; `side` at S, also one past R.

    R, S and M are all made as `t`, so the fixture itself never needs the
    default and a verb under test is the only thing that does. A verb that
    REPLAYS S (`cherry-pick`, `rebase`) shows two identities: the author it
    keeps and the committer it supplies, and only the second can come from the
    default.
    """
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
        "--allow-empty", "-m", "root", cwd=idless)
    git("checkout", "-q", "-b", "side", cwd=idless)
    commit_file(idless, "s", "-c", "user.name=t", "-c", "user.email=t@t")
    git("checkout", "-q", "main", cwd=idless)
    commit_file(idless, "m", "-c", "user.name=t", "-c", "user.email=t@t")
    return idless


def test_commit_tree_takes_the_default(forked):
    """`stage_unmerged`'s verb in `tests/test_shape_doctor.py`."""
    tree = git("rev-parse", "HEAD^{tree}", cwd=forked).stdout.strip()
    sha = git("commit-tree", tree, "-p", "HEAD", "-m", "ct",
              cwd=forked).stdout.strip()
    assert who(forked, sha) == DEFAULT


def test_an_annotated_tag_takes_the_default(forked):
    git("tag", "-a", "v1", "-m", "tag", cwd=forked)
    tagger = git("for-each-ref", "--format=%(taggername)|%(taggeremail)",
                 "refs/tags/v1", cwd=forked).stdout.strip()
    assert tagger == f"{IDENTITY_NAME}|<{IDENTITY_EMAIL}>"


def test_a_merge_takes_the_default(forked):
    git("merge", "--no-ff", "-m", "merge", "side", cwd=forked)
    assert who(forked) == DEFAULT


def test_a_cherry_pick_keeps_the_author_and_takes_the_default_committer(forked):
    git("checkout", "-q", "-b", "pick", "main~1", cwd=forked)
    git("cherry-pick", "side", cwd=forked)
    assert who(forked) == f"t|t@t|{IDENTITY_NAME}|{IDENTITY_EMAIL}"


def test_a_rebase_keeps_the_author_and_takes_the_default_committer(forked):
    git("checkout", "-q", "-b", "reb", "main~1", cwd=forked)
    commit_file(forked, "r", "-c", "user.name=t", "-c", "user.email=t@t")
    git("rebase", "main", cwd=forked)
    assert who(forked) == f"t|t@t|{IDENTITY_NAME}|{IDENTITY_EMAIL}"
    assert git("rev-parse", "HEAD~1", cwd=forked).stdout == git(
        "rev-parse", "main", cwd=forked).stdout
