# SPDX-License-Identifier: Apache-2.0
"""`bump-leg.py`'s fetch of a leg carries no refspec of the leg's own that can
bring a tag under `refs/remotes/origin/`, nor one that gives another namespace
the branches' names (#1037), as `family.py bump`'s fetch of a member carries
none since #946 and #1027.

THE STATE ON MAIN `1a47ed07e`. `_leg_fetch_refspecs` left out only a refspec
whose destination is outside `refs/remotes/origin/`. Every other positive
refspec of the leg's own rode along beside `+refs/heads/*:refs/remotes/
origin/*`, the tags onto the branches' names or in a folder, a mirror into
`origin/` or in a folder, and a short name among them. `on_a_remote_branch`
reads every ref under `refs/remotes/origin/`, so:

- WHERE THE REMOTE HAS A BRANCH AND A TAG OF THE NAME such a refspec writes,
  the fetch exited 128, "Cannot fetch both", where the leg's own `git fetch
  origin` exits 0, and both runs gave the failed-fetch note and answered
  from stale refs.
- WHERE NO NAME WAS SHARED, the tag it put there answered for a branch, so
  both runs pinned a commit only a tag of the remote reaches, against #613's
  rule, which `bump-leg-commit-local-only`'s own words state: a tag is not a
  branch.

The rule is now one function both tools ask, `shape_materialize`'s
`origin_fetch_refspecs`, so the leg's fetch leaves out what the member's
does. The end-to-end rows run `bump-leg.py --dry-run` and the real run,
through the leg's `origin` and through `--local-remote-dir`, with the leg's
remote-tracking refs as the fetch leaves them (`fetched_as_bump`), so a ref
of the leg that moves is one the fetch should not have moved. `WHICH_CLAUSE`
is `tests/test_family_bump_fetch_refspecs.py`'s own table, asked here of
`_leg_fetch_refspecs` in process: one table holds both tools to one rule.

Every remote a test writes is the private bare copy `private_remote` points
the leg's `origin` at.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import FILE_PROTOCOL, REPO, git, load_without_bytecode
from test_bump_leg import SPEC_PIN, branched
from test_bump_leg_dry_run_truth import VIA, assert_one_refusal, tagged
#: #898's helpers: the private remote, a commit made in the leg, a push, a
#: ref's reach, the refusal's two lines in the tag words, and the leg's refs.
from test_bump_leg_reachability_words import (
    bare_of, contains, made_in_the_leg, private_remote, pushed, refs, refusal,
    runner, tag_reaches,
)
from test_bump_leg_rollback import snapshot
#: The member's table of clauses, asked of the leg's fetch below.
from test_family_bump_fetch_refspecs import WHICH_CLAUSE

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml  # noqa: E402

#: The refspec the leg's fetch always carries: every branch of the remote.
BRANCHES = "+refs/heads/*:refs/remotes/origin/*"

#: Where every refspec below writes.
ORIGIN = "refs/remotes/origin/"

#: The tag of the remote each clash row shares a name with a branch.
SHARED = "v-shared-w1037"

#: The tag that alone reaches the commit in each reachability row.
RELEASE = "v-release-w1037"

#: The five refspecs of a leg's own that put a tag of its remote under
#: `origin/`, where `bump-leg.py` reads branches, as #1037 names them: the
#: tags onto the branches' names and in a folder of their own, each left out
#: by its source under `refs/tags/`; a mirror of every ref into `origin/`
#: (the tags land in `origin/tags/`) and into a folder there (`origin/all/`),
#: each by its pattern `refs/*`, which takes the tags too; and a short name,
#: which git completes to the tag before the branch. `{tag}` is the tag the
#: row is about.
TAGS_UNDER_ORIGIN = pytest.mark.parametrize("refspec", [
    "+refs/tags/*:refs/remotes/origin/*",
    "+refs/tags/*:refs/remotes/origin/tags/*",
    "+refs/*:refs/remotes/origin/*", "+refs/*:refs/remotes/origin/all/*",
    "+{tag}:refs/remotes/origin/{tag}"],
    ids=["tags-onto-branches", "tags-in-a-folder", "mirror-into-origin",
         "mirror-in-a-folder", "short-name"])


def where_the_tag_lands(refspec: str, tag: str) -> str:
    """The name under `refs/remotes/origin/` that `refspec` gives the tag
    `tag` of the remote: a branch of that name is the one the tag clashes
    with in the leg's fetch, where `BRANCHES` gives it the same."""
    source, _, destination = refspec.lstrip("+").partition(":")
    if "*" not in source:
        return destination[len(ORIGIN):]
    matched = f"refs/tags/{tag}"[len(source) - 1:]
    return destination.replace("*", matched)[len(ORIGIN):]


def refspecs_only(leg: Path, *refspecs: str) -> None:
    """The leg's `remote.origin.fetch` set to `refspecs` and nothing else."""
    git("config", "--unset-all", "remote.origin.fetch", cwd=leg)
    for refspec in refspecs:
        git("config", "--add", "remote.origin.fetch", refspec, cwd=leg)


def fetched_as_bump(leg: Path) -> None:
    """The leg's remote-tracking refs as `bump-leg.py`'s own fetch leaves
    them once it leaves the leg's refspec out: every branch of `origin`,
    pruned, with no configured refspec in the map. A run after this has
    nothing to fetch, so a ref that moves in it is one the fetch should not
    have moved."""
    git(*FILE_PROTOCOL, "fetch", "-q", "--prune", "--no-prune-tags",
        "--refmap=", "origin", BRANCHES, cwd=leg)


