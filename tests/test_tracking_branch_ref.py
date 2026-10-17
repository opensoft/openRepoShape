# SPDX-License-Identifier: Apache-2.0
"""A `--tracking-branch` git would not create is refused before anything is
made, by `scaffold-project.py` and `scripts/family.py init` alike (#283).

`checked_value` holds the flag to an ALPHABET, which keeps an option and a
shell word off a command line, and the alphabet is wider than the names git
accepts as a branch: `~`, `a..b`, `x.lock`, `a/`, `/a`, `a//b`, `.a` and `a.`
are all inside it. Nothing asked git, so `--dry-run` printed a plan, and a run
against GitHub made all three repositories (`gh repo create`, for the
scaffold; one, for a family holder) before the first `git init -b` died with
`invalid initial branch name`. The re-run was then refused
`scaffold-remote-exists` for the two legs, which the operator had to delete on
GitHub by hand.

Both tools now ask git (`git check-ref-format --branch`) through ONE helper,
`shape_materialize.refuse_bad_branch`, right after `checked_value`, before any
work directory, remote or `gh` call exists and under `--dry-run` too. The
tests below hold four things:

  * each name the issue lists, and the neighbours that share its rules, is
    refused with the tool's own code, exit 2, no plan, no `gh` call and
    nothing on disk, in a `--dry-run` and in a real run, on the local route
    and (where a `#!` stub can run) the GitHub route;
  * a name git accepts is not refused, the slashed ones the shape's own
    branches use included, and one of them still scaffolds;
  * the answer does not depend on where the person stands: git is asked
    with no repository in play, so a working directory inside a repository
    git cannot open, or one removed under the person, changes nothing, and
    a git that cannot answer for any name says so instead of blaming the
    name (the review of a03abcf);
  * the helper's verdict IS git's, over a corpus, whatever git version runs
    the suite: it is asked, never copied.
"""

from __future__ import annotations

import importlib.util
import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from conftest import ORG, REPO, SCAFFOLD, WINDOWS_SKIP, git, run_script

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402
from repo_shape import Refusal  # noqa: E402

FAMILY = REPO / "scripts" / "family.py"

SCAFFOLD_CODE = "scaffold-bad-tracking-branch"
FAMILY_CODE = "family-bad-tracking-branch"

#: What every refusal says before git's own words, which are localised.
NOT_A_BRANCH = "which is not a branch name git will create"

#: `(name, why git refuses it)`. The first nine are the issue's own table; the
#: rest share a rule with one of them, in a place the table does not.
REFUSED = [
    pytest.param("~", "tilde", id="tilde"),
    pytest.param("a~1", "tilde", id="tilde-suffix"),
    pytest.param("a..b", "dot-dot", id="dot-dot"),
    pytest.param("x.lock", ".lock", id="dot-lock"),
    pytest.param("a/", "trailing slash", id="trailing-slash"),
    pytest.param("/a", "leading slash", id="leading-slash"),
    pytest.param("a//b", "double slash", id="double-slash"),
    pytest.param(".a", "leading dot", id="leading-dot"),
    pytest.param("a.", "trailing dot", id="trailing-dot"),
    pytest.param("a/.b", "a part that starts with a dot", id="dot-part"),
    pytest.param("a.lock/b", "a part that ends in .lock", id="lock-part"),
    pytest.param("+x..y", "dot-dot, after a plus", id="plus-dot-dot"),
]

#: Names git creates, and the shape's own habit of putting a slash in one.
#: None is one a project's YAML reader would read as another type (`1`, `0`,
#: `null`, `true`): that is #258's question, asked elsewhere, and a name here
#: must stay a name whichever of the two checks runs.
ACCEPTED = ["main", "trunk", "release/1.2", "feature/x", "shape/update-v1.2",
            "lane-3/shape+fix@eagle", "v1.2.3", "a.b", "a@b", "x+y"]

