# SPDX-License-Identifier: Apache-2.0
"""Where `bump-leg.py --to` refuses a commit as unreachable from the leg's
remote, the refusal's reason is true of the leg in front of the person, and
the fetch that answers prunes and moves no branch of the leg's own (#898).

THE STATES #795 FIXED IN `family.py bump` (#686), IN `bump-leg.py`'S TWINS:

- A COMMIT ONLY A TAG OF THE REMOTE REACHES, which the leg holds too (R613
  p03). Still refused `bump-leg-commit-local-only`: the rule is branches.
  The reason was "somebody committed inside the leg's mount and never pushed
  it", which the pushed tag disproves. It now says a tag of the remote
  reaches it and no branch does, and that the way out is a push to a branch.
  A tag only the leg has, or the remote's tag of the same name at another
  commit, keeps the plain words: the remote is asked by id.
- A LEG WITH NO `origin`, renamed to `upstream` or removed (R613 p10). Its
  fetch failed with no network at fault, and both refusals told it to "fix
  the network or the credential". The note, `bump-leg-commit-local-only` and
  `bump-leg-commit-not-on-remote` now say it has no remote named `origin`,
  and to give it back; a leg config git cannot read is git's failure, quoted.
- A BRANCH DELETED ON THE REMOTE SINCE THE LAST FETCH. Its stale
  remote-tracking ref counted, so a commit no ref of the remote keeps was
  pinned. The fetch now prunes, with `--no-prune-tags`: a ref under
  `refs/remotes/origin/` that no refspec of the fetch maps goes, and never a
  branch or a tag of the leg. The leg's own refspecs that write under
  `origin/` (pull requests, say) ride along, so what they keep there stays.
  The plain words no longer say "never pushed": that commit was pushed.
- GIT'S OPPORTUNISTIC UPDATE. A fetch of `origin` with refspecs on the
  command line also writes each ref it brings wherever `origin`'s CONFIGURED
  refspecs map it, so a leg configured `+refs/heads/*:refs/heads/*` had its
  own branches force-moved by the dry run, and a leg standing on one failed
  the fetch ("refusing to fetch into branch"). `--refmap=` turns that off.

A narrowing refspec of the leg's own, positive or negative, never decides
reachability, as it did not before: those cases are held here so the port
keeps them. Every remote a test writes is a private bare copy of the
session's spec remote, beside the root; the leg's `origin` points at it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import (FILE_PROTOCOL, ORG, PROJECT, REPO, cloned_just_pushed,
                      git, run_script)
from test_bump_leg import BUMP, SPEC_PIN, branched
from test_bump_leg_dry_run_truth import VIA, assert_one_refusal, tagged
from test_bump_leg_rollback import assert_nothing_changed, snapshot

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml  # noqa: E402

#: The spec leg's repository, as the scaffold's `project.yaml` names it.
REPOSITORY = f"{ORG}/{PROJECT}-spec"


def private_remote(project: Path, scaffolded: dict) -> Path:
    """A private bare copy of the spec leg's remote, beside the root, in the
    shape `--local-remote-dir` takes, with the leg's `origin` pointed at it.
    Returns the directory holding it."""
    remotes = project.parent / "remotes"
    bare = cloned_just_pushed(scaffolded["remotes"] / f"{PROJECT}-spec.git",
                              remotes / f"{PROJECT}-spec.git", bare=True)
    git("remote", "set-url", "origin", str(bare), cwd=project / "spec")
    return remotes


def bare_of(remotes: Path) -> Path:
    return remotes / f"{PROJECT}-spec.git"


def runner(project: Path, remotes: Path, via: str):
    """`run(to, *extra)` for this root, reaching the leg through its own
    `origin` or through `--local-remote-dir`."""
    local = ([] if via == "origin" else
             ["--local-remote-dir", str(remotes)])
    return lambda to, *extra: run_script(
        BUMP, "--root", str(project), "--leg", "spec", "--to", to, *local,
        *extra)


def made_in_the_leg(project: Path, name: str) -> str:
    """A commit made inside the leg's mount, adding `<name>.md`, with the leg
    put back where it stood, detached at the pin. Returns the commit."""
    leg = project / "spec"
    pinned = git("rev-parse", "HEAD", cwd=leg).stdout.strip()
    git("checkout", "-q", "--detach", cwd=leg)
    (leg / f"{name}.md").write_text(f"{name}\n", encoding="utf-8")
    git("add", "--", f"{name}.md", cwd=leg)
    git("commit", "-qm", name, cwd=leg)
    made = git("rev-parse", "HEAD", cwd=leg).stdout.strip()
    git("checkout", "-q", "--detach", pinned, cwd=leg)
    return made


def pushed(project: Path, what: str, ref: str) -> None:
    """`what` pushed from the leg to `ref` of its (private) `origin`."""
    git(*FILE_PROTOCOL, "push", "-q", "origin", f"{what}:{ref}",
        cwd=project / "spec")


def contains(repository: Path, commit: str, prefix: str) -> bool:
    """Whether a ref under `prefix` in `repository` contains `commit`."""
    return git("for-each-ref", "--contains", commit, prefix,
               cwd=repository).stdout != ""


def refusal(stderr: str) -> tuple[str, str]:
    """`(the REFUSED line, the line after it)`, and nothing else printed."""
    lines = stderr.splitlines()
    assert len(lines) == 2, stderr
    return lines[0], lines[1]


def pins(project: Path, run, commit: str) -> None:
    """The real run pins `commit`: exit 0, the gitlink and `commit:`."""
    real = run(commit)
    assert real.returncode == 0, real.stdout + real.stderr
    assert git("rev-parse", "HEAD:spec", cwd=project).stdout.strip() == commit
    assert load_yaml(project / SPEC_PIN)["commit"] == commit


def local_only(commit: str) -> tuple[str, str]:
    """`bump-leg-commit-local-only`'s plain two lines, a fetch that worked:
    no longer "somebody ... never pushed it", which a commit pushed to a
    branch since deleted is not."""
    return (
        f"REFUSED bump-leg-commit-local-only: {commit} is in the leg's own "
        f"object store but is reachable from no branch of {REPOSITORY}",
        "Remediation: push it to a branch of the leg and re-run; the "
        "commonest such commit was made inside the leg's mount and never "
        "pushed. A pin the rest of the world cannot fetch is a root the rest "
        "of the world cannot bootstrap.")


# --- R613 p03: a commit only a tag of the remote reaches --------------------

@pytest.mark.parametrize("typed", ["commit", "annotated-tag"])
@pytest.mark.parametrize("via", VIA)
def test_a_commit_only_a_tag_of_the_remote_reaches_is_told_so(
        project, scaffolded, via, typed):
    """A commit on no branch of the leg's remote, pushed with its tag alone,
    as a release can be: the leg holds both. Both runs still refuse it
    `bump-leg-commit-local-only`, in the same two lines, with nothing moved,
    through the leg's `origin` and through `--local-remote-dir`, typed as the
    commit or as its annotated tag's own id. The reason is the true one: a
    tag of the remote reaches it and no branch does, never "never pushed".
    Its way out works: pushed to a branch, it is pinned."""
    remotes = private_remote(project, scaffolded)
    leg = project / "spec"
    made = made_in_the_leg(project, "RELEASE")
    tag = tagged(leg, "v-release-w898", made)
    pushed(project, "refs/tags/v-release-w898", "refs/tags/v-release-w898")
    assert not contains(bare_of(remotes), made, "refs/heads/"), (
        "premise: no branch of the leg's remote reaches it")
    assert contains(bare_of(remotes), made, "refs/tags/"), (
        "premise: a tag of the leg's remote does")
    assert not contains(leg, made, "refs/remotes/"), (
        "premise: no remote-tracking ref of the leg does")
    branched(project)
    run = runner(project, remotes, via)
    before = snapshot(project)

    stderr = assert_one_refusal(project, run,
                                made if typed == "commit" else tag,
                                "bump-leg-commit-local-only", before)

    assert refusal(stderr) == (
        f"REFUSED bump-leg-commit-local-only: {made} is in the leg's own "
        f"object store, and a tag of {REPOSITORY} reaches it, but no branch "
        f"of {REPOSITORY} does",
        "Remediation: push it to a branch of the leg and re-run — a bump "
        "pins only a commit a branch of the leg's remote reaches, and a tag "
        "is not a branch.")

    pushed(project, made, "refs/heads/release-w898")
    pins(project, run, made)


def test_a_tag_of_the_same_name_at_another_commit_keeps_the_plain_words(
        project, scaffolded):
    """THE REMOTE IS ASKED BY ID, NOT BY NAME. The leg tags a commit only it
    holds `v-same`, and the remote has a `v-same` of its own, at the pin.
    That tag does not reach the commit, so both runs keep the plain words,
    "a pin the rest of the world cannot fetch" included, which are true of
    it; the fetch leaves the leg's own tag as it was."""
    remotes = private_remote(project, scaffolded)
    leg = project / "spec"
    made = made_in_the_leg(project, "SAME")
    git("tag", "v-same", made, cwd=leg)
    pinned = git("rev-parse", "HEAD", cwd=leg).stdout.strip()
    git("tag", "v-same", pinned, cwd=bare_of(remotes))
    assert git("cat-file", "-e", made, cwd=bare_of(remotes),
               check=False).returncode != 0, (
        "premise: the remote does not hold it, so its `v-same` cannot reach "
        "it")
    branched(project)
    run = runner(project, remotes, "origin")
    before = snapshot(project)

    stderr = assert_one_refusal(project, run, made,
                                "bump-leg-commit-local-only", before)

    assert refusal(stderr) == local_only(made)
    assert git("rev-parse", "v-same", cwd=leg).stdout.strip() == made, (
        "the leg's own tag is as it was")


