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

import importlib.util
import os
import shlex
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from conftest import (FILE_PROTOCOL, ORG, REPO, WINDOWS_SKIP, git,
                      run_script)
#: The trailer helpers and the two lines a lane's run lands, imported from
#: the file that owns those rules rather than retyped — see
#: `tests/test_commit_trailers.py`.
from test_commit_trailers import LANE, TRAILERS, message_of, trailers_of

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import Refusal, file_sha256, load_yaml, tree_digest  # noqa: E402
#: The exact block `adopt-project.py` appends to an adopted Makefile,
#: imported rather than retyped — see `adopted_root` below, whose whole point
#: is that it cannot drift from what a real adoption writes.
from shape_materialize import (  # noqa: E402
    ADOPT_MAKEFILE_BLOCK, SHAPE_REPOSITORY, readme_shape_lines,
)

UPDATE = REPO / "update-shape.py"
PROJECT = "Atlas"


@pytest.fixture(scope="module")
def update_shape():
    """`update-shape.py` as a module, so `confirm` can be called in-process.

    A hyphenated filename is not importable the ordinary way; this is the
    same `spec_from_file_location` load `test_windows_paths.py` uses for
    `adopt-project.py`. Loading it here executes its own
    `from repo_shape import Refusal`, which resolves to the SAME class object
    imported above — `repo_shape` is cached in `sys.modules` by name, not
    reloaded — so `pytest.raises(Refusal)` catches what this module raises.
    """
    spec = importlib.util.spec_from_file_location("update_shape_entry", UPDATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

#: The file commit B changes upstream. A COPIED file (`COPIED_VERBATIM`), so
#: it carries a `files:` row in the shape pin; the whole point is that an
#: upstream fix to one of these reaches nobody without this command.
CHANGED = "scripts/validate-manifest.py"
CHANGED_SOURCE = f"templates/assembly-root/{CHANGED}"

#: A second copied file, edited in the PROJECT rather than upstream.
LOCAL = "scripts/bootstrap.py"

#: The Makefile: a COPIED_VERBATIM file every scaffolded project already
#: carries a pin row for, and the one an in-place adoption appends
#: `ADOPT_MAKEFILE_BLOCK` to. `adopted_root`, further down, mirrors that
#: append onto an otherwise-ordinary scaffolded project.
MAKEFILE = "Makefile"
MAKEFILE_SOURCE = f"templates/assembly-root/{MAKEFILE}"


def scaffold_upstream_and_project(tmp_path_factory, subdir: str):
    """A fresh clone of this repository at A, and `PROJECT` scaffolded from
    it into a recursive clone of its own — the part `upstream_and_project`
    and `adopted_upstream_and_project` share verbatim. They differ only in
    what commits they make on top afterward, which is why this stops here
    and returns the pieces rather than a finished fixture dict: a shared
    RETURN SHAPE across two fixtures is how the second one quietly drifts
    from the first.
    """
    base = tmp_path_factory.mktemp(subdir)
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
    return base, upstream, commit_a, clone


#: The one line appended to a template source to make it "upstream changed"
#: for `classify()` — shared so `upstream_and_project`'s commit B and
#: `adopted_upstream_and_project`'s commit B' touch `CHANGED_SOURCE` with the
#: exact same bytes rather than two typings of one comment.
UPSTREAM_FIX_LINE = "\n# An upstream fix that must reach every project.\n"


def commit_upstream_changes(upstream, message: str,
                            changes: dict[str, str]) -> str:
    """Append `{source path relative to upstream: text}` to each file and
    commit them together. The one shape both `upstream_and_project`'s
    commit B and `adopted_upstream_and_project`'s commit B' take — append,
    commit with explicit pathspecs, return the new hash — so a third upstream
    commit anywhere in this module reaches for this rather than retyping it.
    """
    for source, text in changes.items():
        path = upstream / source
        path.write_text(path.read_text(encoding="utf-8") + text,
                        encoding="utf-8")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
        "-m", message, "--", *changes, cwd=upstream)
    return git("rev-parse", "HEAD", cwd=upstream).stdout.strip()


@pytest.fixture(scope="module")
def upstream_and_project(tmp_path_factory) -> dict:
    """A clone of this repository at A, a project scaffolded from it, and B."""
    _base, upstream, commit_a, clone = scaffold_upstream_and_project(
        tmp_path_factory, "update-shape")

    # ---- commit B: one copied template file changes upstream --------------
    commit_b = commit_upstream_changes(
        upstream, "Fix the manifest validator",
        {CHANGED_SOURCE: UPSTREAM_FIX_LINE})
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


def next_line_of(stdout: str) -> str:
    """The one `NEXT` line the report ends with, whole.

    Whole, and not a substring match: the property under test is what the
    END of that line is, and a test that searched for `--trailer` anywhere in
    the output would pass just as well if the argument landed in the middle
    of the command.
    """
    lines = [line for line in stdout.splitlines() if line.startswith("NEXT")]
    assert len(lines) == 1, stdout
    return lines[0]


def pin_rows(root) -> dict:
    pin = load_yaml(root / "contracts" / "shape-pin.yaml")
    return {row["path"]: row["sha256"].lower() for row in pin["files"]}


def validators_are_green(root) -> None:
    for script in ("scripts/validate-pins.py", "scripts/validate-manifest.py",
                   "scripts/bootstrap.py"):
        result = run_script(root / script)
        assert result.returncode == 0, (
            f"{script} is red after the update:\n{result.stdout}{result.stderr}")


def assert_refused_and_unpinned(result, root, upstream_and_project,
                                refusal_id: str, *needles: str) -> None:
    """The shape every REFUSED `apply` in this module takes: exit 2, the
    refusal id (and anything else `needles` names) in stderr, and the pin's
    `commit:` untouched — "a refused apply writes nothing at all", repeated
    enough times across the `--branch` postures and the adopted-Makefile
    conflict that a helper is the row's own row, not a fourth copy of it."""
    assert result.returncode == 2, result.stdout
    assert refusal_id in result.stderr
    for needle in needles:
        assert needle in result.stderr
    assert load_yaml(root / "contracts" / "shape-pin.yaml")["commit"].lower() \
        == upstream_and_project["a"], "a refused apply writes nothing at all"


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
    assert "project.yaml" in git("log", "-1", "--format=%B",
                                 cwd=root).stdout


# --- --branch: the three postures (#84) -------------------------------------

def test_branch_onto_the_current_non_tracking_branch_commits_there(
        root, upstream_and_project):
    """The shape a `both` exit leaves a checkout in: a human already checked
    out a branch and committed a hand merge there, so `apply --branch <that
    branch>` must land ON it rather than trying `git checkout -b` a second
    time and finding the branch already exists."""
    git("checkout", "-q", "-b", "shape/already-here", cwd=root)
    result = apply(root, upstream_and_project, "--branch", "shape/already-here")
    assert result.returncode == 0, result.stdout + result.stderr
    assert git("rev-parse", "--abbrev-ref", "HEAD",
               cwd=root).stdout.strip() == "shape/already-here"
    assert "committed on shape/already-here" in result.stdout


def test_branch_naming_an_existing_non_current_branch_refuses_by_name(
        root, upstream_and_project):
    """Committing onto a branch a human already put something on is a
    decision for them, not an assumption this tool makes on their behalf."""
    git("branch", "shape/someone-elses", cwd=root)
    result = apply(root, upstream_and_project,
                   "--branch", "shape/someone-elses")
    assert_refused_and_unpinned(result, root, upstream_and_project,
                                "update-branch-exists", "shape/someone-elses")
    assert git("rev-parse", "--abbrev-ref", "HEAD",
               cwd=root).stdout.strip() == "main", (
        "a refused apply must not leave the checkout on a different branch")


def test_branch_naming_the_tracking_branch_refuses(root, upstream_and_project):
    """`main` is both this root's tracking branch AND its current branch —
    proof the tracking-branch refusal is checked BEFORE the current-branch
    fast path, not after it."""
    result = apply(root, upstream_and_project, "--branch", "main")
    assert_refused_and_unpinned(result, root, upstream_and_project,
                                "update-branch-tracking", "main")


def test_apply_without_yes_refuses_where_nobody_can_be_asked(
        root, upstream_and_project):
    result = run_script(UPDATE, "apply", "--root", str(root), "--upstream",
                        str(upstream_and_project["upstream"]),
                        "--at", upstream_and_project["b"])
    assert result.returncode == 2
    assert "update-unconfirmed" in result.stderr
    assert load_yaml(root / "contracts" / "shape-pin.yaml")["commit"].lower() \
        == upstream_and_project["a"]


def test_apply_without_yes_refuses_on_an_empty_stdin_pipe(
        root, upstream_and_project):
    """The non-tty branch, exercised over a REAL pipe rather than the
    default closed stdin `run_script` now supplies — a Windows-runnable
    caller can pipe an already-closed stream in rather than inheriting a
    console handle, and `confirm` must refuse the same way either way."""
    result = run_script(UPDATE, "apply", "--root", str(root), "--upstream",
                        str(upstream_and_project["upstream"]),
                        "--at", upstream_and_project["b"], input="")
    assert result.returncode == 2
    assert "update-unconfirmed" in result.stderr
    assert load_yaml(root / "contracts" / "shape-pin.yaml")["commit"].lower() \
        == upstream_and_project["a"]


