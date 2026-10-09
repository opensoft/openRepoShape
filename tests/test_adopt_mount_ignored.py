# SPDX-License-Identifier: Apache-2.0
"""A source `.gitignore` hiding a MOUNT PATH must not stop the mount (#174).

`_mount_the_legs` ran `git submodule add` without `--force`, so a source whose
`.gitignore` is `*` + `!.gitignore`, or names `spec` or `code`, was refused at
the mount -- "The following paths are ignored by one of your .gitignore
files" -- AFTER both leg repositories had been created and pushed, although
`check` had said `plan ok`; a corrected re-run then met `leg-remote-exists`.
The mount now passes `--force`, git's documented way past an ignore rule, as
#162 already adds the fresh `.gitmodules` with `-f`: such a source is one to
adopt, not one to refuse.

The mount tests call `_mount_the_legs` on hand-made repositories, so they need
no `git filter-repo` and run on the Windows job, which installs none; the
end-to-end tests need it. All repositories and remotes are local fixtures; no
network is used.
"""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import (ADOPT, DEFAULT_EDITS, FILE_PROTOCOL, git,
                      make_source_repo, resolve, run_script, write_plan)

#: What the end-to-end tests need and the mount tests do not. Spelled here
#: rather than imported from another test module, so that the files do not
#: depend on each other.
needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

SPEC, CODE = "spec", "code"
ROLES = (SPEC, CODE)
PROJECT = "Northwind"
BRANCH = "adopt/three-repo-shape"
GITMODULES = ".gitmodules"
#: The mode `git ls-files -s` and `git ls-tree` report for a gitlink.
GITLINK = "160000"
#: What the assembly root registers once both legs are mounted.
LEG_REGISTRATIONS = ["submodule.code.path code", "submodule.spec.path spec"]
#: The catch-all `.gitignore` the defect was found with: all but itself.
IGNORE_ALL = "*\n!.gitignore\n"
#: The mount tests move nothing, so the mount is all that runs.
NOTHING_MOVED = {leg: [] for leg in (*ROLES, "drop")}
#: The three questions `plan` asks about `SYNTHETIC_TREE`, answered.
ANSWERS = (("examples/", SPEC), (".claude/", "root"),
           ("release.yaml", "root"))

#: `(the source's .gitignore, the mount paths it hides, an ignored file that
#: is not a mount)`. `code/` is the subtle rule: it names a DIRECTORY, so
#: git's own check of the path before it clones the leg passes, and the
#: refusal comes only once the clone has made `code` one. The ignored file is
#: dropped into the assembly, to show the force reaches the mount and nothing
#: else.
HIDING_RULES = [
    pytest.param(IGNORE_ALL, ROLES, ".env", id="all-but-itself"),
    pytest.param("spec\n", (SPEC,), "docs/spec", id="the-spec-mount"),
    pytest.param("code/\n", (CODE,), "src/code/generated.py",
                 id="the-code-mount-as-a-directory"),
]


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_mount_ignored", ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ignoring_source(path: Path, rule: str) -> Path:
    """`make_source_repo`'s source, whose LAST commit makes `rule` its
    `.gitignore`: last, because each commit there is a `git add -A`, which a
    catch-all rule would have kept every other file out of."""
    return make_source_repo(path, edits=DEFAULT_EDITS + (
        (".gitignore", rule, "Ignore what the project does not track"),))


def is_ignored(repo: Path, path: str) -> bool:
    return git("check-ignore", "--no-index", path, cwd=repo,
               check=False).returncode == 0


def hidden_mounts(source: Path) -> tuple:
    """The mount paths the source's rules hide, each asked about as the
    directory it is once a leg is cloned there."""
    return tuple(role for role in ROLES if is_ignored(source, f"{role}/"))


def registrations(repo: Path, *where: str) -> list[str]:
    """Every `submodule.<name>.path <path>` line of a `.gitmodules`: the one
    on the disk, or `--blob <rev>:.gitmodules` for one in a commit."""
    return sorted(git("config", *(where or ("-f", GITMODULES)),
                      "--get-regexp", r"^submodule\..*\.path$", cwd=repo)
                  .stdout.splitlines())


