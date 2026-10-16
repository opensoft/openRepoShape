# SPDX-License-Identifier: Apache-2.0
"""`family.py add --dry-run`, `bump --dry-run` and `remove --dry-run` print
what the real run would do and change nothing in the holder (#326).

`bump`, `add` and `remove` took no `--dry-run`, though the file's exit-code
paragraph said a dry run prints and exits 0 and `bump-leg.py` has one. The
only way to see what a bump would pin was to run it: fetch the member, check
it out at `--to`, rewrite `family.yaml`, stage. Even the `nothing to do`
answer #210 added cost the fetch and the checkout.

THE RULINGS THIS FILE HOLDS THE TWO VERBS TO. `bump --dry-run` makes every
refusal `bump` makes, the same refusal and exit 2; it fetches the member, as a
real bump does, and resolves `--to` and digests it there; it prints the row as
`old -> new` and the full row it would write, and the trailers; it exits 0, or
1 for `nothing to do`; and it never checks the member out, rewrites
`family.yaml`, stages or commits. `remove --dry-run` makes every refusal
`remove` makes and prints the row, the gitlink, the `.gitmodules` section by
name and the directory, and changes nothing. `add --dry-run`, the second part
of #326, makes every refusal `add` makes before its first write, the
member's own included; it reads the member as a real add does, from
throwaway clones in temporary directories outside the holder that are gone
afterwards, and prints the row, the gitlink, the `.gitmodules` section, the
registration, the directory and the trailers; it runs no `git submodule
add` and writes nothing of the holder's: no `.gitmodules`, `family.yaml`,
index, work tree, `.git/config` or `.git/modules`.

"CHANGES NOTHING" IS ASKED AS BYTES, the way `test_family_member_path.py` and
`test_family_add_refusals.py` ask it of a refusal: `git ls-files -s -z`, `git
status --porcelain=v1 -z`, `family.yaml`, `.gitmodules`, the holder's
`.git/config`, the member's HEAD and every byte of the work tree. Then the
REAL run goes, and writes exactly what the dry run printed: a preview that
says one thing and a run that does another is worse than none.

The same family, rules and offline environment as `test_family.py`: members
are scaffolded into local bare repositories, nothing is created on GitHub, a
`gh` on PATH logs and exits 97, and the operator's git configuration is a file
of the test's own. No test pushes to the fixture's own remotes.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from conftest import cloned_just_pushed, git, run_script
#: The trailer lines a lane's run lands, from the file that owns them.
from test_commit_trailers import TRAILERS, trailers_of
#: The family fixture, its names and the offline environment, imported from
#: the modules that own them rather than rebuilt: a holder made any other way
#: would test a different holder.
from test_family import (  # noqa: F401
    FAMILY, ORG, SPARE, family, family_module, manifest, nothing_to_do_line,
    pushed_from_the_mount, validate,
)
from test_family_add_excludes import empty_holder  # noqa: F401
#: The pinned project and the name its renamed copy is added under (#330).
from test_family_add_member_id import PINNED, RENAMED
from test_family_add_refusals import (  # noqa: F401
    GHOST, gitmodules_paths, gitmodules_with, holder, offline,
    one_commit_remote, refusal, sections, take_out_as_printed,
)
from test_family_member_path import (
    GLOB, MEMBER, OTHER, hand_edit, older, raw, recorded,
)
from test_family_member_path import isolated as member_path_env

#: GIT'S AUTOMATIC MAINTENANCE, OFF for every git this module starts, through
#: git's `GIT_CONFIG_COUNT` protocol and never a global file. A `git commit`
#: may start `git maintenance run --auto` in the background (a newer git on
#: the macOS runner does), and it took `.git/objects/maintenance.lock` while
#: a test snapshotted the holder and released it before the comparison: five
#: `objects changed` failures on PR #345's first macOS run, none of them the
#: tool's. With it off, no background job packs or locks objects mid-test.
NO_MAINTENANCE = {"GIT_CONFIG_COUNT": "3",
                  "GIT_CONFIG_KEY_0": "maintenance.auto",
                  "GIT_CONFIG_VALUE_0": "false",
                  "GIT_CONFIG_KEY_1": "gc.auto", "GIT_CONFIG_VALUE_1": "0",
                  "GIT_CONFIG_KEY_2": "gc.autoDetach",
                  "GIT_CONFIG_VALUE_2": "false"}


def isolated(offline, tmp_path: Path) -> dict:
    """`test_family_member_path.isolated`'s offline, identity-carrying
    environment, with git's automatic maintenance off (`NO_MAINTENANCE`)."""
    return {**member_path_env(offline, tmp_path), **NO_MAINTENANCE}


#: The header `bump --dry-run` prints above the row it would write.
ROW_HEADER = "row          as family.yaml would carry it:"

#: The order a test compares a holder's state in. The FIRST key that differs
#: is the one a failure names, so each verb leads with the fact its own first
#: write would change: the member's checkout for `bump`, the index for
#: `remove`.
BUMP_ORDER = ("member HEAD", "family.yaml", "index", "status", ".gitmodules",
              ".git/config", "work tree", "objects", "HEAD")
REMOVE_ORDER = ("index", ".gitmodules", "family.yaml", "work tree",
                ".git/config", "status", "member HEAD", "objects", "HEAD")


def work_tree(root: Path) -> dict:
    """Every directory and file under `root` but its own `.git/`, each file
    as its bytes (a symlink as its target): the holder's work tree, the
    members' checkouts included."""
    found: dict = {}
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        if here == root:
            dirnames[:] = [name for name in dirnames if name != ".git"]
        for name in dirnames:
            found[(here / name).relative_to(root).as_posix() + "/"] = None
        for name in filenames:
            target = here / name
            found[target.relative_to(root).as_posix()] = (
                os.readlink(target).encode("utf-8") if target.is_symlink()
                else target.read_bytes())
    return found


#: An OBJECT FILE under `.git/objects`: a loose object (two hex digits, then
#: the rest of a sha-1 or sha-256 id) or a pack and its index. Only these are
#: listed. A `*.lock`, `info/` and git's other transient files are not
#: objects, and a lock a background job held at the first snapshot and not
#: at the second failed five tests on PR #345's first macOS run.
OBJECT_FILE = re.compile(r"[0-9a-f]{2}/[0-9a-f]{38}(?:[0-9a-f]{24})?"
                         r"|pack/pack-[0-9a-f]+\.(?:pack|idx)")


def objects(root: Path) -> list[str]:
    """Every OBJECT FILE (`OBJECT_FILE`) in the holder's OWN object store,
    `.git/objects`. A blob written there is a write the index and the work
    tree do not show; the member's store, which `bump`'s fetch writes into,
    is under `.git/modules/` and not in this list."""
    store = root / ".git" / "objects"
    return sorted(name for name in (path.relative_to(store).as_posix()
                                    for path in store.rglob("*")
                                    if path.is_file())
                  if OBJECT_FILE.fullmatch(name))


def state(root: Path, env: dict, member: str = MEMBER) -> dict:
    """Everything a dry run must leave exactly as it found it, as bytes,
    `.gitmodules` None where the work tree has no file there."""
    mount = root / "members" / member
    gitmodules = root / ".gitmodules"
    return {
        "objects": objects(root),
        "HEAD": raw(root, env, "rev-parse", "HEAD").stdout,
        "index": raw(root, env, "ls-files", "-s", "-z").stdout,
        "status": raw(root, env, "status", "--porcelain=v1", "-z").stdout,
        "family.yaml": (root / "family.yaml").read_bytes(),
        ".gitmodules": (gitmodules.read_bytes() if gitmodules.is_file()
                        else None),
        ".git/config": (root / ".git" / "config").read_bytes(),
        "member HEAD": (raw(mount, env, "rev-parse", "HEAD").stdout
                        if mount.is_dir() else None),
        "work tree": work_tree(root),
    }


def assert_as_it_was(root: Path, env: dict, before: dict, order) -> None:
    """`root` is in the state `before` recorded, compared key by key in
    `order`, so a failure names the first fact that moved."""
    now = state(root, env)
    for key in order:
        assert now[key] == before[key], f"{key} changed"


def pinned_at(root: Path, env: dict, member: str = MEMBER) -> str:
    """The commit HEAD's gitlink records for `member`."""
    return raw(root, env, "rev-parse", f"HEAD:members/{member}"
               ).stdout.decode("ascii").strip()


def bump(root: Path, env: dict, to: str, *extra: str):
    return run_script(FAMILY, "bump", "--family-root", str(root), "--member",
                      MEMBER, "--to", to, *extra, env=env)


def remove(root: Path, env: dict, *extra: str):
    return run_script(FAMILY, "remove", "--family-root", str(root),
                      "--member", MEMBER, *extra, env=env)


