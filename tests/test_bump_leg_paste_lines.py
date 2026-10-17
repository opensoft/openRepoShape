# SPDX-License-Identifier: Apache-2.0
"""The three paste lines `scripts/bump-leg.py` printed with the root bare keep
a root with a space, a quote or a `$` in it whole (#532).

`_branch_to_bump_from` handed a person `git -C <root> switch -c bump/...` in
both of its refusals, and the real run ended on `NEXT  git -C <root> push -u
origin <branch>`, each with `str(root)` concatenated in. Under `sp ace/` the
line pasted as `git -C .../sp` and an argument nobody wrote, under `it's/` it
was a quotation nothing closes, and under `d$x/` the shell expanded `$x`
before git saw it. Only #484's dry-run hint had been quoted, with `shlex`. The fourth is the
`git -C <leg> status` that `_restore_leg_if_moved`'s `LegNotAsFound` tells a
person to read: the leg's path is a root's, and it was bare too.

THE CLAIM IS MADE THE WAY A SHELL WOULD CHECK IT. Each printed line is read
back by `shlex.split`, the word-splitting a POSIX shell performs, and must
come back as the argv it was printed to mean; then, wherever the host has `sh`,
the line is PASTED into one and what it does is read from git: the branch it
makes is the branch the re-run commits on, and the push it is lands the commit
in the root's remote. Neither is `str in str`.

WHAT IS NOT CLAIMED. These lines are for a POSIX shell (Git Bash, or WSL2, on
Windows), as README's "Windows, natively" says: a Windows root holds a
backslash, which `shlex` quotes, so every exact-string expectation below is
built with `shlex` too, and the pastes into `sh` are POSIX-only.

NO NETWORK, NO `gh`: the bare remotes are the session's own, and the root's
own remote is a private copy, so the push a pasted line makes reaches nothing
another test reads.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import PROJECT, WINDOWS_SKIP, cloned_just_pushed, git
# A fixture is used by being named in this module's namespace, which is what
# the import of `bump_leg_module` is for.
from test_bump_leg import (  # noqa: F401
    WORKING_BRANCH, branched, bump, bump_leg_module,
)

#: Where the advanced spec commit is pushed. Not another module's branch: the
#: bare remotes are session-scoped, and a second, different commit pushed to
#: a name already taken is refused as non-fast-forward.
ADVANCE_BRANCH = "bump-leg-paste-lines-advance"

#: The sentence each of the three lines is followed by (#647), pinned as text:
#: `family.py`'s and the holder's `BRANCH_LEFT` (#607) with a project where
#: they have a holder. Imported by the tests that read these lines' bytes.
BRANCH_LEFT_PROJECT = (
    "If `git switch -c` says that branch already exists, an earlier act left "
    "it: give the branch another name, which starts it where the project "
    "stands, or, only if that branch holds work not merged yet, the same "
    "command with `switch` in place of `switch -c` goes back to it and keeps "
    "every commit on it.")

#: A directory name each way a path breaks a line pasted bare: a space (two
#: arguments), an apostrophe (a quotation nothing closes), a `$` (an
#: expansion).
ROOTS = [
    pytest.param("sp ace", id="space"),
    pytest.param("it's", id="apostrophe"),
    pytest.param("d$x", id="dollar"),
]


@pytest.fixture(scope="module")
def advanced(scaffolded, tmp_path_factory) -> str:
    """A real new commit on the spec leg's bare remote; returns its sha."""
    work = cloned_just_pushed(
        scaffolded["remotes"] / f"{PROJECT}-spec.git",
        tmp_path_factory.mktemp("spec-advance-paste-lines")
        / f"{PROJECT}-spec")
    (work / "PASTE-LINES.md").write_text("# a contract gained\n")
    git("add", "--", "PASTE-LINES.md", cwd=work)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "Advance the spec leg for the paste-line tests", cwd=work)
    git("push", "-q", "origin", f"HEAD:refs/heads/{ADVANCE_BRANCH}", cwd=work)
    return git("rev-parse", "HEAD", cwd=work).stdout.strip()


@pytest.fixture
def make_root(scaffolded, tmp_path):
    """`make_root(name)`: a private copy of the assembly root at
    `<tmp>/<name>/Atlas`, pushing to a private copy of its bare remote, so a
    pasted `git push` reaches nothing the session shares.

    A COPY rather than a scaffold into such a directory: the point under test
    is what the tool PRINTS about a root, and a submodule's `.git` is a file
    holding a RELATIVE path into `../.git/modules/<name>`, which keeps the
    copy honest as well as cheap. The legs are still fetched from the
    session's remotes, through `--local-remote-dir`, as every test here does.
    """
    made: list[Path] = []

    def make(name: str) -> tuple[Path, Path]:
        remote = tmp_path / f"remote-{len(made)}" / f"{PROJECT}.git"
        shutil.copytree(scaffolded["remotes"] / f"{PROJECT}.git", remote,
                        symlinks=True)
        target = tmp_path / name / PROJECT
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(scaffolded["clone"], target, symlinks=True)
        git("remote", "set-url", "origin", str(remote), cwd=target)
        made.append(target)
        return target, remote

    return make


