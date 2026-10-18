# SPDX-License-Identifier: Apache-2.0
"""`plan` asks what its flags alone decide before it makes a work directory,
reads the source with git or runs `gh repo clone` (#903: L2-55, L4-37 and
L1-67 of #457).

ON MAIN AT 50178305 (v1.1.1), probed with a stub `gh` that logs its arguments
and exits 97, `GH_TOKEN=bogus`, an empty `GH_CONFIG_DIR` and `GIT_TRACE`:
- L2-55. `adopt-bad-leg-path`, `adopt-leg-path-collides`,
  `adopt-pin-collides`, `pin-malformed`, `election-date-malformed` and
  `adopt-unwritable-value` were asked in `_checked_plan_inputs`, after
  `_work_root` and `Source.open`. For a local source `plan` had made its
  work directory and run eight `git` commands in the source by then; for an
  `org/repo` one it had run `gh repo clone` once, so with a clone that
  failed each of them was `source-unclonable`, with a remedy about `gh auth
  status`, and the refusal the person had earned was never said.
- L4-37. `plan --source testorg/Thing --project Other --org testorg` named
  `testorg/Other` for the source `testorg/Thing`, a name known before the
  clone, and `adopt-not-the-source` came only after it.
- L1-67. `plan --source testorg/Thing --work-dir <a folder nobody can write
  in>` refused the folder with `execute`'s reason ("`execute` builds the
  spec leg, the code leg and the split there, only after it has made both
  leg repositories"), though what `plan` needs the folder for is the clone.
  A local source is read in place and written nowhere, and the folder was
  probed for it all the same: a directory made in it, and removed, for an
  answer nothing read.

Now every refusal the flags alone decide is asked first, as `--pin-source`
and `--out` are: no work directory, no `git` and no `gh` before it. An
`org/repo` source is held to `--org` and `--project` before the clone, and
its unwritable folder is refused in words about the clone. A local source's
folder is still made, since `--out` may lie in it
(`tests/test_adopt_plan_out_checked.py`), and still refused where it cannot
be made (`tests/test_adopt_work_dir_refusal.py`); it is no longer probed.

The runs here are given a fresh `TMPDIR`, a `GIT_TRACE` file that any `git`
process would write, a `--work-dir` that is not there, and a `gh` that logs
every call, as `tests/test_adopt_pins.py` holds `--pin-source`. An `org/repo`
source is the proof that nothing was cloned; a local one, that no `git` ran
at all. The tests that pass on main as well are the controls, said so.
"""

from __future__ import annotations

import errno
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

import pytest

from conftest import ADOPT, REPO, git, make_source_repo, run_script
from test_adopt_root_symlinks import ticked, unwritable_work  # noqa: F401
from test_adopt_shape_pin_and_work_dir import FIX, WORK_DIR_UNWRITABLE

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml  # noqa: E402

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="the `gh` stub is a `#!/bin/sh` script, which Windows runs not")

UTF8 = "utf-8"
PROJECT = "Thing"
ORG = "testorg"
REPOSITORY = f"{ORG}/{PROJECT}"
PLAN_FILE = "plan.yaml"
ZERO = "0" * 40
#: A source small enough that `plan` asks no question.
SMALL_TREE = {"README.md": "# Thing\n", "src/app/util.py": "VALUE = 1\n",
              "specs/001-feature/tasks.md": "- [ ] one\n"}
#: `plan`'s arguments after `--source <it>`.
PLANNED = ("--project", PROJECT, "--org", ORG, "--elected-by", "Test Human",
           "--elected-on", "2026-09-02")
#: What `plan` says when it is not the source, after the two names.
WHY = ("an in-place adoption keeps the source's own name, and `execute` "
       "pushes the split to the repository they name, opens its pull request "
       "there and sets its topic on it")
