# SPDX-License-Identifier: Apache-2.0
"""`family.py bump --to` refuses a commit only the member's mount holds,
reachable from no branch of the member's remote, as `bump-leg.py` refuses its
twin (#613).

THE DEFECT. `bump` asked only whether the member's objects hold `--to`
(`cat-file -t`), and a commit made inside `members/<Project>` and never
pushed is in the mount's own object store. So `bump --to` pinned it, exit 0,
`validate-family.py` passed, and the holder could then be bootstrapped
nowhere else, since nobody else can fetch that commit. `bump-leg.py` refuses
the same state as `bump-leg-commit-local-only`.

THE RULING THIS FILE HOLDS `bump` TO (the triage's D2, option 1, which Brett
Heap approved at 2026-10-15T16:49:38Z): refuse it as `bump-leg.py` does.
After `--to` is resolved, an annotated tag peeled as #541 peels one, and
before anything is checked out or written, a remote-tracking ref of the
member (`refs/remotes/origin/*`) must contain the commit. One that none
contains is `member-to-local-only`, exit 2, from the real run and its dry
run alike, in the same two lines, with the holder byte for byte as it was.
The split of codes stays: an id the member does not hold keeps
`member-to-unknown` (`test_family_bump_to_checks.py`), and a tree, a blob or
a tag of either keeps `member-to-not-a-commit`, here for objects only the
mount holds too. OFFLINE IS NOT REFUSED FOR BEING OFFLINE: when the member's
fetch fails, both runs answer from the remote-tracking refs the mount
already has, so a commit those refs contain is pinned and one they do not is
refused with a sentence saying the refs may be stale.

TWO EDGES FROM #625'S REVIEW. A commit only a second remote's branch holds is
refused too: the question is asked of `origin` alone. And a pin `add --at`
made from a tag whose commit is on no branch cannot be named by `bump --to`
again until that commit is pushed to a branch; that is accepted as ruled.

The family, the holder, the offline environment and "changes nothing" are
`test_family_dry_run.py`'s, imported rather than rebuilt. The fixture's own
remotes are only ever read: a commit a test pushes goes to a private bare
repository the mount is pointed at (`pushed_from_the_mount`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import git, run_script
#: The family fixture and its names, from the module that owns them.
from test_family import (  # noqa: F401
    FAMILY, ORG, SPARE, family, manifest, nothing_to_do_line,
    pushed_from_the_mount, validate,
)
#: The holder, the offline environment and its `add`, and a copy of the
#: spare member's remote with an annotated tag on it.
from test_family_add_refusals import (  # noqa: F401
    holder, offline, refusal, tagged_remote,
)
#: Both runs over one holder, refused alike with nothing moved; an annotated
#: tag, and an object's id as git resolves it.
from test_family_bump_to_a_tag import annotated, both_runs, oid
#: "Changes nothing", asked as bytes in the order a bump would write.
from test_family_dry_run import (
    bump, commit_in_mount, isolated, pinned_at, state,
)
from test_family_member_path import MEMBER, raw

PATH = f"members/{MEMBER}"
REPOSITORY = f"{ORG}/{MEMBER}"

#: The line both runs print first when the member's fetch fails: since #613
#: it says both halves of the rule the commit is then held to.
FETCH_FAILED = (f"  note: could not fetch {PATH} from its origin; the commit "
                "must already be in its object store and on a branch of its "
                "remote as last fetched")


def local_only(to: str, commit: str = "", *, fetched: bool = True,
               project: str = MEMBER) -> tuple[str, str]:
    """The two lines `bump --to <to>` is refused with when the commit it
    names, `commit` (`to` itself unless an annotated tag was peeled), is in
    the mount's objects and no branch of the member's remote reaches it;
    `fetched` False when the member's fetch failed. `project` is the member
    bumped, `MEMBER` unless a test bumps another."""
    commit = commit or to
    path, repository = f"members/{project}", f"{ORG}/{project}"
    named = (f"--to {to}" if commit == to else
             f"--to {to} is an annotated tag, and the commit it names, "
             f"{commit},")
    stale = ("" if fetched else
             f" The fetch of {path} FAILED, as the note above says, so this "
             "was answered from stale remote-tracking refs: fix the network "
             "or the credential and run it again before believing it.")
    return (
        f"REFUSED member-to-local-only: {named} is in the member's own object "
        f"store, in {path}, but is reachable from no branch of {repository}",
        f"Remediation: push it to a branch of {repository} and run the same "
        f"command again; the commonest such commit was made inside {path} and "
        "never pushed. A pin the rest of the world cannot fetch is a family "
        "the rest of the world cannot bootstrap." + stale)


def made_in_the_mount(holder: Path, env: dict, name: str) -> str:
    """A commit made inside the holder's own mount and NEVER PUSHED, adding
    the file `name`, with the mount put back at the pin: the issue's own
    state. Returns its sha."""
    return commit_in_mount(
        holder, env,
        lambda mount: (mount / name).write_bytes(b"made in the mount\n"),
        push=False)


def only_in_the_mount(family, holder: Path, env: dict, commit: str) -> None:
    """The premise of a refusal: `commit` is a commit in the mount's own
    objects, no remote-tracking ref of the mount contains it, and the
    member's remote does not hold it."""
    mount = holder / PATH
    assert raw(mount, env, "cat-file", "-t", commit).stdout.strip() == \
        b"commit", "premise: the mount holds it, as a commit"
    assert raw(mount, env, "for-each-ref", "--contains", commit,
               "refs/remotes/").stdout == b"", (
        "premise: no remote-tracking ref contains it")
    assert raw(family["remotes"] / f"{MEMBER}.git", env, "cat-file", "-e",
               commit, check=False).returncode != 0, (
        "premise: the member's remote does not hold it")


