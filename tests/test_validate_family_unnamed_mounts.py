# SPDX-License-Identifier: Apache-2.0
"""`validate-family.py` finds a gitlink in `members/`, and a `.gitmodules`
section, whose path no `members:` row names, in every mode (#361).

EVERY CHECK STARTED FROM A ROW. `_check_members` walked `members:` and asked
each row for its gitlink, digest and identity, and nothing walked back from
what the holder records to a row. So a member mounted by hand with `git
submodule add`, a row deleted by hand, the section `family.py remove` leaves
of two for one path (#360), and a section for `Members/IRRS`, which `add`
commits beside the member's own, all passed the holder's own gate, and the
doctor, which runs that gate, called the holder COMPLIANT.

TWO FINDINGS, each with its own code, both made before the `--no-members`
return, as `member-duplicate` (#331) is, since a private family's CI falls
back to that mode: `member-gitlink-unnamed` for a gitlink, read from the
index at stage 0, else HEAD, the order `recorded_gitlink` reads one in, and
`gitmodules-path-unnamed` for a section, read as git reads the file, as
`gitmodules-path-twice` (#300) reads it. "Unnamed" is decided EXACTLY, as
git compares paths. A path a row names in another case is still a finding,
and it names that row: macOS and Windows hold the two as one directory.

A PATH THAT FOLDS TO A ROW'S is one of three things, and what it says to run
depends on which (review of #406, SHOULD-1). A SECOND path to the member's own
directory is taken out with `git rm --cached`. A row HAND-EDITED into a case
variant of its own mount (`path: Members/IRSS` over a mount at
`members/IRSS`) is the row's fault, and a member whose ONLY record is at a
case variant (`members/irss`, the row saying `members/IRSS`) is recorded in
the wrong case: the same command, run in either, takes the member's own
record out of the index, after which `--no-members`, the run a private
family's CI falls back to, says `family ok` over a member that is no longer
there. Those two print no command.

When a hand mount's gitlink says to `git rm` it, its section finding says that
the `git rm` takes the section out too and prints no `--unset-all` line: run
after it they exit 5, the keys being gone.

The same family and the same offline rules as `tests/test_family.py`, whose
fixture is imported. EVERY STATE BUT ONE IS BUILT IN GIT'S INDEX AND
OBJECTS, never through a checkout, so each runs on all three platforms: a
gitlink is an index record written as bytes on stdin (`update-index
--index-info`), and a section is appended to `.gitmodules` by
`tests/test_family_add_refusals.py`'s `gitmodules_with`, which hashes the
file's bytes the same way. The one exception runs the printed remedy, and
mounts the spare member for real with `git submodule add`, as
`tests/test_validate_family_duplicates.py` does, because what that remedy
must clear is what a real mount leaves.

THE CASE-VARIANT STATES HOLD ON macOS AND WINDOWS the same way: a disk that
folds case makes `members/IRSS` and `members/irss` one directory, so none of
them puts a second directory on disk. A gitlink is only ever an index record
(`stage_gitlink`, `git rm --cached`) and a commit of the index, which reads no
directory, so the checkout of `members/IRSS` stays the one directory it is and
the index says whichever spelling the test wants. A section is hashed into
the objects and the one `.gitmodules` file is written beside it, and the one
hand edit, `family.yaml`, is a single file written as bytes.
"""

from __future__ import annotations

import shlex
import subprocess

import pytest

from conftest import git, rmtree, run_script
from repo_shape import PYTHON
from test_family import (  # noqa: F401
    FAMILY, ORG, SPARE, family, family_module, holder, manifest, validate,
)
from test_family_add_refusals import git_section, gitmodules_with
from test_validate_family_member_path_glob import hand_edit

MODES = pytest.mark.parametrize(
    "extra", [(), ("--pins",), ("--no-members",)],
    ids=["members-checked", "pins", "no-members"])

#: What every unnamed gitlink says after its path and commit, and what one
#: that is NOT a case variant of a row's path says to do about it. A
#: holder's CI matches on text, so it is pinned here and not rebuilt from the
#: validator's own strings.
GITLINK_SAID = (
    "FINDING member-gitlink-unnamed: {path} is a gitlink at {commit} that "
    "no row of members: names, so a recursive clone of this holder fetches "
    "it and nothing here pins, digests or identifies it.")