#: Everything inside `checked_value`'s alphabet that is worth a verdict, for
#: the test that holds the helper to git's. Names git refuses AND accepts, the
#: edges of each rule, and a few that only some versions of git have an
#: opinion on (`HEAD`, `@`), which is exactly why the expectation is asked of
#: the git that runs the suite and not written here. Every name is one the
#: disk can hold: a part over its length limit (#689) is the one rule the
#: helper keeps that git does not state, so it is asked in
#: `tests/test_next_refspec_branch_length.py`, not against git's answer.
CORPUS = [
    *ACCEPTED, "1", "0", "~", "a~1", "a..b", "..", ".", "x.lock", ".lock", "a/", "/a",
    "a//b", "/", "//", ".a", "a.", "a/.b", "a./b", "a.lock/b", "a/b.lock",
    "HEAD", "head", "@", "@-1", "a@", "@a", "FETCH_HEAD", "refs/heads/x",
    "heads/x", "a/b/c/d", "a" * 250, "-", "a b", "a\tb", "a:b", "a^b", "a*b",
    "a?b", "a[b", "a\\b", "a@{b", "a@{-1}", "@{-1}", "a\x7fb",
]


def load(name: str, path: Path):
    """A tool loaded as a module, for what it imports."""
    module_spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


class StubGh:
    """A stand-in for `gh` that logs every call and succeeds, so nothing here
    can reach GitHub. `repo view` exits 1 (no such repository yet), as the
    issue's own reproduction does, so a scaffold that got that far would go on
    to `gh repo create`."""

    def __init__(self, root: Path) -> None:
        self.bin = root / "ghbin"
        self.log = root / "gh.log"
        self.bin.mkdir()
        shim = self.bin / "gh"
        shim.write_text(textwrap.dedent("""\
            #!/bin/sh
            echo "gh $*" >> "$STUB_GH_LOG"
            [ "$1 $2" = "repo view" ] && exit 1
            exit 0
            """), encoding="utf-8")
        shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
        self.env = {"PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
                    "STUB_GH_LOG": str(self.log)}

    def calls(self) -> list[str]:
        return (self.log.read_text(encoding="utf-8").splitlines()
                if self.log.exists() else [])


@pytest.fixture
def gh(tmp_path):
    return StubGh(tmp_path)


def assert_nothing_was_made(tmp_path: Path, *, stubbed: bool = False) -> None:
    """No bare remote, no work directory of the tool's own and none of ours:
    what is under `tmp_path` is only what the test itself put there."""
    allowed = {"tmp"} | ({"ghbin"} if stubbed else set())
    found = sorted(p.name for p in tmp_path.iterdir() if p.name != "gh.log")
    assert set(found) <= allowed, f"a refused run created something: {found}"
    assert list((tmp_path / "tmp").iterdir()) == [], (
        "a refused run made a temporary work directory")


def assert_refused(result, code: str, name: str) -> None:
    """Exit 2, the tool's own code, the value named, git's verdict and the
    remediation that says what to write instead, and no plan on stdout."""
    assert result.returncode == 2, result.stderr + result.stdout
    assert result.stderr.startswith(
        f"REFUSED {code}: --tracking-branch is {name!r}, {NOT_A_BRANCH}: "
        "`git check-ref-format --branch` refuses it"), result.stderr
    assert shape_materialize.BRANCH_REMEDIATION in result.stderr
    assert result.stdout == "", "a plan was printed for a refused name"
    assert "Traceback" not in result.stderr


# --- scaffold-project.py ------------------------------------------------------

IDENTITY = ["--org", ORG, "--project", "Atlas", "--elected-by", "Test Human",
            "--elected-on", "2026-09-02"]


def scaffold(tmp_path: Path, *args: str, local: bool = True,
             dry_run: bool = False, env: dict | None = None):
    """One scaffold of `Atlas` under `tmp_path`. `TMPDIR` (and Windows'
    `TEMP` and `TMP`) point at an empty `tmp_path/tmp`, which is how a test
    sees whether the tool made a work directory of its own."""
    scratch = tmp_path / "tmp"
    scratch.mkdir(exist_ok=True)
    flags = [*IDENTITY, *args, "--work-dir", str(tmp_path / "work")]
    if local:
        flags += ["--local-remote-dir", str(tmp_path / "remotes")]
    if dry_run:
        flags.append("--dry-run")
    return run_script(SCAFFOLD, *flags, env={
        "TMPDIR": str(scratch), "TMP": str(scratch), "TEMP": str(scratch),
        **(env or {})})


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real"])
@pytest.mark.parametrize("name, why", REFUSED)
def test_a_name_git_would_not_create_is_refused_before_anything_is_made(
        tmp_path, name, why, dry_run):
    """THE LOCAL ROUTE, which needs no `gh`: on `main` a real run died at
    `git init -q --bare -b <name>` on the first remote with `REFUSED a git or
    gh command failed`, and a `--dry-run` printed a plan and exited 0."""
    result = scaffold(tmp_path, f"--tracking-branch={name}", dry_run=dry_run)
    assert_refused(result, SCAFFOLD_CODE, name)
    assert_nothing_was_made(tmp_path)