def offline_from_here(holder: Path, env: dict, tmp_path: Path) -> None:
    """The mount's `origin` pointed at a repository that is not there, so
    `bump`'s fetch fails, as for a machine with no network or a private
    member with no credential."""
    raw(holder / PATH, env, "remote", "set-url", "origin",
        str(tmp_path / "gone.git"))


def pins(holder: Path, env: dict, commit: str, result) -> None:
    """`result`, a real `bump --to <commit>`, pinned `commit` in the row and
    the gitlink alike, and the holder passes its own gate."""
    assert result.returncode == 0, result.stdout + result.stderr
    row = {r["project"]: r for r in manifest(holder)["members"]}[MEMBER]
    assert row["pin"]["commit"] == commit == pinned_at(holder, env)
    assert validate(holder).returncode == 0


def test_a_commit_only_the_mount_holds_is_refused_and_pinned_once_pushed(
        family, holder, offline, tmp_path):
    """THE ISSUE'S CASE. A commit made in `members/<Project>` and never
    pushed was pinned, exit 0, by a holder its own gate passed and nobody
    else could bootstrap. Now `bump --to` it and `bump --to` it `--dry-run`
    both refuse `member-to-local-only`, exit 2, in the same two lines, with
    nothing on stdout and the holder byte for byte as it was: HEAD, the
    index, the gitlink, `family.yaml` and the member's checkout.

    THE CONTROL: the same commit pushed to a branch of the member's remote
    is pinned by the same command, exit 0, and the holder passes its gate."""
    env = isolated(offline, tmp_path)
    made = made_in_the_mount(holder, env, "LOCAL.md")
    only_in_the_mount(family, holder, env, made)
    gitlink = pinned_at(holder, env)

    stderr = both_runs(holder, env, made)

    assert refusal(stderr) == local_only(made)
    assert pinned_at(holder, env) == gitlink, "the gitlink did not move"
    offline.assert_left_nothing()

    pushed_from_the_mount(holder / PATH, made)
    pins(holder, env, made, bump(holder, env, made))