def test_confirm_treats_eof_as_nobody_to_ask(update_shape, monkeypatch):
    """THE WINDOWS REGRESSION ITSELF, reproduced in-process rather than over
    a subprocess: an inherited console handle can report `isatty()` as True
    with nobody actually there to answer, so `confirm` must catch the
    EOFError `input()` raises on a stream that ends immediately — not only
    refuse when `isatty()` is already False. Same code, same exit meaning,
    reached from the branch the non-tty tests above cannot reach."""
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input",
                        lambda prompt="": (_ for _ in ()).throw(EOFError()))
    args = SimpleNamespace(yes=False)
    with pytest.raises(Refusal) as excinfo:
        update_shape.confirm(args, [], [], "0" * 40)
    assert excinfo.value.code == "update-unconfirmed"


def strip_shape_block(manifest_path) -> None:
    """Remove the `shape:` block from a manifest, as if it had never been
    elected — the one way `rewrite_manifest` has nothing to mirror the pin
    into."""
    lines = manifest_path.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.rstrip() == "shape:")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].strip() and not lines[index].startswith((" ", "\t")):
            end = index
            break
    manifest_path.write_text("\n".join(lines[:start] + lines[end:]) + "\n",
                             encoding="utf-8")


def test_apply_with_no_shape_block_names_this_kinds_own_manifest_validator(
        root, upstream_and_project):
    """A PROJECT root's remediation must send the operator to
    `validate-manifest.py`, the validator this root actually carries — see
    the family-side twin of this test in `test_family.py`, which asserts the
    opposite name on a root that does not carry this one."""
    strip_shape_block(root / "project.yaml")
    result = apply(root, upstream_and_project)
    assert result.returncode == 2
    assert "update-manifest-no-shape" in result.stderr
    assert "validate-manifest.py" in result.stderr
    assert "validate-family.py" not in result.stderr
    assert load_yaml(root / "contracts" / "shape-pin.yaml")["commit"].lower() \
        == upstream_and_project["a"], "a refused apply writes nothing at all"


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
    """Two edits to one file is a merge, and a merge is a human's judgement —
    UNLESS the human says `--accept-local`, which is
    `test_accept_local_on_a_both_row_repins_from_the_local_bytes`'s exit, not
    this test's: this one is the refusal that fires without it, and `check`'s
    detail for `both` now names that exit by path."""
    edit_locally(root, CHANGED)
    checked = check(root, upstream_and_project)
    assert checked.returncode == 1
    assert verdicts(checked.stdout)[CHANGED] == "both"
    assert f"--accept-local {CHANGED}" in checked.stdout

    result = apply(root, upstream_and_project)
    assert_refused_and_unpinned(result, root, upstream_and_project,
                                "update-conflict", CHANGED)


def test_accept_local_on_a_both_row_repins_from_the_local_bytes(
        root, upstream_and_project):
    """`--accept-local` on a `both` row is the person's word, exactly as it
    already is for `locally-modified` (`test_accept_local_on_a_path_with_no_
    row_refuses`'s sibling, not its opposite): the row is recomputed from
    whatever is on disk, whether or not those bytes actually incorporate the
    upstream's side of the conflict. So this ends up recording the LOCAL
    edit alone, not a merge of it with upstream's change to the same file."""
    edit_locally(root, CHANGED)
    edited = (root / CHANGED).read_bytes()
    result = apply(root, upstream_and_project, "--accept-local", CHANGED)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (root / CHANGED).read_bytes() == edited, (
        "the local bytes are kept; upstream's side of the conflict is never "
        "copied over an accepted row")
    assert pin_rows(root)[CHANGED] == file_sha256(root / CHANGED)
    validators_are_green(root)


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


# --- both: an in-place adoption's Makefile, forever (#84) -------------------
#
# THE INKROUTER/IRRS BUG, REPRODUCED. The in-place adoption above merges the
# collision away and drops its row, so the project's Makefile carries none and
# is invisible to this tool. This is the OTHER outcome, and the one
# `adopt-project.py` actually produces when there is no collision: the
# shape's Makefile lands straight at `Makefile`, WITH the adopted project's
# `CONTRACTS_DIR` block appended, and KEEPS its pin row. `classify()`'s
# `verbatim_at_pin` check then reads that row as `both` the moment upstream
# touches the template, forever, regardless of any further local edit — which
# is why `--accept-local` on it could never simply mean "keep my edit": most
# of the time there IS no edit, only the append the adoption itself made.


def set_pin_row_sha256(pin_path, path: str, sha256: str) -> None:
    """Hand-patch one `files:` row's digest to what a real adoption's own
    materializer would have written: over the file AFTER `ADOPT_MAKEFILE_
    BLOCK` was appended (`shape_materialize.py`'s `_materialize`, ~:621-627,
    digests `result.shape_files` only once every append has already landed
    on disk). That is what makes `locally_modified` false and `verbatim_at_
    pin` false AT ONCE — the second `both` branch, "not a verbatim copy ...
    appends to it", rather than the first — which is the actual shape #84
    was filed about.
    """
    lines = pin_path.read_text(encoding="utf-8").splitlines()
    out = []
    at_path = False
    patched = False
    for line in lines:
        if at_path and line.strip().startswith("sha256:"):
            out.append(f'    sha256: "{sha256}"')
            at_path = False
            patched = True
            continue
        out.append(line)
        at_path = line.strip() == f"- path: {path}"
    assert patched, f"{path} has no row in {pin_path}"
    pin_path.write_text("\n".join(out) + "\n", encoding="utf-8")


@pytest.fixture(scope="module")
def adopted_upstream_and_project(tmp_path_factory) -> dict:
    """A SEPARATE clone/project pair, so an upstream Makefile-template change
    cannot move any OTHER test's target commit out from under it.

    `check()`'s default `--at` is the upstream's HEAD, and `upstream_and_
    project` above is shared by every other test in this module; a further
    commit on ITS clone would move all of them onto a target none of them
    expect. This fixture's own commit B' changes the Makefile TEMPLATE — the
    one thing no other test here may see move — so it gets its own clone,
    built by the same `scaffold_upstream_and_project` helper
    `upstream_and_project` calls.
    """
    _base, upstream, commit_a, clone = scaffold_upstream_and_project(
        tmp_path_factory, "update-shape-adopted")

    # ---- mirror an in-place adoption's Makefile append ---------------------
    makefile_path = clone / MAKEFILE
    makefile_path.write_text(
        makefile_path.read_text(encoding="utf-8") + ADOPT_MAKEFILE_BLOCK,
        encoding="utf-8")
    set_pin_row_sha256(clone / "contracts" / "shape-pin.yaml", MAKEFILE,
                       file_sha256(makefile_path))
    git("add", "--", MAKEFILE, "contracts/shape-pin.yaml", cwd=clone)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        "Mirror an in-place adoption's Makefile append", cwd=clone)

    # ---- commit B': the Makefile TEMPLATE changes, like #80's make park ----
    commit_b = commit_upstream_changes(
        upstream, "Change the Makefile template and the manifest validator",
        {MAKEFILE_SOURCE: "\n# make park / make resume, upstream (#80).\n",
         CHANGED_SOURCE: UPSTREAM_FIX_LINE})
    assert commit_a != commit_b

    return {"upstream": upstream, "clone": clone, "a": commit_a, "b": commit_b}


@pytest.fixture
def adopted_root(adopted_upstream_and_project, tmp_path):
    """A private, mutable copy of the adopted project as it stood at A."""
    target = tmp_path / (PROJECT + "Adopted")
    shutil.copytree(adopted_upstream_and_project["clone"], target,
                    symlinks=True)
    return target


def merged_makefile(adopted_upstream_and_project) -> str:
    """The hand merge AGENTS.md's point 4 describes: the upstream's TARGET
    template, with the adoption's own block kept on the end — "apply the
    upstream delta, keep the block", exactly as `_materialize` would if it
    ran again at the new commit."""
    upstream = adopted_upstream_and_project["upstream"]
    target = adopted_upstream_and_project["b"]
    template = subprocess.run(
        ["git", "show", f"{target}:{MAKEFILE_SOURCE}"], cwd=str(upstream),
        capture_output=True, check=True).stdout.decode("utf-8")
    return template + ADOPT_MAKEFILE_BLOCK


