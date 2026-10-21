# SPDX-License-Identifier: Apache-2.0
"""Where `family.py bump --to` refuses a commit as unreachable from the
member's remote, the refusal's reason is true of the mount in front of the
person (#686).

FOUR STATES #613'S CHECK WAS UNTRUE OF, from R613's review of #625:

- A FETCH REFSPEC NARROWED BY HAND (R613 p07). `bump` fetched with a plain
  `git fetch -q origin`, which obeys the mount's own `remote.origin.fetch`.
  Narrowed to `main`, as a single-branch clone leaves it, or absent, as an
  `origin` with a URL and nothing else is, it left no remote-tracking ref for
  the branch holding `--to`, so a pushed commit was refused
  `member-to-local-only` as "reachable from no branch". `bump` now fetches
  every branch by an explicit `+refs/heads/*:refs/remotes/origin/*`, as
  `bump-leg.py` fetches a leg, and pins it; the mount's refspec is left as
  the person set it.
- A BRANCH DELETED ON THE REMOTE SINCE THE LAST FETCH (#459's line 105,
  issuecomment-6203972266, on Brett Heap's word relayed by lane 5 on #473
  at 13:56:50Z: "prune the fetch the tool already makes"). Its stale
  remote-tracking ref counted, so a commit no ref of the remote keeps was
  pinned. The same fetch now prunes, with `--no-prune-tags`: a ref under
  `refs/remotes/origin/` that no refspec of the fetch maps a ref of `origin`
  to goes, and never a branch or a tag of the mount. The mount's own
  refspecs that write under `origin/` (pull requests, say) ride along, so
  what its configuration keeps there stays. A negative one is skipped: a
  narrowing refspec, positive or negative, never decides reachability.
- A COMMIT ONLY A TAG OF THE REMOTE REACHES, which the mount holds too
  (R613 p03). Still refused: the rule is branches (the triage's D2, option
  1). The reason was "A pin the rest of the world cannot fetch", which a
  fresh clone disproves. It now says a tag of the remote reaches it and no
  branch does, and that the way out is a push to a branch. A tag only the
  mount has, or a tag of the remote's of the same name at another commit,
  keeps the plain words: the remote is asked by id.
- A MOUNT WITH NO `origin`, renamed to `upstream` or removed (R613 p10).
  Its fetch failed with no network at fault, and it was told the stale-refs
  sentence and to "fix the network or the credential". The fetch note,
  `member-to-local-only` and `member-to-unknown` now say it has no remote
  named `origin`, and to give it back; a mount config git cannot read, or
  cannot parse at all, is git's failure, quoted.

The family, the holder, the offline environment and "changes nothing" are
the modules' that own them, imported. Every remote a test writes is the
private one `pushed_from_the_mount` points the mount at.
"""

from __future__ import annotations

from pathlib import Path

import pytest

#: The family fixture, and the push every test's private remote comes from.
from test_family import family, pushed_from_the_mount  # noqa: F401
#: The holder, the offline environment, and a refusal's two lines.
from test_family_add_refusals import holder, offline, refusal  # noqa: F401
#: Both runs over one holder, refused alike with nothing moved, and an
#: annotated tag made in the mount.
from test_family_bump_to_a_tag import annotated, both_runs
#: The refusal's words, and the states #613's tests build.
from test_family_bump_to_local_only import (
    PATH, REPOSITORY, local_only, made_in_the_mount, only_in_the_mount, pins,
)
from test_family_dry_run import (
    bump, commit_in_mount, isolated, objects, pinned_at, work_tree,
)
from test_family_member_path import MEMBER, raw

#: The note both runs print first when the mount has no remote named
#: `origin`: what failed, and why, in place of " from its origin".
NO_ORIGIN_NOTE = (f"  note: could not fetch {PATH}: it has no remote named "
                  "`origin`; the commit must already be in its object store "
                  "and on a branch of its remote as last fetched")

#: What a mount with no `origin` is told to do, in both refusals.
ORIGIN_BACK = (f"give {PATH} back a remote named `origin`, for {REPOSITORY}, "
               "and run the same command again: `bump` fetches the member's "
               "branches from `origin` and asks no other remote")


def private_remote(holder: Path) -> Path:
    """Where `pushed_from_the_mount` makes the private bare remote it points
    the mount's `origin` at."""
    return holder.parent / f"{holder.name}-{MEMBER}-origin.git"


def private_origin(holder: Path, env: dict) -> Path:
    """`private_remote`, made by pushing the commit the mount stands on, the
    pin, which its `main` already holds. A test then pushes to it what it
    chooses, and nothing reaches the fixture's own remotes."""
    mount = holder / PATH
    pushed_from_the_mount(mount, raw(mount, env, "rev-parse", "HEAD")
                          .stdout.decode("ascii").strip())
    return private_remote(holder)


