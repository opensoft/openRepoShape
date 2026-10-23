# SPDX-License-Identifier: Apache-2.0
"""The family root's `validate-family.py`: a gitlink outside `members/`
that no row names, and the `gitmodules-path-unnamed` remedy that left one
(#878).

THE ISSUE'S LINE, reproduced on #876's head (77f8a6c8) before this change:
`git submodule add <IRSS> tools/x`, committed, or IRSS added at
`Members/IRRS` and moved by hand with `git mv` to `renamed-1`, committed.
The gate exited 1 in every mode, `gitmodules-path-unnamed`, and printed
only the `--unset-all` lines that take the section out. Typed as printed,
with `.gitmodules` staged and committed, the gate exited 0 in every mode,
while `git submodule status` exited 128 (`no submodule mapping found`)
and a plain clone's `git submodule update --init --recursive` exited 128
(`No url found for submodule path`) with no member checked out: the
gate's gitlinks were read in `members/` alone, so no mode asked about the
one the lines left.

ITS THREE DIRECTIONS, each held here:

- The section's finding prints the `git rm --cached` that takes its
  gitlink out of the index first, and the commit, then its own lines.
- A gitlink outside `members/` that no section gives is a finding of its
  own, `gitlink-unnamed`, whose `git rm --cached` is the one bootstrap's
  `init_stop` cure names for it.
- Where the index stages that gitlink at a commit HEAD does not record
  and a checkout is on disk at it, the `git rm` takes `-f`, with what
  `-f` does, as #876's `_forced` gives it: git refused it there (`staged
  content different from both the file and the HEAD`, exit 1).

Each remedy is typed as printed, split as a POSIX shell splits it and run
with no shell, then the gate is asked in every mode; where HEAD changed, a
plain clone's `git submodule update --init --recursive` must check out
both members and `git submodule status` exit 0 there and in the holder.
WHERE LINES PRINTED BEFORE IT WRITE `.gitmodules` (a value finding's, in
the order #879's C3 names for a stray's `git rm --cached`, or an earlier
unnamed section's), or the file holds a hand edit not staged, git refused
#878's `git rm --cached` (`please stage your changes to .gitmodules or
stash them to proceed`, exit 128), so `git add -- .gitmodules` comes
directly before it there, and every line is typed in the order printed.
THE CONTROLS: the holder as `family.py` made it, a member under
`members/` with its section and its row, and a section with no gitlink,
or none in the index, which prints its own lines alone, as it did.

THE SAME FAMILY, OFFLINE RULES AND HELPERS as
`tests/test_family_holder_bootstrap_texts.py` (#839) and
`tests/test_validate_family_unnamed_mounts.py` (#361). A checkout is git's
own, made by `git submodule add` from the fixture's local remotes; a state
with no checkout is an index record (`stage_gitlink`). The `git mv` form
needs `Members/IRRS` apart from `members/IRRS` on disk, and is skipped
where the disk folds case (`case_sensitive_disk`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import git
from test_family import family, validate  # noqa: F401
from test_family_add_refusals import holder, offline  # noqa: F401
from test_family_bootstrap_gate_order import cloned, fetching, type_line
from test_family_dry_run import isolated
from test_family_head_lost_gitmodules import (  # noqa: F401
    FORCED_SAID, assert_passes_in_every_mode, case_sensitive_disk,
    commit_all, staged_and_committed, typed,
)
from test_family_holder_bootstrap_texts import WORK
from test_family_member_path import MEMBER, OTHER, raw
from test_validate_family_remedies_typed import STAGED
from test_validate_family_unnamed_mounts import (
    SECTION_REMEDY, SECTION_SAID, STAGE, codes, commands, findings, removal,
    spare_commits, stage_gitlink, with_section,
)

#: The gitlink outside `members/` the issue mounts IRSS at, the case
#: variant of MEMBER's path it mounts it at for the `git mv`, and where
#: that moves it.
TOOLS = "tools/x"
VARIANT = f"Members/{MEMBER}"
RENAMED = "renamed-1"

#: `gitlink-unnamed` up to what it says of its `git rm --cached`. A
#: holder's CI matches on text, so it is pinned here and not rebuilt from
#: the gate's own strings.
OUTSIDE_SAID = (
    "FINDING gitlink-unnamed: {path} is a gitlink at {commit}, outside "
    "members/, that no section of .gitmodules gives, so in a plain clone of "
    "this holder git submodule update --init stops there (No url found for "
    "submodule path, exit 128) before it checks out any member, and a "
    "recursive clone checks out nothing at it. No row names {path} and no "
    "clone can check it out. ")

#: What every text says first of the `git rm --cached` it prints.
TAKE_OUT = "take it out of the index alone, which touches no file"

#: What it says first where lines printed before it may leave `.gitmodules`
#: with changes not staged, or it holds some, and the line it prints for
#: that: git takes no gitlink out of the index then (#879's C3), and the
#: line stages every other change in the file too (rv882's NIT 3).
STAGE_SAID = ("stage .gitmodules with the first line, which stages every "
              "other change in it too, since git rm refuses to "
              "take any gitlink out of the index, -f or not, while "
              ".gitmodules holds changes not staged (please stage your "
              "changes to .gitmodules or stash them to proceed, exit 128), "
              "as lines printed above may leave it or as it stands, then ")
STAGE_LINE = "\n    git add -- .gitmodules"

#: What it says next, by what `_forced` reads: the commit; or `-f`, where
#: the index stages the gitlink at a commit HEAD does not record there
#: (`FORCED_OVER`), or where HEAD records nothing (`FORCED_NO_HEAD`), over
#: a checkout. `{line}` names the line that takes it.
COMMIT_THAT = ", and commit that"
FORCED_OVER = (", and commit that. The index stages it at a commit HEAD "
               "does not record there over a checkout, so {line} takes -f: "
               + FORCED_SAID)
FORCED_NO_HEAD = (": HEAD records nothing there, so nothing of it is left to "
                  "commit. The index stages it over a checkout, so {line} "
                  "takes -f: " + FORCED_SAID)

#: What `gitmodules-path-unnamed` says of a section no row names, before
#: what it says to do.
ROW_BACK = (" If its row was deleted or its path: edited by hand, put the "
            "row back as git last had it.")

#: What it says of the gitlink at a section's path outside `members/`,
#: which it takes out first, then of the section.
GITLINK_FIRST = (
    " Otherwise take its gitlink out first, since a gitlink no section "
    "gives stops a plain clone's git submodule update --init (No url found "
    "for submodule path, exit 128) before it checks out any member: ")
SECTION_THEN = (" Then, with the lines after it, take the section out by "
                "hand, in a POSIX shell, every key it holds, so a submodule "
                "later given its name inherits none of them, {then}:")

#: How the section's text ends: the file staged and committed, or, where
#: HEAD's `.gitmodules` holds no section of its name, staged and nothing to
#: commit. Its lines end `git add -- .gitmodules` either way (#1077,
#: RV1069's NIT 3 on #1069).
THEN_COMMIT = "then stage and commit .gitmodules"
THEN_STAGE = ("then stage .gitmodules: HEAD's holds no section of that name, "
              "so nothing of it is left to commit")


def outside(path: str, commit: str, said: str, flag: str = "", *,
            stage: bool = False) -> str:
    """`gitlink-unnamed` whole for the gitlink at `path`, at `commit`:
    `said` (`COMMIT_THAT`, `FORCED_OVER` or `FORCED_NO_HEAD`) of its `git
    rm --cached`, which carries `flag`, after `git add -- .gitmodules`
    where `stage`."""
    first = STAGE_SAID + TAKE_OUT if stage else TAKE_OUT
    return (OUTSIDE_SAID.format(path=path, commit=commit)
            + first[0].upper() + first[1:]
            + said.format(line="the second line" if stage else "the line")
            + ":" + (STAGE_LINE if stage else "")
            + f"\n    git rm --cached{flag} -- {path}")


def section_first(path: str, name: str, url: str, said: str, then: str,
                  flag: str = "", *, stage: bool = False) -> str:
    """`gitmodules-path-unnamed` whole for the section `name`, giving `path`
    and `url`, at a gitlink outside `members/`: its `git rm --cached`,
    carrying `flag`, after `git add -- .gitmodules` where `stage`, of which
    it says `said`, then its own lines, and `then`, the lines ending `git
    add -- .gitmodules` (#1077)."""
    nth = "the second line" if stage else "the first line"
    return (SECTION_SAID.format(path=path, name=name, url=f"url {url}")
            + ROW_BACK + GITLINK_FIRST + (STAGE_SAID if stage else "")
            + f"{TAKE_OUT}, with {nth}" + said.format(line=nth) + "."
            + SECTION_THEN.format(then=then) + (STAGE_LINE if stage else "")
            + f"\n    git rm --cached{flag} -- {path}"
            + "".join(f"\n    {line}" for line in removal(name, "path",
                                                           "url"))
            + STAGE_LINE)


def found_in_every_mode(root: Path, code: str) -> str:
    """The one finding the gate prints, `code`'s, the same in every mode."""
    seen: set[str] = set()
    for extra in ((), ("--pins",), ("--no-members",)):
        result = validate(root, *extra)
        assert result.returncode == 1, (extra, result.stdout + result.stderr)
        assert codes(result) == [code], (extra, result.stderr)
        seen.update(findings(result))
    (finding,) = seen
    return finding


def staged_at(root: Path, env: dict, path: str) -> str:
    """The commit the index stages the gitlink at `path` at."""
    return raw(root, env, "rev-parse", f":{path}").stdout.decode(
        "ascii").strip()


def section_url(root: Path, env: dict, name: str) -> str:
    """The url the work tree's `.gitmodules` gives the section `name`."""
    return raw(root, env, "config", "-f", ".gitmodules", "--get",
               f"submodule.{name}.url").stdout.decode("utf-8").strip()


def assert_a_plain_clone_checks_out_every_member(root: Path, env: dict,
                                                 family, tmp_path: Path
                                                 ) -> None:
    """`git submodule status` exits 0 in `root`; a plain clone of its HEAD,
    then `git submodule update --init --recursive`, exits 0 there with both
    members checked out, and `git submodule status` exits 0 there too."""
    raw(root, env, "submodule", "status")
    clone = cloned(root, env, family, tmp_path, recurse=False)
    raw(clone, env, "submodule", "update", "--init", "--recursive")
    for project in (MEMBER, OTHER):
        assert (clone / "members" / project / ".git").exists(), project
    raw(clone, env, "submodule", "status")


def submodule_added(root: Path, env: dict, family, path: str) -> None:
    """IRSS mounted at `path` by `git submodule add`, not committed."""
    raw(root, env, "submodule", "add", "-q", "--",
        str(family["remotes"] / "IRSS.git"), path)


# --- the issue's two states --------------------------------------------------

def at_tools(root: Path, env: dict, family) -> tuple[str, str]:
    """`git submodule add <IRSS> tools/x`, committed. Returns the section's
    name and the path it gives."""
    submodule_added(root, env, family, TOOLS)
    commit_all(root, env, "IRSS mounted at tools/x by hand")
    return TOOLS, TOOLS


def moved_to_renamed(root: Path, env: dict, family) -> tuple[str, str]:
    """IRSS added at `Members/IRRS`, committed, then moved by hand with
    `git mv` to `renamed-1`, committed: git gives its section that path
    under the name it had."""
    submodule_added(root, env, family, VARIANT)
    commit_all(root, env, "IRSS mounted at Members/IRRS by hand")
    raw(root, env, "mv", "--", VARIANT, RENAMED)
    commit_all(root, env, "Moved by hand to renamed-1")
    return VARIANT, RENAMED


#: `(how the state is made, whether it needs a disk that keeps case)`.
FORMS = {"tools-x": (at_tools, False),
         "git-mv-to-renamed-1": (moved_to_renamed, True)}


@pytest.mark.parametrize("form, keeps_case", FORMS.values(), ids=FORMS)
def test_a_section_s_remedy_takes_its_gitlink_out_first(
        family, holder, offline, tmp_path, request, form, keeps_case):
    """THE ISSUE'S LINE, both forms. The section's finding, in every mode,
    prints the `git rm --cached` of its gitlink first, and the commit, then
    the `--unset-all` lines it printed alone. Typed as printed, with
    `.gitmodules` staged and committed, the gate passes in every mode, and
    a plain clone checks out both members: the lines alone left the
    gitlink, and its update exited 128 at it."""
    if keeps_case:
        request.getfixturevalue("case_sensitive_disk")
    env = fetching(isolated(offline, tmp_path))
    name, path = form(holder, env, family)

    finding = found_in_every_mode(holder, "gitmodules-path-unnamed")

    assert finding == section_first(path, name,
                                    section_url(holder, env, name),
                                    COMMIT_THAT, THEN_COMMIT)
    typed(holder, env, finding)
    staged_and_committed(holder, env, "Typed as printed")
    assert_passes_in_every_mode(holder, 2)
    assert_a_plain_clone_checks_out_every_member(holder, env, family,
                                                 tmp_path)


def section_taken_out_alone(root: Path, env: dict, family) -> None:
    """THE STATE THE OLD REMEDY LEFT: tools/x's section taken out by the
    lines `gitmodules-path-unnamed` printed alone, staged and committed."""
    at_tools(root, env, family)
    for line in removal(TOOLS, "path", "url"):
        type_line(root, env, line)
    staged_and_committed(root, env, "The section taken out alone")


def test_a_gitlink_outside_members_no_section_gives_is_a_finding(
        family, holder, offline, tmp_path):
    """THE NEW FINDING, in the state the old remedy left, where every mode
    said `family ok` while a plain clone's update stopped at the gitlink.
    It names it in every mode, with bootstrap's `git rm --cached`; typed as
    printed and committed, the gate passes in every mode, and a plain
    clone checks out both members."""
    env = fetching(isolated(offline, tmp_path))
    section_taken_out_alone(holder, env, family)
    before = cloned(holder, env, family, tmp_path / "before", recurse=False)
    stopped = raw(before, env, "submodule", "update", "--init", "--recursive",
                  check=False)
    assert stopped.returncode == 128, "premise: a plain clone stops there"

    finding = found_in_every_mode(holder, "gitlink-unnamed")

    assert finding == outside(TOOLS, staged_at(holder, env, TOOLS),
                              COMMIT_THAT)
    typed(holder, env, finding)
    commit_all(holder, env, "Typed as printed")
    assert_passes_in_every_mode(holder, 2)
    assert_a_plain_clone_checks_out_every_member(holder, env, family,
                                                 tmp_path)


# --- -f where git refuses the plain git rm --cached --------------------------

def added_not_committed(root: Path, env: dict, family, work) -> None:
    """rv865b's (a): `git submodule add <IRSS> tools/x`, not committed,
    with `work` in its checkout. HEAD records nothing there."""
    submodule_added(root, env, family, TOOLS)
    work(root / TOOLS, env)


def moved_on(root: Path, env: dict, work) -> None:
    """A commit in tools/x's checkout, staged in the holder, where HEAD
    records the one before it, then `work` in that checkout."""
    raw(root / TOOLS, env, "commit", "-q", "--allow-empty", "-m",
        "Moved on")
    raw(root, env, "add", "--", TOOLS)
    work(root / TOOLS, env)


def committed_then_moved_on(root: Path, env: dict, family, work) -> None:
    at_tools(root, env, family)
    moved_on(root, env, work)


def no_section_then_moved_on(root: Path, env: dict, family, work) -> None:
    section_taken_out_alone(root, env, family)
    moved_on(root, env, work)


#: `(how the state is made, the finding's code, what it says of its -f,
#: how the section's text ends, or None for the gitlink's own finding)`.
FORCED = {
    "section-added-not-committed": (added_not_committed,
                                    "gitmodules-path-unnamed",
                                    FORCED_NO_HEAD, THEN_STAGE),
    "section-committed-moved-on": (committed_then_moved_on,
                                   "gitmodules-path-unnamed", FORCED_OVER,
                                   THEN_COMMIT),
    "no-section-moved-on": (no_section_then_moved_on, "gitlink-unnamed",
                            FORCED_OVER, None),
}


@pytest.mark.parametrize("work", WORK.values(), ids=WORK)
@pytest.mark.parametrize("make, code, said, then", FORCED.values(),
                         ids=FORCED)
def test_a_gitlink_staged_over_a_checkout_is_taken_out_with_f(
        family, holder, offline, tmp_path, make, code, said, then, work):
    """DIRECTION 3: the index stages tools/x at a commit HEAD does not
    record there, or where HEAD records nothing, and a checkout is on disk
    at it that has moved on or holds a file git does not track. The plain
    `git rm --cached` refuses there, exit 1, and changes nothing; the line
    takes `-f`, in every mode, and says what it does. Typed as printed,
    then staged and committed as the text says, or staged where it says
    nothing is left to commit, the gate passes in every mode, the checkout
    is still on disk, and where HEAD changed a plain clone checks out both
    members."""
    env = fetching(isolated(offline, tmp_path))
    make(holder, env, family, work)
    refused = raw(holder, env, "rm", "-q", "--cached", "--", TOOLS,
                  check=False)
    assert refused.returncode == 1, "premise: the plain git rm refuses"

    finding = found_in_every_mode(holder, code)

    assert finding == (
        outside(TOOLS, staged_at(holder, env, TOOLS), said, " -f")
        if then is None else
        section_first(TOOLS, TOOLS, section_url(holder, env, TOOLS), said,
                      then, " -f"))
    typed(holder, env, finding)
    if then == THEN_STAGE:
        raw(holder, env, "add", "--", ".gitmodules")
        raw(holder, env, "diff", "--cached", "--quiet")
    else:
        staged_and_committed(holder, env, "Typed as printed")
        assert_a_plain_clone_checks_out_every_member(holder, env, family,
                                                     tmp_path)
    assert_passes_in_every_mode(holder, 2)
    assert (holder / TOOLS / ".git").is_file(), "-f touched no file"


# --- after lines that write .gitmodules, git add first (#879's C3) ----------

def value_first(root: Path, env: dict, family) -> str:
    """#879's C3 order, before this finding: MEMBER's section given
    `update = None`, committed, beside the state the old remedy left, so
    the value finding's `--unset-all` line prints first. Returns the text
    the gitlink's finding prints whole."""
    section_taken_out_alone(root, env, family)
    raw(root, env, "config", "-f", ".gitmodules",
        f"submodule.members/{MEMBER}.update", "None")
    staged_and_committed(root, env, "update = None")
    return outside(TOOLS, staged_at(root, env, TOOLS), COMMIT_THAT,
                   stage=True)


def earlier_section_first(root: Path, env: dict, family) -> str:
    """A section no row names, for tools/y, with no gitlink, committed
    before tools/x is added: its `--unset-all` lines print first."""
    for key, value in (("path", "tools/y"), ("url", "/nowhere/y.git")):
        raw(root, env, "config", "-f", ".gitmodules",
            f"submodule.tools/y.{key}", value)
    staged_and_committed(root, env, "A section for tools/y")
    at_tools(root, env, family)
    return section_first(TOOLS, TOOLS, section_url(root, env, TOOLS),
                         COMMIT_THAT, THEN_COMMIT, stage=True)


def hand_edit_first(root: Path, env: dict, family) -> str:
    """tools/x added and committed, then `.gitmodules` edited by hand, not
    staged."""
    at_tools(root, env, family)
    gitmodules = root / ".gitmodules"
    gitmodules.write_bytes(gitmodules.read_bytes() + b"# a hand edit\n")
    return section_first(TOOLS, TOOLS, section_url(root, env, TOOLS),
                         COMMIT_THAT, THEN_COMMIT, stage=True)


#: `(how the state is made, which returns the text #878's finding prints
#: last, the codes printed in order)`: lines printed before #878's `git rm
#: --cached` write `.gitmodules`, or it holds a change not staged.
STAGE_FIRST = {
    "value-finding-first": (value_first, ["gitmodules-value-refused",
                                          "gitlink-unnamed"]),
    "earlier-section-first": (earlier_section_first,
                              ["gitmodules-path-unnamed",
                               "gitmodules-path-unnamed"]),
    "hand-edit-not-staged": (hand_edit_first, ["gitmodules-path-unnamed"]),
}


@pytest.mark.parametrize("make, printed", STAGE_FIRST.values(),
                         ids=STAGE_FIRST)
def test_after_lines_that_write_gitmodules_its_git_rm_stages_it_first(
        family, holder, offline, tmp_path, make, printed):
    """#879's C3, for #878's own line. Git takes no gitlink out of the
    index, `-f` or not, while `.gitmodules` holds changes not staged
    (`please stage your changes to .gitmodules or stash them to proceed`,
    exit 128), as a value finding's `--unset-all` lines leave it, or an
    earlier unnamed section's, or a hand edit. So `git add -- .gitmodules`
    comes directly before #878's `git rm --cached`, in every mode, and says
    why. Every line of every finding typed in the order printed, with
    nothing between, then `.gitmodules` staged and committed: the gate
    passes in every mode, and a plain clone checks out both members."""
    env = fetching(isolated(offline, tmp_path))
    expected = make(holder, env, family)

    for extra in ((), ("--pins",), ("--no-members",)):
        result = validate(holder, *extra)
        assert codes(result) == printed, (extra, result.stderr)
        assert findings(result)[-1] == expected, extra
    for finding in findings(result):
        typed(holder, env, finding)
    staged_and_committed(holder, env, "Typed as printed, in order")
    assert_passes_in_every_mode(holder, 2)
    assert_a_plain_clone_checks_out_every_member(holder, env, family,
                                                 tmp_path)


# --- where no git rm is printed, or once -------------------------------------

def test_a_gitlink_outside_members_whose_removal_is_staged_says_commit_it(
        family, holder):
    """`gitlink-unnamed` for a gitlink HEAD records and the index no longer
    holds: its `git rm` fails there (`pathspec ... did not match`), so it
    prints none and says to commit the removal; committed, the gate passes
    in every mode."""
    _, tip = spare_commits(family)
    stage_gitlink(holder, TOOLS, tip)
    git("commit", "-qm", "A gitlink recorded by hand at tools/x",
        cwd=holder)
    git("rm", "-q", "--cached", "--", TOOLS, cwd=holder)

    finding = found_in_every_mode(holder, "gitlink-unnamed")

    assert finding == (OUTSIDE_SAID.format(path=TOOLS, commit=tip) + STAGED
                       + " Commit that removal.")
    git("commit", "-qm", "The removal committed", cwd=holder)
    assert_passes_in_every_mode(holder, 2)


def test_two_sections_for_one_gitlink_outside_members_print_one_git_rm(
        family, holder, offline, tmp_path):
    """Two sections give tools/x (`gitmodules-path-twice`): the first
    section's finding prints the gitlink's `git rm --cached`, and the
    second its own lines alone, since that `git rm` typed again fails.
    Every line typed as printed, `.gitmodules` staged and committed, the
    gate passes in every mode."""
    _, tip = spare_commits(family)
    stage_gitlink(holder, TOOLS, tip)
    with_section(holder, tmp_path, TOOLS, TOOLS, "/nowhere/x.git")
    with_section(holder, tmp_path, "second", TOOLS, "/nowhere/second.git")

    result = validate(holder, "--no-members")

    assert codes(result) == ["gitmodules-path-twice",
                             "gitmodules-path-unnamed",
                             "gitmodules-path-unnamed"], result.stderr
    first, second = findings(result)[1:]
    assert commands(first) == [f"git rm --cached -- {TOOLS}",
                               *removal(TOOLS, "path", "url"), STAGE]
    assert commands(second) == [*removal("second", "path", "url"), STAGE]
    env = isolated(offline, tmp_path)
    for finding in (first, second):
        typed(holder, env, finding)
    staged_and_committed(holder, env, "Typed as printed")
    assert_passes_in_every_mode(holder, 2)


# --- the controls ------------------------------------------------------------

def test_the_holder_as_made_passes_and_a_plain_clone_checks_it_out(
        family, holder, offline, tmp_path):
    """CONTROL: a member under `members/` with its section and its row,
    two of them, as `init` and `add` made the holder."""
    assert_passes_in_every_mode(holder, 2)
    assert_a_plain_clone_checks_out_every_member(
        holder, fetching(isolated(offline, tmp_path)), family, tmp_path)


@pytest.mark.parametrize("recorded", [False, True],
                         ids=["no-gitlink", "gitlink-removal-staged"])
def test_a_section_with_no_gitlink_in_the_index_prints_its_lines_alone(
        family, holder, offline, tmp_path, recorded):
    """CONTROL: a section no row names, at tools/x, where the index holds
    no gitlink, prints what it printed before, its `--unset-all` lines
    alone, in every mode: there is no gitlink, or one HEAD records whose
    removal is staged, where a `git rm` fails. Typed as printed, staged
    and committed, the gate passes in every mode."""
    env = isolated(offline, tmp_path)
    if recorded:
        stage_gitlink(holder, TOOLS, spare_commits(family)[1])
    with_section(holder, tmp_path, TOOLS, TOOLS, "/nowhere/x.git")
    if recorded:
        git("rm", "-q", "--cached", "--", TOOLS, cwd=holder)

    finding = found_in_every_mode(holder, "gitmodules-path-unnamed")

    assert finding == (
        SECTION_SAID.format(path=TOOLS, name=TOOLS, url="url /nowhere/x.git")
        + SECTION_REMEDY + "".join(f"\n    {line}" for line in [*removal(
            TOOLS, "path", "url"), STAGE]))
    typed(holder, env, finding)
    staged_and_committed(holder, env, "Typed as printed")
    assert_passes_in_every_mode(holder, 2)
