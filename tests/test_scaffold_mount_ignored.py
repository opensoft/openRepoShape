# SPDX-License-Identifier: Apache-2.0
"""An ignore rule matching a LEG'S MOUNT PATH must not stop the mount (#229).

`_build_assembly_root` ran `git submodule add` without `--force`, so a leg path
that an ignore rule matches was refused at the mount -- "The following paths
are ignored by one of your .gitignore files" -- AFTER `_create_remotes` and
`_seed_legs` had made all three repositories and pushed both legs. The root is
a fresh `git init` the materializer has just filled, so two sets of rules reach
the mount: the shape's own `.gitignore` (`__pycache__/`, `*.py[cod]`, `.venv/`,
`.DS_Store`), copied into it, and the operator's own excludes (a global
`core.excludesFile`). `--dry-run` asks no ignore rule anything, so it planned a
scaffold the real run could not finish; the run exited 2 with three
repositories and no project, and a corrected re-run was refused as
`scaffold-remote-exists`. It is #174 (`adopt-project.py`, fixed by #200) on the
scaffold side, and the DEFAULT paths fail for an operator whose own excludes
name `spec` or `code`, so no spelling of the invocation avoids it.

The mount now passes `--force`, as adopt's does. A directory-only rule
(`__pycache__/`, `.venv/`) cannot match a path that does not exist yet, so git
passes it before the clone and refuses after it (exit 128); a file rule
(`*.py[cod]`, `.DS_Store`, an operator's `spec`) is caught before the clone
(exit 1). Both kinds are here, the nested spelling of the first, and
`--spec-path` as well as `--code-path`, which is the FIRST mount.

`--force` also turns off two other refusals of git's, which `adopt-project.py`
makes itself first (`_refuse_an_unmountable_path`) and the scaffold does not
need to: a path the index already holds, and a path beyond a symlink or inside
a submodule. The last test pins what is NOT changed: a leg path that is a path
the shape wrote (`README.md`, `scripts`, `contracts`) is still refused at exit
2. It asserts the exit and that no gitlink lands there, never the message, so
it holds both before and after #197 refuses those paths before anything is
made.

Every run is the real `scaffold-project.py` over `--local-remote-dir`: bare
repositories in a temporary directory, no network, and a `gh` on PATH that
fails if it is ever called. The operator's excludes reach git through
`GIT_CONFIG_GLOBAL`, pointed at a file each case writes, so no run reads the
global configuration of whoever runs the suite.
"""

from __future__ import annotations

import os
import stat
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import NamedTuple

import pytest

from conftest import (FILE_PROTOCOL, ORG, SCAFFOLD, git, run_script)
from test_scaffold_ignored_shape_files import excluding, git_under

PROJECT = "Northwind"
SPEC_FLAG, CODE_FLAG = "--spec-path", "--code-path"
DEFAULT_SPEC, DEFAULT_CODE = "spec", "code"
#: The mode `git ls-tree` reports for a gitlink.
GITLINK = "160000"
#: The default paths, under the excludes the issue was reproduced with: an
#: operator whose own global excludes name the two directories.
NAMES_BOTH = b"code\nspec\n"
#: An operator with NO excludes that still names the file, so git does not fall
#: back to `~/.config/git/ignore` of whoever runs the suite. Only the shape's
#: own `.gitignore` is then in play.
NO_EXCLUDES = b""


class Case(NamedTuple):
    """One real scaffold, which is the slow part, so every assertion about it
    is made over the one run. The paths are spelled as git spells them, with
    `/`, on every OS."""
    excludes: bytes        # the operator's global excludes
    flags: tuple           # what is passed besides the identity
    spec: str              # where the spec leg is mounted
    code: str              # where the code leg is mounted
    hidden: tuple          # the leg paths an ignore rule matches


def case(name: str, *fields):
    return pytest.param(Case(*fields), id=name)


CASES = [
    # THE DEFAULT PATHS: nothing in the invocation is wrong, so the operator's
    # only answer, were this refused, is to edit their own excludes.
    case("default-paths-global-excludes", NAMES_BOTH, (), DEFAULT_SPEC,
         DEFAULT_CODE, (DEFAULT_SPEC, DEFAULT_CODE)),
    # A directory-only rule: git passes the path while it does not exist, the
    # leg is cloned into it, and the second check refuses (exit 128).
    case("code-dir-only-rule", NO_EXCLUDES, (CODE_FLAG, "__pycache__"),
         DEFAULT_SPEC, "__pycache__", ("__pycache__",)),
    case("code-dir-only-rule-nested", NO_EXCLUDES,
         (CODE_FLAG, "legs/__pycache__"), DEFAULT_SPEC, "legs/__pycache__",
         ("legs/__pycache__",)),
    # A file rule: caught before the clone (exit 1).
    case("code-file-rule-glob", NO_EXCLUDES, (CODE_FLAG, "legs.pyc"),
         DEFAULT_SPEC, "legs.pyc", ("legs.pyc",)),
    case("code-file-rule-name", NO_EXCLUDES, (CODE_FLAG, ".DS_Store"),
         DEFAULT_SPEC, ".DS_Store", (".DS_Store",)),
    # The FIRST mount, where nothing is in the index or in `.gitmodules` yet.
    case("spec-dir-only-rule", NO_EXCLUDES, (SPEC_FLAG, "__pycache__"),
         "__pycache__", DEFAULT_CODE, ("__pycache__",)),
    # THE CONTROL: no rule matches, so a green here says the harness works.
    case("control-nothing-ignored", NO_EXCLUDES, (CODE_FLAG, "src"),
         DEFAULT_SPEC, "src", ()),
]

