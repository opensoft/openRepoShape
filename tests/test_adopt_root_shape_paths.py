# SPDX-License-Identifier: Apache-2.0
"""What the plan keeps in the root is not where the shape writes (#262, #263).

`check` said `plan ok` to a plan that keeps, in the assembly root,

- a plain FILE where the shape needs a directory (#263): the source's own file
  named `.github`, `contracts` or `scripts`. `execute` made and pushed both
  legs, and `place` died in `NotADirectoryError` (`.github`) or
  `FileExistsError` (`contracts`, `scripts`);
- the source's own `shape/` (#262), where the shape writes its copy of each
  file the root already holds. A real `shape/README.md` was overwritten by
  the shape's README, on the line after `execute` said "nothing was
  overwritten", and the verification ended `adopt-lost`; a directory
  `shape/Makefile/` died in `IsADirectoryError`, and a file named `shape` in
  `FileExistsError`. Both legs were pushed each time, so a corrected re-run
  met `leg-remote-exists`.

Now `check` reports each as a finding and `execute` refuses it before any leg
exists, as #172 and #165 refuse their classes. The materializer refuses to
write a copy over what is there too, for a caller that skipped `check`.

THE RULE IS PLAYED, NOT LISTED. `check` plays `place` over the paths the plan
keeps, in the order `assembly_root_paths` lists what the shape writes, so
these tests hold it to what `place` really does: a plan the rule passes is
adopted, end to end, and a plan it refuses is one `place` would not write.

Everything but the end-to-end tests runs on a machine with no `git
filter-repo`: `execute`'s probe for it is answered, because every refusal
under test comes before the tool would be used. The tests that make the legs
need it, as `tests/test_adopt_e2e.py` does.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import (ADOPT, FILE_PROTOCOL, REPO, SYNTHETIC_TREE, git,
                      make_source_repo, resolve, run_script, write_plan)

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402
from repo_shape import Refusal  # noqa: E402
from shape_materialize import (PLACEHOLDER_RE, first_and_more,  # noqa: E402
                               materialize_assembly_root)

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

#: A symlink is a plain file in a Windows checkout unless `core.symlinks`
#: is on.
needs_disk_symlinks = pytest.mark.skipif(
    sys.platform == "win32",
    reason="a symlink cannot be made on this disk")

PROJECT = "Northwind"
UTF8 = "utf-8"
REMOTES = "remotes"
WORK = "work"
ROLES = ("spec", "code")
SPLIT_BRANCH = "adopt/three-repo-shape"
ANSWERS = (("examples/", "spec"), (".claude/", "root"),
           ("release.yaml", "root"))
CASE_ASIDE = " once case is ignored, as a macOS or Windows disk does"

#: The two findings, and what `execute` writes in front of every one.
IN_THE_WAY = "plan-root-blocks-shape"
COPY_IN_THE_WAY = "plan-root-blocks-shape-copy"
BLOCKED = "materialize-copy-blocked"
RESERVED = ("`shape/` is reserved for the shape's own copies of files the "
            "root already holds")
AFTER_THE_LEGS = "after both leg repositories were created and pushed"

OWN_NOTES = "# Our shape notes\n"


@pytest.fixture(scope="module")
def adopter():
    """`adopt-project.py` loaded as a module, for the functions with no
    command line of their own."""
    module_spec = importlib.util.spec_from_file_location(
        "adopt_root_shape_paths", ADOPT)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


@pytest.fixture
def no_filter_repo_probe(adopter, monkeypatch):
    """`cmd_execute` asks for `git filter-repo` first; every refusal here
    comes before the tool would be used, so the probe is answered."""
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)


# --- what the shape writes, read from the materializer ---------------------

def written_under(adopter, directory: str) -> list[str]:
    """The paths the shape writes inside `directory`, from the list the
    materializer writes them by: no second list."""
    return [path for path in adopter.assembly_root_paths()
            if path.startswith(directory + "/")]


def directories_the_shape_writes_into(adopter) -> list[str]:
    """Every directory above a path of `assembly_root_paths`: `.github`,
    `.github/workflows`, `contracts`, `scripts`."""
    found: list[str] = []
    for path in adopter.assembly_root_paths():
        parts = path.split("/")
        for end in range(1, len(parts)):
            directory = "/".join(parts[:end])
            if directory not in found:
                found.append(directory)
    return found


# --- the rule, in memory ---------------------------------------------------

def row(path: str, mode: str = "100644") -> tuple:
    """A row of `Source.tree()`: `(path, mode, blob id, size)`."""
    return (path, mode, "0" * 40, 1)


def keeping(adopter, *entries: tuple):
    """An adoption plan in memory with these `(path, leg)` entries."""
    return adopter.Plan(Path("adoption-plan.yaml"), {
        "kind": "adoption-plan", "mode": "in-place",
        "legs": {"spec_path": "spec", "code_path": "code"},
        "paths": [{"path": path, "leg": leg} for path, leg in entries]})


def found(adopter, entries: list, rows: list) -> list[str]:
    return adopter._root_shape_findings(keeping(adopter, *entries), rows)


#: The synthetic source's own files a copy collides with, as rows: the root
#: holds each of the shape's paths a source keeps.
HOLDS_README = [row("README.md")]


@pytest.mark.parametrize("kept, entry", [
    pytest.param(".github", ".github", id="dot-github"),
    pytest.param(".github/workflows", ".github/",
                 id="dot-github-workflows-under-a-directory-entry"),
    pytest.param("contracts", "contracts", id="contracts"),
    pytest.param("scripts", "scripts", id="scripts"),
])
def test_a_file_kept_where_the_shape_needs_a_directory_is_a_finding(
        adopter, kept, entry):
    """#263. Each of the directories the shape writes into, as a FILE the
    plan keeps. The finding names the file, the shape's paths inside it, and
    the entry to change."""
    paths = written_under(adopter, kept)
    assert paths, f"the shape writes nothing inside {kept}"
    under = "" if kept == entry else f" under the entry `{entry}`"
    verb = "are inside" if len(paths) > 1 else "is inside"
    assert found(adopter, [(entry, "root")], [row(kept)]) == [
        f"FINDING {IN_THE_WAY}: the shape writes {first_and_more(paths)}, "
        f"which {verb} the file `{kept}`. The plan keeps it in the assembly "
        f"root{under}, and `execute` cannot make a directory where a file "
        f"is, so it would stop writing the shape's files {AFTER_THE_LEGS}: "
        f"send `{entry}` to a leg, `drop` it, or rename it in the source and "
        "re-run `plan`."]


def test_every_directory_the_shape_writes_into_is_found_as_a_file(adopter):
    """No second list: the directories are read off `assembly_root_paths`,
    so a directory the shape gains is one a kept file blocks, without anyone
    editing this rule."""
    directories = directories_the_shape_writes_into(adopter)
    assert {".github", "contracts", "scripts"} <= set(directories)
    for directory in directories:
        said, = found(adopter, [(directory, "root")], [row(directory)])
        assert said.startswith(f"FINDING {IN_THE_WAY}: the shape writes `"), \
            directory
        assert f"the file `{directory}`." in said, directory


def test_a_file_kept_at_a_path_the_shape_writes_is_not_a_finding(adopter):
    """A file where the shape writes a FILE is the collision `place` already
    handles: its copy goes under `shape/`. Only a file where a DIRECTORY is
    needed stops it. The manifest is the one exception, which no copy stands
    in for (#305): `tests/test_adopt_root_manifest.py` holds it."""
    for path in adopter.assembly_root_paths():
        codes = [said.split(":")[0]
                 for said in found(adopter, [(path, "root")], [row(path)])]
        assert codes == (["FINDING plan-root-blocks-manifest"]
                         if path == adopter.SHAPE_MANIFEST else []), path


@pytest.mark.parametrize("kept, tree, said", [
    pytest.param(
        "shape/README.md", [row("README.md"), row("shape/README.md")],
        "the shape's copy of `README.md` is written to `shape/README.md`, "
        "because the root already holds `README.md`. That path is the file "
        "`shape/README.md`. The plan keeps it in the assembly root under "
        "the entry `shape/`, and `execute` would write the copy over it "
        f"{AFTER_THE_LEGS}. {RESERVED}: send `shape/` to a leg, `drop` it, "
        "or rename it in the source and re-run `plan`.",
        id="a-file-at-the-copy"),
    pytest.param(
        "shape/Makefile", [row("Makefile"), row("shape/Makefile/notes.md"),
                           row("shape/Makefile/more.md")],
        "the shape's copy of `Makefile` is written to `shape/Makefile`, "
        "because the root already holds `Makefile`. That path contains the "
        "file `shape/Makefile/notes.md` and 1 more. The plan keeps them in "
        "the assembly root under the entry `shape/`, and `execute` cannot "
        "write a file where a directory is, so it would stop "
        f"{AFTER_THE_LEGS}. {RESERVED}: send `shape/` to a leg, `drop` it, "
        "or rename it in the source and re-run `plan`.",
        id="a-directory-at-the-copy"),
    pytest.param(
        "shape", [row("README.md"), row("shape")],
        "the shape's copy of `README.md` is written to `shape/README.md`, "
        "because the root already holds `README.md`. That path is inside "
        "the file `shape`. The plan keeps it in the assembly root, and "
        "`execute` cannot make a directory where a file is, so it would "
        f"stop {AFTER_THE_LEGS}. {RESERVED}: send `shape` to a leg, `drop` "
        "it, or rename it in the source and re-run `plan`.",
        id="a-file-on-the-way-to-the-copy"),
])
def test_a_kept_path_where_the_shape_writes_a_copy_is_a_finding(
        adopter, kept, tree, said):
    """#262's three cases, in the words of the finding: the copy would be
    written over a file, onto a directory, or beneath a file."""
    entry = kept.split("/")[0] + ("/" if "/" in kept else "")
    assert found(adopter, [(entry, "root"), ("README.md", "root"),
                           ("Makefile", "root")], tree) == [
        f"FINDING {COPY_IN_THE_WAY}: {said}"]


def test_several_copies_beneath_one_kept_file_are_one_finding(adopter):
    """A file named `shape` stops every copy, so it is said once, naming the
    first and counting the rest, as `_kept_collisions` does."""
    tree = [row(path) for path in ("README.md", "AGENTS.md", "Makefile")]
    said, = found(adopter, [("shape", "root"), ("README.md", "root"),
                            ("AGENTS.md", "root"), ("Makefile", "root")],
                  [*tree, row("shape")])
    assert said.startswith(
        f"FINDING {COPY_IN_THE_WAY}: the shape's copies of `README.md` and 2 "
        "more are written to `shape/README.md` and 2 more, because the root "
        "already holds each of them. Those paths are inside the file `shape`.")


def test_a_copy_is_only_asked_about_where_the_root_holds_the_path(adopter):
    """No collision, no copy: a source that keeps a file at `shape/README.md`
    and holds no `README.md` the shape would collide with is adopted, and
    its own file is never written over."""
    assert found(adopter, [("shape/", "root")],
                 [row("shape/README.md")]) == []


def test_a_kept_directory_holding_the_path_makes_the_copy_too(adopter):
    """`place` asks `path.exists()`, which is true of a directory: a source
    that keeps a directory named `Makefile` has a collision, and so a copy at
    `shape/Makefile`, which a real file there would block."""
    rows = [row("Makefile/notes.md"), row("shape/Makefile")]
    said, = found(adopter, [("Makefile/", "root"), ("shape/", "root")], rows)
    assert said.startswith(
        f"FINDING {COPY_IN_THE_WAY}: the shape's copy of `Makefile` is "
        "written to `shape/Makefile`, because the root already holds "
        "`Makefile`. That path is the file `shape/Makefile`.")


@pytest.mark.parametrize("rows, entries", [
    pytest.param([row("README.md"), row("shape/notes.md")],
                 [("README.md", "root"), ("shape/", "root")],
                 id="shape-dir-with-nothing-at-a-copy"),
    pytest.param([row("README.md"), row("shape/docs/guide.md")],
                 [("README.md", "root"), ("shape/", "root")],
                 id="shape-dir-nested"),
    pytest.param([row(".github/workflows/ci.yml"), row("contracts/a.yaml"),
                  row("scripts/run.sh"), row("README.md")],
                 [(".github/", "root"), ("contracts/", "root"),
                  ("scripts/", "root"), ("README.md", "root")],
                 id="directories-the-shape-writes-into"),
    pytest.param([row(".github/workflows/validate.yml"), row("README.md")],
                 [(".github/", "root"), ("README.md", "root")],
                 id="a-workflow-of-the-shapes-name"),
    pytest.param([row("README.md"), row("shapes"), row("shape-x/README.md"),
                  row("scriptsx"), row("contracts.md")],
                 [("README.md", "root"), ("shapes", "root"),
                  ("shape-x/", "root"), ("scriptsx", "root"),
                  ("contracts.md", "root")],
                 id="a-name-that-only-shares-a-prefix"),
])
def test_a_plan_keeping_nothing_in_the_way_has_no_finding(adopter, rows,
                                                          entries):
    """The same trees, adopted: the kept paths share a directory with what
    the shape writes and stand on none of it."""
    assert found(adopter, entries, rows) == []


@pytest.mark.parametrize("leg", ["spec", "code", "drop"])
def test_a_path_the_plan_sends_away_is_not_kept(adopter, leg):
    """`git rm` has removed it by the time the shape is written, so a file
    named `contracts` or `shape` that goes to a leg or is dropped is not in
    the way: only what the plan keeps in the ROOT is asked about."""
    rows = [row("README.md"), row("contracts"), row("shape")]
    assert found(adopter, [("contracts", leg), ("shape", leg),
                           ("README.md", "root")], rows) == []


# --- a symlink or a submodule is another rule's -----------------------------

@pytest.mark.parametrize("mode, path", [
    pytest.param("120000", ".github", id="symlink-above-a-shape-path"),
    pytest.param("120000", "contracts", id="symlink-above-a-shape-path-2"),
    pytest.param("160000", "scripts", id="submodule-above-a-shape-path"),
    pytest.param("120000", "shape", id="symlink-above-a-copy"),
    pytest.param("160000", "shape", id="submodule-above-a-copy"),
])
def test_a_symlink_or_submodule_is_not_a_file_where_a_directory_is(
        adopter, mode, path):
    """A symlink ABOVE a shape path is followed, or refused, by the symlink
    rule (#183, #178), and a submodule the root keeps is
    `plan-submodule-root` (#166). Neither is a FILE where a directory is
    needed, so neither is found here as one."""
    assert found(adopter, [(path, "root"), ("README.md", "root")],
                 [row(path, mode), row("README.md")]) == []


def test_a_symlink_at_the_copy_itself_is_in_the_way(adopter):
    """`place` writes the copy THROUGH a link at its path, onto whatever the
    link leads to: something is AT the path, whatever it is. Nothing on main
    finds a link there, so it is said here, as a write through it and not
    over it."""
    said, = found(adopter, [("shape/", "root"), ("README.md", "root")],
                  [row("README.md"), row("shape/README.md", "120000")])
    assert "That path is the symlink `shape/README.md`." in said
    assert said.startswith(f"FINDING {COPY_IN_THE_WAY}: ")
    assert "`execute` would write the copy through it " in said
    assert "over it" not in said


@pytest.mark.parametrize("rows", [
    pytest.param([row("README.md"), row("shape/README.md", "160000")],
                 id="a-submodule-at-the-copy"),
    pytest.param([row("Makefile"), row("shape/Makefile/sub", "160000")],
                 id="a-submodule-below-the-copy"),
    pytest.param([row("Makefile"), row("shape/Makefile/sub", "160000"),
                  row("shape/Makefile/dep", "160000")],
                 id="a-directory-at-the-copy-of-nothing-but-submodules"),
])
def test_a_submodule_at_the_copy_is_said_once_by_the_submodule_rule(
        adopter, rows):
    """A submodule the plan keeps in the root is `plan-submodule-root`'s
    (#166), which refuses the plan; this rule does not say the same path a
    second time. And what it would say is not true of one: in the clone a
    submodule is an empty directory, so `place` stops at it and overwrites
    nothing, where the finding's sentence says the copy is written over what
    stands there."""
    entries = [("README.md", "root"), ("Makefile", "root"),
               ("shape/", "root")]
    assert found(adopter, entries, rows) == []


def test_a_directory_at_the_copy_names_its_files_and_never_its_submodules(
        adopter):
    """The same path stays in the way for what ELSE is under it: the finding
    names the file, as it did, and leaves the submodule to the submodule
    rule."""
    rows = [row("Makefile"), row("shape/Makefile/sub", "160000"),
            row("shape/Makefile/notes.md")]
    said, = found(adopter, [("Makefile", "root"), ("shape/", "root")], rows)
    assert "That path contains the file `shape/Makefile/notes.md`." in said
    assert "shape/Makefile/sub" not in said
    assert "submodule" not in said


@pytest.mark.parametrize("held", ["README.md", "Makefile"])
def test_a_symlink_where_the_shape_writes_counts_as_the_root_holding_it(
        adopter, held):
    """A kept symlink at a shape path counts as the root holding it.
    `place` asks `Path.exists()`, which FOLLOWS a link and is false of one
    that leads nowhere (written through, so no copy is made); but a tree row
    holds no target to follow, and whether a link leads anywhere is the
    symlink rule's question (#183, #178). Counting it errs towards refusing:
    for a link that leads nowhere the finding below describes a copy that is
    not written, in a plan that rule refuses anyway, and no plan `place`
    would stop at is passed."""
    rows = [row(held, "120000"), row(f"shape/{held}")]
    said, = found(adopter, [(held, "root"), ("shape/", "root")], rows)
    assert said.startswith(
        f"FINDING {COPY_IN_THE_WAY}: the shape's copy of `{held}` is written "
        f"to `shape/{held}`, because the root already holds `{held}`. ")
    # And one that is not held at all is not asked about, link or no link.
    assert found(adopter, [("shape/", "root")], [row(f"shape/{held}")]) == []


# --- case --------------------------------------------------------------------

def test_a_file_named_like_a_directory_but_for_case_is_found_too(adopter):
    """#172's rule for a mount path, for the same reason: a macOS or Windows
    disk keeps `Scripts` and `scripts` as one name, and the assembly is cloned
    there. Said as holding only once case is ignored."""
    paths = written_under(adopter, "scripts")
    said, = found(adopter, [("Scripts", "root")], [row("Scripts")])
    assert said.startswith(
        f"FINDING {IN_THE_WAY}: the shape writes {first_and_more(paths)}, "
        f"which are inside the file `Scripts`{CASE_ASIDE}. ")


def test_a_copy_beside_a_case_twin_is_in_the_way_on_that_disk(adopter):
    rows = [row("README.md"), row("Shape/README.md")]
    said, = found(adopter, [("README.md", "root"), ("Shape/", "root")], rows)
    assert said.startswith(
        f"FINDING {COPY_IN_THE_WAY}: the shape's copy of `README.md` is "
        "written to `shape/README.md`, because the root already holds "
        "`README.md`. That path is the file `Shape/README.md`"
        f"{CASE_ASIDE}.")


@pytest.mark.parametrize("kept", ["scripts", "contracts", ".github"])
def test_what_holds_with_case_kept_is_not_said_again_without_it(adopter,
                                                                kept):
    said, = found(adopter, [(kept, "root")], [row(kept)])
    assert CASE_ASIDE not in said


#: The paths a source keeps in the root, which a disk that keeps case lets
#: the shape write beside and one that ignores it does not: a `readme.md` is
#: `README.md` there, so the shape's README collides with it, its copy goes
#: to `shape/README.md`, and whatever the source keeps at that path, however
#: it is spelled, is in the way. Each is a tree such a disk can hold.
BLOCKED_ONLY_WHERE_CASE_IS_IGNORED = [
    pytest.param(("readme.md", "shape/README.md"), id="a-file-at-the-copy"),
    pytest.param(("readme.md", "shape/readme.md"),
                 id="the-copy-spelled-in-lower-case"),
    pytest.param(("readme.md", "Shape/README.md"),
                 id="the-copy-under-another-spelling-of-shape"),
    pytest.param(("readme.md", "shape"), id="a-file-named-shape"),
    pytest.param(("readme.md", "SHAPE"), id="a-file-named-shape-in-capitals"),
    pytest.param(("readme.md", "shape/README.md/notes.md"),
                 id="a-directory-at-the-copy"),
    pytest.param(("MAKEFILE", "shape/Makefile"), id="a-capitalised-makefile"),
    pytest.param(("agents.md", "shape/AGENTS.md"), id="another-copy"),
    pytest.param(("makefile/notes.md", "shape/Makefile"),
                 id="a-directory-the-path-names-once-case-is-ignored"),
]

#: The same names where no copy is written, or where it is written to a free
#: place: not blocked on either kind of disk.
FREE_WHERE_CASE_IS_IGNORED = [
    pytest.param(("readme.md", "shape/notes.md"), id="nothing-at-the-copy"),
    pytest.param(("readme.md",), id="no-shape-directory"),
    pytest.param(("shape/readme.md",), id="a-copy-and-no-readme-to-collide"),
    pytest.param(("shape/README.md",), id="a-copy-of-the-name-no-readme"),
    pytest.param(("README.md", "shape/readme.txt"), id="another-name"),
]


def the_shapes_spelling(adopter) -> dict[str, str]:
    """Every directory and file the shape writes, and each one's copy under
    `shape/`, as the shape spells it, by its name with case ignored."""
    spelled: dict[str, str] = {}
    for rel in adopter.assembly_root_paths():
        for path in (rel, f"shape/{rel}"):
            parts = path.split("/")
            for end in range(1, len(parts) + 1):
                prefix = "/".join(parts[:end])
                spelled.setdefault(prefix.casefold(), prefix)
    return spelled


def as_a_disk_that_ignores_case_keeps(adopter, paths) -> list[str]:
    """`paths` as such a disk holds them. Every lookup `place` makes is
    spelled the shape's way (`README.md`, `shape/README.md`, `scripts`), and
    a disk that ignores case answers each as it would if the source's own
    name for it were spelled that way. So each component of a kept path that
    is the shape's name once case is ignored is respelled as the shape
    spells it, and `place` is run over THAT: on a disk that keeps case, and on
    one that does not, it does the same. A tree with two paths that are one
    name once case is ignored is not one such a disk holds, and is not
    asked."""
    spelled = the_shapes_spelling(adopter)
    out = []
    for path in paths:
        built = ""
        for part in path.split("/"):
            wanted = f"{built}/{part}" if built else part
            built = spelled.get(wanted.casefold(), wanted)
        out.append(built)
    assert len({p.casefold() for p in out}) == len(out), paths
    return out


def place_stops_or_overwrites(adopter, tmp_path: Path, paths) -> bool:
    """Run the shape's `place` over a root that holds `paths`, as a disk that
    ignores case holds them: whether it raised, or wrote over a kept file."""
    target = tmp_path / "assembly"
    kept = as_a_disk_that_ignores_case_keeps(adopter, paths)
    for name in kept:
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"kept:{name}\n".encode(UTF8))
    try:
        materialize_assembly_root(REPO, target, template_values(),
                                  collision_dir="shape")
    except Exception:  # noqa: BLE001 -- any stop, a Refusal or a traceback
        return True
    return any((target / name).read_bytes() != f"kept:{name}\n".encode(UTF8)
               for name in kept)


