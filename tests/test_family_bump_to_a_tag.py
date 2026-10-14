# SPDX-License-Identifier: Apache-2.0
"""`family.py bump --to` an id that is 40 hex and names no commit itself
(#405, #541).

An annotated tag's own id is 40 hex, and it is what `git rev-parse v2` prints
for a release tag, so `COMMIT_RE` passed it. The checkout peeled it to the
commit the tag names, which the gitlink recorded, while the row recorded the
tag's id as typed: `bump` exited 0 and committed a holder whose own
`validate-family.py` reported `member-gitlink-mismatch`, exit 1, and `bump
--dry-run` printed the tag on its `commit` line and the commit on its
`gitlink` line. #405 made both runs refuse it, naming the commit it tags.

THE RULING THIS FILE HOLDS `bump` TO (Brett Heap, 2026-10-14, on #541):
`bump --to` peels an annotated tag's own id, as `family.py add --at` does. A
tag of a commit (or of a tag of one) is peeled to the commit it names by the
real run and by its dry run alike, and both say so in one line: the dry run
prints that commit and the row it would write and moves nothing, and the real
run pins that commit in the gitlink and the row alike and writes that row. A
tree, a blob, or a tag of either is refused `member-to-not-a-commit`, exit 2,
by both runs in the same two lines, named for what it is in `add --at`'s
words, with nothing in the holder or the member's checkout moved. A `--to`
the member does not hold at all is refused `member-to-unknown`, as
`test_family_bump_to_checks.py` holds it.

ASKED AFTER THE FETCH. A release tag is pushed to the member's remote and
reaches the member's mount only through `bump`'s own `git fetch`, which is the
issue's own flow; a question asked before the fetch finds nothing there. One
test holds that order.

The holder, the offline environment and "changes nothing" are
`test_family_dry_run.py`'s, imported rather than rebuilt. Every tag is made
in the holder's own copy of the member's mount, or in a private bare copy of
the member's remote that the mount is pointed at: the fixture's remotes are
only ever read.
"""

from __future__ import annotations

from pathlib import Path

import pytest

#: The family fixture and its names, from the module that owns them.
from test_family import ORG, family, manifest, validate  # noqa: F401
from test_family_add_refusals import holder, offline, refusal  # noqa: F401
#: "Changes nothing", asked as bytes in the order a bump would write.
from test_family_dry_run import (
    BUMP_ORDER, assert_as_it_was, bump, isolated, pinned_at, printed_row,
    state,
)
from test_family_member_path import MEMBER, older, raw
#: The sentence a bump with nothing to record ends with, from its owner.
from test_family import nothing_to_do_line

PATH = f"members/{MEMBER}"


def annotated(mount: Path, env: dict, name: str, target: str) -> str:
    """An ANNOTATED tag `name` on `target`, made in `mount` and nowhere else;
    returns the tag object's own id, which is 40 hex and not a commit."""
    raw(mount, env, "tag", "-a", "-m", f"the tag {name}", name, target)
    made = raw(mount, env, "rev-parse", name).stdout.decode("ascii").strip()
    assert raw(mount, env, "cat-file", "-t", made).stdout.strip() == b"tag"
    return made


def oid(mount: Path, env: dict, rev: str) -> str:
    """The object `rev` names in `mount`, as git resolves it."""
    return raw(mount, env, "rev-parse", "--verify", rev
               ).stdout.decode("ascii").strip()


def peeled_line(to: str, target: str) -> str:
    """The line both runs of `bump --to <to>` begin with when `to` is an
    annotated tag that names the commit `target`."""
    return (f"--to {to[:12]} is an annotated tag in {ORG}/{MEMBER}; the "
            f"commit it names, {target[:12]}, is what is pinned")


def pins_the_tagged_commit(holder: Path, env: dict, to: str,
                           target: str) -> None:
    """`bump --to <to>`, an annotated tag of `target`, for real: it says
    the tag is peeled, and pins `target` in the gitlink and the row alike,
    and the holder passes its own gate."""
    real = bump(holder, env, to)

    assert real.returncode == 0, real.stdout + real.stderr
    assert real.stderr == ""
    assert real.stdout.splitlines()[0] == peeled_line(to, target)
    row = {r["project"]: r for r in manifest(holder)["members"]}[MEMBER]
    assert row["pin"]["commit"] == target
    assert pinned_at(holder, env) == target
    assert validate(holder).returncode == 0


def both_runs(holder: Path, env: dict, to: str) -> str:
    """`bump --to <to>` with `--dry-run` and then for real, over the same
    holder: both refused, exit 2, in the same words, with nothing written to
    stdout and nothing in the holder moved. Returns the shared stderr."""
    before = state(holder, env)

    dry = bump(holder, env, to, "--dry-run")
    real = bump(holder, env, to)

    # FIRST, WHATEVER THEY PRINTED: nothing moved, the checkout included.
    assert_as_it_was(holder, env, before, BUMP_ORDER)
    assert dry.returncode == real.returncode == 2, (
        dry.stdout + dry.stderr + real.stdout + real.stderr)
    assert dry.stdout == real.stdout == ""
    assert dry.stderr == real.stderr
    return real.stderr


@pytest.mark.parametrize("nested", [False, True],
                         ids=["tag-of-a-commit", "tag-of-a-tag"])
