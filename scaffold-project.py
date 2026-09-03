#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Create a project's three repositories in the shape this standard describes.

    ./scaffold-project.py --org <org> --project <Project> [--dry-run]

WHAT IT DOES
  1. Validates the three names — `<Project>`, `<Project>-spec`,
     `<Project>-code` — against `contracts/repository-naming.yaml` BEFORE it
     creates anything, so a naming mistake costs a message rather than three
     repositories and a rename.
  2. Creates the three remotes: `gh repo create` normally, or three BARE
     repositories in a directory with `--local-remote-dir`, which is the test
     path and touches no network.
  3. Materializes and pushes the spec and code trees.
  4. Materializes the assembly root, mounts the two legs as submodules, and
     writes the three pins — `commit` plus a `sorted-ls-tree-r-v1` tree digest
     for each leg, and a per-file sha256 pin over every file COPIED out of
     openRepoShape.
  5. Sets the `xf-project-<id>` topic on all three (skipped for local remotes).

WHY THE SHAPE FILES ARE COPIED AND NOT SUBMODULED. A scaffolded project must
work in an organisation that forked openRepoShape once and may never speak to
the upstream again; a project that needed the upstream mounted to run its own
gate would have made the shape a dependency rather than a shape. The copies are
digest-pinned in `contracts/shape-pin.yaml`, so "which openRepoShape is this a
copy of, and has anyone edited it since" both have answers.

IDEMPOTENCY. It refuses to write into a remote or a working directory that
already exists. There is no --force: re-running over a live project is not a
scaffold, and the failure mode of getting it wrong is silent data loss.

EXIT CODES: 0 done · 1 nothing (dry run prints and exits 0) · 2 refusal.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SHAPE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SHAPE_ROOT / "scripts"))
from repo_shape import (  # noqa: E402
    COMMIT_RE, PROJECT_ID_RE, TREE_DIGEST_DEFINITION, NamingPolicy, Refusal,
    accepts_role, checked_value, git_out, tree_digest,
)
from shape_materialize import (  # noqa: E402
    DEFAULT_REFERENCE, RULESET_HINT, SHAPE_REPOSITORY, CommandFailed,
    copy_tree, descendant_note, env_commit, git_init_commit,
    materialize_assembly_root, naming_block, run,
)

#: The pin argument: `openGlass@<40 hex>`, optionally organisation-qualified.
PIN_ARG_RE = re.compile(r"^(?P<name>[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?)@(?P<commit>[0-9a-fA-F]{40})$")

#: How a neutral product's tree is read when the pin is taken from the forge
#: rather than from a clone on this machine.
GH_TREE_API = "repos/{repo}/git/trees/{commit}?recursive=1"


def parse_pin(raw: str, org: str) -> tuple[str, str, str]:
    """`openGlass@<sha>` -> (product, `<org>/openGlass`, commit).

    THE COMMIT IS 40 HEX OR IT IS NOT A PIN. An abbreviated oid, a branch name
    or a tag cannot pass here for the same reason `contracts/<leg>-pin.yaml`
    refuses them: a tag can be moved and a commit cannot.
    """
    match = PIN_ARG_RE.match(raw.strip())
    if not match:
        raise Refusal(
            "pin-malformed",
            f"--pin {raw!r} is not `<openProduct>@<40 hex commit>`",
            "Remediation: pass the full 40-character commit, e.g. "
            "--pin openGlass@0123456789abcdef0123456789abcdef01234567. A tag "
            "or an abbreviated oid is refused: a tag can be moved.",
        )
    name = match.group("name")
    product = name.rsplit("/", 1)[-1]
    repository = name if "/" in name else f"{org}/{product}"
    return product, repository, match.group("commit").lower()


def pin_digest_from_source(source: Path, commit: str, repository: str) -> str:
    """The `sorted-ls-tree-r-v1` digest, read from a clone on this machine."""
    try:
        return tree_digest(source, commit)
    except Refusal as exc:
        raise Refusal(
            "pin-source-unreadable",
            f"{source} could not answer for {repository} @ {commit}: "
            f"{exc.detail}",
            "Remediation: point --pin-source at a clone of that repository "
            "that HAS the pinned commit (`git fetch --all` first), or drop "
            "--pin-source and let `gh api` read the forge.",
        ) from exc