GITLINK_REMEDY = (
    " If its row was deleted or its path: edited by hand, put the row back "
    "as git last had it (git log -p -- family.yaml shows the change). If it "
    "was mounted by hand, make a branch with the first command below, since "
    "family.py add refuses the holder's tracking branch, take it out with "
    "the second, which refuses while its checkout holds changes and takes "
    "its .gitmodules section out too, then mount it with the third, from a "
    "checkout of openRepoShape: family.py add writes its row and its gitlink "
    "in one commit, and names the object store git rm leaves under "
    ".git/modules if one is still there.")


def switch_for(holder, member: str) -> str:
    """The first command a hand mount's gitlink prints (#539): the branch
    `family.py add` suggests for `member`, in this holder."""
    return (f"git -C {shlex.quote(str(holder.resolve()))} switch -c "
            f"family/add-{member.lower()}")

#: The same two halves for an unnamed `.gitmodules` section.
SECTION_SAID = (
    "FINDING gitmodules-path-unnamed: .gitmodules gives the path {path} to "
    "the submodule named \"{name}\" ({url}), and no row of members: names "
    "that path, so nothing pins what it registers, and the next family.py "
    "add of its name or its path meets it.")
SECTION_REMEDY = (
    " If its row was deleted or its path: edited by hand, put the row back "
    "as git last had it. Otherwise take the section out by hand, in a POSIX "
    "shell, every key it holds, so a submodule later given its name inherits "
    "none of them, then commit .gitmodules:")

#: What a path a row names in another case adds, in place of the "deleted
#: or edited" sentence: the row it belongs to.
VARIANT = (" It is a case variant of {row_path}, which the row for "
           "{project} names, and macOS and Windows hold the two as one "
           "directory.")

#: What a path that is the member's own, in a row hand-edited into a case
#: variant of it, says: the row is the hand edit, and no command. `{what}` is
#: `gitlink` or `section`.
ROW_EDITED = (
    " It is {path}, the one path the row for {project} may have, and the row "
    "names it as {row_path} instead, which macOS and Windows hold as one "
    "directory with it. The row's path: is the hand edit and this {what} is "
    "the member's own: put {path} back in the row's path: (git log -p -- "
    "family.yaml shows the change). No command is printed, since this {what} "
    "is not what is wrong.")

#: What the only record of a member, in the wrong case, says: no command, and
#: the restore sentence the unnamed gitlink always had.
WRONG_CASE = (
    VARIANT + " The member is recorded in the wrong case, so no command is "
    "printed: taking this {what} out could un-register it. If its row was "
    "deleted or its path: edited by hand, put the row back as git last had "
    "it (git log -p -- family.yaml shows the change).")

#: What a hand mount's section says once its gitlink's `git rm` takes it out.
SECTION_UNDER_GIT_RM = (
    " If its row was deleted or its path: edited by hand, put the row back as "
    "git last had it. Otherwise the git rm printed above for the gitlink at "
    "{path} takes this section out too, so no command is printed here.")


def findings(result) -> list[str]:
    """Every finding WHOLE, in the order printed: its `FINDING` line and
    each indented line under it, the commands a remedy prints."""
    found: list[list[str]] = []
    for line in result.stderr.splitlines():
        if line.startswith("FINDING "):
            found.append([line])
        elif found and line.startswith(" "):
            found[-1].append(line)
    return ["\n".join(lines) for lines in found]


def codes(result) -> list[str]:
    """The code of every finding, in the order printed."""
    return [finding.split(":", 1)[0][len("FINDING "):]
            for finding in findings(result)]


def commands(finding: str) -> list[str]:
    """The commands a finding prints, one to an indented line."""
    return [line.strip() for line in finding.splitlines()[1:]]


def stage_gitlink(root, path: str, commit: str) -> None:
    """A gitlink at `path` in `root`'s index and nowhere else: an index
    record written as BYTES on stdin, so no disk has to hold `path` and no
    clone is made. `--index-info` replaces a record already there."""
    subprocess.run(["git", "update-index", "--add", "--index-info"],
                   cwd=str(root), capture_output=True, check=True,
                   input=f"160000 {commit}\t{path}\n".encode("utf-8"))


def stage_unmerged_gitlink(root, path: str, commit: str) -> None:
    """A gitlink at `path` held at the conflict stages 1, 2 and 3 and NOT at
    stage 0, as a conflicted merge leaves it. As BYTES on stdin, like
    `stage_gitlink`: first the zero-mode record that drops any stage-0 entry
    (`--index-info` will not place a higher stage over one), then the three
    stages."""
    records = f"0 {'0' * 40}\t{path}\n" + "".join(
        f"160000 {commit} {stage}\t{path}\n" for stage in (1, 2, 3))
    subprocess.run(["git", "update-index", "--index-info"], cwd=str(root),
                   capture_output=True, check=True,
                   input=records.encode("utf-8"))


