# SPDX-License-Identifier: Apache-2.0
"""End to end: adopt a repository in place, into local bare repositories.

NO REAL REPOSITORY IS EVER CREATED and no network is used. The two legs are
bare repositories on disk; the "source" is a repository in a temporary
directory, and what `execute` pushes to it is a BRANCH — never `main`, which
is the same posture the tool takes against a real organisation with a
pull-request ruleset.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys

import pytest

from conftest import (ADOPT, REPO, cloned_just_pushed, git, make_source_repo,
                      resolve, run_script, write_plan)

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
    return cloned_just_pushed(adopted["source"], tmp_path / PROJECT,
                              "adopt/three-repo-shape")


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


def test_execute_plans_the_topic_and_skips_it_against_local_remotes(adopted):
    """`gh repo edit --add-topic` is what the scaffold does and what adopt now
    does too; the offline path prints the plan line and calls nothing, which
    is what keeps this suite free of the network."""
    assert "topics skipped for local remotes" in adopted["stdout"]
    assert "gh repo edit" not in adopted["stdout"]
    assert "set on all three" not in adopted["stdout"]


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
    clone = cloned_just_pushed(adopted["remotes"] / f"{PROJECT}-spec.git",
                               tmp_path / "spec-leg")
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
    clone = cloned_just_pushed(adopted["remotes"] / f"{PROJECT}-code.git",
                               tmp_path / "code-leg")
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


def test_the_sources_own_agent_files_are_untouched(adopted, adopted_clone):
    """`root-assistant-instructions` keeps a source's `AGENTS.md` and
    `CLAUDE.md` AT THE ROOT because they address the whole project — which is
    the same reason the shape must not replace one. They are also what the
    project's agents already read, so the shape's stubs go beside them."""
    for name in ("AGENTS.md", "CLAUDE.md"):
        assert (adopted_clone / name).read_text() == "Follow the procedure.\n"
        assert (adopted_clone / "shape" / name).is_file()
        # ...and the source's own tree, on its own default branch, is exactly
        # what it was: nothing here edited it, in place or otherwise.
        assert (adopted["source"] / name).read_text() == \
            "Follow the procedure.\n"

    # The shape's OWN rules took their own name: the source had no such file.
    assert (adopted_clone / "AGENTS-shape.md").is_file()
    assert not (adopted_clone / "shape" / "AGENTS-shape.md").exists()
    rows = {row["path"] for row in
            load_yaml(adopted_clone / "contracts" / "shape-pin.yaml")["files"]}
    assert "AGENTS-shape.md" in rows


def next_block(stdout: str) -> list[str]:
    """The lines `execute` prints from `NEXT:` on, to the end of its run."""
    return stdout.split("\nNEXT: ", 1)[1].splitlines()


def test_next_names_the_bootstrap_a_root_with_its_own_makefile_can_run(
        adopted, adopted_clone):
    """The source kept its own Makefile, so the shape's is `shape/Makefile`
    until a person merges the two, and `make bootstrap` in the root exits 2
    (`No rule to make target 'bootstrap'`) (#480). The NEXT block names the
    command `make bootstrap` runs instead, a line says why, and that command,
    run in a recursive clone of the split, exits 0. (It is run with the
    interpreter running this test, which is what `python3` names here.)"""
    said = next_block(adopted["stdout"])
    assert said[:3] == [f"review the pull request on {PROJECT}, then",
                        f"    git clone --recurse-submodules <{PROJECT} url>",
                        "    python3 scripts/bootstrap.py"], said
    assert said[3].startswith("NOTE the root keeps its own Makefile and the "
                              "shape's is shape/Makefile, so `make bootstrap`")
    command = said[2].split()
    ran = subprocess.run([sys.executable, *command[1:]], cwd=adopted_clone,
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace", check=False)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    if shutil.which("make"):
        made = subprocess.run(["make", "bootstrap"], cwd=adopted_clone,
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace", check=False)
        assert made.returncode != 0, made.stdout + made.stderr


def test_the_makefile_follow_up_says_the_shapes_targets_arrive_with_it(
        adopted):
    """The follow-up the plan carries, and the split commit lists, names
    each of the shape's make targets as arriving only with the merge, and
    what runs meanwhile. The targets are read from the template, so a target
    the shape gains and the follow-up does not name fails here."""
    template = (REPO / "templates" / "assembly-root" / "Makefile").read_text(
        encoding="utf-8")
    targets = [name for name in re.findall(r"(?m)^([a-z][a-z-]*):", template)
               if name != "help"]
    assert "bootstrap" in targets, targets
    message = git("log", "-1", "--format=%B", "adopt/three-repo-shape",
                  cwd=adopted["source"]).stdout
    (planned,) = [item for item in load_yaml(adopted["plan"])["follow_ups"]
                  if item.startswith("merge shape/Makefile into Makefile")]
    for text in (planned, " ".join(message.split())):
        assert ("The shape's make targets ("
                + ", ".join(f"`{target}`" for target in targets)
                + ") arrive only with that merge; until then `python3 "
                "scripts/bootstrap.py` is what `make bootstrap` runs") in text


@pytest.fixture(scope="module")
def adopter():
    """`adopt-project.py` as a module, for what it prints and predicts."""
    module_spec = importlib.util.spec_from_file_location("adopt_e2e_next",
                                                         ADOPT)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def test_next_keeps_make_bootstrap_where_the_shapes_makefile_is_the_roots(
        adopter, capsys):
    """Where the shape's Makefile took its own name, NEXT is what it always
    was, byte for byte."""
    adopter._next_steps({"assembly": PROJECT}, [])

    assert capsys.readouterr().out == (
        f"\nNEXT: review the pull request on {PROJECT}, then\n"
        f"    git clone --recurse-submodules <{PROJECT} url>\n"
        "    make bootstrap\n")


#: A source that keeps its own `scripts/bootstrap.py` in the root beside its
#: own Makefile. `scripts/` goes to the code leg unless the plan is answered
#: otherwise, as `kept_scripts` answers it.
OWN_BOOTSTRAP_TREE = {
    "README.md": "# Northwind\n", "src/app.py": "print(1)\n",
    "docs/spec.md": "# Spec\n", "Makefile": "build:\n\t@echo source build\n",
    "scripts/bootstrap.py": "print('THE SOURCE OWN BOOTSTRAP')\n"}
#: What NEXT says in that root, in place of a bootstrap command.
BOTH_ASIDE = (
    "NOTE the root keeps its own Makefile and scripts/bootstrap.py, and the "
    "shape's are shape/Makefile and shape/scripts/bootstrap.py, so neither "
    "`make bootstrap` nor `python3 scripts/bootstrap.py` runs the shape's "
    "bootstrap yet: merge shape/Makefile into Makefile and "
    "shape/scripts/bootstrap.py into scripts/bootstrap.py first, and then "
    "run `make bootstrap`.")


def kept_scripts(plan) -> None:
    """The plan's `scripts/` answered `root`, LF as `plan` wrote it."""
    text = plan.read_text(encoding="utf-8")
    sent = "  - path: scripts/\n    leg: code\n"
    assert sent in text, text
    with plan.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.replace(sent, (
            "  - path: scripts/\n    leg: root\n"
            "    resolution: \"the source keeps its scripts in the root\"\n"),
            1))


