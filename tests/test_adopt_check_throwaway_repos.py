# SPDX-License-Identifier: Apache-2.0
"""`check`'s throwaway repositories answer as the split will (#910).

`check` asks this machine's git in repositories of its own: which kept
nested `.gitattributes` outrank the root's rule (#530, #619), what `git add`
stores at the root's own (#530's D5(a)), and what the split's checkout, `git
rm` and `git add` make of every file (#654's rehearsal); and, in the work
directory, whether git checks a symlink out as one (#183's probe). Lane 3's
triage of #457 filed four lines against them. Measured on c7a3ff16 with git
2.43, each in a real `check`:

* L1-90: a SHA-256 source, `GIT_DEFAULT_HASH=sha256` over a SHA-1 one, and a
  tree path git refuses (`..`, `.Git/x`) each stopped `check` with `REFUSED
  git-failed`, exit 2, at the rehearsal's `read-tree`. Before #654 `check`
  passed the path, and `execute` made both legs and stopped extracting the
  spec leg, its first clone saying `error: invalid path '..'`.
* L1-92: the three were made in `TMPDIR`, another disk than the work
  directory where `execute` builds the split, wherever `TMPDIR` was.
* L1-94: a `core.hooksPath` from this machine's global config ran its
  `post-index-change` hook 12 times in one `check`, 2 in #619's repository
  and 10 in the rehearsal.
* L1-32: a `git init` the symlink probe's work directory refused otherwise
  than with an `OSError` (`GIT_DEFAULT_HASH=bogus`) stopped `check` with "a
  git or gh command failed", exit 2, where it printed `plan-root-symlink`.

Now each is made in the work directory, each but the symlink probe with the
source's object format and no hook of this machine's (the probe keeps its
plain `git init`, which runs none), a path git refuses is
`plan-path-git-refuses`, a repository git cannot make or ask there is
`adopt-git-unasked`, which says why, and the probe's failure stands for its
finding, with a NOTE.

#1083 followed, measured on 2a119f28 with git 2.43:

* `check` made no clone of the source, and the split's first act after it
  makes both legs is one. git 2.43's `git clone` stops at an
  `init.defaultBranch` it will not take (`a..b`), and every one at a
  `GIT_DEFAULT_HASH` naming no hash, so `check` said `plan ok` and
  `execute` stopped after the legs existed. `check` now makes the split's
  own clone first, and one this git will not make is `adopt-git-unasked`.
* `_resolved` and `_answers`, which ask how a kept submodule's url resolves
  and whether it answers, made their repositories in `TMPDIR` with a plain
  `git init`, so either setting stopped `check` with "a git or gh command
  failed", and `_resolved`'s `update-index` ran this machine's
  `post-index-change` hook. They are made as the others are now.

#1136 followed, measured on bba168bd with git 2.43. In each case `check`
said `plan ok`, and `execute` made both legs and stopped extracting the
spec leg:

* under a parent git's `-c core.protectHFS=true`, over a source path `.g` +
  U+200C + `it/x` (`unable to checkout working tree`);
* under a parent's failing required clean filter, named by the root's own
  `.gitattributes` for itself;
* under `GIT_ATTR_SOURCE=bogus` (`bad --attr-source or GIT_ATTR_SOURCE`).

The rehearsal and `_stored_as_written` left out `GIT_CONFIG_PARAMETERS`,
and every throwaway left out `GIT_ATTR_SOURCE`. Now the two take a parent's
settings as they stand, in either form, an `attr.tree` among them, as the
split's own checkout, `git rm` and `git add` take them; and both borrow the
source's objects, so that a tree named by its object id is the tree the
split's clones read (r1169's SHOULD-1). A `GIT_ATTR_SOURCE` is
`adopt-git-unasked`, by name, before any question. And three of the
throwaways read their environment before they are made.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import tempfile
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import (ADOPT, WINDOWS_SKIP, appended_to_command_scope,
                      findings, git, planned, refused_before_any_leg,
                      run_script)
from test_adopt_nested_attributes import (KEEP_GITHUB, ROOT, ROOT_ATTRIBUTES,
                                          SOURCE, YML_CRLF, adoption_plan,
                                          committed_raw, github)
from test_adopt_relative_submodule_url import (BOTH_IN_CODE, EXTRA, SIBLING,
                                               source_with)
from test_adopt_relative_submodule_url import planned as planned_with_urls
from test_adopt_root_symlinks import (GITHUB, OUTSIDE_CI, WORKFLOW, climbs,
                                      finding, symlink_findings)
from test_adopt_root_symlinks import links_as_links  # noqa: F401
from test_adopt_root_symlinks import unwritable_work  # noqa: F401
from test_adopt_root_symlinks import planned as planned_with_links

#: The two findings #910 adds, and the codes of `execute`'s refusals.
PATH_GIT_REFUSES = "plan-path-git-refuses"
UNASKED = "adopt-git-unasked"
#: The findings and codes the rows below meet besides.
REENCODED_FILES = "plan-file-reencoded"
WORK_DIR_UNWRITABLE = "adopt-work-dir-unwritable"
NOTES = "notes.txt"
CRLF = b"one\r\ntwo\r\n"
TEXT_EOL_LF = b"* text eol=lf\n"
#: How `plan-file-reencoded` begins for the one CRLF file the plan keeps.
KEPT_CRLF = ("the plan keeps 1 file in the assembly root, and this machine's "
             "`git add` would store it as other bytes than its blob")
#: The prefixes of the throwaway repositories of #530 and #654, and of the
#: split's own clone (#1083).
THROWAWAY_PREFIXES = ("openreposhape-attributes-",
                      "openreposhape-reencoded-", "openreposhape-clone-")
#: The prefixes of `_resolved`'s and `_answers`' (#1083).
URL_PREFIXES = ("openreposhape-url-", "openreposhape-ask-")
RELATIVE_URL = "plan-submodule-relative-url"
#: The hooks the counting `core.hooksPath` holds: every one git runs where
#: an index, a checkout or a ref is written, or a commit made.
HOOKS = ("post-index-change", "post-checkout", "reference-transaction",
         "post-commit", "pre-auto-gc")
#: `adopt-git-unasked`, up to where it names why, and from where it names
#: what `execute` does: `{}` is the work directory.
UNASKED_OPENS = (
    "`check` asks this machine's git what the split will make of the source "
    "in throwaway repositories in `{}`, the work directory, where `execute` "
    "builds the split, and it could not: ")
UNASKED_ENDS = (
    ". `execute` asks the same in its own work directory before it makes "
    "either leg, and refuses while git cannot answer there. Fix what that "
    "names -- a git setting, the disk or the directory -- or pass another "
    "--work-dir, and run `check` again.")
PATH_REMEDY = "Remediation: a path git refuses is a fact of the source"


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location(
        "adopt_check_throwaway_repos", ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def a_source(base: Path, object_format: str = "sha1",
             files: dict | None = None) -> Path:
    """`SOURCE` committed in a repository of `object_format`, then each of
    `files` committed byte for byte (`committed_raw`)."""
    path = base / "Thing"
    path.mkdir(parents=True)
    git("init", "-q", "-b", "main", f"--object-format={object_format}", ".",
        cwd=path)
    for name, body in SOURCE.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body.encode("utf-8"))
    git("add", "-A", cwd=path)
    git("commit", "-qm", "Initial import", cwd=path)
    for name, data in (files or {}).items():
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        committed_raw(path, name, data)
    return path


def mktree(repo: Path, rows: list[str]) -> str:
    made = subprocess.run(["git", "mktree"], cwd=str(repo),
                          input="".join(f"{row}\n" for row in rows).encode(),
                          capture_output=True, check=True)
    return made.stdout.decode().strip()


def with_paths(repo: Path, paths: tuple[str, ...]) -> None:
    """A commit on `main` whose tree gains each of `paths`, whether git
    takes it as a path or not: `git mktree` writes what it is given, and no
    index is asked."""
    blob = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                          cwd=str(repo), input=b"x\n", capture_output=True,
                          check=True).stdout.decode().strip()
    nested: dict = {}
    for path in paths:
        *directories, name = path.split("/")
        here = nested
        for directory in directories:
            here = here.setdefault(directory, {})
        here[name] = None

    def rows(names: dict) -> list[str]:
        return [f"100644 blob {blob}\t{name}" if below is None
                else f"040000 tree {mktree(repo, rows(below))}\t{name}"
                for name, below in names.items()]

    held = git("ls-tree", "HEAD", cwd=repo).stdout.splitlines()
    tree = mktree(repo, held + rows(nested))
    commit = git("commit-tree", tree, "-p", "HEAD", "-m", "Add paths",
                 cwd=repo).stdout.strip()
    git("update-ref", "refs/heads/main", commit, cwd=repo)


def checked(plan: Path, env: dict | None = None, *extra: str):
    return run_script(ADOPT, "check", "--plan", str(plan), *extra,
                      env=env or {})


def finding_lines(result) -> list[str]:
    return [line for line in result.stderr.splitlines()
            if line.startswith("FINDING ")]


def codes(result) -> list[str]:
    return [line.split(" ", 2)[1].rstrip(":")
            for line in finding_lines(result)]


def config_with(base: Path, *lines: str) -> dict:
    """`GIT_CONFIG_GLOBAL` naming a file of `lines`, after an include of
    the session's own global config, so that what it sets stays set."""
    config = base / "global-config"
    held = os.environ.get("GIT_CONFIG_GLOBAL", "")
    included = ["[include]", f'\tpath = "{Path(held).as_posix()}"'] \
        if held else []
    config.write_bytes(("\n".join([*included, *lines]) + "\n").encode())
    return {"GIT_CONFIG_GLOBAL": str(config)}


# ---------------------------------------------------------------------------
# L1-90: the source's object format
# ---------------------------------------------------------------------------

#: `(the source's object format, what the environment adds)`: each of the
#: first three stopped `check` with `REFUSED git-failed` on c7a3ff16; the
#: last is the control, which did not.
FORMATS = [
    pytest.param("sha256", {}, id="a-sha256-source"),
    pytest.param("sha1", {"GIT_DEFAULT_HASH": "sha256"},
                 id="default-hash-sha256-over-a-sha1-source"),
    pytest.param("sha256", {"GIT_DEFAULT_HASH": "sha1"},
                 id="default-hash-sha1-over-a-sha256-source"),
    pytest.param("sha1", {}, id="control-a-sha1-source"),
]


@pytest.mark.parametrize(("object_format", "env"), FORMATS)
def test_the_rehearsal_answers_in_the_sources_object_format(
        tmp_path, object_format, env):
    """The CRLF file the plan keeps under `* text eol=lf` is found in every
    format, so the rehearsal was asked, and answered, in the source's."""
    plan = planned(a_source(tmp_path, object_format,
                            {ROOT_ATTRIBUTES: TEXT_EOL_LF, NOTES: CRLF}),
                   tmp_path, {NOTES: ROOT})
    result = checked(plan, env)
    assert "REFUSED" not in result.stderr, result.stderr
    assert result.returncode == 1, result.stderr
    assert codes(result) == [REENCODED_FILES], result.stderr
    assert KEPT_CRLF in finding_lines(result)[0]


@pytest.mark.parametrize(("object_format", "env"), FORMATS[:3])
def test_a_source_with_nothing_to_find_is_plan_ok_in_its_format(
        tmp_path, object_format, env):
    plan = planned(a_source(tmp_path, object_format), tmp_path, {})
    result = checked(plan, env)
    assert result.returncode == 0, result.stderr
    assert "plan ok" in result.stdout


# ---------------------------------------------------------------------------
# L1-90: a tree path git refuses
# ---------------------------------------------------------------------------

