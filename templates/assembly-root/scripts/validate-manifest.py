#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate this project's `project.yaml` — the SOURCE of the group.

`project.yaml` is the self-describing manifest of a project that has elected
the three-repository shape. It is the SOURCE and an aggregation's
`project-register.yaml` row is DERIVED from it, never the other way round —
which is the only construction that works for an organisation that has no
aggregation and no register at all. A register that disagrees with a manifest
is register drift, not manifest drift.

IT CONFERS NOTHING. `schema:`, `legs[].role` and the topic are descriptive
navigation. No field here grants review authority, clearance eligibility, gate
standing or lifecycle state over any repository it names; authority travels in
grants, and a one-repository project is reviewed identically to this one.

WHAT IS CHECKED
  - the envelope: `schema_version`, `kind`, `id`, `name`, `schema`
  - `elected_by` / `elected_on`, because an election with no elector and no
    date is not an election
  - `topic` equals `xf-project-<id>` derived from the id
  - `shape`: a commit-and-digest pin of the openRepoShape revision this
    project was scaffolded from, `revision_kind: commit`, never a tag
  - `legs`: EXACTLY the roles {assembly, spec, code}, once each, all in one
    organisation, at distinct relative paths, with the assembly leg at `.`
  - every leg's repository name against `contracts/repository-naming.yaml`,
    and the classified form against the declared role

EXIT CODES: 0 valid · 1 findings · 2 refusal (the file is missing or unreadable)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_shape import (  # noqa: E402
    COMMIT_RE, PROJECT_ID_RE, SHA256_RE, TREE_DIGEST_DEFINITION, NamingPolicy,
    Refusal, find_repo_root, load_yaml, repo_basename,
)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
QUALIFIED_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$")
REQUIRED_ROLES = {"assembly", "spec", "code"}