#: Paths the shape itself writes into the assembly root, which a leg must not
#: be mounted at. `--force` changes nothing for them: git refuses each after
#: the clone, with and without it.
SHAPE_PATHS = [
    pytest.param("README.md", id="readme-file"),
    pytest.param("scripts", id="scripts-dir"),
    pytest.param("contracts", id="contracts-dir"),
]


@pytest.fixture(scope="module")
def gh_trap(tmp_path_factory) -> SimpleNamespace:
    """A `gh` on PATH that FAILS if it is called, and the log it would write.

    `--local-remote-dir` never calls `gh`; this is how a test knows. A call
    exits 97, so the scaffold fails as well as the log appearing. The shim is a
    `#!` script, which Windows does not run, so there the trap is not set and
    the guarantee is `--local-remote-dir`'s own (see `WINDOWS_SKIP` in
    `conftest.py`).
    """
    if os.name == "nt":
        return SimpleNamespace(env={}, log=None)
    bin_dir = tmp_path_factory.mktemp("gh-trap")
    log = bin_dir / "gh.log"
    shim = bin_dir / "gh"
    shim.write_text(textwrap.dedent("""\
        #!/bin/sh
        echo "$@" >> "$FAKE_GH_LOG"
        echo "fake gh: a scaffold into --local-remote-dir must not call gh" >&2
        exit 97
        """), encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
    return SimpleNamespace(
        env={"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
             "FAKE_GH_LOG": str(log)},
        log=log)


def scaffold(base: Path, gh_trap, excludes: bytes, *flags: str):
    """One real scaffold of `Northwind` into local bare remotes under `base`,
    run as an operator whose global excludes are `excludes`.

    Returns what a test needs to read the outcome: the process, the
    environment to ask git questions under, and where everything is.
    """
    env = {**excluding(base / "operator", excludes), **gh_trap.env}
    remotes, work = base / "remotes", base / "work"
    result = run_script(
        SCAFFOLD, "--org", ORG, "--project", PROJECT, "--elected-by",
        "Test Human", "--elected-on", "2026-09-02",
        "--local-remote-dir", str(remotes), "--work-dir", str(work), *flags,
        env=env)
    return SimpleNamespace(result=result, env=env, remotes=remotes,
                           work=work / PROJECT)


def gitlinks(bare: Path) -> dict:
    """`{path: commit}` for every gitlink in `bare`'s HEAD, read from the
    PUSHED repository and never from a work tree, where the mount is on the
    disk whatever was committed. Empty for a repository that does not exist
    or has no commit, which is what a root that was never pushed holds."""
    if not bare.is_dir():
        return {}
    head = git("--git-dir", str(bare), "rev-parse", "--verify", "-q", "HEAD",
               cwd=bare, check=False)
    if head.returncode != 0:
        return {}
    listing = git("--git-dir", str(bare), "ls-tree", "-r", "-z", "HEAD",
                  cwd=bare).stdout
    found = {}
    for record in listing.split("\0"):
        if record:
            meta, _, name = record.partition("\t")
            mode, _, commit = meta.split()
            if mode == GITLINK:
                found[name] = commit
    return found


def asked(gh_trap) -> str:
    """What the `gh` trap logged, for the message of a failed assertion."""
    return gh_trap.log.read_text()


def tip(bare: Path) -> str:
    return git("--git-dir", str(bare), "rev-parse", "refs/heads/main",
               cwd=bare).stdout.strip()


def ignored(root: Path, path: str, env: dict) -> bool:
    """Would a plain `git add` in `root` refuse `path`, asked as a DIRECTORY?

    The mount is a directory, and `git check-ignore -- __pycache__` on a path
    that does not exist answers "not ignored" for `__pycache__/` and `.venv/`,
    the rules that fail AFTER the clone: so the slash is not optional.
    `--no-index`, because the mount is tracked now and the index would answer.
    """
    asked = git_under(env, "check-ignore", "-q", "--no-index", "--",
                      f"{path}/", cwd=root, check=False)
    assert asked.returncode in (0, 1), asked.stderr
    return asked.returncode == 0


@pytest.fixture(scope="module", params=CASES)
def mounted(request, gh_trap, tmp_path_factory) -> SimpleNamespace:
    """One case's scaffold, run once and read by every test below."""
    wanted = request.param
    base = tmp_path_factory.mktemp("mount-ignored")
    run = scaffold(base, gh_trap, wanted.excludes, *wanted.flags)
    run.spec, run.code, run.hidden = wanted.spec, wanted.code, wanted.hidden
    run.root = run.remotes / f"{PROJECT}.git"
    return run


# --- the scaffold finishes ---------------------------------------------------

def test_an_ignore_rule_really_matches_the_mount_path(mounted):
    """The premise, asked of git rather than assumed: a rule matches exactly
    the leg paths the case lists as hidden, and none at all in the control. If
    the shape stops ignoring `__pycache__` this test fails, instead of the
    rest of the module quietly no longer running the defect."""
    for path in (mounted.spec, mounted.code):
        assert ignored(mounted.work, path, mounted.env) == (
            path in mounted.hidden), path


def test_the_scaffold_exits_zero_and_never_asks_gh(mounted, gh_trap):
    assert mounted.result.returncode == 0, (mounted.result.stderr
                                            + mounted.result.stdout)
    assert "The following paths are ignored" not in mounted.result.stderr
    if gh_trap.log is not None:
        assert not gh_trap.log.exists(), f"gh was asked: {asked(gh_trap)}"


def test_the_pushed_roots_head_holds_a_gitlink_at_each_leg_path(mounted):
    """Read from the PUSHED root, never from the exit code: a root with no
    commit exits 2 and holds nothing, and a root that mounted the wrong place
    would still exit 0. Each gitlink points at the tip its leg was pushed at,
    and no other gitlink is there."""
    assert gitlinks(mounted.root) == {
        mounted.spec: tip(mounted.remotes / f"{PROJECT}-spec.git"),
        mounted.code: tip(mounted.remotes / f"{PROJECT}-code.git")}


def test_gitmodules_registers_each_mount_once_at_its_canonical_remote(
        mounted, tmp_path):
    """The recorded URL is the leg's own remote and not the scaffold's work
    directory, which is gone by the time anyone clones; and the sections are
    exactly the two mounts, because a path git records differently from how it
    is spelled would add a third (#179)."""
    modules = tmp_path / "gitmodules"
    modules.write_text(git("--git-dir", str(mounted.root), "show",
                           "HEAD:.gitmodules", cwd=tmp_path).stdout,
                       encoding="utf-8")
    listed = git("config", "-f", str(modules), "--list", cwd=tmp_path).stdout
    keys = sorted(line.split("=", 1)[0] for line in listed.splitlines())
    assert keys == sorted(f"submodule.{path}.{field}"
                          for path in (mounted.spec, mounted.code)
                          for field in ("path", "url")), listed
    for path, leg in ((mounted.spec, f"{PROJECT}-spec"),
                      (mounted.code, f"{PROJECT}-code")):
        url = git("config", "-f", str(modules), f"submodule.{path}.url",
                  cwd=tmp_path).stdout.strip()
        remote = mounted.remotes / f"{leg}.git"
        assert Path(url).resolve() == remote.resolve()


def test_a_recursive_clone_checks_out_both_legs_and_its_validators_pass(
        mounted, tmp_path):
    """What a person does next: clone the root recursively, as it was pushed,
    under the operator's own excludes. Both legs are checked out at their
    mounts, and the project's own validators, which resolve each leg at the
    path the manifest names, pass."""
    clone = tmp_path / PROJECT
    git_under(mounted.env, *FILE_PROTOCOL, "clone", "-q",
              "--recurse-submodules", str(mounted.root), str(clone),
              cwd=tmp_path)
    for path in (mounted.spec, mounted.code):
        assert any((clone / path).iterdir()), f"{path} was not checked out"
    for validator, ok in (("validate-manifest.py", "manifest ok"),
                          ("validate-pins.py", "pins ok")):
        checked = run_script(clone / "scripts" / validator, cwd=clone,
                             env=mounted.env)
        assert checked.returncode == 0, (f"{validator}: {checked.stderr}"
                                         f"{checked.stdout}")
        assert ok in checked.stdout, checked.stdout


# --- what `--force` does NOT change ------------------------------------------

@pytest.mark.parametrize("path", SHAPE_PATHS)
def test_a_leg_path_the_shape_wrote_is_still_refused(tmp_path, gh_trap, path):
    """`--force` skips git's own look at the path, so this is the proof it
    opened nothing it should not have: the shape writes `README.md`,
    `scripts/` and `contracts/` into the root before the mounts, a leg cannot
    be mounted over them, and the run still exits 2 with no gitlink at the
    path. The message is not asserted, so the test holds as it is both before
    #197 refuses these paths up front and after (then no remote is made at
    all, and `gitlinks` of the absent root is empty)."""
    run = scaffold(tmp_path, gh_trap, NO_EXCLUDES, CODE_FLAG, path)
    assert run.result.returncode == 2, run.result.stderr + run.result.stdout
    assert path not in gitlinks(run.remotes / f"{PROJECT}.git")
    if gh_trap.log is not None:
        assert not gh_trap.log.exists(), f"gh was asked: {asked(gh_trap)}"
