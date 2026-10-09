# SPDX-License-Identifier: Apache-2.0
"""A symlink the plan keeps in the root, at or above a path the shape writes
(#178, #183).

The shape's files are written into the assembly by plain path, so such a link
is followed. Before this, `check` asked nothing about one, and `execute` made
and pushed both legs first. Then, as lane 2's table for #178 recorded on
main: a link that dangles, enters a leg, enters a mount or runs round a loop
ended in a Python traceback; one that leaves the tree had the shape's
`validate.yml` WRITTEN OUTSIDE the assembly. Either way the corrected plan met
`leg-remote-exists`.

Four groups of tests:

- `check` reports each such link, and `execute` refuses it under #168's one
  list of `check`'s findings, before any leg exists. The links are put in
  the source's TREE (`update-index --cacheinfo`), which is all either command
  reads, so these need no symlink privilege and run on Windows too.
- What must NOT be refused: a link whose target the root keeps (followed end
  to end since #167), and one no shape path runs through.
- `core.symlinks=false` (#183): `execute` refuses, before any leg, a link the
  shape would write beneath, because the assembly's clone holds it as a file.
- The materializer's own refusals, for a caller that skipped `check`.

The end-to-end tests at the bottom need `git filter-repo` and a disk that
holds symlinks.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import (ADOPT, FILE_PROTOCOL, REPO, clear_ambient_pin_sources,
                      git, make_source_repo, run_script, write_plan)

sys.path.insert(0, str(REPO / "scripts"))
from shape_materialize import (  # noqa: E402
    PLACEHOLDER_RE, Refusal, assembly_root_paths, materialize_assembly_root,
)

PROJECT = "Northwind"
UTF8 = "utf-8"
REMOTES, WORK = "remotes", "work"
ROOT = "root"
ROOT_SYMLINK = "plan-root-symlink"
FINDING = f"FINDING {ROOT_SYMLINK}: "
BRANCH = "adopt/three-repo-shape"
#: The mode `git ls-tree` reports for a symlink, and for a submodule.
SYMLINK, GITLINK = "120000", "160000"
WORKFLOW = ".github/workflows/validate.yml"
ATTRIBUTES = ".gitattributes"
VALIDATE_PINS = "scripts/validate-pins.py"
README = "README.md"
CI_FILE = "ci/workflows/ci.yml"
ON_PUSH = "on: [push]\n"
RUN_SH = "tools/run.sh"
ECHO = "echo\n"
#: Paths, links and values the cases below share.
GITHUB = ".github"
SCRIPTS = "scripts"
CONTRACTS = "contracts"
SHAPE_DIR = "shape"
TOOLS = "tools"
TOOLS_DIR = "tools/"
TOOLS_UP = "tools/up"
TOOLS_SUB = "tools/sub"
CI_DIR = "ci/"
LOOP = "loop"
CONFIG_DIR = "config/"
CONFIG_ATTRS = "config/attrs"
NOWHERE_ATTRS = "nowhere/attrs"
TOOLING_GH = "tooling/gh"
NOTES_README = "notes/readme.md"
NOTES_UPSTREAM = "notes/upstream"
ETC = "/etc"
OUTSIDE_CI = "../outside-ci"
LATEST = "latest"
BOOTSTRAP_PY = "scripts/bootstrap.py"
SPEC = "spec"
CODE = "code"
THING = "Thing"
PLAN_FILE = "adoption-plan.yaml"
PLAN_FLAG = "--plan"
READ = "read"
ASSEMBLY = "assembly"
BLOCKED = "materialize-blocked"
OUTSIDE = "materialize-outside"
CONFIG_VALUE = "GIT_CONFIG_VALUE_0"
#: `plan` cannot classify a `notes/` holding a link and a readme as one, and
#: lists the two; the readme is answered here and the link with the rest.
NOTES_KEPT = {NOTES_README: ROOT}
#: The arguments every case of a planned source takes.
PLANNED = ("files", "links", "legs")

#: The source every case starts from. `make_source_repo`'s later commits edit
#: the specification and `src/app/main.py`, so both are here.
BASIC = {README: "# Thing\n",
         "specs/001-feature/spec.md": "# The feature\n",
         "src/app/main.py": "import contracts_reader\n"}

#: `git` told to check a symlink out as a plain file, the way Git for
#: Windows' default does, or `git init` on a filesystem without symlinks.
#: `GIT_CONFIG_*` outranks every configuration file.
SYMLINKS_OFF = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.symlinks",
                CONFIG_VALUE: "false"}
SYMLINKS_ON = {**SYMLINKS_OFF, CONFIG_VALUE: "true"}

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

#: What the tests with a symlink ON THE DISK need, as in
#: `test_adopt_ignored_shape_files.py`: Git for Windows checks a tracked
#: symlink out as a plain file unless `core.symlinks` is on, and a runner may
#: make one only in Developer Mode or elevated.
needs_disk_symlinks = pytest.mark.skipif(
    sys.platform == "win32",
    reason="a tracked symlink is a plain file in a Windows checkout")


def symlink(link: Path, target: str) -> None:
    """`link -> target`, or a skip where this runner cannot make one."""
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(target, link)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"this platform cannot create a symlink here: {exc}")


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_root_symlinks", ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Sources and plans
# ---------------------------------------------------------------------------


def commit_index(repo: Path, message: str) -> None:
    git("-c", "user.name=Source Human", "-c",
        "user.email=source@invalid.example", "commit", "-qm", message,
        cwd=repo)


def commit_tree_entries(repo: Path, links: dict, gitlinks: tuple = ()) -> None:
    """Each `links` path as a symlink (its target the blob) and each
    `gitlinks` path as a submodule, in the source's TREE only."""
    for link, target in links.items():
        blob = subprocess.run(
            ["git", "hash-object", "-w", "--stdin"], cwd=str(repo),
            input=target, capture_output=True, text=True, check=True)
        git("update-index", "--add", "--cacheinfo",
            f"{SYMLINK},{blob.stdout.strip()},{link}", cwd=repo)
    head = git("rev-parse", "HEAD", cwd=repo).stdout.strip()
    for path in gitlinks:
        git("update-index", "--add", "--cacheinfo", f"{GITLINK},{head},{path}",
            cwd=repo)
    commit_index(repo, "Link")