def test_an_annotated_tag_of_a_commit_only_the_mount_holds_names_it(
        family, holder, offline, tmp_path):
    """An annotated tag made in the mount, of a commit made there and never
    pushed. Its id is peeled to the commit it names, as #541 peels one, and
    that commit is asked: both runs refuse `member-to-local-only`, naming the
    tag as typed and the commit it names. The refusal comes before the line
    saying what would be pinned, so stdout is empty in both."""
    env = isolated(offline, tmp_path)
    made = made_in_the_mount(holder, env, "TAGGED.md")
    only_in_the_mount(family, holder, env, made)
    to = annotated(holder / PATH, env, "v-local", made)

    stderr = both_runs(holder, env, to)

    assert refusal(stderr) == local_only(to, made)
    offline.assert_left_nothing()


@pytest.mark.parametrize("kind", ["tree", "blob"])
def test_a_tree_or_a_blob_only_the_mount_holds_keeps_its_own_words(
        holder, offline, tmp_path, kind):
    """THE SPLIT OF CODES STAYS. A tree's or a blob's id from a commit only
    the mount holds is in the mount alone too, and it is still named for what
    it is, `member-to-not-a-commit`: reachability is asked only of a
    commit."""
    env = isolated(offline, tmp_path)
    made = made_in_the_mount(holder, env, "OBJECTS.md")
    to = oid(holder / PATH, env,
             f"{made}^{{tree}}" if kind == "tree" else f"{made}:OBJECTS.md")

    stderr = both_runs(holder, env, to)

    assert refusal(stderr)[0] == (
        f"REFUSED member-to-not-a-commit: --to {to} names a {kind} in "
        f"{REPOSITORY}, not a commit")


def test_a_commit_only_another_remotes_branch_holds_is_refused(
        holder, offline, tmp_path):
    """THE RULING NAMES `origin` (#625's review, F1). A commit pushed only to
    a second remote of the mount, a fork, is on a remote-tracking branch,
    `refs/remotes/fork/forked`, and on no branch of the member's own remote,
    the one the holder's recursive clone fetches from: pinned, it breaks
    that clone with `not our ref`. Both runs refuse it
    `member-to-local-only`, in the same two lines, since the question is
    asked of `refs/remotes/origin/` alone, as `bump-leg.py` asks it."""
    env = isolated(offline, tmp_path)
    mount = holder / PATH
    made = made_in_the_mount(holder, env, "FORK.md")
    fork = tmp_path / "fork.git"
    raw(tmp_path, env, "init", "-q", "--bare", str(fork))
    raw(mount, env, "remote", "add", "fork", str(fork))
    raw(mount, env, "push", "-q", "fork", f"{made}:refs/heads/forked")
    assert raw(mount, env, "for-each-ref", "--contains", made,
               "refs/remotes/fork/").stdout != b"", (
        "premise: a remote-tracking branch of the fork contains it")
    assert raw(mount, env, "for-each-ref", "--contains", made,
               "refs/remotes/origin/").stdout == b"", (
        "premise: no branch of the member's own remote does")

    stderr = both_runs(holder, env, made)

    assert refusal(stderr) == local_only(made)
    offline.assert_left_nothing()


