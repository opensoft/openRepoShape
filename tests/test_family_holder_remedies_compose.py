# SPDX-License-Identifier: Apache-2.0
"""The family holder's pinned `scripts/validate-family.py` and
`scripts/bootstrap.py`: remedies that undid each other or refused when
typed as printed, a checkout `git mv` moved that nothing named, and `ok`
beside git's exit 128 (#879).

THE ISSUE'S FIVE LINES, each reproduced on #876's head (a7f6c569) before
this change, and the states beside them found with it:

- C1. Where the work tree's `.gitmodules` is gone, the wrong-case move's
  `git config -f .gitmodules submodule.<name>.path <row path>` made a file
  of that one key, which its `git add` staged: committed, HEAD lost every
  other section (rv876's P5e), and under `--no-members` a later
  `member-gitmodules-url-absent` put that staged file back over its own
  write (P5b). The move puts the file back first now, and no finding
  after it does. So does `member-gitlink-absent`'s own section lines
  (#681), whose one-section file was the same fault.
- C2. `member-gitlink-removal-staged` read "section taken" from the empty
  work tree and printed `git checkout HEAD -- .gitmodules` after a finding
  had put the file back and written a section there, which it took out
  again (P5d). It reads the file git reads now, puts nothing back after an
  earlier finding did, and where a plain `git rm` took its section out,
  writes that section back key by key into the file put back.
- C3. After a `gitmodules-value-refused` finding's lines, a stray's `git
  rm --cached` exited 128 (`please stage your changes to .gitmodules or
  stash them to proceed`, P5g), and so did a hand mount's `git rm` and the
  wrong-case move's `git rm -r --cached`. Each comes after `git add --
  .gitmodules` there now, as #878's do.
- C4. After the `git mv` state's lines were typed, the checkout `git mv`
  moved stayed at `Members/<P>`, untracked and named nowhere, so `family.py
  add` refused it, and after the update `git -C Members/<P> status` read
  the row's path. `member-gitlink-removal-staged` names it now, with that
  status, before its update.
- C5. With every member checked out, bootstrap said `family bootstrap ok`
  where git's update had exited 128, its init stopped at a gitlink it has
  no url for or at an unmerged `.gitmodules`. It fails now, naming the
  stop and its cure, with no credential advice.

Every remedy is typed as printed, in the order printed, split as a POSIX
shell splits it and run with no shell; then the gate is asked in every
mode, and a plain clone's `git submodule update --init --recursive` must
check out both members. A url a remedy writes is the one `family.py add`
writes, on GitHub, and the clone reaches the fixture's local remotes
through it by a `url.<base>.insteadOf` for the one command (`cloning`).
THE CONTROLS: the same states with the work tree's `.gitmodules` on disk,
or with no value finding before the `git rm`, print what they printed.

RV882'S ITEMS ON #882, TAKEN HERE (lane 2's review of #878): both of
`_stage_first`'s branches that print no `git add -- .gitmodules`, where
the work tree holds no file and where the index holds none (SHOULD 1);
`gitlink-unnamed` reading the paths from the file git reads where the
work tree's is gone (SHOULD 2); and `-f` over what is on disk at a staged
gitlink and is no checkout, a directory holding a file or a file, and
none over an empty directory, which git takes the plain line over (NIT
2). NIT 3's clause is in `STAGE_SAID`, which the C3 rows pin.

THE SAME FAMILY, OFFLINE RULES AND HELPERS as
`tests/test_family_holder_bootstrap_texts.py` (#839) and
`tests/test_family_unnamed_gitlink.py` (#878). A case variant is an index
record (`recorded_at`, `stage_gitlink`), but for the `git mv` states, which
need `Members/IRRS` apart from `members/IRRS` on disk and are skipped where
the disk folds case (`case_sensitive_disk`).
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

from conftest import rmtree, run_script
from test_family import FAMILY, SPARE, family, validate  # noqa: F401
from test_family_add_refusals import holder, offline  # noqa: F401
from test_family_bootstrap_gate_order import (
    OUTSIDE_CURE, STOPPED, UNMERGED, UNMERGED_CURE, UNNAMED_CURE, bootstrap,
    fetching, hand_mounted, stray, type_line, with_config, without_url,
)
from test_family_dry_run import isolated
from test_family_head_lost_gitmodules import (  # noqa: F401
    absent, assert_passes_in_every_mode, case_sensitive_disk, commit_all,
    committed_gitmodules, github_to, pinned, recorded_at,
    staged_and_committed, typed, variant_refused,
)
from test_family_holder_bootstrap_texts import (
    WORK, after_fetch_line, put_back_first, section_taken_out,
    unmerged_gitmodules,
)
from test_family_member_path import MEMBER, OTHER, raw
from test_family_remove_gitmodules import verb_args
from test_family_unnamed_gitlink import (
    COMMIT_THAT, FORCED_NO_HEAD, STAGE_LINE, STAGE_SAID, TAKE_OUT, TOOLS,
    assert_a_plain_clone_checks_out_every_member, at_tools,
    found_in_every_mode, outside, section_taken_out_alone, staged_at,
)
from test_validate_family_typed_states import (
    GONE, ROW, SECTION_GIVEN_BACK, URL_ABSENT, VARIANT_PATH, gone,
    unnamed_as_moved,
)
from test_validate_family_unnamed_mounts import (
    GITLINK_SAID, GITLINK_SAID_FETCHED, VARIANT, codes, commands, findings,
    spare_commits, stage_gitlink,
)

MODES = ((), ("--pins",), ("--no-members",))
GITMODULES = ".gitmodules"

#: What a remedy that writes `.gitmodules` says first where the work
#: tree's is gone, `{whose}` as `GONE` names it (C1).
PUT_BACK_THEN = (".gitmodules, gone from the work tree, back from {whose}, "
                 "so that every other section stays")


def cloning(offline, tmp_path: Path, family) -> dict:
    """The offline environment under which a plain clone checks the members
    out from the fixture's local remotes, through the GitHub url a remedy
    writes as `family.py add` writes one (`github_to`)."""
    key, value = github_to(family["remotes"])[1].split("=", 1)
    return with_config(fetching(isolated(offline, tmp_path)), key, value)


def typed_in_order(root: Path, env: dict, result) -> None:
    """Every `git` command every finding of `result` prints, typed as
    printed, in the order printed: not `family.py add`, which mounts a hand
    mount again only where the person wants it."""
    for finding in findings(result):
        for line in commands(finding):
            if line.startswith("git "):
                type_line(root, env, line)


def refusal_lines(result) -> list[str]:
    """The command lines a refusal prints, as printed."""
    return [line.strip() for line in result.stderr.splitlines()[2:]]


def found_alike(root: Path, *modes: tuple[str, ...]) -> list[str]:
    """The gate's findings, exit 1, the same in each of `modes`."""
    seen = []
    for extra in modes:
        result = validate(root, *extra)
        assert result.returncode == 1, (extra, result.stdout + result.stderr)
        seen.append(findings(result))
    assert all(found == seen[0] for found in seen), seen
    return seen[0]


