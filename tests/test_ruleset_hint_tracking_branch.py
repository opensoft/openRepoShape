# SPDX-License-Identifier: Apache-2.0
"""The hint a refused push prints names the run's own tracking branch (#324),
and offers only the exit that finishes the run (#462).

`RULESET_HINT` is what a person reads when an organisation's ruleset has just
refused a direct push. It named `main` as a constant, so a run made with
`--tracking-branch trunk` was told about a branch it never had (#324). It also
offered two exits, and neither could finish (#462): a seed branch and a pull
request, whose base did not exist because the refused push was the first into
a repository `gh repo create` had just made without a README; and an
operator's seed of the default branch followed by a re-run, which the
scaffold refused as `scaffold-remote-exists` for its own legs, flag or no
flag. Brett Heap ruled on 2026-10-12: "Offer only exits that work", "Re-run
reuses empty legs" and "Accept the scaffold's own seed".

ONE EXIT EACH, NAMED BY THE TOOL THAT PRINTS IT. The scaffold's
(`RULESET_HINT`) and `family.py init`'s (`FAMILY_RULESET_HINT`) are the same
command re-run with `--reuse-empty-repo` by an operator holding the bypass
right, whose own pushes are the seed. An adoption's (`ADOPT_RULESET_HINT`, in
`adopt-project.py`, #445's) is a re-run once what its notice names is cleared,
its two legs first: it has no such flag, and a re-run into them is
`leg-remote-exists`. Each names the pull
request only as what cannot finish it, with the run's repository and its
tracking branch: those are the two fields every hint takes.

WHAT IS PINNED HERE
  * each text, byte for byte, as a literal below with the two values as
    markers, for `main` and for `trunk`;
  * every call that prints one passes both fields, and each tool prints its
    own;
  * run through the real tools against local bare remotes that refuse like a
    ruleset, each of the six places prints its tool's text after a push to
    the tracking branch was really refused;
  * THE EXIT IT OFFERS IS TAKEN, with the ruleset off standing in for the
    operator's bypass, and it FINISHES: the scaffold re-run pushes all three
    repositories, a leg the first run had pushed kept at its commit; the
    holder is pushed; the adoption verifies.

THE RULESET IS A `pre-receive` HOOK in each bare remote the tool makes, put
there by `GIT_TEMPLATE_DIR`, which every `git init` the tool runs honours. The
hook refuses a push to anything but `seed/*` for the repositories named in
`RULESET_REFUSES`: the hook runs in the remote's own directory, so the name
picks which of the three a run sees refuse, and an empty `RULESET_REFUSES` is
the operator. It is a shebang script, which Git for Windows runs through its
own `sh` (`test_update_shape_add_ignored.py` does the same). No `gh`, no
network and no real repository is involved.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import shutil
import string
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, ORG, PROJECT, REPO, SCAFFOLD, git, make_source_repo,
                      resolve, rmtree, run_script, write_plan)
from test_adopt_spec_only import ANSWERS, EDITS, SPEC_ONLY_TREE
from test_git_output_decoding import shipped_python

sys.path.insert(0, str(REPO / "scripts"))
from shape_materialize import FAMILY_RULESET_HINT, RULESET_HINT  # noqa: E402

FAMILY = REPO / "scripts" / "family.py"


def _adopt_module():
    spec = importlib.util.spec_from_file_location("adopt_ruleset_hint", ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ADOPT_RULESET_HINT = _adopt_module().ADOPT_RULESET_HINT

#: Each tool's hint, from its first line to its last, with the two values it
#: carries as markers. Literals rather than copies of the constants, so that
#: the test cannot agree with whatever a constant becomes.
SCAFFOLD_TEXT = """If the organisation applies a ruleset requiring changes to arrive by pull
request, a direct push to the default branch is refused BY DESIGN and must not
be worked around. ONE exit finishes this scaffold: an operator holding the
bypass right re-runs it, the same command with --reuse-empty-repo added (after
`--` through setup.sh) and a new --work-dir or none. That run's own pushes are
the seed, so push nothing first: it reuses each repository this run left
empty, and a leg whose one commit is the seed this scaffold pushes, and it
refuses a repository that holds anything else. A seed branch and a pull
request cannot finish it: @REPO@ has no @BRANCH@ for that pull request to
target.

