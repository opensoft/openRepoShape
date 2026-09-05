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
    validate-repository-naming.py --pins openXdox \\
        --referent-chain openXdox,openDox --explain codexDox

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

`--role` IS ALSO WHAT ASKS WHETHER AN ELECTED FORM CARRIES ITS ROLE. Since
2026-09-05 a neutral product may ELECT the shape and be its own assembly root,
so `--explain --role assembly openDox` answers `neutral-product / assembly`
and names the admission, while `--explain openDox` — nothing declared — answers
`neutral-product` as it always did. The form is never overridden by the
declaration; the role is ADDED to it, and the leg form it also satisfies stays
in `also_matches`.

WHAT `--referent-chain` AND `--link-source` ARE FOR. Since 2026-09-05 the
referent may be reached through a CHAIN of neutral-product pins: `codexDox`
pins `openXdox`, and `openXdox` pins `openDox`. The chain is RECORDED, in the
descendant's own manifest under `naming.referent_chain:` (which `--project`
reads); `--referent-chain openXdox,openDox` supplies the same record for a
one-off check. Every link beyond the first is a declaration in ANOTHER tree,
and `--link-source [PRODUCT=]PATH` — like `SHAPE_PIN_SOURCE_<PRODUCT>` and a
checkout sitting beside the project — says where that tree is. A link no
source answers for is reported as `declared-unverified` and the name STILL
classifies as a descendant: the check is offline, and a recorded declaration
is the fact it reads.

EXIT CODES, the same three in every validator this standard ships:
    0  every name classified (and, with `--project`, every declared role and
       the topic agreed with the classification)
    1  a FINDING: at least one name matches no family, or a leg's declared role
       disagrees with the form of its name
    2  a REFUSAL: the question could not be asked at all — the policy file is
       missing, unparsable, or not a naming policy

A chain link whose tree could not be read prints a WARNING and changes no exit
code, deliberately: see `--link-source` below.

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
    CHAIN_RECORD_FIELD, NamingPolicy, Refusal, link_pins_from_trees, load_yaml,
    repo_basename,
)

DEFAULT_POLICY = Path(__file__).resolve().parents[1] / "contracts" / "repository-naming.yaml"


class Target:
    """One name to classify, with everything DECLARED about it.

    `chain` is the recorded `naming.referent_chain:` and `root` is the tree the
    chain's links are looked for beside, which is why a target is a small
    object rather than the tuple it used to be: a link is read from another
    repository's manifest, so the question "where am I standing?" is now part
    of the question being asked.
    """

    def __init__(self, name: str, role: str | None, pins: set[str],
                 chain=(), root: Path | None = None):
        self.name = name
        self.role = role
        self.pins = pins
        self.chain = tuple(chain)
        self.root = root


def _link_pins(target: Target, keyed_sources: dict,
               default_source: Path | None) -> dict:
    """What the chain's links declare, for the links whose trees answer."""
    if not target.chain:
        return {}
    return link_pins_from_trees(target.chain, target.root, keyed_sources,
                                default_source)