def ends_well(root: Path, env: dict, family, tmp_path: Path) -> None:
    """The gate passes in every mode, and a plain clone checks out both
    members (#878's helper)."""
    assert_passes_in_every_mode(root, 2)
    assert_a_plain_clone_checks_out_every_member(root, env, family, tmp_path)


# --- C1: the wrong-case move where the work tree's .gitmodules is gone -------

def moved_in_head(root: Path, env: dict) -> str:
    """MEMBER's gitlink recorded only at `Members/IRRS`, and the section of
    HEAD's `.gitmodules` giving that path, as a committed `git mv` leaves
    them (rv876's P5e state), by index records. Returns the commit."""
    commit = recorded_at(root, env, MEMBER, VARIANT_PATH)
    data = raw(root, env, "show", f"HEAD:{GITMODULES}").stdout
    line = f"\tpath = {ROW}\n".encode()
    assert data.count(line) == 1, data
    committed_gitmodules(root, env, data.replace(
        line, f"\tpath = {VARIANT_PATH}\n".encode()))
    return commit


def moved_refused(commit: str, how: str | None) -> list[str]:
    """The members-mode refusal for `moved_in_head`'s state, with the line
    that puts `.gitmodules` back first where the work tree's is gone as
    `how` says (`GONE`), or none."""
    section = (f"git config -f .gitmodules submodule.{ROW}.path {ROW}",
               "git add -- .gitmodules")
    said = SECTION_GIVEN_BACK
    if how is not None:
        whose, line = GONE[how]
        section = (line, *section)
        said = f"put {PUT_BACK_THEN.format(whose=whose)}, then {said}"
    return variant_refused(ROW, commit, [VARIANT_PATH],
                           {VARIANT_PATH: commit}, section=section,
                           section_said=said)


@pytest.mark.parametrize("how", GONE)
def test_c1_the_move_puts_the_file_back_before_its_section_line(
        family, holder, offline, tmp_path, how):
    """C1, rv876's P5e. Members mode's refusal is printed alone; its `git
    config -f` line made a file of one key, which committed left HEAD with
    no other section. It puts the file back first now, from where git
    reads it. Typed as printed and committed, HEAD keeps OTHER's section,
    the gate passes in every mode and a plain clone checks both out."""
    env = cloning(offline, tmp_path, family)
    commit = moved_in_head(holder, env)
    gone(holder, env, how)

    refused = validate(holder)

    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert refused.stderr.splitlines() == moved_refused(commit, how)
    for line in refusal_lines(refused):
        type_line(holder, env, line)
    commit_all(holder, env, "Move the gitlink as printed")
    assert f'[submodule "members/{OTHER}"]'.encode() in raw(
        holder, env, "show", f"HEAD:{GITMODULES}").stdout
    ends_well(holder, env, family, tmp_path)


