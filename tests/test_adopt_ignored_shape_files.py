# SPDX-License-Identifier: Apache-2.0
"""A source `.gitignore` hiding dot-files must not hide the shape's (#167).

`_commit_the_split` used to stage the assembly root with `git add -A -- .`,
which honours the SOURCE's `.gitignore`. With the common `.*` + `!.gitignore`
that skipped `.gitattributes` and `.github/workflows/validate.yml` -- files the
shape wrote and `contracts/shape-pin.yaml` pins -- and `execute` still ended
with `adoption verified`, because `_verify` accounts for the SOURCE's paths and
never for the ones the shape added. The assembly then failed its first
bootstrap with `shape-copy-missing`.

Two halves, so two groups of tests: the split now FORCES the shape's own paths
(and only those), and the verification now FAILS when a pinned file is not in
the split commit. All repositories and remotes are local fixtures; no network
is used. The end-to-end tests need `git filter-repo`; the others do not, so
they run on the Windows job, which installs none.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

import pytest

from conftest import (ADOPT, FILE_PROTOCOL, REPO, clear_ambient_pin_sources,
                      git, make_source_repo, run_script, write_plan)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import parse_yaml  # noqa: E402
from shape_materialize import Materialized, root_key  # noqa: E402

#: What the end-to-end tests need and the rest do not: they call the two new
#: helpers on hand-made repositories, so they run on a machine with no
#: `git filter-repo`. Spelled here rather than imported from another test
#: module, so that the files do not depend on each other.
needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

#: The common `.gitignore` that hides every dot-file but itself, and so hides
#: `.gitattributes` and `.github/` from a plain `git add`.
IGNORE_DOTFILES = ".*\n!.gitignore\n"

BRANCH = "adopt/three-repo-shape"
PROJECT = "Northwind"
PIN = "contracts/shape-pin.yaml"
ATTRIBUTES = ".gitattributes"
WORKFLOW = ".github/workflows/validate.yml"
README = "README.md"
MAKEFILE = "Makefile"
MAKEFILE_BODY = "all:\n"
IGNORE_FILE = ".gitignore"
#: The id of the finding, and the start of every line that carries it.
MISSING = "FINDING adopt-shape-file-missing:"
#: The source's OWN attributes file, for the variant in which the shape's copy
#: has to be written beside it, under `shape/`, where `.*` hides it again.
OWN_ATTRIBUTES = "* text=auto\n"

#: A source with NO submodules, the `.gitignore` above, and nothing the plan
#: has to ask a human about. `make_source_repo`'s later commits edit the first
#: two source paths, so they must be here.
SOURCE_TREE = {
    README: "# Thing\n",
    IGNORE_FILE: IGNORE_DOTFILES,
    "specs/001-feature/spec.md": "# The feature\n",
    "src/app/main.py": "import contracts_reader\n",
}

#: Untracked in the source and hidden by its `.gitignore`: never in the source
#: commit, so never in the clone `execute` splits -- which is why the test
#: that they stay out also drops them into that clone before it is staged.
STRAY = {".env": "TOKEN=not-for-the-split\n", ".cache/blob": "cached\n"}


def commit_all(repo: Path, message: str) -> None:
    git("add", "-A", "--", ".", cwd=repo)
    git("-c", "user.name=Source Human", "-c",
        "user.email=source@invalid.example", "commit", "-qm", message,
        cwd=repo)


def committed(repo: Path, rev: str = "HEAD") -> set:
    return set(git("ls-tree", "-r", "--name-only", rev,
                   cwd=repo).stdout.splitlines())


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_ignored_shape_files",
                                                  ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# The split stages the shape's own files, and only those
# ---------------------------------------------------------------------------


def hidden_assembly(tmp_path: Path) -> Path:
    """What `execute` has just before staging: a clone of a source whose
    `.gitignore` hides dot-files, with the mount's `git rm` already done and
    the shape's files written to the disk."""
    source = make_source_repo(
        tmp_path / "source", edits=(),
        tree={README: "# Thing\n", IGNORE_FILE: IGNORE_DOTFILES,
              "old.txt": "moves to a leg\n", "src/app.py": "VALUE = 1\n"})
    assembly = tmp_path / "assembly"
    git("clone", "-q", str(source), str(assembly), cwd=tmp_path)
    git("rm", "-q", "--", "old.txt", cwd=assembly)
    (assembly / README).write_text("# Thing, edited\n")
    return assembly


