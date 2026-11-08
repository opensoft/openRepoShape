# SPDX-License-Identifier: Apache-2.0
"""A source with no remote named `origin` is read from its only remote
(#1276).

`git clone` names the remote after `clone.defaultRemoteName`, so a person
with `upstream` there has a clone whose one remote is `upstream`.
`adopt-project.py` read only a remote named `origin`: the organisation
(`_origin_url`), the default branch (`refs/remotes/origin/HEAD`) and the
branches a tracking branch is asked of (`refs/remotes/origin/*`). So `plan`
with no `--org` refused `adopt-no-org`, read the branch HEAD was on as the
default branch, and asked `--tracking-branch` of the source's own branches,
where the same source with its remote named `origin` read the organisation,
`origin/HEAD` and `origin`'s branches.

Now, where a source has no `origin`, its only remote is read in that one's
place, as git itself reads it when no remote is named (`git ls-remote
--get-url`: the current branch's remote, else the only remote, else
`origin`). A source with an `origin` reads exactly as before, whatever other
remotes it has, and so does one with no remote. One with several remotes and
none named `origin` is not guessed among: `adopt-no-org` and
`plan-tracking-branch-missing` name the remotes passed over.

Not #1261: that names the remote of each clone `execute` makes `origin`.
This is the person's own repository, whose remote the tool does not name.
Every source here is cloned with `-c clone.defaultRemoteName=upstream` and
the tool runs under the session's global config, so the clones `execute`
makes name their remote `origin` either way. Nothing fetches from GitHub: a
remote's url is set to GitHub's after its clone or fetch from a bare
repository here. The only `gh` run is `check`'s, answered by the session's
guard (`tests/gh_guard.py`) as a `gh` with no login.
"""

from __future__ import annotations

import shutil
import sys

import pytest

from conftest import ADOPT, FILE_PROTOCOL, REPO, git, make_source_repo, \
    run_script

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml  # noqa: E402

#: A source small enough that `plan` asks no question.
TREE = {"README.md": "# Thing\n", "src/app.py": "print(1)\n",
        "docs/spec.md": "# Spec\n"}
ORG, PROJECT = "testorg", "Thing"
GITHUB_URL = f"https://github.com/{ORG}/{PROJECT}.git"
FORK_URL = f"https://github.com/someone/{PROJECT}.git"
UPSTREAM = "upstream"
MISSING = "plan-tracking-branch-missing"
needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")


def bare_of(tmp_path, owner: str, extra: str):
    """A bare repository `<owner>/Thing.git` of a one-commit `main`, with a
    branch `extra` beside it."""
    seed = make_source_repo(tmp_path / f"seed-{owner}", tree=TREE, edits=())
    git("branch", extra, cwd=seed)
    bare = tmp_path / owner / f"{PROJECT}.git"
    git(*FILE_PROTOCOL, "clone", "-q", "--bare", str(seed), str(bare),
        cwd=tmp_path)
    return bare


def cloned_as(tmp_path, remote: str, *flags: str):
    """The source `Thing`, cloned from `testorg/Thing.git` (`main`, and
    `develop`) under `clone.defaultRemoteName=<remote>`, with that remote's
    url then GitHub's, and HEAD on a branch `feature` of its own, so that
    the default branch is not HEAD's."""
    bare = bare_of(tmp_path, ORG, "develop")
    source = tmp_path / PROJECT
    git(*FILE_PROTOCOL, "-c", f"clone.defaultRemoteName={remote}", "clone",
        "-q", *flags, str(bare), str(source), cwd=tmp_path)
    git("remote", "set-url", remote, GITHUB_URL, cwd=source)
    return source


def with_fork(tmp_path, source, track: bool = False) -> None:
    """A second remote `fork` added to `source` and fetched (`main`, and
    `forkonly`), its url then GitHub's; with `track`, the source's HEAD on a
    branch that tracks it."""
    bare = bare_of(tmp_path, "someone", "forkonly")
    git("remote", "add", "fork", str(bare), cwd=source)
    git(*FILE_PROTOCOL, "fetch", "-q", "fork", cwd=source)
    git("remote", "set-url", "fork", FORK_URL, cwd=source)
    if track:
        git("switch", "-q", "-c", "onfork", "--track", "fork/forkonly",
            cwd=source)


def planned(tmp_path, source, *flags: str, name: str = "plan"):
    """`plan` of `source` as `Thing`, with the flags given: the run and the
    plan's path."""
    out = tmp_path / f"{name}.yaml"
    result = run_script(ADOPT, "plan", "--source", str(source), "--project",
                        PROJECT, "--elected-by", "Test Human",
                        "--elected-on", "2026-11-08", "--out", str(out),
                        *flags)
    return result, out


