# SPDX-License-Identifier: Apache-2.0
"""`family.py add` refuses BEFORE it mounts, and unwinds whatever fails after
(#203).

`add` used to run `git submodule add` first and only then ask whether `--at`
was a commit and whether the member had a `project.yaml`, and neither refusal
undid the mount. A leg, or a short `--at`, left a staged gitlink, a staged
`.gitmodules` section and a cached object store behind; the next `add` of a
DIFFERENT member then committed the refused one's section under its own
title, because `_commit_one` commits `.gitmodules` whole — and
`validate-family.py` and the doctor both passed the result. The `--at` typo
stranded the human in two more refusals (`member-path-taken`,
`member-git-dir-cached`) before the corrected command could run.

So every test here asks the same question of the holder AFTER a refused
`add`: is it exactly as it was? Not "is the refusal printed" — the old code
printed every one of these refusals too — but the index, the two files byte
for byte, the holder's git config, `members/` and `.git/modules/`, HEAD, and
`git status --porcelain` empty. A refusal the holder does not survive
unchanged is the defect, whatever the sentence says.

THE SAME FAMILY AS `test_family.py`, and the same rules: members are
scaffolded into local bare repositories, nothing is created on GitHub, and a
`gh` on PATH logs and exits non-zero so a call to it would be seen. (On
Windows a `#!` shim is not executable and the log stays empty whatever
happens; `add` with `--local-remote-dir` has no `gh` call to make, which is
what the POSIX runs prove.) `add --dry-run` asks these same refusals and is
tested in `test_family_dry_run.py` (#326).
"""

from __future__ import annotations

import importlib.util
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from conftest import git, run_script
#: The family fixture and its names, imported from the module that owns them
#: rather than rebuilt: a holder made any other way would test a different
#: holder. Importing the fixture gives this module its own instance of it.
from test_family import (  # noqa: F401
    FAMILY, NAME, ORG, SPARE, WORK_BRANCH, family, manifest, validate,
)

#: Every refusal that comes after the mount ends with this sentence when the
#: unwind put everything back. The middle names what was restored, in the
#: order `MountRollback.undo` restores it.
UNDONE = ("Nothing was added: the mount has been undone — {restored} — and "
          "the holder is exactly as it was before this command.")

LEG_REMEDIATION = (
    "Remediation: a family pins ASSEMBLY ROOTS. Scaffold or adopt the "
    "project first (`scaffold-project.py`, or `adopt-project.py` for a "
    "repository that already exists), then add it. Adding a leg — "
    "`{root}-spec` or `{root}-code` — is never right: the legs belong to "
    "their own assembly root{named}.")

#: What a good `add` ends with (#487): the push of the branch it committed on,
#: which is the fixture's own, and the pull request it is for.
NEXT = ("NEXT  git -C {root} push -u origin {branch}",
        "      then open a pull request against main; never push to it "
        "directly")

#: What an `--at` naming a tree or a blob, or a tag of one, is told to do.
AT_NAMES_NO_COMMIT_REMEDIATION = (
    "Remediation: pass the commit itself — `git log --format=%H` in the "
    "member lists them. A tree's or a blob's sha is part of a commit and "
    "never one, and a pin is a commit or it is nothing.")

#: What a refused pin write tells the human to do, whatever made it fail.
UNWRITABLE_REMEDIATION = (
    "Remediation: make family.yaml writable, and check the disk has room, "
    "then run the same command again.")

#: What a held lock makes git say, with the path left to git: macOS and
#: Windows spell a temporary directory their own way.
INDEX_LOCKED = r"fatal: Unable to create '[^']*index\.lock': File exists"


@dataclass
class Offline:
    """The environment every `add` here runs in."""

    env: dict
    gh_log: Path
    temp: Path

    def add(self, holder: Path, member: str, *extra: str,
            remotes: Path) -> subprocess.CompletedProcess:
        return run_script(FAMILY, "add", "--family-root", str(holder),
                          "--member", f"{ORG}/{member}", *extra,
                          "--local-remote-dir", str(remotes), env=self.env)

    def assert_left_nothing(self) -> None:
        """No `gh` call, and the throwaway clone `add` reads the member from
        is gone whatever the answer was."""
        assert not self.gh_log.exists(), self.gh_log.read_text()
        assert list(self.temp.iterdir()) == []


@pytest.fixture
def offline(tmp_path) -> Offline:
    """A `gh` that logs and exits 97, and a TEMP of the test's own.

    The temporary directory is the test's so that "the throwaway clone was
    deleted" is a statement about THIS run, not about whatever else on the
    machine uses the system temp directory.
    """
    shim = tmp_path / "shim"
    shim.mkdir()
    log = tmp_path / "gh-calls.log"
    (shim / "gh").write_text(
        "#!/bin/sh\n"
        f"echo \"gh $*\" >> '{log.as_posix()}'\n"
        "echo 'gh shim: refusing to talk to GitHub (exit 97)' >&2\n"
        "exit 97\n", encoding="utf-8")
    (shim / "gh").chmod(0o755)
    temp = tmp_path / "temp"
    temp.mkdir()
    env = {"PATH": str(shim) + os.pathsep + os.environ.get("PATH", ""),
           "TMPDIR": str(temp), "TEMP": str(temp), "TMP": str(temp)}
    return Offline(env, log, temp)


@pytest.fixture
def holder(family, tmp_path) -> Path:
    """A private, mutable copy of the family root, clean."""
    target = tmp_path / NAME
    shutil.copytree(family["root"], target, symlinks=True)
    assert git("status", "--porcelain", cwd=target).stdout == ""
    return target


def snapshot(root: Path, *, status: bool = True) -> dict:
    """Everything a refused `add` must leave exactly as it found it.

    `status=False` for a holder with no `git status` to ask: one whose HEAD
    names a missing object answers `fatal: bad object HEAD`."""
    def read(name: str) -> bytes | None:
        target = root / name
        return target.read_bytes() if target.is_file() else None

    def listing(directory: Path) -> list[str] | None:
        return sorted(os.listdir(directory)) if directory.is_dir() else None

    return {
        # `-q --verify`, so a holder with NO COMMIT YET records no HEAD
        # rather than failing the snapshot.
        "HEAD": git("rev-parse", "-q", "--verify", "HEAD", cwd=root,
                    check=False).stdout,
        "index": git("ls-files", "-s", cwd=root).stdout,
        "status": (git("status", "--porcelain", "--ignored", cwd=root).stdout
                   if status else None),
        "config": git("config", "--local", "--list", cwd=root).stdout,
        ".gitmodules": read(".gitmodules"),
        "family.yaml": read("family.yaml"),
        "members": listing(root / "members"),
        "modules": listing(root / ".git" / "modules"),
        "modules/members": listing(root / ".git" / "modules" / "members"),
    }


def registration(config: str, member: str) -> list[str]:
    """`member`'s own lines of a `git config --list`, BY SECTION — the part
    of a key before its last dot — as `MountRollback` reads them: a
    substring or a prefix would take `members/IRQS.v2`'s keys for
    `members/IRQS`'s."""
    section = f"submodule.members/{member}"
    return [line for line in config.splitlines()
            if line.partition("=")[0].rpartition(".")[0] == section]


def assert_unchanged(root: Path, before: dict, member: str, *,
                     status: bool = True) -> None:
    """The holder is the one `before` recorded, and carries no trace of
    `member` it did not carry before: the three things #203 found left
    behind, named one by one. `status` as for `snapshot`."""
    if status:
        assert git("status", "--porcelain", cwd=root).stdout == ""
    assert snapshot(root, status=status) == before
    assert not (root / "members" / member).exists()
    assert not (root / ".git" / "modules" / "members" / member).exists()
    assert registration(git("config", "--local", "--list", cwd=root).stdout,
                        member) == registration(before["config"], member)


def refusal(stderr: str) -> tuple[str, str]:
    """`(the REFUSED line, the line after it)` — what a refusal says and what
    it tells the human to do next — and that nothing else was printed."""
    lines = stderr.splitlines()
    assert len(lines) == 2, stderr
    return lines[0], lines[1]


def sections(text: str) -> list[str]:
    """The `[submodule "<path>"]` paths a `.gitmodules` registers."""
    return re.findall(r'^\[submodule "([^"]+)"\]$', text, re.MULTILINE)


def one_commit_remote(tmp_path: Path, name: str, files: dict) -> Path:
    """A directory of remotes holding `<name>.git`: ONE commit of `files`
    (path to BYTES), for a member no scaffold would make."""
    remotes = tmp_path / "remotes"
    remotes.mkdir()
    work = tmp_path / f"{name}-work"
    git("init", "-q", str(work), cwd=tmp_path)
    for path, data in files.items():
        (work / path).write_bytes(data)
    git("add", "--", *files, cwd=work)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        f"One commit of {name}", cwd=work)
    git("clone", "-q", "--bare", str(work), str(remotes / f"{name}.git"),
        cwd=tmp_path)
    return remotes


def full_disk(path, text):
    """`write_lf` on a disk with no room left: the pin write fails AFTER the
    mount, in-process, which works as root and on every platform alike."""
    raise OSError(28, "No space left on device", str(path))


def mount_undone(member: str, *,
                 gitmodules: str = ".gitmodules restored byte for byte",
                 registered: str = "dropped from the holder's git config",
                 ) -> str:
    """`UNDONE` for an unwind of everything the MOUNT made — the pin was
    never written — in an ordinary clone, in `undo`'s order."""
    return UNDONE.format(
        restored=f"the gitlink at members/{member} unstaged, "
                 f"members/{member} removed, "
                 f".git/modules/members/{member} removed, {gitmodules}, "
                 f"`submodule.members/{member}` {registered}")


def add_in_process(module, monkeypatch, offline: Offline, root: Path,
                   member: str, remotes: Path) -> int:
    """`family.py add` run IN THIS PROCESS — for a failure no subprocess
    can inject — in the same offline environment as `Offline.add`."""
    monkeypatch.setattr(tempfile, "tempdir", str(offline.temp))
    monkeypatch.setenv("PATH", offline.env["PATH"])
    return module.main(["add", "--family-root", str(root),
                        "--member", f"{ORG}/{member}",
                        "--local-remote-dir", str(remotes)])


def unborn_holder(tmp_path: Path) -> Path:
    """A holder with NO COMMIT YET: `git init` and a hand-written
    `family.yaml`, not even staged. `family.py init` always commits; a
    holder made by hand does not. Its unborn HEAD is on a branch of its own,
    not the tracking branch `main` that `add` refuses to commit onto
    (#487), whatever the default branch of the `git init` running here."""
    root = tmp_path / "Unborn"
    git("init", "-q", "-b", "family/unborn", str(root), cwd=tmp_path)
    (root / "family.yaml").write_bytes(
        b"schema_version: 1\nkind: family-manifest\nname: Unborn\n"
        b"members: []\n")
    return root


# --- check before mount -----------------------------------------------------

@pytest.mark.parametrize("leg", ["IRRS-spec", "IRRS-code"])
def test_a_leg_is_refused_before_anything_is_mounted(family, holder, offline,
                                                     leg):
    """THE CASE THE ISSUE OPENS WITH. A leg has no `project.yaml`, and that is
    now read from a throwaway clone of it, so the holder is never touched:
    no gitlink, no `.gitmodules` section, no object store.

    And the remediation names the legs of `IRRS`, the root the suffix came
    off — not `IRRS-spec-spec`, which no repository is."""
    before = snapshot(holder)
    result = offline.add(holder, leg, remotes=family["remotes"])
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == f"checking {ORG}/{leg} before mounting it\n"
    said, next_line = refusal(result.stderr)
    assert said == (
        f"REFUSED member-not-a-project: {ORG}/{leg} has no project.yaml at "
        "the commit being pinned, so it is not an assembly root of a project "
        "that has elected this shape")
    assert next_line == LEG_REMEDIATION.format(root="IRRS", named=", `IRRS`")
    assert_unchanged(holder, before, leg)
    offline.assert_left_nothing()


