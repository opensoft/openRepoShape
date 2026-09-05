#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Create and maintain a FAMILY: a holder that pins member assembly roots.

    ./scripts/family.py init   --org <org> --family <Name> [--dry-run]
    ./scripts/family.py add    --family-root <path> --member <org>/<Project>
    ./scripts/family.py bump   --family-root <path> --member <Project> --to <sha>
    ./scripts/family.py remove --family-root <path> --member <Project>

A FAMILY IS NOT A PROJECT, and this is a ruling (Brett Heap, 2026-09-04), made
about InkRouter:

    "InkRouter is a set of microservices and they deploy separately as api's.
     so maybe they each need their own assembly repo. So probably InkRouter is
     only something that can download all the others easily? like a holder
     folder and some utilities for the family of services. Then IRRS would be
     assembly and IRRS-spec and IRRS-code."

So a family holder has NO spec leg and NO code leg. It pins other projects'
ASSEMBLY ROOTS as submodules under `members/`, and carries the utilities to
fetch and bootstrap them together. Each member is a whole project — three
repositories, its own gate, its own release — and stays one whether or not a
family names it.

IT CONFERS NOTHING, exactly as the three-repository shape confers nothing.
Membership is navigation. Nothing here grants review authority, clearance
eligibility, gate standing or lifecycle state, and a project in no family is
reviewed identically to one in this family. A consumer deriving a permission
from membership is defective.

THE SAME DOUBLE PIN. A member is pinned twice, in ONE commit: by the gitlink
git records at `members/<Project>`, and by `members[].pin` in `family.yaml` —
the 40-hex commit plus a `sorted-ls-tree-r-v1` tree digest, the same
definition every other pin in this standard uses. `add`, `bump` and `remove`
each write exactly one commit, with explicit pathspecs, moving both together;
`validate-family.py` refuses when they disagree.

WHY A HOLDER AND NOT A BIGGER PROJECT. Eight services that deploy separately
as APIs are eight projects. Folding them into one assembly root would give
them one gate, one release and one pin — which is the opposite of what
"deploy separately" means. The family is the cheapest thing that answers the
only question the estate actually had: how does somebody clone all of them.

EXIT CODES: 0 done · 1 nothing (a dry run prints and exits 0) · 2 a refusal.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SHAPE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHAPE_ROOT / "scripts"))
from repo_shape import (  # noqa: E402
    free_plan_secret_hint,
    COMMIT_RE, PROJECT_ID_RE, PYTHON, TREE_DIGEST_DEFINITION,
    VISIBILITY_CHOICES, NamingPolicy, Refusal, checked_value, git_out,
    load_yaml, recorded_gitlink, repo_basename, tree_digest,
)
from shape_materialize import (  # noqa: E402
    RULESET_HINT, SHAPE_REPOSITORY, CommandFailed, check_program, env_commit,
    materialize_family_root, run, write_lf,
)

NAMING_POLICY = SHAPE_ROOT / "contracts" / "repository-naming.yaml"
MANIFEST = "family.yaml"
MEMBERS_DIR = "members"
FILE_PROTOCOL = ["-c", "protocol.file.allow=always"]

#: `<org>/<Project>`, the only spelling `--member` accepts. A bare name would
#: have to guess an owner, and a family whose members are in another
#: organisation is an ordinary case (an estate's neutral products are).
MEMBER_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


# ---------------------------------------------------------------------------
# family.yaml: reading it, and rewriting the members block
# ---------------------------------------------------------------------------