def asked_of_the_plan(adopter, paths):
    """What `check` finds in a plan that keeps every one of `paths` in the
    root: each is its own entry, and a path under `shape/` is the
    directory's."""
    return found(adopter, [(p, "root") for p in paths],
                 [row(p) for p in paths])


@pytest.mark.parametrize("paths", BLOCKED_ONLY_WHERE_CASE_IS_IGNORED)
def test_a_copy_is_written_where_a_disk_that_ignores_case_holds_the_path(
        adopter, paths):
    """`place` asks `path.exists()`, and on a macOS or Windows disk a kept
    `readme.md` EXISTS as `README.md`: the shape's README collides with it,
    its copy goes to `shape/README.md`, and whatever the source keeps there
    blocks it. `check` said `plan ok` to each of these, read the copy's
    place with case ignored and whether a copy is written at all with case
    kept; `execute` then made both legs and `place` stopped, or wrote over
    the source's own file."""
    said = asked_of_the_plan(adopter, paths)
    assert said, f"{paths}: a plan that `place` stops at on that disk"
    assert {s.split(":")[0] for s in said} == {f"FINDING {COPY_IN_THE_WAY}"}
    assert all(CASE_ASIDE in s for s in said)


@pytest.mark.parametrize("paths", FREE_WHERE_CASE_IS_IGNORED)
def test_a_free_copy_is_not_found_on_a_disk_that_ignores_case(adopter,
                                                              paths):
    assert asked_of_the_plan(adopter, paths) == []