@pytest.mark.parametrize(("rule", "hidden", "stray"), HIDING_RULES)
def test_both_legs_mount_where_the_sources_gitignore_hides_the_path(
        adopter, tmp_path, rule, hidden, stray):
    """Each leg is a gitlink at its own commit, registered at its path with
    its canonical remote, however the rule hides the path; the only paths
    staged are the two mounts and their `.gitmodules`. Without `--force`
    the first hidden mount raised, and in `execute` that was after both
    pushes."""
    source = ignoring_source(tmp_path / "Thing", rule)
    assert hidden_mounts(source) == hidden, "the rule no longer hides a mount"
    assembly = tmp_path / PROJECT
    git("clone", "-q", str(source), str(assembly), cwd=tmp_path)
    (assembly / stray).parent.mkdir(parents=True, exist_ok=True)
    (assembly / stray).write_text("ignored by the source\n")
    assert is_ignored(assembly, stray)
    work = tmp_path / "work"
    names = {role: f"{PROJECT}-{role}" for role in ROLES}
    for role in ROLES:
        make_source_repo(work / names[role], tree={"file.txt": role}, edits=())
    urls = {role: str(tmp_path / "remotes" / f"{names[role]}.git")
            for role in ROLES}

    adopter._mount_the_legs(assembly, work, names, urls, NOTHING_MOVED, *ROLES)

    for role in ROLES:
        head = git("rev-parse", "HEAD", cwd=work / names[role]).stdout.strip()
        assert git("ls-files", "-s", "--", role, cwd=assembly).stdout \
            == f"{GITLINK} {head} 0\t{role}\n"
        url = git("config", "-f", GITMODULES, "--get",
                  f"submodule.{role}.url", cwd=assembly).stdout.strip()
        # A Path comparison: Git may write forward slashes, Windows not.
        assert Path(url) == Path(urls[role])
    assert registrations(assembly) == LEG_REGISTRATIONS
    staged = git("diff", "--cached", "--name-status", cwd=assembly).stdout
    assert sorted(staged.splitlines()) == sorted(
        [f"A\t{GITMODULES}", *(f"A\t{role}" for role in ROLES)])


# ---------------------------------------------------------------------------
# End to end, through `execute`
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def adopted(tmp_path_factory) -> SimpleNamespace:
    """One real adoption of a source whose `.gitignore` is `*` +
    `!.gitignore`. `check` says `plan ok` for it, as it always did: #174
    adopts this source rather than refusing it."""
    base = tmp_path_factory.mktemp("ignore-all")
    source = ignoring_source(base / "Thing", IGNORE_ALL)
    assert hidden_mounts(source) == ROLES
    plan = base / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert "plan ok" in checked.stdout
    remotes = base / "remotes"
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(base / "work"))
    return SimpleNamespace(source=source, remotes=remotes, result=result)


@needs_filter_repo
def test_execute_mounts_both_legs_past_a_gitignore_that_hides_them(adopted):
    """It used to exit 2 at the mount with both leg remotes already pushed.
    The split commit now holds each mount as a gitlink at the commit pushed
    to that leg, registered at its path."""
    result = adopted.result
    assert result.returncode == 0, result.stderr + result.stdout
    assert "adoption verified" in result.stdout
    for role in ROLES:
        pushed = git("rev-parse", "HEAD",
                     cwd=adopted.remotes / f"{PROJECT}-{role}.git") \
            .stdout.strip()
        assert git("ls-tree", BRANCH, "--", role, cwd=adopted.source).stdout \
            == f"{GITLINK} commit {pushed}\t{role}\n"
    assert registrations(adopted.source, "--blob",
                         f"{BRANCH}:{GITMODULES}") == LEG_REGISTRATIONS


@needs_filter_repo
def test_the_assembly_whose_gitignore_hides_its_mounts_bootstraps(adopted,
                                                                  tmp_path):
    """With #167's forced staging of the shape's own files, nothing else
    stands between this source and a working assembly."""
    assert adopted.result.returncode == 0, adopted.result.stderr
    clone = tmp_path / PROJECT
    git(*FILE_PROTOCOL, "clone", "-q", "--recurse-submodules", "-b", BRANCH,
        str(adopted.source), str(clone), cwd=tmp_path)
    bootstrapped = run_script(clone / "scripts" / "bootstrap.py", cwd=clone)
    output = bootstrapped.stderr + bootstrapped.stdout
    assert bootstrapped.returncode == 0, output