class Family:
    """A family root on disk: its manifest, its members, and where it is."""

    def __init__(self, root: Path, data: dict):
        self.root = root
        self.data = data
        self.path = root / MANIFEST

    @classmethod
    def open(cls, root_spec) -> "Family":
        root = Path(root_spec).expanduser().resolve()
        path = root / MANIFEST
        if not path.is_file():
            raise Refusal(
                "family-root-missing",
                f"{path} does not exist, so this is not a family root",
                "Remediation: `family.py init --org <org> --family <Name>` "
                "creates one. A PROJECT is scaffolded with "
                "`scaffold-project.py` and adopted with `adopt-project.py`; "
                "neither of those is a family.")
        data = load_yaml(path)
        if not isinstance(data, dict):
            raise Refusal("family-unreadable", f"{path}: not a mapping")
        if data.get("kind") != "family-manifest":
            raise Refusal(
                "family-wrong-kind",
                f"{path}: kind is {data.get('kind')!r}, expected "
                "'family-manifest'")
        return cls(root, data)

    @property
    def members(self) -> list[dict]:
        return [row for row in (self.data.get("members") or [])
                if isinstance(row, dict)]

    def member(self, project: str) -> dict | None:
        return next((row for row in self.members
                     if str(row.get("project")) == project), None)

    def tracking(self) -> str:
        return checked_value("tracking_branch",
                             self.data.get("tracking_branch") or "main")

    def write_members(self, rows: list[dict]) -> None:
        """Rewrite everything from the `members:` line down.

        A LINE REWRITE, NOT A YAML DUMP, for the same reason
        `update-shape.py` rewrites the shape pin that way: the header of
        `family.yaml` is five paragraphs arguing what a family is and is not,
        and a round trip through a serialiser would delete every one of them.
        The block is LAST in the template precisely so this is a truncation
        and an append rather than a splice.
        """
        text = self.path.read_text(encoding="utf-8")
        lines = text.splitlines()
        out: list[str] = []
        seen = 0
        for line in lines:
            if line.rstrip() in ("members:", "members: []"):
                seen += 1
                out.append("members: []" if not rows else "members:")
                for row in rows:
                    out.extend(_member_lines(row))
                break
            out.append(line)
        if seen != 1:
            raise Refusal(
                "family-members-unrecognised",
                f"{self.path} has {seen} `members:` line(s) where exactly one "
                "was expected, so this tool will not rewrite it",
                "Remediation: the manifest was hand-edited into a shape this "
                "tool does not recognise. `members:` is the LAST block in the "
                "file and everything below it belongs to this tool; fix it by "
                "hand this once.")
        # LF, on every platform, like every other write this standard makes.
        # `family.yaml` is not digest-pinned, so nothing would go red - which
        # is exactly why it is worth saying: one tool rewriting a manifest
        # with CRLF on Windows makes every `members:` edit a whole-file diff.
        write_lf(self.path, "\n".join(out) + "\n")
        self.data["members"] = rows


def _member_lines(row: dict) -> list[str]:
    """One member as the YAML subset `repo_shape.parse_yaml` reads back."""
    pin = row.get("pin") or {}
    return [
        f"  - project: {row['project']}",
        f"    id: {row['id']}",
        f"    repository: {row['repository']}",
        f"    path: {row['path']}",
        "    pin:",
        "      revision_kind: commit",
        f"      commit: \"{pin['commit']}\"",
        "      digest_algorithm: sha256",
        f"      digest_definition: {TREE_DIGEST_DEFINITION}",
        f"      tree_sha256: \"{pin['tree_sha256']}\"",
    ]


def _member_row(project: str, project_id: str, repository: str, commit: str,
                digest: str) -> dict:
    return {
        "project": project,
        "id": project_id,
        "repository": repository,
        "path": f"{MEMBERS_DIR}/{project}",
        "pin": {"revision_kind": "commit", "commit": commit,
                "tree_sha256": digest},
    }


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------


def _checked_member(raw: str) -> tuple[str, str]:
    """`--member` as `(org/Project, Project)`."""
    name = raw.strip()
    if not MEMBER_RE.match(name):
        raise Refusal(
            "member-malformed",
            f"--member {raw!r} is not `<org>/<Project>`",
            "Remediation: name the owner — a family's members may live in "
            "another organisation, so there is no owner to assume. For "
            "`remove` and `bump`, the bare `<Project>` is what is wanted.")
    checked_value("--member", name)
    return name, repo_basename(name)


def _member_url(repository: str, local_remote_dir: Path | None) -> str:
    if local_remote_dir is None:
        return f"https://github.com/{repository}.git"
    return str((local_remote_dir.resolve() /
                f"{repo_basename(repository)}.git"))