def set_leg(plan: Path, path: str, leg: str) -> None:
    """Answer the entry for `path` with `leg`, whatever `plan` said."""
    text = plan.read_text(encoding=UTF8)
    entry = re.compile(rf"(?m)^  - path: {re.escape(path)}\n    leg: .*$")
    assert entry.search(text), f"no plan entry for {path}"
    plan.write_text(entry.sub(
        lambda _: f"  - path: {path}\n    leg: {leg}\n"
                  "    resolution: \"answered by the test\"", text, count=1),
        encoding=UTF8)


def answer(plan: Path, legs: dict) -> None:
    """Each of `legs` answered, and every other question answered `root`."""
    for path, leg in legs.items():
        set_leg(plan, path, leg)
    plan.write_text(plan.read_text(encoding=UTF8).replace(
        "    leg: null\n", "    leg: root\n    resolution: \"kept\"\n"),
        encoding=UTF8)


def planned(base: Path, files: dict, links: dict, legs: dict,
            gitlinks: tuple = ()) -> tuple[Path, Path]:
    """`(source, plan)`: a source with `files` and, in its tree, `links`;
    each of `legs` answered, and every other question answered `root`."""
    source = make_source_repo(base / THING, tree={**BASIC, **files})
    if links or gitlinks:
        commit_tree_entries(source, links, gitlinks)
    plan = base / PLAN_FILE
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    answer(plan, legs)
    return source, plan


def check(plan: Path):
    return run_script(ADOPT, "check", PLAN_FLAG, str(plan))


def symlink_findings(result) -> list[str]:
    return [line for line in result.stderr.splitlines()
            if line.startswith(FINDING)]


def execute_args(base: Path, plan: Path) -> Namespace:
    """What `main` hands `cmd_execute`, with `--yes`."""
    return Namespace(plan=str(plan), source=None,
                     local_remote_dir=base / REMOTES, allow_empty_leg=[],
                     yes=True, work_dir=base / WORK)


def refused_by(adopter, args):
    """The `Refusal` `cmd_execute` raises. Failing to raise one means it went
    on to make the legs."""
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(args)
    return caught.value


def no_leg_was_created(base: Path) -> None:
    assert not (base / REMOTES).exists()
    for role in (SPEC, CODE):
        assert not (base / WORK / f"{PROJECT}-{role}").exists()


def finding(link: str, target: str, shape_path: str, why: str) -> str:
    """The line `check` prints, and `execute`'s refusal carries."""
    return (f"{FINDING}the plan keeps {link} in the root, a symlink to "
            f"{target}, and the shape writes {shape_path} through it, but "
            f"{why}. Send {link} to a leg or `drop` it, or change where it "
            "points in the source and re-run `plan`.")


@pytest.fixture
def no_filter_repo_probe(adopter, monkeypatch):
    """Every refusal under test comes before `git filter-repo` is used."""
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)


# ---------------------------------------------------------------------------
# Refused by `check`, and by `execute` before any leg exists
# ---------------------------------------------------------------------------

