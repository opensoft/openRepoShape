# SPDX-License-Identifier: Apache-2.0
"""`family.py bump --dry-run` and `remove --dry-run` print what the real run
would do and change nothing in the holder (#326).

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
name and the directory, and changes nothing. `add` takes none yet: the
changes to it in flight land first.

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
import sys
from pathlib import Path

import pytest

from conftest import git, run_script
#: The trailer lines a lane's run lands, from the file that owns them.
from test_commit_trailers import TRAILERS, trailers_of
#: The family fixture, its names and the offline environment, imported from
#: the modules that own them rather than rebuilt: a holder made any other way
#: would test a different holder.
from test_family import (  # noqa: F401
    FAMILY, ORG, family, family_module, manifest, nothing_to_do_line,
    validate,
)
from test_family_add_refusals import (  # noqa: F401
    holder, offline, refusal, sections,
)
from test_family_member_path import (
    GLOB, MEMBER, OTHER, hand_edit, isolated, older, raw, recorded,
)

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


def objects(root: Path) -> list[str]:
    """Every file in the holder's OWN object store, `.git/objects`. A blob
    written there is a write the index and the work tree do not show; the
    member's store, which `bump`'s fetch writes into, is under
    `.git/modules/` and not in this list."""
    store = root / ".git" / "objects"
    return sorted(path.relative_to(store).as_posix()
                  for path in store.rglob("*") if path.is_file())


def state(root: Path, env: dict, member: str = MEMBER) -> dict:
    """Everything a dry run must leave exactly as it found it, as bytes."""
    mount = root / "members" / member
    return {
        "objects": objects(root),
        "HEAD": raw(root, env, "rev-parse", "HEAD").stdout,
        "index": raw(root, env, "ls-files", "-s", "-z").stdout,
        "status": raw(root, env, "status", "--porcelain=v1", "-z").stdout,
        "family.yaml": (root / "family.yaml").read_bytes(),
        ".gitmodules": (root / ".gitmodules").read_bytes(),
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


def commit_in_mount(root: Path, env: dict, change) -> str:
    """A commit in `MEMBER`'s mount that `change(mount)` makes, and the mount
    put back at the commit the holder pins: the new commit is in the member's
    objects and nowhere else, and the holder is clean. Returns its sha."""
    mount = root / "members" / MEMBER
    pinned = raw(mount, env, "rev-parse", "HEAD").stdout.decode().strip()
    change(mount)
    raw(mount, env, "add", "-A")
    raw(mount, env, "commit", "-q", "-m", "A commit only this mount has")
    made = raw(mount, env, "rev-parse", "HEAD").stdout.decode().strip()
    raw(mount, env, "checkout", "-q", pinned)
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
    """A `--to` the member's objects do not hold after the fetch is exit 2,
    as the real run's checkout of it is, and neither prints a row."""
    env = isolated(offline, tmp_path)
    missing = "deadbeef" * 5
    before = state(holder, env)

    dry = bump(holder, env, missing, "--dry-run")
    real = bump(holder, env, missing)

    assert dry.returncode == real.returncode == 2, dry.stdout + dry.stderr
    assert dry.stdout == real.stdout == ""
    assert dry.stderr.startswith(
        f"REFUSED resolving {missing[:12]} in members/{MEMBER}, where a real "
        "bump checks it out.")
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
    """WHAT THE REAL RUN ASKS AFTER ITS CHECKOUT, ASKED OF THE OBJECTS. A
    `--to` whose tree has no `project.yaml` is `member-not-a-project` from
    both runs, word for word; the dry run asks it without moving the
    member's checkout, which the real run leaves at `--to`."""
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


#: Hand edits that give `members/<MEMBER>` to a section of another name,
#: appended to `.gitmodules` and committed: `(text, the name git rm then drops
#: every section of, or None for none, the other names whose sections say that
#: path and stay)`. Each is what git 2.43 does, probed: the work-tree file is
#: read with overwrite, so a name keeps its LAST path, a name moving away
#: takes the old path out of git's map, and a suspicious name is ignored.
GHOSTS = {
    "two-names": (
        f'[submodule "ghost"]\n\tpath = members/{MEMBER}\n',
        "ghost", [f"members/{MEMBER}"]),
    "last-path-wins": (
        '[submodule "ghost"]\n\tpath = members/ELSEWHERE\n'
        f'[submodule "ghost"]\n\tpath = members/{MEMBER}\n',
        "ghost", [f"members/{MEMBER}"]),
    "path-left-behind": (
        f'[submodule "ghost"]\n\tpath = members/{MEMBER}\n'
        '[submodule "ghost"]\n\tpath = members/ELSEWHERE\n',
        None, [f"members/{MEMBER}", "ghost"]),
    "suspicious-name": (
        f'[submodule "../ghost"]\n\tpath = members/{MEMBER}\n',
        f"members/{MEMBER}", ["../ghost"]),
}


@pytest.mark.parametrize("text, dropped, kept", GHOSTS.values(), ids=GHOSTS)
def test_remove_dry_run_names_the_sections_a_real_remove_drops(
        holder, offline, tmp_path, text, dropped, kept):
    """A SECOND SECTION FOR THE MEMBER'S PATH — a half-removed member, a hand
    edit — and the dry run names the name whose sections `git rm` drops (or
    that it drops none), the names it leaves that still say the path, and
    the registration `deinit` drops under the same name. Then a REAL
    `remove` takes out exactly the sections of the name the dry run named,
    and the registration it named, and nothing else: the dry run says what
    git will do, not what a reader of the file might expect."""
    env = isolated(offline, tmp_path)
    with (holder / ".gitmodules").open("ab") as gitmodules:
        gitmodules.write(text.encode("utf-8"))
    raw(holder, env, "add", "--", ".gitmodules")
    raw(holder, env, "commit", "-q", "-m", "A second section for one path")
    listed = sections((holder / ".gitmodules").read_text(encoding="utf-8"))
    before = state(holder, env)

    dry = remove(holder, env, "--dry-run")

    assert_as_it_was(holder, env, before, REMOVE_ORDER)
    assert dry.returncode == 0, dry.stdout + dry.stderr
    lines = dry.stdout.splitlines()
    path = f"members/{MEMBER}"
    assert (f'gitmodules   [submodule "{dropped}"]  path {path}, every '
            "section of that name" if dropped else
            "gitmodules   none: git reads no section of .gitmodules in the "
            f"work tree as giving {path}, so none is removed") in lines
    assert ("             left in place, though it gives the same path: "
            + ", ".join(f'[submodule "{name}"]' for name in kept)) in lines
    named = [line for line in lines if line.startswith("registration ")]
    assert named == ([f'registration [submodule "{path}"] in the holder\'s '
                      ".git/config, dropped by `git submodule deinit`"]
                     if dropped == path else [])

    real = remove(holder, env)

    assert real.returncode == 0, real.stdout + real.stderr
    assert sections((holder / ".gitmodules").read_text(encoding="utf-8")) \
        == [name for name in listed if name != dropped]
    assert bool(registered_keys(holder, env, path)) is (not named)


# --- both --------------------------------------------------------------------

@pytest.mark.parametrize("verb", ["bump", "remove"])
def test_a_dry_run_asks_the_manifest_refusal_the_real_run_asks_after_it_writes(
        family, holder, offline, tmp_path, verb):
    """`family-members-unrecognised` is asked by the real `bump` after its
    checkout and by the real `remove` after its unmount. The dry run asks it
    too, exit 2, before anything is written. The hand edit is the one
    `test_family_add_refusals.py` makes: a comment on the `members:` line,
    which YAML reads past and the line rewrite does not, left uncommitted."""
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