def contains(repository: Path, env: dict, commit: str, prefix: str) -> bool:
    """Whether a ref under `prefix` in `repository` contains `commit`."""
    return raw(repository, env, "for-each-ref", "--contains", commit,
               prefix).stdout != b""


def narrowed(mount: Path, env: dict, refspec: str | None,
             branch: str) -> None:
    """The mount's `origin` fetching only `refspec` (none at all when None),
    with no remote-tracking ref left for `branch`: a single-branch clone, or
    an `origin` with a URL and nothing else. (`--unset-all` exits 5 where
    there is no refspec left to unset.)"""
    raw(mount, env, "config", "--unset-all", "remote.origin.fetch",
        check=False)
    if refspec is not None:
        raw(mount, env, "config", "remote.origin.fetch", refspec)
    raw(mount, env, "update-ref", "-d", f"refs/remotes/origin/{branch}")
    assert raw(mount, env, "for-each-ref", f"refs/remotes/origin/{branch}"
               ).stdout == b"", "premise: no remote-tracking ref for it"


@pytest.mark.parametrize("refspec", [
    "+refs/heads/main:refs/remotes/origin/main", None],
    ids=["main-only", "no-refspec"])
def test_a_branch_a_narrowed_refspec_leaves_out_still_counts(
        holder, offline, tmp_path, refspec):
    """R613 p07. A commit pushed to a branch of the member's remote, in a
    mount whose own refspec does not fetch that branch, was refused
    `member-to-local-only` as on no branch. Both runs now fetch every
    branch, so the dry run prints the row, exit 0, and the real run pins it
    and the holder passes its gate, each from the narrowed state. The
    mount's refspec is the person's and is left as they set it."""
    env = isolated(offline, tmp_path)
    mount = holder / PATH
    made = commit_in_mount(
        holder, env,
        lambda m: (m / "NARROW.md").write_bytes(b"a branch left out\n"))
    branch = f"pushed-{made[:12]}"
    assert contains(private_remote(holder), env, made, f"refs/heads/{branch}"
                    ), "premise: a branch of the member's remote holds it"
    narrowed(mount, env, refspec, branch)
    configured = raw(mount, env, "config", "--get-all",
                     "remote.origin.fetch", check=False).stdout

    dry = bump(holder, env, made, "--dry-run")

    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert dry.stderr == ""
    assert f'      commit: "{made}"' in dry.stdout.splitlines()

    narrowed(mount, env, refspec, branch)
    pins(holder, env, made, bump(holder, env, made))
    assert raw(mount, env, "config", "--get-all", "remote.origin.fetch",
               check=False).stdout == configured, "the refspec is as it was"
    offline.assert_left_nothing()


def refs(mount: Path, env: dict) -> list[str]:
    """Every ref of the mount, with the object it names."""
    return raw(mount, env, "for-each-ref", "--format=%(refname) %(objectname)"
               ).stdout.decode().splitlines()


#: A pull-request refspec, as GitHub's and GitLab's documents give it: the
#: mount's own, keeping under `origin/` refs that no branch backs.
PULLS = "+refs/pull/*/head:refs/remotes/origin/pr/*"


#: A refspec of the mount that writes outside `refs/remotes/origin/`.
NOTES = "+refs/notes/*:refs/notes/*"


def under_origin(ref: str, *kept: str) -> bool:
    """Whether a `refs()` line is under `refs/remotes/origin/` and none of
    `kept`, the remote-tracking refs a test expects to survive."""
    return ref.startswith("refs/remotes/origin/") and not any(
        ref.startswith(f"refs/remotes/origin/{name} ") for name in kept)


