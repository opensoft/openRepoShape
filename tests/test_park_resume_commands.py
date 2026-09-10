# SPDX-License-Identifier: Apache-2.0
"""`park` and `resume` — the two installed USER COMMANDS (#82).

They ADD NO MECHANICS, so this file asserts exactly what they do add: finding
the estate, driving the estate's own `make park` / `make resume`, rebuilding or
fast-forwarding the estate before the verb runs, and every refusal. The WIP
commit, the push, the `git worktree add` and the soft reset belong to the
Speckit git extension and are tested in its own suite; `make park` / `make
resume` themselves are tested in `test_park_resume_targets.py`.

OFFLINE, LIKE THE REST OF THIS SUITE, and offline in three ways at once. The
extension script is a STUB that echoes its arguments (the same stub #80's tests
use). Every remote is a BARE REPOSITORY IN A TEMPORARY DIRECTORY, reached
through `$OPENREPOSHAPE_REMOTE_BASE` — `resume`'s documented test path, the
same concession `setup-project.py --local-remote-dir` and `family.py
--local-remote-dir` make. And `$HOME` is a temporary directory too, so the
`~/projects` / `~/Projects` spellings and `~/.agents/workspace.yaml` are the
test's own and never the developer's. Nothing here may create a real
repository, and nothing here reaches the network.

THE WORKSPACE MANIFEST IS WRITTEN BY HAND, at `schema_version: 1` — the schema
`opensoft/workBenches`'s `park.sh` writes as of its S1 (merged 2026-09-09).
Written out rather than generated, because a test that needed a workBenches
checkout beside this one would skip on every machine that has only this
repository, which is every fork.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP, git, rmtree

PARK = REPO / "park"
RESUME = REPO / "resume"
MAKE = shutil.which("make")

#: Both reasons this whole file needs a POSIX machine: the commands are bash,
#: and they run `make` in a root that execs a `#!`-shebang script.
pytestmark = [
    WINDOWS_SKIP,
    pytest.mark.skipif(shutil.which("bash") is None,
                       reason="park and resume are bash scripts"),
    pytest.mark.skipif(MAKE is None, reason="needs `make` on PATH"),
]

#: Where `setup-openspeckit` installs the extension's bash scripts, and so
#: where a stub has to live to be found by the `park` / `resume` targets.
OVERLAY = Path(".specify/extensions/git/scripts/bash")

#: `git` reads one-off configuration out of the environment, which is how a
#: test gives a plain `git clone`/`git submodule update` permission to clone a
#: local path without the tool under test knowing anything about it. `resume`
#: deliberately grants no such permission of its own. Copied from
#: `test_family.py`, for its reasons.
ALLOW_FILE_PROTOCOL = {"GIT_CONFIG_COUNT": "1",
                       "GIT_CONFIG_KEY_0": "protocol.file.allow",
                       "GIT_CONFIG_VALUE_0": "always"}

ORG = "testorg"
FAMILY = "TestFam"
MEMBERS = ("Alpha", "Bravo")
WORKSPACE_SLUG = "tester/wip"

#: A `parked_commit` has to be a 40-hex sha to be the schema's own shape. It
#: never has to RESOLVE here: nothing in this repository reads it — the
#: extension's `resume.sh` does, and it is stubbed.
FAKE_SHA = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"

#: A Makefile whose two verbs only SAY WHERE THEY RAN. Estate resolution is
#: what most of this file is about, and a probe that names its own directory
#: proves the answer in one line — where a real root would prove it through
#: three layers of somebody else's code.
PROBE_MAKEFILE = """\
.PHONY: park resume bootstrap siblings
park:
\t@echo "PROBE park in $(CURDIR) ARGS=[$(ARGS)]"
resume:
\t@echo "PROBE resume in $(CURDIR) ARGS=[$(ARGS)]"
bootstrap:
\t@echo "PROBE bootstrap in $(CURDIR)"
siblings:
\t@echo "PROBE siblings in $(CURDIR)"
"""

FAMILY_YAML = """\
schema_version: 1
kind: family-manifest
id: {id}
name: "{name}"
org: {org}
repository: {org}/{name}
tracking_branch: main
members_dir: members
members:{members}
"""

PROJECT_YAML = """\
schema_version: 1
kind: project-manifest
id: {id}
name: "{name}"
tracking_branch: main
legs:
  - role: assembly
    repository: {org}/{name}
    path: "."
