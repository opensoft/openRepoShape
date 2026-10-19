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

EVERY GIT COMMAND THAT REACHES A REMOTE runs under one prompt rule (#915):
`only_commit`'s two, `_take_held_seed`'s fetch and each push, a first run's
and a re-run's, the pushes asked in a terminal against a local server that
asks for a login. A push git has no login for is refused naming how to give
it one, then the re-run. And a leg git reaches over ssh, through an
operator's `insteadOf` rewrite, is refused with ssh's reason and a remedy for
an ssh key, in the locale git runs in and in one that translates git; the ssh
is a stand-in that refuses every key, so nothing leaves this machine.

A PUSH THE HOST REFUSED A LOGIN FOR names the fix as well (#993): a login a
credential helper holds that the local server refuses, a first run's and a
re-run's, in a terminal, and a key the stand-in ssh refuses where an
`insteadOf` or a `pushInsteadOf` rule sends the push over ssh, each in git's
own locale and in one that translates git.
"""

from __future__ import annotations

import http.server
import importlib.util
import json
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

from conftest import (ORG, PROJECT, PTY_SKIP, SCAFFOLD, WINDOWS_SKIP,
                      appended_to_command_scope, git,
                      load_without_bytecode, rmtree,
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
    assert "could not get a login" not in again.stderr, (
        "a push a ruleset refused is not one git had no login for (#915)")
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
    that reach the leg, run under `PROBE_ENV`: `GIT_TERMINAL_PROMPT=0`
    (#542), the prompt rule `REMOTE_ENV` every command that reaches a remote
    runs under, and `LC_ALL=C`, so `_unread_because` reads git's words
    untranslated (#915). Asked in-process of a leg on disk, so it runs on
    every platform, Windows included, where the terminal test below
    cannot."""
    spec = importlib.util.spec_from_file_location("scaffold_for_probe_env",
                                                  SCAFFOLD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.REMOTE_ENV == {"GIT_TERMINAL_PROMPT": "0"}
    assert module.PROBE_ENV == {"GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
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


#: The verbs of the git commands this scaffold sends to a remote.
REACHES_A_REMOTE = ("ls-remote", "fetch", "push")


def test_every_git_command_that_reaches_a_remote_runs_under_the_rule(
        tmp_path, monkeypatch, capsys, template):
    """#915. `PROBE_ENV` covered `only_commit`'s two commands alone, and a
    reuse re-run's other three ran with git's terminal prompt on:
    `_take_held_seed`'s fetch, each leg's push and the root's. A re-run over
    legs that hold the seed, in-process, records each git command that
    reaches a remote, in order, with the environment it was given: the
    probe's two for each leg under `PROBE_ENV`, then each leg's fetch and
    push, and the root's push, the fetches under `REMOTE_ENV` and the pushes
    under `PUSH_ENV`, which also keeps git's words untranslated for
    `_refused_push` to read (#993). Asked of bare repositories on disk, so it
    runs on every platform."""
    seeds = refused_at_the_root(tmp_path, template)
    module = load_without_bytecode(SCAFFOLD, "scaffold_for_remote_env")
    assert module.PUSH_ENV == {"GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
    asked = []
    real = module.run

    def recording(args, cwd=None, capture=True, env=None):
        if args[1] in REACHES_A_REMOTE:
            asked.append((" ".join(args[1:2] + [arg for arg in args
                                                 if arg == "--depth=1"]),
                          env))
        return real(args, cwd=cwd, capture=capture, env=env)

    monkeypatch.setattr(module, "run", recording)
    code = module.main(["--org", ORG, "--project", PROJECT,
                        "--elected-by", "Test Human",
                        "--elected-on", "2026-09-02",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"),
                        "--reuse-empty-repo"])
    out, err = capsys.readouterr()
    assert code == 0, err + out
    assert {leg: tip(tmp_path, leg) for leg in LEGS} == seeds
    assert commits(tmp_path, "assembly") == 1
    probe, rule, push = module.PROBE_ENV, module.REMOTE_ENV, module.PUSH_ENV
    assert asked == [("ls-remote", probe), ("fetch --depth=1", probe),
                     ("ls-remote", probe), ("fetch --depth=1", probe),
                     ("fetch", rule), ("push", push),
                     ("fetch", rule), ("push", push),
                     ("push", push)], asked


def git_reads_github_from(base: str, helper: str = "") -> dict:
    """What makes git read `https://github.com/<ORG>/` at `base` instead,
    with no askpass program and no credential helper but `helper`, so git
    answers a leg as it would with no login of its own. The prefix is longer
    than an operator's own `https://github.com/` rewrite, so it wins over
    one. An empty `credential.helper` empties the list a config before it
    made, and `helper` is the one after it. The entries are appended, when
    this is called, to the command scope the environment holds."""
    return {**appended_to_command_scope(
                os.environ, [(f"url.{base}.insteadOf",
                              f"https://github.com/{ORG}/"),
                             ("credential.helper", ""),
                             *([("credential.helper", helper)] if helper
                               else [])]),
            "GIT_ASKPASS": ""}


#: The legs `gh` sees: the spec leg, holding commits. The root and the code
#: leg do not exist, so nothing but the spec leg is asked of git.
SEEN_SPEC = {f"{PROJECT}-spec": "PRIVATE"}
UNREAD = (f"REFUSED scaffold-remote-exists: {SPEC_REPO} already exists on "
          "GitHub and has commits\nRemediation: git could not read it "
          f"(`git ls-remote https://github.com/{SPEC_REPO}.git` exited 128: "
          "fatal: ")
#: The ssh key's clause, as each remedy for git's access names it (#915):
#: `ssh -T` against the user, host and port the rule names, with what
#: `GIT_SSH_COMMAND` or `core.sshCommand` adds, which `ssh -T git@github.com`
#: was not for a `Host` alias, `ssh.github.com` on port 443 or a key given by
#: `-i` (RV971), and which `ssh -T -p 443 ssh.github.com` without the user
#: `git` was not either: GitHub refuses it whatever the key (RV971, round 2).
SSH_KEY_CHECK = ("`ssh -T` against the user, host and port your rule names, "
                 "with anything your `GIT_SSH_COMMAND` or `core.sshCommand` "
                 "adds, says whether GitHub takes yours")
SSH_KEY = ("where a `url.<base>.insteadOf` rule in your git config sends "
           "`https://github.com/` over ssh, git logs in with an ssh key "
           f"instead, and {SSH_KEY_CHECK}")
UNREAD_EXIT = ("so whether its one commit is the seed this scaffold pushes "
               "cannot be asked. Let git read it (on GitHub, `gh auth "
               f"setup-git` gives git the login `gh` has; {SSH_KEY}), then "
               "re-run: with --reuse-empty-repo a leg whose one commit is "
               "that seed is reused, and a leg holding anything else is "
               "still refused. There is no --force.")


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


def in_a_terminal_asked_for_a_login(tmp_path, env: dict, *flags: str,
                                    helper: str = "", stored: str = "",
                                    said: str = "terminal prompts disabled",
                                    timeout: float = 90) -> tuple:
    """The scaffold in its GitHub mode with `flags`, a first run or, with
    `--reuse-empty-repo` among them, a re-run, typed in a terminal, with
    `env` (a `fake_gh`'s) and git reading `https://github.com/<ORG>/` from a
    local server that answers every request 401, with `helper` as its one
    credential helper or none, or, given `stored`, a `user:token` login, a
    `store` helper holding that login for the server, which refuses it as a
    host refuses a stale token (#993): `(exit status, the screen)`, the
    screen holding `said`, git's words for the refusal. A run that waits at
    git's prompt is killed after `timeout` seconds, which fails the test."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _AsksForALogin)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        port = server.server_address[1]
        if stored:
            store = tmp_path / "stored-login"
            store.write_text(f"http://{stored}@127.0.0.1:{port}\n",
                             encoding="utf-8")
            helper = f'store --file="{store}"'
        status, screen, _typed = run_in_a_terminal(
            [sys.executable, str(SCAFFOLD), "--org", ORG, "--project",
             PROJECT, "--elected-by", "Test Human", *flags,
             "--work-dir", str(tmp_path / "work")],
            cwd=tmp_path, timeout=timeout,
            env={**os.environ, **env, "LANES_LANE": "",
                 **git_reads_github_from(f"http://127.0.0.1:{port}/{ORG}/",
                                         helper)})
    finally:
        server.shutdown()
        server.server_close()
    # git's prompt starts a line; its refusal says `could not read Username
    # for '...': terminal prompts disabled` inside a line of its own.
    assert not re.search(r"(?m)^Username for ", screen), screen
    assert said in screen, screen
    return status, screen


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
    status, screen = in_a_terminal_asked_for_a_login(
        tmp_path, env, "--reuse-empty-repo", "--no-push")
    assert status == 2, screen
    assert f"REFUSED scaffold-remote-exists: {SPEC_REPO} already exists" in (
        screen), screen


@WINDOWS_SKIP
@PTY_SKIP
def test_a_reuse_re_run_over_empty_legs_does_not_wait_at_its_push(tmp_path):
    """#915. A `--reuse-empty-repo` re-run whose three repositories are all
    empty asks `only_commit` nothing, so its first push, the spec leg's, was
    the first git command to reach GitHub, and it ran with git's terminal
    prompt on: typed in a terminal with no login for the host, it stopped at
    `Username for '...':`, and on main through 01a2b01 this run waits there
    until the harness kills it. Now each push runs under `REMOTE_ENV`, and
    git's ask is a refused push, printed as one with how to give git a login
    and the re-run, this run's own command, before the ruleset hint."""
    env, log = fake_gh(tmp_path, {PROJECT: "PRIVATE",
                                  f"{PROJECT}-spec": "PRIVATE",
                                  f"{PROJECT}-code": "PRIVATE"}, plan="team")
    status, screen = in_a_terminal_asked_for_a_login(
        tmp_path, env, "--reuse-empty-repo", timeout=120)
    assert status == 2, screen
    assert "REFUSED pushing the spec leg. THE EXACT COMMAND WAS:" in screen, (
        screen)
    assert_the_login_is_named(screen, SPEC_REPO, RE_RUN_AS_IT_WAS)
    assert "repo create" not in log.read_text(encoding="utf-8"), (
        "a reused repository is never created")


# --- a push git has no login for (#915) -------------------------------------

#: How `_refused_push` names the fix for a push git had no login for, up to
#: the re-run, with the repository as `@REPO@`. A literal, so the test cannot
#: agree with whatever the code's words become.
NO_LOGIN_REMEDY = (
    "Remediation: git could not get a login for @REPO@: every push this "
    "scaffold makes runs with git's terminal prompt off, so where git would "
    "have asked you for one the push is refused, and a credential helper "
    "with nothing stored for the host answers nothing. Give git a login "
    "first (on GitHub, `gh auth setup-git` gives git the login `gh` has, or "
    "store a token for the host in your credential helper; "
    f"{SSH_KEY}), then re-run ")
#: The re-run it names after a first run: the same command, the flag added.
RE_RUN_WITH_THE_FLAG = (
    "the same command with --reuse-empty-repo added (after `--` through "
    "setup.sh) and a new --work-dir or none: it reuses the repositories this "
    "run left empty, and a leg whose one commit is the seed this scaffold "
    "pushes.")
#: And after a run that was that re-run: the same command again.
RE_RUN_AS_IT_WAS = (
    "the same command with a new --work-dir or none: it reuses the "
    "repositories this run left empty, and a leg whose one commit is the "
    "seed this scaffold pushes.")


#: How it names the fix for a push whose login the host refused (#993): git
#: had one, so "could not get" is not said of it.
LOGIN_REFUSED_REMEDY = (
    "Remediation: the host refused the login git sent for @REPO@: git had "
    "one, from your credential helper for one, and it is wrong, expired or "
    "revoked, so a re-run is refused too until git has one the host takes. "
    "Replace it first (on GitHub, `gh auth setup-git` makes git use the login "
    "`gh` has instead, or store a new token for the host in your credential "
    f"helper; {SSH_KEY}), then re-run ")
#: And for a push ssh was refused the key for (#993): `setup-git` is not
#: named as a fix, since it changes nothing over ssh.
KEY_REFUSED_REMEDY = (
    "Remediation: GitHub took no ssh key of yours for the push to @REPO@: a "
    "`url.<base>.insteadOf` or `url.<base>.pushInsteadOf` rule in your git "
    "config sends it over ssh, where git logs in with an ssh key and not with "
    "the login `gh` has, so `gh auth setup-git` changes nothing for it. Give "
    f"GitHub a key it takes first ({SSH_KEY_CHECK}), then re-run ")


def assert_the_login_is_named(printed: str, repo: str, re_run: str,
                              fix: str = NO_LOGIN_REMEDY) -> None:
    """`printed` says a push was refused, then `fix`, how to give git a login
    for `repo`, then `re_run`, then the ruleset hint: the remedy once, read
    with its lines joined, as a person reads a line the terminal wrapped."""
    said = " ".join(printed.split())
    remedy = fix.replace("@REPO@", repo) + re_run
    assert said.count(remedy) == 1, printed
    assert (said.index("REFUSED pushing ") < said.index(remedy)
            < said.index("If the organisation applies a ruleset")), printed


@WINDOWS_SKIP
@PTY_SKIP
@pytest.mark.parametrize("helper", ["", "store"],
                         ids=["no-helper", "a-store-with-nothing-stored"])
def test_a_first_scaffold_s_push_git_has_no_login_for_names_the_fix(
        tmp_path, helper):
    """#915, RV971's MUST-1. A first scaffold's pushes are the same call as
    a re-run's, so the prompt is off for them too. Typed in a terminal
    against a host that asks for a login, with no credential helper, or
    with `store` over an empty file (a helper `setup-project.py` counts as
    configured, with nothing to give), git asked at `Username for '...':`
    before #915, took what was typed, and pushed (RV971's probe). Now the
    spec leg's push is refused without waiting, the three repositories this
    run created are left empty, and before the ruleset hint, whose re-run
    alone is refused the same way, the run names how to give git a login
    and then the re-run with --reuse-empty-repo. With the rule on a
    re-run's pushes alone (RV971's M10), this run waits at git's prompt
    until the harness kills it."""
    env, log = fake_gh(tmp_path, {}, plan="team")
    store = tmp_path / "git-credentials"
    store.write_text("", encoding="utf-8")
    status, screen = in_a_terminal_asked_for_a_login(
        tmp_path, env, helper=f'store --file="{store}"' if helper else "",
        timeout=120)
    assert status == 2, screen
    assert "REFUSED pushing the spec leg. THE EXACT COMMAND WAS:" in screen, (
        screen)
    assert_the_login_is_named(screen, SPEC_REPO, RE_RUN_WITH_THE_FLAG)
    assert log.read_text(encoding="utf-8").count("repo create") == 3, (
        "a first run creates all three")
    assert store.read_text(encoding="utf-8") == "", "nothing was stored"


#: What the GitHub side holds for a re-run: the three repositories, empty.
ALL_THREE = {PROJECT: "PRIVATE", f"{PROJECT}-spec": "PRIVATE",
             f"{PROJECT}-code": "PRIVATE"}


@WINDOWS_SKIP
@PTY_SKIP
@pytest.mark.parametrize("flags,repos,re_run", [
    ((), {}, RE_RUN_WITH_THE_FLAG),
    (("--reuse-empty-repo",), ALL_THREE, RE_RUN_AS_IT_WAS),
], ids=["a-first-run", "a-re-run"])
def test_a_push_whose_stored_login_the_host_refuses_names_the_fix(
        tmp_path, git_language, flags, repos, re_run):
    """#993. A stored login the host refuses is not one git could not get:
    git sends the token its credential helper holds, the host answers 401,
    and git dies `Authentication failed for '<url>'`, which holds none of
    `NO_LOGIN`'s words, so on main through 04923f1 the push printed the
    ruleset hint alone, whose re-run pushes with the same login. Typed in a
    terminal, with `store` holding a token the local server refuses, a first
    run and a re-run each exit 2 without waiting, and name the login the
    host refused, how to replace it and the re-run, before the hint.

    `translated` runs git where it speaks another language, whose catalogue
    translates `Authentication failed for` (`XX_GIT`): each push runs under
    `PUSH_ENV`, so git's words are found there too; under `REMOTE_ENV` they
    were not, and the run printed the hint alone."""
    env, log = fake_gh(tmp_path, repos, plan="team")
    env.update(git_language)
    status, screen = in_a_terminal_asked_for_a_login(
        tmp_path, env, *flags, stored="someone:badtoken",
        said="fatal: Authentication failed for ", timeout=120)
    assert status == 2, screen
    assert "REFUSED pushing the spec leg. THE EXACT COMMAND WAS:" in screen, (
        screen)
    assert_the_login_is_named(screen, SPEC_REPO, re_run,
                              fix=LOGIN_REFUSED_REMEDY)
    assert "could not get a login" not in screen, screen
    assert log.read_text(encoding="utf-8").count("repo create") == (
        0 if flags else 3), "a first run creates all three, a re-run none"


# --- a leg git reaches over ssh (#915) --------------------------------------

#: What ssh prints when GitHub takes none of its keys, on stderr, before it
#: exits 255. git then prints its generic `fatal:` line, and nothing of
#: ssh's has a `fatal:` of its own.
REFUSED_KEY = "git@github.com: Permission denied (publickey)."
#: An ssh that says `REFUSED_KEY` to every command line, so nothing leaves
#: this machine.
FAKE_SSH = textwrap.dedent(f"""\
    import sys
    print({REFUSED_KEY!r}, file=sys.stderr)
    sys.exit(255)
    """)


def git_reaches_github_over_ssh(tmp_path, rule: str = "insteadOf") -> dict:
    """What an operator's git config that rewrites `https://github.com/` to
    ssh does (#915), for `https://github.com/<ORG>/`, appended to the
    command scope the environment holds, with `FAKE_SSH` as the ssh git
    runs. `rule` is `insteadOf`, for every command, or `pushInsteadOf`, for
    pushes alone (#993). `GIT_SSH_VARIANT` says it takes OpenSSH's options,
    which git would otherwise find out by running it once more, with `-G`."""
    ssh = tmp_path / "fake_ssh.py"
    ssh.write_text(FAKE_SSH, encoding="utf-8")
    return {**appended_to_command_scope(
                os.environ, [(f"url.ssh://git@github.com/{ORG}/.{rule}",
                              f"https://github.com/{ORG}/")]),
            "GIT_SSH_COMMAND": f'"{sys.executable}" "{ssh}"',
            "GIT_SSH_VARIANT": "ssh"}


#: glibc's own `C.UTF-8`, which a test copies under a name of its own into
#: a `LOCPATH` of its own: a locale that is not `C`, so gettext reads
#: `LANGUAGE`, and needs nothing installed beyond the C library's.
C_UTF8 = Path("/usr/lib/locale/C.utf8")
#: What git prints for `fatal: ` in `xx`, the test's own language.
XX_FATAL = "XX-FATAL: "
#: A catalogue for git in `xx`: the `fatal: ` before every fatal line, git's
#: generic message with its advice, and its line for a login the host
#: refused (#993), translated as a person's locale translates them, so where
#: git speaks `xx` none is in git's words.
XX_GIT = {
    "": "Content-Type: text/plain; charset=UTF-8\nLanguage: xx\n",
    "fatal: ": XX_FATAL,
    "Authentication failed for '%s'": "XX the host said no to '%s'",
    "Could not read from remote repository.\n\nPlease make sure you have "
    "the correct access rights\nand the repository exists.":
        "XX could not read the remote.\n\nXX make sure of your rights\n"
        "XX and that the repository is there.",
}


def mo_bytes(messages: dict) -> bytes:
    """`messages` as a GNU gettext catalogue, a `.mo` file, so no `msgfmt` is
    needed: the header (magic, revision 0, the count, where each table is,
    no hash table), a table of each original's length and offset, sorted by
    original, a table of each translation's, then the strings, each ended
    by a NUL. Little-endian; gettext reads either order by the magic."""
    originals = sorted(messages)  # code-point order is UTF-8's byte order
    keys = [key.encode("utf-8") for key in originals]
    values = [messages[key].encode("utf-8") for key in originals]
    count = len(originals)
    strings = 7 * 4 + 2 * 8 * count
    tables = []
    at = strings
    for column in (keys, values):
        for text in column:
            tables += [len(text), at]
            at += len(text) + 1
    return (struct.pack("<7I", 0x950412DE, 0, count, 7 * 4,
                        7 * 4 + 8 * count, 0, 0)
            + struct.pack(f"<{4 * count}I", *tables)
            + b"".join(text + b"\0" for text in keys + values))


def git_speaks_xx(tmp_path) -> dict:
    """What makes git speak `xx` (`XX_GIT`): `LOCPATH` holds `C_UTF8` as
    `xx_XX.UTF-8`, `LC_ALL` names it, `LANGUAGE` asks for `xx`, and
    `GIT_TEXTDOMAINDIR` holds the catalogue. Skipped where there is no
    `C_UTF8` to copy, and where git, asked once of a path that is no
    repository, does not speak it: a git built without gettext, or a C
    library that reads no `LOCPATH`."""
    if not C_UTF8.is_dir():
        pytest.skip(f"no {C_UTF8} to copy as a locale of the test's own")
    kit = tmp_path / "xx"
    shutil.copytree(C_UTF8, kit / "locales" / "xx_XX.UTF-8")
    catalogue = kit / "catalogues" / "xx" / "LC_MESSAGES"
    catalogue.mkdir(parents=True)
    (catalogue / "git.mo").write_bytes(mo_bytes(XX_GIT))
    speaks = {"LOCPATH": str(kit / "locales"), "LC_ALL": "xx_XX.UTF-8",
              "LANGUAGE": "xx", "GIT_TEXTDOMAINDIR": str(kit / "catalogues")}
    asked = subprocess.run(["git", "ls-remote", str(kit / "no-repository")],
                           env={**os.environ, **speaks}, capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           check=False)
    if not asked.stderr.startswith(XX_FATAL):
        pytest.skip("git here does not speak a catalogue from "
                    f"GIT_TEXTDOMAINDIR: {asked.stderr.strip()[:200]}")
    return speaks


@pytest.fixture(params=["as-it-is", "translated"])
def git_language(request, tmp_path) -> dict:
    """What a test adds to its environment to run git as it is (`{}`) or
    translated (`git_speaks_xx`, RV971's kit). Only the translated row is
    skipped where `git_speaks_xx` skips; the other row runs there."""
    return {} if request.param == "as-it-is" else git_speaks_xx(tmp_path)


@WINDOWS_SKIP
def test_a_leg_git_reaches_over_ssh_is_refused_with_ssh_s_reason(
        tmp_path, git_language):
    """#915. Where git config rewrites `https://github.com/` to ssh, git's
    one `fatal:` line for a leg ssh could not log in to is the generic
    `Could not read from remote repository.`, and ssh's own reason, which
    has no `fatal:`, was dropped: the refusal said git could not read the
    leg and not why, and named `gh auth setup-git` alone, which changes
    nothing for git over ssh. Now ssh's last line is the reason, and the
    remedy names the ssh key beside `setup-git`.

    `translated` asks it where git speaks another language (`git_speaks_xx`,
    RV971's kit). `only_commit`'s git runs under `LC_ALL=C` (`PROBE_ENV`),
    so its `fatal:` and its generic line are found there too; without it no
    line started `fatal:`, and the reason was git's last line, advice about
    its own command (RV971's M4)."""
    env, log = fake_gh(tmp_path, SEEN_SPEC, full=[f"{PROJECT}-spec"])
    env.update(git_reaches_github_over_ssh(tmp_path))
    env.update(git_language)
    result = on_github(tmp_path, "--reuse-empty-repo", env=env, cwd=tmp_path)
    assert result.returncode == 2, result.stderr + result.stdout
    assert (f"REFUSED scaffold-remote-exists: {SPEC_REPO} already exists on "
            "GitHub and has commits\nRemediation: git could not read it "
            f"(`git ls-remote https://github.com/{SPEC_REPO}.git` exited "
            f"128: {REFUSED_KEY}), {UNREAD_EXIT}") in result.stderr, (
        result.stderr)
    assert "Could not read from remote repository" not in result.stderr
    assert "repo create" not in log.read_text(encoding="utf-8"), (
        "nothing was created")


@WINDOWS_SKIP
@pytest.mark.parametrize("rule", ["insteadOf", "pushInsteadOf"])
def test_a_push_ssh_was_refused_the_key_for_names_the_fix(
        tmp_path, git_language, rule):
    """#993. Where git config sends a first scaffold's push over ssh, by an
    `insteadOf` rule or a `pushInsteadOf` one, and the host takes no key,
    ssh says `Permission denied (publickey).` and git its generic line,
    neither of them `NO_LOGIN`'s words, so on main through 04923f1 the push
    printed the ruleset hint alone. Now the run exits 2 and names the ssh
    check, then the re-run with the flag, then the hint, and not `gh auth
    setup-git`, which changes nothing over ssh. ssh's words are its own and
    untranslated, so `translated` finds them too."""
    env, log = fake_gh(tmp_path, {}, plan="team")
    env.update(git_reaches_github_over_ssh(tmp_path, rule))
    env.update(git_language)
    result = run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                        "--elected-by", "Test Human",
                        "--work-dir", str(tmp_path / "work"),
                        cwd=tmp_path, env=env)
    assert result.returncode == 2, result.stderr + result.stdout
    assert "REFUSED pushing the spec leg. THE EXACT COMMAND WAS:" in (
        result.stderr), result.stderr
    assert REFUSED_KEY in result.stderr, result.stderr
    assert_the_login_is_named(result.stderr, SPEC_REPO, RE_RUN_WITH_THE_FLAG,
                              fix=KEY_REFUSED_REMEDY)
    assert "setup-git` gives git" not in result.stderr, result.stderr
    assert log.read_text(encoding="utf-8").count("repo create") == 3, (
        "a first run creates all three")


@pytest.fixture(scope="module")
def scaffold_module():
    return load_without_bytecode(SCAFFOLD, "scaffold_for_unread_because")


#: git's advice after its generic `fatal:` line, which no reason keeps.
ADVICE = ("\n\nPlease make sure you have the correct access rights\n"
          "and the repository exists.")
GENERIC = "fatal: Could not read from remote repository."
NOT_A_REPOSITORY = ("fatal: '/x/Atlas-spec.git' does not appear to be a "
                    "git repository")
NO_PROMPT = ("fatal: could not read Username for 'https://github.com': "
             "terminal prompts disabled")
#: Two `fatal:` lines of git's own, the first of them the reason (RV971).
NOT_OUR_REF = ("fatal: remote error: upload-pack: not our ref "
               "0123456789abcdef0123456789abcdef01234567")
HUNG_UP = "fatal: the remote end hung up unexpectedly"
#: A line git prints before a `fatal:` that is not the generic one (RV971).
REDIRECTED = "warning: redirecting to https://github.com/o/r.git/"


@pytest.mark.parametrize("output,reason", [
    (f"Warning: Permanently added 'github.com' to the list of known "
     f"hosts.\n{REFUSED_KEY}\n{GENERIC}{ADVICE}", REFUSED_KEY),
    (f"{NOT_A_REPOSITORY}\n{GENERIC}{ADVICE}", NOT_A_REPOSITORY),
    (f"{GENERIC}{ADVICE}", GENERIC),
    (NO_PROMPT, NO_PROMPT),
    (f"{NOT_OUR_REF}\n{HUNG_UP}", NOT_OUR_REF),
    (f"{REDIRECTED}\n{NO_PROMPT}", NO_PROMPT),
    ("error: one thing\nanother thing", "another thing"),
    ("", None),
], ids=["ssh-before-the-generic-line", "git-s-own-fatal-first",
        "the-generic-line-alone", "one-fatal", "two-fatal-lines-the-first",
        "a-line-before-a-fatal-not-the-generic-one", "no-fatal",
        "nothing-said"])
def test_the_reason_git_could_not_read_a_leg(scaffold_module, output,
                                             reason):
    """`_unread_because` (#542, #915): git's first `fatal:` line, except
    that where it is the generic one the line before it, ssh's, is the
    reason; a `fatal:` of git's own before the generic one, and the generic
    one with nothing before it, are kept; with no `fatal:`, git's last line.
    Of two `fatal:` lines the first is kept, where the last is git hanging
    up (RV971's M8), and a line before a `fatal:` that is not the generic
    one is not the reason (RV971's M11). In-process, so it runs on every
    platform."""
    failed = scaffold_module.CommandFailed(["git", "ls-remote", "u"], None,
                                           128, output)
    assert scaffold_module._unread_because(failed) == (
        "`git ls-remote u` exited 128" + (f": {reason}" if reason else ""))


# --- what a refused push prints (#915) --------------------------------------

#: A refused push that is not a login git could not get: a ruleset's, as
#: `test_ruleset_hint_tracking_branch.py`'s hook and GitHub refuse one.
RULESET_SAID = ("remote: error: GH013: Repository rule violations found for "
                "refs/heads/main: changes must be made through a pull "
                "request.\nTo https://github.com/o/r.git\n ! [remote "
                "rejected] HEAD -> main (pre-receive hook declined)\nerror: "
                "failed to push some refs to 'https://github.com/o/r.git'")
#: git's line where the URL names the user, so only a password is asked.
NO_PASSWORD = ("fatal: could not read Password for "
               "'https://someone@github.com': terminal prompts disabled")
#: git's line where its prompt is on and there is no terminal to ask in: a
#: login git could not get as much as the two above.
NO_TERMINAL = ("fatal: could not read Username for 'https://github.com': "
               "No such device or address")
#: git's line where it sent a login and the host refused it (#993).
LOGIN_REFUSED = ("fatal: Authentication failed for "
                 "'https://github.com/o/r.git/'")
#: What GitHub and git say for a login the host took and a right it lacks:
#: not a login to give or replace, so it keeps the hint alone (#993).
FORBIDDEN = ("remote: Permission to o/r.git denied to someone.\nfatal: "
             "unable to access 'https://github.com/o/r.git/': The requested "
             "URL returned error: 403")
#: ssh's line where the host offers more ways to log in than a key.
REFUSED_KEY_AND_MORE = ("git@example.invalid: Permission denied "
                        "(publickey,password).")


@pytest.mark.parametrize("output,reused,fix,re_run", [
    (NO_PROMPT, False, NO_LOGIN_REMEDY, RE_RUN_WITH_THE_FLAG),
    (NO_PROMPT, True, NO_LOGIN_REMEDY, RE_RUN_AS_IT_WAS),
    (NO_PASSWORD, False, NO_LOGIN_REMEDY, RE_RUN_WITH_THE_FLAG),
    (NO_TERMINAL, False, NO_LOGIN_REMEDY, RE_RUN_WITH_THE_FLAG),
    (LOGIN_REFUSED, False, LOGIN_REFUSED_REMEDY, RE_RUN_WITH_THE_FLAG),
    (LOGIN_REFUSED, True, LOGIN_REFUSED_REMEDY, RE_RUN_AS_IT_WAS),
    (f"{REFUSED_KEY}\n{GENERIC}{ADVICE}", False, KEY_REFUSED_REMEDY,
     RE_RUN_WITH_THE_FLAG),
    (f"{REFUSED_KEY}\n{GENERIC}{ADVICE}", True, KEY_REFUSED_REMEDY,
     RE_RUN_AS_IT_WAS),
    (f"{REFUSED_KEY_AND_MORE}\n{GENERIC}{ADVICE}", False, KEY_REFUSED_REMEDY,
     RE_RUN_WITH_THE_FLAG),
    (RULESET_SAID, False, None, None),
    (FORBIDDEN, False, None, None),
], ids=["no-username", "no-username-on-the-re-run", "no-password",
        "no-terminal", "login-refused", "login-refused-on-the-re-run",
        "ssh-refused-the-key", "ssh-refused-the-key-on-the-re-run",
        "ssh-refused-the-key-of-more-ways", "a-ruleset", "a-403"])
def test_what_a_refused_push_prints(scaffold_module, capsys, output, reused,
                                    fix, re_run):
    """`_refused_push` (#915, #993): the command and git's output, then,
    where git could not get a login (`NO_LOGIN`), the host refused the one
    git sent (`LOGIN_REFUSED`) or ssh was refused the key (`KEY_REFUSED`),
    that case's fix and the re-run, then the ruleset hint. Any other
    refusal, an HTTP 403 among them, prints, byte for byte, what a refused
    push always printed: the command, git's output, the hint. A re-run's
    remedy names its own command again, not the flag it has. In-process, so
    it runs on every platform."""
    failed = scaffold_module.CommandFailed(
        ["git", "push", "-q", "-u", "origin", "HEAD:refs/heads/main"],
        Path("work"), 128, output)
    scaffold_module._refused_push(failed, "pushing the spec leg", "o/r",
                                  "main", reused)
    out, err = capsys.readouterr()
    remedy = ("" if fix is None else
              "\n" + fix.replace("@REPO@", "o/r") + re_run + "\n")
    assert out == ""
    assert err == (failed.loudly("pushing the spec leg") + "\n" + remedy
                   + scaffold_module.RULESET_HINT.format(repo="o/r",
                                                         tracking="main")
                   + "\n"), err


def test_the_root_s_push_git_has_no_login_for_names_the_fix_too(
        tmp_path, monkeypatch, capsys):
    """#915. The root's push is refused as each leg's is (`_refused_push`):
    after both legs went through to bare repositories on disk, the root's
    push, refused in-process with git's words for a login it could not get,
    names how to give git a login for `<ORG>/<PROJECT>` and the re-run,
    before the ruleset hint. In-process, so it runs on every platform."""
    module = load_without_bytecode(SCAFFOLD, "scaffold_for_root_login")
    real = module.run

    def no_login_for_the_root(args, cwd=None, capture=True, env=None):
        if args[:2] == ["git", "push"] and Path(cwd).name == PROJECT:
            raise module.CommandFailed(args, cwd, 128, NO_PROMPT)
        return real(args, cwd=cwd, capture=capture, env=env)

    monkeypatch.setattr(module, "run", no_login_for_the_root)
    code = module.main(["--org", ORG, "--project", PROJECT,
                        "--elected-by", "Test Human",
                        "--elected-on", "2026-09-02",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work")])
    out, err = capsys.readouterr()
    assert code == 2, err + out
    assert "REFUSED pushing the assembly root." in err, err
    assert_the_login_is_named(err, f"{ORG}/{PROJECT}", RE_RUN_WITH_THE_FLAG)
    assert all(tip(tmp_path, leg) for leg in LEGS), "both legs went through"
    assert commits(tmp_path, "assembly") == 0
