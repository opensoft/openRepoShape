#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Classify repository names against `contracts/repository-naming.yaml`.

USAGE
    validate-repository-naming.py NAME [NAME ...]
    validate-repository-naming.py --project project.yaml
    printf '%s\\n' openChart MedxChart | validate-repository-naming.py
    validate-repository-naming.py --explain openxFactory
    validate-repository-naming.py --explain --role assembly MedxScribe
    validate-repository-naming.py --pins openChart --explain MedxChart

A NAME may be given bare (`openChart`) or fully qualified (`opensoft/openChart`);
only the part after the last `/` is classified, because the organisation login
is not part of any family.

WHAT `--role` AND `--pins` ARE FOR. A name in `<Domainx><Product>` form is a
CLAIM of descent, and since the 2026-09-02 ruling a claim needs a REFERENT: it
classifies as a domain descendant only when the project declares a pin on the
matching `open<Product>`. `--pins` supplies those declarations for a one-off
check and `--role` supplies the role the project would declare, so a name can
be classified here on exactly the facts `project.yaml` would carry. With
`--project` both are READ from the manifest instead — the legs' roles, and
`neutral_product_pins:` — which is what the scaffolded project's own gate runs.

EXIT CODES, the same three in every validator this standard ships:
    0  every name classified (and, with `--project`, every declared role and
       the topic agreed with the classification)
    1  a FINDING: at least one name matches no family, or a leg's declared role
       disagrees with the form of its name
    2  a REFUSAL: the question could not be asked at all — the policy file is
       missing, unparsable, or not a naming policy

The 1/2 split is deliberate. "This name is wrong" and "I could not read the
policy" are different facts and a gate that renders them identically invites a
workflow that treats the second as the first.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_shape import (  # noqa: E402
    NamingPolicy, Refusal, load_yaml, repo_basename,
)

DEFAULT_POLICY = Path(__file__).resolve().parents[1] / "contracts" / "repository-naming.yaml"


def _describe(policy: NamingPolicy, name: str, role: str | None,
              pins: set[str]) -> list[str]:
    lines = []
    matches = policy.matches(name)
    if not matches:
        lines.append(f"  {name}: NO FAMILY")
        lines.append("    the four families are: " + ", ".join(
            f["id"] for f in policy.families))
        for family in policy.families:
            lines.append(f"    {family['id']:<18} {family['pattern']}")
        return lines
    found = policy.classify(name, role, pins)
    lines.append(f"  {name}: {found[0]}" + (f" / {found[1]}" if found[1] else ""))
    for family in policy.families:
        hits = [m for m in matches if m[0] == family["id"]]
        mark = "MATCH " if hits else "      "
        role_note = f" (role {hits[0][1]})" if hits and hits[0][1] else ""
        claim = ""
        if hits and policy.requires_referent(family["id"]):
            claim = " [a CLAIM: needs a declared pin on " + " or ".join(
                policy.descendant_referents(name)) + "]"
        lines.append(
            f"    {mark}{family['id']:<18} {family['pattern']}{role_note}{claim}")
    if len(matches) > 1:
        lines.append("    OVERLAP " + found.reason)
        lines.append("    also_matches: " + ", ".join(found.also_matches))
    return lines


def _pins_from_project(data: dict) -> set[str]:
    """The neutral products the manifest DECLARES a pin on.

    `neutral_product_pins:` and nothing else. A leg's
    `naming.referent_declared:` is a RECORD of a declaration, checked by
    `validate-manifest.py` against this list; reading it as a declaration here
    would let a claim vouch for itself.
    """
    return {str(pin) for pin in (data.get("neutral_product_pins") or []) if pin}