@WINDOWS_SKIP  # the `gh` stub is a `#!` script, which Windows does not run
@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real"])
@pytest.mark.parametrize("name, why", REFUSED)
def test_no_repository_is_created_on_github_for_a_name_git_refuses(
        tmp_path, gh, name, why, dry_run):
    """THE ISSUE'S ROUTE: on `main`, against GitHub, the same four names made
    three `gh repo create` calls and then died at the first `git init -b`,
    leaving three repositories with no commit. The refusal now comes before
    the first `gh` call of any kind, `repo view` included."""
    result = scaffold(tmp_path, f"--tracking-branch={name}", local=False,
                      dry_run=dry_run, env=gh.env)
    assert_refused(result, SCAFFOLD_CODE, name)
    assert gh.calls() == [], f"gh was asked: {gh.calls()}"
    assert_nothing_was_made(tmp_path, stubbed=True)


@pytest.mark.parametrize("name", ACCEPTED)
def test_a_name_git_creates_still_passes_a_dry_run(tmp_path, name):
    """The question is git's, so a name git creates is not refused: `release/
    1.2`, the shape's own `shape/update-<sha>` and `lane-3/shape+fix@eagle`
    all have a slash, a dot, a plus or an at sign, and the alphabet admits
    them all."""
    result = scaffold(tmp_path, f"--tracking-branch={name}", dry_run=True)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "--dry-run: nothing was created." in result.stdout
    assert_nothing_was_made(tmp_path)


def test_a_slashed_name_still_scaffolds_and_the_remotes_carry_it(tmp_path):
    """The control for the whole file: the check runs git, takes the answer,
    and goes on. Each of the three bare remotes holds exactly that branch."""
    result = scaffold(tmp_path, "--tracking-branch=release/1.2")
    assert result.returncode == 0, result.stderr + result.stdout
    for name in ("Atlas", "Atlas-spec", "Atlas-code"):
        bare = tmp_path / "remotes" / f"{name}.git"
        heads = git("for-each-ref", "--format=%(refname:short)", "refs/heads",
                    cwd=bare).stdout.split()
        assert heads == ["release/1.2"], f"{name} holds {heads}"


def test_the_repro_of_issue_283_for_a_tilde_names_the_flag_and_the_rule(
        tmp_path):
    """`~` is the value #258 reports misread as YAML null, and it is not a
    branch at all. The first thing the person reads is that, with git's own
    sentence after it."""
    result = scaffold(tmp_path, "--tracking-branch=~", dry_run=True)
    assert_refused(result, SCAFFOLD_CODE, "~")
    assert "no `..`, no `//`, no `~`" in result.stderr


def test_a_leading_dash_is_still_refused_by_the_alphabet_first(tmp_path):
    """`checked_value` runs first and says `unsafe-value`: a value that reads
    as an option never reaches `git check-ref-format`, whose own refusal of it
    is the second line of defence and not the first. `-x` has nothing but its
    leading dash for the alphabet to refuse, so the dash rule is the one
    held."""
    result = scaffold(tmp_path, "--tracking-branch=-x", dry_run=True)
    assert result.returncode == 2
    assert "REFUSED unsafe-value" in result.stderr
    assert SCAFFOLD_CODE not in result.stderr


# --- scripts/family.py init ---------------------------------------------------