def _classify_family_name(policy: NamingPolicy, name: str) -> None:
    """The family name against the policy, in the form a family declares.

    The `family` form is DECLARED-ONLY — `InkRouter` is spelled exactly like
    an assembly root and only `family.yaml` tells them apart — so the
    classifier is asked in those terms rather than left to give the residual
    reading.
    """
    found = policy.classify(name, "family")
    if found is None:
        raise Refusal(
            "naming-unclassified",
            f"{name!r} matches no family in the naming policy",
            "Remediation: --family takes one CamelCase token with no hyphen, "
            "underscore, dot or space — the same rule an assembly root's name "
            "follows, because a holder is spelled like one.")
    if found.family != "family":
        raise Refusal(
            "naming-not-a-family",
            f"{name!r} classifies as {found.family}"
            + (f"/{found.role}" if found.role else "")
            + f", not as a family holder ({found.reason})",
            "Remediation: --family takes one CamelCase token. An "
            "`open<Product>` or `<X>-Install` name is unambiguous by "
            "construction and cannot be declared into a holder.")


def _read_member_project(path: Path, project: str, repository: str) -> str:
    """The member's OWN `project.yaml` id, and that it is an assembly root.

    A FAMILY PINS ASSEMBLY ROOTS, never legs: the assembly root is the
    repository an engineer clones, and it is the only one of the three that
    knows what the whole project is. Reading its manifest here is what lets
    the row record an id the validator can check the mounted tree against.
    """
    manifest_path = path / "project.yaml"
    if not manifest_path.is_file():
        raise Refusal(
            "member-not-a-project",
            f"{repository} has no project.yaml at the commit being pinned, so "
            "it is not an assembly root of a project that has elected this "
            "shape",
            "Remediation: a family pins ASSEMBLY ROOTS. Scaffold or adopt the "
            "project first (`scaffold-project.py`, or `adopt-project.py` for "
            "a repository that already exists), then add it. Adding a leg — "
            f"`{project}-spec` or `{project}-code` — is never right: the legs "
            "belong to their own assembly root.")
    manifest = load_yaml(manifest_path)
    if not isinstance(manifest, dict):
        raise Refusal("member-manifest-unreadable",
                      f"{repository}: project.yaml is not a mapping")
    project_id = str(manifest.get("id") or "")
    if not PROJECT_ID_RE.match(project_id):
        raise Refusal(
            "member-bad-id",
            f"{repository}: project.yaml `id:` is {manifest.get('id')!r}, "
            f"which does not match {PROJECT_ID_RE.pattern}")
    return project_id


def _commit_one(root: Path, message: str, paths: list[str],
                add: list[str] | None = None) -> str:
    """ONE commit, with EXPLICIT PATHSPECS.

    `git commit -- <paths>` commits the working-tree state of exactly those
    paths and nothing the index happens to be carrying. That matters wherever
    more than one session shares a checkout: a bare `git commit` takes
    whatever anyone staged, which is how a one-line bookkeeping commit swept
    nine unrelated renames into itself in the xFactory aggregation on
    2026-07-29.

    `add` defaults to `paths` and differs from it in exactly one case:
    `remove`, where `git rm` has already staged the deletion and taken the
    path out of both the index and the tree, so `git add` on it fails with
    "pathspec did not match any files" while `git commit` on it is correct —
    the pathspec still matches what HEAD has.
    """
    run(["git", "add", "--", *(paths if add is None else add)], cwd=root)
    args = ["git", "commit", "-q", "-F", "-", "--", *paths]
    check_program(args)
    env = dict(os.environ)
    for key, fallback in (("GIT_AUTHOR_NAME", "openRepoShape family"),
                          ("GIT_COMMITTER_NAME", "openRepoShape family"),
                          ("GIT_AUTHOR_EMAIL", "family@openreposhape.invalid"),
                          ("GIT_COMMITTER_EMAIL",
                           "family@openreposhape.invalid")):
        if not env.get(key):
            env[key] = fallback
    proc = subprocess.run(args, cwd=str(root), input=message,
                          capture_output=True, text=True, check=False, env=env)
    if proc.returncode != 0:
        raise CommandFailed(args, root, proc.returncode,
                            proc.stderr + proc.stdout)
    return git_out(["rev-parse", "HEAD"], cwd=root).lower()


