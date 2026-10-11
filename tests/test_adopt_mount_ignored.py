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
a root-kept symlink, outside the work directory. A root-kept FILE on the way to
the path (`docs`, with `spec_path: docs/spec`) is refused by the same guard:
git fails on it in its own words only after both legs were pushed. Those tests
are here too.

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
import unicodedata
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import (ADOPT, DEFAULT_EDITS, FILE_PROTOCOL, SYNTHETIC_TREE,
                      git, make_source_repo, resolve, run_script, write_plan)

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
#: The source's directory, and the remotes' and the work directory beside it.
SOURCE, REMOTES, WORK = "Thing", "remotes", "work"
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
#: How the refusals say what holds the mount path.
INDEX = "the assembly's index"
#: A root-kept FILE named `docs`, and a mount path on the way through it.
KEPT_FILE = "docs"
UNDER_FILE = f"{KEPT_FILE}/{SPEC}"
#: The file `SYNTHETIC_TREE` keeps under a `docs` DIRECTORY.
ARCHITECTURE = "docs/architecture.md"
#: A directory the source keeps files in, which a mount path may be.
KEPT_DIR = "src"
#: What `execute` prints once every source path is accounted for.
VERIFIED = "adoption verified"
#: A directory beyond every repository the tests make.
OUTSIDE = "outside"

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

#: Built once per module: the adopter, and the end-to-end runs that the
#: tests below only read.
module_fixture = pytest.fixture(scope="module")


@module_fixture
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


def linked_source(path: Path, outside: Path, link: str = LINK) -> Path:
    """`make_source_repo`'s source with one more commit: `link`, a symlink
    to `outside`, an absolute directory beyond every repository here."""
    source = make_source_repo(path)
    outside.mkdir()
    try:
        os.symlink(str(outside), source / link)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"this platform cannot create a symlink here: {exc}")
    git("add", link, cwd=source)
    commit_all(source, "Link the legs directory")
    return source


def is_ignored(repo: Path, path: str) -> bool:
    return git("check-ignore", "--no-index", path, cwd=repo,
               check=False).returncode == 0


def hidden_mounts(source: Path) -> tuple:
    """The mount paths the source's rules hide, each asked about as the
    directory it is once a leg is cloned there."""
    return tuple(role for role in ROLES if is_ignored(source, f"{role}/"))


def config(repo: Path, *args: str) -> str:
    return git("config", *args, cwd=repo).stdout


def registrations(repo: Path, *where: str) -> list[str]:
    """Every `submodule.<name>.path <path>` line of a `.gitmodules`: the one
    on the disk, or `--blob <rev>:.gitmodules` for one in a commit."""
    return sorted(config(repo, *(where or ("-f", GITMODULES)),
                         "--get-regexp", r"^submodule\..*\.path$")
                  .splitlines())


def index_entry(repo: Path, path: str) -> str:
    """What the index holds at `path`, as `git ls-files -s` prints it."""
    return git("ls-files", "-s", "--", path, cwd=repo).stdout


def head(repo: Path) -> str:
    return git("rev-parse", "HEAD", cwd=repo).stdout.strip()


def clone(source: Path, destination: Path, *options: str) -> None:
    git(*FILE_PROTOCOL, "clone", "-q", *options, str(source),
        str(destination), cwd=destination.parent)


def assembly_of(source: Path, tmp_path: Path) -> Path:
    """A plain clone of `source`, as `_commit_the_split` makes the assembly."""
    assembly = tmp_path / PROJECT
    clone(source, assembly)
    return assembly


def legs_to_mount(tmp_path: Path) -> SimpleNamespace:
    """The two legs in a work directory, as `_build_the_legs` leaves them,
    with the canonical URLs `_mount_the_legs` records."""
    work = tmp_path / WORK
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
        assert index_entry(assembly, role) \
            == f"{GITLINK} {head(legs.work / legs.names[role])} 0\t{role}\n"
        url = config(assembly, "-f", GITMODULES, "--get",
                     f"submodule.{role}.url").strip()
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
    assert refusal.detail == \
        f"{INDEX} already holds the leg mount path {CODE}: `{CODE}` " \
        "(a submodule)"
    assert index_entry(assembly, CODE) == \
        f"{GITLINK} {head(legs.work / legs.names[SPEC])} 0\t{CODE}\n"


