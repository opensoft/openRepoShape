# SPDX-License-Identifier: Apache-2.0
"""`family.py bump`'s fetch reads only the member remote's branches into
`refs/remotes/origin/`, from the remote named `origin` and from nothing else,
and when it cannot, it says why (#905).

FOUR STATES #686'S FETCH WAS WRONG IN, lane 4's lines U182 to U185 on #459,
each measured on git 2.43 at the v1.1.1 release commit `5017830`:

- A MOUNT WHOSE OWN REFSPEC WRITES ITS BRANCHES (U182), configured
  `+refs/heads/*:refs/heads/*`, or a mirror's `+refs/*:refs/*`. With
  refspecs on the command line, git still updates whatever the configured
  `remote.origin.fetch` maps each fetched ref to, so the mount's local
  `feat`, holding a commit never pushed, was forced to the remote's `feat`,
  by `bump --dry-run` too. The fetch now carries `--refmap=`, and no local
  branch moves.
- A MOUNT THAT MAPS ITS TAGS INTO `origin/` (U183),
  `+refs/tags/*:refs/remotes/origin/*`. That refspec rode along with
  `bump`'s own `+refs/heads/*:refs/remotes/origin/*`, so a branch and a tag
  of one name failed the fetch, 128, "Cannot fetch both", where `git fetch
  origin` exits 0, and `bump` told the person to fix the network. Where no
  name was shared, the tag it put there answered for a branch, and a commit
  only a tag reaches was pinned. A refspec of the mount's whose source is
  under `refs/tags/`, wherever under `origin/` it writes, and one that gives
  another namespace the branches' names (a mirror into `origin/`), are now
  left out: the fetch works, and a tag is not a branch. #946's first head
  left out a tag or mirror refspec only where it wrote the branches' own
  names, so a tag refspec in a folder is left out now (RV946's S1); the
  mirror already was, and now has rows (S2).
- A CONFIG VALUE THAT HOLDS A NEWLINE (U184). `git config --list` was read a
  line at a time, so an alias whose value held the line
  `remote.origin.fetch=+refs/heads/zz:refs/remotes/origin/zz` gave the mount
  a refspec it does not have, and the fetch of a branch `origin` lacks
  failed. It is read with `-z` now, and as bytes, so a refspec whose bytes
  are not UTF-8 reaches the fetch as they are (RV946's N1).
- A MOUNT WITH NO `origin` (U185). Git reads a remote name it does not have
  as a path, so a repository at `origin` inside the mount was fetched, wrote
  its branches under `refs/remotes/origin/`, and `bump` answered from them.
  `git remote get-url origin` is asked before the fetch now, and a mount
  with none gets #686's words with no fetch made.

EVERY ROW RUNS `bump --dry-run` AND `bump`, and asks the mount's refs before
and after each: no ref of the mount moves under either run. To make that a
statement about `bump`'s fetch alone, each state is built with the mount's
remote-tracking refs as `bump`'s own fetch leaves them (`fetched_as_bump`),
so the fetch has nothing to bring; the control row is the one that brings a
branch, and asks that nothing else moved.

The family, the holder, the offline environment and the refusals' words are
the modules' that own them, imported, and #686's own helpers are
`test_family_bump_reachability_words.py`'s. Every remote a test writes is the
private one `pushed_from_the_mount` points the mount at.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

#: The family fixture and the holder copied from it.
from test_family import family, holder  # noqa: F401
#: The offline environment, and a refusal's two lines.
from test_family_add_refusals import offline, refusal  # noqa: F401
#: Both runs over one holder, refused alike with nothing moved, and an
#: annotated tag made in the mount.
from test_family_bump_to_a_tag import annotated, both_runs
#: #686's helpers: the private remote, a ref's reach, the mount's refs, the
#: pull-request refspec, and the words for a mount with no `origin`.
from test_family_bump_reachability_words import (
    PULLS, contains, no_origin, private_origin, private_remote, refs,
    told_no_origin, without_origin,
)
#: The refusal's words, and the states #613's tests build.
from test_family_bump_to_local_only import (
    PATH, local_only, made_in_the_mount, pins,
)
from test_family_dry_run import bump, commit_in_mount, isolated
from test_family_member_path import raw

#: The refspec `bump`'s fetch always carries: every branch of `origin`.
BRANCHES = "+refs/heads/*:refs/remotes/origin/*"

#: A mount's refspec that maps its tags into `origin/`, onto the very names
#: `BRANCHES` gives the branches.
TAGS = "+refs/tags/*:refs/remotes/origin/*"

#: Each refspec of a mount's that puts the tags of `origin` under `origin/`,
#: where `bump` reads branches: onto the branches' names, in a folder of their
#: own (RV946's S1), and in a mirror of every ref of `origin` (S2), which puts
#: the tags in `origin/tags/` and the branches in `origin/heads/`.
TAGS_UNDER_ORIGIN = pytest.mark.parametrize("refspec", [
    TAGS, "+refs/tags/*:refs/remotes/origin/tags/*",
    "+refs/*:refs/remotes/origin/*"],
    ids=["tags-onto-branches", "tags-in-a-folder", "mirror-into-origin"])

#: `caf<e9>`: Latin-1 e-acute is the one byte 0xE9, which is not UTF-8. It is
#: the lone surrogate `os.fsdecode` keeps that byte as, so a byte command line
#: hands git the byte itself; spelled with `chr`, as `os.fsdecode` raises on
#: Windows, where this module must still import.
LATIN1 = "caf" + chr(0xDCE9)

#: A refspec of a byte that is not UTF-8 reaches git only on a byte command
#: line.
BYTE_COMMAND_LINE = pytest.mark.skipif(
    os.name == "nt",
    reason="a command line is UTF-16 text on Windows, so no byte that is not "
           "UTF-8 reaches git through one")

#: The line a value of `alias.zz` holds after its first line, which a
#: listing read a line at a time takes for a refspec of the mount's.
SMUGGLED = "remote.origin.fetch=+refs/heads/zz:refs/remotes/origin/zz"


def fetched_as_bump(mount: Path, env: dict, *extra: str) -> None:
    """The mount's remote-tracking refs as `bump`'s own fetch leaves them:
    every branch of `origin`, and the refspecs in `extra`, pruned, with no
    configured refspec in the map. A run after this has nothing to fetch,
    so a ref that moves in it is one the fetch should not have moved."""
    raw(mount, env, "fetch", "-q", "--prune", "--no-prune-tags", "--refmap=",
        "origin", BRANCHES, *extra)


def where_the_tag_lands(refspec: str, tag: str) -> str:
    """The name under `refs/remotes/origin/` that `refspec`, a glob, gives
    the tag `tag` of `origin`: the branch of that name is the one the tag
    clashes with in `bump`'s fetch, where `BRANCHES` gives it the same."""
    source, _, destination = refspec.lstrip("+").partition(":")
    matched = f"refs/tags/{tag}"[len(source) - 1:]
    return destination.replace("*", matched)[len("refs/remotes/origin/"):]


