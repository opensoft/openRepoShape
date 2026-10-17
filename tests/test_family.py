# SPDX-License-Identifier: Apache-2.0
"""The FAMILY shape, end to end, into local bare repositories.

A family is a HOLDER: it pins member ASSEMBLY ROOTS as submodules under
`members/` and carries the utilities to fetch and bootstrap them together
(Brett Heap, 2026-09-04, about InkRouter). It is not a project — no spec leg,
no code leg — and membership confers nothing.

NO REAL REPOSITORY IS EVER CREATED and no network is used. The holder and both
members are bare repositories in a temporary directory, exactly as the rest of
this suite works.

A LOCAL-PATH SUBMODULE IS A `file://` CLONE, which git has refused by default
since the 2022 advisories. `family.py add --local-remote-dir` passes
`protocol.file.allow=always` itself; for the family's OWN `bootstrap.py` —
which runs a plain `git submodule update`, as it must in the real world — the
tests supply it through git's `GIT_CONFIG_COUNT` environment protocol. That is
a test-harness concession to using bare repositories as origins, not something
a real family ever needs.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys

import pytest

from conftest import (NO_BYTECODE, REPO, cloned_just_pushed, git, rmtree,
                      run_script)
#: The trailer helpers and the two lines a lane's run lands, imported from
#: the file that owns those rules rather than retyped — see
#: `tests/test_commit_trailers.py`.
from test_commit_trailers import (
    ENVIRONMENTS, NON_ASCII_BYTES, POSIX_ONLY, TRAILERS, argv_of, environment,
    message_bytes_of, message_of, trailer_bytes_of, trailers_of,
)
#: The renderer of the README line #148 made `update-shape.py apply` rewrite,
#: and the module that owns its tests, imported rather than retyped for the
#: same reason.
from test_update_shape import rendered_shape_line, strip_shape_block

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import Refusal, load_yaml, tree_digest  # noqa: E402
from shape_materialize import (  # noqa: E402
    SHAPE_REPOSITORY, readme_shape_lines, readme_trailing_shape_line,
)

FAMILY = REPO / "scripts" / "family.py"
DOCTOR = REPO / "shape-doctor.py"
SCAFFOLD = REPO / "scaffold-project.py"
UPDATE = REPO / "update-shape.py"
ORG = "InkRouter"
NAME = "InkRouter"
MEMBERS = ("IRRS", "IRSS")
#: A fourth InkRouter service, scaffolded and deliberately NOT added: the
#: tests that need to `add` something need one that is not a member yet, and
#: removing a member to make room would test `remove` by accident.
SPARE = "IRQS"

#: The branch the fixture grows the family on (#487). `add`, `bump` and
#: `remove` refuse to commit onto the holder's tracking branch, so the members
#: are added on a branch, as a person adds them for a pull request, and the
#: remote's `main` is then moved to it, as merging that pull request leaves
#: it. Every copy of the holder a test makes stands on this branch.
WORK_BRANCH = "family/members"

#: `git` reads one-off configuration out of the environment, which is how a
#: test gives a plain `git submodule update` permission to clone a local path
#: without the tool under test knowing anything about it.
ALLOW_FILE_PROTOCOL = {"GIT_CONFIG_COUNT": "1",
                       "GIT_CONFIG_KEY_0": "protocol.file.allow",
                       "GIT_CONFIG_VALUE_0": "always"}


def scaffold_member(base, project: str) -> None:
    result = run_script(
        SCAFFOLD, "--org", ORG, "--project", project,
        "--elected-by", "Test Human", "--elected-on", "2026-09-04",
        "--local-remote-dir", str(base / "remotes"),
        "--work-dir", str(base / "work"))
    assert result.returncode == 0, result.stderr + result.stdout


@pytest.fixture(scope="module")
def family(tmp_path_factory) -> dict:
    """One real family: init, then two scaffolded members added."""
    base = tmp_path_factory.mktemp("family")
    for project in (*MEMBERS, SPARE):
        scaffold_member(base, project)
        # A SECOND COMMIT in each member, so a pin can be moved to a real
        # commit that is not the tip. A test that pinned 40 zeros would prove
        # only that an unresolvable commit is refused, which is a different
        # property from the lockstep one.
        member = base / "work" / project
        (member / "NOTES.md").write_text("the member moved on\n")
        git("add", "--", "NOTES.md", cwd=member)
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
            "A second commit", cwd=member)
        git("push", "-q", "origin", "main", cwd=member)
    created = run_script(
        FAMILY, "init", "--org", ORG, "--family", NAME,
        "--created-by", "Test Human", "--created-on", "2026-09-04",
        "--local-remote-dir", str(base / "remotes"),
        "--work-dir", str(base / "fam"))
    assert created.returncode == 0, created.stderr + created.stdout
    root = base / "fam" / NAME
    git("switch", "-q", "-c", WORK_BRANCH, cwd=root)
    for project in MEMBERS:
        added = run_script(FAMILY, "add", "--family-root", str(root),
                           "--member", f"{ORG}/{project}",
                           "--local-remote-dir", str(base / "remotes"))
        assert added.returncode == 0, added.stderr + added.stdout
    git("push", "-q", "origin", f"{WORK_BRANCH}:main", cwd=root)
    return {"base": base, "root": root, "remotes": base / "remotes",
            "work": base / "work", "init": created}


@pytest.fixture
def holder(family, tmp_path):
    """A private, mutable copy of the family root."""
    target = tmp_path / NAME
    shutil.copytree(family["root"], target, symlinks=True)
    return target


def validate(root, *extra):
    return run_script(root / "scripts" / "validate-family.py", *extra,
                      cwd=root)


def manifest(root) -> dict:
    return load_yaml(root / "family.yaml")


def family_module():
    """`scripts/family.py` as a module, for the lookups that touch no disk."""
    spec = importlib.util.spec_from_file_location("family_under_test", FAMILY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rows_of(project_rows, root=REPO) -> object:
    """A `Family` over in-memory rows: `member` and `holding` read no disk."""
    return family_module().Family(
        root, {"name": NAME, "members": list(project_rows)})


def mount_twice(holder, remotes) -> None:
    """Pin IRRS a SECOND time, under a row of its own (#206).

    What a family holds after one project is mounted twice: a repository
    renamed at the forge and added under both names, or — on a case-sensitive
    host, before #206 — `add --member inkrouter/irrs` beside `InkRouter/IRRS`.
    The second row is real in every way the gate asks about: mounted, pinned
    at the commit it is mounted at, digested, and `project.yaml` inside it
    says the id the row says. It is spelled `IRRS2` rather than `irrs` so the
    fixture does not need two directories whose names differ only in case,
    which macOS and Windows hold as one.
    """
    git("-c", "protocol.file.allow=always", "submodule", "add", "-q", "--",
        str(remotes / "IRRS.git"), "members/IRRS2", cwd=holder)
    mounted = holder / "members" / "IRRS2"
    commit = git("rev-parse", "HEAD", cwd=mounted).stdout.strip()
    text = (holder / "family.yaml").read_text(encoding="utf-8")
    (holder / "family.yaml").write_text(
        text.rstrip("\n") + "\n" + "\n".join([
            "  - project: IRRS2",
            "    id: irrs",
            "    repository: InkRouter/IRRS2",
            "    path: members/IRRS2",
            "    pin:",
            "      revision_kind: commit",
            f'      commit: "{commit}"',
            "      digest_algorithm: sha256",
            "      digest_definition: sorted-ls-tree-r-v1",
            f'      tree_sha256: "{tree_digest(mounted, commit)}"',
        ]) + "\n", encoding="utf-8")
    git("add", "--", ".gitmodules", "members/IRRS2", "family.yaml",
        cwd=holder)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "Pin IRRS a second time", cwd=holder)


# --- init -------------------------------------------------------------------

def test_init_writes_a_family_manifest_and_nothing_leg_shaped(family):
    data = manifest(family["root"])
    assert data["kind"] == "family-manifest"
    assert data["schema_version"] == 1
    assert data["id"] == "inkrouter"
    assert data["name"] == NAME
    assert data["org"] == ORG
    assert data["repository"] == f"{ORG}/{NAME}"
    assert data["members_dir"] == "members"
    assert data["created_by"] == "Test Human"
    assert "legs" not in data, "a family is a holder; it has no legs"
    root = family["root"]
    assert not (root / "project.yaml").exists()
    assert not (root / "contracts" / "spec-pin.yaml").exists()
    assert not (root / "contracts" / "code-pin.yaml").exists()


def test_init_carries_the_shape_pin_over_its_own_copies(family):
    """The holder is self-contained the same way an assembly root is: copies,
    digest-pinned, so `update-shape.py` can re-sync them later."""
    root = family["root"]
    data = manifest(root)
    pin = load_yaml(root / "contracts" / "shape-pin.yaml")
    assert pin["kind"] == "pinned_contract_manifest"
    assert pin["materialization"] == "copied"
    assert pin["revision_kind"] == "commit"
    assert pin["commit"] == data["shape"]["commit"]
    assert pin["digests"]["tree_sha256"] == \
        data["shape"]["digests"]["tree_sha256"]
    rows = {row["path"] for row in pin["files"]}
    # 2026-09-04: `AGENTS-shape.md` joined the copies. The set is an EQUALITY
    # rather than a floor here on purpose — a holder carries a deliberately
    # smaller set than an assembly root does, and this is the assertion that
    # notices if the assembly root's list ever leaks into it — so a file added
    # to `FAMILY_COPIED_VERBATIM` is expected to move this line.
    #
    # 2026-09-05: `.gitattributes` joined them (#51). A holder's copies are
    # digest-pinned the same way a project's are, so it needs the same
    # statement about its own bytes — and the file is pinned rather than
    # merely shipped, because one that can be edited without the pin noticing
    # says nothing.
    #
    # 2026-09-09: `scripts/siblings.py` joined them (#76). The holder's
    # WORKSTATION utility is a copy like the validator and the bootstrap, and
    # it is PINNED for the same reason: it is the file `update-shape.py` then
    # offers to an existing holder as `upstream-added`, and a copy nothing
    # digests is a copy nobody can tell has been edited.
    assert rows == {"scripts/validate-family.py", "scripts/bootstrap.py",
                    "scripts/siblings.py",
                    "Makefile", ".gitignore", ".gitattributes",
                    ".github/workflows/validate.yml", "AGENTS-shape.md",
                    "scripts/repo_shape.py",
                    "contracts/repository-naming.yaml"}
    assert "scripts/validate-pins.py" not in rows, (
        "a family has no legs, so it does not carry the leg validator")


def test_the_rendered_readme_carries_exactly_one_line_the_rewriter_reads(
        family):
    """THE PARITY THE WHOLE OF #148 RESTS ON: what the template renders is
    what `shape_materialize.README_SHAPE_LINE_RE` matches.

    The template and the pattern are two files, and a reworded template would
    otherwise leave `update-shape.py apply` reporting `absent` for every
    holder in the estate — silently, and exactly as if the drift had been
    fixed. So the holder is rendered by the real materializer and the pattern
    is run over the result: one line, this standard's name, and the commit
    the pin records.

    AND THE OTHER HALF: an ASSEMBLY root renders no such line at all, which
    is why `apply` on a project reads `absent` rather than finding a sentence
    to rewrite. A member scaffolded by this same fixture is the evidence.
    """
    holder = (family["root"] / "README.md").read_text(encoding="utf-8")
    matches = readme_shape_lines(holder)
    assert len(matches) == 1, holder[-400:]
    assert matches[0]["repository"] == SHAPE_REPOSITORY
    assert matches[0]["commit"] == \
        load_yaml(family["root"] / "contracts" / "shape-pin.yaml")["commit"]
    assert matches[0].group(0) == rendered_shape_line(matches[0]["commit"])
    # AND THAT IT IS THE LAST LINE. `apply` moves the sha only in a line the
    # file ENDS with, so that anything higher up is read as an example rather
    # than as this root's claim (Copilot, PR #152); a template that grew a
    # section under this line would otherwise answer `absent` for every
    # holder in the estate, silently and exactly as if the drift were fixed.
    assert readme_trailing_shape_line(holder) is not None, holder[-400:]

    member = family["work"] / MEMBERS[0] / "README.md"
    assert readme_shape_lines(member.read_text(encoding="utf-8")) == [], (
        "an assembly root's README claims no shape commit, so there is "
        "nothing there to drift")


def test_init_copies_the_siblings_utility_and_the_makefile_target(family, monkeypatch):
    """THE HOLDER CARRIES THE UTILITY, not a second implementation of it.

    `make siblings` runs the copy; `family.py siblings` runs the very same
    file out of the standard (ruling 1b, 2026-09-09: one implementation, two
    entry points). So the copy must be byte-identical to the template, pinned
    by digest, executable like the other two scripts, and named by the
    Makefile the holder ships.
    """
    monkeypatch.syspath_prepend(str(REPO / "scripts"))
    from repo_shape import file_sha256
    root = family["root"]
    copied = root / "scripts" / "siblings.py"
    template = (REPO / "templates" / "family-root" / "scripts" /
                "siblings.py")
    assert copied.read_bytes() == template.read_bytes()
    rows = {row["path"]: row["sha256"].lower()
            for row in load_yaml(root / "contracts" / "shape-pin.yaml")["files"]}
    assert rows["scripts/siblings.py"] == file_sha256(copied)
    if os.name != "nt":
        assert copied.stat().st_mode & 0o111, (
            "`FAMILY_EXECUTABLE` names it, so the materializer chmods it")
    makefile = (root / "Makefile").read_text()
    assert "siblings:" in makefile
    assert "$(PYTHON) scripts/siblings.py" in makefile
    assert "make siblings" in (root / "README.md").read_text()
    assert "make siblings" in (root / "AGENTS-shape.md").read_text()


def test_init_writes_the_holders_agent_files(family, monkeypatch):
    """The holder gets its OWN pinned rules — a family has no legs, no leg
    pins and no lockstep workflow refs, so half of the assembly root's file
    would be instructions about things that are not here."""
    monkeypatch.syspath_prepend(str(REPO / "scripts"))
    from repo_shape import file_sha256
    root = family["root"]
    template = REPO / "templates" / "family-root" / "AGENTS-shape.md"
    copied = root / "AGENTS-shape.md"
    assert copied.read_bytes() == template.read_bytes()
    assert "{{" not in copied.read_text()

    rows = {row["path"]: row["sha256"].lower()
            for row in load_yaml(root / "contracts" / "shape-pin.yaml")["files"]}
    assert rows["AGENTS-shape.md"] == file_sha256(copied)

    flat = " ".join(copied.read_text().split())
    assert "a consumer deriving permission from them is defective" in flat
    for rule in ("members/<Project>", "family.py add", "family.py bump",
                 "family.py remove", "make bootstrap", "make validate",
                 "make pins", "update-shape.py", "--admin",
                 "--accept-local", "pull request",
                 # 2026-09-11 (#111): the procedure an agent follows is the
                 # one in the holder it is standing in, so `bump`'s trailers
                 # have to be HERE and not only in the standard's AGENTS.md.
                 "--trailer"):
        assert rule in flat, f"the holder's rules say nothing about {rule}"
    assert "no spec leg, no code leg and no `project.yaml`" in flat

    agents = (root / "AGENTS.md").read_text()
    assert agents.splitlines()[0] == (
        "Read AGENTS-shape.md first — the rules of this repository's shape.")
    assert NAME in agents
    assert "inkrouter" in agents
    assert ORG in agents
    assert "{{" not in agents
    assert (root / "CLAUDE.md").read_text() == "Read AGENTS.md.\n"
    assert "AGENTS.md" not in rows, (
        "the holder's own instructions are the holder's, not the shape's")
    assert "CLAUDE.md" not in rows, (
        "the holder's own instructions are the holder's, not the shape's")


def test_the_holder_says_what_its_bytes_are(family, monkeypatch):
    """A holder carries a digest pin over copies, so it carries the same
    statement about line endings an assembly root does (#51, 2026-09-05).
    Without it a clone under `core.autocrlf=true` digests CRLF against an LF
    row and `make validate` is red on files nobody touched."""
    monkeypatch.syspath_prepend(str(REPO / "scripts"))
    from repo_shape import file_sha256
    root = family["root"]
    copied = root / ".gitattributes"
    template = REPO / "templates" / "family-root" / ".gitattributes"
    assert copied.read_bytes() == template.read_bytes(), "verbatim, like the rest"
    assert b"\r" not in copied.read_bytes(), (
        "the file that says LF is itself written LF, on every platform")
    assert "* text=auto eol=lf" in copied.read_text()
    rows = {row["path"]: row["sha256"].lower()
            for row in load_yaml(root / "contracts" / "shape-pin.yaml")["files"]}
    assert rows[".gitattributes"] == file_sha256(copied)


def test_init_is_one_commit_and_the_remote_has_it(family):
    root = family["root"]
    assert int(git("rev-list", "--count", "HEAD", cwd=root).stdout) == 3, (
        "one commit for the holder and one per member added")
    bare = family["remotes"] / f"{NAME}.git"
    assert bare.is_dir()
    assert git("rev-parse", "main", cwd=bare).stdout.strip() == \
        git("rev-parse", "HEAD", cwd=root).stdout.strip()


def test_init_dry_run_creates_nothing(tmp_path):
    result = run_script(FAMILY, "init", "--org", ORG, "--family", "Contoso",
                        "--created-by", "Test Human",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"), "--dry-run")
    assert result.returncode == 0, result.stderr
    assert "--dry-run: nothing was created." in result.stdout
    assert not (tmp_path / "remotes").exists()
    assert not (tmp_path / "work").exists()


def test_init_plans_the_topic_and_skips_it_against_local_remotes(family):
    """The holder carries `xf-project-<family-id>` exactly as a scaffolded
    project's three repositories do — and `gh` is never called offline, which
    is what keeps this suite free of the network."""
    assert "topics       skipped for local remotes" in family["init"].stdout
    assert "gh repo edit" not in family["init"].stdout


def test_init_dry_run_plans_the_gh_topic_command_for_a_real_org(
        tmp_path, monkeypatch, capsys):
    """No `--local-remote-dir`, so the plan is the REAL one — and a dry run
    prints it before anything is created. It also asks whether the holder
    exists (#537), which against GitHub is `gh repo view`: asked in process
    here, of a stand-in that says it does not, so no `gh` is run."""
    module = family_module()
    asked = []
    monkeypatch.setattr(module, "_remote_is_empty",
                        lambda repository: asked.append(repository))
    code = module.main(["init", "--org", ORG, "--family", "Contoso",
                        "--created-by", "Test Human",
                        "--work-dir", str(tmp_path / "work"), "--dry-run"])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert "topics       gh repo edit --add-topic xf-project-contoso" \
        in captured.out
    assert asked == [f"{ORG}/Contoso"]
    assert not (tmp_path / "work").exists()


def test_init_refuses_a_name_that_is_not_a_holder_form(tmp_path):
    result = run_script(FAMILY, "init", "--org", ORG, "--family", "Ink-Router",
                        "--created-by", "Test Human",
                        "--local-remote-dir", str(tmp_path / "remotes"))
    assert result.returncode == 2
    assert "naming-unclassified" in result.stderr
    assert not (tmp_path / "remotes").exists()


def test_init_refuses_a_neutral_product_name(tmp_path):
    """`open<Product>` is unambiguous by construction and a declaration
    cannot make it a holder."""
    result = run_script(FAMILY, "init", "--org", ORG, "--family", "openChart",
                        "--created-by", "Test Human",
                        "--local-remote-dir", str(tmp_path / "remotes"))
    assert result.returncode == 2
    assert "naming-not-a-family" in result.stderr


def test_init_reuses_an_empty_repository_and_refuses_a_live_one(tmp_path):
    """`InkRouter` in the InkRouter org is an EMPTY repository today: a name
    somebody reserved, which is not a project somebody started."""
    remotes = tmp_path / "remotes"
    remotes.mkdir()
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main",
                    str(remotes / "Contoso.git")], check=True)
    refused = run_script(FAMILY, "init", "--org", ORG, "--family", "Contoso",
                         "--created-by", "Test Human",
                         "--local-remote-dir", str(remotes),
                         "--work-dir", str(tmp_path / "w1"))
    assert refused.returncode == 2
    assert "family-remote-exists" in refused.stderr
    assert "--reuse-empty-repo" in refused.stderr

    reused = run_script(FAMILY, "init", "--org", ORG, "--family", "Contoso",
                        "--created-by", "Test Human", "--reuse-empty-repo",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / "w2"))
    assert reused.returncode == 0, reused.stderr + reused.stdout
    assert "reuse" in reused.stdout

    again = run_script(FAMILY, "init", "--org", ORG, "--family", "Contoso",
                       "--created-by", "Test Human", "--reuse-empty-repo",
                       "--local-remote-dir", str(remotes),
                       "--work-dir", str(tmp_path / "w3"))
    assert again.returncode == 2
    assert "has commits" in again.stderr
    assert "There is no --force" in again.stderr


# --- add --------------------------------------------------------------------

def test_each_member_is_mounted_and_pinned_twice(family):
    root = family["root"]
    rows = {row["project"]: row for row in manifest(root)["members"]}
    assert sorted(rows) == list(MEMBERS)
    for project, row in rows.items():
        assert row["repository"] == f"{ORG}/{project}"
        assert row["path"] == f"members/{project}"
        assert row["id"] == project.lower()
        assert row["pin"]["revision_kind"] == "commit"
        assert row["pin"]["digest_definition"] == "sorted-ls-tree-r-v1"
        gitlink = git("rev-parse", f"HEAD:members/{project}",
                      cwd=root).stdout.strip()
        assert gitlink == row["pin"]["commit"], (
            "the gitlink and the pin move together or not")
        assert row["pin"]["tree_sha256"] == \
            tree_digest(root / "members" / project, gitlink)


def test_add_writes_exactly_one_commit_with_explicit_pathspecs(family):
    committed = set(git("show", "--name-only", "--format=", "HEAD",
                        cwd=family["root"]).stdout.split())
    assert committed == {".gitmodules", "members/IRSS", "family.yaml"}


def test_add_refuses_a_member_that_is_already_there(family, tmp_path):
    holder = tmp_path / NAME
    shutil.copytree(family["root"], holder, symlinks=True)
    result = run_script(FAMILY, "add", "--family-root", str(holder),
                        "--member", f"{ORG}/IRRS",
                        "--local-remote-dir", str(family["remotes"]))
    assert result.returncode == 2
    assert "member-already-present" in result.stderr
    assert "bump" in result.stderr


@pytest.mark.parametrize("spelling", [
    "inkrouter/irrs",       # the whole name, folded: issue #206's own
    "INKROUTER/IRRS",
    "InkRouter/irrs",       # only the repository
    "OtherOrg/Irrs",        # another owner: the project name is the row's too
])
def test_add_refuses_a_spelling_of_a_member_the_family_already_pins(
        family, holder, spelling):
    """GITHUB RESOLVES `owner/repo` CASE-INSENSITIVELY (#149, #206).
    `--member inkrouter/irrs` on a family that pins `InkRouter/IRRS` named
    the same repository, mounted it a second time and wrote a second row —
    and both gates passed. It is `member-already-present`, naming the row
    that is already there in the spelling the row uses, and nothing is
    mounted, staged or written."""
    head = git("rev-parse", "HEAD", cwd=holder).stdout
    status = git("status", "--porcelain", cwd=holder).stdout
    text = (holder / "family.yaml").read_bytes()
    result = run_script(FAMILY, "add", "--family-root", str(holder),
                        "--member", spelling,
                        "--local-remote-dir", str(family["remotes"]))
    assert result.returncode == 2, result.stderr + result.stdout
    assert "REFUSED member-already-present" in result.stderr
    assert "the row IRRS pins InkRouter/IRRS" in result.stderr
    assert "`family.py bump --member IRRS --to <commit>`" in result.stderr
    assert "mounting" not in result.stdout
    assert git("rev-parse", "HEAD", cwd=holder).stdout == head
    assert git("status", "--porcelain", cwd=holder).stdout == status
    assert (holder / "family.yaml").read_bytes() == text
    # `listdir`, not `exists`: macOS and Windows hold `members/irrs` and
    # `members/IRRS` as one directory, which is not what is being asked.
    assert sorted(os.listdir(holder / "members")) == list(MEMBERS)


def test_add_of_a_member_that_is_not_there_is_unchanged_by_the_case_rule(
        family, holder):
    """The comparison is a NAME, not a prefix and not a near miss: `IRQS` is
    not `IRRS`, and it is mounted and recorded in the spelling it was given."""
    result = run_script(FAMILY, "add", "--family-root", str(holder),
                        "--member", f"{ORG}/{SPARE}",
                        "--local-remote-dir", str(family["remotes"]))
    assert result.returncode == 0, result.stderr + result.stdout
    rows = {r["project"]: r for r in manifest(holder)["members"]}
    assert sorted(rows) == sorted([*MEMBERS, SPARE])
    assert rows[SPARE]["repository"] == f"{ORG}/{SPARE}"
    assert rows[SPARE]["path"] == f"members/{SPARE}"
    assert validate(holder).returncode == 0


def test_member_and_holding_name_the_row_in_its_own_spelling():
    """`Family.member` and `Family.holding`, over rows and no disk."""
    irrs = {"project": "IRRS", "repository": "InkRouter/IRRS"}
    irss = {"project": "IRSS", "repository": "InkRouter/IRSS"}
    both = rows_of([irrs, irss])
    assert both.member("IRRS") is irrs
    assert both.member("irrs") is irrs, "the forge folds the case"
    assert both.member("IRQS") is None
    assert both.member("IRR") is None and both.member("IRRSS") is None
    assert both.holding("inkrouter/irrs", "irrs") is irrs
    assert both.holding("OtherOrg/IRRS", "IRRS") is irrs
    assert both.holding(f"{ORG}/{SPARE}", SPARE) is None

    # A ROW THAT NAMES ITS REPOSITORY UNDER ANOTHER PROJECT NAME — hand-made,
    # which `validate-family.py` calls `member-repository-name` — still pins
    # that repository, and `add` finds it by the repository alone.
    alias = {"project": "Alias", "repository": "InkRouter/IRRS"}
    assert rows_of([alias]).member("irrs") is None
    assert rows_of([alias]).holding("inkrouter/irrs", "irrs") is alias


def test_member_prefers_the_exact_spelling_and_refuses_to_guess_between_two():
    """A family a pre-#206 `add` pinned twice holds `IRRS` AND `irrs`. Naming
    either exactly reaches that row, which is how the extra one is removed;
    a third spelling fits both, and bumping the wrong one is worse than
    stopping."""
    module = family_module()
    upper = {"project": "IRRS", "repository": "InkRouter/IRRS"}
    lower = {"project": "irrs", "repository": "inkrouter/irrs"}
    twice = rows_of([upper, lower])
    assert twice.member("IRRS") is upper
    assert twice.member("irrs") is lower
    with pytest.raises(module.Refusal) as refused:
        twice.member("Irrs")
    assert refused.value.code == "member-ambiguous"
    assert "IRRS, irrs" in refused.value.detail


def test_add_refuses_a_bare_member_name(family, tmp_path):
    holder = tmp_path / NAME
    shutil.copytree(family["root"], holder, symlinks=True)
    result = run_script(FAMILY, "add", "--family-root", str(holder),
                        "--member", "IRRS",
                        "--local-remote-dir", str(family["remotes"]))
    assert result.returncode == 2
    assert "member-malformed" in result.stderr


def test_add_refuses_a_repository_that_is_not_an_assembly_root(family,
                                                               tmp_path):
    """A FAMILY PINS ASSEMBLY ROOTS, never legs: `IRRS-spec` has no
    `project.yaml`, because it is half of a project rather than one."""
    holder = tmp_path / NAME
    shutil.copytree(family["root"], holder, symlinks=True)
    result = run_script(FAMILY, "add", "--family-root", str(holder),
                        "--member", f"{ORG}/IRRS-spec",
                        "--local-remote-dir", str(family["remotes"]))
    assert result.returncode == 2
    assert "member-not-a-project" in result.stderr
    assert "ASSEMBLY ROOTS" in result.stderr


def test_add_at_pins_the_named_commit(family, tmp_path):
    """`--at` pins a commit that is not the tip, which is what a family does
    when a member has moved on and this family has not followed."""
    holder = tmp_path / NAME
    shutil.copytree(family["root"], holder, symlinks=True)
    wanted = git("rev-parse", "main~1",
                 cwd=family["remotes"] / f"{SPARE}.git").stdout.strip()
    tip = git("rev-parse", "main",
              cwd=family["remotes"] / f"{SPARE}.git").stdout.strip()
    result = run_script(FAMILY, "add", "--family-root", str(holder),
                        "--member", f"{ORG}/{SPARE}", "--at", wanted,
                        "--local-remote-dir", str(family["remotes"]))
    assert result.returncode == 0, result.stderr + result.stdout
    row = {r["project"]: r for r in manifest(holder)["members"]}[SPARE]
    assert row["pin"]["commit"] == wanted != tip
    assert git("rev-parse", f"HEAD:members/{SPARE}",
               cwd=holder).stdout.strip() == wanted
    assert validate(holder).returncode == 0


def test_add_refuses_an_abbreviated_commit(family, tmp_path):
    holder = tmp_path / NAME
    shutil.copytree(family["root"], holder, symlinks=True)
    result = run_script(FAMILY, "add", "--family-root", str(holder),
                        "--member", f"{ORG}/{SPARE}", "--at", "abc1234",
                        "--local-remote-dir", str(family["remotes"]))
    assert result.returncode == 2
    assert "member-at-not-a-commit" in result.stderr
    assert "A tag can be moved" in result.stderr


# --- validate ---------------------------------------------------------------

def test_the_family_passes_its_own_gate(family):
    result = validate(family["root"])
    assert result.returncode == 0, result.stderr + result.stdout
    assert "family ok: InkRouter (inkrouter), 2 member(s)" in result.stdout
    assert "InkRouter: family (declared by family.yaml)" in result.stdout


def test_make_pins_checks_the_lockstep_alone(family):
    proc = subprocess.run(["make", "pins"], cwd=str(family["root"]),
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "gitlink == pin" in proc.stdout
    assert "copied shape file(s)" not in proc.stdout, (
        "--pins is the member lockstep alone")


def test_validate_refuses_a_missing_gitlink(holder):
    """A row naming a member this repository does not record as a submodule
    is a claim about a tree that is not here."""
    git("rm", "-r", "-q", "-f", "--", "members/IRRS", cwd=holder)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "Drop the gitlink but keep the row", cwd=holder)
    result = validate(holder)
    assert result.returncode == 2
    assert "member-gitlink-absent" in result.stderr
    assert "family.py add" in result.stderr


def test_validate_finds_a_pin_that_disagrees_with_the_gitlink(holder):
    """THE LOCKSTEP RULE. Moving the pin alone is exactly the failure the
    xFactory aggregation shipped seven times in a row."""
    text = (holder / "family.yaml").read_text()
    row = {r["project"]: r for r in manifest(holder)["members"]}["IRRS"]
    # A REAL commit that is not the gitlink: the member's own parent. Pinning
    # 40 zeros would prove only that an unresolvable commit is refused, which
    # is a different property.
    parent = git("rev-parse", "HEAD~1",
                 cwd=holder / "members" / "IRRS").stdout.strip()
    (holder / "family.yaml").write_text(
        text.replace(row["pin"]["commit"], parent))
    result = validate(holder)
    assert result.returncode == 1
    assert "member-gitlink-mismatch" in result.stderr
    assert "THE LOCKSTEP RULE" in result.stderr


def test_validate_accepts_a_member_bump_that_is_staged_but_not_committed(holder):
    """The family's half of the same reading: `recorded_gitlink` asks the
    INDEX first, so a bump whose gitlink is staged and whose row moved with it
    validates BEFORE it is committed, rather than reporting the commit it is
    about to replace. That is when a person runs `make validate` — after
    staging, to find out whether the commit they are about to make is in
    lockstep.

    The member's new commit is EMPTY, so `pin.tree_sha256` still recomputes
    and the gitlink is the only fact that moved.
    """
    member = holder / "members" / "IRRS"
    before = git("rev-parse", "HEAD:members/IRRS", cwd=holder).stdout.strip()
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
        "--allow-empty", "-m", "The member moved again", cwd=member)
    after = git("rev-parse", "HEAD", cwd=member).stdout.strip()
    git("add", "--", "members/IRRS", cwd=holder)  # staged, NOT committed
    manifest_path = holder / "family.yaml"
    text = manifest_path.read_text()
    assert text.count(before) == 1, "fixture drift: IRRS's pin is not unique"
    manifest_path.write_text(text.replace(before, after, 1))
    result = validate(holder)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "gitlink == pin" in result.stdout


def test_validate_finds_a_digest_that_does_not_recompute(holder):
    text = (holder / "family.yaml").read_text()
    row = {r["project"]: r for r in manifest(holder)["members"]}["IRSS"]
    (holder / "family.yaml").write_text(
        text.replace(row["pin"]["tree_sha256"], "b" * 64))
    result = validate(holder)
    assert result.returncode == 1
    assert "member-digest-mismatch" in result.stderr


def test_validate_finds_an_id_that_is_not_the_project_mounted_there(holder):
    """A repository at the right commit is not by itself the project the row
    claims: `project.yaml` inside the member is the source."""
    text = (holder / "family.yaml").read_text()
    (holder / "family.yaml").write_text(
        text.replace("    id: irrs\n", "    id: something-else\n"))
    result = validate(holder)
    assert result.returncode == 1
    assert "member-id-mismatch" in result.stderr
    assert "the source" in result.stderr


def test_validate_finds_one_project_pinned_twice(family, holder):
    """TWO ROWS, ONE `id:` — a project mounted twice, whichever way its
    repository was spelled (#206). Everything else about the second row is
    in order, so this is the only finding there is, and `--pins` (what
    `make pins` runs) asks it too."""
    assert validate(holder).returncode == 0
    mount_twice(holder, family["remotes"])
    result = validate(holder)
    assert result.returncode == 1, result.stderr + result.stdout
    assert result.stderr.count("FINDING") == 1, result.stderr
    assert "FINDING member-duplicate-id: IRRS2 and IRRS both record id " \
        "'irrs'" in result.stderr
    assert "one project is pinned twice" in result.stderr
    assert "--member IRRS2` takes the later row, IRRS2, out" in result.stderr
    assert validate(holder, "--pins").returncode == 1


def test_validate_finds_one_project_pinned_twice_under_no_members(family,
                                                                  holder):
    """`--no-members` is what a private family's CI runs when its members
    cannot be checked out. Two rows with one `id:` is a fact of `family.yaml`
    alone, so that run still finds it, beside the members it skips."""
    mount_twice(holder, family["remotes"])
    result = validate(holder, "--no-members")
    assert result.returncode == 1, result.stderr + result.stdout
    assert result.stderr.count("FINDING") == 1, result.stderr
    assert "FINDING member-duplicate-id: IRRS2 and IRRS both record id " \
        "'irrs'" in result.stderr
    assert "member(s) SKIPPED (--no-members)" in result.stdout


def test_the_duplicate_id_remediation_runs_as_printed(family, holder):
    """The finding names a command, and that command is the repair: typed
    from a checkout of openRepoShape exactly as printed, it takes the later
    row out and the gate goes green. It carries the `--family-root` that
    `remove` requires and the row's own spelling, not a placeholder."""
    mount_twice(holder, family["remotes"])
    found = validate(holder)
    assert found.returncode == 1, found.stderr + found.stdout
    commands = re.findall(r"`([^`]*scripts/family\.py remove [^`]*)`",
                          found.stderr)
    assert len(commands) == 1, found.stderr
    argv = shlex.split(commands[0])
    assert argv[0] in ("python3", "python"), commands[0]
    assert argv[1] == "scripts/family.py", commands[0]
    assert argv[argv.index("--member") + 1] == "IRRS2", commands[0]
    assert os.path.samefile(argv[argv.index("--family-root") + 1], holder)
    removed = run_script(REPO / argv[1], *argv[2:], cwd=REPO)
    assert removed.returncode == 0, removed.stderr + removed.stdout
    assert [r["project"] for r in manifest(holder)["members"]] == list(MEMBERS)
    assert validate(holder).returncode == 0


def test_an_exact_duplicate_row_is_one_finding(family, holder):
    """One row written twice, byte for byte, is `member-duplicate`'s finding
    and only that. `member-duplicate-id` saying it too would be one fault
    reported twice, and its `remove` would take out BOTH rows, because
    `remove` drops every row spelled the way it was given."""
    family_root = family_module().Family.open(holder)
    rows = family_root.members
    irrs = next(row for row in rows if row["project"] == "IRRS")
    family_root.write_members([*rows, dict(irrs)])
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam",
        "Write IRRS's row twice", cwd=holder)
    for extra in ((), ("--pins",)):
        result = validate(holder, *extra)
        assert result.returncode == 1, result.stderr + result.stdout
        assert result.stderr.count("FINDING") == 1, result.stderr
        assert "FINDING member-duplicate: IRRS appears more than once" \
            in result.stderr
        assert "member-duplicate-id" not in result.stderr


def test_the_doctor_reports_a_project_pinned_twice(family, holder):
    """The doctor's `family` row IS the holder's own validator, so the
    finding reaches it — it is not a second check somebody has to remember."""
    mount_twice(holder, family["remotes"])
    result = run_script(DOCTOR, "--root", str(holder), "--json")
    assert result.returncode != 0, result.stdout
    rows = {row["id"]: row for row in json.loads(result.stdout)["rows"]}
    assert rows["family"]["status"] == "FINDING"
    assert "validate-family.py" in rows["family"]["reason"]


def test_validate_finds_an_edited_shape_copy(holder):
    copy = holder / "scripts" / "validate-family.py"
    copy.write_text(copy.read_text() + "\n# edited in place\n")
    result = validate(holder)
    assert result.returncode == 1
    assert "shape-copy-drift" in result.stderr
    assert "carry the change upstream" in result.stderr


def test_validate_refuses_a_repository_that_is_not_a_family(project):
    """A project runs `validate-manifest.py`; the family validator says so
    rather than reporting an empty family."""
    shutil.copy(REPO / "templates" / "family-root" / "scripts" /
                "validate-family.py", project / "scripts")
    result = run_script(project / "scripts" / "validate-family.py",
                        cwd=project)
    assert result.returncode == 2
    assert "family-manifest-missing" in result.stderr


def test_an_empty_family_is_valid(tmp_path):
    """A family with no members yet is empty, not wrong."""
    created = run_script(FAMILY, "init", "--org", ORG, "--family", "Contoso",
                         "--created-by", "Test Human",
                         "--local-remote-dir", str(tmp_path / "remotes"),
                         "--work-dir", str(tmp_path / "work"))
    assert created.returncode == 0, created.stderr + created.stdout
    result = validate(tmp_path / "work" / "Contoso")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "0 member(s)" in result.stdout


# --- bump -------------------------------------------------------------------

def test_bump_moves_the_gitlink_and_the_pin_together(family, tmp_path):
    holder = tmp_path / NAME
    shutil.copytree(family["root"], holder, symlinks=True)
    member = family["work"] / "IRRS"
    (member / "MOVED.md").write_text("the member advanced\n")
    git("add", "--", "MOVED.md", cwd=member)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "Advance the member", cwd=member)
    git("push", "-q", "origin", "main", cwd=member)
    moved = git("rev-parse", "HEAD", cwd=member).stdout.strip()

    was = {r["project"]: r for r in manifest(holder)["members"]}["IRRS"]
    result = run_script(FAMILY, "bump", "--family-root", str(holder),
                        "--member", "IRRS", "--to", moved)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "nothing to do" not in result.stdout, (
        "a bump that moves the pin is not the one #210 made say so")

    row = {r["project"]: r for r in manifest(holder)["members"]}["IRRS"]
    assert row["pin"]["commit"] == moved != was["pin"]["commit"]
    assert git("rev-parse", "HEAD:members/IRRS",
               cwd=holder).stdout.strip() == moved
    committed = set(git("show", "--name-only", "--format=", "HEAD",
                        cwd=holder).stdout.split())
    assert committed == {"members/IRRS", "family.yaml"}
    assert validate(holder).returncode == 0
    # Undo it in the shared bare repository, so the module fixture's own
    # members stay where the other tests found them.
    git("reset", "-q", "--hard", "HEAD~1", cwd=member)
    git("push", "-q", "--force", "origin", "main", cwd=member)


def test_bump_refuses_a_member_that_is_not_there(holder):
    result = run_script(FAMILY, "bump", "--family-root", str(holder),
                        "--member", "Nope", "--to", "0" * 40)
    assert result.returncode == 2
    assert "member-unknown" in result.stderr


def test_bump_finds_a_member_in_any_case_and_keeps_the_rows_spelling(
        family, holder):
    """`bump --member irss` used to refuse `member-unknown` and recommend
    `family.py add --member <org>/irss` — which is the duplicate (#206). The
    row is found, and the row's spelling is the one written and mounted."""
    older = git("rev-parse", "main~1",
                cwd=family["remotes"] / "IRSS.git").stdout.strip()
    was = {r["project"]: r for r in manifest(holder)["members"]}["IRSS"]
    assert was["pin"]["commit"] != older
    result = run_script(FAMILY, "bump", "--family-root", str(holder),
                        "--member", "irss", "--to", older)
    assert result.returncode == 0, result.stderr + result.stdout
    rows = {r["project"]: r for r in manifest(holder)["members"]}
    assert sorted(rows) == list(MEMBERS), "no second row, in either spelling"
    assert rows["IRSS"]["pin"]["commit"] == older
    assert rows["IRSS"]["path"] == "members/IRSS"
    assert git("rev-parse", "HEAD:members/IRSS",
               cwd=holder).stdout.strip() == older
    assert message_of(holder).startswith("Bump IRSS to ")
    assert set(git("show", "--name-only", "--format=", "HEAD",
                   cwd=holder).stdout.split()) == {"members/IRSS",
                                                   "family.yaml"}
    assert validate(holder).returncode == 0


def test_bump_refuses_a_tag(holder):
    result = run_script(FAMILY, "bump", "--family-root", str(holder),
                        "--member", "IRRS", "--to", "v1.0.0")
    assert result.returncode == 2
    assert "member-to-not-a-commit" in result.stderr


# --- bump to the commit already pinned (#210) -------------------------------

def nothing_to_do_line(project: str, commit: str) -> str:
    """The sentence `bump-leg.py` answers the same re-run with, repository
    first, so a lane or script reads one wording from either tool."""
    return (f"nothing to do: {ORG}/{project} is already pinned at "
            f"{commit[:12]} and every fact agrees.")


def pushed_from_the_mount(member, commit: str) -> None:
    """`commit`, made in the holder's own mount `member`, PUSHED to a branch
    of the member's remote, as a person pushes one before they bump it
    (#613).

    `bump --to` refuses a commit no branch of the member's remote reaches,
    `member-to-local-only`, as `bump-leg.py` refuses its twin, so a commit a
    test bumps to is pushed first. NOT TO THE FIXTURE'S OWN REMOTE: every
    holder is a copy of one module family, and the other tests read its bare
    remotes (`older` is their `main~1`). The remote is a bare repository of
    the test's own beside the holder, named for the holder and the member,
    made on the first push with the member's `main` as the mount last
    fetched it; the mount's `origin` is pointed at it, so `bump`'s own fetch
    reads it, and each commit goes to a branch named for it.
    """
    holder = member.parents[1]
    remote = holder.parent / f"{holder.name}-{member.name}-origin.git"
    if not remote.exists():
        git("init", "-q", "--bare", str(remote), cwd=holder.parent)
        git("push", "-q", str(remote),
            "refs/remotes/origin/main:refs/heads/main", cwd=member)
        git("remote", "set-url", "origin", str(remote), cwd=member)
    git("push", "-q", "origin", f"{commit}:refs/heads/pushed-{commit[:12]}",
        cwd=member)


def commit_in_member(member, message: str = "The member moved again") -> str:
    """An EMPTY commit on top of the member's HEAD: a new commit whose tree is
    the old one's, so `pin.tree_sha256` still recomputes and the gitlink is the
    only fact that moves. PUSHED (`pushed_from_the_mount`, #613), so a bump to
    it is a bump to a commit the member's remote has. Returns its sha."""
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
        "--allow-empty", "-m", message, cwd=member)
    made = git("rev-parse", "HEAD", cwd=member).stdout.strip()
    pushed_from_the_mount(member, made)
    return made


@pytest.mark.parametrize("extra", [
    (), ("--trailer", TRAILERS[0], "--trailer", TRAILERS[1])],
    ids=["plain", "with-trailers"])
def test_bump_to_the_commit_already_pinned_is_nothing_to_do(holder, extra):
    """A re-run of a bump that already landed. It used to check the member out
    at the commit, rewrite the same row and hand `git commit` nothing, which
    exited 1 and reached `main` as "REFUSED a git or gh command failed", exit
    2 — a refusal, where `family.py` documents exit 1 for nothing and
    `bump-leg.py` answers the same re-run with `nothing to do` (#210).

    NOTHING IS WRITTEN: no commit, no staged path, not one byte of
    `family.yaml`. A lane re-runs a bump with its `Lane:` and `Co-Authored-By:`
    trailers, so the run with them is the one that has to read the same.
    """
    pinned = git("rev-parse", "HEAD:members/IRRS", cwd=holder).stdout.strip()
    row = {r["project"]: r for r in manifest(holder)["members"]}["IRRS"]
    assert row["pin"]["commit"] == pinned, "fixture drift: gitlink != pin"
    head = git("rev-parse", "HEAD", cwd=holder).stdout.strip()
    status = git("status", "--porcelain", cwd=holder).stdout
    before = (holder / "family.yaml").read_bytes()

    result = run_script(FAMILY, "bump", "--family-root", str(holder),
                        "--member", "IRRS", "--to", pinned, *extra)

    assert result.returncode == 1, result.stderr + result.stdout
    assert nothing_to_do_line("IRRS", pinned) in result.stdout
    assert result.stderr == "", (
        "nothing to do is not a refusal, and says nothing on stderr")
    assert "REFUSED" not in result.stdout + result.stderr
    assert "committed" not in result.stdout
    assert git("rev-parse", "HEAD", cwd=holder).stdout.strip() == head, (
        "no commit, not even an empty one")
    assert git("status", "--porcelain", cwd=holder).stdout == status == ""
    assert (holder / "family.yaml").read_bytes() == before
    assert validate(holder).returncode == 0


def test_bump_to_the_commit_already_pinned_ignores_what_the_member_holds(
        holder):
    """The member's own untracked and modified files are not something the
    holder's commit can record: `git commit` finds nothing to commit with them
    there, so a bump that asked `git diff` without `--ignore-submodules=dirty`
    would have gone on to commit and been refused again (#210)."""
    member = holder / "members" / "IRRS"
    pinned = git("rev-parse", "HEAD:members/IRRS", cwd=holder).stdout.strip()
    (member / "UNTRACKED.md").write_text("left lying in the mount\n")
    (member / "NOTES.md").write_text("edited in place\n")
    head = git("rev-parse", "HEAD", cwd=holder).stdout.strip()

    result = run_script(FAMILY, "bump", "--family-root", str(holder),
                        "--member", "IRRS", "--to", pinned)

    assert result.returncode == 1, result.stderr + result.stdout
    assert nothing_to_do_line("IRRS", pinned) in result.stdout
    assert git("rev-parse", "HEAD", cwd=holder).stdout.strip() == head
    assert (member / "UNTRACKED.md").is_file(), "the member's files stay"
    assert (member / "NOTES.md").read_text() == "edited in place\n"


def test_bump_to_the_commit_already_pinned_leaves_an_uncommitted_edit_alone(
        holder):
    """An uncommitted edit to the `members:` block is not this run's to
    discard, however wrong it is. The rewrite equals `HEAD`, so there would be
    nothing to record; since #684 `bump` refuses the edit before that, as a
    `family.yaml` holding a change HEAD does not, and leaves it where it is.
    `git status` says the same before and after."""
    pinned = git("rev-parse", "HEAD:members/IRRS", cwd=holder).stdout.strip()
    manifest_path = holder / "family.yaml"
    manifest_path.write_text(manifest_path.read_text().replace(
        "    id: irrs\n", "    id: something-else\n"))
    edited = manifest_path.read_bytes()
    status = git("status", "--porcelain", cwd=holder).stdout
    assert status.strip() == "M family.yaml", status

    result = run_script(FAMILY, "bump", "--family-root", str(holder),
                        "--member", "IRRS", "--to", pinned)

    assert result.returncode == 2, result.stderr + result.stdout
    assert result.stdout == ""
    assert result.stderr.startswith("REFUSED family-manifest-uncommitted: ")
    assert manifest_path.read_bytes() == edited
    assert git("status", "--porcelain", cwd=holder).stdout == status


def test_bump_to_the_pinned_commit_unstages_a_stray_gitlink_and_says_nothing(
        holder):
    """THE VALIDATOR'S OWN REMEDY, followed with the pinned commit. Somebody
    moved the member and ran `git add members/IRRS` without committing:
    `validate-family.py` reads the INDEX first, reports
    `member-gitlink-mismatch` and names `family.py bump --member <Project> --to
    <commit>` as the repair. `bump` checks the member out at the pinned commit,
    which is HEAD's gitlink, but the index still differs from HEAD, so
    `git diff HEAD` found something and `git commit` then did not: the refusal
    #210 is about, exit 2, reached through the remedy. The gitlink is
    re-staged before git is asked, the index agrees with HEAD again, and there
    is nothing to record (#210)."""
    member = holder / "members" / "IRRS"
    pinned = git("rev-parse", "HEAD:members/IRRS", cwd=holder).stdout.strip()
    stray = commit_in_member(member, "A stray move, staged and never committed")
    git("add", "--", "members/IRRS", cwd=holder)
    assert git("ls-files", "-s", "--", "members/IRRS",
               cwd=holder).stdout.split()[1] == stray, "fixture drift"
    broken = validate(holder)
    assert broken.returncode == 1
    assert "member-gitlink-mismatch" in broken.stderr
    head = git("rev-parse", "HEAD", cwd=holder).stdout.strip()
    before = (holder / "family.yaml").read_bytes()

    result = run_script(FAMILY, "bump", "--family-root", str(holder),
                        "--member", "IRRS", "--to", pinned)

    assert result.returncode == 1, result.stderr + result.stdout
    assert nothing_to_do_line("IRRS", pinned) in result.stdout
    assert "REFUSED" not in result.stdout + result.stderr
    assert git("rev-parse", "HEAD", cwd=holder).stdout.strip() == head
    assert git("ls-files", "-s", "--", "members/IRRS",
               cwd=holder).stdout.split()[1] == pinned
    assert git("status", "--porcelain", cwd=holder).stdout == ""
    assert (holder / "family.yaml").read_bytes() == before
    assert validate(holder).returncode == 0


def test_bump_finishes_a_bump_an_earlier_run_staged_and_did_not_commit(holder):
    """THE MANIFEST ALREADY NAMES `--to`, and there is still something to
    commit: a run that wrote the row and staged both paths and then died
    before `git commit` — a hook that refused, a lock — leaves exactly this.
    Reading `was == --to` as "nothing to do" would call the half-finished bump
    done and leave the commit for somebody to make by hand (#210). Since #684
    the staged `family.yaml` is refused first, as a change HEAD does not hold,
    and with the gitlink staged beside it the refusal names one way out
    alone: `git checkout HEAD -- family.yaml`, which leaves the gitlink
    staged, and the same bump then finishes in ONE commit of both paths.
    (`git commit -- family.yaml` would commit the row without its
    gitlink.)"""
    member = holder / "members" / "IRRS"
    before = git("rev-parse", "HEAD:members/IRRS", cwd=holder).stdout.strip()
    after = commit_in_member(member)
    manifest_path = holder / "family.yaml"
    text = manifest_path.read_text()
    assert text.count(before) == 1, "fixture drift: IRRS's pin is not unique"
    manifest_path.write_text(text.replace(before, after, 1))
    git("add", "--", "members/IRRS", "family.yaml", cwd=holder)
    head = git("rev-parse", "HEAD", cwd=holder).stdout.strip()
    args = ["bump", "--family-root", str(holder), "--member", "IRRS", "--to",
            after]

    refused = run_script(FAMILY, *args)
    assert refused.returncode == 2, refused.stderr + refused.stdout
    assert refused.stderr.startswith("REFUSED family-manifest-uncommitted: ")
    assert ("Remediation: the index also stages a gitlink under members/ "
            in refused.stderr), refused.stderr
    git("checkout", "HEAD", "--", "family.yaml", cwd=holder)
    result = run_script(FAMILY, *args)

    assert result.returncode == 0, result.stderr + result.stdout
    assert "nothing to do" not in result.stdout
    assert git("rev-parse", "HEAD", cwd=holder).stdout.strip() != head
    assert git("rev-parse", "HEAD:members/IRRS",
               cwd=holder).stdout.strip() == after
    assert set(git("show", "--name-only", "--format=", "HEAD",
                   cwd=holder).stdout.split()) == {"members/IRRS",
                                                  "family.yaml"}
    assert validate(holder).returncode == 0


def test_bump_to_the_pinned_commit_repairs_a_gitlink_that_moved_alone(holder):
    """`validate-family.py`'s own remedy for `member-gitlink-mismatch` is
    `family.py bump --member <Project> --to <commit>`, and when the commit it
    is pointed at is the one the row already names the manifest agrees with
    `--to` and the gitlink does not. That is a bump with something to commit
    (#210)."""
    member = holder / "members" / "IRRS"
    pinned = git("rev-parse", "HEAD:members/IRRS", cwd=holder).stdout.strip()
    commit_in_member(member)
    git("add", "--", "members/IRRS", cwd=holder)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        "Move the gitlink and not the pin", cwd=holder)
    broken = validate(holder)
    assert broken.returncode == 1
    assert "member-gitlink-mismatch" in broken.stderr

    result = run_script(FAMILY, "bump", "--family-root", str(holder),
                        "--member", "IRRS", "--to", pinned)

    assert result.returncode == 0, result.stderr + result.stdout
    assert "nothing to do" not in result.stdout
    assert git("rev-parse", "HEAD:members/IRRS",
               cwd=holder).stdout.strip() == pinned
    assert validate(holder).returncode == 0, "and the lockstep rule holds"


def test_bump_to_the_pinned_commit_repairs_a_digest_that_does_not_recompute(
        holder):
    """The other half of the same remedy: a row whose `tree_sha256` is wrong
    names the commit `--to` names, and the bump rewrites the digest from the
    member's own objects. Comparing the commit and not the digest would have
    called it done."""
    member = holder / "members" / "IRRS"
    pinned = git("rev-parse", "HEAD:members/IRRS", cwd=holder).stdout.strip()
    row = {r["project"]: r for r in manifest(holder)["members"]}["IRRS"]
    manifest_path = holder / "family.yaml"
    manifest_path.write_text(manifest_path.read_text().replace(
        row["pin"]["tree_sha256"], "b" * 64))
    git("add", "--", "family.yaml", cwd=holder)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        "Hand-edit a digest", cwd=holder)
    broken = validate(holder)
    assert broken.returncode == 1
    assert "member-digest-mismatch" in broken.stderr

    result = run_script(FAMILY, "bump", "--family-root", str(holder),
                        "--member", "IRRS", "--to", pinned)

    assert result.returncode == 0, result.stderr + result.stdout
    assert "nothing to do" not in result.stdout
    repaired = {r["project"]: r for r in manifest(holder)["members"]}["IRRS"]
    assert repaired["pin"]["tree_sha256"] == tree_digest(member, pinned)
    assert validate(holder).returncode == 0


