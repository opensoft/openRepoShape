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

AND THE STATES BESIDE THEM that the first round's review found: a member's
gitlink held only at the conflict stages, which `remove` emptied as it
emptied a merged one (its S1); a condition of each new check that no test
held (its S2 and N5); and the variant move typed half way, or leaving a
directory on a case-sensitive disk (its N1 and N2).

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
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import appended_to_command_scope, clone_just_pushed, run_script
from repo_shape import PYTHON
#: The family fixture, its names, the offline environment and the readings
#: of a holder, imported from the modules that own them rather than rebuilt.
from test_family import (  # noqa: F401
    FAMILY, NAME, ORG, SPARE, family, manifest, validate,
)
from test_family_add_excludes import empty_holder  # noqa: F401
from test_family_add_refusals import holder, offline  # noqa: F401
from test_family_dry_run import hand_edit_digest, isolated
from test_family_member_path import MEMBER, OTHER, raw
from test_family_remove_gitmodules import (
    deleted, edited, head_paths, left_out, ran, refused_alike,
    typed_as_printed, verb_args,
)
from test_scaffold_ignored_shape_files import excluding
from test_validate_family_duplicates import EXACT, irrs_row, rewrite
from test_validate_family_unnamed_mounts import (
    codes, commands, findings, spare_commits, stage_gitlink,
    stage_unmerged_gitlink,
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
    `GIT_CONFIG_*` entry after the ones it already holds
    (`appended_to_command_scope`)."""
    return {**env, **appended_to_command_scope(
        env, [("core.ignorecase", ignorecase)])}


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
           with_url: bool = True, printed_url: str | None = None) -> str:
    """The `member-gitmodules-absent` finding for `project`'s gitlink at
    `commit`, WHOLE: its line and the commands under it. `held` is whether
    HEAD holds a `.gitmodules` at all; `with_url` whether the section to
    write has no url of its own; `printed_url` the url line's value where
    it is not `url(project)`."""
    path = f"members/{project}"
    lines = f"\n    git config -f .gitmodules submodule.{path}.path {path}"
    if with_url:
        lines += (f"\n    git config -f .gitmodules submodule.{path}.url "
                  f"{printed_url or url(project)}")
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


def test_remove_of_a_member_with_no_gitlink_is_not_this_refusal(
        family, holder, offline, tmp_path):
    """The refusal is for a member whose gitlink the index records: that is
    the unmount the commit's failure emptied. With none, the run fails at
    its first git call, which writes nothing, and the dry run says so by
    git's own words, as before; the remedy of this refusal could not help."""
    env = isolated(offline, tmp_path)
    head_lost(holder, env)
    raw(holder, env, "rm", "-q", "--cached", "--", f"members/{MEMBER}")
    commit_all(holder, env, "MEMBER's gitlink taken out")

    dry = run_script(FAMILY, *verb_args("remove", holder, family),
                     "--dry-run", env=env)

    assert dry.returncode == 2, dry.stdout + dry.stderr
    assert "member-gitmodules-absent" not in dry.stderr, dry.stderr
    assert "did not match any file(s) known to git" in dry.stderr


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


def test_remove_refuses_it_where_the_members_gitlink_is_unmerged(
        family, holder, offline, tmp_path):
    """THE REVIEW'S S1: HEAD lost `.gitmodules`, and MEMBER's gitlink is held
    only at the conflict stages 1, 2 and 3 (`stage_unmerged_gitlink`).
    `deinit` and `git rm` run on an unmerged gitlink as on a merged one, so
    while the refusal asked only for one at stage 0, the dry run exited 0
    and the real run emptied the mount and died at its commit. Both refuse
    now, with the holder byte for byte as it was, the mount's files and the
    three stages included. Typed as printed, the remedy writes both
    sections back, and `remove` then commits."""
    env = isolated(offline, tmp_path)
    head_lost(holder, env)
    path = f"members/{MEMBER}"
    stage_unmerged_gitlink(holder, path, pinned(holder, MEMBER))
    listed = raw(holder, env, "ls-files", "-s", "--", path).stdout
    assert [line.split()[2] for line in listed.splitlines()] == [
        b"1", b"2", b"3"], "premise: unmerged, no stage 0"
    args = verb_args("remove", holder, family)

    said, remediation = refused_alike(holder, env, args)

    assert said == REMOVE_REFUSED.format(member=MEMBER)
    assert remediation == remove_remedy(MEMBER, OTHER)
    assert (holder / path / "project.yaml").is_file()
    typed_as_printed(holder, env, remediation)
    ran(holder, env, args)
    assert head_paths(holder, env) == [f"members/{OTHER}"]
    assert_passes_in_every_mode(holder, 1)


def test_removes_remedy_names_only_members_whose_gitlink_is_indexed(
        family, holder, offline, tmp_path):
    """The remedy writes back the section of each member whose gitlink the
    index records, and of no other. OTHER's gitlink taken out and its row
    left: a section for it would register a path the holder records
    nothing at, so the remedy writes MEMBER's section alone."""
    env = isolated(offline, tmp_path)
    head_lost(holder, env)
    raw(holder, env, "rm", "-q", "--cached", "--", f"members/{OTHER}")
    commit_all(holder, env, "OTHER's gitlink taken out")

    said, remediation = refused_alike(holder, env,
                                      verb_args("remove", holder, family))

    assert said == REMOVE_REFUSED.format(member=MEMBER)
    assert remediation == remove_remedy(MEMBER)


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


def test_a_row_the_gitlink_checks_do_not_read_is_asked_nothing(
        holder, offline, tmp_path):
    """The rows `_check_member` reads at their path, and no other, in a
    holder whose HEAD lost `.gitmodules`. OTHER's gitlink taken out too: a
    row with no gitlink is `member-gitlink-absent`'s, members checked.
    MEMBER's row given another `path:` by hand: that row is `member-path`'s,
    and its mount `member-gitlink-unnamed`'s."""
    env = isolated(offline, tmp_path)
    head_lost(holder, env)
    raw(holder, env, "rm", "-q", "--cached", "--", f"members/{OTHER}")
    commit_all(holder, env, "OTHER's gitlink taken out")
    rows = (holder / "family.yaml").read_bytes()
    line = f"    path: members/{MEMBER}\n".encode()
    assert rows.count(line) == 1, "fixture drift: MEMBER's path line"
    (holder / "family.yaml").write_bytes(rows.replace(
        line, f"    path: members/{MEMBER}-moved\n".encode()))

    result = validate(holder, "--no-members")

    assert result.returncode == 1, result.stderr + result.stdout
    assert "member-gitlink-unnamed" in result.stderr, result.stderr
    assert "member-gitmodules-absent" not in result.stderr, result.stderr


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


@pytest.mark.parametrize("extra", [(), ("--pins",)],
                         ids=["members-checked", "pins"])
def test_a_checked_out_member_it_names_still_has_its_tree_checked(
        holder, offline, tmp_path, extra):
    """Only a member it names that is NOT checked out stops after its
    gitlink. One that is checked out is asked its tree as before: MEMBER's
    digest edited by hand, in a holder whose HEAD lost `.gitmodules`, is
    `member-digest-mismatch` beside the two `member-gitmodules-absent`."""
    env = isolated(offline, tmp_path)
    head_lost(holder, env)
    hand_edit_digest(holder, env)

    result = validate(holder, *extra)

    assert result.returncode == 1, result.stderr + result.stdout
    assert codes(result) == ["member-gitmodules-absent"] * 2 + [
        "member-digest-mismatch"]
    assert findings(result)[2].startswith(
        f"FINDING member-digest-mismatch: {MEMBER}: pin.tree_sha256 "
        f"{'b' * 64}\n"), result.stderr


@MODES
def test_a_head_gitmodules_git_cannot_read_is_refused(holder, offline,
                                                      tmp_path, extra):
    """HEAD's `.gitmodules` committed broken, the work tree's mended and not
    committed. A clone reads HEAD's, which git cannot read either, so the
    gate refuses `gitmodules-unreadable` in every mode, saying to commit the
    mended file, and never reads the broken file as one that gives no
    section. Committed, the holder passes."""
    env = isolated(offline, tmp_path)
    mended = (holder / GITMODULES).read_bytes()
    committed_gitmodules(holder, env,
                         f'[submodule "members/{MEMBER}"\n\tpath = x\n'
                         .encode("utf-8"))
    (holder / GITMODULES).write_bytes(mended)

    result = validate(holder, *extra)

    assert result.returncode == 2, result.stderr + result.stdout
    lines = result.stderr.splitlines()
    assert lines[0].startswith(
        "REFUSED gitmodules-unreadable: HEAD's .gitmodules could not be read "
        "as git reads it: `git config -z --blob "), result.stderr
    assert lines[-1] == (
        "Remediation: git cannot read it either, so none of this holder's "
        "submodules can be cloned from it. Mend the file by hand (`git config "
        "-f .gitmodules --list` says where it breaks), commit it, then run "
        "this again.")
    staged_and_committed(holder, env, "Commit the mended .gitmodules")
    assert_passes_in_every_mode(holder, 2)


def test_a_repository_not_org_and_name_prints_the_url_placeholder(
        holder, offline, tmp_path):
    """The url line gives `https://github.com/<repository>.git`, the url
    `family.py add` writes, only where the row's `repository:` is
    `<org>/<Name>`. From any other value that would be a url nobody chose,
    so the line prints `<url>` for the person to fill in."""
    env = isolated(offline, tmp_path)
    head_lost(holder, env)
    rows = (holder / "family.yaml").read_bytes()
    line = f"    repository: {ORG}/{MEMBER}\n".encode("utf-8")
    assert rows.count(line) == 1, "fixture drift: MEMBER's repository line"
    (holder / "family.yaml").write_bytes(rows.replace(
        line, f"    repository: {MEMBER}\n".encode("utf-8")))

    result = validate(holder, "--no-members")

    assert result.returncode == 1, result.stderr + result.stdout
    assert findings(result) == [
        absent(MEMBER, pinned(holder, MEMBER), held=False,
               printed_url="<url>"),
        absent(OTHER, pinned(holder, OTHER), held=False)]


def test_a_row_written_twice_is_one_finding_per_path(holder, offline,
                                                     tmp_path):
    """MEMBER's row written twice in a holder whose HEAD lost `.gitmodules`:
    `member-duplicate` once, and `member-gitmodules-absent` once per path,
    not once per row."""
    env = isolated(offline, tmp_path)
    head_lost(holder, env)
    row = irrs_row(holder)
    assert row["project"] == MEMBER, "fixture drift: MEMBER is IRRS"
    other = next(r for r in manifest(holder)["members"]
                 if r["project"] == OTHER)
    rewrite(holder, [row, dict(row), other])

    result = validate(holder, "--no-members")

    assert result.returncode == 1, result.stderr + result.stdout
    assert findings(result) == [
        EXACT,
        absent(MEMBER, pinned(holder, MEMBER), held=False),
        absent(OTHER, pinned(holder, OTHER), held=False)]


# --- 574/2: a gitlink recorded only at a case variant of the row's path -----

def variant_refused(path: str, commit: str, variants: list[str],
                    gitlinks: dict[str, str], *, sparse: tuple = (),
                    aside: str = "", section: tuple = (),
                    section_said: str = "") -> list[str]:
    """`member-gitlink-absent`'s lines for a row whose gitlink is recorded
    only at `variants`. What the move meets beside them (#762): `sparse`,
    the variants a sparse checkout keeps off disk; `aside`, the sentence
    for an entry in the way; and `section`, the lines that make
    `.gitmodules` give `path`, with `section_said`, what they do."""
    project = path.split("/", 1)[1]
    found = ", ".join(f"{variant} (at {gitlinks[variant]})"
                      for variant in variants)
    moved = " and ".join(f"`[ {variant} -ef {path} ] || [ -e {variant}/.git ] "
                         f"|| mv -- {variant} ../{variant.replace('/', '-')}`"
                         for variant in variants)
    status = " or ".join(f"`git -C {variant} status`" for variant in variants)
    unpushed = " or ".join(f"`git -C {variant} log --oneline HEAD --branches "
                           "--not --remotes`" for variant in variants)
    return [
        f"REFUSED member-gitlink-absent: no gitlink (mode 160000) recorded at "
        f"'{path}'. {project} is named in family.yaml, and this repository "
        "records its gitlink only at a case variant of that path, which "
        f"macOS and Windows hold as one directory with it: {found}. A "
        f"recursive clone checks out nothing at {path}.",
        "Remediation: the member is recorded in the wrong case. "
        + aside + ("Then move" if aside else "Move") + " its gitlink to the "
        "row's path, at the commit the row pins, in the index alone, which "
        "touches no file, with the "
        + ("first two lines below" if section else "two lines below")
        + (" (the first with --sparse, which needs git 2.34 or later: a "
           f"sparse checkout keeps {' and '.join(sparse)} off disk, and "
           "without it git rm passes over what that keeps off disk, exit 0, "
           "and removes nothing)" if sparse else "")
        + (f"; the lines after them {section_said}, and stage .gitmodules. "
           "Commit that." if section else ", and commit that.")
        + " A directory left at "
        f"{' or '.join(variants)} is the "
        "row's own where the disk folds case, as macOS's and Windows' "
        "usually do and a Linux mount can (WSL's /mnt/c). Where the disk "
        "holds the two apart it stays there, untracked, and family.py add "
        "refuses it as family-members-dir-variant: move each one that is "
        f"there out of the holder, in a POSIX shell, {moved}, which moves "
        "nothing where the two names are one directory or where it holds a "
        ".git entry, a checkout. A checkout git submodule add made holds a "
        ".git file naming its store by a path relative to it, which a move "
        "would leave pointing nowhere. Its commits are kept under this "
        "holder's .git/modules/, in the directory its .git file names, "
        "whatever becomes of the checkout, and only what is not committed is "
        f"in the checkout alone ({status} shows it, except where a plain mv "
        "brought the checkout to that path: git cannot open it there, so "
        "check its files by hand). Delete such a checkout by hand once "
        "nothing only it holds is needed. A checkout whose .git is a "
        "directory, a clone of its own, holds its commits there and nowhere "
        f"else, and {unpushed} lists the ones not pushed: move it out of the "
        "holder whole, by hand, rather than delete it. Then, where nothing is "
        f"checked out at {path}, as in a fresh clone, `git submodule update "
        "--init --recursive` checks the member out there. Run it last: a "
        "checkout git mv moved to a variant names the member's own store, "
        f"which that update points at {path}, so {status} reads {path} after "
        "it. The " + ("lines" if section else "two lines") + ":",
        "    git rm -r --cached" + (" --sparse" if sparse else "")
        + " --ignore-unmatch -- " + " ".join(variants),
        f"    git update-index --add --cacheinfo 160000,{commit},{path}",
        *(f"    {line}" for line in section)]


def refused_at(root: Path, commit: str, variants: list[str]) -> list[str]:
    """The members-checked gate in `root`, where MEMBER's gitlink is recorded
    only at `variants`, at `commit`: exit 2, in `variant_refused`'s lines,
    which it returns."""
    result = validate(root)
    assert result.returncode == 2, result.stderr + result.stdout
    lines = result.stderr.splitlines()
    assert lines == variant_refused(f"members/{MEMBER}", commit, variants,
                                    dict.fromkeys(variants, commit))
    return lines


def moved_as_printed(root: Path, env: dict, lines: list[str],
                     variants: list[str]) -> None:
    """The refusal's two command lines typed as printed, and the commit it
    says to make: HEAD then records MEMBER once, at its own path, and at
    none of `variants`."""
    for line in lines[2:]:
        raw(root, env, *shlex.split(line)[1:])
    commit_all(root, env, "Move the gitlink as printed")
    listed = raw(root, env, "ls-tree", "-r", "--name-only", "HEAD").stdout
    assert f"members/{MEMBER}\n".encode() in listed
    for variant in variants:
        assert f"{variant}\n".encode() not in listed


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

    lines = refused_at(holder, commit, variants)

    moved_as_printed(holder, env, lines, variants)
    assert_passes_in_every_mode(holder, 2)


@DISKS
def test_a_variant_whose_removal_is_staged_is_moved_as_printed(
        holder, offline, tmp_path, ignorecase):
    """HALF REPAIRED (the review's N1): the variant's removal staged and not
    committed. HEAD still records the gitlink there, so the refusal still
    names it, and the plain `git rm -r --cached` of it failed, `pathspec
    ... did not match`. With `--ignore-unmatch` the lines typed as printed
    and committed move the gitlink, and the holder passes."""
    env = on_disk(isolated(offline, tmp_path), ignorecase)
    variant = f"Members/{MEMBER}"
    commit = recorded_at(holder, env, MEMBER, variant)
    raw(holder, env, "rm", "-q", "--cached", "--", variant)

    lines = refused_at(holder, commit, [variant])

    moved_as_printed(holder, env, lines, [variant])
    assert_passes_in_every_mode(holder, 2)


@pytest.fixture
def case_sensitive_disk(tmp_path):
    """Skips where `Members/` and `members/` would be one directory, as
    macOS and Windows hold them by default (nothing is left behind there to
    move), or where there is no `mv` to type."""
    (tmp_path / "CaseProbe").mkdir()
    if (tmp_path / "caseprobe").exists():
        pytest.skip("this disk is case-insensitive: Members/IRRS is "
                    "members/IRRS here, so no second directory can exist")
    if shutil.which("mv") is None:
        pytest.skip("no mv on PATH to type the printed line with")


#: The guarded `mv` the variant refusal gives for each variant, backticked:
#: two shell tests, then the move (#681).
GUARDED_MOVE = re.compile(r"`(\[ [^`]* \|\| mv -- [^`]*)`")


def typed_in_sh(root: Path, line: str) -> subprocess.CompletedProcess:
    """`line` typed as printed, in a POSIX shell standing in `root`."""
    return subprocess.run(["sh", "-c", line], cwd=str(root),
                          capture_output=True, check=False)


def test_a_variant_directory_left_on_disk_is_moved_out_as_printed(
        family, holder, offline, tmp_path, case_sensitive_disk):
    """THE REVIEW'S N2, in its C3 layout: MEMBER's gitlink recorded only at
    `Members/IRRS`, its checkout still at `members/IRRS`, and a second
    directory at `Members/IRRS` holding the member's files, as a
    case-sensitive disk can hold. The index move leaves that directory on
    disk, untracked, where `family.py add` refused any other member past it
    (`family-members-dir-variant`). Every line the refusal prints, typed as
    printed: the two lines, their commit, and the guarded `mv`, in a POSIX
    shell. A plain directory, apart from the row's and with no `.git`
    entry, is moved out (a checkout is not since #681:
    `tests/test_validate_family_remedies_typed.py`). The gate then passes
    in every mode, and SPARE is added."""
    env = isolated(offline, tmp_path)
    variant = f"Members/{MEMBER}"
    commit = recorded_at(holder, env, MEMBER, variant)
    (holder / variant).mkdir(parents=True)
    (holder / variant / "project.yaml").write_bytes(
        (holder / "members" / MEMBER / "project.yaml").read_bytes())

    lines = refused_at(holder, commit, [variant])

    moved_as_printed(holder, env, lines, [variant])
    (move,) = GUARDED_MOVE.findall(lines[1])
    typed = typed_in_sh(holder, move)
    assert typed.returncode == 0, typed.stderr
    assert not (holder / variant).exists()
    assert (tmp_path / f"Members-{MEMBER}" / "project.yaml").is_file()
    assert_passes_in_every_mode(holder, 2)
    added = run_script(FAMILY, *verb_args("add", holder, family), env=env)
    assert added.returncode == 0, added.stdout + added.stderr
    assert_passes_in_every_mode(holder, 3)


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

    refused_at(clone, commit, [f"Members/{MEMBER}"])


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