@TAGS_UNDER_ORIGIN
@pytest.mark.parametrize("via", VIA)
def test_a_branch_and_a_tag_of_one_name_fail_no_fetch_of_the_leg(
        project, scaffolded, via, refspec):
    """The leg's only refspec puts the tags of its remote under `origin/`,
    and the remote has a tag, at the pin, and a branch named where that
    refspec puts the tag, holding `--to`. The leg's own `git fetch origin`
    exits 0, and a fetch carrying that refspec beside `BRANCHES` exits 128,
    "Cannot fetch both", so both runs gave the failed-fetch note and
    answered from refs the fetch had not renewed. Left out, both runs fetch,
    print no note and pin the commit, and no ref of the leg moves."""
    remotes = private_remote(project, scaffolded)
    leg = project / "spec"
    pin = git("rev-parse", "HEAD", cwd=leg).stdout.strip()
    made = made_in_the_leg(project, "SHARED")
    spec = refspec.format(tag=SHARED)
    branch = where_the_tag_lands(spec, SHARED)
    pushed(project, made, f"refs/heads/{branch}")
    git("tag", SHARED, pin, cwd=bare_of(remotes))
    refspecs_only(leg, spec)
    fetched_as_bump(leg)
    assert git(*FILE_PROTOCOL, "fetch", "--dry-run", "origin", cwd=leg,
               check=False).returncode == 0, (
        "premise: the leg's own fetch works")
    clash = git(*FILE_PROTOCOL, "fetch", "--dry-run", "origin", BRANCHES,
                spec, cwd=leg, check=False)
    assert clash.returncode == 128, "premise: the two refspecs clash"
    assert "Cannot fetch both " in clash.stderr
    assert f" to {ORIGIN}{branch}" in clash.stderr
    branched(project)
    run = runner(project, remotes, via)
    before = refs(leg)

    dry = run(made, "--dry-run")

    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert dry.stderr == "", "the fetch worked: no note"
    assert f"commit       {pin[:12]} -> {made[:12]}" in dry.stdout
    assert refs(leg) == before, "no ref of the leg moved (dry run)"

    real = run(made)

    assert real.returncode == 0, real.stdout + real.stderr
    assert real.stderr == "", "the fetch worked: no note"
    assert git("rev-parse", "HEAD:spec", cwd=project).stdout.strip() == made
    assert load_yaml(project / SPEC_PIN)["commit"] == made
    assert refs(leg) == before, "no ref of the leg moved (real run)"


@TAGS_UNDER_ORIGIN
@pytest.mark.parametrize("via", VIA)
def test_a_tag_the_leg_maps_into_origin_does_not_answer_for_a_branch(
        project, scaffolded, via, refspec):
    """A commit no branch of the leg's remote reaches, pushed with its
    annotated tag alone, in a leg whose only refspec puts that tag under
    `origin/` and shares no name between a tag and a branch. Carried, the
    refspec put the tag where `on_a_remote_branch` reads branches, and both
    runs pinned the commit. Left out, both refuse it
    `bump-leg-commit-local-only` in the words for a commit only a tag of the
    remote reaches, with nothing in the root moved, and no ref of the leg
    moves."""
    remotes = private_remote(project, scaffolded)
    bare = bare_of(remotes)
    leg = project / "spec"
    made = made_in_the_leg(project, "TAGGED")
    tagged(leg, RELEASE, made)
    pushed(project, f"refs/tags/{RELEASE}", f"refs/tags/{RELEASE}")
    refspecs_only(leg, refspec.format(tag=RELEASE))
    fetched_as_bump(leg)
    assert not contains(bare, made, "refs/heads/"), (
        "premise: no branch of the leg's remote reaches it")
    assert contains(bare, made, "refs/tags/"), (
        "premise: a tag of the leg's remote does")
    assert not contains(leg, made, "refs/remotes/"), (
        "premise: no remote-tracking ref of the leg does")
    branched(project)
    run = runner(project, remotes, via)
    before = snapshot(project)
    leg_refs = refs(leg)

    stderr = assert_one_refusal(project, run, made,
                                "bump-leg-commit-local-only", before)

    assert refusal(stderr) == tag_reaches(made)
    assert refs(leg) == leg_refs, "no ref of the leg moved"


@pytest.fixture(scope="module")
def bump_leg_py():
    """`scripts/bump-leg.py`, loaded once for `WHICH_CLAUSE`'s rows."""
    return load_without_bytecode(REPO / "scripts" / "bump-leg.py",
                                 "bump_leg_fetch_refspecs")


@WHICH_CLAUSE
def test_which_clause_leaves_each_refspec_out_of_the_legs_fetch(
        bump_leg_py, tmp_path, refspec, carried):
    """#1037. A repository whose `origin` has `refspec` as its one fetch
    refspec, asked of `_leg_fetch_refspecs` in process: the leg's fetch
    carries every branch and, where no clause of `origin_fetch_refspecs`
    leaves it out, `refspec`, forced. The rows and their ids are the
    member's (`test_family_bump_fetch_refspecs.py` says which clause each
    holds), so a clause either tool gains is asked of both; on main every
    row the member leaves out by a tag or the branches' glob was carried
    here."""
    leg = tmp_path / "leg"
    git("init", "-q", str(leg), cwd=tmp_path)
    git("remote", "add", "origin", str(tmp_path / "origin.git"), cwd=leg)
    refspecs_only(leg, refspec)
    expected = ([BRANCHES, "+" + refspec.lstrip("+")] if carried
                else [BRANCHES])

    assert bump_leg_py._leg_fetch_refspecs(leg) == expected