OWN_NAME = ("Remediation: no plan was written. Run `plan` again with "
            "`--project {name} --org {org}`, the source's own name, which "
            "`plan` writes into the plan's `org:`, `project:` and `legs:`. "
            "Any other name is another repository; if {repository} is not "
            "the one to adopt, plan from a clone of the one that is, or with "
            "`--source <org>/<repo>`.\n")


def stub_gh(directory: Path) -> dict:
    """A `gh` that records its arguments in `gh.log` beside it and exits
    97, and the environment that puts it first on PATH."""
    bin_dir = directory / "fakebin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text('#!/bin/sh\necho "$*" >> "$GH_STUB_LOG"\nexit 97\n',
                  encoding=UTF8)
    gh.chmod(0o755)
    return {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "GH_STUB_LOG": str(directory / "gh.log")}


class Harness:
    """What a run here is given and what it leaves: a stub `gh`, a fresh
    `TMPDIR`, a `GIT_TRACE` file and a `--work-dir` that is not there."""

    def __init__(self, base: Path) -> None:
        self.env = stub_gh(base)
        self.temp = base / "tmp"
        self.temp.mkdir()
        self.trace = base / "git-trace.log"
        self.work = base / "work"
        self.out = base / PLAN_FILE
        self.env.update(TMPDIR=str(self.temp), GIT_TRACE=str(self.trace))

    def plan(self, source: str, *flags: str, work: bool = False,
             planned: tuple = PLANNED):
        """`plan --source source`, with `planned`, then `flags`: a flag
        given twice is read as its last value."""
        return run_script(
            ADOPT, "plan", "--source", source, *planned, *flags, "--out",
            str(self.out), *(("--work-dir", str(self.work)) if work else ()),
            env=self.env)

    def gh_calls(self) -> list[str]:
        log = Path(self.env["GH_STUB_LOG"])
        return log.read_text(encoding=UTF8).splitlines() if log.exists() \
            else []

    def git_commands(self) -> list[str]:
        """What each `git` the run started was asked, from `GIT_TRACE`."""
        if not self.trace.exists():
            return []
        said = self.trace.read_text(encoding=UTF8, errors="replace")
        return [line.split("trace: built-in: git ", 1)[1]
                for line in said.splitlines()
                if "trace: built-in: git " in line]


@pytest.fixture
def harness(tmp_path) -> Harness:
    return Harness(tmp_path)


@pytest.fixture
def source(tmp_path) -> Path:
    return make_source_repo(tmp_path / "Thing", tree=SMALL_TREE, edits=())


#: The sources `plan` is run against: an `org/repo` one, where `gh repo
#: clone` is the first thing that can run, and a local one, where `git`
#: reads the source; each with the default work directory and with one
#: that is not there.
SOURCES = [
    pytest.param(True, False, id="org-repo"),
    pytest.param(True, True, id="org-repo-work-dir"),
    pytest.param(False, False, id="local"),
    pytest.param(False, True, id="local-work-dir"),
]


def the_source(cloned: bool, local: Path) -> str:
    return REPOSITORY if cloned else str(local)


def refused_first(harness: Harness, result, code: str, said: str,
                  work: bool) -> None:
    """`result` is `plan`'s refusal as `code` and nothing before it ran: no
    `gh`, no `git` at all, no work directory and nothing in `TMPDIR`; and
    no plan."""
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(f"REFUSED {code}: "), result.stderr
    assert said in result.stderr, result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert result.stdout == ""
    assert harness.gh_calls() == [], "gh was called"
    assert not harness.trace.exists(), "a git process ran"
    if work:
        assert not harness.work.exists(), "a work directory was made"
    assert list(harness.temp.iterdir()) == []
    assert not harness.out.exists()


# ---------------------------------------------------------------------------
# L2-55 and L4-37: what the flags alone decide is asked first
# ---------------------------------------------------------------------------