# --- --trailer: the lines a bump's commit ends with (#111) ------------------

def test_bump_with_two_trailers_ends_the_commit_message_in_the_order_given(
        family, tmp_path):
    """`bump` composes its own message, so a `Lane:` line — which the
    lane-collision protocol wants on every artifact a lane produces, the
    COMMIT included — reaches it no other way, and this estate's convention
    adds `Co-Authored-By:` beside it (#111).

    TWO BUMPS OF THE SAME MEMBER TO THE SAME COMMIT, one with the flag and
    one without, so the trailer block is the ONLY difference between the two
    messages: the ordering claim and the "a run passing none writes what it
    always wrote" claim, in one assertion, with no pasted copy of today's
    wording to go stale.
    """
    plain = tmp_path / (NAME + "-plain")
    trailed = tmp_path / (NAME + "-trailed")
    shutil.copytree(family["root"], plain, symlinks=True)
    shutil.copytree(family["root"], trailed, symlinks=True)

    member = family["work"] / "IRRS"
    (member / "TRAILED.md").write_text("the member advanced\n")
    git("add", "--", "TRAILED.md", cwd=member)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "Advance the member again", cwd=member)
    git("push", "-q", "origin", "main", cwd=member)
    moved = git("rev-parse", "HEAD", cwd=member).stdout.strip()

    for holder_root, extra in ((plain, ()),
                               (trailed, ("--trailer", TRAILERS[0],
                                          "--trailer", TRAILERS[1]))):
        result = run_script(FAMILY, "bump", "--family-root", str(holder_root),
                            "--member", "IRRS", "--to", moved, *extra)
        assert result.returncode == 0, result.stderr + result.stdout

    assert message_of(trailed) == \
        message_of(plain) + "\n" + "\n".join(TRAILERS) + "\n"
    assert trailers_of(trailed) == list(TRAILERS), (
        "and git reads them back as the trailer block, in order")
    assert trailers_of(plain) == [], "the run without the flag carries none"
    # Still ONE commit, still explicit pathspecs: a trailer changes the
    # message and nothing else.
    assert set(git("show", "--name-only", "--format=", "HEAD",
                   cwd=trailed).stdout.split()) == {"members/IRRS",
                                                    "family.yaml"}
    assert validate(trailed).returncode == 0
    # Undo it in the shared bare repository, so the module fixture's own
    # members stay where the other tests found them.
    git("reset", "-q", "--hard", "HEAD~1", cwd=member)
    git("push", "-q", "--force", "origin", "main", cwd=member)