def commit(root, message: str) -> None:
    git("commit", "-qm", message, cwd=root)


def record_in_another_case(holder, project: str, spelling: str) -> str:
    """`project`'s gitlink taken out of the index at its own path, recorded at
    `spelling` instead, and committed: in the index and objects alone, so no
    disk has to hold both names and the checkout does not move. Returns the
    commit the gitlink names."""
    named = pinned(holder, project)
    git("rm", "-q", "--cached", "--", f"members/{project}", cwd=holder)
    stage_gitlink(holder, spelling, named)
    commit(holder, f"Record {project} at {spelling}")
    return named


def spare_commits(family) -> tuple[str, str]:
    """The spare member's two commits, older first: real commits a gitlink
    can name, though the holder never mounts them."""
    work = family["work"] / SPARE
    older, newer = (git("rev-parse", rev, cwd=work).stdout.strip()
                    for rev in ("HEAD~1", "HEAD"))
    return older, newer


def pinned(holder, project: str) -> str:
    return next(row["pin"]["commit"] for row in manifest(holder)["members"]
                if row["project"] == project)


def with_path_replaced(holder, old: bytes, new: bytes) -> None:
    """HEAD's `.gitmodules` with `old` replaced by `new` (once), hashed into
    git's objects and committed, and the same bytes written to disk:
    `gitmodules_with`'s mechanics for an edit in place rather than an append,
    as BYTES, so no platform rewrites a line ending."""
    data = subprocess.run(["git", "show", "HEAD:.gitmodules"],
                          cwd=str(holder), capture_output=True,
                          check=True).stdout
    assert data.count(old) == 1, data
    data = data.replace(old, new)
    blob = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                          cwd=str(holder), input=data, capture_output=True,
                          check=True).stdout.decode("ascii").strip()
    git("update-index", "--cacheinfo", f"100644,{blob},.gitmodules",
        cwd=holder)
    commit(holder, "A section whose path is another case")
    (holder / ".gitmodules").write_bytes(data)


def with_section(holder, tmp_path, name: str, path: str, url: str) -> None:
    """`[submodule "<name>"]` giving `path` and `url`, appended to HEAD's
    `.gitmodules` in git's objects and committed, with the same bytes on
    disk."""
    gitmodules_with(holder, git_section(tmp_path / "section", name,
                                        path=path, url=url), "the work tree")


def removal(name: str, *keys: str) -> list[str]:
    """The commands that take every key of section `name` out, as printed."""
    return [f"git config -f .gitmodules --unset-all "
            f"{shlex.quote(f'submodule.{name}.{key}')}" for key in keys]


def take_out_as_printed(holder, finding: str) -> None:
    """Run every command `finding` prints, split as a POSIX shell splits it
    and run with no shell, then commit `.gitmodules`, as it says."""
    for command in commands(finding):
        argv = shlex.split(command)
        assert argv[0] == "git", command
        git(*argv[1:], cwd=holder)
    git("add", "--", ".gitmodules", cwd=holder)
    commit(holder, "Take the section out as printed")


def assert_passes_in_every_mode(holder, members: int) -> None:
    for extra in ((), ("--pins",), ("--no-members",)):
        result = validate(holder, *extra)
        assert result.returncode == 0, (extra, result.stderr + result.stdout)
        assert (f"family ok: InkRouter (inkrouter), {members} member(s)"
                in result.stdout), extra


# --- the issue's three rows --------------------------------------------------

@MODES
def test_a_member_mounted_by_hand_is_two_findings(family, holder, tmp_path,
                                                  extra):
    """ROW (a): what `git submodule add` of a member leaves, with no row: a
    gitlink in `members/` that every recursive clone fetches, and the
    section that registers it. Neither is named, so each is its own
    finding, in every mode: neither needs the member checked out.

    The gitlink says to `git rm` it, and that takes its section out too, so
    the section's finding says that and prints no `--unset-all` line: run
    after the `git rm` they exit 5, the keys being gone."""
    _, tip = spare_commits(family)
    stage_gitlink(holder, f"members/{SPARE}", tip)
    with_section(holder, tmp_path, f"members/{SPARE}", f"members/{SPARE}",
                 f"/nowhere/{SPARE}.git")
    result = validate(holder, *extra)
    assert result.returncode == 1, result.stderr + result.stdout
    assert "REFUSED" not in result.stderr, result.stderr
    gitlink, section = findings(result)
    assert gitlink.splitlines()[0] == GITLINK_SAID.format(
        path=f"members/{SPARE}", commit=tip) + GITLINK_REMEDY
    assert commands(gitlink) == [
        switch_for(holder, SPARE),
        f"git rm -- members/{SPARE}",
        f"{PYTHON} scripts/family.py add --family-root "
        f"{shlex.quote(str(holder.resolve()))} --member <org>/{SPARE}"]
    assert section == SECTION_SAID.format(
        path=f"members/{SPARE}", name=f"members/{SPARE}",
        url=f"url /nowhere/{SPARE}.git") + SECTION_UNDER_GIT_RM.format(
            path=f"members/{SPARE}")
    assert commands(section) == []
    assert "--unset-all" not in result.stderr