# --- R613 p10: a leg with no remote named `origin` --------------------------

#: The note both runs print first when the leg has no remote named `origin`.
NO_ORIGIN_NOTE = ("  note: `git fetch origin` in spec exited 128: spec has no "
                  "remote named `origin`; answering from the remote-tracking "
                  "refs this checkout already has")


def origin_back(project: Path) -> str:
    """What a leg with no `origin` is told to do, in both refusals."""
    mount = project.resolve() / "spec"
    return (f"give {mount} back a remote named `origin`, for {REPOSITORY}, "
            "and re-run: this tool fetches the leg's branches from `origin` "
            "and asks no other remote")


def without_origin(project: Path, gone: str) -> str:
    """The leg's `origin` renamed to `upstream`, or removed, as `gone` says;
    returns its URL, for the way back."""
    leg = project / "spec"
    url = git("remote", "get-url", "origin", cwd=leg).stdout.strip()
    if gone == "renamed":
        git("remote", "rename", "origin", "upstream", cwd=leg)
    else:
        git("remote", "remove", "origin", cwd=leg)
    assert git("remote", "get-url", "origin", cwd=leg,
               check=False).returncode == 2, "premise: no remote `origin`"
    return url


def told_no_origin(stderr: str) -> tuple[str, str]:
    """The refusal after the note that the leg has no `origin`, and nothing
    about a network or a credential anywhere in it."""
    lines = stderr.splitlines()
    assert lines[0] == NO_ORIGIN_NOTE, stderr
    assert "network" not in stderr
    assert "credential" not in stderr
    return refusal("\n".join(lines[1:]))