def printed_row(stdout: str) -> list[str]:
    """The row `bump --dry-run` printed under `ROW_HEADER`, line by line, as
    `family.yaml` would carry it."""
    lines = stdout.splitlines()
    row = []
    for line in lines[lines.index(ROW_HEADER) + 1:]:
        if not line.startswith(("  - ", "    ")):
            break
        row.append(line)
    return row


def commit_in_mount(root: Path, env: dict, change, *,
                    push: bool = True) -> str:
    """A commit in `MEMBER`'s mount that `change(mount)` makes, and the mount
    put back at the commit the holder pins, with the holder clean. Returns
    its sha.

    PUSHED unless `push` is False (#613): `bump --to` refuses a commit no
    branch of the member's remote reaches, `member-to-local-only`, as
    `bump-leg.py` refuses its twin, so a commit a test bumps to goes first to
    a branch of the private remote `pushed_from_the_mount` points the mount
    at. With `push=False` it is in the member's objects and nowhere else,
    the state #613 refuses."""
    mount = root / "members" / MEMBER
    pinned = raw(mount, env, "rev-parse", "HEAD").stdout.decode().strip()
    change(mount)
    raw(mount, env, "add", "-A")
    raw(mount, env, "commit", "-q", "-m", "A commit only this mount has")
    made = raw(mount, env, "rev-parse", "HEAD").stdout.decode().strip()
    raw(mount, env, "checkout", "-q", pinned)
    if push:
        pushed_from_the_mount(mount, made)
    assert raw(root, env, "status", "--porcelain=v1", "-z").stdout == b"", (
        "premise: the holder is clean")
    return made


# --- bump --------------------------------------------------------------------

def test_bump_dry_run_prints_the_move_and_a_real_bump_writes_exactly_that(
        family, holder, offline, tmp_path):
    """THE RULING'S FIRST TEST. A real move, previewed: the `old -> new` line,
    the gitlink, the full row, and not one byte of the holder or the member's
    checkout moved; no `gh` call, and the scratch copy the manifest is read
    through is gone. Then the real bump writes exactly the row the dry run
    printed, digest and all, and the holder validates."""
    env = isolated(offline, tmp_path)
    target, pinned = older(family), pinned_at(holder, env)
    assert target != pinned, "premise: a bump with something to move"
    before = state(holder, env)

    dry = bump(holder, env, target, "--dry-run")

    # FIRST, WHATEVER IT PRINTED: nothing moved.
    assert_as_it_was(holder, env, before, BUMP_ORDER)
    offline.assert_left_nothing()
    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert dry.stderr == ""
    lines = dry.stdout.splitlines()
    assert lines[:2] == [
        f"member       {MEMBER}  {ORG}/{MEMBER} at members/{MEMBER}",
        f"commit       {pinned[:12]} -> {target[:12]}"]
    assert f"gitlink      members/{MEMBER} {pinned[:12]} -> {target[:12]}" \
        in lines
    row = printed_row(dry.stdout)
    assert row[0] == f"  - project: {MEMBER}"
    assert f'      commit: "{target}"' in row
    assert lines[-1].startswith("--dry-run: nothing was changed in the "
                                "holder. `git fetch` ran in members/")

    real = bump(holder, env, target)

    assert real.returncode == 0, real.stdout + real.stderr
    text = (holder / "family.yaml").read_bytes().decode("utf-8")
    assert "\n".join(row) + "\n" in text, "the row printed is the row written"
    written = {r["project"]: r for r in manifest(holder)["members"]}[MEMBER]
    digest = written["pin"]["tree_sha256"]
    assert written["pin"]["commit"] == target
    assert f'      tree_sha256: "{digest}"' in row
    assert f"({digest})" in lines[2], "the tree line carries the same digest"
    assert pinned_at(holder, env) == target
    assert validate(holder).returncode == 0


@pytest.mark.parametrize("extra", [
    (), ("--trailer", TRAILERS[0], "--trailer", TRAILERS[1])],
    ids=["plain", "with-trailers"])
def test_bump_dry_run_to_the_pinned_commit_is_nothing_to_do(
        holder, offline, tmp_path, extra):
    """`--to` the pinned commit: exit 1, the real run's own `nothing to do`
    sentence, no row and no trailers (a run that writes no commit has none
    to end), and nothing changed."""
    env = isolated(offline, tmp_path)
    pinned = pinned_at(holder, env)
    before = state(holder, env)

    result = bump(holder, env, pinned, "--dry-run", *extra)

    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stderr == ""
    assert nothing_to_do_line(MEMBER, pinned) in result.stdout
    assert ROW_HEADER not in result.stdout
    assert "trailers" not in result.stdout
    assert "--dry-run:" not in result.stdout
    assert_as_it_was(holder, env, before, BUMP_ORDER)


def hand_edit_digest(root: Path, env: dict) -> None:
    """`MEMBER`'s `tree_sha256` hand-edited and committed: the row names the
    pinned commit and its digest does not recompute."""
    row = {r["project"]: r for r in manifest(root)["members"]}[MEMBER]
    manifest_path = root / "family.yaml"
    manifest_path.write_bytes(manifest_path.read_bytes().replace(
        row["pin"]["tree_sha256"].encode("ascii"), b"b" * 64))
    raw(root, env, "add", "--", "family.yaml")
    raw(root, env, "commit", "-q", "-m", "Hand-edit a digest")


def move_the_gitlink_alone(root: Path, env: dict) -> None:
    """`MEMBER`'s gitlink moved and committed, its row left naming the
    pinned commit."""
    mount = root / "members" / MEMBER
    raw(mount, env, "commit", "-q", "--allow-empty", "-m", "Moved alone")
    raw(root, env, "add", "--", f"members/{MEMBER}")
    raw(root, env, "commit", "-q", "-m", "Move the gitlink and not the pin")


@pytest.mark.parametrize("break_it", [hand_edit_digest,
                                      move_the_gitlink_alone],
                         ids=["digest", "gitlink"])
def test_bump_dry_run_of_a_repair_to_the_pinned_commit_is_a_move(
        holder, offline, tmp_path, break_it):
    """THE REAL RUN'S `nothing to do` RULE (#210), NOT `--to` AGAINST THE ROW.
    `validate-family.py` names `bump --to <the pinned commit>` as the repair
    for a digest that does not recompute and for a gitlink that moved alone,
    and in both the row already names `--to`. The real bump commits the
    repair; its dry run says it would, exit 0 and the row, and the real run
    then agrees."""
    env = isolated(offline, tmp_path)
    pinned = {r["project"]: r for r in manifest(holder)["members"]
              }[MEMBER]["pin"]["commit"]
    break_it(holder, env)
    assert validate(holder).returncode == 1, "premise: the holder is red"
    before = state(holder, env)

    dry = bump(holder, env, pinned, "--dry-run")

    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert "nothing to do" not in dry.stdout
    row = printed_row(dry.stdout)
    assert_as_it_was(holder, env, before, BUMP_ORDER)

    real = bump(holder, env, pinned)

    assert real.returncode == 0, real.stdout + real.stderr
    assert "\n".join(row) + "\n" in (holder / "family.yaml").read_text(
        encoding="utf-8")
    assert validate(holder).returncode == 0


def test_bump_dry_run_prints_the_trailers_the_real_commit_ends_with(
        family, holder, offline, tmp_path):
    """`--trailer` with `--dry-run` prints the lines, in order, after the row
    and before the closing line, worded as `bump-leg.py --dry-run` words
    them; with none it says so. The real run then ends its commit with
    exactly those lines."""
    env = isolated(offline, tmp_path)
    target = older(family)
    trailers = ("--trailer", TRAILERS[0], "--trailer", TRAILERS[1])

    dry = bump(holder, env, target, "--dry-run", *trailers)
    plain = bump(holder, env, target, "--dry-run")

    assert dry.returncode == plain.returncode == 0, dry.stderr + plain.stderr
    lines = dry.stdout.splitlines()
    at = lines.index("trailers     2 to append, in order:")
    assert lines[at + 1:at + 3] == [f"  {TRAILERS[0]}", f"  {TRAILERS[1]}"]
    assert lines.index(ROW_HEADER) < at
    assert lines[-1].startswith("--dry-run: ")
    assert "trailers     none" in plain.stdout.splitlines()

    real = bump(holder, env, target, *trailers)

    assert real.returncode == 0, real.stdout + real.stderr
    assert trailers_of(holder) == list(TRAILERS)


def deinit_member(root: Path, env: dict) -> None:
    """`MEMBER`'s mount de-initialized: no checkout to resolve `--to` in."""
    raw(root, env, "submodule", "deinit", "-q", "-f", "--",
        f"members/{MEMBER}")


def hand_edit_path(root: Path, env: dict) -> None:
    """#315's `member-path`: `MEMBER`'s `path:` hand-edited to a glob."""
    hand_edit(root, MEMBER, GLOB)


