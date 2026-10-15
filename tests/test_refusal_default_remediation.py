# SPDX-License-Identifier: Apache-2.0
"""A refusal built without a remedy prints none, and the assembly root's
lockstep remedy is `validate-pins.py`'s alone (#370).

`repo_shape.Refusal` gave every refusal built without a remediation of its
own `repo_shape.REMEDIATION`: run `git submodule update --init --recursive`,
then `validate-pins.py`, and move a leg's gitlink, `contracts/<leg>-pin.yaml`
and its workflow `@<sha>` refs in one commit. That is an assembly root's
remedy for its legs, and it reached every tool. A family holder, which has no
legs and no `validate-pins.py`, was told to run that file and move a leg pin
by `family.py add` over a `.gitmodules` git cannot read, by its own
`validate-family.py` over a short member pin, and by `family.py bump` over a
`family.yaml` of the wrong kind; so was `update-shape.py` over a shape pin
with no `files:` rows, and the doctor put the same sentence in a row's NEXT.

NOW `repo_shape` assumes no remedy, and a refusal with none prints its
`REFUSED` line alone. `validate-pins.py`, whose remedy it is, prints
`REMEDIATION` under every refusal it makes that names no other, so its output
is byte for byte what it was. `family.py add` names an unreadable
`.gitmodules` as the holder's own gate does: `gitmodules-unreadable`, with
the gate's remedy and one step more, the `git add .gitmodules` that `add`
needs before it runs again (#407). `adopt-project.py`'s report of a late
failure, which left the lockstep remedy off by comparing against it, leaves an
absent one off too.

The family runs are offline, as in `test_family_add_refusals.py`, whose
fixtures they use: members in local bare repositories, and a `gh` that logs
and exits 97.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

from conftest import REPO, git, run_script
from test_family import (  # noqa: F401
    FAMILY, MEMBERS, SPARE, family, validate,
)
from test_family_add_refusals import (  # noqa: F401
    holder, offline, snapshot,
)

sys.path.insert(0, str(REPO / "scripts"))
import repo_shape  # noqa: E402
from repo_shape import (  # noqa: E402
    PYTHON, REMEDIATION, Refusal, git_out, load_yaml,
)

UPDATE = REPO / "update-shape.py"
DOCTOR = REPO / "shape-doctor.py"

#: The words of the remedy that is an assembly root's and no other's: the
#: file it says to run and the pin it says to move.
LOCKSTEP_WORDS = ("validate-pins.py", "<leg>-pin.yaml", "git submodule update")

#: A `.gitmodules` git refuses to read, as `test_family_add_refusals.py`
#: writes one for the holder's validator.
UNREADABLE_GITMODULES = b'[submodule "broken"\n'

#: How the gate's remedy for that file ends, and how `add`'s does: `add`
#: commits the file and refuses a copy nobody has staged (#407), so the
#: mended file is staged first, where the gate reads the work tree's copy.
RUN_AGAIN = " then run this again."
STAGE_THEN_RUN_AGAIN = " then `git add .gitmodules` and run this again."


def says_no_lockstep(text: str) -> None:
    for words in LOCKSTEP_WORDS:
        assert words not in text, text


# --- repo_shape ---------------------------------------------------------------


def test_a_refusal_built_without_a_remedy_prints_its_line_alone():
    """No remedy is assumed, so none is printed; one that is passed is."""
    bare = Refusal("some-code", "what went wrong")
    assert bare.remediation == ""
    assert str(bare) == "REFUSED some-code: what went wrong"
    named = Refusal("some-code", "what went wrong", "Remediation: do this.")
    assert str(named) == ("REFUSED some-code: what went wrong\n"
                          "Remediation: do this.")


def test_the_lockstep_remedy_keeps_its_name_and_its_words():
    """`REMEDIATION` is still the name, and still these words: the
    validators a root already has import it by that name (#370)."""
    assert REMEDIATION == (
        "Remediation: run `git submodule update --init --recursive`, then "
        f"`{PYTHON} scripts/validate-pins.py`. If the PIN itself is stale, "
        "advance the gitlink, `contracts/<leg>-pin.yaml` and every workflow "
        "`@<sha>` that names the leg in ONE commit (see README, 'The lockstep "
        "invariant').")


def test_the_shared_readers_assume_no_remedy(tmp_path):
    """`git_out` and `load_yaml` refuse for every tool, so they name no
    remedy that is one tool's; the not-UTF-8 refusal keeps its own."""
    git("init", "-q", cwd=tmp_path)
    with pytest.raises(Refusal) as failed:
        git_out(["rev-parse", "--verify", "no-such-revision"], cwd=tmp_path)
    assert failed.value.code == "git-failed"
    assert failed.value.remediation == ""
    unparsable = tmp_path / "unparsable.yaml"
    unparsable.write_bytes(b"kind: [unclosed\n")
    with pytest.raises(Refusal) as failed:
        load_yaml(unparsable)
    assert failed.value.code == "yaml-unparsable"
    assert str(failed.value) == f"REFUSED yaml-unparsable: {failed.value.detail}"
    not_utf8 = tmp_path / "latin1.yaml"
    not_utf8.write_bytes(b"name: caf\xe9\n")
    with pytest.raises(Refusal) as failed:
        load_yaml(not_utf8)
    assert failed.value.remediation.startswith(
        "Remediation: every YAML file this tool reads must be UTF-8.")


# --- the family holder ----------------------------------------------------------


@pytest.mark.parametrize("dry_run", [False, True], ids=["add", "add-dry-run"])
def test_add_names_an_unreadable_gitmodules_as_the_holders_gate_does(
        family, holder, offline, dry_run):
    """`add` over a `.gitmodules` git cannot read is refused as the holder's
    own `validate-family.py` refuses it: the same two lines, code and remedy,
    where it was `git-failed` under an assembly root's lockstep remedy. The
    remedy takes one step more, the stage `add` needs before it runs again
    (#407), and differs in nothing else."""
    (holder / ".gitmodules").write_bytes(UNREADABLE_GITMODULES)
    # No `git status` to ask: git cannot read the file for that either.
    before = snapshot(holder, status=False)
    added = offline.add(holder, SPARE, *(["--dry-run"] if dry_run else []),
                        remotes=family["remotes"])
    assert added.returncode == 2, added.stderr + added.stdout
    gate = validate(holder, "--no-members")
    assert gate.returncode == 2, gate.stderr + gate.stdout
    assert gate.stderr.startswith("REFUSED gitmodules-unreadable: ")
    *said, remedy = gate.stderr.splitlines()
    assert remedy.endswith(RUN_AGAIN), remedy
    assert added.stderr.splitlines() == [
        *said, remedy.replace(RUN_AGAIN, STAGE_THEN_RUN_AGAIN)]
    says_no_lockstep(added.stderr)
    assert snapshot(holder, status=False) == before
    offline.assert_left_nothing()


@pytest.mark.parametrize("copy", ["index", "HEAD"])
def test_add_says_which_copy_git_read_when_the_working_tree_has_none(
        family, holder, offline, copy):
    """With no `.gitmodules` in the working tree, `add` reads the index's
    copy, or HEAD's, as `git submodule add` does; when git cannot read that
    one, the remedy says to put it back before mending it."""
    (holder / ".gitmodules").write_bytes(UNREADABLE_GITMODULES)
    git("add", "--", ".gitmodules", cwd=holder)
    if copy == "HEAD":
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
            "an unreadable .gitmodules", "--", ".gitmodules", cwd=holder)
        git("rm", "-q", "--cached", "--", ".gitmodules", cwd=holder)
    (holder / ".gitmodules").unlink()
    added = offline.add(holder, SPARE, remotes=family["remotes"])
    assert added.returncode == 2, added.stderr + added.stdout
    # git's own words come between the two, on as many lines as git uses.
    lines = added.stderr.splitlines()
    assert lines[0].startswith(
        "REFUSED gitmodules-unreadable: .gitmodules could not be read as git "
        "reads it: `git config -z --blob "), added.stderr
    put_back = ("`git checkout -- .gitmodules`" if copy == "index"
                else "`git checkout HEAD -- .gitmodules`")
    assert lines[-1] == (
        "Remediation: git cannot read it either, so none of this holder's "
        "submodules can be cloned from it as it stands. Mend the file by hand "
        "(`git config -f .gitmodules --list` says where it breaks), then `git "
        "add .gitmodules` and run this again. With no .gitmodules in the "
        "working tree, git read "
        f"{'the index' if copy == 'index' else 'HEAD'}'s copy: put it back "
        f"first, {put_back}.")
    says_no_lockstep(added.stderr)
    offline.assert_left_nothing()