def test_a_project_without_a_manifest_is_named_as_itself(family, holder,
                                                         offline, tmp_path):
    """A name with no leg suffix keeps the sentence it always had: there is
    no root to strip it to, so none is named."""
    remotes = one_commit_remote(tmp_path, "IRXS",
                                {"README.md": b"not a project\n"})
    before = snapshot(holder)
    result = offline.add(holder, "IRXS", remotes=remotes)
    assert result.returncode == 2, result.stdout + result.stderr
    said, next_line = refusal(result.stderr)
    assert said == (
        f"REFUSED member-not-a-project: {ORG}/IRXS has no project.yaml at the "
        "commit being pinned, so it is not an assembly root of a project that "
        "has elected this shape")
    assert next_line == LEG_REMEDIATION.format(root="IRXS", named="")
    assert_unchanged(holder, before, "IRXS")
    offline.assert_left_nothing()


def test_an_unreadable_manifest_is_named_in_the_member_not_in_the_clone(
        holder, offline, tmp_path):
    """`load_yaml`'s own refusals name the FILE, and the probe reads the
    member's `project.yaml` out of a throwaway clone that is deleted before
    anybody reads the line. So the file is named where a human can find it,
    `<repository> @ <commit>:project.yaml`, never by the clone's temporary
    path. A byte that is not UTF-8 is the refusal (#192) that names it."""
    data = b"schema_version: 1\nkind: project-manifest\nname: \xff\n"
    remotes = one_commit_remote(tmp_path, "IRBAD", {"project.yaml": data})
    commit = git("rev-parse", "HEAD",
                 cwd=remotes / "IRBAD.git").stdout.strip()
    byte = data.index(b"\xff")
    before = snapshot(holder)
    result = offline.add(holder, "IRBAD", remotes=remotes)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == f"checking {ORG}/IRBAD before mounting it\n"
    assert refusal(result.stderr) == (
        f"REFUSED yaml-unreadable: {ORG}/IRBAD @ {commit[:12]}:project.yaml: "
        f"not UTF-8 at byte {byte} (invalid start byte)",
        "Remediation: every YAML file this tool reads must be UTF-8. "
        f"Byte {byte}, counting from 0 at the start of the file, is the first "
        "one that is not: re-save the file as UTF-8, or replace that byte "
        "with the character it was meant to be, and run the command again.")
    assert_unchanged(holder, before, "IRBAD")
    offline.assert_left_nothing()


def test_a_short_at_is_refused_before_the_member_is_even_read(family, holder,
                                                              offline):
    """`--at abc1234`, the commonest typo there is: refused on its SHAPE,
    before the member is cloned, so not even the `checking` line prints."""
    before = snapshot(holder)
    result = offline.add(holder, SPARE, "--at", "abc1234",
                         remotes=family["remotes"])
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == ""
    assert refusal(result.stderr) == (
        "REFUSED member-at-not-a-commit: --at 'abc1234' is not a 40-hex "
        "commit",
        "Remediation: pass the full 40 characters. A tag can be moved and a "
        "commit cannot, which is why a pin is never a tag.")
    assert_unchanged(holder, before, SPARE)
    offline.assert_left_nothing()


@pytest.mark.parametrize("whose", ["nobody's", "its leg's"])
def test_an_at_that_is_not_a_commit_of_the_member_is_refused(family, holder,
                                                             offline, whose):
    """`member-at-unknown`: a well-formed sha the member's objects do not
    have. Forty zeros is nobody's commit; the spec leg's tip is the real
    mistake the remediation names — a commit of the LEG, handed to its
    root."""
    at = ("0" * 40 if whose == "nobody's" else
          git("rev-parse", "main",
              cwd=family["remotes"] / f"{SPARE}-spec.git").stdout.strip())
    before = snapshot(holder)
    result = offline.add(holder, SPARE, "--at", at, remotes=family["remotes"])
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == f"checking {ORG}/{SPARE} before mounting it\n"
    assert refusal(result.stderr) == (
        f"REFUSED member-at-unknown: --at {at} is not a commit any branch or "
        f"tag of {ORG}/{SPARE} reaches",
        "Remediation: check the commit — it belongs to the member's ASSEMBLY "
        "ROOT, not to one of its legs — and that it has been pushed. A pin "
        "the rest of the world cannot fetch is a family the rest of the "
        "world cannot bootstrap.")
    assert_unchanged(holder, before, SPARE)
    offline.assert_left_nothing()


def test_a_member_with_no_tip_is_refused(holder, offline, tmp_path):
    """`member-no-tip`: an empty repository has no commit to pin, which a
    clone of it says by having a HEAD that resolves to nothing."""
    remotes = tmp_path / "remotes"
    remotes.mkdir()
    git("init", "-q", "--bare", str(remotes / "IREMPTY.git"), cwd=tmp_path)
    before = snapshot(holder)
    result = offline.add(holder, "IREMPTY", remotes=remotes)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == f"checking {ORG}/IREMPTY before mounting it\n"
    assert refusal(result.stderr) == (
        f"REFUSED member-no-tip: {ORG}/IREMPTY has no commit on its default "
        "branch to pin: it is empty, or its HEAD names a branch it does not "
        "have",
        "Remediation: a family pins a commit, so the member must have one. "
        "Scaffold or adopt the project first, which gives it one, or pass "
        "`--at <40-hex commit>` naming a commit it already has.")
    assert_unchanged(holder, before, "IREMPTY")
    offline.assert_left_nothing()


def test_a_member_that_cannot_be_read_is_refused_unmounted(holder, offline,
                                                           tmp_path):
    """A member that does not exist — or a PRIVATE one with no credential —
    fails the throwaway clone, and the refusal says what it was reading and
    what to check. Nothing was mounted to undo."""
    remotes = tmp_path / "remotes"
    remotes.mkdir()
    before = snapshot(holder)
    result = offline.add(holder, "IRNOPE", remotes=remotes)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == f"checking {ORG}/IRNOPE before mounting it\n"
    lines = result.stderr.splitlines()
    assert lines[0] == (f"REFUSED reading {ORG}/IRNOPE. THE EXACT COMMAND "
                        "WAS:")
    assert lines[1].startswith("    git -c protocol.file.allow=always clone "
                               "-q --bare -- ")
    assert lines[-1] == (
        "The member must be readable from here. If it is PRIVATE, check `gh "
        "auth status` or your SSH key; a family cannot pin what it cannot "
        "read.")
    assert_unchanged(holder, before, "IRNOPE")
    offline.assert_left_nothing()


def test_a_manifest_this_tool_will_not_rewrite_is_refused_before_the_mount(
        family, holder, offline):
    """`family-members-unrecognised` used to be raised by the pin write,
    AFTER the mount, so a hand-edited `members:` line left the mount behind
    exactly as a leg did. It is asked first now."""
    path = holder / "family.yaml"
    text = path.read_text(encoding="utf-8")
    assert text.count("\nmembers:\n") == 1
    path.write_bytes(text.replace("\nmembers:\n",
                                  "\nmembers:  # edited by hand\n")
                     .encode("utf-8"))
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "A hand edit", "--", "family.yaml", cwd=holder)
    before = snapshot(holder)
    result = offline.add(holder, SPARE, remotes=family["remotes"])
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == ""
    assert refusal(result.stderr) == (
        "REFUSED family-members-unrecognised: "
        f"{holder.resolve() / 'family.yaml'} has 0 `members:` line(s) where "
        "exactly one was expected, so this tool will not rewrite it",
        "Remediation: the manifest was hand-edited into a shape this tool "
        "does not recognise. `members:` is the LAST block in the file and "
        "everything below it belongs to this tool; fix it by hand this once "
        "and commit that (`git commit -- family.yaml`), then run the same "
        "command again.")
    assert_unchanged(holder, before, SPARE)
    offline.assert_left_nothing()


@pytest.mark.parametrize("kind", ["tree", "blob"])
def test_an_at_that_names_a_tree_or_a_blob_is_refused_as_one(family, holder,
                                                             offline, kind):
    """A tree's or a blob's sha IS in the member — `git ls-tree` and `git
    rev-parse <commit>:<path>` print them — so it is refused as what it
    is, still `member-at-unknown` and still before the mount, and never as
    a commit no branch reaches, which would send the human looking for a
    push that is not missing."""
    at = git("rev-parse",
             "main^{tree}" if kind == "tree" else "main:project.yaml",
             cwd=family["remotes"] / f"{SPARE}.git").stdout.strip()
    before = snapshot(holder)
    result = offline.add(holder, SPARE, "--at", at, remotes=family["remotes"])
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == f"checking {ORG}/{SPARE} before mounting it\n"
    assert refusal(result.stderr) == (
        f"REFUSED member-at-unknown: --at {at} names a {kind} in "
        f"{ORG}/{SPARE}, not a commit", AT_NAMES_NO_COMMIT_REMEDIATION)
    assert_unchanged(holder, before, SPARE)
    offline.assert_left_nothing()


def tagged_remote(family, tmp_path: Path, target: str) -> tuple[Path, str]:
    """A COPY of the member's remote with one ANNOTATED tag on `target` (any
    revision of it), in a directory of remotes of its own: `(that directory,
    the tag object's own sha)`. The session's remotes are not written to."""
    remotes = tmp_path / "remotes"
    remotes.mkdir()
    bare = remotes / f"{SPARE}.git"
    shutil.copytree(family["remotes"] / f"{SPARE}.git", bare, symlinks=True)
    git("-c", "user.name=t", "-c", "user.email=t@t", "tag", "-a", "-m",
        "an annotated tag", "v-annotated", target, cwd=bare)
    at = git("rev-parse", "v-annotated", cwd=bare).stdout.strip()
    assert git("cat-file", "-t", at, cwd=bare).stdout.strip() == "tag"
    return remotes, at


@pytest.mark.parametrize("kind", ["tree", "blob"])
def test_an_at_that_is_a_tag_of_a_tree_or_a_blob_is_named_for_what_it_tags(
        family, holder, offline, tmp_path, kind):
    """THE `^{}` IN `cat-file -t <at>^{}`. The sha of an ANNOTATED TAG is the
    tag object's own, and `cat-file -t` of it is `tag` — neither a tree nor a
    blob — so without the peel a tag of a tree is refused as a commit no
    branch or tag reaches, the very wording the tree and blob refusal exists
    to avoid. With it the tag is named by what it tags."""
    remotes, at = tagged_remote(
        family, tmp_path,
        "main^{tree}" if kind == "tree" else "main:project.yaml")
    before = snapshot(holder)
    result = offline.add(holder, SPARE, "--at", at, remotes=remotes)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == f"checking {ORG}/{SPARE} before mounting it\n"
    assert refusal(result.stderr) == (
        f"REFUSED member-at-unknown: --at {at} names a {kind} in "
        f"{ORG}/{SPARE}, not a commit", AT_NAMES_NO_COMMIT_REMEDIATION)
    assert_unchanged(holder, before, SPARE)
    offline.assert_left_nothing()


def test_an_at_that_is_a_tag_of_a_commit_pins_the_commit_it_tags(
        family, holder, offline, tmp_path):
    """The other half of the same peel: an annotated tag's own sha is not a
    commit, but it names one, and `add` pins THAT — the commit the tag is on,
    which is not the tip — exactly as checking the tag out always did."""
    remotes, at = tagged_remote(family, tmp_path, "main~1")
    bare = remotes / f"{SPARE}.git"
    commit = git("rev-parse", "main~1", cwd=bare).stdout.strip()
    tip = git("rev-parse", "main", cwd=bare).stdout.strip()
    assert at != commit != tip
    result = offline.add(holder, SPARE, "--at", at, remotes=remotes)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""
    row = {r["project"]: r for r in manifest(holder)["members"]}[SPARE]
    assert row["pin"]["commit"] == commit
    assert git("rev-parse", f"HEAD:members/{SPARE}",
               cwd=holder).stdout.strip() == commit
    assert git("status", "--porcelain", cwd=holder).stdout == ""
    offline.assert_left_nothing()


