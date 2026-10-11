# SPDX-License-Identifier: Apache-2.0
"""Verification passes over the two leg mounts and NO OTHER gitlink (#165).

`_verify` used to skip every gitlink in the root tree. The shape adds exactly
two, the mounts at `spec_path` and `code_path`; any other one is a path like a
blob, and skipping it hid a source submodule the root kept (reported lost),
one the split failed to remove (in a leg AND the root, counted once) and one
nobody asked for (not even counted as added).

EVERY REPOSITORY HERE BUT ONE IS A HAND-MADE COMMIT, its gitlinks written with
`git update-index --cacheinfo 160000,...`, and `_verify` is called directly. No
`git filter-repo` is involved, so the Windows job, which installs none, runs
all of those. The one exception is the run of `execute` at the bottom, which
proves `cmd_execute` hands `_verify` the PLAN'S mount paths: it needs `git
filter-repo` and is skipped without it, as every `execute` test is.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, REPO, git, make_source_repo, resolve,
                      run_script, write_plan)

sys.path.insert(0, str(REPO / "scripts"))
from shape_materialize import SHAPE_REPOSITORY  # noqa: E402

#: The commits the source's and the root's extra gitlinks name. A gitlink
#: records ANOTHER repository's commit and git never resolves it here, so
#: these need exist nowhere: the sha is all that `_verify` compares.
DEPENDENCY = "1" * 40
ELSEWHERE = "2" * 40
SUBMODULE = "upstream/dependency"

NAMES = {"assembly": "Northwind", "spec": "Northwind-spec",
         "code": "Northwind-code"}
SOURCE_FILES = {"README.md": "# Thing\n", "specs/a.md": "# A\n",
                "src/app.py": "VALUE = 1\n"}
#: Each leg holds the source path the plan moved to it, at the same bytes.
LEG_FILES = {"spec": {"specs/a.md": "# A\n"},
             "code": {"src/app.py": "VALUE = 1\n"}}
#: The split commit's own files: the README it kept, and three it ADDED. A
#: real split always carries `contracts/shape-pin.yaml`, and #167's check of
#: the shape's files reads it out of the split commit, so this one carries a
#: minimal pin that names a file the commit holds.
ROOT_FILES = {"README.md": "# Thing\n", "project.yaml": "kind: project\n",
              ".gitmodules": "[submodule \"spec\"]\n",
              "contracts/shape-pin.yaml":
                  "files:\n  - path: project.yaml\n    sha256: \"0\"\n"}
PATHS_FOR = {"spec": ["specs/"], "code": ["src/"], "root": ["README.md"]}
#: Where the plan mounts each leg, unless a test says otherwise.
DEFAULT_MOUNTS = {"spec": "spec", "code": "code"}
#: Two that are NOT the defaults, so a `_verify` or a `cmd_execute` that
#: spelled `spec` and `code` itself instead of reading the plan is caught.
NESTED_MOUNTS = {"spec": "legs/spec", "code": "impl/code"}

#: What both root-tree gitlink findings end with, spelled out here rather than
#: read from adopt-project.py, so a change to it fails this file.
EXIT = ("do not merge this split. Look at legs.spec_path and legs.code_path "
        "first: git records a mount at its path's canonical spelling, so a "
        "value such as `spec/` or `./code` mounts the leg at `spec` or `code` "
        "and leaves nothing at the value as spelled; spell it that way in the "
        "plan and re-run, as below. With both values already canonical, "
        "nothing in the plan does this, so the split itself is wrong: report "
        f"it to {SHAPE_REPOSITORY}")


def commit(repo: Path, files: dict, gitlinks: dict | None = None) -> str:
    """A new repository at `repo` with ONE commit of `files` and `gitlinks`."""
    repo.mkdir(parents=True)
    git("init", "-q", "-b", "main", ".", cwd=repo)
    for name, body in files.items():
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body.encode("utf-8"))
    git("add", "-A", "--", ".", cwd=repo)
    for path, sha in (gitlinks or {}).items():
        git("update-index", "--add", "--cacheinfo", f"160000,{sha},{path}",
            cwd=repo)
    git("-c", "user.name=Test Human", "-c", "user.email=test@invalid.example",
        "commit", "-qm", "One commit", cwd=repo)
    return git("rev-parse", "HEAD", cwd=repo).stdout.strip()


@pytest.fixture
def verify(tmp_path, capsys):
    """A factory: build the source, both legs and the split, then `_verify`.

    `source`, `code` and `root` are the gitlinks each one carries beyond its
    files; `mounts` is where the plan mounts each leg, which is what
    `_verify` is told and where the root gets that leg's gitlink unless
    `mounted_at` names another path for it; `unmount` names a leg whose mount
    gitlink the root does NOT get, and `root_files` adds to the root's files.
    Returns `(exit, out, err)`.
    """
    module_spec = importlib.util.spec_from_file_location("adopt_verify",
                                                         ADOPT)
    adopter = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(adopter)

    def run(source=None, code=None, root=None, unmount=(), root_files=None,
            drop=(), mounts=DEFAULT_MOUNTS, mounted_at=None):
        source_path = tmp_path / "source"
        source_commit = commit(source_path, SOURCE_FILES, source)
        work = tmp_path / "work"
        heads = {role: commit(work / NAMES[role], LEG_FILES[role],
                              code if role == "code" else None)
                 for role in ("spec", "code")}
        links = {(mounted_at or mounts).get(role, mounts[role]): heads[role]
                 for role in heads if role not in unmount}
        split = commit(tmp_path / "assembly",
                       {**ROOT_FILES, **(root_files or {})},
                       {**links, **(root or {})})
        verified = adopter._verify(
            adopter.Source(source_path, None, "main", source_commit),
            tmp_path / "assembly", work, NAMES,
            {**PATHS_FOR, "drop": list(drop)}, split, mounts["spec"],
            mounts["code"])
        captured = capsys.readouterr()
        return verified, captured.out, captured.err

    return run


def row(out: str, leg: str) -> str:
    """The verification table's row for `leg`, stripped."""
    return next(line.strip() for line in out.splitlines()
                if line.strip().startswith(f"{leg} "))


