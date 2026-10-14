# SPDX-License-Identifier: Apache-2.0
"""`family.py bump --to` an id that is 40 hex and names no commit (#405).

An annotated tag's own id is 40 hex, and it is what `git rev-parse v2` prints
for a release tag, so `COMMIT_RE` passed it. The checkout peeled it to the
commit the tag names, which the gitlink recorded, while the row recorded the
tag's id as typed: `bump` exited 0 and committed a holder whose own
`validate-family.py` reported `member-gitlink-mismatch`, exit 1, and `bump
--dry-run` printed the tag on its `commit` line and the commit on its
`gitlink` line.

THE RULING THIS FILE HOLDS `bump` TO. A `--to` that names an annotated tag, a
tree or a blob in the member's objects is refused `member-to-not-a-commit`,
exit 2, by the real run and by its dry run alike, in the same two lines, with
nothing in the holder or the member's checkout moved. A tag of a commit (or
of a tag of one) is refused naming the commit it peels to, and the re-run
with that commit is the person's: it is what `bump-leg.py` does with the same
`--to` for a leg, whose own `validate-pins.py` goes red on the tag's id and
rolls the bump back. A tree, a blob, or a tag of either is named for what it
is. A `--to` the member does not hold at all is still git's to report, as
`test_family_dry_run.py` holds it.

ASKED AFTER THE FETCH. A release tag is pushed to the member's remote and
reaches the member's mount only through `bump`'s own `git fetch`, which is the
issue's own flow; a check asked before the fetch finds nothing there and lets
the tag through to the checkout. One test holds that order.

The holder, the offline environment and "changes nothing" are
`test_family_dry_run.py`'s, imported rather than rebuilt. Every tag is made
in the holder's own copy of the member's mount, or in a private bare copy of
the member's remote that the mount is pointed at: the fixture's remotes are
only ever read.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import cloned_just_pushed
#: The family fixture and its names, from the module that owns them.
from test_family import ORG, family, manifest, validate  # noqa: F401
from test_family_add_refusals import holder, offline, refusal  # noqa: F401
#: "Changes nothing", asked as bytes in the order a bump would write.
from test_family_dry_run import (
    BUMP_ORDER, assert_as_it_was, bump, isolated, pinned_at, state,
)
from test_family_member_path import MEMBER, older, raw

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


def tag_refusal(to: str, target: str) -> tuple[str, str]:
    """The two lines `bump --to <to>` is refused with when `to` is an
    annotated tag that peels to the commit `target`."""
    return (
        f"REFUSED member-to-not-a-commit: --to {to} is an annotated tag in "
        f"{ORG}/{MEMBER}, not a commit; the commit it names is {target}",
        f"Remediation: pass that commit, `--to {target}`. A pin is a commit "
        f"or it is nothing: checking the tag out would put {target[:12]} in "
        f"the gitlink at {PATH} and the tag's own id in the row, which "
        "`validate-family.py` refuses as `member-gitlink-mismatch`.")


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
def test_bump_to_an_annotated_tag_is_refused_naming_the_commit_it_tags(
        family, holder, offline, tmp_path, nested):
    """THE ISSUE'S PROBE. `bump --to <the tag's id>` exited 0 and wrote the
    tag's id into `pin.commit` over a gitlink at the commit it tags, and the
    holder's own gate was red. Now both runs refuse it, name the commit the
    tag peels to (through a tag of a tag as well) and move nothing; and the
    re-run the refusal names pins that commit in the gitlink and the row
    alike, and the gate is green."""
    env = isolated(offline, tmp_path)
    mount = holder / PATH
    target = older(family)
    assert target != pinned_at(holder, env), "premise: a bump with a move"
    to = annotated(mount, env, "v-release", target)
    if nested:
        to = annotated(mount, env, "v-release-again", to)

    stderr = both_runs(holder, env, to)

    assert refusal(stderr) == tag_refusal(to, target)
    offline.assert_left_nothing()

    again = bump(holder, env, target)

    assert again.returncode == 0, again.stdout + again.stderr
    row = {r["project"]: r for r in manifest(holder)["members"]}[MEMBER]
    assert row["pin"]["commit"] == target == pinned_at(holder, env)
    assert validate(holder).returncode == 0


def test_a_release_tag_only_the_fetch_brings_is_refused_after_the_fetch(
        family, holder, offline, tmp_path):
    """THE ISSUE'S OWN FLOW, AND THE ORDER IT NEEDS. The member releases: a
    new commit and an annotated tag on it, both pushed, after the holder was
    made. Neither is in the member's mount until `bump` fetches, so the
    question is asked of what the fetch brought, after it: asked before, it
    found no such object, let `--to` through, and the checkout and the row
    split the tag from its commit again.

    THE REAL RUN GOES FIRST, so no dry run's fetch has handed the mount the
    tag before it. Both runs then refuse in the same two lines and move
    nothing, and the re-run with the commit the refusal names pins it in the
    gitlink and the row alike."""
    env = isolated(offline, tmp_path)
    mount = holder / PATH
    # A PRIVATE COPY of the member's remote, which the mount is pointed at:
    # the fixture's own remote is read here and never written to.
    remote = tmp_path / f"{MEMBER}-private.git"
    cloned_just_pushed(family["remotes"] / f"{MEMBER}.git", remote,
                       bare=True, env=env)
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
    before = state(holder, env)

    real = bump(holder, env, to)

    assert_as_it_was(holder, env, before, BUMP_ORDER)
    assert real.returncode == 2, real.stdout + real.stderr
    assert real.stdout == ""
    assert refusal(real.stderr) == tag_refusal(to, target)
    assert oid(mount, env, f"{to}^{{commit}}") == target, (
        "the fetch brought the tag, and the refusal was made after it")

    dry = bump(holder, env, to, "--dry-run")

    assert_as_it_was(holder, env, before, BUMP_ORDER)
    assert dry.returncode == 2, dry.stdout + dry.stderr
    assert dry.stdout == ""
    assert dry.stderr == real.stderr
    offline.assert_left_nothing()

    again = bump(holder, env, target)

    assert again.returncode == 0, again.stdout + again.stderr
    row = {r["project"]: r for r in manifest(holder)["members"]}[MEMBER]
    assert row["pin"]["commit"] == target == pinned_at(holder, env)
    assert validate(holder).returncode == 0


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
        "is an annotated tag of a tree"),
    "tag-of-a-blob": (lambda mount, env, target: annotated(
        mount, env, "v-blob", oid(mount, env, f"{target}:project.yaml")),
        "is an annotated tag of a blob"),
}


@pytest.mark.parametrize("make, said", NOT_COMMITS.values(), ids=NOT_COMMITS)
def test_bump_to_a_tree_a_blob_or_a_tag_of_one_is_refused_by_name(
        family, holder, offline, tmp_path, make, said):
    """A tree's or a blob's id, or an annotated tag of one, is 40 hex and in
    the member's objects too. Both runs failed on it in git's own words, the
    dry run's resolve and the real run's checkout, so the two runs did not
    even print the same refusal. Now both name it for what it is, as `add
    --at` does, in the same two lines, and move nothing."""
    env = isolated(offline, tmp_path)
    to = make(holder / PATH, env, older(family))
    assert len(to) == 40, "premise: 40 hex, which `COMMIT_RE` passes"

    stderr = both_runs(holder, env, to)

    assert refusal(stderr) == (
        f"REFUSED member-to-not-a-commit: --to {to} {said} in "
        f"{ORG}/{MEMBER}, not a commit",
        "Remediation: pass the commit itself — `git log --format=%H` in "
        f"{PATH} lists them. A pin is a commit or it is nothing.")
    offline.assert_left_nothing()
