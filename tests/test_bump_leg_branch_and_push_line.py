# SPDX-License-Identifier: Apache-2.0
"""`scripts/bump-leg.py` reads the root's branch the way git spells it, ends
on a push no branch name can bend, spells what a dirty root lists, names
what its commit holds, and says what a dry run does not run (#672).

FIVE LINES, EACH MEASURED ON MAIN BEFORE THE FIX:

  * THE BRANCH. `current_branch` asked `git symbolic-ref --short HEAD`, which
    gives the shortest name that is not ambiguous: beside a tag `main` it
    printed `heads/main`, the compare with the tracking branch read that
    against `main`, and the bump COMMITTED ON THE DEFAULT BRANCH and printed
    `push -u origin heads/main`. A HEAD on `refs/tags/<t>` read as `<t>`, and
    the bump moved the tag. The full ref is read now, and only a ref under
    `refs/heads/` is a branch.
  * THE PUSH. The NEXT line ended `push -u origin <branch>`, and a bare
    `<branch>` is a refspec: a leading `+` is FORCE. A root on `+x` was told
    `push -u origin +x`, which pushed a local `x` over origin's `x`, forced,
    and never pushed `+x`; on `+main` it rewinds origin's `main`. It is
    `refs/heads/<branch>:refs/heads/<branch>` now, the branch and nothing
    else on both sides, the form #689 and #674 give `family.py`'s and
    `update-shape.py`'s push lines.
  * THE DIRTY ROOT. Under `core.quotePath=false` git prints a name as the
    bytes it holds, and `bump-leg-root-dirty` printed a C1 control and a
    bidi override raw. Each line is `repo_shape.spelled` now, split on git's
    own newlines, so U+0085 and U+2028 stay on their line and are named.
  * THE COMMIT. `committed <sha>:` listed the paths STAGED, and the leg is
    staged whether or not its gitlink moves: over a gitlink a person had
    moved by hand it named `spec` beside the pin, and the report and the
    message said `X -> X`. The paths are read from git now, and the old
    commit is the pin's own `commit:` where the gitlink already holds it.
  * THE DRY RUN. It never runs the project's own validators, so over a pin
    they already refuse it exits 0 and the real run ends
    `bump-leg-validators-red`. Its closing paragraph says so.

NO NETWORK, NO `gh`: the bare remotes are the session's own, and every root
here pushes to a private copy of its remote (`make_root`), so a push reaches
nothing another test reads. Every printed line is run as the argv a POSIX
shell reads out of it, without a shell, so these hold on every OS.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import FILE_PROTOCOL, PROJECT, REPO, cloned_just_pushed, git
# A fixture is used by being named in this module's namespace, which is what
# the imports of `bump_leg_module` and `make_root` are for.
from test_bump_leg import (  # noqa: F401
    branched, bump, bump_leg_module, committed, reference_both_legs, validate,
)
from test_bump_leg_paste_lines import make_root, next_line, words  # noqa: F401

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import spelled  # noqa: E402

#: Where the advanced spec commit is pushed. Not another module's branch: the
#: bare remotes are session-scoped, and a second, different commit pushed to
#: a name already taken is refused as non-fast-forward.
ADVANCE_BRANCH = "bump-leg-branch-and-push-line-advance"

SPEC_PIN = "contracts/spec-pin.yaml"

#: The sentence the dry run's closing paragraph ends with.
NOT_VALIDATED = (
    "A dry run does not run the project's own validators "
    "(scripts/validate-pins.py and scripts/validate-manifest.py): the real "
    "run runs them after the rewrite, and can still end "
    "`bump-leg-validators-red`, with every byte rolled back.")


@pytest.fixture(scope="module")
def advanced(scaffolded, tmp_path_factory) -> str:
    """A real new commit on the spec leg's bare remote; returns its sha."""
    remote = scaffolded["remotes"] / f"{PROJECT}-spec.git"
    work = cloned_just_pushed(
        remote, tmp_path_factory.mktemp("spec-advance-push-line") / "leg")
    (work / "PUSH-LINE.md").write_text("# the push line\n", encoding="utf-8")
    git("add", "--", "PUSH-LINE.md", cwd=work)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "Advance the spec leg for the push-line tests", cwd=work)
    git("push", "-q", "origin", f"HEAD:refs/heads/{ADVANCE_BRANCH}", cwd=work)
    return git("rev-parse", "HEAD", cwd=work).stdout.strip()


