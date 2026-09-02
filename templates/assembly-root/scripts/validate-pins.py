#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""THE LOCKSTEP VALIDATOR — three things move in one commit, or this refuses.

For every leg of this project, THREE facts name the same commit and they are
advanced TOGETHER, in ONE commit, or not at all:

    1. the GITLINK      — the `160000` entry this repository records for the
                          submodule at the leg's path
    2. the PIN FILE     — `commit:` in `contracts/<role>-pin.yaml`
    3. every WORKFLOW `@<sha>` REFERENCE naming that leg's repository, in
       `.github/workflows/*.yml`

This is not a hypothesis. In the xFactory aggregation the same invariant
(gitlink, `review-lane-reusable.yml@<sha>`, and a `PIN` constant in a test) was
practice for months and written down nowhere; seven consecutive pin-syncs from
2026-08-25 moved the gitlink alone and left the `validate` check red on every
pull request until 2026-08-26 — unnoticed for a day because `validate` runs on
pull requests only, so `main` never reported it and the breakage surfaced on
somebody else's change. Shipping the check in the template is what turns that
into a one-time scaffold cost instead of a per-project tribal rule.

The DIGEST is checked too: the pin records the sha256 of the leg's tree at the
pinned commit under the `sorted-ls-tree-r-v1` definition, recomputed here from
the submodule's own object store. A gitlink and a pin file that agree on a
commit whose bytes are not the bytes the pin was written against is drift the
commit comparison alone cannot see.

EXIT CODES
    0  every leg's three facts agree and every digest recomputes
    1  a FINDING: drift a reviewer can act on
    2  a REFUSAL: the question could not be asked — an uninitialized submodule,
       an unresolvable commit, an unreadable pin. An unanswerable pin question
       is never an implicit pass.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_shape import (  # noqa: E402
    COMMIT_RE, SHA256_RE, TREE_DIGEST_DEFINITION, Refusal, file_sha256,
    find_repo_root, git_out, load_yaml, recorded_gitlink, tree_digest,
)

#: `owner/repo[/path]@<40 hex>` as it appears in a `uses:` line.
WORKFLOW_REF_RE = re.compile(
    r"(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)(?P<path>/[^@\s'\"]*)?"
    r"@(?P<sha>[0-9a-fA-F]{40})"
)

LOCKSTEP = (
    "THE LOCKSTEP RULE: a leg's gitlink, its `contracts/<role>-pin.yaml` "
    "`commit:`, and EVERY `.github/workflows/*.yml` reference of the form "
    "`<org>/<leg>/...@<sha>` are ONE invariant. Move all three in ONE commit "
    "or the next pull request is red on somebody else's change."
)


class Report:
    def __init__(self) -> None:
        self.findings: list[str] = []
        self.notes: list[str] = []

    def finding(self, code: str, detail: str) -> None:
        self.findings.append(f"FINDING {code}: {detail}")

    def note(self, text: str) -> None:
        self.notes.append(f"  ok  {text}")


def _workflow_refs(root: Path) -> list[tuple[Path, str, str]]:
    """Every (file, owner/repo, sha) `@<sha>` reference in the workflows."""
    out: list[tuple[Path, str, str]] = []
    workflows = root / ".github" / "workflows"
    if not workflows.is_dir():
        return out
    for path in sorted(workflows.iterdir()):
        if path.suffix not in (".yml", ".yaml") or not path.is_file():
            continue
        for match in WORKFLOW_REF_RE.finditer(path.read_text(encoding="utf-8")):
            out.append((path, match.group("repo"), match.group("sha").lower()))
    return out