@MODES
def test_a_section_no_row_names_is_a_finding(holder, tmp_path, extra):
    """ROW (b): a section with no row and no gitlink, the state `family.py
    remove` leaves when the file held two sections for one path (#360). A
    clone does not follow it, but the next `add` of its name or its path
    meets it, so it is a finding, in every mode."""
    with_section(holder, tmp_path, "members/Old", "members/Old",
                 "/nowhere/old.git")
    result = validate(holder, *extra)
    assert result.returncode == 1, result.stderr + result.stdout
    (section,) = findings(result)
    assert section.splitlines()[0] == SECTION_SAID.format(
        path="members/Old", name="members/Old",
        url="url /nowhere/old.git") + SECTION_REMEDY
    assert commands(section) == removal("members/Old", "path", "url")


@MODES
def test_a_section_for_a_case_variant_of_a_members_path_names_that_row(
        holder, tmp_path, extra):
    """ROW (c): a section under another name for `Members/IRRS`, beside
    IRRS's own for `members/IRRS`. git compares the two paths exactly, so
    `add` committed IRRS's section beside it and `gitmodules-path-twice`
    does not pair them, but on macOS and Windows they are one directory.
    So it is unnamed, decided exactly, and the finding names the row whose
    path it is the variant of."""
    with_section(holder, tmp_path, "ghost", "Members/IRRS",
                 "/nowhere/ghost.git")
    result = validate(holder, *extra)
    assert result.returncode == 1, result.stderr + result.stdout
    (section,) = findings(result)
    assert section.splitlines()[0] == (
        SECTION_SAID.format(path="Members/IRRS", name="ghost",
                            url="url /nowhere/ghost.git")
        + VARIANT.format(row_path="members/IRRS", project="IRRS")
        + " Take the section out by hand, in a POSIX shell, every key it "
        "holds, so a submodule later given its name inherits none of them, "
        "then commit .gitmodules:")
    assert commands(section) == removal("ghost", "path", "url")


# --- the two findings' edges -------------------------------------------------

@MODES
def test_a_gitlink_at_a_case_variant_of_a_members_path_names_that_row(
        holder, extra):
    """A gitlink at `Members/IRRS` beside IRRS's at `members/IRRS`, in the
    index only, so the same on every disk. Its directory IS IRRS's where
    case is folded, so its remedy is `git rm --cached`, which touches no
    file, and never the plain `git rm` that would take IRRS's checkout with
    it there."""
    commit_ = pinned(holder, "IRRS")
    stage_gitlink(holder, "Members/IRRS", commit_)
    result = validate(holder, *extra)
    assert result.returncode == 1, result.stderr + result.stdout
    (gitlink,) = findings(result)
    assert gitlink.splitlines()[0] == (
        GITLINK_SAID.format(path="Members/IRRS", commit=commit_)
        + VARIANT.format(row_path="members/IRRS", project="IRRS")
        + " Take it out of the index alone, which touches no file, and "
        "commit that:")
    assert commands(gitlink) == ["git rm --cached -- Members/IRRS"]


def test_the_case_variant_remedy_run_as_printed_clears_it_and_no_file(holder):
    """Run as printed, it takes the variant out of the index and leaves
    IRRS's checkout and gitlink as they were, and the holder passes."""
    stage_gitlink(holder, "Members/IRRS", pinned(holder, "IRRS"))
    (gitlink,) = findings(validate(holder, "--no-members"))
    (command,) = commands(gitlink)
    git(*shlex.split(command)[1:], cwd=holder)
    assert (holder / "members" / "IRRS" / "project.yaml").is_file()
    assert_passes_in_every_mode(holder, 2)