def head_of(repo: Path, ref: str = "HEAD") -> str:
    return git("rev-parse", "--verify", "-q", ref, cwd=repo,
               check=False).stdout.strip()


def commit_empty(root: Path, message: str) -> str:
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
        "--allow-empty", "-m", message, cwd=root)
    return head_of(root)


def lines_of(result) -> list[str]:
    return result.stdout.splitlines()


# --- the branch, read in full ------------------------------------------------


def test_a_tag_named_like_the_tracking_branch_does_not_let_the_bump_onto_it(
        project, scaffolded, advanced):
    """THE ISSUE'S MEASUREMENT: a tag `main` beside the tracking branch
    `main`. `--short` read `heads/main`, the refusal was not given, the bump
    committed on the default branch and printed a push to it. Refused now,
    in the words a root on `main` with no such tag is given, and the dry run
    names the tracking branch as itself."""
    git("tag", "main", cwd=project)
    head = head_of(project)

    real = bump(project, scaffolded, advanced)
    assert real.returncode == 2, real.stderr + real.stdout
    assert "REFUSED bump-leg-on-tracking-branch" in real.stderr, real.stderr
    assert "is on 'main', which project.yaml declares" in real.stderr
    assert real.stdout == ""
    assert head_of(project) == head, "nothing was committed on main"

    dry = bump(project, scaffolded, advanced, "--dry-run")
    assert dry.returncode == 0, dry.stderr + dry.stdout
    assert f"{project.resolve()} is on 'main', the tracking branch." in \
        dry.stdout, dry.stdout
    assert "heads/main" not in dry.stdout


def test_a_head_on_a_tag_ref_is_no_branch_to_bump_on(project, scaffolded,
                                                     advanced):
    """`symbolic-ref` lets HEAD name `refs/tags/<t>`, and `--short` read it
    as the branch `<t>`: the bump committed THROUGH it, which moved the tag,
    and printed `push -u origin x`. A ref outside `refs/heads/` is no
    branch: refused as a root on no branch is, with the tag where it was."""
    git("tag", "x", cwd=project)
    tagged = head_of(project, "refs/tags/x")
    git("symbolic-ref", "HEAD", "refs/tags/x", cwd=project)

    result = bump(project, scaffolded, advanced)
    assert result.returncode == 2, result.stderr + result.stdout
    assert "REFUSED bump-leg-root-detached" in result.stderr, result.stderr
    assert result.stdout == ""
    assert head_of(project, "refs/tags/x") == tagged, "the tag did not move"


# --- the push, by its full ref -----------------------------------------------


def push_argv(root: Path, branch: str) -> list[str]:
    """The NEXT line's argv: the branch by its full refname on both sides,
    the form #689 and #674 give `family.py`'s and `update-shape.py`'s."""
    return ["git", "-C", str(root.resolve()), "push", "-u", "origin",
            f"refs/heads/{branch}:refs/heads/{branch}"]


def run_the_line(line: str, cwd: Path) -> subprocess.CompletedProcess:
    """The NEXT line as the argv a POSIX shell reads out of it, run without
    a shell, from a directory that is not the root's."""
    return subprocess.run(words(line), cwd=str(cwd), capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          check=False)


def upstream_of(root: Path, branch: str) -> str:
    return git("for-each-ref", "--format=%(upstream)",
               f"refs/heads/{branch}", cwd=root).stdout.strip()