@pytest.mark.parametrize("how", GONE)
def test_c1_one_put_back_serves_the_move_and_a_url_finding_after_it(
        family, holder, offline, tmp_path, how):
    """C1, rv876's P5b: the same state with OTHER's url gone too. Under
    `--no-members` the move prints first, and `member-gitmodules-url-absent`
    after it put back the file the move had just staged, one key in it.
    The move puts the file back first now, and the url finding puts nothing
    back. Typed in order and committed, the gate passes in every mode and a
    plain clone checks both out."""
    env = cloning(offline, tmp_path, family)
    commit = moved_in_head(holder, env)
    data = raw(holder, env, "show", f"HEAD:{GITMODULES}").stdout
    committed_gitmodules(holder, env, without_url(data, OTHER))
    gone(holder, env, how)

    result = validate(holder, "--no-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert findings(result) == [
        unnamed_as_moved(VARIANT_PATH, commit, moved_refused(commit, how),
                         said=GITLINK_SAID_FETCHED),
        URL_ABSENT.format(commit=pinned(holder, OTHER))]
    typed_in_order(holder, env, result)
    staged_and_committed(holder, env, "Typed in order")
    ends_well(holder, env, family, tmp_path)


def test_c1_control_with_the_file_on_disk_the_move_is_as_it_was(
        family, holder, offline, tmp_path):
    """No misfire: the same state with the work tree's `.gitmodules` on
    disk. The move prints no put-back, as before; typed and committed, the
    gate passes in every mode."""
    env = cloning(offline, tmp_path, family)
    commit = moved_in_head(holder, env)

    refused = validate(holder)

    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert refused.stderr.splitlines() == moved_refused(commit, None)
    for line in refusal_lines(refused):
        type_line(holder, env, line)
    commit_all(holder, env, "Move the gitlink as printed")
    ends_well(holder, env, family, tmp_path)


@pytest.mark.parametrize("how", GONE)
def test_c1_the_absent_gitlink_s_section_lines_put_the_file_back_first(
        family, holder, offline, tmp_path, how):
    """C1's sibling, found with it: `member-gitlink-absent`'s own remedy
    (#681) for a member taken out by a plain `git rm`, committed, with the
    work tree's `.gitmodules` then gone. Its section lines made a file of
    MEMBER's section alone, so committed, HEAD lost OTHER's. The file is
    put back first now. Typed as printed, committed, and the member checked
    out as the text says, the gate passes in every mode."""
    env = cloning(offline, tmp_path, family)
    commit = pinned(holder, MEMBER)
    raw(holder, env, "rm", "-q", "--", ROW)
    commit_all(holder, env, "MEMBER taken out by hand")
    gone(holder, env, how)
    whose, line = GONE[how]

    refused = validate(holder)

    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert (f"with the lines after it, the first of which puts "
            f"{PUT_BACK_THEN.format(whose=whose)}, then stage .gitmodules. "
            in refused.stderr), refused.stderr
    assert refusal_lines(refused) == [
        f"git update-index --add --cacheinfo 160000,{commit},{ROW}", line,
        f"git config -f .gitmodules submodule.{ROW}.path {ROW}",
        f"git config -f .gitmodules submodule.{ROW}.url "
        f"https://github.com/InkRouter/{MEMBER}.git"]
    for line in refusal_lines(refused):
        type_line(holder, env, line)
    staged_and_committed(holder, env, "Put the member back as printed")
    raw(holder, env, "submodule", "update", "--init", "--recursive")
    ends_well(holder, env, family, tmp_path)


# --- C2: the removal staged, beside a finding that put the file back --------

@pytest.mark.parametrize("how", GONE)
def test_c2_the_removal_s_line_puts_nothing_back_over_an_earlier_write(
        family, holder, offline, tmp_path, how):
    """C2, rv876's P5d: `git rm --cached members/IRRS`, OTHER's section out
    of HEAD's `.gitmodules`, and the work tree's file gone. The absent
    finding puts the file back and writes OTHER's section; the removal's
    `git checkout HEAD -- .gitmodules`, read from the empty work tree, then
    took it out, so the commit had nothing to commit. It reads the file git
    reads now, which gives MEMBER's section, and prints no put-back. Typed
    in order and committed, the gate passes and a plain clone checks both
    out."""
    env = cloning(offline, tmp_path, family)
    data = raw(holder, env, "show", f"HEAD:{GITMODULES}").stdout
    committed_gitmodules(holder, env, section_taken_out(data, OTHER))
    raw(holder, env, "rm", "-q", "--cached", "--", ROW)
    gone(holder, env, how)

    found = found_alike(holder, *MODES)

    assert [finding.split(":", 1)[0] for finding in found] == [
        "FINDING member-gitmodules-absent",
        "FINDING member-gitlink-removal-staged"]
    assert found[0] == put_back_first(
        absent(OTHER, pinned(holder, OTHER), held=True), how)
    assert commands(found[1]) == [f"git reset -q -- {ROW}"]
    typed_in_order(holder, env, validate(holder, "--no-members"))
    staged_and_committed(holder, env, "Typed in order")
    ends_well(holder, env, family, tmp_path)


def url_of(root: Path, env: dict, path: str) -> str:
    """The url the section of HEAD's `.gitmodules` named `path` gives."""
    return raw(root, env, "config", "--blob", f"HEAD:{GITMODULES}",
               f"submodule.{path}.url").stdout.decode("utf-8").strip()