def test_a_mount_path_a_kept_submodule_holds_is_refused(adopter, tmp_path):
    """The source's own submodule at `spec`, kept in the root: the index
    holds a gitlink at the mount path. The refusal names it, rather than
    leaving the answer to whatever `--force` makes of a gitlink there."""
    source = make_source_repo(tmp_path / SOURCE)
    dependency = make_source_repo(tmp_path / "dependency",
                                  tree={"value.txt": "1\n"}, edits=())
    git(*FILE_PROTOCOL, "submodule", "add", str(dependency), SPEC, cwd=source)
    commit_all(source, "Depend on the dependency, at spec")
    assembly = assembly_of(source, tmp_path)

    refusal = mount_refused(adopter, assembly, legs_to_mount(tmp_path),
                            *ROLES)

    assert refusal.code == OCCUPIED
    assert refusal.detail == \
        f"{INDEX} already holds the leg mount path {SPEC}: `{SPEC}` " \
        "(a submodule)"


@needs_disk_symlinks
def test_a_mount_path_a_kept_symlink_holds_is_refused(adopter, tmp_path):
    """A root-kept symlink AT the mount path, which a mount would have to
    write through. The refusal says it is a symlink, and never writes the
    leg where the link points."""
    outside = tmp_path / OUTSIDE
    assembly = assembly_of(linked_source(tmp_path / SOURCE, outside, SPEC),
                           tmp_path)

    refusal = mount_refused(adopter, assembly, legs_to_mount(tmp_path),
                            *ROLES)

    assert refusal.code == OCCUPIED
    assert refusal.detail == \
        f"{INDEX} already holds the leg mount path {SPEC}: `{SPEC}` " \
        "(a symlink)"
    assert list(outside.iterdir()) == []


def test_a_mount_path_a_kept_directory_holds_files_under_is_refused(
        adopter, tmp_path):
    """The index holds entries UNDER `src`, not `src` itself, and the
    refusal says so, naming the first by its path and what it is. The name
    carries no raw tab: that is `git ls-files -s`'s own separator, and
    inside backticks it read as a path with a tab in it."""
    assembly = assembly_of(make_source_repo(tmp_path / SOURCE), tmp_path)
    assert index_entry(assembly, KEPT_DIR).count("\n") == 2, \
        "the source tree no longer keeps two files in src"

    refusal = mount_refused(adopter, assembly, legs_to_mount(tmp_path),
                            KEPT_DIR, CODE)

    assert refusal.code == OCCUPIED
    assert refusal.detail == \
        f"{INDEX} already holds paths under src, the leg mount path: " \
        "`src/app/main.py` (a file) and 1 more"
    assert "\t" not in refusal.detail


def test_the_entry_at_the_mount_path_is_named_before_one_under_it(adopter):
    """A disk that ignores case can hold `spec` and `SPEC/notes.md` in one
    index, and `git ls-files` lists the capitals first. The refusal says the
    mount path is held, so it names what holds THAT, not the first entry
    listed. Asked of the function itself, as an index like this is not one a
    test can rely on making on every disk."""
    held = [("a file", f"{SPEC.upper()}/notes.md"), ("a file", SPEC)]

    assert adopter._refusal_for_held(SPEC, held).detail == \
        f"{INDEX} already holds the leg mount path {SPEC}: `{SPEC}` " \
        "(a file) and 1 more"


def test_a_mount_path_holding_a_file_with_a_non_ascii_name_is_refused(
        adopter, tmp_path):
    """git prints a path with such a character QUOTED unless it is asked for
    NUL-terminated output, and `"src/d\\303\\266.py"` is not a path under
    `src`: the guard read it as nothing and let the mount through to the
    failure it exists to prevent. The name is spelled with an escape so that
    no editor or filesystem normalises it; a macOS checkout may hand it back
    decomposed, so the message is compared composed."""
    name = "src/d\u00f6.py"
    source = make_source_repo(tmp_path / SOURCE, tree={name: "x = 1\n"},
                              edits=())
    assembly = assembly_of(source, tmp_path)

    refusal = mount_refused(adopter, assembly, legs_to_mount(tmp_path),
                            KEPT_DIR, CODE)

    assert refusal.code == OCCUPIED
    assert unicodedata.normalize("NFC", refusal.detail) == \
        f"{INDEX} already holds paths under src, the leg mount path: " \
        f"`{name}` (a file)"


