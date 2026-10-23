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

The groups of tests:

- `check` reports each such link, and `execute` refuses it under #168's one
  list of `check`'s findings, before any leg exists. The links are put in
  the source's TREE (`update-index --cacheinfo`), which is all either command
  reads, so these need no symlink privilege and run on Windows too.
- What must NOT be refused: a link whose target the root keeps (followed end
  to end since #167), one whose destination is there by the time the shape
  writes through it, and one no shape path runs through.
- A link AT a path the shape writes is decided by what `place` will find
  (#183's review, B1): where something is already there, the shape's copy
  goes beside it under `shape/` and the link is kept, as on main; where
  nothing is, the shape would write through it, and it is refused. Outside
  the assembly that is a question for this machine's disk, which `check` and
  `execute` each ask.
- `place` asks where the shape's copy under `shape/` lands only of the disk,
  after both legs exist (#262's `copy_in_the_way`), so `check` refuses a
  link that leads the copy onto something already there (B2). A link AT the
  copy is #262's own finding, `plan-root-blocks-shape-copy`.
- A case twin, `.GitHub` for `.github`, is followed as a macOS or Windows
  disk follows it, and refused on every disk (S1).
- The file of each pin the plan declares, `contracts/<product>-pin.yaml`, is
  a path the shape writes, before its own pin (#273), and is followed too;
  a link AT one is #273's own finding, `plan-root-holds-pin`.
- `core.symlinks=false` (#183): `execute` refuses, before any leg, a link the
  shape would write beneath, because the assembly's clone holds it as a file.
  A link AT a path the shape writes is then that file, which `place` writes
  the copy beside, so neither `check` nor `execute` refuses it, wherever it
  leads (B-OFF). A link ABOVE one that `check` reports says it is that file
  there, not where it leads (#531). The tests of a link `check` follows tell
  `git` to check a symlink out as one, since Git for Windows' own default is
  a file.
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

from conftest import (ADOPT, REPO, WINDOWS_SKIP, appended_to_command_scope,
                      clear_ambient_pin_sources, cloned_just_pushed, git,
                      make_source_repo, run_script, write_plan)

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
SHAPE_README = f"{SHAPE_DIR}/{README}"
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
AGENTS = "AGENTS.md"
CLAUDE = "CLAUDE.md"
MAKEFILE = "Makefile"
DOCS_DIR = "docs/"
DOCS_AGENTS = "docs/agents.md"
VENDOR_DIR = "vendor/"
SPEC = "spec"
CODE = "code"
THING = "Thing"
PLAN_FILE = "adoption-plan.yaml"
PLAN_FLAG = "--plan"
WORK_FLAG = "--work-dir"
READ = "read"
ASSEMBLY = "assembly"
OUTSIDE_DIR = "outside"
BLOCKED = "materialize-blocked"
#: #262's refusal, in `place`, of a copy whose place is taken.
COPY_BLOCKED = "materialize-copy-blocked"
#: #262's finding for a path the plan keeps where the shape writes its copy.
COPY_IN_THE_WAY = "plan-root-blocks-shape-copy"
COPY_FINDING = f"FINDING {COPY_IN_THE_WAY}: "
#: A file of the source's own that a link at the copy leads onto.
NOTES_MD = "notes.md"
OUTSIDE = "materialize-outside"
#: How `execute` reports a refusal met once both legs exist, the
#: materializer's among them (#188): the step it stopped at, with the refusal
#: on the same line, then the notice of what the run left.
SPLIT_STEP = "REFUSED committing the split."
LEFT_BEHIND = "NOTHING has been rolled back: "
BOTH_PUSHED = "and both legs are pushed."
#: The materializer's refusal of a path that follows too many symlinks.
SYMLINK_LOOP = "materialize-symlink-loop"
#: Case twins of paths the shape writes, as a macOS or Windows disk reads
#: them (S1), and the rest of what several cases name.
GITHUB_TWIN = ".GitHub"
GITIGNORE_TWIN = ".GITIGNORE"
NOWHERE_GITIGNORE = "nowhere/gitignore"
BUILD_MAKEFILE = "build/Makefile"
GIT_INFO = ".git/info"
GIT_HEAD = ".git/HEAD"
GIT_DESCRIPTION = ".git/description"
GIT_HOOKS = ".git/hooks"
NOWHERE_MD = "nowhere.md"
#: The probe B-OFF makes, as tests put a stand-in in its place.
PROBE = "_checks_out_symlinks"
#: And the probe of how git keeps the clone's refs (#904).
REF_PROBE = "_clone_ref_store"
SYMLINKS_OFF_CODE = "adopt-symlinks-off"
#: What the assembly's clone holds in its own `.git` when the shape is
#: written, besides `HEAD`: the files git makes in every clone it checks
#: out, and places in the directories of its objects, its refs, their logs,
#: and the stores of the legs `execute` has mounted (2b of #183's re-verify).
GIT_KEPT = (".git/index", ".git/packed-refs", ".git/logs/HEAD",
            ".git/refs/heads", ".git/objects/pack", ".git/modules/spec")
#: And the names in those directories that #904 names, where it counted
#: each directory with whatever might be under it (L1-J1 of #457): what git
#: makes in every such clone on its files backend, the branch the clone
#: checks out (the source's HEAD branch, `main` here), `origin/HEAD`, the
#: split branch and a log of each among them.
GIT_NAMED = (".git/config", ".git/refs/tags", ".git/objects/info",
             ".git/modules/code", ".git/refs/heads/main",
             ".git/refs/remotes/origin/HEAD", f".git/refs/heads/{BRANCH}",
             ".git/logs/refs/heads/main",
             ".git/logs/refs/remotes/origin/HEAD",
             f".git/logs/refs/heads/{BRANCH}")
#: Names in those directories that the clone does NOT hold, which checked
#: ok while they were counted whole: `execute` wrote the shape's file into
#: each, in the clone's `.git` (L1-J1 of #457).
GIT_MISSING = (".git/refs/remotes/origin/main", ".git/logs/refs/heads/nope",
               ".git/modules/nope", ".git/refs/heads/nope")
#: A name under no directory the clone's `.git` holds; one in its object
#: store, which `check` does not read; and one in a leg's store, which is
#: made after `check`.
GIT_NO_DIRECTORY = ".git/nowhere/x"
GIT_OBJECT = ".git/objects/zz/nothing"
GIT_IN_A_STORE = ".git/modules/spec/nope"
SPEC_OTHER = "spec/docs/other.md"
VENDOR = "vendor"
PERSONAL = "a personal file\n"
VERIFIED = "adoption verified"
MODULE = "module"
#: `plan` cannot classify a `notes/` holding a link and a readme as one, and
#: lists the two; the readme is answered here and the link with the rest.
NOTES_KEPT = {NOTES_README: ROOT}
#: The arguments every case of a planned source takes.
FILES, LINKS = "files", "links"
PLANNED = (FILES, LINKS, "legs")
#: What `check` adds to a finding that holds only on a disk that ignores
#: case: #198's `CASE_ASIDE`, word for word.
CASE_ASIDE = " once case is ignored, as a macOS or Windows disk does"

#: The source every case starts from. `make_source_repo`'s later commits edit
#: the specification and `src/app/main.py`, so both are here.
BASIC = {README: "# Thing\n",
         "specs/001-feature/spec.md": "# The feature\n",
         "src/app/main.py": "import contracts_reader\n"}

#: `git` told to check a symlink out as a plain file, the way Git for
#: Windows' default does, or `git init` on a filesystem without symlinks.
#: `GIT_CONFIG_*` outranks every configuration file. Set by `told_git`, after
#: the entries the environment holds.
CORE_SYMLINKS = "core.symlinks"

#: What this runner lacks, if anything, for the end-to-end tests.
NO_FILTER_REPO = shutil.which("git-filter-repo") is None
ON_WINDOWS = sys.platform == "win32"

needs_filter_repo = pytest.mark.skipif(
    NO_FILTER_REPO,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

#: What the tests with a symlink ON THE DISK need, as in
#: `test_adopt_ignored_shape_files.py`: Git for Windows checks a tracked
#: symlink out as a plain file unless `core.symlinks` is on, and a runner may
#: make one only in Developer Mode or elevated.
needs_disk_symlinks = pytest.mark.skipif(
    ON_WINDOWS,
    reason="a tracked symlink is a plain file in a Windows checkout")


def symlink(link: Path, target: str) -> None:
    """`link -> target`, or a skip where this runner cannot make one."""
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(target, link)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"this platform cannot create a symlink here: {exc}")


def told_git(monkeypatch, value: str) -> None:
    """`git` told `core.symlinks=<value>` through `GIT_CONFIG_*`, after
    whatever entries the runner's job sets there (the Windows job sets two),
    which stay as they were."""
    for name, entry in appended_to_command_scope(
            os.environ, [(CORE_SYMLINKS, value)]).items():
        monkeypatch.setenv(name, entry)


def links_as_files(monkeypatch) -> None:
    """`git` told to check a symlink out as a plain file, after the runner's
    own `GIT_CONFIG_*`, as Git for Windows' default does."""
    told_git(monkeypatch, "false")


def no_probe(_work_root):
    """A stand-in for `_checks_out_symlinks` where no probe may be made."""
    raise AssertionError("the probe was made")


@pytest.fixture
def links_as_links(monkeypatch):
    """`git` told to check a symlink out AS a symlink. `check` follows a
    link AT a path the shape writes only where `git` does that, and Git for
    Windows' own default is a plain file (B-OFF)."""
    told_git(monkeypatch, "true")


@pytest.fixture(scope=MODULE)
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
    """Each `links` path as a symlink (its target the blob, text or bytes)
    and each `gitlinks` path as a submodule, in the source's TREE only."""
    for link, target in links.items():
        raw = target if isinstance(target, bytes) else target.encode(UTF8)
        blob = subprocess.run(
            ["git", "hash-object", "-w", "--stdin"], cwd=str(repo),
            input=raw, capture_output=True, check=True)
        git("update-index", "--add", "--cacheinfo",
            f"{SYMLINK},{blob.stdout.decode().strip()},{link}", cwd=repo)
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


def check(plan: Path, *extra: str):
    return run_script(ADOPT, "check", PLAN_FLAG, str(plan), *extra)


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


def ticked(path: str) -> str:
    """A path as a finding spells it (`_spelled`): between backticks."""
    return f"`{path}`"


def finding(link: str, target: str, shape_path: str, why: str,
            aside: str = "", *, fix: str = "") -> str:
    """The line `check` prints, and `execute`'s refusal carries. `fix` is
    its last sentence where that is not the one for a disk that holds
    symlinks."""
    fix = fix or (f"Send {ticked(link)} to a leg or `drop` it, or change "
                  "where it points in the source and re-run `plan`.")
    return (f"{FINDING}the plan keeps {ticked(link)} in the root, a symlink "
            f"to {ticked(target)}, and {ticked(shape_path)}, a path the shape "
            f"writes, runs through it{aside}, but {why}. {fix}")


def leads(link: str, here: str, which: str) -> str:
    """Why a symlink's destination is not in the planned root."""
    return f"the symlink {ticked(link)} leads to {ticked(here)}, which {which}"


def climbs(link: str) -> str:
    return f"at the symlink {ticked(link)} it climbs above the assembly root"


def refused_alike(adopter, base: Path, plan: Path, line: str,
                  *extra: str) -> None:
    """`check` exits 1 with exactly `line`, and `execute` refuses with the
    same line, word for word, before any leg exists."""
    checked = check(plan, *extra)
    assert checked.returncode == 1, checked.stderr + checked.stdout
    assert symlink_findings(checked) == [line], checked.stderr
    refusal = refused_by(adopter, execute_args(base, plan))
    assert refusal.code == ROOT_SYMLINK
    assert f"  {line}" in refusal.detail.splitlines()
    assert "no leg repository was created" in refusal.remediation
    no_leg_was_created(base)


def passed_alike(adopter, base: Path, plan: Path, *extra: str) -> None:
    """`check` says `plan ok`, and `execute`'s refusal of `check`'s
    findings passes."""
    checked = check(plan, *extra)
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert "plan ok" in checked.stdout
    loaded = adopter.Plan.load(plan)
    # Made as `execute`'s `_work_root` makes it: the disk is asked there.
    (base / WORK).mkdir(exist_ok=True)
    source = loaded.open_source(None, base / WORK)
    assert adopter._refuse_what_check_finds(loaded, source) is None


@pytest.fixture
def no_filter_repo_probe(adopter, monkeypatch):
    """Every refusal under test comes before `git filter-repo` is used."""
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)


# ---------------------------------------------------------------------------
# Refused by `check`, and by `execute` before any leg exists
# ---------------------------------------------------------------------------

NOT_IN_THE_TREE = "is not in the source tree"
#: Why a link the shape writes through cannot lead it into the assembly's
#: own `.git` (#904): ABOVE a path the shape writes, never (D9); AT one, to
#: a name the clone does not hold by then, the shape's file would go into
#: `.git`, or find no directory there; and where `check` does not read
#: what is there, which of the two cannot be told.
IN_ITS_GIT = "is in the assembly's own `.git`"
NOT_INTO_GIT = ("a symlink above a path the shape writes is followed only "
                "through directories the root holds, never into `.git`")
ABOVE_INTO_GIT = f"{IN_ITS_GIT}, and {NOT_INTO_GIT}"
NOTHING_THERE = (f"{IN_ITS_GIT}, where its clone holds nothing of that name "
                 "by the time the shape is written, so ")
WRITTEN_INTO_GIT = (NOTHING_THERE + "the shape would write its file through "
                    "the link into `.git`, where no commit holds it")
NO_DIRECTORY_IN_GIT = (NOTHING_THERE + "the shape would find no directory "
                       "there to write its file in, and stop after both leg "
                       "repositories were created and pushed")
OBJECT_STORE = ("the clone's object store, which holds what the source's own "
                "store holds when `execute` clones it and the objects "
                "`execute` writes before the shape")
SPEC_STORE = ("the store of the spec leg, which `git submodule add` makes "
              "from that leg, with this machine's git template, after this "
              "check")
REFTABLES = ("where the reftable backend keeps the clone's refs, in tables "
             "git names as it writes them")
#: Where the source's HEAD is on no branch: each link into the refs of the
#: branch `git clone` checks out, which git guesses, and the directory of
#: them `check` reads nothing in, with what it holds.
GUESSED = "which git guesses where the source's HEAD is on no branch"
GUESSED_REFS = {
    ".git/refs/heads/main": (
        ".git/refs/heads",
        f"where `git clone` writes the branch it checks out, {GUESSED}"),
    ".git/refs/remotes/origin/HEAD": (
        ".git/refs/remotes",
        "where `git clone` writes `origin/HEAD` for the branch it checks "
        f"out, {GUESSED}"),
    ".git/logs/refs/heads/main": (
        ".git/logs/refs/heads",
        "where `git clone` writes the reflog of the branch it checks out, "
        f"{GUESSED}"),
    ".git/logs/refs/remotes/origin/HEAD": (
        ".git/logs/refs/remotes",
        "where `git clone` writes the reflog of `origin/HEAD` for the branch "
        f"it checks out, {GUESSED}"),
}


def inside(top: str, holds: str) -> str:
    """Where a name is that `check` reads nothing of: in `top`, which holds
    `holds`."""
    return f"inside {ticked(top)}, {holds}, and `check` reads nothing there"


def unread(top: str, holds: str) -> str:
    """Why a link AT a path the shape writes is refused where it leads into
    such a place."""
    return (f"is {inside(top, holds)}, so whether `place` would write the "
            "shape's copy beside it or the shape's file into `.git` cannot "
            "be told before any leg exists")
SPEC_MOUNT = "it enters `spec`, where the plan mounts the spec leg"
ON_THIS_MACHINE = ("an absolute path: a place on this machine, not in the "
                   "assembly")
#: Why the shape's scripts cannot run from where a link puts them; `{}` is
#: the directory they land in.
SCRIPTS_MISPLACED = (
    "and the shape's scripts look for the assembly root, and for "
    "contracts/repository-naming.yaml, from the directory above their own, "
    "so they run only from a directory directly under the root, which {} is "
    "not")
ON_A_FILE = ("a file that is already there, where the shape's copy cannot be "
             "written")
#: Why a path that follows more than 40 symlinks cannot be written: the
#: lookup cannot tell a loop from a long chain, and `open()` gives up on both.
TOO_MANY = ("more than 40, round a loop or along a chain longer than Linux's "
            "`open()` follows")
#: 41 symlinks and no loop, `.github -> l1`, `l1 -> l2` ... `l40 -> ci`:
#: `open()` gives up at `l40` all the same (F1 of #183's re-verify).
CHAIN = {GITHUB: "l1", **{f"l{n}": f"l{n + 1}" for n in range(1, 40)},
         "l40": "ci"}


def too_many(at: str) -> str:
    """How a refusal says that a path follows more than 40 symlinks, the
    last at `at`."""
    return f"follows too many symlinks at {ticked(at)}"

LINK_TO_GH = {"tooling/gh/workflows/build.yml": "on: push\n"}

#: `(*PLANNED, (link, target, shape path, why[, aside]))`. The first ten are
#: lane 2's table for #178 (D3-D12) and #183's loop; the rest are the other
#: ways a link the shape writes through cannot be written through.
REFUSED = [
    pytest.param({}, {ATTRIBUTES: NOWHERE_ATTRS}, {ATTRIBUTES: ROOT},
                 (ATTRIBUTES, NOWHERE_ATTRS, ATTRIBUTES,
                  leads(ATTRIBUTES, NOWHERE_ATTRS, NOT_IN_THE_TREE)),
                 id="D4-a-dangling-file-link"),
    pytest.param({"config/readme.md": "c\n"}, {ATTRIBUTES: CONFIG_ATTRS},
                 {CONFIG_DIR: ROOT, ATTRIBUTES: ROOT},
                 (ATTRIBUTES, CONFIG_ATTRS, ATTRIBUTES,
                  leads(ATTRIBUTES, CONFIG_ATTRS, NOT_IN_THE_TREE)),
                 id="D3-a-dangling-file-link-in-a-kept-directory"),
    pytest.param(LINK_TO_GH, {GITHUB: TOOLING_GH},
                 {"tooling/": CODE, GITHUB: ROOT},
                 (GITHUB, TOOLING_GH, WORKFLOW,
                  leads(GITHUB, TOOLING_GH, "the plan sends to the code leg")),
                 id="D5-into-a-path-sent-to-a-leg"),
    pytest.param(LINK_TO_GH, {GITHUB: TOOLING_GH},
                 {"tooling/": "drop", GITHUB: ROOT},
                 (GITHUB, TOOLING_GH, WORKFLOW,
                  leads(GITHUB, TOOLING_GH, "the plan sends to `drop`")),
                 id="into-a-dropped-path"),
    pytest.param({}, {GITHUB: OUTSIDE_CI}, {GITHUB: ROOT},
                 (GITHUB, OUTSIDE_CI, WORKFLOW, climbs(GITHUB)),
                 id="D6-a-relative-link-out"),
    pytest.param({}, {GITHUB: "/srv/ci"}, {GITHUB: ROOT},
                 (GITHUB, "/srv/ci", WORKFLOW,
                  f"the symlink `.github` leads to `/srv/ci`, "
                  f"{ON_THIS_MACHINE}"), id="D6b-an-absolute-link"),
    pytest.param({}, {GITHUB: "spec/ci"}, {GITHUB: ROOT},
                 (GITHUB, "spec/ci", WORKFLOW, SPEC_MOUNT),
                 id="D7-into-a-mount"),
    pytest.param({}, {GITHUB: SPEC}, {GITHUB: ROOT},
                 (GITHUB, SPEC, WORKFLOW, SPEC_MOUNT),
                 id="D7b-at-a-mount"),
    pytest.param({}, {GITHUB: "code/ci"}, {GITHUB: ROOT},
                 (GITHUB, "code/ci", WORKFLOW,
                  "it enters `code`, where the plan mounts the code leg"),
                 id="into-the-other-mount"),
    pytest.param({}, {GITHUB: GIT_INFO}, {GITHUB: ROOT},
                 (GITHUB, GIT_INFO, WORKFLOW,
                  leads(GITHUB, GIT_INFO, ABOVE_INTO_GIT)),
                 id="D9-into-dot-git"),
    pytest.param({}, {GITHUB: "../Northwind/ci"}, {GITHUB: ROOT},
                 (GITHUB, "../Northwind/ci", WORKFLOW, climbs(GITHUB)),
                 id="D12-out-and-back-by-name"),
    pytest.param({}, {GITHUB: GITHUB}, {GITHUB: ROOT},
                 (GITHUB, GITHUB, WORKFLOW,
                  f"it {too_many(GITHUB)}: {TOO_MANY}"),
                 id="a-link-to-itself"),
    pytest.param({}, {GITHUB: LOOP, LOOP: GITHUB},
                 {GITHUB: ROOT, LOOP: ROOT},
                 (GITHUB, LOOP, WORKFLOW,
                  f"it {too_many(GITHUB)}: {TOO_MANY}"),
                 id="a-loop-of-two"),
    pytest.param({CI_FILE: ON_PUSH}, CHAIN,
                 {CI_DIR: ROOT, **{link: ROOT for link in CHAIN}},
                 (GITHUB, "l1", WORKFLOW, f"it {too_many('l40')}: {TOO_MANY}"),
                 id="a-chain-of-41-links"),
    pytest.param({}, {GITHUB: README}, {GITHUB: ROOT},
                 (GITHUB, README, WORKFLOW,
                  f"it passes through {ticked(README)}, which is a file"),
                 id="to-a-file-the-shape-writes-beneath"),
    pytest.param({CI_FILE: ON_PUSH}, {GITHUB: "nowhere/../ci"},
                 {CI_DIR: ROOT, GITHUB: ROOT},
                 (GITHUB, "nowhere/../ci", WORKFLOW,
                  "it passes through `nowhere`, which is not a directory in "
                  "the assembly root"), id="dot-dot-from-nowhere"),
    pytest.param({RUN_SH: ECHO}, {GITHUB: TOOLS_UP,
                                  TOOLS_UP: "../../x"},
                 {TOOLS_DIR: ROOT, GITHUB: ROOT},
                 (GITHUB, TOOLS_UP, WORKFLOW, climbs(TOOLS_UP)),
                 id="a-chain-whose-second-link-leaves"),
    pytest.param({}, {SHAPE_DIR: "../elsewhere"}, {SHAPE_DIR: ROOT},
                 (SHAPE_DIR, "../elsewhere", SHAPE_README, climbs(SHAPE_DIR)),
                 id="the-collision-directory-leaves"),
    pytest.param({"tools/sub/run.sh": ECHO}, {SCRIPTS: TOOLS_SUB},
                 {TOOLS_DIR: ROOT, SCRIPTS: ROOT},
                 (SCRIPTS, TOOLS_SUB, VALIDATE_PINS,
                  "it lands at `tools/sub/validate-pins.py`, "
                  + SCRIPTS_MISPLACED.format(ticked(TOOLS_SUB))),
                 id="R2-scripts-two-directories-down"),
    pytest.param({}, {SCRIPTS: "."}, {SCRIPTS: ROOT},
                 (SCRIPTS, ".", VALIDATE_PINS,
                  "it lands at `validate-pins.py`, "
                  + SCRIPTS_MISPLACED.format("the root itself")),
                 id="R6-scripts-in-the-root-itself"),
    pytest.param({RUN_SH: ECHO}, {SCRIPTS: "tools/.."},
                 {TOOLS_DIR: ROOT, SCRIPTS: ROOT},
                 (SCRIPTS, "tools/..", VALIDATE_PINS,
                  "it lands at `validate-pins.py`, "
                  + SCRIPTS_MISPLACED.format("the root itself")),
                 id="R9-scripts-in-the-root-by-dot-dot"),
    pytest.param({"scripts/own.sh": ECHO, RUN_SH: ECHO},
                 {BOOTSTRAP_PY: "../tools/bootstrap.py"},
                 {TOOLS_DIR: ROOT, "scripts/": ROOT},
                 (BOOTSTRAP_PY, "../tools/bootstrap.py", BOOTSTRAP_PY,
                  leads(BOOTSTRAP_PY, "tools/bootstrap.py", NOT_IN_THE_TREE)),
                 id="R10-one-script-apart-from-the-rest"),
    # The shape writes AGENTS.md before CLAUDE.md, so AGENTS.md still
    # dangles when the shape writes through it.
    pytest.param({}, {AGENTS: CLAUDE}, {AGENTS: ROOT},
                 (AGENTS, CLAUDE, AGENTS,
                  leads(AGENTS, CLAUDE, NOT_IN_THE_TREE)),
                 id="a-link-to-what-the-shape-writes-only-later"),
    pytest.param({DOCS_AGENTS: "a\n"}, {AGENTS: SPEC_OTHER},
                 {DOCS_DIR: SPEC, AGENTS: ROOT},
                 (AGENTS, SPEC_OTHER, AGENTS,
                  leads(AGENTS, SPEC_OTHER,
                        "the spec leg, mounted at `spec`, does not hold")),
                 id="at-a-path-into-a-leg-that-lacks-it"),
    # Only a template puts `description` in `.git`, and `execute` clones
    # with none: the shape would write through the link into the clone's own
    # `.git`, where no commit holds it.
    pytest.param({}, {CLAUDE: GIT_DESCRIPTION}, {CLAUDE: ROOT},
                 (CLAUDE, GIT_DESCRIPTION, CLAUDE,
                  leads(CLAUDE, GIT_DESCRIPTION, WRITTEN_INTO_GIT)),
                 id="at-a-path-to-what-only-a-template-puts-in-dot-git"),
    pytest.param({}, {CLAUDE: GIT_HOOKS}, {CLAUDE: ROOT},
                 (CLAUDE, GIT_HOOKS, CLAUDE,
                  leads(CLAUDE, GIT_HOOKS, WRITTEN_INTO_GIT)),
                 id="at-a-path-to-the-hooks-only-a-template-makes"),
    # #904, L1-J1 of #457: a name the clone's `.git` does not hold, in a
    # directory git makes there, which checked ok while `.git/objects`,
    # `.git/refs`, `.git/logs` and `.git/modules` were counted whole.
    *(pytest.param({}, {CLAUDE: missing}, {CLAUDE: ROOT},
                   (CLAUDE, missing, CLAUDE,
                    leads(CLAUDE, missing, WRITTEN_INTO_GIT)),
                   id="J1-at-a-path-to-no-" + missing[5:].replace("/", "-"))
      for missing in GIT_MISSING),
    pytest.param({}, {CLAUDE: GIT_NO_DIRECTORY}, {CLAUDE: ROOT},
                 (CLAUDE, GIT_NO_DIRECTORY, CLAUDE,
                  leads(CLAUDE, GIT_NO_DIRECTORY, NO_DIRECTORY_IN_GIT)),
                 id="at-a-path-to-no-directory-in-dot-git"),
    pytest.param({}, {CLAUDE: GIT_OBJECT}, {CLAUDE: ROOT},
                 (CLAUDE, GIT_OBJECT, CLAUDE,
                  leads(CLAUDE, GIT_OBJECT,
                        unread(".git/objects", OBJECT_STORE))),
                 id="J1-at-a-path-into-the-object-store"),
    pytest.param({}, {CLAUDE: GIT_IN_A_STORE}, {CLAUDE: ROOT},
                 (CLAUDE, GIT_IN_A_STORE, CLAUDE,
                  leads(CLAUDE, GIT_IN_A_STORE,
                        unread(".git/modules/spec", SPEC_STORE))),
                 id="at-a-path-into-a-legs-store"),
    # J2 of #457: a `..` in the clone's `.git`. ABOVE a path the shape
    # writes it is refused, as D9 refuses the link, and says so; AT one it
    # steps back out only of a directory git makes there.
    pytest.param({}, {GITHUB: ".git/refs/.."}, {GITHUB: ROOT},
                 (GITHUB, ".git/refs/..", WORKFLOW,
                  "it passes through `.git/refs`, in the assembly's own "
                  f"`.git`, and {NOT_INTO_GIT}"),
                 id="J2-above-a-path-back-out-of-dot-git-refs"),
    pytest.param({}, {CLAUDE: ".git/refs/nope/../HEAD"}, {CLAUDE: ROOT},
                 (CLAUDE, ".git/refs/nope/../HEAD", CLAUDE,
                  "it passes through `.git/refs/nope`, in the assembly's own "
                  "`.git`, where its clone holds no directory of that name by "
                  "the time the shape is written"),
                 id="J2-at-a-path-back-out-of-no-directory-in-dot-git"),
    pytest.param({}, {CLAUDE: ".git/objects/ab/../info"}, {CLAUDE: ROOT},
                 (CLAUDE, ".git/objects/ab/../info", CLAUDE,
                  "it passes through `.git/objects/ab`, "
                  f"{inside('.git/objects', OBJECT_STORE)}, so whether it is "
                  "a directory cannot be told before any leg exists"),
                 id="J2-at-a-path-back-out-of-the-object-store"),
    # B2: the copy under `shape/` lands on something already there.
    pytest.param({}, {SHAPE_DIR: "."}, {SHAPE_DIR: ROOT},
                 (SHAPE_DIR, ".", SHAPE_README,
                  f"it lands on {ticked(README)}, {ON_A_FILE}"),
                 id="the-collision-directory-is-the-root"),
    pytest.param({"vendor/README.md": "vendor's own\n"}, {SHAPE_DIR: VENDOR},
                 {VENDOR_DIR: ROOT, SHAPE_DIR: ROOT},
                 (SHAPE_DIR, VENDOR, SHAPE_README,
                  f"it lands on `vendor/README.md`, {ON_A_FILE}"),
                 id="the-collision-directory-holds-the-name"),
    pytest.param({"sub/README.md/x.txt": "x\n"}, {SHAPE_DIR: "sub"},
                 {"sub/": ROOT, SHAPE_DIR: ROOT},
                 (SHAPE_DIR, "sub", SHAPE_README,
                  "it lands on `sub/README.md`, a directory that is already "
                  "there, where the shape's copy cannot be written"),
                 id="the-collision-directory-holds-a-directory-of-the-name"),
    # S1: a case twin is followed as a disk that ignores case follows it.
    pytest.param({}, {GITHUB_TWIN: OUTSIDE_CI}, {GITHUB_TWIN: ROOT},
                 (GITHUB_TWIN, OUTSIDE_CI, WORKFLOW, climbs(GITHUB_TWIN),
                  CASE_ASIDE), id="a-case-twin-above-a-shape-path"),
    pytest.param({}, {GITIGNORE_TWIN: NOWHERE_GITIGNORE},
                 {GITIGNORE_TWIN: ROOT},
                 (GITIGNORE_TWIN, NOWHERE_GITIGNORE, ".gitignore",
                  leads(GITIGNORE_TWIN, NOWHERE_GITIGNORE, NOT_IN_THE_TREE),
                  CASE_ASIDE), id="a-case-twin-at-a-shape-path"),
]


@pytest.mark.parametrize((*PLANNED, "expected"), REFUSED)
def test_check_reports_the_link_and_execute_refuses_it_before_any_leg(
        adopter, no_filter_repo_probe, links_as_links, tmp_path, files, links,
        legs, expected):
    """One finding naming the link, its target and the shape path that runs
    through it; `execute` refuses with the same line, word for word, and
    makes no leg, so the corrected plan does not meet `leg-remote-exists`."""
    _, plan = planned(tmp_path, files, links, legs)
    refused_alike(adopter, tmp_path, plan, finding(*expected))


def test_a_link_into_a_submodule_kept_in_the_root_is_reported(
        links_as_links, tmp_path):
    """A gitlink is a directory in a checkout, holding another repository:
    a link into it is not a link into `a file`."""
    _, plan = planned(tmp_path, {}, {GITHUB: "vendor/lib/ci"},
                      {GITHUB: ROOT, VENDOR_DIR: ROOT},
                      gitlinks=("vendor/lib",))
    checked = check(plan)
    assert finding(GITHUB, "vendor/lib/ci", WORKFLOW,
                   "it enters `vendor/lib`, a submodule the plan keeps in the "
                   "root") in symlink_findings(checked), checked.stderr


def test_one_finding_per_link_however_many_shape_paths_run_through_it(
        links_as_links, tmp_path):
    """`contracts -> /srv` carries four shape paths; the finding names the
    first one the materializer writes."""
    _, plan = planned(tmp_path, {}, {CONTRACTS: "/srv"},
                      {CONTRACTS: ROOT})
    findings = symlink_findings(check(plan))
    assert findings == [finding(
        CONTRACTS, "/srv", "contracts/spec-pin.yaml",
        f"the symlink `contracts` leads to `/srv`, {ON_THIS_MACHINE}")]


def test_a_link_at_the_copy_is_one_finding_by_the_rule_that_sees_it(
        adopter, no_filter_repo_probe, tmp_path):
    """A symlink kept AT the copy under `shape/` of a path the root holds is
    #262's: `plan-root-blocks-shape-copy` names it, saying the materializer
    writes no copy through it and stops there (#904, L1-K9 of #457), and
    this rule does not say the same link again. `execute`
    refuses with that line, before any leg. Where the root holds the path
    only through a symlink above it (`.github -> ci`, the project's own
    `ci/workflows/validate.yml` kept), #262's rule, which follows no link,
    does not see the copy, and the link at it is this rule's."""
    held = tmp_path / "held"
    _, plan = planned(held, {NOTES_MD: "n\n"},
                      {SHAPE_README: f"../{NOTES_MD}"},
                      {NOTES_MD: ROOT, "shape/": ROOT})
    checked = check(plan)
    assert checked.returncode == 1, checked.stderr + checked.stdout
    assert symlink_findings(checked) == [], checked.stderr
    said = [line for line in checked.stderr.splitlines()
            if line.startswith(COPY_FINDING)]
    assert len(said) == 1, checked.stderr
    assert f"That path is the symlink {ticked(SHAPE_README)}." in said[0]
    assert ("the materializer writes no copy through it: it would stop "
            "there (`materialize-copy-blocked`)") in said[0]
    refusal = refused_by(adopter, execute_args(held, plan))
    assert refusal.code == COPY_IN_THE_WAY
    assert f"  {said[0]}" in refusal.detail.splitlines()
    no_leg_was_created(held)

    through = tmp_path / "through"
    copy = f"{SHAPE_DIR}/{WORKFLOW}"
    out_of_the_copy = f"../../../{NOTES_MD}"
    _, plan = planned(through, {"ci/workflows/validate.yml": ON_PUSH,
                                NOTES_MD: "n\n"},
                      {GITHUB: "ci", copy: out_of_the_copy},
                      {CI_DIR: ROOT, GITHUB: ROOT, NOTES_MD: ROOT,
                       "shape/": ROOT})
    refused_alike(adopter, through, plan, finding(
        copy, out_of_the_copy, copy,
        f"it lands on {ticked(NOTES_MD)}, {ON_A_FILE}"))


#: Two targets that are not plain text: a byte that is not UTF-8, and a
#: newline that would end the one-line FINDING.
SPELLED = [
    pytest.param(b"nowhere\xff", "nowhere\\udcff", id="not-utf-8"),
    pytest.param(b"a\nb", "a\\nb", id="a-newline"),
]


@pytest.mark.parametrize(("raw", "spelled"), SPELLED)
def test_a_target_that_is_not_plain_text_is_spelled(links_as_links, tmp_path,
                                                    raw, spelled):
    """As #166's findings spell a path: between backticks, a byte that is
    not UTF-8 as `\\udcff`, the plan's own spelling of it (#329), and a
    newline as `\\n`, so the finding is one line that reads one way."""
    _, plan = planned(tmp_path, {}, {GITHUB: raw}, {GITHUB: ROOT})
    checked = check(plan)
    assert symlink_findings(checked) == [finding(
        GITHUB, spelled, WORKFLOW, leads(GITHUB, spelled, NOT_IN_THE_TREE))]


#: A drive letter's paths, as a source written on Windows can hold them:
#: absolute there, and on Linux and macOS a relative path into a directory
#: named `C:` (F2 of #183's re-verify). Nothing on a Windows runner is at
#: either.
DRIVE_CLAUDE = "C:/no-such-dir-183/CLAUDE.md"
DRIVE_CI = "C:/no-such-dir-183/ci"


def drive_reading(link: str, target: str, at_the_path: bool) -> str:
    """Why `link -> target`, a drive letter's path, cannot be written
    through, read as this machine's `open()` reads it."""
    if not ON_WINDOWS:
        return leads(link, target, NOT_IN_THE_TREE)
    where = (f"the symlink {ticked(link)} leads to {ticked(target)}, "
             f"{ON_THIS_MACHINE}")
    return f"{where}, and nothing is there" if at_the_path else where


@pytest.mark.parametrize(("link", "target", "path"), [
    pytest.param(CLAUDE, DRIVE_CLAUDE, CLAUDE, id="at-a-shape-path"),
    pytest.param(GITHUB, DRIVE_CI, WORKFLOW, id="above-a-shape-path"),
])
def test_a_drive_letter_target_is_read_as_this_machine_reads_it(
        adopter, no_filter_repo_probe, links_as_links, tmp_path, link, target,
        path):
    """`C:/x` is absolute only on Windows. There it is a place on this
    machine, not in the assembly; on Linux and macOS it is a relative path,
    and nothing in this source is at it. Refused on every disk, and each
    sentence is true where it prints: on Linux it used to say "an absolute
    path: a place on this machine"."""
    _, plan = planned(tmp_path, {}, {link: target}, {link: ROOT})
    refused_alike(adopter, tmp_path, plan, finding(
        link, target, path, drive_reading(link, target, link == path)))


@pytest.mark.skipif(ON_WINDOWS,
                    reason="Windows cannot hold a directory named `C:`")
def test_a_drive_letter_target_into_the_root_is_followed_off_windows(
        adopter, tmp_path):
    """On Linux and macOS, `.github -> C:/ci` leads into the root's own
    `C:/ci`, as it does on main, which adopts it and bootstraps: `open()`
    and the materializer follow it there, and so does `check`."""
    _, plan = planned(tmp_path, {"C:/ci/keep.txt": "k\n"},
                      {GITHUB: "C:/ci"}, {"C:/": ROOT, GITHUB: ROOT})
    passed_alike(adopter, tmp_path, plan)


#: `main`'s finding (#303) for a symlink of the source with an empty target.
EMPTY_SYMLINK = "plan-empty-symlink"


@pytest.mark.parametrize("links, legs, empty", [
    pytest.param({GITHUB: ""}, {GITHUB: ROOT}, GITHUB, id="above"),
    pytest.param({CLAUDE: ""}, {CLAUDE: ROOT}, CLAUDE, id="at"),
    pytest.param({GITHUB: "ci", "ci": ""}, {GITHUB: ROOT, "ci": ROOT},
                 "ci", id="second-in-a-chain"),
    pytest.param({"scripts": ""}, {"scripts": ROOT}, "scripts",
                 id="above-the-scripts"),
    pytest.param({"shape": ""}, {"shape": ROOT}, "shape",
                 id="above-the-copies"),
])
def test_a_link_with_an_empty_target_is_mains_to_report(
        adopter, no_filter_repo_probe, tmp_path, links, legs, empty):
    """Linux cannot hold a symlink to nothing, and every clone `execute`
    makes of the source checks it out, wherever the plan sends it. `main`
    (#303) names each such symlink in the source as `plan-empty-symlink`,
    with the fix in the source. A shape path that runs through one, at,
    above or along a chain, gets no `plan-root-symlink` beside it: one link,
    one finding, and `execute` refuses with `main`'s. Above `scripts` and
    above `shape`, the empty target walked on as the root would be a fault
    of its own (the scripts land in the root; a copy lands on the root's own
    `README.md`), so those two cases hold the walk to marking the link
    empty."""
    _, plan = planned(tmp_path, {}, links, legs)
    checked = check(plan)
    assert checked.returncode == 1, checked.stderr + checked.stdout
    assert symlink_findings(checked) == [], checked.stderr
    said = [line for line in checked.stderr.splitlines()
            if line.startswith(f"FINDING {EMPTY_SYMLINK}: ")]
    assert len(said) == 1, checked.stderr
    assert said[0].startswith(f"FINDING {EMPTY_SYMLINK}: {ticked(empty)} ")
    refusal = refused_by(adopter, execute_args(tmp_path, plan))
    assert refusal.code == EMPTY_SYMLINK
    assert f"  {said[0]}" in refusal.detail.splitlines()
    assert ROOT_SYMLINK not in refusal.detail
    no_leg_was_created(tmp_path)


# ---------------------------------------------------------------------------
# A declared pin's file (#273)
# ---------------------------------------------------------------------------
#
# Since #273, `execute` writes `contracts/<product>-pin.yaml` for each pin the
# plan declares, through `place`, after the copies and before the shape's own
# pin. The walk follows those files too, so a link that only a pin's file
# runs through, and that it cannot be written through, is refused before any
# leg; walked without them, `check` passed such a link, and `execute` stopped
# at one after both legs (rv183g's P1). A link AT a pin's file stays #273's
# `plan-root-holds-pin`, one finding.

GOVERNANCE = "governance"
GLASS, LENS = "openGlass", "openLens"
#: The name of the file `execute` writes the pin the plan declares on
#: openGlass to, in `contracts/`; and where it lands through
#: `contracts -> governance`.
PIN_NAME = "openglass-pin.yaml"
PIN_FILE = f"{CONTRACTS}/{PIN_NAME}"
GOVERNANCE_PIN = f"{GOVERNANCE}/{PIN_NAME}"
ROOT_HOLDS_PIN = "plan-root-holds-pin"
PIN_MALFORMED = "plan-pin-malformed"
PIN_UNRECORDED = "plan-pin-unrecorded"
SHAPE_PIN = "contracts/shape-pin.yaml"
#: What `plan` writes for a plan that declares no pin.
NO_PIN = "pins: []\n"
#: An absolute path where nothing is; `{b}` is the test's own directory.
ABSOLUTE_PIN = "{b}/abs/pin.yaml"
#: A `contracts/` the root keeps, with nothing at a pin's file.
REAL_CONTRACTS = ({"contracts/README.md": "c\n"}, {"contracts/": ROOT})
#: rv183g's source: `contracts -> governance`, a directory the root keeps.
THROUGH_GOVERNANCE = ({"governance/README.md": "# governance\n"},
                      {CONTRACTS: ROOT, "governance/": ROOT})


def pin_row(product: str, commit: bool = True) -> str:
    """One `pins:` entry as `plan --pin <product>@<commit>` records it, or,
    without `commit`, the same entry with its commit left out."""
    lines = [f"  - product: {product}",
             f"    repository: opensoft/{product}",
             f"    commit: \"{'0123456789abcdef' * 2}01234567\"",
             f"    tree_sha256: \"{'0123456789abcdef' * 4}\"",
             f"    digest_source: \"local-clone ({product})\""]
    return "\n".join(lines if commit else lines[:2] + lines[3:]) + "\n"


def declare(plan: Path, block: str) -> None:
    """The plan's `pins: []` replaced by `block`, which starts with `pins:`,
    as a hand edit would leave it: bytes, so LF everywhere. It is read as
    text, which reads `\\r\\n` as `\\n`, because `answer` writes the plan
    back with `write_text`, and on Windows that ends every line `\\r\\n`."""
    text = plan.read_text(encoding=UTF8)
    assert text.count(NO_PIN) == 1, "the plan was written with no pin"
    plan.write_bytes(text.replace(NO_PIN, block, 1).encode(UTF8))


def through_governance(base: Path, target: str, block: str) -> Path:
    """The plan for rv183g's source, whose `governance/openglass-pin.yaml`
    leads to `target`, with `block` as its `pins:`."""
    files, legs = THROUGH_GOVERNANCE
    _, plan = planned(base, files, {CONTRACTS: GOVERNANCE,
                                    GOVERNANCE_PIN: target}, legs)
    declare(plan, block)
    return plan


def planned_root(adopter, base: Path, plan: Path):
    """`(the plan, its source, the walks' `_PlannedRoot`)`, as `check` reads
    them, with symlinks taken to be checked out as symlinks."""
    loaded = adopter.Plan.load(plan)
    (base / WORK).mkdir(exist_ok=True)
    source = loaded.open_source(None, base / WORK)
    return loaded, source, adopter._PlannedRoot(
        loaded, source, source.tree(), probe=adopter._SymlinkProbe(None))


A_PIN = "pins:\n" + pin_row(GLASS)

#: `(where governance/openglass-pin.yaml leads, why)`: rv183g's three, and
#: one that dangles inside, which `place` writes the pin through and this
#: branch refuses as it refuses AT-dangle-dir-present. `{b}` is the test's
#: own directory and `{w}` the work directory.
PIN_THROUGH = [
    pytest.param(ABSOLUTE_PIN,
                 f"the symlink {ticked(GOVERNANCE_PIN)} leads to "
                 f"{ticked(ABSOLUTE_PIN)}, {ON_THIS_MACHINE}, and "
                 "nothing is there", id="an-absolute-path-where-nothing-is"),
    pytest.param("../../outside-pin.yaml",
                 f"{climbs(GOVERNANCE_PIN)}, to "
                 f"{ticked('{w}/outside-pin.yaml')}, where nothing is",
                 id="out-of-the-root"),
    pytest.param(PIN_NAME,
                 f"it {too_many(GOVERNANCE_PIN)}: {TOO_MANY}", id="itself"),
    pytest.param("nowhere.yaml",
                 leads(GOVERNANCE_PIN, "governance/nowhere.yaml",
                       NOT_IN_THE_TREE), id="nowhere-inside"),
]


def where(text: str, base: Path) -> str:
    """`text` with `{b}` and `{w}` filled in for the test's directory."""
    return text.format(b=base.as_posix(),
                       w=(base / WORK).resolve().as_posix())


@pytest.mark.parametrize(("target", "why"), PIN_THROUGH)
def test_a_link_only_a_pins_file_runs_through_is_refused_before_any_leg(
        adopter, no_filter_repo_probe, links_as_links, tmp_path, target,
        why):
    """rv183g's P1. No other path the shape writes meets
    `governance/openglass-pin.yaml`; with `--pin openGlass@<commit>`,
    `execute` writes the pin's file through it. It stopped there after both
    legs on the first three (`materialize-outside`,
    `materialize-symlink-loop`), and wrote the fourth through the link, which
    this branch refuses as it refuses AT-dangle-dir-present. Now `check`
    says each once, naming the first link and the pin's file, and `execute`
    refuses with the same line before any leg."""
    plan = through_governance(tmp_path, where(target, tmp_path), A_PIN)
    refused_alike(adopter, tmp_path, plan,
                  finding(CONTRACTS, GOVERNANCE, PIN_FILE,
                          where(why, tmp_path)),
                  WORK_FLAG, str(tmp_path / WORK))


@pytest.mark.parametrize("target", [
    pytest.param(case.values[0], id=case.id) for case in PIN_THROUGH])
def test_without_a_pin_no_path_the_shape_writes_meets_that_link(
        adopter, links_as_links, tmp_path, target):
    """The control: the same source with no pin declared. No path the shape
    writes runs through `governance/openglass-pin.yaml`, so it is not this
    check's business."""
    plan = through_governance(tmp_path, where(target, tmp_path), NO_PIN)
    passed_alike(adopter, tmp_path, plan, WORK_FLAG, str(tmp_path / WORK))


@needs_filter_repo
@needs_disk_symlinks
def test_without_a_pin_that_source_adopts(tmp_path):
    """The control end to end: `contracts -> governance`, with
    `governance/openglass-pin.yaml` leading to an absolute path where
    nothing is, and no pin, adopts, the link kept as the source had it."""
    target = where(ABSOLUTE_PIN, tmp_path)
    plan = through_governance(tmp_path, target, NO_PIN)
    result = execute(tmp_path, plan)
    assert result.returncode == 0, result.stderr + result.stdout
    assert VERIFIED in result.stdout
    source = tmp_path / THING
    assert split_modes(source)[GOVERNANCE_PIN] == SYMLINK
    assert git("show", f"{BRANCH}:{GOVERNANCE_PIN}",
               cwd=source).stdout == target


@pytest.mark.parametrize(("link", "aside"), [
    pytest.param(PIN_FILE, "", id="at-the-pins-file"),
    pytest.param("contracts/OpenGlass-pin.yaml", CASE_ASIDE,
                 id="a-case-twin-at-it"),
])
def test_a_link_at_a_pins_file_is_one_finding_by_the_rule_that_sees_it(
        adopter, no_filter_repo_probe, links_as_links, tmp_path, link,
        aside):
    """A symlink kept AT a pin's file is #273's: `plan-root-holds-pin` names
    it, on a disk that keeps case or, for a case twin, on one that ignores
    it. The walk, which follows the pin's file now, meets the same link
    leading nowhere and does not say it again: one link, one finding, and
    `execute` refuses with #273's line."""
    files, legs = REAL_CONTRACTS
    _, plan = planned(tmp_path, files, {link: "nowhere.yaml"}, legs)
    declare(plan, A_PIN)
    checked = check(plan)
    assert checked.returncode == 1, checked.stderr + checked.stdout
    assert symlink_findings(checked) == [], checked.stderr
    said = [line for line in checked.stderr.splitlines()
            if line.startswith(f"FINDING {ROOT_HOLDS_PIN}: ")]
    assert len(said) == 1, checked.stderr
    assert said[0].startswith(f"FINDING {ROOT_HOLDS_PIN}: the plan keeps the "
                              f"symlink {ticked(link)} "), said[0]
    assert f"at {ticked(PIN_FILE)}{aside}, where `execute` writes" in said[0]
    refusal = refused_by(adopter, execute_args(tmp_path, plan))
    assert refusal.code == ROOT_HOLDS_PIN
    assert f"  {said[0]}" in refusal.detail.splitlines()
    assert ROOT_SYMLINK not in refusal.detail
    no_leg_was_created(tmp_path)


#: What `plan-root-holds-pin` says of a declared pin's file.
DECLARED_HELD = ("the pin the plan declares on `openGlass`. The shape's pin "
                 "would be written beside it, under `shape/`, and the root's "
                 "own `validate-pins.py` would read the source's file as that "
                 "pin")
#: `(files, links, what is kept at the pin's file, the link it is reached
#: through, aside)`: rv183g's source, `governance/` kept, holding the pin's
#: file, reached through a kept link above `contracts/`. `place` finds it
#: there, writes the pin beside it, and the root's `contracts/
#: openglass-pin.yaml` is the source's: `check` passed each, and the
#: root's first bootstrap refused the file as `yaml-unparsable` and the
#: link as `neutral-pin-unreadable` (#904, L1-K2 of #457).
HELD_THROUGH = [
    pytest.param({GOVERNANCE_PIN: "not a pin\n"}, {CONTRACTS: GOVERNANCE},
                 "the file", CONTRACTS, "", id="a-file"),
    pytest.param({}, {CONTRACTS: GOVERNANCE, GOVERNANCE_PIN: README},
                 "the symlink", CONTRACTS, "", id="a-link-to-the-readme"),
    pytest.param({GOVERNANCE_PIN: "not a pin\n"}, {"Contracts": GOVERNANCE},
                 "the file", "Contracts", CASE_ASIDE, id="through-a-case-twin"),
]


def held_pins(result) -> list[str]:
    return [line for line in result.stderr.splitlines()
            if line.startswith(f"FINDING {ROOT_HOLDS_PIN}: ")]


def held_through(kind: str, link: str, aside: str, held: str, rel: str,
                 written: str) -> str:
    """`plan-root-holds-pin` for `held`, kept under `governance/` and
    reached as the pin's file `rel` through the symlink `link`."""
    return (f"FINDING {ROOT_HOLDS_PIN}: the plan keeps {kind} {ticked(held)} "
            "in the assembly root under the entry `governance/`, at "
            f"{ticked(rel)} through the symlink {ticked(link)} to "
            f"`governance`{aside}, where `execute` writes {written}: send "
            f"{ticked(link)} to a leg or `drop` it, or rename {ticked(held)} "
            "in the source and re-run `plan`.")


@pytest.mark.parametrize(("files", "links", "kind", "link", "aside"),
                         HELD_THROUGH)
def test_a_pins_file_the_root_keeps_through_a_link_is_refused_before_any_leg(
        adopter, no_filter_repo_probe, links_as_links, tmp_path, files, links,
        kind, link, aside):
    """The pin's file is asked through the links the plan keeps above it,
    as the walk follows it, and the source's file there is #273's
    `plan-root-holds-pin`, once, naming the link; `execute` refuses with the
    same line before any leg. A link there that leads nowhere is the walk's
    still (`PIN_THROUGH`): one link, one finding."""
    base_files, _ = THROUGH_GOVERNANCE
    _, plan = planned(tmp_path, {**base_files, **files}, links,
                      {"governance/": ROOT, link: ROOT})
    declare(plan, A_PIN)
    checked = check(plan)
    assert checked.returncode == 1, checked.stderr + checked.stdout
    assert symlink_findings(checked) == [], checked.stderr
    line = held_through(kind, link, aside, GOVERNANCE_PIN, PIN_FILE,
                        DECLARED_HELD)
    assert held_pins(checked) == [line], checked.stderr
    refusal = refused_by(adopter, execute_args(tmp_path, plan))
    assert refusal.code == ROOT_HOLDS_PIN
    assert f"  {line}" in refusal.detail.splitlines()
    no_leg_was_created(tmp_path)


def test_the_shapes_own_pin_the_root_keeps_through_a_link_is_refused_too(
        adopter, no_filter_repo_probe, links_as_links, tmp_path):
    """The same for the shape's own pin, with no pin declared: `place`
    wrote it beside `governance/shape-pin.yaml`, and `execute`'s
    verification failed as `adopt-shape-pin-unreadable` after both legs
    (measured on main 6c861635 and 5e539a87)."""
    files, legs = THROUGH_GOVERNANCE
    held = f"{GOVERNANCE}/shape-pin.yaml"
    _, plan = planned(tmp_path, {**files, held: "x\n"},
                      {CONTRACTS: GOVERNANCE}, legs)
    checked = check(plan)
    assert checked.returncode == 1, checked.stderr + checked.stdout
    said = held_pins(checked)
    assert len(said) == 1, checked.stderr
    whole = held_through("the file", CONTRACTS, "", held, SHAPE_PIN,
                         "the shape's own pin")
    head, _, tail = whole.partition("the shape's own pin")
    assert said[0].startswith(head + "the shape's own pin: "), said[0]
    assert said[0].endswith(tail), said[0]
    refusal = refused_by(adopter, execute_args(tmp_path, plan))
    assert refusal.code == ROOT_HOLDS_PIN
    no_leg_was_created(tmp_path)


def test_a_directory_at_a_pins_file_through_a_link_names_what_it_reaches(
        adopter, no_filter_repo_probe, links_as_links, tmp_path):
    """A directory the root keeps where the walk reaches the pin's file,
    `governance/openglass-pin.yaml/`, is `plan-root-holds-pin` too: the
    finding names the first file kept in it (`README.md`, which sorts
    before `notes.md`), inside the pin's file, and its fix renames the
    directory the walk reaches, not that file (rv1091's NIT 4 on #1091).
    Before #1091 `check` passed it (measured on main 823624d9). The
    directory holds two files, so that the first is not the last
    (rv1140's NIT 1)."""
    files, legs = THROUGH_GOVERNANCE
    held = f"{GOVERNANCE_PIN}/{README}"
    later = f"{GOVERNANCE_PIN}/notes.md"
    _, plan = planned(tmp_path, {**files, later: "# notes\n",
                                 held: "# readme\n"},
                      {CONTRACTS: GOVERNANCE}, legs)
    declare(plan, A_PIN)
    checked = check(plan)
    assert checked.returncode == 1, checked.stderr + checked.stdout
    assert symlink_findings(checked) == [], checked.stderr
    line = (f"FINDING {ROOT_HOLDS_PIN}: the plan keeps the file "
            f"{ticked(held)} in the assembly root under the entry "
            f"`governance/`, inside {ticked(PIN_FILE)} through the symlink "
            f"{ticked(CONTRACTS)} to `governance`, where `execute` writes "
            f"{DECLARED_HELD}: send {ticked(CONTRACTS)} to a leg or `drop` "
            f"it, or rename {ticked(GOVERNANCE_PIN)} in the source and "
            "re-run `plan`.")
    assert held_pins(checked) == [line], checked.stderr
    refusal = refused_by(adopter, execute_args(tmp_path, plan))
    assert refusal.code == ROOT_HOLDS_PIN
    assert f"  {line}" in refusal.detail.splitlines()
    no_leg_was_created(tmp_path)


def test_a_pins_file_through_a_link_to_where_nothing_is_kept_is_no_finding(
        links_as_links, tmp_path):
    """The control: nothing is kept at `governance/openglass-pin.yaml`, so
    `place` writes the pin there, through the link, and the root reads it
    at `contracts/openglass-pin.yaml`, as on main."""
    files, legs = THROUGH_GOVERNANCE
    _, plan = planned(tmp_path, files, {CONTRACTS: GOVERNANCE}, legs)
    declare(plan, A_PIN)
    checked = check(plan)
    assert held_pins(checked) == [], checked.stderr
    assert symlink_findings(checked) == [], checked.stderr


#: `pins:` blocks `execute` writes no pin file from, with the code `check`
#: names each by.
NOT_A_PIN = [
    pytest.param("pins: 7\n", PIN_MALFORMED, id="a-number"),
    pytest.param(f"pins: {GLASS}\n", PIN_MALFORMED, id="text"),
    pytest.param("pins:\n  - 7\n", PIN_MALFORMED, id="an-entry-7"),
    pytest.param(f"pins:\n  - {GLASS}\n", PIN_UNRECORDED, id="a-name-alone"),
    pytest.param("pins:\n" + pin_row(GLASS, commit=False), PIN_UNRECORDED,
                 id="no-commit"),
]


@pytest.mark.parametrize(("block", "code"), NOT_A_PIN)
def test_a_pins_block_execute_writes_no_file_from_adds_no_path(
        adopter, no_filter_repo_probe, links_as_links, tmp_path, block,
        code):
    """The walk reads the pins as `_leg_collision_findings` reads them,
    `_declared_pins`: only the entries `execute` writes a file from. So a
    `pins:` that is no list, or an entry that is no pin, adds no path to
    walk and raises nothing, and the link only a pin's file would meet gets
    no finding of its own: `check` names the `pins:` alone, with no
    traceback, and `execute` refuses with that, before any leg. The walk is
    asked directly too, as `_root_symlink_findings` makes it."""
    plan = through_governance(tmp_path, where(ABSOLUTE_PIN, tmp_path), block)
    checked = check(plan)
    assert checked.returncode == 1, checked.stderr + checked.stdout
    assert "Traceback" not in checked.stderr, checked.stderr
    said = [line for line in checked.stderr.splitlines()
            if line.startswith("FINDING ")]
    assert said, checked.stderr
    assert all(line.startswith(f"FINDING {code}: ") for line in said), said
    refusal = refused_by(adopter, execute_args(tmp_path, plan))
    assert refusal.code == code
    assert ROOT_SYMLINK not in refusal.detail
    no_leg_was_created(tmp_path)
    loaded, source, walked = planned_root(adopter, tmp_path, plan)
    assert walked.pins == []
    assert [walk.path for walk in walked.walks()
            if not walk.path.startswith(f"{SHAPE_DIR}/")] == list(
                assembly_root_paths())
    assert adopter._root_symlink_findings(loaded, source,
                                          source.tree()) == []


def test_the_walk_follows_each_pins_file_where_the_materializer_writes_it(
        adopter, tmp_path):
    """The pins the walk follows are those `execute` hands the materializer
    (`_recorded_pins`), each product once, in the plan's order; and the
    paths it follows are those the materializer writes when it is handed
    them, in its order: each pin's file after the copies, and the shape's
    own pin last."""
    _, plan = planned(tmp_path, {}, {}, {})
    declare(plan, "pins:\n" + pin_row(LENS) + pin_row(GLASS) + pin_row(LENS))
    loaded, _, walked = planned_root(adopter, tmp_path, plan)
    assert walked.pins == [LENS, GLASS]
    assert walked.pins == list(adopter._recorded_pins(loaded))
    target = tmp_path / ASSEMBLY
    target.mkdir()
    written = materialize_assembly_root(
        REPO, target, template_values(), collision_dir=SHAPE_DIR,
        neutral_pins={product: {} for product in walked.pins}).written
    assert [walk.path for walk in walked.walks()
            if not walk.path.startswith(f"{SHAPE_DIR}/")] == written
    assert written == list(assembly_root_paths(walked.pins))
    assert written[-3:] == ["contracts/openlens-pin.yaml", PIN_FILE,
                            SHAPE_PIN]


def test_a_link_to_a_pins_file_finds_the_pin_place_wrote_first(
        adopter, links_as_links, tmp_path):
    """rv183g's side effect: with a pin, `contracts/shape-pin.yaml ->
    openglass-pin.yaml`. `place` writes the pin's file before the shape's
    own pin, so it finds a file there and writes the shape's pin beside it,
    under `shape/`, as it does for any path the root holds. The walk now
    says the same, where it said the link led to what is not in the source
    tree, and `check` prints no link finding for it. (The root's
    `contracts/shape-pin.yaml` is then not the shape's pin: a question of
    what the root keeps at the shape's pin, not of where this link leads,
    which `plan-root-holds-pin` now answers before any leg, as it does for
    a file the source keeps there, #524.)"""
    files, legs = REAL_CONTRACTS
    _, plan = planned(tmp_path, files, {SHAPE_PIN: PIN_NAME}, legs)
    declare(plan, A_PIN)
    checked = check(plan)
    assert symlink_findings(checked) == [], checked.stderr
    _, _, walked = planned_root(adopter, tmp_path, plan)
    walks = {walk.path: walk for walk in walked.walks()}
    shape_pin = walks[SHAPE_PIN]
    assert (shape_pin.problem, shape_pin.landed, shape_pin.taken) == (
        None, PIN_FILE, True)
    copy = walks[f"{SHAPE_DIR}/{SHAPE_PIN}"]
    assert (copy.problem, copy.links, copy.taken) == (None, [], False)


@needs_disk_symlinks
def test_the_materializer_writes_the_shapes_pin_beside_that_link(tmp_path):
    """What the walk above predicts, on the disk: the pin's file is written
    first, and the shape's pin beside the link, which is left as it was."""
    target = tmp_path / ASSEMBLY
    symlink(target / SHAPE_PIN, PIN_NAME)
    result = materialize_assembly_root(
        REPO, target, template_values(), collision_dir=SHAPE_DIR,
        neutral_pins={GLASS: {}})
    assert PIN_FILE in result.written
    assert (SHAPE_PIN, f"{SHAPE_DIR}/{SHAPE_PIN}") in result.collisions
    assert os.readlink(target / SHAPE_PIN) == PIN_NAME


# ---------------------------------------------------------------------------
# A link AT a path the shape writes, leading out of the assembly (B1)
# ---------------------------------------------------------------------------
#
# `place` writes the shape's copy beside such a link when its destination is
# there, and keeps the link as the source had it: `CLAUDE.md` linked to a
# personal global file. Where nothing is there, the shape would write its
# file THROUGH the link, outside the assembly, as main does. Whether
# something is there is a fact of the machine running the command.

#: `(links, legs, files, (link, target, culprit, culprit's target, path))`,
#: each a link AT a shape path whose destination is an absolute path: `{o}`
#: is a directory outside the source, and the destination is
#: `{o}/<path>`. The culprit is the link whose target is absolute.
AT_OUTSIDE = [
    pytest.param({CLAUDE: f"{{o}}/{CLAUDE}"}, {CLAUDE: ROOT}, {},
                 (CLAUDE, f"{{o}}/{CLAUDE}", CLAUDE, f"{{o}}/{CLAUDE}",
                  CLAUDE), id="direct"),
    pytest.param({MAKEFILE: BUILD_MAKEFILE,
                  BUILD_MAKEFILE: f"{{o}}/{MAKEFILE}"},
                 {MAKEFILE: ROOT, BUILD_MAKEFILE: ROOT},
                 {"build/x.txt": "x\n"},
                 (MAKEFILE, BUILD_MAKEFILE, BUILD_MAKEFILE,
                  f"{{o}}/{MAKEFILE}", MAKEFILE), id="a-two-link-chain"),
]


#: The arguments every `AT_OUTSIDE` case takes.
AT_OUTSIDE_ARGS = (LINKS, "legs", FILES, "names")


def outside_plan(base: Path, links: dict, legs: dict,
                 files: dict) -> tuple[Path, Path]:
    """`(the directory outside, the plan)` for an `AT_OUTSIDE` case."""
    outside = base / OUTSIDE_DIR
    outside.mkdir()
    _, plan = planned(base, files, {link: target.format(o=outside.as_posix())
                                    for link, target in links.items()}, legs)
    return outside, plan


@pytest.mark.parametrize(AT_OUTSIDE_ARGS, AT_OUTSIDE)
def test_a_link_at_a_path_to_a_place_outside_that_is_there_is_kept(
        adopter, tmp_path, links, legs, files, names):
    """(b) Main writes the shape's copy beside it as `shape/<path>`, and
    keeps the link exactly as the source had it."""
    outside, plan = outside_plan(tmp_path, links, legs, files)
    (outside / names[-1]).write_text(PERSONAL, encoding=UTF8)
    passed_alike(adopter, tmp_path, plan)


@pytest.mark.parametrize(AT_OUTSIDE_ARGS, AT_OUTSIDE)
def test_a_link_at_a_path_to_a_place_outside_that_is_not_there_is_refused(
        adopter, no_filter_repo_probe, links_as_links, tmp_path, links, legs,
        files, names):
    """(a) Where nothing is there, main writes the shape's file THROUGH the
    link, onto this machine outside the assembly."""
    outside, plan = outside_plan(tmp_path, links, legs, files)
    link, target, culprit, place, path = (
        name.format(o=outside.as_posix()) for name in names)
    refused_alike(adopter, tmp_path, plan, finding(
        link, target, path, f"the symlink {ticked(culprit)} leads to "
        f"{ticked(place)}, {ON_THIS_MACHINE}, and nothing is there"))
    assert list(outside.iterdir()) == []


def test_execute_asks_its_own_disk_before_any_leg(adopter,
                                                  no_filter_repo_probe,
                                                  links_as_links, tmp_path):
    """`check` passed while the file was there; `execute` finds it gone and
    refuses before any leg, rather than trusting what `check` saw."""
    outside, plan = outside_plan(tmp_path, {CLAUDE: f"{{o}}/{CLAUDE}"},
                                 {CLAUDE: ROOT}, {})
    personal = outside / CLAUDE
    personal.write_text(PERSONAL, encoding=UTF8)
    assert check(plan).returncode == 0
    personal.unlink()
    refusal = refused_by(adopter, execute_args(tmp_path, plan))
    assert refusal.code == ROOT_SYMLINK
    assert "and nothing is there" in refusal.detail
    no_leg_was_created(tmp_path)


def test_a_link_at_a_path_that_climbs_into_the_work_directory(
        adopter, no_filter_repo_probe, links_as_links, tmp_path):
    """`execute` makes the assembly's clone in its work directory, so `..`
    above the root leads there: refused while nothing is there, kept, as on
    main, once something is. `check` asks the same directory when it is
    given the same `--work-dir`."""
    _, plan = planned(tmp_path, {}, {MAKEFILE: "../shared/Makefile"},
                      {MAKEFILE: ROOT})
    work = tmp_path / WORK
    place = f"{work.resolve().as_posix()}/shared/Makefile"
    refused_alike(adopter, tmp_path, plan, finding(
        MAKEFILE, "../shared/Makefile", MAKEFILE,
        f"{climbs(MAKEFILE)}, to {ticked(place)}, where nothing is"),
        WORK_FLAG, str(work))
    (work / "shared").mkdir()
    (work / "shared" / MAKEFILE).write_text("all:\n", encoding=UTF8)
    passed_alike(adopter, tmp_path, plan, WORK_FLAG, str(work))


def test_a_link_at_a_path_into_what_execute_makes_beside_the_assembly(
        adopter, no_filter_repo_probe, links_as_links, tmp_path):
    """The spec leg's clone is made in the work directory only after this
    check, so the disk cannot answer for it yet."""
    _, plan = planned(tmp_path, {}, {AGENTS: "../Northwind-spec/agents.md"},
                      {AGENTS: ROOT})
    work = tmp_path / WORK
    made = f"{work.resolve().as_posix()}/Northwind-spec"
    refused_alike(adopter, tmp_path, plan, finding(
        AGENTS, "../Northwind-spec/agents.md", AGENTS,
        f"{climbs(AGENTS)} into {ticked(made)}, where `execute` makes the "
        "spec leg's clone after this check"), WORK_FLAG, str(work))


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
    pytest.param({"vendor/keep.txt": "k\n"}, {SHAPE_DIR: VENDOR},
                 {VENDOR_DIR: ROOT, SHAPE_DIR: ROOT},
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
    # Where the shape has written the destination itself by the time it
    # writes the path: main writes CLAUDE.md's copy beside the link, and
    # the workflow into the `scripts/` the shape made.
    pytest.param({}, {CLAUDE: AGENTS}, {CLAUDE: ROOT},
                 id="a-link-to-what-the-shape-writes-first"),
    pytest.param({}, {GITHUB: SCRIPTS}, {GITHUB: ROOT},
                 id="a-directory-the-shape-makes-first"),
    # A link AT a path into a mounted leg that holds its destination, or
    # onto the mount itself: the copy goes beside, as on main.
    pytest.param({DOCS_AGENTS: "a\n"}, {AGENTS: "spec/docs/agents.md"},
                 {DOCS_DIR: SPEC, AGENTS: ROOT},
                 id="at-a-path-into-a-leg-that-holds-it"),
    pytest.param({}, {AGENTS: SPEC}, {AGENTS: ROOT},
                 id="at-a-path-onto-a-mount"),
    pytest.param({}, {CLAUDE: "code/CLAUDE.md"},
                 {CLAUDE: ROOT, "src/": "drop"},
                 id="at-a-path-into-a-seeded-leg"),
    pytest.param({DOCS_AGENTS: "a\n"}, {AGENTS: "../Northwind/docs/agents.md"},
                 {DOCS_DIR: ROOT, AGENTS: ROOT},
                 id="at-a-path-back-into-the-assembly-by-its-name"),
    pytest.param({CI_FILE: ON_PUSH}, {GITHUB_TWIN: "ci"},
                 {CI_DIR: ROOT, GITHUB_TWIN: ROOT},
                 id="a-case-twin-that-stays-inside"),
    # A link AT a path to what the clone's own `.git` holds by the time the
    # shape is written: `place` finds it there and writes the copy beside,
    # as on main (F3 and 2b of #183's re-verify).
    pytest.param({}, {CLAUDE: GIT_HEAD}, {CLAUDE: ROOT},
                 id="at-a-path-to-the-clones-own-head"),
    *(pytest.param({}, {CLAUDE: kept}, {CLAUDE: ROOT},
                   id="at-a-path-to-the-clones-own-"
                      + kept[5:].replace("/", "-"))
      for kept in GIT_KEPT),
    # #904: what git makes in those directories, named (L1-J1 of #457);
    # and J2's `..` back out of a directory git makes there, which was
    # refused as no directory in the assembly root, as main adopts it.
    *(pytest.param({}, {CLAUDE: named}, {CLAUDE: ROOT},
                   id="at-a-path-to-the-clones-own-"
                      + named[5:].replace("/", "-"))
      for named in GIT_NAMED),
    pytest.param({}, {CLAUDE: ".git/refs/../HEAD"}, {CLAUDE: ROOT},
                 id="J2-at-a-path-back-out-of-dot-git-refs"),
    pytest.param({}, {CLAUDE: ".git/../AGENTS.md"}, {CLAUDE: ROOT},
                 id="J2-at-a-path-back-out-of-dot-git"),
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
    passed_alike(adopter, tmp_path, plan)


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
    pushed. It is refused before them, and the probe leaves nothing.
    `check` passes the plan, as #183 left it: the walk follows `.github`
    into the `ci/` the root keeps, so no finding of `check`'s comes first,
    and the refusal is `execute`'s own, after that list (#531 changes what a
    finding says, not that order)."""
    _, plan = github_to_ci(tmp_path)
    links_as_files(monkeypatch)
    checked = check(plan)
    assert checked.returncode == 0, checked.stderr + checked.stdout
    refusal = refused_by(adopter, execute_args(tmp_path, plan))
    assert refusal.code == SYMLINKS_OFF_CODE
    work = (tmp_path / WORK).resolve()
    assert refusal.detail == (
        f"the plan keeps `.github` in the root, a symlink to `ci`, and "
        f"{ticked(WORKFLOW)}, a path the shape writes, runs through it, but "
        "`git` here checks a symlink out as a plain file: `core.symlinks` is "
        f"false for a repository made in {work}. The assembly's clone would "
        "hold `.github` as a file, and nothing can be written beneath a "
        "file.")
    assert "no leg repository was created" in refusal.remediation
    assert "send `.github` to a leg or `drop` it" in refusal.remediation
    no_leg_was_created(tmp_path)
    assert list(work.iterdir()) == []


def test_a_case_twin_checked_out_as_a_file_is_named_as_one(
        adopter, no_filter_repo_probe, tmp_path, monkeypatch):
    """On a disk that ignores case, `.github/workflows/` runs through the
    kept `.GitHub`, which this checkout would hold as a file. On a disk that
    keeps case it does not run through it at all, so the refusal says which
    disk it means, as `check`'s finding does (S1)."""
    _, plan = planned(tmp_path, {CI_FILE: ON_PUSH}, {GITHUB_TWIN: "ci"},
                      {CI_DIR: ROOT, GITHUB_TWIN: ROOT})
    links_as_files(monkeypatch)
    refusal = refused_by(adopter, execute_args(tmp_path, plan))
    assert refusal.code == SYMLINKS_OFF_CODE
    assert refusal.detail.startswith(
        f"the plan keeps `.GitHub` in the root, a symlink to `ci`, and "
        f"{ticked(WORKFLOW)}, a path the shape writes, runs through "
        f"it{CASE_ASIDE}, but `git` here checks a symlink out as a plain "
        "file: "), refusal.detail
    no_leg_was_created(tmp_path)


def test_the_probe_answers_what_git_would_do(adopter, tmp_path, monkeypatch):
    told_git(monkeypatch, "true")
    assert adopter._checks_out_symlinks(tmp_path) is True
    told_git(monkeypatch, "false")
    assert adopter._checks_out_symlinks(tmp_path) is False
    assert list(tmp_path.iterdir()) == []


def test_with_symlinks_on_the_same_plan_passes_the_probe(adopter, tmp_path,
                                                         monkeypatch):
    _, plan = github_to_ci(tmp_path)
    told_git(monkeypatch, "true")
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
    monkeypatch.setattr(adopter, PROBE, no_probe)
    monkeypatch.setattr(adopter, REF_PROBE, no_probe)
    links_as_files(monkeypatch)
    _, plan = planned(tmp_path, files, links, legs)
    loaded = adopter.Plan.load(plan)
    opened = loaded.open_source(None, tmp_path / READ)
    assert adopter._refuse_symlinks_checked_out_as_files(
        loaded, opened, tmp_path) is None
    # Nor does `check`'s list, which asks only of a link it cannot follow.
    assert adopter._refuse_what_check_finds(loaded, opened) is None


#: Links AT a path the shape writes that `check` cannot follow, which a
#: checkout without symlinks holds as plain files (B-OFF of #183's
#: re-verify): `CLAUDE.md` linked to a personal file on another machine,
#: one that dangles, and D3's. `place` finds each file there and writes the
#: shape's copy beside it, and main adopts and bootstraps each.
AT_A_FILE = [
    pytest.param({}, {CLAUDE: "/nonexistent-183/.claude/CLAUDE.md"},
                 {CLAUDE: ROOT}, id="absolute-and-nothing-there"),
    pytest.param({}, {CLAUDE: NOWHERE_MD}, {CLAUDE: ROOT},
                 id="dangling"),
    pytest.param({"config/readme.md": "c\n"}, {ATTRIBUTES: CONFIG_ATTRS},
                 {CONFIG_DIR: ROOT, ATTRIBUTES: ROOT},
                 id="D3-dangling-in-a-kept-directory"),
]


@pytest.mark.parametrize(PLANNED, [
    *AT_A_FILE,
    pytest.param({}, {GITIGNORE_TWIN: NOWHERE_GITIGNORE},
                 {GITIGNORE_TWIN: ROOT}, id="a-case-twin"),
])
def test_with_symlinks_off_a_link_at_a_path_is_a_file_passed_by_both(
        adopter, tmp_path, monkeypatch, files, links, legs):
    """Where `git` checks a symlink out as a plain file (Git for Windows'
    default), nothing about where a link AT a path the shape writes leads is
    refused: `check` and `execute` each ask their own work directory, and
    neither the list of `check`'s findings nor the probe for a link the
    shape writes beneath refuses it. A case twin is that file once case is
    ignored, and a second name where it is kept."""
    _, plan = planned(tmp_path, files, links, legs)
    links_as_files(monkeypatch)
    passed_alike(adopter, tmp_path, plan)
    loaded = adopter.Plan.load(plan)
    work = tmp_path / WORK
    opened = loaded.open_source(None, work)
    assert adopter._refuse_symlinks_checked_out_as_files(
        loaded, opened, work) is None
    assert list(work.iterdir()) == []


#: Why a link a path the shape writes runs BENEATH cannot be written
#: through where `git` checks a symlink out as a plain file (#531): `{}` is
#: the link. `adopt-symlinks-off`'s reason, as `check` says it.
HELD_AS_A_FILE = ("`git` here checks a symlink out as a plain file "
                  "(`core.symlinks` is false), so the assembly's clone would "
                  "hold {} as a file, wherever it points, and nothing can be "
                  "written beneath a file")


def as_a_file(link: str, target: str, shape_path: str,
              aside: str = "") -> str:
    """The line `check` prints, and `execute`'s refusal carries, for a link
    the shape writes beneath, where `git` checks it out as a plain file: no
    target it is given changes that there, so the fix is in the plan."""
    return finding(link, target, shape_path,
                   HELD_AS_A_FILE.format(ticked(link)), aside,
                   fix=f"Send {ticked(link)} to a leg or `drop` it in the "
                       "plan, and run `check` again.")


#: L1-J3's source: `scripts -> tools/deep`, whose scripts would run from
#: two directories down, where a disk holds symlinks.
TOOLS_DEEP = "tools/deep"
SCRIPTS_DEEP = ({"tools/deep/run.sh": ECHO}, {SCRIPTS: TOOLS_DEEP},
                {TOOLS_DIR: ROOT, SCRIPTS: ROOT})

#: `(*PLANNED, (link, target, shape path[, aside]))`: links `check` reports
#: where a disk holds symlinks, each ABOVE the first path the shape writes
#: through it. Each is L1-J3's question: the clone holds the link as a file.
ABOVE_AS_A_FILE = [
    pytest.param(*SCRIPTS_DEEP, (SCRIPTS, TOOLS_DEEP, VALIDATE_PINS),
                 id="L1-J3-scripts-two-directories-down"),
    pytest.param({}, {GITHUB: OUTSIDE_CI}, {GITHUB: ROOT},
                 (GITHUB, OUTSIDE_CI, WORKFLOW), id="D6-a-relative-link-out"),
    pytest.param(LINK_TO_GH, {GITHUB: TOOLING_GH},
                 {"tooling/": CODE, GITHUB: ROOT},
                 (GITHUB, TOOLING_GH, WORKFLOW),
                 id="D5-into-a-path-sent-to-a-leg"),
    pytest.param({}, {CONTRACTS: "/srv"}, {CONTRACTS: ROOT},
                 (CONTRACTS, "/srv", "contracts/spec-pin.yaml"),
                 id="one-finding-for-four-paths"),
    pytest.param({}, {SHAPE_DIR: "."}, {SHAPE_DIR: ROOT},
                 (SHAPE_DIR, ".", SHAPE_README),
                 id="the-collision-directory-is-the-root"),
    pytest.param({}, {GITHUB_TWIN: OUTSIDE_CI}, {GITHUB_TWIN: ROOT},
                 (GITHUB_TWIN, OUTSIDE_CI, WORKFLOW, CASE_ASIDE),
                 id="a-case-twin-above-a-shape-path"),
]


@pytest.mark.parametrize((*PLANNED, "expected"), ABOVE_AS_A_FILE)
def test_with_symlinks_off_a_link_above_a_path_is_named_as_a_file(
        adopter, no_filter_repo_probe, tmp_path, monkeypatch, files, links,
        legs, expected):
    """L1-J3 of #183's re-verify (#531). Where `git` checks a symlink out as
    a plain file, a link the shape writes BENEATH is that file in the
    assembly's clone, and nothing can be written beneath a file, wherever
    the link leads. `check`'s one finding for it said where it led, and
    sent the person to change that, which leads on to `execute`'s
    `adopt-symlinks-off` there. Now it says what `adopt-symlinks-off` says,
    with a fix that works on that disk, and `execute` refuses with the same
    line, word for word, before any leg."""
    _, plan = planned(tmp_path, files, links, legs)
    links_as_files(monkeypatch)
    refused_alike(adopter, tmp_path, plan, as_a_file(*expected))


@pytest.mark.parametrize("leg", [CODE, "drop"])
def test_with_symlinks_off_the_fix_the_finding_gives_works_there(
        adopter, tmp_path, monkeypatch, leg):
    """L1-J3's finding sent the person to change where `scripts` points,
    and on that disk no target helps. The fix it gives now works there:
    `scripts` answered as it says, `check` passes, and so do `execute`'s
    list of `check`'s findings and its own probe for a link the shape
    writes beneath."""
    links_as_files(monkeypatch)
    files, links, legs = SCRIPTS_DEEP
    _, kept = planned(tmp_path / ROOT, files, links, legs)
    said = symlink_findings(check(kept))
    assert said == [as_a_file(SCRIPTS, TOOLS_DEEP, VALIDATE_PINS)]
    answered = tmp_path / leg
    _, plan = planned(answered, files, links, {**legs, SCRIPTS: leg})
    passed_alike(adopter, answered, plan)
    loaded = adopter.Plan.load(plan)
    work = answered / WORK
    assert adopter._refuse_symlinks_checked_out_as_files(
        loaded, loaded.open_source(None, work), work) is None


def git_reads_symlinks_as(directory: Path) -> str:
    """What `git config --type=bool --get core.symlinks` says in a
    repository made in `directory`, as the probe asks it ("" for nothing)."""
    repo = directory / "asked"
    git("init", "-q", str(repo), cwd=directory)
    said = subprocess.run(
        ["git", "config", "--type=bool", "--get", CORE_SYMLINKS],
        cwd=str(repo), capture_output=True, text=True, check=False)
    shutil.rmtree(repo)
    return said.stdout.strip()


def test_each_command_asks_its_own_work_directory(adopter, tmp_path,
                                                  monkeypatch):
    """B-OFF asks the disk where the command makes its clone. A global
    configuration that turns `core.symlinks` off only for repositories made
    under one directory (`includeIf "gitdir:"`) is met by a work directory
    there and by no other, both by `check`'s list and by `execute`'s own
    refusal of a link the shape writes beneath."""
    base = tmp_path.resolve()
    off, on = base / "off", base / "on"
    off.mkdir()
    on.mkdir()
    included = base / "links-as-files.gitconfig"
    included.write_text("[core]\n\tsymlinks = false\n", encoding=UTF8)
    config = base / "global.gitconfig"
    config.write_text(f"[includeIf \"gitdir:{off.as_posix()}/\"]\n"
                      f"\tpath = {included.as_posix()}\n", encoding=UTF8)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    told = (git_reads_symlinks_as(off), git_reads_symlinks_as(on))
    if told != ("false", ""):
        pytest.skip(f"git here does not tell the two directories apart: "
                    f"{told}, from this runner's own configuration")
    _, at = planned(base / "at", {}, {CLAUDE: NOWHERE_MD}, {CLAUDE: ROOT})
    loaded = adopter.Plan.load(at)
    assert adopter._refuse_what_check_finds(
        loaded, loaded.open_source(None, off)) is None
    with pytest.raises(adopter.Refusal) as caught:
        adopter._refuse_what_check_finds(loaded, loaded.open_source(None, on))
    assert caught.value.code == ROOT_SYMLINK
    _, above = github_to_ci(base / "above")
    loaded = adopter.Plan.load(above)
    opened = loaded.open_source(None, base / READ)
    with pytest.raises(adopter.Refusal) as caught:
        adopter._refuse_symlinks_checked_out_as_files(loaded, opened, off)
    assert caught.value.code == SYMLINKS_OFF_CODE
    assert adopter._refuse_symlinks_checked_out_as_files(
        loaded, opened, on) is None


def test_with_no_work_directory_a_symlink_is_taken_as_one(adopter,
                                                          monkeypatch):
    """A `Source` that no command opened has no work directory to ask: no
    probe is made, and `git` is taken to check a symlink out as one."""
    monkeypatch.setattr(adopter, PROBE, no_probe)
    assert adopter._SymlinkProbe(None).symlinks() is True


def test_the_probe_is_made_once_however_many_walks_ask(adopter, tmp_path,
                                                       monkeypatch):
    """The answer is kept: two links AT paths the shape writes that a walk
    cannot follow, each met by the walk that keeps case and the one that
    folds it, make one probe."""
    asked = []

    def probe(work_root):
        asked.append(work_root)
        return False

    monkeypatch.setattr(adopter, PROBE, probe)
    _, plan = planned(tmp_path, {},
                      {CLAUDE: NOWHERE_MD, AGENTS: "nowhere-agents.md"},
                      {CLAUDE: ROOT, AGENTS: ROOT})
    loaded = adopter.Plan.load(plan)
    work = tmp_path / WORK
    work.mkdir()
    assert adopter._refuse_what_check_finds(
        loaded, loaded.open_source(None, work)) is None
    assert len(asked) == 1


def cannot_write_in(directory: Path) -> bool:
    try:
        (directory / "made").mkdir()
    except PermissionError:
        return True
    (directory / "made").rmdir()
    return False


@pytest.fixture
def unwritable_work(tmp_path):
    """A work directory this user cannot write in, or a skip where `chmod`
    cannot make one so (root, Windows)."""
    work = tmp_path / WORK
    work.mkdir()
    work.chmod(0o500)
    if not cannot_write_in(work):
        work.chmod(0o700)
        pytest.skip("chmod cannot keep this user from writing a directory")
    yield work
    work.chmod(0o700)


def test_a_work_directory_no_probe_can_be_made_in_reports_as_before(
        adopter, tmp_path, unwritable_work):
    """J4 of #183's re-verify: where this user cannot write the work
    directory, no repository can be made there to ask `git`, and a symlink
    is taken to be checked out as one, as before B-OFF asked. `check`
    prints its finding for a link AT a path that the walk cannot follow, and
    `execute`'s list of `check`'s findings refuses with it, where both ended
    in a PermissionError traceback."""
    _, plan = planned(tmp_path, {}, {CLAUDE: NOWHERE_MD}, {CLAUDE: ROOT})
    line = finding(CLAUDE, NOWHERE_MD, CLAUDE,
                   leads(CLAUDE, NOWHERE_MD, NOT_IN_THE_TREE))
    checked = check(plan, WORK_FLAG, str(unwritable_work))
    assert "Traceback" not in checked.stderr, checked.stderr
    assert checked.returncode == 1, checked.stderr + checked.stdout
    assert symlink_findings(checked) == [line]
    loaded = adopter.Plan.load(plan)
    with pytest.raises(adopter.Refusal) as caught:
        adopter._refuse_what_check_finds(
            loaded, loaded.open_source(None, unwritable_work))
    assert caught.value.code == ROOT_SYMLINK
    assert f"  {line}" in caught.value.detail.splitlines()


# ---------------------------------------------------------------------------
# What the clone's own `.git` holds, as this machine's git keeps refs (#904)
# ---------------------------------------------------------------------------
#
# Which names git makes in the clone's `.git` depends on how git here keeps
# refs: on its files backend, its default, or on the reftable backend (git
# 2.45 and later, where `GIT_DEFAULT_REF_FORMAT` or `init.defaultRefFormat`
# says so: L1-K8 of #457), and with reflogs or none (`core.logAllRefUpdates`).
# `check` and `execute` each ask a throwaway repository in their own work
# directory, once, and only where a walk is led into the clone's `.git`.

GIT_VERSION = re.search(r"(\d+)\.(\d+)", subprocess.run(
    ["git", "--version"], capture_output=True, text=True,
    check=False).stdout)
#: Whether this runner's git has the reftable backend.
REFTABLE_GIT = GIT_VERSION is not None and (
    int(GIT_VERSION[1]), int(GIT_VERSION[2])) >= (2, 45)
needs_reftable = pytest.mark.skipif(
    not REFTABLE_GIT, reason="the reftable backend needs git 2.45 or later")
REF_FORMAT = "GIT_DEFAULT_REF_FORMAT"
LOG_HEAD = ".git/logs/HEAD"
PACKED_REFS = ".git/packed-refs"
TABLES = ".git/reftable"


def refs_on_reftable(monkeypatch) -> None:
    """`git` told to make every repository on the reftable backend."""
    monkeypatch.setenv(REF_FORMAT, "reftable")


def no_reflogs(monkeypatch) -> None:
    """`git` told to write no reflog, after the runner's own
    `GIT_CONFIG_*`."""
    for name, entry in appended_to_command_scope(
            os.environ, [("core.logAllRefUpdates", "false")]).items():
        monkeypatch.setenv(name, entry)


def test_the_ref_probe_answers_what_git_would_do(adopter, tmp_path,
                                                 monkeypatch):
    """Git's defaults where nothing says otherwise, the files backend with
    reflogs; none where `core.logAllRefUpdates` is false; and nothing is
    left behind."""
    monkeypatch.delenv(REF_FORMAT, raising=False)
    assert adopter._clone_ref_store(tmp_path) == (False, True)
    no_reflogs(monkeypatch)
    assert adopter._clone_ref_store(tmp_path) == (False, False)
    assert list(tmp_path.iterdir()) == []


@needs_reftable
def test_the_ref_probe_answers_reftable_where_git_makes_it(adopter, tmp_path,
                                                           monkeypatch):
    refs_on_reftable(monkeypatch)
    assert adopter._clone_ref_store(tmp_path) == (True, True)


def test_with_no_work_directory_the_refs_are_gits_defaults(adopter,
                                                          monkeypatch):
    """A `Source` that no command opened has no work directory to ask: no
    probe is made, and git's defaults are taken."""
    monkeypatch.setattr(adopter, REF_PROBE, no_probe)
    assert adopter._SymlinkProbe(None).ref_store() == (False, True)


#: `(where CLAUDE.md leads, why it is refused, or None)` where the clone
#: keeps its refs on the reftable backend: measured with git 2.47.1, its
#: `.git` holds `reftable/tables.list` and the tables, and a `refs/heads`
#: that is a file, and no `packed-refs` and no `logs` (L1-K8 of #457).
ON_REFTABLE = [
    pytest.param(TABLES, None, id="the-tables"),
    pytest.param(f"{TABLES}/tables.list", None, id="their-list"),
    pytest.param(".git/refs/heads", None, id="refs-heads-a-file"),
    pytest.param(GIT_HEAD, None, id="head"),
    pytest.param(PACKED_REFS, WRITTEN_INTO_GIT, id="no-packed-refs"),
    pytest.param(LOG_HEAD, NO_DIRECTORY_IN_GIT, id="no-logs"),
    pytest.param(".git/refs/heads/main", NO_DIRECTORY_IN_GIT,
                 id="no-loose-branch"),
    pytest.param(f"{TABLES}/0x01.ref", unread(TABLES, REFTABLES),
                 id="a-table"),
]


def root_symlink_findings_here(adopter, base: Path, plan: Path) -> list:
    """`check`'s symlink findings, asked in this process, where a stand-in
    for a probe answers."""
    loaded = adopter.Plan.load(plan)
    (base / WORK).mkdir(exist_ok=True)
    source = loaded.open_source(None, base / WORK)
    return adopter._root_symlink_findings(loaded, source, source.tree())


@pytest.mark.parametrize(("target", "why"), ON_REFTABLE)
def test_on_the_reftable_backend_the_clones_git_is_what_git_makes_there(
        adopter, links_as_links, tmp_path, monkeypatch, target, why):
    """Asked of any git, the probe answered: a link to the tables was
    refused, though the copy goes beside them, and one to `packed-refs`
    checked ok and had the shape's file written there."""
    monkeypatch.setattr(adopter, REF_PROBE, lambda _work_root: (True, True))
    _, plan = planned(tmp_path, {}, {CLAUDE: target}, {CLAUDE: ROOT})
    assert root_symlink_findings_here(adopter, tmp_path, plan) == (
        [] if why is None
        else [finding(CLAUDE, target, CLAUDE, leads(CLAUDE, target, why))])


@needs_reftable
def test_where_git_keeps_refs_on_reftable_check_and_execute_ask_it(
        adopter, no_filter_repo_probe, links_as_links, tmp_path,
        monkeypatch):
    """The same of a real git that makes reftable repositories, as `check`
    and `execute` each ask it."""
    refs_on_reftable(monkeypatch)
    there = tmp_path / "there"
    _, plan = planned(there, {}, {CLAUDE: TABLES}, {CLAUDE: ROOT})
    passed_alike(adopter, there, plan)
    gone = tmp_path / "gone"
    _, plan = planned(gone, {}, {CLAUDE: PACKED_REFS}, {CLAUDE: ROOT})
    refused_alike(adopter, gone, plan, finding(
        CLAUDE, PACKED_REFS, CLAUDE,
        leads(CLAUDE, PACKED_REFS, WRITTEN_INTO_GIT)))


def test_where_git_writes_no_reflogs_a_link_to_one_is_refused(
        adopter, no_filter_repo_probe, links_as_links, tmp_path,
        monkeypatch):
    """`core.logAllRefUpdates` false: the clone has no `.git/logs`, so the
    shape would find no directory for `.git/logs/HEAD` and stop after both
    legs; `check` and `execute` refuse it before them."""
    _, plan = planned(tmp_path, {}, {CLAUDE: LOG_HEAD}, {CLAUDE: ROOT})
    no_reflogs(monkeypatch)
    refused_alike(adopter, tmp_path, plan, finding(
        CLAUDE, LOG_HEAD, CLAUDE, leads(CLAUDE, LOG_HEAD,
                                        NO_DIRECTORY_IN_GIT)))


@pytest.mark.parametrize("target", GUESSED_REFS)
def test_where_the_sources_head_is_on_no_branch_its_branch_is_not_named(
        adopter, no_filter_repo_probe, links_as_links, tmp_path, target):
    """`git clone` checks out the branch the source's HEAD is on. Where HEAD
    is on none, git guesses one, so a link to `refs/heads/main` cannot be
    told to find something, and is refused saying so; and so is one to the
    `origin/HEAD` it writes for that branch, or to the reflog of either,
    each saying what git writes there (rv1091's NIT 2 on #1091)."""
    top, holds = GUESSED_REFS[target]
    source, plan = planned(tmp_path, {}, {CLAUDE: target}, {CLAUDE: ROOT})
    git("checkout", "-q", "--detach", cwd=source)
    refused_alike(adopter, tmp_path, plan, finding(
        CLAUDE, target, CLAUDE, leads(CLAUDE, target, unread(top, holds))))


#: How `git init` fails where `GIT_DEFAULT_HASH` names no hash, as #910's
#: probe tests raise it, and how the NOTE that says so begins.
UNKNOWN_HASH = "fatal: unknown hash algorithm 'bogus'"
NO_REF_PROBE_NOTE = ("NOTE `check` could not ask git how it keeps the refs "
                     "of a repository made in ")


@pytest.mark.parametrize("failure", [
    pytest.param(lambda adopter: adopter.CommandFailed(
        ["git", "init", "-q", "probe"], None, 128, UNKNOWN_HASH),
        id="command-failed"),
    pytest.param(lambda adopter: adopter.Refusal(
        "git-failed", f"`git init` exited 128: {UNKNOWN_HASH}"),
        id="refusal")])
def test_a_ref_probe_git_will_not_make_takes_gits_defaults_and_says_so(
        adopter, monkeypatch, tmp_path, failure):
    """As #910 has the symlink probe do: a `git init` that fails otherwise
    than with an `OSError` stops nothing; git's defaults are taken, and a
    NOTE says why, in git's words."""
    def refused(_work_root):
        raise failure(adopter)

    monkeypatch.setattr(adopter, REF_PROBE, refused)
    probe = adopter._SymlinkProbe(tmp_path)
    assert probe.ref_store() == adopter.GIT_DEFAULT_REFS
    notes = probe.notes()
    assert len(notes) == 1, notes
    assert notes[0].startswith(NO_REF_PROBE_NOTE), notes[0]
    assert UNKNOWN_HASH in notes[0]


def test_a_ref_probe_in_a_work_directory_it_cannot_write_gives_no_note(
        adopter, monkeypatch, tmp_path):
    """An `OSError` is `adopt-work-dir-unwritable`'s to say (#524), and the
    probe adds no NOTE of its own."""
    def unwritable(_work_root):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(adopter, REF_PROBE, unwritable)
    probe = adopter._SymlinkProbe(tmp_path)
    assert probe.ref_store() == adopter.GIT_DEFAULT_REFS
    assert probe.notes() == []


def refusing_the_ref_probe(base: Path) -> dict:
    """The environment of a git that will not make the ref probe's
    repository: a stub first on PATH fails each `git init` of a
    `refs-probe-*` directory as `GIT_DEFAULT_HASH=bogus` fails it
    (`UNKNOWN_HASH`, exit 128), and hands any other command to the real
    git."""
    stubs = base / "ref-probe-stubs"
    stubs.mkdir()
    stub = stubs / "git"
    stub.write_bytes("\n".join([
        "#!/bin/sh",
        'for arg in "$@"; do',
        '  [ "$arg" = init ] || continue',
        '  for word in "$@"; do',
        '    case "$word" in */refs-probe-*) ;; *) continue ;; esac',
        f'    echo "{UNKNOWN_HASH}" >&2',
        "    exit 128",
        "  done",
        "done",
        'exec "$REAL_GIT" "$@"', ""]).encode("ascii"))
    stub.chmod(0o755)
    return {"PATH": str(stubs) + os.pathsep + os.environ["PATH"],
            "REAL_GIT": shutil.which("git")}


@WINDOWS_SKIP  # a `#!` stub named `git` first on PATH
def test_check_says_where_git_would_not_make_the_ref_probe(
        links_as_links, tmp_path, monkeypatch):
    """A git that will not make the ref probe's repository, and makes every
    other: `check` passes a link to `.git/HEAD`, as git's defaults hold it,
    and says why it took them, in git's words. The probe's `git init` is
    failed by a stub, as `GIT_DEFAULT_HASH=bogus` failed it here before
    #1083: that variable now stops the split's own `git clone` of the
    source too, which `check` makes first and names `adopt-git-unasked`,
    so it would no longer reach the probe (r1119b's MUST-2)."""
    _, plan = planned(tmp_path, {}, {CLAUDE: GIT_HEAD}, {CLAUDE: ROOT})
    for name, value in refusing_the_ref_probe(tmp_path).items():
        monkeypatch.setenv(name, value)
    checked = check(plan)
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert NO_REF_PROBE_NOTE in checked.stdout, checked.stdout
    assert UNKNOWN_HASH in checked.stdout, checked.stdout


def test_the_ref_probe_is_made_once_however_many_walks_ask(adopter, tmp_path,
                                                           monkeypatch):
    """Two links into the clone's `.git`, each met by both disks' walks and
    by the pins' walks, make one probe of how git keeps refs."""
    asked = []

    def probe(work_root):
        asked.append(work_root)
        return adopter.GIT_DEFAULT_REFS

    monkeypatch.setattr(adopter, REF_PROBE, probe)
    _, plan = planned(tmp_path, {},
                      {CLAUDE: GIT_HEAD, AGENTS: ".git/refs/heads/nope"},
                      {CLAUDE: ROOT, AGENTS: ROOT})
    loaded = adopter.Plan.load(plan)
    work = tmp_path / WORK
    work.mkdir()
    source = loaded.open_source(None, work)
    with pytest.raises(adopter.Refusal) as caught:
        adopter._refuse_what_check_finds(loaded, source)
    assert caught.value.code == ROOT_SYMLINK
    assert len(asked) == 1


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
    plain FILE holding `ci`. It used to be a NotADirectoryError traceback.

    A source that keeps a plain file named `.github` is #263's
    `plan-root-blocks-shape` in `check`, and `execute` refuses it before any
    leg exists, so only a caller that skipped `check` meets this refusal.
    The remediation does not send that caller to `check`; it names the work
    directory, which by then holds both legs' clones."""
    target = tmp_path / ASSEMBLY
    target.mkdir()
    (target / GITHUB).write_text("ci", encoding=UTF8)
    refusal = refused_materializing(target)
    assert refusal.code == BLOCKED
    assert refusal.detail == (f"{ticked(WORKFLOW)} cannot be written: "
                              f"{ticked(GITHUB)} is a file, not a directory")
    assert "nothing was written at that path" in refusal.remediation
    assert "check" not in refusal.remediation
    assert ("an empty `--work-dir`, or none: a `--work-dir` this run was "
            "given still holds its clones of both legs, and the next run "
            "cannot clone into them") in refusal.remediation


#: `(links, files, code, detail)` of a target holding `links` and `files`.
#: `{t}` is the target directory and `{o}` the directory beside it that a
#: link out of it reaches. Each path the refusal names is between backticks,
#: as the materializer writes one for a caller that passes no `spell`; `{t}`
#: is the directory the caller gave, named as it is.
UNWRITABLE = [
    pytest.param({GITHUB: "../outside"}, (), OUTSIDE,
                 f"{ticked(WORKFLOW)} would be written outside {{t}}: at the "
                 f"symlink {ticked(GITHUB)} it climbs above it",
                 id="a-relative-link-out"),
    pytest.param({GITHUB: "{o}"}, (), OUTSIDE,
                 f"{ticked(WORKFLOW)} would be written through the symlink "
                 f"{ticked(GITHUB)}, which leads to the absolute path `{{o}}`; "
                 "the shape follows only a symlink whose relative target "
                 "stays inside {t}", id="an-absolute-link"),
    pytest.param({SHAPE_DIR: "../outside"}, (README,), OUTSIDE,
                 f"{ticked(SHAPE_README)} would be written outside {{t}}: at "
                 f"the symlink {ticked(SHAPE_DIR)} it climbs above it",
                 id="the-collision-directory-out"),
    pytest.param({GITHUB: GITHUB}, (), SYMLINK_LOOP,
                 f"{ticked(WORKFLOW)} {too_many(GITHUB)} in {{t}}: {TOO_MANY}",
                 id="a-link-to-itself"),
    pytest.param({GITHUB: LOOP, LOOP: GITHUB}, (), SYMLINK_LOOP,
                 f"{ticked(WORKFLOW)} {too_many(GITHUB)} in {{t}}: {TOO_MANY}",
                 id="a-loop-of-two"),
    pytest.param(CHAIN, ("ci/keep.txt",), SYMLINK_LOOP,
                 f"{ticked(WORKFLOW)} {too_many('l40')} in {{t}}: {TOO_MANY}",
                 id="a-chain-of-41-links"),
    pytest.param({GITHUB: "nowhere"}, (), BLOCKED,
                 f"{ticked(WORKFLOW)} cannot be written: {ticked(GITHUB)} is "
                 "a symlink to `nowhere`, which is not a directory here",
                 id="a-dangling-directory-link"),
    pytest.param({GITHUB: README}, (README,), BLOCKED,
                 f"{ticked(WORKFLOW)} cannot be written: {ticked(GITHUB)} is "
                 f"a symlink to {ticked(README)}, which is not a directory "
                 "here", id="a-link-to-a-file"),
    pytest.param({ATTRIBUTES: NOWHERE_ATTRS}, (), BLOCKED,
                 f"{ticked(ATTRIBUTES)} cannot be written: the symlink "
                 f"{ticked(ATTRIBUTES)} leads to {ticked(NOWHERE_ATTRS)}, and "
                 "there is no directory there to write it in",
                 id="a-dangling-file-link"),
    # S2: `open()` takes `..`, `.` and a trailing `/` only from a directory.
    pytest.param({MAKEFILE: "ci/"}, (), BLOCKED,
                 f"{ticked(MAKEFILE)} cannot be written: the target of the "
                 f"symlink {ticked(MAKEFILE)} goes on from `ci`, which is not "
                 "a directory here", id="a-file-link-spelled-as-a-directory"),
    pytest.param({MAKEFILE: "a/.."}, (), BLOCKED,
                 f"{ticked(MAKEFILE)} cannot be written: the target of the "
                 f"symlink {ticked(MAKEFILE)} goes on from `a`, which is not "
                 "a directory here", id="dot-dot-after-nothing"),
    pytest.param({MAKEFILE: "README.md/.."}, (README,), BLOCKED,
                 f"{ticked(MAKEFILE)} cannot be written: the target of the "
                 f"symlink {ticked(MAKEFILE)} goes on from {ticked(README)}, "
                 "which is not a directory here", id="dot-dot-after-a-file"),
    # B2: the copy under `shape/` led onto something already there. Where a
    # copy lands is #262's `copy_in_the_way`, which `place` asks first.
    pytest.param({SHAPE_DIR: "."}, (README,), COPY_BLOCKED,
                 f"the shape's copy of {ticked(README)} cannot be written to "
                 f"{ticked(SHAPE_README)}: {ticked(SHAPE_README)} is already "
                 "there, and nothing was written there",
                 id="the-copy-onto-a-file"),
    pytest.param({SHAPE_DIR: ".", MAKEFILE: "docs"}, ("docs/x.md",),
                 COPY_BLOCKED,
                 f"the shape's copy of {ticked(MAKEFILE)} cannot be written to "
                 f"{ticked(SHAPE_DIR + '/' + MAKEFILE)}: "
                 f"{ticked(SHAPE_DIR + '/' + MAKEFILE)} is already there, a "
                 "directory, and nothing was written there",
                 id="the-copy-into-a-directory"),
]


@needs_disk_symlinks
@pytest.mark.parametrize((LINKS, FILES, CODE, "detail"), UNWRITABLE)
def test_the_materializer_refuses_before_it_writes(tmp_path, links, files,
                                                   code, detail):
    """A symlink in the way is a named refusal: never a write outside the
    target, never one over what is already there, never a traceback. Before
    this rule the two links out wrote `validate.yml` into `outside/`, and the
    rest raised OSError, FileExistsError, FileNotFoundError or
    NotADirectoryError; before #262 the copies wrote over README.md or raised
    IsADirectoryError, and #262's `copy_in_the_way` refuses them now."""
    target, outside = tmp_path / ASSEMBLY, tmp_path / OUTSIDE_DIR
    target.mkdir()
    outside.mkdir()
    for name in files:
        (target / name).parent.mkdir(parents=True, exist_ok=True)
        (target / name).write_text("the source's own\n", encoding=UTF8)
    for link, to in links.items():
        symlink(target / link, to.format(o=outside))
    refusal = refused_materializing(target)
    assert (refusal.code, refusal.detail) == (
        code, detail.format(t=target, o=outside))
    assert list(outside.iterdir()) == [], "written outside the target"
    for name in files:
        assert (target / name).read_text(encoding=UTF8) == "the source's own\n"


#: `(link, the path the refusal names)`: a symlink with an empty target
#: above a path the shape writes, and at one.
TO_NOTHING = [
    pytest.param(GITHUB, WORKFLOW, id="above-a-shape-path"),
    pytest.param(ATTRIBUTES, ATTRIBUTES, id="at-a-shape-path"),
]


@needs_disk_symlinks
@pytest.mark.parametrize(("link", "path"), TO_NOTHING)
def test_the_materializer_refuses_a_link_to_nothing(tmp_path, monkeypatch,
                                                    link, path):
    """Linux cannot make a symlink with an empty target, so the link is made
    to a placeholder and read back empty, as a disk that holds one answers.
    `open()` finds nothing through such a link. Read as `.`, it was taken
    for the directory it is in, and the refusal named the wrong thing."""
    target = tmp_path / ASSEMBLY
    target.mkdir()
    symlink(target / link, "placeholder")
    real = os.readlink
    monkeypatch.setattr(os, "readlink",
                        lambda here: "" if Path(here).name == link
                        else real(here))
    refusal = refused_materializing(target)
    assert (refusal.code, refusal.detail) == (
        BLOCKED, f"{ticked(path)} cannot be written: the symlink "
                 f"{ticked(link)} has an empty target, which leads nowhere")


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


@needs_disk_symlinks
def test_the_materializer_writes_beside_a_link_to_something_there(tmp_path):
    """A link AT a path whose destination is there is never written
    through: the copy goes beside it, and what it leads to is untouched."""
    target, outside = tmp_path / ASSEMBLY, tmp_path / OUTSIDE_DIR
    target.mkdir()
    outside.mkdir()
    (outside / CLAUDE).write_text(PERSONAL, encoding=UTF8)
    symlink(target / CLAUDE, str(outside / CLAUDE))
    result = materialize(target)
    assert (CLAUDE, f"{SHAPE_DIR}/{CLAUDE}") in result.collisions
    assert (outside / CLAUDE).read_text(encoding=UTF8) == PERSONAL


#: A symlink's target that no terminal shows as it is: a line break, which
#: would split a refusal's one line, and an ESC, which a terminal acts on.
UNPRINTABLE_TARGET = "no\nwhere\x1b"
#: How `_spelled` writes the refusal for a `.github` that leads there.
SPELLED_REFUSAL = (f"{ticked(WORKFLOW)} cannot be written: {ticked(GITHUB)} "
                   "is a symlink to `no\\nwhere\\x1b`, which is not a "
                   "directory here")


@needs_disk_symlinks
def test_a_refusal_spells_each_name_as_its_caller_asks(adopter, tmp_path):
    """`adopt-project.py` hands the materializer its `_spelled`, as #212
    spells every path a finding or a refusal names. A caller that passes no
    `spell`, the scaffold, gets each name between backticks, as above: the
    shape's own paths need nothing more."""
    target = tmp_path / ASSEMBLY
    target.mkdir()
    symlink(target / GITHUB, UNPRINTABLE_TARGET)
    with pytest.raises(Refusal) as caught:
        materialize_assembly_root(REPO, target, template_values(),
                                  collision_dir=SHAPE_DIR,
                                  spell=adopter._spelled)
    assert (caught.value.code, caught.value.detail) == (BLOCKED,
                                                        SPELLED_REFUSAL)


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
                      WORK_FLAG, str(base / WORK))


def split_modes(source: Path) -> dict:
    listing = git("ls-tree", "-r", BRANCH, cwd=source).stdout
    return {line.split("\t", 1)[1]: line.split(" ", 1)[0]
            for line in listing.splitlines()}


def bootstraps(source: Path, base: Path) -> None:
    """A recursive clone of the split, and its bootstrap, exit 0."""
    clone = cloned_just_pushed(source, base / PROJECT, BRANCH)
    booted = run_script(clone / SCRIPTS / "bootstrap.py", cwd=clone)
    assert booted.returncode == 0, booted.stderr + booted.stdout


@pytest.fixture(scope=MODULE)
def scripts_through_a_link(tmp_path_factory) -> SimpleNamespace:
    """One real adoption of a source that keeps `scripts -> tools`."""
    if ON_WINDOWS or NO_FILTER_REPO:
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
    assert VERIFIED in result.stdout
    modes = split_modes(scripts_through_a_link.source)
    assert modes[SCRIPTS] == SYMLINK
    assert {"tools/bootstrap.py", "tools/repo_shape.py", RUN_SH} <= set(modes)
    assert VALIDATE_PINS not in modes


@needs_filter_repo
@needs_disk_symlinks
def test_that_assembly_bootstraps(scripts_through_a_link, tmp_path):
    assert scripts_through_a_link.result.returncode == 0
    bootstraps(scripts_through_a_link.source, tmp_path)


@pytest.fixture(scope=MODULE)
def claude_md_outside(tmp_path_factory) -> SimpleNamespace:
    """One real adoption of a source that keeps `CLAUDE.md` linked to a
    personal file outside it, which this machine has (B1)."""
    if ON_WINDOWS or NO_FILTER_REPO:
        pytest.skip("needs git filter-repo and a disk that holds symlinks")
    base = tmp_path_factory.mktemp("claude-outside")
    personal = base / OUTSIDE_DIR / CLAUDE
    personal.parent.mkdir()
    personal.write_text("a personal global CLAUDE.md\n", encoding=UTF8)
    source, plan = disk_source(base, {}, {CLAUDE: str(personal)},
                               {CLAUDE: ROOT})
    return SimpleNamespace(base=base, source=source, personal=personal,
                           result=execute(base, plan))


@needs_filter_repo
@needs_disk_symlinks
def test_a_link_at_a_path_to_a_file_outside_adopts_beside_it(
        claude_md_outside):
    """As on main: the copy goes beside the link as `shape/CLAUDE.md`, the
    split keeps the link exactly as the source had it, and the file it
    leads to is untouched."""
    result = claude_md_outside.result
    assert result.returncode == 0, result.stderr + result.stdout
    assert VERIFIED in result.stdout
    assert (f"  beside  {SHAPE_DIR}/{CLAUDE} (the source already has "
            f"{CLAUDE}; nothing was overwritten)") in result.stdout
    source = claude_md_outside.source
    modes = split_modes(source)
    assert modes[CLAUDE] == SYMLINK
    assert modes[f"{SHAPE_DIR}/{CLAUDE}"] == "100644"
    assert git("show", f"{BRANCH}:{CLAUDE}",
               cwd=source).stdout == str(claude_md_outside.personal)
    assert claude_md_outside.personal.read_text(encoding=UTF8) == (
        "a personal global CLAUDE.md\n")


@needs_filter_repo
@needs_disk_symlinks
def test_that_assembly_bootstraps_too(claude_md_outside, tmp_path):
    assert claude_md_outside.result.returncode == 0
    bootstraps(claude_md_outside.source, tmp_path)


@needs_filter_repo
@needs_disk_symlinks
def test_a_link_at_a_path_into_the_clones_own_git_adopts_beside_it(tmp_path):
    """`CLAUDE.md -> .git/HEAD`: every clone has that file, so `place`
    writes the shape's copy beside the link and keeps it, and the adoption
    verifies, as on main (F3 of #183's re-verify)."""
    source, plan = disk_source(tmp_path, {}, {CLAUDE: GIT_HEAD},
                               {CLAUDE: ROOT})
    result = execute(tmp_path, plan)
    assert result.returncode == 0, result.stderr + result.stdout
    assert VERIFIED in result.stdout
    assert (f"  beside  {SHAPE_DIR}/{CLAUDE} (the source already has "
            f"{CLAUDE}; nothing was overwritten)") in result.stdout
    assert split_modes(source)[CLAUDE] == SYMLINK
    assert git("show", f"{BRANCH}:{CLAUDE}", cwd=source).stdout == GIT_HEAD


def adopted_beside(result, source: Path, links: dict) -> None:
    """`execute` verified the adoption, each link is kept as the source had
    it, and the shape's copy of each is beside it under `shape/`."""
    assert result.returncode == 0, result.stderr + result.stdout
    assert VERIFIED in result.stdout
    modes = split_modes(source)
    for link, target in links.items():
        assert (f"  beside  {SHAPE_DIR}/{link} (the source already has "
                f"{link}; nothing was overwritten)") in result.stdout
        assert modes[link] == SYMLINK
        assert modes[f"{SHAPE_DIR}/{link}"] == "100644"
        assert git("show", f"{BRANCH}:{link}", cwd=source).stdout == target


#: Two links, each AT a path the shape writes, into what the assembly's
#: clone holds in its own `.git` by then (2b of #183's re-verify).
INTO_THE_CLONES_GIT = [
    pytest.param({CLAUDE: ".git/index", AGENTS: ".git/packed-refs"},
                 id="the-index-and-the-packed-refs"),
    pytest.param({CLAUDE: ".git/logs/HEAD", AGENTS: ".git/objects/pack"},
                 id="a-log-and-the-packs"),
    pytest.param({CLAUDE: ".git/refs/heads", AGENTS: ".git/modules/spec"},
                 id="the-branches-and-a-legs-store"),
    # #904: J2's step back out of `.git/refs`, and names in the directories
    # that were counted whole (L1-J1 of #457).
    pytest.param({CLAUDE: ".git/refs/../HEAD",
                  AGENTS: ".git/refs/remotes/origin/HEAD"},
                 id="J2-back-out-of-refs-and-origins-head"),
    pytest.param({CLAUDE: ".git/refs/heads/main",
                  AGENTS: f".git/logs/refs/heads/{BRANCH}"},
                 id="the-cloned-branch-and-the-split-branchs-log"),
]


@needs_filter_repo
@needs_disk_symlinks
@pytest.mark.parametrize(LINKS, INTO_THE_CLONES_GIT)
def test_links_into_what_the_clones_own_git_holds_adopt_beside_them(
        tmp_path, links):
    """Git makes each in the clone, or `execute` does before the shape is
    written, so `place` finds it there and writes the copy beside the link,
    as on main. Before 2b only five such names counted, and these were
    refused."""
    source, plan = planned(tmp_path, {}, links, {link: ROOT for link in links})
    adopted_beside(execute(tmp_path, plan), source, links)


@needs_filter_repo
@needs_disk_symlinks
@needs_reftable
def test_on_reftable_links_to_what_its_git_holds_adopt_beside_them(
        tmp_path, monkeypatch):
    """L1-K8 of #457 end to end: where git keeps refs on the reftable
    backend, the clone's `.git` holds `reftable` and a `refs/heads` file,
    so `place` writes the copies beside the links, and the adoption
    verifies."""
    refs_on_reftable(monkeypatch)
    links = {CLAUDE: TABLES, AGENTS: ".git/refs/heads"}
    source, plan = planned(tmp_path, {}, links, {link: ROOT for link in links})
    adopted_beside(execute(tmp_path, plan), source, links)


@needs_filter_repo
@pytest.mark.parametrize(PLANNED, AT_A_FILE)
def test_with_symlinks_off_execute_adopts_beside_the_file(
        tmp_path, monkeypatch, files, links, legs):
    """B-OFF of #183's re-verify, end to end: where `git` checks a symlink
    out as a plain file, the assembly's clone holds the link AT the shape
    path as one, `place` writes the copy beside it, and the split keeps the
    link as the source had it, as main does. Before, `check` refused it, and
    so did `execute`, before any leg."""
    source, plan = planned(tmp_path, files, links, legs)
    links_as_files(monkeypatch)
    adopted_beside(execute(tmp_path, plan), source, links)


@needs_filter_repo
@needs_disk_symlinks
def test_an_unrelated_absolute_link_in_the_root_still_adopts(tmp_path):
    """Rule 2 of the brief: no shape path runs through it, so main's
    behaviour is kept: the split carries the link exactly as it was."""
    source, plan = disk_source(tmp_path, {NOTES_README: "n\n"},
                               {NOTES_UPSTREAM: ETC}, NOTES_KEPT)
    result = execute(tmp_path, plan)
    assert result.returncode == 0, result.stderr + result.stdout
    assert VERIFIED in result.stdout
    assert split_modes(source)[NOTES_UPSTREAM] == SYMLINK
    assert git("show", f"{BRANCH}:notes/upstream",
               cwd=source).stdout == ETC


def refused_past_check(adopter, base: Path, target: str, monkeypatch,
                       capsys) -> str:
    """What `execute` prints to stderr, exiting 2, for a source that keeps
    `.github -> target` in the root, with #168's refusal of `check`'s
    findings taken away so that the link reaches the materializer."""
    source = make_source_repo(base / THING, tree=BASIC)
    symlink(source / GITHUB, target)
    git("add", "-A", "--", ".", cwd=source)
    commit_index(source, "Keep .github as a link")
    plan = base / PLAN_FILE
    assert write_plan(source, plan, project=PROJECT).returncode == 0
    set_leg(plan, GITHUB, ROOT)
    monkeypatch.setenv("LANES_LANE", "")
    clear_ambient_pin_sources(monkeypatch)
    monkeypatch.setattr(adopter, "_refuse_what_check_finds",
                        lambda *_: None)
    code = adopter.main(["execute", PLAN_FLAG, str(plan), "--yes",
                         "--local-remote-dir", str(base / REMOTES),
                         WORK_FLAG, str(base / WORK)])
    seen = capsys.readouterr()
    assert code == 2, seen.err + seen.out
    return seen.err


@needs_filter_repo
@needs_disk_symlinks
def test_a_caller_that_skips_check_meets_the_materializer_refusal(
        adopter, tmp_path, monkeypatch, capsys):
    """Defence in depth: with #168's refusal taken away, the link out (D6)
    reaches the materializer, which refuses it by name -- no traceback, and
    nothing written into the directory beside the work directory. Both legs
    are pushed by then, so `execute` reports it as #188 reports every
    failure after them: at the step, with the notice of what the run left."""
    outside = tmp_path / WORK / "outside-ci"
    outside.mkdir(parents=True)
    said = refused_past_check(adopter, tmp_path, OUTSIDE_CI, monkeypatch,
                              capsys)
    assert f"{SPLIT_STEP} {OUTSIDE}: " in said
    notice = said.split(LEFT_BEHIND, 1)[1]
    assert BOTH_PUSHED in notice.split("\n", 1)[0]
    assert "Traceback" not in said
    assert list(outside.iterdir()) == []


@needs_filter_repo
@needs_disk_symlinks
def test_execute_hands_the_materializer_its_spelling(adopter, tmp_path,
                                                     monkeypatch, capsys):
    """The refusal `execute` prints for a link no shape file can be written
    through names its target as `check` would: on one line, the line break
    and the ESC spelled (#212), after the step #188 names. Printed raw, the
    line break split the refusal in two."""
    said = refused_past_check(adopter, tmp_path, UNPRINTABLE_TARGET,
                              monkeypatch, capsys)
    assert f"{SPLIT_STEP} {BLOCKED}: {SPELLED_REFUSAL}" in said.splitlines()
    assert LEFT_BEHIND in said
