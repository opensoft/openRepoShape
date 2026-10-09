# SPDX-License-Identifier: Apache-2.0
"""A leg's mount path is canonical, or `scaffold-project.py` refuses it (#179).

`--spec-path spec/` used to scaffold. Git records the mount at `spec`, but the
scaffold's `git config -f .gitmodules submodule.spec/.url` wrote a SECOND
section literally named `spec/`, so the real `spec` registration kept the
operator's work directory as its URL: exit 0, three remotes pushed, and a
recursive clone of the new project that failed the moment the work directory
was moved or deleted. It is `adopt-project.py`'s #169, in the other tool that
writes `legs.spec_path` and `legs.code_path`.

The scaffold now asks the ONE question adopt asks (`shape_materialize`'s
`leg_path_problems`) before it builds anything, so what is refused here is
refused with the same sentence, and the canonical spelling where one exists.
Every test below runs `scaffold-project.py` with `--local-remote-dir` (no
network, no `gh`) except the one that proves `gh` is never asked, which puts a
fake one on PATH. Nothing needs `git filter-repo`.
"""

from __future__ import annotations

import importlib.util
import os
import stat
import sys
import textwrap
from pathlib import Path

import pytest

from conftest import (ADOPT, FILE_PROTOCOL, ORG, REPO, SCAFFOLD, WINDOWS_SKIP,
                      git, run_script)

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402

CODE_OF_REFUSAL = "REFUSED scaffold-bad-leg-path"

#: What a refusal prints before the canonical spelling, and so what it must
#: NOT print where no spelling exists.
OFFER = "Write '"

SPEC, CODE = "--spec-path", "--code-path"
SLASHED = "spec/"
LEGS_SPEC, LEGS_CODE, IMPL_CODE = "legs/spec", "legs/code", "impl/code"

#: Where a test's scaffold writes, under `tmp_path`: the bare remotes, the
#: tool's work directory, and the temporary directory the tool would otherwise
#: make that work directory in.
REMOTES, WORK, SCRATCH = "remotes", "work", "tmp"

#: Everything but the leg paths and the remotes, the same for every run here.
IDENTITY = ["--org", ORG, "--project", "Northwind", "--elected-by",
            "Test Human", "--elected-on", "2026-09-02"]

#: `(flag, value, canonical spelling)`. The spelling is what the refusal must
#: offer, or None where none exists: an absolute path and a `..` name another
#: place, a Git or Windows name names no place a leg can be mounted at, and
#: picking one for the person is the silent rewrite this refuses.
REFUSED = [
    # Spelled with a slash, a dot or a backslash Git drops on its way in.
    pytest.param(SPEC, SLASHED, "spec", id="trailing-slash"),
    pytest.param(CODE, "./code", "code", id="leading-dot-slash"),
    pytest.param(SPEC, "legs//spec", LEGS_SPEC, id="doubled-slash"),
    pytest.param(CODE, "legs/./code", LEGS_CODE, id="dot-segment"),
    pytest.param(SPEC, "legs\\spec", LEGS_SPEC, id="backslash"),
    # Another place altogether.
    pytest.param(SPEC, "/spec", None, id="absolute"),
    pytest.param(CODE, "../code", None, id="dotdot"),
    # Canonical, and a path a leg cannot be mounted at.
    pytest.param(SPEC, ".git", None, id="dot-git"),
    pytest.param(CODE, "legs/.git", None, id="nested-dot-git"),
    pytest.param(SPEC, ".gitmodules", None, id="dot-gitmodules"),
    pytest.param(SPEC, "CON", None, id="windows-device"),
    pytest.param(CODE, "spec.", None, id="trailing-dot"),
    # Outside the alphabet that may reach a `git` command line: refused by the
    # same helper, and by its code, since the leg paths are asked first.
    pytest.param(SPEC, "spec; rm -rf ~", None, id="shell-metacharacter"),
    pytest.param(CODE, "--upload-pack=x", None, id="git-option"),
]

#: `(spec path, code path)`: two paths that cannot both be mounted.
COLLIDING = [
    pytest.param("mount", "mount", id="equal"),
    pytest.param("legs", LEGS_CODE, id="code-inside-spec"),
    pytest.param(IMPL_CODE, "impl", id="spec-inside-code"),
    pytest.param("Spec", "spec", id="equal-but-case"),
    pytest.param("Legs/spec", "legs", id="nested-but-case"),
]