@pytest.mark.parametrize("name", ["+x", "+main"])
def test_a_branch_named_with_a_leading_plus_is_pushed_and_nothing_is_forced(
        make_root, scaffolded, advanced, name):
    """THE ISSUE'S MEASUREMENT, and its worst case. Origin's `<name minus +>`
    has moved on from the local branch of that name. The bare line read
    `+<name>` as the FORCED refspec `<name minus +>`: origin's `x` was
    overwritten (`forced update`), and on `+main` origin's DEFAULT BRANCH was
    rewound, while `+<name>` itself was never pushed. By its full refname
    the line pushes `+<name>`, as a new branch, upstream recorded, and
    leaves the other where it was."""
    root, remote = make_root("plain")
    other = name[1:]
    start = head_of(root)
    git("checkout", "-q", "-b", "w672-elsewhere", cwd=root)
    moved_on = commit_empty(root, f"origin's {other} moves on")
    git("push", "-q", "origin", f"HEAD:refs/heads/{other}", cwd=root)
    git("checkout", "-q", "main", cwd=root)
    if other != "main":
        git("branch", other, start, cwd=root)
    git("checkout", "-q", "-b", name, cwd=root)

    result = bump(root, scaffolded, advanced)
    assert result.returncode == 0, result.stderr + result.stdout
    line = next_line(result.stdout)
    assert words(line) == push_argv(root, name)

    pushed = run_the_line(line, root.parent)
    assert pushed.returncode == 0, pushed.stderr + pushed.stdout
    assert "forced update" not in pushed.stderr, pushed.stderr
    assert head_of(remote, f"refs/heads/{name}") == head_of(root)
    assert head_of(remote, f"refs/heads/{other}") == moved_on, (
        f"origin's {other} was not touched")
    assert upstream_of(root, name) == f"refs/remotes/origin/{name}"


def test_a_branch_beside_a_tag_of_its_name_is_pushed_by_its_full_ref(
        make_root, scaffolded, advanced):
    """A branch `v1` beside a tag `v1`: `--short` read `heads/v1`, and the
    line said `push -u origin heads/v1` (git's own bare `v1` there is `src
    refspec v1 matches more than one`). The line names `refs/heads/v1` on
    both sides, and run, it pushes the branch and records its upstream."""
    root, remote = make_root("plain")
    git("tag", "v1", cwd=root)
    git("checkout", "-q", "-b", "v1", cwd=root)

    result = bump(root, scaffolded, advanced)
    assert result.returncode == 0, result.stderr + result.stdout
    line = next_line(result.stdout)
    assert words(line) == push_argv(root, "v1")

    pushed = run_the_line(line, root.parent)
    assert pushed.returncode == 0, pushed.stderr + pushed.stdout
    assert head_of(remote, "refs/heads/v1") == head_of(root, "refs/heads/v1")
    assert upstream_of(root, "v1") == "refs/remotes/origin/v1"


# --- the dirty root, spelled -------------------------------------------------

#: `(a name, as `bump-leg-root-dirty` lists it under core.quotePath=false)`.
SPELLED = [
    pytest.param("caf\u009b\u202eevil.yml", "caf\\x9b\\u202eevil.yml",
                 id="c1-and-bidi"),
    pytest.param("a\u2028b.yml", "a\\u2028b.yml", id="line-separator"),
    pytest.param("c\u0085d.yml", "c\\x85d.yml", id="next-line"),
    pytest.param("end\u2028", "end\\u2028", id="ends-in-a-separator"),
]


def raw_controls(name: str, text: str) -> list[str]:
    """The characters of `name` that `spelled` escapes and that `text` still
    holds as they are: what a terminal must not be handed raw."""
    return [char for char in name if spelled(char) != char and char in text]


def dirty_with(project: Path, name: str) -> None:
    """A tracked workflow file `name`, committed and then edited, under
    `core.quotePath=false`, on a bump branch; or skip where the disk cannot
    hold the name."""
    branched(project)
    path = project / ".github" / "workflows" / name
    try:
        path.write_bytes(b"on: [push]\n")
    except (OSError, UnicodeError) as exc:
        pytest.skip(f"this filesystem cannot hold the name: {exc}")
    git("add", "--", f".github/workflows/{name}", cwd=project)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "A workflow whose name holds a control", cwd=project)
    path.write_bytes(path.read_bytes() + b"# edited\n")
    git("config", "core.quotePath", "false", cwd=project)


