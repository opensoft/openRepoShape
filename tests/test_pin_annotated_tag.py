# SPDX-License-Identifier: Apache-2.0
"""An annotated tag's own object id given as a pin's commit (#651).

`git rev-parse v1.2` prints a release tag's OWN id, 40 hex, so a person can
pass it as `--pin openGlass@<id>`, and `PIN_ARG_RE` takes it. On main
a5245427 nothing asked what the id was. `declared_pin_values`, which
`scaffold-project.py` and `adopt-project.py plan` share, read the digest with
`git ls-tree`, which peels a tag to its tree. So `plan` recorded the TAG's id
as the pin's `commit:`, and `execute` and the scaffold, its `--dry-run` alike,
wrote it under the pin file's `revision_kind: commit` and "A COMMIT, NEVER A
TAG". The root's own `validate-pins.py` passed it, for the same reason. A tag
of a tag went the same way, and so did a TREE's id; a blob's was
`pin-source-unreadable`.

Now the id is asked where its digest is read: `git cat-file -t` in the
`--pin-source` clone, or the forge's own GraphQL `object(oid:)` with none.
An annotated tag's id is PEELED to the commit it names, as `bump-leg.py
--to` (#534), `family.py add --at` and `family.py bump --to` (#541) peel one,
and one line says so. A tree, a blob, or a tag of either, is refused
`pin-not-a-commit`, naming which. `check` asks the same of the clone `plan`
read the digest from, so a plan an earlier `plan` or a hand edit left with
such an id is `plan-pin-not-a-commit`, and `execute` refuses it before any
leg.

NO NETWORK AND NO GITHUB: the product is a local stand-in, and the forge is
the stub `gh` of `test_adopt_pins.py`, which answers from a file.

#912 holds two questions this file asks. A tag the `--pin-source` clone
holds without the commit it names cannot be peeled there, and was refused
"an annotated tag that names no commit"; the clone cannot say what it
names, so it is the clone that cannot answer, `pin-source-unreadable`, as
before #651. And where `check` asks the pin nothing, because the clone
`plan` read it from is gone or partial or `gh api` read it, its NOTE said
only that the digest was not rechecked, so a recorded tag's id passed as a
commit; the NOTE now says its commit was not asked either.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import (SCAFFOLD, WINDOWS_SKIP, git, planned,
                      refused_before_any_leg, run_script)
from test_adopt_pins import (  # noqa: F401
    ENTRY, GATE_RECOMPUTES, NOT_RECHECKED, ORG, PIN_FILE, PLANNED, PROJECT,
    adopter, asked_what, check_plan, forge_objects, gh_calls, gh_env,
    make_product, pin_entry, pin_notes, plan_with, read_from,
    shape_materialize, tree_listing, with_pins,
)
from test_scaffold_pin_and_reuse import assert_pin_digest_recomputed
from repo_shape import double_quoted, load_yaml, tree_digest

NOT_A_COMMIT = "pin-not-a-commit"
PIN_SOURCE, DRY_RUN = "--pin-source", "--dry-run"
UTF8 = "utf-8"
PLAN_NOT_A_COMMIT = "plan-pin-not-a-commit"
REPOSITORY = "opensoft/openGlass"
#: Where the forge path's refusals say the id was asked.
ON_THE_FORGE = f"{REPOSITORY} on the forge"

#: The ids `tagged` holds that name a commit through annotated tags.
PEELED = [pytest.param("tag", id="an-annotated-tag"),
          pytest.param("tag_of_tag", id="a-tag-of-a-tag")]
#: `(the id in `tagged`, how a refusal says it names no commit)`.
NO_COMMIT = [
    pytest.param("tree", "names a tree", id="a-tree"),
    pytest.param("blob", "names a blob", id="a-blob"),
    pytest.param("tree_tag", "is an annotated tag of a tree",
                 id="a-tag-of-a-tree"),
]


@pytest.fixture(scope="module")
def tagged(tmp_path_factory) -> SimpleNamespace:
    """A stand-in for `openGlass` whose second commit is tagged `v1` (an
    annotated tag), `v1` tagged again (a tag of a tag), and its tree tagged
    too: `commit` and each id a person could pass for it."""
    path, _, commit = make_product(
        tmp_path_factory.mktemp("tagged") / "openGlass")

    def rev(name: str) -> str:
        return git("rev-parse", name, cwd=path).stdout.strip()

    tree = rev(f"{commit}^{{tree}}")
    git("tag", "-a", "-m", "the release", "v1", commit, cwd=path)
    git("tag", "-a", "-m", "the release, tagged again", "v1-again", "v1",
        cwd=path)
    git("tag", "-a", "-m", "a tree", "a-tree", tree, cwd=path)
    return SimpleNamespace(path=path, commit=commit, tag=rev("v1"),
                           tag_of_tag=rev("v1-again"), tree=tree,
                           blob=rev(f"{commit}:README.md"),
                           tree_tag=rev("a-tree"))


def forge(tagged: SimpleNamespace) -> dict:
    """What the forge's GraphQL `object(oid:)` answers for each id."""
    def tag_of(kind: str, oid: str) -> dict:
        return {"__typename": "Tag",
                "target": {"__typename": kind, "oid": oid}}

    return {tagged.commit: {"__typename": "Commit"},
            tagged.tag: tag_of("Commit", tagged.commit),
            tagged.tag_of_tag: tag_of("Tag", tagged.tag),
            tagged.tree: {"__typename": "Tree"},
            tagged.blob: {"__typename": "Blob"},
            tagged.tree_tag: tag_of("Tree", tagged.tree)}


