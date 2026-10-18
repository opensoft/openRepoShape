# SPDX-License-Identifier: Apache-2.0
"""`family.py add` checks its own commit for the gitlink at exactly
`members/<Project>`, and finds a `members:` line spelled as any null the
holder's reader reads (#920).

THE COMMIT, AFTER THE FACT (#459's U049, #363's option 2, which PR #574 left
out). #574 refuses each known cause of a misplaced gitlink, another spelling
of `members/` in the index, in HEAD or on disk, before the mount, and nothing
asked the commit afterwards: a cause nobody foresaw would commit the gitlink
somewhere else with exit 0, and a fresh clone would leave the member empty.
Each test here makes such a commit: #363's own state, with #574's refusal
switched off in process so that git itself chooses the path, or a
`pre-commit` hook that moves the gitlink or takes it out. `add` must take its
commit back, unwind the mount as every refusal after the mount does, name
the path git chose, and never take back a commit it did not make.

THE `members:` LINE (#459's U188, RV870's NIT-3). `add`'s finder took only
`members:` and `members: []`, so a holder whose `family.yaml` said `members:
null`, which its own gate reads as no members, was refused as having no
`members:` line at all. One test per spelling of null the reader reads, a
control for `members: []`, and the rule that only a line at the margin is
the manifest's own `members:`.

THE SAME FAMILY AS `test_family.py`, and the same offline rules as
`test_family_add_refusals.py`, whose fixtures and helpers these are.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from conftest import git
#: The family fixture and its names, imported from the module that owns
#: them; importing a fixture gives this module its own instance of it.
from test_family import (  # noqa: F401
    ORG, SPARE, family, holder, manifest,
)
#: The offline environment, the in-process module, and the holder's
#: snapshot, from the module that tests every other refusal after the mount.
from test_family_add_refusals import (  # noqa: F401
    UNDONE, add_in_process, assert_unchanged, family_module, offline, plant,
    refusal, snapshot, unborn_holder,
)
#: A `members:` line in place of the fixture's block, committed, from the
#: module that reads every other spelling of it (#864).
from test_family_members_not_a_list import members_are

#: `add`'s mount path for the spare member.
MOUNT = f"members/{SPARE}"

#: What `member-gitlink-misplaced` tells the human to do, before its last
#: words, which say whether the commit was taken back.
MISPLACED_REMEDIATION = (
    "Remediation: `add` asks git for the gitlink at `members/<Project>` and "
    "nowhere else, and every cause known to record it elsewhere, another "
    "spelling of `members/` in the index, in HEAD or on disk, is refused "
    "before the mount, so this cause is not one of them. Find what moved it, "
    "such as a hook or a setting like `core.ignorecase`, and mend that")

#: Its last words where the commit was taken back.
TAKEN_BACK = ", then run the same command again."

#: Its last words where it was not.
NOT_TAKEN_BACK = (
    ". The commit and the mount are still there, for the reason above: `git "
    "log` shows what the branch holds, and taking them out is yours to do "
    "before you run the same command again.")

#: What the unwind puts back after a commit is taken back in a holder that
#: has members, so a `.gitmodules`, in `undo`'s order: the pin was written,
#: so `family.yaml` is restored as well as everything the mount made.
UNWOUND = UNDONE.format(
    restored=f"the gitlink at {MOUNT} unstaged, {MOUNT} removed, "
             f".git/modules/{MOUNT} removed, .gitmodules restored byte for "
             "byte, family.yaml restored byte for byte, "
             f"`submodule.{MOUNT}` dropped from the holder's git config")

#: What the refused commit's sha is read back out of.
MADE_RE = re.compile(r"REFUSED member-gitlink-misplaced: the commit "
                     r"([0-9a-f]{12}) records ")

#: Two `pre-commit` hooks, each a cause `add` cannot know before the mount,
#: with what the refusal says the commit records: one takes the member's
#: gitlink out of the commit, and one records it at `parked/<Project>`.
#: git runs the hook on the index it commits, and reads that index again
#: after it, so what the hook stages is what the commit holds.
HOOKS = {
    "takes it out": (
        f"git rm -q --cached -- {MOUNT}\n",
        f"no new gitlink, at `{MOUNT}` or anywhere else"),
    "moves it": (
        f"sha=$(git rev-parse :{MOUNT}) || exit 1\n"
        f"git rm -q --cached -- {MOUNT}\n"
        f'git update-index --add --cacheinfo "160000,$sha,parked/{SPARE}"\n',
        f"{SPARE}'s gitlink at `parked/{SPARE}`, not at `{MOUNT}`"),
}

#: A hook is a `#!/bin/sh` file git runs, which git for Windows runs only
#: through its own shell; the POSIX runs prove the rule.
POSIX_HOOKS = pytest.mark.skipif(sys.platform == "win32",
                                 reason="a #!/bin/sh hook")


def head(root: Path) -> str:
    return git("rev-parse", "HEAD", cwd=root).stdout.strip()


def misplaced(made: str, where: str) -> str:
    """The start of the REFUSED line for the commit `made`, which records
    `where`, up to the sentence saying whether it was taken back."""
    return (f"REFUSED member-gitlink-misplaced: the commit {made} records "
            f"{where}, while .gitmodules and family.yaml name `{MOUNT}`, so "
            "a fresh clone would leave the member empty.")


def made_of(stderr: str) -> str:
    """The twelve characters of the commit the refusal names."""
    found = MADE_RE.match(stderr)
    assert found is not None, stderr
    return found.group(1)


def gitlinks(root: Path, commit: str) -> list[str]:
    """The path of every gitlink `commit` records, as `git ls-tree -r`
    lists them."""
    return [line.partition("\t")[2] for line in git(
        "ls-tree", "-r", commit, cwd=root).stdout.splitlines()
        if line.startswith("160000 ")]


def hooked(root: Path, tmp_path: Path, name: str, body: str) -> None:
    """The hook `name` running `body`, in a hooks folder of the test's own
    that the holder's own config names (`core.hooksPath`), so neither the
    operator's global setting nor `.git/hooks` decides where git looks."""
    hooks = tmp_path / "hooks"
    hooks.mkdir(exist_ok=True)
    (hooks / name).write_text("#!/bin/sh\n" + body, encoding="utf-8")
    (hooks / name).chmod(0o755)
    git("config", "--local", "core.hooksPath", hooks.as_posix(), cwd=root)