def check(plan):
    return run_script(ADOPT, "check", "--plan", str(plan))


# --- the issue's rows: a source cloned under `upstream` ----------------------

def test_plan_reads_the_organisation_from_the_only_remote(tmp_path):
    """The issue's first row. On main: `REFUSED adopt-no-org: the source's
    `origin` names no organisation`, exit 2, where the same source with
    `origin` planned `testorg`. Now the organisation and the repository are
    read from `upstream`, and the `source` line names the remote read."""
    source = cloned_as(tmp_path, UPSTREAM)
    git("switch", "-q", "-c", "feature", cwd=source)

    result, plan = planned(tmp_path, source)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "adopt-no-org" not in result.stderr, result.stderr
    written = load_yaml(plan)
    assert written["org"] == ORG, written
    assert written["source"]["repository"] == f"{ORG}/{PROJECT}"
    assert f"{source} (upstream: {ORG}/{PROJECT}) @ " in result.stdout, \
        result.stdout


def test_the_default_branch_is_the_only_remotes_head(tmp_path):
    """The issue's second row, the default branch. The source's HEAD is on
    `feature`, and `upstream/HEAD` names `main`. On main `plan` read HEAD's
    branch, `feature`, as the default and the tracking branch, as for a
    source with no remote; with `origin` it read `main`. Now `main`."""
    source = cloned_as(tmp_path, UPSTREAM)
    git("switch", "-q", "-c", "feature", cwd=source)

    result, plan = planned(tmp_path, source, "--org", ORG)

    assert result.returncode == 0, result.stdout + result.stderr
    written = load_yaml(plan)
    assert written["source"]["default_branch"] == "main", written["source"]
    assert written["tracking_branch"] == "main", written


def test_a_tracking_branch_is_asked_of_the_only_remotes_branches(tmp_path):
    """The issue's second row, `--tracking-branch`. `develop` is a branch of
    `upstream` the source has not made its own. On main `plan` noted it as
    "no branch of the source (its branches: `feature`, `main`...)" and
    `check` found it, exit 1, where the same source with `origin` checked
    ok. Now it checks ok; and `wip`, a branch of the source's own alone, is
    found as no branch of `upstream`, with the fetch from `upstream`."""
    source = cloned_as(tmp_path, UPSTREAM)
    git("switch", "-q", "-c", "feature", cwd=source)
    git("branch", "wip", cwd=source)

    result, plan = planned(tmp_path, source, "--org", ORG,
                           "--tracking-branch", "develop")
    assert result.returncode == 0, result.stdout + result.stderr
    assert MISSING not in result.stdout + result.stderr, result.stdout
    checked = check(plan)
    assert checked.returncode == 0, checked.stdout + checked.stderr

    result, plan = planned(tmp_path, source, "--org", ORG,
                           "--tracking-branch", "wip", name="wip")
    found = ("is `wip`, which is no branch of the source's remote `upstream` "
             "(its branches: `develop`, `main`; the source's default branch "
             "is `main`)")
    assert f"NOTE the tracking branch {found}" in result.stdout, result.stdout
    checked = check(plan)
    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert f"FINDING {MISSING}: `tracking_branch` {found}" in checked.stderr
    assert "(`git fetch upstream`), and then `check` is run again." in \
        checked.stderr, checked.stderr


@needs_filter_repo
def test_execute_names_the_only_remote_in_its_way_through(tmp_path):
    """`execute --local-remote-dir` of the `develop` plan: `check`'s reading
    passes it, and the source itself, where the split goes, has no
    `develop`, so it is refused before any leg exists, as for the same
    source with `origin`, and each command it gives is run with `upstream`.
    On main it was refused as `check`'s finding, `develop` being no branch
    it read."""
    source = cloned_as(tmp_path, UPSTREAM)
    _, plan = planned(tmp_path, source, "--org", ORG,
                      "--tracking-branch", "develop")

    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))

    assert result.returncode == 2, result.stdout + result.stderr
    said = " ".join(result.stderr.split())
    assert f"REFUSED {MISSING}: `tracking_branch` is `develop`, which " in said
    assert "as `check` prints them" not in said, said
    assert ("run `git fetch --prune upstream` and `git remote set-head "
            "upstream --auto`") in said, said
    assert ("one only its remote `upstream` has is not: `git branch <name> "
            "upstream/<name>` makes it one.") in said, said
    assert "origin" not in said, said
    assert not (tmp_path / "remotes").exists()


