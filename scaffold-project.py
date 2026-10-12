#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Create a project's three repositories in the shape this standard describes.

    ./scaffold-project.py --org <org> --project <Project> [--dry-run]

WHAT IT DOES
  1. Validates the three names — `<Project>`, `<Project>-spec`,
     `<Project>-code` — against `contracts/repository-naming.yaml` BEFORE it
     creates anything, so a naming mistake costs a message rather than three
     repositories and a rename. A leg path that is, holds or lies inside a
     path the shape writes into the assembly root (`contracts`,
     `project.yaml`, a `--pin`'s `contracts/<product>-pin.yaml`) is refused
     just as early, for the same reason (#197), and so is a `--pin` whose
     file the shape writes itself or another `--pin` writes (#241), and a
     `--referent-chain` link between the first and the last that is not a
     neutral product's name (#251).
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

import os
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
    free_plan_secret_hint,
    COMMIT_RE, NEUTRAL_PRODUCT_OWNER, PROJECT_ID_RE, TREE_DIGEST_DEFINITION,
    VISIBILITY_CHOICES, NamingPolicy, Refusal, accepts_role, checked_value,
    git_out, link_pins_from_trees, repo_basename, tree_digest,
)
from shape_materialize import (  # noqa: E402
    RULESET_HINT, SHAPE_REPOSITORY, CommandFailed,
    copy_tree, default_reference, descendant_note, election_date, env_commit,
    escape_what_stdout_cannot_encode, git_init_commit,
    materialize_assembly_root, naming_block, run, stage_written,
)
# The leg-path rule `adopt-project.py` asks of its own paths (#179).
from shape_materialize import refuse_bad_leg_paths  # noqa: E402
from shape_advisory import scaffold_lines  # noqa: E402
# The shape half of the leg-path collision rule, which `adopt-project.py`
# asks of its own mount paths (#172), imported as one unit (#197), with the
# one spelling of the file a `--pin` adds to what the shape writes.
from shape_materialize import (  # noqa: E402
    assembly_root_paths, neutral_pin_path, shape_path_collisions,
)

#: The pin argument: `openGlass@<40 hex>`, optionally organisation-qualified.
PIN_ARG_RE = re.compile(r"^(?P<name>[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?)@(?P<commit>[0-9a-fA-F]{40})$")

#: How a neutral product's tree is read when the pin is taken from the forge
#: rather than from a clone on this machine.
GH_TREE_API = "repos/{repo}/git/trees/{commit}?recursive=1"

#: The naming-policy form every link between a chain's first and last must
#: classify as (#251). Each such link is an entry of the link before its
#: `neutral_product_pins:`, the key a link is verified by
#: (`referent.chain.link_declared_by`), so it is a neutral product's name.
CHAIN_LINK_FORM = "neutral-product"


def parse_pin(raw: str, owner: str = NEUTRAL_PRODUCT_OWNER) -> tuple[str, str, str]:
    """`openGlass@<sha>` -> (product, `<owner>/openGlass`, commit).

    THE COMMIT IS 40 HEX OR IT IS NOT A PIN. An abbreviated oid, a branch name
    or a tag cannot pass here for the same reason `contracts/<leg>-pin.yaml`
    refuses them: a tag can be moved and a commit cannot.

    AN UNQUALIFIED NAME RESOLVES UNDER `owner` (opensoft, unless `--pin-owner`
    said otherwise) — NEVER under the pinning project's own `--org`. Domain
    repositories never author a neutral product; they only pin the opensoft
    original, so `--org MedxSoft --pin openGlass@<sha>` must not go looking
    for `MedxSoft/openGlass`, which does not exist and was never the claim.
    """
    match = PIN_ARG_RE.match(raw.strip())
    if not match:
        raise Refusal(
            "pin-malformed",
            f"--pin {raw!r} is not `[owner/]<openProduct>@<40 hex commit>`",
            "Remediation: pass the full 40-character commit, e.g. "
            "--pin openGlass@0123456789abcdef0123456789abcdef01234567 "
            f"(resolved under {NEUTRAL_PRODUCT_OWNER}/openGlass by default), "
            "or name the owner explicitly with --pin MedxSoft/openGlass@<sha> "
            "or --pin-owner MedxSoft. A tag or an abbreviated oid is refused: "
            "a tag can be moved.",
        )
    name = match.group("name")
    product = name.rsplit("/", 1)[-1]
    repository = name if "/" in name else f"{owner}/{product}"
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
        # UTF-8 and STRICT, not `errors="replace"`: this JSON becomes a
        # digest, and a replaced byte would be a wrong digest with a
        # confident tone (#217).
        capture_output=True, text=True, encoding="utf-8", check=False)
    if proc.returncode != 0:
        raise Refusal(
            "pin-unreadable",
            f"`gh api` could not read {repository} @ {commit}: "
            f"{proc.stderr.strip()}",
            "Remediation: check the commit exists in that repository and that "
            "`gh auth status` can see it. An unqualified --pin resolves under "
            f"{NEUTRAL_PRODUCT_OWNER} by default (never the project's own "
            "--org) — if this product actually lives under a different "
            "owner, name it explicitly with --pin <owner>/<openProduct>@<sha> "
            "or --pin-owner <owner>. You can also pass --pin-source <local "
            "clone> to compute the digest with no network at all.",
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
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", check=False)
    if probe.returncode != 0:
        return None
    commits = subprocess.run(
        ["gh", "api", f"repos/{repository}/commits?per_page=1"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False)
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


def remote_visibility(repository: str) -> str | None:
    """`<org>/<repo>`'s GitHub visibility (`private`, `public`, `internal`),
    lowercased, or None if it cannot be read — the repository does not exist,
    or `gh` cannot see it. Never called for a `--local-remote-dir` repository:
    a bare repository on disk has no visibility at all.
    """
    proc = subprocess.run(
        ["gh", "repo", "view", repository, "--json", "visibility"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False)
    if proc.returncode != 0:
        return None
    try:
        value = json.loads(proc.stdout).get("visibility")
    except json.JSONDecodeError:
        return None
    return str(value).lower() if value else None


def local_remote_is_empty(bare: Path) -> bool | None:
    """The same question for a bare repository on disk (the test path)."""
    if not bare.exists():
        return None
    out = subprocess.run(["git", "-C", str(bare), "rev-list", "--count", "--all"],
                         capture_output=True, text=True,
                         encoding="utf-8", errors="replace", check=False)
    if out.returncode != 0:
        raise Refusal("remote-unreadable",
                      f"{bare} exists but is not a git repository")
    return out.stdout.strip() in ("", "0")


def main(argv: list[str] | None = None) -> int:
    # FIRST, so that every `print` after it -- `--help` included -- escapes
    # a name stdout cannot encode rather than raising on it (#214).
    escape_what_stdout_cannot_encode()
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--org", required=True)
    parser.add_argument("--project", required=True,
                        help="the assembly-root name, e.g. Atlas")
    parser.add_argument("--id", default=None, help="lowercase project id")
    parser.add_argument("--name", default=None, help="display name")
    parser.add_argument("--visibility", choices=VISIBILITY_CHOICES,
                        default=None,
                        help="default: private for a fresh scaffold; with "
                             "--reuse-empty-repo and an existing assembly "
                             "root, the two new legs INHERIT that root's own "
                             "visibility instead (a mismatch with an explicit "
                             "--visibility is a warning, not a refusal)")
    parser.add_argument("--pin-owner", default=NEUTRAL_PRODUCT_OWNER,
                        help="the organisation an UNQUALIFIED --pin name "
                             f"resolves under (default: {NEUTRAL_PRODUCT_OWNER}, "
                             "where every neutral open<Product> lives — never "
                             "this scaffold's own --org). Name the owner in "
                             "--pin itself (owner/openProduct@<sha>) to "
                             "override it for one pin without changing this "
                             "default for the others.")
    parser.add_argument("--elected-by", default=None)
    parser.add_argument("--elected-on", default=None, help="YYYY-MM-DD")
    parser.add_argument("--reference", default=None,
                        help="the document the election followed. Default: "
                             "openxFactory's ratified "
                             "docs/project-repo-schema.md for an election on "
                             "or after 2026-09-02, and the staged fragment it "
                             "was ratified from for one dated earlier — so "
                             "--elected-on chooses it, and a back-dated "
                             "project does not claim it followed a document "
                             "that did not exist yet.")
    parser.add_argument("--tracking-branch", default="main")
    parser.add_argument("--spec-path", default="spec",
                        help="where the spec leg is mounted, as a path in "
                             "the assembly root (default: spec). A path that "
                             "is, holds or lies inside a FILE the shape "
                             "writes into the root is refused before anything "
                             "is created: `project.yaml` is one, and "
                             "`contracts` holds several.")
    parser.add_argument("--code-path", default="code",
                        help="where the code leg is mounted, as a path in "
                             "the assembly root (default: code). A path that "
                             "is, holds or lies inside a FILE the shape "
                             "writes into the root is refused before anything "
                             "is created: `project.yaml` is one, and "
                             "`contracts` holds several.")
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
                             "than a name shaped like one. Repeatable, "
                             "once per product (the same name in another "
                             "case, or under another owner, is the same "
                             "product).")
    parser.add_argument("--referent-chain", default="",
                        metavar="openLayer,openProduct",
                        help="the CHAIN of neutral-product pins this project "
                             "reaches its referent through, e.g. "
                             "--referent-chain openXdox,openDox. Its first "
                             "entry must be one of the --pin products (the "
                             "pin this project actually holds), its last "
                             "must be the `open<Product>` the name claims, "
                             "and every link between them must be a neutral "
                             "product's name (`open<Product>`, e.g. "
                             "openXdox); the manifest RECORDS it, which is "
                             "what makes a descendant that pins a LAYER a "
                             "descendant (2026-09-05).")
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
        product, repository, commit = parse_pin(raw, args.pin_owner)
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


def declared_pin_products(args) -> dict[str, None]:
    """The products `declared_pin_values` keys its pins by, in its order and
    read by the same `parse_pin`, with no digest: so no `git` and no `gh`.

    #197: `_build_assembly_root` hands those pins to the materializer, which
    writes `neutral_pin_path(product)` for each, and the leg paths are asked
    about that file before `_identity` and `_declaration` run, which is
    before any digest is read. A malformed `--pin` is therefore refused
    here, by `parse_pin`'s own `pin-malformed`, rather than in
    `_declaration`; it was refused before anything was created either way.
    """
    return dict.fromkeys(parse_pin(raw, args.pin_owner)[0] for raw in args.pin)


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


#: What every refused `--pin` is told to do. The file a pin is written at is
#: `neutral_pin_path`'s, spelled for a placeholder product, never by hand. It
#: names `spec`, `code` and `shape` outright (#288): for a repository truly
#: called one of them, "name the product for the repository it pins" is no
#: remedy at all, because no spelling of that name can be pinned.
PIN_COLLISION_REMEDIATION = (
    "Remediation: nothing was created. A neutral product is named for the "
    "repository it pins, as `--pin openGlass@<40 hex commit>` names "
    f"{NEUTRAL_PRODUCT_OWNER}/openGlass by default, and its pin is written at "
    f"`{neutral_pin_path('<openProduct>')}`, the name lowercased, beside the "
    "pins the shape writes for its two legs and for itself, so `spec`, `code` "
    "and `shape`, in any case, are names no product can be pinned under. Pass "
    "each product once, by the name of the repository it pins."
)


def _refuse_colliding_pins(pins, owner: str) -> None:
    """No `--pin` is written where the shape writes a file of its own, and no
    two `--pin`s are written at one path, or this refuses (#241).

    `_build_assembly_root` hands the pins to the materializer, which writes
    each at `neutral_pin_path(product)` after the shape's own files and
    before the copy pin, and a second file at one path is
    `materialize-collision`: a pin over a leg's pin, or the copy pin over a
    pin named `shape`, or a pin over another pin. So each was met only after
    `_create_remotes` and `_seed_legs`. On main through 39ac59c, `--pin
    spec@<sha>` (`Spec@`, `code@`, `MedxSoft/code@`, `shape@`) and `--pin
    openGlass@<sha> --pin OpenGlass@<sha>` planned under `--dry-run`, then
    created all three repositories, pushed both legs, left the root with no
    commit and exited 2, and the corrected re-run was refused as
    `scaffold-remote-exists`. Against GitHub, each left three repositories
    for a run that made no project.

    THE QUESTION IS ASKED THROUGH THE MATERIALIZER'S OWN TWO DEFINITIONS: a
    pin's file is `neutral_pin_path(product)`, and the shape's own files are
    `assembly_root_paths()` with no pins. `neutral_pin_path` lowercases, so
    `Spec` is `spec` and `openGlass` and `OpenGlass` are one file, with no
    case rule of this tool's own. The product is read by `parse_pin` alone,
    so a malformed `--pin` is still its `pin-malformed`, and no digest is
    read: no `git` and no `gh`.

    THE RAW `--pin` LIST, NEVER `declared_pin_products`, which collapses a
    repeated product, as `declared_pin_values` does by keeping the last:
    `--pin openGlass@<A> --pin openGlass@<B>` planned one pin, wrote `<B>`
    and dropped `<A>` without a word. A declaration is a claim about what
    the project descends from, so a repeat is refused whether or not its
    commits agree: either way it is a typing error, and one of the two
    would be lost. Every argument is named as it was typed.

    IT RUNS BEFORE `_refuse_colliding_leg_paths`, which asks about
    `assembly_root_paths(<the --pin products>)`. With `--pin spec@<sha>`
    that list held `contracts/spec-pin.yaml` twice, and `--spec-path
    contracts` was told it contains that file "and 4 more" where there
    were three (#197's re-review, N1). Refused first, no pin path it lists
    is the shape's or listed twice.
    """
    # Folded on both sides, as `path_overlap` folds the leg paths: a future
    # mixed-case shape file under `contracts/` is still one path with a
    # lowercased pin on the case-insensitive disk of macOS and Windows.
    shape_files = {shape_file.casefold()
                   for shape_file in assembly_root_paths()}
    written: dict[str, list[tuple[str, str]]] = {}
    for raw in pins:
        product = parse_pin(raw, owner)[0]
        path = neutral_pin_path(product)
        written.setdefault(path, []).append((raw, product))
    collisions = []
    for path, typed in written.items():
        in_shape = path.casefold() in shape_files
        if not in_shape and len(typed) == 1:
            continue
        products = list(dict.fromkeys(product for _, product in typed))
        said = (" and ".join(f"--pin {raw!r}" for raw, _ in typed)
                + (" writes the pin" if len(typed) == 1 else " write the pins")
                + " of the product" + ("s" if len(products) > 1 else "") + " "
                + " and ".join(f"`{product}`" for product in products))
        if in_shape:
            collisions.append(
                f"{said} at `{path}`, a file the shape writes into the "
                "assembly root itself: name the product for the repository it "
                "pins.")
        else:
            collisions.append(
                f"{said} at one file, `{path}`, which holds one pin: pass "
                "each product once.")
    if collisions:
        raise Refusal("scaffold-pin-collides", " ".join(collisions),
                      PIN_COLLISION_REMEDIATION)


def _leg_collision_remediation(neutral_pins=()) -> str:
    """What a leg-path collision tells the person to do. The paths are
    `assembly_root_paths(neutral_pins)`, the materializer's own list for this
    run, never a copy of it: each `--pin` adds the file it writes."""
    return (
        "Remediation: nothing was created, and nothing here picks a path for "
        "you, so pass another one yourself. A leg path neither is, holds nor "
        "lies inside, whatever the case, a path the shape writes into the "
        "assembly root ("
        + ", ".join(f"`{path}`" for path in assembly_root_paths(neutral_pins))
        + "). The defaults `spec` and `code` pass."
    )


def _refuse_colliding_leg_paths(spec_path: str, code_path: str,
                                neutral_pins=()) -> None:
    """Neither leg is mounted over a path the shape writes into the assembly
    root, or this refuses (#197).

    `_build_assembly_root` writes the shape into the root FIRST and mounts
    the legs after it, so a leg path the shape had just written was met only
    by `git submodule add`. On main through 20e13f0, `--spec-path contracts`
    and `--code-path project.yaml` planned under `--dry-run`, then created
    all three repositories, pushed both legs, left the root empty and exited
    2 (`'contracts' already exists and is not a valid git repo`).
    `--code-path Makefile/code` died the same way, and `--spec-path
    Contracts` exited 0 with a gitlink beside the shape's `contracts/`,
    which a macOS or Windows disk keeps as one path. Against GitHub, each
    left three repositories for a run that made no project.

    THE QUESTION IS `adopt-project.py`'s (#172), asked through the one
    definition both tools import: `shape_path_collisions` over
    `assembly_root_paths(neutral_pins)`, so a file the shape gains is
    refused here without anybody editing this tool. It is asked with no
    collision directory, because the scaffold hands the materializer none
    and writes nothing under adopt's `shape/`.

    A `--pin` IS ONE MORE PATH. `_build_assembly_root` hands the materializer
    `neutral_pins=pins`, which writes `neutral_pin_path(product)` for each,
    so `neutral_pins` is those products (`declared_pin_products`) and they
    are asked about with the rest. Without them, `--pin openGlass@<sha>
    --spec-path contracts/openglass-pin.yaml` planned and then made three
    repositories, and `Contracts/OpenGlass-pin.yaml` exited 0 with a gitlink
    beside the pin, one path on a macOS or Windows disk. With no `--pin`,
    `contracts/openglass-pin.yaml` lies inside a directory the shape writes
    into, not a path it writes, and it mounts. `_refuse_colliding_pins` runs
    first (#241), so each pin's path is listed once and is none of the
    shape's own, and a count here counts distinct paths.
    """
    collisions = [sentence
                  for what, value in (("--spec-path", spec_path),
                                      ("--code-path", code_path))
                  for sentence in shape_path_collisions(
                      what, value, neutral_pins=neutral_pins)]
    if collisions:
        raise Refusal("scaffold-leg-path-collides", " ".join(collisions),
                      _leg_collision_remediation(neutral_pins))


def _elector(args) -> str:
    """(a) Whose act electing this shape was, or a refusal.

    Split out of `_scaffold` for #138. `--elected-by` first, then this
    machine's git identity; the manifest records a name either way, because
    electing this shape is a human's act and `elected_by` is the record of
    whose.
    """
    elected_by = args.elected_by
    if not elected_by:
        try:
            # Per-invocation identity first, then the config — never a global
            # config write (see the CI workflow note, 2026-09-03).
            elected_by = (os.environ.get("GIT_AUTHOR_NAME") or "").strip() or git_out(["config", "user.name"], cwd=SHAPE_ROOT)
        except Refusal:
            elected_by = ""
    if not elected_by:
        raise Refusal(
            "scaffold-no-elector",
            "no --elected-by, no GIT_AUTHOR_NAME and no `git config user.name`. Electing this "
            "shape is a human's act and the manifest records whose.",
            "Remediation: re-run with --elected-by 'Your Name'.",
        )
    return elected_by


def _identity(args, project: str) -> tuple[str, str, str, str, str]:
    """(b) Who this project is and who elected the shape for it, from the
    defaults its flags fall back to: `(project_id, display, elected_on,
    reference, elected_by)`.

    Split out of `_scaffold` for #138, and the ORDER inside it is load-bearing.
    `--elected-on` is PARSED HERE, before anything is created, whether or not
    it is the value that chooses the reference: an explicit --reference must
    not let a malformed --elected-on through into a manifest field no reader
    can use.
    """
    project_id = checked_value("--id", args.id or project.lower())
    display = args.name or project
    elected_on = args.elected_on or _dt.date.today().isoformat()
    election_date(elected_on)
    reference = args.reference or default_reference(elected_on)
    return project_id, display, elected_on, reference, _elector(args)


def referent_chain_links(raw: str) -> tuple:
    """`--referent-chain`'s links: split on commas, each stripped, an empty
    one dropped. ONE reading, for `_declaration` and for the check below, so
    the links that are judged are the links that are recorded."""
    return tuple(link.strip() for link in raw.split(",") if link.strip())


def _refuse_malformed_chain_links(policy, chain: tuple) -> None:
    """Every link between the chain's first and last is a neutral product's
    name, or this refuses (#251).

    `naming_block` writes the chain into `project.yaml` as a plain flow
    sequence, `[openXdox, openDox]`, and nothing else looked at a MIDDLE
    link: `_chain_shape_problem` asks the length, a repeat, the first link and
    the last, and a link whose tree is not on the disk is declared-unverified,
    a warning. On main through 150c41d, `--referent-chain openXdox,a #b,openDox`
    created all three repositories, pushed both legs and exited 0 with a
    manifest the project's own `validate-manifest.py` refused as
    `yaml-unparsable` (the `#` began a comment), and `it's`, `a]b`, `null` and
    `007` were each recorded as a different chain than the one typed.

    THE NAMING POLICY ALREADY SAYS WHAT A LINK IS. Each link past the first is
    read out of the link before its `neutral_product_pins:`, so it is the
    name of a neutral product, and `CHAIN_LINK_FORM` is that family. A name of
    that form is one plain YAML word, so the manifest stays plain and reads
    back as typed. The link is judged at its basename, as `resolve_referent`
    reads it and `naming_block` records it.

    The FIRST and LAST links are left to the checks that already anchor them:
    the first must be a `--pin` product and the last the referent the name
    claims, both compared casefolded because a pin names WHICH repository, not
    how it was typed. Each must casefold to a name this run already holds
    (`[A-Za-z0-9_.-]`, or `open<Product>`), so neither can carry a `#`, a
    quote, a bracket, a comma or a space.

    Asked before `_declaration`, so before `gh api` reads a pin's tree and
    before `--dry-run` returns: a dry run refuses exactly as the real run
    does, and nothing has been created.

    The chain and each bad link are quoted with `repr`, as `--pin` and `--id`
    are in their refusals: a link is the operator's own argument, and one
    that holds a newline, a carriage return or an escape byte prints as
    `\\n`, `\\r` or `\\x1b`, so it cannot end the refusal's line and start
    another that reads as a refusal of its own.
    """
    malformed = [link for link in chain[1:-1]
                 if CHAIN_LINK_FORM not in {family for family, _role
                                            in policy.matches(
                                                repo_basename(link))}]
    if not malformed:
        return
    form = (policy.family(CHAIN_LINK_FORM) or {}).get("pattern", "")
    raise Refusal(
        "chain-link-malformed",
        f"--referent-chain {','.join(chain)!r}: "
        + ", ".join(repr(link) for link in malformed)
        + (" is not" if len(malformed) == 1 else " are not")
        + " the name of a neutral product. Every link between the first and "
        "the last is a product the link before it pins, and the manifest "
        "records each one as a name.",
        "Remediation: nothing was created. Spell each link between the first "
        "and the last as the neutral product's repository name, "
        f"`open<Product>` (the naming policy's `{form}`, e.g. openXdox). "
        "`validate-repository-naming.py --explain <link>` says which form a "
        "name is.")


def _declaration(args) -> tuple[dict, set, tuple, dict]:
    """(c) What the project DECLARES about itself: `(pins, declared_pins,
    chain, link_pins)`.

    Split out of `_scaffold` for #138. THE RECORDED CHAIN (2026-09-05):
    `codexDox` pins `openXdox` and reaches `openDox` through it; the chain is a
    DECLARATION, so it is checked by `_check_declared_names` below and written
    into the manifest rather than re-derived by every reader. A link is
    verified against its own tree when `--pin-source` (or
    `SHAPE_PIN_SOURCE_<PRODUCT>`) points at one, and is declared-unverified
    otherwise — a warning, never a refusal, because the check is offline.

    A tree `--pin-source` reached whose declaration could not be read (a
    `neutral_product_pins:` that is not a list of names) is declared-unverified
    too, and the warning says that tree could not be READ, with why, rather
    than that it "is not reachable here" (#338): the scaffold prints no other
    line about a source, so `with_reasons` is asked for here.
    """
    pins = declared_pin_values(args)
    declared_pins: set[str] = set(pins)
    chain = referent_chain_links(args.referent_chain)
    link_pins = link_pins_from_trees(chain, None, {}, args.pin_source,
                                     with_reasons=True) if chain else {}
    return pins, declared_pins, chain, link_pins


def _check_referent_chain(policy, assembly_name: str, declared_pins: set,
                          chain: tuple, link_pins: dict) -> None:
    """(d) A declared `--referent-chain` reaches the referent the name claims,
    or this refuses. Split out of `_scaffold` for #138.
    """
    if not chain:
        return
    resolution = policy.resolve_referent(assembly_name, declared_pins,
                                         chain, link_pins)
    if resolution.status == "broken":
        raise Refusal(
            "chain-not-declared",
            f"--referent-chain {','.join(chain)}: {resolution.reason}",
            "Remediation: the first entry is the product this project "
            "PINS (pass it as --pin <product>@<40 hex>) and the last is "
            "the `open<Product>` the name claims; every link between them "
            "is declared by that link's own project.yaml.")
    for warning in resolution.warnings:
        print(f"WARNING {warning}", file=sys.stderr)


def _check_one_name(policy, name: str, role: str, declared_pins: set,
                    chain: tuple, link_pins: dict) -> None:
    """(e) ONE of the three names classifies as a form its role accepts, or
    this refuses. Split out of `_scaffold` for #138.
    """
    found = policy.classify(name, role, declared_pins,
                            chain if role == "assembly" else (), link_pins)
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


def _check_declared_names(policy, names: dict, declared_pins: set,
                          chain: tuple, link_pins: dict) -> None:
    """(d+e) The chain, then each of the three names. Split out of `_scaffold`
    for #138; the chain is judged first because a broken one makes every
    classification under it meaningless.
    """
    _check_referent_chain(policy, names["assembly"], declared_pins, chain,
                          link_pins)
    for role, name in names.items():
        _check_one_name(policy, name, role, declared_pins, chain, link_pins)


def _shape_revision() -> tuple[str, str]:
    """(f) The shape revision this project is cut from: `(commit, tree)`.

    Split out of `_scaffold` for #138. A DIRTY checkout still scaffolds — the
    per-file sha256 rows are computed from the actual copies, so drift stays
    detectable — but it says so, loudly, because `commit:` and `tree_sha256`
    would then describe bytes nobody copied.
    """
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
    return shape_commit, shape_tree


def _repository_urls(args, names: dict) -> tuple[bool, dict, dict]:
    """(g) The three repositories as the forge — or the disk — names them:
    `(local, repositories, urls)`.

    Split out of `_scaffold` for #138. `local` is `--local-remote-dir`, the
    TEST path: three bare repositories in a directory, and no network.
    """
    local = args.local_remote_dir is not None
    if local:
        remote_dir = args.local_remote_dir.resolve()
        urls = {role: str(remote_dir / f"{name}.git")
                for role, name in names.items()}
    else:
        urls = {role: f"https://github.com/{args.org}/{name}.git"
                for role, name in names.items()}
    repositories = {role: f"{args.org}/{name}" for role, name in names.items()}
    return local, repositories, urls


def _leg_visibility(args, assembly_repository: str, local: bool) -> str:
    """(h) The visibility the two NEW legs are created at: explicit, or
    inherited from a reused empty root.

    Split out of `_scaffold` for #138. An organisation that created the
    assembly root first (--reuse-empty-repo) generally wants the two NEW legs
    to match what it already is, not the tool's own idea of a default. Reading
    it costs one `gh repo view`, is skipped entirely for --local-remote-dir (a
    bare repository on disk has no visibility at all) and for a fresh scaffold
    with nothing to reuse.
    """
    reused_visibility = None
    if args.reuse_empty_repo and not local:
        reused_visibility = remote_visibility(assembly_repository)
    if args.visibility is None:
        if reused_visibility:
            print(f"NOTE {assembly_repository} is already {reused_visibility} "
                  "on GitHub; the two new legs inherit that visibility (pass "
                  "--visibility to choose one explicitly).")
        return reused_visibility or "private"
    if reused_visibility and reused_visibility != args.visibility:
        print(f"WARNING --visibility {args.visibility} disagrees with the "
              f"reused {assembly_repository}, which is {reused_visibility} "
              "on GitHub. The two new legs are created "
              f"{args.visibility} because that is what you asked for, not "
              "because it is what the assembly root already is.",
              file=sys.stderr)
    return args.visibility


def _print_plan(args, values: dict, names: dict, repositories: dict,
                urls: dict, local: bool, policy, declared_pins: set,
                chain: tuple, link_pins: dict, pins: dict) -> None:
    """(i) The plan a human reads before they type yes.

    Split out of `_scaffold` for #138, in three parts — this one, the declared
    classification and the actions — because the plan is the ONE output of
    this tool that somebody is asked to act on, and a printer that no longer
    fits on a screen is a printer nobody proof-reads.
    """
    print(f"project      {values['PROJECT_NAME']} ({values['PROJECT_ID']})   "
          f"topic {values['TOPIC']}")
    # THE TRIAD, OFFERED FIRST (openxFactory `prefer-triad-project-shape`,
    # ratified by Brett Heap on 2026-10-06). This tool has no
    # single-repository mode -- every run creates an assembly root and two
    # legs -- so the offer is the tool itself, and the plan a person reads
    # before typing yes names it as the preferred shape with the posture
    # beside it. Printed once, in a dry run and a real one alike; it changes
    # nothing this run does and no exit code.
    first, second = scaffold_lines()
    print(f"triad        {first}")
    print(f"             {second}")
    print(f"shape        {SHAPE_REPOSITORY} @ {values['SHAPE_COMMIT'][:12]} "
          f"(tree {values['SHAPE_TREE_SHA256'][:12]}…)")
    print(f"elected by   {values['ELECTED_BY']} on {values['ELECTED_ON']}")
    print(f"reference    {values['REFERENCE']}"
          + ("" if args.reference else "   (chosen by the election date)"))
    for role in ("assembly", "spec", "code"):
        print(f"  {role:<9} {repositories[role]:<28} -> {urls[role]}")
    for role in ("assembly", "spec", "code"):
        note = descendant_note(policy, names[role], role, declared_pins,
                               chain if role == "assembly" else ())
        if note:
            print(note)
    print(f"legs mounted at {args.spec_path}/ and {args.code_path}/ inside "
          f"{names['assembly']}")
    for product, pin_values in pins.items():
        print(f"pin          {pin_values['PIN_REPOSITORY']} @ "
              f"{pin_values['PIN_COMMIT'][:12]} tree "
              f"{pin_values['PIN_TREE_SHA256'][:12]}… -> "
              f"{neutral_pin_path(product)} ({pin_values['PIN_DIGEST_SOURCE']})")
    _print_declared_classification(policy, names, declared_pins, chain,
                                   link_pins, pins)
    _print_plan_actions(args, values["TOPIC"], local)


def _print_declared_classification(policy, names: dict, declared_pins: set,
                                   chain: tuple, link_pins: dict,
                                   pins: dict) -> None:
    """(i′) What the naming policy makes of the assembly root's own name.

    PRINT THE CLASSIFICATION whenever the root is not an ordinary project-leg
    — a neutral-product or descendant root, pinned or not — so the human
    reading the plan before typing yes sees `neutral-product / assembly` even
    with no `--pin` on the command line (2026-09-05). A pinned root always
    printed this line; what is new is that `openDox` needs no pin to earn one.
    Split out of `_print_plan` for #138.
    """
    found = policy.classify(names["assembly"], "assembly", declared_pins,
                            chain, link_pins)
    if pins or found.family != "project-leg":
        print(f"declared     {names['assembly']} classifies as {found.family}"
              + (f" / {found.role}" if found.role else "")
              + f" — {found.reason}")


def _print_plan_actions(args, topic: str, local: bool) -> None:
    """(i″) The four lines that say what this run will DO — create the
    remotes, reuse an empty root, push, set the topic. Split out of
    `_print_plan` for #138.
    """
    print("remotes      " + ("bare repositories on disk (no network)" if local
                             else f"gh repo create --{args.visibility}"))
    if args.reuse_empty_repo:
        print("reuse        an EXISTING <Project> with zero commits is used as "
              "the assembly root")
    print("push         " + ("SKIPPED (--no-push)" if args.no_push else "yes"))
    print("topics       " + ("skipped for local remotes" if local
                             else f"gh repo edit --add-topic {topic}"))


def _refuse_existing_trees(work_root: Path, names: dict) -> None:
    """(j) Refuse to write over a working tree that already has something in
    it. Split out of `_scaffold` for #138.
    """
    for role, name in names.items():
        target = work_root / name
        if target.exists() and any(target.iterdir()):
            raise Refusal(
                "scaffold-target-exists",
                f"{target} already exists and is not empty",
                "Remediation: choose an empty --work-dir. There is no --force: "
                "re-running over a live tree is not a scaffold.",
            )


def _create_remotes(args, values: dict, repositories: dict, urls: dict,
                    local: bool, reused: set) -> None:
    """(k) The three remotes, spec and code first so a failure costs the
    cheapest thing. Split out of `_scaffold` for #138.

    It takes no `names`: every line here addresses a repository by the
    `<org>/<name>` the forge knows it as, or by its clone URL, and the bare
    name is not one of the things it needs.
    """
    display = values["PROJECT_NAME"]
    project_id = values["PROJECT_ID"]
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


def _private_leg_note(args, repositories: dict, local: bool) -> None:
    """(k′) A private or internal leg is unreadable to the `validate`
    workflow's default GITHUB_TOKEN — the defect on the first real adoption
    (MedxSoft/MedxEHR #7). Printed once, after both legs are known to have
    been created at this visibility, rather than per-leg. Split out of
    `_scaffold` for #138.
    """
    if not local and args.visibility in ("private", "internal"):
        print(f"NOTE {repositories['spec']} and {repositories['code']} are "
              f"{args.visibility}: give {repositories['assembly']} a way to "
              "read them — a GitHub App (SHAPE_LEGS_APP_ID + "
              "SHAPE_LEGS_APP_PRIVATE_KEY, preferred) or a SHAPE_LEGS_TOKEN "
              "PAT (contents:read on the legs, fallback) — or the `validate` "
              "check cannot check them out.")
        hint = free_plan_secret_hint(
            args.org, repositories["assembly"],
            f"{repositories['spec']} and {repositories['code']} are")
        if hint:
            print(hint)


def _seed_legs(args, values: dict, names: dict, repositories: dict,
               urls: dict, work_root: Path) -> dict | None:
    """(l) The two legs: template, one commit, push.

    Returns the four template values the assembly root's own templates name —
    or None when a push was REFUSED, having already said so on stderr and
    printed the ruleset hint. Split out of `_scaffold` for #138.
    """
    display = values["PROJECT_NAME"]
    shape_commit = values["SHAPE_COMMIT"]
    leg_commits: dict[str, str] = {}
    leg_digests: dict[str, str] = {}
    for role, template in (("spec", "spec-root"), ("code", "code-root")):
        work = work_root / names[role]
        written = copy_tree(SHAPE_ROOT / "templates" / template, work, values)
        commit = git_init_commit(
            work, f"Seed the {role} leg of {display}\n\n"
                  f"Scaffolded from {SHAPE_REPOSITORY} @ {shape_commit}.",
            args.tracking_branch, written)
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
                return None
        print(f"  {role:<9} {commit[:12]} tree {leg_digests[role][:12]}… "
              f"-> {urls[role]}")
    return {
        "SPEC_COMMIT": leg_commits["spec"],
        "CODE_COMMIT": leg_commits["code"],
        "SPEC_TREE_SHA256": leg_digests["spec"],
        "CODE_TREE_SHA256": leg_digests["code"],
    }


def _build_assembly_root(args, values: dict, names: dict, repositories: dict,
                         urls: dict, pins: dict, work_root: Path) -> bool:
    """(m) The assembly root: manifest, the two legs mounted, three pins.

    Returns False when the push was REFUSED, having already said so on stderr
    and printed the ruleset hint. Split out of `_scaffold` for #138.
    """
    display = values["PROJECT_NAME"]
    shape_commit = values["SHAPE_COMMIT"]
    assembly = work_root / names["assembly"]
    assembly.mkdir(parents=True, exist_ok=True)
    # ONE materializer, shared with `adopt-project.py`. The scaffold builds
    # into a directory it made itself, so a collision here is a defect and
    # `collision_dir=None` says so by raising.
    materialized = materialize_assembly_root(SHAPE_ROOT, assembly, values,
                                             neutral_pins=pins)

    # NO TEMPLATE (#229). `git init` copies the operator's template
    # (`init.templateDir`, or `GIT_TEMPLATE_DIR`) into `.git`, and one that
    # holds a `modules/<leg path>` store, as a copy of a working Triad root's
    # `.git` does, plants `.git/modules/<leg path>`. `git submodule add
    # --force` below REACTIVATES a store that is already there ("Reactivating
    # local git directory") where it would refuse without `--force`, so the
    # mount took the STRANGER's store: exit 0, a pushed root whose gitlink is
    # that store's commit and not the leg's tip, and a recursive clone that
    # fails. The empty `--template=` is git's documented way to use none. The
    # root is a build directory this tool fills and pushes, so no template
    # content belongs in it, and whoever clones the pushed root still gets
    # their template from `git clone`.
    run(["git", "init", "-q", "--template=", "-b", args.tracking_branch,
         str(assembly)])
    # `git submodule add` from the LEG WORKING TREE, then the recorded URL is
    # rewritten to the canonical remote: this way the scaffold never depends on
    # a push having propagated, and `--no-push` produces the same tree.
    for role, path in (("spec", args.spec_path), ("code", args.code_path)):
        # `--force`, git's documented way past an ignore rule (git's flag, not
        # one of this tool's: it still has none), for the reason
        # `stage_written` forces what the materializer wrote (#175). The root
        # is a fresh `git init` the materializer has just filled, so two sets
        # of rules reach the MOUNT PATH: the shape's own `.gitignore`, copied
        # into the root (`__pycache__/`, `*.py[cod]`, `.venv/`, `.DS_Store`),
        # and the operator's own excludes. A path either matches (`__pycache__`
        # as `--code-path`, or the DEFAULT `spec` under a global
        # `core.excludesFile` that names it) was refused HERE, after
        # `_create_remotes` and `_seed_legs` had made all three repositories
        # and pushed both legs: three repositories and no project, a corrected
        # re-run met `scaffold-remote-exists`, and `--dry-run`, which asks no
        # ignore rule anything, had planned it (#229; #174 and #200 for the
        # same cure in `adopt-project.py`). A gitlink once added is TRACKED,
        # so no rule touches it again.
        # Besides the ignore rule, `--force` changes three things in git 2.43,
        # and none can arise here, so there is no guard like adopt's
        # `_refuse_an_unmountable_path`:
        #   - a `.git/modules/<path>` already there is REACTIVATED instead of
        #     refused. `_refuse_existing_trees` refuses a
        #     `<work-dir>/<assembly>` that is not empty, so no `.git` was
        #     there when the run began, and the root is `git init`ed with no
        #     template (above), so `.git/modules` holds nothing before the
        #     first mount and only that mount's store at the second.
        #   - a GITLINK the index already holds at the path is accepted
        #     instead of refused, and a repository already checked out there
        #     is REUSED instead of the leg cloned. (A regular file or a
        #     tracked directory there is refused either way.)
        #     When the second mount runs, the index holds `.gitmodules` and
        #     the first gitlink and nothing else (the materialized files are
        #     staged after both, `stage_written`). No leg path can be
        #     `.gitmodules`, which `refuse_bad_leg_paths` refuses (#201), and
        #     the two paths are different and not nested, whatever the case
        #     (#169, #179), so the second add meets neither.
        #   - git's early dry run of the path is skipped. That dry run is what
        #     refuses a path beyond a symlink or inside a submodule before
        #     anything is cloned. With `--force` git still refuses both, but
        #     later: a path beyond a symlink only at the last step, after the
        #     leg has been cloned into the link's target. The materializer
        #     writes only regular files, and a mount inside the other is the
        #     nesting that was just refused.
        # A leg AT a path the shape wrote (`contracts`, `project.yaml`) is a
        # collision of another kind: refused up front by the collision check
        # where there is one, and by git at the mount where there is not.
        # `--force` changes neither.
        run(["git", "-c", "protocol.file.allow=always", "submodule", "add",
             "--force", "-q", str(work_root / names[role]), path],
            cwd=assembly)
        run(["git", "config", "-f", ".gitmodules", f"submodule.{path}.url",
             urls[role]], cwd=assembly)
        run(["git", "remote", "set-url", "origin", urls[role]],
            cwd=assembly / path)
    run(["git", "submodule", "sync", "-q"], cwd=assembly)
    # Every file the materializer wrote is FORCED past the operator's own
    # excludes (#175); see `stage_written`.
    stage_written(assembly, materialized.written)
    env_commit(assembly,
               f"Scaffold {display}: manifest, two legs, three pins\n\n"
               f"Shape {SHAPE_REPOSITORY} @ {shape_commit}.\n"
               f"spec {values['SPEC_COMMIT']}\ncode {values['CODE_COMMIT']}")
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
            return False
    print(f"  assembly  {run(['git', 'rev-parse', 'HEAD'], cwd=assembly)[:12]} "
          f"-> {urls['assembly']}")
    return True


def _set_topics(repositories: dict, topic: str, local: bool) -> None:
    """(n) The `xf-project-<id>` topic, on all three. Skipped entirely for
    `--local-remote-dir`: a bare repository on disk has no topics. Split out
    of `_scaffold` for #138.
    """
    if local:
        return
    for role in ("assembly", "spec", "code"):
        run(["gh", "repo", "edit", repositories[role], "--add-topic", topic])
    print(f"  topic     {topic} set on all three")


def _scaffold(args) -> int:
    """The whole act, as the phases above, in the order they must happen.

    NOTHING IS CREATED until every name has been judged and the plan has been
    printed, which is what makes `--dry-run` an honest rehearsal: the refusals
    a real run would raise are raised by a dry run too.
    """
    # VALIDATED BEFORE ANYTHING IS BUILT FROM THEM. These five reach a `git`
    # or `gh` command line, and `checked_value` refuses a leading `-` because
    # git reads its own arguments. The naming policy checks what a project
    # name MEANS a few lines below; this checks what it may CONTAIN.
    project = checked_value("--project", args.project)
    args.tracking_branch = checked_value("--tracking-branch",
                                         args.tracking_branch)
    # The leg paths are asked the ONE question `adopt-project.py` asks of its
    # own -- canonical, mountable, two different places, then the alphabet
    # `checked_value` allows -- BEFORE `checked_value` is asked alone, because
    # it lets `spec/` through: Git records that mount at `spec` while the
    # `.gitmodules` write in `_build_assembly_root` names a second section,
    # `spec/`, so the project's recursive clone fails once this work
    # directory is gone (#179). Asked first, the answer for `legs\spec` is the
    # spelling to retype, where the alphabet check alone would only say no.
    # Refused before a work directory or a remote exists, and by `--dry-run`.
    spec_leg = ("--spec-path", args.spec_path)
    code_leg = ("--code-path", args.code_path)
    refuse_bad_leg_paths("scaffold-bad-leg-path", spec_leg, code_leg)
    args.spec_path = checked_value(*spec_leg)
    args.code_path = checked_value(*code_leg)
    args.org = checked_value("--org", args.org)
    args.pin_owner = checked_value("--pin-owner", args.pin_owner)
    # EACH `--pin`'S FILE AGAINST THE SHAPE'S OWN AND AGAINST EACH OTHER, from
    # the arguments as typed (#241), and first: the leg-path question below
    # asks about every pin's file, and would miscount one written over the
    # shape's or listed twice. Here for the reasons the leg paths are, so a
    # dry run refuses it too and no process has been started.
    _refuse_colliding_pins(args.pin, args.pin_owner)
    # THE LEG PATHS AGAINST THE SHAPE'S OWN, before anything else runs
    # (#197): `_identity` may read git's config, `_declaration` asks `gh api`
    # for a `--pin` with no `--pin-source`, `_leg_visibility` asks `gh repo
    # view` about a reused root, and `--dry-run` returns only after all of
    # them. Refused here, a dry run refuses exactly as the real run would,
    # and no process has been started. Each `--pin`'s file is among the
    # shape's paths, its product read off the argument by `parse_pin` alone.
    _refuse_colliding_leg_paths(args.spec_path, args.code_path,
                                declared_pin_products(args))
    project_id, display, elected_on, reference, elected_by = _identity(
        args, project)

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
    # carries the two legs. Since 2026-09-05 an `open<Product>` MAY be that
    # root too: a neutral product may ELECT the shape (Brett Heap, "elect the
    # shape for both, follow the pin chain, no family yet"), and because
    # electing confers nothing, `openDox` mounting `openDox-spec` and
    # `openDox-code` is a fact about layout rather than a claim about
    # neutrality. The form still wins the classification — the manifest records
    # `form: neutral-product, role: assembly` with the leg form in
    # `also_matches` — so nothing here reads a neutral product as a leg.
    #
    # What is still refused is a real mismatch: a `-spec` name offered as the
    # assembly root; an `<X>-Install`, which carries a hyphen and therefore
    # satisfies no leg form at all, offered as ANY leg; and either of the two
    # CamelCase forms offered as the `spec` or `code` leg, because those names
    # carry the lowercase suffix and are ordinary project legs.
    #
    # A chain's middle links are NAMES, judged before `_declaration` asks
    # `gh api` or git for any pin's tree (#251).
    _refuse_malformed_chain_links(policy,
                                  referent_chain_links(args.referent_chain))
    pins, declared_pins, chain, link_pins = _declaration(args)
    _check_declared_names(policy, names, declared_pins, chain, link_pins)
    topic = policy.topic_for(project_id)

    shape_commit, shape_tree = _shape_revision()
    local, repositories, urls = _repository_urls(args, names)
    args.visibility = _leg_visibility(args, repositories["assembly"], local)

    values = {
        "PROJECT": project,
        "PROJECT_ID": project_id,
        "PROJECT_NAME": display,
        "ORG": args.org,
        "TOPIC": topic,
        "VISIBILITY": args.visibility,
        "REFERENCE": reference,
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
                                        declared_pins, chain=chain),
        "SPEC_NAMING": naming_block(policy, names["spec"], "spec", declared_pins),
        "CODE_NAMING": naming_block(policy, names["code"], "code", declared_pins),
    }

    _print_plan(args, values, names, repositories, urls, local, policy,
                declared_pins, chain, link_pins, pins)
    if args.dry_run:
        print("\n--dry-run: nothing was created.")
        return 0

    # ---- refuse to write over anything that already exists ----------------
    work_root = (args.work_dir.resolve() if args.work_dir
                 else Path(tempfile.mkdtemp(prefix="openreposhape-")))
    work_root.mkdir(parents=True, exist_ok=True)
    _refuse_existing_trees(work_root, names)
    # THE ONE REPOSITORY THAT MAY ALREADY EXIST is the assembly root, and only
    # with `--reuse-empty-repo`, and only with ZERO commits. An organisation
    # that creates the repository first and asks for the shape second is the
    # ordinary case, not a mistake; an EMPTY repository is a name that has been
    # reserved, and reserving a name is not starting a project. A repository
    # with commits is refused exactly as before: that is a live project, and
    # `adopt-project.py` is the tool for one of those.
    if local:
        args.local_remote_dir.resolve().mkdir(parents=True, exist_ok=True)
    reused = _reusable_remotes(names, urls, repositories, local,
                               args.reuse_empty_repo)

    _create_remotes(args, values, repositories, urls, local, reused)
    _private_leg_note(args, repositories, local)

    leg_values = _seed_legs(args, values, names, repositories, urls, work_root)
    if leg_values is None:
        return 2
    values.update(leg_values)

    if not _build_assembly_root(args, values, names, repositories, urls, pins,
                                work_root):
        return 2
    _set_topics(repositories, topic, local)

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