def a_second_section(root: Path, env: dict) -> None:
    """#360: a section of another name giving `MEMBER`'s path, committed."""
    commit_sections(root, env, f'[submodule "ghost"]\n\tpath = '
                                f'members/{MEMBER}\n')


#: Each refusal `bump` or `remove` makes before its first write, and how a
#: test brings the holder to it: `(verb, --member, --to, set-up, code)`.
#: `None` for `bump`'s `--to` is the member's older commit, a real move.
REFUSALS = {
    "bump-unknown": ("bump", "Nope", "0" * 40, None, "member-unknown"),
    "bump-not-a-commit": ("bump", MEMBER, "v1.0.0", None,
                          "member-to-not-a-commit"),
    "bump-member-path": ("bump", MEMBER, None, hand_edit_path,
                         "member-path"),
    "bump-uninitialized": ("bump", MEMBER, None, deinit_member,
                           "member-uninitialized"),
    "remove-unknown": ("remove", "Nope", None, None, "member-unknown"),
    "remove-member-path": ("remove", MEMBER, None, hand_edit_path,
                           "member-path"),
    "remove-path-registered-twice": ("remove", MEMBER, None,
                                     a_second_section,
                                     "member-path-registered-twice"),
}


@pytest.mark.parametrize("verb, member, to, set_up, code",
                         REFUSALS.values(), ids=REFUSALS)
def test_a_refusal_is_the_same_refusal_under_dry_run(
        family, holder, offline, tmp_path, verb, member, to, set_up, code):
    """THE RULING: a refusal under `--dry-run` is the same refusal, exit 2.
    The real run and the dry run, over the same holder, print the same two
    lines on stderr and nothing on stdout, and leave the holder as it was —
    #315's `member-path` over a hand-edited `path:` among them, the edit
    still sitting uncommitted in the work tree."""
    env = isolated(offline, tmp_path)
    if set_up is not None:
        set_up(holder, env)
    args = [verb, "--family-root", str(holder), "--member", member]
    if verb == "bump":
        args += ["--to", to or older(family)]
    before = state(holder, env)

    real = run_script(FAMILY, *args, env=env)
    dry = run_script(FAMILY, *args, "--dry-run", env=env)

    assert dry.returncode == real.returncode == 2, dry.stdout + dry.stderr
    assert dry.stdout == real.stdout == ""
    assert dry.stderr == real.stderr
    assert refusal(dry.stderr)[0].startswith(f"REFUSED {code}: ")
    assert_as_it_was(holder, env, before,
                     BUMP_ORDER if verb == "bump" else REMOVE_ORDER)


def test_bump_dry_run_of_a_commit_the_member_does_not_have_exits_2(
        holder, offline, tmp_path):
    """A `--to` the member's objects do not hold after the fetch is exit 2
    from both runs, and neither prints a row. The dry run's resolve and the
    real run's checkout failed on it in git's words; both now refuse it
    `member-to-unknown`, in the same words, saying to push it first, as
    `test_family_bump_to_checks.py` holds it (#541)."""
    env = isolated(offline, tmp_path)
    missing = "deadbeef" * 5
    before = state(holder, env)

    dry = bump(holder, env, missing, "--dry-run")
    real = bump(holder, env, missing)

    assert dry.returncode == real.returncode == 2, dry.stdout + dry.stderr
    assert dry.stdout == real.stdout == ""
    assert dry.stderr == real.stderr
    assert refusal(dry.stderr)[0].startswith(
        f"REFUSED member-to-unknown: --to {missing} ")
    assert_as_it_was(holder, env, before, BUMP_ORDER)


def test_bump_dry_run_after_a_failed_fetch_says_what_it_resolved_from(
        family, holder, offline, tmp_path):
    """A fetch that fails is a note, as in the real run, and `--to` is then
    resolved from what the member's object store already holds; the closing
    line says THAT, not that the fetch is how `--to` was resolved."""
    env = isolated(offline, tmp_path)
    raw(holder / "members" / MEMBER, env, "remote", "set-url", "origin",
        str(tmp_path / "gone.git"))
    before = state(holder, env)

    dry = bump(holder, env, older(family), "--dry-run")

    assert_as_it_was(holder, env, before, BUMP_ORDER)
    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert dry.stderr.startswith(f"  note: could not fetch members/{MEMBER} "
                                 "from its origin")
    assert dry.stdout.splitlines()[-1] == (
        f"--dry-run: nothing was changed in the holder. The fetch of "
        f"members/{MEMBER} failed, as the note says, so --to was resolved and "
        "the digest above computed from what its object store already held, "
        "as a real bump would; the member's checkout, family.yaml, the index "
        "and the holder's commits are as they were.")
    assert "`git fetch` ran" not in dry.stdout


def test_bump_dry_run_reads_the_members_manifest_at_to_and_refuses_as_bump(
        holder, offline, tmp_path):
    """WHAT THE REAL RUN READS AFTER ITS CHECKOUT, ASKED OF THE OBJECTS. A
    `--to` whose tree has no `project.yaml` is `member-not-a-project` from
    both runs, word for word, and neither moves the member's checkout: the
    real run asks it of the same objects before its checkout (#365), where
    it used to refuse after it and leave the member at `--to`."""
    env = isolated(offline, tmp_path)
    target = commit_in_mount(
        holder, env, lambda mount: (mount / "project.yaml").unlink())
    before = state(holder, env)

    dry = bump(holder, env, target, "--dry-run")

    assert dry.returncode == 2, dry.stdout + dry.stderr
    assert dry.stdout == ""
    assert refusal(dry.stderr)[0].startswith("REFUSED member-not-a-project: ")
    assert_as_it_was(holder, env, before, BUMP_ORDER)
    real = bump(holder, env, target)
    assert real.returncode == 2
    assert real.stderr == dry.stderr
    assert_as_it_was(holder, env, before, BUMP_ORDER)


@pytest.mark.skipif(sys.platform == "win32",
                    reason="a symbolic link in a checkout needs privileges "
                           "on Windows that a runner does not grant")
def test_bump_dry_run_leaves_a_linked_manifest_to_the_real_run(
        holder, offline, tmp_path):
    """A `project.yaml` that is a SYMLINK at `--to` is only its link text in
    the objects, and a checkout reads through it. The dry run does not
    refuse it — the real run pins it — and says the `id:` it prints is the
    row's own; the real run then writes the row it printed."""
    env = isolated(offline, tmp_path)

    def link(mount: Path) -> None:
        (mount / "project.yaml").rename(mount / "manifest.yaml")
        (mount / "project.yaml").symlink_to("manifest.yaml")

    target = commit_in_mount(holder, env, link)

    dry = bump(holder, env, target, "--dry-run")

    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert any(line.startswith("note         project.yaml is a symbolic link")
               for line in dry.stdout.splitlines())
    row = printed_row(dry.stdout)
    assert "    id: irrs" in row
    real = bump(holder, env, target)
    assert real.returncode == 0, real.stdout + real.stderr
    assert "\n".join(row) + "\n" in (holder / "family.yaml").read_text(
        encoding="utf-8")


# --- remove ------------------------------------------------------------------

def test_remove_dry_run_prints_what_a_real_remove_takes_and_changes_nothing(
        holder, offline, tmp_path):
    """THE RULING'S REMOVE TEST. The row, the gitlink, the `.gitmodules`
    section by name and the directory, printed; the index, `.gitmodules`,
    `family.yaml`, the work tree and `.git/config` byte for byte as they
    were. Then the real remove takes out exactly those four and leaves the
    neighbour's row, gitlink, section and directory alone."""
    env = isolated(offline, tmp_path)
    gitlink = pinned_at(holder, env)
    before = state(holder, env)

    dry = remove(holder, env, "--dry-run")

    # FIRST, WHATEVER IT PRINTED: nothing moved.
    assert_as_it_was(holder, env, before, REMOVE_ORDER)
    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert dry.stderr == ""
    lines = dry.stdout.splitlines()
    assert lines[:4] == [
        f"row          {MEMBER}  {ORG}/{MEMBER}, pinned at {gitlink[:12]}, "
        "dropped from family.yaml",
        f"gitlink      members/{MEMBER}  {gitlink[:12]}",
        f'gitmodules   [submodule "members/{MEMBER}"]  path members/{MEMBER}, '
        "every section of that name",
        f'registration [submodule "members/{MEMBER}"] in the holder\'s '
        ".git/config, dropped by `git submodule deinit`",
    ]
    assert lines[4].startswith(f"directory    members/{MEMBER}  deleted with "
                               "everything in it")
    assert lines[-1].startswith("--dry-run: nothing was changed")
    assert registered_keys(holder, env, f"members/{MEMBER}"), (
        "premise: the registration the dry run named is there")

    real = remove(holder, env)

    assert real.returncode == 0, real.stdout + real.stderr
    assert [r["project"] for r in manifest(holder)["members"]] == [OTHER]
    assert raw(holder, env, "ls-files", "-s", "--", f"members/{MEMBER}"
               ).stdout == b""
    assert raw(holder, env, "ls-files", "-s", "--", f"members/{OTHER}"
               ).stdout.startswith(b"160000 ")
    assert sections((holder / ".gitmodules").read_text(encoding="utf-8")) \
        == [f"members/{OTHER}"]
    assert not (holder / "members" / MEMBER).exists()
    assert (holder / "members" / OTHER / "project.yaml").is_file()
    assert registered_keys(holder, env, f"members/{MEMBER}") == []
    assert registered_keys(holder, env, f"members/{OTHER}")
    assert validate(holder).returncode == 0


