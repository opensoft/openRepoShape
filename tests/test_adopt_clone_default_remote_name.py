# SPDX-License-Identifier: Apache-2.0
"""`adopt-project.py` under a `clone.defaultRemoteName` of the person's own
(#1261): each clone it makes names its remote `origin`.

`git clone` names the remote it makes after `clone.defaultRemoteName`, and
`execute` addressed each of its clones as `origin`. With `upstream` in the
global git config, `plan` and `check` exited 0, and `execute
--local-remote-dir` ended in `REFUSED mounting the legs`, exit 2, after both
legs were made and pushed: `git remote set-url origin <leg url>`, in the
clone `git submodule add` had made, said "error: No such remote 'origin'"
(measured on main `be21751c`, git 2.43, git-filter-repo 2.47.0). Every clone
`execute` makes now carries `-c clone.defaultRemoteName=origin`, which
reaches the clone `git submodule add` makes too, and `gh repo clone` is
handed `--origin origin` after its `--`.

EACH ROW GIVES THE SETTING TO ITS OWN CHILD ONLY: a `GIT_CONFIG_GLOBAL` of
its own, passed in that child's environment. The file is the session's
(`no_auto_maintenance`: the person's own config included, maintenance off)
and then the setting, so every other row runs under the session's config as
it did.

A source made twice is two histories (its commits carry the time they were
made), so the run without the setting adopts a copy of the very source the
run with it adopts: `test_adopt_e2e.py`'s module adoption has a source of
its own, which is why these rows are not there.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ADOPT, git, make_source_repo, resolve, run_script

PROJECT = "Northwind"
ORG = "testorg"
#: `plan`'s arguments after `--source <it>`, as `write_plan` gives them.
PLANNED = ("--project", PROJECT, "--org", ORG, "--elected-by", "Test Human",
           "--elected-on", "2026-09-02")
ANSWERS = (("examples/", "spec"), (".claude/", "root"),
           ("release.yaml", "root"))
LEGS = ("spec", "code")
#: The person's own setting, as #1261's probe held it.
UPSTREAM = b"[clone]\n\tdefaultRemoteName = upstream\n"
#: A name git refuses for a remote: `fatal: 'a..b' is not a valid remote
#: name`, from any clone that reads it.
REFUSED_NAME = b"[clone]\n\tdefaultRemoteName = a..b\n"
VERIFIED = "adoption verified"

#: `execute` REQUIRES `git filter-repo`; CI installs it.
needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")


def global_config(session: Path, directory: Path, setting: bytes) -> dict:
    """The environment that gives one child `setting`: a `GIT_CONFIG_GLOBAL`
    holding the session's file (`session`) and then `setting`."""
    directory.mkdir(parents=True, exist_ok=True)
    config = directory / "global.gitconfig"
    config.write_bytes(session.read_bytes() + setting)
    return {"GIT_CONFIG_GLOBAL": str(config)}


def remotes(repository: Path) -> list[str] | None:
    """`git remote` in `repository`, or None where the run made none."""
    if not (repository / ".git").exists():
        return None
    return git("remote", cwd=repository).stdout.split()


def adopted(base: Path, golden: Path, env: dict) -> dict:
    """`plan`, `check` and `execute --local-remote-dir` of a copy of `golden`
    in `base`, each with `env` in its environment, and what each said."""
    source = base / "Thing"
    shutil.copytree(golden, source, symlinks=True)
    plan = base / "adoption-plan.yaml"
    planned = run_script(ADOPT, "plan", "--source", str(source), *PLANNED,
                         "--out", str(plan), env=env)
    assert planned.returncode == 0, planned.stdout + planned.stderr
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    checked = run_script(ADOPT, "check", "--plan", str(plan), env=env)
    executed = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                          "--local-remote-dir", str(base / "remotes"),
                          "--work-dir", str(base / "work"), env=env,
                          merge_stderr=True)
    return {"base": base, "checked": checked, "executed": executed}


def leg_dump(remotes_dir: Path) -> list[str]:
    """Every ref and every object of both legs pushed into `remotes_dir`,
    with HEAD: an object's id is the hash of its bytes, so two equal dumps
    are two byte-identical legs."""
    lines: list[str] = []
    for leg in LEGS:
        bare = remotes_dir / f"{PROJECT}-{leg}.git"
        lines += [f"== {leg}",
                  git("symbolic-ref", "HEAD", cwd=bare).stdout.strip()]
        lines += git("for-each-ref",
                     "--format=%(objectname) %(objecttype) %(refname)",
                     cwd=bare).stdout.splitlines()
        lines += sorted(git("cat-file", "--batch-all-objects",
                            "--batch-check", cwd=bare).stdout.splitlines())
    return lines


def clone_remotes(work: Path) -> dict:
    """The remotes of each repository `execute` made in `work`: the
    assembly, each leg's mount in it, and each leg's own clone."""
    assembly = work / PROJECT
    return {"assembly": remotes(assembly),
            **{f"{leg} mount": remotes(assembly / leg) for leg in LEGS},
            **{f"{leg} clone": remotes(work / f"{PROJECT}-{leg}")
               for leg in LEGS}}


@pytest.fixture(scope="module")
def adoptions(tmp_path_factory, no_auto_maintenance) -> dict:
    """One source, adopted twice: `without` under the session's config,
    and `upstream` with `clone.defaultRemoteName = upstream` added."""
    base = tmp_path_factory.mktemp("default-remote-name")
    golden = make_source_repo(base / "golden" / "Thing")
    return {
        "without": adopted(base / "without", golden, {}),
        "upstream": adopted(base / "upstream", golden, global_config(
            no_auto_maintenance, base / "config", UPSTREAM))}


