# SPDX-License-Identifier: Apache-2.0
"""A doctor NEXT is the command and only the command (#277).

THE DEFECT. Twenty-nine of the doctor's NEXT builders ended the command with
`   # <comment>`, and one printed prose in the command's place. Sixteen were
there when this began (3ae0109). Doctor A (#276) then rewrote the `legs`
tail and added two more (`lockstep_next` and the `members` git line), doctor
B (#278, #298) added two (its crash line and its restore line), and lane 2's
#237 (#267) added five, which landed while this was in CI (`pin_restore`
four times and `unreadable_pin_row`). Lane 2's #291 then added four, which
landed while this waited to land: `pin_restore`'s three `git diff` lines
for a file a person may have edited, and `unreadable_next`'s line for one
no git command can put back. Lane 2's #496 rewrote the first of #267's,
which now takes the pin alone and gives a copy conflicted beside it to a
person. A tail was harmless in exactly the shells that read `#` as a
comment where a word starts -- `sh -c`, bash, `zsh -c` -- which is how
every test and every agent tool call had read one. An
INTERACTIVE zsh without `interactivecomments` -- zsh's default, and macOS's
login shell, the one a person pastes into -- reads `#` as a word. Pasted
there, the manifest NEXT handed `# read its output in full` to the
validator as arguments, ran `it names what it refused` as a second command
and exited 127; the `legs` and `members` NEXTs ran the `make bootstrap`
their comments put in backticks, in whatever directory the person was
standing in.

THE FIX IS A FIELD, NOT A SPELLING. Each sentence moved, verbatim, to the
row's `why` -- `"why"` in `--json`, a `WHY` line under `NEXT` in the table,
`Why:` after `Remediation:` -- and `next` is the bare command. So this file
holds three things, and the code before #277 fails each of them:

  * a PROPERTY over one fixture per converted builder and branch: the NEXT
    has no shell comment (`shlex` reads it the same with and without
    comments), no backtick, no `$(` that `sh` would run and, on POSIX, none
    of `;`, `&`, `|`, `(`, `)` outside a quotation (PowerShell's `$env:`
    line ends its assignment with a `;`, by design);
  * a PASTE into `zsh -f -i` through a pty, as a person pastes: the manifest
    NEXT is the validator's own finding and exit, and the legs NEXT, pasted
    in a directory whose Makefile's `bootstrap` target leaves a marker,
    leaves none -- each beside a line the doctor printed before #277, pasted
    the same way, so the harness is shown to see the defect it guards;
  * an AST GUARD over `shape-doctor.py`: no string that is not a docstring
    holds a tail -- two or more blanks, or a tab, then `#`, a blank after
    it or not, or a `#` that opens the text after a part that is not a
    constant -- except `placement_plan_leg`'s YAML comment lines and the one
    `placement plan written to` line in `report`, where that text is not a
    NEXT. A string is read whole, across `+` and the pieces of an f-string
    (#679). It is what turns a tail landed later, by any lane, into a red
    test.

The fixtures are `tests/test_shape_doctor.py`'s, imported rather than rebuilt
(the precedent is `tests/test_family_add_refusals.py`); importing a fixture
gives this module its own instance of it.
"""

from __future__ import annotations

import ast
import os
import re
import select
import shlex
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP, appended_to_command_scope, git, rmtree
#: The lane a lane's run sets, from the file that owns that rule.
from test_commit_trailers import LANE
#: The doctor's own fixtures and helpers, from the module that owns them. A
#: project or a holder made any other way would be a different project.
from test_shape_doctor import (  # noqa: F401
    BREAKAGES, DOCTOR, DRIFT_TARGET, FAMILY_MEMBER, FAMILY_NAME,
    GIT_IDENTITY, SCAFFOLD_WHY, SHAPE_PIN, UPSTREAM_TARGET, behind_row,
    break_manifest, break_the_pin, doctor, doctor_module, holder,
    not_forty_hex, pin_with, project, recommit_a_good_pin, red_root, rows_of,
    scaffolded_here, stage, standard, standard_ahead,
    standard_of_another_history,
)
#: The `manifest kinds` row's roots and its guard (#548), from the module
#: that owns them: the row is that module's, and so is `rows_of`, which asks
#: the guard of every row it reads.
from test_shape_doctor import (
    MISSPELT_KIND, READ_NOWHERE, assert_next_holds_no_prose, commit_all,
    family_beside, give_a_kind, outside_single_quotes, plant_family_yaml,
    write_inventory,
)
#: The lockstep remedy `validate-pins.py` prints under its refusals, and the
#: one every `Refusal` carried before #370, from the module that spells it;
#: importing `tests/test_shape_doctor.py` put `scripts/` on the path.
from repo_shape import REMEDIATION
#: Lane 2's ways to make a file under `contracts/` not load (#291), from the
#: module that owns them: the `manifest kinds` row's NEXTs are #291's, so the
#: roots are too.
from test_shape_doctor import (
    NAMING_COPY, PROJECT_LINE, SLIP, SPEC_PIN, a_copy_conflicted_on_its_own,
    append_to, conflict_in, insert_after_first_line, leg_pin_not_utf8,
    own_pin_named_edited_with_a_slip,
)
#: Doctor A's ways to make a leg or a member red (#276), from the module that
#: owns them: the `legs` and `members` lines are A's, so the roots are too.
#: Its `commit_in(root, message)` commits whatever is staged, with an
#: identity of its own, which is all the pin's history below needs of one.
from test_doctor_legs_members_next import (
    commit_in, holder_copy, holder_without, make_gitlink_moved,
    make_member_gitlink_mismatch, member_unbootstrapped,
)
#: Doctor B's crashing validator and unloaded manifest (#278, #298), from the
#: module that owns them.
from test_doctor_validator_rows import crashing, lost_gate, unloaded


# --- making each converted row print its NEXT -------------------------------

def a_short_standard(tmp_path: Path, name: str) -> Path:
    """A directory standing in for a standard that lacks what a row needs:
    what the doctor's own checkout cannot be made to lack in a test."""
    short = tmp_path / name
    short.mkdir()
    return short


def _validator_neither_readable(standard, project, holder, tmp_path):
    # Neither the root's copy nor the standard's is there: a validator name
    # nothing carries, asked of the builder itself.
    module = doctor_module(standard)
    ctx = module.Context(project.resolve())
    return module.validator_row(
        ctx, "manifest", "manifest", "scripts/validate-nothing.py",
        "templates/assembly-root/scripts/validate-nothing.py",
        ["--root", str(ctx.root)]).as_dict()


def _validator_own_copy(standard, project, holder, tmp_path):
    root = red_root("manifest", project, holder, tmp_path, keep_own=True)
    return rows_of(doctor(standard, root, "--json"))["manifest"]


def _validator_template_copy(standard, project, holder, tmp_path):
    root = red_root("pins", project, holder, tmp_path)
    return rows_of(doctor(standard, root, "--json"))["pins"]


def _unloaded_manifest(standard, project, holder, tmp_path):
    edit, code = BREAKAGES["tab-indent"]
    break_manifest(project.resolve() / "project.yaml", edit, code)
    return rows_of(doctor(standard, project, "--json"))["manifest"]