def test_the_holders_gate_refuses_a_short_member_pin_with_no_leg_remedy(
        holder):
    """The issue's second case: a member's `pin.commit` cut to 12 hex is
    `member-pin-commit`, and the line alone: a holder has no
    `validate-pins.py` and no leg pin to move."""
    text = (holder / "family.yaml").read_text(encoding="utf-8")
    # A member's, under `pin:`: the `shape:` block's comes first.
    short, count = re.subn(r'^(      commit: "[0-9a-f]{12})[0-9a-f]{28}"',
                           r'\1"', text, count=1, flags=re.M)
    assert count == 1, text
    (holder / "family.yaml").write_bytes(short.encode("utf-8"))
    gate = validate(holder)
    assert gate.returncode == 2, gate.stderr + gate.stdout
    assert gate.stderr.startswith("REFUSED member-pin-commit: ")
    assert gate.stderr.count("\n") == 1, gate.stderr
    says_no_lockstep(gate.stderr)


def test_bump_refuses_a_family_manifest_of_the_wrong_kind_with_no_leg_remedy(
        holder):
    """The issue's third case: `bump` over a `family.yaml` whose `kind:` is
    not `family-manifest` is `family-wrong-kind`, and the line alone."""
    text = (holder / "family.yaml").read_text(encoding="utf-8")
    assert "kind: family-manifest" in text
    (holder / "family.yaml").write_bytes(
        text.replace("kind: family-manifest", "kind: project-manifest")
        .encode("utf-8"))
    member = holder / "members" / MEMBERS[0]
    commit = git("rev-parse", "HEAD", cwd=member).stdout.strip()
    bumped = run_script(FAMILY, "bump", "--family-root", str(holder),
                        "--member", MEMBERS[0], "--to", commit)
    assert bumped.returncode == 2, bumped.stderr + bumped.stdout
    assert bumped.stderr.startswith("REFUSED family-wrong-kind: ")
    assert bumped.stderr.count("\n") == 1, bumped.stderr
    says_no_lockstep(bumped.stderr)


