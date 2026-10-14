# SPDX-License-Identifier: Apache-2.0
"""The assembly root takes no git template, and a mount must be the pushed leg (#243).

`_commit_the_split` built the assembly root with `git clone`, and `git clone`
copies the operator's template (`init.templateDir`, or `GIT_TEMPLATE_DIR`) into
the new `.git`. A template that holds a NON-BARE store at `modules/spec` and
`modules/code`, as one made by copying a working Triad root's `.git` does,
leaves `.git/modules/spec` and `.git/modules/code` in the "fresh" clone.
`_mount_the_legs` passes `--force` to `git submodule add` (#174, #200), which
REACTIVATES a store that is already there where it would refuse without it, so
each mount took the STRANGER's store and checked out its `HEAD`. `execute`
then exited 0 over a split branch whose two gitlinks were the stranger's
commit, pushed it, and the verification said `adoption verified`: it checked
that each mount path holds a gitlink (`adopt-mount-missing`, #173) and never
which commit the gitlink names. `git clone --recurse-submodules` of the pushed
branch exits 128, for everyone. #229 cured the scaffold's counterpart with
`git init --template=`; this is the clone's.

Two changes, which are not alternatives. The assembly root is cloned with
`--template=` (git's documented way to use none), so the `.git/modules` the
mounts meet is empty: that is the cure, and only it prevents the harm. And the
verification compares each mount's gitlink with the commit `execute` pushed to
that leg and refuses `adopt-mount-commit` when they differ, so a wrong commit
can never read `adoption verified` whatever put it there (a leftover store, a
git that reuses a name differently); it does not undo the push.

What is here:

  * the premise, asked of git: a plain clone under the operator's template
    gets the stranger's store, and `--template=` gets nothing, through either
    way an operator names a template;
  * `execute` end to end under such a template (by configuration, by the
    environment, and with stores that have no `origin`, which died loudly at
    `git remote set-url origin` before) and with none, read from the PUSHED
    split branch: each gitlink is its leg's pushed tip, the work directory's
    own `.git/modules` holds only the two stores the mounts made, and a
    recursive clone under a clean configuration succeeds and validates;
  * the verification on its own, with no template, on commits built by hand
    and on the root a real mount leaves over a planted store, so it does not
    depend on the cure, and through `cmd_execute` with the mount's commit
    swapped after the mount.

Only the end-to-end tests need `git filter-repo`. The verification tests build
their legs by hand, so a machine that has none still runs them. Every
repository and remote is local; no network is used, and the operator's
configuration reaches git through `GIT_CONFIG_GLOBAL`, a file each test
writes, so nothing here reads or writes the global configuration of whoever
runs the suite.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import (ADOPT, FILE_PROTOCOL, REPO, git, make_source_repo,
                      resolve, run_script, write_plan)

sys.path.insert(0, str(REPO / "scripts"))
from shape_materialize import SHAPE_REPOSITORY  # noqa: E402

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

PROJECT = "Northwind"
SPEC, CODE = "spec", "code"
ROLES = (SPEC, CODE)
SOURCE, REMOTES, WORK = "Thing", "remotes", "work"
BRANCH = "adopt/three-repo-shape"
#: The mode `git ls-tree` reports for a gitlink.
GITLINK = "160000"
#: What `execute` prints once every source path is accounted for.
VERIFIED = "adoption verified"
#: A commit no repository here holds: a gitlink records another repository's
#: commit and git never resolves it in the root, so it need exist nowhere.
ELSEWHERE = "2" * 40
#: The three questions `plan` asks about `SYNTHETIC_TREE`, answered as
#: tests/test_adopt_e2e.py answers them.
ANSWERS = (("examples/", SPEC), (".claude/", "root"), ("release.yaml", "root"))
NAMES = {"assembly": PROJECT, SPEC: f"{PROJECT}-{SPEC}",
         CODE: f"{PROJECT}-{CODE}"}
PATHS_FOR = {SPEC: [], CODE: [], "root": ["README.md"], "drop": []}
#: The split commit's own files, as `tests/test_adopt_verify.py` builds them:
#: the shape's manifest and a minimal pin that names a file the commit holds,
#: which #167's check of the shape's files reads out of the split commit.
SPLIT_FILES = {"README.md": "# Thing\n", "project.yaml": "kind: project\n",
               "contracts/shape-pin.yaml":
                   "files:\n  - path: project.yaml\n    sha256: \"0\"\n"}

#: How `adopt-mount-commit` ends, spelled out here rather than read from
#: adopt-project.py, so a change to it fails this file.
MOUNT_COMMIT_DEFECT = (
    "no plan chooses a mount's commit: each leg is mounted from its own work "
    "directory, and a module store already under `.git/modules/<name>`, which "
    "`git submodule add --force` reactivates, is the known way another "
    "repository's commit is mounted instead, so the split itself is wrong: "
    f"do not merge it, and report it to {SHAPE_REPOSITORY}")


def wrong_commit(path: str, role: str, found: str, pushed: str) -> str:
    """The `adopt-mount-commit` finding for the mount at `path`."""
    return (f"FINDING adopt-mount-commit: {path} is a gitlink to "
            f"{found[:12]} in the root tree, where the {role} leg was pushed "
            f"at {pushed[:12]}, so the mount is not the leg this run pushed "
            "and a recursive clone of the split checks out the wrong commit "
            f"or cannot fetch one; {MOUNT_COMMIT_DEFECT}")


@pytest.fixture
def adopter():
    """`adopt-project.py` as a module, to call `_verify` and `cmd_execute`."""
    module_spec = importlib.util.spec_from_file_location("adopt_template",
                                                         ADOPT)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# An operator's git template
# ---------------------------------------------------------------------------


def operator(base: Path, template: Path | None = None,
             via: str = "config") -> dict:
    """The environment of an operator whose template is `template`, named the
    way `via` says: `config` is `init.templateDir`, `env` is
    `GIT_TEMPLATE_DIR`. No `template` is an operator with none.

    `GIT_CONFIG_GLOBAL` (git 2.32) stands in for `~/.gitconfig` for every git
    the run starts. The path is written POSIX-style and quoted, because a
    backslash in a git config value is an escape character.
    """
    base.mkdir(parents=True, exist_ok=True)
    config = base / "gitconfig"
    config.write_bytes(
        f'[init]\n\ttemplateDir = "{template.as_posix()}"\n'.encode()
        if template is not None and via == "config" else b"")
    env = {"GIT_CONFIG_GLOBAL": str(config)}
    if template is not None and via == "env":
        env["GIT_TEMPLATE_DIR"] = str(template)
    return env


def git_under(env: dict, *args: str, cwd: Path) -> str:
    """`git` run under `env` on top of this process's; its stdout, stripped."""
    proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          text=True, check=False, env={**os.environ, **env})
    assert proc.returncode == 0, (f"git {' '.join(args)} in {cwd}:\n"
                                  f"{proc.stderr}{proc.stdout}")
    return proc.stdout.strip()