def _unloaded_manifest_neither_readable(standard, project, holder, tmp_path):
    # The branch that hands on `validator_row`'s NEXT -- and now its `why`.
    edit, code = BREAKAGES["tab-indent"]
    break_manifest(project.resolve() / "project.yaml", edit, code)
    module = doctor_module(standard)
    ctx = module.Context(project.resolve())
    assert ctx.manifest_refusal is not None, "the manifest still loads"
    return module.unloaded_manifest_row(
        ctx, "manifest", "manifest", "scripts/validate-nothing.py",
        "templates/assembly-root/scripts/validate-nothing.py").as_dict()


def _shape_currency_cannot_answer(standard, project, holder, tmp_path):
    stranger = standard_of_another_history(standard, tmp_path)
    return rows_of(doctor(stranger, project, "--json"))["shape-currency"]


def _shape_currency_behind_pin_only(standard, project, holder, tmp_path):
    # Run inside a lane, so the `apply` grows its trailer -- which is `why`'s
    # to carry now, and never `next`'s.
    row = behind_row(standard_ahead(standard, tmp_path), project, LANE)
    assert row["detail"].get("behind_pin_only") is True, row
    assert row["why"].endswith(f" --trailer 'Lane: {LANE}'"), row["why"]
    return row


def _shape_currency_moved(standard, project, holder, tmp_path):
    ahead = standard_ahead(standard, tmp_path, UPSTREAM_TARGET,
                           "\n# an upstream fix, after this project was cut\n",
                           "An upstream fix to a copied file")
    edited = project / DRIFT_TARGET
    edited.write_text(edited.read_text(encoding="utf-8")
                      + "\n# a local edit nobody carried upstream\n",
                      encoding="utf-8")
    row = behind_row(ahead, project, LANE)
    # The `apply` -- the lane's trailer with it -- is the row's `why`, and
    # nothing of it is on the NEXT. Neither carries `--accept-local`: the
    # flag is the person's to add, never the row's (#501).
    assert "--accept-local" not in row["why"], row["why"]
    assert row["why"].endswith(f" --trailer 'Lane: {LANE}'"), row["why"]
    for moved in ("apply", "--accept-local", "--trailer"):
        assert moved not in row["next"], (moved, row["next"])
    return row


def _legs(standard, project, holder, tmp_path):
    # A leg committed past its pin where the gitlink IS the pin: doctor A's
    # git line, which a checkout cures (#276).
    commit_in(project / "spec")
    return rows_of(doctor(standard, project, "--json"))["legs"]


def _legs_lockstep(standard, project, holder, tmp_path):
    # A gitlink that is not the pin, which no checkout cures: doctor A's
    # lockstep line, the root's own `validate-pins.py` (`lockstep_next`).
    make_gitlink_moved(project)
    return rows_of(doctor(standard, project, "--json"))["legs"]


def _leg_shape_files_partly_copyable(standard, project, holder, tmp_path):
    (project / "spec" / "AGENTS.md").unlink()
    (project / "spec" / "CLAUDE.md").unlink()
    return rows_of(doctor(standard, project, "--json"))["leg-shape-files"]


def _leg_shape_files_all_rendered(standard, project, holder, tmp_path):
    # The NEXT that WAS prose, with a command in backticks inside it.
    (project / "spec" / "AGENTS.md").unlink()
    row = rows_of(doctor(standard, project, "--json"))["leg-shape-files"]
    # The `--help` the sentence names, now the command itself. Its path may
    # be quoted (a Windows temporary directory is), so read as words.
    words = row["next"].split()
    assert words[-1] == "--help" and "scaffold-project.py" in words[-2], \
        row["next"]
    return row


def _placement_policy_missing(standard, project, holder, tmp_path):
    module = doctor_module(standard)
    ctx = module.Context(project.resolve())
    ctx.shape = a_short_standard(tmp_path, "a-standard-without-adopt")
    adopt, _policy, row = module.placement_policy(
        ctx, ctx.shape / "contracts" / "path-classification.yaml")
    assert adopt is None and row is not None, row
    return row.as_dict()


def _placement_plan(standard, project, holder, tmp_path):
    stage(project / "spec", "tool.py", "VALUE = 1\n")
    return rows_of(doctor(standard, project, "--json"))["placement"]


def _placement_moved(standard, project, holder, tmp_path):
    # A submodule moved since the adoption (#525): the spec leg holds it,
    # and the row names the code leg, which holds none. Its NEXT is the
    # doctor again, as `unreadable_next`'s is for a file only a person can
    # mend, and its `why` gives both ways out.
    from test_shape_doctor import record_submodules, stage_gitlink
    stage_gitlink(project / "spec", "vendor/rules")
    record_submodules(project, ("vendor/rules", "code"))
    return rows_of(doctor(standard, project, "--json"))["placement"]


def _agent_files_pinned(standard, project, holder, tmp_path):
    (project / "AGENTS-shape.md").unlink()
    return rows_of(doctor(standard, project, "--json"))["agent-files"]


def _agent_files_unpinned(standard, project, holder, tmp_path):
    # No `contracts/shape-pin.yaml` names `AGENTS-shape.md`: the branch
    # that sends the reader to `update-shape.py check` and `apply --add`.
    module = doctor_module(standard)
    here = tmp_path / "unpinned"
    here.mkdir()
    for name in ("AGENTS.md", "CLAUDE.md"):
        (here / name).write_text("an agent file\n", encoding="utf-8")
    return module.check_agent_files(module.Context(here)).as_dict()


def _agent_files_rendered(standard, project, holder, tmp_path):
    (project / "CLAUDE.md").unlink()
    return rows_of(doctor(standard, project, "--json"))["agent-files"]


def _members(standard, project, holder, tmp_path):
    root = tmp_path / FAMILY_NAME
    shutil.copytree(holder["root"], root, symlinks=True)
    mount = root / "members" / FAMILY_MEMBER
    rmtree(mount)
    mount.mkdir()
    return rows_of(doctor(standard, root, "--json"))["members"]


def _members_git_line(standard, project, holder, tmp_path):
    # A holder whose own bootstrap cannot run: doctor A's plain git line.
    root = holder_copy(holder, tmp_path)
    holder_without(root, "bootstrap.py")
    member_unbootstrapped(root)
    return rows_of(doctor(standard, root, "--json"))["members"]


def _members_lockstep(standard, project, holder, tmp_path):
    # A member whose gitlink is not its pin: the family gate, through the
    # same `lockstep_next` as the `legs` row.
    root = holder_copy(holder, tmp_path)
    make_member_gitlink_mismatch(root)
    return rows_of(doctor(standard, root, "--json"))["members"]


def _validator_crashed(standard, project, holder, tmp_path):
    # The root's own `validate-pins.py` raising: doctor B's crash line (#278).
    here, root, row_id, _own = crashing("own-pins", standard, project, holder,
                                        tmp_path)
    return rows_of(doctor(here, root, "--json"))[row_id]


def _unloaded_manifest_restore(standard, project, holder, tmp_path):
    # A manifest that does not load and a gate whose `repo_shape.py` is gone
    # from the tree, which HEAD still holds: doctor B's restore line (#298).
    root, row_id, _refusal = unloaded("project", project, holder, tmp_path,
                                      "tree")
    return rows_of(doctor(standard, root, "--json"))[row_id]


def _validator_crashed_restore(standard, project, holder, tmp_path):
    # An own gate that crashed for want of the `repo_shape.py` it lost, which
    # HEAD still holds: the same restore line, on a valid manifest (#697).
    root = lost_gate("manifest", project, holder, tmp_path)
    return rows_of(doctor(standard, root, "--json"))["manifest"]