def family_init(tmp_path: Path, *args: str, local: bool = True,
                dry_run: bool = False, env: dict | None = None):
    """One `family.py init` of `Contoso` from an empty `tmp_path/into`, so
    anything the run lands there is seen."""
    into = tmp_path / "into"
    into.mkdir(exist_ok=True)
    scratch = tmp_path / "tmp"
    scratch.mkdir(exist_ok=True)
    flags = ["init", "--org", ORG, "--family", "Contoso", "--created-by",
             "Test Human", "--created-on", "2026-09-09", *args]
    if local:
        flags += ["--local-remote-dir", str(tmp_path / "remotes")]
    if dry_run:
        flags.append("--dry-run")
    return run_script(FAMILY, *flags, cwd=into, env={
        "TMPDIR": str(scratch), "TMP": str(scratch), "TEMP": str(scratch),
        **(env or {})})


def assert_family_made_nothing(tmp_path: Path, *, stubbed: bool = False):
    allowed = {"tmp", "into"} | ({"ghbin"} if stubbed else set())
    found = sorted(p.name for p in tmp_path.iterdir() if p.name != "gh.log")
    assert set(found) <= allowed, f"a refused run created something: {found}"
    assert list((tmp_path / "into").iterdir()) == [], (
        "a refused run landed a holder")


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real"])
@pytest.mark.parametrize("name, why", REFUSED)
def test_family_init_refuses_a_name_git_would_not_create_before_anything_is_made(
        tmp_path, name, why, dry_run):
    result = family_init(tmp_path, f"--tracking-branch={name}",
                         dry_run=dry_run)
    assert_refused(result, FAMILY_CODE, name)
    assert_family_made_nothing(tmp_path)


@WINDOWS_SKIP  # the `gh` stub is a `#!` script, which Windows does not run
@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real"])
@pytest.mark.parametrize("name", ["~", "a..b", "x.lock", "a/"])
def test_family_init_creates_no_github_repository_for_a_name_git_refuses(
        tmp_path, gh, name, dry_run):
    """On `main`, `_create_holder_remote` ran `gh repo create` and then
    `_create_holder_worktree`'s first `git init -b` died: one repository on
    GitHub with no commit, and a re-run refused `family-remote-exists`."""
    result = family_init(tmp_path, f"--tracking-branch={name}", local=False,
                         dry_run=dry_run, env=gh.env)
    assert_refused(result, FAMILY_CODE, name)
    assert gh.calls() == [], f"gh was asked: {gh.calls()}"
    assert_family_made_nothing(tmp_path, stubbed=True)


@pytest.mark.parametrize("name", ["main", "release/1.2"])
def test_family_init_still_takes_a_name_git_creates(tmp_path, name):
    result = family_init(tmp_path, f"--tracking-branch={name}", dry_run=True)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "--dry-run: nothing was created." in result.stdout


# --- wherever the person stands (review of a03abcf) ---------------------------

def inside_a_repository_git_cannot_open(tmp_path: Path, kind: str) -> Path:
    """A directory inside a repository git cannot open, of the two kinds the
    review of a03abcf ran from: a `.git` FILE naming a gitdir that is gone
    (a linked worktree whose main repository was moved or deleted), and a
    repository whose `.git/config` does not parse."""
    where = tmp_path / kind
    if kind == "gitfile":
        where.mkdir()
        gone = tmp_path / "moved" / ".git" / "worktrees" / kind
        (where / ".git").write_text(f"gitdir: {gone.as_posix()}\n",
                                    encoding="utf-8")
    else:
        git("init", "-q", str(where), cwd=tmp_path)
        with open(where / ".git" / "config", "a", encoding="utf-8") as config:
            config.write("[core\nbroken\n")
    return where