def one_refused(path: str) -> str:
    return (f"the source commit holds 1 path this machine's git refuses as a "
            f"path, and holds in no index: `{path}`. Each clone the split "
            "makes of the source would stop at it, `unable to checkout "
            "working tree`, so `execute` refuses it before it makes either "
            "leg, whatever the plan answers for it.")


#: `(paths, the plan's entries for them, what `check` says)`.
REFUSED_PATHS = [
    pytest.param(("..",), {"..": ROOT}, one_refused(".."), id="dot-dot"),
    pytest.param((".Git/x",), {".Git/": ROOT}, one_refused(".Git/x"),
                 id="dot-git-in-another-case"),
    pytest.param(("notes/.git/x",), {"notes/": ROOT},
                 one_refused("notes/.git/x"), id="dot-git-below-the-root"),
    pytest.param(("..", ".Git/x", "notes/.git/x"),
                 {"..": ROOT, ".Git/": ROOT, "notes/": ROOT},
                 "the source commit holds 3 paths this machine's git refuses "
                 "as a path, and holds in no index: `..`, `.Git/x` and "
                 "`notes/.git/x`. Each clone the split makes of the source "
                 "would stop at the first, `unable to checkout working "
                 "tree`, so `execute` refuses them before it makes either "
                 "leg, whatever the plan answers for them.",
                 id="three-in-the-trees-order"),
]


@pytest.mark.parametrize(("paths", "answers", "said"), REFUSED_PATHS)
def test_a_path_git_refuses_is_a_finding(tmp_path, paths, answers, said):
    source = a_source(tmp_path)
    with_paths(source, paths)
    result = checked(planned(source, tmp_path, answers))
    assert "REFUSED" not in result.stderr, result.stderr
    assert result.returncode == 1, result.stderr
    assert finding_lines(result) == [f"FINDING {PATH_GIT_REFUSES}: {said}"]
    assert result.stderr.count(PATH_REMEDY) == 1, result.stderr


def test_a_path_git_takes_beside_them_is_no_finding(tmp_path):
    """The control: `..x` and `.Gitx/x` are paths git takes."""
    source = a_source(tmp_path)
    with_paths(source, ("..x", ".Gitx/x"))
    assert findings(planned(source, tmp_path,
                            {"..x": ROOT, ".Gitx/": ROOT})) == []


def test_execute_refuses_a_path_git_refuses_before_any_leg(
        adopter, monkeypatch, tmp_path):
    source = a_source(tmp_path)
    with_paths(source, ("..",))
    refusal = refused_before_any_leg(
        adopter, monkeypatch, planned(source, tmp_path, {"..": ROOT}),
        tmp_path)
    assert refusal.code == PATH_GIT_REFUSES
    assert PATH_REMEDY in refusal.remediation


def test_the_rehearsal_asks_nothing_more_of_a_tree_git_refuses(adopter,
                                                               tmp_path):
    """Asked on its own, the rehearsal stops before its `read-tree`, which
    git refuses at `..`: `plan-path-git-refuses` names the path."""
    source = a_source(tmp_path)
    with_paths(source, ("..",))
    plan = adopter.Plan.load(planned(source, tmp_path, {"..": ROOT}))
    work = tmp_path / "work"
    work.mkdir()
    opened = plan.open_source(None, work)
    assert adopter._reencoded_files_findings(plan, opened,
                                             opened.tree()) == []
    assert list(work.iterdir()) == []


# ---------------------------------------------------------------------------
# L1-92: in the work directory
# ---------------------------------------------------------------------------

def recording_where_made(adopter, monkeypatch) -> list:
    """`(prefix, parent)` of each directory `adopt-project.py` makes with
    `tempfile.mkdtemp` from here on, appended as it is made."""
    made = []

    def mkdtemp(suffix=None, prefix=None, dir=None):
        path = tempfile.mkdtemp(suffix=suffix, prefix=prefix, dir=dir)
        made.append((prefix, Path(path).parent.resolve()))
        return path

    monkeypatch.setattr(adopter, "tempfile", SimpleNamespace(
        mkdtemp=mkdtemp, gettempdir=tempfile.gettempdir,
        TemporaryDirectory=tempfile.TemporaryDirectory))
    return made


def asked_where(made: list, prefixes: tuple) -> list:
    return [(prefix, parent) for prefix, parent in made if prefix in prefixes]


def test_each_throwaway_repository_is_made_in_the_work_directory(
        adopter, monkeypatch, tmp_path):
    """The source keeps a nested `.gitattributes` above a pinned copy and
    its own root one, so all three questions are asked, after the split's
    own clone of the source (#1083): each throwaway repository is made in
    the work directory the source was opened in, not in `TMPDIR`, and none
    is left there."""
    plan = adopter.Plan.load(adoption_plan(tmp_path, github(YML_CRLF),
                                           KEEP_GITHUB))
    work = tmp_path / "work"
    work.mkdir()
    opened = plan.open_source(None, work)
    made = recording_where_made(adopter, monkeypatch)
    found, _, _ = adopter._entry_findings(plan, opened)
    assert any(line.startswith("FINDING plan-nested-attributes: ")
               for line in found), found
    asked = asked_where(made, THROWAWAY_PREFIXES)
    assert {prefix for prefix, _ in asked} == set(THROWAWAY_PREFIXES)
    assert {parent for _, parent in asked} == {work.resolve()}
    assert list(work.iterdir()) == []


# ---------------------------------------------------------------------------
# L1-94: no hook of this machine's
# ---------------------------------------------------------------------------

def counting_hooks(base: Path) -> tuple[Path, Path]:
    """`(hooks, log)`: a directory of `HOOKS`, each adding its name to
    `log` as a line each time git runs it."""
    hooks = base / "hooks"
    hooks.mkdir()
    log = base / "hook-runs.log"
    for name in HOOKS:
        hook = hooks / name
        hook.write_bytes(f"#!/bin/sh\necho {name} >> '{log.as_posix()}'\n"
                         .encode())
        hook.chmod(0o755)
    return hooks, log


def runs(log: Path) -> list[str]:
    return log.read_text(encoding="utf-8").splitlines() \
        if log.exists() else []


def in_the_global_config(base: Path, hooks: Path) -> dict:
    return config_with(base, "[core]", f'\thooksPath = "{hooks.as_posix()}"')


def in_the_command_scope(_base: Path, hooks: Path) -> dict:
    return appended_to_command_scope(os.environ,
                                     [("core.hooksPath", hooks.as_posix())])


def appended_to_parameters(entries) -> dict:
    """`GIT_CONFIG_PARAMETERS` as a parent `git -c <key>=<value>` hands it
    to each command it runs, an alias or a hook: `entries` after any the
    environment holds, each in git's own quoted form, `'<key>'='<value>'`
    (git 2.43 writes the key in the case it was given)."""
    held = os.environ.get("GIT_CONFIG_PARAMETERS", "")
    added = " ".join(f"'{key}'='{value}'" for key, value in entries)
    return {"GIT_CONFIG_PARAMETERS": f"{held} {added}".strip()}


def from_a_parent_git(_base: Path, hooks: Path) -> dict:
    return appended_to_parameters([("core.hooksPath", hooks.as_posix())])


#: Where a hook's directory is configured: the second and third reach the
#: split's own clone as a parent git hands them (r1119's SHOULD-2), where
#: that clone's own `-c core.hooksPath` comes after them.
HOOKS_CONFIGURED = [
    pytest.param(in_the_global_config, id="global-config"),
    pytest.param(in_the_command_scope, id="git-config-count"),
    pytest.param(from_a_parent_git, id="git-config-parameters")]


@pytest.mark.parametrize("configured", HOOKS_CONFIGURED)
def test_no_hook_of_this_machines_runs_in_a_throwaway_repository(
        tmp_path, configured):
    """The source keeps its own root `.gitattributes`, so #619's question
    of `git add` is asked as well as the rehearsal's: on c7a3ff16 the
    global config's hook ran 12 times in this `check`. The split's own
    clone writes refs, which runs `reference-transaction`, and takes the
    settings a parent git hands it too (`git-config-parameters`), so its
    own `-c core.hooksPath` must come after them."""
    plan = planned(a_source(tmp_path, files={ROOT_ATTRIBUTES: b"*.md text\n"}),
                   tmp_path, {})
    hooks, log = counting_hooks(tmp_path)
    result = checked(plan, configured(tmp_path, hooks))
    assert result.returncode == 0, result.stderr
    assert runs(log) == []


@pytest.mark.parametrize("configured", HOOKS_CONFIGURED)
def test_the_counting_hook_runs_where_this_machines_config_reaches(
        tmp_path, configured):
    """The control: the same config runs the hook in a repository of its
    own, so the row above counts something that would run."""
    hooks, log = counting_hooks(tmp_path)
    repository = tmp_path / "ordinary"
    git("init", "-q", str(repository), cwd=tmp_path)
    (repository / "a").write_bytes(b"a\n")
    subprocess.run(["git", "add", "a"], cwd=str(repository), check=True,
                   env={**os.environ, **configured(tmp_path, hooks)})
    assert runs(log) == ["post-index-change"]


# ---------------------------------------------------------------------------
# L1-32: the symlink probe's own failure
# ---------------------------------------------------------------------------

def linked_github_plan(base: Path) -> Path:
    """A plan that keeps `.github`, a symlink climbing out of the root, in
    the root: `check`'s finding for it asks the probe (#531)."""
    _, plan = planned_with_links(base, {}, {GITHUB: OUTSIDE_CI},
                                 {GITHUB: ROOT})
    return plan


NO_PROBE_NOTE = "NOTE `check` could not ask git whether it checks a symlink"


def test_a_probe_git_will_not_make_stands_for_its_finding(
        links_as_links, tmp_path):  # noqa: F811
    """`GIT_DEFAULT_HASH=bogus` makes the probe's `git init` fail, and of
    the `git init`s only it: each throwaway repository names its format.
    `check` prints the finding the probe stands for, as it does with no
    such variable, and says why in a NOTE. (The split's own `git clone`
    stops at that variable too, on git 2.43, which `adopt-git-unasked`
    says beside them: the rows of #1083 below.)"""
    result = checked(linked_github_plan(tmp_path),
                     {"GIT_DEFAULT_HASH": "bogus"})
    assert "REFUSED" not in result.stderr, result.stderr
    assert result.returncode == 1, result.stderr
    assert symlink_findings(result) == [
        finding(GITHUB, OUTSIDE_CI, WORKFLOW, climbs(GITHUB))]
    assert NO_PROBE_NOTE in result.stdout, result.stdout
    assert "unknown hash algorithm 'bogus'" in result.stdout, result.stdout


def test_a_probe_git_makes_prints_the_same_finding_and_no_note(
        links_as_links, tmp_path):  # noqa: F811
    """The control: the same plan, with no such variable."""
    result = checked(linked_github_plan(tmp_path))
    assert result.returncode == 1, result.stderr
    assert symlink_findings(result) == [
        finding(GITHUB, OUTSIDE_CI, WORKFLOW, climbs(GITHUB))]
    assert NO_PROBE_NOTE not in result.stdout


@pytest.mark.parametrize("failure", [
    pytest.param(lambda adopter: adopter.CommandFailed(
        ["git", "init", "-q", "probe"], None, 128,
        "fatal: unknown hash algorithm 'bogus'"), id="command-failed"),
    pytest.param(lambda adopter: adopter.Refusal(
        "git-failed", "`git init` exited 128: fatal: unknown hash "
        "algorithm 'bogus'"), id="refusal")])
