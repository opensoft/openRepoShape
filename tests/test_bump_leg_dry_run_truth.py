# SPDX-License-Identifier: Apache-2.0
"""`scripts/bump-leg.py --dry-run` gives the real run's answer (#534, #438).

STEP 1 OF "Advancing a leg" IS A DRY RUN, and the line it prints is what the
human reads and agrees to. Two answers differed:

  * `--to <an annotated tag's own id>`: the id is 40 hex, so it passed
    `COMMIT_RE`, and reachability and `object_present` both PEEL a tag, so
    nothing refused it. The dry run printed the tag's id as the new commit and
    exited 0. The real run checked the leg out at the commit the tag names,
    wrote the TAG's id into the pin and the workflow references, was refused by
    the project's own `validate-pins.py` and rolled back, exit 2.

  * a pin the validators read and the rewrite refuses (#438): `rewrite_pin`
    ran before the dry-run return only inside the nothing-to-do test, so
    `digests: {tree_sha256: ...}` (a flow mapping) previewed `old -> new`,
    exit 0, and the real run was refused `bump-leg-pin-unrecognised` after the
    leg had been checked out. It is now computed once, before the return.

THE RULING THIS FILE HOLDS BOTH RUNS TO FOR A TAG: the tag's id is PEELED, as
`family.py add --at` peels one. The run goes on with the commit the tag names,
the same in the dry run and the real run, and prints one line saying so ahead
of the `commit` line. A tree's or a blob's id, or a tag of either, is refused
`bump-leg-target-not-a-commit` by name, in both runs, with nothing written.

WHAT THE FETCH BRINGS, measured here and not assumed. `fetch_leg` fetches
`+refs/heads/*:refs/remotes/origin/*`, and git follows an annotated tag that
points into the history it brings: a release tag pushed to the leg's remote
reaches the leg's object store through that fetch, from the
`--local-remote-dir` bare repository and from the leg's own `origin` alike
(both are run below). A tag whose commit is on no branch is NOT brought, and
neither is its commit: it is `bump-leg-commit-not-on-remote` in both runs, and
one test holds that. The peel is therefore asked AFTER the fetch.

Every case here runs the dry run AND the real run over the same root and
asserts that they give one answer. The leg's remote is a PRIVATE bare copy of
the session's, so a tag pushed here never reaches another module's leg.

NO NETWORK, NO `gh`, NO BASH: the bare remotes are on disk, so this runs on
every OS the suite runs on.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import FILE_PROTOCOL, ORG, PROJECT, REPO, git, run_script
from test_bump_leg import (
    BUMP, SPEC_PIN, branched, bump, commit_spec_pin, committed,
    reference_both_legs, spec_ref, validate,
)
from test_bump_leg_rollback import assert_nothing_changed, snapshot

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml, tree_digest  # noqa: E402

#: The two ways a leg is reached. `--local-remote-dir` is the TEST path of the
#: tool; the leg's own `origin` is what every person's run uses.
VIA = ["local-remote-dir", "origin"]

#: Printed by the dry run after the report and by no other run.
DRY_RUN_FOOTER = "\n--dry-run: nothing was changed."

#: Printed by the real run once the rewrite is written, and by no dry run.
VALIDATORS_HEADER = "\nthe project's own validators"

ADVANCE_BRANCH = "bump-leg-dry-run-truth-advance"


def peel_line(tag: str, commit: str) -> str:
    """The one line a peel adds, as the tool prints it. `would be pinned`,
    because a refusal can still follow it (the commit may be on no branch of
    the remote), and a run that says `is pinned` and then refuses is not true
    on screen."""
    return (f"--to {tag[:12]} is an annotated tag; it names commit "
            f"{commit[:12]}, which is what would be pinned")


# --- the private remote, and what is pushed to it ---------------------------

@pytest.fixture(scope="module")
def leg_remote(scaffolded, tmp_path_factory) -> dict:
    """A PRIVATE bare copy of the spec leg's remote, in the shape
    `--local-remote-dir` takes: a directory holding `<leg>.git`. The session's
    own bare repositories are only ever read, so a tag pushed to this one
    reaches no other module's leg.

    `--no-local`, as `clone_just_pushed` reads a remote a scaffold has just
    written (#440): through upload-pack, which a repack does not break.
    """
    remotes = tmp_path_factory.mktemp("w534-remotes")
    proc = subprocess.run(
        ["git", *FILE_PROTOCOL, "clone", "-q", "--bare", "--no-local",
         str(scaffolded["remotes"] / f"{PROJECT}-spec.git"),
         str(remotes / f"{PROJECT}-spec.git")],
        capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return {"remotes": remotes, "bare": remotes / f"{PROJECT}-spec.git"}


def private_work(leg_remote: dict, tmp_path_factory, name: str) -> Path:
    """A clone of the private remote to make commits in and push from."""
    work = tmp_path_factory.mktemp(f"w534-{name}") / f"{PROJECT}-spec"
    proc = subprocess.run(
        ["git", *FILE_PROTOCOL, "clone", "-q", "--no-local",
         str(leg_remote["bare"]), str(work)],
        capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return work


def tagged(work: Path, name: str, target: str) -> str:
    """An ANNOTATED tag `name` on `target`; returns the tag object's own id,
    which is 40 hex and not a commit."""
    git("tag", "-a", "-m", f"the tag {name}", name, target, cwd=work)
    made = git("rev-parse", name, cwd=work).stdout.strip()
    assert git("cat-file", "-t", made, cwd=work).stdout.strip() == "tag"
    return made


@pytest.fixture(scope="module")
def release(leg_remote, tmp_path_factory) -> dict:
    """THE ISSUE'S FLOW: the leg's new commit is pushed to a branch of its
    remote and ANNOTATED-tagged there, `git tag -a v2`, as a release is.

    `tag` is the tag object's own id (what `git rev-parse v2` prints), and
    `tag_of_tag` the id of a tag that tags that tag. `commit` is the commit
    they both name.
    """
    work = private_work(leg_remote, tmp_path_factory, "release")
    (work / "RELEASE-CONTRACT.md").write_text("# the release's contract\n")
    git("add", "--", "RELEASE-CONTRACT.md", cwd=work)
    git("commit", "-qm", "The release commit", cwd=work)
    commit = git("rev-parse", "HEAD", cwd=work).stdout.strip()
    tag = tagged(work, "v2-w534", commit)
    again = tagged(work, "v2-again-w534", tag)
    git("push", "-q", "origin", f"HEAD:refs/heads/{ADVANCE_BRANCH}",
        "v2-w534", "v2-again-w534", cwd=work)
    assert git("rev-parse", f"{tag}^{{}}", cwd=work).stdout.strip() == commit
    assert git("rev-parse", f"{again}^{{}}", cwd=work).stdout.strip() == commit
    return {"commit": commit, "tag": tag, "tag_of_tag": again}


@pytest.fixture(scope="module")
def tag_only(leg_remote, tmp_path_factory) -> dict:
    """A commit that is on NO branch of the leg's remote, held only by an
    annotated tag pushed there: the one tag the fetch does not bring."""
    work = private_work(leg_remote, tmp_path_factory, "tag-only")
    git("checkout", "-q", "--detach", cwd=work)
    (work / "TAG-ONLY.md").write_text("# held by a tag alone\n")
    git("add", "--", "TAG-ONLY.md", cwd=work)
    git("commit", "-qm", "A commit no branch holds", cwd=work)
    commit = git("rev-parse", "HEAD", cwd=work).stdout.strip()
    tag = tagged(work, "only-w534", commit)
    git("push", "-q", "origin", "refs/tags/only-w534", cwd=work)
    return {"commit": commit, "tag": tag}


# --- running the two runs ---------------------------------------------------

def point_origin_at(project: Path, remote: Path) -> None:
    """The leg's own `origin` is the private bare repository, so a run
    WITHOUT `--local-remote-dir` fetches from where the tag was pushed."""
    git("remote", "set-url", "origin", str(remote), cwd=project / "spec")


def runner(project: Path, leg_remote: dict, via: str):
    """`bump(to, *extra)` for this root, reaching the leg by `via`."""
    if via == "origin":
        point_origin_at(project, leg_remote["bare"])
        return lambda to, *extra: run_script(
            BUMP, "--root", str(project), "--leg", "spec", "--to", to, *extra)
    return lambda to, *extra: bump(project, leg_remote, to, *extra)


def holds(project: Path, oid: str) -> bool:
    """Does the leg's own object store hold `oid`?"""
    return git("cat-file", "-e", oid, cwd=project / "spec",
               check=False).returncode == 0


def report_of(result, *, real: bool) -> str:
    """What a run printed up to the point the two runs part: the report a human
    reads, the `old -> new` line included."""
    cut = VALIDATORS_HEADER if real else DRY_RUN_FOOTER
    assert cut in result.stdout, result.stdout + result.stderr
    return result.stdout.split(cut)[0]


def assert_one_refusal(project: Path, run, to: str, code: str,
                       before: dict) -> str:
    """Both runs refused, exit 2, in the same words, with nothing written:
    the pin, the workflows, the index and the leg's checkout as they were.
    Returns the shared stderr."""
    dry = run(to, "--dry-run")
    assert_nothing_changed(project, before)
    real = run(to)
    assert_nothing_changed(project, before)

    assert dry.returncode == real.returncode == 2, (
        dry.stdout + dry.stderr + real.stdout + real.stderr)
    assert f"REFUSED {code}" in dry.stderr
    assert dry.stderr == real.stderr, "one refusal, in the same words"
    assert dry.stdout == real.stdout, "and the same report before it"
    return real.stderr


# --- #534: an annotated tag's own id is peeled, in both runs ----------------

@pytest.mark.parametrize("via", VIA)
@pytest.mark.parametrize("which", ["tag", "tag_of_tag"],
                         ids=["tag", "tag-of-a-tag"])
def test_a_release_tags_own_id_is_peeled_to_its_commit_in_both_runs(
        project, leg_remote, release, via, which):
    """THE ISSUE'S RELEASE FLOW, end to end. The dry run exits 0, says it
    peeled the tag, and prints the COMMIT on its `commit` line; the real run
    makes a commit whose gitlink, `commit:` in the pin and workflow reference
    all name the COMMIT, and the project's own `validate-pins.py` is green. Run
    through `--local-remote-dir` and through the leg's own `origin`, and
    through a tag of a tag, which `^{}` peels as well.

    BEFORE THE FIX the dry run exited 0 with the TAG's id on its `commit` line
    while the real run exited 2: the checkout peeled it, the pin did not, and
    the project's own gate refused.
    """
    tag, commit = release[which], release["commit"]
    was, _ = reference_both_legs(project)
    branched(project)
    assert not holds(project, tag), (
        "premise: the leg has never received the tag — the fetch brings it")
    run = runner(project, leg_remote, via)
    before = snapshot(project)

    dry = run(tag, "--dry-run")

    assert dry.returncode == 0, dry.stderr + dry.stdout
    assert_nothing_changed(project, before)
    assert holds(project, tag), "the fetch brought the tag, as git follows it"
    out = dry.stdout
    old_to_new = f"commit       {was[:12]} -> {commit[:12]}"
    assert out.count(peel_line(tag, commit)) == 1
    assert old_to_new in out
    assert out.index(peel_line(tag, commit)) < out.index(old_to_new), (
        "the peel is said before the line the human reads")
    assert f"-> {tag[:12]}" not in out, "the tag's id is never the new commit"
    digest = tree_digest(project / "spec", commit)
    assert f"tree         {digest[:12]}… ({digest})" in out
    assert "legs.yml  1 reference(s)" in out

    real = run(tag)

    assert real.returncode == 0, real.stderr + real.stdout
    assert report_of(real, real=True) == report_of(dry, real=False), (
        "the dry run printed the report the real run printed")
    assert git("rev-parse", "HEAD:spec", cwd=project).stdout.strip() == commit
    pin = load_yaml(project / SPEC_PIN)
    assert pin["commit"] == commit
    assert pin["digests"]["tree_sha256"] == digest
    workflow = (project / ".github" / "workflows" / "legs.yml").read_text(
        encoding="utf-8")
    assert spec_ref(commit) in workflow
    assert tag not in workflow
    assert committed(project) == {"spec", SPEC_PIN,
                                  ".github/workflows/legs.yml"}
    assert validate(project).returncode == 0, "the project's own gate is green"
    assert git("status", "--porcelain", cwd=project).stdout == ""


def test_a_tag_made_inside_the_legs_mount_is_peeled_in_both_runs(
        project, leg_remote, release):
    """A tag the person made in the leg's own checkout, on a commit that is
    pushed. The leg already holds the tag, so no fetch had to bring it, and it
    is peeled all the same: asked of the leg's objects, wherever the tag came
    from."""
    commit = release["commit"]
    leg = project / "spec"
    # The commit reaches the leg without the remote's tag, so the tag in the
    # mount is the only one there is.
    git(*FILE_PROTOCOL, "fetch", "-q", "--no-tags", str(leg_remote["bare"]),
        "+refs/heads/*:refs/remotes/origin/*", cwd=leg)
    tag = tagged(leg, "mine-w534", commit)
    reference_both_legs(project)
    branched(project)
    run = runner(project, leg_remote, "local-remote-dir")
    before = snapshot(project)

    dry = run(tag, "--dry-run")
    assert dry.returncode == 0, dry.stderr + dry.stdout
    assert_nothing_changed(project, before)
    assert peel_line(tag, commit) in dry.stdout

    real = run(tag)
    assert real.returncode == 0, real.stderr + real.stdout
    assert report_of(real, real=True) == report_of(dry, real=False)
    assert git("rev-parse", "HEAD:spec", cwd=project).stdout.strip() == commit
    assert load_yaml(project / SPEC_PIN)["commit"] == commit
    assert validate(project).returncode == 0


@pytest.mark.parametrize("via", VIA)
def test_a_tag_of_the_commit_already_pinned_is_nothing_to_do_in_both_runs(
        project, leg_remote, via):
    """`nothing to do`, exit 1, as for the commit itself: the peeled commit is
    what is compared with the pin, so a tag of the pinned commit moves
    nothing, writes no empty commit and is said to have been peeled."""
    pinned = git("rev-parse", "HEAD:spec", cwd=project).stdout.strip()
    tag = tagged(project / "spec", "pinned-w534", pinned)
    branched(project)
    run = runner(project, leg_remote, via)
    before = snapshot(project)

    dry = run(tag, "--dry-run")
    assert_nothing_changed(project, before)
    real = run(tag)
    assert_nothing_changed(project, before)

    assert dry.returncode == real.returncode == 1, (
        dry.stdout + dry.stderr + real.stdout + real.stderr)
    assert dry.stdout == real.stdout, "one answer from both runs"
    assert peel_line(tag, pinned) in real.stdout
    assert f"nothing to do: {ORG}/{PROJECT}-spec is already pinned at " \
           f"{pinned[:12]} and every fact agrees." in real.stdout


# --- a tree, a blob or a tag of either is refused by name -------------------

def leg_objects(project: Path) -> dict:
    """A tree, a blob and the two tags that tag them, all in the leg."""
    leg = project / "spec"
    tree = git("rev-parse", "HEAD^{tree}", cwd=leg).stdout.strip()
    row = next(line for line in
               git("ls-tree", "-r", "HEAD", cwd=leg).stdout.splitlines()
               if " blob " in line)
    blob = row.split()[2]
    return {"tree": tree, "blob": blob,
            "tag of a tree": tagged(leg, "tree-w534", tree),
            "tag of a blob": tagged(leg, "blob-w534", blob)}


NOT_COMMITS = {
    "tree": "names a tree",
    "blob": "names a blob",
    "tag of a tree": "is an annotated tag of a tree",
    "tag of a blob": "is an annotated tag of a blob",
}


@pytest.mark.parametrize("via", VIA)
@pytest.mark.parametrize("kind", NOT_COMMITS)
def test_a_tree_a_blob_or_a_tag_of_either_is_refused_by_name_in_both_runs(
        project, leg_remote, via, kind):
    """The id is in the leg: `git ls-tree` prints a tree's and a blob's, so
    "no branch of the remote contains it" would send the human looking for a
    push that is not missing. Refused `bump-leg-target-not-a-commit`, naming
    what it is, by the dry run and by the real run, and neither wrote a byte:
    the pin, the workflows, the index and the leg's checkout are as they
    were."""
    oid = leg_objects(project)[kind]
    branched(project)
    run = runner(project, leg_remote, via)
    before = snapshot(project)

    stderr = assert_one_refusal(project, run, oid,
                                "bump-leg-target-not-a-commit", before)

    assert f"--to {oid} {NOT_COMMITS[kind]} in the leg " \
           f"({ORG}/{PROJECT}-spec), not a commit" in stderr
    assert "bump-leg-commit-not-on-remote" not in stderr
    assert "no branch" not in stderr


# --- what the fetch does not bring ------------------------------------------

@pytest.mark.parametrize("via", VIA)
def test_a_tag_the_fetch_never_brings_is_not_on_the_remote_in_both_runs(
        project, leg_remote, tag_only, via):
    """THE MEASUREMENT'S OTHER HALF. The fetch is `+refs/heads/*`, and git
    follows only a tag that points into the history it brings; a tag whose
    commit is on no branch, and the commit with it, stays on the remote. The
    tag's id is then an id the leg does not hold, which is the reachability
    verdict's, `bump-leg-commit-not-on-remote`, from BOTH runs: one answer,
    and no tags fetch of this tool's own to give another.

    The refusal is the existing one and nothing new: a pin the rest of the
    world can fetch only through a tag is a different question."""
    branched(project)
    run = runner(project, leg_remote, via)
    before = snapshot(project)

    stderr = assert_one_refusal(project, run, tag_only["tag"],
                                "bump-leg-commit-not-on-remote", before)

    assert not holds(project, tag_only["tag"]), "the fetch did not bring it"
    assert not holds(project, tag_only["commit"])
    assert "no branch containing" in stderr


# --- the branch a tag's id names, on the tracking branch --------------------

#: The branch a `git switch -c` line creates, wherever the line sits.
SWITCH_BRANCH = re.compile(r"switch -c (\S+)")


@pytest.mark.parametrize("via", VIA)
def test_the_dry_runs_branch_hint_names_the_branch_the_real_runs_refusal_names(
        project, leg_remote, release, via):
    """ON THE TRACKING BRANCH with an annotated tag's id as `--to`. The real
    run is refused `bump-leg-on-tracking-branch` BEFORE the fetch, naming
    `bump/spec-<the id as typed>`; `_branch_to_bump_from` has only the typed id
    to name it from. The dry run goes on, peels the tag, and ends with a hint
    for the same `git switch -c`. The hint reads the typed id as well, so a
    person who pastes either line creates ONE branch: the dry run does not
    name a branch from the peeled commit while the real run names it from the
    tag, which would be two answers to one question (#534)."""
    tag, commit = release["tag"], release["commit"]
    assert tag[:12] != commit[:12], "premise: the two ids name two branches"
    assert git("symbolic-ref", "--short", "HEAD",
               cwd=project).stdout.strip() == "main", (
        "premise: a fresh project stands on its tracking branch")
    run = runner(project, leg_remote, via)
    before = snapshot(project)

    dry = run(tag, "--dry-run")
    real = run(tag)

    assert dry.returncode == 0, dry.stderr + dry.stdout
    assert real.returncode == 2, real.stdout + real.stderr
    assert_nothing_changed(project, before)
    assert peel_line(tag, commit) in dry.stdout, "the dry run peeled the tag"
    assert "REFUSED bump-leg-on-tracking-branch" in real.stderr
    # The hint is the last line but one: the sentence #647 adds is under it.
    hint = dry.stdout.splitlines()[-2]
    assert "the real run needs a branch" in hint
    named_by_dry_run = SWITCH_BRANCH.search(hint).group(1)
    named_by_real_run = SWITCH_BRANCH.search(real.stderr).group(1)
    assert named_by_dry_run == named_by_real_run == f"bump/spec-{tag[:12]}"


# --- #438: a pin layout the rewrite refuses is refused by the dry run -------

def flow_mapping(text: str) -> str:
    """The issue's layout: `digests` as one flow mapping. The reader and
    `validate-pins.py` accept it; a LINE rewrite finds no `tree_sha256:`
    line in it."""
    digest = next(line.split('"')[1] for line in text.splitlines()
                  if line.startswith("  tree_sha256:"))
    laid = text.replace(f'digests:\n  tree_sha256: "{digest}"\n',
                        f'digests: {{tree_sha256: "{digest}"}}\n', 1)
    assert laid != text, "fixture: the scaffold's layout was found"
    return laid


def folded_commit(text: str) -> str:
    """`commit:`'s value on the line below its key: it reads, and it is the
    one layout the rewrite's own read-back refuses."""
    pinned = next(line.split('"')[1] for line in text.splitlines()
                  if line.startswith("commit:"))
    laid = text.replace(f'commit: "{pinned}"\n', f"commit: >-\n  {pinned}\n",
                        1)
    assert laid != text, "fixture: the scaffold's commit line was found"
    return laid


#: The layout, the words of the refusal, and what the rewrite found wrong.
REFUSED_LAYOUTS = {
    "a flow mapping for digests": (
        flow_mapping, "has 0 `tree_sha256` line(s)"),
    "commit folded onto the next line": (
        folded_commit, "does not read back to the target"),
}


@pytest.mark.parametrize("layout", REFUSED_LAYOUTS)
def test_a_pin_layout_the_rewrite_refuses_is_refused_by_the_dry_run_too(
        project, leg_remote, release, layout):
    """THE ISSUE'S FLOW. The pin is committed in a layout the validators accept
    and the rewrite cannot carry; before, the dry run printed `old -> new` and
    exited 0, and the real run exited 2 `bump-leg-pin-unrecognised` after
    the leg had been checked out. Both runs now refuse it, exit 2, in the
    same words, and neither wrote a byte or moved the leg.

    The leg stands ON its branch, as `bootstrap.py` leaves it, so a checkout
    of the leg is something the snapshot would see."""
    transform, why = REFUSED_LAYOUTS[layout]
    git("checkout", "-q", "-B", "main", cwd=project / "spec")
    branched(project)
    pin = project / SPEC_PIN
    commit_spec_pin(project, transform(pin.read_text(encoding="utf-8")),
                    "Lay the pin out another way")
    if transform is flow_mapping:
        assert validate(project).returncode == 0, (
            "premise: the project's own gate accepts the layout")
    before = snapshot(project)
    run = runner(project, leg_remote, "local-remote-dir")

    stderr = assert_one_refusal(project, run, release["commit"],
                                "bump-leg-pin-unrecognised", before)

    assert why in stderr
    assert "bump-leg-validators-red" not in stderr
    assert "rolled back" not in stderr, (
        "nothing was moved, so nothing needed rolling back")


def test_the_scaffolds_own_pin_layout_is_accepted_by_both_runs(
        project, leg_remote, release):
    """THE CONTROL: the layout every project has gives exit 0 from the dry run
    and exit 0 from the real run, and the real run commits."""
    reference_both_legs(project)
    branched(project)
    before = snapshot(project)
    run = runner(project, leg_remote, "local-remote-dir")

    dry = run(release["commit"], "--dry-run")
    assert dry.returncode == 0, dry.stderr + dry.stdout
    assert_nothing_changed(project, before)
    real = run(release["commit"])

    assert real.returncode == 0, real.stderr + real.stdout
    assert report_of(real, real=True) == report_of(dry, real=False)
    assert git("rev-parse", "HEAD:spec", cwd=project).stdout.strip() == (
        release["commit"])
    assert validate(project).returncode == 0
