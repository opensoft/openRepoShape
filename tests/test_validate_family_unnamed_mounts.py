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
    "was mounted by hand, take it out with the first command below, which "
    "refuses while its checkout holds changes and takes its .gitmodules "
    "section out too, then mount it with the second, from a checkout of "
    "openRepoShape: family.py add writes its row and its gitlink in one "
    "commit, and names the object store git rm leaves under .git/modules if "
    "one is still there.")

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


def commit(root, message: str) -> None:
    git("commit", "-qm", message, cwd=root)


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
    finding, in every mode: neither needs the member checked out."""
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
        f"git rm -- members/{SPARE}",
        f"{PYTHON} scripts/family.py add --family-root "
        f"{shlex.quote(str(holder.resolve()))} --member <org>/{SPARE}"]
    assert section.splitlines()[0] == SECTION_SAID.format(
        path=f"members/{SPARE}", name=f"members/{SPARE}",
        url=f"url /nowhere/{SPARE}.git") + SECTION_REMEDY
    assert commands(section) == removal(f"members/{SPARE}", "path", "url")


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


# --- the remedy, run as printed, from a real mount ---------------------------

def test_a_hand_mount_is_taken_out_and_added_back_as_printed(family, holder):
    """ROW (a) FOR REAL, and the gitlink's remedy run as printed. `git rm`
    takes the checkout and its section out; `family.py add`, run as printed
    with the org filled in, then refuses `member-git-dir-cached` for the
    object store `git rm` leaves, as the remedy says it will name; with that
    gone, the same `add` mounts and pins the member with its row, and the
    holder passes in every mode.

    `git rm --cached`, which the issue proposed, is NOT the remedy: it
    leaves the checkout at the mount path, and `add` refuses that as
    `member-path-taken` before it gets as far as the store."""
    git("-c", "protocol.file.allow=always", "submodule", "add", "-q", "--",
        str(family["remotes"] / f"{SPARE}.git"), f"members/{SPARE}",
        cwd=holder)
    commit(holder, "Mount IRQS by hand")
    result = validate(holder)
    assert result.returncode == 1, result.stderr + result.stdout
    assert codes(result) == ["member-gitlink-unnamed",
                             "gitmodules-path-unnamed"]
    rm, add = commands(findings(result)[0])
    git(*shlex.split(rm)[1:], cwd=holder)
    assert not (holder / "members" / SPARE).exists()
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