def _describe(policy: NamingPolicy, target: Target, link_pins: dict) -> list[str]:
    name, role, pins = target.name, target.role, target.pins
    lines = []
    matches = policy.matches(name, role)
    if not matches:
        lines.append(f"  {name}: NO FAMILY")
        lines.append(f"    the {len(policy.families)} families are: " + ", ".join(
            f["id"] for f in policy.families))
        for family in policy.families:
            lines.append(f"    {family['id']:<18} {family['pattern']}")
        return lines
    found = policy.classify(name, role, pins, target.chain, link_pins)
    lines.append(f"  {name}: {found[0]}" + (f" / {found[1]}" if found[1] else ""))
    for family in policy.families:
        hits = [m for m in matches if m[0] == family["id"]]
        mark = "MATCH " if hits else "      "
        role_note = f" (role {hits[0][1]})" if hits and hits[0][1] else ""
        claim = ""
        if hits and policy.requires_referent(family["id"]):
            # WHAT WOULD BE ACCEPTED, both halves of it. Naming only the direct
            # pin is what sent `codexDox` looking for an `openDox` pin its
            # family does not hold (2026-09-05).
            claim = (" [a CLAIM: needs a declared pin on " + " or ".join(
                policy.descendant_referents(name))
                + ", or a declared chain (`"
                + str(policy.chain_rule().get("record_field")
                      or CHAIN_RECORD_FIELD)
                + "`) of pins ending in one of them]")
        elif policy.declared_only(family["id"]):
            claim = (" [DECLARED-ONLY: reported only with --role "
                     + family["id"] + "; " + str(family.get("declared_by") or
                                                 "a declaration").strip() + "]")
        elif hits and family.get("admits_declared_role"):
            # NAME THE ADMISSION, not just its effect. A reader who sees
            # `openDox: neutral-product / assembly` and no explanation has to
            # go and read the classifier to learn that the form still won and
            # the role was ADDED to it (2026-09-05).
            admits = ", ".join(str(r) for r in family["admits_declared_role"])
            carried = (found.role if found.family == family["id"]
                       and found.role else None)
            # THREE ANSWERS, not two: nothing declared, a role declared and
            # ADMITTED, or a role declared and REFUSED (`--role spec openDox`
            # declares a role this family does not admit). Collapsing the
            # last two into "none is declared here" told the reader a
            # declaration was absent when it was in fact refused (2026-09-05).
            if role is None:
                admission = "; none is declared here"
            elif carried:
                admission = f" — this name carries {carried}"
            else:
                admission = f"; {role} is declared here and is not admitted"
            claim = (f" [ADMITS a declared role of {admits}: the form still "
                     "wins and carries the role the project declares, where "
                     "the name also satisfies that leg form"
                     + admission
                     + "]")
            if carried:
                role_note = f" (role {carried}, ADMITTED)"
        lines.append(
            f"    {mark}{family['id']:<18} {family['pattern']}{role_note}{claim}")
    if target.chain:
        lines.append("    CHAIN " + " → ".join(target.chain)
                     + f"   [{found.referent.status}]")
    for warning in found.referent.warnings:
        lines.append("    WARNING " + warning)
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


def _chain_from_leg(leg: dict) -> tuple:
    """The pin chain a leg's `naming:` block RECORDS, if it records one.

    Read from the manifest and nowhere else: the chain is a declaration, and
    inferring one from the pins would be the classifier writing the record it
    then checks.
    """
    naming = leg.get("naming")
    if not isinstance(naming, dict):
        return ()
    recorded = naming.get(CHAIN_RECORD_FIELD)
    if isinstance(recorded, str):
        recorded = [recorded]
    return tuple(str(link) for link in (recorded or []) if str(link).strip())