"""


# --- the environment every run gets ----------------------------------------

def command_env(home: Path, env: dict | None = None) -> dict:
    """A fake `$HOME`, every variable these commands read cleared first.

    Cleared rather than merely defaulted, so a developer's own `$PROJECTS_DIR`
    or `$AGENT_PROTOCOL_ROOT` cannot change what these tests assert.
    `PYTHON=<this interpreter>` because the Makefiles say `PYTHON ?= python3`
    and `?=` honours the environment: the suite must exercise the interpreter
    it is running under, not whichever `python3` is first on PATH.
    """
    environ = dict(os.environ)
    for name in ("PROJECTS_DIR", "AGENT_PROTOCOL_ROOT",
                 "OPENREPOSHAPE_REMOTE_BASE", "MAKEFLAGS", "MAKELEVEL",
                 "SPECKIT_WORKSPACE_PATH", "SPECKIT_WORKSPACE_REPOSITORY"):
        environ.pop(name, None)
    environ["HOME"] = str(home)
    environ["PYTHON"] = sys.executable
    environ.setdefault("GIT_AUTHOR_NAME", "openRepoShape tests")
    environ.setdefault("GIT_AUTHOR_EMAIL", "tests@openreposhape.invalid")
    environ.setdefault("GIT_COMMITTER_NAME", "openRepoShape tests")
    environ.setdefault("GIT_COMMITTER_EMAIL", "tests@openreposhape.invalid")
    environ.update(env or {})
    return environ


def run(command: Path, *args: str, home: Path, cwd: Path | None = None,
        env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(command), *args], capture_output=True,
                          text=True, check=False, input="",
                          cwd=str(cwd) if cwd else str(home),
                          env=command_env(home, env))


@pytest.fixture
def home(tmp_path) -> Path:
    """A fake home with `projects/` in it — the common spelling."""
    target = tmp_path / "home"
    (target / "projects").mkdir(parents=True)
    return target


# --- estates on disk, with no remote at all ---------------------------------

def write_stub(root: Path, verb: str, code: int = 0, label: str = "") -> Path:
    """An executable stand-in for the extension's `<verb>.sh` (#80's stub)."""
    script = root / OVERLAY / f"{verb}.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        f'#!/bin/sh\necho "{label or verb}.sh ran with: $*"\nexit {code}\n',
        encoding="utf-8")
    script.chmod(0o755)
    return script


def probe_family(projects: Path, name: str) -> Path:
    """A family FOLDER with a holder in it and a probe Makefile. Returns the
    holder, which is where both verbs must run."""
    holder = projects / name / name
    holder.mkdir(parents=True)
    (holder / "family.yaml").write_text(
        FAMILY_YAML.format(id=name.lower(), name=name, org=ORG,
                           members=" []"), encoding="utf-8")
    (holder / "Makefile").write_text(PROBE_MAKEFILE, encoding="utf-8")
    return holder


def probe_project(projects: Path, name: str, *, at: Path | None = None) -> Path:
    """A standalone project root with a probe Makefile."""
    root = at if at is not None else projects / name
    root.mkdir(parents=True, exist_ok=True)
    (root / "project.yaml").write_text(
        PROJECT_YAML.format(id=name.lower(), name=name, org=ORG),
        encoding="utf-8")
    (root / "Makefile").write_text(PROBE_MAKEFILE, encoding="utf-8")
    return root


# --- the offline remotes, built once ---------------------------------------

def commit_all(path: Path, message: str) -> None:
    git("add", "-A", cwd=path)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", message,
        cwd=path)


def seed_member(base: Path, name: str) -> Path:
    """A bare repository holding one member of the family.

    Everything the flow reads and nothing else: an `origin` to identify it by,
    its own `project.yaml` id and tracking branch, the REAL assembly-root
    Makefile (so `make park` / `make resume` / `make bootstrap` are the shipped
    recipes), a `scripts/bootstrap.py` STUB, and the two overlay stubs. TWO
    commits, so a clone can be reset one back and be genuinely behind.
    """
    seed = base / "seed" / name
    (seed / "scripts").mkdir(parents=True)
    (seed / "project.yaml").write_text(
        PROJECT_YAML.format(id=name.lower(), name=name, org=ORG),
        encoding="utf-8")
    shutil.copy2(REPO / "templates" / "assembly-root" / "Makefile",
                 seed / "Makefile")
    # THE TEMPLATE'S OWN `.gitignore`, because a root that did not ignore
    # `__pycache__/` would read as a DIRTY ROOT the moment anything ran a
    # script in it - which is a fiction about the project, not about park.
    shutil.copy2(REPO / "templates" / "assembly-root" / ".gitignore",
                 seed / ".gitignore")
    (seed / "scripts" / "bootstrap.py").write_text(
        "#!/usr/bin/env python3\n"
        f'print("BOOTSTRAP-{name} ran")\n', encoding="utf-8")
    for verb in ("park", "resume"):
        write_stub(seed, verb, label=name)
    git("init", "-q", "-b", "main", ".", cwd=seed)
    commit_all(seed, "seed")
    (seed / "NOTES.md").write_text("the member moved on\n", encoding="utf-8")
    commit_all(seed, "a second commit, so a clone can be behind")
    bare = base / "remotes" / f"{name}.git"
    bare.parent.mkdir(exist_ok=True)
    git("clone", "-q", "--bare", str(seed), str(bare), cwd=base)
    return bare


def seed_holder(base: Path, members: dict) -> Path:
    """A bare repository holding the family HOLDER, with real submodules.

    Built from the template bytes, the way `test_park_resume_targets.py`'s
    fixture is, but with `git submodule add` so a `git clone
    --recurse-submodules` of it produces the pinned `members/<Project>` copies
    the holder's own `make bootstrap` and `make validate` read.
    """
    seed = base / "seed" / FAMILY
    (seed / "scripts").mkdir(parents=True)
    template = REPO / "templates" / "family-root"
    shutil.copy2(template / "Makefile", seed / "Makefile")
    shutil.copy2(template / ".gitignore", seed / ".gitignore")
    for rel in ("scripts/bootstrap.py", "scripts/siblings.py"):
        shutil.copy2(template / rel, seed / rel)
    shutil.copy2(REPO / "scripts" / "repo_shape.py",
                 seed / "scripts" / "repo_shape.py")
    rows = ""
    for name in MEMBERS:
        rows += (f"\n  - project: {name}\n"
                 f"    id: {name.lower()}\n"
                 f"    repository: {ORG}/{name}\n"
                 f"    path: members/{name}\n")
    (seed / "family.yaml").write_text(
        FAMILY_YAML.format(id=FAMILY.lower(), name=FAMILY, org=ORG,
                           members=rows), encoding="utf-8")
    git("init", "-q", "-b", "main", ".", cwd=seed)
    commit_all(seed, "seed")
    for name in MEMBERS:
        git("-c", "protocol.file.allow=always", "submodule", "add", "-q",
            str(members[name]), f"members/{name}", cwd=seed)
    commit_all(seed, "the members, pinned")
    (seed / "NOTES.md").write_text("the holder moved on\n", encoding="utf-8")
    commit_all(seed, "a second commit, so a clone can be behind")
    bare = base / "remotes" / f"{FAMILY}.git"
    git("clone", "-q", "--bare", str(seed), str(bare), cwd=base)
    return bare


def family_manifest(family: str = FAMILY) -> str:
    """One workspace manifest in the S1 schema, by hand (see this file's
    docstring). `family:` present is what makes it a FAMILY file, and the
    holder repository is read from the file's own org plus that name — the
    doubled-name rule; `projects[]` are the MEMBERS."""
    blocks = ""
    for name in MEMBERS:
        blocks += f"""\
  - id: {name.lower()}
    repository: {ORG}/{name}
    shape: three-leg
    root: {family}/{name}
    tracking_branch: main
    worktree_root: worktrees
    parked_at: 2026-09-09T18:42:11Z
    parked_on: Eagle
    parked_by_lane: xfactory-2
    active_feature: 001-{name.lower()}-thing
    active_feature_source: state_file
    features:
      - branch: 001-{name.lower()}-thing
        feature_directory: worktrees/001-{name.lower()}-thing/spec/specs/001-{name.lower()}-thing
        legs:
          - role: spec
            remote: origin
            parked_commit: {FAKE_SHA}
            wip: true
            wip_depth: 1
            pushed: true