# A root-kept FILE on the way to the mount path: `docs`, with `spec_path:
# docs/spec`. git's own dry run passes it, and `git submodule add` dies
# "could not create leading directories" only AFTER both legs were pushed.


def kept_file_assembly(tmp_path: Path) -> Path:
    source = make_source_repo(
        tmp_path / SOURCE, tree={KEPT_FILE: "a file named docs\n",
                                 "README.md": "# Thing\n"}, edits=())
    return assembly_of(source, tmp_path)


def test_a_mount_path_under_a_kept_file_is_refused_before_the_clone(
        adopter, tmp_path):
    assembly = kept_file_assembly(tmp_path)

    refusal = mount_refused(adopter, assembly, legs_to_mount(tmp_path),
                            UNDER_FILE, CODE)

    assert refusal.code == OCCUPIED
    assert refusal.detail == \
        f"{INDEX} holds `{KEPT_FILE}` (a file) where the leg mount path " \
        f"{UNDER_FILE} needs a directory"
    assert (assembly / KEPT_FILE).is_file()
    assert not git("diff", "--cached", "--name-only", cwd=assembly).stdout, \
        "something was staged before the refusal"


def test_a_mount_path_beside_a_kept_directorys_files_is_mounted(adopter,
                                                                tmp_path):
    """The other side of the file on the way: `docs/` kept in the root as a
    DIRECTORY, with `spec_path: docs/spec`. The index then holds entries
    under `docs` and none AT it, and the mount sits beside them."""
    assembly = assembly_of(make_source_repo(tmp_path / SOURCE), tmp_path)
    assert index_entry(assembly, ARCHITECTURE), "docs is no longer a directory"
    legs = legs_to_mount(tmp_path)

    mount(adopter, assembly, legs, UNDER_FILE, CODE)

    assert index_entry(assembly, UNDER_FILE) == \
        f"{GITLINK} {head(legs.work / legs.names[SPEC])} 0\t{UNDER_FILE}\n"
    assert index_entry(assembly, ARCHITECTURE)


#: `(the source's files, spec_path, code_path, the refusal's detail)`. Each
#: is a case-only twin of a mount path: a mount `Spec` beside `spec`; a
#: root-kept `SPEC/notes.md` beside a `spec` mount; a root-kept FILE `Docs` on
#: the way to `docs/spec`. A macOS or Windows disk keeps each pair as ONE path,
#: and the assembly is cloned there too, so all three are refused on every
#: disk, as #169 refuses `Spec` and `spec` as the two legs' paths.
CASE_TWINS = [
    pytest.param(
        None, "Spec", SPEC,
        f"{INDEX} already holds the leg mount path {SPEC}: `Spec` "
        "(a submodule)", id="a-twin-mount"),
    pytest.param(
        {"SPEC/notes.md": "notes\n"}, SPEC, CODE,
        f"{INDEX} already holds paths under {SPEC}, the leg mount path: "
        "`SPEC/notes.md` (a file)", id="a-twin-directory"),
    pytest.param(
        {"Docs": "a file named Docs\n"}, UNDER_FILE, CODE,
        f"{INDEX} holds `Docs` (a file) where the leg mount path "
        f"{UNDER_FILE} needs a directory", id="a-twin-file-on-the-way"),
]


@pytest.mark.parametrize("ignorecase", ["false", "true"])
@pytest.mark.parametrize(("files", "spec_path", "code_path", "detail"),
                         CASE_TWINS)
