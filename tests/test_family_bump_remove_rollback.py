# SPDX-License-Identifier: Apache-2.0
"""`family.py bump` and `remove` refuse what they can before they write, and
put the holder back when they are refused after it (#365); `remove` refuses a
`.gitmodules` that gives the member's path to two submodules (#360).

#365. A `bump` or `remove` that failed after its first write — a holder
`pre-commit` hook that exits 1, an `index.lock` somebody else held — exited 2
with `REFUSED a git or gh command failed` and left everything it had done:
`bump` the member checked out at `--to`, `family.yaml` rewritten and both
staged; `remove` the member's checkout emptied by `git submodule deinit -f`,
its registration dropped, the gitlink unstaged, `.gitmodules` and
`family.yaml` changed. Nothing it printed said so. `add` puts the holder back
on the same failures and says what it put back (#203). Two refusals that a
`--dry-run` already asks before it writes were asked by the real runs only
AFTER their first write: `remove` over a `members:` line `family.yaml` this
tool will not rewrite, and `bump --to` a commit whose tree has no
`project.yaml`. Those are now asked first, so the real run and the dry run
refuse at the same point in the same words, and the holder is byte for byte
as it was. What cannot be asked first is put back, and the sentence says what
was put back, or what is left and the commands that put it back, which a
test here types exactly as printed.

#360. git maps a path to ONE submodule name, so with two sections giving
`members/<P>`, `git rm` took out one and the commit kept the other, and
`remove` exited 0. Now it refuses, before any git command that writes, in
both orders of the two sections and under `--dry-run` alike, naming each with
its url and printing the by-key removal of the one that is not the member's
own; typed as printed, that removal lets the same `remove` take the member
out and leave no section for its path.

THE ROLLBACK NEVER CLONES (review 365-5d56e75, MUST-1). `remove`'s checkout
comes back through `git submodule update`, which CLONES where git keeps no
store for the submodule's NAME. The rollback asked about the store the
checkout's own `.git` named instead, so a section renamed by hand had it
clone the member from its url. It now asks about the store git will use,
and runs `update` only where that store holds the commit; under a backstop
(`-c protocol.allow=never`, `--no-fetch`) that a test here makes the check
wrong to prove. A member whose store is gone is removed again, as it was
before the rollback (SHOULD-1), and the registration a rollback writes back
is called the same keys, not the same bytes (NIT-1).

THE SAME FAMILY, RULES AND OFFLINE ENVIRONMENT as `test_family.py` and
`test_family_dry_run.py`: members are scaffolded into local bare
repositories, nothing is created on GitHub, a `gh` on PATH logs and exits 97,
the operator's git configuration is a file of the test's own, and git's
automatic maintenance is off. Every doubled `.gitmodules` is built in git's
own objects from BYTES (`hash-object -w --stdin`, `update-index
--cacheinfo`, a commit), as `test_family_add_refusals.gitmodules_with`
builds one, so no test depends on how a checkout writes a file. A hook is a
`#!/bin/sh` script, which git for Windows runs with its own `sh`, named by a
LOCAL `core.hooksPath` so a global one cannot point git elsewhere.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path

import pytest

from conftest import FILE_PROTOCOL, git, rmtree, run_script
#: The family fixture, its names, the offline environment and the holder's
#: byte-for-byte state, imported from the modules that own them rather than
#: rebuilt: a holder made, or compared, any other way would test a
#: different thing.
from test_family import (  # noqa: F401
    FAMILY, family, family_module, manifest, validate,
)
from test_family_add_refusals import (  # noqa: F401
    INDEX_LOCKED, gitmodules_paths, holder, offline, refusal,
    take_out_as_printed,
)
from test_family_dry_run import (
    BUMP_ORDER, commit_in_mount, isolated, registered_keys, state,
)
from test_family_member_path import MEMBER, OTHER, older, raw

PATH = f"members/{MEMBER}"

#: What the injected `pre-commit` hook says before it exits 1.
HOOK_SAID = "pre-commit: refusing (injected)"


def refusing_hook(root: Path, tmp_path: Path) -> None:
    """A `pre-commit` hook in `root` that refuses every commit."""
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "pre-commit").write_bytes(
        f"#!/bin/sh\necho '{HOOK_SAID}' >&2\nexit 1\n".encode("utf-8"))
    (hooks / "pre-commit").chmod(0o755)
    git("config", "--local", "core.hooksPath", hooks.as_posix(), cwd=root)


def index_lock(root: Path) -> Path:
    """Where git takes the holder's index lock, as git says it."""
    return root / git("rev-parse", "--git-path", "index.lock",
                      cwd=root).stdout.strip()


def snapshot(root: Path, env: dict) -> dict:
    """`test_family_dry_run.state` — HEAD, `ls-files -s -z`, `status
    --porcelain=v1 -z`, `family.yaml`, `.gitmodules`, `.git/config`, the
    member's HEAD, every byte of the work tree, the holder's own objects —
    and the branch the member is on, and the holder's `submodule.*` keys and
    values, sorted: what a rollback of `remove` is held to, since `git
    config --add` puts a section it brings back last in the file."""
    now = state(root, env)
    mount = root / PATH
    now["member branch"] = (
        raw(mount, env, "symbolic-ref", "-q", "HEAD", check=False).stdout
        if (mount / ".git").exists() else None)
    now["registration"] = sorted(
        line for line in raw(root, env, "config", "--local", "--list"
                             ).stdout.decode("utf-8").splitlines()
        if line.startswith("submodule."))
    return now


#: What a rollback puts back, compared in this order. Not the holder's
#: objects: the refused commit's `git add` stored blobs, which nothing
#: records and `git gc` drops. Not `.git/config`'s bytes for `remove`,
#: whose registration `git config --add` brings back as the last section;
#: its keys and values are compared instead.
BUMP_PUT_BACK = ("member HEAD", "member branch", "family.yaml", "index",
                 "status", ".gitmodules", ".git/config", "work tree", "HEAD")
REMOVE_PUT_BACK = ("index", ".gitmodules", "family.yaml", "registration",
                   "work tree", "member HEAD", "member branch", "status",
                   "HEAD")
#: A refusal made before the first write leaves EVERYTHING, objects and the
#: config's bytes included.
EVERYTHING = (*BUMP_ORDER, "member branch", "registration")


def assert_same(before: dict, after: dict, order) -> None:
    """`after` is `before`, key by key in `order`, so a failure names the
    first fact that moved."""
    for key in order:
        assert after[key] == before[key], f"{key} changed"


def bump(root: Path, env: dict, to: str, *extra: str):
    return run_script(FAMILY, "bump", "--family-root", str(root), "--member",
                      MEMBER, "--to", to, *extra, env=env)


