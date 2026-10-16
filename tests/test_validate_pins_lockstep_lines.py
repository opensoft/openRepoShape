# SPDX-License-Identifier: Apache-2.0
"""`validate-pins.py`: THE LOCKSTEP RULE only where it applies, and the
`bump-leg.py` lines a pin's digest and a workflow reference end on (#539).

THE COUNT. The report ended `<n> finding(s).` and THE LOCKSTEP RULE whatever
was found, so a lone `shape-copy-drift`, an edited copy that `update-shape.py`
or a revert puts right, was followed by a rule about moving a gitlink, a pin
and the workflows together. The count ends at the rule only where a finding
the rule is about was found: a gitlink off its pin, a pin's digest, or a
workflow reference.

TWO FINDINGS NAMED NO COMMAND. `pin-digest-mismatch` and
`pin-workflow-ref-mismatch` ended at THE LOCKSTEP RULE, though `bump-leg.py
--to` the commit the gitlink and the pin name cures both: it recomputes the
digest from the leg's own objects and moves every reference to the leg's
repository, in one commit. Each now names its lines where one can commit,
by #478's rule for a gitlink: the root has this gate of its own, and every
finding is the leg's own. A digest names one line. A reference names two,
`--to` the gitlink's commit and `--to` its own, since an edit to it may have
been meant, and which commit stays is the person's call. Held back by
another finding, they say what comes first in #478's words.

ANOTHER LEG'S GITLINK IS NO FINDING TO CLEAR FIRST (#677). The spec
gitlink committed by hand beside the code leg's digest or a workflow
reference to it: a bump of either leg is rolled back over the other's
finding, so "First clear that finding" named a step no line could take.
Both findings name the step two gitlinks off their pins name, by hand, and
once it is committed the code leg's line is named and cures the root. A
finding no bump clears is still the one to clear first. The step puts the
leg's workflow references back with its gitlink, an undo is followed by
`git submodule update`, and where the leg's own digest is wrong too, which
the step leaves, no line is promised (#702's review, S15 and S18).

EVERY LINE HERE IS RUN AS PRINTED, from the standard's checkout, split as a
POSIX shell splits it (the gate's lines are POSIX-quoted, #532), over a root
under a directory whose name holds a blank and an apostrophe; the doctor
then says COMPLIANT.

The fixtures are `tests/test_shape_doctor.py`'s and
`tests/test_doctor_gitlink_repairs.py`'s, imported, so this module has its
own scaffold and its own remotes, and the push `advanced` makes moves no
other module's.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

import pytest

from conftest import FILE_PROTOCOL, git, run_script
from repo_shape import PYTHON
from test_doctor_gitlink_repairs import (  # noqa: F401
    ANOTHER_LEG, OTHER_SHA, WORKING, advanced, assert_compliant,
    both_digests, copy_drifted, digest_moved, moved_by_hand, path_moved,
    pin_of, put_back, under_an_awkward_name, workflow_at,
)
from test_shape_doctor import (  # noqa: F401
    GIT_IDENTITY, PROJECT, project, scaffolded_here, standard,
)

#: How THE LOCKSTEP RULE starts, wherever the gate prints it.
RULE = "THE LOCKSTEP RULE: a leg's gitlink, its `contracts/<role>-pin.yaml` "

#: What a `bump-leg.py` line needs to commit, as every gate line says it.
COMMITS = ("on a branch other than the tracking branch, once this validator "
           "and validate-manifest.py pass on its rewrite (it rolls the bump "
           "back when either is red), and refuses a commit no branch of the "
           "leg's remote contains")


def gate(root: Path) -> subprocess.CompletedProcess:
    """The root's own `validate-pins.py`, run in the root."""
    return run_script(root / "scripts" / "validate-pins.py", cwd=root)


