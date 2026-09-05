# SPDX-License-Identifier: Apache-2.0
"""A file the STANDARD ADDS after a project was cut from it, reaching it.

THE PIN CANNOT NAME WHAT DID NOT EXIST. `tests/test_update_shape.py` covers
the upstream FIX to a file the pin already carries a row for; this module
covers the other half, observed on 2026-09-04 when `AGENTS-shape.md` was added
to the assembly root and the family holder: a file named by the upstream's copy
lists and by no project's pin reaches nobody, because the file list is read
from the pin and a pin records the day it was written.

THE UPSTREAM IS A CLONE OF THIS REPOSITORY AND THE ADDITION IS A REAL COMMIT
IN IT. C1 is the clone's HEAD, the revision the project and the family holder
are scaffolded from; C2 adds two files to `templates/assembly-root/` and one to
`templates/family-root/` and names them in the copy lists, by editing the
clone's `scripts/shape_materialize.py` textually — which is exactly what a
pull request adding a template file does. Nothing here touches a network, and
the assertion that matters most is the one about C1: an older upstream that
never named these files must report NO addition at all, because the lists have
to be read at the TARGET commit rather than out of the checkout running the
command.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

import pytest

from conftest import FILE_PROTOCOL, ORG, REPO, git, run_script

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import file_sha256, load_yaml  # noqa: E402

UPDATE = REPO / "update-shape.py"
SCAFFOLD_ARGS = ("--elected-by", "Test Human", "--elected-on", "2026-09-02")
PROJECT = "Atlas"
FAMILY = "InkRouter"

#: What C2 adds to the ASSEMBLY ROOT's lists: one ordinary file, and one the
#: `EXECUTABLE` list names — the mode is part of what a materializer sets, so
#: it is part of what `--add` has to reproduce.
ADDED = "AGENTS-shape-test.md"
ADDED_SCRIPT = "scripts/new-check.py"
#: And to the FAMILY holder's, which is a DIFFERENT list. A project must not be
#: offered a family's addition, nor a family a project's.
FAMILY_ADDED = "FAMILY-shape-test.md"

MATERIALIZER = "scripts/shape_materialize.py"
#: An existing row, for the "--add what is already pinned" refusal.
PINNED = "scripts/bootstrap.py"


def commit_all(repo, message: str, paths: list[str]) -> str:
    git("add", "--", *paths, cwd=repo)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        message, "--", *paths, cwd=repo)
    return git("rev-parse", "HEAD", cwd=repo).stdout.strip()


def name_in_list(text: str, list_name: str, entry: str) -> str:
    """Add `entry` to `list_name` the way a pull request would: in the source.

    Anchored on the newline before the name so that `COPIED_VERBATIM` does not
    also match `FAMILY_COPIED_VERBATIM`, which is the whole reason the family
    has its own list.
    """
    opening = f"\n{list_name} = ("
    assert text.count(opening) == 1, f"{list_name} is not a tuple literal"
    return text.replace(opening, f'{opening}\n    "{entry}",', 1)


@pytest.fixture(scope="module")
def standard(tmp_path_factory) -> dict:
    """A clone at C1, a project and a family cut from it, and C2 above them."""
    base = tmp_path_factory.mktemp("shape-additions")
    upstream = base / "openRepoShape"
    proc = subprocess.run(["git", "clone", "-q", str(REPO), str(upstream)],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    c1 = git("rev-parse", "HEAD", cwd=upstream).stdout.strip()

    result = run_script(
        upstream / "scaffold-project.py", "--org", ORG, "--project", PROJECT,
        *SCAFFOLD_ARGS, "--local-remote-dir", str(base / "remotes"),
        "--work-dir", str(base / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    clone = base / "clone" / PROJECT
    proc = subprocess.run(
        ["git", *FILE_PROTOCOL, "clone", "-q", "--recurse-submodules",
         str(base / "remotes" / f"{PROJECT}.git"), str(clone)],
        capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr

    created = run_script(
        upstream / "scripts" / "family.py", "init", "--org", FAMILY,
        "--family", FAMILY, "--created-by", "Test Human",
        "--created-on", "2026-09-04",
        "--local-remote-dir", str(base / "remotes"),
        "--work-dir", str(base / "fam"))
    assert created.returncode == 0, created.stderr + created.stdout

    # ---- C2: the standard gains three files -------------------------------
    (upstream / "templates" / "assembly-root" / ADDED).write_text(
        "# The shape's own AGENTS file, added after these projects were cut.\n",
        encoding="utf-8")
    (upstream / "templates" / "assembly-root" / ADDED_SCRIPT).write_text(
        "#!/usr/bin/env python3\nprint('a new check')\n", encoding="utf-8")
    (upstream / "templates" / "family-root" / FAMILY_ADDED).write_text(
        "# The holder's copy of the same idea.\n", encoding="utf-8")
    source = upstream / MATERIALIZER
    text = source.read_text(encoding="utf-8")
    text = name_in_list(text, "COPIED_VERBATIM", ADDED)
    text = name_in_list(text, "COPIED_VERBATIM", ADDED_SCRIPT)
    text = name_in_list(text, "EXECUTABLE", ADDED_SCRIPT)
    text = name_in_list(text, "FAMILY_COPIED_VERBATIM", FAMILY_ADDED)
    source.write_text(text, encoding="utf-8")
    c2 = commit_all(upstream, "Add AGENTS-shape to both roots", [
        MATERIALIZER,
        f"templates/assembly-root/{ADDED}",
        f"templates/assembly-root/{ADDED_SCRIPT}",
        f"templates/family-root/{FAMILY_ADDED}",
    ])
    assert c1 != c2
    return {"upstream": upstream, "clone": clone, "family": base / "fam" / FAMILY,
            "c1": c1, "c2": c2}


@pytest.fixture
def root(standard, tmp_path):
    """A private, mutable copy of the project as it was cut at C1."""
    target = tmp_path / PROJECT
    shutil.copytree(standard["clone"], target, symlinks=True)
    return target


@pytest.fixture
def holder(standard, tmp_path):
    target = tmp_path / FAMILY
    shutil.copytree(standard["family"], target, symlinks=True)
    return target


def check(root, standard, *extra):
    return run_script(UPDATE, "check", "--root", str(root),
                      "--upstream", str(standard["upstream"]), *extra)


def apply(root, standard, *extra):
    return run_script(UPDATE, "apply", "--root", str(root), "--yes",
                      "--upstream", str(standard["upstream"]),
                      "--at", standard["c2"], *extra)


def pin(root) -> dict:
    return load_yaml(root / "contracts" / "shape-pin.yaml")


def pin_paths(root) -> list:
    return [row["path"] for row in pin(root)["files"]]


def pin_rows(root) -> dict:
    return {row["path"]: row["sha256"].lower() for row in pin(root)["files"]}


#: Every verdict `check` can print, in the column it prints them in. The
#: detail lines are parenthesised and carry no path, so they cannot be
#: mistaken for one.
STATES = ("unchanged", "upstream-changed", "upstream-added",
          "locally-modified", "both", "already-at-target", "upstream-removed",
          "unmapped", "copy-missing")


def verdicts(stdout: str) -> dict:
    """`{path: state}` out of the report."""
    out = {}
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] in STATES and line.startswith("  "):
            out[parts[1]] = parts[0]
    return out


# --- check -------------------------------------------------------------------

def test_check_reports_a_file_the_standard_added_as_upstream_added(
        root, standard):
    """The verdict is the product: a human sees the NAME of each new file, and
    `check` exits 1 because an addition is something to do."""
    result = check(root, standard, "--at", standard["c2"])
    assert result.returncode == 1, result.stdout + result.stderr
    verdict = verdicts(result.stdout)
    assert verdict[ADDED] == "upstream-added"
    assert verdict[ADDED_SCRIPT] == "upstream-added"
    pinned = {path: state for path, state in verdict.items()
              if path in pin_rows(root)}
    assert set(pinned.values()) == {"unchanged"}, pinned
    assert f"--add {ADDED}" in result.stdout, (
        "the flag is spelled out; a human names the file, so they need the "
        "spelling")
    assert FAMILY_ADDED not in result.stdout, (
        "a family's addition is named in the FAMILY list; offering it to a "
        "project would re-sync the wrong root's file"
    )
    assert not (root / ADDED).exists(), "`check` writes nothing"


def test_check_against_an_older_upstream_reports_no_addition(root, standard):
    """THE LISTS ARE READ AT THE TARGET COMMIT. C1 never named these files, so
    a project updating to C1 is owed nothing — an answer taken from the copy
    lists of the checkout RUNNING the command could not tell the difference."""
    result = check(root, standard, "--at", standard["c1"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "nothing to do" in result.stdout
    assert "upstream-added" not in result.stdout


def test_check_says_nothing_about_a_path_the_root_already_has(root, standard):
    """MedxEHR's posture, generalised: a file the root HAS and the pin does not
    record is the in-place adoption state, and nothing here may overwrite it.
    Reporting it every time would be noise ahead of a refusal."""
    (root / ADDED).write_text("# The project wrote its own.\n", encoding="utf-8")
    result = check(root, standard, "--at", standard["c2"])
    assert result.returncode == 1
    assert ADDED not in result.stdout
    assert ADDED_SCRIPT in result.stdout, "the other addition still reports"


# --- apply without --add -----------------------------------------------------

def test_apply_without_add_writes_no_new_file_and_says_so(root, standard):
    """Nothing lands in a project's tree because a tool decided it should. The
    pin still moves: the additions are a separate consent from the re-sync."""
    result = apply(root, standard)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (root / ADDED).exists()
    assert not (root / ADDED_SCRIPT).exists()
    assert f"not added; pass --add {ADDED}" in result.stdout
    assert f"not added; pass --add {ADDED_SCRIPT}" in result.stdout
    assert pin(root)["commit"].lower() == standard["c2"], (
        "the pin still moves onto the target; only the FILES wait for a name")
    assert ADDED not in pin_rows(root)
    validators_are_green(root)


# --- apply --add -------------------------------------------------------------

def test_add_copies_the_file_appends_its_row_and_stays_green(root, standard):
    """The five hand steps for a file that never existed here before: the
    bytes, the mode, a new `files:` row, and the project's own validator."""
    result = apply(root, standard, "--add", ADDED, "--add", ADDED_SCRIPT)
    assert result.returncode == 0, result.stdout + result.stderr
    for rel in (ADDED, ADDED_SCRIPT):
        expected = subprocess.run(
            ["git", "show",
             f"{standard['c2']}:templates/assembly-root/{rel}"],
            cwd=str(standard["upstream"]), capture_output=True,
            check=True).stdout
        assert (root / rel).read_bytes() == expected
        assert pin_rows(root)[rel] == file_sha256(root / rel)
    assert pin_paths(root)[-2:] == [ADDED, ADDED_SCRIPT], (
        "an addition is appended, so the rows the scaffold wrote keep their "
        "order and the new one reads as what it is")
    assert os.access(root / ADDED_SCRIPT, os.X_OK), (
        "the materializer chmods what `EXECUTABLE` names, and so must this")
    assert not (root / ADDED).stat().st_mode & 0o111, (
        "and only what it names")
    assert pin(root)["commit"].lower() == standard["c2"]
    assert f"add -- {ADDED} {ADDED_SCRIPT} &&" in result.stdout, (
        "the NEXT hint has to work when a human pastes it, and `git commit -- "
        "<path>` refuses a path git has never heard of")
    validators_are_green(root)