def test_a_branch_deleted_on_the_remote_since_the_last_fetch_no_longer_counts(
        holder, offline, tmp_path):
    """#459's line 105 (issuecomment-6203972266), on Brett Heap's word
    relayed by lane 5 (#473, 13:56:50Z): "prune the fetch the tool already
    makes". A commit pushed to a branch of the member's remote, and that
    branch deleted there after the mount last fetched: the mount's
    remote-tracking ref still contained the commit, so `bump` pinned it,
    exit 0, with no ref of the remote keeping it. The fetch both runs make
    now prunes that ref, and both refuse `member-to-local-only`, with
    nothing moved. WHAT NOTHING ON THE REMOTE BACKS GOES, AND NOTHING ELSE:
    the mount's own branch and tag on the commit stay, in a mount set to
    prune tags, and so does `origin/HEAD` (it names `main`, which the remote
    still has). The mount's own refspec keeps pull requests under `origin/`:
    `pr/7`, which the remote still has, stays, and `pr/8`, which it deleted,
    goes with the branch, pruned against that refspec alone; a ref put
    there by hand, which no refspec maps, goes too. A refspec of the mount
    that writes OUTSIDE `origin/` (`+refs/notes/*:refs/notes/*`, here) is
    not put on the command line: nothing outside `origin/` is written."""
    env = isolated(offline, tmp_path)
    mount = holder / PATH
    made = commit_in_mount(
        holder, env,
        lambda m: (m / "DELETED.md").write_bytes(b"a branch deleted since\n"))
    stale = f"refs/remotes/origin/pushed-{made[:12]}"
    remote = private_remote(holder)
    pin = pinned_at(holder, env, MEMBER)
    for number in ("7", "8"):
        raw(remote, env, "update-ref", f"refs/pull/{number}/head", pin)
    raw(mount, env, "config", "--add", "remote.origin.fetch", PULLS)
    raw(mount, env, "fetch", "-q", "origin")
    raw(mount, env, "config", "--add", "remote.origin.fetch", NOTES)
    raw(remote, env, "update-ref", "refs/notes/review", pin)
    raw(remote, env, "update-ref", "-d", "refs/pull/8/head")
    raw(remote, env, "update-ref", "-d", f"refs/heads/pushed-{made[:12]}")
    raw(mount, env, "update-ref", "refs/remotes/origin/by-hand", pin)
    assert not contains(remote, env, made, "refs/"), (
        "premise: no ref of the member's remote reaches it")
    assert contains(mount, env, made, stale), (
        "premise: the mount's stale remote-tracking ref still does")
    raw(mount, env, "branch", "mine", made)
    raw(mount, env, "tag", "mine-tag", made)
    raw(mount, env, "config", "remote.origin.pruneTags", "true")
    before = refs(mount, env)
    for name in ("pr/7", "pr/8", "by-hand"):
        assert f"refs/remotes/origin/{name} {pin}" in before, (
            f"premise: the mount holds origin/{name}")
    kept = [ref for ref in before if not under_origin(ref, "HEAD")]

    stderr = both_runs(holder, env, made)

    assert refusal(stderr) == local_only(made)
    after = refs(mount, env)
    assert [ref for ref in after if not under_origin(ref, "HEAD")
            ] == kept, "no branch, no tag and not `origin/HEAD` was touched"
    assert not [ref for ref in after if ref.startswith("refs/notes/")], (
        "a refspec of the mount that writes outside `origin/` is not named")
    assert f"refs/remotes/origin/pr/7 {pin}" in after, (
        "the pull request the mount's own refspec keeps, and the remote "
        "still has, stays")
    for gone in (stale, "refs/remotes/origin/pr/8",
                 "refs/remotes/origin/by-hand"):
        assert not [ref for ref in after if ref.startswith(gone + " ")], (
            f"{gone}, which nothing on the remote backs, is pruned")
    offline.assert_left_nothing()


def test_a_branch_the_mounts_own_negative_refspec_excludes_still_counts(
        holder, offline, tmp_path):
    """A NARROWING REFSPEC NEVER DECIDES REACHABILITY, a negative one no more
    than a positive one (R613 p07; lane 1's N1 on #795). The mount excludes,
    with `^refs/heads/<branch>`, the branch a commit was pushed to, and has
    no remote-tracking ref for it. Git applies a configured negative refspec
    only to a fetch with none on the command line, so `bump`'s own refspec
    fetches the branch and both runs find the commit on a branch of the
    member's remote: the dry run prints the row, exit 0, and the real run
    pins it. Honouring the exclusion refused it `member-to-local-only` with
    "reachable from no branch of <repository>", untrue of a branch the remote
    has. The exclusion is left as the person set it."""
    env = isolated(offline, tmp_path)
    mount = holder / PATH
    made = commit_in_mount(
        holder, env,
        lambda m: (m / "EXCLUDED.md").write_bytes(b"a branch left out\n"))
    branch = f"pushed-{made[:12]}"
    exclusion = f"^refs/heads/{branch}"
    raw(mount, env, "config", "--add", "remote.origin.fetch", exclusion)
    raw(mount, env, "update-ref", "-d", f"refs/remotes/origin/{branch}")
    configured = raw(mount, env, "config", "--get-all",
                     "remote.origin.fetch").stdout
    assert exclusion in configured.decode().splitlines(), (
        "premise: the mount excludes the branch")

    dry = bump(holder, env, made, "--dry-run")

    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert dry.stderr == ""
    assert f'      commit: "{made}"' in dry.stdout.splitlines()
    assert contains(mount, env, made, f"refs/remotes/origin/{branch}"), (
        "the excluded branch was fetched")

    raw(mount, env, "update-ref", "-d", f"refs/remotes/origin/{branch}")
    pins(holder, env, made, bump(holder, env, made))
    assert raw(mount, env, "config", "--get-all", "remote.origin.fetch"
               ).stdout == configured, "the exclusion is as it was"
    offline.assert_left_nothing()