def block(stderr: str, code: str) -> list[str]:
    """The one finding `code` in the gate's report: its `FINDING` line and
    every indented line under it."""
    lines = stderr.splitlines()
    starts = [at for at, line in enumerate(lines)
              if line.startswith(f"FINDING {code}: ")]
    assert len(starts) == 1, stderr
    found = [lines[starts[0]]]
    for line in lines[starts[0] + 1:]:
        if not line.startswith(" "):
            break
        found.append(line)
    return found


def count_line(stderr: str) -> str:
    """The line the gate's report ends on."""
    return stderr.rstrip("\n").splitlines()[-1]


def bump_of(root: Path, role: str = "spec") -> str:
    """A gate line for `role`, up to its `--to`."""
    return (f"{PYTHON} scripts/bump-leg.py --root {shlex.quote(str(root))} "
            f"--leg {role} --to")


def on_a_branch(project: Path, tmp_path: Path, change) -> Path:
    """The root under an awkward name, on a branch (`bump-leg.py` refuses
    the tracking branch), with `change(root)` committed there: a clean root,
    which is what `bump-leg.py` asks for."""
    root = under_an_awkward_name(project, tmp_path)
    git("checkout", "-q", "-b", WORKING, cwd=root)
    change(root)
    git("add", "-A", "--", ".", cwd=root)
    git("commit", "-qm", "the change under test", cwd=root)
    return root


def run_from_the_standard(standard: Path, line: str) -> None:
    """Run a gate line exactly as printed, from the standard's checkout,
    as a POSIX shell splits it; and require exit 0."""
    argv = shlex.split(line)
    assert argv[:2] == [PYTHON, "scripts/bump-leg.py"], line
    ran = subprocess.run(argv, cwd=str(standard), capture_output=True,
                         text=True, encoding="utf-8", errors="replace",
                         check=False, stdin=subprocess.DEVNULL,
                         env={**os.environ, **GIT_IDENTITY,
                              "PYTHONDONTWRITEBYTECODE": "1"})
    assert ran.returncode == 0, line + "\n" + ran.stdout + ran.stderr


def gitlink_moved(root: Path) -> None:
    """The spec leg one empty commit past its pin, and that commit staged
    as its gitlink: `pin-gitlink-mismatch`, with no refusal beside it."""
    leg = root / "spec"
    git("commit", "-q", "--allow-empty", "-m", "past the pin", cwd=leg)
    moved = git("rev-parse", "HEAD", cwd=leg).stdout.strip()
    git("update-index", "--cacheinfo", f"160000,{moved},spec", cwd=root)


# --- the count ends at the rule only where it applies ------------------------

#: A finding the rule is not about, alone, and how to make it.
NOT_THE_RULES = {
    "shape-copy-drift": copy_drifted,
    "pin-path-mismatch": path_moved,
    "shape-copy-missing": lambda root: (root / "Makefile").unlink(),
}


@pytest.mark.parametrize("code", sorted(NOT_THE_RULES))
def test_a_finding_the_rule_is_not_about_ends_on_the_count_alone(project,
                                                                  code):
    """The issue's case, a lone `shape-copy-drift`, and two more findings
    no leg moved alone: the count, and no word of THE LOCKSTEP RULE."""
    root = project.resolve()
    NOT_THE_RULES[code](root)
    result = gate(root)
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stderr.count("FINDING ") == 1, result.stderr
    assert f"FINDING {code}: " in result.stderr
    assert "LOCKSTEP RULE" not in result.stdout + result.stderr
    assert count_line(result.stderr) == "1 finding(s)."


#: A finding the rule IS about, and how to make it.
THE_RULES = {
    "pin-gitlink-mismatch": gitlink_moved,
    "pin-digest-mismatch": digest_moved,
    "pin-workflow-ref-mismatch": workflow_at("spec", OTHER_SHA),
}


@pytest.mark.parametrize("code", sorted(THE_RULES))
def test_the_count_ends_at_the_rule_where_the_rule_applies(project, code):
    """Each of the three, beside a `shape-copy-drift`: the count still ends
    at the rule, because one of its findings is there."""
    root = project.resolve()
    THE_RULES[code](root)
    copy_drifted(root)
    result = gate(root)
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"FINDING {code}: " in result.stderr
    assert count_line(result.stderr).startswith("2 finding(s). " + RULE)


