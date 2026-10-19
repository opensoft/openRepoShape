# SPDX-License-Identifier: Apache-2.0
"""A leg mounted away from its default path is read across WHERE IT IS (#522).

Two things `adopt-project.py` writes named a leg's mount path as if it were
the default:

  * the block `execute` appends to the assembly root's Makefile exported
    `CONTRACTS_DIR ?= $(CURDIR)/spec/contracts` whatever `--spec-path` said,
    so a project adopted with `--spec-path legs/spec` pointed its code leg's
    tooling at a directory that does not exist, while `plan`'s own follow-up
    said the Makefile wires `$(CURDIR)/legs/spec/contracts`;
  * the follow-up for a code file that names a spec directory said
    `../<spec path>/<dir>` "relative to `<code path>/`", one `..` whatever
    the code leg's depth: `--spec-path legs/spec --code-path legs/code`
    printed `../legs/spec/contracts/`, where `../spec/contracts/` is right
    (auA-13 on #457). #522 climbed once per segment; #600 then took the path
    out of the follow-up, because `plan` writes the line once and the hand
    edit of `legs.spec_path` or `legs.code_path` that the tool asks for left
    a path in it that no longer led anywhere: it names the two keys, and the
    path is printed beside the CURRENT mounts instead, by `check` and in the
    split message (#600's review, F1; `tests/test_adopt_leg_keys.py`).

The block is now rendered with the plan's mount paths, and a DEFAULT
adoption gets the bytes it always got; the path climbs once per segment of
the code leg's path below what the two paths share. Each relative path is
checked by where it LEADS, not only by how it is spelled.

`plan` needs no `git filter-repo`; the end-to-end tests at the bottom do, and
skip without it, as `tests/test_adopt_e2e.py` does. No network and no
GitHub: the legs are bare repositories on disk, and `tests/conftest.py`
keeps a `gh` guard first on PATH.
"""

from __future__ import annotations

import hashlib
import posixpath
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, REPO, clone_just_pushed, git,
                      load_without_bytecode, make_source_repo, run_script,
                      write_plan)
from test_adopt_literal_names import follow_up

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402
from repo_shape import load_yaml  # noqa: E402
from test_pinned_copy_text import ADOPTED_SENTENCES  # noqa: E402

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

PROJECT = "Northwind"
SPLIT_BRANCH = "adopt/three-repo-shape"

#: The block every adoption appended before #522, byte for byte. A default
#: adoption (`spec`, `code`) must keep appending exactly this: its bytes are
#: what the pin of every project adopted so far digests.
DEFAULT_BLOCK = """
# --- adopted project: reading ACROSS the legs -------------------------------
# The spec leg owns `contracts/`; the code leg holds the tooling that reads
# them. Mounted here, `spec/contracts` is one relative path from `code/`, so
# the root exports it once and the code leg takes it from the environment
# rather than each script guessing at `../`.
CONTRACTS_DIR ?= $(CURDIR)/spec/contracts
export CONTRACTS_DIR

.PHONY: contracts-dir
contracts-dir:
\t@echo $(CONTRACTS_DIR)
"""

#: The follow-up that says what the root Makefile does. It names the KEY the
#: block is rendered from and no path: `execute` renders the block from the
#: plan's CURRENT `legs.spec_path`, and the tool's own remediations ask for a
#: hand edit of it after `plan` wrote this line (#522's review, F1).
MAKEFILE_FOLLOW_UP = (
    "the root Makefile wires `CONTRACTS_DIR` to the `contracts/` of the spec "
    "leg, where the plan's `legs.spec_path` mounts it, and exports it, so the "
    "code leg's tooling takes the path from the environment instead of "
    "assuming it sits beside it")

#: The same line for a source that keeps a root `Makefile` of its own (#906):
#: the shape's, with the block, is written beside it as `shape/Makefile`, so
#: the block waits there until the two are merged, as #634 words it for the
#: pinned `AGENTS-shape.md`, and the root's Makefile is the source's, which
#: the run adds nothing to.
OWN_MAKEFILE_FOLLOW_UP = (
    "the shape's Makefile wires `CONTRACTS_DIR` to the `contracts/` of the "
    "spec leg, where the plan's `legs.spec_path` mounts it, and exports it, "
    "so the code leg's tooling takes the path from the environment instead "
    "of assuming it sits beside it; but the source keeps a Makefile of its "
    "own at the root, so that block waits in `shape/Makefile` until the two "
    "are merged, and the run adds none of it to the root's Makefile")