def test_the_probe_takes_a_failed_git_init_as_a_disk_with_symlinks(
        adopter, monkeypatch, tmp_path, failure):
    def refused(_work_root):
        raise failure(adopter)

    monkeypatch.setattr(adopter, "_checks_out_symlinks", refused)
    probe = adopter._SymlinkProbe(tmp_path)
    assert probe.symlinks() is True
    notes = probe.notes()
    assert len(notes) == 1, notes
    assert "fatal: unknown hash algorithm 'bogus'" in notes[0]


def test_a_work_directory_the_probe_cannot_write_gives_no_note(
        adopter, monkeypatch, tmp_path):
    """An `OSError` is `adopt-work-dir-unwritable`'s to say (#524), and the
    probe adds no NOTE of its own."""
    def unwritable(_work_root):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(adopter, "_checks_out_symlinks", unwritable)
    probe = adopter._SymlinkProbe(tmp_path)
    assert probe.symlinks() is True
    assert probe.notes() == []


# ---------------------------------------------------------------------------
# A throwaway repository git cannot make or ask: `adopt-git-unasked`
# ---------------------------------------------------------------------------

def bad_default_branch(base: Path) -> dict:
    """A global config whose `init.defaultBranch` git will not take."""
    return config_with(base, "[init]", "\tdefaultBranch = a..b")


#: What the stub `git` of `refusing_init` says for each throwaway `git init`.
REFUSED_INIT = "fatal: r1031: no repository can be made here"


def refusing_init(base: Path) -> dict:
    """The environment of a git that makes no throwaway repository: a stub
    first on PATH refuses each `git init` given a `--template`, as every one
    `check` makes is given one, and hands any other command to the real git.
    Which setting stops a `git init` is git's version's to say (CI on
    #1031), so the rows below do not lean on one."""
    stubs = base / "stubs"
    stubs.mkdir()
    stub = stubs / "git"
    stub.write_bytes("\n".join([
        "#!/bin/sh",
        'for arg in "$@"; do',
        '  case "$arg" in --template=*) ;; *) continue ;; esac',
        '  for word in "$@"; do',
        '    [ "$word" = init ] || continue',
        f'    echo "{REFUSED_INIT}" >&2',
        "    exit 128",
        "  done",
        "done",
        'exec "$REAL_GIT" "$@"', ""]).encode("ascii"))
    stub.chmod(0o755)
    return {"PATH": str(stubs) + os.pathsep + os.environ["PATH"],
            "REAL_GIT": shutil.which("git")}


@WINDOWS_SKIP  # a `#!` stub named `git` first on PATH
def test_a_repository_git_cannot_make_is_one_finding_that_says_why(
        tmp_path):
    plan = planned(a_source(tmp_path), tmp_path, {})
    work = tmp_path / "work"
    result = checked(plan, refusing_init(tmp_path), "--work-dir", str(work))
    assert "REFUSED" not in result.stderr, result.stderr
    assert result.returncode == 1, result.stderr
    assert finding_lines(result) == [
        f"FINDING {UNASKED}: " + UNASKED_OPENS.format(os.path.realpath(work))
        + f"`git init` there exited 128: {REFUSED_INIT}" + UNASKED_ENDS]
    assert list(work.iterdir()) == []


def this_gits_clone(base: Path, env: dict) -> subprocess.CompletedProcess:
    """This machine's `git clone` of a repository of its own, under `env`:
    whether it makes one there is its version's to say (CI on #1031)."""
    source = base / "clone-asked-of"
    git("init", "-q", "-b", "main", str(source), cwd=base)
    return subprocess.run(["git", "clone", "-q", "--no-checkout", "--shared",
                           str(source), str(base / "clone-asked")],
                          env={**os.environ, **env}, capture_output=True,
                          check=False)


def unasked_clone(work: Path, code: int, said: str) -> str:
    """`adopt-git-unasked` for a split's clone git ended with `code` and
    `said` in `work`."""
    return (f"FINDING {UNASKED}: "
            + UNASKED_OPENS.format(os.path.realpath(work))
            + f"the split's `git clone` of the source exited {code} there: "
            + said + UNASKED_ENDS)


def test_a_default_branch_is_asked_of_the_splits_own_clone(tmp_path):
    """`init.defaultBranch = a..b`: `check` answers as the split's own `git
    clone` of the source does on this git (#1083). git 2.43's stops at it,
    `fatal: invalid branch name`, and `check` says so as one
    `adopt-git-unasked`, where 2a119f28 said `plan ok` and `execute` then
    stopped after both legs existed. git 2.55's takes it (CI on #1031), and
    there no `git init` stops a question: each names its branch, and the
    CRLF file the plan keeps is found."""
    plan = planned(a_source(tmp_path, files={ROOT_ATTRIBUTES: TEXT_EOL_LF,
                                             NOTES: CRLF}),
                   tmp_path, {NOTES: ROOT})
    work = tmp_path / "work"
    env = bad_default_branch(tmp_path)
    clone = this_gits_clone(tmp_path, env)
    result = checked(plan, env, "--work-dir", str(work))
    assert "REFUSED" not in result.stderr, result.stderr
    assert result.returncode == 1, result.stderr
    if clone.returncode == 0:
        assert codes(result) == [REENCODED_FILES], result.stderr
    else:
        assert finding_lines(result) == [unasked_clone(
            work, clone.returncode, clone.stderr.decode().strip())]
    assert list(work.iterdir()) == []


def test_a_default_branch_git_will_not_take_stops_no_throwaway_init(
        adopter, monkeypatch, tmp_path):
    """Each throwaway `git init` names its branch, as the split's own `git
    init -b` does, so `init.defaultBranch = a..b` stops none of the
    questions asked in them, on any git: asked of the rehearsal, which
    clones nothing, the CRLF file the plan keeps is found. Read, it was
    `adopt-git-unasked`, which `execute` refused, though git 2.55's `git
    clone`, which CI runs, does not stop at it (CI on #1031)."""
    plan = adopter.Plan.load(planned(
        a_source(tmp_path, files={ROOT_ATTRIBUTES: TEXT_EOL_LF, NOTES: CRLF}),
        tmp_path, {NOTES: ROOT}))
    work = tmp_path / "work"
    work.mkdir()
    opened = plan.open_source(None, work)
    for name, value in bad_default_branch(tmp_path).items():
        monkeypatch.setenv(name, value)
    found = adopter._reencoded_files_findings(plan, opened, opened.tree())
    assert len(found) == 1, found
    assert KEPT_CRLF in found[0], found[0]
    assert list(work.iterdir()) == []


@WINDOWS_SKIP  # a `#!` stub named `git` first on PATH
def test_execute_refuses_it_before_any_leg_exists(adopter, monkeypatch,
                                                 tmp_path):
    plan = planned(a_source(tmp_path), tmp_path, {})
    for name, value in refusing_init(tmp_path).items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)
    remotes = tmp_path / "remotes"
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(Namespace(
            plan=str(plan), source=None, local_remote_dir=remotes,
            allow_empty_leg=[], yes=True, work_dir=tmp_path / "work"))
    assert caught.value.code == UNASKED
    assert REFUSED_INIT in caught.value.detail
    assert "no leg repository was created" in caught.value.remediation
    assert not remotes.exists()


def test_a_step_git_fails_in_the_rehearsal_is_one_finding_in_its_words(
        adopter, monkeypatch, tmp_path):
    """A step git fails in the rehearsal's repository once it is made, here
    its `read-tree` of the source commit, is `adopt-git-unasked` in git's
    words, in the place of the question asked there, and no `git-failed`
    refusal stops `check` (`_SplitRehearsal.asked`; r1031's SHOULD-2)."""
    plan = adopter.Plan.load(planned(
        a_source(tmp_path, files={ROOT_ATTRIBUTES: TEXT_EOL_LF, NOTES: CRLF}),
        tmp_path, {NOTES: ROOT}))
    work = tmp_path / "work"
    work.mkdir()
    opened = plan.open_source(None, work)
    real = adopter._SplitRehearsal.git

    def git(self, args, index, data=b""):
        if args[0] == "read-tree":
            return subprocess.CompletedProcess(args, 128, b"",
                                               b"fatal: r1031")
        return real(self, args, index, data)

    monkeypatch.setattr(adopter._SplitRehearsal, "git", git)
    try:
        found, _, _ = adopter._entry_findings(plan, opened)
    except adopter.Refusal as refusal:
        pytest.fail(f"REFUSED {refusal.code}: {refusal.detail}")
    assert len(found) == 1, found
    assert found[0].startswith(
        f"FINDING {UNASKED}: "
        + UNASKED_OPENS.format(os.path.realpath(work))
        + f"`git read-tree {opened.commit}` in "), found[0]
    assert "exited 128: fatal: r1031" in found[0]
    assert found[0].endswith(UNASKED_ENDS), found[0]
    assert list(work.iterdir()) == []


#: The NOTE `check` prints where no throwaway repository can be made in the
#: work directory at all; `{}` is that directory.
UNMADE_NOTE = ("NOTE `check` could not make a throwaway repository in `{}`, "
               "the work directory, to ask this machine's git what the split "
               "will make of the source: a directory or a file could not be "
               "made there (Permission denied). It asked nothing about the "
               "source's paths and files there, nor about the urls of the "
               "submodules the plan keeps; run `check` again with a "
               "--work-dir this user can write in.")


def test_a_work_directory_nothing_can_be_made_in_says_so_once(
        tmp_path, unwritable_work):  # noqa: F811
    """`adopt-work-dir-unwritable` names the directory (#524), the one
    finding for the one cause, as `check` asks it the same way, and a NOTE
    the questions it kept from being asked, where on c7a3ff16 they were
    asked in `TMPDIR`, another disk than the split's."""
    plan = planned(a_source(tmp_path), tmp_path, {})
    result = checked(plan, None, "--work-dir", str(unwritable_work))
    assert "Traceback" not in result.stderr, result.stderr
    assert result.returncode == 1, result.stderr
    assert codes(result) == [WORK_DIR_UNWRITABLE], result.stderr
    assert UNMADE_NOTE.format(os.path.realpath(unwritable_work)) in \
        result.stdout.splitlines(), result.stdout


# ---------------------------------------------------------------------------
# #1083 (a): the split's own clone of the source
# ---------------------------------------------------------------------------

#: What the stub `git` of `refusing_clone` says for every `git clone`.
REFUSED_CLONE = "fatal: w1083: no clone can be made here"


def refusing_clone(base: Path) -> dict:
    """The environment of a git that clones nothing: a stub first on PATH
    refuses each `git clone` and hands any other command to the real git.
    Which setting stops a clone is git's version's to say (CI on #1031), so
    the rows below do not lean on one."""
    stubs = base / "clone-stubs"
    stubs.mkdir()
    stub = stubs / "git"
    stub.write_bytes("\n".join([
        "#!/bin/sh",
        'for arg in "$@"; do',
        '  [ "$arg" = clone ] || continue',
        f'  echo "{REFUSED_CLONE}" >&2',
        "  exit 128",
        "done",
        'exec "$REAL_GIT" "$@"', ""]).encode("ascii"))
    stub.chmod(0o755)
    return {"PATH": str(stubs) + os.pathsep + os.environ["PATH"],
            "REAL_GIT": shutil.which("git")}


@WINDOWS_SKIP  # a `#!` stub named `git` first on PATH
def test_a_clone_git_will_not_make_is_one_finding_that_says_why(tmp_path):
    """The split's first act after it makes both legs is its `git clone` of
    the source, and `check` makes that clone first, in the work directory:
    where git will not make it, that is one `adopt-git-unasked` in git's
    words, the questions after it are not asked, and nothing is left there.
    On 2a119f28 `check` cloned nothing, and said `plan ok`."""
    plan = planned(a_source(tmp_path, files={ROOT_ATTRIBUTES: TEXT_EOL_LF,
                                             NOTES: CRLF}),
                   tmp_path, {NOTES: ROOT})
    work = tmp_path / "work"
    result = checked(plan, refusing_clone(tmp_path), "--work-dir", str(work))
    assert "REFUSED" not in result.stderr, result.stderr
    assert result.returncode == 1, result.stderr
    assert finding_lines(result) == [unasked_clone(work, 128, REFUSED_CLONE)]
    assert list(work.iterdir()) == []