# --- a lone digest names one line, and the line cures it ---------------------

def test_a_lone_digest_names_its_line_and_the_line_cures_it(standard, project,
                                                            tmp_path):
    """`--to` the commit the gitlink and the pin already name: run as
    printed, it writes ONE commit, the recomputed digest, and the doctor
    says COMPLIANT."""
    root = on_a_branch(project, tmp_path, digest_moved)
    pinned = pin_of(root)
    base = git("rev-parse", "HEAD", cwd=root).stdout.strip()
    result = gate(root)
    assert result.returncode == 1, result.stdout + result.stderr
    lines = block(result.stderr, "pin-digest-mismatch")
    assert lines[3].startswith("  " + RULE), lines
    assert lines[4:] == [
        "  From a checkout of openRepoShape, this recomputes the digest at "
        f"{pinned[:12]}, the commit the gitlink and the pin already name, "
        "from the leg's own objects and writes it into the pin; run it with "
        f"`--dry-run` first. It commits {COMMITS}, so push that commit from "
        "the leg first if no branch holds it:",
        f"    {bump_of(root)} {pinned}"], lines
    assert count_line(result.stderr).startswith("1 finding(s). " + RULE)
    run_from_the_standard(standard, lines[5])
    assert git("rev-list", "--count", f"{base}..HEAD",
               cwd=root).stdout.strip() == "1"
    assert pin_of(root) == pinned
    assert gate(root).returncode == 0
    assert_compliant(standard, root)


# --- a lone reference names two lines, and either cures it -------------------

@pytest.mark.parametrize("which", ["keep", "take"])
def test_a_lone_reference_names_two_lines_and_either_cures_it(
        standard, project, advanced, tmp_path, which):
    """A workflow naming the spec leg at a commit its remote has, while the
    gitlink and the pin agree on another: `keep` puts the reference back at
    theirs, `take` moves the gitlink and the pin to the reference's. Either,
    run as printed, writes ONE commit putting all three at its commit."""
    root = on_a_branch(project, tmp_path, workflow_at("spec", advanced))
    pinned = pin_of(root)
    base = git("rev-parse", "HEAD", cwd=root).stdout.strip()
    result = gate(root)
    assert result.returncode == 1, result.stdout + result.stderr
    lines = block(result.stderr, "pin-workflow-ref-mismatch")
    assert lines[0] == (
        f"FINDING pin-workflow-ref-mismatch: legs.yml: `testorg/{PROJECT}-spec"
        f"@{advanced}` != the gitlink {pinned} recorded at 'spec'"), lines
    assert lines[1].startswith("  " + RULE), lines
    assert lines[2:] == [
        "  Which commit stays is the person's call. From a checkout of "
        "openRepoShape, the first command keeps the commit the gitlink and "
        "the pin name and moves every reference to the leg's repository to "
        "it, and the second moves the gitlink and the pin to this "
        "reference's; run either with `--dry-run` first. Either puts all "
        f"three at it in one commit, {COMMITS}, so push one made in the leg "
        "first:",
        f"    {bump_of(root)} {pinned}",
        f"    {bump_of(root)} {advanced}"], lines
    want = pinned if which == "keep" else advanced
    run_from_the_standard(standard, lines[3 if which == "keep" else 4])
    assert git("rev-list", "--count", f"{base}..HEAD",
               cwd=root).stdout.strip() == "1"
    assert git("rev-parse", "HEAD:spec", cwd=root).stdout.strip() == want
    assert pin_of(root) == want
    workflow = (root / ".github" / "workflows" / "legs.yml").read_text(
        encoding="utf-8")
    assert f"@{want}\n" in workflow, workflow
    assert_compliant(standard, root)


