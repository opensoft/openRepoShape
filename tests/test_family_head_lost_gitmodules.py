# SPDX-License-Identifier: Apache-2.0
"""A holder whose HEAD lost `.gitmodules`, and the gate's gitlink remedies
(#611).

THE ISSUE'S FOUR LINES, each reproduced on main before this change:

- 571(b). In a holder whose HEAD already lost `.gitmodules` (the commit #407
  describes), `family.py remove --dry-run` exited 0, and the real run did
  `git submodule deinit` and `git rm`, then died at its commit's `git
  --literal-pathspecs add -f -- .gitmodules family.yaml` (`pathspec
  '.gitmodules' did not match any files`). Its rollback put HEAD and the
  index back and left the member's directory EMPTY. `remove` now refuses
  that holder before any git command that writes, `member-gitmodules-absent`,
  under `--dry-run` alike, and its remedy writes back each member's section.
- 571(c). `validate-family.py` passed a `members:` row whose gitlink no
  section of HEAD's `.gitmodules` gives (#407's decision 3): `family ok` in
  the holder, `--no-members` too, while a fresh recursive clone left every
  such member empty and its gate refused `member-uninitialized`, naming a `git
  submodule update` that exits 0 and checks nothing out. It is the finding
  `member-gitmodules-absent` now, in every mode, read from HEAD, and a member
  it names that is not checked out is not refused as uninitialized.
- 574/2. `member-gitlink-absent` said nothing of a gitlink HEAD holds at a
  case variant of the row's path (#363's item 3), and named `family.py add`,
  which cannot help: the row is there. It names the variant now, and the
  index move that records the member at its own path.
- 574/3. A hand mount's `member-gitlink-unnamed` remedy said `git rm`, then
  `family.py add`. `add` refuses a path under another spelling of `members/`
  that HEAD holds and the index no longer does (#574), so it says to commit
  the removal between them now.

THE SAME FAMILY, OFFLINE RULES AND READINGS as
`test_family_remove_gitmodules.py` (#407), whose helpers are imported. Every
remedy is typed as printed: split as a POSIX shell splits it, run with no
shell. The url a written-back section gives is the one `family.py add`
writes, `https://github.com/<org>/<Name>.git`, and a clone reaches the
fixture's local remotes through it by a `url.<base>.insteadOf` for the one
command, as `clone_just_pushed` reaches the legs. The case-variant states are
index records and commits (`stage_gitlink`), never two directories whose
names differ only in case, and each is asked again with
`core.ignorecase=true`, how macOS and Windows clone, so every one runs on all
three systems.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

from conftest import clone_just_pushed, run_script
from repo_shape import PYTHON
#: The family fixture, its names, the offline environment and the readings
#: of a holder, imported from the modules that own them rather than rebuilt.
from test_family import (  # noqa: F401
    FAMILY, NAME, ORG, SPARE, family, validate,
)
from test_family_add_excludes import empty_holder  # noqa: F401
from test_family_add_refusals import holder, offline  # noqa: F401
from test_family_dry_run import isolated
from test_family_member_path import MEMBER, OTHER, raw
from test_family_remove_gitmodules import (
    deleted, edited, head_paths, left_out, ran, refused_alike,
    typed_as_printed, verb_args,
)
from test_scaffold_ignored_shape_files import excluding
from test_validate_family_unnamed_mounts import (
    commands, findings, spare_commits, stage_gitlink,
)

GITMODULES = ".gitmodules"
MODES = pytest.mark.parametrize(
    "extra", [(), ("--pins",), ("--no-members",)],
    ids=["members-checked", "pins", "no-members"])

#: The two disks: git's own reading of a case-sensitive one, and how macOS
#: and Windows clone (`core.ignorecase=true`), set for every git command the
#: test types.
DISKS = pytest.mark.parametrize("ignorecase", ["false", "true"],
                                ids=["linux", "folding"])


def on_disk(env: dict, ignorecase: str) -> dict:
    """`env` with `core.ignorecase` set to `ignorecase`, one more
    `GIT_CONFIG_*` entry after the ones it already holds."""
    index = int(env.get("GIT_CONFIG_COUNT", "0"))
    return {**env, "GIT_CONFIG_COUNT": str(index + 1),
            f"GIT_CONFIG_KEY_{index}": "core.ignorecase",
            f"GIT_CONFIG_VALUE_{index}": ignorecase}


def url(project: str) -> str:
    """The url `family.py add` writes for a member of the fixture's org."""
    return f"https://github.com/{ORG}/{project}.git"


