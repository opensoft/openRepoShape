# SPDX-License-Identifier: Apache-2.0
"""What the scaffold's and `family.py init`'s plan and NOTEs say about the
remotes and their visibility (#913).

WHAT WAS WRONG, in #459's lines that #913 groups:
- U167, L2-96. Under `--reuse-empty-repo` a root whose `--json visibility`
  read failed had the legs this run creates made private with no word,
  `--dry-run` included, and only a real run's last NOTE said the read
  failed; and the root was read twice, before the plan and again while the
  remotes were made, so the two reads could disagree.
- U163, L2-92. A reused leg whose read failed was taken at the run's
  visibility, so the leg NOTE and the Free-plan hint went by a value GitHub
  did not give: a private leg under a public run got no NOTE and its
  private root no hint, and a public leg under a private run was called
  private, and nothing said a read failed.
- U010, AT-scaffold N3. The plan a person approves, the scaffold's and
  `init`'s, named neither the tracking branch nor, under
  `--local-remote-dir`, the visibility the manifest records.
- U060, L2-61. Only gh's not-found answer reads as absent (#609), and
  GitHub gives it for a private repository the token cannot see, so the
  plan said a repository would be created that the real run then fails to
  create. gh's answer cannot tell the two apart, so the plan says "not
  found" is what this token can see.

`gh` is `test_scaffold_reuse_seeded_legs.py`'s stub, first on PATH: it knows
each repository at its visibility, names the plan, and fails the `--json
visibility` reads it is told to. Nothing reaches GitHub. It is a `#!`
script, so the runs that start it are `WINDOWS_SKIP`ped; the plans under
`--local-remote-dir` start no `gh` and run everywhere.
"""

from __future__ import annotations

import pytest

from conftest import ORG, PROJECT, REPO, SCAFFOLD, WINDOWS_SKIP, run_script
from test_scaffold_reuse_seeded_legs import fake_gh, on_github

FAMILY = REPO / "scripts" / "family.py"
HOLDER = "Orbit"
ROOT = f"{ORG}/{PROJECT}"
SPEC, CODE = f"{ROOT}-spec", f"{ROOT}-code"
BAD_GATEWAY = "HTTP 502: Bad Gateway (https://api.github.com/graphql)"
PLAN_STARTS = "project      "
DRY_RUN_DONE = "--dry-run: nothing was created."
VISIBILITY_ASKED = f"repo view {ROOT} --json visibility"

#: What the scaffold says before its plan of a root it could not read, with
#: no `--visibility` and with `--visibility public`.
ROOT_UNREAD_DEFAULT = (
    f"NOTE this run could not read {ROOT}'s visibility from GitHub, so a leg "
    "this run creates is created private, the default, and does not "
    f"inherit {ROOT}'s; a leg it reuses keeps its own. Pass --visibility to "
    f"choose one before any leg exists; `gh repo view {ROOT} --json "
    f"visibility` says which {ROOT} is.")
ROOT_UNREAD_PUBLIC = (
    f"NOTE this run could not read {ROOT}'s visibility from GitHub, so it "
    "cannot say whether --visibility public agrees with it. A leg this run "
    "creates is created public, as you asked; a leg it reuses keeps its "
    f"own. `gh repo view {ROOT} --json visibility` says which {ROOT} is.")
#: What a real run says at its end of a reused root it could not read.
ROOT_UNREAD_AT_THE_END = (
    f"NOTE this run could not read {ROOT}'s visibility from GitHub, so it "
    "cannot say whether the Free-plan secrets hint applies.")
#: What the plan says under its `gh repo create` row.
NOT_FOUND_LINES = (
    "             with this token: a private repository it cannot see is "
    "not found\n"
    "             either, and `gh repo create` then fails for it\n")


def unread_legs(*legs: str) -> str:
    """The NOTE a real run prints for the reused legs it could not read."""
    if len(legs) == 1:
        whose, them, who, which = (f"{legs[0]}'s visibility", "it",
                                   "if it is", "that leg")
        asks = f"`gh repo view {legs[0]} --json visibility` says which it is."
    else:
        whose, them, who, which = (
            f"the visibility of {legs[0]} and {legs[1]}", "them",
            "for each that is", "the legs")
        asks = (f"`gh repo view {legs[0]} --json visibility` and `gh repo "
                f"view {legs[1]} --json visibility` say which each is.")
    return (f"NOTE this run could not read {whose} from GitHub, so it cannot "
            f"say whether {ROOT} needs a way to read {them}: {who} private or "
            f"internal, give {ROOT} a GitHub App (SHAPE_LEGS_APP_ID + "
            "SHAPE_LEGS_APP_PRIVATE_KEY, preferred) or a SHAPE_LEGS_TOKEN PAT "
            f"(contents:read on {which}, fallback), or the `validate` check "
            f"cannot check it out. {asks}")