@pytest.mark.parametrize("gone", ["renamed", "removed"])
def test_a_leg_with_no_origin_is_told_so_and_not_to_fix_the_network(
        project, scaffolded, gone):
    """R613 p10. A commit pushed to a branch of the leg's remote, in a leg
    whose `origin` was renamed to `upstream` (so `upstream/<branch>` holds
    it) or removed. The fetch of `origin` fails, and both runs said the
    commit was "never pushed" and to fix the network or the credential. Now,
    with nothing moved, the note says the leg has no remote named `origin`,
    and the refusal that whether a branch reaches the commit is therefore
    not known, and to give it back. That way out works: given back, the same
    commit is pinned."""
    remotes = private_remote(project, scaffolded)
    leg = project / "spec"
    made = made_in_the_leg(project, "UPSTREAM")
    pushed(project, made, "refs/heads/pushed-w898")
    url = without_origin(project, gone)
    if gone == "renamed":
        assert contains(leg, made, "refs/remotes/upstream/"), (
            "premise: a remote-tracking branch of `upstream` holds it")
    branched(project)
    run = runner(project, remotes, "origin")
    before = snapshot(project)

    stderr = assert_one_refusal(project, run, made,
                                "bump-leg-commit-local-only", before)

    assert told_no_origin(stderr) == (
        f"REFUSED bump-leg-commit-local-only: {made} is in the leg's own "
        f"object store, but the leg's mount, {project.resolve() / 'spec'}, "
        f"has no remote named `origin`, so whether a branch of {REPOSITORY} "
        "reaches it is not known",
        f"Remediation: {origin_back(project)}. If the commit is not pushed "
        "yet, push it to a branch of the leg first.")

    if gone == "renamed":
        git("remote", "rename", "upstream", "origin", cwd=leg)
    else:
        git("remote", "add", "origin", url, cwd=leg)
    pins(project, run, made)


