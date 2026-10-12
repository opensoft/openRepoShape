# SPDX-License-Identifier: Apache-2.0
"""A gitlink committed by hand: the `pins` row and `validate-pins.py` name
both repairs (#478).

THE DEFECT. `git -C spec pull`, then `git add spec && git commit` in the
root, is the most ordinary way a leg's gitlink leaves its pin. The doctor
said DRIFTED, its `pins` row was `FINDING pin-gitlink-mismatch` with the gate
as its NEXT, and the gate printed THE LOCKSTEP RULE and no command, though
AGENTS.md says a finding names its fix and lists `bump-leg.py` among them.

WHAT THEY SAY NOW. Two `bump-leg.py` lines, and which one to run is the
person's call: `--to` the gitlink's commit keeps the move, `--to` the pin's
undoes it. The doctor names them in the row's reason and in
`detail.gitlink_repairs`, spelled by `quote_arg` for the reader's shell; the
gate names the same two, from a checkout of openRepoShape. The row's NEXT is
still the gate.

EVERY REPAIR HERE IS RUN, from a directory that is not the root and through
the argv the reader's own shell makes of the printed line (`pasted`: `shlex`
on POSIX, PowerShell's reading on Windows), so these run on all three
systems. The root sits under a directory whose name holds a blank and an
apostrophe, so a line that is not quoted for its shell fails here.

NO NETWORK. The leg's new commit is pushed to a branch of its bare remote on
disk, which is what `bump-leg.py` asks of a commit it pins. The fixtures are
`tests/test_shape_doctor.py`'s, imported, so this module has its own scaffold
and its own remotes, and the push moves no other module's.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from conftest import FILE_PROTOCOL, REPO, git, run_script
from test_commit_trailers import LANE
from test_shape_doctor import (  # noqa: F401
    DOCTOR, DRIFT_TARGET, GIT_IDENTITY, PROJECT, doctor, doctor_module,
    pasted, project, rows_of, scaffolded_here, standard,
)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import PYTHON  # noqa: E402

#: The branch of the spec leg's remote the new commit is pushed to.
ADVANCE = "doctor-gitlink-advance"

#: The branch the root is on when the gitlink is committed by hand:
#: `bump-leg.py` refuses the tracking branch, and names this step itself.
WORKING = "take-the-new-spec"

#: A commit no repository here holds, for a workflow reference that is wrong.
OTHER_SHA = "0123456789abcdef0123456789abcdef01234567"


@pytest.fixture(scope="module")
def advanced(scaffolded_here, tmp_path_factory) -> str:
    """A new commit on a branch of the spec leg's remote, as a merged pull
    request leaves one; its sha."""
    work = tmp_path_factory.mktemp("spec-advance") / f"{PROJECT}-spec"
    remote = scaffolded_here["base"] / "remotes" / f"{PROJECT}-spec.git"
    proc = subprocess.run(["git", "clone", "-q", str(remote), str(work)],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    (work / "requirements").mkdir(exist_ok=True)
    (work / "requirements" / "r478.md").write_text("# R478\n",
                                                  encoding="utf-8")
    git("add", "--", "requirements/r478.md", cwd=work)
    git("commit", "-qm", "Add R478", cwd=work)
    git("push", "-q", "origin", f"HEAD:refs/heads/{ADVANCE}", cwd=work)
    return git("rev-parse", "HEAD", cwd=work).stdout.strip()


def pin_of(root: Path, role: str = "spec") -> str:
    text = (root / "contracts" / f"{role}-pin.yaml").read_text(
        encoding="utf-8")
    found = re.search(r'(?m)^commit: "([0-9a-f]{40})"$', text)
    assert found, text
    return found.group(1)


def under_an_awkward_name(project: Path, tmp_path: Path) -> Path:
    """The root moved under a directory whose name needs quoting in every
    shell: a blank, and an apostrophe."""
    root = tmp_path / "it's my work" / PROJECT
    root.parent.mkdir()
    shutil.move(str(project), str(root))
    return root.resolve()


@pytest.fixture
def hand_moved(project, advanced, tmp_path) -> dict:
    """The issue's reproduction: the leg fetched and checked out at the new
    commit, and the gitlink committed by hand in the root, on a branch."""
    root = under_an_awkward_name(project, tmp_path)
    pinned = pin_of(root)
    leg = root / "spec"
    git(*FILE_PROTOCOL, "fetch", "-q", "origin", ADVANCE, cwd=leg)
    git("checkout", "-q", "--detach", advanced, cwd=leg)
    git("checkout", "-q", "-b", WORKING, cwd=root)
    git("add", "--", "spec", cwd=root)
    git("commit", "-qm", "take the new spec", cwd=root)
    return {"root": root, "gitlink": advanced, "pin": pinned,
            "base": git("rev-parse", "HEAD", cwd=root).stdout.strip()}


def pins_row(standard: Path, root: Path, env: dict | None = None) -> dict:
    result = run_script(standard / DOCTOR, "--root", str(root), "--json",
                        env=env)
    assert result.returncode == 1, result.stdout + result.stderr
    return rows_of(result)["pins"]


def gate_row(standard: Path, root: Path) -> dict:
    """The row the gate alone makes of `root`, before #478's reason: the
    doctor's own `validator_row`, asked in this process."""
    module = doctor_module(standard)
    ctx = module.Context(root.resolve())
    return module.validator_row(ctx, "pins", "pins", *module.PINS_GATE,
                                ["--root", str(ctx.root)]).as_dict()