@WINDOWS_SKIP  # a `#!` stub named `git` first on PATH
def test_execute_refuses_a_clone_git_will_not_make_before_any_leg(
        adopter, monkeypatch, tmp_path):
    """On 2a119f28 `execute` made both legs, and its first clone of the
    source then stopped it, with nothing rolled back."""
    plan = planned(a_source(tmp_path), tmp_path, {})
    for name, value in refusing_clone(tmp_path).items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)
    remotes = tmp_path / "remotes"
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(Namespace(
            plan=str(plan), source=None, local_remote_dir=remotes,
            allow_empty_leg=[], yes=True, work_dir=tmp_path / "work"))
    assert caught.value.code == UNASKED
    assert REFUSED_CLONE in caught.value.detail
    assert "no leg repository was created" in caught.value.remediation
    assert not remotes.exists()


def test_the_clone_is_asked_with_the_protocol_setting_execute_gives_it(
        tmp_path):
    """`protocol.file.allow = never` in this machine's config refuses a
    `git clone` of a path, and `execute` gives each of its clones
    `-c protocol.file.allow=always` (`FILE_PROTOCOL`), so `check` asks the
    split's clone with it too, and finds nothing: a control, `plan ok` on
    2a119f28 as here."""
    plan = planned(a_source(tmp_path), tmp_path, {})
    work = tmp_path / "work"
    result = checked(plan, config_with(tmp_path, '[protocol "file"]',
                                       "\tallow = never"),
                     "--work-dir", str(work))
    assert result.returncode == 0, result.stderr
    assert "plan ok" in result.stdout
    assert list(work.iterdir()) == []


@WINDOWS_SKIP  # a `#!` stub named `git` first on PATH
def test_no_url_is_asked_once_the_clone_cannot_be_made(tmp_path):
    """Where the split's clone cannot be made, that is the one finding, and
    no url question is asked after it, in a repository of the same work
    directory, as no other is (#910): one cause, one finding. On 2a119f28
    `check` cloned nothing and named the relative url alone."""
    work = tmp_path / "work"
    result = checked(url_plan(tmp_path), refusing_clone(tmp_path),
                     "--work-dir", str(work))
    assert "REFUSED" not in result.stderr, result.stderr
    assert finding_lines(result) == [unasked_clone(work, 128, REFUSED_CLONE)]
    assert list(work.iterdir()) == []


def test_execute_refuses_a_default_branch_its_clone_will_not_take(
        adopter, monkeypatch, tmp_path):
    """`init.defaultBranch = a..b`, on a git whose `git clone` stops at it,
    as 2.43's does: `execute` refuses it before any leg exists, where on
    2a119f28 it made both and stopped extracting the spec leg (#1083)."""
    plan = planned(a_source(tmp_path), tmp_path, {})
    env = bad_default_branch(tmp_path)
    if this_gits_clone(tmp_path, env).returncode == 0:
        pytest.skip("this git's `git clone` takes `init.defaultBranch = "
                    "a..b`, as 2.55's does: the split clones there")
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)
    remotes = tmp_path / "remotes"
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(Namespace(
            plan=str(plan), source=None, local_remote_dir=remotes,
            allow_empty_leg=[], yes=True, work_dir=tmp_path / "work"))
    assert caught.value.code == UNASKED
    assert "invalid branch name" in caught.value.detail
    assert not remotes.exists()


# ---------------------------------------------------------------------------
# #1083 (b): the submodule urls' own throwaway repositories
# ---------------------------------------------------------------------------

def a_url_and_nowhere(base: Path) -> tuple[Path, str, str]:
    """`(source, url, nowhere)`: a source that keeps a submodule whose url
    is relative and one whose url is `url`, an absolute path on this disk
    where a repository answers; and `nowhere`, a directory beside it that
    holds nothing, for a rewrite of that url to name."""
    dependency = base / "dependency"
    source = source_with(base, SIBLING, second=dependency.as_posix(),
                         dependency=dependency)
    return source, dependency.as_posix(), (base / "nowhere").as_posix()


def kept_in_the_code_leg(source: Path, base: Path) -> Path:
    """A plan of `a_url_and_nowhere`'s `source` that keeps both submodules
    in the code leg."""
    return planned_with_urls(source, base,
                             answers={**BOTH_IN_CODE, EXTRA: "code"})


def url_plan(base: Path) -> Path:
    """A plan that keeps in the code leg a submodule whose url is relative,
    which `_resolved` resolves from the source and from the leg, and one
    whose url is an absolute path on this disk, which `_answers` asks."""
    source, _, _ = a_url_and_nowhere(base)
    return kept_in_the_code_leg(source, base)


def asked_with_urls(adopter, base: Path):
    """`(plan, opened, work)`: `url_plan`, opened in a work directory."""
    plan = adopter.Plan.load(url_plan(base))
    work = base / "work"
    work.mkdir()
    return plan, plan.open_source(None, work), work


def the_clone_as_2_55_makes_it(adopter, monkeypatch) -> None:
    """The split's own clone made, as git 2.55's `git clone` makes it under
    an `init.defaultBranch` 2.43's stops at (CI on #1031), so that the rows
    below ask what the urls' own repositories make of the setting on any
    git. (`raising=False`: 2a119f28 makes no such clone.)"""
    monkeypatch.setattr(adopter, "_split_clone_asked", lambda _source: None,
                        raising=False)


#: `(what this machine's git is given, how the row is named)`: each stopped
#: `check` with "a git or gh command failed" at `_resolved`'s `git init -q
#: <TMPDIR>/openreposhape-url-*` on 2a119f28.
URL_SETTINGS = [
    pytest.param(bad_default_branch, id="init-default-branch-a..b"),
    pytest.param(lambda _base: {"GIT_DEFAULT_HASH": "bogus"},
                 id="git-default-hash-bogus"),
]


@pytest.mark.parametrize("setting", URL_SETTINGS)
def test_the_submodule_urls_are_asked_whatever_the_setting(
        adopter, monkeypatch, tmp_path, setting):
    """Each of `_resolved`'s and `_answers`' repositories names its branch
    and the source's format, as every throwaway does: what `check` says of
    the urls under the setting is what it says without it."""
    plan, opened, work = asked_with_urls(adopter, tmp_path)
    wanted = adopter._entry_findings(plan, opened)
    assert [line.split(" ", 2)[1].rstrip(":") for line in wanted[0]] == [
        RELATIVE_URL], wanted[0]
    the_clone_as_2_55_makes_it(adopter, monkeypatch)
    for name, value in setting(tmp_path).items():
        monkeypatch.setenv(name, value)
    assert adopter._entry_findings(plan, opened) == wanted
    assert list(work.iterdir()) == []


def test_the_submodule_urls_are_asked_in_the_work_directory(
        adopter, monkeypatch, tmp_path):
    """`_resolved`'s and `_answers`' repositories are made in the work
    directory the source was opened in, where 2a119f28 made them in
    `TMPDIR`, and none is left there."""
    plan, opened, work = asked_with_urls(adopter, tmp_path)
    made = recording_where_made(adopter, monkeypatch)
    adopter._entry_findings(plan, opened)
    asked = asked_where(made, URL_PREFIXES)
    assert {prefix for prefix, _ in asked} == set(URL_PREFIXES), made
    assert {parent for _, parent in asked} == {work.resolve()}
    assert list(work.iterdir()) == []


@pytest.mark.parametrize("configured", [
    pytest.param(in_the_global_config, id="global-config"),
    pytest.param(in_the_command_scope, id="git-config-count")])
def test_no_hook_of_this_machines_runs_where_the_urls_are_asked(
        tmp_path, configured):
    """On 2a119f28 `_resolved`'s `update-index` ran the counting
    `post-index-change` hook twice in this `check`, once for each side a
    relative url is resolved from."""
    plan = url_plan(tmp_path)
    hooks, log = counting_hooks(tmp_path)
    result = checked(plan, configured(tmp_path, hooks))
    assert "REFUSED" not in result.stderr, result.stderr
    assert codes(result) == [RELATIVE_URL], result.stderr
    assert runs(log) == []


def counting_fsmonitor(base: Path) -> tuple[Path, Path]:
    """`(program, log)`: a `core.fsmonitor` program that adds a line to
    `log` each time git runs it, and exits 1, which git takes as a monitor
    that cannot say what changed, and goes on without it."""
    program = base / "fsmonitor"
    log = base / "fsmonitor-runs.log"
    program.write_bytes(f"#!/bin/sh\necho fsmonitor >> '{log.as_posix()}'\n"
                        "exit 1\n".encode())
    program.chmod(0o755)
    return program, log


#: Where this machine's `core.fsmonitor` program is configured.
FSMONITOR_CONFIGURED = [
    pytest.param(lambda base, program: config_with(
        base, "[core]", f'\tfsmonitor = "{program.as_posix()}"'),
        id="global-config"),
    pytest.param(lambda _base, program: appended_to_command_scope(
        os.environ, [("core.fsmonitor", program.as_posix())]),
        id="git-config-count")]


@pytest.mark.parametrize("configured", FSMONITOR_CONFIGURED)
def test_no_fsmonitor_of_this_machines_runs_where_the_urls_are_asked(
        tmp_path, configured):
    """`_resolved`'s and `_answers`' repositories are given
    `core.fsmonitor=false`, as the rehearsal's and #619's are, so no
    fsmonitor program or daemon of this machine's is started for a
    repository that is about to go. On 9b998936 the counting program ran
    8 times in this `check`, in `_resolved`'s two repositories (r1119b's
    SHOULD-A)."""
    plan = url_plan(tmp_path)
    program, log = counting_fsmonitor(tmp_path)
    result = checked(plan, configured(tmp_path, program))
    assert "REFUSED" not in result.stderr, result.stderr
    assert codes(result) == [RELATIVE_URL], result.stderr
    assert runs(log) == []


@pytest.mark.parametrize("configured", FSMONITOR_CONFIGURED)
def test_the_counting_fsmonitor_runs_where_this_machines_config_reaches(
        tmp_path, configured):
    """The control: the same config runs the program for a `git add` in a
    repository of its own, so the row above counts something that would
    run."""
    program, log = counting_fsmonitor(tmp_path)
    repository = tmp_path / "ordinary"
    git("init", "-q", str(repository), cwd=tmp_path)
    (repository / "a").write_bytes(b"a\n")
    subprocess.run(["git", "add", "a"], cwd=str(repository), check=True,
                   env={**os.environ, **configured(tmp_path, program)})
    assert runs(log) != []


def test_a_url_question_git_cannot_ask_is_one_finding_after_the_rest(
        adopter, monkeypatch, tmp_path):
    """Where `_answers`' repository cannot be made or asked, that is
    `adopt-git-unasked`, once, as for every throwaway: the relative url
    `_resolved` answered before it is still said, and no question after it
    is asked, nor the NOTE of urls `_answers` would not ask. On 2a119f28 it
    was a `Refusal` out of `check`."""
    plan, opened, work = asked_with_urls(adopter, tmp_path)

    def unasked(_urls, _source=None):
        raise adopter._Unasked(work, "w1083: not here")

    monkeypatch.setattr(adopter, "_answers", unasked)
    asked = []
    monkeypatch.setattr(adopter, "_asked_in_throwaways",
                        lambda *args: asked.append(args) or ([], []))
    try:
        found, _, notes = adopter._entry_findings(plan, opened)
    except adopter.Refusal as refusal:
        pytest.fail(f"REFUSED {refusal.code}: {refusal.detail}")
    assert [line.split(" ", 2)[1].rstrip(":") for line in found] == [
        UNASKED, RELATIVE_URL], found
    assert "w1083: not here" in found[0]
    assert asked == []
    assert not any("did not ask whether the url" in note for note in notes)