@pytest.mark.parametrize("value", ["Lane xfactory-1", "Lane:xfactory-1",
                                   "Lane: "])
def test_bump_refuses_a_malformed_trailer(holder, value):
    """ARGPARSE'S OWN ERROR PATH: a malformed trailer is a malformed command
    line, refused with the usage line beside it and before the holder is
    read — so the manifest is untouched and no member was fetched."""
    result = run_script(FAMILY, "bump", "--family-root", str(holder),
                        "--member", "IRRS", "--to", "0" * 40,
                        "--trailer", value)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "--trailer" in result.stderr
    assert "usage:" in result.stderr
    assert "member-to-not-a-commit" not in result.stderr, (
        "argparse refuses before the tool reads anything at all")


@ENVIRONMENTS
def test_bump_with_a_non_ascii_trailer_lands_it_as_typed(
        holder, tmp_path, git_kind, locale):
    """#322: `--trailer "Co-Authored-By: José ..."` lands as the bytes typed.

    The cell that was broken is `old-git-c-locale`: a git without `commit
    --trailer` takes the trailer in the stdin message, a `C` locale reads the
    argument as lone surrogates, and `_commit_one`'s `errors="replace"` wrote
    each as `?`. The stand-in git refuses the option outright, so a run that
    passed it would fail here rather than pass. The member moves by an empty
    commit in the holder's own mount, so nothing in the shared remotes does."""
    after = commit_in_member(holder / "members" / "IRRS")
    result = run_script(FAMILY, "bump", "--family-root", str(holder),
                        "--member", "IRRS", "--to", after,
                        "--trailer", argv_of(NON_ASCII_BYTES),
                        "--trailer", TRAILERS[0],
                        env=environment(tmp_path, git_kind, locale))
    assert result.returncode == 0, result.stderr + result.stdout
    assert message_bytes_of(holder).endswith(
        b"\n\n" + NON_ASCII_BYTES + b"\n" + TRAILERS[0].encode() + b"\n")
    assert trailer_bytes_of(holder) == [NON_ASCII_BYTES,
                                        TRAILERS[0].encode()], (
        "and git reads them back as the trailer block, byte for byte")


