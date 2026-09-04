#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Adopt an EXISTING repository into the three-repository shape, IN PLACE.

    ./adopt-project.py plan    --source <path|org/repo> --project <Project>
    ./adopt-project.py check   --plan adoption-plan.yaml
    ./adopt-project.py execute --plan adoption-plan.yaml [--yes]

IN PLACE IS THE WHOLE POSTURE, and it is a ruling (Brett Heap, 2026-09-02):
the repository being adopted KEEPS ITS NAME, ITS IDENTITY AND ITS FULL
HISTORY and becomes the assembly root. `<Project>-spec` and `<Project>-code`
are NEW repositories, extracted with history-preserving filters. The source is
never deleted, never renamed, and never force-pushed: the only change to it is
ONE split commit, which arrives on a BRANCH and by pull request, because the
organisations this is built for apply PR-only rulesets and a tool that needed
a bypass would be a tool that cannot be used where it is needed.

THREE SUBCOMMANDS, BECAUSE THE MIDDLE ONE IS A HUMAN.

  plan     walks the source at its default branch, classifies every top-level
           path against `contracts/path-classification.yaml`, and writes
           `adoption-plan.yaml`. Paths it cannot honestly call carry
           `leg: null`, `review_required: true` and the QUESTION to ask.
  check    validates a plan against the source: every path covered exactly
           once, no unresolved legs, leg names conforming to the naming
           policy. It prints what will happen and changes nothing.
  execute  creates the two legs, extracts them with `git filter-repo`, makes
           the one split commit on a branch of the source, sets the
           `xf-project-<id>` topic on all three (skipped for local remotes),
           and then VERIFIES by blob sha that every source path landed in
           exactly one place.

THE PLAN IS AN ARTIFACT A HUMAN OR AN AI EDITS. That is why it is YAML with
reasons in it rather than a pipe between two processes: the classifier is
right about `openspec/` and cannot be right about `examples/golden-run/`
without knowing whether the specification cites it. `execute` REFUSES while
any `leg:` is still null.

WHY `git filter-repo` AND NOT A VENDORED COPY. Extracting history correctly is
a solved problem with one correct implementation, and a vendored copy of it
would be a second implementation that drifts. It is a hard REQUIREMENT here,
preflighted with an exact install hint; the alternative — `git subtree` or a
hand-rolled `filter-branch` — is slower, rewrites author dates, and is exactly
the kind of thing that is discovered to have been wrong a year later.

A LEG WITH NOTHING IN IT IS SEEDED, NOT EXTRACTED. A repository can honestly
have no code yet — InkRouter's IRRS and IRSS are specifications (Brett Heap,
2026-09-04) — and `git filter-repo` over an empty path list yields an empty
HISTORY rather than an empty repository. So a leg no entry assigns a path to
is seeded from `templates/<role>-root/` as one initial commit, the plan
records `seeded_from_template: true` for it, the split still mounts and pins
it, and the verification table reads `code: 0 of N source paths (seeded from
template)`. `check` WARNS; `execute` refuses without `--allow-empty-leg
<leg>`, in the plan or on its command line, because a plan that lost its code
paths to a bad edit looks identical from here.

MODE. `in-place` is the only mode in v0.2. A future `new-root` mode would
create a NEW assembly root and reduce the source to one leg; it is recorded in
the plan's `mode:` field so a plan written today says which posture it took,
rather than being reinterpreted later by a tool that grew a second one.

EXIT CODES: 0 done · 1 findings (a plan that does not check out; a
verification mismatch) · 2 a refusal — the question could not be asked.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SHAPE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SHAPE_ROOT / "scripts"))
from path_classify import PathPolicy, Verdict  # noqa: E402
from repo_shape import (  # noqa: E402
    free_plan_secret_hint,
    COMMIT_RE, NEUTRAL_PRODUCT_OWNER, PROJECT_ID_RE, TREE_DIGEST_DEFINITION,
    VISIBILITY_CHOICES, NamingPolicy, Refusal, accepts_role, checked_value,
    git_out, load_yaml, tree_digest,
)
from shape_materialize import (  # noqa: E402
    ADOPT_MAKEFILE_BLOCK, RULESET_HINT, SHAPE_REPOSITORY,
    CommandFailed, copy_tree, default_reference, election_date, env_commit,
    git_init_commit, materialize_assembly_root, naming_block, run,
)

#: The naming policy this tool classifies leg names against. One constant,
#: because three spellings of the same path is how the second one goes stale.
NAMING_POLICY = SHAPE_ROOT / "contracts" / "repository-naming.yaml"
PATH_POLICY = SHAPE_ROOT / "contracts" / "path-classification.yaml"

#: A declared pin here is a NAME, `[owner/]openProduct` — never `@<commit>`.
#: Adopting a project records no commit for a neutral-product pin at plan
#: time (there is no `contracts/<product>-pin.yaml` for one, unlike
#: `scaffold-project.py --pin`), so a value carrying `@` is almost always
#: that OTHER tool's syntax pasted in by habit, and is refused rather than
#: silently written into `neutral_product_pins:` as a name nothing matches.
PIN_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?$")


def _checked_pin_name(raw: str) -> str:
    name = raw.strip()
    if not PIN_NAME_RE.match(name):
        raise Refusal(
            "adopt-pin-malformed",
            f"--pin {raw!r} is not `[owner/]openProduct`",
            "Remediation: pass --pin openGlass, or name the owner explicitly "
            f"with --pin {NEUTRAL_PRODUCT_OWNER}/openGlass — every neutral "
            f"open<Product> lives under {NEUTRAL_PRODUCT_OWNER} by the "
            "family's rule. Adopting a project declares no commit for a "
            "neutral-product pin at plan time, so drop `@<commit>` if you "
            "copied it from `scaffold-project.py --pin`.",
        )
    return name


PLAN_KIND = "adoption-plan"
ADOPT_BRANCH = "adopt/three-repo-shape"
COLLISION_DIR = "shape"
LEG_VALUES = ("spec", "code", "root", "drop")
FILE_PROTOCOL = ["-c", "protocol.file.allow=always"]

#: THE SPEC-ONLY CASE. A repository can honestly have nothing for one leg —
#: InkRouter's IRRS and IRSS are specifications with no implementation yet
#: (Brett Heap, 2026-09-04: "We do not have any code yet for either service").
#: A leg that no plan entry assigns a path to CANNOT be extracted: `git
#: filter-repo` over an empty path list rewrites every commit to nothing and
#: leaves an empty history, which is not the same thing as an empty
#: repository and is not something to push at a project. Such a leg is SEEDED
#: from the shape's own leg template as ONE initial commit — the same bytes
#: `scaffold-project.py` would have written for a new project — and the split
#: commit mounts it exactly like an extracted one. It carries no history from
#: the adopted repository because there was none to carry, and the
#: verification table says so rather than reporting a hole.
SEED_TEMPLATE = {"spec": "templates/spec-root", "code": "templates/code-root"}
EXTRACTED_LEGS = ("spec", "code")

FILTER_REPO_HINT = (
    "Remediation: install it — `pip install git-filter-repo`, or "
    "`apt install git-filter-repo`, or `brew install git-filter-repo`; it is "
    "one file on PATH named `git-filter-repo`. It is NOT vendored here on "
    "purpose: history extraction has one correct implementation and a copy of "
    "it is a second one that drifts."
)


# ---------------------------------------------------------------------------
# A very small YAML writer, for the one document this tool emits
# ---------------------------------------------------------------------------
#
# `repo_shape.parse_yaml` reads a SUBSET, so this writes the same subset: block
# mappings, block sequences and single-line scalars. Everything it emits is
# read back by `check`, and `tests/test_adopt_plan.py` round-trips a plan
# through both, which is what keeps the writer and the reader honest about
# each other.

_PLAIN_RE = re.compile(r"^[A-Za-z_.][A-Za-z0-9_./@:+-]*$")


def y(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.4f}"
    text = str(value)
    if text and _PLAIN_RE.match(text) and not text.endswith(":"):
        return text
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def emit(lines: list[str], key: str, value, indent: int = 0) -> None:
    lines.append(f"{' ' * indent}{key}: {y(value)}")


# ---------------------------------------------------------------------------
# The source repository, read ONLY
# ---------------------------------------------------------------------------