#: `(flags, the refusal's code, text it holds)` for each refusal of
#: `_checked_plan_inputs` that needs the flags alone, in the order it asks.
FLAG_REFUSALS = [
    pytest.param(("--project", "Th ing"), "unsafe-value", "--project",
                 id="project"),
    pytest.param(("--spec-path", "spec/"), "adopt-bad-leg-path",
                 "--spec-path", id="bad-leg-path"),
    pytest.param(("--code-path", "./code"), "adopt-bad-leg-path",
                 "--code-path", id="bad-code-path"),
    pytest.param(("--pin", f"spec@{ZERO}"), "adopt-pin-collides", "--pin",
                 id="pin-collides"),
    pytest.param(("--pin", "openGlass"), "pin-malformed", "openGlass",
                 id="pin-malformed"),
    pytest.param(("--spec-path", "project.yaml"), "adopt-leg-path-collides",
                 "project.yaml", id="leg-path-collides"),
    pytest.param(("--id", "North_Wind"), "adopt-bad-id", "--id",
                 id="id"),
    pytest.param(("--org=-evil",), "unsafe-value", "--org", id="org"),
    pytest.param(("--elected-on", "2026-9-2"), "election-date-malformed",
                 "--elected-on", id="elected-on"),
    pytest.param(("--reference", "ref\nx"), "adopt-unwritable-value",
                 "--reference", id="reference"),
    pytest.param(("--elected-by", "a\nb"), "adopt-unwritable-value",
                 "--elected-by", id="elected-by"),
]


@pytest.mark.parametrize("cloned, work", SOURCES)
@pytest.mark.parametrize("flags, code, said", FLAG_REFUSALS)
def test_a_refusal_the_flags_alone_decide_is_asked_before_anything_exists(
        harness, source, cloned, work, flags, code, said):
    """Each is `plan`'s refusal, in its own words, with no `gh repo clone`,
    no `git` in the source, no work directory made and nothing in the temp
    folder: on main an `org/repo` source was `source-unclonable` for each,
    and a local one had run eight `git` commands and made the directory."""
    result = harness.plan(the_source(cloned, source), *flags, work=work)
    refused_first(harness, result, code, said, work)


def test_the_branch_a_tracking_branch_names_is_asked_before_the_source(
        harness, source):
    """`--tracking-branch a..b` is git's to refuse, and is asked of a
    throwaway repository in the temp folder, never of the source: the only
    `git` that ran is `check-ref-format`, and it removed what it made."""
    for given in (REPOSITORY, str(source)):
        result = harness.plan(given, "--tracking-branch", "a..b", work=True)
        assert result.returncode == 2, result.stdout + result.stderr
        assert result.stderr.startswith(
            "REFUSED adopt-bad-tracking-branch: --tracking-branch is "
            "'a..b'"), result.stderr
        assert result.stdout == ""
        assert harness.gh_calls() == []
        asked = harness.git_commands()
        assert asked, "git was never asked"
        assert all(line.startswith("check-ref-format ")
                   for line in asked), asked
        assert not harness.work.exists()
        assert list(harness.temp.iterdir()) == []


#: Pairs of refusals in the order `_checked_plan_inputs` asked them on main,
#: which holds where both apply: the first is the one said.
ORDER = [
    pytest.param(("--project", "Th ing"), ("--spec-path", "spec/"),
                 "unsafe-value", id="project-then-leg-path"),
    pytest.param(("--spec-path", "spec/"), ("--pin", "openGlass"),
                 "adopt-bad-leg-path", id="leg-path-then-pin"),
    pytest.param(("--pin", f"spec@{ZERO}"), ("--spec-path", "project.yaml"),
                 "adopt-pin-collides", id="pin-then-collision"),
    pytest.param(("--spec-path", "project.yaml"), ("--id", "North_Wind"),
                 "adopt-leg-path-collides", id="collision-then-id"),
    pytest.param(("--id", "North_Wind"), ("--org=-evil",),
                 "adopt-bad-id", id="id-then-org"),
    pytest.param(("--org=-evil",), ("--elected-on", "2026-9-2"),
                 "unsafe-value", id="org-then-date"),
    pytest.param(("--elected-on", "2026-9-2"), ("--reference", "ref\nx"),
                 "election-date-malformed", id="date-then-reference"),
]