def remove(root: Path, env: dict, *extra: str):
    return run_script(FAMILY, "remove", "--family-root", str(root),
                      "--member", MEMBER, *extra, env=env)


def pinned(root: Path, env: dict) -> str:
    return raw(root, env, "rev-parse", f"HEAD:{PATH}").stdout.decode(
        "ascii").strip()


def on_main(root: Path, env: dict) -> str:
    """The commit the member stands at, on the branch `git submodule add`
    left it on, `main`: the state each sentence below names."""
    mount = root / PATH
    assert raw(mount, env, "symbolic-ref", "--short", "-q", "HEAD"
               ).stdout.decode("utf-8").strip() == "main", (
        "premise: the member is on its branch, as `add` leaves it")
    return raw(mount, env, "rev-parse", "HEAD").stdout.decode("ascii").strip()


def loud(command: str, root: Path, code: int) -> list[str]:
    """The head of the block a failed git command gets, as it always has."""
    return ["REFUSED a git or gh command failed. THE EXACT COMMAND WAS:",
            f"    {command}", f"    (in {root.resolve()})", f"    exit {code}",
            "--- output ---"]


def bump_undone(*restored: str) -> str:
    return ("Nothing was bumped: the bump has been undone — "
            + ", ".join(restored) + " — and the holder is exactly as it was "
            "before this command.")


#: How a fully unwound `remove` ends: its registration comes back as `git
#: config --add` writes it, the section last in the file, so the sentence
#: says the same keys and never calls the holder EXACTLY as it was (review
#: 365-5d56e75, NIT-1).
SAME_KEYS = (" Its git config holds the same keys and values as before, the "
             "section put back written last.")


def remove_undone(at: str, *, legs: str = "",
                  held: str = "as it was before this command") -> str:
    """The sentence a fully unwound `remove` ends with, every step named."""
    return ("Nothing was removed: the unmount has been undone — "
            f"the gitlink at {PATH} put back in the index as it was, "
            ".gitmodules restored byte for byte, family.yaml restored byte "
            f"for byte, `submodule.{PATH}` restored in the holder's git "
            f"config, {PATH} checked out again at {at[:12]} on main from the "
            "object store `git rm` keeps" + legs + f" — and the holder is "
            f"{held}." + SAME_KEYS)


def typed_by_hand(root: Path, sentence: str) -> list[str]:
    """Run each command the sentence lists after `in this order:`, exactly
    as printed (split as a POSIX shell splits it, run with no shell, each a
    `git` command), and return them."""
    listed = sentence.split(" in this order: ", 1)[1].split(". Then ", 1)[0]
    commands = re.findall(r"`([^`]*)`", listed)
    for command in commands:
        words = shlex.split(command)
        assert words[0] == "git", command
        subprocess.run(words, cwd=str(root), check=True,
                       capture_output=True)
    return commands


def in_process(module, monkeypatch, env: dict, argv: list[str]) -> int:
    """`family.py` run IN THIS PROCESS, for a failure no subprocess can
    inject, in the same offline environment as a subprocess run."""
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return module.main(argv)


# --- bump: a refusal after the checkout is put back ----------------------

def test_a_bump_a_pre_commit_hook_refuses_puts_the_holder_back(
        family, holder, offline, tmp_path):
    """THE ISSUE'S FIRST PROBE. The hook refuses the ONE commit after the
    member is checked out at `--to`, `family.yaml` rewritten and both paths
    staged. The failed command is quoted as it always was, exit 2, and the
    sentence under it names what was put back: the gitlink's index entry,
    the manifest's bytes and entry, the member back on its branch at the
    commit it stood at. The holder is as it was, byte for byte but the
    blobs the refused commit stored; and the same bump, the hook gone, runs
    at once."""
    env = isolated(offline, tmp_path)
    refusing_hook(holder, tmp_path)
    target, at = older(family), on_main(holder, env)
    assert target != pinned(holder, env), "premise: a bump that moves"
    before = snapshot(holder, env)

    result = bump(holder, env, target)

    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == ""
    assert result.stderr.splitlines() == [
        *loud(f"git commit -q -F - -- :(literal){PATH} :(literal)family.yaml",
              holder, 1),
        HOOK_SAID, "--- end output ---",
        bump_undone(f"the gitlink at {PATH} put back in the index as it was",
                    "family.yaml restored byte for byte",
                    f"{PATH} back on main at {at[:12]}")]
    assert_same(before, snapshot(holder, env), BUMP_PUT_BACK)
    offline.assert_left_nothing()

    git("config", "--local", "--unset", "core.hooksPath", cwd=holder)
    again = bump(holder, env, target)
    assert again.returncode == 0, again.stdout + again.stderr
    assert pinned(holder, env) == target
    assert validate(holder).returncode == 0


def test_a_bump_under_a_held_index_lock_puts_the_holder_back(
        family, holder, offline, tmp_path):
    """The second probe: another git command holds the holder's
    `index.lock`. The member's checkout, which is not the holder's index,
    goes ahead and so does the manifest's rewrite; the first stage fails on
    the lock. Neither index entry had moved, so the sentence names the two
    things that had — the manifest's bytes and the member's checkout — and
    no `validate-family.py` finding is left behind (it used to report
    `member-gitlink-mismatch`)."""
    env = isolated(offline, tmp_path)
    target, at = older(family), on_main(holder, env)
    lock = index_lock(holder)
    lock.write_bytes(b"")
    try:
        before = snapshot(holder, env)
        result = bump(holder, env, target)
        after = snapshot(holder, env)
    finally:
        lock.unlink()

    assert result.returncode == 2, result.stdout + result.stderr
    lines = result.stderr.splitlines()
    assert lines[:5] == loud(f"git --literal-pathspecs add -f -- {PATH}",
                             holder, 128)
    assert re.search(INDEX_LOCKED, result.stderr), result.stderr
    assert lines[-1] == bump_undone("family.yaml restored byte for byte",
                                    f"{PATH} back on main at {at[:12]}")
    assert_same(before, after, BUMP_PUT_BACK)
    assert validate(holder).returncode == 0


# --- remove: a refusal after the unmount is put back ----------------------

