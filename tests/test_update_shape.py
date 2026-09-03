# SPDX-License-Identifier: Apache-2.0
"""Re-syncing a project's copied shape files, entirely offline.

THE UPSTREAM IS A CLONE OF THIS REPOSITORY IN A TEMPORARY DIRECTORY, and the
project is scaffolded out of that clone into bare repositories on disk. So
"the upstream moved" is a real commit in a real git repository rather than a
mock, and nothing here touches a network or a real repository — the same rule
the rest of the suite runs under.

Commit A is the clone's HEAD; commit B changes ONE copied template file. Every
verdict this tool can reach is then a state of that pair plus the root's own
bytes: unchanged, upstream-changed, locally-modified, both, and the in-place
adoption case where a file the human merged away has no pin row at all.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

import pytest

from conftest import FILE_PROTOCOL, ORG, REPO, git, run_script

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import file_sha256, load_yaml, tree_digest  # noqa: E402

UPDATE = REPO / "update-shape.py"
PROJECT = "Atlas"

#: The file commit B changes upstream. A COPIED file (`COPIED_VERBATIM`), so
#: it carries a `files:` row in the shape pin; the whole point is that an
#: upstream fix to one of these reaches nobody without this command.
CHANGED = "scripts/validate-manifest.py"
CHANGED_SOURCE = f"templates/assembly-root/{CHANGED}"

#: A second copied file, edited in the PROJECT rather than upstream.
LOCAL = "scripts/bootstrap.py"


@pytest.fixture(scope="module")
def upstream_and_project(tmp_path_factory) -> dict:
    """A clone of this repository at A, a project scaffolded from it, and B."""
    base = tmp_path_factory.mktemp("update-shape")
    upstream = base / "openRepoShape"
    proc = subprocess.run(["git", "clone", "-q", str(REPO), str(upstream)],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    commit_a = git("rev-parse", "HEAD", cwd=upstream).stdout.strip()

    result = run_script(
        upstream / "scaffold-project.py", "--org", ORG, "--project", PROJECT,
        "--elected-by", "Test Human", "--elected-on", "2026-09-02",
        "--local-remote-dir", str(base / "remotes"),
        "--work-dir", str(base / "work"))
    assert result.returncode == 0, result.stderr + result.stdout

    clone = base / "clone" / PROJECT
    proc = subprocess.run(
        ["git", *FILE_PROTOCOL, "clone", "-q", "--recurse-submodules",
         str(base / "remotes" / f"{PROJECT}.git"), str(clone)],
        capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr

    # ---- commit B: one copied template file changes upstream --------------
    source = upstream / CHANGED_SOURCE
    source.write_text(source.read_text(encoding="utf-8")
                      + "\n# An upstream fix that must reach every project.\n",
                      encoding="utf-8")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
        "-m", "Fix the manifest validator", "--", CHANGED_SOURCE, cwd=upstream)
    commit_b = git("rev-parse", "HEAD", cwd=upstream).stdout.strip()
    assert commit_a != commit_b

    return {"upstream": upstream, "clone": clone, "a": commit_a, "b": commit_b}


@pytest.fixture
def root(upstream_and_project, tmp_path):
    """A private, mutable copy of the project as it was scaffolded at A."""
    target = tmp_path / PROJECT
    shutil.copytree(upstream_and_project["clone"], target, symlinks=True)
    return target


def check(root, upstream_and_project, *extra):
    return run_script(UPDATE, "check", "--root", str(root),
                      "--upstream", str(upstream_and_project["upstream"]),
                      *extra)


def apply(root, upstream_and_project, *extra):
    return run_script(UPDATE, "apply", "--root", str(root), "--yes",
                      "--upstream", str(upstream_and_project["upstream"]),
                      "--at", upstream_and_project["b"], *extra)


#: Every verdict `check` can print, in the column it prints them in.
STATES = ("unchanged", "upstream-changed", "locally-modified", "both",
          "already-at-target", "upstream-removed", "unmapped", "copy-missing")


def verdicts(stdout: str) -> dict:
    """`{path: state}` out of the report. The detail lines are parenthesised
    and carry no path, so they cannot be mistaken for a verdict."""
    out = {}
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] in STATES and line.startswith("  "):
            out[parts[1]] = parts[0]
    return out


def pin_rows(root) -> dict:
    pin = load_yaml(root / "contracts" / "shape-pin.yaml")
    return {row["path"]: row["sha256"].lower() for row in pin["files"]}


def validators_are_green(root) -> None:
    for script in ("scripts/validate-pins.py", "scripts/validate-manifest.py",
                   "scripts/bootstrap.py"):
        result = run_script(root / script)
        assert result.returncode == 0, (
            f"{script} is red after the update:\n{result.stdout}{result.stderr}")


# --- check -----------------------------------------------------------------

def test_check_names_the_changed_file_and_calls_the_rest_unchanged(
        root, upstream_and_project):
    """The verdict is per file, and the report is the whole point: a human
    says yes to a named list, not to "an update"."""
    result = check(root, upstream_and_project)
    assert result.returncode == 1, result.stdout + result.stderr
    verdict = verdicts(result.stdout)
    assert verdict[CHANGED] == "upstream-changed"
    assert set(verdict) == set(pin_rows(root)), "every pinned row is reported"
    others = {path: state for path, state in verdict.items() if path != CHANGED}
    assert set(others.values()) == {"unchanged"}, others
    assert upstream_and_project["b"] in result.stdout
    assert "NEXT" in result.stdout


def test_check_at_the_pinned_commit_has_nothing_to_do(root,
                                                      upstream_and_project):
    result = check(root, upstream_and_project, "--at", upstream_and_project["a"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "nothing to do" in result.stdout


def test_a_root_with_no_shape_pin_refuses(tmp_path):
    (tmp_path / "contracts").mkdir()
    result = run_script(UPDATE, "check", "--root", str(tmp_path))
    assert result.returncode == 2
    assert "update-pin-missing" in result.stderr
    assert "adopt-project.py" in result.stderr, (
        "a refusal that does not name the tool that answers it puts the exit "
        "in tribal memory")


# --- apply -----------------------------------------------------------------

def test_apply_copies_repins_and_leaves_every_validator_green(
        root, upstream_and_project):
    """The five hand steps, done once and checked: the bytes, the file row,
    the pin's commit and tree digest, and the manifest's mirror of both."""
    before = (root / LOCAL).read_bytes()
    result = apply(root, upstream_and_project)
    assert result.returncode == 0, result.stdout + result.stderr

    upstream, target = upstream_and_project["upstream"], upstream_and_project["b"]
    expected = subprocess.run(["git", "show", f"{target}:{CHANGED_SOURCE}"],
                              cwd=str(upstream), capture_output=True,
                              check=True).stdout
    assert (root / CHANGED).read_bytes() == expected
    assert (root / LOCAL).read_bytes() == before, "an unchanged copy is untouched"

    pin = load_yaml(root / "contracts" / "shape-pin.yaml")
    assert pin["commit"].lower() == target
    assert pin["digests"]["tree_sha256"].lower() == tree_digest(upstream, target)
    assert pin_rows(root)[CHANGED] == file_sha256(root / CHANGED)

    manifest = load_yaml(root / "project.yaml")
    assert manifest["shape"]["commit"].lower() == target
    assert (manifest["shape"]["digests"]["tree_sha256"].lower()
            == tree_digest(upstream, target))
    assert manifest["legs"][0]["repository"] == f"{ORG}/{PROJECT}", (
        "rewriting the shape block must not disturb the rest of the manifest")
    validators_are_green(root)


def test_apply_on_a_branch_commits_only_what_it_wrote(root,
                                                      upstream_and_project):
    """Explicit pathspecs. A shared checkout is the ordinary case, and a bare
    `git commit` there takes whatever anybody staged."""
    (root / "unrelated.txt").write_text("another session's work\n")
    git("add", "--", "unrelated.txt", cwd=root)
    result = apply(root, upstream_and_project, "--branch", "shape/update-test")
    assert result.returncode == 0, result.stdout + result.stderr
    assert git("rev-parse", "--abbrev-ref", "HEAD",
               cwd=root).stdout.strip() == "shape/update-test"
    committed = set(git("show", "--name-only", "--format=", "HEAD",
                        cwd=root).stdout.split())
    assert committed == {CHANGED, "contracts/shape-pin.yaml", "project.yaml"}
    assert "unrelated.txt" not in committed


def test_apply_without_yes_refuses_where_nobody_can_be_asked(
        root, upstream_and_project):
    result = run_script(UPDATE, "apply", "--root", str(root), "--upstream",
                        str(upstream_and_project["upstream"]),
                        "--at", upstream_and_project["b"])
    assert result.returncode == 2
    assert "update-unconfirmed" in result.stderr
    assert load_yaml(root / "contracts" / "shape-pin.yaml")["commit"].lower() \
        == upstream_and_project["a"]


# --- drift the project introduced ------------------------------------------

def edit_locally(root, rel: str) -> None:
    path = root / rel
    path.write_text(path.read_text(encoding="utf-8")
                    + "\n# This project edited its copy.\n", encoding="utf-8")


def test_a_locally_modified_copy_is_refused_by_name(root,
                                                    upstream_and_project):
    """Re-pinning a local edit would turn today's drift finding into a digest
    that agrees with the fork. That is the one thing the shape pin's header
    forbids, so it takes a human's word."""
    edit_locally(root, LOCAL)
    checked = check(root, upstream_and_project)
    assert checked.returncode == 1
    assert verdicts(checked.stdout)[LOCAL] == "locally-modified"

    result = apply(root, upstream_and_project)
    assert result.returncode == 2
    assert "update-local-drift" in result.stderr
    assert LOCAL in result.stderr
    assert f"--accept-local {LOCAL}" in result.stderr
    pin = load_yaml(root / "contracts" / "shape-pin.yaml")
    assert pin["commit"].lower() == upstream_and_project["a"], (
        "a refused apply writes nothing at all")