def test_next_names_no_bootstrap_where_the_roots_script_is_the_sources_own(
        tmp_path):
    """The source kept its own `scripts/bootstrap.py` in the root as well as
    its own Makefile, so the shape's script went to
    `shape/scripts/bootstrap.py`, and NEXT's `python3 scripts/bootstrap.py`
    ran the SOURCE's script in a recursive clone and exited 0, with no leg
    placed and nothing validated (#493's review, F2). NEXT names no
    bootstrap command there, and says which merges come first."""
    source = make_source_repo(tmp_path / PROJECT, tree=OWN_BOOTSTRAP_TREE,
                              edits=())
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    kept_scripts(plan)

    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))

    assert result.returncode == 0, result.stderr + result.stdout
    assert "  beside  shape/scripts/bootstrap.py " in result.stdout
    assert next_block(result.stdout) == [
        f"review the pull request on {PROJECT}, then",
        f"    git clone --recurse-submodules <{PROJECT} url>",
        BOTH_ASIDE], result.stdout


def test_next_names_no_bootstrap_where_only_the_script_went_aside(
        adopter, capsys):
    """With the shape's Makefile in the root and the source's own
    `scripts/bootstrap.py`, `make bootstrap` runs the source's script, so
    NEXT names no command there either."""
    adopter._next_steps({"assembly": PROJECT}, [
        ("scripts/bootstrap.py", "shape/scripts/bootstrap.py")])

    assert capsys.readouterr().out == (
        f"\nNEXT: review the pull request on {PROJECT}, then\n"
        f"    git clone --recurse-submodules <{PROJECT} url>\n"
        "NOTE the root keeps its own scripts/bootstrap.py, and the shape's is "
        "shape/scripts/bootstrap.py, so neither `make bootstrap` nor `python3 "
        "scripts/bootstrap.py` runs the shape's bootstrap yet: merge "
        "shape/scripts/bootstrap.py into scripts/bootstrap.py first, and then "
        "run `make bootstrap`.\n")