# --- the commit, after the fact (U049) ---------------------------------------

def test_363s_own_state_is_taken_back_naming_the_path_git_chose(
        family, holder, offline, family_module, monkeypatch, capsys):
    """#363, AS IT WAS MEASURED. HEAD holds `Members/README.md`, an
    uncommitted `git rm` has taken it out of the index, and `core.ignorecase`
    is set: git commits the new gitlink in the spelling HEAD gives the
    folder, `Members/IRQS`, while `.gitmodules` and `family.yaml` say
    `members/IRQS`. #574 refuses that state before the mount
    (`_members_spellings`), so its refusal is switched off here, in process,
    to make git choose a path nothing refused. The commit is taken back, the
    mount unwound, and the holder is the one the snapshot recorded, the
    human's staged `git rm` included. The path the refusal names is the
    one the commit it took back records."""
    plant(holder, "100644", "Members/README.md")
    git("commit", "-q", "-m", "A folder in another spelling", cwd=holder)
    git("rm", "-r", "-q", "--cached", "--", "Members", cwd=holder)
    git("config", "--local", "core.ignorecase", "true", cwd=holder)
    monkeypatch.setattr(family_module, "_members_spellings",
                        lambda root, project, on_disk, rows: [])
    was = head(holder)
    before = snapshot(holder)
    assert before["status"] == "D  Members/README.md\n"

    code = add_in_process(family_module, monkeypatch, offline, holder, SPARE,
                          family["remotes"])
    out, err = capsys.readouterr()
    assert code == 2, out + err
    assert out == (f"checking {ORG}/{SPARE} before mounting it\n"
                   f"mounting {ORG}/{SPARE} at {MOUNT}\n")
    made = made_of(err)
    assert refusal(err) == (
        misplaced(made, f"{SPARE}'s gitlink at `Members/{SPARE}`, not at "
                        f"`{MOUNT}`")
        + f" It has been taken back: the branch names {was[:12]} again. "
        + UNWOUND, MISPLACED_REMEDIATION + TAKEN_BACK)
    assert git("rev-parse", f"{made}^", cwd=holder).stdout.strip() == was
    assert sorted(gitlinks(holder, made)) == sorted(
        [f"Members/{SPARE}", *gitlinks(holder, was)])
    assert snapshot(holder) == before
    assert not (holder / MOUNT).exists()
    offline.assert_left_nothing()


