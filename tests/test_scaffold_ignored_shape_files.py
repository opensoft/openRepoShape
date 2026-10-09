# SPDX-License-Identifier: Apache-2.0
"""An operator's own excludes must not hide the files the shape writes (#175).

`scaffold-project.py` (both legs and the assembly root) and `family.py init`
staged their first commit with `git add -A -- .`, which honours a global
`core.excludesFile` and `.git/info/exclude`. On a machine whose excludes say
`.*`, `contracts/` and `scripts/`, the scaffold exited 0 with an assembly root
whose first commit held no `.gitattributes`, `.github/`, `.gitignore` and
nothing under `contracts/` or `scripts/` -- `contracts/shape-pin.yaml`
included -- so the new project's first `make bootstrap` failed. It is the
scaffold side of #167, with the same fix: `-A`, then `git add -f` over exactly
the paths the materializer wrote (`shape_materialize.stage_written`).

Three groups: the scaffold and the family holder end to end under those
excludes; a file nobody asked the shape to write staying out; and the helper
itself, under an `info/exclude` rule. Every repository is a bare repository in
a temporary directory; no network is used and `gh` is never invoked. The
excludes reach git through `GIT_CONFIG_GLOBAL`, pointed at a file each test
writes, so no run reads the global configuration of whoever runs the suite.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import (FILE_PROTOCOL, ORG, PROJECT, REPO, SCAFFOLD,
                      clear_ambient_pin_sources, git, run_script)

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402
from repo_shape import parse_yaml  # noqa: E402
from shape_materialize import copy_tree, git_init_commit  # noqa: E402

FAMILY = REPO / "scripts" / "family.py"
HOLDER = "InkRouter"
LEGS = (f"{PROJECT}-spec", f"{PROJECT}-code")
PIN = "contracts/shape-pin.yaml"
#: The operator's excludes the issue was reproduced with: every dot-file, and
#: the two directories the shape copies its validators and pins into.
EXCLUDES = b".*\ncontracts/\nscripts/\n"
#: Pinned files those excludes hide, which the first commit used to lack.
HIDDEN_PINNED = {".gitattributes", ".github/workflows/validate.yml",
                 ".gitignore", "contracts/repository-naming.yaml",
                 "scripts/bootstrap.py", "scripts/repo_shape.py"}
#: Files nobody asked the shape to write, each hidden by EXCLUDES.
STRAY = {".env": "TOKEN=not-for-the-commit\n",
         "scripts/stray.py": "print('not the shape')\n"}


def excluding(base: Path) -> dict:
    """The environment of an operator whose GLOBAL excludes are EXCLUDES.

    `GIT_CONFIG_GLOBAL` (git 2.32) stands in for `~/.gitconfig` for every git
    the run starts. The path is written POSIX-style and quoted, because a
    backslash in a git config value is an escape character, and the bytes are
    written as they are, because a CRLF would be part of every pattern.
    """
    excludes = base / "excludes"
    excludes.write_bytes(EXCLUDES)
    config = base / "gitconfig"
    config.write_bytes(
        f'[core]\n\texcludesFile = "{excludes.as_posix()}"\n'.encode())
    return {"GIT_CONFIG_GLOBAL": str(config)}


def git_under(env: dict, *args: str, cwd: Path,
              check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          text=True, check=False, env={**os.environ, **env})
    if check:
        assert proc.returncode == 0, (f"git {' '.join(args)} in {cwd}:\n"
                                      f"{proc.stderr}{proc.stdout}")
    return proc


def ignored(root: Path, path: str, env: dict) -> bool:
    """Would a plain `git add` in `root` skip `path`? The test's premise."""
    return git_under(env, "check-ignore", "-q", "--no-index", "--", path,
                     cwd=root, check=False).returncode == 0


def committed(bare: Path) -> set:
    return set(git("--git-dir", str(bare), "ls-tree", "-r", "--name-only",
                   "HEAD", cwd=bare).stdout.splitlines())


def pinned(bare: Path) -> list:
    """Every `path:` of the shape pin IN THE COMMIT -- never on the disk, where
    the working tree still holds each file a plain `git add` skipped."""
    shown = git("--git-dir", str(bare), "show", f"HEAD:{PIN}", cwd=bare,
                check=False)
    assert shown.returncode == 0, f"{PIN} is not in {bare.name}'s HEAD"
    paths = [row["path"] for row in parse_yaml(shown.stdout)["files"]]
    assert paths, f"{PIN} names no file, so nothing could be checked"
    return paths


def on_disk(root: Path, skip: tuple = ()) -> set:
    """Every file under `root`, POSIX-spelled, but `.git` and `skip`."""
    found = set()
    for directory, subdirs, files in os.walk(root):
        here = Path(directory).relative_to(root)
        if here == Path("."):
            subdirs[:] = [name for name in subdirs
                          if name not in (".git", *skip)]
        found.update((here / name).as_posix() for name in files)
    return found


def first_commit_only(bare: Path) -> None:
    count = git("--git-dir", str(bare), "rev-list", "--count", "HEAD",
                cwd=bare).stdout.strip()
    assert count == "1", f"{bare.name} has {count} commits, not its first"