def test_c2_a_section_git_rm_took_is_written_back_into_the_file_put_back(
        family, holder, offline, tmp_path):
    """C2's other half, found with it: a plain `git rm members/IRRS`, which
    takes its section out of the work tree's `.gitmodules` and stages that,
    beside OTHER's section out of HEAD's, and the work tree's file then
    deleted. The absent finding puts back the index's, which lacks MEMBER's
    section, and the removal's `git checkout HEAD -- .gitmodules` took
    OTHER's out again. Now the removal writes MEMBER's section back, key by
    key as HEAD has it, into the file put back, before the update, which
    dies `No url found` without it. Typed in order and committed, the gate
    passes and a plain clone checks both out."""
    env = cloning(offline, tmp_path, family)
    data = raw(holder, env, "show", f"HEAD:{GITMODULES}").stdout
    committed_gitmodules(holder, env, section_taken_out(data, OTHER))
    member_url = url_of(holder, env, ROW)
    raw(holder, env, "rm", "-q", "--", ROW)
    gone(holder, env, "deleted")

    result = validate(holder, "--no-members")

    assert codes(result) == ["member-gitmodules-absent",
                             "member-gitlink-removal-staged"]
    removal = findings(result)[1]
    assert commands(removal) == [
        f"git reset -q -- {ROW}",
        f"git config -f .gitmodules submodule.{ROW}.path {ROW}",
        f"git config -f .gitmodules submodule.{ROW}.url "
        f"{shlex.quote(member_url)}",
        f"git submodule update --init --recursive -- {ROW}"]
    assert ("the first its gitlink, the second to the third the .gitmodules "
            "section git rm took out, key by key as HEAD has it, in the file "
            "a line above put back, the fourth its checkout, and nothing is "
            "left to commit.") in removal, removal
    typed_in_order(holder, env, result)
    staged_and_committed(holder, env, "Typed in order")
    ends_well(holder, env, family, tmp_path)


#: `(how the removal and the file's loss are made, the line the removal
#: prints for .gitmodules)`: the removal's own finding alone, where it is
#: the one that puts the file back.
ALONE_GONE = {
    "plain-rm-file-deleted": (
        lambda root, env: (raw(root, env, "rm", "-q", "--", ROW),
                           (root / GITMODULES).unlink()),
        "git checkout HEAD -- .gitmodules"),
    "cached-rm-deletion-staged": (
        lambda root, env: (raw(root, env, "rm", "-q", "--cached", "--", ROW),
                           raw(root, env, "rm", "-q", "--", GITMODULES)),
        "git checkout HEAD -- .gitmodules"),
    "cached-rm-file-deleted": (
        lambda root, env: (raw(root, env, "rm", "-q", "--cached", "--", ROW),
                           (root / GITMODULES).unlink()),
        "git checkout -- .gitmodules"),
}


@pytest.mark.parametrize("make, line", ALONE_GONE.values(), ids=ALONE_GONE)
def test_c2_a_removal_alone_puts_the_file_back_as_git_reads_it(
        family, holder, offline, tmp_path, make, line):
    """The removal's own finding, with no other before it, where the work
    tree's `.gitmodules` is gone: it puts the file back, from HEAD where a
    plain `git rm` took MEMBER's section out of the index's, else from
    where git reads it, so a deletion of `.gitmodules` staged beside the
    removal is undone too. Typed as printed, nothing is left to commit, and
    the gate passes in every mode."""
    env = cloning(offline, tmp_path, family)
    make(holder, env)

    (removal,) = found_alike(holder, *MODES)

    assert line in commands(removal)
    typed_in_order(holder, env, validate(holder, "--no-members"))
    assert raw(holder, env, "status", "--porcelain").stdout == b""
    ends_well(holder, env, family, tmp_path)


def test_c2_control_with_the_file_on_disk_the_removal_is_as_it_was(
        family, holder, offline, tmp_path):
    """No misfire: a plain `git rm members/IRRS` with the work tree's
    `.gitmodules` on disk prints what it printed: the reset, `git checkout
    HEAD -- .gitmodules` for the section `git rm` took out, and the
    update."""
    env = cloning(offline, tmp_path, family)
    raw(holder, env, "rm", "-q", "--", ROW)

    (removal,) = found_alike(holder, *MODES)

    assert commands(removal) == [
        f"git reset -q -- {ROW}", "git checkout HEAD -- .gitmodules",
        f"git submodule update --init --recursive -- {ROW}"]
    assert ("the first its gitlink, the second the .gitmodules section git "
            "rm took out, putting that file back as HEAD has it and dropping "
            "any other change to it, the third its checkout") in removal


# --- C3: a git rm of a gitlink after a value finding's lines ----------------

def value_committed(root: Path, env: dict) -> None:
    """MEMBER's section given `update = None`, committed (#768)."""
    data = raw(root, env, "show", f"HEAD:{GITMODULES}").stdout
    line = f"\tpath = {ROW}\n".encode()
    assert data.count(line) == 1, data
    committed_gitmodules(root, env,
                         data.replace(line, line + b"\tupdate = None\n"))


def staged_first(text: str) -> str:
    """`text` after #878's sentence that stages `.gitmodules` first."""
    said = STAGE_SAID + text
    return said[0].upper() + said[1:]