#: What `remove` says in a holder that holds no `.gitmodules` anywhere.
REMOVE_REFUSED = (
    "REFUSED member-gitmodules-absent: the holder has no .gitmodules: neither "
    "the work tree, the index nor HEAD holds one, though the index records a "
    "gitlink at members/{member}. `git rm` edits only a .gitmodules the work "
    "tree has, and `remove` commits .gitmodules as `git rm` leaves it, so "
    "with none to commit it would fail after `git submodule deinit` and `git "
    "rm` had emptied members/{member}. A recursive clone of the holder checks "
    "out none of its members, and its validate-family.py finds "
    "member-gitmodules-absent for each. No git command that writes was run "
    "and nothing was written.")


def remove_remedy(*projects: str) -> str:
    """`remove`'s remediation, writing back the section of each of
    `projects`, in that order."""
    written = " and ".join(
        f"`git config -f .gitmodules submodule.members/{project}.{key} "
        f"{value}`" for project in projects
        for key, value in (("path", f"members/{project}"),
                           ("url", url(project))))
    return ("Remediation: write back the section `family.py add` writes for "
            "each member the index records, this one included, in a POSIX "
            f"shell — {written} — then stage it, `git add -f .gitmodules` "
            "(`-f`, since an operator's excludes may match it), and commit it "
            "on its own first if the command's commit should carry only its "
            "own change, and run the same command again.")


def absent(project: str, commit: str, *, held: bool,
           with_url: bool = True) -> str:
    """The `member-gitmodules-absent` finding for `project`'s gitlink at
    `commit`, WHOLE: its line and the commands under it. `held` is whether
    HEAD holds a `.gitmodules` at all; `with_url` whether the section to
    write has no url of its own."""
    path = f"members/{project}"
    lines = f"\n    git config -f .gitmodules submodule.{path}.path {path}"
    if with_url:
        lines += (f"\n    git config -f .gitmodules submodule.{path}.url "
                  f"{url(project)}")
    return (f"FINDING member-gitmodules-absent: {path} is a gitlink at "
            f"{commit} that a row of members: names, and "
            + ("no section of HEAD's .gitmodules gives that path" if held
               else "HEAD holds no .gitmodules")
            + ", so a recursive clone of this holder checks out nothing "
            "there, and neither does make bootstrap in that clone, whatever "
            "checkout this holder has of it. Write its section back by hand, "
            "in a POSIX shell, as family.py add writes one, then stage and "
            f"commit .gitmodules:{lines}")


# --- the states --------------------------------------------------------------

def commit_all(root: Path, env: dict, message: str) -> None:
    raw(root, env, "commit", "-q", "-m", message)


def head_lost(root: Path, env: dict) -> None:
    """THE ISSUE'S STATE: `.gitmodules` deleted and the deletion committed,
    as the commit #407 describes left it. The registrations stay in the
    holder's git config, and its checkouts on disk."""
    raw(root, env, "rm", "-q", "--", GITMODULES)
    commit_all(root, env, "The commit #407 describes")


def committed_gitmodules(root: Path, env: dict, data: bytes) -> None:
    """`data` committed as `.gitmodules`, hashed into git's objects as
    BYTES, and the same bytes on disk, so no platform rewrites a line
    ending."""
    blob = raw(root, env, "hash-object", "-w", "--stdin",
               stdin=data).stdout.decode("ascii").strip()
    raw(root, env, "update-index", "--cacheinfo",
        f"100644,{blob},{GITMODULES}")
    commit_all(root, env, "A .gitmodules edited by hand")
    (root / GITMODULES).write_bytes(data)