def words(line: str) -> list[str]:
    """The words a POSIX shell reads out of `line`, or a failure that says what
    the shell said: a line no shell can read is the defect, and its own
    assertion."""
    try:
        return shlex.split(line)
    except ValueError as exc:
        raise AssertionError(f"no shell can read this line -- {exc}\n"
                             f"  {line}") from exc


def paste(line: str, cwd: Path) -> subprocess.CompletedProcess:
    """`line` typed into a POSIX `sh`, from a directory that is not the
    root's, so only what the line itself says can reach it."""
    return subprocess.run(["sh", "-c", line], cwd=str(cwd),
                          capture_output=True, text=True, check=False)


def switch_argv(root: Path, to: str) -> list[str]:
    """What the `switch -c` lines mean: the root as `Project.open` resolves
    it, and the branch `bump/<role>-<the id as typed, 12 characters>`."""
    return ["git", "-C", str(root.resolve()), "switch", "-c",
            f"bump/spec-{to[:12]}"]


def detached_remedy(stderr: str) -> str:
    """The command between the backticks of `bump-leg-root-detached`'s
    remediation."""
    found = re.search(r"^Remediation: `(.*)` and re-run\.$", stderr, re.M)
    assert found, stderr
    return found.group(1)


def tracking_remedy(stderr: str) -> str:
    """The command `bump-leg-on-tracking-branch` puts on a line of its own,
    after `Run:`."""
    found = re.search(r"default branch\. Run:\n    (.*)\nand re-run\.$",
                      stderr, re.M)
    assert found, stderr
    return found.group(1)


def next_line(stdout: str) -> str:
    """The one `NEXT` line a real run ends on, whole, without its label."""
    lines = [line for line in stdout.splitlines()
             if line.startswith("NEXT")]
    assert len(lines) == 1, stdout
    assert lines[0].startswith("NEXT  "), lines[0]
    return lines[0][len("NEXT  "):]


def current_branch(root: Path):
    return git("symbolic-ref", "--short", "-q", "HEAD", cwd=root,
               check=False).stdout.strip()


# --- the two `switch -c` remedies --------------------------------------------


@pytest.mark.parametrize("name", ROOTS)
def test_the_root_detached_remedy_is_one_command(
        make_root, scaffolded, advanced, name):
    """`bump-leg-root-detached`: the root is on no branch, and the remedy's
    `switch -c` is split into the argv it means."""
    root, _ = make_root(name)
    git("checkout", "-q", "--detach", cwd=root)

    result = bump(root, scaffolded, advanced)
    assert result.returncode == 2, result.stderr + result.stdout
    assert result.stdout == ""
    assert "REFUSED bump-leg-root-detached" in result.stderr, result.stderr
    assert words(detached_remedy(result.stderr)) == switch_argv(root, advanced)


@pytest.mark.parametrize("name", ROOTS)
def test_the_tracking_branch_remedy_is_one_command(
        make_root, scaffolded, advanced, name):
    """`bump-leg-on-tracking-branch`: the root stands on the project's
    tracking branch, and the `switch -c` on a line of its own is the argv it
    means."""
    root, _ = make_root(name)

    result = bump(root, scaffolded, advanced)
    assert result.returncode == 2, result.stderr + result.stdout
    assert result.stdout == ""
    assert "REFUSED bump-leg-on-tracking-branch" in result.stderr
    assert words(tracking_remedy(result.stderr)) == switch_argv(root,
                                                                advanced)


def test_the_two_remedies_and_the_dry_run_hint_are_one_spelling(
        make_root, scaffolded, advanced):
    """The dry run's rule (#477) is that it names the branch the real run's
    refusal names; all three lines come from one function, so one spelling,
    quoting included."""
    root, _ = make_root("it's")
    hint = bump(root, scaffolded, advanced, "--dry-run")
    assert hint.returncode == 0, hint.stderr + hint.stdout
    needle = "Create one first with: "
    assert hint.stdout.count(needle) == 1, hint.stdout
    from_the_dry_run = hint.stdout.split(needle)[1].splitlines()[0]
    assert words(from_the_dry_run) == switch_argv(root, advanced)

    refused = bump(root, scaffolded, advanced)
    assert tracking_remedy(refused.stderr) == from_the_dry_run

    git("checkout", "-q", "--detach", cwd=root)
    detached = bump(root, scaffolded, advanced)
    assert detached_remedy(detached.stderr) == from_the_dry_run