@pytest.mark.parametrize("first, second, code", ORDER)
def test_the_refusals_keep_the_order_they_were_asked_in(harness, first,
                                                        second, code):
    """The order inside `_checked_plan_inputs` is the order a reader would
    look for the line that was wrong in (#138), and moving the questions
    ahead of the source keeps it. Asked of an `org/repo` source, where on
    main none of these was said at all."""
    for flags in ((*first, *second), (*second, *first)):
        result = harness.plan(REPOSITORY, *flags, work=True)
        refused_first(harness, result, code, "", work=True)


def test_a_flag_refusal_is_said_before_a_name_that_is_not_the_sources(
        harness):
    """`--project Other` for the source `testorg/Thing` is
    `adopt-not-the-source`, which is asked next, once the source's name is
    known; a refusal the flags alone decide is said before it."""
    result = harness.plan(REPOSITORY, "--project", "Other", "--spec-path",
                          "spec/", work=True)
    refused_first(harness, result, "adopt-bad-leg-path", "--spec-path",
                  work=True)


# ---------------------------------------------------------------------------
# L4-37: an `org/repo` source is held to --org and --project before the clone
# ---------------------------------------------------------------------------

def not_the_source(named: str, repository: str, how: str) -> str:
    """The whole of stderr when `plan` refuses `named`, the repository the
    flags name, for the source `repository`. `how` is how it names the
    flags."""
    own_org, own_name = repository.split("/")
    return (f"REFUSED adopt-not-the-source: {how} {named}, and the source "
            f"is {repository}: {WHY}\n"
            + OWN_NAME.format(name=own_name, org=own_org,
                              repository=repository))


@pytest.mark.parametrize("given, flags, expected", [
    pytest.param(
        REPOSITORY, ("--project", "Other"),
        not_the_source("testorg/Other", REPOSITORY,
                       "--org testorg and --project Other name"),
        id="another-project"),
    pytest.param(
        REPOSITORY, ("--org", "other-org"),
        not_the_source("other-org/Thing", REPOSITORY,
                       "--org other-org and --project Thing name"),
        id="another-org"),
    pytest.param(
        f"https://github.com/{REPOSITORY}.git", ("--project", "Other"),
        not_the_source("testorg/Other", REPOSITORY,
                       "--org testorg and --project Other name"),
        id="a-url"),
])
@pytest.mark.parametrize("work", [False, True], ids=["default", "work-dir"])
def test_an_org_repo_source_is_held_to_its_name_before_it_is_cloned(
        harness, given, flags, expected, work):
    """The name is the one `--source` gave, so the refusal comes with no
    `gh repo clone` and no work directory, in the words it has after a
    clone. On main it came after the clone, and with a clone that failed it
    was never said."""
    result = harness.plan(given, *flags, work=work)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr == expected
    assert result.stdout == ""
    assert harness.gh_calls() == []
    assert harness.git_commands() == []
    if work:
        assert not harness.work.exists()
    assert list(harness.temp.iterdir()) == []


def test_no_org_is_the_sources_and_the_refusal_says_where_it_came_from(
        harness):
    """`--org` not given is the organisation of `--source`, as it is after
    the clone, and the refusal names it so and not as a flag nobody typed
    (#427)."""
    planned = ("--project", "Other", "--elected-by", "Test Human",
               "--elected-on", "2026-09-02")
    result = harness.plan(REPOSITORY, work=True, planned=planned)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr == not_the_source(
        "testorg/Other", REPOSITORY,
        "--project Other, with the organisation of `--source` (`--org` not "
        "given), names")
    assert harness.gh_calls() == []
    assert not harness.work.exists()


