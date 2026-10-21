# SPDX-License-Identifier: Apache-2.0
"""`--reuse-empty-repo` reuses the two legs as it reuses the root, and also a
leg whose one commit is the seed this scaffold pushes (#462).

WHAT WAS WRONG. A run whose push an organisation's ruleset refused left its
three repositories behind: all three empty when the first push, the spec
leg's, was refused, and a leg at one commit for each leg pushed before a later
push was. The re-run was refused as `scaffold-remote-exists` for the legs with
`--reuse-empty-repo` and without it, before the ruleset came into it at all,
and so was the re-run after an operator seeded a leg by hand. So no exit
finished a new project in a ruleset-protected organisation.

THE RULINGS (Brett Heap, 2026-10-12). "Re-run reuses empty legs": the flag
reuses each leg exactly as it reuses the root, when it exists with zero
commits. "Accept the scaffold's own seed": it also reuses a leg whose ONLY
commit has exactly the tree this scaffold would push to it. Any other leg
with commits is still refused, a root with commits still names
`adopt-project.py`, and nothing deletes, rewrites or force-pushes a remote.

Everything here runs against bare repositories on disk (`--local-remote-dir`)
but the tests of GitHub's side, a reused leg's visibility and a leg `gh` sees
that git cannot read (#542), which run against a fake `gh` on `PATH`, with
`--no-push`, and point git's `https://github.com/` at a path or a local
server that refuses it. The ruleset is the `pre-receive` hook
`test_ruleset_hint_tracking_branch.py` builds, and an empty `RULESET_REFUSES`
is the operator holding the bypass right.

EVERY GIT COMMAND THAT REACHES A REMOTE runs under one prompt rule (#915):
`only_commit`'s two, `_take_held_seed`'s fetch and each push, a first run's
and a re-run's, the pushes asked in a terminal against a local server that
asks for a login. A push git has no login for is refused naming how to give
it one, then the re-run. And a leg git reaches over ssh, through an
operator's `insteadOf` rewrite, is refused with ssh's reason and a remedy for
an ssh key, in the locale git runs in and in one that translates git; the ssh
is a stand-in that refuses every key, so nothing leaves this machine.

A PUSH THE HOST REFUSED A LOGIN FOR names the fix as well (#993): a login a
credential helper holds that the local server refuses, a first run's and a
re-run's, in a terminal, and a key the stand-in ssh refuses where an
`insteadOf` or a `pushInsteadOf` rule sends the push over ssh, each in git's
own locale and in one that translates git.

A PUSH SSH REFUSED THE HOST'S KEY FOR is not a ruleset's (#1108): a key ssh
does not know, refused unasked as under `BatchMode=yes`, and a key that
changed, each in the words OpenSSH 9.6 printed for it against a fake server,
is told how to check the key against GitHub's fingerprints and keep it, then
the re-run, and not the ruleset hint; a changed key is never told to be
accepted as it comes. And a ruleset's refusal on GitHub says, after the hint,
the prompts the hint's re-run can still wait at, which it does not say under
`--local-remote-dir`.

A SEED FOUND ONLY ON ANOTHER BRANCH IS SAID (#921). The re-run takes a seed
that sits on `seed/scaffold`, the branch the ruleset hint made before #506,
creates the tracking branch at it and leaves that branch as it is. Its NOTE
names each such branch, says it remains and, on GitHub only, that it may be
the leg's default branch, in a dry run as in the real run, and says nothing
where the tracking branch holds the seed too.
"""

from __future__ import annotations

import http.server
import importlib.util
import json
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

from conftest import (ORG, PROJECT, PTY_SKIP, SCAFFOLD, WINDOWS_SKIP,
                      appended_to_command_scope, git,
                      load_without_bytecode, rmtree,
                      run_in_a_terminal, run_script)
from test_ruleset_hint_tracking_branch import refusing, text_for
from test_ruleset_hint_tracking_branch import template  # noqa: F401

LEGS = ("spec", "code")
REPOS = {"assembly": f"{PROJECT}.git", "spec": f"{PROJECT}-spec.git",
         "code": f"{PROJECT}-code.git"}


def scaffold(tmp_path, work: str, *extra: str, env: dict | None = None):
    return run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                      "--elected-by", "Test Human",
                      "--elected-on", "2026-09-02",
                      "--local-remote-dir", str(tmp_path / "remotes"),
                      "--work-dir", str(tmp_path / work), *extra, env=env)


def bare(tmp_path, role: str) -> Path:
    return tmp_path / "remotes" / REPOS[role]


def tip(tmp_path, role: str, ref: str = "refs/heads/main") -> str:
    """The commit at `ref`, or "" when there is none or no repository."""
    if not bare(tmp_path, role).is_dir():
        return ""
    return git("rev-parse", "--verify", "-q", ref, cwd=bare(tmp_path, role),
               check=False).stdout.strip()


def commits(tmp_path, role: str) -> int:
    return int(git("rev-list", "--count", "--all",
                   cwd=bare(tmp_path, role)).stdout.strip())


def reserve(tmp_path, *roles: str) -> None:
    """Each repository named, created EMPTY: a reserved name."""
    for role in roles:
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main",
                        str(bare(tmp_path, role))], check=True)


def assert_finished(tmp_path, result) -> None:
    """The project is whole: each repository holds ONE commit on `main`, and
    the root mounts each leg at that leg's commit."""
    assert result.returncode == 0, result.stderr + result.stdout
    for role in REPOS:
        assert tip(tmp_path, role), role
        assert commits(tmp_path, role) == 1, role
    for leg in LEGS:
        mounted = git("rev-parse", f"refs/heads/main:{leg}",
                      cwd=bare(tmp_path, "assembly")).stdout.strip()
        assert mounted == tip(tmp_path, leg), leg


def refused_at_the_root(tmp_path, template_dir):
    """A first run whose ruleset covers the root alone: both legs pushed, one
    commit each, and the root empty. Returns the two legs' commits."""
    first = scaffold(tmp_path, "w1",
                     env=refusing(template_dir, REPOS["assembly"]))
    assert first.returncode == 2, first.stderr + first.stdout
    assert "REFUSED pushing the assembly root" in first.stderr
    seeds = {leg: tip(tmp_path, leg) for leg in LEGS}
    assert all(seeds.values()) and commits(tmp_path, "assembly") == 0
    return seeds


# --- empty legs -------------------------------------------------------------

def test_three_empty_repositories_are_all_reused_with_the_flag(tmp_path):
    """Ruling: "Re-run reuses empty legs". An organisation that reserved all
    three names first, or a run a ruleset refused at its first push."""
    reserve(tmp_path, "assembly", "spec", "code")
    result = scaffold(tmp_path, "work", "--reuse-empty-repo")
    for role in REPOS:
        assert f"reuse {bare(tmp_path, role)} (zero commits)" in result.stdout
    assert_finished(tmp_path, result)


def test_an_empty_leg_without_the_flag_is_refused_naming_the_flag(tmp_path):
    reserve(tmp_path, "spec")
    result = scaffold(tmp_path, "work")
    assert result.returncode == 2
    assert "scaffold-remote-exists" in result.stderr
    assert "it has ZERO commits" in result.stderr
    assert "re-run with --reuse-empty-repo to use it as the spec leg" in (
        result.stderr)
    # #915, U037: a re-run under --local-remote-dir reads and pushes paths
    # on disk, where no ssh, credential helper or askpass is asked, so no
    # prompt can follow and the remedy does not say one can.
    assert STILL_ASKS.strip() not in result.stderr, result.stderr
    assert not bare(tmp_path, "code").exists(), "nothing was created"


def test_the_flag_without_the_operator_is_refused_again_and_changes_nothing(
        tmp_path, template):  # noqa: F811
    """The flag is not the bypass: under the ruleset the re-run is refused at
    the same push, prints the same exit, and leaves the three as they were."""
    everything = refusing(template, *REPOS.values())
    assert scaffold(tmp_path, "w1", env=everything).returncode == 2
    again = scaffold(tmp_path, "w2", "--reuse-empty-repo", env=everything)
    assert again.returncode == 2
    assert "REFUSED pushing the spec leg" in again.stderr
    assert "ONE exit finishes this scaffold" in again.stderr
    assert "could not get a login" not in again.stderr, (
        "a push a ruleset refused is not one git had no login for (#915)")
    assert [commits(tmp_path, role) for role in REPOS] == [0, 0, 0]


# --- a leg holding the scaffold's own seed ----------------------------------

def test_legs_holding_the_seed_are_reused_at_their_commits(
        tmp_path, template):  # noqa: F811
    """Ruling: "Accept the scaffold's own seed". The root's push was refused
    after both legs were pushed; the operator's re-run takes each leg's
    commit as it is, pushes nothing over it, and mounts and pins it."""
    seeds = refused_at_the_root(tmp_path, template)
    # A LATER DATE for anything the re-run commits. A commit made in the same
    # second as the first run's, by the same identity, with the same message
    # and tree, IS the first run's, so without it a re-run that made a new
    # leg commit could pass "never rewritten" by the clock.
    later = {"GIT_AUTHOR_DATE": "2031-01-01T00:00:00+0000",
             "GIT_COMMITTER_DATE": "2031-01-01T00:00:00+0000"}
    result = scaffold(tmp_path, "w2", "--reuse-empty-repo",
                      env={**refusing(template), **later})
    for leg in LEGS:
        assert (f"reuse {bare(tmp_path, leg)} (one commit, {seeds[leg][:12]}: "
                "the seed this scaffold pushes)") in result.stdout
    assert "NOTE the seed in" not in result.stdout, (
        "a seed on the tracking branch is taken from it, so no branch "
        "elsewhere is in question (#921)")
    assert_finished(tmp_path, result)
    for leg in LEGS:
        assert tip(tmp_path, leg) == seeds[leg], "a reused leg is never rewritten"
        pin = git("show", f"main:contracts/{leg}-pin.yaml",
                  cwd=bare(tmp_path, "assembly")).stdout
        assert seeds[leg] in pin, pin


def seed_pushed_to(tmp_path, template_dir, *branches: str) -> str:
    """A first run every ruleset refused, so all three repositories are made
    and empty, then the spec leg's seed pushed, as an operator would, to each
    of `branches` (`main` not among them unless named): the commit pushed."""
    assert scaffold(tmp_path, "w1", env=refusing(
        template_dir, *REPOS.values())).returncode == 2
    for branch in branches:
        pushed = subprocess.run(
            ["git", "-C", str(tmp_path / "w1" / f"{PROJECT}-spec"), "push",
             "-q", str(bare(tmp_path, "spec")),
             f"main:refs/heads/{branch}"],
            capture_output=True, text=True, check=False,
            env={**os.environ, **refusing(template_dir)})
        assert pushed.returncode == 0, pushed.stderr
    seed = tip(tmp_path, "spec", f"refs/heads/{branches[0]}")
    assert seed
    return seed


def seed_branch_note(tmp_path, tracking: str, *branches: str) -> str:
    """The NOTE a `--local-remote-dir` re-run prints for the spec leg's seed
    found only on `branches` (#921): no word of GitHub, as the leg is a bare
    repository on disk."""
    if len(branches) > 1:
        found = ("branches " + ", ".join(f"`{name}`" for name in branches[:-1])
                 + f" and `{branches[-1]}`")
        left = "them, so they remain"
    else:
        found = f"branch `{branches[0]}`"
        left = f"`{branches[0]}`, so that branch remains"
    return (f"NOTE the seed in {bare(tmp_path, 'spec')} was found only on its "
            f"{found}: this run creates `{tracking}` at it and does not "
            f"touch {left}.")


def test_a_seed_pushed_to_a_seed_branch_alone_is_taken_too(
        tmp_path, template):  # noqa: F811
    """The exit the hint used to print: the seed pushed to `seed/scaffold`,
    which the ruleset lets through, and `main` absent. Its one commit is the
    seed, so the re-run takes it and creates `main` AT it: a new branch, not
    a rewrite. And it SAYS which branch remains (#921): `seed/scaffold` is
    left as it is. It says nothing of GitHub's default branch, as a bare
    repository on disk is no GitHub's."""
    seed = seed_pushed_to(tmp_path, template, "seed/scaffold")
    assert seed and not tip(tmp_path, "spec")
    result = scaffold(tmp_path, "w2", "--reuse-empty-repo",
                      env=refusing(template))
    assert_finished(tmp_path, result)
    assert tip(tmp_path, "spec") == seed
    assert tip(tmp_path, "spec", "refs/heads/seed/scaffold") == seed, (
        "the branch the seed was found on is not touched")
    note = seed_branch_note(tmp_path, "main", "seed/scaffold")
    assert result.stdout.count(note) == 1, result.stdout
    assert result.stdout.count("NOTE the seed in") == 1, (
        "the code leg was empty and the root is no leg: one leg, one NOTE")
    assert "GitHub" not in result.stdout, result.stdout
    assert result.stdout.index(f"reuse {bare(tmp_path, 'spec')} (one commit") \
        < result.stdout.index(note), "the NOTE follows the leg's reuse line"