def answering(base: Path, tagged: SimpleNamespace, env: dict) -> dict:
    """`env` with the stub `gh` answering as the forge would for `tagged`:
    what each id names, and the tree listing at its commit."""
    return {**env,
            "GH_STUB_OBJECTS": str(forge_objects(base / "objects.json",
                                                 forge(tagged))),
            "GH_STUB_TREE": str(tree_listing(base / "tree.json", tagged.path,
                                             tagged.commit))}


def peeled(named: str, commit: str) -> str:
    """The line both tools print when a `--pin` id is an annotated tag."""
    return (f"--pin {REPOSITORY} @ {named[:12]} is an annotated tag; it "
            f"names commit {commit[:12]}, which is what the pin records")


def refused(result, named: str, what: str, where: str) -> None:
    """`result` is `pin-not-a-commit` for `--pin openGlass@<named>`, exit 2,
    with the remediation that says what to pass instead."""
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr == (
        f"REFUSED {NOT_A_COMMIT}: --pin openGlass@{named} {what} in {where}, "
        f"not a commit\n{shape_materialize.PIN_NOT_A_COMMIT_REMEDIATION}\n")


def scaffold(base: Path, named: str, *extra: str,
             env: dict | None = None):
    """`scaffold-project.py --pin openGlass@<named>` into `base`."""
    return run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                      "--elected-by", "Test Human",
                      "--elected-on", "2026-09-02",
                      "--pin", f"openGlass@{named}",
                      "--local-remote-dir", str(base / "remotes"),
                      "--work-dir", str(base / "work"), *extra, env=env)


# --- `plan` and the scaffold, from a `--pin-source` clone --------------------

@pytest.mark.parametrize("kind", PEELED)
def test_plan_records_the_commit_an_annotated_tag_names(source_repo, tmp_path,
                                                        tagged, gh_env, kind):
    """`plan` records the commit, its digest, and says it peeled the tag;
    the tag's own id is in no value it records."""
    named = getattr(tagged, kind)
    out = tmp_path / "plan.yaml"
    result = plan_with(source_repo, out, f"openGlass@{named}",
                       extra=(PIN_SOURCE, str(tagged.path)), env=gh_env)
    assert result.returncode == 0, result.stdout + result.stderr
    pin = load_yaml(out)["pins"][0]
    assert pin["commit"] == tagged.commit
    assert pin["tree_sha256"] == tree_digest(tagged.path, tagged.commit)
    assert peeled(named, tagged.commit) in result.stdout.splitlines()
    assert f"pin        {REPOSITORY} @ {tagged.commit[:12]} " in result.stdout
    assert named not in out.read_text(encoding=UTF8)
    assert gh_calls(gh_env) == ""