class Source:
    """A repository being read, and nothing more. Nothing here writes to it."""

    def __init__(self, path: Path, repository: str | None, branch: str,
                 commit: str):
        self.path = path
        self.repository = repository
        self.branch = branch
        self.commit = commit

    @classmethod
    def open(cls, spec: str, work_root: Path) -> "Source":
        """`spec` is a local path (used in place) or `org/repo` (cloned)."""
        candidate = Path(spec).expanduser()
        if candidate.exists():
            path = candidate.resolve()
            repository = _remote_repository(path)
        else:
            if "/" not in spec:
                raise Refusal(
                    "source-unresolvable",
                    f"--source {spec!r} is neither a path that exists nor an "
                    "`org/repo` name",
                    "Remediation: pass a local clone's path, or `org/repo`.")
            repository = spec
            path = work_root / "source-readonly" / spec.split("/")[-1]
            path.parent.mkdir(parents=True, exist_ok=True)
            print(f"cloning {spec} (read only) into {path}")
            try:
                run(["gh", "repo", "clone", spec, str(path), "--", "--quiet"])
            except CommandFailed as exc:
                raise Refusal(
                    "source-unclonable",
                    f"could not clone {spec}: {exc.output.strip()[:400]}",
                    "Remediation: check `gh auth status` and the repository "
                    "name, or clone it yourself and pass the path.") from exc
        branch = _default_branch(path)
        commit = git_out(["rev-parse", branch], cwd=path).lower()
        return cls(path, repository, branch, commit)

    def tree(self) -> list[tuple[str, str, str, int]]:
        """(path, mode, blob sha, size) for every file at the pinned commit."""
        raw = git_out(["ls-tree", "-r", "-l", "-z", self.commit],
                      cwd=self.path, binary=True)
        out = []
        for record in raw.split(b"\x00"):
            if not record:
                continue
            head, _, path = record.partition(b"\t")
            mode, kind, oid, size = head.decode().split(maxsplit=3)
            out.append((path.decode("utf-8", "surrogateescape"), mode, oid,
                        0 if size.strip() == "-" else int(size)))
            del kind
        return sorted(out)

    def commit_count(self) -> int:
        return int(git_out(["rev-list", "--count", self.commit], cwd=self.path))


def _remote_repository(path: Path) -> str | None:
    try:
        url = git_out(["remote", "get-url", "origin"], cwd=path)
    except Refusal:
        return None
    match = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$", url)
    return match.group(1) if match else None


