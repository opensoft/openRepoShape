# SPDX-License-Identifier: Apache-2.0
"""The NEXT push line names its branch by its full refname, and a tracking
branch the disk cannot hold is refused before anything exists (#689).

THE PUSH LINE. `family.py add`, `bump` and `remove` each end with ONE line
that pushes the branch the commit is on, and it spelled the branch bare:
`git -C <holder> push -u origin <branch>`. A bare name is a refspec git reads
for itself, so, measured on main at d4a7fab:

  * a holder on `+x` (a name `git check-ref-format --branch` accepts) printed
    `push -u origin +x`, a FORCED refspec for the LOCAL branch `x`. With an
    older local `x` and somebody's commit on origin's `x`, pasting it said
    `+ ...  x -> x (forced update)` and overwrote origin's `x`, and the commit
    the act made was never pushed; with no local `x`, `src refspec x does not
    match any`;
  * a branch that shares its name with a tag (`v1`) died `src refspec v1
    matches more than one`, exit 1.

It is `refs/heads/<branch>:refs/heads/<branch>` now, one word the way the
shell reads it. Every case here runs the line as printed, against a bare
repository of the test's own, and holds the OLD spelling to the failure the
issue measured, so the test cannot pass on a git that reads a bare name
another way.

THE LENGTH. `git check-ref-format` has no length limit, and `checked_value`
allows 255 characters, so a tracking branch of 251 to 255 passed
`--dry-run`, and the real run died at the first commit with every remote
made: `fatal: cannot lock ref 'HEAD': Unable to create '.../refs/heads/aaa
....lock': File name too long`. Git locks a branch by making
`refs/heads/<last part>.lock`, so the last part of the name may be at most
250 bytes and any other 255. `shape_materialize.refuse_bad_branch`, the one
helper `scaffold-project.py`, `family.py init` and `adopt-project.py` ask,
refuses it before anything exists, `--dry-run` too. Where this disk makes the
name, git is held to the same rows.

THE SAME FAMILY AS `tests/test_family.py`, in `on_main`'s private copy of the
holder on its tracking branch, its `origin` made over to a bare repository
of the test's own so no other test sees a branch pushed here.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import REPO, findings, git, write_plan
from test_adopt_branch_names import TRACKING_KEY, with_branch, world  # noqa: F401
from test_family import family, family_module, validate  # noqa: F401
from test_family_printed_quoting import host_words
from test_family_tracking_branch import (  # noqa: F401
    act, next_push, on_main, refspec,
)
from test_tracking_branch_ref import (
    FAMILY_CODE, SCAFFOLD_CODE, assert_family_made_nothing,
    assert_nothing_was_made, family_init, scaffold,
)

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402
from repo_shape import Refusal  # noqa: E402

# --- the NEXT push line ------------------------------------------------------

#: `(branch, an older local x, a tag v1, what the bare name said)`: the three
#: states the issue measured, and the words git gave the line printed before.
STATES = [
    pytest.param("+x", True, False, "(forced update)", id="plus-over-a-local-x"),
    pytest.param("+x", False, False, "src refspec x does not match any",
                 id="plus-and-no-local-x"),
    pytest.param("v1", False, True, "matches more than one",
                 id="named-like-a-tag"),
]


def arranged(holder: Path, base: Path, branch: str, local_x: bool,
             tag: bool) -> tuple[Path, str]:
    """A bare `origin` of this test's own, holding the holder's `main` and
    somebody's `x` (one commit above it), made the holder's `origin`; the
    holder gets an older local `x` and a tag `v1` where asked, then stands on
    `branch`. Returns the bare repository and somebody's commit."""
    bare = base / "origin.git"
    git("init", "-q", "--bare", "-b", "main", str(bare), cwd=base)
    git("remote", "set-url", "origin", str(bare), cwd=holder)
    git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=holder)
    somebody = git("commit-tree", "-p", "HEAD", "-m", "Somebody's x",
                   "HEAD^{tree}", cwd=holder).stdout.strip()
    git("push", "-q", "origin", f"{somebody}:refs/heads/x", cwd=holder)
    if local_x:
        git("branch", "x", "HEAD", cwd=holder)
    if tag:
        git("tag", "v1", cwd=holder)
    git("switch", "-q", "-c", branch, cwd=holder)
    return bare, somebody