NOTHING has been rolled back. What already exists is listed above; delete it
by hand if you want a clean re-run."""

FAMILY_TEXT = """If the organisation applies a ruleset requiring changes to arrive by pull
request, a direct push to the default branch is refused BY DESIGN and must not
be worked around. ONE exit finishes this family: an operator holding the
bypass right re-runs `family.py init`, the same command with
--reuse-empty-repo added and a new --into or --work-dir. That run's own push
is the seed, so push nothing first: it reuses the holder while it is empty,
and refuses it once it has a commit. A seed branch and a pull request cannot
finish it: @REPO@ has no @BRANCH@ for that pull request to target.

NOTHING has been rolled back. What already exists is listed above; delete it
by hand if you want a clean re-run."""

ADOPT_TEXT = """If the organisation applies a ruleset requiring changes to arrive by pull
request, a direct push to the default branch is refused BY DESIGN and must not
be worked around. An adoption has ONE legitimate exit: have an operator
holding the bypass right re-run it, once what the notice below names is
cleared. The scaffold's other exit, a seed branch and a pull request, cannot
finish an adoption: @REPO@ has no @BRANCH@ for that pull request to target,
and nothing would run the rest of this adoption after it was merged. Under
such a ruleset, that bypass is the fix the notice below asks for, never a
change to the ruleset."""

#: Each constant, the name a tool prints it by, and its literal.
HINTS = {
    "RULESET_HINT": (RULESET_HINT, SCAFFOLD_TEXT),
    "FAMILY_RULESET_HINT": (FAMILY_RULESET_HINT, FAMILY_TEXT),
    "ADOPT_RULESET_HINT": (ADOPT_RULESET_HINT, ADOPT_TEXT),
}

#: Which hint each shipped tool prints, and only that one.
PRINTED_BY = {
    "scaffold-project.py": "RULESET_HINT",
    "scripts/family.py": "FAMILY_RULESET_HINT",
    "adopt-project.py": "ADOPT_RULESET_HINT",
}


def text_for(name: str, repo: str, tracking: str) -> str:
    return (HINTS[name][1].replace("@REPO@", repo)
            .replace("@BRANCH@", tracking))


# --- the text ---------------------------------------------------------------

@pytest.mark.parametrize("name", HINTS)
def test_each_hint_for_main_is_its_text(name):
    printed = HINTS[name][0].format(repo="o/r", tracking="main")
    assert printed == "\n" + text_for(name, "o/r", "main") + "\n"


@pytest.mark.parametrize("name", HINTS)
def test_each_hint_for_another_branch_changes_that_branch_and_nothing_else(
        name):
    printed = HINTS[name][0].format(repo="o/r", tracking="trunk")
    assert printed == "\n" + text_for(name, "o/r", "trunk") + "\n"
    assert "main" not in printed, "no `main` is left in the hint"
    assert printed.count("trunk") == 1, "the base the pull request lacks"
    # ONE exit, the one AGENTS.md allows, and `--admin` is not it.
    assert "--admin" not in printed
    assert "ONE" in printed and "bypass right" in printed
    # The pull request is named only as what cannot finish the run: no
    # command to push a seed branch or open one is printed (#462).
    assert "seed/scaffold" not in printed
    assert "gh pr create" not in printed
    assert "push -u" not in printed
    assert "Two legitimate exits" not in printed


def test_the_scaffold_and_the_family_re_run_with_the_flag_and_adoption_not():
    """`--reuse-empty-repo` is the scaffold's and `family.py init`'s; an
    adoption has no such flag, so its hint must not send anybody to one."""
    scaffold = RULESET_HINT.format(repo="o/r", tracking="main")
    family = FAMILY_RULESET_HINT.format(repo="o/r", tracking="main")
    adoption = ADOPT_RULESET_HINT.format(repo="o/r", tracking="main")
    assert "--reuse-empty-repo" in scaffold
    assert "--reuse-empty-repo" in family and "family.py init" in family
    assert "--reuse-empty-repo" not in adoption
    assert "re-run this scaffold" not in family + adoption


@pytest.mark.parametrize("name", HINTS)
def test_each_hint_takes_two_fields_the_repository_and_the_branch(name):
    fields = {field for _, field, _, _ in
              string.Formatter().parse(HINTS[name][0]) if field}
    assert fields == {"repo", "tracking"}


# --- every caller passes it --------------------------------------------------

def hint_calls() -> list[tuple[str, int, str, set]]:
    """Every `<hint>.format(...)` in the shipped tools, as `(file, line, the
    hint's name, the keywords it names)`."""
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


def test_each_tool_prints_its_own_hint_and_passes_both_fields():
    calls = hint_calls()
    assert set(PRINTED_BY) <= {path for path, _, _, _ in calls}, (
        "the scan no longer finds the tools that print the hint, so it is not "
        "reading what it claims to")
    wrong = [f"{path}:{line} prints {name}" for path, line, name, _ in calls
             if PRINTED_BY.get(path, name) != name]
    assert not wrong, (
        "each tool names its own exit; another tool's hint sends the person "
        "to a flag or a command this one does not have (#462):\n  "
        + "\n  ".join(wrong))
    offenders = [f"{path}:{line} names only {sorted(named)}"
                 for path, line, _, named in calls
                 if named != {"repo", "tracking"}]
    assert not offenders, (
        "a hint's `.format` without `repo=` or `tracking=` raises KeyError "
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
    a direct push, for the repositories named (`Atlas-spec.git`). Named none,
    it is the operator holding the bypass right: the hooks are there and
    refuse nothing."""
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