def test_a_dry_run_says_the_seed_branch_too_and_makes_nothing(
        tmp_path, template):  # noqa: F811
    """The question is asked before anything is made (#537), the NOTE with
    it, so a person reads it in the plan and not after the run."""
    seed = seed_pushed_to(tmp_path, template, "seed/scaffold")
    result = scaffold(tmp_path, "w2", "--reuse-empty-repo", "--dry-run",
                      env=refusing(template))
    assert result.returncode == 0, result.stderr + result.stdout
    assert seed_branch_note(tmp_path, "main", "seed/scaffold") in (
        result.stdout), result.stdout
    assert not tip(tmp_path, "spec"), "a dry run creates no branch"
    assert tip(tmp_path, "spec", "refs/heads/seed/scaffold") == seed


def test_a_seed_on_the_tracking_branch_as_well_prints_no_seed_note(
        tmp_path, template):  # noqa: F811
    """`main` holds the seed beside `seed/scaffold`: the re-run creates
    nothing and takes the seed from `main`, so there is no seed found only
    elsewhere to say (#921)."""
    seed = seed_pushed_to(tmp_path, template, "seed/scaffold", "main")
    assert tip(tmp_path, "spec") == seed
    result = scaffold(tmp_path, "w2", "--reuse-empty-repo",
                      env=refusing(template))
    assert_finished(tmp_path, result)
    assert "NOTE the seed in" not in result.stdout, result.stdout


def test_a_seed_on_two_branches_names_both(tmp_path, template):  # noqa: F811
    """Neither is `main`: both remain, and the NOTE names both, in the
    order a sort gives them, whichever order git listed them."""
    seed = seed_pushed_to(tmp_path, template, "seed/scaffold", "other")
    result = scaffold(tmp_path, "w2", "--reuse-empty-repo",
                      env=refusing(template))
    assert_finished(tmp_path, result)
    assert tip(tmp_path, "spec") == seed
    assert seed_branch_note(tmp_path, "main", "other", "seed/scaffold") in (
        result.stdout), result.stdout


def test_a_branch_name_is_shown_safe_in_the_seed_note(
        tmp_path, template):  # noqa: F811
    """The remote gives the name, and git takes U+202E in a branch's name:
    shown raw it reorders the line a person reads. It is spelt as
    `shown_path` spells a path, as `repr` does (#692, #766)."""
    name = "seed/" + chr(0x202E) + "scaffold"
    assert not name.isprintable()
    seed_pushed_to(tmp_path, template, name)
    result = scaffold(tmp_path, "w2", "--reuse-empty-repo", "--dry-run",
                      env=refusing(template))
    assert result.returncode == 0, result.stderr + result.stdout
    assert chr(0x202E) not in result.stdout + result.stderr
    assert f"its branch `{name!r}`: " in result.stdout, result.stdout


@pytest.mark.parametrize("refs,found_on", [
    pytest.param(("HEAD", "refs/heads/seed/scaffold"), ("seed/scaffold",),
                 id="github-default-branch-is-seed-scaffold"),
    pytest.param(("refs/heads/seed/scaffold", "refs/heads/main"), (),
                 id="the-tracking-branch-holds-it-too"),
    pytest.param(("HEAD", "refs/heads/main"), (), id="only-the-tracking"),
    pytest.param(("refs/heads/zeta", "refs/heads/alpha"), ("alpha", "zeta"),
                 id="sorted"),
    pytest.param(("refs/tags/v0", "refs/pull/1/head"), (),
                 id="a-tag-and-a-pull-request-are-no-branch"),
    pytest.param(("refs/heads/seed/scaffold", "refs/pull/1/head"),
                 ("seed/scaffold",), id="a-pull-request-beside-the-branch"),
    pytest.param(("refs/heads/mainline",), ("mainline",),
                 id="a-name-that-starts-with-the-tracking-name"),
    pytest.param(("refs/heads/seed/main",), ("seed/main",),
                 id="a-branch-ending-in-the-tracking-name"),
    pytest.param(("refs/tags/main", "refs/heads/seed/scaffold"),
                 ("seed/scaffold",), id="a-tag-named-as-the-tracking-branch"),
])
def test_the_branches_a_seed_was_found_on(scaffold_module, refs, found_on):
    """#921: `_seed_branches` names each branch, by name and in order, and
    names none where `main` holds the seed too."""
    assert scaffold_module._seed_branches(refs, "main") == found_on


@pytest.mark.parametrize("local,branches,said", [
    pytest.param(
        True, ("seed/scaffold",),
        "NOTE the seed in T was found only on its branch `seed/scaffold`: "
        "this run creates `main` at it and does not touch `seed/scaffold`, "
        "so that branch remains.",
        id="local-one-branch-and-no-word-of-github"),
    pytest.param(
        True, ("other", "seed/scaffold"),
        "NOTE the seed in T was found only on its branches `other` and "
        "`seed/scaffold`: this run creates `main` at it and does not touch "
        "them, so they remain.",
        id="local-two-branches-and-no-word-of-github"),
    pytest.param(
        False, ("seed/scaffold",),
        "NOTE the seed in T was found only on its branch `seed/scaffold`: "
        "this run creates `main` at it and does not touch `seed/scaffold`, "
        "so that branch remains, and on GitHub it may be the leg's default "
        "branch.",
        id="github-one-branch-may-be-the-default"),
    pytest.param(
        False, ("other", "seed/scaffold"),
        "NOTE the seed in T was found only on its branches `other` and "
        "`seed/scaffold`: this run creates `main` at it and does not touch "
        "them, so they remain, and on GitHub one of them may be the leg's "
        "default branch.",
        id="github-two-branches-one-may-be-the-default"),
])
def test_the_seed_note_says_github_only_on_github(scaffold_module, local,
                                                  branches, said):
    """#921: "on GitHub it may be the leg's default branch" is said of a
    GitHub leg, as the issue says it, and not of a bare repository under
    `--local-remote-dir`, which has no GitHub to be the default branch of."""
    assert scaffold_module._seed_branch_note(
        "T", branches, "main", local) == said


@pytest.mark.parametrize("local,ending", [
    pytest.param(False, "so that branch remains, and on GitHub it may be "
                 "the leg's default branch.", id="github-leg"),
    pytest.param(True, "so that branch remains.", id="bare-repository-leg"),
])
def test_the_note_a_re_run_prints_says_github_only_for_a_github_leg(
        scaffold_module, monkeypatch, capsys, local, ending):
    """RV1052d's NIT-A: `_reusable_remotes` hands `_seed_branch_note` the
    `local` it was called with. Every run in this file that finds a seed only
    on `seed/scaffold` is a `--local-remote-dir` run, and the unit test above
    calls `_seed_branch_note` directly, so a call that always passed `True`
    for `local` (RV1052d's R2c) printed no GitHub clause for a GitHub leg and
    no test failed. Here `remote_is_empty` says the leg exists with commits
    and `_held_seed` says its one commit is the seed, found on
    `seed/scaffold` alone, and the NOTE that `_reusable_remotes` itself
    prints is what is read: GitHub's ends with the default-branch clause, and
    the bare repository's, which has no GitHub, does not. In-process, so it
    runs on every platform."""
    seed = "0123456789abcdef0123456789abcdef01234567"
    monkeypatch.setattr(scaffold_module, "remote_is_empty",
                        lambda repository: False)
    monkeypatch.setattr(scaffold_module, "local_remote_is_empty",
                        lambda target: False)
    monkeypatch.setattr(scaffold_module, "_held_seed",
                        lambda role, url, values, tracking, scratch: (
                            seed, None, ("seed/scaffold",)))
    reused = scaffold_module._reusable_remotes(
        {"spec": "Atlas-spec"}, {"spec": "/remotes/Atlas-spec.git"},
        {"spec": "o/Atlas-spec"}, local=local, reuse_flag=True, values={},
        tracking="main")
    assert reused == {"spec": seed}
    notes = [line for line in capsys.readouterr().out.splitlines()
             if line.startswith("NOTE the seed in")]
    target = str(Path("/remotes/Atlas-spec.git")) if local else "o/Atlas-spec"
    assert notes == [
        f"NOTE the seed in {target} was found only on its branch "
        "`seed/scaffold`: this run creates `main` at it and does not touch "
        f"`seed/scaffold`, {ending}"], notes
    assert notes[0].endswith(", and on GitHub it may be the leg's default "
                             "branch.") is (not local)
    assert ("GitHub" in notes[0]) is (not local)


