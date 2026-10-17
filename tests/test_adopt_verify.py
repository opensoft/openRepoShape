# SPDX-License-Identifier: Apache-2.0
"""Verification passes over the two leg mounts and NO OTHER gitlink (#165).

`_verify` used to skip every gitlink in the root tree. The shape adds exactly
two, the mounts at `spec_path` and `code_path`; any other one is a path like a
blob, and skipping it hid a source submodule the root kept (reported lost),
one the split failed to remove (in a leg AND the root, counted once) and one
nobody asked for (not even counted as added). Every other one is also a
finding of its own: the root keeps no gitlink but the two mounts, so the
check FAILS CLOSED on one rather than trusting `check`'s refusals to have
kept it out.

THE ROOT'S `project.yaml` IS THE SHAPE'S MANIFEST, or the run fails (#389).
`check` finds, and `execute` refuses before any leg exists, a plan that keeps
the source's own `project.yaml` in the root (#305), and that refusal was all
there was: `_verify` asked nothing about the manifest, so with it taken away
the run wrote the shape's manifest beside the source's file as
`shape/project.yaml` and said `adoption verified` over an assembly the doctor
calls NOT A SHAPE ROOT. That is a finding of its own now, which fails closed
as the gitlink checks do.

EVERY TEST BUT THE LAST THREE CALLS `_verify` DIRECTLY on hand-made commits,
their gitlinks written with `git update-index --cacheinfo 160000,...`. No `git
filter-repo` is involved, so a machine that has none still runs all of
those. The last three run `execute`, so they need `git filter-repo` and are
skipped without it, as every `execute` test is: one proves `cmd_execute` hands
`_verify` the PLAN'S mount paths and that the assembly clones and bootstraps
from them, the other two that a source submodule, and the source's own
`project.yaml`, that a broken plan check let into the root fail the run.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import (ADOPT, FILE_PROTOCOL, REPO, SYNTHETIC_TREE,
                      clone_just_pushed, git, make_source_repo, resolve,
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
#: Where `execute` pushed the two legs. `_verify` names them in the way out
#: it prints after a finding (#188), with the split branch; nothing here is
#: pushed to them.
URLS = {role: f"https://github.com/testorg/{name}.git"
        for role, name in NAMES.items()}
#: The source file the plan sends to the code leg.
APP = "src/app.py"
SOURCE_FILES = {"README.md": "# Thing\n", "specs/a.md": "# A\n",
                APP: "VALUE = 1\n"}
#: Each leg holds the source path the plan moved to it, at the same bytes.
LEG_FILES = {"spec": {"specs/a.md": "# A\n"},
             "code": {APP: "VALUE = 1\n"}}
#: The line `_verify` prints only when it found nothing.
VERIFIED = "adoption verified"
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

#: How every root-tree gitlink finding ends, spelled out here rather than read
#: from adopt-project.py, so a change to it fails this file.
SPLIT_IS_WRONG = ("so the split itself is wrong: do not merge it, and report "
                  f"it to {SHAPE_REPOSITORY}")
#: `adopt-unexpected-gitlink` and `adopt-mount-missing`: since #169 a leg path
#: git would record at another spelling never reaches a leg.
EXIT = ("this is not how the plan spells its leg paths: `execute` refuses "
        "before any leg exists a leg path git would record at another "
        f"spelling (`plan-bad-leg-path`), {SPLIT_IS_WRONG}")
#: `adopt-root-submodule`: since #166 and #168 no plan `execute` runs keeps
#: one of the source's submodules in the root.
ROOT_EXIT = ("`execute` refuses before any leg exists a plan that keeps a "
             "submodule of the source's in the root (`plan-submodule-root`) "
             "or leaves one with no leg (`plan-unresolved`, "
             f"`plan-uncovered`, `plan-bad-leg`), {SPLIT_IS_WRONG}")

#: The shape's manifest, the source's own file of that name, and where
#: `execute` writes the manifest when the root already holds one (#389).
MANIFEST = "project.yaml"
THEIRS = "name: theirs\n"
MANIFEST_COPY = f"shape/{MANIFEST}"
#: What `adopt-manifest-not-shape` says after its first sentence: since #305
#: and #172 no plan `execute` runs keeps a path of the source's at
#: `project.yaml` or mounts a leg there.
MANIFEST_EXIT = (
    "`shape-doctor.py`, the root's validators and `make bootstrap` read the "
    "manifest at `project.yaml` itself, and no copy stands in for it; "
    "`execute` refuses before any leg exists a plan that keeps a path of the "
    "source's at `project.yaml` in the root (`plan-root-blocks-manifest`) or "
    f"mounts a leg there (`plan-leg-path-collides`), {SPLIT_IS_WRONG}")
#: Its first sentence for the manifest beside a root `project.yaml` that is
#: not the source's own.
BESIDE = (f"the shape's manifest is at `{MANIFEST_COPY}` in the root tree, "
          f"where it is written only when the root already holds `{MANIFEST}`")


def manifest_not_shape(said: str) -> str:
    """The `adopt-manifest-not-shape` finding whose first sentence is
    `said`."""
    return f"FINDING adopt-manifest-not-shape: {said}. {MANIFEST_EXIT}"


def kept_manifest(oid: str, beside: bool) -> str:
    """The finding for the source's own `project.yaml` at `oid` left in the
    root, with the shape's manifest `beside` it or not."""
    return manifest_not_shape(
        f"`{MANIFEST}` in the root tree is the source's own file "
        f"({oid[:12]}), not the shape's manifest"
        + (f", which is beside it as `{MANIFEST_COPY}`" if beside else ""))