def bump_argv(standard: Path, root: Path, commit: str) -> list[str]:
    return [PYTHON, str(standard.resolve() / "scripts" / "bump-leg.py"),
            "--root", str(root), "--leg", "spec", "--to", commit]


# --- the doctor names both, and the gate is still its NEXT ------------------

@pytest.mark.parametrize("own_copy", [True, False])
def test_a_hand_committed_gitlink_names_both_bump_leg_commands(
        standard, hand_moved, own_copy):
    """`--to` the gitlink's commit and `--to` the pin's, each a line the
    reader's shell hands back whole, in the reason and in `detail`; and the
    NEXT is the gate, byte for byte. The template's copy of the gate, which
    a root without its own falls back to, names the same two."""
    root = hand_moved["root"]
    if not own_copy:
        (root / "scripts" / "validate-pins.py").unlink()
    gitlink, pinned = hand_moved["gitlink"], hand_moved["pin"]
    # The gitlink's commit AS GIT READS IT: the index's stage-0 entry, which
    # is what the gate compares and what `bump-leg.py` replaces.
    staged = git("ls-files", "--stage", "--", "spec", cwd=root).stdout.split()
    assert staged[:3] == ["160000", gitlink, "0"], staged
    row = pins_row(standard, root)
    gate = gate_row(standard, root)
    assert row["status"] == "FINDING", row
    assert row["detail"]["exit"] == 1, row
    repairs = row["detail"].get("gitlink_repairs")
    assert isinstance(repairs, list) and len(repairs) == 1, row["detail"]
    keep, back = repairs[0]["keep_gitlink"], repairs[0]["keep_pin"]
    assert pasted(keep) == bump_argv(standard, root, gitlink), keep
    assert pasted(back) == bump_argv(standard, root, pinned), back
    module = doctor_module(standard)
    assert repairs == [{
        "role": "spec", "path": "spec", "gitlink": gitlink, "pin": pinned,
        "keep_gitlink": module.bump_leg_command(standard.resolve(), root,
                                                "spec", gitlink),
        "keep_pin": module.bump_leg_command(standard.resolve(), root, "spec",
                                            pinned)}], repairs
    assert f"`{keep}` keeps the gitlink's {gitlink[:12]}" in row["reason"]
    assert f"`{back}` keeps the pin's {pinned[:12]}" in row["reason"]
    assert "the person's call" in row["reason"], row["reason"]
    assert "a branch other than main" in row["reason"], row["reason"]
    assert "no branch of the leg's remote contains" in row["reason"]
    # What the gate said is kept whole in front of it, and the NEXT and the
    # rest of `detail` are the gate's own.
    assert row["reason"].startswith(gate["reason"] + ". "), row["reason"]
    assert "pin-gitlink-mismatch" in gate["reason"], gate["reason"]
    assert row["next"] == gate["next"], row["next"]
    assert "bump-leg" not in row["next"], row["next"]
    assert {key: value for key, value in row["detail"].items()
            if key != "gitlink_repairs"} == gate["detail"]
    # And the table says what `--json` says.
    table = run_script(standard / DOCTOR, "--root", str(root))
    assert table.returncode == 1, table.stdout + table.stderr
    assert row["reason"] in table.stdout, table.stdout