#: A source with nothing for the plan to ask about, no Makefile of its own
#: (so the shape's, with the block, is the root's), and one code file that
#: names `contracts/`, which the rules send to the spec leg.
READER = "src/app/main.py"
POLICY = "policy.yaml"
TREE = {
    "README.md": "# Thing\n",
    "specs/001-feature/spec.md": "# The feature\n",
    f"contracts/{POLICY}": "schema_version: 1\nkind: policy\n",
    READER: f"CONTRACTS = 'contracts/{POLICY}'\n",
    "tests/test_main.py": "def test_ok():\n    assert True\n",
}
EDITS = (("specs/001-feature/spec.md",
          "# The feature\n\nA second paragraph.\n",
          "Extend the specification"),)

#: `(spec path, code path, the spec leg's mount relative to the code leg's)`.
MOUNTS = [
    pytest.param("spec", "code", "../spec", id="defaults"),
    pytest.param("legs/spec", "legs/code", "../spec", id="siblings-in-legs"),
    pytest.param("spec", "impl/code", "../../spec", id="code-nested"),
    pytest.param("legs/spec", "code", "../legs/spec", id="spec-nested"),
    pytest.param("legs/spec", "impl/code", "../../legs/spec",
                 id="both-nested-apart"),
    pytest.param("a/b/spec", "a/code", "../b/spec", id="one-segment-shared"),
    pytest.param("spec", "a/b/c/code", "../../../../spec", id="code-deep"),
    pytest.param("Legs/spec", "legs/code", "../../Legs/spec",
                 id="case-differs"),
    pytest.param("a/b/spec", "a/b/code", "../spec", id="two-segments-shared"),
    pytest.param("legs/spec", "legsX/code", "../../legs/spec",
                 id="prefix-of-the-text-not-of-a-segment"),
    pytest.param("legsX/spec", "legs/code", "../../legsX/spec",
                 id="a-segment-that-extends-the-other"),
]


@pytest.fixture(scope="module")
def adopter():
    """`adopt-project.py` loaded as a module, for its helpers."""
    return load_without_bytecode(ADOPT, "adopt_contracts_dir")


def contracts_dir_line(block: str) -> str:
    (line,) = [line for line in block.splitlines()
               if line.startswith("CONTRACTS_DIR ")]
    return line


# --- the Makefile block -----------------------------------------------------

def test_a_default_adoption_appends_the_block_it_always_did():
    """`spec` and `code` render the pre-#522 block byte for byte, and the
    constant that names it is that rendering."""
    render = shape_materialize.adopt_makefile_block
    assert render("spec", "code") == DEFAULT_BLOCK
    assert shape_materialize.ADOPT_MAKEFILE_BLOCK == DEFAULT_BLOCK


@pytest.mark.parametrize("spec_path, code_path", [
    ("legs/spec", "legs/code"), ("spec-v2", "code"),
    ("legs/spec", "impl/code"), ("a..b", "x/code")])
def test_the_block_exports_the_spec_leg_where_the_plan_mounts_it(
        spec_path, code_path):
    block = shape_materialize.adopt_makefile_block(spec_path, code_path)
    assert contracts_dir_line(block) == (
        f"CONTRACTS_DIR ?= $(CURDIR)/{spec_path}/contracts")
    assert "$(CURDIR)/spec/contracts" not in block
    # The comment that says why names the same two paths.
    assert (f"Mounted here, `{spec_path}/contracts` is one relative path "
            f"from `{code_path}/`") in block
    # Everything but those two lines is the default block's.
    def rest(text: str) -> list[str]:
        return [line for line in text.splitlines()
                if not line.startswith(("CONTRACTS_DIR ", "# them. Mounted"))]
    assert rest(block) == rest(DEFAULT_BLOCK)


# --- the cross-leg follow-up ------------------------------------------------

@pytest.mark.parametrize("spec_path, code_path, expected", MOUNTS)
def test_the_spec_leg_is_named_relative_to_where_the_code_leg_is(
        adopter, spec_path, code_path, expected):
    """The path `check` and the split message print beside the CURRENT mounts
    (#600's review, F1): #522's helper, which #600 had deleted with the path
    in the follow-up."""
    across = adopter.spec_leg_from_code_leg(spec_path, code_path)
    assert across == expected
    # And it LEADS there: from the code leg, the path is the spec leg.
    assert posixpath.normpath(posixpath.join(code_path, across)) == spec_path


@pytest.fixture(scope="module")
def source(tmp_path_factory) -> Path:
    """One source for every `plan` below; `plan` only reads it."""
    return make_source_repo(tmp_path_factory.mktemp("contracts-dir") / "Thing",
                            TREE, edits=EDITS)


