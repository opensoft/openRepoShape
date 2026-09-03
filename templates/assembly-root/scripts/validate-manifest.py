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
    and the classified form against the declared role. TWO forms may be an
    assembly root: the bare project-leg form, and — since 2026-09-02 — a
    DECLARED domain descendant, because a descendant may carry legs
    (`MedxGlass` pins `openGlass` and still mounts `MedxGlass-spec` and
    `MedxGlass-code`). The pin is what admits the second, so the refusal for
    `referent_declared: true` with no pin file beside it stands unchanged.
  - each leg's OPTIONAL `naming:` record — that `form` and `role` are the
    classification the policy actually returns for that name given what this
    manifest declares, that `also_matches` lists every other form the name
    satisfies, and that `referent_declared: true` has the pin file to show for
    it. A `<Domainx><Product>` name is a domain descendant only when the
    matching `open<Product>` is in `neutral_product_pins:` and
    `contracts/<referent>-pin.yaml` exists (2026-09-02: a claim needs a
    referent). The whole check is OFFLINE.

EXIT CODES: 0 valid · 1 findings · 2 refusal (the file is missing or unreadable)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_shape import (  # noqa: E402
    COMMIT_RE, PROJECT_ID_RE, SHA256_RE, TREE_DIGEST_DEFINITION,
    VISIBILITY_CHOICES, NamingPolicy, Refusal, accepts_role, find_repo_root,
    load_yaml, repo_basename,
)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
QUALIFIED_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$")
REQUIRED_ROLES = {"assembly", "spec", "code"}


def _declared_pins(manifest: dict) -> set[str]:
    """The neutral products this manifest DECLARES a pin on.

    `neutral_product_pins:` is the declaration and the ONLY declaration. A
    leg's `naming.referent_declared:` is a RECORD of one, checked against this
    set — never folded into it. Reading the record as a declaration would let
    a `naming:` block assert its own descent, which is a claim promoting
    itself to a referent: exactly the move the 2026-09-02 ruling forbids.
    """
    return {str(pin) for pin in (manifest.get("neutral_product_pins") or []) if pin}