"""
    return (f"schema_version: 1\nkind: workspace-manifest\n"
            f"family: {family}\nwritten_by: speckit park\nprojects:\n"
            + blocks)


def standalone_manifest(project: str) -> str:
    """A STANDALONE project's manifest: no `family:` key, so the root
    repository is `projects[0].repository` and the folder is its `root:`.

    Named for the project's `project.yaml` id (`alpha`), which is what the
    extension names it — and not for the folder a person types (`Alpha`),
    which is why the file is matched case-insensitively.
    """
    return f"""schema_version: 1
kind: workspace-manifest
written_by: speckit park
projects:
  - id: {project.lower()}
    repository: {ORG}/{project}
    shape: three-leg
    root: {project}
    tracking_branch: main
    worktree_root: worktrees
    parked_at: 2026-09-09T18:42:11Z
    parked_on: Eagle
    parked_by_lane: xfactory-2
    active_feature: 001-{project.lower()}-thing
    active_feature_source: state_file
    features:
      - branch: 001-{project.lower()}-thing
        legs:
          - role: repo
            remote: origin
            parked_commit: {FAKE_SHA}
            wip: false
            wip_depth: 0
            pushed: true
"""


def seed_workspace(base: Path, name: str, files: dict) -> Path:
    """A bare repository standing in for the person's private `<user>-wip`."""
    seed = base / "seed" / f"ws-{name}"
    seed.mkdir(parents=True)
    for rel, body in files.items():
        target = seed / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    git("init", "-q", "-b", "main", ".", cwd=seed)
    commit_all(seed, "the record")
    bare = base / "remotes" / f"{name}.git"
    bare.parent.mkdir(exist_ok=True)
    git("clone", "-q", "--bare", str(seed), str(bare), cwd=base)
    return bare


