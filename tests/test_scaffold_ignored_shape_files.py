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

Four groups: the scaffold and the family holder end to end under those
excludes; a file nobody asked the shape to write staying out; the helper
itself, under an `info/exclude` rule; and the converse, that forcing what
`copy_tree` wrote must not force an operator's own artifact out of a checkout
of the tool (a locally ignored `.vscode/settings.json` in `templates/`), which
the Codex review of PR #185 found. Every repository is a bare repository in
a temporary directory; no network is used and `gh` is never invoked. The
excludes reach git through `GIT_CONFIG_GLOBAL`, pointed at a file each test
writes, so no run reads the global configuration of whoever runs the suite.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
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


def excluding(base: Path, rules: bytes = EXCLUDES) -> dict:
    """The environment of an operator whose GLOBAL excludes are `rules`.

    `GIT_CONFIG_GLOBAL` (git 2.32) stands in for `~/.gitconfig` for every git
    the run starts. The path is written POSIX-style and quoted, because a
    backslash in a git config value is an escape character, and the bytes are
    written as they are, because a CRLF would be part of every pattern.
    `rules=b""` is an operator with NO excludes that still names the file, so
    git does not fall back to `~/.config/git/ignore` of whoever runs the suite.
    """
    base.mkdir(parents=True, exist_ok=True)
    excludes = base / "excludes"
    excludes.write_bytes(rules)
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


# ---------------------------------------------------------------------------
# A file the tool's own checkout does not track is not a template input
# ---------------------------------------------------------------------------
#
# `copy_tree` walks a template directory of a CHECKOUT, and that checkout is
# somebody's working copy: an editor writes `.vscode/settings.json` into
# `templates/spec-root/`, a test run writes `__pycache__/x.pyc`. Forcing
# whatever `copy_tree` wrote (#175) turned each such file into a commit in a
# new leg and a push (Codex, PR #185), and a `.pyc` into a UTF-8 crash. The
# tests below keep the discriminator honest in both directions: untracked AND
# ignored in the tool's own checkout is skipped; everything else, the tracked
# dot-file a global `.*` hides included, is still copied and still forced.

VALUES = {"PROJECT_NAME": "Atlas"}
#: A spec-leg-like template: its own `.gitignore` hides the editor
#: directories, as `templates/spec-root/.gitignore` does, and `README.md`
#: carries a placeholder so a copy that did not render would show.
SPEC_TEMPLATE = {".gitignore": ".DS_Store\n*.swp\n.idea/\n.vscode/\n",
                 "README.md": "# {{PROJECT_NAME}}\n",
                 "requirements/.gitkeep": ""}
#: What the tool's own `.gitignore` says, `__pycache__/` and `*.py[cod]`.
TOOL_GITIGNORE = "__pycache__/\n*.py[cod]\n.pytest_cache/\n"
#: An editor's file the TEMPLATE's `.gitignore` hides, and a compiled file the
#: TOOL's `.gitignore` hides, which is not UTF-8 and so cannot be read as text.
EDITOR_STRAY = {".vscode/settings.json": b'{"editor.tabSize": 2}\n'}
COMPILED_STRAY = {"__pycache__/x.pyc": b"\xff\xfe\x00\x01 not utf-8 \x80"}
LOCAL_STRAYS = {**EDITOR_STRAY, **COMPILED_STRAY}


def strew(src: Path, strays: dict) -> None:
    """Drop `strays` (name -> bytes) under `src`, as an editor would."""
    for name, body in strays.items():
        target = src / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)


def write_template(src: Path, template: dict) -> None:
    for name, body in template.items():
        (src / name).parent.mkdir(parents=True, exist_ok=True)
        (src / name).write_bytes(body.encode())


def commit_everything(root: Path, env: dict) -> None:
    """`git init`, `add -A` and one commit, under `env` and a fixed identity."""
    who = {"GIT_AUTHOR_NAME": "openRepoShape tests",
           "GIT_AUTHOR_EMAIL": "tests@openreposhape.invalid",
           "GIT_COMMITTER_NAME": "openRepoShape tests",
           "GIT_COMMITTER_EMAIL": "tests@openreposhape.invalid"}
    env = {**env, **who}
    git_under(env, "init", "-q", "-b", "main", str(root), cwd=root.parent)
    git_under(env, "add", "-A", "--", ".", cwd=root)
    git_under(env, "commit", "-q", "-m", "The tool's checkout", cwd=root)