NOT_IN_THE_TREE = "which is not in the source tree"
CLIMBS = "it climbs above the assembly root"
SPEC_MOUNT = "it enters spec, where the plan mounts the spec leg"
#: Why the shape's scripts cannot run from where a link puts them; `{}` is
#: the directory they land in.
SCRIPTS_MISPLACED = (
    "and the shape's scripts look for the assembly root, and for "
    "contracts/repository-naming.yaml, from the directory above their own, "
    "so they run only from a directory directly under the root, which {} is "
    "not")
LINK_TO_GH = {"tooling/gh/workflows/build.yml": "on: push\n"}

#: `(*PLANNED, (link, target, shape path, why))`. The first ten are
#: lane 2's table for #178 (D3-D12) and #183's loop; the rest are the other
#: ways a link the shape writes through cannot be written through.
REFUSED = [
    pytest.param({}, {ATTRIBUTES: NOWHERE_ATTRS}, {ATTRIBUTES: ROOT},
                 (ATTRIBUTES, NOWHERE_ATTRS, ATTRIBUTES,
                  f"the symlink {ATTRIBUTES} leads to nowhere/attrs, "
                  f"{NOT_IN_THE_TREE}"), id="D4-a-dangling-file-link"),
    pytest.param({"config/readme.md": "c\n"}, {ATTRIBUTES: CONFIG_ATTRS},
                 {CONFIG_DIR: ROOT, ATTRIBUTES: ROOT},
                 (ATTRIBUTES, CONFIG_ATTRS, ATTRIBUTES,
                  f"the symlink {ATTRIBUTES} leads to config/attrs, "
                  f"{NOT_IN_THE_TREE}"),
                 id="D3-a-dangling-file-link-in-a-kept-directory"),
    pytest.param(LINK_TO_GH, {GITHUB: TOOLING_GH},
                 {"tooling/": CODE, GITHUB: ROOT},
                 (GITHUB, TOOLING_GH, WORKFLOW,
                  "the symlink .github leads to tooling/gh, which the plan "
                  "sends to the code leg"), id="D5-into-a-path-sent-to-a-leg"),
    pytest.param(LINK_TO_GH, {GITHUB: TOOLING_GH},
                 {"tooling/": "drop", GITHUB: ROOT},
                 (GITHUB, TOOLING_GH, WORKFLOW,
                  "the symlink .github leads to tooling/gh, which the plan "
                  "sends to `drop`"), id="into-a-dropped-path"),
    pytest.param({}, {GITHUB: OUTSIDE_CI}, {GITHUB: ROOT},
                 (GITHUB, OUTSIDE_CI, WORKFLOW,
                  f"at the symlink .github {CLIMBS}"),
                 id="D6-a-relative-link-out"),
    pytest.param({}, {GITHUB: "/srv/ci"}, {GITHUB: ROOT},
                 (GITHUB, "/srv/ci", WORKFLOW,
                  "the symlink .github leads to /srv/ci, an absolute path: a "
                  "place on this machine, not in the assembly"),
                 id="D6b-an-absolute-link"),
    pytest.param({}, {GITHUB: "spec/ci"}, {GITHUB: ROOT},
                 (GITHUB, "spec/ci", WORKFLOW, SPEC_MOUNT),
                 id="D7-into-a-mount"),
    pytest.param({}, {GITHUB: SPEC}, {GITHUB: ROOT},
                 (GITHUB, SPEC, WORKFLOW, SPEC_MOUNT),
                 id="D7b-at-a-mount"),
    pytest.param({}, {GITHUB: "code/ci"}, {GITHUB: ROOT},
                 (GITHUB, "code/ci", WORKFLOW,
                  "it enters code, where the plan mounts the code leg"),
                 id="into-the-other-mount"),
    pytest.param({}, {GITHUB: ".git/info"}, {GITHUB: ROOT},
                 (GITHUB, ".git/info", WORKFLOW,
                  f"the symlink .github leads to .git/info, {NOT_IN_THE_TREE}"),
                 id="D9-into-dot-git"),
    pytest.param({}, {GITHUB: "../Northwind/ci"}, {GITHUB: ROOT},
                 (GITHUB, "../Northwind/ci", WORKFLOW,
                  f"at the symlink .github {CLIMBS}"),
                 id="D12-out-and-back-by-name"),
    pytest.param({}, {GITHUB: GITHUB}, {GITHUB: ROOT},
                 (GITHUB, GITHUB, WORKFLOW,
                  "it runs round a symlink loop at .github"),
                 id="a-link-to-itself"),
    pytest.param({}, {GITHUB: LOOP, LOOP: GITHUB},
                 {GITHUB: ROOT, LOOP: ROOT},
                 (GITHUB, LOOP, WORKFLOW,
                  "it runs round a symlink loop at .github"),
                 id="a-loop-of-two"),
    pytest.param({}, {GITHUB: README}, {GITHUB: ROOT},
                 (GITHUB, README, WORKFLOW,
                  f"it passes through {README}, which is a file"),
                 id="to-a-file-the-shape-writes-beneath"),
    pytest.param({CI_FILE: ON_PUSH}, {GITHUB: "nowhere/../ci"},
                 {CI_DIR: ROOT, GITHUB: ROOT},
                 (GITHUB, "nowhere/../ci", WORKFLOW,
                  "it passes through nowhere, which is not a directory in "
                  "the assembly root"), id="dot-dot-from-nowhere"),
    pytest.param({RUN_SH: ECHO}, {GITHUB: TOOLS_UP,
                                  TOOLS_UP: "../../x"},
                 {TOOLS_DIR: ROOT, GITHUB: ROOT},
                 (GITHUB, TOOLS_UP, WORKFLOW,
                  f"at the symlink tools/up {CLIMBS}"),
                 id="a-chain-whose-second-link-leaves"),
    pytest.param({}, {SHAPE_DIR: "../elsewhere"}, {SHAPE_DIR: ROOT},
                 (SHAPE_DIR, "../elsewhere", f"shape/{README}",
                  f"at the symlink shape {CLIMBS}"),
                 id="the-collision-directory-leaves"),
    pytest.param({"tools/sub/run.sh": ECHO}, {SCRIPTS: TOOLS_SUB},
                 {TOOLS_DIR: ROOT, SCRIPTS: ROOT},
                 (SCRIPTS, TOOLS_SUB, VALIDATE_PINS,
                  "it lands at tools/sub/validate-pins.py, "
                  + SCRIPTS_MISPLACED.format(TOOLS_SUB)),
                 id="R2-scripts-two-directories-down"),
    pytest.param({}, {SCRIPTS: "."}, {SCRIPTS: ROOT},
                 (SCRIPTS, ".", VALIDATE_PINS,
                  "it lands at validate-pins.py, "
                  + SCRIPTS_MISPLACED.format("the root itself")),
                 id="R6-scripts-in-the-root-itself"),
    pytest.param({RUN_SH: ECHO}, {SCRIPTS: "tools/.."},
                 {TOOLS_DIR: ROOT, SCRIPTS: ROOT},
                 (SCRIPTS, "tools/..", VALIDATE_PINS,
                  "it lands at validate-pins.py, "
                  + SCRIPTS_MISPLACED.format("the root itself")),
                 id="R9-scripts-in-the-root-by-dot-dot"),
    pytest.param({"scripts/own.sh": ECHO, RUN_SH: ECHO},
                 {BOOTSTRAP_PY: "../tools/bootstrap.py"},
                 {TOOLS_DIR: ROOT, "scripts/": ROOT},
                 (BOOTSTRAP_PY, "../tools/bootstrap.py",
                  BOOTSTRAP_PY,
                  "the symlink scripts/bootstrap.py leads to "
                  f"tools/bootstrap.py, {NOT_IN_THE_TREE}"),
                 id="R10-one-script-apart-from-the-rest"),
]