@pytest.fixture(scope="session")
def remotes(tmp_path_factory) -> dict:
    """Every bare repository this file clones from, built once."""
    base = tmp_path_factory.mktemp("parkresume")
    members = {name: seed_member(base, name) for name in MEMBERS}
    holder = seed_holder(base, members)
    workspace = seed_workspace(
        base, "wip",
        {f"workspaces/{ORG}/{FAMILY}.yaml": family_manifest()})
    two_orgs = seed_workspace(
        base, "twoorgs",
        {f"workspaces/orga/{FAMILY}.yaml": family_manifest(),
         f"workspaces/orgb/{FAMILY}.yaml": family_manifest()})
    solo = seed_workspace(
        base, "solo",
        {f"workspaces/{ORG}/alpha.yaml": standalone_manifest("Alpha")})
    return {"base": base, "dir": base / "remotes", "members": members,
            "holder": holder, "workspace": workspace, "two_orgs": two_orgs,
            "solo": solo}


def offline(remotes: dict, extra: dict | None = None) -> dict:
    return {"OPENREPOSHAPE_REMOTE_BASE": str(remotes["dir"]),
            **ALLOW_FILE_PROTOCOL, **(extra or {})}


@pytest.fixture
def estate(remotes, home) -> dict:
    """The family estate ALREADY on this machine: holder plus both siblings.

    Cloned rather than resumed, so the tests about `park` and about a REFRESH
    do not depend on the fresh-machine path working first.
    """
    projects = home / "projects"
    folder = projects / FAMILY
    folder.mkdir(parents=True, exist_ok=True)
    git("-c", "protocol.file.allow=always", "clone", "-q",
        "--recurse-submodules", str(remotes["holder"]), str(folder / FAMILY),
        cwd=projects)
    siblings = {}
    for name in MEMBERS:
        git("clone", "-q", str(remotes["members"][name]),
            str(folder / name), cwd=projects)
        siblings[name] = folder / name
    return {"projects": projects, "folder": folder, "holder": folder / FAMILY,
            "siblings": siblings}


# ===========================================================================
# estate resolution — the half both commands share
# ===========================================================================

@pytest.mark.parametrize("spelling", ["projects", "Projects"])
def test_a_named_estate_is_found_under_either_spelling(tmp_path, spelling):
    """People spell it both ways, which is the issue's own words."""
    fake_home = tmp_path / "home"
    projects = fake_home / spelling
    projects.mkdir(parents=True)
    holder = probe_family(projects, "InkRouter")
    result = run(PARK, "InkRouter", home=fake_home)
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"PROBE park in {holder} ARGS=[]" in result.stdout