def test_accept_local_repins_that_file_from_the_root_bytes(
        root, upstream_and_project):
    edit_locally(root, LOCAL)
    edited = (root / LOCAL).read_bytes()
    result = apply(root, upstream_and_project, "--accept-local", LOCAL)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (root / LOCAL).read_bytes() == edited, "the local bytes are kept"
    assert pin_rows(root)[LOCAL] == file_sha256(root / LOCAL)
    assert pin_rows(root)[CHANGED] == file_sha256(root / CHANGED)
    validators_are_green(root)


def test_accept_local_on_a_path_with_no_row_refuses(root,
                                                    upstream_and_project):
    result = apply(root, upstream_and_project, "--accept-local", "README.md")
    assert result.returncode == 2
    assert "update-accept-local-unknown" in result.stderr


def test_changed_on_both_sides_refuses_and_names_the_file(
        root, upstream_and_project):
    """Two edits to one file is a merge, and a merge is a human's judgement."""
    edit_locally(root, CHANGED)
    checked = check(root, upstream_and_project)
    assert checked.returncode == 1
    assert verdicts(checked.stdout)[CHANGED] == "both"

    for extra in ((), ("--accept-local", CHANGED)):
        result = apply(root, upstream_and_project, *extra)
        assert result.returncode == 2, result.stdout
        assert "update-conflict" in result.stderr
        assert CHANGED in result.stderr
    assert load_yaml(root / "contracts" / "shape-pin.yaml")["commit"].lower() \
        == upstream_and_project["a"]