def test_remove_dry_run_of_a_member_the_index_does_not_hold_fails_as_remove(
        holder, offline, tmp_path):
    """A row whose gitlink is no longer in the index: the real `remove`'s
    first git call, `git submodule deinit`, fails on the path, loudly, exit
    2. The dry run fails where it fails, on git's same line, printed the
    same way, exit 2, and never with a remediation for a LEG
    (`validate-pins.py`, `contracts/<leg>-pin.yaml`) that a holder does not
    have. Nothing moves, from either."""
    env = isolated(offline, tmp_path)
    raw(holder, env, "rm", "-q", "--cached", "--", f"members/{MEMBER}")
    raw(holder, env, "commit", "-q", "-m", "Unstage the gitlink by hand")
    before = state(holder, env)

    dry = remove(holder, env, "--dry-run")

    assert_as_it_was(holder, env, before, REMOVE_ORDER)
    real = remove(holder, env)
    assert_as_it_was(holder, env, before, REMOVE_ORDER)
    assert dry.returncode == real.returncode == 2, dry.stdout + dry.stderr
    assert dry.stdout == real.stdout == ""
    assert dry.stderr.startswith(
        f"REFUSED listing members/{MEMBER} in the index, where a real remove "
        "unmounts it. THE EXACT COMMAND WAS:")
    assert real.stderr.startswith("REFUSED a git or gh command failed. THE "
                                  "EXACT COMMAND WAS:")
    for result in (dry, real):
        assert (f"error: pathspec 'members/{MEMBER}' did not match any "
                "file(s) known to git") in result.stderr
        assert "validate-pins" not in result.stderr
        assert "-pin.yaml" not in result.stderr


def registered_keys(root: Path, env: dict, name: str) -> list[str]:
    """The `submodule.<name>.*` lines of the holder's own git config, by
    section: the part of a key before its last dot."""
    listed = raw(root, env, "config", "--local", "--list").stdout.decode(
        "utf-8", "replace")
    return [line for line in listed.splitlines()
            if line.partition("=")[0].rpartition(".")[0]
            == f"submodule.{name}"]


#: Hand edits that give `members/<MEMBER>` to a section of ANOTHER name,
#: appended to `.gitmodules` and committed: `(text, the other name)`. Each is
#: a second submodule for the member's path, by any `path` line it has —
#: the last one, an earlier one it then moves away from, or a name git
#: ignores — and each is refused by `remove` and its dry run alike (#360),
#: because `git rm` takes out the sections of ONE name and the commit kept
#: the other.
GHOSTS = {
    "two-names": (
        f'[submodule "ghost"]\n\tpath = members/{MEMBER}\n', "ghost"),
    "last-path-wins": (
        '[submodule "ghost"]\n\tpath = members/ELSEWHERE\n'
        f'[submodule "ghost"]\n\tpath = members/{MEMBER}\n', "ghost"),
    "path-left-behind": (
        f'[submodule "ghost"]\n\tpath = members/{MEMBER}\n'
        '[submodule "ghost"]\n\tpath = members/ELSEWHERE\n', "ghost"),
    "suspicious-name": (
        f'[submodule "../ghost"]\n\tpath = members/{MEMBER}\n', "../ghost"),
}

#: Hand edits that give the path to the member's OWN name alone, in more
#: than one section: `(text, the name git rm then drops every section of, or
#: None for none, the names whose sections say that path and stay)`. Each is
#: what git 2.43 does, probed: the work-tree file is read with overwrite, so
#: a name keeps its LAST path, and a name moving away takes the old path out
#: of git's map. One name, so no refusal: the dry run says what git does.
ONE_NAME = {
    "own-name-comes-back": (
        f'[submodule "members/{MEMBER}"]\n\tpath = members/ELSEWHERE\n'
        f'[submodule "members/{MEMBER}"]\n\tpath = members/{MEMBER}\n',
        f"members/{MEMBER}", []),
    "own-name-moves-away": (
        f'[submodule "members/{MEMBER}"]\n\tpath = members/ELSEWHERE\n',
        None, [f"members/{MEMBER}"]),
}


def commit_sections(root: Path, env: dict, text: str) -> list[str]:
    """`text` appended to `.gitmodules` as BYTES and committed; returns the
    sections the file then names, in order."""
    with (root / ".gitmodules").open("ab") as gitmodules:
        gitmodules.write(text.encode("utf-8"))
    raw(root, env, "add", "--", ".gitmodules")
    raw(root, env, "commit", "-q", "-m", "A second section for one path")
    return sections((root / ".gitmodules").read_text(encoding="utf-8"))


def assert_dry_run_names_what_git_drops(root: Path, env: dict,
                                        listed: list[str],
                                        dropped: str | None,
                                        kept: list[str]) -> None:
    """The dry run names the name whose sections `git rm` drops (or that it
    drops none), the names it leaves that still say the path, and the
    registration `deinit` drops under the same name; then a REAL `remove`
    takes out exactly the sections of that name, and the registration it
    named, and nothing else: the dry run says what git will do, not what a
    reader of the file might expect."""
    before = state(root, env)
    dry = remove(root, env, "--dry-run")
    assert_as_it_was(root, env, before, REMOVE_ORDER)
    assert dry.returncode == 0, dry.stdout + dry.stderr
    lines = dry.stdout.splitlines()
    path = f"members/{MEMBER}"
    assert (f'gitmodules   [submodule "{dropped}"]  path {path}, every '
            "section of that name" if dropped else
            "gitmodules   none: git reads no section of .gitmodules in the "
            f"work tree as giving {path}, so none is removed") in lines
    left = [line for line in lines if line.startswith("             left ")]
    assert left == ([] if not kept else [
        "             left in place, though it gives the same path: "
        + ", ".join(f'[submodule "{name}"]' for name in kept)])
    named = [line for line in lines if line.startswith("registration ")]
    assert named == ([f'registration [submodule "{path}"] in the holder\'s '
                      ".git/config, dropped by `git submodule deinit`"]
                     if dropped == path else [])

    real = remove(root, env)

    assert real.returncode == 0, real.stdout + real.stderr
    assert sections((root / ".gitmodules").read_text(encoding="utf-8")) \
        == [name for name in listed if name != dropped]
    assert bool(registered_keys(root, env, path)) is (not named)


@pytest.mark.parametrize("text, other", GHOSTS.values(), ids=GHOSTS)
def test_remove_dry_run_names_the_sections_a_real_remove_drops(
        holder, offline, tmp_path, text, other):
    """A SECOND SUBMODULE FOR THE MEMBER'S PATH — a half-removed member, a
    hand edit — is refused by the dry run and the real run in the same
    words, with the holder byte for byte as it was (#360), naming the other
    section and printing its by-key removal. Run as printed, that removal
    leaves the member's own section, and then the dry run names it as the
    one `git rm` drops, and a real `remove` drops exactly that and leaves no
    section for the path."""
    env = isolated(offline, tmp_path)
    commit_sections(holder, env, text)
    before = state(holder, env)

    real = remove(holder, env)
    dry = remove(holder, env, "--dry-run")

    assert_as_it_was(holder, env, before, REMOVE_ORDER)
    assert dry.returncode == real.returncode == 2, dry.stdout + dry.stderr
    assert dry.stdout == real.stdout == ""
    assert dry.stderr == real.stderr
    said, remediation = refusal(real.stderr)
    assert said.startswith("REFUSED member-path-registered-twice: "), said
    assert f"`{other}` (no url)" in said
    assert take_out_as_printed(holder, remediation), remediation
    raw(holder, env, "commit", "-q", "-m", "Take the other section out")

    assert_dry_run_names_what_git_drops(
        holder, env, sections((holder / ".gitmodules").read_text(
            encoding="utf-8")), f"members/{MEMBER}", [])
    assert f"members/{MEMBER}" not in gitmodules_paths(holder)


@pytest.mark.parametrize("text, dropped, kept", ONE_NAME.values(),
                         ids=ONE_NAME)