def test_the_repairs_carry_the_lane_trailer_inside_a_lane(standard,
                                                          hand_moved):
    """Each line writes a commit, so it carries the lane's `--trailer`, as
    the `shape currency` row's `apply` does (#111); and none without one."""
    root = hand_moved["root"]
    plain = pins_row(standard, root, {"LANES_LANE": ""})
    lane = pins_row(standard, root, {"LANES_LANE": LANE})
    for key in ("keep_gitlink", "keep_pin"):
        without = plain["detail"]["gitlink_repairs"][0][key]
        within = lane["detail"]["gitlink_repairs"][0][key]
        assert "--trailer" not in without, without
        assert within == without + f" --trailer 'Lane: {LANE}'", within
        assert pasted(within)[-2:] == ["--trailer", f"Lane: {LANE}"]
        assert f"`{within}`" in lane["reason"], lane["reason"]


#: `bump_leg_command` for each shell, from either host: `platform` is passed
#: on to every value, as `copy_command`'s is, so the Windows line is asserted
#: on a POSIX runner too. A blank and an apostrophe in the root, so both
#: quotings are exercised: `sh` closes, escapes and reopens, PowerShell
#: doubles.
BUMP_LINES = {
    "posix": (PurePosixPath("/srv/my work/openRepoShape"),
              PurePosixPath("/srv/it's/Atlas"),
              "python3 '/srv/my work/openRepoShape/scripts/bump-leg.py' "
              "--root '/srv/it'\\''s/Atlas' --leg spec --to " + OTHER_SHA),
    "nt": (PureWindowsPath("C:/shape/openRepoShape"),
           PureWindowsPath("C:/Users/Jane O'Neill/Atlas"),
           "python C:\\shape\\openRepoShape\\scripts\\bump-leg.py "
           "--root 'C:\\Users\\Jane O''Neill\\Atlas' --leg spec --to "
           + OTHER_SHA),
}


@pytest.mark.parametrize("platform", sorted(BUMP_LINES))
def test_the_bump_line_is_spelled_for_each_shell(standard, monkeypatch,
                                                 platform):
    monkeypatch.delenv("LANES_LANE", raising=False)
    shape, root, line = BUMP_LINES[platform]
    module = doctor_module(standard)
    assert module.bump_leg_command(shape, root, "spec", OTHER_SHA,
                                   platform) == line


# --- the gate names the same two --------------------------------------------

def test_the_gate_names_the_same_two_commands(hand_moved):
    """The project's own `validate-pins.py`: still the finding and THE
    LOCKSTEP RULE, then the two lines, from a checkout of openRepoShape, with
    this root quoted as `validate-family.py` quotes a holder's."""
    root = hand_moved["root"]
    result = run_script(root / "scripts" / "validate-pins.py", cwd=root)
    assert result.returncode == 1, result.stdout + result.stderr
    lines = result.stderr.splitlines()
    first = lines.index(
        f"FINDING pin-gitlink-mismatch: spec: gitlink {hand_moved['gitlink']}"
        f" != contracts/spec-pin.yaml commit {hand_moved['pin']}")
    assert lines[first + 1].startswith("  THE LOCKSTEP RULE: "), lines
    assert lines[first + 2].startswith(
        "  Which commit stays is the person's call. From a checkout of "
        "openRepoShape,"), lines
    bump = (f"    {PYTHON} scripts/bump-leg.py --root "
            f"{shlex.quote(str(root))} --leg spec --to")
    assert lines[first + 3] == f"{bump} {hand_moved['gitlink']}", lines
    assert lines[first + 4] == f"{bump} {hand_moved['pin']}", lines


# --- running either one is the cure -----------------------------------------

@pytest.mark.parametrize("which", ["keep_gitlink", "keep_pin"])
def test_each_repair_run_as_printed_makes_the_doctor_compliant(
        standard, hand_moved, tmp_path, which):
    """Run from elsewhere exactly as the row printed it, each line writes ONE
    commit on the branch, puts the gitlink and the pin at its commit, and
    the doctor says COMPLIANT, exit 0."""
    root = hand_moved["root"]
    row = pins_row(standard, root)
    line = row["detail"]["gitlink_repairs"][0][which]
    want = hand_moved["gitlink" if which == "keep_gitlink" else "pin"]
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    ran = subprocess.run(pasted(line), cwd=str(elsewhere), capture_output=True,
                         text=True, encoding="utf-8", errors="replace",
                         check=False, stdin=subprocess.DEVNULL,
                         env={**os.environ, **GIT_IDENTITY,
                              "PYTHONDONTWRITEBYTECODE": "1"})
    assert ran.returncode == 0, line + "\n" + ran.stdout + ran.stderr
    count = git("rev-list", "--count", f"{hand_moved['base']}..HEAD",
                cwd=root).stdout.strip()
    assert count == "1", count
    assert git("rev-parse", "HEAD:spec", cwd=root).stdout.strip() == want
    assert pin_of(root) == want
    assert git("symbolic-ref", "--short", "HEAD",
               cwd=root).stdout.strip() == WORKING
    after = doctor(standard, root, "--json")
    assert after.returncode == 0, after.stdout + after.stderr
    rows = rows_of(after)
    assert rows["pins"]["status"] == "ok", rows["pins"]
    assert rows["legs"]["status"] == "ok", rows["legs"]
    assert json.loads(after.stdout)["verdict"] == "COMPLIANT", after.stdout