def plant_module_stores(base: Path, origin: bool = True) -> SimpleNamespace:
    """A git template holding a NON-BARE module store at `modules/spec` and
    `modules/code`, each with a commit of its own: the template an operator
    gets by copying a working Triad root's `.git`. No git command puts a
    `modules/` into a template directory, so the stores are copied in.

    The commit belongs to no leg, so a gitlink that equals it is a mount of
    something `execute` did not build. `origin` gives each store the remote a
    working root's store has; without one, `execute` died at `git remote
    set-url origin` after both legs were pushed (exit 2), which is loud, where
    with one it exited 0. The stranger is made under a configuration of its
    own, so nothing of the operator's, or of whoever runs the suite, reaches
    it. `shutil.copytree`, because git writes object files read-only.
    """
    who = {"GIT_AUTHOR_NAME": "A stranger",
           "GIT_AUTHOR_EMAIL": "stranger@elsewhere.invalid",
           "GIT_COMMITTER_NAME": "A stranger",
           "GIT_COMMITTER_EMAIL": "stranger@elsewhere.invalid"}
    env = {**operator(base / "neutral"), **who}
    stranger, template = base / "stranger", base / "template"
    git_under(env, "init", "-q", "-b", "main", str(stranger), cwd=base)
    git_under(env, "commit", "-q", "--allow-empty", "-m",
              "A commit that belongs to no leg", cwd=stranger)
    if origin:
        git_under(env, "remote", "add", "origin", str(stranger), cwd=stranger)
    planted = git_under(env, "rev-parse", "HEAD", cwd=stranger)
    for name in ROLES:
        shutil.copytree(stranger / ".git", template / "modules" / name)
    return SimpleNamespace(template=template, commit=planted)