def test_remove_dry_run_follows_git_through_one_names_sections(
        holder, offline, tmp_path, text, dropped, kept):
    """ONE NAME, MORE THAN ONE SECTION, NO REFUSAL: only one submodule says
    the path, so `remove` runs, and its dry run names what git's own reading
    of the file makes of it — the name's sections all dropped when its last
    `path` is the member's, none when it moved away."""
    env = isolated(offline, tmp_path)
    listed = commit_sections(holder, env, text)
    assert_dry_run_names_what_git_drops(holder, env, listed, dropped, kept)


# --- both --------------------------------------------------------------------

@pytest.mark.parametrize("verb", ["bump", "remove"])
def test_a_dry_run_asks_the_manifest_refusal_the_real_run_asks_first_too(
        family, holder, offline, tmp_path, verb):
    """`family-members-unrecognised` is asked by the real `bump` before its
    checkout and by the real `remove` before its unmount (#365; both used to
    ask it after, with the holder changed). The dry run asks it too, exit 2,
    before anything is written. The hand edit is the one
    `test_family_add_refusals.py` makes: a comment on the `members:` line,
    which YAML reads past and the line rewrite does not, left uncommitted.
    The real runs are held to the same holder in
    `test_family_bump_remove_rollback.py`."""
    env = isolated(offline, tmp_path)
    manifest_path = holder / "family.yaml"
    text = manifest_path.read_bytes().decode("utf-8")
    assert text.count("\nmembers:\n") == 1, "fixture drift"
    manifest_path.write_bytes(text.replace(
        "\nmembers:\n", "\nmembers:  # edited by hand\n").encode("utf-8"))
    before = state(holder, env)
    extra = ["--to", older(family)] if verb == "bump" else []

    dry = run_script(FAMILY, verb, "--family-root", str(holder), "--member",
                     MEMBER, *extra, "--dry-run", env=env)

    assert dry.returncode == 2, dry.stdout + dry.stderr
    assert "REFUSED family-members-unrecognised: " in dry.stderr
    assert_as_it_was(holder, env, before,
                     BUMP_ORDER if verb == "bump" else REMOVE_ORDER)


#: Git commands that write: to the index, a work tree, a ref, the object
#: store or the history. A dry run runs none of them. `hash-object` and
#: `config` are here only when they would write (`-w`, or anything but a
#: listing); `bump --dry-run` asks `hash-object` for a blob id, with no `-w`.
WRITERS = {"add", "checkout", "commit", "merge", "mv", "pull", "push",
           "reset", "restore", "rm", "stash", "submodule", "switch",
           "update-index", "update-ref", "write-tree"}


def writes(argv: list[str]) -> bool:
    """Whether the git command `argv` writes, by `WRITERS` and the two
    commands that write only when told to."""
    sub = subcommand_of(argv)
    if sub == "hash-object":
        return "-w" in argv
    if sub == "config":
        return "--list" not in argv
    return sub in WRITERS


def subcommand_of(argv: list[str]) -> str:
    """The git subcommand in `argv`, past git's own options."""
    words = iter(argv[1:])
    for word in words:
        if word in ("-c", "-C"):
            next(words)
        elif not word.startswith("-"):
            return word
    raise AssertionError(f"no subcommand in {argv}")


@pytest.mark.parametrize("verb, to, code", [
    ("bump", "older", 0), ("bump", "pinned", 1), ("remove", None, 0)],
    ids=["bump-move", "bump-nothing", "remove"])
def test_a_dry_run_runs_no_git_command_that_writes(
        family, holder, offline, tmp_path, monkeypatch, verb, to, code):
    """"Changes nothing" is what the holder shows; this is the other half,
    that nothing which writes is RUN. Every program the dry run starts is
    recorded, in this process: no checkout, no stage, no commit, no `git
    submodule`, a `git config` only to list and a `git hash-object` with no
    `-w`, which `nothing to do` is the run that asks. `bump`'s does fetch,
    as the help and the docstring say it does, and `remove`'s does not."""
    module = family_module()
    args = [verb, "--family-root", str(holder), "--member", MEMBER]
    if to is not None:
        args += ["--to", older(family) if to == "older" else
                 git("rev-parse", f"HEAD:members/{MEMBER}",
                     cwd=holder).stdout.strip()]
    for key, value in isolated(offline, tmp_path).items():
        monkeypatch.setenv(key, value)
    calls = recorded(monkeypatch)

    assert module.main([*args, "--dry-run"]) == code

    gits = [argv for argv in calls if Path(argv[0]).name == "git"]
    assert gits, "premise: the calls were recorded"
    assert [argv for argv in gits if writes(argv)] == []
    ran = {subcommand_of(argv) for argv in gits}
    assert ("fetch" in ran) is (verb == "bump")
    assert ("hash-object" in ran) is (to == "pinned"), (
        "premise: `nothing to do` is asked of `hash-object`, and only then")


# --- add ---------------------------------------------------------------------

#: The mount path of the member every `add` here adds: the spare, which the
#: family has scaffolded and not added.
SPARE_PATH = f"members/{SPARE}"

#: The order an `add --dry-run` test compares a holder's state in: the
#: facts `git submodule add`, the real run's first write, changes first.
ADD_ORDER = ("index", ".gitmodules", ".git/modules", ".git/config",
             "family.yaml", "status", "work tree", "objects", "HEAD")


def add_state(root: Path, env: dict) -> dict:
    """Everything `add --dry-run` must leave as it found it, as bytes: what
    `state` reads but a member's HEAD, with a file that is not there as
    None (absent stays absent), HEAD read as a holder with no commit reads
    it, and the holder's `.git/modules` listed two deep, which is where a
    mount keeps its object store. In a holder that is a linked worktree,
    `.git` is a file and the three read from inside it are None."""
    def read(name: str) -> bytes | None:
        target = root / name
        return target.read_bytes() if target.is_file() else None

    modules = root / ".git" / "modules"
    return {
        "objects": objects(root) if (root / ".git").is_dir() else None,
        "HEAD": raw(root, env, "rev-parse", "-q", "--verify", "HEAD",
                    check=False).stdout,
        "index": raw(root, env, "ls-files", "-s", "-z").stdout,
        "status": raw(root, env, "status", "--porcelain=v1", "-z").stdout,
        "family.yaml": read("family.yaml"),
        ".gitmodules": read(".gitmodules"),
        ".git/config": read(".git/config"),
        ".git/modules": (sorted(path.relative_to(modules).as_posix()
                                for depth in ("*", "*/*")
                                for path in modules.glob(depth))
                         if modules.is_dir() else None),
        "work tree": work_tree(root),
    }


def assert_add_as_it_was(root: Path, env: dict, before: dict) -> None:
    """`root` is in the state `before` recorded, compared in `ADD_ORDER`,
    so a failure names the first fact that moved."""
    now = add_state(root, env)
    for key in ADD_ORDER:
        assert now[key] == before[key], f"{key} changed"


def add(root: Path, env: dict, remotes: Path, *extra: str,
        member: str = f"{ORG}/{SPARE}"):
    return run_script(FAMILY, "add", "--family-root", str(root), "--member",
                      member, "--local-remote-dir", str(remotes), *extra,
                      env=env)


def field(lines: list[str], label: str) -> str:
    """The one line of a dry run's output that `label` starts, without the
    label and the padding that lines every value up at column 13."""
    found = [line[13:] for line in lines if line.startswith(f"{label:<13}")]
    assert len(found) == 1, (label, lines)
    return found[0]


def tip_of(family, project: str = SPARE) -> str:
    return git("rev-parse", "main",
               cwd=family["remotes"] / f"{project}.git").stdout.strip()


def gitmodules_value(root: Path, env: dict, key: str) -> str:
    """`submodule.<SPARE_PATH>.<key>` as git reads the holder's
    `.gitmodules`."""
    return raw(root, env, "config", "-f", ".gitmodules", "--get",
               f"submodule.{SPARE_PATH}.{key}").stdout.decode("utf-8").strip()


@pytest.mark.parametrize("which", ["holder", "empty_holder"],
                         ids=["two-members", "first-member"])