# --- the in-place adoption case --------------------------------------------

def test_a_file_with_no_pin_row_is_not_a_shape_file(root,
                                                    upstream_and_project):
    """MedxEHR's state, reproduced.

    Adopting in place collides on `Makefile`, `README.md` and `.gitignore`:
    the shape's copies land under `shape/`, a human merges them into the
    project's own files and drops the pin rows for the copies that no longer
    exist. What is left is a root Makefile that is nobody's verbatim copy and
    has no row. This command must not see it, must not re-copy it, and must
    not resurrect its row — re-deriving the file list from this repository's
    copy lists is exactly how it would.
    """
    pin_path = root / "contracts" / "shape-pin.yaml"
    kept, dropping = [], False
    for line in pin_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("  - path: "):
            dropping = line[len("  - path: "):].strip() == "Makefile"
        if dropping and (line.startswith("  - path: ")
                         or line.startswith("    sha256:")):
            continue
        kept.append(line)
    pin_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    merged = "# The project's own Makefile, merged after an adoption.\n"
    (root / "Makefile").write_text(merged, encoding="utf-8")
    assert "Makefile" not in pin_rows(root)

    checked = check(root, upstream_and_project)
    assert checked.returncode == 1
    assert "Makefile" not in checked.stdout

    result = apply(root, upstream_and_project)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (root / "Makefile").read_text(encoding="utf-8") == merged
    assert "Makefile" not in pin_rows(root)
    assert pin_rows(root)[CHANGED] == file_sha256(root / CHANGED)
    validators_are_green(root)