@pytest.mark.parametrize("value", [True, False], ids=["value", "control"])
def test_c3_the_stray_s_git_rm_stages_the_file_first_after_a_value(
        family, holder, offline, tmp_path, value):
    """C3, rv876's P5g: a committed `update = None`, and a stray gitlink at
    `Members/IRRS` staged with nothing on disk. The value finding's
    `--unset-all` leaves `.gitmodules` with changes not staged, and the
    stray's `git rm --cached` then exited 128. It comes after `git add --
    .gitmodules` now, in every mode, as #878's do. With no value finding
    before it, the control, it prints none. Typed in order, and the value's
    fix committed, nothing is left, the gate passes and a plain clone
    checks both out."""
    env = cloning(offline, tmp_path, family)
    if value:
        value_committed(holder, env)
    commit = pinned(holder, MEMBER)
    stage_gitlink(holder, VARIANT_PATH, commit)
    take = (staged_first(TAKE_OUT) + COMMIT_THAT + ":" + STAGE_LINE if value
            else f"Take{TAKE_OUT[4:]}{COMMIT_THAT}:")

    found = found_alike(holder, *MODES)

    assert found[-1] == (
        GITLINK_SAID.format(path=VARIANT_PATH, commit=commit)
        + VARIANT.format(row_path=ROW, project=MEMBER) + f" {take}"
        + f"\n    git rm --cached -- {VARIANT_PATH}")
    typed_in_order(holder, env, validate(holder, "--no-members"))
    if value:
        staged_and_committed(holder, env, "Typed in order")
    assert raw(holder, env, "status", "--porcelain").stdout == b""
    ends_well(holder, env, family, tmp_path)


def test_c3_a_hand_mount_s_git_rm_stages_the_file_first_after_a_value(
        family, holder, offline, tmp_path):
    """C3's sibling, found with it: a hand mount's plain `git rm`, after
    the value finding's lines, exited 128 too. `git add -- .gitmodules`
    comes before it now, the second of the four, and the text counts the
    others on. Typed in order to the removal, and committed, the gate
    passes and a plain clone checks both out."""
    env = cloning(offline, tmp_path, family)
    value_committed(holder, env)
    path = hand_mounted(holder, env, family)

    result = validate(holder, "--no-members")

    assert codes(result) == ["gitmodules-value-refused",
                             "member-gitlink-unnamed"]
    mount = findings(result)[1]
    switch, stage, removal, add = commands(mount)
    assert (stage, removal) == ("git add -- .gitmodules", f"git rm -- {path}")
    assert (", stage .gitmodules with the second, which stages every other "
            "change in it too, since git rm refuses to take any gitlink out "
            "of the index") in mount
    assert ("take it out with the third, which refuses while its checkout "
            "holds changes") in mount
    assert "then mount it with the fourth, " in mount
    assert add.startswith("python3 scripts/family.py add "), add
    for line in commands(findings(result)[0]) + [switch, stage, removal]:
        type_line(holder, env, line)
    staged_and_committed(holder, env, "Typed in order")
    ends_well(holder, env, family, tmp_path)


def test_c3_the_wrong_case_move_s_git_rm_stages_the_file_first_after_a_value(
        family, holder, offline, tmp_path):
    """C3's sibling, found with it: the wrong-case move under
    `--no-members`, after the value finding's lines: its `git rm -r
    --cached` exited 128, and its `update-index` then left the gitlink at
    both paths. `git add -- .gitmodules` comes first now. Typed in order
    and committed, the gate passes and a plain clone checks both out."""
    env = cloning(offline, tmp_path, family)
    value_committed(holder, env)
    commit = recorded_at(holder, env, MEMBER, VARIANT_PATH)

    result = validate(holder, "--no-members")

    assert codes(result) == ["gitmodules-value-refused",
                             "member-gitlink-unnamed"]
    move = findings(result)[1]
    assert commands(move) == [
        "git add -- .gitmodules",
        f"git rm -r --cached --ignore-unmatch -- {VARIANT_PATH}",
        f"git update-index --add --cacheinfo 160000,{commit},{ROW}"]
    assert (" The member is recorded in the wrong case. "
            + staged_first("move its gitlink to the row's path, at the "
                           "commit the row pins, in the index alone, which "
                           "touches no file, with the next two lines, and "
                           "commit that.")) in move
    typed_in_order(holder, env, result)
    staged_and_committed(holder, env, "Typed in order")
    ends_well(holder, env, family, tmp_path)


# --- C4: the checkout git mv moved ------------------------------------------

#: What `member-gitlink-removal-staged` says of the checkout `git mv` moved
#: to `Members/IRRS`, before its update (C4).
MOVED = (
    " The checkout git mv moved to {variant} stays there, untracked, and "
    "family.py add refuses it as family-members-dir-variant: its .git file "
    "names the member's store under this holder's .git/modules/ by a path "
    "relative to it, and its commits are kept there whatever becomes of the "
    "checkout, so only what is not committed is in the checkout alone, which "
    "`git -C {variant} status` shows. Delete it by hand once nothing only it "
    "holds is needed, before the last line: that update points the store at "
    "{path}, after which `git -C {variant} status` reads {path} instead.")