def pin_digest_from_gh(repository: str, commit: str) -> str:
    """The same digest, computed from the forge's own recursive tree listing.

    A SHALLOW READ, not a clone: `git/trees/<commit>?recursive=1` returns one
    row per object with `mode`, `type`, `sha` and `path` — exactly the four
    columns `git ls-tree -r -z` emits, which is what makes the two readings
    the same number. Tree rows are dropped because `-r` emits none; a
    submodule arrives as `type: commit` with mode `160000` and is kept, as
    `ls-tree` keeps it.
    """
    proc = subprocess.run(
        ["gh", "api", GH_TREE_API.format(repo=repository, commit=commit)],
        capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise Refusal(
            "pin-unreadable",
            f"`gh api` could not read {repository} @ {commit}: "
            f"{proc.stderr.strip()}",
            "Remediation: check the commit exists in that repository and that "
            "`gh auth status` can see it, or pass --pin-source <local clone> "
            "to compute the digest with no network at all.",
        )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise Refusal("pin-unreadable",
                      f"{repository} @ {commit}: {exc}") from exc
    if payload.get("truncated"):
        raise Refusal(
            "pin-tree-truncated",
            f"the forge truncated its tree listing for {repository} @ "
            f"{commit}, so the digest would be computed over a PARTIAL tree",
            "Remediation: clone that repository and pass --pin-source <path>. "
            "A digest over a partial tree is a wrong answer with a confident "
            "tone.",
        )
    import hashlib
    records = sorted(
        f"{row['mode']} {row['type']} {row['sha']}\t{row['path']}".encode()
        for row in payload.get("tree") or [] if row.get("type") != "tree")
    digest = hashlib.sha256()
    for record in records:
        digest.update(record)
        digest.update(b"\n")
    return digest.hexdigest()


def remote_is_empty(repository: str) -> bool | None:
    """Does `<org>/<repo>` exist on GitHub with ZERO commits?

    True: it exists and is empty. False: it exists and has commits. None: it
    does not exist. GitHub answers a commit listing for an empty repository
    with 409 and the words "Git Repository is empty", which is the only
    reliable signal — `size: 0` is also what a repository of small files says.
    """
    probe = subprocess.run(["gh", "repo", "view", repository, "--json", "name"],
                           capture_output=True, text=True, check=False)
    if probe.returncode != 0:
        return None
    commits = subprocess.run(
        ["gh", "api", f"repos/{repository}/commits?per_page=1"],
        capture_output=True, text=True, check=False)
    if commits.returncode != 0:
        blob = (commits.stderr + commits.stdout).lower()
        if "empty" in blob:
            return True
        raise Refusal(
            "remote-unreadable",
            f"{repository} exists but its commit listing could not be read: "
            f"{commits.stderr.strip()}",
            "Remediation: check `gh auth status`, then re-run.",
        )
    try:
        return not json.loads(commits.stdout)
    except json.JSONDecodeError:
        return False


def local_remote_is_empty(bare: Path) -> bool | None:
    """The same question for a bare repository on disk (the test path)."""
    if not bare.exists():
        return None
    out = subprocess.run(["git", "-C", str(bare), "rev-list", "--count", "--all"],
                         capture_output=True, text=True, check=False)
    if out.returncode != 0:
        raise Refusal("remote-unreadable",
                      f"{bare} exists but is not a git repository")
    return out.stdout.strip() in ("", "0")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--org", required=True)
    parser.add_argument("--project", required=True,
                        help="the assembly-root name, e.g. Atlas")
    parser.add_argument("--id", default=None, help="lowercase project id")
    parser.add_argument("--name", default=None, help="display name")
    parser.add_argument("--visibility", choices=("private", "public"),
                        default="private")
    parser.add_argument("--elected-by", default=None)
    parser.add_argument("--elected-on", default=None, help="YYYY-MM-DD")
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--tracking-branch", default="main")
    parser.add_argument("--spec-path", default="spec")
    parser.add_argument("--code-path", default="code")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--local-remote-dir", type=Path, default=None,
                        help="create bare repositories here instead of calling "
                             "`gh repo create` (the TEST path; no network)")
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument("--reuse-empty-repo", action="store_true",
                        help="if <org>/<Project> already exists and has ZERO "
                             "commits, use it as the assembly root instead of "
                             "refusing. A repository with commits is still "
                             "refused: that is a live project, not a slot.")
    parser.add_argument("--pin", action="append", default=[],
                        metavar="openProduct@COMMIT",
                        help="declare a neutral-product pin, e.g. "
                             "--pin openGlass@<40 hex>. It writes "
                             "contracts/<openproduct>-pin.yaml and lists the "
                             "product in the manifest, which is what makes a "
                             "`<Domainx><Product>` name a DESCENDANT rather "
                             "than a name shaped like one. Repeatable.")
    parser.add_argument("--pin-source", type=Path, default=None,
                        help="a local clone to compute --pin digests from, "
                             "instead of reading the forge with `gh api` (the "
                             "TEST path; no network)")
    parser.add_argument("--work-dir", type=Path, default=None,
                        help="where the working trees are built "
                             "(default: a temporary directory)")
    args = parser.parse_args(argv)

    try:
        return _scaffold(args)
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except CommandFailed as exc:
        print(exc.loudly("a git or gh command failed"), file=sys.stderr)
        return 2