@pytest.mark.parametrize("typed", ["commit", "annotated-tag"])
def test_a_commit_only_a_tag_of_the_remote_reaches_is_told_so(
        holder, offline, tmp_path, typed):
    """R613 p03. A commit on no branch of the member's remote, pushed with
    its tag alone, as a release is: a fresh clone of the remote holds it. It
    is still refused `member-to-local-only` by both runs, in the same two
    lines, with nothing moved, named as typed (the tag's own id is peeled),
    but the reason is the true one: a tag of the remote reaches it and no
    branch does. Its way out works: pushed to a branch, it is pinned."""
    env = isolated(offline, tmp_path)
    mount = holder / PATH
    made = made_in_the_mount(holder, env, "RELEASE.md")
    tag = annotated(mount, env, "v-release", made)
    remote = private_origin(holder, env)
    raw(mount, env, "push", "-q", "origin", "refs/tags/v-release")
    assert not contains(remote, env, made, "refs/heads/"), (
        "premise: no branch of the member's remote reaches it")
    assert contains(remote, env, made, "refs/tags/"), (
        "premise: a tag of the member's remote does")
    assert not contains(mount, env, made, "refs/remotes/"), (
        "premise: no remote-tracking ref of the mount does")
    to = made if typed == "commit" else tag

    stderr = both_runs(holder, env, to)

    assert refusal(stderr) == local_only(to, made, tagged=True)
    assert "cannot fetch" not in stderr
    offline.assert_left_nothing()

    raw(mount, env, "push", "-q", "origin", f"{made}:refs/heads/release")
    pins(holder, env, made, bump(holder, env, made))


@pytest.mark.parametrize("kind", ["lightweight", "annotated"])
def test_a_tag_of_the_same_name_at_another_commit_keeps_the_plain_words(
        family, holder, offline, tmp_path, kind):
    """THE REMOTE IS ASKED BY ID, NOT BY NAME. The mount tags a commit only
    it holds `v-same`, and the member's remote has a `v-same` of its own, at
    the pin, lightweight or annotated (listed with its `^{}` line, the pin
    too). That tag does not reach the commit, so both runs keep #613's
    words, "a pin the rest of the world cannot fetch" included, which are
    true of it; the fetch leaves the mount's own tag as it was."""
    env = isolated(offline, tmp_path)
    mount = holder / PATH
    made = made_in_the_mount(holder, env, "SAME.md")
    raw(mount, env, "tag", "v-same", made)
    remote = private_origin(holder, env)
    tag_as(remote, env, kind, "v-same", pinned_at(holder, env, MEMBER),
           "the remote's")
    only_in_the_mount(family, holder, env, made)
    assert raw(remote, env, "cat-file", "-e", made,
               check=False).returncode != 0, (
        "premise: the remote does not hold it, so its `v-same` cannot reach "
        "it")

    stderr = both_runs(holder, env, made)

    assert refusal(stderr) == local_only(made)
    assert raw(mount, env, "rev-parse", "v-same").stdout.decode().strip() \
        == made, "the mount's own tag is as it was"
    offline.assert_left_nothing()


def tag_as(mount: Path, env: dict, kind: str, name: str, target: str,
           whose: str) -> str:
    """`name` on `target` in `mount`, `lightweight`, `annotated` or
    `tag-of-a-tag`; returns what `git rev-parse name` prints, a commit for
    the first and the tag object's own id for the others. A tag of a tag is
    an annotated `name` on an annotated `<name>-inner` on `target`, and the
    inner one's ref is then deleted: only the outer tag names it. `whose` is
    in an annotated tag's words, so two made on one commit are two objects,
    never the one that two tags of the same words made in one second would
    be."""
    if kind == "tag-of-a-tag":
        inner = tag_as(mount, env, "annotated", f"{name}-inner", target,
                       f"{whose} inner")
        tag_as(mount, env, "annotated", name, inner, whose)
        raw(mount, env, "tag", "-d", f"{name}-inner")
    elif kind == "annotated":
        raw(mount, env, "tag", "-a", "-m", f"{whose} v1", name, target)
    else:
        raw(mount, env, "tag", name, target)
    return raw(mount, env, "rev-parse", name).stdout.decode().strip()