def test_a_gitlink_is_read_from_the_index_first_and_from_head_second(
        family, holder):
    """THE ORDER `recorded_gitlink` READS ONE. A gitlink HEAD records at one
    commit and the index stages at another is reported at the staged one,
    which the next commit will record; once the index no longer holds it,
    HEAD's is the gitlink, and it is still a finding until a commit drops
    it."""
    older, newer = spare_commits(family)
    path = f"members/{SPARE}"
    stage_gitlink(holder, path, older)
    commit(holder, "A gitlink no row names")
    stage_gitlink(holder, path, newer)
    (staged,) = findings(validate(holder, "--no-members"))
    assert staged.startswith(GITLINK_SAID.format(path=path, commit=newer))
    git("rm", "-q", "--cached", "--", path, cwd=holder)
    (committed,) = findings(validate(holder, "--no-members"))
    assert committed.startswith(GITLINK_SAID.format(path=path, commit=older))
    commit(holder, "Drop it")
    assert_passes_in_every_mode(holder, 2)


def test_only_members_is_asked_about(family, holder):
    """`members/` in any case, and nothing beside it: a gitlink elsewhere
    in the holder is not a member's mount, and no row could name it."""
    _, tip = spare_commits(family)
    stage_gitlink(holder, f"tools/{SPARE}", tip)
    stage_gitlink(holder, f"membersX/{SPARE}", tip)
    stage_gitlink(holder, f"MEMBERS/{SPARE}", tip)
    result = validate(holder, "--no-members")
    assert result.returncode == 1, result.stderr + result.stdout
    (gitlink,) = findings(result)
    assert gitlink.startswith(GITLINK_SAID.format(path=f"MEMBERS/{SPARE}",
                                                  commit=tip))


def test_a_removed_row_is_named_by_its_gitlink_and_its_section(holder):
    """A row deleted by hand leaves the member's gitlink and its section,
    and both are found; putting the row back, as both say, clears them."""
    text = (holder / "family.yaml").read_bytes()
    rows = manifest(holder)["members"]
    irss = next(row for row in rows if row["project"] == "IRSS")
    family_module().Family.open(holder).write_members(
        [row for row in rows if row["project"] != "IRSS"])
    result = validate(holder, "--no-members")
    assert result.returncode == 1, result.stderr + result.stdout
    assert codes(result) == ["member-gitlink-unnamed",
                             "gitmodules-path-unnamed"]
    assert findings(result)[0].startswith(GITLINK_SAID.format(
        path="members/IRSS", commit=irss["pin"]["commit"]) + GITLINK_REMEDY)
    (holder / "family.yaml").write_bytes(text)
    assert_passes_in_every_mode(holder, 2)


@pytest.mark.parametrize("row", ["b", "c"])
def test_a_sections_removal_run_as_printed_clears_it(holder, tmp_path, row):
    """The commands an unnamed section prints, typed exactly as printed,
    take every key out, and the holder passes again."""
    name, path = (("members/Old", "members/Old") if row == "b" else
                  ("ghost", "Members/IRRS"))
    with_section(holder, tmp_path, name, path, "/nowhere/x.git")
    (section,) = findings(validate(holder, "--no-members"))
    take_out_as_printed(holder, section)
    assert name not in (holder / ".gitmodules").read_text(encoding="utf-8")
    assert_passes_in_every_mode(holder, 2)


def test_an_index_git_cannot_list_is_a_refusal_not_a_pass(holder):
    """The gitlink check is the one reader of `members/` that `--no-members`
    runs, so an index git cannot list is a question it cannot answer: a
    refusal, exit 2, never an implicit pass."""
    (holder / ".git" / "index").write_bytes(b"not an index\n")
    result = validate(holder, "--no-members")
    assert result.returncode == 2, result.stderr + result.stdout
    assert result.stderr.startswith(
        "REFUSED gitlinks-unreadable: the index could not be listed, so the "
        "gitlinks it records in members/ could not be read: `git ls-files "
        "-s -z` in "), result.stderr
    assert result.stderr.splitlines()[-1] == (
        "Remediation: git status in this repository says what is wrong with "
        "its index. Mend that, then run this again.")


# --- a path that folds to a row's: only a second one is taken out ------------

def url_of(holder, project: str) -> str:
    """The url `family.py add` wrote in `project`'s section."""
    return git("config", "-f", ".gitmodules", "--get",
               f"submodule.members/{project}.url",
               cwd=holder).stdout.strip()


