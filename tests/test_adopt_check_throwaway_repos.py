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
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import tempfile
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import (ADOPT, appended_to_command_scope, findings, git,
                      planned, refused_before_any_leg, run_script)
from test_adopt_nested_attributes import (KEEP_GITHUB, ROOT, ROOT_ATTRIBUTES,
                                          SOURCE, YML_CRLF, adoption_plan,
                                          committed_raw, github)
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
#: The prefixes of the throwaway repositories of #530 and #654.
THROWAWAY_PREFIXES = ("openreposhape-attributes-",
                      "openreposhape-reencoded-")
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

def test_each_throwaway_repository_is_made_in_the_work_directory(
        adopter, monkeypatch, tmp_path):
    """The source keeps a nested `.gitattributes` above a pinned copy and
    its own root one, so all three questions are asked: each throwaway
    repository is made in the work directory the source was opened in, not
    in `TMPDIR`, and none is left there."""
    plan = adopter.Plan.load(adoption_plan(tmp_path, github(YML_CRLF),
                                           KEEP_GITHUB))
    work = tmp_path / "work"
    work.mkdir()
    opened = plan.open_source(None, work)
    made = []

    def mkdtemp(suffix=None, prefix=None, dir=None):
        path = tempfile.mkdtemp(suffix=suffix, prefix=prefix, dir=dir)
        made.append((prefix, Path(path).parent.resolve()))
        return path

    monkeypatch.setattr(adopter, "tempfile", SimpleNamespace(
        mkdtemp=mkdtemp, gettempdir=tempfile.gettempdir,
        TemporaryDirectory=tempfile.TemporaryDirectory))
    found, _, _ = adopter._entry_findings(plan, opened)
    assert any(line.startswith("FINDING plan-nested-attributes: ")
               for line in found), found
    asked = [(prefix, parent) for prefix, parent in made
             if prefix in THROWAWAY_PREFIXES]
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


@pytest.mark.parametrize("configured", [
    pytest.param(in_the_global_config, id="global-config"),
    pytest.param(in_the_command_scope, id="git-config-count")])
def test_no_hook_of_this_machines_runs_in_a_throwaway_repository(
        tmp_path, configured):
    """The source keeps its own root `.gitattributes`, so #619's question
    of `git add` is asked as well as the rehearsal's: on c7a3ff16 the
    global config's hook ran 12 times in this `check`."""
    plan = planned(a_source(tmp_path, files={ROOT_ATTRIBUTES: b"*.md text\n"}),
                   tmp_path, {})
    hooks, log = counting_hooks(tmp_path)
    result = checked(plan, configured(tmp_path, hooks))
    assert result.returncode == 0, result.stderr
    assert runs(log) == []


@pytest.mark.parametrize("configured", [
    pytest.param(in_the_global_config, id="global-config"),
    pytest.param(in_the_command_scope, id="git-config-count")])
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
    """`GIT_DEFAULT_HASH=bogus` makes the probe's `git init` fail, and only
    it: each throwaway repository names its format. `check` prints the
    finding the probe stands for, as it does with no such variable, and
    says why in a NOTE."""
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


def test_a_repository_git_cannot_make_is_one_finding_that_says_why(
        tmp_path):
    plan = planned(a_source(tmp_path), tmp_path, {})
    work = tmp_path / "work"
    result = checked(plan, bad_default_branch(tmp_path), "--work-dir",
                     str(work))
    assert "REFUSED" not in result.stderr, result.stderr
    assert result.returncode == 1, result.stderr
    lines = finding_lines(result)
    assert len(lines) == 1, result.stderr
    assert lines[0].startswith(f"FINDING {UNASKED}: " + UNASKED_OPENS.format(
        os.path.realpath(work)) + "`git init` there exited 128: "), lines[0]
    assert "init.defaultBranch" in lines[0]
    assert lines[0].endswith(UNASKED_ENDS), lines[0]
    assert list(work.iterdir()) == []


def test_the_splits_own_clone_refuses_that_setting_too(tmp_path):
    """The control, and why it is a finding and not a NOTE: the split's
    clone of the source fails under the same config."""
    source = a_source(tmp_path)
    cloned = subprocess.run(
        ["git", "clone", "-q", str(source), str(tmp_path / "clone")],
        capture_output=True, check=False,
        env={**os.environ, **bad_default_branch(tmp_path)})
    assert cloned.returncode != 0, cloned.stderr


def test_execute_refuses_it_before_any_leg_exists(adopter, monkeypatch,
                                                 tmp_path):
    plan = planned(a_source(tmp_path), tmp_path, {})
    for name, value in bad_default_branch(tmp_path).items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)
    remotes = tmp_path / "remotes"
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(Namespace(
            plan=str(plan), source=None, local_remote_dir=remotes,
            allow_empty_leg=[], yes=True, work_dir=tmp_path / "work"))
    assert caught.value.code == UNASKED
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
               "source's paths and files there; run `check` again with a "
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