def test_a_remove_a_pre_commit_hook_refuses_puts_the_holder_back(
        family, holder, offline, tmp_path):
    """THE ISSUE'S REMOVE PROBE. By the commit, `deinit -f` has emptied the
    member's checkout and dropped its registration, and `git rm` has
    unstaged the gitlink, deleted the directory and taken the section out
    of `.gitmodules`. Each comes back — the checkout from the object store
    `git rm` keeps, with no fetch, on its branch — and the sentence names
    every one. The same `remove`, the hook gone, then runs at once."""
    env = isolated(offline, tmp_path)
    refusing_hook(holder, tmp_path)
    at = on_main(holder, env)
    before = snapshot(holder, env)

    result = remove(holder, env)

    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == ""
    assert result.stderr.splitlines() == [
        *loud("git commit -q -F - -- :(literal).gitmodules "
              f":(literal){PATH} :(literal)family.yaml", holder, 1),
        HOOK_SAID, "--- end output ---", remove_undone(at)]
    assert_same(before, snapshot(holder, env), REMOVE_PUT_BACK)
    offline.assert_left_nothing()

    git("config", "--local", "--unset", "core.hooksPath", cwd=holder)
    again = remove(holder, env)
    assert again.returncode == 0, again.stdout + again.stderr
    assert [r["project"] for r in manifest(holder)["members"]] == [OTHER]
    assert validate(holder).returncode == 0


def test_a_remove_puts_back_the_members_legs_it_had_checked_out(
        family, holder, offline, tmp_path):
    """A BOOTSTRAPPED HOLDER checks each member's legs out inside the mount
    (its `make bootstrap` runs `git submodule update --init --recursive`),
    and `deinit -f` deletes them with the rest. `git submodule update` brings
    back one level, so the legs that were checked out come back by name,
    from the stores inside the member's own, and the holder's work tree is
    byte for byte what it was, theirs included."""
    env = isolated(offline, tmp_path)
    git(*FILE_PROTOCOL, "submodule", "update", "-q", "--init",
        cwd=holder / PATH)
    legs = sorted(name for name in ("spec", "code")
                  if (holder / PATH / name / ".git").exists())
    assert legs == ["code", "spec"], "premise: both legs checked out"
    refusing_hook(holder, tmp_path)
    at = on_main(holder, env)
    before = snapshot(holder, env)

    result = remove(holder, env)

    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.splitlines()[-1] == remove_undone(
        at, legs=", and code and spec in it")
    assert_same(before, snapshot(holder, env), REMOVE_PUT_BACK)


def test_what_deinit_discarded_is_named_not_called_put_back(
        family, holder, offline, tmp_path):
    """`deinit -f` DISCARDS what no object store holds: an untracked file
    in the member, here. The checkout comes back, and the sentence says the
    holder is as it was BUT FOR that, never "exactly"."""
    env = isolated(offline, tmp_path)
    refusing_hook(holder, tmp_path)
    (holder / PATH / "SCRATCH.md").write_bytes(b"never committed\n")
    at = on_main(holder, env)
    before = snapshot(holder, env)

    result = remove(holder, env)

    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.splitlines()[-1] == remove_undone(
        at, held="as it was before this command but for what `git submodule "
        f"deinit -f` discarded in {PATH}, which no object store holds: the "
        "uncommitted changes and the untracked and ignored files `git status "
        "--ignored` listed there")
    assert not (holder / PATH / "SCRATCH.md").exists()
    assert_same(before, snapshot(holder, env),
                ("index", ".gitmodules", "family.yaml", "registration",
                 "member HEAD", "member branch", "HEAD"))


def test_a_remove_under_a_held_index_lock_is_refused_before_it_unmounts(
        family, holder, offline, tmp_path):
    """THE PRE-CHECK. `git submodule deinit` takes no index lock, so with
    one held it emptied the member and dropped its registration, and `git
    rm` then died on the lock. The lock is refused first, named where git
    keeps it, and nothing at all is written: not one byte of the holder, its
    git config included, and the lock left where it was."""
    env = isolated(offline, tmp_path)
    lock = index_lock(holder)
    lock.write_bytes(b"")
    try:
        before = snapshot(holder, env)
        result = remove(holder, env)
        after = snapshot(holder, env)
        assert lock.is_file()
    finally:
        lock.unlink()

    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == ""
    shown = lock.resolve().as_posix()
    assert refusal(result.stderr) == (
        f"REFUSED family-index-locked: the holder's index is locked: {shown} "
        "exists. `git submodule deinit` takes no such lock, so `remove` "
        f"would empty {PATH} and drop its registration and then fail at `git "
        "rm`, its first write to the index; it was refused before either, "
        "and nothing was written.",
        "Remediation: another git command is running in the holder, or one "
        "that stopped left the lock behind. Let it finish and run the same "
        "command again; if no git command is running, delete the lock (`rm "
        f"-f {shlex.quote(shown)}`) and run the same command again.")
    assert_same(before, after, EVERYTHING)


def test_a_remove_dry_run_under_a_held_index_lock_is_unchanged(
        holder, offline, tmp_path):
    """`--dry-run` IS UNCHANGED: it writes nothing, so a lock is not its
    question, and it prints what a real remove would take out, exit 0."""
    env = isolated(offline, tmp_path)
    lock = index_lock(holder)
    lock.write_bytes(b"")
    try:
        dry = remove(holder, env, "--dry-run")
    finally:
        lock.unlink()
    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert dry.stdout.splitlines()[-1].startswith("--dry-run: nothing was "
                                                  "changed")


# --- refusals a dry run asks first are asked first (#365) -----------------

def comment_on_members(root: Path, env: dict) -> None:
    """A comment on the `members:` line, uncommitted: YAML reads past it and
    the line rewrite does not (`family-members-unrecognised`)."""
    manifest_path = root / "family.yaml"
    text = manifest_path.read_bytes()
    assert text.count(b"\nmembers:\n") == 1, "fixture drift"
    manifest_path.write_bytes(text.replace(
        b"\nmembers:\n", b"\nmembers:  # edited by hand\n"))


@pytest.mark.parametrize("verb", ["remove", "bump"])
def test_a_manifest_this_tool_will_not_rewrite_is_refused_before_any_write(
        family, holder, offline, tmp_path, verb):
    """THE COORDINATOR'S (a). `remove` refused `family-members-unrecognised`
    AFTER `deinit` and `git rm`, with the member unmounted and `.gitmodules`
    changed, and `bump` after its checkout, while each one's `--dry-run`
    refused it first and changed nothing. Both runs now refuse it before
    anything is written, in the same words, and the holder is byte for byte
    as it was: the real run's stderr is the dry run's."""
    env = isolated(offline, tmp_path)
    comment_on_members(holder, env)
    extra = ["--to", older(family)] if verb == "bump" else []
    args = [verb, "--family-root", str(holder), "--member", MEMBER, *extra]
    before = snapshot(holder, env)

    real = run_script(FAMILY, *args, env=env)
    after = snapshot(holder, env)
    dry = run_script(FAMILY, *args, "--dry-run", env=env)

    assert real.returncode == dry.returncode == 2, real.stdout + real.stderr
    assert real.stdout == dry.stdout == ""
    assert real.stderr == dry.stderr
    assert refusal(real.stderr)[0].startswith(
        "REFUSED family-members-unrecognised: ")
    assert_same(before, after, EVERYTHING)


