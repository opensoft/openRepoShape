# SPDX-License-Identifier: Apache-2.0
"""Adoption preserves an existing dependency through the nested leg mount.

All repositories and remotes are local fixtures; no network is used.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
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
    git(*FILE_PROTOCOL, "submodule", "add", "-q", str(dependency_remote),
        "upstream/dependency", cwd=source)
    git("-c", "user.name=Source Human", "-c",
        "user.email=source@invalid.example", "commit", "-qm",
        "Pin existing dependency", cwd=source)
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
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(tmp_path / "remotes"),
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
            git(*FILE_PROTOCOL, "submodule", "add", "-q", str(dependency),
                path, cwd=source)
        if registered:
            git("-c", "user.name=Source Human", "-c",
                "user.email=source@invalid.example", "commit", "-qm",
                "Register dependencies", cwd=source)
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
    """Two registrations in the source: one kept in the assembly, one moved."""
    return mount_world()


def test_mount_preserves_registration_kept_in_assembly(mount_fixture,
                                                       tmp_path):
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
    tree = {"README.md": "# Thing\n", ".gitignore": IGNORE_DOTFILES,
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
# #166. `check` and `execute` read the SAME `submodule_plan_problems`, so a
# plan `check` passes is a plan `execute` runs. None of these needs
# `git filter-repo` but the one that reaches `execute` past its preflight.

#: The two ids, as `check` prints them and `execute` raises them.
SPLIT = "plan-submodule-split"
ROOT = "plan-submodule-root"

#: A source whose plan asks nothing but the submodule's questions: `specs/`
#: and `src/` classify themselves and `README.md` stays in the root.
SMALL_TREE = {"README.md": "# Thing\n", "src/app/util.py": "VALUE = 1\n",
              "specs/001-feature/tasks.md": "- [ ] one\n"}


def registered_source(base: Path, registered=("upstream/dependency",),
                      orphan: str | None = None) -> Path:
    """A source registering a real dependency at each of `registered`.

    `orphan` adds a gitlink at that path with NO registration, written
    straight into the index as `git add` of an embedded clone would write it,
    so that a source with a submodule and no `.gitmodules` is planned too.
    """
    dependency = make_source_repo(base / "dependency",
                                  tree={"value.txt": "dependency\n"}, edits=())
    source = make_source_repo(base / "Thing", tree=SMALL_TREE)
    for path in registered:
        git(*FILE_PROTOCOL, "submodule", "add", "-q", str(dependency), path,
            cwd=source)
    if orphan:
        head = git("rev-parse", "HEAD", cwd=dependency).stdout.strip()
        git("update-index", "--add", "--cacheinfo", f"160000,{head},{orphan}",
            cwd=source)
    git("-c", "user.name=Source Human", "-c",
        "user.email=source@invalid.example", "commit", "-qm",
        "Register dependencies", cwd=source)
    return source


@pytest.fixture(scope="module")
def registered_plan(tmp_path_factory):
    """ONE source with `upstream/dependency` registered, and its plan.

    Each check test answers a COPY of the plan; the source is only ever read.
    """
    base = tmp_path_factory.mktemp("registered")
    source = registered_source(base)
    plan = base / "adoption-plan.yaml"
    written = write_plan(source, plan)
    assert written.returncode == 0, written.stderr + written.stdout
    return plan, written


def answered(plan: Path, tmp_path: Path, answers) -> Path:
    """A copy of `plan` with each `(path, leg)` in `answers` resolved; a leg
    of None leaves that entry's question unanswered."""
    copy = tmp_path / "adoption-plan.yaml"
    copy.write_text(plan.read_text(encoding="utf-8"), encoding="utf-8")
    for path, leg in answers:
        if leg is not None:
            resolve(copy, path, leg)
    return copy


def finding_codes(stderr: str) -> list[str]:
    return [line.split(":", 1)[0].split()[1] for line in stderr.splitlines()
            if line.startswith("FINDING ")]


def test_plan_asks_the_submodule_question_on_gitmodules(registered_plan):
    plan, written = registered_plan
    rows = {str(row["path"]): row for row in load_yaml(plan)["paths"]}
    row = rows[".gitmodules"]
    assert row["leg"] is None
    assert row["review_required"] is True
    assert row["rule"] == "ambiguous-gitmodules"
    assert ("A source's own `.gitmodules` goes to the SAME leg as every "
            "submodule it registers; `execute` writes the assembly root a "
            "fresh one for its two mounts.") in row["question"]
    assert "`root` is not an answer" in row["question"]
    # Printed with the other unresolved paths, which is where it is read.
    assert "goes to the SAME leg as every submodule" in written.stdout


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
    (None, "code", ["plan-unresolved"]),
    (None, "root", ["plan-unresolved", ROOT]),
])
def test_check_holds_a_submodule_to_the_leg_of_its_registration(
        registered_plan, tmp_path, modules_leg, dependency_leg, expected):
    plan = answered(registered_plan[0], tmp_path,
                    ((".gitmodules", modules_leg),
                     ("upstream/", dependency_leg)))
    result = run_script(ADOPT, "check", "--plan", str(plan))
    assert finding_codes(result.stderr) == expected, result.stderr
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
        assert f"FINDING {ROOT}: .gitmodules has leg: root" in result.stderr
    if dependency_leg == "root":
        assert (f"FINDING {ROOT}: upstream/dependency (entry upstream/) has "
                "leg: root") in result.stderr