def _targets_from_project(policy: NamingPolicy, path: Path) -> tuple[list, list[str]]:
    """Return ([(name, role, pins)], findings) for a `project.yaml` manifest."""
    data = load_yaml(path)
    if not isinstance(data, dict):
        raise Refusal("manifest-unreadable", f"{path}: not a mapping")
    findings: list[str] = []
    pins = _pins_from_project(data)
    targets: list[tuple[str, str | None, set[str]]] = []
    for leg in data.get("legs") or []:
        if not isinstance(leg, dict) or "repository" not in leg:
            findings.append(f"{path}: a leg has no `repository:`")
            continue
        name = repo_basename(str(leg["repository"]))
        declared = leg.get("role")
        declared = str(declared) if declared else None
        targets.append((name, declared, pins))
        found = policy.classify(name, declared, pins)
        # `declared_role` only wins where the NAME satisfies it, so a role that
        # disagrees with its own name still lands here rather than being made
        # true by declaring it.
        if found and found[0] == "project-leg" and declared and found[1] != declared:
            findings.append(
                f"{name}: declared role {declared!r} but the name is the "
                f"{found[1]!r} form of the project-leg family"
            )
    project_id = data.get("id")
    topic = data.get("topic")
    if project_id is not None:
        expected = policy.topic_for(str(project_id))
        if topic is not None and topic != expected:
            findings.append(
                f"topic {topic!r} != {expected!r} derived from id {project_id!r}"
            )
    return targets, findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("names", nargs="*", help="repository names to classify")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--project", type=Path, default=None,
                        help="read the leg names, their roles and the declared "
                             "neutral-product pins from a project.yaml manifest")
    parser.add_argument("--role", default=None,
                        choices=("assembly", "spec", "code"),
                        help="the role the NAMES on the command line are "
                             "offered as; a descendant-form name with no "
                             "referent pin is classified by this")
    parser.add_argument("--pins", default="",
                        help="comma-separated neutral products the project "
                             "declares a pin on, e.g. --pins openChart. A "
                             "`<Domainx><Product>` name is a domain descendant "
                             "only when its `open<Product>` is in this list.")
    parser.add_argument("--explain", action="store_true",
                        help="print every family each name satisfies, why one "
                             "of them won, and what the others are recorded as")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    try:
        policy = NamingPolicy.load(args.policy)
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2

    cli_pins = {p.strip() for p in args.pins.split(",") if p.strip()}
    targets: list[tuple[str, str | None, set[str]]] = [
        (repo_basename(n), args.role, cli_pins) for n in args.names]
    findings: list[str] = []
    if args.project is not None:
        try:
            extra, findings = _targets_from_project(policy, args.project)
        except Refusal as exc:
            print(str(exc), file=sys.stderr)
            return 2
        targets.extend(extra)
    if not targets and not sys.stdin.isatty():
        targets = [(repo_basename(line.strip()), args.role, cli_pins)
                   for line in sys.stdin if line.strip()]
    if not targets:
        print("REFUSED naming-no-target: no names given. Pass names, "
              "`--project project.yaml`, or names on stdin.", file=sys.stderr)
        return 2

    unclassified = []
    for name, role, pins in targets:
        found = policy.classify(name, role, pins)
        if args.explain:
            print("\n".join(_describe(policy, name, role, pins)))
        elif not args.quiet:
            label = "NO FAMILY" if not found else (
                found[0] + (f"/{found[1]}" if found[1] else ""))
            also = f"   also_matches {','.join(found.also_matches)}" \
                if found and found.also_matches else ""
            print(f"  {name:<32} {label}{also}")
        if not found:
            unclassified.append(name)

    for finding in findings:
        print(f"FINDING {finding}", file=sys.stderr)
    if unclassified:
        print(
            "FINDING naming-unclassified: "
            + ", ".join(unclassified)
            + "\n  These names match none of the four families in "
            + str(args.policy)
            + ".\n  A project's three repositories are `<Project>`, "
            "`<Project>-spec` and `<Project>-code`; `<Project>` is one "
            "CamelCase token with no hyphen, underscore, dot or space.",
            file=sys.stderr,
        )
    return 1 if (unclassified or findings) else 0


if __name__ == "__main__":
    sys.exit(main())
