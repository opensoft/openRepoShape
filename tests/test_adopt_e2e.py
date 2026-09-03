# SPDX-License-Identifier: Apache-2.0
"""End to end: adopt a repository in place, into local bare repositories.

NO REAL REPOSITORY IS EVER CREATED and no network is used. The two legs are
bare repositories on disk; the "source" is a repository in a temporary
directory, and what `execute` pushes to it is a BRANCH — never `main`, which
is the same posture the tool takes against a real organisation with a
pull-request ruleset.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

import pytest

from conftest import (ADOPT, FILE_PROTOCOL, REPO, git, resolve, run_script,
                      write_plan)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml  # noqa: E402

PROJECT = "Northwind"
ANSWERS = (("examples/", "spec"), (".claude/", "root"), ("release.yaml", "root"))

#: `execute` REQUIRES `git filter-repo` and says so with an install hint. A
#: machine without it skips this file rather than failing it — the refusal
#: itself is tested in `test_adopt_plan.py`, which needs no such tool — while
#: CI installs it, so the end-to-end path never quietly stops running.
pytestmark = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")


@pytest.fixture(scope="module")
def adopted(tmp_path_factory) -> dict:
    """One real adoption: plan, answer the questions, check, execute."""
    base = tmp_path_factory.mktemp("adopt")
    source = base / "Thing"
    from conftest import make_source_repo
    make_source_repo(source)
    plan = base / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stderr
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(base / "remotes"),
                        "--work-dir", str(base / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    return {"base": base, "source": source, "plan": plan,
            "remotes": base / "remotes", "work": base / "work",
            "stdout": result.stdout, "stderr": result.stderr}


@pytest.fixture
def adopted_clone(adopted, tmp_path):
    """A recursive clone of the source at the split branch."""
    target = tmp_path / PROJECT
    proc = subprocess.run(
        ["git", *FILE_PROTOCOL, "clone", "-q", "--recurse-submodules",
         "-b", "adopt/three-repo-shape", str(adopted["source"]), str(target)],
        capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return target


# --- what execute refuses --------------------------------------------------

def test_execute_refuses_while_a_leg_is_null(source_repo, tmp_path):
    plan = tmp_path / "plan.yaml"
    assert write_plan(source_repo, plan, project=PROJECT).returncode == 0
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "plan-unresolved" in result.stderr
    assert "never an implicit `root`" in result.stderr
    assert not (tmp_path / "remotes").exists()


def test_execute_refuses_without_yes_when_nobody_can_be_asked(source_repo,
                                                              tmp_path):
    """A subprocess has no terminal, so there is nobody to answer the prompt.
    Creating two repositories on an assumption is the thing being prevented."""
    plan = tmp_path / "plan.yaml"
    assert write_plan(source_repo, plan, project=PROJECT).returncode == 0
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    result = run_script(ADOPT, "execute", "--plan", str(plan),
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "adopt-unconfirmed" in result.stderr
    assert not (tmp_path / "remotes").exists()


# --- the legs --------------------------------------------------------------

def test_both_legs_exist_with_more_than_one_commit(adopted):
    for leg in ("spec", "code"):
        bare = adopted["remotes"] / f"{PROJECT}-{leg}.git"
        assert bare.is_dir()
        count = int(git("rev-list", "--count", "main", cwd=bare).stdout)
        assert count > 1, f"the {leg} leg kept {count} commit(s): not history"


def test_a_files_history_is_followable_inside_its_leg(adopted, tmp_path):
    """The point of `git filter-repo`: the commits that made a file come with
    it. The specification was edited in a second commit; the leg has both."""
    clone = tmp_path / "spec-leg"
    subprocess.run(["git", "clone", "-q",
                    str(adopted["remotes"] / f"{PROJECT}-spec.git"),
                    str(clone)], check=True)
    log = git("log", "--oneline", "--", "specs/001-feature/spec.md",
              cwd=clone).stdout.splitlines()
    assert len(log) == 2, f"expected two commits for the spec file, got {log}"
    assert "Extend the specification" in " ".join(log)
    assert (clone / "specs" / "001-feature" / "spec.md").read_text() \
        .endswith("A second paragraph.\n")
    authors = git("log", "--format=%an", cwd=clone).stdout.split("\n")
    assert "Source Human" in authors, "the original author must survive"


def test_the_legs_keep_the_paths_they_had_in_the_source(adopted, tmp_path):
    """Paths are NOT flattened: `scripts/validate.py` stays there, which is
    what makes `../spec/contracts` from `code/` the correct read-across."""
    clone = tmp_path / "code-leg"
    subprocess.run(["git", "clone", "-q",
                    str(adopted["remotes"] / f"{PROJECT}-code.git"),
                    str(clone)], check=True)
    assert (clone / "src" / "app" / "main.py").is_file()
    assert (clone / "tests" / "test_main.py").is_file()
    assert not (clone / "specs").exists()


# --- the assembly root -----------------------------------------------------

def test_the_source_keeps_its_default_branch_untouched(adopted):
    """IN PLACE means in place: `main` is where it was, and the split is on a
    branch, because the organisations this serves are pull-request only."""
    head = git("rev-parse", "main", cwd=adopted["source"]).stdout.strip()
    plan = load_yaml(adopted["plan"])
    assert head == plan["source"]["commit"]
    branches = git("branch", "--format=%(refname:short)",
                   cwd=adopted["source"]).stdout.split()
    assert "adopt/three-repo-shape" in branches


def test_the_split_commit_lists_every_moved_path(adopted):
    message = git("log", "-1", "--format=%B", "adopt/three-repo-shape",
                  cwd=adopted["source"]).stdout
    assert "MOVED TO THE SPEC LEG" in message
    assert "MOVED TO THE CODE LEG" in message
    assert "STAYS IN THE ASSEMBLY ROOT" in message
    for path in ("specs/", "contracts/", "src/", "tests/", ".specify/"):
        assert path in message
    assert "FOLLOW-UPS, which this commit does NOT do:" in message
    assert "CONTRACTS_DIR" in message


def test_the_root_mounts_both_legs_and_keeps_the_root_paths(adopted_clone):
    assert (adopted_clone / "spec" / "specs" / "001-feature" / "spec.md").is_file()
    assert (adopted_clone / "code" / "src" / "app" / "main.py").is_file()
    assert not (adopted_clone / "specs").exists()
    assert not (adopted_clone / "src").exists()
    for kept in ("README.md", "LICENSE", "AGENTS.md", "CLAUDE.md", "Makefile",
                 ".specify/scripts/plan.sh", ".claude/commands/ship.md"):
        assert (adopted_clone / kept).is_file(), f"{kept} must stay in the root"


def test_the_shape_files_land_beside_what_the_source_already_had(adopted_clone):
    """NOTHING IS OVERWRITTEN. The source's own README and Makefile are its
    history; the shape's copies are written beside them and the follow-up says
    to merge them."""
    assert (adopted_clone / "README.md").read_text() == "# Thing\n"
    assert (adopted_clone / "Makefile").read_text().startswith("test:")
    assert (adopted_clone / "shape" / "README.md").is_file()
    shape_makefile = (adopted_clone / "shape" / "Makefile").read_text()
    assert "CONTRACTS_DIR ?= $(CURDIR)/spec/contracts" in shape_makefile
    assert "export CONTRACTS_DIR" in shape_makefile


def test_the_adopted_root_passes_its_own_gate(adopted_clone):
    """The whole point of the shape: the converted project runs its own
    validators, with no openRepoShape anywhere near it."""
    for validator, args in (("validate-repository-naming.py",
                             ["--project", "project.yaml"]),
                            ("validate-manifest.py", []),
                            ("validate-pins.py", [])):
        result = run_script(adopted_clone / "scripts" / validator, *args,
                            cwd=adopted_clone)
        assert result.returncode == 0, \
            f"{validator}: {result.stderr}{result.stdout}"


def test_the_manifest_and_pins_describe_the_legs_that_were_created(adopted,
                                                                   adopted_clone):
    manifest = load_yaml(adopted_clone / "project.yaml")
    assert manifest["kind"] == "project-manifest"
    assert [leg["repository"] for leg in manifest["legs"]] == [
        f"testorg/{PROJECT}", f"testorg/{PROJECT}-spec", f"testorg/{PROJECT}-code"]
    assert manifest["visibility"] == "private", (
        "the fixture passed no --visibility; the two new legs default to "
        "private, and the assembly root's OWN visibility is whatever the "
        "adopted source already was on GitHub — unrelated to this field")
    for role in ("spec", "code"):
        pin = load_yaml(adopted_clone / "contracts" / f"{role}-pin.yaml")
        assert pin["revision_kind"] == "commit"
        tip = git("rev-parse", "main",
                  cwd=adopted["remotes"] / f"{PROJECT}-{role}.git").stdout.strip()
        assert pin["commit"] == tip
        gitlink = git("rev-parse", f"HEAD:{role}", cwd=adopted_clone).stdout.strip()
        assert gitlink == tip, "the gitlink and the pin move together or not"


# --- verification ----------------------------------------------------------

def test_verification_accounts_for_every_source_path(adopted):
    out = adopted["stdout"]
    assert "adoption verified: every source path is in exactly one place" in out
    assert "VERIFICATION" in out
    counted = sum(int(line.split()[1]) for line in out.splitlines()
                  if line.strip().startswith(("spec ", "code ", "root ", "drop "))
                  and " of " in line)
    total = int([line for line in out.splitlines()
                 if " of " in line and "source paths" in line][0].split()[3])
    assert counted == total, "the table must add up to the source's file count"


def test_a_dropped_path_is_accounted_for_as_dropped(source_repo, tmp_path):
    """`drop` is a legitimate answer, and the verification knows it: a dropped
    path is in no leg and no longer in the root, and that is not a loss."""
    plan = tmp_path / "plan.yaml"
    assert write_plan(source_repo, plan, project=PROJECT).returncode == 0
    for path, leg in ANSWERS:
        resolve(plan, path, "drop" if path == "release.yaml" else leg)
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "drop       1 of" in result.stdout
    assert "adoption verified" in result.stdout
    assert not (tmp_path / "work" / PROJECT / "release.yaml").exists()


def test_re_running_into_a_live_leg_refuses(adopted, tmp_path):
    """There is no --force here either: re-running over a seeded leg is not
    an adoption."""
    result = run_script(ADOPT, "execute", "--plan", str(adopted["plan"]),
                        "--yes", "--local-remote-dir", str(adopted["remotes"]),
                        "--work-dir", str(tmp_path / "work2"))
    assert result.returncode == 2
    assert "leg-remote-exists" in result.stderr
    assert "There is no --force" in result.stderr


def test_the_tool_never_touches_the_source_working_tree(adopted):
    """`plan` and `check` READ. Nothing here dirties the repository it reads."""
    status = git("status", "--porcelain", cwd=adopted["source"]).stdout
    assert status.strip() == "", f"the source was modified: {status}"


def test_a_plan_path_that_is_a_git_option_is_refused(source_repo, tmp_path):
    """THE PLAN IS UNTRUSTED INPUT: it is edited between `plan` and `execute`,
    by a human or by an AI, and every path in it becomes a git argument."""
    plan = tmp_path / "plan.yaml"
    assert write_plan(source_repo, plan, project=PROJECT).returncode == 0
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    plan.write_text(plan.read_text().replace(
        "  - path: specs/\n", "  - path: --output=/tmp/pwned\n", 1))
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "unsafe-value" in result.stderr
    assert not (tmp_path / "remotes").exists()
