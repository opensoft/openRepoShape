#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate this FAMILY's `family.yaml`, its member pins and its shape copies.

A family is a HOLDER: a repository that pins other projects' assembly roots as
submodules under `members/` and carries the utilities to fetch and bootstrap
them together (Brett Heap, 2026-09-04). It has no spec leg and no code leg,
and this validator is the whole of its gate.

IT CONFERS NOTHING, and neither does membership. No row in `family.yaml`
grants review authority, clearance eligibility, gate standing or lifecycle
state over anything it names; a project in no family is reviewed identically.
A consumer deriving a permission from membership is defective.

WHAT IS CHECKED

  - the envelope: `schema_version`, `kind: family-manifest`, `id`, `name`,
    `org`, `created_by` / `created_on`, `visibility`, `members_dir`
  - the family NAME against `contracts/repository-naming.yaml`, in the
    `family` form. That form is DECLARED-ONLY: `InkRouter` is spelled exactly
    like an assembly root and `family.yaml` is what tells them apart, so the
    declaration is this file's existence and the classifier is asked in those
    terms.
  - `shape`: a commit-and-digest pin of the openRepoShape revision this root
    was cut from, `revision_kind: commit`, never a tag
  - EVERY MEMBER, three ways:
      1. the GITLINK this repository records at `members/<Project>` equals
         `members[].pin.commit` — the same lockstep rule an assembly root
         applies to its legs, for the same reason: two facts that can drift
         apart will;
      2. the tree digest recomputed from the member's own object store equals
         `pin.tree_sha256`, so a gitlink and a pin that agree on a commit
         whose bytes are not the pinned bytes is still drift;
      3. the mounted tree carries a `project.yaml` whose `id` is the `id` this
         row records — a repository at the right commit is not by itself the
         project the row claims.
  - the COPIED shape files, each against its `sha256` row in
    `contracts/shape-pin.yaml`. Editing a copy in place is drift and the exit
    is to carry it upstream, never to update the digest.

EXIT CODES
    0  the manifest is valid, every member is in lockstep, every copy matches
    1  a FINDING: drift a reviewer can act on
    2  a REFUSAL: the question could not be asked — no manifest, an
       uninitialized member, an unreadable pin. An unanswerable question is
       never an implicit pass.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_shape import (  # noqa: E402
    COMMIT_RE, PROJECT_ID_RE, SHA256_RE, TREE_DIGEST_DEFINITION,
    VISIBILITY_CHOICES, NamingPolicy, Refusal, file_sha256, find_repo_root,
    git_out, load_yaml, recorded_gitlink, repo_basename, tree_digest,
)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
QUALIFIED_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$")
MANIFEST = "family.yaml"
DEFAULT_MEMBERS_DIR = "members"

LOCKSTEP = (
    "THE LOCKSTEP RULE: a member's gitlink and its `members[].pin.commit` in "
    "`family.yaml` are ONE invariant. `scripts/family.py bump --member "
    "<Project> --to <commit>` moves both in one commit; moving one alone is "
    "what this refuses."
)


class Report:
    def __init__(self) -> None:
        self.findings: list[str] = []
        self.notes: list[str] = []

    def finding(self, code: str, detail: str) -> None:
        self.findings.append(f"FINDING {code}: {detail}")

    def note(self, text: str) -> None:
        self.notes.append(f"  ok  {text}")


