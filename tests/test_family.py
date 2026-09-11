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

import os
import shutil
import subprocess
import sys

import pytest

from conftest import FILE_PROTOCOL, REPO, git, rmtree, run_script
from test_update_shape import strip_shape_block

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml, tree_digest  # noqa: E402

FAMILY = REPO / "scripts" / "family.py"
SCAFFOLD = REPO / "scaffold-project.py"
UPDATE = REPO / "update-shape.py"
ORG = "InkRouter"
NAME = "InkRouter"
MEMBERS = ("IRRS", "IRSS")
#: A fourth InkRouter service, scaffolded and deliberately NOT added: the
#: tests that need to `add` something need one that is not a member yet, and
#: removing a member to make room would test `remove` by accident.
SPARE = "IRQS"

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
    for project in MEMBERS:
        added = run_script(FAMILY, "add", "--family-root", str(root),
                           "--member", f"{ORG}/{project}",
                           "--local-remote-dir", str(base / "remotes"))
        assert added.returncode == 0, added.stderr + added.stdout
    git("push", "-q", "origin", "main", cwd=root)
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
                 "--accept-local", "pull request"):
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


def test_init_dry_run_plans_the_gh_topic_command_for_a_real_org(tmp_path):
    """No `--local-remote-dir`, so the plan is the REAL one — and a dry run
    prints it before anything is created, so this needs no network either."""
    result = run_script(FAMILY, "init", "--org", ORG, "--family", "Contoso",
                        "--created-by", "Test Human",
                        "--work-dir", str(tmp_path / "work"), "--dry-run")
    assert result.returncode == 0, result.stderr
    assert "topics       gh repo edit --add-topic xf-project-contoso" \
        in result.stdout
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


def test_bump_refuses_a_tag(holder):
    result = run_script(FAMILY, "bump", "--family-root", str(holder),
                        "--member", "IRRS", "--to", "v1.0.0")
    assert result.returncode == 2
    assert "member-to-not-a-commit" in result.stderr


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
    target = tmp_path_factory.mktemp("family-clone") / NAME
    proc = subprocess.run(
        ["git", *FILE_PROTOCOL, "clone", "-q", "--recurse-submodules",
         str(family["remotes"] / f"{NAME}.git"), str(target)],
        capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
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
    target = tmp_path / NAME
    proc = subprocess.run(
        ["git", *FILE_PROTOCOL, "clone", "-q",
         str(family["remotes"] / f"{NAME}.git"), str(target)],
        capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
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
        f"holder {NAME} the holder main",
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
    nothing moved."""
    wrong = tmp_path / "somewhere-else"
    wrong.mkdir()
    holder = wrong / NAME
    shutil.copytree(family["root"], holder, symlinks=True)

    result = siblings(holder, "--dry-run")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "WARNING the holder's parent folder is 'somewhere-else', not " \
        "'InkRouter'." in result.stderr
    assert "NOTHING WAS MOVED" in result.stderr
    assert "LINKED WORKTREE" in result.stderr
    # The exact commands, and the staging name the one-step `mv A A/A` cannot
    # be spelled without.
    assert f"mv {holder} {tmp_path / 'InkRouter.holder'}" in result.stderr
    assert f"mkdir -p {tmp_path / 'InkRouter'}" in result.stderr
    assert f"mv {tmp_path / 'InkRouter.holder'} " \
           f"{tmp_path / 'InkRouter' / 'InkRouter'}" in result.stderr
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

    `family.py siblings` runs `templates/family-root/scripts/siblings.py`
    through `runpy`, the way the root `bootstrap` shim runs the assembly
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
        env=ALLOW_FILE_PROTOCOL))

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
        manifest_path.read_text().replace("id: irss", "id: something-else", 1))
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