def _remote_is_empty(repository: str) -> bool | None:
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
        if "empty" in (commits.stderr + commits.stdout).lower():
            return True
        raise Refusal(
            "remote-unreadable",
            f"{repository} exists but its commit listing could not be read: "
            f"{commits.stderr.strip()}",
            "Remediation: check `gh auth status`, then re-run.")
    try:
        return not json.loads(commits.stdout)
    except json.JSONDecodeError:
        return False


def _local_remote_is_empty(bare: Path) -> bool | None:
    if not bare.exists():
        return None
    out = subprocess.run(["git", "-C", str(bare), "rev-list", "--count",
                          "--all"], capture_output=True, text=True, check=False)
    if out.returncode != 0:
        raise Refusal("remote-unreadable",
                      f"{bare} exists but is not a git repository")
    return out.stdout.strip() in ("", "0")


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def cmd_init(args) -> int:  # noqa: C901
    family = checked_value("--family", args.family)
    args.org = checked_value("--org", args.org)
    args.tracking_branch = checked_value("--tracking-branch",
                                         args.tracking_branch)
    family_id = checked_value("--id", args.id or family.lower())
    if not PROJECT_ID_RE.match(family_id):
        raise Refusal("family-bad-id",
                      f"--id {family_id!r} must match {PROJECT_ID_RE.pattern}",
                      "Remediation: pass an explicit lowercase --id.")
    policy = NamingPolicy.load(NAMING_POLICY)
    _classify_family_name(policy, family)
    topic = policy.topic_for(family_id)

    created_by = args.created_by or (os.environ.get("GIT_AUTHOR_NAME") or "").strip()
    if not created_by:
        try:
            created_by = git_out(["config", "user.name"], cwd=SHAPE_ROOT)
        except Refusal:
            created_by = ""
    if not created_by:
        raise Refusal(
            "family-no-creator",
            "no --created-by, no GIT_AUTHOR_NAME and no `git config "
            "user.name`. Creating a family is a human's act and the manifest "
            "records whose.",
            "Remediation: re-run with --created-by 'Your Name'.")

    local = args.local_remote_dir is not None
    repository = f"{args.org}/{family}"
    url = (str(args.local_remote_dir.resolve() / f"{family}.git") if local
           else f"https://github.com/{repository}.git")

    shape_commit = git_out(["rev-parse", "HEAD"], cwd=SHAPE_ROOT).lower()
    shape_tree = tree_digest(SHAPE_ROOT, shape_commit)
    if git_out(["status", "--porcelain"], cwd=SHAPE_ROOT):
        print("WARNING the openRepoShape checkout is DIRTY. `commit:` and "
              f"`tree_sha256` will record {shape_commit[:12]}, which does NOT "
              "describe the bytes being copied. The per-file sha256 rows are "
              "computed from the actual copies, so drift stays detectable — "
              "but commit before creating a real family.", file=sys.stderr)

    values = {
        "FAMILY": family,
        "FAMILY_NAME": args.name or family,
        "FAMILY_ID": family_id,
        "FAMILY_REPOSITORY": repository,
        "ORG": args.org,
        "VISIBILITY": args.visibility,
        "TRACKING_BRANCH": args.tracking_branch,
        "CREATED_BY": created_by,
        "CREATED_ON": args.created_on or _dt.date.today().isoformat(),
        "CLONE_URL": url,
        "SHAPE_REPOSITORY": SHAPE_REPOSITORY,
        "SHAPE_COMMIT": shape_commit,
        "SHAPE_TREE_SHA256": shape_tree,
        "DIGEST_DEFINITION": TREE_DIGEST_DEFINITION,
    }

    print(f"family       {values['FAMILY_NAME']} ({family_id})")
    print(f"shape        {SHAPE_REPOSITORY} @ {shape_commit[:12]} "
          f"(tree {shape_tree[:12]}…)")
    print(f"created by   {values['CREATED_BY']} on {values['CREATED_ON']}")
    print(f"  holder     {repository:<28} -> {url}")
    print(f"members      mounted under {MEMBERS_DIR}/; none yet — "
          "`family.py add` puts one there")
    print("remotes      " + ("a bare repository on disk (no network)" if local
                             else f"gh repo create --{args.visibility}"))
    if args.reuse_empty_repo:
        print("reuse        an EXISTING <Family> with zero commits is used as "
              "the holder")
    print("topics       " + ("skipped for local remotes" if local
                             else f"gh repo edit --add-topic {topic}"))
    if args.dry_run:
        print("\n--dry-run: nothing was created.")
        return 0

    work_root = (args.work_dir.resolve() if args.work_dir
                 else Path(tempfile.mkdtemp(prefix="openreposhape-family-")))
    work_root.mkdir(parents=True, exist_ok=True)
    work = work_root / family
    if work.exists() and any(work.iterdir()):
        raise Refusal(
            "family-target-exists", f"{work} already exists and is not empty",
            "Remediation: choose an empty --work-dir. There is no --force.")

    # THE ONE REPOSITORY THAT MAY ALREADY EXIST is the holder, and only with
    # --reuse-empty-repo, and only with ZERO commits. `InkRouter` in the
    # InkRouter org is exactly that today: a name somebody reserved, which is
    # not the same as a project somebody started.
    target = Path(url) if local else repository
    empty = _local_remote_is_empty(target) if local else _remote_is_empty(target)
    reuse = False
    if empty is not None:
        if not (args.reuse_empty_repo and empty):
            raise Refusal(
                "family-remote-exists",
                f"{target} already exists" + ("" if local else " on GitHub")
                + ("" if empty else " and has commits"),
                ("Remediation: it has ZERO commits, so it is a reserved name "
                 "rather than a live repository — re-run with "
                 "--reuse-empty-repo to use it as the family holder."
                 if empty else
                 "Remediation: it HAS commits, so it is a live repository and "
                 "this is not an init. There is no --force."))
        reuse = True
        print(f"  reuse {target} (zero commits)")

    print("\ncreating the holder")
    if not reuse:
        if local:
            Path(url).parent.mkdir(parents=True, exist_ok=True)
            run(["git", "init", "-q", "--bare", "-b", args.tracking_branch, url])
            print(f"  bare  {url}")
        else:
            run(["gh", "repo", "create", repository, f"--{args.visibility}",
                 "--description",
                 f"{values['FAMILY_NAME']} — family holder: the "
                 f"{family_id} projects, pinned as submodules"])
            print(f"  gh    {repository} ({args.visibility})")

    work.mkdir(parents=True, exist_ok=True)
    materialize_family_root(SHAPE_ROOT, work, values)
    run(["git", "init", "-q", "-b", args.tracking_branch, str(work)])
    run(["git", "add", "-A", "--", "."], cwd=work)
    env_commit(work,
               f"Create the {values['FAMILY_NAME']} family holder\n\n"
               f"A HOLDER, not a project: no spec leg, no code leg. It pins "
               f"member assembly roots under {MEMBERS_DIR}/ and carries the "
               f"utilities to fetch and bootstrap them together (Brett Heap, "
               f"2026-09-04).\n\nShape {SHAPE_REPOSITORY} @ {shape_commit}.\n"
               "Membership confers nothing.\n")
    run(["git", "remote", "add", "origin", url], cwd=work)
    if not args.no_push:
        try:
            run(["git", "push", "-q", "-u", "origin", args.tracking_branch],
                cwd=work)
        except CommandFailed as exc:
            print(exc.loudly("pushing the family holder"), file=sys.stderr)
            print(RULESET_HINT.format(work=work, repo=repository,
                                      role="family"), file=sys.stderr)
            return 2
    head = git_out(["rev-parse", "HEAD"], cwd=work)[:12]
    print(f"  holder    {head} -> {url}")
    if not local:
        run(["gh", "repo", "edit", repository, "--add-topic", topic])
        print(f"  topic     {topic} set on the holder")
    if not local and args.visibility in ("private", "internal"):
        print(f"NOTE {repository} is {args.visibility} and its members will "
              "be too: give it a way to read them — a GitHub App "
              "(SHAPE_LEGS_APP_ID + SHAPE_LEGS_APP_PRIVATE_KEY, preferred) or "
              "a SHAPE_LEGS_TOKEN PAT with contents:read on the members AND "
              "their legs — or the `validate` check cannot check them out.")
        hint = free_plan_secret_hint(
            args.org, repository, f"{repository} and its members are")
        if hint:
            print(hint)
    print(f"""
NEXT STEPS

    {PYTHON} {Path(__file__).name} add --family-root {work} \\
        --member {args.org}/<Project>
    git -C {work} push

`add` mounts the member at {MEMBERS_DIR}/<Project>, records its pin, and
writes ONE commit. Then `make bootstrap` in the holder fetches every member
and its legs and runs each member's own bootstrap.

Working tree at {work}
""")
    return 0


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