def test_a_gitlink_the_index_lacks_and_that_manifest_are_refused_alike(
        holder, offline, tmp_path):
    """REVIEW 365-5d56e75, NIT-2. With the gitlink gone from the index AND
    a `members:` line this tool will not rewrite, the real `remove` refused
    `family-members-unrecognised`, which it asks first, while its dry run
    asked `ls-files` first and printed git's loud `did not match`. The dry
    run asks in the real run's order now: the same refusal, in the same
    words, and nothing written."""
    env = isolated(offline, tmp_path)
    comment_on_members(holder, env)
    raw(holder, env, "update-index", "--force-remove", "--", PATH)
    before = snapshot(holder, env)

    real = remove(holder, env)
    after = snapshot(holder, env)
    dry = remove(holder, env, "--dry-run")

    assert real.returncode == dry.returncode == 2, real.stdout + real.stderr
    assert real.stdout == dry.stdout == ""
    assert real.stderr == dry.stderr
    assert refusal(real.stderr)[0].startswith(
        "REFUSED family-members-unrecognised: ")
    assert_same(before, after, EVERYTHING)


def test_a_to_with_no_project_yaml_is_refused_before_the_checkout(
        holder, offline, tmp_path):
    """THE COORDINATOR'S (b). `bump --to` a commit whose tree has no
    `project.yaml` refused `member-not-a-project` with the member left
    checked out at `--to`, and the holder's own validator then reported it.
    The member's `project.yaml` at `--to` is read from its objects first, as
    the dry run reads it, so the member never moves and the real run's
    words are the dry run's."""
    env = isolated(offline, tmp_path)
    target = commit_in_mount(
        holder, env, lambda mount: (mount / "project.yaml").unlink())
    before = snapshot(holder, env)

    real = bump(holder, env, target)
    after = snapshot(holder, env)
    dry = bump(holder, env, target, "--dry-run")

    assert real.returncode == dry.returncode == 2, real.stdout + real.stderr
    assert real.stdout == dry.stdout == ""
    assert real.stderr == dry.stderr
    assert refusal(real.stderr)[0].startswith("REFUSED member-not-a-project: ")
    assert_same(before, after, EVERYTHING)
    assert validate(holder).returncode == 0


# --- #360: two submodules for the member's path ---------------------------

GHOST = (f'[submodule "ghost"]\n\tpath = {PATH}\n'
         "\turl = /nowhere/ghost.git\n").encode("utf-8")


def head_gitmodules(root: Path) -> bytes:
    """HEAD's `.gitmodules`, as bytes."""
    return subprocess.run(["git", "show", "HEAD:.gitmodules"],
                          cwd=str(root), capture_output=True,
                          check=True).stdout


def commit_gitmodules(root: Path, data: bytes, message: str) -> None:
    """`data` as `.gitmodules`, built in git's objects from BYTES,
    committed, and the same bytes written to the work tree: no test here
    depends on how a checkout writes a file."""
    blob = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                          cwd=str(root), input=data, capture_output=True,
                          check=True).stdout.decode("ascii").strip()
    git("update-index", "--cacheinfo", f"100644,{blob},.gitmodules",
        cwd=root)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        message, cwd=root)
    (root / ".gitmodules").write_bytes(data)


def doubled(root: Path, section: bytes, first: bool) -> None:
    """HEAD's `.gitmodules` with `section` before (`first`) or after the
    member's own, committed (`commit_gitmodules`)."""
    data = head_gitmodules(root)
    commit_gitmodules(root, section + data if first else data + section,
                      "A second section for the member's path")


def renamed_section(root: Path, name: str) -> bytes:
    """HEAD's `.gitmodules` with the member's section renamed by hand to
    `name`, its path and url kept, committed (`commit_gitmodules`). git now
    keeps the member's store at `modules/<name>`, while its checkout's
    `.git` still names `modules/members/<MEMBER>`. Returns the url."""
    data = head_gitmodules(root)
    renamed = data.replace(f'[submodule "{PATH}"]'.encode("utf-8"),
                           f'[submodule "{name}"]'.encode("utf-8"))
    assert renamed != data, "fixture drift"
    commit_gitmodules(root, renamed, "The member's section renamed by hand")
    return git("config", "-f", ".gitmodules", f"submodule.{name}.url",
               cwd=root).stdout.strip()


@pytest.mark.parametrize("first", [False, True],
                         ids=["after the members own", "before it"])
def test_two_sections_for_the_members_path_are_refused_in_either_order(
        holder, offline, tmp_path, first):
    """THE ISSUE'S TWO ORDERS. After the member's own section, git found the
    ghost for the path and `remove` committed the member's own section and
    kept its registration; before it, the commit kept the ghost. Each is now
    refused before any git command that writes, by `remove` and its dry run
    in the same words, naming both sections with their urls in the file's
    order and printing the by-key removal of the one not named after the
    path; the holder is byte for byte as it was. Typed as printed, the
    removal lets the same `remove` run: no section of HEAD's `.gitmodules`
    gives the path, the holder's git config holds no registration under
    either name, and the holder passes its own gate."""
    env = isolated(offline, tmp_path)
    url = git("config", "-f", ".gitmodules", f"submodule.{PATH}.url",
              cwd=holder).stdout.strip()
    doubled(holder, GHOST, first)
    before = snapshot(holder, env)

    real = remove(holder, env)
    after = snapshot(holder, env)
    dry = remove(holder, env, "--dry-run")

    assert real.returncode == dry.returncode == 2, real.stdout + real.stderr
    assert real.stdout == dry.stdout == ""
    assert real.stderr == dry.stderr
    assert_same(before, after, EVERYTHING)
    named = [f"`{PATH}` (url {url})", "`ghost` (url /nowhere/ghost.git)"]
    said, remediation = refusal(real.stderr)
    assert said == (
        f"REFUSED member-path-registered-twice: .gitmodules gives {MEMBER}'s "
        f"path {PATH} to 2 submodules, "
        + ", ".join(named[::-1] if first else named)
        + ". git finds ONE of them for a path, and `git rm` takes out only "
        "that one's sections, so this command's commit would keep the other "
        f"registering {PATH} with no gitlink and no row behind it. No git "
        "command that writes was run and nothing was written.")
    assert remediation == (
        f"Remediation: which of them is {MEMBER}'s is a person's to say, and "
        "a section somebody wrote is not this tool's to drop or rewrite. If "
        f"`{PATH}`, the name `family.py add` gives a member's own section, "
        f"is {MEMBER}'s, take each other one out by hand, in a POSIX shell — "
        "`git config -f .gitmodules --unset-all submodule.ghost.path` and "
        "`git config -f .gitmodules --unset-all submodule.ghost.url`, then "
        "`git add .gitmodules` — and run the same command again.")

    assert len(take_out_as_printed(holder, remediation)) == 2
    removed = remove(holder, env)

    assert removed.returncode == 0, removed.stdout + removed.stderr
    assert PATH not in gitmodules_paths(holder)
    assert registered_keys(holder, env, PATH) == []
    assert registered_keys(holder, env, "ghost") == []
    assert [r["project"] for r in manifest(holder)["members"]] == [OTHER]
    assert raw(holder, env, "status", "--porcelain=v1", "-z").stdout == b""
    assert validate(holder).returncode == 0


