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
CARRIED. The three places that print `RULESET_HINT` (the scaffold's legs, its
assembly root, the family holder) push the tracking branch by name from a clone
made on it, so each passes the tracking branch for both.

AN ADOPTION PRINTS ITS OWN HINT, `ADOPT_RULESET_HINT` in `adopt-project.py`
(#177), from both of its legs. It prints no command, and names the tracking
branch once: as the branch the new leg has no pull request base on. The rule is
the same there, the run's own tracking branch and never `main`. Its prose is
#177's, pinned by #177's own tests; what is pinned here is the branch.

WHAT IS PINNED HERE
  * the text itself: byte for byte what it was for `main` (the literal below is
    the hint as it stood before this change, with the two branches left as
    markers), and `trunk` in exactly the two places `main` stood, for `trunk`;
    and the adoption's hint holds no `main` of its own;
  * every one of the five places that prints a hint passes every field of it,
    run through the real tools against local bare remotes that refuse like a
    ruleset. For the scaffold and the family holder, the ref the hint names as
    local is AT the commit the refused push carried: the remote's own hook
    records it. For both adopt legs, the hint printed is the adoption's, for
    that leg's repository and the run's tracking branch, from a source whose
    own branch is `master` whatever the tracking branch is;
  * where the printed push is runnable (the scaffold's legs and root, a family
    holder), it is RUN, and the seed branch arrives.

THE RULESET IS A `pre-receive` HOOK in each bare remote the tool makes, put
there by `GIT_TEMPLATE_DIR`, which every `git init` the tool runs honours. The
hook refuses a push to anything but `seed/*` for the repositories named in
`RULESET_REFUSES`: the hook runs in the remote's own directory, so the name
picks which of the three a run sees refuse. It is a shebang script, which Git
for Windows runs through its own `sh` (`test_update_shape_add_ignored.py` does
the same). No `gh`, no network and no real repository is involved.
"""

from __future__ import annotations

import ast
import importlib.util
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


def _adopt_module():
    """`adopt-project.py` as a module, for its hint: its name is not one
    `import` takes."""
    spec = importlib.util.spec_from_file_location("adopt_ruleset_hint", ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ADOPT_RULESET_HINT = _adopt_module().ADOPT_RULESET_HINT

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
    assert "bypass right" in printed
    assert "pull request" in printed


def test_the_local_ref_and_the_base_are_two_fields():
    """A local ref that is not the tracking branch (`HEAD`, for a push of
    `HEAD:`) stands in the push alone, and the pull request still lands on
    the tracking branch."""
    printed = RULESET_HINT.format(work="W", repo="o/r", role="spec",
                                  local="HEAD", tracking="trunk")
    assert printed == "\n" + hint_for("W", "o/r", "spec", "HEAD", "trunk") + "\n"
    assert "origin HEAD:seed/scaffold" in printed
    assert "--base trunk --head seed/scaffold" in printed
    assert "main" not in printed
    assert printed.count("trunk") == 1


def fields_of(hint: str) -> set:
    return {name for _, name, _, _ in string.Formatter().parse(hint) if name}


def test_the_hint_takes_five_fields_two_of_them_a_branch():
    assert fields_of(RULESET_HINT) == {"work", "repo", "role", "local",
                                       "tracking"}


def test_the_adoption_hint_names_the_tracking_branch_and_no_main():
    """`ADOPT_RULESET_HINT` is #177's, and #324's rule holds of it: its one
    branch is the `{tracking}` field, and no `main` is written into it, so
    the text for another branch is the text for `main` with that branch in
    the one place `main` stood."""
    assert "main" not in ADOPT_RULESET_HINT
    assert "tracking" in fields_of(ADOPT_RULESET_HINT)
    printed = ADOPT_RULESET_HINT.format(repo="o/r", tracking="trunk")
    assert "main" not in printed
    assert printed.count("trunk") == 1, "the base the pull request lacks"
    assert ("o/r has no trunk for that pull request"
            in " ".join(printed.split()))
    assert (ADOPT_RULESET_HINT.format(repo="o/r", tracking="main")
            == printed.replace("trunk", "main"))


# --- every caller passes it --------------------------------------------------

#: Each hint a shipped tool prints, by the name it prints it by.
HINTS = {"RULESET_HINT": RULESET_HINT,
         "ADOPT_RULESET_HINT": ADOPT_RULESET_HINT}


def hint_calls() -> list[tuple[str, int, str, set]]:
    """Every `RULESET_HINT.format(...)` and `ADOPT_RULESET_HINT.format(...)`
    in the shipped tools, as `(file, line, the hint, the keywords it
    names)`."""
    found = []
    for path in shipped_python():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "format"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id in HINTS):
                found.append((path.relative_to(REPO).as_posix(), node.lineno,
                              node.func.value.id,
                              {keyword.arg for keyword in node.keywords}))
    return found


def test_no_call_that_prints_the_hint_leaves_a_branch_out():
    calls = hint_calls()
    assert {("scaffold-project.py", "RULESET_HINT"),
            ("scripts/family.py", "RULESET_HINT"),
            ("adopt-project.py", "ADOPT_RULESET_HINT")} <= {
                (path, hint) for path, _, hint, _ in calls}, (
        "the scan no longer finds the tools that print the hint, so it is not "
        "reading what it claims to")
    offenders = [f"{path}:{line} names only {sorted(named)} of {hint}"
                 for path, line, hint, named in calls
                 if not fields_of(HINTS[hint]) <= named]
    assert not offenders, (
        "a hint's `.format` without `local=` or `tracking=` raises KeyError "
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


# --- the five places that print one ------------------------------------------

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
#: The adoption's two legs: they need `git filter-repo`, and they print
#: `ADOPT_RULESET_HINT`, which names no command (#177).
ADOPTION = ("adopt-extracted", "adopt-seeded")
#: The three that print `RULESET_HINT`, having pushed the tracking branch by
#: name.
PUSHED_BY_NAME = tuple(case for case in CASES if case not in ADOPTION)


def refused_run(case: str, tracking: str, tmp_path, template):
    """Run the tool that prints `case`'s hint against remotes that refuse its
    push, with `--tracking-branch <tracking>`; returns the process, the
    directory the remotes are in and the work directory. An adoption's source
    is on `master`, whatever the tracking branch is."""
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


def printed_hint(result, case: str, tracking: str) -> tuple[str, str]:
    """`(the hint block, the work clone it names)`, after checking the block
    is the whole hint, with this case's role and repository, and the tracking
    branch as both the local ref and the base."""
    assert result.returncode == 2, result.stderr + result.stdout
    start = result.stderr.index("If the organisation applies a ruleset")
    block = result.stderr[start:]
    named = re.search(r"^ +git -C (.+) push -u origin \S+:seed/scaffold$",
                      block, re.M)
    assert named, block
    _, role, repository = CASES[case]
    assert block.startswith(hint_for(named[1], repository, role, tracking,
                                     tracking) + "\n"), block
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


def nothing_reached(bare: Path, tracking: str) -> str:
    """The refusal was real: nothing reached the tracking branch, and the one
    push the remote refused went to it. Returns the commit it carried."""
    assert git("rev-parse", "--verify", "-q", f"refs/heads/{tracking}",
               cwd=bare, check=False).returncode != 0
    return refused_commit(bare, tracking)


@pytest.mark.parametrize("tracking", ["trunk", "main"])
@pytest.mark.parametrize("case", PUSHED_BY_NAME)
def test_the_hint_names_the_tracking_branch_the_run_was_made_with(
        case, tracking, tmp_path, template):
    result, remotes, _ = refused_run(case, tracking, tmp_path, template)
    block, work = printed_hint(result, case, tracking)
    assert f"origin {tracking}:seed/scaffold" in block
    assert f"--base {tracking} --head seed/scaffold" in block
    if tracking != "main":
        # Not the work path: a directory may be called anything.
        assert "main" not in block.replace(work, "<work>"), (
            "the default branch is not this run's")

    bare = remotes / (CASES[case][0])
    pushed = nothing_reached(bare, tracking)

    # THE LOCAL REF THE HINT NAMES IS AT THE COMMIT THE REFUSED PUSH CARRIED,
    # which is what advising it to be pushed to `seed/scaffold` means.
    assert commit_of(tracking, work) == pushed, (
        f"`{tracking}` in the work clone is not what was pushed: "
        + git("branch", "-a", "-v", cwd=Path(work)).stdout)

    # The printed command can run here, so run it: the seed branch arrives,
    # at the commit the work clone holds.
    ran = subprocess.run(["git", "-C", work, "push", "-u", "origin",
                          f"{tracking}:seed/scaffold"],
                         capture_output=True, text=True, check=False,
                         env={**os.environ, **refusing(template,
                                                       CASES[case][0])})
    assert ran.returncode == 0, ran.stderr
    assert git("rev-parse", "refs/heads/seed/scaffold",
               cwd=bare).stdout.strip() == pushed


@pytest.mark.parametrize("tracking", ["trunk", "main"])
@pytest.mark.parametrize("case", ADOPTION)
def test_an_adoption_hint_names_the_tracking_branch_the_run_was_made_with(
        case, tracking, tmp_path, template):
    """Both adopt legs print the adoption's own hint (#177), for the leg's
    repository and the run's tracking branch: never `main` for another
    branch, and never the source's own branch, which is `master` here."""
    if shutil.which("git-filter-repo") is None:
        pytest.skip("git filter-repo is not installed: "
                    "`pip install git-filter-repo`")
    result, remotes, _ = refused_run(case, tracking, tmp_path, template)
    assert result.returncode == 2, result.stderr + result.stdout
    refused, _, repository = CASES[case]
    hint = ADOPT_RULESET_HINT.format(repo=repository,
                                     tracking=tracking).lstrip("\n")
    start = result.stderr.index("If the organisation applies a ruleset")
    printed = result.stderr[start:start + len(hint)]
    assert printed == hint, result.stderr
    assert (f"{repository} has no {tracking} for that pull request"
            in " ".join(printed.split()))
    assert "master" not in printed, "the source's branch is not the leg's"
    if tracking != "main":
        assert "main" not in printed, "the default branch is not this run's"
    nothing_reached(remotes / refused, tracking)
