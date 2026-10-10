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
the split commit. Both read a path the way a checkout does, through any
symlink the plan kept in the root: the forced add stages a file where the link
put it, and the check finds a pinned file through the split tree's own links,
so it agrees with the first bootstrap. All repositories and remotes are local
fixtures; no network is used. The end-to-end tests need `git filter-repo`; the
others do not, so they run on the Windows job, which installs none -- except
the ones that make a symlink on the DISK, which skip there.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

import pytest

from conftest import (ADOPT, FILE_PROTOCOL, REPO, clear_ambient_pin_sources,
                      git, make_source_repo, resolve, run_script, write_plan)

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

#: What the tests with a symlink ON THE DISK need. Git for Windows checks a
#: tracked symlink out as a plain file unless `core.symlinks` is on, and a
#: runner may make one only in Developer Mode or elevated; the defect they
#: guard is a POSIX layout, and the POSIX legs of CI run them. The tests that
#: put a symlink only in a TREE (`update-index --cacheinfo`) need neither, and
#: run everywhere.
needs_disk_symlinks = pytest.mark.skipif(
    sys.platform == "win32",
    reason="a tracked symlink is a plain file in a Windows checkout")


def symlink(link: Path, target: str) -> None:
    """`link -> target`, or a skip where this runner cannot make one."""
    try:
        os.symlink(target, link)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"this platform cannot create a symlink here: {exc}")


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
#: The two exits every shape-file finding names, and the ONLY two: the plan
#: answer the footer and AGENTS.md give, and a defect report. Never a
#: hand-staged push of a split nobody re-verifies.
PLAN_ANSWER = ("send that path to a leg or `drop` it, and re-run into fresh "
               "legs")
DEFECT = "do not merge it, and report it to opensoft/openRepoShape"
#: The mode `git ls-tree` reports for a symlink.
SYMLINK = "120000"
#: Where the shape's own pin lands when the source keeps one of its own.
COLLISION_PIN = f"shape/{PIN}"
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


def commit_index(repo: Path, message: str) -> None:
    git("-c", "user.name=Source Human", "-c",
        "user.email=source@invalid.example", "commit", "-qm", message,
        cwd=repo)


def commit_all(repo: Path, message: str) -> None:
    git("add", "-A", "--", ".", cwd=repo)
    commit_index(repo, message)


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


@needs_disk_symlinks
def test_a_file_written_through_a_symlink_is_staged_where_it_landed(adopter,
                                                                    tmp_path):
    """The plan kept `.github -> ci` in the root, so the shape's workflow
    was written THROUGH the link: git tracks it at `ci/workflows/`, and
    refuses the written spelling as a pathspec "beyond a symbolic link". A
    link that leads OUT of the assembly is not staged at all: what it wrote
    is in no repository, and the verification reports the file missing."""
    source = make_source_repo(
        tmp_path / "source", edits=(),
        tree={README: "# Thing\n", IGNORE_FILE: "build/\n",
              "ci/workflows/ci.yml": "on: [push]\n"})
    symlink(source / ".github", "ci")
    symlink(source / "out", "../elsewhere")
    commit_all(source, "Link .github, and a directory outside")
    assembly = tmp_path / "assembly"
    git("clone", "-q", str(source), str(assembly), cwd=tmp_path)
    (tmp_path / "elsewhere").mkdir()
    written = [WORKFLOW, "out/landed.txt", PIN]
    write_files(assembly, written)
    assert (assembly / "ci" / "workflows" / "validate.yml").is_file()
    assert (tmp_path / "elsewhere" / "landed.txt").is_file()

    materialized = Materialized()
    materialized.written = written
    adopter._stage_the_split(assembly, materialized)

    staged = git("diff", "--cached", "--name-status",
                 cwd=assembly).stdout.splitlines()
    assert sorted(staged) == ["A\tci/workflows/validate.yml", f"A\t{PIN}"]


# ---------------------------------------------------------------------------
# The verification fails when a pinned file is not in the split commit
# ---------------------------------------------------------------------------

SHA = "0" * 64


def pin_of(*paths: str) -> str:
    rows = "".join(f"  - path: {path}\n    sha256: \"{SHA}\"\n"
                   for path in paths)
    return f"schema_version: 1\nkind: pinned_contract_manifest\nfiles:\n{rows}"