def declared_pin_values(args) -> dict[str, dict[str, str]]:
    """The template values for every `--pin`, with its digest resolved.

    The digest is the same `sorted-ls-tree-r-v1` number every other pin here
    carries, read either from a clone on this machine (`--pin-source`, and no
    network at all) or from the forge's own recursive tree listing.
    """
    pins: dict[str, dict[str, str]] = {}
    for raw in args.pin:
        product, repository, commit = parse_pin(raw, args.org)
        if args.pin_source is not None:
            digest = pin_digest_from_source(args.pin_source.resolve(), commit,
                                            repository)
            digest_source = f"local-clone ({args.pin_source})"
        else:
            digest = pin_digest_from_gh(repository, commit)
            digest_source = "gh-api-tree-recursive"
        pins[product] = {
            "PIN_PRODUCT": product,
            "PIN_REPOSITORY": repository,
            "PIN_COMMIT": commit,
            "PIN_TREE_SHA256": digest,
            "PIN_DIGEST_SOURCE": digest_source,
        }
    return pins


def _reusable_remotes(names: dict, urls: dict, repositories: dict,
                      local: bool, reuse_flag: bool) -> set[str]:
    """Which remotes already exist, and whether that is allowed.

    THE ONE REPOSITORY THAT MAY ALREADY EXIST is the assembly root, and only
    with `--reuse-empty-repo`, and only with ZERO commits. An organisation
    that creates the repository first and asks for the shape second is the
    ordinary case, not a mistake; an EMPTY repository is a name that has been
    reserved, and reserving a name is not starting a project. A repository
    with commits is refused: that is a live project, and `adopt-project.py`
    is the tool for one of those.
    """
    reused: set[str] = set()
    for role in names:
        target = Path(urls[role]) if local else repositories[role]
        empty = (local_remote_is_empty(target) if local
                 else remote_is_empty(target))
        if empty is None:
            continue
        if role == "assembly" and reuse_flag and empty:
            reused.add(role)
            print(f"  reuse {target} (zero commits)")
            continue
        raise Refusal(
            "scaffold-remote-exists",
            f"{target} already exists" + ("" if local else " on GitHub")
            + ("" if empty else " and has commits"),
            _exists_remedy(role, empty, reuse_flag))
    return reused


def _exists_remedy(role: str, empty: bool, reuse_flag: bool) -> str:
    """The remedy line for a remote that is already there.

    Three different situations answer to three different exits, and a refusal
    that named only one of them would send a human to the wrong one.
    """
    if role != "assembly":
        return ("Remediation: the two legs must not exist yet — they are "
                "created and seeded here. Delete them, or scaffold under a "
                "different --project. There is no --force.")
    if empty and not reuse_flag:
        return ("Remediation: it has ZERO commits, so it is a reserved name "
                "rather than a live project — re-run with --reuse-empty-repo "
                "to use it as the assembly root.")
    return ("Remediation: it HAS commits, so it is a live repository and this "
            "is not a scaffold. Use `adopt-project.py plan --source "
            "<org>/<repo> --project <Project>` to convert it in place, which "
            "keeps its name, its identity and its history. There is no "
            "--force.")