def findings(err: str) -> list[str]:
    """Every `FINDING` line `_verify` wrote, in order."""
    return [line for line in err.splitlines() if line.startswith("FINDING")]


def test_the_two_mounts_are_passed_over_and_every_source_path_counted(verify):
    """The common case: no submodule anywhere but the two the shape adds."""
    verified, out, err = verify()
    assert verified == 0, err
    assert [row(out, leg) for leg in ("spec", "code", "root", "drop")] == [
        "spec       1 of 3 source paths", "code       1 of 3 source paths",
        "root       1 of 3 source paths", "drop       0 of 3 source paths"]
    # project.yaml, the pin and .gitmodules, and NOT the two mounts.
    assert row(out, "added").startswith("added      3 new paths")
    assert "adoption verified" in out
    assert err == ""


def test_a_source_submodule_the_root_keeps_at_its_commit_lands_as_root(
        verify):
    """Same path, same commit: a `root` landing, as a blob would be."""
    verified, out, err = verify(source={SUBMODULE: DEPENDENCY},
                                root={SUBMODULE: DEPENDENCY})
    assert verified == 0, err
    assert row(out, "root") == "root       2 of 4 source paths"
    assert err == ""


def test_a_source_submodule_in_no_place_is_lost(verify):
    verified, _, err = verify(source={SUBMODULE: DEPENDENCY})
    assert verified == 1
    assert findings(err) == [
        f"FINDING adopt-lost: {SUBMODULE} ({DEPENDENCY[:12]}) is in no leg, "
        "not in the root tree, and not listed as drop"]


def test_a_dropped_source_submodule_is_counted_as_dropped(verify):
    verified, out, err = verify(source={SUBMODULE: DEPENDENCY},
                                drop=("upstream/",))
    assert verified == 0, err
    assert row(out, "drop") == "drop       1 of 4 source paths"


def test_a_source_submodule_in_a_leg_and_the_root_is_duplicated(verify):
    """The split failed to remove it: two owners for one submodule."""
    verified, _, err = verify(source={SUBMODULE: DEPENDENCY},
                              code={SUBMODULE: DEPENDENCY},
                              root={SUBMODULE: DEPENDENCY})
    assert verified == 1
    assert findings(err) == [f"FINDING adopt-duplicated: {SUBMODULE} is in "
                             f"code:{DEPENDENCY}, root:{DEPENDENCY}"]


@pytest.mark.parametrize("path, world", [
    ("vendor/extra", {}),
    (SUBMODULE, {"source": {SUBMODULE: DEPENDENCY},
                 "code": {SUBMODULE: DEPENDENCY}}),
], ids=["at-a-path-the-source-never-had",
        "at-the-source-submodule-path-at-another-commit"])
def test_a_gitlink_the_shape_did_not_add_is_a_finding(verify, path, world):
    """Neither a mount nor the source's submodule at its own commit.

    The second case moved the source's submodule to the code leg, so every
    source path is accounted for: only the root's gitlink is wrong, and a
    rule that matched the PATH alone would pass it.
    """
    verified, _, err = verify(root={path: ELSEWHERE}, **world)
    assert verified == 1
    assert findings(err) == [
        f"FINDING adopt-unexpected-gitlink: {path} is a gitlink to "
        f"{ELSEWHERE[:12]} in the root tree, and neither a leg mount as the "
        "plan spells their paths (code, spec) nor the source's own submodule "
        f"at that commit; {EXIT}"]