def test_a_cached_store_in_a_linked_worktree_is_refused_where_git_keeps_it(
        family, holder, offline, tmp_path):
    """`member-git-dir-cached`, ASKED OF GIT. In a LINKED WORKTREE — a
    lane's usual holder — `git rm` leaves a removed member's object store
    under `.git/worktrees/<name>/modules/`, and `git submodule add` refuses
    to write over it there just as it does under `.git/modules/`. The
    refusal looks where git keeps it and names that, before anything is
    read or mounted; looking only in `.git/modules/` would send the add on
    into git's own refusal after the mount."""
    lane = tmp_path / "lane"
    git("worktree", "add", "-q", "-b", "readd-irqs", str(lane), cwd=holder)
    added = offline.add(lane, SPARE, remotes=family["remotes"])
    assert added.returncode == 0, added.stdout + added.stderr
    removed = run_script(FAMILY, "remove", "--family-root", str(lane),
                         "--member", SPARE, env=offline.env)
    assert removed.returncode == 0, removed.stdout + removed.stderr
    gitdir = Path(git("rev-parse", "--absolute-git-dir",
                      cwd=lane).stdout.strip())
    store = lane.resolve() / git("rev-parse", "--git-path",
                                 f"modules/members/{SPARE}",
                                 cwd=lane).stdout.strip()
    # The case this test exists for: a store `.git/modules/<path>` is not.
    assert gitdir.parent.name == "worktrees"
    assert store.is_dir() and store.parent.parent == gitdir / "modules"

    before = snapshot(lane)
    result = offline.add(lane, SPARE, remotes=family["remotes"])
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == ""
    assert result.stderr.splitlines() == [
        f"REFUSED member-git-dir-cached: {store.as_posix()} still holds the "
        f"object store of a previously removed {SPARE}, and `git submodule "
        "add` will not write over it",
        "Remediation: if nothing unpushed lives in it — and nothing does "
        "unless somebody committed inside the mount — delete it and re-run. "
        "It is this directory:",
        f"    {store.as_posix()}",
        "and in a POSIX shell (Git Bash on Windows) this deletes it and "
        "nothing else:",
        f"    rm -rf {shlex.quote(store.as_posix())}",
        "It is left behind by `git rm` on purpose, which is why this tool "
        "will not remove it for you.",
    ]
    assert_unchanged(lane, before, SPARE)
    assert store.is_dir()
    offline.assert_left_nothing()


@pytest.mark.skipif(sys.platform == "win32",
                    reason="a tracked symlink is a plain file in a Windows "
                           "checkout")
def test_a_linked_manifest_is_left_to_the_mount_which_reads_through_it(
        holder, offline, tmp_path):
    """A SYMLINK IS LEFT TO THE MOUNT. An object store holds only a link's
    text and a checkout reads THROUGH the link, so a member whose
    `project.yaml` links to its real manifest is not judged by the probe —
    whose copy of the file would be the words `manifest/project.yaml` —
    but by the mount, which reads the manifest it links to. It is added,
    as it always was. (The link is built in the member's INDEX, not on a
    disk.)"""
    remotes = tmp_path / "remotes"
    remotes.mkdir()
    work = tmp_path / "IRLN-work"
    git("init", "-q", str(work), cwd=tmp_path)
    (work / "manifest").mkdir()
    (work / "manifest" / "project.yaml").write_bytes(
        b"schema_version: 1\nkind: project-manifest\nid: irln\nname: IRLN\n")
    git("add", "--", "manifest/project.yaml", cwd=work)
    link = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                          cwd=str(work), input=b"manifest/project.yaml",
                          capture_output=True, check=True).stdout
    git("update-index", "--add", "--cacheinfo",
        f"120000,{link.decode('ascii').strip()},project.yaml", cwd=work)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "A linked manifest", cwd=work)
    git("clone", "-q", "--bare", str(work), str(remotes / "IRLN.git"),
        cwd=tmp_path)
    tip = git("rev-parse", "HEAD", cwd=remotes / "IRLN.git").stdout.strip()

    result = offline.add(holder, "IRLN", remotes=remotes)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""
    row = {r["project"]: r for r in manifest(holder)["members"]}["IRLN"]
    assert row["id"] == "irln"
    assert row["pin"]["commit"] == tip
    assert git("rev-parse", "HEAD:members/IRLN",
               cwd=holder).stdout.strip() == tip
    assert (holder / "members" / "IRLN" / "project.yaml").is_symlink()
    assert git("status", "--porcelain", cwd=holder).stdout == ""
    offline.assert_left_nothing()


# --- what a refusal leaves for the NEXT command -----------------------------

def test_a_good_add_after_a_refused_one_commits_only_its_own_entry(
        family, holder, offline):
    """THE DEFECT ITSELF. A refused leg, then a good member: the good one's
    commit carries ONE gitlink and ONE new `.gitmodules` section, its own —
    never the refused leg's registration under the title "Add IRQS"."""
    was = git("rev-parse", "HEAD", cwd=holder).stdout.strip()
    refused = offline.add(holder, "IRRS-spec", remotes=family["remotes"])
    assert refused.returncode == 2, refused.stdout + refused.stderr

    added = offline.add(holder, SPARE, remotes=family["remotes"])
    assert added.returncode == 0, added.stdout + added.stderr
    assert git("rev-parse", "HEAD~1", cwd=holder).stdout.strip() == was
    assert git("show", "--name-only", "--format=", "HEAD",
               cwd=holder).stdout.split() == [
        ".gitmodules", "family.yaml", f"members/{SPARE}"]
    gitlinks = [line for line in git("diff-tree", "-r", "--no-commit-id",
                                     "HEAD", cwd=holder).stdout.splitlines()
                if line.split()[1] == "160000"]
    assert len(gitlinks) == 1 and gitlinks[0].endswith(f"\tmembers/{SPARE}")
    old = sections(git("show", "HEAD~1:.gitmodules", cwd=holder).stdout)
    new = sections(git("show", "HEAD:.gitmodules", cwd=holder).stdout)
    assert [s for s in new if s not in old] == [f"members/{SPARE}"]
    assert "IRRS-spec" not in git("show", "HEAD:.gitmodules",
                                  cwd=holder).stdout
    pinned = sorted(row["path"] for row in manifest(holder)["members"])
    mounted = sorted(line.split("\t")[1] for line in git(
        "ls-tree", "HEAD", "members/", cwd=holder).stdout.splitlines())
    assert sorted(new) == pinned == mounted
    assert git("status", "--porcelain", cwd=holder).stdout == ""
    assert validate(holder).returncode == 0
    offline.assert_left_nothing()


@pytest.mark.parametrize("typo", ["abc1234", "0" * 40])
def test_the_corrected_command_runs_at_once_after_a_bad_at(family, holder,
                                                           offline, typo):
    """The issue's three-refusals-in-a-row path: a bad `--at`, then the
    command with the right one. It runs first time — no `member-path-taken`,
    no `member-git-dir-cached` — because there was nothing to clear."""
    wanted = git("rev-parse", "main~1",
                 cwd=family["remotes"] / f"{SPARE}.git").stdout.strip()
    bad = offline.add(holder, SPARE, "--at", typo, remotes=family["remotes"])
    assert bad.returncode == 2, bad.stdout + bad.stderr
    good = offline.add(holder, SPARE, "--at", wanted,
                       remotes=family["remotes"])
    assert good.returncode == 0, good.stdout + good.stderr
    row = {r["project"]: r for r in manifest(holder)["members"]}[SPARE]
    assert row["pin"]["commit"] == wanted
    assert git("rev-parse", f"HEAD:members/{SPARE}",
               cwd=holder).stdout.strip() == wanted
    assert validate(holder).returncode == 0
    offline.assert_left_nothing()


# --- unwind after it --------------------------------------------------------

@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0,
                    reason="root writes through a read-only file")
def test_a_pin_that_cannot_be_written_unwinds_the_mount(family, holder,
                                                        offline):
    """`family-manifest-unwritable`: the mount is made and the pin write
    fails. It used to be a traceback over a half-added member; it is a
    refusal now, and the holder is put back — every piece named — so the
    same command, once the file is writable, simply runs."""
    manifest_path = holder / "family.yaml"
    before = snapshot(holder)
    manifest_path.chmod(stat.S_IREAD)
    try:
        result = offline.add(holder, SPARE, remotes=family["remotes"])
    finally:
        manifest_path.chmod(stat.S_IREAD | stat.S_IWRITE)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == (f"checking {ORG}/{SPARE} before mounting it\n"
                             f"mounting {ORG}/{SPARE} at members/{SPARE}\n")
    assert refusal(result.stderr) == (
        "REFUSED family-manifest-unwritable: family.yaml could not be "
        f"rewritten with {SPARE}'s pin: Permission denied. " + UNDONE.format(
            restored=f"the gitlink at members/{SPARE} unstaged, "
                     f"members/{SPARE} removed, "
                     f".git/modules/members/{SPARE} removed, "
                     ".gitmodules restored byte for byte, "
                     f"`submodule.members/{SPARE}` dropped from the holder's "
                     "git config"),
        "Remediation: make family.yaml writable, and check the disk has "
        "room, then run the same command again.")
    assert_unchanged(holder, before, SPARE)
    offline.assert_left_nothing()

    again = offline.add(holder, SPARE, remotes=family["remotes"])
    assert again.returncode == 0, again.stdout + again.stderr
    assert validate(holder).returncode == 0


def test_a_commit_that_fails_unwinds_the_mount_and_the_pin(family, holder,
                                                           offline,
                                                           tmp_path):
    """The last step fails — here a `pre-commit` hook that refuses — after
    the mount AND the pin write. The failed command is shown as it ran, and
    the sentence under it names what was put back, `family.yaml` included."""
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "pre-commit").write_bytes(
        b"#!/bin/sh\necho 'pre-commit: refusing (injected)' >&2\nexit 1\n")
    (hooks / "pre-commit").chmod(0o755)
    # LOCAL, so a `core.hooksPath` in the runner's global config cannot
    # point git somewhere this hook is not.
    git("config", "--local", "core.hooksPath", hooks.as_posix(), cwd=holder)
    before = snapshot(holder)
    result = offline.add(holder, SPARE, remotes=family["remotes"])
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == (f"checking {ORG}/{SPARE} before mounting it\n"
                             f"mounting {ORG}/{SPARE} at members/{SPARE}\n")
    assert result.stderr.splitlines() == [
        f"REFUSED committing {SPARE} to the family. THE EXACT COMMAND WAS:",
        "    git commit -q -F - -- :(literal).gitmodules "
        f":(literal)members/{SPARE} :(literal)family.yaml",
        f"    (in {holder.resolve()})",
        "    exit 1",
        "--- output ---",
        "pre-commit: refusing (injected)",
        "--- end output ---",
        UNDONE.format(
            restored=f"the gitlink at members/{SPARE} unstaged, "
                     f"members/{SPARE} removed, "
                     f".git/modules/members/{SPARE} removed, "
                     ".gitmodules restored byte for byte, "
                     "family.yaml restored byte for byte, "
                     f"`submodule.members/{SPARE}` dropped from the holder's "
                     "git config"),
    ]
    assert_unchanged(holder, before, SPARE)
    offline.assert_left_nothing()


@pytest.fixture
def family_module():
    """`family.py` as a module, for the failures no subprocess can inject:
    a member that moves between the probe and the mount, a pin write that
    fails as root too, an unwind step that fails, a failure after the commit
    landed. A fresh module per test, so nothing patched here outlives it."""
    spec = importlib.util.spec_from_file_location("family_add_refusals",
                                                  FAMILY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_member_that_moves_on_between_the_probe_and_the_mount_is_unwound(
        family, holder, offline, tmp_path, family_module, monkeypatch,
        capsys):
    """THE BACKSTOP. `add` reads the member twice — the throwaway clone,
    then the mount — and the mount's reading is what the pin records. A
    member whose next commit deletes `project.yaml`, pushed in between, is
    refused by the SECOND reading, after the mount: the same refusal a leg
    got before #203, and now it is unwound and says so."""
    remotes = tmp_path / "remotes"
    shutil.copytree(family["remotes"] / f"{SPARE}.git",
                    remotes / f"{SPARE}.git", symlinks=True)
    probe = family_module._probe_member

    def moved_on(*args, **kwargs):
        commit = probe(*args, **kwargs)
        work = tmp_path / "moving"
        git("clone", "-q", str(remotes / f"{SPARE}.git"), str(work),
            cwd=tmp_path)
        git("rm", "-q", "--", "project.yaml", cwd=work)
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
            "No longer a project", cwd=work)
        git("push", "-q", "origin", "HEAD", cwd=work)
        return commit

    monkeypatch.setattr(family_module, "_probe_member", moved_on)
    monkeypatch.setattr(tempfile, "tempdir", str(offline.temp))
    monkeypatch.setenv("PATH", offline.env["PATH"])
    before = snapshot(holder)
    code = family_module.main(["add", "--family-root", str(holder),
                               "--member", f"{ORG}/{SPARE}",
                               "--local-remote-dir", str(remotes)])
    out, err = capsys.readouterr()
    assert code == 2, out + err
    assert out == (f"checking {ORG}/{SPARE} before mounting it\n"
                   f"mounting {ORG}/{SPARE} at members/{SPARE}\n")
    assert refusal(err) == (
        f"REFUSED member-not-a-project: {ORG}/{SPARE} has no project.yaml "
        "at the commit being pinned, so it is not an assembly root of a "
        "project that has elected this shape. " + UNDONE.format(
            restored=f"the gitlink at members/{SPARE} unstaged, "
                     f"members/{SPARE} removed, "
                     f".git/modules/members/{SPARE} removed, "
                     ".gitmodules restored byte for byte, "
                     f"`submodule.members/{SPARE}` dropped from the holder's "
                     "git config"),
        LEG_REMEDIATION.format(root=SPARE, named=""))
    assert_unchanged(holder, before, SPARE)
    offline.assert_left_nothing()