@pytest.mark.parametrize("paths", [*BLOCKED_ONLY_WHERE_CASE_IS_IGNORED,
                                   *FREE_WHERE_CASE_IS_IGNORED])
def test_what_check_finds_is_what_place_does_on_a_disk_that_ignores_case(
        adopter, tmp_path, paths):
    """The rule is played, and held to the real thing on the disk it claims
    to model: the shape's own materializer run over the tree such a disk
    holds. Raised or overwrote a kept file, if and only if `check` finds."""
    assert bool(asked_of_the_plan(adopter, paths)) == \
        place_stops_or_overwrites(adopter, tmp_path, paths), paths


def test_the_finding_says_the_root_holds_the_path_only_once_case_is_ignored(
        adopter):
    """The kept path is `readme.md`, so on a disk that keeps case the root
    holds no `README.md` and no copy is written: the finding says that it
    does on the other kind, as every finding of this rule does that only
    that kind makes."""
    rows = [row("readme.md"), row("shape/README.md")]
    said, = found(adopter, [("readme.md", "root"), ("shape/", "root")], rows)
    assert said == (
        f"FINDING {COPY_IN_THE_WAY}: the shape's copy of `README.md` is "
        "written to `shape/README.md`, because the root already holds "
        f"`README.md`{CASE_ASIDE}. That path is the file `shape/README.md`. "
        "The plan keeps it in the assembly root under the entry `shape/`, "
        f"and `execute` would write the copy over it {AFTER_THE_LEGS}. "
        f"{RESERVED}: send `shape/` to a leg, `drop` it, or rename it in the "
        "source and re-run `plan`.")