def cmd_add(args) -> int:
    family = Family.open(args.family_root)
    repository, project = _checked_member(args.member)
    if family.member(project) is not None:
        raise Refusal(
            "member-already-present",
            f"{project} is already a member of {family.data.get('name')}",
            "Remediation: `family.py bump --member "
            f"{project} --to <commit>` moves an existing member; `remove` "
            "takes it out. Adding it twice is not a way to move it.")
    path = f"{MEMBERS_DIR}/{project}"
    if (family.root / path).exists():
        raise Refusal(
            "member-path-taken",
            f"{path} already exists in the family root but no `members:` row "
            "names it",
            "Remediation: this is a half-finished add or a hand-made "
            "directory. Remove it (`git rm -r` if it is tracked), then re-run.")
    # `git rm` deliberately leaves a removed submodule's OBJECT STORE behind,
    # so a member that was removed and is being added back trips `git
    # submodule add` with an error about a git directory found locally. That
    # cache is not this tool's to delete — it may hold commits somebody made
    # inside the mount and never pushed — so the exit is named instead of
    # taken.
    # NAMED IN POSIX: git spells this `.git/modules/<path>`, and so does the
    # human who retypes the remediation below.
    cached = family.root / ".git" / "modules" / path
    if cached.exists():
        raise Refusal(
            "member-git-dir-cached",
            f"{cached.as_posix()} still holds the object store of a "
            f"previously removed {project}, and `git submodule add` will not "
            "write over it",
            "Remediation: if nothing unpushed lives in it — and nothing does "
            "unless somebody committed inside the mount — delete it and "
            f"re-run:\n    rm -rf {cached.as_posix()}\nIt is left behind by "
            "`git rm` on purpose, which is why this tool will not remove it "
            "for you.")

    url = _member_url(repository, args.local_remote_dir)
    protocol = FILE_PROTOCOL if args.local_remote_dir is not None else []
    print(f"mounting {repository} at {path}")
    try:
        run(["git", *protocol, "submodule", "add", "-q", "--", url, path],
            cwd=family.root)
    except CommandFailed as exc:
        print(exc.loudly(f"mounting {repository}"), file=sys.stderr)
        print("The member must be readable from here. If it is PRIVATE, check "
              "`gh auth status` or your SSH key; a family cannot pin what it "
              "cannot read.", file=sys.stderr)
        return 2
    member = family.root / path
    if args.at:
        commit = checked_value("--at", args.at)
        if not COMMIT_RE.match(commit):
            raise Refusal(
                "member-at-not-a-commit",
                f"--at {args.at!r} is not a 40-hex commit",
                "Remediation: pass the full 40 characters. A tag can be moved "
                "and a commit cannot, which is why a pin is never a tag.")
        try:
            run(["git", "checkout", "-q", commit.lower()], cwd=member)
        except CommandFailed as exc:
            print(exc.loudly(f"checking {repository} out at {commit[:12]}"),
                  file=sys.stderr)
            return 2
    commit = git_out(["rev-parse", "HEAD"], cwd=member).lower()
    project_id = _read_member_project(member, project, repository)
    digest = tree_digest(member, commit)
    row = _member_row(project, project_id, repository, commit, digest)
    rows = sorted(family.members + [row], key=lambda r: str(r["project"]))
    family.write_members(rows)

    head = _commit_one(
        family.root,
        f"Add {project} to the {family.data.get('name')} family\n\n"
        f"{repository} @ {commit[:12]} is mounted at {path} and pinned in "
        f"{MANIFEST} — the gitlink and `members[].pin.commit` in ONE commit, "
        "which is the whole of the lockstep rule.\n\nIt remains a whole "
        "project: its own assembly root, its own legs, its own gate. "
        "Membership confers nothing.\n",
        [".gitmodules", path, MANIFEST])
    print(f"  {project:<16} {commit[:12]} tree {digest[:12]}… "
          f"(project {project_id})")
    print(f"  committed {head[:12]}: .gitmodules, {path}, {MANIFEST}")
    print(f"\nNEXT  git -C {family.root} push -u origin <branch> && open a "
          "pull request")
    return 0