def refspecs_only(mount: Path, env: dict, *refspecs: str) -> None:
    """The mount's `remote.origin.fetch` set to `refspecs` and nothing
    else."""
    raw(mount, env, "config", "--unset-all", "remote.origin.fetch")
    for refspec in refspecs:
        raw(mount, env, "config", "--add", "remote.origin.fetch", refspec)


def both_pin(holder: Path, env: dict, made: str) -> None:
    """`bump --dry-run --to <made>` prints the row, exit 0, with nothing on
    stderr (no note that the fetch failed), then `bump --to <made>` pins it
    with nothing on stderr either, and no ref of the mount moves under
    either run."""
    mount = holder / PATH
    before = refs(mount, env)

    dry = bump(holder, env, made, "--dry-run")

    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert dry.stderr == ""
    assert f'      commit: "{made}"' in dry.stdout.splitlines()
    assert refs(mount, env) == before, "no ref of the mount moved (dry run)"

    real = bump(holder, env, made)

    pins(holder, env, made, real)
    assert real.stderr == ""
    assert refs(mount, env) == before, "no ref of the mount moved (real run)"


@pytest.mark.parametrize("refspec", [
    "+refs/heads/*:refs/heads/*", "+refs/*:refs/*"],
    ids=["heads-onto-heads", "mirror"])