def test_what_holds_with_case_kept_says_nothing_of_case_in_what_it_holds(
        adopter):
    """The same plan with the file spelled as the shape spells it: the root
    holds `README.md` on every disk, so the sentence says nothing of case."""
    rows = [row("README.md"), row("shape/README.md")]
    said, = found(adopter, [("README.md", "root"), ("shape/", "root")], rows)
    assert CASE_ASIDE not in said


def test_several_copies_held_once_case_is_ignored_are_one_finding(adopter):
    """A file named `shape` stops every copy, so it is one finding, as when
    the root holds them with case kept; the sentence says the root holds
    them once case is ignored."""
    paths = ("readme.md", "agents.md", "makefile", "shape")
    said, = asked_of_the_plan(adopter, paths)
    assert said.startswith(
        f"FINDING {COPY_IN_THE_WAY}: the shape's copies of `README.md` and 2 "
        "more are written to `shape/README.md` and 2 more, because the root "
        f"already holds each of them{CASE_ASIDE}. Those paths are inside the "
        "file `shape`.")


def test_a_finding_that_mixes_copies_held_either_way_is_still_one(adopter):
    """The root holds `README.md` on every disk and `AGENTS.md` only once
    case is ignored; a file named `shape` stops both copies. One finding for
    the one kept path, and what it says of the root holding them is true of
    both disks: each is held once case is ignored."""
    said, = asked_of_the_plan(adopter, ("README.md", "agents.md", "shape"))
    assert said.startswith(
        f"FINDING {COPY_IN_THE_WAY}: the shape's copies of `README.md` and 1 "
        "more are written to `shape/README.md` and 1 more, because the root "
        f"already holds each of them{CASE_ASIDE}. Those paths are inside the "
        "file `shape`.")