@pytest.mark.parametrize((*PLANNED, "expected"), REFUSED)
def test_check_reports_the_link_and_execute_refuses_it_before_any_leg(
        adopter, no_filter_repo_probe, tmp_path, files, links, legs,
        expected):
    """One finding naming the link, its target and the shape path that runs
    through it; `execute` refuses with the same line, word for word, and
    makes no leg, so the corrected plan does not meet `leg-remote-exists`."""
    _, plan = planned(tmp_path, files, links, legs)
    line = finding(*expected)

    checked = check(plan)
    assert checked.returncode == 1, checked.stderr + checked.stdout
    assert symlink_findings(checked) == [line], checked.stderr

    refusal = refused_by(adopter, execute_args(tmp_path, plan))
    assert refusal.code == ROOT_SYMLINK
    assert f"  {line}" in refusal.detail.splitlines()
    assert "no leg repository was created" in refusal.remediation
    no_leg_was_created(tmp_path)


def test_a_link_into_a_submodule_kept_in_the_root_is_reported(tmp_path):
    """A gitlink is a directory in a checkout, holding another repository:
    a link into it is not a link into `a file`."""
    _, plan = planned(tmp_path, {}, {GITHUB: "vendor/lib/ci"},
                      {GITHUB: ROOT, "vendor/": ROOT},
                      gitlinks=("vendor/lib",))
    checked = check(plan)
    assert finding(GITHUB, "vendor/lib/ci", WORKFLOW,
                   "it enters vendor/lib, a submodule the plan keeps in the "
                   "root") in symlink_findings(checked), checked.stderr


