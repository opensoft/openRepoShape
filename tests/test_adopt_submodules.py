# SPDX-License-Identifier: Apache-2.0
"""Adoption preserves an existing dependency through the nested leg mount.

All repositories and remotes are local fixtures; no network is used.
"""

from __future__ import annotations

import builtins
import contextlib
import importlib.util
import io
import re
import shutil
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import (ADOPT, FILE_PROTOCOL, REPO, git, make_source_repo,
                      resolve, run_script, write_plan)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml  # noqa: E402


#: What the end-to-end test needs and the mount tests below do not: they call
#: `_mount_the_legs` on hand-made repositories, so they run on a machine with
#: no `git filter-repo` (the Windows CI job installs none).
needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")


def adopt(command: str, plan: Path, *args: str):
    """`adopt-project.py <command> --plan <plan> [args]`."""
    return run_script(ADOPT, command, "--plan", str(plan), *args)


def add_submodule(source: Path, dependency: Path, path: str) -> None:
    """`git submodule add` of the local `dependency` at `path`, as a person
    adding a dependency to `source` would."""
    git(*FILE_PROTOCOL, "submodule", "add", "-q", str(dependency), path,
        cwd=source)


def commit_as_source_human(source: Path, message: str) -> None:
    git("-c", "user.name=Source Human", "-c",
        "user.email=source@invalid.example", "commit", "-qm", message,
        cwd=source)