def test_an_adopted_makefile_reports_both_and_names_accept_local(
        adopted_root, adopted_upstream_and_project):
    """The #84 reproduction: an adopted Makefile reads `both` the moment
    upstream touches the template, via the "not a verbatim copy" branch
    rather than "edited here AND upstream" — there is no local edit yet, only
    the adoption's own append — and `check`'s detail now names the exit."""
    result = check(adopted_root, adopted_upstream_and_project)
    assert result.returncode == 1, result.stdout + result.stderr
    verdict = verdicts(result.stdout)
    assert verdict[MAKEFILE] == "both"
    assert verdict[CHANGED] == "upstream-changed"
    assert f"--accept-local {MAKEFILE}" in result.stdout
    assert "appends to it" in result.stdout, (
        "the 'not a verbatim copy ... appends to it' branch must be the one "
        "that fired, not 'edited here AND upstream'")


def test_apply_without_accept_local_still_refuses_the_adopted_makefile(
        adopted_root, adopted_upstream_and_project):
    result = apply(adopted_root, adopted_upstream_and_project)
    assert_refused_and_unpinned(result, adopted_root,
                                adopted_upstream_and_project,
                                "update-conflict", MAKEFILE)


def test_accept_local_on_an_adopted_makefile_repins_the_hand_merge(
        adopted_root, adopted_upstream_and_project):
    """AGENTS.md point 4's exit, taken exactly as written: the hand merge is
    committed on a branch, then `apply --accept-local <path> --branch <that
    branch>` lands ON it — items 1 and 2 together, because #84's own
    reproduction needed both at once."""
    merged = merged_makefile(adopted_upstream_and_project)
    (adopted_root / MAKEFILE).write_text(merged, encoding="utf-8")
    branch = "shape/update-84-test"
    git("checkout", "-q", "-b", branch, cwd=adopted_root)
    git("add", "--", MAKEFILE, cwd=adopted_root)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        "Hand-merge the Makefile: upstream delta applied, adoption's block "
        "kept", cwd=adopted_root)

    result = apply(adopted_root, adopted_upstream_and_project,
                   "--accept-local", MAKEFILE, "--branch", branch)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"committed on {branch}" in result.stdout

    assert git("rev-parse", "--abbrev-ref", "HEAD",
               cwd=adopted_root).stdout.strip() == branch, (
        "apply must commit ONTO the branch already checked out, never "
        "create a second one")
    assert (adopted_root / MAKEFILE).read_text(encoding="utf-8") == merged

    rows = pin_rows(adopted_root)
    assert rows[MAKEFILE] == file_sha256(adopted_root / MAKEFILE)
    assert rows[CHANGED] == file_sha256(adopted_root / CHANGED)

    target = adopted_upstream_and_project["b"]
    upstream = adopted_upstream_and_project["upstream"]
    expected_changed = subprocess.run(
        ["git", "show", f"{target}:{CHANGED_SOURCE}"], cwd=str(upstream),
        capture_output=True, check=True).stdout
    assert (adopted_root / CHANGED).read_bytes() == expected_changed

    pin = load_yaml(adopted_root / "contracts" / "shape-pin.yaml")
    assert pin["commit"].lower() == target
    assert pin["digests"]["tree_sha256"].lower() == tree_digest(upstream,
                                                                target)
    manifest = load_yaml(adopted_root / "project.yaml")
    assert manifest["shape"]["commit"].lower() == target
    assert (manifest["shape"]["digests"]["tree_sha256"].lower()
            == tree_digest(upstream, target))
    validators_are_green(adopted_root)


def test_accept_local_on_an_adopted_makefile_trusts_the_word_even_unmerged(
        adopted_root, adopted_upstream_and_project):
    """`--accept-local` is the person's word, not a check that a merge
    actually happened: an UNMERGED adopted Makefile — still exactly the
    bytes the pin already recorded — is accepted just the same, and
    `validate-pins.py` stays green because the row is recomputed from
    whatever is on disk, merged or not."""
    before = (adopted_root / MAKEFILE).read_bytes()
    result = apply(adopted_root, adopted_upstream_and_project,
                   "--accept-local", MAKEFILE)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (adopted_root / MAKEFILE).read_bytes() == before, (
        "the unmerged local bytes are kept; upstream's Makefile template is "
        "never copied over an accepted row")
    assert pin_rows(adopted_root)[MAKEFILE] == file_sha256(
        adopted_root / MAKEFILE)
    validators_are_green(adopted_root)


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


# --- --trailer: the lines the commit ends with (#111) -----------------------
#
# `apply --branch` composes its own commit message, so a `Lane:` line — which
# the lane-collision protocol wants on every artifact a lane produces, the
# COMMIT included — reaches it no other way, and this estate's convention adds
# `Co-Authored-By:` beside it. The grammar, the git-version question and the
# `LANES_LANE` rule are `tests/test_commit_trailers.py`'s; what these assert is
# the tool: that the flag reaches the commit, that it is refused where there is
# no commit to reach, and that a run passing none writes exactly what it always
# wrote.

def test_two_trailers_end_the_commit_message_in_the_order_given(
        root, upstream_and_project, tmp_path):
    """TWO RUNS OF THE SAME APPLY, one with the flag and one without, and the
    trailer block is the ONLY difference between the messages.

    That is the byte-identity claim and the ordering claim in one assertion,
    and it is written as a comparison rather than against a pasted copy of
    today's message on purpose: a future edit to the wording is then a change
    in one place, not a test that fails for a reason that has nothing to do
    with trailers.
    """
    plain = tmp_path / (PROJECT + "-plain")
    shutil.copytree(root, plain, symlinks=True)
    bare = apply(plain, upstream_and_project, "--branch", "shape/update-plain")
    assert bare.returncode == 0, bare.stderr + bare.stdout

    result = apply(root, upstream_and_project,
                   "--branch", "shape/update-trailers",
                   "--trailer", TRAILERS[0], "--trailer", TRAILERS[1])
    assert result.returncode == 0, result.stderr + result.stdout

    assert message_of(root) == \
        message_of(plain) + "\n" + "\n".join(TRAILERS) + "\n"
    assert trailers_of(root) == list(TRAILERS), (
        "and git reads them back as the trailer block, in order")
    assert trailers_of(plain) == [], "the run without the flag carries none"
    # The commit is still the one this tool makes: explicit pathspecs, and
    # nothing about a trailer changes what it committed.
    assert set(git("show", "--name-only", "--format=", "HEAD",
                   cwd=root).stdout.split()) == \
        {CHANGED, "contracts/shape-pin.yaml", "project.yaml"}


def test_one_trailer_is_the_whole_block(root, upstream_and_project):
    """Repeatable means one is as legitimate as two: a lane with no
    co-author to name passes the `Lane:` line alone."""
    result = apply(root, upstream_and_project, "--branch", "shape/update-one",
                   "--trailer", TRAILERS[0])
    assert result.returncode == 0, result.stderr + result.stdout
    assert message_of(root).endswith("\n" + TRAILERS[0] + "\n")
    assert trailers_of(root) == [TRAILERS[0]]


def test_no_trailer_leaves_the_commit_carrying_none(root,
                                                    upstream_and_project):
    """The default, stated on its own: a message with no trailer block at
    all, still ending in the sentence this tool has always ended on."""
    result = apply(root, upstream_and_project, "--branch", "shape/update-none")
    assert result.returncode == 0, result.stderr + result.stdout
    assert trailers_of(root) == []
    assert message_of(root).endswith(
        "the copies are not hand-edited and the digests are recomputed, not "
        "adjusted.\n")
    assert "Lane:" not in message_of(root)


def test_a_trailer_without_branch_is_refused_like_push_and_pr(
        root, upstream_and_project):
    """A trailer is a LINE ON THE COMMIT this tool writes, so without
    `--branch` there is no commit for it to be a line on — the same shape of
    refusal `--push` and `--pr` already carry, under the same id, and a
    refused apply writes nothing at all."""
    result = apply(root, upstream_and_project, "--trailer", TRAILERS[0])
    assert_refused_and_unpinned(result, root, upstream_and_project,
                                "update-branch-required", "--trailer",
                                "--branch")
    assert "--push" not in result.stderr, (
        "the refusal names the flag that was passed, not the two that were "
        "not")


def test_the_refusal_names_every_flag_that_was_passed(root,
                                                      upstream_and_project):
    result = apply(root, upstream_and_project, "--push",
                   "--trailer", TRAILERS[0])
    assert_refused_and_unpinned(result, root, upstream_and_project,
                                "update-branch-required",
                                "--push and --trailer have nothing to act on")


@pytest.mark.parametrize("value", ["Lane xfactory-1", "Lane:xfactory-1",
                                   "Lane: ", "not a trailer at all"])
def test_a_malformed_trailer_is_refused_before_a_byte_is_read(
        root, upstream_and_project, value):
    """ARGPARSE'S OWN ERROR PATH, which is why this refusal arrives with the
    usage line and before the tool has opened the root: a malformed trailer
    is a malformed command line."""
    result = apply(root, upstream_and_project, "--branch", "shape/update-bad",
                   "--trailer", value)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "--trailer" in result.stderr
    assert "usage:" in result.stderr
    assert load_yaml(root / "contracts" / "shape-pin.yaml")["commit"].lower() \
        == upstream_and_project["a"], "argparse refused before anything ran"
    assert git("rev-parse", "--abbrev-ref", "HEAD",
               cwd=root).stdout.strip() == "main"