def without_section(root: Path, env: dict, project: str) -> None:
    """HEAD's `.gitmodules` with `project`'s section taken out by hand and
    committed, the other member's left as `family.py add` wrote it."""
    data = raw(root, env, "show", f"HEAD:{GITMODULES}").stdout
    section = re.compile(rb'\[submodule "members/' + project.encode() +
                         rb'"\]\n(?:\t[^\n]*\n)*')
    assert len(section.findall(data)) == 1, data
    committed_gitmodules(root, env, section.sub(b"", data))


def pinned(root: Path, project: str) -> str:
    """The commit `family.yaml` pins `project` at, as git records its
    gitlink after `family.py add`."""
    return raw(root, {}, "rev-parse", f"HEAD:members/{project}").stdout.decode(
        "ascii").strip()


def typed(root: Path, env: dict, finding: str) -> None:
    """Every command `finding` prints, typed as printed."""
    for command in commands(finding):
        argv = shlex.split(command)
        assert argv[0] == "git", command
        raw(root, env, *argv[1:])


def staged_and_committed(root: Path, env: dict, message: str) -> None:
    """What a finding's "then stage and commit .gitmodules" says."""
    raw(root, env, "add", "--", GITMODULES)
    commit_all(root, env, message)


def assert_passes_in_every_mode(root: Path, members: int) -> None:
    for extra in ((), ("--pins",), ("--no-members",)):
        result = validate(root, *extra)
        assert result.returncode == 0, (extra, result.stderr + result.stdout)
        assert (f"family ok: {NAME} (inkrouter), {members} member(s)"
                in result.stdout), extra


def github_to(remotes: Path) -> list[str]:
    """The `-c` that makes a clone read `https://github.com/<org>/` from the
    fixture's local remotes, for the one command."""
    uri = remotes.resolve().as_uri().rstrip("/") + "/"
    return ["-c", f"url.{uri}.insteadOf=https://github.com/{ORG}/"]


def pushed_and_cloned(root: Path, env: dict, family, tmp_path: Path,
                      branch: str) -> Path:
    """HEAD pushed to `branch` of the family's own remote, then a fresh
    `clone --recurse-submodules` of it, which must exit 0."""
    remote = family["remotes"] / f"{NAME}.git"
    raw(root, env, "push", "-q", str(remote), f"HEAD:refs/heads/{branch}")
    clone = tmp_path / f"clone-{branch.replace('/', '-')}"
    cloned = clone_just_pushed(remote, clone, branch,
                               config=github_to(family["remotes"]))
    assert cloned.returncode == 0, cloned.stdout + cloned.stderr
    return clone


# --- 571(b): remove in a holder whose HEAD lost .gitmodules ------------------

@pytest.mark.parametrize("rules", [b"", b"*\n"], ids=["no-excludes", "star"])
def test_remove_refuses_a_holder_whose_head_lost_gitmodules(
        family, holder, offline, tmp_path, rules):
    """`member-gitmodules-absent`, by `remove` and its dry run alike, exit 2,
    with the holder byte for byte as it was, MEMBER's checkout included:
    the real run used to empty it and fail at its commit. Typed as printed,
    under an operator whose excludes hold `*` too (hence the `-f`), the
    remedy writes both members' sections back and stages them; `remove`
    then commits MEMBER's removal with OTHER's section back in HEAD, and
    the gate passes."""
    env = {**isolated(offline, tmp_path), **excluding(tmp_path / "op", rules)}
    head_lost(holder, env)
    args = verb_args("remove", holder, family)

    said, remediation = refused_alike(holder, env, args)

    assert said == REMOVE_REFUSED.format(member=MEMBER)
    assert remediation == remove_remedy(MEMBER, OTHER)
    assert (holder / "members" / MEMBER / "project.yaml").is_file()
    assert typed_as_printed(holder, env, remediation)[-1] == (
        "git add -f .gitmodules")
    ran(holder, env, args)
    assert head_paths(holder, env) == [f"members/{OTHER}"]
    assert_passes_in_every_mode(holder, 1)


