# SPDX-License-Identifier: Apache-2.0
"""The hint a refused push prints names the run's own tracking branch (#324).

`RULESET_HINT` is what a person reads when an organisation's ruleset has just
refused a direct push, and it says to push a seed BRANCH and open a pull
request. It named `main` twice, as a constant: the local branch in `git -C
<work> push -u origin main:seed/scaffold`, and `gh pr create --base main`. A
run made with `--tracking-branch trunk` creates its work clones with `git init
-b trunk` and pushes `trunk`, so the first command died on `error: src refspec
main does not match any` and the second named a base the repository does not
have.

TWO FIELDS NAME A BRANCH. `{tracking}` is the remote's branch, the base the pull
request lands on. `{local}` is the ref in the work clone that the refused push
CARRIED: the tracking branch where the tool pushed it by name (the scaffold, the
family holder), `HEAD` where it pushed `HEAD:` (both adopt legs). An extracted
leg's clone holds the source's own branch of the tracking branch's name, which
is another commit than the one pushed, so the tracking branch there would seed
a leg with the wrong history once `origin` exists.

WHAT IS PINNED HERE
  * the text itself: byte for byte what it was for `main` (the literal below is
    the hint as it stood before this change, with the two branches left as
    markers), and `trunk` in exactly the two places `main` stood, for `trunk`;
  * every one of the five places that prints it passes both fields, run through
    the real tools against local bare remotes that refuse like a ruleset, and
    the ref the hint names as local is AT the commit the refused push carried:
    the remote's own hook records it;
  * where the printed push is runnable (the scaffold's legs and root, a family
    holder), it is RUN, and the seed branch arrives.

THE RULESET IS A `pre-receive` HOOK in each bare remote the tool makes, put
there by `GIT_TEMPLATE_DIR`, which every `git init` the tool runs honours. The
hook refuses a push to anything but `seed/*` for the repositories named in
`RULESET_REFUSES`: the hook runs in the remote's own directory, so the name
picks which of the three a run sees refuse. It is a shebang script, which Git
for Windows runs through its own `sh` (`test_update_shape_add_ignored.py` does
the same). No `gh`, no network and no real repository is involved.

The extracted and the seeded leg of an ADOPTION print the hint too, and its
`push -u origin` cannot run there: `git filter-repo` removed `origin` from the
extracted clone, and the seeded clone never had one (#177, open). That is not
this change's to fix, so those two assert the text and that the ref the text
names is the commit the refused push carried.
"""

from __future__ import annotations

import ast
import os
import re
import shutil
import string
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, ORG, PROJECT, REPO, SCAFFOLD, git, make_source_repo,
                      resolve, run_script, write_plan)
from test_adopt_spec_only import ANSWERS, EDITS, SPEC_ONLY_TREE
from test_git_output_decoding import shipped_python

sys.path.insert(0, str(REPO / "scripts"))
from shape_materialize import RULESET_HINT  # noqa: E402

FAMILY = REPO / "scripts" / "family.py"

#: The hint as it stood on `main` before #324, from its first line to its last,
#: with the five values it carries as markers (the two branches were one `main`
#: then). Raw, because the second command ends in a backslash. It is a literal rather than a copy of the module's own
#: constant so that the test cannot agree with whatever the constant becomes.
HINT = r"""If the organisation applies a ruleset requiring changes to arrive by pull
request, a direct push to the default branch is refused BY DESIGN and must not
be worked around. Two legitimate exits:

  (1) have an operator holding the bypass right seed the default branch once,
      then re-run this scaffold; or
  (2) push a seed BRANCH and open a pull request:
          git -C @WORK@ push -u origin @LOCAL@:seed/scaffold
          gh pr create --repo @REPO@ --base @BRANCH@ --head seed/scaffold \
              --title 'Seed the @ROLE@ leg' --body 'Scaffolded shape.'

NOTHING has been rolled back. What already exists is listed above; delete it
by hand if you want a clean re-run."""


def hint_for(work: str, repo: str, role: str, local: str,
             tracking: str) -> str:
    return (HINT.replace("@WORK@", work).replace("@REPO@", repo)
            .replace("@ROLE@", role).replace("@LOCAL@", local)
            .replace("@BRANCH@", tracking))


# --- the text ---------------------------------------------------------------

def test_the_hint_for_main_is_the_text_it_always_was():
    printed = RULESET_HINT.format(work="W", repo="o/r", role="spec",
                                  local="main", tracking="main")
    assert printed == "\n" + hint_for("W", "o/r", "spec", "main", "main") + "\n"