def test_a_case_only_twin_is_refused_whatever_this_disk_does_with_case(
        adopter, tmp_path, ignorecase, files, spec_path, code_path, detail):
    """The index question is asked with `--icase-pathspecs` on every disk,
    and `core.ignorecase`, which `git clone` sets from THIS disk, is set by
    hand to both values here: the answer is the same either way, on Linux,
    macOS and Windows alike. Asked as `ls-files` alone, it matches
    case-sensitively and finds none of the three twins."""
    source = make_source_repo(tmp_path / SOURCE, tree=files,
                              edits=() if files else None)
    assembly = assembly_of(source, tmp_path)
    config(assembly, "core.ignorecase", ignorecase)

    refusal = mount_refused(adopter, assembly, legs_to_mount(tmp_path),
                            spec_path, code_path)

    assert refusal.code == OCCUPIED
    assert refusal.detail == detail


def test_the_remediation_says_how_to_run_again(adopter, tmp_path):
    """Both legs exist when a mount is refused, and so does the work
    directory holding their clones, which the next run cannot clone into:
    the way on is another path, fresh legs AND an empty `--work-dir`, or
    none. The end-to-end test below follows these words."""
    assembly = assembly_of(make_source_repo(tmp_path / SOURCE), tmp_path)

    remediation = mount_refused(adopter, assembly, legs_to_mount(tmp_path),
                                CODE, CODE).remediation

    assert "with no file, symlink or submodule it keeps there on the way" \
        in remediation
    assert "`--local-remote-dir`" in remediation
    assert "an empty `--work-dir`, or none" in remediation


@needs_disk_symlinks
def test_a_mount_path_beyond_a_kept_symlink_is_refused_before_the_clone(
        adopter, tmp_path):
    """`legs -> <a directory outside>`, kept in the root, and `spec_path:
    legs/spec`. `--force` skips git's own dry run of the path, so the leg was
    cloned THROUGH the link, outside the work directory, before git refused.
    The dry run is made first now, and nothing is written outside."""
    outside = tmp_path / OUTSIDE
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


def execute(base: Path, plan: Path, remotes: str = REMOTES,
            work: str = WORK):
    return run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                      "--local-remote-dir", str(base / remotes),
                      "--work-dir", str(base / work))


def edited(plan: Path, old: str, new: str, out: Path | None = None) -> Path:
    """`plan` with its first `old` replaced by `new`, written to `out` or in
    place, as a human or an AI edits it between `check` and `execute`."""
    text = plan.read_text(encoding="utf-8")
    assert old in text, f"{old!r} is not in the plan"
    (out or plan).write_text(text.replace(old, new, 1), encoding="utf-8")
    return out or plan


def checked_ok(plan: Path) -> None:
    """`check` says `plan ok`, as it did for every plan here."""
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert "plan ok" in checked.stdout


def split_branch_exists(source: Path) -> bool:
    return git("rev-parse", "--verify", "-q", BRANCH, cwd=source,
               check=False).returncode == 0


@module_fixture
def adopted(tmp_path_factory) -> SimpleNamespace:
    """One real adoption of a source whose `.gitignore` is `*` +
    `!.gitignore`. `check` says `plan ok` for it, as it always did: #174
    adopts this source rather than refusing it."""
    base = tmp_path_factory.mktemp("ignore-all")
    source = ignoring_source(base / SOURCE, IGNORE_ALL)
    assert hidden_mounts(source) == ROLES
    plan = planned(base, source)
    checked_ok(plan)
    return SimpleNamespace(source=source, remotes=base / REMOTES,
                           result=execute(base, plan))


@needs_filter_repo
def test_execute_mounts_both_legs_past_a_gitignore_that_hides_them(adopted):
    """It used to exit 2 at the mount with both leg remotes already pushed.
    The split commit now holds each mount as a gitlink at the commit pushed
    to that leg, registered at its path."""
    result = adopted.result
    assert result.returncode == 0, result.stderr + result.stdout
    assert VERIFIED in result.stdout
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
    checkout = tmp_path / PROJECT
    clone(adopted.source, checkout, "--recurse-submodules", "-b", BRANCH)
    bootstrapped = run_script(checkout / "scripts" / "bootstrap.py",
                              cwd=checkout)
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
    edited(plan, f"  spec_path: {SPEC}\n", f"  spec_path: {CODE}\n")

    result = execute(tmp_path, plan)

    assert result.returncode == 2, result.stderr + result.stdout
    assert "REFUSED " in result.stderr
    assert VERIFIED not in result.stdout
    assert not split_branch_exists(source)