@needs_filter_repo
@pytest.mark.parametrize("dependency_leg", ["code", "spec"])
def test_adopt_moves_existing_gitmodules_with_its_dependency(tmp_path,
                                                            dependency_leg):
    dependency = make_source_repo(
        tmp_path / "dependency", tree={"value.txt": "first\n"},
        edits=(("value.txt", "second\n", "Update dependency"),))
    dependency_remote = tmp_path / "dependency.git"
    git("clone", "-q", "--bare", str(dependency), str(dependency_remote),
        cwd=tmp_path)
    source = make_source_repo(tmp_path / "Thing")
    add_submodule(source, dependency_remote, "upstream/dependency")
    commit_as_source_human(source, "Pin existing dependency")
    source_head = git("rev-parse", "HEAD", cwd=source).stdout.strip()
    original_modules = git("rev-parse", "HEAD:.gitmodules",
                           cwd=source).stdout.strip()
    dependency_head = git("rev-parse", "HEAD:upstream/dependency",
                          cwd=source).stdout.strip()
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan)
    assert written.returncode == 0, written.stderr + written.stdout
    for path, leg in (("examples/", "spec"), (".claude/", "root"),
                      ("release.yaml", "root"),
                      (".gitmodules", dependency_leg),
                      ("upstream/", dependency_leg)):
        resolve(plan, path, leg)
    checked = adopt("check", plan)
    assert checked.returncode == 0, checked.stderr + checked.stdout
    result = adopt("execute", plan, "--yes",
                   "--local-remote-dir", str(tmp_path / REMOTES),
                   "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 0, result.stderr + result.stdout

    clone = tmp_path / "assembly"
    git(*FILE_PROTOCOL, "clone", "-q", "--recurse-submodules", "-b",
        "adopt/three-repo-shape", str(source), str(clone), cwd=tmp_path)
    leg = clone / dependency_leg
    assert git("rev-parse", "HEAD:.gitmodules", cwd=leg).stdout.strip() \
        == original_modules
    assert git("rev-parse", "HEAD:upstream/dependency",
               cwd=leg).stdout.strip() == dependency_head
    assert git("ls-tree", "HEAD", "--", "upstream/dependency",
               cwd=leg).stdout.startswith("160000 commit ")
    assert git("rev-parse", "HEAD", cwd=leg / "upstream/dependency") \
        .stdout.strip() == dependency_head
    assert (leg / "upstream/dependency/value.txt").read_text() == "second\n"
    assert "Pin existing dependency" in git(
        "log", "--format=%s", "--", ".gitmodules", cwd=leg).stdout
    root_modules = git("config", "-f", ".gitmodules", "--get-regexp",
                       r"^submodule\..*\.path$", cwd=clone).stdout.splitlines()
    assert sorted(root_modules) == ["submodule.code.path code",
                                    "submodule.spec.path spec"]
    assert git("rev-parse", "HEAD", cwd=source).stdout.strip() == source_head
    assert git("status", "--porcelain", cwd=source).stdout == ""

    # The generated assembly still satisfies the standard's contracts.
    for validator, args in (("validate-repository-naming.py",
                             ("--project", "project.yaml")),
                            ("validate-manifest.py", ()),
                            ("validate-pins.py", ())):
        checked = run_script(clone / "scripts" / validator, *args, cwd=clone)
        assert checked.returncode == 0, checked.stderr + checked.stdout
    pin = load_yaml(clone / "contracts/shape-pin.yaml")
    assert pin["commit"] == git("rev-parse", "HEAD", cwd=REPO) \
        .stdout.strip()
    bootstrapped = run_script(clone / "scripts/bootstrap.py", cwd=clone)
    assert bootstrapped.returncode == 0, bootstrapped.stderr + bootstrapped.stdout
    assert git("rev-parse", "HEAD", cwd=leg / "upstream/dependency") \
        .stdout.strip() == dependency_head


#: The common `.gitignore` that hides every dot-file but itself, and so hides
#: `.gitmodules` from a plain `git add`.
IGNORE_DOTFILES = ".*\n!.gitignore\n"

#: What the assembly root registers once both legs are mounted, whatever else
#: it kept.
LEG_REGISTRATIONS = ["submodule.code.path code", "submodule.spec.path spec"]


def registrations(assembly: Path) -> list[str]:
    """Every `submodule.<name>.path <path>` line of the assembly's file."""
    return sorted(git("config", "-f", ".gitmodules", "--get-regexp",
                      r"^submodule\..*\.path$", cwd=assembly)
                  .stdout.splitlines())


def clone_assembly(source: Path, tmp_path: Path) -> Path:
    """The assembly root `execute` starts from: a plain clone of the source."""
    assembly = tmp_path / "assembly"
    git("clone", "-q", str(source), str(assembly), cwd=tmp_path)
    return assembly


@pytest.fixture
def mount_world(tmp_path):
    """A factory for the real Git mount boundary: `build(registered, tree)`.

    `registered` are the paths the source registers a dependency at, in one
    commit after `tree` (the default source tree when None); the two legs are
    ready in `work`. No `git filter-repo` is involved.
    """
    module_spec = importlib.util.spec_from_file_location("adopt_submodules",
                                                         ADOPT)
    adopter = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(adopter)

    def build(registered=("upstream/kept", "upstream/moved"), tree=None):
        dependency = make_source_repo(tmp_path / "dependency",
                                      tree={"value.txt": "dependency\n"},
                                      edits=())
        source = make_source_repo(tmp_path / "source", tree=tree)
        for path in registered:
            add_submodule(source, dependency, path)
        if registered:
            commit_as_source_human(source, REGISTER)
        work = tmp_path / "work"
        work.mkdir()
        names = {role: f"Northwind-{role}" for role in ("spec", "code")}
        for role in names:
            make_source_repo(work / names[role], tree={"file.txt": role},
                             edits=())
        urls = {role: str(work / names[role]) for role in names}
        return adopter, source, work, names, urls

    return build


@pytest.fixture
def mount_fixture(mount_world):
    """Two registrations in the source: one left in the assembly, one moved.
    Since #166 a plan cannot leave one there; the mount is driven directly."""
    return mount_world()


def test_mount_preserves_registration_kept_in_assembly(mount_fixture,
                                                       tmp_path):
    """MOUNT DEFENCE IN DEPTH, for a plan `check` and `execute` now refuse.

    #166 ruled that the assembly root keeps no submodule of the source's:
    `.gitmodules` and `upstream/kept` left in the root are `plan-submodule-
    root` findings and an `execute` refusal before the mount is reached, and
    #168 refuses every other finding of `check` there too. Should such a
    plan slip past both, the mount still appends its two legs to the
    registrations it finds rather than replacing them.
    """
    adopter, source, work, names, urls = mount_fixture
    assembly = clone_assembly(source, tmp_path)
    kept = git("rev-parse", "HEAD:upstream/kept", cwd=source).stdout.strip()
    adopter._mount_the_legs(
        assembly, work, names, urls,
        {"spec": [], "code": ["upstream/moved"], "drop": []}, "spec", "code")
    assert registrations(assembly) == [
        "submodule.code.path code", "submodule.spec.path spec",
        "submodule.upstream/kept.path upstream/kept"]
    assert git("rev-parse", ":upstream/kept", cwd=assembly).stdout.strip() \
        == kept
    url = git("config", "-f", ".gitmodules", "--get",
              "submodule.upstream/kept.url", cwd=assembly).stdout.strip()
    # A Path comparison: Git writes forward slashes, Windows backslashes.
    assert Path(url) == source.parent / "dependency"


def test_failed_mount_does_not_poison_a_fresh_clone(mount_fixture, tmp_path):
    adopter, source, work, names, urls = mount_fixture
    paths = {"spec": [], "code": [".gitmodules", "upstream/"], "drop": []}
    failed = tmp_path / "failed-assembly"
    git("clone", "-q", str(source), str(failed), cwd=tmp_path)
    unavailable = {**names, "code": "missing-code"}
    # The spec mount must succeed, so that the failure is the code leg's and
    # not a refusal to write into a `.gitmodules` that is going away.
    with pytest.raises(adopter.CommandFailed, match="missing-code"):
        adopter._mount_the_legs(failed, work, unavailable, urls,
                                paths, "spec", "code")

    fresh = tmp_path / "fresh-assembly"
    git("clone", "-q", str(source), str(fresh), cwd=tmp_path)
    adopter._mount_the_legs(fresh, work, names, urls, paths, "spec", "code")
    for role in names:
        assert (fresh / role / "file.txt").read_text() == role


@pytest.mark.parametrize("registered, moved", [
    ((), []),
    (("upstream/moved",), [".gitmodules", "upstream/"]),
], ids=["source-has-no-submodules", "source-registry-moved-to-a-leg"])
def test_mount_stages_gitmodules_past_a_gitignore_that_hides_it(
        mount_world, tmp_path, registered, moved):
    """`.*` + `!.gitignore` must not break the mount (the common source).

    A source with no submodules never had a `.gitmodules`, so the mount has
    none to replace and `git submodule add` writes its own; a source whose
    file the plan moved gets a fresh one, staged with `-f`.
    """
    tree = {README: "# Thing\n", ".gitignore": IGNORE_DOTFILES,
            "src/app.py": "VALUE = 1\n"}
    adopter, source, work, names, urls = mount_world(registered, tree)
    assert git("check-ignore", "-q", "--no-index", ".gitmodules",
               cwd=source, check=False).returncode == 0
    assembly = clone_assembly(source, tmp_path)
    adopter._mount_the_legs(assembly, work, names, urls,
                            {"spec": [], "code": moved, "drop": []},
                            "spec", "code")
    assert registrations(assembly) == LEG_REGISTRATIONS
    assert git("ls-files", "--", ".gitmodules", cwd=assembly).stdout \
        == ".gitmodules\n"


def test_mount_removes_gitmodules_before_a_submodule_that_sorts_ahead(
        mount_world, tmp_path):
    """`.deps/moved` sorts before `.gitmodules`, and `git rm` of it edits the
    file that registers it: removed in that order, the second `git rm` is
    refused for "changes staged in the index".
    """
    adopter, source, work, names, urls = mount_world((".deps/moved",))
    assembly = clone_assembly(source, tmp_path)
    adopter._mount_the_legs(
        assembly, work, names, urls,
        {"spec": [], "code": [".gitmodules", ".deps/"], "drop": []},
        "spec", "code")
    assert registrations(assembly) == LEG_REGISTRATIONS
    assert git("ls-files", "--", ".deps", cwd=assembly).stdout == ""


# --- the plan's own answer: one leg for a submodule and its registration ----
#
# #166. `check` and `execute` read the SAME list of findings, so `execute`
# refuses every submodule problem `check` finds beside every other one (#168),
# and `plan` asks the question on every entry that holds a submodule, so it
# never proposes what `check` refuses. `check` reads the source's
# `.gitmodules` as git's own submodule reader will read it in the leg. None
# of these needs `git filter-repo` but the ones that reach `execute` past its
# preflight.

#: The ids, as `check` prints them and `execute` raises them.
SPLIT = "plan-submodule-split"
ROOT = "plan-submodule-root"
UNREGISTERED = "plan-submodule-unregistered"
UNREADABLE = "plan-gitmodules-unreadable"
SUBMODULE_CODES = (ROOT, UNREADABLE, UNREGISTERED, SPLIT)
#: `check`'s own ids for an entry it rejects before asking about submodules.
UNRESOLVED = "plan-unresolved"
UNCOVERED = "plan-uncovered"
BAD_LEG = "plan-bad-leg"

#: The plan entries these sources ask about, and the file every plan below is
#: written to, each in a directory of its own.
GITMODULES = ".gitmodules"
UPSTREAM = "upstream/"
EXTRA = "extra/"
PLAN_FILE = "adoption-plan.yaml"
#: The submodule most of these sources register, under UPSTREAM, and the
#: one file in the repository it is a commit of.
DEPENDENCY = "upstream/dependency"
DEPENDENCY_TREE = {"value.txt": "dependency\n"}
#: Stands, in a hand-written `.gitmodules`, for the dependency's absolute
#: path, which `registered_source` knows only once it has made it: the url a
#: leg's own clone can follow, where `../dependency` is relative to the leg.
THE_DEPENDENCY = "<the dependency>"


def registration(name: str = DEPENDENCY, url: str = "../dependency") -> str:
    """`DEPENDENCY` registered by hand, under `name`, with `url`."""
    return f'[submodule "{name}"]\n\tpath = {DEPENDENCY}\n\turl = {url}\n'


#: The submodule #166's N3 found unasked, under a directory its rule calls
#: code, and a file a directory holding a submodule may hold beside it.
VENDORED = "src/vendored"
DOCS_INDEX = "docs/index.md"
#: The paths the questions below name, each in more than two of them.
APP = "src/app/"
DOCS = "docs/"
THEME_README = "docs/theme/README.md"
THEME_SUB = "docs/theme/sub"
README = "README.md"
#: A later section that gives `registration()`'s path to a name with no url.
SHADOWING = '[submodule "b"]\n\tpath = upstream/dependency\n'
#: The commit a source registers its dependencies in.
REGISTER = "Register dependencies"
#: Where `execute` makes the legs' bare remotes, under a test's own directory.
REMOTES = "remotes"
#: A section that moves `registration()`'s name to another path.
MOVED_ELSEWHERE = '[submodule "upstream/dependency"]\n\tpath = elsewhere\n'

#: What the assembly root's `.gitmodules` is, in the `plan-submodule-root`
#: detail and in the remediation: true whether or not `.gitmodules` is the
#: entry answered `root`, which "`execute` writes it a fresh one" was not.
RESERVED = "is reserved for its two leg mounts"

#: A source whose plan asks nothing but the submodule's questions: `specs/`
#: and `src/` classify themselves and `README.md` stays in the root.
SMALL_TREE = {README: "# Thing\n", "src/app/util.py": "VALUE = 1\n",
              "specs/001-feature/tasks.md": "- [ ] one\n"}

# The sources these tests answer plans for, as `registered_source`
# arguments: a test names the one it answers, and `plan_of` plans each once.

#: `upstream/dependency`, registered with a url:
REGISTERED = {}
#: `upstream/orphan`, and no `.gitmodules` at all:
LONE_ORPHAN = {"registered": (), "orphan": "upstream/orphan"}
#: `upstream/dependency` registered, and `extra/orphan` beside it not:
BESIDE = {"orphan": "extra/orphan"}
#: `upstream/dependency`, beside a `.gitmodules` with a bad config line:
UNREADABLE_FILE = {"gitmodules": '[submodule "upstream/dependency"\n'
                                 "\tpath = upstream/dependency\n"}
#: `d0/s0` to `d9/s9` registered, and `extra/orphan` beside them not:
CROWDED = {**BESIDE, "registered": tuple(f"d{i}/s{i}" for i in range(10))}
#: `upstream/dependency` and `extra/second`, both registered:
TWO = {"registered": (DEPENDENCY, "extra/second")}
#: `dep`, registered at the top level, so it is a plan entry of its own:
TOP = {"registered": ("dep",)}
#: A `.gitmodules` registering a submodule the tree no longer holds, and no
#: gitlink anywhere:
STALE = {"registered": (), "gitmodules": '[submodule "gone"]\n'
                                         "\tpath = gone\n\turl = ../gone\n"}


def registered_source(base: Path, registered=(DEPENDENCY,),
                      orphan: str | None = None,
                      gitmodules: str | bytes | None = None,
                      extra: dict | None = None) -> Path:
    """A source registering a real dependency at each of `registered`.

    `orphan` adds a gitlink at that path with NO registration, written
    straight into the index as `git add` of an embedded clone would write it,
    so that a source with a submodule and no `.gitmodules` is planned too.
    `gitmodules`, when given, replaces the file `git submodule add` wrote, as
    a hand edit would: written as BYTES, LF on every platform, so that a byte
    no encoding gives is written as it is, and with THE_DEPENDENCY replaced
    by the dependency's path. `extra` adds files to SMALL_TREE.
    """
    dependency = make_source_repo(base / "dependency", tree=DEPENDENCY_TREE,
                                  edits=())
    source = make_source_repo(base / "Thing",
                              tree={**SMALL_TREE, **(extra or {})})
    for path in registered:
        add_submodule(source, dependency, path)
    if orphan:
        head = git("rev-parse", "HEAD", cwd=dependency).stdout.strip()
        git("update-index", "--add", "--cacheinfo", f"160000,{head},{orphan}",
            cwd=source)
    if gitmodules is not None:
        raw = gitmodules if isinstance(gitmodules, bytes) \
            else gitmodules.encode()
        (source / GITMODULES).write_bytes(raw.replace(
            THE_DEPENDENCY.encode(), dependency.as_posix().encode()))
        git("add", "--", GITMODULES, cwd=source)
    commit_as_source_human(source, REGISTER)
    return source


def planned(source: Path, base: Path):
    """`(plan, completed)`: `plan` run on `source`, into a directory of its
    own under `base`."""
    plan = base / "plan" / PLAN_FILE
    plan.parent.mkdir()
    written = write_plan(source, plan)
    assert written.returncode == 0, written.stderr + written.stdout
    return plan, written


@pytest.fixture(scope="module")
def plan_of(tmp_path_factory):
    """`plan_of(SOURCE)`: `planned` for one of the sources above, built once
    per module. The source is only ever read, and each test answers a COPY
    of its plan."""
    made: dict[str, tuple] = {}

    def build(source: dict):
        key = repr(sorted(source.items()))
        if key not in made:
            base = tmp_path_factory.mktemp("source")
            made[key] = planned(registered_source(base, **source), base)
        return made[key]

    return build


def answered(plan: Path, tmp_path: Path, answers: dict) -> Path:
    """A copy of `plan` with each `{path: leg}` in `answers` resolved; a leg
    of None leaves that entry's question unanswered."""
    copy = tmp_path / PLAN_FILE
    shutil.copyfile(plan, copy)
    for path, leg in answers.items():
        if leg is not None:
            resolve(copy, path, leg)
    return copy


def plan_rows(plan: Path) -> dict:
    """`{path: entry}` for every entry of the plan file."""
    return {str(row["path"]): row for row in load_yaml(plan)["paths"]}


def check_plan(plan: Path):
    return adopt("check", plan)


def edited(plan: Path, removed: str | None, added: dict) -> None:
    """`plan` with the entry for `removed` deleted, and an entry `path: leg`
    for each of `added` put first, as a hand edit would leave it -- a careless
    one, or one that splits an entry. Bytes, because `plan` writes LF on
    every platform, and `conftest.resolve` keeps it so: an entry is found
    by its LF-ended lines."""
    lines = plan.read_bytes().splitlines(keepends=True)
    if removed:
        start = lines.index(f"  - path: {removed}\n".encode())
        end = start + 1
        while lines[end].startswith(b"    "):
            end += 1
        del lines[start:end]
    first = lines.index(b"paths:\n") + 1
    lines[first:first] = [f"  - path: {path}\n    leg: {leg}\n".encode()
                          for path, leg in added.items()]
    plan.write_bytes(b"".join(lines))


def findings(stderr: str) -> list[tuple[str, str]]:
    """`(code, detail)` for each `FINDING <code>: <detail>` line `check`
    printed, in its order."""
    return [tuple(line.split(" ", 1)[1].split(": ", 1))
            for line in stderr.splitlines() if line.startswith("FINDING ")]


def finding_codes(stderr: str) -> list[str]:
    return [code for code, _ in findings(stderr)]


@contextlib.contextmanager
def windows_text_mode():
    """Text mode as Windows has it: a file opened for writing as text, with
    no `newline=` named, gets CRLF for every `\\n` it is given. Only the
    Windows job ever saw that, so it is put here where every platform does.
    A context and not a fixture, so that it covers the one call it is for:
    `plan_of` caches what it builds for the whole module."""
    real_open = io.open

    def open_as_windows(file, mode="r", buffering=-1, encoding=None,
                        errors=None, newline=None, *rest, **named):
        if newline is None and "b" not in mode and set(mode) & set("wax+"):
            newline = "\r\n"
        return real_open(file, mode, buffering, encoding, errors, newline,
                         *rest, **named)

    # `Path.write_text` opens through `io.open`; a bare `open` is `builtins`'.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(io, "open", open_as_windows)
        patch.setattr(builtins, "open", open_as_windows)
        yield


def test_a_plan_answered_where_text_mode_writes_crlf_is_still_edited(
        plan_of, tmp_path):
    """PR #194's `tests-windows`, ten failures: `conftest.resolve` wrote the
    answered plan with `Path.write_text`, which on Windows turns every LF
    into CRLF, and `edited` -- which reads the LF `plan` writes on every
    platform -- found neither `paths:` nor `  - path: <entry>` in it."""
    asked = plan_of(REGISTERED)[0]
    with windows_text_mode():
        plan = answered(asked, tmp_path,
                        {GITMODULES: "code", UPSTREAM: "code"})
    assert b"\r" not in plan.read_bytes()
    edited(plan, UPSTREAM, {DEPENDENCY: "spec"})
    rows = plan_rows(plan)
    assert UPSTREAM not in rows
    assert rows[DEPENDENCY]["leg"] == "spec"


def test_plan_asks_the_submodule_question_on_gitmodules(plan_of):
    plan, written = plan_of(REGISTERED)
    row = plan_rows(plan)[GITMODULES]
    question = row["question"]
    assert row["leg"] is None
    assert row["review_required"] is True
    assert row["rule"] == "ambiguous-gitmodules"
    # #166's sentence, framed so that it is also true where
    # `shape-doctor.py --placement-plan` prints it, for a leg already split.
    assert question.startswith(
        "When a repository is adopted, a source's own `.gitmodules` goes to "
        "the SAME leg as every submodule it registers; `execute` writes the "
        "assembly root a fresh one for its two mounts.")
    assert ("A submodule it does not register with a path and a url cannot "
            "be kept in a leg at all") in question
    # No stricter than the rule: one submodule may be dropped by itself.
    assert ("Any one submodule may also be dropped on its own; its "
            "registration stays behind in that leg, inert.") in question
    # `shape-doctor.py --placement-plan` prints this question too, for a file
    # no `check` or `execute` ever reads: the TOOL refuses, true in both.
    assert ("`root` is not an answer for this file or for any submodule, and "
            "`adopt-project.py` refuses a plan that gives it") in question
    # Printed for an EMPTY `.gitmodules` too, so it claims no registration.
    assert row["reason"].startswith(
        "`.gitmodules` is where a repository registers its submodules.")
    # Printed with the other unresolved paths, which is where it is read.
    assert "goes to the SAME leg as every submodule" in written.stdout


@pytest.mark.parametrize("gitlinks, extra, entry, rule, own", [
    # The 2026-09-02 ruling roots `.specify/` and the assistant directories,
    # and still roots their FILES; a SUBMODULE there is asked instead.
    ((".specify/vendored",), {".specify/memory/constitution.md": "# c\n"},
     ".specify/", "root-spec-kit", (".specify/memory/", ".specify/vendored")),
    ((".cursor",), {}, ".cursor", "root-assistant-instructions", ()),
    # Asked already, but whether it is root: `.gitmodules`' question instead.
    ((".agents",), {}, ".agents", "ambiguous-assistant-project-memory", ()),
    (("docs/theme",), {DOCS_INDEX: "# Docs\n"}, DOCS,
     "spec-governance", (DOCS_INDEX, "docs/theme")),
    ((DEPENDENCY,), {}, UPSTREAM, "default", ()),
    # Nothing but submodules, and still split, to drop one on its own.
    (("vendor/a", "vendor/b"), {}, "vendor/", "default",
     ("vendor/a", "vendor/b")),
    # Under a rule that would have called it code, unasked (#166's N3).
    ((VENDORED,), {}, "src/", "code-source-and-tests",
     (APP, VENDORED)),
    # Deeper than one level: only the directory holding it is opened.
    ((THEME_SUB,), {DOCS_INDEX: "# Docs\n", THEME_README: "# Theme\n"},
     DOCS, "spec-governance", (DOCS_INDEX, THEME_README, THEME_SUB)),
], ids=["specify-vendored", "cursor", "agents", "docs-theme", "upstream",
        "two-in-one-entry", "src-vendored", "nested"])
def test_plan_asks_on_every_entry_that_holds_a_submodule(
        plan_of, tmp_path, gitlinks, extra, entry, rule, own):
    """`plan` never proposes what `check` refuses: the entry covering a
    gitlink is asked `.gitmodules`' question, whatever rule matched it, and
    names its submodules and, when it holds more than one path, the `own`
    entries that replace it so that each submodule is answered on its own;
    the untouched plan is then UNRESOLVED there, never a submodule kept in
    the root."""
    plan = plan_of({"registered": gitlinks, "extra": extra})[0]
    rows = plan_rows(plan)
    row = rows[entry]
    # Everything `.gitmodules` is asked -- `leg: null`, `review_required`,
    # its rule, reason and question -- and only its own size besides.
    expected = {**rows[GITMODULES], "path": entry, "files": row["files"],
                "bytes": row["bytes"]}
    expected["question"] += (
        " This entry holds the submodule(s) "
        + ", ".join(f"`{path}`" for path in gitlinks)
        + f": it is asked this question, not classified by its rule `{rule}`.")
    if own:
        expected["question"] += (
            " Split the entry if its paths do not all belong in one leg: "
            "replace it with an entry for each of "
            + ", ".join(f"`{path}`" for path in own)
            + ", each with its own `leg:`. An entry added beside this one "
            "for a path it covers is `plan-covered-twice`.")
    assert row == expected
    assert (row["leg"], row["rule"]) == (None, "ambiguous-gitmodules")
    result = check_plan(answered(plan, tmp_path, {}))
    assert set(finding_codes(result.stderr)) == {UNRESOLVED}, result.stderr
    assert f"FINDING {UNRESOLVED}: {entry} still has" in result.stderr


@pytest.mark.parametrize("modules_leg, dependency_leg, expected", [
    ("code", "code", []),
    ("spec", "spec", []),
    # A dropped gitlink leaves its registration behind, inert.
    ("code", "drop", []),
    ("drop", "drop", []),
    ("code", "spec", [SPLIT]),
    ("drop", "code", [SPLIT]),
    ("root", "root", [ROOT, ROOT]),
    ("spec", "root", [ROOT]),
    ("root", "code", [ROOT, SPLIT]),
    # An unanswered `.gitmodules` is `plan-unresolved`'s, and is not also
    # reported as a split; a gitlink kept in the root is refused regardless.
    (None, "code", [UNRESOLVED]),
    (None, "root", [UNRESOLVED, ROOT]),
])
def test_check_holds_a_submodule_to_the_leg_of_its_registration(
        adopter, plan_of, tmp_path, modules_leg, dependency_leg, expected):
    plan = answered(plan_of(REGISTERED)[0], tmp_path,
                    {GITMODULES: modules_leg, UPSTREAM: dependency_leg})
    result = check_plan(plan)
    assert finding_codes(result.stderr) == expected, result.stderr
    # The remediation, ONCE after the last finding and before the count,
    # when any of them is a submodule problem: `check` says how to fix it.
    told = result.stderr.count(adopter.SUBMODULE_REMEDIATION)
    assert told == (1 if set(expected) & set(SUBMODULE_CODES) else 0)
    if told:
        at = result.stderr.index(adopter.SUBMODULE_REMEDIATION)
        assert result.stderr.rindex("FINDING ") < at \
            < result.stderr.index(" finding(s) in ")
    if not expected:
        assert result.returncode == 0, result.stderr
        assert "plan ok" in result.stdout
        return
    assert result.returncode == 1
    assert f"{len(expected)} finding(s) in {plan}" in result.stderr
    if SPLIT in expected:
        assert (f"FINDING {SPLIT}: the submodule "
                f"upstream/dependency (entry upstream/) has leg: "
                f"{dependency_leg} but the source's .gitmodules has leg: "
                f"{modules_leg}") in result.stderr
    if modules_leg == "root":
        assert (f"FINDING {ROOT}: .gitmodules has leg: root, and the "
                "assembly root keeps no submodule of the source's: its "
                f".gitmodules {RESERVED}") in result.stderr
    if dependency_leg == "root":
        assert (f"FINDING {ROOT}: upstream/dependency (entry upstream/) has "
                "leg: root") in result.stderr


def test_check_finds_a_submodule_a_rule_classified_silently(tmp_path):
    """`tools/dep` is under `tools/**`, which a plan written before #166
    called code without asking; `plan` asks there now. Answered as that rule
    would have it, with `.gitmodules` in spec, the two split, and `check`
    finds it however the plan came to say so."""
    plan = planned(registered_source(tmp_path, registered=("tools/dep",)),
                   tmp_path)[0]
    assert plan_rows(plan)["tools/"]["review_required"] is True
    resolve(plan, "tools/", "code")
    resolve(plan, GITMODULES, "spec")
    result = check_plan(plan)
    assert result.returncode == 1, result.stderr + result.stdout
    assert (f"FINDING {SPLIT}: the submodule tools/dep (entry tools/) has "
            "leg: code but the source's .gitmodules has leg: spec") \
        in result.stderr


#: The entries an asked entry's question names to replace it with.
REPLACE_WITH_RE = re.compile(r"replace it with an entry for each of (.+?), "
                             r"each with its own `leg:`")


def test_the_split_the_question_names_is_the_edit_that_works(tmp_path):
    """#166's N3: `src/vendored`, an orphan, under `src/`, which its rule
    calls code. `check` says to drop it; adding `src/vendored: drop` BESIDE
    `src/` covers it twice, and the edit the entry's question names -- `src/`
    replaced by `src/app/` and `src/vendored` -- is the one `check` passes."""
    plan = planned(registered_source(tmp_path, registered=(),
                                     orphan=VENDORED), tmp_path)[0]
    named = REPLACE_WITH_RE.search(plan_rows(plan)["src/"]["question"])
    own = re.findall(r"`([^`]+)`", named[1])
    assert own == [APP, VENDORED]
    beside = answered(plan, tmp_path, {"src/": "code"})
    edited(beside, None, {VENDORED: "drop"})
    assert finding_codes(check_plan(beside).stderr) == ["plan-covered-twice"]
    split = tmp_path / "split" / PLAN_FILE
    split.parent.mkdir()
    shutil.copyfile(plan, split)
    edited(split, "src/", {path: "drop" if path == VENDORED else "code"
                           for path in own})
    result = check_plan(split)
    assert result.returncode == 0, result.stderr
    assert "plan ok" in result.stdout


def children(source: Path, directory: str) -> list[str]:
    """The plan entries for what is directly in `directory` at HEAD: a
    directory with its slash, anything else as it is."""
    listed = git("ls-tree", "HEAD", "--", directory, cwd=source).stdout
    return [path + "/" if kind == "tree" else path
            for kind, path in (line.split()[1::2]
                               for line in listed.splitlines())]


@pytest.mark.parametrize("gitlink, extra, entry, opened, where", [
    (VENDORED, {f"src/f{i:02}.py": "x\n" for i in range(12)}, "src/",
     ("src/",), "`src/`, 14 in all"),
    # Deeper than one level: each directory on the way is opened.
    (THEME_SUB, {**{f"docs/f{i}.md": "x\n" for i in range(8)},
                 THEME_README: "# Theme\n"}, DOCS, (DOCS, "docs/theme/"),
     "one of `docs/`, `docs/theme/`, other than those directories, "
     "10 in all"),
], ids=["one-directory", "nested"])
def test_a_long_split_is_described_not_listed(adopter, tmp_path, gitlink,
                                              extra, entry, opened, where):
    """#166's R5-2. Past SPLIT_ENTRIES_NAMED the question does not name the
    entries that replace a directory, one by one, on one line of the plan
    and again in `check`'s finding: it says which directories they are the
    paths of and counts them, and that edit is the one `check` passes."""
    source = registered_source(tmp_path, registered=(gitlink,), extra=extra)
    plan = planned(source, tmp_path)[0]
    question = plan_rows(plan)[entry]["question"]
    assert question.endswith(
        " Split the entry if its paths do not all belong in one leg: replace "
        f"it with an entry for each path directly in {where}, each with its "
        "own `leg:`. An entry added beside this one for a path it covers is "
        "`plan-covered-twice`.")
    assert "f00" not in question and "f0." not in question
    own = [path for directory in opened for path in children(source, directory)
           if path not in opened]
    assert len(own) > adopter.SPLIT_ENTRIES_NAMED
    split = answered(plan, tmp_path, {GITMODULES: "code"})
    edited(split, entry, {path: "code" for path in own})
    result = check_plan(split)
    assert result.returncode == 0, result.stderr


#: A harness under `src/` that reads `contracts/`: `plan` names it in a
#: follow-up, and the root Makefile's `CONTRACTS_DIR` in another.
HARNESS = {"contracts/api.yaml": "kind: api\n",
           "src/app/harness.py": "SCHEMA = 'contracts/api.yaml'\n"}


@pytest.mark.parametrize("gitlink, entry", [
    ("src/vendor/dep", "src/"),
    ("contracts/vendor/x", "contracts/"),
])
def test_a_submodule_takes_nothing_from_what_the_rules_imply(tmp_path,
                                                             gitlink, entry):
    """#166's NEW-1. The entry holding the submodule is asked, and what the
    RULES imply about the rest of the source is what it is without one: the
    harness follow-up and the `CONTRACTS_DIR` line, the seeding record, and
    no SEEDED warning. Read after the question, `src/: null` lost the first
    and called the code leg empty, and `contracts/: null` lost both."""
    plain = make_source_repo(tmp_path / "plain",
                             tree={**SMALL_TREE, **HARNESS})
    without = load_yaml(planned(plain, tmp_path)[0])
    held = tmp_path / "held"
    plan, written = planned(registered_source(held, registered=(gitlink,),
                                              extra=HARNESS), held)
    assert plan_rows(plan)[entry]["leg"] is None
    data = load_yaml(plan)
    follow_ups = data["follow_ups"]
    assert follow_ups == without["follow_ups"]
    assert [item.split(" ", 1)[0] for item in follow_ups
            if "`contracts/`" in item or "CONTRACTS_DIR" in item] \
        == ["code/src/app/harness.py", "the"], follow_ups
    assert data["seeding"] == without["seeding"] == {
        "spec": {"seeded_from_template": False},
        "code": {"seeded_from_template": False}}
    assert "will be SEEDED" not in written.stdout


def git_bytes(source: Path, *args: str, stdin: bytes) -> bytes:
    """`git <args>` in `source`, fed and answering BYTES."""
    done = subprocess.run(["git", *args], cwd=source, input=stdin,
                          capture_output=True, check=False)
    if done.returncode:
        # Where git fails outright on a name it will not record, the case
        # cannot be built there, and is not a failure. `update-index` does
        # not fail on one: it ignores it and exits 0, which `raw_source`
        # finds by reading the tree back.
        pytest.skip(f"git {args[0]} refuses it here: {done.stderr!r}")
    return done.stdout


#: Ends a name in `-z` output, and in what `update-index -z` is given.
NUL = b"\x00"


def raw_source(base: Path, gitlink: bytes, beside: bytes | None) -> Path:
    """A source with the submodule `gitlink`, registered, and a file at
    `beside`: names given as BYTES and put straight into the index, as `git
    add` records them, so that a name no UTF-8 file or line can hold is
    built with no filesystem that has to hold it. Skipped where git does not
    keep a name in the tree, which only git can say: `update-index` ignores a
    path it will not record, and exits 0 (on the Windows runner it left out a
    backslash and a newline)."""
    dependency = make_source_repo(base / "dependency", tree=DEPENDENCY_TREE,
                                  edits=())
    source = make_source_repo(base / "raw-source", tree=SMALL_TREE)
    head = git("rev-parse", "HEAD", cwd=dependency).stdout.strip()
    index = b"160000 " + head.encode() + b"\t" + gitlink + NUL
    if beside:
        blob = git_bytes(source, "hash-object", "-w", "--stdin",
                         stdin=b"x\n").strip()
        index += b"100644 " + blob + b"\t" + beside + NUL
    git_bytes(source, "update-index", "-z", "--index-info", stdin=index)
    # Quoted as git config quotes a value: a bare backslash is an escape.
    quoted = gitlink.replace(b"\\", b"\\\\").replace(b'"', b'\\"')
    (source / GITMODULES).write_bytes(
        b'[submodule "dep"]\n\tpath = "' + quoted + b'"\n\turl = '
        + dependency.as_posix().encode() + b"\n")
    git("add", "--", GITMODULES, cwd=source)
    commit_as_source_human(source, REGISTER)
    held = subprocess.run(
        ["git", "ls-tree", "-r", "-z", "--name-only", "HEAD"], cwd=source,
        capture_output=True, check=True).stdout.split(NUL)
    missing = [name for name in (gitlink, beside) if name and name not in held]
    if missing:
        pytest.skip(f"git does not keep {missing!r} in a tree here")
    return source


@pytest.mark.parametrize("gitlink, beside, entry, named", [
    # Not UTF-8: `Source.tree` keeps the byte as a surrogate, which no UTF-8
    # plan can hold.
    (b"upstream/d\xe9p", None, UPSTREAM,
     " This entry holds the submodule(s) `upstream/d\\xe9p`: it is asked"),
    (b"src/vendored", b"src/caf\xe9.py", "src/",
     "an entry for each of `src/app/`, `src/caf\\xe9.py`, `src/vendored`,"),
    # A newline would end the plan's line, and read back as a space.
    (b"src/vendored", b"src/a\nb.py", "src/",
     "an entry for each of `src/a\\nb.py`, `src/app/`, `src/vendored`,"),
    # A backtick, and a backslash, would break the backticks around a name.
    (b"src/ven`d\\or", None, "src/",
     "an entry for each of `src/app/`, `src/ven\\`d\\\\or`,"),
], ids=["non-utf8-submodule", "non-utf8-file-beside", "newline-beside",
        "backtick-and-backslash"])
def test_a_name_no_plan_line_can_hold_is_spelled_in_the_question(
        tmp_path, gitlink, beside, entry, named):
    """#166's NEW-2 and R5-1. A name that is not UTF-8, or that holds a
    newline or a backtick, is SPELLED in the question with a backslash, and
    `plan` writes its plan over the one `--out` held -- where it used to raise
    mid-write and leave that file empty."""
    source = raw_source(tmp_path, gitlink, beside)
    plan = tmp_path / PLAN_FILE
    plan.write_text("a plan answered before this run\n", encoding="utf-8")
    written = write_plan(source, plan)
    assert written.returncode == 0, written.stderr
    assert named in plan_rows(plan)[entry]["question"]


def test_a_newline_spelled_in_the_question_is_the_entry_to_write(tmp_path):
    """The spelling is the entry: `src/a\\nb.py` between double quotes is a
    YAML scalar holding the newline, so the split the question names covers
    the file, where the name read back as `src/a b.py` covered nothing."""
    source = raw_source(tmp_path, b"src/vendored", b"src/a\nb.py")
    plan = planned(source, tmp_path)[0]
    named = REPLACE_WITH_RE.search(plan_rows(plan)["src/"]["question"])
    own = re.findall(r"`([^`]+)`", named[1])
    assert own == ["src/a\\nb.py", APP, VENDORED]
    split = answered(plan, tmp_path, {GITMODULES: "code"})
    edited(split, "src/", {f'"{path}"': "code" for path in own})
    result = check_plan(split)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("gitlink, beside", [
    (b".git/vendored", None),
    (b"src/vendored", b".git/x"),
], ids=["submodule", "file-beside"])
def test_a_source_whose_name_git_will_not_record_is_skipped_not_failed(
        tmp_path, gitlink, beside):
    """PR #194's `tests-windows`, the three name failures: the runner's git
    left a backslash and a newline out of the source's tree, and the question
    never named them. `git update-index --index-info` exits 0 for a path it
    will not record and says `Ignoring path`; every platform does it for a
    `.git` component, which is how Linux runs this. Asked of the tree the
    tool reads, `raw_source` skips that case where it used to fail."""
    with pytest.raises(pytest.skip.Exception,
                       match=r"git does not keep .*\.git/"):
        raw_source(tmp_path, gitlink, beside)


@pytest.mark.parametrize("leg, expected", [
    ("code", [UNREGISTERED]),
    ("spec", [UNREGISTERED]),
    ("drop", []),
    ("root", [ROOT]),
])
def test_an_orphan_gitlink_may_be_dropped_but_not_kept(plan_of, tmp_path,
                                                       leg, expected):
    """No `.gitmodules` at all. The source's own `git clone
    --recurse-submodules` skips a gitlink with no URL; the assembly's
    recurses INTO the leg and dies on it, so a leg is worse than the source
    for it, not "no worse". Dropped, it goes nowhere."""
    plan = answered(plan_of(LONE_ORPHAN)[0], tmp_path, {UPSTREAM: leg})
    assert GITMODULES not in plan_rows(plan)
    result = check_plan(plan)
    assert finding_codes(result.stderr) == expected, result.stderr
    assert result.returncode == (1 if expected else 0)
    if UNREGISTERED in expected:
        assert (f"FINDING {UNREGISTERED}: the submodule upstream/orphan "
                f"(entry upstream/) has leg: {leg} but no .gitmodules entry "
                "in the source registers its path with a url") \
            in result.stderr


@pytest.mark.parametrize("orphan_leg, expected", [
    ("code", [UNREGISTERED]),
    # In the OTHER leg it is still unregistered, and only that: no leg holds
    # a URL for it, so moving `.gitmodules` would not help.
    ("spec", [UNREGISTERED]),
    ("drop", []),
])
def test_check_refuses_to_keep_a_gitlink_its_gitmodules_does_not_register(
        plan_of, tmp_path, orphan_leg, expected):
    plan = answered(plan_of(BESIDE)[0], tmp_path,
                    {GITMODULES: "code", UPSTREAM: "code", EXTRA: orphan_leg})
    result = check_plan(plan)
    assert finding_codes(result.stderr) == expected, result.stderr
    assert result.returncode == (1 if expected else 0)
    if expected:
        assert (f"FINDING {UNREGISTERED}: the submodule extra/orphan (entry "
                f"extra/) has leg: {orphan_leg}") in result.stderr


#: A comment no encoding gives, as a Latin-1 editor writes one: `git config
#: --blob` reads 0xFF as the end of the file.
LATIN_1_COMMENT = b"# caf\xe9 \xff\xfe\n"
#: Upper-case section and keys, which git lower-cases.
UPPER_CASE_KEYS = ('[Submodule "upstream/dependency"]\n'
                   "\tPATH = upstream/dependency\n\tURL = ../dependency\n")


@pytest.mark.parametrize("gitmodules, expected", [
    ('[submodule "upstream/dependency"]\n\tpath = upstream/dependency\n',
     [UNREGISTERED]),
    (registration(url=""), [UNREGISTERED]),
    # git skips a `submodule.path` with no `<name>`, so this does too.
    ("[submodule]\n\tpath = upstream/dependency\n\turl = ../dependency\n",
     [UNREGISTERED]),
    ('[submodule "elsewhere"]\n\tpath = elsewhere/dependency\n'
     "\turl = ../dependency\n", [UNREGISTERED]),
    ("", [UNREGISTERED]),
    # Section and key names are case-insensitive to git, and so here.
    (UPPER_CASE_KEYS, []),
    # git reads the leg's CHECKED-OUT file, where a 0xFF byte is a byte:
    # the registration after one is a registration, and so is an override.
    (LATIN_1_COMMENT + registration().encode(), []),
    (registration().encode() + b"# \xff\n" + MOVED_ELSEWHERE.encode(),
     [UNREGISTERED]),
    # git ignores a name that is empty or has a `..` component, at `/` or
    # `\`, with "ignoring suspicious submodule name"; `a..b` is a name.
    (registration("../escape"), [UNREGISTERED]),
    (registration("a\\\\..\\\\b"), [UNREGISTERED]),
    (registration(""), [UNREGISTERED]),
    (registration("a..b"), []),
    # A `url` or `path` that starts with `-` is ignored, "may be interpreted
    # as a command-line option", and the value before it stands.
    (registration(url="-oops"), [UNREGISTERED]),
    (registration() + "\tpath = -upstream/dependency\n", []),
    # A path belongs to the LAST name given it, url or none.
    (registration() + SHADOWING,
     [UNREGISTERED]),
    (SHADOWING + registration(), []),
    # ...and a name moved elsewhere takes its old path's registration with
    # it, even one a later name holds (git keeps that map BY PATH).
    (registration() + registration("b") + MOVED_ELSEWHERE, [UNREGISTERED]),
    # A key with no value is fatal to git, but not under a name it ignores.
    (registration() + '[submodule "../b"]\n\tpath\n', []),
], ids=["no-url", "empty-url", "no-name", "another-path", "empty-file",
        "upper-case-keys", "a-0xff-comment", "a-0xff-hides-an-override",
        "name-dotdot", "name-dotdot-backslash", "name-empty",
        "name-dots-not-a-component", "url-option-like",
        "path-option-like-after-a-path", "last-name-for-a-path-has-no-url",
        "first-name-for-a-path-has-no-url", "a-name-moved-off-its-path",
        "no-value-under-an-ignored-name"])
def test_a_registration_is_a_named_path_with_a_url(tmp_path, gitmodules,
                                                   expected):
    """`upstream/dependency` is a gitlink in every case; only the
    `.gitmodules` beside it, both kept in code, changes. Each expectation
    is what git's own submodule reader does with the same shape in a leg:
    no finding exactly where `git submodule update --init` there populates
    the dependency (probed on git 2.43)."""
    plan = answered(
        planned(registered_source(tmp_path, gitmodules=gitmodules),
                tmp_path)[0],
        tmp_path, {GITMODULES: "code", UPSTREAM: "code"})
    result = check_plan(plan)
    assert finding_codes(result.stderr) == expected, result.stderr
    assert result.returncode == (1 if expected else 0)


#: The submodule most of these sources hold, as a finding names it.
NAMED_DEPENDENCY = f"{DEPENDENCY} (entry {UPSTREAM})"
#: Both of them kept in code.
BOTH_IN_CODE = {GITMODULES: "code", UPSTREAM: "code"}
#: What `why_not` says of an entry that holds the path and no url.
NO_URL_READ = "its .gitmodules entry `{}` has no url git reads"


@pytest.mark.parametrize("source, answers, submodule, why", [
    ({"gitmodules": '[submodule "upstream/dependency"]\n'
                    "\tpath = upstream/dependency\n"},
     BOTH_IN_CODE, NAMED_DEPENDENCY, NO_URL_READ.format(DEPENDENCY)),
    ({"gitmodules": registration(url="-oops")}, BOTH_IN_CODE,
     NAMED_DEPENDENCY, NO_URL_READ.format(DEPENDENCY)),
    # Shadowed: the path belongs to the LAST name given it.
    ({"gitmodules": registration() + SHADOWING},
     BOTH_IN_CODE, NAMED_DEPENDENCY, NO_URL_READ.format("b")),
    ({"gitmodules": registration("../escape")}, BOTH_IN_CODE,
     NAMED_DEPENDENCY,
     "git ignores its .gitmodules entry `../escape` as a suspicious name"),
    ({"gitmodules": registration() + MOVED_ELSEWHERE}, BOTH_IN_CODE,
     NAMED_DEPENDENCY, "git dropped its path when the .gitmodules entry "
                       "`upstream/dependency` moved to `elsewhere`"),
    ({"gitmodules": registration() + registration("b") + MOVED_ELSEWHERE},
     BOTH_IN_CODE, NAMED_DEPENDENCY,
     "git dropped its path when the .gitmodules entry "
     "`upstream/dependency` moved to `elsewhere`"),
    ({"registered": (), "orphan": "-dep",
      "gitmodules": '[submodule "d"]\n\tpath = -dep\n\turl = ../dep\n'},
     {GITMODULES: "code", '"-dep"': "code"}, "-dep",
     "git ignores its .gitmodules path, which starts with `-`"),
    # No entry names it: what was said before.
    ({"gitmodules": '[submodule "elsewhere"]\n'
                    "\tpath = elsewhere/dependency\n\turl = ../dependency\n"},
     BOTH_IN_CODE, NAMED_DEPENDENCY,
     "no .gitmodules entry in the source registers its path with a url"),
], ids=["no-url", "url-option-like", "shadowed-by-a-later-name",
        "suspicious-name", "moved-off-its-path", "moved-under-a-later-name",
        "path-option-like", "no-entry"])
def test_an_unregistered_submodule_is_told_why_git_ignores_its_entry(
        adopter, tmp_path, source, answers, submodule, why):
    """#166's N2. An entry of `.gitmodules` that names the submodule's path
    and that git ignores is named, with the reason, rather than "no entry"
    beside an entry the person can see."""
    plan = answered(planned(registered_source(tmp_path, **source),
                            tmp_path)[0], tmp_path, answers)
    assert findings(check_plan(plan).stderr) == [(
        UNREGISTERED, f"the submodule {submodule} has leg: code but {why}, "
                      + adopter.NO_URL_IN_THE_LEG)]


@pytest.mark.parametrize("modules_leg, dependency_leg, expected", [
    ("code", "code", [UNREADABLE]),
    ("code", "drop", [UNREADABLE]),
    ("drop", "spec", [UNREADABLE]),
    # Beside a submodule `git filter-repo` fails on it, wherever the two go.
    ("drop", "drop", [UNREADABLE]),
    ("root", "drop", [ROOT, UNREADABLE]),
])
def test_a_gitmodules_git_cannot_read_is_not_one_that_registers_nothing(
        adopter, plan_of, tmp_path, modules_leg, dependency_leg, expected):
    plan = answered(plan_of(UNREADABLE_FILE)[0], tmp_path,
                    {GITMODULES: modules_leg, UPSTREAM: dependency_leg})
    result = check_plan(plan)
    assert finding_codes(result.stderr) == expected, result.stderr
    assert result.returncode == 1
    assert (f"FINDING {UNREADABLE}: git cannot read the source's "
            ".gitmodules for its submodules (fatal: bad config line 2 in "
            f".gitmodules), {adopter.FAILS_IN_THE_EXTRACTION}\n") \
        in result.stderr


#: A `.gitmodules` whose one defect is a key with no value, which only git's
#: SUBMODULE reader dies on, and git runs that for a gitlink alone.
BARE_KEY = '[submodule "b"]\n\tpath\n'
#: A line no git reader can parse, and nothing else.
BAD_LINE = UNREADABLE_FILE["gitmodules"]


@pytest.mark.parametrize("source, answers, legs, where", [
    # S3: beside no submodule a key with no value is read by nothing, and
    # main adopts and clones it.
    ({"registered": (), "gitmodules": BARE_KEY}, {GITMODULES: "code"}, {},
     None),
    ({"registered": (), "gitmodules": '[submodule "d"]\n\tpath = d\n\turl\n'},
     {GITMODULES: "code"}, {}, None),
    # Every reader dies on a bad line: in a leg, the assembly's clone.
    ({"registered": (), "gitmodules": BAD_LINE}, {GITMODULES: "code"}, {},
     "FAILS_IN_THE_CLONE"),
    ({"registered": (), "gitmodules": BAD_LINE}, {GITMODULES: "drop"}, {},
     None),
    # Beside a submodule, a key with no value fails `git filter-repo` too...
    ({"gitmodules": registration() + BARE_KEY},
     {GITMODULES: "drop", UPSTREAM: "drop"}, {}, "FAILS_IN_THE_EXTRACTION"),
    # ...unless no leg is extracted at all.
    (UNREADABLE_FILE, {GITMODULES: "drop", UPSTREAM: "drop"},
     {"src/": "drop", "specs/": "drop"}, None),
], ids=["no-path-value-beside-no-submodule",
        "no-url-value-beside-no-submodule",
        "bad-line-beside-no-submodule-kept",
        "bad-line-beside-no-submodule-dropped",
        "no-value-beside-a-dropped-submodule", "no-leg-extracted"])
def test_git_fails_on_a_gitmodules_it_cannot_read_where_it_reads_it(
        adopter, plan_of, tmp_path, source, answers, legs, where):
    """#166's S3, measured end to end on main and this branch alike: the
    finding is made where git would fail, and says where that is -- the
    extraction, for a file beside a submodule, or else the clone of a leg
    that keeps it."""
    plan = answered(plan_of(source)[0], tmp_path, answers)
    for path, leg in legs.items():
        edited(plan, path, {path: leg})
    found = findings(check_plan(plan).stderr)
    if where is None:
        assert found == [], found
        return
    assert [code for code, _ in found] == [UNREADABLE], found
    assert found[0][1].endswith(getattr(adopter, where)), found


@pytest.mark.parametrize("where, expected", [
    ("relative", []),
    ("absolute", [UNREGISTERED]),
])
def test_git_follows_no_include_in_a_gitmodules(tmp_path, where, expected):
    """git's submodule reader never follows `[include]` in `.gitmodules`, so
    neither does `check`. A registration beside a RELATIVE include is a
    registration (`git config --blob` dies on one: "relative config includes
    must come from files"), and one that lives only in an ABSOLUTE include,
    a file on the machine running `check`, is none."""
    operator = tmp_path / "operator.gitconfig"
    operator.write_bytes(registration().encode())
    gitmodules = {
        "relative": registration() + "[include]\n\tpath = .gitmodules-local\n",
        "absolute": f'[include]\n\tpath = "{operator.as_posix()}"\n',
    }[where]
    plan = answered(
        planned(registered_source(tmp_path, gitmodules=gitmodules),
                tmp_path)[0],
        tmp_path, {GITMODULES: "code", UPSTREAM: "code"})
    result = check_plan(plan)
    assert finding_codes(result.stderr) == expected, result.stderr


@pytest.mark.parametrize("source, said, where", [
    # git calls the file it read from `--file -` "standard input".
    (UNREADABLE_FILE, "fatal: bad config line 2 in .gitmodules)",
     "FAILS_IN_THE_EXTRACTION"),
    # `git config --list` lists both; git's submodule reader dies on each.
    ({"gitmodules": registration() + BARE_KEY},
     "missing value for 'submodule.b.path'", "FAILS_IN_THE_EXTRACTION"),
    ({"gitmodules": '[submodule "d"]\n\tpath = upstream/dependency\n\turl\n'},
     "missing value for 'submodule.d.url'", "FAILS_IN_THE_EXTRACTION"),
    # A `.gitmodules` that is itself a gitlink has no blob to read, and no
    # file for `git fast-export` to read either: the clone of its leg is
    # where git fails on it.
    ({"registered": (), "orphan": GITMODULES}, "fatal: git cat-file",
     "FAILS_IN_THE_CLONE"),
], ids=["bad-config-line", "path-with-no-value", "url-with-no-value",
        "gitmodules-is-a-gitlink"])
def test_a_gitmodules_git_cannot_read_says_what_git_said(
        adopter, plan_of, tmp_path, source, said, where):
    """The finding names the file AND what git says about it, on the one
    line `check` prints a finding on, and where git fails on it."""
    plan = plan_of(source)[0]
    plan = answered(plan, tmp_path, {path: "code" for path in
                                     (GITMODULES, UPSTREAM)
                                     if path in plan_rows(plan)})
    found = findings(check_plan(plan).stderr)
    assert [code for code, _ in found] == [UNREADABLE], found
    assert found[0][1].startswith(
        "git cannot read the source's .gitmodules for its submodules ("
        + said), found
    assert found[0][1].endswith(getattr(adopter, where)), found


@pytest.mark.parametrize("modules_leg, expected", [
    ("code", []),
    ("spec", []),
    ("drop", []),
    ("root", [ROOT]),
])
def test_a_gitmodules_with_no_submodule_beside_it(plan_of, tmp_path,
                                                  modules_leg, expected):
    """A `.gitmodules` whose one registration names no gitlink in the tree:
    in a leg it registers nothing git will look up, so it goes anywhere but
    the root, whose `.gitmodules` is the two mounts'."""
    plan = answered(plan_of(STALE)[0], tmp_path, {GITMODULES: modules_leg})
    result = check_plan(plan)
    assert finding_codes(result.stderr) == expected, result.stderr
    assert result.returncode == (1 if expected else 0)


@pytest.mark.parametrize("upstream_leg, extra_leg, split", [
    ("code", "code", []),
    ("code", "spec", ["extra/second (entry extra/) has leg: spec"]),
    ("spec", "code", ["upstream/dependency (entry upstream/) has leg: spec"]),
    ("spec", "spec", ["extra/second (entry extra/) has leg: spec",
                      "upstream/dependency (entry upstream/) has leg: spec"]),
])
def test_check_finds_each_submodule_split_from_its_registration(
        plan_of, tmp_path, upstream_leg, extra_leg, split):
    """Two registered submodules and `.gitmodules` in code: each one kept
    away from it is its own `plan-submodule-split`, and only those."""
    plan = answered(plan_of(TWO)[0], tmp_path,
                    {GITMODULES: "code", UPSTREAM: upstream_leg,
                     EXTRA: extra_leg})
    found = findings(check_plan(plan).stderr)
    assert [code for code, _ in found] == [SPLIT] * len(split), found
    assert [detail.split(" but ")[0] for _, detail in found] \
        == [f"the submodule {where}" for where in split]


@pytest.mark.parametrize("dep_leg, expected", [
    ("code", []),
    ("spec", [(SPLIT, "the submodule dep has leg: spec but the source's "
                      ".gitmodules has leg: code")]),
    ("root", [(ROOT, "dep has leg: root, and the assembly root keeps no "
                     "submodule of the source's")]),
])
def test_a_submodule_that_is_its_own_entry_is_named_alone(plan_of, tmp_path,
                                                          dep_leg, expected):
    """`dep` is a top-level gitlink, so its entry is itself: the finding
    names it with no `(entry ...)` to point at."""
    plan = answered(plan_of(TOP)[0], tmp_path, {GITMODULES: "code",
                                                "dep": dep_leg})
    found = findings(check_plan(plan).stderr)
    assert [code for code, _ in found] == [code for code, _ in expected]
    for (_, detail), (_, start) in zip(found, expected):
        assert detail.startswith(start), detail


@pytest.mark.parametrize("answers, removed, added, own", [
    ({GITMODULES: "code"}, UPSTREAM, None, UNCOVERED),
    ({UPSTREAM: "code"}, GITMODULES, None, UNCOVERED),
    ({GITMODULES: "code", UPSTREAM: "code"}, None, DEPENDENCY,
     "plan-covered-twice"),
    ({GITMODULES: "code", UPSTREAM: "Code"}, None, None, BAD_LEG),
    ({GITMODULES: "Code", UPSTREAM: "code"}, None, None, BAD_LEG),
], ids=["gitlink-uncovered", "gitmodules-uncovered", "gitlink-covered-twice",
        "gitlink-bad-leg", "gitmodules-bad-leg"])
def test_the_submodule_rule_leaves_a_rejected_entry_to_its_own_finding(
        adopter, plan_of, tmp_path, answers, removed, added, own):
    """An entry `check` already rejects is not ALSO a submodule problem: the
    helper skips it, and `check` reports it once, by its own finding."""
    plan = answered(plan_of(REGISTERED)[0], tmp_path, answers)
    edited(plan, removed, {added: "spec"} if added else {})
    result = check_plan(plan)
    assert finding_codes(result.stderr) == [own], result.stderr
    assert adopter.SUBMODULE_REMEDIATION not in result.stderr
    loaded = adopter.Plan.load(plan)
    source = loaded.open_source(None, tmp_path / "work")
    tree = source.tree()
    assert adopter.submodule_plan_problems(
        loaded.entries, tree, source.registered_submodules(tree)) == []


@pytest.fixture(scope="module")
def adopter():
    """`adopt-project.py` as a module, for the refusal `execute` makes."""
    module_spec = importlib.util.spec_from_file_location("adopt_refusals",
                                                         ADOPT)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def refused_by_execute(adopter, plan_path: Path, tmp_path: Path):
    """What `_refuse_what_check_finds` raises for `plan_path`, or None."""
    plan = adopter.Plan.load(plan_path)
    source = plan.open_source(None, tmp_path / "work")
    try:
        adopter._refuse_what_check_finds(plan, source)
    except adopter.Refusal as refusal:
        return refusal
    return None


def as_refused(found: list[tuple[str, str]]) -> list[str]:
    """`check`'s findings as `execute`'s refusal lists them, one a line."""
    return [f"  FINDING {code}: {detail}" for code, detail in found]


@pytest.mark.parametrize("source, answers, code", [
    (REGISTERED, {GITMODULES: "code", UPSTREAM: "spec"}, SPLIT),
    (REGISTERED, {GITMODULES: "drop", UPSTREAM: "code"}, SPLIT),
    (REGISTERED, {GITMODULES: "root", UPSTREAM: "root"}, ROOT),
    (BESIDE, {GITMODULES: "code", UPSTREAM: "code", EXTRA: "code"},
     UNREGISTERED),
    (LONE_ORPHAN, {UPSTREAM: "code"}, UNREGISTERED),
    (UNREADABLE_FILE, {GITMODULES: "code", UPSTREAM: "code"}, UNREADABLE),
    (UNREADABLE_FILE, {GITMODULES: "drop", UPSTREAM: "drop"}, UNREADABLE),
    (REGISTERED, {GITMODULES: "spec", UPSTREAM: "spec"}, None),
    (REGISTERED, {GITMODULES: "code", UPSTREAM: "drop"}, None),
    (BESIDE, {GITMODULES: "code", UPSTREAM: "code", EXTRA: "drop"}, None),
    (LONE_ORPHAN, {UPSTREAM: "drop"}, None),
])
def test_execute_refuses_what_check_finds(adopter, plan_of, tmp_path,
                                          source, answers, code):
    """The refusal `execute` makes, asked of `_refuse_what_check_finds`
    directly; that `cmd_execute` makes it before any leg exists is pinned by
    the end-to-end refusal below, which needs `git filter-repo`."""
    plan = answered(plan_of(source)[0], tmp_path, answers)
    found = findings(check_plan(plan).stderr)
    refusal = refused_by_execute(adopter, plan, tmp_path)
    if code is None:
        assert found == [] and refusal is None, (found, refusal)
        return
    # ONE list: the refusal is what `check` found, in its words.
    assert refusal is not None, found
    assert refusal.code == found[0][0] == code
    assert refusal.detail.splitlines()[1:] == as_refused(found)
    assert refusal.remediation.endswith("\n" + adopter.SUBMODULE_REMEDIATION)
    # No stricter than the rule: one submodule may be dropped by itself.
    assert ("Any one submodule may also be dropped on its own: its "
            "registration stays behind") in refusal.remediation
    assert "never keeps a submodule" in refusal.remediation
    assert RESERVED in refusal.remediation
    assert ("cannot be kept in a leg at all" in refusal.remediation
            and "and re-run `plan`" in refusal.remediation)
    # The one edit that answers a submodule apart from its directory entry.
    assert ("REPLACE that entry with an entry for each of its children"
            in refusal.remediation
            and "`plan-covered-twice`" in refusal.remediation)


@pytest.mark.parametrize("first_leg, code", [
    ("root", ROOT),
    ("code", UNREGISTERED),
])
def test_a_mixed_refusal_is_named_by_the_problem_to_fix_first(
        adopter, plan_of, tmp_path, first_leg, code):
    """`.gitmodules` and `extra/orphan` in code, `d1/` to `d9/` split to
    spec, and `d0/` in the root or not: eleven problems or ten, listed root,
    then unregistered, then split. The refusal takes the FIRST one's code
    and names as many as `execute` names of any findings, then counts the
    rest."""
    answers = {GITMODULES: "code", EXTRA: "code", "d0/": first_leg,
               **{f"d{i}/": "spec" for i in range(1, 10)}}
    plan = answered(plan_of(CROWDED)[0], tmp_path, answers)
    found = findings(check_plan(plan).stderr)
    assert [found_code for found_code, _ in found] == (
        [ROOT] * (first_leg == "root") + [UNREGISTERED] + [SPLIT] * 9)
    refusal = refused_by_execute(adopter, plan, tmp_path)
    assert refusal.code == code
    shown = adopter.REFUSED_FINDINGS_SHOWN
    assert refusal.detail.splitlines()[1:] == (
        as_refused(found[:shown]) + [f"  and {len(found) - shown} more"])


def test_execute_refuses_every_finding_check_prints_at_once(
        adopter, plan_of, tmp_path, monkeypatch):
    """#166's NEW-3. `check` lists an uncovered path and a split submodule;
    `execute` used to refuse the split alone, in a function of its own, and
    the uncovered path only once that was fixed. Through `cmd_execute`, as a
    person meets it: one refusal naming both, before any leg exists, with
    #168's remedy and the submodule one."""
    plan = answered(plan_of(REGISTERED)[0], tmp_path,
                    {GITMODULES: "code", UPSTREAM: "spec"})
    edited(plan, README, {})
    found = findings(check_plan(plan).stderr)
    assert [code for code, _ in found] == [UNCOVERED, SPLIT], found
    # Every refusal here comes before the tool would be used.
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)
    remotes = tmp_path / REMOTES
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(Namespace(
            plan=str(plan), source=None, local_remote_dir=remotes,
            allow_empty_leg=[], yes=True, work_dir=tmp_path / "work"))
    refusal = caught.value
    assert refusal.code == UNCOVERED
    assert refusal.detail.splitlines()[1:] == as_refused(found)
    assert "no leg repository was created" in refusal.remediation
    assert refusal.remediation.endswith("\n" + adopter.SUBMODULE_REMEDIATION)
    assert not remotes.exists()