def _pin_row(standard, root, restore):
    """The `shape currency` row for a root whose OWN pin does not read, and
    the proof that the fixture reached the branch it was made for."""
    row = rows_of(doctor(standard, root, "--json"))["shape-currency"]
    assert row["detail"]["restore"] == restore, row["detail"]
    return row


def _pin_unmerged(standard, project, holder, tmp_path):
    # The issue's own reproduction: two branches rewrite `commit:`, then merge.
    # Lane 2's `pin_restore`, #237: the pin is `UU`, and the NEXT takes one
    # side of it whole.
    base = git("rev-parse", "HEAD", cwd=project).stdout.strip()
    for branch, digit in (("edit-a", "1"), ("edit-b", "2")):
        git("checkout", "-q", "-b", branch, base, cwd=project)
        break_the_pin(project, pin_with(r'^commit: .*$',
                                        f'commit: "{digit * 40}"'))
        git("add", "--", SHAPE_PIN, cwd=project)
        commit_in(project, branch)
    merged = subprocess.run(["git", "merge", "-q", "edit-a"],
                            cwd=str(project), capture_output=True, text=True,
                            check=False, env={**os.environ, **GIT_IDENTITY})
    assert merged.returncode != 0, merged.stdout + merged.stderr
    return _pin_row(standard, project, "unmerged")


def _pin_unmerged_copy_beside(standard, project, holder, tmp_path):
    # #496 (#485): the pin and a copy it has a row for conflicted together.
    # The NEXT takes the pin alone, and the `why` gives the copy to a
    # person to merge by hand.
    conflict_in(project, SHAPE_PIN, "commit", "Makefile")
    row = _pin_row(standard, project, "unmerged")
    assert row["detail"]["left_for_a_person"] == ["Makefile"], row
    return row


def _pin_uncommitted(standard, project, holder, tmp_path):
    # HEAD holds a pin that reads and the tree differs from it: `checkout HEAD`.
    break_the_pin(project, not_forty_hex)
    return _pin_row(standard, project, "uncommitted")


def _pin_hidden(standard, project, holder, tmp_path):
    # HEAD's pin reads, the copy here is broken, and `git status` says
    # nothing because an index flag hides it: the `ls-files -v` that shows
    # which.
    recommit_a_good_pin(project)
    git("update-index", "--assume-unchanged", "--", SHAPE_PIN, cwd=project)
    break_the_pin(project, not_forty_hex)
    return _pin_row(standard, project, "hidden")


def _pin_committed(standard, project, holder, tmp_path):
    # A commit broke the pin: `checkout <that commit>~1`.
    break_the_pin(project, not_forty_hex)
    git("add", "--", SHAPE_PIN, cwd=project)
    commit_in(project, "break the pin")
    row = _pin_row(standard, project, "committed")
    # The commit's own name is in the sentence, so it is read past: the
    # words after it are asserted here, the words before it by CASES.
    assert row["why"].endswith(
        ", the commit that broke it, and the newest pin in its history that "
        "reads. Commit that rather than editing the pin"), row["why"]
    return row


def _pin_no_history(standard, project, holder, tmp_path):
    # One root commit holds a bad pin: nothing git can name puts one back, so
    # `unreadable_pin_row` keeps the `update-shape.py check` it always had.
    break_the_pin(project, not_forty_hex)
    git("checkout", "-q", "--orphan", "squashed", cwd=project)
    git("add", "--", SHAPE_PIN, cwd=project)
    commit_in(project, "the whole history, squashed into one commit")
    return _pin_row(standard, project, "none")


def _kinds_row(standard, root, rel, restore):
    """The `manifest kinds` row for a root where `rel` does not load, and the
    proof that the fixture reached the branch it was made for (#291)."""
    row = rows_of(doctor(standard, root, "--json"))["manifest-kinds"]
    assert row["detail"]["restore"] == {rel: restore}, row["detail"]
    return row


def _pin_unmerged_shown(standard, project, holder, tmp_path):
    # A copy the shape pin has a row for, conflicted on its own: the `diff`
    # that shows the hunks git could not merge, and nothing taken whole.
    a_copy_conflicted_on_its_own(project)
    return _kinds_row(standard, project, NAMING_COPY, "unmerged")


def _pin_uncommitted_shown(standard, project, holder, tmp_path):
    # The copy's uncommitted change breaks it: the `diff HEAD` that shows it.
    append_to(project / NAMING_COPY, SLIP)
    return _kinds_row(standard, project, NAMING_COPY, "uncommitted")


def _pin_committed_shown(standard, project, holder, tmp_path):
    # A hand merge of the copy, committed with a slip: the `diff <it>~1`
    # that shows every change since the newest copy that reads.
    copy = project / NAMING_COPY
    insert_after_first_line(copy, PROJECT_LINE)
    append_to(copy, SLIP)
    git("add", "--", NAMING_COPY, cwd=project)
    commit_in(project, "the hand merge, with a slip")
    return _kinds_row(standard, project, NAMING_COPY, "committed")


def _unreadable_next_by_hand(standard, project, holder, tmp_path):
    # A file of the project's own that does not load: no git command is
    # named, and the NEXT is this doctor again.
    rel, restore = own_pin_named_edited_with_a_slip(project)
    return _kinds_row(standard, project, rel, restore)


def _unreadable_next_restore(standard, project, holder, tmp_path):
    # A leg pin that does not load: the branch of `unreadable_next` that
    # hands on `pin_restore`'s command and, now, its `why`.
    leg_pin_not_utf8(project)
    return _kinds_row(standard, project, SPEC_PIN, "uncommitted")


def _machine(standard, project, holder, tmp_path):
    # A preflight that is not ready, on every host: whether the real one is
    # depends on the machine, and the row's NEXT only exists when it is not.
    module = doctor_module(standard)
    ctx = module.Context(project.resolve())
    ctx.shape = a_short_standard(tmp_path, "a-standard-not-ready")
    (ctx.shape / "setup-project.py").write_text(
        "import sys\nprint('[!!] a prerequisite is missing')\nsys.exit(1)\n",
        encoding="utf-8")
    return module.check_machine(ctx).as_dict()


def _way_in(standard, project, holder, tmp_path):
    here = tmp_path / "Loose"
    here.mkdir()
    (here / "notes.txt").write_text("nothing to see\n", encoding="utf-8")
    return rows_of(doctor(standard, here, "--json"))["way-in"]


def _kinds(standard, root):
    return rows_of(doctor(standard, root, "--json"))["manifest-kinds"]


def _read_nowhere(project: Path, case: str) -> str:
    """One of #439's files, written into `project` and not committed; its
    path."""
    _where, rel, _kind, body, _read_at = READ_NOWHERE[case]
    (project / rel).write_bytes(body)
    return rel


def _removal_next_committed(standard, project, holder, tmp_path):
    # #439: a kind whose gate runs here, at a path it never reads, committed:
    # the `git rm` of it (#548).
    rel = _read_nowhere(project, "contracts-project-yaml")
    commit_all(project, f"{rel}, which no gate reads")
    return _kinds(standard, project)


def _removal_next_loose(standard, project, holder, tmp_path):
    # A kind nothing registers, never added: the `git status --ignored` that
    # shows it, where the NEXT was "register the kind ..., or remove the
    # file" (#548), and never the deletion no history can undo (review of
    # PR #555).
    write_inventory(project)
    return _kinds(standard, project)


def _removal_next_changed(standard, project, holder, tmp_path):
    # #327's file, staged and never committed: the `git status` that shows
    # the change git rm will not discard.
    plant_family_yaml(project, holder)
    git("add", "--", "contracts/family.yaml", cwd=project)
    return _kinds(standard, project)