def test_two_sections_neither_named_after_the_path_are_both_printed(
        holder, offline, tmp_path):
    """Where NO section has the name `family.py add` gives a member's own,
    which one is the member's is not guessed: the removal is printed for
    every one, and the remediation says to leave out the member's own."""
    env = isolated(offline, tmp_path)
    renamed_section(holder, "old")
    doubled(holder, GHOST, first=False)
    before = snapshot(holder, env)

    result = remove(holder, env)

    assert result.returncode == 2, result.stdout + result.stderr
    assert_same(before, snapshot(holder, env), EVERYTHING)
    remediation = refusal(result.stderr)[1]
    assert (f"None of them has the name `family.py add` gives a member's "
            f"own section, `{PATH}`, so the commands that follow take out "
            f"every one: leave out those of {MEMBER}'s own and run the rest, "
            "in a POSIX shell — `git config -f .gitmodules --unset-all "
            "submodule.old.path` and `git config -f .gitmodules --unset-all "
            "submodule.old.url` and `git config -f .gitmodules --unset-all "
            "submodule.ghost.path` and `git config -f .gitmodules "
            "--unset-all submodule.ghost.url`, then `git add .gitmodules`"
            ) in remediation, remediation


# --- the restore never clones (review 365-5d56e75, MUST-1) ---------------

#: The name a member's section is renamed to by hand, below: git then keeps
#: the member's store at `modules/renamed`, where none is.
RENAMED = "renamed"


def holds(store: Path, commit: str, work: Path) -> bool:
    """Whether the object store `store` holds `commit`. `--work-tree`
    because the store names a checkout of its own that may be gone."""
    return subprocess.run(
        ["git", "--git-dir", str(store), "--work-tree", str(work), "cat-file",
         "-e", f"{commit}^{{commit}}"], capture_output=True).returncode == 0


def foreign_store(store: Path, url: str, tmp_path: Path) -> None:
    """A store at `store` that is NOT the member's: one commit of its own,
    so git can read its HEAD, and `origin` the member's url, which has the
    pinned commit, so a fetch into it would get that commit."""
    work = tmp_path / "foreign"
    git("init", "-q", "--separate-git-dir", str(store), str(work),
        cwd=tmp_path)
    git("commit", "-q", "--allow-empty", "-m", "Not the member's", cwd=work)
    git("remote", "add", "origin", url, cwd=work)


def configured(env: dict, key: str, value: str) -> dict:
    """`env` with one more entry in git's `GIT_CONFIG_COUNT` protocol."""
    count = int(env.get("GIT_CONFIG_COUNT", "0"))
    return {**env, "GIT_CONFIG_COUNT": str(count + 1),
            f"GIT_CONFIG_KEY_{count}": key,
            f"GIT_CONFIG_VALUE_{count}": value}


@pytest.mark.parametrize("store", ["absent", "without the commit"])
def test_a_store_git_would_not_restore_from_is_never_used(
        family, holder, offline, tmp_path, store):
    """THE REVIEW'S PROBE. The member's section renamed by hand: git then
    looks for its store at `modules/renamed`, while the checkout's own
    `.git` names `modules/members/<MEMBER>`, which the rollback used to
    check. With no store under the new name, `git submodule update` cloned
    the member from its url; with one that lacks the commit, it would fetch
    into it. Neither is run: everything else is put back, the directory is
    made again, empty, and the sentence names the store git would use, why
    it is not used, and the store the checkout had, still there. Nothing
    was cloned or fetched, and the holder's git config gained no
    `submodule.renamed.*` key."""
    env = isolated(offline, tmp_path)
    url = renamed_section(holder, RENAMED)
    other = holder / ".git" / "modules" / RENAMED
    if store != "absent":
        foreign_store(other, url, tmp_path)
    refusing_hook(holder, tmp_path)
    at, pin = on_main(holder, env), pinned(holder, env)
    own = Path(git("rev-parse", "--absolute-git-dir", cwd=holder / PATH
                   ).stdout.strip())
    shown = git("rev-parse", "--git-path", f"modules/{RENAMED}",
                cwd=holder).stdout.strip()
    before = snapshot(holder, env)

    result = remove(holder, env)

    assert result.returncode == 2, result.stdout + result.stderr
    why = ("which is not there, and clone it there" if store == "absent" else
           f"which does not hold {pin[:12]}, and fetch it")
    assert result.stderr.splitlines()[-1] == (
        f"The unmount was undone only in part (the gitlink at {PATH} put back "
        "in the index as it was, .gitmodules restored byte for byte, "
        f"family.yaml restored byte for byte); NOT {PATH} checked out again "
        f"at {at[:12]} on main from the object store `git rm` keeps: git "
        f"would check it out of {shown}, {why}, so `git submodule update` "
        f"was not run, and {PATH} was made again, empty; the object store its "
        f"checkout had, {own.as_posix()}, is still there. The checkout of "
        f"{PATH} comes back only from its remote, which this command never "
        "reaches. `git status` shows whether anything else is left, before "
        "running `remove` again.")
    assert_same(before, snapshot(holder, env),
                ("index", ".gitmodules", "family.yaml", "registration",
                 ".git/config", "HEAD"))
    assert list((holder / PATH).iterdir()) == []
    assert not holds(other, pin, holder)
    assert holds(own, pin, holder), "the member's own store is untouched"
    offline.assert_left_nothing()