def planned_follow_ups(source: Path, out: Path, spec_path: str,
                       code_path: str) -> list[str]:
    written = write_plan(source, out, project=PROJECT,
                         extra=("--spec-path", spec_path,
                                "--code-path", code_path))
    assert written.returncode == 0, written.stderr + written.stdout
    return [str(item) for item in load_yaml(out)["follow_ups"]]


@pytest.mark.parametrize("spec_path, code_path, across", MOUNTS)
def test_plan_names_the_read_across_by_the_two_keys(
        source, tmp_path, spec_path, code_path, across):
    """The follow-up for the code file that names `contracts/` is the same
    line for every mount: it says where the file is, in the code leg, and
    names `legs.code_path` and `legs.spec_path` for the two mounts, with no
    path of either. #522 printed the path from the code leg to the spec
    leg's `contracts/`, and a hand edit of either key after `plan` left a
    path in it that led nowhere (#600); `check` and the split message print
    it beside the CURRENT mounts instead (#600's review, F1)."""
    follow_ups = planned_follow_ups(source, tmp_path / "plan.yaml",
                                    spec_path, code_path)
    (named,) = [item for item in follow_ups
                if f"{READER} in the code leg names " in item]
    assert named == follow_up(READER, "contracts/")
    assert "`legs.code_path`" in named and "`legs.spec_path`" in named
    # Neither mount path, nor the path from one to the other, is in it.
    assert f"{spec_path}/" not in named and f"{code_path}/" not in named
    assert "../" not in named and " relative to " not in named
    assert f"{across}/contracts/" not in named
    # The Makefile follow-up names the key, so it is the same line for every
    # mount, and it names no path for a hand edit of the key to contradict.
    assert follow_ups.count(MAKEFILE_FOLLOW_UP) == 1, follow_ups
    assert not [item for item in follow_ups if "$(CURDIR)" in item]


# --- `execute`, end to end --------------------------------------------------

SPEC_PATH, CODE_PATH = "legs/spec", "impl/code"