def _taking_out_committed(standard, project, holder, tmp_path):
    # The shape pin given a kind nothing registers, committed: no NEXT and a
    # `why` naming a row that said `ok` (review of PR #555, round 2), now
    # the `git log -p -1` that shows the commit.
    give_a_kind(project, SHAPE_PIN, MISSPELT_KIND, True)
    return _kinds(standard, project)


def _taking_out_changed(standard, project, holder, tmp_path):
    # The naming policy given a kind nothing registers, and not committed:
    # the `git diff HEAD` that shows the change, never a NEXT taking it out.
    naming = project / NAMING_COPY
    naming.write_bytes(naming.read_bytes().replace(
        b"kind: repository-naming-policy\n", b"kind: service-inventory\n"))
    return _kinds(standard, project)


def _family_beside(standard, project, holder, tmp_path):
    # #211's file, whose NEXT held `family.py init` and `family.py add` in
    # backticks: the `git rm` of it, and those two in the `why` (#548).
    family_beside(project, holder)
    return _kinds(standard, project)


def _every_fault(standard, project, holder, tmp_path):
    # Every fault that is a file to take out, at once and in every git state:
    # #211's committed, an unregistered kind and #327's untracked, #439's
    # staged. ONE command, where the NEXT was their sentences joined by `; `.
    family_beside(project, holder)
    write_inventory(project)
    plant_family_yaml(project, holder)
    git("add", "--", _read_nowhere(project, "a-pin-nothing-declares"),
        cwd=project)
    return _kinds(standard, project)


def _a_repository_row(row_id):
    """The builder of a `the way in` row for a git repository with no
    `origin`, which is the adoption with `--org <your-org>` and the scaffold
    beside it (#545)."""
    def build(standard, project, holder, tmp_path):
        here = tmp_path / "Loose"
        here.mkdir()
        git("init", "-q", "-b", "main", ".", cwd=here)
        return rows_of(doctor(standard, here, "--json"))[row_id]
    return build


#: One fixture per NEXT #277 converted, by the builder and branch it reaches,
#: and how the sentence that used to follow `   # ` on it now opens -- moved
#: VERBATIM, less the `#`, so these are the words main, doctors A and B and
#: lane 2's #237, #291 and #496 printed. The `manifest kinds` NEXTs #277
#: left as prose (#211, #327) are here too since #548, by the git state the
#: one command they print now reaches (`removal_next`), or, for a file a
#: gate here reads, the read-only one that shows its kind line (`taking_out`,
#: review of PR #555), with the sentence that now opens their `why`; a
#: `Refusal.remediation` reaches no NEXT
#: (`test_a_refusal_a_check_lets_out_has_no_next_and_keeps_its_remedy`).
CASES = {
    "validator_row-neither-readable": (
        _validator_neither_readable,
        "from a complete checkout of the standard; this one is missing that "
        "file"),
    "validator_row-own-copy": (
        _validator_own_copy,
        "read its output in full; it names what it refused"),
    "validator_row-template-copy": (
        _validator_template_copy,
        "read its output in full; it names what it refused"),
    "unloaded_manifest_row": (
        _unloaded_manifest, "the file to fix is "),
    "unloaded_manifest_row-neither-readable": (
        _unloaded_manifest_neither_readable,
        "from a complete checkout of the standard; this one is missing that "
        "file"),
    "pin_restore-unmerged": (
        _pin_unmerged,
        "--theirs takes the other side. Take one side of the pin whole and "
        "never a hand-merged pin, then finish the merge as git says and run "
        "this doctor again"),
    "pin_restore-unmerged-copy-beside": (
        _pin_unmerged_copy_beside,
        "--theirs takes the other side. Take one side of the pin whole and "
        "never a hand-merged pin. Makefile is a copy conflicted too. A copy "
        "can hold an edit of the project"),
    "pin_restore-uncommitted": (
        _pin_uncommitted,
        "puts back the pin as last committed and discards the uncommitted "
        "change that broke it, which no tool of this standard writes"),
    "pin_restore-hidden": (
        _pin_hidden,
        "HEAD holds a pin that reads and git status shows no change to the "
        "copy here, so no commit broke it and nothing in history is put "
        "back. S in the first column is skip-worktree, as a sparse checkout "
        "sets it, and a lowercase h is assume-unchanged: either hides the "
        "copy here from git. Any other letter means the file itself cannot "
        "be read, as the refusal says. Clearing that is for a person, then "
        "run this doctor again"),
    "pin_restore-committed": (_pin_committed, "the pin as it was before "),
    "unreadable_pin_row": (
        _pin_no_history,
        "no commit in this root holds a pin to put back, so whether it was "
        "ever scaffolded or adopted is for a person to decide"),
    "pin_restore-unmerged-shown": (
        _pin_unmerged_shown,
        "a merge left the copy conflicted, and this shows the hunks git could "
        "not merge. A copy can hold an edit of the project"),
    "pin_restore-uncommitted-shown": (
        _pin_uncommitted_shown,
        "HEAD holds a copy that reads, and this shows the uncommitted change "
        "that breaks the copy here. A copy can hold an edit of the project"),
    "pin_restore-committed-shown": (
        _pin_committed_shown,
        "the newest copy in its history that reads is the one before "),
    "unreadable_next": (
        _unreadable_next_by_hand,
        "the reason names each file that does not load and why, and none is a "
        "file this root declares a tool writes with a copy that reads in its "
        "history, so what each should say -- a merge conflict resolved, a "
        "hand edit put right -- is for a person to decide. This row reads "
        "them again once they load"),
    "unreadable_next-pin_restore": (
        _unreadable_next_restore,
        "puts back the pin as last committed and discards the uncommitted "
        "change that broke it, which no tool of this standard writes"),
    "check_shape_currency-cannot-answer": (
        _shape_currency_cannot_answer,
        "this checkout of the standard does not carry the commit the pin "
        "names; fetch it, or run the doctor from a clone that has it"),
    "check_shape_currency-pin-alone-behind": (
        _shape_currency_behind_pin_only, "then apply --at "),
    "check_shape_currency-copies-moved": (
        _shape_currency_moved, "then apply --at "),
    "validator_row-crashed": (
        _validator_crashed,
        "read its output in full, it shows where the validator stopped"),
    "unloaded_manifest_row-restore": (
        _unloaded_manifest_restore,
        "it puts back the scripts/repo_shape.py HEAD holds, the copy this "
        "project committed and scripts/validate-manifest.py imports, where "
        "update-shape.py apply would copy a newer one"),
    "validator_row-crashed-restore": (
        _validator_crashed_restore,
        "it puts back the scripts/repo_shape.py HEAD holds, the copy this "
        "project committed and scripts/validate-manifest.py imports, where "
        "update-shape.py apply would copy a newer one. Then run `"),
    "check_legs": (
        _legs,
        "checks each leg out at the commit this repository records for it, "
        "and fetches a mount that is empty"),
    "lockstep_next-legs": (
        _legs_lockstep,
        "no submodule update cures a leg whose gitlink or pin is missing or "
        "disagrees, or a mount git cannot read a HEAD in. validate-pins.py "
        "prints what it finds and names the repair where it has one"),
    "missing_shape_file_fix-partly-copyable": (
        _leg_shape_files_partly_copyable,
        "and the rest are RENDERED per project (placeholders): "
        "scaffold-project.py writes those, and copying a template verbatim "
        "would not"),
    "missing_shape_file_fix-all-rendered": (
        _leg_shape_files_all_rendered,
        "the missing file(s) are RENDERED per project from "
        "templates/<role>-root/ -- `"),
    "placement_policy": (
        _placement_policy_missing,
        "from a COMPLETE checkout of the standard; this one is short "
        "adopt-project.py"),
    "check_placement": (
        _placement_plan,
        "writes the paths above as a plan to resolve by hand. Moving one is a "
        "pull request on each leg and a pin bump in the root, so this "
        "command makes neither"),
    "check_placement-moved": (
        _placement_moved,
        "each submodule above is in a leg its row in project.yaml's "
        "`submodules:` does not name"),
    "check_agent_files-pinned": (
        _agent_files_pinned,
        "the pin has a `files:` row for it, so it was deleted rather than "
        "never copied; restore it from this repository's own history, then "),
    "check_agent_files-unpinned": (
        _agent_files_unpinned,
        "no pin row names it, so it is reported upstream-added and taken, on "
        "the human's word, with `apply --add AGENTS-shape.md`"),
    "check_agent_files-rendered": (
        _agent_files_rendered,
        "CLAUDE.md is RENDERED per project, not copied; write it, or take a "
        "rendered one from a scaffolded root"),
    "members_verdict": (
        _members,
        "what `make bootstrap` runs in a holder: it fetches every member at "
        "its pin and leaves it detached there"),
    "members_verdict-git-line": (
        _members_git_line,
        "checks each member out at the commit this repository records for "
        "it, and fetches a mount that is empty"),
    "lockstep_next-members": (
        _members_lockstep,
        "no submodule update cures a member whose gitlink or pin is missing "
        "or disagrees, or a mount git cannot read a HEAD in. "
        "validate-family.py prints what it finds and names the repair where "
        "it has one"),
    "check_machine": (
        _machine,
        "it names each missing prerequisite and offers to install it, on a "
        "typed yes"),
    "removal_next-committed": (
        _removal_next_committed,
        "takes contracts/project.yaml out of this root: commit that on a "
        "branch and land it as a pull request. Never rename it onto a path a "
        "gate here reads"),
    "removal_next-loose": (
        _removal_next_loose,
        "shows contracts/inventory.yaml, which git does not track: no commit "
        "holds it, so deleting it cannot be undone and is a person's act, "
        "never this row's, with nothing to commit after. A person deletes it "
        "with: git -C "),
    "removal_next-changed": (
        _removal_next_changed,
        "shows the changes no commit holds in contracts/family.yaml, which "
        "git rm will not discard: commit or drop them, and the next run "
        "names the way out. Or move what contracts/family.yaml describes"),
    "taking_out-committed": (
        _taking_out_committed,
        "shows the last commit that changed contracts/shape-pin.yaml. "
        "contracts/shape-pin.yaml declares kind pinned_contract_manifes "
        "where a gate here reads it as pinned_contract_manifest, and no gate "
        "here checks the kind it declares, so this row is the one that says "
        "so"),
    "taking_out-changed": (
        _taking_out_changed,
        "shows the change to contracts/repository-naming.yaml that no commit "
        "holds. contracts/repository-naming.yaml declares kind "
        "service-inventory where a gate here reads it as "
        "repository-naming-policy, and the manifest row's gate finds that "
        "too"),
    "check_manifest_kinds-family-beside": (
        _family_beside,
        "takes family.yaml out of this root: commit that on a branch and land "
        "it as a pull request. Or move the membership family.yaml records to "
        "a holder of its own (`family.py init`, then `family.py add` there)"),
    "check_manifest_kinds-every-fault": (
        _every_fault,
        "takes family.yaml out of this root: commit that on a branch and land "
        "it as a pull request. The next run names the way out for "
        "contracts/inventory.yaml, contracts/family.yaml, "
        "contracts/release-pin.yaml. Or register the kind "
        "contracts/inventory.yaml declares"),
    # Its sentence is the scaffold rows' one now (#545): it opens with the
    # placeholder to replace, and the words printed after `   # ` follow.
    "check_the_way_in": (_way_in, SCAFFOLD_WHY),
    # #545's, which were never a `   # ` tail; the property holds them to the
    # same rule, and the placeholder is the one the scaffold line carries.
    "check_the_way_in-adopt-no-origin": (
        _a_repository_row("way-in"),
        "replace <your-org> with the GitHub organisation to adopt under"),
    "check_the_other_way_in": (
        _a_repository_row("way-in-scaffold"), SCAFFOLD_WHY),
}