@POSIX_HOOKS
@pytest.mark.parametrize("hook", list(HOOKS))
def test_a_commit_a_hook_moved_the_gitlink_in_is_taken_back(
        family, holder, offline, tmp_path, hook):
    """A CAUSE NOBODY FORESAW, through the real command: a `pre-commit` hook
    takes the gitlink out of the commit, or records it at `parked/IRQS`.
    `add` exited 0 for both, leaving the branch on a commit whose
    `.gitmodules` and `family.yaml` name a gitlink it does not hold there.
    Now the commit is taken back and the holder is exactly as it was."""
    body, where = HOOKS[hook]
    hooked(holder, tmp_path, "pre-commit", body)
    was = head(holder)
    before = snapshot(holder)

    result = offline.add(holder, SPARE, remotes=family["remotes"])
    assert result.returncode == 2, result.stdout + result.stderr
    assert refusal(result.stderr) == (
        misplaced(made_of(result.stderr), where)
        + f" It has been taken back: the branch names {was[:12]} again. "
        + UNWOUND, MISPLACED_REMEDIATION + TAKEN_BACK)
    assert_unchanged(holder, before, SPARE)
    offline.assert_left_nothing()


@POSIX_HOOKS
def test_a_commit_the_branch_has_moved_on_from_is_never_taken_back(
        family, holder, offline, tmp_path):
    """ONLY THIS COMMAND'S ONE COMMIT IS TAKEN BACK. A `post-commit` hook
    puts a commit of its own on the branch after `add`'s, so HEAD names a
    commit that is not one commit on where `add` found the branch. Taking
    it back would lose the hook's commit too, so nothing is taken back and
    nothing undone, the refusal says why, and the remedy leaves the commit
    and the mount to the human."""
    hooked(holder, tmp_path, "pre-commit", HOOKS["takes it out"][0])
    hooked(holder, tmp_path, "post-commit",
           'git update-ref HEAD "$(git commit-tree -p HEAD '
           '-m "a commit a hook made" "HEAD^{tree}")"\n')
    was = head(holder)

    result = offline.add(holder, SPARE, remotes=family["remotes"])
    assert result.returncode == 2, result.stdout + result.stderr
    now = head(holder)
    assert git("log", "-1", "--format=%s", cwd=holder).stdout == (
        "a commit a hook made\n")
    assert git("rev-parse", "HEAD~2", cwd=holder).stdout.strip() == was
    assert refusal(result.stderr) == (
        misplaced(now[:12], HOOKS["takes it out"][1])
        + f" It was NOT taken back: {now[:12]} is not one commit on "
        f"{was[:12]}, where this command found the branch, and this tool "
        "takes back no commit it did not make. The commit had already "
        "landed, so nothing was undone: `git log -1` in the holder shows it.",
        MISPLACED_REMEDIATION + NOT_TAKEN_BACK)
    assert (holder / MOUNT / "project.yaml").is_file()
    offline.assert_left_nothing()


def test_take_back_moves_no_branch_that_names_another_commit(holder,
                                                             family_module):
    """THE VALUE `git update-ref` MUST FIND. `take_back` is handed a commit
    that is one commit on where the rollback found the branch, but the
    branch names another one by then. git is given the commit to take back
    as the value the branch must hold, so it refuses, the branch is left on
    the other commit, and the sentence quotes git."""
    was = head(holder)
    rollback = family_module.MountRollback(holder, MOUNT)
    tree = git("rev-parse", "HEAD^{tree}", cwd=holder).stdout.strip()
    made = git("commit-tree", "-p", was, "-m", "this command's", tree,
               cwd=holder).stdout.strip()
    other = git("commit-tree", "-p", was, "-m", "anybody else's", tree,
                cwd=holder).stdout.strip()
    git("update-ref", "HEAD", other, cwd=holder)

    taken, said = rollback.take_back(made)
    assert taken is False
    assert said.startswith(
        " It was NOT taken back: `git update-ref -m family.py add: "
        f"{made[:12]} taken back HEAD {was} {made}` in "), said
    assert head(holder) == other