def test_the_holder_remove_leaves_clones_with_the_other_member(
        family, holder, offline, tmp_path):
    """THE ISSUE'S CLONE. After the remedy and the `remove`, a push and a
    fresh `clone --recurse-submodules` check OTHER out, from the url the
    written-back section gives, and the clone's own gate passes, where
    before the change a clone of this holder checked out no member at all."""
    env = isolated(offline, tmp_path)
    head_lost(holder, env)
    args = verb_args("remove", holder, family)
    typed_as_printed(holder, env, refused_alike(holder, env, args)[1])
    ran(holder, env, args)

    clone = pushed_and_cloned(holder, env, family, tmp_path, "w611/removed")

    assert (clone / "members" / OTHER / "project.yaml").is_file()
    assert not (clone / "members" / MEMBER).exists()
    gate = validate(clone)
    assert gate.returncode == 0, gate.stdout + gate.stderr


def test_remove_of_a_member_whose_section_alone_is_gone_runs_as_before(
        family, holder, offline, tmp_path):
    """The refusal is for a holder with NO `.gitmodules`, where the commit
    cannot stage one. Where HEAD's file lacks only the member's own section,
    `git rm` finds none to take out and `remove` commits the gitlink and the
    row, as it did before: the holder it leaves passes the gate."""
    env = isolated(offline, tmp_path)
    without_section(holder, env, MEMBER)

    removed = run_script(FAMILY, *verb_args("remove", holder, family),
                         env=env)

    assert removed.returncode == 0, removed.stdout + removed.stderr
    assert head_paths(holder, env) == [f"members/{OTHER}"]
    assert_passes_in_every_mode(holder, 1)


# --- 571(c): a gitlink no section of HEAD's .gitmodules gives ---------------

@MODES
def test_a_head_that_lost_gitmodules_is_a_finding_per_member(holder, offline,
                                                              tmp_path, extra):
    """THE ISSUE'S GATE: `family ok` before the change, in every mode. One
    finding per member, each naming its gitlink and the two lines that write
    its section back, in every mode, since none needs a member checked out.
    Typed as printed, staged and committed, the holder passes again."""
    env = isolated(offline, tmp_path)
    head_lost(holder, env)

    result = validate(holder, *extra)

    assert result.returncode == 1, result.stderr + result.stdout
    assert "REFUSED" not in result.stderr, result.stderr
    assert findings(result) == [
        absent(project, pinned(holder, project), held=False)
        for project in (MEMBER, OTHER)]
    for finding in findings(result):
        typed(holder, env, finding)
    staged_and_committed(holder, env, "Write the sections back as printed")
    assert_passes_in_every_mode(holder, 2)


@MODES
def test_a_section_head_lost_alone_is_one_finding(holder, offline, tmp_path,
                                                  extra):
    """One member's section taken out of HEAD's `.gitmodules` by hand: a
    recursive clone checks that member out nowhere, though the file is
    there. One finding, for it alone, and the other member is asked
    nothing."""
    env = isolated(offline, tmp_path)
    without_section(holder, env, OTHER)

    result = validate(holder, *extra)

    assert result.returncode == 1, result.stderr + result.stdout
    (finding,) = findings(result)
    assert finding == absent(OTHER, pinned(holder, OTHER), held=True)
    typed(holder, env, finding)
    staged_and_committed(holder, env, "Write the section back as printed")
    assert_passes_in_every_mode(holder, 2)