def unquoted_operators(command: str) -> list[str]:
    """The control operators `sh` would act on in `command`: `;`, `&`, `|`,
    `(`, `)`, `<`, `>`, outside any quotation.

    `commenters` IS EMPTY ON PURPOSE. To an interactive zsh a `#` is a word,
    so an operator after one is live there, and a reader that stopped at the
    `#` the way `sh` does would wave through the very line #277 is about.
    """
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    return [token for token in lexer
            if token and set(token) <= set("();<>|&")]


#: The operators a NEXT must not carry outside a quotation on POSIX: a list
#: (`;`, `&`, `&&`, `|`, `||`) runs a second command, a parenthesis opens a
#: subshell -- and an unquoted `$(` is read as `$` then the operator `(`,
#: so it is one of them. `<` and `>` are not here: the way-in row's
#: `<your-org>` is a placeholder the reader replaces, unquoted on purpose.
LIVE_OPERATORS = ";&|()"


def test_the_operator_readers_see_what_sh_runs_and_not_a_quoted_path():
    """The property below is only as good as these two readers, so each is
    shown to find an operator `sh` acts on, and to pass one that sits in a
    quoted path."""
    assert set("".join(unquoted_operators("a; b && c | d (e)"))) == set(
        LIVE_OPERATORS)
    assert unquoted_operators("git -C '/w/a;b&c|d (e)' status") == []
    assert "(" in unquoted_operators("echo $(make)")
    assert "$(" in outside_single_quotes('echo "$(make)"')
    assert "$(" not in outside_single_quotes("echo '$(make)'")
    assert "$(" not in outside_single_quotes("echo \\$(make)")
    assert "$(" not in outside_single_quotes("echo 'it'\"'\"'s $(here)'")


@pytest.mark.parametrize("case", list(CASES))
def test_every_converted_next_is_a_command_and_nothing_else(
        standard, project, holder, tmp_path, case):
    """The property, over one red fixture per converted builder and branch.

    NO SHELL COMMENT: `shlex` reads the line the same with comments on and
    off, so nothing in it is a `#` where a word starts. NO BACKTICK, AND NO
    `$(` THAT RUNS: command substitution in sh, bash and zsh alike. On
    POSIX, NO `;`, `&`, `|`, `(` OR `)` OUTSIDE A QUOTATION, read from
    `shlex`'s tokens so that a quoted path holding one is a path: what
    followed a `;` in a tail was the second command an interactive zsh ran,
    and the others start one too. AND THE SENTENCE IS NOT LOST: it is the
    row's `why`, opening with the words printed after `   # ` before #277.
    """
    build, opens = CASES[case]
    row = build(standard, project, holder, tmp_path)
    command, why = row["next"], row["why"]
    assert command, (case, row)
    assert why and why.startswith(opens), (case, opens, why)
    assert shlex.split(command, comments=True) == shlex.split(command), (
        case, command)
    assert "`" not in command, (case, command)
    if os.name != "nt":
        live = "".join(unquoted_operators(command))
        for operator in LIVE_OPERATORS:
            assert operator not in live, (case, operator, command)
        assert "$(" not in outside_single_quotes(command), (case, command)
    assert "   # " not in command, (case, command)