def test_a_mount_refspec_onto_its_own_branches_moves_none_of_them(
        holder, offline, tmp_path, refspec):
    """U182. The mount's own refspec writes its local branches, and its
    `feat` holds a commit never pushed, on top of the remote's `feat`.
    `bump --to` the remote's `feat` moved the local one to it (and the
    local `main` to the remote's `main`), by a dry run too, so the unpushed
    commit was left on no branch. With `--refmap=` the fetch maps only by
    the refspecs it names, so both runs pin the commit and neither moves a
    local branch, and the mount's refspec is as the person set it."""
    env = isolated(offline, tmp_path)
    mount = holder / PATH
    made = commit_in_mount(
        holder, env,
        lambda m: (m / "FEAT.md").write_bytes(b"the remote's feat\n"))
    raw(mount, env, "push", "-q", "origin", f"{made}:refs/heads/feat")
    tree = f"{made}^{{tree}}"
    unpushed = raw(mount, env, "commit-tree", tree, "-p", made, "-m",
                   "work on feat, never pushed").stdout.decode().strip()
    raw(mount, env, "update-ref", "refs/heads/feat", unpushed)
    refspecs_only(mount, env, refspec)
    fetched_as_bump(mount, env)
    assert raw(private_remote(holder), env, "cat-file", "-e", unpushed,
               check=False).returncode != 0, (
        "premise: the remote does not hold the local feat's commit")

    both_pin(holder, env, made)

    assert raw(mount, env, "rev-parse", "refs/heads/feat"
               ).stdout.decode().strip() == unpushed, "local feat kept"
    assert raw(mount, env, "config", "--get-all", "remote.origin.fetch"
               ).stdout.decode().strip() == refspec, "the refspec is kept"
    offline.assert_left_nothing()


@TAGS_UNDER_ORIGIN
def test_tags_mapped_into_origin_fetch_a_branch_and_a_tag_of_one_name(
        holder, offline, tmp_path, refspec):
    """U183. The mount's only refspec puts the tags of `origin` under
    `origin/`, and the member's remote has a tag, at the pin, and a branch
    named where that refspec puts the tag, holding `--to`: `v-shared` onto
    the branches' names, `tags/v-shared` in a folder or a mirror. The
    person's own `git fetch origin` exits 0, and a fetch carrying that
    refspec beside `bump`'s own exits 128, "Cannot fetch both", so both runs
    said they could not fetch the member from its origin. Leaving the
    mount's refspec out, both runs fetch, print no note and pin the commit,
    and no ref of the mount moves."""
    env = isolated(offline, tmp_path)
    mount = holder / PATH
    made = commit_in_mount(
        holder, env,
        lambda m: (m / "SHARED.md").write_bytes(b"a branch, and a tag\n"))
    branch = where_the_tag_lands(refspec, "v-shared")
    raw(mount, env, "push", "-q", "origin", f"{made}:refs/heads/{branch}")
    raw(private_remote(holder), env, "tag", "v-shared",
        raw(mount, env, "rev-parse", "HEAD").stdout.decode().strip())
    refspecs_only(mount, env, refspec)
    fetched_as_bump(mount, env)
    assert raw(mount, env, "fetch", "--dry-run", "origin",
               check=False).returncode == 0, (
        "premise: the person's own fetch works")
    clash = raw(mount, env, "fetch", "--dry-run", "origin", BRANCHES, refspec,
                check=False)
    assert clash.returncode == 128, "premise: the two refspecs clash"
    assert "Cannot fetch both " in clash.stderr.decode()
    assert f" to refs/remotes/origin/{branch}" in clash.stderr.decode()

    both_pin(holder, env, made)

    offline.assert_left_nothing()