def tracked_under(root: Path, directory: str) -> set:
    """What `root` tracks under `directory`, relative to it."""
    listing = git_under({}, "ls-files", "-z", "--", directory, cwd=root)
    return {name[len(directory) + 1:] for name in listing.stdout.split("\0")
            if name}


@pytest.fixture
def checkout(tmp_path, monkeypatch) -> SimpleNamespace:
    """A fake checkout of the tool: a git repository at the SHAPE ROOT whose
    `templates/spec-root/` holds SPEC_TEMPLATE, committed, under a global
    configuration with no excludes (every later `git` of the test reads it,
    `copy_tree`'s included). `dst` is where a leg would be written."""
    for key, value in excluding(tmp_path / "quiet", rules=b"").items():
        monkeypatch.setenv(key, value)
    root = tmp_path / "shape"
    write_template(root / "templates" / "spec-root", SPEC_TEMPLATE)
    (root / ".gitignore").write_bytes(TOOL_GITIGNORE.encode())
    commit_everything(root, {})
    return SimpleNamespace(root=root, src=root / "templates" / "spec-root",
                           dst=tmp_path / "leg")


def test_a_locally_ignored_stray_in_the_template_is_neither_copied_nor_forced(
        checkout):
    """An editor's `.vscode/settings.json` and a binary `__pycache__/x.pyc`,
    untracked and ignored in the tool's checkout, are not template inputs:
    `copy_tree` writes neither, returns neither and does not die on the
    `.pyc`, so `git add -f` has nothing of the operator's to force (#175, Codex
    review of PR #185). The shape's own files are all still there."""
    strew(checkout.src, LOCAL_STRAYS)
    for name in LOCAL_STRAYS:
        assert ignored(checkout.root, f"templates/spec-root/{name}", {}), (
            f"{name} is not hidden, so this test no longer runs the defect")

    written = copy_tree(checkout.src, checkout.dst, VALUES)

    assert sorted(written) == sorted(SPEC_TEMPLATE)
    assert (checkout.dst / "README.md").read_text(
        encoding="utf-8") == "# Atlas\n"
    for name in LOCAL_STRAYS:
        assert name not in written
        assert not (checkout.dst / name).exists(), name


def test_a_tracked_dot_file_a_global_dot_exclude_hides_is_still_forced(
        checkout, monkeypatch, tmp_path):
    """#175 still holds under the stray filter. The operator's global excludes
    say `.*`; the template's `.gitignore` is TRACKED in the tool's checkout, so
    it is no stray, and `git_init_commit` still commits it past those rules --
    while the strays beside it, hidden by the same rules, stay out."""
    for key, value in excluding(tmp_path / "operator").items():
        monkeypatch.setenv(key, value)
    strew(checkout.src, LOCAL_STRAYS)
    git_under({}, "init", "-q", "-b", "main", str(checkout.dst), cwd=tmp_path)
    assert ignored(checkout.dst, ".gitignore", {}), (
        "the excludes no longer hide the template's `.gitignore`, so this "
        "test no longer runs the #175 defect")

    written = copy_tree(checkout.src, checkout.dst, VALUES)
    head = git_init_commit(checkout.dst, "Seed the leg\n", "main", written)

    assert ".gitignore" in written
    tree = set(git("ls-tree", "-r", "--name-only", head,
                   cwd=checkout.dst).stdout.splitlines())
    assert tree == set(SPEC_TEMPLATE)


def test_an_untracked_template_file_nothing_ignores_is_still_copied(checkout):
    """A template file a developer has added and not committed yet is no
    stray: nothing in the tool's checkout ignores it, so it is copied and
    returned, and a stray beside it is still left out (#175, PR #185)."""
    (checkout.src / "NEW.md").write_text("# New\n", encoding="utf-8")
    strew(checkout.src, EDITOR_STRAY)
    untracked = git_under({}, "ls-files", "--error-unmatch", "--",
                          "templates/spec-root/NEW.md", cwd=checkout.root,
                          check=False)
    assert untracked.returncode != 0, "NEW.md is tracked, so the test is moot"

    written = copy_tree(checkout.src, checkout.dst, VALUES)

    assert sorted(written) == sorted([*SPEC_TEMPLATE, "NEW.md"])
    assert (checkout.dst / "NEW.md").read_text(encoding="utf-8") == "# New\n"
    assert not (checkout.dst / ".vscode").exists()