def test_add_on_a_branch_commits_the_new_file_too(root, standard):
    """Explicit pathspecs, so the added file has to be IN the list."""
    result = apply(root, standard, "--add", ADDED,
                   "--branch", "shape/add-test")
    assert result.returncode == 0, result.stdout + result.stderr
    committed = set(git("show", "--name-only", "--format=", "HEAD",
                        cwd=root).stdout.split())
    assert committed == {ADDED, "contracts/shape-pin.yaml", "project.yaml"}


# --- the three refusals ------------------------------------------------------

def test_add_of_an_already_pinned_path_refuses(root, standard):
    result = apply(root, standard, "--add", PINNED)
    assert result.returncode == 2, result.stdout
    assert "update-add-already-pinned" in result.stderr
    assert PINNED in result.stderr
    assert pin(root)["commit"].lower() == standard["c1"], (
        "a refused apply writes nothing at all")


def test_add_of_a_path_the_upstream_does_not_name_refuses(root, standard):
    """Including a path the upstream DOES name — for the other kind of root."""
    for path in ("no-such-file.md", FAMILY_ADDED):
        result = apply(root, standard, "--add", path)
        assert result.returncode == 2, result.stdout
        assert "update-add-not-upstream" in result.stderr
        assert path in result.stderr
    assert pin(root)["commit"].lower() == standard["c1"]