# --- one list ----------------------------------------------------------------

def test_the_findings_come_in_the_order_the_shape_writes(adopter):
    """`README.md` is the first path the shape writes, `contracts/...` the
    third and `.github/...` the thirteenth, whatever order the plan lists
    them in."""
    rows = [row(".github"), row("contracts"), row("shape/README.md"),
            row("README.md")]
    entries = [(".github", "root"), ("contracts", "root"),
               ("shape/", "root"), ("README.md", "root")]
    said = found(adopter, entries, rows)
    assert [(s.split(":")[0], s.split("`")[1]) for s in said] == [
        (f"FINDING {COPY_IN_THE_WAY}", "README.md"),
        (f"FINDING {IN_THE_WAY}", "contracts/spec-pin.yaml"),
        (f"FINDING {IN_THE_WAY}", ".github/workflows/validate.yml")]


def test_leg_findings_asks_it_and_a_placement_plan_never_does(adopter):
    """`check` and `execute` read `_leg_findings`, which reads this rule.
    The doctor's PLACEMENT plan has a `legs:` LIST and no source tree: it is
    asked about its entries only, and is not asked this."""
    plan = keeping(adopter, ("contracts", "root"))
    said = adopter._leg_findings(plan, [row("contracts")])
    assert [s.split(":")[0] for s in said] == [f"FINDING {IN_THE_WAY}"]
    placement = adopter.Plan(Path("placement-plan.yaml"), {
        "kind": "adoption-plan", "mode": "in-place",
        "legs": [{"name": "spec"}],
        "paths": [{"path": "contracts", "leg": "root"}]})
    assert adopter._leg_findings(placement, None) == []


# --- `check` and `execute`, on real plans ------------------------------------

def without(*prefixes: str) -> dict:
    """The synthetic tree minus every path at or under each prefix."""
    return {path: body for path, body in SYNTHETIC_TREE.items()
            if not any(path == p or path.startswith(p + "/")
                       for p in prefixes)}


def with_files(files: dict, *drop: str) -> dict:
    return {**without(*drop), **files}


#: `(tree, the entry kept in the root, the code, what the finding says)`: the
#: six reproductions of #262 and #263, as the issues give them, beside the
#: same plan one rename away from adopting.
ISSUE_CASES = [
    pytest.param(
        with_files({"shape/README.md": OWN_NOTES}), "shape", COPY_IN_THE_WAY,
        "the shape's copy of `README.md` is written to `shape/README.md`",
        id="262-a-real-shape-readme"),
    pytest.param(
        with_files({"shape/Makefile/notes.md": "x\n"}), "shape",
        COPY_IN_THE_WAY, "That path contains the file "
        "`shape/Makefile/notes.md`", id="262-a-directory-shape-makefile"),
    pytest.param(
        with_files({"shape": "a file named shape\n"}), "shape",
        COPY_IN_THE_WAY, "inside the file `shape`",
        id="262-a-file-named-shape"),
    pytest.param(
        with_files({".github": "a plain file\n"}, ".github"), ".github",
        IN_THE_WAY, "the shape writes `.github/workflows/validate.yml`, "
        "which is inside the file `.github`", id="263-a-file-dot-github"),
    pytest.param(
        with_files({"contracts": "a plain file\n"}, "contracts"),
        "contracts", IN_THE_WAY, "which are inside the file `contracts`",
        id="263-a-file-contracts"),
    pytest.param(
        with_files({"scripts": "a plain file\n"}), "scripts", IN_THE_WAY,
        "which are inside the file `scripts`", id="263-a-file-scripts"),
]