@pytest.mark.parametrize("verb", ["add", "bump", "remove"])
@pytest.mark.parametrize("branch, local_x, tag, old_words", STATES)
def test_the_printed_push_lands_the_branch_it_names(
        family, on_main, tmp_path, verb, branch, local_x, tag, old_words):
    """THE ISSUE'S THREE LINES, for each act. The line names the branch by
    its full refname on both sides. Typed as printed it pushes that branch,
    at the act's commit, leaves somebody's `x` alone, and sets the branch's
    upstream to itself. The line printed before, run against a copy of the
    same remote, fails or forces exactly as measured."""
    holder = on_main
    bare, somebody = arranged(holder, tmp_path, branch, local_x, tag)
    done = act(family, holder, verb)
    assert done.returncode == 0, done.stdout + done.stderr
    head = git("rev-parse", "HEAD", cwd=holder).stdout.strip()
    push, _ = next_push(done.stdout)
    assert push == ["git", "-C", str(holder), "push", "-u", "origin",
                    f"refs/heads/{branch}:refs/heads/{branch}"]

    # THE CONTROL: the bare spelling, against a copy of origin.
    copy = tmp_path / "old.git"
    shutil.copytree(bare, copy)
    old = subprocess.run([*push[:4], str(copy), branch], capture_output=True,
                         text=True, check=False)
    assert old_words in old.stderr, old.stderr
    assert git("rev-parse", "-q", "--verify", f"refs/heads/{branch}",
               cwd=copy, check=False).returncode != 0, (
        "the old line pushed the branch it named")
    if local_x:
        assert git("rev-parse", "refs/heads/x", cwd=copy).stdout.strip() \
            != somebody, "the old line did not overwrite origin's x"

    pushed = subprocess.run(push, capture_output=True, text=True, check=False)
    assert pushed.returncode == 0, pushed.stderr
    assert git("rev-parse", f"refs/heads/{branch}",
               cwd=bare).stdout.strip() == head
    assert git("rev-parse", "refs/heads/x", cwd=bare).stdout.strip() == \
        somebody, "somebody's x on origin was moved"
    assert git("config", "--get", f"branch.{branch}.merge",
               cwd=holder).stdout.strip() == f"refs/heads/{branch}"
    assert git("config", "--get", f"branch.{branch}.remote",
               cwd=holder).stdout.strip() == "origin"
    assert validate(holder).returncode == 0


@pytest.mark.parametrize("branch", [
    "+x", "v1", "family/add-irrs", "it's", "a$b;c", "lane-3/shape+fix@eagle",
    "é"])
def test_the_refspec_is_one_word_whatever_the_branch(capsys, branch):
    """The whole refspec is ONE word for the shell to read, quoted as every
    other word of the line is (#486), so a branch holding an apostrophe, a
    `$` or a `;` still reaches git as the refname it is."""
    holder = Path("/srv/my work/Sonata")
    family_module()._print_next(
        SimpleNamespace(root=holder, tracking=lambda: "main"), branch)
    (line,) = [line for line in capsys.readouterr().out.splitlines()
               if line.startswith("NEXT  ")]
    assert host_words(line[len("NEXT  "):]) == [
        "git", "-C", str(holder), "push", "-u", "origin", refspec(branch)]


# --- a branch the disk cannot hold ---------------------------------------------

A, E = "a", "é"

#: Names git creates on a disk of 255-byte file names, as `(name)`.
HELD = [
    pytest.param(A * 250, id="250-bytes"),
    pytest.param("x/" + A * 250, id="last-part-250"),
    pytest.param(A * 255 + "/x", id="first-part-255"),
    pytest.param("y/" + "b" * 251 + "/z", id="middle-part-251"),
    pytest.param(E * 125, id="125-two-byte-characters"),
]
#: Names it does not, as `(name, the words after "it is"/"its ... is")`.
TOO_LONG = [
    pytest.param(A * 251, "it is 251 bytes long, and may be at most 250",
                 id="251-bytes"),
    pytest.param(A * 255, "it is 255 bytes long, and may be at most 250",
                 id="255-bytes"),
    pytest.param("x/" + A * 251,
                 "its last part is 251 bytes long, and may be at most 250",
                 id="last-part-251"),
    pytest.param(A * 256 + "/x",
                 "its part 1 is 256 bytes long, and may be at most 255",
                 id="first-part-256"),
    pytest.param(E * 126, "it is 252 bytes long, and may be at most 250",
                 id="126-two-byte-characters"),
]


def shown(name: str) -> str:
    """The name as a long one is said: both ends, where the tail is what
    tells two long names apart."""
    return name if len(name) <= 27 else f"{name[:12]}...{name[-12:]}"


@pytest.mark.parametrize("name", HELD)
def test_a_name_the_disk_holds_is_not_refused(name):
    assert shape_materialize.branch_problem("--tracking-branch", name) is None
    assert shape_materialize.refuse_bad_branch(
        "any-code", "--tracking-branch", name) is None


@pytest.mark.parametrize("name, words", TOO_LONG)
def test_a_name_the_disk_cannot_hold_says_which_part_and_how_long(name, words):
    problem = shape_materialize.branch_problem("--tracking-branch", name)
    assert problem == (
        f"--tracking-branch is {shown(name)!r}, which is not a branch name "
        f"git will create: {words}")
    with pytest.raises(Refusal) as caught:
        shape_materialize.refuse_bad_branch("any-code", "--tracking-branch",
                                            name)
    assert caught.value.code == "any-code"
    assert caught.value.detail == problem
    remedy = caught.value.remediation
    assert remedy == shape_materialize.BRANCH_LENGTH_REMEDIATION
    # The remedy names both limits and says why git's own check passes.
    assert "at most 250 bytes" in remedy
    assert "255" in remedy
    assert "no length limit" in remedy