# ---------------------------------------------------------------------------
# bump
# ---------------------------------------------------------------------------


def cmd_bump(args) -> int:
    family = Family.open(args.family_root)
    project = checked_value("--member", repo_basename(args.member))
    row = family.member(project)
    if row is None:
        raise Refusal(
            "member-unknown",
            f"{project} is not a member of {family.data.get('name')}",
            "Remediation: `family.py add --member <org>/" + project
            + "` puts it in the family first.")
    commit = checked_value("--to", args.to).lower()
    if not COMMIT_RE.match(commit):
        raise Refusal(
            "member-to-not-a-commit",
            f"--to {args.to!r} is not a 40-hex commit",
            "Remediation: pass the full 40 characters. A tag can be moved and "
            "a commit cannot; a pin is a commit or it is nothing.")
    path = str(row.get("path") or f"{MEMBERS_DIR}/{project}")
    member = family.root / path
    if not (member / ".git").exists():
        raise Refusal(
            "member-uninitialized",
            f"{path} is not an initialized submodule checkout, so the new "
            "commit cannot be resolved or digested",
            "Remediation: `git submodule update --init " + path + "`, or "
            "`make bootstrap`, which resolves a credential for a private "
            "member first.")
    try:
        run(["git", "fetch", "-q", "origin"], cwd=member)
    except CommandFailed:
        print(f"  note: could not fetch {path} from its origin; the commit "
              "must already be in its object store", file=sys.stderr)
    try:
        run(["git", "checkout", "-q", commit], cwd=member)
    except CommandFailed as exc:
        print(exc.loudly(f"checking {path} out at {commit[:12]}"),
              file=sys.stderr)
        return 2

    was = str((row.get("pin") or {}).get("commit") or "")
    project_id = _read_member_project(member, project,
                                      str(row.get("repository")))
    digest = tree_digest(member, commit)
    rows = [(_member_row(project, project_id, str(row["repository"]), commit,
                         digest) if str(r.get("project")) == project else r)
            for r in family.members]
    family.write_members(rows)

    head = _commit_one(
        family.root,
        f"Bump {project} to {commit[:12]} in the "
        f"{family.data.get('name')} family\n\n"
        f"{was[:12]} -> {commit[:12]}. The gitlink at {path} and "
        f"`members[].pin` in {MANIFEST} move in ONE commit, which is what "
        "`validate-family.py` checks and what a reviewer reads as one "
        "change.\n",
        [path, MANIFEST])
    print(f"  {project:<16} {was[:12]} -> {commit[:12]} tree {digest[:12]}…")
    print(f"  committed {head[:12]}: {path}, {MANIFEST}")
    return 0


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------