@POSIX_ONLY
@pytest.mark.parametrize("locale", ["c", "utf8"])
def test_bump_refuses_a_trailer_that_is_not_utf8_by_name(
        holder, tmp_path, locale):
    typed = b"Co-Authored-By: Jos\xe9 <jose@example.invalid>"
    head = git("rev-parse", "HEAD", cwd=holder).stdout.strip()
    result = run_script(FAMILY, "bump", "--family-root", str(holder),
                        "--member", "IRRS", "--to", "0" * 40,
                        "--trailer", argv_of(typed),
                        env=environment(tmp_path, "old", locale))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "usage:" in result.stderr
    assert "not UTF-8 text" in result.stderr
    assert repr(typed) in result.stderr
    assert "member-to-not-a-commit" not in result.stderr, (
        "argparse refuses before the tool reads anything at all")
    assert git("rev-parse", "HEAD", cwd=holder).stdout.strip() == head


@POSIX_ONLY
def test_commit_one_refuses_a_trailer_that_is_no_text_before_it_stages(
        tmp_path):
    """A caller that reaches the helper without the command line's own check
    gets the same refusal, raised before the stage: the file is still
    untracked and there is no commit."""
    root = tmp_path / "repo"
    root.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=root)
    (root / "a.txt").write_text("x\n", encoding="utf-8")

    with pytest.raises(Refusal) as caught:
        family_module()._commit_one(
            root, "A commit\n", ["a.txt"],
            trailers=[argv_of(b"Co-Authored-By: Jos\xe9")])

    assert caught.value.code == "trailer-not-utf8"
    assert git("status", "--porcelain", cwd=root).stdout == "?? a.txt\n"
    assert git("rev-parse", "--verify", "-q", "HEAD", cwd=root,
               check=False).returncode != 0, "nothing was committed"