@pytest.mark.parametrize("kind", ["gitfile", "bad-config"])
def test_the_default_branch_is_not_refused_from_inside_a_repository_git_cannot_open(
        tmp_path, kind):
    """`--branch` sets up the repository it is run in, so asked in the
    person's working directory git failed for EVERY name in one it could not
    open: both tools refused the default `main` as "not a branch name git
    will create" and told the person to pass `main`, where `main` scaffolds
    from the same directory. The question's own empty directory is put inside
    the broken repository too (`TMPDIR`), so a question that only moved its
    working directory, and still let git look for a repository, fails here
    as well."""
    where = inside_a_repository_git_cannot_open(tmp_path, kind)
    scratch = where / "tmp"
    scratch.mkdir()
    env = {"TMPDIR": str(scratch), "TMP": str(scratch), "TEMP": str(scratch)}
    local = ["--local-remote-dir", str(tmp_path / "remotes"), "--dry-run"]
    family = ["init", "--org", ORG, "--family", "Contoso", "--created-by",
              "Test Human", "--created-on", "2026-09-09", "--into",
              str(tmp_path / "into"), *local]

    made = run_script(SCAFFOLD, *IDENTITY, *local, cwd=where, env=env)
    assert made.returncode == 0, made.stderr + made.stdout
    assert "--dry-run: nothing was created." in made.stdout
    held = run_script(FAMILY, *family, cwd=where, env=env)
    assert held.returncode == 0, held.stderr + held.stdout
    assert "--dry-run: nothing was created." in held.stdout

    # Still git's verdict on the name, from the same directory.
    assert_refused(run_script(SCAFFOLD, *IDENTITY, "--tracking-branch=a..b",
                              *local, cwd=where, env=env),
                   SCAFFOLD_CODE, "a..b")
    assert_refused(run_script(FAMILY, *family, "--tracking-branch=a..b",
                              cwd=where, env=env),
                   FAMILY_CODE, "a..b")
    assert list(scratch.iterdir()) == [], (
        "the question left its empty directory behind")


@pytest.mark.skipif(os.name == "nt", reason="Windows does not remove a "
                    "directory a process is standing in")
def test_the_answer_does_not_need_the_working_directory_to_exist(
        tmp_path, monkeypatch):
    """A directory removed under the person: git run there dies before it
    reads its arguments (`Unable to read current working directory`), and a
    scaffold without the question succeeds from it."""
    gone = tmp_path / "gone"
    gone.mkdir()
    monkeypatch.chdir(gone)
    gone.rmdir()
    assert shape_materialize.branch_problem("--tracking-branch", "main") is None
    problem = shape_materialize.branch_problem("--tracking-branch", "a..b")
    assert problem is not None
    assert problem.startswith(
        f"--tracking-branch is 'a..b', {NOT_A_BRANCH}: "
        "`git check-ref-format --branch` refuses it"), problem


