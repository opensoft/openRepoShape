# SPDX-License-Identifier: Apache-2.0
"""`family.py bump --to` makes the checks `add` makes, and says to push an
unpushed commit first (#541).

TWO LINES OF #541 ARE HELD HERE; its riding line, an annotated tag's own id,
is held by `test_family_bump_to_a_tag.py`, and here where it meets the other
two: a refusal after the peel, and the branch a person is told to make.

THE DUPLICATE ID. `add` refuses a member whose `project.yaml` records the
`id` another row records (#330, `member-duplicate-id`): that is one project
pinned twice. `bump` read the id at `--to` and never asked, so a member whose
`project.yaml` at `--to` records another member's id was committed, exit 0,
and the holder's own `validate-family.py` then refused it under that code.
Now the dry run and the real run both refuse it, before anything moves, in
the same two lines; and the real run asks again of the id its checkout
reads, so a linked `project.yaml`, which only a checkout reads through, is
refused there and put back.

THE UNPUSHED COMMIT. `bump --to` a commit made in the member's working clone
and not pushed failed in git's own words, `fatal: reference is not a tree`,
exit 2, from the real run's checkout (and the dry run's resolve failed in
other words of git's), and neither said to push it first. Now both runs
refuse it `member-to-unknown`, naming the commit, saying no branch of the
member's remote reaches it, and saying to push it first; once it is pushed,
the same command pins it. When the member's fetch itself failed, the refusal
says so and does not claim the remote lacks the commit.

THE SAME FAMILY, RULES AND OFFLINE ENVIRONMENT as `test_family_dry_run.py`,
imported from the modules that own them: members are scaffolded into local
bare repositories, nothing is created on GitHub, a `gh` on PATH logs and
exits 97, and the operator's git configuration is a file of the test's own.
The fixture's own remotes are only ever read: a commit to push goes to a
private bare repository the test makes and points the member's mount at.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import cloned_just_pushed
from repo_shape import shell_quoted
#: The family fixture and its names, from the module that owns them.
from test_family import (  # noqa: F401
    NAME, ORG, family, manifest, validate,
)
from test_family_add_refusals import holder, offline, refusal  # noqa: F401
#: "Changes nothing", asked as bytes in the order a bump would write.
from test_family_dry_run import (
    BUMP_ORDER, assert_as_it_was, bump, commit_in_mount, isolated, pinned_at,
    state,
)
from test_family_bump_remove_rollback import (
    BUMP_PUT_BACK, assert_same, bump_undone, snapshot,
)
#: Both runs over one holder, refused alike with nothing moved; an annotated
#: tag, and the line a peel prints.
from test_family_bump_to_a_tag import annotated, both_runs, peeled_line
from test_family_member_path import MEMBER, OTHER, older, raw
#: The shell's reading of a printed line, and of a refusal's `switch`.
from test_family_printed_quoting import host_words
from test_family_tracking_branch import remedy_switch

PATH = f"members/{MEMBER}"

#: The line `project.yaml` records the member's own id on, as the scaffold
#: writes it, and the id the neighbour's row records.
OWN_ID_LINE = f'\nid: "{MEMBER.lower()}"\n'.encode("ascii")
OTHER_ID = OTHER.lower()


def records_the_neighbours_id(manifest_path: Path) -> None:
    """`manifest_path`, the member's `project.yaml`, rewritten as BYTES to
    record the neighbour's id in place of the member's own."""
    data = manifest_path.read_bytes()
    assert data.count(OWN_ID_LINE) == 1, "fixture drift: the id line"
    manifest_path.write_bytes(data.replace(
        OWN_ID_LINE, f'\nid: "{OTHER_ID}"\n'.encode("ascii")))


def duplicate_id_refusal(to: str, holder: Path) -> tuple[str, str]:
    """The two lines `bump --to <to>` is refused with when the member's
    `project.yaml` at `to` records the neighbour's id. The `remove` the
    remedy names carries `--family-root` and the holder, as `remove`
    requires (#1005)."""
    return (
        f"REFUSED member-duplicate-id: {ORG}/{MEMBER} at {to[:12]} is "
        f"already a member of {NAME} under another name: its project.yaml "
        f"there records id '{OTHER_ID}', and the row {OTHER} pins "
        f"{ORG}/{OTHER} with that id. Bumping {MEMBER} to it would pin one "
        "project twice, which `validate-family.py` refuses",
        "Remediation: a family pins each project once. Pass `--to` a commit "
        f"of {ORG}/{MEMBER} whose project.yaml records an id no other row "
        f"records. If {ORG}/{MEMBER} and {ORG}/{OTHER} are one project, "
        f"`family.py remove --family-root {shell_quoted(holder.resolve())} "
        f"--member {OTHER}` takes the other row out first. "
        "Two projects that record one id are a fault in one of their "
        "`project.yaml` files, mended in that project, not in the family.")


# --- the duplicate id --------------------------------------------------------

def test_bump_to_a_commit_recording_another_rows_id_is_refused_alike(
        holder, offline, tmp_path):
    """THE ISSUE'S FIRST LINE. The member's `project.yaml` at `--to` records
    the neighbour's id. `bump` committed it, exit 0, and the holder's own
    gate refused `member-duplicate-id`. Now both runs refuse it under that
    code, in the same two lines, before the checkout, and the holder is as
    it was and still passes its gate."""
    env = isolated(offline, tmp_path)
    to = commit_in_mount(holder, env, lambda mount: records_the_neighbours_id(
        mount / "project.yaml"))

    stderr = both_runs(holder, env, to)

    assert refusal(stderr) == duplicate_id_refusal(to, holder)
    assert validate(holder).returncode == 0
    offline.assert_left_nothing()


@pytest.mark.skipif(sys.platform == "win32",
                    reason="a symbolic link in a checkout needs privileges "
                           "on Windows that a runner does not grant")
def test_a_duplicate_id_read_through_a_linked_manifest_is_put_back(
        holder, offline, tmp_path):
    """A `project.yaml` that is a SYMLINK at `--to` is only its link text in
    the member's objects; a checkout reads through it, and the dry run
    leaves its id to the real run, as it always has. The real run asks the
    id its checkout read, which is the id the row would record: refused
    `member-duplicate-id`, and the member put back where it stood, with the
    sentence that says so: `commit_in_mount` left it detached at the pin."""
    env = isolated(offline, tmp_path)

    def link(mount: Path) -> None:
        (mount / "project.yaml").rename(mount / "manifest.yaml")
        records_the_neighbours_id(mount / "manifest.yaml")
        (mount / "project.yaml").symlink_to("manifest.yaml")

    to = commit_in_mount(holder, env, link)
    at = pinned_at(holder, env)
    before = snapshot(holder, env)

    real = bump(holder, env, to)

    assert_same(before, snapshot(holder, env), BUMP_PUT_BACK)
    assert real.returncode == 2, real.stdout + real.stderr
    assert real.stdout == ""
    said, remedy = duplicate_id_refusal(to, holder)
    assert refusal(real.stderr) == (
        f"{said}. {bump_undone(f'{PATH} checked out at {at[:12]} again')}",
        remedy)
    assert validate(holder).returncode == 0
    offline.assert_left_nothing()


def test_a_duplicate_id_behind_a_tag_is_refused_after_the_peel_line(
        holder, offline, tmp_path):
    """THE PEEL LINE ABOVE A REFUSAL. `--to` is an annotated tag of a
    commit whose `project.yaml` records the neighbour's id. Both runs peel
    it and say so, in the line that says what WOULD be pinned, then refuse
    `member-duplicate-id` for the commit the tag names, exit 2, and pin
    nothing: the holder is as it was and still passes its gate."""
    env = isolated(offline, tmp_path)
    made = commit_in_mount(holder, env, lambda mount:
                           records_the_neighbours_id(mount / "project.yaml"))
    to = annotated(holder / PATH, env, "v-duplicate", made)

    stderr = both_runs(holder, env, to, peeled_line(to, made) + "\n")

    assert refusal(stderr) == duplicate_id_refusal(made, holder)
    assert validate(holder).returncode == 0
    offline.assert_left_nothing()


# --- the branch a person is told to make -------------------------------------

def test_both_runs_name_the_branch_for_the_tag_id_as_typed(
        family, holder, offline, tmp_path):
    """On the holder's tracking branch the real run refuses
    `family-on-tracking-branch` before it fetches, so before any peel,
    naming `family/bump-<id>-<the typed id's first twelve>`. The dry run
    fetches and peels, and its hint still names that branch, not one made
    from the commit the tag names: the branch a person makes from the dry
    run is the one the real run asks for."""
    env = isolated(offline, tmp_path)
    raw(holder, env, "switch", "-q", "-C", "main")
    target = older(family)
    to = annotated(holder / PATH, env, "v-release", target)
    assert to[:12] != target[:12], "premise: the two names differ"
    switch = ["git", "-C", str(holder.resolve()), "switch", "-c",
              f"family/bump-{MEMBER.lower()}-{to[:12]}"]
    before = state(holder, env)

    dry = bump(holder, env, to, "--dry-run")
    real = bump(holder, env, to)

    assert_as_it_was(holder, env, before, BUMP_ORDER)
    assert dry.returncode == 0, dry.stdout + dry.stderr
    lines = dry.stdout.splitlines()
    assert lines[0] == peeled_line(to, target)
    at = lines.index("branch       main is the holder's tracking branch, "
                     "where a real bump refuses (family-on-tracking-branch); "
                     "make a branch first:")
    assert host_words(lines[at + 1]) == switch
    assert real.returncode == 2, real.stdout + real.stderr
    assert real.stdout == ""
    assert remedy_switch(real.stderr) == switch
    offline.assert_left_nothing()


# --- the commit not yet pushed -----------------------------------------------

def a_private_remote(holder: Path, env: dict, tmp_path: Path) -> Path:
    """A bare repository of the test's own holding the member's history, its
    `main` at the member's tip, with the member's mount pointed at it: the
    remote a person pushes to. Filled by a push from the mount, so the
    fixture's own remote is not read through its files."""
    mount = holder / PATH
    remote = tmp_path / f"{MEMBER}-private.git"
    raw(tmp_path, env, "init", "-q", "--bare", str(remote))
    raw(mount, env, "push", "-q", str(remote),
        "refs/remotes/origin/main:refs/heads/main")
    raw(mount, env, "remote", "set-url", "origin", str(remote))
    return remote


def test_bump_to_a_commit_not_pushed_says_to_push_it_first(
        holder, offline, tmp_path):
    """THE ISSUE'S SECOND LINE, IN ITS OWN FLOW. A commit is made in a
    working clone of the member and not pushed. Both runs refused it in
    git's words, the real run's `reference is not a tree`. Now both refuse
    it `member-to-unknown`, in the same two lines, naming the commit and
    saying to push it first, with nothing moved; and once it is pushed, the
    same command pins it and the holder passes its gate."""
    env = isolated(offline, tmp_path)
    remote = a_private_remote(holder, env, tmp_path)
    work = tmp_path / f"{MEMBER}-work"
    cloned_just_pushed(remote, work, "main", recurse=False, env=env)
    (work / "LOCAL.md").write_bytes(b"made here, not pushed yet\n")
    raw(work, env, "add", "--", "LOCAL.md")
    raw(work, env, "commit", "-q", "-m", "A commit only the clone has")
    made = raw(work, env, "rev-parse", "HEAD").stdout.decode("ascii").strip()

    stderr = both_runs(holder, env, made)

    assert refusal(stderr) == (
        f"REFUSED member-to-unknown: --to {made} is not a commit any branch "
        f"of {ORG}/{MEMBER} reaches: {PATH} fetched from its origin and "
        "holds no object with that id",
        f"Remediation: push it first, to a branch of {ORG}/{MEMBER}, and run "
        "the same command again. A pin the rest of the world cannot fetch is "
        "a family the rest of the world cannot bootstrap. If it is pushed, "
        "check the commit: it belongs to the member's ASSEMBLY ROOT, not to "
        "one of its legs.")
    offline.assert_left_nothing()

    raw(work, env, "push", "-q", "origin", "HEAD:refs/heads/main")
    again = bump(holder, env, made)

    assert again.returncode == 0, again.stdout + again.stderr
    row = {r["project"]: r for r in manifest(holder)["members"]}[MEMBER]
    assert row["pin"]["commit"] == made == pinned_at(holder, env)
    assert validate(holder).returncode == 0


def test_a_commit_missing_after_a_failed_fetch_is_not_called_unpushed(
        holder, offline, tmp_path):
    """The fetch fails, as for a private member with no credential, so the
    member's object store is all either run can ask. A `--to` it does not
    hold is refused `member-to-unknown` by both runs alike, after the fetch's
    own note, saying the fetch failed and that whether the remote has it is
    not known, and to push it first if it is not pushed yet."""
    env = isolated(offline, tmp_path)
    raw(holder / PATH, env, "remote", "set-url", "origin",
        str(tmp_path / "gone.git"))
    missing = "deadbeef" * 5

    stderr = both_runs(holder, env, missing)

    lines = stderr.splitlines()
    assert lines[0] == (f"  note: could not fetch {PATH} from its origin; "
                        "the commit must already be in its object store and "
                        "on a branch of its remote as last fetched")
    assert refusal("\n".join(lines[1:])) == (
        f"REFUSED member-to-unknown: --to {missing} is not a commit {PATH} "
        "holds, and its fetch from its origin failed, so whether a branch of "
        f"{ORG}/{MEMBER} reaches it is not known",
        f"Remediation: push it first, to a branch of {ORG}/{MEMBER}, if it is "
        f"not pushed yet; make {ORG}/{MEMBER} readable from here — if it is "
        "PRIVATE, check `gh auth status` or your SSH key — and run the same "
        "command again. A pin the rest of the world cannot fetch is a family "
        "the rest of the world cannot bootstrap.")
    offline.assert_left_nothing()