def cmd_remove(args) -> int:
    family = Family.open(args.family_root)
    project = checked_value("--member", repo_basename(args.member))
    row = family.member(project)
    if row is None:
        raise Refusal(
            "member-unknown",
            f"{project} is not a member of {family.data.get('name')}",
            "Remediation: `validate-family.py` lists what is here. Removing "
            "something that is not a member is a no-op worth refusing, "
            "because the argument is usually a typo for something that is.")
    path = str(row.get("path") or f"{MEMBERS_DIR}/{project}")
    # THE MEMBER REPOSITORY IS NOT TOUCHED. Removing a member unmounts it from
    # this holder and nothing else: the project keeps its name, its history,
    # its legs and its gate. A family that could delete a project by dropping
    # a row would be a family that confers something.
    run(["git", "submodule", "deinit", "-f", "-q", "--", path], cwd=family.root)
    run(["git", "rm", "-r", "-q", "-f", "--", path], cwd=family.root)
    family.write_members([r for r in family.members
                          if str(r.get("project")) != project])
    head = _commit_one(
        family.root,
        f"Remove {project} from the {family.data.get('name')} family\n\n"
        f"Unmounted from {path} and dropped from {MANIFEST}. "
        f"{row.get('repository')} itself is untouched: it keeps its name, its "
        "history, its legs and its gate. Membership was navigation and "
        "conferred nothing, so losing it takes nothing away.\n",
        [".gitmodules", path, MANIFEST], add=[".gitmodules", MANIFEST])
    print(f"  removed {project} ({row.get('repository')}) from {path}")
    print(f"  committed {head[:12]}: .gitmodules, {path}, {MANIFEST}")
    # POSIX for the same reason it is POSIX in `add`: git spells this path
    # `.git/modules/<path>`, and so does the human who deletes it.
    cached = family.root / ".git" / "modules" / path
    if cached.exists():
        print(f"  NOTE {cached.as_posix()} still holds that member's object "
              "store. `git rm` leaves it on purpose, in case somebody "
              "committed inside the mount; delete it (`rm -rf`) before adding "
              "this member back.")
    return 0


# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="family.py", description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="create a family holder")
    init.add_argument("--org", required=True)
    init.add_argument("--family", required=True,
                      help="the holder's name, ONE CamelCase token, e.g. "
                           "InkRouter")
    init.add_argument("--id", default=None, help="lowercase family id")
    init.add_argument("--name", default=None, help="display name")
    init.add_argument("--visibility", choices=VISIBILITY_CHOICES,
                      default="private")
    init.add_argument("--created-by", default=None)
    init.add_argument("--created-on", default=None, help="YYYY-MM-DD")
    init.add_argument("--tracking-branch", default="main")
    init.add_argument("--reuse-empty-repo", action="store_true",
                      help="if <org>/<Family> already exists and has ZERO "
                           "commits, use it as the holder instead of "
                           "refusing. A repository with commits is still "
                           "refused: that is live, not a slot.")
    init.add_argument("--local-remote-dir", type=Path, default=None,
                      help="create a bare repository here instead of calling "
                           "`gh repo create` (the TEST path; no network)")
    init.add_argument("--work-dir", type=Path, default=None)
    init.add_argument("--no-push", action="store_true")
    init.add_argument("--dry-run", action="store_true")
    init.set_defaults(func=cmd_init)

    add = subparsers.add_parser("add", help="mount and pin a member")
    add.add_argument("--family-root", required=True)
    add.add_argument("--member", required=True, metavar="ORG/PROJECT",
                     help="the member's ASSEMBLY ROOT, `<org>/<Project>` — "
                          "never a leg")
    add.add_argument("--at", default=None, metavar="COMMIT",
                     help="pin this 40-hex commit instead of the member's "
                          "current tip")
    add.add_argument("--local-remote-dir", type=Path, default=None,
                     help="resolve the member to a bare repository here "
                          "instead of github.com (the TEST path)")
    add.set_defaults(func=cmd_add)

    bump = subparsers.add_parser("bump", help="move a member's pin")
    bump.add_argument("--family-root", required=True)
    bump.add_argument("--member", required=True, metavar="PROJECT")
    bump.add_argument("--to", required=True, metavar="COMMIT",
                      help="the 40-hex commit to move the gitlink and the pin "
                           "to, together")
    bump.set_defaults(func=cmd_bump)

    remove = subparsers.add_parser("remove", help="unmount a member")
    remove.add_argument("--family-root", required=True)
    remove.add_argument("--member", required=True, metavar="PROJECT")
    remove.set_defaults(func=cmd_remove)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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