def test_one_finding_per_link_however_many_shape_paths_run_through_it(
        tmp_path):
    """`contracts -> /srv` carries four shape paths; the finding names the
    first one the materializer writes."""
    _, plan = planned(tmp_path, {}, {CONTRACTS: "/srv"},
                      {CONTRACTS: ROOT})
    findings = symlink_findings(check(plan))
    assert findings == [finding(
        CONTRACTS, "/srv", "contracts/spec-pin.yaml",
        "the symlink contracts leads to /srv, an absolute path: a place on "
        "this machine, not in the assembly")]


# ---------------------------------------------------------------------------
# Not refused
# ---------------------------------------------------------------------------

#: `PLANNED` cases: plans whose links the shape writes through, or
#: past, safely: each target is something the root keeps, and the shape's
#: scripts still land directly under the root. Main adopts and bootstraps
#: every one of them (lane 2's 4c; the R rows of this branch's report).
ACCEPTED = [
    pytest.param({RUN_SH: ECHO}, {SCRIPTS: TOOLS},
                 {TOOLS_DIR: ROOT, SCRIPTS: ROOT},
                 id="R1-scripts-directly-under-the-root"),
    pytest.param({"governance/policy.md": "p\n"}, {CONTRACTS: "governance"},
                 {"governance/": ROOT, CONTRACTS: ROOT},
                 id="R3-contracts-elsewhere"),
    pytest.param({}, {GITHUB: "."}, {GITHUB: ROOT},
                 id="R4-github-to-the-root"),
    pytest.param({}, {CONTRACTS: "."}, {CONTRACTS: ROOT},
                 id="R5-contracts-to-the-root"),
    pytest.param({"vendor/keep.txt": "k\n"}, {SHAPE_DIR: "vendor"},
                 {"vendor/": ROOT, SHAPE_DIR: ROOT},
                 id="R7-the-collision-directory-elsewhere"),
    pytest.param({"ci/workflows/validate.yml": ON_PUSH}, {GITHUB: "ci"},
                 {CI_DIR: ROOT, GITHUB: ROOT},
                 id="R8-a-link-to-the-projects-own-workflow"),
    pytest.param({CI_FILE: ON_PUSH}, {GITHUB: "ci"},
                 {CI_DIR: ROOT, GITHUB: ROOT}, id="C14c-github-to-ci"),
    pytest.param({CONFIG_ATTRS: "* text=auto\n"},
                 {ATTRIBUTES: CONFIG_ATTRS},
                 {CONFIG_DIR: ROOT, ATTRIBUTES: ROOT},
                 id="D2-a-live-file-link-the-shape-writes-beside"),
    pytest.param({CI_FILE: ON_PUSH, RUN_SH: ECHO},
                 {GITHUB: TOOLS_UP, TOOLS_UP: "../ci/"},
                 {CI_DIR: ROOT, TOOLS_DIR: ROOT, GITHUB: ROOT},
                 id="D10-a-chain-through-dot-dot"),
]

#: Links no path the shape writes runs through: main keeps each exactly as
#: the source had it, and so must this. The last is D6's link out, sent to a
#: leg instead of kept: the mount's `git rm` takes it out of the root before
#: the shape is written, so where it leads is the leg's business, and a
#: `check` that followed it would refuse a plan main adopts.
UNRELATED = [
    pytest.param({NOTES_README: "n\n"}, {NOTES_UPSTREAM: ETC},
                 NOTES_KEPT, id="an-absolute-link"),
    pytest.param({NOTES_README: "n\n"}, {"notes/old": "../gone"},
                 NOTES_KEPT, id="a-dangling-link-out"),
    pytest.param({}, {LATEST: LATEST}, {LATEST: ROOT},
                 id="a-link-to-itself-no-shape-path-meets"),
    pytest.param({}, {GITHUB: OUTSIDE_CI}, {GITHUB: CODE},
                 id="the-link-itself-sent-to-a-leg"),
]


@pytest.mark.parametrize(PLANNED, ACCEPTED + UNRELATED)
def test_a_link_the_shape_can_write_through_or_never_meets_is_not_refused(
        adopter, tmp_path, files, links, legs):
    _, plan = planned(tmp_path, files, links, legs)
    checked = check(plan)
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert "plan ok" in checked.stdout
    loaded = adopter.Plan.load(plan)
    source = loaded.open_source(None, tmp_path / READ)
    assert adopter._refuse_what_check_finds(loaded, source) is None


# ---------------------------------------------------------------------------
# core.symlinks=false (#183)
# ---------------------------------------------------------------------------


def github_to_ci(base: Path) -> tuple[Path, Path]:
    return planned(base, {CI_FILE: ON_PUSH}, {GITHUB: "ci"},
                   {CI_DIR: ROOT, GITHUB: ROOT})


