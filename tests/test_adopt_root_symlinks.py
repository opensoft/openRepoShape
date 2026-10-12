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
#: The materializer's refusal of a path that follows too many symlinks.
SYMLINK_LOOP = "materialize-symlink-loop"
CONFIG_VALUE = "GIT_CONFIG_VALUE_0"
#: Case twins of paths the shape writes, as a macOS or Windows disk reads
#: them (S1), and the rest of what several cases name.
GITHUB_TWIN = ".GitHub"
GITIGNORE_TWIN = ".GITIGNORE"
NOWHERE_GITIGNORE = "nowhere/gitignore"
BUILD_MAKEFILE = "build/Makefile"
GIT_INFO = ".git/info"
GIT_HEAD = ".git/HEAD"
GIT_DESCRIPTION = ".git/description"
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
#: `GIT_CONFIG_*` outranks every configuration file.
SYMLINKS_OFF = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.symlinks",
                CONFIG_VALUE: "false"}
SYMLINKS_ON = {**SYMLINKS_OFF, CONFIG_VALUE: "true"}

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
            aside: str = "") -> str:
    """The line `check` prints, and `execute`'s refusal carries."""
    return (f"{FINDING}the plan keeps {ticked(link)} in the root, a symlink "
            f"to {ticked(target)}, and {ticked(shape_path)}, a path the shape "
            f"writes, runs through it{aside}, but {why}. Send {ticked(link)} "
            "to a leg or `drop` it, or change where it points in the source "
            "and re-run `plan`.")


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
                  leads(GITHUB, GIT_INFO, NOT_IN_THE_TREE)),
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
                  leads(CLAUDE, GIT_DESCRIPTION, NOT_IN_THE_TREE)),
                 id="at-a-path-to-what-only-a-template-puts-in-dot-git"),
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
        adopter, no_filter_repo_probe, tmp_path, files, links, legs,
        expected):
    """One finding naming the link, its target and the shape path that runs
    through it; `execute` refuses with the same line, word for word, and
    makes no leg, so the corrected plan does not meet `leg-remote-exists`."""
    _, plan = planned(tmp_path, files, links, legs)
    refused_alike(adopter, tmp_path, plan, finding(*expected))


def test_a_link_into_a_submodule_kept_in_the_root_is_reported(tmp_path):
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
        tmp_path):
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
    #262's: `plan-root-blocks-shape-copy` names it, the shape's copy written
    THROUGH it, and this rule does not say the same link again. `execute`
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
    assert "`execute` would write the copy through it " in said[0]
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


#: An empty target, and two that are not plain text: a byte that is not
#: UTF-8, and a newline that would end the one-line FINDING.
SPELLED = [
    pytest.param(b"nowhere\xff", "nowhere\\xff", id="not-utf-8"),
    pytest.param(b"a\nb", "a\\nb", id="a-newline"),
]


@pytest.mark.parametrize(("raw", "spelled"), SPELLED)
def test_a_target_that_is_not_plain_text_is_spelled(tmp_path, raw, spelled):
    """As #166's findings spell a path: between backticks, a byte that is
    not UTF-8 as `\\xff` and a newline as `\\n`, so the finding is one line
    that reads one way."""
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
        adopter, no_filter_repo_probe, tmp_path, link, target, path):
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