def test_add_refuses_to_overwrite_a_file_the_root_already_has(root, standard):
    """The `--accept-local` posture, for the same reason: two files with one
    name is a merge, and this command copies bytes."""
    own = "# The project wrote its own AGENTS-shape.\n"
    (root / ADDED).write_text(own, encoding="utf-8")
    result = apply(root, standard, "--add", ADDED)
    assert result.returncode == 2, result.stdout
    assert "update-add-would-overwrite" in result.stderr
    assert ADDED in result.stderr
    assert (root / ADDED).read_text(encoding="utf-8") == own
    assert pin(root)["commit"].lower() == standard["c1"]
    assert ADDED not in pin_rows(root)


def test_a_red_validator_rolls_the_added_file_back_out(root, standard):
    """The addition is inside the SAME transaction as the re-pin. A file
    written and then left behind by a rolled-back apply would be a copy no pin
    row records — the state this tool refuses to create on purpose."""
    spec = root / "contracts" / "spec-pin.yaml"
    spec.write_text(spec.read_text(encoding="utf-8")
                    .replace('commit: "', 'commit: "' + "0" * 40 + '" # ', 1),
                    encoding="utf-8")
    assert run_script(root / "scripts" / "validate-pins.py",
                      cwd=root).returncode != 0, "fixture: the leg pin is red"
    result = apply(root, standard, "--add", ADDED)
    assert result.returncode == 2, result.stdout
    assert "update-validators-red" in result.stderr
    assert not (root / ADDED).exists(), "every byte, including the new file"
    assert pin(root)["commit"].lower() == standard["c1"]