def test_the_first_member_of_an_empty_family_unwinds_to_no_gitmodules(
        family, offline, tmp_path, family_module, monkeypatch, capsys):
    """`.gitmodules`, `members/` and `.git/modules/` do not exist until the
    first member is mounted, so the unwind REMOVES them rather than restoring
    them — "absent, as before". The pin write is made to fail in-process
    here, which works as root and everywhere else alike."""
    created = run_script(FAMILY, "init", "--org", ORG, "--family", "Contoso",
                         "--created-by", "Test Human",
                         "--local-remote-dir", str(tmp_path / "fam-remotes"),
                         "--work-dir", str(tmp_path / "work"))
    assert created.returncode == 0, created.stderr + created.stdout
    root = tmp_path / "work" / "Contoso"
    assert not (root / ".gitmodules").exists()
    assert not (root / "members").exists()
    # On a branch, as `add` requires: it refuses the tracking branch (#487).
    git("switch", "-q", "-c", f"family/add-{SPARE.lower()}", cwd=root)
    monkeypatch.setattr(family_module, "write_lf", full_disk)
    monkeypatch.setattr(tempfile, "tempdir", str(offline.temp))
    monkeypatch.setenv("PATH", offline.env["PATH"])
    before = snapshot(root)
    code = family_module.main(["add", "--family-root", str(root),
                               "--member", f"{ORG}/{SPARE}",
                               "--local-remote-dir", str(family["remotes"])])
    out, err = capsys.readouterr()
    assert code == 2, out + err
    assert refusal(err) == (
        "REFUSED family-manifest-unwritable: family.yaml could not be "
        f"rewritten with {SPARE}'s pin: No space left on device. "
        + UNDONE.format(
            restored=f"the gitlink at members/{SPARE} unstaged, "
                     f"members/{SPARE} removed, "
                     f".git/modules/members/{SPARE} removed, "
                     ".gitmodules removed, as there was none before, "
                     f"`submodule.members/{SPARE}` dropped from the holder's "
                     "git config"),
        "Remediation: make family.yaml writable, and check the disk has "
        "room, then run the same command again.")
    assert_unchanged(root, before, SPARE)
    assert not (root / ".gitmodules").exists()
    assert not (root / "members").exists()
    assert not (root / ".git" / "modules").exists()
    offline.assert_left_nothing()


def test_a_holder_that_is_a_linked_worktree_unwinds_the_store_git_keeps_there(
        family, holder, offline, tmp_path, family_module, monkeypatch,
        capsys):
    """A LANE OPENS ITS PULL REQUEST FROM A LINKED WORKTREE, where `.git` is
    a file and git keeps a mount's object store under
    `.git/worktrees/<name>/modules/`, not `.git/modules/`. The unwind deletes
    the store where git put it — asked of `git rev-parse --git-path`, not
    assumed — so the same command, run again, mounts afresh instead of
    meeting a store `git submodule add` refuses to reuse."""
    lane = tmp_path / "lane"
    git("worktree", "add", "-q", "-b", "add-irqs", str(lane), cwd=holder)
    gitdir = Path(git("rev-parse", "--absolute-git-dir",
                      cwd=lane).stdout.strip())
    named = git("rev-parse", "--git-path", f"modules/members/{SPARE}",
                cwd=lane).stdout.strip()
    store = lane / named
    # The case this test exists for: the store is the WORKTREE's, which a
    # `.git/modules/<path>` written into the code would never find.
    assert gitdir.parent.name == "worktrees"
    assert store.parent.parent == gitdir / "modules"
    listed = sorted(os.listdir(gitdir))

    monkeypatch.setattr(family_module, "write_lf", full_disk)
    monkeypatch.setattr(tempfile, "tempdir", str(offline.temp))
    monkeypatch.setenv("PATH", offline.env["PATH"])
    before = snapshot(lane)
    code = family_module.main(["add", "--family-root", str(lane),
                               "--member", f"{ORG}/{SPARE}",
                               "--local-remote-dir", str(family["remotes"])])
    out, err = capsys.readouterr()
    assert code == 2, out + err
    assert refusal(err) == (
        "REFUSED family-manifest-unwritable: family.yaml could not be "
        f"rewritten with {SPARE}'s pin: No space left on device. "
        + UNDONE.format(
            restored=f"the gitlink at members/{SPARE} unstaged, "
                     f"members/{SPARE} removed, "
                     f"{named} removed, "
                     ".gitmodules restored byte for byte, "
                     f"`submodule.members/{SPARE}` dropped from the holder's "
                     "git config"),
        "Remediation: make family.yaml writable, and check the disk has "
        "room, then run the same command again.")
    assert_unchanged(lane, before, SPARE)
    assert not store.exists()
    assert sorted(os.listdir(gitdir)) == listed

    # A fresh process, so nothing patched above reaches it.
    again = offline.add(lane, SPARE, remotes=family["remotes"])
    assert again.returncode == 0, again.stdout + again.stderr
    assert store.is_dir()
    assert git("show", "--name-only", "--format=", "HEAD",
               cwd=lane).stdout.split() == [
        ".gitmodules", "family.yaml", f"members/{SPARE}"]
    assert git("status", "--porcelain", cwd=lane).stdout == ""
    offline.assert_left_nothing()


def test_an_unwind_that_cannot_finish_says_what_is_left(
        family, holder, offline, family_module, monkeypatch, capsys):
    """A PARTIAL UNWIND SAYS SO. When one step cannot be put back — here the
    holder's git config is locked — the refusal names what WAS restored and
    what was NOT, with git's own reason, and sends the human to `git status`
    before `add` runs again. It never claims a holder exactly as it was."""
    def locked(self):
        raise family_module.CommandFailed(
            ["git", "config", "--local", "--remove-section",
             f"submodule.members/{SPARE}"], self.root, 255,
            "error: could not lock config file .git/config: File exists")

    monkeypatch.setattr(family_module, "write_lf", full_disk)
    monkeypatch.setattr(family_module.MountRollback, "_undo_registration",
                        locked)
    monkeypatch.setattr(tempfile, "tempdir", str(offline.temp))
    monkeypatch.setenv("PATH", offline.env["PATH"])
    before = snapshot(holder)
    code = family_module.main(["add", "--family-root", str(holder),
                               "--member", f"{ORG}/{SPARE}",
                               "--local-remote-dir", str(family["remotes"])])
    out, err = capsys.readouterr()
    assert code == 2, out + err
    assert refusal(err) == (
        "REFUSED family-manifest-unwritable: family.yaml could not be "
        f"rewritten with {SPARE}'s pin: No space left on device. The mount "
        f"was undone only in part (the gitlink at members/{SPARE} unstaged, "
        f"members/{SPARE} removed, .git/modules/members/{SPARE} removed, "
        ".gitmodules restored byte for byte); NOT "
        f"`submodule.members/{SPARE}` dropped from the holder's git config: "
        f"`git config --local --remove-section submodule.members/{SPARE}`: "
        "error: could not lock config file .git/config: File exists. Put "
        "those back by hand — `git status` shows what is left — before "
        "running `add` again.",
        "Remediation: make family.yaml writable, and check the disk has "
        "room, then run the same command again.")
    # Everything but the one step it names is back; that one is still there.
    after = snapshot(holder)
    assert {k: v for k, v in after.items() if k != "config"} == \
        {k: v for k, v in before.items() if k != "config"}
    assert f"submodule.members/{SPARE}.url=" in after["config"]
    assert f"submodule.members/{SPARE}." not in before["config"]
    offline.assert_left_nothing()


def test_a_failure_after_the_commit_landed_undoes_nothing(
        family, holder, offline, family_module, monkeypatch, capsys):
    """NEVER OVER A COMMIT THAT LANDED. A failure after `git commit` has
    succeeded — here the HEAD read `_commit_one` ends with — must not unwind:
    undoing the tree under a landed commit would leave a working copy that
    contradicts its own history. The commit stands, the holder is clean and
    valid, and the sentence says where to look."""
    commit_one = family_module._commit_one

    def landed_then_failed(root, *args, **kwargs):
        commit_one(root, *args, **kwargs)
        raise family_module.Refusal(
            "git-failed", f"`git rev-parse HEAD` in {root} exited 128: "
            "fatal: injected after the commit", "Remediation: injected.")

    monkeypatch.setattr(family_module, "_commit_one", landed_then_failed)
    monkeypatch.setattr(tempfile, "tempdir", str(offline.temp))
    monkeypatch.setenv("PATH", offline.env["PATH"])
    was = git("rev-parse", "HEAD", cwd=holder).stdout.strip()
    code = family_module.main(["add", "--family-root", str(holder),
                               "--member", f"{ORG}/{SPARE}",
                               "--local-remote-dir", str(family["remotes"])])
    out, err = capsys.readouterr()
    assert code == 2, out + err
    assert refusal(err) == (
        f"REFUSED git-failed: `git rev-parse HEAD` in {holder.resolve()} "
        "exited 128: fatal: injected after the commit. The commit had "
        "already landed, so nothing was undone: `git log -1` in the holder "
        "shows it.",
        "Remediation: injected.")
    assert git("rev-parse", "HEAD~1", cwd=holder).stdout.strip() == was
    assert git("show", "--name-only", "--format=", "HEAD",
               cwd=holder).stdout.split() == [
        ".gitmodules", "family.yaml", f"members/{SPARE}"]
    assert git("status", "--porcelain", cwd=holder).stdout == ""
    assert (holder / "members" / SPARE / "project.yaml").is_file()
    assert validate(holder).returncode == 0
    offline.assert_left_nothing()


@pytest.mark.parametrize("raised", [
    KeyboardInterrupt(), ValueError("injected after the mount")],
    ids=["KeyboardInterrupt", "ValueError"])
def test_an_exception_that_is_no_refusal_is_unwound_and_raised_unchanged(
        family, holder, offline, family_module, monkeypatch, capsys, raised):
    """NOT ONLY A REFUSAL OR A FAILED GIT COMMAND IS UNWOUND. Ctrl-C after
    the mount, or an error nobody wrote a refusal for, would otherwise be
    #203 by another road: the member staged and left for the next `add` to
    commit. The holder is put back and the sentence says so; then the
    exception goes on EXACTLY as raised — the same object — so Ctrl-C
    still stops the program and a bug still shows its own traceback.
    `tree_digest` runs after the mount and before the pin is written."""
    def interrupted(repo, rev):
        raise raised

    monkeypatch.setattr(family_module, "tree_digest", interrupted)
    before = snapshot(holder)
    with pytest.raises(type(raised)) as caught:
        add_in_process(family_module, monkeypatch, offline, holder, SPARE,
                       family["remotes"])
    assert caught.value is raised
    out, err = capsys.readouterr()
    assert out == (f"checking {ORG}/{SPARE} before mounting it\n"
                   f"mounting {ORG}/{SPARE} at members/{SPARE}\n")
    assert err == mount_undone(SPARE) + "\n"
    assert_unchanged(holder, before, SPARE)
    offline.assert_left_nothing()


