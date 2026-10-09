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

`--force` also turns off two of git's own refusals, so the mount makes them
itself first (`_refuse_an_unmountable_path`): a path the index already holds,
which `--force` lets through when it is a gitlink and then REUSES the
repository there (`spec_path` equal to `code_path` verified an assembly that
mounts the spec leg only); and git's `add --dry-run` before the clone, which
refuses a path beyond a symlink, and without which the leg was cloned through
a root-kept symlink, outside the work directory. Those tests are here too.

The mount tests call `_mount_the_legs` on hand-made repositories, so they need
no `git filter-repo` and run on the Windows job, which installs none -- except
the one that makes a symlink on the DISK, which skips there. The end-to-end
tests need `git filter-repo`. All repositories and remotes are local fixtures;
no network is used.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
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

#: What a test with a symlink ON THE DISK needs: Git for Windows checks a
#: tracked symlink out as a plain file unless `core.symlinks` is on, and a
#: runner may make one only in Developer Mode or elevated. The defect is a
#: POSIX layout, and the POSIX legs of CI run it.
needs_disk_symlinks = pytest.mark.skipif(
    sys.platform == "win32",
    reason="a tracked symlink is a plain file in a Windows checkout")

SPEC, CODE = "spec", "code"
ROLES = (SPEC, CODE)
PROJECT = "Northwind"
#: The source's directory, and the remotes' beside it.
SOURCE, REMOTES = "Thing", "remotes"
ROOT = "root"
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
ANSWERS = (("examples/", SPEC), (".claude/", ROOT), ("release.yaml", ROOT))
#: The two refusals the mount makes before `git submodule add --force`.
OCCUPIED = "adopt-mount-occupied"
UNADDABLE = "adopt-mount-unaddable"
#: A root-kept directory symlink, and a mount path through it.
LINK = "legs"
THROUGH_LINK = f"{LINK}/{SPEC}"

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


def commit_all(repo: Path, message: str) -> None:
    git("-c", "user.name=Source Human", "-c",
        "user.email=source@invalid.example", "commit", "-qm", message,
        cwd=repo)


def linked_source(path: Path, outside: Path) -> Path:
    """`make_source_repo`'s source with one more commit: `legs`, a symlink
    to `outside`, an absolute directory beyond every repository here."""
    source = make_source_repo(path)
    outside.mkdir()
    try:
        os.symlink(str(outside), source / LINK)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"this platform cannot create a symlink here: {exc}")
    git("add", LINK, cwd=source)
    commit_all(source, "Link the legs directory")
    return source


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


def head(repo: Path) -> str:
    return git("rev-parse", "HEAD", cwd=repo).stdout.strip()


def assembly_of(source: Path, tmp_path: Path) -> Path:
    """A plain clone of `source`, as `_commit_the_split` makes the assembly."""
    assembly = tmp_path / PROJECT
    git("clone", "-q", str(source), str(assembly), cwd=tmp_path)
    return assembly


def legs_to_mount(tmp_path: Path) -> SimpleNamespace:
    """The two legs in a work directory, as `_build_the_legs` leaves them,
    with the canonical URLs `_mount_the_legs` records."""
    work = tmp_path / "work"
    names = {role: f"{PROJECT}-{role}" for role in ROLES}
    for role in ROLES:
        make_source_repo(work / names[role], tree={"file.txt": role}, edits=())
    urls = {role: str(tmp_path / REMOTES / f"{names[role]}.git")
            for role in ROLES}
    return SimpleNamespace(work=work, names=names, urls=urls)


def mount(adopter, assembly: Path, legs: SimpleNamespace, spec_path: str,
          code_path: str) -> None:
    adopter._mount_the_legs(assembly, legs.work, legs.names, legs.urls,
                            NOTHING_MOVED, spec_path, code_path)


def mount_refused(adopter, assembly: Path, legs: SimpleNamespace,
                  spec_path: str, code_path: str):
    """The `Refusal` the mount raises. A `CommandFailed` instead is git
    refusing in its own words, after the guard let the path through."""
    with pytest.raises(adopter.Refusal) as caught:
        mount(adopter, assembly, legs, spec_path, code_path)
    return caught.value


