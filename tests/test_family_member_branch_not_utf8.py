# SPDX-License-Identifier: Apache-2.0
"""`scripts/family.py`: a member checked out on a branch that is not UTF-8 is
read as the bytes git wrote, so `bump` and `remove` run, and a rollback puts
the member back ON that branch (#918, #457's L1-70).

ON 00f6d7f7 (2026-10-20): `_member_head` read `git symbolic-ref -q HEAD`
through `git_out`, which decodes UTF-8 strictly, and caught only `Refusal`.
`PinRollback` records the member's HEAD before the first write, so for a
member on `caf<0xE9>` it raised `UnicodeDecodeError`: `bump` and `remove`
ended in a traceback, exit 1, before they wrote anything. Now the name is
read as `_holder_branch` reads the holder's (#765): one newline and
`refs/heads/` off the bytes, the rest decoded with `surrogateescape`, as
#425 decodes a source's default branch; and git is handed it back as the
byte it is.

The family, its offline environment and the `pre-commit` hook that refuses
are `tests/test_family_bump_remove_rollback.py`'s: the hook refuses the one
commit after the first write, so each verb's rollback runs, and the member
must come back on its branch at its commit.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from conftest import (NOT_UTF_8_BRANCH, git, git_answer_bytes,
                      on_a_branch_that_is_not_utf_8)
from test_family import family, family_module  # noqa: F401
from test_family_add_refusals import holder, offline  # noqa: F401
from test_family_bump_remove_rollback import (
    BUMP_PUT_BACK, REMOVE_PUT_BACK, assert_same, bump, refusing_hook, remove,
    snapshot,
)
from test_family_dry_run import isolated
from test_family_member_path import MEMBER, older

PATH = f"members/{MEMBER}"
#: The ref a checkout on `NOT_UTF_8_BRANCH` is attached to, as git prints it.
ATTACHED = (b"refs/heads/" + NOT_UTF_8_BRANCH.encode("utf-8",
                                                     "surrogateescape")
            + b"\n")
#: How each verb's sentence begins once its rollback has put everything
#: back, and what it puts back.
UNDONE = {"bump": ("Nothing was bumped: the bump has been undone",
                   BUMP_PUT_BACK),
          "remove": ("Nothing was removed: the unmount has been undone",
                     REMOVE_PUT_BACK)}


@pytest.mark.parametrize("verb", ["bump", "remove"])
def test_a_member_on_a_branch_that_is_not_utf8_is_put_back_on_it(
        family, holder, offline, tmp_path, verb):
    """The member's checkout is on `caf<0xE9>` at the commit the holder
    pins, and the holder's `pre-commit` hook refuses: on 00f6d7f7 a
    `UnicodeDecodeError` traceback, exit 1. Now each verb runs to the
    commit the hook refuses, exit 2, and its rollback puts the holder back
    as it was and the member back on `caf<0xE9>`, attached, at its
    commit."""
    env = isolated(offline, tmp_path)
    mount = holder / PATH
    on_a_branch_that_is_not_utf_8(mount)
    at = git_answer_bytes(mount, "rev-parse", "HEAD").decode("ascii").strip()
    refusing_hook(holder, tmp_path)
    before = snapshot(holder, env)
    begins, put_back = UNDONE[verb]

    result = (bump(holder, env, older(family)) if verb == "bump"
              else remove(holder, env))

    assert "Traceback" not in result.stderr, result.stderr
    assert result.returncode == 2, result.stdout + result.stderr
    sentence = result.stderr.splitlines()[-1]
    assert sentence.startswith(begins), sentence
    assert " on caf" in sentence and at[:12] in sentence, sentence
    assert git_answer_bytes(mount, "symbolic-ref", "-q", "HEAD") == ATTACHED
    assert git_answer_bytes(mount, "rev-parse", "HEAD").decode(
        "ascii").strip() == at
    assert_same(before, snapshot(holder, env), put_back)


def checkout_on(tmp_path: Path, branch: str) -> tuple[Path, str]:
    """A repository of one commit, switched to a new branch `branch`, made
    as `on_a_branch_that_is_not_utf_8` makes one where it is that branch:
    `(it, its commit)`."""
    repository = tmp_path / "member"
    repository.mkdir()
    git("init", "-q", "-b", "main", cwd=repository)
    git("-c", "user.name=T", "-c", "user.email=t@example.invalid", "commit",
        "-q", "--allow-empty", "-m", "one", cwd=repository)
    if branch == NOT_UTF_8_BRANCH:
        on_a_branch_that_is_not_utf_8(repository)
    else:
        subprocess.run(["git", "switch", "-q", "-c", branch],
                       cwd=str(repository), capture_output=True, check=True)
    return repository, git("rev-parse", "HEAD", cwd=repository
                           ).stdout.strip()


@pytest.mark.parametrize("branch", [
    pytest.param(NOT_UTF_8_BRANCH, id="not-utf8"),
    pytest.param("feat\u00a0", id="trailing-no-break-space"),
])
def test_the_member_head_is_the_branch_git_wrote(tmp_path, branch):
    """`_member_head` reads the branch git wrote: a byte that is not UTF-8
    as its surrogate, where it raised `UnicodeDecodeError`; and a trailing
    U+00A0, which `strip()` took off, so the rollback named `feat`."""
    repository, at = checkout_on(tmp_path, branch)

    assert family_module()._member_head(repository) == (at, branch)