@pytest.mark.parametrize("store", ["absent", "without the commit"])
def test_a_wrong_store_check_still_reaches_no_remote(
        family, holder, offline, tmp_path, monkeypatch, capsys, store):
    """THE BACKSTOP, PROVED WITHOUT THE NETWORK. The store check is made
    WRONG here (`_unrestorable` answers that git can restore), so `git
    submodule update` runs against the renamed section's store, and the url
    is a LOCAL bare repository that has the commit: a clone or a fetch that
    happened would succeed, and show. No `GIT_ALLOW_PROTOCOL`, which would
    override both.

    - `absent`: `update` would CLONE. The environment allows every protocol
      by default (`protocol.allow=always`, as git allows https and ssh), so
      only the restore's `-c protocol.allow=never` refuses it.
    - `without the commit`: `update` would FETCH into the store. The
      environment allows the file protocol BY NAME (`protocol.file.allow`),
      which `protocol.allow=never` does not override, so only `--no-fetch`
      stops it.

    The step is named as not done, with git's reason; the
    `submodule.renamed.*` keys `update --init` wrote are named, with the
    commands that take them out; and the commit is in no store but the
    member's own."""
    env = isolated(offline, tmp_path)
    url = renamed_section(holder, RENAMED)
    other = holder / ".git" / "modules" / RENAMED
    if store == "absent":
        env = configured(env, "protocol.allow", "always")
    else:
        foreign_store(other, url, tmp_path)
        env = configured(env, "protocol.file.allow", "always")
    refusing_hook(holder, tmp_path)
    at, pin = on_main(holder, env), pinned(holder, env)
    module = family_module()
    monkeypatch.setattr(module, "_unrestorable", lambda *args: None)
    monkeypatch.delenv("GIT_ALLOW_PROTOCOL", raising=False)

    code = in_process(module, monkeypatch, env, [
        "remove", "--family-root", str(holder), "--member", MEMBER])
    out, err = capsys.readouterr()

    assert code == 2, out + err
    said = err.splitlines()[-1]
    assert (f"; NOT {PATH} checked out again at {at[:12]} on main from the "
            "object store `git rm` keeps: `git -c protocol.allow=never "
            "--literal-pathspecs submodule update --init --no-fetch -q -- "
            f"{PATH}`: ") in said, said
    if store == "absent":
        assert "transport 'file' not allowed" in said, said
    left = re.search(r"; NOT the holder's git config as it was: it holds "
                     r"`([^`]+)` and `([^`]+)`, which it did not\.", said)
    assert left and sorted(left.groups()) == [
        f"submodule.{RENAMED}.active", f"submodule.{RENAMED}.url"], said
    for key in left.groups():
        assert f"`git config --local --unset-all {key}`" in said, said
    assert not holds(other, pin, holder), "nothing was cloned or fetched"
    offline.assert_left_nothing()


def test_a_checkout_whose_git_dir_deinit_absorbed_is_put_back(
        family, holder, offline, tmp_path):
    """THE RECORDED STORE WAS WRONG THE OTHER WAY TOO. A member checked out
    with a `.git` DIRECTORY of its own (cloned into the mount by hand) and
    no store in the holder's git directory: `deinit` moves that `.git` into
    `.git/modules/<name>` before it empties the checkout, and the rollback
    called the store gone, because the one it had recorded was the
    directory `deinit` moved. git reuses the store it moved, and so does
    the rollback: nothing is cloned, the checkout is back on its branch, and
    the sentence says where git keeps its store now, since the member's
    `.git` is a file naming it and no longer the directory it was."""
    env = isolated(offline, tmp_path)
    mount = holder / PATH
    url = git("config", "-f", ".gitmodules", f"submodule.{PATH}.url",
              cwd=holder).stdout.strip()
    rmtree(mount)
    rmtree(holder / ".git" / "modules" / "members" / MEMBER)
    git(*FILE_PROTOCOL, "clone", "-q", url, str(mount), cwd=tmp_path)
    assert (mount / ".git").is_dir(), "premise: an embedded .git directory"
    embedded = Path(git("rev-parse", "--absolute-git-dir", cwd=mount
                        ).stdout.strip())
    refusing_hook(holder, tmp_path)
    at = on_main(holder, env)
    assert at == pinned(holder, env), "premise: the clone stands at the pin"
    before = snapshot(holder, env)

    result = remove(holder, env)

    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.splitlines()[-1] == remove_undone(at) + (
        f" {PATH} now has its object store at .git/modules/{PATH}, where git "
        f"keeps it, and no longer at {embedded.as_posix()}.")
    after = snapshot(holder, env)
    assert_same(before, after, ("index", ".gitmodules", "family.yaml",
                                "registration", "member HEAD",
                                "member branch", "status", "HEAD"))
    assert (mount / ".git").is_file()

    def but_its_git(tree: dict) -> dict:
        return {name: data for name, data in tree.items()
                if not name.startswith(f"{PATH}/.git")}

    assert but_its_git(after["work tree"]) == but_its_git(before["work tree"])


def test_a_leg_no_store_holds_is_left_out_not_cloned(
        family, holder, offline, tmp_path, monkeypatch, capsys):
    """THE SAME RULE FOR THE MEMBER'S LEGS, which `git submodule update`
    brings back by name inside the member. A leg whose store is gone by the
    time the rollback runs (taken away here as the manifest's rewrite fails,
    after the unmount) would be cloned, so it is not: the member and its
    other leg come back, and the sentence names the leg left out and says
    its checkout comes back only from its remote."""
    env = isolated(offline, tmp_path)
    mount = holder / PATH
    git(*FILE_PROTOCOL, "submodule", "update", "-q", "--init", cwd=mount)
    assert git("config", "-f", ".gitmodules", "submodule.spec.path",
               cwd=mount).stdout.strip() == "spec", "fixture drift"
    leg_store = Path(git("rev-parse", "--absolute-git-dir",
                         cwd=mount / "spec").stdout.strip())
    shown = git("rev-parse", "--git-path", "modules/spec",
                cwd=mount).stdout.strip()
    module = family_module()
    at = on_main(holder, env)

    def store_gone_then_full(path, text):
        rmtree(leg_store)
        raise OSError(28, "No space left on device", str(path))

    monkeypatch.setattr(module, "write_lf", store_gone_then_full)
    before = snapshot(holder, env)
    code = in_process(module, monkeypatch, env, [
        "remove", "--family-root", str(holder), "--member", MEMBER])
    out, err = capsys.readouterr()

    assert code == 2, out + err
    said, next_line = refusal(err)
    assert said == (
        "REFUSED family-manifest-unwritable: family.yaml could not be "
        f"rewritten without {MEMBER}'s row: No space left on device. The "
        f"unmount was undone only in part (the gitlink at {PATH} put back in "
        "the index as it was, .gitmodules restored byte for byte, "
        f"`submodule.{PATH}` restored in the holder's git config); NOT {PATH} "
        f"checked out again at {at[:12]} on main from the object store `git "
        f"rm` keeps, and code and spec in it: {PATH} is checked out again, "
        f"but not spec in it: git would check it out of {shown}, which is "
        "not there, and clone it there, so `git submodule update` was not "
        f"run for it. The checkout of {PATH}/spec comes back only from its "
        "remote, which this command never reaches. `git status` shows "
        "whether anything else is left, before running `remove` again.")
    assert next_line == ("Remediation: make family.yaml writable, and check "
                         "the disk has room, then run the same command "
                         "again.")
    assert_same(before, snapshot(holder, env),
                ("index", ".gitmodules", "family.yaml", "registration",
                 "member HEAD", "member branch", "HEAD"))
    assert (mount / "code" / ".git").exists()
    assert not (mount / "spec" / ".git").exists()
    assert not leg_store.exists(), "nothing was cloned"