@pytest.mark.parametrize("given, cloned", [
    pytest.param(REPOSITORY, REPOSITORY, id="the-name"),
    pytest.param("testorg/thing", "testorg/thing", id="another-case"),
    pytest.param(f"https://github.com/{REPOSITORY}", REPOSITORY, id="a-url"),
])
def test_control_the_sources_own_name_still_reaches_the_clone(
        harness, given, cloned):
    """Compared without case, as GitHub resolves a name: `testorg/thing` is
    `--project Thing` in `testorg`. The refusal is not asked of what it
    would pass, and `plan` goes on to `gh repo clone`, which the stub
    refuses: one call, and `source-unclonable`. Passes on main as well."""
    result = harness.plan(given, work=True)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith("REFUSED source-unclonable: "), \
        result.stderr
    calls = harness.gh_calls()
    assert len(calls) == 1, calls
    assert calls[0].startswith(f"repo clone {cloned} "), calls


def test_control_a_local_source_is_held_to_its_name_after_git_reads_it(
        harness, source):
    """A source read in place names its repository by its `origin`, which
    only `git` can read, so `adopt-not-the-source` is still asked after it,
    as before; and `gh` is not called for it."""
    git("remote", "add", "origin", f"https://github.com/{REPOSITORY}.git",
        cwd=source)
    result = harness.plan(str(source), "--project", "Other", work=True)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr == not_the_source(
        "testorg/Other", REPOSITORY, "--org testorg and --project Other name")
    assert "remote get-url origin" in harness.git_commands()
    assert harness.gh_calls() == []


# ---------------------------------------------------------------------------
# L1-67: plan's own reason for a folder it cannot clone into, and no probe
# ---------------------------------------------------------------------------

def plan_cannot_clone(work: Path, repository: str) -> str:
    """The whole of stderr when `plan` refuses `work`: the reason ends in
    what `plan` does there, which is the clone."""
    name = repository.split("/")[1]
    return (f"REFUSED {WORK_DIR_UNWRITABLE}: --work-dir "
            f"{ticked(str(work.resolve()))} cannot be written: making a "
            "directory in it, and removing it again, failed "
            f"({os.strerror(errno.EACCES)}), and `plan` clones {repository} "
            f"into `source-readonly/{name}` there\n"
            f"Remediation: {FIX}\n")


@pytest.mark.parametrize("repository", [REPOSITORY, f"{ORG}/Atlas"])
def test_plan_gives_its_own_reason_for_a_folder_it_cannot_clone_into(
        harness, unwritable_work, repository):  # noqa: F811
    """`execute` builds the legs and the split in the work directory, and
    says so; `plan` only clones, and says that. The directory is left as it
    was, and `gh` is never called."""
    name = repository.split("/")[1]
    planned = ("--project", name, "--org", ORG, "--elected-by", "Test Human",
               "--elected-on", "2026-09-02")
    result = harness.plan(repository, "--work-dir", str(unwritable_work),
                          planned=planned)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr == plan_cannot_clone(unwritable_work, repository)
    assert "`execute` builds" not in result.stderr
    assert result.stdout == ""
    assert harness.gh_calls() == []
    assert list(unwritable_work.iterdir()) == []


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_flag_first", ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def probes_made(adopter, monkeypatch, capsys, *args: str) -> tuple:
    """`plan <args>` in this process, and `(its exit code, its stderr, the
    prefix of each temporary directory it made)`: the write probe of
    `_unwritable_work_dir` makes one named `write-probe-` and removes it,
    which nothing left on disk shows."""
    prefixes: list[str] = []
    real = tempfile.mkdtemp

    def spy(*spied, **named):
        prefixes.append(named.get("prefix", ""))
        return real(*spied, **named)

    monkeypatch.setattr(tempfile, "mkdtemp", spy)
    capsys.readouterr()
    code = adopter.main(["plan", *args])
    return code, capsys.readouterr().err, prefixes