@pytest.mark.skipif(os.name == "nt", reason="a Windows path of this length is "
                    "refused whatever git says")
@pytest.mark.parametrize("name", [
    pytest.param(row.values[0], id=row.id) for row in
    [*HELD[:4], *TOO_LONG[:4]]])
def test_the_rows_are_what_git_makes_on_this_disk(tmp_path, name):
    """THE ROWS ARE MEASURED, NOT ASSUMED: `git branch <name>` in a repository
    of its own succeeds exactly where the helper accepts the name (ASCII rows
    only: a disk may normalise `é` into more bytes than the helper counts)."""
    git("init", "-q", "-b", "main", str(tmp_path), cwd=tmp_path)
    git("commit", "-q", "--allow-empty", "-m", "base", cwd=tmp_path)
    made = git("branch", name, cwd=tmp_path, check=False)
    accepted = shape_materialize.branch_problem("--tracking-branch",
                                                name) is None
    assert (made.returncode == 0) == accepted, (
        made.stderr[:200], len(name))


def assert_too_long(result, code: str, name: str) -> None:
    """Exit 2, the tool's own code, the name as a long one is said, the size
    and the limit, the remedy, and nothing on stdout."""
    assert result.returncode == 2, result.stderr + result.stdout
    assert result.stderr.startswith(
        f"REFUSED {code}: --tracking-branch is {shown(name)!r}, which is not "
        f"a branch name git will create: it is {len(name)} bytes long, and "
        "may be at most 250\n"
        f"{shape_materialize.BRANCH_LENGTH_REMEDIATION}"), result.stderr
    assert result.stdout == "", "a plan was printed for a refused name"
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real"])
@pytest.mark.parametrize("size", [251, 255])
def test_scaffold_refuses_a_tracking_branch_over_250_before_anything_is_made(
        tmp_path, size, dry_run):
    """THE ISSUE'S SCAFFOLD: `--dry-run` exited 0, and the real run made all
    three bare remotes and then died at the first commit."""
    name = A * size
    result = scaffold(tmp_path, f"--tracking-branch={name}", dry_run=dry_run)
    assert_too_long(result, SCAFFOLD_CODE, name)
    assert_nothing_was_made(tmp_path)


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real"])
@pytest.mark.parametrize("size", [251, 255])
def test_family_init_refuses_a_tracking_branch_over_250_before_anything_is_made(
        tmp_path, size, dry_run):
    """THE ISSUE'S REPRODUCTION: `r/Orbit.git` and `w/Orbit` existed when the
    real run died. Now neither run makes a folder, a remote or a holder."""
    name = A * size
    result = family_init(tmp_path, f"--tracking-branch={name}", dry_run=dry_run)
    assert_too_long(result, FAMILY_CODE, name)
    assert_family_made_nothing(tmp_path)


def test_a_dry_run_with_250_still_passes_in_both_tools(tmp_path):
    """The other side of the row: 250 is held, so a plan is printed."""
    name = A * 250
    for run in (scaffold, family_init):
        result = run(tmp_path, f"--tracking-branch={name}", dry_run=True)
        assert result.returncode == 0, result.stderr + result.stdout
        assert "--dry-run: nothing was created." in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="a Windows path of this length is "
                    "refused whatever the tool says")
@pytest.mark.parametrize("tool, remote", [(scaffold, "Atlas.git"),
                                          (family_init, "Contoso.git")])
def test_a_real_run_with_250_makes_every_remote_and_pushes_the_branch(
        tmp_path, tool, remote):
    """THE CONTROL FOR THE LIMIT: where the check lets a name through, the run
    goes to its end and the remote holds exactly that branch."""
    name = A * 250
    result = tool(tmp_path, f"--tracking-branch={name}")
    assert result.returncode == 0, result.stderr + result.stdout
    bare = tmp_path / "remotes" / remote
    assert git("for-each-ref", "--format=%(refname:short)", "refs/heads",
               cwd=bare).stdout.split() == [name]


def test_adopt_refuses_the_same_name_in_plan_and_in_check(world, tmp_path):
    """`adopt-project.py` asks the same helper: `plan` refuses a
    `--tracking-branch` of 251 as `adopt-bad-tracking-branch` and writes
    nothing, and `check` finds a plan edited to it once, under
    `plan-bad-tracking-branch`, in the same words."""
    name = A * 251
    plan = tmp_path / "adoption-plan.yaml"
    result = write_plan(world[0], plan, extra=("--tracking-branch", name))
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(
        f"REFUSED adopt-bad-tracking-branch: --tracking-branch is "
        f"{shown(name)!r}, which is not a branch name git will create: it is "
        "251 bytes long, and may be at most 250\n"), result.stderr
    assert not plan.exists()

    checked = tmp_path / "check"
    checked.mkdir()
    ((code, detail),) = findings(with_branch(world, checked, TRACKING_KEY,
                                             name))
    assert code == "plan-bad-tracking-branch"
    assert detail == (
        f"{TRACKING_KEY} is {shown(name)!r}, which is not a branch name git "
        "will create: it is 251 bytes long, and may be at most 250")