def test_add_dry_run_prints_what_a_real_add_writes_and_changes_nothing(
        family, offline, tmp_path, request, which):
    """THE RULING'S FIRST TEST, for `add`. A real add previewed: the row,
    the gitlink, the `.gitmodules` section (in a new file for a family's
    first member) and the rest of what the mount makes, and not one byte of
    the holder moved: HEAD, the index, `git status`, `family.yaml`,
    `.gitmodules` (absent stays absent), `.git/config`, the `.git/modules`
    listing, the work tree and the holder's own objects. No `gh` call, and
    no temporary clone left behind. Then the real add writes exactly the
    row, the section and the gitlink the dry run printed, and the holder
    validates."""
    root = request.getfixturevalue(which)
    env = isolated(offline, tmp_path)
    first = which == "empty_holder"
    assert (root / ".gitmodules").exists() is not first, "premise"
    assert registered_keys(root, env, SPARE_PATH) == [], "premise"
    tip = tip_of(family)
    before = add_state(root, env)

    dry = add(root, env, family["remotes"], "--dry-run")

    # FIRST, WHATEVER IT PRINTED: nothing moved, and nothing was left.
    assert_add_as_it_was(root, env, before)
    offline.assert_left_nothing()
    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert dry.stderr == ""
    lines = dry.stdout.splitlines()
    assert lines[:3] == [
        f"checking {ORG}/{SPARE} before mounting it",
        f"member       {SPARE}  {ORG}/{SPARE} at {SPARE_PATH}",
        f"commit       none -> {tip[:12]}"]
    assert field(lines, "gitlink") == f"{SPARE_PATH} none -> {tip[:12]}"
    section = re.fullmatch(
        rf'\[submodule "{SPARE_PATH}"\]  path {SPARE_PATH}, url (.+?)'
        r"(, in a new \.gitmodules)?", field(lines, "gitmodules"))
    assert section, field(lines, "gitmodules")
    assert bool(section.group(2)) is first
    assert field(lines, "registration") == (
        f'[submodule "{SPARE_PATH}"] in the holder\'s .git/config, written '
        "by `git submodule add`")
    assert field(lines, "directory") == (
        f"{SPARE_PATH}  the member checked out at {tip[:12]}; its object "
        f"store at .git/modules/{SPARE_PATH}")
    row = printed_row(dry.stdout)
    assert row[0] == f"  - project: {SPARE}"
    assert f'      commit: "{tip}"' in row
    assert "trailers     none" in lines
    assert lines[-1] == (
        f"--dry-run: nothing was changed in the holder. {ORG}/{SPARE} was "
        "read from throwaway clones in temporary directories outside the "
        "holder, now deleted; .gitmodules, family.yaml, the index, the work "
        "tree and the holder's git directory are as they were.")
    was = sections(before[".gitmodules"].decode("utf-8")) if not first else []

    real = add(root, env, family["remotes"])

    assert real.returncode == 0, real.stdout + real.stderr
    text = (root / "family.yaml").read_text(encoding="utf-8")
    assert "\n".join(row) + "\n" in text, "the row printed is the row written"
    written = {r["project"]: r for r in manifest(root)["members"]}[SPARE]
    assert f"({written['pin']['tree_sha256']})" in lines[3], (
        "the tree line carries the digest written")
    assert pinned_at(root, env, SPARE) == tip
    now = sections((root / ".gitmodules").read_text(encoding="utf-8"))
    assert [name for name in now if name not in was] == [SPARE_PATH]
    assert gitmodules_value(root, env, "path") == SPARE_PATH
    assert gitmodules_value(root, env, "url") == section.group(1)
    assert registered_keys(root, env, SPARE_PATH)
    assert (root / SPARE_PATH / "project.yaml").is_file()
    assert (root / ".git" / "modules" / SPARE_PATH).is_dir()
    assert trailers_of(root) == [], "no --trailer, no trailer"
    assert validate(root).returncode == 0
    offline.assert_left_nothing()


def something_at_the_mount_path(root: Path) -> None:
    """A directory at the mount path that no row names: a half-finished
    add, or a hand's."""
    (root / SPARE_PATH).mkdir(parents=True)
    (root / SPARE_PATH / "README").write_bytes(b"left here by hand\n")


def a_section_under_another_name(root: Path) -> None:
    """#300's ghost: a section named `ghost` giving the mount path, in the
    work tree only, a hand edit nobody staged."""
    gitmodules_with(root, GHOST, "the work tree only")


def the_mount_paths_name_given_to_another_path(root: Path) -> None:
    """A section NAMED the mount path that gives another path (#242)."""
    with (root / ".gitmodules").open("ab") as gitmodules:
        gitmodules.write(f'[submodule "{SPARE_PATH}"]\n\tpath = '
                         "members/ELSEWHERE\n\turl = /nowhere/else.git\n"
                         .encode("utf-8"))


def a_cached_store(root: Path) -> None:
    """The object store a removed member leaves under `.git/modules`."""
    (root / ".git" / "modules" / SPARE_PATH).mkdir(parents=True)


def a_members_line_edited_by_hand(root: Path) -> None:
    """A comment on the `members:` line, which YAML reads past and the line
    rewrite does not, left uncommitted."""
    manifest_path = root / "family.yaml"
    text = manifest_path.read_bytes().decode("utf-8")
    assert text.count("\nmembers:\n") == 1, "fixture drift"
    manifest_path.write_bytes(text.replace(
        "\nmembers:\n", "\nmembers:  # edited by hand\n").encode("utf-8"))


def a_renamed_copy_of_a_member(root: Path) -> Path:
    """#330's case: a bare copy of the pinned `IRRS` under a name no row has,
    `IRRS2`, so `holding` passes it and its `project.yaml` still records the
    id `irrs` the row `IRRS` pins. It is a copy of the remote the holder's
    own `.gitmodules` names, as a repository renamed at the forge is to
    anybody who clones it by the new name, and it is made BESIDE the holder,
    never in the family's remotes, which every test of the module shares.
    Returns the directory of remotes the add is to read the member from."""
    source = git("config", "-f", ".gitmodules", "--get",
                 f"submodule.members/{PINNED}.url", cwd=root).stdout.strip()
    remotes = root.parent / "renamed-remotes"
    remotes.mkdir()
    cloned_just_pushed(Path(source), remotes / f"{RENAMED}.git", bare=True)
    return remotes


#: Each refusal `add` makes before its first write that a fixture provokes
#: cheaply, in `add`'s own order, as `(--member, more arguments, set-up,
#: what stderr starts with)`: the holder's own refusals first, then the
#: member's, which need the probe's throwaway clone, and last the member's
#: `id:` against the rows (#330), which needs what that clone read. A
#: set-up that needs the member read from somewhere other than the family's
#: remotes returns that directory of remotes; the others return None.
ADD_REFUSALS = {
    "malformed": (SPARE, (), None, "REFUSED member-malformed: "),
    "malformed-dot": (f"{ORG}/..", (), None, "REFUSED member-malformed: "),
    # #399's rule: a name that BEGINS with `.`, `_` or `-` is refused by the
    # pattern, in its general sentence, in either position. (An owner that
    # begins with `-` cannot be said as `--member <owner>/<project>`:
    # argparse reads it as an option, so that spelling is the real run's
    # test in `test_family_member_name.py`.)
    "malformed-project-underscore": (f"{ORG}/_{SPARE}", (), None,
                                     "REFUSED member-malformed: "),
    "malformed-project-hyphen": (f"{ORG}/-{SPARE}", (), None,
                                 "REFUSED member-malformed: "),
    "malformed-project-dot": (f"{ORG}/.{SPARE}", (), None,
                              "REFUSED member-malformed: "),
    "malformed-owner-underscore": (f"_{ORG}/{SPARE}", (), None,
                                   "REFUSED member-malformed: "),
    "malformed-owner-dot": (f".{ORG}/{SPARE}", (), None,
                            "REFUSED member-malformed: "),
    "duplicate-row": (f"{ORG}/{MEMBER}", (), None,
                      "REFUSED member-already-present: "),
    "duplicate-row-in-another-case": (
        f"{ORG.lower()}/{MEMBER.lower()}", (), None,
        "REFUSED member-already-present: "),
    "path-taken": (f"{ORG}/{SPARE}", (), something_at_the_mount_path,
                   "REFUSED member-path-taken: "),
    "name-taken": (f"{ORG}/{SPARE}", (),
                   the_mount_paths_name_given_to_another_path,
                   "REFUSED member-name-taken: "),
    "path-registered": (f"{ORG}/{SPARE}", (), a_section_under_another_name,
                        "REFUSED member-path-registered: "),
    "git-dir-cached": (f"{ORG}/{SPARE}", (), a_cached_store,
                       "REFUSED member-git-dir-cached: "),
    "members-unrecognised": (f"{ORG}/{SPARE}", (),
                             a_members_line_edited_by_hand,
                             "REFUSED family-members-unrecognised: "),
    "at-not-a-commit": (f"{ORG}/{SPARE}", ("--at", "abc1234"), None,
                        "REFUSED member-at-not-a-commit: "),
    "at-unknown": (f"{ORG}/{SPARE}", ("--at", "0" * 40), None,
                   "REFUSED member-at-unknown: "),
    "a-leg": (f"{ORG}/{MEMBER}-spec", (), None,
              "REFUSED member-not-a-project: "),
    "unreadable": (f"{ORG}/IRNOPE", (), None,
                   f"REFUSED reading {ORG}/IRNOPE. THE EXACT COMMAND WAS:"),
    "duplicate-id": (f"{ORG}/{RENAMED}", (), a_renamed_copy_of_a_member,
                     "REFUSED member-duplicate-id: "),
}