@pytest.mark.parametrize("kinds", [
    ("lightweight", "annotated"), ("annotated", "annotated"),
    ("annotated", "lightweight"), ("tag-of-a-tag", "tag-of-a-tag"),
    ("tag-of-a-tag", "lightweight"), ("tag-of-a-tag", "annotated")],
    ids=["mount-lightweight-origin-annotated", "both-annotated-made-apart",
         "mount-annotated-origin-lightweight",
         "both-tags-of-a-tag-made-apart",
         "mount-tag-of-a-tag-origin-lightweight",
         "mount-tag-of-a-tag-origin-annotated"])
def test_a_tag_at_the_commit_reaches_it_whatever_its_object_is(
        holder, offline, tmp_path, kinds):
    """#982. THE COMMITS TAGS POINT TO ARE COMPARED, NOT THE TAG OBJECTS ALONE.
    A commit on no branch of the member's remote, which a tag of the remote
    reaches, under a `v1` the mount has too and made on its own: a
    lightweight `v1` of the mount beside an annotated `v1` of the remote,
    two annotated `v1` made apart, and the reverse of the first. The two
    tags are two objects and name one commit, and the check compared the
    objects, so each got the plain words, "a pin the rest of the world
    cannot fetch" included, where a tag of the remote does reach the commit.
    Both runs now tell the true reason, as for a tag the mount and the
    remote share, with nothing moved and the mount's own `v1` as it was.

    THROUGH A TAG OF A TAG TOO: the mount's `v1` a tag of a tag, beside a
    tag of a tag made apart, a lightweight or an annotated `v1` of the
    remote. Git before 2.44 reads `%(*objectname)` one level, to the inner
    tag, so these kept the plain words while the mount's tags were read that
    way (measured, git 2.43); `git rev-parse <id>^{}` peels to the commit."""
    mount_kind, remote_kind = kinds
    env = isolated(offline, tmp_path)
    mount = holder / PATH
    made = made_in_the_mount(holder, env, "TAGGED.md")
    remote_tag = tag_as(mount, env, remote_kind, "v1", made, "the remote's")
    remote = private_origin(holder, env)
    raw(mount, env, "push", "-q", "origin", "refs/tags/v1")
    raw(mount, env, "tag", "-d", "v1")
    mount_tag = tag_as(mount, env, mount_kind, "v1", made, "the mount's")
    assert raw(remote, env, "rev-parse", "refs/tags/v1").stdout.decode(
        ).strip() == remote_tag, (
        "premise: the remote holds the tag the mount first made")
    assert mount_tag != remote_tag, "premise: the two tags are two objects"
    for repository in (mount, remote):
        assert raw(repository, env, "rev-parse", "refs/tags/v1^{}"
                   ).stdout.decode().strip() == made, (
            "premise: both name the commit")
    assert not contains(remote, env, made, "refs/heads/"), (
        "premise: no branch of the member's remote reaches it")
    assert not contains(mount, env, made, "refs/remotes/"), (
        "premise: no remote-tracking ref of the mount does")

    stderr = both_runs(holder, env, made)

    assert refusal(stderr) == local_only(made, made, tagged=True)
    assert "cannot fetch" not in stderr
    assert raw(mount, env, "rev-parse", "v1").stdout.decode().strip() \
        == mount_tag, "the mount's own tag is as it was"
    offline.assert_left_nothing()


def test_a_tag_of_a_tag_the_two_share_reaches_it(holder, offline, tmp_path):
    """#982. A TAG OF A TAG THE MOUNT AND THE REMOTE SHARE, the mount's own
    pushed with its inner tag's ref deleted: the remote lists the outer tag
    and its `^{}` line, the commit. Both runs give the tag words, with
    nothing moved."""
    env = isolated(offline, tmp_path)
    mount = holder / PATH
    made = made_in_the_mount(holder, env, "SHARED.md")
    shared = tag_as(mount, env, "tag-of-a-tag", "v1", made, "the shared")
    remote = private_origin(holder, env)
    raw(mount, env, "push", "-q", "origin", "refs/tags/v1")
    assert raw(remote, env, "rev-parse", "refs/tags/v1").stdout.decode(
        ).strip() == shared, "premise: the two share the tag"
    assert not contains(remote, env, made, "refs/heads/"), (
        "premise: no branch of the member's remote reaches it")

    stderr = both_runs(holder, env, made)

    assert refusal(stderr) == local_only(made, made, tagged=True)
    offline.assert_left_nothing()


def made_on(holder: Path, env: dict, parent: str, name: str) -> str:
    """A commit made in the holder's own mount on top of `parent`, a commit
    only the mount holds, and NEVER PUSHED, adding the file `name`, with the
    mount put back at the pin: `commit_in_mount`, which checks `parent` out
    first. Returns its sha."""
    def change(mount: Path) -> None:
        raw(mount, env, "checkout", "-q", parent)
        (mount / name).write_bytes(b"made in the mount, on top of another\n")

    return commit_in_mount(holder, env, change, push=False)