def test_a_local_source_does_not_probe_the_work_dir_it_writes_nothing_in(
        adopter, monkeypatch, capsys, tmp_path, source,
        unwritable_work):  # noqa: F811
    """A local source is read in place, so the plan is written, exit 0, in a
    work directory this user cannot write in, and no directory is made in
    it to find that out. On main one was, and removed, for an answer
    `Source.in_place` never read."""
    out = tmp_path / PLAN_FILE
    code, said, prefixes = probes_made(
        adopter, monkeypatch, capsys, "--source", str(source), *PLANNED,
        "--out", str(out), "--work-dir", str(unwritable_work))
    assert code == 0, said
    assert out.is_file()
    assert "write-probe-" not in prefixes, prefixes


def test_control_an_org_repo_source_still_probes_the_work_dir_it_clones_into(
        adopter, monkeypatch, capsys, tmp_path,
        unwritable_work):  # noqa: F811
    """The clone is made in the work directory, so it is asked whether one
    can be: once, and refused in `plan`'s words. Passes on main as well,
    in `execute`'s."""
    code, said, prefixes = probes_made(
        adopter, monkeypatch, capsys, "--source", REPOSITORY, *PLANNED,
        "--out", str(tmp_path / PLAN_FILE), "--work-dir",
        str(unwritable_work))
    assert code == 2, said
    assert said == plan_cannot_clone(unwritable_work, REPOSITORY)
    assert prefixes.count("write-probe-") == 1, prefixes


def test_control_a_local_source_is_refused_a_work_dir_that_cannot_be_made(
        harness, source, tmp_path):
    """The directory is still made for a local source, since `--out` may
    lie in it, so one that cannot be made is refused as it was, by name.
    Passes on main as well."""
    in_the_way = tmp_path / "a-file"
    in_the_way.write_text("mine\n", encoding=UTF8)
    result = harness.plan(str(source), "--work-dir", str(in_the_way))
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(
        f"REFUSED {WORK_DIR_UNWRITABLE}: --work-dir "
        f"{ticked(str(in_the_way.resolve()))} cannot be made: "), \
        result.stderr
    assert in_the_way.read_text(encoding=UTF8) == "mine\n"


# ---------------------------------------------------------------------------
# Controls: a good plan still plans, and its values are still recorded
# ---------------------------------------------------------------------------

GOOD = ("--spec-path", "legs/spec", "--code-path", "legs/code",
        "--tracking-branch", "main", "--id", "thing", "--reference",
        "a reference", "--elected-by", "Test Human", "--elected-on",
        "2026-09-02", "--org", ORG, "--project", PROJECT)


@pytest.mark.parametrize("work", [False, True], ids=["default", "work-dir"])
def test_control_a_plan_with_good_flags_still_plans_a_local_source(
        harness, source, work):
    """Every value `_checked_flag_inputs` asks is still handed back and
    recorded as it was typed, and the plan is written. Passes on main as
    well."""
    result = harness.plan(str(source), *GOOD, work=work)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"plan written to {harness.out}" in result.stdout
    plan = load_yaml(harness.out)
    assert plan["project"] == PROJECT
    assert plan["org"] == ORG
    assert plan["id"] == "thing"
    assert plan["tracking_branch"] == "main"
    assert plan["reference"] == "a reference"
    assert plan["elected_on"] == "2026-09-02"
    assert plan["legs"]["spec_path"] == "legs/spec"
    assert plan["legs"]["code_path"] == "legs/code"
    assert harness.gh_calls() == []


def test_control_a_plan_with_good_flags_reaches_the_clone_of_an_org_repo(
        harness):
    """The same flags, for an `org/repo` source: nothing is refused for
    them, and `plan` goes on to the clone, which the stub refuses, once.
    Passes on main as well."""
    result = harness.plan(REPOSITORY, *GOOD, work=True)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith("REFUSED source-unclonable: "), \
        result.stderr
    calls = harness.gh_calls()
    assert len(calls) == 1, calls
    assert calls[0].startswith(f"repo clone {REPOSITORY} "), calls