# --- remove -----------------------------------------------------------------

def test_remove_unmounts_the_member_and_touches_nothing_else(family, tmp_path):
    holder = tmp_path / NAME
    shutil.copytree(family["root"], holder, symlinks=True)
    result = run_script(FAMILY, "remove", "--family-root", str(holder),
                        "--member", "IRSS")
    assert result.returncode == 0, result.stderr + result.stdout
    assert [r["project"] for r in manifest(holder)["members"]] == ["IRRS"]
    assert not (holder / "members" / "IRSS").exists()
    assert "IRSS" not in (holder / ".gitmodules").read_text()
    assert validate(holder).returncode == 0
    # The member repository itself is untouched: membership conferred nothing,
    # so losing it takes nothing away.
    bare = family["remotes"] / "IRSS.git"
    assert bare.is_dir()
    assert git("rev-parse", "main", cwd=bare).stdout.strip()


def test_remove_finds_a_member_in_any_case(family, holder):
    result = run_script(FAMILY, "remove", "--family-root", str(holder),
                        "--member", "irss")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "removed IRSS (InkRouter/IRSS) from members/IRSS" in result.stdout
    assert [r["project"] for r in manifest(holder)["members"]] == ["IRRS"]
    assert sorted(os.listdir(holder / "members")) == ["IRRS"]
    assert message_of(holder).startswith("Remove IRSS from ")
    assert validate(holder).returncode == 0