def scratch_free(text: str) -> str:
    """`text` with the random part of a throwaway clone's directory name
    taken out: the one thing two runs over the same holder print
    differently, in the exact command of a clone that failed."""
    return re.sub(r"openreposhape-member-[^/\\\s]+", "openreposhape-member-*",
                  text)


@pytest.mark.parametrize("member, extra, set_up, said",
                         ADD_REFUSALS.values(), ids=ADD_REFUSALS)
def test_a_refusal_add_makes_before_it_mounts_is_the_same_under_dry_run(
        family, holder, offline, tmp_path, member, extra, set_up, said):
    """THE RULING: every refusal `add` makes before its first write is the
    same refusal under `--dry-run`, the same code and exit 2, whether it is
    the holder's (asked before the member is read) or the member's (asked
    of the probe's throwaway clone). The real run and the dry run, over the
    same holder, print the same stdout and the same stderr, and leave the
    holder as it was, every hand edit a set-up made still in place, and no
    temporary clone behind."""
    env = isolated(offline, tmp_path)
    remotes = family["remotes"]
    if set_up is not None:
        remotes = set_up(holder) or remotes
    before = add_state(holder, env)

    real = add(holder, env, remotes, *extra, member=member)
    dry = add(holder, env, remotes, *extra, "--dry-run", member=member)

    assert dry.returncode == real.returncode == 2, dry.stdout + dry.stderr
    assert dry.stdout == real.stdout
    assert scratch_free(dry.stderr) == scratch_free(real.stderr)
    assert dry.stderr.startswith(said), dry.stderr
    assert_add_as_it_was(holder, env, before)
    offline.assert_left_nothing()


def test_add_dry_run_prints_the_trailers_the_real_commit_ends_with(
        family, holder, offline, tmp_path):
    """`--trailer` with `--dry-run` prints the lines, in order, after the row
    and before the closing line, worded as `bump --dry-run` words them. The
    real add then ends its one commit with exactly those lines. `add` takes
    the same repeatable `--trailer` as `bump` (#326)."""
    env = isolated(offline, tmp_path)
    trailers = ("--trailer", TRAILERS[0], "--trailer", TRAILERS[1])

    dry = add(holder, env, family["remotes"], "--dry-run", *trailers)

    assert dry.returncode == 0, dry.stdout + dry.stderr
    lines = dry.stdout.splitlines()
    at = lines.index("trailers     2 to append, in order:")
    assert lines[at + 1:at + 3] == [f"  {TRAILERS[0]}", f"  {TRAILERS[1]}"]
    assert lines.index(ROW_HEADER) < at
    assert lines[-1].startswith("--dry-run: ")

    real = add(holder, env, family["remotes"], *trailers)

    assert real.returncode == 0, real.stdout + real.stderr
    assert trailers_of(holder) == list(TRAILERS)


def test_add_dry_run_with_at_previews_that_commit(family, holder, offline,
                                                   tmp_path):
    """`--at` an older commit: the dry run previews THAT commit and has no
    `without --at` note, and the real add pins the commit printed."""
    env = isolated(offline, tmp_path)
    older_spare = git("rev-parse", "main~1",
                      cwd=family["remotes"] / f"{SPARE}.git").stdout.strip()
    assert older_spare != tip_of(family), "premise"

    dry = add(holder, env, family["remotes"], "--at", older_spare,
              "--dry-run")
    plain = add(holder, env, family["remotes"], "--dry-run")

    assert dry.returncode == plain.returncode == 0, dry.stderr + plain.stderr
    lines = dry.stdout.splitlines()
    assert field(lines, "commit") == f"none -> {older_spare[:12]}"
    assert f'      commit: "{older_spare}"' in printed_row(dry.stdout)
    assert not any(line.startswith("note         without --at")
                   for line in lines)
    assert field(plain.stdout.splitlines(), "note") == (
        "without --at a real add pins the tip it finds when it mounts, "
        f"which is {tip_of(family)[:12]} unless {ORG}/{SPARE} moves on "
        f"first; --at {tip_of(family)} pins this one")

    real = add(holder, env, family["remotes"], "--at", older_spare)

    assert real.returncode == 0, real.stdout + real.stderr
    assert pinned_at(holder, env, SPARE) == older_spare
    assert "\n".join(printed_row(dry.stdout)) + "\n" in (
        holder / "family.yaml").read_text(encoding="utf-8")


def test_add_dry_run_names_a_registration_the_mount_rewrites(
        family, holder, offline, tmp_path):
    """A `submodule.members/<P>` registration the holder already has, from
    a member removed by hand: `git submodule add` rewrites its url, and the
    dry run says so rather than that it writes one. The real add leaves the
    url the dry run printed."""
    env = isolated(offline, tmp_path)
    raw(holder, env, "config", "--local", f"submodule.{SPARE_PATH}.url",
        "/where/it/used/to/live.git")
    before = add_state(holder, env)

    dry = add(holder, env, family["remotes"], "--dry-run")

    assert_add_as_it_was(holder, env, before)
    assert dry.returncode == 0, dry.stdout + dry.stderr
    lines = dry.stdout.splitlines()
    assert field(lines, "registration") == (
        f'[submodule "{SPARE_PATH}"] in the holder\'s .git/config, its url '
        "rewritten by `git submodule add`")
    url = field(lines, "gitmodules").rpartition(", url ")[2]

    real = add(holder, env, family["remotes"])

    assert real.returncode == 0, real.stdout + real.stderr
    assert raw(holder, env, "config", "--local", "--get",
               f"submodule.{SPARE_PATH}.url").stdout.decode(
                   "utf-8").strip() == url


@pytest.mark.parametrize("taken_out, held_in", [
    ("from the work tree", "the index and HEAD"),
    ("from the work tree and the index", "HEAD")],
    ids=["unstaged-deletion", "staged-deletion"])
def test_add_dry_run_names_the_refusal_git_makes_at_the_mount(
        family, holder, offline, tmp_path, taken_out, held_in):
    """GIT'S OWN REFUSAL, NAMED AND NOT MADE. With no `.gitmodules` in the
    work tree and one in the index or HEAD, `git submodule add` refuses to
    write the file, before it writes anything, and the real add exits 2
    there with the holder unchanged. Only git can say that sentence, so the
    dry run says in a note what will happen and how to put the file back,
    and exits 0, never claiming a new `.gitmodules`."""
    env = isolated(offline, tmp_path)
    if taken_out == "from the work tree":
        (holder / ".gitmodules").unlink()
    else:
        raw(holder, env, "rm", "-q", "--", ".gitmodules")
    before = add_state(holder, env)

    dry = add(holder, env, family["remotes"], "--dry-run")

    assert_add_as_it_was(holder, env, before)
    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert ", in a new .gitmodules" not in dry.stdout
    assert (f"note         .gitmodules is in {held_in} but not in the work "
            "tree, where `git submodule add` refuses to write it: the real "
            "run exits 2 at its mount with the holder unchanged. Put back "
            "the copy git read first: `git checkout -- .gitmodules` (the "
            "index's), or `git checkout HEAD -- .gitmodules`"
            ) in dry.stdout.splitlines()

    real = add(holder, env, family["remotes"])

    assert real.returncode == 2, real.stdout + real.stderr
    assert ("fatal: please make sure that the .gitmodules file is in the "
            "working tree") in real.stderr
    assert_add_as_it_was(holder, env, before)
    offline.assert_left_nothing()


@pytest.mark.skipif(sys.platform == "win32",
                    reason="a tracked symlink is a plain file in a Windows "
                           "checkout, which the real add refuses")
def test_add_dry_run_leaves_a_linked_manifest_to_the_real_run(
        holder, offline, tmp_path):
    """A `project.yaml` that is a SYMLINK is only its link text in the
    member's objects, and the real add's mount reads through it. The dry
    run does not refuse it, since the real run pins it; it says the `id:`
    is the real run's to read and prints no guess. The real add then writes
    the printed row with the id the link leads to. (The link is built in
    the member's INDEX, not on a disk.)"""
    env = isolated(offline, tmp_path)
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
    git("commit", "-qm", "A linked manifest", cwd=work)
    git("clone", "-q", "--bare", str(work), str(remotes / "IRLN.git"),
        cwd=tmp_path)
    tip = git("rev-parse", "HEAD", cwd=remotes / "IRLN.git").stdout.strip()
    before = add_state(holder, env)

    dry = add(holder, env, remotes, "--dry-run", member=f"{ORG}/IRLN")

    assert_add_as_it_was(holder, env, before)
    assert dry.returncode == 0, dry.stdout + dry.stderr
    lines = dry.stdout.splitlines()
    assert (f"note         project.yaml is a symbolic link at {tip[:12]}, "
            "which only a checkout reads through: the real run reads the "
            "`id:` through the link, and the row below leaves it to that run"
            ) in lines
    row = printed_row(dry.stdout)
    assert row[1] == "    id: (read through the link by the real run)"

    real = add(holder, env, remotes, member=f"{ORG}/IRLN")

    assert real.returncode == 0, real.stdout + real.stderr
    text = (holder / "family.yaml").read_text(encoding="utf-8")
    assert "\n".join([row[0], "    id: irln", *row[2:]]) + "\n" in text
    offline.assert_left_nothing()