def test_an_id_a_leg_with_no_origin_lacks_is_not_put_down_to_the_network(
        project, scaffolded):
    """R613 p10, `bump-leg-commit-not-on-remote`'s half. An id the leg does
    not hold, in a leg with no `origin`: both runs said the remote has no
    branch containing it and to fix the network or the credential. Now they
    say the leg has no remote named `origin` to fetch it from, and to push
    it if it is not pushed and give the leg its `origin` back."""
    remotes = private_remote(project, scaffolded)
    without_origin(project, "renamed")
    missing = "deadbeef" * 5
    branched(project)
    run = runner(project, remotes, "origin")
    before = snapshot(project)

    stderr = assert_one_refusal(project, run, missing,
                                "bump-leg-commit-not-on-remote", before)

    assert told_no_origin(stderr) == (
        f"REFUSED bump-leg-commit-not-on-remote: {missing} is not in the "
        f"leg's own object store, and the leg's mount, "
        f"{project.resolve() / 'spec'}, has no remote named `origin` to "
        f"fetch it from, so whether a branch of {REPOSITORY} reaches it is "
        "not known",
        "Remediation: check the commit — it belongs to the LEG, not to the "
        "assembly root — and push it to a branch of the leg first if it is "
        f"not pushed yet; {origin_back(project)}.")


#: A `url` with no value under the leg's `[remote "origin"]`. Git's config
#: parser reads it as a key with no value, so every read of the config that
#: asks no remote works; git's remote reader dies over it (measured, git
#: 2.43): `git remote get-url origin` and the fetch exit 128.
VALUELESS_URL = b'[remote "origin"]\n\turl\n'


def test_a_leg_config_git_cannot_read_is_gits_own_failure(
        project, scaffolded):
    """WHETHER THE LEG HAS AN `origin` IS GIT'S ANSWER, never a guess. `git
    remote get-url origin` exits 2 for "No such remote" alone; a leg whose
    `origin` has a `url` with no value fails its fetch and that question
    with 128, and both runs print git's failure, the exact command, git's
    own words and exit 2, rather than telling the person the leg has no
    `origin` or to fix the network. Nothing in the root moves."""
    private_remote(project, scaffolded)
    leg = project / "spec"
    made = made_in_the_leg(project, "CONFIG")
    pushed(project, made, "refs/heads/config-w898")
    config = Path(git("rev-parse", "--absolute-git-dir", cwd=leg)
                  .stdout.strip()) / "config"
    config.write_bytes(config.read_bytes() + VALUELESS_URL)
    asked = git("remote", "get-url", "origin", cwd=leg, check=False)
    assert asked.returncode == 128, "premise: git's own failure, not 2"
    said = asked.stderr.strip()
    assert "missing value for 'remote.origin.url'" in said
    branched(project)
    run = runner(project, project.parent / "remotes", "origin")
    before = snapshot(project)

    dry = run(made, "--dry-run")
    real = run(made)

    assert_nothing_changed(project, before)
    assert dry.returncode == real.returncode == 2, real.stdout + real.stderr
    assert dry.stderr == real.stderr
    assert "THE EXACT COMMAND WAS:\n    git remote get-url origin\n" in (
        real.stderr)
    assert f"--- output ---\n{said}\n--- end output ---" in real.stderr
    assert "    exit 128\n" in real.stderr
    for word in ("no remote named", "network", "credential"):
        assert word not in real.stderr


# --- a fetch that failed: the words say so, and no more ---------------------

#: What a refusal ends with, after its plain words, when the fetch failed: the
#: answer came from remote-tracking refs that fetch did not renew.
STALE = (" The fetch above FAILED, so this was answered from stale "
         "remote-tracking refs; fix the network or the credential and "
         "re-run before believing it.")