@MODES
def test_a_row_hand_edited_into_a_case_variant_of_its_mount_is_the_edit(
        holder, extra):
    """STATE (i), REVIEW SHOULD-1: IRSS's row says `path: Members/IRSS` and
    the real mount is `members/IRSS`. The mount is the canonical path and the
    ROW is the hand edit, so each finding says that and names no command: the
    `git rm --cached` and the `--unset-all` lines these used to print took
    the member's own gitlink and section out, after which `--no-members` said
    `family ok` over a family with one member. Members checked, `member-path`
    names the edit beside them; `--no-members` never runs it, which is why
    the finding must say it."""
    original = (holder / "family.yaml").read_bytes()
    hand_edit(holder, "Members/IRSS")
    commit_ = pinned(holder, "IRSS")
    result = validate(holder, *extra)
    assert result.returncode == 1, result.stderr + result.stdout
    assert "REFUSED" not in result.stderr, result.stderr
    assert codes(result) == (
        ["member-gitlink-unnamed", "gitmodules-path-unnamed"]
        + ([] if extra == ("--no-members",) else ["member-path"]))
    said = dict(path="members/IRSS", project="IRSS", row_path="Members/IRSS")
    gitlink, section = findings(result)[:2]
    assert gitlink == GITLINK_SAID.format(
        path="members/IRSS", commit=commit_) + ROW_EDITED.format(
            what="gitlink", **said)
    assert section == SECTION_SAID.format(
        path="members/IRSS", name="members/IRSS",
        url=f"url {url_of(holder, 'IRSS')}") + ROW_EDITED.format(
            what="section", **said)
    assert "git rm" not in result.stderr, result.stderr
    assert "--unset-all" not in result.stderr, result.stderr
    # Said and done: the path put back in the row clears all three.
    (holder / "family.yaml").write_bytes(original)
    assert_passes_in_every_mode(holder, 2)


@MODES
def test_a_member_recorded_only_in_another_case_says_so_and_prints_no_command(
        holder, extra):
    """STATE (ii), REVIEW SHOULD-1: IRSS's row is canonical, and the only
    gitlink the holder records for it is at `members/irss`. `git rm --cached`
    of that took the member's only record out, and `--no-members` then said
    `family ok` over a holder that records one gitlink fewer than it has rows.
    It says the member is recorded in the wrong case instead, and sends the
    operator to git's history, as every other unnamed gitlink does.

    Members checked, the row's own gitlink is read at its exact path, finds
    none and is the refusal `member-gitlink-absent`, which prints no finding,
    so only `--no-members` shows the finding; a git that matched the pathspec
    in any case would find the variant and print it, so either is accepted
    there, and what no run may do is print a command."""
    named = record_in_another_case(holder, "IRSS", "members/irss")
    result = validate(holder, *extra)
    assert "git rm" not in result.stderr + result.stdout
    assert "--unset-all" not in result.stderr + result.stdout
    if result.returncode == 2:
        assert extra != ("--no-members",), result.stderr
        assert result.stderr.startswith(
            "REFUSED member-gitlink-absent: no gitlink (mode 160000) "
            "recorded at 'members/IRSS'."), result.stderr
        return
    assert result.returncode == 1, result.stderr + result.stdout
    (gitlink,) = findings(result)
    assert gitlink == GITLINK_SAID.format(
        path="members/irss", commit=named) + WRONG_CASE.format(
            row_path="members/IRSS", project="IRSS", what="gitlink")


@MODES
def test_a_sections_only_path_in_another_case_says_so_and_prints_no_command(
        holder, extra):
    """The section's own state (ii): IRSS's row is canonical, its gitlink is
    where it belongs, and the ONLY section that registers it gives
    `members/irss`. `--unset-all` of that left the member with no section."""
    url = url_of(holder, "IRSS")
    with_path_replaced(holder, b"\tpath = members/IRSS\n",
                       b"\tpath = members/irss\n")
    result = validate(holder, *extra)
    assert result.returncode == 1, result.stderr + result.stdout
    (section,) = findings(result)
    assert section == SECTION_SAID.format(
        path="members/irss", name="members/IRSS", url=f"url {url}"
    ) + WRONG_CASE.format(row_path="members/IRSS", project="IRSS",
                          what="section")
    assert "--unset-all" not in result.stderr, result.stderr


def test_a_third_spelling_beside_an_edited_row_prints_no_command_either(
        holder):
    """The row is hand-edited AND a gitlink sits at a third spelling,
    `MEMBERS/IRSS`: neither the row's path nor the canonical one. Nothing here
    says it is a second path to a member that is standing, so it is not told
    to `git rm --cached`; the row is wrong first."""
    hand_edit(holder, "Members/IRSS")
    stage_gitlink(holder, "MEMBERS/IRSS", pinned(holder, "IRSS"))
    result = validate(holder, "--no-members")
    assert result.returncode == 1, result.stderr + result.stdout
    third = next(f for f in findings(result)
                 if f.startswith("FINDING member-gitlink-unnamed: MEMBERS/"))
    assert commands(third) == []
    assert "The member is recorded in the wrong case, so no command" in third
    assert "git rm" not in result.stderr, result.stderr