# --- pasted, as a person pastes ---------------------------------------------

#: The line the paste ends with, and what it prints: the status of the line
#: before it. `$?` is never expanded in the echo of what was typed, so only
#: the shell's own answer matches.
PASTED_EXIT = re.compile(r"pasted-exit=(\d+)")


def paste_into_zsh(line: str, cwd: Path, timeout: float = 120.0) -> tuple:
    """`(status, transcript)`: `line` typed into `zsh -f -i` through a pty.

    `-f` reads no startup file of the person's, so `interactivecomments` is
    zsh's default, OFF, which is the shell #277 is about; `TERM=dumb` keeps
    the line editor quiet. The line is typed whole, then a second line that
    prints its status; `exit` is typed only once that answer is read, so a
    platform that drops a pty's unread output when the shell ends cannot
    lose it. `status` is None when no answer came -- a line that left the
    shell inside an open quotation, say -- and the transcript says why.

    The environment is the test's own, less `PYTHONPATH` (a NEXT carries
    what it needs, #238) and with file-protocol git for the one child that
    may clone from the suite's local remotes -- per process, never
    `GIT_ALLOW_PROTOCOL` (see `tests/conftest.py`), appended to the command
    scope the environment holds. It is read from `os.environ` HERE, at the
    call, as doctor A's `paste_env()` is (#758): a dict built when its module
    is imported, at collection, is made before the session fixture puts the
    `gh` guard first on `PATH`, so a line pasted with it would reach
    whatever `gh` the machine has.
    """
    import pty  # POSIX only: `tty` beneath it needs `termios`
    env = {name: value for name, value in os.environ.items()
           if name.upper() != "PYTHONPATH"}
    env.update({"TERM": "dumb", "PYTHONDONTWRITEBYTECODE": "1",
                **appended_to_command_scope(
                    os.environ, [("protocol.file.allow", "always")])})
    master, slave = pty.openpty()
    try:
        shell = subprocess.Popen(["zsh", "-f", "-i"], stdin=slave,
                                 stdout=slave, stderr=slave, cwd=str(cwd),
                                 env=env, start_new_session=True)
    finally:
        os.close(slave)
    heard = bytearray()
    deadline = time.monotonic() + timeout

    def listen(until=None) -> re.Match | None:
        while time.monotonic() < deadline:
            if until is not None:
                found = until.search(heard.decode("utf-8", "replace"))
                if found:
                    return found
            ready, _, _ = select.select([master], [], [], 0.5)
            if not ready:
                if shell.poll() is not None:
                    return None
                continue
            try:
                chunk = os.read(master, 65536)
            except OSError:  # EIO: Linux's EOF on a pty whose shell is gone
                return None
            if not chunk:
                return None
            heard.extend(chunk)
        return None

    try:
        os.write(master, line.encode("utf-8") + b"\n"
                 + b"print -r -- pasted-exit=$?\n")
        answered = listen(PASTED_EXIT)
        try:
            os.write(master, b"exit\n")
        except OSError:
            pass
        deadline = min(deadline, time.monotonic() + 10)
        listen()
    finally:
        if shell.poll() is None:
            shell.kill()
        shell.wait(timeout=30)
        os.close(master)
    transcript = heard.decode("utf-8", "replace")
    return (int(answered.group(1)) if answered else None), transcript


#: What a pasted line must not have made the shell say: a word the shell
#: tried to run (the text after a `;`), or an argument the command refused
#: (the comment's own words, handed to it).
MISREAD = ("command not found", "unrecognized arguments")


@WINDOWS_SKIP
@pytest.mark.skipif(shutil.which("zsh") is None, reason="needs zsh")
def test_the_manifest_next_pasted_into_an_interactive_zsh_is_the_validator(
        standard, project, holder, tmp_path):
    """The validator's own finding, with the validator's own exit.

    THE LINE MAIN PRINTED IS PASTED TOO, and is the defect: its validator
    refuses the comment's words as arguments, `it names what it refused`
    after the `;` is a command that does not exist, and the status the person
    sees is that one's, 127. That half is what shows this harness reads `#`
    the way the person's shell does; without it the first half could pass
    in a shell that skipped the comment.
    """
    root = red_root("manifest", project, holder, tmp_path, keep_own=True)
    row = rows_of(doctor(standard, root, "--json"))["manifest"]
    assert row["status"] == "FINDING" and row["detail"]["own_copy"], row
    here = tmp_path / "standing-anywhere"
    here.mkdir()

    status, transcript = paste_into_zsh(row["next"], here)
    assert status == row["detail"]["exit"], transcript
    assert "FINDING manifest-topic" in transcript, transcript
    for misread in MISREAD:
        assert misread not in transcript, (misread, transcript)

    status, transcript = paste_into_zsh(f"{row['next']}   # {row['why']}",
                                        here)
    assert status == 127, transcript
    assert "command not found: it" in transcript, transcript


def legs_line_before_277(standard: Path, root: Path) -> str:
    """The `legs` NEXT the doctor printed for `root` before #276 and #277
    (`check_legs` at 3ae0109, the line #277 was filed against): the root's
    own bootstrap, and a tail holding `make bootstrap` in backticks.

    SPELLED HERE BECAUSE NOTHING PRINTS IT ANY MORE. #276 made the `legs`
    NEXT a git line whose sentence carries no backtick, so the line it
    prints today, with its `why` put back after `   # `, runs no `make`
    pasted, and could not show that this harness runs a backtick at all.
    """
    module = doctor_module(standard)
    return (f"{module.PYTHON} "
            f"{module.quote_arg(root / 'scripts' / 'bootstrap.py')} "
            f"--root {module.quote_arg(root)}   # what `make bootstrap` "
            "runs: it puts every leg on its tracking branch AT the pinned "
            "commit")


@WINDOWS_SKIP
@pytest.mark.skipif(shutil.which("zsh") is None or shutil.which("make") is None,
                    reason="needs zsh and make")
def test_the_legs_next_pasted_into_an_interactive_zsh_runs_no_make(
        standard, project, tmp_path):
    """Pasted where a Makefile's `bootstrap` target leaves a marker: none.

    The `legs` comment said "what `make bootstrap` runs" -- a pair of
    backticks, which an interactive zsh runs as command substitution in the
    directory the person is standing in, before the command it was pasted
    with. That line (`legs_line_before_277`) is pasted second, in the same
    directory, and leaves the marker, so the first half cannot be passing
    because the harness never runs a backtick.
    """
    commit_in(project / "spec")
    row = rows_of(doctor(standard, project, "--json"))["legs"]
    assert row["status"] == "FINDING", row
    here = tmp_path / "standing-here"
    here.mkdir()
    (here / "Makefile").write_text("bootstrap:\n\ttouch MARKER\n",
                                   encoding="utf-8")
    marker = here / "MARKER"

    status, transcript = paste_into_zsh(row["next"], here)
    assert status is not None, transcript
    assert not marker.exists(), transcript
    for misread in MISREAD:
        assert misread not in transcript, (misread, transcript)

    paste_into_zsh(legs_line_before_277(standard, project.resolve()), here)
    assert marker.exists(), (
        "the line the doctor printed before #277 must run `make bootstrap` "
        "here, or this test is proving nothing about the backticks")