def test_bump_to_an_annotated_tag_pins_the_commit_it_tags(
        family, holder, offline, tmp_path, nested):
    """THE RULING'S PROBE (#541). `bump --to <the tag's id>` once wrote the
    tag's id into `pin.commit` over a gitlink at the commit it tags, and
    #405 refused it. Now it is peeled, through a tag of a tag as well, as
    `add --at` peels it: the dry run says so, moves nothing and prints that
    commit and its row; the real run says the same line and pins that commit
    in the gitlink and the row alike, writing the row the dry run printed,
    and the gate is green."""
    env = isolated(offline, tmp_path)
    mount = holder / PATH
    target, pinned = older(family), pinned_at(holder, env)
    assert target != pinned, "premise: a bump with a move"
    to = annotated(mount, env, "v-release", target)
    if nested:
        to = annotated(mount, env, "v-release-again", to)
    before = state(holder, env)

    dry = bump(holder, env, to, "--dry-run")

    assert_as_it_was(holder, env, before, BUMP_ORDER)
    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert dry.stderr == ""
    assert dry.stdout.splitlines()[:3] == [
        peeled_line(to, target),
        f"member       {MEMBER}  {ORG}/{MEMBER} at {PATH}",
        f"commit       {pinned[:12]} -> {target[:12]}"]
    row = printed_row(dry.stdout)
    assert f'      commit: "{target}"' in row
    offline.assert_left_nothing()

    pins_the_tagged_commit(holder, env, to, target)

    assert "\n".join(row) + "\n" in (holder / "family.yaml").read_bytes(
    ).decode("utf-8"), "the row printed is the row written"


def test_a_release_tag_only_the_fetch_brings_is_peeled_after_the_fetch(
        family, holder, offline, tmp_path):
    """THE ISSUE'S OWN FLOW, AND THE ORDER IT NEEDS. The member releases: a
    new commit and an annotated tag on it, both pushed, after the holder was
    made. Neither is in the member's mount until `bump` fetches, so the
    question is asked of what the fetch brought, after it: asked before, it
    finds no such object.

    THE REAL RUN GOES FIRST, so no dry run's fetch has handed the mount the
    tag before it: it peels the tag its own fetch brought and pins the
    commit. The dry run of the same `--to` then peels it to the same commit,
    in the same line, and finds `nothing to do`."""
    env = isolated(offline, tmp_path)
    mount = holder / PATH
    # A PRIVATE COPY of the member's remote, which the mount is pointed at:
    # the fixture's own remote is read here and never written to.
    remote = tmp_path / f"{MEMBER}-private.git"
    raw(tmp_path, env, "clone", "-q", "--bare", "--",
        str(family["remotes"] / f"{MEMBER}.git"), str(remote))
    work = tmp_path / f"{MEMBER}-release"
    raw(tmp_path, env, "clone", "-q", "--", str(remote), str(work))
    (work / "RELEASE.md").write_bytes(b"release 2\n")
    raw(work, env, "add", "--", "RELEASE.md")
    raw(work, env, "commit", "-q", "-m", "Release 2")
    target = oid(work, env, "HEAD")
    to = annotated(work, env, "v2", target)
    raw(work, env, "push", "-q", "origin", "HEAD:refs/heads/main",
        "refs/tags/v2")
    raw(mount, env, "remote", "set-url", "origin", str(remote))
    for name in (target, to):
        assert raw(mount, env, "cat-file", "-e", name,
                   check=False).returncode != 0, (
            f"premise: {name} reaches the mount only through the fetch")

    pins_the_tagged_commit(holder, env, to, target)

    assert oid(mount, env, f"{to}^{{commit}}") == target, (
        "the fetch brought the tag, and the peel was made after it")
    before = state(holder, env)
    dry = bump(holder, env, to, "--dry-run")

    assert_as_it_was(holder, env, before, BUMP_ORDER)
    assert dry.returncode == 1, dry.stdout + dry.stderr
    assert dry.stdout.splitlines()[0] == peeled_line(to, target)
    assert dry.stdout.splitlines()[-1] == nothing_to_do_line(MEMBER, target)
    offline.assert_left_nothing()


#: Each id that is in the member's objects and is not a commit's, how a test
#: makes it from a commit of the member, and what the refusal calls it.
NOT_COMMITS = {
    "tree": (lambda mount, env, target: oid(mount, env, f"{target}^{{tree}}"),
             "names a tree"),
    "blob": (lambda mount, env, target: oid(mount, env,
                                            f"{target}:project.yaml"),
             "names a blob"),
    "tag-of-a-tree": (lambda mount, env, target: annotated(
        mount, env, "v-tree", oid(mount, env, f"{target}^{{tree}}")),
        "names a tree"),
    "tag-of-a-blob": (lambda mount, env, target: annotated(
        mount, env, "v-blob", oid(mount, env, f"{target}:project.yaml")),
        "names a blob"),
}


@pytest.mark.parametrize("make, said", NOT_COMMITS.values(), ids=NOT_COMMITS)
def test_bump_to_a_tree_a_blob_or_a_tag_of_one_is_refused_by_name(
        family, holder, offline, tmp_path, make, said):
    """A tree's or a blob's id, or an annotated tag of one, is 40 hex and in
    the member's objects too. Both runs failed on it in git's own words, the
    dry run's resolve and the real run's checkout, so the two runs did not
    even print the same refusal. Now both name it for what it is, in the
    words `add --at` names one with, a tag by what it tags (#541), in the
    same two lines, and move nothing."""
    env = isolated(offline, tmp_path)
    to = make(holder / PATH, env, older(family))
    assert len(to) == 40, "premise: 40 hex, which `COMMIT_RE` passes"

    stderr = both_runs(holder, env, to)

    assert refusal(stderr) == (
        f"REFUSED member-to-not-a-commit: --to {to} {said} in "
        f"{ORG}/{MEMBER}, not a commit",
        "Remediation: pass the commit itself — `git log --format=%H` in "
        f"{PATH} lists them. A tree's or a blob's sha is part of a commit and "
        "never one, and a pin is a commit or it is nothing.")
    offline.assert_left_nothing()