@pytest.mark.parametrize("dry_run", [pytest.param(True, id="dry-run"),
                                     pytest.param(False, id="real")])
def test_the_scaffold_pins_the_commit_an_annotated_tag_names(tmp_path, tagged,
                                                             gh_env, dry_run):
    """The scaffold reads its pin with the same reader: the dry run says
    what the real run writes, and the pin file the real run commits holds
    the commit, which the root's own `validate-pins.py` recomputes."""
    result = scaffold(tmp_path, tagged.tag, PIN_SOURCE, str(tagged.path),
                      *([DRY_RUN] if dry_run else []), env=gh_env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert peeled(tagged.tag, tagged.commit) in result.stdout.splitlines()
    assert (f"pin          {REPOSITORY} @ {tagged.commit[:12]} "
            in result.stdout), result.stdout
    assert gh_calls(gh_env) == ""
    if dry_run:
        assert not (tmp_path / "remotes").exists()
        return
    root = tmp_path / "work" / PROJECT
    pin_file = root / PIN_FILE
    pin = load_yaml(pin_file)
    assert pin["commit"] == tagged.commit
    assert pin["revision_kind"] == "commit"
    assert tagged.tag not in pin_file.read_text(encoding=UTF8)
    gate = run_script(root / "scripts" / "validate-pins.py", PIN_SOURCE,
                      f"openGlass={tagged.path}", cwd=root)
    assert gate.returncode == 0, gate.stdout + gate.stderr
    assert_pin_digest_recomputed(gate, "openGlass", tagged.commit)


@pytest.mark.parametrize(("kind", "what"), NO_COMMIT)
@pytest.mark.parametrize("tool", ["adopt-plan", "scaffold-dry-run"])
def test_an_id_that_names_no_commit_is_refused(source_repo, tmp_path, tagged,
                                               gh_env, kind, what, tool):
    """A tree's or a blob's id, or a tag of one, names no commit at all:
    both tools refuse it by name, before `plan` writes a plan or the
    scaffold makes a remote."""
    named = getattr(tagged, kind)
    source = (PIN_SOURCE, str(tagged.path))
    if tool == "adopt-plan":
        made = tmp_path / "plan.yaml"
        result = plan_with(source_repo, made, f"openGlass@{named}",
                           extra=source, env=gh_env)
    else:
        made = tmp_path / "remotes"
        result = scaffold(tmp_path, named, *source, DRY_RUN, env=gh_env)
    refused(result, named, what, f"the clone at {tagged.path.resolve()}")
    assert not made.exists()
    assert gh_calls(gh_env) == ""


# --- with no `--pin-source`: the forge is asked ------------------------------

@WINDOWS_SKIP  # the stub `gh` is a `#!` script; Windows executes none
@pytest.mark.parametrize("kind", PEELED)
def test_with_no_pin_source_the_forge_says_what_the_id_names(
        source_repo, tmp_path, tagged, gh_env, kind):
    """`gh api graphql` asks the forge what the id is, each tag in turn,
    and the tree listing is read at the commit the last one names."""
    named = getattr(tagged, kind)
    out = tmp_path / "plan.yaml"
    result = plan_with(source_repo, out, f"openGlass@{named}",
                       env=answering(tmp_path, tagged, gh_env))
    assert result.returncode == 0, result.stdout + result.stderr
    pin = load_yaml(out)["pins"][0]
    assert pin["commit"] == tagged.commit
    assert pin["tree_sha256"] == tree_digest(tagged.path, tagged.commit)
    assert peeled(named, tagged.commit) in result.stdout.splitlines()
    asked = [named] + ([tagged.tag] if kind == "tag_of_tag" else [])
    assert gh_calls(gh_env).splitlines() == [
        *(asked_what(oid) for oid in asked),
        f"api repos/{REPOSITORY}/git/trees/{tagged.commit}?recursive=1"]


@WINDOWS_SKIP  # the stub `gh` is a `#!` script; Windows executes none
@pytest.mark.parametrize(("kind", "what"), NO_COMMIT)
def test_the_forge_path_refuses_an_id_that_names_no_commit(
        tmp_path, tagged, gh_env, kind, what):
    """The scaffold's dry run, with no `--pin-source`: the forge's answer
    is refused in the same words, and no tree listing is asked for."""
    named = getattr(tagged, kind)
    result = scaffold(tmp_path, named, DRY_RUN,
                      env=answering(tmp_path, tagged, gh_env))
    refused(result, named, what, ON_THE_FORGE)
    assert gh_calls(gh_env).splitlines() == [asked_what(named)]


@WINDOWS_SKIP  # the stub `gh` is a `#!` script; Windows executes none
def test_an_id_the_forge_does_not_hold_is_unreadable(source_repo, tmp_path,
                                                     tagged, gh_env):
    """An id the forge holds no object for is `pin-unreadable`, the
    refusal of a forge that cannot answer, before any tree is read."""
    missing = "c0ffee" * 6 + "c0ff"
    out = tmp_path / "plan.yaml"
    result = plan_with(source_repo, out, f"openGlass@{missing}",
                       env=answering(tmp_path, tagged, gh_env))
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(
        f"REFUSED pin-unreadable: `gh api` could not read {REPOSITORY} @ "
        f"{missing}: the forge holds no object {missing} in {REPOSITORY}\n"), \
        result.stderr
    assert gh_calls(gh_env).splitlines() == [asked_what(missing)]
    assert not out.exists()


# --- `check` asks the clone `plan` read the digest from ----------------------

@pytest.fixture
def tagged_clone(tmp_path, tagged) -> Path:
    """A copy of `tagged`: the clone a plan below records `plan` read its
    digest from."""
    clone = tmp_path / "openGlass-clone"
    shutil.copytree(tagged.path, clone, symlinks=True)
    return clone


@pytest.mark.parametrize(("kind", "what"), [
    *(pytest.param(kind.values[0], None, id=kind.id) for kind in PEELED),
    *NO_COMMIT])
def test_check_finds_a_recorded_id_that_is_no_commit(
        adopter, monkeypatch, source_repo, tmp_path, tagged, tagged_clone,
        gh_env, kind, what):
    """A plan whose `commit:` is a tag's id -- written by `plan` before
    #651, or edited in -- recomputes the commit's digest, so `check` passed
    it and `execute` wrote it. `check` now asks the clone what the id is
    and names the commit a tag names; `execute` refuses with that line
    before any leg."""
    named = getattr(tagged, kind)
    what = what or f"is an annotated tag of commit {tagged.commit}"
    plan = planned(source_repo, tmp_path, PLANNED)
    with_pins(plan, read_from(tagged_clone, named,
                              tree_digest(tagged.path, tagged.commit)))
    checked = check_plan(plan, env=gh_env)
    assert checked.returncode == 1, checked.stdout + checked.stderr
    lines = [line for line in checked.stderr.splitlines()
             if line.startswith("FINDING ")]
    assert len(lines) == 1, checked.stderr
    assert lines[0].startswith(
        f"FINDING {PLAN_NOT_A_COMMIT}: {ENTRY} records `commit: {named}`, "
        f"which {what} in the clone `plan` read its digest from, "
        f"{tagged_clone}, not a commit. "), lines[0]
    assert lines[0].endswith(
        f"re-run `plan` with `--pin {REPOSITORY}@<40 hex commit>`, which "
        "reads the digest there (from `--pin-source <clone>` with no "
        "network, or `gh api`) and records both, as `scaffold-project.py "
        "--pin` takes it."), lines[0]
    refusal = refused_before_any_leg(adopter, monkeypatch, plan, tmp_path)
    assert refusal.code == PLAN_NOT_A_COMMIT
    assert gh_calls(gh_env) == ""


# --- a tag whose commit the clone lacks (#912) -------------------------------
#
# `commit_in_clone` peels an annotated tag with `rev-parse <id>^{}`, and in a
# clone that holds the tag but not the commit it names, git answers "missing
# object referenced by" the tag, and the peel nothing. On main 6c861635 the
# id was then refused "an annotated tag that names no commit", by `plan`, the
# scaffold and `check` alike, which no tag of a commit is. Nothing in that
# clone says what the tag names, so it is asked no further: the digest's
# reader finds no tree at the id and refuses the clone as one that cannot
# answer, saying to fetch the commit into it, as it did before #651.

#: The refusal of a clone that cannot answer for a pin, and of a plan's.
UNREADABLE = "pin-source-unreadable"
PLAN_UNREADABLE = "plan-pin-source-unreadable"


@pytest.fixture
def lacking(tmp_path, tagged) -> Path:
    """A clone that holds the annotated tag `v1` and the tag of it, and not
    the commit they name: the two tag objects alone, written into it as
    `git hash-object` writes an object, from their bytes."""
    clone = tmp_path / "openGlass-lacking"
    git("init", "-q", "-b", "main", str(clone), cwd=tmp_path)
    for oid in (tagged.tag, tagged.tag_of_tag):
        raw = subprocess.run(["git", "cat-file", "tag", oid],
                             cwd=tagged.path, capture_output=True,
                             check=True).stdout
        made = subprocess.run(["git", "hash-object", "-t", "tag", "-w",
                               "--stdin"], cwd=clone, input=raw,
                              capture_output=True, check=True)
        assert made.stdout.decode().strip() == oid
    assert git("cat-file", "-e", tagged.commit, cwd=clone,
               check=False).returncode != 0
    return clone


@pytest.mark.parametrize("kind", PEELED)
def test_a_clone_lacking_a_tags_commit_cannot_say_what_it_names(
        tagged, lacking, kind):
    """`commit_in_clone` answers such a tag as an id the clone cannot say
    anything of: the id as given, with no reason to refuse it."""
    named = getattr(tagged, kind)
    assert shape_materialize.commit_in_clone(lacking, named) == (named, "")


@pytest.mark.parametrize("kind", PEELED)
@pytest.mark.parametrize("tool", ["adopt-plan", "scaffold-dry-run"])
def test_a_tag_whose_commit_the_clone_lacks_is_unreadable_there(
        source_repo, tmp_path, tagged, lacking, gh_env, kind, tool):
    """Both tools refuse it as a clone that cannot answer for the pin, with
    the remediation that says to fetch the commit into it, and never as an
    id that names no commit: before `plan` writes a plan or the scaffold
    makes a remote, and with no `gh`."""
    named = getattr(tagged, kind)
    source = (PIN_SOURCE, str(lacking))
    if tool == "adopt-plan":
        made = tmp_path / "plan.yaml"
        result = plan_with(source_repo, made, f"openGlass@{named}",
                           extra=source, env=gh_env)
    else:
        made = tmp_path / "remotes"
        result = scaffold(tmp_path, named, *source, DRY_RUN, env=gh_env)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(
        f"REFUSED {UNREADABLE}: {lacking.resolve()} could not answer for "
        f"{REPOSITORY} @ {named}: "), result.stderr
    assert "a clone of that repository that HAS the pinned commit (`git " \
           "fetch --all` first)" in result.stderr, result.stderr
    assert "annotated tag" not in result.stdout + result.stderr
    assert not made.exists()
    assert gh_calls(gh_env) == ""


def test_check_finds_a_recorded_clone_lacking_a_tags_commit_unreadable(
        adopter, monkeypatch, source_repo, tmp_path, tagged, lacking,
        gh_env):
    """`check` asks the clone `plan` read the digest from the same question,
    so a plan that records such a tag's id finds that clone unable to
    answer for it, as for a commit it lacks; `execute` refuses it before
    any leg."""
    plan = planned(source_repo, tmp_path, PLANNED)
    with_pins(plan, read_from(lacking, tagged.tag,
                              tree_digest(tagged.path, tagged.commit)))
    checked = check_plan(plan, env=gh_env)
    assert checked.returncode == 1, checked.stdout + checked.stderr
    lines = [line for line in checked.stderr.splitlines()
             if line.startswith("FINDING ")]
    assert len(lines) == 1, checked.stderr
    assert lines[0].startswith(
        f"FINDING {PLAN_UNREADABLE}: {ENTRY} records `commit: {tagged.tag}`, "
        "and the clone its `digest_source:` names cannot answer for it: "
        f"{lacking} could not answer for {REPOSITORY} @ {tagged.tag}: "), \
        lines[0]
    assert "annotated tag" not in checked.stdout + checked.stderr
    refusal = refused_before_any_leg(adopter, monkeypatch, plan, tmp_path)
    assert refusal.code == PLAN_UNREADABLE
    assert gh_calls(gh_env) == ""


# --- a recorded id `check` asks nothing of (#912) ----------------------------
#
# #457's L1-82, its second case. `check` asks a recorded `commit:` what it
# names only of the clone `plan` read the digest from, still at its path and
# no partial clone. Where it is gone or partial, or `gh api` read the digest,
# `check` asks the pin nothing, and reads no network to ask it, so on main
# 6c861635 a tag's id recorded there passed `check`, and `execute` wrote it,
# with a NOTE that said only that the digest was not rechecked. The NOTE now
# says the commit was not asked either, and why.

#: Where `check` asks a recorded pin nothing.
NOT_ASKED = ["gone", "partial", "gh-api"]


def not_asked(where: str, base: Path, clone: Path) -> tuple[str, str]:
    """`(the digest_source: a plan records, why check asks the pin nothing)`
    for `where`: a clone no longer at its path under `base`, `clone` made a
    partial clone by its config alone (nothing is fetched), or `gh api`."""
    if where == "gh-api":
        return ("gh-api-tree-recursive",
                "`plan` read it with `gh api`, and `check` reads no network")
    if where == "gone":
        gone = base / "openGlass-gone"
        return (f"local-clone ({gone})",
                f"the clone `plan` read it from is not at {gone}")
    for setting in (("core.repositoryformatversion", "1"),
                    ("extensions.partialClone", "origin"),
                    ("remote.origin.promisor", "true")):
        git("config", *setting, cwd=clone)
    return (f"local-clone ({clone})",
            f"the clone at {clone} is a partial clone (`git clone "
            "--filter`), whose `git` fetches what it lacks over the network, "
            "and `check` reads no network")


@pytest.mark.parametrize("where", NOT_ASKED)
def test_check_says_it_did_not_ask_a_recorded_id_it_cannot_ask(
        source_repo, tmp_path, tagged, tagged_clone, gh_env, where):
    """A tag's id recorded as the pin's `commit:`, with its commit's digest,
    where `check` asks the pin nothing: it still passes and runs no `gh`,
    and its one NOTE about the pin says that neither the digest nor what
    the commit names was asked here, and why."""
    recorded, why = not_asked(where, tmp_path, tagged_clone)
    plan = planned(source_repo, tmp_path, PLANNED)
    with_pins(plan, "pins:\n" + pin_entry(
        commit=tagged.tag, digest=tree_digest(tagged.path, tagged.commit),
        source=double_quoted(recorded)[1:-1]))
    checked = check_plan(plan, env=gh_env)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    notes = pin_notes(checked)
    assert notes == [f"{NOT_RECHECKED}{why}. {GATE_RECOMPUTES}"], \
        checked.stdout
    assert (f"NOTE {ENTRY}: digest NOT rechecked here, nor its `commit:` "
            f"asked whether it names a commit: {why}. ") in notes[0], notes
    assert notes[0].endswith("; `plan` asks what the commit names where it "
                             "reads the digest."), notes
    assert gh_calls(gh_env) == ""