@pytest.mark.parametrize("extra", [(), ("--dry-run",)],
                         ids=["bump", "dry-run"])
@pytest.mark.parametrize("name, shown", SPELLED)
def test_a_dirty_name_holding_controls_is_listed_spelled(
        project, scaffolded, advanced, name, shown, extra):
    """THE ISSUE'S MEASUREMENT (`caf<U+009B><U+202E>evil.yml`), and the two
    characters `splitlines` breaks a line at: the name is on ONE line of its
    own, every control written as its escape, and none of them raw."""
    dirty_with(project, name)
    result = bump(project, scaffolded, advanced, *extra)
    assert result.returncode == 2, result.stderr + result.stdout
    assert "REFUSED bump-leg-root-dirty" in result.stderr, result.stderr
    assert f"    M .github/workflows/{shown}" in result.stderr.split("\n"), (
        result.stderr)
    assert raw_controls(name, result.stderr) == [], ascii(result.stderr)


def test_under_the_default_quoting_git_names_the_file_itself(
        project, scaffolded, advanced):
    """THE CONTROL: with `core.quotePath` as git ships it, git quotes the
    bytes itself, and the line is git's, unchanged."""
    dirty_with(project, "caf\u009b\u202eevil.yml")
    git("config", "--unset", "core.quotePath", cwd=project)
    result = bump(project, scaffolded, advanced)
    assert result.returncode == 2, result.stderr + result.stdout
    assert ('    M ".github/workflows/caf\\302\\233\\342\\200\\256evil.yml"'
            in result.stderr.splitlines()), result.stderr


# --- the commit, as git holds it ---------------------------------------------


def body_of(project: Path) -> str:
    return git("log", "-1", "--format=%b", cwd=project).stdout


@pytest.mark.parametrize("setting", [None, "submodule.spec.ignore",
                                     "diff.ignoreSubmodules"])
def test_the_committed_line_names_the_paths_git_holds(
        project, scaffolded, advanced, setting):
    """The paths of the commit, as git lists them, in git's order: a
    workflow, the pin and the gitlink. With an `ignore = all` the person set
    for the leg, `git show` drops the gitlink from its list, and the line
    still names it, because the commit holds it."""
    reference_both_legs(project)
    branched(project)
    if setting:
        git("config", setting, "all", cwd=project)

    result = bump(project, scaffolded, advanced)
    assert result.returncode == 0, result.stderr + result.stdout
    held = git("show", "--ignore-submodules=none", "--name-only",
               "--format=", "HEAD", cwd=project).stdout.split()
    assert held == [".github/workflows/legs.yml", SPEC_PIN, "spec"]
    assert f"  committed {head_of(project)[:12]}: {', '.join(held)}" in \
        lines_of(result), result.stdout
    assert not any(line.startswith("gitlink ") for line in lines_of(result))


def test_a_gitlink_moved_by_hand_is_reported_as_the_pins_move(
        project, scaffolded, advanced):
    """THE ISSUE'S MEASUREMENT (AT-scaffold N9): a person moved the gitlink to
    the new commit by hand and committed it; the pin still names the old
    one. The report, the dry run's included, and the commit message said
    `X -> X`, and `committed` named `spec` beside the pin, which the commit
    does not hold. The old commit is the pin's own now, a line says the
    gitlink does not move, and the commit's paths are git's."""
    pinned = git("rev-parse", "HEAD:spec", cwd=project).stdout.strip()
    branched(project)
    leg = project / "spec"
    git(*FILE_PROTOCOL, "fetch", "-q",
        str(scaffolded["remotes"] / f"{PROJECT}-spec.git"), ADVANCE_BRANCH,
        cwd=leg)
    git("checkout", "-q", "--detach", advanced, cwd=leg)
    git("add", "--", "spec", cwd=project)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "Move the gitlink by hand", cwd=project)
    moved = f"commit       {pinned[:12]} -> {advanced[:12]}"
    held = (f"gitlink      spec already records {advanced[:12]}, so this "
            "does not move it")

    dry = bump(project, scaffolded, advanced, "--dry-run")
    assert dry.returncode == 0, dry.stderr + dry.stdout
    assert moved in lines_of(dry), dry.stdout
    assert held in lines_of(dry), dry.stdout

    result = bump(project, scaffolded, advanced)
    assert result.returncode == 0, result.stderr + result.stdout
    assert moved in lines_of(result), result.stdout
    assert held in lines_of(result), result.stdout
    assert f"{advanced[:12]} -> {advanced[:12]}" not in result.stdout
    assert committed(project) == {SPEC_PIN}
    assert f"  committed {head_of(project)[:12]}: {SPEC_PIN}" in \
        lines_of(result), result.stdout
    body = body_of(project)
    assert body.startswith(f"{pinned[:12]} -> {advanced[:12]}, tree "), body
    assert (f"The gitlink at spec already recorded {advanced[:12]}, so this "
            "commit does not move it.") in body, body
    assert "so the pin file is the whole of it." in body, body
    assert validate(project).returncode == 0, "the project's own gate agrees"