# --- the six places that print one ------------------------------------------

#: What each caller refuses, with the hint it prints and the repository that
#: hint names. `scaffold-spec` is the first leg's push, `scaffold-code` the
#: second's after the first went through, `scaffold-root` the assembly
#: root's after both legs went through, `family` the holder's.
CASES = {
    "scaffold-spec": ("Atlas-spec.git", "RULESET_HINT", f"{ORG}/Atlas-spec"),
    "scaffold-code": ("Atlas-code.git", "RULESET_HINT", f"{ORG}/Atlas-code"),
    "scaffold-root": ("Atlas.git", "RULESET_HINT", f"{ORG}/Atlas"),
    "family": ("Contoso.git", "FAMILY_RULESET_HINT", f"{ORG}/Contoso"),
    "adopt-extracted": ("Redwood-spec.git", "ADOPT_RULESET_HINT",
                        f"{ORG}/Redwood-spec"),
    "adopt-seeded": ("Redwood-code.git", "ADOPT_RULESET_HINT",
                     f"{ORG}/Redwood-code"),
}
NEEDS_FILTER_REPO = ("adopt-extracted", "adopt-seeded")
SCAFFOLDED = (f"{PROJECT}.git", f"{PROJECT}-spec.git", f"{PROJECT}-code.git")


def run_the_tool(case: str, tracking: str, tmp_path, env: dict, work: Path,
                 *extra: str):
    """Run the tool that prints `case`'s hint into `work`, against the
    remotes in `tmp_path / "remotes"`, with `--tracking-branch <tracking>`.
    An adoption's source is on `master` and its plan is written once."""
    where = ("--local-remote-dir", str(tmp_path / "remotes"),
             "--work-dir", str(work))
    if case.startswith("scaffold"):
        return run_script(
            SCAFFOLD, "--org", ORG, "--project", PROJECT,
            "--elected-by", "Test Human", "--elected-on", "2026-09-02",
            "--tracking-branch", tracking, *where, *extra, env=env)
    if case == "family":
        return run_script(
            FAMILY, "init", "--org", ORG, "--family", "Contoso",
            "--created-by", "Test Human", "--created-on", "2026-09-04",
            "--tracking-branch", tracking, *where, *extra, env=env)
    plan = tmp_path / "adoption-plan.yaml"
    if not plan.exists():
        source = make_source_repo(tmp_path / "IRRS", SPEC_ONLY_TREE,
                                  branch="master", edits=EDITS)
        written = write_plan(source, plan, project="Redwood",
                             extra=("--tracking-branch", tracking,
                                    "--allow-empty-leg", "code"))
        assert written.returncode == 0, written.stderr + written.stdout
        for path, leg in ANSWERS:
            resolve(plan, path, leg)
    return run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                      "--allow-empty-leg", "code", *where, *extra, env=env)