def test_a_step_git_fails_in_a_url_repository_is_unasked_in_its_words(
        adopter, tmp_path):
    """A step git fails in `_resolved`'s or `_answers`' repository once it
    is made is `adopt-git-unasked` in git's words, as one in the rehearsal
    is, and never "a git or gh command failed" (`_throwaway_git`)."""
    work = tmp_path / "work"
    work.mkdir()
    scratch = work / "scratch"
    scratch.mkdir()
    env = adopter._inherited_env()
    hooks_off = adopter._throwaway_made(
        scratch, scratch / adopter.THROWAWAY_REPOSITORY, None, env)
    assert adopter._throwaway_git(scratch, hooks_off,
                                  ["rev-parse", "--is-inside-work-tree"],
                                  env) == "true"
    with pytest.raises(adopter._Unasked) as caught:
        adopter._throwaway_git(scratch, hooks_off, ["hash-object", "absent"],
                               env)
    assert caught.value.code == UNASKED
    assert caught.value.where == work
    assert caught.value.why.startswith("`git hash-object` in "), \
        caught.value.why
    assert "exited 128: fatal: " in caught.value.why, caught.value.why
    assert "absent" in caught.value.why, caught.value.why


def test_a_work_directory_nothing_can_be_made_in_asks_no_url(
        tmp_path, unwritable_work):  # noqa: F811
    """No url question is asked in a work directory nothing can be made in:
    `adopt-work-dir-unwritable` is the one finding, as for every other
    throwaway (#524, #910), where 2a119f28 asked the urls in `TMPDIR`, and
    one `_Unasked` more would have stopped `check`."""
    plan = url_plan(tmp_path)
    result = checked(plan, None, "--work-dir", str(unwritable_work))
    assert "Traceback" not in result.stderr, result.stderr
    assert "REFUSED" not in result.stderr, result.stderr
    assert codes(result) == [WORK_DIR_UNWRITABLE], result.stderr
    assert UNMADE_NOTE.format(os.path.realpath(unwritable_work)) in \
        result.stdout.splitlines(), result.stdout


# ---------------------------------------------------------------------------
# #1083 (c): a work directory not made yet, and case twins
# ---------------------------------------------------------------------------

def test_a_work_directory_not_made_yet_is_made_and_asked_in(adopter,
                                                           tmp_path):
    """r1031's NIT-R2-2: a `Source` opened outside a command, on a work
    directory that is not there, is asked as one `check --work-dir` makes
    (`_throwaway`'s `_made_0755`): the CRLF file is found, there is no NOTE
    of a directory that could not be made, and the directory is left there,
    empty. Before #910 its questions were asked in `TMPDIR`."""
    plan = adopter.Plan.load(planned(
        a_source(tmp_path, files={ROOT_ATTRIBUTES: TEXT_EOL_LF, NOTES: CRLF}),
        tmp_path, {NOTES: ROOT}))
    work = tmp_path / "not-made" / "yet"
    found, _, notes = adopter._entry_findings(
        plan, plan.open_source(None, work))
    assert [line.split(" ", 2)[1].rstrip(":") for line in found] == [
        REENCODED_FILES], found
    assert not any(note.startswith(
        "NOTE `check` could not make a throwaway repository")
        for note in notes), notes
    assert list(work.iterdir()) == []


#: Two paths one case-insensitive disk holds as one file.
TWINS = ("Notes.md", "notes.md")


def test_case_twins_are_both_held_under_core_ignorecase(adopter, monkeypatch,
                                                        tmp_path):
    """`_paths_git_refuses` hands every path of the source commit to `git
    update-index --index-info`, and names `plan-path-git-refuses` for one
    the index then lacks. On a case-insensitive disk `git init` sets
    `core.ignorecase=true`, and `git add` will not hold case twins. That
    question reads no file of the disk, only the setting, which this row
    sets on a disk that holds both twins: the control shows git honours it
    (`git add` holds one twin at most), and `--index-info` still holds
    both, so neither is named."""
    source = a_source(tmp_path)
    with_paths(source, TWINS)
    plan = adopter.Plan.load(planned(source, tmp_path, {}))
    work = tmp_path / "work"
    work.mkdir()
    opened = plan.open_source(None, work)
    for name, value in config_with(tmp_path, "[core]",
                                   "\tignorecase = true").items():
        monkeypatch.setenv(name, value)
    control = tmp_path / "control"
    git("init", "-q", "-b", "main", str(control), cwd=tmp_path)
    for twin, data in zip(TWINS, (b"a\n", b"b\n")):
        (control / twin).write_bytes(data)
    subprocess.run(["git", "add", "--", *TWINS], cwd=str(control),
                   capture_output=True, check=False)
    held = git("ls-files", cwd=control).stdout.split()
    assert len(held) < 2, held
    assert adopter._paths_git_refuses(opened, opened.tree()) == []
    assert list(work.iterdir()) == []


# ---------------------------------------------------------------------------
# r1119: what the split's own clone inherits, and what it must not
# ---------------------------------------------------------------------------

def with_parameters(_base: Path, entries) -> dict:
    """`entries` as a parent git hands them: `git -c <key>=<value>`
    running an alias or a hook that runs `adopt-project.py`."""
    return appended_to_parameters(entries)


def with_command_scope(_base: Path, entries) -> dict:
    """`entries` in git's command scope (`GIT_CONFIG_COUNT`)."""
    return appended_to_command_scope(os.environ, entries)


def with_global_config(base: Path, entries) -> dict:
    """`entries` in a global config file."""
    lines = []
    for key, value in entries:
        section, _, name = key.rpartition(".")
        lines += [f"[{section}]", f"\t{name} = {value}"]
    return config_with(base, *lines)


#: The two forms in which a parent git hands this process its settings. On
#: bdcf9952 `_inherited_env()` gave the split's own clone the second and
#: left out the first, which `execute`'s clone takes (r1119's SHOULD-2).
FROM_A_PARENT = [
    pytest.param(with_parameters, id="git-config-parameters"),
    pytest.param(with_command_scope, id="git-config-count")]
BAD_DEFAULT_BRANCH = [("init.defaultBranch", "a..b")]


@pytest.mark.parametrize("handed", FROM_A_PARENT)
def test_a_parent_gits_default_branch_is_asked_of_the_splits_own_clone(
        tmp_path, handed):
    """`init.defaultBranch = a..b`, handed down by a parent git, as the
    global config's is asked above: git 2.43's `git clone` stops at it,
    and `check` says so as one `adopt-git-unasked`. On bdcf9952 the clone
    took no `GIT_CONFIG_PARAMETERS`, and `check` said `plan ok` where
    `execute`'s clone, which takes the whole environment, stopped after
    both legs existed. git 2.55's clone takes the name, and there the CRLF
    file the plan keeps is found."""
    plan = planned(a_source(tmp_path, files={ROOT_ATTRIBUTES: TEXT_EOL_LF,
                                             NOTES: CRLF}),
                   tmp_path, {NOTES: ROOT})
    work = tmp_path / "work"
    env = handed(tmp_path, BAD_DEFAULT_BRANCH)
    clone = this_gits_clone(tmp_path, env)
    result = checked(plan, env, "--work-dir", str(work))
    assert "REFUSED" not in result.stderr, result.stderr
    assert result.returncode == 1, result.stderr
    if clone.returncode == 0:
        assert codes(result) == [REENCODED_FILES], result.stderr
    else:
        assert finding_lines(result) == [unasked_clone(
            work, clone.returncode, clone.stderr.decode().strip())]
    assert list(work.iterdir()) == []


@pytest.mark.parametrize("handed", FROM_A_PARENT)
def test_execute_refuses_a_parent_gits_default_branch_before_any_leg(
        adopter, monkeypatch, tmp_path, handed):
    """Measured on bdcf9952 with git 2.43 and `GIT_CONFIG_PARAMETERS`:
    `execute` made both legs and stopped extracting the spec leg, `fatal:
    invalid branch name`, with nothing rolled back."""
    plan = planned(a_source(tmp_path), tmp_path, {})
    env = handed(tmp_path, BAD_DEFAULT_BRANCH)
    if this_gits_clone(tmp_path, env).returncode == 0:
        pytest.skip("this git's `git clone` takes `init.defaultBranch = "
                    "a..b`, as 2.55's does: the split clones there")
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)
    remotes = tmp_path / "remotes"
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(Namespace(
            plan=str(plan), source=None, local_remote_dir=remotes,
            allow_empty_leg=[], yes=True, work_dir=tmp_path / "work"))
    assert caught.value.code == UNASKED
    assert "invalid branch name" in caught.value.detail
    assert not remotes.exists()


#: The setting the stub `git` of `refusing_a_setting` reads, under a key no
#: config of a machine this runs on sets, and what it says when it is set.
REFUSING_KEY = "test.refusesplitclone"
REFUSED_BY_SETTING = "fatal: f1119: a setting this clone reads refuses it"


def refusing_a_setting(base: Path) -> dict:
    """The environment of a git whose `git clone` stops at a setting, on
    every version: a stub first on PATH asks the real git whether the
    config that clone reads -- the files, `GIT_CONFIG_COUNT` and
    `GIT_CONFIG_PARAMETERS` alike -- sets `REFUSING_KEY` to `yes`, and
    refuses the clone where it does. Any other command is the real git's.
    `init.defaultBranch = a..b` stops git 2.43's clone and not 2.55's (CI
    on #1031), so the rows below do not lean on it."""
    stubs = base / "setting-stubs"
    stubs.mkdir()
    stub = stubs / "git"
    stub.write_bytes("\n".join([
        "#!/bin/sh",
        'for arg in "$@"; do',
        '  [ "$arg" = clone ] || continue',
        f'  if [ "$("$REAL_GIT" config --get {REFUSING_KEY})" = yes ]; then',
        f'    echo "{REFUSED_BY_SETTING}" >&2',
        "    exit 128",
        "  fi",
        "  break",
        "done",
        'exec "$REAL_GIT" "$@"', ""]).encode("ascii"))
    stub.chmod(0o755)
    return {"PATH": str(stubs) + os.pathsep + os.environ["PATH"],
            "REAL_GIT": shutil.which("git")}


#: Each form a setting can reach the split's clone in: a file, as the rows
#: of #1083 ask it, and the two a parent git hands down.
EVERY_FORM = [pytest.param(with_global_config, id="global-config"),
              *FROM_A_PARENT]


@WINDOWS_SKIP  # a `#!` stub named `git` first on PATH
@pytest.mark.parametrize("handed", EVERY_FORM)
def test_a_setting_that_stops_the_clone_is_asked_in_every_form(tmp_path,
                                                               handed):
    """Whatever form the setting comes in, `check`'s clone reads it as the
    split's does, and one that stops it is one `adopt-git-unasked`, on any
    version of git. On bdcf9952 `git-config-parameters` was `plan ok`."""
    plan = planned(a_source(tmp_path), tmp_path, {})
    work = tmp_path / "work"
    env = {**refusing_a_setting(tmp_path),
           **handed(tmp_path, [(REFUSING_KEY, "yes")])}
    result = checked(plan, env, "--work-dir", str(work))
    assert "REFUSED" not in result.stderr, result.stderr
    assert result.returncode == 1, result.stderr
    assert finding_lines(result) == [
        unasked_clone(work, 128, REFUSED_BY_SETTING)]
    assert list(work.iterdir()) == []