# --- the assembly root ----------------------------------------------------------


@pytest.mark.parametrize("files", ["0", "false", "~", "{}", "[]"])
def test_update_shape_refuses_a_pin_with_no_files_with_no_leg_remedy(
        project, files):
    """`read_pin`'s `update-pin-no-files` for each falsy `files:` (#370's
    comment): the line alone, where it printed the lockstep remedy."""
    pin = project / "contracts" / "shape-pin.yaml"
    text = pin.read_text(encoding="utf-8")
    at = text.index("\nfiles:")
    pin.write_bytes((text[:at] + f"\nfiles: {files}\n").encode("utf-8"))
    checked = run_script(UPDATE, "check", "--root", str(project),
                         "--upstream", str(REPO))
    assert checked.returncode == 2, checked.stderr + checked.stdout
    assert checked.stderr.startswith("REFUSED update-pin-no-files: ")
    assert checked.stderr.count("\n") == 1, checked.stderr
    says_no_lockstep(checked.stderr)


def _break_spec_pin(project: Path, how: str) -> str:
    """Break the spec leg's pin `how`, and return the `REFUSED` line
    `validate-pins.py` makes of it."""
    pin = project / "contracts" / "spec-pin.yaml"
    text = pin.read_text(encoding="utf-8")
    if how == "short-commit":
        match = re.search(r'^commit: "?([0-9a-f]{40})"?$', text, re.M)
        assert match, text
        short = match.group(1)[:12]
        pin.write_bytes(text.replace(match.group(0), f'commit: "{short}"')
                        .encode("utf-8"))
        return (f"REFUSED pin-tag-only: contracts/spec-pin.yaml: `commit:` is "
                f"'{short}', which is not 40 hex. An abbreviated oid, a "
                "branch or a tag is a moving reference.")
    pin.write_bytes(b"commit: [unclosed\n")
    return (f"REFUSED yaml-unparsable: {pin.resolve()}: not a flow "
            "collection: '[unclosed'")