def test_a_section_of_the_name_add_gives_keeps_its_url(holder, offline,
                                                       tmp_path):
    """A section named `members/<P>`, as `family.py add` names one, whose
    path is another case (`members/irss`): no section gives OTHER's path,
    so a clone checks it out nowhere. The section's url is kept, and only
    its path is written, which clears this finding and the section's own
    `gitmodules-path-unnamed` beside it."""
    env = isolated(offline, tmp_path)
    data = raw(holder, env, "show", f"HEAD:{GITMODULES}").stdout
    old = f"\tpath = members/{OTHER}\n".encode()
    assert data.count(old) == 1, data
    committed_gitmodules(holder, env, data.replace(
        old, f"\tpath = members/{OTHER.lower()}\n".encode()))

    result = validate(holder)

    assert result.returncode == 1, result.stderr + result.stdout
    section, finding = findings(result)
    assert section.startswith("FINDING gitmodules-path-unnamed: "), section
    assert finding == absent(OTHER, pinned(holder, OTHER), held=True,
                             with_url=False)
    typed(holder, env, finding)
    staged_and_committed(holder, env, "Write the path back as printed")
    assert_passes_in_every_mode(holder, 2)


def test_a_fresh_clone_of_it_says_the_finding_and_not_uninitialized(
        family, holder, offline, tmp_path):
    """BOOTSTRAP, VALIDATE AND A FRESH RECURSIVE CLONE AGREE. Pushed, the
    holder whose HEAD lost `.gitmodules` clones with exit 0 and both
    members empty; `make bootstrap`'s script there checks neither out, and
    says so for each; and the clone's gate names both, members checked or
    not, where before the change it refused `member-uninitialized`, whose
    `git submodule update` exits 0 there. With the sections written back
    as printed and pushed, a fresh clone checks both out and its gate
    passes."""
    env = isolated(offline, tmp_path)
    head_lost(holder, env)
    clone = pushed_and_cloned(holder, env, family, tmp_path, "w611/lost")
    expected = [absent(project, pinned(holder, project), held=False)
                for project in (MEMBER, OTHER)]

    assert [path.name for path in (clone / "members").iterdir()
            if any(path.iterdir())] == []
    booted = run_script(clone / "scripts" / "bootstrap.py", cwd=clone)
    for project in (MEMBER, OTHER):
        assert f"  [{project}] {project}: NOT CHECKED OUT; skipped." in (
            booted.stdout), booted.stdout
    for extra in ((), ("--no-members",)):
        gate = validate(clone, *extra)
        assert gate.returncode == 1, (extra, gate.stderr + gate.stdout)
        assert "member-uninitialized" not in gate.stderr, gate.stderr
        assert findings(gate) == expected, extra

    for finding in expected:
        typed(holder, env, finding)
    staged_and_committed(holder, env, "Write the sections back as printed")
    mended = pushed_and_cloned(holder, env, family, tmp_path, "w611/mended")
    for project in (MEMBER, OTHER):
        assert (mended / "members" / project / "project.yaml").is_file()
    assert_passes_in_every_mode(mended, 2)


#: `(set-up, what it is)`: the work tree's `.gitmodules` is not HEAD's, and
#: HEAD's gives every member's path, so a clone checks each out.
NOT_HEADS = {
    "deleted, not committed": deleted,
    "edited, not staged": edited,
    "left out by a sparse checkout": left_out,
}


@pytest.mark.parametrize("set_up", NOT_HEADS.values(), ids=NOT_HEADS)
def test_a_work_tree_copy_that_is_not_heads_is_no_finding(holder, offline,
                                                          tmp_path, set_up):
    """No misfire: the finding reads HEAD's file, which a clone reads, and
    never the work tree's. A deletion nobody committed, an edit nobody
    staged and a sparse checkout that leaves the file out are each no fact
    about what a clone gets."""
    env = isolated(offline, tmp_path)
    set_up(holder, env)

    for extra in ((), ("--no-members",)):
        result = validate(holder, *extra)
        assert result.returncode == 0, (extra, result.stderr + result.stdout)


def test_a_holder_with_no_members_is_asked_nothing(empty_holder):
    """No misfire: a holder `init` made holds no `.gitmodules` and no
    gitlink, and passes in every mode."""
    for extra in ((), ("--pins",), ("--no-members",)):
        result = validate(empty_holder, *extra)
        assert result.returncode == 0, (extra, result.stderr + result.stdout)