@TAGS_UNDER_ORIGIN
def test_a_tag_a_mount_maps_into_origin_does_not_answer_for_a_branch(
        holder, offline, tmp_path, refspec):
    """U183, the reachability half: why leaving the refspec out keeps the
    answer right. A commit no branch of the member's remote reaches, pushed
    with its tag alone, in a mount whose refspec puts that tag under
    `origin/` and shares no name between a tag and a branch. Carried, the
    refspec put the tag under `origin/`, where `bump` reads branches, and
    both runs pinned the commit: onto the branches' names on main, and in a
    folder (`origin/tags/v-release`) on #946's first head too (RV946's S1);
    the mirror (S2) had no test. Left out, both refuse it in #686's words for
    a commit only a tag of the remote reaches, with nothing in the holder
    moved, and no ref of the mount moves."""
    env = isolated(offline, tmp_path)
    mount = holder / PATH
    made = made_in_the_mount(holder, env, "TAGGED.md")
    annotated(mount, env, "v-release", made)
    remote = private_origin(holder, env)
    raw(mount, env, "push", "-q", "origin", "refs/tags/v-release")
    refspecs_only(mount, env, refspec)
    fetched_as_bump(mount, env)
    assert not contains(remote, env, made, "refs/heads/"), (
        "premise: no branch of the member's remote reaches it")
    assert contains(remote, env, made, "refs/tags/"), (
        "premise: a tag of the member's remote does")
    assert not contains(mount, env, made, "refs/remotes/"), (
        "premise: no remote-tracking ref of the mount does")
    before = refs(mount, env)

    stderr = both_runs(holder, env, made)

    assert refusal(stderr) == local_only(made, tagged=True)
    assert refs(mount, env) == before, "no ref of the mount moved"
    offline.assert_left_nothing()


def test_a_config_value_holding_a_refspec_line_is_not_read_as_one(
        holder, offline, tmp_path):
    """U184. An alias whose value holds, on its second line, a line that
    reads as a `remote.origin.fetch` naming a branch `zz` the remote lacks.
    `git config --list` prints that line as a line of its own, and `git
    config --get-all remote.origin.fetch` does not list it. Read a line at a
    time, it went on the fetch's command line, the fetch failed, and both
    runs said they could not fetch the member from its origin. Read with
    `-z`, both runs fetch, print no note and pin the commit. The mount's own
    pull-request refspec is still read, so `origin/pr/7`, which the remote
    has, is kept, and no ref of the mount moves."""
    env = isolated(offline, tmp_path)
    mount = holder / PATH
    made = commit_in_mount(
        holder, env,
        lambda m: (m / "ALIAS.md").write_bytes(b"an alias of two lines\n"))
    remote = private_remote(holder)
    raw(remote, env, "update-ref", "refs/pull/7/head", made)
    raw(mount, env, "config", "--add", "remote.origin.fetch", PULLS)
    raw(mount, env, "config", "alias.zz", "!echo\n" + SMUGGLED)
    fetched_as_bump(mount, env, PULLS)
    assert SMUGGLED in raw(mount, env, "config", "--list"
                           ).stdout.decode().splitlines(), (
        "premise: a listing read a line at a time shows it")
    assert "+refs/heads/zz:refs/remotes/origin/zz" not in raw(
        mount, env, "config", "--get-all", "remote.origin.fetch"
    ).stdout.decode().splitlines(), "premise: it is no refspec of the mount"
    assert raw(remote, env, "rev-parse", "-q", "--verify", "refs/heads/zz",
               check=False).returncode != 0, "premise: there is no `zz`"
    assert f"refs/remotes/origin/pr/7 {made}" in refs(mount, env), (
        "premise: the mount holds origin/pr/7")

    both_pin(holder, env, made)

    offline.assert_left_nothing()


@BYTE_COMMAND_LINE
def test_a_refspec_whose_bytes_are_not_utf8_reaches_the_fetch_as_they_are(
        holder, offline, tmp_path):
    """U184, its bytes (RV946's N1). The mount keeps, by a refspec of its
    own, a ref of `origin` whose name holds the byte 0xE9 (`caf<e9>`, in
    Latin-1) under `origin/review/`. The listing is read as bytes and
    decoded with `surrogateescape`, so the refspec reaches the fetch byte for
    byte: both runs fetch, print no note and pin, and no ref of the mount
    moves, `origin/review/cafe` kept. Decoded with `replace`, as `run`
    decoded the listing on main, the byte became U+FFFD, the fetch asked
    `origin` for a ref it does not have and failed, and both runs said they
    could not fetch the member from its origin."""
    env = isolated(offline, tmp_path)
    mount = holder / PATH
    made = commit_in_mount(
        holder, env,
        lambda m: (m / "LATIN1.md").write_bytes(b"a ref named in Latin-1\n"))
    refspec = f"+refs/review/{LATIN1}:refs/remotes/origin/review/cafe"
    raw(private_remote(holder), env, "update-ref", f"refs/review/{LATIN1}",
        made)
    raw(mount, env, "config", "--add", "remote.origin.fetch", refspec)
    fetched_as_bump(mount, env, refspec)
    assert bytes([0xE9]) in raw(mount, env, "config", "--get-all",
                                "remote.origin.fetch").stdout, (
        "premise: the mount's refspec holds the byte")
    assert f"refs/remotes/origin/review/cafe {made}" in refs(mount, env), (
        "premise: the mount holds origin/review/cafe")

    both_pin(holder, env, made)

    offline.assert_left_nothing()


