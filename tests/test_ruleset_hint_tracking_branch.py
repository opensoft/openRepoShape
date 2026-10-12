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

WHAT IS PINNED HERE
  * the text itself: byte for byte what it was for `main` (the literal below is
    the hint as it stood before this change, with the branch left as a marker),
    and `trunk` in exactly the two places `main` stood, for `trunk`;
  * every one of the five places that prints it passes the branch, run through
    the real tools against local bare remotes that refuse like a ruleset;
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
this change's to fix, so those two assert the text and that the branch the
text names is one the work clone holds.
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
#: with the four values it carries as markers. Raw, because the second command
#: ends in a backslash. It is a literal rather than a copy of the module's own
#: constant so that the test cannot agree with whatever the constant becomes.
HINT = r"""If the organisation applies a ruleset requiring changes to arrive by pull
request, a direct push to the default branch is refused BY DESIGN and must not
be worked around. Two legitimate exits:

  (1) have an operator holding the bypass right seed the default branch once,
      then re-run this scaffold; or
  (2) push a seed BRANCH and open a pull request:
          git -C @WORK@ push -u origin @BRANCH@:seed/scaffold
          gh pr create --repo @REPO@ --base @BRANCH@ --head seed/scaffold \
              --title 'Seed the @ROLE@ leg' --body 'Scaffolded shape.'

NOTHING has been rolled back. What already exists is listed above; delete it
by hand if you want a clean re-run."""


def hint_for(work: str, repo: str, role: str, tracking: str) -> str:
    return (HINT.replace("@WORK@", work).replace("@REPO@", repo)
            .replace("@ROLE@", role).replace("@BRANCH@", tracking))


# --- the text ---------------------------------------------------------------

def test_the_hint_for_main_is_the_text_it_always_was():
    printed = RULESET_HINT.format(work="W", repo="o/r", role="spec",
                                  tracking="main")
    assert printed == "\n" + hint_for("W", "o/r", "spec", "main") + "\n"


def test_the_hint_for_another_branch_changes_that_branch_and_nothing_else():
    printed = RULESET_HINT.format(work="W", repo="o/r", role="spec",
                                  tracking="trunk")
    assert printed == "\n" + hint_for("W", "o/r", "spec", "trunk") + "\n"
    assert "main" not in printed, "no `main` is left in the hint"
    assert printed.count("trunk") == 2, "the local branch and `--base`"
    # The exits are the ones AGENTS.md allows, and `--admin` is not one.
    assert "--admin" not in printed
    assert "bypass right" in printed and "pull request" in printed


def test_the_hint_takes_four_fields_and_the_branch_is_one_of_them():
    fields = {name for _, name, _, _ in string.Formatter().parse(RULESET_HINT)
              if name}
    assert fields == {"work", "repo", "role", "tracking"}


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


def test_no_call_that_prints_the_hint_leaves_the_branch_out():
    calls = hint_calls()
    assert {"scaffold-project.py", "adopt-project.py",
            "scripts/family.py"} <= {path for path, _, _ in calls}, (
        "the scan no longer finds the tools that print the hint, so it is not "
        "reading what it claims to")
    offenders = [f"{path}:{line} names only {sorted(named)}"
                 for path, line, named in calls if "tracking" not in named]
    assert not offenders, (
        "`RULESET_HINT.format` without `tracking=` raises KeyError inside the "
        "failure path that exists to explain a refusal (#324):\n  "
        + "\n  ".join(offenders))


# --- a ruleset in miniature --------------------------------------------------

HOOK = (b"#!/bin/sh\n"
        b"# A ruleset: while RULESET_REFUSES names the repository this runs in,\n"
        b"# a push to anything but a seed/* branch is refused.\n"
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


def refused_run(case: str, tracking: str, tmp_path, template):
    """Run the tool that prints `case`'s hint against remotes that refuse its
    push, with `--tracking-branch <tracking>`; returns the process, the
    directory the remotes are in and the work directory."""
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
        # The source's own default branch IS the tracking branch, as it is
        # wherever the plan's pull request has a base to land on.
        source = make_source_repo(tmp_path / "IRRS", SPEC_ONLY_TREE,
                                  branch=tracking, edits=EDITS)
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


def printed_hint(result, case: str, tracking: str) -> tuple[str, str]:
    """`(the hint block, the work clone it names)`, after checking the block
    is the whole hint with this case's role and repository."""
    assert result.returncode == 2, result.stderr + result.stdout
    start = result.stderr.index("If the organisation applies a ruleset")
    block = result.stderr[start:]
    named = re.search(r"^ +git -C (.+) push -u origin \S+:seed/scaffold$",
                      block, re.M)
    assert named, block
    _, role, repository = CASES[case]
    assert block.startswith(hint_for(named[1], repository, role, tracking)
                            + "\n"), block
    return block, named[1]


@pytest.mark.parametrize("tracking", ["trunk", "main"])
@pytest.mark.parametrize("case", CASES)
def test_the_hint_names_the_tracking_branch_the_run_was_made_with(
        case, tracking, tmp_path, template):
    if case in NEEDS_FILTER_REPO and shutil.which("git-filter-repo") is None:
        pytest.skip("git filter-repo is not installed: "
                    "`pip install git-filter-repo`")
    result, remotes, _ = refused_run(case, tracking, tmp_path, template)
    block, work = printed_hint(result, case, tracking)
    assert f"origin {tracking}:seed/scaffold" in block
    assert f"--base {tracking} --head seed/scaffold" in block
    if tracking != "main":
        # Not the work path: a directory may be called anything.
        assert "main" not in block.replace(work, "<work>"), (
            "the default branch is not this run's")

    # The branch the hint names as the LOCAL one is one the clone holds.
    held = git("rev-parse", "--verify", "-q", f"refs/heads/{tracking}",
               cwd=Path(work), check=False)
    assert held.returncode == 0, (
        f"the work clone has no branch {tracking}: "
        + git("branch", "-a", cwd=Path(work)).stdout)

    # The refusal was real: nothing reached the tracking branch.
    bare = remotes / (CASES[case][0])
    assert git("rev-parse", "--verify", "-q", f"refs/heads/{tracking}",
               cwd=bare, check=False).returncode != 0

    if case in NEEDS_FILTER_REPO:
        return
    # Where the printed command can run, run it: the seed branch arrives, at
    # the commit the work clone holds.
    pushed = subprocess.run(["git", "-C", work, "push", "-u", "origin",
                             f"{tracking}:seed/scaffold"],
                            capture_output=True, text=True, check=False,
                            env={**os.environ, **refusing(template,
                                                          CASES[case][0])})
    assert pushed.returncode == 0, pushed.stderr
    assert git("rev-parse", "refs/heads/seed/scaffold", cwd=bare).stdout == \
        git("rev-parse", f"refs/heads/{tracking}", cwd=Path(work)).stdout