#: A refspec of the leg's own that names a branch its remote does not have.
#: Git cannot satisfy it, so the fetch fails with 128 ("couldn't find remote
#: ref"), as the person's own `git fetch origin` does, while `git ls-remote`
#: still answers.
MISSING = "+refs/heads/trunk:refs/remotes/origin/trunk"


def failed_fetch_note(remote: str) -> str:
    """The note both runs print first when `git fetch <remote>` failed in a
    leg that HAS a remote named `origin` to ask: the exit and the stale-refs
    answer, and no word of a missing `origin`."""
    return (f"  note: `git fetch {remote}` in spec exited 128; answering "
            "from the remote-tracking refs this checkout already has")


def test_a_tag_is_not_asked_of_a_remote_the_fetch_could_not_read(
        project, scaffolded):
    """THE TAG CHECK IS ASKED ONLY AFTER A FETCH THAT WORKED. A commit only a
    tag of the leg's remote reaches, as in R613 p03, in a leg whose own
    refspec names a branch the remote lacks (`MISSING`): the fetch fails with
    128, where `git ls-remote` still answers and lists the tag. Both runs
    refuse it `bump-leg-commit-local-only` in the plain words with the
    stale-refs sentence after them, as for any commit after a failed fetch,
    and never in the tag words, which are said of a remote the fetch read.
    Nothing in the root moves."""
    remotes = private_remote(project, scaffolded)
    leg = project / "spec"
    made = made_in_the_leg(project, "TAGFAIL")
    tag = tagged(leg, "v-failed-w898", made)
    pushed(project, "refs/tags/v-failed-w898", "refs/tags/v-failed-w898")
    git("config", "--unset-all", "remote.origin.fetch", cwd=leg)
    git("config", "--add", "remote.origin.fetch", MISSING, cwd=leg)
    assert contains(bare_of(remotes), made, "refs/tags/"), (
        "premise: a tag of the leg's remote reaches it")
    assert not contains(bare_of(remotes), made, "refs/heads/"), (
        "premise: no branch of the leg's remote does")
    assert not contains(leg, made, "refs/remotes/"), (
        "premise: no remote-tracking ref of the leg does")
    failed = git(*FILE_PROTOCOL, "fetch", "-q", "origin", cwd=leg,
                 check=False)
    assert failed.returncode == 128, "premise: git's own fetch fails"
    assert "couldn't find remote ref" in failed.stderr
    listed = git(*FILE_PROTOCOL, "ls-remote", "--tags", "--refs", "origin",
                 cwd=leg).stdout
    assert tag in listed, "premise: the remote still lists the tag, by id"
    branched(project)
    run = runner(project, remotes, "origin")
    before = snapshot(project)

    stderr = assert_one_refusal(project, run, made,
                                "bump-leg-commit-local-only", before)

    note, *rest = stderr.splitlines()
    assert note == failed_fetch_note("origin")
    plain, remediation = local_only(made)
    assert refusal("\n".join(rest)) == (plain, remediation + STALE)


def test_a_stand_in_directory_the_leg_lacks_fails_the_fetch_not_the_origin(
        project):
    """`--local-remote-dir` NAMES NO REMOTE OF THE LEG'S, so whether the leg
    has an `origin` is not what failed. A leg with no `origin` at all, and a
    directory that holds no `<repo>.git`: the fetch of that path fails with
    128, and both runs say only that, in the note, and refuse the commit the
    leg holds in the plain words with the stale-refs sentence. The note does
    not say the leg has no remote named `origin`, which is true and has
    nothing to do with a path the fetch was given. Nothing in the root
    moves."""
    made = made_in_the_leg(project, "NOWHERE")
    without_origin(project, "removed")
    empty = project.parent / "empty-remotes"
    empty.mkdir()
    absent = empty.resolve() / f"{PROJECT}-spec.git"
    assert not absent.exists(), (
        "premise: the directory holds no copy of the leg's remote")
    branched(project)
    run = runner(project, empty, "local-remote-dir")
    before = snapshot(project)

    stderr = assert_one_refusal(project, run, made,
                                "bump-leg-commit-local-only", before)

    note, *rest = stderr.splitlines()
    assert note == failed_fetch_note(str(absent))
    assert "no remote named" not in stderr
    plain, remediation = local_only(made)
    assert refusal("\n".join(rest)) == (plain, remediation + STALE)