def root_submodule(path: str, sha: str) -> str:
    """The `adopt-root-submodule` finding for the source's own `path`."""
    return (f"FINDING adopt-root-submodule: `{path}` is a gitlink to "
            f"{sha[:12]} in the root tree, the source's own submodule at its "
            "own commit, and the assembly root keeps no submodule of the "
            "source's: its .gitmodules is reserved for its two leg mounts; "
            f"{ROOT_EXIT}")


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
def adopter():
    """`adopt-project.py` as a module, to call `_verify` and `cmd_execute`."""
    module_spec = importlib.util.spec_from_file_location("adopt_verify",
                                                         ADOPT)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


@pytest.fixture
def verify(adopter, tmp_path, capsys):
    """A factory: build the source, both legs and the split, then `_verify`.

    `source`, `code` and `root` are the gitlinks each one carries beyond its
    files; `mounts` is where the plan mounts each leg, which is what
    `_verify` is told and where the root gets that leg's gitlink unless
    `mounted_at` names another path for it; `unmount` names a leg whose mount
    gitlink the root does NOT get, and `root_files` and `source_files` add
    to the root's files and the source's. Returns `(exit, out, err)`.
    """
    def run(source=None, code=None, root=None, unmount=(), root_files=None,
            drop=(), mounts=DEFAULT_MOUNTS, mounted_at=None,
            source_files=None):
        source_path = tmp_path / "source"
        source_commit = commit(source_path,
                               {**SOURCE_FILES, **(source_files or {})},
                               source)
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
            mounts["code"], urls=dict(URLS, assembly=str(source_path)),
            branch=SPLIT_BRANCH)
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
    assert VERIFIED in out
    assert err == ""


def test_a_source_submodule_the_root_keeps_at_its_commit_is_a_finding(
        verify):
    """Same path, same commit: counted `root`, where it is, AND refused.

    The fixture's root `.gitmodules` registers `spec` alone, as the fresh one
    `execute` writes registers only the two mounts: an assembly like this
    clones with that directory empty. It used to verify.
    """
    verified, out, err = verify(source={SUBMODULE: DEPENDENCY},
                                root={SUBMODULE: DEPENDENCY})
    assert verified == 1
    assert row(out, "root") == "root       2 of 4 source paths"
    assert findings(err) == [root_submodule(SUBMODULE, DEPENDENCY)]
    assert VERIFIED not in out


def test_a_source_submodule_in_no_place_is_lost(verify):
    verified, _, err = verify(source={SUBMODULE: DEPENDENCY})
    assert verified == 1
    assert findings(err) == [
        f"FINDING adopt-lost: `{SUBMODULE}` ({DEPENDENCY[:12]}) is in no "
        "leg, not in the root tree, and not listed as drop"]


def test_a_dropped_source_submodule_is_counted_as_dropped(verify):
    verified, out, err = verify(source={SUBMODULE: DEPENDENCY},
                                drop=("upstream/",))
    assert verified == 0, err
    assert row(out, "drop") == "drop       1 of 4 source paths"