def litter(root: Path) -> None:
    for name, body in STRAY.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# The scaffold, end to end, under the excludes
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def excluded_scaffold(tmp_path_factory) -> SimpleNamespace:
    base = tmp_path_factory.mktemp("excluded-scaffold")
    env = excluding(base)
    result = run_script(
        SCAFFOLD, "--org", ORG, "--project", PROJECT,
        "--visibility", "private", "--elected-by", "Test Human",
        "--elected-on", "2026-09-02",
        "--local-remote-dir", str(base / "remotes"),
        "--work-dir", str(base / "work"), env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    return SimpleNamespace(env=env, remotes=base / "remotes",
                           work=base / "work")


def test_every_pinned_file_is_in_the_assembly_roots_first_commit(
        excluded_scaffold):
    bare = excluded_scaffold.remotes / f"{PROJECT}.git"
    first_commit_only(bare)
    paths = pinned(bare)
    work = excluded_scaffold.work / PROJECT
    hidden = {path for path in (*paths, PIN)
              if ignored(work, path, excluded_scaffold.env)}
    assert hidden >= HIDDEN_PINNED | {PIN}, (
        "the excludes no longer hide the shape's files, so this test no "
        f"longer runs the defect: {sorted(hidden)}")
    assert sorted(set(paths) - committed(bare)) == []


def test_the_first_commits_hold_every_file_the_scaffold_wrote(
        excluded_scaffold):
    """Not the pinned files alone: the assembly root's whole tree, the two
    mounts and `.gitmodules` included, and each leg's whole template, its
    `.gitignore` and `.gitkeep` included."""
    work, remotes = excluded_scaffold.work, excluded_scaffold.remotes
    assert committed(remotes / f"{PROJECT}.git") == (
        on_disk(work / PROJECT, skip=("spec", "code")) | {"spec", "code"})
    for leg, template in zip(LEGS, ("spec-root", "code-root")):
        bare = remotes / f"{leg}.git"
        first_commit_only(bare)
        assert ignored(work / leg, ".gitignore", excluded_scaffold.env)
        assert committed(bare) == on_disk(REPO / "templates" / template)


def test_the_scaffold_bootstraps_under_the_same_excludes(excluded_scaffold,
                                                        tmp_path):
    env = excluded_scaffold.env
    clone = tmp_path / PROJECT
    git_under(env, *FILE_PROTOCOL, "clone", "-q", "--recurse-submodules",
              str(excluded_scaffold.remotes / f"{PROJECT}.git"), str(clone),
              cwd=tmp_path)
    result = run_script(clone / "scripts" / "bootstrap.py", cwd=clone, env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "bootstrap ok" in result.stdout


# ---------------------------------------------------------------------------
# The family holder, end to end, under the excludes
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def excluded_family(tmp_path_factory) -> SimpleNamespace:
    base = tmp_path_factory.mktemp("excluded-family")
    env = excluding(base)
    result = run_script(
        FAMILY, "init", "--org", ORG, "--family", HOLDER,
        "--created-by", "Test Human", "--created-on", "2026-09-04",
        "--local-remote-dir", str(base / "remotes"),
        "--work-dir", str(base / "work"), env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    return SimpleNamespace(env=env, bare=base / "remotes" / f"{HOLDER}.git",
                           work=base / "work" / HOLDER)


def test_every_file_the_holder_wrote_is_in_its_first_commit(excluded_family):
    bare, work = excluded_family.bare, excluded_family.work
    first_commit_only(bare)
    paths = pinned(bare)
    hidden = {path for path in (*paths, PIN)
              if ignored(work, path, excluded_family.env)}
    assert hidden >= {".gitattributes", ".gitignore", "scripts/bootstrap.py",
                      PIN}, sorted(hidden)
    assert sorted(set(paths) - committed(bare)) == []
    assert committed(bare) == on_disk(work)


def test_the_holder_bootstraps_under_the_same_excludes(excluded_family,
                                                      tmp_path):
    env = excluded_family.env
    clone = tmp_path / HOLDER
    git_under(env, "clone", "-q", str(excluded_family.bare), str(clone),
              cwd=tmp_path)
    result = run_script(clone / "scripts" / "bootstrap.py", cwd=clone, env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "family bootstrap ok" in result.stdout


# ---------------------------------------------------------------------------
# Only what the shape wrote is forced
# ---------------------------------------------------------------------------


def test_a_stray_file_the_scaffold_did_not_write_stays_out(
        tmp_path, monkeypatch, capsys):
    """The scaffold refuses a work directory that is not empty, so the only
    way an ignored file is on the disk when a root is staged is to arrive
    with the shape's own files: the same names are dropped into all three
    roots the moment each is written, which is where a `-f .` would take
    them."""
    scaffold = load(SCAFFOLD, "scaffold_ignored_shape_files")
    copy, materialize = scaffold.copy_tree, scaffold.materialize_assembly_root

    def copy_then_litter(src, dst, values):
        written = copy(src, dst, values)
        litter(dst)
        return written

    def materialize_then_litter(shape_root, target, values, **options):
        materialized = materialize(shape_root, target, values, **options)
        litter(target)
        return materialized

    monkeypatch.setattr(scaffold, "copy_tree", copy_then_litter)
    monkeypatch.setattr(scaffold, "materialize_assembly_root",
                        materialize_then_litter)
    clear_ambient_pin_sources(monkeypatch)
    for key, value in excluding(tmp_path).items():
        monkeypatch.setenv(key, value)
    remotes, work = tmp_path / "remotes", tmp_path / "work"
    code = scaffold.main([
        "--org", ORG, "--project", PROJECT, "--elected-by", "Test Human",
        "--elected-on", "2026-09-02", "--local-remote-dir", str(remotes),
        "--work-dir", str(work)])

    seen = capsys.readouterr()
    assert code == 0, seen.err + seen.out
    for name in (PROJECT, *LEGS):
        tree = committed(remotes / f"{name}.git")
        assert ".gitignore" in tree, f"{name}: the forced add did not run"
        assert sorted(set(STRAY) & tree) == [], name
        for stray, body in STRAY.items():
            assert (work / name / stray).read_text(encoding="utf-8") == body


def test_a_stray_file_the_family_init_did_not_write_stays_out(
        tmp_path, monkeypatch, capsys):
    family = load(FAMILY, "family_ignored_shape_files")
    materialize = family.materialize_family_root

    def materialize_then_litter(shape_root, target, values):
        materialized = materialize(shape_root, target, values)
        litter(target)
        return materialized

    monkeypatch.setattr(family, "materialize_family_root",
                        materialize_then_litter)
    for key, value in excluding(tmp_path).items():
        monkeypatch.setenv(key, value)
    remotes, work = tmp_path / "remotes", tmp_path / "work"
    code = family.main([
        "init", "--org", ORG, "--family", HOLDER,
        "--created-by", "Test Human", "--created-on", "2026-09-04",
        "--local-remote-dir", str(remotes), "--work-dir", str(work)])

    seen = capsys.readouterr()
    assert code == 0, seen.err + seen.out
    tree = committed(remotes / f"{HOLDER}.git")
    assert {".gitattributes", PIN} <= tree
    assert sorted(set(STRAY) & tree) == []
    assert (work / HOLDER / ".env").is_file()


# ---------------------------------------------------------------------------
# The helper, under an `info/exclude` rule
# ---------------------------------------------------------------------------

#: A leg-like template: one file each `info/exclude` rule below hides, and
#: one that no rule hides.
TEMPLATE = {"README.md": "# The leg\n", ".gitignore": "build/\n",
            ".github/workflows/validate.yml": "on: [push]\n",
            "scripts/tool.py": "VALUE = 1\n", "requirements/.gitkeep": ""}


def test_git_init_commit_forces_what_copy_tree_wrote_past_info_exclude(
        tmp_path, monkeypatch):
    """`info/exclude` is the repository's own ignore file and a plain `git
    add` honours it exactly as it does a global one. The repository is made
    first so the rule is in place before `git_init_commit`'s own `git init`,
    which re-initialises it and keeps the rule; the global configuration is
    an empty file, so nothing but that rule is in play."""
    empty = tmp_path / "gitconfig"
    empty.write_bytes(b"")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    template, work = tmp_path / "template", tmp_path / "work"
    for name, body in TEMPLATE.items():
        (template / name).parent.mkdir(parents=True, exist_ok=True)
        (template / name).write_bytes(body.encode())
    git("init", "-q", "-b", "main", str(work), cwd=tmp_path)
    (work / ".git" / "info").mkdir(exist_ok=True)
    (work / ".git" / "info" / "exclude").write_bytes(b".*\nscripts/\n")

    written = copy_tree(template, work, {})
    litter(work)
    assert sorted(written) == sorted(TEMPLATE)
    for name in (*TEMPLATE, *STRAY):
        if name != "README.md":
            assert ignored(work, name, {}), f"{name} is not hidden"

    head = git_init_commit(work, "Seed the leg\n", "main", written)

    tree = set(git("ls-tree", "-r", "--name-only", head,
                   cwd=work).stdout.splitlines())
    assert tree == set(TEMPLATE)
    for name in STRAY:
        assert (work / name).is_file()


def test_stage_written_forces_exactly_the_list_and_never_the_tree(
        monkeypatch):
    """What reaches `git`: `-A` over the tree, then `-f` over the written
    paths alone -- and with none, no forced add at all, never a `-f .`."""
    calls = []
    monkeypatch.setattr(shape_materialize, "run",
                        lambda args, cwd=None, capture=True: calls.append(args))
    shape_materialize.stage_written(Path("root"), [".gitattributes", PIN])
    shape_materialize.stage_written(Path("root"), [])
    assert calls == [
        ["git", "add", "-A", "--", "."],
        ["git", "add", "-f", "--", ".gitattributes", PIN],
        ["git", "add", "-A", "--", "."],
    ]