def gitlinks(repo: Path, rev: str) -> dict:
    """`{path: commit}` for every gitlink in `rev` of `repo`, read from the
    commit and never from a work tree, where the mount is on the disk
    whatever was committed."""
    listing = git("ls-tree", "-r", "-z", rev, cwd=repo).stdout
    found = {}
    for record in listing.split("\0"):
        if record:
            meta, _, name = record.partition("\t")
            mode, _, commit = meta.split()
            if mode == GITLINK:
                found[name] = commit
    return found


# --- the premise -------------------------------------------------------------


@pytest.mark.parametrize("via", ["config", "env"])
def test_a_plain_clone_takes_the_templates_stores_and_template_none_takes_none(
        tmp_path, via):
    """The premise, asked of git rather than assumed. A plain `git clone` under
    the operator's template copies its `modules/spec` into `.git/modules`, at
    the commit the stranger made, whether the template is named by
    `init.templateDir` or by `GIT_TEMPLATE_DIR`; `--template=`, git's
    documented way to use none, copies nothing under either, which is the
    claim `_commit_the_split`'s clone rests on. If git stops doing the first,
    this fails instead of the tests below quietly no longer running the
    defect."""
    planted = plant_module_stores(tmp_path / "planted")
    env = operator(tmp_path / "operator", planted.template, via)
    source = make_source_repo(tmp_path / SOURCE, tree={"a.txt": "a\n"},
                              edits=())

    git_under(env, *FILE_PROTOCOL, "clone", "-q", str(source),
              str(tmp_path / "plain"), cwd=tmp_path)
    store = tmp_path / "plain" / ".git" / "modules" / SPEC
    assert git_under(env, "--git-dir", str(store), "rev-parse", "HEAD",
                     cwd=tmp_path) == planted.commit

    git_under(env, *FILE_PROTOCOL, "clone", "-q", "--template=", str(source),
              str(tmp_path / "none"), cwd=tmp_path)
    assert not (tmp_path / "none" / ".git" / "modules").exists()


# ---------------------------------------------------------------------------
# `execute`, end to end
# ---------------------------------------------------------------------------

#: `(how the operator names a template, or None; whether the planted stores
#: have an origin)`. THE CONTROL is the same run with no template at all: a
#: green there says the harness works, and that the clone's flag changed
#: nothing it should not.
CASES = [
    pytest.param(("config", True), id="template-by-configuration"),
    pytest.param(("env", True), id="template-by-environment"),
    pytest.param(("config", False), id="template-stores-with-no-origin"),
    pytest.param((None, True), id="control-no-template"),
]


def adopt(base: Path, env: dict) -> SimpleNamespace:
    """`plan`, `check` and `execute` of the standard source into local bare
    remotes under `base`, the last two as the operator `env` describes."""
    source = make_source_repo(base / SOURCE)
    plan = base / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    checked = run_script(ADOPT, "check", "--plan", str(plan), env=env)
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(base / REMOTES),
                        "--work-dir", str(base / WORK), env=env)
    return SimpleNamespace(source=source, checked=checked, result=result,
                           remotes=base / REMOTES,
                           assembly=base / WORK / PROJECT)


def pushed_tip(remotes: Path, role: str) -> str:
    bare = remotes / f"{NAMES[role]}.git"
    return git("--git-dir", str(bare), "rev-parse", "refs/heads/main",
               cwd=remotes).stdout.strip()


