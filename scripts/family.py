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

EXIT CODES: 0 done, or a `--dry-run` printed what it would do · 1 nothing to
do · 2 a refusal, and a refusal made before the first write is the same
refusal under `--dry-run`. Every subcommand takes `--dry-run`: `init`, `add`,
`bump`, `remove` and `siblings` (#326).
`siblings` exits with the template script's own code, unchanged. A `bump` whose
commit would record nothing — the member is already pinned at `--to`, in the
gitlink and in `family.yaml` alike — is `nothing`: it says `nothing to do`, as
`bump-leg.py` does for a leg, and writes no commit; its dry run says the same
and exits 1 too.

A DRY RUN ASKS WHAT THE REAL RUN ASKS, AND STOPS BEFORE ITS FIRST WRITE
(#326). `bump --dry-run` makes every refusal `bump` makes before its first
write and FETCHES the member, as a real bump does: a fetch writes into the
member's object store, which nothing in the holder records, and it is how
`--to` is resolved and digested. It then reads the member's `project.yaml`
and tree from those objects, as the real run does before its checkout
(#365), so the two refuse alike, and prints the row it would write and the
trailers its commit would end with; it never checks the member out, rewrites
`family.yaml`, stages or commits. `remove --dry-run` makes every refusal
`remove` makes before its first write and prints the row, the gitlink, the
`.gitmodules` section, the holder's registration of the member and the
directory it would remove, and runs no git command that writes.
`add --dry-run` makes every refusal `add` makes before its first write, the
member's own included, and READS THE MEMBER to ask them, as a real add does:
a bare clone from its remote into a temporary directory outside the holder,
deleted whatever the answer. It reads the member once more the same way, at
the commit that clone resolved, for the `id:` and the digest the row records,
and prints that row, the gitlink, the `.gitmodules` section, the registration
and the directory the mount would make, and the trailers its commit would end
with; it never runs `git submodule add` and writes nothing of the holder's.

WHAT ONLY THE WRITE ITSELF CAN ANSWER IS NOT ASKED. A member whose local
changes `git checkout` would refuse to overwrite gets exit 0 and a row from
`bump --dry-run`, and exit 2 from the real `bump`'s checkout; an unmerged
`.gitmodules` is refused by the real `remove`'s `git rm` and not by its dry
run; a `.gitmodules` the index or HEAD holds and the work tree does not is
refused by the real `add`'s `git submodule add`, and its dry run exits 0 with
a note that says so; and a held `index.lock` is refused by the real `remove`
before it unmounts anything (#365) and not by its dry run, because a lock is
a fact about the moment, not about the holder. Each is git's own refusal or
one made before the first write, and a real run puts back what it wrote
first. A `project.yaml` that is a symbolic link is read through the link
by a real `add`'s mount and by nothing before it, so `add --dry-run` leaves
its `id:` to the real run and says so; what fails only once the mount is made
is unwound by the real run and never reached by its dry run.

A REFUSED `bump` OR `remove` PUTS THE HOLDER BACK (#365), as a refused `add`
does (#203). `PinRollback` records what each one writes before the first
write and puts it back on any failure after it, and the refusal ends with
the sentence that names what was put back, or what is left and the commands
that put it back, in order. The exit is still 2, and a failed git command is
still quoted as it ran. `remove`'s checkout comes back only from an object
store git already has, never from a remote: where git has none, the sentence
says the checkout is not back. `remove` also refuses, under `--dry-run` as
well, a `.gitmodules` that gives the member's path to more than one
submodule (#360): `git rm` takes out the section of the one git finds for
that path, and its commit used to keep the others.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import runpy
import shlex
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
#:
#: EACH NAME BEGINS WITH A LETTER OR A DIGIT, as the holder's own
#: `validate-family.py` requires of a row's `repository:` (`QUALIFIED_RE`,
#: `member-repository`), because `add` writes `--member` verbatim as that row.
#: Without it `testorg/_Zed`, `testorg/.Zed`, `_org/Zed` and `.org/Zed` were
#: mounted, pinned and committed with exit 0, and the gate the holder ships
#: failed the commit `add` had just reported (#366). THIS IS A THIRD SPELLING
#: OF THAT PATTERN, not an import of it: the validator reads the holder's own
#: copy of `repo_shape.py`, so a constant moved there would reach an existing
#: holder only through `update-shape.py`. `tests/test_family_member_name.py`
#: reads every spelling and fails when they differ, so it is one rule kept in
#: three places and never three rules. Change one and the test names the rest.
MEMBER_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$")

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


def _member_path(project: str, row: dict | None = None) -> str:
    """The ONE path a member has, `members/<project>` (#299); given the
    member's row, that path or the refusal that says the row names another.

    THE TOOL WRITES `path:` ITSELF, as this and nothing else (`_member_row`),
    and `bump` and `remove` used to read it back and hand it to git as it
    stood. Git reads a path as a pathspec: `path: members/*` made `remove
    --member Atlas` exit 0 with one commit that unmounted EVERY member while
    dropping only Atlas's row, and `path: .` made it `git rm -r -f` the
    holder's own files and die on the missing manifest. A hand edit is outside
    the supported path (AGENTS.md: do not hand-edit the `members:` block), and
    the rule this asks is the one `validate-family.py` already records as
    `member-path`; but the validator runs after a commit, in CI and in the
    doctor, never in front of these two verbs, so they ask it themselves,
    BEFORE ANY GIT CALL AND ANY WRITE.

    A row with no `path:` keeps defaulting to it, as it always has, and the
    comparison is EXACT, as the validator's is: `members/IRRS/`, `members/irrs`
    and a neighbour's path are each a different string and each refused. The
    validator keeps its own spelling of this rule on purpose. It ships INTO
    every holder, as `repo_shape.py` does, so sharing it would move every
    holder's pin for a refusal of a hand edit.

    A ROW'S PROJECT HAS TO BE A DIRECTORY NAME TOO. Its `path:` is checked
    against `members/<project>`, so a row that says `project: ..` and `path:
    members/..` is EQUAL to the expected path and passed the comparison, and
    `remove` then ran `git rm -r -f -- members/..` over the holder's root,
    while `project: .` and `path: members/.` unmounted every member in one
    commit naming one (#299). Each takes two hand edits, the project and the
    path, and `add` cannot write either: `_checked_member` refuses a `.` or
    `..` segment as `member-malformed` before the member is read, so
    `_member_row` is never reached with one. A project that
    does not make `members/<project>` ONE directory directly under `members/`
    has no path of its own to be compared with, so it is refused here, under
    the same code, only when a row is given: what `add` writes (`_member_row`,
    no row) is as it was.
    """
    expected = f"{MEMBERS_DIR}/{project}"
    if row is not None and (project in ("", ".", "..") or "/" in project):
        names = {".": f"the {MEMBERS_DIR} directory itself",
                 "..": "the holder's root"}.get(
            project, f"no single directory directly under {MEMBERS_DIR}/")
        raise Refusal(
            "member-path",
            f"{project!r} is not a project name: its path would be "
            f"{expected!r}, which is {names}, not a member. Acting on it "
            "would unmount more than one member or remove the holder's own "
            "files, so no git command was run and nothing was written.",
            "Remediation: this tool never writes such a row, so it is a hand "
            f"edit. Restore {MANIFEST} from git (`git checkout -- "
            f"{MANIFEST}` if the edit is not committed), or put the row's "
            "`project:` and `path:` back as the tool wrote them "
            f"(`project: <Project>`, `path: {MEMBERS_DIR}/<Project>`), then "
            "run the command again naming that member.")
    declared = expected if row is None else str(row.get("path") or expected)
    if declared != expected:
        raise Refusal(
            "member-path",
            f"{project}: path is {declared!r} in {MANIFEST}, expected "
            f"{expected!r}. Git would read that value as a pathspec, so no "
            "git command was run and nothing was written.",
            "Remediation: this tool writes that field itself, so a different "
            f"value is a hand edit. Put `path: {expected}` back in "
            f"{MANIFEST}, or `git checkout -- {MANIFEST}` if the edit is not "
            "committed, then run the same command again.")
    return expected


def _member_row(project: str, project_id: str, repository: str, commit: str,
                digest: str) -> dict:
    return {
        "project": project,
        "id": project_id,
        "repository": repository,
        "path": _member_path(project),
        "pin": {"revision_kind": "commit", "commit": commit,
                "tree_sha256": digest},
    }


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------


def _checked_member(raw: str) -> tuple[str, str]:
    """`--member` as `(org/Project, Project)`."""
    name = raw.strip()
    # A SEGMENT THAT IS `.` OR `..` IS A DIRECTORY REFERENCE, NOT A NAME
    # (#299), AND IT IS SAID SO BEFORE THE PATTERN IS ASKED (#366). `<org>/..`
    # once matched `MEMBER_RE`, and its mount path `members/..` is the
    # holder's root: on a fresh holder `_checked_mount_path` found the root's
    # own files "in the index" under it and told the human to `git rm -r
    # --cached -- members/..`, which stages the deletion of every file the
    # holder has. The pattern refuses both now, for beginning with a dot, but
    # in its general sentence, and what is wrong with `.` and `..` is that
    # they are no name at all, which that sentence does not say. So the clause
    # stays, FIRST, for the more specific one; it is read only on a name with
    # a `/`, since a bare `.` has no owner to blame and the general sentence
    # asks for one. An owner of `.` or `..` names no account.
    owner, slash, project = name.partition("/")
    for which, segment in (("owner", owner), ("project", project)):
        if not slash or segment not in (".", ".."):
            continue
        if which == "owner":
            why = "no organisation or account is called that"
        else:
            where = ("the members directory itself" if segment == "."
                     else "the holder's root")
            why = f"it would mount at {MEMBERS_DIR}/{segment}, {where}"
        raise Refusal(
            "member-malformed",
            f"--member {raw!r} has `{segment}` as its {which}, which is a "
            f"directory reference and not a name: {why}",
            "Remediation: name the repository as `<org>/<Project>`, each a "
            "real name beginning with a letter or a digit; `.` and `..` are "
            "neither, though a name may contain a dot after that (`Ze.d`).")
    # BEFORE THE MEMBER IS READ, a name the holder's own gate would refuse is
    # refused here (#366): `add` writes `--member` verbatim as the row's
    # `repository:`, and `validate-family.py` fails a row whose owner or
    # project begins with anything but a letter or a digit.
    if not MEMBER_RE.match(name):
        raise Refusal(
            "member-malformed",
            f"--member {raw!r} is not `<org>/<Project>`: each name begins "
            "with a letter or a digit and goes on with letters, digits, `.`, "
            "`_` and `-`",
            "Remediation: name the owner — a family's members may live in "
            "another organisation, so there is no owner to assume — and "
            "begin neither name with `.`, `_` or `-`: the holder's "
            "`validate-family.py` refuses such a `repository:` as "
            "`member-repository`, so a commit that wrote one would fail the "
            "gate the holder ships. For `remove` and `bump`, the bare "
            "`<Project>` is what is wanted.")
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

    THE COMMIT READS THEM LITERALLY TOO (#299). The stage above was literal
    and `git commit -- <paths>` was not, so a path that is a glob to git
    committed whatever else it matched: with `members/*` named, the move of
    every OTHER member's gitlink somebody had staged went into this commit
    beside the one it was for. `bump` and `remove` hand it a path that is
    always `members/<project>` (`_member_path`); the magic is the guard that
    does not depend on that being so.

    PER-PATHSPEC `:(literal)`, NOT THE GLOBAL `--literal-pathspecs`, ON THIS
    ONE CALL. The global option works by putting `GIT_LITERAL_PATHSPECS=1` in
    git's environment, and every child of `git commit` inherits it: the
    holder's `pre-commit`, `commit-msg` and `post-commit` hooks, its own or the
    operator's `core.hooksPath`. A hook that picks the staged files with a
    glob (`git diff --cached --name-only -- '*.yaml'`) then matched nothing,
    and a linter behind it checked nothing, on every `add`, `bump` and
    `remove` commit. The magic is spelled on each path and reaches no hook. It
    is right for a path `git rm` took out of the index and the tree, which the
    commit still matches in HEAD. `deinit`, `rm` and `diff` run no COMMIT
    hooks, so they keep the global option (`rm`, like `force_stage`'s `add`,
    writes the index, so a `post-index-change` hook still sees the variable
    after them; that is theirs and predates this).

    THE CALLER'S OWN `GIT_LITERAL_PATHSPECS` IS DROPPED FROM THIS ONE COMMIT'S
    ENVIRONMENT. The variable turns pathspec magic OFF, and `:(literal)` is
    magic: with it exported (a safety default, or a `family.py` run from a
    hook or alias of a `git --literal-pathspecs` command, which exports it to
    its children) git took `:(literal)family.yaml` as a file of that name,
    found none, and every `add`, `bump` and `remove` commit failed, `bump` and
    `remove` leaving the pin or the unmount staged with no rollback. The
    commit's paths are literal by their magic and need no help from the
    environment. Only this variable: the other pathspec variables turn magic
    ON or change only how a glob matches, and the magic still reads.
    """
    force_stage(root, paths if add is None else add)
    message, trailer_args = commit_trailers(message, trailers)
    args = ["git", "commit", "-q", "-F", "-", *trailer_args, "--",
            *[f":(literal){path}" for path in paths]]
    check_program(args)
    env = dict(os.environ)
    env.pop("GIT_LITERAL_PATHSPECS", None)
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
# holder's own (`_checked_add_target`), the member's (`_probe_member`, of a
# throwaway clone), and whether the `id` the member's `project.yaml` records
# is one a row already pins (`_checked_member_id`, #330) — and whatever still
# fails after the mount is undone by `MountRollback`, which says what it put
# back.


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
    case-insensitive disk takes for the same path. One per record, as git
    lists them, so a conflicted path counts once per stage, and each is
    spelled as the index spells it.

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
    # ASCII only, as git's `icase` folds; APFS and NTFS fold more (`ſ` is
    # `s` to them), which no git check of a pathspec follows either.
    wanted = path.encode("utf-8").lower()
    entries = []
    for name, records in _index_records(root).items():
        folded = name.lower()
        if folded == wanted or folded.startswith(wanted + b"/"):
            entries.extend((name.decode("utf-8", "replace"),
                            INDEX_ENTRY_KINDS.get(int(record.split()[0], 8),
                                                  "a file"))
                           for record in records)
    return entries


def _submodule_paths(
        root: Path) -> dict[str, tuple[str, str | None, tuple[str, ...]]]:
    """`{name: (path, url, keys)}` of every submodule the holder's
    `.gitmodules` names, read from where `git submodule add` reads it: the
    file in the working tree, or the index's copy where there is none, or
    HEAD's where the index has none either. `url` is None for a section that
    gives no url; a section that gives no path is no submodule and is not
    listed. `keys` is every key the section holds, path and url included,
    once each, in the order git lists them.

    `add`'s ONE READER OF THE FILE, for both questions `_checked_mount_path`
    asks of it: the path a NAME is given (`member-name-taken`, #242), and
    the names a PATH is given, each with its url and its keys
    (`member-path-registered`, #300). A second reader for those could read a
    second copy of the file.

    IT IS NOT THE FILE'S ONLY READER. `remove` reads the WORK TREE's copy,
    which is the one `git rm` edits, twice more, for questions this one does
    not answer: `_gitmodules_names` models git's own path lookup (a name
    keeps its LAST `path`, and a name that moves on takes the old path out of
    git's map), which is the name `git rm` drops and the name whose object
    store `git submodule update` uses; and `_sections_giving` names every
    section that gives a path in ANY of its `path` lines (#360). All three
    read it through `git config --list`, never through a parser of this
    tool's.
    """
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
    found: dict[str, dict[str, str]] = {}
    for record in listed.split(b"\0"):
        key, _, value = record.decode("utf-8",
                                      "surrogateescape").partition("\n")
        section, _, variable = key.rpartition(".")
        if section.startswith("submodule."):
            found.setdefault(section[len("submodule."):], {})[variable] = value
    return {name: (keys["path"], keys.get("url"), tuple(keys))
            for name, keys in found.items() if "path" in keys}


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
    - THE PATH UNDER ANOTHER NAME (#300), the mirror of the name: a section
      that already gives the mount path to a submodule named something
      else — a half-removed member, a hand edit, a merge that kept both
      sides. This one git does not make at all, with `--force` or without
      it: it writes the member's own section beside that one, so `add`
      committed two sections for one path, `validate-family.py` passed
      them, and a recursive clone followed the LATER of the two, the other
      one's url as soon as an edit put it last. It is refused, naming the
      section and its url, and left exactly as it is: it is somebody's
      registration, and dropping or rewriting it as part of the add would
      decide whose without asking. The path is compared exactly; git reads
      `.gitmodules` that way too.
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
        # whose pathspec is `path`, does not carry. So where HEAD holds the
        # variant, the removal is committed first. Otherwise HEAD keeps the
        # variant beside the member, or, with `core.ignorecase` set, records
        # the gitlink under a spelling other than `path` (`MEMBERS/ATLAS/...`
        # gave `MEMBERS/Atlas`, and kept its file too), or both, while
        # `.gitmodules` and the manifest say `path`.
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
               f"add's own commit names {path} alone: otherwise HEAD keeps "
               "the other spelling beside the member, or, with "
               "`core.ignorecase` set, records the member's gitlink under a "
               f"spelling other than the {path} that {GITMODULES} and "
               f"{MANIFEST} say, or both; then ")
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
    sections = _submodule_paths(root)
    other = sections.get(path, (None, None))[0]
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
    ghosts = [(name, url, keys) for name, (at, url, keys) in sections.items()
              if at == path and name != path]
    if ghosts:
        named = " and ".join(
            f"`{name}` ({'no url' if url is None else 'url ' + url})"
            for name, url, _ in ghosts)
        # BY KEY, NOT BY SECTION: `--remove-section` cannot address a
        # section whose name holds `]`, nor one whose header a hand spelled
        # `[Submodule "..."]` (git 2.43: `no such section`), while a key
        # reaches every section `git config --list` names. EVERY KEY it
        # holds, not its path and url alone: a `branch`, `shallow` or
        # `update` left behind is inherited by the submodule a later `add`
        # gives that name, which git writes into the same section. git
        # drops the header with the last key.
        removal = " and ".join(
            f"`git config -f {GITMODULES} --unset-all "
            f"{shlex.quote('submodule.' + name + '.' + key)}`"
            for name, _, keys in ghosts for key in keys)
        raise Refusal(
            "member-path-registered",
            f"{GITMODULES} already gives the path {path} to the submodule"
            + ("s" if len(ghosts) > 1 else "") + f" named {named}, and that "
            f"is the path {project} is mounted at",
            "Remediation: git would write the member's own section beside "
            "it, and a recursive clone of the holder follows whichever "
            "section for that path comes last in the file. A section "
            "somebody wrote is not this tool's to drop or rewrite, so take it "
            f"out by hand, in a POSIX shell — {removal}, then `git add "
            f"{GITMODULES}` — and re-run."
            + ("" if os.path.lexists(root / GITMODULES) else
               f" With no {GITMODULES} in the working tree, put back the "
               f"copy git read first: `git checkout -- {GITMODULES}` (the "
               f"index's), or `git checkout HEAD -- {GITMODULES}`."))


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


def _checked_member_id(family: Family, repository: str, project: str,
                       project_id: str) -> None:
    """Refused when a row already records the `id` the member's own
    `project.yaml` does (#330): the project is a member under another name.

    `family.holding` compares NAMES — the row's project and its repository —
    and a repository renamed at the forge keeps its `project.yaml`, so
    `--member testorg/Atlas2` on a family that pins `testorg/Atlas` passed it,
    was mounted, and committed a second row recording id `atlas`, which the
    holder's own `validate-family.py` then refused as `member-duplicate-id`
    and its CI went red. The id is what the validator compares, because it is
    the project's own name for itself, so it is asked here too, under the
    validator's code, BEFORE ANYTHING IS MOUNTED: `cmd_add` asks it of the
    id `_probe_member` read from the throwaway clone, and `_mount_and_pin`
    asks it again of the mount's reading, which is what the row records — a
    linked `project.yaml` the probe leaves to the mount, or a member that
    moved in between, is refused there and unwound like any other refusal.

    THE ROWS THE VALIDATOR ASKS, ASKED THE WAY IT ASKS THEM
    (`_check_member_ids_unique` in the holder's copy): the row's `id:` as a
    string, compared exactly; a row with no `project:` or no `id:`, and a row
    whose `project:` an earlier row already spells exactly, are other
    findings' and are skipped. So `add` refuses what the gate would refuse
    and nothing it would pass. The validator keeps its own spelling of the
    rule, as it keeps `member-path`'s: it ships INTO every holder, and a
    shared copy would move every holder's pin.
    """
    projects: set[str] = set()
    for row in family.members:
        name = row.get("project")
        if not isinstance(name, str) or not name or name in projects:
            continue
        projects.add(name)
        if not row.get("id") or str(row["id"]) != project_id:
            continue
        raise Refusal(
            "member-duplicate-id",
            f"{project} is already a member of {family.data.get('name')} "
            f"under another name: {repository}'s project.yaml records id "
            f"{project_id!r}, and the row {name} pins "
            f"{row.get('repository')} with that id. Adding it would pin one "
            "project twice, which `validate-family.py` refuses",
            "Remediation: a family pins each project once. If "
            f"{repository} is {row.get('repository')} renamed at the forge, "
            f"`family.py remove --member {name}` takes the old row out and "
            "this `add` then pins it under the new name; `family.py bump "
            f"--member {name} --to <commit>` moves the row that is there "
            "instead. Two projects that record one id are a fault in one of "
            "their `project.yaml` files, mended in that project, not in the "
            "family.")


def _probe_member(url: str, protocol: list[str], repository: str,
                  project: str, at: str | None) -> tuple[str, str | None]:
    """`(the commit add will pin, the id its project.yaml records)`, with
    every refusal about the MEMBER asked of a throwaway clone BEFORE the
    holder is touched (#203). The id is None only for a linked
    `project.yaml`, which `_probe_manifest` leaves to the mount.

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
        return commit, _probe_manifest(clone, commit, scratch / "project",
                                       project, repository)
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
                    repository: str) -> str | None:
    """`_read_member_project`, asked of the member's objects at `commit`
    rather than of a checkout: the id it returns, or None for a link.

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
        return None
    scratch.mkdir()
    if kind == b"blob":
        (scratch / "project.yaml").write_bytes(
            git_out(["cat-file", "blob", oid.decode("ascii")], cwd=clone,
                    binary=True))
    return _read_member_project(
        scratch, project, repository,
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
    names what differs and sends the human to `git ls-files -s`, and the one
    command that changes anything, `git rm -r --cached`, touches no file.
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
        # that cannot be read back leaves the steps undone but unconfirmed,
        # and the sentence says exactly that.
        moved, unread = "", None
        if not failed:
            try:
                moved = self._index_moved()
            except Refusal as exc:
                unread = _reason(exc)
        if failed:
            return (" The mount was undone only in part"
                    + (" (" + ", ".join(restored) + ")" if restored else "")
                    + "; NOT " + "; NOT ".join(failed) + ". Put those back "
                    "by hand — `git status` shows what is left — before "
                    "running `add` again.")
        undone = ((" Nothing was committed: the mount has been undone — "
                   + ", ".join(restored) + " —") if restored else
                  " Nothing was committed,")
        # `git ls-files -s` is where both sentences send the human: it lists
        # every record the index holds now, so an entry that is new, or
        # staged differently, can be read there record by record. An entry
        # that is gone is in no listing at all, which is why the sentence
        # names it. `git status` compares the index with HEAD, not with the
        # index before this command, so it is not that comparison either.
        if unread is not None:
            return (undone + " but the holder's index could not be read back "
                    "to confirm it is as it was before this command: "
                    f"{unread}. Check it before running `add` again: `git "
                    "ls-files -s` lists what the index now holds.")
        if moved:
            return (undone + " but the holder's index is NOT as it was before "
                    f"this command ({moved}). Put it back before running "
                    "`add` again: `git ls-files -s` lists what the index now "
                    "holds, and `git rm -r --cached -- <path>` takes a path "
                    "new in it back out and touches no file.")
        if restored:
            return (" Nothing was added: the mount has been undone — "
                    + ", ".join(restored) + " — and the holder is exactly as "
                    "it was before this command.")
        return " Nothing was added, and nothing in the holder had changed."


def _rewrite_members(family: Family, rows: list[dict], what: str) -> None:
    """`family.write_members`, the rows rewritten `what` (`with Atlas's
    pin`), with a failed write made a refusal, `family-manifest-unwritable`,
    and never a traceback.

    ONE SPELLING FOR `add`, `bump` AND `remove` (#365), the rule
    `update-shape.py` keeps for the same reason: each caller puts the holder
    back on a refusal, and an `OSError` reaching `main` would print a
    traceback over the one sentence that says the holder was put back.
    """
    try:
        family.write_members(rows)
    except OSError as exc:
        raise Refusal(
            "family-manifest-unwritable",
            f"{MANIFEST} could not be rewritten {what}: "
            f"{exc.strerror or exc}",
            f"Remediation: make {MANIFEST} writable, and check the disk has "
            "room, then run the same command again.") from exc


def _mount_and_pin(family: Family, repository: str, project: str, path: str,
                   url: str, protocol: list[str], at: str | None,
                   rollback: MountRollback,
                   trailers: list[str] = ()) -> tuple[str, str, str, str]:
    """The part of `add` that writes: `git submodule add`, the pin and the
    ONE commit, ending with `trailers`, as `bump`'s does (#326). Returns
    `(commit, digest, project id, the new HEAD)`.

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
    # Asked again of THIS reading, which is the id the row records (#330).
    _checked_member_id(family, repository, project, project_id)
    digest = tree_digest(member, commit)
    row = _member_row(project, project_id, repository, commit, digest)
    rows = sorted(family.members + [row], key=lambda r: str(r["project"]))
    _rewrite_members(family, rows, f"with {project}'s pin")

    rollback.step = f"committing {project} to the family"
    head = _commit_one(
        family.root,
        f"Add {project} to the {family.data.get('name')} family\n\n"
        f"{repository} @ {commit[:12]} is mounted at {path} and pinned in "
        f"{MANIFEST} — the gitlink and `members[].pin.commit` in ONE commit, "
        "which is the whole of the lockstep rule.\n\nIt remains a whole "
        "project: its own assembly root, its own legs, its own gate. "
        "Membership confers nothing.\n",
        [GITMODULES, path, MANIFEST], trailers=trailers)
    return commit, digest, project_id, head


#: The `id:` `add --dry-run` prints for a member whose `project.yaml` is a
#: symbolic link: the objects hold only the link's text, and only a checkout
#: reads through it, so the id is the real run's to read and none is guessed.
LINKED_ID = "(read through the link by the real run)"


def _resolves(root: Path, spec: str) -> bool:
    """Whether `spec` names an object in the holder (`git rev-parse -q
    --verify`). `git submodule add` asks it of `:.gitmodules` and
    `HEAD:.gitmodules` when the work tree has no `.gitmodules`, and refuses
    to write the file if either answers."""
    try:
        git_out(["rev-parse", "-q", "--verify", spec], cwd=root)
    except Refusal:
        return False
    return True


def _add_dry_run(family: Family, repository: str, project: str, path: str,
                 url: str, protocol: list[str], commit: str, at: str | None,
                 trailers: list[str]) -> int:
    """`add --dry-run` (#326), entered once every refusal `add` makes before
    its first write has been asked — the holder's (`_checked_add_target`),
    the member's (`_probe_member`) and whether the `id:` the probe read is
    one a row already pins (`_checked_member_id`, #330, which `cmd_add` asks
    of the probe's reading before it comes here, so the dry run refuses
    `member-duplicate-id` through the one function the real run does) — and
    before `MountRollback` is taken or anything is mounted: what a real
    `add` would write, and no write to the holder.

    THE MEMBER IS READ A SECOND TIME, AS THE REAL RUN READS IT A SECOND
    TIME. A real `add` reads the member twice: the probe's throwaway clone,
    which asks the refusals, and the mount, whose reading the row records.
    The dry run has no mount, so its second reading is a second throwaway
    clone, made as the probe makes its own: bare, in a temporary directory
    OUTSIDE the holder, and deleted whatever the answer, so nothing the
    holder has is written. It is read at the commit the probe resolved,
    which is the one the mount checks out unless the member moves on in
    between: the `id:` by `_member_id_at`, which reads `project.yaml` with
    the function the mount's checkout is read with, and the digest by
    `tree_digest`, which reads objects and never a checkout, so the digest
    printed is the one the real run computes from the same tree, never a
    guess. The row is `_member_row`'s, as the real run's is.

    A LINKED `project.yaml` IS LEFT TO THE REAL RUN, as the probe leaves it
    to the mount: the objects hold only the link's text and a checkout reads
    through it, so the `id:` is printed as the real run's to read
    (`LINKED_ID`) and never guessed.

    PRINTED, in `bump --dry-run`'s layout: the commit and its digest; the
    gitlink `git submodule add` stages at the path; the `.gitmodules` section
    it writes, under the name git gives it (the path), with the url git is
    handed, and whether the file is new; the registration it writes in the
    holder's `.git/config`, or the one there whose url it rewrites; the
    directory it checks the member out into and the object store it keeps,
    where git keeps it (`_module_dir`); the row as `family.yaml` would carry
    it; and the trailers its commit would end with (`_print_trailers`).

    GIT'S OWN REFUSAL AT THE MOUNT IS NAMED, NOT MADE. With no `.gitmodules`
    in the work tree and one in the index or HEAD, `git submodule add`
    refuses to write the file (`please make sure that the .gitmodules file
    is in the working tree`) before it writes anything, and the real run
    exits 2 there. Only git can say that sentence, so the dry run says what
    will happen in a `note` and how to put the file back, and exits 0, as
    `bump --dry-run` does for the checkout's own refusal.
    """
    scratch = Path(tempfile.mkdtemp(prefix="openreposhape-member-"))
    try:
        clone = scratch / "member.git"
        run(["git", *protocol, "clone", "-q", "--bare", "--", url, str(clone)])
        project_id = _member_id_at(clone, commit, project, repository)
        digest = tree_digest(clone, commit)
    except CommandFailed as exc:
        print(exc.loudly(f"reading {repository}"), file=sys.stderr)
        print(UNREADABLE_HINT, file=sys.stderr)
        return 2
    finally:
        try:
            _rmtree(scratch)
        except OSError as exc:
            print(f"  note: the throwaway clone {scratch} could not be "
                  f"deleted ({exc.strerror or exc}); nothing in the holder "
                  "refers to it", file=sys.stderr)
    root = family.root
    linked = project_id is None
    row = _member_row(project, LINKED_ID if linked else project_id,
                      repository, commit, digest)
    store, _ = _module_dir(root, path)
    print(f"member       {project}  {repository} at {path}")
    print(f"commit       none -> {commit[:12]}")
    print(f"tree         {digest[:12]}… ({digest})")
    if linked:
        print("note         project.yaml is a symbolic link at "
              f"{commit[:12]}, which only a checkout reads through: the real "
              "run reads the `id:` through the link, and the row below leaves "
              "it to that run")
    if at is None:
        print("note         without --at a real add pins the tip it finds "
              f"when it mounts, which is {commit[:12]} unless {repository} "
              f"moves on first; --at {commit} pins this one")
    print(f"gitlink      {path} none -> {commit[:12]}")
    on_disk = os.path.lexists(root / GITMODULES)
    elsewhere = [] if on_disk else [
        where for where, spec in (("the index", f":{GITMODULES}"),
                                  ("HEAD", f"HEAD:{GITMODULES}"))
        if _resolves(root, spec)]
    print(f'gitmodules   [submodule "{path}"]  path {path}, url {url}'
          + ("" if on_disk or elsewhere else f", in a new {GITMODULES}"))
    if elsewhere:
        print(f"note         {GITMODULES} is in {' and '.join(elsewhere)} but "
              "not in the work tree, where `git submodule add` refuses to "
              "write it: the real run exits 2 at its mount with the holder "
              "unchanged. Put back the copy git read first: `git checkout -- "
              f"{GITMODULES}` (the index's), or `git checkout HEAD -- "
              f"{GITMODULES}`")
    print(f'registration [submodule "{path}"] in the holder\'s .git/config, '
          + ("its url rewritten" if _registered(root, path) else "written")
          + " by `git submodule add`")
    print(f"directory    {path}  the member checked out at {commit[:12]}; "
          f"its object store at {store}")
    print(f"row          as {MANIFEST} would carry it:")
    for line in _member_lines(row):
        print(line)
    _print_trailers(trailers)
    print(f"\n--dry-run: nothing was changed in the holder. {repository} was "
          "read from throwaway clones in temporary directories outside the "
          f"holder, now deleted; {GITMODULES}, {MANIFEST}, the index, the "
          "work tree and the holder's git directory are as they were.")
    return 0


def cmd_add(args) -> int:
    """Mount one member and pin it in ONE commit, or refuse and leave the
    holder exactly as it was (#203); or with `--dry-run`, print what it
    would write and change nothing in the holder (#326, `_add_dry_run`).

    IN THIS ORDER, AND ONLY THIS ORDER: the holder's refusals
    (`_checked_add_target`), then the member's (`_probe_member`, of a
    throwaway clone), then the member's id against the rows
    (`_checked_member_id`, #330), and only then the mount, the pin and the
    commit (`_mount_and_pin`), inside a `MountRollback` that puts the holder
    back if anything still fails and says what it put back.

    WHEN TWO APPLY, THE EARLIER ONE IS SAID. The holder's refusals need
    nothing cloned, so they come first: a section under another name that
    already gives the mount path (`member-path-registered`, #300) is refused
    with not one line on stdout even when the member also records an id a
    row pins, and `member-duplicate-id` is said on the re-run, once that
    section is out.
    """
    family = Family.open(args.family_root)
    repository, project = _checked_member(args.member)
    path = _member_path(project)
    at = _checked_add_target(family, repository, project, path, args.at)

    url = _member_url(repository, args.local_remote_dir)
    protocol = FILE_PROTOCOL if args.local_remote_dir is not None else []
    # FLUSHED, so that in a log holding both streams the line saying what
    # was being done comes before a refusal of it, not after.
    print(f"checking {repository} before mounting it", flush=True)
    try:
        commit, probed_id = _probe_member(url, protocol, repository, project,
                                          at)
    except CommandFailed as exc:
        print(exc.loudly(f"reading {repository}"), file=sys.stderr)
        print(UNREADABLE_HINT, file=sys.stderr)
        return 2
    if probed_id is not None:
        _checked_member_id(family, repository, project, probed_id)

    # Every refusal above is the same under `--dry-run`, which leaves here,
    # before `MountRollback` is taken and anything is mounted (#326).
    if args.dry_run:
        return _add_dry_run(family, repository, project, path, url,
                            protocol, commit, at, args.trailer)

    rollback = MountRollback(family.root, path)
    print(f"mounting {repository} at {path}", flush=True)
    try:
        commit, digest, project_id, head = _mount_and_pin(
            family, repository, project, path, url, protocol,
            commit if at else None, rollback, args.trailer)
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
# bump and remove: putting the holder back (#365)
# ---------------------------------------------------------------------------


#: What every git command that puts a checkout back runs with, first on its
#: line (`_offline_git`): no transport at all, a local path's included.
NO_REMOTE = ["-c", "protocol.allow=never"]

#: What `_offline_git` puts in the environment of every git command it runs,
#: over the caller's: no terminal prompt, and an EMPTY `GIT_ALLOW_PROTOCOL`,
#: which allows no transport at all and, unlike `NO_REMOTE`, is not
#: overridden by a `protocol.<name>.allow` set by name or by the caller's own
#: `GIT_ALLOW_PROTOCOL` (review 365-7cca975, NIT-A).
OFFLINE_ENV = {"GIT_TERMINAL_PROMPT": "0", "GIT_ALLOW_PROTOCOL": ""}


def _offline_git(args: list[str], cwd: Path) -> str:
    """`git -c protocol.allow=never <args>` in `cwd`, with `OFFLINE_ENV` in
    its environment (`GIT_TERMINAL_PROMPT=0` and an empty
    `GIT_ALLOW_PROTOCOL`): a git command of the rollback's restore (#365).
    Its output, as `run` returns it; a failure is a `CommandFailed`, as
    `run`'s is.

    THE BACKSTOP UNDER THE STORE CHECK (`_unrestorable`). The rollback runs
    `git submodule update` only where git has the store and the commit, so
    nothing needs a remote; this is for the check being wrong. `-c` reaches
    every git the command starts, through `GIT_CONFIG_PARAMETERS`, the clone
    `git submodule update` would make included, and `protocol.allow=never`
    refuses each transport git would otherwise allow, https, ssh and a
    local path alike; with no terminal prompt, a credential git would ask
    for is a failure, not a wait. `--no-fetch` stops the fetch into a store
    that lacks the commit, and the store is checked before `update` runs at
    all.

    WHY `GIT_ALLOW_PROTOCOL` IS EMPTY HERE. `protocol.allow` yields to a
    `protocol.<name>.allow` set by name and to the caller's
    `GIT_ALLOW_PROTOCOL`, so a person whose environment or configuration
    allows the file protocol, or any other, had `-c protocol.allow=never`
    defeated and a wrong store check cloned from the member's url (measured
    with a local bare repository, review 365-7cca975, NIT-A). The variable
    OVERRIDES both: git then behaves as if `protocol.allow` were `never` and
    each protocol it lists, none here, `always`, whatever the configuration
    says. The restore reads local object stores and needs no transport, so
    nothing is lost; the `-c` and `--no-fetch` guards stay as the layers
    under it.
    """
    command = ["git", *NO_REMOTE, *args]
    check_program(command)
    proc = subprocess.run(command, cwd=str(cwd), capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          check=False, env={**os.environ, **OFFLINE_ENV})
    if proc.returncode != 0:
        raise CommandFailed(command, cwd, proc.returncode,
                            (proc.stderr or "") + (proc.stdout or ""))
    return (proc.stdout or "").strip()


def _store_holds(store: Path, commit: str, work: Path) -> bool:
    """Whether the object store `store` holds `commit`.

    `--work-tree`, a directory this never reads: a submodule's store names
    its checkout in `core.worktree`, and git asked with `--git-dir` alone
    changes into that directory first, and dies where `git rm` deleted it
    (git 2.43, probed for #365). Under the backstop, so that a store that
    fetches what it lacks on demand fetches nothing here either.
    """
    try:
        _offline_git(["--git-dir", str(store), "--work-tree", str(work),
                      "cat-file", "-e", f"{commit}^{{commit}}"], work)
    except CommandFailed:
        return False
    return True


def _store_git_uses(root: Path, path: str) -> tuple[str, Path] | None:
    """`(as git spells it, on disk)` of the object store `git submodule
    update`, run in `root`, keeps for the submodule at `path`, there or not;
    None where no section of the work tree's `.gitmodules` gives git the
    path.

    THE STORE OF THE NAME, NOT OF THE PATH (#365). git keeps a submodule's
    store at `modules/<name>` under the git directory (`_module_dir`, given
    the name), `<name>` being the submodule `.gitmodules` gives the path to:
    git's own path lookup, which `git rm` and `git submodule update` share
    and `_gitmodules_names` models. The two are the same for every member
    `add` mounts and differ once a section is renamed by hand.
    """
    name = _gitmodules_names(root, path)[0]
    return None if name is None else _module_dir(root, name)


def _unrestorable(root: Path, path: str, commit: str | None) -> str | None:
    """Why `git submodule update --init --no-fetch -- <path>`, run in
    `root`, could NOT check `commit` out of an object store git already
    has; None when it could (#365).

    THE STORE GIT WILL USE (`_store_git_uses`), NOT ONE THE ROLLBACK
    RECORDED, because `update` CLONES a store where there is none. The store
    a checkout's own `.git` names is not always that one: a section renamed
    by hand sent `update` to another name's store, absent, and the rollback
    cloned the member from its url while the store it had sat unused; and
    `deinit` moves an embedded `.git` into the name's own, which a check of
    the recorded one called gone. A store that does not hold `commit` is not
    used either: `update` would fetch into it.
    """
    found = _store_git_uses(root, path)
    if found is None:
        return f"no section of {GITMODULES} gives git {path}"
    shown, store = found
    if not store.is_dir():
        return (f"git would check it out of {shown}, which is not there, and "
                "clone it there")
    if commit is not None and not _store_holds(store, commit, root):
        return (f"git would check it out of {shown}, which does not hold "
                f"{commit[:12]}, and fetch it")
    return None


def _member_head(member: Path) -> tuple[str | None, str | None]:
    """`(the commit a checkout stands at, the branch it is on)`, each None
    where there is none: no checkout, no commit yet, a detached HEAD.

    ONLY WHERE THE CHECKOUT HAS A `.git` OF ITS OWN. A directory `git
    submodule deinit` has emptied is a plain directory inside the holder, and
    git asked there answers with the HOLDER's HEAD (git 2.43, probed for
    #365): the rollback would have taken the holder's commit for the
    member's.
    """
    if not os.path.lexists(member / ".git"):
        return None, None
    try:
        at = git_out(["rev-parse", "-q", "--verify", "HEAD^{commit}"],
                     cwd=member).lower()
    except Refusal:
        at = None
    try:
        ref = git_out(["symbolic-ref", "-q", "HEAD"], cwd=member)
    except Refusal:
        ref = ""
    return at, (ref[len("refs/heads/"):] if ref.startswith("refs/heads/")
                else None)


def _head_target(member: Path, at: str, branch: str | None) -> list[str]:
    """What `git checkout -q` is given to put a checkout back at `at`: the
    branch it was on, while that branch still names `at`, with `--` after
    it so a file of the branch's name is never what is checked out; else
    the commit itself."""
    if branch is not None:
        try:
            named = git_out(["rev-parse", "-q", "--verify",
                             f"refs/heads/{branch}^{{commit}}"], cwd=member)
        except Refusal:
            named = ""
        if named.lower() == at:
            return [branch, "--"]
    return [at]


def _head_back(member: Path, at: str | None, branch: str | None) -> bool:
    """Put a checkout back at `at`, on `branch` if it was on one; False when
    it already stands there.

    THE BRANCH TOO, NOT THE COMMIT ALONE. `git submodule add` leaves a new
    member ON its branch, and `bump`'s checkout of `--to`, like the checkout
    `git submodule update` makes, DETACHES it: putting the commit back alone
    would leave the right commit and the branch no longer checked out.
    Under `_offline_git`'s backstop, as every command that puts a checkout
    back runs: a checkout reads only the store, and fetches nothing even
    from a store that fetches what it lacks on demand.
    """
    if at is None or _member_head(member) == (at, branch):
        return False
    _offline_git(["checkout", "-q", *_head_target(member, at, branch)],
                 member)
    return True


def _head_by_hand(path: str, at: str, branch: str | None) -> str:
    """`_head_back` as the human types it in the holder: the branch the
    checkout was on, else the commit. FROM THE RECORD, with no git call: it
    is named when a step failed, often with `path` not on disk at all."""
    target = f"{shlex.quote(branch)} --" if branch is not None else at
    return f"git -C {shlex.quote(path)} checkout -q {target}"


def _entries_by_hand(name: str, entries: list[bytes]) -> str:
    """The command that puts `name`'s index entries back as `entries` holds
    them, typed in the holder: `--cacheinfo` for the one record a path
    usually has (with `--add`, which a path `git rm` took out needs), `git rm
    --cached` for a path the index did not hold, and `--index-info` for the
    records of a conflicted one."""
    quoted = shlex.quote(name)
    if not entries:
        return f"git rm -q --cached -- {quoted}"
    fields = [entry.partition(b"\t")[0].decode("ascii").split()
              for entry in entries]
    if len(fields) == 1 and fields[0][2] == "0":
        mode, oid, _ = fields[0]
        return f"git update-index --add --cacheinfo {mode},{oid},{quoted}"
    records = "".join(f"{mode} {oid} {stage}\\t{name}\\n"
                      for mode, oid, stage in fields)
    return (f"printf {shlex.quote(records.replace('%', '%%'))} | "
            "git update-index --index-info")


class PinRollback:
    """Everything `bump` and `remove` change in the holder once they write,
    and how to put the holder back (#365): `MountRollback`'s rule for `add`
    (#203), for the two verbs that were written before it.

    WHAT EACH ONE WRITES. `bump` checks the member out at `--to`, rewrites
    `family.yaml`, stages the gitlink, then stages the manifest and commits.
    `remove` runs `git submodule deinit -f`, which empties the member's
    checkout and drops its registration from the holder's git config; then
    `git rm`, which unstages the gitlink, deletes the directory and takes
    the member's section out of `.gitmodules`; then it rewrites
    `family.yaml`, stages both files and commits. A holder `pre-commit` hook
    that exits 1, or a lock taken by somebody else, failed either verb after
    those steps, and exit 2 left every one of them in place, with nothing
    said about any of it.

    RECORDED BEFORE THE FIRST WRITE, and put back by `undo` on ANY failure
    after it: the index entries of the gitlink and of each file, picked out
    of the WHOLE index (`_index_records`), so no pathspec setting in the
    environment narrows what is read and no call here names the member's
    path (#299 holds every such call to a literal spelling); each file's
    bytes; and the commit and branch the member's checkout stands at.
    `remove` also records every `submodule.*` key in the holder's git
    config, the member's object store, which of the member's own submodules
    (its legs) are checked out, and whether `git status --ignored` lists
    anything in it.

    `remove`'s CHECKOUT COMES BACK FROM THE STORE GIT KEEPS FOR IT, AND
    NEVER FROM A REMOTE: `git submodule update --init --no-fetch --
    members/<P>`, once the gitlink, `.gitmodules` and the registration are
    back, reconnects that store and checks the gitlink's commit out of it.
    `update` takes the store of the NAME `.gitmodules` gives the path, and
    CLONES one where there is none, so it runs only where that store is
    there and holds the commit (`_unrestorable`), never on the strength of
    the store the checkout's own `.git` named when it was recorded. Where it
    is not, `update` is not run: the directory is made again, empty, as a
    member never checked out has it, and the sentence says the checkout
    comes back only from its remote; where the store its checkout had is
    still there under a name git does not look for (a section renamed by
    hand) and the sentence has named it, it says the checkout can come back
    from that store with no network, or from its remote, and prints no
    command that does either. So too for a member whose
    checkout git could not read before the first write, its store gone: it
    is recorded as one no store is known to hold, and its `remove` goes
    ahead as it always has. Every git command that puts a checkout back runs
    under `_offline_git`'s backstop, and `update` with `--no-fetch`, so a
    store check that is wrong still reaches no remote. The member's branch
    is put back after it, and each leg that was checked out, by the same
    rule, from the stores inside the member's. What `deinit -f` discards —
    changes nobody committed, untracked and ignored files — is in no store,
    so when `git status --ignored` listed anything in the member the
    sentence says that much is gone instead of calling the holder as it was.

    THE REGISTRATION COMES BACK AS THE SAME KEYS, NOT THE SAME BYTES.
    `git config --add` writes a section it puts back LAST in `.git/config`,
    so the sentence says the git config holds the same keys and values and
    does not call it as it was. Its recorded bytes are not written back:
    `deinit` rewrites the file, a `pre-commit` hook or another git command
    can write it while the run goes on, and `update --init` registers a
    name it reads, so nothing shows that the bytes recorded before the first
    write are all the file should hold afterwards.

    NEVER OVER A COMMIT THAT LANDED, and "AS IT WAS" ONLY FOR WHAT WAS
    COMPARED, as `MountRollback` says them. Its steps that do the same thing
    here are borrowed below rather than spelled a second time.

    WHAT IS LEFT IS NAMED WITH THE COMMANDS THAT PUT IT BACK. A step that
    fails — commonly a lock somebody took after the run began, which refuses
    every index write and nothing else — is named with git's own reason, a
    step that needs it is not tried (the checkout needs the gitlink,
    `.gitmodules` and the registration back), and the sentence gives, in
    the order to type them, the commands that do each one by hand.
    """

    _head = MountRollback._head
    _bytes = MountRollback._bytes
    _undo_file = MountRollback._undo_file
    _index_moved = MountRollback._index_moved

    def __init__(self, root: Path, path: str, verb: str,
                 files: tuple[str, ...], *, unmount: bool = False) -> None:
        self.root = root
        self.path = path
        self.verb = verb
        self.unmount = unmount
        self.member = root / path
        #: What the loud block of a failed git command is headed with: the
        #: words `main` has always used, but for `bump`'s checkout, whose
        #: failure has always been named for itself.
        self.step = "a git or gh command failed"
        self.head = self._head()
        self.index = _index_records(root)
        self.gitlink = self.index.get(path.encode("utf-8"), [])
        self.files = {name: (self._bytes(name),
                             self.index.get(name.encode("utf-8"), []))
                      for name in files}
        self.at, self.branch = _member_head(self.member)
        self.registration = self._registration() if unmount else []
        self.existed = self.member.is_dir()
        #: The commit the gitlink names, which `git submodule update` checks
        #: out: its stage-0 record's, or None for one the index holds
        #: conflicted.
        self.pinned = next((fields[1].decode("ascii") for fields in
                            (record.partition(b"\t")[0].split()
                             for record in self.gitlink)
                            if fields[2:] == [b"0"]), None)
        #: Whether `remove` has a checkout to bring back: one with a `.git`
        #: of its own.
        self.checkout = unmount and os.path.lexists(self.member / ".git")
        #: The object store the checkout's own `.git` named. For the
        #: sentence only: the restore asks which store git will use.
        self.store: Path | None = None
        self.legs: list[tuple[str, str, str | None, str | None]] = []
        self.discards = False
        #: Why git could not read the checkout before the first write — its
        #: object store gone, most often — or None. READ WITH A GUARD (#365):
        #: such a member was removed before the rollback existed, and a read
        #: that raised here refused the whole `remove` as a LEG's `git-failed`
        #: while its dry run exited 0. Its checkout is in no store this
        #: rollback can name, so it is never put back from one.
        self.unread: str | None = None
        if self.checkout:
            try:
                self.store = Path(_git_bytes(
                    ["rev-parse", "--absolute-git-dir"], self.member
                ).decode("utf-8", "surrogateescape").strip())
                self.legs = self._legs()
                self.discards = bool(_git_bytes(
                    ["--no-optional-locks", "status", "--porcelain=v1", "-z",
                     "--ignored"], self.member))
            except CommandFailed as exc:
                self.unread = _reason(exc)
                self.store, self.legs, self.discards = None, [], False
        #: Set once `remove`'s checkout has been brought back, which is when
        #: what `deinit -f` discarded is known to be gone.
        self.emptied = False
        #: Set once the registration is written back: the same keys, the
        #: section last in the file.
        self.rewritten = False
        #: Set once the checkout is found to have no store git could bring it
        #: back from, by the restore or by the sentence.
        self.storeless = False
        #: Set once the sentence has named the store the checkout had as
        #: still there (`_store_kept`), which the closing words refer to.
        self.store_said = False
        #: `{leg: why}` for each leg the restore found no store for.
        self.legs_left: dict[str, str] = {}
        #: Set once the member's checkout, and then its legs that could be,
        #: are back, so the commands typed by hand redo neither.
        self.member_back = False
        self.legs_back = False
        #: Where git keeps the store it checked the member out of, when that
        #: is not the store the checkout had (an embedded `.git` that
        #: `deinit` moved into the holder's git directory).
        self.moved_to: str | None = None

    def _legs(self) -> list[tuple[str, str, str | None, str | None]]:
        """`(path, its gitlink's commit, the commit it stands at, its
        branch)` of each submodule of the MEMBER's that is checked out in
        it: a member is an assembly root, and the holder's own bootstrap
        (`git submodule update --init --recursive`) checks its legs out
        inside the mount. `git submodule update` brings back one level, so
        each comes back by name, and only those that were there: one never
        checked out has no store, and `update` would clone it."""
        listed = _git_bytes(["ls-files", "-s", "-z"], self.member)
        legs: dict[str, tuple[str, str, str | None, str | None]] = {}
        for record in listed.split(b"\0"):
            head, _, name = record.partition(b"\t")
            leg = name.decode("utf-8", "surrogateescape")
            if head.startswith(b"160000 ") and leg not in legs and \
                    os.path.lexists(self.member / leg / ".git"):
                legs[leg] = (leg, head.split()[1].decode("ascii"),
                             *_member_head(self.member / leg))
        return list(legs.values())

    def _registration(self) -> list[tuple[str, str]]:
        """Every `submodule.*` key and value in the holder's own git config,
        in order. ALL OF THEM, not one name's: `deinit` drops the keys of
        the name git finds for the path, which is a name `.gitmodules` gives
        and not always the path."""
        listed = git_out(["config", "--local", "--list", "-z"],
                         cwd=self.root, binary=True)
        found = []
        for record in listed.split(b"\0"):
            key, _, value = record.decode("utf-8",
                                          "surrogateescape").partition("\n")
            if key.startswith("submodule."):
                found.append((key, value))
        return found

    def _sections_moved(self, now: list[tuple[str, str]]) -> list[str]:
        """The `submodule.<name>` sections whose keys differ between `now`
        and the record, in the record's order and then any new one's."""
        def of(listed, section):
            return [pair for pair in listed
                    if pair[0].rpartition(".")[0] == section]

        sections = dict.fromkeys(key.rpartition(".")[0]
                                 for key, _ in self.registration + now)
        return [section for section in sections
                if of(now, section) != of(self.registration, section)]

    def _undo_entries(self, name: str, entries: list[bytes]) -> bool:
        """`name`'s index entries put back as `entries` holds them, the way
        `MountRollback` puts them back, but compared on the WHOLE index's
        listing, so no call here names the path."""
        if _index_records(self.root).get(name.encode("utf-8"), []) == entries:
            return False
        run(["git", "update-index", "--force-remove", "--", name],
            cwd=self.root)
        if entries:
            _git_input(["update-index", "-z", "--index-info"], self.root,
                       b"".join(entry + b"\0" for entry in entries))
        return True

    def _undo_registration(self) -> str | None:
        now = self._registration()
        moved = self._sections_moved(now)
        for section in moved:
            for key in dict.fromkeys(key for key, _ in now
                                     if key.rpartition(".")[0] == section):
                run(["git", "config", "--local", "--unset-all", key],
                    cwd=self.root)
            for key, value in self.registration:
                if key.rpartition(".")[0] == section:
                    run(["git", "config", "--local", "--add", key, value],
                        cwd=self.root)
        if not moved:
            return None
        self.rewritten = True
        return (" and ".join(f"`{section}`" for section in moved)
                + " restored in the holder's git config")

    def _storeless(self) -> str | None:
        """Why the member's checkout cannot come back from an object store
        git has, in the sentence's words; None when it can (#365)."""
        if self.unread is not None:
            return ("git could not read its checkout before this command "
                    f"({self.unread}), so no object store here is known to "
                    "hold it")
        why = _unrestorable(self.root, self.path, self.pinned)
        return (None if why is None else
                why + ", so `git submodule update` was not run")

    def _store_kept(self) -> str:
        """`; the object store its checkout had, <it>, is still there`, where
        that store is there and is not the one git looks in: what a human
        who renamed the section by hand needs to know to bring it back."""
        found = _store_git_uses(self.root, self.path)
        if self.store is None or not self.store.is_dir() or (
                found is not None
                and found[1].resolve() == self.store.resolve()):
            return ""
        self.store_said = True
        return (f"; the object store its checkout had, "
                f"{self.store.as_posix()}, is still there")

    def _made_again(self) -> bool:
        """The member's directory made again, empty, if it was there before
        and is not now: a gitlink with no directory reads as deleted, which a
        later `git commit -a` would record, and an empty one is how a member
        never checked out stands."""
        if self.existed and not self.member.is_dir():
            self.member.mkdir(parents=True)
            return True
        return False

    def _undo_work_tree(self) -> str | None:
        if not self.checkout:
            return (f"{self.path} made again, empty, as it was"
                    if self._made_again() else None)
        if os.path.lexists(self.member / ".git") and \
                _member_head(self.member) == (self.at, self.branch):
            return None
        # THE STORE GIT WILL USE IS ASKED FIRST, and `update` is not run
        # without it: it would clone (#365).
        why = self._storeless()
        if why is not None:
            self.storeless = True
            if self._made_again():
                why += f", and {self.path} was made again, empty"
            raise Refusal("member-store-gone", why + self._store_kept())
        found = _store_git_uses(self.root, self.path)
        _offline_git(["--literal-pathspecs", "submodule", "update", "--init",
                      "--no-fetch", "-q", "--", self.path], self.root)
        self.emptied = True
        if found is not None and self.store is not None and \
                found[1].resolve() != self.store.resolve():
            self.moved_to = found[0]
        _head_back(self.member, self.at, self.branch)
        self.member_back = True
        ready = []
        for leg in self.legs:
            try:
                left = _unrestorable(self.member, leg[0], leg[1])
            except (CommandFailed, Refusal) as exc:
                left = _reason(exc)
            if left is None:
                ready.append(leg)
            else:
                self.legs_left[leg[0]] = left
        if ready:
            _offline_git(["--literal-pathspecs", "submodule", "update",
                          "--init", "--no-fetch", "-q", "--",
                          *[leg for leg, _, _, _ in ready]], self.member)
            for leg, _, at, branch in ready:
                _head_back(self.member / leg, at, branch)
        self.legs_back = True
        if self.legs_left:
            raise Refusal(
                "member-store-gone",
                f"{self.path} is checked out again, but "
                + "; and ".join(f"not {leg} in it: {why}, so `git submodule "
                                "update` was not run for it"
                                for leg, why in self.legs_left.items()))
        return self._work_tree_said()

    def _head_said(self) -> str:
        at = (self.at or "")[:12]
        if self.branch is not None:
            return f"{self.path} back on {self.branch} at {at}"
        return f"{self.path} checked out at {at} again"

    def _work_tree_said(self) -> str:
        if not self.checkout:
            return f"{self.path} made again, empty, as it was"
        if self.at is None:
            return f"{self.path} checked out again"
        said = (f"{self.path} checked out again at {self.at[:12]}"
                + (f" on {self.branch}" if self.branch else "")
                + " from the object store `git rm` keeps")
        if self.legs:
            said += (", and " + " and ".join(leg for leg, _, _, _ in self.legs)
                     + " in it")
        return said

    def _file_by_hand(self, name: str) -> list[str]:
        """The commands that put `name` back: its index entries, then its
        bytes from them where they are what the index held. Bytes git does
        not have — an edit nobody had staged — have no command, and the
        sentence's `git status` shows them."""
        data, entries = self.files[name]
        typed = [_entries_by_hand(name, entries)]
        if self._bytes(name) == data:
            return typed
        if data is None:
            return typed + [f"rm -f -- {shlex.quote(name)}"]
        staged = [entry.partition(b"\t")[0].split()[1].decode("ascii")
                  for entry in entries if entry.partition(b"\t")[0]
                  .endswith(b" 0")]
        try:
            blob = _git_bytes(["hash-object", "--stdin", f"--path={name}"],
                              self.root, data).decode("ascii").strip()
        except CommandFailed:
            blob = None
        if staged and blob == staged[0]:
            typed.append(f"git checkout -- {shlex.quote(name)}")
        return typed

    def _registration_by_hand(self) -> list[str]:
        try:
            now = self._registration()
        except Refusal:
            now = []
        typed = []
        for section in self._sections_moved(now):
            typed += [f"git config --local --unset-all {shlex.quote(key)}"
                      for key in dict.fromkeys(
                          key for key, _ in now
                          if key.rpartition(".")[0] == section)]
            typed += [f"git config --local --add {shlex.quote(key)} "
                      f"{shlex.quote(value)}"
                      for key, value in self.registration
                      if key.rpartition(".")[0] == section]
        return typed

    def _work_tree_by_hand(self) -> list[str]:
        """The commands that bring the checkout back by hand, and NONE THAT
        COULD CLONE OR FETCH (#365): `git submodule update` only where git
        holds the store and the commit now, and under the same backstop the
        rollback runs it with. Where git does not, the directory is made
        again, empty, and the sentence says where the checkout comes back
        from (`undo`). Nothing already back is typed again."""
        made = ([f"mkdir {shlex.quote(self.path)}"]
                if self.existed and not self.member.is_dir() else [])
        if not self.checkout:
            return made
        try:
            storeless = self._storeless() is not None
        except (CommandFailed, Refusal):
            storeless = True
        if storeless:
            self.storeless = True
            return made
        offline = " ".join(NO_REMOTE)
        typed = []
        if not self.member_back:
            typed.append(f"git {offline} submodule update --init --no-fetch "
                         "-- " + shlex.quote(self.path))
            if self.at is not None and (self.branch is not None
                                        or self.pinned != self.at):
                typed.append(_head_by_hand(self.path, self.at, self.branch))
        legs = [] if self.legs_back else [
            leg for leg in self.legs if leg[0] not in self.legs_left]
        if legs:
            typed.append(f"git -C {shlex.quote(self.path)} {offline} "
                         "submodule update --init --no-fetch -- " + " ".join(
                             shlex.quote(leg) for leg, _, _, _ in legs))
            typed += [_head_by_hand(f"{self.path}/{leg}", at, branch)
                      for leg, _, at, branch in legs
                      if at is not None and branch is not None]
        return typed

    def _config_left(self, missing: list[str], typed: list[str]) -> list[str]:
        """What a checkout that did not come back left in the holder's git
        config, as a `NOT` clause, with the commands that take it out added
        to `typed`; [] when it left nothing.

        `git submodule update --init` registers the name it reads before it
        checks anything out, so a restore that failed after that, or ran
        against a store that was not the member's, leaves `submodule.<name>.*`
        keys the registration step had already compared and passed (the
        review's probe left `submodule.atlas.url` and `.active`). Asked only
        once the registration was put back and the checkout was not."""
        if "work tree" not in missing or "registration" in missing:
            return []
        try:
            now = self._registration()
        except Refusal:
            return []
        moved = self._sections_moved(now)
        if not moved:
            return []
        new = list(dict.fromkeys(key for key, value in now
                                 if key.rpartition(".")[0] in moved
                                 and (key, value) not in self.registration))
        gone = list(dict.fromkeys(key for key, value in self.registration
                                  if key.rpartition(".")[0] in moved
                                  and (key, value) not in now))
        typed += self._registration_by_hand()
        said = []
        if new:
            said.append("it holds " + " and ".join(f"`{key}`" for key in new)
                        + ", which it did not")
        if gone:
            said.append("it lost " + " and ".join(f"`{key}`" for key in gone))
        return ["the holder's git config as it was: " + ", and ".join(said)]

    def _steps(self) -> list[tuple]:
        """`(key, what it puts back, how, the keys it needs back first, the
        commands that do it by hand)` for each step, in the order `undo`
        takes them: the index and the files, then what lies outside them."""
        steps = [("gitlink",
                  f"the gitlink at {self.path} put back in the index as it "
                  "was",
                  lambda: self._undo_entries(self.path, self.gitlink), (),
                  lambda: [_entries_by_hand(self.path, self.gitlink)])]
        for name, (data, entries) in self.files.items():
            steps.append((
                name,
                (f"{name} restored byte for byte" if data is not None else
                 f"{name} removed, as there was none before"),
                lambda name=name, data=data, entries=entries:
                    self._undo_file(name, data, entries),
                (), lambda name=name: self._file_by_hand(name)))
        if not self.unmount:
            steps.append((
                "member", self._head_said(),
                lambda: _head_back(self.member, self.at, self.branch), (),
                lambda: [_head_by_hand(self.path, self.at, self.branch)]))
            return steps
        steps.append(("registration",
                      "the holder's `submodule.*` keys put back in its git "
                      "config", self._undo_registration, (),
                      self._registration_by_hand))
        steps.append(("work tree", self._work_tree_said(),
                      self._undo_work_tree,
                      ("gitlink", GITMODULES, "registration"),
                      self._work_tree_by_hand))
        return steps

    def _config_moved(self) -> str:
        """What the holder's `submodule.*` keys hold now that they did not,
        and what they have lost, as `_index_moved` names the index's; ""
        when they are the recorded keys and values, wherever in the file."""
        now = self._registration()
        if sorted(now) == sorted(self.registration):
            return ""
        parts = []
        for said, pairs in (("new in it", [pair for pair in now
                                           if pair not in self.registration]),
                            ("gone from it", [pair for pair in
                                              self.registration
                                              if pair not in now])):
            if pairs:
                parts.append(f"{said}: " + ", ".join(
                    f"`{key}={value}`" for key, value in pairs[:5]))
        return "the holder's git config " + "; ".join(parts)

    def undo(self) -> str:
        """Put the holder back. Returns the sentence a refusal ends with:
        what was put back, or what is left and the commands that put it
        back, and, where the index (or `remove`'s registration) is not the
        one recorded, what differs."""
        now = self._head()
        if now is not None and now != self.head:
            return (" The commit had already landed, so nothing was undone: "
                    "`git log -1` in the holder shows it.")
        named = {"gitlink": f"the gitlink at {self.path}",
                 GITMODULES: GITMODULES, "registration": "the registration"}
        restored, failed, typed, missing = [], [], [], []
        for key, said, action, needs, by_hand in self._steps():
            lacking = [named[need] for need in needs if need in missing]
            if lacking:
                missing.append(key)
                failed.append(f"{said}: not tried, as it needs "
                              + " and ".join(lacking) + " back first")
                typed += by_hand()
                continue
            try:
                done = action()
            except _EntryNotRestored as exc:
                missing.append(key)
                if exc.bytes_restored:
                    restored.append(said)
                failed.append(f"the index entry of {exc.name} put back as "
                              f"it was: {_reason(exc.cause)}")
                typed.append(_entries_by_hand(exc.name,
                                              self.files[exc.name][1]))
                continue
            except (CommandFailed, Refusal, OSError) as exc:
                missing.append(key)
                failed.append(f"{said}: {_reason(exc)}")
                typed += by_hand()
                continue
            if done:
                restored.append(done if isinstance(done, str) else said)
        noun = "bump" if self.verb == "bump" else "unmount"
        if failed:
            if self.unmount:
                failed += self._config_left(missing, typed)
            text = (f" The {noun} was undone only in part"
                    + (" (" + ", ".join(restored) + ")" if restored else "")
                    + "; NOT " + "; NOT ".join(failed) + ".")
            # NO COMMAND HERE CLONES (#365): a checkout no store git has can
            # bring back is said to come back only from its remote, and
            # one whose old store the sentence named as still there, that
            # it can come back from that store with no network as well
            # (review 365-7cca975, NIT-B), with no command to do it.
            kept = self.storeless and self.store_said
            remote_only = ([self.path] if self.storeless and not kept
                           else []) + [f"{self.path}/{leg}"
                                       for leg in self.legs_left]
            if kept:
                text += (f" The checkout of {self.path} can come back from "
                         "the object store named above with no network, or "
                         "from its remote; this command did neither.")
            if remote_only:
                text += (" The checkout of " + " and ".join(remote_only)
                         + " comes back only from "
                         + ("its remote" if len(remote_only) == 1 else
                            "their remotes")
                         + ", which this command never reaches.")
            if typed:
                return (text + " Put the rest back by hand, in the holder and "
                        "in this order: " + "; ".join(f"`{line}`"
                                                      for line in typed)
                        + f". Then `git status` shows whether anything is "
                        f"left, before running `{self.verb}` again.")
            if remote_only or kept:
                return (text + " `git status` shows whether anything else is "
                        f"left, before running `{self.verb}` again.")
            return (text + " Put those back by hand — `git status` shows what "
                    f"is left — before running `{self.verb}` again.")
        moved, unread = "", None
        try:
            moved = "; ".join(part for part in (
                self._index_moved(),
                self._config_moved() if self.unmount else "") if part)
        except Refusal as exc:
            unread = _reason(exc)
        undone = ((f" Nothing was committed: the {noun} has been undone — "
                   + ", ".join(restored) + " —") if restored else
                  " Nothing was committed,")
        if unread is not None:
            return (undone + " but the holder could not be read back to "
                    f"confirm it is as it was before this command: {unread}. "
                    f"Check it before running `{self.verb}` again: `git "
                    "ls-files -s` lists what the index now holds.")
        if moved:
            return (undone + " but the holder is NOT as it was before this "
                    f"command ({moved}). Put it back before running "
                    f"`{self.verb}` again: `git ls-files -s` lists what the "
                    "index now holds.")
        did = "bumped" if self.verb == "bump" else "removed"
        if not restored:
            return (f" Nothing was {did}, and nothing in the holder had "
                    "changed.")
        # "EXACTLY" ONLY WHEN NOTHING BELOW QUALIFIES IT: a registration
        # written back is the same keys in another place in the file, a
        # checkout git keeps elsewhere now is not byte for byte the one it
        # had, and what `deinit -f` discarded is in no store.
        discarded = self.emptied and self.discards
        held = ("as it was before this command"
                if discarded or self.rewritten or self.moved_to else
                "exactly as it was before this command")
        if discarded:
            held += (" but for what `git submodule deinit -f` discarded in "
                     f"{self.path}, which no object store holds: the "
                     "uncommitted changes and the untracked and ignored "
                     "files `git status --ignored` listed there")
        text = (f" Nothing was {did}: the {noun} has been undone — "
                + ", ".join(restored) + f" — and the holder is {held}.")
        if self.rewritten:
            text += (" Its git config holds the same keys and values as "
                     "before, the section put back written last.")
        if self.moved_to is not None and self.store is not None:
            text += (f" {self.path} now has its object store at "
                     f"{self.moved_to}, where git keeps it, and no longer at "
                     f"{self.store.as_posix()}.")
        return text


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

    THE PATHS ARE TAKEN LITERALLY (`--literal-pathspecs`, #299), as the
    commit this answers for takes them: a glob here would find the
    difference in a neighbouring member and answer "something to record" for
    a member that has nothing, so the commit would go ahead.
    """
    try:
        run(["git", "--literal-pathspecs", "diff", "--quiet",
             "--ignore-submodules=dirty", "HEAD", "--", *paths], cwd=root)
    except CommandFailed as exc:
        if exc.code == 1:
            return False
        raise
    return True


def _nothing_to_do(row: dict, commit: str) -> str:
    """The sentence a bump that records nothing ends with, real or dry run:
    the one `bump-leg.py` answers the same re-run with, repository first."""
    return (f"\nnothing to do: {row['repository']} is already pinned at "
            f"{commit[:12]} and every fact agrees.")


def _bumped_rows(family: Family, row: dict, project_id: str, commit: str,
                 digest: str) -> tuple[dict, list[dict]]:
    """`(the member's new row, every row as `bump` writes them)`.

    ONE FUNCTION FOR THE REAL RUN AND ITS DRY RUN (#326), so the row `bump
    --dry-run` prints is the row a real `bump` writes by construction, not
    by two spellings that happen to agree today.
    """
    project = str(row["project"])
    new = _member_row(project, project_id, str(row["repository"]), commit,
                      digest)
    return new, [new if str(r.get("project")) == project else r
                 for r in family.members]


def _member_id_at(member: Path, commit: str, project: str,
                  repository: str) -> str | None:
    """The member's `project.yaml` id at `commit`, read from its OBJECTS
    rather than from a checkout, or None where only a checkout can read it.

    WHAT `bump` READS AFTER ITS CHECKOUT, ASKED WITHOUT ONE (#326), so `bump
    --dry-run` makes the same refusals (`member-not-a-project`,
    `member-manifest-unreadable`, `member-bad-id` and `load_yaml`'s own) and
    prints the id the real run would write. The one blob is copied into a
    directory of its own and read by `_read_member_project`, the function
    the checkout is read with, so every sentence is the real run's but the
    file's name: `<repository> @ <commit>:project.yaml`, where a temporary
    path would name a file deleted before anybody reads the line. A
    `project.yaml` that is absent, a directory or a submodule is no file,
    which is what a checkout's `is_file()` says about it too.

    A SYMLINK IS None. A checkout reads THROUGH a link and the objects hold
    only the link's text, so its id is the real run's to read; the dry run
    says so rather than refusing a member the real run would pin.
    """
    listed = _git_bytes(["ls-tree", "-z", commit, "--", "project.yaml"],
                        member)
    mode, kind, oid = (listed.split(b"\t", 1)[0].split() + [b""] * 3)[:3]
    if mode == b"120000":
        return None
    with tempfile.TemporaryDirectory(prefix="openreposhape-member-") as tmp:
        if kind == b"blob":
            (Path(tmp) / "project.yaml").write_bytes(
                _git_bytes(["cat-file", "blob", oid.decode("ascii")], member))
        return _read_member_project(
            Path(tmp), project, repository,
            shown=f"{repository} @ {commit[:12]}:project.yaml")


def _head_oid(root: Path, path: str) -> str | None:
    """The object HEAD records at `path` — for a gitlink, the commit — or
    None where HEAD records nothing there. A tree path, not a pathspec, so
    no glob in it is ever expanded."""
    try:
        return git_out(["rev-parse", "-q", "--verify", f"HEAD:{path}"],
                       cwd=root).lower()
    except Refusal:
        return None


def _git_bytes(args: list[str], cwd: Path, data: bytes | None = None) -> bytes:
    """`git <args>` in `cwd`, its output as BYTES, `data` (if any) on stdin
    as bytes for the reason `_git_input` gives; a failure is a
    `CommandFailed`.

    WHAT THE DRY RUNS ASK GIT WITH (#326). `git_out`'s failure is a
    `Refusal` that carries `repo_shape`'s default remediation, which is a
    LEG's (run `validate-pins.py`, advance `contracts/<leg>-pin.yaml`), and
    a holder has neither. A `CommandFailed` is printed as every failed git
    command in this file is: the exact command, where, and git's own words,
    exit 2, which is how the real run reports the same failure.
    """
    command = ["git", *args]
    check_program(command)
    proc = subprocess.run(command, cwd=str(cwd), input=data,
                          capture_output=True, check=False)
    if proc.returncode != 0:
        raise CommandFailed(command, cwd, proc.returncode,
                            (proc.stderr + proc.stdout).decode("utf-8",
                                                               "replace"))
    return proc.stdout


def _manifest_blob(root: Path, text: str) -> str:
    """The blob id `family.yaml` would have with `text` in it, as `git add`
    would store it — `git hash-object --path`, which applies the holder's
    own attributes and filters — and WITHOUT `-w`, so nothing is written."""
    return _git_bytes(["hash-object", "--stdin", f"--path={MANIFEST}"], root,
                      text.encode("utf-8")).decode("ascii").strip().lower()


def _print_trailers(trailers: list[str]) -> None:
    """The `--trailer` lines the commit would end with, verbatim and in the
    order given, which is the order `commit_trailers` appends them in.

    `bump --dry-run` prints them after the row (#326), worded as
    `bump-leg.py --dry-run` prints its own, so a lane reads one form from
    either tool before the lines land rather than after. Never printed for
    `nothing to do`: a run that writes no commit has nothing to end.
    """
    if trailers:
        print(f"trailers     {len(trailers)} to append, in order:")
        for line in trailers:
            print(f"  {line}")
    else:
        print("trailers     none")


def _checked_to_names_a_commit(member: Path, path: str, row: dict,
                               commit: str) -> None:
    """`member-to-not-a-commit` for a `--to` that is 40 hex and names, in the
    member's objects, something that is not a commit: an annotated tag, a
    tree or a blob (#405). `bump` and `bump --dry-run` both ask it, after
    the fetch and before the checkout, so the two runs make one refusal and
    the holder is left byte for byte as it was.

    AN ANNOTATED TAG'S OWN ID IS 40 HEX, and it is what `git rev-parse v2`
    prints for a release tag. `COMMIT_RE` passed it, the checkout PEELED it
    to the commit it names, which the gitlink then recorded, and the row
    recorded the tag's id as typed: `bump` exited 0 with a commit the
    holder's own `validate-family.py` refused as `member-gitlink-mismatch`,
    and the dry run printed the two ids side by side on its `commit` and
    `gitlink` lines.

    REFUSED, NOT PEELED, as `bump-leg.py` refuses the same `--to` for a leg:
    its `validate-pins.py` goes red on the tag's id in the pin and the bump
    is rolled back, exit 2. The pin is the id the person typed and the
    `old -> new` line is what they read, so the refusal names the commit the
    tag peels to (through a tag of a tag too, `^{}`) and the re-run is
    theirs. A tree's or a blob's id, or a tag of one, is named for what it
    is, as `add --at` names one (`member-at-unknown`); before, both runs
    failed on it in git's words, exit 2, from the dry run's resolve or the
    real run's checkout.

    AN ID THE MEMBER DOES NOT HOLD is not asked here. The dry run's resolve
    and the real run's checkout fail on it in git's words, exit 2, as they
    always have.
    """
    try:
        kind = run(["git", "cat-file", "-t", commit], cwd=member)
    except CommandFailed:
        return
    if kind == "commit":
        return
    try:
        peeled = run(["git", "rev-parse", "-q", "--verify", f"{commit}^{{}}"],
                     cwd=member).lower()
        names = run(["git", "cat-file", "-t", peeled], cwd=member)
    except CommandFailed:
        peeled, names = "", ""
    repository = row.get("repository")
    if names == "commit":
        raise Refusal(
            "member-to-not-a-commit",
            f"--to {commit} is an annotated tag in {repository}, not a "
            f"commit; the commit it names is {peeled}",
            f"Remediation: pass that commit, `--to {peeled}`. A pin is a "
            "commit or it is nothing: checking the tag out would put "
            f"{peeled[:12]} in the gitlink at {path} and the tag's own id in "
            "the row, which `validate-family.py` refuses as "
            "`member-gitlink-mismatch`.")
    if kind != "tag":
        what = f"names a {kind}"
    elif names in ("tree", "blob"):
        what = f"is an annotated tag of a {names}"
    else:
        what = "is an annotated tag"
    raise Refusal(
        "member-to-not-a-commit",
        f"--to {commit} {what} in {repository}, not a commit",
        "Remediation: pass the commit itself — `git log --format=%H` in "
        f"{path} lists them. A pin is a commit or it is nothing.")


def _bump_dry_run(family: Family, row: dict, path: str, commit: str,
                  trailers: list[str], fetched: bool) -> int:
    """`bump --dry-run`, entered after the member is fetched (or the fetch
    failed, `fetched` False, and said so) and before it is checked out
    (#326): the answers a real `bump` gives, and no write.

    THE REAL RUN'S QUESTIONS, IN ITS ORDER, ASKED OF THE MEMBER'S OBJECTS.
    `--to` is resolved as the checkout would take it (`^{commit}`, which is
    what `git checkout` accepts), and one the member does not have after the
    fetch is exit 2, where the real run's checkout fails. The manifest is
    read by `_member_id_at` and the digest by `tree_digest`, which reads
    objects and never a checkout, so the digest printed is the one the real
    run computes, never a guess. The rows are `_bumped_rows`', and
    `family.rewritten` asks `family-members-unrecognised` without writing.

    `nothing to do` IS THE REAL RUN'S OWN RULE (#210), asked without the
    write: the commit would record nothing when HEAD's gitlink is already
    the commit `--to` resolves to AND the rewritten manifest is the blob
    HEAD already has. Not `--to` against the row alone: a row naming `--to`
    over a gitlink that moved alone, or a digest that does not recompute, is
    a bump with something to commit, under `--dry-run` as well.

    THE CHECKOUT'S OWN QUESTION IS NOT ASKED. Local changes in the member
    that `git checkout` would refuse to overwrite are found by the real run,
    exit 2, while the dry run prints the row and exits 0: only the checkout
    knows which of them the move touches.
    """
    project, repository = str(row["project"]), str(row.get("repository"))
    member = family.root / path
    try:
        resolved = run(["git", "rev-parse", "--verify",
                        f"{commit}^{{commit}}"], cwd=member).lower()
    except CommandFailed as exc:
        print(exc.loudly(f"resolving {commit[:12]} in {path}, where a real "
                         "bump checks it out"), file=sys.stderr)
        return 2
    project_id = _member_id_at(member, resolved, project, repository)
    linked = project_id is None
    if linked:
        project_id = str(row.get("id") or "")
    digest = tree_digest(member, commit)
    new, rows = _bumped_rows(family, row, project_id, commit, digest)
    text = family.rewritten(rows)
    was = str((row.get("pin") or {}).get("commit") or "")
    recorded = _head_oid(family.root, path)

    print(f"member       {project}  {repository} at {path}")
    print(f"commit       {was[:12]} -> {commit[:12]}")
    print(f"tree         {digest[:12]}… ({digest})")
    if linked:
        print("note         project.yaml is a symbolic link at "
              f"{resolved[:12]}, which only a checkout reads through: the "
              "`id:` below is the row's own, and the real run reads it "
              "through the link")
    if recorded == resolved and \
            _head_oid(family.root, MANIFEST) == _manifest_blob(family.root,
                                                               text):
        print(_nothing_to_do(row, commit))
        return 1
    print(f"gitlink      {path} {(recorded or 'none')[:12]} -> "
          f"{resolved[:12]}")
    print(f"row          as {MANIFEST} would carry it:")
    for line in _member_lines(new):
        print(line)
    _print_trailers(trailers)
    how = (f"`git fetch` ran in {path}, as a real bump's does, which is how "
           "--to was resolved and the digest above computed" if fetched else
           f"The fetch of {path} failed, as the note says, so --to was "
           "resolved and the digest above computed from what its object "
           "store already held, as a real bump would")
    print(f"\n--dry-run: nothing was changed in the holder. {how}; the "
          f"member's checkout, {MANIFEST}, the index and the holder's commits "
          "are as they were.")
    return 0


def _bump_and_pin(family: Family, row: dict, path: str, commit: str,
                  trailers: list[str], rollback: PinRollback) -> int:
    """The part of `bump` that writes: the checkout, the pin and the ONE
    commit, or `nothing to do`. Returns the exit code. Runs inside the
    caller's `PinRollback` (#365), which puts back whatever a failure here
    leaves; `nothing to do` is no failure, and is left as it always was."""
    project = str(row["project"])
    member = family.root / path
    rollback.step = f"checking {path} out at {commit[:12]}"
    run(["git", "checkout", "-q", commit], cwd=member)
    rollback.step = "a git or gh command failed"

    was = str((row.get("pin") or {}).get("commit") or "")
    project_id = _read_member_project(member, project,
                                      str(row.get("repository")))
    digest = tree_digest(member, commit)
    _, rows = _bumped_rows(family, row, project_id, commit, digest)
    original = family.path.read_bytes()
    _rewrite_members(family, rows, f"with {project}'s new pin")
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
        print(_nothing_to_do(row, commit))
        return 1

    head = _commit_one(
        family.root,
        f"Bump {project} to {commit[:12]} in the "
        f"{family.data.get('name')} family\n\n"
        f"{was[:12]} -> {commit[:12]}. The gitlink at {path} and "
        f"`members[].pin` in {MANIFEST} move in ONE commit, which is what "
        "`validate-family.py` checks and what a reviewer reads as one "
        "change.\n",
        [path, MANIFEST], trailers=trailers)
    print(f"  {project:<16} {was[:12]} -> {commit[:12]} tree {digest[:12]}…")
    print(f"  committed {head[:12]}: {path}, {MANIFEST}")
    return 0


def _checked_bump_target(family: Family, row: dict, path: str,
                         commit: str) -> None:
    """Every refusal the real `bump` can ask before its checkout, asked as
    `bump --dry-run` asks it and in its order (#365): the member's
    `project.yaml` at `--to`, read from its objects (`_member_id_at`), and
    a `members:` block this tool will not rewrite.

    THE REAL RUN ASKED BOTH AFTER ITS FIRST WRITE. A `--to` whose tree has no
    `project.yaml` was refused `member-not-a-project` with the member left
    checked out at `--to`, which the holder's own validator then reported,
    while `bump --dry-run` refused the same commit and changed nothing. Asked
    here, before the rollback is even recorded, the two runs refuse at the
    same point in the same words, and the holder is byte for byte as it was.
    A `--to` the member's objects do not hold is left to the checkout, which
    fails on it in git's words, as it always has, before it writes anything;
    a symbolic link is left to the read through the checkout, as the dry run
    leaves it.
    """
    member = family.root / path
    try:
        resolved = run(["git", "rev-parse", "-q", "--verify",
                        f"{commit}^{{commit}}"], cwd=member).lower()
    except CommandFailed:
        return
    project_id = _member_id_at(member, resolved, str(row["project"]),
                               str(row.get("repository")))
    if project_id is None:
        project_id = str(row.get("id") or "")
    # THE ROWS THE BUMP WRITES, not the rows the manifest has: a row with no
    # `path:` line is the member's own path by default (`_member_path`), and
    # only the row `_bumped_rows` makes for it spells one out to rewrite.
    _, rows = _bumped_rows(family, row, project_id, commit,
                           tree_digest(member, commit))
    family.rewritten(rows)


def _put_back_on_failure(rollback: PinRollback, write) -> int:
    """`write()`, inside `rollback`, as `cmd_add` runs its mount (#365): a
    refusal ends with the sentence `undo` returns; a failed git command is
    quoted as it ran, headed as it always was, with that sentence under it,
    exit 2; anything else is put back and goes on exactly as raised, so
    Ctrl-C still stops the program and a bug still shows its traceback."""
    try:
        return write()
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


def cmd_bump(args) -> int:
    """Move one member's gitlink and pin in ONE commit, or with `--dry-run`
    print the row it would write and change nothing in the holder (#326).

    The refusals before the fetch are the same under `--dry-run`. The dry run
    leaves after the fetch and before the checkout, which is the real run's
    first write, and asks of the member's objects what the real run asks
    before that checkout too (`_bump_dry_run`, `_checked_bump_target`). The
    real run then records the holder and puts it back if anything after the
    checkout fails (`PinRollback`, #365).
    """
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
    # THE ROW'S `path:` IS CHECKED, NOT TRUSTED (#299): `member` below, the
    # fetch and checkout in it, and every pathspec after them are this path.
    path = _member_path(project, row)
    member = family.root / path
    if not (member / ".git").exists():
        raise Refusal(
            "member-uninitialized",
            f"{path} is not an initialized submodule checkout, so the new "
            "commit cannot be resolved or digested",
            "Remediation: `git submodule update --init " + path + "`, or "
            "`make bootstrap`, which resolves a credential for a private "
            "member first.")
    fetched = True
    try:
        run(["git", "fetch", "-q", "origin"], cwd=member)
    except CommandFailed:
        fetched = False
        print(f"  note: could not fetch {path} from its origin; the commit "
              "must already be in its object store", file=sys.stderr)
    # WHAT `--to` NAMES IS ASKED OF THE FETCHED OBJECTS (#405), before the
    # dry run leaves and before the checkout: a tag, a tree or a blob is
    # refused by both runs alike, with nothing in the holder moved.
    _checked_to_names_a_commit(member, path, row, commit)
    if args.dry_run:
        return _bump_dry_run(family, row, path, commit, args.trailer,
                             fetched)
    _checked_bump_target(family, row, path, commit)
    rollback = PinRollback(family.root, path, "bump", (MANIFEST,))
    return _put_back_on_failure(rollback, lambda: _bump_and_pin(
        family, row, path, commit, args.trailer, rollback))


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------


def _suspicious_name(name: str) -> bool:
    """Whether git IGNORES a submodule of this name: an empty one, or one
    with a `..` component between `/` or `\\` on any platform — git's own
    `check_submodule_name`, which warns "ignoring suspicious submodule name"
    and reads nothing in that section."""
    return not name or ".." in re.split(r"[/\\]", name)


def _gitmodules_names(root: Path, path: str) -> tuple[str | None, list[str]]:
    """`(the name whose sections `git rm` drops for the gitlink at `path`,
    or None, every other name with a `path = <path>` line)` (#326).

    GIT'S OWN LOOKUP, MODELLED OVER GIT'S OWN READING OF THE FILE. `git rm`
    edits `.gitmodules` only where the work tree has one. It asks which
    submodule has the gitlink's path (`submodule_from_path`), and drops EVERY
    section of that name. Its reading of the WORK-TREE file is the one with
    overwrite on (`parse_config`, as `gitmodules_cb` calls it), and three
    rules follow from it, each one a hand edit `remove --dry-run` must not
    misreport:

    - a name keeps the LAST `path` it is given;
    - a name moving to another path takes the OLD path out of git's path map,
      whichever name held it there, so a path a ghost name passed through can
      end up with no submodule at all, and then `git rm` drops nothing
      ("Could not find section in .gitmodules");
    - a suspicious name (`_suspicious_name`) and a path that reads as an
      option (a leading `-`) are ignored.

    The file is read by `git config --list`, never by a parser of this
    tool's, as `add`'s `_submodule_paths` reads it; the rules are git's, as
    git 2.43 applies them and as the tests check them against a real
    `remove` on every runner.
    """
    if not (root / GITMODULES).is_file():
        return None, []
    listed = _git_bytes(["config", "-z", "--file", GITMODULES, "--list"],
                        root)
    paths: dict[str, str] = {}
    owner: dict[str, str] = {}
    giving: list[str] = []
    for record in listed.split(b"\0"):
        key, _, value = record.decode("utf-8",
                                      "surrogateescape").partition("\n")
        section, _, variable = key.rpartition(".")
        if not section.startswith("submodule.") or variable != "path":
            continue
        name = section[len("submodule."):]
        if value == path and name not in giving:
            giving.append(name)
        if _suspicious_name(name) or value.startswith("-"):
            continue
        if name in paths:
            owner.pop(paths[name], None)
        paths[name] = value
        owner[value] = name
    dropped = owner.get(path)
    return dropped, [name for name in giving if name != dropped]


def _registered(root: Path, name: str) -> bool:
    """Whether the holder's own git config holds a `submodule.<name>`
    section: the registration `git submodule deinit` drops, looked up by the
    same name `git rm` drops in `.gitmodules`. By section — the part of a
    key before its LAST dot — as `MountRollback` reads one, so a dotted
    neighbour's keys are not taken for this name's."""
    listed = _git_bytes(["config", "--local", "-z", "--list"], root)
    return any(record.decode("utf-8", "surrogateescape").partition("\n")[0]
               .rpartition(".")[0] == f"submodule.{name}"
               for record in listed.split(b"\0") if record)


def _sections_giving(root: Path, path: str
                     ) -> list[tuple[str, str | None, tuple[str, ...]]]:
    """`(name, url, keys)` of every submodule the work tree's `.gitmodules`
    gives `path` to, in ANY of its `path` lines, in the order the file first
    names them (#360). `url` is the last the name gives, or None; `keys` is
    every key it holds, once each, in the order git lists them.

    ANY `path` LINE, NOT ONLY THE LAST. `git rm` takes out the sections of
    ONE name, the one git's path lookup returns (`_gitmodules_names`), and
    every other section that says this path stays in the file `remove`
    commits, whatever git makes of its name: a section of a name that gives
    the path and then moves on took the path out of git's lookup altogether,
    so `git rm` took out nothing and the member's own section stayed. Read
    where `git rm` reads, the work tree's file, by `git config --list`, as
    `_gitmodules_names` reads it.
    """
    if not (root / GITMODULES).is_file():
        return []
    listed = _git_bytes(["config", "-z", "--file", GITMODULES, "--list"],
                        root)
    found: dict[str, dict[str, str]] = {}
    giving: list[str] = []
    for record in listed.split(b"\0"):
        key, _, value = record.decode("utf-8",
                                      "surrogateescape").partition("\n")
        section, _, variable = key.rpartition(".")
        if not section.startswith("submodule."):
            continue
        name = section[len("submodule."):]
        found.setdefault(name, {})[variable] = value
        if variable == "path" and value == path and name not in giving:
            giving.append(name)
    return [(name, found[name].get("url"), tuple(found[name]))
            for name in giving]


def _checked_one_section(root: Path, project: str, path: str) -> None:
    """`member-path-registered-twice`: `remove` refuses, before any git
    command that writes and under `--dry-run` alike, a `.gitmodules` that
    gives the member's path to more than one submodule (#360).

    git maps a path to ONE submodule name, the last section in the file to
    give it, so `git submodule deinit` deinitialised that name and `git rm`
    took out its sections, and the other stayed: in the commit `remove`
    wrote, registering `members/<P>` with no gitlink and no row, while it
    printed `removed` and exited 0. When the other was written FIRST, the
    member's own section was the one left, and with it the registration
    `deinit` never touched, which a later `add` of the member then wrote
    into. `validate-family.py` passed either result: after `remove` the path
    has one section, not two.

    REFUSED, NOT CLEANED, as `add` refuses the same file (#317,
    `member-path-registered`). Which section is the member's is a person's
    to say, and one somebody wrote is not this tool's to drop or rewrite;
    so each is named with its url, and #317's by-key removal is printed for
    every section not named after the path, `members/<P>`, the name `family.py
    add` gives a member's own. With the others gone, `remove` runs as it
    always has. The holder is left byte for byte as it was.
    """
    sections = _sections_giving(root, path)
    if len(sections) < 2:
        return
    named = ", ".join(
        f"`{name}` ({'no url' if url is None else 'url ' + url})"
        for name, url, _ in sections)
    others = [(name, keys) for name, _, keys in sections if name != path]
    removal = " and ".join(
        f"`git config -f {GITMODULES} --unset-all "
        f"{shlex.quote('submodule.' + name + '.' + key)}`"
        for name, keys in others for key in keys)
    which = (f"If `{path}`, the name `family.py add` gives a member's own "
             f"section, is {project}'s, take each other one out by hand"
             if len(others) < len(sections) else
             f"None of them has the name `family.py add` gives a member's "
             f"own section, `{path}`, so the commands that follow take out "
             f"every one: leave out those of {project}'s own and run the "
             "rest")
    raise Refusal(
        "member-path-registered-twice",
        f"{GITMODULES} gives {project}'s path {path} to {len(sections)} "
        f"submodules, {named}. git finds ONE of them for a path, and `git "
        "rm` takes out only that one's sections, so this command's commit "
        + ("would keep the other" if len(sections) == 2 else
           "would keep the others")
        + f" registering {path} with no gitlink and no row behind it. No git "
        "command that writes was run and nothing was written.",
        f"Remediation: which of them is {project}'s is a person's to say, "
        "and a section somebody wrote is not this tool's to drop or "
        f"rewrite. {which}, in a POSIX shell — {removal}, then `git add "
        f"{GITMODULES}` — and run the same command again.")


def _checked_index_unlocked(root: Path, path: str) -> None:
    """`family-index-locked`: the real `remove` refuses a held `index.lock`
    BEFORE it unmounts anything (#365).

    `git submodule deinit` takes no index lock, so with one held — another
    git command running in the holder, or one that stopped without letting
    go — `deinit -f` emptied the member's checkout and dropped its
    registration, and `git rm`, the first step that writes the index, then
    died on the lock. The lock is where git says it is (`git rev-parse
    --git-path index.lock`), which in a linked worktree is not
    `.git/index.lock`. A lock taken after this check is the rollback's to
    meet. The dry run does not ask: it writes nothing, and a lock is a fact
    about the moment.
    """
    shown = _git_bytes(["rev-parse", "--git-path", "index.lock"],
                       root).decode("utf-8", "surrogateescape").strip()
    lock = root / shown
    if not os.path.lexists(lock):
        return
    raise Refusal(
        "family-index-locked",
        f"the holder's index is locked: {lock.as_posix()} exists. `git "
        f"submodule deinit` takes no such lock, so `remove` would empty "
        f"{path} and drop its registration and then fail at `git rm`, its "
        "first write to the index; it was refused before either, and "
        "nothing was written.",
        "Remediation: another git command is running in the holder, or one "
        "that stopped left the lock behind. Let it finish and run the same "
        "command again; if no git command is running, delete the lock (`rm "
        f"-f {shlex.quote(lock.as_posix())}`) and run the same command "
        "again.")


def _unmount_and_drop(family: Family, row: dict, path: str) -> int:
    """The part of `remove` that writes: the unmount, the row and the ONE
    commit. Returns the exit code. Runs inside the caller's `PinRollback`
    (#365), which puts back whatever a failure here leaves."""
    project = str(row["project"])
    # THE MEMBER REPOSITORY IS NOT TOUCHED. Removing a member unmounts it from
    # this holder and nothing else: the project keeps its name, its history,
    # its legs and its gate. A family that could delete a project by dropping
    # a row would be a family that confers something.
    #
    # BOTH CALLS TAKE THE PATH LITERALLY (`--literal-pathspecs`, #299), the
    # global option, which `git submodule` honours too: the path is always
    # `members/<project>` here, so this is defence in depth that does not
    # depend on the row being right. Without it a glob in the path would
    # unmount and remove every member it matched.
    run(["git", "--literal-pathspecs", "submodule", "deinit", "-f", "-q",
         "--", path], cwd=family.root)
    run(["git", "--literal-pathspecs", "rm", "-r", "-q", "-f", "--", path],
        cwd=family.root)
    _rewrite_members(family, [r for r in family.members
                              if str(r.get("project")) != project],
                     f"without {project}'s row")
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


def _remove_dry_run(family: Family, row: dict, path: str) -> int:
    """`remove --dry-run` (#326): what a real `remove` would take out, and
    no git command that writes.

    THE REAL RUN'S FAILURES, IN ITS ORDER. `family.rewritten` asks
    `family-members-unrecognised` first, without writing, because the real
    run asks it before its unmount (#365): asked after the listing below, a
    gitlink the index does not hold beside a `members:` line this tool will
    not rewrite got git's loud failure here and the refusal there. The real
    run's first git call that writes, `git submodule deinit -- <path>`,
    then fails on a path the index holds nothing at, and the real run prints
    that failure loudly, the exact command and git's own `did not match any
    file(s) known to git`, exit 2. `ls-files --error-unmatch` over the same
    LITERAL pathspec fails where it fails, with the same line from git, and
    is printed the same way, exit 2; it lists what `git rm -r` would unstage
    when it does not fail.

    PRINTED: the row, each index entry under the path (the gitlink), the
    `.gitmodules` section `git rm` drops for it and any it leaves that gives
    the same path (`_gitmodules_names`), the registration `deinit` drops
    from the holder's git config under that same name (`_registered`), and
    the directory `deinit -f` empties and `git rm` deletes, uncommitted work
    in the member included. The member's object store is not removed, by
    either run, so it is not on the list.
    """
    project = str(row["project"])
    root = family.root
    family.rewritten([r for r in family.members
                      if str(r.get("project")) != project])
    try:
        listed = _git_bytes(["--literal-pathspecs", "ls-files", "-s", "-z",
                             "--error-unmatch", "--", path], root)
    except CommandFailed as exc:
        print(exc.loudly(f"listing {path} in the index, where a real remove "
                         "unmounts it"), file=sys.stderr)
        return 2
    entries = []
    for record in listed.split(b"\0"):
        if record:
            head, _, name = record.partition(b"\t")
            mode, oid = head.decode("ascii").split()[:2]
            entries.append((mode, oid, name.decode("utf-8", "replace")))

    pinned = str((row.get("pin") or {}).get("commit") or "")
    print(f"row          {project}  {row.get('repository')}, pinned at "
          f"{pinned[:12]}, dropped from {MANIFEST}")
    for mode, oid, name in entries:
        if mode == "160000":
            print(f"gitlink      {name}  {oid[:12]}")
        else:
            print(f"index        {name}  {oid[:12]} (mode {mode})")
    for name in [name for mode, _, name in entries if mode == "160000"]:
        dropped, kept = _gitmodules_names(root, name)
        if dropped is None:
            print(f"gitmodules   none: git reads no section of {GITMODULES} "
                  f"in the work tree as giving {name}, so none is removed")
        else:
            print(f'gitmodules   [submodule "{dropped}"]  path {name}, every '
                  "section of that name")
        if kept:
            print("             left in place, though it gives the same "
                  "path: " + ", ".join(f'[submodule "{other}"]'
                                       for other in kept))
        if dropped is not None and _registered(root, dropped):
            print(f'registration [submodule "{dropped}"] in the holder\'s '
                  ".git/config, dropped by `git submodule deinit`")
    print(f"directory    {path}  " + (
        "deleted with everything in it: `git submodule deinit -f` discards "
        "uncommitted work in the member, and `git rm` the directory"
        if os.path.lexists(root / path) else "not on disk"))
    print("\n--dry-run: nothing was changed: the index, .gitmodules, "
          f"{MANIFEST}, the work tree and the holder's git config are as they "
          "were, and no git command that writes was run.")
    return 0


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
    # THE ROW'S `path:` IS CHECKED, NOT TRUSTED (#299), before the first git
    # call: `path: members/*` unmounted every member under one commit naming
    # one, and `path: .` removed the holder's own files.
    path = _member_path(project, row)
    # A `.gitmodules` that gives the path to a second submodule is refused
    # here, before any git command that writes (#360), so the dry run makes
    # the same refusal, as it makes every one above.
    _checked_one_section(family.root, project, path)
    # Every refusal above is the same under `--dry-run`, which leaves here,
    # before the unmount, the real run's first write (#326).
    if args.dry_run:
        return _remove_dry_run(family, row, path)
    # WHAT CAN BE ASKED BEFORE THE UNMOUNT IS (#365); what fails after it is
    # put back (`PinRollback`). A `members:` block this tool will not rewrite
    # was refused after `deinit` and `git rm`, with the member unmounted and
    # `.gitmodules` changed, where the dry run refused it first; it is asked
    # here, as the dry run asks it, so the two refuse in the same words with
    # the holder as it was. Then the lock, which only the real run meets.
    family.rewritten([r for r in family.members
                      if str(r.get("project")) != project])
    _checked_index_unlocked(family.root, path)
    rollback = PinRollback(family.root, path, "remove",
                           (GITMODULES, MANIFEST), unmount=True)
    return _put_back_on_failure(
        rollback, lambda: _unmount_and_drop(family, row, path))


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
    add.add_argument("--trailer", action="append", metavar='"KEY: VALUE"',
                     default=[], type=trailer_line,
                     help="append this `<Key>: <value>` line to the commit "
                          "this writes; repeatable, kept in the order given")
    add.add_argument("--dry-run", action="store_true",
                     help="print the row, the gitlink and the .gitmodules "
                          "section this would write, and its trailers, and "
                          "change nothing in the holder: it READS the member, "
                          "as a real add does, from throwaway clones in "
                          "temporary directories outside the holder, which "
                          "it deletes, and mounts, writes, stages and commits "
                          "nothing")
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
    bump.add_argument("--dry-run", action="store_true",
                      help="print the row this would write, and its "
                           "trailers, and change nothing in the holder: it "
                           "FETCHES the member, as a real bump does, to "
                           "resolve --to and digest it, and checks nothing "
                           "out, writes, stages and commits nothing; exit 1 "
                           "if there is nothing to do")
    bump.set_defaults(func=cmd_bump)

    remove = subparsers.add_parser("remove", help="unmount a member")
    remove.add_argument("--family-root", required=True)
    remove.add_argument("--member", required=True, metavar="PROJECT")
    remove.add_argument("--dry-run", action="store_true",
                        help="print the row, the gitlink, the .gitmodules "
                             "section and the directory this would remove, "
                             "and change nothing")
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