def test_the_collision_dir_agrees_with_adopt_project():
    """`update-shape.py` maps `shape/Makefile` back to the template it came
    from, so its idea of where a collision lands must be the one that puts it
    there. Two spellings of one constant is how the second one goes stale."""
    spellings = {path: [line for line in
                        path.read_text(encoding="utf-8").splitlines()
                        if line.startswith("COLLISION_DIR = ")]
                 for path in (UPDATE, REPO / "adopt-project.py")}
    assert all(len(lines) == 1 for lines in spellings.values()), spellings
    assert len({tuple(lines) for lines in spellings.values()}) == 1, spellings


# --- the bootstrap notice --------------------------------------------------

def test_bootstrap_says_so_when_it_can_tell_offline_that_the_shape_moved(
        root, upstream_and_project):
    """Opt-in, offline, one line, and never a failure."""
    quiet = run_script(root / "scripts" / "bootstrap.py")
    assert quiet.returncode == 0
    assert "the upstream is at" not in quiet.stdout, (
        "with nothing to read, bootstrap says nothing: an absent answer is "
        "not a finding")

    told = run_script(root / "scripts" / "bootstrap.py",
                      env={"SHAPE_UPSTREAM_PATH":
                           str(upstream_and_project["upstream"])})
    assert told.returncode == 0, told.stdout + told.stderr
    assert upstream_and_project["b"][:12] in told.stdout
    assert "update-shape.py check" in told.stdout

    (root / ".shape-upstream-tip").write_text(upstream_and_project["b"] + "\n")
    cached = run_script(root / "scripts" / "bootstrap.py")
    assert cached.returncode == 0
    assert upstream_and_project["b"][:12] in cached.stdout

    (root / ".shape-upstream-tip").write_text(upstream_and_project["a"] + "\n")
    agreed = run_script(root / "scripts" / "bootstrap.py")
    assert agreed.returncode == 0
    assert "the upstream is at" not in agreed.stdout


def test_apply_at_the_pinned_commit_writes_nothing(root, upstream_and_project):
    """A no-op apply must not try to commit an empty change; `--branch` with
    nothing to commit is a git failure, not an answer."""
    result = run_script(UPDATE, "apply", "--root", str(root), "--yes",
                        "--upstream", str(upstream_and_project["upstream"]),
                        "--at", upstream_and_project["a"],
                        "--branch", "shape/noop")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "nothing to do" in result.stdout
    assert git("rev-parse", "--abbrev-ref", "HEAD",
               cwd=root).stdout.strip() == "main"