def test_the_hint_for_another_branch_changes_that_branch_and_nothing_else():
    printed = RULESET_HINT.format(work="W", repo="o/r", role="spec",
                                  local="trunk", tracking="trunk")
    assert printed == "\n" + hint_for("W", "o/r", "spec", "trunk", "trunk") + "\n"
    assert "main" not in printed, "no `main` is left in the hint"
    assert printed.count("trunk") == 2, "the local branch and `--base`"
    # The exits are the ones AGENTS.md allows, and `--admin` is not one.
    assert "--admin" not in printed
    assert "bypass right" in printed and "pull request" in printed


def test_the_local_ref_and_the_base_are_two_fields():
    """An adoption names `HEAD` where it pushed `HEAD:`, and still lands its
    pull request on the tracking branch."""
    printed = RULESET_HINT.format(work="W", repo="o/r", role="spec",
                                  local="HEAD", tracking="trunk")
    assert printed == "\n" + hint_for("W", "o/r", "spec", "HEAD", "trunk") + "\n"
    assert "origin HEAD:seed/scaffold" in printed
    assert "--base trunk --head seed/scaffold" in printed
    assert "main" not in printed and printed.count("trunk") == 1


def test_the_hint_takes_five_fields_two_of_them_a_branch():
    fields = {name for _, name, _, _ in string.Formatter().parse(RULESET_HINT)
              if name}
    assert fields == {"work", "repo", "role", "local", "tracking"}


# --- every caller passes it --------------------------------------------------

def hint_calls() -> list[tuple[str, int, set]]:
    """Every `RULESET_HINT.format(...)` in the shipped tools, as `(file, line,
    the keywords it names)`."""
    found = []
    for path in shipped_python():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "format"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "RULESET_HINT"):
                found.append((path.relative_to(REPO).as_posix(), node.lineno,
                              {keyword.arg for keyword in node.keywords}))
    return found


def test_no_call_that_prints_the_hint_leaves_a_branch_out():
    fields = {name for _, name, _, _ in string.Formatter().parse(RULESET_HINT)
              if name}
    calls = hint_calls()
    assert {"scaffold-project.py", "adopt-project.py",
            "scripts/family.py"} <= {path for path, _, _ in calls}, (
        "the scan no longer finds the tools that print the hint, so it is not "
        "reading what it claims to")
    offenders = [f"{path}:{line} names only {sorted(named)}"
                 for path, line, named in calls if not fields <= named]
    assert not offenders, (
        "`RULESET_HINT.format` without `local=` or `tracking=` raises KeyError "
        "inside the failure path that exists to explain a refusal (#324):\n  "
        + "\n  ".join(offenders))


# --- a ruleset in miniature --------------------------------------------------

HOOK = (b"#!/bin/sh\n"
        b"# A ruleset: while RULESET_REFUSES names the repository this runs in,\n"
        b"# a push to anything but a seed/* branch is refused, and what it\n"
        b"# refused is written to `refused` in the repository, as `<sha> <ref>`.\n"
        b'here=$(basename "$(pwd)")\n'
        b'case " $RULESET_REFUSES " in\n'
        b'  *" $here "*) ;;\n'
        b"  *) exit 0 ;;\n"
        b"esac\n"
        b"while read old new ref; do\n"
        b'  case "$ref" in\n'
        b"    refs/heads/seed/*) ;;\n"
        b'    *) echo "remote: error: GH013: Repository rule violations found '
        b'for $ref: changes must be made through a pull request." >&2\n'
        b'       echo "$new $ref" >> refused\n'
        b"       exit 1 ;;\n"
        b"  esac\n"
        b"done\n"
        b"exit 0\n")