def test_the_next_line_check_prints_carries_the_lane_when_one_is_set(
        root, upstream_and_project):
    """So a run that PASTES the line lands protocol-complete, rather than
    landing a commit somebody has to amend afterwards — which is how four
    InkRouter re-pins landed with no trailer at all (#111)."""
    # THE BASELINE PINS THE ENVIRONMENT ITSELF (Copilot, PR #112).
    # `tests/conftest.py::run_script` blanks `LANES_LANE` for every run that
    # does not ask for one, so this is belt and braces — but the assertion
    # below is "the lane run is the plain one PLUS the trailer", and a
    # baseline that had silently been a second lane run would have compared
    # two identical lines and passed.
    result = run_script(UPDATE, "check", "--root", str(root), "--upstream",
                        str(upstream_and_project["upstream"]),
                        env={"LANES_LANE": ""})
    assert result.returncode == 1, result.stdout + result.stderr
    plain = next_line_of(result.stdout)

    lane = run_script(UPDATE, "check", "--root", str(root), "--upstream",
                      str(upstream_and_project["upstream"]),
                      env={"LANES_LANE": LANE})
    assert lane.returncode == 1, lane.stdout + lane.stderr
    assert next_line_of(lane.stdout) == plain + f' --trailer "Lane: {LANE}"'
    # And it is a line that survives being pasted: one argument, whole.
    assert shlex.split(next_line_of(lane.stdout))[-2:] == \
        ["--trailer", f"Lane: {LANE}"]
    assert "Co-Authored-By" not in lane.stdout, (
        "the second trailer names a person or a model, which no environment "
        "variable knows; it is the caller's to pass")


def test_the_next_line_says_nothing_about_a_lane_when_none_is_set(
        root, upstream_and_project):
    """Today's output, byte for byte, for everybody who is not in a lane."""
    result = run_script(UPDATE, "check", "--root", str(root), "--upstream",
                        str(upstream_and_project["upstream"]),
                        env={"LANES_LANE": ""})
    assert result.returncode == 1, result.stdout + result.stderr
    assert "--trailer" not in result.stdout
    assert next_line_of(result.stdout).endswith(
        f"--branch shape/update-{upstream_and_project['b'][:12]}")


# --- the README's `Shape:` line (#148) --------------------------------------
#
# A family holder's README ends with the standard it was cut from, and until
# #148 nothing moved that sha afterwards: InkRouter's holder named a commit
# four re-pins old while its pin was current. The line is prose in a file no
# pin row covers, so `apply` moves it in the pin's own commit and leaves it
# strictly alone in every case where moving it would be a guess.
#
# THE TESTS BUILD THE LINE FROM THE TEMPLATE rather than retyping it, so a
# reworded template fails here rather than quietly passing against a form
# nothing renders any more. `tests/test_family.py` asserts the other half of
# that: what the template renders is what the pattern matches.

FAMILY_README_TEMPLATE = REPO / "templates" / "family-root" / "README.md"


def rendered_shape_line(commit: str,
                        repository: str = SHAPE_REPOSITORY) -> str:
    """The trailing line `templates/family-root/README.md` renders, built out
    of the template itself.

    An ASSEMBLY root renders no such line — which is why these tests put one
    on a scaffolded project by hand: the rewriter reads a form, not a kind of
    root, and an adopted project that copied the holder's sentence gets the
    same answer as the holder.
    """
    line = FAMILY_README_TEMPLATE.read_text(encoding="utf-8").splitlines()[-1]
    assert "{{SHAPE_COMMIT}}" in line, (
        "the template's last line is no longer the Shape: line; #148's "
        "rewriter reads the LAST line's form")
    return (line.replace("{{SHAPE_REPOSITORY}}", repository)
                .replace("{{SHAPE_COMMIT}}", commit))


def give_readme(root, *lines: str, commit: bool = True):
    """Append `lines` to this root's README and hand it back.

    COMMITTED BY DEFAULT, because that is what a holder's README is: the line
    is rendered by the scaffold and lands in the scaffold's commit. `apply`
    refuses to carry a README that has changes of its own (Copilot, PR #152),
    so a fixture that left the line in the working tree would be testing that
    refusal by accident in every test here instead of the rewrite.
    """
    readme = root / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\n"
                      + "".join(line + "\n" for line in lines),
                      encoding="utf-8")
    if commit:
        git("add", "--", "README.md", cwd=root)
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
            "The README names the shape it was cut from", "--", "README.md",
            cwd=root)
    return readme


def committed_files(root) -> set:
    return set(git("show", "--name-only", "--format=", "HEAD",
                   cwd=root).stdout.split())


def test_apply_moves_the_readmes_shape_line_in_the_pins_own_commit(
        root, upstream_and_project):
    """ONE COMMIT, because the line is a claim about the pin beside it.

    A sha moved in a later commit is a README that was wrong in between, and
    "in between" is where every stale holder README has lived. Everything but
    those 40 characters is byte for byte what it was: this tool does not
    re-render a document the project owns.
    """
    a, b = upstream_and_project["a"], upstream_and_project["b"]
    readme = give_readme(root, rendered_shape_line(a))
    before = readme.read_bytes()

    result = apply(root, upstream_and_project, "--branch", "shape/update-rm")
    assert result.returncode == 0, result.stdout + result.stderr

    after = readme.read_bytes()
    assert len(after) == len(before), "one sha for another, nothing else"
    assert after.decode("utf-8").splitlines()[:-1] == \
        before.decode("utf-8").splitlines()[:-1]
    assert after.decode("utf-8").splitlines()[-1] == rendered_shape_line(b)
    assert f"README.md: Shape: line {a[:12]} -> {b[:12]}" in result.stdout

    committed = committed_files(root)
    assert {"README.md", "contracts/shape-pin.yaml"} <= committed, committed
    assert "README.md" in git("log", "-1", "--format=%B", cwd=root).stdout, (
        "the one file in this commit with no pin row is named in the message")
    validators_are_green(root)


def test_a_red_validator_rolls_the_readme_line_back_with_the_rest(
        root, upstream_and_project):
    """The rewrite is inside the SAME transaction as the copies and the pin.

    A README left naming a commit the rolled-back tree is not pinned to would
    be exactly the drift this feature exists to end, introduced by the
    feature.
    """
    a = upstream_and_project["a"]
    readme = give_readme(root, rendered_shape_line(a))
    before = readme.read_bytes()
    spec = root / "contracts" / "spec-pin.yaml"
    spec.write_text(spec.read_text(encoding="utf-8")
                    .replace('commit: "', 'commit: "' + "0" * 40 + '" # ', 1),
                    encoding="utf-8")
    assert run_script(root / "scripts" / "validate-pins.py",
                      cwd=root).returncode != 0, "fixture: the leg pin is red"

    result = apply(root, upstream_and_project)
    assert result.returncode == 2, result.stdout
    assert "update-validators-red" in result.stderr
    assert readme.read_bytes() == before, "every byte, including the README"


def test_a_readme_with_no_shape_line_is_left_exactly_as_it_was(
        root, upstream_and_project):
    """A SCAFFOLDED ASSEMBLY ROOT IS THIS CASE, and so is every adopted
    project whose own README says nothing about a shape. Silence would read
    as "done", so the run says which of the two it did."""
    readme = root / "README.md"
    before = readme.read_bytes()
    assert readme_shape_lines(before.decode("utf-8")) == [], (
        "fixture: an assembly root renders no Shape: line")

    result = apply(root, upstream_and_project, "--branch", "shape/update-no")
    assert result.returncode == 0, result.stdout + result.stderr
    assert readme.read_bytes() == before
    assert "README.md: no Shape: line, untouched" in result.stdout
    assert "README.md" not in committed_files(root)


def test_a_shape_line_naming_another_repository_is_untouched_and_said(
        root, upstream_and_project):
    """The line names WHICH standard, and this tool pins one of them. A
    project that records a second standard's revision in the same form is
    making a statement about a repository this run knows nothing about."""
    elsewhere = rendered_shape_line(upstream_and_project["a"],
                                    repository="octo/Elsewhere")
    readme = give_readme(root, elsewhere)
    before = readme.read_bytes()

    result = apply(root, upstream_and_project, "--branch", "shape/update-el")
    assert result.returncode == 0, result.stdout + result.stderr
    assert readme.read_bytes() == before
    assert "octo/Elsewhere" in result.stdout
    assert f"not {SHAPE_REPOSITORY}, untouched" in result.stdout
    assert "README.md" not in committed_files(root)


def test_two_shape_lines_are_untouched_and_the_run_says_why(
        root, upstream_and_project):
    """Choosing between them would be the tool deciding which of a project's
    own sentences is the true one."""
    readme = give_readme(root,
                         rendered_shape_line(upstream_and_project["a"]),
                         rendered_shape_line(upstream_and_project["b"]))
    before = readme.read_bytes()

    result = apply(root, upstream_and_project, "--branch", "shape/update-two")
    assert result.returncode == 0, result.stdout + result.stderr
    assert readme.read_bytes() == before
    assert "README.md: 2 Shape: lines, untouched" in result.stdout
    assert "README.md" not in committed_files(root)