@pytest.mark.parametrize("how", ["short-commit", "unparsable"])
def test_validate_pins_prints_the_lockstep_remedy_as_it_always_did(
        project, how):
    """The assembly root's own gate is the one place the lockstep remedy is
    the right one, and it prints it under each refusal that names no other:
    its own (`pin-tag-only`) and one `repo_shape` raises for it
    (`yaml-unparsable`), byte for byte what it printed before #370."""
    line = _break_spec_pin(project, how)
    checked = run_script(project / "scripts" / "validate-pins.py",
                         "--quiet", cwd=project)
    assert checked.returncode == 2, checked.stderr + checked.stdout
    assert checked.stderr.splitlines() == [line, REMEDIATION]


def test_validate_pins_prints_it_once_beside_a_repo_shape_that_still_defaults(
        project):
    """A root that takes the new `validate-pins.py` and keeps a
    `repo_shape.py` whose `Refusal` still defaults to `REMEDIATION` prints
    the remedy once, as both printed it before: the gate adds it only to a
    refusal that carries none."""
    shared = project / "scripts" / "repo_shape.py"
    text = shared.read_bytes().decode("utf-8")
    old, count = re.subn(
        r"(def __init__\(self, code: str, detail: str, remediation: str = )"
        r"[^)]*\)", r"\1REMEDIATION)", text, count=1)
    assert count == 1, "Refusal.__init__ is not where this test looks"
    shared.write_bytes(old.encode("utf-8"))
    line = _break_spec_pin(project, "short-commit")
    checked = run_script(project / "scripts" / "validate-pins.py",
                         "--quiet", cwd=project)
    assert checked.returncode == 2, checked.stderr + checked.stdout
    assert checked.stderr.splitlines() == [line, REMEDIATION]


# --- the doctor -----------------------------------------------------------------


def doctor_module():
    """`shape-doctor.py` as a module: the filename has a hyphen."""
    spec = importlib.util.spec_from_file_location("shape_doctor_370", DOCTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_doctor_row_refused_without_a_remedy_has_no_next(project):
    """A check that a `repo_shape` refusal ends becomes a FINDING whose NEXT
    is the refusal's remedy. One built without a remedy has no NEXT now,
    where the row printed the lockstep sentence as the thing to run."""
    doctor = doctor_module()

    def refused(ctx):
        repo_shape.git_out(["rev-parse", "--verify", "no-such-revision"],
                           cwd=ctx.root)

    doctor.CHECKS = (doctor.Check(
        "probe", "probe", (doctor.PROJECT, doctor.FAMILY, doctor.NOT_A_ROOT),
        refused),)
    rows = doctor.run_checks(doctor.Context(project.resolve()))
    assert [(row.id, row.status) for row in rows] == [("probe", doctor.FINDING)]
    assert rows[0].reason.startswith("refused: `git rev-parse --verify "), \
        rows[0].reason
    assert rows[0].next_command is None, rows[0].next_command


def test_a_late_adoption_failure_prints_no_empty_remedy_line():
    """`adopt-project.py` reports a failure once a leg repository exists as
    `REFUSED <step>. <code>: <detail>`, with the refusal's own remedy under
    it but never the lockstep one. A refusal with no remedy at all, which is
    what `git_out` raises now, is that line alone, not the line and an
    empty one."""
    spec = importlib.util.spec_from_file_location("adopt_370",
                                                  REPO / "adopt-project.py")
    adopter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adopter)
    step = "verifying the split"
    assert adopter._failed_loudly(step, adopter.Refusal(
        "git-failed", "`git ls-tree` exited 128")) == (
        "REFUSED verifying the split. git-failed: `git ls-tree` exited 128")
    assert adopter._failed_loudly(step, adopter.Refusal(
        "git-failed", "it failed", REMEDIATION)) == (
        "REFUSED verifying the split. git-failed: it failed")
    assert adopter._failed_loudly(step, adopter.Refusal(
        "some-code", "it failed", "Remediation: do this.")) == (
        "REFUSED verifying the split. some-code: it failed\n"
        "Remediation: do this.")


def test_the_doctors_refusal_line_is_whole_when_there_is_no_remedy():
    """`refusal_line` takes a remedy off the end of `str()`, and a refusal
    with none has none to take: its line is quoted whole, a trailing
    newline in the detail included."""
    doctor = doctor_module()
    assert doctor.refusal_line(Refusal("c", "d\n")) == "REFUSED c: d\n"
    assert doctor.refusal_line(
        Refusal("c", "d", "Remediation: x.")) == "REFUSED c: d"