@pytest.mark.parametrize("root_files, found", [
    (None, "nothing"),
    ({"code": "not a mount\n"}, "a blob (mode 100644)"),
    ({"code/stray.txt": "not a mount\n"}, "a directory"),
], ids=["absent", "a-blob", "a-directory"])
def test_a_mount_path_that_is_not_a_gitlink_is_a_finding(verify, root_files,
                                                         found):
    verified, _, err = verify(unmount=("code",), root_files=root_files)
    assert verified == 1
    assert findings(err) == [
        f"FINDING adopt-mount-missing: the root tree has {found} at code as "
        "the plan spells it, where the gitlink that mounts the code leg "
        f"belongs; {EXIT}"]


def test_the_plans_own_mount_paths_are_the_two_passed_over(verify):
    """`legs/spec` and `impl/code`: the mounts are WHERE THE PLAN SAYS.

    A `_verify` that passed over `spec` and `code` whatever the plan said
    would report both of these gitlinks as unexpected and both of its own
    paths as missing.
    """
    verified, out, err = verify(mounts=NESTED_MOUNTS)
    assert verified == 0, err
    assert [row(out, leg) for leg in ("spec", "code", "root")] == [
        "spec       1 of 3 source paths", "code       1 of 3 source paths",
        "root       1 of 3 source paths"]
    assert row(out, "added").startswith("added      3 new paths")
    assert err == ""


@pytest.mark.parametrize("mounts", [
    {**DEFAULT_MOUNTS, "spec": "spec/"},
    NESTED_MOUNTS,
], ids=["a-spelling-git-canonicalises", "the-default-the-plan-did-not-use"])
def test_a_spec_gitlink_not_where_the_plan_spells_the_mount_is_two_findings(
        verify, tmp_path, mounts):
    """The spec leg's own gitlink sits at `spec`; the plan spells its mount
    another way.

    `spec/` is the case `execute` reaches: `plan --spec-path spec/` writes it,
    and `git submodule add` records the mount at `spec`. Both findings fire,
    and their exit is the closing paragraph's, to fix the plan and re-run.
    `legs/spec` with the gitlink at `spec` is what a `_verify` that knew only
    the default would pass.
    """
    verified, _, err = verify(mounts=mounts, mounted_at={"spec": "spec"})
    head = git("rev-parse", "HEAD",
               cwd=tmp_path / "work" / NAMES["spec"]).stdout.strip()
    assert verified == 1
    assert findings(err) == [
        f"FINDING adopt-unexpected-gitlink: spec is a gitlink to {head[:12]} "
        "in the root tree, and neither a leg mount as the plan spells their "
        f"paths ({mounts['code']}, {mounts['spec']}) nor the source's own "
        f"submodule at that commit; {EXIT}",
        f"FINDING adopt-mount-missing: the root tree has nothing at "
        f"{mounts['spec']} as the plan spells it, where the gitlink that "
        f"mounts the spec leg belongs; {EXIT}"]
    assert err.rstrip("\n").endswith(
        "the exit is to fix the plan and re-run into a fresh "
        "--local-remote-dir or fresh leg repositories, unless a finding "
        "above names another exit.")


#: `execute` REQUIRES `git filter-repo`; without it, the one test below is
#: skipped, as every `execute` test in this suite is.
needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

#: The questions `plan` leaves open on SYNTHETIC_TREE, answered as
#: tests/test_adopt_e2e.py answers them.
ANSWERS = (("examples/", "spec"), (".claude/", "root"),
           ("release.yaml", "root"))


@needs_filter_repo
def test_execute_verifies_the_mounts_where_the_plan_puts_them(tmp_path):
    """`plan --spec-path legs/spec --code-path impl/code`, then `execute`.

    `cmd_execute` must hand `_verify` the PLAN'S two paths: one that passed
    `spec` and `code` would fail this correct adoption on four findings.
    """
    source = make_source_repo(tmp_path / "Thing")
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan,
                         extra=("--spec-path", NESTED_MOUNTS["spec"],
                                "--code-path", NESTED_MOUNTS["code"]))
    assert written.returncode == 0, written.stderr + written.stdout
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stderr
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "adoption verified" in result.stdout
    tree = git("ls-tree", "-r", "adopt/three-repo-shape", cwd=source).stdout
    gitlinks = sorted(line.split("\t", 1)[1] for line in tree.splitlines()
                      if line.startswith("160000 "))
    assert gitlinks == sorted(NESTED_MOUNTS.values())