def test_check_says_what_apply_would_do_to_the_readme_line(
        root, upstream_and_project):
    """THE HUMAN READS THIS BEFORE SAYING YES, which is the whole posture of
    this tool: `apply` writes nothing `check` did not print first."""
    a, b = upstream_and_project["a"], upstream_and_project["b"]
    absent = check(root, upstream_and_project)
    assert absent.returncode == 1, absent.stdout + absent.stderr
    assert "readme-shape-line: absent" in absent.stdout

    readme = give_readme(root, rendered_shape_line(a))
    stale = check(root, upstream_and_project)
    assert stale.returncode == 1, stale.stdout + stale.stderr
    assert f"readme-shape-line: stale ({a[:12]}, pin will read {b[:12]})" \
        in stale.stdout

    readme.write_text(readme.read_text(encoding="utf-8").replace(a, b),
                      encoding="utf-8")
    current = check(root, upstream_and_project)
    assert current.returncode == 1, current.stdout + current.stderr
    assert "readme-shape-line: current" in current.stdout


def test_a_stale_readme_line_never_moves_checks_exit_code(
        root, upstream_and_project):
    """INKROUTER'S EXACT STATE, and the one run that cannot fix it: the pin
    already names the target, so there is no commit for the line to move in.
    Exit 0 all the same — the line is prose, and a `check` that failed over a
    sentence would be a gate this standard never made — and the report says
    plainly that the next re-pin carries it."""
    a = upstream_and_project["a"]
    give_readme(root, rendered_shape_line(upstream_and_project["b"]))
    result = check(root, upstream_and_project, "--at", a)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "nothing to do" in result.stdout
    assert "readme-shape-line: stale" in result.stdout
    assert "the next re-pin carries it" in result.stdout


def test_a_readme_with_changes_of_its_own_is_left_alone_and_not_committed(
        root, upstream_and_project):
    """THE ONE FILE `apply` WRITES THAT HAS NO DRIFT CHECK (Copilot, #152).

    `git commit -- README.md` commits the WORKING TREE version of that path,
    and a pinned copy can never carry somebody else's edit into that commit
    because `update-local-drift` refuses first. The README has no pin row, so
    without a check of its own a half-written paragraph — staged or not —
    would ride into a shape re-pin the human approved from a `check` that
    never showed it. That is the xFactory sweep `commit_on_branch` was
    written against, arriving through the door this feature opened.
    """
    a = upstream_and_project["a"]
    readme = give_readme(root, rendered_shape_line(a))
    line = rendered_shape_line(a) + "\n"
    text = readme.read_text(encoding="utf-8")
    assert text.endswith(line), "fixture: the rendered line is the last one"
    # ABOVE the trailing line, which is where a paragraph added to a README
    # that has one goes. Under it the line would no longer be the last, and
    # a line that is not the last is a different reading (`absent`) and a
    # different test — this one is about the edit, not about the position.
    mine = text[:-len(line)] + "A paragraph I am writing.\n" + line
    readme.write_text(mine, encoding="utf-8")

    result = apply(root, upstream_and_project, "--branch", "shape/update-wip")
    assert result.returncode == 0, result.stdout + result.stderr
    assert readme.read_text(encoding="utf-8") == mine, (
        "neither the sha nor the paragraph moved")
    assert "uncommitted changes, untouched" in result.stdout
    assert f"README.md: its Shape: line names {a[:12]} and the pin will read "\
        f"{upstream_and_project['b'][:12]}" in result.stdout, (
        "the line names both commits and claims no direction between them — "
        "see test_an_uncommitted_line_ahead_of_the_target_is_not_behind")
    assert "README.md" not in committed_files(root)

    # And `check` says the same thing first, rather than promising a rewrite
    # the run will not perform.
    checked = check(root, upstream_and_project)
    assert "readme-shape-line: uncommitted" in checked.stdout


def test_an_uncommitted_line_ahead_of_the_target_is_not_behind(
        root, upstream_and_project):
    """`--at` CAN AIM A RE-PIN BACKWARDS, so "behind" is not a fact.

    `uncommitted` is reached on any disagreement between the line and the
    TARGET, and `--at` is free to name a commit OLDER than the one the README
    already claims — rehearsing a rollback to a known-good standard is the
    ordinary way that happens. Both readings used to call such a line
    "behind", which is the one thing it is not (Copilot, PR #152), and an
    operator told an ahead line is an old one reaches for the wrong repair.
    Naming both commits in the order `stale` already names them is true
    whichever way they lie.

    `check` is where this is reachable end to end, because it is the reader
    that answers about a target `apply` would decline as nothing to do. The
    `apply` half of the same sentence is asserted in
    `test_a_readme_with_changes_of_its_own_is_left_alone_and_not_committed`,
    which runs a real re-pin over an uncommitted README.
    """
    a, b = upstream_and_project["a"], upstream_and_project["b"]
    readme = give_readme(root, rendered_shape_line(b))
    # ABOVE the trailing line, so the reading under test is `uncommitted` and
    # not `absent`: a paragraph added below it would make the claim no longer
    # the last line, which is a different reading and a different test.
    line = rendered_shape_line(b) + "\n"
    text = readme.read_text(encoding="utf-8")
    readme.write_text(text[:-len(line)] + "A paragraph I am writing.\n" + line,
                      encoding="utf-8")

    # `--at a` aims at the commit this root is already pinned to, while the
    # README names b — so the line is AHEAD of the target, not behind it.
    checked = check(root, upstream_and_project, "--at", a)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert f"readme-shape-line: uncommitted ({b[:12]}, pin will read " \
        f"{a[:12]}," in checked.stdout
    assert "behind" not in checked.stdout, (
        "the line is ahead of the target here; nothing may call it behind")


def test_check_names_the_readme_in_the_pin_alone_preview(
        root, upstream_and_project, tmp_path):
    """THE COMMONEST HOLDER RE-PIN OF ALL: a pin behind the standard with not
    one copied byte different. `apply` moves the README's line in that same
    commit, so a preview reading "the pin alone" described a commit that
    would have had a second file in it (Copilot, #152)."""
    give_readme(root, rendered_shape_line(upstream_and_project["a"]))
    # A PRIVATE COPY of the upstream, advanced by a commit that changes
    # nothing this project copies: the pin moves and every row stays
    # `unchanged`. A copy rather than a commit on the module-scoped fixture,
    # for the reason `test_shape_doctor.py::advanced_standard` gives — every
    # other test here is a claim about a project cut from THAT upstream at
    # THAT HEAD.
    ahead = tmp_path / "openRepoShape-ahead"
    shutil.copytree(upstream_and_project["upstream"], ahead, symlinks=True)
    # Back to A first: commit B changes a file this project COPIES, and one
    # `upstream-changed` row is the other branch of the report entirely.
    git("reset", "--hard", "-q", upstream_and_project["a"], cwd=ahead)
    empty = commit_upstream_changes(
        ahead, "An upstream change no project copies",
        {"README.md": "\nA line no project copies.\n"})
    result = run_script(UPDATE, "check", "--root", str(root),
                        "--upstream", str(ahead), "--at", empty)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "`apply` would move the pin and README.md's Shape: line" \
        in result.stdout
    assert "the pin alone" not in result.stdout


def test_an_ignored_untracked_readme_is_left_alone_rather_than_half_committed(
        root, upstream_and_project):
    """`git status --porcelain` SAYS NOTHING ABOUT AN IGNORED FILE, so the
    committed check had to ask with `--ignored` (Copilot, #152).

    Without it this README read as clean, was rewritten, and then handed `git
    commit -- README.md` a pathspec git has never heard of — a failure
    arriving after every other byte was written, on the one path `cmd_apply`
    does not roll back. The exclude goes in `.git/info/exclude` rather than
    `.gitignore` because `.gitignore` is a PINNED copy: editing it would be
    drift, and this test would be exercising that refusal instead.
    """
    a = upstream_and_project["a"]
    readme = give_readme(root, rendered_shape_line(a))
    before = readme.read_bytes()
    exclude = root / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    exclude.write_text("README.md\n", encoding="utf-8")
    git("rm", "-q", "--cached", "--", "README.md", cwd=root)
    # No pathspec: the staged DELETION is what has to land, and `commit --
    # README.md` would commit the working tree's copy of that path instead,
    # putting the file straight back.
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        "The README is this project's own, and ignored", cwd=root)

    result = apply(root, upstream_and_project, "--branch", "shape/update-ign")
    assert result.returncode == 0, result.stdout + result.stderr
    assert readme.read_bytes() == before
    assert "uncommitted changes, untouched" in result.stdout
    assert "README.md" not in committed_files(root)
    validators_are_green(root)