def test_an_exact_remedy_is_the_line_shlex_spells(make_root, scaffolded,
                                                  advanced):
    """The byte test, built with `shlex` so it holds on a Windows root too
    (every one holds a backslash, which `shlex` quotes): the whole remediation
    of the tracking-branch refusal, and the root-detached one."""
    root, _ = make_root("sp ace")
    line = shlex.join(switch_argv(root, advanced))
    tracking = bump(root, scaffolded, advanced)
    assert tracking.stderr.endswith(
        "will not make a commit whose only next step is a push to the "
        f"default branch. Run:\n    {line}\nand re-run.\n"
        f"{BRANCH_LEFT_PROJECT}\n"), tracking.stderr

    git("checkout", "-q", "--detach", cwd=root)
    detached = bump(root, scaffolded, advanced)
    assert detached.stderr.endswith(
        f"Remediation: `{line}` and re-run.\n{BRANCH_LEFT_PROJECT}\n"), \
        detached.stderr


@WINDOWS_SKIP
@pytest.mark.parametrize("name", ROOTS)
def test_pasting_the_tracking_branch_remedy_makes_the_branch_the_rerun_uses(
        make_root, scaffolded, advanced, name):
    """THE LINE, RUN: pasted into `sh` it makes `bump/spec-<id>` in THAT root
    and nowhere else, and the run it refused then goes through, on it."""
    root, _ = make_root(name)
    refused = bump(root, scaffolded, advanced)
    assert refused.returncode == 2, refused.stderr + refused.stdout
    assert current_branch(root) == "main"

    pasted = paste(tracking_remedy(refused.stderr), root.parent)
    assert pasted.returncode == 0, pasted.stderr + pasted.stdout
    assert current_branch(root) == f"bump/spec-{advanced[:12]}"

    again = bump(root, scaffolded, advanced)
    assert again.returncode == 0, again.stderr + again.stdout


@WINDOWS_SKIP
@pytest.mark.parametrize("name", ROOTS)
def test_pasting_the_detached_remedy_puts_the_root_on_a_branch(
        make_root, scaffolded, advanced, name):
    root, _ = make_root(name)
    git("checkout", "-q", "--detach", cwd=root)
    refused = bump(root, scaffolded, advanced)
    assert refused.returncode == 2, refused.stderr + refused.stdout
    assert current_branch(root) == ""

    pasted = paste(detached_remedy(refused.stderr), root.parent)
    assert pasted.returncode == 0, pasted.stderr + pasted.stdout
    assert current_branch(root) == f"bump/spec-{advanced[:12]}"

    again = bump(root, scaffolded, advanced)
    assert again.returncode == 0, again.stderr + again.stdout


# --- the closing NEXT --------------------------------------------------------


@pytest.mark.parametrize("name", ROOTS)
def test_the_closing_next_is_one_command(make_root, scaffolded, advanced,
                                         name):
    """`NEXT  git -C <root> push -u origin refs/heads/<b>:refs/heads/<b>`,
    split into the argv it means, and spelled exactly as `shlex` spells it.
    The branch by its full refname (#672): a bare one is a refspec, and a
    leading `+` forces."""
    root, _ = make_root(name)
    branched(root)
    result = bump(root, scaffolded, advanced)
    assert result.returncode == 0, result.stderr + result.stdout

    line = next_line(result.stdout)
    argv = ["git", "-C", str(root.resolve()), "push", "-u", "origin",
            f"refs/heads/{WORKING_BRANCH}:refs/heads/{WORKING_BRANCH}"]
    assert words(line) == argv
    assert line == shlex.join(argv)
    assert ("      then open a pull request against main; never push the "
            "bump to the default branch directly") in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="a Windows root holds a "
                    "backslash, which `shlex` quotes")
def test_an_ordinary_root_prints_the_line_it_always_did(make_root, scaffolded,
                                                        advanced):
    """Nothing is quoted that needs no quoting: a root whose name is plain
    prints the bytes it did before #532, the branch by its full refname on
    both sides (#672)."""
    root, _ = make_root("plain")
    branched(root)
    result = bump(root, scaffolded, advanced)
    assert result.returncode == 0, result.stderr + result.stdout
    assert next_line(result.stdout) == (
        f"git -C {root.resolve()} push -u origin "
        f"refs/heads/{WORKING_BRANCH}:refs/heads/{WORKING_BRANCH}")