def _check_envelope(manifest: dict, policy: NamingPolicy,
                    report: Report) -> None:
    if manifest.get("schema_version") != 1:
        report.finding("family-schema-version",
                       f"schema_version is {manifest.get('schema_version')!r}, "
                       "expected 1")
    if manifest.get("kind") != "family-manifest":
        report.finding("family-kind",
                       f"kind is {manifest.get('kind')!r}, expected "
                       "'family-manifest'")
    family_id = manifest.get("id")
    if not isinstance(family_id, str) or not PROJECT_ID_RE.match(family_id):
        report.finding("family-id",
                       f"id is {family_id!r}; it must match "
                       f"{PROJECT_ID_RE.pattern}")
    name = manifest.get("name")
    if not isinstance(name, str) or not name.strip():
        report.finding("family-name", f"name is {name!r}")
    else:
        # THE DECLARED-ONLY FORM, ASKED FOR BY NAME. This manifest IS the
        # declaration, so the classifier is given `family` rather than being
        # left to read a bare CamelCase token as the assembly root it also
        # looks like.
        found = policy.classify(repo_basename(name.strip()), "family")
        if found is None:
            report.finding("naming-unclassified",
                           f"{name!r} matches no family in the naming policy. "
                           "A family holder is one CamelCase token with no "
                           "hyphen, underscore, dot or space.")
        elif found.family != "family":
            report.finding(
                "naming-not-a-family",
                f"{name!r} classifies as {found.family!r}"
                + (f"/{found.role}" if found.role else "")
                + f", not as a family holder ({found.reason})")
        else:
            report.note(f"{name}: {found.family} (declared by {MANIFEST})")
    if not isinstance(manifest.get("org"), str) or not manifest.get("org"):
        report.finding("family-org", f"org is {manifest.get('org')!r}")
    if not isinstance(manifest.get("created_by"), str) or \
            not manifest["created_by"].strip():
        report.finding("family-created-by",
                       "created_by is empty. Creating a family is a human's "
                       "act and the manifest records whose.")
    created_on = manifest.get("created_on")
    if not isinstance(created_on, str) or not DATE_RE.match(created_on):
        report.finding("family-created-on",
                       f"created_on is {created_on!r}, expected an ISO date "
                       "YYYY-MM-DD")
    visibility = manifest.get("visibility")
    if visibility is not None and visibility not in VISIBILITY_CHOICES:
        report.finding("family-visibility",
                       f"visibility is {visibility!r}, expected one of "
                       f"{sorted(VISIBILITY_CHOICES)} or no field at all")
    members_dir = manifest.get("members_dir", DEFAULT_MEMBERS_DIR)
    if members_dir != DEFAULT_MEMBERS_DIR:
        report.finding("family-members-dir",
                       f"members_dir is {members_dir!r}; this shape mounts "
                       f"members under {DEFAULT_MEMBERS_DIR!r}, and one name "
                       "is what keeps a reader and a validator looking in the "
                       "same place")

    shape = manifest.get("shape")
    if not isinstance(shape, dict):
        report.finding("family-shape",
                       "shape is missing; a family root records the "
                       "openRepoShape revision it was cut from")
        return
    if shape.get("revision_kind") != "commit":
        report.finding("pin-tag-only",
                       f"shape.revision_kind is {shape.get('revision_kind')!r}. "
                       "A tag can be moved and a commit cannot.")
    if not COMMIT_RE.match(str(shape.get("commit") or "")):
        report.finding("family-shape-commit",
                       f"shape.commit is {shape.get('commit')!r}, not 40 hex")
    digests = shape.get("digests")
    if not isinstance(digests, dict) or \
            not SHA256_RE.match(str(digests.get("tree_sha256") or "")):
        report.finding("family-shape-digest",
                       f"shape.digests.tree_sha256 is not 64 hex: {digests!r}")
    if shape.get("digest_definition") != TREE_DIGEST_DEFINITION:
        report.finding("family-shape-digest-definition",
                       f"shape.digest_definition is "
                       f"{shape.get('digest_definition')!r}, expected "
                       f"{TREE_DIGEST_DEFINITION!r}")