@WINDOWS_SKIP  # a `#!` stub named `git` first on PATH
@pytest.mark.parametrize("handed", EVERY_FORM)
def test_execute_refuses_a_setting_that_stops_its_clone_before_any_leg(
        adopter, monkeypatch, tmp_path, handed):
    """`execute`'s first clone of the source reads the setting in the whole
    environment; on bdcf9952, under `git-config-parameters`, it was the
    first to read it, after both legs existed."""
    plan = planned(a_source(tmp_path), tmp_path, {})
    env = {**refusing_a_setting(tmp_path),
           **handed(tmp_path, [(REFUSING_KEY, "yes")])}
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)
    remotes = tmp_path / "remotes"
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(Namespace(
            plan=str(plan), source=None, local_remote_dir=remotes,
            allow_empty_leg=[], yes=True, work_dir=tmp_path / "work"))
    assert caught.value.code == UNASKED
    assert REFUSED_BY_SETTING in caught.value.detail
    assert "no leg repository was created" in caught.value.remediation
    assert not remotes.exists()


#: The variables that name another repository, its objects, an index or a
#: work tree, and a tree to read attributes from, and what each names below
#: the test's directory: no throwaway takes one.
ANOTHER_REPOSITORY = {
    "GIT_DIR": "git-dir", "GIT_WORK_TREE": "work-tree",
    "GIT_INDEX_FILE": "index", "GIT_COMMON_DIR": "common",
    "GIT_OBJECT_DIRECTORY": "objects", "GIT_ATTR_SOURCE": "HEAD"}


def test_the_clone_takes_a_parent_gits_settings_and_no_other_repository(
        adopter, monkeypatch, tmp_path):
    """`_split_clone_env()`: `_inherited_env()`, which keeps
    `GIT_CONFIG_COUNT` but an `attr.tree` in it, and the parent's
    `GIT_CONFIG_PARAMETERS` as it stands; and none of the variables that
    name another repository, its objects, an index or a work tree, nor
    `GIT_ATTR_SOURCE`. With no parent setting there is none. The two
    entries are appended after those the environment holds, as every test
    gives git a setting (`appended_to_command_scope`, #758), and the last
    entry `_split_clone_env()` keeps is the second (r1119b's MUST-1)."""
    named = ANOTHER_REPOSITORY
    for name, value in named.items():
        monkeypatch.setenv(name, str(tmp_path / value))
    parameters = "'test.parentone'='one' 'core.hooksPath'='/nowhere'"
    monkeypatch.setenv("GIT_CONFIG_PARAMETERS", parameters)
    for name, value in appended_to_command_scope(
            os.environ,
            [("attr.tree", "HEAD"), ("test.heldone", "one")]).items():
        monkeypatch.setenv(name, value)
    env = adopter._split_clone_env()
    assert env["GIT_CONFIG_PARAMETERS"] == parameters
    assert [env.get(name) for name in named] == [None] * len(named)
    scoped = [(env[f"GIT_CONFIG_KEY_{n}"], env[f"GIT_CONFIG_VALUE_{n}"])
              for n in range(int(env["GIT_CONFIG_COUNT"]))]
    assert scoped[-1] == ("test.heldone", "one")
    assert "attr.tree" not in [key.lower() for key, _ in scoped]
    monkeypatch.delenv("GIT_CONFIG_PARAMETERS")
    assert "GIT_CONFIG_PARAMETERS" not in adopter._split_clone_env()


def objects_of(repository: Path) -> dict:
    """Each file below `repository`'s object directory, and its bytes."""
    objects = repository / ".git" / "objects"
    return {path.relative_to(objects).as_posix(): path.read_bytes()
            for path in sorted(objects.rglob("*")) if path.is_file()}


def test_the_clone_writes_nothing_into_an_object_directory_around_it(
        tmp_path):
    """r1119's SHOULD-1: `GIT_OBJECT_DIRECTORY` names the source's own
    objects, as it does for a command git runs in the source. `check`
    promises never to write into the source, and its clone of it takes
    no such variable (`_inherited_env()`): `plan ok`, and the source's
    object directory as it was. In the whole environment the clone wrote
    `objects/info/alternates` there, naming the throwaway's own objects,
    which `check` then removes (r1119, M6)."""
    source = a_source(tmp_path)
    plan = planned(source, tmp_path, {})
    before = objects_of(source)
    work = tmp_path / "work"
    result = checked(plan, {"GIT_OBJECT_DIRECTORY": str(
        source / ".git" / "objects")}, "--work-dir", str(work))
    assert result.returncode == 0, result.stderr
    assert "plan ok" in result.stdout
    assert objects_of(source) == before
    assert list(work.iterdir()) == []


def rewritten_in_the_source(source: Path, url: str, target: str) -> None:
    """The source's own config rewrites `url` to `target`; the control:
    git there expands it so (`--get-url` contacts nothing)."""
    git("config", f"url.{target}.insteadOf", url, cwd=source)
    assert git("ls-remote", "--get-url", url,
               cwd=source).stdout.strip() == target


def test_a_repository_around_check_rewrites_no_url_it_asks(tmp_path):
    """`_answers` asks each url in a throwaway repository of its own, so
    that no repository's config around this process rewrites a url, as
    the assembly's recursive clone would not: here `GIT_DIR` names the
    source, as it does for a hook git runs there, and the source's own
    config rewrites the on-disk url to a directory that holds nothing
    (the control: git there expands it so). `check` says what it says with
    no `GIT_DIR`; in the whole environment `_answers` read the rewrite,
    and found the url answering nothing (r1119, M14). Nor is the source's
    config written: `_resolved` sets `remote.origin.url` in its own
    repository, which in the whole environment is the source."""
    source, url, nowhere = a_url_and_nowhere(tmp_path)
    rewritten_in_the_source(source, url, nowhere)
    plan = kept_in_the_code_leg(source, tmp_path)
    config = (source / ".git" / "config").read_bytes()
    for env in ({}, {"GIT_DIR": str(source / ".git")}):
        result = checked(plan, env)
        assert "REFUSED" not in result.stderr, result.stderr
        assert codes(result) == [RELATIVE_URL], (env, result.stderr)
        assert (source / ".git" / "config").read_bytes() == config, env


#: How the NOTE begins that names each kept url `check` did not ask, as a
#: config here rewrites it off the disk.
URL_NOT_ASKED = ("NOTE `check` did not ask whether the url of each "
                 "submodule the plan keeps")
#: Where the source's own config sends the on-disk url: a directory that
#: holds nothing, which `git ls-remote` finds answering nothing, and a
#: network, which `check` names in `URL_NOT_ASKED` and does not ask.
REWRITTEN_TO = [
    pytest.param(lambda _source, nowhere: nowhere,
                 id="a-directory-holding-nothing"),
    pytest.param(lambda source, _nowhere: "https://f1119c.invalid/"
                 + source.name, id="a-network")]


@pytest.mark.parametrize("rewritten_to", REWRITTEN_TO)
def test_a_work_directory_inside_the_source_rewrites_no_url_it_asks(
        tmp_path, rewritten_to):
    """`--work-dir` inside the source's own work tree, whose config
    rewrites the on-disk url: `_answers` asks git in its throwaway
    repository, which git finds before the source around it, so `check`
    says what it says with a work directory outside the source, leaves
    nothing there and writes nothing into the source's config. Asked in
    the throwaway's own directory, which is no repository, git found the
    source around it and read its rewrite (r1119b's NIT-A): `git
    ls-remote` there gave a false `plan-submodule-url-answers-nothing`
    (R8), and `--get-url` there a NOTE of a url on a network not asked."""
    source, url, nowhere = a_url_and_nowhere(tmp_path)
    rewritten_in_the_source(source, url, rewritten_to(source, nowhere))
    plan = kept_in_the_code_leg(source, tmp_path)
    config = (source / ".git" / "config").read_bytes()
    for work in (tmp_path / "work", source / "work"):
        result = checked(plan, None, "--work-dir", str(work))
        assert "REFUSED" not in result.stderr, result.stderr
        assert codes(result) == [RELATIVE_URL], (work, result.stderr)
        assert URL_NOT_ASKED not in result.stdout + result.stderr, \
            (work, result.stdout)
        assert list(work.iterdir()) == []
    assert (source / ".git" / "config").read_bytes() == config


def test_a_parent_gits_url_rewrite_is_not_read_where_a_url_is_asked(
        tmp_path):
    """A parent git's `-c url.<nowhere>.insteadOf=<url>`: the split's own
    clone takes the settings a parent hands down (`_split_clone_env`), and
    the assembly's recursive clone, run later by no such parent, does not,
    so `_answers` leaves `GIT_CONFIG_PARAMETERS` out, as its docstring
    says, and `check` says what it says without it. Taking it, `_answers`
    found the url answering nothing (r1119b's NIT-B, A18). The control:
    git expands the url so under it."""
    source, url, nowhere = a_url_and_nowhere(tmp_path)
    plan = kept_in_the_code_leg(source, tmp_path)
    handed = appended_to_parameters([(f"url.{nowhere}.insteadOf", url)])
    expanded = subprocess.run(["git", "ls-remote", "--get-url", url],
                              cwd=str(tmp_path), capture_output=True,
                              env={**os.environ, **handed}, check=True)
    assert expanded.stdout.decode().strip() == nowhere
    for env in ({}, handed):
        result = checked(plan, env)
        assert "REFUSED" not in result.stderr, result.stderr
        assert codes(result) == [RELATIVE_URL], (env, result.stderr)


@pytest.mark.parametrize("asked", [
    pytest.param(lambda adopter, source: adopter._resolved(
        "..", ["../x"], None, source), id="resolved"),
    pytest.param(lambda adopter, source: adopter._answers(["/x"], source),
                 id="answers"),
    pytest.param(lambda adopter, source: adopter._split_clone_asked(source),
                 id="split-clone"),
    pytest.param(lambda adopter, source: adopter._AttributesProbe(source),
                 id="attributes-probe"),
    pytest.param(lambda adopter, source: adopter._stored_as_written(
        b"x\n", "100644", b"x\n", source), id="stored-as-written"),
    pytest.param(lambda adopter, source: adopter._SplitRehearsal(source),
                 id="split-rehearsal")])
def test_an_environment_read_that_raises_leaves_no_throwaway(
        adopter, monkeypatch, tmp_path, asked):
    """r1119's NIT-3: each reads its environment before it makes its
    throwaway, so that a raise there leaves none in the work directory.
    On bdcf9952 `_resolved` and `_answers` made it first, and on bba168bd
    `_AttributesProbe`, `_stored_as_written` and the rehearsal did (#1136):
    each left its throwaway behind. The last two read
    `_split_checkout_env()`, the others `_inherited_env()`, so both are
    made to raise. (By reading, a
    `GIT_CONFIG_COUNT` of a superscript two raised in `_inherited_env()`,
    whose `isdigit()` is true and whose `int()` raises; measured, git
    refuses that count itself, `bogus count in GIT_CONFIG_COUNT`, at
    `check`'s first command, before any throwaway.)"""
    plan = adopter.Plan.load(planned(a_source(tmp_path), tmp_path, {}))
    work = tmp_path / "work"
    work.mkdir()
    opened = plan.open_source(None, work)
    opened.object_format()

    def unreadable():
        raise RuntimeError("f1119: no environment")

    monkeypatch.setattr(adopter, "_inherited_env", unreadable)
    monkeypatch.setattr(adopter, "_split_checkout_env", unreadable)
    with pytest.raises(RuntimeError, match="f1119: no environment"):
        asked(adopter, opened)
    assert list(work.iterdir()) == []


