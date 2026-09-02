#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Classify repository names against `contracts/repository-naming.yaml`.

USAGE
    validate-repository-naming.py NAME [NAME ...]
    validate-repository-naming.py --project project.yaml
    printf '%s\\n' openChart MedxChart | validate-repository-naming.py
    validate-repository-naming.py --explain openxFactory

A NAME may be given bare (`openChart`) or fully qualified (`opensoft/openChart`);
only the part after the last `/` is classified, because the organisation login
is not part of any family.

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


def _describe(policy: NamingPolicy, name: str) -> list[str]:
    lines = []
    matches = policy.matches(name)
    if not matches:
        lines.append(f"  {name}: NO FAMILY")
        lines.append("    the four families are: " + ", ".join(
            f["id"] for f in policy.families))
        for family in policy.families:
            lines.append(f"    {family['id']:<18} {family['pattern']}")
        return lines
    winner = matches[0]
    lines.append(f"  {name}: {winner[0]}" + (f" / {winner[1]}" if winner[1] else ""))
    for family in policy.families:
        hits = [m for m in matches if m[0] == family["id"]]
        mark = "MATCH " if hits else "      "
        role = f" (role {hits[0][1]})" if hits and hits[0][1] else ""
        lines.append(f"    {mark}{family['id']:<18} {family['pattern']}{role}")
    if len(matches) > 1:
        lines.append("    OVERLAP resolved by precedence: " + " > ".join(
            f"{m[0]}" + (f"/{m[1]}" if m[1] else "") for m in matches))
    return lines


def _names_from_project(policy: NamingPolicy, path: Path) -> tuple[list[str], list[str]]:
    """Return (names, findings) for a `project.yaml` manifest."""
    data = load_yaml(path)
    if not isinstance(data, dict):
        raise Refusal("manifest-unreadable", f"{path}: not a mapping")
    findings: list[str] = []
    names: list[str] = []
    for leg in data.get("legs") or []:
        if not isinstance(leg, dict) or "repository" not in leg:
            findings.append(f"{path}: a leg has no `repository:`")
            continue
        name = repo_basename(str(leg["repository"]))
        names.append(name)
        declared = leg.get("role")
        found = policy.classify(name)
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
    return names, findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("names", nargs="*", help="repository names to classify")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--project", type=Path, default=None,
                        help="read the leg names from a project.yaml manifest")
    parser.add_argument("--explain", action="store_true",
                        help="print every family each name satisfies")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    try:
        policy = NamingPolicy.load(args.policy)
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2

    names = [repo_basename(n) for n in args.names]
    findings: list[str] = []
    if args.project is not None:
        try:
            extra, findings = _names_from_project(policy, args.project)
        except Refusal as exc:
            print(str(exc), file=sys.stderr)
            return 2
        names.extend(extra)
    if not names and not sys.stdin.isatty():
        names = [repo_basename(line.strip()) for line in sys.stdin if line.strip()]
    if not names:
        print("REFUSED naming-no-target: no names given. Pass names, "
              "`--project project.yaml`, or names on stdin.", file=sys.stderr)
        return 2

    unclassified = []
    for name in names:
        found = policy.classify(name)
        if args.explain:
            print("\n".join(_describe(policy, name)))
        elif not args.quiet:
            label = "NO FAMILY" if not found else (
                found[0] + (f"/{found[1]}" if found[1] else ""))
            print(f"  {name:<32} {label}")
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