@pytest.fixture(scope="module", params=CASES)
def adopted(request, tmp_path_factory) -> SimpleNamespace:
    """One case's adoption, run once and read by every test below."""
    via, origin = request.param
    base = tmp_path_factory.mktemp("clone-template")
    planted = plant_module_stores(base / "planted", origin) if via else None
    env = operator(base / "operator", planted.template if planted else None,
                   via or "config")
    run = adopt(base, env)
    run.planted = planted
    run.clean = operator(base / "clean-operator")
    return run


@needs_filter_repo
def test_check_passes_and_execute_exits_zero_having_accounted_for_every_path(
        adopted):
    assert "plan ok" in adopted.checked.stdout
    assert adopted.checked.returncode == 0, adopted.checked.stderr
    assert adopted.result.returncode == 0, (adopted.result.stderr
                                            + adopted.result.stdout)
    assert VERIFIED in adopted.result.stdout


@needs_filter_repo
def test_each_mount_is_the_commit_pushed_to_its_leg_never_a_planted_store(
        adopted):
    """Read from the split branch `execute` PUSHED, never from the exit code or
    the verification's own line: each gitlink is the tip its own leg was
    pushed at, and no other gitlink is there. The planted commit is named in
    the message because a split that mounted a planted store carries it."""
    found = gitlinks(adopted.source, BRANCH)
    planted = adopted.planted.commit if adopted.planted else "no template"
    assert found == {role: pushed_tip(adopted.remotes, role)
                     for role in ROLES}, (
        f"the template's planted commit was {planted}")
    assert planted not in found.values()


@needs_filter_repo
def test_the_assembly_execute_built_holds_only_the_stores_its_mounts_made(
        adopted):
    """The cause, not only its effect: the root was cloned with no template, so
    `.git/modules` held nothing when the mounts ran, and now holds exactly the
    two stores they made, each at its leg's tip. A planted store is at the
    stranger's commit."""
    modules = adopted.assembly / ".git" / "modules"
    assert sorted(path.name for path in modules.iterdir()) == sorted(ROLES)
    for role in ROLES:
        assert git("--git-dir", str(modules / role), "rev-parse", "HEAD",
                   cwd=adopted.assembly).stdout.strip() \
            == pushed_tip(adopted.remotes, role)


@needs_filter_repo
def test_a_clean_recursive_clone_succeeds_and_the_projects_validators_pass(
        adopted, tmp_path):
    """What the NEXT lines tell the human to run, under a configuration with no
    template, so a failure here is the split's. A split that mounted a planted
    store fails the clone with `Fetched in submodule path '<path>', but it did
    not contain` the planted commit (exit 128). `bootstrap.py` is the last of
    the validators: it places each leg AT its pin, so it fails where a gitlink
    and a pin disagree."""
    clone = tmp_path / PROJECT
    git_under(adopted.clean, *FILE_PROTOCOL, "clone", "-q",
              "--recurse-submodules", "-b", BRANCH, str(adopted.source),
              str(clone), cwd=tmp_path)
    for role in ROLES:
        assert git_under(adopted.clean, "rev-parse", "HEAD", cwd=clone / role) \
            == pushed_tip(adopted.remotes, role)
    for validator, ok in (("validate-manifest.py", "manifest ok"),
                          ("validate-pins.py", "pins ok"),
                          ("bootstrap.py", "bootstrap ok")):
        checked = run_script(clone / "scripts" / validator, cwd=clone,
                             env=adopted.clean)
        assert checked.returncode == 0, (f"{validator}: {checked.stderr}"
                                         f"{checked.stdout}")
        assert ok in checked.stdout, checked.stdout


# ---------------------------------------------------------------------------
# The verification on its own: a mount is the leg this run pushed
# ---------------------------------------------------------------------------