@needs_filter_repo
@needs_disk_symlinks
def test_execute_refuses_a_mount_through_a_kept_symlink(tmp_path):
    """A root-kept `legs -> <a directory outside>` and `--spec-path
    legs/spec`. With `--force` alone the spec leg was cloned through the
    link, outside `--work-dir`, before git refused the add."""
    outside = tmp_path / OUTSIDE
    source = linked_source(tmp_path / SOURCE, outside)
    plan = planned(tmp_path, source, "--spec-path", THROUGH_LINK,
                   answers=(*ANSWERS, (LINK, ROOT)))

    result = execute(tmp_path, plan)

    assert result.returncode == 2, result.stderr + result.stdout
    assert f"REFUSED {UNADDABLE}: git will not add the leg mount path " \
        f"{THROUGH_LINK}: " in result.stderr
    assert list(outside.iterdir()) == []
    assert not split_branch_exists(source)


@module_fixture
def refused_under_a_file(tmp_path_factory) -> SimpleNamespace:
    """One real run of a plan `check` passes, whose `spec_path` is `docs/spec`
    while `docs` is a file the plan keeps in the root. What it left behind is
    recorded here, the instant it returned, so no test depends on another."""
    base = tmp_path_factory.mktemp("file-on-the-way")
    tree = {path: body for path, body in SYNTHETIC_TREE.items()
            if path != ARCHITECTURE}
    source = make_source_repo(base / SOURCE,
                              tree={**tree, KEPT_FILE: "a file named docs\n"})
    plan = planned(base, source, "--spec-path", UNDER_FILE)
    # A file called `docs` is `spec-governance` to the classifier.
    edited(plan, f"  - path: {KEPT_FILE}\n    leg: {SPEC}\n",
           f"  - path: {KEPT_FILE}\n    leg: {ROOT}\n    resolution: "
           '"kept in the root by the test"\n')
    checked_ok(plan)
    result = execute(base, plan)
    return SimpleNamespace(
        base=base, source=source, plan=plan, result=result,
        split=split_branch_exists(source),
        legs={role: (base / REMOTES / f"{PROJECT}-{role}.git").is_dir()
              for role in ROLES})


@needs_filter_repo
def test_execute_refuses_a_mount_under_a_kept_file_in_its_own_words(
        refused_under_a_file):
    """It exited 2 at the mount with git's `could not create leading
    directories ... Not a directory` and no remediation, after both legs were
    pushed. It is a named refusal now, with the remediation, and that
    remediation's first claim is true: the legs exist, and nothing was split."""
    state = refused_under_a_file
    assert state.result.returncode == 2, \
        state.result.stderr + state.result.stdout
    assert f"REFUSED {OCCUPIED}: {INDEX} holds `{KEPT_FILE}` (a file) where " \
        f"the leg mount path {UNDER_FILE} needs a directory" \
        in state.result.stderr
    assert "a git or gh command failed" not in state.result.stderr
    assert "with no file, symlink or submodule it keeps there" \
        in state.result.stderr
    assert VERIFIED not in state.result.stdout
    assert state.legs == {role: True for role in ROLES}
    assert not state.split


@needs_filter_repo
def test_the_remediations_next_step_adopts_the_source(refused_under_a_file):
    """The words of the refusal, followed: `legs.spec_path` changed, and the
    plan run again with fresh leg repositories and an empty `--work-dir`.
    Fresh repositories alone are not the way on, and the remediation says why:
    the refused run's own `--work-dir` still holds its clones of both legs,
    and the next run cannot clone into them."""
    state = refused_under_a_file
    assert "an empty `--work-dir`, or none" in state.result.stderr
    corrected = edited(state.plan, f"  spec_path: {UNDER_FILE}\n",
                       "  spec_path: specification\n",
                       state.base / "corrected-plan.yaml")
    checked_ok(corrected)

    reused = execute(state.base, corrected, "reused-work-remotes", WORK)
    again = execute(state.base, corrected, "fresh-remotes", "fresh-work")

    assert reused.returncode != 0
    assert VERIFIED not in reused.stdout
    assert again.returncode == 0, again.stderr + again.stdout
    assert VERIFIED in again.stdout
    assert split_branch_exists(state.source)