def test_projects_dir_overrides_both_spellings(tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    elsewhere = tmp_path / "code"
    elsewhere.mkdir()
    root = probe_project(elsewhere, "Atlas")
    result = run(PARK, "Atlas", home=fake_home,
                 env={"PROJECTS_DIR": str(elsewhere)})
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"PROBE park in {root} ARGS=[]" in result.stdout


def test_a_family_folder_wins_over_a_standalone_root_of_the_same_name(home):
    """The holder is what drives the members. A family answered as one of its
    own members would park one project and report the estate parked."""
    projects = home / "projects"
    holder = probe_family(projects, "Dual")
    probe_project(projects, "Dual", at=projects / "Dual")
    result = run(PARK, "Dual", home=home)
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"PROBE park in {holder}" in result.stdout
    assert f"PROBE park in {projects / 'Dual'} " not in result.stdout


def test_with_no_name_the_estate_around_the_cwd_is_used(home):
    """`park` from a subdirectory, which is how a person actually types it."""
    projects = home / "projects"
    holder = probe_family(projects, "InkRouter")
    deep = holder / "scripts" / "inner"
    deep.mkdir(parents=True)
    result = run(PARK, home=home, cwd=deep)
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"PROBE park in {holder}" in result.stdout


def test_nearest_wins_so_a_member_parks_itself(home):
    """Standing inside a member of a family, the member is the estate. Nearest
    wins: it is where the person is."""
    projects = home / "projects"
    probe_family(projects, "InkRouter")
    member = probe_project(projects, "IRRS", at=projects / "InkRouter" / "IRRS")
    result = run(PARK, home=home, cwd=member)
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"PROBE park in {member}" in result.stdout


def test_no_name_and_no_estate_refuses_and_lists_what_it_found(home):
    """RULING 3, and the whole of it: nothing is parked by guess, and the
    refusal has to carry the names — a person in the wrong folder needs them,
    not an instruction to go and look."""
    projects = home / "projects"
    probe_family(projects, "InkRouter")
    probe_project(projects, "Atlas")
    result = run(PARK, home=home, cwd=home)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "no estate around" in result.stderr
    assert "never guesses which estate you meant, and it never parks all of" \
        in result.stderr
    assert "family   InkRouter" in result.stderr
    assert "project  Atlas" in result.stderr


def test_no_name_and_no_estates_at_all_says_none(tmp_path):
    fake_home = tmp_path / "home"
    (fake_home / "projects").mkdir(parents=True)
    result = run(PARK, home=fake_home)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "(none)" in result.stderr


def test_a_name_that_is_not_an_estate_refuses_and_names_resume(home):
    projects = home / "projects"
    probe_project(projects, "Atlas")
    result = run(PARK, "Nope", home=home)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "no estate named 'Nope'" in result.stderr
    assert "resume Nope" in result.stderr
    assert "project  Atlas" in result.stderr


#: The three spellings of one repository a clone's `origin` can carry. All
#: three must answer `--repo testorg/atlas` — and the case difference is in the
#: flag on purpose: GitHub owners and names are case-insensitive.
ORIGIN_SPELLINGS = [
    "https://github.com/TestOrg/Atlas.git",
    "git@github.com:TestOrg/Atlas.git",
    "ssh://git@github.com/TestOrg/Atlas.git",
]


@pytest.mark.parametrize("origin", ORIGIN_SPELLINGS)
def test_repo_matches_a_local_clone_by_its_origin(home, origin):
    """RULING 1: `--repo` matches a clone you already have."""
    projects = home / "projects"
    root = probe_project(projects, "Atlas")
    git("init", "-q", "-b", "main", ".", cwd=root)
    git("remote", "add", "origin", origin, cwd=root)
    result = run(PARK, "--repo", "testorg/atlas", home=home)
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"PROBE park in {root}" in result.stdout


def test_repo_finds_a_member_two_levels_down(home):
    """The estates this standard places are `<projects>/<Project>` and
    `<projects>/<Family>/<Project>`, so the search is two deep."""
    projects = home / "projects"
    probe_family(projects, "InkRouter")
    member = probe_project(projects, "IRRS", at=projects / "InkRouter" / "IRRS")
    git("init", "-q", "-b", "main", ".", cwd=member)
    git("remote", "add", "origin", "https://github.com/TestOrg/IRRS.git",
        cwd=member)
    result = run(PARK, "--repo", "TestOrg/IRRS", home=home)
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"PROBE park in {member}" in result.stdout


def test_repo_with_no_match_refuses_and_names_git_clone(home):
    """RULING 1's other half: only `resume` clones, so this refusal names the
    clone command rather than running one."""
    projects = home / "projects"
    probe_project(projects, "Atlas")
    result = run(PARK, "--repo", "TestOrg/Nothing", home=home)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "no clone under your projects directory has origin TestOrg/Nothing" \
        in result.stderr
    assert "git clone --recurse-submodules https://github.com/TestOrg/Nothing.git" \
        in result.stderr
    assert "it never clones one" in result.stderr


def test_repo_that_is_not_owner_slash_name_is_refused(home):
    result = run(PARK, "--repo", "Atlas", home=home)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "is not <owner/name>" in result.stderr


def test_a_name_and_repo_together_are_refused(home):
    result = run(PARK, "Atlas", "--repo", "TestOrg/Atlas", home=home)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "One estate per run" in result.stderr


@pytest.mark.parametrize("command", [PARK, RESUME], ids=["park", "resume"])
def test_an_unknown_flag_is_refused_and_names_the_double_dash(home, command):
    """The extension has flags these commands have no opinion about, and a
    command that ate them would be a command people stop using the moment the
    extension grows one."""
    result = run(command, "--feature", "001-a", home=home)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "does not know --feature" in result.stderr
    assert "-- --feature" in result.stderr


@pytest.mark.parametrize("command", [PARK, RESUME], ids=["park", "resume"])
def test_help_prints_the_first_usage_line(command):
    result = subprocess.run(["bash", str(command), "--help"],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0].startswith(f"{command.name} [<Name>]")


# ===========================================================================
# park
# ===========================================================================

def test_park_drives_the_holders_make_park_and_args_arrive(estate, home):
    """The whole interface: the holder's `make park` fans out to each member's
    working clone, and `ARGS` reaches the extension in every one of them."""
    result = run(PARK, FAMILY, "--dry-run", "--lane", "xfactory-2", home=home)
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"park: {FAMILY} - the family holder at {estate['holder']}" \
        in result.stdout
    assert "make park ARGS='--dry-run --lane xfactory-2'" in result.stdout
    for name in MEMBERS:
        assert f"--- {name}: make park ---" in result.stdout
        assert f"{name}.sh ran with: --dry-run --lane xfactory-2" \
            in result.stdout


def test_park_passes_extension_flags_after_a_double_dash(estate, home):
    result = run(PARK, FAMILY, "--", "--feature", "001-a", "--no-push",
                 home=home)
    assert result.returncode == 0, result.stderr + result.stdout
    for name in MEMBERS:
        assert f"{name}.sh ran with: --feature 001-a --no-push" in result.stdout


def test_park_reports_an_unpushed_main_commit_and_a_dirty_root(estate, home):
    """What park does NOT carry. Neither is park's to touch: a root is PR-only
    and a pin bump in progress is somebody's unfinished edit."""
    alpha = estate["siblings"]["Alpha"]
    (alpha / "LOCAL.md").write_text("never pushed\n", encoding="utf-8")
    commit_all(alpha, "a commit on main that origin has not seen")
    (estate["holder"] / "PINBUMP.md").write_text("half a bump\n",
                                                 encoding="utf-8")

    result = run(PARK, FAMILY, home=home)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "what park does NOT carry" in result.stdout
    assert f"unpushed main  root    {alpha}" in result.stdout
    assert "1 commit(s) on main that origin has not seen" in result.stdout
    assert "land them as a pull request" in result.stdout
    assert f"uncommitted    holder  {estate['holder']}" in result.stdout
    assert "A pin bump in progress is not" in result.stdout
    assert "ignored files  never travel" in result.stdout
    assert "2 thing(s) above are not park's to carry" in result.stdout


def test_park_says_when_it_left_nothing_behind(estate, home):
    result = run(PARK, FAMILY, home=home)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "nothing else was left behind" in result.stdout
    assert "0 thing(s) above are not park's to carry" in result.stdout


def test_park_never_reads_the_pinned_copy(estate, home):
    """`members/<Project>` is pinned and DETACHED; nobody's work is there, and
    a report that named it would be reporting on the wrong copy."""
    result = run(PARK, FAMILY, home=home)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "members/" not in result.stdout.split("what park does NOT carry")[1]


def test_park_dry_run_creates_and_commits_nothing(estate, home):
    heads = {name: git("rev-parse", "HEAD", cwd=path).stdout
             for name, path in estate["siblings"].items()}
    holder_head = git("rev-parse", "HEAD", cwd=estate["holder"]).stdout
    before = sorted(p.name for p in estate["folder"].iterdir())

    result = run(PARK, FAMILY, "--dry-run", home=home)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "--dry-run: nothing was committed, pushed or recorded." \
        in result.stdout
    for name, path in estate["siblings"].items():
        assert git("rev-parse", "HEAD", cwd=path).stdout == heads[name]
    assert git("rev-parse", "HEAD",
               cwd=estate["holder"]).stdout == holder_head
    assert sorted(p.name for p in estate["folder"].iterdir()) == before


def test_park_in_a_standalone_root_runs_that_roots_verb(estate, home):
    """A member of a family IS a standalone estate when you name it: `park
    --repo <owner>/Alpha` is the member's own root, not the holder's.

    The origin is re-spelled as the url a real member carries, because a clone
    whose origin is a bare repository ON DISK answers `<Name>` and the
    walk-up but never `--repo`: a filesystem path has a name and no owner, and
    inventing one is what `repo_slug_of` refuses to do.
    """
    git("remote", "set-url", "origin",
        f"https://github.com/{ORG}/Alpha.git", cwd=estate["siblings"]["Alpha"])
    result = run(PARK, "--repo", f"{ORG}/Alpha", home=home)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "the assembly root at" in result.stdout
    assert "Alpha.sh ran with:" in result.stdout
    assert "Bravo.sh ran with:" not in result.stdout


def test_park_passes_the_scripts_exit_code_through(estate, home):
    """A refusal must never read as success. Make flattens the extension's 3
    to its own 2 (#80's Makefile says so at the target); what matters is that
    the run is non-zero and the code is still on screen."""
    write_stub(estate["siblings"]["Alpha"], "park", code=3, label="Alpha")
    result = run(PARK, FAMILY, home=home)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "3" in result.stdout + result.stderr
    assert "`make park` exited" in result.stdout


def test_park_refuses_a_root_with_no_makefile(home):
    projects = home / "projects"
    root = projects / "Atlas"
    root.mkdir(parents=True)
    (root / "project.yaml").write_text(
        PROJECT_YAML.format(id="atlas", name="Atlas", org=ORG),
        encoding="utf-8")
    result = run(PARK, "Atlas", home=home)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "has no Makefile" in result.stderr
    assert "update-shape.py" in result.stderr


# ===========================================================================
# resume — the fresh machine
# ===========================================================================

def test_resume_on_a_fresh_machine_builds_the_whole_estate(remotes, home):
    """The issue's own sentence, end to end and offline: `resume InkRouter` on
    a machine that has none of it — clone the workspace record, write the
    config, clone the holder into `<Family>/<Family>`, bootstrap it, place
    every member beside it, and recreate their features."""
    result = run(RESUME, FAMILY, "--workspace", WORKSPACE_SLUG, home=home,
                 env=offline(remotes))
    assert result.returncode == 0, result.stderr + result.stdout

    config = home / ".agents" / "workspace.yaml"
    assert config.is_file(), result.stdout + result.stderr
    assert config.read_text(encoding="utf-8") == (
        f"repository: {WORKSPACE_SLUG}\npath: ~/projects/wip\n")
    assert (home / "projects" / "wip" / "workspaces" / ORG
            / f"{FAMILY}.yaml").is_file()

    folder = home / "projects" / FAMILY
    holder = folder / FAMILY
    assert (holder / "family.yaml").is_file(), "the holder was not cloned"
    assert (holder / "members" / "Alpha" / ".git").exists(), (
        "the pinned copies came with --recurse-submodules")
    for name in MEMBERS:
        assert (folder / name / ".git").is_dir(), f"{name} is not beside it"
        assert git("rev-parse", "--abbrev-ref", "HEAD",
                   cwd=folder / name).stdout.strip() == "main"
        assert f"{name}.sh ran with:" in result.stdout, (
            "each member's own make resume must have run")
    assert "(b) the layout" in result.stdout
    assert f"holder    {FAMILY}" in result.stdout
    assert "`make resume` exited 0" in result.stdout
    assert "0 refusal(s)" in result.stdout


def test_resume_writes_the_config_only_when_asked_by_name(remotes, home):
    """The only file this standard ever writes outside a repository, and it is
    written only because `--workspace` asked for it."""
    result = run(RESUME, FAMILY, home=home, env=offline(remotes))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "no workspace record is configured" in result.stderr
    assert "--workspace <owner>/<repo>" in result.stderr
    assert not (home / ".agents" / "workspace.yaml").exists()
    assert not (home / "projects" / FAMILY).exists(), "nothing was created"


def test_resume_refuses_to_overwrite_a_config_that_names_another_repository(
        remotes, home):
    config = home / ".agents" / "workspace.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("repository: tester/other\npath: ~/projects/other\n",
                      encoding="utf-8")
    result = run(RESUME, FAMILY, "--workspace", WORKSPACE_SLUG, home=home,
                 env=offline(remotes))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "already names" in result.stderr
    assert "never overwrites one" in result.stderr
    assert config.read_text(encoding="utf-8").startswith(
        "repository: tester/other")


