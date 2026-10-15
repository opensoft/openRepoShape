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
    (auA-13 on #457).

The block is now rendered with the plan's mount paths, and a DEFAULT
adoption gets the bytes it always got; the follow-up climbs once per segment
of the code leg's path below what the two paths share. Each relative path is
checked by where it LEADS, not only by how it is spelled.

`plan` needs no `git filter-repo`; the end-to-end tests at the bottom do, and
skip without it, as `tests/test_adopt_e2e.py` does. No network and no
GitHub: the legs are bare repositories on disk, and `tests/conftest.py`
keeps a `gh` guard first on PATH.
"""

from __future__ import annotations

import hashlib
import importlib.util
import posixpath
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, REPO, clone_just_pushed, git, make_source_repo,
                      run_script, write_plan)

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402
from repo_shape import load_yaml  # noqa: E402

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
]


@pytest.fixture(scope="module")
def adopter():
    """`adopt-project.py` loaded as a module, for its helpers."""
    module_spec = importlib.util.spec_from_file_location(
        "adopt_contracts_dir", ADOPT)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


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


@pytest.mark.parametrize("spec_path, code_path, expected", MOUNTS)
def test_plan_names_the_read_across_from_where_the_code_leg_is(
        source, tmp_path, spec_path, code_path, expected):
    """The follow-up for the code file that names `contracts/` gives the
    path from the code leg's mount, and that path leads to the spec leg's
    `contracts/`. The defaults print what they always printed."""
    follow_ups = planned_follow_ups(source, tmp_path / "plan.yaml",
                                    spec_path, code_path)
    (named,) = [item for item in follow_ups
                if item.startswith(f"{code_path}/{READER} names ")]
    assert named == (
        f"{code_path}/{READER} names `contracts/`, which moves to the spec "
        f"leg: it must read across the assembly root — `{expected}/"
        f"contracts/` relative to `{code_path}/` — or take the path from "
        "the environment")
    assert posixpath.normpath(posixpath.join(
        code_path, f"{expected}/contracts/")) == f"{spec_path}/contracts"
    # The Makefile follow-up names the key, so it is the same line for every
    # mount, and it names no path for a hand edit of the key to contradict.
    assert follow_ups.count(MAKEFILE_FOLLOW_UP) == 1, follow_ups
    assert not [item for item in follow_ups if "$(CURDIR)" in item]


# --- `execute`, end to end --------------------------------------------------

SPEC_PATH, CODE_PATH, ACROSS = "legs/spec", "impl/code", "../../legs/spec"


def adopt_with_legs_mounted_away(base: Path, *, by_hand: bool) -> dict:
    """One real adoption with both legs mounted away from their defaults, at
    SPEC_PATH and CODE_PATH, and a recursive clone of its split branch. Its
    own source: `execute` pushes the split branch into the repository it
    adopts.

    `by_hand` plans with the DEFAULT paths and then edits `legs.spec_path` and
    `legs.code_path` in the plan, as `MOUNT_REMEDIATION` and
    `plan-leg-path-collides` ask a person to. Otherwise `plan` is given them.
    """
    source = make_source_repo(base / "Thing", TREE, edits=EDITS)
    plan = base / "adoption-plan.yaml"
    follow_ups = planned_follow_ups(
        source, plan, *(("spec", "code") if by_hand else (SPEC_PATH, CODE_PATH)))
    if by_hand:
        text = plan.read_text(encoding="utf-8")
        edited = (text.replace("  spec_path: spec\n",
                               f"  spec_path: {SPEC_PATH}\n")
                      .replace("  code_path: code\n",
                               f"  code_path: {CODE_PATH}\n"))
        assert (f"  spec_path: {SPEC_PATH}\n" in edited
                and f"  code_path: {CODE_PATH}\n" in edited), text
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
    return {"source": source, "clone": clone, "follow_ups": follow_ups,
            "makefile": makefile}


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
def test_the_follow_ups_read_across_leads_to_the_contracts(adopted):
    """What the plan told the person to write in the code leg, followed from
    the code leg of a recursive clone, reaches the spec leg's file."""
    (named,) = [item for item in adopted["follow_ups"]
                if item.startswith(f"{CODE_PATH}/{READER} names ")]
    assert f"`{ACROSS}/contracts/` relative to `{CODE_PATH}/`" in named
    code_leg = adopted["clone"].joinpath(*CODE_PATH.split("/"))
    assert (code_leg / READER).is_file()
    target = code_leg.joinpath(*ACROSS.split("/"), "contracts", POLICY)
    assert target.resolve().is_file()
    assert target.resolve() == (adopted["clone"].joinpath(
        *SPEC_PATH.split("/"), "contracts", POLICY)).resolve()


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