def test_a_dotted_neighbours_registration_is_left_as_it_was(
        family, holder, offline, family_module, monkeypatch, capsys):
    """THE HOLDER'S `submodule.<path>` KEYS, BY SECTION. A member's name may
    carry a dot, so `submodule.members/IRQS.v2.url` is the registration of
    the member at `members/IRQS.v2`; a prefix match would take it for
    `members/IRQS`'s, and the unwind would then write a second copy of it
    back. It and `members/IRQSX`'s are each left exactly as they were."""
    neighbours = [(f"submodule.members/{SPARE}.v2.url", "/elsewhere/v2.git"),
                  (f"submodule.members/{SPARE}X.url", "/elsewhere/x.git")]
    for key, value in neighbours:
        git("config", "--local", key, value, cwd=holder)
    monkeypatch.setattr(family_module, "write_lf", full_disk)
    before = snapshot(holder)
    code = add_in_process(family_module, monkeypatch, offline, holder, SPARE,
                          family["remotes"])
    out, err = capsys.readouterr()
    assert code == 2, out + err
    assert refusal(err) == (
        "REFUSED family-manifest-unwritable: family.yaml could not be "
        f"rewritten with {SPARE}'s pin: No space left on device. "
        + mount_undone(SPARE), UNWRITABLE_REMEDIATION)
    assert_unchanged(holder, before, SPARE)
    config = git("config", "--local", "--list", cwd=holder).stdout
    for key, value in neighbours:
        assert config.splitlines().count(f"{key}={value}") == 1
    offline.assert_left_nothing()


def test_a_registration_the_holder_already_had_is_put_back_as_it_was(
        family, holder, offline, family_module, monkeypatch, capsys):
    """A REGISTRATION LEFT BY A PLAIN `git rm`. Taking a member out by hand
    — `git rm`, not `family.py remove` — keeps its `submodule.<path>` keys
    in the holder's git config, and once the object store the refusal names
    is deleted, `add` runs. `git submodule add` rewrites that `url` IN
    PLACE, so an unwind that only dropped the section would lose what the
    holder had: the old keys are put back, and the sentence says "restored",
    not "dropped". (The keys are the config's last, where `--add` puts them
    back, so the listing compares line for line.)"""
    old = [(f"submodule.members/{SPARE}.url", "/where/it/used/to/live.git"),
           (f"submodule.members/{SPARE}.active", "true")]
    for key, value in old:
        git("config", "--local", key, value, cwd=holder)
    monkeypatch.setattr(family_module, "write_lf", full_disk)
    before = snapshot(holder)
    code = add_in_process(family_module, monkeypatch, offline, holder, SPARE,
                          family["remotes"])
    out, err = capsys.readouterr()
    assert code == 2, out + err
    assert refusal(err) == (
        "REFUSED family-manifest-unwritable: family.yaml could not be "
        f"rewritten with {SPARE}'s pin: No space left on device. "
        + mount_undone(SPARE,
                       registered="restored in the holder's git config"),
        UNWRITABLE_REMEDIATION)
    assert_unchanged(holder, before, SPARE)
    assert registration(git("config", "--local", "--list",
                            cwd=holder).stdout, SPARE) == [
        f"{key}={value}" for key, value in old]
    offline.assert_left_nothing()


def test_a_held_index_lock_is_reported_half_by_half(
        family, holder, offline, family_module, monkeypatch, capsys):
    """A PARTIAL UNWIND SAYS EXACTLY WHAT IT DID. Another git process
    holding `index.lock` refuses every index write and nothing else: the
    unwind still puts `.gitmodules`'s BYTES back, removes both trees and
    drops the registration, but cannot unstage the gitlink or put
    `.gitmodules`'s index entry back. So the bytes are listed as restored
    and the index entry as not — never `.gitmodules` as unrestored — and
    git's reason is its `fatal:` line naming the lock, not the advice it
    prints after it, with no doubled full stop."""
    lock = holder / ".git" / "index.lock"

    def locked_then_full(path, text):
        lock.write_bytes(b"")
        full_disk(path, text)

    monkeypatch.setattr(family_module, "write_lf", locked_then_full)
    before = snapshot(holder)
    try:
        code = add_in_process(family_module, monkeypatch, offline, holder,
                              SPARE, family["remotes"])
    finally:
        if lock.exists():
            lock.unlink()
    out, err = capsys.readouterr()
    assert code == 2, out + err
    said, next_line = refusal(err)
    assert re.fullmatch(
        re.escape(
            "REFUSED family-manifest-unwritable: family.yaml could not be "
            f"rewritten with {SPARE}'s pin: No space left on device. The "
            f"mount was undone only in part (members/{SPARE} removed, "
            f".git/modules/members/{SPARE} removed, .gitmodules restored "
            f"byte for byte, `submodule.members/{SPARE}` dropped from the "
            f"holder's git config); NOT the gitlink at members/{SPARE} "
            f"unstaged: `git update-index --force-remove -- "
            f"members/{SPARE}`: ") + INDEX_LOCKED + re.escape(
            "; NOT the index entry of .gitmodules put back as it was: `git "
            "update-index --force-remove -- .gitmodules`: ") + INDEX_LOCKED
        + re.escape(". Put those back by hand — `git status` shows what is "
                    "left — before running `add` again."), said), said
    assert next_line == UNWRITABLE_REMEDIATION
    # What it says is what is there: every byte back, two index entries not.
    after = snapshot(holder)
    for key in ("HEAD", "config", ".gitmodules", "family.yaml", "members",
                "modules", "modules/members"):
        assert after[key] == before[key], key
    assert git("diff", "--cached", "--name-only", cwd=holder).stdout.split() \
        == [".gitmodules", f"members/{SPARE}"]
    offline.assert_left_nothing()


def test_a_refused_add_in_a_holder_with_no_commit_leaves_it_with_none(
        family, offline, tmp_path, family_module, monkeypatch, capsys):
    """NO HEAD IS NOT A COMMIT THAT LANDED. A holder with no commit yet has
    no HEAD before the mount and still none after a failed pin write, and
    the unwind reads that as nothing having landed: it puts the holder back
    — `.gitmodules`, `members/` and `.git/modules/` all absent again, the
    manifest untracked as the human left it — instead of claiming a
    commit."""
    root = unborn_holder(tmp_path)
    monkeypatch.setattr(family_module, "write_lf", full_disk)
    before = snapshot(root)
    assert before["HEAD"] == "" and before["status"] == "?? family.yaml\n"
    code = add_in_process(family_module, monkeypatch, offline, root, SPARE,
                          family["remotes"])
    out, err = capsys.readouterr()
    assert code == 2, out + err
    assert refusal(err) == (
        "REFUSED family-manifest-unwritable: family.yaml could not be "
        f"rewritten with {SPARE}'s pin: No space left on device. "
        + mount_undone(SPARE,
                       gitmodules=".gitmodules removed, as there was none "
                                  "before"), UNWRITABLE_REMEDIATION)
    assert snapshot(root) == before
    assert not (root / ".gitmodules").exists()
    assert not (root / "members").exists()
    assert not (root / ".git" / "modules").exists()
    offline.assert_left_nothing()


@pytest.mark.parametrize("state", ["an annotated tag", "a missing object"])
def test_a_head_that_names_no_readable_commit_is_unwound_like_any_other(
        family, holder, offline, family_module, monkeypatch, capsys, state):
    """HEAD IS READ ONE WAY, BEFORE AND AFTER. `MountRollback` records it with
    `rev-parse -q --verify HEAD^{commit}` and `undo` reads it the same way. A
    bare `rev-parse HEAD` is not the same answer where HEAD is a symbolic ref
    to an ANNOTATED TAG (the tag's own sha, not the commit's) or where the
    branch HEAD is on names a MISSING OBJECT (that object's sha, where the
    other says there is none): `undo` took the difference for the one commit
    having landed, said "nothing was undone" and left the half-added member
    staged, in a holder it had unwound before. The two states are corrupt, so
    they are built with git's own plumbing and a loose ref, and the holder
    must still come back as it was."""
    if state == "an annotated tag":
        git("-c", "user.name=t", "-c", "user.email=t@t", "tag", "-a", "-m",
            "an annotated tag", "v1", cwd=holder)
        git("symbolic-ref", "HEAD", "refs/tags/v1", cwd=holder)
        # A HEAD that names a tag is on no branch, which the real `add`
        # refuses before the mount (#487, `family-holder-detached`). What
        # this test asks is how the rollback READS such a HEAD, so the
        # branch is answered here as a holder on a branch answers it.
        monkeypatch.setattr(family_module, "_checked_branch",
                            lambda *_args: WORK_BRANCH)
    else:
        # The branch HEAD is on: the fixture's own (#487), not `main`.
        ref = holder / ".git" / "refs" / "heads" / WORK_BRANCH
        ref.parent.mkdir(parents=True, exist_ok=True)
        ref.write_bytes(b"deadbeef" * 5 + b"\n")
        if git("rev-parse", "HEAD", cwd=holder, check=False).stdout.strip() \
                != "deadbeef" * 5:
            pytest.skip("this git does not read a loose ref file over its "
                        "own ref store, so the state cannot be made here")
    # The state this test exists for: the two readings DISAGREE in it.
    commit = git("rev-parse", "-q", "--verify", "HEAD^{commit}", cwd=holder,
                 check=False).stdout.strip()
    assert git("rev-parse", "HEAD", cwd=holder).stdout.strip() != commit
    # `git status` is a fatal error over a missing HEAD object.
    status = state == "an annotated tag"
    monkeypatch.setattr(family_module, "write_lf", full_disk)
    before = snapshot(holder, status=status)
    code = add_in_process(family_module, monkeypatch, offline, holder, SPARE,
                          family["remotes"])
    out, err = capsys.readouterr()
    assert code == 2, out + err
    assert refusal(err) == (
        "REFUSED family-manifest-unwritable: family.yaml could not be "
        f"rewritten with {SPARE}'s pin: No space left on device. "
        + mount_undone(SPARE), UNWRITABLE_REMEDIATION)
    assert_unchanged(holder, before, SPARE, status=status)
    assert git("ls-files", "-s", "--", f"members/{SPARE}", cwd=holder
               ).stdout == ""
    offline.assert_left_nothing()


# --- the happy path, unchanged ----------------------------------------------