def write_files(root: Path, files) -> None:
    for name in files:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"{name}\n")


def test_the_split_forces_the_shape_files_and_nothing_else(adopter, tmp_path):
    """The shape's paths are staged past the source's `.gitignore`; a file
    the source ignored that the shape did NOT write stays out; and what
    `-A` was there for -- an edit, a deletion -- is still staged."""
    assembly = hidden_assembly(tmp_path)
    shape_files = [ATTRIBUTES, WORKFLOW, f"shape/{ATTRIBUTES}", PIN]
    strays = [".env", ".cache/blob", ".idea/workspace.xml"]
    write_files(assembly, shape_files + strays)
    for name in shape_files[:-1] + strays:
        # The premise: git would skip every one of these (the pin, under
        # `contracts/`, is the one path here that `.*` does not hide).
        assert git("check-ignore", "-q", "--no-index", name, cwd=assembly,
                   check=False).returncode == 0, name

    written = Materialized()
    written.written = list(shape_files)
    adopter._stage_the_split(assembly, written)

    staged = git("diff", "--cached", "--name-status",
                 cwd=assembly).stdout.splitlines()
    assert sorted(staged) == sorted(
        [f"A\t{name}" for name in shape_files]
        + [f"M\t{README}", "D\told.txt"])


def test_the_forced_paths_are_the_written_ones_in_posix_spelling(adopter,
                                                                  monkeypatch):
    """What reaches `git` is the materializer's own POSIX spelling, which
    `git` takes as a pathspec on Windows too, and never a bare `.` after
    `-f`: forcing the tree would sweep in what the source ignored on purpose.

    The rows are keyed from a Windows path, because that is the spelling the
    materializer is given there and the one that must come out forward-slash.
    """
    root = PureWindowsPath(r"D:\a\_temp\t\Atlas")
    written = Materialized()
    written.written = [root_key(root / ".github" / "workflows" / "validate.yml",
                                root),
                       root_key(root / "shape" / ".gitattributes", root)]
    calls = []
    monkeypatch.setattr(adopter, "run",
                        lambda args, cwd=None, capture=True: calls.append(args))
    adopter._stage_the_split(Path("assembly"), written)

    assert calls == [
        ["git", "add", "-A", "--", "."],
        ["git", "add", "-f", "--", ".github/workflows/validate.yml",
         "shape/.gitattributes"]]
    assert not any("\\" in part for call in calls for part in call)


# ---------------------------------------------------------------------------
# The verification fails when a pinned file is not in the split commit
# ---------------------------------------------------------------------------

SHA = "0" * 64


def pin_of(*paths: str) -> str:
    rows = "".join(f"  - path: {path}\n    sha256: \"{SHA}\"\n"
                   for path in paths)
    return f"schema_version: 1\nkind: pinned_contract_manifest\nfiles:\n{rows}"


def split_commit_of(tmp_path: Path, files: dict, ignore: str = IGNORE_DOTFILES,
                    disk_only: tuple = ()) -> tuple:
    """A tiny assembly repo whose ONE commit is whatever `git add -A` takes
    under `ignore`, and `(repo, that commit)`. `disk_only` files are written
    after the commit, so the working tree has them and the commit does not."""
    repo = tmp_path / "assembly"
    repo.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=repo)
    for name, body in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(body)
    (repo / IGNORE_FILE).write_text(ignore)
    commit_all(repo, "The split")
    write_files(repo, disk_only)
    return repo, git("rev-parse", "HEAD", cwd=repo).stdout.strip()


def test_a_pinned_file_the_split_commit_lacks_is_a_finding(adopter, tmp_path):
    """The bug as the first bootstrap saw it: the pin names `.gitattributes`
    and the workflow, the `.*` source `.gitignore` kept both out of the
    commit, and the files are on the DISK -- so the finding can only come
    from the commit's own tree."""
    files = {MAKEFILE: MAKEFILE_BODY,
             PIN: pin_of(MAKEFILE, ATTRIBUTES, WORKFLOW)}
    repo, commit = split_commit_of(tmp_path, files,
                                   disk_only=(ATTRIBUTES, WORKFLOW))
    assert (repo / ATTRIBUTES).is_file() and (repo / WORKFLOW).is_file()

    findings = adopter._shape_file_findings(repo, commit)

    assert len(findings) == 2, findings
    assert findings[0].startswith(
        f"{MISSING} {ATTRIBUTES} is named by {PIN} but is not in the split "
        f"commit {commit[:12]}.")
    assert findings[1].startswith(f"{MISSING} {WORKFLOW} ")
    # The finding says what to do, per file.
    assert f"`git add -f -- {ATTRIBUTES}`" in findings[0]
    assert "shape-copy-missing" in findings[0]
    assert not any(MAKEFILE in finding for finding in findings)