def test_execute_refuses_a_link_it_would_check_out_as_a_file(
        adopter, no_filter_repo_probe, tmp_path, monkeypatch):
    """The assembly's clone would hold `.github` as a plain file, and the
    materializer died there with NotADirectoryError after both legs were
    pushed. It is refused before them, and the probe leaves nothing."""
    _, plan = github_to_ci(tmp_path)
    for key, value in SYMLINKS_OFF.items():
        monkeypatch.setenv(key, value)
    refusal = refused_by(adopter, execute_args(tmp_path, plan))
    assert refusal.code == "adopt-symlinks-off"
    work = (tmp_path / WORK).resolve()
    assert refusal.detail == (
        f"the plan keeps .github in the root, a symlink to ci, and the shape "
        f"writes {WORKFLOW} through it, but `git` here checks a symlink out "
        "as a plain file: `core.symlinks` is false for a repository made in "
        f"{work}. The assembly's clone would hold .github as a file, and "
        "nothing can be written beneath a file.")
    assert "no leg repository was created" in refusal.remediation
    assert "send .github to a leg or `drop` it" in refusal.remediation
    no_leg_was_created(tmp_path)
    assert list(work.iterdir()) == []


def test_the_probe_answers_what_git_would_do(adopter, tmp_path, monkeypatch):
    for key, value in SYMLINKS_ON.items():
        monkeypatch.setenv(key, value)
    assert adopter._checks_out_symlinks(tmp_path) is True
    monkeypatch.setenv(CONFIG_VALUE, "false")
    assert adopter._checks_out_symlinks(tmp_path) is False
    assert list(tmp_path.iterdir()) == []


def test_with_symlinks_on_the_same_plan_passes_the_probe(adopter, tmp_path,
                                                         monkeypatch):
    source, plan = github_to_ci(tmp_path)
    for key, value in SYMLINKS_ON.items():
        monkeypatch.setenv(key, value)
    loaded = adopter.Plan.load(plan)
    opened = loaded.open_source(None, tmp_path / READ)
    assert adopter._refuse_symlinks_checked_out_as_files(
        loaded, opened, tmp_path) is None


#: Plans for which the probe is never made: no link; a link no shape path
#: meets; a live link AT a shape path, which a checkout without symlinks
#: still takes as a file the shape's copy goes beside.
NO_PROBE = [
    pytest.param({}, {}, {}, id="no-link"),
    pytest.param({NOTES_README: "n\n"}, {NOTES_UPSTREAM: ETC},
                 NOTES_KEPT, id="an-unrelated-link"),
    pytest.param({CONFIG_ATTRS: "* text=auto\n"},
                 {ATTRIBUTES: CONFIG_ATTRS},
                 {CONFIG_DIR: ROOT, ATTRIBUTES: ROOT}, id="a-link-at-a-path"),
]


@pytest.mark.parametrize(PLANNED, NO_PROBE)
def test_an_adoption_with_no_link_beneath_a_shape_path_makes_no_probe(
        adopter, tmp_path, monkeypatch, files, links, legs):
    """An ordinary adoption runs exactly as before: nothing is made in the
    work directory to ask `git` a question this plan does not raise."""
    def no_probe(_work_root):
        raise AssertionError("the probe was made")

    monkeypatch.setattr(adopter, "_checks_out_symlinks", no_probe)
    for key, value in SYMLINKS_OFF.items():
        monkeypatch.setenv(key, value)
    _, plan = planned(tmp_path, files, links, legs)
    loaded = adopter.Plan.load(plan)
    opened = loaded.open_source(None, tmp_path / READ)
    assert adopter._refuse_symlinks_checked_out_as_files(
        loaded, opened, tmp_path) is None


# ---------------------------------------------------------------------------
# The materializer's own refusals, for a caller that skipped `check`
# ---------------------------------------------------------------------------


def template_values() -> dict:
    """A value for every placeholder the assembly-root templates hold."""
    names = set()
    for path in (REPO / "templates" / "assembly-root").rglob("*"):
        if path.is_file():
            names.update(PLACEHOLDER_RE.findall(path.read_text(encoding=UTF8)))
    return {name[2:-2]: "x" for name in names}


def materialize(target: Path):
    return materialize_assembly_root(REPO, target, template_values(),
                                     collision_dir=SHAPE_DIR)


def test_the_materializer_writes_the_paths_check_follows_in_order(tmp_path):
    """`check` follows `assembly_root_paths()`; this is the list the
    materializer writes, in its order."""
    target = tmp_path / ASSEMBLY
    target.mkdir()
    assert materialize(target).written == list(assembly_root_paths())


def refused_materializing(target: Path) -> Refusal:
    with pytest.raises(Refusal) as caught:
        materialize(target)
    return caught.value


