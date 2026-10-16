#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate this FAMILY's `family.yaml`, its member pins and its shape copies.

A family is a HOLDER: a repository that pins other projects' assembly roots as
submodules under `members/` and carries the utilities to fetch and bootstrap
them together (Brett Heap, 2026-09-04). It has no spec leg and no code leg,
and this validator is the whole of its gate.

IT CONFERS NOTHING, and neither does membership. No row in `family.yaml`
grants review authority, clearance eligibility, gate standing or lifecycle
state over anything it names; a project in no family is reviewed identically.
A consumer deriving a permission from membership is defective.

WHAT IS CHECKED

  - the envelope: `schema_version`, `kind: family-manifest`, `id`, `name`,
    `org`, `created_by` / `created_on`, `visibility`, `members_dir`
  - the family NAME against `contracts/repository-naming.yaml`, in the
    `family` form. That form is DECLARED-ONLY: `InkRouter` is spelled exactly
    like an assembly root and `family.yaml` is what tells them apart, so the
    declaration is this file's existence and the classifier is asked in those
    terms.
  - `shape`: a commit-and-digest pin of the openRepoShape revision this root
    was cut from, `revision_kind: commit`, never a tag
  - across the rows, that no two name ONE `project:`, in any case:
    `members/IRRS` and `members/irrs` are one directory on macOS and Windows,
    whatever `id:` each row records (#331). This one reads `family.yaml`
    alone, so `--no-members` asks it too.
  - EVERY MEMBER, three ways:
      1. the GITLINK this repository records at `members/<Project>` equals
         `members[].pin.commit` — the same lockstep rule an assembly root
         applies to its legs, for the same reason: two facts that can drift
         apart will;
      2. the tree digest recomputed from the member's own object store equals
         `pin.tree_sha256`, so a gitlink and a pin that agree on a commit
         whose bytes are not the pinned bytes is still drift;
      3. the mounted tree carries a `project.yaml` whose `id` is the `id` this
         row records — a repository at the right commit is not by itself the
         project the row claims.
    A row whose `path:` is not `members/<Project>` is the `member-path`
    finding and none of the three is asked of it: nothing read through a
    path the row may not have is a fact about the member (#367). A row
    whose gitlink is recorded only at a case variant of its path is refused
    naming that variant, the index move that puts it back, and what to do
    with a directory the variant leaves on disk (#611). The first is asked
    of every row before the other two are asked of any (#648), so a later
    row's gitlink refusal is never hidden behind an earlier row's
    `member-uninitialized`, as a plain clone whose `git submodule update`
    died at that gitlink left it.
    And, across the rows, that no two record ONE `id`: that is one project
    pinned twice, however each row spelled its repository (#206). This one
    reads `family.yaml` alone, so `--no-members` asks it too.
  - that no two sections of `.gitmodules` give ONE path (#300): a recursive
    clone fetches that path from only one of them, so the other is a url
    the next edit can make the one. It reads that file alone, so
    `--no-members` asks it too.
  - the REVERSE of every member check (#361): that each gitlink this
    repository records in `members/` (the index at stage 0, else HEAD), and
    each path a `.gitmodules` section gives, is a path some row names. A
    member mounted by hand, a row deleted by hand, a section `family.py
    remove` left behind: every check above starts from a row, so none of
    them ever asked. Neither needs a member checked out, so `--no-members`
    asks them too. A path a row names in another case is still one of these,
    and what it says to do depends on which of the two is the member's own:
    it names no command that would un-register the member, and for a member
    recorded only in the wrong case it names the index move that records it
    at its row's path, as the row's own refusal does members checked
    (#648). A gitlink whose removal is staged and not committed, which HEAD
    still records, says to commit it, and prints no `git rm`, which would
    fail (#681).
  - that a section of HEAD's `.gitmodules` gives the path of every row's
    gitlink, the `member-gitmodules-absent` finding (#611, #407's decision
    3). A recursive clone reads HEAD's file, so a gitlink no section of it
    gives is left empty there, by CI and by `make bootstrap`, though the
    holder it was committed in keeps its checkout. It needs no member
    checked out, so `--no-members` asks it too, and a member it names that
    is not checked out is not then refused as uninitialized. A
    `.gitmodules` staged and not committed counts for nothing until it is
    committed, since HEAD's file is the one a clone reads: a `family.py
    add` staged and not committed is this finding for its own member; a
    section taken out and staged, not committed, is no finding; and a file
    put back and staged, not committed, in a holder whose HEAD lost it is
    still this finding for every member.
  - the COPIED shape files, each against its `sha256` row in
    `contracts/shape-pin.yaml`. Editing a copy in place is drift and the exit
    is to carry it upstream, never to update the digest.

EXIT CODES
    0  the manifest is valid, every member is in lockstep, every copy matches
    1  a FINDING: drift a reviewer can act on
    2  a REFUSAL: the question could not be asked — no manifest, an
       uninitialized member (but for one no section of HEAD's `.gitmodules`
       gives: that is `member-gitmodules-absent`, exit 1), an unreadable
       pin, no git to run. An unanswerable question is never an implicit
       pass.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import sys
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_shape import (  # noqa: E402
    COMMIT_RE, PROJECT_ID_RE, PYTHON, SHA256_RE, TREE_DIGEST_DEFINITION,
    VISIBILITY_CHOICES, NamingPolicy, Refusal, file_sha256, find_repo_root,
    git_out, load_yaml, recorded_gitlink, repo_basename, tree_digest,
)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
QUALIFIED_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$")
MANIFEST = "family.yaml"
GITMODULES = ".gitmodules"
DEFAULT_MEMBERS_DIR = "members"
#: A submodule's entry in a tree or the index, as `ls-files -s` and
#: `ls-tree` spell its mode.
GITLINK_MODE = b"160000"

LOCKSTEP = (
    "THE LOCKSTEP RULE: a member's gitlink and its `members[].pin.commit` in "
    "`family.yaml` are ONE invariant. `scripts/family.py bump --member "
    "<Project> --to <commit>` moves both in one commit; moving one alone is "
    "what this refuses."
)

#: The findings THE LOCKSTEP RULE is about (#539): a member's gitlink and its
#: pin out of step, and the pin's digest of the commit they name. The closing
#: count ends at the rule only where one of them was found.
LOCKSTEP_CODES = frozenset({"member-gitlink-mismatch",
                            "member-digest-mismatch"})

#: A branch-name word as `family.py` suggests one (#487, its
#: `BRANCH_WORD_RE`): dot-separated words of lowercase letters, digits, `_`
#: and `-`, and no trailing `.lock`. Anything else is said as `member`.
BRANCH_WORD_RE = re.compile(r"[a-z0-9][a-z0-9_-]*(?:\.[a-z0-9_-]+)*")

#: What a remedy says where it cannot name the member's project, a gitlink
#: whose path gives none: ONE placeholder for the one value, in the branch
#: and in `--member` alike (#539).
PROJECT_PLACEHOLDER = "<Project>"

#: What a remedy that names `_switch_line` says at the end of its prose
#: (#607): where an earlier act left that branch, `switch -c` fails `fatal: a
#: branch named '<branch>' already exists` (exit 128). Another name comes
#: first: it starts the branch where the holder stands now, which works in
#: every state. The same command with `switch` for `switch -c` goes back to
#: the old branch, which is right only where it holds work not merged yet;
#: it keeps its commits, and nothing here names `switch -C`, which resets it.
#: In words, not a second command: this report is read in CI too, where the
#: checkout has none of the person's branches to ask about. `family.py`'s
#: `BRANCH_LEFT`, word for word.
BRANCH_LEFT = ("If `git switch -c` says that branch already exists, an "
               "earlier act left it: give the branch another name, which "
               "starts it where the holder stands, or, only if that branch "
               "holds work not merged yet, the same command with `switch` "
               "in place of `switch -c` goes back to it and keeps every "
               "commit on it.")


def _switch_line(root: Path, verb: str, name: str | None) -> str:
    """`git -C <holder> switch -c family/<verb>-<member>`: the branch
    `family.py add`, `bump` and `remove` refuse to commit without, since a
    holder's tracking branch is refused (`family-on-tracking-branch`, #487),
    spelled as `family.py` suggests it and the holder's docs show it (#539).
    `name` is the member's row `id:` for `remove` and its project for
    `add`, lowercased; None says `PROJECT_PLACEHOLDER`, the one the
    `--member` beside it says. POSIX-quoted, as every other line this file
    prints is. Every remedy that names it ends its prose with `BRANCH_LEFT`
    (#607); openRepoShape's own tests read this file's source and fail one
    that does not."""
    if name is None:
        return (f"git -C {shlex.quote(str(root))} switch -c "
                f"family/{verb}-{PROJECT_PLACEHOLDER}")
    word = name.lower()
    if not BRANCH_WORD_RE.fullmatch(word) or word.endswith(".lock"):
        word = "member"
    return shlex.join(["git", "-C", str(root), "switch", "-c",
                       f"family/{verb}-{word}"])


class Report:
    def __init__(self) -> None:
        self.findings: list[str] = []
        self.notes: list[str] = []
        #: Each finding's code, in step with `findings` (#539).
        self.codes: list[str] = []

    def finding(self, code: str, detail: str) -> None:
        self.findings.append(f"FINDING {code}: {detail}")
        self.codes.append(code)

    def note(self, text: str) -> None:
        self.notes.append(f"  ok  {text}")


@contextmanager
def _git_runs(unread: str) -> Iterator[None]:
    """The `git-not-runnable` refusal, exit 2, for a check that reads this
    holder through git and could not start it (#368).

    `git_out` raises `OSError` when there is no git to run, and nothing here
    caught it: the run ended in a `FileNotFoundError` traceback, which exits
    1, a FINDING's code, though nothing was found. So every check that runs
    git, in every mode, runs it inside this, and `unread` says which check
    it was and what it could not read. ONE code for the whole validator,
    whichever check met the missing git first: it is one fact about the
    machine, and `gitmodules-unreadable` keeps meaning a file git ran and
    could not read.

    Around the git calls ALONE, and never around a whole check: a
    `project.yaml` nobody may read is an `OSError` too, and it is not this.
    """
    try:
        yield
    except OSError as exc:
        raise Refusal(
            "git-not-runnable",
            f"{unread}: git could not be run ({exc.strerror or exc})",
            "Remediation: put git on PATH and run this again. This check "
            "reads the holder the way git does, and nothing could clone it "
            "or fetch its members without git either.") from exc


def _check_schema_kind_and_id(manifest: dict, report: Report) -> None:
    """`schema_version`, `kind` and `id` — three fixed-shape fields that carry
    no lookup and no branch of their own, split from `_check_envelope` for
    #137 so the fields that DO (the name, the dates, the shape block) are not
    buried beside them."""
    if manifest.get("schema_version") != 1:
        report.finding("family-schema-version",
                       f"schema_version is {manifest.get('schema_version')!r}, "
                       "expected 1")
    if manifest.get("kind") != "family-manifest":
        report.finding("family-kind",
                       f"kind is {manifest.get('kind')!r}, expected "
                       "'family-manifest'")
    family_id = manifest.get("id")
    if not isinstance(family_id, str) or not PROJECT_ID_RE.match(family_id):
        report.finding("family-id",
                       f"id is {family_id!r}; it must match "
                       f"{PROJECT_ID_RE.pattern}")


def _check_family_name(manifest: dict, policy: NamingPolicy,
                       report: Report) -> None:
    """The one field in the envelope that is also a naming-policy question:
    is `name` even a string, and if so, does it classify as a family?

    Split from `_check_envelope` for #137: the DECLARED-ONLY classification
    below is its own decision, distinct from the fixed-shape checks beside it.
    """
    name = manifest.get("name")
    if not isinstance(name, str) or not name.strip():
        report.finding("family-name", f"name is {name!r}")
        return
    # THE DECLARED-ONLY FORM, ASKED FOR BY NAME. This manifest IS the
    # declaration, so the classifier is given `family` rather than being
    # left to read a bare CamelCase token as the assembly root it also
    # looks like.
    found = policy.classify(repo_basename(name.strip()), "family")
    if found is None:
        report.finding("naming-unclassified",
                       f"{name!r} matches no family in the naming policy. "
                       "A family holder is one CamelCase token with no "
                       "hyphen, underscore, dot or space.")
    elif found.family != "family":
        report.finding(
            "naming-not-a-family",
            f"{name!r} classifies as {found.family!r}"
            + (f"/{found.role}" if found.role else "")
            + f", not as a family holder ({found.reason})")
    else:
        report.note(f"{name}: {found.family} (declared by {MANIFEST})")


def _check_org_visibility_and_dates(manifest: dict, report: Report) -> None:
    """`org`, `created_by`, `created_on`, `visibility` and `members_dir` —
    five independent fields, none of them read by any other check, split from
    `_check_envelope` for #137."""
    if not isinstance(manifest.get("org"), str) or not manifest.get("org"):
        report.finding("family-org", f"org is {manifest.get('org')!r}")
    if not isinstance(manifest.get("created_by"), str) or \
            not manifest["created_by"].strip():
        report.finding("family-created-by",
                       "created_by is empty. Creating a family is a human's "
                       "act and the manifest records whose.")
    created_on = manifest.get("created_on")
    if not isinstance(created_on, str) or not DATE_RE.match(created_on):
        report.finding("family-created-on",
                       f"created_on is {created_on!r}, expected an ISO date "
                       "YYYY-MM-DD")
    visibility = manifest.get("visibility")
    if visibility is not None and visibility not in VISIBILITY_CHOICES:
        report.finding("family-visibility",
                       f"visibility is {visibility!r}, expected one of "
                       f"{sorted(VISIBILITY_CHOICES)} or no field at all")
    members_dir = manifest.get("members_dir", DEFAULT_MEMBERS_DIR)
    if members_dir != DEFAULT_MEMBERS_DIR:
        report.finding("family-members-dir",
                       f"members_dir is {members_dir!r}; this shape mounts "
                       f"members under {DEFAULT_MEMBERS_DIR!r}, and one name "
                       "is what keeps a reader and a validator looking in the "
                       "same place")


def _check_shape_block(manifest: dict, report: Report) -> None:
    """`shape:` — the commit-and-digest pin of the openRepoShape revision
    this root was cut from. Split from `_check_envelope` for #137: an absent
    block ends the check early exactly as it always did, since nothing below
    it can be asked about a `shape` that is not there."""
    shape = manifest.get("shape")
    if not isinstance(shape, dict):
        report.finding("family-shape",
                       "shape is missing; a family root records the "
                       "openRepoShape revision it was cut from")
        return
    if shape.get("revision_kind") != "commit":
        report.finding("pin-tag-only",
                       f"shape.revision_kind is {shape.get('revision_kind')!r}. "
                       "A tag can be moved and a commit cannot.")
    if not COMMIT_RE.match(str(shape.get("commit") or "")):
        report.finding("family-shape-commit",
                       f"shape.commit is {shape.get('commit')!r}, not 40 hex")
    digests = shape.get("digests")
    if not isinstance(digests, dict) or \
            not SHA256_RE.match(str(digests.get("tree_sha256") or "")):
        report.finding("family-shape-digest",
                       f"shape.digests.tree_sha256 is not 64 hex: {digests!r}")
    if shape.get("digest_definition") != TREE_DIGEST_DEFINITION:
        report.finding("family-shape-digest-definition",
                       f"shape.digest_definition is "
                       f"{shape.get('digest_definition')!r}, expected "
                       f"{TREE_DIGEST_DEFINITION!r}")


def _check_envelope(manifest: dict, policy: NamingPolicy,
                    report: Report) -> None:
    """`schema_version`, `kind: family-manifest`, `id`, `name`, `org`,
    `created_by` / `created_on`, `visibility`, `members_dir` and `shape` — in
    that order, unchanged; each is now its own decision (#137)."""
    _check_schema_kind_and_id(manifest, report)
    _check_family_name(manifest, policy, report)
    _check_org_visibility_and_dates(manifest, report)
    _check_shape_block(manifest, report)


def _member_project_name(row: dict, seen: dict, report: Report) -> str | None:
    """The row's own `project:`, or None when nothing else about this member
    should run — it has none, or its name was already seen once in
    `members:`. Split from `_check_member` for #137: the two ways this
    member's checks stop before they start, in one place.

    A name seen once already stops this row's checks and says nothing: the
    finding for it is `_check_member_names_unique`'s (#331), made before any
    row is checked so `--no-members` makes it too, and made once, not here as
    well."""
    project = row.get("project")
    if not isinstance(project, str) or not project:
        report.finding("member-project", f"a member row has no `project:`: "
                                         f"{row!r}")
        return None
    if project in seen:
        return None
    seen[project] = True
    return project


def _check_member_repository_and_path(row: dict, project: str,
                                      report: Report) -> str | None:
    """`repository:` and `path:` against what they must equal for `project`.

    Split from `_check_member` for #137. Returns `path`, defaulted the same
    way the row itself defaults it, since the gitlink and digest checks that
    follow need the same value. Returns None where that is not the one path
    the row may have, the `member-path` finding: nothing may be read through
    it (#367).
    """
    repository = row.get("repository")
    if not isinstance(repository, str) or not QUALIFIED_RE.match(repository):
        report.finding("member-repository",
                       f"{project}: repository is {repository!r}, expected "
                       "`<org>/<Name>`")
    elif repo_basename(repository) != project:
        report.finding("member-repository-name",
                       f"{project}: repository is {repository!r}, whose name "
                       f"is {repo_basename(repository)!r}. A member's row and "
                       "the repository it pins are the same project or the "
                       "row is describing something else.")

    path = str(row.get("path") or f"{DEFAULT_MEMBERS_DIR}/{project}")
    expected = f"{DEFAULT_MEMBERS_DIR}/{project}"
    if path != expected:
        report.finding("member-path",
                       f"{project}: path is {path!r}, expected {expected!r}, "
                       f"the one path a row for {project} may have. Its "
                       "gitlink, digest and project id are not checked "
                       "through any other.")
        return None
    return path


def _pin_commit(pin: dict, project: str, report: Report) -> str:
    """The pin's `revision_kind` and `commit`, checked; returns the LOWERED
    commit. Split from `_check_member` for #137. Raises `Refusal` for a
    commit nothing after this point can be checked against — an abbreviated
    oid, a branch or a tag is a moving reference."""
    if pin.get("revision_kind") != "commit":
        report.finding("pin-tag-only",
                       f"{project}: pin.revision_kind is "
                       f"{pin.get('revision_kind')!r}. A tag can be moved and "
                       "a commit cannot; a pin is a commit or it is nothing.")
    commit = str(pin.get("commit") or "")
    if not COMMIT_RE.match(commit):
        raise Refusal(
            "member-pin-commit",
            f"{project}: pin.commit is {commit!r}, which is not 40 hex. An "
            "abbreviated oid, a branch or a tag is a moving reference.")
    return commit.lower()


def _check_member_gitlink(root: Path, path: str, commit: str, project: str,
                          repository, gitlinks: dict[str, str],
                          report: Report) -> None:
    """The submodule gitlink this repository records at `path`, against the
    pin — THE LOCKSTEP RULE. Split from `_check_member` for #137. Raises
    `Refusal` when there is no gitlink at all: a row naming a member this
    repository does not record as a submodule (`_gitlink_put_back` says
    what to do). Where `gitlinks` (`_member_gitlinks`) holds one at a case
    variant of `path`, the refusal names that instead (#611)."""
    gitlink = recorded_gitlink(root, path)
    if gitlink is None:
        variants = sorted(other for other in gitlinks if other != path
                          and other.casefold() == path.casefold())
        if variants:
            raise _gitlink_in_another_case(path, commit, project, variants,
                                           gitlinks)
        raise Refusal(
            "member-gitlink-absent",
            f"no gitlink (mode 160000) recorded at {path!r}. {project} is "
            f"named in {MANIFEST} but this repository does not record it as a "
            "submodule.",
            _gitlink_put_back(root, path, commit, repository))
    if gitlink != commit:
        report.finding(
            "member-gitlink-mismatch",
            f"{path}: gitlink {gitlink} != {MANIFEST} pin {commit}\n  "
            + LOCKSTEP)
    else:
        report.note(f"{path}: gitlink == pin {commit[:12]}")


def _gitlink_put_back(root: Path, path: str, commit: str,
                      repository) -> str:
    """What `member-gitlink-absent` says where no case variant of `path`
    holds the gitlink either: a row whose gitlink was taken out by hand, as
    `git rm` takes it out, with its `.gitmodules` section (#681).

    IN WORDS, AS NO TOOL TAKES THIS STATE. It named `family.py add`, which
    refuses the row that is there (`member-already-present`), and `family.py
    remove` dies at its `git submodule deinit` (`pathspec ... did not
    match`), which finds no gitlink, having removed nothing. So a member
    that is to stay has its gitlink put back in the index alone, at the
    commit the row pins, as `_wrong_case_move` records one, and, where no
    section of HEAD's `.gitmodules` gives its path, its section written back
    as `member-gitmodules-absent` writes one (`_section_lines`); and a
    member that is to go has its row taken out by hand. Either is
    committed, and a member put back is checked out as
    `member-uninitialized` says.
    """
    head = _head_gitmodules(root)
    sections = head[1] if head is not None else {}
    given = {keys["path"] for keys in sections.values() if "path" in keys}
    lines = ("" if path in given
             else _section_lines(path, repository, sections))
    written = (", and its .gitmodules section back by hand, in a POSIX "
               "shell, as family.py add writes one, with the lines after it, "
               "then stage .gitmodules" if lines else "")
    return (
        "Remediation: family.py add refuses the row, which is there "
        "(member-already-present), and family.py remove cannot take the "
        "member out, since its git submodule deinit finds no gitlink. If "
        "the member is to stay, put its gitlink back at the commit the row "
        "pins, in the index alone, which touches no file, with the first "
        f"line below{written}. Commit that, and `git submodule update "
        "--init --recursive`, or `make bootstrap`, then checks the member "
        f"out at {path}. If it is to go, take its row out of {MANIFEST} by "
        "hand and commit that.\n"
        "    git update-index --add --cacheinfo "
        f"{shlex.quote(f'160000,{commit},{path}')}{lines}")


def _gitlink_in_another_case(path: str, commit: str, project: str,
                             variants: list[str],
                             gitlinks: dict[str, str]) -> Refusal:
    """`member-gitlink-absent` for a row whose gitlink this repository
    records only at a case variant of its path (#611, #363's item 3), as a
    holder committed in #363's state does: `Members/<P>`, under a row and a
    `.gitmodules` section that say `members/<P>`. A fresh clone checks out
    nothing at the row's path, and the plain refusal's `family.py add`
    cannot help: the row is there already.

    EACH VARIANT IS NAMED, AND THE GITLINK IS MOVED IN THE INDEX ALONE, as
    #574's remedies act on an index entry under another spelling of
    `members/` (Brett Heap, 2026-10-14, "Refuse on every disk"): `git rm -r
    --cached` takes each variant out and touches no file, and `git
    update-index --cacheinfo` records the gitlink at the row's path, at the
    commit the row pins, reading no disk either. So the two lines work on
    every disk, wherever the checkout stands, and the commit after them
    records the member once, at its own path. `member-gitlink-unnamed`
    prints the same move for the same gitlink under `--no-members` (#648),
    and no command that takes it out ALONE, which would un-register the
    member; these take it out and record it together. `--ignore-unmatch`,
    since a variant whose removal is staged and not yet committed is still
    named here, from HEAD, and the plain `git rm` of it failed (`pathspec
    ... did not match`).

    WHAT IS LEFT ON DISK. Where nothing is checked out at the row's path,
    as in a fresh clone, `git submodule update --init --recursive` checks
    the member out there once the move is committed. Where the disk holds
    a variant apart from the row's path, a directory there (the empty one a
    fresh clone leaves, a plain one, or a checkout) stays behind,
    untracked, and `family.py add` refuses it as
    `family-members-dir-variant` (#574), so the text says to move it out of
    the holder, by an `mv` with nothing to fill in, which a shell test
    skips where the disk folds the two names into one directory, the
    row's own, and where the directory is a checkout (#681). A checkout
    is deleted by hand once nothing only it holds is needed.
    """
    found = ", ".join(f"{variant} (at {gitlinks[variant]})"
                      for variant in variants)
    return Refusal(
        "member-gitlink-absent",
        f"no gitlink (mode 160000) recorded at {path!r}. {project} is named "
        f"in {MANIFEST}, and this repository records its gitlink only at a "
        "case variant of that path, which macOS and Windows hold as one "
        f"directory with it: {found}. A recursive clone checks out nothing "
        f"at {path}.",
        "Remediation: the member is recorded in the wrong case. "
        + _wrong_case_move(path, commit, variants))


def _wrong_case_move(path: str, commit: str, variants: list[str]) -> str:
    """The index move for a member recorded only at `variants`, case
    variants of its row's `path`, to `path` at the pinned `commit`, with
    what it leaves on disk: what `_gitlink_in_another_case` says, and
    `member-gitlink-unnamed` under `--no-members` (#648), in one text.

    EACH `mv` IS GUARDED BY TWO TESTS A POSIX SHELL RUNS (#681, rv611c's
    N-1 and N-2), not by a system's name: this text is read in CI too, on
    another disk than the one it is typed on. `[ <variant> -ef <path> ]` is
    true where the disk takes the two names for one directory, the row's
    own, as a Linux mount that folds case does too (WSL's `/mnt/c`), where
    the `mv` moved the member's own checkout out. `[ -e <variant>/.git ]`
    is true for a checkout, and a submodule's `.git` is a file naming this
    holder's `.git/modules/` by a relative path, which a move leaves
    pointing nowhere (`fatal: not a git repository`). So the `mv` runs only
    for a directory apart from the row's with no `.git` entry, the empty one
    a fresh clone leaves or a plain one, and the text says where a
    submodule checkout's commits are kept, what deleting it would lose, and
    to delete a checkout by hand once nothing it holds is needed.
    """
    taken_out = " ".join(shlex.quote(variant) for variant in variants)
    moved = " and ".join(
        f"`[ {shlex.quote(variant)} -ef {shlex.quote(path)} ] || "
        f"[ -e {shlex.quote(variant + '/.git')} ] || "
        f"mv -- {shlex.quote(variant)} "
        f"{shlex.quote('../' + variant.replace('/', '-'))}`"
        for variant in variants)
    stores = " or ".join(f".git/modules/{variant}" for variant in variants)
    status = " or ".join(f"`git -C {shlex.quote(variant)} status`"
                         for variant in variants)
    return (
        "Move its gitlink to the row's path, at the commit the row pins, in "
        "the index alone, which touches no file, with the two lines below, "
        f"and commit that. Where nothing is checked out at {path}, as in a "
        "fresh clone, `git submodule update --init --recursive` then checks "
        "the member out there. A directory left at "
        f"{' or '.join(variants)} is the row's own where the disk folds "
        "case, as macOS's and Windows' usually do and a Linux mount can "
        "(WSL's /mnt/c). Where the disk holds the two apart it stays there, "
        "untracked, and family.py add refuses it as "
        "family-members-dir-variant: move each one that is there out of the "
        f"holder, {moved}, which moves nothing where the two names are one "
        "directory or where it holds a .git entry, a checkout. A checkout "
        "git submodule add made there holds a .git file naming this "
        "holder's .git/modules/ by a path relative to it, which a move would "
        f"leave pointing nowhere; its commits are kept in {stores}, whatever "
        "becomes of the directory, and only what is not committed is in the "
        f"directory alone ({status} shows it). Delete a checkout by hand "
        "once nothing it holds is needed. The two lines:\n"
        f"    git rm -r --cached --ignore-unmatch -- {taken_out}\n"
        "    git update-index --add --cacheinfo "
        f"{shlex.quote(f'160000,{commit},{path}')}")


def _check_member_tree(member: Path, pin: dict, path: str, commit: str,
                       project: str, report: Report) -> None:
    """Is `member`'s own object store readable at `commit`, and does its
    digest match the pin? Split from `_check_member` for #137 — the two
    questions were already one comment block ("the digest and the identity")
    in the source. Raises `Refusal` when the tree cannot even be read: an
    uninitialized submodule, or a commit its checkout does not have. Presence
    is not identity and an unreadable surface must fail rather than degrade.
    """
    if not (member / ".git").exists():
        raise Refusal(
            "member-uninitialized",
            f"{path} is not an initialized submodule checkout, so neither the "
            "pinned digest nor the project it claims can be read. Presence is "
            "not identity and an unreadable surface must fail rather than "
            "degrade.",
            "Remediation: `git submodule update --init --recursive`, or `make "
            "bootstrap`, which resolves a credential for private members "
            "first.")
    try:
        git_out(["rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}"],
                cwd=member)
    except Refusal as exc:
        raise Refusal(
            "member-commit-unresolvable",
            f"{path}: the pinned commit {commit} is not in that member's "
            f"object store ({exc.detail})") from exc

    recorded = pin.get("tree_sha256")
    if not isinstance(recorded, str) or not SHA256_RE.match(recorded):
        report.finding("member-digest-malformed",
                       f"{project}: pin.tree_sha256 is {recorded!r}, not 64 hex")
    elif pin.get("digest_definition", TREE_DIGEST_DEFINITION) != \
            TREE_DIGEST_DEFINITION:
        report.finding(
            "member-digest-definition",
            f"{project}: pin.digest_definition is "
            f"{pin.get('digest_definition')!r}, expected "
            f"{TREE_DIGEST_DEFINITION!r}. A digest whose definition is "
            "unstated is a number, not an identity.")
    else:
        actual = tree_digest(member, commit)
        if actual.lower() != recorded.lower():
            report.finding(
                "member-digest-mismatch",
                f"{project}: pin.tree_sha256 {recorded}\n"
                f"       recomputed at {commit[:12]} {actual}\n"
                "  The gitlink and the pin may agree on a commit whose bytes "
                f"are not the bytes the pin was written against.\n  {LOCKSTEP}")
        else:
            report.note(f"{path}: tree digest recomputes ({recorded[:12]}…)")


class Gitlinked(NamedTuple):
    """A member `_check_member` asked up to its gitlink, with what
    `_check_member_checkout` reads its checkout by."""

    row: dict
    project: str
    path: str
    pin: dict
    commit: str


def _check_member(root: Path, row: dict, seen: dict, report: Report,
                  gitlinks: dict[str, str]) -> Gitlinked | None:
    """One member up to its checkout: the row itself and the gitlink. The
    member, for `_check_member_checkout` to ask its digest and identity of,
    or None where nothing more is asked of it.

    NOTHING IS READ THROUGH A PATH THE ROW MAY NOT HAVE (#367). A hand-edited
    `path:` is `member-path`, and this member's checks stop once its pin is
    read: the pin is a fact of the row, and everything after it is read at
    the path. They used to go on. At `members/*` the gitlink listing took the
    path for a glob and answered with a neighbour's commit, gathered as this
    member's `member-gitlink-mismatch`, and the tree check then refused
    `member-uninitialized`, whose remedy cannot help, and whose refusal
    dropped both findings unprinted.

    The git each check runs is run inside `_git_runs`, which names the check
    when there is no git to run (#368); the identity check reads a file and
    runs none.
    """
    project = _member_project_name(row, seen, report)
    if project is None:
        return None

    path = _check_member_repository_and_path(row, project, report)

    pin = row.get("pin")
    if not isinstance(pin, dict):
        report.finding("member-pin", f"{project}: `pin:` is {pin!r}, expected "
                                     "a mapping")
        return None
    commit = _pin_commit(pin, project, report)
    if path is None:
        return None

    # ---- the gitlink -------------------------------------------------------
    with _git_runs(f"the gitlink recorded at {path} could not be read"):
        _check_member_gitlink(root, path, commit, project,
                              row.get("repository"), gitlinks, report)
    return Gitlinked(row, project, path, pin, commit)


def _check_member_checkout(root: Path, asked: Gitlinked, report: Report,
                           unregistered: set[str]) -> None:
    """One member's digest and identity, read in its checkout, asked once
    every row's gitlink has been (`_check_members`, #648).

    A MEMBER NO SECTION OF HEAD'S `.gitmodules` GIVES (`unregistered`, the
    `member-gitmodules-absent` finding, #611) that is not checked out is
    asked nothing here. Refused `member-uninitialized`, it named `git
    submodule update --init`, which exits 0 there and checks nothing out,
    and the refusal dropped the finding that says why: the state a fresh
    clone of a holder whose HEAD lost `.gitmodules` is in, and CI's. The
    finding is made all the same, so the run still fails.
    """
    member = root / asked.path
    if asked.path in unregistered and not (member / ".git").exists():
        return
    with _git_runs(f"{asked.project}'s pinned commit and its tree digest "
                   f"could not be read in {asked.path}"):
        _check_member_tree(member, asked.pin, asked.path, asked.commit,
                           asked.project, report)
    _check_member_identity(member, asked.row, asked.project, report)


def _check_member_identity(member: Path, row: dict, project: str,
                           report: Report) -> None:
    """The mounted tree is the PROJECT this row claims, not just a commit.

    A member is an assembly root, so it carries `project.yaml`, and that file
    is the SOURCE of what that project is. The row here is a pin of it. Where
    the two disagree the row is wrong, because a family cannot rename a
    project by describing it differently.
    """
    manifest_path = member / "project.yaml"
    if not manifest_path.is_file():
        report.finding(
            "member-not-a-project",
            f"{row.get('path')}: no project.yaml in the mounted tree. A member "
            "is a project's ASSEMBLY ROOT — the repository an engineer clones "
            "— and a family pins assembly roots, never legs.")
        return
    try:
        manifest = load_yaml(manifest_path)
    except Refusal as exc:
        report.finding("member-manifest-unreadable",
                       f"{row.get('path')}/project.yaml: {exc.detail}")
        return
    if not isinstance(manifest, dict):
        report.finding("member-manifest-unreadable",
                       f"{row.get('path')}/project.yaml: not a mapping")
        return
    recorded_id = row.get("id")
    actual_id = manifest.get("id")
    if recorded_id is None:
        report.finding(
            "member-id-absent",
            f"{project}: the row records no `id:`, so nothing checks that the "
            "tree mounted here is the project this row claims")
    elif str(recorded_id) != str(actual_id):
        report.finding(
            "member-id-mismatch",
            f"{row.get('path')}: project.yaml declares id {actual_id!r} but "
            f"{MANIFEST} records {recorded_id!r} for {project}. The project's "
            "own manifest is the source; this row is a pin of it.")
    else:
        report.note(f"{row.get('path')}: project.yaml id {actual_id}")


def _load_shape_pin(root: Path) -> tuple[dict, str]:
    """`contracts/shape-pin.yaml`, read and validated as a mapping.

    Split from `_check_shape_pin` for #137. Raises `Refusal` for a pin this
    validator cannot read at all — absent, or not a mapping — the same two
    ways every other REFUSAL in this file is unreadable.
    """
    pin_path = root / "contracts" / "shape-pin.yaml"
    if not pin_path.is_file():
        raise Refusal("shape-pin-missing", f"{pin_path} does not exist")
    pin = load_yaml(pin_path)
    # POSIX, on every platform: a finding names a path in THIS repository,
    # and `str()` of a relative Path on Windows spells it with backslashes —
    # a path the reader cannot paste back into git.
    rel = pin_path.relative_to(root).as_posix()
    if not isinstance(pin, dict):
        raise Refusal("shape-pin-unreadable", f"{pin_path}: not a mapping")
    return pin, rel


def _check_shape_pin_envelope(pin: dict, rel: str, manifest: dict,
                              report: Report) -> str:
    """`revision_kind`, `commit` and its agreement with `family.yaml`.

    Split from `_check_shape_pin` for #137. Returns the (un-lowered) `commit`
    string exactly as the parent used to hold it in its own local variable —
    nothing downstream reads it, but the shape matches every other `_pin_*`
    helper in this file.
    """
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
                       f"{rel} commit {commit} != {MANIFEST} shape.commit "
                       f"{declared}")
    return commit


def _check_one_shape_file(root: Path, rel: str, row, report: Report) -> None:
    """One `files:` row: present, and its digest matches its `sha256`.

    Split from `_check_shape_pin` for #137 — the per-row body of its loop.
    A row that is no mapping, or whose `path:` is absent, empty or no
    string, is `shape-pin-row`, as `update-shape.py` refuses it
    `update-pin-row`: its `path:` was read as a path, so a row with none
    was `None is pinned but absent` (#681).
    """
    if not isinstance(row, dict):
        report.finding("shape-pin-row", f"{rel}: a files row is not a mapping")
        return
    path = row.get("path")
    if not isinstance(path, str) or not path:
        report.finding("shape-pin-row", f"{rel}: a files row's `path:` is "
                                        f"{path!r}, not the path of a file")
        return
    target = root / path
    if not target.is_file():
        report.finding("shape-copy-missing",
                       f"{rel}: {row.get('path')} is pinned but absent")
        return
    actual = file_sha256(target)
    if actual != str(row.get("sha256", "")).lower():
        report.finding(
            "shape-copy-drift",
            f"{row.get('path')}: sha256 {actual}\n"
            f"       {rel} records {row.get('sha256')}\n"
            "  A shape file was edited in place. Either revert it, or "
            "carry the change upstream to openRepoShape and re-pin with "
            "`update-shape.py`.")


def _check_shape_pin_files(root: Path, pin: dict, rel: str,
                           report: Report) -> None:
    """Every `files:` row, and the summary note when none of them drifted.

    Split from `_check_shape_pin` for #137.
    """
    before = len(report.findings)
    files = pin.get("files") or []
    if not isinstance(files, list):
        # Asked, not assumed (#290): `files: 5` was iterated, and the run
        # ended in a TypeError with no finding naming the pin.
        report.finding("shape-pin-row",
                       f"{rel}: `files:` is {files!r}, not a list of "
                       "`path:`/`sha256:` rows, so nothing about the copied "
                       "shape files is actually asserted")
        return
    if not files:
        report.finding("shape-pin-no-files",
                       f"{rel}: no `files:` rows, so nothing about the copied "
                       "shape files is actually asserted")
    for row in files:
        _check_one_shape_file(root, rel, row, report)
    if len(report.findings) == before:
        report.note(f"{rel}: {len(files)} copied shape file(s) match their "
                    "digests")


def _check_shape_pin(root: Path, manifest: dict, report: Report) -> None:
    """The COPIED shape files, each against its digest. Same rule everywhere.

    A family root holds copies of openRepoShape rather than mounting it, so
    there is no gitlink to compare and the identity of the copies is carried
    by the per-file `sha256` rows.
    """
    pin, rel = _load_shape_pin(root)
    _check_shape_pin_envelope(pin, rel, manifest, report)
    _check_shape_pin_files(root, pin, rel, report)


def _check_member_names_unique(members: list, report: Report) -> None:
    """No two rows of `members:` name ONE project, in any case — the
    `member-duplicate` finding (#331).

    It reads `members:` alone, so it runs under `--no-members` too, the run a
    private family's CI falls back to when its members cannot be checked out,
    and it runs before any row is checked, as `member-duplicate-id` does
    (#206). `_member_project_name` used to make this finding, and only the
    members-checked loop reaches that, so `--no-members` passed a
    `family.yaml` that named one row twice. It is made HERE and once, in
    every mode: `_member_project_name` still skips a row it has already seen,
    and says nothing.

    Two spellings that differ only in case are one row: `members/IRRS` and
    `members/irrs` are ONE directory on a case-insensitive disk (macOS,
    Windows), where a holder can mount only one of them, whatever `id:` each
    row records. The rows' ids are no help here and `member-duplicate-id`'s
    question is a different one: it asks whether one PROJECT is mounted
    twice, this asks whether one DIRECTORY is named twice.

    THE FOLD IS `str.casefold()`, as the standard's other same-path-in-any-case
    checks use it (`shape_materialize.py`, `adopt-project.py`). `family.py add`
    only writes ASCII names (`checked_value`: `[A-Za-z0-9._/@+~-]`), and a
    members-checked run refuses any other as `member-repository`
    (`QUALIFIED_RE`) or `member-repository-name`. Under `--no-members` neither
    runs, so a hand edit can put ANY string in `project:`, and a disk folds
    more than ASCII case: the long s (U+017F) folds to `s`, and a final sigma
    (U+03C2) to a small sigma (U+03C3), so `IRRS` and `irrs` spelt with the
    long s, or a name in capital sigmas and the same name in small ones, are
    one directory there, and `lower()` keeps each pair apart. On every name
    `family.py` can write the two folds agree, and `Family.member` in
    `family.py` compares with `lower()` (#206), so the tool that writes the
    rows and this gate cannot disagree about a row the tool wrote.
    `casefold()` is no one disk's own fold either: NTFS's table does not fold
    the German sharp s (U+00DF) to `ss`, so for such a pair this may name a
    collision that disk does not make, and APFS also ignores normalization,
    which no fold here handles. It errs on the side of a gate that says one
    row has to go.

    A row whose spelling an earlier row already has, to the byte, keeps the
    finding it always had. A row that differs only in case, as a
    case-insensitive disk folds it, names BOTH rows as written. Either way
    each later row is one finding, against the first row that holds its name.
    A row with no `project:` is `member-project`'s, and a row that is no
    mapping is `member-row`'s: both are skipped here, as
    `_check_member_ids_unique` skips them.
    """
    spelled: set[str] = set()
    first_folded: dict[str, str] = {}
    for row in members:
        if not isinstance(row, dict):
            continue
        project = row.get("project")
        if not isinstance(project, str) or not project:
            continue
        if project in spelled:
            report.finding("member-duplicate",
                           f"{project} appears more than once in `members:`")
            continue
        spelled.add(project)
        first = first_folded.setdefault(project.casefold(), project)
        if first != project:
            report.finding(
                "member-duplicate",
                f"{first} and {project} are two rows of `members:` whose "
                f"`project:` differs only in case, so `members/{first}` and "
                f"`members/{project}` are one directory on a case-insensitive "
                "disk (macOS, Windows), and a holder there can keep only one "
                "of them. Whether the rows pin one project or two, one of "
                "them has to go: keep the row whose `repository:` is the "
                "member's and drop the other.")


def _check_member_ids_unique(root: Path, members: list,
                             report: Report) -> None:
    """No two rows record ONE `id:` — that is one project pinned twice (#206).

    `id` is the member's own `project.yaml` id, so two rows recording the same
    one mount the same project twice, however each row spelled its repository:
    GitHub resolves `InkRouter/IRRS` and `inkrouter/irrs` to one repository,
    and a `family.py add` that compared the spelling used to write both rows
    and pass this gate. A row with no `id:` is `member-id-absent`'s finding
    and a row with no `project:` is `member-project`'s, not this one's.

    A row whose `project:` an earlier row already spells EXACTLY is
    `member-duplicate`'s finding and is skipped here: one finding for one
    fault, and the `remove` this one prints would take out both of those
    rows, because `family.py remove` drops every row spelled that way.

    It reads `family.yaml` alone, so it runs under `--no-members` too — the
    run a private family's CI falls back to when its members cannot be
    checked out. The remediation is runnable as printed: openRepoShape's
    `scripts/family.py` from a checkout of the standard, this holder's own
    path, and the later row's own spelling, which `remove` matches exactly;
    and before it the `git switch -c` that `remove` needs on a holder that
    stands on its tracking branch, which it refuses (#487, #539).
    """
    ids: dict[str, str] = {}
    projects: set[str] = set()
    for row in members:
        if not isinstance(row, dict):
            continue
        project = row.get("project")
        if not isinstance(project, str) or not project or project in projects:
            continue
        projects.add(project)
        if not row.get("id"):
            continue
        member_id = str(row["id"])
        if member_id not in ids:
            ids[member_id] = project
            continue
        first = ids[member_id]
        report.finding(
            "member-duplicate-id",
            f"{project} and {first} both record id {member_id!r}: one "
            "project is pinned twice. A family pins each project once. From "
            "a checkout of openRepoShape, and on a branch other than the "
            "holder's tracking branch, which `remove` refuses "
            f"(`{_switch_line(root, 'remove', member_id)}` makes one), "
            f"`{PYTHON} scripts/family.py remove "
            f"--family-root {shlex.quote(str(root))} --member "
            f"{shlex.quote(project)}` takes the later row, {project}, out; "
            f"name {first} there instead to keep {project}. {BRANCH_LEFT}")


def _gitmodules_sections(root: Path) -> dict[str, dict[str, str]]:
    """Every `submodule` section of `.gitmodules`, `{name: {key: value}}`,
    each key in the order git lists it: the file read ONCE for the two
    questions asked of it, two sections for one path (#300) and a path no
    row names (#361).

    READ AS GIT READS IT, with `git config -z --file .gitmodules --list` as
    `family.py` reads it, and no parser of this file's own: the working-tree
    file, which in CI is HEAD's. A holder with no members has no
    `.gitmodules`, and that is no finding; one git cannot read is a refusal,
    because nothing could be cloned from it either. EVERY KEY a section
    holds is kept, not its path and url alone, because the remedy for a
    section no row names takes each of them out (`family.py`'s
    `_submodule_paths` says why: a key left behind is inherited).

    No git to run is `git-not-runnable` (#368). It used to be
    `gitmodules-unreadable`, which now means only a file git ran and could
    not read: the missing git is one fact about the machine, and every check
    here that meets it says so under one code.
    """
    if not os.path.lexists(root / GITMODULES):
        return {}
    with _git_runs(f"{GITMODULES} could not be read as git reads it"):
        try:
            listed = git_out(["config", "-z", "--file", GITMODULES, "--list"],
                             cwd=root, binary=True)
        except Refusal as exc:
            raise Refusal(
                "gitmodules-unreadable",
                f"{GITMODULES} could not be read as git reads it: "
                f"{exc.detail}",
                "Remediation: git cannot read it either, so none of this "
                "holder's submodules can be cloned from it as it stands. Mend "
                f"the file by hand (`git config -f {GITMODULES} --list` says "
                "where it breaks), then run this again.") from exc
    return _sections_listed(listed)


def _sections_listed(listed: bytes) -> dict[str, dict[str, str]]:
    """`{name: {key: value}}` of every `submodule` section in what `git
    config -z --list` printed, each key in the order git lists it: one
    reading for the work tree's `.gitmodules` and HEAD's (#611)."""
    sections: dict[str, dict[str, str]] = {}
    for record in listed.split(b"\0"):
        key, _, value = record.decode("utf-8",
                                      "surrogateescape").partition("\n")
        section, _, variable = key.rpartition(".")
        if section.startswith("submodule."):
            sections.setdefault(section[len("submodule."):],
                                {})[variable] = value
    return sections


def _head_gitmodules(root: Path
                     ) -> tuple[bool, dict[str, dict[str, str]]] | None:
    """`(whether HEAD holds a .gitmodules, its sections)`, read as
    `_gitmodules_sections` reads the work tree's, or None for a HEAD git
    cannot list, a holder before its first commit, which a clone cannot
    take either (#611).

    HEAD'S, NOT THE WORK TREE'S: a recursive clone of this holder, and CI's
    checkout, read the file HEAD holds. A work tree's copy nobody has
    committed is no fact about what a clone gets, and neither is one a
    sparse checkout leaves out of the work tree or a deletion nobody has
    committed. HEAD's ROOT TREE is listed and the entry picked by name, with
    no pathspec, as `_member_gitlinks` lists HEAD. One git cannot read is
    `gitmodules-unreadable`, as the work tree's is.
    """
    with _git_runs(f"HEAD's {GITMODULES} could not be read as git reads it"):
        try:
            tree = git_out(["ls-tree", "-z", "HEAD"], cwd=root, binary=True)
        except Refusal:
            return None
        blob = next((meta.split()[2].decode("ascii")
                     for meta, _, name in (record.partition(b"\t")
                                           for record in tree.split(b"\0"))
                     if name == GITMODULES.encode()
                     and meta.split()[1:2] == [b"blob"]), None)
        if blob is None:
            return False, {}
        try:
            listed = git_out(["config", "-z", "--blob", blob, "--list"],
                             cwd=root, binary=True)
        except Refusal as exc:
            raise Refusal(
                "gitmodules-unreadable",
                f"HEAD's {GITMODULES} could not be read as git reads it: "
                f"{exc.detail}",
                "Remediation: git cannot read it either, so none of this "
                "holder's submodules can be cloned from it. Mend the file by "
                f"hand (`git config -f {GITMODULES} --list` says where it "
                "breaks), commit it, then run this again.") from exc
    return True, _sections_listed(listed)


def _check_gitmodules_paths(sections: dict[str, dict[str, str]],
                            report: Report) -> None:
    """No two sections of `.gitmodules` give ONE path (#300).

    `family.py add` committed a second section for a mount path that a
    section under another name already gave — a half-removed member, a hand
    edit, a merge that kept both sides — and this gate passed the result. A
    recursive clone fetches the path from only one of them, the last in the
    file, so the other is a url the next edit to the file can make the one
    fetched. `add` refuses to write one now; this finds a holder that
    already has one. `sections` is `_gitmodules_sections`'s reading. A
    section whose path no row names is `_check_gitmodules_named`'s question
    (#361).
    """
    paths: dict[str, list[str]] = {}
    for name, keys in sections.items():
        if "path" in keys:
            paths.setdefault(keys["path"], []).append(name)
    for path, names in paths.items():
        if len(names) < 2:
            continue
        listing = ", ".join(
            f"`{name}` (" + (f"url {sections[name]['url']}"
                             if "url" in sections[name] else "no url") + ")"
            for name in names)
        report.finding(
            "gitmodules-path-twice",
            f"{GITMODULES} gives the path {path} to {len(names)} "
            f"submodules, {listing}. A recursive clone fetches that path "
            "from only one of them, the last in the file, so the order of "
            "the sections decides which repository lands there. Keep the one "
            "whose url is the member's (`family.py add` names it after its "
            f"path, `{path}`) and take each other out by hand, `git config "
            f"-f {GITMODULES} --unset-all submodule.<name>.<key>` for every "
            "key that section holds, so a submodule later given its name "
            f"inherits none of them, then commit {GITMODULES}.")


def _member_gitlinks(root: Path) -> dict[str, str]:
    """`{path: commit}` for every gitlink this repository records in
    `members/`, the directory spelt in any case: what `_check_gitlinks_named`
    asks of each (#361).

    IN THE ORDER `recorded_gitlink` READS ONE: the index at stage 0 first,
    HEAD second. A path the index holds at stage 0 as a gitlink is answered
    from there, any other gitlink HEAD records from HEAD, so this lists
    exactly the paths at which that function finds a gitlink, and each with
    the commit it would answer.

    THE WHOLE INDEX AND THE WHOLE TREE, WITH NO PATHSPEC, as `family.py`'s
    `_index_entries` lists the index (#302): a pathspec matches `members/`
    only in the case it is spelt, and `Members/Zed` is in `members/` on
    macOS and Windows. `-z`, so a name git would quote comes back as itself.

    A HEAD git cannot list is read as recording nothing, as
    `recorded_gitlink` reads it: a holder before its first commit has none.
    An index git cannot list is `gitlinks-unreadable`: this is the one check
    of `members/` that `--no-members` runs, and a directory nobody could
    list is never an implicit pass.
    """
    with _git_runs(f"the gitlinks this repository records in "
                   f"{DEFAULT_MEMBERS_DIR}/ could not be listed"):
        try:
            head = git_out(["ls-tree", "-r", "-z", "HEAD"], cwd=root,
                           binary=True)
        except Refusal:
            head = b""
        try:
            index = git_out(["ls-files", "-s", "-z"], cwd=root, binary=True)
        except Refusal as exc:
            raise Refusal(
                "gitlinks-unreadable",
                f"the index could not be listed, so the gitlinks it records "
                f"in {DEFAULT_MEMBERS_DIR}/ could not be read: {exc.detail}",
                "Remediation: git status in this repository says what is "
                "wrong with its index. Mend that, then run this "
                "again.") from exc
    found: dict[str, str] = {}
    for listing, oid_at, stage_at in ((head, 2, None), (index, 1, 2)):
        for record in listing.split(b"\0"):
            meta, _, name = record.partition(b"\t")
            fields = meta.split()
            if len(fields) != 3 or fields[0] != GITLINK_MODE:
                continue
            if stage_at is not None and fields[stage_at] != b"0":
                continue
            path = name.decode("utf-8", "surrogateescape")
            if path.split("/", 1)[0].casefold() == DEFAULT_MEMBERS_DIR:
                found[path] = fields[oid_at].decode("ascii").lower()
    return found


def _staged_removals(root: Path, gitlinks: dict[str, str]) -> frozenset[str]:
    """The paths of `gitlinks` (`_member_gitlinks`) whose removal is staged
    and not committed (#681): HEAD records the gitlink, and the index holds
    no entry at that path, at any stage. A `git rm` of one fails (`pathspec
    ... did not match any files`), so a finding about one says to commit
    the removal and prints none: it named the same `git rm` until the
    commit. A path the index holds unmerged is a conflict, not a removal,
    and is not one of these. The whole index, `-z`, as `_member_gitlinks`
    lists it."""
    with _git_runs(f"the gitlinks this repository records in "
                   f"{DEFAULT_MEMBERS_DIR}/ could not be listed"):
        listed = git_out(["ls-files", "-z"], cwd=root, binary=True)
    indexed = {name.decode("utf-8", "surrogateescape")
               for name in listed.split(b"\0")}
    return frozenset(set(gitlinks) - indexed)


class RowPath(NamedTuple):
    """What a row names by the path it gives: `who` names the row in a
    finding, `canonical` is the one path its project may have,
    `members/<project>`, or None for a row with no `project:`, and `pin` is
    the commit its `pin:` names, lowered, or None where that is no 40-hex
    commit (#648)."""

    who: str
    canonical: str | None
    pin: str | None = None


def _row_paths(members: list) -> dict[str, RowPath]:
    """`{path: RowPath}` for every row that gives a path: its `path:`, or
    `members/<project>` where it has none, defaulted as
    `_check_member_repository_and_path` defaults it. `who` names the row in
    a finding: `the row for <project>`, or, for a row with no `project:`
    (`member-project`'s), `a row with no project:`.

    A row NAMES the path it gives, AS WRITTEN (#361), and nothing else: a
    hand-edited `path:` names that string, so the member's own mount is then
    a gitlink no row names, beside the row's `member-path` finding. The
    row's canonical path rides along, because what to say about a path that
    folds to the row's depends on which of the two is the canonical one.
    """
    named: dict[str, RowPath] = {}
    for row in members:
        if not isinstance(row, dict):
            continue
        project = row.get("project")
        if not isinstance(project, str) or not project:
            project = None
        canonical = (f"{DEFAULT_MEMBERS_DIR}/{project}"
                     if project is not None else None)
        if row.get("path"):
            path = str(row["path"])
        elif canonical is not None:
            path = canonical
        else:
            continue
        pin = row.get("pin")
        commit = str(pin.get("commit") or "") if isinstance(pin, dict) else ""
        named.setdefault(path, RowPath(
            f"the row for {project}" if project else "a row with no project:",
            canonical, commit.lower() if COMMIT_RE.match(commit) else None))
    return named


def _case_variant(path: str,
                  named: dict[str, RowPath]) -> tuple[str, RowPath] | None:
    """`(row path, row)` of a row naming `path` in another case, or None.

    `str.casefold()`, as `member-duplicate` folds (#331): on macOS and
    Windows `Members/Atlas` IS `members/Atlas`, so a finding about the one
    says which row the other belongs to.
    """
    folded = path.casefold()
    for row_path, row in named.items():
        if row_path.casefold() == folded:
            return row_path, row
    return None


#: The three things a path that folds to a row's path can be, and so what a
#: finding about it may tell an operator to run: `STRAY`, a second path to
#: the member's own directory, which a command can take out; `ROW_EDITED`,
#: the member's own path, whose row was hand-edited into a case variant of
#: it; and `WRONG_CASE`, the only record of the member there is, in the
#: wrong case.
STRAY, ROW_EDITED, WRONG_CASE = "stray", "row-edited", "wrong-case"

#: What a gitlink or a section nobody can account for says to do when the
#: fault may be in the row, in `git log -p -- family.yaml`'s words.
RESTORE_ROW = ("If its row was deleted or its path: edited by hand, put the "
               "row back as git last had it (git log -p -- family.yaml shows "
               "the change).")


def _variant_case(path: str, row_path: str, row: RowPath,
                  holds: set[str]) -> str:
    """Which of `STRAY`, `ROW_EDITED` and `WRONG_CASE` the path `path`, which
    folds to the path `row_path` that `row` names, is (#361).

    `holds` is every exact path that holds what is being asked about: the
    gitlinks, or the paths the sections give. A command that takes `path` out
    leaves the member standing in ONE state only, `STRAY`: the row's path is
    its canonical `members/<project>` AND that exact path holds a gitlink (a
    section) too, so `path` is a second one. In the other two it takes the
    member's own record out, and every mode that does not check members would
    then say `family ok`:

    - `ROW_EDITED`: `path` IS the row's canonical path and the row spells it
      another way, a mount at `members/Nova` and a row written `Members/Nova`.
      The row is the hand edit, and the cure is in `family.yaml`.
    - `WRONG_CASE`, any other: the row's path is canonical with nothing at it,
      so `path` is the only record there is, in the wrong case; or the row's
      path is no canonical one either and `path` is a third spelling, which
      this does not decide while the row is wrong.
    """
    if row_path == row.canonical and row_path in holds:
        return STRAY
    if path == row.canonical:
        return ROW_EDITED
    return WRONG_CASE


def _variant_said(row_path: str, row: RowPath) -> str:
    """The sentence that says a path is a case variant of a row's."""
    return (f" It is a case variant of {row_path}, which {row.who} names, and "
            "macOS and Windows hold the two as one directory.")


def _variant_advice(kind: str, path: str, row_path: str, row: RowPath,
                    what: str) -> str:
    """What a `ROW_EDITED` or `WRONG_CASE` path says, in place of a command.

    `what` is `gitlink` or `section`. No command is printed in either: the
    `git rm --cached` or the `--unset-all` lines that suit a `STRAY` would
    take the member's own record out, and a family whose members a runner
    could not check out would then pass. A `ROW_EDITED` says the row is what
    is wrong, and where to put its path back; a `WRONG_CASE` says the member
    is recorded in the wrong case, and sends the operator to `git log -p --
    family.yaml`, as an unnamed path that no row folds to does (`RESTORE_ROW`).
    A `WRONG_CASE` gitlink whose row's path is its canonical one and whose
    pin is a commit never comes here: `_check_gitlinks_named` prints the
    index move for it, which records the member as it takes the gitlink out
    (#648).
    """
    if kind == ROW_EDITED:
        return (f" It is {path}, the one path {row.who} may have, and the row "
                f"names it as {row_path} instead, which macOS and Windows "
                "hold as one directory with it. The row's path: is the hand "
                f"edit and this {what} is the member's own: put {path} back "
                "in the row's path: (git log -p -- family.yaml shows the "
                f"change). No command is printed, since this {what} is not "
                "what is wrong.")
    return (_variant_said(row_path, row)
            + " The member is recorded in the wrong case, so no command is "
              f"printed: taking this {what} out could un-register it. "
            + RESTORE_ROW)


def _check_gitlinks_named(root: Path, gitlinks: dict[str, str],
                          named: dict[str, RowPath], removed: frozenset[str],
                          report: Report) -> None:
    """Every gitlink in `members/` is at a path some row names EXACTLY — the
    `member-gitlink-unnamed` finding (#361).

    Every member check starts from a row, so a gitlink no row names was
    never asked about: a member mounted by hand with `git submodule add`, or
    a row deleted by hand. A recursive clone of the holder fetches it all
    the same, and so does `bootstrap.py`'s `git submodule update`, while
    nothing pins, digests or identifies it.

    EXACTLY, as git compares paths. A gitlink a row names in another case is
    still a finding, and says which of three it is (`_variant_case`). A
    second path to the member's own directory is taken out of the index
    alone with `git rm --cached`, which touches no file, and committed. The
    member's own gitlink, which the ROW misspells, prints no command, since
    taking it out could un-register the member. The only record of a member
    there is, in the wrong case, prints the index move members mode's
    `member-gitlink-absent` prints (`_wrong_case_move`, #648), which records
    the member at its row's path as it takes the variants out, so
    `--no-members`, the run CI falls back to when the members cannot be
    checked out, names the cure too; where the row's path is not its
    canonical one, or its pin no commit, it prints no command either. Any
    other is taken out with a plain `git rm`,
    which refuses while its checkout holds changes, then mounted with
    `family.py add`: `add` cannot adopt an existing mount, and after `git rm
    --cached` alone it refuses the checkout left in the way
    (`member-path-taken`). The removal is committed between the two (#611):
    `add` refuses a path under another spelling of `members/` that HEAD
    holds and the index no longer does (#574), which an uncommitted `git rm
    -- Members/<P>` leaves. `add` then names the object store `git rm` leaves
    in `.git/modules`, if it is still there. `--member` is quoted as the
    paths are, its project alone: `<org>` is the operator's to fill in.
    A BRANCH FIRST (#539): `add` refuses the holder's tracking branch
    (#487), so the first of the three lines is the `git switch -c` that
    makes the branch `add` suggests.

    A REMOVAL STAGED AND NOT COMMITTED (`removed`, `_staged_removals`) is
    still a gitlink HEAD records, so it is still named, and its `git rm`
    typed again failed: it says to commit the removal instead and prints
    no `git rm` (#681). A hand mount's keeps the branch and the `add`.
    """
    holds = set(gitlinks)
    for path, commit in sorted(gitlinks.items()):
        if path in named:
            continue
        said = (f"{path} is a gitlink at {commit} that no row of members: "
                "names, so a recursive clone of this holder fetches it and "
                "nothing here pins, digests or identifies it.")
        variant = _case_variant(path, named)
        if variant is not None:
            row_path, row = variant
            kind = _variant_case(path, row_path, row, holds)
            if kind == WRONG_CASE and row_path == row.canonical and row.pin:
                variants = sorted(other for other in holds
                                  if other != row_path
                                  and other.casefold() == row_path.casefold())
                report.finding(
                    "member-gitlink-unnamed",
                    f"{said}{_variant_said(row_path, row)} The member is "
                    "recorded in the wrong case. "
                    + _wrong_case_move(row_path, row.pin, variants))
                continue
            if kind != STRAY:
                report.finding(
                    "member-gitlink-unnamed",
                    said + _variant_advice(kind, path, row_path, row,
                                           "gitlink"))
                continue
            report.finding(
                "member-gitlink-unnamed",
                f"{said}{_variant_said(row_path, row)} "
                + _second_path_out(path, path in removed))
            continue
        parts = path.split("/")
        project = parts[1] if len(parts) == 2 and parts[1] else None
        report.finding(
            "member-gitlink-unnamed",
            f"{said} " + _mounted_by_hand(root, path, project,
                                          path in removed))


#: What a gitlink whose removal is staged and not committed says in place of
#: the `git rm` that would take it out, which fails there (#681).
STAGED_REMOVAL = ("HEAD records it and the index holds nothing at that "
                  "path, so its removal is staged and not committed, and no "
                  "git rm is printed, since one fails there (pathspec ... "
                  "did not match any files).")


def _second_path_out(path: str, staged: bool) -> str:
    """What a `STRAY` gitlink, a second path to a member's own directory,
    says to do: take it out of the index alone, or, where that is staged
    already (#681), commit it."""
    if staged:
        return f"{STAGED_REMOVAL} Commit that removal."
    return ("Take it out of the index alone, which touches no file, and "
            f"commit that:\n    git rm --cached -- {shlex.quote(path)}")


def _mounted_by_hand(root: Path, path: str, project: str | None,
                     staged: bool) -> str:
    """What a gitlink no row names, in no case, says to do after what it is:
    put its row back, or take a hand mount out, commit that, and mount it
    with `family.py add`, on a branch (`_check_gitlinks_named`). Where its
    removal is staged already (#681), the same with no `git rm`."""
    member = (PROJECT_PLACEHOLDER if project is None
              else shlex.quote(project))
    add = (f"    {PYTHON} scripts/family.py add --family-root "
           f"{shlex.quote(str(root))} --member <org>/{member}")
    if staged:
        return (
            f"{STAGED_REMOVAL} Commit that removal before family.py add, "
            "which refuses a path under another spelling of members/ that "
            "HEAD holds and the index no longer does, and on a branch, since "
            "family.py add refuses the holder's tracking branch: where the "
            "holder stands on it, the first command below makes one, taking "
            "the staged removal with it. If it was mounted by hand, then "
            "mount it with the second, from a checkout of "
            "openRepoShape: family.py add writes its row and its gitlink in "
            "one commit, and names the object store git rm leaves under "
            f".git/modules if one is still there. {BRANCH_LEFT}\n"
            f"    {_switch_line(root, 'add', project)}\n{add}")
    return (
        f"{RESTORE_ROW} If it was mounted by hand, make a branch "
        "with the first command below, since family.py add refuses the "
        "holder's tracking branch, take it out with the second, which "
        f"refuses while its checkout holds changes and takes its "
        f"{GITMODULES} section out too, and commit that removal, since "
        "family.py add refuses a path under another spelling of members/ "
        "that HEAD holds and the index no longer does, then mount it "
        "with the third, from a checkout of openRepoShape: family.py add "
        "writes its row and its gitlink in one commit, and names the "
        "object store git rm leaves under .git/modules if one is still "
        f"there. {BRANCH_LEFT}\n"
        f"    {_switch_line(root, 'add', project)}\n"
        f"    git rm -- {shlex.quote(path)}\n{add}")


def _check_gitmodules_named(sections: dict[str, dict[str, str]],
                            gitlinks: dict[str, str],
                            named: dict[str, RowPath], removed: frozenset[str],
                            report: Report) -> None:
    """Every path a `.gitmodules` section gives is a path some row names
    EXACTLY — the `gitmodules-path-unnamed` finding (#361).

    A section with no row is inert to a clone, which follows gitlinks, but
    it is what the next `family.py add` of its name or its path meets: under
    its own name git rewrites it in place and the member inherits every key
    it held, and under another name `add` refuses `member-path-registered`.
    It is what `family.py remove` leaves of two sections for one path
    (#360), and a section for `Members/Atlas` is one `add` commits beside
    the member's own, since git compares the two exactly: that one is still
    a finding, and says which of three it is (`_variant_case`). Only the
    section that is a second one beside the member's own is taken out. A
    section with no path gives none and is not one of these.

    The remedy is #300's, by key, every key the section holds, one command
    to a line: `--remove-section` cannot address a section whose name holds
    `]`, and a key left behind is inherited.

    A section at the path of a gitlink whose finding says to `git rm` it
    prints no command: that `git rm` takes the section out too, and a
    `--unset-all` run after it exits 5, the key being gone. A gitlink whose
    removal is staged (`removed`, #681) prints no `git rm`, so its section,
    which `git rm --cached` leaves, keeps its own commands. Where two
    sections give the path (`gitmodules-path-twice`) it takes out only the
    one git reads for it, the last in the file, so each of those keeps its
    own commands.
    """
    holds = {keys["path"] for keys in sections.values() if "path" in keys}
    given = Counter(keys["path"] for keys in sections.values()
                    if "path" in keys)
    for name, keys in sections.items():
        path = keys.get("path")
        if path is None or path in named:
            continue
        url = f"url {keys['url']}" if "url" in keys else "no url"
        said = (f'{GITMODULES} gives the path {path} to the submodule named '
                f'"{name}" ({url}), and no row of members: names that path, '
                "so nothing pins what it registers, and the next family.py "
                "add of its name or its path meets it.")
        variant = _case_variant(path, named)
        lead = "Take"
        if variant is not None:
            row_path, row = variant
            kind = _variant_case(path, row_path, row, holds)
            if kind != STRAY:
                report.finding(
                    "gitmodules-path-unnamed",
                    said + _variant_advice(kind, path, row_path, row,
                                           "section"))
                continue
            said += _variant_said(row_path, row)
        else:
            said += (" If its row was deleted or its path: edited by hand, "
                     "put the row back as git last had it.")
            lead = "Otherwise take"
            if path in gitlinks and path not in removed and given[path] == 1:
                report.finding(
                    "gitmodules-path-unnamed",
                    f"{said} Otherwise the git rm printed above for the "
                    f"gitlink at {path} takes this section out too, so no "
                    "command is printed here.")
                continue
        removal = "".join(
            f"\n    git config -f {GITMODULES} --unset-all "
            f"{shlex.quote(f'submodule.{name}.{key}')}" for key in keys)
        report.finding(
            "gitmodules-path-unnamed",
            f"{said} {lead} the section out by hand, in a POSIX shell, every "
            "key it holds, so a submodule later given its name inherits none "
            f"of them, then commit {GITMODULES}:{removal}")


def _section_lines(path: str, repository,
                   sections: dict[str, dict[str, str]]) -> str:
    """The lines that write the `.gitmodules` section of the gitlink at
    `path` as `family.py add` writes it, each on an indented line of its
    own: named after its path, with the url it gives a member,
    `https://github.com/` and the row's `repository:`, or `<url>` where that
    is not `<org>/<Name>`. A section of that name in `sections` (HEAD's)
    that has a url keeps it: only its path is written. What
    `member-gitmodules-absent` prints, and `member-gitlink-absent` (#681).
    """
    keys = {"path": shlex.quote(path)}
    if "url" not in sections.get(path, {}):
        keys["url"] = (
            shlex.quote(f"https://github.com/{repository}.git")
            if isinstance(repository, str)
            and QUALIFIED_RE.match(repository) else "<url>")
    return "".join(
        f"\n    git config -f {GITMODULES} "
        f"{shlex.quote(f'submodule.{path}.{key}')} {value}"
        for key, value in keys.items())


def _check_gitlinks_registered(root: Path, members: list,
                               gitlinks: dict[str, str],
                               report: Report) -> set[str]:
    """Every row's gitlink is at a path a section of HEAD's `.gitmodules`
    gives — the `member-gitmodules-absent` finding (#611, #407's decision
    3). Returns the paths it was made for, of which `_check_member` asks no
    checkout that is not there.

    A recursive clone checks a gitlink out only where a section gives its
    path, so a gitlink with none is left empty in every clone, by CI and by
    `make bootstrap` there, whose `git submodule update` exits 0 and checks
    nothing out. The holder the commit was made in keeps its checkout, and
    its git config the registration, so every other check here passed it:
    `family.py remove` committed a `.gitmodules` the work tree had lost
    (#407) and the gate said `family ok`.

    HEAD's file (`_head_gitmodules`), and the rows that `_check_member`
    reads at their path: one whose `path:` is not `members/<project>` is
    `member-path`'s, and one with no gitlink there is
    `member-gitlink-absent`'s (`gitlinks`, read as `recorded_gitlink` reads
    one). A holder with no members holds no gitlink and is asked nothing.
    THREE SOURCES: the gitlinks from the index first, the rows from the
    work tree's `family.yaml`, and the sections from HEAD alone, as #407's
    decision 3 has it, so a `.gitmodules` staged and not committed counts
    for nothing until it is committed (the module docstring gives the three
    cases).

    The remedy writes the section as `family.py add` writes it
    (`_section_lines`).
    """
    head = _head_gitmodules(root)
    if head is None:
        return set()
    held, sections = head
    given = {keys["path"] for keys in sections.values() if "path" in keys}
    unregistered: set[str] = set()
    for row in members:
        project = row.get("project") if isinstance(row, dict) else None
        if not isinstance(project, str) or not project:
            continue
        path = f"{DEFAULT_MEMBERS_DIR}/{project}"
        if (str(row.get("path") or path) != path or path in unregistered
                or path not in gitlinks or path in given):
            continue
        unregistered.add(path)
        lines = _section_lines(path, row.get("repository"), sections)
        report.finding(
            "member-gitmodules-absent",
            f"{path} is a gitlink at {gitlinks[path]} that a row of members: "
            "names, and "
            + (f"no section of HEAD's {GITMODULES} gives that path" if held
               else f"HEAD holds no {GITMODULES}")
            + ", so a recursive clone of this holder checks out nothing "
            "there, and neither does make bootstrap in that clone, whatever "
            "checkout this holder has of it. Write its section back by hand, "
            "in a POSIX shell, as family.py add writes one, then stage and "
            f"commit {GITMODULES}:{lines}")
    return unregistered


def _check_members(root: Path, members: list, no_members: bool,
                  report: Report) -> None:
    """Every row in `members:`, or the `--no-members` skip line.

    Split from `main` for #137. Every check that needs no member checked
    out comes first, so `--no-members` asks them too: the ones that read a
    file alone, `family.yaml`'s names (#331) and ids (#206) and the paths
    `.gitmodules` gives twice (#300), then the gitlinks and sections no row
    names, which read the index and HEAD as well (#361), and the gitlinks
    no section of HEAD's `.gitmodules` gives (#611).

    THEN EVERY ROW'S GITLINK, AND ONLY THEN ANY ROW'S CHECKOUT (#648). Each
    row used to be asked whole before the next was asked at all, so in a
    plain clone of a holder whose later row's gitlink is recorded only in
    another case, where `git submodule update --init --recursive` dies at
    that gitlink (`No url found for submodule path`, exit 128) before it
    checks out any member, an earlier row was refused
    `member-uninitialized`, naming that same update, and the later row's
    `member-gitlink-absent`, which names the move that cures both, was
    never reached.
    """
    _check_member_names_unique(members, report)
    _check_member_ids_unique(root, members, report)
    sections = _gitmodules_sections(root)
    _check_gitmodules_paths(sections, report)
    named = _row_paths(members)
    gitlinks = _member_gitlinks(root)
    removed = _staged_removals(root, gitlinks)
    _check_gitlinks_named(root, gitlinks, named, removed, report)
    _check_gitmodules_named(sections, gitlinks, named, removed, report)
    unregistered = _check_gitlinks_registered(root, members, gitlinks,
                                              report)
    if no_members:
        print(f"  --  {len(members)} member(s) SKIPPED (--no-members): "
              "their gitlinks, digests and project ids are not checked "
              "here")
        return
    seen: dict[str, bool] = {}
    gitlinked: list[Gitlinked] = []
    for row in members:
        if not isinstance(row, dict):
            report.finding("member-row",
                           f"a member is not a mapping: {row!r}")
            continue
        asked = _check_member(root, row, seen, report, gitlinks)
        if asked is not None:
            gitlinked.append(asked)
    for asked in gitlinked:
        _check_member_checkout(root, asked, report, unregistered)
    if not members:
        report.note("no members yet: a family with none is empty, not "
                    "wrong")


def _run_checks(args: argparse.Namespace, report: Report) -> tuple[dict, list]:
    """Everything `main` used to run inside its own single `try`.

    Split from `main` for #137: lifting this whole body out from under
    `main`'s `try` removes a level of nesting from every branch inside it,
    which is where most of `main`'s cognitive complexity was. Raises
    `Refusal` exactly as `main` always caught it; returns `(manifest,
    members)`, which `main` still needs afterward for the final summary line.
    """
    root = find_repo_root(args.root or Path(__file__).resolve().parents[1])
    manifest_path = root / MANIFEST
    if not manifest_path.is_file():
        raise Refusal(
            "family-manifest-missing",
            f"{manifest_path} does not exist. A family holder declares "
            f"itself in `{MANIFEST}`; a repository without one is not a "
            "family and does not run this validator.",
            f"Remediation: `{PYTHON} scripts/family.py init --org <org> "
            "--family <Name>` creates one. An ordinary project runs "
            "`validate-manifest.py` instead.")
    manifest = load_yaml(manifest_path)
    if not isinstance(manifest, dict):
        raise Refusal("family-manifest-unreadable",
                      f"{manifest_path}: not a mapping")
    policy_path = args.policy or (root / "contracts" /
                                  "repository-naming.yaml")
    policy = NamingPolicy.load(policy_path)
    if not args.pins:
        _check_envelope(manifest, policy, report)

    members = manifest.get("members")
    if members is None:
        members = []
    if not isinstance(members, list):
        raise Refusal("family-members-unreadable",
                      f"{manifest_path}: `members:` is {members!r}, "
                      "expected a list")
    _check_members(root, members, args.no_members, report)
    if not args.pins:
        _check_shape_pin(root, manifest, report)
    return manifest, members


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None,
                        help="the family root (default: the enclosing "
                             "repository)")
    parser.add_argument("--policy", type=Path, default=None)
    parser.add_argument("--pins", action="store_true",
                        help="the member lockstep check alone: gitlink, "
                             "digest and identity, with no envelope and no "
                             "shape-copy check (what `make pins` runs)")
    parser.add_argument("--no-members", action="store_true",
                        help="the envelope and the shape copies alone, "
                             "skipping every member. The complement of "
                             "--pins, and what CI runs when the members could "
                             "not be checked out: the checks that do not need "
                             "them still run, and the ones that do are "
                             "skipped out loud rather than passing on an "
                             "unreadable surface.")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    if args.pins and args.no_members:
        print("REFUSED family-nothing-to-check: --pins and --no-members are "
              "complements; together they ask for nothing.\n"
              "Remediation: pass one, or neither.", file=sys.stderr)
        return 2

    report = Report()
    try:
        manifest, members = _run_checks(args, report)
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not args.quiet:
        for note in report.notes:
            print(note)
    for finding in report.findings:
        print(finding, file=sys.stderr)
    if report.findings:
        # THE LOCKSTEP RULE ONLY WHERE IT APPLIES (#539): a lone
        # `shape-copy-drift` or `member-duplicate-id` is no gitlink moved
        # alone.
        rule = any(code in LOCKSTEP_CODES for code in report.codes)
        print(f"\n{len(report.findings)} finding(s) in {MANIFEST}."
              + (f" {LOCKSTEP}" if rule else ""), file=sys.stderr)
        return 1
    print(f"family ok: {manifest.get('name')} ({manifest.get('id')}), "
          f"{len(members)} member(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