def test_a_split_commit_holding_every_pinned_file_has_no_findings(adopter,
                                                                  tmp_path):
    files = {MAKEFILE: MAKEFILE_BODY, ATTRIBUTES: "* text=auto\n",
             PIN: pin_of(MAKEFILE, ATTRIBUTES)}
    repo, commit = split_commit_of(tmp_path, files, ignore="build/\n")
    assert adopter._shape_file_findings(repo, commit) == []


def test_a_split_commit_with_no_pin_is_one_finding_about_the_pin(adopter,
                                                                 tmp_path):
    repo, commit = split_commit_of(tmp_path, {MAKEFILE: MAKEFILE_BODY})
    findings = adopter._shape_file_findings(repo, commit)
    assert len(findings) == 1, findings
    assert findings[0].startswith(
        f"{MISSING} {PIN} is the pin that lists the shape's files and is not "
        "in the split commit")


@pytest.mark.parametrize("pin", [
    "kind: pinned_contract_manifest\n",
    "files:\n  - sha256: \"abc\"\n",
    f"files:\n\t- path: {MAKEFILE}\n",
], ids=["no-files-block", "row-without-a-path", "not-parseable"])
def test_a_pin_that_is_not_a_list_of_paths_fails_closed(adopter, tmp_path,
                                                        pin):
    """One finding, never a quiet pass: a pin that names nothing would make
    every pinned file look present."""
    repo, commit = split_commit_of(tmp_path,
                                   {MAKEFILE: MAKEFILE_BODY, PIN: pin})
    findings = adopter._shape_file_findings(repo, commit)
    assert len(findings) == 1, findings
    assert findings[0].startswith(
        f"FINDING adopt-shape-pin-unreadable: {PIN} in the split commit")


def test_a_gitlink_at_a_pinned_path_is_not_the_pinned_file(adopter, tmp_path):
    repo, commit = split_commit_of(tmp_path, {PIN: pin_of("spec")},
                                   ignore="build/\n")
    git("update-index", "--add", "--cacheinfo", f"160000,{commit},spec",
        cwd=repo)
    git("-c", "user.name=T", "-c", "user.email=t@invalid.example", "commit",
        "-qm", "Mount", cwd=repo)
    head = git("rev-parse", "HEAD", cwd=repo).stdout.strip()
    findings = adopter._shape_file_findings(repo, head)
    assert [f.split(" is named", 1)[0] for f in findings] == \
        [f"{MISSING} spec"]


# ---------------------------------------------------------------------------
# End to end, through `execute`
# ---------------------------------------------------------------------------


def adoption_plan(source: Path, base: Path) -> Path:
    plan = base / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    return plan


def source_with_hidden_files(base: Path, own_attributes: bool) -> Path:
    source = make_source_repo(base / "Thing", tree=SOURCE_TREE)
    if own_attributes:
        (source / ATTRIBUTES).write_text(OWN_ATTRIBUTES)
        git("add", "-f", "--", ATTRIBUTES, cwd=source)
        commit_all(source, "Track our own attributes")
    for name, body in STRAY.items():
        (source / name).parent.mkdir(parents=True, exist_ok=True)
        (source / name).write_text(body)
    for name in (ATTRIBUTES, WORKFLOW):
        assert git("check-ignore", "-q", "--no-index", name, cwd=source,
                   check=False).returncode == 0, f"{name} is not hidden"
    return source


@pytest.fixture(scope="module", params=[False, True],
                ids=["no-attributes-of-its-own", "its-own-attributes"])
def adopted(request, tmp_path_factory) -> SimpleNamespace:
    """One real adoption of a source with NO submodules and the `.gitignore`
    above; the second variant tracks a `.gitattributes` of its own, which
    sends the shape's copy to `shape/.gitattributes`, hidden by `.*` again."""
    base = tmp_path_factory.mktemp("ignored")
    source = source_with_hidden_files(base, request.param)
    plan = adoption_plan(source, base)
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(base / "remotes"),
                        "--work-dir", str(base / "work"))
    return SimpleNamespace(
        source=source, own=request.param, result=result,
        attributes=f"shape/{ATTRIBUTES}" if request.param else ATTRIBUTES)