def test_outside_any_git_work_tree_everything_is_copied(tmp_path,
                                                         monkeypatch):
    """A tarball install has no repository to ask, and `git` says so with an
    exit status rather than a stray list: `copy_tree` neither raises nor
    guesses, and copies every file as it did before the filter, a
    `.vscode/settings.json` included (#175, PR #185). The ceiling keeps `git`
    from finding a repository ABOVE the temporary directory."""
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    src = tmp_path / "tarball" / "templates" / "spec-root"
    write_template(src, SPEC_TEMPLATE)
    strew(src, EDITOR_STRAY)
    asked = git_under({}, "rev-parse", "--show-toplevel", cwd=src, check=False)
    assert asked.returncode != 0, "src is inside a repository after all"

    written = copy_tree(src, tmp_path / "leg", VALUES)

    assert sorted(written) == sorted([*SPEC_TEMPLATE, *EDITOR_STRAY])


def test_inside_a_foreign_repository_everything_is_copied(tmp_path,
                                                           monkeypatch):
    """A tool vendored inside some OTHER repository: the git top level is that
    repository's, not the shape root, and its ignore rules are not this
    tool's to apply, so every file is copied (#175, PR #185). The premise is
    checked: asked from `src`, git WOULD name the `.vscode/settings.json`."""
    for key, value in excluding(tmp_path / "quiet", rules=b"").items():
        monkeypatch.setenv(key, value)
    outer = tmp_path / "outer"
    git_under({}, "init", "-q", "-b", "main", str(outer), cwd=tmp_path)
    (outer / ".gitignore").write_bytes(b".vscode/\n")
    src = outer / "vendor" / "shape" / "templates" / "spec-root"
    write_template(src, SPEC_TEMPLATE)
    strew(src, EDITOR_STRAY)
    top = git_under({}, "rev-parse", "--show-toplevel", cwd=src).stdout.strip()
    assert not os.path.samefile(top, src.parent.parent)
    listed = git_under({}, "ls-files", "-z", "--others", "--ignored",
                       "--exclude-standard", "--", ".", cwd=src).stdout
    assert ".vscode/settings.json" in listed.split("\0")

    written = copy_tree(src, tmp_path / "leg", VALUES)

    assert sorted(written) == sorted([*SPEC_TEMPLATE, *EDITOR_STRAY])


def tool_checkout(base: Path) -> Path:
    """A private copy of this repository's tracked files, `tests/` left out, as
    a git repository of its own: a tool checkout a test may litter without
    touching the shared one, with a real `HEAD` the scaffold can pin."""
    root = base / "tool"
    listing = git("ls-files", "-z", cwd=REPO).stdout
    for name in sorted(name for name in listing.split("\0") if name):
        source = REPO / name
        if name.startswith("tests/") or not source.is_file():
            continue
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, root / name, follow_symlinks=False)
    commit_everything(root, excluding(base / "quiet", rules=b""))
    return root


def test_a_stray_in_the_tools_checkout_stays_out_of_both_new_legs(
        tmp_path, monkeypatch, capsys):
    """End to end, under the operator's `.*` excludes: the scaffold is run
    against a private copy of the tool made a git repository, with an editor
    file and a compiled file littered under BOTH `templates/spec-root/` and
    `templates/code-root/`. Each leg's first commit holds exactly what the
    tool's checkout tracks there, the dot-files the excludes hide included,
    and none of the strays (#175, Codex review of PR #185)."""
    tool = tool_checkout(tmp_path)
    roles = (("spec", "spec-root"), ("code", "code-root"))
    for _, template in roles:
        strew(tool / "templates" / template, LOCAL_STRAYS)
        for name in LOCAL_STRAYS:
            assert ignored(tool, f"templates/{template}/{name}", {}), name
    scaffold = load(SCAFFOLD, "scaffold_stray_templates")
    monkeypatch.setattr(scaffold, "SHAPE_ROOT", tool)
    clear_ambient_pin_sources(monkeypatch)
    for key, value in excluding(tmp_path / "operator").items():
        monkeypatch.setenv(key, value)
    remotes, work = tmp_path / "remotes", tmp_path / "work"

    code = scaffold.main([
        "--org", ORG, "--project", PROJECT, "--elected-by", "Test Human",
        "--elected-on", "2026-09-02", "--local-remote-dir", str(remotes),
        "--work-dir", str(work)])

    seen = capsys.readouterr()
    assert code == 0, seen.err + seen.out
    for leg, (_, template) in zip(LEGS, roles):
        bare = remotes / f"{leg}.git"
        first_commit_only(bare)
        tree = committed(bare)
        assert ".gitignore" in tree, f"{leg}: the forced add did not run"
        assert tree == tracked_under(tool, f"templates/{template}"), leg
        for name in LOCAL_STRAYS:
            assert not (work / leg / name).exists(), f"{leg}: {name} copied"