def test_an_untracked_copy_put_back_is_still_a_finding_until_committed(
        holder, offline, tmp_path):
    """A `.gitmodules` put back by hand, untracked: the holder's own
    checkouts still work, but HEAD, which a clone reads, holds none, so the
    finding stands until the file is committed, and the holder then
    passes."""
    env = isolated(offline, tmp_path)
    kept = (holder / GITMODULES).read_bytes()
    head_lost(holder, env)
    (holder / GITMODULES).write_bytes(kept)

    result = validate(holder, "--no-members")

    assert result.returncode == 1, result.stderr + result.stdout
    assert [finding.split(":", 1)[0] for finding in findings(result)] == [
        "FINDING member-gitmodules-absent"] * 2
    staged_and_committed(holder, env, "Put .gitmodules back")
    assert_passes_in_every_mode(holder, 2)


# --- 574/2: a gitlink recorded only at a case variant of the row's path -----

def variant_refused(path: str, commit: str, variants: list[str],
                    gitlinks: dict[str, str]) -> list[str]:
    """`member-gitlink-absent`'s lines for a row whose gitlink is recorded
    only at `variants`."""
    project = path.split("/", 1)[1]
    found = ", ".join(f"{variant} (at {gitlinks[variant]})"
                      for variant in variants)
    return [
        f"REFUSED member-gitlink-absent: no gitlink (mode 160000) recorded at "
        f"'{path}'. {project} is named in family.yaml, and this repository "
        "records its gitlink only at a case variant of that path, which "
        f"macOS and Windows hold as one directory with it: {found}. A "
        f"recursive clone checks out nothing at {path}.",
        "Remediation: the member is recorded in the wrong case. Move its "
        "gitlink to the row's path, at the commit the row pins, in the index "
        "alone, which touches no file, and commit that:",
        "    git rm -r --cached -- " + " ".join(variants),
        f"    git update-index --add --cacheinfo 160000,{commit},{path}"]


def recorded_at(root: Path, env: dict, project: str,
                *spellings: str) -> str:
    """`project`'s gitlink taken out of the index at its own path and
    recorded at each of `spellings`, then committed: index records alone,
    so no disk holds two names and the checkout does not move. Returns the
    commit it names."""
    commit = pinned(root, project)
    raw(root, env, "rm", "-q", "--cached", "--", f"members/{project}")
    for spelling in spellings:
        stage_gitlink(root, spelling, commit)
    commit_all(root, env, f"{project} recorded at {', '.join(spellings)}")
    return commit


@DISKS
@pytest.mark.parametrize("spellings", [
    ("Members/{p}",), ("MEMBERS/{p}", "Members/{p}")], ids=["one", "two"])
def test_a_gitlink_only_at_a_case_variant_is_named_and_moved_as_printed(
        holder, offline, tmp_path, ignorecase, spellings):
    """#363's item 3: HEAD records MEMBER's gitlink at `Members/IRRS` (and,
    in the second case, at `MEMBERS/IRRS` too) while its row and section say
    `members/IRRS`. The refusal names each variant with its commit and,
    since `family.py add` cannot help, prints the move: the variants out of
    the index, the gitlink in at the row's path at the pinned commit. Typed
    as printed and committed, on either disk, HEAD records the member once,
    at its own path, and the holder passes in every mode."""
    env = on_disk(isolated(offline, tmp_path), ignorecase)
    variants = sorted(spelling.format(p=MEMBER) for spelling in spellings)
    commit = recorded_at(holder, env, MEMBER, *variants)

    result = validate(holder)

    assert result.returncode == 2, result.stderr + result.stdout
    lines = result.stderr.splitlines()
    path = f"members/{MEMBER}"
    assert lines == variant_refused(path, commit, variants,
                                    dict.fromkeys(variants, commit))
    for line in lines[2:]:
        raw(holder, env, *shlex.split(line)[1:])
    commit_all(holder, env, "Move the gitlink as printed")
    listed = raw(holder, env, "ls-tree", "-r", "--name-only", "HEAD").stdout
    assert f"{path}\n".encode() in listed
    for variant in variants:
        assert f"{variant}\n".encode() not in listed
    assert_passes_in_every_mode(holder, 2)