def _naming_findings(leg_role, name: str, naming, policy: NamingPolicy,
                     pins: set[str], root: Path | None) -> list[str]:
    """Check one leg's OPTIONAL `naming:` record against the policy.

    Absent is fine: the block is a record, not a requirement, and a manifest
    written before this field existed is not thereby wrong. Present and
    disagreeing with the classifier is a FINDING, because a record that can
    drift from the thing it records is worse than no record.
    """
    out: list[str] = []
    if naming is None:
        return out
    if not isinstance(naming, dict):
        return [f"FINDING manifest-naming: leg {leg_role!r}: naming is "
                f"{naming!r}, expected a mapping"]
    found = policy.classify(name, str(leg_role) if leg_role else None, pins)
    if found is None:
        return out  # already reported as naming-unclassified
    if naming.get("form") != found.family:
        out.append(f"FINDING naming-form: leg {leg_role!r}: naming.form is "
                   f"{naming.get('form')!r}, but {name!r} classifies as "
                   f"{found.family!r}")
    recorded_role = naming.get("role")
    if (recorded_role or None) != found.role:
        out.append(f"FINDING naming-role: leg {leg_role!r}: naming.role is "
                   f"{recorded_role!r}, but {name!r} classifies as "
                   f"{found.role!r}")
    also = naming.get("also_matches")
    if also is None:
        also = []
    if not isinstance(also, list):
        out.append(f"FINDING naming-also-matches: leg {leg_role!r}: "
                   f"also_matches is {also!r}, expected a list")
    elif sorted(str(a) for a in also) != sorted(found.also_matches):
        out.append(
            f"FINDING naming-also-matches: leg {leg_role!r}: also_matches is "
            f"{sorted(str(a) for a in also)}, but {name!r} also satisfies "
            f"{sorted(found.also_matches)}. `also_matches` records the forms "
            "that were NOT chosen; it is not a place to add or drop one.")

    # The referent. `descendant_referents()` returns every spelling that would
    # serve — `open<Product>` canonically, and the x-stem `openx<Product>` the
    # neutral family also admits — so the record and the pins are checked
    # against the same set the classifier consulted, not against one spelling.
    referents = policy.descendant_referents(name)
    recorded_referent = naming.get("descendant_referent")
    if not referents:
        if recorded_referent is not None:
            out.append(
                f"FINDING naming-referent: leg {leg_role!r}: "
                f"descendant_referent is {recorded_referent!r}, but {name!r} "
                "is not in `<Domainx><Product>` form and claims descent from "
                "nothing")
        return out

    if recorded_referent is not None and str(recorded_referent) not in referents:
        out.append(
            f"FINDING naming-referent: leg {leg_role!r}: descendant_referent "
            f"is {recorded_referent!r}, but {name!r} would need "
            + " or ".join(referents))
    declared_pins = {pin.casefold() for pin in pins}
    satisfied = next((r for r in referents if r.casefold() in declared_pins), None)
    declared = naming.get("referent_declared")
    if declared is not None and bool(declared) != (satisfied is not None):
        out.append(
            f"FINDING naming-referent-declared: leg {leg_role!r}: "
            f"referent_declared is {declared!r}, but " + " / ".join(referents)
            + (" is" if len(referents) == 1 else " are")
            + (" in" if satisfied else " not in")
            + " this manifest's `neutral_product_pins:`. A descendant form is "
            "a claim; the pin is the referent.")
    if declared is True and satisfied and root is not None:
        pin_path = root / "contracts" / f"{satisfied.lower()}-pin.yaml"
        if not pin_path.is_file():
            out.append(
                f"FINDING naming-referent-missing: leg {leg_role!r}: "
                f"{satisfied} is declared as this leg's referent, but "
                f"{pin_path.relative_to(root)} does not exist. A declared pin "
                "that is not in the tree is a claim wearing the costume of a "
                "referent.")
    return out


def _findings(manifest: dict, policy: NamingPolicy, root=None) -> list[str]:
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

    # OPTIONAL, like `reference:` — a manifest scaffolded before this field
    # existed is not thereby wrong. Present and not one of the three real
    # GitHub visibilities is a finding.
    visibility = manifest.get("visibility")
    if visibility is not None and visibility not in VISIBILITY_CHOICES:
        bad("manifest-visibility",
            f"visibility is {visibility!r}, expected one of "
            f"{sorted(VISIBILITY_CHOICES)} or no field at all")

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

    pins = _declared_pins(manifest)
    declared_pins = manifest.get("neutral_product_pins")
    if declared_pins is not None and not isinstance(declared_pins, list):
        bad("manifest-neutral-product-pins",
            f"neutral_product_pins is {declared_pins!r}, expected a list of "
            "neutral product names")

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
        # The DECLARED role and the declared pins are what the classifier is
        # given, because that is what the project says about itself. A role
        # only wins where the NAME satisfies it, so declaring `assembly` over
        # `<Project>-spec` still lands in naming-role-mismatch below.
        found = policy.classify(name, str(role) if role else None, pins)
        if found is None:
            bad("naming-unclassified",
                f"leg {role!r}: {name!r} matches no family in the naming policy")
        elif accepts_role(found, str(role or "")):
            # Either the project-leg family in exactly the declared role, or a
            # DECLARED domain descendant serving as the assembly root, which
            # the 2026-09-02 ruling admits: a descendant may carry legs.
            # `accepts_role` is the one definition; see `repo_shape`.
            pass
        elif found[0] != "project-leg":
            bad("naming-not-a-leg",
                f"leg {role!r}: {name!r} classifies as {found[0]!r}, not as a "
                f"project leg ({found.reason})")
        else:
            bad("naming-role-mismatch",
                f"leg {role!r}: {name!r} is the {found[1]!r} form of the "
                "project-leg family")
        out.extend(_naming_findings(role, name, leg.get("naming"), policy,
                                    pins, root))
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

    findings = _findings(manifest, policy, root)
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