def split_commit_of(tmp_path: Path, files: dict, ignore: str = IGNORE_DOTFILES,
                    disk_only: tuple = (), links: dict | None = None) -> tuple:
    """A tiny assembly repo whose ONE commit is whatever `git add -A` takes
    under `ignore`, and `(repo, that commit)`. `disk_only` files are written
    after the commit, so the working tree has them and the commit does not.

    `links` maps a path to a symlink target, put in the commit's TREE only
    (mode 120000, the target as its blob), never on the disk: a tree is all
    the check reads, and it needs no symlink privilege on any platform."""
    repo = tmp_path / "assembly"
    repo.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=repo)
    for name, body in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(body)
    (repo / IGNORE_FILE).write_text(ignore)
    git("add", "-A", "--", ".", cwd=repo)
    for link, target in (links or {}).items():
        blob = subprocess.run(
            ["git", "hash-object", "-w", "--stdin"], cwd=str(repo),
            input=target, capture_output=True, text=True, check=True)
        git("update-index", "--add", "--cacheinfo",
            f"{SYMLINK},{blob.stdout.strip()},{link}", cwd=repo)
    commit_index(repo, "The split")
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
        f"commit {commit[:12]}, so the assembly's first `make bootstrap` "
        "refuses with shape-copy-missing. ")
    assert findings[1].startswith(f"{MISSING} {WORKFLOW} ")
    assert not any(MAKEFILE in finding for finding in findings)
    for finding in findings:
        # What to do: the exit the footer under it and AGENTS.md give, or a
        # defect report. Not the `.gitignore` diagnosis the forced add has
        # made impossible, and not a `git add -f` that fails "beyond a
        # symbolic link" or on a file the plan sent to a leg.
        assert PLAN_ANSWER in finding and DEFECT in finding
        assert COLLISION_PIN in finding
        assert "gitignore" not in finding and "git add" not in finding
        assert "push" not in finding


def test_a_split_commit_holding_every_pinned_file_has_no_findings(adopter,
                                                                  tmp_path):
    files = {MAKEFILE: MAKEFILE_BODY, ATTRIBUTES: "* text=auto\n",
             PIN: pin_of(MAKEFILE, ATTRIBUTES)}
    repo, commit = split_commit_of(tmp_path, files, ignore="build/\n")
    assert adopter._shape_file_findings(repo, commit) == []


def test_a_split_commit_with_no_pin_is_one_finding_about_the_pin(adopter,
                                                                 tmp_path):
    """With no pin, `validate-pins.py` refuses with `shape-pin-missing`
    before it reads a row, so that is the refusal the finding names."""
    repo, commit = split_commit_of(tmp_path, {MAKEFILE: MAKEFILE_BODY})
    findings = adopter._shape_file_findings(repo, commit)
    assert len(findings) == 1, findings
    assert findings[0].startswith(
        f"{MISSING} {PIN} is the pin that lists the shape's files and is not "
        f"in the split commit {commit[:12]}, so the assembly's first `make "
        "bootstrap` refuses with shape-pin-missing. ")
    assert "shape-copy-missing" not in findings[0]
    assert PLAN_ANSWER in findings[0] and DEFECT in findings[0]


@pytest.mark.parametrize("pin", [
    "kind: pinned_contract_manifest\n",
    "files:\n  - sha256: \"abc\"\n",
    f"files:\n\t- path: {MAKEFILE}\n",
    "files: []\n",
], ids=["no-files-block", "row-without-a-path", "not-parseable",
        "an-empty-list"])
def test_a_pin_that_is_not_a_list_of_paths_fails_closed(adopter, tmp_path,
                                                        pin):
    """One finding, never a quiet pass: a pin that names nothing would make
    every pinned file look present. It says what to do, too: the source's
    own pin kept in the root is the plan answer that gets here."""
    repo, commit = split_commit_of(tmp_path,
                                   {MAKEFILE: MAKEFILE_BODY, PIN: pin})
    findings = adopter._shape_file_findings(repo, commit)
    assert len(findings) == 1, findings
    assert findings[0].startswith(
        f"FINDING adopt-shape-pin-unreadable: {PIN} in the split commit")
    assert COLLISION_PIN in findings[0]
    assert PLAN_ANSWER in findings[0] and DEFECT in findings[0]


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