@pytest.mark.parametrize("kinds", [
    ("annotated", "annotated"), ("lightweight", "annotated"),
    ("annotated", "lightweight")],
    ids=["both-annotated-made-apart", "mount-lightweight-origin-annotated",
         "mount-annotated-origin-lightweight"])
def test_a_tag_at_a_descendant_of_the_commit_reaches_it(
        holder, offline, tmp_path, kinds):
    """#1019. A TAG AT A DESCENDANT OF THE COMMIT REACHES IT, as a tag at the
    commit does: the mount's tags are listed with `for-each-ref --contains`,
    a tag at the commit or at any commit made on top of it, where
    `--points-at` lists only a tag AT the commit. A commit on no branch of
    the member's remote and a commit made on top of it, on none either; the
    mount and the remote each tag the DESCENDANT `v1`, made apart (the
    reviewer's case J of #988). Both runs refuse the commit
    `member-to-local-only` in the tag words, with nothing moved and the
    mount's own `v1` as it was. Every row before this one tagged the commit
    itself, so `--points-at` in place of `--contains`, the mutant M9 of
    #988's review, survived all 54 of them."""
    mount_kind, remote_kind = kinds
    env = isolated(offline, tmp_path)
    mount = holder / PATH
    made = made_in_the_mount(holder, env, "BELOW.md")
    above = made_on(holder, env, made, "ABOVE.md")
    remote_tag = tag_as(mount, env, remote_kind, "v1", above, "the remote's")
    remote = private_origin(holder, env)
    raw(mount, env, "push", "-q", "origin", "refs/tags/v1")
    raw(mount, env, "tag", "-d", "v1")
    mount_tag = tag_as(mount, env, mount_kind, "v1", above, "the mount's")
    assert raw(mount, env, "rev-parse", f"{above}^").stdout.decode().strip(
        ) == made, "premise: the commit is the parent of the one the tags name"
    assert mount_tag != remote_tag, "premise: the two tags are two objects"
    for repository in (mount, remote):
        assert raw(repository, env, "rev-parse", "refs/tags/v1^{}"
                   ).stdout.decode().strip() == above, (
            "premise: both tags name the descendant")
        assert raw(repository, env, "for-each-ref", "--points-at", made,
                   "refs/tags/").stdout == b"", (
            "premise: no tag is AT the commit")
    assert contains(remote, env, made, "refs/tags/"), (
        "premise: a tag of the member's remote reaches it, from above")
    assert not contains(remote, env, made, "refs/heads/"), (
        "premise: no branch of the member's remote reaches it")
    assert not contains(mount, env, made, "refs/remotes/"), (
        "premise: no remote-tracking ref of the mount does")

    stderr = both_runs(holder, env, made)

    assert refusal(stderr) == local_only(made, made, tagged=True)
    assert "cannot fetch" not in stderr
    assert raw(mount, env, "rev-parse", "v1").stdout.decode().strip() \
        == mount_tag, "the mount's own tag is as it was"
    offline.assert_left_nothing()


def test_a_tag_at_an_ancestor_of_the_commit_alone_keeps_the_plain_words(
        holder, offline, tmp_path):
    """#1019's CONTROL, the row above turned over. The commit the runs name is
    the CHILD here, which the member's remote does not hold, and the mount
    and the remote both tag its PARENT, which only a tag reaches. A tag at an
    ancestor does not reach a commit made on top of it: `for-each-ref
    --contains` lists the tags at the commit and above it, never below it.
    So both runs keep #613's words, "a pin the rest of the world cannot
    fetch" included, which are true of the child. A check that read the tags
    the other way round (`--merged`) would tell the tag words here."""
    env = isolated(offline, tmp_path)
    mount = holder / PATH
    parent = made_in_the_mount(holder, env, "PARENT.md")
    child = made_on(holder, env, parent, "CHILD.md")
    tag_as(mount, env, "annotated", "v-below", parent, "the parent's")
    remote = private_origin(holder, env)
    raw(mount, env, "push", "-q", "origin", "refs/tags/v-below")
    assert raw(mount, env, "rev-parse", f"{child}^").stdout.decode().strip(
        ) == parent, "premise: the commit named is the child of the one tagged"
    assert contains(remote, env, parent, "refs/tags/"), (
        "premise: a tag of the member's remote reaches the parent")
    assert raw(remote, env, "cat-file", "-e", child,
               check=False).returncode != 0, (
        "premise: the member's remote does not hold the child")
    assert not contains(mount, env, child, "refs/tags/"), (
        "premise: no tag of the mount reaches the child")
    assert not contains(mount, env, child, "refs/remotes/"), (
        "premise: no remote-tracking ref of the mount does")

    stderr = both_runs(holder, env, child)

    assert refusal(stderr) == local_only(child)
    offline.assert_left_nothing()


