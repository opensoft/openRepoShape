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
but the tests of GitHub's side, a reused leg's visibility and a leg `gh` sees
that git cannot read (#542), which run against a fake `gh` on `PATH`, with
`--no-push`, and point git's `https://github.com/` at a path or a local
server that refuses it. The ruleset is the `pre-receive` hook
`test_ruleset_hint_tracking_branch.py` builds, and an empty `RULESET_REFUSES`
is the operator holding the bypass right.
"""

from __future__ import annotations

import http.server
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

from conftest import (ORG, PROJECT, PTY_SKIP, SCAFFOLD, WINDOWS_SKIP,
                      appended_to_command_scope, git, rmtree,
                      run_in_a_terminal, run_script)
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


def theirs_at_one_commit(tmp_path) -> None:
    """The spec leg's bare repository, holding ONE commit that is not a tree
    this scaffold writes: somebody's repository that has the name."""
    work = tmp_path / "theirs"
    git("init", "-q", "-b", "main", str(work), cwd=tmp_path)
    (work / "README.md").write_text("# live\n", encoding="utf-8")
    git("add", "README.md", cwd=work)
    git("commit", "-q", "-m", "live", cwd=work)
    reserve(tmp_path, "spec")
    git("push", "-q", str(bare(tmp_path, "spec")), "main", cwd=work)


def test_a_leg_somebody_else_made_is_refused(tmp_path):
    """One commit, but not a tree this scaffold writes: somebody's
    repository that happens to have the name."""
    theirs_at_one_commit(tmp_path)
    before = {role: tip(tmp_path, role) for role in REPOS}
    result = scaffold(tmp_path, "work", "--reuse-empty-repo")
    assert_refused_as_not_the_seed(tmp_path, result, before)
    assert not bare(tmp_path, "code").exists(), "nothing was created"


# --- a reused leg's visibility (GitHub) -------------------------------------

#: A `gh` that knows the repositories `FAKE_GH_REPOS` names
#: (`org/name=VISIBILITY,...`), each at that visibility and EMPTY unless
#: `FAKE_GH_FULL` names it too (`org/name,...`), when its commit listing has
#: one commit; it answers `repo create` and `repo edit` with success, answers
#: `api orgs/<org>` with `FAKE_GH_PLAN` when that is set (the Free-plan hint
#: asks it for `.plan.name`), and with `FAKE_GH_PLAN_ERROR` on stderr and
#: exit 1 when that is, answers `repo view` of each repository that
#: `FAKE_GH_VIEW_ERRORS` (JSON, `{"org/name": "stderr text"}`) names with that
#: text and exit 1, known or not (a 401, where an unknown one is not-found),
#: answers only `repo view --json visibility` of each that
#: `FAKE_GH_VISIBILITY_ERRORS` names so (an `HTTP 502` after `--json name`
#: found it), and logs every call.
FAKE_GH = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json
    import os
    import sys

    argv = sys.argv[1:]
    with open(os.environ["FAKE_GH_LOG"], "a", encoding="utf-8") as f:
        f.write(" ".join(argv) + "\\n")
    KNOWN = dict(pair.split("=") for pair in
                 os.environ["FAKE_GH_REPOS"].split(",") if pair)
    FULL = os.environ.get("FAKE_GH_FULL", "").split(",")
    ERRORS = json.loads(os.environ.get("FAKE_GH_VIEW_ERRORS", "{}"))
    UNSEEN = json.loads(os.environ.get("FAKE_GH_VISIBILITY_ERRORS", "{}"))

    if argv[:2] == ["repo", "view"]:
        repo = argv[2]
        fields = (argv[argv.index("--json") + 1].split(",")
                  if "--json" in argv else [])
        if repo in UNSEEN and "visibility" in fields:
            ERRORS[repo] = UNSEEN[repo]
        if repo in ERRORS:
            print(ERRORS[repo], file=sys.stderr)
            sys.exit(1)
        if repo not in KNOWN:
            print("GraphQL: Could not resolve to a Repository", file=sys.stderr)
            sys.exit(1)
        out = {}
        if "name" in fields:
            out["name"] = repo.rsplit("/", 1)[-1]
        if "visibility" in fields:
            out["visibility"] = KNOWN[repo]
        print(json.dumps(out))
    elif (argv[:1] == ["api"] and argv[1].startswith("orgs/")
          and "FAKE_GH_PLAN_ERROR" in os.environ):
        print(os.environ["FAKE_GH_PLAN_ERROR"], file=sys.stderr)
        sys.exit(1)
    elif (argv[:1] == ["api"] and argv[1].startswith("orgs/")
          and "FAKE_GH_PLAN" in os.environ):
        print(os.environ["FAKE_GH_PLAN"])
    elif argv[:1] == ["api"] and argv[1].split("/commits")[0][6:] in KNOWN:
        print('[{"sha": "0"}]' if argv[1].split("/commits")[0][6:] in FULL
              else "[]")
    elif argv[:2] in (["repo", "create"], ["repo", "edit"]):
        pass
    else:
        print(f"fake gh: unhandled {argv!r}", file=sys.stderr)
        sys.exit(1)
    """)


def fake_gh(tmp_path, repos: dict, full=(), plan: str | None = None,
            view_errors: dict | None = None, *,
            visibility_errors: dict | None = None,
            plan_error: str | None = None) -> tuple[dict, Path]:
    """`FAKE_GH` first on PATH, knowing `repos` (`{name: VISIBILITY}`, each
    under `ORG`) and holding commits in each of `full`, naming `plan` as the
    organisation's GitHub plan when one is given, or failing that question
    with the text `plan_error`, and failing `repo view` of each name in
    `view_errors` (`{name: stderr text}`, each under `ORG`) with that text,
    or only its `--json visibility` for each name in `visibility_errors`:
    the environment for the run, and the log of every call. Nothing it
    answers reaches GitHub."""
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    gh = fakebin / "gh"
    gh.write_text(FAKE_GH, encoding="utf-8")
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    log = tmp_path / "gh.log"
    log.write_text("", encoding="utf-8")
    env = {"PATH": f"{fakebin}{os.pathsep}{os.environ.get('PATH', '')}",
           "FAKE_GH_LOG": str(log),
           "FAKE_GH_REPOS": ",".join(f"{ORG}/{name}={visibility}"
                                     for name, visibility in repos.items()),
           "FAKE_GH_FULL": ",".join(f"{ORG}/{name}" for name in full)}
    if plan is not None:
        env["FAKE_GH_PLAN"] = plan
    if plan_error is not None:
        env["FAKE_GH_PLAN_ERROR"] = plan_error
    for key, errors in (("FAKE_GH_VIEW_ERRORS", view_errors),
                        ("FAKE_GH_VISIBILITY_ERRORS", visibility_errors)):
        if errors:
            env[key] = json.dumps(
                {f"{ORG}/{name}": text for name, text in errors.items()})
    return env, log


def on_github(tmp_path, *extra: str, env: dict, cwd: Path | None = None):
    """The scaffold in its GitHub mode, against `fake_gh`, pushing nothing."""
    return run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                      "--elected-by", "Test Human", "--no-push",
                      "--work-dir", str(tmp_path / "work"), *extra,
                      cwd=cwd, env=env)


@WINDOWS_SKIP
def test_a_reused_leg_keeps_its_visibility_and_a_disagreement_is_said(
        tmp_path):
    """A reused leg is not created, so it keeps the visibility the run that
    created it gave it; a run whose visibility disagrees is told so, as
    `_leg_visibility` tells it about a reused root. The shebang `gh` is why
    this is skipped on Windows, which does not run one; what it pins is a
    `gh repo view` read, which is platform-blind."""
    env, log = fake_gh(tmp_path, {PROJECT: "PRIVATE",
                                  f"{PROJECT}-spec": "PUBLIC",
                                  f"{PROJECT}-code": "PRIVATE"})
    result = on_github(tmp_path, "--reuse-empty-repo", env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (f"WARNING {ORG}/{PROJECT}-spec is reused and is public on GitHub, "
            "where this run's visibility is private.") in result.stderr
    assert f"{ORG}/{PROJECT}-code is reused" not in result.stderr, (
        "a reused leg that agrees is not warned about")
    assert "repo create" not in log.read_text(encoding="utf-8"), (
        "a reused repository is never created")


# --- the reuse re-run's visibility text (#542) ------------------------------

SPEC_REPO, CODE_REPO = f"{ORG}/{PROJECT}-spec", f"{ORG}/{PROJECT}-code"
#: What the private-leg NOTE says after its subject, for one leg and for two.
READ_IT = (f": give {ORG}/{PROJECT} a way to read it — a GitHub App "
           "(SHAPE_LEGS_APP_ID + SHAPE_LEGS_APP_PRIVATE_KEY, preferred) or a "
           "SHAPE_LEGS_TOKEN PAT (contents:read on that leg, fallback) — or "
           "the `validate` check cannot check it out.")
READ_THEM = (f": give {ORG}/{PROJECT} a way to read them — a GitHub App "
             "(SHAPE_LEGS_APP_ID + SHAPE_LEGS_APP_PRIVATE_KEY, preferred) or a "
             "SHAPE_LEGS_TOKEN PAT (contents:read on the legs, fallback) — or "
             "the `validate` check cannot check them out.")
INHERITED = (f"NOTE {ORG}/{PROJECT} is already private on GitHub; a leg this "
             "run creates inherits that visibility, and a leg it reuses keeps "
             "its own (pass --visibility to choose one explicitly).")
DISAGREES = (f"WARNING --visibility public disagrees with the reused "
             f"{ORG}/{PROJECT}, which is private on GitHub. A leg this run "
             "creates is created public because that is what you asked for, "
             "not because it is what the assembly root already is; a leg it "
             "reuses keeps its own.")


@WINDOWS_SKIP
@pytest.mark.parametrize("repos,flags,said", [
    # A private run that reuses a PUBLIC spec leg: on main the NOTE called
    # both legs private, beside the WARNING that the spec leg is public.
    ({PROJECT: "PRIVATE", f"{PROJECT}-spec": "PUBLIC",
      f"{PROJECT}-code": "PRIVATE"}, (),
     [INHERITED, f"NOTE {CODE_REPO} is private{READ_IT}"]),
    # A public run that reuses a private and an internal leg: on main it
    # printed no NOTE at all, and its WARNING spoke of "the two new legs".
    ({PROJECT: "PRIVATE", f"{PROJECT}-spec": "PRIVATE",
      f"{PROJECT}-code": "INTERNAL"}, ("--visibility", "public"),
     [DISAGREES,
      f"NOTE {SPEC_REPO} is private and {CODE_REPO} is internal{READ_THEM}"]),
    # One leg created at the run's public, one reused private.
    ({PROJECT: "PUBLIC", f"{PROJECT}-code": "PRIVATE"},
     ("--visibility", "public"), [f"NOTE {CODE_REPO} is private{READ_IT}"]),
    # Both legs private: the sentence the note has always printed.
    ({PROJECT: "PRIVATE", f"{PROJECT}-spec": "PRIVATE",
      f"{PROJECT}-code": "PRIVATE"}, (),
     [f"NOTE {SPEC_REPO} and {CODE_REPO} are private{READ_THEM}"]),
    # Both legs public: no note.
    ({PROJECT: "PUBLIC", f"{PROJECT}-spec": "PUBLIC",
      f"{PROJECT}-code": "PUBLIC"}, ("--visibility", "public"), []),
], ids=["reused-public-leg-under-private", "reused-closed-legs-under-public",
        "created-public-reused-private", "both-private", "both-public"])
def test_the_visibility_text_follows_each_leg_as_it_stands(
        tmp_path, repos, flags, said):
    """The reuse re-run's visibility lines (#542). `_private_leg_note` names
    each leg that is private or internal at the visibility it has, a reused
    one's read from GitHub, and no other; `_leg_visibility`'s two lines,
    printed before anything is asked of the legs, no longer call them "the
    two new legs", which a re-run that reuses one or both is not."""
    env, _log = fake_gh(tmp_path, repos)
    result = on_github(tmp_path, "--reuse-empty-repo", *flags, env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    printed = result.stdout + result.stderr
    for line in said:
        assert line in printed, printed
    notes = [line for line in result.stdout.splitlines()
             if line.startswith("NOTE ") and "a way to read" in line]
    assert len(notes) == len([line for line in said if "a way to read" in line
                              ]), notes
    assert "two new legs" not in printed


#: The Free-plan hint's subject is the root, where the `validate` workflow
#: runs. On the Free plan an organisation secret reaches only a public
#: repository, so the hint is true when the root is private or internal and
#: false when it is public, whatever a leg is. `None` is no hint; otherwise
#: the repository it names as the reason, as `FREE_PLAN_HINT` puts it before
#: " private, so": the root (#602), where it named the closed legs.
ROOT_IS = f"{ORG}/{PROJECT} is"
#: What the hint named as its reason before #602, which no row may print.
LEG_SUBJECTS = (f"{SPEC_REPO} is", f"{CODE_REPO} is",
                f"{SPEC_REPO} and {CODE_REPO} are")


@WINDOWS_SKIP
@pytest.mark.parametrize("repos,flags,plan,named", [
    # A public run that creates the root and reuses a private code leg: the
    # root is public, so its workflow is given the organisation's secrets.
    ({f"{PROJECT}-code": "PRIVATE"}, ("--visibility", "public"), "free", None),
    # The same with the root reused, public on GitHub.
    ({PROJECT: "PUBLIC", f"{PROJECT}-code": "PRIVATE"},
     ("--visibility", "public"), "free", None),
    # A public root reused with no flag: the run, and the leg it creates,
    # inherit public, and both reused legs are private.
    ({PROJECT: "PUBLIC", f"{PROJECT}-spec": "PRIVATE",
      f"{PROJECT}-code": "PRIVATE"}, (), "free", None),
    # The run's flag is not the root: `--visibility private` over a root that
    # is public on GitHub, and the root is what has the workflow.
    ({PROJECT: "PUBLIC", f"{PROJECT}-spec": "PRIVATE",
      f"{PROJECT}-code": "PRIVATE"}, ("--visibility", "private"), "free",
     None),
    # And the other way: a public run over a root that is private on GitHub.
    ({PROJECT: "PRIVATE", f"{PROJECT}-code": "PRIVATE"},
     ("--visibility", "public"), "free", ROOT_IS),
    # An internal root is closed too, and its run creates the spec leg
    # internal.
    ({PROJECT: "INTERNAL", f"{PROJECT}-code": "PRIVATE"}, (), "free",
     ROOT_IS),
    # Controls: a private root with both legs private, reused and created
    # new, gets the hint as before, with the root as its subject (#602 moved
    # only that); and a paid plan says nothing.
    ({PROJECT: "PRIVATE", f"{PROJECT}-spec": "PRIVATE",
      f"{PROJECT}-code": "PRIVATE"}, (), "free", ROOT_IS),
    ({}, (), "free", ROOT_IS),
    ({PROJECT: "PRIVATE", f"{PROJECT}-spec": "PRIVATE",
      f"{PROJECT}-code": "PRIVATE"}, (), "team", None),
], ids=["public-run-new-root", "public-root-reused",
        "public-root-inherited", "private-flag-over-public-root",
        "public-flag-over-private-root", "internal-root",
        "private-root-reused-legs", "private-run-new-repositories",
        "paid-plan"])
def test_the_free_plan_hint_goes_by_the_root_as_it_stands(
        tmp_path, repos, flags, plan, named):
    """#542. `_private_leg_note` printed the Free-plan hint whenever a leg was
    private or internal, so a public root that reused a private leg was told
    its organisation secrets "resolve to EMPTY inside the workflow", which on
    the Free plan holds only of a private one. The per-leg NOTE is printed
    in every case a leg is closed, since a public root still needs a
    credential to read a private leg; the hint only when the root, as it
    stands, is private or internal: GitHub's for a reused root, else the
    run's. #602: and it names the root as the repository that is private,
    where it named the closed legs, which are not why the secrets resolve to
    EMPTY."""
    env, _log = fake_gh(tmp_path, repos, plan=plan)
    result = on_github(tmp_path, "--reuse-empty-repo", *flags, env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    printed = result.stdout + result.stderr
    assert "a way to read" in printed, printed
    if named is None:
        assert "resolve to EMPTY" not in printed, printed
    else:
        assert f"NOTE {ORG} is on the GitHub FREE plan" in printed, printed
        assert f"{named} private, so org-level" in printed, printed
        assert printed.count("resolve to EMPTY") == 1, printed
    for subject in LEG_SUBJECTS:
        assert f"{subject} private, so" not in printed, printed


# --- a leg that gh sees and git cannot read (#542) --------------------------

def test_the_two_git_commands_that_read_a_leg_ask_no_terminal(
        tmp_path, monkeypatch):
    """`only_commit`'s `git ls-remote` and `git fetch`, the two commands
    that reach the leg, run under `PROBE_ENV`, `GIT_TERMINAL_PROMPT=0`
    (#542). Asked in-process of a leg on disk, so it runs on every platform,
    Windows included, where the terminal test below cannot."""
    spec = importlib.util.spec_from_file_location("scaffold_for_probe_env",
                                                  SCAFFOLD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.PROBE_ENV == {"GIT_TERMINAL_PROMPT": "0"}
    asked = []
    real = module.run

    def recording(args, cwd=None, capture=True, env=None):
        asked.append((args[1], env))
        return real(args, cwd=cwd, capture=capture, env=env)

    monkeypatch.setattr(module, "run", recording)
    theirs_at_one_commit(tmp_path)
    held = module.only_commit(str(bare(tmp_path, "spec")), tmp_path / "probe")
    assert held is not None, asked
    assert held[0] == tip(tmp_path, "spec"), asked
    assert {verb: env for verb, env in asked
            if verb in ("ls-remote", "fetch")} == {
        "ls-remote": module.PROBE_ENV, "fetch": module.PROBE_ENV}, asked


def git_reads_github_from(base: str) -> dict:
    """What makes git read `https://github.com/<ORG>/` at `base` instead,
    with no credential helper and no askpass program, so git answers a leg
    as it would with no login of its own. The prefix is longer than an
    operator's own `https://github.com/` rewrite, so it wins over one. The two
    entries are appended, when this is called, to the command scope the
    environment holds."""
    return {**appended_to_command_scope(
                os.environ, [(f"url.{base}.insteadOf",
                              f"https://github.com/{ORG}/"),
                             ("credential.helper", "")]),
            "GIT_ASKPASS": ""}


#: The legs `gh` sees: the spec leg, holding commits. The root and the code
#: leg do not exist, so nothing but the spec leg is asked of git.
SEEN_SPEC = {f"{PROJECT}-spec": "PRIVATE"}
UNREAD = (f"REFUSED scaffold-remote-exists: {SPEC_REPO} already exists on "
          "GitHub and has commits\nRemediation: git could not read it "
          f"(`git ls-remote https://github.com/{SPEC_REPO}.git` exited 128: "
          "fatal: ")
UNREAD_EXIT = ("so whether its one commit is the seed this scaffold pushes "
               "cannot be asked. Let git read it (on GitHub, `gh auth "
               "setup-git` gives git the login `gh` has), then re-run: with "
               "--reuse-empty-repo a leg whose one commit is that seed is "
               "reused, and a leg holding anything else is still refused. "
               "There is no --force.")


@WINDOWS_SKIP
@pytest.mark.parametrize("flags", [(), ("--reuse-empty-repo",)],
                         ids=["without-the-flag", "with-the-flag"])
def test_a_leg_git_cannot_read_is_refused_as_existing_not_as_a_failure(
        tmp_path, flags):
    """On main through bfed143 `_held_seed` let `only_commit`'s
    `CommandFailed` through, so a leg `gh` sees with commits and git cannot
    read was `REFUSED a git or gh command failed`, the generic line; with
    the flag and without it, since the seed is asked either way. Now it is
    `scaffold-remote-exists`, saying git could not read it, before anything
    is created."""
    env, log = fake_gh(tmp_path, SEEN_SPEC, full=[f"{PROJECT}-spec"])
    env.update(git_reads_github_from(f"{tmp_path / 'unreadable'}/"))
    result = on_github(tmp_path, *flags, env=env, cwd=tmp_path)
    assert result.returncode == 2, result.stderr + result.stdout
    assert "a git or gh command failed" not in result.stderr
    assert UNREAD in result.stderr, result.stderr
    assert "does not appear to be a git repository), " + UNREAD_EXIT in (
        result.stderr), result.stderr
    assert "repo create" not in log.read_text(encoding="utf-8"), (
        "nothing was created")


class _AsksForALogin(http.server.BaseHTTPRequestHandler):
    """A git host that answers every request 401, as GitHub answers git for
    a private repository it is given no login for."""

    def do_GET(self):  # noqa: N802 - the name `BaseHTTPRequestHandler` calls
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="w542"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_POST = do_GET

    def log_message(self, *args):  # the test reads the screen, not this
        pass


@WINDOWS_SKIP
@PTY_SKIP
def test_a_leg_git_would_ask_a_login_for_does_not_wait_on_the_terminal(
        tmp_path):
    """`only_commit` runs git with `GIT_TERMINAL_PROMPT=0` (#542). Typed in a
    terminal, a re-run whose leg git has no login for stopped at git's
    `Username for ...:` prompt before a word about the leg; on main through
    bfed143 this run waits there until the harness kills it. Now git's ask
    is a failure, and the run is refused as `scaffold-remote-exists`."""
    env, _log = fake_gh(tmp_path, SEEN_SPEC, full=[f"{PROJECT}-spec"])
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _AsksForALogin)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        port = server.server_address[1]
        status, screen, _typed = run_in_a_terminal(
            [sys.executable, str(SCAFFOLD), "--org", ORG, "--project",
             PROJECT, "--elected-by", "Test Human", "--no-push",
             "--reuse-empty-repo", "--work-dir", str(tmp_path / "work")],
            cwd=tmp_path, timeout=90,
            env={**os.environ, **env, "LANES_LANE": "",
                 **git_reads_github_from(f"http://127.0.0.1:{port}/{ORG}/")})
    finally:
        server.shutdown()
        server.server_close()
    # git's prompt starts a line; its refusal says `could not read Username
    # for '...': terminal prompts disabled` inside the remedy's line.
    assert not re.search(r"(?m)^Username for ", screen), screen
    assert status == 2, screen
    assert f"REFUSED scaffold-remote-exists: {SPEC_REPO} already exists" in (
        screen), screen
    assert "terminal prompts disabled" in screen, screen