def adopt_with_legs_mounted_away(base: Path, *, by_hand: bool,
                                 tree: dict = TREE) -> dict:
    """One real adoption of `tree` with both legs mounted away from their
    defaults, at SPEC_PATH and CODE_PATH, and a recursive clone of its split
    branch. Its own source: `execute` pushes the split branch into the
    repository it adopts.

    `by_hand` plans with the DEFAULT paths and then edits `legs.spec_path` and
    `legs.code_path` in the plan, as `MOUNT_REMEDIATION` and
    `plan-leg-path-collides` ask a person to. Otherwise `plan` is given them.
    """
    source = make_source_repo(base / "Thing", tree, edits=EDITS)
    plan = base / "adoption-plan.yaml"
    planned_follow_ups(
        source, plan, *(("spec", "code") if by_hand else (SPEC_PATH, CODE_PATH)))
    if by_hand:
        text = plan.read_text(encoding="utf-8")
        edited = (text.replace("  spec_path: spec\n",
                               f"  spec_path: {SPEC_PATH}\n")
                      .replace("  code_path: code\n",
                               f"  code_path: {CODE_PATH}\n"))
        assert f"  spec_path: {SPEC_PATH}\n" in edited, text
        assert f"  code_path: {CODE_PATH}\n" in edited, text
        with open(plan, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(edited)
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(base / "remotes"),
                        "--work-dir", str(base / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "adoption verified" in result.stdout, result.stdout
    # `execute` has just pushed into `source`: read it through git, not
    # through its files (#440, #554).
    clone = base / PROJECT
    proc = clone_just_pushed(source, clone, branch=SPLIT_BRANCH)
    assert proc.returncode == 0, proc.stderr
    makefile = subprocess.run(
        ["git", "show", f"{SPLIT_BRANCH}:Makefile"], cwd=str(source),
        capture_output=True, check=True).stdout
    return {"source": source, "clone": clone, "makefile": makefile}


@pytest.fixture(scope="module")
def adopted(tmp_path_factory) -> dict:
    """The adoption whose `plan` was given both mount paths."""
    return adopt_with_legs_mounted_away(
        tmp_path_factory.mktemp("contracts-dir-adopted"), by_hand=False)


@pytest.fixture(scope="module")
def adopted_by_hand(tmp_path_factory) -> dict:
    """The adoption whose plan's mount paths were edited after `plan`."""
    return adopt_with_legs_mounted_away(
        tmp_path_factory.mktemp("contracts-dir-by-hand"), by_hand=True)


#: A root `Makefile` the source keeps: the `root-project-makefile` rule leaves
#: it in the root, and the shape's Makefile lands beside it as `shape/Makefile`.
OWN_MAKEFILE = "build:\n\t@echo the source's own build\n"


@pytest.fixture(scope="module")
def adopted_with_its_own_makefile(tmp_path_factory) -> dict:
    """The adoption of a source that keeps a root Makefile of its own."""
    return adopt_with_legs_mounted_away(
        tmp_path_factory.mktemp("contracts-dir-own-makefile"), by_hand=False,
        tree={**TREE, "Makefile": OWN_MAKEFILE})


@needs_filter_repo
def test_the_adopted_makefile_exports_the_spec_legs_contracts(adopted):
    """The split's Makefile (the shape's, at the root: the source kept none)
    exports `$(CURDIR)/legs/spec/contracts`, and in a recursive clone that
    is the directory holding the source's contracts."""
    text = adopted["makefile"].decode("utf-8")
    line = contracts_dir_line(text)
    exported = adopted["clone"].joinpath(
        *line.split("$(CURDIR)/", 1)[1].split("/"))
    assert (exported / POLICY).is_file(), line
    assert line == f"CONTRACTS_DIR ?= $(CURDIR)/{SPEC_PATH}/contracts"
    assert text.endswith(
        shape_materialize.adopt_makefile_block(SPEC_PATH, CODE_PATH))


@needs_filter_repo
@pytest.mark.skipif(shutil.which("make") is None or sys.platform == "win32",
                    reason="needs make, and a POSIX `$(CURDIR)` spelling")
def test_make_contracts_dir_prints_a_directory_that_exists(adopted):
    made = subprocess.run(
        ["make", "--no-print-directory", "-s", "contracts-dir"],
        cwd=str(adopted["clone"]), capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False)
    assert made.returncode == 0, made.stdout + made.stderr
    printed = Path(made.stdout.strip())
    assert printed == adopted["clone"].resolve() / SPEC_PATH / "contracts"
    assert (printed / POLICY).is_file()


@needs_filter_repo
def test_the_pinned_agent_file_is_true_of_the_adopted_makefile(adopted):
    """L2-33 (#610). The adopted root's pinned `AGENTS-shape.md` said "the
    root Makefile exports `$(CURDIR)/spec/contracts` once", while this
    root's Makefile exports `$(CURDIR)/legs/spec/contracts`. It names no
    path now: the `contracts/` of the spec leg at the path `project.yaml`
    mounts it, and that is the path the Makefile exports."""
    said = " ".join((adopted["clone"] / "AGENTS-shape.md").read_text(
        encoding="utf-8").split())
    assert "$(CURDIR)" not in said
    assert "spec/contracts" not in said
    assert ADOPTED_SENTENCES in said
    (mounted,) = [str(leg["path"]) for leg in load_yaml(
        adopted["clone"] / "project.yaml")["legs"] if leg["role"] == "spec"]
    assert mounted == SPEC_PATH
    assert contracts_dir_line(adopted["makefile"].decode("utf-8")) == (
        f"CONTRACTS_DIR ?= $(CURDIR)/{mounted}/contracts")


@needs_filter_repo
@pytest.mark.skipif(shutil.which("make") is None or sys.platform == "win32",
                    reason="needs make, and a POSIX `$(CURDIR)` spelling")
def test_the_pinned_agent_file_says_where_a_kept_makefile_leaves_the_block(
        adopted_with_its_own_makefile):
    """F1 (rv610, #634). A source that keeps a root Makefile of its own keeps
    it AT THE ROOT, with no `CONTRACTS_DIR`, so `make contracts-dir` there
    has no rule: the block waits in `shape/Makefile`. The pinned
    `AGENTS-shape.md` said the root's Makefile exports `CONTRACTS_DIR` and
    `make contracts-dir` prints it. It now says the SHAPE's Makefile does,
    and that the block waits in `shape/Makefile` where the source kept its
    own."""
    clone = adopted_with_its_own_makefile["clone"]
    # The source's own bytes, whatever line ending `write_text` gave them.
    assert adopted_with_its_own_makefile["makefile"].decode(
        "utf-8").splitlines() == OWN_MAKEFILE.splitlines()
    block = (clone / "shape" / "Makefile").read_text(encoding="utf-8")
    assert contracts_dir_line(block) == (
        f"CONTRACTS_DIR ?= $(CURDIR)/{SPEC_PATH}/contracts")
    at_the_root = subprocess.run(
        ["make", "--no-print-directory", "-s", "contracts-dir"],
        cwd=str(clone), capture_output=True, text=True, encoding="utf-8",
        errors="replace", check=False)
    assert at_the_root.returncode != 0, at_the_root.stdout
    assert "No rule to make target 'contracts-dir'" in at_the_root.stderr, (
        at_the_root.stderr)
    # Where the block waits, the target prints the spec leg's `contracts/`.
    in_the_shapes = subprocess.run(
        ["make", "--no-print-directory", "-s", "-f", "shape/Makefile",
         "contracts-dir"],
        cwd=str(clone), capture_output=True, text=True, encoding="utf-8",
        errors="replace", check=False)
    assert in_the_shapes.returncode == 0, in_the_shapes.stderr
    assert Path(in_the_shapes.stdout.strip()) == (
        clone.resolve() / SPEC_PATH / "contracts")
    said = " ".join((clone / "AGENTS-shape.md").read_text(
        encoding="utf-8").split())
    assert ADOPTED_SENTENCES in said


@needs_filter_repo
def test_the_pin_digests_the_rendered_makefile(adopted):
    """The block is the adoption's own append, so the shape pin records the
    Makefile as written, block included, and the project's own pin
    validator passes over it."""
    rows = {row["path"]: row["sha256"] for row in load_yaml(
        adopted["clone"] / "contracts" / "shape-pin.yaml")["files"]}
    assert rows["Makefile"] == hashlib.sha256(adopted["makefile"]).hexdigest()
    validated = subprocess.run(
        [sys.executable, "scripts/validate-pins.py"], cwd=str(adopted["clone"]),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False)
    assert validated.returncode == 0, validated.stdout + validated.stderr


@needs_filter_repo
def test_a_hand_edited_mount_leaves_the_follow_up_true_of_the_makefile(
        adopted_by_hand):
    """#522's review, F1. `plan` wrote the Makefile follow-up once, and the
    split commit's message, which is also the pull request's body, holds it.
    `execute` renders the Makefile in that same commit from the plan's mount
    paths as they are NOW. After the hand edit the tool asks for, the message
    still said `$(CURDIR)/spec/contracts` while the Makefile said
    `$(CURDIR)/legs/spec/contracts`: the follow-up names the key, and so
    cannot disagree with the Makefile about its value."""
    message = " ".join(git(
        "log", "-1", "--format=%B", SPLIT_BRANCH,
        cwd=adopted_by_hand["source"]).stdout.split())
    assert MAKEFILE_FOLLOW_UP in message
    assert "$(CURDIR)" not in message
    assert contracts_dir_line(adopted_by_hand["makefile"].decode("utf-8")) == (
        f"CONTRACTS_DIR ?= $(CURDIR)/{SPEC_PATH}/contracts")
    # The edited paths are where `execute` mounted the legs.
    mounts = git("show", f"{SPLIT_BRANCH}:.gitmodules",
                 cwd=adopted_by_hand["source"]).stdout
    assert f"path = {SPEC_PATH}" in mounts
    assert f"path = {CODE_PATH}" in mounts


@needs_filter_repo
def test_the_path_the_split_message_prints_leads_to_the_contracts(
        adopted_by_hand):
    """#600's review, F1. The follow-up names the keys and no path, so the
    split commit's message prints the path from the code leg to the spec
    leg's `contracts/` where it says where the legs are mounted, from the
    mounts `execute` made: after the hand edit to `legs/spec` and
    `impl/code`, `../../legs/spec/contracts/`, which the default plan would
    have given as `../spec/contracts/`. Followed from the code leg of a
    recursive clone, it reaches the spec leg's file."""
    message = git("log", "-1", "--format=%B", SPLIT_BRANCH,
                  cwd=adopted_by_hand["source"]).stdout
    marker = "the spec leg's `contracts/` is `"
    printed = message.split(marker, 1)[1].split("`", 1)[0]
    assert printed == "../../legs/spec/contracts/"
    # The plan holds the read-across line, so the spec leg's own path comes
    # first (#906), and then the path to its `contracts/`.
    assert (f"mounted back here at {SPEC_PATH}/ and {CODE_PATH}/, so from "
            f"the code leg the spec leg is `../../legs/spec/` and "
            f"{marker}{printed}`.") in message
    code_leg = adopted_by_hand["clone"].joinpath(*CODE_PATH.split("/"))
    target = code_leg.joinpath(*printed.rstrip("/").split("/"), POLICY)
    assert target.resolve() == adopted_by_hand["clone"].joinpath(
        *SPEC_PATH.split("/"), "contracts", POLICY).resolve()
    assert target.resolve().is_file()