def test_remove_takes_the_extra_row_out_of_a_family_pinned_twice(family,
                                                                 holder):
    """The way out for a holder that already pins one project twice: name the
    row to drop, and the gate goes green again."""
    mount_twice(holder, family["remotes"])
    assert validate(holder).returncode == 1
    result = run_script(FAMILY, "remove", "--family-root", str(holder),
                        "--member", "IRRS2")
    assert result.returncode == 0, result.stderr + result.stdout
    assert [r["project"] for r in manifest(holder)["members"]] == list(MEMBERS)
    assert validate(holder).returncode == 0


def test_remove_leaves_the_object_store_and_says_so(family, tmp_path):
    """`git rm` keeps a removed submodule's git directory on purpose, and
    `add` cannot write over it. Neither command deletes it — somebody may
    have committed inside the mount — so both name the exit."""
    holder = tmp_path / NAME
    shutil.copytree(family["root"], holder, symlinks=True)
    removed = run_script(FAMILY, "remove", "--family-root", str(holder),
                         "--member", "IRSS")
    assert removed.returncode == 0, removed.stderr + removed.stdout
    assert ".git/modules/members/IRSS" in removed.stdout

    again = run_script(FAMILY, "add", "--family-root", str(holder),
                       "--member", f"{ORG}/IRSS",
                       "--local-remote-dir", str(family["remotes"]))
    assert again.returncode == 2
    assert "member-git-dir-cached" in again.stderr
    assert "rm -rf" in again.stderr

    # `conftest.rmtree`, not `shutil`: this is a git object store, and
    # git writes its objects read-only — which Windows refuses to unlink.
    rmtree(holder / ".git" / "modules" / "members" / "IRSS")
    back = run_script(FAMILY, "add", "--family-root", str(holder),
                      "--member", f"{ORG}/IRSS",
                      "--local-remote-dir", str(family["remotes"]))
    assert back.returncode == 0, back.stderr + back.stdout
    assert validate(holder).returncode == 0


def test_remove_refuses_a_member_that_is_not_there(holder):
    result = run_script(FAMILY, "remove", "--family-root", str(holder),
                        "--member", "Nope")
    assert result.returncode == 2
    assert "member-unknown" in result.stderr


# --- bootstrap --------------------------------------------------------------

@pytest.fixture(scope="module")
def bootstrapped(family, tmp_path_factory):
    """A fresh recursive clone of the family, bootstrapped."""
    target = cloned_just_pushed(family["remotes"] / f"{NAME}.git",
                                tmp_path_factory.mktemp("family-clone") / NAME)
    result = run_script(target / "scripts" / "bootstrap.py", cwd=target,
                        env=ALLOW_FILE_PROTOCOL)
    return {"root": target, "result": result}


def test_bootstrap_fetches_every_member_and_runs_each_ones_own(bootstrapped):
    result = bootstrapped["result"]
    assert result.returncode == 0, result.stderr + result.stdout
    assert "every member and leg fetched" in result.stdout
    for project in MEMBERS:
        assert f"--- {project}: make bootstrap ---" in result.stdout
        # each member's own bootstrap put ITS legs on their tracking branches
        assert (bootstrapped["root"] / "members" / project / "spec").is_dir()
    assert "family bootstrap ok" in result.stdout


def test_bootstrap_reports_the_credential_source_it_used(bootstrapped):
    """`none` is a legitimate answer and is said out loud: a family whose
    members are public needs no credential at all."""
    assert "credential source: none" in bootstrapped["result"].stdout


def test_bootstrap_degrades_when_a_member_cannot_be_fetched(family, tmp_path):
    """A missing credential is a DEGRADE, not a failure: without
    `protocol.file.allow` git refuses these local submodules exactly as it
    would refuse a private one with no token."""
    target = cloned_just_pushed(family["remotes"] / f"{NAME}.git",
                                tmp_path / NAME, recurse=False)
    result = run_script(target / "scripts" / "bootstrap.py", cwd=target)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "FETCH INCOMPLETE" in result.stderr
    assert "SHAPE_LEGS_TOKEN" in result.stderr
    assert "NOT CHECKED OUT; skipped" in result.stdout
    assert "family bootstrap ok" in result.stdout


def test_make_validate_runs_the_family_then_every_member(bootstrapped):
    proc = subprocess.run(["make", "validate"], cwd=str(bootstrapped["root"]),
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "family ok: InkRouter" in proc.stdout
    for project in MEMBERS:
        assert f"--- {project}: make validate ---" in proc.stdout
        assert f"manifest ok: {project}" in proc.stdout


# --- update-shape knows a family root when it sees one ----------------------


def upstream_clone(path):
    """A clone of openRepoShape at the revision THIS HOLDER WAS CUT FROM.

    That revision is the WORKING TREE, not `HEAD`. `family.py init`
    materialized the holder from the templates on disk and recorded `HEAD` as
    the pin — printing its own DIRTY warning as it did — so a clone at `HEAD`
    is a different tree from the one the copies came from whenever anything is
    uncommitted. It is uncommitted precisely in the pull request that ADDS a
    file to `templates/family-root/`, and `update-shape.py` then correctly
    reports the new copy as `upstream-removed`: absent from a tree it was
    never in. Committing the working tree into the clone keeps this fixture's
    premise — "the upstream this holder came from" — true either way, and
    changes nothing when the checkout is clean.
    """
    subprocess.run(["git", "clone", "-q", str(REPO), str(path)], check=True)
    shutil.copytree(REPO, path, dirs_exist_ok=True, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", "__pycache__",
                                                  ".pytest_cache"))
    if git("status", "--porcelain", cwd=path).stdout.strip():
        git("add", "-A", cwd=path)
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
            "The working tree this holder was materialized from", cwd=path)
    return path

def test_update_shape_reads_a_family_root_and_mirrors_into_family_yaml(
        family, tmp_path):
    """The holder carries the same COPY pin an assembly root does, so the same
    command re-syncs it — into `family.yaml`, and green against
    `validate-family.py` rather than the leg validators."""
    upstream = upstream_clone(tmp_path / "openRepoShape")

    holder = tmp_path / NAME
    shutil.copytree(family["root"], holder, symlinks=True)
    before = load_yaml(holder / "family.yaml")["shape"]["commit"]

    changed = "templates/family-root/scripts/validate-family.py"
    source = upstream / changed
    source.write_text(source.read_text()
                      + "\n# An upstream fix that must reach every family.\n")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        "Fix the family validator", "--", changed, cwd=upstream)
    target_commit = git("rev-parse", "HEAD", cwd=upstream).stdout.strip()

    checked = run_script(UPDATE, "check", "--root", str(holder),
                         "--upstream", str(upstream))
    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert "upstream-changed" in checked.stdout
    assert "scripts/validate-family.py" in checked.stdout

    applied = run_script(UPDATE, "apply", "--root", str(holder), "--yes",
                         "--upstream", str(upstream), "--at", target_commit)
    assert applied.returncode == 0, applied.stdout + applied.stderr
    assert "the family's own validators" in applied.stdout
    assert "family.yaml" in applied.stdout

    data = load_yaml(holder / "family.yaml")
    assert data["shape"]["commit"] == target_commit != before
    assert load_yaml(holder / "contracts" / "shape-pin.yaml")["commit"] \
        == target_commit
    assert "must reach every family" in \
        (holder / "scripts" / "validate-family.py").read_text()
    assert validate(holder).returncode == 0