# --- named only where a line can commit --------------------------------------

#: A lone finding a bump of its leg clears, how to make it, and how the
#: held-back sentence names what the gate names once it is alone.
HELD = {
    "pin-digest-mismatch": (digest_moved, "the bump-leg.py line"),
    "pin-workflow-ref-mismatch": (workflow_at("spec", OTHER_SHA),
                                  "the two bump-leg.py lines"),
}


@pytest.mark.parametrize("code", sorted(HELD))
def test_another_finding_holds_the_lines_back_and_says_what_comes_first(
        project, code):
    """`bump-leg.py` runs this whole gate before it commits and rolls the
    bump back when it is red, so beside a finding no bump clears the gate
    names no line, says to clear that first, as a held-back gitlink says it
    (#478), and once that is done names the lines."""
    root = project.resolve()
    make, named = HELD[code]
    make(root)
    copy_drifted(root)
    result = gate(root)
    assert result.returncode == 1, result.stdout + result.stderr
    assert block(result.stderr, code)[-1] == (
        "  No single bump-leg.py line can commit while this validator also "
        "reports shape-copy-drift: bump-leg.py moves one leg and runs this "
        "validator before it commits, rolling the bump back when it is red. "
        f"First clear that finding; this validator then names {named} for "
        "that leg.")
    assert "scripts/bump-leg.py" not in result.stderr, result.stderr
    git("checkout", "--", "scripts/bootstrap.py", cwd=root)
    cleared = gate(root)
    assert cleared.returncode == 1, cleared.stdout + cleared.stderr
    assert block(cleared.stderr, code)[-1] == f"    {bump_of(root)} " + (
        pin_of(root) if code == "pin-digest-mismatch" else OTHER_SHA)


def test_another_leg_out_of_step_names_no_line(project):
    """The spec leg's digest and a workflow reference to the code leg: a
    bump of either leg leaves the other's finding red, so no line commits,
    and neither finding names one or a first step the other's would
    contradict. Each ends at THE LOCKSTEP RULE, as before."""
    root = project.resolve()
    digest_moved(root)
    workflow_at("code", OTHER_SHA)(root)
    result = gate(root)
    assert result.returncode == 1, result.stdout + result.stderr
    for code in ("pin-digest-mismatch", "pin-workflow-ref-mismatch"):
        assert block(result.stderr, code)[-1].startswith("  " + RULE)
    assert "bump-leg.py" not in result.stderr, result.stderr


# --- another leg's gitlink is put back by hand first (#677) ------------------

def held(what: str, first: str, then: str) -> str:
    """The last line of a held-back finding, in the gate's words (#478):
    what holds the line back, what comes first, and what follows."""
    return (f"  No single bump-leg.py line can commit while {what}: "
            "bump-leg.py moves one leg and runs this validator before it "
            f"commits, rolling the bump back when it is red. First {first}; "
            f"this validator then {then}")


#: What comes first where the spec gitlink holds back another leg's line:
#: its workflow references go back with it, and an undo is followed by the
#: leg checked out again (#702).
PUT_SPEC_BACK = ("put spec's gitlink back at its pin (check that leg out at "
                 "the pin's commit and commit its gitlink in this root, with "
                 "every workflow reference to its repository at that commit "
                 "too), or undo the commit that moved it and run `git "
                 "submodule update -- spec` in this root")

#: The code digest's finding, where the spec pin has one too.
CODE_DIGEST = "pin-digest-mismatch: contracts/code-pin.yaml"


def code_named(lines: str, advanced: str) -> str:
    """What the spec gitlink's finding says follows the step: the code
    leg's `lines`, and how the spec move is kept if it was meant (#702)."""
    return (f"names {lines} for code, and if spec's move was meant, bumping "
            f"spec to {advanced[:12]} after that line keeps it.")