def test_check_finds_a_submodule_a_rule_classified_silently(tmp_path):
    """`tools/dep` is under `tools/**`, so `plan` calls it code and asks
    nothing; only `.gitmodules` is asked. Answered `spec`, the two split."""
    source = registered_source(tmp_path, registered=("tools/dep",))
    plan = tmp_path / "plan" / "adoption-plan.yaml"
    plan.parent.mkdir()
    assert write_plan(source, plan).returncode == 0
    rows = {str(row["path"]): row for row in load_yaml(plan)["paths"]}
    assert rows["tools/"]["leg"] == "code"
    resolve(plan, ".gitmodules", "spec")
    result = run_script(ADOPT, "check", "--plan", str(plan))
    assert result.returncode == 1, result.stderr + result.stdout
    assert (f"FINDING {SPLIT}: the submodule tools/dep (entry tools/) has "
            "leg: code but the source's .gitmodules has leg: spec") \
        in result.stderr


@pytest.mark.parametrize("leg, expected", [
    ("code", []),
    ("root", [ROOT]),
])
def test_an_orphan_gitlink_may_go_to_a_leg_but_not_the_root(tmp_path, leg,
                                                            expected):
    """No `.gitmodules` at all: the gitlink was unclonable in the source too,
    and a leg is no worse a place for it. The root is still not one."""
    source = registered_source(tmp_path, registered=(),
                               orphan="upstream/orphan")
    assert git("ls-tree", "HEAD", "--", ".gitmodules",
               cwd=source).stdout == ""
    plan = tmp_path / "plan" / "adoption-plan.yaml"
    plan.parent.mkdir()
    assert write_plan(source, plan).returncode == 0
    resolve(plan, "upstream/", leg)
    result = run_script(ADOPT, "check", "--plan", str(plan))
    assert finding_codes(result.stderr) == expected, result.stderr
    assert result.returncode == (1 if expected else 0)


@pytest.fixture(scope="module")
def adopter():
    """`adopt-project.py` as a module, for the refusal `execute` makes."""
    module_spec = importlib.util.spec_from_file_location("adopt_refusals",
                                                         ADOPT)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("modules_leg, dependency_leg, code", [
    ("code", "spec", SPLIT),
    ("drop", "code", SPLIT),
    ("root", "root", ROOT),
    ("spec", "spec", None),
    ("code", "drop", None),
])
def test_execute_refuses_what_check_finds(adopter, registered_plan, tmp_path,
                                          modules_leg, dependency_leg, code):
    plan_path = answered(registered_plan[0], tmp_path,
                         ((".gitmodules", modules_leg),
                          ("upstream/", dependency_leg)))
    plan = adopter.Plan.load(plan_path)
    source = plan.open_source(None, tmp_path / "work")
    if code is None:
        adopter._refuse_an_unrunnable_plan(plan, source)
        return
    with pytest.raises(adopter.Refusal) as refused:
        adopter._refuse_an_unrunnable_plan(plan, source)
    assert refused.value.code == code
    assert "upstream/dependency" in refused.value.detail
    assert "`git rm` it in the leg afterwards" in refused.value.remediation
    assert "never keeps a submodule" in refused.value.remediation


@needs_filter_repo
def test_execute_refuses_a_split_submodule_before_any_leg_exists(tmp_path):
    """Before #166 this plan was extracted, mounted, pushed and verified, and
    its assembly's recursive clone then exited 128. Refused now, and refused
    before `_create_leg_remotes`: a re-run must not meet two legs that a
    refused plan already made."""
    source = registered_source(tmp_path)
    head = git("rev-parse", "HEAD", cwd=source).stdout.strip()
    plan = tmp_path / "plan" / "adoption-plan.yaml"
    plan.parent.mkdir()
    assert write_plan(source, plan).returncode == 0
    resolve(plan, ".gitmodules", "code")
    resolve(plan, "upstream/", "spec")
    remotes = tmp_path / "remotes"
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2, result.stderr + result.stdout
    assert (f"REFUSED {SPLIT}: the submodule upstream/dependency (entry "
            "upstream/) has leg: spec but the source's .gitmodules has leg: "
            "code") in result.stderr
    assert "creating the leg repositories" not in result.stdout
    assert list(remotes.glob("*.git")) == [], "a refused plan made a leg"
    assert git("rev-parse", "HEAD", cwd=source).stdout.strip() == head
    assert git("branch", "--list", "adopt/*", cwd=source).stdout == ""