@pytest.mark.parametrize(("rule", "hidden", "stray"), HIDING_RULES)
def test_both_legs_mount_where_the_sources_gitignore_hides_the_path(
        adopter, tmp_path, rule, hidden, stray):
    """Each leg is a gitlink at its own commit, registered at its path with
    its canonical remote, however the rule hides the path; the only paths
    staged are the two mounts and their `.gitmodules`. Without `--force`
    the first hidden mount raised, and in `execute` that was after both
    pushes."""
    source = ignoring_source(tmp_path / SOURCE, rule)
    assert hidden_mounts(source) == hidden, "the rule no longer hides a mount"
    assembly = assembly_of(source, tmp_path)
    (assembly / stray).parent.mkdir(parents=True, exist_ok=True)
    (assembly / stray).write_text("ignored by the source\n")
    assert is_ignored(assembly, stray)
    legs = legs_to_mount(tmp_path)

    mount(adopter, assembly, legs, *ROLES)

    for role in ROLES:
        assert git("ls-files", "-s", "--", role, cwd=assembly).stdout \
            == f"{GITLINK} {head(legs.work / legs.names[role])} 0\t{role}\n"
        url = git("config", "-f", GITMODULES, "--get",
                  f"submodule.{role}.url", cwd=assembly).stdout.strip()
        # A Path comparison: Git may write forward slashes, Windows not.
        assert Path(url) == Path(legs.urls[role])
    assert registrations(assembly) == LEG_REGISTRATIONS
    staged = git("diff", "--cached", "--name-status", cwd=assembly).stdout
    assert sorted(staged.splitlines()) == sorted(
        [f"A\t{GITMODULES}", *(f"A\t{role}" for role in ROLES)])


# ---------------------------------------------------------------------------
# What `--force` would let through, refused before the add
# ---------------------------------------------------------------------------


def test_a_second_mount_at_the_first_ones_path_is_refused(adopter, tmp_path):
    """`spec_path` equal to `code_path`. Past the gitlink the spec leg's mount
    left there, `--force` reused the spec leg's checkout as the code leg's
    mount, and `execute` said `adoption verified` over an assembly mounting
    the spec leg only. The refusal names what holds the path."""
    assembly = assembly_of(make_source_repo(tmp_path / SOURCE), tmp_path)
    legs = legs_to_mount(tmp_path)

    refusal = mount_refused(adopter, assembly, legs, CODE, CODE)

    assert refusal.code == OCCUPIED
    spec_mount = f"{GITLINK} {head(legs.work / legs.names[SPEC])} 0\t{CODE}"
    assert f"mount path {CODE}, with a submodule: `{spec_mount}`" \
        in refusal.detail
    assert git("ls-files", "-s", "--", CODE, cwd=assembly).stdout \
        == spec_mount + "\n"


def test_a_mount_path_a_kept_submodule_holds_is_refused(adopter, tmp_path):
    """The source's own submodule at `spec`, kept in the root: the index
    holds a gitlink at the mount path. The refusal names it, rather than
    leaving the answer to whatever `--force` makes of a gitlink there."""
    source = make_source_repo(tmp_path / SOURCE)
    dependency = make_source_repo(tmp_path / "dependency",
                                  tree={"value.txt": "1\n"}, edits=())
    git(*FILE_PROTOCOL, "submodule", "add", "-q", str(dependency), SPEC,
        cwd=source)
    commit_all(source, "Depend on the dependency, at spec")
    assembly = assembly_of(source, tmp_path)

    refusal = mount_refused(adopter, assembly, legs_to_mount(tmp_path),
                            *ROLES)

    assert refusal.code == OCCUPIED
    assert f"with a submodule: `{GITLINK} {head(dependency)} 0\t{SPEC}`" \
        in refusal.detail


def test_a_case_only_twin_is_refused_where_the_disk_ignores_case(adopter,
                                                                 tmp_path):
    """On a disk that ignores case, `Spec` holds `spec`, and `git clone`
    records that disk as `core.ignorecase`. It is set by hand here, on a disk
    that does not ignore case, so this pins the INDEX question only: asked
    with `--icase-pathspecs`, it finds the `Spec` mount that `ls-files`
    alone matches case-sensitively and misses."""
    assembly = assembly_of(make_source_repo(tmp_path / SOURCE), tmp_path)
    git("config", "core.ignorecase", "true", cwd=assembly)
    legs = legs_to_mount(tmp_path)

    refusal = mount_refused(adopter, assembly, legs, "Spec", SPEC)

    assert refusal.code == OCCUPIED
    spec_leg = head(legs.work / legs.names[SPEC])
    assert f"mount path {SPEC}, with a submodule: `{GITLINK} {spec_leg} " \
        "0\tSpec`" in refusal.detail


@needs_disk_symlinks
def test_a_mount_path_beyond_a_kept_symlink_is_refused_before_the_clone(
        adopter, tmp_path):
    """`legs -> <a directory outside>`, kept in the root, and `spec_path:
    legs/spec`. `--force` skips git's own dry run of the path, so the leg was
    cloned THROUGH the link, outside the work directory, before git refused.
    The dry run is made first now, and nothing is written outside."""
    outside = tmp_path / "outside"
    assembly = assembly_of(linked_source(tmp_path / SOURCE, outside),
                           tmp_path)

    refusal = mount_refused(adopter, assembly, legs_to_mount(tmp_path),
                            THROUGH_LINK, CODE)

    assert refusal.code == UNADDABLE
    assert f"mount path {THROUGH_LINK}: " in refusal.detail
    assert "beyond a symbolic link" in refusal.detail
    assert list(outside.iterdir()) == []