#: `(files, links)` of a split commit in which every pinned file is found
#: THROUGH the tree's own symlinks, as a checkout of it finds them -- and as
#: the first bootstrap's `validate-pins.py` does, which opens the pinned name.
FOUND_THROUGH_LINKS = [
    pytest.param({"ci/workflows/validate.yml": "on: [push]\n",
                  PIN: pin_of(WORKFLOW)},
                 {".github": "ci"}, id="a-linked-directory"),
    pytest.param({"config/attributes": OWN_ATTRIBUTES,
                  PIN: pin_of(ATTRIBUTES)},
                 {ATTRIBUTES: "config/attributes"}, id="a-linked-file"),
    pytest.param({"tools/run.sh": "echo\n",
                  "ci/workflows/validate.yml": "on: [push]\n",
                  PIN: pin_of(WORKFLOW)},
                 {".github": "tools/up", "tools/up": "../ci/"},
                 id="a-chain-read-from-each-links-own-directory"),
    pytest.param({"meta/shape-pin.yaml": pin_of(MAKEFILE),
                  MAKEFILE: MAKEFILE_BODY},
                 {"contracts": "meta"}, id="the-pin-itself-behind-a-link"),
]


@pytest.mark.parametrize(("files", "links"), FOUND_THROUGH_LINKS)
def test_a_pinned_path_is_found_through_the_split_trees_symlinks(
        adopter, tmp_path, files, links):
    """The plan kept a symlink in the root and the shape wrote through it:
    the split holds the file where the link leads, and a lookup of the pinned
    NAME in `git ls-tree` alone would call it missing in a split that
    bootstraps."""
    repo, commit = split_commit_of(tmp_path, files, ignore="build/\n",
                                   links=links)
    assert adopter._shape_file_findings(repo, commit) == []


def findings_within(adopter, repo: Path, commit: str,
                    seconds: float = 60) -> list:
    """`_shape_file_findings`, or a FAILURE if it has not answered within
    `seconds`: a symlink loop must end in a finding, and a lookup that goes
    round it for ever has to fail this test rather than hang the run."""
    answer = []
    worker = threading.Thread(
        target=lambda: answer.append(adopter._shape_file_findings(repo,
                                                                  commit)),
        daemon=True)
    worker.start()
    worker.join(seconds)
    assert answer, (f"no answer in {seconds}s: the lookup went round a loop, "
                    "or raised (printed above)")
    return answer[0]


#: `(links, why)`: a pinned path whose symlink leads to no file of the split,
#: and how the finding says so. `{c}` is the split commit's short id.
LEADS_NOWHERE = [
    pytest.param({".github": "/etc"},
                 "leads out of the split commit {c} at the symlink .github, "
                 "to /etc", id="an-absolute-link"),
    pytest.param({".github": "../ci"},
                 "climbs above the root of the split commit {c} at the "
                 "symlink .github", id="a-link-above-the-root"),
    pytest.param({".github": ".github"},
                 "runs round a symlink loop at .github in the split commit "
                 "{c}", id="a-link-to-itself"),
    pytest.param({".github": "loop", "loop": ".github"},
                 "runs round a symlink loop at ", id="a-loop-of-two"),
    pytest.param({".github": "nowhere/../ci"},
                 "passes through nowhere, which is not a directory in the "
                 "split commit {c}",
                 id="through-a-directory-that-is-not-there"),
    pytest.param({".github": "nowhere"},
                 "is not in the split commit {c}", id="a-dangling-link"),
]


@pytest.mark.parametrize(("links", "why"), LEADS_NOWHERE)
def test_a_link_out_of_the_tree_or_round_a_loop_is_a_finding(
        adopter, tmp_path, links, why):
    """Never a hang and never a quiet pass. A checkout finds nothing outside
    the clone, takes `..` only from a directory, and gives up on a loop with
    ELOOP -- and the first bootstrap then refuses with shape-copy-missing --
    even where `ci/workflows/validate.yml` is in the split."""
    repo, commit = split_commit_of(
        tmp_path, {"ci/workflows/validate.yml": "on: [push]\n",
                   PIN: pin_of(WORKFLOW)},
        ignore="build/\n", links=links)
    findings = findings_within(adopter, repo, commit)
    assert len(findings) == 1, findings
    assert findings[0].startswith(f"{MISSING} {WORKFLOW} is named by {PIN} "
                                  "but "), findings[0]
    assert why.format(c=commit[:12]) in findings[0], findings[0]
    assert "refuses with shape-copy-missing. " in findings[0]


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


#: A source with an ordinary `.gitignore` and a `ci/` directory that a
#: tracked symlink `.github -> ci` also names. `plan` asks about both, and the
#: human keeps both in the root.
LINKED_TREE = {
    README: "# Thing\n",
    IGNORE_FILE: "__pycache__/\n*.pyc\n",
    "specs/001-feature/spec.md": "# The feature\n",
    "src/app/main.py": "import contracts_reader\n",
    "ci/workflows/ci.yml": "on: [push]\n",
}