# --- a branch deleted on the remote: the fetch prunes -----------------------

#: A pull-request refspec, as GitHub's documents give it: the leg's own,
#: keeping under `origin/` refs that no branch backs.
PULLS = "+refs/pull/*/head:refs/remotes/origin/pr/*"

#: A refspec of the leg that writes outside `refs/remotes/origin/`.
NOTES = "+refs/notes/*:refs/notes/*"


def refs(leg: Path) -> list[str]:
    """Every ref of the leg, with the object it names."""
    return git("for-each-ref", "--format=%(refname) %(objectname)",
               cwd=leg).stdout.splitlines()


def under_origin(ref: str, *kept: str) -> bool:
    """Whether a `refs()` line is under `refs/remotes/origin/` and none of
    `kept`, the remote-tracking refs a test expects to survive."""
    return ref.startswith("refs/remotes/origin/") and not any(
        ref.startswith(f"refs/remotes/origin/{name} ") for name in kept)


@pytest.mark.parametrize("via", VIA)
def test_a_branch_deleted_on_the_remote_since_the_last_fetch_no_longer_counts(
        project, scaffolded, via):
    """A commit pushed to a branch of the leg's remote, and that branch
    deleted there after the leg last fetched: the leg's remote-tracking ref
    still contained it, so both runs pinned it, the dry run exit 0, with no
    ref of the remote keeping it. The fetch now prunes that ref, and both
    refuse `bump-leg-commit-local-only` in the plain words, with nothing
    moved, through `origin` and through `--local-remote-dir`.

    WHAT NOTHING ON THE REMOTE BACKS GOES, AND NOTHING ELSE: the leg's own
    branch and tag on the commit stay, in a leg set to prune tags (which
    git 2.43 applies to no fetch with refspecs on its command line, so
    `--no-prune-tags` is belt and braces here, measured), and so does
    `origin/HEAD`. The leg's own refspec keeps pull requests under
    `origin/`: `pr/7`, which the remote still has, stays, and `pr/8`, which
    it deleted, goes, pruned against that refspec alone; a ref put there by
    hand, which no refspec maps, goes too. A refspec of the leg that writes
    OUTSIDE `origin/` (`NOTES`) is not put on the command line."""
    remotes = private_remote(project, scaffolded)
    bare = bare_of(remotes)
    leg = project / "spec"
    pin = git("rev-parse", "HEAD", cwd=leg).stdout.strip()
    made = made_in_the_leg(project, "DELETED")
    pushed(project, made, "refs/heads/gone-w898")
    stale = "refs/remotes/origin/gone-w898"
    for number in ("7", "8"):
        git("update-ref", f"refs/pull/{number}/head", pin, cwd=bare)
    git("config", "--add", "remote.origin.fetch", PULLS, cwd=leg)
    git(*FILE_PROTOCOL, "fetch", "-q", "origin", cwd=leg)
    git("config", "--add", "remote.origin.fetch", NOTES, cwd=leg)
    git("update-ref", "refs/notes/review", pin, cwd=bare)
    git("update-ref", "-d", "refs/pull/8/head", cwd=bare)
    git("update-ref", "-d", "refs/heads/gone-w898", cwd=bare)
    git("update-ref", "refs/remotes/origin/by-hand", pin, cwd=leg)
    assert not contains(bare, made, "refs/"), (
        "premise: no ref of the leg's remote reaches it")
    assert contains(leg, made, stale), (
        "premise: the leg's stale remote-tracking ref still does")
    git("branch", "mine", made, cwd=leg)
    git("tag", "mine-tag", made, cwd=leg)
    git("config", "remote.origin.pruneTags", "true", cwd=leg)
    before_refs = refs(leg)
    for name in ("pr/7", "pr/8", "by-hand"):
        assert f"refs/remotes/origin/{name} {pin}" in before_refs, (
            f"premise: the leg holds origin/{name}")
    kept = [ref for ref in before_refs if not under_origin(ref, "HEAD")]
    branched(project)
    run = runner(project, remotes, via)
    before = snapshot(project)

    stderr = assert_one_refusal(project, run, made,
                                "bump-leg-commit-local-only", before)

    assert refusal(stderr) == local_only(made)
    after = refs(leg)
    assert [ref for ref in after if not under_origin(ref, "HEAD")] == kept, (
        "no branch, no tag and not `origin/HEAD` was touched")
    assert not [ref for ref in after if ref.startswith("refs/notes/")], (
        "a refspec of the leg that writes outside `origin/` is not named")
    assert f"refs/remotes/origin/pr/7 {pin}" in after, (
        "the pull request the leg's own refspec keeps, and the remote still "
        "has, stays")
    for gone in (stale, "refs/remotes/origin/pr/8",
                 "refs/remotes/origin/by-hand"):
        assert not [ref for ref in after if ref.startswith(gone + " ")], (
            f"{gone}, which nothing on the remote backs, is pruned")