@pytest.mark.parametrize("code", sorted(ANOTHER_LEG))
def test_another_legs_finding_and_the_gitlink_name_the_hand_step(
        standard, project, advanced, tmp_path, code):
    """The spec gitlink committed by hand, and the code leg's digest or a
    workflow reference to it: each finding names the spec gitlink put back
    by hand, neither says to clear the other first, and no line is named.
    The code finding names its own lines for code, by name (#702).
    Once that is committed the code leg's line is named, and run as printed
    it makes the root COMPLIANT."""
    moved = moved_by_hand(project, tmp_path, {"spec": advanced},
                          ANOTHER_LEG[code])
    root = moved["root"]
    result = gate(root)
    assert result.returncode == 1, result.stdout + result.stderr
    assert block(result.stderr, "pin-gitlink-mismatch")[-1] == held(
        f"code is out of step too ({code})", PUT_SPEC_BACK, code_named(
            "the bump-leg.py line" if code == "pin-digest-mismatch"
            else "the bump-leg.py lines", advanced))
    assert block(result.stderr, code)[-1] == held(
        "spec is off its pin", PUT_SPEC_BACK, f"names {HELD[code][1]} for "
        "code.")
    assert "First clear" not in result.stderr, result.stderr
    assert "scripts/bump-leg.py" not in result.stderr, result.stderr
    put_back(root, "spec", moved["pins"]["spec"])
    cleared = gate(root)
    assert cleared.returncode == 1, cleared.stdout + cleared.stderr
    line = f"    {bump_of(root, 'code')} {pin_of(root, 'code')}"
    assert line in block(cleared.stderr, code), cleared.stderr
    run_from_the_standard(standard, line.strip())
    assert_compliant(standard, root)


def test_a_finding_no_bump_clears_is_still_cleared_first(project, advanced,
                                                         tmp_path):
    """The control: beside the code leg's digest, a `shape-copy-drift`,
    which no bump clears, is still the finding to clear first, and the
    spec gitlink is put back beside it."""
    def both(root: Path) -> None:
        ANOTHER_LEG["pin-digest-mismatch"](root)
        copy_drifted(root)

    root = moved_by_hand(project, tmp_path, {"spec": advanced}, both)["root"]
    result = gate(root)
    assert result.returncode == 1, result.stdout + result.stderr
    also = " and this validator also reports shape-copy-drift"
    first = "clear that finding, and " + PUT_SPEC_BACK
    assert block(result.stderr, "pin-gitlink-mismatch")[-1] == held(
        "code is out of step too (pin-digest-mismatch)" + also, first,
        code_named("the bump-leg.py line", advanced))
    assert block(result.stderr, "pin-digest-mismatch")[-1] == held(
        "spec is off its pin" + also, first,
        "names the bump-leg.py line for code.")


def test_the_legs_own_digest_promises_no_line(project, advanced, tmp_path):
    """#702's S15: the spec gitlink committed by hand, and both pins'
    digests written wrong. The spec digest is recomputed at its pin's
    commit, so it outlasts the gitlink put back: both findings name the
    step and promise no line, and after it the gate names none."""
    moved = moved_by_hand(project, tmp_path, {"spec": advanced},
                          both_digests)
    root = moved["root"]
    result = gate(root)
    assert result.returncode == 1, result.stdout + result.stderr
    none = "names no line while spec's own pin-digest-mismatch stands."
    assert block(result.stderr, "pin-gitlink-mismatch")[-1] == held(
        "code is out of step too (pin-digest-mismatch)", PUT_SPEC_BACK, none)
    assert block(result.stderr, CODE_DIGEST)[-1] == held(
        "spec is off its pin", PUT_SPEC_BACK, none)
    put_back(root, "spec", moved["pins"]["spec"])
    after = gate(root)
    assert after.returncode == 1, after.stdout + after.stderr
    assert "bump-leg.py" not in after.stderr, after.stderr


def undo_the_move(root: Path, moved: dict) -> None:
    """The other route: the commit that moved the spec leg reverted, and
    the leg checked out at the gitlink that restores (#702)."""
    git("revert", "--no-edit", moved["base"], cwd=root)
    git(*FILE_PROTOCOL, "submodule", "update", "--", "spec", cwd=root)