def test_a_clone_of_another_branch_names_the_only_remote(tmp_path):
    """The default branch's refusal (#797) of a `git clone -b develop` made
    under `upstream`: `upstream/HEAD` names `main`, which the source has no
    branch of. It is refused by name, `upstream/HEAD` and its way through
    said with `upstream`. On main HEAD's `develop` was read as the default
    branch, and planned."""
    source = cloned_as(tmp_path, UPSTREAM, "-b", "develop")

    result, plan = planned(tmp_path, source, "--org", ORG)

    assert result.returncode == 2, result.stdout + result.stderr
    assert ("REFUSED source-default-branch-not-local: the source's "
            "`upstream/HEAD` names `main`, the default branch its remote "
            "`upstream` had when it was last asked, and the source has no "
            "branch `main` of its own (its branches: `develop`)") in \
        result.stderr, result.stderr
    assert "`git branch main upstream/main`, run in the source; where " \
        "`upstream` may have changed its default branch since, run `git " \
        "remote set-head upstream --auto` first." in result.stderr
    assert not plan.exists()


def test_check_asks_the_split_branch_of_the_only_remotes_branches(tmp_path):
    """`check` asks for the split branch in the assembly repository, as the
    source's remote last fetched it, where that is the source's own
    repository. `upstream` has a branch `adopt`, which git cannot hold
    beside `adopt/three-repo-shape`. On main `upstream`'s branches were not
    read, and `check` said `plan ok`; it is found now, named as `upstream`
    last fetched it, with the fetch that prunes it from `upstream`."""
    source = cloned_as(tmp_path, UPSTREAM)
    git("update-ref", "refs/remotes/upstream/adopt", "HEAD", cwd=source)
    _, plan = planned(tmp_path, source, "--org", ORG)

    checked = check(plan)

    assert checked.returncode == 1, checked.stdout + checked.stderr
    said = " ".join(checked.stderr.split())
    assert (f"`{ORG}/{PROJECT}` on GitHub, as the source's remote `upstream` "
            "last fetched it,") in said, said
    assert ("A branch named as the source's remote `upstream` last fetched it "
            "leaves `check`'s findings once `git fetch --prune upstream` in "
            "the source finds it gone there.") in said, said


@pytest.mark.parametrize("url, said", [
    ("/srv/clones/Thing.git", None),
    ("https://github.com/-evil/Thing.git", "-evil"),
], ids=["path", "refused-org"])
def test_the_only_remote_is_named_where_origin_was(tmp_path, url, said):
    """Every word that named `origin` names the remote read in its place:
    a path names no organisation (`adopt-no-org`), and an organisation
    `checked_value` refuses is named by where it came from (#427)."""
    source = cloned_as(tmp_path, UPSTREAM)
    git("remote", "set-url", UPSTREAM, url, cwd=source)

    result, _ = planned(tmp_path, source)

    assert result.returncode == 2, result.stdout + result.stderr
    if said is None:
        assert ("REFUSED adopt-no-org: the source's remote `upstream` names "
                "no organisation this tool can read: it has none,") in \
            result.stderr, result.stderr
        result, _ = planned(tmp_path, source, "--org", ORG, name="org")
        assert result.returncode == 0, result.stdout + result.stderr
        assert ("NOTE the source's remote `upstream` is the path "
                f"`{url}`, which names no repository on GitHub") in \
            result.stdout, result.stdout
    else:
        assert ("--org (not given, so the organisation of the source's "
                f"remote `upstream`) is '{said}'") in result.stderr, \
            result.stderr


@pytest.mark.parametrize("change, why", [
    (("remote", "set-url", UPSTREAM, "/srv/clones/Thing.git"),
     "its remote `upstream` names no repository"),
    (("remote", "add", "fork", FORK_URL),
     "it has no remote `origin`, and which of its 2 others it is a clone of "
     "is not guessed: `fork`, `upstream`"),
], ids=["path", "second-remote"])
def test_a_plan_whose_source_names_none_now_says_why(tmp_path, change, why):
    """A plan made while `upstream` named the source's repository, edited
    to another organisation, of a source that names none now: `check` holds
    the plan to its own record and says why the source names none, by the
    remote it read or the remotes passed over (#716)."""
    source = cloned_as(tmp_path, UPSTREAM)
    result, plan = planned(tmp_path, source)
    assert result.returncode == 0, result.stdout + result.stderr
    text = plan.read_text(encoding="utf-8")
    assert f"\norg: {ORG}\n" in text, text
    with plan.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.replace(f"\norg: {ORG}\n", "\norg: other\n", 1))
    git(*change, cwd=source)

    checked = check(plan)

    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert (f"and the plan records the source as {ORG}/{PROJECT} ({why}): "
            "an in-place adoption keeps the source's own name") in \
        checked.stderr, checked.stderr