def test_add_dry_run_reads_the_member_outside_the_holder_and_writes_nothing(
        family, holder, offline, tmp_path, monkeypatch):
    """IN PROCESS, every program the dry run starts recorded. The member is
    read from two bare clones, the probe's and the dry run's own, each in a
    directory under the run's TEMP and none in the holder; and the holder's
    `git status`, asked while the dry run's own clone is still there, at the
    moment its digest is computed, is the status before the run: a clone
    made inside the holder would show in it, even one deleted afterwards. No
    git command run in the holder writes, `git add --dry-run`, the real
    run's own check of the mount path, aside; none runs `git submodule`."""
    module = family_module()
    env = isolated(offline, tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(tempfile, "tempdir", str(offline.temp))
    before = add_state(holder, env)
    real_run, real_digest = subprocess.run, module.tree_digest
    calls: list[tuple[list[str], object]] = []
    digested: list[tuple[Path, bytes]] = []

    def record(argv, *rest, **named):
        calls.append((list(argv), named.get("cwd")))
        return real_run(argv, *rest, **named)

    def digest(repo, rev):
        status = real_run(["git", "status", "--porcelain=v1", "-z"],
                          cwd=str(holder), capture_output=True,
                          check=True).stdout
        digested.append((Path(repo), status))
        return real_digest(repo, rev)

    monkeypatch.setattr(subprocess, "run", record)
    monkeypatch.setattr(module, "tree_digest", digest)

    code = module.main(["add", "--family-root", str(holder), "--member",
                        f"{ORG}/{SPARE}", "--local-remote-dir",
                        str(family["remotes"]), "--dry-run"])
    ran = list(calls)

    assert code == 0
    assert len(digested) == 1, "premise: one digest, of the dry run's clone"
    (repo, status), = digested
    assert status == before["status"], (
        "the holder's status moved while the member was being read")
    temp, root = offline.temp.resolve(), holder.resolve()
    assert temp in repo.resolve().parents and root not in repo.resolve(
        ).parents, repo
    gits = [(argv, cwd) for argv, cwd in ran if Path(argv[0]).name == "git"]
    clones = [argv for argv, _ in gits if subcommand_of(argv) == "clone"]
    assert len(clones) == 2, "the probe's clone and the dry run's own"
    assert all(temp in Path(argv[-1]).resolve().parents for argv in clones)
    in_holder = [argv for argv, cwd in gits
                 if cwd is not None and Path(cwd).resolve() == root]
    assert in_holder, "premise: the holder was asked"
    assert [argv for argv in in_holder if writes(argv) and not (
        subcommand_of(argv) == "add" and "--dry-run" in argv)] == []
    assert "submodule" not in {subcommand_of(argv) for argv, _ in gits}
    assert_add_as_it_was(holder, env, before)
    offline.assert_left_nothing()


def test_add_dry_run_prints_the_id_the_members_manifest_records(
        holder, offline, tmp_path):
    """NEVER AN INVENTED ID (#326's third ruling). Every member the family
    fixture scaffolds records `id:` as its name lowercased, so a dry run
    that printed `project.lower()` would pass every other test here. This
    member is `IRDI` and its `project.yaml` says `id: routing-core`: the dry
    run prints that id, read from the member, and the real add then writes
    exactly the row the dry run printed."""
    env = isolated(offline, tmp_path)
    remotes = one_commit_remote(tmp_path, "IRDI", {
        "project.yaml": b"schema_version: 1\nkind: project-manifest\n"
                        b"id: routing-core\nname: IRDI\n"})
    before = add_state(holder, env)

    dry = add(holder, env, remotes, "--dry-run", member=f"{ORG}/IRDI")

    assert_add_as_it_was(holder, env, before)
    assert dry.returncode == 0, dry.stdout + dry.stderr
    row = printed_row(dry.stdout)
    assert row[:2] == ["  - project: IRDI", "    id: routing-core"]

    real = add(holder, env, remotes, member=f"{ORG}/IRDI")

    assert real.returncode == 0, real.stdout + real.stderr
    assert "\n".join(row) + "\n" in (holder / "family.yaml").read_text(
        encoding="utf-8"), "the row printed is the row written"
    assert {r["project"]: r for r in manifest(holder)["members"]
            }["IRDI"]["id"] == "routing-core"
    offline.assert_left_nothing()


def test_add_dry_run_removes_its_own_clone_when_reading_the_member_fails(
        family, holder, offline, tmp_path, monkeypatch, capsys):
    """RULING 2's "removed afterwards, also on a refusal", for the dry run's
    OWN clone. Every other refusal here is made before that clone exists.
    Here the probe reads the member, and the member's remote is gone by the
    time the dry run clones it a second time, as it would be if it were
    renamed or made private in between. That clone fails in git, and the
    failure is printed as every failed reading of the member is: the exact
    command, then the hint, exit 2. The directory the dry run made for its
    clone is gone, nothing else is left in TEMP, and the holder is as it
    was. In process, so the remote can be moved between the two clones."""
    module = family_module()
    env = isolated(offline, tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(tempfile, "tempdir", str(offline.temp))
    remotes = tmp_path / "remotes"
    remotes.mkdir()
    shutil.copytree(family["remotes"] / f"{SPARE}.git",
                    remotes / f"{SPARE}.git", symlinks=True)
    before = add_state(holder, env)
    real_run = module.run
    clones: list[Path] = []

    def run(args, *rest, **named):
        if "clone" in args:
            clones.append(Path(args[-1]))
            if len(clones) == 2:
                (remotes / f"{SPARE}.git").rename(remotes / f"{SPARE}.gone")
        return real_run(args, *rest, **named)

    monkeypatch.setattr(module, "run", run)

    code = module.main(["add", "--family-root", str(holder), "--member",
                        f"{ORG}/{SPARE}", "--local-remote-dir", str(remotes),
                        "--dry-run"])
    out, err = capsys.readouterr()

    assert code == 2, out + err
    assert len(clones) == 2, "premise: the dry run's own clone was the one"
    assert out == f"checking {ORG}/{SPARE} before mounting it\n"
    lines = err.splitlines()
    assert lines[0] == (f"REFUSED reading {ORG}/{SPARE}. THE EXACT COMMAND "
                        "WAS:")
    assert "clone -q --bare -- " in lines[1]
    assert lines[-1] == module.UNREADABLE_HINT
    assert not clones[1].parent.exists(), "the dry run's clone was left"
    assert_add_as_it_was(holder, env, before)
    offline.assert_left_nothing()


def test_add_dry_run_names_the_store_git_keeps_for_a_linked_worktree(
        family, holder, offline, tmp_path):
    """THE OBJECT STORE IS NAMED WHERE GIT KEEPS IT (`_module_dir`), not
    where it usually is. A holder that is a LINKED WORKTREE, a lane's usual
    holder, has a `.git` FILE, and git keeps a mount's store under
    `.git/worktrees/<name>/modules/`, not `.git/modules/`. The dry run
    names that store, it does not exist yet, and the real add then puts
    the store exactly there."""
    env = isolated(offline, tmp_path)
    lane = tmp_path / "lane"
    git("worktree", "add", "-q", "-b", "add-irqs", str(lane), cwd=holder)
    assert (lane / ".git").is_file(), "premise: a linked worktree"
    before = add_state(lane, env)

    dry = add(lane, env, family["remotes"], "--dry-run")

    assert_add_as_it_was(lane, env, before)
    assert dry.returncode == 0, dry.stdout + dry.stderr
    directory = field(dry.stdout.splitlines(), "directory")
    said = (f"{SPARE_PATH}  the member checked out at "
            f"{tip_of(family)[:12]}; its object store at ")
    assert directory.startswith(said), directory
    store = lane / directory[len(said):]
    assert not store.exists(), "premise: no store before the real add"

    real = add(lane, env, family["remotes"])

    assert real.returncode == 0, real.stdout + real.stderr
    assert (store / "config").is_file(), (
        f"the store printed, {store}, is not the one git made")
    offline.assert_left_nothing()