def test_resume_clones_the_workspace_the_config_names(remotes, home):
    """A config that is there and a checkout that is not: the repository comes
    from the config, and no flag is needed."""
    config = home / ".agents" / "workspace.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(f"repository: {WORKSPACE_SLUG}\npath: ~/projects/wip\n",
                      encoding="utf-8")
    result = run(RESUME, FAMILY, home=home, env=offline(remotes))
    assert result.returncode == 0, result.stderr + result.stdout
    assert (home / "projects" / "wip" / "workspaces").is_dir()
    assert (home / "projects" / FAMILY / FAMILY / "family.yaml").is_file()


def test_resume_refuses_when_two_orgs_record_the_same_name(remotes, home):
    """Two projects in two organisations may share a name, so nothing here
    picks one — and `--org` is how the question gets answered."""
    refused = run(RESUME, FAMILY, "--workspace", "tester/twoorgs", home=home,
                  env=offline(remotes))
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert "workspace manifests record 'TestFam'" in refused.stderr
    assert "orga/TestFam.yaml" in refused.stderr
    assert "orgb/TestFam.yaml" in refused.stderr
    assert f"resume {FAMILY} --org <org>" in refused.stderr
    assert not (home / "projects" / FAMILY).exists()

    # The config was written by the run above, so this one needs no flag.
    answered = run(RESUME, FAMILY, "--org", "orgb", home=home,
                   env=offline(remotes))
    assert answered.returncode == 0, answered.stderr + answered.stdout
    assert "org             orgb" in answered.stdout
    assert (home / "projects" / FAMILY / FAMILY / "family.yaml").is_file()