def make_legs(base: Path, advanced: tuple = ()) -> SimpleNamespace:
    """The two legs' work directories, as `_build_the_legs` leaves them: each
    a repository of its own, whose `HEAD` is what was pushed. A leg in
    `advanced` has a second commit after its first, so a gitlink at the first
    is an older commit of the same leg."""
    work = base / WORK
    heads, firsts = {}, {}
    for role in ROLES:
        edits = (("NOTES.md", "later\n", "A later commit"),) \
            if role in advanced else ()
        repo = make_source_repo(work / NAMES[role], tree={"file.txt": role},
                                edits=edits)
        heads[role] = git("rev-parse", "HEAD", cwd=repo).stdout.strip()
        firsts[role] = git("rev-parse", "HEAD~1" if edits else "HEAD",
                           cwd=repo).stdout.strip()
    urls = {role: str(base / REMOTES / f"{NAMES[role]}.git")
            for role in ROLES}
    return SimpleNamespace(work=work, heads=heads, firsts=firsts, urls=urls)


def the_source(base: Path):
    """A one-file source, and its `Source` for `_verify`.

    Its README.md is written with `write_bytes`, as `split_of` writes the
    split's, so the two are ONE blob on every OS, as in
    `tests/test_adopt_verify.py`. `make_source_repo` writes with `write_text`,
    which on Windows ends each line with CRLF, and the split's LF README.md
    was then another blob: `adopt-lost` in every verification here."""
    repo = base / SOURCE
    repo.mkdir(parents=True)
    git("init", "-q", "-b", "main", ".", cwd=repo)
    (repo / "README.md").write_bytes(SPLIT_FILES["README.md"].encode("utf-8"))
    git("add", "-A", "--", ".", cwd=repo)
    git("-c", "user.name=Source Human", "-c", "user.email=human@source.invalid",
        "commit", "-qm", "Initial import", cwd=repo)
    return repo, git("rev-parse", "HEAD", cwd=repo).stdout.strip()


def split_of(root: Path, links: dict | None = None) -> str:
    """The split commit: `SPLIT_FILES` and `links` (a mount path to the commit
    its gitlink names, written with `git update-index --cacheinfo`, which
    resolves nothing) on top of whatever `root` already stages."""
    for name, body in SPLIT_FILES.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body.encode("utf-8"))
    git("add", "-A", "--", ".", cwd=root)
    for path, sha in (links or {}).items():
        git("update-index", "--add", "--cacheinfo", f"{GITLINK},{sha},{path}",
            cwd=root)
    git("-c", "user.name=Test Human", "-c", "user.email=test@invalid.example",
        "commit", "-qm", "The split", cwd=root)
    return git("rev-parse", "HEAD", cwd=root).stdout.strip()


def verify(adopter, capsys, source: tuple, root: Path, legs: SimpleNamespace,
           split: str, mounts: dict) -> tuple:
    """`_verify` of `split`, whose mounts are at `mounts`. `(exit, out, err)`.

    `_verify` names the legs' repositories and the split branch in the way
    out it prints after a finding (#188), so it is given them as `execute`
    has them: each leg's under `REMOTES`, and the source as the assembly's.
    Nothing is pushed to them here."""
    repo, commit = source
    code = adopter._verify(adopter.Source(repo, None, "main", commit), root,
                           legs.work, NAMES, PATHS_FOR, split, mounts[SPEC],
                           mounts[CODE],
                           urls=dict(legs.urls, assembly=str(repo)),
                           branch=BRANCH)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def findings(err: str) -> list[str]:
    return [line for line in err.splitlines() if line.startswith("FINDING")]


DEFAULT_MOUNTS = {SPEC: SPEC, CODE: CODE}
#: Two that are not the defaults, so a check that spelled `spec` and `code`
#: itself instead of reading the plan is caught.
NESTED_MOUNTS = {SPEC: "legs/spec", CODE: "impl/code"}