def execute_in(plan: Path, base: Path):
    """`execute --yes` of `plan`, its leg remotes under `base/remotes` and its
    work in `base/work`: `(result, remotes, work)`."""
    remotes, work = base / REMOTES, base / "work"
    return adopt("execute", plan, "--yes", "--local-remote-dir", str(remotes),
                 "--work-dir", str(work)), remotes, work


def clone_the_split(source: Path, tmp_path: Path):
    """`git clone --recurse-submodules` of the branch `execute` pushed the
    split to, into `tmp_path/clone`: what a person runs next."""
    return git(*FILE_PROTOCOL, "clone", "-q", "--recurse-submodules", "-b",
               "adopt/three-repo-shape", str(source), str(tmp_path / "clone"),
               cwd=tmp_path, check=False)


def source_state(source: Path) -> list[str]:
    """HEAD, every ref and `git status`: what a refused `execute` must not
    move. Submodules are ignored by the status, which otherwise reads
    `.gitmodules` for them and dies on one it cannot read."""
    return [git(*args, cwd=source).stdout for args in (
        ("rev-parse", "HEAD"), ("for-each-ref",),
        ("status", "--porcelain", "--ignore-submodules=all"))]


@needs_filter_repo
@pytest.mark.parametrize("source, answers, code, refused", [
    (REGISTERED, {GITMODULES: "code", UPSTREAM: "spec"}, SPLIT,
     "the submodule upstream/dependency (entry upstream/) has leg: spec but "
     "the source's .gitmodules has leg: code"),
    (LONE_ORPHAN, {UPSTREAM: "code"}, UNREGISTERED,
     "the submodule upstream/orphan (entry upstream/) has leg: code but no "
     ".gitmodules entry in the source registers its path with a url"),
    # Both dropped, and `git filter-repo` still fails on the file: on main
    # that was after both leg remotes existed (#166's S3).
    (UNREADABLE_FILE, {GITMODULES: "drop", UPSTREAM: "drop"}, UNREADABLE,
     "git cannot read the source's .gitmodules for its submodules (fatal: "
     "bad config line 2 in .gitmodules), and the source holds a submodule, "
     "so `git filter-repo` fails on that file when `execute` extracts a "
     "leg"),
], ids=["split", "unregistered-orphan", "unreadable-beside-a-dropped-one"])
def test_execute_refuses_a_submodule_plan_before_anything_exists(
        tmp_path, source, answers, code, refused):
    """Before #166 each plan was extracted, mounted, pushed and verified,
    and the assembly's recursive clone then exited 128 -- the orphan's
    although the source's own recursive clone exits 0 -- or, for the file
    git cannot read, `execute` died extracting a leg. Refused now, and
    refused before `_create_leg_remotes`: a re-run must not meet two legs
    that a refused plan already made."""
    thing = registered_source(tmp_path, **source)
    before = source_state(thing)
    plan = answered(planned(thing, tmp_path)[0], tmp_path, answers)
    result, remotes, work = execute_in(plan, tmp_path)
    assert result.returncode == 2, result.stderr + result.stdout
    assert f"REFUSED {code}: 1 finding(s) in " in result.stderr
    assert f"\n  FINDING {code}: {refused}" in result.stderr
    assert "creating the leg repositories" not in result.stdout
    # Nothing was made but the empty work directory `--work-dir` names.
    assert not remotes.exists(), "a refused plan made the remotes directory"
    assert list(work.iterdir()) == [], "a refused plan wrote into its work"
    assert source_state(thing) == before


