# SPDX-License-Identifier: Apache-2.0
"""A `--pin-source` must be a clone's top level (#800).

`declared_pin_values`, which `adopt-project.py plan` and `scaffold-project.py`
share, reads a `--pin`'s digest with `tree_digest` IN the `--pin-source`, and
`git ls-tree -r` there lists only the part of the tree under the folder it
runs in. On main bf1f099b nothing asked whether the path was a clone's top
level: `plan --pin openGlass@<commit> --pin-source glass/sub` recorded the
digest of `sub/` alone, the scaffold's `--dry-run` printed the same, and
`check` recomputed it there and said `plan ok` (#457's L1-82). A folder the
commit does not hold, inside a partial clone, recorded the sha256 of nothing,
and `check` passed it with the partial-clone NOTE (L1-04).

Now git is asked first. A working tree's top level, a linked worktree's
among them, has an empty `rev-parse --show-prefix` outside the git
directory, and a bare clone's git directory is the path itself. Any other
path is `pin-source-not-a-clone`, naming the top level git finds, or saying
that it finds none; `check` asks a recorded path the same question before a
partial clone's NOTE and finds `plan-pin-source-not-a-clone`, which
`execute` refuses before any leg. What a top level digests is unchanged.

NO NETWORK AND NO GITHUB: the product is a local stand-in, and `gh` is the
stub of `test_adopt_pins.py`, which logs each call. No refusal here is
preceded by a `gh` call.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import (ADOPT, ORG, SCAFFOLD, WINDOWS_SKIP, git, planned,
                      refused_before_any_leg, run_script)
from test_adopt_pins import (  # noqa: F401
    ENTRY, PIN_FILE, PLANNED, adopter, check_plan, gh_calls, gh_env,
    read_from, with_pins,
)
from test_pin_source_unreadable import RUNS, adoptable, made, run  # noqa: F401
from repo_shape import Refusal, load_yaml, parse_yaml, tree_digest

NOT_A_CLONE = "pin-source-not-a-clone"
PLAN_NOT_A_CLONE = "plan-pin-source-not-a-clone"
DRY_RUN = "--dry-run"
#: The stand-ins' own names, each used by more than one case below.
GLASS, PARTIAL, BARE = "openGlass", "openGlass-partial", "openGlass.git"

#: What the refusal says to pass where git names no top level to pass.
NO_TOP_LEVEL = ("Remediation: pass --pin-source the top level of a clone of "
                "the pinned product (`git rev-parse --show-toplevel` prints "
                "it in that clone's working tree), or drop --pin-source and "
                "let `gh api` read the forge.")

#: Each `--pin-source` that is no clone's top level, under the stand-ins'
#: folder: `(the path, how the refusal says why, the path that says it)`.
REFUSED = [
    pytest.param(f"{GLASS}/sub", "folder", GLASS, id="a-folder-of-a-clone"),
    pytest.param(f"{PARTIAL}/sub", "folder", PARTIAL,
                 id="a-folder-of-a-partial-clone"),
    pytest.param(f"{GLASS}/untracked", "folder", GLASS,
                 id="an-untracked-folder"),
    pytest.param(f"{PARTIAL}/notaclone", "folder", PARTIAL,
                 id="an-untracked-folder-of-a-partial-clone"),
    pytest.param(f"{BARE}/refs", "bare-folder", BARE,
                 id="a-folder-of-a-bare-clone"),
    pytest.param(f"{GLASS}/.git", "git-directory", f"{GLASS}/.git",
                 id="a-git-directory"),
    pytest.param("plain", "no-clone", None, id="no-clone"),
]
#: Each clone's top level, all of one tree.
TOP_LEVELS = [
    pytest.param(GLASS, id="a-clone"),
    pytest.param(BARE, id="a-bare-clone"),
    pytest.param("openGlass-worktree", id="a-linked-worktree"),
    pytest.param(PARTIAL, id="a-partial-clone"),
]


@pytest.fixture(scope="module")
def stand_ins(tmp_path_factory) -> SimpleNamespace:
    """A stand-in for `openGlass` holding `README.md`, `sub/a.txt` and
    `lib/b.py`, as the issue's `glass` does, with an untracked folder in
    it; a bare clone of it, a linked worktree of it, a clone marked partial
    by its config alone (nothing is fetched) with an untracked folder of
    its own, and a folder that is no clone."""
    base = tmp_path_factory.mktemp("top-level").resolve()
    glass = base / GLASS
    glass.mkdir()
    git("init", "-q", "-b", "main", cwd=glass)
    for name, body in (("README.md", b"# openGlass\n"), ("sub/a.txt", b"a\n"),
                       ("lib/b.py", b"b = 1\n")):
        (glass / name).parent.mkdir(exist_ok=True)
        (glass / name).write_bytes(body)
    git("add", "-A", cwd=glass)
    git("commit", "-qm", "seed", cwd=glass)
    commit = git("rev-parse", "HEAD", cwd=glass).stdout.strip()
    (glass / "untracked").mkdir()
    (glass / "untracked" / "notes.txt").write_bytes(b"not committed\n")
    git("clone", "-q", "--bare", str(glass), str(base / BARE), cwd=base)
    git("worktree", "add", "-q", "--detach", str(base / "openGlass-worktree"),
        commit, cwd=glass)
    partial = base / PARTIAL
    git("clone", "-q", str(glass), str(partial), cwd=base)
    for setting in (("core.repositoryformatversion", "1"),
                    ("extensions.partialClone", "origin"),
                    ("remote.origin.promisor", "true")):
        git("config", *setting, cwd=partial)
    (partial / "notaclone").mkdir()
    (base / "plain").mkdir()
    return SimpleNamespace(base=base, commit=commit,
                           digest=tree_digest(glass, commit))


def why(kind: str, named: str) -> str:
    """How the refusal, and `check`'s finding, say why a path is no clone's
    top level, naming `named`: all of it, or its head where git's own words
    follow (`no-clone`)."""
    return {
        "folder": (f"it is a folder inside the clone at {named}, and a digest "
                   "read there covers only what the commit holds under that "
                   "folder"),
        "bare-folder": f"it is a folder inside the bare clone at {named}",
        "git-directory": (f"it is inside {named}, the git directory of a "
                          "clone, where git finds no top level"),
        "no-clone": "git finds no clone there: ",
    }[kind]


def has_a_top_level(kind: str) -> bool:
    """Whether the refusal names a top level to pass as `--pin-source`."""
    return kind in ("folder", "bare-folder")


def assert_refused(result, stand_ins, where: str, kind: str,
                   named: str | None) -> None:
    """`result` is `pin-source-not-a-clone` for `where`, exit 2: the whole
    refusal, or, where git's own words follow its head, the head and the
    remediation."""
    assert result.returncode == 2, result.stdout + result.stderr
    named = str(stand_ins.base / named) if named else ""
    head = (f"REFUSED {NOT_A_CLONE}: --pin-source {stand_ins.base / where} is "
            f"not a clone's top level: {why(kind, named)}")
    if has_a_top_level(kind):
        assert result.stderr == (
            f"{head}\nRemediation: pass --pin-source {named}, the clone's top "
            "level, where a pin's digest is read over its commit's whole "
            "tree.\n"), result.stderr
    else:
        assert result.stderr.startswith(head), result.stderr
        assert result.stderr.endswith(f"\n{NO_TOP_LEVEL}\n"), result.stderr
        assert result.stderr.count("REFUSED ") == 1, result.stderr


# --- `plan` and the scaffold, `--dry-run` and the real run -------------------

@pytest.mark.parametrize("kind", RUNS)
@pytest.mark.parametrize(("where", "said", "named"), REFUSED)
def test_a_path_that_is_no_clone_s_top_level_is_refused(
        kind, where, said, named, tmp_path, adoptable, stand_ins, gh_env):
    """L1-82 and L1-04, and git's other two answers, through every way in:
    exit 2, the one refusal naming the top level git finds, nothing made,
    and no `gh` call."""
    result = run(kind, tmp_path, adoptable, str(stand_ins.base / where),
                 commit=stand_ins.commit, env=gh_env)
    assert_refused(result, stand_ins, where, said, named)
    assert made(kind, tmp_path) == [], "a refusal comes before anything exists"
    assert gh_calls(gh_env) == ""


@pytest.mark.parametrize("kind", RUNS)
@pytest.mark.parametrize("where", TOP_LEVELS)
def test_a_top_level_is_read_as_it_always_was(kind, where, tmp_path,
                                              adoptable, stand_ins, gh_env):
    """A clone's top level, a bare clone, a linked worktree and a partial
    clone each read the one digest `repo_shape.tree_digest` reads at the
    clone's top level, which is what every one of them read before."""
    result = run(kind, tmp_path, adoptable, str(stand_ins.base / where),
                 commit=stand_ins.commit, env=gh_env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert NOT_A_CLONE not in result.stdout + result.stderr
    digest = stand_ins.digest
    if kind == "adopt-plan":
        pin = load_yaml(tmp_path / "plan.yaml")["pins"][0]
        assert pin["tree_sha256"] == digest
    elif kind == "scaffold-run":
        written = git("show", f"main:{PIN_FILE}",
                      cwd=tmp_path / "remotes" / "MedxGlass.git").stdout
        assert parse_yaml(written)["digests"]["tree_sha256"] == digest
    else:
        assert f"tree {digest[:12]}" in result.stdout, result.stdout
    assert gh_calls(gh_env) == ""


def scaffold_on_github(base: Path, stand_ins, where: str, env: dict):
    """The scaffold's `--dry-run` with no `--local-remote-dir`, which asks
    GitHub about its three repositories once the pins are read."""
    return run_script(SCAFFOLD, "--org", ORG, "--project", "MedxGlass",
                      "--elected-by", "Test Human",
                      "--elected-on", "2026-09-02",
                      "--pin", f"openGlass@{stand_ins.commit}",
                      "--pin-source", str(stand_ins.base / where),
                      "--work-dir", str(base / "work"), DRY_RUN, env=env)


@WINDOWS_SKIP  # the stub `gh` is a `#!` script; Windows executes none
def test_the_scaffold_refuses_before_it_asks_github(tmp_path, stand_ins,
                                                    gh_env):
    """Against GitHub the dry run asks `gh` about its repositories after it
    reads the pins (the control, a top level, does), so the refusal comes
    before any `gh` call."""
    refused = scaffold_on_github(tmp_path, stand_ins, f"{GLASS}/sub", gh_env)
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert refused.stderr.startswith(f"REFUSED {NOT_A_CLONE}: ")
    assert gh_calls(gh_env) == ""
    scaffold_on_github(tmp_path, stand_ins, GLASS, gh_env)
    assert gh_calls(gh_env) != "", "the control never reached GitHub"


@pytest.mark.skipif(os.name == "nt",
                    reason="needs a path holding a control character, which "
                           "a Windows file name cannot hold")
def test_a_path_holding_a_control_character_is_named_spelled(
        tmp_path, adoptable, stand_ins, gh_env):
    """The folder and the top level git finds are each named as Python's
    `repr` spells them, as every `--pin-source` refusal names a path that
    is not printable: no raw ESC, and no line but the tool's own."""
    clone = tmp_path / "gl\x1b[31mass\nREFUSED forged-line: not the tool\r"
    (clone / "sub").mkdir(parents=True)
    git("init", "-q", cwd=clone)
    result = run("scaffold-dry-run", tmp_path, adoptable, str(clone / "sub"),
                 commit=stand_ins.commit, env=gh_env)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "\x1b" not in result.stderr, result.stderr
    assert result.stderr.startswith(
        f"REFUSED {NOT_A_CLONE}: --pin-source {str(clone / 'sub')!r} is not "
        f"a clone's top level: {why('folder', repr(str(clone)))}\n"), \
        result.stderr
    lines = result.stderr.splitlines()
    assert [line for line in lines if line.startswith("REFUSED")] \
        == lines[:1], result.stderr


@pytest.mark.parametrize("tool", [(SCAFFOLD,), (ADOPT, "plan")],
                         ids=["scaffold", "adopt-plan"])
def test_each_tool_names_the_refusal_in_its_help(tool):
    """`--pin-source`'s help names the refusal, as it names the others."""
    result = run_script(*tool, "--help", env={"COLUMNS": "1000"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert re.search(rf"`{NOT_A_CLONE}`", result.stdout), result.stdout


# --- `check` asks a recorded path the same question --------------------------

def recorded_on_main(path: Path, stand_ins) -> str:
    """The digest `plan` on main recorded from `path`: whatever `git
    ls-tree` lists there, or, where git cannot answer, the clone's own."""
    try:
        return tree_digest(path, stand_ins.commit)
    except Refusal:
        return stand_ins.digest


@pytest.mark.parametrize(("where", "said", "named"), REFUSED)
def test_check_finds_a_recorded_path_that_is_no_clone_s_top_level(
        adopter, monkeypatch, source_repo, tmp_path, stand_ins, gh_env,
        where, said, named):
    """A plan `plan` wrote on main from such a path, with the digest it read
    there: `check` passed it, recomputing the same number or, inside a
    partial clone, NOTEing that it did not ask. It is now a finding, asked
    before that NOTE, and `execute` refuses it before any leg."""
    path = stand_ins.base / where
    plan = planned(source_repo, tmp_path, PLANNED)
    with_pins(plan, read_from(path, stand_ins.commit,
                              recorded_on_main(path, stand_ins)))
    checked = check_plan(plan, env=gh_env)
    assert checked.returncode == 1, checked.stdout + checked.stderr
    lines = [line for line in checked.stderr.splitlines()
             if line.startswith("FINDING ")]
    assert len(lines) == 1, checked.stderr
    shown = str(stand_ins.base / named) if named else ""
    assert lines[0].startswith(
        f"FINDING {PLAN_NOT_A_CLONE}: {ENTRY} records that `plan` read its "
        f"digest from {path}, which is not a clone's top level: "
        f"{why(said, shown)}"), lines[0]
    fix = (f"re-run `plan` with `--pin-source {shown}`, its top level."
           if has_a_top_level(said) else "re-run `plan` with `--pin "
           "opensoft/openGlass@<40 hex commit>`, which reads the digest "
           "there (from `--pin-source <clone>` with no network, or `gh "
           "api`) and records both, as `scaffold-project.py --pin` takes "
           "it.")
    assert lines[0].endswith(
        f". `plan` refuses such a --pin-source as `{NOT_A_CLONE}`: {fix}"), \
        lines[0]
    assert f"NOTE {ENTRY}" not in checked.stdout, checked.stdout
    refusal = refused_before_any_leg(adopter, monkeypatch, plan, tmp_path)
    assert refusal.code == PLAN_NOT_A_CLONE
    assert gh_calls(gh_env) == ""


@pytest.mark.parametrize("where", TOP_LEVELS)
def test_check_asks_a_recorded_top_level_as_it_always_did(
        source_repo, tmp_path, stand_ins, gh_env, where):
    """The controls: the digest recomputes at a clone's top level, a bare
    clone's and a linked worktree's, and a partial clone is NOTEd as not
    asked, as before; `check` passes each."""
    path = stand_ins.base / where
    plan = planned(source_repo, tmp_path, PLANNED)
    with_pins(plan, read_from(path, stand_ins.commit, stand_ins.digest))
    checked = check_plan(plan, env=gh_env)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    said = (f"digest NOT rechecked here, nor its `commit:` asked whether it "
            f"names a commit: the clone at {path} is a partial clone"
            if where == PARTIAL else
            f"digest recomputes at {stand_ins.commit[:12]} in the clone "
            f"`plan` read it from, {path}.")
    assert f"NOTE {ENTRY}: {said}" in checked.stdout, checked.stdout
    assert gh_calls(gh_env) == ""
