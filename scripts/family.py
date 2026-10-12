#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Create and maintain a FAMILY: a holder that pins member assembly roots.

    ./scripts/family.py init     --org <org> --family <Name> [--into <dir>]
    ./scripts/family.py add      --family-root <path> --member <org>/<Project>
    ./scripts/family.py bump     --family-root <path> --member <Project> --to <sha>
    ./scripts/family.py remove   --family-root <path> --member <Project>
    ./scripts/family.py siblings --family-root <path>

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

THE WORKSTATION LAYOUT (Brett Heap, 2026-09-09, issue #76). `init` lands the
holder at `<into>/<Family>/<Family>`: a PLAIN FOLDER named after the family,
holding the holder clone and — once `siblings` has run — the members' working
clones beside it. The doubled name is kept on purpose: the holder is a
repository and keeps its own name, and `family.yaml` is what tells the two
apart. `siblings` is the holder's own `make siblings`, run from a checkout of
this standard so it works before the holder is anywhere else; there is ONE
implementation of it, `templates/family-root/scripts/siblings.py`, and this
subcommand runs that file rather than a second copy of its logic.

EXIT CODES: 0 done · 1 nothing (a dry run prints and exits 0) · 2 a refusal.
`siblings` exits with the template script's own code, unchanged. A `bump` whose
commit would record nothing — the member is already pinned at `--to`, in the
gitlink and in `family.yaml` alike — is `nothing`: it says `nothing to do`, as
`bump-leg.py` does for a leg, and writes no commit.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import runpy
import shutil
import stat
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
    load_yaml, recorded_gitlink, repo_basename, same_repository, tree_digest,
)
from shape_materialize import (  # noqa: E402
    RULESET_HINT, SHAPE_REPOSITORY, CommandFailed, check_program,
    commit_trailers, env_commit, escape_what_stdout_cannot_encode,
    force_stage, materialize_family_root, run, stage_written, trailer_line,
    write_lf,
)

NAMING_POLICY = SHAPE_ROOT / "contracts" / "repository-naming.yaml"
MANIFEST = "family.yaml"
MEMBERS_DIR = "members"
#: `add` and `remove` each list it as BOTH the gitlink path `git submodule`
#: writes and (`remove` only) an explicit `add=` path re-staged after `git rm`
#: -- named once so the two commits cannot spell the file differently.
GITMODULES = ".gitmodules"
FILE_PROTOCOL = ["-c", "protocol.file.allow=always"]

#: `<org>/<Project>`, the only spelling `--member` accepts. A bare name would
#: have to guess an owner, and a family whose members are in another
#: organisation is an ordinary case (an estate's neutral products are).
MEMBER_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

#: The suffix a LEG's name carries after its assembly root's — the
#: `(?:-spec|-code)?` that `contracts/repository-naming.yaml`'s leg pattern
#: ends in, and nothing looser: `IRRS-spec` is the spec leg of `IRRS`.
LEG_SUFFIX_RE = re.compile(r"-(?:spec|code)$")


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
        """The row for `project`, compared the way the forge compares a name.

        GitHub resolves an owner and a repository name case-insensitively
        (`repo_shape.same_repository`, #149), so `irss` and `IRSS` are ONE
        member and a row typed the other way is not a stranger (#206). The
        row's own spelling is the one it keeps: callers read `row["project"]`
        and `row["path"]` back, never the spelling they were handed. An EXACT
        match wins, so a family a pre-#206 `add` pinned twice (`IRRS` and
        `irrs`) can still be mended by naming the row to touch; any other
        spelling that fits two rows is refused rather than guessed.
        """
        rows = [row for row in self.members
                if str(row.get("project")).lower() == project.lower()]
        for row in rows:
            if str(row.get("project")) == project:
                return row
        if len(rows) > 1:
            raise Refusal(
                "member-ambiguous",
                f"{project} fits {len(rows)} rows of {self.data.get('name')}: "
                + ", ".join(str(row.get("project")) for row in rows),
                "Remediation: name one of them in the spelling the row uses; "
                "the family pins one project twice, and `remove` takes the "
                "extra one out.")
        return rows[0] if rows else None

    def holding(self, repository: str, project: str) -> dict | None:
        """The row that already pins this repository, or None (#206).

        By name first (`member`), then by the row's `repository:` — the
        forge's own identity, which `repo_shape.same_repository` folds for
        case — so `inkrouter/irrs` finds the row that pins `InkRouter/IRRS`.
        """
        row = self.member(project)
        if row is not None:
            return row
        return next((row for row in self.members
                     if same_repository(repository,
                                        str(row.get("repository")))), None)

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
        text = self.rewritten(rows)
        # LF, on every platform, like every other write this standard makes.
        # `family.yaml` is not digest-pinned, so nothing would go red - which
        # is exactly why it is worth saying: one tool rewriting a manifest
        # with CRLF on Windows makes every `members:` edit a whole-file diff.
        write_lf(self.path, text)
        self.data["members"] = rows

    def rewritten(self, rows: list[dict]) -> str:
        """The manifest's text with the `members:` block replaced by `rows`,
        or the refusal `write_members` would raise — and nothing written.

        SPLIT OUT SO THE REFUSAL CAN BE ASKED EARLY (#203). `add` calls this
        with the rows the manifest already has BEFORE it mounts anything, so
        a manifest this tool will not rewrite is refused while the holder is
        still exactly as the human left it, rather than after `git submodule
        add` has staged a gitlink and a `.gitmodules` section that the
        refusal would then leave behind.
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
        return "\n".join(out) + "\n"


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


def _read_member_project(path: Path, project: str, repository: str,
                         shown: str | None = None) -> str:
    """The member's OWN `project.yaml` id, and that it is an assembly root.

    A FAMILY PINS ASSEMBLY ROOTS, never legs: the assembly root is the
    repository an engineer clones, and it is the only one of the three that
    knows what the whole project is. Reading its manifest here is what lets
    the row record an id the validator can check the mounted tree against.

    `shown` IS THE NAME A REFUSAL GIVES THE FILE when `path` is not where a
    human could find it: `add` reads the member's manifest out of a
    throwaway clone before it mounts anything (#203), and a `load_yaml`
    refusal naming that clone's temporary directory would name a file that
    has been deleted by the time anybody reads the line. Every other word of
    every refusal here is the same either way.
    """
    manifest_path = path / "project.yaml"
    if not manifest_path.is_file():
        # A LEG IS NAMED BY ITS ROOT (#203). The commonest way here is
        # `--member <org>/IRRS-spec`, and the legs of `IRRS-spec` are
        # `IRRS-spec-spec` and `IRRS-spec-code`, which no naming rule makes
        # and no repository is — so the sentence names the legs of the root
        # the suffix came off, and that root, which is the one a family pins.
        root = LEG_SUFFIX_RE.sub("", project)
        raise Refusal(
            "member-not-a-project",
            f"{repository} has no project.yaml at the commit being pinned, so "
            "it is not an assembly root of a project that has elected this "
            "shape",
            "Remediation: a family pins ASSEMBLY ROOTS. Scaffold or adopt the "
            "project first (`scaffold-project.py`, or `adopt-project.py` for "
            "a repository that already exists), then add it. Adding a leg — "
            f"`{root}-spec` or `{root}-code` — is never right: the legs "
            "belong to their own assembly root"
            + (f", `{root}`." if root != project else "."))
    try:
        manifest = load_yaml(manifest_path)
    except Refusal as exc:
        if shown is None:
            raise
        raise Refusal(exc.code, exc.detail.replace(str(manifest_path), shown),
                      exc.remediation) from exc
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
                add: list[str] | None = None,
                trailers: list[str] = ()) -> str:
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

    `trailers` ARE THE LINES THE COMMIT ENDS WITH, in the order `--trailer`
    named them (2026-09-11, #111). A holder's `bump` writes its own message,
    so a `Lane:` line — which the lane-collision protocol wants on every
    artifact a lane produces, the commit included — reaches it no other way;
    `Co-Authored-By:` is this estate's own convention beside it. Passed none,
    the message is exactly the one this function has always written. See
    `shape_materialize.commit_trailers` for the two ways git is asked.

    THE NAMED PATHS ARE FORCED PAST THE OPERATOR'S EXCLUDES (#242). `git
    add` reads a global `core.excludesFile` too, and the gitlink at
    `members/<Project>` sits under a directory such a file may name: under
    `members`, `members/` or `*` it refused `git add -- .gitmodules
    members/<Project> family.yaml` even once the mount itself was forced, and
    `bump`, which stages `[path, MANIFEST]` here, died the same way with the
    gitlink already tracked. `members/` is a fixed path, so there was nothing
    in either invocation to change but the operator's own excludes. `-f`
    reaches only the paths named, which are the ones this commit is of.
    EACH NAME IS TAKEN LITERALLY (`--literal-pathspecs`): a pathspec is a glob
    to git, and `-f` must stage the path it names and no ignored neighbour a
    glob character would match (#202). Both are what
    `shape_materialize.force_stage` does (#233), the one forced add the
    scaffold and `update-shape.py` share, so it is called here rather than
    spelled a second time; `bump`'s re-stage before its nothing-to-record
    check is the same call, for the same reason.
    """
    force_stage(root, paths if add is None else add)
    message, trailer_args = commit_trailers(message, trailers)
    args = ["git", "commit", "-q", "-F", "-", *trailer_args, "--", *paths]
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
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False,
                          env=env)
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
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", check=False)
    if probe.returncode != 0:
        return None
    commits = subprocess.run(
        ["gh", "api", f"repos/{repository}/commits?per_page=1"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False)
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
                          "--all"], capture_output=True, text=True,
                         encoding="utf-8", errors="replace", check=False)
    if out.returncode != 0:
        raise Refusal("remote-unreadable",
                      f"{bare} exists but is not a git repository")
    return out.stdout.strip() in ("", "0")


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