@needs_filter_repo
@pytest.mark.parametrize("modules_leg, dependency_leg, gitmodules", [
    ("code", "code", None),
    ("spec", "spec", None),
    # Dropped on its own: its registration stays behind in the leg, inert.
    ("code", "drop", None),
    # Hand-written registrations `check` reads as the leg's clone reads them:
    # upper-case keys, and two `git config --blob` refused.
    ("code", "code", UPPER_CASE_KEYS.replace("../dependency", THE_DEPENDENCY)),
    ("code", "code",
     LATIN_1_COMMENT + registration(url=THE_DEPENDENCY).encode()),
    ("code", "code", registration(url=THE_DEPENDENCY)
     + "[include]\n\tpath = .gitmodules-local\n"),
], ids=["both-code", "both-spec", "dropped-on-its-own", "upper-case-keys",
        "a-0xff-comment", "an-include-git-never-follows"])
def test_an_accepted_submodule_plan_adopts_clones_and_bootstraps(
        tmp_path, modules_leg, dependency_leg, gitmodules):
    """The plans the refusals above leave legal really adopt: `execute`
    verifies, and the assembly's `git clone --recurse-submodules` and its
    `bootstrap.py` both exit 0, which a split plan's clone did not (#166)."""
    thing = registered_source(tmp_path, gitmodules=gitmodules)
    plan = answered(planned(thing, tmp_path)[0], tmp_path,
                    {GITMODULES: modules_leg, UPSTREAM: dependency_leg})
    checked = check_plan(plan)
    assert checked.returncode == 0, checked.stderr + checked.stdout
    result = execute_in(plan, tmp_path)[0]
    assert result.returncode == 0, result.stderr + result.stdout
    assert "adoption verified" in result.stdout

    clone = tmp_path / "clone"
    cloned = clone_the_split(thing, tmp_path)
    assert cloned.returncode == 0, cloned.stderr
    bootstrapped = run_script(clone / "scripts/bootstrap.py", cwd=clone)
    assert bootstrapped.returncode == 0, (bootstrapped.stderr
                                          + bootstrapped.stdout)
    assert "bootstrap ok" in bootstrapped.stdout
    leg = clone / modules_leg
    gitlink = git("ls-tree", "HEAD", "--", DEPENDENCY, cwd=leg).stdout
    # The registration travels with `.gitmodules`, whether or not its
    # gitlink did.
    assert git("config", "-f", GITMODULES, "--get",
               f"submodule.{DEPENDENCY}.path", cwd=leg).stdout.strip() \
        == DEPENDENCY
    if dependency_leg == "drop":
        assert gitlink == "" and not (leg / UPSTREAM).exists()
        return
    assert gitlink.startswith("160000 commit ")
    # Cloned into the leg, at the commit the source pinned.
    assert {name: (leg / DEPENDENCY / name).read_text(encoding="utf-8")
            for name in DEPENDENCY_TREE} == DEPENDENCY_TREE


@needs_filter_repo
def test_a_key_with_no_value_beside_no_submodule_adopts_and_clones(tmp_path):
    """#166's S3, end to end: a `.gitmodules` whose one defect is a key with
    no value, in a source with no submodule, kept in a leg. git runs its
    submodule reader for a gitlink alone, so nothing reads the file that way:
    main adopted and cloned it, and `check` no longer refuses it."""
    thing = registered_source(tmp_path, registered=(), gitmodules=BARE_KEY)
    plan = answered(planned(thing, tmp_path)[0], tmp_path,
                    {GITMODULES: "code"})
    checked = check_plan(plan)
    assert checked.returncode == 0, checked.stderr + checked.stdout
    result = execute_in(plan, tmp_path)[0]
    assert result.returncode == 0, result.stderr + result.stdout
    assert "adoption verified" in result.stdout
    clone = tmp_path / "clone"
    cloned = clone_the_split(thing, tmp_path)
    assert cloned.returncode == 0, cloned.stderr
    assert (clone / "code" / GITMODULES).read_bytes() == BARE_KEY.encode()