def _default_branch(path: Path) -> str:
    """The branch the adoption reads, in the order a reader would guess it."""
    for args in (["symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
                 ["symbolic-ref", "--short", "HEAD"]):
        try:
            name = git_out(args, cwd=path)
        except Refusal:
            continue
        if name:
            return name.split("/", 1)[1] if name.startswith("origin/") else name
    return "main"


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------


class Entry:
    """One row of the plan: a path, the leg proposed for it, and why."""

    def __init__(self, path: str, verdict: Verdict, files: int, size: int):
        self.path = path
        self.leg = verdict.leg
        self.rule = verdict.rule
        self.reason = verdict.reason
        self.confidence = verdict.confidence
        self.question = verdict.question
        self.files = files
        self.bytes = size

    def write(self, lines: list[str]) -> None:
        lines.append(f"  - path: {y(self.path)}")
        emit(lines, "leg", self.leg, 4)
        emit(lines, "confidence", self.confidence, 4)
        emit(lines, "rule", self.rule, 4)
        emit(lines, "reason", self.reason, 4)
        emit(lines, "files", self.files, 4)
        emit(lines, "bytes", self.bytes, 4)
        emit(lines, "review_required", self.leg is None, 4)
        if self.question:
            emit(lines, "question", self.question, 4)


def walk(policy: PathPolicy, files: list[tuple[str, int]],
         prefix: str = "") -> list[Entry]:
    """Classify a level of the tree, descending ONLY where children disagree.

    `files` are `(path relative to prefix, size)`; `prefix` is what to put back
    in front when an entry is written. One entry per top-level name is the
    goal: a reader has to read this, and 167 rows for 167 files would bury the
    four decisions that actually need a human.
    """
    here = [(p, s) for p, s in files if "/" not in p]
    groups: dict[str, list[tuple[str, int]]] = {}
    for path, size in files:
        if "/" in path:
            head, _, rest = path.partition("/")
            groups.setdefault(head, []).append((rest, size))

    entries: list[Entry] = []
    for path, size in sorted(here):
        full = prefix + path
        entries.append(Entry(full, policy.classify_file(full), 1, size))
    for name, children in sorted(groups.items()):
        directory = f"{prefix}{name}/"
        verdicts = [policy.classify_file(directory + child)
                    for child, _ in children]
        folded = policy.fold(verdicts, [c for c, _ in children])
        if folded is not None:
            entries.append(Entry(directory, folded, len(children),
                                 sum(s for _, s in children)))
        else:
            entries.extend(walk(policy, children, directory))
    return sorted(entries, key=lambda e: e.path)


def cross_leg_references(source: "Source", entries: list["Entry"],
                        spec_path: str, code_path: str) -> list[str]:
    """Files that will move to the CODE leg and name a path in the SPEC leg.

    Found by asking git, not by guessing: `git grep -l` over the source commit,
    restricted to the paths the plan sends to the code leg, for the name of
    each directory the plan sends to the spec leg. That is how a follow-up ends
    up saying `scripts/validate.py` instead of "something may read contracts".

    This is the 2026-09-02 ruling made operational: `contracts/*.yaml` go to
    the spec leg, and the code that reads them reads ACROSS the assembly root
    mount. The read is one relative path from the code leg — but only once
    somebody edits it, so the plan says which file and the human decides when.
    """
    code_paths = [e.path.rstrip("/") for e in entries if e.leg == "code"]
    spec_dirs = [e.path for e in entries
                 if e.leg == "spec" and e.path.endswith("/")]
    if not code_paths or not spec_dirs:
        return []
    out: list[str] = []
    for spec_dir in spec_dirs:
        proc = subprocess.run(
            ["git", "grep", "-l", "-I", "-F", spec_dir, source.commit, "--",
             *code_paths],
            cwd=str(source.path), capture_output=True, text=True, check=False)
        hits = [line.split(":", 1)[1] for line in proc.stdout.splitlines()
                if ":" in line]
        # Fixtures last. A test fixture that mentions `contracts/` is usually
        # quoting a path rather than reading one, and burying the harness that
        # DOES read it under twenty of them is how a follow-up list stops
        # being read at all.
        hits.sort(key=lambda h: ("fixture" in h or h.startswith("tests/"), h))
        for hit in hits[:8]:
            out.append(
                f"{code_path}/{hit} names `{spec_dir}`, which moves to the "
                f"spec leg: it must read across the assembly root — "
                f"`../{spec_path}/{spec_dir}` relative to `{code_path}/` — or "
                "take the path from the environment")
        if len(hits) > 8:
            out.append(f"… and {len(hits) - 8} more file(s) under the code leg "
                       f"naming `{spec_dir}`")
    return out


def follow_ups_for(source: "Source", entries: list["Entry"], names: dict,
                   spec_path: str, code_path: str,
                   collisions: list[str]) -> list[str]:
    """The code changes an in-place split MAKES NECESSARY, named in the plan.

    A split that moved `contracts/` into the spec leg and said nothing about
    the harness that reads it would have handed somebody a red build and no
    explanation.
    """
    out = cross_leg_references(source, entries, spec_path, code_path)
    if any(e.leg == "spec" and (e.path == "contracts/"
                                or e.path.startswith("contracts/"))
           for e in entries):
        out.append(
            f"the root Makefile wires `CONTRACTS_DIR ?= $(CURDIR)/{spec_path}/"
            "contracts` and exports it, so the code leg's tooling takes the "
            "path from the environment instead of assuming it sits beside it")
    if any(e.path in ("CODEOWNERS", ".github/CODEOWNERS") for e in entries):
        out.append(
            "CODEOWNERS in the assembly root now names paths that live in the "
            "legs; re-scope it here and add one to each leg, since a code "
            "owner rule cannot cross a repository boundary")
    out.extend(collisions)
    out.append(
        "open the split as a pull request against the source's default "
        f"branch; the legs {names['spec']} and {names['code']} are seeded "
        "before it, so review the root's diff and the two new repositories "
        "together")
    return out


def summary_of(entries: list[Entry]) -> dict[str, dict[str, float]]:
    total_files = sum(e.files for e in entries) or 1
    total_bytes = sum(e.bytes for e in entries) or 1
    out: dict[str, dict[str, float]] = {}
    for leg in ("spec", "code", "root", "drop", "unresolved"):
        rows = [e for e in entries
                if (e.leg or "unresolved") == leg]
        if not rows and leg in ("drop",):
            continue
        files = sum(e.files for e in rows)
        size = sum(e.bytes for e in rows)
        out[leg] = {
            "files": files, "bytes": size,
            "file_share": round(files / total_files, 4),
            "byte_share": round(size / total_bytes, 4),
        }
    return out


def seeded_legs(assigned: dict) -> list[str]:
    """The legs no path is assigned to, in the order the tool reports them.

    ONE DEFINITION, consulted by `plan`, `check` and `execute`, because three
    answers to "is this leg empty?" is how the plan starts describing a split
    the tool does not perform. `assigned` maps a leg to the paths the entries
    give it; a leg with none is seeded.
    """
    return [role for role in EXTRACTED_LEGS if not assigned.get(role)]


def assigned_paths(entries) -> dict[str, list[str]]:
    """`{leg: [path, ...]}` from plan `Entry` objects OR from loaded rows."""
    out: dict[str, list[str]] = {leg: [] for leg in LEG_VALUES}
    for entry in entries:
        if isinstance(entry, dict):
            leg, path = entry.get("leg"), entry.get("path")
        else:
            leg, path = entry.leg, entry.path
        if leg is not None and str(leg) in out:
            out[str(leg)].append(str(path))
    return out


def render_plan(args, source: Source, entries: list[Entry], names: dict,
                pins: list[str], follow_ups: list[str]) -> str:
    lines = [
        "schema_version: 1",
        f"kind: {PLAN_KIND}",
        "",
        "# Written by `adopt-project.py plan`. IT IS MEANT TO BE EDITED.",
        "# Every entry with `review_required: true` carries a `question:`; a",
        "# human or an AI answers it by setting `leg:` to spec, code, root or",
        "# drop and adding one line of `resolution:` beside it. `check` then",
        "# has to pass, and `execute` REFUSES while any leg is still null.",
        "",
        f"generated_on: {_dt.date.today().isoformat()}",
        f"tool: {SHAPE_REPOSITORY} adopt-project.py",
        "",
        "source:",
    ]
    emit(lines, "repository", source.repository, 2)
    emit(lines, "local_path", str(source.path), 2)
    emit(lines, "default_branch", source.branch, 2)
    emit(lines, "commit", source.commit, 2)
    emit(lines, "files", sum(e.files for e in entries), 2)
    emit(lines, "bytes", sum(e.bytes for e in entries), 2)
    emit(lines, "commits", source.commit_count(), 2)
    lines += ["", "# The adopted repository KEEPS its name, its identity and",
              "# its history and becomes the assembly root. `new-root` — a new",
              "# root with the source reduced to one leg — is not implemented",
              "# in v0.2; the field records which posture this plan took.",
              "mode: in-place", ""]
    emit(lines, "project", args.project)
    emit(lines, "org", args.org)
    emit(lines, "id", args.id)
    emit(lines, "visibility", args.visibility)
    emit(lines, "tracking_branch", args.tracking_branch)
    emit(lines, "adopt_branch", ADOPT_BRANCH)
    emit(lines, "elected_by", args.elected_by)
    emit(lines, "elected_on", args.elected_on)
    emit(lines, "reference", args.reference)
    lines.append("")
    lines.append("legs:")
    emit(lines, "assembly", names["assembly"], 2)
    emit(lines, "spec", names["spec"], 2)
    emit(lines, "code", names["code"], 2)
    emit(lines, "spec_path", args.spec_path, 2)
    emit(lines, "code_path", args.code_path, 2)
    lines += ["",
              "# Neutral products this project declares a pin on. A",
              "# `<Domainx><Product>` assembly root is a DESCENDANT only when",
              "# its `open<Product>` is listed here (2026-09-02).",
              "pins: [" + ", ".join(pins) + "]", ""]

    seeded = seeded_legs(assigned_paths(entries))
    lines += [
        "# A leg that NO entry below assigns a path to is SEEDED from the",
        "# shape's own leg template as one initial commit, instead of being",
        "# extracted: `git filter-repo` over an empty path list yields an",
        "# empty HISTORY, which is not an empty repository. The split still",
        "# mounts it. This block RECORDS what the entries said when the plan",
        "# was written; `check` and `execute` re-derive it from the entries,",
        "# which are edited afterwards, and the entries always win.",
        "seeding:",
    ]
    for role in EXTRACTED_LEGS:
        lines.append(f"  {role}:")
        emit(lines, "seeded_from_template", role in seeded, 4)
        if role in seeded:
            emit(lines, "template", SEED_TEMPLATE[role], 4)
            emit(lines, "reason",
                 f"no entry assigns a path to the {role} leg", 4)
    lines += [
        "",
        "# Seeding a leg is EXPLICIT HUMAN INTENT, so `execute` refuses to do",
        "# it unless the leg is named here (or on its own command line) with",
        "# `--allow-empty-leg <leg>`. A repository that turns out to have no",
        "# code is a fact worth confirming; a plan that lost every code path",
        "# to a bad edit looks exactly the same from here.",
        "allow_empty_legs: ["
        + ", ".join(sorted(getattr(args, "allow_empty_leg", None) or []))
        + "]",
        "", "paths:"]
    for entry in entries:
        entry.write(lines)
    lines += ["", "follow_ups:"]
    for item in follow_ups:
        lines.append(f"  - {y(item)}")
    lines += ["", "summary:"]
    for leg, row in summary_of(entries).items():
        lines.append(f"  {leg}:")
        for key, value in row.items():
            emit(lines, key, value, 4)
    return "\n".join(lines) + "\n"


def cmd_plan(args) -> int:
    work_root = _work_root(args)
    source = Source.open(args.source, work_root)
    policy = PathPolicy.load(args.path_policy or PATH_POLICY)
    naming = NamingPolicy.load(NAMING_POLICY)

    args.project = checked_value("--project", args.project)
    args.tracking_branch = checked_value("--tracking-branch",
                                         args.tracking_branch)
    args.spec_path = checked_value("--spec-path", args.spec_path)
    args.code_path = checked_value("--code-path", args.code_path)
    args.id = args.id or args.project.lower()
    if not PROJECT_ID_RE.match(args.id):
        raise Refusal("adopt-bad-id",
                      f"--id {args.id!r} must match {PROJECT_ID_RE.pattern}",
                      "Remediation: pass an explicit lowercase --id.")
    args.org = checked_value(
        "--org", args.org or (source.repository or "/").split("/")[0] or "-")
    if not args.org:
        raise Refusal(
            "adopt-no-org", "the source has no `origin` to read an "
            "organisation from", "Remediation: pass --org <org>.")
    args.elected_on = args.elected_on or _dt.date.today().isoformat()
    # Read before the plan is written, whether or not it is what chooses the
    # reference: a date the tools cannot parse would reach `execute` as a
    # manifest field instead of as a question.
    election_date(args.elected_on)
    args.reference = args.reference or default_reference(args.elected_on)
    args.elected_by = args.elected_by or _elector()
    names = _names(args.project)
    pins = [_checked_pin_name(p) for p in (args.pin or []) if p.strip()]
    _check_names(naming, names, set(pins))

    tree = source.tree()
    entries = walk(policy, [(path, size) for path, _, _, size in tree])
    materialized = _predict_collisions(entries)
    follow_ups = follow_ups_for(source, entries, names, args.spec_path,
                                args.code_path, materialized)
    out = Path(args.out)
    out.write_text(render_plan(args, source, entries, names, pins, follow_ups),
                   encoding="utf-8")

    print(f"source     {source.repository or source.path} @ "
          f"{source.commit[:12]} ({source.branch}), "
          f"{len(tree)} files, {source.commit_count()} commits")
    print(f"project    {args.project} ({args.id}) in {args.org}, mode in-place")
    _print_entries(entries)
    _print_summary(entries)
    print(f"\nfollow-ups ({len(follow_ups)}):")
    for item in follow_ups:
        print(f"  - {item}")
    for line in seeding_warnings(seeded_legs(assigned_paths(entries)),
                                 set(args.allow_empty_leg or [])):
        print(line)
    unresolved = [e for e in entries if e.leg is None]
    print(f"\nplan written to {out}")
    if unresolved:
        print(f"{len(unresolved)} path(s) need a human or an AI to answer a "
              "question before `execute` will run:")
        for entry in unresolved:
            print(f"  {entry.path}\n      {entry.question}")
    return 0


def seeding_warnings(seeded: list[str], allowed: set) -> list[str]:
    """What `plan` and `check` say about a leg that will be seeded.

    A WARNING AND NOT A FINDING. A repository with no implementation yet is a
    legitimate thing to adopt — the InkRouter services are specifications with
    no code (2026-09-04) — so `check` must be able to pass on one. What it
    must never do is let the seeding happen unremarked: the same empty leg is
    also what a plan looks like after somebody deletes the entries that fed
    it, and only a human can tell those two apart. Hence the consent flag,
    named here rather than discovered when `execute` refuses.
    """
    out: list[str] = []
    for role in seeded:
        out.append(
            f"\nWARNING the {role} leg will be SEEDED from "
            f"{SEED_TEMPLATE[role]}/, not extracted:\n"
            f"        no entry assigns a path to it, and `git filter-repo` "
            f"over an empty\n        path list yields an empty history rather "
            f"than an empty repository.\n        The leg is created, mounted "
            f"and pinned like any other; it simply\n        carries no history "
            f"from the adopted repository, because there is none.")
        if role not in allowed:
            out.append(
                f"        `execute` REFUSES until a human says so: re-run "
                f"`plan` with\n        --allow-empty-leg {role}, or pass it to "
                f"`execute` itself.")
        else:
            out.append(f"        --allow-empty-leg {role} is declared, so "
                       "`execute` will proceed.")
    return out


def _print_entries(entries: list[Entry]) -> None:
    print(f"\n{'path':<34} {'leg':<10} {'conf':<7} {'files':>6} {'rule'}")
    for entry in entries:
        print(f"{entry.path:<34} {(entry.leg or 'REVIEW'):<10} "
              f"{entry.confidence:<7} {entry.files:>6} {entry.rule}")


def _print_summary(entries: list[Entry]) -> None:
    print()
    for leg, row in summary_of(entries).items():
        print(f"{leg:<10} {int(row['files']):>4} files  "
              f"{int(row['bytes']):>9} bytes  "
              f"{row['file_share']:>6.1%} of files  "
              f"{row['byte_share']:>6.1%} of bytes")


def _predict_collisions(entries: list[Entry]) -> list[str]:
    """Which shape files will not be able to take their own names.

    Known BEFORE `execute` runs, because the plan says which paths survive in
    the root, so the follow-up is in the plan the human reads rather than in
    output they may never scroll back to.
    """
    surviving = {e.path for e in entries if e.leg == "root"}
    from shape_materialize import COPIED_FROM_SHAPE, COPIED_VERBATIM, TEMPLATED
    shape_paths = [dst for _, dst in COPIED_FROM_SHAPE] + \
        list(COPIED_VERBATIM) + list(TEMPLATED)
    out = []
    for path in sorted(set(shape_paths)):
        if path in surviving or f"{path.split('/')[0]}/" in surviving:
            out.append(
                f"merge {COLLISION_DIR}/{path} into {path}: the source "
                "repository already has that name, so the shape's copy was "
                "written beside it and NOTHING was overwritten")
    return out


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------


class Plan:
    """A loaded `adoption-plan.yaml`, with the source it names."""

    def __init__(self, path: Path, data: dict):
        self.path = path
        self.data = data
        if data.get("kind") != PLAN_KIND:
            raise Refusal("plan-wrong-kind",
                          f"{path}: kind is {data.get('kind')!r}, expected "
                          f"{PLAN_KIND!r}")
        if data.get("mode") != "in-place":
            raise Refusal(
                "plan-unsupported-mode",
                f"{path}: mode is {data.get('mode')!r}; v0.2 implements "
                "`in-place` only",
                "Remediation: re-run `plan`, which writes `mode: in-place`. "
                "A `new-root` mode is described in the tool's own docstring "
                "and is not implemented.")
        self.entries = [e for e in (data.get("paths") or [])
                        if isinstance(e, dict)]
        self.legs = data.get("legs") or {}
        self.pins = [str(p) for p in (data.get("pins") or []) if p]

    @classmethod
    def load(cls, path: Path) -> "Plan":
        data = load_yaml(path)
        if not isinstance(data, dict):
            raise Refusal("plan-unreadable", f"{path}: not a mapping")
        return cls(path, data)

    @property
    def source_commit(self) -> str:
        return str((self.data.get("source") or {}).get("commit") or "")

    def open_source(self, override: str | None, work_root: Path) -> Source:
        spec = override or (self.data.get("source") or {}).get("local_path") \
            or (self.data.get("source") or {}).get("repository")
        if not spec:
            raise Refusal("plan-no-source",
                          f"{self.path}: `source:` names neither a local path "
                          "nor a repository")
        return Source.open(str(spec), work_root)

    def names(self) -> dict[str, str]:
        """The three repository names the plan declares, validated as values.

        They reach `gh repo create` and a push URL, so they are checked here
        rather than trusted because they came out of a file this tool wrote:
        the file is edited between `plan` and `execute`, on purpose.
        """
        return {role: checked_value(f"legs.{role}", self.legs.get(role))
                for role in ("assembly", "spec", "code")}

    @property
    def project_id(self) -> str:
        """The lowercase machine name, RE-VALIDATED here.

        The GitHub topic is derived from it, both for the manifest's `TOPIC`
        and for `gh repo edit --add-topic`, so it is read in ONE place rather
        than spelled out at each. `plan` refuses an `--id` that is not this
        shape, but the plan is edited between `plan` and `execute` on purpose,
        so the check is repeated where the value is USED: it reaches a `gh`
        command line and a written manifest, and a topic that does not match
        `contracts/repository-naming.yaml` is one `validate-repository-naming.py`
        will refuse in the project's own gate, long after the run that set it.
        """
        project_id = str(self.get("id", self.names()["assembly"].lower()))
        if not PROJECT_ID_RE.match(project_id):
            raise Refusal(
                "plan-bad-id",
                f"{self.path}: `id:` is {project_id!r} and must match "
                f"{PROJECT_ID_RE.pattern}",
                "Remediation: fix `id:` in the plan, or re-run `plan` with an "
                "explicit lowercase --id. The GitHub topic is derived from it.")
        return project_id

    def get(self, key, default=None):
        value = self.data.get(key)
        return default if value is None else value

    def allowed_empty_legs(self) -> set[str]:
        """The legs this PLAN consents to having seeded. `execute` unions it
        with its own `--allow-empty-leg`, so consent can be given at either
        end — but it is never inferred from the entries being empty, which is
        the state the consent exists to be deliberate about."""
        return {str(role) for role in (self.data.get("allow_empty_legs") or [])
                if role}

    def seeding_record_disagreements(self, seeded: list[str]) -> list[str]:
        """Where the plan's `seeding:` record and its own entries disagree.

        A NOTE, NOT A FINDING, and the entries win. The record is written by
        `plan`; the entries are edited afterwards, and resolving an ambiguous
        path INTO the code leg is exactly the edit that makes a recorded
        `seeded_from_template: true` stale. Refusing there would punish the
        human for answering the question the plan asked them.
        """
        record = self.data.get("seeding")
        if not isinstance(record, dict):
            return []
        out: list[str] = []
        for role in EXTRACTED_LEGS:
            row = record.get(role)
            if not isinstance(row, dict) or "seeded_from_template" not in row:
                continue
            recorded = bool(row.get("seeded_from_template"))
            if recorded != (role in seeded):
                out.append(
                    f"NOTE the `seeding:` record says the {role} leg would be "
                    f"{'seeded' if recorded else 'extracted'}, but the entries "
                    f"now say {'seeded' if role in seeded else 'extracted'}. "
                    "The entries win; the record is stale because the plan was "
                    "edited after it was written, which is what a plan is for.")
        return out


def _covering(entry_paths: list[str], path: str) -> list[str]:
    """Every plan entry that covers `path` — a file entry or an ancestor."""
    return [p for p in entry_paths
            if p == path or (p.endswith("/") and path.startswith(p))]


def _coverage_findings(entry_paths: list[str], tree_paths: list[str]) -> list[str]:
    """Every source path covered EXACTLY once, and every entry covering something.

    Both halves matter and they fail differently: an uncovered path is a file
    the split would silently drop, and an entry covering nothing is a plan
    describing a tree that no longer exists.
    """
    findings: list[str] = []
    duplicates = sorted({p for p in entry_paths if entry_paths.count(p) > 1})
    for path in duplicates:
        findings.append(f"FINDING plan-duplicate-path: {path} appears "
                        f"{entry_paths.count(path)} times")
    uncovered, multiple = [], []
    for path in tree_paths:
        covering = _covering(entry_paths, path)
        if not covering:
            uncovered.append(path)
        elif len(covering) > 1:
            multiple.append((path, covering))
    for path in uncovered[:20]:
        findings.append(f"FINDING plan-uncovered: {path} is in the source "
                        "tree and in no plan entry")
    if len(uncovered) > 20:
        findings.append(f"FINDING plan-uncovered: … and {len(uncovered) - 20} "
                        "more uncovered paths")
    for path, covering in multiple[:20]:
        findings.append(f"FINDING plan-covered-twice: {path} is covered by "
                        f"{covering}")
    used = {p for path in tree_paths for p in _covering(entry_paths, path)}
    for path in sorted(set(entry_paths) - used):
        findings.append(f"FINDING plan-empty-entry: {path} covers nothing in "
                        "the source tree at this commit")
    return findings


def _leg_findings(plan: Plan) -> list[str]:
    """`leg:` is answered, and answered with one of the four words."""
    findings: list[str] = []
    for entry in plan.entries:
        leg = entry.get("leg")
        if leg is None:
            findings.append(
                f"FINDING plan-unresolved: {entry.get('path')} still has "
                f"`leg: null`. The question was: {entry.get('question')}")
        elif str(leg) not in LEG_VALUES:
            findings.append(
                f"FINDING plan-bad-leg: {entry.get('path')} declares leg "
                f"{leg!r}; it is one of {list(LEG_VALUES)}")
    return findings


def _topics_line(topic: str, local: bool) -> str:
    """The `topics` plan line, the one `scaffold-project.py` also prints.

    A project's repositories carry `xf-project-<id>` so the organisation can
    be listed by project; the adopted assembly root is the project's own root
    and gets it exactly as the two new legs do.
    """
    return "  topics " + ("skipped for local remotes" if local else
                          f"gh repo edit --add-topic {topic} on all three")


def _print_what_will_happen(plan: Plan, source: Source, names: dict,
                            topic: str, local: bool = False) -> None:
    moved = [e for e in plan.entries if str(e.get("leg")) in ("spec", "code")]
    stays = [e for e in plan.entries if str(e.get("leg")) == "root"]
    drops = [e for e in plan.entries if str(e.get("leg")) == "drop"]
    seeded = seeded_legs(assigned_paths(plan.entries))
    print(f"\nWHAT WILL HAPPEN, against {source.repository or source.path} @ "
          f"{source.commit[:12]}:")
    print(f"  create {names['spec']} and {names['code']} "
          f"({plan.get('visibility', 'private')})")
    print(f"  extract {len(moved)} path(s) with `git filter-repo`, history "
          "preserved")
    for role in seeded:
        print(f"  SEED the {role} leg from {SEED_TEMPLATE[role]}/ — no path is "
              "assigned to it")
    print(f"  ONE split commit on branch {plan.get('adopt_branch', ADOPT_BRANCH)} "
          f"of {names['assembly']}: `git rm -r` those paths, mount the legs at "
          f"{plan.legs.get('spec_path')}/ and {plan.legs.get('code_path')}/")
    print(f"  {len(stays)} path(s) stay in the assembly root; "
          f"{len(drops)} dropped")
    print("  the source is never deleted, never renamed, never force-pushed")
    print(_topics_line(topic, local))
    for item in plan.get("follow_ups", []):
        print(f"  follow-up: {item}")


def cmd_check(args) -> int:
    plan = Plan.load(Path(args.plan))
    work_root = _work_root(args)
    source = plan.open_source(args.source, work_root)
    naming = NamingPolicy.load(NAMING_POLICY)
    findings: list[str] = []

    if plan.source_commit and source.commit != plan.source_commit:
        findings.append(
            f"FINDING plan-stale: the plan was written against "
            f"{plan.source_commit[:12]} but {source.branch} is now at "
            f"{source.commit[:12]}. Re-run `plan`: a coverage check against a "
            "tree that has moved proves nothing about the tree that will be "
            "split.")

    entry_paths = [str(e.get("path")) for e in plan.entries]
    tree_paths = [path for path, _, _, _ in source.tree()]
    findings.extend(_coverage_findings(entry_paths, tree_paths))
    findings.extend(_leg_findings(plan))

    names = plan.names()
    pins = set(plan.pins)
    try:
        _check_names(naming, names, pins)
        for role, name in names.items():
            found = naming.classify(name, role, pins)
            print(f"  {role:<9} {name:<28} {found.family}"
                  + (f"/{found.role}" if found.role else ""))
    except Refusal as exc:
        findings.append(f"FINDING {exc.code}: {exc.detail}")

    _print_what_will_happen(plan, source, names,
                            naming.topic_for(plan.project_id))

    seeded = seeded_legs(assigned_paths(plan.entries))
    for line in seeding_warnings(seeded, plan.allowed_empty_legs()):
        print(line)
    for line in plan.seeding_record_disagreements(seeded):
        print(line)

    for finding in findings:
        print(finding, file=sys.stderr)
    if findings:
        print(f"\n{len(findings)} finding(s) in {plan.path}", file=sys.stderr)
        return 1
    print("\nplan ok")
    return 0


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------


def _require_filter_repo() -> None:
    if shutil.which("git-filter-repo") is None:
        probe = subprocess.run(["git", "filter-repo", "--version"],
                               capture_output=True, text=True, check=False)
        if probe.returncode != 0:
            raise Refusal(
                "filter-repo-missing",
                "`git filter-repo` is not on PATH, and history extraction "
                "will not be attempted without it",
                FILTER_REPO_HINT)


def _confirm(args, plan: Plan, names: dict) -> None:
    if args.yes:
        return
    if not sys.stdin.isatty():
        raise Refusal(
            "adopt-unconfirmed",
            "this is not an interactive terminal and --yes was not passed, so "
            "there is nobody to ask. Creating two repositories and rewriting a "
            "third's default branch by pull request is not something to do on "
            "an assumption.",
            "Remediation: run it where a human can answer, or pass --yes once "
            "they have read the plan and the follow-ups.")
    print(f"\nThis creates {names['spec']} and {names['code']} and pushes a "
          f"split branch to {names['assembly']}.")
    answer = input("Type yes to proceed: ").strip().lower()
    if answer != "yes":
        raise Refusal("adopt-declined", f"answered {answer!r}, not 'yes'",
                      "Remediation: nothing was created. Re-run when ready.")


def _refuse_an_unrunnable_plan(plan: Plan, source: Source) -> None:
    """The two states a plan can be in that must not be executed.

    An unanswered question is never an implicit `root`, and a plan written
    against a tree that has since moved proves nothing about the tree that
    would be split — which is how a path goes missing.
    """
    unresolved = [e for e in plan.entries if e.get("leg") is None]
    if unresolved:
        raise Refusal(
            "plan-unresolved",
            f"{len(unresolved)} path(s) still have `leg: null`: "
            + ", ".join(str(e.get("path")) for e in unresolved[:8]),
            "Remediation: answer each entry's `question:` by setting `leg:` "
            "and adding a `resolution:` line, then run `check`. An unanswered "
            "question is never an implicit `root`.")
    if plan.source_commit and source.commit != plan.source_commit:
        raise Refusal(
            "plan-stale",
            f"the plan was written against {plan.source_commit[:12]} and "
            f"{source.branch} is now at {source.commit[:12]}",
            "Remediation: re-run `plan`, re-answer anything new, then "
            "`check`. Splitting a tree the plan has not seen is how a path "
            "goes missing.")


def _create_leg_remotes(plan: Plan, names: dict, repositories: dict,
                        urls: dict, tracking: str, local: bool) -> None:
    """(a) The two NEW repositories. The assembly root is never created here."""
    print("\ncreating the leg repositories")
    if local:
        Path(urls["spec"]).parent.mkdir(parents=True, exist_ok=True)
    for role in ("spec", "code"):
        if not local:
            run(["gh", "repo", "create", repositories[role],
                 f"--{plan.get('visibility', 'private')}", "--description",
                 f"{names['assembly']} — {role} leg, extracted from "
                 f"{repositories['assembly']} with history"])
            print(f"  gh    {repositories[role]}")
            continue
        bare = Path(urls[role])
        if bare.exists():
            raise Refusal(
                "leg-remote-exists", f"{bare} already exists",
                "Remediation: choose an empty --local-remote-dir. There is no "
                "--force: re-running over a live leg is not an adoption.")
        run(["git", "init", "-q", "--bare", "-b", tracking, str(bare)])
        print(f"  bare  {bare}")

    # A private or internal leg is unreadable to the `validate` workflow's
    # default GITHUB_TOKEN — the defect on the first real adoption
    # (MedxSoft/MedxEHR #7).
    visibility = plan.get("visibility", "private")
    if not local and visibility in ("private", "internal"):
        print(f"NOTE {repositories['spec']} and {repositories['code']} are "
              f"{visibility}: give {repositories['assembly']} a way to "
              "read them — a GitHub App (SHAPE_LEGS_APP_ID + "
              "SHAPE_LEGS_APP_PRIVATE_KEY, preferred) or a SHAPE_LEGS_TOKEN "
              "PAT (contents:read on the legs, fallback) — or the `validate` "
              "check cannot check them out.")
        hint = free_plan_secret_hint(
            plan.get("org", ""), repositories["assembly"],
            f"{repositories['spec']} and {repositories['code']} are")
        if hint:
            print(hint)


def _extract_leg(role: str, source: Source, work: Path, paths: list[str],
                 listing: Path, branch: str, url: str, tracking: str,
                 repository: str) -> tuple[str, str]:
    """(b) One leg, with its history: clone, filter, push. Returns commit+digest.

    A FRESH clone every time, because `git filter-repo` rewrites the whole
    object graph and is documented to want one; the branch is reset to the
    PLAN's commit rather than to whatever the default branch is now, so the
    extraction and the coverage check are about the same tree.
    """
    run(["git", *FILE_PROTOCOL, "clone", "-q", str(source.path), str(work)])
    run(["git", "checkout", "-q", "-B", branch, source.commit], cwd=work)
    listing.write_text("\n".join(paths) + "\n", encoding="utf-8")
    run(["git", "filter-repo", "--paths-from-file", str(listing), "--force"],
        cwd=work)
    head = git_out(["rev-parse", "HEAD"], cwd=work).lower()
    try:
        run(["git", "push", "-q", url, f"HEAD:refs/heads/{tracking}"], cwd=work)
    except CommandFailed as exc:
        print(exc.loudly(f"pushing the {role} leg"), file=sys.stderr)
        print(RULESET_HINT.format(work=work, repo=repository, role=role),
              file=sys.stderr)
        raise
    count = git_out(["rev-list", "--count", "HEAD"], cwd=work)
    print(f"  {role:<5} {len(paths):>3} path(s) -> {head[:12]} "
          f"({count} commits kept) -> {url}")
    return head, tree_digest(work, head)


def _seed_leg(role: str, work: Path, values: dict, branch: str, url: str,
              tracking: str, repository: str, display: str) -> tuple[str, str]:
    """(b′) A leg with NO extracted path: seeded from the shape's template.

    The same bytes `scaffold-project.py` writes for a new project's leg, as
    ONE initial commit with the identity this invocation carries. It is not an
    extraction and does not pretend to be: the commit message says the leg was
    seeded and why, so a reader of that repository's own history is never left
    wondering which commits of the adopted repository went missing.

    `branch` is accepted and ignored on purpose — a seeded leg has no branch of
    the source to reset to. `tracking` is the branch it is pushed to, exactly
    as an extracted leg is.
    """
    del branch
    copy_tree(SHAPE_ROOT / SEED_TEMPLATE[role], work, values)
    commit = git_init_commit(
        work,
        f"Seed the {role} leg of {display}\n\n"
        f"No path of {display} was assigned to the {role} leg by the adoption "
        f"plan, so this leg is SEEDED from {SHAPE_REPOSITORY}'s "
        f"{SEED_TEMPLATE[role]}/ rather than extracted with `git filter-repo`: "
        "a filter over an empty path list yields an empty HISTORY, which is "
        "not an empty repository.\n\nIt carries no history from the adopted "
        "repository because there was none to carry. The assembly root mounts "
        "and pins it exactly as it does the extracted leg.\n",
        tracking).lower()
    try:
        run(["git", "push", "-q", url, f"HEAD:refs/heads/{tracking}"], cwd=work)
    except CommandFailed as exc:
        print(exc.loudly(f"pushing the seeded {role} leg"), file=sys.stderr)
        print(RULESET_HINT.format(work=work, repo=repository, role=role),
              file=sys.stderr)
        raise
    print(f"  {role:<5}   0 path(s) -> {commit[:12]} (SEEDED from "
          f"{SEED_TEMPLATE[role]}/) -> {url}")
    return commit, tree_digest(work, commit)


def _mount_the_legs(assembly: Path, work_root: Path, names: dict, urls: dict,
                    paths_for: dict, spec_path: str, code_path: str) -> None:
    """(c, first half) `git rm` what moved, then mount the two legs.

    The submodule is added from the LEG'S WORKING TREE and its recorded URL is
    then rewritten to the canonical remote, exactly as the scaffold does: the
    adoption never depends on a push having propagated.
    """
    for path in sorted(paths_for["spec"] + paths_for["code"] + paths_for["drop"]):
        run(["git", "rm", "-r", "-q", "--", path.rstrip("/")], cwd=assembly)
    for role, path in (("spec", spec_path), ("code", code_path)):
        run(["git", *FILE_PROTOCOL, "submodule", "add", "-q",
             str(work_root / names[role]), path], cwd=assembly)
        run(["git", "config", "-f", ".gitmodules", f"submodule.{path}.url",
             urls[role]], cwd=assembly)
        run(["git", "remote", "set-url", "origin", urls[role]],
            cwd=assembly / path)
    run(["git", "submodule", "sync", "-q"], cwd=assembly)


def cmd_execute(args) -> int:  # noqa: C901
    plan = Plan.load(Path(args.plan))
    work_root = _work_root(args)
    source = plan.open_source(args.source, work_root)
    naming = NamingPolicy.load(NAMING_POLICY)
    _require_filter_repo()

    names = plan.names()
    pins = set(plan.pins)
    _check_names(naming, names, pins)
    _refuse_an_unrunnable_plan(plan, source)

    # THE PLAN IS UNTRUSTED INPUT. It is a file a human or an AI edited, and
    # every value below becomes an argument to `git` or `gh`, so each one is
    # validated before it is used rather than after something has gone wrong.
    local = args.local_remote_dir is not None
    spec_path = checked_value("legs.spec_path", plan.legs.get("spec_path")
                              or "spec")
    code_path = checked_value("legs.code_path", plan.legs.get("code_path")
                              or "code")
    branch = checked_value("adopt_branch", plan.get("adopt_branch",
                                                    ADOPT_BRANCH))
    tracking = checked_value("tracking_branch",
                             plan.get("tracking_branch", "main"))
    org = checked_value("org", plan.get("org"))
    repositories = {role: f"{org}/{name}" for role, name in names.items()}
    if local:
        # NOT created yet: nothing exists on disk until the human has said
        # yes, so a refused run leaves the directory it would have used
        # absent rather than empty.
        remote_dir = args.local_remote_dir.resolve()
        urls = {role: str(remote_dir / f"{name}.git")
                for role, name in names.items()}
        urls["assembly"] = str(source.path)
    else:
        urls = {role: f"https://github.com/{org}/{name}.git"
                for role, name in names.items()}

    paths_for = {leg: [checked_value("a plan path", e.get("path"))
                       for e in plan.entries if str(e.get("leg")) == leg]
                 for leg in LEG_VALUES}

    # A leg with no path is SEEDED, and seeding takes a human's word. Derived
    # from the ENTRIES, never from the plan's own `seeding:` record: the
    # entries are what the split is actually made of.
    seeded = seeded_legs(paths_for)
    allowed = plan.allowed_empty_legs() | set(args.allow_empty_leg or [])
    unconsented = [role for role in seeded if role not in allowed]
    if unconsented:
        raise Refusal(
            "adopt-empty-leg-unconsented",
            "no path is assigned to the "
            + " and ".join(f"{role} leg" for role in unconsented)
            + ", so it would be SEEDED from "
            + " and ".join(f"{SEED_TEMPLATE[role]}/" for role in unconsented)
            + " instead of extracted, and no `--allow-empty-leg` says that is "
            "intended",
            "Remediation: a repository that genuinely has no "
            + "/".join(unconsented) + " yet is adopted with "
            + " ".join(f"--allow-empty-leg {role}" for role in unconsented)
            + " — on this command, or recorded in the plan by re-running "
            "`plan` with the same flag. A plan that lost its "
            + "/".join(unconsented) + " paths to a bad edit looks identical "
            "from here, which is why this is a human's word and not an "
            "inference.")
    for line in plan.seeding_record_disagreements(seeded):
        print(line)
    topic = naming.topic_for(plan.project_id)
    print(_topics_line(topic, local))
    _confirm(args, plan, names)

    # ---- (a) the two legs' remotes ----------------------------------------
    _create_leg_remotes(plan, names, repositories, urls, tracking, local)

    # The substitution table is built BEFORE the legs, because a SEEDED leg is
    # rendered from `templates/<role>-root/` and needs it. The four leg
    # commit/digest values are the only ones that cannot be known yet; they
    # are filled in below, before the assembly root is materialized.
    shape_commit = git_out(["rev-parse", "HEAD"], cwd=SHAPE_ROOT).lower()
    values = _template_values(plan, names, repositories, urls, spec_path,
                              code_path, tracking, {}, {},
                              shape_commit, pins, naming)

    # ---- (b) history-preserving extraction, or a seeded leg ---------------
    leg_commits: dict[str, str] = {}
    leg_digests: dict[str, str] = {}
    for role in EXTRACTED_LEGS:
        try:
            if role in seeded:
                leg_commits[role], leg_digests[role] = _seed_leg(
                    role, work_root / names[role], values, branch, urls[role],
                    tracking, repositories[role], names["assembly"])
            else:
                leg_commits[role], leg_digests[role] = _extract_leg(
                    role, source, work_root / names[role], paths_for[role],
                    work_root / f"{role}-paths.txt", branch, urls[role],
                    tracking, repositories[role])
        except CommandFailed:
            return 2
    values.update({
        "SPEC_COMMIT": leg_commits["spec"],
        "CODE_COMMIT": leg_commits["code"],
        "SPEC_TREE_SHA256": leg_digests["spec"],
        "CODE_TREE_SHA256": leg_digests["code"],
    })

    # ---- (c) ONE split commit on a branch of the source -------------------
    assembly = work_root / names["assembly"]
    run(["git", *FILE_PROTOCOL, "clone", "-q", str(source.path), str(assembly)])
    run(["git", "checkout", "-q", "-B", branch, source.commit], cwd=assembly)
    _mount_the_legs(assembly, work_root, names, urls, paths_for, spec_path,
                    code_path)

    materialized = materialize_assembly_root(
        SHAPE_ROOT, assembly, values, collision_dir=COLLISION_DIR,
        append={"Makefile": ADOPT_MAKEFILE_BLOCK})
    for intended, actual in materialized.collisions:
        print(f"  beside  {actual} (the source already has {intended}; nothing "
              "was overwritten)")

    follow_ups = [str(f) for f in plan.get("follow_ups", [])]
    message = _split_message(names, paths_for, leg_commits, spec_path,
                             code_path, follow_ups, materialized.collisions,
                             seeded)
    run(["git", "add", "-A", "--", "."], cwd=assembly)
    env_commit(assembly, message)
    split_commit = git_out(["rev-parse", "HEAD"], cwd=assembly).lower()
    try:
        run(["git", "push", "-q", urls["assembly"],
             f"HEAD:refs/heads/{branch}"], cwd=assembly)
    except CommandFailed as exc:
        print(exc.loudly("pushing the split branch"), file=sys.stderr)
        return 2
    print(f"\n  split {split_commit[:12]} on {branch} -> {urls['assembly']}")
    topics_failed = False
    if not local:
        try:
            url = run(["gh", "pr", "create", "--repo", repositories["assembly"],
                       "--base", tracking, "--head", branch,
                       "--title", f"Adopt the three-repository shape: "
                                  f"{names['spec']} and {names['code']}",
                       "--body", message])
            print(f"  pull request {url}")
        except CommandFailed as exc:
            print(exc.loudly("opening the pull request"), file=sys.stderr)
            print("The branch IS pushed. Open the pull request by hand:\n"
                  f"    gh pr create --repo {repositories['assembly']} "
                  f"--base {tracking} --head {branch}", file=sys.stderr)
            return 2

        # ---- the topic, on all three --------------------------------------
        # The assembly root pre-existed and is still a repository OF THIS
        # PROJECT: `project.yaml` claims `topic: <topic>` either way, and a
        # claim the organisation cannot see is the defect being fixed here.
        #
        # A TOPIC THAT WILL NOT SET DOES NOT SUPPRESS THE VERIFICATION TABLE.
        # The split is pushed and the pull request is open by now, and the
        # blob-sha accounting for every source path is the report a human is
        # told to read back (AGENTS.md step 7); losing it to a permission or a
        # rate limit would be the more expensive failure. It is still a
        # non-zero exit, reported after the table, with the commands to
        # finish by hand.
        try:
            for role in ("assembly", "spec", "code"):
                run(["gh", "repo", "edit", repositories[role], "--add-topic",
                     topic])
            print(f"  topic     {topic} set on all three")
        except CommandFailed as exc:
            topics_failed = True
            print(exc.loudly("setting the project topic"), file=sys.stderr)
            print("The split IS pushed and the pull request IS open. Set the "
                  "topic by hand:\n"
                  + "\n".join(f"    gh repo edit {repositories[role]} "
                              f"--add-topic {topic}"
                              for role in ("assembly", "spec", "code")),
                  file=sys.stderr)

    # ---- (d) verification, by blob sha ------------------------------------
    verified = _verify(source, assembly, work_root, names, paths_for,
                       split_commit, seeded)
    if verified:
        return verified   # a verification mismatch outranks a missing topic
    return 2 if topics_failed else 0


def _template_values(plan: Plan, names, repositories, urls, spec_path,
                     code_path, tracking, leg_commits, leg_digests,
                     shape_commit, pins, naming) -> dict[str, str]:
    project = names["assembly"]
    project_id = plan.project_id
    elected_on = str(plan.get("elected_on", _dt.date.today().isoformat()))
    # `.get(role, "")` because this table is built BEFORE the legs exist, so
    # that a SEEDED leg's template can be rendered from it. The four values
    # are filled in by the caller as soon as each leg has a commit, and the
    # assembly root — the only tree whose templates name them — is
    # materialized after that.
    return {
        "PROJECT": project,
        "PROJECT_ID": project_id,
        "PROJECT_NAME": project,
        "ORG": str(plan.get("org")),
        "TOPIC": naming.topic_for(project_id),
        "VISIBILITY": str(plan.get("visibility", "private")),
        # A plan that omits `reference:` — one written by hand, or by a tool
        # older than this rule — is resolved from ITS OWN `elected_on`, not
        # from the day `execute` happens to run. The plan carries the human's
        # act; the calendar of the machine running the split does not.
        "REFERENCE": str(plan.get("reference")
                         or default_reference(elected_on)),
        "ELECTED_BY": str(plan.get("elected_by", "")),
        "ELECTED_ON": elected_on,
        "TRACKING_BRANCH": tracking,
        "SPEC_PATH": spec_path,
        "CODE_PATH": code_path,
        "ASSEMBLY_REPOSITORY": repositories["assembly"],
        "SPEC_REPOSITORY": repositories["spec"],
        "CODE_REPOSITORY": repositories["code"],
        "SHAPE_REPOSITORY": SHAPE_REPOSITORY,
        "SHAPE_COMMIT": shape_commit,
        "SHAPE_TREE_SHA256": tree_digest(SHAPE_ROOT, shape_commit),
        "DIGEST_DEFINITION": TREE_DIGEST_DEFINITION,
        "CLONE_URL": urls["assembly"],
        "ASSEMBLY_CLONE_URL": urls["assembly"],
        "SPEC_COMMIT": leg_commits.get("spec", ""),
        "CODE_COMMIT": leg_commits.get("code", ""),
        "SPEC_TREE_SHA256": leg_digests.get("spec", ""),
        "CODE_TREE_SHA256": leg_digests.get("code", ""),
        "NEUTRAL_PRODUCT_PINS": ("[]" if not pins else
                                 "\n" + "\n".join(f"  - {p}"
                                                  for p in sorted(pins))),
        "ASSEMBLY_NAMING": naming_block(naming, names["assembly"], "assembly",
                                        pins),
        "SPEC_NAMING": naming_block(naming, names["spec"], "spec", pins),
        "CODE_NAMING": naming_block(naming, names["code"], "code", pins),
    }


def _split_message(names, paths_for, leg_commits, spec_path, code_path,
                   follow_ups, collisions, seeded=()) -> str:
    def none_line(role: str) -> list[str]:
        if role not in seeded:
            return ["  (none)"]
        return [f"  (none — this leg was SEEDED from {SHAPE_REPOSITORY}'s "
                f"{SEED_TEMPLATE[role]}/, because no path of this repository "
                f"was assigned to it. It is mounted and pinned like the other "
                f"leg and carries no history from here, there being none.)"]

    lines = [
        f"Adopt the three-repository shape: {names['spec']} and "
        f"{names['code']}",
        "",
        f"{names['assembly']} keeps its name, its identity and its full "
        "history and becomes the assembly root of the project. The two legs "
        "are NEW repositories extracted with `git filter-repo`, so every "
        "moved file keeps the commits that made it. Nothing was deleted: what "
        "leaves this tree arrives in a leg at the same path, mounted back "
        f"here at {spec_path}/ and {code_path}/.",
        "",
        f"MOVED TO THE SPEC LEG ({names['spec']} @ {leg_commits['spec'][:12]}):",
    ]
    lines += [f"  {path}" for path in sorted(paths_for["spec"])] \
        or none_line("spec")
    lines += ["",
              f"MOVED TO THE CODE LEG ({names['code']} @ "
              f"{leg_commits['code'][:12]}):"]
    lines += [f"  {path}" for path in sorted(paths_for["code"])] \
        or none_line("code")
    if paths_for["drop"]:
        lines += ["", "DROPPED (in no leg and no longer here):"]
        lines += [f"  {path}" for path in sorted(paths_for["drop"])]
    lines += ["", "STAYS IN THE ASSEMBLY ROOT:"]
    lines += [f"  {path}" for path in sorted(paths_for["root"])]
    if collisions:
        lines += ["", "WRITTEN BESIDE, NOT OVER (this repository had the name "
                  "first):"]
        lines += [f"  {actual}  <- the shape's {intended}"
                  for intended, actual in collisions]
    if follow_ups:
        lines += ["", "FOLLOW-UPS, which this commit does NOT do:"]
        lines += [f"  - {item}" for item in follow_ups]
    return "\n".join(lines) + "\n"


def _verify(source: Source, assembly: Path, work_root: Path, names,
            paths_for, split_commit: str, seeded=()) -> int:
    """Every source blob is in exactly one place afterwards, or this fails.

    THE ONE CHECK THAT MAKES THE REST TRUSTWORTHY. Counting paths would pass a
    split that silently truncated a file; comparing BLOB SHAs cannot. A path
    that is in two places is as much a finding as a path that is in none —
    the second is data loss and the first is two owners for one file.

    A SEEDED LEG DOES NOT WEAKEN IT. Its files are template bytes that were
    never in the source, so they cannot match a source blob and are counted as
    added, exactly like the manifest and the pins. The leg's row therefore
    reads `0 of N source paths (seeded from template)` — which is the honest
    number, and still leaves every source path to be accounted for somewhere.
    """
    print("\nVERIFICATION — every source path at "
          f"{source.commit[:12]}, by blob sha")
    before = {path: oid for path, _, oid, _ in source.tree()}
    after: dict[str, list[str]] = {}
    for role in ("spec", "code"):
        for path, _, oid, _ in _tree_of(work_root / names[role], "HEAD"):
            after.setdefault(path, []).append(f"{role}:{oid}")
    for path, mode, oid, _ in _tree_of(assembly, split_commit):
        if mode == "160000":
            continue
        after.setdefault(path, []).append(f"root:{oid}")

    counts, findings = _account_for(before, after, paths_for["drop"])
    added = sorted(set(after) - set(before))
    for leg in ("spec", "code", "root", "drop"):
        note = " (seeded from template)" if leg in seeded else ""
        print(f"  {leg:<6} {counts[leg]:>5} of {len(before)} source "
              f"paths{note}")
    print(f"  added  {len(added):>5} new paths (manifest, pins, shape files"
          + (", seeded leg" if seeded else "") + ")")
    for finding in findings:
        print(finding, file=sys.stderr)
    if findings:
        print(f"\n{len(findings)} verification finding(s). The legs and the "
              "branch exist; NOTHING was deleted from the source, so the exit "
              "is to fix the plan and re-run into a fresh --local-remote-dir "
              "or fresh leg repositories.", file=sys.stderr)
        return 1
    print("\nadoption verified: every source path is in exactly one place")
    print(f"\nNEXT: review the pull request on {names['assembly']}, then\n"
          f"    git clone --recurse-submodules <{names['assembly']} url>\n"
          "    make bootstrap")
    return 0


def _account_for(before: dict, after: dict, drops: list[str]) -> tuple[dict, list]:
    """Where each source blob landed: exactly one place, or a finding.

    A path in TWO places is as much a finding as a path in none — the second
    is data loss and the first is two repositories owning one file.
    """
    dropped = {p.rstrip("/") for p in drops}
    counts = {"spec": 0, "code": 0, "root": 0, "drop": 0}
    findings: list[str] = []
    for path, oid in sorted(before.items()):
        landings = [where for where in after.get(path, [])
                    if where.split(":", 1)[1] == oid]
        if len(landings) == 1:
            counts[landings[0].split(":", 1)[0]] += 1
        elif landings:
            findings.append(f"FINDING adopt-duplicated: {path} is in "
                            + ", ".join(landings))
        elif any(path == d or path.startswith(d + "/") for d in dropped):
            counts["drop"] += 1
        else:
            findings.append(f"FINDING adopt-lost: {path} ({oid[:12]}) is in no "
                            "leg, not in the root tree, and not listed as drop")
    return counts, findings


def _tree_of(repo: Path, rev: str) -> list[tuple[str, str, str, int]]:
    raw = git_out(["ls-tree", "-r", "-z", rev], cwd=repo, binary=True)
    out = []
    for record in raw.split(b"\x00"):
        if not record:
            continue
        head, _, path = record.partition(b"\t")
        mode, kind, oid = head.decode().split()
        out.append((path.decode("utf-8", "surrogateescape"), mode, oid, 0))
        del kind
    return out


# ---------------------------------------------------------------------------
# shared
# ---------------------------------------------------------------------------


def _names(project: str) -> dict[str, str]:
    return {"assembly": project, "spec": f"{project}-spec",
            "code": f"{project}-code"}


def _check_names(policy: NamingPolicy, names: dict[str, str],
                 pins: set[str]) -> None:
    for role, name in names.items():
        found = policy.classify(name, role, pins)
        if found is None:
            raise Refusal(
                "naming-unclassified",
                f"{name!r} matches no family in the naming policy",
                "Remediation: --project takes one CamelCase token with no "
                "hyphen, underscore, dot or space.")
        if not accepts_role(found, role):
            raise Refusal(
                "naming-role-mismatch",
                f"{name!r} classifies as {found.family}"
                + (f"/{found.role}" if found.role else "")
                + f", not as the {role!r} form of a project leg "
                f"({found.reason})",
                "Remediation: --project takes one CamelCase token. A declared "
                "descendant MAY be the assembly root — declare the pin with "
                "`--pin open<Product>` and it classifies as one.")


def _elector() -> str:
    try:
        return git_out(["config", "user.name"], cwd=SHAPE_ROOT)
    except Refusal:
        return ""


def _work_root(args) -> Path:
    root = (args.work_dir.resolve() if getattr(args, "work_dir", None)
            else Path(tempfile.mkdtemp(prefix="openreposhape-adopt-")))
    root.mkdir(parents=True, exist_ok=True)
    return root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="classify a source repository")
    plan.add_argument("--source", required=True,
                      help="a local path (read only) or `org/repo` to clone")
    plan.add_argument("--project", required=True,
                      help="the assembly-root name; for an in-place adoption "
                           "it is the source repository's own name")
    plan.add_argument("--org", default=None)
    plan.add_argument("--id", default=None)
    plan.add_argument("--visibility", choices=VISIBILITY_CHOICES,
                      default="private")
    plan.add_argument("--elected-by", default=None)
    plan.add_argument("--elected-on", default=None, help="YYYY-MM-DD")
    plan.add_argument("--reference", default=None,
                      help="the document the election followed. Default: "
                           "openxFactory's ratified "
                           "docs/project-repo-schema.md for an election on or "
                           "after 2026-09-02, and the staged fragment it was "
                           "ratified from for one dated earlier — so "
                           "--elected-on chooses it.")
    plan.add_argument("--tracking-branch", default="main")
    plan.add_argument("--spec-path", default="spec")
    plan.add_argument("--code-path", default="code")
    plan.add_argument("--pin", action="append", default=[],
                      help="a neutral product this project declares a pin on "
                           "— a NAME only, e.g. --pin openGlass or --pin "
                           f"{NEUTRAL_PRODUCT_OWNER}/openGlass to name the "
                           "owner explicitly. Adopting a project pins no "
                           "commit at plan time, so a trailing @<commit> "
                           "(scaffold-project.py's syntax) is refused.")
    plan.add_argument("--allow-empty-leg", action="append", default=[],
                      choices=EXTRACTED_LEGS,
                      help="record in the plan that this leg having NO path "
                           "is intended, so it may be SEEDED from the shape's "
                           "template instead of extracted. The InkRouter "
                           "services are specifications with no code yet "
                           "(2026-09-04): `--allow-empty-leg code`. "
                           "Repeatable.")
    plan.add_argument("--path-policy", type=Path, default=None)
    plan.add_argument("--out", default="adoption-plan.yaml")
    plan.add_argument("--work-dir", type=Path, default=None)
    plan.set_defaults(func=cmd_plan)

    check = subparsers.add_parser("check", help="validate a plan")
    check.add_argument("--plan", required=True)
    check.add_argument("--source", default=None,
                       help="override the source the plan names")
    check.add_argument("--work-dir", type=Path, default=None)
    check.set_defaults(func=cmd_check)

    execute = subparsers.add_parser("execute", help="carry the plan out")
    execute.add_argument("--plan", required=True)
    execute.add_argument("--source", default=None)
    execute.add_argument("--local-remote-dir", type=Path, default=None,
                         help="create the legs as bare repositories here "
                              "instead of calling `gh` (the TEST path)")
    execute.add_argument("--allow-empty-leg", action="append", default=[],
                         choices=EXTRACTED_LEGS,
                         help="proceed even though NO path is assigned to this "
                              "leg, seeding it from the shape's template. "
                              "Unioned with the plan's own `allow_empty_legs:`; "
                              "without one of the two, execute refuses.")
    execute.add_argument("--yes", action="store_true",
                         help="the human has read the plan and the follow-ups")
    execute.add_argument("--work-dir", type=Path, default=None)
    execute.set_defaults(func=cmd_execute)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except CommandFailed as exc:
        print(exc.loudly("a git or gh command failed"), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