SIBLINGS_SCRIPT = (SHAPE_ROOT / "templates" / "family-root" / "scripts" /
                   "siblings.py")


def _landing(args, family: str) -> tuple[Path | None, Path]:
    """`(the family folder, the holder)` — WHERE `init` PUTS THINGS.

    THE DEFAULT LANDS WHERE YOU ARE STANDING, which is the rule #39 gave
    projects and the ruling of 2026-09-09 gives families: `--into` is the
    PARENT directory (the invocation directory by default), the family FOLDER
    `<Family>/` is created in it, and the holder is cloned INSIDE that at
    `<into>/<Family>/<Family>`. The folder is a plain directory and never a
    repository; the doubled name is the holder keeping its own repository
    name, and `family.yaml` is what tells the two apart.

    STANDING IN THE FAMILY FOLDER ALREADY is the one exception: when the
    directory is itself named `<Family>` and holds no `<Family>/family.yaml`,
    a second `<Family>/` would nest a folder inside the folder the person is
    already in, so the holder lands at `<dir>/<Family>`. When it DOES hold
    one, the family exists and this is not an init — refused by name below.

    `--work-dir` keeps today's semantics untouched (`<work-dir>/<Family>`, no
    folder made) because every test and every rehearsal in this suite passes
    it, and a flag that quietly changed meaning is worse than a second flag.
    """
    if args.work_dir is not None:
        return None, args.work_dir.expanduser().resolve() / family
    into = (args.into or Path.cwd()).expanduser().resolve()
    if into.name == family:
        if (into / family / MANIFEST).is_file():
            raise Refusal(
                "family-holder-already-here",
                f"{into} is already the {family} family folder and its holder "
                f"is at {into / family}, so there is nothing to init",
                "Remediation: `family.py add --family-root "
                f"{into / family} --member <org>/<Project>` grows it, and "
                "`make siblings` in the holder puts each member's working "
                "clone beside it. There is no --force.")
        return into, into / family
    return into / family, into / family / family


def _checked_family_identity(args) -> tuple[str, str, str]:
    """`(family, family_id, topic)` — every name check `init` makes before
    it decides where anything lands.

    Split from `cmd_init` for #136. Mutates `args.org` and
    `args.tracking_branch` to their checked values, exactly as `cmd_init`
    always has, because every later read of either expects the checked
    form.
    """
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
    return family, family_id, topic


def _creator_name(args) -> str:
    """Whoever `--created-by` (or the environment, or git config) says
    created this family — refused when nothing does.

    Split from `cmd_init` for #136: creating a family is a human's act and
    the manifest records whose.
    """
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
    return created_by


def _holder_remote(args, family: str) -> tuple[bool, str, str]:
    """`(local, repository, url)` — where the holder's remote lives.

    Split from `cmd_init` for #136.
    """
    local = args.local_remote_dir is not None
    repository = f"{args.org}/{family}"
    url = (str(args.local_remote_dir.resolve() / f"{family}.git") if local
           else f"https://github.com/{repository}.git")
    return local, repository, url


def _shape_snapshot() -> tuple[str, str]:
    """`(shape_commit, shape_tree)` of this checkout, warning to stderr when
    it is dirty.

    Split from `cmd_init` for #136.
    """
    shape_commit = git_out(["rev-parse", "HEAD"], cwd=SHAPE_ROOT).lower()
    shape_tree = tree_digest(SHAPE_ROOT, shape_commit)
    if git_out(["status", "--porcelain"], cwd=SHAPE_ROOT):
        print("WARNING the openRepoShape checkout is DIRTY. `commit:` and "
              f"`tree_sha256` will record {shape_commit[:12]}, which does NOT "
              "describe the bytes being copied. The per-file sha256 rows are "
              "computed from the actual copies, so drift stays detectable — "
              "but commit before creating a real family.", file=sys.stderr)
    return shape_commit, shape_tree


