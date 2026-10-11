# SPDX-License-Identifier: Apache-2.0
"""Which branch, and which repository, a shape update's pull request is told
to land on (#209).

`update-shape.py apply --branch` ends in a `NEXT` line a human pastes, and
`--pr` opens the pull request itself. Both name a base and a repository, and
they used to settle them separately: `open_pull_request` read the manifest's
`tracking_branch:` and the assembly leg's `repository:`, and the `NEXT` line
wrote `main` and a literal `<org>/<Project>` whatever the manifest said, so a
project scaffolded with `--tracking-branch trunk` was handed a command that
targets a branch its remote does not have, by the very run whose `--pr` would
have opened the pull request against `trunk`.

THREE ROOTS, ALL REAL: a project scaffolded with `--tracking-branch trunk`, a
default one (`tracking_branch: main` recorded), and a default one whose
manifest records NO tracking branch at all — which `validate-manifest.py`
accepts and which every other tool (`bootstrap.py`, `bump-leg.py`,
`family.py`, `commit_on_branch`'s own refusal) reads as `main`. The remote's
HEAD is never consulted for that last case: `apply` is otherwise offline.

THE UPSTREAM IS A CLONE OF THIS REPOSITORY, the project is scaffolded out of
it into bare repositories in a temporary directory, and `gh` is stubbed at the
one seam `update-shape.py` reaches it by — nothing here touches a network.
"""

from __future__ import annotations

import importlib.util
import shlex
import shutil
from types import SimpleNamespace

import pytest

from conftest import ORG, REPO, git, run_script
from test_family import upstream_clone
from test_update_shape import (CHANGED_SOURCE, PROJECT, UPSTREAM_FIX_LINE,
                               apply, commit_upstream_changes, next_line_of,
                               scaffold_upstream_and_project)

UPDATE = REPO / "update-shape.py"


def project_with_an_upstream_fix(tmp_path_factory, subdir: str,
                                 *scaffold_args: str) -> dict:
    """A project at A, and an upstream that has since moved to B — the shape
    `test_update_shape.py`'s own `upstream_and_project` returns, so `apply`
    and `next_line_of` from there take it unchanged."""
    _base, upstream, commit_a, clone = scaffold_upstream_and_project(
        tmp_path_factory, subdir, *scaffold_args)
    commit_b = commit_upstream_changes(
        upstream, "Fix the manifest validator",
        {CHANGED_SOURCE: UPSTREAM_FIX_LINE})
    assert commit_a != commit_b
    return {"upstream": upstream, "clone": clone, "a": commit_a, "b": commit_b}


@pytest.fixture(scope="module")
def default_project(tmp_path_factory) -> dict:
    return project_with_an_upstream_fix(tmp_path_factory, "pr-base-default")


@pytest.fixture(scope="module")
def trunk_project(tmp_path_factory) -> dict:
    return project_with_an_upstream_fix(
        tmp_path_factory, "pr-base-trunk", "--tracking-branch", "trunk")


def record_no_tracking_branch(root) -> None:
    """Commit a `project.yaml` with no `tracking_branch:` line on the root's
    own branch. Bytes in and bytes out, so a Windows checkout keeps whatever
    line endings the manifest already had."""
    manifest = root / "project.yaml"
    lines = manifest.read_bytes().splitlines(keepends=True)
    kept = [line for line in lines if not line.startswith(b"tracking_branch:")]
    assert len(kept) == len(lines) - 1, "the scaffold records one tracking branch"
    manifest.write_bytes(b"".join(kept))
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        "Record no tracking branch", "--", "project.yaml", cwd=root)


@pytest.fixture(params=["default", "trunk", "unrecorded"])
def case(request, default_project, trunk_project, tmp_path_factory):
    """One root to update: its fixture dict, the base its pull request must
    name, and `copy()` for a private mutable copy of it. A case that makes
    two copies gets two roots no run has touched, which is what lets one
    test compare what the `NEXT` line says with what `--pr` does."""
    which, project, base, strip = {
        "default": ("default", default_project, "main", False),
        "trunk": ("trunk", trunk_project, "trunk", False),
        "unrecorded": ("unrecorded", default_project, "main", True),
    }[request.param]

    def copy():
        target = tmp_path_factory.mktemp(f"pr-base-{which}") / PROJECT
        shutil.copytree(project["clone"], target, symlinks=True)
        if strip:
            record_no_tracking_branch(target)
        return target

    return SimpleNamespace(id=which, project=project, base=base, copy=copy)