#: A pull-request refspec the leg wrote WITHOUT the `+`, as a person may.
UNFORCED = "refs/pull/*/head:refs/remotes/origin/pr/*"


def test_the_legs_own_refspecs_are_forced_as_the_first_is(project,
                                                          scaffolded):
    """A REMOTE-TRACKING REF ONLY MIRRORS THE REMOTE, so each refspec of the
    leg's own that rides along is forced, whether the leg wrote its `+` or
    not. The leg keeps pull requests under `origin/` with `UNFORCED`, and the
    remote's `pull/7` was moved BACK, as a force-push does: the person's own
    `git fetch origin` refuses that ref and exits 1. This fetch does not fail:
    both runs print no note, `origin/pr/7` follows the remote, and the commit
    a branch of the remote reaches is pinned. Without the `+` the fetch
    exited 1, said so in a note and answered from stale refs. The leg's
    refspecs are as they were."""
    remotes = private_remote(project, scaffolded)
    bare = bare_of(remotes)
    leg = project / "spec"
    pin = git("rev-parse", "HEAD", cwd=leg).stdout.strip()
    made = made_in_the_leg(project, "REWOUND")
    pushed(project, made, "refs/heads/rewound-w898")
    git("update-ref", "refs/pull/7/head", made, cwd=bare)
    git("config", "--add", "remote.origin.fetch", UNFORCED, cwd=leg)
    git(*FILE_PROTOCOL, "fetch", "-q", "origin", cwd=leg)
    assert f"refs/remotes/origin/pr/7 {made}" in refs(leg), (
        "premise: the leg holds the pull request as it was")
    git("update-ref", "refs/pull/7/head", pin, cwd=bare)
    own = git(*FILE_PROTOCOL, "fetch", "origin", cwd=leg, check=False)
    assert own.returncode == 1, "premise: the person's own fetch refuses it"
    assert "non-fast-forward" in own.stderr
    # A fetch that failed must not be answered from the branch it brought.
    git("update-ref", "-d", "refs/remotes/origin/rewound-w898", cwd=leg)
    configured = git("config", "--get-all", "remote.origin.fetch",
                     cwd=leg).stdout
    branched(project)
    run = runner(project, remotes, "origin")

    dry = run(made, "--dry-run")

    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert dry.stderr == "", "the fetch worked: no note"
    assert f"refs/remotes/origin/pr/7 {pin}" in refs(leg), (
        "the pull request follows the remote, forced")
    pins(project, run, made)
    assert git("config", "--get-all", "remote.origin.fetch",
               cwd=leg).stdout == configured, "the refspecs are as they were"


# --- `--refmap=`: the fetch moves no branch of the leg's own ----------------

#: A refspec of the leg's own that maps the remote's branches onto ITS
#: branches, as a mirror's configuration does.
MIRRORED = "+refs/heads/*:refs/heads/*"


def heads(leg: Path) -> str:
    """The leg's own branches, with the commit each names."""
    return git("for-each-ref", "--format=%(refname) %(objectname)",
               "refs/heads/", cwd=leg).stdout