def _findings(manifest: dict, policy: NamingPolicy) -> list[str]:
    out: list[str] = []

    def bad(code: str, detail: str) -> None:
        out.append(f"FINDING {code}: {detail}")

    if manifest.get("schema_version") != 1:
        bad("manifest-schema-version",
            f"schema_version is {manifest.get('schema_version')!r}, expected 1")
    if manifest.get("kind") != "project-manifest":
        bad("manifest-kind",
            f"kind is {manifest.get('kind')!r}, expected 'project-manifest'")
    if manifest.get("schema") != "project-repo-schema":
        bad("manifest-schema",
            f"schema is {manifest.get('schema')!r}, expected "
            "'project-repo-schema'")

    project_id = manifest.get("id")
    if not isinstance(project_id, str) or not PROJECT_ID_RE.match(project_id):
        bad("manifest-id",
            f"id is {project_id!r}; it must match {PROJECT_ID_RE.pattern}")
        project_id = None
    if not isinstance(manifest.get("name"), str) or not manifest.get("name").strip():
        bad("manifest-name", f"name is {manifest.get('name')!r}")

    if not isinstance(manifest.get("elected_by"), str) or \
            not manifest["elected_by"].strip():
        bad("manifest-elected-by",
            "elected_by is empty. Electing the shape is a human's act and the "
            "manifest records whose.")
    elected_on = manifest.get("elected_on")
    if not isinstance(elected_on, str) or not DATE_RE.match(elected_on):
        bad("manifest-elected-on",
            f"elected_on is {elected_on!r}, expected an ISO date YYYY-MM-DD")

    if project_id:
        expected_topic = policy.topic_for(project_id)
        if manifest.get("topic") != expected_topic:
            bad("manifest-topic",
                f"topic is {manifest.get('topic')!r}, expected "
                f"{expected_topic!r} derived from id {project_id!r}")

    reference = manifest.get("reference")
    if reference is not None and (not isinstance(reference, str) or not reference.strip()):
        bad("manifest-reference", f"reference is {reference!r}; drop the key or "
                                  "name the document the election followed")

    shape = manifest.get("shape")
    if not isinstance(shape, dict):
        bad("manifest-shape", "shape is missing; a scaffolded project records "
                              "the openRepoShape revision it was cut from")
    else:
        if not isinstance(shape.get("repository"), str):
            bad("manifest-shape-repository",
                f"shape.repository is {shape.get('repository')!r}")
        if shape.get("revision_kind") != "commit":
            bad("pin-tag-only",
                f"shape.revision_kind is {shape.get('revision_kind')!r}. A tag "
                "can be moved and a commit cannot.")
        if not COMMIT_RE.match(str(shape.get("commit") or "")):
            bad("manifest-shape-commit",
                f"shape.commit is {shape.get('commit')!r}, not 40 hex")
        digests = shape.get("digests")
        if not isinstance(digests, dict) or \
                not SHA256_RE.match(str(digests.get("tree_sha256") or "")):
            bad("manifest-shape-digest",
                f"shape.digests.tree_sha256 is not 64 hex: {digests!r}")
        if shape.get("digest_definition") != TREE_DIGEST_DEFINITION:
            bad("manifest-shape-digest-definition",
                f"shape.digest_definition is "
                f"{shape.get('digest_definition')!r}, expected "
                f"{TREE_DIGEST_DEFINITION!r}")

    legs = manifest.get("legs")
    if not isinstance(legs, list) or not legs:
        bad("manifest-legs", "legs is missing or empty")
        return out

    roles = [leg.get("role") for leg in legs if isinstance(leg, dict)]
    if sorted(r for r in roles if r) != sorted(REQUIRED_ROLES):
        bad("manifest-roles",
            f"legs declare roles {roles!r}; this schema requires exactly "
            f"{sorted(REQUIRED_ROLES)}, once each")

    owners: set[str] = set()
    paths: dict[str, str] = {}
    for leg in legs:
        if not isinstance(leg, dict):
            bad("manifest-leg", f"a leg is not a mapping: {leg!r}")
            continue
        role = leg.get("role")
        repository = leg.get("repository")
        path = leg.get("path")
        if not isinstance(repository, str) or not QUALIFIED_RE.match(repository):
            bad("manifest-leg-repository",
                f"leg {role!r}: repository is {repository!r}, expected "
                "`<org>/<Name>`")
            continue
        owners.add(repository.split("/", 1)[0])
        name = repo_basename(repository)
        found = policy.classify(name)
        if found is None:
            bad("naming-unclassified",
                f"leg {role!r}: {name!r} matches no family in the naming policy")
        elif found[0] != "project-leg":
            bad("naming-not-a-leg",
                f"leg {role!r}: {name!r} classifies as {found[0]!r}, not as a "
                "project leg")
        elif found[1] != role:
            bad("naming-role-mismatch",
                f"leg {role!r}: {name!r} is the {found[1]!r} form of the "
                "project-leg family")
        if not isinstance(path, str) or not path:
            bad("manifest-leg-path", f"leg {role!r}: path is {path!r}")
            continue
        if role == "assembly" and path != ".":
            bad("manifest-assembly-path",
                f"the assembly leg is this repository, so its path is '.', not "
                f"{path!r}")
        if role != "assembly":
            if path.startswith("/") or ".." in Path(path).parts or path == ".":
                bad("manifest-leg-path",
                    f"leg {role!r}: path {path!r} must be a relative path "
                    "inside the assembly root")
            if path in paths:
                bad("manifest-leg-path-collision",
                    f"legs {paths[path]!r} and {role!r} both claim path {path!r}")
            paths[path] = str(role)
    if len(owners) > 1:
        bad("manifest-legs-split",
            f"the legs span more than one organisation: {sorted(owners)}")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--policy", type=Path, default=None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    try:
        root = find_repo_root(args.root or Path(__file__).resolve().parents[1])
        manifest_path = root / "project.yaml"
        if not manifest_path.is_file():
            raise Refusal(
                "manifest-missing",
                f"{manifest_path} does not exist. A project that has elected "
                "this schema declares it in `project.yaml`; a project that has "
                "not, does not run this validator.",
            )
        manifest = load_yaml(manifest_path)
        if not isinstance(manifest, dict):
            raise Refusal("manifest-unreadable", f"{manifest_path}: not a mapping")
        policy_path = args.policy or (root / "contracts" / "repository-naming.yaml")
        policy = NamingPolicy.load(policy_path)
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2

    findings = _findings(manifest, policy)
    for finding in findings:
        print(finding, file=sys.stderr)
    if findings:
        print(f"\n{len(findings)} finding(s) in {manifest_path}", file=sys.stderr)
        return 1
    if not args.quiet:
        print(f"manifest ok: {manifest.get('name')} "
              f"({manifest.get('id')}), {len(manifest.get('legs') or [])} legs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
