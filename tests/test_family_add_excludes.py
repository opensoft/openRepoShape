# SPDX-License-Identifier: Apache-2.0
"""`family.py add` and `bump` stage past the operator's own excludes (#242).

`add` mounted the member with `git submodule add` and no `--force`, and
`_commit_one` staged with a plain `git add`; both read a global
`core.excludesFile`. `members/` is a fixed path, so an operator whose
excludes named `members`, `members/`, `*` or the member's own name had every
add of every family refused, with nothing in the invocation to change: git's
dry run refused the first four before the clone, and a directory-only rule on
the member's name (`Atlas/` in the issue) matched only once the clone was a
directory, so git's last `git add` refused it after. With the mount forced
alone, `members`, `members/` and `*` still died at `_commit_one`'s `git add`,
and so did every `bump`, which stages `[path, family.yaml]` through it. Both
are forced now, as #200 forced adopt's mount and #229 the scaffold's.

THE ISSUE'S MEMBER IS `Atlas`; this family's spare is `IRQS`, so the two
rules on the member's name are `IRQS` and `IRQS/`.

`--force` turns off more than the ignore check, and each thing it turns off
is refused before the member is read: a cached `.git/modules/<path>` it would
reactivate, an index entry at the path it would accept, a path beyond a
symlink or inside a submodule its skipped dry run would have refused before
the clone, and a name another path already has, which git 2.51 and later
would rename the mount past. Each of those tests asks the question
`test_family_add_refusals.py` asks: is the holder exactly as it was?

The same family and the same rules as `test_family.py` and
`test_family_add_refusals.py`: members are scaffolded into local bare
repositories, nothing is created on GitHub, and a `gh` on PATH logs and exits
non-zero, so a call to it would be seen. The excludes reach git through
`GIT_CONFIG_GLOBAL` (`test_scaffold_ignored_shape_files.excluding`), so no run
reads the global configuration of whoever runs the suite. No test pushes to
the fixture's own remotes.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import FILE_PROTOCOL, git, rmtree, run_script
#: The family fixture, its names and the offline environment, imported from
#: the modules that own them rather than rebuilt: a holder made any other way
#: would test a different holder.
from test_family import (  # noqa: F401
    FAMILY, NAME, ORG, SPARE, family, manifest,
)
from test_family_add_refusals import (  # noqa: F401
    holder, offline, refusal, snapshot,
)
from test_scaffold_ignored_shape_files import excluding, git_under

MOUNT = f"members/{SPARE}"

#: The operator's excludes, one row each: a rule over `members/` three ways,
#: and the member's own name as a file rule and as a directory-only one.
RULES = {
    "members": b"members\n",
    "members/": b"members/\n",
    "*": b"*\n",
    SPARE: f"{SPARE}\n".encode(),
    f"{SPARE}/": f"{SPARE}/\n".encode(),
}

#: What every refusal of an index entry at the mount path tells the human.
STAGED_REMEDIATION = (
    "Remediation: this is a half-finished add or a hand edit. `git rm -r "
    f"--cached -- {MOUNT}` takes it out of the index and touches no file; "
    "then re-run.")

#: What every refusal of git's own dry run tells the human, whatever git said:
#: git's line is the cause, and the remediation presumes none.
UNADDABLE_REMEDIATION = (
    "Remediation: that is git's own check of the path, made before anything "
    "is cloned or written, and git's line quoted above says why it refused. "
    "Every member is mounted under `members/`, which must be a plain "
    "directory of the holder's own: where git names a symbolic link there, "
    "replace it with a directory, and where it names a submodule, take that "
    "out (`git rm`); anything else it names, a held `index.lock` say, is "
    "fixed where git says. Then re-run.")

#: The dry run `member-path-unaddable` quotes, as `_reason` names it.
DRY_RUN = ("`git --literal-pathspecs add --dry-run --ignore-missing -f "
           f"--no-warn-embedded-repo -- {MOUNT}`")

SYMLINK_SKIP = pytest.mark.skipif(
    sys.platform == "win32",
    reason="a symbolic link needs a privilege a Windows runner does not have")


def under(offline, tmp_path: Path, rules: bytes) -> dict:
    """`offline`'s environment, for an operator whose global excludes are
    `rules` (`b""`: none, still naming the file)."""
    return {**offline.env, **excluding(tmp_path / "operator", rules)}


def add(env: dict, root: Path, remotes: Path) -> subprocess.CompletedProcess:
    return run_script(FAMILY, "add", "--family-root", str(root),
                      "--member", f"{ORG}/{SPARE}",
                      "--local-remote-dir", str(remotes), env=env)


def ignored_mount(root: Path, env: dict) -> bool:
    """Do the operator's excludes match the mount path? THE PREMISE: a test
    whose rule matched nothing would pass on the old code. Asked with the
    TRAILING SLASH, the directory form, which is the only form a
    directory-only rule like `IRQS/` answers while the path does not exist
    yet (#229)."""
    return git_under(env, "check-ignore", "-q", "--no-index", "--",
                     f"{MOUNT}/", cwd=root, check=False).returncode == 0


def tip_of(family) -> str:
    return git("rev-parse", "main",
               cwd=family["remotes"] / f"{SPARE}.git").stdout.strip()


def committed(root: Path) -> list[str]:
    return git("show", "--name-only", "--format=", "HEAD",
               cwd=root).stdout.split()


def gitlink(root: Path, path: str) -> str:
    """`git ls-tree HEAD <path>`, as git prints it: the mode, the type and
    the commit the holder's own commit records — never the exit code."""
    return git("ls-tree", "HEAD", "--", path, cwd=root).stdout


def validated(root: Path, env: dict) -> str:
    """`validate-family.py`, run under `env`'s excludes; its stdout."""
    checked = run_script(root / "scripts" / "validate-family.py", cwd=root,
                         env=env)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    return checked.stdout


def recursive_clone(root: Path, tmp_path: Path) -> Path:
    """`root` pushed to a bare repository of its own, then cloned with every
    submodule by an operator with NO excludes: the holder a reviewer pulls.
    The fixture's remote is never pushed to, so no other test sees the
    commit."""
    env = excluding(tmp_path / "reviewer", b"")
    bare = tmp_path / "pushed" / f"{NAME}.git"
    git_under(env, "init", "-q", "--bare", "-b", "main", str(bare),
              cwd=tmp_path)
    git_under(env, "push", "-q", str(bare), "HEAD:refs/heads/main", cwd=root)
    clone = tmp_path / "clone" / NAME
    git_under(env, *FILE_PROTOCOL, "clone", "-q", "--recurse-submodules",
              str(bare), str(clone), cwd=tmp_path)
    return clone


def refused_before_the_mount(result: subprocess.CompletedProcess, root: Path,
                             before: dict) -> None:
    """Refused before the member was even read — not one line on stdout,
    where `checking ... before mounting it` is the first — and the holder
    exactly as `before` recorded it."""
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == ""
    assert snapshot(root) == before


@pytest.fixture
def empty_holder(tmp_path) -> Path:
    """A holder with NO member yet, so `members/` does not exist and a test
    can put something else there. `family.py init`, into remotes of its
    own."""
    created = run_script(FAMILY, "init", "--org", ORG, "--family", "Contoso",
                         "--created-by", "Test Human",
                         "--created-on", "2026-09-04",
                         "--local-remote-dir", str(tmp_path / "own-remotes"),
                         "--work-dir", str(tmp_path / "work"))
    assert created.returncode == 0, created.stderr + created.stdout
    root = tmp_path / "work" / "Contoso"
    assert not (root / "members").exists()
    return root


# --- the issue: every rule, `add` and `bump` --------------------------------

@pytest.mark.parametrize("rule", ["none", *RULES])
def test_add_mounts_and_commits_past_the_operators_excludes(
        family, holder, offline, tmp_path, rule):
    """THE ISSUE'S TABLE, ONE ROW EACH, and `none` the control. Every rule
    used to exit 2: `members`, `members/`, `*` and `IRQS` at git's dry run,
    `IRQS/` at git's last `git add` after the clone. Now each is ONE commit
    of exactly `.gitmodules`, `family.yaml` and a gitlink at the member's
    tip, read back from git; the holder validates under the same excludes;
    and it clones, every submodule with it, for somebody who has none."""
    env = under(offline, tmp_path, RULES.get(rule, b""))
    assert ignored_mount(holder, env) is (rule != "none")
    tip = tip_of(family)
    was = git("rev-parse", "HEAD", cwd=holder).stdout.strip()
    result = add(env, holder, family["remotes"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""
    assert git("rev-parse", "HEAD~1", cwd=holder).stdout.strip() == was
    assert committed(holder) == [".gitmodules", "family.yaml", MOUNT]
    assert gitlink(holder, MOUNT) == f"160000 commit {tip}\t{MOUNT}\n"
    assert f'[submodule "{MOUNT}"]' in git("show", "HEAD:.gitmodules",
                                           cwd=holder).stdout
    row = {r["project"]: r for r in manifest(holder)["members"]}[SPARE]
    assert row["pin"]["commit"] == tip
    assert git_under(env, "status", "--porcelain", cwd=holder).stdout == ""
    assert f"family ok: {NAME} (inkrouter), 3 member(s)" in validated(holder,
                                                                      env)
    clone = recursive_clone(holder, tmp_path)
    assert git("rev-parse", "HEAD", cwd=clone / MOUNT).stdout.strip() == tip
    assert (clone / MOUNT / "project.yaml").is_file()
    offline.assert_left_nothing()


def test_bump_moves_the_gitlink_past_the_operators_excludes(holder, offline,
                                                            tmp_path):
    """`bump` RIDES WITH THE ISSUE. It stages `[path, family.yaml]` through
    `_commit_one`, so under `members` it died at the same `git add` with the
    gitlink already tracked, and left both staged with no commit. The new
    commit is made inside the holder's own mount, so the fixture's remote is
    never pushed to."""
    env = under(offline, tmp_path, RULES["members"])
    member = holder / "members" / "IRRS"
    (member / "MOVED.md").write_bytes(b"the member advanced\n")
    git("add", "--", "MOVED.md", cwd=member)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "Advance the member", cwd=member)
    moved = git("rev-parse", "HEAD", cwd=member).stdout.strip()
    pinned = {r["project"]: r for r in manifest(holder)["members"]}["IRRS"]
    assert pinned["pin"]["commit"] != moved
    was = git("rev-parse", "HEAD", cwd=holder).stdout.strip()

    result = run_script(FAMILY, "bump", "--family-root", str(holder),
                        "--member", "IRRS", "--to", moved, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""
    assert git("rev-parse", "HEAD~1", cwd=holder).stdout.strip() == was
    assert committed(holder) == ["family.yaml", "members/IRRS"]
    assert gitlink(holder, "members/IRRS") == \
        f"160000 commit {moved}\tmembers/IRRS\n"
    row = {r["project"]: r for r in manifest(holder)["members"]}["IRRS"]
    assert row["pin"]["commit"] == moved
    assert git_under(env, "status", "--porcelain", cwd=holder).stdout == ""
    assert f"family ok: {NAME} (inkrouter), 2 member(s)" in validated(holder,
                                                                      env)
    offline.assert_left_nothing()


def test_remove_is_one_commit_under_the_operators_excludes(holder, offline,
                                                           tmp_path):
    """The control the issue names: `remove` never failed — `git rm` stages
    the deletion and `_commit_one` is handed only the two files it left —
    and forcing the add must not change what it commits."""
    env = under(offline, tmp_path, RULES["members"])
    result = run_script(FAMILY, "remove", "--family-root", str(holder),
                        "--member", "IRSS", env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert committed(holder) == [".gitmodules", "family.yaml", "members/IRSS"]
    assert gitlink(holder, "members/IRSS") == ""
    assert [line.split("\t")[1] for line in gitlink(
        holder, "members/").splitlines()] == ["members/IRRS"]
    assert f"family ok: {NAME} (inkrouter), 1 member(s)" in validated(holder,
                                                                      env)
    offline.assert_left_nothing()


# --- what else `--force` would let past git, each refused first -------------

@pytest.mark.parametrize("where", ["an ordinary clone", "a linked worktree"])
def test_a_cached_store_is_refused_before_the_mount_would_reactivate_it(
        family, holder, offline, tmp_path, where):
    """`member-git-dir-cached`. Given `--force`, `git submodule add`
    REACTIVATES a `.git/modules/<path>` left by a removed member instead of
    refusing it, and the gitlink is then that store's commit. The refusal
    comes first, at the store git's own `--git-path` names — a linked
    worktree's is under `.git/worktrees/<name>/modules/` — and under the
    operator's excludes, so the `-f` everywhere else changes nothing here."""
    env = under(offline, tmp_path, RULES["members"])
    root = holder
    if where == "a linked worktree":
        root = tmp_path / "lane"
        git("worktree", "add", "-q", "-b", "readd", str(root), cwd=holder)
    added = add(env, root, family["remotes"])
    assert added.returncode == 0, added.stdout + added.stderr
    removed = run_script(FAMILY, "remove", "--family-root", str(root),
                         "--member", SPARE, env=env)
    assert removed.returncode == 0, removed.stdout + removed.stderr
    store = root.resolve() / git("rev-parse", "--git-path",
                                 f"modules/{MOUNT}", cwd=root).stdout.strip()
    assert store.is_dir()

    before = snapshot(root)
    result = add(env, root, family["remotes"])
    refused_before_the_mount(result, root, before)
    assert result.stderr.splitlines() == [
        f"REFUSED member-git-dir-cached: {store.as_posix()} still holds the "
        f"object store of a previously removed {SPARE}, and `git submodule "
        "add` will not write over it",
        "Remediation: if nothing unpushed lives in it — and nothing does "
        "unless somebody committed inside the mount — delete it and re-run:",
        f"    rm -rf {store.as_posix()}",
        "It is left behind by `git rm` on purpose, which is why this tool "
        "will not remove it for you.",
    ]
    assert store.is_dir()
    offline.assert_left_nothing()


@pytest.mark.parametrize("entry", ["a submodule", "a file", "a file under it"])
def test_an_index_entry_at_the_mount_path_is_refused_before_the_mount(
        family, holder, offline, tmp_path, entry):
    """`member-path-taken`, ASKED OF THE INDEX TOO. Nothing is on disk, but
    the index holds the path: a half-finished add, or `rm -rf` where `git rm`
    was meant. Given `--force`, git ACCEPTS a gitlink there and replaces it
    with the member's — the one staged here names a commit the member does
    not have, so the replacement would be visible — and the human's staged
    entry is gone without a word. A file at the path or under it git refuses
    either way, but only at the mount. All three are refused first, and the
    remediation, run as printed, lets the same command through."""
    env = under(offline, tmp_path, RULES["members"])
    if entry == "a submodule":
        git("update-index", "--add", "--cacheinfo",
            f"160000,{'1' * 40},{MOUNT}", cwd=holder)
        named = f"`{MOUNT}` (a submodule)"
    else:
        blob = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                              cwd=str(holder), input=b"a file\n",
                              capture_output=True, check=True).stdout
        name = MOUNT if entry == "a file" else f"{MOUNT}/inside"
        git("update-index", "--add", "--cacheinfo",
            f"100644,{blob.decode('ascii').strip()},{name}", cwd=holder)
        named = f"`{name}` (a file)" + ("" if name == MOUNT else
                                        f" under {MOUNT}")
    before = snapshot(holder)
    result = add(env, holder, family["remotes"])
    refused_before_the_mount(result, holder, before)
    assert refusal(result.stderr) == (
        f"REFUSED member-path-taken: the family root's index holds {named}, "
        f"though nothing is at {MOUNT} on disk and no `members:` row names it",
        STAGED_REMEDIATION)
    offline.assert_left_nothing()

    git("rm", "-r", "-q", "--cached", "--", MOUNT, cwd=holder)
    again = add(env, holder, family["remotes"])
    assert again.returncode == 0, again.stdout + again.stderr
    assert gitlink(holder, MOUNT) == \
        f"160000 commit {tip_of(family)}\t{MOUNT}\n"


@SYMLINK_SKIP
@pytest.mark.parametrize("target", ["nothing", "a directory"])
def test_a_link_at_the_mount_path_is_refused_before_the_mount(
        family, holder, offline, tmp_path, target):
    """`member-path-taken` by `lexists`. A link to a directory was always
    refused; a DANGLING one was let through, to fail at the clone, because
    `Path.exists()` follows a link to nothing and says False. Either is
    refused first now, and what it points at is untouched."""
    env = under(offline, tmp_path, RULES["members"])
    pointed = tmp_path / "elsewhere"
    if target == "a directory":
        pointed.mkdir()
    os.symlink(str(pointed), holder / MOUNT)
    before = snapshot(holder)
    result = add(env, holder, family["remotes"])
    refused_before_the_mount(result, holder, before)
    assert refusal(result.stderr) == (
        f"REFUSED member-path-taken: {MOUNT} already exists in the family "
        "root but no `members:` row names it",
        "Remediation: this is a half-finished add or a hand-made directory. "
        "Remove it (`git rm -r` if it is tracked), then re-run.")
    assert (holder / MOUNT).is_symlink()
    assert (list(pointed.iterdir()) == []) if target == "a directory" else \
        not pointed.exists()
    offline.assert_left_nothing()


@SYMLINK_SKIP
def test_members_as_a_link_is_refused_before_the_member_is_cloned_through_it(
        family, empty_holder, offline, tmp_path):
    """`member-path-unaddable`: GIT'S OWN DRY RUN, made first. `--force`
    skips the dry run that refuses a path beyond a symbolic link, so with
    `members` linking elsewhere the member was CLONED through the link —
    outside the holder — before git refused the last step. The same dry run
    is made before anything is read, with `-f`, so the operator's rule
    passes it and the link does not."""
    env = under(offline, tmp_path, RULES["members"])
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    os.symlink(str(elsewhere), empty_holder / "members")
    before = snapshot(empty_holder)
    result = add(env, empty_holder, family["remotes"])
    refused_before_the_mount(result, empty_holder, before)
    assert refusal(result.stderr) == (
        f"REFUSED member-path-unaddable: git will not add the mount path "
        f"{MOUNT}: {DRY_RUN}: fatal: pathspec '{MOUNT}' is beyond a symbolic "
        "link", UNADDABLE_REMEDIATION)
    assert list(elsewhere.iterdir()) == []
    offline.assert_left_nothing()


@pytest.mark.parametrize("name", ["members", "other"])
def test_members_as_a_submodule_is_refused_before_the_member_is_cloned_into_it(
        family, empty_holder, offline, tmp_path, name):
    """`member-path-unaddable`, the dry run's other refusal: `members`
    is itself a submodule's path. Given `--force`, git cloned the member INTO
    that submodule's working tree before refusing it (when the submodule is
    named `other`), or refused only at the clone (named `members`, whose
    store would hold the member's). Refused first, either way."""
    env = under(offline, tmp_path, RULES["members"])
    git(*FILE_PROTOCOL, "submodule", "add", "-q", "--name", name, "--",
        str(family["remotes"] / "IRRS-spec.git"), "members", cwd=empty_holder)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "A submodule at members", cwd=empty_holder)
    before = snapshot(empty_holder)
    result = add(env, empty_holder, family["remotes"])
    refused_before_the_mount(result, empty_holder, before)
    assert refusal(result.stderr) == (
        f"REFUSED member-path-unaddable: git will not add the mount path "
        f"{MOUNT}: {DRY_RUN}: fatal: Pathspec '{MOUNT}' is in submodule "
        "'members'", UNADDABLE_REMEDIATION)
    assert not (empty_holder / MOUNT).exists()
    offline.assert_left_nothing()


def test_a_dry_run_refused_for_another_reason_quotes_git_and_guesses_nothing(
        family, holder, offline, tmp_path):
    """`member-path-unaddable` WHEN THE CAUSE IS NOT THE PATH. git's dry run
    takes `index.lock`, so with one held — another git still running, or
    one that died — it refuses before the member is read, which is right.
    The remediation told the human to replace a symbolic link or take a
    submodule out, and neither was there; it now sends them to git's own
    line, which names the lock."""
    env = under(offline, tmp_path, RULES["members"])
    lock = holder / git("rev-parse", "--git-path", "index.lock",
                        cwd=holder).stdout.strip()
    lock.write_bytes(b"")
    before = snapshot(holder)
    result = add(env, holder, family["remotes"])
    refused_before_the_mount(result, holder, before)
    said, remediation = refusal(result.stderr)
    assert said.startswith(
        "REFUSED member-path-unaddable: git will not add the mount path "
        f"{MOUNT}: {DRY_RUN}: fatal: Unable to create '"), said
    assert said.endswith("index.lock': File exists"), said
    assert remediation == UNADDABLE_REMEDIATION
    assert lock.is_file()
    offline.assert_left_nothing()


@pytest.mark.parametrize("store", ["checked out", "not checked out"])
def test_a_name_another_submodule_has_is_refused_before_the_mount(
        family, holder, offline, tmp_path, store):
    """`member-name-taken`. git names a submodule after its path, so the
    mount at `members/IRQS` is named `members/IRQS`; here `.gitmodules`
    already gives that name to a submodule at `vendor/spec`. Git 2.51 and
    later refuse that without `--force` and, given it, mount the member under
    a new name (`members/IRQS1`) whose store and registration the unwind
    would not find; git before 2.51 rewrites the other submodule's section to
    point at the member. Refused first on every git — and before
    `member-git-dir-cached`, which would otherwise blame a "previously
    removed" member for the other submodule's store."""
    env = under(offline, tmp_path, RULES["members"])
    git(*FILE_PROTOCOL, "submodule", "add", "-q", "--name", MOUNT, "--",
        str(family["remotes"] / "IRRS-spec.git"), "vendor/spec", cwd=holder)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        f"A submodule named {MOUNT} at vendor/spec", cwd=holder)
    if store == "not checked out":
        git("submodule", "deinit", "-q", "-f", "--", "vendor/spec",
            cwd=holder)
        rmtree(holder / ".git" / "modules" / "members" / SPARE)
    before = snapshot(holder)
    result = add(env, holder, family["remotes"])
    refused_before_the_mount(result, holder, before)
    assert refusal(result.stderr) == (
        f"REFUSED member-name-taken: .gitmodules already gives the name "
        f"`{MOUNT}` to the submodule at vendor/spec, and that is the name git "
        f"gives {SPARE}'s mount",
        "Remediation: git names a submodule after its path, so that name is "
        "a member's. Give that submodule a name of its own, or take it out, "
        "by hand, then re-run. Mounting over the name would rewrite its "
        f"section to point at {SPARE} (git before 2.51), or mount {SPARE} "
        "under another name this tool does not follow (git 2.51 and later, "
        "with the `--force` this tool mounts with).")
    assert not (holder / MOUNT).exists()
    offline.assert_left_nothing()


@pytest.mark.parametrize("kept_in", ["the index", "HEAD"])
def test_a_name_taken_in_a_gitmodules_off_the_disk_is_refused_before_the_mount(
        family, holder, offline, tmp_path, kept_in):
    """`member-name-taken`, READ WHERE `git submodule add` READS IT. With no
    `.gitmodules` on disk git reads the index's copy, or HEAD's where the
    index has none either, and so does `_submodule_paths`: here only that
    copy gives the mount's name to `vendor/spec`. Read off the disk alone,
    nothing named it, and the add went on to blame a "previously removed"
    member for `vendor/spec`'s store instead."""
    env = under(offline, tmp_path, RULES["members"])
    git(*FILE_PROTOCOL, "submodule", "add", "-q", "--name", MOUNT, "--",
        str(family["remotes"] / "IRRS-spec.git"), "vendor/spec", cwd=holder)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        f"A submodule named {MOUNT} at vendor/spec", cwd=holder)
    if kept_in == "HEAD":
        git("rm", "-q", "--cached", "--", ".gitmodules", cwd=holder)
    (holder / ".gitmodules").unlink()
    before = snapshot(holder)
    result = add(env, holder, family["remotes"])
    refused_before_the_mount(result, holder, before)
    assert refusal(result.stderr)[0] == (
        "REFUSED member-name-taken: .gitmodules already gives the name "
        f"`{MOUNT}` to the submodule at vendor/spec, and that is the name git "
        f"gives {SPARE}'s mount")
    offline.assert_left_nothing()