@pytest.fixture(scope="module")
def update_shape():
    """`update-shape.py` as a module, so `--pr` can run in this process with
    `gh` stubbed. Loaded under its own name; it executes
    `from repo_shape import Refusal` against the same cached module the other
    test files use."""
    spec = importlib.util.spec_from_file_location("update_shape_pr_base",
                                                  UPDATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def gh_calls(update_shape, monkeypatch) -> list:
    """Every `gh` command the tool tries to run, none of them run.

    Stubbed on `update_shape.run`, the one function every command goes
    through: `gh` is answered with a pull request URL and `git` still runs
    for real, because the commit under test has to be a real one.
    """
    real = update_shape.run
    calls: list = []

    def run(command, *args, **kwargs):
        if command[0] == "gh":
            calls.append(list(command))
            return "https://example.invalid/pull/1"
        return real(command, *args, **kwargs)

    monkeypatch.setattr(update_shape, "run", run)
    for name, value in (("GIT_AUTHOR_NAME", "openRepoShape tests"),
                        ("GIT_AUTHOR_EMAIL", "tests@openreposhape.invalid"),
                        ("GIT_COMMITTER_NAME", "openRepoShape tests"),
                        ("GIT_COMMITTER_EMAIL", "tests@openreposhape.invalid"),
                        ("LANES_LANE", "")):
        monkeypatch.setenv(name, value)
    return calls


@pytest.mark.parametrize("flags", [(), ("--push",)],
                         ids=["branch", "branch-push"])
def test_the_next_line_names_the_roots_tracking_branch_as_the_base(case,
                                                                   flags):
    """Both forms of the `gh pr create` the run prints: the bare `--branch`
    one, which pushes first, and the `--branch --push` one, which has. Each
    names the project's own repository as well, since the bare form's `gh`
    runs wherever the line was pasted."""
    root = case.copy()
    branch = f"shape/base-{case.id}-{'push' if flags else 'plain'}"
    result = apply(root, case.project, "--branch", branch, *flags)
    assert result.returncode == 0, result.stdout + result.stderr
    line = next_line_of(result.stdout)
    assert "gh pr create" in line
    assert line.count("--base") == 1, line
    assert line.endswith(f"gh pr create --repo {ORG}/{PROJECT} --base "
                         f"{case.base} --head {branch}"), line


def test_the_next_line_after_a_push_names_the_repository_not_a_placeholder(
        case):
    """The `--branch --push` line is pasted as it stands, so the repository in
    it is the project's own and not the `<org>/<Project>` it used to print:
    the human is not told to fill in what the manifest already says."""
    branch = f"shape/repo-{case.id}"
    result = apply(case.copy(), case.project, "--branch", branch, "--push")
    assert result.returncode == 0, result.stdout + result.stderr
    line = next_line_of(result.stdout)
    assert "<" not in line and ">" not in line, line
    assert line == (f"NEXT  gh pr create --repo {ORG}/{PROJECT} --base "
                    f"{case.base} --head {branch}"), line


def test_the_pull_request_is_opened_against_the_base_the_next_line_names(
        case, update_shape, gh_calls):
    """THE DISAGREEMENT ITSELF: runs on untouched copies of one root, two
    printing the command a human pastes (before and after a push) and one
    opening the pull request. What they name is compared with each other, not
    only with the expectation, so the next drift between them fails here
    whichever side moves."""
    printed = {}
    for flags in ((), ("--push",)):
        branch = f"shape/printed-{case.id}-{'push' if flags else 'plain'}"
        result = apply(case.copy(), case.project, "--branch", branch, *flags)
        assert result.returncode == 0, result.stdout + result.stderr
        printed[flags] = (next_line_of(result.stdout), branch)

    code = update_shape.main([
        "apply", "--root", str(case.copy()), "--yes",
        "--upstream", str(case.project["upstream"]),
        "--at", case.project["b"], "--branch", f"shape/opened-{case.id}",
        "--pr"])
    assert code == 0
    assert len(gh_calls) == 1, gh_calls
    command = gh_calls[0]
    assert command[:3] == ["gh", "pr", "create"], command
    assert command.count("--base") == 1, command
    assert command.count("--repo") == 1, command
    opened_against = command[command.index("--base") + 1]
    opened_in = command[command.index("--repo") + 1]

    assert opened_against == case.base
    assert opened_in == f"{ORG}/{PROJECT}"
    plain, branch = printed[()]
    assert plain.endswith(f" && gh pr create --repo {opened_in} --base "
                          f"{opened_against} --head {branch}"), plain
    pushed, branch = printed[("--push",)]
    assert pushed == (f"NEXT  gh pr create --repo {opened_in} --base "
                      f"{opened_against} --head {branch}"), pushed


@pytest.mark.parametrize("kind_name", ["PROJECT_KIND", "FAMILY_KIND"])
@pytest.mark.parametrize("manifest_text, base", [
    ("tracking_branch: trunk\n", "trunk"),
    ("name: Atlas\n", "main"),
], ids=["recorded", "unrecorded"])
def test_each_kind_of_root_is_asked_in_its_own_manifest(
        update_shape, tmp_path, capsys, kind_name, manifest_text, base):
    """A family holder is updated by the same command and its manifest is
    `family.yaml`: `next_line` has to be told which kind it is, or it would
    look for a `project.yaml` a holder does not carry."""
    kind = getattr(update_shape, kind_name)
    (tmp_path / kind.manifest).write_text(manifest_text, encoding="utf-8")
    assert update_shape.tracking_branch_of(
        update_shape.load_yaml(tmp_path / kind.manifest)) == base

    args = SimpleNamespace(branch="shape/x", push=False, pr=False)
    update_shape.next_line(tmp_path, args, [], "0" * 40, [], kind)
    line = capsys.readouterr().out.strip()
    assert line.startswith("NEXT"), line
    assert line.endswith(f"--base {base} --head shape/x"), line


#: Manifests a family holder and a project can declare their repository in,
#: and the repository `open_pull_request` has always read out of each.
REPOSITORY_MANIFESTS = [
    ("PROJECT_KIND", "legs:\n"
                     "  - role: spec\n"
                     "    repository: acme/AtlasSpec\n"
                     "  - role: assembly\n"
                     "    repository: acme/Atlas\n"
                     "  - role: code\n"
                     "    repository: acme/AtlasCode\n", "acme/Atlas"),
    ("FAMILY_KIND", "repository: acme/Holder\n"
                    "org: other\n"
                    "name: Ignored\n", "acme/Holder"),
    ("FAMILY_KIND", "org: acme\nname: Holder\n", "acme/Holder"),
]


@pytest.mark.parametrize("kind_name, manifest_text, repository",
                         REPOSITORY_MANIFESTS,
                         ids=["project-assembly-leg", "family-repository",
                              "family-org-and-name"])
def test_the_repository_is_read_where_open_pull_request_reads_it(
        update_shape, tmp_path, capsys, kind_name, manifest_text, repository):
    """The assembly leg's `repository:` for a project (not the spec leg's or
    the code leg's), a family's own `repository:` first and its `org:` and
    `name:` where it has none. The `--push` line prints exactly that."""
    kind = getattr(update_shape, kind_name)
    (tmp_path / kind.manifest).write_text(manifest_text, encoding="utf-8")
    assert update_shape.pull_request_repository(
        update_shape.load_yaml(tmp_path / kind.manifest), kind)[0] == repository

    for push in (True, False):
        args = SimpleNamespace(branch="shape/x", push=push, pr=False)
        update_shape.next_line(tmp_path, args, [], "0" * 40, [], kind)
        line = capsys.readouterr().out.strip()
        assert line.endswith(f"gh pr create --repo {repository} --base main "
                             "--head shape/x"), line
        assert line.startswith("NEXT  gh pr create" if push else
                               "NEXT  git -C "), line


@pytest.mark.parametrize("kind_name, manifest_text, refusal", [
    ("PROJECT_KIND", "legs:\n  - role: spec\n    repository: acme/AtlasSpec\n",
     "project.yaml declares no assembly leg, so there is no repository to "
     "open a pull request against"),
    ("PROJECT_KIND", "legs:\n  - role: assembly\n",
     "project.yaml declares no assembly leg, so there is no repository to "
     "open a pull request against"),
    ("FAMILY_KIND", "name: Holder\n",
     "family.yaml declares neither `repository:` nor an `org:`/`name:` pair, "
     "so there is no repository to open a pull request against"),
], ids=["no-assembly-leg", "assembly-leg-without-repository", "family"])
def test_a_manifest_naming_no_repository_refuses_pr_and_leaves_the_placeholder(
        update_shape, tmp_path, capsys, gh_calls, kind_name, manifest_text,
        refusal):
    """Nothing to open a pull request against: `--pr` refuses, as it always
    did, and says so in the same words. The `NEXT` line runs after the
    commit, where a refusal would take the commit back, so it prints the
    placeholder it always printed and leaves the human to fill it in."""
    kind = getattr(update_shape, kind_name)
    (tmp_path / kind.manifest).write_text(manifest_text, encoding="utf-8")
    assert update_shape.pull_request_repository(
        update_shape.load_yaml(tmp_path / kind.manifest), kind)[0] == ""

    with pytest.raises(update_shape.Refusal) as raised:
        update_shape.pull_request_target(tmp_path, kind)
    assert raised.value.code == "update-pr-no-repository"
    assert refusal in str(raised.value)
    assert gh_calls == []

    args = SimpleNamespace(branch="shape/x", push=True, pr=False)
    update_shape.next_line(tmp_path, args, [], "0" * 40, [], kind)
    assert capsys.readouterr().out.strip() == (
        "NEXT  gh pr create --repo <org>/<Project> --base main --head shape/x")
    args = SimpleNamespace(branch="shape/x", push=False, pr=False)
    update_shape.next_line(tmp_path, args, [], "0" * 40, [], kind)
    assert capsys.readouterr().out.strip().endswith(
        " && gh pr create --base main --head shape/x")


def test_nothing_in_the_next_line_names_a_base_when_the_pull_request_is_open(
        update_shape, tmp_path, capsys):
    """`--pr` has opened it, so there is no `gh pr create` left to print and
    no manifest this line has any business reading."""
    args = SimpleNamespace(branch="shape/x", push=False, pr=True)
    update_shape.next_line(tmp_path, args, [], "0" * 40, [])
    assert capsys.readouterr().out.strip() == (
        "NEXT  the pull request is open; ask a human to review and merge it")


@pytest.mark.parametrize("push", [True, False], ids=["branch-push", "branch"])
def test_a_value_the_manifest_holds_is_quoted_for_the_shell_that_reads_the_line(
        update_shape, tmp_path, capsys, push):
    """The base and the repository come out of a manifest a human may have
    edited, and the line is pasted into a shell. `validate-manifest.py` never
    looks at `tracking_branch:`, so `a&b` reaches the line, and an unquoted
    `&` would end the command there. What a shell READS from the line is
    compared, not the text, so any quoting that says the same thing passes."""
    (tmp_path / "project.yaml").write_text(
        'tracking_branch: "a&b"\n'
        "legs:\n"
        "  - role: assembly\n"
        '    repository: "acme/It\'s here"\n', encoding="utf-8")
    args = SimpleNamespace(branch="shape/x", push=push, pr=False)
    update_shape.next_line(tmp_path, args, [], "0" * 40, [])
    line = capsys.readouterr().out.strip()
    command = line.partition(" && ")[2] if not push else line[len("NEXT  "):]
    assert shlex.split(command) == [
        "gh", "pr", "create", "--repo", "acme/It's here", "--base", "a&b",
        "--head", "shape/x"], line


FAMILY_SOURCE = "templates/family-root/scripts/validate-family.py"
FAMILY_FIX_LINE = "\n# An upstream fix that must reach every family.\n"
HOLDER = "Contoso"


@pytest.fixture(scope="module")
def trunk_holder(tmp_path_factory) -> dict:
    """A real family holder cut with `--tracking-branch trunk` into a local
    bare repository, and an upstream that has since moved to B: the same
    `upstream` / `b` shape `apply` from `test_update_shape.py` takes."""
    base = tmp_path_factory.mktemp("pr-base-family")
    created = run_script(
        REPO / "scripts" / "family.py", "init", "--org", ORG,
        "--family", HOLDER, "--created-by", "Test Human",
        "--created-on", "2026-09-09", "--tracking-branch", "trunk",
        "--local-remote-dir", str(base / "remotes"),
        "--work-dir", str(base / "work"))
    assert created.returncode == 0, created.stderr + created.stdout
    upstream = upstream_clone(base / "openRepoShape")
    commit_b = commit_upstream_changes(upstream, "Fix the family validator",
                                       {FAMILY_SOURCE: FAMILY_FIX_LINE})
    return {"upstream": upstream, "clone": base / "work" / HOLDER,
            "b": commit_b}


@pytest.mark.parametrize("flags", [(), ("--push",)],
                         ids=["branch", "branch-push"])
def test_a_family_holder_is_asked_in_its_own_manifest_after_the_commit(
        trunk_holder, tmp_path, flags):
    """`apply --branch` END TO END ON A HOLDER, which has `family.yaml` and no
    `project.yaml`. `next_line` runs after the commit, inside the arm that
    undoes the tree on a refusal; one that looked for `project.yaml` would
    commit (and push), then refuse, and roll the working tree back under the
    commit it had made. Here the run succeeds, prints the holder's own
    repository and its own tracking branch, and leaves the tree clean."""
    holder = tmp_path / HOLDER
    shutil.copytree(trunk_holder["clone"], holder, symlinks=True)
    branch = f"shape/family-{'push' if flags else 'plain'}"
    result = apply(holder, trunk_holder, "--branch", branch, *flags)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"committed on {branch}" in result.stdout, result.stdout
    line = next_line_of(result.stdout)
    assert line.endswith(f"gh pr create --repo {ORG}/{HOLDER} --base trunk "
                         f"--head {branch}"), line
    assert line.startswith("NEXT  git -C " if not flags else
                           "NEXT  gh pr create"), line
    assert git("status", "--porcelain", cwd=holder).stdout == ""
    assert git("rev-parse", "--abbrev-ref", "HEAD",
               cwd=holder).stdout.strip() == branch