def _check_member(root: Path, row: dict, seen: dict, report: Report) -> None:
    """One member: the row itself, the gitlink, the digest, the identity."""
    project = row.get("project")
    if not isinstance(project, str) or not project:
        report.finding("member-project", f"a member row has no `project:`: "
                                         f"{row!r}")
        return
    if project in seen:
        report.finding("member-duplicate",
                       f"{project} appears more than once in `members:`")
        return
    seen[project] = True

    repository = row.get("repository")
    if not isinstance(repository, str) or not QUALIFIED_RE.match(repository):
        report.finding("member-repository",
                       f"{project}: repository is {repository!r}, expected "
                       "`<org>/<Name>`")
    elif repo_basename(repository) != project:
        report.finding("member-repository-name",
                       f"{project}: repository is {repository!r}, whose name "
                       f"is {repo_basename(repository)!r}. A member's row and "
                       "the repository it pins are the same project or the "
                       "row is describing something else.")

    path = str(row.get("path") or f"{DEFAULT_MEMBERS_DIR}/{project}")
    expected = f"{DEFAULT_MEMBERS_DIR}/{project}"
    if path != expected:
        report.finding("member-path",
                       f"{project}: path is {path!r}, expected {expected!r}")

    pin = row.get("pin")
    if not isinstance(pin, dict):
        report.finding("member-pin", f"{project}: `pin:` is {pin!r}, expected "
                                     "a mapping")
        return
    if pin.get("revision_kind") != "commit":
        report.finding("pin-tag-only",
                       f"{project}: pin.revision_kind is "
                       f"{pin.get('revision_kind')!r}. A tag can be moved and "
                       "a commit cannot; a pin is a commit or it is nothing.")
    commit = str(pin.get("commit") or "")
    if not COMMIT_RE.match(commit):
        raise Refusal(
            "member-pin-commit",
            f"{project}: pin.commit is {commit!r}, which is not 40 hex. An "
            "abbreviated oid, a branch or a tag is a moving reference.")
    commit = commit.lower()

    # ---- the gitlink -------------------------------------------------------
    gitlink = recorded_gitlink(root, path)
    if gitlink is None:
        raise Refusal(
            "member-gitlink-absent",
            f"no gitlink (mode 160000) recorded at {path!r}. {project} is "
            f"named in {MANIFEST} but this repository does not record it as a "
            "submodule.",
            "Remediation: `python3 scripts/family.py add --family-root . "
            f"--member <org>/{project}` mounts and pins it in one commit; a "
            "row with no submodule is a claim about a tree that is not here.")
    if gitlink != commit:
        report.finding(
            "member-gitlink-mismatch",
            f"{path}: gitlink {gitlink} != {MANIFEST} pin {commit}\n  "
            + LOCKSTEP)
    else:
        report.note(f"{path}: gitlink == pin {commit[:12]}")

    # ---- the digest and the identity --------------------------------------
    member = root / path
    if not (member / ".git").exists():
        raise Refusal(
            "member-uninitialized",
            f"{path} is not an initialized submodule checkout, so neither the "
            "pinned digest nor the project it claims can be read. Presence is "
            "not identity and an unreadable surface must fail rather than "
            "degrade.",
            "Remediation: `git submodule update --init --recursive`, or `make "
            "bootstrap`, which resolves a credential for private members "
            "first.")
    try:
        git_out(["rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}"],
                cwd=member)
    except Refusal as exc:
        raise Refusal(
            "member-commit-unresolvable",
            f"{path}: the pinned commit {commit} is not in that member's "
            f"object store ({exc.detail})") from exc

    recorded = pin.get("tree_sha256")
    if not isinstance(recorded, str) or not SHA256_RE.match(recorded):
        report.finding("member-digest-malformed",
                       f"{project}: pin.tree_sha256 is {recorded!r}, not 64 hex")
    elif pin.get("digest_definition", TREE_DIGEST_DEFINITION) != \
            TREE_DIGEST_DEFINITION:
        report.finding(
            "member-digest-definition",
            f"{project}: pin.digest_definition is "
            f"{pin.get('digest_definition')!r}, expected "
            f"{TREE_DIGEST_DEFINITION!r}. A digest whose definition is "
            "unstated is a number, not an identity.")
    else:
        actual = tree_digest(member, commit)
        if actual.lower() != recorded.lower():
            report.finding(
                "member-digest-mismatch",
                f"{project}: pin.tree_sha256 {recorded}\n"
                f"       recomputed at {commit[:12]} {actual}\n"
                "  The gitlink and the pin may agree on a commit whose bytes "
                f"are not the bytes the pin was written against.\n  {LOCKSTEP}")
        else:
            report.note(f"{path}: tree digest recomputes ({recorded[:12]}…)")

    _check_member_identity(root, member, row, project, report)


def _check_member_identity(root: Path, member: Path, row: dict, project: str,
                           report: Report) -> None:
    """The mounted tree is the PROJECT this row claims, not just a commit.

    A member is an assembly root, so it carries `project.yaml`, and that file
    is the SOURCE of what that project is. The row here is a pin of it. Where
    the two disagree the row is wrong, because a family cannot rename a
    project by describing it differently.
    """
    manifest_path = member / "project.yaml"
    if not manifest_path.is_file():
        report.finding(
            "member-not-a-project",
            f"{row.get('path')}: no project.yaml in the mounted tree. A member "
            "is a project's ASSEMBLY ROOT — the repository an engineer clones "
            "— and a family pins assembly roots, never legs.")
        return
    try:
        manifest = load_yaml(manifest_path)
    except Refusal as exc:
        report.finding("member-manifest-unreadable",
                       f"{row.get('path')}/project.yaml: {exc.detail}")
        return
    if not isinstance(manifest, dict):
        report.finding("member-manifest-unreadable",
                       f"{row.get('path')}/project.yaml: not a mapping")
        return
    recorded_id = row.get("id")
    actual_id = manifest.get("id")
    if recorded_id is None:
        report.finding(
            "member-id-absent",
            f"{project}: the row records no `id:`, so nothing checks that the "
            "tree mounted here is the project this row claims")
    elif str(recorded_id) != str(actual_id):
        report.finding(
            "member-id-mismatch",
            f"{row.get('path')}: project.yaml declares id {actual_id!r} but "
            f"{MANIFEST} records {recorded_id!r} for {project}. The project's "
            "own manifest is the source; this row is a pin of it.")
    else:
        report.note(f"{row.get('path')}: project.yaml id {actual_id}")