def refusing(template, *repositories: str) -> dict:
    """The environment under which every bare repository a tool makes refuses
    a direct push, for the repositories named (`Atlas-spec.git`)."""
    return {"GIT_TEMPLATE_DIR": str(template),
            "RULESET_REFUSES": " ".join(repositories)}


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    """A git template directory whose only file is the refusing hook, after
    proving the hook refuses on this machine.

    A machine whose own `core.hooksPath` is set never reads a repository's
    hooks, which would make every test below fail for a reason that is about
    the machine; that, and only that, is a skip. Anything else that lets the
    push through is a failure.
    """
    root = tmp_path_factory.mktemp("ruleset")
    hooks = root / "template" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "pre-receive").write_bytes(HOOK)
    (hooks / "pre-receive").chmod(0o755)
    template = root / "template"
    env = {**os.environ, **refusing(template, "probe.git")}
    bare, work = root / "probe.git", root / "probe"
    work.mkdir()

    def probe(*args, cwd=root):
        return subprocess.run(["git", *args], cwd=str(cwd), env=env,
                              capture_output=True, text=True, check=False)

    assert probe("init", "-q", "--bare", "-b", "trunk", str(bare)).returncode == 0
    assert probe("init", "-q", "-b", "trunk", ".", cwd=work).returncode == 0
    made = probe("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                 "--allow-empty", "-m", "probe", cwd=work)
    assert made.returncode == 0, made.stderr
    direct = probe("push", "-q", str(bare), "HEAD:refs/heads/trunk", cwd=work)
    if direct.returncode == 0:
        hooks_path = probe("config", "--get", "core.hooksPath")
        if hooks_path.stdout.strip():
            pytest.skip("this machine's git sets core.hooksPath, so a "
                        "repository's own hooks are never run and a bare "
                        "remote cannot be made to refuse like a ruleset")
        pytest.fail("the simulated ruleset let a direct push through: "
                    + direct.stderr)
    seed = probe("push", "-q", str(bare), "HEAD:refs/heads/seed/scaffold",
                 cwd=work)
    assert seed.returncode == 0, "the ruleset also refused the seed branch"
    return template


# --- the five places that print it -------------------------------------------

#: What each caller refuses, with the role and repository its hint names.
#: `scaffold-spec` is the first leg's push, `scaffold-root` the assembly
#: root's after both legs went through, `family` the holder's.
CASES = {
    "scaffold-spec": ("Atlas-spec.git", "spec", f"{ORG}/Atlas-spec"),
    "scaffold-root": ("Atlas.git", "assembly", f"{ORG}/Atlas"),
    "family": ("Contoso.git", "family", f"{ORG}/Contoso"),
    "adopt-extracted": ("Redwood-spec.git", "spec", f"{ORG}/Redwood-spec"),
    "adopt-seeded": ("Redwood-code.git", "code", f"{ORG}/Redwood-code"),
}
NEEDS_FILTER_REPO = ("adopt-extracted", "adopt-seeded")


def source_with_a_second_line(path: Path, tracking: str) -> Path:
    """A source whose default branch is `master`, whatever the tracking branch
    is, and which ALSO has a branch of the tracking branch's name: another
    line, one commit behind `master` and with a commit and a spec file of its
    own.
    That is what a source adopted into a tracking branch of another name
    looks like, and it is where the extracted leg's clone holds a branch of
    the tracking branch's name that is not the commit the push carried."""
    source = make_source_repo(path, SPEC_ONLY_TREE, branch="master",
                              edits=EDITS)
    git("checkout", "-q", "-b", tracking, "HEAD~1", cwd=source)
    # A spec path, so the commit survives the extraction of the spec leg.
    (source / "specs" / "001-render" / "second-line.md").write_text(
        "only on this line\n", encoding="utf-8")
    git("add", "specs/001-render/second-line.md", cwd=source)
    git("commit", "-q", "-m", "A second line", cwd=source)
    git("checkout", "-q", "master", cwd=source)
    return source


def refused_run(case: str, tracking: str, tmp_path, template,
                second_line: bool = True):
    """Run the tool that prints `case`'s hint against remotes that refuse its
    push, with `--tracking-branch <tracking>`; returns the process, the
    directory the remotes are in and the work directory. An adoption's source
    is on `master`, with or without a second line of the tracking branch's
    name."""
    refused = CASES[case][0]
    env = refusing(template, refused)
    remotes, work = tmp_path / "remotes", tmp_path / "work"
    where = ("--local-remote-dir", str(remotes), "--work-dir", str(work))
    if case.startswith("scaffold"):
        result = run_script(
            SCAFFOLD, "--org", ORG, "--project", PROJECT,
            "--elected-by", "Test Human", "--elected-on", "2026-09-02",
            "--tracking-branch", tracking, *where, env=env)
    elif case == "family":
        result = run_script(
            FAMILY, "init", "--org", ORG, "--family", "Contoso",
            "--created-by", "Test Human", "--created-on", "2026-09-04",
            "--tracking-branch", tracking, *where, env=env)
    else:
        if second_line:
            source = source_with_a_second_line(tmp_path / "IRRS", tracking)
        else:
            source = make_source_repo(tmp_path / "IRRS", SPEC_ONLY_TREE,
                                      branch="master", edits=EDITS)
        plan = tmp_path / "adoption-plan.yaml"
        written = write_plan(source, plan, project="Redwood",
                             extra=("--tracking-branch", tracking,
                                    "--allow-empty-leg", "code"))
        assert written.returncode == 0, written.stderr + written.stdout
        for path, leg in ANSWERS:
            resolve(plan, path, leg)
        result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                            "--allow-empty-leg", "code", *where, env=env)
    return result, remotes, work


def local_ref(case: str, tracking: str) -> str:
    """The ref each case's hint names: where the tool pushed the tracking
    branch by name, that branch; where it pushed `HEAD:`, `HEAD`."""
    return "HEAD" if case in NEEDS_FILTER_REPO else tracking