def test_a_pin_add_at_made_from_a_tag_alone_is_refused_until_pushed(
        family, holder, offline, tmp_path):
    """D1 OF #625'S REVIEW, ACCEPTED AS RULED. A release commit on no branch
    of the member's remote, with only its annotated tag pushed: `add --at
    <the tag's id>` pins that commit, and the mount holds it, because its
    clone brought every tag. `bump --to` the very commit pinned said
    `nothing to do` before #613; now both runs refuse it
    `member-to-local-only`, with nothing moved, since no branch of the
    remote reaches it. The refusal's own way out works: once the commit is
    pushed to a branch of the member, the same command says `nothing to
    do`, exit 1."""
    env = isolated(offline, tmp_path)
    remotes, at = tagged_remote(family, tmp_path, "main")
    bare = remotes / f"{SPARE}.git"
    release = git("rev-parse", "main", cwd=bare).stdout.strip()
    git("update-ref", "refs/heads/main", "main~1", cwd=bare)
    assert git("for-each-ref", "--contains", release, "refs/heads/",
               cwd=bare).stdout == "", "premise: only the tag reaches it"
    added = offline.add(holder, SPARE, "--at", at, remotes=remotes)
    assert added.returncode == 0, added.stdout + added.stderr
    row = {r["project"]: r for r in manifest(holder)["members"]}[SPARE]
    assert row["pin"]["commit"] == release, "premise: add --at pinned it"
    mount = holder / "members" / SPARE
    assert raw(mount, env, "cat-file", "-t", release).stdout.strip() == \
        b"commit", "premise: the mount holds it, through its clone's tags"

    def bump_the_pin(*extra: str):
        return run_script(FAMILY, "bump", "--family-root", str(holder),
                          "--member", SPARE, "--to", release, *extra,
                          env=env)

    before = state(holder, env, SPARE)
    dry, real = bump_the_pin("--dry-run"), bump_the_pin()

    assert state(holder, env, SPARE) == before, "nothing moved"
    assert dry.returncode == real.returncode == 2, real.stdout + real.stderr
    assert dry.stdout == real.stdout == ""
    assert dry.stderr == real.stderr
    assert refusal(real.stderr) == local_only(release, project=SPARE)

    raw(mount, env, "push", "-q", "origin", f"{release}:refs/heads/release")
    again = bump_the_pin()

    assert again.returncode == 1, again.stdout + again.stderr
    assert nothing_to_do_line(SPARE, release) in again.stdout
    offline.assert_left_nothing()


def test_offline_a_commit_the_remote_tracking_refs_hold_is_pinned(
        holder, offline, tmp_path):
    """OFFLINE, ANSWERED FROM THE REFS THE MOUNT HAS. A commit pushed while
    the remote could be reached is on a remote-tracking ref of the mount.
    Then the fetch fails: both runs print the note that says so and answer
    from those refs, as `bump-leg.py` does, so the dry run prints the row
    and exits 0 and the real run pins the commit."""
    env = isolated(offline, tmp_path)
    made = commit_in_mount(
        holder, env,
        lambda mount: (mount / "PUSHED.md").write_bytes(b"pushed, then "
                                                        b"offline\n"))
    assert raw(holder / PATH, env, "for-each-ref", "--contains", made,
               "refs/remotes/origin/").stdout != b"", (
        "premise: the push left a remote-tracking ref that contains it")
    offline_from_here(holder, env, tmp_path)

    dry = bump(holder, env, made, "--dry-run")

    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert dry.stderr.splitlines() == [FETCH_FAILED]
    assert f'      commit: "{made}"' in dry.stdout.splitlines()

    real = bump(holder, env, made)

    assert real.stderr.splitlines() == [FETCH_FAILED]
    pins(holder, env, made, real)
    offline.assert_left_nothing()


def test_offline_a_commit_only_the_mount_holds_is_refused_as_maybe_stale(
        family, holder, offline, tmp_path):
    """OFFLINE, AND NO REF CONTAINS IT. The fetch fails and no remote-tracking
    ref the mount has contains the commit: both runs refuse it
    `member-to-local-only`, after the fetch's note, ending with the sentence
    that says the answer came from stale refs and to fix the network or the
    credential before believing it."""
    env = isolated(offline, tmp_path)
    made = made_in_the_mount(holder, env, "STALE.md")
    only_in_the_mount(family, holder, env, made)
    offline_from_here(holder, env, tmp_path)

    stderr = both_runs(holder, env, made)

    lines = stderr.splitlines()
    assert lines[0] == FETCH_FAILED
    assert refusal("\n".join(lines[1:])) == local_only(made, fetched=False)
    offline.assert_left_nothing()