@needs_filter_repo
def test_the_split_lands_the_files_the_pin_names(adopted):
    result = adopted.result
    assert result.returncode == 0, result.stderr + result.stdout
    assert "adoption verified" in result.stdout

    tree = committed(adopted.source, BRANCH)
    assert {adopted.attributes, WORKFLOW, PIN} <= tree
    pin = parse_yaml(git("show", f"{BRANCH}:{PIN}", cwd=adopted.source).stdout)
    rows = {row["path"] for row in pin["files"]}
    assert {adopted.attributes, WORKFLOW} <= rows
    assert rows <= tree, f"pinned but not in the split: {sorted(rows - tree)}"
    if adopted.own:
        # Beside, not over: the source's own bytes are where they were.
        assert git("show", f"{BRANCH}:{ATTRIBUTES}",
                   cwd=adopted.source).stdout == OWN_ATTRIBUTES


@needs_filter_repo
def test_the_assembly_bootstraps_where_it_failed_with_shape_copy_missing(
        adopted, tmp_path):
    clone = tmp_path / PROJECT
    git(*FILE_PROTOCOL, "clone", "-q", "--recurse-submodules", "-b", BRANCH,
        str(adopted.source), str(clone), cwd=tmp_path)
    bootstrapped = run_script(clone / "scripts" / "bootstrap.py", cwd=clone)
    output = bootstrapped.stderr + bootstrapped.stdout
    assert "shape-copy-missing" not in output, output
    assert bootstrapped.returncode == 0, output


def execute_in_process(adopter, tmp_path: Path, monkeypatch) -> tuple:
    """`execute` run in THIS process, so a test can patch one step of it:
    `(source, exit code)`. What `run_script` blanks for a child is blanked
    here too."""
    monkeypatch.setenv("LANES_LANE", "")
    clear_ambient_pin_sources(monkeypatch)
    source = source_with_hidden_files(tmp_path, own_attributes=False)
    plan = adoption_plan(source, tmp_path)
    code = adopter.main(["execute", "--plan", str(plan), "--yes",
                         "--local-remote-dir", str(tmp_path / "remotes"),
                         "--work-dir", str(tmp_path / "work")])
    return source, code


@needs_filter_repo
def test_a_file_the_gitignore_hides_is_not_swept_into_the_split(
        adopter, tmp_path, monkeypatch, capsys):
    """Nothing but the shape's paths is forced, through `execute` itself.

    The source holds STRAY untracked and hidden, so they were never in the
    commit `execute` clones; the same names are therefore ALSO written into
    the clone the moment the shape is, which is the only way an ignored file
    can be on the disk when the split is staged -- and where a `-f .` would
    take it."""
    materialize = adopter.materialize_assembly_root

    def materialize_then_litter(shape_root, target, values, **options):
        materialized = materialize(shape_root, target, values, **options)
        for name, body in STRAY.items():
            (target / name).parent.mkdir(parents=True, exist_ok=True)
            (target / name).write_text(body)
        return materialized

    monkeypatch.setattr(adopter, "materialize_assembly_root",
                        materialize_then_litter)
    source, code = execute_in_process(adopter, tmp_path, monkeypatch)

    seen = capsys.readouterr()
    assert code == 0, seen.err + seen.out
    tree = committed(source, BRANCH)
    assert {ATTRIBUTES, WORKFLOW} <= tree
    for name, body in STRAY.items():
        assert name not in tree
        assert (source / name).read_text() == body, \
            "the source's own working tree was touched"


@needs_filter_repo
def test_execute_fails_at_verification_when_the_split_lacks_a_pinned_file(
        adopter, tmp_path, monkeypatch, capsys):
    """The verification half, wired into `execute`: with the staging put back
    as it was before #167, `execute` no longer says `adoption verified` -- it
    exits 1 naming each file, instead of leaving it to the first bootstrap."""
    def plain_add(assembly, materialized):
        del materialized
        adopter.run(["git", "add", "-A", "--", "."], cwd=assembly)

    monkeypatch.setattr(adopter, "_stage_the_split", plain_add)
    source, code = execute_in_process(adopter, tmp_path, monkeypatch)

    seen = capsys.readouterr()
    assert code == 1, seen.err + seen.out
    assert f"{MISSING} {ATTRIBUTES} " in seen.err
    assert f"{MISSING} {WORKFLOW} " in seen.err
    assert "adoption verified" not in seen.out
    assert ATTRIBUTES not in committed(source, BRANCH)
