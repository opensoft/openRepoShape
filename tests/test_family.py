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

import shutil
import subprocess
import sys

import pytest

from conftest import FILE_PROTOCOL, REPO, git, run_script

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
    assert rows == {"scripts/validate-family.py", "scripts/bootstrap.py",
                    "Makefile", ".gitignore",
                    ".github/workflows/validate.yml", "scripts/repo_shape.py",
                    "contracts/repository-naming.yaml"}
    assert "scripts/validate-pins.py" not in rows, (
        "a family has no legs, so it does not carry the leg validator")


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

    shutil.rmtree(holder / ".git" / "modules" / "members" / "IRSS")
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

def test_update_shape_reads_a_family_root_and_mirrors_into_family_yaml(
        family, tmp_path):
    """The holder carries the same COPY pin an assembly root does, so the same
    command re-syncs it — into `family.yaml`, and green against
    `validate-family.py` rather than the leg validators."""
    upstream = tmp_path / "openRepoShape"
    proc = subprocess.run(["git", "clone", "-q", str(REPO), str(upstream)],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr

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


def test_update_shape_does_not_resync_a_family_bootstrap_from_the_project_one(
        family, tmp_path):
    """BOTH ROOTS HOLD A `scripts/bootstrap.py` AND THEY ARE DIFFERENT FILES.
    One copy-source table keyed by the path in the root would have re-synced
    the family's from `templates/assembly-root/`, silently."""
    upstream = tmp_path / "openRepoShape"
    proc = subprocess.run(["git", "clone", "-q", str(REPO), str(upstream)],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
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