# ---------------------------------------------------------------------------
# #1136: a parent git's settings, and `GIT_ATTR_SOURCE`, in the throwaways
# ---------------------------------------------------------------------------

PARAMETERS = "GIT_CONFIG_PARAMETERS"
REENCODED_ATTRIBUTES = "plan-attributes-reencoded"
#: A path git takes on Linux and refuses under `core.protectHFS=true`: `.git`
#: with a zero-width non-joiner in it, which HFS+ ignores in a name.
HFS_PATH = ".g\u200cit/x"
#: Its entry in the plan, and its name in `check`'s finding, as `_spelled`
#: writes them.
HFS_ENTRY = '".g\\u200cit/"'
HFS_SAID = ".g\\u200cit/x"
PROTECT_HFS = [("core.protectHFS", "true")]


def the_index_holds(base: Path, path: str, env: dict) -> bool:
    """Whether this machine's git, under `env` laid over this process's
    environment, holds `path` in an index. `update-index --index-info` says
    `Ignoring path` of one it refuses and still exits 0, so the index is
    read back."""
    repository = base / "index-asked"
    git("init", "-q", str(repository), cwd=base)
    laid = {**os.environ, **env}
    blob = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                          cwd=str(repository), input=b"x\n",
                          capture_output=True, check=True)
    subprocess.run(["git", "update-index", "--add", "--index-info"],
                   cwd=str(repository), env=laid, capture_output=True,
                   input=f"100644 {blob.stdout.decode().strip()}\t{path}\n"
                   .encode(), check=False)
    held = subprocess.run(["git", "ls-files", "-z"], cwd=str(repository),
                          env=laid, capture_output=True, check=True)
    return path.encode() in held.stdout.split(b"\0")


def hfs_plan(base: Path) -> Path:
    """The plan for a source whose tree holds `HFS_PATH`, kept in the root."""
    source = a_source(base)
    with_paths(source, (HFS_PATH,))
    return planned(source, base, {HFS_ENTRY: ROOT})


def protect_hfs_handed(base: Path, handed) -> dict:
    """`PROTECT_HFS` in the form `handed` gives it, or a skip where this
    git still holds `HFS_PATH` under it."""
    env = handed(base, PROTECT_HFS)
    if the_index_holds(base, HFS_PATH, env):
        pytest.skip("this git holds `.g` + U+200C + `it/x` in an index "
                    "under `core.protectHFS=true`")
    return env


@pytest.mark.parametrize("handed", FROM_A_PARENT)
def test_a_parent_gits_protect_hfs_is_asked_in_the_rehearsal(tmp_path,
                                                             handed):
    """`core.protectHFS=true`, handed down by a parent git, over a source
    path `.g` + U+200C + `it/x`: the rehearsal takes the setting, as the
    split's checkout does, and says the path is one git refuses. Measured
    on bba168bd with git 2.43: under `git-config-parameters`, `check` said
    `plan ok`, and `execute` made both legs and stopped extracting the spec
    leg, `unable to checkout working tree`. Under `git-config-count` it was
    this finding already."""
    env = protect_hfs_handed(tmp_path, handed)
    result = checked(hfs_plan(tmp_path), env)
    assert "REFUSED" not in result.stderr, result.stderr
    assert result.returncode == 1, result.stderr
    assert finding_lines(result) == [
        f"FINDING {PATH_GIT_REFUSES}: {one_refused(HFS_SAID)}"]


def test_with_no_setting_git_takes_that_path(tmp_path):
    """The control: with no `core.protectHFS`, git on Linux holds the path,
    and `check` finds nothing in it."""
    if not the_index_holds(tmp_path, HFS_PATH, {}):
        pytest.skip("this git refuses `.g` + U+200C + `it/x` with no "
                    "setting, as macOS's does by default")
    assert findings(hfs_plan(tmp_path)) == []


@pytest.mark.parametrize("handed", FROM_A_PARENT)
def test_execute_refuses_a_path_a_parent_gits_setting_refuses_before_any_leg(
        adopter, monkeypatch, tmp_path, handed):
    env = protect_hfs_handed(tmp_path, handed)
    plan = hfs_plan(tmp_path)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    refusal = refused_before_any_leg(adopter, monkeypatch, plan, tmp_path)
    assert refusal.code == PATH_GIT_REFUSES


#: A filter git must run, whose clean step fails, and the root's own
#: `.gitattributes`, which names it for itself.
FAILING = "w1136"
FAILING_FILTER = [(f"filter.{FAILING}.clean", "false"),
                  (f"filter.{FAILING}.smudge", "cat"),
                  (f"filter.{FAILING}.required", "true")]
FILTERED_ROOT = f"/.gitattributes filter={FAILING}\n".encode()


def filtered_root_plan(base: Path) -> Path:
    return planned(a_source(base, files={ROOT_ATTRIBUTES: FILTERED_ROOT}),
                   base, {})


@pytest.mark.parametrize("handed", FROM_A_PARENT)
def test_a_parent_gits_filter_is_asked_where_the_root_is_stored(tmp_path,
                                                                handed):
    """A failing clean filter, handed down by a parent git, that the root's
    `.gitattributes` names for itself: `_stored_as_written` takes the
    setting, as the split's `git add` does, and says the root is stored
    otherwise. Measured on bba168bd with git 2.43: under
    `git-config-parameters`, `check` said `plan ok`, and `execute` made
    both legs and stopped extracting the spec leg, `clean filter 'w1136'
    failed`. Under `git-config-count` it was this finding already."""
    result = checked(filtered_root_plan(tmp_path),
                     handed(tmp_path, FAILING_FILTER))
    assert "REFUSED" not in result.stderr, result.stderr
    assert result.returncode == 1, result.stderr
    assert codes(result) == [REENCODED_ATTRIBUTES], result.stderr


@pytest.mark.parametrize("handed", FROM_A_PARENT)
def test_execute_refuses_a_parent_gits_filter_before_any_leg(
        adopter, monkeypatch, tmp_path, handed):
    plan = filtered_root_plan(tmp_path)
    for name, value in handed(tmp_path, FAILING_FILTER).items():
        monkeypatch.setenv(name, value)
    refusal = refused_before_any_leg(adopter, monkeypatch, plan, tmp_path)
    assert refusal.code == REENCODED_ATTRIBUTES


def no_setting(_base: Path, _entries) -> dict:
    return {}


#: Where an `attr.tree` comes from: nowhere (the control), a global config,
#: and the two forms a parent git hands it in.
ATTR_TREE_HANDED = [pytest.param(no_setting, id="no-setting"), *EVERY_FORM]
#: `execute` needs `git filter-repo` before it gets far enough to verify.
NEEDS_FILTER_REPO = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `execute` refuses without it")


def empty_tree_plan(base: Path, handed) -> tuple[Path, dict]:
    """The plan for a source whose root says `* text eol=lf` over a CRLF
    file the plan keeps in the root, and `attr.tree` naming the empty tree
    in the form `handed` gives it. The control: in the source, the setting
    makes git read no `eol` for that file; where this git reads no
    `attr.tree`, the forms are skipped."""
    source = a_source(base, files={ROOT_ATTRIBUTES: TEXT_EOL_LF, NOTES: CRLF})
    env = handed(base, [("attr.tree", mktree(source, []))])
    read = subprocess.run(["git", "check-attr", "eol", "--", NOTES],
                          cwd=str(source), env={**os.environ, **env},
                          capture_output=True, text=True, check=True)
    if env and read.stdout.strip() == f"{NOTES}: eol: lf":
        pytest.skip("this git reads no `attr.tree`")
    assert read.stdout.strip() == f"{NOTES}: eol: " + (
        "unspecified" if env else "lf")
    return planned(source, base, {NOTES: ROOT}), env


@pytest.mark.parametrize("handed", ATTR_TREE_HANDED)
def test_a_parent_gits_attr_tree_is_read_in_the_rehearsal_as_the_split_reads_it(
        tmp_path, handed):
    """`attr.tree` naming the empty tree makes git read no rule, in the
    split's checkout and `git add` too, which take this process's whole
    environment: the CRLF file the plan keeps is stored as its blob there,
    and `execute` verifies (the next row). The rehearsal takes the setting
    in every form now, as it took a global config's already, and finds
    nothing; with no setting it finds the file. Measured on b8e63bcf with
    git 2.43, which left `attr.tree` out of both forms a parent hands it
    in: `check` said `plan-file-reencoded` under each, and `execute`
    refused a file its own git stores as its blob (r1169's SHOULD-1)."""
    plan, env = empty_tree_plan(tmp_path, handed)
    result = checked(plan, env)
    assert "REFUSED" not in result.stderr, result.stderr
    if env:
        assert result.returncode == 0, result.stderr
        assert "plan ok" in result.stdout
    else:
        assert result.returncode == 1, result.stderr
        assert codes(result) == [REENCODED_FILES], result.stderr
        assert KEPT_CRLF in finding_lines(result)[0]


@NEEDS_FILTER_REPO
@pytest.mark.parametrize("handed", ATTR_TREE_HANDED)
def test_execute_reads_a_parent_gits_attr_tree_as_check_does(tmp_path,
                                                             handed):
    """`execute`, run as a person runs it, under the same settings: where
    `check` says `plan ok`, its own git reads no rule either and it
    verifies the adoption; with no setting it refuses the file `check`
    finds, before any leg. On b8e63bcf it refused under each form a parent
    hands `attr.tree` in."""
    plan, env = empty_tree_plan(tmp_path, handed)
    remotes = tmp_path / "remotes"
    done = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                      "--local-remote-dir", str(remotes),
                      "--work-dir", str(tmp_path / "work"), env=env)
    if env:
        assert done.returncode == 0, done.stderr
        assert "adoption verified" in done.stdout, done.stdout
    else:
        assert done.returncode == 2, done.stderr
        assert f"REFUSED {REENCODED_FILES}: " in done.stderr, done.stderr
        assert not remotes.exists()


#: A root `.gitattributes` that names no filter and none of the source's
#: files, so that only a rule `attr.tree` names is read for the root's own.
NEUTRAL_ROOT = b"*.png binary\n"


def side_tree_handed(base: Path, handed) -> tuple[Path, dict]:
    """The plan for a source whose root keeps `NEUTRAL_ROOT`, and which
    holds, on a side branch, a tree whose `.gitattributes` names the
    failing filter for the root's own (`FILTERED_ROOT`); and
    `FAILING_FILTER`, with `attr.tree` naming that tree by its object id,
    in the form `handed` gives them. The control: in the source, git reads
    that filter for `.gitattributes`; where this git reads no `attr.tree`,
    the form is skipped."""
    source = a_source(base, files={ROOT_ATTRIBUTES: NEUTRAL_ROOT})
    rules = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                           cwd=str(source), input=FILTERED_ROOT,
                           capture_output=True, check=True
                           ).stdout.decode().strip()
    tree = mktree(source, [f"100644 blob {rules}\t{ROOT_ATTRIBUTES}"])
    side = git("commit-tree", tree, "-m", "Side", cwd=source).stdout.strip()
    git("update-ref", "refs/heads/side", side, cwd=source)
    env = handed(base, [*FAILING_FILTER, ("attr.tree", tree)])
    read = subprocess.run(["git", "check-attr", "filter", "--",
                           ROOT_ATTRIBUTES], cwd=str(source),
                          env={**os.environ, **env}, capture_output=True,
                          text=True, check=True)
    if read.stdout.strip() == f"{ROOT_ATTRIBUTES}: filter: unspecified":
        pytest.skip("this git reads no `attr.tree`")
    assert read.stdout.strip() == f"{ROOT_ATTRIBUTES}: filter: {FAILING}"
    return planned(source, base, {}), env