# --- the family holder -------------------------------------------------------

def test_a_family_holder_takes_its_own_addition(holder, standard):
    """The holder carries the same copy pin, so it is offered the FAMILY list's
    addition and no other, and is green against `validate-family.py`."""
    checked = run_script(UPDATE, "check", "--root", str(holder), "--upstream",
                         str(standard["upstream"]), "--at", standard["c2"])
    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert verdicts(checked.stdout)[FAMILY_ADDED] == "upstream-added"
    assert ADDED not in checked.stdout and ADDED_SCRIPT not in checked.stdout

    result = run_script(UPDATE, "apply", "--root", str(holder), "--yes",
                        "--upstream", str(standard["upstream"]),
                        "--at", standard["c2"], "--add", FAMILY_ADDED,
                        "--branch", "shape/add-test")
    assert result.returncode == 0, result.stdout + result.stderr
    expected = subprocess.run(
        ["git", "show",
         f"{standard['c2']}:templates/family-root/{FAMILY_ADDED}"],
        cwd=str(standard["upstream"]), capture_output=True, check=True).stdout
    assert (holder / FAMILY_ADDED).read_bytes() == expected
    assert pin_rows(holder)[FAMILY_ADDED] == file_sha256(holder / FAMILY_ADDED)
    assert pin(holder)["commit"].lower() == standard["c2"]
    assert load_yaml(holder / "family.yaml")["shape"]["commit"].lower() \
        == standard["c2"]
    green = run_script(holder / "scripts" / "validate-family.py", cwd=holder)
    assert green.returncode == 0, green.stdout + green.stderr
    # A family root has no `project.yaml`; the commit that mirrors the pin
    # must name the manifest this holder actually carries.
    message = git("log", "-1", "--format=%B", cwd=holder).stdout
    assert "family.yaml" in message
    assert "project.yaml" not in message


def validators_are_green(root) -> None:
    for script in ("scripts/validate-pins.py", "scripts/validate-manifest.py",
                   "scripts/bootstrap.py"):
        result = run_script(root / script, cwd=root)
        assert result.returncode == 0, (
            f"{script} is red after the update:\n{result.stdout}{result.stderr}")