def test_the_premise_a_plain_clone_under_the_setting_names_upstream(
        no_auto_maintenance, tmp_path):
    """Asked of git, not assumed: under the rows' global config a plain
    `git clone` names its remote `upstream`, and under the session's it
    names it `origin`. If git stops reading the setting, this fails rather
    than the rows below passing over nothing."""
    source = make_source_repo(tmp_path / "Thing", tree={"a.txt": "a\n"},
                              edits=())
    env = {**os.environ, **global_config(no_auto_maintenance,
                                         tmp_path / "config", UPSTREAM)}
    made = subprocess.run(["git", "clone", "-q", str(source),
                           str(tmp_path / "set")], env=env,
                          capture_output=True, text=True, check=False)
    assert made.returncode == 0, made.stderr
    git("clone", "-q", str(source), str(tmp_path / "unset"), cwd=tmp_path)
    assert remotes(tmp_path / "set") == ["upstream"]
    assert remotes(tmp_path / "unset") == ["origin"]


@needs_filter_repo
def test_execute_under_the_setting_exits_0_and_says_adoption_verified(
        adoptions):
    """On main `check` said `plan ok` and `execute` exited 2, `REFUSED
    mounting the legs`, with both legs pushed."""
    checked = adoptions["upstream"]["checked"]
    assert checked.returncode == 0, checked.stdout + checked.stderr
    executed = adoptions["upstream"]["executed"]
    assert executed.returncode == 0, executed.stdout[-3000:]
    assert VERIFIED in executed.stdout, executed.stdout[-3000:]
    assert adoptions["without"]["executed"].returncode == 0, \
        adoptions["without"]["executed"].stdout[-3000:]


@needs_filter_repo
def test_the_legs_are_the_bytes_a_run_without_the_setting_pushes(adoptions):
    """Every ref and object of both legs, HEAD too. (On main the legs were
    these bytes as well: both were pushed before the mount refused.)"""
    without, upstream = (leg_dump(adoptions[run]["base"] / "remotes")
                         for run in ("without", "upstream"))
    assert len(without) > 2 * len(LEGS), without
    assert upstream == without


@needs_filter_repo
def test_each_clone_execute_makes_has_the_remotes_it_has_without_it(
        adoptions):
    """The assembly and each mount name their remote `origin`, which
    `_mount_the_legs` sets the leg's url on, and each leg's own clone has
    what it has without the setting (`git filter-repo` removes `origin`
    alone). On main each named it `upstream`, and the code leg's mount was
    never made."""
    without, upstream = (clone_remotes(adoptions[run]["base"] / "work")
                         for run in ("without", "upstream"))
    assert without["assembly"] == ["origin"], without
    assert all(without[f"{leg} mount"] == ["origin"] for leg in LEGS), \
        without
    assert upstream == without


def test_check_passes_under_a_default_remote_name_git_refuses(
        no_auto_maintenance, tmp_path):
    """`check` asks git for `_extract_leg`'s clone of the source in a
    throwaway (`_split_clone_asked`), with the settings that clone is
    given. Under `clone.defaultRemoteName = a..b`, a name git refuses,
    `check` said `adopt-git-unasked` on main, `fatal: 'a..b' is not a valid
    remote name`, as `execute`'s clone then did; neither clone reads the
    setting now, and `check` says `plan ok`."""
    env = global_config(no_auto_maintenance, tmp_path / "config",
                        REFUSED_NAME)
    source = make_source_repo(tmp_path / "Thing")
    plan = tmp_path / "adoption-plan.yaml"
    planned = run_script(ADOPT, "plan", "--source", str(source), *PLANNED,
                         "--out", str(plan), env=env)
    assert planned.returncode == 0, planned.stdout + planned.stderr
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    checked = run_script(ADOPT, "check", "--plan", str(plan), env=env)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert "adopt-git-unasked" not in checked.stdout + checked.stderr
    assert checked.stdout.rstrip().endswith("plan ok"), checked.stdout


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="the `gh` stub is a `#!/bin/sh` script, which Windows runs not")
def test_gh_repo_clone_is_handed_origin_for_the_remotes_name(tmp_path):
    """The `cloned: true` path: `gh repo clone <org/repo> <directory> --
    <git clone flags>`, as `Source.clone` runs it, is handed `--origin
    origin` beside `--quiet`, so the clone `_default_branch` and
    `_branches_of` read as `origin`'s names its remote so. A stub `gh`,
    first on PATH, writes each argument on a line of its own and exits 97:
    `plan` refuses `source-unclonable`, and no `gh` of this machine runs."""
    stub = tmp_path / "stub"
    stub.mkdir()
    log = tmp_path / "gh.log"
    gh = stub / "gh"
    gh.write_text("#!/bin/sh\nfor arg in \"$@\"; do printf '%s\\n' "
                  "\"$arg\"; done >> \"$GH_ARGV_LOG\"\nexit 97\n",
                  encoding="utf-8")
    gh.chmod(0o755)
    work = tmp_path / "work"
    result = run_script(
        ADOPT, "plan", "--source", f"{ORG}/Thing", "--project", "Thing",
        "--org", ORG, "--elected-by", "Test Human", "--elected-on",
        "2026-09-02", "--out", str(tmp_path / "plan.yaml"), "--work-dir",
        str(work),
        env={"PATH": f"{stub}{os.pathsep}{os.environ.get('PATH', '')}",
             "GH_ARGV_LOG": str(log)})
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith("REFUSED source-unclonable: "), \
        result.stderr
    assert log.read_text(encoding="utf-8").splitlines() == [
        "repo", "clone", f"{ORG}/Thing",
        str(Path(os.path.realpath(work)) / "source-readonly" / "Thing"),
        "--", "--quiet", "--origin", "origin"]