@WINDOWS_SKIP
def test_a_symlinked_readme_is_never_written_through(root,
                                                     upstream_and_project,
                                                     tmp_path):
    """A ROOT MAY POINT ITS README OUT OF ITSELF, and `Path.is_file()`
    follows the link (Copilot, #152).

    Written through, the replacement would land in a file outside this
    repository — somebody else's — while the symlink git tracks stayed
    byte-identical, so the commit would not contain the edit it had just
    made. Left alone, and said.
    """
    outside = tmp_path / "elsewhere.md"
    outside.write_text("Someone else's document.\n\n"
                       + rendered_shape_line(upstream_and_project["a"])
                       + "\n", encoding="utf-8")
    before = outside.read_bytes()
    readme = root / "README.md"
    readme.unlink()
    readme.symlink_to(outside)
    git("add", "--", "README.md", cwd=root)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        "The README lives outside this root", "--", "README.md", cwd=root)

    result = apply(root, upstream_and_project, "--branch", "shape/update-sym")
    assert result.returncode == 0, result.stdout + result.stderr
    assert outside.read_bytes() == before, (
        "a file outside the root is not this tool's to write")
    assert "a symlink, untouched" in result.stdout
    assert "README.md" not in committed_files(root)

    checked = check(root, upstream_and_project)
    assert "readme-shape-line: symlink" in checked.stdout


def test_a_shape_line_that_is_not_the_last_line_is_an_example_not_a_claim(
        root, upstream_and_project):
    """A README MAY SHOW WHAT THE LINE LOOKS LIKE (Copilot, PR #152).

    The pattern is anchored to a LINE, so before #152's third round any
    occurrence of the form was read as this root's claim about its own pin —
    including one inside a paragraph explaining the form to a reader, or a
    fenced example in a project whose whole subject is this standard. `apply`
    would have rewritten that prose to say something the prose does not mean:
    the documentation version of the drift #148 is about, made by the fix.
    Only the line the file ENDS with is the rendered metadata, so this README
    reads `absent` — and `absent` says which absent it is, because a human
    looking at a file that plainly contains the line deserves better than
    silence.
    """
    a = upstream_and_project["a"]
    readme = give_readme(root, "A holder's README ends with a line like",
                         rendered_shape_line(a), "",
                         "and `apply` moves that sha with the pin.")
    before = readme.read_bytes()
    assert len(readme_shape_lines(before.decode("utf-8"))) == 1, (
        "fixture: the form is in the file, just not as its last line")

    checked = check(root, upstream_and_project)
    assert "readme-shape-line: absent (README.md carries a Shape: line, but " \
        "not as its last line" in checked.stdout

    result = apply(root, upstream_and_project, "--branch", "shape/update-eg")
    assert result.returncode == 0, result.stdout + result.stderr
    assert readme.read_bytes() == before, (
        "an example is not this tool's to move")
    assert "README.md: its Shape: line is not the last line" in result.stdout
    assert "README.md" not in committed_files(root)
    validators_are_green(root)


def test_an_example_above_the_rendered_line_leaves_the_readme_ambiguous(
        root, upstream_and_project):
    """AND THE COLLISION THE EOF RULE DOES NOT DISSOLVE. A README that both
    SHOWS the form and ENDS with it carries two exact matches, and two is
    already the answer `apply` refuses to choose between: rewriting the last
    one and leaving an example naming a different commit two paragraphs above
    would leave the file contradicting itself, in this tool's name.
    """
    a = upstream_and_project["a"]
    readme = give_readme(root, "A holder's README ends with a line like",
                         rendered_shape_line(a), "",
                         "which for this root reads", "",
                         rendered_shape_line(a))
    before = readme.read_bytes()

    checked = check(root, upstream_and_project)
    assert "readme-shape-line: ambiguous (2 Shape: lines" in checked.stdout

    result = apply(root, upstream_and_project, "--branch", "shape/update-two")
    assert result.returncode == 0, result.stdout + result.stderr
    assert readme.read_bytes() == before
    assert "README.md: 2 Shape: lines, untouched" in result.stdout
    assert "README.md" not in committed_files(root)


def test_a_hard_linked_readme_is_never_written_through(
        root, upstream_and_project, tmp_path):
    """A SECOND NAME FOR THE SAME BYTES IS NOT A SECOND FILE (Copilot, #152).

    `is_symlink()` says no and git says clean, because nothing about the
    content differs — and every write this tool makes goes THROUGH a name:
    `Rollback.write` overwrites the inode and the undo writes back the same
    way. So a rewrite here would also change whatever else that inode is
    called, a file no `check` showed and no pin covers, while the commit
    records only `README.md`. Left alone, and said.
    """
    a = upstream_and_project["a"]
    readme = give_readme(root, rendered_shape_line(a))
    before = readme.read_bytes()
    second = tmp_path / "the-same-bytes.md"
    try:
        os.link(str(readme), str(second))
    except (OSError, NotImplementedError) as exc:  # pragma: no cover
        pytest.skip(f"this platform will not hard-link: {exc}")

    result = apply(root, upstream_and_project, "--branch", "shape/update-hard")
    assert result.returncode == 0, result.stdout + result.stderr
    assert readme.read_bytes() == before
    assert second.read_bytes() == before, (
        "a file outside the root is not this tool's to write")
    assert "another name points at these same bytes, untouched" \
        in result.stdout
    assert "README.md" not in committed_files(root)

    checked = check(root, upstream_and_project)
    assert "readme-shape-line: hard-link" in checked.stdout


def denied(readme, mode: int, probe: str) -> None:
    """Put `mode` on the README, and SKIP if this user is not stopped by it.

    root ignores a file's permission bits and so does a filesystem mounted
    without them; a test that assumed otherwise would be failing about the
    machine it runs on rather than about the code. Windows has no mode to
    take a read away with, so the reading probe skips there too.
    """
    readme.chmod(mode)
    try:
        with readme.open(probe):
            pass
    except OSError:
        return
    pytest.skip("this user is not stopped by the README's permission bits")


def test_a_readme_the_os_will_not_write_refuses_and_rolls_the_tree_back(
        root, upstream_and_project):
    """THE PHASE RUNS AFTER THE COPIES AND THE PIN (Copilot, PR #152).

    An `OSError` escaping it would have ended the command with a traceback
    over a tree that had already been rewritten and re-pinned: `cmd_apply`
    rolls back on `Refusal` and `CommandFailed` and on nothing else. Named as
    a refusal, the arm that already exists puts every byte back — and the
    ledger opens for writing BEFORE it records anything, so a file it cannot
    write is one it never promised to restore.
    """
    a = upstream_and_project["a"]
    readme = give_readme(root, rendered_shape_line(a))
    before = readme.read_bytes()
    copied = root / CHANGED
    copied_before = copied.read_bytes()
    denied(readme, 0o444, "r+b")
    try:
        result = apply(root, upstream_and_project)
    finally:
        readme.chmod(0o644)

    assert_refused_and_unpinned(result, root, upstream_and_project,
                                "update-readme-unwritable", "README.md")
    assert readme.read_bytes() == before
    assert copied.read_bytes() == copied_before, (
        "the copies this command had already written are rolled back too")
    validators_are_green(root)


def test_a_readme_the_os_will_not_read_is_a_reading_rather_than_a_traceback(
        root, upstream_and_project):
    """THE SAME HAZARD ON THE WAY IN, and the answer is the opposite one: a
    README this tool cannot read is one it cannot be wrong about, so it is
    LEFT ALONE and the reason is said, rather than a refusal that would stop
    a re-pin over prose.
    """
    readme = give_readme(root, rendered_shape_line(upstream_and_project["a"]))
    before = readme.read_bytes()
    denied(readme, 0o000, "rb")
    try:
        result = apply(root, upstream_and_project, "--branch",
                       "shape/update-noread")
        checked = check(root, upstream_and_project)
    finally:
        readme.chmod(0o644)

    assert result.returncode == 0, result.stdout + result.stderr
    assert readme.read_bytes() == before
    assert "README.md: not readable" in result.stdout
    assert "README.md" not in committed_files(root)
    assert "readme-shape-line: unreadable (README.md is not readable" \
        in checked.stdout