def test_a_source_submodule_in_a_leg_and_the_root_is_duplicated(verify):
    """The split failed to remove it: two owners for one submodule, and a
    submodule of the source's in the root besides. Two facts, two findings:
    neither rule covers the other, since a blob can be duplicated too and a
    submodule can sit in the root alone."""
    verified, _, err = verify(source={SUBMODULE: DEPENDENCY},
                              code={SUBMODULE: DEPENDENCY},
                              root={SUBMODULE: DEPENDENCY})
    assert verified == 1
    assert findings(err) == [f"FINDING adopt-duplicated: `{SUBMODULE}` is in "
                             f"code:{DEPENDENCY}, root:{DEPENDENCY}",
                             root_submodule(SUBMODULE, DEPENDENCY)]


@pytest.mark.parametrize("path, world", [
    ("vendor/extra", {}),
    (SUBMODULE, {"source": {SUBMODULE: DEPENDENCY},
                 "code": {SUBMODULE: DEPENDENCY}}),
    (APP, {}),
], ids=["at-a-path-the-source-never-had",
        "at-the-source-submodule-path-at-another-commit",
        "at-a-path-where-the-source-had-a-blob"])
def test_a_gitlink_the_shape_did_not_add_is_a_finding(verify, path, world):
    """Neither a mount nor the source's submodule at its own commit.

    The second case moved the source's submodule to the code leg, and the
    third holds a gitlink where the source had the file the code leg took,
    so every source path is accounted for: only the root's gitlink is wrong,
    and a rule that matched the PATH alone would call either the source's
    own submodule.
    """
    verified, _, err = verify(root={path: ELSEWHERE}, **world)
    assert verified == 1
    assert findings(err) == [
        f"FINDING adopt-unexpected-gitlink: `{path}` is a gitlink to "
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

    `spec/` is the case `execute` reached until #169: `git submodule add`
    records that mount at `spec`. `plan`, `check` and `execute` now refuse
    the spelling before any leg exists, and `_verify`, asked it directly,
    still fires both findings. `legs/spec` with the gitlink at `spec` is
    what a `_verify` that knew only the default would pass.
    """
    verified, _, err = verify(mounts=mounts, mounted_at={"spec": "spec"})
    head = git("rev-parse", "HEAD",
               cwd=tmp_path / "work" / NAMES["spec"]).stdout.strip()
    assert verified == 1
    assert findings(err) == [
        "FINDING adopt-unexpected-gitlink: `spec` is a gitlink to "
        f"{head[:12]} in the root tree, and neither a leg mount as the plan "
        f"spells their paths ({mounts['code']}, {mounts['spec']}) nor the "
        f"source's own submodule at that commit; {EXIT}",
        f"FINDING adopt-mount-missing: the root tree has nothing at "
        f"{mounts['spec']} as the plan spells it, where the gitlink that "
        f"mounts the spec leg belongs; {EXIT}"]
    # The exit is the plan's unless a finding names another, as these do.
    # What the run left to clear first, the legs and the split branch,
    # follows it (#188).
    assert ("verification finding(s). NOTHING was deleted from the source, "
            "so the exit is to fix the plan and re-run, unless a finding "
            "above names another exit.\n") in err


def test_the_manifest_beside_the_roots_project_yaml_is_a_finding(verify):
    """`execute` writes the manifest to `shape/project.yaml` only when the
    root already holds `project.yaml`, so the root's is not the manifest,
    whatever it is: a leg mounted there (#172), a case twin on a disk that
    ignores case. The fixture's root holds a stand-in no source path is."""
    verified, out, err = verify(
        root_files={MANIFEST_COPY: ROOT_FILES[MANIFEST]})
    assert verified == 1
    assert findings(err) == [manifest_not_shape(BESIDE)]
    assert VERIFIED not in out


@pytest.mark.parametrize("beside", [True, False], ids=[
    "the-manifest-beside-it", "the-manifest-nowhere"])
def test_the_sources_own_project_yaml_in_the_root_is_a_finding(
        verify, tmp_path, beside):
    """Counted `root`, where it is, AND refused: every source path is in
    exactly one place, and the root still reads the source's file where the
    manifest belongs. Beside it is #305's split. With no copy beside it, it
    is the split a kept symlink at `project.yaml` that leads nowhere makes:
    the manifest is written through the link, and the root keeps the link,
    a file here, which the check does not tell apart."""
    copy = {MANIFEST_COPY: ROOT_FILES[MANIFEST]} if beside else {}
    verified, out, err = verify(source_files={MANIFEST: THEIRS},
                                root_files={MANIFEST: THEIRS, **copy})
    own = git("rev-parse", f"HEAD:{MANIFEST}",
              cwd=tmp_path / "source").stdout.strip()
    assert verified == 1
    assert row(out, "root") == "root       2 of 4 source paths"
    assert findings(err) == [kept_manifest(own, beside)]
    assert VERIFIED not in out


@pytest.mark.parametrize("source_files, root_files", [
    (None, {"shape/README.md": "# The shape's README\n"}),
    ({MANIFEST_COPY: THEIRS}, {MANIFEST_COPY: THEIRS}),
], ids=["the-copy-of-a-kept-readme", "the-sources-own-shape-project-yaml"])
def test_what_else_the_root_holds_under_shape_still_verifies(
        verify, source_files, root_files):
    """Not over-refused. A kept `README.md` with the shape's copy beside it
    is the designed follow-up merge; the source's own `shape/project.yaml`,
    kept where the root's `project.yaml` is the manifest, is no copy the
    shape wrote."""
    verified, out, err = verify(source_files=source_files,
                                root_files=root_files)
    assert verified == 0, err
    assert VERIFIED in out
    assert err == ""


@pytest.mark.parametrize("beside", [False, True], ids=[
    "the-manifest-at-the-root", "the-manifest-beside-it"])
def test_a_dropped_project_yaml_is_never_the_sources_own(verify, beside):
    """The plan dropped it, so the split `git rm`ed it before the shape
    wrote, and what is at `project.yaml` is the shape's, whatever its bytes.
    A source file that held exactly the manifest this run renders (here the
    fixture's stand-in), answered `drop`, passes `check` and verified on
    main; matched by blob alone, this check refused it as the source's own
    (#389's review, R1). Only that half is waived: the manifest beside the
    root's is a finding still."""
    copy = {MANIFEST_COPY: ROOT_FILES[MANIFEST]} if beside else {}
    verified, out, err = verify(source_files={MANIFEST: ROOT_FILES[MANIFEST]},
                                root_files=copy, drop=(MANIFEST,))
    assert verified == (1 if beside else 0), err
    assert findings(err) == ([manifest_not_shape(BESIDE)] if beside else [])
    assert (VERIFIED in out) == (not beside)


#: `execute` REQUIRES `git filter-repo`; without it, the three tests below are
#: skipped, as every `execute` test in this suite is.
needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

#: The questions `plan` leaves open on SYNTHETIC_TREE, answered as
#: tests/test_adopt_e2e.py answers them.
ANSWERS = (("examples/", "spec"), (".claude/", "root"),
           ("release.yaml", "root"))
#: The branch `execute` pushes the split to.
SPLIT_BRANCH = "adopt/three-repo-shape"


def clone_the_split(source: Path, tmp_path: Path):
    """`git clone --recurse-submodules` of the split branch into
    `tmp_path/clone`: what the NEXT lines tell the human to run."""
    return clone_just_pushed(source, tmp_path / "clone", SPLIT_BRANCH)


@needs_filter_repo
def test_execute_verifies_the_mounts_where_the_plan_puts_them(tmp_path):
    """`plan --spec-path legs/spec --code-path impl/code`, then `execute`,
    then the two commands its NEXT lines name.

    `cmd_execute` must hand `_verify` the PLAN'S two paths: one that passed
    `spec` and `code` would fail this correct adoption on four findings. The
    work directory is moved away before the clone, so the clone fetches each
    leg from the URL the root `.gitmodules` records, and not from the
    working copy the mount was made from.
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
    assert VERIFIED in result.stdout
    tree = git("ls-tree", "-r", SPLIT_BRANCH, cwd=source).stdout
    gitlinks = sorted(line.split("\t", 1)[1] for line in tree.splitlines()
                      if line.startswith("160000 "))
    assert gitlinks == sorted(NESTED_MOUNTS.values())

    (tmp_path / "work").rename(tmp_path / "work-moved-away")
    cloned = clone_the_split(source, tmp_path)
    assert cloned.returncode == 0, cloned.stderr
    clone = tmp_path / "clone"
    assert (clone / NESTED_MOUNTS["spec"] / "specs/001-feature/spec.md") \
        .is_file()
    assert (clone / NESTED_MOUNTS["code"] / "src/app/util.py").is_file()
    bootstrapped = run_script(clone / "scripts/bootstrap.py", cwd=clone)
    assert bootstrapped.returncode == 0, \
        bootstrapped.stderr + bootstrapped.stdout
    assert "NOT INITIALIZED" not in bootstrapped.stdout


def checked_plan(source: Path, tmp_path: Path, answers: tuple):
    """`plan` of `source` with ANSWERS and `answers` written in, and what
    `check` says of it: `(plan, check's result)`."""
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan)
    assert written.returncode == 0, written.stderr + written.stdout
    for path, leg in (*ANSWERS, *answers):
        resolve(plan, path, leg)
    return plan, run_script(ADOPT, "check", "--plan", str(plan))


def execute_past_check(adopter, monkeypatch, capsys, tmp_path: Path,
                       plan: Path):
    """`execute` of `plan` with `check`'s refusals taken away, as a
    regression in a plan check would take them: `(exit, out, err)`."""
    monkeypatch.setattr(adopter, "_refuse_what_check_finds",
                        lambda *_: None)
    exit_code = adopter.cmd_execute(Namespace(
        plan=str(plan), source=None, local_remote_dir=tmp_path / "remotes",
        allow_empty_leg=[], yes=True, work_dir=tmp_path / "work"))
    out, err = capsys.readouterr()
    return exit_code, out, err


@needs_filter_repo
def test_execute_fails_a_source_submodule_the_plan_checks_let_into_the_root(
        adopter, tmp_path, capsys, monkeypatch):
    """THE CHECK FAILS CLOSED: it does not lean on the plan checks before it.

    `.gitmodules` to the code leg and `upstream/` to the root is
    `plan-submodule-root`, which `check` finds and `execute` refuses before
    any leg exists (#166, #168). With that refusal taken away, as a
    regression in either would take it, the run goes on to a split whose
    root keeps the source's submodule beside a fresh `.gitmodules` that does
    not register it, and the verification must refuse it rather than say
    `adoption verified`.
    """
    dependency = make_source_repo(tmp_path / "dependency",
                                  tree={"value.txt": "dependency\n"},
                                  edits=())
    source = make_source_repo(tmp_path / "Thing")
    git(*FILE_PROTOCOL, "submodule", "add", "-q", str(dependency), SUBMODULE,
        cwd=source)
    git("-c", "user.name=Source Human", "-c",
        "user.email=source@invalid.example", "commit", "-qm",
        "Pin a dependency", cwd=source)
    pinned = git("rev-parse", f"HEAD:{SUBMODULE}", cwd=source).stdout.strip()
    plan, checked = checked_plan(source, tmp_path, ((".gitmodules", "code"),
                                                    ("upstream/", "root")))
    assert checked.returncode == 1
    assert (f"FINDING plan-submodule-root: `{SUBMODULE}` (entry "
            "`upstream/`) has leg: root") in checked.stderr

    exit_code, out, err = execute_past_check(adopter, monkeypatch, capsys,
                                             tmp_path, plan)
    assert exit_code == 1, out + err
    assert findings(err) == [root_submodule(SUBMODULE, pinned)]
    assert VERIFIED not in out


@needs_filter_repo
def test_execute_fails_a_source_manifest_the_plan_checks_let_into_the_root(
        adopter, tmp_path, capsys, monkeypatch):
    """#305's run, with its refusal taken away (#389).

    `project.yaml` answered `root` is `plan-root-blocks-manifest`, which
    `check` finds and `execute` refuses before any leg exists. Taken away,
    the run writes the shape's manifest beside the source's own file as
    `shape/project.yaml`, and on main it said `adoption verified` over a
    root whose `project.yaml` the doctor reads as NOT A SHAPE ROOT. The
    shape's other copies beside a kept file (`shape/README.md`,
    `shape/Makefile`, `shape/AGENTS.md`) are the designed follow-up, and
    no finding.
    """
    source = make_source_repo(tmp_path / "Thing",
                              tree={**SYNTHETIC_TREE, MANIFEST: THEIRS})
    own = git("rev-parse", f"HEAD:{MANIFEST}", cwd=source).stdout.strip()
    plan, checked = checked_plan(source, tmp_path, ((MANIFEST, "root"),))
    assert checked.returncode == 1
    assert "FINDING plan-root-blocks-manifest: the plan keeps the file " \
        f"`{MANIFEST}` in the assembly root, " in checked.stderr

    exit_code, out, err = execute_past_check(adopter, monkeypatch, capsys,
                                             tmp_path, plan)
    assert exit_code == 1, out + err
    assert f"  beside  {MANIFEST_COPY} (the source already has " \
        f"{MANIFEST}; nothing was overwritten)" in out
    assert "  beside  shape/README.md (" in out
    assert findings(err) == [kept_manifest(own, beside=True)]
    assert VERIFIED not in out