def printed_hint(result, case: str, tracking: str) -> tuple[str, str]:
    """`(the hint block, the work clone it names)`, after checking the block
    is the whole hint, with this case's role, repository and local ref."""
    assert result.returncode == 2, result.stderr + result.stdout
    start = result.stderr.index("If the organisation applies a ruleset")
    block = result.stderr[start:]
    named = re.search(r"^ +git -C (.+) push -u origin \S+:seed/scaffold$",
                      block, re.M)
    assert named, block
    _, role, repository = CASES[case]
    assert block.startswith(hint_for(named[1], repository, role,
                                     local_ref(case, tracking), tracking)
                            + "\n"), block
    return block, named[1]


def refused_commit(bare: Path, tracking: str) -> str:
    """The commit the refused push carried, as the remote's own hook saw it:
    exactly one push was refused, and it was to the tracking branch."""
    lines = (bare / "refused").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1, lines
    commit, ref = lines[0].split()
    assert ref == f"refs/heads/{tracking}", lines
    return commit


def commit_of(ref: str, work: str) -> str:
    return git("rev-parse", "--verify", "-q", f"{ref}^{{commit}}",
               cwd=Path(work), check=False).stdout.strip()


@pytest.mark.parametrize("tracking", ["trunk", "main"])
@pytest.mark.parametrize("case", CASES)
def test_the_hint_names_the_tracking_branch_the_run_was_made_with(
        case, tracking, tmp_path, template):
    if case in NEEDS_FILTER_REPO and shutil.which("git-filter-repo") is None:
        pytest.skip("git filter-repo is not installed: "
                    "`pip install git-filter-repo`")
    result, remotes, _ = refused_run(case, tracking, tmp_path, template)
    block, work = printed_hint(result, case, tracking)
    local = local_ref(case, tracking)
    assert f"origin {local}:seed/scaffold" in block
    assert f"--base {tracking} --head seed/scaffold" in block
    if tracking != "main":
        # Not the work path: a directory may be called anything.
        assert "main" not in block.replace(work, "<work>"), (
            "the default branch is not this run's")

    # The refusal was real: nothing reached the tracking branch, and the one
    # push the remote refused is the one the hint is about.
    bare = remotes / (CASES[case][0])
    assert git("rev-parse", "--verify", "-q", f"refs/heads/{tracking}",
               cwd=bare, check=False).returncode != 0
    pushed = refused_commit(bare, tracking)

    # THE LOCAL REF THE HINT NAMES IS AT THE COMMIT THE REFUSED PUSH CARRIED,
    # which is what advising it to be pushed to `seed/scaffold` means.
    assert commit_of(local, work) == pushed, (
        f"`{local}` in the work clone is not what was pushed: "
        + git("branch", "-a", "-v", cwd=Path(work)).stdout)
    if case == "adopt-extracted":
        # The scenario is the one that bites: the clone also holds the
        # source's own `<tracking>`, another commit than the one pushed.
        assert commit_of(tracking, work) not in ("", pushed), (
            "the source's second line is not in the extracted clone, so this "
            "run cannot tell `HEAD` from the tracking branch")

    if case in NEEDS_FILTER_REPO:
        return
    # Where the printed command can run, run it: the seed branch arrives, at
    # the commit the work clone holds.
    ran = subprocess.run(["git", "-C", work, "push", "-u", "origin",
                          f"{local}:seed/scaffold"],
                         capture_output=True, text=True, check=False,
                         env={**os.environ, **refusing(template,
                                                       CASES[case][0])})
    assert ran.returncode == 0, ran.stderr
    assert git("rev-parse", "refs/heads/seed/scaffold",
               cwd=bare).stdout.strip() == pushed


@pytest.mark.parametrize("tracking", ["trunk", "main"])
def test_an_extracted_leg_names_what_it_pushed_when_the_source_has_no_such_branch(
        tracking, tmp_path, template):
    """A source on `master` adopted into `--tracking-branch <tracking>` has no
    branch of that name for its clone to hold: the clone has `master` and the
    adopt branch only. The hint must still name a ref the clone has, and it is
    `HEAD`, the commit the refused push carried."""
    if shutil.which("git-filter-repo") is None:
        pytest.skip("git filter-repo is not installed: "
                    "`pip install git-filter-repo`")
    result, remotes, _ = refused_run("adopt-extracted", tracking, tmp_path,
                                     template, second_line=False)
    block, work = printed_hint(result, "adopt-extracted", tracking)
    assert "origin HEAD:seed/scaffold" in block
    assert f"--base {tracking} --head seed/scaffold" in block
    pushed = refused_commit(remotes / CASES["adopt-extracted"][0], tracking)
    assert commit_of("HEAD", work) == pushed
    assert commit_of(tracking, work) == "", (
        "the clone has a branch of the tracking branch's name after all, so "
        "this run does not show what it is meant to: "
        + git("branch", "-a", cwd=Path(work)).stdout)