def test_resume_refuses_a_name_no_manifest_records(remotes, home):
    config = home / ".agents" / "workspace.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(f"repository: {WORKSPACE_SLUG}\npath: ~/projects/wip\n",
                      encoding="utf-8")
    result = run(RESUME, "Nowhere", home=home, env=offline(remotes))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "no workspace manifest records 'Nowhere'" in result.stderr
    assert "grep -rn 'id: '" in result.stderr


def test_resume_dry_run_clones_nothing(remotes, home):
    config = home / ".agents" / "workspace.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(f"repository: {WORKSPACE_SLUG}\npath: ~/projects/wip\n",
                      encoding="utf-8")
    result = run(RESUME, FAMILY, "--dry-run", home=home, env=offline(remotes))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "would clone" in result.stdout
    assert "nothing was cloned, pulled, bootstrapped or recreated" \
        in result.stdout
    assert not (home / "projects" / "wip").exists()
    assert not (home / "projects" / FAMILY).exists()


def test_resume_rebuilds_a_standalone_project(remotes, home):
    """One root and no holder: the repository comes from `projects[0]`, the
    folder from its `root:`, and there is no `make siblings` in it at all.

    `resume Alpha` also proves the file lookup: the manifest is `alpha.yaml`,
    named for the project id, while `Alpha` is the folder a person types.
    """
    result = run(RESUME, "Alpha", "--workspace", "tester/solo", home=home,
                 env=offline(remotes))
    assert result.returncode == 0, result.stderr + result.stdout
    root = home / "projects" / "Alpha"
    assert (root / "project.yaml").is_file(), result.stdout + result.stderr
    assert "records         a standalone estate, root repository testorg/Alpha" \
        in result.stdout
    assert "BOOTSTRAP-Alpha ran" in result.stdout
    assert "Alpha.sh ran with:" in result.stdout
    assert "make siblings" not in result.stdout
    assert "root      Alpha" in result.stdout, "the layout table names the root"
    assert not (home / "projects" / FAMILY).exists(), (
        "a standalone resume must not touch the family of the same members")


# ===========================================================================
# resume — the estate that is already here
# ===========================================================================

