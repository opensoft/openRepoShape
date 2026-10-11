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
what the POSIX runs prove.) `add` has no `--dry-run`, so there is none to
test here.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from conftest import git, run_script
#: The family fixture and its names, imported from the module that owns them
#: rather than rebuilt: a holder made any other way would test a different
#: holder. Importing the fixture gives this module its own instance of it.
from test_family import (  # noqa: F401
    FAMILY, NAME, ORG, SPARE, family, manifest, validate,
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

NEXT = "NEXT  git -C {root} push -u origin <branch> && open a pull request"


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


def snapshot(root: Path) -> dict:
    """Everything a refused `add` must leave exactly as it found it."""
    def read(name: str) -> bytes | None:
        target = root / name
        return target.read_bytes() if target.is_file() else None

    def listing(directory: Path) -> list[str] | None:
        return sorted(os.listdir(directory)) if directory.is_dir() else None

    return {
        "HEAD": git("rev-parse", "HEAD", cwd=root).stdout,
        "index": git("ls-files", "-s", cwd=root).stdout,
        "status": git("status", "--porcelain", "--ignored", cwd=root).stdout,
        "config": git("config", "--local", "--list", cwd=root).stdout,
        ".gitmodules": read(".gitmodules"),
        "family.yaml": read("family.yaml"),
        "members": listing(root / "members"),
        "modules": listing(root / ".git" / "modules"),
        "modules/members": listing(root / ".git" / "modules" / "members"),
    }


def assert_unchanged(root: Path, before: dict, member: str) -> None:
    """The holder is the one `before` recorded, and carries no trace of
    `member`: the three things #203 found left behind, named one by one."""
    assert git("status", "--porcelain", cwd=root).stdout == ""
    assert snapshot(root) == before
    assert not (root / "members" / member).exists()
    assert not (root / ".git" / "modules" / "members" / member).exists()
    assert f"members/{member}" not in git(
        "config", "--local", "--list", cwd=root).stdout


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
        "everything below it belongs to this tool; fix it by hand this once.")
    assert_unchanged(holder, before, SPARE)
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
        f"    git commit -q -F - -- .gitmodules members/{SPARE} family.yaml",
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
        NEXT.format(root=holder.resolve()),
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