def test_a_readme_that_is_not_utf_8_is_a_reading_no_platform_can_skip(
        root, upstream_and_project):
    """THE ARM DIRECTLY ABOVE, WITH NOTHING TO ARRANGE (#158).

    `_classify` turns every way of failing to READ this file into a reading
    rather than a raise, and the test above covers the `OSError` half of that
    by taking a read away with `denied()` — which skips outright for root,
    for a filesystem mounted without permission bits, and on Windows, where
    there is no mode to take a read away with. So the `UnicodeDecodeError`
    half, which is the older of the two and the one `check`, `apply` and the
    doctor all lean on when they are pointed at somebody else's prose, had no
    test that was guaranteed to run anywhere.

    Bytes that are not UTF-8 need nobody's permission and skip nowhere. The
    answer is the same one every README this tool cannot account for gets:
    left alone, said out loud, and absent from the commit.
    """
    readme = root / "README.md"
    # A rendered Shape: line with one byte corrupted. 0xFF begins no UTF-8
    # sequence at all, so there is no locale and no platform on which this
    # file decodes — and the corruption is in the one line a rewrite would
    # otherwise move.
    readme.write_bytes(
        readme.read_text(encoding="utf-8").encode("utf-8") + b"\n"
        + rendered_shape_line(upstream_and_project["a"]).encode("utf-8")
        .replace(b"Shape", b"Sh\xffpe") + b"\n")
    git("add", "--", "README.md", cwd=root)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        "The README picked up a byte on its way through an editor", "--",
        "README.md", cwd=root)
    before = readme.read_bytes()

    result = apply(root, upstream_and_project, "--branch", "shape/update-utf8")
    checked = check(root, upstream_and_project)

    assert result.returncode == 0, result.stdout + result.stderr
    assert readme.read_bytes() == before, (
        "a README this tool cannot read is one it cannot be wrong about, so "
        "it is not one it writes")
    assert "README.md: not valid UTF-8, untouched" in result.stdout
    assert "README.md" not in committed_files(root)
    assert "readme-shape-line: unreadable (README.md is not valid UTF-8)" \
        in checked.stdout


def test_git_answers_three_ways_for_a_readme_and_one_of_them_is_committed(
        root, upstream_and_project, update_shape):
    """THE THREE READINGS BEHIND ONE BOOLEAN, side by side (Codex, PR #152).

    `apply` moves the sha only in a README that is exactly what HEAD has.
    `git commit -- README.md` records the WORKING TREE version of that path,
    so a dirty README would carry somebody's unrelated paragraph into a shape
    re-pin the human approved from a `check` that never showed it; an
    untracked or IGNORED one is a pathspec git has never heard of, and that
    failure would arrive after every other byte was written. Each is one
    `git status` away from the others, and this is where which is which is
    written down.
    """
    readme = give_readme(root, rendered_shape_line(upstream_and_project["a"]))
    committed = readme.read_text(encoding="utf-8")
    assert update_shape.readme_is_committed(root) is True, (
        "a tracked README holding nothing but HEAD's bytes")

    readme.write_text(committed + "\nA paragraph I am writing.\n",
                      encoding="utf-8")
    assert update_shape.readme_is_committed(root) is False, (
        "a tracked README with changes of its own")

    readme.write_text(committed, encoding="utf-8")
    exclude = root / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    exclude.write_text("README.md\n", encoding="utf-8")
    git("rm", "-q", "--cached", "--", "README.md", cwd=root)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        "The README is this project's own, and ignored", cwd=root)
    assert update_shape.readme_is_committed(root) is False, (
        "an IGNORED untracked README, which `--porcelain` alone says "
        "nothing at all about")


def test_an_index_flag_does_not_make_an_edited_readme_committed(
        root, upstream_and_project, update_shape):
    """`git status` READS THE INDEX, and two flags tell it to stop looking.

    `--assume-unchanged` and `--skip-worktree` both leave `git status` silent
    over a README somebody is part way through editing, while `git commit --
    README.md` goes on recording the complete working-tree file (Codex,
    PR #152) — so the status question alone would have let exactly the edit
    the last round closed back in through a flag. The bytes are asked for as
    well now: what `git hash-object` makes of the file on disk against the
    blob HEAD records for that path, which no index flag can quiet.
    """
    a = upstream_and_project["a"]
    readme = give_readme(root, rendered_shape_line(a))
    line = rendered_shape_line(a) + "\n"
    text = readme.read_text(encoding="utf-8")
    mine = text[:-len(line)] + "A paragraph I am writing.\n" + line

    for flag in ("assume-unchanged", "skip-worktree"):
        git("update-index", f"--{flag}", "--", "README.md", cwd=root)
        readme.write_text(mine, encoding="utf-8")
        assert not git("status", "--porcelain", "--ignored", "--",
                       "README.md", cwd=root).stdout.strip(), (
            f"fixture: --{flag} is what makes git say nothing here")
        assert update_shape.readme_is_committed(root) is False, flag
        git("update-index", f"--no-{flag}", "--", "README.md", cwd=root)
        readme.write_text(text, encoding="utf-8")

    git("update-index", "--assume-unchanged", "--", "README.md", cwd=root)
    readme.write_text(mine, encoding="utf-8")
    result = apply(root, upstream_and_project, "--branch", "shape/update-flag")
    assert result.returncode == 0, result.stdout + result.stderr
    assert readme.read_text(encoding="utf-8") == mine, (
        "neither the sha nor the paragraph moved")
    assert "uncommitted changes, untouched" in result.stdout
    assert "README.md" not in committed_files(root)


def test_crlf_endings_and_a_bom_survive_a_rewrite_byte_for_byte(
        root, upstream_and_project):
    """THE REWRITE IS 40 CHARACTERS, and the rest of the file is evidence.

    `_classify` decodes the whole README and `rewrite` re-encodes it, so
    every byte outside the `commit` span is a promise this test is the only
    thing keeping (Copilot, PR #152): a holder checked out on Windows under
    `core.autocrlf`, or written by an editor that leads with a BOM, must come
    back with its endings and its BOM exactly as they were. A rewriter that
    normalised them would rewrite every line of the file to move one sha —
    and would show up in that holder's next diff as a whole-file change
    nobody asked for.
    """
    a, b = upstream_and_project["a"], upstream_and_project["b"]
    readme = root / "README.md"
    readme.write_bytes(
        ("\ufeff# Atlas\r\n\r\nA README written where the lines end in two "
         "characters.\r\n\r\n" + rendered_shape_line(a) + "\r\n")
        .encode("utf-8"))
    git("add", "--", "README.md", cwd=root)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        "The README came from a Windows editor", "--", "README.md", cwd=root)
    before = readme.read_bytes()

    result = apply(root, upstream_and_project, "--branch", "shape/update-crlf")
    assert result.returncode == 0, result.stdout + result.stderr
    after = readme.read_bytes()
    assert after != before, "the sha moved"
    assert after == before.replace(a.encode("ascii"), b.encode("ascii")), (
        "only the 40 hex characters changed — the BOM, the CRLF endings and "
        "every other byte are what they were")
    assert after.startswith(b"\xef\xbb\xbf")
    assert after.count(b"\r\n") == before.count(b"\r\n")
    assert "README.md" in committed_files(root)


def test_a_readme_checked_out_with_crlf_is_committed_and_keeps_its_endings(
        root, upstream_and_project, update_shape):
    """A HOLDER CLONED ON WINDOWS IS THE ONE MOST APT TO DRIFT, and this is
    what says its README is still a README `apply` writes.

    `readme_is_committed` weighs `git hash-object -- README.md` against
    `HEAD:README.md`, and a reviewer read that as hashing the RAW bytes: a
    CRLF working tree would then hash unequal to its own LF blob, be read as
    `uncommitted`, and keep its stale line for ever — this feature's
    byte-preserving CRLF support defeated on the one platform that needs it
    (Copilot, PR #152). It does not happen, because a file handed to
    `hash-object` as an argument is hashed AS that path, clean filter and
    all. The three hashes below are that argument made of bytes rather than
    of prose: the raw file is NOT the committed blob, and the filtered one
    is.

    THE CRLF COMES FROM `.git/info/attributes`, which outranks every
    `.gitattributes` in the tree — the project's own ships `* text=auto
    eol=lf` and is a PINNED copy, so editing it would be drift and this test
    would be exercising that refusal instead. It is the per-clone lever
    `test_git_answers_three_ways_for_a_readme_and_one_of_them_is_committed`
    already uses for the ignored case, and it reproduces exactly what a
    clone under Git for Windows' `core.autocrlf=true` default gets: LF in
    the index, CRLF on disk, and a `git status` with nothing to say.
    """
    a, b = upstream_and_project["a"], upstream_and_project["b"]
    readme = give_readme(root, rendered_shape_line(a))
    attributes = root / ".git" / "info" / "attributes"
    attributes.parent.mkdir(parents=True, exist_ok=True)
    attributes.write_text("README.md text eol=crlf\n", encoding="utf-8")
    readme.unlink()
    git("checkout", "--", "README.md", cwd=root)

    before = readme.read_bytes()
    assert b"\r\n" in before, (
        "fixture: `eol=crlf` is what puts CRLF in this working tree")
    assert not git("status", "--porcelain", "--ignored", "--", "README.md",
                   cwd=root).stdout.strip(), (
        "fixture: git calls a CRLF checkout of an LF blob clean")
    head = git("rev-parse", "HEAD:README.md", cwd=root).stdout.strip()
    assert git("hash-object", "--no-filters", "--", "README.md",
               cwd=root).stdout.strip() != head, (
        "fixture: the bytes on disk really are not the committed blob")
    assert git("hash-object", "--", "README.md",
               cwd=root).stdout.strip() == head, (
        "the clean filter runs on a file argument, so a CRLF working tree "
        "hashes to the LF blob it was committed as")
    assert update_shape.readme_is_committed(root) is True

    result = apply(root, upstream_and_project, "--branch", "shape/update-eol")
    assert result.returncode == 0, result.stdout + result.stderr
    after = readme.read_bytes()
    # The scaffolded README names commit A in prose of its own a few lines
    # up, so the expectation is built by index rather than by replacing every
    # occurrence: only the LAST line is this tool's, and every CRLF in the
    # file — including the one ending the line it rewrote — is where it was.
    was, now = (rendered_shape_line(a).encode("utf-8"),
                rendered_shape_line(b).encode("utf-8"))
    at = before.rindex(was)
    assert after == before[:at] + now + before[at + len(was):]
    assert after.count(b"\r\n") == before.count(b"\r\n")
    assert "README.md" in committed_files(root)