#: The `git mv` states: nothing more, and #876's two.
MOVES = {"clean": lambda checkout, env: None, **WORK}


@pytest.mark.parametrize("work", MOVES.values(), ids=MOVES)
def test_c4_the_checkout_git_mv_moved_is_named_before_the_update(
        family, holder, offline, tmp_path, case_sensitive_disk, work):
    """C4, in the three `git mv` states rv876 measured: `git mv
    members/IRRS Members/IRRS`, staged, clean, with a commit, or with an
    untracked file in the checkout it moved. After the lines were typed,
    `Members/IRRS` stayed, untracked and named nowhere, `family.py add`
    refused it, and the update made its status read `members/IRRS`. The
    removal's finding names it now, in every mode, with `git -C
    Members/IRRS status` before the update. Typed in order, with that
    status read and the checkout deleted by hand before the last line as
    the text says, nothing is left untracked, the gate passes, `family.py
    add` takes the spare member, the commit is in the member's store, and a
    plain clone checks both out."""
    env = cloning(offline, tmp_path, family)
    (holder / "Members").mkdir()
    raw(holder, env, "mv", ROW, VARIANT_PATH)
    work(holder / VARIANT_PATH, env)
    made = raw(holder / VARIANT_PATH, env, "rev-parse", "HEAD").stdout

    found = found_alike(holder, *MODES)

    assert ("and nothing is left to commit."
            + MOVED.format(variant=VARIANT_PATH, path=ROW)
            + " If it is to go,") in found[-1], found[-1]
    lines = [line for finding in found for line in commands(finding)]
    assert lines[-1] == f"git submodule update --init --recursive -- {ROW}"
    for line in lines[:-1]:
        type_line(holder, env, line)
    status = raw(holder, env, "-C", VARIANT_PATH, "status", "--porcelain")
    assert (b"?? scratch.txt\n" in status.stdout) is (work is WORK.get(
        "untracked")), status.stdout
    rmtree(holder / VARIANT_PATH)
    type_line(holder, env, lines[-1])
    assert raw(holder, env, "status", "--porcelain").stdout == b""
    store = holder / ".git" / "modules" / ROW
    assert raw(holder, env, f"--git-dir={store}", "cat-file", "-e",
               made.decode("ascii").strip(), check=False).returncode == 0
    added = run_script(FAMILY, *verb_args("add", holder, family),
                       "--dry-run", env=env)
    assert added.returncode == 0, added.stdout + added.stderr
    ends_well(holder, env, family, tmp_path)


# --- C5: bootstrap with every member checked out ----------------------------

#: What (a) says where every row's member is checked out and git updated
#: none of them, and how the run then ends (C5).
NONE_UPDATED = ("  NO MEMBER UPDATED, and not for want of a credential: "
                "{why}. {cure}")
STOP_FAILED = "family bootstrap FAILED: {path} (git stopped at it)"


def outside_gitlink(root: Path, env: dict, family) -> str:
    """SPARE's gitlink recorded by hand at `vendor/IRQS`, outside
    `members/`, with no section, and committed. Returns its path."""
    stage_gitlink(root, f"vendor/{SPARE}", spare_commits(family)[1])
    commit_all(root, env, "A gitlink mounted by hand outside members/")
    return f"vendor/{SPARE}"


#: `(how the stop is made in the holder, every member checked out, what
#: the line says cures it)`: each a gitlink git's init has no url for.
STOPS = {
    "outside": (outside_gitlink, OUTSIDE_CURE),
    "stray": (stray, UNNAMED_CURE),
    "hand-mount": (hand_mounted, UNNAMED_CURE),
}