#: The `manifest kinds` NEXT for a `family.yaml` beside `project.yaml` before
#: #548 (`FAMILY_BESIDE_FIX` at 5ed3e5de), spelled here because nothing
#: prints it any more.
FAMILY_BESIDE_NEXT_BEFORE_548 = (
    "an assembly root is not a family holder: take family.yaml out of this "
    "root, or move the membership to a holder of its own (`family.py init`, "
    "then `family.py add` there), as the human decides -- never `family.py "
    "add` here, which would mount the members inside a project")


@WINDOWS_SKIP
@pytest.mark.skipif(shutil.which("zsh") is None, reason="needs zsh")
def test_the_family_beside_next_pasted_into_zsh_runs_no_family_py(
        standard, project, holder, tmp_path, monkeypatch):
    """#548's own defect, pasted where a `family.py` first on `PATH` leaves a
    marker. The NEXT now is the `git rm` that takes `family.yaml` out, and
    leaves none; the line the doctor printed before #548, pasted the same
    way, runs `family.py init` and `family.py add` out of its backticks and
    leaves it, so this harness is shown to run a backtick."""
    family_beside(project, holder)
    row = rows_of(doctor(standard, project, "--json"))["manifest-kinds"]
    assert row["status"] == "FINDING", row
    stub = tmp_path / "stub"
    stub.mkdir()
    marker = tmp_path / "MARKER"
    (stub / "family.py").write_text(
        f"#!/bin/sh\ntouch {shlex.quote(str(marker))}\n", encoding="utf-8")
    (stub / "family.py").chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub}{os.pathsep}{os.environ['PATH']}")

    status, transcript = paste_into_zsh(row["next"], project)
    assert status == 0, transcript
    assert not marker.exists(), transcript
    assert git("ls-files", "--", "family.yaml", cwd=project).stdout == "", (
        "the NEXT did not take family.yaml out", transcript)

    paste_into_zsh(FAMILY_BESIDE_NEXT_BEFORE_548, project)
    assert marker.exists(), (
        "the line the doctor printed before #548 must run `family.py` here, "
        "or this test is proving nothing about the backticks")


# --- the report says the sentence, off the command's line -------------------

def test_the_table_prints_why_on_its_own_line_under_next(standard, project,
                                                        holder, tmp_path):
    """`NEXT` is the command as `--json` has it, and `WHY` is the line under
    it, with the sentence `--json` carries as `why`. Two rows at once, so the
    pairing is shown to be per row, and every row of the run carries the key.
    """
    root = red_root("manifest", project, holder, tmp_path, keep_own=True)
    commit_in(root / "spec")
    rows = rows_of(doctor(standard, root, "--json"))
    for name, row in rows.items():
        assert "why" in row, (name, row)
    explained = [row for row in rows.values() if row["next"] and row["why"]]
    assert {"manifest", "legs"} <= {row["id"] for row in explained}, rows
    table = doctor(standard, root).stdout.splitlines()
    for row in explained:
        [at] = [index for index, line in enumerate(table)
                if line.split()[:1] == ["NEXT"]
                and line.endswith("  " + row["next"])]
        assert table[at + 1].split()[0] == "WHY", table[at:at + 2]
        assert table[at + 1].endswith("  " + row["why"]), table[at:at + 2]


def test_a_report_that_cannot_answer_says_why_after_the_remediation(
        standard, project, tmp_path):
    """The CANNOT ANSWER block on stderr: `Remediation:` is the command, as
    the row's `next` is, and `Why:` is the line after it."""
    stranger = standard_of_another_history(standard, tmp_path)
    row = rows_of(doctor(stranger, project, "--json"))["shape-currency"]
    plain = doctor(stranger, project)
    assert plain.returncode == 3, plain.stdout + plain.stderr
    said = plain.stderr.splitlines()
    [at] = [index for index, line in enumerate(said)
            if line.startswith("  Remediation: ")]
    assert said[at] == "  Remediation: " + row["next"], said
    assert said[at + 1] == "  Why: " + row["why"], said


def test_a_cannot_answer_row_with_no_command_still_says_why(
        standard, project, capsys):
    """`Why:` is printed whenever the row has a `why`, whether or not it has
    a command for `Remediation:` (the coordinator's ruling on #277's merge
    with #278, which prints no `Remediation:` for a row with no NEXT). No
    row the doctor builds today is that row, so the report is handed one."""
    module = doctor_module(standard)
    ctx = module.Context(project.resolve())
    row = module.Row("cannot", "cannot", module.FINDING, "it could not ask",
                     None, {"environment": True}, why="what to do instead")
    module.report(ctx, [row], "CANNOT ANSWER (cannot: it could not ask)", 3)
    said = capsys.readouterr().err.splitlines()
    at = said.index("REFUSED shape-doctor-cannot-answer: it could not ask")
    assert said[at + 1:] == ["  Why: what to do instead"], said


# --- a refusal's remedy reaches no NEXT, and the guard over the rows --------
#
# #408: a check that let a `Refusal` out became a FINDING whose NEXT was the
# refusal's remedy, and a standard whose own path policy did not load an
# `n/a` row whose NEXT was the same: prose a tool prints under its refusal,
# `repo_shape.REMEDIATION` holding `git submodule update` and
# `validate-pins.py` in backticks. #494 left both with no known reach; #548
# makes it none.


@pytest.mark.parametrize("remedy", ["none", "lockstep"])
def test_a_refusal_a_check_lets_out_has_no_next_and_keeps_its_remedy(
        standard, project, remedy):
    """Both rows a refusal makes -- `run_checks`' FINDING for a check that
    lets one out, `placement_policy`'s `n/a` for a path policy that does not
    load -- have no NEXT, whatever the refusal carries. A remedy, where
    there is one, is the row's `why`, less its `Remediation:` label, so what
    it said is still printed, on a `WHY` line."""
    module = doctor_module(standard)
    carried = REMEDIATION if remedy == "lockstep" else ""

    def refused(_ctx):
        raise module.Refusal("probe-refused", "a check let this out", carried)

    class Unloadable:
        @staticmethod
        def load(path):
            raise module.Refusal("policy-refused", f"{path}: it does not load",
                                 carried)

    module.CHECKS = (module.Check("probe", "probe", (module.PROJECT,),
                                  refused),)
    ctx = module.Context(project.resolve())
    [escaped] = module.run_checks(ctx)
    ctx.adopt().PathPolicy = Unloadable
    _adopt, _policy, unread = module.placement_policy(
        ctx, standard / "contracts" / "path-classification.yaml")
    expected = (REMEDIATION.removeprefix("Remediation: ")
                if remedy == "lockstep" else None)
    for row in (escaped.as_dict(), unread.as_dict()):
        assert row["next"] is None, row
        assert row["why"] == expected, row
        assert_next_holds_no_prose(row)
    assert escaped.status == module.FINDING, escaped.as_dict()


def test_the_rows_guard_finds_a_backtick_or_a_remediation_in_a_next():
    """`assert_next_holds_no_prose`, which `rows_of` asks of every row the
    suite reads, shown to fail on each NEXT #548 and #408 were filed about
    and on prose that opens with `Remediation:`, and to pass a row with no
    NEXT and a command whose quoted path holds a backtick, which is a
    character of the path -- in each spelling `quote_arg` has for an
    apostrophe, `sh`'s `'\\''` and PowerShell's `''`."""
    for line in (FAMILY_BESIDE_NEXT_BEFORE_548, REMEDIATION,
                 "Remediation: run the gate again"):
        with pytest.raises(AssertionError):
            assert_next_holds_no_prose({"id": "before", "next": line})
    for line in (None, "git -C '/w/it`s here' status",
                 "git -C '/w/it'\\''s `here`' status",
                 "git -C 'C:\\it''s `here`' status"):
        assert_next_holds_no_prose({"id": "after", "next": line})