def test_a_committed_line_git_cannot_read_back_still_says_the_bump_landed(
        project, scaffolded, advanced, bump_leg_module, monkeypatch, capsys):
    """THE LINE IS READ AFTER THE COMMIT, so nothing in it may refuse: a
    `git-failed` there would be exit 2 over a bump that landed. The line
    names the commit and says where its paths are, and the run ends on its
    NEXT, exit 0."""
    branched(project)
    before = head_of(project)
    real_git_out = bump_leg_module.git_out

    def no_diff_tree(args, *rest, **kwargs):
        if args[:1] == ["diff-tree"]:
            raise bump_leg_module.Refusal(
                "git-failed", "`git diff-tree` exited 128: fatal: bad object")
        return real_git_out(args, *rest, **kwargs)

    monkeypatch.setattr(bump_leg_module, "git_out", no_diff_tree)
    code = bump_leg_module.main([
        "--root", str(project), "--leg", "spec", "--to", advanced,
        "--local-remote-dir", str(scaffolded["remotes"])])
    out = capsys.readouterr().out

    head = head_of(project)
    assert code == 0, out
    assert git("rev-parse", f"{head}~1", cwd=project).stdout.strip() == before
    assert (f"  committed {head[:12]}: its paths could not be read back "
            "(`git diff-tree` exited 128: fatal: bad object); `git show "
            f"--name-only {head[:12]}` lists them") in out.splitlines(), out
    assert next_line(out) == shlex.join(push_argv(project, "bump/spec"))


# --- the dry run, and what it does not run -----------------------------------


def test_a_dry_run_says_the_validators_are_the_real_runs(project, scaffolded,
                                                         advanced):
    """THE ISSUE'S MEASUREMENT: a pin `validate-pins.py` already refuses
    (`yaml-unparsable`, a tab-indented line after a `note:`), committed. The
    dry run previews the move, exit 0, as before, and now says that it runs
    no validator and that the real run can still end red; the real run then
    does, rolled back. No behaviour changes."""
    branched(project)
    pin = project / SPEC_PIN
    pin.write_bytes(pin.read_bytes()
                    + b"note: a remark\n\tindented with a tab\n")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "A pin its validator cannot parse", "--", SPEC_PIN, cwd=project)
    gate = validate(project)
    assert gate.returncode == 2, gate.stdout + gate.stderr
    assert "yaml-unparsable" in gate.stdout + gate.stderr
    head = head_of(project)

    dry = bump(project, scaffolded, advanced, "--dry-run")
    assert dry.returncode == 0, dry.stderr + dry.stdout
    assert NOT_VALIDATED in dry.stdout, dry.stdout

    real = bump(project, scaffolded, advanced)
    assert real.returncode == 2, real.stderr + real.stdout
    assert "REFUSED bump-leg-validators-red" in real.stderr, real.stderr
    assert head_of(project) == head
    assert git("status", "--porcelain", cwd=project).stdout == ""