@pytest.fixture
def swapped(adopter, tmp_path, capsys):
    """A factory: build the source and both legs, the split whose mounts are
    the legs' pushed tips except where `swap` names another commit for a leg
    (a 40-hex commit, or `older` for the leg's first commit), then `_verify`.
    Returns `(exit, out, err, legs)`."""
    def run(swap: dict | None = None, mounts: dict = DEFAULT_MOUNTS,
            advanced: tuple = ()):
        swap = swap or {}
        legs = make_legs(tmp_path, advanced)
        named = {role: legs.firsts[role] if swap.get(role) == "older"
                 else swap.get(role, legs.heads[role]) for role in ROLES}
        root = tmp_path / "assembly"
        root.mkdir()
        git("init", "-q", "-b", "main", ".", cwd=root)
        split = split_of(root, {mounts[role]: named[role] for role in ROLES})
        code, out, err = verify(adopter, capsys, the_source(tmp_path), root,
                                legs, split, mounts)
        return code, out, err, legs

    return run


@pytest.mark.parametrize("mounts", [DEFAULT_MOUNTS, NESTED_MOUNTS],
                         ids=["the-default-paths", "the-plans-own-paths"])
def test_mounts_at_the_pushed_tips_verify(swapped, mounts):
    """The control: each gitlink is its leg's pushed tip, so there is nothing
    to refuse, at the default paths and at the plan's own."""
    code, out, err, _ = swapped(mounts=mounts)
    assert code == 0, err
    assert VERIFIED in out
    assert err == ""


@pytest.mark.parametrize("swap, roles", [
    ({SPEC: ELSEWHERE}, (SPEC,)),
    ({CODE: ELSEWHERE}, (CODE,)),
    ({SPEC: ELSEWHERE, CODE: ELSEWHERE}, (CODE, SPEC)),
], ids=["the-spec-mount", "the-code-mount", "both-mounts"])
@pytest.mark.parametrize("mounts", [DEFAULT_MOUNTS, NESTED_MOUNTS],
                         ids=["the-default-paths", "the-plans-own-paths"])
def test_a_mount_that_names_another_commit_is_refused(swapped, swap, roles,
                                                      mounts):
    """Each swapped mount is one finding of its own, in tree order, naming the
    mount path as the plan spells it, the commit the gitlink names and the one
    its leg was pushed at; the run exits 1 and never says `adoption verified`.
    Nothing else is wrong with the split, so these are all the findings."""
    code, out, err, legs = swapped(swap, mounts)
    assert code == 1
    assert findings(err) == [
        wrong_commit(mounts[role], role, ELSEWHERE, legs.heads[role])
        for role in roles]
    assert VERIFIED not in out
    assert f"{len(roles)} verification finding(s)." in err


def test_a_mount_at_an_older_commit_of_its_own_leg_is_refused(swapped):
    """The comparison is EXACT, not "a commit the leg holds": a mount at the
    leg's first commit, where its second was pushed, is a clone that succeeds
    on the wrong tree, and the pin the split wrote names the pushed one."""
    code, out, err, legs = swapped({SPEC: "older"}, advanced=(SPEC,))
    assert legs.firsts[SPEC] != legs.heads[SPEC]
    assert code == 1
    assert findings(err) == [wrong_commit(SPEC, SPEC, legs.firsts[SPEC],
                                          legs.heads[SPEC])]
    assert VERIFIED not in out


def test_a_missing_mount_is_still_only_the_missing_finding(adopter, tmp_path,
                                                           capsys):
    """`adopt-mount-missing` (#173) is untouched, and the commit is not asked
    about a mount that is not there: one finding, not two."""
    legs = make_legs(tmp_path)
    root = tmp_path / "assembly"
    root.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=root)
    split = split_of(root, {SPEC: legs.heads[SPEC]})

    code, out, err = verify(adopter, capsys, the_source(tmp_path), root, legs,
                            split, DEFAULT_MOUNTS)

    assert code == 1
    assert [line.split(":", 1)[0] for line in findings(err)] == [
        "FINDING adopt-mount-missing"]
    assert VERIFIED not in out


# --- the root a real mount leaves over a planted store -----------------------


@pytest.mark.parametrize("template_none", [False, True],
                         ids=["plain-clone", "clone-with-no-template"])