def test_update_shape_moves_the_holder_readmes_shape_line_with_the_pin(
        family, tmp_path):
    """#148 END TO END, ON A REAL HOLDER RATHER THAN A SYNTHESISED README.

    This is the drift the issue was filed over: InkRouter's holder still read
    `6fe09a41535a` four re-pins after `contracts/shape-pin.yaml` had moved on,
    because nothing rewrote the sentence the scaffold rendered. Here the same
    re-pin carries it, in the same commit, and the rest of the file is byte
    for byte what it was — a holder's README is its own document.
    """
    upstream = upstream_clone(tmp_path / "openRepoShape")
    changed = "templates/family-root/scripts/validate-family.py"
    source = upstream / changed
    source.write_text(source.read_text()
                      + "\n# An upstream fix that must reach every family.\n")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        "Fix the family validator", "--", changed, cwd=upstream)
    target_commit = git("rev-parse", "HEAD", cwd=upstream).stdout.strip()

    holder = tmp_path / NAME
    shutil.copytree(family["root"], holder, symlinks=True)
    readme = holder / "README.md"
    before = readme.read_bytes()
    named = readme_shape_lines(before.decode("utf-8"))[0]["commit"]
    assert named != target_commit, "fixture: the line starts out behind"

    applied = run_script(UPDATE, "apply", "--root", str(holder), "--yes",
                         "--upstream", str(upstream), "--at", target_commit)
    assert applied.returncode == 0, applied.stdout + applied.stderr
    after = readme.read_bytes()
    assert len(after) == len(before), "one sha for another, nothing else"
    assert readme_shape_lines(after.decode("utf-8"))[0]["commit"] == \
        target_commit
    assert (f"README.md: Shape: line {named[:12]} -> {target_commit[:12]}"
            in applied.stdout)
    assert validate(holder).returncode == 0


def test_update_shape_with_no_shape_block_names_the_family_validator(
        family, tmp_path):
    """A FAMILY root's remediation must send the operator to
    `validate-family.py` — the validator this root actually carries, not
    `validate-manifest.py`, which a family root does not have. See the twin
    of this test on a project root in `test_update_shape.py`."""
    upstream = upstream_clone(tmp_path / "openRepoShape")
    changed = "templates/family-root/scripts/validate-family.py"
    source = upstream / changed
    source.write_text(source.read_text()
                      + "\n# forces a target commit past the family's pin.\n")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        "Force a target commit past the family's pin", "--", changed,
        cwd=upstream)
    target_commit = git("rev-parse", "HEAD", cwd=upstream).stdout.strip()

    holder = tmp_path / NAME
    shutil.copytree(family["root"], holder, symlinks=True)
    before = load_yaml(holder / "contracts" / "shape-pin.yaml")["commit"]
    strip_shape_block(holder / "family.yaml")

    applied = run_script(UPDATE, "apply", "--root", str(holder), "--yes",
                         "--upstream", str(upstream), "--at", target_commit)
    assert applied.returncode == 2
    assert "update-manifest-no-shape" in applied.stderr
    assert "validate-family.py" in applied.stderr
    assert "validate-manifest.py" not in applied.stderr
    assert load_yaml(holder / "contracts" / "shape-pin.yaml")["commit"] \
        == before, "a refused apply writes nothing at all"


def test_update_shape_does_not_resync_a_family_bootstrap_from_the_project_one(
        family, tmp_path):
    """BOTH ROOTS HOLD A `scripts/bootstrap.py` AND THEY ARE DIFFERENT FILES.
    One copy-source table keyed by the path in the root would have re-synced
    the family's from `templates/assembly-root/`, silently."""
    upstream = upstream_clone(tmp_path / "openRepoShape")
    holder = tmp_path / NAME
    shutil.copytree(family["root"], holder, symlinks=True)

    checked = run_script(UPDATE, "check", "--root", str(holder),
                         "--upstream", str(upstream))
    verdicts = {}
    for line in checked.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and line.startswith("  "):
            verdicts[parts[1]] = parts[0]
    assert verdicts.get("scripts/bootstrap.py") == "unchanged", (
        "the family's bootstrap must be compared against "
        "templates/family-root/scripts/bootstrap.py, not the assembly root's")


def test_no_members_checks_the_envelope_and_the_copies_alone(holder):
    """What CI runs when the members could not be checked out: the checks
    that do not need them still run, and the ones that do are skipped OUT
    LOUD rather than passing on an unreadable surface."""
    shutil.rmtree(holder / "members" / "IRRS")
    (holder / "members" / "IRRS").mkdir()
    refused = validate(holder)
    assert refused.returncode == 2
    assert "member-uninitialized" in refused.stderr

    result = validate(holder, "--no-members")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "2 member(s) SKIPPED (--no-members)" in result.stdout
    assert "copied shape file(s) match their digests" in result.stdout
    assert "InkRouter: family" in result.stdout


def test_no_members_still_finds_an_edited_copy(holder):
    copy = holder / "Makefile"
    copy.write_text(copy.read_text() + "\n# edited in place\n")
    result = validate(holder, "--no-members")
    assert result.returncode == 1
    assert "shape-copy-drift" in result.stderr


def test_pins_and_no_members_together_ask_for_nothing(holder):
    result = validate(holder, "--pins", "--no-members")
    assert result.returncode == 2
    assert "family-nothing-to-check" in result.stderr


# --- init lands in a family FOLDER (#76, 2026-09-09) ------------------------
#
# THE LAYOUT IS PLACED, NEVER MOVED. `init` used to materialize the holder in
# a TEMP directory unless `--work-dir` said otherwise, so every family folder
# on every workstation was arranged by hand afterwards — which is why the
# doubled `<Family>/<Family>` had to be explained to each person who met it.
# The default now lands where the person is standing, in a plain folder named
# after the family, and `--work-dir` keeps exactly its old meaning.


def init_local(tmp_path, *extra, family: str = "Contoso", cwd=None):
    return run_script(FAMILY, "init", "--org", ORG, "--family", family,
                      "--created-by", "Test Human", "--created-on",
                      "2026-09-09", "--local-remote-dir",
                      str(tmp_path / "remotes"), *extra, cwd=cwd)


def test_init_lands_the_holder_in_a_family_folder_where_you_are_standing(
        tmp_path):
    """`<into>/<Family>/<Family>`, with `<into>` the invocation directory.

    The same "lands where you were standing" rule #39 gave projects. The
    folder is a PLAIN DIRECTORY — not a repository, not a submodule — and the
    holder keeps its own repository name inside it.
    """
    stand = tmp_path / "projects"
    stand.mkdir()
    result = init_local(tmp_path, cwd=stand)
    assert result.returncode == 0, result.stderr + result.stdout
    folder, holder = stand / "Contoso", stand / "Contoso" / "Contoso"
    assert folder.is_dir(), (
        "the family folder is a plain directory and never a repository")
    assert not (folder / ".git").exists(), (
        "the family folder is a plain directory and never a repository")
    assert (holder / "family.yaml").is_file()
    assert (holder / ".git").is_dir()
    assert f"folder       {folder}" in result.stdout
    assert f"landing      {holder}" in result.stdout
    # The next block names the folder, the holder and BOTH next commands, and
    # says which of the two copies of a member you work in.
    assert f"family folder  {folder}" in result.stdout
    assert f"holder         {holder}" in result.stdout
    assert "add --family-root" in result.stdout
    assert "make siblings" in result.stdout
    assert "TWO COPIES OF EVERY MEMBER" in result.stdout
    assert "BESIDE the holder" in result.stdout


def test_init_into_names_the_parent_directory(tmp_path):
    """`--into` is the PARENT, not the landing spot: the folder goes in it."""
    into = tmp_path / "elsewhere"
    result = init_local(tmp_path, "--into", str(into))
    assert result.returncode == 0, result.stderr + result.stdout
    assert (into / "Contoso" / "Contoso" / "family.yaml").is_file()


def test_init_standing_in_the_family_folder_does_not_nest_another(tmp_path):
    """A person standing in `Contoso/` means THAT folder, not one inside it.

    Otherwise the first thing anybody does — `mkdir Contoso && cd Contoso` —
    produces `Contoso/Contoso/Contoso`, and the layout that has to be
    explained once has to be explained twice.
    """
    stand = tmp_path / "Contoso"
    stand.mkdir()
    result = init_local(tmp_path, cwd=stand)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (stand / "Contoso" / "family.yaml").is_file()
    assert not (stand / "Contoso" / "Contoso").exists()


def test_init_refuses_when_that_folder_already_holds_its_holder(tmp_path):
    """The second run in the same place is not an init of anything."""
    stand = tmp_path / "Contoso"
    stand.mkdir()
    assert init_local(tmp_path, cwd=stand).returncode == 0
    again = init_local(tmp_path, "--reuse-empty-repo", cwd=stand)
    assert again.returncode == 2
    assert "family-holder-already-here" in again.stderr
    assert "family.py add" in again.stderr
    assert "make siblings" in again.stderr
    assert "There is no --force" in again.stderr


def test_init_work_dir_keeps_its_old_meaning_and_makes_no_folder(tmp_path):
    """`<work-dir>/<Family>`, exactly as before — every rehearsal in this
    suite passes it, and a flag that quietly changed meaning is worse than a
    second flag."""
    work = tmp_path / "work"
    result = init_local(tmp_path, "--work-dir", str(work))
    assert result.returncode == 0, result.stderr + result.stdout
    assert (work / "Contoso" / "family.yaml").is_file()
    assert not (work / "Contoso" / "Contoso").exists()
    assert "--work-dir: no family folder" in result.stdout


def test_init_refuses_into_and_work_dir_together(tmp_path):
    result = init_local(tmp_path, "--into", str(tmp_path / "a"),
                        "--work-dir", str(tmp_path / "b"))
    assert result.returncode == 2
    assert "family-two-landings" in result.stderr
    assert not (tmp_path / "a").exists()
    assert not (tmp_path / "b").exists()


def test_init_refuses_a_landing_that_exists_and_is_not_empty(tmp_path):
    """As before, and with no --force: the holder target is somebody's
    directory and nothing here writes into one."""
    stand = tmp_path / "projects"
    (stand / "Contoso" / "Contoso").mkdir(parents=True)
    (stand / "Contoso" / "Contoso" / "MINE.md").write_text("not yours\n")
    result = init_local(tmp_path, cwd=stand)
    assert result.returncode == 2
    assert "family-target-exists" in result.stderr
    assert "There is no --force" in result.stderr
    assert (stand / "Contoso" / "Contoso" / "MINE.md").is_file()


def test_init_dry_run_prints_the_landing_and_creates_nothing(tmp_path):
    stand = tmp_path / "projects"
    stand.mkdir()
    result = init_local(tmp_path, "--dry-run", cwd=stand)
    assert result.returncode == 0, result.stderr
    assert f"landing      {stand / 'Contoso' / 'Contoso'}" in result.stdout
    assert "--dry-run: nothing was created." in result.stdout
    assert not (stand / "Contoso").exists()
    assert not (tmp_path / "remotes").exists()


# --- make siblings: the members, beside the holder ---------------------------


SIBLINGS = REPO / "templates" / "family-root" / "scripts" / "siblings.py"


@pytest.fixture
def estate(family, tmp_path):
    """A CORRECT workstation layout: `<tmp>/InkRouter/InkRouter` and nothing
    beside it yet. Function-scoped, because these tests write clones."""
    folder = tmp_path / NAME
    folder.mkdir()
    holder = folder / NAME
    shutil.copytree(family["root"], holder, symlinks=True)
    return {"folder": folder, "holder": holder, "remotes": family["remotes"]}


def siblings(holder, *extra, env=None):
    return run_script(holder / "scripts" / "siblings.py", *extra, cwd=holder,
                      env={**ALLOW_FILE_PROTOCOL, **(env or {})})


def layout(stdout: str) -> list[str]:
    """The layout table alone — the part with no absolute path in it, so two
    runs in two directories can be compared line for line."""
    lines = stdout.splitlines()
    start = lines.index("(b) the layout")
    rows = []
    for line in lines[start + 1:]:
        if not line.startswith("  "):
            break
        rows.append(" ".join(line.split()))
    return rows