def answered_plan(source: Path, out: Path) -> Path:
    written = write_plan(source, out, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    for path, leg in ANSWERS:
        resolve(out, path, leg)
    return out


def answer(plan: Path, prefix: str, leg: str) -> None:
    """Answer every entry at or under `prefix` with `leg`, as a person would,
    with a reason; however `plan` grouped them."""
    text = plan.read_text(encoding=UTF8)
    entry = re.compile(r"^  - path: (?P<path>\S+)\n    leg: \S+\n",
                       re.MULTILINE)

    def edit(match: re.Match) -> str:
        path = match.group("path")
        if path.rstrip("/") != prefix and not path.startswith(prefix + "/"):
            return match.group(0)
        return (f"  - path: {path}\n    leg: {leg}\n"
                "    resolution: \"answered by the test\"\n")

    edited = entry.sub(edit, text)
    assert edited != text, f"no entry at or under {prefix} in the plan"
    with plan.open("w", encoding=UTF8, newline="\n") as handle:
        handle.write(edited)


def kept_source(tmp_path: Path, tree: dict, kept: str, leg: str = "root"):
    """A source with `tree`, and an answered plan that gives `kept` `leg`."""
    source = make_source_repo(tmp_path / "Thing", tree=tree)
    plan = answered_plan(source, tmp_path / "plan.yaml")
    answer(plan, kept, leg)
    return source, plan


def check(plan: Path):
    return run_script(ADOPT, "check", "--plan", str(plan))


def findings_of(result) -> list[str]:
    return [line for line in result.stderr.splitlines()
            if line.startswith("FINDING ")]


@pytest.mark.parametrize("tree, kept, code, said", ISSUE_CASES)
def test_check_reports_what_it_passed(tmp_path, tree, kept, code, said):
    _, plan = kept_source(tmp_path, tree, kept)
    result = check(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    finding, = findings_of(result)
    assert finding.startswith(f"FINDING {code}: ")
    assert said in finding
    assert "plan ok" not in result.stdout
    assert "1 finding(s) in " in result.stderr


@pytest.mark.parametrize("leg", ["spec", "drop"])
@pytest.mark.parametrize("tree, kept, code, said", ISSUE_CASES)
def test_the_remediation_the_finding_names_makes_check_pass(
        tmp_path, tree, kept, code, said, leg):
    """`send <entry> to a leg, drop it`: either, and the plan checks ok,
    where the plan that keeps it in the root does not."""
    _, kept_plan = kept_source(tmp_path / "kept", tree, kept)
    assert findings_of(check(kept_plan))
    _, plan = kept_source(tmp_path / "sent", tree, kept, leg=leg)
    result = check(plan)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "plan ok" in result.stdout


def execute_args(tmp_path: Path, plan: Path) -> Namespace:
    """What `main` hands `cmd_execute`: `--yes`, a local remote directory
    that does not exist yet, and a work directory."""
    return Namespace(plan=str(plan), source=None,
                     local_remote_dir=tmp_path / REMOTES, allow_empty_leg=[],
                     yes=True, work_dir=tmp_path / WORK)


def no_leg_was_created(tmp_path: Path, source: Path) -> None:
    """What a refused run leaves undone: the directory the legs would have
    gone in was never made, no leg was cloned, and the source has no split
    branch."""
    assert not (tmp_path / REMOTES).exists(), (
        "not even the directory the legs go in")
    for role in ROLES:
        assert not (tmp_path / WORK / f"{PROJECT}-{role}").exists()
    assert git("branch", "--list", SPLIT_BRANCH, cwd=source).stdout == ""


@pytest.mark.parametrize("tree, kept, code, said", ISSUE_CASES)
def test_execute_refuses_it_before_any_leg_exists(
        adopter, no_filter_repo_probe, tmp_path, tree, kept, code, said):
    source, plan = kept_source(tmp_path, tree, kept)
    printed, = findings_of(check(plan))
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(execute_args(tmp_path, plan))
    assert caught.value.code == code
    assert printed in caught.value.detail
    assert ("keep in the root no path where the shape writes a file or its "
            "copy") in caught.value.remediation
    no_leg_was_created(tmp_path, source)


def test_execute_refuses_every_finding_at_once_and_leads_with_the_first(
        adopter, no_filter_repo_probe, tmp_path):
    """A `.github` file and an own `shape/README.md` together: the refusal
    carries both findings as `check` prints them, under the first one's code,
    which is the one for the first path the shape writes (`README.md`)."""
    tree = with_files({".github": "a plain file\n",
                       "shape/README.md": OWN_NOTES}, ".github")
    source, plan = kept_source(tmp_path, tree, ".github")
    answer(plan, "shape", "root")
    printed = findings_of(check(plan))
    assert [p.split(":")[0] for p in printed] == [
        f"FINDING {COPY_IN_THE_WAY}", f"FINDING {IN_THE_WAY}"]
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(execute_args(tmp_path, plan))
    assert caught.value.code == COPY_IN_THE_WAY
    for finding in printed:
        assert finding in caught.value.detail
    no_leg_was_created(tmp_path, source)


def lower_case_readme_source(tmp_path: Path):
    """A source whose README is `readme.md` and which keeps its own
    `shape/README.md`: it adopts where case is kept, and where case is
    ignored the shape's README collides with `readme.md`, so its copy goes
    to the source's own `shape/README.md`."""
    tree = with_files({"readme.md": "# Thing\n",
                       "shape/README.md": OWN_NOTES}, "README.md")
    source, plan = kept_source(tmp_path, tree, "shape")
    answer(plan, "readme.md", "root")
    return source, plan


def test_check_finds_what_only_a_disk_that_ignores_case_would_stop_at(
        tmp_path):
    """The case the review found: `check` said `plan ok`, and `execute`
    on macOS or Windows made both legs and then stopped."""
    _, plan = lower_case_readme_source(tmp_path)
    result = check(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    finding, = findings_of(result)
    assert finding.startswith(
        f"FINDING {COPY_IN_THE_WAY}: the shape's copy of `README.md` is "
        "written to `shape/README.md`, because the root already holds "
        f"`README.md`{CASE_ASIDE}. ")
    assert "plan ok" not in result.stdout


def test_execute_refuses_it_before_any_leg_exists_too(
        adopter, no_filter_repo_probe, tmp_path):
    source, plan = lower_case_readme_source(tmp_path)
    printed, = findings_of(check(plan))
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(execute_args(tmp_path, plan))
    assert caught.value.code == COPY_IN_THE_WAY
    assert printed in caught.value.detail
    no_leg_was_created(tmp_path, source)


def add_a_submodule(tmp_path: Path, source: Path, at: str) -> None:
    """`git submodule add` of a local repository at `at` in `source`, as a
    person adding a dependency would, committed."""
    dependency = make_source_repo(tmp_path / "dependency",
                                  tree={"value.txt": "first\n"}, edits=())
    git(*FILE_PROTOCOL, "submodule", "add", "-q", str(dependency), at,
        cwd=source)
    git("-c", "user.name=Source Human", "-c",
        "user.email=source@invalid.example", "commit", "-qm",
        "Add a dependency", cwd=source)


def test_check_names_a_submodule_at_the_copy_once_and_by_the_submodule_rule(
        tmp_path):
    """The source keeps a submodule AT `shape/README.md`. #166 refuses a
    submodule kept in the root, and says it of `.gitmodules` and of the
    submodule's path, once each; this rule says nothing of the same path,
    which would be a third finding naming `shape/README.md`, and one that
    describes a copy written over a submodule."""
    source = make_source_repo(tmp_path / "Thing")
    add_a_submodule(tmp_path, source, "shape/README.md")
    plan = answered_plan(source, tmp_path / "plan.yaml")
    answer(plan, ".gitmodules", "root")
    answer(plan, "shape", "root")
    result = check(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    codes = [line.split(":")[0] for line in findings_of(result)]
    assert codes == ["FINDING plan-submodule-root"] * 2, result.stderr
    named = [line for line in findings_of(result)
             if "`shape/README.md`" in line]
    assert len(named) == 1, "the path is said once"
    assert COPY_IN_THE_WAY not in result.stderr


def test_the_finding_spells_a_kept_path_it_cannot_print_as_it_is(adopter):
    """A source path is bytes, and a name may hold a line break: it is
    spelled with a backslash, as every finding of `check`'s that names a
    source path spells it (#166), so the finding stays on one line."""
    said, = found(adopter, [("Makefile", "root"), ("shape/", "root")],
                  [row("Makefile"), row("shape/Makefile/a\nb"),
                   row("shape/Makefile/\udce9")])
    assert "\n" not in said
    assert "the file `shape/Makefile/a\\nb` and 1 more." in said


# --- end to end -----------------------------------------------------------

def executed(plan: Path, tmp_path: Path):
    """`execute` run as the command, in its own process."""
    return run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                      "--local-remote-dir", str(tmp_path / REMOTES),
                      "--work-dir", str(tmp_path / WORK))


@needs_filter_repo
@pytest.mark.parametrize("tree, kept, code, said", ISSUE_CASES)
def test_execute_refuses_it_end_to_end_and_the_remote_dir_stays_empty(
        tmp_path, tree, kept, code, said):
    """The issues' reproductions: on main each ended with both leg
    repositories pushed, and a traceback, or `adopt-lost`. Refused before a
    leg is made, so the EMPTY `--local-remote-dir` it is given stays empty."""
    source, plan = kept_source(tmp_path, tree, kept)
    (tmp_path / REMOTES).mkdir()
    result = executed(plan, tmp_path)
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"REFUSED {code}: 1 finding(s) in " in result.stderr
    assert said in result.stderr
    assert "Traceback" not in result.stderr
    assert "creating the leg repositories" not in result.stdout
    assert "adoption verified" not in result.stdout
    assert list((tmp_path / REMOTES).iterdir()) == [], "no leg was made"
    assert not (tmp_path / WORK / f"{PROJECT}-spec").exists()
    assert git("branch", "--list", SPLIT_BRANCH, cwd=source).stdout == ""


@needs_filter_repo
def test_a_plan_that_keeps_its_own_shape_directory_beside_the_copies_adopts(
        tmp_path):
    """Not over-refused: `shape/` kept in the root with a file of its own,
    nothing at a path the shape writes a copy to. The shape's copies land
    beside it, and the verification accounts for every path."""
    tree = with_files({"shape/notes.md": OWN_NOTES})
    source, plan = kept_source(tmp_path, tree, "shape")
    assert check(plan).returncode == 0
    result = executed(plan, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "adoption verified" in result.stdout
    split = git("ls-tree", "-r", "--name-only", SPLIT_BRANCH,
                cwd=source).stdout.splitlines()
    assert "shape/notes.md" in split, "the source's own file is kept"
    assert "shape/README.md" in split, "and the shape's copy is beside it"
    assert git("show", f"{SPLIT_BRANCH}:shape/notes.md",
               cwd=source).stdout == OWN_NOTES


@needs_filter_repo
@pytest.mark.parametrize("tree, kept", [
    pytest.param(with_files({"shape/README.md": OWN_NOTES}), "shape",
                 id="shape-dir"),
    pytest.param(with_files({"contracts": "a plain file\n"}, "contracts"),
                 "contracts", id="contracts-file"),
])
def test_the_remediation_adopts_end_to_end(tmp_path, tree, kept):
    """What the finding says to do, done: the entry sent to a leg, and
    `execute` adopts, with every source path accounted for."""
    source, plan = kept_source(tmp_path, tree, kept, leg="code")
    assert check(plan).returncode == 0
    result = executed(plan, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "adoption verified" in result.stdout


# --- the materializer's own refusal, for a caller that skipped `check` -------

def template_values() -> dict:
    template = REPO / "templates" / "assembly-root"
    return {name[2:-2]: "x" for path in template.rglob("*") if path.is_file()
            for name in PLACEHOLDER_RE.findall(path.read_text(UTF8))}


def in_the_way(target: Path, actual: str):
    """`copy_in_the_way`, looked up when asked, so that a checkout without
    it fails these tests one by one and not the whole module."""
    return shape_materialize.copy_in_the_way(target, actual)


def materialized_beside(tmp_path: Path, files: dict) -> Path:
    """An assembly root holding `files`, as a clone of the source would."""
    target = tmp_path / "assembly"
    for name, body in files.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding=UTF8)
    return target


def test_a_free_way_is_free(tmp_path):
    target = materialized_beside(tmp_path, {"README.md": "# Thing\n"})
    assert in_the_way(target, "shape/README.md") is None
    assert in_the_way(
        target, "shape/.github/workflows/validate.yml") is None


@pytest.mark.parametrize("files, actual, said", [
    pytest.param({"shape/README.md": OWN_NOTES}, "shape/README.md",
                 "`shape/README.md` is already there",
                 id="a-file-at-the-copy"),
    pytest.param({"shape/Makefile/notes.md": "x\n"}, "shape/Makefile",
                 "`shape/Makefile` is already there, a directory",
                 id="a-directory-at-the-copy"),
    pytest.param({"shape": "a file\n"}, "shape/README.md",
                 "`shape` is not a directory", id="a-file-named-shape"),
    pytest.param({"shape/.github": "a file\n"},
                 "shape/.github/workflows/validate.yml",
                 "`shape/.github` is not a directory",
                 id="a-file-on-the-way-down"),
])
def test_what_stands_where_the_copy_goes_is_named(tmp_path, files, actual,
                                                  said):
    target = materialized_beside(tmp_path, files)
    assert in_the_way(target, actual) == said


@needs_disk_symlinks
def test_a_symlink_to_nowhere_is_in_the_way_and_one_to_a_directory_is_not(
        tmp_path):
    """A dangling link is written THROUGH, landing a file where nothing was
    meant; a link to a directory on the way is walked, as `mkdir` walks it."""
    target = materialized_beside(tmp_path, {"README.md": "# Thing\n",
                                            "elsewhere/keep": "x\n"})
    (target / "shape").symlink_to("elsewhere", target_is_directory=True)
    assert in_the_way(target, "shape/README.md") is None
    (target / "shape").unlink()
    (target / "shape").symlink_to("nowhere")
    assert in_the_way(target, "shape/README.md") == \
        "`shape` is not a directory"
    (target / "shape").unlink()
    (target / "shape").mkdir()
    (target / "shape" / "README.md").symlink_to("nowhere")
    assert in_the_way(target, "shape/README.md") == \
        "`shape/README.md` is already there"


@pytest.mark.parametrize("files, said, kept", [
    pytest.param({"README.md": "# Thing\n", "shape/README.md": OWN_NOTES},
                 "`shape/README.md` is already there", "shape/README.md",
                 id="a-file-at-the-copy"),
    pytest.param({"Makefile": "all:\n", "shape/Makefile/notes.md": "x\n"},
                 "`shape/Makefile` is already there, a directory",
                 "shape/Makefile/notes.md", id="a-directory-at-the-copy"),
    pytest.param({"README.md": "# Thing\n", "shape": "a file\n"},
                 "`shape` is not a directory", "shape",
                 id="a-file-named-shape"),
])
def test_the_materializer_never_writes_a_copy_over_what_is_there(
        tmp_path, files, said, kept):
    """The source's own `shape/README.md` was overwritten by the shape's, on
    the line after `execute` said nothing was: the materializer refuses
    instead, and what was there is what it was."""
    target = materialized_beside(tmp_path, files)
    before = (target / kept).read_bytes()
    with pytest.raises(Refusal) as caught:
        materialize_assembly_root(REPO, target, template_values(),
                                  collision_dir="shape")
    assert caught.value.code == BLOCKED
    assert said in caught.value.detail
    assert "and nothing was written there" in caught.value.detail
    assert "plan-root-blocks-shape-copy" in caught.value.remediation
    assert "an empty `--work-dir`" in caught.value.remediation
    assert (target / kept).read_bytes() == before


def test_the_materializer_names_a_bad_link_at_the_copy_by_its_own_finding(
        tmp_path):
    """#979 left a link at the copy whose target `plan-empty-symlink` or
    `plan-bad-symlink-target` names out of `plan-root-blocks-shape-copy`
    (#1089, N4). The materializer's refusal and `copy_in_the_way`'s docstring
    still said `check` reports a path kept at the copy as that finding alone,
    and for a caller that skipped `check` they now say what names such a
    link, and what helps it: `drop` does not."""
    target = materialized_beside(tmp_path, {"README.md": "# Thing\n",
                                            "shape/README.md": OWN_NOTES})
    with pytest.raises(Refusal) as caught:
        materialize_assembly_root(REPO, target, template_values(),
                                  collision_dir="shape")
    remediation = " ".join(caught.value.remediation.split())
    for said in (
            f"reports a plan that does as `{COPY_IN_THE_WAY}`, before any "
            "leg exists, except a symlink there whose target "
            "`plan-empty-symlink` or `plan-bad-symlink-target` names: that "
            "finding names it, once.",
            "for such a symlink give it a target of its own in the source, "
            "or remove it there, and re-run `plan`, since no answer in the "
            "plan changes a target."):
        assert said in remediation
    doc = " ".join(shape_materialize.copy_in_the_way.__doc__.split())
    assert (f"(`{COPY_IN_THE_WAY}`; a symlink there whose target "
            "`plan-empty-symlink` or `plan-bad-symlink-target` names is "
            "that finding's alone, #979)") in doc


def test_the_materializer_still_writes_a_copy_where_the_way_is_free(tmp_path):
    """The refusal is for a taken copy only: the collision it handled before
    is still written beside the file the source keeps."""
    target = materialized_beside(tmp_path, {"README.md": "# Thing\n"})
    materialized = materialize_assembly_root(REPO, target, template_values(),
                                             collision_dir="shape")
    assert materialized.collisions == [("README.md", "shape/README.md")]
    assert (target / "README.md").read_text(UTF8) == "# Thing\n"
    assert (target / "shape" / "README.md").is_file()


def refused_in_the_materializer(adopter, monkeypatch, capsys,
                                tmp_path: Path, plan: Path):
    """The `Refusal` the materializer raised in an in-process `execute` of
    `plan`.

    It does not escape `execute`. Both legs are pushed by the time the
    materializer runs, so it is reported the way every failure is once a leg
    repository exists (#188): the refusal's own code, detail and
    remediation, under the step that raised it, then the notice of what the
    run left. `execute` then exits 2, as `main` would have for the refusal.
    So the materializer is asked what it raised, and the report is checked
    to say exactly that."""
    raised = []
    materialize = adopter.materialize_assembly_root

    def recorded(*args, **kwargs):
        try:
            return materialize(*args, **kwargs)
        except adopter.Refusal as exc:
            raised.append(exc)
            raise

    monkeypatch.setattr(adopter, "materialize_assembly_root", recorded)
    assert adopter.cmd_execute(execute_args(tmp_path, plan)) == 2
    assert len(raised) == 1, "the materializer wrote the copy"
    refusal = raised[0]
    err = capsys.readouterr().err
    assert (f"REFUSED committing the split. {refusal.code}: "
            f"{refusal.detail}\n{refusal.remediation}\n") in err
    assert err.rstrip().splitlines()[-1].startswith(
        "NOTHING has been rolled back: "), err
    return refusal


@needs_filter_repo
def test_with_check_skipped_execute_stops_at_the_copy_and_overwrites_nothing(
        adopter, monkeypatch, capsys, tmp_path):
    """On main this run pushed a split with the shape's README at the
    source's own `shape/README.md`, said `nothing was overwritten`, and ended
    `adopt-lost`. With the finding switched off for one in-process `execute`,
    so that the run reaches the materializer, it stops there in the
    materializer's words, pushes no split branch, and the source's file is
    what it was. The legs exist by then, which is why `check` finds this
    first, and why the refusal is reported with the notice of what the run
    left (`refused_in_the_materializer`)."""
    monkeypatch.setattr(adopter, "_root_shape_findings",
                        lambda plan, tree, *_: [])
    source, plan = kept_source(tmp_path,
                               with_files({"shape/README.md": OWN_NOTES}),
                               "shape")
    refusal = refused_in_the_materializer(adopter, monkeypatch, capsys,
                                          tmp_path, plan)
    assert refusal.code == BLOCKED
    assert refusal.detail.startswith(
        "the shape's copy of `README.md` cannot be written to "
        "`shape/README.md`: `shape/README.md` is already there")
    assert git("branch", "--list", SPLIT_BRANCH, cwd=source).stdout == ""
    assert git("show", "main:shape/README.md", cwd=source).stdout == OWN_NOTES
    for role in ROLES:
        git("rev-parse", "--verify", "-q", "refs/heads/main",
            cwd=tmp_path / REMOTES / f"{PROJECT}-{role}.git")