def test_git_submodule_update_is_no_undo(standard, hand_moved):
    """WHY THE UNDO IS `bump-leg.py --to <the pin>` AND NOT A GIT LINE,
    pinned by what git does: `submodule update --checkout` checks the leg out
    at the GITLINK, which is the commit being undone, so it leaves the leg
    where it is and the row where it was."""
    root = hand_moved["root"]
    git(*FILE_PROTOCOL, "submodule", "update", "--init", "--checkout", "--",
        "spec", cwd=root)
    assert git("rev-parse", "HEAD", cwd=root / "spec").stdout.strip() == \
        hand_moved["gitlink"]
    assert "gitlink_repairs" in pins_row(standard, root)["detail"]


# --- every other pins row is the gate's, untouched --------------------------

def edit(root: Path, relative: str, pattern: str, replacement: str) -> None:
    target = root / relative
    text = target.read_text(encoding="utf-8")
    edited, count = re.subn(pattern, replacement, text)
    assert count == 1, (relative, pattern)
    target.write_text(edited, encoding="utf-8")


def digest_moved(root: Path) -> None:
    edit(root, "contracts/spec-pin.yaml",
         r'(?m)^(  tree_sha256: ")[0-9a-f]{64}(")$', r"\g<1>" + "0" * 64 +
         r"\g<2>")


def path_moved(root: Path) -> None:
    edit(root, "contracts/spec-pin.yaml", r'(?m)^submodule_path: .*$',
         'submodule_path: "elsewhere"')


def workflow_off(root: Path) -> None:
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    (workflows / "legs.yml").write_text(
        "on: [pull_request]\njobs:\n  spec:\n    uses: "
        f"testorg/{PROJECT}-spec/.github/workflows/x.yml@{OTHER_SHA}\n",
        encoding="utf-8")


def copy_drifted(root: Path) -> None:
    target = root / DRIFT_TARGET
    target.write_text(target.read_text(encoding="utf-8") + "\n# edit\n",
                      encoding="utf-8")


def refused_with_the_gitlink_moved(root: Path) -> None:
    """A gitlink off its pin AND a gate that refuses before it reports it:
    the refusal is the thing to fix first, so no repair is named."""
    leg = root / "spec"
    git("commit", "-q", "--allow-empty", "-m", "past the pin", cwd=leg)
    moved = git("rev-parse", "HEAD", cwd=leg).stdout.strip()
    git("update-index", "--cacheinfo", f"160000,{moved},spec", cwd=root)
    (root / "code" / ".git").unlink()


OTHER_FINDINGS = {
    "pin-digest-mismatch": (digest_moved, 1),
    "pin-path-mismatch": (path_moved, 1),
    "pin-workflow-ref-mismatch": (workflow_off, 1),
    "shape-copy-drift": (copy_drifted, 1),
    "pin-submodule-uninitialized": (refused_with_the_gitlink_moved, 2),
}


@pytest.mark.parametrize("code", sorted(OTHER_FINDINGS))
def test_every_other_pins_row_is_the_gates_own(standard, project, code):
    """Byte for byte the row the gate alone makes, with no repair named:
    four findings a gitlink at its pin can have, and a refusal over a
    gitlink that is not."""
    root = project.resolve()
    make, exit_code = OTHER_FINDINGS[code]
    make(root)
    row = pins_row(standard, root)
    assert row["detail"]["exit"] == exit_code, row
    assert code in row["reason"], row["reason"]
    assert row == gate_row(standard, root)
    assert "gitlink_repairs" not in row["detail"], row["detail"]
    assert "bump-leg" not in row["reason"], row["reason"]
    gate = run_script(root / "scripts" / "validate-pins.py", cwd=root)
    assert "bump-leg.py" not in gate.stdout + gate.stderr