#: The pinned attributes file every scaffolded project carries, and the one
#: line commit C appends to the standard's copy of it. `-text` turns the
#: check-in normalisation OFF for README.md, which is what makes the same
#: working tree answer git's "is this committed?" question two different
#: ways depending on whether the copy has landed yet.
ATTRIBUTES = ".gitattributes"
ATTRIBUTES_SOURCE = f"templates/assembly-root/{ATTRIBUTES}"
ATTRIBUTES_FIX_LINE = "\nREADME.md -text\n"


def test_an_upstream_attributes_change_does_not_decide_the_readmes_fate(
        root, upstream_and_project, tmp_path):
    """THE README IS CLASSIFIED BEFORE THE FIRST COPIED BYTE LANDS (#158).

    `.gitattributes` IS A PINNED COPY, and `readme_is_committed` asks git two
    questions about README.md — `git status` and `git hash-object` — that git
    answers through the attributes in the WORKING TREE. Classified after
    `_write_copies`, this root's README would therefore have its fate decided
    by an upstream edit to `* text=auto eol=lf`: the CRLF working tree below
    hashes to the LF blob it was committed as while the PINNED attributes are
    on disk, and to something else the moment the standard's new
    `README.md -text` replaces them. The line would have read `uncommitted`
    and kept its stale sha — `apply` silently declining to move it for a
    reason that has nothing to do with the README, and one no `check` run
    before the copies landed could have predicted (Copilot, PR #152).

    THE READING MOVES, THE WRITE DOES NOT. Root, repository and target are
    all known before the first copy, so the classification is taken there;
    the rewrite stays where the `Rollback` ledger wants it, after the pin
    move and before the validators, so a red validator still puts this line
    back with everything else.
    """
    a = upstream_and_project["a"]
    # A PRIVATE copy of the upstream, back at A and advanced by a commit that
    # changes ONE copied file: the attributes. A copy rather than a commit on
    # the module-scoped fixture, for the reason `advanced_standard` gives —
    # every other test here is a claim about a project cut from THAT upstream
    # at THAT HEAD.
    ahead = tmp_path / "openRepoShape-attributes"
    shutil.copytree(upstream_and_project["upstream"], ahead, symlinks=True)
    git("reset", "--hard", "-q", a, cwd=ahead)
    target = commit_upstream_changes(
        ahead, "The standard stops normalising README.md's line endings",
        {ATTRIBUTES_SOURCE: ATTRIBUTES_FIX_LINE})

    # A holder cloned on Windows: CRLF in the working tree, LF in the index,
    # and a `git status` with nothing to say — written as bytes so no
    # platform's newline translation has a hand in it.
    readme = root / "README.md"
    readme.write_bytes(
        (readme.read_text(encoding="utf-8") + "\n"
         + rendered_shape_line(a) + "\n").replace("\n", "\r\n")
        .encode("utf-8"))
    git("add", "--", "README.md", cwd=root)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        "The README came from a Windows editor", "--", "README.md", cwd=root)
    before = readme.read_bytes()
    head = git("rev-parse", "HEAD:README.md", cwd=root).stdout.strip()
    assert b"\r\n" in before, "fixture: the working tree really is CRLF"
    assert git("hash-object", "--", "README.md",
               cwd=root).stdout.strip() == head, (
        "fixture: under the PINNED `* text=auto eol=lf` this file hashes to "
        "the LF blob it was committed as, so it is `committed`")
    assert git("hash-object", "--no-filters", "--", "README.md",
               cwd=root).stdout.strip() != head, (
        "fixture: with that normalisation off — which is exactly what the "
        "upstream's new `README.md -text` does — it does not, so the copy "
        "landing first would have flipped the answer")

    result = run_script(UPDATE, "apply", "--root", str(root), "--yes",
                        "--upstream", str(ahead), "--at", target,
                        "--branch", "shape/update-attributes")
    assert result.returncode == 0, result.stdout + result.stderr
    assert ATTRIBUTES_FIX_LINE.strip() in \
        (root / ATTRIBUTES).read_text(encoding="utf-8"), (
        "fixture: the run really did land the standard's new attributes")

    after = readme.read_bytes()
    # The scaffolded README names commit A in prose of its own a few lines
    # up, so the expectation is built by index: only the LAST line is this
    # tool's.
    was, now = (rendered_shape_line(a).encode("utf-8"),
                rendered_shape_line(target).encode("utf-8"))
    at = before.rindex(was)
    assert after == before[:at] + now + before[at + len(was):], (
        "the line moved: the README was classified before the attributes it "
        "is judged under were replaced"
    )
    assert after.count(b"\r\n") == before.count(b"\r\n")
    assert "README.md" in committed_files(root)
    assert "uncommitted" not in result.stdout, result.stdout


def test_a_name_carrying_an_escape_is_not_a_line_this_tool_reads(
        root, upstream_and_project):
    r"""A README IS TEXT SOMEBODY ELSE WROTE, and both readers print the name
    they read out of it straight back to whoever ran them.

    The repository capture used to be `[^`\r\n]+` — anything that was not a
    backtick, an ESC included — while `apply`'s `other-repository` line and
    `check`'s row each echo `match["repository"]` to the terminal (Copilot,
    PR #152). A README whose line named `` `<ESC>[2J...` `` would have played
    terminal control sequences into that terminal, and `shape-doctor.py`
    reads OTHER repositories' READMEs, so the file need not be one the
    operator wrote.

    The capture is the shape a repository name actually has now, so a crafted
    one is not a `Shape:` line at all. `absent` is the right answer and not a
    lesser one: the file is left exactly as it was, which is what this tool
    does with every README it cannot account for.
    """
    a = upstream_and_project["a"]
    crafted = f"Shape: `\x1b[2K{SHAPE_REPOSITORY}` @ `{a}`."
    readme = give_readme(root, crafted)
    before = readme.read_bytes()
    assert readme_shape_lines(before.decode("utf-8")) == [], (
        "a name with an escape character in it is not a repository name")

    result = apply(root, upstream_and_project, "--branch", "shape/update-esc")
    assert result.returncode == 0, result.stdout + result.stderr
    assert readme.read_bytes() == before, "an `absent` README is not written"
    assert "\x1b" not in result.stdout + result.stderr, (
        "nothing out of that line reached the operator's terminal")
    assert "no Shape: line, untouched" in result.stdout
    assert "README.md" not in committed_files(root)


def test_a_backtick_name_running_over_a_line_break_is_not_a_second_line(
        root, upstream_and_project):
    """`[^`]+` MATCHED NEWLINES, and `re.MULTILINE` does not stop it: only
    the `^` and `$` anchors are per line, so a backtick-quoted name broken
    over two lines used to match as one (Copilot, PR #152).

    The cost was not a bad rewrite but a missing one: a malformed example
    like this counted as a SECOND `Shape:` line, which made the holder's real
    one `ambiguous` and left it drifting — the failure #148 exists to end,
    reached through a typo in somebody's prose.
    """
    a, b = upstream_and_project["a"], upstream_and_project["b"]
    broken = ["Shape: `not/a real", "repository` @ `" + "0" * 40 + "`."]
    readme = give_readme(root, *broken, "", rendered_shape_line(a))
    before = readme.read_bytes()
    assert len(readme_shape_lines(before.decode("utf-8"))) == 1, (
        "fixture: the malformed example is not a line the rewriter reads")

    result = apply(root, upstream_and_project, "--branch", "shape/update-brk")
    assert result.returncode == 0, result.stdout + result.stderr
    after = readme.read_bytes()
    # EVERYTHING BUT THE LAST LINE IS BYTE FOR BYTE WHAT IT WAS, which is the
    # strongest way to say it: the malformed example keeps its sha, and so
    # does the scaffolded sentence that names the same commit in prose of its
    # own a few lines up. Only the trailing line is this tool's.
    #
    # The line is found by index rather than by slicing a tail off the end,
    # because the ending is not this test's business: `Path.write_text` gives
    # the fixture CRLF on Windows, and the rewriter is supposed to leave
    # whatever it finds there exactly as it is.
    was, now = (rendered_shape_line(a).encode("utf-8"),
                rendered_shape_line(b).encode("utf-8"))
    at = before.rindex(was)
    assert after == before[:at] + now + before[at + len(was):]
    assert f"README.md: Shape: line {a[:12]} -> {b[:12]}" in result.stdout
    assert "README.md" in committed_files(root)