# --- a member whose store is gone (review 365-5d56e75, SHOULD-1) ----------

def facts(root: Path, env: dict) -> dict:
    """What can be read of a holder whose member's store is gone, where
    `git status` itself fails: HEAD, the index, the two files and the
    holder's `submodule.*` keys."""
    return {
        "HEAD": raw(root, env, "rev-parse", "HEAD").stdout,
        "index": raw(root, env, "ls-files", "-s", "-z").stdout,
        ".gitmodules": (root / ".gitmodules").read_bytes(),
        "family.yaml": (root / "family.yaml").read_bytes(),
        "registration": sorted(
            line for line in raw(root, env, "config", "--local", "--list"
                                 ).stdout.decode("utf-8").splitlines()
            if line.startswith("submodule.")),
    }


def store_taken_away(root: Path) -> Path:
    """The member's object store deleted, its checkout and gitfile kept."""
    store = root / ".git" / "modules" / "members" / MEMBER
    rmtree(store)
    assert (root / PATH / ".git").is_file()
    return store


def test_a_member_whose_store_is_gone_is_removed_as_its_dry_run_says(
        holder, offline, tmp_path):
    """MAIN REMOVED SUCH A MEMBER; THE ROLLBACK'S SET-UP REFUSED IT. With
    the store gone, `git status` in the holder fails, and the rollback read
    the member with no guard before the first write, so `remove` was
    refused `git-failed` with a LEG's remediation while its dry run exited
    0. The read is guarded: the dry run previews exactly what it previews
    with the store there, and the real run removes the member in one
    commit, exit 0."""
    env = isolated(offline, tmp_path)
    with_store = remove(holder, env, "--dry-run")
    store_taken_away(holder)

    dry = remove(holder, env, "--dry-run")
    real = remove(holder, env)

    assert dry.returncode == with_store.returncode == 0, dry.stderr
    assert dry.stdout == with_store.stdout
    assert dry.stderr == with_store.stderr == ""
    assert real.returncode == 0, real.stdout + real.stderr
    assert re.fullmatch(rf"  removed {MEMBER} \([^)]*\) from {PATH}",
                        real.stdout.splitlines()[0]), real.stdout
    assert raw(holder, env, "rev-parse", "-q", "--verify", f"HEAD:{PATH}",
               check=False).returncode != 0
    assert PATH not in gitmodules_paths(holder)
    assert registered_keys(holder, env, PATH) == []
    assert [r["project"] for r in manifest(holder)["members"]] == [OTHER]
    assert raw(holder, env, "status", "--porcelain=v1", "-z").stdout == b""
    assert validate(holder).returncode == 0


def test_a_member_whose_store_is_gone_is_put_back_but_its_checkout(
        holder, offline, tmp_path):
    """The same member under a `pre-commit` hook that refuses: the index,
    `.gitmodules`, `family.yaml`, HEAD and the registration are put back.
    Its checkout is in no store git has, so it is not put back and nothing
    is cloned: the directory is made again, empty, and the sentence names
    the checkout it could not restore, with git's own reason, and says it
    comes back only from its remote."""
    env = isolated(offline, tmp_path)
    store = store_taken_away(holder)
    refusing_hook(holder, tmp_path)
    before = facts(holder, env)

    result = remove(holder, env)

    assert result.returncode == 2, result.stdout + result.stderr
    assert re.fullmatch(
        re.escape("The unmount was undone only in part (the gitlink at "
                  f"{PATH} put back in the index as it was, .gitmodules "
                  "restored byte for byte, family.yaml restored byte for "
                  "byte, "
                  f"`submodule.{PATH}` restored in the holder's git config); "
                  f"NOT {PATH} checked out again: git could not read its "
                  "checkout before this command (`git rev-parse "
                  "--absolute-git-dir`: fatal: ")
        + r"[^`]*"
        + re.escape("), so no object store here is known to hold it, and "
                    f"{PATH} was made again, empty. The checkout of {PATH} "
                    "comes back only from its remote, which this command "
                    "never reaches. `git status` shows whether anything else "
                    "is left, before running `remove` again."),
        result.stderr.splitlines()[-1]), result.stderr
    assert facts(holder, env) == before
    assert list((holder / PATH).iterdir()) == []
    assert not store.exists(), "nothing was cloned"
    offline.assert_left_nothing()


# --- what the rollback says when it cannot finish --------------------------

def test_a_remove_whose_unwind_meets_a_lock_lists_the_commands_left(
        family, holder, offline, tmp_path, monkeypatch, capsys):
    """A LOCK TAKEN AFTER THE PRE-CHECK — here as the manifest's rewrite
    fails, after `deinit` and `git rm` — refuses every index write of the
    unwind and nothing else. The sentence lists what WAS put back
    (`.gitmodules`'s bytes, the registration), what was NOT with git's own
    reason, the checkout as not tried for want of the gitlink and the
    section, and the commands that put the rest back. With the lock gone,
    those commands, typed exactly as printed and in that order, leave the
    holder as it was."""
    env = isolated(offline, tmp_path)
    module = family_module()
    lock = index_lock(holder)
    gitlink = pinned(holder, env)
    staged = raw(holder, env, "ls-files", "-s", "--", ".gitmodules"
                 ).stdout.decode("ascii").split()[1]
    at = on_main(holder, env)

    def locked_then_full(path, text):
        lock.write_bytes(b"")
        raise OSError(28, "No space left on device", str(path))

    monkeypatch.setattr(module, "write_lf", locked_then_full)
    before = snapshot(holder, env)
    try:
        code = in_process(module, monkeypatch, env, [
            "remove", "--family-root", str(holder), "--member", MEMBER])
    finally:
        if lock.exists():
            lock.unlink()
    out, err = capsys.readouterr()

    assert code == 2, out + err
    said, next_line = refusal(err)
    assert re.fullmatch(
        re.escape(
            "REFUSED family-manifest-unwritable: family.yaml could not be "
            f"rewritten without {MEMBER}'s row: No space left on device. The "
            "unmount was undone only in part (.gitmodules restored byte for "
            f"byte, `submodule.{PATH}` restored in the holder's git config); "
            f"NOT the gitlink at {PATH} put back in the index as it was: `git "
            f"update-index --force-remove -- {PATH}`: ") + INDEX_LOCKED
        + re.escape("; NOT the index entry of .gitmodules put back as it "
                    "was: `git update-index --force-remove -- .gitmodules`: ")
        + INDEX_LOCKED + re.escape(
            f"; NOT {PATH} checked out again at {at[:12]} on main from the "
            "object store `git rm` keeps: not tried, as it needs the gitlink "
            f"at {PATH} and .gitmodules back first. Put the rest back by "
            "hand, in the holder and in this order: `git update-index --add "
            f"--cacheinfo 160000,{gitlink},{PATH}`; `git update-index --add "
            f"--cacheinfo 100644,{staged},.gitmodules`; `git -c "
            "protocol.allow=never submodule update --init --no-fetch -- "
            f"{PATH}`; `git -C {PATH} checkout -q main --`. Then `git status` "
            "shows whether anything is left, before running `remove` "
            "again."), said), said
    assert next_line == ("Remediation: make family.yaml writable, and check "
                         "the disk has room, then run the same command "
                         "again.")

    assert len(typed_by_hand(holder, said)) == 4
    assert_same(before, snapshot(holder, env), REMOVE_PUT_BACK)