@WINDOWS_SKIP
@pytest.mark.parametrize("name", ROOTS)
def test_pasting_the_closing_next_pushes_the_commit_the_run_made(
        make_root, scaffolded, advanced, name):
    """THE LINE, RUN: pasted into `sh` it pushes THIS root's branch, and the
    root's own remote then holds it at the commit the run wrote."""
    root, remote = make_root(name)
    branched(root)
    result = bump(root, scaffolded, advanced)
    assert result.returncode == 0, result.stderr + result.stdout
    committed = git("rev-parse", "HEAD", cwd=root).stdout.strip()

    pasted = paste(next_line(result.stdout), root.parent)
    assert pasted.returncode == 0, pasted.stderr + pasted.stdout
    assert git("rev-parse", f"refs/heads/{WORKING_BRANCH}",
               cwd=remote).stdout.strip() == committed


@pytest.mark.parametrize("branch", ["bump/it's", "wip$x", "fix/a;b"])
def test_the_closing_next_carries_the_branch_whole(make_root, scaffolded,
                                                   advanced, branch):
    """The BRANCH is a word of the line too, and git accepts an apostrophe, a
    `$` and a `;` in one: bare, the last word of the line would be a
    quotation nothing closes, an expansion, or the end of the command."""
    root, _ = make_root("sp ace")
    branched(root, branch)
    result = bump(root, scaffolded, advanced)
    assert result.returncode == 0, result.stderr + result.stdout

    line = next_line(result.stdout)
    pushed = f"refs/heads/{branch}:refs/heads/{branch}"
    assert words(line) == ["git", "-C", str(root.resolve()), "push", "-u",
                           "origin", pushed]
    assert words(line)[-1] == pushed
    assert line == shlex.join(["git", "-C", str(root.resolve()), "push", "-u",
                               "origin", pushed])


@WINDOWS_SKIP
@pytest.mark.parametrize("branch", ["bump/it's", "wip$x", "fix/a;b"])
def test_pasting_the_closing_next_pushes_a_branch_with_a_quote_in_its_name(
        make_root, scaffolded, advanced, branch):
    """THE LINE, RUN: the branch that lands in the root's remote is the one
    the root stood on, whatever it is called."""
    root, remote = make_root("it's")
    branched(root, branch)
    result = bump(root, scaffolded, advanced)
    assert result.returncode == 0, result.stderr + result.stdout
    committed = git("rev-parse", "HEAD", cwd=root).stdout.strip()

    pasted = paste(next_line(result.stdout), root.parent)
    assert pasted.returncode == 0, pasted.stderr + pasted.stdout
    assert git("rev-parse", f"refs/heads/{branch}",
               cwd=remote).stdout.strip() == committed


# --- the status line of a leg that is not as it was found --------------------


def status_remedy(message: str) -> str:
    """The command between the backticks after `Read`, in
    `LegNotAsFound`'s message."""
    found = re.search(r"Read `(.*)` before anything else", message)
    assert found, message
    return found.group(1)


@pytest.mark.parametrize("name", ROOTS)
def test_the_status_line_of_a_leg_not_as_found_is_one_command(
        make_root, bump_leg_module, name):
    """`_restore_leg_if_moved` reads the leg's `git status` against what it
    was before the bump and, where it differs, sends the person to read it.
    The leg's path is a root's: `git -C <leg> status` pasted bare under `sp
    ace/` was `git -C .../sp` and an argument nobody wrote."""
    root, _ = make_root(name)
    leg = root.resolve() / "spec"
    placement = bump_leg_module.leg_placement(leg)
    was = git("rev-parse", "HEAD", cwd=leg).stdout.strip()

    with pytest.raises(bump_leg_module.LegNotAsFound) as raised:
        bump_leg_module._restore_leg_if_moved(leg, placement, was,
                                              b"not its status")
    line = status_remedy(str(raised.value))
    assert words(line) == ["git", "-C", str(leg), "status"]
    assert line == shlex.join(["git", "-C", str(leg), "status"])


@WINDOWS_SKIP
@pytest.mark.parametrize("name", ROOTS)
def test_pasting_the_status_line_reads_that_leg(make_root, bump_leg_module,
                                                name):
    root, _ = make_root(name)
    leg = root.resolve() / "spec"
    was = git("rev-parse", "HEAD", cwd=leg).stdout.strip()
    with pytest.raises(bump_leg_module.LegNotAsFound) as raised:
        bump_leg_module._restore_leg_if_moved(
            leg, bump_leg_module.leg_placement(leg), was, b"not its status")

    pasted = paste(status_remedy(str(raised.value)), root.parent)
    assert pasted.returncode == 0, pasted.stderr + pasted.stdout
    assert pasted.stderr == ""