def _check_leg(root: Path, leg: dict, report: Report, refs) -> None:
    role = leg.get("role")
    path = str(leg.get("path") or "")
    repository = str(leg.get("repository") or "")
    pin_path = root / "contracts" / f"{role}-pin.yaml"
    if not pin_path.is_file():
        raise Refusal(
            "pin-missing",
            f"leg {role!r} declares {repository} at {path!r} but "
            f"{pin_path.relative_to(root)} does not exist",
        )
    pin = load_yaml(pin_path)
    if not isinstance(pin, dict):
        raise Refusal("pin-unreadable", f"{pin_path}: not a mapping")

    rel = pin_path.relative_to(root)
    if pin.get("kind") != "pinned_contract_manifest":
        report.finding("pin-wrong-kind",
                       f"{rel}: kind is {pin.get('kind')!r}, expected "
                       "'pinned_contract_manifest'")
    if pin.get("revision_kind") != "commit":
        report.finding(
            "pin-tag-only",
            f"{rel}: revision_kind is {pin.get('revision_kind')!r}. A tag can "
            "be moved and a commit cannot; a pin is a commit or it is nothing.",
        )
    commit = str(pin.get("commit") or "")
    if not COMMIT_RE.match(commit):
        raise Refusal(
            "pin-tag-only",
            f"{rel}: `commit:` is {commit!r}, which is not 40 hex. An "
            "abbreviated oid, a branch or a tag is a moving reference.",
        )
    commit = commit.lower()
    if pin.get("submodule_path") != path:
        report.finding("pin-path-mismatch",
                       f"{rel}: submodule_path is {pin.get('submodule_path')!r} "
                       f"but project.yaml puts the {role} leg at {path!r}")
    if pin.get("source_repository") != repository:
        report.finding("pin-repository-mismatch",
                       f"{rel}: source_repository is "
                       f"{pin.get('source_repository')!r} but project.yaml "
                       f"declares {repository!r}")

    # ---- fact 1 vs fact 2: the gitlink and the pin file --------------------
    gitlink = recorded_gitlink(root, path)
    if gitlink is None:
        raise Refusal(
            "pin-gitlink-absent",
            f"no gitlink (mode 160000) recorded at {path!r}. The {role} leg is "
            "declared in project.yaml but this repository does not record it "
            "as a submodule.",
        )
    if gitlink != commit:
        report.finding(
            "pin-gitlink-mismatch",
            f"{path}: gitlink {gitlink} != {rel} commit {commit}\n  " + LOCKSTEP,
        )
    else:
        report.note(f"{path}: gitlink == {rel} commit {commit[:12]}")

    # ---- the digest --------------------------------------------------------
    submodule = root / path
    if not (submodule / ".git").exists():
        raise Refusal(
            "pin-submodule-uninitialized",
            f"{path} is not an initialized submodule checkout, so the pinned "
            "digest cannot be recomputed. Presence is not identity and an "
            "unreadable surface must fail rather than degrade.",
        )
    try:
        git_out(["rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}"],
                cwd=submodule)
    except Refusal as exc:
        raise Refusal(
            "pin-commit-unresolvable",
            f"{path}: the pinned commit {commit} is not in that submodule's "
            f"object store ({exc.detail})",
        ) from exc
    recorded = (pin.get("digests") or {}).get("tree_sha256")
    if not isinstance(recorded, str) or not SHA256_RE.match(recorded):
        report.finding("pin-digest-malformed",
                       f"{rel}: digests.tree_sha256 is {recorded!r}, not 64 hex")
    elif pin.get("digest_definition") != TREE_DIGEST_DEFINITION:
        report.finding(
            "pin-digest-definition",
            f"{rel}: digest_definition is {pin.get('digest_definition')!r}, "
            f"expected {TREE_DIGEST_DEFINITION!r}. A digest whose definition is "
            "unstated is a number, not an identity.",
        )
    else:
        actual = tree_digest(submodule, commit)
        if actual.lower() != recorded.lower():
            report.finding(
                "pin-digest-mismatch",
                f"{rel}: digests.tree_sha256 {recorded}\n"
                f"       recomputed at {commit[:12]} {actual}\n"
                f"  The gitlink and the pin may agree on a commit whose bytes "
                f"are not the bytes the pin was written against.\n  " + LOCKSTEP,
            )
        else:
            report.note(f"{path}: tree digest recomputes ({recorded[:12]}…)")

    # ---- fact 3: every workflow reference naming this leg ------------------
    seen = 0
    for wf_path, wf_repo, wf_sha in refs:
        if wf_repo != repository:
            continue
        seen += 1
        if wf_sha != gitlink:
            report.finding(
                "pin-workflow-ref-mismatch",
                f"{wf_path.name}: `{wf_repo}@{wf_sha}` != the gitlink "
                f"{gitlink} recorded at {path!r}\n  " + LOCKSTEP,
            )
    if seen:
        report.note(f"{repository}: {seen} workflow @<sha> reference(s) "
                    f"agree with the gitlink")


def _check_shape_pin(root: Path, manifest: dict, report: Report) -> None:
    """The shape pin is a COPY pin, and it is checked as one.

    openRepoShape is not a submodule of a scaffolded project: the scaffold
    COPIES a small set of files out of it so the project is self-contained in
    an org that may never obtain the upstream. There is therefore no gitlink to
    compare — the identity of the copies is carried by the per-file `sha256`
    rows, exactly the half of `neutral-product-pin`'s shape that exists for
    artifacts a consumer holds rather than mounts.
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
                       f"{rel} commit {commit} != project.yaml shape.commit "
                       f"{declared}")
    before = len(report.findings)
    files = pin.get("files") or []
    if not files:
        report.finding("shape-pin-no-files",
                       f"{rel}: no `files:` rows, so nothing about the copied "
                       "shape files is actually asserted")
    for row in files:
        if not isinstance(row, dict):
            report.finding("shape-pin-row", f"{rel}: a files row is not a mapping")
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
                "carry the change upstream to openRepoShape and re-pin.",
            )
    if len(report.findings) == before:
        report.note(f"{rel}: {len(files)} copied shape file(s) match their digests")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None,
                        help="assembly root (default: the enclosing repository)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    report = Report()
    try:
        root = find_repo_root(args.root or Path(__file__).resolve().parents[1])
        manifest_path = root / "project.yaml"
        if not manifest_path.is_file():
            raise Refusal(
                "manifest-missing",
                f"{manifest_path} does not exist, so there is no declaration of "
                "which legs to check. A one-repository project has no legs and "
                "does not run this validator.",
            )
        manifest = load_yaml(manifest_path)
        if not isinstance(manifest, dict):
            raise Refusal("manifest-unreadable", f"{manifest_path}: not a mapping")
        legs = [leg for leg in (manifest.get("legs") or [])
                if isinstance(leg, dict) and leg.get("role") != "assembly"]
        if not legs:
            raise Refusal("manifest-no-legs",
                          f"{manifest_path}: no non-assembly legs declared")
        refs = _workflow_refs(root)
        for leg in legs:
            _check_leg(root, leg, report, refs)
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
        print(f"\n{len(report.findings)} finding(s). " + LOCKSTEP, file=sys.stderr)
        return 1
    print("pins ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