def test_the_makefile_follow_up_waits_for_a_script_that_went_aside_too(
        adopter):
    """`plan` predicts the follow-ups from what the plan keeps in the root,
    and tells each the whole list: where `scripts/` stays as well, the
    root's `scripts/bootstrap.py` is the source's own, so the Makefile's
    follow-up does not name `python3 scripts/bootstrap.py` as what runs
    meanwhile (#493's review, F2)."""
    kept = [adopter.Entry(path, adopter.Verdict(
        "root", "test", "kept by the test", "high"), 1, 1)
        for path in ("Makefile", "scripts/")]

    (makefile,) = [item for item in adopter._predict_collisions(kept)
                   if item.startswith("merge shape/Makefile into Makefile")]

    assert makefile.endswith(
        "arrive only with that merge, and the root's scripts/bootstrap.py is "
        "the source's own until shape/scripts/bootstrap.py is merged into it "
        "as well, so neither `make bootstrap` nor `python3 "
        "scripts/bootstrap.py` runs the shape's bootstrap before both merges "
        "are made"), makefile


def test_the_agent_file_collision_says_add_a_line_not_merge(adopted):
    """A merge is the wrong instruction for an instruction file: it is how a
    project's own agent instructions end up inside the shape's. The follow-up
    names the one line to add, and the reason it is not a replacement."""
    follow_ups = " ".join(load_yaml(adopted["plan"])["follow_ups"])
    message = git("log", "-1", "--format=%B", "adopt/three-repo-shape",
                  cwd=adopted["source"]).stdout
    for text in (follow_ups, message):
        flat = " ".join(text.split())
        assert ("add the line `Read AGENTS-shape.md first — the rules of this "
                "repository's shape.` to the existing AGENTS.md") in flat
        assert "rather than replacing it with shape/AGENTS.md" in flat
        assert "root-assistant-instructions" in flat
        assert "ALREADY read" in flat
        assert "to the existing CLAUDE.md" in flat
    # The ordinary collisions still say merge.
    assert "merge shape/Makefile into Makefile" in follow_ups
    assert "merge shape/AGENTS.md" not in follow_ups


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


def test_a_source_with_no_submodule_gets_no_submodule_record(adopted_clone):
    """`execute` records the leg of each source submodule it keeps (#189),
    and this source has none: its manifest gains no `submodules:` and no
    comment about one, and is the manifest every adoption wrote before."""
    manifest = adopted_clone / "project.yaml"
    assert "submodules" not in load_yaml(manifest)
    assert "#189" not in manifest.read_text(encoding="utf-8")


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
    by a human or by an AI, and every path in it reaches git. An entry's path
    that begins with `-` is `check`'s finding `plan-unsafe-path` (#196), and
    `execute` refuses it before any leg exists."""
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
    assert "REFUSED plan-unsafe-path" in result.stderr
    assert not (tmp_path / "remotes").exists()