def test_a_git_that_cannot_answer_for_any_name_does_not_blame_the_name(
        tmp_path, monkeypatch):
    """Asked of no repository, git still reads the person's global config,
    and a malformed one makes it fail for every name. That is not the name's
    fault: the refusal says the name could not be checked, with git's words,
    and the remedy is about git, not a name to pass instead. The two are told
    apart by asking git about `main` as well, not by reading git's words,
    which are localised."""
    broken = tmp_path / "gitconfig"
    broken.write_text("[user\nbroken\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(broken))
    control = subprocess.run(["git", "config", "--global", "--list"],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", check=False)
    assert control.returncode != 0, "this git read the malformed config"
    for name in ("main", "a..b"):
        with pytest.raises(Refusal) as caught:
            shape_materialize.refuse_bad_branch("any-code",
                                                "--tracking-branch", name)
        refusal = caught.value
        assert refusal.code == "any-code"
        assert refusal.detail.startswith(
            f"--tracking-branch is {name!r}, which could not be checked: "
            "`git check-ref-format --branch` fails for `main` too, so git "
            "could not answer ("), refusal.detail
        assert NOT_A_BRANCH not in refusal.detail
        assert (refusal.remediation
                == shape_materialize.BRANCH_UNCHECKED_REMEDIATION)


# --- the helper ---------------------------------------------------------------

def git_says(name: str) -> bool:
    """Whether the git that runs this suite accepts `name` exactly as written
    as a branch (`check-ref-format --branch` echoes it back unexpanded)."""
    proc = subprocess.run(["git", "check-ref-format", "--branch", name],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False)
    return proc.returncode == 0 and proc.stdout.strip() == name


@pytest.mark.parametrize("name", CORPUS)
def test_the_helper_says_what_git_says(name):
    """ASKED, NEVER COPIED: for every name in a corpus that holds the rules'
    edges, the helper accepts it exactly when this git does. Two versions of
    git that disagree about `HEAD` or `@` make the suite agree with each of
    them in turn."""
    problem = shape_materialize.branch_problem("--tracking-branch", name)
    assert (problem is None) == git_says(name), (name, problem)


def test_the_corpus_holds_names_of_both_kinds():
    """So the test above cannot pass by git refusing, or accepting, them all."""
    verdicts = {git_says(name) for name in CORPUS}
    assert verdicts == {True, False}
    assert sum(not git_says(name) for name in CORPUS) >= 20


def test_a_refusal_carries_the_callers_code_the_flag_and_the_remedy():
    with pytest.raises(Refusal) as caught:
        shape_materialize.refuse_bad_branch("any-code", "tracking_branch",
                                            "a..b")
    refusal = caught.value
    assert refusal.code == "any-code"
    assert refusal.detail.startswith(
        f"tracking_branch is 'a..b', {NOT_A_BRANCH}: "
        "`git check-ref-format --branch` refuses it")
    assert refusal.remediation == shape_materialize.BRANCH_REMEDIATION
    assert shape_materialize.refuse_bad_branch(
        "any-code", "tracking_branch", "main") is None


def test_a_leading_dash_is_not_put_to_git(monkeypatch):
    """The value would be an option to the question itself, so it is refused
    without one. (`checked_value` has refused it already, for the callers that
    ask it first.)"""
    def not_asked(*args, **kwargs):
        raise AssertionError("git was asked about a value that reads as an "
                             "option")
    monkeypatch.setattr(shape_materialize, "run", not_asked)
    problem = shape_materialize.branch_problem("--tracking-branch", "-x")
    assert problem == ("--tracking-branch is '-x', " + NOT_A_BRANCH
                       + ": it begins with `-`, which git reads as an option")


def test_a_git_that_cannot_run_is_a_refusal_not_a_traceback(monkeypatch):
    def no_git(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "git")
    monkeypatch.setattr(shape_materialize, "run", no_git)
    problem = shape_materialize.branch_problem("--tracking-branch", "main")
    assert problem is not None
    assert "could not be checked" in problem
    assert "`git check-ref-format --branch` could not be run" in problem
    with pytest.raises(Refusal) as caught:
        shape_materialize.refuse_bad_branch("any-code", "--tracking-branch",
                                            "main")
    assert caught.value.code == "any-code"
    assert (caught.value.remediation
            == shape_materialize.BRANCH_UNCHECKED_REMEDIATION)


def test_a_value_that_cannot_be_an_argument_is_a_refusal_not_a_traceback():
    """A NUL cannot be put on a command line at all."""
    problem = shape_materialize.branch_problem("tracking_branch", "a\x00b")
    assert problem is not None
    assert "could not be checked" in problem


def test_a_name_git_would_expand_is_not_the_name_that_was_written(monkeypatch):
    """In a repository `check-ref-format --branch` expands `@{-1}` to the
    branch before; the tools write the name they were given, so a spelling
    that means another branch is refused. The helper asks git with no
    repository, where git has nothing to expand, and the alphabet keeps `{`
    out, so this is the helper's own guard against a git that expands
    anyway, held here with a git that answers another name."""
    monkeypatch.setattr(shape_materialize, "run", lambda *a, **k: "main")
    problem = shape_materialize.branch_problem("--tracking-branch", "@{-1}")
    assert problem == ("--tracking-branch is '@{-1}', " + NOT_A_BRANCH
                       + ": `git check-ref-format --branch` reads it as "
                       "'main', not as written")


def test_it_is_one_definition_for_both_tools():
    """Two copies of a rule are how the second starts refusing other values:
    each tool imports the same function."""
    scaffolder = load("scaffold_for_tracking_branch_ref", SCAFFOLD)
    family = load("family_for_tracking_branch_ref", FAMILY)
    defined = shape_materialize.refuse_bad_branch
    assert defined.__module__ == "shape_materialize"
    assert scaffolder.refuse_bad_branch is defined
    assert family.refuse_bad_branch is defined


def test_the_helper_is_not_in_a_shape_copy():
    """`scripts/repo_shape.py` is copied into every project and digest-pinned,
    so a function added there would put an `upstream-changed` row in front of
    every project for a rule no project's own copy asks."""
    shape_copy = (REPO / "scripts" / "repo_shape.py").read_text(
        encoding="utf-8")
    assert "branch_problem" not in shape_copy
    assert "refuse_bad_branch" not in shape_copy
