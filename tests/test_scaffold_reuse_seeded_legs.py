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
but the one test of a reused leg's GitHub visibility, which runs against a
fake `gh` on `PATH`, with `--no-push`. The ruleset is the `pre-receive` hook
`test_ruleset_hint_tracking_branch.py` builds, and an empty `RULESET_REFUSES`
is the operator holding the bypass right.
"""

from __future__ import annotations

import os
import stat
import subprocess
import textwrap
from pathlib import Path

import pytest

from conftest import ORG, PROJECT, SCAFFOLD, WINDOWS_SKIP, git, rmtree, run_script
from test_ruleset_hint_tracking_branch import refusing, template  # noqa: F401

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
    assert_finished(tmp_path, result)
    for leg in LEGS:
        assert tip(tmp_path, leg) == seeds[leg], "a reused leg is never rewritten"
        pin = git("show", f"main:contracts/{leg}-pin.yaml",
                  cwd=bare(tmp_path, "assembly")).stdout
        assert seeds[leg] in pin, pin


def test_a_seed_pushed_to_a_seed_branch_alone_is_taken_too(
        tmp_path, template):  # noqa: F811
    """The exit the hint used to print: the seed pushed to `seed/scaffold`,
    which the ruleset lets through, and `main` absent. Its one commit is the
    seed, so the re-run takes it and creates `main` AT it: a new branch, not
    a rewrite."""
    everything = refusing(template, *REPOS.values())
    assert scaffold(tmp_path, "w1", env=everything).returncode == 2
    pushed = subprocess.run(
        ["git", "-C", str(tmp_path / "w1" / f"{PROJECT}-spec"), "push", "-q",
         str(bare(tmp_path, "spec")), "main:refs/heads/seed/scaffold"],
        capture_output=True, text=True, check=False,
        env={**os.environ, **everything})
    assert pushed.returncode == 0, pushed.stderr
    seed = tip(tmp_path, "spec", "refs/heads/seed/scaffold")
    assert seed and not tip(tmp_path, "spec")
    result = scaffold(tmp_path, "w2", "--reuse-empty-repo",
                      env=refusing(template))
    assert_finished(tmp_path, result)
    assert tip(tmp_path, "spec") == seed


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


def test_a_leg_somebody_else_made_is_refused(tmp_path):
    """One commit, but not a tree this scaffold writes: somebody's
    repository that happens to have the name."""
    work = tmp_path / "theirs"
    git("init", "-q", "-b", "main", str(work), cwd=tmp_path)
    (work / "README.md").write_text("# live\n", encoding="utf-8")
    git("add", "README.md", cwd=work)
    git("commit", "-q", "-m", "live", cwd=work)
    reserve(tmp_path, "spec")
    git("push", "-q", str(bare(tmp_path, "spec")), "main", cwd=work)
    before = {role: tip(tmp_path, role) for role in REPOS}
    result = scaffold(tmp_path, "work", "--reuse-empty-repo")
    assert_refused_as_not_the_seed(tmp_path, result, before)
    assert not bare(tmp_path, "code").exists(), "nothing was created"


# --- a reused leg's visibility (GitHub) -------------------------------------

#: A `gh` that knows three EMPTY repositories, each at the visibility
#: `FAKE_GH_REPOS` gives it (`org/name=VISIBILITY,...`), answers `repo create`
#: and `repo edit` with success, and logs every call.
FAKE_GH = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json
    import os
    import sys

    argv = sys.argv[1:]
    with open(os.environ["FAKE_GH_LOG"], "a", encoding="utf-8") as f:
        f.write(" ".join(argv) + "\\n")
    KNOWN = dict(pair.split("=") for pair in
                 os.environ["FAKE_GH_REPOS"].split(","))

    if argv[:2] == ["repo", "view"]:
        repo = argv[2]
        if repo not in KNOWN:
            print("GraphQL: Could not resolve to a Repository", file=sys.stderr)
            sys.exit(1)
        fields = argv[argv.index("--json") + 1].split(",")
        out = {}
        if "name" in fields:
            out["name"] = repo.rsplit("/", 1)[-1]
        if "visibility" in fields:
            out["visibility"] = KNOWN[repo]
        print(json.dumps(out))
    elif argv[:1] == ["api"] and argv[1].split("/commits")[0][6:] in KNOWN:
        print("[]")
    elif argv[:2] in (["repo", "create"], ["repo", "edit"]):
        pass
    else:
        print(f"fake gh: unhandled {argv!r}", file=sys.stderr)
        sys.exit(1)
    """)


@WINDOWS_SKIP
def test_a_reused_leg_keeps_its_visibility_and_a_disagreement_is_said(
        tmp_path):
    """A reused leg is not created, so it keeps the visibility the run that
    created it gave it; a run whose visibility disagrees is told so, as
    `_leg_visibility` tells it about a reused root. The shebang `gh` is why
    this is skipped on Windows, which does not run one; what it pins is a
    `gh repo view` read, which is platform-blind."""
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    gh = fakebin / "gh"
    gh.write_text(FAKE_GH, encoding="utf-8")
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    log = tmp_path / "gh.log"
    log.write_text("", encoding="utf-8")
    env = {"PATH": f"{fakebin}{os.pathsep}{os.environ.get('PATH', '')}",
           "FAKE_GH_LOG": str(log),
           "FAKE_GH_REPOS": f"{ORG}/{PROJECT}=PRIVATE,"
                            f"{ORG}/{PROJECT}-spec=PUBLIC,"
                            f"{ORG}/{PROJECT}-code=PRIVATE"}
    result = run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                        "--elected-by", "Test Human", "--reuse-empty-repo",
                        "--no-push", "--work-dir", str(tmp_path / "work"),
                        env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (f"WARNING {ORG}/{PROJECT}-spec is reused and is public on GitHub, "
            "where this run's visibility is private.") in result.stderr
    assert f"{ORG}/{PROJECT}-code is reused" not in result.stderr, (
        "a reused leg that agrees is not warned about")
    assert "repo create" not in log.read_text(encoding="utf-8"), (
        "a reused repository is never created")