def refused_commit(bare: Path, tracking: str) -> str:
    """The commit the refused push carried, as the remote's own hook saw it:
    exactly one push was refused, and it was to the tracking branch."""
    lines = (bare / "refused").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1, lines
    commit, ref = lines[0].split()
    assert ref == f"refs/heads/{tracking}", lines
    return commit


def tip(bare: Path, tracking: str) -> str:
    return git("rev-parse", "--verify", "-q", f"refs/heads/{tracking}",
               cwd=bare, check=False).stdout.strip()


@pytest.mark.parametrize("tracking", ["trunk", "main"])
@pytest.mark.parametrize("case", CASES)
def test_the_hint_names_one_exit_and_taking_it_finishes_the_run(
        case, tracking, tmp_path, template):
    if case in NEEDS_FILTER_REPO and shutil.which("git-filter-repo") is None:
        pytest.skip("git filter-repo is not installed: "
                    "`pip install git-filter-repo`")
    refused, name, repository = CASES[case]
    remotes = tmp_path / "remotes"
    result = run_the_tool(case, tracking, tmp_path,
                          refusing(template, refused), tmp_path / "work")

    # The tool's own hint, for this repository and this tracking branch.
    assert result.returncode == 2, result.stderr + result.stdout
    start = result.stderr.index("If the organisation applies a ruleset")
    block = result.stderr[start:]
    assert block.startswith(text_for(name, repository, tracking) + "\n"), block
    if tracking != "main":
        assert "main" not in block, "the default branch is not this run's"

    # The refusal was real: the one push the remote refused went to the
    # tracking branch, and nothing reached it.
    bare = remotes / refused
    refused_commit(bare, tracking)
    assert tip(bare, tracking) == ""
    if case.startswith("scaffold"):
        before = {repo: tip(remotes / repo, tracking) for repo in SCAFFOLDED}

    # THE EXIT, TAKEN: the ruleset off is the operator holding the bypass
    # right, and the run is made again as the hint says.
    operator = refusing(template)
    if case.startswith("scaffold") or case == "family":
        again = run_the_tool(case, tracking, tmp_path, operator,
                             tmp_path / "again", "--reuse-empty-repo")
    else:
        unfinished = run_the_tool(case, tracking, tmp_path, operator,
                                  tmp_path / "unfinished")
        assert unfinished.returncode == 2, unfinished.stdout
        assert "already exists" in unfinished.stderr, (
            "the hint says a re-run is refused while the legs exist")
        for leg in ("Redwood-spec.git", "Redwood-code.git"):
            rmtree(remotes / leg)
        again = run_the_tool(case, tracking, tmp_path, operator,
                             tmp_path / "again")
    assert again.returncode == 0, again.stderr + again.stdout

    if case == "family":
        assert tip(bare, tracking)
        return
    if case in NEEDS_FILTER_REPO:
        assert "adoption verified" in again.stdout
        return
    # Every repository is pushed, each holds ONE commit, and a leg the first
    # run had pushed is where that run left it: reused, never rewritten.
    for repo in SCAFFOLDED:
        assert tip(remotes / repo, tracking), repo
        assert git("rev-list", "--count", "--all",
                   cwd=remotes / repo).stdout.strip() == "1", repo
        if before[repo]:
            assert tip(remotes / repo, tracking) == before[repo], repo
    root = remotes / f"{PROJECT}.git"
    for leg in ("spec", "code"):
        mounted = git("rev-parse", f"refs/heads/{tracking}:{leg}",
                      cwd=root).stdout.strip()
        assert mounted == tip(remotes / f"{PROJECT}-{leg}.git", tracking), leg