@pytest.mark.parametrize("handed", EVERY_FORM)
def test_a_parent_gits_attr_tree_is_read_where_the_root_is_stored(tmp_path,
                                                                  handed):
    """`attr.tree` naming a tree the source holds, whose `.gitattributes`
    names a failing required clean filter for the root's own: the split's
    clones hold that tree, and its `git add` of the root runs the filter.
    `_stored_as_written` takes the setting in every form and borrows the
    source's objects, so it reads that tree too, and says the root is
    stored otherwise, in git's words. Measured on b8e63bcf with git 2.43:
    under each form `check` said `plan ok`, and `execute` made both legs
    and stopped in the spec leg, `fatal: .gitattributes: clean filter
    'w1136' failed`, with nothing rolled back (r1169's SHOULD-1). The
    global config's was `plan ok` too: the throwaway held no such tree."""
    plan, env = side_tree_handed(tmp_path, handed)
    result = checked(plan, env)
    assert "REFUSED" not in result.stderr, result.stderr
    assert result.returncode == 1, result.stderr
    assert codes(result) == [REENCODED_ATTRIBUTES], result.stderr
    assert f"clean filter '{FAILING}' failed" in finding_lines(result)[0]


def test_the_failing_filter_alone_is_read_for_no_file(tmp_path):
    """The control: the same filter with no `attr.tree`, which no rule of
    the source names, is `plan ok`."""
    source = a_source(tmp_path, files={ROOT_ATTRIBUTES: NEUTRAL_ROOT})
    result = checked(planned(source, tmp_path, {}),
                     with_parameters(tmp_path, FAILING_FILTER))
    assert result.returncode == 0, result.stderr
    assert "plan ok" in result.stdout


@pytest.mark.parametrize("handed", EVERY_FORM)
def test_execute_refuses_a_parent_gits_attr_tree_filter_before_any_leg(
        adopter, monkeypatch, tmp_path, handed):
    plan, env = side_tree_handed(tmp_path, handed)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    refusal = refused_before_any_leg(adopter, monkeypatch, plan, tmp_path)
    assert refusal.code == REENCODED_ATTRIBUTES


#: The forms `core.hooksPath` and `core.fsmonitor` reach `check` in.
COUNTERS_HANDED = [pytest.param(with_global_config, id="global-config"),
                   *FROM_A_PARENT]


@pytest.mark.parametrize("handed", COUNTERS_HANDED)
def test_no_hook_or_fsmonitor_runs_where_the_rehearsal_asks(tmp_path,
                                                            handed):
    """The rehearsal and `_stored_as_written` take a parent git's settings
    now, and their own `-c core.hooksPath` and `core.fsmonitor=false` come
    after them: git takes a key's last value, so neither the counting
    hooks nor the counting fsmonitor run. The source keeps its own root
    `.gitattributes`, so both are asked. The control: the same settings
    run both for a `git add` in a repository of their own."""
    plan = planned(a_source(tmp_path, files={ROOT_ATTRIBUTES: b"*.md text\n"}),
                   tmp_path, {})
    hooks, hook_log = counting_hooks(tmp_path)
    program, fsmonitor_log = counting_fsmonitor(tmp_path)
    env = handed(tmp_path, [("core.hooksPath", hooks.as_posix()),
                            ("core.fsmonitor", program.as_posix())])
    result = checked(plan, env)
    assert result.returncode == 0, result.stderr
    assert (runs(hook_log), runs(fsmonitor_log)) == ([], [])
    repository = tmp_path / "ordinary"
    git("init", "-q", str(repository), cwd=tmp_path)
    (repository / "a").write_bytes(b"a\n")
    subprocess.run(["git", "add", "a"], cwd=str(repository), check=True,
                   env={**os.environ, **env})
    assert runs(hook_log) == ["post-index-change"]
    assert runs(fsmonitor_log) != []


def a_source_with_no_code(base: Path) -> Path:
    """A source holding a spec and no code, whose code leg `execute` seeds
    with no commit under `--allow-empty-leg code`."""
    path = base / "Thing"
    path.mkdir(parents=True)
    git("init", "-q", "-b", "main", ".", cwd=path)
    for name in ("README.md", "specs/001-feature/spec.md"):
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_bytes(b"# Thing\n")
    git("add", "-A", cwd=path)
    git("commit", "-qm", "Initial import", cwd=path)
    return path


def tree_of(source: Path, *flags: str) -> str:
    return git("rev-parse", *flags, "HEAD^{tree}", cwd=source).stdout.strip()


#: What `adopt-git-unasked` says of a `GIT_ATTR_SOURCE`, after its value.
ATTR_SOURCE_WHY = (
    ", and every git command the split runs would read attributes from the "
    "tree it names in place of the files it writes, in each repository it "
    "makes, and stop in any of them where it names no tree; the legs `git "
    "filter-repo` rewrites and a leg seeded with no commit are not made "
    "yet, so no throwaway repository can answer for them")
#: How it ends, in place of the words every other cause of
#: `adopt-git-unasked` ends with (`UNASKED_ENDS`), which send the person to
#: another `--work-dir` that cannot help (r1169's NIT-3).
ATTR_SOURCE_ENDS = (
    ". `execute` refuses it too, whatever it names, before it makes either "
    "leg. Unset `GIT_ATTR_SOURCE`, which a `git --attr-source` running this "
    "tool also sets, and run `check` again.")


def unasked_attr_source(work: Path, value: str) -> str:
    """`adopt-git-unasked` for `GIT_ATTR_SOURCE` set to `value` in `work`."""
    return (f"FINDING {UNASKED}: "
            + UNASKED_OPENS.format(os.path.realpath(work))
            + "`GIT_ATTR_SOURCE` is set in its environment, "
            + (f"to `{value}`" if value else "empty") + ATTR_SOURCE_WHY
            + ATTR_SOURCE_ENDS)


#: `(what GIT_ATTR_SOURCE names, from the source; whether the source holds
#: no code, its code leg seeded empty)`. Measured on bba168bd with git
#: 2.43, `check` said `plan ok` under each. `execute` made both legs and
#: stopped under the first four: at extracting the spec leg, at seeding the
#: code leg, and at pushing the spec leg. It took the next two to `adoption
#: verified`, and refusing them too is #1136's known limit. The last two
#: were rows of `test_no_tree_this_machine_names_steers_the_question` and
#: `..._steers_the_split_question`, which found the file the throwaway was
#: asked about while every throwaway left the variable out.
ATTR_SOURCES = [
    pytest.param(lambda _source: "bogus", False, id="bogus"),
    pytest.param(lambda _source: "", False, id="empty"),
    pytest.param(lambda _source: "HEAD", True,
                 id="head-over-a-code-leg-seeded-empty"),
    pytest.param(lambda source: tree_of(source, "--short=12"), True,
                 id="the-tree-abbreviated-over-a-code-leg-seeded-empty"),
    pytest.param(lambda _source: "HEAD", False, id="head"),
    pytest.param(tree_of, False, id="the-tree"),
    pytest.param(lambda source: mktree(source, []), False,
                 id="the-empty-tree"),
]


def attr_source_plan(base: Path, named, no_code: bool) -> tuple[Path, str]:
    """The plan, and the value `named` gives `GIT_ATTR_SOURCE`."""
    source = a_source_with_no_code(base) if no_code else a_source(base)
    return planned(source, base, {}), named(source)


@pytest.mark.parametrize(("named", "no_code"), ATTR_SOURCES)
def test_git_attr_source_is_one_finding_that_names_it(tmp_path, named,
                                                      no_code):
    """Whatever it names, `GIT_ATTR_SOURCE` is one `adopt-git-unasked` that
    names it, before any question, so nothing is made in the work
    directory."""
    plan, value = attr_source_plan(tmp_path, named, no_code)
    work = tmp_path / "work"
    result = checked(plan, {"GIT_ATTR_SOURCE": value}, "--work-dir",
                     str(work))
    assert "REFUSED" not in result.stderr, result.stderr
    assert result.returncode == 1, result.stderr
    assert finding_lines(result) == [unasked_attr_source(work, value)]
    assert list(work.iterdir()) == []


@pytest.mark.parametrize(("named", "no_code"), ATTR_SOURCES[:3])
def test_execute_refuses_git_attr_source_before_any_leg(
        adopter, monkeypatch, tmp_path, named, no_code):
    """On bba168bd each made both legs first (`ATTR_SOURCES`)."""
    plan, value = attr_source_plan(tmp_path, named, no_code)
    monkeypatch.setenv("GIT_ATTR_SOURCE", value)
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)
    remotes = tmp_path / "remotes"
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(Namespace(
            plan=str(plan), source=None, local_remote_dir=remotes,
            allow_empty_leg=["code"] if no_code else [], yes=True,
            work_dir=tmp_path / "work"))
    assert caught.value.code == UNASKED
    assert "`GIT_ATTR_SOURCE` is set in its environment" in \
        caught.value.detail
    assert caught.value.detail.endswith(ATTR_SOURCE_ENDS[2:])
    assert "no leg repository was created" in caught.value.remediation
    assert not remotes.exists()


def test_git_attr_source_is_refused_before_the_splits_own_clone_is_asked(
        adopter, monkeypatch, tmp_path):
    """r1169's NIT-1: under `GIT_ATTR_SOURCE`, `execute` refuses with
    `adopt-git-unasked` before `check`'s first question, the split's own
    clone, is asked, and nothing is made in the work directory. Asked
    first, that clone would answer and remove itself, as it takes no
    `GIT_ATTR_SOURCE` (`_inherited_env()`), so the finding alone does not
    say which came first."""
    plan = planned(a_source(tmp_path), tmp_path, {})
    asked = []
    monkeypatch.setattr(adopter, "_split_clone_asked", asked.append)
    monkeypatch.setenv("GIT_ATTR_SOURCE", "HEAD")
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)
    work, remotes = tmp_path / "work", tmp_path / "remotes"
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(Namespace(
            plan=str(plan), source=None, local_remote_dir=remotes,
            allow_empty_leg=[], yes=True, work_dir=work))
    assert caught.value.code == UNASKED
    assert asked == []
    assert list(work.iterdir()) == []
    assert not remotes.exists()


def test_the_checkout_questions_take_the_settings_and_no_attr_source(
        adopter, monkeypatch, tmp_path):
    """`_split_checkout_env()`: this process's environment, a parent git's
    settings in both forms as they stand among it, `attr.tree` too, as
    the split's checkout, `git rm` and `git add` take them; and none of
    the variables that name another repository, its objects, an index or
    a work tree, nor `GIT_ATTR_SOURCE`, which is refused before any
    question. With no `GIT_CONFIG_PARAMETERS` there is none."""
    for name, value in ANOTHER_REPOSITORY.items():
        monkeypatch.setenv(name, str(tmp_path / value))
    parameters = "'attr.tree'='HEAD' 'core.protectHFS'='true'"
    monkeypatch.setenv(PARAMETERS, parameters)
    scope = appended_to_command_scope(
        os.environ, [("attr.tree", "HEAD"), ("test.heldone", "one")])
    for name, value in scope.items():
        monkeypatch.setenv(name, value)
    env = adopter._split_checkout_env()
    assert env[PARAMETERS] == parameters
    assert {name: env.get(name) for name in scope} == scope
    assert env == {name: value for name, value in os.environ.items()
                   if name not in ANOTHER_REPOSITORY}
    monkeypatch.delenv(PARAMETERS)
    assert PARAMETERS not in adopter._split_checkout_env()