def _check_shape_pin(root: Path, manifest: dict, report: Report) -> None:
    """The COPIED shape files, each against its digest. Same rule everywhere.

    A family root holds copies of openRepoShape rather than mounting it, so
    there is no gitlink to compare and the identity of the copies is carried
    by the per-file `sha256` rows.
    """
    pin_path = root / "contracts" / "shape-pin.yaml"
    if not pin_path.is_file():
        raise Refusal("shape-pin-missing", f"{pin_path} does not exist")
    pin = load_yaml(pin_path)
    rel = pin_path.relative_to(root)
    if not isinstance(pin, dict):
        raise Refusal("shape-pin-unreadable", f"{pin_path}: not a mapping")
    if pin.get("revision_kind") != "commit":
        report.finding("pin-tag-only",
                       f"{rel}: revision_kind is {pin.get('revision_kind')!r}")
    commit = str(pin.get("commit") or "")
    if not COMMIT_RE.match(commit):
        report.finding("shape-pin-commit",
                       f"{rel}: `commit:` {commit!r} is not 40 hex")
    declared = (manifest.get("shape") or {}).get("commit")
    if declared and str(declared).lower() != commit.lower():
        report.finding("shape-pin-manifest-disagree",
                       f"{rel} commit {commit} != {MANIFEST} shape.commit "
                       f"{declared}")
    before = len(report.findings)
    files = pin.get("files") or []
    if not files:
        report.finding("shape-pin-no-files",
                       f"{rel}: no `files:` rows, so nothing about the copied "
                       "shape files is actually asserted")
    for row in files:
        if not isinstance(row, dict):
            report.finding("shape-pin-row",
                           f"{rel}: a files row is not a mapping")
            continue
        target = root / str(row.get("path"))
        if not target.is_file():
            report.finding("shape-copy-missing",
                           f"{rel}: {row.get('path')} is pinned but absent")
            continue
        actual = file_sha256(target)
        if actual != str(row.get("sha256", "")).lower():
            report.finding(
                "shape-copy-drift",
                f"{row.get('path')}: sha256 {actual}\n"
                f"       {rel} records {row.get('sha256')}\n"
                "  A shape file was edited in place. Either revert it, or "
                "carry the change upstream to openRepoShape and re-pin with "
                "`update-shape.py`.")
    if len(report.findings) == before:
        report.note(f"{rel}: {len(files)} copied shape file(s) match their "
                    "digests")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None,
                        help="the family root (default: the enclosing "
                             "repository)")
    parser.add_argument("--policy", type=Path, default=None)
    parser.add_argument("--pins", action="store_true",
                        help="the member lockstep check alone: gitlink, "
                             "digest and identity, with no envelope and no "
                             "shape-copy check (what `make pins` runs)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    report = Report()
    try:
        root = find_repo_root(args.root or Path(__file__).resolve().parents[1])
        manifest_path = root / MANIFEST
        if not manifest_path.is_file():
            raise Refusal(
                "family-manifest-missing",
                f"{manifest_path} does not exist. A family holder declares "
                f"itself in `{MANIFEST}`; a repository without one is not a "
                "family and does not run this validator.",
                "Remediation: `python3 scripts/family.py init --org <org> "
                "--family <Name>` creates one. An ordinary project runs "
                "`validate-manifest.py` instead.")
        manifest = load_yaml(manifest_path)
        if not isinstance(manifest, dict):
            raise Refusal("family-manifest-unreadable",
                          f"{manifest_path}: not a mapping")
        policy_path = args.policy or (root / "contracts" /
                                      "repository-naming.yaml")
        policy = NamingPolicy.load(policy_path)
        if not args.pins:
            _check_envelope(manifest, policy, report)

        members = manifest.get("members")
        if members is None:
            members = []
        if not isinstance(members, list):
            raise Refusal("family-members-unreadable",
                          f"{manifest_path}: `members:` is {members!r}, "
                          "expected a list")
        seen: dict[str, bool] = {}
        for row in members:
            if not isinstance(row, dict):
                report.finding("member-row",
                               f"a member is not a mapping: {row!r}")
                continue
            _check_member(root, row, seen, report)
        if not members:
            report.note("no members yet: a family with none is empty, not "
                        "wrong")
        if not args.pins:
            _check_shape_pin(root, manifest, report)
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not args.quiet:
        for note in report.notes:
            print(note)
    for finding in report.findings:
        print(finding, file=sys.stderr)
    if report.findings:
        print(f"\n{len(report.findings)} finding(s) in {MANIFEST}. {LOCKSTEP}",
              file=sys.stderr)
        return 1
    print(f"family ok: {manifest.get('name')} ({manifest.get('id')}), "
          f"{len(members)} member(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