def test_a_link_with_an_empty_target_is_fixed_in_the_source(
        adopter, no_filter_repo_probe, tmp_path):
    """Linux cannot hold a symlink to nothing: `git clone` there stops with
    `unable to create symlink`, so on main `execute` made both legs and then
    exited 2 with nothing said. Every clone `execute` makes of the source
    checks the link out, wherever the plan sends it, so the finding says to
    fix it in the source. (Where `core.symlinks` is false the clone holds a
    plain file instead, so the finding claims no more than that.)"""
    _, plan = planned(tmp_path, {}, {GITHUB: ""}, {GITHUB: ROOT})
    line = (f"{FINDING}the plan keeps `.github` in the root, a symlink to "
            f"``, and {ticked(WORKFLOW)}, a path the shape writes, runs "
            "through it, but the symlink `.github` has an empty target, "
            "which leads nowhere. Give `.github` a target in the source, or "
            "remove it there, and re-run `plan`: Linux cannot hold a symlink "
            "to nothing, and every clone `execute` makes of the source checks "
            "it out, wherever the plan sends it.")
    refused_alike(adopter, tmp_path, plan, line)


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
        adopter, no_filter_repo_probe, tmp_path, links, legs, files, names):
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
                                                  tmp_path):
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
        adopter, no_filter_repo_probe, tmp_path):
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
        adopter, no_filter_repo_probe, tmp_path):
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
    # A link AT a path to what git makes in every clone's own `.git`:
    # `place` finds it there and writes the copy beside, as on main (F3 of
    # #183's re-verify).
    pytest.param({}, {CLAUDE: GIT_HEAD}, {CLAUDE: ROOT},
                 id="at-a-path-to-the-clones-own-head"),
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
    pushed. It is refused before them, and the probe leaves nothing."""
    _, plan = github_to_ci(tmp_path)
    for key, value in SYMLINKS_OFF.items():
        monkeypatch.setenv(key, value)
    refusal = refused_by(adopter, execute_args(tmp_path, plan))
    assert refusal.code == "adopt-symlinks-off"
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
    for key, value in SYMLINKS_OFF.items():
        monkeypatch.setenv(key, value)
    refusal = refused_by(adopter, execute_args(tmp_path, plan))
    assert refusal.code == "adopt-symlinks-off"
    assert refusal.detail.startswith(
        f"the plan keeps `.GitHub` in the root, a symlink to `ci`, and "
        f"{ticked(WORKFLOW)}, a path the shape writes, runs through "
        f"it{CASE_ASIDE}, but `git` here checks a symlink out as a plain "
        "file: "), refusal.detail
    no_leg_was_created(tmp_path)


def test_the_probe_answers_what_git_would_do(adopter, tmp_path, monkeypatch):
    for key, value in SYMLINKS_ON.items():
        monkeypatch.setenv(key, value)
    assert adopter._checks_out_symlinks(tmp_path) is True
    monkeypatch.setenv(CONFIG_VALUE, "false")
    assert adopter._checks_out_symlinks(tmp_path) is False
    assert list(tmp_path.iterdir()) == []


def test_with_symlinks_on_the_same_plan_passes_the_probe(adopter, tmp_path,
                                                         monkeypatch):
    _, plan = github_to_ci(tmp_path)
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
    clone = base / PROJECT
    git(*FILE_PROTOCOL, "clone", "-q", "--recurse-submodules", "-b", BRANCH,
        str(source), str(clone), cwd=base)
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
                        lambda plan, source: None)
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
    nothing written into the directory beside the work directory."""
    outside = tmp_path / WORK / "outside-ci"
    outside.mkdir(parents=True)
    said = refused_past_check(adopter, tmp_path, OUTSIDE_CI, monkeypatch,
                              capsys)
    assert "REFUSED materialize-outside: " in said
    assert "Traceback" not in said
    assert list(outside.iterdir()) == []


@needs_filter_repo
@needs_disk_symlinks
def test_execute_hands_the_materializer_its_spelling(adopter, tmp_path,
                                                     monkeypatch, capsys):
    """The refusal `execute` prints for a link no shape file can be written
    through names its target as `check` would: on one line, the line break
    and the ESC spelled (#212). Printed raw, the line break split the
    refusal in two."""
    said = refused_past_check(adopter, tmp_path, UNPRINTABLE_TARGET,
                              monkeypatch, capsys)
    assert f"REFUSED {BLOCKED}: {SPELLED_REFUSAL}" in said.splitlines()