def test_a_bump_whose_unwind_meets_a_lock_lists_the_command_left(
        family, holder, offline, tmp_path, monkeypatch, capsys):
    """The same for `bump`: a lock taken once the gitlink is staged refuses
    the commit's own stage and then the unwind's one index write. The
    manifest and the member's checkout are put back; the gitlink's entry is
    named with git's reason and the one command that puts it back, which,
    typed as printed, leaves the holder as it was."""
    env = isolated(offline, tmp_path)
    module = family_module()
    lock = index_lock(holder)
    gitlink, at, target = pinned(holder, env), on_main(holder, env), \
        older(family)

    def locked_after_the_stage(root, paths):
        lock.write_bytes(b"")
        return False

    monkeypatch.setattr(module, "_nothing_to_record", locked_after_the_stage)
    before = snapshot(holder, env)
    try:
        code = in_process(module, monkeypatch, env, [
            "bump", "--family-root", str(holder), "--member", MEMBER,
            "--to", target])
    finally:
        if lock.exists():
            lock.unlink()
    out, err = capsys.readouterr()

    assert code == 2, out + err
    lines = err.splitlines()
    assert lines[:5] == loud(
        f"git --literal-pathspecs add -f -- {PATH} family.yaml", holder, 128)
    assert re.fullmatch(
        re.escape("The bump was undone only in part (family.yaml restored "
                  f"byte for byte, {PATH} back on main at {at[:12]}); NOT the "
                  f"gitlink at {PATH} put back in the index as it was: `git "
                  f"update-index --force-remove -- {PATH}`: ") + INDEX_LOCKED
        + re.escape(". Put the rest back by hand, in the holder and in this "
                    "order: `git update-index --add --cacheinfo "
                    f"160000,{gitlink},{PATH}`. Then `git status` shows "
                    "whether anything is left, before running `bump` "
                    "again."), lines[-1]), lines[-1]

    assert typed_by_hand(holder, lines[-1]) == [
        f"git update-index --add --cacheinfo 160000,{gitlink},{PATH}"]
    assert_same(before, snapshot(holder, env), BUMP_PUT_BACK)


# --- never over a landed commit, and not only on a refusal ----------------

@pytest.mark.parametrize("verb", ["bump", "remove"])
def test_a_failure_after_the_commit_landed_undoes_nothing(
        family, holder, offline, tmp_path, monkeypatch, capsys, verb):
    """NEVER OVER A COMMIT THAT LANDED. A failure after `git commit`
    succeeded must not unwind: the tree under a landed commit would
    contradict its own history. The commit stands, the holder is clean and
    valid, and the sentence says where to look."""
    env = isolated(offline, tmp_path)
    module = family_module()
    commit_one = module._commit_one

    def landed_then_failed(root, *args, **kwargs):
        commit_one(root, *args, **kwargs)
        raise module.Refusal("git-failed", "injected after the commit",
                             "Remediation: injected.")

    monkeypatch.setattr(module, "_commit_one", landed_then_failed)
    was = git("rev-parse", "HEAD", cwd=holder).stdout.strip()
    extra = ["--to", older(family)] if verb == "bump" else []
    code = in_process(module, monkeypatch, env, [
        verb, "--family-root", str(holder), "--member", MEMBER, *extra])
    out, err = capsys.readouterr()

    assert code == 2, out + err
    assert refusal(err) == (
        "REFUSED git-failed: injected after the commit. The commit had "
        "already landed, so nothing was undone: `git log -1` in the holder "
        "shows it.", "Remediation: injected.")
    assert git("rev-parse", "HEAD~1", cwd=holder).stdout.strip() == was
    assert git("status", "--porcelain", cwd=holder).stdout == ""
    assert validate(holder).returncode == 0


@pytest.mark.parametrize("verb", ["bump", "remove"])
def test_an_interrupt_after_the_first_write_is_put_back_and_raised(
        family, holder, offline, tmp_path, monkeypatch, capsys, verb):
    """NOT ONLY A REFUSAL OR A FAILED GIT COMMAND. Ctrl-C at the manifest's
    rewrite — after `bump`'s checkout, after `remove`'s unmount, and asked
    by neither one's checks before its first write — is put back, the
    sentence printed, and the interrupt goes on exactly as raised."""
    env = isolated(offline, tmp_path)
    module = family_module()
    raised = KeyboardInterrupt()

    def interrupted(*args):
        raise raised

    monkeypatch.setattr(module, "write_lf", interrupted)
    at = on_main(holder, env)
    before = snapshot(holder, env)
    extra = ["--to", older(family)] if verb == "bump" else []
    with pytest.raises(KeyboardInterrupt) as caught:
        in_process(module, monkeypatch, env, [
            verb, "--family-root", str(holder), "--member", MEMBER, *extra])
    assert caught.value is raised
    out, err = capsys.readouterr()

    assert out == ""
    assert err == (bump_undone(f"{PATH} back on main at {at[:12]}")
                   if verb == "bump" else
                   remove_undone(at).replace(
                       ".gitmodules restored byte for byte, family.yaml "
                       "restored byte for byte",
                       ".gitmodules restored byte for byte")) + "\n"
    assert_same(before, snapshot(holder, env),
                BUMP_PUT_BACK if verb == "bump" else REMOVE_PUT_BACK)
