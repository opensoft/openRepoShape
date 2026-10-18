# SPDX-License-Identifier: Apache-2.0
"""Every command `update-shape.py` prints for a person to paste keeps a root
with a space, a quote or a `$` in it whole (#325).

`landing_failed`'s NEXT line and the rollback's hand-fix lines were quoted for
a POSIX shell by #202 and #204. The three NEXT lines a run prints BEFORE
anything has gone wrong were not: `check`'s `apply`, `apply --branch`'s
`git -C <root> push && gh pr create` and `apply`'s own `git -C <root>
checkout -b && git -C <root> commit`. Each put the root in bare, so a project
under `my projects/`, `it's here/` or `$HOME/` was handed a line that ran in
the wrong directory, did not parse, or expanded.

THE CLAIM IS MADE THE WAY A SHELL WOULD CHECK IT. Each line is read back by
`shlex.split`, the POSIX word-splitting `sh` performs, and compared with the
argv it was printed to mean; the lines that can be run safely are then pasted
into a real `sh` and the effect is read from git. Neither is `str in str`.

WHAT IS NOT CLAIMED. These lines are for a POSIX shell, as `_by_hand` says of
its own: on Windows every root holds a backslash, which `shlex` quotes, so a
Windows root prints in single quotes where it used to print bare. PowerShell
reads a single-quoted string as itself, so the line still pastes there
unless the root holds an apostrophe, whose POSIX spelling (`'\\''`) is not
PowerShell's. The `argv` tests run on every OS; the plain-root byte test, the
real-shell pastes and the doctor's row (which is spelled for PowerShell there,
by `quote_arg`) do not.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import ORG, REPO, WINDOWS_SKIP, git, run_script
from test_commit_trailers import LANE
from test_update_shape import (CHANGED, CHANGED_SOURCE, LOCAL, PROJECT,
                               UPSTREAM_FIX_LINE, apply,
                               commit_upstream_changes, next_line_of,
                               scaffold_upstream_and_project)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import PYTHON  # noqa: E402
from shape_materialize import SHAPE_REPOSITORY  # noqa: E402

UPDATE = REPO / "update-shape.py"
PIN = "contracts/shape-pin.yaml"
MANIFEST = "project.yaml"

#: A directory name each way a path breaks a line pasted bare. One for a
#: space (two arguments), one for an apostrophe (a quotation nothing closes),
#: one for `$` and a backtick (an expansion and a command substitution), one
#: for the characters that end or chain a command, and one for a double
#: quote, which a Windows file name cannot hold.
AWKWARD = [
    pytest.param("my projects", id="space"),
    pytest.param("it's here", id="apostrophe"),
    pytest.param("cost $HOME `true`", id="dollar-and-backtick"),
    pytest.param("a;b (c) & d", id="shell-metacharacters"),
    pytest.param('say "hi"', id="double-quote", marks=pytest.mark.skipif(
        os.name == "nt", reason="a double quote cannot be in a Windows "
                                "file name")),
]

#: The names a line is actually PASTED under. Pasted unquoted, each one only
#: fails (a wrong directory, a syntax error); the ones left out above would
#: also chain a command, which a test has no business running.
PASTED = [
    pytest.param("my projects", id="space"),
    pytest.param("it's here", id="apostrophe"),
    pytest.param("cost $HOME", id="dollar"),
]

#: The `gh` a pasted line reaches. It records its arguments, one per line, and
#: answers a pull request URL; nothing else is a command it knows.
GH_STUB = """#!/bin/sh
printf '%s\\n' "$@" > "$GH_LOG"
echo "https://example.invalid/pull/1"
"""


@pytest.fixture(scope="module")
def project(tmp_path_factory) -> dict:
    """A project at A, its bare remote, and an upstream moved to B."""
    base, upstream, commit_a, clone = scaffold_upstream_and_project(
        tmp_path_factory, "update-shape-next-quoting")
    commit_b = commit_upstream_changes(
        upstream, "Fix the manifest validator",
        {CHANGED_SOURCE: UPSTREAM_FIX_LINE})
    assert commit_a != commit_b
    return {"upstream": upstream, "clone": clone, "a": commit_a,
            "b": commit_b, "remote": base / "remotes" / f"{PROJECT}.git"}


@pytest.fixture
def make_root(project, tmp_path):
    """`make_root(name)`: a private copy of the root at `<tmp>/<name>/Atlas`,
    pushing to a private copy of its remote, so two runs never meet on one.

    A COPY rather than a scaffold into such a directory: the point under test
    is what the tool PRINTS about a root, and a submodule's `.git` is a file
    holding a RELATIVE path into `../.git/modules/<name>`, which keeps the
    copy honest as well as cheap."""
    made: list[Path] = []

    def make(name: str) -> Path:
        remote = tmp_path / f"remote-{len(made)}" / f"{PROJECT}.git"
        shutil.copytree(project["remote"], remote, symlinks=True)
        target = tmp_path / name / PROJECT
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(project["clone"], target, symlinks=True)
        git("remote", "set-url", "origin", str(remote), cwd=target)
        made.append(target)
        return target

    return make


@pytest.fixture(scope="module")
def update_shape():
    """`update-shape.py` as a module, so a line is built in this process."""
    spec = importlib.util.spec_from_file_location("update_shape_quoting",
                                                  UPDATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def argv_of(line: str) -> list[str]:
    """The words a POSIX shell reads out of a printed NEXT line, or a failure
    that says what the shell said. A line no shell can read is the defect,
    and its own assertion."""
    assert line.startswith("NEXT  "), line
    try:
        return shlex.split(line[len("NEXT  "):])
    except ValueError as exc:
        raise AssertionError(f"no shell can read this line -- {exc}\n"
                             f"  {line}") from exc


def steps(argv: list[str]) -> list[list[str]]:
    """`argv` cut at each `&&`: the commands the line chains."""
    out: list[list[str]] = [[]]
    for word in argv:
        if word == "&&":
            out.append([])
        else:
            out[-1].append(word)
    return out


#: The first words of the body of every pull request this tool opens or tells a
#: person to open (#535). What the rest of it says is
#: `tests/test_update_shape_messages.py`'s.
BODY_OPENS = "Written by openRepoShape's `update-shape.py`: "


def pr_words(project: dict) -> tuple[str, str]:
    """`(title, body)` of the pull request for the run these tests make, spelled
    out by hand: the line a person pastes carries both (#535), because a
    `gh pr create` without them has `gh` prompt for them."""
    return (f"Re-sync the shape copies to {SHAPE_REPOSITORY} @ "
            f"{project['b'][:12]}",
            BODY_OPENS + "`contracts/shape-pin.yaml` and `project.yaml` "
            f"re-pinned onto {project['b']}. No copy re-copied from the "
            "upstream was hand-edited and every digest was recomputed.")


def check_run(project, root, *, lane: str = "", upstream=None):
    result = run_script(UPDATE, "check", "--root", str(root), "--upstream",
                        str(upstream or project["upstream"]),
                        env={"LANES_LANE": lane})
    assert result.returncode == 1, result.stdout + result.stderr
    return result


def edit_local(root: Path) -> None:
    """Edit the project's own copy of a pinned file, which is what makes
    `check` name it as `locally-modified`, and which its NEXT offered
    `--accept-local` for until #501."""
    path = root / LOCAL
    path.write_text(path.read_text(encoding="utf-8") + "\n# an edit\n",
                    encoding="utf-8")


# --- check's NEXT line ------------------------------------------------------


@pytest.mark.parametrize("variant", ["plain", "lane", "local-edit"])
@pytest.mark.parametrize("name", AWKWARD)
def test_the_next_line_check_prints_is_one_argv(project, make_root, name,
                                                variant):
    """The `apply` `check` tells a person to run, read back by the shell:
    the root, the upstream and the branch each ONE word, with the lane's
    trailer where there is one.

    AND NO LOCALLY EDITED PATH (#501). The line carried `--accept-local
    <path>` for one, and pasted, it re-pinned the edit; a project keeping
    its edit is the human's word, which `update-local-drift` asks for."""
    root = make_root(name)
    if variant == "local-edit":
        edit_local(root)
    result = check_run(project, root,
                       lane=LANE if variant == "lane" else "")
    expected = [PYTHON, "update-shape.py", "apply", "--root",
                str(root.resolve()), "--upstream",
                str(project["upstream"].resolve()), "--at", project["b"],
                "--yes", "--branch", f"shape/update-{project['b'][:12]}"]
    if variant == "lane":
        expected += ["--trailer", f"Lane: {LANE}"]
    assert argv_of(next_line_of(result.stdout)) == expected


def test_the_upstream_check_names_is_one_argument_too(project, make_root,
                                                      tmp_path):
    """`--upstream` is a path on somebody's disk as much as the root is: a
    clone of the standard under a directory with a space, a quote and a `$`
    is one argument and not three."""
    upstream = tmp_path / "up stream's $copy" / "openRepoShape"
    upstream.parent.mkdir()
    shutil.copytree(project["upstream"], upstream, symlinks=True)
    root = make_root("my projects")
    result = check_run(project, root, upstream=upstream)
    argv = argv_of(next_line_of(result.stdout))
    assert argv[argv.index("--upstream") + 1] == str(upstream.resolve())
    assert argv[argv.index("--root") + 1] == str(root.resolve())
    assert argv[-2:] == ["--branch", f"shape/update-{project['b'][:12]}"]


def test_the_lane_trailer_is_spelled_by_the_same_quoter(update_shape,
                                                        monkeypatch):
    """No double quotes written by hand: whatever `LANE_NAME_RE` admits goes
    through `shlex.quote` like every other argument on the line."""
    monkeypatch.setenv("LANES_LANE", LANE)
    command = update_shape.apply_command(Path("root"), "o/r", "0" * 40)
    assert command.endswith(f" --trailer {shlex.quote('Lane: ' + LANE)}")
    assert '"' not in command, command
    monkeypatch.setenv("LANES_LANE", "")
    assert "--trailer" not in update_shape.apply_command(Path("root"), "o/r",
                                                         "0" * 40)


# --- apply's NEXT lines -----------------------------------------------------


@pytest.mark.parametrize("name", AWKWARD)
def test_the_branch_next_line_is_one_argv(project, make_root, name):
    """`apply --branch` ends on the push and the pull request that finish the
    job. The root is the one argument of it that is a path."""
    root = make_root(name)
    branch = "shape/next-quoting-branch"
    result = apply(root, project, "--branch", branch)
    assert result.returncode == 0, result.stdout + result.stderr
    title, body = pr_words(project)
    assert argv_of(next_line_of(result.stdout)) == [
        "git", "-C", str(root.resolve()), "push", "-u", "origin",
        f"refs/heads/{branch}:refs/heads/{branch}",
        "&&", "gh", "pr", "create", "--repo", f"{ORG}/{PROJECT}", "--base",
        "main", "--head", branch, "--title", title, "--body", body]


def test_the_branch_and_push_next_line_is_one_argv(project, make_root):
    """The line after `--push` names no path, so there is nothing in it to
    break; it is read back all the same, because it is a line somebody pastes
    and the claim is about every one."""
    root = make_root("plain")
    branch = "shape/next-quoting-pushed"
    result = apply(root, project, "--branch", branch, "--push")
    assert result.returncode == 0, result.stdout + result.stderr
    title, body = pr_words(project)
    assert argv_of(next_line_of(result.stdout)) == [
        "gh", "pr", "create", "--repo", f"{ORG}/{PROJECT}", "--base", "main",
        "--head", branch, "--title", title, "--body", body]


@pytest.mark.parametrize("name", AWKWARD)
def test_the_commands_apply_prints_without_a_branch_are_each_one_argv(
        project, make_root, name):
    """`apply` with no `--branch` writes the files and prints the branch and
    the commit as two commands; `git -C <root>` opens each."""
    root = make_root(name)
    result = apply(root, project)
    assert result.returncode == 0, result.stdout + result.stderr
    target = project["b"][:12]
    first, second = steps(argv_of(next_line_of(result.stdout)))
    where = str(root.resolve())
    assert first == ["git", "-C", where, "checkout", "-b",
                     f"shape/update-{target}"]
    assert second[:6] == ["git", "-C", where, "commit", "-m",
                          f"Re-sync the shape @ {target}"]
    assert second[6] == "--"
    assert sorted(second[7:]) == sorted([PIN, MANIFEST, CHANGED])


@pytest.mark.parametrize("name", AWKWARD)
def test_the_staging_step_names_the_root_too(update_shape, capsys, tmp_path,
                                             name):
    """`--add` puts a third command in the line, `git -C <root> ... add -f`,
    and it is the one a bare root hurts most: it stages."""
    root = tmp_path / name / PROJECT
    added = ["docs/shape guide.md", "it's [x].md"]
    paths = sorted({PIN, MANIFEST, *added})
    target = "ab" * 20
    args = SimpleNamespace(branch=None, pr=False, push=False)

    update_shape.next_line(root, args, paths, target, added)

    where = str(root)
    assert steps(argv_of(capsys.readouterr().out.strip())) == [
        ["git", "-C", where, "checkout", "-b", f"shape/update-{target[:12]}"],
        ["git", "-C", where, "--literal-pathspecs", "add", "-f", "--",
         *added],
        ["git", "-C", where, "commit", "-m",
         f"Re-sync the shape @ {target[:12]}", "--", *paths]]


def test_the_branch_is_quoted_even_where_its_alphabet_makes_that_a_no_op(
        update_shape, capsys, tmp_path):
    """`checked_branch` admits only characters `shlex.quote` leaves alone, so
    today the branch prints as it always did. It is passed through the quoter
    anyway, so that widening that alphabet cannot reopen the line: asked
    directly, with a name `main` never lets in."""
    (tmp_path / "project.yaml").write_text(
        "tracking_branch: main\nlegs:\n  - role: assembly\n"
        "    repository: acme/Atlas\n", encoding="utf-8")
    branch = "shape/it's here"
    for push in (True, False):
        args = SimpleNamespace(branch=branch, push=push, pr=False)
        update_shape.next_line(tmp_path, args, [], "0" * 40, [])
        words = argv_of(capsys.readouterr().out.strip())
        assert words[words.index("--head") + 1] == branch, words
        if not push:
            assert words[words.index("push") + 3] == (
                f"refs/heads/{branch}:refs/heads/{branch}"), words


# --- a plain root prints what it always printed -----------------------------


@pytest.mark.skipif(
    os.name == "nt",
    reason="every Windows root holds a backslash, which `shlex` quotes, so "
           "a Windows root prints in single quotes where it used to print "
           "bare; `_by_hand` says so of its own lines")
def test_a_plain_root_prints_the_bytes_it_always_printed(project, make_root):
    """THE LINES BEFORE #325, spelled out by hand: for a root and an upstream
    that need no quoting, not one byte of any of the three lines moved. The
    two changes since are on purpose: the `gh pr create` the branch line ends
    with carries `--title` and `--body` (#535), after everything it had, and
    its push names the branch in full, `refs/heads/<b>:refs/heads/<b>`, so a
    tag of the same name cannot take it (#674)."""
    root = make_root("plain")
    for path in (root.resolve(), project["upstream"].resolve()):
        assert shlex.quote(str(path)) == str(path), (
            "the temporary directory itself needs quoting, so this run has "
            "no plain root to compare")
    where = str(root.resolve())
    b12 = project["b"][:12]

    checked = check_run(project, root)
    assert next_line_of(checked.stdout) == (
        f"NEXT  {PYTHON} update-shape.py apply --root {where} --upstream "
        f"{project['upstream'].resolve()} --at {project['b']} --yes "
        f"--branch shape/update-{b12}")

    branch = "shape/next-quoting-plain"
    pushing = make_root("plain-too")
    branched = apply(pushing, project, "--branch", branch)
    assert branched.returncode == 0, branched.stdout + branched.stderr
    title, body = pr_words(project)
    assert next_line_of(branched.stdout) == (
        f"NEXT  git -C {pushing.resolve()} push -u origin "
        f"refs/heads/{branch}:refs/heads/{branch} && "
        f"gh pr create --repo {ORG}/{PROJECT} --base main --head {branch} "
        f"--title {shlex.quote(title)} --body {shlex.quote(body)}")

    bare = make_root("plain-three")
    unbranched = apply(bare, project)
    assert unbranched.returncode == 0, unbranched.stdout + unbranched.stderr
    there = str(bare.resolve())
    assert next_line_of(unbranched.stdout) == (
        f"NEXT  git -C {there} checkout -b shape/update-{b12} && git -C "
        f"{there} commit -m 'Re-sync the shape @ {b12}' -- {PIN} "
        f"{MANIFEST} {CHANGED}")


# --- pasted into a real shell -----------------------------------------------


def identity() -> dict:
    return {**os.environ, "LANES_LANE": "",
            "GIT_AUTHOR_NAME": "openRepoShape tests",
            "GIT_AUTHOR_EMAIL": "tests@openreposhape.invalid",
            "GIT_COMMITTER_NAME": "openRepoShape tests",
            "GIT_COMMITTER_EMAIL": "tests@openreposhape.invalid"}


def paste(line: str, cwd: Path, env: dict) -> subprocess.CompletedProcess:
    """`line` exactly as printed, minus the `NEXT  ` marker, into `sh -c`."""
    assert line.startswith("NEXT  "), line
    return subprocess.run(["sh", "-c", line[len("NEXT  "):]], cwd=str(cwd),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False, env=env)


@WINDOWS_SKIP
@pytest.mark.parametrize("name", PASTED)
def test_the_line_check_prints_runs_when_it_is_pasted(project, make_root,
                                                      name):
    """The whole promise, end to end: the `apply` that `check` prints, into
    `sh` from the checkout of the standard, lands the re-pin on the branch it
    names with the lane's trailer on the commit — in the project the line
    named, not in a directory the shell made of its pieces."""
    root = make_root(name)
    line = next_line_of(check_run(project, root, lane=LANE).stdout)

    pasted = paste(line, REPO, identity())

    assert pasted.returncode == 0, pasted.stdout + pasted.stderr
    branch = f"shape/update-{project['b'][:12]}"
    assert git("symbolic-ref", "--short", "HEAD",
               cwd=root).stdout.strip() == branch
    assert f"Lane: {LANE}" in git("log", "-1", "--format=%B",
                                  cwd=root).stdout


@WINDOWS_SKIP
@pytest.mark.parametrize("name", PASTED)
def test_the_commands_apply_prints_run_when_they_are_pasted(project, make_root,
                                                            tmp_path, name):
    """`apply` without `--branch` leaves the files written and says how to
    commit them. Pasted from ANOTHER directory, which is what `git -C` is
    for, the line makes the branch and the commit in the root it named."""
    root = make_root(name)
    result = apply(root, project)
    assert result.returncode == 0, result.stdout + result.stderr
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    pasted = paste(next_line_of(result.stdout), elsewhere, identity())

    assert pasted.returncode == 0, pasted.stdout + pasted.stderr
    assert git("symbolic-ref", "--short", "HEAD",
               cwd=root).stdout.strip() == f"shape/update-{project['b'][:12]}"
    assert sorted(git("show", "--name-only", "--format=", "HEAD",
                      cwd=root).stdout.split()) == sorted(
        [PIN, MANIFEST, CHANGED])


@WINDOWS_SKIP
@pytest.mark.parametrize("name", PASTED)
def test_the_branch_line_pushes_and_opens_when_it_is_pasted(project, make_root,
                                                            tmp_path, name):
    """`git -C <root> push -u origin refs/heads/<branch>:refs/heads/<branch>
    && gh pr create ...` (#674 names the branch in full): the push
    has to reach the root's own remote for the `&&` to let `gh` run, so a
    `gh` that ran at all is the proof that the root arrived whole."""
    root = make_root(name)
    branch = "shape/next-quoting-pasted"
    result = apply(root, project, "--branch", branch)
    assert result.returncode == 0, result.stdout + result.stderr
    binary = tmp_path / "bin"
    binary.mkdir()
    stub = binary / "gh"
    stub.write_text(GH_STUB, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "gh.log"
    env = {**identity(), "GH_LOG": str(log),
           "PATH": f"{binary}{os.pathsep}{os.environ['PATH']}"}

    pasted = paste(next_line_of(result.stdout), tmp_path, env)

    assert pasted.returncode == 0, pasted.stdout + pasted.stderr
    title, body = pr_words(project)
    assert log.read_text(encoding="utf-8").split("\n")[:-1] == [
        "pr", "create", "--repo", f"{ORG}/{PROJECT}", "--base", "main",
        "--head", branch, "--title", title, "--body", body]
    remote = git("config", "remote.origin.url", cwd=root).stdout.strip()
    assert git("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}",
               cwd=Path(remote)).stdout.strip() == git(
        "rev-parse", "HEAD", cwd=root).stdout.strip()


# --- the doctor's row for the same command ----------------------------------


@pytest.mark.skipif(
    os.name == "nt",
    reason="the doctor spells this row for PowerShell on Windows, and "
           "`shlex.split` reads POSIX quoting; `tests/test_shape_doctor.py` "
           "asserts the PowerShell spelling")
@pytest.mark.parametrize("name", AWKWARD)
def test_the_doctors_shape_currency_row_keeps_the_root_whole(project,
                                                             make_root, name):
    """THE HALF OF #325 THAT WAS ALREADY RIGHT. The doctor spells every value
    in this row with `quote_arg` (#101, #102), so its `check` and the `apply`
    in its `why` carry the same words the NEXT line above does. Asserted
    here for the roots #325 names, and for `$`, which the earlier tests of
    this row did not use."""
    root = make_root(name)
    upstream = project["upstream"]
    result = run_script(upstream / "shape-doctor.py", "--root", str(root),
                        "--json", env={"LANES_LANE": LANE})
    assert result.returncode == 1, result.stdout + result.stderr
    row = {r["id"]: r for r in json.loads(result.stdout)["rows"]}[
        "shape-currency"]
    assert row["status"] == "FINDING", row
    # The `check` is the NEXT, alone, and the `apply` that follows it is the
    # row's `why`, which opens with `then ` (#277).
    command = row["next"]
    assert row["why"].startswith("then "), row["why"]
    then = row["why"].removeprefix("then ")
    assert shlex.split(command) == [
        PYTHON, str(upstream / "update-shape.py"), "check", "--root",
        str(root.resolve()), "--upstream", str(upstream)]
    assert shlex.split(then) == [
        "apply", "--at", project["b"], "--yes", "--branch",
        f"shape/update-{project['b'][:12]}", "--trailer", f"Lane: {LANE}"]