def test_a_file_where_the_shape_needs_a_directory_is_a_refusal(tmp_path):
    """What a `core.symlinks=false` checkout makes of `.github -> ci`: a
    plain FILE holding `ci`. It used to be a NotADirectoryError traceback."""
    target = tmp_path / ASSEMBLY
    target.mkdir()
    (target / GITHUB).write_text("ci", encoding=UTF8)
    refusal = refused_materializing(target)
    assert refusal.code == BLOCKED
    assert refusal.detail == (f"{WORKFLOW} cannot be written: .github is a "
                              "file, not a directory")
    assert "nothing was written at that path" in refusal.remediation


#: `(links, files, code, detail)` of a target holding `links` and `files`. `{t}` is the target directory and `{o}`
#: the directory beside it that a link out of it reaches.
UNWRITABLE = [
    pytest.param({GITHUB: "../outside"}, (), OUTSIDE,
                 f"{WORKFLOW} would be written outside {{t}}: at the symlink "
                 ".github it climbs above it", id="a-relative-link-out"),
    pytest.param({GITHUB: "{o}"}, (), OUTSIDE,
                 f"{WORKFLOW} would be written through the symlink .github, "
                 "which leads to the absolute path {o}; the shape follows "
                 "only a symlink whose relative target stays inside {t}",
                 id="an-absolute-link"),
    pytest.param({SHAPE_DIR: "../outside"}, (README,), OUTSIDE,
                 f"shape/{README} would be written outside {{t}}: at the "
                 "symlink shape it climbs above it",
                 id="the-collision-directory-out"),
    pytest.param({GITHUB: GITHUB}, (), "materialize-symlink-loop",
                 f"{WORKFLOW} runs round a symlink loop at .github in {{t}}",
                 id="a-link-to-itself"),
    pytest.param({GITHUB: LOOP, LOOP: GITHUB}, (),
                 "materialize-symlink-loop",
                 f"{WORKFLOW} runs round a symlink loop at .github in {{t}}",
                 id="a-loop-of-two"),
    pytest.param({GITHUB: "nowhere"}, (), BLOCKED,
                 f"{WORKFLOW} cannot be written: .github is a symlink to "
                 "nowhere, which is not a directory here",
                 id="a-dangling-directory-link"),
    pytest.param({GITHUB: README}, (README,), BLOCKED,
                 f"{WORKFLOW} cannot be written: .github is a symlink to "
                 f"{README}, which is not a directory here",
                 id="a-link-to-a-file"),
    pytest.param({ATTRIBUTES: NOWHERE_ATTRS}, (), BLOCKED,
                 f"{ATTRIBUTES} cannot be written: the symlink {ATTRIBUTES} "
                 "leads to nowhere/attrs, and there is no directory there to "
                 "write it in", id="a-dangling-file-link"),
]


@needs_disk_symlinks
@pytest.mark.parametrize(("links", "files", CODE, "detail"), UNWRITABLE)
def test_the_materializer_refuses_before_it_writes(tmp_path, links, files,
                                                   code, detail):
    """Never a write outside the target and never a traceback. On main the
    two links out wrote `validate.yml` into `outside/`, and the rest raised
    OSError, FileExistsError or FileNotFoundError."""
    target, outside = tmp_path / ASSEMBLY, tmp_path / "outside"
    target.mkdir()
    outside.mkdir()
    for name in files:
        (target / name).write_text("the source's own\n", encoding=UTF8)
    for link, to in links.items():
        symlink(target / link, to.format(o=outside))
    refusal = refused_materializing(target)
    assert (refusal.code, refusal.detail) == (
        code, detail.format(t=target, o=outside))
    assert list(outside.iterdir()) == [], "written outside the target"


@needs_disk_symlinks
@pytest.mark.parametrize("inside", [
    {GITHUB: "ci"},
    {GITHUB: TOOLS_UP, TOOLS_UP: "../ci/"},
], ids=["a-link-to-a-directory", "a-chain-through-dot-dot"])
def test_the_materializer_still_writes_through_a_link_that_stays_inside(
        tmp_path, inside):
    target = tmp_path / ASSEMBLY
    (target / "ci").mkdir(parents=True)
    (target / TOOLS).mkdir()
    for link, to in inside.items():
        symlink(target / link, to)
    written = materialize(target).written
    assert WORKFLOW in written
    assert (target / "ci" / "workflows" / "validate.yml").is_file()


# ---------------------------------------------------------------------------
# End to end, through `execute`
# ---------------------------------------------------------------------------


def disk_source(base: Path, files: dict, links: dict, legs: dict) -> tuple:
    """`(source, plan)` with each link a real symlink in the source, and a
    plan `check` passes."""
    source = make_source_repo(base / THING, tree={**BASIC, **files})
    for link, target in links.items():
        symlink(source / link, target)
    git("add", "-A", "--", ".", cwd=source)
    commit_index(source, "Link")
    plan = base / PLAN_FILE
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    answer(plan, legs)
    checked = check(plan)
    assert checked.returncode == 0, checked.stderr + checked.stdout
    return source, plan