def test_a_fresh_clone_of_a_case_variant_says_it_too(family, holder, offline,
                                                     tmp_path):
    """The same state pushed: a fresh clone names the variant, where the
    refusal named `family.py add` and nothing of `Members/`. MEMBER is the
    first row, so its gitlink is asked before any member's checkout."""
    env = isolated(offline, tmp_path)
    commit = recorded_at(holder, env, MEMBER, f"Members/{MEMBER}")
    remote = family["remotes"] / f"{NAME}.git"
    raw(holder, env, "push", "-q", str(remote), "HEAD:refs/heads/w611/case")
    clone = tmp_path / "clone"
    cloned = clone_just_pushed(remote, clone, "w611/case", recurse=False)
    assert cloned.returncode == 0, cloned.stdout + cloned.stderr

    result = validate(clone)

    assert result.returncode == 2, result.stderr + result.stdout
    variant = f"Members/{MEMBER}"
    assert result.stderr.splitlines() == variant_refused(
        f"members/{MEMBER}", commit, [variant], {variant: commit})


# --- 574/3: a hand mount's remedy commits the removal before the add ---------

@DISKS
def test_a_hand_mount_under_members_spelt_another_way_is_added_as_printed(
        family, holder, offline, tmp_path, ignorecase):
    """A gitlink at `Members/IRQS` that no row names, with its section, as a
    hand mount leaves one (index records, so no disk holds `Members/`).
    Typed as printed, the branch, the `git rm`, the commit the text says
    the removal needs, and the `add` with the org filled in mount IRQS at
    `members/IRQS` with its row, and the holder passes in every mode. With
    the removal left uncommitted, as the text said before, `add` refuses:
    HEAD still holds `Members/IRQS`."""
    env = on_disk(isolated(offline, tmp_path), ignorecase)
    raw(holder, env, "switch", "-q", "-C", "main")
    _, tip = spare_commits(family)
    hand = f"Members/{SPARE}"
    stage_gitlink(holder, hand, tip)
    data = raw(holder, env, "show", f"HEAD:{GITMODULES}").stdout + (
        f'[submodule "{hand}"]\n\tpath = {hand}\n\turl = {url(SPARE)}\n'
        .encode())
    committed_gitmodules(holder, env, data)

    result = validate(holder, "--no-members")

    assert result.returncode == 1, result.stderr + result.stdout
    gitlink = findings(result)[0]
    assert gitlink.startswith(f"FINDING member-gitlink-unnamed: {hand} ")
    assert (", and commit that removal, since family.py add refuses a path "
            "under another spelling of members/ that HEAD holds and the "
            "index no longer does, then mount it with the third, ") in gitlink
    switch, rm, add = commands(gitlink)
    raw(holder.parent, env, *shlex.split(switch)[1:])
    raw(holder, env, *shlex.split(rm)[1:])
    argv = [arg.replace("<org>", ORG) for arg in shlex.split(add)]
    assert argv[:3] == [PYTHON, "scripts/family.py", "add"], add

    def add_as_printed():
        return run_script(FAMILY, *argv[2:], "--local-remote-dir",
                          str(family["remotes"]), env=env)

    uncommitted = add_as_printed()
    assert uncommitted.returncode == 2, uncommitted.stdout + uncommitted.stderr
    assert "in HEAD and no longer in the index" in uncommitted.stderr
    commit_all(holder, env, "Take the hand mount out, as printed")
    added = add_as_printed()
    assert added.returncode == 0, added.stdout + added.stderr
    assert (holder / "members" / SPARE / "project.yaml").is_file()
    assert_passes_in_every_mode(holder, 3)