def test_a_good_add_is_one_commit_on_its_branch_as_before(family, holder,
                                                          offline):
    """What #203 must not have changed: one commit of exactly three paths,
    the mount left ON ITS BRANCH at the member's tip (the state the doctor's
    `members` row expects of a fresh add), the pin agreeing with the gitlink,
    and the same lines printed — one more, first, saying the member is
    checked before it is mounted."""
    was = git("rev-parse", "HEAD", cwd=holder).stdout.strip()
    tip = git("rev-parse", "main",
              cwd=family["remotes"] / f"{SPARE}.git").stdout.strip()
    result = offline.add(holder, SPARE, remotes=family["remotes"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""
    head = git("rev-parse", "HEAD", cwd=holder).stdout.strip()
    row = {r["project"]: r for r in manifest(holder)["members"]}[SPARE]
    assert row["pin"]["commit"] == tip
    digest = row["pin"]["tree_sha256"]
    assert result.stdout.splitlines() == [
        f"checking {ORG}/{SPARE} before mounting it",
        f"mounting {ORG}/{SPARE} at members/{SPARE}",
        f"  {SPARE:<16} {tip[:12]} tree {digest[:12]}… (project irqs)",
        f"  committed {head[:12]}: .gitmodules, members/{SPARE}, family.yaml",
        "",
        *[line.format(root=holder.resolve(), branch=WORK_BRANCH)
          for line in NEXT],
    ]
    assert git("rev-parse", "HEAD~1", cwd=holder).stdout.strip() == was
    assert git("show", "--name-only", "--format=", "HEAD",
               cwd=holder).stdout.split() == [
        ".gitmodules", "family.yaml", f"members/{SPARE}"]
    assert git("rev-parse", f"HEAD:members/{SPARE}",
               cwd=holder).stdout.strip() == tip
    assert git("symbolic-ref", "HEAD",
               cwd=holder / "members" / SPARE).stdout.strip() == \
        "refs/heads/main"
    assert git("status", "--porcelain", cwd=holder).stdout == ""
    assert validate(holder).returncode == 0
    offline.assert_left_nothing()


def test_the_first_add_to_a_holder_with_no_commit_makes_its_root_commit(
        family, offline, tmp_path):
    """`family.py init` always commits, but a holder made by hand — `git
    init` and a `family.yaml` — has no HEAD until its first member, and
    `add` has always given it that root commit. Recording HEAD for the
    unwind must not turn "no commit yet" into `git-failed`."""
    root = unborn_holder(tmp_path)
    tip = git("rev-parse", "main",
              cwd=family["remotes"] / f"{SPARE}.git").stdout.strip()
    result = offline.add(root, SPARE, remotes=family["remotes"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""
    assert git("rev-list", "--count", "HEAD", cwd=root).stdout.strip() == "1"
    assert git("show", "--name-only", "--format=", "HEAD",
               cwd=root).stdout.split() == [
        ".gitmodules", "family.yaml", f"members/{SPARE}"]
    assert git("rev-parse", f"HEAD:members/{SPARE}",
               cwd=root).stdout.strip() == tip
    row = {r["project"]: r for r in manifest(root)["members"]}[SPARE]
    assert row["pin"]["commit"] == tip
    assert git("status", "--porcelain", cwd=root).stdout == ""
    offline.assert_left_nothing()


# --- a case variant of the mount path, and the whole index (#302) -----------

#: `add`'s mount path for the spare member.
SPARE_MOUNT = f"members/{SPARE}"

#: What a refused `add` ends with when the unwind put back everything it
#: recorded but the index still differs: the middle names what was put back,
#: and `{moved}` what differs.
INDEX_MOVED = (
    "Nothing was committed: the mount has been undone — {restored} — but the "
    "holder's index is NOT as it was before this command ({moved}). Put it "
    "back before running `add` again: `git ls-files -s` lists what the index "
    "now holds, and `git rm -r --cached -- <path>` takes a path new in it "
    "back out and touches no file.")

#: Each case variant of the mount path the index can hold, as `(mode, name,
#: whether HEAD holds it as well)`: a file under it and a gitlink at it,
#: staged, and a file under it that a commit already holds.
CASE_VARIANTS = {
    "a file under it, staged": ("100644", f"Members/{SPARE}/README", False),
    "a submodule at it, staged": ("160000", f"members/{SPARE.lower()}", False),
    "a file under it, committed": ("100644", f"Members/{SPARE}/README", True),
}


def index_bytes(root: Path) -> bytes:
    """`git ls-files -s -z` of `root`, as bytes: the whole index, every
    record and every byte of each name, which is the strongest form of "the
    index is as it was"."""
    return subprocess.run(["git", "ls-files", "-s", "-z"], cwd=str(root),
                          capture_output=True, check=True).stdout


def plant(root: Path, mode: str, name: str) -> None:
    """An index entry `name` and nothing on disk, by `update-index
    --cacheinfo`: a case variant needs no case-insensitive disk this way, so
    the state is the same on every OS. A gitlink names a commit nothing has;
    a file is a blob written as BYTES. `core.protectNTFS` is off for this
    one command, so git for Windows indexes a `*` it would refuse to check
    out."""
    oid = "1" * 40
    if mode != "160000":
        oid = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                             cwd=str(root), input=b"a file\n",
                             capture_output=True,
                             check=True).stdout.decode("ascii").strip()
    git("-c", "core.protectNTFS=false", "update-index", "--add", "--cacheinfo",
        f"{mode},{oid},{name}", cwd=root)


@pytest.mark.parametrize("ignorecase", ["true", "false"])
@pytest.mark.parametrize("variant", list(CASE_VARIANTS))
def test_a_case_variant_of_the_mount_path_in_the_index_is_refused_first(
        family, holder, offline, variant, ignorecase):
    """THE ISSUE'S STATE (#302): the index holds the mount path in another
    case, and nothing is on disk. With `core.ignorecase` set, `git submodule
    add` staged the member's own files under the variant (19 of them beside
    `Members/IRQS/README`). The commit's pathspec then matched nothing, and
    the unwind, asking for exact names, left all 19 staged while saying the
    holder was exactly as it was. Now it is refused before the member is
    even read, on every disk and whatever `core.ignorecase` says, because a
    holder is cloned on macOS and Windows too, where the two spellings are
    one path. The refusal names the entry as the index spells it, and its
    remediation, run as printed, lets the same command through with the
    member under one spelling only. Where HEAD holds the variant, the
    removal is committed first: the add's own commit names `members/IRQS`
    alone, so without it HEAD keeps the variant, records the gitlink under
    another spelling, or both."""
    mode, name, committed = CASE_VARIANTS[variant]
    git("config", "--local", "core.ignorecase", ignorecase, cwd=holder)
    plant(holder, mode, name)
    if committed:
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
            f"Track {name}", cwd=holder)
    spelled = name[:len(SPARE_MOUNT)]
    assert spelled != SPARE_MOUNT and spelled.lower() == SPARE_MOUNT.lower()
    kind = "a submodule" if mode == "160000" else "a file"
    before, index = snapshot(holder), index_bytes(holder)

    result = offline.add(holder, SPARE, remotes=family["remotes"])
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == ""
    assert refusal(result.stderr) == (
        f"REFUSED member-path-taken: the family root's index holds `{name}` "
        f"({kind})" + ("" if name == spelled else f" under {spelled}")
        + f", the same path as {SPARE_MOUNT} on a case-insensitive disk, "
        f"though nothing is at {SPARE_MOUNT} on disk and no `members:` row "
        "names it",
        "Remediation: this is a half-finished add or a hand edit. `git rm -r "
        f"--cached -- {spelled}` takes it out of the index and touches no "
        "file; where HEAD holds it too, commit that removal first, since the "
        f"add's own commit names {SPARE_MOUNT} alone: otherwise HEAD keeps "
        "the other spelling beside the member, or, with `core.ignorecase` "
        "set, records the member's gitlink under a spelling other than the "
        f"{SPARE_MOUNT} that .gitmodules and family.yaml say, or both; then "
        "re-run.")
    assert index_bytes(holder) == index
    assert snapshot(holder) == before
    offline.assert_left_nothing()

    git("rm", "-r", "-q", "--cached", "--", spelled, cwd=holder)
    if committed:
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
            f"Untrack {spelled}", cwd=holder)
    again = offline.add(holder, SPARE, remotes=family["remotes"])
    assert again.returncode == 0, again.stdout + again.stderr
    held = [line for line in git("ls-tree", "-r", "--name-only", "HEAD",
                                 cwd=holder).stdout.splitlines()
            if line.lower() == SPARE_MOUNT.lower()
            or line.lower().startswith(SPARE_MOUNT.lower() + "/")]
    assert held == [SPARE_MOUNT]
    offline.assert_left_nothing()


def test_a_gitlink_git_stages_under_another_spelling_is_named_not_hidden(
        family, holder, offline, family_module, monkeypatch, capsys):
    """THE CLOSING SENTENCE SAYS "EXACTLY AS IT WAS" ONLY FOR WHAT IT
    COMPARED (#302). The index holds `Members/README`, a case variant of
    `members/` and not of the mount path. #318 let it by, by design; Brett
    Heap's ruling of 2026-10-14 ("Refuse on every disk") reverses that, and
    `add` refuses it before the member is read (#362,
    `test_family_members_case_variants.py`). That refusal is switched off
    here, in process, because what this asks is what the unwind says when
    git stages under a name no step asks for all the same. With
    `core.ignorecase` set, git stages the new gitlink in the spelling the
    index already gives the directory, `Members/IRQS`, and the commit, whose
    pathspec is `members/IRQS`, matches nothing. The unwind puts back every
    piece it recorded by name, and the gitlink it never recorded is still
    staged. That used to end "the holder is exactly as it was". The whole
    index is compared now, so the sentence names the entry, and the command
    it names takes it back out, touching no file."""
    git("config", "--local", "core.ignorecase", "true", cwd=holder)
    plant(holder, "100644", "Members/README")
    tip = git("rev-parse", "main",
              cwd=family["remotes"] / f"{SPARE}.git").stdout.strip()
    before, index = snapshot(holder), index_bytes(holder)
    monkeypatch.setattr(family_module, "_members_spellings",
                        lambda root, project, on_disk, rows: [])

    code = add_in_process(family_module, monkeypatch, offline, holder, SPARE,
                          family["remotes"])
    out, err = capsys.readouterr()
    assert code == 2, out + err
    assert out == (f"checking {ORG}/{SPARE} before mounting it\n"
                   f"mounting {ORG}/{SPARE} at {SPARE_MOUNT}\n")
    # The step that failed, and not the command's own spelling, which is the
    # commit's business and changes with it.
    lines = err.splitlines()
    assert lines[0] == (f"REFUSED committing {SPARE} to the family. THE "
                        "EXACT COMMAND WAS:")
    assert lines[-1] == INDEX_MOVED.format(
        restored=f"{SPARE_MOUNT} removed, .git/modules/{SPARE_MOUNT} removed, "
                 ".gitmodules restored byte for byte, family.yaml restored "
                 f"byte for byte, `submodule.{SPARE_MOUNT}` dropped from the "
                 "holder's git config",
        moved=f"new in it: `Members/{SPARE}`")
    # What it says is what is there: one record more, the member's gitlink
    # in the other spelling, and nothing lost.
    was, now = set(index.split(b"\0")), set(index_bytes(holder).split(b"\0"))
    assert now - was == {f"160000 {tip} 0\tMembers/{SPARE}".encode()}
    assert was - now == set()
    offline.assert_left_nothing()

    git("rm", "-r", "-q", "--cached", "--", f"Members/{SPARE}", cwd=holder)
    assert index_bytes(holder) == index
    assert snapshot(holder) == before


def test_the_closing_sentence_names_what_the_index_gained_lost_and_changed(
        holder, family_module):
    """THE SENTENCE AT UNIT LEVEL (#302), for the differences no mount makes
    on its own. The rollback records the index, which is then changed by
    hand. With nothing changed, `undo` keeps the sentence it had. With ONE
    entry restaged and nothing else, its name is unchanged and its record is
    not: comparing names alone would call that holder unchanged. Then six
    entries are new and one is gone as well. `undo` has nothing of its own
    to put back, and it names each kind, five names at most, never calling
    the holder unchanged."""
    rollback = family_module.MountRollback(holder, SPARE_MOUNT)
    assert rollback.undo() == (
        " Nothing was added, and nothing in the holder had changed.")
    then = ("Put it back before running `add` again: `git ls-files -s` lists "
            "what the index now holds, and `git rm -r --cached -- <path>` "
            "takes a path new in it back out and touches no file.")
    plant(holder, "100644", "Makefile")
    assert rollback.undo() == (
        " Nothing was committed, but the holder's index is NOT as it was "
        f"before this command (staged differently: `Makefile`). {then}")
    for n in range(1, 7):
        plant(holder, "100644", f"new/{n}")
    git("update-index", "--force-remove", "--", "README.md", cwd=holder)
    assert rollback.undo() == (
        " Nothing was committed, but the holder's index is NOT as it was "
        "before this command (new in it: `new/1`, `new/2`, `new/3`, `new/4`, "
        "`new/5` and 1 more; gone from it: `README.md`; staged differently: "
        f"`Makefile`). {then}")


def test_an_index_that_cannot_be_read_back_is_never_called_as_it_was(
        holder, family_module, monkeypatch):
    """The comparison is a git command too. If the index cannot be read
    back after the unwind, every step may still have been undone, but the
    index has not been shown to be as it was. The sentence says exactly
    that, with git's reason, and sends the human to `git ls-files -s`, as
    the sentence for an index that differs does. It never calls the holder
    as it was, nor the unwind partial, and the refusal it ends is still the
    one printed."""
    rollback = family_module.MountRollback(holder, SPARE_MOUNT)

    def unreadable(root):
        raise family_module.Refusal(
            "git-failed", f"`git ls-files -s -z` in {root} exited 128: "
            "fatal: index file corrupt")

    monkeypatch.setattr(family_module, "_index_records", unreadable)
    assert rollback.undo() == (
        " Nothing was committed, but the holder's index could not be read "
        "back to confirm it is as it was before this command: `git ls-files "
        f"-s -z` in {holder} exited 128: fatal: index file corrupt. Check it "
        "before running `add` again: `git ls-files -s` lists what the index "
        "now holds.")


def test_the_index_is_asked_at_the_mount_path_in_any_case_and_literally(
        holder, family_module):
    """`_index_entries` (#302): every entry AT the path or UNDER it, in any
    case, each as the index spells it. Never a neighbour the path is only a
    prefix of (`members/IRQSX`), never a variant of `members/` alone, and
    never what a glob would add: `members/IRQ*` is a name, so it selects
    itself in any case, where `git --icase-pathspecs` would read it as a
    glob and select `members/IRQS`, `members/IRQSX/b` and `MEMBERS/irqs/a`
    besides. (The entries are planted, with nothing on disk.)

    A VARIANT OF `members/` ALONE IS NO LONGER LET BY. #318 pinned it here
    as not refused, by design; Brett Heap's ruling of 2026-10-14 ("Refuse
    on every disk") reverses that (#362). It is still not `_index_entries`'s
    to select, since it is not at the mount path, and `_members_spellings`
    names it instead, with every other path under a spelling of `members`
    that is not `members` itself, and each case variant of the mount path
    under `members/` itself, by the entry its remedy acts on, never the
    other spelling's directory (#574's review, B1). With nothing on disk,
    that remedy takes it out of the index, as #318's does."""
    for name in ("MEMBERS/irqs/a", SPARE_MOUNT, f"{SPARE_MOUNT}X/b",
                 "Members/README", "members/IRQ*/c", "members/irq*"):
        plant(holder, "100644", name)
    plant(holder, "160000", f"members/{SPARE.lower()}/d")
    assert family_module._index_entries(holder, SPARE_MOUNT) == [
        ("MEMBERS/irqs/a", "a file"), (SPARE_MOUNT, "a file"),
        (f"members/{SPARE.lower()}/d", "a submodule")]
    assert family_module._index_entries(holder, "members/IRQ*") == [
        ("members/IRQ*/c", "a file"), ("members/irq*", "a file")]
    found = family_module._members_spellings(
        holder, SPARE, family_module._members_on_disk(holder))
    assert [(spelled.name, spelled.target, spelled.mount, spelled.remedy)
            for spelled in found] == [
        ("MEMBERS/irqs/a", "MEMBERS/irqs", True, "git rm -r --cached"),
        ("Members/README", "Members/README", False, "git rm -r --cached"),
        (f"members/{SPARE.lower()}/d", f"members/{SPARE.lower()}", True,
         "git rm -r --cached")]


def test_a_conflicted_entry_at_the_mount_path_is_counted_once_per_stage(
        holder, family_module):
    """`member-path-taken` counts as main counted (#302): one per index
    record, so a path conflicted at three stages is named "and 2 more". The
    read now lists the whole index, and an exact-case entry still gets the
    text #242 wrote, byte for byte. (The three stages are written as BYTES
    on stdin.)"""
    blob = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                          cwd=str(holder), input=b"a file\n",
                          capture_output=True,
                          check=True).stdout.decode("ascii").strip()
    subprocess.run(["git", "update-index", "--index-info"], cwd=str(holder),
                   input=b"".join(f"100644 {blob} {stage}\t{SPARE_MOUNT}/"
                                  "README\n".encode("ascii")
                                  for stage in (1, 2, 3)),
                   capture_output=True, check=True)
    with pytest.raises(family_module.Refusal) as caught:
        family_module._checked_mount_path(holder, SPARE, SPARE_MOUNT)
    assert (caught.value.code, caught.value.detail,
            caught.value.remediation) == (
        "member-path-taken",
        f"the family root's index holds `{SPARE_MOUNT}/README` (a file) and "
        f"2 more under {SPARE_MOUNT}, though nothing is at {SPARE_MOUNT} on "
        "disk and no `members:` row names it",
        "Remediation: this is a half-finished add or a hand edit. `git rm -r "
        f"--cached -- {SPARE_MOUNT}` takes it out of the index and touches no "
        "file; then re-run.")