def no_origin(to: str) -> tuple[str, str]:
    """The two lines `bump --to <to>`, a commit the mount holds, is refused
    with when the mount has no remote named `origin`."""
    return (
        f"REFUSED member-to-local-only: --to {to} is in the member's own "
        f"object store, in {PATH}, but {PATH} has no remote named `origin`, "
        f"so whether a branch of {REPOSITORY} reaches it is not known",
        f"Remediation: {ORIGIN_BACK}. If the commit is not pushed yet, push "
        f"it to a branch of {REPOSITORY} first.")


def without_origin(mount: Path, env: dict, gone: str) -> str:
    """The mount's `origin` renamed to `upstream`, or removed, as `gone`
    says; returns its URL, for the way back."""
    url = raw(mount, env, "remote", "get-url", "origin").stdout.decode()
    if gone == "renamed":
        raw(mount, env, "remote", "rename", "origin", "upstream")
    else:
        raw(mount, env, "remote", "remove", "origin")
    assert raw(mount, env, "remote", "get-url", "origin",
               check=False).returncode == 2, "premise: no remote `origin`"
    return url.strip()


def told_no_origin(stderr: str) -> tuple[str, str]:
    """The refusal after the note that the mount has no `origin`, and
    nothing about a network or a credential anywhere in it."""
    lines = stderr.splitlines()
    assert lines[0] == NO_ORIGIN_NOTE
    assert "network" not in stderr
    assert "credential" not in stderr
    return refusal("\n".join(lines[1:]))


@pytest.mark.parametrize("gone", ["renamed", "removed"])
def test_a_mount_with_no_origin_is_told_so_and_not_to_fix_the_network(
        holder, offline, tmp_path, gone):
    """R613 p10. A commit pushed to a branch of the member's remote, in a
    mount whose `origin` was renamed to `upstream` (so `upstream/<branch>`
    holds it) or removed. The fetch of `origin` fails, and both runs said
    the commit was on no branch and to fix the network or the credential.
    Now, with nothing moved, the note says the mount has no remote named
    `origin`, and the refusal that whether a branch reaches the commit is
    therefore not known, and to give the mount its `origin` back. That way
    out works: given back, the same commit is pinned."""
    env = isolated(offline, tmp_path)
    mount = holder / PATH
    made = commit_in_mount(
        holder, env,
        lambda m: (m / "UPSTREAM.md").write_bytes(b"pushed, then renamed\n"))
    url = without_origin(mount, env, gone)
    if gone == "renamed":
        assert contains(mount, env, made, "refs/remotes/upstream/"), (
            "premise: a remote-tracking branch of `upstream` holds it")

    stderr = both_runs(holder, env, made)

    assert told_no_origin(stderr) == no_origin(made)
    offline.assert_left_nothing()

    if gone == "renamed":
        raw(mount, env, "remote", "rename", "upstream", "origin")
    else:
        raw(mount, env, "remote", "add", "origin", url)
    pins(holder, env, made, bump(holder, env, made))


def test_an_id_a_mount_with_no_origin_lacks_is_not_put_down_to_access(
        holder, offline, tmp_path):
    """R613 p10, `member-to-unknown`'s half. An id the mount does not hold,
    in a mount with no `origin`: both runs said its fetch from its origin
    failed and to make the repository readable, "check `gh auth status` or
    your SSH key". Now they say it has no remote named `origin` to fetch it
    from, and to push it if it is not pushed and give the mount its
    `origin` back."""
    env = isolated(offline, tmp_path)
    without_origin(holder / PATH, env, "renamed")
    missing = "deadbeef" * 5

    stderr = both_runs(holder, env, missing)

    assert told_no_origin(stderr) == (
        f"REFUSED member-to-unknown: --to {missing} is not a commit {PATH} "
        f"holds, and {PATH} has no remote named `origin` to fetch it from, "
        f"so whether a branch of {REPOSITORY} reaches it is not known",
        f"Remediation: push it first, to a branch of {REPOSITORY}, if it is "
        f"not pushed yet; {ORIGIN_BACK}. A pin the rest of the world cannot "
        "fetch is a family the rest of the world cannot bootstrap.")
    assert "gh auth status" not in stderr
    offline.assert_left_nothing()


#: A `url` with no value under the mount's `[remote "origin"]`. Git's config
#: parser reads a key with no `=` as a key with no value, so every read of
#: the config that asks no remote works; git's remote reader dies over it
#: (measured, git 2.43): `git remote get-url origin` and the fetch exit 128,
#: "error: missing value for 'remote.origin.url'" and "fatal: bad config
#: variable 'remote.origin.url' in file '<config>' at line <n>".
VALUELESS_URL = b'[remote "origin"]\n\turl\n'