def execute(base: Path, plan: Path):
    return run_script(ADOPT, "execute", PLAN_FLAG, str(plan), "--yes",
                      "--local-remote-dir", str(base / REMOTES),
                      "--work-dir", str(base / WORK))


def split_modes(source: Path) -> dict:
    listing = git("ls-tree", "-r", BRANCH, cwd=source).stdout
    return {line.split("\t", 1)[1]: line.split(" ", 1)[0]
            for line in listing.splitlines()}


@pytest.fixture(scope="module")
def scripts_through_a_link(tmp_path_factory) -> SimpleNamespace:
    """One real adoption of a source that keeps `scripts -> tools`."""
    if sys.platform == "win32" or shutil.which("git-filter-repo") is None:
        pytest.skip("needs git filter-repo and a disk that holds symlinks")
    base = tmp_path_factory.mktemp("scripts-link")
    source, plan = disk_source(base, {RUN_SH: ECHO}, {SCRIPTS: TOOLS},
                               {TOOLS_DIR: ROOT, SCRIPTS: ROOT})
    return SimpleNamespace(base=base, source=source,
                           result=execute(base, plan))


@needs_filter_repo
@needs_disk_symlinks
def test_a_link_the_root_keeps_and_the_shape_writes_through_adopts(
        scripts_through_a_link):
    """Rule 3 of the brief: a link whose target the root keeps is followed,
    end to end. The split holds the link, and the shape's scripts where it
    leads; `_verify` finds each pinned script through it."""
    result = scripts_through_a_link.result
    assert result.returncode == 0, result.stderr + result.stdout
    assert "adoption verified" in result.stdout
    modes = split_modes(scripts_through_a_link.source)
    assert modes[SCRIPTS] == SYMLINK
    assert {"tools/bootstrap.py", "tools/repo_shape.py", RUN_SH} <= set(modes)
    assert VALIDATE_PINS not in modes


@needs_filter_repo
@needs_disk_symlinks
def test_that_assembly_bootstraps(scripts_through_a_link, tmp_path):
    assert scripts_through_a_link.result.returncode == 0
    clone = tmp_path / PROJECT
    git(*FILE_PROTOCOL, "clone", "-q", "--recurse-submodules", "-b", BRANCH,
        str(scripts_through_a_link.source), str(clone), cwd=tmp_path)
    booted = run_script(clone / SCRIPTS / "bootstrap.py", cwd=clone)
    assert booted.returncode == 0, booted.stderr + booted.stdout


@needs_filter_repo
@needs_disk_symlinks
def test_an_unrelated_absolute_link_in_the_root_still_adopts(tmp_path):
    """Rule 2 of the brief: no shape path runs through it, so main's
    behaviour is kept: the split carries the link exactly as it was."""
    source, plan = disk_source(tmp_path, {NOTES_README: "n\n"},
                               {NOTES_UPSTREAM: ETC}, NOTES_KEPT)
    result = execute(tmp_path, plan)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "adoption verified" in result.stdout
    assert split_modes(source)[NOTES_UPSTREAM] == SYMLINK
    assert git("show", f"{BRANCH}:notes/upstream",
               cwd=source).stdout == ETC


@needs_filter_repo
@needs_disk_symlinks
def test_a_caller_that_skips_check_meets_the_materializer_refusal(
        adopter, tmp_path, monkeypatch, capsys):
    """Defence in depth: with #168's refusal taken away, the link out (D6)
    reaches the materializer, which refuses it by name -- no traceback, and
    nothing written into the directory beside the work directory."""
    outside = tmp_path / WORK / "outside-ci"
    source = make_source_repo(tmp_path / THING, tree=BASIC)
    symlink(source / GITHUB, OUTSIDE_CI)
    git("add", "-A", "--", ".", cwd=source)
    commit_index(source, "Link out")
    plan = tmp_path / PLAN_FILE
    assert write_plan(source, plan, project=PROJECT).returncode == 0
    set_leg(plan, GITHUB, ROOT)
    outside.mkdir(parents=True)
    monkeypatch.setenv("LANES_LANE", "")
    clear_ambient_pin_sources(monkeypatch)
    monkeypatch.setattr(adopter, "_refuse_what_check_finds",
                        lambda plan, source: None)
    code = adopter.main(["execute", PLAN_FLAG, str(plan), "--yes",
                         "--local-remote-dir", str(tmp_path / REMOTES),
                         "--work-dir", str(tmp_path / WORK)])
    seen = capsys.readouterr()
    assert code == 2, seen.err + seen.out
    assert "REFUSED materialize-outside: " in seen.err
    assert "Traceback" not in seen.err
    assert list(outside.iterdir()) == []