def _scaffold(args) -> int:  # noqa: C901
    # VALIDATED BEFORE ANYTHING IS BUILT FROM THEM. These five reach a `git`
    # or `gh` command line, and `checked_value` refuses a leading `-` because
    # git reads its own arguments. The naming policy checks what a project
    # name MEANS a few lines below; this checks what it may CONTAIN.
    project = checked_value("--project", args.project)
    args.tracking_branch = checked_value("--tracking-branch",
                                         args.tracking_branch)
    args.spec_path = checked_value("--spec-path", args.spec_path)
    args.code_path = checked_value("--code-path", args.code_path)
    args.org = checked_value("--org", args.org)
    project_id = checked_value("--id", args.id or project.lower())
    display = args.name or project
    elected_on = args.elected_on or _dt.date.today().isoformat()
    local = args.local_remote_dir is not None

    elected_by = args.elected_by
    if not elected_by:
        try:
            elected_by = git_out(["config", "user.name"], cwd=SHAPE_ROOT)
        except Refusal:
            elected_by = ""
    if not elected_by:
        raise Refusal(
            "scaffold-no-elector",
            "no --elected-by and no `git config user.name`. Electing this "
            "shape is a human's act and the manifest records whose.",
            "Remediation: re-run with --elected-by 'Your Name'.",
        )

    names = {"assembly": project, "spec": f"{project}-spec",
             "code": f"{project}-code"}
    policy = NamingPolicy.load(SHAPE_ROOT / "contracts" / "repository-naming.yaml")
    if not PROJECT_ID_RE.match(project_id):
        raise Refusal("scaffold-bad-id",
                      f"--id {project_id!r} must match {PROJECT_ID_RE.pattern}",
                      "Remediation: pass an explicit lowercase --id.")
    # WHAT THE PROJECT DECLARES ABOUT ITSELF, before any name is judged.
    # With no `--pin`, a descendant-form name is a claim with no referent and
    # the DECLARED ROLE wins. With `--pin openGlass@<sha>`, `MedxGlass` IS a
    # descendant — and, since 2026-09-02, may still be the assembly root that
    # carries the two legs. What is still refused is a real mismatch: a
    # `-spec` name offered as the assembly root, or a `open<Product>` /
    # `<X>-Install` form used as any leg — those forms are unambiguous by
    # construction and declaring a role cannot make them into a leg.
    pins = declared_pin_values(args)
    declared_pins: set[str] = set(pins)
    for role, name in names.items():
        found = policy.classify(name, role, declared_pins)
        if found is None:
            raise Refusal(
                "naming-unclassified",
                f"{name!r} matches no family in the naming policy. "
                "`<Project>` is one CamelCase token with no hyphen, "
                "underscore, dot or space.",
                "Remediation: re-run with a --project value of that form.",
            )
        if not accepts_role(found, role):
            raise Refusal(
                "naming-role-mismatch",
                f"{name!r} classifies as {found[0]}"
                + (f"/{found[1]}" if found[1] else "")
                + f", not as the {role!r} form of a project leg"
                + f" ({found.reason})",
                "Remediation: re-run with a --project value that is one "
                "CamelCase token.",
            )
    topic = policy.topic_for(project_id)

    # ---- the shape revision this project is cut from ----------------------
    shape_commit = git_out(["rev-parse", "HEAD"], cwd=SHAPE_ROOT).lower()
    shape_tree = tree_digest(SHAPE_ROOT, shape_commit)
    dirty = git_out(["status", "--porcelain"], cwd=SHAPE_ROOT)
    if dirty:
        print(
            "WARNING the openRepoShape checkout is DIRTY. `commit:` and "
            f"`tree_sha256` in the shape pin will record {shape_commit[:12]}, "
            "which does NOT describe the bytes being copied. The per-file "
            "sha256 rows are computed from the actual copies, so drift stays "
            "detectable — but commit before scaffolding a real project.",
            file=sys.stderr,
        )

    if local:
        remote_dir = args.local_remote_dir.resolve()
        urls = {role: str(remote_dir / f"{name}.git")
                for role, name in names.items()}
    else:
        urls = {role: f"https://github.com/{args.org}/{name}.git"
                for role, name in names.items()}
    repositories = {role: f"{args.org}/{name}" for role, name in names.items()}

    values = {
        "PROJECT": project,
        "PROJECT_ID": project_id,
        "PROJECT_NAME": display,
        "ORG": args.org,
        "TOPIC": topic,
        "REFERENCE": args.reference,
        "ELECTED_BY": elected_by,
        "ELECTED_ON": elected_on,
        "TRACKING_BRANCH": args.tracking_branch,
        "SPEC_PATH": args.spec_path,
        "CODE_PATH": args.code_path,
        "ASSEMBLY_REPOSITORY": repositories["assembly"],
        "SPEC_REPOSITORY": repositories["spec"],
        "CODE_REPOSITORY": repositories["code"],
        "SHAPE_REPOSITORY": SHAPE_REPOSITORY,
        "SHAPE_COMMIT": shape_commit,
        "SHAPE_TREE_SHA256": shape_tree,
        "DIGEST_DEFINITION": TREE_DIGEST_DEFINITION,
        "CLONE_URL": urls["assembly"],
        "ASSEMBLY_CLONE_URL": urls["assembly"],
        "NEUTRAL_PRODUCT_PINS": ("[]" if not pins else
                                 "\n" + "\n".join(f"  - {p}" for p in pins)),
        "ASSEMBLY_NAMING": naming_block(policy, names["assembly"], "assembly",
                                        declared_pins),
        "SPEC_NAMING": naming_block(policy, names["spec"], "spec", declared_pins),
        "CODE_NAMING": naming_block(policy, names["code"], "code", declared_pins),
    }

    # ---- the plan ----------------------------------------------------------
    print(f"project      {display} ({project_id})   topic {topic}")
    print(f"shape        {SHAPE_REPOSITORY} @ {shape_commit[:12]} "
          f"(tree {shape_tree[:12]}…)")
    print(f"elected by   {elected_by} on {elected_on}")
    print(f"reference    {args.reference}")
    for role in ("assembly", "spec", "code"):
        print(f"  {role:<9} {repositories[role]:<28} -> {urls[role]}")
    for role in ("assembly", "spec", "code"):
        note = descendant_note(policy, names[role], role, declared_pins)
        if note:
            print(note)
    print(f"legs mounted at {args.spec_path}/ and {args.code_path}/ inside "
          f"{names['assembly']}")
    for product, pin_values in pins.items():
        print(f"pin          {pin_values['PIN_REPOSITORY']} @ "
              f"{pin_values['PIN_COMMIT'][:12]} tree "
              f"{pin_values['PIN_TREE_SHA256'][:12]}… -> "
              f"contracts/{product.lower()}-pin.yaml ({pin_values['PIN_DIGEST_SOURCE']})")
    if pins:
        found = policy.classify(names["assembly"], "assembly", declared_pins)
        print(f"declared     {names['assembly']} classifies as {found.family}"
              + (f" / {found.role}" if found.role else "")
              + f" — {found.reason}")
    print("remotes      " + ("bare repositories on disk (no network)" if local
                             else f"gh repo create --{args.visibility}"))
    if args.reuse_empty_repo:
        print("reuse        an EXISTING <Project> with zero commits is used as "
              "the assembly root")
    print("push         " + ("SKIPPED (--no-push)" if args.no_push else "yes"))
    print("topics       " + ("skipped for local remotes" if local
                             else f"gh repo edit --add-topic {topic}"))
    if args.dry_run:
        print("\n--dry-run: nothing was created.")
        return 0

    # ---- refuse to write over anything that already exists ----------------
    work_root = (args.work_dir.resolve() if args.work_dir
                 else Path(tempfile.mkdtemp(prefix="openreposhape-")))
    work_root.mkdir(parents=True, exist_ok=True)
    for role, name in names.items():
        target = work_root / name
        if target.exists() and any(target.iterdir()):
            raise Refusal(
                "scaffold-target-exists",
                f"{target} already exists and is not empty",
                "Remediation: choose an empty --work-dir. There is no --force: "
                "re-running over a live tree is not a scaffold.",
            )
    # THE ONE REPOSITORY THAT MAY ALREADY EXIST is the assembly root, and only
    # with `--reuse-empty-repo`, and only with ZERO commits. An organisation
    # that creates the repository first and asks for the shape second is the
    # ordinary case, not a mistake; an EMPTY repository is a name that has been
    # reserved, and reserving a name is not starting a project. A repository
    # with commits is refused exactly as before: that is a live project, and
    # `adopt-project.py` is the tool for one of those.
    if local:
        remote_dir.mkdir(parents=True, exist_ok=True)
    reused = _reusable_remotes(names, urls, repositories, local,
                               args.reuse_empty_repo)

    # ---- create the remotes ------------------------------------------------
    print("\ncreating remotes")
    for role in ("spec", "code", "assembly"):
        if role in reused:
            print(f"  reused {repositories[role]} (created by somebody else, "
                  "zero commits)")
            continue
        if local:
            run(["git", "init", "-q", "--bare", "-b", args.tracking_branch,
                 urls[role]])
            print(f"  bare  {urls[role]}")
        else:
            description = {
                "assembly": f"{display} — assembly root (project {project_id})",
                "spec": f"{display} — spec leg (project {project_id})",
                "code": f"{display} — code leg (project {project_id})",
            }[role]
            run(["gh", "repo", "create", repositories[role],
                 f"--{args.visibility}", "--description", description])
            print(f"  gh    {repositories[role]} ({args.visibility})")

    # ---- the two legs ------------------------------------------------------
    leg_commits: dict[str, str] = {}
    leg_digests: dict[str, str] = {}
    for role, template in (("spec", "spec-root"), ("code", "code-root")):
        work = work_root / names[role]
        copy_tree(SHAPE_ROOT / "templates" / template, work, values)
        commit = git_init_commit(
            work, f"Seed the {role} leg of {display}\n\n"
                  f"Scaffolded from {SHAPE_REPOSITORY} @ {shape_commit}.",
            args.tracking_branch)
        leg_commits[role] = commit.lower()
        leg_digests[role] = tree_digest(work, commit)
        run(["git", "remote", "add", "origin", urls[role]], cwd=work)
        if not args.no_push:
            try:
                run(["git", "push", "-q", "-u", "origin", args.tracking_branch],
                    cwd=work)
            except CommandFailed as exc:
                print(exc.loudly(f"pushing the {role} leg"), file=sys.stderr)
                print(RULESET_HINT.format(work=work, repo=repositories[role],
                                          role=role), file=sys.stderr)
                return 2
        print(f"  {role:<9} {commit[:12]} tree {leg_digests[role][:12]}… "
              f"-> {urls[role]}")

    values.update({
        "SPEC_COMMIT": leg_commits["spec"],
        "CODE_COMMIT": leg_commits["code"],
        "SPEC_TREE_SHA256": leg_digests["spec"],
        "CODE_TREE_SHA256": leg_digests["code"],
    })

    # ---- the assembly root -------------------------------------------------
    assembly = work_root / names["assembly"]
    assembly.mkdir(parents=True, exist_ok=True)
    # ONE materializer, shared with `adopt-project.py`. The scaffold builds
    # into a directory it made itself, so a collision here is a defect and
    # `collision_dir=None` says so by raising.
    materialize_assembly_root(SHAPE_ROOT, assembly, values, neutral_pins=pins)

    run(["git", "init", "-q", "-b", args.tracking_branch, str(assembly)])
    # `git submodule add` from the LEG WORKING TREE, then the recorded URL is
    # rewritten to the canonical remote: this way the scaffold never depends on
    # a push having propagated, and `--no-push` produces the same tree.
    for role, path in (("spec", args.spec_path), ("code", args.code_path)):
        run(["git", "-c", "protocol.file.allow=always", "submodule", "add",
             "-q", str(work_root / names[role]), path], cwd=assembly)
        run(["git", "config", "-f", ".gitmodules", f"submodule.{path}.url",
             urls[role]], cwd=assembly)
        run(["git", "remote", "set-url", "origin", urls[role]],
            cwd=assembly / path)
    run(["git", "submodule", "sync", "-q"], cwd=assembly)
    run(["git", "add", "-A", "--", "."], cwd=assembly)
    env_commit(assembly,
               f"Scaffold {display}: manifest, two legs, three pins\n\n"
               f"Shape {SHAPE_REPOSITORY} @ {shape_commit}.\n"
               f"spec {leg_commits['spec']}\ncode {leg_commits['code']}")
    run(["git", "remote", "add", "origin", urls["assembly"]], cwd=assembly)
    if not args.no_push:
        try:
            run(["git", "push", "-q", "-u", "origin", args.tracking_branch],
                cwd=assembly)
        except CommandFailed as exc:
            print(exc.loudly("pushing the assembly root"), file=sys.stderr)
            print(RULESET_HINT.format(work=assembly,
                                      repo=repositories["assembly"],
                                      role="assembly"), file=sys.stderr)
            return 2
    print(f"  assembly  {run(['git', 'rev-parse', 'HEAD'], cwd=assembly)[:12]} "
          f"-> {urls['assembly']}")

    # ---- topics ------------------------------------------------------------
    if not local:
        for role in ("assembly", "spec", "code"):
            run(["gh", "repo", "edit", repositories[role], "--add-topic", topic])
        print(f"  topic     {topic} set on all three")

    print(f"""
NEXT STEPS

    git clone --recurse-submodules {urls['assembly']}
    cd {names['assembly']}
    make bootstrap

`make bootstrap` puts each leg on `{args.tracking_branch}` AT its pinned commit,
runs the naming, manifest and lockstep-pin validators, and prints the review
authority a wallet register names for this project — or says that authority is
not wallet-carried here, and continues.

Working trees are at {work_root}
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