#: The two routes the step names, each as it is taken by hand.
ROUTES = {
    "put back": lambda root, moved: put_back(
        root, "spec", moved["pins"]["spec"],
        workflow_at("spec", moved["pins"]["spec"])),
    "undo": undo_the_move,
}


@pytest.mark.parametrize("route", sorted(ROUTES))
def test_a_reference_moved_with_the_gitlink_goes_back_with_it(
        standard, project, advanced, tmp_path, route):
    """#702's S18: the spec gitlink and a workflow reference to the spec
    leg moved together by hand, then the code pin's digest written wrong.
    The reference agrees with the gitlink, so the gate does not report it,
    and the step names it. Taken either way, the gate then names the code
    leg's line; run as printed, and then the spec bump the gitlink's
    finding offers for a move that was meant, the root is COMPLIANT."""
    moved = moved_by_hand(project, tmp_path, {"spec": advanced},
                          workflow_at("spec", advanced))
    root = moved["root"]
    digest_moved(root, "code")
    git("commit", "-qam", "the code digest, by hand", cwd=root)
    result = gate(root)
    assert result.returncode == 1, result.stdout + result.stderr
    assert block(result.stderr, "pin-gitlink-mismatch")[-1] == held(
        "code is out of step too (pin-digest-mismatch)", PUT_SPEC_BACK,
        code_named("the bump-leg.py line", advanced))
    ROUTES[route](root, moved)
    cleared = gate(root)
    assert cleared.returncode == 1, cleared.stdout + cleared.stderr
    line = f"    {bump_of(root, 'code')} {pin_of(root, 'code')}"
    assert block(cleared.stderr, "pin-digest-mismatch")[-1] == line
    run_from_the_standard(standard, line.strip())
    run_from_the_standard(standard, f"{bump_of(root)} {advanced}")
    assert_compliant(standard, root)


@pytest.mark.parametrize("code", ["pin-digest-mismatch",
                                  "pin-workflow-ref-mismatch"])
def test_beside_its_legs_gitlink_it_points_at_the_gitlinks_lines(
        project, advanced, tmp_path, code):
    """The spec gitlink committed by hand, and the spec pin's digest written
    wrong or a reference to the spec leg left at the pin: the gitlink's two
    lines clear this finding too (#478 runs them), so it says so and names
    no line of its own."""
    pinned = pin_of(project)
    also = (digest_moved if code == "pin-digest-mismatch"
            else workflow_at("spec", pinned))
    root = moved_by_hand(project, tmp_path, {"spec": advanced}, also)["root"]
    result = gate(root)
    assert result.returncode == 1, result.stdout + result.stderr
    assert block(result.stderr, code)[-1] == (
        "  Either bump-leg.py line under spec's pin-gitlink-mismatch above "
        "clears this finding too.")
    lines = result.stderr.splitlines()
    assert len([line for line in lines if "scripts/bump-leg.py" in line]) == 2


def test_a_root_without_its_own_gate_is_told_no_line(standard, project):
    """`bump-leg.py` runs the root's own `validate-pins.py` and skips an
    absent one, so the standard's template copy, run over a root that has
    none, cannot say what the bump's run will: the digest ends at THE
    LOCKSTEP RULE, as a gitlink does there (#478)."""
    root = project.resolve()
    digest_moved(root)
    (root / "scripts" / "validate-pins.py").unlink()
    template = run_script(
        standard / "templates" / "assembly-root" / "scripts" /
        "validate-pins.py", "--root", str(root), cwd=root,
        env={"PYTHONPATH": str(standard / "scripts")})
    assert template.returncode == 1, template.stdout + template.stderr
    assert block(template.stderr, "pin-digest-mismatch")[-1].startswith(
        "  " + RULE)
    assert "bump-leg.py" not in template.stderr, template.stderr