def test_a_mount_path_inside_the_other_legs_mount_is_refused(adopter,
                                                             tmp_path):
    """The code leg inside the spec leg's mount: the same dry run refuses a
    path inside a submodule, before the code leg is cloned into the spec
    leg's checkout."""
    assembly = assembly_of(make_source_repo(tmp_path / SOURCE), tmp_path)
    inside = f"{SPEC}/{CODE}"

    refusal = mount_refused(adopter, assembly, legs_to_mount(tmp_path),
                            SPEC, inside)

    assert refusal.code == UNADDABLE
    assert f"mount path {inside}: " in refusal.detail
    assert "is in submodule" in refusal.detail
    assert not (assembly / inside).exists()


# ---------------------------------------------------------------------------
# End to end, through `execute`
# ---------------------------------------------------------------------------


def planned(base: Path, source: Path, *extra: str,
            answers: tuple = ANSWERS) -> Path:
    """`plan` for `source`, its questions answered."""
    plan = base / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT, extra=extra)
    assert written.returncode == 0, written.stderr + written.stdout
    for path, leg in answers:
        resolve(plan, path, leg)
    return plan


def execute(base: Path, plan: Path):
    return run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                      "--local-remote-dir", str(base / REMOTES),
                      "--work-dir", str(base / "work"))


def split_branch_exists(source: Path) -> bool:
    return git("rev-parse", "--verify", "-q", BRANCH, cwd=source,
               check=False).returncode == 0


@pytest.fixture(scope="module")
def adopted(tmp_path_factory) -> SimpleNamespace:
    """One real adoption of a source whose `.gitignore` is `*` +
    `!.gitignore`. `check` says `plan ok` for it, as it always did: #174
    adopts this source rather than refusing it."""
    base = tmp_path_factory.mktemp("ignore-all")
    source = ignoring_source(base / SOURCE, IGNORE_ALL)
    assert hidden_mounts(source) == ROLES
    plan = planned(base, source)
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert "plan ok" in checked.stdout
    return SimpleNamespace(source=source, remotes=base / REMOTES,
                           result=execute(base, plan))


@needs_filter_repo
def test_execute_mounts_both_legs_past_a_gitignore_that_hides_them(adopted):
    """It used to exit 2 at the mount with both leg remotes already pushed.
    The split commit now holds each mount as a gitlink at the commit pushed
    to that leg, registered at its path."""
    result = adopted.result
    assert result.returncode == 0, result.stderr + result.stdout
    assert "adoption verified" in result.stdout
    for role in ROLES:
        pushed = head(adopted.remotes / f"{PROJECT}-{role}.git")
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


@needs_filter_repo
def test_execute_refuses_a_plan_that_mounts_both_legs_at_one_path(tmp_path):
    """`spec_path: code` edited into a plan `check` passes. With `--force`
    alone this exited 0, `adoption verified`, with the spec leg's commit as
    the only mount, at `code`. It is refused now, and nothing is split.

    The assertions do not name the refusal's code: #169 refuses equal leg
    paths before any leg exists, under its own, and once it lands this plan
    meets that refusal first. Either way it is refused and not split; the
    mount tests above pin `adopt-mount-occupied` itself."""
    source = make_source_repo(tmp_path / SOURCE)
    plan = planned(tmp_path, source)
    text = plan.read_text(encoding="utf-8")
    assert f"  spec_path: {SPEC}\n" in text
    plan.write_text(text.replace(f"  spec_path: {SPEC}\n",
                                 f"  spec_path: {CODE}\n", 1),
                    encoding="utf-8")

    result = execute(tmp_path, plan)

    assert result.returncode == 2, result.stderr + result.stdout
    assert "REFUSED " in result.stderr
    assert "adoption verified" not in result.stdout
    assert not split_branch_exists(source)


@needs_filter_repo
@needs_disk_symlinks
def test_execute_refuses_a_mount_through_a_kept_symlink(tmp_path):
    """A root-kept `legs -> <a directory outside>` and `--spec-path
    legs/spec`. With `--force` alone the spec leg was cloned through the
    link, outside `--work-dir`, before git refused the add."""
    outside = tmp_path / "outside"
    source = linked_source(tmp_path / SOURCE, outside)
    plan = planned(tmp_path, source, "--spec-path", THROUGH_LINK,
                   answers=(*ANSWERS, (LINK, ROOT)))

    result = execute(tmp_path, plan)

    assert result.returncode == 2, result.stderr + result.stdout
    assert f"REFUSED {UNADDABLE}: git will not add the leg mount path " \
        f"{THROUGH_LINK}: " in result.stderr
    assert list(outside.iterdir()) == []
    assert not split_branch_exists(source)