# --- the guard: no tail comes back -------------------------------------------

#: What the guard calls a tail: two or more blanks, or a tab, then `#`. The
#: house spelling was three spaces and a blank after the `#`; two, or a tab,
#: is the same comment to a shell, and the same word to an interactive zsh,
#: and so is a `#` with no blank after it, which zsh pastes as the first
#: character of an argument (#277, #679). A `#` that opens the literal text
#: after a part that is not a constant -- `f"{command}{pad}# x"` -- is a tail
#: too (`tail_runs`), because that part may be the blanks.
TAIL = re.compile(r"(?:[ \t]{2,}|\t)#")

#: The strings that may hold one, by the def they are written in -- its
#: whole path from the module, so a nested def or a method that shares the
#: name is not waved through -- and why: neither is a NEXT. `None` allows
#: every string in that def; text allows that one string and no other, so a
#: tail written anywhere else in `report` is still found. A line number
#: would move with every edit above it.
TAIL_ALLOWED = {
    # YAML comment lines, written into the placement plan.
    "placement_plan_leg": None,
    # `placement plan written to <file>   # nothing moved: ...`, a line of
    # the report and not a command.
    "report": "   # nothing moved: answer every `resolution:` before a repair "
              "runs it",
}


def pieces_of(node: ast.AST, parts: set[int]) -> list[str | None]:
    """A string expression read whole: its parts left to right, each the text
    of a constant, or `None` for a part that is not one -- a name, a call, a
    formatted value, a `*`.

    A `+` chain is read through to its ends and so is an f-string, so a tail
    spelled across them is one string here, as it is where it is printed.
    Every node read is added to `parts`, so that the walk does not read one
    of its pieces again on its own.
    """
    parts.add(id(node))
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        return [piece for value in node.values
                for piece in pieces_of(value, parts)]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return pieces_of(node.left, parts) + pieces_of(node.right, parts)
    if isinstance(node, ast.FormattedValue) and node.format_spec:
        # `{value:{width}#x}`: the spec's `#` is a flag, not a comment.
        parts.add(id(node.format_spec))
    return [None]


def tail_runs(pieces: list[str | None]) -> list[str]:
    """The runs of constant text in `pieces`, each between two parts that are
    not constants, that hold a `TAIL`, or that open with a `#` straight after
    such a part: it may be the blanks that make the tail.
    """
    runs: list[str] = []
    run, led = "", False
    for piece in [*pieces, None]:
        if piece is not None:
            run += piece
            continue
        if TAIL.search(run) or (led and run.startswith("#")):
            runs.append(run)
        run, led = "", True
    return runs


def tails_in(source: str) -> list[tuple[int, str, str]]:
    """`(line, def, text)` for every run of constant text in `source` that
    holds a tail (`tail_runs`) and is not a docstring, by the path of the defs
    it is written in (`outer/inner`, or `<module>`); the line is where the
    string expression begins.

    Each string expression is read whole (`pieces_of`): the pieces of an
    f-string and the ends of a `+` chain are one string, so a tail spelled
    after a `{command}`, or split between two constants, is found like any
    other. A run is the text between two parts that are not constants, so
    `TAIL_ALLOWED` names the same text it did when each constant was read
    alone.
    """
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and \
                    isinstance(first.value, ast.Constant) and \
                    isinstance(first.value.value, str):
                docstrings.add(id(first.value))
    found: list[tuple[int, str, str]] = []
    parts: set[int] = set()

    def visit(node, owner: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)):
                visit(child, child.name if owner == "<module>"
                      else f"{owner}/{child.name}")
                continue
            if isinstance(child, (ast.Constant, ast.JoinedStr, ast.BinOp)) \
                    and id(child) not in docstrings \
                    and id(child) not in parts:
                found.extend((child.lineno, owner, run) for run in
                             tail_runs(pieces_of(child, parts)))
            visit(child, owner)

    visit(tree, "<module>")
    return found


def disallowed(found: list[tuple[int, str, str]]) -> list:
    """The tails `TAIL_ALLOWED` does not allow."""
    return [(line, owner, text) for line, owner, text in found
            if owner not in TAIL_ALLOWED
            or TAIL_ALLOWED[owner] not in (None, text)]


def test_no_string_in_the_doctor_ends_a_command_with_a_comment():
    """The CLASS of the defect, for every builder, including later ones.

    Every NEXT is built from string constants in `shape-doctor.py`, so a
    tail in one is on its way to a NEXT. Two places hold that text for
    other reasons (`TAIL_ALLOWED`). A builder that wants to say why its
    command is the fix says it as the row's `why`.

    THE SCANNER IS SHOWN TO SEE ONE FIRST, on samples spelled the ways a
    tail can be -- three spaces after an f-string's `{command}`, two spaces,
    a tab, three spaces and a `#` with no blank after it (#679), a tail
    split across `+` (#679), one that opens with the `#` after a formatted
    value (#679), a second tail in `report` beside its allowed line, and one
    in a nested def that shares the name `report` -- beside a docstring that
    mentions one, a `#` with nothing before it, one blank and a format
    spec's `#` flag, none of which may count. And the real file yields
    exactly the allowed pair -- `placement_plan_leg`'s YAML comment and the
    one line in `report` -- so the guard is reading the strings it should.
    """
    sample = ('def builder(command):\n'
              '    """Its docstring may say `   # x`."""\n'
              '    return f"{command}   # a tail"\n'
              'def two(command):\n'
              '    return command + "  # two spaces"\n'
              'def tab(command):\n'
              '    return command + "\\t# a tab"\n'
              'def unspaced(command):\n'
              '    return command + "   #x"\n'
              'def split(command):\n'
              '    return command + "   " + "# x"\n'
              'def led(command, pad):\n'
              '    return f"{command}{pad}# x"\n'
              'def quiet(command, width):\n'
              '    lines = ["# a line of YAML", f"{command} # one blank"]\n'
              '    return lines, f"{command:{width}#x}"\n'
              'def report(plan):\n'
              f'    print(f"{{plan}}{TAIL_ALLOWED["report"]}")\n'
              '    print(f"{plan}   # a second one")\n'
              'def outer():\n'
              '    def report():\n'
              '        return "x   # nested"\n'
              '    return report\n')
    assert [(owner, text) for _, owner, text in
            disallowed(tails_in(sample))] == [
        ("builder", "   # a tail"), ("two", "  # two spaces"),
        ("tab", "\t# a tab"), ("unspaced", "   #x"), ("split", "   # x"),
        ("led", "# x"), ("report", "   # a second one"),
        ("outer/report", "x   # nested")]

    found = tails_in((REPO / DOCTOR).read_text(encoding="utf-8"))
    outside = disallowed(found)
    assert not outside, (
        f"{DOCTOR} builds a string with a `   #` tail at {outside}; an "
        "interactive zsh reads that `#` as a word and runs what follows it "
        "(#277). Pass the sentence as the row's `why=` instead.")
    assert {owner for _, owner, _ in found} == set(TAIL_ALLOWED), found
    assert [text for _, owner, text in found if owner == "report"] == [
        TAIL_ALLOWED["report"]], found