def test_dry_run_help_says_the_mode_bits_and_nothing_that_stays(tmp_path):
    """#923 U063 and #921 U088, the scaffold's half: `--dry-run`'s help says
    the write question is asked of `os.access`, which on Windows says yes for
    every folder, so a quota, a Windows ACL or a read-only drive there can
    pass it, and that it leaves "nothing that stays" where it once said "make
    no folder": it makes and removes `openreposhape-seed-*` and
    `openreposhape-branch-*` in the temporary folder. The wording is
    `docs/cli.md`'s too."""
    result = run_script(SCAFFOLD, "--help", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    said = " ".join(result.stdout.split())
    assert ("Whether each folder can be written in is asked of `os.access`, "
            "which reads the mode bits and on Windows says yes for every "
            "folder, so a quota, a Windows ACL or a read-only drive on "
            "Windows can pass here and be refused by the real run. It leaves "
            "nothing that stays: it makes and removes temporary folders, "
            "creates no remote and pushes nothing") in said, said
    assert "make no folder" not in said
    assert "its mode bits'" not in said, (
        "only the write question is `os.access`'s: a file in the way and a "
        "tree's contents are not the mode bits'")


def test_a_leg_holding_the_seed_without_the_flag_names_the_flag(
        tmp_path, template):  # noqa: F811
    refused_at_the_root(tmp_path, template)
    rmtree(bare(tmp_path, "assembly"))
    result = scaffold(tmp_path, "w2", env=refusing(template))
    assert result.returncode == 2
    assert "scaffold-remote-exists" in result.stderr
    assert "and has commits" in result.stderr
    assert "its one commit is the seed this scaffold pushes" in result.stderr
    assert "re-run with --reuse-empty-repo to use it as the spec leg" in (
        result.stderr)
    assert not bare(tmp_path, "assembly").exists(), "nothing was created"


# --- what is still refused ---------------------------------------------------

def assert_refused_as_not_the_seed(tmp_path, result, before: dict) -> None:
    assert result.returncode == 2, result.stdout
    assert "scaffold-remote-exists" in result.stderr
    assert f"{bare(tmp_path, 'spec')} already exists and has commits" in (
        result.stderr)
    assert "it holds commits other than the one seed this scaffold would " \
           "push to it" in result.stderr
    assert "There is no --force." in result.stderr
    assert {role: tip(tmp_path, role) for role in REPOS} == before, (
        "a refused re-run moves nothing")


def test_a_leg_with_a_commit_after_the_seed_is_refused(
        tmp_path, template):  # noqa: F811
    refused_at_the_root(tmp_path, template)
    clone = tmp_path / "w1" / f"{PROJECT}-spec"
    (clone / "extra.md").write_text("somebody's work\n", encoding="utf-8")
    git("add", "extra.md", cwd=clone)
    git("commit", "-q", "-m", "Somebody's work", cwd=clone)
    git("push", "-q", "origin", "main", cwd=clone)
    before = {role: tip(tmp_path, role) for role in REPOS}
    result = scaffold(tmp_path, "w2", "--reuse-empty-repo",
                      env=refusing(template))
    assert_refused_as_not_the_seed(tmp_path, result, before)


def test_a_leg_whose_tip_has_the_seed_tree_over_another_commit_is_refused(
        tmp_path, template):  # noqa: F811
    """The seed must be the leg's ONLY commit, not a tip with its tree: an
    empty commit on top of it is a second commit somebody made."""
    refused_at_the_root(tmp_path, template)
    clone = tmp_path / "w1" / f"{PROJECT}-spec"
    git("commit", "-q", "--allow-empty", "-m", "Somebody's empty commit",
        cwd=clone)
    git("push", "-q", "origin", "main", cwd=clone)
    before = {role: tip(tmp_path, role) for role in REPOS}
    result = scaffold(tmp_path, "w2", "--reuse-empty-repo",
                      env=refusing(template))
    assert_refused_as_not_the_seed(tmp_path, result, before)


def test_a_leg_with_another_commit_on_another_ref_is_refused(
        tmp_path, template):  # noqa: F811
    """EVERY ref counts, as `rev-list --all` counts every ref for "empty": the
    seed on `main` and somebody's commit on another branch is two commits."""
    refused_at_the_root(tmp_path, template)
    clone = tmp_path / "w1" / f"{PROJECT}-spec"
    git("checkout", "-q", "-b", "theirs", cwd=clone)
    (clone / "theirs.md").write_text("somebody's branch\n", encoding="utf-8")
    git("add", "theirs.md", cwd=clone)
    git("commit", "-q", "-m", "Somebody's branch", cwd=clone)
    git("push", "-q", "origin", "theirs", cwd=clone)
    before = {role: tip(tmp_path, role) for role in REPOS}
    result = scaffold(tmp_path, "w2", "--reuse-empty-repo",
                      env=refusing(template))
    assert_refused_as_not_the_seed(tmp_path, result, before)
    assert tip(tmp_path, "spec", "refs/heads/theirs"), "nothing was deleted"


def test_a_leg_this_run_would_seed_with_another_tree_is_refused(
        tmp_path, template):  # noqa: F811
    """The seed is the tree THIS run would push: a re-run with another
    `--code-path` writes another spec leg (its AGENTS.md names the path), so
    the first run's seed is not its seed."""
    refused_at_the_root(tmp_path, template)
    before = {role: tip(tmp_path, role) for role in REPOS}
    result = scaffold(tmp_path, "w2", "--reuse-empty-repo", "--code-path",
                      "src", env=refusing(template))
    assert_refused_as_not_the_seed(tmp_path, result, before)


def theirs_at_one_commit(tmp_path) -> None:
    """The spec leg's bare repository, holding ONE commit that is not a tree
    this scaffold writes: somebody's repository that has the name."""
    work = tmp_path / "theirs"
    git("init", "-q", "-b", "main", str(work), cwd=tmp_path)
    (work / "README.md").write_text("# live\n", encoding="utf-8")
    git("add", "README.md", cwd=work)
    git("commit", "-q", "-m", "live", cwd=work)
    reserve(tmp_path, "spec")
    git("push", "-q", str(bare(tmp_path, "spec")), "main", cwd=work)


def test_a_leg_somebody_else_made_is_refused(tmp_path):
    """One commit, but not a tree this scaffold writes: somebody's
    repository that happens to have the name."""
    theirs_at_one_commit(tmp_path)
    before = {role: tip(tmp_path, role) for role in REPOS}
    result = scaffold(tmp_path, "work", "--reuse-empty-repo")
    assert_refused_as_not_the_seed(tmp_path, result, before)
    assert not bare(tmp_path, "code").exists(), "nothing was created"


# --- a reused leg's visibility (GitHub) -------------------------------------

#: A `gh` that knows the repositories `FAKE_GH_REPOS` names
#: (`org/name=VISIBILITY,...`), each at that visibility and EMPTY unless
#: `FAKE_GH_FULL` names it too (`org/name,...`), when its commit listing has
#: one commit; it answers `repo create` and `repo edit` with success, answers
#: `api orgs/<org>` with `FAKE_GH_PLAN` when that is set (the Free-plan hint
#: asks it for `.plan.name`), and with `FAKE_GH_PLAN_ERROR` on stderr and
#: exit 1 when that is, answers `repo view` of each repository that
#: `FAKE_GH_VIEW_ERRORS` (JSON, `{"org/name": "stderr text"}`) names with that
#: text and exit 1, known or not (a 401, where an unknown one is not-found),
#: answers only `repo view --json visibility` of each that
#: `FAKE_GH_VISIBILITY_ERRORS` names so (an `HTTP 502` after `--json name`
#: found it), and logs every call.
FAKE_GH = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json
    import os
    import sys

    argv = sys.argv[1:]
    with open(os.environ["FAKE_GH_LOG"], "a", encoding="utf-8") as f:
        f.write(" ".join(argv) + "\\n")
    KNOWN = dict(pair.split("=") for pair in
                 os.environ["FAKE_GH_REPOS"].split(",") if pair)
    FULL = os.environ.get("FAKE_GH_FULL", "").split(",")
    ERRORS = json.loads(os.environ.get("FAKE_GH_VIEW_ERRORS", "{}"))
    UNSEEN = json.loads(os.environ.get("FAKE_GH_VISIBILITY_ERRORS", "{}"))

    if argv[:2] == ["repo", "view"]:
        repo = argv[2]
        fields = (argv[argv.index("--json") + 1].split(",")
                  if "--json" in argv else [])
        if repo in UNSEEN and "visibility" in fields:
            ERRORS[repo] = UNSEEN[repo]
        if repo in ERRORS:
            print(ERRORS[repo], file=sys.stderr)
            sys.exit(1)
        if repo not in KNOWN:
            print("GraphQL: Could not resolve to a Repository", file=sys.stderr)
            sys.exit(1)
        out = {}
        if "name" in fields:
            out["name"] = repo.rsplit("/", 1)[-1]
        if "visibility" in fields:
            out["visibility"] = KNOWN[repo]
        print(json.dumps(out))
    elif (argv[:1] == ["api"] and argv[1].startswith("orgs/")
          and "FAKE_GH_PLAN_ERROR" in os.environ):
        print(os.environ["FAKE_GH_PLAN_ERROR"], file=sys.stderr)
        sys.exit(1)
    elif (argv[:1] == ["api"] and argv[1].startswith("orgs/")
          and "FAKE_GH_PLAN" in os.environ):
        print(os.environ["FAKE_GH_PLAN"])
    elif argv[:1] == ["api"] and argv[1].split("/commits")[0][6:] in KNOWN:
        print('[{"sha": "0"}]' if argv[1].split("/commits")[0][6:] in FULL
              else "[]")
    elif argv[:2] in (["repo", "create"], ["repo", "edit"]):
        pass
    else:
        print(f"fake gh: unhandled {argv!r}", file=sys.stderr)
        sys.exit(1)
    """)


def fake_gh(tmp_path, repos: dict, full=(), plan: str | None = None,
            view_errors: dict | None = None, *,
            visibility_errors: dict | None = None,
            plan_error: str | None = None) -> tuple[dict, Path]:
    """`FAKE_GH` first on PATH, knowing `repos` (`{name: VISIBILITY}`, each
    under `ORG`) and holding commits in each of `full`, naming `plan` as the
    organisation's GitHub plan when one is given, or failing that question
    with the text `plan_error`, and failing `repo view` of each name in
    `view_errors` (`{name: stderr text}`, each under `ORG`) with that text,
    or only its `--json visibility` for each name in `visibility_errors`:
    the environment for the run, and the log of every call. Nothing it
    answers reaches GitHub."""
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    gh = fakebin / "gh"
    gh.write_text(FAKE_GH, encoding="utf-8")
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    log = tmp_path / "gh.log"
    log.write_text("", encoding="utf-8")
    env = {"PATH": f"{fakebin}{os.pathsep}{os.environ.get('PATH', '')}",
           "FAKE_GH_LOG": str(log),
           "FAKE_GH_REPOS": ",".join(f"{ORG}/{name}={visibility}"
                                     for name, visibility in repos.items()),
           "FAKE_GH_FULL": ",".join(f"{ORG}/{name}" for name in full)}
    if plan is not None:
        env["FAKE_GH_PLAN"] = plan
    if plan_error is not None:
        env["FAKE_GH_PLAN_ERROR"] = plan_error
    for key, errors in (("FAKE_GH_VIEW_ERRORS", view_errors),
                        ("FAKE_GH_VISIBILITY_ERRORS", visibility_errors)):
        if errors:
            env[key] = json.dumps(
                {f"{ORG}/{name}": text for name, text in errors.items()})
    return env, log


def on_github(tmp_path, *extra: str, env: dict, cwd: Path | None = None):
    """The scaffold in its GitHub mode, against `fake_gh`, pushing nothing."""
    return run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                      "--elected-by", "Test Human", "--no-push",
                      "--work-dir", str(tmp_path / "work"), *extra,
                      cwd=cwd, env=env)


@WINDOWS_SKIP
def test_a_reused_leg_keeps_its_visibility_and_a_disagreement_is_said(
        tmp_path):
    """A reused leg is not created, so it keeps the visibility the run that
    created it gave it; a run whose visibility disagrees is told so, as
    `_leg_visibility` tells it about a reused root. The shebang `gh` is why
    this is skipped on Windows, which does not run one; what it pins is a
    `gh repo view` read, which is platform-blind."""
    env, log = fake_gh(tmp_path, {PROJECT: "PRIVATE",
                                  f"{PROJECT}-spec": "PUBLIC",
                                  f"{PROJECT}-code": "PRIVATE"})
    result = on_github(tmp_path, "--reuse-empty-repo", env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (f"WARNING {ORG}/{PROJECT}-spec is reused and is public on GitHub, "
            "where this run's visibility is private.") in result.stderr
    assert f"{ORG}/{PROJECT}-code is reused" not in result.stderr, (
        "a reused leg that agrees is not warned about")
    assert "repo create" not in log.read_text(encoding="utf-8"), (
        "a reused repository is never created")


# --- the reuse re-run's visibility text (#542) ------------------------------

SPEC_REPO, CODE_REPO = f"{ORG}/{PROJECT}-spec", f"{ORG}/{PROJECT}-code"
#: What the private-leg NOTE says after its subject, for one leg and for two.
READ_IT = (f": give {ORG}/{PROJECT} a way to read it — a GitHub App "
           "(SHAPE_LEGS_APP_ID + SHAPE_LEGS_APP_PRIVATE_KEY, preferred) or a "
           "SHAPE_LEGS_TOKEN PAT (contents:read on that leg, fallback) — or "
           "the `validate` check cannot check it out.")
READ_THEM = (f": give {ORG}/{PROJECT} a way to read them — a GitHub App "
             "(SHAPE_LEGS_APP_ID + SHAPE_LEGS_APP_PRIVATE_KEY, preferred) or a "
             "SHAPE_LEGS_TOKEN PAT (contents:read on the legs, fallback) — or "
             "the `validate` check cannot check them out.")
INHERITED = (f"NOTE {ORG}/{PROJECT} is already private on GitHub; a leg this "
             "run creates inherits that visibility, and a leg it reuses keeps "
             "its own (pass --visibility to choose one explicitly).")
DISAGREES = (f"WARNING --visibility public disagrees with the reused "
             f"{ORG}/{PROJECT}, which is private on GitHub. A leg this run "
             "creates is created public because that is what you asked for, "
             "not because it is what the assembly root already is; a leg it "
             "reuses keeps its own.")


@WINDOWS_SKIP
@pytest.mark.parametrize("repos,flags,said", [
    # A private run that reuses a PUBLIC spec leg: on main the NOTE called
    # both legs private, beside the WARNING that the spec leg is public.
    ({PROJECT: "PRIVATE", f"{PROJECT}-spec": "PUBLIC",
      f"{PROJECT}-code": "PRIVATE"}, (),
     [INHERITED, f"NOTE {CODE_REPO} is private{READ_IT}"]),
    # A public run that reuses a private and an internal leg: on main it
    # printed no NOTE at all, and its WARNING spoke of "the two new legs".
    ({PROJECT: "PRIVATE", f"{PROJECT}-spec": "PRIVATE",
      f"{PROJECT}-code": "INTERNAL"}, ("--visibility", "public"),
     [DISAGREES,
      f"NOTE {SPEC_REPO} is private and {CODE_REPO} is internal{READ_THEM}"]),
    # One leg created at the run's public, one reused private.
    ({PROJECT: "PUBLIC", f"{PROJECT}-code": "PRIVATE"},
     ("--visibility", "public"), [f"NOTE {CODE_REPO} is private{READ_IT}"]),
    # Both legs private: the sentence the note has always printed.
    ({PROJECT: "PRIVATE", f"{PROJECT}-spec": "PRIVATE",
      f"{PROJECT}-code": "PRIVATE"}, (),
     [f"NOTE {SPEC_REPO} and {CODE_REPO} are private{READ_THEM}"]),
    # Both legs public: no note.
    ({PROJECT: "PUBLIC", f"{PROJECT}-spec": "PUBLIC",
      f"{PROJECT}-code": "PUBLIC"}, ("--visibility", "public"), []),
], ids=["reused-public-leg-under-private", "reused-closed-legs-under-public",
        "created-public-reused-private", "both-private", "both-public"])
def test_the_visibility_text_follows_each_leg_as_it_stands(
        tmp_path, repos, flags, said):
    """The reuse re-run's visibility lines (#542). `_private_leg_note` names
    each leg that is private or internal at the visibility it has, a reused
    one's read from GitHub, and no other; `_leg_visibility`'s two lines,
    printed before anything is asked of the legs, no longer call them "the
    two new legs", which a re-run that reuses one or both is not."""
    env, _log = fake_gh(tmp_path, repos)
    result = on_github(tmp_path, "--reuse-empty-repo", *flags, env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    printed = result.stdout + result.stderr
    for line in said:
        assert line in printed, printed
    notes = [line for line in result.stdout.splitlines()
             if line.startswith("NOTE ") and "a way to read" in line]
    assert len(notes) == len([line for line in said if "a way to read" in line
                              ]), notes
    assert "two new legs" not in printed


#: The Free-plan hint's subject is the root, where the `validate` workflow
#: runs. On the Free plan an organisation secret reaches only a public
#: repository, so the hint is true when the root is private or internal and
#: false when it is public, whatever a leg is. `None` is no hint; otherwise
#: the repository it names as the reason, as `FREE_PLAN_HINT` puts it before
#: " private, so": the root (#602), where it named the closed legs.
ROOT_IS = f"{ORG}/{PROJECT} is"
#: An INTERNAL root is not called private (#994): the hint's `what` says it is
#: internal, which the hint treats as private.
INTERNAL_ROOT_IS = f"{ROOT_IS} internal, which this hint treats as"
#: What the hint named as its reason before #602, which no row may print.
LEG_SUBJECTS = (f"{SPEC_REPO} is", f"{CODE_REPO} is",
                f"{SPEC_REPO} and {CODE_REPO} are")


@WINDOWS_SKIP
@pytest.mark.parametrize("repos,flags,plan,named", [
    # A public run that creates the root and reuses a private code leg: the
    # root is public, so its workflow is given the organisation's secrets.
    ({f"{PROJECT}-code": "PRIVATE"}, ("--visibility", "public"), "free", None),
    # The same with the root reused, public on GitHub.
    ({PROJECT: "PUBLIC", f"{PROJECT}-code": "PRIVATE"},
     ("--visibility", "public"), "free", None),
    # A public root reused with no flag: the run, and the leg it creates,
    # inherit public, and both reused legs are private.
    ({PROJECT: "PUBLIC", f"{PROJECT}-spec": "PRIVATE",
      f"{PROJECT}-code": "PRIVATE"}, (), "free", None),
    # The run's flag is not the root: `--visibility private` over a root that
    # is public on GitHub, and the root is what has the workflow.
    ({PROJECT: "PUBLIC", f"{PROJECT}-spec": "PRIVATE",
      f"{PROJECT}-code": "PRIVATE"}, ("--visibility", "private"), "free",
     None),
    # And the other way: a public run over a root that is private on GitHub.
    ({PROJECT: "PRIVATE", f"{PROJECT}-code": "PRIVATE"},
     ("--visibility", "public"), "free", ROOT_IS),
    # An internal root is closed too, and its run creates the spec leg
    # internal. The hint does not call it private (#994).
    ({PROJECT: "INTERNAL", f"{PROJECT}-code": "PRIVATE"}, (), "free",
     INTERNAL_ROOT_IS),
    # Controls: a private root with both legs private, reused and created
    # new, gets the hint as before, with the root as its subject (#602 moved
    # only that); and a paid plan says nothing.
    ({PROJECT: "PRIVATE", f"{PROJECT}-spec": "PRIVATE",
      f"{PROJECT}-code": "PRIVATE"}, (), "free", ROOT_IS),
    ({}, (), "free", ROOT_IS),
    ({PROJECT: "PRIVATE", f"{PROJECT}-spec": "PRIVATE",
      f"{PROJECT}-code": "PRIVATE"}, (), "team", None),
], ids=["public-run-new-root", "public-root-reused",
        "public-root-inherited", "private-flag-over-public-root",
        "public-flag-over-private-root", "internal-root",
        "private-root-reused-legs", "private-run-new-repositories",
        "paid-plan"])
def test_the_free_plan_hint_goes_by_the_root_as_it_stands(
        tmp_path, repos, flags, plan, named):
    """#542. `_private_leg_note` printed the Free-plan hint whenever a leg was
    private or internal, so a public root that reused a private leg was told
    its organisation secrets "resolve to EMPTY inside the workflow", which on
    the Free plan holds only of a private one. The per-leg NOTE is printed
    in every case a leg is closed, since a public root still needs a
    credential to read a private leg; the hint only when the root, as it
    stands, is private or internal: GitHub's for a reused root, else the
    run's. #602: and it names the root as the repository that is private,
    where it named the closed legs, which are not why the secrets resolve to
    EMPTY."""
    env, _log = fake_gh(tmp_path, repos, plan=plan)
    result = on_github(tmp_path, "--reuse-empty-repo", *flags, env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    printed = result.stdout + result.stderr
    assert "a way to read" in printed, printed
    if named is None:
        assert "resolve to EMPTY" not in printed, printed
    else:
        assert f"NOTE {ORG} is on the GitHub FREE plan" in printed, printed
        assert f"{named} private, so org-level" in printed, printed
        assert (f"{ROOT_IS} private, so" in printed) == (named == ROOT_IS), \
            printed
        assert printed.count("resolve to EMPTY") == 1, printed
    for subject in LEG_SUBJECTS:
        assert f"{subject} private, so" not in printed, printed


# --- a leg that gh sees and git cannot read (#542) --------------------------

def test_the_two_git_commands_that_read_a_leg_ask_no_terminal(
        tmp_path, monkeypatch):
    """`only_commit`'s `git ls-remote` and `git fetch`, the two commands
    that reach the leg, run under `PROBE_ENV`: `GIT_TERMINAL_PROMPT=0`
    (#542), the prompt rule `REMOTE_ENV` every command that reaches a remote
    runs under, and `LC_ALL=C`, so `_unread_because` reads git's words
    untranslated (#915). Asked in-process of a leg on disk, so it runs on
    every platform, Windows included, where the terminal test below
    cannot."""
    spec = importlib.util.spec_from_file_location("scaffold_for_probe_env",
                                                  SCAFFOLD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.REMOTE_ENV == {"GIT_TERMINAL_PROMPT": "0"}
    assert module.PROBE_ENV == {"GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
    asked = []
    real = module.run

    def recording(args, cwd=None, capture=True, env=None):
        asked.append((args[1], env))
        return real(args, cwd=cwd, capture=capture, env=env)

    monkeypatch.setattr(module, "run", recording)
    theirs_at_one_commit(tmp_path)
    held = module.only_commit(str(bare(tmp_path, "spec")), tmp_path / "probe")
    assert held is not None, asked
    assert held[0] == tip(tmp_path, "spec"), asked
    assert {verb: env for verb, env in asked
            if verb in ("ls-remote", "fetch")} == {
        "ls-remote": module.PROBE_ENV, "fetch": module.PROBE_ENV}, asked


#: The verbs of the git commands this scaffold sends to a remote.
REACHES_A_REMOTE = ("ls-remote", "fetch", "push")


def test_every_git_command_that_reaches_a_remote_runs_under_the_rule(
        tmp_path, monkeypatch, capsys, template):
    """#915. `PROBE_ENV` covered `only_commit`'s two commands alone, and a
    reuse re-run's other three ran with git's terminal prompt on:
    `_take_held_seed`'s fetch, each leg's push and the root's. A re-run over
    legs that hold the seed, in-process, records each git command that
    reaches a remote, in order, with the environment it was given: the
    probe's two for each leg under `PROBE_ENV`, then each leg's fetch and
    push, and the root's push, the fetches under `REMOTE_ENV` and the pushes
    under `PUSH_ENV`, which also keeps git's words untranslated for
    `_refused_push` to read (#993). Asked of bare repositories on disk, so it
    runs on every platform."""
    seeds = refused_at_the_root(tmp_path, template)
    module = load_without_bytecode(SCAFFOLD, "scaffold_for_remote_env")
    assert module.PUSH_ENV == {"GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
    asked = []
    real = module.run

    def recording(args, cwd=None, capture=True, env=None):
        if args[1] in REACHES_A_REMOTE:
            asked.append((" ".join(args[1:2] + [arg for arg in args
                                                 if arg == "--depth=1"]),
                          env))
        return real(args, cwd=cwd, capture=capture, env=env)

    monkeypatch.setattr(module, "run", recording)
    code = module.main(["--org", ORG, "--project", PROJECT,
                        "--elected-by", "Test Human",
                        "--elected-on", "2026-09-02",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"),
                        "--reuse-empty-repo"])
    out, err = capsys.readouterr()
    assert code == 0, err + out
    assert {leg: tip(tmp_path, leg) for leg in LEGS} == seeds
    assert commits(tmp_path, "assembly") == 1
    probe, rule, push = module.PROBE_ENV, module.REMOTE_ENV, module.PUSH_ENV
    assert asked == [("ls-remote", probe), ("fetch --depth=1", probe),
                     ("ls-remote", probe), ("fetch --depth=1", probe),
                     ("fetch", rule), ("push", push),
                     ("fetch", rule), ("push", push),
                     ("push", push)], asked


def git_reads_github_from(base: str, helper: str = "") -> dict:
    """What makes git read `https://github.com/<ORG>/` at `base` instead,
    with no askpass program and no credential helper but `helper`, so git
    answers a leg as it would with no login of its own. The prefix is longer
    than an operator's own `https://github.com/` rewrite, so it wins over
    one. An empty `credential.helper` empties the list a config before it
    made, and `helper` is the one after it. The entries are appended, when
    this is called, to the command scope the environment holds."""
    return {**appended_to_command_scope(
                os.environ, [(f"url.{base}.insteadOf",
                              f"https://github.com/{ORG}/"),
                             ("credential.helper", ""),
                             *([("credential.helper", helper)] if helper
                               else [])]),
            "GIT_ASKPASS": ""}


#: The legs `gh` sees: the spec leg, holding commits. The root and the code
#: leg do not exist, so nothing but the spec leg is asked of git.
SEEN_SPEC = {f"{PROJECT}-spec": "PRIVATE"}
UNREAD = (f"REFUSED scaffold-remote-exists: {SPEC_REPO} already exists on "
          "GitHub and has commits\nRemediation: git could not read it "
          f"(`git ls-remote https://github.com/{SPEC_REPO}.git` exited 128: "
          "fatal: ")
#: The ssh key's clause, as each remedy for git's access names it (#915):
#: `ssh -T` against the user, host and port the rule names, with what
#: `GIT_SSH_COMMAND` or `core.sshCommand` adds, which `ssh -T git@github.com`
#: was not for a `Host` alias, `ssh.github.com` on port 443 or a key given by
#: `-i` (RV971), and which `ssh -T -p 443 ssh.github.com` without the user
#: `git` was not either: GitHub refuses it whatever the key (RV971, round 2).
SSH_KEY_CHECK = ("`ssh -T` against the user, host and port your rule names, "
                 "with anything your `GIT_SSH_COMMAND` or `core.sshCommand` "
                 "adds, says whether GitHub takes yours")
SSH_KEY = ("where a `url.<base>.insteadOf` rule in your git config sends "
           "`https://github.com/` over ssh, git logs in with an ssh key "
           f"instead, and {SSH_KEY_CHECK}")
#: What each remedy that sends a person into the `--reuse-empty-repo`
#: re-run on GitHub ends with (#915, U037; Brett Heap, 2026-10-21, "U039 and
#: U037: take your recommendations"): that re-run turns off git's own
#: prompt alone, and ssh, a credential helper and an askpass program, which
#: are the operator's and stay as they set them up, can still make it wait.
#: A literal, so the test cannot agree with whatever the code's words become.
STILL_ASKS = (
    " That re-run turns off git's own terminal prompt and no other, so it "
    "can still wait at an ssh passphrase or host-key prompt, at a credential "
    "helper that prompts, or at `GIT_ASKPASS`, `SSH_ASKPASS` or "
    "`core.askPass`: to keep it from waiting, load your key into an ssh "
    "agent, use a helper that answers without prompting, or set "
    "`GIT_SSH_COMMAND='ssh -o BatchMode=yes'` (with anything your "
    "`core.sshCommand` adds) in your shell for the run, which makes ssh fail "
    "at once instead.")
UNREAD_EXIT = ("so whether its one commit is the seed this scaffold pushes "
               "cannot be asked. Let git read it (on GitHub, `gh auth "
               f"setup-git` gives git the login `gh` has; {SSH_KEY}), then "
               "re-run: with --reuse-empty-repo a leg whose one commit is "
               "that seed is reused, and a leg holding anything else is "
               "still refused. There is no --force." + STILL_ASKS)


@WINDOWS_SKIP
@pytest.mark.parametrize("flags", [(), ("--reuse-empty-repo",)],
                         ids=["without-the-flag", "with-the-flag"])
def test_a_leg_git_cannot_read_is_refused_as_existing_not_as_a_failure(
        tmp_path, flags):
    """On main through bfed143 `_held_seed` let `only_commit`'s
    `CommandFailed` through, so a leg `gh` sees with commits and git cannot
    read was `REFUSED a git or gh command failed`, the generic line; with
    the flag and without it, since the seed is asked either way. Now it is
    `scaffold-remote-exists`, saying git could not read it, before anything
    is created."""
    env, log = fake_gh(tmp_path, SEEN_SPEC, full=[f"{PROJECT}-spec"])
    env.update(git_reads_github_from(f"{tmp_path / 'unreadable'}/"))
    result = on_github(tmp_path, *flags, env=env, cwd=tmp_path)
    assert result.returncode == 2, result.stderr + result.stdout
    assert "a git or gh command failed" not in result.stderr
    assert UNREAD in result.stderr, result.stderr
    assert "does not appear to be a git repository), " + UNREAD_EXIT in (
        result.stderr), result.stderr
    assert "repo create" not in log.read_text(encoding="utf-8"), (
        "nothing was created")


class _AsksForALogin(http.server.BaseHTTPRequestHandler):
    """A git host that answers every request 401, as GitHub answers git for
    a private repository it is given no login for."""

    def do_GET(self):  # noqa: N802 - the name `BaseHTTPRequestHandler` calls
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="w542"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_POST = do_GET

    def log_message(self, *args):  # the test reads the screen, not this
        pass


def in_a_terminal_asked_for_a_login(tmp_path, env: dict, *flags: str,
                                    helper: str = "", stored: str = "",
                                    said: str = "terminal prompts disabled",
                                    timeout: float = 90) -> tuple:
    """The scaffold in its GitHub mode with `flags`, a first run or, with
    `--reuse-empty-repo` among them, a re-run, typed in a terminal, with
    `env` (a `fake_gh`'s) and git reading `https://github.com/<ORG>/` from a
    local server that answers every request 401, with `helper` as its one
    credential helper or none, or, given `stored`, a `user:token` login, a
    `store` helper holding that login for the server, which refuses it as a
    host refuses a stale token (#993): `(exit status, the screen)`, the
    screen holding `said`, git's words for the refusal. A run that waits at
    git's prompt is killed after `timeout` seconds, which fails the test."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _AsksForALogin)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        port = server.server_address[1]
        if stored:
            store = tmp_path / "stored-login"
            store.write_text(f"http://{stored}@127.0.0.1:{port}\n",
                             encoding="utf-8")
            helper = f'store --file="{store}"'
        status, screen, _typed = run_in_a_terminal(
            [sys.executable, str(SCAFFOLD), "--org", ORG, "--project",
             PROJECT, "--elected-by", "Test Human", *flags,
             "--work-dir", str(tmp_path / "work")],
            cwd=tmp_path, timeout=timeout,
            env={**os.environ, **env, "LANES_LANE": "",
                 **git_reads_github_from(f"http://127.0.0.1:{port}/{ORG}/",
                                         helper)})
    finally:
        server.shutdown()
        server.server_close()
    # git's prompt starts a line; its refusal says `could not read Username
    # for '...': terminal prompts disabled` inside a line of its own.
    assert not re.search(r"(?m)^Username for ", screen), screen
    assert said in screen, screen
    return status, screen


@WINDOWS_SKIP
@PTY_SKIP
def test_a_leg_git_would_ask_a_login_for_does_not_wait_on_the_terminal(
        tmp_path):
    """`only_commit` runs git with `GIT_TERMINAL_PROMPT=0` (#542). Typed in a
    terminal, a re-run whose leg git has no login for stopped at git's
    `Username for ...:` prompt before a word about the leg; on main through
    bfed143 this run waits there until the harness kills it. Now git's ask
    is a failure, and the run is refused as `scaffold-remote-exists`."""
    env, _log = fake_gh(tmp_path, SEEN_SPEC, full=[f"{PROJECT}-spec"])
    status, screen = in_a_terminal_asked_for_a_login(
        tmp_path, env, "--reuse-empty-repo", "--no-push")
    assert status == 2, screen
    assert f"REFUSED scaffold-remote-exists: {SPEC_REPO} already exists" in (
        screen), screen


@WINDOWS_SKIP
@PTY_SKIP
def test_a_reuse_re_run_over_empty_legs_does_not_wait_at_its_push(tmp_path):
    """#915. A `--reuse-empty-repo` re-run whose three repositories are all
    empty asks `only_commit` nothing, so its first push, the spec leg's, was
    the first git command to reach GitHub, and it ran with git's terminal
    prompt on: typed in a terminal with no login for the host, it stopped at
    `Username for '...':`, and on main through 01a2b01 this run waits there
    until the harness kills it. Now each push runs under `REMOTE_ENV`, and
    git's ask is a refused push, printed as one with how to give git a login
    and the re-run, this run's own command, before the ruleset hint."""
    env, log = fake_gh(tmp_path, {PROJECT: "PRIVATE",
                                  f"{PROJECT}-spec": "PRIVATE",
                                  f"{PROJECT}-code": "PRIVATE"}, plan="team")
    status, screen = in_a_terminal_asked_for_a_login(
        tmp_path, env, "--reuse-empty-repo", timeout=120)
    assert status == 2, screen
    assert "REFUSED pushing the spec leg. THE EXACT COMMAND WAS:" in screen, (
        screen)
    assert_the_login_is_named(screen, SPEC_REPO, RE_RUN_AS_IT_WAS)
    assert "repo create" not in log.read_text(encoding="utf-8"), (
        "a reused repository is never created")


# --- a push git has no login for (#915) -------------------------------------

#: How `_refused_push` names the fix for a push git had no login for, up to
#: the re-run, with the repository as `@REPO@`. A literal, so the test cannot
#: agree with whatever the code's words become.
NO_LOGIN_REMEDY = (
    "Remediation: git could not get a login for @REPO@: every push this "
    "scaffold makes runs with git's terminal prompt off, so where git would "
    "have asked you for one the push is refused, and a credential helper "
    "with nothing stored for the host answers nothing. Give git a login "
    "first (on GitHub, `gh auth setup-git` gives git the login `gh` has, or "
    "store a token for the host in your credential helper; "
    f"{SSH_KEY}), then re-run ")
#: The re-run it names after a first run: the same command, the flag added,
#: and the prompts that re-run can still wait at (`STILL_ASKS`, #915 U037).
RE_RUN_WITH_THE_FLAG = (
    "the same command with --reuse-empty-repo added (after `--` through "
    "setup.sh) and a new --work-dir or none: it reuses the repositories this "
    "run left empty, and a leg whose one commit is the seed this scaffold "
    "pushes." + STILL_ASKS)
#: And after a run that was that re-run: the same command again.
RE_RUN_AS_IT_WAS = (
    "the same command with a new --work-dir or none: it reuses the "
    "repositories this run left empty, and a leg whose one commit is the "
    "seed this scaffold pushes." + STILL_ASKS)


#: How it names the fix for a push whose login the host refused (#993): git
#: had one, so "could not get" is not said of it.
LOGIN_REFUSED_REMEDY = (
    "Remediation: the host refused the login git sent for @REPO@: git had "
    "one, from your credential helper for one, and it is wrong, expired or "
    "revoked, so a re-run is refused too until git has one the host takes. "
    "Replace it first (on GitHub, `gh auth setup-git` makes git use the login "
    "`gh` has instead, or store a new token for the host in your credential "
    f"helper; {SSH_KEY}), then re-run ")
#: And for a push ssh was refused the key for (#993): `setup-git` is not
#: named as a fix, since it changes nothing over ssh.
KEY_REFUSED_REMEDY = (
    "Remediation: GitHub took no ssh key of yours for the push to @REPO@: a "
    "`url.<base>.insteadOf` or `url.<base>.pushInsteadOf` rule in your git "
    "config sends it over ssh, where git logs in with an ssh key and not with "
    "the login `gh` has, so `gh auth setup-git` changes nothing for it. Give "
    f"GitHub a key it takes first ({SSH_KEY_CHECK}), then re-run ")


def assert_the_login_is_named(printed: str, repo: str, re_run: str,
                              fix: str = NO_LOGIN_REMEDY) -> None:
    """`printed` says a push was refused, then `fix`, how to give git a login
    for `repo`, then `re_run`, then the ruleset hint: the remedy once, read
    with its lines joined, as a person reads a line the terminal wrapped."""
    said = " ".join(printed.split())
    remedy = fix.replace("@REPO@", repo) + re_run
    assert said.count(remedy) == 1, printed
    assert (said.index("REFUSED pushing ") < said.index(remedy)
            < said.index("If the organisation applies a ruleset")), printed


@WINDOWS_SKIP
@PTY_SKIP
@pytest.mark.parametrize("helper", ["", "store"],
                         ids=["no-helper", "a-store-with-nothing-stored"])
def test_a_first_scaffold_s_push_git_has_no_login_for_names_the_fix(
        tmp_path, helper):
    """#915, RV971's MUST-1. A first scaffold's pushes are the same call as
    a re-run's, so the prompt is off for them too. Typed in a terminal
    against a host that asks for a login, with no credential helper, or
    with `store` over an empty file (a helper `setup-project.py` counts as
    configured, with nothing to give), git asked at `Username for '...':`
    before #915, took what was typed, and pushed (RV971's probe). Now the
    spec leg's push is refused without waiting, the three repositories this
    run created are left empty, and before the ruleset hint, whose re-run
    alone is refused the same way, the run names how to give git a login
    and then the re-run with --reuse-empty-repo. With the rule on a
    re-run's pushes alone (RV971's M10), this run waits at git's prompt
    until the harness kills it."""
    env, log = fake_gh(tmp_path, {}, plan="team")
    store = tmp_path / "git-credentials"
    store.write_text("", encoding="utf-8")
    status, screen = in_a_terminal_asked_for_a_login(
        tmp_path, env, helper=f'store --file="{store}"' if helper else "",
        timeout=120)
    assert status == 2, screen
    assert "REFUSED pushing the spec leg. THE EXACT COMMAND WAS:" in screen, (
        screen)
    assert_the_login_is_named(screen, SPEC_REPO, RE_RUN_WITH_THE_FLAG)
    assert log.read_text(encoding="utf-8").count("repo create") == 3, (
        "a first run creates all three")
    assert store.read_text(encoding="utf-8") == "", "nothing was stored"


#: What the GitHub side holds for a re-run: the three repositories, empty.
ALL_THREE = {PROJECT: "PRIVATE", f"{PROJECT}-spec": "PRIVATE",
             f"{PROJECT}-code": "PRIVATE"}


@WINDOWS_SKIP
@PTY_SKIP
@pytest.mark.parametrize("flags,repos,re_run", [
    ((), {}, RE_RUN_WITH_THE_FLAG),
    (("--reuse-empty-repo",), ALL_THREE, RE_RUN_AS_IT_WAS),
], ids=["a-first-run", "a-re-run"])
def test_a_push_whose_stored_login_the_host_refuses_names_the_fix(
        tmp_path, git_language, flags, repos, re_run):
    """#993. A stored login the host refuses is not one git could not get:
    git sends the token its credential helper holds, the host answers 401,
    and git dies `Authentication failed for '<url>'`, which holds none of
    `NO_LOGIN`'s words, so on main through 04923f1 the push printed the
    ruleset hint alone, whose re-run pushes with the same login. Typed in a
    terminal, with `store` holding a token the local server refuses, a first
    run and a re-run each exit 2 without waiting, and name the login the
    host refused, how to replace it and the re-run, before the hint.

    `translated` runs git where it speaks another language, whose catalogue
    translates `Authentication failed for` (`XX_GIT`): each push runs under
    `PUSH_ENV`, so git's words are found there too; under `REMOTE_ENV` they
    were not, and the run printed the hint alone."""
    env, log = fake_gh(tmp_path, repos, plan="team")
    env.update(git_language)
    status, screen = in_a_terminal_asked_for_a_login(
        tmp_path, env, *flags, stored="someone:badtoken",
        said="fatal: Authentication failed for ", timeout=120)
    assert status == 2, screen
    assert "REFUSED pushing the spec leg. THE EXACT COMMAND WAS:" in screen, (
        screen)
    assert_the_login_is_named(screen, SPEC_REPO, re_run,
                              fix=LOGIN_REFUSED_REMEDY)
    assert "could not get a login" not in screen, screen
    assert log.read_text(encoding="utf-8").count("repo create") == (
        0 if flags else 3), "a first run creates all three, a re-run none"


# --- a leg git reaches over ssh (#915) --------------------------------------

#: What ssh prints when GitHub takes none of its keys, on stderr, before it
#: exits 255. git then prints its generic `fatal:` line, and nothing of
#: ssh's has a `fatal:` of its own.
REFUSED_KEY = "git@github.com: Permission denied (publickey)."


def fake_ssh(says: str) -> str:
    """An ssh that says `says` on stderr to every command line and exits
    255, so nothing leaves this machine."""
    return textwrap.dedent(f"""\
        import sys
        print({says!r}, file=sys.stderr)
        sys.exit(255)
        """)


def git_reaches_github_over_ssh(tmp_path, rule: str = "insteadOf",
                                says: str = REFUSED_KEY) -> dict:
    """What an operator's git config that rewrites `https://github.com/` to
    ssh does (#915), for `https://github.com/<ORG>/`, appended to the
    command scope the environment holds, with `fake_ssh(says)` as the ssh
    git runs, which says `REFUSED_KEY` unless told otherwise (#1108).
    `rule` is `insteadOf`, for every command, or `pushInsteadOf`, for pushes
    alone (#993). `GIT_SSH_VARIANT` says it takes OpenSSH's options, which
    git would otherwise find out by running it once more, with `-G`."""
    ssh = tmp_path / "fake_ssh.py"
    ssh.write_text(fake_ssh(says), encoding="utf-8")
    return {**appended_to_command_scope(
                os.environ, [(f"url.ssh://git@github.com/{ORG}/.{rule}",
                              f"https://github.com/{ORG}/")]),
            "GIT_SSH_COMMAND": f'"{sys.executable}" "{ssh}"',
            "GIT_SSH_VARIANT": "ssh"}


#: glibc's own `C.UTF-8`, which a test copies under a name of its own into
#: a `LOCPATH` of its own: a locale that is not `C`, so gettext reads
#: `LANGUAGE`, and needs nothing installed beyond the C library's.
C_UTF8 = Path("/usr/lib/locale/C.utf8")
#: What git prints for `fatal: ` in `xx`, the test's own language.
XX_FATAL = "XX-FATAL: "
#: A catalogue for git in `xx`: the `fatal: ` before every fatal line, git's
#: generic message with its advice, and its line for a login the host
#: refused (#993), translated as a person's locale translates them, so where
#: git speaks `xx` none is in git's words.
XX_GIT = {
    "": "Content-Type: text/plain; charset=UTF-8\nLanguage: xx\n",
    "fatal: ": XX_FATAL,
    "Authentication failed for '%s'": "XX the host said no to '%s'",
    "Could not read from remote repository.\n\nPlease make sure you have "
    "the correct access rights\nand the repository exists.":
        "XX could not read the remote.\n\nXX make sure of your rights\n"
        "XX and that the repository is there.",
}


def mo_bytes(messages: dict) -> bytes:
    """`messages` as a GNU gettext catalogue, a `.mo` file, so no `msgfmt` is
    needed: the header (magic, revision 0, the count, where each table is,
    no hash table), a table of each original's length and offset, sorted by
    original, a table of each translation's, then the strings, each ended
    by a NUL. Little-endian; gettext reads either order by the magic."""
    originals = sorted(messages)  # code-point order is UTF-8's byte order
    keys = [key.encode("utf-8") for key in originals]
    values = [messages[key].encode("utf-8") for key in originals]
    count = len(originals)
    strings = 7 * 4 + 2 * 8 * count
    tables = []
    at = strings
    for column in (keys, values):
        for text in column:
            tables += [len(text), at]
            at += len(text) + 1
    return (struct.pack("<7I", 0x950412DE, 0, count, 7 * 4,
                        7 * 4 + 8 * count, 0, 0)
            + struct.pack(f"<{4 * count}I", *tables)
            + b"".join(text + b"\0" for text in keys + values))


def git_speaks_xx(tmp_path) -> dict:
    """What makes git speak `xx` (`XX_GIT`): `LOCPATH` holds `C_UTF8` as
    `xx_XX.UTF-8`, `LC_ALL` names it, `LANGUAGE` asks for `xx`, and
    `GIT_TEXTDOMAINDIR` holds the catalogue. Skipped where there is no
    `C_UTF8` to copy, and where git, asked once of a path that is no
    repository, does not speak it: a git built without gettext, or a C
    library that reads no `LOCPATH`."""
    if not C_UTF8.is_dir():
        pytest.skip(f"no {C_UTF8} to copy as a locale of the test's own")
    kit = tmp_path / "xx"
    shutil.copytree(C_UTF8, kit / "locales" / "xx_XX.UTF-8")
    catalogue = kit / "catalogues" / "xx" / "LC_MESSAGES"
    catalogue.mkdir(parents=True)
    (catalogue / "git.mo").write_bytes(mo_bytes(XX_GIT))
    speaks = {"LOCPATH": str(kit / "locales"), "LC_ALL": "xx_XX.UTF-8",
              "LANGUAGE": "xx", "GIT_TEXTDOMAINDIR": str(kit / "catalogues")}
    asked = subprocess.run(["git", "ls-remote", str(kit / "no-repository")],
                           env={**os.environ, **speaks}, capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           check=False)
    if not asked.stderr.startswith(XX_FATAL):
        pytest.skip("git here does not speak a catalogue from "
                    f"GIT_TEXTDOMAINDIR: {asked.stderr.strip()[:200]}")
    return speaks


@pytest.fixture(params=["as-it-is", "translated"])
def git_language(request, tmp_path) -> dict:
    """What a test adds to its environment to run git as it is (`{}`) or
    translated (`git_speaks_xx`, RV971's kit). Only the translated row is
    skipped where `git_speaks_xx` skips; the other row runs there."""
    return {} if request.param == "as-it-is" else git_speaks_xx(tmp_path)


@WINDOWS_SKIP
def test_a_leg_git_reaches_over_ssh_is_refused_with_ssh_s_reason(
        tmp_path, git_language):
    """#915. Where git config rewrites `https://github.com/` to ssh, git's
    one `fatal:` line for a leg ssh could not log in to is the generic
    `Could not read from remote repository.`, and ssh's own reason, which
    has no `fatal:`, was dropped: the refusal said git could not read the
    leg and not why, and named `gh auth setup-git` alone, which changes
    nothing for git over ssh. Now ssh's last line is the reason, and the
    remedy names the ssh key beside `setup-git`.

    `translated` asks it where git speaks another language (`git_speaks_xx`,
    RV971's kit). `only_commit`'s git runs under `LC_ALL=C` (`PROBE_ENV`),
    so its `fatal:` and its generic line are found there too; without it no
    line started `fatal:`, and the reason was git's last line, advice about
    its own command (RV971's M4)."""
    env, log = fake_gh(tmp_path, SEEN_SPEC, full=[f"{PROJECT}-spec"])
    env.update(git_reaches_github_over_ssh(tmp_path))
    env.update(git_language)
    result = on_github(tmp_path, "--reuse-empty-repo", env=env, cwd=tmp_path)
    assert result.returncode == 2, result.stderr + result.stdout
    assert (f"REFUSED scaffold-remote-exists: {SPEC_REPO} already exists on "
            "GitHub and has commits\nRemediation: git could not read it "
            f"(`git ls-remote https://github.com/{SPEC_REPO}.git` exited "
            f"128: {REFUSED_KEY}), {UNREAD_EXIT}") in result.stderr, (
        result.stderr)
    assert "Could not read from remote repository" not in result.stderr
    assert "repo create" not in log.read_text(encoding="utf-8"), (
        "nothing was created")


@WINDOWS_SKIP
@pytest.mark.parametrize("rule", ["insteadOf", "pushInsteadOf"])
def test_a_push_ssh_was_refused_the_key_for_names_the_fix(
        tmp_path, git_language, rule):
    """#993. Where git config sends a first scaffold's push over ssh, by an
    `insteadOf` rule or a `pushInsteadOf` one, and the host takes no key,
    ssh says `Permission denied (publickey).` and git its generic line,
    neither of them `NO_LOGIN`'s words, so on main through 04923f1 the push
    printed the ruleset hint alone. Now the run exits 2 and names the ssh
    check, then the re-run with the flag, then the hint, and not `gh auth
    setup-git`, which changes nothing over ssh. ssh's words are its own and
    untranslated, so `translated` finds them too."""
    env, log = fake_gh(tmp_path, {}, plan="team")
    env.update(git_reaches_github_over_ssh(tmp_path, rule))
    env.update(git_language)
    result = run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                        "--elected-by", "Test Human",
                        "--work-dir", str(tmp_path / "work"),
                        cwd=tmp_path, env=env)
    assert result.returncode == 2, result.stderr + result.stdout
    assert "REFUSED pushing the spec leg. THE EXACT COMMAND WAS:" in (
        result.stderr), result.stderr
    assert REFUSED_KEY in result.stderr, result.stderr
    assert_the_login_is_named(result.stderr, SPEC_REPO, RE_RUN_WITH_THE_FLAG,
                              fix=KEY_REFUSED_REMEDY)
    assert "setup-git` gives git" not in result.stderr, result.stderr
    assert log.read_text(encoding="utf-8").count("repo create") == 3, (
        "a first run creates all three")


# --- a push ssh refused the host's key for (#1108) ---------------------------

#: What OpenSSH 9.6 printed, measured against a fake server through a
#: ProxyCommand, where the host's key was in no known_hosts file: that line
#: alone under `BatchMode=yes`, answered no, and with no terminal to ask in,
#: and after `NOT_KNOWN_STRICTLY` under `StrictHostKeyChecking=yes`. git's
#: generic line follows it.
UNKNOWN_HOST_KEY = "Host key verification failed."
NOT_KNOWN_STRICTLY = ("No ED25519 host key is known for github.com and you "
                      "have requested strict checking.\n" + UNKNOWN_HOST_KEY)
#: And where the host sent a key other than the one known_hosts held for it,
#: with `BatchMode=yes` and without: the banner, the new key's fingerprint
#: and the `ssh-keygen -R` line, then `UNKNOWN_HOST_KEY`'s words. The
#: measured server's name and file are GitHub's and root's here.
CHANGED_HOST_KEY = (
    "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@\n"
    "@    WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!     @\n"
    "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@\n"
    "IT IS POSSIBLE THAT SOMEONE IS DOING SOMETHING NASTY!\n"
    "Someone could be eavesdropping on you right now (man-in-the-middle "
    "attack)!\n"
    "It is also possible that a host key has just been changed.\n"
    "The fingerprint for the ED25519 key sent by the remote host is\n"
    "SHA256:mbL0wrypDk6+kSG4m6mdpKUCCVRWcJVA+1FnGrp2L5o.\n"
    "Please contact your system administrator.\n"
    "Add correct host key in /root/.ssh/known_hosts to get rid of "
    "this message.\n"
    "Offending ED25519 key in /root/.ssh/known_hosts:1\n"
    "  remove with:\n"
    "  ssh-keygen -f '/root/.ssh/known_hosts' -R 'github.com'\n"
    "Host key for github.com has changed and you have requested strict "
    "checking.\n" + UNKNOWN_HOST_KEY)
#: How each remedy for a host key has a person see the key's fingerprint
#: and keep it: `ssh -T` as git runs ssh, but with `-o BatchMode=no -o
#: StrictHostKeyChecking=ask` first, which ssh keeps over the person's
#: ssh_config and a later `-o` (a `BatchMode yes` there refuses an unknown
#: key without showing or asking, an `accept-new` keeps it without showing
#: or asking, a `yes` refuses without asking; measured, OpenSSH 9.6); and
#: where GitHub's own are read, over https rather than the connection in
#: doubt, for github.com, each without the `SHA256:` ssh shows before it.
SEE_THE_KEY = ("`ssh -T -o BatchMode=no -o StrictHostKeyChecking=ask`, both "
               "options first so that they win over your ssh_config and any "
               "later `-o`, against the user, host and port your rule names, "
               "with the rest of what your `GIT_SSH_COMMAND` or "
               "`core.sshCommand` adds, shows the fingerprint of the key the "
               "host sends and asks whether to keep it")
PUBLISHED = ("`gh api --hostname github.com meta --jq "
             ".ssh_key_fingerprints` prints them, and ssh shows each with "
             "`SHA256:` before it")
#: How `_refused_push` names the fix for a key ssh does not know, up to the
#: re-run, with the repository as `@REPO@`. A literal, so the test cannot
#: agree with whatever the code's words become.
UNKNOWN_HOST_KEY_REMEDY = (
    "Remediation: ssh could not verify the key of the host the push to "
    "@REPO@ reached: a `url.<base>.insteadOf` or `url.<base>.pushInsteadOf` "
    "rule in your git config sends it over ssh, that key is in none of your "
    "known_hosts files, and ssh refused it without asking, as under "
    "`BatchMode=yes`, or was answered no, so nothing was pushed, and a "
    "re-run is refused the same way until ssh holds the key. Keep it first, "
    f"once you know it is GitHub's: {SEE_THE_KEY}, so answer yes only to a "
    f"fingerprint GitHub publishes ({PUBLISHED}), then re-run ")
#: And for a key that changed, which a machine in the middle of the
#: connection shows too: nothing accepted, removed or pushed before its
#: fingerprint is checked against GitHub's.
CHANGED_HOST_KEY_REMEDY = (
    "Remediation: the host the push to @REPO@ reached sent ssh a key other "
    "than the one your known_hosts holds for it: a `url.<base>.insteadOf` or "
    "`url.<base>.pushInsteadOf` rule in your git config sends it over ssh, "
    "and ssh refuses a changed key, so nothing was pushed, and a re-run is "
    "refused the same way. A machine in the middle of the connection shows "
    "this as well as a key GitHub replaced, so accept no key from that host, "
    "and push nothing to it, until you have checked that the fingerprint ssh "
    f"printed above is one GitHub publishes ({PUBLISHED}); only then remove "
    "the old key (the `ssh-keygen -R` line ssh printed) and keep the new one "
    f"({SEE_THE_KEY}), answering yes only to a fingerprint GitHub "
    "publishes, which can be another of its keys than the one you "
    "checked, then re-run ")
#: What the scaffold prints after the ruleset hint on GitHub (#1108): the
#: prompts the hint's re-run can still wait at, as `STILL_ASKS` says them of
#: every other re-run, in a paragraph of its own that names that re-run.
HINT_PROMPTS = ("\nThe --reuse-empty-repo re-run"
                + STILL_ASKS.removeprefix(" That re-run") + "\n")


def assert_the_host_key_is_named(printed: str, repo: str, re_run: str,
                                 fix: str) -> None:
    """`printed` says a push was refused, then `fix`, how to check and keep
    the host's key for the push to `repo`, then `re_run`, once, read with
    its lines joined, and no ruleset hint: ssh refused before any ruleset
    was asked, and the hint's re-run fails the same way (#1108)."""
    said = " ".join(printed.split())
    remedy = fix.replace("@REPO@", repo) + re_run
    assert said.count(remedy) == 1, printed
    assert said.index("REFUSED pushing ") < said.index(remedy), printed
    assert "If the organisation applies a ruleset" not in printed, printed


@WINDOWS_SKIP
@pytest.mark.parametrize("says,fix,flags,repos,re_run", [
    (UNKNOWN_HOST_KEY, UNKNOWN_HOST_KEY_REMEDY, (), {}, RE_RUN_WITH_THE_FLAG),
    (UNKNOWN_HOST_KEY, UNKNOWN_HOST_KEY_REMEDY, ("--reuse-empty-repo",),
     ALL_THREE, RE_RUN_AS_IT_WAS),
    (NOT_KNOWN_STRICTLY, UNKNOWN_HOST_KEY_REMEDY, (), {},
     RE_RUN_WITH_THE_FLAG),
    (CHANGED_HOST_KEY, CHANGED_HOST_KEY_REMEDY, (), {}, RE_RUN_WITH_THE_FLAG),
], ids=["an-unknown-key", "an-unknown-key-on-the-re-run",
        "an-unknown-key-checked-strictly", "a-changed-key"])
def test_a_push_ssh_refused_the_host_key_for_names_the_key_not_the_ruleset(
        tmp_path, says, fix, flags, repos, re_run):
    """#1108, RV1101's S1. Where git config sends a scaffold's push over ssh
    and ssh refuses the host's key, ssh says `Host key verification failed.`
    and git its generic line, so on main through 823624d the push printed
    the ruleset hint alone, whose re-run fails the same way: measured with
    `BatchMode=yes`, which #1101 advises, a first run's and a re-run's exit
    2 in under 2 s. Now the run exits 2 and names the host key, how to see
    its fingerprint, check it against GitHub's and keep it, then the re-run,
    and no ruleset hint: ssh refused before any ruleset was asked. A key
    that changed, which a machine in the middle of the connection shows
    too, is never told to be accepted as it comes."""
    env, log = fake_gh(tmp_path, repos, plan="team")
    env.update(git_reaches_github_over_ssh(tmp_path, says=says))
    result = run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                        "--elected-by", "Test Human", *flags,
                        "--work-dir", str(tmp_path / "work"),
                        cwd=tmp_path, env=env)
    assert result.returncode == 2, result.stderr + result.stdout
    assert "REFUSED pushing the spec leg. THE EXACT COMMAND WAS:" in (
        result.stderr), result.stderr
    assert says in result.stderr, result.stderr
    assert_the_host_key_is_named(result.stderr, SPEC_REPO, re_run, fix)
    assert log.read_text(encoding="utf-8").count("repo create") == (
        0 if flags else 3), "a first run creates all three, a re-run none"


def github_remotes_that_refuse(tmp_path, template_dir) -> dict:
    """GitHub's side of a first run whose pushes a ruleset refuses: the three
    repositories it creates, made beforehand as bare repositories with the
    ruleset's hook (`template`), since the fake `gh` only answers `repo
    create`, and what makes git read `https://github.com/<ORG>/` from
    them."""
    remotes = tmp_path / "remotes"
    for repo in REPOS.values():
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main",
                        str(remotes / repo)], check=True,
                       env={**os.environ,
                            "GIT_TEMPLATE_DIR": str(template_dir)})
    return git_reads_github_from(f"{remotes}/")


@WINDOWS_SKIP
@pytest.mark.parametrize("role,what", [("spec", "the spec leg"),
                                       ("assembly", "the assembly root")],
                         ids=["a-leg", "the-root"])
def test_a_ruleset_s_refusal_on_github_says_what_its_re_run_can_wait_at(
        tmp_path, template, role, what):  # noqa: F811
    """#1108, RV1101's S1. `RULESET_HINT`'s one exit is the
    `--reuse-empty-repo` re-run, which turns off git's own prompt alone, and
    on main through 823624d the hint did not say so where every other
    remedy into that re-run did (#915, U037). Now a first run on GitHub
    whose push a ruleset refuses, a leg's or the root's, ends with the hint,
    byte for byte, and then the prompts that re-run can still wait at
    (`HINT_PROMPTS`); under `--local-remote-dir` the hint is the last thing
    printed (`test_ruleset_hint_tracking_branch.py`)."""
    env, log = fake_gh(tmp_path, {}, plan="team")
    env.update(github_remotes_that_refuse(tmp_path, template))
    env.update(refusing(template, REPOS[role]))
    result = run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                        "--elected-by", "Test Human",
                        "--work-dir", str(tmp_path / "work"),
                        cwd=tmp_path, env=env)
    assert result.returncode == 2, result.stderr + result.stdout
    assert f"REFUSED pushing {what}. THE EXACT COMMAND WAS:" in (
        result.stderr), result.stderr
    repo = {"spec": SPEC_REPO, "assembly": f"{ORG}/{PROJECT}"}[role]
    assert result.stderr.endswith(
        "\n" + text_for("RULESET_HINT", repo, "main") + "\n" + HINT_PROMPTS
        + "\n"), result.stderr
    assert tip(tmp_path, role) == "", "the ruleset refused it"
    if role == "assembly":
        assert all(tip(tmp_path, leg) for leg in LEGS), "both legs went in"
    assert log.read_text(encoding="utf-8").count("repo create") == 3


@pytest.fixture(scope="module")
def scaffold_module():
    return load_without_bytecode(SCAFFOLD, "scaffold_for_unread_because")


@pytest.mark.parametrize("role,empty,reuse_flag,seeded,unread,re_run", [
    ("spec", False, True, False,
     "`git ls-remote x` exited 128: Host key verification failed.", True),
    ("spec", True, False, False, None, True),
    ("code", False, False, True, None, True),
    ("spec", False, True, False, None, False),
    ("assembly", True, False, False, None, True),
    ("assembly", False, True, False, None, False),
], ids=["a-leg-git-cannot-read", "an-empty-leg", "a-leg-holding-the-seed",
        "a-leg-with-other-commits", "an-empty-root", "a-root-with-commits"])
def test_each_re_run_remedy_says_the_prompts_it_can_still_wait_at(
        scaffold_module, role, empty, reuse_flag, seeded, unread, re_run):
    """#915, U037 (Brett Heap, 2026-10-21, "U039 and U037: take your
    recommendations"). The prompt rule turns off git's own prompt alone:
    measured at 2a119f2, a re-run's probe and push waited until killed at
    ssh's host-key prompt, at a passphrase prompt, at a prompting credential
    helper, and at `GIT_ASKPASS`, `SSH_ASKPASS` and `core.askPass`. Those
    are the operator's and stay as they are, so each remedy whose exit is
    the `--reuse-empty-repo` re-run ends saying so, and how to keep it from
    waiting (`STILL_ASKS`); one whose exit is no re-run, deleting a leg or
    adopting a root, does not. Under `--local-remote-dir` git reads paths on
    disk, where none of them is asked, so no remedy says it there.
    In-process, so it runs on every platform."""
    on_github = scaffold_module._exists_remedy(role, empty, reuse_flag,
                                               seeded, unread)
    on_disk = scaffold_module._exists_remedy(role, empty, reuse_flag,
                                             seeded, unread, local=True)
    assert STILL_ASKS.strip() not in on_disk, on_disk
    assert on_github == on_disk + (STILL_ASKS if re_run else ""), on_github


#: git's advice after its generic `fatal:` line, which no reason keeps.
ADVICE = ("\n\nPlease make sure you have the correct access rights\n"
          "and the repository exists.")
GENERIC = "fatal: Could not read from remote repository."
NOT_A_REPOSITORY = ("fatal: '/x/Atlas-spec.git' does not appear to be a "
                    "git repository")
NO_PROMPT = ("fatal: could not read Username for 'https://github.com': "
             "terminal prompts disabled")
#: Two `fatal:` lines of git's own, the first of them the reason (RV971).
NOT_OUR_REF = ("fatal: remote error: upload-pack: not our ref "
               "0123456789abcdef0123456789abcdef01234567")
HUNG_UP = "fatal: the remote end hung up unexpectedly"
#: A line git prints before a `fatal:` that is not the generic one (RV971).
REDIRECTED = "warning: redirecting to https://github.com/o/r.git/"


@pytest.mark.parametrize("output,reason", [
    (f"Warning: Permanently added 'github.com' to the list of known "
     f"hosts.\n{REFUSED_KEY}\n{GENERIC}{ADVICE}", REFUSED_KEY),
    (f"{NOT_A_REPOSITORY}\n{GENERIC}{ADVICE}", NOT_A_REPOSITORY),
    (f"{GENERIC}{ADVICE}", GENERIC),
    (NO_PROMPT, NO_PROMPT),
    (f"{NOT_OUR_REF}\n{HUNG_UP}", NOT_OUR_REF),
    (f"{REDIRECTED}\n{NO_PROMPT}", NO_PROMPT),
    ("error: one thing\nanother thing", "another thing"),
    ("", None),
], ids=["ssh-before-the-generic-line", "git-s-own-fatal-first",
        "the-generic-line-alone", "one-fatal", "two-fatal-lines-the-first",
        "a-line-before-a-fatal-not-the-generic-one", "no-fatal",
        "nothing-said"])
def test_the_reason_git_could_not_read_a_leg(scaffold_module, output,
                                             reason):
    """`_unread_because` (#542, #915): git's first `fatal:` line, except
    that where it is the generic one the line before it, ssh's, is the
    reason; a `fatal:` of git's own before the generic one, and the generic
    one with nothing before it, are kept; with no `fatal:`, git's last line.
    Of two `fatal:` lines the first is kept, where the last is git hanging
    up (RV971's M8), and a line before a `fatal:` that is not the generic
    one is not the reason (RV971's M11). In-process, so it runs on every
    platform."""
    failed = scaffold_module.CommandFailed(["git", "ls-remote", "u"], None,
                                           128, output)
    assert scaffold_module._unread_because(failed) == (
        "`git ls-remote u` exited 128" + (f": {reason}" if reason else ""))


# --- what a refused push prints (#915) --------------------------------------

#: A refused push that is not a login git could not get: a ruleset's, as
#: `test_ruleset_hint_tracking_branch.py`'s hook and GitHub refuse one.
RULESET_SAID = ("remote: error: GH013: Repository rule violations found for "
                "refs/heads/main: changes must be made through a pull "
                "request.\nTo https://github.com/o/r.git\n ! [remote "
                "rejected] HEAD -> main (pre-receive hook declined)\nerror: "
                "failed to push some refs to 'https://github.com/o/r.git'")
#: git's line where the URL names the user, so only a password is asked.
NO_PASSWORD = ("fatal: could not read Password for "
               "'https://someone@github.com': terminal prompts disabled")
#: git's line where its prompt is on and there is no terminal to ask in: a
#: login git could not get as much as the two above.
NO_TERMINAL = ("fatal: could not read Username for 'https://github.com': "
               "No such device or address")
#: git's line where it sent a login and the host refused it (#993).
LOGIN_REFUSED = ("fatal: Authentication failed for "
                 "'https://github.com/o/r.git/'")
#: What GitHub and git say for a login the host took and a right it lacks:
#: not a login to give or replace, so it keeps the hint alone (#993).
FORBIDDEN = ("remote: Permission to o/r.git denied to someone.\nfatal: "
             "unable to access 'https://github.com/o/r.git/': The requested "
             "URL returned error: 403")
#: ssh's line where the host offers more ways to log in than a key.
REFUSED_KEY_AND_MORE = ("git@example.invalid: Permission denied "
                        "(publickey,password).")


#: What ssh and git print where ssh refused the host's key (#1108): a key
#: ssh does not know, as under `BatchMode=yes` and as under
#: `StrictHostKeyChecking=yes`, and a key that changed.
UNKNOWN_HOST_SAID = f"{UNKNOWN_HOST_KEY}\n{GENERIC}{ADVICE}"
STRICTLY_SAID = f"{NOT_KNOWN_STRICTLY}\n{GENERIC}{ADVICE}"
CHANGED_HOST_SAID = f"{CHANGED_HOST_KEY}\n{GENERIC}{ADVICE}"
#: The remedies printed INSTEAD OF the ruleset hint (#1108).
NO_HINT_AFTER = (UNKNOWN_HOST_KEY_REMEDY, CHANGED_HOST_KEY_REMEDY)
#: A ruleset's refusal whose `remote:` lines carry ssh's words (#1108, RV1130's
#: N2): the server wrote them, as a ruleset's message or a hook's can, so
#: they are not ssh's, and the refusal keeps the ruleset hint. One carries
#: them after a carriage return, in git's real shape (measured, git 2.43,
#: under `LC_ALL=C`, from a hook writing "see the log\rHost key verification
#: failed.\n"): git prefixes each line the server sent, and each part after a
#: `\r` in it, with `remote:` and ends each with eight spaces, so a line that
#: starts with it is the server's from end to end. Another carries a form
#: feed, which git keeps inside one prefixed line (measured, git 2.43, with
#: `cat -A`: "remote: ff^LHost key verification failed.        $"), so a
#: split at every separator `str.splitlines` knows (`\v`, `\f`, `\x1c` to
#: `\x1e`, `\x85`, U+2028 and U+2029) would cut the server's line in two.
RULESET_SAYING_HOST_KEY = (
    "remote: error: GH013: Repository rule violations found for "
    "refs/heads/main: Host key verification failed.\n"
    "remote: REMOTE HOST IDENTIFICATION HAS CHANGED\n"
    "remote: see the log        \rremote: Host key verification failed."
    "        \n"
    "remote: see the log\x0cHost key verification failed.        \n"
    "To https://github.com/o/r.git\n ! [remote rejected] HEAD -> main "
    "(pre-receive hook declined)\nerror: failed to push some refs to "
    "'https://github.com/o/r.git'")
#: And the same words on `remote:` lines beside ssh's own line for a key it
#: does not know: the remedy is the unknown key's, whatever the server says
#: of a change.
UNKNOWN_HOST_AMONG_REMOTE_LINES = (
    "remote: REMOTE HOST IDENTIFICATION HAS CHANGED\n" + UNKNOWN_HOST_SAID)


@pytest.mark.parametrize("local", [False, True], ids=["on-github", "on-disk"])
@pytest.mark.parametrize("output,reused,fix,re_run", [
    (NO_PROMPT, False, NO_LOGIN_REMEDY, RE_RUN_WITH_THE_FLAG),
    (NO_PROMPT, True, NO_LOGIN_REMEDY, RE_RUN_AS_IT_WAS),
    (NO_PASSWORD, False, NO_LOGIN_REMEDY, RE_RUN_WITH_THE_FLAG),
    (NO_TERMINAL, False, NO_LOGIN_REMEDY, RE_RUN_WITH_THE_FLAG),
    (LOGIN_REFUSED, False, LOGIN_REFUSED_REMEDY, RE_RUN_WITH_THE_FLAG),
    (LOGIN_REFUSED, True, LOGIN_REFUSED_REMEDY, RE_RUN_AS_IT_WAS),
    (f"{REFUSED_KEY}\n{GENERIC}{ADVICE}", False, KEY_REFUSED_REMEDY,
     RE_RUN_WITH_THE_FLAG),
    (f"{REFUSED_KEY}\n{GENERIC}{ADVICE}", True, KEY_REFUSED_REMEDY,
     RE_RUN_AS_IT_WAS),
    (f"{REFUSED_KEY_AND_MORE}\n{GENERIC}{ADVICE}", False, KEY_REFUSED_REMEDY,
     RE_RUN_WITH_THE_FLAG),
    (UNKNOWN_HOST_SAID, False, UNKNOWN_HOST_KEY_REMEDY, RE_RUN_WITH_THE_FLAG),
    (UNKNOWN_HOST_SAID, True, UNKNOWN_HOST_KEY_REMEDY, RE_RUN_AS_IT_WAS),
    (STRICTLY_SAID, False, UNKNOWN_HOST_KEY_REMEDY, RE_RUN_WITH_THE_FLAG),
    (CHANGED_HOST_SAID, False, CHANGED_HOST_KEY_REMEDY, RE_RUN_WITH_THE_FLAG),
    (CHANGED_HOST_SAID, True, CHANGED_HOST_KEY_REMEDY, RE_RUN_AS_IT_WAS),
    (RULESET_SAID, False, None, None),
    (FORBIDDEN, False, None, None),
    (RULESET_SAYING_HOST_KEY, False, None, None),
    (UNKNOWN_HOST_AMONG_REMOTE_LINES, False, UNKNOWN_HOST_KEY_REMEDY,
     RE_RUN_WITH_THE_FLAG),
], ids=["no-username", "no-username-on-the-re-run", "no-password",
        "no-terminal", "login-refused", "login-refused-on-the-re-run",
        "ssh-refused-the-key", "ssh-refused-the-key-on-the-re-run",
        "ssh-refused-the-key-of-more-ways", "an-unknown-host-key",
        "an-unknown-host-key-on-the-re-run",
        "an-unknown-host-key-checked-strictly", "a-changed-host-key",
        "a-changed-host-key-on-the-re-run", "a-ruleset", "a-403",
        "a-ruleset-whose-remote-lines-say-the-host-key-failed",
        "an-unknown-host-key-among-remote-lines-saying-it-changed"])
def test_what_a_refused_push_prints(scaffold_module, capsys, output, reused,
                                    fix, re_run, local):
    """`_refused_push` (#915, #993, #1108): the command and git's output,
    then one of three. Where ssh refused the host's key, a key it does not
    know (`UNKNOWN_HOST_KEY`) or one that changed (`CHANGED_HOST_KEY`), that
    case's fix and the re-run, and no ruleset hint. Where git could not get
    a login (`NO_LOGIN`), the host refused the one git sent
    (`LOGIN_REFUSED`) or ssh was refused the key (`KEY_REFUSED`), that
    case's fix and the re-run, then the ruleset hint, byte for byte. Any
    other refusal, an HTTP 403 among them, the hint, and on GitHub, not
    under `--local-remote-dir` (`local`), the prompts its re-run can still
    wait at (`HINT_PROMPTS`), which a login remedy has said already where
    there is one. Only ssh's own lines are read for a host key: a ruleset's
    refusal whose `remote:` lines, the server's, carry ssh's words keeps the
    hint, and `remote:` lines beside ssh's own line for an unknown key do
    not make it a changed one (`_without_remote_lines`). A re-run's remedy
    names its own command again, not the flag it has. In-process, so it
    runs on every platform."""
    failed = scaffold_module.CommandFailed(
        ["git", "push", "-q", "-u", "origin", "HEAD:refs/heads/main"],
        Path("work"), 128, output)
    scaffold_module._refused_push(failed, "pushing the spec leg", "o/r",
                                  "main", reused, local)
    out, err = capsys.readouterr()
    remedy = ("" if fix is None else
              "\n" + fix.replace("@REPO@", "o/r") + re_run + "\n")
    hint = ("" if fix in NO_HINT_AFTER else
            "\n" + text_for("RULESET_HINT", "o/r", "main") + "\n"
            + ("" if fix or local else HINT_PROMPTS) + "\n")
    assert out == ""
    assert err == (failed.loudly("pushing the spec leg") + "\n" + remedy
                   + hint), err


def test_the_root_s_push_git_has_no_login_for_names_the_fix_too(
        tmp_path, monkeypatch, capsys):
    """#915. The root's push is refused as each leg's is (`_refused_push`):
    after both legs went through to bare repositories on disk, the root's
    push, refused in-process with git's words for a login it could not get,
    names how to give git a login for `<ORG>/<PROJECT>` and the re-run,
    before the ruleset hint. In-process, so it runs on every platform."""
    module = load_without_bytecode(SCAFFOLD, "scaffold_for_root_login")
    real = module.run

    def no_login_for_the_root(args, cwd=None, capture=True, env=None):
        if args[:2] == ["git", "push"] and Path(cwd).name == PROJECT:
            raise module.CommandFailed(args, cwd, 128, NO_PROMPT)
        return real(args, cwd=cwd, capture=capture, env=env)

    monkeypatch.setattr(module, "run", no_login_for_the_root)
    code = module.main(["--org", ORG, "--project", PROJECT,
                        "--elected-by", "Test Human",
                        "--elected-on", "2026-09-02",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work")])
    out, err = capsys.readouterr()
    assert code == 2, err + out
    assert "REFUSED pushing the assembly root." in err, err
    assert_the_login_is_named(err, f"{ORG}/{PROJECT}", RE_RUN_WITH_THE_FLAG)
    assert all(tip(tmp_path, leg) for leg in LEGS), "both legs went through"
    assert commits(tmp_path, "assembly") == 0