def _template_values(args, family: str, family_id: str, repository: str,
                     url: str, created_by: str, shape_commit: str,
                     shape_tree: str) -> dict:
    """The values `materialize_family_root` substitutes into the holder's
    template.

    Split from `cmd_init` for #136.
    """
    return {
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


def _checked_landing(args, family: str) -> tuple[Path | None, Path]:
    """`(folder, holder)`, refused when `--into` and `--work-dir` both name
    where the holder goes.

    Split from `cmd_init` for #136.
    """
    if args.into is not None and args.work_dir is not None:
        raise Refusal(
            "family-two-landings",
            "--into and --work-dir both name where the holder goes, and they "
            "do not mean the same thing",
            "Remediation: pass --into <parent> for the workstation layout "
            f"(<parent>/{family}/{family}), or --work-dir <dir> for the bare "
            f"override (<dir>/{family}, no family folder). Not both.")
    return _landing(args, family)


def _print_init_plan(values: dict, repository: str, url: str,
                     shape_commit: str, shape_tree: str, folder: Path | None,
                     holder: Path, local: bool, topic: str,
                     reuse_empty_repo: bool) -> None:
    """Print the plan `init` is about to carry out — what `--dry-run` shows,
    and what a real run shows before it does anything.

    Split from `cmd_init` for #136.
    """
    print(f"family       {values['FAMILY_NAME']} ({values['FAMILY_ID']})")
    print(f"shape        {SHAPE_REPOSITORY} @ {shape_commit[:12]} "
          f"(tree {shape_tree[:12]}…)")
    print(f"created by   {values['CREATED_BY']} on {values['CREATED_ON']}")
    print(f"  holder     {repository:<28} -> {url}")
    if folder is None:
        print(f"landing      {holder}   (--work-dir: no family folder)")
    else:
        print(f"folder       {folder}   a plain folder, NOT a repository")
        print(f"landing      {holder}   the holder clone, inside it")
    print(f"members      mounted under {MEMBERS_DIR}/; none yet — "
          "`family.py add` puts one there")
    print("remotes      " + ("a bare repository on disk (no network)" if local
                             else f"gh repo create --{values['VISIBILITY']}"))
    if reuse_empty_repo:
        print("reuse        an EXISTING <Family> with zero commits is used as "
              "the holder")
    print("topics       " + ("skipped for local remotes" if local
                             else f"gh repo edit --add-topic {topic}"))


def _prepare_landing_dir(folder: Path | None, holder: Path) -> Path:
    """Make the landing directory, refused if the holder's target already
    exists and is not empty.

    Split from `cmd_init` for #136.
    """
    # `mkdir -p` on the FOLDER, which is fine if it is already there — a
    # family folder somebody made by hand, or one a scaffolded member already
    # landed in, is exactly the case this is supposed to join.
    work = holder
    (folder or work.parent).mkdir(parents=True, exist_ok=True)
    if work.exists() and any(work.iterdir()):
        raise Refusal(
            "family-target-exists", f"{work} already exists and is not empty",
            "Remediation: choose another --into (or an empty --work-dir); if "
            "that IS the holder, it is already a family and `family.py add` "
            "is what grows it. There is no --force.")
    return work


def _checked_reuse(reuse_empty_repo: bool, local: bool, url: str,
                   repository: str) -> bool:
    """Is the holder's remote an existing, empty repository being reused?

    Refused when the remote already exists WITH commits, or exists empty
    without `--reuse-empty-repo`. Split from `cmd_init` for #136.
    """
    # THE ONE REPOSITORY THAT MAY ALREADY EXIST is the holder, and only with
    # --reuse-empty-repo, and only with ZERO commits. `InkRouter` in the
    # InkRouter org is exactly that today: a name somebody reserved, which is
    # not the same as a project somebody started.
    target = Path(url) if local else repository
    empty = _local_remote_is_empty(target) if local else _remote_is_empty(target)
    if empty is None:
        return False
    if not (reuse_empty_repo and empty):
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
    print(f"  reuse {target} (zero commits)")
    return True


def _create_holder_remote(args, values: dict, local: bool, url: str,
                          repository: str, reuse: bool) -> None:
    """Create the holder's remote — a bare local repository, or a GitHub
    repository — unless an existing empty one is being reused.

    Split from `cmd_init` for #136.
    """
    print("\ncreating the holder")
    if reuse:
        return
    if local:
        Path(url).parent.mkdir(parents=True, exist_ok=True)
        run(["git", "init", "-q", "--bare", "-b", args.tracking_branch, url])
        print(f"  bare  {url}")
    else:
        run(["gh", "repo", "create", repository, f"--{args.visibility}",
             "--description",
             f"{values['FAMILY_NAME']} — family holder: the "
             f"{values['FAMILY_ID']} projects, pinned as submodules"])
        print(f"  gh    {repository} ({args.visibility})")


def _create_holder_worktree(args, work: Path, values: dict, shape_commit: str,
                            repository: str, url: str) -> int | None:
    """Materialize the holder, make its first commit, and push it.

    `None` on success (push succeeded, or `--no-push`); an int is the exit
    code `cmd_init` should return right away. Split from `cmd_init` for
    #136: a push that fails here is reported with the ruleset hint and its
    own exit code, handled here rather than left for `main`'s generic "a
    git or gh command failed".
    """
    work.mkdir(parents=True, exist_ok=True)
    materialized = materialize_family_root(SHAPE_ROOT, work, values)
    run(["git", "init", "-q", "-b", args.tracking_branch, str(work)])
    # Every file the materializer wrote is FORCED past the operator's own
    # excludes (#175); see `stage_written`.
    stage_written(work, materialized.written)
    env_commit(work,
               f"Create the {values['FAMILY_NAME']} family holder\n\n"
               f"A HOLDER, not a project: no spec leg, no code leg. It pins "
               f"member assembly roots under {MEMBERS_DIR}/ and carries the "
               f"utilities to fetch and bootstrap them together (Brett Heap, "
               f"2026-09-04).\n\nShape {SHAPE_REPOSITORY} @ {shape_commit}.\n"
               "Membership confers nothing.\n")
    run(["git", "remote", "add", "origin", url], cwd=work)
    if args.no_push:
        return None
    try:
        run(["git", "push", "-q", "-u", "origin", args.tracking_branch],
            cwd=work)
    except CommandFailed as exc:
        print(exc.loudly("pushing the family holder"), file=sys.stderr)
        print(RULESET_HINT.format(work=work, repo=repository,
                                  role="family"), file=sys.stderr)
        return 2
    return None


def _finish_holder_remote(args, repository: str, topic: str,
                          local: bool) -> None:
    """Set the holder's topic and print the private-visibility secrets hint.

    Neither applies to a local (no-network) remote. Split from `cmd_init`
    for #136.
    """
    if local:
        return
    run(["gh", "repo", "edit", repository, "--add-topic", topic])
    print(f"  topic     {topic} set on the holder")
    if args.visibility in ("private", "internal"):
        print(f"NOTE {repository} is {args.visibility} and its members will "
              "be too: give it a way to read them — a GitHub App "
              "(SHAPE_LEGS_APP_ID + SHAPE_LEGS_APP_PRIVATE_KEY, preferred) or "
              "a SHAPE_LEGS_TOKEN PAT with contents:read on the members AND "
              "their legs — or the `validate` check cannot check them out.")
        hint = free_plan_secret_hint(
            args.org, repository, f"{repository} and its members are")
        if hint:
            print(hint)


def _print_next_steps(args, work: Path, folder: Path | None) -> None:
    """The NEXT STEPS block `init` ends with.

    Split from `cmd_init` for #136.
    """
    print(f"""
NEXT STEPS

    {PYTHON} {Path(__file__).name} add --family-root {work} \\
        --member {args.org}/<Project>
    cd {work} && make siblings

`add` mounts the member at {MEMBERS_DIR}/<Project>, records its pin, and
writes ONE commit; land it as a pull request. `make siblings` then puts each
member's WORKING clone beside the holder, in the family folder, on its
tracking branch.

TWO COPIES OF EVERY MEMBER, on purpose: pinned and DETACHED inside the holder
under {MEMBERS_DIR}/ (what `make bootstrap` and `make validate` read), and a
working clone BESIDE the holder — that second one is where you work, and
`family.py bump` is how the family follows it.

family folder  {folder if folder is not None else work.parent}
holder         {work}
""")


def cmd_init(args) -> int:
    family, family_id, topic = _checked_family_identity(args)
    created_by = _creator_name(args)
    local, repository, url = _holder_remote(args, family)
    shape_commit, shape_tree = _shape_snapshot()
    values = _template_values(args, family, family_id, repository, url,
                              created_by, shape_commit, shape_tree)

    folder, holder = _checked_landing(args, family)
    _print_init_plan(values, repository, url, shape_commit, shape_tree,
                     folder, holder, local, topic, args.reuse_empty_repo)
    if args.dry_run:
        print("\n--dry-run: nothing was created.")
        return 0

    work = _prepare_landing_dir(folder, holder)
    reuse = _checked_reuse(args.reuse_empty_repo, local, url, repository)
    _create_holder_remote(args, values, local, url, repository, reuse)

    code = _create_holder_worktree(args, work, values, shape_commit,
                                   repository, url)
    if code is not None:
        return code
    head = git_out(["rev-parse", "HEAD"], cwd=work)[:12]
    print(f"  holder    {head} -> {url}")
    _finish_holder_remote(args, repository, topic, local)
    _print_next_steps(args, work, folder)
    return 0


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------
#
# CHECK BEFORE MOUNT, UNWIND AFTER IT (#203). `add` used to run `git submodule
# add` FIRST and only then ask whether `--at` was a commit and whether the
# member had a `project.yaml`, and neither refusal undid the mount. A leg, or a
# short `--at`, left a staged gitlink, a staged `.gitmodules` section and a
# cached object store behind; the next `add` of a DIFFERENT member then
# committed the refused one's `.gitmodules` section under its own title,
# because `_commit_one` commits the working-tree state of `.gitmodules` whole,
# and `validate-family.py` and the doctor both passed the result. So every
# refusal `add` makes is now asked before the holder is touched — the
# holder's own (`_checked_add_target`) and the member's (`_probe_member`, of a
# throwaway clone) — and whatever still fails after the mount is undone by
# `MountRollback`, which says what it put back.


#: Said when the member cannot be read, which is what a PRIVATE member looks
#: like from a machine that has no credential for it.
UNREADABLE_HINT = ("The member must be readable from here. If it is PRIVATE, "
                   "check `gh auth status` or your SSH key; a family cannot "
                   "pin what it cannot read.")


def _rmtree(path: Path) -> None:
    """`shutil.rmtree` that also works over a git object store on Windows.

    Both trees `add` deletes are object stores — the throwaway clone, and the
    `.git/modules/<path>` of a mount it is undoing — and git writes loose
    objects and packs READ-ONLY, which Windows refuses to unlink: the plain
    call raises PermissionError there and succeeds everywhere else. The
    handler is the one `setup-project.py` carries, which a one-file installer
    cannot share. `onexc` where it exists, because `onerror` is deprecated
    from 3.12 and its warning would land on this command's own stderr;
    `onerror` on the 3.9 this standard still runs on.
    """
    def clear_readonly(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=clear_readonly)
    else:  # pragma: no cover - the spelling before 3.12
        shutil.rmtree(path, onerror=clear_readonly)


def _module_dir(root: Path, path: str) -> tuple[str, Path]:
    """`(as git spells it, on disk)`: where the holder keeps the object store
    of the submodule at `path`.

    ASKED OF GIT, NOT ASSUMED (#203). `.git/modules/<path>` is right for a
    holder that is an ordinary clone and wrong for one that is a LINKED
    WORKTREE — a lane's usual way of opening a pull request — where `.git` is
    a file and git keeps the store under `.git/worktrees/<name>/modules/`.
    `git rev-parse --git-path` answers for both, so the refusal that names a
    cached store and the unwind that deletes the one a refused run made look
    where `git submodule add` writes. For an ordinary clone the answer is the
    `.git/modules/<path>` this tool has always named.
    """
    shown = git_out(["rev-parse", "--git-path", f"modules/{path}"], cwd=root)
    return shown, root / shown


#: How a refusal names an index entry by its mode, as `adopt-project.py`
#: names one; any other mode is a file.
INDEX_ENTRY_KINDS = {0o160000: "a submodule", 0o120000: "a symlink"}


def _index_records(root: Path) -> dict[bytes, list[bytes]]:
    """Every entry of the holder's index, `{name: its records}`: one record
    per stage, each as `git ls-files -s -z` prints it, which is the form
    `git update-index --index-info` takes back.

    THE WHOLE INDEX, WITH NO PATHSPEC, so no pathspec setting in the
    environment can narrow what is read. `_index_entries` picks a mount
    path's entries out of it, and `MountRollback` compares all of it, before
    the mount and after the unwind (#302). `-z`, for a name git would
    otherwise quote.
    """
    listed = git_out(["ls-files", "-s", "-z"], cwd=root, binary=True)
    records: dict[bytes, list[bytes]] = {}
    for record in listed.split(b"\0"):
        if record:
            records.setdefault(record.partition(b"\t")[2], []).append(record)
    return records


def _index_entries(root: Path, path: str) -> list[tuple[str, str]]:
    """`(name, kind)` of every entry the holder's index holds AT `path` or
    UNDER it, IN ANY CASE: what `git submodule add` refuses, without
    `--force`, as "already exists in the index", and what a clone on a
    case-insensitive disk takes for the same path. One per name, whatever
    its stages, spelled as the index spells it.

    ANY CASE, ON EVERY DISK, whatever the holder's `core.ignorecase` says,
    as adopt's `_index_entries` asks (#302). A holder is cloned on macOS and
    Windows too, where `Members/IRRS` and `members/IRRS` are ONE path. With
    `core.ignorecase` set, `git submodule add` staged the member's own files
    under the variant the index held (an entry `Members/IRRS/README` had 19
    staged beside it). The commit's pathspec then matched nothing, and the
    unwind, which asks for exact names, left all 19 staged while saying the
    holder was exactly as it was.

    LITERAL, AND SO ASKED WITH NO PATHSPEC AT ALL. git refuses
    `--literal-pathspecs` beside `--icase-pathspecs`, and `--icase-pathspecs`
    alone reads `*` and `?` as globs. `:(literal,icase)` magic is not parsed
    at all when the environment sets `GIT_LITERAL_PATHSPECS`, and then it
    matches nothing, without a word. So the whole index is listed and the
    names are compared here, with ASCII case folded, as git's own `icase`
    folds it: `members/IRRS` selects `MEMBERS/irrs` and `members/IRRS/...`,
    and never `members/IRRSX`, nor a `members/IRR?` that a glob would match.
    """
    wanted = path.encode("utf-8").lower()
    entries = []
    for name, records in _index_records(root).items():
        folded = name.lower()
        if folded == wanted or folded.startswith(wanted + b"/"):
            entries.append((name.decode("utf-8", "replace"),
                            INDEX_ENTRY_KINDS.get(
                                int(records[0].split()[0], 8), "a file")))
    return entries


def _submodule_paths(root: Path) -> dict[str, str]:
    """`{name: path}` of every submodule the holder's `.gitmodules` names,
    read from where `git submodule add` reads it: the file in the working
    tree, or the index's copy where there is none, or HEAD's where the index
    has none either."""
    if os.path.lexists(root / GITMODULES):
        source = ["--file", GITMODULES]
    else:
        for spec in (f":{GITMODULES}", f"HEAD:{GITMODULES}"):
            try:
                source = ["--blob", git_out(["rev-parse", "-q", "--verify",
                                             spec], cwd=root)]
                break
            except Refusal:
                continue
        else:
            return {}
    listed = git_out(["config", "-z", *source, "--list"], cwd=root,
                     binary=True)
    found = {}
    for record in listed.split(b"\0"):
        key, _, value = record.decode("utf-8",
                                      "surrogateescape").partition("\n")
        section, _, variable = key.rpartition(".")
        if section.startswith("submodule.") and variable == "path":
            found[section[len("submodule."):]] = value
    return found


def _checked_mount_path(root: Path, project: str, path: str) -> None:
    """Every refusal about the MOUNT PATH, made before the member is read or
    anything is mounted (#242).

    `git submodule add` makes each of these refusals on its own. But the
    mount passes `--force`, to get past the operator's ignore rules (see
    `_mount_and_pin`), and `--force` turns them off or moves them to after
    the clone. So each is asked here first, the way git asks it, and named:

    - SOMETHING AT THE PATH. On disk, by `lexists`, so a dangling link counts
      as well as a directory a half-finished add or a hand left there. In
      the INDEX, any entry at the path or under it, with nothing on disk:
      given `--force`, git accepts a gitlink there and replaces it with the
      member's, and whatever the human had staged is gone without a word.
    - GIT'S OWN DRY RUN, `git add --dry-run --ignore-missing` of the path —
      the check `--force` skips — made here with `-f`, so an ignore rule
      passes it and nothing else does. It refuses a path beyond a symbolic
      link (a `members` that links elsewhere, through which `--force` had
      the member CLONED, outside the holder) and one inside a submodule (a
      `members` that is one, into whose tree it was cloned) before git said
      no. It fails for reasons that are not about the path as well — the
      dry run takes `index.lock`, so a held one refuses it — so the
      remediation quotes git's own line and presumes no cause.
    - THE NAME. git names a submodule after its path; git 2.51 and later
      refuse a name another path already has, and, given `--force`, mount
      the member under a new one (`members/IRRS1`) instead. Git before 2.51
      rewrites the other submodule's section to point at the member. Both
      are refused here, on every git.
    """
    if os.path.lexists(root / path):
        raise Refusal(
            "member-path-taken",
            f"{path} already exists in the family root but no `members:` row "
            "names it",
            "Remediation: this is a half-finished add or a hand-made "
            "directory. Remove it (`git rm -r` if it is tracked), then re-run.")
    held = _index_entries(root, path)
    if held:
        at_it = [entry for entry in held if entry[0].lower() == path.lower()]
        name, kind = (at_it or held)[0]
        more = f" and {len(held) - 1} more" if len(held) > 1 else ""
        # IN ANY CASE, AND NAMED AS THE INDEX SPELLS IT (#302). `git rm`
        # matches a pathspec case-sensitively even with `core.ignorecase`
        # set, so the remediation names each spelling of the mount path the
        # index holds. That is `path` itself when the case is the same. A
        # removal staged under another spelling is one the add's commit,
        # whose pathspec is `path`, does not carry, so where HEAD holds the
        # variant it is committed first, or the holder keeps both.
        variant = name[:len(path)]
        spelled = " ".join(sorted({entry[0][:len(path)] for entry in held}))
        raise Refusal(
            "member-path-taken",
            f"the family root's index holds `{name}` ({kind}){more}"
            + ("" if at_it else f" under {variant}")
            + ("" if variant == path else
               f", the same path as {path} on a case-insensitive disk")
            + f", though nothing is at {path} on disk and no `members:` row "
            "names it",
            "Remediation: this is a half-finished add or a hand edit. `git rm "
            f"-r --cached -- {spelled}` takes it out of the index and touches "
            "no file; "
            + ("then " if spelled == path else
               "where HEAD holds it too, commit that removal first, since the "
               f"add's own commit names {path} alone and would keep both "
               "spellings; then ")
            + "re-run.")
    try:
        run(["git", "--literal-pathspecs", "add", "--dry-run",
             "--ignore-missing", "-f", "--no-warn-embedded-repo", "--", path],
            cwd=root)
    except CommandFailed as exc:
        raise Refusal(
            "member-path-unaddable",
            f"git will not add the mount path {path}: {_reason(exc)}",
            "Remediation: that is git's own check of the path, made before "
            "anything is cloned or written, and git's line quoted above says "
            "why it refused. Every member is mounted under `members/`, which "
            "must be a plain directory of the holder's own: where git names a "
            "symbolic link there, replace it with a directory, and where it "
            "names a submodule, take that out (`git rm`); anything else it "
            "names, a held `index.lock` say, is fixed where git says. Then "
            "re-run.") from exc
    other = _submodule_paths(root).get(path)
    if other is not None and other != path:
        raise Refusal(
            "member-name-taken",
            f"{GITMODULES} already gives the name `{path}` to the submodule "
            f"at {other}, and that is the name git gives {project}'s mount",
            "Remediation: git names a submodule after its path, so that name "
            "is a member's. Give that submodule a name of its own, or take it "
            "out, by hand, then re-run. Mounting over the name would rewrite "
            f"its section to point at {project} (git before 2.51), or mount "
            f"{project} under another name this tool does not follow (git "
            "2.51 and later, with the `--force` this tool mounts with).")


def _checked_add_target(family: Family, repository: str, project: str,
                        path: str, at: str | None) -> str | None:
    """Every refusal `add` makes about the HOLDER and its own arguments,
    asked before the member is read or anything is mounted. Returns `--at`
    checked and lowercased, or None.

    WHETHER THE FAMILY ALREADY PINS THIS PROJECT IS ASKED OF `family.holding`
    (#206), which takes the repository as well as the name: a case-variant
    spelling of a member the family holds, or another row pinning the same
    repository, is refused here too, before anything is mounted.

    `--at`'s SHAPE IS ASKED HERE (#203). It used to be asked after the mount,
    so `--at abc1234` — a short sha, the commonest typo there is — left the
    member mounted and staged, and the corrected command was then refused
    twice more (`member-path-taken`, `member-git-dir-cached`) before it could
    run. Whether the commit is IN the member is `_probe_commit`'s question,
    because only the member's own objects can answer it.
    """
    held = family.holding(repository, project)
    if held is not None:
        raise Refusal(
            "member-already-present",
            f"{project} is already a member of {family.data.get('name')}: "
            f"the row {held.get('project')} pins {held.get('repository')}",
            "Remediation: `family.py bump --member "
            f"{held.get('project')} --to <commit>` moves an existing member; "
            "`remove` takes it out. Adding it twice is not a way to move it.")
    # Everything the mount's `--force` would otherwise let past git, but the
    # cached store, which is asked below (#242).
    _checked_mount_path(family.root, project, path)
    # `git rm` deliberately leaves a removed submodule's OBJECT STORE behind,
    # so a member that was removed and is being added back trips `git
    # submodule add` with an error about a git directory found locally. That
    # cache is not this tool's to delete — it may hold commits somebody made
    # inside the mount and never pushed — so the exit is named instead of
    # taken. And it is named HERE, before the mount, because the mount passes
    # `--force`, which REACTIVATES such a store instead of refusing it and
    # pins whatever commit the store has checked out, not the member's
    # (#242).
    # NAMED IN POSIX: git spells this `.git/modules/<path>`, and so does the
    # human who retypes the remediation below.
    _, cached = _module_dir(family.root, path)
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
    # The pin is written into a `members:` block `write_members` has to be
    # able to find; a manifest it would refuse is refused NOW, while there is
    # nothing to undo.
    family.rewritten(family.members)
    if not at:
        return None
    commit = checked_value("--at", at)
    if not COMMIT_RE.match(commit):
        raise Refusal(
            "member-at-not-a-commit",
            f"--at {at!r} is not a 40-hex commit",
            "Remediation: pass the full 40 characters. A tag can be moved "
            "and a commit cannot, which is why a pin is never a tag.")
    return commit.lower()


def _probe_member(url: str, protocol: list[str], repository: str,
                  project: str, at: str | None) -> str:
    """The commit `add` will pin, with every refusal about the MEMBER asked
    of a throwaway clone BEFORE the holder is touched (#203).

    A BARE CLONE IN A TEMPORARY DIRECTORY, OUTSIDE THE HOLDER. The commit is
    resolved and the manifest read from the member's own objects — no
    checkout, and nothing of the holder's: not its index, not `.gitmodules`,
    not `.git/` — and the clone is deleted whatever the answer. Only a member
    that passes is mounted.

    TWO CLONES OF THE MEMBER, ON PURPOSE. A member is an assembly root, whose
    legs are submodules a clone does not fetch, so the second clone is
    small; and it buys a mount that `git submodule add` makes exactly as it
    always has — on its branch, which is the state the doctor's `members`
    row says a fresh `add` leaves. The mount is read again afterwards and
    that reading is what the pin records, so a member that moved between the
    two clones is pinned where the mount found it, or refused there and
    unwound.
    """
    scratch = Path(tempfile.mkdtemp(prefix="openreposhape-member-"))
    try:
        clone = scratch / "member.git"
        run(["git", *protocol, "clone", "-q", "--bare", "--", url, str(clone)])
        commit = _probe_commit(clone, repository, at)
        _probe_manifest(clone, commit, scratch / "project", project,
                        repository)
        return commit
    finally:
        try:
            _rmtree(scratch)
        except OSError as exc:
            print(f"  note: the throwaway clone {scratch} could not be "
                  f"deleted ({exc.strerror or exc}); nothing in the holder "
                  "refers to it", file=sys.stderr)


def _probe_commit(clone: Path, repository: str, at: str | None) -> str:
    """`--at`, or the member's tip, as a commit of the member — or the
    refusal saying which of the two it was not.

    `^{commit}` PEELS: an annotated tag's own sha resolves to the commit it
    tags, which is what checking it out pinned before; a tree's or a blob's
    resolves to nothing and is refused. A clone fetches every branch and tag,
    which is everything a mount of the member could ever check out.

    A TREE OR A BLOB IS NAMED AS ONE. Its sha is in the member — `git
    ls-tree` and `git rev-parse <commit>:<path>` print them — so "not a
    commit any branch or tag reaches" would send the human to look for a
    push that is not missing. `^{}` peels any tag first, so a tag of a tree
    is named by the tree it tags.
    """
    wanted = at or "HEAD"
    try:
        return git_out(["rev-parse", "-q", "--verify", f"{wanted}^{{commit}}"],
                       cwd=clone).lower()
    except Refusal as exc:
        missing = exc
    if at is None:
        raise Refusal(
            "member-no-tip",
            f"{repository} has no commit on its default branch to pin: it is "
            "empty, or its HEAD names a branch it does not have",
            "Remediation: a family pins a commit, so the member must have "
            "one. Scaffold or adopt the project first, which gives it one, "
            "or pass `--at <40-hex commit>` naming a commit it already "
            "has.") from missing
    try:
        kind = git_out(["cat-file", "-t", f"{at}^{{}}"], cwd=clone)
    except Refusal:
        kind = None
    if kind in ("tree", "blob"):
        raise Refusal(
            "member-at-unknown",
            f"--at {at} names a {kind} in {repository}, not a commit",
            "Remediation: pass the commit itself — `git log --format=%H` in "
            "the member lists them. A tree's or a blob's sha is part of a "
            "commit and never one, and a pin is a commit or it is "
            "nothing.") from missing
    raise Refusal(
        "member-at-unknown",
        f"--at {at} is not a commit any branch or tag of {repository} "
        "reaches",
        "Remediation: check the commit — it belongs to the member's ASSEMBLY "
        "ROOT, not to one of its legs — and that it has been pushed. A pin "
        "the rest of the world cannot fetch is a family the rest of the "
        "world cannot bootstrap.") from missing


def _probe_manifest(clone: Path, commit: str, scratch: Path, project: str,
                    repository: str) -> None:
    """`_read_member_project`, asked of the member's objects at `commit`
    rather than of a checkout.

    THE SAME FUNCTION, SO THE SAME REFUSALS. The one file is copied out of
    the clone into a directory of its own and read by the function the mount
    is read with, so `member-not-a-project`, `member-manifest-unreadable`,
    `member-bad-id` and `load_yaml`'s own refusals are the ones a human has
    always been given, word for word, with the file named as `<repository> @
    <commit>:project.yaml` instead of by a temporary path. A `project.yaml`
    that is a directory or a submodule is no file at all, which is what a
    checkout's `is_file()` says about it too.

    A SYMLINK IS LEFT TO THE MOUNT. A checkout reads THROUGH a link and an
    object store holds only the link's text, so a linked `project.yaml` is
    not judged here: the mount's own reading judges it, and a refusal there
    is unwound like any other.
    """
    listed = git_out(["ls-tree", "-z", commit, "--", "project.yaml"],
                     cwd=clone, binary=True)
    mode, kind, oid = (listed.split(b"\t", 1)[0].split() + [b""] * 3)[:3]
    if mode == b"120000":
        return
    scratch.mkdir()
    if kind == b"blob":
        (scratch / "project.yaml").write_bytes(
            git_out(["cat-file", "blob", oid.decode("ascii")], cwd=clone,
                    binary=True))
    _read_member_project(scratch, project, repository,
                         shown=f"{repository} @ {commit[:12]}:project.yaml")


def _git_input(args: list[str], cwd: Path, data: bytes) -> None:
    """`git <args>`, reading `data` on stdin as BYTES.

    Bytes, never text: these are index records, and a text-mode pipe is
    re-encoded and, on Windows, has its line endings rewritten on the way to
    a program that reads every byte of a record as part of it.
    """
    command = ["git", *args]
    check_program(command)
    proc = subprocess.run(command, cwd=str(cwd), input=data,
                          capture_output=True, check=False)
    if proc.returncode != 0:
        raise CommandFailed(command, cwd, proc.returncode,
                            (proc.stderr + proc.stdout).decode("utf-8",
                                                               "replace"))


def _reason(exc: BaseException) -> str:
    """One line saying why an unwind step failed, for the sentence that
    names what is left to do by hand — without a full stop of its own,
    because that sentence supplies one after it.

    GIT'S CAUSE, NOT ITS ADVICE. A lock git cannot take is reported as
    `fatal: Unable to create '…/index.lock': File exists.` and then a
    paragraph of advice ending `remove the file manually to continue.`, the
    least informative line of them all. So the first `fatal:` or `error:`
    line is the one quoted, and the last line only when git printed neither.
    """
    if isinstance(exc, CommandFailed):
        lines = [line.strip() for line in exc.output.splitlines()
                 if line.strip()]
        said = next((line for line in lines
                     if line.startswith(("fatal:", "error:"))),
                    lines[-1] if lines else f"exit {exc.code}")
        text = f"`{' '.join(exc.args_list)}`: {said}"
    elif isinstance(exc, Refusal):
        text = exc.detail
    else:
        text = getattr(exc, "strerror", None) or str(exc)
    return text.rstrip().rstrip(".")


class _EntryNotRestored(Exception):
    """A file `undo` put back ON DISK whose INDEX ENTRY it could not put
    back — a held `index.lock` refuses the second and not the first — so
    the sentence can say which half is left instead of calling the bytes
    unrestored."""

    def __init__(self, name: str, bytes_restored: bool,
                 cause: BaseException) -> None:
        super().__init__(name)
        self.name = name
        self.bytes_restored = bytes_restored
        self.cause = cause


def _ended(text: str) -> str:
    """`text` ending in a full stop, so a sentence can follow it."""
    text = text.rstrip()
    return text if text.endswith((".", "!", "?")) else text + "."


class MountRollback:
    """Everything `add` changes in the holder once it mounts, and how to put
    the holder back (#203).

    ALL OF IT. `git submodule add` writes the member's working tree at
    `members/<Project>` (making `members/` for the first member), its object
    store under the holder's git directory, a staged gitlink, a staged
    section in `.gitmodules` (making the file for the first member) and a
    `submodule.<path>` registration in the holder's `.git/config`; `add` then
    rewrites `family.yaml`, and `_commit_one` stages it. Each of those is
    recorded BEFORE the mount and put back by `undo`, so a refusal after the
    mount leaves no half-added member for the next `add`'s commit to carry.

    ONLY WHAT THIS RUN MADE IS DELETED. A directory is removed only if it did
    not exist when the record was taken — and `add` refuses before the mount
    when either of the two does — and a parent only if it is empty, as
    `update-shape.py`'s `Rollback` treats one: a directory that is not empty
    holds something nobody here wrote. The two files go back to the bytes AND
    the index entries they had, not to HEAD's, so whatever a human had
    staged in either before running `add` is still staged after it.

    NEVER OVER A COMMIT THAT LANDED. HEAD is recorded too, and if it has
    moved the one commit happened: undoing the tree under it would leave a
    working copy that contradicts its own history, so nothing is undone and
    the sentence says so.

    "EXACTLY AS IT WAS" ONLY FOR WHAT WAS COMPARED (#302). Each step puts
    back what it recorded, by its exact name. git can stage under a name no
    step asks for: with `core.ignorecase` set, a mount whose directory the
    index already holds in another case is staged in that case, and the
    commit's pathspec then matches nothing. So the WHOLE index is recorded
    too, and `undo` compares it after its steps. Only when the two agree
    does the sentence say the holder is as it was. When they do not, it
    names what differs and sends the human to `git status`, and the one
    command it names, `git rm -r --cached`, touches no file.
    """

    def __init__(self, root: Path, path: str) -> None:
        self.root = root
        self.path = path
        #: What `add` was doing, for the loud block a failed git command
        #: gets; `_mount_and_pin` moves it on before each step.
        self.step = f"mounting {path}"
        #: None in a holder with NO COMMIT YET (#203), which `add` gives its
        #: root commit exactly as it always has: `-q --verify` exits 1 there
        #: without a word, where a bare `rev-parse HEAD` refused the whole
        #: add as `git-failed`. `undo` reads HEAD through the same `_head`
        #: and takes a commit it names now, and did not then, as the one
        #: commit having landed.
        self.head = self._head()
        #: The whole index, which `undo` compares with the index after its
        #: steps (#302).
        self.index = _index_records(root)
        self.gitlink = self._entries(path)
        self.files = {name: (self._bytes(name), self._entries(name))
                      for name in (GITMODULES, MANIFEST)}
        self.registration = self._registration()
        module_shown, module = _module_dir(root, path)
        #: `(directory, as it is named, its parents that do not exist yet)`
        #: for each of the two directories the mount makes, if it is absent
        #: now. Parents nearest first, which is the order they empty in.
        self.trees = [(tree, shown, [p for p in tree.parents
                                     if not p.exists()])
                      for tree, shown in ((root / path, path),
                                          (module, module_shown))
                      if not tree.exists()]

    def _head(self) -> str | None:
        """The commit HEAD names, or None if it names none — read ONE way,
        so what `undo` compares is what the constructor recorded.

        `-q --verify HEAD^{commit}` PEELS and VERIFIES: it answers with the
        commit an annotated tag names, and with nothing at all for a branch
        that does not exist yet or names an object that is missing. A bare
        `rev-parse HEAD` answers with the tag's own sha, or with the missing
        object's, and the two readings then differ in a holder nothing has
        committed to: `undo` took that for the one commit having landed, said
        so, and left the half-added member staged (#203).
        """
        try:
            return git_out(["rev-parse", "-q", "--verify", "HEAD^{commit}"],
                           cwd=self.root)
        except Refusal:
            return None

    def _bytes(self, name: str) -> bytes | None:
        target = self.root / name
        return target.read_bytes() if target.is_file() else None

    def _entries(self, name: str) -> list[bytes]:
        """The index records for exactly `name`, one per stage, in the form
        `git update-index --index-info` takes back — so a path that was
        conflicted is put back conflicted."""
        listed = git_out(["ls-files", "-s", "-z", "--", name], cwd=self.root,
                         binary=True)
        exact = name.encode("utf-8")
        return [record for record in listed.split(b"\0")
                if record.partition(b"\t")[2] == exact]

    def _registration(self) -> list[tuple[str, str]]:
        """The holder's own `submodule.<path>.*` keys and values, in order.

        LISTED AND FILTERED HERE, NOT MATCHED BY A PATTERN: a member's name
        may carry a `.`, so `submodule.members/IRQS.v2.url` belongs to a
        different member that a prefix would take for this one. A variable
        name is everything after a key's LAST dot, so the section is
        everything before it.
        """
        listed = git_out(["config", "--local", "--list", "-z"],
                         cwd=self.root, binary=True)
        section = f"submodule.{self.path}"
        found = []
        for record in listed.split(b"\0"):
            key, _, value = record.decode("utf-8",
                                          "surrogateescape").partition("\n")
            if key.rpartition(".")[0] == section:
                found.append((key, value))
        return found

    def _undo_entries(self, name: str, entries: list[bytes]) -> bool:
        if self._entries(name) == entries:
            return False
        run(["git", "update-index", "--force-remove", "--", name],
            cwd=self.root)
        if entries:
            _git_input(["update-index", "-z", "--index-info"], self.root,
                       b"".join(entry + b"\0" for entry in entries))
        return True

    def _undo_file(self, name: str, data: bytes | None,
                   entries: list[bytes]) -> bool:
        changed = self._bytes(name) != data
        if changed and data is None:
            (self.root / name).unlink()
        elif changed:
            (self.root / name).write_bytes(data)
        try:
            return self._undo_entries(name, entries) or changed
        except (CommandFailed, Refusal, OSError) as exc:
            raise _EntryNotRestored(name, changed, exc) from exc

    def _undo_tree(self, tree: Path, parents: list[Path]) -> bool:
        removed = tree.exists()
        if removed:
            _rmtree(tree)
        for parent in parents:
            if parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
        return removed

    def _undo_registration(self) -> bool:
        now = self._registration()
        if now == self.registration:
            return False
        if now:
            run(["git", "config", "--local", "--remove-section",
                 f"submodule.{self.path}"], cwd=self.root)
        for key, value in self.registration:
            run(["git", "config", "--local", "--add", key, value],
                cwd=self.root)
        return True

    def _index_moved(self) -> str:
        """What the index holds now that it did not hold before the mount,
        what it has lost, and what it holds staged differently, each named
        up to five times in the index's order. Returns "" when the index is
        the one the constructor recorded (#302)."""
        now = _index_records(self.root)
        if now == self.index:
            return ""
        parts = []
        for said, names in (
                ("new in it", [name for name in now
                               if name not in self.index]),
                ("gone from it", [name for name in self.index
                                  if name not in now]),
                ("staged differently", [name for name in now
                                        if name in self.index
                                        and now[name] != self.index[name]])):
            if names:
                shown = ", ".join(f"`{name.decode('utf-8', 'replace')}`"
                                  for name in names[:5])
                more = f" and {len(names) - 5} more" if len(names) > 5 else ""
                parts.append(f"{said}: {shown}{more}")
        return "; ".join(parts)

    def undo(self) -> str:
        """Put the holder back. Returns the sentence a refusal ends with:
        what was put back, or — if any of it could not be — what is left,
        and, where the index is not the one recorded, what differs in it."""
        # NO HEAD IS NOT A COMMIT THAT LANDED: a holder with no commit yet
        # reads None before and after, and so does one whose HEAD names no
        # readable commit. Only a commit HEAD now names and did not before
        # is the one commit having landed.
        now = self._head()
        if now is not None and now != self.head:
            return (" The commit had already landed, so nothing was undone: "
                    "`git log -1` in the holder shows it.")
        steps = [(f"the gitlink at {self.path} unstaged", self._undo_entries,
                  (self.path, self.gitlink))]
        steps += [(f"{shown} removed", self._undo_tree, (tree, parents))
                  for tree, shown, parents in self.trees]
        steps += [((f"{name} restored byte for byte" if data is not None else
                    f"{name} removed, as there was none before"),
                   self._undo_file, (name, data, entries))
                  for name, (data, entries) in self.files.items()]
        # A REGISTRATION THE HOLDER ALREADY HAD is put back, not dropped —
        # `git submodule add` rewrites its `url` in place — and the sentence
        # says which of the two happened.
        steps.append(((f"`submodule.{self.path}` restored in the holder's "
                       "git config" if self.registration else
                       f"`submodule.{self.path}` dropped from the holder's "
                       "git config"), self._undo_registration, ()))
        restored, failed = [], []
        for said, action, arguments in steps:
            try:
                if action(*arguments):
                    restored.append(said)
            except _EntryNotRestored as exc:
                if exc.bytes_restored:
                    restored.append(said)
                failed.append(f"the index entry of {exc.name} put back as it "
                              f"was: {_reason(exc.cause)}")
            except (CommandFailed, Refusal, OSError) as exc:
                failed.append(f"{said}: {_reason(exc)}")
        # THE WHOLE INDEX, once every step has been asked (#302). A partial
        # unwind already says it is one, and names `git status`. An index
        # that cannot be read back is one more thing not shown to be back.
        moved = ""
        if not failed:
            try:
                moved = self._index_moved()
            except Refusal as exc:
                failed.append("the index read back to compare with the one "
                              f"recorded before the mount: {_reason(exc)}")
        if failed:
            return (" The mount was undone only in part"
                    + (" (" + ", ".join(restored) + ")" if restored else "")
                    + "; NOT " + "; NOT ".join(failed) + ". Put those back "
                    "by hand — `git status` shows what is left — before "
                    "running `add` again.")
        if moved:
            return ((" Nothing was committed: the mount has been undone — "
                     + ", ".join(restored) + " —" if restored else
                     " Nothing was committed,")
                    + " but the holder's index is NOT as it was before this "
                    f"command ({moved}). Put it back before running `add` "
                    "again: `git status` shows each difference, and `git rm "
                    "-r --cached -- <path>` takes a path new in it back out "
                    "and touches no file.")
        if restored:
            return (" Nothing was added: the mount has been undone — "
                    + ", ".join(restored) + " — and the holder is exactly as "
                    "it was before this command.")
        return " Nothing was added, and nothing in the holder had changed."


def _mount_and_pin(family: Family, repository: str, project: str, path: str,
                   url: str, protocol: list[str], at: str | None,
                   rollback: MountRollback) -> tuple[str, str, str, str]:
    """The part of `add` that writes: `git submodule add`, the pin and the
    ONE commit. Returns `(commit, digest, project id, the new HEAD)`.

    Every step runs inside the caller's `MountRollback` and moves its `step`
    on first, so a git command that fails is named by what `add` was doing.
    The member is read AGAIN here, from the mount, and this reading is what
    the pin records: `_probe_member` asked the same questions moments ago, so
    a refusal here means the member moved in between, and it is unwound like
    any other.
    """
    rollback.step = f"mounting {repository}"
    # `--force`, git's documented way past an ignore rule (#242). `members/`
    # is a fixed path and `add` has no flag that moves it, so an operator
    # whose own excludes name `members`, `members/`, `*` or the member's name
    # had the mount refused for every member of every family, with nothing in
    # the invocation to change: by git's dry run before the clone, or — for a
    # rule like `IRRS/`, which matches only once the clone is a directory —
    # by git's last `git add` after it. That is #174 (adopt, fixed by #200)
    # and #229 (scaffold) on the family side. A gitlink once added is
    # tracked, so no rule touches it again; `_commit_one` is the second
    # reader of the rules and is forced past them too.
    # `--force` changes four more things, and each is refused before the
    # member is read, by `_checked_add_target`, while the holder is exactly as
    # the human left it:
    #   - a `.git/modules/<path>` already there is REACTIVATED, and the
    #     gitlink is that store's commit, not the member's:
    #     `member-git-dir-cached`, at the store git's own `--git-path` names,
    #     a linked worktree's included.
    #   - a GITLINK the index already holds at the path is accepted, and a
    #     repository already checked out there is REUSED instead of cloned:
    #     `member-path-taken`, for anything at the path on disk (a dangling
    #     link included) and for any index entry at it or under it.
    #   - git's early dry run is skipped, so a path beyond a symlink, or
    #     inside a submodule, had the member CLONED through the link or into
    #     the submodule before git refused it: `member-path-unaddable` makes
    #     that same dry run first, with `-f`, so an ignore rule passes it and
    #     nothing else does.
    #   - git 2.51 and later RENAME a mount whose name another path already
    #     has (`members/IRRS1`), giving it a store and a registration
    #     `MountRollback` would not find: `member-name-taken`.
    run(["git", *protocol, "submodule", "add", "-q", "--force", "--", url,
         path], cwd=family.root)
    member = family.root / path
    if at:
        rollback.step = f"checking {repository} out at {at[:12]}"
        run(["git", "checkout", "-q", at], cwd=member)
    commit = git_out(["rev-parse", "HEAD"], cwd=member).lower()
    project_id = _read_member_project(member, project, repository)
    digest = tree_digest(member, commit)
    row = _member_row(project, project_id, repository, commit, digest)
    rows = sorted(family.members + [row], key=lambda r: str(r["project"]))
    # A FAILED WRITE IS A REFUSAL, NEVER A TRACEBACK — the rule
    # `update-shape.py` keeps for the same reason: the caller unwinds on a
    # refusal, and an `OSError` reaching `main` would print a traceback over
    # the one sentence that says the holder was put back.
    try:
        family.write_members(rows)
    except OSError as exc:
        raise Refusal(
            "family-manifest-unwritable",
            f"{MANIFEST} could not be rewritten with {project}'s pin: "
            f"{exc.strerror or exc}",
            f"Remediation: make {MANIFEST} writable, and check the disk has "
            "room, then run the same command again.") from exc

    rollback.step = f"committing {project} to the family"
    head = _commit_one(
        family.root,
        f"Add {project} to the {family.data.get('name')} family\n\n"
        f"{repository} @ {commit[:12]} is mounted at {path} and pinned in "
        f"{MANIFEST} — the gitlink and `members[].pin.commit` in ONE commit, "
        "which is the whole of the lockstep rule.\n\nIt remains a whole "
        "project: its own assembly root, its own legs, its own gate. "
        "Membership confers nothing.\n",
        [GITMODULES, path, MANIFEST])
    return commit, digest, project_id, head


def cmd_add(args) -> int:
    """Mount one member and pin it in ONE commit, or refuse and leave the
    holder exactly as it was (#203).

    IN THIS ORDER, AND ONLY THIS ORDER: the holder's refusals
    (`_checked_add_target`), then the member's (`_probe_member`, of a
    throwaway clone), and only then the mount, the pin and the commit
    (`_mount_and_pin`), inside a `MountRollback` that puts the holder back
    if anything still fails and says what it put back.
    """
    family = Family.open(args.family_root)
    repository, project = _checked_member(args.member)
    path = f"{MEMBERS_DIR}/{project}"
    at = _checked_add_target(family, repository, project, path, args.at)

    url = _member_url(repository, args.local_remote_dir)
    protocol = FILE_PROTOCOL if args.local_remote_dir is not None else []
    # FLUSHED, so that in a log holding both streams the line saying what
    # was being done comes before a refusal of it, not after.
    print(f"checking {repository} before mounting it", flush=True)
    try:
        commit = _probe_member(url, protocol, repository, project, at)
    except CommandFailed as exc:
        print(exc.loudly(f"reading {repository}"), file=sys.stderr)
        print(UNREADABLE_HINT, file=sys.stderr)
        return 2

    rollback = MountRollback(family.root, path)
    print(f"mounting {repository} at {path}", flush=True)
    try:
        commit, digest, project_id, head = _mount_and_pin(
            family, repository, project, path, url, protocol,
            commit if at else None, rollback)
    except Refusal as exc:
        exc.detail = _ended(exc.detail) + rollback.undo()
        raise
    except CommandFailed as exc:
        undone = rollback.undo()
        print(exc.loudly(rollback.step), file=sys.stderr)
        print(undone.strip(), file=sys.stderr)
        return 2
    except BaseException:
        print(rollback.undo().strip(), file=sys.stderr)
        raise
    print(f"  {project:<16} {commit[:12]} tree {digest[:12]}… "
          f"(project {project_id})")
    print(f"  committed {head[:12]}: .gitmodules, {path}, {MANIFEST}")
    print(f"\nNEXT  git -C {family.root} push -u origin <branch> && open a "
          "pull request")
    return 0


# ---------------------------------------------------------------------------
# bump
# ---------------------------------------------------------------------------


def _nothing_to_record(root: Path, paths: list[str]) -> bool:
    """Whether `git commit -- <paths>` has nothing to record: the gitlink the
    member stands at and the manifest as rewritten are what `HEAD` already has.

    ASKED OF GIT, AFTER THE SAME REWRITE THE COMMIT WOULD CARRY (#210), and
    not read off the pin alone. A row that names `--to` is not by itself a bump
    with nothing in it: `validate-family.py` names `bump --to <commit>` as the
    repair for a gitlink that disagrees with the pin and for a digest that does
    not recompute, and both leave the row's commit equal to `--to`; and so does
    a bump an earlier run wrote and staged but never committed. In each of
    them `git diff` finds something, and the commit goes ahead.
    `--ignore-submodules=dirty` is what `git commit` itself ignores: files the
    member holds untracked or modified are not a thing this commit records,
    its HEAD is. The caller has staged the gitlink first, as `_commit_one`
    would, so a stray one in the index is not a difference. Exit 1 is git's
    "there is a difference"; any other failure is a real one and propagates.
    """
    try:
        run(["git", "diff", "--quiet", "--ignore-submodules=dirty", "HEAD",
             "--", *paths], cwd=root)
    except CommandFailed as exc:
        if exc.code == 1:
            return False
        raise
    return True


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
    project = str(row["project"])
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
    original = family.path.read_bytes()
    family.write_members(rows)
    # THE GITLINK IS RE-STAGED BEFORE GIT IS ASKED, as `_commit_one` does it
    # first anyway. An index still holding a stray gitlink somebody staged and
    # never committed makes `git diff HEAD` find a difference the commit then
    # does not find, and a bump to the pinned commit ended in the refusal #210
    # is about. `validate-family.py` reads the index first, reports
    # `member-gitlink-mismatch` and names this very command as the repair. The
    # checkout above already moved the member to `--to`, so this stages that
    # and nothing else: a submodule path stages its gitlink, never the
    # member's files, and the manifest's own index state is left as found.
    # FORCED, as `_commit_one`'s stage is (#242): this is a third reader of
    # the operator's excludes, and under one naming `members` or `*` a plain
    # `git add` refused the gitlink here, before the commit was reached, and
    # `bump` exited 2. `-f` reaches the one path named, taken literally.
    force_stage(family.root, [path])
    if _nothing_to_record(family.root, [path, MANIFEST]):
        # The same sentence `bump-leg.py` answers the same re-run with, and
        # exit 1, which is what this file's docstring says `nothing` is. The
        # manifest goes back byte for byte as it was found: the rewrite
        # recorded nothing, and an uncommitted hand edit it happened to
        # overwrite is not this run's to discard.
        family.path.write_bytes(original)
        print(f"  {project:<16} {was[:12]} -> {commit[:12]} tree "
              f"{digest[:12]}…")
        print(f"\nnothing to do: {row['repository']} is already pinned at "
              f"{commit[:12]} and every fact agrees.")
        return 1

    head = _commit_one(
        family.root,
        f"Bump {project} to {commit[:12]} in the "
        f"{family.data.get('name')} family\n\n"
        f"{was[:12]} -> {commit[:12]}. The gitlink at {path} and "
        f"`members[].pin` in {MANIFEST} move in ONE commit, which is what "
        "`validate-family.py` checks and what a reviewer reads as one "
        "change.\n",
        [path, MANIFEST], trailers=args.trailer)
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
    project = str(row["project"])
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
        [GITMODULES, path, MANIFEST], add=[GITMODULES, MANIFEST])
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
# siblings
# ---------------------------------------------------------------------------