@pytest.mark.parametrize("placed", ["detached", "on-a-branch"])
def test_the_fetch_moves_no_branch_of_the_legs_own(project, scaffolded,
                                                    placed):
    """A leg whose `origin` is configured `+refs/heads/*:refs/heads/*` beside
    its remote-tracking refspec. Git's opportunistic update wrote each branch
    the fetch brought through that refspec too, forced: DETACHED, the leg's
    local `main`, holding a commit never pushed, was moved to the remote's
    `main` by the dry run; ON A BRANCH (`main`, as `bootstrap.py` leaves a
    leg), git refused the whole fetch, "refusing to fetch into branch", and
    the answer came from stale refs after a note. With `--refmap=` both runs
    fetch, print no note, pin the pushed commit, and leave every branch of
    the leg's own, and its refspecs, as they were."""
    remotes = private_remote(project, scaffolded)
    leg = project / "spec"
    pin = git("rev-parse", "HEAD", cwd=leg).stdout.strip()
    made = made_in_the_leg(project, "ADVANCE")
    pushed(project, made, "refs/heads/advance-w898")
    # The push wrote `origin/advance-w898` into the leg; a fetch that failed
    # must not be answered from it.
    git("update-ref", "-d", "refs/remotes/origin/advance-w898", cwd=leg)
    unpushed = made_in_the_leg(project, "UNPUSHED")
    if placed == "detached":
        git("branch", "-f", "main", unpushed, cwd=leg)
    else:
        pushed(project, pin, "refs/heads/side-w898")
        git("branch", "-f", "side-w898", unpushed, cwd=leg)
        git("checkout", "-q", "-B", "main", pin, cwd=leg)
    git("config", "--add", "remote.origin.fetch", MIRRORED, cwd=leg)
    configured = git("config", "--get-all", "remote.origin.fetch",
                     cwd=leg).stdout
    own = heads(leg)
    assert unpushed in own, (
        "premise: a branch of the leg holds a commit the remote does not")
    branched(project)
    run = runner(project, remotes, "origin")

    dry = run(made, "--dry-run")

    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert dry.stderr == "", "the fetch worked: no note"
    assert f"commit       {pin[:12]} -> {made[:12]}" in dry.stdout
    assert heads(leg) == own, "the dry run moved no branch of the leg's own"

    pins(project, run, made)
    assert heads(leg) == own, "nor did the real run"
    assert git("config", "--get-all", "remote.origin.fetch",
               cwd=leg).stdout == configured, "the refspecs are as they were"


# --- a narrowing refspec of the leg's own never decides reachability --------

@pytest.mark.parametrize("narrowing", [
    "+refs/heads/main:refs/remotes/origin/main", None,
    "^refs/heads/side-w898"],
    ids=["main-only", "no-refspec", "negative"])
def test_a_narrowing_refspec_of_the_legs_own_never_decides_reachability(
        project, scaffolded, narrowing):
    """A commit pushed to a branch the leg's own refspec does not fetch: one
    narrowed to `main`, as a single-branch clone leaves it, none at all, as
    an `origin` with a URL and nothing else has, or a negative refspec that
    excludes the branch. The leg's own refspecs that write under `origin/`
    now ride along on the fetch (for the prune), and the first refspec, every
    branch, still overrides each narrowing, so both runs find the commit on a
    branch of the remote and the real run pins it. The refspecs are the
    person's and are left as they were."""
    remotes = private_remote(project, scaffolded)
    leg = project / "spec"
    made = made_in_the_leg(project, "SIDE")
    pushed(project, made, "refs/heads/side-w898")
    if narrowing is None or not narrowing.startswith("^"):
        git("config", "--unset-all", "remote.origin.fetch", cwd=leg)
    if narrowing is not None:
        git("config", "--add", "remote.origin.fetch", narrowing, cwd=leg)
    git("update-ref", "-d", "refs/remotes/origin/side-w898", cwd=leg)
    assert not contains(leg, made, "refs/remotes/"), (
        "premise: no remote-tracking ref of the leg holds it")
    configured = git("config", "--get-all", "remote.origin.fetch", cwd=leg,
                     check=False).stdout
    branched(project)
    run = runner(project, remotes, "origin")

    dry = run(made, "--dry-run")

    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert dry.stderr == ""
    assert contains(leg, made, "refs/remotes/origin/side-w898"), (
        "the branch the leg's refspec leaves out was fetched")
    pins(project, run, made)
    assert git("config", "--get-all", "remote.origin.fetch", cwd=leg,
               check=False).stdout == configured, (
        "the refspecs are as they were")