@pytest.mark.parametrize("gone", ["renamed", "removed"])
def test_a_mount_with_no_origin_fetches_no_path_named_origin(
        holder, offline, tmp_path, gone):
    """U185. The mount's `origin` is renamed to `upstream`, or removed, and
    a repository is at the path `origin` inside the mount, a leg mounted
    there, say. Git reads `origin` as that path, so the fetch read it, wrote
    its branch under `refs/remotes/origin/`, by a dry run too, and both runs
    answered in #613's words, from that repository's branches. `git remote
    get-url origin` is asked first now: the mount is not fetched, nothing
    is written under `refs/remotes/origin/`, and both runs say it has no
    remote named `origin`, with nothing in the holder moved."""
    env = isolated(offline, tmp_path)
    mount = holder / PATH
    made = commit_in_mount(
        holder, env,
        lambda m: (m / "NO-ORIGIN.md").write_bytes(b"pushed, then gone\n"))
    without_origin(mount, env, gone)
    leg = mount / "origin"
    raw(mount, env, "init", "-q", "-b", "leg-main", str(leg))
    (leg / "LEG.md").write_bytes(b"a leg mounted at `origin`\n")
    raw(leg, env, "add", "LEG.md")
    raw(leg, env, "commit", "-q", "-m", "The leg's one commit")
    gitdir = Path(raw(mount, env, "rev-parse", "--absolute-git-dir")
                  .stdout.decode().strip())
    (gitdir / "info").mkdir(exist_ok=True)
    with (gitdir / "info" / "exclude").open("ab") as exclude:
        exclude.write(b"/origin/\n")
    listed = raw(mount, env, "ls-remote", "origin").stdout
    assert b"\trefs/heads/leg-main\n" in listed, (
        "premise: git reads `origin` as the path")
    before = refs(mount, env)
    assert not [ref for ref in before
                if ref.startswith("refs/remotes/origin/")], (
        "premise: nothing under `refs/remotes/origin/`")

    stderr = both_runs(holder, env, made)

    assert told_no_origin(stderr) == no_origin(made)
    assert refs(mount, env) == before, "no ref of the mount moved"
    offline.assert_left_nothing()


def test_an_ordinary_mount_fetches_the_branch_and_moves_nothing_else(
        holder, offline, tmp_path):
    """THE CONTROL. A mount as `add` leaves it, `+refs/heads/*:refs/remotes/
    origin/*`, and a commit pushed to a branch of the member's remote since
    the mount last fetched. The fetch brings that branch, and only that:
    the dry run prints the row, exit 0, with no note, and the one ref of the
    mount it adds is the branch's remote-tracking ref; the real run then
    pins the commit and moves no ref."""
    env = isolated(offline, tmp_path)
    mount = holder / PATH
    made = commit_in_mount(
        holder, env,
        lambda m: (m / "ORDINARY.md").write_bytes(b"pushed since\n"))
    tracking = f"refs/remotes/origin/pushed-{made[:12]}"
    raw(mount, env, "update-ref", "-d", tracking)
    assert raw(mount, env, "config", "--get-all", "remote.origin.fetch"
               ).stdout.decode().strip() == BRANCHES, (
        "premise: the mount's refspec is the one `add` leaves")
    before = refs(mount, env)

    dry = bump(holder, env, made, "--dry-run")

    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert dry.stderr == ""
    assert f'      commit: "{made}"' in dry.stdout.splitlines()
    fetched = refs(mount, env)
    assert sorted(fetched) == sorted([*before, f"{tracking} {made}"]), (
        "the fetch added the branch's remote-tracking ref, and moved nothing "
        "else")

    real = bump(holder, env, made)

    pins(holder, env, made, real)
    assert real.stderr == ""
    assert refs(mount, env) == fetched, "the real run moved no ref"
    offline.assert_left_nothing()
