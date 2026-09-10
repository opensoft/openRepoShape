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
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from conftest import FILE_PROTOCOL, ORG, REPO, git, run_script

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import Refusal, file_sha256, load_yaml, tree_digest  # noqa: E402
#: The exact block `adopt-project.py` appends to an adopted Makefile,
#: imported rather than retyped — see `adopted_root` below, whose whole point
#: is that it cannot drift from what a real adoption writes.
from shape_materialize import ADOPT_MAKEFILE_BLOCK  # noqa: E402

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