#: Canonical paths the scaffold must keep scaffolding: the defaults, and a
#: pair that proves a path with a directory in it is fine.
SCAFFOLDS = [
    pytest.param((), ("spec", "code"), id="defaults"),
    pytest.param((SPEC, LEGS_SPEC, CODE, IMPL_CODE), (LEGS_SPEC, IMPL_CODE),
                 id="nested-paths"),
]


def load(name: str, path: Path):
    """A tool loaded as a module, for what it imports and what it says."""
    module_spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def adopter():
    """`adopt-project.py`: the OTHER reader of the rule, so a test can ask it
    for the sentence it would have said."""
    return load("adopt_for_scaffold_leg_paths", ADOPT)


@pytest.fixture(scope="module")
def scaffolder():
    return load("scaffold_for_leg_paths", SCAFFOLD)


def scaffold(tmp_path: Path, *args: str, work: bool = False):
    """One scaffold of `Northwind` into local bare remotes under `tmp_path`.

    Without `work`, no `--work-dir` is given, so the tool would make its own
    in a temporary directory; `TMPDIR` (and Windows' `TEMP` and `TMP`) point
    at an empty `tmp_path/tmp` instead, which is how a test sees whether one
    was made.
    """
    scratch = tmp_path / SCRATCH
    scratch.mkdir(exist_ok=True)
    flags = [*IDENTITY, "--local-remote-dir", str(tmp_path / REMOTES), *args]
    if work:
        flags += ["--work-dir", str(tmp_path / WORK)]
    return run_script(SCAFFOLD, *flags, env={
        "TMPDIR": str(scratch), "TMP": str(scratch), "TEMP": str(scratch)})


def assert_nothing_was_created(tmp_path: Path) -> None:
    """No bare remote, no work directory of the tool's own and none of ours."""
    found = sorted(p.name for p in tmp_path.iterdir())
    assert found == [SCRATCH], f"a refused scaffold created something: {found}"
    assert list((tmp_path / SCRATCH).iterdir()) == [], (
        "a refused scaffold made a temporary work directory")


# --- refused, with nothing created ----------------------------------------

@pytest.mark.parametrize("flag, value, canonical", REFUSED)
def test_a_leg_path_that_cannot_be_mounted_is_refused_before_anything_is_made(
        tmp_path, adopter, flag, value, canonical):
    # `=` form, so a value that begins with `-` reaches the tool as a value
    # and argparse does not take it for another option.
    result = scaffold(tmp_path, f"{flag}={value}")
    assert result.returncode == 2, result.stderr + result.stdout
    assert CODE_OF_REFUSAL in result.stderr
    # THE SAME SENTENCE `plan` says for the same value: one rule, two tools.
    assert adopter.leg_path_problem(flag, value) in result.stderr
    if canonical is None:
        assert OFFER not in result.stderr
    else:
        assert f"{OFFER}{canonical}'." in result.stderr
    assert result.stdout == "", "a plan was printed for a refused scaffold"
    assert_nothing_was_created(tmp_path)


@pytest.mark.parametrize("spec, code", COLLIDING)
def test_two_leg_paths_that_collide_are_refused_before_anything_is_made(
        tmp_path, adopter, spec, code):
    result = scaffold(tmp_path, SPEC, spec, CODE, code)
    assert result.returncode == 2, result.stderr + result.stdout
    assert CODE_OF_REFUSAL in result.stderr
    sentence = " ".join(adopter.leg_path_problems((SPEC, spec), (CODE, code)))
    assert sentence and sentence in result.stderr
    assert result.stdout == ""
    assert_nothing_was_created(tmp_path)


def test_a_default_path_is_one_of_the_two_that_can_collide(tmp_path):
    """`--spec-path code` collides with the DEFAULT code path, which is the
    way a person meets this without ever typing `--code-path`."""
    result = scaffold(tmp_path, SPEC, "code")
    assert result.returncode == 2, result.stderr + result.stdout
    assert CODE_OF_REFUSAL in result.stderr
    assert "--spec-path and --code-path are both 'code'" in result.stderr
    assert_nothing_was_created(tmp_path)


def test_both_bad_paths_are_named_in_one_refusal(tmp_path):
    result = scaffold(tmp_path, SPEC, SLASHED, CODE, "./code")
    assert result.returncode == 2
    assert f"--spec-path is {SLASHED!r}" in result.stderr
    assert "--code-path is './code'" in result.stderr
    assert_nothing_was_created(tmp_path)


def test_a_dry_run_refuses_a_bad_leg_path_as_the_real_run_would(tmp_path):
    """`--dry-run` is a rehearsal: it must not print a plan for a scaffold the
    real run refuses."""
    result = scaffold(tmp_path, "--dry-run", SPEC, SLASHED)
    assert result.returncode == 2, result.stderr + result.stdout
    assert CODE_OF_REFUSAL in result.stderr
    assert "nothing was created" not in result.stdout
    assert_nothing_was_created(tmp_path)