def test_siblings_clones_each_member_beside_the_holder_on_its_branch(estate):
    """Through `make siblings`, which is the entry point a holder ships.

    The sibling is a WORKING clone: on its tracking branch, with its own
    bootstrap already run, so its legs are on their branches at their pins.
    """
    proc = subprocess.run(["make", "siblings"], cwd=str(estate["holder"]),
                           capture_output=True, text=True, check=False,
                           env={**os.environ, **ALLOW_FILE_PROTOCOL})
    assert proc.returncode == 0, proc.stderr + proc.stdout
    for project in MEMBERS:
        sibling = estate["folder"] / project
        assert (sibling / ".git").is_dir(), f"{project} was not cloned"
        assert git("rev-parse", "--abbrev-ref", "HEAD",
                   cwd=sibling).stdout.strip() == "main", (
            "a sibling is a working clone on its tracking branch, not a "
            "detached checkout like the pinned copy")
        assert (sibling / "spec" / ".git").exists(), (
            "the member's own bootstrap placed its legs")
        assert git("rev-parse", "--abbrev-ref", "HEAD",
                   cwd=sibling / "spec").stdout.strip() == "main"
    assert "siblings ok: 2 member(s)" in proc.stdout
    assert layout(proc.stdout) == [
        "what name state branch",
        f"holder {NAME} the holder {WORK_BRANCH}",
        "sibling IRRS cloned main",
        "sibling IRSS cloned main",
        "pinned members/IRRS pinned in the holder main",
        "pinned members/IRSS pinned in the holder main",
    ]


def test_a_second_run_is_all_present_and_exits_zero(estate):
    """IDEMPOTENT, which is what makes it safe to put in a handoff."""
    first = siblings(estate["holder"])
    assert first.returncode == 0, first.stderr + first.stdout
    second = siblings(estate["holder"])
    assert second.returncode == 0, second.stderr + second.stdout
    assert "cloned" not in " ".join(layout(second.stdout))
    assert second.stdout.count("present, fetched") == len(MEMBERS)
    assert "fetching only" in second.stdout


def test_siblings_touches_nothing_in_a_clone_somebody_is_working_in(estate):
    """FETCH ONLY: no checkout, no reset, no pull, no branch switch.

    A utility that "helpfully" moved somebody's HEAD would be the most
    destructive thing in this standard, so the branch a person is on and the
    file they have not committed are both still there afterwards.
    """
    assert siblings(estate["holder"]).returncode == 0
    sibling = estate["folder"] / "IRRS"
    git("checkout", "-q", "-b", "wip", cwd=sibling)
    (sibling / "SCRATCH.md").write_text("uncommitted work\n")
    was = git("rev-parse", "HEAD", cwd=sibling).stdout.strip()

    result = siblings(estate["holder"])
    assert result.returncode == 0, result.stderr + result.stdout
    assert git("rev-parse", "--abbrev-ref", "HEAD",
               cwd=sibling).stdout.strip() == "wip"
    assert git("rev-parse", "HEAD", cwd=sibling).stdout.strip() == was
    assert (sibling / "SCRATCH.md").read_text() == "uncommitted work\n"
    assert "sibling IRRS present, fetched wip" in layout(result.stdout)


def test_siblings_reports_a_clone_of_another_repository_and_skips_it(estate):
    """A directory at the right NAME is not by itself the member.

    Reported, skipped, left exactly as it is, and the run exits non-zero — the
    exit is the human's hand, never an overwrite.
    """
    wrong = estate["folder"] / "IRSS"
    wrong.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=wrong)
    git("remote", "add", "origin", "https://github.com/Somebody/Else.git",
        cwd=wrong)
    (wrong / "MINE.md").write_text("somebody else's work\n")

    result = siblings(estate["holder"])
    assert result.returncode == 1, result.stdout + result.stderr
    assert "WRONG ORIGIN" in result.stdout
    assert "FINDING IRSS:" in result.stderr
    assert "Somebody/Else" in result.stderr
    assert "no existing clone was touched" in result.stderr
    assert (wrong / "MINE.md").read_text() == "somebody else's work\n"
    assert not (wrong / "project.yaml").exists(), "nothing was written into it"
    # The other member is still placed: one bad directory is not a reason to
    # do nothing for the rest of the family.
    assert (estate["folder"] / "IRRS" / ".git").is_dir()


def test_siblings_reports_a_directory_that_is_not_a_clone_at_all(estate):
    result = siblings(estate["holder"])
    assert result.returncode == 0
    rmtree(estate["folder"] / "IRRS")
    (estate["folder"] / "IRRS").mkdir()
    (estate["folder"] / "IRRS" / "notes.md").write_text("mine\n")
    again = siblings(estate["holder"])
    assert again.returncode == 1
    assert "NOT A CLONE" in again.stdout
    assert (estate["folder"] / "IRRS" / "notes.md").read_text() == "mine\n"


def test_siblings_warns_about_the_parent_folder_and_moves_nothing(family,
                                                                  tmp_path):
    """THE DOCTOR PATTERN, NOT A MOVER (#76). The holder here sits under a
    folder that is not named after the family, which is what a hand-arranged
    workstation looks like — and the answer is a warning, the exact `mv`, and
    nothing moved. Asked before anything is cloned, so it stops there, exit 1
    (#543; `test_family_siblings_placement.py`)."""
    wrong = tmp_path / "somewhere-else"
    wrong.mkdir()
    holder = wrong / NAME
    shutil.copytree(family["root"], holder, symlinks=True)

    result = siblings(holder, "--dry-run")
    assert result.returncode == 1, result.stderr + result.stdout
    assert "WARNING the holder's parent folder is 'somewhere-else', not " \
        "'InkRouter'." in result.stderr
    assert "NOTHING WAS MOVED" in result.stderr
    assert "LINKED WORKTREE" in result.stderr
    # The exact commands, and the staging name the one-step `mv A A/A` cannot
    # be spelled without. Each is a POSIX shell's and quoted for one (#486):
    # `shlex.join` is the standard library's spelling of that, which leaves
    # these paths bare everywhere but in Windows' backslashes.
    staged, wanted = tmp_path / "InkRouter.holder", tmp_path / "InkRouter"
    assert shlex.join(["mv", str(holder), str(staged)]) in result.stderr
    assert shlex.join(["mkdir", "-p", str(wanted)]) in result.stderr
    assert shlex.join(["mv", str(staged), str(wanted / "InkRouter")]) \
        in result.stderr
    assert holder.is_dir(), "it moves nothing, and that is the whole point"
    assert (holder / "family.yaml").is_file(), (
        "it moves nothing, and that is the whole point")
    assert not (tmp_path / "InkRouter").exists()


def test_siblings_dry_run_clones_nothing(estate):
    result = siblings(estate["holder"], "--dry-run")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "would clone" in result.stdout
    assert "--dry-run: nothing was cloned, fetched or moved." in result.stdout
    for project in MEMBERS:
        assert not (estate["folder"] / project).exists()


def test_family_py_siblings_runs_the_holders_own_file(family, tmp_path):
    """ONE IMPLEMENTATION, TWO ENTRY POINTS (ruling 1b, 2026-09-09).

    `family.py siblings` runs the holder's own `scripts/siblings.py` (#543),
    the way the root `bootstrap` shim runs the assembly
    root's bootstrap — so a person with a checkout of the standard and a
    holder on disk gets the same run, and its exit code, without a second
    code path to keep in step. The proof is the layout table: byte for byte
    the same as `make siblings`, which is the part of the output that carries
    no absolute path.
    """
    def one(name: str, runner) -> dict:
        folder = tmp_path / name / NAME
        folder.mkdir(parents=True)
        holder = folder / NAME
        shutil.copytree(family["root"], holder, symlinks=True)
        result = runner(holder)
        assert result.returncode == 0, result.stderr + result.stdout
        return {"folder": folder, "result": result}

    theirs = one("target", lambda holder: siblings(holder))
    ours = one("shim", lambda holder: run_script(
        FAMILY, "siblings", "--family-root", str(holder),
        env={**ALLOW_FILE_PROTOCOL, **NO_BYTECODE}))

    assert layout(ours["result"].stdout) == layout(theirs["result"].stdout)
    for project in MEMBERS:
        assert (ours["folder"] / project / ".git").is_dir()
        assert git("rev-parse", "--abbrev-ref", "HEAD",
                   cwd=ours["folder"] / project).stdout.strip() == "main"


def test_family_py_siblings_refuses_a_path_that_is_not_a_holder(project):
    result = run_script(FAMILY, "siblings", "--family-root", str(project))
    assert result.returncode == 2
    assert "family-root-missing" in result.stderr
    assert "family.py init" in result.stderr


#: SPELLINGS OF ONE REPOSITORY. `{remotes}` is this family's own mounted url,
#: which is a bare repository on disk here and a GitHub url in the world;
#: `{org}` reaches the same member through `family.yaml`'s `repository:`, the
#: way a person's own clone of a PRIVATE member is usually spelled. Every
#: scheme is dropped by pattern rather than by a list, which is why
#: `file://<path>` and `<path>` are one answer as well (#79's S5332: a list of
#: schemes is also a list of literals, and one of them read as a transport
#: choice).
SPELLINGS = (
    "git@github.com:{org}/IRRS.git",
    "https://github.com/{org}/IRRS.git",
    "ssh://git@github.com/{org}/IRRS.git",
    "git+ssh://git@github.com/{org}/IRRS.git",
    "file://{remotes}/IRRS.git",
    "{remotes}/IRRS.git/",
)


@pytest.mark.parametrize("spelling", SPELLINGS)
def test_siblings_accepts_a_clone_whose_remote_is_spelled_differently(
        estate, spelling):
    """One repository, six spellings, and a utility that refused to fetch
    somebody's clone over a punctuation difference would send them to delete
    it.

    `--dry-run` for the second run, so the IDENTITY is what is under test and
    nothing reaches for a network: `place` verifies the origin and the
    `project.yaml` id BEFORE the dry run decides not to fetch, and this suite
    creates nothing and contacts nothing.
    """
    assert siblings(estate["holder"]).returncode == 0
    sibling = estate["folder"] / "IRRS"
    git("remote", "set-url", "origin",
        spelling.format(org=ORG, remotes=estate["remotes"]), cwd=sibling)

    result = siblings(estate["holder"], "--dry-run")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "WRONG ORIGIN" not in result.stdout
    assert "sibling IRRS present, would fetch main" in layout(result.stdout)


def test_siblings_skips_a_clone_whose_project_id_is_not_the_rows(estate):
    """A repository at the right url is not by itself the project the row
    claims: `project.yaml` inside the clone is the source."""
    assert siblings(estate["holder"]).returncode == 0
    sibling = estate["folder"] / "IRSS"
    manifest_path = sibling / "project.yaml"
    manifest_path.write_text(
        manifest_path.read_text().replace('id: "irss"', 'id: "something-else"',
                                          1))
    result = siblings(estate["holder"])
    assert result.returncode == 1, result.stdout + result.stderr
    assert "WRONG PROJECT" in result.stdout
    assert "something-else" in result.stderr


def test_siblings_resolves_a_relative_submodule_url(estate):
    """A `../<Repo>.git` in `.gitmodules` is relative to THIS repository's
    REMOTE, which is git's own rule — a clone that took the string literally
    would fetch from wherever the process happened to be standing."""
    modules = estate["holder"] / ".gitmodules"
    modules.write_text(
        "\n".join(f'[submodule "members/{p}"]\n\tpath = members/{p}\n'
                  f"\turl = ../{p}.git" for p in MEMBERS) + "\n")
    result = siblings(estate["holder"])
    assert result.returncode == 0, result.stderr + result.stdout
    for project in MEMBERS:
        sibling = estate["folder"] / project
        assert (sibling / ".git").is_dir()
        assert git("remote", "get-url", "origin", cwd=sibling).stdout.strip() \
            == str(estate["remotes"] / f"{project}.git")