@POSIX_HOOKS
def test_a_first_commit_is_taken_back_to_a_branch_with_none(family, offline,
                                                            tmp_path):
    """A HOLDER WITH NO COMMIT YET gets `add`'s root commit (#203). Where
    that commit holds no gitlink at the mount path, the branch is deleted
    again, which is what it was, and the holder is unwound to the
    untracked `family.yaml` the human left."""
    root = unborn_holder(tmp_path)
    hooked(root, tmp_path, "pre-commit", HOOKS["takes it out"][0])
    before = snapshot(root)
    assert before["HEAD"] == ""

    result = offline.add(root, SPARE, remotes=family["remotes"])
    assert result.returncode == 2, result.stdout + result.stderr
    assert refusal(result.stderr) == (
        misplaced(made_of(result.stderr), HOOKS["takes it out"][1])
        + " It has been taken back: the branch has no commit again. "
        + UNDONE.format(
            restored=f"the gitlink at {MOUNT} unstaged, {MOUNT} removed, "
                     f".git/modules/{MOUNT} removed, .gitmodules removed, as "
                     "there was none before, family.yaml restored byte for "
                     f"byte, `submodule.{MOUNT}` dropped from the holder's "
                     "git config"), MISPLACED_REMEDIATION + TAKEN_BACK)
    assert snapshot(root) == before
    assert git("symbolic-ref", "HEAD", cwd=root).stdout == (
        "refs/heads/family/unborn\n")
    offline.assert_left_nothing()


# --- the `members:` line (U188) ----------------------------------------------

#: `(the value after members:, what the holder's reader reads it as)`:
#: each spelling of null the reader reads (`repo_shape._scalar`), and then
#: `[]`, the control, found before #920 too. A comment after the value is
#: still a hand edit `add` refuses
#: (`test_a_manifest_this_tool_will_not_rewrite_is_refused_before_the_mount`).
SPELLINGS = [
    pytest.param("null", None, id="null"),
    pytest.param("Null", None, id="Null"),
    pytest.param("NULL", None, id="NULL"),
    pytest.param("~", None, id="tilde"),
    pytest.param("[]", [], id="control-empty-list"),
]


@pytest.mark.parametrize("value,read", SPELLINGS)
def test_the_first_member_is_written_under_any_members_line_read_as_none(
        family, holder, offline, value, read):
    """RV870's NIT-3. The holder's reader, and so its own gate, reads each
    of these as no members, and `add` refused every one but `[]` as having
    no `members:` line at all (`family-members-unrecognised`), writing
    nothing. Now the line is found and rewritten as `members:` with the one
    row under it, and nothing above it moves. The fixture's two mounts stay
    as they are, unnamed by any row, as `test_family_members_not_a_list.py`
    leaves them for its own controls."""
    members_are(holder, value)
    assert manifest(holder)["members"] == read
    kept = (holder / "family.yaml").read_text(encoding="utf-8").partition(
        "\nmembers:")[0]
    was = head(holder)

    result = offline.add(holder, SPARE, remotes=family["remotes"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""
    text = (holder / "family.yaml").read_text(encoding="utf-8")
    assert text.startswith(f"{kept}\nmembers:\n  - project: {SPARE}\n")
    assert [row["project"] for row in manifest(holder)["members"]] == [SPARE]
    assert git("rev-parse", "HEAD~1", cwd=holder).stdout.strip() == was
    assert git("show", "--name-only", "--format=", "HEAD",
               cwd=holder).stdout.split() == [".gitmodules", "family.yaml",
                                              MOUNT]
    assert git("status", "--porcelain", cwd=holder).stdout == ""
    offline.assert_left_nothing()


def test_an_indented_members_null_is_never_the_members_line(tmp_path,
                                                           family_module):
    """AT THE MARGIN ONLY. The reader reads `  members: null` alone as it
    reads `members: null`, but in the file it is a key of another mapping.
    Rewritten with no rows, a manifest that holds one above its own
    `members: []` comes back byte for byte, the indented line kept."""
    text = ("kind: family-manifest\nnotes:\n  members: null\n"
            "members: []\n")
    (tmp_path / "family.yaml").write_text(text, encoding="utf-8")
    held = family_module.Family(tmp_path, {"members": []})
    assert held.rewritten([]) == text


@pytest.mark.parametrize("line", ["members: ~  # no member yet",
                                  "members:  null"])
def test_a_null_with_more_than_one_word_is_still_a_hand_edit(
        tmp_path, family_module, line):
    """ONE WORD, AS `members:` AND `members: []` ARE TAKEN. The reader reads
    a comment after the null, or a second space before it, the same way,
    but the line is rewritten whole and a comment on it would be dropped:
    it is refused as the hand edit it always was, and nothing is
    rewritten."""
    (tmp_path / "family.yaml").write_text(
        f"kind: family-manifest\n{line}\n", encoding="utf-8")
    held = family_module.Family(tmp_path, {"members": None})
    with pytest.raises(family_module.Refusal) as caught:
        held.rewritten([])
    assert caught.value.code == "family-members-unrecognised"