#: A section header with no closing `]`, which git's config parser cannot
#: parse: every git command that reads the mount's config exits 128, "fatal:
#: bad config line <n> in file <config>", the holder's own commands that
#: look into the mount among them (measured, git 2.43).
UNCLOSED_HEADER = b'[remote "origin"\n'


def mount_config_ending(holder: Path, env: dict, tail: bytes) -> str:
    """A commit pushed from the mount, as `commit_in_mount` makes it, then
    `tail` appended to the mount's own git config. Returns the commit."""
    mount = holder / PATH
    made = commit_in_mount(
        holder, env, lambda m: (m / "CONFIG.md").write_bytes(b"pushed\n"))
    config = Path(raw(mount, env, "rev-parse", "--absolute-git-dir")
                  .stdout.decode().strip()) / "config"
    config.write_bytes(config.read_bytes() + tail)
    return made


def gits_own_failure(stderr: str) -> None:
    """A refusal that is git's own failure, quoted, exit 128: never that the
    mount has no `origin`, nor the network or a credential to fix."""
    assert "THE EXACT COMMAND WAS:\n    git " in stderr
    assert "    exit 128\n" in stderr
    assert "`origin`" not in stderr
    assert "network" not in stderr
    assert "credential" not in stderr


def test_a_mount_config_git_cannot_read_is_gits_own_failure(
        holder, offline, tmp_path):
    """WHETHER THE MOUNT HAS AN `origin` IS GIT'S ANSWER, never a guess.
    `git remote get-url origin` exits 2 for "No such remote" alone; a mount
    whose `origin` has a `url` with no value fails its fetch and that
    question with 128, and both runs print git's failure, the exact command,
    git's own words and exit 2, rather than telling the person the mount has
    no `origin` or to fix the network. Nothing in the holder moves.

    WHY A `url` WITH NO VALUE (#816). `bump` first asks the holder whether
    `family.yaml` holds a change HEAD does not, and that check's `git
    ls-files -m` reads each gitlinked mount's repository, so a mount config
    git cannot parse at all is refused there, before the fetch (the next
    test). A `url` with no value parses: the holder's check and the mount's
    `git config --list` work, and only git's remote reader, the fetch's and
    `get-url`'s, dies over it, so the question is asked."""
    env = isolated(offline, tmp_path)
    mount = holder / PATH
    made = mount_config_ending(holder, env, VALUELESS_URL)
    raw(holder, env, "ls-files", "-m", "-z")  # premise: the holder reads it
    asked = raw(mount, env, "remote", "get-url", "origin", check=False)
    assert asked.returncode == 128, "premise: git's own failure, not 2"
    said = asked.stderr.decode().strip()
    assert "missing value for 'remote.origin.url'" in said

    stderr = both_runs(holder, env, made)

    assert "THE EXACT COMMAND WAS:\n    git remote get-url origin\n" in stderr
    assert f"--- output ---\n{said}\n--- end output ---" in stderr
    gits_own_failure(stderr)
    offline.assert_left_nothing()


def test_a_mount_config_git_cannot_parse_is_gits_own_failure_where_met(
        holder, offline, tmp_path):
    """The same answer where git cannot parse the mount's config at all, a
    section header with no closing `]`: both runs print git's own failure,
    in the same words, the exact command and exit 2, and nothing of a
    missing `origin`, the network or a credential. Which command meets it
    first is not this test's: since #816 the holder's `git ls-files -m`
    reads the mount's repository before the fetch and fails there (git
    2.43), and every git command in the mount fails alike. Nothing in the
    holder moves, as far as git can read it: `git status` in the holder and
    `rev-parse` in the mount read that config too."""
    env = isolated(offline, tmp_path)
    made = mount_config_ending(holder, env, UNCLOSED_HEADER)

    def held() -> dict:
        return {"gitlink": pinned_at(holder, env),
                "index": raw(holder, env, "ls-files", "-s", "-z").stdout,
                "family.yaml": (holder / "family.yaml").read_bytes(),
                "work tree": work_tree(holder),
                "objects": objects(holder)}

    before = held()

    dry = bump(holder, env, made, "--dry-run")
    real = bump(holder, env, made)

    assert held() == before, "nothing in the holder moved"
    assert dry.returncode == real.returncode == 2, real.stdout + real.stderr
    assert dry.stdout == real.stdout == ""
    assert dry.stderr == real.stderr
    assert "fatal: bad config line " in real.stderr
    gits_own_failure(real.stderr)
    offline.assert_left_nothing()
