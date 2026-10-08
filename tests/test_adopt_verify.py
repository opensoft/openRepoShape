# SPDX-License-Identifier: Apache-2.0
"""Verification passes over the two leg mounts and NO OTHER gitlink (#165).

`_verify` used to skip every gitlink in the root tree. The shape adds exactly
two, the mounts at `spec_path` and `code_path`; any other one is a path like a
blob, and skipping it hid a source submodule the root kept (reported lost),
one the split failed to remove (in a leg AND the root, counted once) and one
nobody asked for (not even counted as added).

EVERY REPOSITORY HERE IS ONE HAND-MADE COMMIT, its gitlinks written with `git
update-index --cacheinfo 160000,...`, and `_verify` is called directly. No
`git filter-repo` is involved, so the Windows job, which installs none, runs
the whole file.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from conftest import ADOPT, REPO, git

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
#: The split commit's own files: the README it kept, and two it ADDED.
ROOT_FILES = {"README.md": "# Thing\n", "project.yaml": "kind: project\n",
              ".gitmodules": "[submodule \"spec\"]\n"}
PATHS_FOR = {"spec": ["specs/"], "code": ["src/"], "root": ["README.md"]}


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
    files; `unmount` names a leg whose mount gitlink the root does NOT get,
    and `root_files` adds to the root's files. Returns `(exit, out, err)`.
    """
    module_spec = importlib.util.spec_from_file_location("adopt_verify",
                                                         ADOPT)
    adopter = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(adopter)

    def run(source=None, code=None, root=None, unmount=(), root_files=None,
            drop=()):
        source_path = tmp_path / "source"
        source_commit = commit(source_path, SOURCE_FILES, source)
        work = tmp_path / "work"
        heads = {role: commit(work / NAMES[role], LEG_FILES[role],
                              code if role == "code" else None)
                 for role in ("spec", "code")}
        links = {role: heads[role] for role in heads if role not in unmount}
        split = commit(tmp_path / "assembly",
                       {**ROOT_FILES, **(root_files or {})},
                       {**links, **(root or {})})
        verified = adopter._verify(
            adopter.Source(source_path, None, "main", source_commit),
            tmp_path / "assembly", work, NAMES,
            {**PATHS_FOR, "drop": list(drop)}, split, "spec", "code")
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
    # project.yaml and .gitmodules, and NOT the two mounts.
    assert row(out, "added").startswith("added      2 new paths")
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
        f"{ELSEWHERE[:12]} in the root tree, and neither a leg mount (code, "
        "spec) nor the source's own submodule at that commit; no plan answer "
        "does that, so the split itself is wrong: do not merge it, and report "
        f"it to {SHAPE_REPOSITORY}"]


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
        f"FINDING adopt-mount-missing: the root tree has {found} at code, "
        "where the gitlink that mounts the code leg belongs; no plan answer "
        "does that, so the split itself is wrong: do not merge it, and report "
        f"it to {SHAPE_REPOSITORY}"]
