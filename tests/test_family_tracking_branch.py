# SPDX-License-Identifier: Apache-2.0
"""`add`, `bump` and `remove` commit on a BRANCH, and say which (#487).

AGENTS.md says each of the three writes ONE commit, to land as a pull
request and never as a push to the default branch, and no step made the
branch that pull request needs. After `init` the holder stands on its
tracking branch, and all three committed straight onto it; `add` printed
`NEXT  git -C <holder> push -u origin <branch> && open a pull request`, a
placeholder no repository has (`error: src refspec family/add-atlas does not
match any`, exit 1), even on a branch; and `bump` and `remove` printed no
NEXT at all. `bump-leg.py` refuses exactly this for a leg
(`bump-leg-on-tracking-branch`).

So, as `bump-leg.py` does: the REAL run of each refuses the holder's tracking
branch (`family-on-tracking-branch`) and a HEAD on no branch
(`family-holder-detached`), before the member is read or anything is
written, with the `git -C <holder> switch -c <branch>` that makes one,
quoted; `--dry-run` runs anywhere and says what the real run would do; and
each act that commits ends with ONE pasteable line pushing the branch it
committed on, then the pull request it is for.

THE PROOF IS THE PRINTED LINES, RUN. The remedy's `switch` is split the way
the reader's shell splits it (`shlex`, or PowerShell's reading on Windows,
the dialect `repo_shape.shell_quoted` speaks there) and run; the act is run
again and goes through; its NEXT is split and run, and the holder's remote
then has the branch at the commit the act wrote.

THE BRANCH IS READ AS GIT WROTE IT (#765): a trailing no-break space stays
on it, and a name that is not UTF-8 is refused by name
(`family-branch-not-utf8`), since no line could spell it.

THE SAME FAMILY AS `test_family.py`, in a private copy put back on its
tracking branch, which is where `init` leaves a holder. The remote a push
reaches is this module's own instance of the fixture's, and every branch a
test pushes there is deleted again.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from conftest import (NOT_UTF_8_BRANCH_NAMED, REPO, git, held_by_git,
                      on_a_branch_that_is_not_utf_8, run_script)
#: The family fixture, its names and the work branch it grows the holder on,
#: imported from the module that owns them.
from test_family import (  # noqa: F401
    FAMILY, NAME, ORG, SPARE, WORK_BRANCH, family, manifest, validate,
)
#: The shell's reading of a printed line on this host, owned by #486's tests.
from test_family_printed_quoting import host_words

TRACKING = "main"


@pytest.fixture
def on_main(family, tmp_path):
    """A private copy of the holder, back on its tracking branch with every
    member the fixture added: what a person has after `init`, or after
    pulling `main` once the last pull request landed."""
    holder = tmp_path / NAME
    shutil.copytree(family["root"], holder, symlinks=True)
    git("switch", "-q", "-C", TRACKING, cwd=holder)
    assert git("status", "--porcelain", cwd=holder).stdout == ""
    return holder.resolve()


def older_commit(family, project: str = "IRRS") -> str:
    """A commit of the member that is not the one the family pins: the
    fixture pins each member's tip, and its parent is the scaffold's own."""
    return git("rev-parse", "main~1",
               cwd=family["remotes"] / f"{project}.git").stdout.strip()


def act(family, holder, verb: str, *extra: str):
    """`verb` against `holder`, as a person types it."""
    if verb == "add":
        args = ["--member", f"{ORG}/{SPARE}",
                "--local-remote-dir", str(family["remotes"])]
    elif verb == "bump":
        args = ["--member", "IRRS", "--to", older_commit(family)]
    else:
        args = ["--member", "IRSS"]
    return run_script(FAMILY, verb, "--family-root", str(holder), *args,
                      *extra)


#: The branch each act's refusal suggests: `family/<verb>-<member>`, the
#: member by its row's id, and the commit's first twelve for `bump`.
def suggested(family, verb: str) -> str:
    if verb == "add":
        return f"family/add-{SPARE.lower()}"
    if verb == "bump":
        return f"family/bump-irrs-{older_commit(family)[:12]}"
    return "family/remove-irss"


def snapshot(holder) -> dict:
    return {"head": git("rev-parse", "HEAD", cwd=holder).stdout,
            "branch": git("symbolic-ref", "-q", "HEAD", cwd=holder,
                          check=False).stdout,
            "index": git("ls-files", "-s", cwd=holder).stdout,
            "status": git("status", "--porcelain", cwd=holder).stdout,
            "manifest": (holder / "family.yaml").read_bytes(),
            "modules": sorted(p.name for p in
                              (holder / ".git" / "modules" / "members")
                              .iterdir())}


def remedy_switch(stderr: str) -> list[str]:
    """The remedy's command line, as the reader's shell reads it."""
    lines = stderr.splitlines()
    at = next(i for i, line in enumerate(lines)
              if line.startswith("Remediation: ")
              and line.endswith("run the same command again:"))
    return host_words(lines[at + 1])


def next_push(stdout: str) -> tuple[list[str], str]:
    """The NEXT line, as the reader's shell reads it, and the line under
    it."""
    lines = stdout.splitlines()
    at = next(i for i, line in enumerate(lines) if line.startswith("NEXT  "))
    return host_words(lines[at][len("NEXT  "):]), lines[at + 1]


def refspec(branch: str) -> str:
    """The word the NEXT push ends with (#689): the branch by its full
    refname on both sides, which no `+`, tag or checked-out branch can
    change the reading of."""
    return f"refs/heads/{branch}:refs/heads/{branch}"


@pytest.mark.parametrize("verb", ["add", "bump", "remove"])
def test_each_act_refuses_the_tracking_branch_then_lands_on_a_branch(
        family, on_main, verb):
    """THE ISSUE, END TO END, for each of the three acts: refused on `main`
    with the holder exactly as it was; the printed `switch` makes the
    branch; the act goes through on it; its printed NEXT pushes that
    branch, which the remote then holds at the act's commit."""
    holder = on_main
    before = snapshot(holder)
    refused = act(family, holder, verb)
    assert refused.returncode == 2, refused.stdout + refused.stderr
    # Not one line on stdout: for `add`, not even the line that says the
    # member is being read, so nothing was cloned either.
    assert refused.stdout == ""
    assert (f"REFUSED family-on-tracking-branch: {holder} is on "
            f"'{TRACKING}', which family.yaml declares as the holder's "
            f"tracking branch, and `{verb}` will not write a commit whose "
            "only next step is a push to the default branch. No git command "
            "that writes was run and nothing was written."
            in refused.stderr), refused.stderr
    assert snapshot(holder) == before

    branch = suggested(family, verb)
    switch = remedy_switch(refused.stderr)
    assert switch == ["git", "-C", str(holder), "switch", "-c", branch]
    subprocess.run(switch, check=True, capture_output=True)

    done = act(family, holder, verb)
    assert done.returncode == 0, done.stdout + done.stderr
    head = git("rev-parse", "HEAD", cwd=holder).stdout.strip()
    assert git("rev-parse", branch, cwd=holder).stdout.strip() == head
    assert git("rev-parse", TRACKING, cwd=holder).stdout == before["head"], (
        "the tracking branch did not move")
    push, then = next_push(done.stdout)
    assert push == ["git", "-C", str(holder), "push", "-u", "origin",
                    refspec(branch)]
    assert then == (f"      then open a pull request against {TRACKING}; "
                    "never push to it directly")
    assert done.stdout.rstrip().endswith(then), (
        "NEXT is the last thing the act says")
    pushed = subprocess.run(push, capture_output=True, text=True,
                            check=False)
    try:
        assert pushed.returncode == 0, pushed.stderr
        remote = family["remotes"] / f"{NAME}.git"
        assert git("rev-parse", f"refs/heads/{branch}",
                   cwd=remote).stdout.strip() == head
    finally:
        git("push", "-q", "origin", "--delete", branch, cwd=holder,
            check=False)
    assert validate(holder).returncode == 0


def test_a_holder_on_no_branch_is_refused_too(family, on_main):
    """A detached HEAD would take a commit no branch holds and leave
    nothing to push, so it is refused with the same remedy, as
    `bump-leg.py` refuses `bump-leg-root-detached`."""
    holder = on_main
    git("checkout", "-q", "--detach", cwd=holder)
    before = snapshot(holder)
    refused = act(family, holder, "add")
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert refused.stdout == ""
    assert (f"REFUSED family-holder-detached: {holder} is not on a branch"
            in refused.stderr), refused.stderr
    assert remedy_switch(refused.stderr) == [
        "git", "-C", str(holder), "switch", "-c", suggested(family, "add")]
    assert snapshot(holder) == before


def test_a_branch_ending_in_a_no_break_space_is_pushed_as_itself(family,
                                                                on_main):
    """`feat<U+00A0>` beside a branch `feat` (#765): `strip()` read the
    holder's branch as `feat`, so the act committed on `feat<U+00A0>` and
    its NEXT pushed `feat`, the other branch, which holds no such commit.
    Read as git wrote it, the NEXT names the branch the commit is on, and
    run, pushes that commit there and leaves `feat` alone."""
    holder = on_main
    name = "feat" + chr(0xA0)
    git("branch", "feat", cwd=holder)
    git("switch", "-q", "-c", name, cwd=holder)

    done = act(family, holder, "remove")
    assert done.returncode == 0, done.stdout + done.stderr
    push, _ = next_push(done.stdout)
    assert push == ["git", "-C", str(holder), "push", "-u", "origin",
                    refspec(name)]
    remote = family["remotes"] / f"{NAME}.git"
    pushed = subprocess.run(push, capture_output=True, text=True, check=False)
    try:
        assert pushed.returncode == 0, pushed.stderr
        assert git("rev-parse", f"refs/heads/{name}", cwd=remote).stdout == \
            git("rev-parse", "HEAD", cwd=holder).stdout
        assert git("rev-parse", "--verify", "-q", "refs/heads/feat",
                   cwd=remote, check=False).stdout == ""
    finally:
        git("push", "-q", "origin", "--delete", name, cwd=holder,
            check=False)


@pytest.mark.parametrize("verb", ["add", "bump", "remove"])
def test_a_branch_named_with_a_byte_that_is_not_utf8_is_refused_by_name(
        family, on_main, verb):
    """`caf<0xE9>` (#765): the act committed on it and printed a NEXT whose
    spelling of the byte was the stream's: the raw byte, which a UTF-8
    terminal shows and copies as U+FFFD, or the six characters of its
    escape, which name another branch. Refused by name now, by its bytes, before anything is fetched or
    written, with how to rename it: no NEXT, `add` prints not even the line
    that says the member is being read, and the holder, its refs and each
    member's git directory are as they were, FETCH_HEAD and objects too."""
    holder = on_main
    before = on_a_branch_that_is_not_utf_8(holder)

    refused = act(family, holder, verb)

    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert refused.stdout == ""
    assert (f"REFUSED family-branch-not-utf8: {holder} is on the branch "
            f"{NOT_UTF_8_BRANCH_NAMED}, whose name is not UTF-8"
            in refused.stderr), refused.stderr
    assert refused.stderr.rstrip().endswith(" branch -m <a new name>"), (
        refused.stderr)
    assert held_by_git(holder) == before


@pytest.mark.parametrize("verb", ["add", "bump", "remove"])
def test_a_dry_run_runs_on_the_tracking_branch_and_says_so(family, on_main,
                                                          verb):
    """`--dry-run` commits nothing, so it runs on any branch: on the
    tracking branch it exits 0 and says the real run refuses there, by its
    code, with the `switch` that makes a branch on a line of its own."""
    holder = on_main
    before = snapshot(holder)
    result = act(family, holder, verb, "--dry-run")
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    at = lines.index(f"branch       {TRACKING} is the holder's tracking "
                     f"branch, where a real {verb} refuses "
                     "(family-on-tracking-branch); make a branch first:")
    assert host_words(lines[at + 1]) == [
        "git", "-C", str(holder), "switch", "-c", suggested(family, verb)]
    assert "NEXT" not in result.stdout
    assert snapshot(holder) == before


@pytest.mark.parametrize("verb", ["add", "bump", "remove"])
def test_a_dry_run_on_a_branch_names_where_the_commit_lands(family, on_main,
                                                           verb):
    holder = on_main
    git("switch", "-q", "-c", "family/wip", cwd=holder)
    result = act(family, holder, verb, "--dry-run")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (f"branch       family/wip: the commit lands there, for a pull "
            f"request against {TRACKING}") in result.stdout.splitlines()


def test_the_suggested_branch_is_a_name_git_takes():
    """A member name that is no plain branch word is suggested as
    `member`: the remedy must paste and work."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("family_branch", FAMILY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module._suggested_branch("add", "Atlas") == "family/add-atlas"
    assert module._suggested_branch("add", "Ze.d") == "family/add-ze.d"
    assert module._suggested_branch("bump", "irrs", "a" * 40) == \
        "family/bump-irrs-" + "a" * 12
    for odd in ("x.lock", "a..b", "a.", "-a", ""):
        assert module._suggested_branch("remove", odd) == \
            "family/remove-member"
    for name in ("atlas", "ze.d", "a_b-c"):
        branch = module._suggested_branch("add", name)
        assert subprocess.run(["git", "check-ref-format", "--branch",
                               branch], capture_output=True,
                              check=False).returncode == 0, branch


def test_init_next_steps_make_the_branch_before_the_add(tmp_path):
    """`init` leaves the holder on its tracking branch, where `add` now
    refuses, so its NEXT STEPS open with the `switch` that makes a branch,
    before the `add`: the first printed command is not one that refuses."""
    into = tmp_path / "projects"
    into.mkdir()
    result = run_script(FAMILY, "init", "--org", ORG, "--family", "Orbit",
                        "--created-by", "Test Human",
                        "--created-on", "2026-10-12",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--into", str(into), cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    holder = into.resolve() / "Orbit" / "Orbit"
    block = [line.strip() for line in
             result.stdout.split("NEXT STEPS", 1)[1].splitlines()
             if line.strip()]
    assert host_words(block[0]) == ["git", "-C", str(holder), "switch",
                                    "-c", "family/add-<Project>"]
    assert " add --family-root " in block[1]
    assert git("symbolic-ref", "--short", "HEAD", cwd=holder).stdout.strip() \
        == TRACKING
    assert "it refuses main, the holder's tracking branch" in " ".join(
        result.stdout.split())


def test_the_tracking_branch_is_the_one_family_yaml_declares(family,
                                                            tmp_path):
    """NOT `main` BY NAME. A family made with `--tracking-branch trunk`
    refuses `add` on `trunk`, and a branch that happens to be called `main`
    is an ordinary work branch there: the dry run says the commit lands on
    it for a pull request against `trunk`, the real run commits on it, and
    its NEXT pushes `main` for that pull request."""
    remotes = tmp_path / "remotes"
    shutil.copytree(family["remotes"], remotes, symlinks=True)
    made = run_script(FAMILY, "init", "--org", ORG, "--family", "Orbit",
                      "--created-by", "Test Human",
                      "--created-on", "2026-10-13",
                      "--tracking-branch", "trunk",
                      "--local-remote-dir", str(remotes),
                      "--work-dir", str(tmp_path / "fam"))
    assert made.returncode == 0, made.stdout + made.stderr
    holder = (tmp_path / "fam" / "Orbit").resolve()
    assert git("symbolic-ref", "--short", "HEAD",
               cwd=holder).stdout.strip() == "trunk"
    add = ["add", "--family-root", str(holder), "--member", f"{ORG}/{SPARE}",
           "--local-remote-dir", str(remotes)]

    refused = run_script(FAMILY, *add)
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert (f"REFUSED family-on-tracking-branch: {holder} is on 'trunk', "
            "which family.yaml declares as the holder's tracking branch"
            in refused.stderr), refused.stderr

    git("switch", "-q", "-c", "main", cwd=holder)
    dry = run_script(FAMILY, *add, "--dry-run")
    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert ("branch       main: the commit lands there, for a pull request "
            "against trunk") in dry.stdout.splitlines(), dry.stdout

    done = run_script(FAMILY, *add)
    assert done.returncode == 0, done.stdout + done.stderr
    push, then = next_push(done.stdout)
    assert push == ["git", "-C", str(holder), "push", "-u", "origin",
                    refspec("main")]
    assert then == ("      then open a pull request against trunk; never "
                    "push to it directly")


@pytest.mark.parametrize("doc", [
    "AGENTS.md", "README.md", "templates/family-root/AGENTS-shape.md",
    "templates/family-root/README.md"])
def test_each_doc_makes_the_branch_before_the_add(doc):
    """The standard's own docs and the two a holder carries show the
    `git -C <holder> switch -c family/add-...` in the same code block as,
    and before, the first `add`: followed as written, the first command a
    person runs is not one that refuses."""
    text = (REPO / doc).read_text(encoding="utf-8")
    add = text.index("python3 scripts/family.py add ")
    block = text[text.rindex("```", 0, add):add]
    assert " switch -c family/add-" in block, block