def test_two_sections_for_a_hand_mounts_path_each_keep_their_commands(
        family, holder, tmp_path):
    """`git rm` of a gitlink takes out ONE section for its path, the last the
    file gives, so the `git rm` finding cannot say it takes out both: where a
    path is given twice (`gitmodules-path-twice`), each section keeps its own
    `--unset-all` lines. The last assertion is the premise: after the `git
    rm` the finding prints, one of the two sections is still there."""
    _, tip = spare_commits(family)
    path = f"members/{SPARE}"
    stage_gitlink(holder, path, tip)
    with_section(holder, tmp_path, path, path, f"/nowhere/{SPARE}.git")
    with_section(holder, tmp_path, "second", path, "/nowhere/second.git")
    result = validate(holder, "--no-members")
    assert result.returncode == 1, result.stderr + result.stdout
    assert codes(result) == ["gitmodules-path-twice", "member-gitlink-unnamed",
                             "gitmodules-path-unnamed",
                             "gitmodules-path-unnamed"]
    first, second = findings(result)[2:]
    assert commands(first) == removal(path, "path", "url")
    assert commands(second) == removal("second", "path", "url")
    assert first.splitlines()[0].endswith(SECTION_REMEDY)
    assert "takes this section out too" not in result.stderr
    git(*shlex.split(commands(findings(result)[1])[1])[1:], cwd=holder)
    listed = git("config", "-f", ".gitmodules", "--list", cwd=holder).stdout
    assert listed.count(f".path={path}") == 1, listed


# --- a conflicted index records no gitlink at stage 0 ------------------------

def test_a_gitlink_held_only_at_conflict_stages_is_not_recorded(family,
                                                                holder):
    """`_member_gitlinks` reads the index at STAGE 0, as `recorded_gitlink`
    does: a conflicted merge holds a path at stages 1, 2 and 3, and none of
    them is a commit anybody is about to make. A path HEAD never recorded and
    the index holds only so is no gitlink the holder records."""
    _, tip = spare_commits(family)
    stage_unmerged_gitlink(holder, f"members/{SPARE}", tip)
    listed = git("ls-files", "-s", "--", f"members/{SPARE}",
                 cwd=holder).stdout.split()
    assert listed[2::4] == ["1", "2", "3"], listed
    assert_passes_in_every_mode(holder, 2)


def test_a_gitlink_head_records_is_head_s_when_the_index_holds_it_unmerged(
        family, holder):
    """The fallback to HEAD, as `recorded_gitlink` falls back: HEAD's gitlink
    is the one named, and no stage of the conflict is, whichever came last."""
    older, newer = spare_commits(family)
    path = f"members/{SPARE}"
    stage_gitlink(holder, path, older)
    commit(holder, "A gitlink no row names")
    stage_unmerged_gitlink(holder, path, newer)
    result = validate(holder, "--no-members")
    assert result.returncode == 1, result.stderr + result.stdout
    (gitlink,) = findings(result)
    assert gitlink.startswith(GITLINK_SAID.format(path=path, commit=older))


# --- the add remedy quotes the member it names -------------------------------

@pytest.mark.parametrize("project,quoted", [
    ("My Proj", "<org>/'My Proj'"),
    ("O'Brien", "<org>/'O'\"'\"'Brien'")], ids=["space", "quote"])
def test_the_add_remedy_quotes_the_member_it_names(family, holder, project,
                                                   quoted):
    """`--member` is quoted as the paths beside it are, its project alone:
    `<org>` is the operator's to fill in, and quoted whole it would be a
    literal org of that name. Split as a POSIX shell splits it, the value is
    the org and the project as written."""
    _, tip = spare_commits(family)
    stage_gitlink(holder, f"members/{project}", tip)
    result = validate(holder, "--no-members")
    assert result.returncode == 1, result.stderr + result.stdout
    (gitlink,) = findings(result)
    switch, rm, add = commands(gitlink)
    assert add.endswith(f" --member {quoted}"), add
    assert shlex.split(add)[-1] == f"<org>/{project}"
    assert shlex.split(rm)[-1] == f"members/{project}"
    # No branch word spells the project, so the branch says `member`, as
    # `family.py add` would suggest it (#539).
    assert shlex.split(switch)[-1] == "family/add-member", switch