def _targets_from_project(policy: NamingPolicy, path: Path,
                          keyed_sources: dict,
                          default_source: Path | None) -> tuple[list, list[str]]:
    """Return ([Target], findings) for a `project.yaml` manifest."""
    data = load_yaml(path)
    if not isinstance(data, dict):
        raise Refusal("manifest-unreadable", f"{path}: not a mapping")
    findings: list[str] = []
    pins = _pins_from_project(data)
    root = path.resolve().parent
    targets: list[Target] = []
    for leg in data.get("legs") or []:
        if not isinstance(leg, dict) or "repository" not in leg:
            findings.append(f"{path}: a leg has no `repository:`")
            continue
        name = repo_basename(str(leg["repository"]))
        declared = leg.get("role")
        declared = str(declared) if declared else None
        target = Target(name, declared, pins, _chain_from_leg(leg), root)
        targets.append(target)
        found = policy.classify(name, declared, pins, target.chain,
                                _link_pins(target, keyed_sources,
                                           default_source))
        # `declared_role` only wins where the NAME satisfies it, so a role that
        # disagrees with its own name still lands here rather than being made
        # true by declaring it.
        if found and found[0] == "project-leg" and declared and found[1] != declared:
            findings.append(
                f"{name}: declared role {declared!r} but the name is the "
                f"{found[1]!r} form of the project-leg family"
            )
        # A RECORDED chain that does not hold is drift in the record, and the
        # finding names the link. Unverified is not this: it is a warning,
        # printed by the caller, and never an exit code.
        if found and found.referent.status == "broken":
            findings.append(f"{name}: {found.referent.reason}")
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
                        choices=("assembly", "spec", "code", "family"),
                        help="the role the NAMES on the command line are "
                             "offered as; a descendant-form name with no "
                             "referent pin is classified by this, and "
                             "`family` is what asks whether a name is a valid "
                             "HOLDER — a form spelled exactly like an assembly "
                             "root, so it is reported only when declared")
    parser.add_argument("--pins", default="",
                        help="comma-separated neutral products the project "
                             "declares a pin on, e.g. --pins openChart. A "
                             "`<Domainx><Product>` name is a domain descendant "
                             "only when its `open<Product>` is in this list.")
    parser.add_argument("--referent-chain", default="",
                        help="the pin chain the project RECORDS as reaching "
                             "its referent, e.g. --referent-chain "
                             "openXdox,openDox. The first entry must be in "
                             "--pins and the last must be the name's "
                             "`open<Product>`; with --project it is read from "
                             "each leg's `naming.referent_chain:` instead.")
    parser.add_argument("--link-source", action="append", default=[],
                        metavar="[PRODUCT=]PATH",
                        help="where a chain LINK's own tree is, so its "
                             "`neutral_product_pins:` can be read and the "
                             "link VERIFIED — e.g. --link-source "
                             "openXdox=../openXdox. A bare PATH applies to "
                             "whichever link has no more specific answer. "
                             "SHAPE_PIN_SOURCE_<PRODUCT> and a checkout "
                             "beside the project are tried too. A link no "
                             "source answers for is declared-unverified, "
                             "which is a warning and not a finding.")
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

    keyed_sources: dict[str, Path] = {}
    default_source: Path | None = None
    for raw in args.link_source:
        product, sep, path = raw.partition("=")
        if sep:
            keyed_sources[product.casefold()] = Path(path)
        else:
            default_source = Path(raw)

    cli_pins = {p.strip() for p in args.pins.split(",") if p.strip()}
    cli_chain = tuple(c.strip() for c in args.referent_chain.split(",")
                      if c.strip())
    here = Path.cwd()
    targets: list[Target] = [
        Target(repo_basename(n), args.role, cli_pins, cli_chain, here)
        for n in args.names]
    findings: list[str] = []
    if args.project is not None:
        try:
            extra, findings = _targets_from_project(
                policy, args.project, keyed_sources, default_source)
        except Refusal as exc:
            print(str(exc), file=sys.stderr)
            return 2
        targets.extend(extra)
    if not targets and not sys.stdin.isatty():
        targets = [Target(repo_basename(line.strip()), args.role, cli_pins,
                          cli_chain, here)
                   for line in sys.stdin if line.strip()]
    if not targets:
        print("REFUSED naming-no-target: no names given. Pass names, "
              "`--project project.yaml`, or names on stdin.", file=sys.stderr)
        return 2

    unclassified = []
    warnings: list[str] = []
    for target in targets:
        name = target.name
        link_pins = _link_pins(target, keyed_sources, default_source)
        found = policy.classify(name, target.role, target.pins, target.chain,
                                link_pins)
        if args.explain:
            print("\n".join(_describe(policy, target, link_pins)))
        elif not args.quiet:
            label = "NO FAMILY" if not found else (
                found[0] + (f"/{found[1]}" if found[1] else ""))
            also = f"   also_matches {','.join(found.also_matches)}" \
                if found and found.also_matches else ""
            print(f"  {name:<32} {label}{also}")
        if found:
            warnings.extend(f"{name}: {text}"
                            for text in found.referent.warnings)
        if not found:
            unclassified.append(name)

    # A WARNING IS NOT A FINDING. An unread link tree is the ordinary case in
    # a fork-and-run checkout, and an exit code that punished it would make the
    # answer depend on which repositories happen to be on the disk.
    for warning in warnings:
        if not args.quiet and not args.explain:
            print(f"WARNING {warning}", file=sys.stderr)
    for finding in findings:
        print(f"FINDING {finding}", file=sys.stderr)
    if unclassified:
        print(
            "FINDING naming-unclassified: "
            + ", ".join(unclassified)
            + "\n  These names match none of the families in "
            + str(args.policy)
            + ".\n  A project's three repositories are `<Project>`, "
            "`<Project>-spec` and `<Project>-code`; `<Project>` is one "
            "CamelCase token with no hyphen, underscore, dot or space.",
            file=sys.stderr,
        )
    return 1 if (unclassified or findings) else 0


if __name__ == "__main__":
    sys.exit(main())