def cmd_siblings(args) -> int:
    """The holder's `make siblings`, run from a checkout of the standard.

    ONE IMPLEMENTATION, TWO ENTRY POINTS (Brett Heap, 2026-09-09, ruling 1b:
    *"One implementation, two entry points… No second code path."*). The
    implementation is `templates/family-root/scripts/siblings.py`, the file a
    holder CARRIES and its Makefile calls; this subcommand runs that same file
    against `--family-root`, exactly as the root `bootstrap` shim runs the
    assembly root's `scripts/bootstrap.py`. That is what makes it work before
    the holder is cloned anywhere else — the standard has the utility, the
    holder is only where it usually lives.

    `runpy` rather than an import: the script is a `__main__` program that
    ends in `sys.exit(main())`, so its exit code is the one this process
    exits with, unchanged and unrewritten.
    """
    root = Path(args.family_root).expanduser().resolve()
    if not (root / MANIFEST).is_file():
        raise Refusal(
            "family-root-missing",
            f"{root / MANIFEST} does not exist, so this is not a family root",
            "Remediation: `family.py init --org <org> --family <Name>` creates "
            "one; point --family-root at the HOLDER (the `<Family>/<Family>` "
            "clone), not at the family folder around it.")
    if not SIBLINGS_SCRIPT.is_file():
        raise Refusal(
            "siblings-script-missing",
            f"{SIBLINGS_SCRIPT} is missing from this checkout of the standard",
            "Remediation: this subcommand runs the holder's own copy of that "
            "file and has no second implementation to fall back on. Re-clone "
            "openRepoShape, or run `make siblings` in the holder, which uses "
            "its own copy.")
    sys.argv = ["siblings", "--root", str(root),
                *(["--dry-run"] if args.dry_run else [])]
    runpy.run_path(str(SIBLINGS_SCRIPT), run_name="__main__")
    return 0  # pragma: no cover - the script exits before returning here


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
    init.add_argument("--into", type=Path, default=None, metavar="DIR",
                      help="the PARENT directory the family folder is made "
                           "in (default: the directory you are standing in). "
                           "The holder lands at <into>/<Family>/<Family>, "
                           "beside where `make siblings` clones the members.")
    init.add_argument("--work-dir", type=Path, default=None,
                      help="THE OVERRIDE: land the holder at "
                           "<work-dir>/<Family> and make no family folder at "
                           "all. Mutually exclusive with --into.")
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
    bump.add_argument("--trailer", action="append", metavar='"KEY: VALUE"',
                      default=[], type=trailer_line,
                      help="append this `<Key>: <value>` line to the commit "
                           "this writes; repeatable, kept in the order given")
    bump.set_defaults(func=cmd_bump)

    remove = subparsers.add_parser("remove", help="unmount a member")
    remove.add_argument("--family-root", required=True)
    remove.add_argument("--member", required=True, metavar="PROJECT")
    remove.set_defaults(func=cmd_remove)

    siblings = subparsers.add_parser(
        "siblings",
        help="clone every member BESIDE the holder, on its tracking branch")
    siblings.add_argument("--family-root", required=True,
                          help="the HOLDER (`<Family>/<Family>`); the "
                               "siblings are placed in the folder around it")
    siblings.add_argument("--dry-run", action="store_true",
                          help="say what would be cloned and fetched; clone "
                               "nothing, fetch nothing, move nothing")
    siblings.set_defaults(func=cmd_siblings)
    return parser


def main(argv: list[str] | None = None) -> int:
    # FIRST, so that every `print` after it -- `--help` included -- escapes
    # a name stdout cannot encode rather than raising on it (#214).
    escape_what_stdout_cannot_encode()
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