def test_a_gitlink_that_names_no_project_says_one_placeholder_for_it(
        family, holder):
    """`members/deep/er` is two levels down, so no project is read from its
    path, and the remedy cannot name one. The branch and `--member` beside
    it stand for the one project, so they say it the one way, `<Project>`
    (#539): `family/add-<project>` over `--member <org>/<Project>` was two
    spellings for one value."""
    _, tip = spare_commits(family)
    stage_gitlink(holder, "members/deep/er", tip)
    result = validate(holder, "--no-members")
    assert result.returncode == 1, result.stderr + result.stdout
    (gitlink,) = findings(result)
    switch, rm, add = commands(gitlink)
    assert shlex.split(switch)[-1] == "family/add-<Project>", switch
    assert shlex.split(add)[-1] == "<org>/<Project>", add
    assert shlex.split(rm)[-1] == "members/deep/er", rm
    assert "<project>" not in gitlink, gitlink


# --- the remedy, run as printed, from a real mount ---------------------------

def test_a_hand_mount_is_taken_out_and_added_back_as_printed(family, holder):
    """ROW (a) FOR REAL, and the gitlink's remedy run as printed, from the
    holder's TRACKING BRANCH, where `init` leaves it and `add` refuses to
    commit (#487): the first line makes the branch `add` suggests (#539).
    `git rm` takes the checkout and its section out; `family.py add`, run
    as printed with the org filled in, then refuses `member-git-dir-cached`
    for the object store `git rm` leaves, as the remedy says it will name;
    with that gone, the same `add` mounts and pins the member with its row
    on that branch, and the holder passes in every mode.

    `git rm --cached`, which the issue proposed, is NOT the remedy: it
    leaves the checkout at the mount path, and `add` refuses that as
    `member-path-taken` before it gets as far as the store."""
    git("switch", "-q", "-C", "main", cwd=holder)
    git("-c", "protocol.file.allow=always", "submodule", "add", "-q", "--",
        str(family["remotes"] / f"{SPARE}.git"), f"members/{SPARE}",
        cwd=holder)
    commit(holder, "Mount IRQS by hand")
    result = validate(holder)
    assert result.returncode == 1, result.stderr + result.stdout
    assert codes(result) == ["member-gitlink-unnamed",
                             "gitmodules-path-unnamed"]
    switch, rm, add = commands(findings(result)[0])
    assert commands(findings(result)[1]) == []
    git(*shlex.split(switch)[1:], cwd=holder.parent)
    git(*shlex.split(rm)[1:], cwd=holder)
    assert not (holder / "members" / SPARE).exists()
    assert f"members/{SPARE}" not in (holder / ".gitmodules").read_text(
        encoding="utf-8")
    argv = [arg.replace("<org>", ORG) for arg in shlex.split(add)]
    assert argv[:3] == [PYTHON, "scripts/family.py", "add"], add

    def add_as_printed():
        return run_script(FAMILY, *argv[2:], "--local-remote-dir",
                          str(family["remotes"]))

    refused = add_as_printed()
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert refused.stderr.startswith("REFUSED member-git-dir-cached: ")
    rmtree(holder / ".git" / "modules" / "members" / SPARE)
    added = add_as_printed()
    assert added.returncode == 0, added.stdout + added.stderr
    assert git("status", "--porcelain", cwd=holder).stdout == ""
    assert git("symbolic-ref", "--short", "HEAD",
               cwd=holder).stdout.strip() == f"family/add-{SPARE.lower()}"
    assert_passes_in_every_mode(holder, 3)


# --- a holder whose rows name everything -------------------------------------

@MODES
def test_a_holder_whose_rows_name_every_gitlink_and_section_passes(holder,
                                                                   extra):
    """THE CONTROL: the family `init` and `add` made, two members, every
    gitlink and every section named by a row."""
    result = validate(holder, *extra)
    assert result.returncode == 0, result.stderr + result.stdout
    assert findings(result) == []
    assert "family ok: InkRouter (inkrouter), 2 member(s)" in result.stdout


def test_a_member_added_by_family_py_is_named(family, holder):
    """And one more member, added the way a member is added: its gitlink and
    its section are its row's, so nothing is unnamed."""
    added = run_script(FAMILY, "add", "--family-root", str(holder),
                       "--member", f"{ORG}/{SPARE}", "--local-remote-dir",
                       str(family["remotes"]))
    assert added.returncode == 0, added.stdout + added.stderr
    assert_passes_in_every_mode(holder, 3)