# --- a section under ANOTHER name at the mount path (#300) ------------------
#
# The mirror of `member-name-taken` (#242), which refuses a section whose NAME
# is the mount path for another path: here a section under another name
# already gives the mount PATH. git writes the member's own section beside it
# without a word, so `add` exited 0 and committed two sections for one path,
# `validate-family.py` said `family ok`, and a recursive clone followed the
# one LAST in the file — the other's url, as soon as an edit put it there.
# Each holder below is built in git's index and objects, never through a
# checkout of the file.

#: A section under another name whose path is the spare's mount path, with a
#: url nothing can fetch: what a half-removed member, a hand edit or a merge
#: that kept both sides leaves behind.
GHOST = (f'[submodule "ghost"]\n\tpath = members/{SPARE}\n'
         "\turl = /nowhere/ghost.git\n").encode("utf-8")

GHOST_REFUSED = (
    "REFUSED member-path-registered: .gitmodules already gives the path "
    f"members/{SPARE} to the submodule named `ghost` (url "
    f"/nowhere/ghost.git), and that is the path {SPARE} is mounted at")

#: How the refusal spells taking GHOST out: by key, which reaches every
#: section, one command for each key it holds, in the order git lists
#: them.
GHOST_REMOVAL = (
    "`git config -f .gitmodules --unset-all submodule.ghost.path` and "
    "`git config -f .gitmodules --unset-all submodule.ghost.url`")


def ghost_remediation(removal: str, off_disk: bool = False) -> str:
    """What `member-path-registered` tells the human to do, around the
    `git config` command(s), `removal`, that take each section out — and,
    only where the working tree has no `.gitmodules` (`off_disk`), how to
    put back the copy git read."""
    return (
        "Remediation: git would write the member's own section beside it, "
        "and a recursive clone of the holder follows whichever section for "
        "that path comes last in the file. A section somebody wrote is not "
        "this tool's to drop or rewrite, so take it out by hand, in a POSIX "
        f"shell — {removal}, then `git add .gitmodules` — and re-run."
        + (" With no .gitmodules in the working tree, put back the copy git "
           "read first: `git checkout -- .gitmodules` (the index's), or `git "
           "checkout HEAD -- .gitmodules`." if off_disk else ""))


def gitmodules_with(root: Path, extra: bytes, kept_in: str) -> bytes:
    """HEAD's `.gitmodules` with `extra` appended, kept ONLY where `kept_in`
    says, and built in git's index and objects rather than through a
    checkout: "the work tree only" writes it to disk and neither stages nor
    commits it — a hand edit nobody has staged, the commonest ghost, which
    only a reader that asks the working tree FIRST sees; "the work tree"
    commits it and writes the same bytes to disk; "the index" stages it over
    HEAD's and leaves no file on disk; "HEAD" commits it, then takes it off
    the disk AND out of the index, where `git submodule add` still reads it.
    Returns the bytes."""
    data = subprocess.run(["git", "show", "HEAD:.gitmodules"],
                          cwd=str(root), capture_output=True,
                          check=True).stdout + extra
    if kept_in == "the work tree only":
        (root / ".gitmodules").write_bytes(data)
        return data
    blob = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                          cwd=str(root), input=data, capture_output=True,
                          check=True).stdout.decode("ascii").strip()
    git("update-index", "--cacheinfo", f"100644,{blob},.gitmodules",
        cwd=root)
    if kept_in != "the index":
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
            "A section of somebody else's", cwd=root)
    if kept_in == "the work tree":
        (root / ".gitmodules").write_bytes(data)
    else:
        (root / ".gitmodules").unlink()
    if kept_in == "HEAD":
        git("rm", "-q", "--cached", "--", ".gitmodules", cwd=root)
    return data


def git_section(scratch: Path, name: str, **values: str) -> bytes:
    """`[submodule "<name>"]` holding `values`, in the bytes GIT writes for
    them, for `gitmodules_with` to append. A value read from git must be
    escaped as git escapes it: a Windows path's backslashes written raw
    (`D:\\a\\...`) are escapes git does not know, and the file is then one it
    cannot read at all (`bad config line`). `scratch` is a file of the
    test's own, written afresh."""
    if scratch.exists():
        scratch.unlink()
    for key, value in values.items():
        git("config", "-f", str(scratch), f"submodule.{name}.{key}", value,
            cwd=scratch.parent)
    return scratch.read_bytes()


def gitmodules_paths(root: Path) -> list[str]:
    """Every `path` HEAD's `.gitmodules` gives, in file order, as git lists
    them."""
    listed = git("config", "--blob", "HEAD:.gitmodules", "--list",
                 cwd=root).stdout.splitlines()
    return [line.partition("=")[2] for line in listed
            if line.partition("=")[0].rpartition(".")[2] == "path"]


def take_out_as_printed(root: Path, remediation: str) -> list[str]:
    """Run each `git config` command `remediation` prints, exactly as
    printed (split as a POSIX shell splits it, run with no shell), then
    stage `.gitmodules`, as the remediation says. Returns the commands."""
    commands = re.findall(r"`(git config [^`]*)`", remediation)
    for command in commands:
        git(*shlex.split(command)[1:], cwd=root)
    git("add", "--", ".gitmodules", cwd=root)
    return commands


def refused_unchanged(result: subprocess.CompletedProcess, root: Path,
                      before: dict) -> tuple[str, str]:
    """Refused before the member was read — nothing on stdout, nothing
    cloned or mounted — with the holder byte for byte as `before` recorded
    it. Returns `(the REFUSED line, the remediation)`."""
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == ""
    assert snapshot(root) == before
    assert not (root / "members" / SPARE).exists()
    assert not (root / ".git" / "modules" / "members" / SPARE).exists()
    return refusal(result.stderr)


@pytest.mark.parametrize("kept_in", ["the work tree only", "the work tree",
                                     "the index", "HEAD"])
def test_a_section_under_another_name_at_the_mount_path_is_refused(
        family, holder, offline, kept_in):
    """THE ISSUE'S PROBE, from each copy of the file `git submodule add`
    reads: the working tree's — an unstaged hand edit as well as a committed
    ghost — else the index's, else HEAD's. A section named `ghost` gives
    `members/IRQS` to a url nothing can fetch, and `add --member
    InkRouter/IRQS` is refused before the member is read — not one line on
    stdout, nothing cloned, nothing mounted — naming the section and its
    url, and the holder is byte for byte as it was, the ghost included: it
    is somebody's registration, not this tool's to drop. Only where the
    working tree has no `.gitmodules` does the remediation say how to put
    one back."""
    gitmodules_with(holder, GHOST, kept_in)
    before = snapshot(holder)
    result = offline.add(holder, SPARE, remotes=family["remotes"])
    assert refused_unchanged(result, holder, before) == (
        GHOST_REFUSED, ghost_remediation(
            GHOST_REMOVAL, off_disk=kept_in in ("the index", "HEAD")))
    offline.assert_left_nothing()


def test_a_section_named_the_mount_path_in_another_case_is_another_name(
        family, holder, offline):
    """git's submodule names are case-sensitive, so `Members/IRQS` is
    ANOTHER name than the `members/IRQS` git gives the mount, and its
    section for the mount path is a ghost like any other: refused, named in
    its own spelling."""
    gitmodules_with(holder, (f'[submodule "Members/{SPARE}"]\n'
                             f"\tpath = members/{SPARE}\n"
                             "\turl = /nowhere/ghost.git\n").encode(),
                    "the work tree")
    before = snapshot(holder)
    result = offline.add(holder, SPARE, remotes=family["remotes"])
    said, _ = refused_unchanged(result, holder, before)
    assert said == (
        "REFUSED member-path-registered: .gitmodules already gives the path "
        f"members/{SPARE} to the submodule named `Members/{SPARE}` (url "
        f"/nowhere/ghost.git), and that is the path {SPARE} is mounted at")
    offline.assert_left_nothing()


@pytest.mark.parametrize("other", [
    None, (f"members/{SPARE}X", "ghost"), (f"members/{SPARE}/", "ghost"),
    (f"members/{SPARE}", f"members/{SPARE}")],
    ids=["no other section", "another path", "a trailing slash",
         "the member's own name"])