@pytest.fixture(scope="module")
def adopted_through_a_link(tmp_path_factory) -> SimpleNamespace:
    """One real adoption of the LINKED_TREE source: the shape's workflow is
    written through `.github`, to `ci/workflows/validate.yml`. Its tests
    carry `needs_disk_symlinks`, which skips them before it is built."""
    base = tmp_path_factory.mktemp("linked")
    source = make_source_repo(base / "Thing", tree=LINKED_TREE)
    symlink(source / ".github", "ci")
    commit_all(source, "Link .github to ci")
    plan = base / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    for path in (".github", "ci/"):
        resolve(plan, path, "root", "the CI the project runs")
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(base / "remotes"),
                        "--work-dir", str(base / "work"))
    return SimpleNamespace(source=source, result=result)


@needs_filter_repo
@needs_disk_symlinks
def test_a_root_kept_symlink_the_shape_writes_through_adopts(
        adopted_through_a_link):
    """It used to die at the forced add, "beyond a symbolic link", after the
    legs were pushed. The split holds the link and, where it leads, the
    shape's workflow, and the verification finds that file by its pinned
    name, the way the first bootstrap does."""
    result = adopted_through_a_link.result
    assert result.returncode == 0, result.stderr + result.stdout
    assert "adoption verified" in result.stdout
    assert "FINDING" not in result.stderr, result.stderr
    listing = git("ls-tree", "-r", BRANCH,
                  cwd=adopted_through_a_link.source).stdout
    modes = {line.split("\t", 1)[1]: line.split(" ", 1)[0]
             for line in listing.splitlines()}
    assert modes[".github"] == SYMLINK
    assert "ci/workflows/validate.yml" in modes
    assert WORKFLOW not in modes
    pin = parse_yaml(git("show", f"{BRANCH}:{PIN}",
                         cwd=adopted_through_a_link.source).stdout)
    assert WORKFLOW in {row["path"] for row in pin["files"]}


@needs_filter_repo
@needs_disk_symlinks
def test_the_assembly_with_a_root_kept_symlink_bootstraps(
        adopted_through_a_link, tmp_path):
    assert adopted_through_a_link.result.returncode == 0
    clone = tmp_path / PROJECT
    git(*FILE_PROTOCOL, "clone", "-q", "--recurse-submodules", "-b", BRANCH,
        str(adopted_through_a_link.source), str(clone), cwd=tmp_path)
    bootstrapped = run_script(clone / "scripts" / "bootstrap.py", cwd=clone)
    output = bootstrapped.stderr + bootstrapped.stdout
    assert bootstrapped.returncode == 0, output


@needs_filter_repo
def test_a_source_pin_kept_in_the_root_fails_verification_with_the_plan_answer(
        tmp_path):
    """The case the finding is left for once the add is forced: the source
    has a `contracts/shape-pin.yaml` of its OWN, and the plan keeps
    `contracts/` in the root. The shape's pin lands beside it, under
    `shape/`; the one at the pinned path names a file the plan moved to the
    code leg, and the first bootstrap would refuse with shape-copy-missing.
    `execute` says so, with the plan answer as the exit, never a hand edit
    of the split."""
    own_pin = pin_of(README, "src/app/main.py")
    source = make_source_repo(
        tmp_path / "Thing",
        tree={README: "# Thing\n", IGNORE_FILE: "__pycache__/\n",
              "specs/001-feature/spec.md": "# The feature\n",
              "src/app/main.py": "import contracts_reader\n",
              PIN: own_pin})
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    text = plan.read_text(encoding="utf-8")
    entry = "  - path: contracts/\n    leg: spec\n"
    assert entry in text, "plan no longer sends contracts/ to the spec leg"
    plan.write_text(text.replace(
        entry, "  - path: contracts/\n    leg: root\n"
               "    resolution: \"kept beside the shape's own\"\n", 1),
        encoding="utf-8")
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stderr + checked.stdout

    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))

    assert result.returncode == 1, result.stderr + result.stdout
    assert "adoption verified" not in result.stdout
    assert COLLISION_PIN in result.stdout
    findings = [line for line in result.stderr.splitlines()
                if line.startswith("FINDING ")]
    assert len(findings) == 1, result.stderr
    assert findings[0].startswith(
        f"{MISSING} src/app/main.py is named by {PIN} but is not in the split "
        "commit ")
    assert "refuses with shape-copy-missing. " in findings[0]
    assert PLAN_ANSWER in findings[0] and DEFECT in findings[0]
    assert "git add" not in findings[0]
    assert "fix the plan and re-run" in result.stderr
    assert git("show", f"{BRANCH}:{PIN}", cwd=source).stdout == own_pin