@pytest.fixture
def behind(estate, home, remotes) -> dict:
    """The estate, one commit behind on the holder and on every sibling.

    `reset --hard HEAD~1` rather than a push to the shared bare remotes: the
    remotes are built once per session, and a test that moved one would decide
    what the next test sees.
    """
    config = home / ".agents" / "workspace.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(f"repository: {WORKSPACE_SLUG}\npath: ~/projects/wip\n",
                      encoding="utf-8")
    git("clone", "-q", str(remotes["workspace"]),
        str(home / "projects" / "wip"), cwd=home)
    for path in (estate["holder"], *estate["siblings"].values()):
        git("reset", "--hard", "-q", "HEAD~1", cwd=path)
    return estate


def test_resume_fast_forwards_the_holder_and_every_sibling(behind, home,
                                                           remotes):
    """RULING 2: a person running `resume` is asking for the estate to be
    current, so each working clone's tracking branch is fast-forwarded — and
    each one's own `make bootstrap` puts its legs at the new pins."""
    heads = {name: git("rev-parse", "HEAD", cwd=path).stdout.strip()
             for name, path in behind["siblings"].items()}
    result = run(RESUME, FAMILY, home=home, env=offline(remotes))
    assert result.returncode == 0, result.stderr + result.stdout
    for name, path in behind["siblings"].items():
        assert git("rev-parse", "HEAD", cwd=path).stdout.strip() != heads[name], (
            f"{name} was not fast-forwarded")
        assert git("rev-parse", "HEAD", cwd=path).stdout.strip() == git(
            "rev-parse", "origin/main", cwd=path).stdout.strip()
        assert f"BOOTSTRAP-{name} ran" in result.stdout
    assert "present         " in result.stdout
    assert "0 refusal(s)" in result.stdout


def test_resume_refuses_a_dirty_sibling_by_name_and_resumes_the_rest(
        behind, home, remotes):
    """RULING 2's other half. Never reset, never stashed, and named — and the
    rest of the estate still comes back."""
    alpha = behind["siblings"]["Alpha"]
    (alpha / "MINE.md").write_text("half a thought\n", encoding="utf-8")
    head = git("rev-parse", "HEAD", cwd=alpha).stdout.strip()

    result = run(RESUME, FAMILY, home=home, env=offline(remotes))
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"REFUSED Alpha: uncommitted changes in {alpha}" in result.stdout
    assert "nothing was reset" in result.stdout
    assert git("rev-parse", "HEAD", cwd=alpha).stdout.strip() == head, (
        "a refused sibling must be exactly where it was")
    assert (alpha / "MINE.md").is_file(), "nothing may be discarded"
    bravo = behind["siblings"]["Bravo"]
    assert git("rev-parse", "HEAD", cwd=bravo).stdout.strip() == git(
        "rev-parse", "origin/main", cwd=bravo).stdout.strip()
    assert "Bravo.sh ran with:" in result.stdout, (
        "one refusal must not stop the members after it")
    assert "1 refusal(s)" in result.stdout


def test_resume_refuses_a_sibling_on_a_feature_branch_by_name(behind, home,
                                                              remotes):
    bravo = behind["siblings"]["Bravo"]
    git("checkout", "-q", "-b", "001-a-feature", cwd=bravo)
    result = run(RESUME, FAMILY, home=home, env=offline(remotes))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "REFUSED Bravo: HEAD is '001-a-feature', not its tracking branch " \
        "'main'" in result.stdout
    assert git("rev-parse", "--abbrev-ref",
               "HEAD", cwd=bravo).stdout.strip() == "001-a-feature"
    assert "Alpha.sh ran with:" in result.stdout


def test_resume_skips_a_member_with_no_working_clone_by_name(behind, home,
                                                            remotes):
    """A skip is not a pass — and `make siblings` is what places one, which is
    exactly what this run does before it reports."""
    rmtree(behind["siblings"]["Alpha"])
    result = run(RESUME, FAMILY, home=home, env=offline(remotes))
    assert result.returncode == 0, result.stderr + result.stdout
    assert (behind["folder"] / "Alpha" / ".git").is_dir(), (
        "`make siblings` must have placed the member back")
    assert "Alpha.sh ran with:" in result.stdout


def test_resume_with_no_name_refreshes_the_estate_around_the_cwd(behind, home,
                                                                 remotes):
    result = run(RESUME, home=home, cwd=behind["holder"], env=offline(remotes))
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"resume: {FAMILY}" in result.stdout
    for name, path in behind["siblings"].items():
        assert git("rev-parse", "HEAD", cwd=path).stdout.strip() == git(
            "rev-parse", "origin/main", cwd=path).stdout.strip(), name


def test_resume_with_no_name_and_no_estate_refuses(home):
    result = run(RESUME, home=home, cwd=home)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "no estate around" in result.stderr
    assert "resume <Name>" in result.stderr


def test_resume_refuses_a_repo_it_cannot_match(home):
    result = run(RESUME, "--repo", "TestOrg/Nothing", home=home)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "no clone under your projects directory has origin" in result.stderr
    assert "resume <Name>" in result.stderr