def test_a_section_that_is_not_another_name_at_the_mount_path_is_added_past(
        family, holder, offline, other):
    """THE CONTROL. The plain add still exits 0, and so does one past a
    section for ANOTHER path: one that only begins like the mount path, or
    one that ends in a slash — git compares a section's path exactly, so a
    recursive clone never fetches the mount path from it, and neither does
    this refusal. So does one past a section that already carries the
    member's own name for its own path — what `remove` leaves behind when a
    ghost came after the member's section (#300) — which git rewrites in
    place. Each commits ONE section for the mount path, with the member's
    url. The holder passes its own gate, except where the other section's
    path is one no row names, which is now a finding of its own (#361) and
    the only one: the add did not make it, and did not make it worse."""
    if other is not None:
        path, name = other
        gitmodules_with(holder, (f'[submodule "{name}"]\n\tpath = {path}\n'
                                 "\turl = /nowhere/ghost.git\n").encode(),
                        "the work tree")
    # The member's url, spelled the way `add` spelled IRRS's beside it.
    url = git("config", "-f", ".gitmodules", "submodule.members/IRRS.url",
              cwd=holder).stdout.strip()[:-len("IRRS.git")] + f"{SPARE}.git"
    result = offline.add(holder, SPARE, remotes=family["remotes"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""
    assert gitmodules_paths(holder).count(f"members/{SPARE}") == 1
    assert git("config", "--blob", "HEAD:.gitmodules",
               f"submodule.members/{SPARE}.url",
               cwd=holder).stdout.strip() == url
    assert git("status", "--porcelain", cwd=holder).stdout == ""
    checked = validate(holder)
    if other is None or other[0] == f"members/{SPARE}":
        assert checked.returncode == 0, checked.stderr + checked.stdout
    else:
        assert checked.returncode == 1, checked.stderr + checked.stdout
        assert [line.split(":", 1)[0] for line in checked.stderr.splitlines()
                if line.startswith("FINDING")] == [
            "FINDING gitmodules-path-unnamed"], checked.stderr
        assert (f".gitmodules gives the path {other[0]} to the submodule "
                f'named "{other[1]}"') in checked.stderr
    offline.assert_left_nothing()


def test_every_section_at_the_mount_path_is_named_and_taken_out_as_printed(
        family, holder, offline):
    """TWO SECTIONS under other names at one mount path, one named with a
    space and one with no url: the refusal names both, each with its url or
    the want of one, and its `git config` commands, typed exactly as
    printed, take both out — after which the same `add` runs, and the holder
    gives the mount path to one section, the member's."""
    gitmodules_with(holder, GHOST + (f'[submodule "old {SPARE}"]\n'
                                     f"\tpath = members/{SPARE}\n").encode(),
                    "the work tree")
    before = snapshot(holder)
    refused = offline.add(holder, SPARE, remotes=family["remotes"])
    said, remediation = refused_unchanged(refused, holder, before)
    assert said == (
        "REFUSED member-path-registered: .gitmodules already gives the path "
        f"members/{SPARE} to the submodules named `ghost` (url "
        f"/nowhere/ghost.git) and `old {SPARE}` (no url), and that is the "
        f"path {SPARE} is mounted at")
    assert remediation == ghost_remediation(
        f"{GHOST_REMOVAL} and `git config -f .gitmodules --unset-all "
        f"'submodule.old {SPARE}.path'`")
    assert len(take_out_as_printed(holder, remediation)) == 3, remediation
    added = offline.add(holder, SPARE, remotes=family["remotes"])
    assert added.returncode == 0, added.stdout + added.stderr
    assert gitmodules_paths(holder) == [
        "members/IRRS", "members/IRSS", f"members/{SPARE}"]
    assert git("status", "--porcelain", cwd=holder).stdout == ""
    assert validate(holder).returncode == 0
    offline.assert_left_nothing()


@pytest.mark.parametrize("header, name", [
    (f'[submodule "old]{SPARE}"]', f"old]{SPARE}"),
    ('[Submodule "ghost"]', "ghost")],
    ids=["a name with ]", "a header a hand capitalised"])
def test_a_section_git_cannot_name_by_section_is_taken_out_as_printed(
        family, holder, offline, header, name):
    """THE PRINTED COMMANDS WORK FOR EVERY SECTION. `git config
    --remove-section` cannot address a section whose name holds `]`, nor one
    whose header a hand spelled `[Submodule "..."]` (git 2.43 says `no such
    section` for both), so the refusal takes a section out by its keys,
    which reach every section `git config --list` names. Run exactly as
    printed, they clear the way for the same `add`."""
    gitmodules_with(holder, (f"{header}\n\tpath = members/{SPARE}\n"
                             "\turl = /nowhere/ghost.git\n").encode(),
                    "the work tree only")
    before = snapshot(holder)
    refused = offline.add(holder, SPARE, remotes=family["remotes"])
    said, remediation = refused_unchanged(refused, holder, before)
    assert said == (
        "REFUSED member-path-registered: .gitmodules already gives the path "
        f"members/{SPARE} to the submodule named `{name}` (url "
        f"/nowhere/ghost.git), and that is the path {SPARE} is mounted at")
    quoted = [shlex.quote(f"submodule.{name}.{key}")
              for key in ("path", "url")]
    assert remediation == ghost_remediation(
        f"`git config -f .gitmodules --unset-all {quoted[0]}` and "
        f"`git config -f .gitmodules --unset-all {quoted[1]}`")
    assert len(take_out_as_printed(holder, remediation)) == 2, remediation
    added = offline.add(holder, SPARE, remotes=family["remotes"])
    assert added.returncode == 0, added.stdout + added.stderr
    assert gitmodules_paths(holder) == [
        "members/IRRS", "members/IRSS", f"members/{SPARE}"]
    assert validate(holder).returncode == 0
    offline.assert_left_nothing()


@pytest.mark.parametrize("same_url", [False, True],
                         ids=["another url", "the same url"])
def test_the_validator_finds_two_sections_for_one_path(family, holder,
                                                       tmp_path, same_url):
    """`gitmodules-path-twice`, so a holder that already has a ghost fails
    its own gate instead of passing it. One section per path is clean; one
    more for `members/IRRS`, under another name and LAST in the file — the
    one a recursive clone follows — is the only finding, under `--pins` and
    `--no-members` as well, because it reads `.gitmodules` alone. Two
    sections for one path are a finding whatever their urls: the same url
    twice is still one path given twice, and the next edit can change
    either."""
    assert validate(holder).returncode == 0
    url = git("config", "-f", ".gitmodules", "submodule.members/IRRS.url",
              cwd=holder).stdout.strip()
    other = url if same_url else "/nowhere/ghost.git"
    # Written by git, so the member's url — a path with backslashes on
    # Windows — is escaped as git escapes it.
    gitmodules_with(holder, git_section(tmp_path / "ghost-section", "ghost",
                                        path="members/IRRS", url=other),
                    "the work tree")
    for extra in ((), ("--pins",), ("--no-members",)):
        result = validate(holder, *extra)
        assert result.returncode == 1, result.stderr + result.stdout
        assert [line for line in result.stderr.splitlines()
                if line.startswith("FINDING")] == [
            "FINDING gitmodules-path-twice: .gitmodules gives the path "
            f"members/IRRS to 2 submodules, `members/IRRS` (url {url}), "
            f"`ghost` (url {other}). A recursive clone fetches that path "
            "from only one of them, the last in the file, so the order of "
            "the sections decides which repository lands there. Keep the one "
            "whose url is the member's (`family.py add` names it after its "
            "path, `members/IRRS`) and take each other out by hand, `git "
            "config -f .gitmodules --unset-all submodule.<name>.<key>` for "
            "every key that section holds, so a submodule later given its "
            "name inherits none of them, then commit .gitmodules."], extra


def test_a_gitmodules_git_cannot_read_is_a_refusal_not_a_pass(holder):
    """The validator reads `.gitmodules` as git reads it, so a file git
    cannot read is a question it cannot answer: a refusal, exit 2, never an
    implicit pass."""
    (holder / ".gitmodules").write_bytes(b'[submodule "broken"\n')
    result = validate(holder)
    assert result.returncode == 2, result.stderr + result.stdout
    assert result.stderr.startswith(
        "REFUSED gitmodules-unreadable: .gitmodules could not be read as git "
        "reads it: `git config -z --file .gitmodules --list` in ")
    assert result.stderr.splitlines()[-1] == (
        "Remediation: git cannot read it either, so none of this holder's "
        "submodules can be cloned from it as it stands. Mend the file by "
        "hand (`git config -f .gitmodules --list` says where it breaks), "
        "then run this again.")


def test_a_validator_with_no_git_to_run_refuses_instead_of_crashing(
        holder, monkeypatch, capsys):
    """`--no-members` ran no git before `.gitmodules` was read, so a
    machine without git now meets one here. That is a question this run
    cannot answer — a refusal, exit 2 — never the traceback that exits 1, a
    finding's code. The holder's own validator is run IN THIS PROCESS with
    its one git call failing as a missing program does, so no PATH is
    changed for anything else. The code is `git-not-runnable`, the one the
    whole validator gives a missing git (#368,
    `tests/test_validate_family_without_git.py`), and no longer
    `gitmodules-unreadable`, which means a file git ran and could not
    read."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    spec = importlib.util.spec_from_file_location(
        "holder_validate_family", holder / "scripts" / "validate-family.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def no_git(args, cwd, binary=False, env=None):
        raise FileNotFoundError(2, "No such file or directory", "git")

    monkeypatch.setattr(module, "git_out", no_git)
    code = module.main(["--root", str(holder), "--no-members"])
    out, err = capsys.readouterr()
    assert code == 2, out + err
    assert err.splitlines() == [
        "REFUSED git-not-runnable: .gitmodules could not be read as git "
        "reads it: git could not be run (No such file or directory)",
        "Remediation: put git on PATH and run this again. This check reads "
        "the holder the way git does, and nothing could clone it or fetch "
        "its members without git either."]


def test_every_key_of_a_ghost_goes_so_a_later_member_of_its_name_inherits_none(
        family, holder, offline, tmp_path):
    """EVERY KEY, NOT ITS PATH AND URL ALONE. A ghost named `members/IRQZ`
    for the spare's mount path also carries `branch`, `shallow` and
    `update`. The refusal prints one `git config --unset-all` per key it
    holds, and run as printed they take the whole section out, header and
    all. Had any key stayed, the add of a member that IS called IRQZ would
    have had git write its path and url into that same section and inherit
    the rest — a `branch = dev` that `git submodule update --remote` then
    fails on, under a gate that says ok. Here IRQZ's section holds its path
    and its url and nothing else."""
    remotes = tmp_path / "remotes"
    remotes.mkdir()
    for name in (SPARE, "IRQZ"):
        shutil.copytree(family["remotes"] / f"{SPARE}.git",
                        remotes / f"{name}.git", symlinks=True)
    gitmodules_with(holder, (
        '[submodule "members/IRQZ"]\n'
        f"\tpath = members/{SPARE}\n\turl = /nowhere/ghost.git\n"
        "\tbranch = dev\n\tshallow = true\n\tupdate = none\n").encode(),
        "the work tree")
    before = snapshot(holder)
    refused = offline.add(holder, SPARE, remotes=remotes)
    said, remediation = refused_unchanged(refused, holder, before)
    assert said == (
        "REFUSED member-path-registered: .gitmodules already gives the path "
        f"members/{SPARE} to the submodule named `members/IRQZ` (url "
        f"/nowhere/ghost.git), and that is the path {SPARE} is mounted at")
    assert remediation == ghost_remediation(" and ".join(
        "`git config -f .gitmodules --unset-all "
        f"submodule.members/IRQZ.{key}`"
        for key in ("path", "url", "branch", "shallow", "update")))
    assert len(take_out_as_printed(holder, remediation)) == 5, remediation
    assert git("config", "-f", ".gitmodules", "--get-regexp",
               r"^submodule\.members/IRQZ\.", cwd=holder,
               check=False).stdout == ""
    assert "members/IRQZ" not in (holder / ".gitmodules").read_text(
        encoding="utf-8")
    added = offline.add(holder, "IRQZ", remotes=remotes)
    assert added.returncode == 0, added.stdout + added.stderr
    listed = git("config", "--blob", "HEAD:.gitmodules", "--get-regexp",
                 r"^submodule\.members/IRQZ\.", cwd=holder).stdout
    assert [line.split(" ", 1)[0] for line in listed.splitlines()] == [
        "submodule.members/IRQZ.path", "submodule.members/IRQZ.url"]
    assert git("status", "--porcelain", cwd=holder).stdout == ""
    offline.assert_left_nothing()