def test_the_repro_of_issue_179_is_refused_and_no_project_exists_to_clone(
        tmp_path):
    """The command from the issue, unchanged. On `main` it exited 0, pushed
    three remotes, and `git clone --recurse-submodules` of the result failed
    once the work directory was moved (`Failed to clone 'spec' a second
    time`). Now it is refused, and there is no `Northwind.git` to clone."""
    result = run_script(
        SCAFFOLD, *IDENTITY, SPEC, SLASHED,
        "--local-remote-dir", str(tmp_path / REMOTES),
        "--work-dir", str(tmp_path / WORK))
    assert result.returncode == 2, result.stderr + result.stdout
    assert f"{OFFER}spec'." in result.stderr
    assert not (tmp_path / REMOTES).exists()
    assert not (tmp_path / WORK).exists()


@WINDOWS_SKIP  # the `gh` below is a `#!` script, which Windows does not run
def test_a_refused_leg_path_never_reaches_gh(tmp_path):
    """Local remotes are the test path; the real one calls `gh repo create`.
    The refusal comes before the first `gh` call, so no repository is created
    on the forge for a project that was never going to scaffold."""
    bin_dir, log = tmp_path / "bin", tmp_path / "gh.log"
    bin_dir.mkdir()
    shim = bin_dir / "gh"
    shim.write_text(textwrap.dedent("""\
        #!/bin/sh
        echo "$@" >> "$FAKE_GH_LOG"
        echo "fake gh: no network here" >&2
        exit 1
        """), encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
    result = run_script(
        SCAFFOLD, *IDENTITY, SPEC, SLASHED, "--work-dir", str(tmp_path / WORK),
        env={"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
             "FAKE_GH_LOG": str(log)})
    assert result.returncode == 2, result.stderr + result.stdout
    assert CODE_OF_REFUSAL in result.stderr
    assert not log.exists(), f"gh was asked: {log.read_text()}"
    assert not (tmp_path / WORK).exists()


# --- still scaffolds ------------------------------------------------------

@pytest.mark.parametrize("args, paths", SCAFFOLDS)
def test_canonical_paths_still_scaffold_and_a_clone_survives_the_work_dir(
        tmp_path, args, paths):
    """The mounts and their `.gitmodules` sections agree, so the new project
    clones recursively with the scaffold's work directory gone."""
    result = scaffold(tmp_path, *args, work=True)
    assert result.returncode == 0, result.stderr + result.stdout

    assembly = tmp_path / REMOTES / "Northwind.git"
    modules = tmp_path / "gitmodules"
    modules.write_text(git("show", "HEAD:.gitmodules", cwd=assembly).stdout,
                       encoding="utf-8")
    listed = git("config", "-f", str(modules), "--list", cwd=tmp_path).stdout
    keys = sorted(line.split("=", 1)[0] for line in listed.splitlines())
    assert keys == sorted(f"submodule.{path}.{field}"
                          for path in paths for field in ("path", "url")), (
        "the registrations are not exactly one per mount: " + listed)
    assert str(tmp_path / WORK) not in listed, (
        "a registration still points at the scaffold's work directory")

    (tmp_path / WORK).rename(tmp_path / "work.moved")
    clone = tmp_path / "clone"
    cloned = git(*FILE_PROTOCOL, "clone", "-q", "--recurse-submodules",
                 str(assembly), str(clone), cwd=tmp_path, check=False)
    assert cloned.returncode == 0, cloned.stderr
    for path in paths:
        assert any((clone / path).iterdir()), f"{path} was not checked out"


# --- one definition, two readers ------------------------------------------

def test_both_tools_ask_one_definition(adopter, scaffolder):
    """Adopt used to carry its own copy of the rule, so the scaffold could not
    ask it; two copies are how the second starts refusing other values."""
    for name in ("leg_path_problem", "leg_path_problems"):
        defined = getattr(shape_materialize, name)
        assert defined.__module__ == "shape_materialize"
        assert getattr(adopter, name) is defined
    # Adopt reads the refusal under its old private name, so its call sites
    # did not have to change; it is still the one function.
    refusal = shape_materialize.refuse_bad_leg_paths
    assert refusal.__module__ == "shape_materialize"
    assert adopter._refuse_bad_leg_paths is refusal
    assert scaffolder.refuse_bad_leg_paths is refusal