def test_a_mount_over_a_planted_store_never_verifies_and_over_none_does(
        adopter, tmp_path, capsys, monkeypatch, template_none):
    """What `_commit_the_split` did, step by step and with no `git filter-repo`,
    the real `_mount_the_legs` over a clone made under the operator's
    template. A PLAIN clone leaves the stranger's stores in `.git/modules`, so
    `git submodule add --force` reactivates them: each gitlink is the
    planted commit (asserted, as the defect), and the verification refuses
    both. Cloned with `--template=`, the cure, the same mounts are the legs'
    tips and verify. The first half is the check standing without the cure."""
    planted = plant_module_stores(tmp_path / "planted")
    env = operator(tmp_path / "operator", planted.template)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", env["GIT_CONFIG_GLOBAL"])
    repo, commit = the_source(tmp_path)
    legs = make_legs(tmp_path)
    root = tmp_path / "assembly"
    git(*FILE_PROTOCOL, "clone", "-q", *(["--template="] * template_none),
        str(repo), str(root), cwd=tmp_path)
    assert (root / ".git" / "modules").exists() is not template_none

    adopter._mount_the_legs(
        root, legs.work, NAMES, legs.urls, {SPEC: [], CODE: [], "drop": []},
        SPEC, CODE)
    mounted = {role: git("ls-files", "-s", "--", role, cwd=root)
               .stdout.split()[1] for role in ROLES}
    split = split_of(root)
    code, out, err = verify(adopter, capsys, (repo, commit), root, legs,
                            split, DEFAULT_MOUNTS)

    if template_none:
        assert mounted == legs.heads
        assert code == 0, err
        assert VERIFIED in out
        return
    assert mounted == {role: planted.commit for role in ROLES}, \
        "the mount no longer reactivates a planted store: the premise moved"
    assert code == 1
    assert findings(err) == [
        wrong_commit(role, role, planted.commit, legs.heads[role])
        for role in (CODE, SPEC)]
    assert VERIFIED not in out


# --- `cmd_execute` with the mount's commit swapped after the mount -----------


@needs_filter_repo
def test_execute_exits_one_when_a_mount_is_swapped_after_the_mount(
        adopter, tmp_path, capsys, monkeypatch):
    """The seam `tests/test_adopt_verify.py` uses to run the real `cmd_execute`
    with one step changed: here the real `_mount_the_legs` runs, and the spec
    mount's checkout is then moved to a commit of its own that no leg holds,
    which is what a reactivated store leaves there. The split commit records
    the mount's checked-out `HEAD` (`git add -A` restages every gitlink from
    the work tree, so an index entry swapped by hand would be put back), and
    is pushed, as in the defect. The verification must refuse it: exit 1, the
    finding, no `adoption verified`. It does not depend on the clone's
    `--template=`, which would have kept a planted store out in the first
    place."""
    source = make_source_repo(tmp_path / SOURCE)
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    mount = adopter._mount_the_legs
    moved_to = {}

    def mount_then_swap(assembly, *rest):
        mount(assembly, *rest)
        git("-c", "user.name=A stranger", "-c",
            "user.email=stranger@elsewhere.invalid", "commit", "-q",
            "--allow-empty", "-m", "A commit that belongs to no leg",
            cwd=assembly / SPEC)
        moved_to[SPEC] = git("rev-parse", "HEAD",
                             cwd=assembly / SPEC).stdout.strip()

    monkeypatch.setattr(adopter, "_mount_the_legs", mount_then_swap)

    exit_code = adopter.cmd_execute(Namespace(
        plan=str(plan), source=None, local_remote_dir=tmp_path / REMOTES,
        allow_empty_leg=[], yes=True, work_dir=tmp_path / WORK))

    out, err = capsys.readouterr()
    assert exit_code == 1, out + err
    pushed = pushed_tip(tmp_path / REMOTES, SPEC)
    assert moved_to[SPEC] != pushed
    assert findings(err) == [wrong_commit(SPEC, SPEC, moved_to[SPEC], pushed)]
    assert VERIFIED not in out
    assert gitlinks(source, BRANCH) == {
        SPEC: moved_to[SPEC], CODE: pushed_tip(tmp_path / REMOTES, CODE)}