@pytest.mark.parametrize("make, cure", STOPS.values(), ids=STOPS)
def test_c5_a_stop_with_every_member_checked_out_fails_naming_it(
        family, holder, offline, tmp_path, make, cure):
    """C5: every member checked out, as in the holder itself, and a gitlink
    git's init has no url for, at which `git submodule update --init`
    exited 128 before it updated any member. Bootstrap gave the credential
    advice and said ok. It names the stop now, with its cure, gives no
    advice, and fails on the gitlink. The gate's remedy for that gitlink
    typed as printed and committed, the run ends ok and a plain clone
    checks both out."""
    env = cloning(offline, tmp_path, family)
    path = make(holder, env, family)

    result = bootstrap(holder, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert after_fetch_line(result) == [
        NONE_UPDATED.format(why=STOPPED.format(path=path),
                            cure=cure.format(path=path)),
        STOP_FAILED.format(path=path)]
    typed_in_order(holder, env, validate(holder, "--no-members"))
    commit_all(holder, env, "The gate's remedy, typed as printed")
    booted = bootstrap(holder, env, "--skip-members")
    assert booted.stdout.endswith("\nfamily bootstrap ok\n"), (
        booted.stdout + booted.stderr)
    ends_well(holder, env, family, tmp_path)


def test_c5_a_bad_line_after_the_first_section_fails_naming_a_stop(
        family, holder, offline, tmp_path):
    """C5, the issue's own state (RV877's O1): every member checked out, a
    line git cannot parse committed in HEAD's `.gitmodules` after the first
    section, and the work tree's file deleted. Git reads the index's up to
    that line and dies `No url found` at the second member. Bootstrap said
    ok with the advice. It fails now on the gitlink it stopped at, with no
    advice: which one is the blob's reading, #877's (#856), so either
    member's path is taken here."""
    env = cloning(offline, tmp_path, family)
    data = (holder / GITMODULES).read_bytes()
    first = data.index(b"[submodule", 1)
    bad = (chr(9) + 'branch = "unterminated' + chr(10)).encode("ascii")
    committed_gitmodules(holder, env, data[:first] + bad + data[first:])
    (holder / GITMODULES).unlink()

    result = bootstrap(holder, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    said = after_fetch_line(result)
    assert said[0].startswith(
        "  NO MEMBER UPDATED, and not for want of a credential: git stopped "
        "at members/"), said
    assert re.fullmatch(rf"family bootstrap FAILED: members/({MEMBER}|"
                        rf"{OTHER}) \(git stopped at it\)", said[1]), said


def test_c5_an_unmerged_file_with_every_member_checked_out_fails(
        family, holder, offline, tmp_path):
    """C5's unmerged case: every member checked out, and `.gitmodules` held
    only at a merge's conflict stages, which git reads nothing from, so its
    init died at the first gitlink. Bootstrap said ok. It says why and the
    merge's cure now, and fails on `.gitmodules`; resolved and added as the
    cure says, the run ends ok."""
    env = cloning(offline, tmp_path, family)
    unmerged_gitmodules(holder, env)

    result = bootstrap(holder, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert after_fetch_line(result) == [
        NONE_UPDATED.format(why=UNMERGED, cure=UNMERGED_CURE),
        "family bootstrap FAILED: .gitmodules (git cannot read it)"]
    raw(holder, env, "add", GITMODULES)
    booted = bootstrap(holder, env, "--skip-members")
    assert booted.stdout.endswith("\nfamily bootstrap ok\n"), (
        booted.stdout + booted.stderr)


def test_c5_control_the_holder_as_made_bootstraps_ok(family, holder, offline,
                                                     tmp_path):
    """No misfire: the holder as `family.py` made it, every member checked
    out and nothing that stops git's init. Asking `init_stop` with no row
    left finds nothing, and the run ends ok, saying every member and leg
    was fetched, with nothing on stderr."""
    env = cloning(offline, tmp_path, family)

    result = bootstrap(holder, env, "--skip-members")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "  every member and leg fetched" in result.stdout.splitlines()
    assert result.stderr == ""


# --- rv882's items on #882, taken here ---------------------------------------

#: What the `-f` sentence says is on disk at a gitlink with no `.git` entry
#: there (rv882's NIT 2), in place of "a checkout".
OVER_FILES = "what is on disk there, which is no checkout"


def head_paths(root: Path, env: dict) -> set[str]:
    """Every path a section of HEAD's `.gitmodules` gives."""
    listed = raw(root, env, "config", "--blob", f"HEAD:{GITMODULES}",
                 "--get-regexp", r"\.path$").stdout.decode("utf-8")
    return {line.split(" ", 1)[1] for line in listed.splitlines()}


def test_rv882_should_1_no_git_add_where_the_work_tree_holds_no_file(
        family, holder, offline, tmp_path):
    """rv882's SHOULD 1 on #882: (D), the gitlink at tools/x that no
    section gives, with the work tree's `.gitmodules` deleted and not
    staged. No `git add -- .gitmodules` is printed, in any mode: it would
    stage that deletion, the commit after it deleted the file from HEAD,
    and a plain clone stopped at members/IRRS. Typed as printed and
    committed, HEAD's `.gitmodules` still gives both members, the gate
    passes in every mode and a plain clone checks both out."""
    env = cloning(offline, tmp_path, family)
    section_taken_out_alone(holder, env, family)
    gone(holder, env, "deleted")

    finding = found_in_every_mode(holder, "gitlink-unnamed")

    assert finding == outside(TOOLS, staged_at(holder, env, TOOLS),
                              COMMIT_THAT)
    typed(holder, env, finding)
    commit_all(holder, env, "Typed as printed")
    assert head_paths(holder, env) == {ROW, f"members/{OTHER}"}
    ends_well(holder, env, family, tmp_path)


def test_rv882_should_1_no_git_add_where_the_index_holds_no_file(
        family, holder, offline, tmp_path):
    """rv882's SHOULD 1, the other branch: (D) with `.gitmodules` on disk
    and its removal staged (`git rm --cached`), so the index holds none.
    No `git add -- .gitmodules` is printed: it would stage the file again
    over the removal the person staged. The `git rm --cached` alone, typed
    as printed, exits 0, and the staged removal stays as it was."""
    env = cloning(offline, tmp_path, family)
    section_taken_out_alone(holder, env, family)
    raw(holder, env, "rm", "-q", "--cached", "--", GITMODULES)

    finding = found_in_every_mode(holder, "gitlink-unnamed")

    assert finding == outside(TOOLS, staged_at(holder, env, TOOLS),
                              COMMIT_THAT)
    typed(holder, env, finding)
    staged = raw(holder, env, "diff", "--cached", "--name-status").stdout
    assert staged == f"D\t{GITMODULES}\nD\t{TOOLS}\n".encode(), staged


@pytest.mark.parametrize("how", GONE)
def test_rv882_should_2_a_gitlink_the_file_git_reads_gives_is_no_finding(
        family, holder, offline, tmp_path, how):
    """rv882's SHOULD 2 on #882: (A), IRSS mounted at tools/x with `git
    submodule add` and committed, with the work tree's `.gitmodules` gone.
    The index's or HEAD's file, which git reads in its place, gives tools/x
    a section, and a plain clone checks it out, while `gitlink-unnamed`
    said that no section gave it. The paths are read from the file git
    reads now: no mode finds `gitlink-unnamed`, and the gate passes."""
    env = cloning(offline, tmp_path, family)
    at_tools(holder, env, family)
    gone(holder, env, how)

    assert_passes_in_every_mode(holder, 2)


def on_disk_under(root: Path, path: str) -> list[str]:
    """Every entry on disk under `path`, and its bytes where it is a file."""
    return sorted((str(entry.relative_to(root)),
                   entry.read_bytes() if entry.is_file() else b"")
                  for entry in [root / path, *(root / path).rglob("*")])


def files_at(root: Path, path: str) -> None:
    """A directory at `path` that holds a file and no `.git`."""
    (root / path).mkdir(parents=True)
    (root / path / "kept.txt").write_bytes(b"kept\n")


def a_file_at(root: Path, path: str) -> None:
    """A file at `path`."""
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_bytes(b"kept\n")


def an_empty_directory_at(root: Path, path: str) -> None:
    """An empty directory at `path`."""
    (root / path).mkdir(parents=True)


#: `(what is on disk at tools/x, the flag its git rm --cached carries, what
#: the text says of it)`: git 2.43 refused the plain line over the first
#: two and took it over the third (rv882's NIT 2).
ON_DISK = {
    "a-directory-holding-a-file": (files_at, " -f", FORCED_NO_HEAD.replace(
        "over a checkout", f"over {OVER_FILES}")),
    "a-file": (a_file_at, " -f", FORCED_NO_HEAD.replace(
        "over a checkout", f"over {OVER_FILES}")),
    "an-empty-directory": (an_empty_directory_at, "", COMMIT_THAT),
}


@pytest.mark.parametrize("make, flag, said", ON_DISK.values(), ids=ON_DISK)
def test_rv882_nit_2_a_gitlink_staged_over_what_is_no_checkout(
        family, holder, offline, tmp_path, make, flag, said):
    """rv882's NIT 2 on #882: IRQS's gitlink staged by hand at tools/x,
    HEAD recording nothing there, over a directory holding a file and no
    `.git`, or a file. Git refused the plain `git rm --cached` there
    (`staged content different from both the file and the HEAD`, exit 1),
    and `_forced` asked for a `.git` entry alone, so no `-f` was printed.
    It is now, with what is on disk there; over an empty directory, which
    git takes the plain line over, it is not. Typed as printed, the line
    exits 0 and leaves what was on disk; the gate passes in every mode and
    a plain clone checks both out."""
    env = cloning(offline, tmp_path, family)
    make(holder, TOOLS)
    commit = spare_commits(family)[1]
    stage_gitlink(holder, TOOLS, commit)
    before = on_disk_under(holder, "tools")

    finding = found_in_every_mode(holder, "gitlink-unnamed")

    assert finding == outside(TOOLS, commit, said, flag)
    typed(holder, env, finding)
    assert on_disk_under(holder, "tools") == before
    ends_well(holder, env, family, tmp_path)


def test_rv882_nit_2_the_move_takes_f_over_what_is_no_checkout(
        family, holder, offline, tmp_path, case_sensitive_disk):
    """rv882's NIT 2, in the wrong-case move, which asks `_forced` too:
    MEMBER recorded only at `Members/IRRS` and committed, then staged
    there at another commit, over a directory holding a file and no
    `.git`. The move's `git rm -r --cached` carries `-f` now, and says
    what is on disk there; typed as printed and committed, it exits 0,
    leaves the file, and the gate passes in members mode."""
    env = cloning(offline, tmp_path, family)
    commit = recorded_at(holder, env, MEMBER, VARIANT_PATH)
    other = spare_commits(family)[1]
    stage_gitlink(holder, VARIANT_PATH, other)
    files_at(holder, VARIANT_PATH)

    refused = validate(holder)

    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert refused.stderr.splitlines() == [
        line.replace("over a checkout", f"over {OVER_FILES}")
        for line in variant_refused(ROW, commit, [VARIANT_PATH],
                                    {VARIANT_PATH: other},
                                    forced=(VARIANT_PATH,))]
    for line in refusal_lines(refused):
        type_line(holder, env, line)
    commit_all(holder, env, "Moved as printed")
    assert (holder / VARIANT_PATH / "kept.txt").read_bytes() == b"kept\n"
    assert validate(holder).returncode == 0