# --- (c): a source with `origin` reads as it did ----------------------------

def test_a_source_with_origin_and_another_remote_reads_origin(tmp_path):
    """The issue's third row. A source with `origin` and a second remote
    `fork`, fetched, its HEAD on a branch that tracks `fork` -- the remote
    `git ls-remote --get-url` names -- reads every fact from `origin`, as on
    main: the organisation, `origin/HEAD`'s `main`, and `origin`'s
    branches, so `forkonly` is no branch of it."""
    source = cloned_as(tmp_path, "origin")
    with_fork(tmp_path, source, track=True)

    result, plan = planned(tmp_path, source, "--tracking-branch", "forkonly")

    assert result.returncode == 0, result.stdout + result.stderr
    written = load_yaml(plan)
    assert written["org"] == ORG, written
    assert written["source"]["default_branch"] == "main", written["source"]
    assert f"{source} (origin: {ORG}/{PROJECT}) @ " in result.stdout
    assert ("NOTE the tracking branch is `forkonly`, which is no branch of "
            "the source's remote `origin` (its branches: `develop`, `main`; "
            "the source's default branch is `main`).") in result.stdout, \
        result.stdout


def test_a_legacy_origin_is_read_beside_another_remote(tmp_path):
    """An `origin` kept as a file in `.git/branches`, which `git remote`
    does not list and `git remote get-url origin` reads, beside one remote
    `fork` in the config: `origin` is read, as on main, and `fork` is
    not."""
    source = make_source_repo(tmp_path / PROJECT, tree=TREE, edits=())
    (source / ".git" / "branches").mkdir(exist_ok=True)
    (source / ".git" / "branches" / "origin").write_text(
        f"{GITHUB_URL}\n", encoding="utf-8")
    git("remote", "add", "fork", FORK_URL, cwd=source)

    result, plan = planned(tmp_path, source)

    assert result.returncode == 0, result.stdout + result.stderr
    assert load_yaml(plan)["org"] == ORG
    assert f"{source} (origin: {ORG}/{PROJECT}) @ " in result.stdout


# --- (d): several remotes and no `origin` are not guessed among --------------

def test_several_remotes_and_no_origin_are_named_and_not_guessed(tmp_path):
    """Two remotes, `upstream` and `fork`, and no `origin`. Neither is read:
    `plan` with no `--org` refuses `adopt-no-org` naming both, and with
    `--org` the source is read as one with no remote, HEAD's `feature` its
    default branch, and a branch only a remote has is found naming both.
    On main `adopt-no-org` said only "the source's `origin`... it has
    none"."""
    source = cloned_as(tmp_path, UPSTREAM)
    with_fork(tmp_path, source)
    git("switch", "-q", "-c", "feature", cwd=source)
    passed = ("it has no remote `origin`, and which of its 2 others it is a "
              "clone of is not guessed: `fork`, `upstream`")

    result, _ = planned(tmp_path, source)
    assert result.returncode == 2, result.stdout + result.stderr
    assert ("REFUSED adopt-no-org: the source names no organisation this "
            f"tool can read: {passed}\n") in result.stderr, result.stderr
    assert "(`git remote rename <name> origin`)" in result.stderr

    result, plan = planned(tmp_path, source, "--org", ORG,
                           "--tracking-branch", "develop", name="org")
    assert result.returncode == 0, result.stdout + result.stderr
    assert load_yaml(plan)["source"]["default_branch"] == "feature"
    found = ("is `develop`, which is no branch of the source (its branches: "
             "`feature`, `main`; the source's default branch is `feature`; "
             f"{passed}).")
    assert f"NOTE the tracking branch {found}" in result.stdout, result.stdout
    checked = check(plan)
    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert f"FINDING {MISSING}: `tracking_branch` {found}" in checked.stderr


def test_an_only_remote_named_outside_printable_ascii_is_not_read(tmp_path):
    """A remote whose name is not printable ASCII goes into every way
    through as a command line, so it is not read in `origin`'s place, and
    `adopt-no-org` says why, naming it."""
    source = cloned_as(tmp_path, "Ürsprung")

    result, _ = planned(tmp_path, source)

    assert result.returncode == 2, result.stdout + result.stderr
    assert ("REFUSED adopt-no-org: the source names no organisation this "
            "tool can read: it has no remote `origin`, and its one remote, "
            "`Ürsprung`, is not read in that one's place, as its name "
            "is not printable ASCII") in result.stderr, result.stderr