def calls_of(log) -> list:
    return log.read_text(encoding="utf-8").splitlines()


# --- U167: a root it could not read, said before the plan, and read once ----

@WINDOWS_SKIP
@pytest.mark.parametrize("flags, note", [
    ((), ROOT_UNREAD_DEFAULT),
    (("--visibility", "public"), ROOT_UNREAD_PUBLIC),
], ids=["default", "chosen"])
def test_a_root_it_could_not_read_is_said_before_the_plan(tmp_path, flags,
                                                          note):
    """L2-96: a dry run over a reused root whose visibility read fails says
    so before the plan, while `--visibility` can still choose what the legs
    it creates are, and asks the root's visibility once. On main it printed
    nothing about the read and planned the legs private."""
    env, log = fake_gh(tmp_path, {PROJECT: "PRIVATE"},
                       visibility_errors={PROJECT: BAD_GATEWAY})
    result = on_github(tmp_path, "--reuse-empty-repo", "--dry-run", *flags,
                       env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert DRY_RUN_DONE in result.stdout
    assert result.stdout.count(note) == 1, result.stdout
    assert result.stdout.index(note) < result.stdout.index(PLAN_STARTS)
    assert calls_of(log).count(VISIBILITY_ASKED) == 1, calls_of(log)


@WINDOWS_SKIP
@pytest.mark.parametrize("repos", [{}, {PROJECT: "PRIVATE"}],
                         ids=["not-found", "read"])
def test_a_root_gh_does_not_find_or_reads_is_not_said_to_be_unread(
        tmp_path, repos):
    """The controls: a root gh does not find is the ordinary
    `--reuse-empty-repo` run, which creates it, and one it reads is
    inherited as before; neither is said to be unread."""
    env, _log = fake_gh(tmp_path, repos)
    result = on_github(tmp_path, "--reuse-empty-repo", "--dry-run", env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "could not read" not in result.stdout + result.stderr
    assert (f"NOTE {ROOT} is already private on GitHub" in result.stdout) == (
        bool(repos)), result.stdout


@WINDOWS_SKIP
@pytest.mark.parametrize("errors", [None, {PROJECT: BAD_GATEWAY}],
                         ids=["read", "unread"])
def test_a_real_run_reads_the_reused_root_once(tmp_path, errors):
    """L2-96: the real run asks the root's visibility once, before the plan,
    and its last NOTE goes by that read: the root's visibility for the
    Free-plan hint, or `ROOT_VISIBILITY_UNREAD`. On main `_create_remotes`
    asked again, and the two reads could disagree."""
    env, log = fake_gh(tmp_path, {PROJECT: "PRIVATE"}, plan="free",
                       visibility_errors=errors)
    result = on_github(tmp_path, "--reuse-empty-repo", env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert calls_of(log).count(VISIBILITY_ASKED) == 1, calls_of(log)
    if errors:
        assert ROOT_UNREAD_DEFAULT in result.stdout, result.stdout
        assert ROOT_UNREAD_AT_THE_END in result.stdout, result.stdout
        assert f"NOTE {ORG} is on the GitHub FREE plan" not in result.stdout
    else:
        assert f"{ROOT} is private, so org-level" in result.stdout
        assert "could not read" not in result.stdout


# --- U163: a reused leg it could not read -----------------------------------

@WINDOWS_SKIP
@pytest.mark.parametrize("repos, flags, plan, unread, said, hint", [
    # L2-92's first run: everything private, a public run, a Free plan. On
    # main: no leg NOTE and no hint, though the root is private on Free.
    ({PROJECT: "PRIVATE", f"{PROJECT}-spec": "PRIVATE",
      f"{PROJECT}-code": "PRIVATE"}, ("--visibility", "public"), "free",
     ("spec", "code"), (), True),
    # Its second: everything public, a private run. On main the NOTE called
    # both legs private.
    ({PROJECT: "PUBLIC", f"{PROJECT}-spec": "PUBLIC",
      f"{PROJECT}-code": "PUBLIC"}, ("--visibility", "private"), "free",
     ("spec", "code"), (), False),
    # One leg unread, the other read private: the one read is named at its
    # visibility, the other said to be unread, and a paid plan has no hint.
    ({PROJECT: "PRIVATE", f"{PROJECT}-spec": "PUBLIC",
      f"{PROJECT}-code": "PRIVATE"}, (), "team", ("spec",),
     (f"NOTE {CODE} is private: give {ROOT} a way to read it",), False),
], ids=["private-legs-under-a-public-run", "public-legs-under-a-private-run",
        "one-leg-unread"])
def test_a_reused_leg_it_could_not_read_is_said_to_be_unread(
        tmp_path, repos, flags, plan, unread, said, hint):
    """L2-92: a reused leg whose visibility GitHub does not give is said to
    be unread, by name, with what its answer would mean, and the legs it
    could read are named as before; the Free-plan hint goes by the root. On
    main the run's visibility stood in for each such leg."""
    legs = {"spec": f"{PROJECT}-spec", "code": f"{PROJECT}-code"}
    env, _log = fake_gh(tmp_path, repos, plan=plan, visibility_errors={
        legs[role]: BAD_GATEWAY for role in unread})
    result = on_github(tmp_path, "--reuse-empty-repo", *flags, env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    printed = result.stdout + result.stderr
    assert printed.count(unread_legs(*(f"{ORG}/{legs[role]}"
                                       for role in unread))) == 1, printed
    notes = [line for line in result.stdout.splitlines()
             if line.startswith("NOTE ") and ": give " in line]
    assert len(notes) == len(said), notes
    for line in said:
        assert line in printed, printed
    assert (f"{ROOT} is private, so org-level" in printed) == hint, printed
    for role in unread:
        assert f"WARNING {ORG}/{legs[role]} is reused" not in printed, printed


# --- U010 and U060: the plan's rows -----------------------------------------

def scaffold_on_disk(tmp_path, *extra: str):
    return run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                      "--elected-by", "Test Human", "--dry-run",
                      "--local-remote-dir", str(tmp_path / "remotes"),
                      "--work-dir", str(tmp_path / "work"), *extra)


def init_run(tmp_path, *extra: str, env: dict | None = None):
    return run_script(FAMILY, "init", "--org", ORG, "--family", HOLDER,
                      "--created-by", "Test Human", "--dry-run",
                      "--work-dir", str(tmp_path / "work"), *extra, env=env)


@pytest.mark.parametrize("tool", ["scaffold", "family"])
@pytest.mark.parametrize("flags, branch, visibility", [
    ((), "main", "private"),
    (("--tracking-branch", "trunk", "--visibility", "public"), "trunk",
     "public"),
], ids=["defaults", "chosen"])
def test_the_plan_on_disk_names_the_branch_and_the_visibility(
        tmp_path, tool, flags, branch, visibility):
    """AT-scaffold N3: under `--local-remote-dir` the plan names the tracking
    branch the repositories are created on and the visibility the manifest
    records, which a bare repository on disk does not have; on main it
    named neither."""
    if tool == "scaffold":
        result = scaffold_on_disk(tmp_path, *flags)
        manifest, created = "project.yaml", "each of the three is created on"
        remotes = "remotes      bare repositories on disk (no network)\n"
    else:
        result = init_run(tmp_path, "--local-remote-dir",
                          str(tmp_path / "remotes"), *flags)
        manifest, created = "family.yaml", "the holder is created on"
        remotes = "remotes      a bare repository on disk (no network)\n"
    assert result.returncode == 0, result.stderr + result.stdout
    out = result.stdout
    row = (f"visibility   {visibility}, which {manifest} records; a bare "
           "repository on disk has none\n")
    assert out.count(row) == 1, out
    assert out.index(row) < out.index(remotes), out
    assert out.count(f"branch       {branch}, the tracking branch "
                     f"{created}\n") == 1, out
    assert "with this token" not in out, out


@WINDOWS_SKIP
@pytest.mark.parametrize("tool", ["scaffold", "family"])
def test_the_plan_on_github_says_not_found_is_what_this_token_sees(
        tmp_path, tool):
    """L2-61 and AT-scaffold N3 against GitHub: the `gh repo create` row
    says it creates what gh does not find, and that a private repository
    this token cannot see is not found either, so its create then fails;
    the branch is named; the visibility is the `gh repo create` flag, and
    no row of its own."""
    env, _log = fake_gh(tmp_path, {})
    if tool == "scaffold":
        result = on_github(tmp_path, "--dry-run", "--tracking-branch",
                           "trunk", env=env)
        row = ("remotes      gh repo create --private, for each of the three "
               "gh does not find\n")
        branch = "branch       trunk, the tracking branch each of the three "
    else:
        result = init_run(tmp_path, "--tracking-branch", "trunk", env=env)
        row = ("remotes      gh repo create --private, if gh does not find "
               f"{ORG}/{HOLDER}\n")
        branch = "branch       trunk, the tracking branch the holder "
    assert result.returncode == 0, result.stderr + result.stdout
    assert DRY_RUN_DONE in result.stdout
    assert result.stdout.count(row + NOT_FOUND_LINES) == 1, result.stdout
    assert result.stdout.count(branch) == 1, result.stdout
    assert "visibility   " not in result.stdout, result.stdout
