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
implementation of it, the holder's pinned `scripts/siblings.py`, and this
subcommand runs that file rather than a second copy of its logic (#543).

EXIT CODES: 0 done, or a `--dry-run` printed what it would do · 1 nothing to
do · 2 a refusal, and a refusal made before the first write is the same
refusal under `--dry-run`. Every subcommand takes `--dry-run`: `init`, `add`,
`bump`, `remove` and `siblings` (#326). ONE EXCEPTION, THE BRANCH (#487): a
real `add`, `bump` or `remove` refuses to commit onto the holder's tracking
branch, or onto no branch at all, as `bump-leg.py` does for a leg; a dry run
commits nothing, so it runs on any branch and says where the real run's commit
would land, or that it would refuse there and the command that makes a branch.
`siblings` exits with the holder's script's own code, unchanged. A `bump` whose
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
`init --dry-run` asks whether `<org>/<Family>` already exists, with the
question the real run asks before it creates the holder (#537): `gh repo
view` and the commit listing, or the bare repository with
`--local-remote-dir`. It refuses `family-remote-exists` as the real run does,
and makes no folder, remote or repository. Both runs ask it after whether
each folder `init` makes can be made and the holder written (#609), and
before the real run makes the family folder, so a refusal leaves none: a file
where a folder must go, or a folder this user cannot write in, is
`family-folder-cannot-be-made` or `family-target-exists`, never a traceback.
Only gh's own not-found answer says the holder does not exist; any other
`gh repo view` failure (a bad login, a rate limit, no network) is refused as
`remote-unreadable`.

`init` ASKS GITHUB'S LIMITS FIRST, WHERE GITHUB IS (#863), as the scaffold
and `adopt-project.py` ask theirs (#838), before `_creator_name` and before
any `gh` call, so `--dry-run` refuses the same. The holder's topic,
`xf-project-<family id>`, is set last, after the holder is created and pushed,
and GitHub keeps a topic to 50 characters, so a family id over 39 (which a
`--family` of 40 or more gives by default) is `family-topic-too-long`; an
`--org` over GitHub's 39 is `family-org-too-long`, one holding a character
GitHub gives no organisation (`.`), ending in a hyphen or holding two in a
row is `family-bad-org`, and a `--family` over GitHub's 100 for a
repository's name is `family-name-too-long`. Under `--local-remote-dir`
nothing goes to GitHub and none of them is asked.

WHAT ONLY THE WRITE ITSELF CAN ANSWER IS NOT ASKED. A member whose local
changes `git checkout` would refuse to overwrite gets exit 0 and a row from
`bump --dry-run`, and exit 2 from the real `bump`'s checkout; a
`.gitmodules` the index or HEAD holds and the work tree does not is
refused by the real `add`'s `git submodule add`, and its dry run exits 0 with
a note that says so (but for one a sparse checkout leaves out, below); and a
held `index.lock` is refused by the real `remove` before it unmounts anything
(#365) and not by its dry run, because a lock is a fact about the moment, not
about the holder. Each is git's own refusal or
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

`remove` AND `add` COMMIT ONLY THEIR OWN CHANGE TO `.gitmodules` (#407). Each
commits the file as git leaves it in the work tree, so the work tree's copy
must be the one the index holds. `remove` refuses, before any git command that
writes and under `--dry-run` alike, a `.gitmodules` the index or HEAD holds
and the work tree does not have: `git rm` edits only one it has, and the
commit took the file out of HEAD and every other member's section with it,
with exit 0. Both verbs refuse, as early, a work tree's copy that is not the
index's: changed and not staged, unmerged, one whose deletion is staged, an
edit the index's assume-unchanged mark hides from git, an untracked file where
neither the index nor HEAD holds one, and a file a sparse checkout leaves out:
one the index marks skip-worktree, which `add` refuses on disk or not, as `git
submodule add` cannot stage it, and `remove` where it is missing or is not the
index's copy. `add` committed such a change beside the member's section;
`remove`'s `git rm` refused some of them only after `git submodule deinit` had
emptied the member. A change somebody has STAGED is theirs and goes into the
commit, which is what the remediations of #300 and #360 rely on. `add` leaves
a `.gitmodules` the work tree lacks to `git submodule add`, which refuses it,
as said above, but for one a sparse checkout leaves out, where the restore its
dry run's note prints would not work.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

SHAPE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHAPE_ROOT / "scripts"))
from repo_shape import (  # noqa: E402
    COMMIT_RE, PROJECT_ID_RE, PYTHON, TREE_DIGEST_DEFINITION,
    VISIBILITY_CHOICES, NamingPolicy, Refusal, YamlError, checked_value,
    double_quoted, git_out, load_yaml, parse_yaml, recorded_gitlink,
    repo_basename, same_repository, tree_digest,
)
from shape_materialize import (  # noqa: E402
    FAMILY_RULESET_HINT, SHAPE_REPOSITORY, CommandFailed, check_program,
    commit_trailers, env_commit, escape_what_stdout_cannot_encode,
    force_stage, inherited_child_environment, make_folder,
    materialize_family_root, refuse_bad_branch, refuse_unless_not_found,
    refuse_unmakeable_folder, run, shown_source, stage_written,
    target_in_the_way, target_remediation, trailer_line, write_lf,
)
# What `init` asks of the holder's own reader and validator before it creates
# anything (#307), imported as its own unit and not added to the lists above.
import importlib.util  # noqa: E402
from repo_shape import YamlError, parse_yaml  # noqa: E402
from shape_materialize import (  # noqa: E402
    FAMILY_TEMPLATED, PLACEHOLDER_RE, render,
)
# How every command this prints for a person to paste spells its paths
# (#486), the quoting the holder's `scripts/siblings.py` uses too.
from repo_shape import shell_line, shell_quoted  # noqa: E402
# Whether a value `init` writes into the holder is one line of text a file
# can hold: the creator read from `git config user.name` (#426), and the
# holder's clone URL under `--local-remote-dir` (#255, #433). It is the
# question the scaffold and `adopt-project.py` ask of theirs.
from shape_materialize import unwritable_reason  # noqa: E402
# Whether `--family` names a folder a Windows disk can make (#688): the rule
# the scaffold and `adopt-project.py` hold a leg's mount path to, asked of a
# path of one segment.
from shape_materialize import _unmountable_reason  # noqa: E402
# How a refusal quotes the words git echoes of a value it refused (#688): as
# a path is quoted (#610), as it is when printable and as Python's `repr`
# spells it when it is not.
from repo_shape import shown_path  # noqa: E402
# A reused holder's own visibility and the Free-plan secrets note, asked as
# the scaffold asks them of its root (#660).
from shape_materialize import (  # noqa: E402
    free_plan_secrets_note, repository_visibility,
)
# What GitHub keeps a repository's name, a topic and an organisation's name
# to, and the characters it gives an organisation's: asked by `init` where
# GitHub is, before anything is created (#863), with the scaffold's and
# `adopt-project.py`'s own questions (#838). `_both_ends` shows a long name
# as their refusals show one.
from shape_materialize import (  # noqa: E402
    GITHUB_ID_MAX, GITHUB_NAME_MAX, GITHUB_OWNER_MAX, GITHUB_TOPIC_MAX,
    _both_ends, refuse_a_topic_github_cannot_set,
    refuse_an_owner_github_cannot_have, refuse_an_owner_github_cannot_spell,
)
# What `init`'s plan says "not found" means against GitHub, in the
# scaffold's words (#913, L2-61).
from shape_materialize import NOT_FOUND_WITH_THIS_TOKEN  # noqa: E402

NAMING_POLICY = SHAPE_ROOT / "contracts" / "repository-naming.yaml"
MANIFEST = "family.yaml"
MEMBERS_DIR = "members"
#: `add` and `remove` each list it as BOTH the gitlink path `git submodule`
#: writes and (`remove` only) an explicit `add=` path re-staged after `git rm`
#: -- named once so the two commits cannot spell the file differently.
GITMODULES = ".gitmodules"
FILE_PROTOCOL = ["-c", "protocol.file.allow=always"]
#: What `add` says when git cannot read the holder's `.gitmodules` (#370), in
#: the words the holder's own `validate-family.py` says it about the same
#: file, under the same code, `gitmodules-unreadable` (#300): both read it as
#: git does, so one fault has one name and one remedy. `repo_shape`'s
#: `git-failed` was all `add` said before, under the lockstep remedy of an
#: assembly root's legs. A SECOND SPELLING, not an import: the validator is
#: the holder's copy. ONE STEP MORE than the validator's: `add` commits the
#: file and refuses a copy nobody has staged (#407), so the mended file is
#: staged, `git add .gitmodules`, before the run again, where the gate reads
#: the work tree's copy and needs no stage.
#: `tests/test_refusal_default_remediation.py` runs both over one file and
#: fails when they differ in anything else.
GITMODULES_UNREADABLE = (
    "Remediation: git cannot read it either, so none of this holder's "
    "submodules can be cloned from it as it stands. Mend the file by hand "
    f"(`git config -f {GITMODULES} --list` says where it breaks), then `git "
    f"add {GITMODULES}` and run this again.")

#: What `git symbolic-ref HEAD` prints before a branch's name: the one
#: spelling `_holder_branch` and `_member_head` strip to read a HEAD back as
#: the branch it is on, named once so the two cannot differ.
HEADS_PREFIX = "refs/heads/"

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
        try:
            data = load_yaml(path)
        except Refusal as exc:
            # A MERGE CONFLICTED IN `family.yaml` ITSELF, the commonest one
            # in a holder, is named as the act it is (#684, #612's review
            # N4), asked ONLY HERE, once the parse has failed: asked before
            # it, git would run ahead of the refusal of a hand-edited
            # `path:`, which runs no git command at all.
            if exc.code == "yaml-unparsable" and not exc.remediation:
                exc.remediation = _unparsable_in_an_act(root)
            raise
        if not isinstance(data, dict):
            raise Refusal("family-unreadable", f"{path}: not a mapping")
        if data.get("kind") != "family-manifest":
            raise Refusal(
                "family-wrong-kind",
                f"{path}: kind is {data.get('kind')!r}, expected "
                "'family-manifest'")
        _checked_members_readable(path, data.get("members"))
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

        THE FIX BY HAND IS COMMITTED before the run again (#684): the verbs
        refuse a `family.yaml` holding a change HEAD does not
        (`_checked_manifest_committed`), and this refusal is only reached
        once the shape it names is committed.
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
                "hand this once and commit that (`git commit -- "
                f"{MANIFEST}`), then run the same command again.")
        return "\n".join(out) + "\n"


#: What `add`, `bump` and `remove` say under `family-members-unreadable`.
MEMBERS_UNREADABLE = (
    "Remediation: `members:` is the list of rows `family.py add` writes, one "
    "mapping per member, and this tool rewrites no `members:` it cannot read. "
    "The holder's own `scripts/validate-family.py` names this same fault: "
    f"mend `{MANIFEST}` by hand, commit it (`git commit -- {MANIFEST}`), then "
    "run the same command again.")


def _checked_members_readable(path: Path, members) -> None:
    """Refuse a `members:` that is not a list, or that holds an entry that
    is not a mapping, in the words of the holder's own `validate-family.py`
    (#864): its `family-members-unreadable` refusal for the first, its
    `member-row` finding for the second, the value spelled as it spells it.

    ONCE, IN `Family.open`, so every verb stops here, before it fetches,
    mounts or rewrites anything, the dry runs alike. Each verb read the rows
    as `members or []`: `members: 5` ended `add`, `bump` and `remove` in a
    `TypeError`, `openXdox` or `[5]` was a family with no members, so a
    member mounted there was `member-unknown`, and in a list of rows and a
    `5` the rows were read and the `5` dropped, so all three exited 0 and
    committed a `family.yaml` without it. A `members:` this tool cannot read
    is never one it rewrites. Absent or null is no members, as the gate
    reads it, and is left to the verbs.
    """
    if members is None:
        return
    if not isinstance(members, list):
        raise Refusal("family-members-unreadable",
                      f"{path}: `members:` is {members!r}, expected a list",
                      MEMBERS_UNREADABLE)
    unread = [f"a member is not a mapping: {row!r}" for row in members
              if not isinstance(row, dict)]
    if unread:
        raise Refusal("family-members-unreadable",
                      f"{path}: {'; '.join(unread)}", MEMBERS_UNREADABLE)


def _member_id(value) -> str:
    """A row's `id:` as `_member_lines` spells it: bare where the holder's
    reader takes the bare text back as that same text, and between double
    quotes where it does not (#259).

    THE MEMBER'S OWN `project.yaml` QUOTES ITS ID NOW. A project scaffolded
    with `--id 007` used to write `id: 007`, which every reader took as the
    number 7; this row then recorded `str(7)`, and the two agreed on a
    misread. The template writes `id: "007"` since #259, so the id read here
    is `007`, and written bare it would come back as 7: `validate-family.py`
    would report `member-id-mismatch` for a member it had just pinned, and so
    would `2026`, `20261011`, `true` and `null`. The reader is asked, not a
    list of the words it treats as something else, so a word it learns later
    is quoted with no edit here. An id that reads back bare, which is every
    ordinary one, is written as it always was, so a row whose id reads back
    as text does not move.

    A ROW WHOSE BARE ID THE READER MISREADS MOVES, ONCE. A holder written
    before #259 holds `id: 2026` for a member scaffolded with `--id 2026`,
    and the next `bump`, `add` or `remove` of that holder rewrites the row as
    `id: "2026"`. That is harmless: `validate-family.py` compares the id with
    `str()`, and passes before and after.
    """
    text = str(value)
    try:
        if parse_yaml(f"id: {text}\n") == {"id": text}:
            return text
    except YamlError:
        # Bare, `[`, `{`, `&a`, `*a`, `!t` and an unclosed quote are not read
        # as another type: the reader raises, and the holder would not load.
        pass
    return double_quoted(text)


def _member_lines(row: dict) -> list[str]:
    """One member as the YAML subset `repo_shape.parse_yaml` reads back."""
    pin = row.get("pin") or {}
    return [
        f"  - project: {row['project']}",
        f"    id: {_member_id(row['id'])}",
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

    A ROW PUT BACK BY HAND IS COMMITTED before the run again (#684): the
    verbs refuse a `family.yaml` holding a change HEAD does not
    (`_checked_manifest_committed`), so a row put back over an edit already
    committed would be refused next, for want of that commit.
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
            f"(`project: <Project>`, `path: {MEMBERS_DIR}/<Project>`) and "
            "commit that, then run the command again naming that member.")
    declared = expected if row is None else str(row.get("path") or expected)
    if declared != expected:
        raise Refusal(
            "member-path",
            f"{project}: path is {declared!r} in {MANIFEST}, expected "
            f"{expected!r}. Git would read that value as a pathspec, so no "
            "git command was run and nothing was written.",
            "Remediation: this tool writes that field itself, so a different "
            f"value is a hand edit. Put `path: {expected}` back in "
            f"{MANIFEST} and commit that, or `git checkout -- {MANIFEST}` if "
            "the edit is not committed, then run the same command again.")
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


#: The rule a `--family` is held to, as `naming-unclassified` states it
#: (`_classify_family_name`). `family-bad-id`'s derived remedy names it in
#: the same words, so the person who follows it is not sent from one
#: refusal to the other (#659).
FAMILY_NAME_RULE = ("one CamelCase token with no hyphen, underscore, dot "
                    "or space")


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
            f"Remediation: --family takes {FAMILY_NAME_RULE} — the same rule "
            "an assembly root's name follows, because a holder is spelled "
            "like one.")
    if found.family != "family":
        raise Refusal(
            "naming-not-a-family",
            f"{name!r} classifies as {found.family}"
            + (f"/{found.role}" if found.role else "")
            + f", not as a family holder ({found.reason})",
            "Remediation: --family takes one CamelCase token. An "
            "`open<Product>` or `<X>-Install` name is unambiguous by "
            "construction and cannot be declared into a holder.")


#: What `family-bad-holder-name` is told to do (#688).
HOLDER_NAME_REMEDIATION = (
    "Remediation: nothing was created, and `--dry-run` refuses the same. "
    "Choose another --family. It names the holder, its repository and the "
    "folder it is cloned into and, unless --work-dir is given, the family "
    "folder around it, which `make siblings` looks for by that very name; "
    "and a holder is cloned on Windows too, where no file or folder can be "
    "called a device name (`CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9`, "
    "`LPT1`-`LPT9`, in any case, with or without an extension), and a name "
    "ending in a dot or a space is made under another name. There is no "
    "--force.")


def _refuse_an_unholdable_holder_name(family: str) -> None:
    """`--family` names a folder a Windows disk can make, or this refuses
    as `family-bad-holder-name` (#688), before anything exists and under
    `--dry-run` alike.

    `init` makes the holder at `<into>/<Family>/<Family>` (`--work-dir`:
    `<dir>/<Family>`), its bare repository under `--local-remote-dir` is
    `<Family>.git`, and `make siblings` goes on only in a family folder named
    exactly `--family` (#543). `CON`, `Nul`, `com1` and the other device
    names are each one CamelCase token, which is all the naming policy asks,
    so `init` made and pushed a holder that no Windows disk could clone: it
    can make no file or folder of that name, with or without an extension.

    THE QUESTION IS THE LEG PATH RULE'S (`_unmountable_reason`), the one the
    scaffold and `adopt-project.py` ask of a leg's mount path, asked of a
    path of one segment, in its own words. It is asked after
    `_classify_family_name` on purpose: the policy's token holds no `.`, no
    `~` and no space, so a device name is the only answer the rule can give
    here, and the names it also refuses (a trailing dot or space, `.git`,
    `git~1`, `.gitmodules`) are refused before it, as `unsafe-value`,
    `family-bad-id` or `naming-unclassified`, as they always were.
    """
    reason = _unmountable_reason(family)
    if reason:
        raise Refusal(
            "family-bad-holder-name",
            f"--family is {family!r}, which names the holder and the folders "
            f"`init` makes for it, and {reason}.",
            HOLDER_NAME_REMEDIATION)


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


# ---------------------------------------------------------------------------
# The branch an act commits on (#487)
# ---------------------------------------------------------------------------
#
# AGENTS.md says each of `add`, `bump` and `remove` writes ONE commit, to land
# as a pull request, never as a push to the default branch. Nothing made the
# branch that pull request needs: after `init` the holder stands on its
# tracking branch, and all three committed straight onto it, while `add`
# printed `git -C <holder> push -u origin <branch>`, a placeholder no
# repository has (`src refspec ... does not match any`), and `bump` and
# `remove` printed no NEXT at all. `bump-leg.py` refuses exactly this for a
# leg (`bump-leg-on-tracking-branch`). So the real run of each refuses the
# tracking branch and a HEAD on no branch, before it reads the member or
# writes anything, with the `git switch -c` that makes a branch; and each
# act that commits ends with ONE pasteable line that pushes the branch it
# committed on.


def _holder_branch(root: Path) -> str | None:
    """The branch the holder's HEAD is on, or None: detached, or a HEAD
    that names something other than a branch.

    READ AS THE BYTES GIT WROTE (#765). Exactly one newline and exactly
    `refs/heads/` come off the bytes, and the rest is decoded with
    `surrogateescape`. `strip()` also took a trailing U+00A0, U+2028 or
    U+0085, which a branch name may end in: a holder on `feat<U+00A0>` was
    read as `feat`, a branch of its own, and the NEXT line pushed that one
    and not the commit the act made. A NAME THAT IS NOT UTF-8 IS REFUSED
    here, `family-branch-not-utf8`: no line this tool prints can spell it,
    and a push line naming another branch is worse than none. The real run
    of each act asks this before it reads the member or writes anything,
    and its dry run at the line that would name the branch."""
    try:
        ref = _git_bytes(["symbolic-ref", "-q", "HEAD"], root)
    except CommandFailed:
        return None
    ref = ref[:-1] if ref.endswith(b"\n") else ref
    heads = HEADS_PREFIX.encode("ascii")
    if not ref.startswith(heads):
        return None
    raw = ref[len(heads):]
    branch = raw.decode("utf-8", "surrogateescape")
    try:
        branch.encode("utf-8")
    except UnicodeEncodeError:
        # NAMED BY ITS BYTES, `b'caf<0xE9>'`, as `trailer-not-utf8` names a
        # trailer, and THE HOLDER as `shown_path` names a path, as
        # `_checked_branch`'s other refusals name it (#766). The remedy is
        # quoted for a POSIX shell, as bump-leg's and update-shape's are, so
        # README's sentence on the lines quoted for PowerShell stays true;
        # a command to paste, it holds the holder's path raw inside its
        # quotes, as their `switch -c` does (#459).
        raise Refusal(
            "family-branch-not-utf8",
            f"{shown_path(root)} is on the branch {raw!r}, whose name is not "
            "UTF-8, so no line this tool prints can name it: the NEXT line "
            "would push a branch that is not there. Nothing was committed, "
            "and the holder's work tree and index are as they were.",
            "Remediation: give the branch a name that is UTF-8 text, then "
            "run the same command again:\n    "
            + shell_line(["git", "-C", root, "branch", "-m"], "posix")
            + " <a new name>") from None
    return branch


#: A branch-name component the suggestion may use as it stands: dot-separated
#: words of lowercase letters, digits, `_` and `-`, which no git rule refuses
#: but a trailing `.lock`, which is checked beside it.
BRANCH_WORD_RE = re.compile(r"[a-z0-9][a-z0-9_-]*(?:\.[a-z0-9_-]+)*")


def _suggested_branch(verb: str, name: str, commit: str | None = None) -> str:
    """The branch a refusal suggests for one act (#487): `family/<verb>-
    <member>`, with the commit's first twelve for `bump`, as `bump-leg.py`
    suggests `bump/<leg>-<sha12>`. The member is its row's `id:` (`bump`,
    `remove`), or its name lowercased (`add`, which has not read the member
    yet); one that is not a plain branch word is said as `member`."""
    word = name.lower()
    if not BRANCH_WORD_RE.fullmatch(word) or word.endswith(".lock"):
        word = "member"
    return f"family/{verb}-{word}" + (f"-{commit[:12]}" if commit else "")


def _switch_command(root: Path, branch: str) -> str:
    """`git -C <holder> switch -c <branch>`, every word spelled by
    `shell_quoted` for the reader's shell (#486)."""
    return shell_line(["git", "-C", root, "switch", "-c", branch])


#: What every remedy that names `_switch_command` says next (#607): where an
#: earlier act left that branch, `switch -c` fails `fatal: a branch named
#: '<branch>' already exists` (exit 128). ANOTHER NAME COMES FIRST, because a
#: new branch starts where the holder stands now, which works in every
#: state. Going back to the old branch is right only where it holds work not
#: merged yet: one left behind a main that has moved on makes the act collide
#: with what main took in since, or find its member already there, and a
#: commit made on a detached HEAD is left behind by any `git switch <branch>`.
#: `git switch` keeps the branch's commits and refuses to overwrite a changed
#: file; nothing here names `switch -C`, which resets the branch.
#: IN WORDS, NOT A SECOND COMMAND: no one line works in both states in every
#: shell this file quotes for (PowerShell 5.1 has no `||`), and README lists
#: the kinds of line printed for PowerShell. The holder's
#: `validate-family.py` says the same words.
BRANCH_LEFT = ("If `git switch -c` says that branch already exists, an "
               "earlier act left it: give the branch another name, which "
               "starts it where the holder stands, or, only if that branch "
               "holds work not merged yet, the same command with `switch` "
               "in place of `switch -c` goes back to it and keeps every "
               "commit on it.")


def _checked_branch(family: "Family", verb: str, suggested: str) -> str:
    """The branch `verb`'s ONE commit lands on: the one the holder stands
    on, refused when that is the holder's tracking branch or there is none
    (#487). Asked by the real run, after the refusals about the arguments
    and the holder and before the member is read or anything is written;
    `--dry-run` asks `_branch_said` instead. The remedy's `switch -c` is
    followed by `BRANCH_LEFT`, for a holder that has the branch (#607).

    THE HOLDER IS NAMED AS `shown_path` NAMES A PATH (#766), as #692 names
    the folders `init` makes: a holder whose path held an ESC sent it to the
    terminal, and one with a line break began a line of its own choosing.
    A printable path is named byte for byte. The remedy's `switch -c` is
    a command to paste, and still holds the holder's path raw inside its
    shell quotes (#459)."""
    branch = _holder_branch(family.root)
    if branch is not None and branch != family.tracking():
        return branch
    remedy = ("Remediation: these organisations are pull-request only, so "
              "make a branch for the change and run the same command "
              f"again:\n    {_switch_command(family.root, suggested)}\n"
              f"{BRANCH_LEFT}\nThen push that branch and open a pull "
              "request, as the NEXT line the command ends with says. "
              "`--dry-run` runs on any branch.")
    if branch is None:
        raise Refusal(
            "family-holder-detached",
            f"{shown_path(family.root)} is not on a branch, so `{verb}` "
            "would write a commit no branch holds, with nothing to push and "
            "open a pull request from. No git command that writes was run "
            "and nothing was written.", remedy)
    raise Refusal(
        "family-on-tracking-branch",
        f"{shown_path(family.root)} is on {branch!r}, which {MANIFEST} "
        "declares as the holder's tracking branch, and "
        f"`{verb}` will not write a commit whose only next step is a push to "
        "the default branch. No git command that writes was run and nothing "
        "was written.", remedy)


def _branch_said(family: "Family", verb: str, suggested: str) -> list[str]:
    """The `branch` line a dry run prints (#487): where the real run's
    commit lands, or that the real run refuses here, by its code, and the
    command that makes a branch, on a line of its own, then `BRANCH_LEFT`
    as the real run's remedy says it (#607)."""
    branch = _holder_branch(family.root)
    tracking = family.tracking()
    if branch is not None and branch != tracking:
        return [f"branch       {branch}: the commit lands there, for a pull "
                f"request against {tracking}"]
    code, where = (("family-holder-detached", "the holder is on no branch")
                   if branch is None else
                   ("family-on-tracking-branch",
                    f"{branch} is the holder's tracking branch"))
    return [f"branch       {where}, where a real {verb} refuses ({code}); "
            "make a branch first:",
            f"             {_switch_command(family.root, suggested)}",
            f"             {BRANCH_LEFT}"]


# ---------------------------------------------------------------------------
# What the holder is in the middle of, and what its sparse checkout leaves out
# ---------------------------------------------------------------------------
#
# `add`, `bump` and `remove` each end in ONE `git commit -- <paths>`
# (`_commit_one`), made after the verb's first writes and put back by its
# rollback if it fails. An act git has unfinished in the holder, and a path
# its sparse checkout leaves out, make that commit fail or land in the wrong
# place EVERY time, so each verb did its writes and undid them, or committed
# where nobody wanted it: refusals made at the wrong end (#612, from #459's
# 571(e), 571(d) and 574/5; the third of 574/5, a `members` that is a file,
# is `_members_is_a_file`, beside the mount path's other refusals). Each is
# asked once, before the first write and under `--dry-run` alike, so the two
# runs refuse in the same words.

#: What git keeps in its directory while an act is unfinished, in the order
#: `_operation_in_progress` asks it: `(the name git keeps, what it is, how a
#: person finishes it, how a person gives it up, what `git commit --
#: <paths>` does during it)`, the last with `{verb}` for the verb that
#: asked. A REBASE IS ASKED FIRST: it holds a HEAD detached on the commit it
#: stopped at, it may hold a merge, a cherry-pick or a revert of its own
#: beside its mark (a merge begun at a rebase's `edit` stop leaves both
#: `MERGE_HEAD` and `rebase-merge/`), and `git rebase --abort` puts all of it
#: back, where `git merge --abort` would leave `rebase-merge/` and a second
#: refusal. What git does with the partial commit was measured on git 2.43 in
#: each state: it REFUSES one during a merge and a cherry-pick and MAKES it
#: during a revert, a rebase and a `git am`.
REBASE_EFFECT = (
    "git does not refuse that during a rebase: the commit would land on the "
    "HEAD the rebase has detached, in the middle of its sequence, where "
    "`git rebase --continue` replays the rest on top of it into the rebased "
    "branch and `git rebase --abort` drops it")
#: A BISECT, ASKED LAST (#684, #612's review E2). git keeps `BISECT_LOG` from
#: `git bisect start` to `git bisect reset`, and once the bisect checks out a
#: commit to test, HEAD is detached there: the real run met it as
#: `family-holder-detached`, whose `git switch -c` would branch from the
#: commit under test, and the dry run printed a plan. git does not refuse the
#: partial commit there, and `git bisect reset` leaves it behind (`you are
#: leaving 1 commit behind`, measured on git 2.43). Its exit is `git bisect
#: reset`, and nothing finishes it by hand. Asked after the others: a merge
#: or a cherry-pick begun at the commit under test leaves its own mark beside
#: `BISECT_LOG`, and `git bisect reset` cannot check a branch out over the
#: conflict it stopped on (`you need to resolve your current index first`,
#: exit 1, measured), so that act is named, and ended, first.
BISECT_EFFECT = (
    "git does not refuse that during a bisect: once the bisect has checked "
    "out a commit to test, the commit would be made on it, on no branch, "
    "and `git bisect reset` would leave it behind")
OPERATION_MARKS = (
    ("rebase-merge", "a rebase", "git rebase --continue",
     "git rebase --abort", REBASE_EFFECT),
    ("rebase-apply", "a rebase", "git rebase --continue",
     "git rebase --abort", REBASE_EFFECT),
    ("MERGE_HEAD", "a merge", "git commit", "git merge --abort",
     "git refuses that during a merge (`fatal: cannot do a partial commit "
     "during a merge.`), after `{verb}`'s first writes, which are then put "
     "back"),
    ("CHERRY_PICK_HEAD", "a cherry-pick", "git cherry-pick --continue",
     "git cherry-pick --abort",
     "git refuses that during a cherry-pick (`fatal: cannot do a partial "
     "commit during a cherry-pick.`), after `{verb}`'s first writes, which "
     "are then put back"),
    ("REVERT_HEAD", "a revert", "git revert --continue",
     "git revert --abort",
     "git does not refuse that during a revert: the commit is made on the "
     "branch as `{verb}`'s own, and git takes it as the end of the revert, "
     "so `git revert --continue` and `--abort` then say `no cherry-pick or "
     "revert in progress` and the revert's changes are left half done in "
     "the index and the work tree"),
    ("BISECT_LOG", "a bisect", None, "git bisect reset", BISECT_EFFECT),
)

#: `git am` keeps its state in `rebase-apply` too, and git tells it from a
#: rebase by the file `applying` there (`wt_status_check_rebase`): so that
#: its exit is `git am --abort`, which `git rebase --abort` is not. Its HEAD
#: stays on the branch, so the partial commit lands there.
AM_MARK = "rebase-apply/applying"
AM_OPERATION = ("a `git am`", "git am --continue", "git am --abort",
                "git does not refuse that during a `git am`, so the commit "
                "would land on the branch, in the middle of the patches "
                "being applied")

#: A cherry-pick or a revert of SEVERAL commits keeps `sequencer/` for the
#: steps still to take, and once its stopped step is committed by hand
#: neither `CHERRY_PICK_HEAD` nor `REVERT_HEAD` is left, though `git status`
#: still says `Cherry-pick currently in progress.` (#612's review, F2). It
#: is named from the first word of `sequencer/todo`, as `git status` names
#: it: `pick` or `p`, a cherry-pick; `revert`, a revert.
SEQUENCER = "sequencer"
SEQUENCER_TODO = "sequencer/todo"
CHERRY_PICK = "git cherry-pick"
SEQUENCE_COMMANDS = {"pick": CHERRY_PICK, "p": CHERRY_PICK,
                     "revert": "git revert"}

#: A `sequencer/` whose `todo` is missing, empty or not a series git reads.
#: Measured on git 2.43: `git status` says nothing is in progress,
#: `--continue` fails (`fatal: cherry-pick failed`, exit 128), and `--abort`
#: and `--quit` of either command exit 0 and take the directory away. So it
#: is named for what it is and has no `finish`.
SEQUENCE_UNREADABLE = (
    "a cherry-pick or revert series", None, "git cherry-pick --abort",
    "git does not refuse that, and the commit would land beside a "
    "`sequencer/` directory git can read no series from, which `--continue` "
    "fails on")

#: A REBASE GIT CAN READ NOTHING OF (#684, #612's review E5 and N5): a
#: `rebase-merge/` or `rebase-apply/` that holds no `head-name`, as a stale,
#: empty one does. `git status` still says `You are currently rebasing.`,
#: but `git rebase --continue` and `git rebase --abort` both fail there
#: (`could not read '.git/rebase-merge/head-name'`, exit 1), and `git rebase
#: --quit` takes the directory away and moves nothing (exit 0); measured on
#: git 2.43 in both. A real rebase writes `head-name` when it starts, and
#: `git am`, which writes none, is told apart by `applying` first. So it is
#: named as the sequencer's unreadable twin is: no `finish`, and `--quit`.
REBASE_HEAD_NAMES = {"rebase-merge": "rebase-merge/head-name",
                     "rebase-apply": "rebase-apply/head-name"}

#: THE TWO MARKS A REFTABLE KEEPS AS REFS (#684, #612's review E4). A holder
#: whose refs are a reftable (`git init --ref-format=reftable`, git 2.45 and
#: later) keeps `CHERRY_PICK_HEAD` and `REVERT_HEAD` in its ref store while
#: a cherry-pick or a revert is stopped, and in no file; `MERGE_HEAD`,
#: `rebase-merge/` and `sequencer/todo` stay files there (lane 5's probe, on
#: git 2.47.1). The file check found neither, so the verb went on to the
#: commit this check is there to keep it from. Each is asked of the ref store
#: in its own row of `OPERATION_MARKS`, where its file is not there
#: (`_in_ref_store`), and the refusal says git keeps it `IN_THE_REF_STORE`.
#: `MERGE_HEAD` is asked as a file alone, because it is a file on both
#: backends: a stopped merge leaves `MERGE_HEAD` a file on a reftable too
#: (lane 5's probe, git 2.47.1), and git reads `MERGE_HEAD` and `FETCH_HEAD`
#: from their files whatever the backend (`is_pseudo_ref`, git 2.47.1's
#: `refs.c`), so the file is the whole answer. Asking the ref store for it
#: would also stop the verbs on git 2.43, which answers `git show-ref
#: --exists MERGE_HEAD` 1, `failed to look up reference: Success`, where no
#: merge is in progress (measured; git 2.47.1 answers 2 there).
REF_STORE_MARKS = ("CHERRY_PICK_HEAD", "REVERT_HEAD")
IN_THE_REF_STORE = "in its ref store, not as a file"
#: How `git show-ref --exists <name>` (git 2.43 and later) answers where the
#: ref store holds no ref of that exact name: 2, `error: reference does not
#: exist`; 0 where it holds one (both measured on git 2.43, for each mark,
#: with a cherry-pick stopped, a revert stopped and neither). A git before
#: 2.43 knows no `--exists` and exits 129, `error: unknown option `exists'`
#: (measured on git 2.40.4).
SHOW_REF_MISSING = 2
GIT_UNKNOWN_OPTION = 129


def _rebase_unreadable(mark: str) -> tuple:
    """`(finish, abort, effect)` for a `mark` directory that holds no
    `head-name` (`REBASE_HEAD_NAMES`); what it is, a rebase, is its row's in
    `OPERATION_MARKS`."""
    return (None, "git rebase --quit",
            "git does not refuse that, and the commit would land beside a "
            f"`{mark}/` directory that holds no `head-name`, so git can read "
            "no rebase from it and `git rebase --continue` and `--abort` both "
            "fail there")


def _git_paths(root: Path, names: list[str]) -> list[Path]:
    """Where git keeps each of `names` for the holder at `root`, ASKED OF GIT
    in ONE `git rev-parse --git-path <a> --git-path <b> ...` (one line per
    name; a process per name matters on Windows), never `.git/<name>`: in a
    linked worktree, which is where a lane opens its pull request, `.git` is
    a file and the per-worktree state (`MERGE_HEAD`, `rebase-merge/`,
    `index.lock`) is under `.git/worktrees/<name>/` (#365, `_module_dir`,
    `_checked_index_unlocked`). git answers relative to `root` or absolute,
    and `root /` takes both. A holder whose path holds a newline (a linked
    worktree's answer is absolute, through the holder's own `.git`) would make
    the lines and the names disagree: each name is then asked alone, and its
    WHOLE answer less git's final newline is the path, never its first line
    (#612's verification, V-F1: a path cut at its newline named nothing, and
    a merge in that worktree was missed, which is #612's own defect)."""
    def asked(*words: str) -> str:
        shown = _git_bytes(["rev-parse", *words], root).decode(
            "utf-8", "surrogateescape")
        return shown[:-1] if shown.endswith("\n") else shown

    lines = asked(*[word for name in names
                    for word in ("--git-path", name)]).split("\n")
    if len(lines) != len(names):
        lines = [asked("--git-path", name) for name in names]
    return [root / line for line in lines]


def _in_ref_store(root: Path, mark: str) -> bool:
    """Whether the holder's ref store holds a ref called EXACTLY `mark`
    (`REF_STORE_MARKS`, #684), asked with `git show-ref --exists <mark>`, one
    process per mark, since `--exists` takes one name.

    THE EXACT NAME. `git rev-parse -q --verify CHERRY_PICK_HEAD`, which the
    issue named, also resolves a branch or a tag of that name, and no
    operation leaves either: measured on git 2.43 with `git branch
    CHERRY_PICK_HEAD` and `git tag REVERT_HEAD`, it answers each with the
    commit, and `show-ref --exists` answers 2 for both.

    GIT'S OWN FAILURE IS NEVER "NOTHING IN PROGRESS". Only 0 is "held" and
    only 2 "not held"; any other exit is a `CommandFailed`, which the verb
    prints as it prints every failed git command, exit 2, before its first
    write. The one other exit read as "not held" is 129, from a git before
    2.43, which knows no `--exists`: such a git cannot open a reftable at
    all (`unknown repository extension found: refstorage`, exit 128 at the
    `git rev-parse` `_git_paths` asks first, measured on git 2.43 and 2.40.4
    with the extension set by hand), so a holder it gets this far in keeps
    its refs as files, and the file asked first is the whole answer.
    """
    try:
        _git_bytes(["show-ref", "--exists", mark], root)
    except CommandFailed as exc:
        if exc.code in (SHOW_REF_MISSING, GIT_UNKNOWN_OPTION):
            return False
        raise
    return True


def _sequence_act(todo: Path) -> tuple:
    """`(what, finish, abort, effect)` for the series `todo` holds, named from
    its first word as `git status` names it, or `SEQUENCE_UNREADABLE`."""
    try:
        first = todo.read_bytes().split(b"\n", 1)[0].split(None, 1)
    except OSError:
        first = []
    command = SEQUENCE_COMMANDS.get(
        first[0].decode("utf-8", "replace") if first else "")
    if command is None:
        return SEQUENCE_UNREADABLE
    what = "a cherry-pick" if command == CHERRY_PICK else "a revert"
    return (f"{what} series", f"{command} --continue", f"{command} --abort",
            "git does not refuse that between the steps of a series, so the "
            f"commit would land in the middle of it: `{command} --continue` "
            f"replays the rest on top of it, and `{command} --abort` stops "
            "and leaves it where it is (`You seem to have moved HEAD. Not "
            "rewinding`)")


def _operation_in_progress(
        root: Path,
) -> tuple[str, str, Path | None, str | None, str, str] | None:
    """`(what, the mark's name, where it is, how to finish it, how to give it
    up, what the partial commit would do)` for the act the holder's git
    directory shows unfinished, or None; the first of `OPERATION_MARKS`
    that is there, then a `sequencer/`. `finish` is None where git can
    continue nothing. `where` is None for a mark the holder's ref store holds
    and no file does (`REF_STORE_MARKS`, #684): the ref store is asked in the
    mark's own row, once its file is not there, so the rows keep their
    order and a mark that is a file is named at its path, as before."""
    names = [*(mark for mark, *_ in OPERATION_MARKS), AM_MARK, SEQUENCER,
             SEQUENCER_TODO, *REBASE_HEAD_NAMES.values()]
    marks = dict(zip(names, _git_paths(root, names)))
    for mark, what, finish, abort, effect in OPERATION_MARKS:
        where = marks[mark]
        if not os.path.lexists(where):
            if mark in REF_STORE_MARKS and _in_ref_store(root, mark):
                return what, mark, None, finish, abort, effect
            continue
        if mark == "rebase-apply" and os.path.lexists(marks[AM_MARK]):
            what, finish, abort, effect = AM_OPERATION
        elif mark in REBASE_HEAD_NAMES and not os.path.lexists(
                marks[REBASE_HEAD_NAMES[mark]]):
            finish, abort, effect = _rebase_unreadable(mark)
        return what, mark, where, finish, abort, effect
    if os.path.lexists(marks[SEQUENCER]):
        what, finish, abort, effect = _sequence_act(marks[SEQUENCER_TODO])
        return what, SEQUENCER, marks[SEQUENCER], finish, abort, effect
    return None


#: What the remedy says of an act git can continue nothing of (`finish` is
#: None), by the mark found, with `{mark}` and `{abort}` filled in: each
#: names only the exit that works there (#684).
REBASE_UNREADABLE_EXIT = (
    "`{mark}/` is what a rebase left behind, and it holds no `head-name`, so "
    "git can read no rebase from it and there is nothing to continue or give "
    "up: clear it without moving HEAD with `{abort}`.")
UNFINISHABLE = {
    SEQUENCER: ("`sequencer/` is what a cherry-pick or revert series left "
                "behind, and git can read no step from it, so there is "
                "nothing to continue: give it up with `{abort}` (`git revert "
                "--abort` is the same), or clear it without moving HEAD with "
                "`git cherry-pick --quit`."),
    "rebase-merge": REBASE_UNREADABLE_EXIT,
    "rebase-apply": REBASE_UNREADABLE_EXIT,
    "BISECT_LOG": ("end the bisect with `{abort}` once you have what it was "
                   "for: it takes HEAD back to where the bisect started."),
}


def _operation_exit(found: tuple) -> str:
    """What a person does about the act `_operation_in_progress` found: its
    own exit, and only what works there, then `Then run the same command
    again.` The remediation of `family-operation-in-progress`, and of a
    `family.yaml` an act left unparsable (`_unparsable_in_an_act`, #684), in
    the same words."""
    _, mark, _, finish, abort, _ = found
    if finish is None:
        said = UNFINISHABLE[mark].format(mark=mark, abort=abort)
    else:
        said = ("end it, whichever way suits the work in it: finish it with "
                f"`{finish}` once whatever stopped it is resolved and staged, "
                f"or give it up with `{abort}`.")
    return f"{said} Then run the same command again."


def _checked_no_operation_in_progress(root: Path, verb: str) -> None:
    """`family-operation-in-progress`: `verb` refuses, before its first
    write and under `--dry-run` alike, a holder with a merge, a cherry-pick,
    a revert, a rebase, a `git am` or a bisect unfinished in it (#612,
    571(e); the bisect, #684).

    THE COMMIT GOES WRONG, AFTER THE WRITES. `add`, `bump` and `remove`
    commit with `git commit -- <paths>` (`_commit_one`). git refuses a
    partial commit while a merge or a cherry-pick is unfinished (`fatal:
    cannot do a partial commit during a merge.`), and by then `add` had
    mounted the member, `bump` had checked it out at `--to` and `remove` had
    unmounted it; the rollback put each back (#203, #365) and the person got
    exit 2, with the work done and undone for nothing. The commonest source
    is `git merge`, which is also where #571's `--ours` and `--theirs`
    restores come from: the same state, one step earlier. A merge that
    stopped with `--no-commit` has no conflict at all and fails the same.

    A REVERT, A REBASE AND A `git am` ARE NOT REFUSED BY git, which is
    worse (measured on git 2.43, each stopped on a conflict). The partial
    commit is made: in a revert, on the branch as the verb's own, and git
    takes it as the END of the revert (`REVERT_HEAD` goes, `--continue` and
    `--abort` then say `no cherry-pick or revert in progress`, and the
    revert's changes are left half done in the index and the work tree); on
    the HEAD a rebase has detached, in the middle of its sequence, where
    `git rebase --continue` replays the rest on top of it into the rebased
    branch and `--abort` drops it; and on the branch in the middle of an
    `am`. The real run met a rebase at the branch refusal
    (`family-holder-detached`, #487), which committed nothing but whose
    remedy, `git switch -c`, is the wrong advice in the middle of a rebase,
    and the dry run printed a plan for it. This check comes before that one,
    so a rebase is named as what it is.

    A SERIES IS ASKED TOO (#612's review, F2). `git cherry-pick A..B` and
    `git revert A..B` keep `sequencer/` for the steps to come; once a
    stopped step is committed by hand no `CHERRY_PICK_HEAD` or `REVERT_HEAD`
    is left, yet `git status` still says the act is in progress, and the
    verb's commit lands in the middle of the series (measured: `--continue`
    then replays the rest on top of it, and `--abort` exits 0 with `You seem
    to have moved HEAD. Not rewinding`, keeping it). The act is named from
    the first word of `sequencer/todo`. Where that file is missing, empty or
    no series, `git status` says nothing and `--continue` fails, and
    `--abort` and `--quit` both exit 0: the refusal names it generically and
    offers only what works.

    A BISECT IS ASKED TOO, AND A REBASE DIRECTORY GIT CAN READ NOTHING OF
    (#684, #612's review E2 and E5). A bisect holds HEAD detached on the
    commit it tests, where the real run met it as `family-holder-detached`,
    whose `git switch -c` would branch from that commit, and the dry run
    printed a plan (`BISECT_EFFECT`); its exit is `git bisect reset`. A
    stale, empty `rebase-merge/` was named as a rebase with `git rebase
    --abort`, which fails there as `--continue` does; it is named with `git
    rebase --quit`, the exit that works (`REBASE_HEAD_NAMES`). The remedy of
    each act that has no `finish` is its own (`UNFINISHABLE`).

    So the marks are asked, and the refusal names the one it found and that
    act's OWN exit: `git commit` for a merge, `--continue` for the others,
    or `--abort`; `--quit` or `git bisect reset` where nothing else works.
    Every mark is looked for WHERE GIT KEEPS IT (`_git_paths`), which in a
    linked worktree is not `.git/<name>`. Asked of the holder's own git
    directory, never of a member's: a merge in a MEMBER's mount is that
    checkout's own business.

    A REFTABLE KEEPS TWO OF THE MARKS AS REFS (#684, #612's review E4). A
    holder whose refs are a reftable holds `CHERRY_PICK_HEAD` and
    `REVERT_HEAD` in its ref store and in no file, and the file check found
    neither, so a cherry-pick or a revert stopped there was not refused.
    Where the file is not there, each is asked of the ref store too, by its
    exact name (`_in_ref_store`), and the refusal says git keeps it there
    (`IN_THE_REF_STORE`), with the same exit. A mark that is a file is named
    at its path, byte for byte as before, and git's own failure to answer is
    a failed git command, never "nothing in progress".

    WHEN IT IS ASKED (#612's review, N4; #684). Each verb asks it right
    after `Family.open` and the checks of its own arguments, so after
    `family.yaml` is parsed. The commonest merge conflict in a holder is in
    `family.yaml` itself, whose `<<<<<<<` `load_yaml` reads as a YAML merge
    key, so the parse fails first, and `Family.open` asks the same marks
    then (`_unparsable_in_an_act`): its `yaml-unparsable` names the act and
    this exit. Only then: asked before `load_yaml`, git would run before the
    refusal of a hand-edited `path:`, which this test holds to no git
    command at all:
    `test_family_member_path.py::test_the_refusal_is_made_before_any_git_call`.

    THE MARK'S PATH IS NAMED AS `shown_source` NAMES A PATH (#692): as it is,
    and as Python's `repr` spells it when a character in it is not printable.
    It is the true path, as git keeps it, so a holder whose path holds a line
    break printed the refusal across two lines, with a line of the person's
    choosing in it, and an ESC reached the terminal. A printable path is
    named byte for byte.
    """
    found = _operation_in_progress(root)
    if found is None:
        return
    what, mark, where, _, _, effect = found
    kept = (IN_THE_REF_STORE if where is None
            else f"at {shown_source(where.as_posix())}")
    raise Refusal(
        "family-operation-in-progress",
        f"{what} is unfinished in the family root: git keeps {mark} "
        f"{kept}. `{verb}` makes its commit with "
        "`git commit -- "
        f"<paths>`, and {effect.format(verb=verb)}. No git command that "
        "writes was run and nothing was written.",
        "Remediation: " + _operation_exit(found))


def _unparsable_in_an_act(root: Path) -> str:
    """The remediation of a `family.yaml` that does not parse while an act
    git has unfinished is in the holder, or "" where none is (#684, #612's
    review N4), for `Family.open`.

    A MERGE THAT CONFLICTED IN `family.yaml` WAS NEVER NAMED AS ONE. Every
    verb parses the manifest first, and git's `<<<<<<<` line reads as a YAML
    merge key, so the person was told `yaml-unparsable ... merge keys are not
    supported`, with no remediation, before the operation check was ever
    asked. The marks are asked here once the parse has failed, and the
    refusal keeps its code and its line and gains the act and its exit
    (`_operation_exit`). A holder git cannot answer for (not a repository,
    no git on PATH) keeps the refusal as it was: this is a remediation, and
    must never turn a refusal into a failure of its own.
    """
    try:
        found = _operation_in_progress(root)
    except (CommandFailed, OSError):
        return ""
    if found is None:
        return ""
    what, mark, where, *_ = found
    said = _operation_exit(found)
    kept = IN_THE_REF_STORE if where is None else f"at {where.as_posix()}"
    return (f"Remediation: {what} is unfinished in the family root: git "
            f"keeps {mark} {kept}, and where it left "
            f"{MANIFEST} conflicted, the reader cannot parse the lines git "
            "marks the conflict with (`<<<<<<<` reads as a YAML merge key). "
            + said[:1].upper() + said[1:])


def _checked_manifest_committed(root: Path, verb: str) -> None:
    """`family-manifest-uncommitted`: `verb` refuses, before its first write
    and under `--dry-run` alike, a `family.yaml` that holds a change HEAD
    does not, staged or not (#684; #459's line from #571's review, ruled by
    Brett Heap and relayed by lane 5 on #473 at 2026-10-16T13:56:50Z:
    "refuse a dirty `family.yaml`").

    THE COMMAND'S COMMIT TOOK IT. `add`, `bump` and `remove` rewrite
    `family.yaml` as the work tree has it (`Family.rewritten`) and commit it
    with `git commit -- <paths>` (`_commit_one`), which takes each path as
    the work tree has it: a comment line edited by hand and never staged
    went into the command's commit beside its own row, under its message.
    This is #407's rule for `.gitmodules` (`_checked_gitmodules_as_staged`)
    for the other file every one of those commits names, with one
    difference: a change staged and not committed is refused too, since the
    commit takes it just the same. So the remedies that have a person put a
    row back by hand (`member-path`, `_member_path`) say to commit that.

    ASKED OF GIT, AND NOTHING WRITTEN: the index's records for the file
    (`_index_records`, no pathspec), HEAD's entry for it, MODE AND OBJECT,
    from `git ls-tree -r -z HEAD` with no pathspec (a mode change staged
    and not committed went into the commit too, measured with `remove`:
    `mode change 100644 => 100755 family.yaml`), and `git ls-files -m`,
    git's own answer to "modified", which compares the work tree's copy
    with the index's by content where their stat data differ. Not `git
    hash-object`, which a dry run asks only for `bump`'s `nothing to do`;
    so a copy the index marks assume-unchanged, which git does not compare,
    is not seen.

    A HOLDER WHOSE HEAD HOLDS NO `family.yaml`, as one made by hand with no
    commit yet does, has no committed copy for a change to differ from: the
    command's commit is the file's first, as `add` has always made it, and
    nothing is asked.

    THE REMEDY IS GIT'S TWO WAYS OUT, both measured on git 2.43: `git commit
    -- family.yaml` commits the work tree's copy and nothing else staged,
    unmerged or not; `git checkout HEAD -- family.yaml` puts HEAD's back in
    the index and the work tree. Where the change is a staged deletion over
    a copy that is HEAD's byte for byte, or a mode staged with `git
    update-index --chmod` that the work tree's copy does not have, the
    first has nothing to commit, and the second is the way out.

    A CHANGE TO IT STAGED, AND A GITLINK UNDER `members/` STAGED BESIDE IT
    (#210's half-finished bump, lane 1's review of #816, F5), is told the
    second ALONE: there the first commits the row without its gitlink, so
    the row and the gitlink HEAD holds disagree (measured), while the
    second, and the same `bump` run again, makes the one commit of both.
    That holds for `bump` only: after the second, a half-finished `add`
    meets `member-path-taken` (lane 1 measured). Every stopped `add` or
    `bump` stages `family.yaml` beside its gitlink, so a gitlink staged by
    hand beside a change to the work tree's copy alone is told both ways
    out: no run stopped there, and the second alone would drop the
    person's edit (lane 1's re-verification, N1).
    """
    held = _head_entries(root)
    head = held.get(MANIFEST.encode())
    if head is None:
        return
    index = _index_records(root)
    records = [record.partition(b"\t")[0].split()
               for record in index.get(MANIFEST.encode(), [])]
    merged = [(mode, oid) for mode, oid, stage in records if stage == b"0"]
    unmerged = len(merged) != len(records)
    if unmerged:
        said = ["it is unmerged in the index"]
    elif not merged:
        said = ["its deletion is staged, so the index holds no copy"]
    elif merged != [head]:
        said = ["a change to it is staged and not committed"]
    else:
        said = []
    # `ls-files -m` lists an unmerged path once for each stage the work
    # tree's copy differs from, which says nothing more.
    if not unmerged and MANIFEST.encode() in _git_bytes(
            ["ls-files", "-m", "-z"], root).split(b"\0"):
        said.append("git lists the work tree's copy as modified, a change "
                    "nobody has staged")
    if not said:
        return
    raise Refusal(
        "family-manifest-uncommitted",
        f"{MANIFEST} holds a change HEAD does not: {', and '.join(said)}. "
        f"`{verb}` rewrites {MANIFEST} as the work tree has it and commits "
        "it, so that change would go into the command's commit beside its "
        "own. No git command that writes was run and nothing was written.",
        ("Remediation: the index also stages a gitlink under "
         f"{MEMBERS_DIR}/ that HEAD does not hold, as a run stopped before "
         f"its commit leaves it, and `git commit -- {MANIFEST}` would commit "
         "the row without it: put back HEAD's copy, in the index and the "
         f"work tree, `git checkout HEAD -- {MANIFEST}`."
         if merged and merged != [head] and _gitlink_staged(index, held)
         else
         "Remediation: which change to keep is a person's to say. To keep "
         f"it, commit it on its own first, `git commit -- {MANIFEST}`; to "
         "drop it, put back HEAD's copy, in the index and the work tree, "
         f"`git checkout HEAD -- {MANIFEST}`.")
        + " Then run the same command again.")


def _head_entries(root: Path) -> dict[bytes, tuple[bytes, bytes]]:
    """`{path: (mode, object)}` of every file and gitlink HEAD holds, by
    `git ls-tree -r -z HEAD` with NO PATHSPEC, as `_tree_entries` reads a
    tree, the mode kept as git prints it; none where HEAD names no commit
    yet, or none git can read (#684)."""
    try:
        listed = _git_bytes(["ls-tree", "-r", "-z", "HEAD"], root)
    except CommandFailed:
        return {}
    held = {}
    for record in listed.split(b"\0"):
        meta, _, name = record.partition(b"\t")
        if meta:
            mode, _, oid = meta.split()
            held[name] = (mode, oid)
    return held


def _gitlink_staged(index: dict[bytes, list[bytes]],
                    held: dict[bytes, tuple[bytes, bytes]]) -> bool:
    """Does `index` (`_index_records`) stage a gitlink under `members/` that
    HEAD (`_head_entries`) does not hold, mode and commit, as a run stopped
    between its stage and its commit leaves one (#684; lane 1's review of
    #816, F5)? Asked only where the index's copy of `family.yaml` differs
    from HEAD's too (N1)."""
    prefix = f"{MEMBERS_DIR}/".encode()
    return any(
        mode == b"160000" and held.get(name) != (mode, oid)
        for name, found in index.items() if name.startswith(prefix)
        for mode, oid, _ in (record.partition(b"\t")[0].split()
                             for record in found))


def _sparse_rules_exclude(root: Path, paths: list[str]) -> list[str]:
    """The `paths` the holder's sparse-checkout rules leave out, in the order
    given, ASKED OF GIT (`git sparse-checkout check-rules`), or none.

    `check-rules` reads paths on stdin and prints the ones the rules keep
    INSIDE, so what it does not print is out. It is asked only where sparse
    checkout is ON, and that is asked of git too, with `git sparse-checkout
    list`, which dies `this worktree is not sparse` where `core.sparseCheckout`
    is off. THE GATE IS NOT OPTIONAL (measured on git 2.43): `git
    sparse-checkout disable` turns the setting off and leaves
    `.git/info/sparse-checkout` as it was, and `check-rules` still reads that
    file and says the paths it excluded are outside, so a holder that is no
    longer sparse would be refused for rules git no longer applies.

    A GIT THAT CANNOT ANSWER IS "CANNOT TELL", NOT A REFUSAL. A git without
    the subcommand says `unknown subcommand` and exits 129; one with it can
    fail on the rules themselves (a sparse-checkout file that is not there).
    Any non-zero exit is treated alike: nothing is refused, and the late
    failure and its rollback stay as they were before #612, which leave the
    holder as it was. So a refusal made here is always git's own word, and a
    git that cannot give it costs nothing but the earliness.

    Paths go on stdin as BYTES, NUL-separated (`-z`), so no name is quoted,
    split or re-encoded on the way, on Windows too.
    """
    try:
        _git_bytes(["sparse-checkout", "list"], root)
    except CommandFailed:
        return []
    names = [path.encode("utf-8", "surrogateescape") for path in paths]
    try:
        inside = _git_bytes(["sparse-checkout", "check-rules", "-z"], root,
                            b"".join(name + b"\0" for name in names))
    except CommandFailed:
        return []
    kept = set(inside.split(b"\0"))
    return [path for path, name in zip(paths, names) if name not in kept]


def _sparse_is_cone(root: Path) -> bool:
    """Are the holder's sparse rules in cone mode? Read as a LISTING, `git
    config -z --list`, the way `_registered` reads config, and never `git
    config --get`: `test_family_dry_run.py` counts any `git config` that is
    not a listing as a write. Git writes section and variable names in lower
    case, so the key is `core.sparsecheckoutcone`; the last one listed wins,
    one with no value (`sparseCheckoutCone` alone) is true, and one that is
    unset is false, which is non-cone."""
    try:
        listing = _git_bytes(["config", "-z", "--list"], root)
    except CommandFailed:
        return False
    cone = False
    for record in listing.split(b"\0"):
        key, has_value, value = record.partition(b"\n")
        if key.lower() == b"core.sparsecheckoutcone":
            word = value.strip().lower()
            cone = not has_value or word in (b"true", b"yes", b"on") or (
                word.isdigit() and int(word) != 0)
    return cone


def _sparse_rules_hold_no_pattern(root: Path) -> bool:
    """Do the holder's NON-CONE sparse rules hold no pattern at all, as an
    EMPTY `.git/info/sparse-checkout` does (#684, #612's review E3)? ASKED
    OF GIT: `git sparse-checkout list` prints each pattern it reads from the
    file, comments and blank lines left out, so it prints nothing, or a
    blank line for a line of spaces, where there is none (measured on git
    2.43). Asked by the caller only of non-cone rules: in cone mode it lists
    the directories in the cone, and prints nothing for a cone of none, whose
    root files are inside and whose `git sparse-checkout add members` is
    right. A `list` that fails is no answer, and leaves the remedy as it
    was."""
    try:
        listed = _git_bytes(["sparse-checkout", "list"], root)
    except CommandFailed:
        return False
    return not listed.strip()


def _checked_inside_sparse_rules(root: Path, verb: str,
                                 paths: list[str]) -> None:
    """`family-sparse-excluded`: `verb` refuses, before its first write and
    under `--dry-run` alike, a path it stages that the holder's sparse
    checkout leaves out (#612, 571(d) and 574/5).

    GIT WILL NOT UPDATE AN INDEX ENTRY OUTSIDE THE RULES. `git add` and `git
    rm` say so (`outside of your sparse-checkout definition`) whatever the
    entry's skip-worktree mark says, and `git submodule add` says it of the
    mount. #407's `gitmodules-sparse` reads the MARK, which git clears for a
    file put back on disk by hand, so a `.gitmodules` the rules leave out
    but a person restored passed it: `remove` then did `deinit` and `git
    rm`, and failed at `git add` in its commit. A `members/` the rules
    leave out failed `add` at `git submodule add`, after the member was
    read, and `remove` and `bump` at `git rm` and `git add`, after the
    unmount and the checkout. Each rolled back. Here the rules are asked,
    not the marks: the paths each verb stages, named by its caller, are
    `.gitmodules`, `members/<Project>` and `family.yaml` for `add` and
    `remove` (the gitlink of the second is staged by `git rm`), and
    `members/<Project>` and `family.yaml` for `bump`.

    THE EXIT NAMES THE COMMAND THAT BRINGS THE PATH BACK, by the mode of the
    rules (`_sparse_is_cone`). In CONE mode, `git sparse-checkout add
    members`: it takes a directory, and `members/<Project>` is refused there
    for a gitlink git already tracks (`fatal: 'members/IRSS' is not a
    directory`). In NON-cone mode, the mount path itself, `git
    sparse-checkout add members/<Project>`, which its inner slash anchors at
    the root. `members` alone is NOT enough there: appended after a rule that
    names the member (`!/members/IRQS`, `!/members/*`, `!IRQS`,
    `!/members/I*`) it exits 0 and leaves the path out (measured on git
    2.43, #612's review F3), and the verb was refused again with the same
    remedy, a loop that only `disable` got out of.

    A ROOT FILE (`.gitmodules`, `family.yaml`) can only be out of non-cone
    rules: in CONE mode git keeps every file at the root inside (measured on
    git 2.43 with `set --cone`: both are inside, and a directory that is not
    in the cone is out). It is named UNANCHORED, `git sparse-checkout add
    .gitmodules`, which wins over `!/.gitmodules`, `!.gitmodules` and `!/.*`
    appended before it (measured here, and over `!/*` by the review), and
    which meets no shell that converts a leading slash into a path (Git Bash
    on Windows can). git prints a warning when the PERSON types such a
    pattern, and also for `members/<Project>` of a member git already tracks
    (`pass a leading slash before paths such as 'family.yaml' if you want a
    single file`); it never appears in the verb's own output, and the command
    brings the path back all the same. It is about how far a slashless
    pattern reaches, and nothing else in a holder's root, or in what
    `members/` holds that git tracks, is named so.

    `git sparse-checkout disable` is named beside it for any path: it brings
    back every path and leaves a copy already on disk as it is, as
    `gitmodules-sparse` says.

    NON-CONE RULES THAT HOLD NO PATTERN get `disable` ALONE (#684, #612's
    review E3). An empty rules file with sparse checkout on leaves out every
    path, so every path a verb stages is refused, and `git sparse-checkout
    add <the paths>` there makes those the only paths kept: measured on git
    2.43, it took every other file out of the work tree, and the holder's
    top level went from 14 entries to `.git`, `.gitmodules`, `family.yaml`
    and `members`. `disable` brings every path back and takes nothing away
    (`_sparse_rules_hold_no_pattern`).

    `git sparse-checkout check-rules` is a recent subcommand (the git here,
    2.43, has it); a git without it is "cannot tell" and refuses nothing
    (`_sparse_rules_exclude`).
    """
    out = _sparse_rules_exclude(root, paths)
    if not out:
        return
    # ONE PATTERN PER PATH: the mount path itself, or `members` once in cone
    # mode; a root file as it is named, unanchored.
    cone = _sparse_is_cone(root)
    patterns = list(dict.fromkeys(
        MEMBERS_DIR if cone and path.startswith(MEMBERS_DIR + "/") else path
        for path in out))
    names = ", ".join(f"`{path}`" for path in out)
    one = len(out) == 1
    if not cone and _sparse_rules_hold_no_pattern(root):
        bring = ("the rules hold no pattern at all, so they leave out every "
                 "path, and `git sparse-checkout add` would keep only the "
                 "paths it is given and take every other file out of the "
                 f"work tree: bring {'it' if one else 'them'} back with ")
    else:
        bring = (f"bring {'it' if one else 'them'} back into the rules: "
                 f"`git sparse-checkout add {' '.join(patterns)}`, or ")
    raise Refusal(
        "family-sparse-excluded",
        f"the holder's sparse checkout leaves out {names}, which `{verb}` "
        "stages, and git will not update an index entry outside the "
        "sparse-checkout definition: `git sparse-checkout check-rules` says "
        f"{'it is' if one else 'they are'} outside, so `{verb}` would fail "
        "after its first writes. No git command that writes was run and "
        "nothing was written.",
        f"Remediation: {bring}`git "
        "sparse-checkout disable`, which brings back every path the sparse "
        "checkout leaves out and leaves a copy already on disk as it is. "
        "Then run the same command again.")


def _print_next(family: "Family", branch: str) -> None:
    """The NEXT an act that committed ends with (#487): ONE pasteable line
    that pushes the branch the commit is on, every word quoted for the
    reader's shell (#486), then the pull request it is for.

    THE BRANCH BY ITS FULL REFNAME, ON BOTH SIDES (#689). A bare `<branch>`
    is a REFSPEC git reads for itself, and a leading `+` in one means FORCE:
    a holder on `+x` printed `push -u origin +x`, which pushed the LOCAL
    branch `x` over origin's `x` (`+ 77de599...261789e x -> x (forced
    update)`) and never the commit this act made, or, with no local `x`,
    died `src refspec x does not match any`. A branch that shares its name
    with a tag (`v1`) died `src refspec v1 matches more than one`.
    `refs/heads/<branch>:refs/heads/<branch>` is the branch it is whatever
    is checked out, and `-u` still records `origin/<branch>` as its upstream
    (`branch.<branch>.merge`). `init`'s own push names its side of the
    remote in full too (`HEAD:refs/heads/<branch>`, #421), and the whole
    refspec is ONE word for `shell_line` to quote.
    """
    refspec = f"{HEADS_PREFIX}{branch}:{HEADS_PREFIX}{branch}"
    print("\nNEXT  " + shell_line(["git", "-C", family.root, "push", "-u",
                                    "origin", refspec]))
    print(f"      then open a pull request against {family.tracking()}; "
          "never push to it directly")


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
    # BEFORE THE STAGE: a trailer that cannot be carried exactly is refused
    # while nothing has been staged (#322).
    message, trailer_args = commit_trailers(message, trailers)
    force_stage(root, paths if add is None else add)
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

    NO `gh` ON PATH IS `gh-not-found` (#537), as `pin_digest_from_gh` names
    it, and not a `FileNotFoundError` traceback: `init --dry-run` asks this
    question too now, and before that a dry run needed no `gh` at all.

    ONLY GH'S NOT-FOUND ANSWER IS "IT DOES NOT EXIST" (#609), as the
    scaffold's `remote_is_empty` reads it. Any failure of `gh repo view` used
    to be, so with a bad login `init --dry-run` exited 0 and the real run
    made its family folder and failed at `gh repo create`;
    `refuse_unless_not_found` refuses every other failure by name.
    """
    try:
        probe = subprocess.run(
            ["gh", "repo", "view", repository, "--json", "name"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", check=False)
    except FileNotFoundError as exc:
        raise Refusal(
            "gh-not-found",
            f"the `gh` CLI is not on PATH, so whether {repository} already "
            f"exists on GitHub cannot be asked: {exc}",
            "Remediation: put `gh` on PATH, logged in (`gh auth login`), and "
            "run this again: the real run creates the holder with `gh repo "
            "create`. `openRepoShape --preflight` names each missing "
            "prerequisite and offers to install it, on a typed yes.") from exc
    if probe.returncode != 0:
        refuse_unless_not_found(repository, probe)
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


#: The holder's own copy of the workstation utility, relative to the holder:
#: the path its Makefile's `SIBLINGS_SCRIPT` names, and the file `siblings`
#: runs (#543).
SIBLINGS_SCRIPT = "scripts/siblings.py"


def _family_script() -> str:
    """This file as the person who ran it names it from where they stand
    (#488): the path its NEXT lines run it by.

    `init`'s NEXT STEPS printed `Path(__file__).name`, `family.py`, which
    runs only from `scripts/`. AGENTS.md runs `init` from the standard's
    root, where that line failed `can't open file`, exit 2. So the path is
    RELATIVE TO THE DIRECTORY THE COMMAND WAS RUN FROM: from the root it is
    `scripts/family.py`, as `setup-project.py`, `validate-family.py`,
    AGENTS.md and README spell it, and from anywhere else it is the path
    that reaches this file from there. It is absolute where no relative path
    exists, another drive on Windows, or where that directory is gone.
    """
    here = Path(__file__).resolve()
    try:
        return os.path.relpath(here, Path.cwd())
    except (ValueError, OSError):
        return str(here)


def _add_command(holder: Path, org: str) -> str:
    """The `add` that grows the holder at `holder`, as `init` prints it:
    ONE line, so it pastes into PowerShell too, with this file's path, the
    holder's and the organisation each spelled by `shell_quoted` for the
    reader's shell (#486). A holder under `my work/` used to print
    `--family-root .../my work/Orbit`, two arguments to argparse.
    `<Project>` is left for the person to fill in."""
    return (f"{PYTHON} {shell_quoted(_family_script())} add --family-root "
            f"{shell_quoted(holder)} --member {shell_quoted(org)}/<Project>")


def _standard_checkout(start: Path) -> Path | None:
    """The checkout of openRepoShape that `start` is, or lies inside, or
    None (#488).

    A checkout is a directory holding `scripts/family.py` beside
    `templates/family-root/`, which is what this file needs of its own
    (`FAMILY_TEMPLATE`), so it is found whatever the directory is called and
    whichever copy of the standard is asked: this one, another clone, an
    install. `os.path`'s tests, which answer False for a directory this user
    cannot search rather than raising.
    """
    for directory in (start, *start.parents):
        if os.path.isfile(directory / "scripts" / "family.py") and \
                os.path.isdir(directory / "templates" / "family-root"):
            return directory
    return None


def _refuse_landing_in_standard(into: Path, holder: Path,
                                family: str) -> None:
    """`family-landing-in-standard`: with neither `--into` nor `--work-dir`,
    `init` refuses to land inside a checkout of openRepoShape (#488).

    AGENTS.md spelled the command `python3 scripts/family.py init ...`, a
    path that runs from the standard's root, and `--into` defaults to where
    the person stands, so the command followed exactly printed `landing
    <standard>/<Family>/<Family>` with no word, and `make siblings` would
    then have cloned every member into the standard's tree too. README's
    example passes `--into ..`, and so does AGENTS.md's now; this is the
    refusal for the run that does not. An explicit `--into` or `--work-dir`
    is somebody's choice of a place and is not second-guessed.

    THE REMEDY NAMES `--into ..` FROM THE ROOT, and from deeper inside the
    checkout the relative path that reaches its parent from there, so the
    printed flag lands the family beside the checkout wherever the person
    stands. Asked before anything is created, under `--dry-run` alike.

    THE THREE PATHS ARE NAMED AS `shown_path` NAMES A PATH (#766): the
    holder, the checkout and where `--into ..` lands, each under the
    directory the person stands in, whose name can hold an ESC or a line
    break. `--into {parent}` is `..` and `..`s, or on Windows a path no
    control character can be in, and is named as it is.
    """
    checkout = _standard_checkout(into)
    if checkout is None:
        return
    beside = checkout.parent
    try:
        parent = os.path.relpath(beside, into)
    except ValueError:  # another drive on Windows
        parent = str(beside)
    raise Refusal(
        "family-landing-in-standard",
        f"with neither --into nor --work-dir the holder lands where you are "
        f"standing, at {shown_path(holder)}, which is inside "
        f"{shown_path(checkout)}, a checkout of openRepoShape itself (it "
        "holds scripts/family.py and templates/family-root/). The family "
        "would be part of the standard's tree, and `make siblings` would "
        "clone every member into it too. Nothing was created, and "
        "`--dry-run` refuses the same.",
        f"Remediation: pass `--into {parent}` to land it beside this "
        f"checkout, at {shown_path(beside / family / family)}, or `--into "
        "<dir>` for any other parent directory; `--work-dir <dir>` is the "
        "override (`<dir>/<Family>`, no family folder). There is no --force.")


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

    THE DEFAULT IS REFUSED INSIDE A CHECKOUT OF THE STANDARD (#488,
    `_refuse_landing_in_standard`), after the holder-already-here question:
    a holder that exists there is the more specific answer.
    """
    if args.work_dir is not None:
        return None, args.work_dir.expanduser().resolve() / family
    into = (args.into or Path.cwd()).expanduser().resolve()
    # `os.path.isfile`, which answers False for a holder this user cannot
    # search: `Path.is_file()` raised `PermissionError` there, a traceback
    # before the question about the holder (`_refuse_a_taken_holder`) that
    # names it (#609's rule: a refusal by name, never a traceback). The two
    # paths are named as `shown_path` names a path (#766): `--into`, or the
    # directory the person stands in, can hold an ESC or a line break.
    if into.name == family and os.path.isfile(into / family / MANIFEST):
        raise Refusal(
            "family-holder-already-here",
            f"{shown_path(into)} is already the {family} family folder and "
            f"its holder is at {shown_path(into / family)}, so there is "
            "nothing to init",
            f"Remediation: `{_add_command(into / family, args.org)}` grows "
            "it, and `make siblings` in the holder puts each member's "
            "working clone beside it. There is no --force.")
    folder, holder = ((into, into / family) if into.name == family else
                      (into / family, into / family / family))
    if args.into is None:
        _refuse_landing_in_standard(into, holder, family)
    return folder, holder


#: Where `init` takes the id from when no `--id` is passed, as a sentence
#: names it: in the label `_manifest_flags` gives a value no flag supplied,
#: and in `family-bad-id` (#659).
FAMILY_ID_DERIVED_FROM = "--family lowercased"

#: How `family-bad-id` is told to go on (#659), in the words the scaffold
#: gives `scaffold-bad-id` and `adopt-project.py plan` `adopt-bad-id`
#: (#658). A `--id` the person passed is theirs to retype. An id `init`
#: derived is `--family` lowercased, and `--family` also names the holder
#: and, unless `--work-dir` is given, its family folder (`_landing`); the
#: name is the one `_classify_family_name` reads against a policy whose
#: forms take only ASCII letters, digits and hyphens, so "pass an explicit
#: lowercase --id" led straight to `naming-unclassified`, and so would
#: "change --family" to `North-Wind`. The derived remedy names the rule.
PASSED_FAMILY_ID_REMEDIATION = "Remediation: pass an explicit lowercase --id."
DERIVED_FAMILY_ID_REMEDIATION = (
    f"Remediation: change --family to {FAMILY_NAME_RULE}. The id is "
    f"{FAMILY_ID_DERIVED_FROM}, and an explicit --id would not change "
    "--family, which also names the holder and, unless --work-dir is given, "
    "its family folder.")


def _refuse_bad_family_id(family_id: str, given: str | None) -> None:
    """`family-bad-id`: an id `validate-family.py` would not take
    (`PROJECT_ID_RE`), named by where it came from (#659), as the scaffold
    names `scaffold-bad-id`.

    `given` is `--id` as parsed. One the person passed is named as the flag
    they typed, value as typed, and keeps its remedy. With none, or an empty
    one, the id is `--family` lowercased (`args.id or family.lower()`), and
    `--id 'north_wind' must match` named a value nobody had typed: the flag
    is named as `_manifest_flags` names one, by where its value came from,
    and an empty `--id ''` as empty, because it was passed."""
    if PROJECT_ID_RE.match(family_id):
        return
    pattern = PROJECT_ID_RE.pattern
    if given:
        raise Refusal("family-bad-id",
                      f"--id {family_id!r} must match {pattern}",
                      PASSED_FAMILY_ID_REMEDIATION)
    unset = "not given" if given is None else "empty"
    raise Refusal("family-bad-id",
                  f"--id ({unset}, so {FAMILY_ID_DERIVED_FROM}) is "
                  f"{family_id!r}, which must match {pattern}",
                  DERIVED_FAMILY_ID_REMEDIATION)


#: How `family-name-too-long`, `family-org-too-long`, `family-bad-org` and
#: `family-topic-too-long` are told to go on (#863), in the scaffold's words
#: for its own (#838). A `--id` the person passed is theirs to shorten. One
#: `init` derived is `--family` lowercased, and an explicit `--id` is the way
#: round it that keeps the holder's name as it is. A `--family` too long for
#: GitHub is told the id's bound too: its id is `--family` lowercased unless
#: `--id` is given, so whoever picks a shorter name learns both numbers.
GITHUB_NOTHING_MADE = ("Remediation: nothing was created, and `--dry-run` "
                       "refuses the same.")
HOLDER_TOO_LONG_REMEDIATION = (
    f"{GITHUB_NOTHING_MADE} Choose a shorter --family, of at most "
    f"{GITHUB_NAME_MAX} characters, GitHub's limit on a repository's name: "
    "it names the holder, its repository and, unless --work-dir is given, "
    f"its family folder. Its id, {FAMILY_ID_DERIVED_FROM} unless --id is "
    f"given, is at most {GITHUB_ID_MAX}, as GitHub keeps the topic "
    f"`xf-project-<id>` to {GITHUB_TOPIC_MAX}.")
PASSED_TOPIC_REMEDIATION = (
    f"{GITHUB_NOTHING_MADE} Pass a shorter --id, of at most {GITHUB_ID_MAX} "
    "characters.")
DERIVED_TOPIC_REMEDIATION = (
    f"{GITHUB_NOTHING_MADE} Pass an explicit --id of at most {GITHUB_ID_MAX} "
    f"characters: the id need not be {FAMILY_ID_DERIVED_FROM}, and --family, "
    "which names the holder, its repository and, unless --work-dir is given, "
    "its family folder, stays as it is.")
ORG_REMEDIATION = (
    f"{GITHUB_NOTHING_MADE} Pass --org as GitHub spells the organisation, the "
    "`<org>` of `https://github.com/<org>`: GitHub gives no user or "
    f"organisation a name of more than {GITHUB_OWNER_MAX} characters.")
ORG_SPELLING_REMEDIATION = (
    f"{GITHUB_NOTHING_MADE} Pass --org as GitHub spells the organisation, the "
    "`<org>` of `https://github.com/<org>`.")


def _refuse_what_github_cannot_hold(args, family: str, family_id: str,
                                    topic: str) -> None:
    """What GitHub will not take of the holder, refused where GitHub is
    asked (#863), before anything exists and under `--dry-run` alike:
    `family-name-too-long`, a `--family` over GitHub's 100 for the holder's
    repository, `<org>/<Family>`; `family-org-too-long` and
    `family-bad-org`, an `--org` GitHub gives no organisation, by its length
    or its characters; and `family-topic-too-long`, an id whose
    `xf-project-<id>` topic GitHub will not set. The questions are the
    scaffold's (#838), asked with its helpers.

    THE TOPIC IS SET LAST (`_finish_holder_remote`'s `gh repo edit
    --add-topic`), after `_create_holder_remote` and
    `_create_holder_worktree`'s push, so an id over 39 characters, which a
    `--family` of 40 or more gives by default, failed there with the holder
    made and pushed, no NEXT STEPS printed, and a re-run refused as
    `family-remote-exists`. An `--org` or a `--family` GitHub will not take
    failed at `gh repo create`. Under `--local-remote-dir` none is asked: a
    bare repository on disk has no topic and no owner, and its name is the
    disk's. The id is named as `_refuse_bad_family_id` names it, by where it
    came from."""
    if args.local_remote_dir is not None:
        return
    if len(family) > GITHUB_NAME_MAX:
        raise Refusal(
            "family-name-too-long",
            f"--family is {_both_ends(family)}, {len(family)} characters, and "
            "GitHub keeps a repository's name, the holder's "
            f"`<org>/<Family>`, to at most {GITHUB_NAME_MAX}",
            HOLDER_TOO_LONG_REMEDIATION)
    refuse_an_owner_github_cannot_have("family-org-too-long", args.org,
                                       "--org", ORG_REMEDIATION)
    refuse_an_owner_github_cannot_spell("family-bad-org", args.org, "--org",
                                        ORG_SPELLING_REMEDIATION)
    if args.id:
        named, remediation = "--id", PASSED_TOPIC_REMEDIATION
    else:
        unset = "not given" if args.id is None else "empty"
        named = f"--id ({unset}, so {FAMILY_ID_DERIVED_FROM})"
        remediation = DERIVED_TOPIC_REMEDIATION
    refuse_a_topic_github_cannot_set("family-topic-too-long", topic,
                                     family_id, named, remediation)


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
    # AND GIT'S OWN ANSWER (#283): `_create_holder_remote` runs `gh repo
    # create` before `_create_holder_worktree`'s first `git init -b`, so a
    # name git refuses as a branch (`~`, `a..b`, `x.lock`, `a/`) created the
    # holder's repository and then died. Asked here, `--dry-run` refuses it
    # too, before anything is created.
    refuse_bad_branch("family-bad-tracking-branch", "--tracking-branch",
                      args.tracking_branch)
    family_id = checked_value("--id", args.id or family.lower())
    _refuse_bad_family_id(family_id, args.id)
    policy = NamingPolicy.load(NAMING_POLICY)
    _classify_family_name(policy, family)
    _refuse_an_unholdable_holder_name(family)
    topic = policy.topic_for(family_id)
    # WHAT GITHUB WILL NOT TAKE (#863), before `_creator_name` and before any
    # `gh` call: the topic is set last, after the holder is pushed.
    _refuse_what_github_cannot_hold(args, family, family_id, topic)
    return family, family_id, topic


#: Why a creator `unwritable_reason` refuses cannot be recorded (#426): how
#: each remediation below ends.
CREATOR_UNWRITABLE_WHY = (
    "which the manifest could keep only as a lone surrogate, and that is no "
    "character; a line break or a control character would break or garble "
    "the line the plan prints it on; and a bidirectional embedding, override "
    "or isolate control would show the rest of that line in another order "
    "than it is written.")

#: What `family-unwritable-value` is told to do (#426), in the scaffold's
#: words for the same refusal (`scaffold-unwritable-value`, #282), BY WHERE
#: `_creator_name` READ THE CREATOR (#688). Each names the flag, the variable
#: or the setting that supplied the name, so the person corrects the one that
#: did; the setting's is the words #426 gave it.
CREATOR_UNWRITABLE_REMEDIATIONS = {
    "--created-by": (
        "Remediation: nothing was created, and `--dry-run` refuses the same. "
        "Pass --created-by again, retyped. A byte that is not UTF-8 reaches "
        "a command line from a terminal or a script whose encoding is not "
        "the locale's, " + CREATOR_UNWRITABLE_WHY),
    "GIT_AUTHOR_NAME": (
        "Remediation: nothing was created, and `--dry-run` refuses the same. "
        "`init` read the creator from GIT_AUTHOR_NAME, because no "
        "--created-by was given: correct that variable, or unset it, for git "
        "makes the holder's first commit as it too; --created-by 'Your Name' "
        "changes only who `family.yaml` records. The environment keeps it as "
        "the bytes it was given, so a name set in a legacy code page holds a "
        "byte that is not UTF-8, " + CREATOR_UNWRITABLE_WHY),
    "`git config user.name`": (
        "Remediation: nothing was created, and `--dry-run` refuses the same. "
        "`init` read the creator from `git config user.name`, because no "
        "--created-by was given and GIT_AUTHOR_NAME names nobody: pass "
        "--created-by 'Your Name', or correct that setting. git keeps it as "
        "the bytes it was given, so a name saved in a legacy code page holds "
        "a byte that is not UTF-8, " + CREATOR_UNWRITABLE_WHY),
}

#: The variables git makes the holder's first commit with, by role, and the
#: identity `git var` names for that role (#688). `env_commit` gives a name
#: or an address that is unset or empty a fallback of its own, and passes a
#: date on as it stands.
COMMIT_IDENTITY = (
    ("author", "GIT_AUTHOR_IDENT",
     ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_AUTHOR_DATE")),
    ("committer", "GIT_COMMITTER_IDENT",
     ("GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "GIT_COMMITTER_DATE")),
)

#: A name and an address git takes, standing in for one the person left
#: unset or empty, where `env_commit` puts its fallback: git is then asked
#: about the person's own variables, beside values it accepts. Each is
#: spelled once, and neither is the fallback `env_commit` or `commit_on_branch`
#: spells: the answer does not depend on which acceptable value stands in, and
#: a third copy of a fallback would be one more to keep in step with them.
COMMIT_STAND_IN_NAME = "identity check"
COMMIT_STAND_IN_EMAIL = "identity-check@openreposhape.invalid"
COMMIT_IDENTITY_STAND_IN = {
    "GIT_AUTHOR_NAME": COMMIT_STAND_IN_NAME,
    "GIT_AUTHOR_EMAIL": COMMIT_STAND_IN_EMAIL,
    "GIT_COMMITTER_NAME": COMMIT_STAND_IN_NAME,
    "GIT_COMMITTER_EMAIL": COMMIT_STAND_IN_EMAIL,
}

#: What `family-bad-commit-identity` is told to do (#688).
COMMIT_IDENTITY_REMEDIATION = (
    "Remediation: nothing was created, and `--dry-run` refuses the same. "
    "Correct each variable named, or unset it, and run again. `init` makes "
    "the holder's first commit with them only after the holder's remote and "
    "work directory exist, and git would refuse them there. Unset or empty, "
    "a name or an address is `init`'s own and a date is the moment of the "
    "commit; --created-by sets who `family.yaml` records, not who git makes "
    "the commit as.")


def _refuse_an_unusable_commit_identity() -> None:
    """The author and the committer git will make the holder's first commit
    as are ones git accepts, or this refuses as `family-bad-commit-identity`
    (#688), before anything exists and under `--dry-run` alike.

    `_creator_name` passes over a GIT_AUTHOR_NAME of whitespace alone and
    reads `git config user.name`, so `family.yaml` was written from a good
    name. But `env_commit` replaces a variable only when it is unset or
    empty, so `git commit` was handed the whitespace, and refused it (`fatal:
    name consists only of disallowed characters`), exit 2, after the holder's
    remote and work directory existed. A GIT_COMMITTER_NAME of whitespace, a
    name of nothing but `<>`, and a GIT_AUTHOR_DATE or GIT_COMMITTER_DATE git
    cannot read failed at the same commit in the same way.

    GIT'S OWN ANSWER, as `refuse_bad_branch` asks git of a branch (#283):
    `git var GIT_AUTHOR_IDENT` and `git var GIT_COMMITTER_IDENT` build the
    identity by the rules `git commit` applies, so the question is no copy
    of git's rules that could fall behind them. Each role is asked with the
    person's own variables and `COMMIT_IDENTITY_STAND_IN` where `env_commit`
    would put its fallback, and only a role the person set a variable of:
    the stand-ins alone are an identity git takes. Asked of NO repository,
    from an empty directory, as `_ask_git_branch` asks: no repository's
    config plays a part, as none but the new holder's does at the commit,
    and `refuse_bad_branch` has just had an answer from git there, so a
    refusal here is about the variables. The detail names every variable of
    the role the person set, with git's own words, which say which one.
    Git echoes a value it refuses (`fatal: invalid date format: <the date>`)
    as it was given, a line break and a bidi control included, so its words
    are quoted by `shown_path` (#610): as they are when printable, as
    Python's `repr` spells them when not. Raw, a `GIT_AUTHOR_DATE` holding a
    line break began a line of its own choosing in the refusal.

    `cmd_init` ASKS IT AFTER THE QUESTIONS ABOUT WHAT IT WRITES, before the
    landing, the plan and anything made: the clone URL's refusal (#433)
    still comes before any process but `git check-ref-format`, and the
    manifest's (#307) before `run` is reached.
    """
    problems = []
    for role, ident, variables in COMMIT_IDENTITY:
        given = [f"{key} {os.environ[key]!r}" for key in variables
                 if os.environ.get(key)]
        if not given:
            continue
        identity = {key: os.environ.get(key) or stand_in
                    for key, stand_in in COMMIT_IDENTITY_STAND_IN.items()
                    if key in variables}
        nowhere = tempfile.mkdtemp(prefix="openreposhape-ident-")
        try:
            run(["git", f"--git-dir={nowhere}", "var", ident],
                cwd=Path(nowhere), env=identity)
        except CommandFailed as exc:
            listed = (f"{', '.join(given[:-1])} and {given[-1]}"
                      if len(given) > 1 else given[0])
            # Git echoes a value it refuses (a date) as it was given, so its
            # words are spelled as a path is (#610), never printed raw.
            problems.append(
                f"git refuses the {role} the holder's first commit would be "
                f"made as, from {listed} (`git var {ident}`: "
                f"{shown_path(exc.output)})")
        finally:
            # Empty: git writes nothing there (`_ask_git_branch`'s reason).
            shutil.rmtree(nowhere, ignore_errors=True)
    if problems:
        raise Refusal("family-bad-commit-identity", "; ".join(problems) + ".",
                      COMMIT_IDENTITY_REMEDIATION)


def _creator_name(args) -> str:
    """Whoever `--created-by` (or the environment, or git config) says
    created this family — refused when nothing does.

    Split from `cmd_init` for #136: creating a family is a human's act and
    the manifest records whose.

    A `git config user.name` THAT IS NOT TEXT IS REFUSED BY NAME (#426), as
    the scaffold refuses the same setting (#282) and `adopt-project.py`'s
    `plan` does (#292). git keeps the name as the bytes it was given, and one
    saved in a legacy code page is not UTF-8: nobody did anything wrong.
    `git_out`'s own strict decode raised `UnicodeDecodeError`, a traceback,
    exit 1, under `--dry-run` too, naming neither the setting nor the flag
    (`--created-by`) that gets past it. The setting is now read as bytes and
    decoded as `sys.argv` and `os.environ` are, `surrogateescape`, so the
    byte survives as a lone surrogate for `unwritable_reason` to name: the
    one question the scaffold and adopt ask of the same name, so a name that
    holds a line break, a control character or a bidi control is refused in
    the same words as one that holds a byte that is not UTF-8. It is asked
    here, before the holder's remote or work directory, and `--dry-run`
    refuses alike.

    WHATEVER ANSWERED IS ASKED (#688). #426 asked only what `git config
    user.name` answered, so the same name was refused from the setting and
    accepted from `--created-by` or GIT_AUTHOR_NAME: `--created-by
    $'Ada\\nLovelace' --dry-run` exited 0 with the plan's `created by` line
    broken in two, and one holding U+202E exited 0. The scaffold asks its
    elector whatever the source (`_identity`), and so does this now, once,
    of the name that answered. The detail names the creator as
    `_manifest_flags` (#307) names it, so this refusal and
    `family-manifest-invalid` agree on who is meant; the remediation names
    the flag, the variable or the setting that answered
    (`CREATOR_UNWRITABLE_REMEDIATIONS`), for that is the one to correct.

    GIT_AUTHOR_NAME is also who git makes the holder's first commit as, and
    a blank one passed over here is not passed over there: `cmd_init` asks
    git about that later (`_refuse_an_unusable_commit_identity`, #688).
    THE REMEDIES ARE EXITS THAT WORK (Brett Heap's ruling, "Offer only exits
    that work"): the variable's own says to correct or unset it, not to pass
    `--created-by`, which changes only who `family.yaml` records and leaves
    git to refuse the same variable at the commit; and where the variable is
    set but blank and nothing else names a creator, the refusal says that
    variable is there and is the cause, instead of "no GIT_AUTHOR_NAME", and
    tells the person to unset it AND pass `--created-by`.
    """
    created_by, source = args.created_by, "--created-by"
    blank_variable = False
    if not created_by:
        named = os.environ.get("GIT_AUTHOR_NAME") or ""
        created_by, source = named.strip(), "GIT_AUTHOR_NAME"
        blank_variable = bool(named) and not created_by
    if not created_by:
        source = "`git config user.name`"
        try:
            created_by = git_out(["config", "user.name"], cwd=SHAPE_ROOT,
                                 binary=True).decode(
                                     "utf-8", "surrogateescape").strip()
        except Refusal:
            created_by = ""
    if not created_by and blank_variable:
        raise Refusal(
            "family-no-creator",
            "no --created-by, a GIT_AUTHOR_NAME of whitespace alone, and no "
            "`git config user.name`. Creating a family is a human's act and "
            "the manifest records whose.",
            "Remediation: unset GIT_AUTHOR_NAME, which git would make the "
            "holder's first commit as and refuses, and re-run with "
            "--created-by 'Your Name'.")
    if not created_by:
        raise Refusal(
            "family-no-creator",
            "no --created-by, no GIT_AUTHOR_NAME and no `git config "
            "user.name`. Creating a family is a human's act and the manifest "
            "records whose.",
            "Remediation: re-run with --created-by 'Your Name'.")
    reason = unwritable_reason(created_by)
    if reason:
        raise Refusal(
            "family-unwritable-value",
            f"{_manifest_flags(args)['CREATED_BY']} is {created_by!r}, which "
            f"`init` records in the holder's `family.yaml`, and {reason}.",
            CREATOR_UNWRITABLE_REMEDIATIONS[source])
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


#: What every `family-unwritable-value` for a clone URL made under
#: `--local-remote-dir` tells a person to do, `init`'s for the holder (#433)
#: and `add`'s for a member (#693) alike: another directory, or GitHub, as
#: the scaffold's twin says (`CLONE_URL_REMEDIATION`), with the verb and the
#: last name of the GitHub URL filled in.
#:
#: THE URL IS THE PATH THE FLAG RESOLVES TO (#693). A `--local-remote-dir`
#: typed as text can lead through a symbolic link to a directory whose name
#: is not, or be relative to one, and the URL a refusal names is then not
#: the path that was typed. Told only to pass a path that is "one line of
#: UTF-8 text", which it already was, a person renames the link and is
#: refused again, so this says where the fault is.
#:
#: WHAT THE DIRECTORY MUST HOLD IS THE CALLER'S (`{holding}`, #693). `init`
#: makes the holder's bare repository there, so a directory made anew is a
#: way out of its refusal. `add` reads the member's bare `<Project>.git`
#: from it (`_probe_member`), so a new, empty directory is refused again
#: with `does not exist`: its remedy says the directory must hold the
#: repository, renamed or moved, as lane 1's review of #812 measured.
LOCAL_REMOTE_DIR_REMEDY = (
    "Pass a --local-remote-dir whose path is one line of UTF-8 text with no "
    "control character in it{holding}, and run again; or run `{verb}` "
    "against GitHub, without --local-remote-dir, "
    "where the clone URL is `https://github.com/<org>/<{name}>.git`. The "
    "clone URL is the path --local-remote-dir resolves to, so where the path "
    "given is text and the URL named above is not, the fault is in what it "
    "leads through: a symbolic link on it whose target is not text, or, for "
    "a relative path, the directory it was given from. Rename or replace "
    "the directory whose name is not text, or pass a path that does not "
    "lead through it; renaming a link changes nothing.")

#: What a `family-unwritable-value` for the holder's clone URL is told to do
#: (#433). The holder's `README.md` quotes the URL for a shell (#693) and
#: writes every character of it as itself but an apostrophe, so a lone
#: surrogate, which a Windows name can hold, cannot be written either, as
#: #282's `UNWRITABLE_REMEDIATION` in `scaffold-project.py` says (#693).
CLONE_URL_REMEDIATION = (
    "Remediation: nothing was created, and `--dry-run` refuses the same. "
    + LOCAL_REMOTE_DIR_REMEDY.format(
        verb="init", name="Family",
        holding=", a directory renamed or made anew")
    + " The holder's `README.md` prints the clone URL in a `git clone` "
    "line, in quotes where a shell needs them, every character but an "
    "apostrophe written as itself: a byte that is not UTF-8 in the path (a "
    "directory named in a legacy code page), or a lone surrogate, cannot be "
    "written at all, a line break or a control character would break or "
    "garble the line it is written into, and a bidirectional embedding, "
    "override or isolate control would show the rest of that line in "
    "another order than it is written.")

#: What a `family-unwritable-value` for a member's clone URL is told to do
#: (#693). `git submodule add` records the URL in the holder's `.gitmodules`
#: as it is given (a line break escaped as `\n`, every other character
#: raw), and the holder's `make siblings` reads it back through `git config
#: --list` as UTF-8 text, a line a value. Measured on main: `caf<e9>` came
#: back as `caf\ufffd`, a line break cut the URL short at it, and an escape
#: and a bidi override came back as themselves.
MEMBER_URL_REMEDIATION = (
    "Remediation: `--dry-run` refuses the same. "
    + LOCAL_REMOTE_DIR_REMEDY.format(
        verb="add", name="Project",
        holding=" and that holds the member's bare repository "
                "`<Project>.git`, its directory renamed or the repository "
                "moved")
    + " The holder's `.gitmodules` records the clone URL as git is given "
    "it, and the holder's `make siblings` reads it back as UTF-8 text, a "
    "line a value: a byte that is not UTF-8 in the path (a directory named "
    "in a legacy code page), or a lone surrogate, reads back as another "
    "path, a line break ends the URL where it falls, a control character "
    "garbles the line it is shown in, and a bidirectional embedding, "
    "override or isolate control shows the rest of that line in another "
    "order than it is written.")


def _refuse_an_unwritable_clone_url(local: bool, url: str) -> None:
    """Refuse the holder's clone URL when no file can hold it, before any
    remote or folder exists, as `adopt-project.py` (#255) and the scaffold
    (#433) refuse theirs.

    Only a local one can be refused: under `--local-remote-dir` the URL is
    the bare repository's own path, which `templates/family-root/README.md`
    prints (`git clone --recurse-submodules {{CLONE_URL}}`); against GitHub
    it is `https://github.com/<org>/<Family>.git`, ASCII by construction. A
    directory whose name is not UTF-8 reaches `sys.argv` as a string with a
    lone surrogate, and `write_lf` encodes strictly, so `init` raised
    `UnicodeEncodeError` in `materialize_family_root` after `<Family>.git`
    existed and the family folder was made, while `--dry-run` exited 0 and
    said nothing (#433). One bidi override or a line break in the path was
    written into the README raw.

    The code is this tool's own, `family-unwritable-value`, for the question
    `adopt-unwritable-value` and `scaffold-unwritable-value` answer:
    `unwritable_reason`, the one `shape_materialize` keeps for all three.
    """
    if not local:
        return
    reason = unwritable_reason(url)
    if reason:
        raise Refusal(
            "family-unwritable-value",
            "under --local-remote-dir the holder's clone URL is the bare "
            f"repository's own path, {url!r}, which `init` writes into the "
            f"holder's `README.md`, and {reason}.",
            CLONE_URL_REMEDIATION)


def _refuse_an_unwritable_member_url(local: bool, url: str) -> None:
    r"""Refuse a member's clone URL that the holder's `.gitmodules` cannot
    hold as text, before the member is read or anything is mounted, and
    under `--dry-run` alike, as `init` refuses the holder's (#433, #693).

    Only a local one can be refused: under `--local-remote-dir` the URL is
    the bare repository's own path (`_member_url`), which `git submodule add`
    writes into `.gitmodules`; against GitHub it is
    `https://github.com/<org>/<Project>.git`, ASCII by construction
    (`MEMBER_RE`). On main `add --local-remote-dir <dir>/caf<e9>` exited 0,
    dry run and real, and committed the byte into `.gitmodules`, where the
    holder's `make siblings` read the URL as `caf\ufffd`, another path than
    the one the holder is pinned to; a line break, an escape and a bidi
    override were committed too (#693).

    `init`'s question (`unwritable_reason`) and `init`'s code
    (`family-unwritable-value`), with `add`'s own words for where the URL
    goes (`MEMBER_URL_REMEDIATION`).
    """
    if not local:
        return
    reason = unwritable_reason(url)
    if reason:
        raise Refusal(
            "family-unwritable-value",
            "under --local-remote-dir the member's clone URL is the bare "
            f"repository's own path, {url!r}, which `add` writes into the "
            f"holder's `.gitmodules`, and {reason}. No git command that "
            "writes was run and nothing was written.",
            MEMBER_URL_REMEDIATION)


def _shape_snapshot() -> tuple[str, str]:
    """`(shape_commit, shape_tree)` of this checkout, warning to stderr when
    it is dirty.

    Split from `cmd_init` for #136.

    WHETHER THE CHECKOUT IS DIRTY IS ASKED OF GIT'S BYTES (#423). Only
    whether `status --porcelain` printed anything is used, never what, so it
    is not decoded at all. With `core.quotePath=false` git prints a file name
    as the bytes it holds, and a name that is not UTF-8 made `git_out`'s
    strict decode raise `UnicodeDecodeError`: a traceback, exit 1, before the
    holder's remote existed, where this means to print the warning below and
    go on.
    """
    shape_commit = git_out(["rev-parse", "HEAD"], cwd=SHAPE_ROOT).lower()
    shape_tree = tree_digest(SHAPE_ROOT, shape_commit)
    if git_out(["status", "--porcelain"], cwd=SHAPE_ROOT, binary=True):
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

    THE CLONE URL IS ONE WORD OF A COMMAND A PERSON PASTES (#693). The
    holder's `README.md` prints it in `git clone --recurse-submodules
    {{CLONE_URL}}`, and under `--local-remote-dir` it is a path, which was
    rendered raw: under `a b/` the line split in two when pasted, and a path
    holding `$`, `'`, `;` or `&` broke it too. It is spelled by
    `shell_quoted` in the POSIX dialect whatever the host, since the README
    is a committed file read on every OS and pasted commands are for a POSIX
    shell (#532); a GitHub URL and an ordinary POSIX path are left bare (a
    Windows path, spelled with `\\`, is quoted). Only this value is quoted:
    the block's other placeholder, `{{FAMILY}}` in `cd {{FAMILY}}`, is a
    name the naming policy spells in letters and digits.
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
        "CLONE_URL": shell_quoted(url, "posix"),
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

    THE FOLDER AND THE HOLDER ARE NAMED AS `shown_path` NAMES A PATH (#766).
    Both lie under `--into`, `--work-dir` or the directory the person
    stands in, and the plan is on stdout before any refusal, so a name with
    a line break and then `WARNING forged-line: pwned` printed that line as
    a line of the plan, on a dry run and on a run refused after it, and an
    ESC reached the terminal. A printable path is named byte for byte.

    THE BRANCH AND, ON DISK, THE VISIBILITY ARE NAMED (#913), as the
    scaffold's plan names them: the plan named neither the tracking branch
    the holder is created on nor, under `--local-remote-dir`, the
    visibility `family.yaml` records. And "not found" is what this token can
    see (#913, L2-61): GitHub answers a private repository the token cannot
    see as not found, so the `remotes` row says when the holder is created
    in the scaffold's words (`NOT_FOUND_WITH_THIS_TOKEN`).
    """
    print(f"family       {values['FAMILY_NAME']} ({values['FAMILY_ID']})")
    print(f"shape        {SHAPE_REPOSITORY} @ {shape_commit[:12]} "
          f"(tree {shape_tree[:12]}…)")
    print(f"created by   {values['CREATED_BY']} on {values['CREATED_ON']}")
    print(f"  holder     {repository:<28} -> {url}")
    if folder is None:
        print(f"landing      {shown_path(holder)}   (--work-dir: no family "
              "folder)")
    else:
        print(f"folder       {shown_path(folder)}   a plain folder, NOT a "
              "repository")
        print(f"landing      {shown_path(holder)}   the holder clone, inside "
              "it")
    print(f"members      mounted under {MEMBERS_DIR}/; none yet — "
          "`family.py add` puts one there")
    if local:
        print(f"visibility   {values['VISIBILITY']}, which {MANIFEST} "
              "records; a bare repository on disk has none")
        print("remotes      a bare repository on disk (no network)")
    else:
        print(f"remotes      gh repo create --{values['VISIBILITY']}, if gh "
              f"does not find {repository}")
        for line in NOT_FOUND_WITH_THIS_TOKEN:
            print(f"             {line}")
    if reuse_empty_repo:
        print("reuse        an EXISTING <Family> with zero commits is used as "
              "the holder")
    print(f"branch       {values['TRACKING_BRANCH']}, the tracking branch the "
          "holder is created on")
    print("topics       " + ("skipped for local remotes" if local
                             else f"gh repo edit --add-topic {topic}"))


#: The code of every folder `init` makes and cannot (#609).
FOLDER_REFUSAL = "family-folder-cannot-be-made"


def _landing_folder(folder: Path | None, holder: Path) -> tuple[Path, str]:
    """`(the folder init makes the holder in, how the person names it)`:
    the family folder, or with `--work-dir` that directory itself."""
    if folder is None:
        return holder.parent, "--work-dir"
    return folder, "the family folder"


def _landing_flag(folder: Path | None) -> str:
    """The flag the person landed `init` by: `--work-dir` where there is no
    family folder, `--into` otherwise."""
    return "--work-dir" if folder is None else "--into"


def _refuse_a_taken_holder(folder: Path | None, holder: Path) -> None:
    """`family-target-exists`: something already stands where the holder
    goes, a folder that holds anything or, since #609, a file, which
    `iterdir()` met with a `NotADirectoryError` traceback, or an empty folder
    this user cannot write in (L2-60), whose remediation names the flag the
    person landed by: `--work-dir` where there is no family folder, `--into`
    otherwise."""
    why = target_in_the_way(holder)
    if why:
        raise Refusal(
            "family-target-exists",
            f"{shown_source(holder)} already exists and {why}",
            target_remediation(
                why,
                "Remediation: choose another --into (or an empty "
                "--work-dir); if that IS the holder, it is already a family "
                "and `family.py add` is what grows it. There is no --force.",
                _landing_flag(folder)))


def _refuse_unmakeable_landing(args, folder: Path | None, holder: Path,
                               local: bool) -> None:
    """Every folder `init` makes, and the holder it writes, asked before
    anything is made, by the dry run and the real run alike (#609): the
    family folder (or `--work-dir`), the holder in it, `--local-remote-dir`.

    THE DRY RUN ASKED NONE OF IT. With a file where the family folder, the
    holder or `--local-remote-dir` goes, `init --dry-run` exited 0 and the
    real run died in `mkdir` or `iterdir()` with a traceback. A folder that
    cannot be made, because a file stands at it or above it or this user
    cannot write where it goes, is `family-folder-cannot-be-made` now, and
    the real run's own `mkdir` is `make_folder`, which refuses the same in
    the system's words.
    """
    landing, named = _landing_folder(folder, holder)
    refuse_unmakeable_folder(FOLDER_REFUSAL, named, landing,
                             _landing_flag(folder))
    _refuse_a_taken_holder(folder, holder)
    if local:
        refuse_unmakeable_folder(FOLDER_REFUSAL, "--local-remote-dir",
                                 args.local_remote_dir.resolve())


def _prepare_landing_dir(folder: Path | None, holder: Path) -> Path:
    """Make the landing directory, refused if something already stands
    where the holder goes (`_refuse_a_taken_holder`).

    Split from `cmd_init` for #136. Run only after `_refuse_unmakeable_landing`
    and `_checked_reuse` have said yes (#609), so a refused run leaves no
    folder; the holder is asked again, as it stands once the folder is made.
    """
    # `mkdir -p` on the FOLDER, which is fine if it is already there — a
    # family folder somebody made by hand, or one a scaffolded member already
    # landed in, is exactly the case this is supposed to join.
    landing, named = _landing_folder(folder, holder)
    make_folder(FOLDER_REFUSAL, named, landing)
    _refuse_a_taken_holder(folder, holder)
    return holder


def _checked_reuse(reuse_empty_repo: bool, local: bool, url: str,
                   repository: str) -> bool:
    """Is the holder's remote an existing, empty repository being reused?

    Refused when the remote already exists WITH commits, or exists empty
    without `--reuse-empty-repo`. Split from `cmd_init` for #136.

    A LOCAL REMOTE IS NAMED AS `shown_path` NAMES A PATH (#766): it is a
    path under `--local-remote-dir`. `_refuse_an_unwritable_clone_url`
    refuses a control character there first, so only a character that is
    not printable and not refused (a zero-width space) reaches this from
    the command line. A GitHub `<org>/<Family>` is named as it is.
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
            f"{shown_path(target) if local else target} already exists"
            + ("" if local else " on GitHub")
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
        make_folder(FOLDER_REFUSAL, "--local-remote-dir", Path(url).parent)
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
        # THE BRANCH BY ITS FULL REFNAME (#421). A bare `<branch>` is a
        # REFSPEC, and a leading `+` in one means FORCE: `--tracking-branch
        # +x`, a name `git check-ref-format --branch` accepts and `git init
        # -b` creates, was read as the forced push of a local branch `x` and
        # died `src refspec x does not match any`, after `gh repo create` had
        # made the holder. `HEAD:refs/heads/<branch>` names both sides in
        # full, so every name git accepts is pushed as the branch it is, and
        # `-u` still records `origin/<branch>` as its upstream. The same
        # spelling `scaffold-project.py` pushes its three repositories with.
        run(["git", "push", "-q", "-u", "origin",
             f"HEAD:refs/heads/{args.tracking_branch}"], cwd=work)
    except CommandFailed as exc:
        print(exc.loudly("pushing the family holder"), file=sys.stderr)
        print(FAMILY_RULESET_HINT.format(repo=repository,
                                         tracking=args.tracking_branch),
              file=sys.stderr)
        return 2
    return None


def _finish_holder_remote(args, repository: str, topic: str, local: bool,
                          reuse: bool) -> None:
    """Set the holder's topic and print the members' credential NOTE and the
    Free-plan secrets note.

    Neither applies to a local (no-network) remote. Split from `cmd_init`
    for #136.

    THE CREDENTIAL NOTE IS ABOUT THE MEMBERS, AND EVERY HOLDER GETS IT (#913,
    L2-95). The `validate` workflow's default GITHUB_TOKEN cannot read a
    private or internal member whatever the holder is, so a public holder
    needs the App or the PAT as much as a private one. The NOTE was printed
    only for a holder that is private or internal, in words that gave the
    holder's visibility as the reason: a public holder whose members are
    private was never told, and its `validate` check then could not check
    them out. `add`, which knows each member, is not this function's.

    BY THE HOLDER AS IT STANDS (#660). The holder is the repository whose
    `validate` workflow reads the secrets. One this run created has the
    run's `--visibility`; one `--reuse-empty-repo` reused keeps its own,
    which `--visibility` never touched, and GitHub is asked for it
    (`repository_visibility`). Both lines went by `--visibility` alone, so
    a public holder reused under the default `private` was called private
    and given the Free-plan hint. A reused holder whose visibility GitHub
    does not give is `ROOT_VISIBILITY_UNREAD`: whether it is private is the
    very question that went unanswered.

    NO MEMBER IS NAMED THAT DOES NOT EXIST (#660). `init` mounts none, and
    `add` mounts a member of any visibility, so the NOTE's "and its members
    will be too" said what nothing here decides, and the hint's "<holder>
    and its members are private" named members there are not. The hint
    names the holder alone, as the scaffold's and adopt's name the root
    (#602), and the NOTE says which members need the credential: those added
    later that are private or internal.
    """
    if local:
        return
    run(["gh", "repo", "edit", repository, "--add-topic", topic])
    print(f"  topic     {topic} set on the holder")
    visibility = args.visibility
    if reuse:
        # `gh` has just set the topic, so an `OSError` here is no missing
        # `gh` to refuse, only a visibility this run could not read.
        try:
            visibility = repository_visibility(repository)
        except OSError:
            visibility = None
    print("NOTE a member you add that is, or has a leg that is, private or "
          f"internal needs a way for {repository}, public or not, to read "
          "it — a GitHub App (SHAPE_LEGS_APP_ID + SHAPE_LEGS_APP_PRIVATE_KEY, "
          "preferred) or a SHAPE_LEGS_TOKEN PAT with contents:read on the "
          "members AND their legs — or the `validate` check cannot check "
          "that member out.")
    note = free_plan_secrets_note(args.org, repository, visibility)
    if note:
        print(note)


def _print_next_steps(args, work: Path, folder: Path | None) -> None:
    """The NEXT STEPS block `init` ends with.

    Split from `cmd_init` for #136. A BRANCH FIRST (#487): the holder stands
    on its tracking branch, where `add` refuses to commit, so the block
    opens with the `git switch -c` that makes a branch for it. Its member
    is `<Project>`, the one placeholder the `--member` under it says
    (#607); `add`'s own refusal names the branch lowercased.

    ONE COMMAND A LINE, `cd` apart from `make siblings`: Windows PowerShell
    5.1, the shell `setup-project.py` documents, rejects `&&` between two
    statements, and these lines are quoted for the shell of the host (#486).

    `--work-dir` makes no family folder, and `make siblings` stops before it
    clones anything in a holder whose parent folder is not named after the
    family (#543), so there the block says so instead of promising clones.
    """
    switch = shell_line(["git", "-C", work, "switch", "-c"])
    beside = ("`make siblings` then puts each member's WORKING clone\n"
              "beside the holder, in the family folder, on its tracking "
              "branch.")
    where = f"family folder  {folder if folder is not None else work.parent}"
    if folder is None and work.parent.name != work.name:
        # --work-dir MAKES NO FAMILY FOLDER, and `make siblings` clones
        # nothing until the holder sits in one (#543), so none is promised.
        beside = ("--work-dir made no family folder, so `make siblings`\n"
                  "clones nothing: it prints the `mv` that puts the holder "
                  f"in a folder\nnamed {work.name}, and stops until it is "
                  "there.")
        where = f"family folder  none: {work.parent} is not named {work.name}"
    print(f"""
NEXT STEPS

    {switch} family/add-<Project>
    {_add_command(work, args.org)}
    cd {shell_quoted(work)}
    make siblings

`add` mounts the member at {MEMBERS_DIR}/<Project>, records its pin, and
writes ONE commit on that branch: it refuses {args.tracking_branch}, the
holder's tracking branch. Push the branch as its NEXT line says and land it
as a pull request. {beside}

TWO COPIES OF EVERY MEMBER, on purpose: pinned and DETACHED inside the holder
under {MEMBERS_DIR}/ (what `make bootstrap` and `make validate` read), and a
working clone BESIDE the holder — that second one is where you work, and
`family.py bump` is how the family follows it.

{where}
holder         {work}
""")


# ---------------------------------------------------------------------------
# What `init` may write into the holder's manifest (#307)
# ---------------------------------------------------------------------------
#
# `init` renders `templates/family-root/family.yaml` from values a person typed
# (`--id`, `--org`, `--name`, `--created-by`, `--created-on`,
# `--tracking-branch`) and pushes the result. The holder then reads it with two
# programs of its own: its YAML reader (`scripts/repo_shape.py`) and its
# `scripts/validate-family.py`, which `make validate` and the `validate`
# workflow run FIRST. `init` asked neither of them anything, so a value the
# holder could not hold was found by the holder's own gate, after the
# repository existed and was pushed, and `init` cannot be run again over a
# pushed holder (`family-remote-exists`, and there is no --force):
#
#   * REFUSED BY THE VALIDATOR. `--created-by ' '`, `--created-on 20261011`,
#     `2026-W41-6` or `tomorrow`, `--name 'Contoso Group'`: all exit 0, and the
#     holder is red from its first commit.
#   * READ BACK AS SOMETHING ELSE. The template writes `id`, `org`,
#     `created_on`, `visibility` and `tracking_branch` bare, so `--id null`,
#     `--org null`, `--created-on 20261011` and `--tracking-branch true`,
#     `007` or `null` became None, True and 7. The validator judges the first
#     three; it has no rule about `tracking_branch` at all, so that one was
#     SILENT: the holder sat on a branch named `true` while its manifest said
#     `True`, and `update-shape.py apply --branch` printed `gh pr create
#     --base True`.
#
# THE CURE IS #261'S, FOR THE FAMILY: ask, before anything is created and under
# `--dry-run` alike, and refuse. `family_manifest_misreads` renders each
# template line that carries one of the values, reads that line with the
# holder's reader and refuses a value that does not come back as the same
# text; `family_manifest_invalid` renders the whole `family.yaml`, reads it, and
# runs the validator the template ships (LOADED from that file, never
# re-implemented) over it. Both read the TEMPLATE, so a placeholder the
# template quotes is asked as the quoted line it is: the day the templates quote
# `id:` and `tracking_branch:` (#259), those values read back and the first
# question refuses nothing, with no edit here.
#
# REFUSED, NOT QUOTED OR CORRECTED. A value the manifest cannot hold has no
# spelling that is the same value (`007` as a branch is a legal git name and a
# different number), and rewriting a person's value for them is the silent
# retyping this refuses. Whether the templates quote is #259's decision, and
# one decision for every tool that renders them.
#
# THIS IS THE SMALLEST VERSION THE FAMILY NEEDS, and not `shape_materialize`'s:
# the questions there (`manifest_misreads`, `manifest_invalid`, #261) are
# written for the assembly root's `project.yaml` and its `validate-manifest.py`.
# #314 added them first, and this change landed second without unifying them,
# so the two sets of helpers exist side by side. Unifying them is an item on
# tracking issue #459's checklist: the two differ only in the template, the
# validator's entry point and the sentence that names the file.

#: The holder's template directory, and the one validator in it these
#: questions ask. `materialize_family_root` reads the same directory.
FAMILY_TEMPLATE = SHAPE_ROOT / "templates" / "family-root"
FAMILY_VALIDATOR = "scripts/validate-family.py"

#: The names this module asks of the validator: the report it fills and the
#: function that makes every FINDING of the envelope. `family.yaml`'s members,
#: gitlinks and shape copies are not asked: there are none yet.
FAMILY_VALIDATOR_ASKS = ("Report", "_check_envelope")

#: The templated files the holder's reader reads: the materializer's own list
#: of what it renders, so a templated YAML file added there is asked about
#: here without an edit.
FAMILY_TEMPLATED_YAML = tuple(rel for rel in FAMILY_TEMPLATED
                              if rel.endswith(".yaml"))

#: How a refusal names each value the manifest records.
MANIFEST_FLAGS = {
    "FAMILY_ID": "--id", "FAMILY_NAME": "--name", "ORG": "--org",
    "CREATED_BY": "--created-by", "CREATED_ON": "--created-on",
    "VISIBILITY": "--visibility", "TRACKING_BRANCH": "--tracking-branch",
}

#: Which placeholder carries the value a finding of the validator is about,
#: for the ones `init` is handed a value for. A finding with no row is still
#: refused, in the validator's words and without a flag to point at.
FINDING_PLACEHOLDER = {
    "family-id": "FAMILY_ID", "family-name": "FAMILY_NAME",
    "naming-unclassified": "FAMILY_NAME", "naming-not-a-family": "FAMILY_NAME",
    "family-org": "ORG", "family-created-by": "CREATED_BY",
    "family-created-on": "CREATED_ON", "family-visibility": "VISIBILITY",
}

_FINDING_RE = re.compile(r"^FINDING (?P<code>[a-z0-9-]+): (?P<detail>.*)$",
                         re.DOTALL)

#: The validator modules already loaded, by the file they were loaded from.
_VALIDATORS: dict = {}


def _validator_unusable(what: str, why: str) -> Refusal:
    """The refusal for a template validator that cannot be asked, and not a
    traceback. It is a defect of the copy of the standard that was run and not
    of any value; nothing was created, because the question is asked before
    anything exists, and a validator that cannot answer lets no manifest
    through unasked."""
    return Refusal(
        "family-validator-unusable",
        f"templates/family-root/{FAMILY_VALIDATOR}, the validator this run "
        f"asks about the manifest it would write, {what}: {why}",
        "Remediation: this is a defect in the copy of this standard you ran, "
        "not in your values: the file is missing, unreadable or broken "
        "there, and nothing was created. Restore it from the standard's "
        "repository, or reinstall the standard, and run again.")


def family_validator(template_dir: Path = FAMILY_TEMPLATE):
    """The holder's own `scripts/validate-family.py`, as a module.

    LOADED FROM THE TEMPLATE IT IS COPIED FROM, so what is asked is the rule
    the holder will apply and no second spelling of it exists. By path,
    because the filename has a hyphen and cannot be imported by name. The
    directory the validator puts at the front of `sys.path` for its own
    imports is taken off again, and NO BYTECODE IS WRITTEN: importing a source
    file makes CPython write `scripts/__pycache__/` beside it, and this file
    is a TEMPLATE, in a tree every reader of it then meets.
    """
    path = Path(template_dir) / FAMILY_VALIDATOR
    module = _VALIDATORS.get(path)
    if module is None:
        spec = importlib.util.spec_from_file_location(
            "openreposhape_validate_family", path)
        module = importlib.util.module_from_spec(spec)
        saved_path, saved_flag = list(sys.path), sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            spec.loader.exec_module(module)
        except (Exception, SystemExit) as exc:  # missing, unreadable, broken
            raise _validator_unusable(
                "could not be loaded", f"{type(exc).__name__}: {exc}"
            ) from exc
        finally:
            sys.path[:] = saved_path
            sys.dont_write_bytecode = saved_flag
        for name in FAMILY_VALIDATOR_ASKS:
            if not hasattr(module, name):
                raise _validator_unusable(
                    "could not be used", f"it has no `{name}`")
        _VALIDATORS[path] = module
    return module


def _reading_in_words(reading) -> str:
    """What the holder's reader made of a value, as a sentence says it."""
    if isinstance(reading, YamlError):
        return f"nothing at all, because it refuses the line ({reading})"
    if reading is None:
        return "no value at all"
    if isinstance(reading, bool):
        return "the boolean " + ("true" if reading else "false")
    if isinstance(reading, (int, float)):
        return f"the number {reading!r}"
    if isinstance(reading, str):
        return f"the text {reading!r}"
    return "a list" if isinstance(reading, list) else "a mapping"


def _line_shown(line: str) -> str:
    """`line` in backticks, or as Python spells it where it holds a character
    a terminal shows as something else, so that one finding stays one line."""
    return f"`{line}`" if line.isprintable() else repr(line)


def _reading_of(rendered: str):
    """What the holder's reader makes of the one `key: value` line
    `rendered`: the value, the `YamlError` it raised, or the whole answer when
    it is not one key with one value (a value with a line break in it can
    carry a second key into the file)."""
    try:
        parsed = parse_yaml(rendered.lstrip() + "\n")
    except YamlError as exc:
        return exc
    if isinstance(parsed, dict) and len(parsed) == 1:
        return next(iter(parsed.values()))
    return parsed


def _misread_rows(values: dict, what: dict, template_dir: Path
                  ) -> dict[str, list[tuple]]:
    """For each placeholder of `what` whose value the holder's reader would
    not read back as that same text: `(rendered line, reading)` for each
    template line that carries it."""
    found: dict[str, list] = {}
    for rel in FAMILY_TEMPLATED_YAML:
        text = (Path(template_dir) / rel).read_text(encoding="utf-8")
        for line in text.splitlines():
            keys = [token[2:-2] for token in PLACEHOLDER_RE.findall(line)]
            if (len(keys) != 1 or keys[0] not in what
                    or keys[0] not in values
                    or line.lstrip().startswith("#")):
                continue
            key, value = keys[0], str(values[keys[0]])
            rendered = render(line, {key: value}, rel).lstrip()
            reading = _reading_of(rendered)
            if not (isinstance(reading, str) and reading == value):
                found.setdefault(key, []).append((rendered, reading))
    return found


def family_manifest_misreads(values: dict, what: dict,
                             template_dir: Path = FAMILY_TEMPLATE
                             ) -> list[str]:
    """A sentence for each value the holder's reader would read back as
    anything but that same text; `[]` when every one reads back.

    `values` is the substitution table; `what` names the placeholders to ask
    about and how a refusal calls each (`{"FAMILY_ID": "--id"}`). Each
    template line that carries exactly one of them is rendered with the
    value, as `render` writes it, and read as the holder reads it, so a value
    the template quotes is asked as the quoted line it is.
    """
    return [
        f"{what[key]} is {str(values[key])!r}, which is written "
        + " and ".join(f"into family.yaml as {_line_shown(line)}"
                       for line, _ in rows)
        + ", where the holder's own YAML reader reads it back as "
        + f"{_reading_in_words(rows[0][1])} and not as that text."
        for key, rows in _misread_rows(values, what, template_dir).items()]


def _sentences_of(findings: list[str], values: dict, what: dict) -> list[str]:
    """The FINDINGs of the validator as sentences: one for each value `init`
    was handed, naming it and holding every finding about it, and one for each
    finding that is about none of them."""
    by_value: dict[str, list[str]] = {}
    sentences: list[str] = []
    for finding in findings:
        match = _FINDING_RE.match(finding)
        if match is None:
            sentences.append(finding)
            continue
        code, detail = match.group("code"), match.group("detail")
        said = f"{code}: {detail if detail.endswith('.') else detail + '.'}"
        key = FINDING_PLACEHOLDER.get(code)
        if key in what and key in values:
            by_value.setdefault(key, []).append(said)
        else:
            sentences.append("the manifest this run would write is one the "
                             f"holder's own validate-family.py refuses: {said}")
    return [f"{what[key]} is {str(values[key])!r}, which the holder's own "
            f"validate-family.py refuses: {' '.join(said)}"
            for key, said in by_value.items()] + sentences


def family_manifest_invalid(values: dict, policy: NamingPolicy, what: dict,
                            template_dir: Path = FAMILY_TEMPLATE
                            ) -> list[str]:
    """A sentence for each FINDING the holder's own validator would make of
    the `family.yaml` these `values` render; `[]` when it would pass.

    The WHOLE manifest is rendered and read, so a rule about how one value
    relates to another is asked as the holder asks it. `values` must be the
    complete table and `policy` the naming policy the holder carries a copy
    of. The validator's `Report` is asked for its findings alone: its notes
    are what it says when nothing is wrong.
    """
    template = (Path(template_dir) / MANIFEST).read_text(encoding="utf-8")
    try:
        manifest = parse_yaml(render(template, values, MANIFEST))
    except YamlError as exc:
        return ["the manifest this run would write is a file the holder's "
                f"own YAML reader refuses: {exc}."]
    if not isinstance(manifest, dict):
        return ["the manifest this run would write is not a mapping, which "
                "is what the holder's own YAML reader makes of it."]
    validator = family_validator(template_dir)
    # THE VALIDATOR'S OWN DEFECT, NEVER A FINDING. One that raises, one that
    # EXITS (a `sys.exit(0)` would end this run with a zero, having printed
    # and created nothing) and one whose `Report` has no `findings`, or whose
    # findings are not text, did not answer, and a manifest it did not answer
    # for is not one that passed.
    try:
        report = validator.Report()
        validator._check_envelope(manifest, policy, report)
        findings = list(report.findings)
    except SystemExit as exc:
        raise _validator_unusable(
            "exited when it was asked", f"SystemExit: {exc.code}") from exc
    except Exception as exc:
        raise _validator_unusable(
            "raised when it was asked", f"{type(exc).__name__}: {exc}"
        ) from exc
    for finding in findings:
        if not isinstance(finding, str):
            raise _validator_unusable(
                "answered with a finding that is not text",
                f"its type is {type(finding).__name__}")
    return _sentences_of(findings, values, what)


#: The remediation of a value the reader turns into something else, without
#: the sentence about what was or was not created, which `init` adds. WHAT IT
#: SAYS HOLDS OF EVERY VALUE THE RULE REFUSES: the holder's reader reads back
#: something other than what was typed. What that does next differs by value
#: (`--tracking-branch 2026` happens to survive, because every reader of the
#: field turns the number back into text) and is not claimed.
MANIFEST_MISREAD_REMEDIATION = (
    "Remediation: choose another value for each one named, as nothing here "
    "will retype it for you. family.yaml writes a value like these unquoted, "
    "so the holder's own YAML reader takes `null` and `~` for no value, "
    "`true` and `false` for booleans, and `007`, `2026` or `20261011` for "
    "numbers: what it reads back is not what was typed. A value the reader "
    "takes for text (`contoso`, `release-2026`, `v2`) passes. A branch `007` "
    "reads back as the branch `7`, and `2026` happens to work today because "
    "the tools that read it turn the number back into text, but it is still "
    "a number to the holder's reader and not a name.")
MANIFEST_INVALID_REMEDIATION = (
    "Remediation: choose a value the holder's own validate-family.py "
    "accepts; the words after each value are the validator's own. A holder "
    "it refuses is red from its first commit, because `make validate` and "
    "the `validate` workflow run it first, and `init` cannot be run again "
    "over a pushed holder: there is no --force.")


def _manifest_flags(args) -> dict:
    """`MANIFEST_FLAGS`, with a value no flag supplied named by where it came
    from, so that a refusal does not point at a flag nobody typed."""
    flags = dict(MANIFEST_FLAGS)
    for key, flag, given, source in (
            ("FAMILY_ID", "--id", args.id, FAMILY_ID_DERIVED_FROM),
            ("FAMILY_NAME", "--name", args.name, "--family"),
            ("CREATED_BY", "--created-by", args.created_by,
             "GIT_AUTHOR_NAME or `git config user.name`"),
            ("CREATED_ON", "--created-on", args.created_on, "today")):
        if not given:
            flags[key] = f"{flag} (not given, so {source})"
    return flags


def refuse_unholdable_manifest(args, values: dict,
                               template_dir: Path = FAMILY_TEMPLATE) -> None:
    """The manifest this run would write is one the holder can hold, or this
    refuses (#307), before a work directory, a remote or a repository exists
    and under `--dry-run` alike.

    `values` is the whole substitution table, so the holder's own YAML reader
    and `validate-family.py` are asked about the `family.yaml` `init` is about
    to write. A value the reader turns into something else (`--id null`,
    `--tracking-branch 007`) is `family-manifest-misread`, and comes first
    and alone, because the validator's finding about it (`id is None`) is its
    consequence; one the validator refuses (`--created-by ' '`, `--name
    'Contoso Group'`) is `family-manifest-invalid`, in the validator's words.
    """
    flags = _manifest_flags(args)
    nothing = " Nothing was created, and `--dry-run` refuses the same."
    problems = family_manifest_misreads(values, flags, template_dir)
    if problems:
        raise Refusal("family-manifest-misread", " ".join(problems),
                      MANIFEST_MISREAD_REMEDIATION + nothing)
    problems = family_manifest_invalid(
        values, NamingPolicy.load(NAMING_POLICY), flags, template_dir)
    if problems:
        raise Refusal("family-manifest-invalid", " ".join(problems),
                      MANIFEST_INVALID_REMEDIATION + nothing)


def cmd_init(args) -> int:
    family, family_id, topic = _checked_family_identity(args)
    created_by = _creator_name(args)
    local, repository, url = _holder_remote(args, family)
    _refuse_an_unwritable_clone_url(local, url)
    shape_commit, shape_tree = _shape_snapshot()
    values = _template_values(args, family, family_id, repository, url,
                              created_by, shape_commit, shape_tree)
    # THE HOLDER MUST BE ABLE TO HOLD WHAT IS ABOUT TO BE WRITTEN (#307): the
    # manifest is rendered from this very table and put through the holder's
    # own reader and `validate-family.py`, before the plan is printed, so a
    # `--dry-run` refuses what the real run would, and before `gh repo create`.
    refuse_unholdable_manifest(args, values)
    # AND THE IDENTITY GIT WILL MAKE THE FIRST COMMIT AS (#688), asked of git
    # here, before the landing and the plan, so `--dry-run` refuses it too.
    _refuse_an_unusable_commit_identity()

    folder, holder = _checked_landing(args, family)
    _print_init_plan(values, repository, url, shape_commit, shape_tree,
                     folder, holder, local, topic, args.reuse_empty_repo)
    # ONE QUESTION, ASKED BY BOTH RUNS BEFORE ANYTHING IS MADE (#537, #609):
    # every folder `init` makes and the holder it writes, then whether the
    # holder's remote exists, with the real run's own `_checked_reuse`. It
    # READS: the folders, then a `gh repo view` and a commit listing, or the
    # bare repository on disk with `--local-remote-dir`. So `--dry-run`
    # refuses what the real run refuses, and the real run asks it all
    # before `_prepare_landing_dir` makes the family folder: a refusal left
    # that folder empty behind it (#537's first line).
    _refuse_unmakeable_landing(args, folder, holder, local)
    reuse = _checked_reuse(args.reuse_empty_repo, local, url, repository)
    if args.dry_run:
        print("\n--dry-run: nothing was created.")
        return 0

    work = _prepare_landing_dir(folder, holder)
    _create_holder_remote(args, values, local, url, repository, reuse)

    code = _create_holder_worktree(args, work, values, shape_commit,
                                   repository, url)
    if code is not None:
        return code
    head = git_out(["rev-parse", "HEAD"], cwd=work)[:12]
    print(f"  holder    {head} -> {url}")
    _finish_holder_remote(args, repository, topic, local, reuse)
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


#: `str.translate`'s table for folding ASCII letters and nothing else, as
#: `_index_entries` folds a name's bytes and as git's own `icase` folds.
ASCII_FOLD = {upper: upper + 32 for upper in range(ord("A"), ord("Z") + 1)}

#: Where `_members_spellings` found a path, as its refusal says it (#362,
#: #363, #364).
IN_INDEX = "in the index"
IN_HEAD_ONLY = "in HEAD and no longer in the index"
#: A section of `.gitmodules` that gives a member another spelling of its
#: row's path, where HEAD records the member's gitlink at that path and the
#: index holds it nowhere: its removal staged (#761, rv685's candidate 1).
IN_GITMODULES = "in .gitmodules, its gitlink's removal staged"
#: A section of `.gitmodules` that gives a member another spelling of its
#: row's path, where the index records the member's gitlink at that path
#: already, as a hand edit or #646's old move back leaves it (#840).
IN_SECTION = "in .gitmodules, its gitlink at its row's path"
#: A section of `.gitmodules` that gives another spelling of a row's path
#: beside the section that gives that path itself, as `git rm --cached` of
#: a submodule a hand added there leaves it, or a hand edit (#840, rv865's
#: MUST 1).
BESIDE_SECTION = "in .gitmodules, beside the section giving its row's path"
ON_DISK = "on disk and untracked"

#: What the remedy does to a path `_members_spellings` found, in the order
#: `_spellings_refusal` says them. What HEAD holds and the index no longer
#: does is a pending change, committed first. What the index holds is renamed
#: with `git mv` where it is on disk in its own spelling, with `git mv
#: --sparse` where the sparse rules leave it out, and otherwise taken out of
#: the index, which touches no file, as #318 takes out a variant of the
#: mount path. A `members/` renamed with `git mv` is renamed back with it,
#: whole, in two steps through a free name (#685). A member's own gitlink,
#: held only under another spelling of its row's path, is moved back to that
#: path in the index alone (#646), after what the index holds at or under
#: that path, or at `members` itself, is set aside (#761), with `git mv`,
#: `git mv --sparse` or `git rm -r --cached` as the same rule names what the
#: index holds (Codex's P2 1 on #828). What is on disk and untracked is
#: moved out of the way, but for a checkout, which a move would leave
#: pointing nowhere, and which is deleted by hand (#761); a `members/` a
#: hand renamed is moved back. #840 adds five: a symbolic link at a
#: spelling the index holds entries under, moved out of the way FIRST,
#: since git goes through it (`LINK_OUT`); a checkout git does not track
#: inside a directory a `git mv` or `mv` below moves, deleted by hand before
#: that move (`CHECKOUT_FIRST`); a gitlink at a case variant of a row's path
#: beside the member's own gitlink at that path, a second path to its
#: directory, taken out of the index alone wherever it is, as the gate's own
#: line takes one out, since `git mv` would carry the section that gives its
#: path along (`UNSTAGE_SECOND`, rv865b's MUST 1); a section of
#: `.gitmodules` pointed back at its row's path where the index records the
#: gitlink there already and no section gives that path (`POINT_BACK`), or
#: taken out, every key it holds, where one does (`TAKE_OUT`); and an
#: UNMERGED entry in the way of a move back, taken out of the index, every
#: stage, with what of it is on disk moved out of the way (`ASIDE_UNMERGED`,
#: `ASIDE_UNMERGED_MV`), since `git mv` refuses a conflicted entry.
LINK_OUT = "mv link"
COMMIT = "git commit"
CHECKOUT_FIRST = "by hand, first"
RENAME = "git mv"
RENAME_SPARSE = "git mv --sparse"
UNSTAGE = "git rm -r --cached"
UNSTAGE_SECOND = "git rm -r --cached second"
POINT_BACK = "git config -f"
TAKE_OUT = "git config -f --unset-all"
RENAME_BACK = "git mv back"
ASIDE = "git mv aside"
ASIDE_SPARSE = "git mv --sparse aside"
ASIDE_OUT = "git rm -r --cached aside"
ASIDE_UNMERGED = "git rm -r --cached unmerged aside"
ASIDE_UNMERGED_MV = "git rm -r --cached and mv unmerged aside"
RESTORE = "git update-index"
MOVE = "mv"
CHECKOUT = "by hand"
MOVE_BACK = "mv back"
REMEDY_ORDER = (LINK_OUT, COMMIT, CHECKOUT_FIRST, RENAME, RENAME_SPARSE,
                UNSTAGE, UNSTAGE_SECOND, POINT_BACK, TAKE_OUT, RENAME_BACK,
                ASIDE, ASIDE_SPARSE, ASIDE_OUT, ASIDE_UNMERGED,
                ASIDE_UNMERGED_MV, RESTORE, MOVE, CHECKOUT, MOVE_BACK)
#: Each remedy that sets aside what is in the way of a move back (#761).
SET_ASIDE = (ASIDE, ASIDE_SPARSE, ASIDE_OUT, ASIDE_UNMERGED,
             ASIDE_UNMERGED_MV)

#: What a `--sparse` the remedy prints needs (#685). `git rm --sparse` came
#: with git 2.34. `git mv` took `--sparse` in 2.34 too, but there it still
#: says `bad source` for one entry a sparse checkout keeps off disk, which
#: is the one entry the remedy names: its `builtin/mv.c` is the same from
#: 2.34.0 to 2.37.7, and 2.38.0 is the first to look that entry up in the
#: index, and the first whose tests move one (`can move out-of-cone file
#: with --sparse`). Read from git's source, not run.
#:
#: NO OTHER WAY IS NAMED. On git 2.43, the only git run here, clearing the
#: entry's `skip-worktree` bit first (`git update-index
#: --no-skip-worktree`) leaves `git mv` saying `bad source`, since the file
#: is still off disk, and in a cone-mode sparse checkout `git rm --cached`
#: then still removes nothing. An older git may differ (2.33's `mv.c` has
#: no sparse code at all), but none was run.
#:
#: THE RULES, NOT THE BIT (#761, rv685's candidate 2). git 2.43 asks the
#: sparse-checkout rules of each path it updates, whatever its
#: `skip-worktree` bit says: an entry the rules leave out that is on disk
#: with the bit cleared is refused by a plain `git mv` (`exist outside of
#: your sparse-checkout definition`, exit 1), file or directory, and taken
#: by `git mv --sparse`; one off disk with the bit cleared is refused by
#: `git rm --cached` the same way and taken by `git rm --cached --sparse`;
#: and `git rm --cached --ignore-unmatch` passes over such a gitlink with
#: exit 0, as it does one marked. So each `--sparse` is printed where the
#: rules leave the entry out (`_sparse_rules_exclude`), as well as where it
#: is marked. A gitlink on disk as a directory is the one entry plain `git
#: mv` takes there, and `--sparse` takes it too. Measured on git 2.43. A git
#: that cannot answer `check-rules` leaves the bit alone to decide, as
#: before.
SPARSE_MV_GIT = "which needs git 2.38 or later"
SPARSE_RM_GIT = "which needs git 2.34 or later"
#: What `-f` on a `git rm --cached` of a gitlink does, said wherever one is
#: printed with it: the move back's (#761) and a second path's (rv865b's
#: round-2 MUST 1), as the validator's `FORCED_SAID` says it (#839).
FORCED_SAID = ("whose -f takes out a staged gitlink whose checkout has moved "
               "on or holds a file git does not track, which git rm otherwise "
               "refuses, and with --cached touches no file")

#: The name a `members/` renamed with `git mv` is renamed back through, or
#: the first of its numbered variants that nothing holds (#685).
RENAMING = "members.renaming"


class Spelled(NamedTuple):
    """A path at or under a spelling of `members/` other than `members/`
    itself, or at or under a case variant of the mount path, as
    `_members_spellings` found it: `name` as git or the disk spells it,
    `kind` (`a file`, `a submodule`, `a symlink`, `a directory`), `where`
    (`IN_INDEX`, `IN_HEAD_ONLY`, `IN_GITMODULES` or `ON_DISK`), `target`,
    the path its remedy acts on, `mount`, whether it is at or under a case
    variant of the mount path itself, `remedy`, which of `REMEDY_ORDER` acts
    on it, and `committed`, whether HEAD holds it too, so that taking it out
    of the index is a change to commit. `sparse` says, for `UNSTAGE`, that
    the sparse rules leave it out, so that `git rm --cached` takes it only
    with `--sparse` (#761), and for `UNSTAGE_SECOND` that they leave it out
    or a sparse checkout marks it, either of which needs `--sparse` too
    (rv865b's MUST 1).

    A MEMBER'S OWN GITLINK (`RESTORE`, #646) has its row's path as `target`,
    `committed` says whether the move leaves anything to commit, `recorded`
    is the commit it records, at which the move records it back, and
    `sparse` whether a sparse checkout keeps it off disk (`skip-worktree`)
    or its rules leave it out, either of which `git rm --cached
    --ignore-unmatch` passes over without a word unless it is given
    `--sparse` too; `recorded` is empty, and `sparse` false, for every other
    remedy but `UNSTAGE` and `ASIDE_OUT`. `sections` names each section of
    `.gitmodules` that gives the member another spelling of its row's path,
    as a `git mv` of its mount leaves it, which the move points back at that
    path (#761); empty for every other remedy. One found `IN_GITMODULES` is
    a member HEAD records at its row's path and the index holds nowhere,
    named by the path its section gives, and moved back at HEAD's commit.
    `forced` says the removal takes `-f`: the index stages the variant at a
    commit HEAD does not record there, and a checkout is on disk at it,
    which `git rm --cached` refuses wherever that checkout has moved on or
    holds a file it does not track (#761), and the same of a second path
    taken out of the index (`UNSTAGE_SECOND`, rv865b's round-2 MUST 1).
    `checkout`, for `UNSTAGE_SECOND` alone, says that a checkout `git
    submodule add` or `git mv` made is on disk at it in its own spelling,
    which the remedy names to delete by hand in the same round, before any
    update (rv865b's round-2 SHOULD 1).

    WHAT IS SET ASIDE BEFORE THE MOVE BACK (`SET_ASIDE`, #761) is an entry
    the index holds at or under a row's path, or at `members` itself, which
    `git update-index` would replace or fail on: renamed with `git mv`
    (`ASIDE`) where it is on disk as the index holds it, with `git mv
    --sparse` (`ASIDE_SPARSE`) where a sparse checkout needs that, else
    taken out of the index (`ASIDE_OUT`), `sparse` saying that its rules
    leave it out, so that `git rm --cached` takes it only with `--sparse`
    (Codex's P2 1 on #828); `target` is the entry itself.

    WHAT A `members/` RENAMED WITH `git mv` HOLDS (`RENAME_BACK`, #685) has
    that spelling as `target`, `committed` says whether renaming it back
    leaves anything to commit, `through` is the free name it is renamed
    back through, and `put_back` says whether the disk lacks this entry,
    which is put back first, since `git mv` of a directory refuses any
    entry under it that is not on disk (`bad source`); `through` is empty,
    and `put_back` false, for every other remedy.

    #840's FOUR. A section found `IN_SECTION` (`POINT_BACK`) is named by the
    path it gives, `kind` `a section`, with its row's path as `target`, its
    name in `sections`, and `committed` saying whether HEAD's section gives
    another path. One found `BESIDE_SECTION` (`TAKE_OUT`) is named by the
    path it gives, which is its `target` too, with its name in `sections`,
    every key it holds in `keys`, and `committed` saying whether HEAD holds
    a section of that name. A symbolic link moved out of the way first
    (`LINK_OUT`) and a checkout deleted before a move takes it
    (`CHECKOUT_FIRST`) are found `ON_DISK`, each its own `target`. An
    unmerged entry set aside (`ASIDE_UNMERGED`, or `ASIDE_UNMERGED_MV` where
    it is on disk as the index holds it) is its own `target` too."""

    name: str
    kind: str
    where: str
    target: str
    mount: bool
    remedy: str
    committed: bool = False
    recorded: str = ""
    sparse: bool = False
    through: str = ""
    put_back: bool = False
    sections: tuple[str, ...] = ()
    forced: bool = False
    keys: tuple[str, ...] = ()
    checkout: bool = False


def _folded(name: str) -> str:
    """`name` with ASCII case folded, as git's `icase` folds it."""
    return name.translate(ASCII_FOLD)


def _shown(name: str) -> str:
    """`name`, read from git or a listing with `surrogateescape`, as a
    refusal shows it: a byte that is not UTF-8 as U+FFFD, never as a lone
    surrogate a stream may not encode."""
    return name.encode("utf-8", "surrogateescape").decode("utf-8", "replace")


def _spelled_target(name: str, project: str,
                    occupied: frozenset[str] = frozenset(),
                    rows: frozenset[str] = frozenset()
                    ) -> tuple[str, bool] | None:
    """`(the path a remedy acts on, whether it is at or under a case variant
    of members/<project>)` for a path `name`, `/`-separated as git spells
    it, or None when nothing about `name` is a case variant.

    ONE ENTRY OF THE OTHER SPELLING AT A TIME, NEVER THAT SPELLING ITSELF
    (#574's review, B1). On macOS and Windows `Members` and `members` are one
    directory, holding the members' own checkouts, so a remedy that renamed
    `Members` would take every member with it. Under a spelling of `members`
    other than `members` itself the remedy acts on the entry directly below
    it (`Members/README`, `Members/docs`, `Members/IRQS`), or on the spelling
    only where that is the entry, a file or link named `Members`. Where that
    entry folds to a name `members/` itself tracks (`occupied`, folded), it
    is that name's directory on such a disk, so the remedy acts on `name`
    alone. Under `members/` itself only a case variant of the mount path is
    one (`members/irqs`), and its remedy acts on that, and so is a case
    variant of the path of a `members:` row (`rows`, its exact paths) that
    is no row's own path (`members/irrs` beside the row `members/IRRS`,
    #840): one path with it on macOS and Windows, which a clone there
    cannot hold beside the member's checkout. The mount path itself,
    `members/<project>` exactly, is no variant: what is there is
    `member-path-taken`'s first two questions."""
    first, _, rest = name.partition("/")
    if _folded(first) != MEMBERS_DIR:
        return None
    second = rest.partition("/")[0]
    mount = bool(rest) and _folded(second) == _folded(project)
    if first != MEMBERS_DIR:
        if not rest:
            return first, False
        if not mount and _folded(second) in occupied:
            return name, False
        return f"{first}/{second}", mount
    here = f"{first}/{second}"
    if mount and second != project or not mount and rest and (
            here not in rows
            and _folded(here) in {_folded(row) for row in rows}):
        return here, mount
    return None


def _disk_kind(path: Path) -> str:
    """What is at `path`, not following a link, as a refusal names it."""
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode):
        return "a symlink"
    return "a directory" if stat.S_ISDIR(mode) else "a file"


def _members_on_disk(root: Path) -> dict[str, tuple[str, list[str] | None]]:
    """`{spelling: (kind, its entries)}` for every spelling of `members` the
    holder's root holds on disk, `members` itself included, READ BY LISTING
    DIRECTORIES (#364). `kind` is `_disk_kind`'s; the entries are the
    directory's own names, through a link, none for a file, and None for a
    directory that cannot be listed.

    `os.path.lexists(root / path)` was the question, and it answers as the
    disk resolves a name: exactly on Linux, in any case on macOS and
    Windows. So an untracked `Members/<Project>` was refused there and the
    member mounted beside it on Linux. A listing hands back each name in the
    spelling the disk keeps, on every disk: the root is listed for every
    spelling of `members`, ASCII case folded, and each of those for its
    entries, one level at a time and never through a pathspec.
    `_members_dir_on_disk` then says which of them, if any, is `members/`
    itself on this disk.
    """
    found: dict[str, tuple[str, list[str] | None]] = {}
    for name in sorted(os.listdir(root)):
        if _folded(name) != MEMBERS_DIR:
            continue
        top = root / name
        entries: list[str] | None = []
        if top.is_dir():
            try:
                entries = sorted(os.listdir(top))
            except OSError:
                entries = None
        found[name] = (_disk_kind(top), entries)
    return found


def _members_dir_on_disk(
        root: Path, on_disk: dict[str, tuple[str, list[str] | None]]
        ) -> str | None:
    """The spelling under which the holder's root keeps `members/` ITSELF
    on this disk, from `_members_on_disk`'s listing: `members` where it is
    listed; else the one directory listed under another spelling that IS
    `members/` here (#574's review, B1, and Codex's P2 there); else None.

    THE ALIAS IS ASKED, NEVER GUESSED. A checkout on macOS or Windows of a
    holder that held `Members/README` beside its members makes ONE directory
    for both, spelled `Members` because that entry sorts first, and it holds
    the members' own checkouts. There `members` resolves to it:
    `os.path.isdir` of `members` is true and `os.path.samefile` names the
    same directory. On Linux `members` is not there at all, whatever
    `Members` holds (a `members/` a hand renamed, a human's own folder), so
    that `Members` is a variant like any other. A link is never the alias:
    it is named, and what it points at is not entered."""
    if MEMBERS_DIR in on_disk:
        return MEMBERS_DIR
    canonical = root / MEMBERS_DIR
    for name, (kind, _) in on_disk.items():
        try:
            if (kind == "a directory" and os.path.isdir(canonical)
                    and os.path.samefile(canonical, root / name)):
                return name
        except OSError:
            continue
    return None


def _on_disk_as_named(root: Path, name: str, directory: bool) -> bool:
    """Is `name` on disk IN THAT SPELLING, a directory where `directory`
    says so and no directory where it does not? Each component is looked up
    in its parent's listing, exactly, so a disk that folds case cannot
    answer for another entry: on macOS an index entry `Members` (a file) is
    not the holder's `members/` directory, and `git mv` of it would move
    that directory and every member in it. A link is no directory here, and
    nothing BEYOND a link is on disk in the holder (#840): it is where the
    link points, which `LINK_OUT` moves out of the way first."""
    here = root
    for depth, part in enumerate(name.split("/")):
        try:
            if part not in os.listdir(here) or depth and os.path.islink(here):
                return False
        except OSError:
            return False
        here = here / part
    return stat.S_ISDIR(here.lstat().st_mode) == directory


def _skip_worktree(root: Path) -> set[str]:
    """Every index entry a sparse checkout keeps off disk (`git ls-files
    -t`'s `S`), by its name as `_index_records` decodes it. `git mv` of one
    says `not under version control`, and `git rm --cached` refuses it as
    outside the sparse-checkout definition; `git mv --sparse` renames it."""
    listed = git_out(["ls-files", "-t", "-z"], cwd=root, binary=True)
    return {record[2:].decode("utf-8", "surrogateescape")
            for record in listed.split(b"\0") if record.startswith(b"S ")}


def _disk_spellings(
        root: Path, on_disk: dict[str, tuple[str, list[str] | None]],
        project: str, canon: str | None,
        gitlinks: set[str],
        rows: frozenset[str] = frozenset()) -> list[tuple[str, str, str]]:
    """`[(path, kind, remedy)]` of what the disk holds at or under a
    spelling of `members/` other than `members/` itself, or at a case
    variant of the mount path, from `_members_on_disk`'s listing; `canon` is
    `_members_dir_on_disk`'s answer, `gitlinks` every gitlink the index
    holds, and `rows` each `members:` row's path.

    - In `members/` ITSELF, under whichever spelling this disk keeps it,
      each entry that is a case variant of `<project>` (`members/irqs`,
      `Members/irqs` where `Members` is that directory), or of a row's path
      and no row's own (`members/irrs`, #840), moved.
    - A spelling that is not a directory, a link to one included, or a
      directory nobody may list, is named and moved itself: what is behind a
      link is not entered, and `members` itself as a link is not judged
      here (git's own dry run refuses it, `member-path-unaddable`).
    - A directory under another spelling, entry by entry, each moved; an
      EMPTY one holds nothing a clone or a disk could meet, and is what a
      `git mv` of its last entry leaves behind, so it is not named.
    - Where no `members/` is on disk at all and such a directory holds a
      member's checkout (`<spelling>/<name>/.git`, where the index holds the
      gitlink `members/<name>`), it is `members/` a hand renamed (Codex's P2
      on #574), and it is moved BACK; only a case variant of the mount path
      in it is moved out of the way first.
    - An entry to be moved that is a directory holding a `.git` FILE is a
      CHECKOUT, never moved (`_moved_or_kept`, #761).
    """
    found: list[tuple[str, str, str]] = []
    moved_back = False
    for name, (kind, entries) in on_disk.items():
        if name in (canon, MEMBERS_DIR):
            if kind == "a directory":
                found.extend((f"{name}/{entry}",
                              _disk_kind(root / name / entry),
                              _moved_or_kept(root / name / entry))
                             for entry in entries or ()
                             if _variant_in_members(root, name, entry,
                                                    project, rows))
            continue
        if kind != "a directory" or entries is None:
            found.append((name, kind, MOVE))
            continue
        back = canon is None and not moved_back and any(
            f"{MEMBERS_DIR}/{entry}" in gitlinks
            and os.path.lexists(root / name / entry / ".git")
            for entry in entries)
        moved_back = moved_back or back
        found.extend((f"{name}/{entry}", _disk_kind(root / name / entry),
                      _moved_or_kept(root / name / entry))
                     for entry in entries
                     if not back or _folded(entry) == _folded(project))
        if back:
            found.append((name, kind, MOVE_BACK))
    return found


def _variant_in_members(root: Path, name: str, entry: str, project: str,
                        rows: frozenset[str]) -> bool:
    """Is `entry`, listed in `members/` itself under the spelling `name`
    this disk keeps it in, one `_disk_spellings` names: a case variant of
    the mount path, or of a row's path and no row's own (`_spelled_target`,
    #840)?

    NOT WHERE THE DISK TAKES IT FOR THAT ROW'S OWN PATH (`samefile`, as
    `_members_dir_on_disk` asks of `members/`, rv865's SHOULD 1). macOS and
    Windows list a directory in the spelling it was made in, so the member's
    own checkout kept as `members/irrs` for the row `members/IRRS` is listed
    so, and that is what the move back leaves on such a disk, its closing
    guard `[ members/irrs -ef members/IRRS ]` being true there: named, it
    was refused as on disk and untracked, the member's only checkout, every
    time `add` ran. On Linux the two are two paths, and the row's is not
    there, so it is still named. A LINK IS NEVER THE ROW'S OWN, as
    `_members_dir_on_disk` never takes one for `members/`: `samefile`
    follows it, so a link `members/irrs -> IRRS` was let through on Linux,
    where `4268f804` named it (rv865b's NIT 1)."""
    spelled = _spelled_target(f"{MEMBERS_DIR}/{entry}", project, rows=rows)
    if spelled is None or spelled[1]:
        return spelled is not None
    if os.path.islink(root / name / entry):
        return True
    for row in rows:
        try:
            if _folded(row) == _folded(f"{MEMBERS_DIR}/{entry}") and (
                    os.path.samefile(root / name / entry, root / row)):
                return False
        except OSError:
            continue
    return True


def _moved_or_kept(path: Path) -> str:
    """`CHECKOUT` for a directory, not a link, that holds a `.git` FILE, a
    checkout whose store that file names by a path relative to it, as `git
    submodule add` and `git mv` write one; `MOVE` for anything else (#761).

    A PLAIN `mv` LEAVES SUCH A CHECKOUT POINTING NOWHERE (#681's N-1,
    measured for the validator with plain git): moved out of the holder,
    its `.git` file names `../../.git/modules/<path>` from a place where
    that is no store, and `git -C <new place> status` says `fatal: not a
    git repository`, so `<new name>` cannot be filled in to keep it. Its
    commits are in that store whatever becomes of it, so it is deleted by
    hand once nothing only it holds is needed. A clone of its own, whose
    `.git` is a directory, holds its commits there and is moved whole by
    the `mv`, which keeps them."""
    try:
        if stat.S_ISLNK(path.lstat().st_mode) or not path.is_dir():
            return MOVE
        return CHECKOUT if stat.S_ISREG(
            (path / ".git").lstat().st_mode) else MOVE
    except OSError:
        return MOVE


def _tree_entries(root: Path, tree: str,
                  recursive: bool = False) -> list[tuple[str, str, str]]:
    """`[(name, kind, object)]` of the tree object `tree`, by `git ls-tree
    -z` with NO PATH, so no pathspec setting in the environment can narrow
    what is read. `kind` is `a tree` or, as `INDEX_ENTRY_KINDS` names an
    index entry, `a submodule`, `a symlink` or `a file`. `recursive` lists
    every file and gitlink below `tree`, and no tree."""
    listed = git_out(["ls-tree", *(["-r"] if recursive else []), "-z", tree],
                     cwd=root, binary=True)
    entries = []
    for record in listed.split(b"\0"):
        if not record:
            continue
        meta, _, name = record.partition(b"\t")
        mode, kind, oid = meta.split()
        entries.append((name.decode("utf-8", "surrogateescape"),
                        "a tree" if kind == b"tree" else
                        INDEX_ENTRY_KINDS.get(int(mode, 8), "a file"),
                        oid.decode("ascii")))
    return entries


def _head_spellings(root: Path) -> list[tuple[str, str, str]]:
    """`[(path, kind, object)]` of every file and gitlink HEAD holds at or
    under a spelling of `members` (`members/` itself included), or none in a
    holder with NO COMMIT YET (#363). A gitlink's object is the commit it
    records (#646).

    HEAD's root tree is listed, and each entry there whose name folds to
    `members` is listed through by its object, so nothing else of HEAD is
    read and no pathspec is used. `-q --verify HEAD^{tree}` answers nothing
    at all, without a word, where HEAD names no commit yet, as
    `MountRollback._head` reads it."""
    try:
        tree = git_out(["rev-parse", "-q", "--verify", "HEAD^{tree}"],
                       cwd=root)
    except Refusal:
        return []
    held: list[tuple[str, str, str]] = []
    for name, kind, oid in _tree_entries(root, tree):
        if _folded(name) != MEMBERS_DIR:
            continue
        if kind != "a tree":
            held.append((name, kind, oid))
            continue
        held.extend((f"{name}/{below}", what, at)
                    for below, what, at in _tree_entries(root, oid, True))
    return held


def _free_name(root: Path, listed: dict[str, list]) -> str:
    """`RENAMING`, or else the first of `RENAMING-2`, `RENAMING-3` and on,
    that nothing the index holds (`listed`) is at or under, in any case, and
    that the disk does not hold, as it resolves a name."""
    folded = {_folded(name) for name in listed}
    count = 1
    while True:
        name = RENAMING if count == 1 else f"{RENAMING}-{count}"
        if not os.path.lexists(root / name) and not any(
                held == name or held.startswith(name + "/")
                for held in folded):
            return name
        count += 1


def _renamed_with_git(root: Path, found: list[Spelled],
                      listed: dict[str, list], canon: str | None,
                      excluded: frozenset[str] = frozenset()
                      ) -> tuple[str, str, frozenset[str]] | None:
    """`(the spelling, the free name, the entries to put back first)` where
    `members/` was renamed to that spelling with `git mv`, and what
    `_members_spellings` found in the index under it is that (#685), or
    None. `listed` is every index entry's records, `canon` is
    `_members_dir_on_disk`'s answer, and `excluded` the index entries the
    sparse rules leave out (#761).

    `git mv` of `members/` renames each member's checkout, its gitlink and
    its section of `.gitmodules` (`path = Members/<P>`), staged or
    committed. The move back of a member's own gitlink (#646) puts the
    gitlink back and leaves the section naming the other spelling, so `git
    submodule update` then says `No url found for submodule path
    'members/<P>'`, and the gate finds `gitmodules-path-unnamed`. `git mv`
    of the spelling to a free name, then of that to `members`, takes all of
    it back, on every disk: on macOS and Windows the spelling IS
    `members/`, and a `git mv -- Members members` would take `members` for
    that directory and rename it into itself (`members/Members`), which the
    disk refuses. It is the remedy where all of these hold:

    - The index holds nothing at or under `members` itself.
    - Every member's own gitlink (`RESTORE`) the index holds under another
      spelling is under this one spelling, which nothing at that spelling
      itself can sit beside, and nothing the index holds under another
      spelling is a case variant of the mount path. What it holds under a
      THIRD spelling keeps its own remedy, which runs first, in
      `REMEDY_ORDER` (#761, rv685's NIT 5): on Linux a `git mv` of it, or
      its removal from the index, touches nothing under this spelling, and
      on macOS and Windows, where the three are one directory, it is never
      on disk in its own spelling (`_on_disk_as_named` reads the listing),
      so it is taken out of the index, which touches no file, and its file
      goes back with the rest.
    - HEAD holds no member's gitlink under another spelling that the index
      no longer does, and no section of `.gitmodules` gives one whose
      removal is staged (`IN_GITMODULES`, #761), which the rename would
      leave out, its section naming this spelling (rv685's candidate 1).
    - No `members/` is on this disk, or the one there is that spelling's own
      directory (`samefile`), as on macOS and Windows: a second directory
      would take the second step into it.
    - Neither that spelling nor `members` is a link, which is never
      `members/` itself (`_members_dir_on_disk`): `git mv` of a link to a
      directory says `not under version control`, and with a link `members
      -> Members` the second step says `destination already exists` and
      leaves the holder half renamed (#685's review, MUST-B).
    - Every entry under it is at stage 0 (`git mv` says `source directory
      is empty` for an unmerged gitlink, and `conflicted` for a file), and
      no sparse checkout keeps one off disk, nor do its rules leave one out
      whatever its bit says, either of which `git mv` refuses without
      `--sparse` (#761: `exist outside of your sparse-checkout definition`,
      exit 1, measured on git 2.43 for an entry on disk, its bit cleared).
    - Every entry under it is on disk as the index holds it, as the disk
      resolves the name, or can be put back first: `git mv` of a directory
      says `bad source` for any entry under it that is not. A file is put
      back with `git checkout --`; a gitlink with `git submodule update`,
      where a section of `.gitmodules` with a url gives its path.
    """
    if any(name == MEMBERS_DIR or name.startswith(MEMBERS_DIR + "/")
           for name in listed):
        return None
    held = [spelled for spelled in found if spelled.where == IN_INDEX]
    spellings = {spelled.name.partition("/")[0] for spelled in held
                 if spelled.remedy == RESTORE}
    if (len(spellings) != 1
            or any(spelled.mount for spelled in held)
            or any(spelled.remedy == RESTORE for spelled in found
                   if spelled.where in (IN_HEAD_ONLY, IN_GITMODULES))):
        return None
    (spelling,) = spellings
    if os.path.islink(root / spelling) or (
            canon is not None and os.path.islink(root / canon)):
        return None
    if canon is not None:
        try:
            if not (os.path.isdir(root / spelling) and os.path.samefile(
                    root / spelling, root / canon)):
                return None
        except OSError:
            return None
    under = [name for name in listed if name.startswith(spelling + "/")]
    if any(fields[2] != b"0" for name in under for fields in listed[name]):
        return None
    skipped = _skip_worktree(root)
    sections: set[str] | None = None
    put_back = set()
    for name in under:
        if name in skipped or name in excluded:
            return None
        here = root / name
        gitlink = listed[name][0][0] == b"160000"
        # As the index holds it: a gitlink a directory, anything else not.
        if (os.path.isdir(here) if gitlink else os.path.lexists(here) and (
                os.path.islink(here) or not os.path.isdir(here))):
            continue
        if os.path.lexists(here):
            return None
        if gitlink:
            if sections is None:
                try:
                    sections = {path for path, url, _
                                in _submodule_paths(root).values() if url}
                except Refusal:
                    return None
            if name not in sections:
                return None
        put_back.add(name)
    return spelling, _free_name(root, listed), frozenset(put_back)


def _members_spellings(root: Path, project: str,
                       on_disk: dict[str, tuple[str, list[str] | None]],
                       rows: frozenset[str] = frozenset()) -> list[Spelled]:
    """Every path the holder has at or under a spelling of `members/` other
    than `members/` itself, or at or under a case variant of the mount path
    `members/<project>`: in the index, in HEAD and no longer in the index,
    and on disk untracked (#362, #363, #364), each with the remedy that acts
    on it. `on_disk` is `_members_on_disk`'s listing, and `rows` the path of
    each `members:` row (`_rows_paths`), a case variant of which under
    `members/` itself, and no row's own path, is one too (`members/irrs`
    beside the row `members/IRRS`, #840): nothing named it and `add` went
    through, in the index, in HEAD or on disk, and the member's own gitlink
    there is moved back as below.

    #840 ADDS THREE MORE, each where a printed command failed or misled as
    typed: a section of `.gitmodules` giving a member another spelling of
    its row's path beside its gitlink at that path (`_sections_astray`); a
    symbolic link the index holds entries under, which git goes through
    (`_disk_found`); and a checkout git does not track inside a directory a
    `git mv` or `mv` moves (`_checkouts_in_the_way`).

    A MEMBER'S OWN GITLINK HELD IN THE WRONG CASE (#646) is moved back, never
    taken out or renamed. Where the index holds nothing at or under a row's
    path, a gitlink at a case variant of that path, in the index or in HEAD
    alone, is that member's (`Members/<P>` for the row `members/<P>`, #363's
    state after the fact). `git rm --cached` of it, or a committed `git mv`
    to another name, took it away from its row, and `git mv` to the row's
    path fails or misplaces it (`bad source`; `members/<P>/<P>`; `renaming
    ... failed`), so it is `RESTORE`: taken out of the index and recorded at
    the row's path, at the commit it records there, by `git update-index`,
    which reads no disk, as `validate-family.py` gives the same move (#611).
    An unmerged one is recorded at its stage 2, and is no member's own where
    it has no gitlink there. Where the index holds a gitlink at or under
    the row's path, a gitlink at a variant is a second one, which taking
    out leaves the member where it is: it keeps the remedy below.

    WHAT IS IN THE WAY OF THE MOVE IS SET ASIDE FIRST (#761, #670's (g) and
    (h)). `git update-index --add --cacheinfo` of the row's path replaces a
    file the index holds there without a word, and fails on one under it,
    or at `members` itself (`appears as both a file and as a directory`,
    exit 128, after the removal took the variant out), and #574's remedy
    takes the member's gitlink out instead. So where the index holds only
    files and links at or under a row's path, at any stage (an unmerged one
    is taken out of the index, every stage, #840), a gitlink at a variant
    is still the member's own, and each of those entries is set
    aside first (`SET_ASIDE`, `_set_aside`), as is a file or link the index
    holds at `members` itself wherever a gitlink is moved back: renamed with
    `git mv` where it is on disk as the index holds it, as
    `_members_is_a_file` moves `members` itself, else taken out of the
    index, each with `--sparse` where a sparse checkout needs it. WHOSE
    GITLINK IT IS NEVER TURNS ON THE SPARSE CHECKOUT (Codex's P2 1 on #828):
    a row whose file it marked or left out was dropped here, so the gitlink
    kept #574's remedy, which took it away from its row. The other order
    fails: measured, the move back first replaced the file at the row's
    path, and the `git mv` of that path then took the member's gitlink
    away.

    ITS SECTION OF `.gitmodules` IS POINTED BACK TOO (#761, #670's (e)). A
    `git mv` of a member's mount (`git mv members/<P> Members/<P>`) moves
    the section's `path` with it, which the move back of the gitlink leaves
    naming the variant: `git submodule update` then says `No url found for
    submodule path 'members/<P>'`. So each section that gives a member
    another spelling of its row's path is named on the member's `RESTORE`
    (`sections`), from the file `_submodule_paths` reads, and the move is a
    change to commit where HEAD's section gives another path.

    A MEMBER WHOSE GITLINK'S REMOVAL IS STAGED (#761, rv685's candidate 1):
    HEAD records it at its row's path, the index holds it nowhere, and a
    section of `.gitmodules` gives it another spelling, as a `git mv
    members Members` followed by `git rm --cached Members/<P>` leaves it.
    Nothing in the index or HEAD is under another spelling for it, so the
    rename back passed it by and left its section naming `Members/<P>`. It
    is `IN_GITMODULES`, moved back at HEAD's commit, with its section, and
    the rename back is not printed (`_renamed_with_git`).

    A `members/` RENAMED WITH `git mv` (#685), staged or committed, is
    renamed back with it, whole, in two steps through a free name
    (`RENAME_BACK`, `_renamed_with_git`), in place of the move back, which
    would leave each member's section of `.gitmodules` naming the other
    spelling; what the disk holds under that spelling goes back with it, so
    it is not named. What the index holds under a third spelling keeps its
    own remedy (#761).

    THE INDEX, the whole of it, as `_index_entries` reads it (#362). Each
    entry's remedy acts on `_spelled_target`'s path: renamed with `git mv`
    where that path is on disk in its own spelling (`_on_disk_as_named`) and
    is not `members/` itself under another spelling; renamed with `git mv
    --sparse`, entry by entry, where a sparse checkout keeps the entry off
    disk, or its rules leave it out whatever its bit says (#761); else taken
    out of the index, which touches no file, with `--sparse` where the rules
    leave it out. A SECOND PATH TO A MEMBER'S DIRECTORY, a gitlink at a case
    variant of a row's path beside the member's own gitlink at that path
    (`_second_gitlink`), is taken out of the index where it would be renamed
    (`UNSTAGE_SECOND`): `git mv` carried the section of `.gitmodules` that
    gives its path along, under the same name, and the take-out of that
    section after it left a gitlink no section names, at which a plain
    clone's `git submodule update --init --recursive` stopped, exit 128,
    while the gate passed (rv865b's MUST 1). Its removal takes `-f` where
    the move back's would (`_forced`), and a checkout left on disk in its
    own spelling (`checkout`) is named to delete by hand in the same round
    (rv865b's round-2 MUST 1 and SHOULD 1). THEN HEAD, for what it holds
    that the index no longer does, a `git rm -r Members` not committed yet
    (#363): the add's own commit names three paths and nothing else, so it
    would keep that file beside the member, and with `core.ignorecase` set
    git records the member's gitlink in the spelling HEAD has, where a fresh
    clone cannot find it. THEN THE DISK, by `_disk_spellings` (#364): a path
    the index holds itself, or holds anything above, or, for a path moved
    out of the way, anything under, is the index's to name, so no two
    remedies act on one path.
    """
    canon = _members_dir_on_disk(root, on_disk)
    listed = {name.decode("utf-8", "surrogateescape"):
              [record.split() for record in records]
              for name, records in _index_records(root).items()}
    indexed: dict[str, int] = {name: int(fields[0][0], 8)
                               for name, fields in listed.items()}
    gitlinks = {name for name, mode in indexed.items() if mode == 0o160000}
    occupied = frozenset(
        _folded(rest.partition("/")[0]) for first, _, rest
        in (name.partition("/") for name in indexed)
        if first == MEMBERS_DIR and rest)
    head = _head_spellings(root)
    in_head = {name: oid for name, _, oid in head}
    gitlink = INDEX_ENTRY_KINDS[0o160000]
    sparse = _SparseAsked(root, indexed)
    marked, left_out = sparse.marked, sparse.left_out
    strays, blocked, at_members = _rows_held(rows, indexed, listed)
    owners = {**strays, **{_folded(row): row for row in blocked}}
    found: list[Spelled] = []
    restored: list[str] = []
    moved: set[str] = set()
    for name, mode in indexed.items():
        spelled = _spelled_target(name, project, occupied, rows)
        if spelled is None:
            continue
        target, mount = spelled
        kind = INDEX_ENTRY_KINDS.get(mode, "a file")
        # The record it is moved back at: its own, or, unmerged, the one at
        # stage 2, the holder's own side, where git lists stage 1, the merge
        # base, first (#646's review, N2). With no gitlink there, it is no
        # member's own.
        ours = next((fields for fields in listed[name]
                     if fields[2] in (b"0", b"2")), None)
        own = (owners.get(_folded(name))
               if ours is not None and ours[0] == b"160000" else None)
        if own is not None:
            # The move leaves nothing to commit only where HEAD holds no
            # such variant and records the gitlink at the row's path
            # already, at this commit: a move to the variant, staged alone.
            recorded = ours[1].decode("ascii")
            moved.add(own)
            found.append(Spelled(
                _shown(name), kind, IN_INDEX, _shown(own), mount, RESTORE,
                name in in_head or in_head.get(own) != recorded, recorded,
                name in marked() or name in left_out(),
                forced=in_head.get(name) != recorded
                and os.path.lexists(root / name / ".git")))
            continue
        out = forced = checkout = False
        present = target != canon and _on_disk_as_named(
            root, target, target != name or mode == 0o160000)
        if present:
            # On disk, and left out by the rules whatever its bit says:
            # plain `git mv` refuses it (#761).
            remedy = RENAME_SPARSE if name in left_out() else RENAME
        else:
            remedy = RENAME_SPARSE if name in marked() else UNSTAGE
            out = remedy == UNSTAGE and name in left_out()
        if remedy != UNSTAGE and _second_gitlink(name, mode, rows, indexed):
            # A second path to a member's directory, which `git mv` would
            # carry its section along with (rv865b's MUST 1), with `-f` as
            # the move back takes it, and its checkout named (round 2).
            remedy = UNSTAGE_SECOND
            out = name in marked() or name in left_out()
            forced = _forced(root, name, listed[name][0][1], in_head)
            checkout = present and _moved_or_kept(root / name) == CHECKOUT
        target = name if remedy == RENAME_SPARSE else target
        found.append(Spelled(_shown(name), kind, IN_INDEX, _shown(target),
                             mount, remedy, name in in_head, sparse=out,
                             forced=forced, checkout=checkout))
    for name, kind, oid in head:
        spelled = _spelled_target(name, project, occupied, rows)
        if spelled is None or name in indexed:
            continue
        own = owners.get(_folded(name)) if kind == gitlink else None
        if own is not None:
            restored.append(name)
            moved.add(own)
            found.append(Spelled(_shown(name), kind, IN_HEAD_ONLY,
                                 _shown(own), spelled[1], RESTORE, True,
                                 oid))
            continue
        found.append(Spelled(_shown(name), kind, IN_HEAD_ONLY,
                             _shown(spelled[0]), spelled[1], COMMIT, True))
    # A member HEAD records at its row's path, the index nowhere, and a
    # section gives another spelling of (#761, rv685's candidate 1), in
    # sorted order: `rows` is a set, so the text would follow its hash.
    staged_out = [row for row in sorted(strays.values()) if row not in moved
                  and row in in_head and (row, gitlink, in_head[row]) in head]
    staged, gone = _sections_restored(root, found, moved, staged_out,
                                      in_head, project, rows)
    found.extend(staged)
    # What the disk holds where its section says is the move's to name too.
    restored.extend(gone)
    found.extend(_in_the_way(root, listed, head, moved,
                             (blocked, at_members), sparse))
    found.extend(_sections_astray(root, rows, indexed))
    renamed = _renamed_with_git(root, found, listed, canon, left_out()
                                if any(spelled.remedy == RESTORE
                                       for spelled in found) else frozenset())
    if renamed is not None:
        spelling, through, missing = renamed
        gone = {_shown(name) for name in missing}
        found = [spelled._replace(target=spelling, remedy=RENAME_BACK,
                                  recorded="", sparse=False, through=through,
                                  put_back=spelled.name in gone,
                                  sections=(), forced=False)
                 if spelled.where == IN_INDEX
                 and spelled.name.startswith(_shown(spelling) + "/")
                 else spelled
                 for spelled in found]
    # What the disk holds at a gitlink moved back from HEAD is the move's to
    # name, as what it holds at an index entry is the index's, and what it
    # holds under a `members/` renamed with `git mv` goes back with it.
    found.extend(_disk_found(root, (on_disk, canon, gitlinks), project, rows,
                             [*indexed, *restored,
                              *([renamed[0]] if renamed else [])]))
    # A checkout inside a directory a `git mv` or `mv` moves (#840).
    found.extend(_checkouts_in_the_way(root, found, gitlinks, project, rows))
    return found


class _SparseAsked:
    """What a sparse checkout marks (`skip-worktree`), and what its rules
    leave out of the index entries under a spelling of `members` (#761),
    each asked of git once, and only where it matters."""

    def __init__(self, root: Path, indexed: dict[str, int]) -> None:
        self.root = root
        self.names = [name for name in indexed
                      if _folded(name.partition("/")[0]) == MEMBERS_DIR]
        self._marked: frozenset[str] | None = None
        self._out: frozenset[str] | None = None

    def marked(self) -> frozenset[str]:
        """The entries a sparse checkout marks (`_skip_worktree`)."""
        if self._marked is None:
            self._marked = frozenset(_skip_worktree(self.root))
        return self._marked

    def left_out(self) -> frozenset[str]:
        """The entries its rules leave out (`_sparse_rules_exclude`)."""
        if self._out is None:
            self._out = frozenset(_sparse_rules_exclude(self.root,
                                                        self.names))
        return self._out


def _in_the_way(root: Path, listed: dict[str, list],
                head: list[tuple[str, str, str]], moved: set[str],
                held: tuple[dict[str, list[str]], str | None],
                sparse: _SparseAsked) -> list[Spelled]:
    """What is in the way of the move back of the gitlinks to the rows in
    `moved`, set aside first (`_set_aside`, #761): what the index holds at
    or under each of those rows, and a file or link at `members`, as
    `_rows_held` found them (`held`), wherever a gitlink is moved back, and
    nothing where none is. `listed` is every index entry's records, of which
    one held at a stage other than 0 is unmerged (#840), and `head` is
    `_head_spellings`'s. HEAD's gitlink at a row's path, which the move puts
    back, is no change for the removal of what stands there to leave to
    commit."""
    blocked, at_members = held
    if not moved:
        return []
    names = [name for row in sorted(moved & blocked.keys())
             for name in blocked[row]] + ([at_members] if at_members else [])
    if not names:
        return []
    gitlink = INDEX_ENTRY_KINDS[0o160000]
    kept = {name: oid for name, kind, oid in head
            if kind != gitlink or name not in moved}
    unmerged = frozenset(name for name in names
                         if any(fields[2] != b"0" for fields in listed[name]))
    return _set_aside(root, {name: int(listed[name][0][0], 8)
                             for name in names}, kept, names, sparse.marked(),
                      sparse.left_out(), unmerged)


def _second_gitlink(name: str, mode: int, rows: frozenset[str],
                    indexed: dict[str, int]) -> bool:
    """Is the index's entry `name`, of `mode`, a gitlink at a case variant
    of a row's path (`rows`) where the index (`indexed`, by mode) records a
    gitlink at that path itself: a second path to the member's directory,
    which the gate's `member-gitlink-unnamed` takes out of the index alone
    with `git rm --cached` (its `STRAY`, rv865b's MUST 1)?"""
    return mode == 0o160000 and any(
        _folded(row) == _folded(name) and indexed.get(row) == 0o160000
        for row in rows)


def _forced(root: Path, name: str, recorded: bytes,
            in_head: dict[str, str]) -> bool:
    """Does `git rm --cached` of the gitlink `name`, which the index records
    at `recorded`, take `-f`? Where HEAD (`in_head`) does not record it at
    that commit and a checkout is on disk at it, as the move back asks of a
    variant (#761): git refuses it there wherever that checkout has moved
    on or holds a file it does not track (`staged content different from
    both the file and the HEAD`, exit 1, rv865b's round-2 MUST 1, measured
    on git 2.43 and 2.47.1), and with `--cached` `-f` touches no file."""
    return in_head.get(name) != recorded.decode("ascii") and os.path.lexists(
        root / name / ".git")


def _rows_held(rows: frozenset[str], indexed: dict[str, int],
               listed: dict[str, list]
               ) -> tuple[dict[str, str], dict[str, list[str]], str | None]:
    """`(strays, blocked, at_members)` for `_members_spellings`, from the
    index's entries by mode (`indexed`) and their records (`listed`):

    - each row's path the index holds nothing at or under, by its folded
      spelling, where a gitlink at another spelling of it is that member's
      own (#646);
    - each row's path the index holds files and links alone at or under,
      at every stage it holds each at, with those entries, which are set
      aside before the move back (#761);
    - `members` where the index holds a file or link there, at every stage
      it holds it at, which no `members/<P>` can sit beside, else None.

    Whatever a sparse checkout says of an entry in the way, the gitlink is
    still the member's own: `_set_aside` gives the entry the `--sparse` git
    needs (Codex's P2 1 on #828). AN UNMERGED ONE IS IN THE WAY TOO (#840,
    rv828's SHOULD 3): passed by, the gitlink at the variant kept #574's
    `git mv`, which took it away from its row, and the commit after it
    failed (`Committing is not possible because you have unmerged files`);
    `_set_aside` takes it out of the index, every stage, as git allows."""
    def file_or_link(name: str) -> bool:
        """A file or link at every stage the index holds it at."""
        return all(fields[0] != b"160000" for fields in listed[name])

    strays: dict[str, str] = {}
    blocked: dict[str, list[str]] = {}
    for row in rows:
        held = [name for name in indexed
                if name == row or name.startswith(row + "/")]
        if not held:
            strays[_folded(row)] = row
        elif all(file_or_link(name) for name in held):
            blocked[row] = held
    at_members = (MEMBERS_DIR if MEMBERS_DIR in indexed
                  and file_or_link(MEMBERS_DIR) else None)
    return strays, blocked, at_members


def _sections_restored(root: Path, found: list[Spelled], moved: set[str],
                       staged_out: list[str], in_head: dict[str, str],
                       project: str, rows: frozenset[str] = frozenset()
                       ) -> tuple[list[Spelled], list[str]]:
    """Each section of `.gitmodules` that gives a member moved back another
    spelling of its row's path, named on the member's `RESTORE` in `found`
    (which this updates in place), and an `IN_GITMODULES` move for each row
    in `staged_out`, whose gitlink HEAD records at its path and the index
    holds nowhere, where a section gives it another spelling: returned, with
    the path each such section gives, as git spells it (#761). `moved` is
    the rows a `RESTORE` in `found` moves back to, which this adds those
    rows to, and `rows` every `members:` row's path, of which a section's
    path under `members/` itself may be a variant (#840).

    The file is the one `_submodule_paths` reads, the work tree's where
    there is one, which is the one `git config -f .gitmodules` edits; one
    git cannot read names no section here, and is refused on its own once
    the move is done (`gitmodules-unreadable`). HEAD's copy says whether
    pointing a section back is a change to commit: it is where HEAD's
    section gives another path, as after a committed `git mv`, and not
    where only a staged one moved it."""
    if not moved and not staged_out:
        return [], []
    try:
        given = _submodule_paths(root)
    except Refusal:
        return [], []
    head = _head_section_paths(root)

    def giving(row: str) -> tuple[str, ...]:
        return tuple(sorted(
            name for name, (path, _, _) in given.items()
            if path != row and _folded(path) == _folded(row)))

    added: list[Spelled] = []
    gone: list[str] = []
    for row in staged_out:
        variants = sorted({given[name][0] for name in giving(row)
                           if _spelled_target(given[name][0], project,
                                              rows=rows) is not None})
        if variants:
            moved.add(row)
            gone.extend(variants)
            added.append(Spelled(
                _shown(variants[0]), INDEX_ENTRY_KINDS[0o160000],
                IN_GITMODULES, _shown(row),
                _spelled_target(variants[0], project, rows=rows)[1], RESTORE,
                False, in_head[row]))
    for index, spelled in enumerate([*found, *added]):
        if spelled.remedy != RESTORE:
            continue
        row = next(row for row in moved if _shown(row) == spelled.target)
        names = giving(row)
        updated = spelled._replace(
            sections=names, committed=spelled.committed or any(
                head.get(name) != row for name in names))
        if index < len(found):
            found[index] = updated
        else:
            added[index - len(found)] = updated
    return added, gone


def _head_section_paths(root: Path) -> dict[str, str]:
    """`{name: path}` of every section of HEAD's `.gitmodules` that gives a
    path, read as `_submodule_paths` reads a copy (`git config --blob`), or
    none where HEAD names no commit, holds no `.gitmodules`, or holds one git
    cannot read (#761)."""
    try:
        blob = git_out(["rev-parse", "-q", "--verify", f"HEAD:{GITMODULES}"],
                       cwd=root)
        listed = git_out(["config", "-z", "--blob", blob, "--list"],
                         cwd=root, binary=True)
    except Refusal:
        return {}
    found: dict[str, str] = {}
    for record in listed.split(b"\0"):
        key, _, value = record.decode("utf-8",
                                      "surrogateescape").partition("\n")
        section, _, variable = key.rpartition(".")
        if section.startswith("submodule.") and variable == "path":
            found[section[len("submodule."):]] = value
    return found


def _set_aside(root: Path, indexed: dict[str, int], in_head: dict[str, str],
               names: list[str], marked: frozenset[str],
               left_out: frozenset[str],
               unmerged: frozenset[str] = frozenset()) -> list[Spelled]:
    """One of `SET_ASIDE` for each of `names`, an entry the index holds at
    or under a row's path that a gitlink is moved back to, or at `members`
    itself (#761), by the rule `_members_spellings` names what the index
    holds by; `in_head` is what HEAD holds that the move back does not put
    back, `marked` what a sparse checkout marks (`skip-worktree`), and
    `left_out` what its rules leave out. Renamed with `git mv` where it is
    on disk as the index holds it, a file or link and no directory, or with
    `git mv --sparse` where the rules leave it out; off disk, renamed with
    `git mv --sparse` where it is marked, which keeps what it holds, and
    else taken out of the index, which touches no file, with `--sparse`
    where the rules leave it out. A rename leaves a change to commit, and a
    removal one where `in_head` holds the entry. HEAD's gitlink at the row's
    path is not in it: a file staged there over a staged `git mv` of the
    mount and deleted from disk was said to leave its removal to commit,
    and the commit printed failed with nothing to commit (found in #828's
    fix round for Codex's P2s).

    EACH `--sparse` IS ONE GIT ASKS FOR (Codex's P2 1 on #828), measured on
    git 2.43 and 2.47.1 for a file under a row's path. Marked and on disk,
    plain `git mv` takes it. Marked and off disk, or left out by the rules
    with its bit cleared and on disk, plain `git mv` and `git rm --cached`
    refuse it (`exist outside of your sparse-checkout definition`, exit 1),
    and `git mv --sparse` takes it. Left out and off disk, `git rm --cached`
    refuses it the same way, `git mv` with or without `--sparse` says `bad
    source` (exit 128), and `git rm --cached --sparse` takes it.

    AN UNMERGED ONE (`unmerged`, #840, rv828's SHOULD 3), which `git mv`
    refuses (`conflicted`, exit 128), is taken out of the index, every
    stage, with `git rm -r --cached`, which git allows there and which
    touches no file (`ASIDE_UNMERGED`), and where it is on disk as the index
    holds it, it is then moved out of the way with `mv`
    (`ASIDE_UNMERGED_MV`): measured on git 2.43, a file left at the row's
    path made the update fail (`could not create directories for
    members/<P>/.git`), and one left under it stayed in the member's
    checkout, which `git status` then lists as modified. Its removal leaves
    a change to commit where `in_head` holds it."""
    aside = []
    for name in names:
        remedy = _aside_remedy(_on_disk_as_named(root, name, False), name,
                               (marked, left_out, unmerged))
        aside.append(Spelled(
            _shown(name), INDEX_ENTRY_KINDS.get(indexed[name], "a file"),
            IN_INDEX, _shown(name), False, remedy,
            remedy in (ASIDE, ASIDE_SPARSE) or name in in_head,
            sparse=remedy == ASIDE_OUT and name in left_out))
    return aside


def _aside_remedy(on: bool, name: str,
                  sets: tuple[frozenset[str], frozenset[str], frozenset[str]]
                  ) -> str:
    """Which of `SET_ASIDE` `_set_aside` gives `name`, on disk as the index
    holds it where `on`; `sets` is what a sparse checkout marks, what its
    rules leave out, and what the index holds unmerged (#840)."""
    marked, left_out, unmerged = sets
    if name in unmerged:
        return ASIDE_UNMERGED_MV if on else ASIDE_UNMERGED
    if on:
        return ASIDE_SPARSE if name in left_out else ASIDE
    return ASIDE_SPARSE if name in marked else ASIDE_OUT


def _sections_astray(root: Path, rows: frozenset[str],
                     indexed: dict[str, int]) -> list[Spelled]:
    """Each section of `.gitmodules` that gives another spelling of a row's
    path, where the index records the member's gitlink at that path already
    (#840), from the file `_submodule_paths` reads, the one `git config -f
    .gitmodules` edits: pointed back (`POINT_BACK`, `IN_SECTION`) or taken
    out (`TAKE_OUT`, `BESIDE_SECTION`), as `_row_sections_astray` tells the
    two apart for each such row.

    A HAND EDIT, OR #646'S OLD MOVE BACK, LEAVES ONE: the gitlink back at
    `members/<P>` and the section still saying `Members/<P>`. Nothing at
    another spelling is in the index, HEAD or the disk, so `add` went
    through and committed that `.gitmodules` beside the new member, and the
    gate refused it in every mode (`gitmodules-path-unnamed`, and
    `member-gitmodules-absent` once committed: a recursive clone checks the
    member out nowhere). So does `git rm --cached` of a submodule a hand
    added at another spelling, beside the member's own section, which `git
    rm --cached` leaves. A member moved back (`RESTORE`) has its sections on
    its own move (`_sections_restored`); its gitlink is not at its row's
    path, so it is not one of these."""
    held = [row for row in sorted(rows) if indexed.get(row) == 0o160000]
    if not held:
        return []
    try:
        given = _submodule_paths(root)
    except Refusal:
        return []
    head = _head_section_paths(root)
    return [spelled for row in held
            for spelled in _row_sections_astray(row, given, head)]


def _row_sections_astray(
        row: str, given: dict[str, tuple[str, str | None, tuple[str, ...]]],
        head: dict[str, str]) -> list[Spelled]:
    """`_sections_astray`'s answer for the row's path `row`, whose gitlink
    the index records there, from every section `given` (`_submodule_paths`)
    and HEAD's (`head`, `_head_section_paths`), as the gate tells the cases
    apart (`gitmodules-path-unnamed`, `member-gitmodules-absent`):

    - WHERE A SECTION GIVES THE ROW'S PATH ITSELF, each one that gives
      another spelling of it is a second one beside it, the gate's `STRAY`,
      and is taken out, every key it holds, with the gate's own
      `--unset-all` lines (`TAKE_OUT`), and that is a change to commit where
      HEAD holds a section of that name. Pointed back, it gave the row's
      path twice, with ITS url (rv865's MUST 1: `git submodule add
      <another url> Members/<P>`, its rename or removal typed as printed,
      left a recursive clone fetching the member from that url, exit 128,
      and the gate refused `gitmodules-path-twice`). It is taken out after
      the index's own remedy for a gitlink at its path, `git rm --cached`,
      which leaves it (`UNSTAGE_SECOND`): `git mv` moved it with the
      gitlink, under the same name, and taken out after that, it left a
      gitlink no section names, at which a plain clone's `git submodule
      update --init --recursive` stopped, exit 128 (rv865b's MUST 1).
    - WHERE NONE DOES, the gate's `member-gitmodules-absent`, the section
      named after the row's path, as `add` names one, is the member's own,
      and is pointed back with the gate's own line, `git config -f
      .gitmodules submodule.<row path>.path <row path>` (`POINT_BACK`): a
      change to commit where HEAD's section gives another path, a gitlink
      the index holds at that path too being taken out of the index first,
      which leaves the section where it is (rv865b's ruling on K2: renamed
      with `git mv`, it took the section along, and the update printed
      after the point-back stopped, exit 128). Once it is pointed back,
      every other one is a second one beside it, and taken out as above.
      Where no section named so can be pointed back, none is touched
      here: the gate names each such section and prints no command for it,
      since taking it out could un-register the member."""
    paths = {path for path, _, _ in given.values()}
    astray = [(name, path, keys) for name, (path, _, keys)
              in sorted(given.items())
              if path != row and _folded(path) == _folded(row)]
    back = row not in paths and any(name == row for name, _, _ in astray)
    found = []
    for name, path, keys in astray:
        if back and name == row:
            found.append(Spelled(_shown(path), "a section", IN_SECTION,
                                 _shown(row), False, POINT_BACK,
                                 head.get(name) != row, sections=(name,)))
        elif back or row in paths:
            found.append(Spelled(_shown(path), "a section", BESIDE_SECTION,
                                 _shown(path), False, TAKE_OUT, name in head,
                                 sections=(name,), keys=keys))
    return found


def _disk_found(root: Path,
                listing: tuple[dict[str, tuple[str, list[str] | None]],
                               str | None, set[str]],
                project: str, rows: frozenset[str],
                named: list[str]) -> list[Spelled]:
    """What the disk holds that `_members_spellings` names, by
    `_disk_spellings` over `listing` (`_members_on_disk`'s listing,
    `_members_dir_on_disk`'s answer and every gitlink the index holds): a
    path one of `named` (the index's entries, the gitlinks moved back from
    HEAD, a `members/` renamed with `git mv`) is at or above is theirs to
    name, and so is one moved out of the way that one of them is under.

    BUT A SYMBOLIC LINK ONE OF THEM IS UNDER IS NAMED FIRST (`LINK_OUT`,
    #840, rv685's round-3 candidate 3). `git rm --cached` of a gitlink under
    a link goes through it, to a checkout whose `.git` file names its store
    by a path relative to where the link points, and fails (`fatal: not a
    git repository: Members/IRRS/../../.git/modules/members/IRRS`, exit 128,
    measured on git 2.43 with `Members` a link to a directory outside the
    holder), and `git mv` of a file under it moves that file in from where
    the link points. Moved out of the way first, the link takes nothing
    with it, and every line after it acts on the index alone
    (`_on_disk_as_named` takes nothing beyond a link for on disk)."""
    on_disk, canon, gitlinks = listing
    found = []
    for path, kind, remedy in _disk_spellings(root, on_disk, project, canon,
                                              gitlinks, rows):
        if any(name == path or path.startswith(name + "/") for name in named):
            continue
        under = any(name.startswith(path + "/") for name in named)
        if under and kind == "a symlink":
            remedy = LINK_OUT
        elif under and remedy in (MOVE, CHECKOUT):
            continue
        found.append(Spelled(_shown(path), kind, ON_DISK, _shown(path),
                             _spelled_target(path, project, rows=rows)[1],
                             remedy))
    return found


def _checkouts_in_the_way(root: Path, found: list[Spelled],
                          gitlinks: set[str], project: str,
                          rows: frozenset[str]) -> list[Spelled]:
    """`CHECKOUT_FIRST` for each checkout git does not track inside a
    directory that a `git mv` (`RENAME`) or an `mv` (`MOVE`) in `found`
    moves (#840, w761's candidate on #828).

    `git mv` OF A DIRECTORY MOVES IT WHOLE, untracked files and all, and so
    does `mv`. Measured on git 2.43: a committed `Members/X/notes` and a
    checkout `git submodule add` made at `Members/X/Y`, then taken out of
    the index; #574's `git mv -- Members/X <new name>` typed as printed
    moved the checkout too, and `git -C <new name>/Y status` then said
    `fatal: not a git repository`, its `.git` file naming its store by a
    path relative to where it was, as #681's N-1 measured for a plain `mv`.
    So each is named before the move, to be deleted by hand once nothing
    only it holds is needed, as `CHECKOUT` names one found on disk: its
    commits are kept in that store. A checkout the index records (a gitlink)
    is moved by `git mv` with its `.git` file mended, measured, and is not
    named; one at the moved path itself is that path's own, and is not
    entered."""
    moved = sorted({spelled.target for spelled in found
                    if spelled.remedy in (RENAME, MOVE)})
    return [Spelled(_shown(path), "a directory", ON_DISK, _shown(path),
                    _spelled_target(path, project, rows=rows)[1],
                    CHECKOUT_FIRST)
            for target in moved
            for path in _checkouts_under(root, target, gitlinks)]


def _checkouts_under(root: Path, target: str,
                     gitlinks: set[str]) -> list[str]:
    """Every directory strictly under `target`, not through a link, that
    holds a `.git` FILE and is no gitlink the index holds, as a path from
    `root`; none where `target` is no directory or is a repository itself.
    A directory holding a `.git` entry of any kind is not entered."""
    top = root / target
    if os.path.islink(top) or not top.is_dir() or os.path.lexists(
            top / ".git"):
        return []
    found = []
    # `os.walk` lists a link to a directory and never enters it.
    for here, dirs, _ in os.walk(top):
        held = {name for name in dirs
                if os.path.lexists(os.path.join(here, name, ".git"))}
        dirs[:] = sorted(set(dirs) - held)
        found.extend(Path(here, name).relative_to(root).as_posix()
                     for name in held
                     if _moved_or_kept(Path(here, name)) == CHECKOUT)
    return sorted(name for name in found if name not in gitlinks)


#: How the work tree's `.gitmodules` stands beside the index's copy, as
#: `_gitmodules_beside` answers it (#685).
GITMODULES_MODIFIED = "modified"
GITMODULES_MISSING = "missing"
GITMODULES_UNMERGED = "unmerged"
#: HEAD holds one and its deletion is staged, and the work tree has none
#: (`GITMODULES_DELETED`) or one git does not track (`GITMODULES_UNTRACKED`)
#: (#840).
GITMODULES_DELETED = "deleted"
GITMODULES_UNTRACKED = "untracked"


def _gitmodules_beside(root: Path) -> str:
    """How the work tree's `.gitmodules` stands beside the index's copy, told
    apart as `_checked_gitmodules_as_staged` tells them apart, for the
    remedies `_spellings_refusal` prints (#685): `GITMODULES_UNMERGED` where
    the index holds it at a stage other than 0; `GITMODULES_DELETED` and
    `GITMODULES_UNTRACKED` where HEAD holds one and the index none, its
    deletion staged, and the work tree none or one (#840);
    `GITMODULES_MISSING` where the index holds it at stage 0 and the work
    tree has none; `GITMODULES_MODIFIED` where both hold one and git lists
    it as modified (`git ls-files -m`, which lists a missing one too); else
    empty: none in the index or HEAD, one a sparse checkout keeps off disk
    (`gitmodules-sparse`'s), or one as the index holds it."""
    records = _gitmodules_in_index(root)
    if any(stage for _, _, stage in records):
        return GITMODULES_UNMERGED
    if not records and _head_oid(root, GITMODULES) is not None:
        return (GITMODULES_UNTRACKED if os.path.lexists(root / GITMODULES)
                else GITMODULES_DELETED)
    if not records or records[0][0].upper() == "S":
        return ""
    if not os.path.lexists(root / GITMODULES):
        return GITMODULES_MISSING
    if GITMODULES.encode() in _git_bytes(["ls-files", "-m", "-z"],
                                         root).split(b"\0"):
        return GITMODULES_MODIFIED
    return ""


#: The order `_spellings_refusal` names its groups in. Its remedies run in
#: `REMEDY_ORDER`: a pending change in HEAD is committed first.
SPELLED_ORDER = (IN_INDEX, IN_HEAD_ONLY, IN_GITMODULES, IN_SECTION,
                 BESIDE_SECTION, ON_DISK)


def _spellings_refusal(path: str, found: list[Spelled],
                       gitmodules: str = "") -> Refusal:
    """The refusal for what `_members_spellings` found: every path named in
    its exact spelling, at most five in each place, with where it was found,
    and every remedy (Brett Heap's ruling of 2026-10-14, "Refuse on every
    disk", #362, #363, #364).

    `member-path-taken` where any is at or under a case variant of the mount
    path, as #318 refuses one in the index; `family-members-dir-variant`
    where every one is under a spelling of `members/` alone: a fault of the
    holder's `members/` directory (`members_dir`, as `family.yaml` names
    it), which no member can be added past. A case variant of a row's path
    under `members/` itself (#840) is that code's too, and its first
    sentence says so (`_lead`).

    THE REMEDIES RUN IN `REMEDY_ORDER`, and each command names one entry, so
    no command takes another's path from under it: a symbolic link the
    index holds entries under moved out of the way first (#840), since git
    goes through it; `git commit` for what HEAD holds and the index no
    longer does, since the add's own commit names three paths; a checkout
    git does not track inside a directory a `git mv` or `mv` below moves,
    deleted by hand before that move (#840); then `git mv`, `git mv
    --sparse` and `git rm -r --cached` for what the index holds, `git rm -r
    --cached` alone for a second path to a member's directory, as the gate
    takes one out (rv865b's MUST 1), and a commit; then each section of
    `.gitmodules` pointed back at its row's path where the index records
    the gitlink there already and no section gives that path, and each
    taken out, every key it holds, where one gives it beside it (#840,
    rv865's MUST 1), each with a commit where HEAD's copy changes or a
    commit before it took a staged one in; then, for a
    `members/` renamed with `git mv` (#685), what puts back an entry under
    it that the disk lacks, the `git mv` of it to a free name and of that
    to `members`, and a commit; then what is in the way of the move back set
    aside (#761), the move of a member's own gitlink back to its row's path
    with its section of `.gitmodules`, and a commit; then `mv` for what is
    on disk and untracked, a checkout there left to be deleted by hand
    (#761), and `mv` back for a renamed `members/`; then each checkout a
    second path taken out of the index leaves, deleted by hand before the
    update (rv865b's round-2 SHOULD 1). Every path is quoted
    for a POSIX shell (#532). A `--sparse` says the git it needs
    (`SPARSE_MV_GIT`, `SPARSE_RM_GIT`, #685), and is printed where the
    sparse rules leave an entry out as well as where they mark it (#761).

    AN ENTRY IN THE WAY OF THE MOVE BACK (#761), at or under a row's path
    or at `members` itself, which `git update-index` would replace or fail
    on, is set aside first, in no commit of its own: the move's commit
    takes both, so the history never holds the member's gitlink beside the
    file, nor the file gone and the gitlink not back. Its `git mv --sparse`
    and `git rm --cached --sparse` are said as the index's are (Codex's P2
    1 on #828).

    THE WORK TREE'S `.gitmodules` (`gitmodules`, `_gitmodules_beside`'s
    answer, which `_gitmodules_first` passes, the first two only where a
    remedy runs `git mv` or `git rm` of a gitlink or points a section back)
    comes first (#685):
    - A change to it nobody has staged (`GITMODULES_MODIFIED`) is staged:
      `git mv` and `git rm` of a gitlink refuse to run beside one (`Please
      stage your changes to .gitmodules or stash them to proceed`).
    - A copy the work tree lacks (`GITMODULES_MISSING`) is put back from the
      index: `git mv` rewrites a moved member's section only in the work
      tree's copy and passes over it where there is none, and a `git add`
      of the file would stage its deletion, which the printed commit would
      then take out of HEAD with every member's section (#685's review,
      MUST-A).
    - A deletion staged while HEAD holds one, the work tree lacking it too
      (`GITMODULES_DELETED`, #840), is put back from HEAD (`git checkout
      HEAD -- .gitmodules`): any commit printed here would take the file,
      and every member's section, out of HEAD.
    `gitmodules-unstaged`, which says the same of the file, is asked after
    this refusal; an unmerged copy, or a deletion staged beside a copy git
    does not track, is its to name first, and an unmerged copy the work
    tree lacks too is `gitmodules-missing`'s (`_gitmodules_first`, #840).

    THE MOVE BACK (#646) is `validate-family.py`'s for the same state
    (#611), in one line: `git rm -r --cached --ignore-unmatch` of every
    variant, which touches no file, and is no error where only HEAD holds
    one, with `--sparse` where a sparse checkout keeps one off disk, since
    without it git passes that one over, exit 0, and the index ends with two
    gitlinks; a `git update-index --add --cacheinfo` per row, at the commit
    the variant records, the first found where a row has two, the index's
    before HEAD's; a `git config -f .gitmodules submodule.<name>.path <row
    path>` per section that gives another spelling of it, and `git add --
    .gitmodules` (#761); and the commit, where it leaves one to make. A
    member whose removal is staged (`IN_GITMODULES`) is put back at HEAD's
    commit in the same line.

    ITS CLOSING SENTENCES, after every other remedy, so that a `members/`
    moved back has taken the checkout with it, are the validator's
    (`_wrong_case_move`, #681), each `mv` guarded by tests a POSIX shell
    runs, dash and bash alike (#761), in the form the validator prints
    (#839): `[ ! -L <variant> ]` FIRST, so a symbolic link there is always
    moved, the link and never what it points at, since `-ef` and `-e` read
    through it, and the guard kept one pointing at the row's own directory,
    which the next `add` refused as on disk and untracked (rv865b's NIT 4);
    then, in braces, `[ ! -e <variant> ]`, true where nothing is there,
    where the `mv` alone failed, exit 1 (`cannot stat`), and stopped what
    was typed after it, as where a sparse checkout keeps the variant off
    disk (Codex's P2 2 on #828); `[ <variant> -ef <row path> ]`, true where
    the disk takes the two names for one directory, the row's own; and `[
    -e <variant>/.git ]`, true for a checkout, which a move leaves pointing
    nowhere. So the text is the same on every disk, it exits 0 wherever it
    is typed, and the shell, not a sentence about the system, keeps the
    row's own directory in place. Then where a checkout's commits are
    kept, and that it is deleted by hand once nothing only it holds is
    needed; a clone of its own is moved out
    whole, by hand. ONE ORDER DIFFERS FROM THE VALIDATOR'S, measured: the
    update `git submodule update --init --recursive` comes LAST here. A
    checkout at the variant that `git mv` of the mount made shares the
    member's store, `.git/modules/members/<P>`, and the update, checking
    the member out at the row's path, points that store's `core.worktree`
    there: `git -C <variant> status` then printed the row's clean checkout
    and not the variant's own uncommitted file. Read before the update, it
    names that file, so the checkout is weighed and deleted first. A
    section pointed back with no move back closes on the same update, for a
    fresh clone, which checks the member out nowhere until it is (#840).
    """
    mount = any(spelled.mount for spelled in found)
    groups = []
    for where in SPELLED_ORDER:
        # What is set aside is at a row's path or at `members`, no spelling
        # of either: its part names it.
        here = [spelled for spelled in found if spelled.where == where
                and spelled.remedy not in SET_ASIDE]
        if not here:
            continue
        shown = ", ".join(f"`{spelled.name}` ({spelled.kind})"
                          for spelled in here[:5])
        more = f" and {len(here) - 5} more" if len(here) > 5 else ""
        groups.append(f"{where}: {shown}{more}")
    by = {remedy: sorted({spelled.target for spelled in found
                          if spelled.remedy == remedy})
          for remedy in REMEDY_ORDER}

    # What `.gitmodules` needs first, then a link git would go through
    # (#840), before any line that names a path under it.
    parts = [*_gitmodules_part(gitmodules), *_link_part(by)]
    if by[COMMIT]:
        named = ", ".join(f"`{target}`" for target in by[COMMIT])
        parts.append(
            "commit the pending change first (`git commit`), since the add's "
            f"own commit names {GITMODULES}, {path} and {MANIFEST} alone: "
            f"HEAD would keep {named} beside the member, or, with "
            "`core.ignorecase` set, record the member's gitlink in that "
            "spelling")
    # A checkout inside a directory moved below, before that move (#840).
    parts.extend(_checkout_first_part(by))
    index = []
    if by[RENAME]:
        index.append("rename what the index holds with `git mv`, entry by "
                     f"entry ({_each(RENAME, by[RENAME])})")
    if by[RENAME_SPARSE]:
        index.append("rename what the sparse checkout leaves out with `git "
                     f"mv --sparse`, {SPARSE_MV_GIT}, entry by entry "
                     f"({_each(RENAME_SPARSE, by[RENAME_SPARSE])})")
    if by[UNSTAGE]:
        quoted = " ".join(shell_quoted(target, "posix")
                          for target in by[UNSTAGE])
        # `--sparse` where the rules leave one out (#761), which `git rm
        # --cached` otherwise refuses.
        out = any(spelled.sparse for spelled in found
                  if spelled.remedy == UNSTAGE)
        index.append("take what has nothing on disk in that spelling out of "
                     f"the index, which touches no file (`{UNSTAGE}"
                     f"{' --sparse' if out else ''} -- {quoted}`"
                     + (f", {SPARSE_RM_GIT}" if out else "") + ")")
    index.extend(_second_path_part(found, by))
    removed = _removed(found, by)
    renamed = bool(by[RENAME] or by[RENAME_SPARSE])
    if renamed or removed:
        index[-1] += ", and commit " + (
            "both" if renamed and removed else
            "the rename" if renamed else "the removal")
    if index:
        parts.append(", ".join(index))
    # A section astray beside a gitlink at its row's path (#840), pointed
    # back or taken out before what is set aside, whose commit is the
    # move's. A commit printed before it takes a staged `.gitmodules` into
    # HEAD.
    parts.extend(_point_back_part(found, by,
                                  any((by[COMMIT], renamed, removed))))
    # A `members/` RENAMED WITH `git mv` (#685), one spelling at most: what
    # puts back an entry under it the disk lacks, then the two `git mv`s.
    for target in by[RENAME_BACK]:
        held = [spelled for spelled in found if spelled.remedy == RENAME_BACK]
        through = shell_quoted(held[0].through, "posix")
        quoted = shell_quoted(target, "posix")
        gitlink = INDEX_ENTRY_KINDS[0o160000]
        back = [f"`{command} -- {' '.join(names)}`" for command, names in (
            ("git submodule update --init --recursive", sorted(
                shell_quoted(spelled.name, "posix") for spelled in held
                if spelled.put_back and spelled.kind == gitlink)),
            ("git checkout", sorted(
                shell_quoted(spelled.name, "posix") for spelled in held
                if spelled.put_back and spelled.kind != gitlink)))
            if names]
        parts.append(
            (f"put back what the index holds under `{target}` and the disk "
             f"does not, {' and '.join(back)}, then " if back else "")
            + f"rename `{target}` back to {MEMBERS_DIR}/, since it holds the "
            f"gitlinks of members whose rows place them under {MEMBERS_DIR}/, "
            "in two steps through a name nothing holds, as macOS and Windows "
            f"take `{target}` for {MEMBERS_DIR}/ itself: `git mv` takes each "
            f"checkout, and each section of {GITMODULES} that names it, with "
            f"it (`{RENAME} -- {quoted} {through}`, then `{RENAME} -- "
            f"{through} {MEMBERS_DIR}`)"
            + (", and commit the rename" if by[COMMIT] or any(
                spelled.committed for spelled in held) else ""))
    # WHAT IS IN THE WAY OF THE MOVE BACK (#761), set aside first, in the
    # move's own commit; then the move back itself, and its closing
    # sentences, which come last.
    aside = _set_aside_part(found, by)
    if aside:
        parts.append(aside)
    moving, closing = _move_back_parts(found, by)
    if moving:
        parts.append(moving)
    if by[MOVE]:
        parts.append("move what is on disk and untracked out of the way "
                     f"({_each(MOVE, by[MOVE])})")
    if by[CHECKOUT]:
        named = " and ".join(f"`{target}`" for target in by[CHECKOUT])
        parts.append(
            "delete by hand each checkout on disk and untracked, "
            f"{named}, once nothing only it holds is needed, rather than "
            "move it: its .git file names its store by a path relative to "
            "it, which a move would leave pointing nowhere, and its commits "
            "are kept in that store, so only what is not committed is in it "
            "alone")
    for target in by[MOVE_BACK]:
        parts.append(
            f"move `{target}` back to {MEMBERS_DIR}/, since it holds "
            f"checkouts of members git tracks under {MEMBERS_DIR}/ (`mv -- "
            f"{shell_quoted(target, 'posix')} {MEMBERS_DIR}`)")
    # A checkout a second path leaves, before the update below (round 2).
    parts.extend(_second_checkout_part(found))
    # Last, so that a `members/` moved back has taken the checkout with it.
    parts.extend(closing)
    said = "; ".join(parts)
    return Refusal(
        "member-path-taken" if mount else "family-members-dir-variant",
        _lead(path, found, mount) + " — " + "; ".join(groups),
        f"Remediation: every member is mounted under {MEMBERS_DIR}/, and a "
        "holder keeps that directory in one spelling on every disk. "
        + said[:1].upper() + said[1:] + "; then re-run.")


def _second_path_part(found: list[Spelled],
                      by: dict[str, list[str]]) -> list[str]:
    """`_spellings_refusal`'s index part that takes each second path to a
    member's directory out of the index alone (`UNSTAGE_SECOND`, rv865b's
    MUST 1), with `--sparse` where a sparse checkout needs it and `-f` where
    the index stages it at a commit HEAD does not record there beside a
    checkout (`_forced`, rv865b's round-2 MUST 1), said as the move back
    says it (`FORCED_SAID`), or empty; `by` is its targets by remedy."""
    if not by[UNSTAGE_SECOND]:
        return []
    quoted = " ".join(shell_quoted(target, "posix")
                      for target in by[UNSTAGE_SECOND])
    second = [spelled for spelled in found
              if spelled.remedy == UNSTAGE_SECOND]
    out = any(spelled.sparse for spelled in second)
    force = any(spelled.forced for spelled in second)
    return ["take each gitlink at another spelling of a row's path beside "
            "the member's own gitlink at that path, a second path to its "
            "directory, out of the index alone, which touches no file, as "
            "the gate's own line does, since git mv would carry the section "
            f"of {GITMODULES} that gives its path along under the same name, "
            "and with that section taken out, a gitlink no section names "
            "would stop a plain clone's git submodule update --init "
            f"--recursive (`{UNSTAGE}{' --sparse' if out else ''}"
            f"{' -f' if force else ''} -- {quoted}`"
            + (f", {SPARSE_RM_GIT}" if out else "")
            + (f", {FORCED_SAID}" if force else "") + ")"]


def _second_checkout_part(found: list[Spelled]) -> list[str]:
    """`_spellings_refusal`'s part that names each checkout a second path
    taken out of the index leaves on disk (`UNSTAGE_SECOND` with
    `checkout`), to be deleted by hand in the same round, with the `git -C
    <path> status` that shows what is in it alone, before the update that
    closes the remedy, or empty (rv865b's round-2 SHOULD 1).

    A checkout `git mv` of the member's own mount made there names the
    member's store, `.git/modules/members/<P>`, and the update, checking
    the member out at its row's path, points that store's `core.worktree`
    there: `git -C <variant> status` then printed nothing while a file not
    committed was in it, and the next run said to delete it, as #828's move
    back found and orders its closing sentences against. Named before the
    update, its status still names that file."""
    left = sorted({spelled.target for spelled in found
                   if spelled.remedy == UNSTAGE_SECOND and spelled.checkout})
    if not left:
        return []
    named = " and ".join(f"`{target}`" for target in left)
    status = " or ".join(f"`git -C {shell_quoted(target, 'posix')} status`"
                         for target in left)
    return ["delete by hand each checkout that git rm --cached of a second "
            f"path leaves on disk, {named}, once nothing only it holds is "
            "needed, rather than move it, and before any update below: its "
            ".git file names its store by a path relative to it, which a move "
            "would leave pointing nowhere, its commits are kept in that "
            "store, so only what is not committed is in it alone "
            f"({status} shows it), and the update points a store it may share "
            "with the row at the row's path, after which that status shows "
            "the row's checkout instead"]


def _removed(found: list[Spelled], by: dict[str, list[str]]) -> bool:
    """Whether the index's removals (`UNSTAGE`, `UNSTAGE_SECOND`) leave a
    change to commit: only where HEAD holds what they remove, as it does
    once the pending change is committed; an entry staged and never
    committed leaves nothing to commit."""
    taken = (UNSTAGE, UNSTAGE_SECOND)
    return any(by[remedy] for remedy in taken) and (bool(by[COMMIT]) or any(
        spelled.committed for spelled in found if spelled.remedy in taken))


def _each(command: str, targets: list[str]) -> str:
    """One printed `<command> -- <target> <new name>` for each of `targets`,
    each quoted for a POSIX shell (#532)."""
    return " and ".join(
        f"`{command} -- {shell_quoted(target, 'posix')} <new name>`"
        for target in targets)


def _lead(path: str, found: list[Spelled], mount: bool) -> str:
    """What `_spellings_refusal` says the holder holds, before the places:
    a case variant of the mount path `path` (`mount`); a path at or under
    another spelling of `members/`; a case variant of a row's path under
    `members/` itself (#840); or the last two together. What is set aside is
    at a row's path or at `members`, no spelling of either, and says
    nothing here."""
    if mount:
        return (f"the family root holds a case variant of {path}, the same "
                "path on a case-insensitive disk, though no `members:` row "
                "names it")
    firsts = {spelled.name.partition("/")[0] for spelled in found
              if spelled.remedy not in SET_ASIDE}
    row = (f"a case variant of the path of a `members:` row under "
           f"{MEMBERS_DIR}/, the same path as that row's on a "
           "case-insensitive disk")
    if firsts == {MEMBERS_DIR}:
        return f"the family root holds {row}"
    return (f"the family root holds a path at or under another spelling of "
            f"{MEMBERS_DIR}/, which a case-insensitive disk takes for "
            f"{MEMBERS_DIR}/ itself"
            + (f", and {row}" if MEMBERS_DIR in firsts else ""))


def _gitmodules_part(gitmodules: str) -> list[str]:
    """`_spellings_refusal`'s first part, for the work tree's `.gitmodules`
    as `_gitmodules_beside` found it (`gitmodules`), or empty: a change
    nobody has staged, staged (#685); a copy the work tree lacks, put back
    from the index (#685); a deletion staged while HEAD holds one, put back
    from HEAD, as `remove`'s `gitmodules-missing` puts it back (#840).
    A list, empty or of one, as each part helper here returns."""
    said = {
        GITMODULES_MODIFIED: (
            f"stage the change to {GITMODULES} that nobody has staged, or set "
            "it aside, since `git mv` and `git rm` of a gitlink refuse to run "
            f"beside one (`git add -- {GITMODULES}`)"),
        GITMODULES_MISSING: (
            f"put back the copy of {GITMODULES} the index holds, which the "
            "work tree lacks, since git edits each member's section there "
            f"(`git checkout -- {GITMODULES}`)"),
        GITMODULES_DELETED: (
            f"put back HEAD's copy of {GITMODULES}, in the index and the work "
            "tree, since its deletion is staged and the work tree lacks it: "
            "git edits each member's section there, and any commit would "
            "take the deletion, and every member's section with it, out of "
            f"HEAD (`git checkout HEAD -- {GITMODULES}`)"),
    }.get(gitmodules)
    return [said] if said else []


def _link_part(by: dict[str, list[str]]) -> list[str]:
    """`_spellings_refusal`'s part that moves a symbolic link the index
    holds entries under out of the way first (`LINK_OUT`, #840), or empty;
    `by` is its targets by remedy. In the words `member-path-unaddable` has
    for `members` itself: a plain directory of the holder's own."""
    if not by[LINK_OUT]:
        return []
    return ["move each symbolic link that the index holds entries under out "
            f"of the way first ({_each(MOVE, by[LINK_OUT])}), which moves the "
            f"link and not what it names: every member is mounted under "
            f"{MEMBERS_DIR}/, which must be a plain directory of the holder's "
            "own, and git goes through the link, where `git rm --cached` of a "
            "gitlink under it fails (`not a git repository`), since a "
            "checkout where it points names its store by a path relative to "
            "it"]


def _checkout_first_part(by: dict[str, list[str]]) -> list[str]:
    """`_spellings_refusal`'s part that names each checkout inside a
    directory a `git mv` or `mv` below moves, to be deleted by hand first
    (`CHECKOUT_FIRST`, #840), or empty; `by` is its targets by remedy."""
    if not by[CHECKOUT_FIRST]:
        return []
    named = " and ".join(f"`{target}`" for target in by[CHECKOUT_FIRST])
    status = " or ".join(f"`git -C {shell_quoted(target, 'posix')} status`"
                         for target in by[CHECKOUT_FIRST])
    return ["first delete by hand each checkout git does not track inside a "
            f"directory moved below, {named}, once nothing only it holds is "
            "needed: git mv and mv of a directory move everything in it, "
            "and would leave the checkout's .git file, which names its store "
            "by a path relative to it, pointing nowhere, while its commits are "
            "kept in that store, so only what is not committed is in it alone "
            f"({status} shows it)"]


def _point_back_part(found: list[Spelled], by: dict[str, list[str]],
                     earlier: bool = False) -> list[str]:
    """`_spellings_refusal`'s parts that point back each section found
    `IN_SECTION` (`POINT_BACK`, #840) and take out each found
    `BESIDE_SECTION` (`TAKE_OUT`, rv865's MUST 1), or empty; `by` is its
    targets by remedy. Each commits where HEAD's copy holds what it changes,
    or where `earlier`, a commit printed before it, takes a staged
    `.gitmodules` into HEAD: a pending change, or the index's rename or
    removal, and, for the take-out, the point-back's own commit (rv865b's
    NIT 3: HEAD kept a section staged to be taken out, the gate passed, and
    the holder pushed before the next `add` carried it)."""
    parts = []
    pointed = sorted({(name, spelled.target) for spelled in found
                      if spelled.remedy == POINT_BACK
                      for name in spelled.sections})
    if pointed:
        committed = _committed(found, POINT_BACK, earlier)
        parts.append(
            f"point each section of {GITMODULES} that gives a member another "
            "spelling of its row's path back at that path, where the index "
            "records the member's gitlink there already, since add would "
            f"commit that {GITMODULES} beside the new member and a recursive "
            "clone finds no section for the member's path "
            f"({_section_lines(pointed)}, then `git add -- {GITMODULES}`)"
            + committed)
        earlier = earlier or bool(committed)
    taken = {name: spelled.keys for spelled in found
             if spelled.remedy == TAKE_OUT for name in spelled.sections}
    if taken:
        unset = " and ".join(
            f"`git config -f {GITMODULES} --unset-all "
            f"{shell_quoted(f'submodule.{name}.{key}', 'posix')}`"
            for name in sorted(taken) for key in taken[name])
        parts.append(
            f"take out each section of {GITMODULES} that gives another "
            "spelling of a row's path beside the section that gives that path "
            "itself, every key it holds, as the gate's own lines do, so a "
            "submodule later given its name inherits none of them: add would "
            f"commit that {GITMODULES} beside the new member, a disk that "
            "folds case takes the two paths for one, and git rm --cached of "
            f"a gitlink at that path leaves it ({unset}, then `git add -- "
            f"{GITMODULES}`)" + _committed(found, TAKE_OUT, earlier))
    return parts


def _committed(found: list[Spelled], remedy: str, earlier: bool) -> str:
    """`, and commit that` where a part of `remedy` leaves a change to
    commit: `earlier`, or what it acts on `committed`; else empty."""
    return (", and commit that" if earlier or any(
        spelled.committed for spelled in found if spelled.remedy == remedy)
        else "")


def _section_lines(pointed: list[tuple[str, str]]) -> str:
    """The `git config -f .gitmodules submodule.<name>.path <row path>`
    line for each `(name, row path)` in `pointed`, as the gate prints it
    (`member-gitmodules-absent`), each quoted for a POSIX shell (#761)."""
    return " and ".join(
        f"`git config -f {GITMODULES} "
        f"{shell_quoted(f'submodule.{name}.path', 'posix')} "
        f"{shell_quoted(row, 'posix')}`" for name, row in pointed)


def _update_sentence(rows: list[str]) -> str:
    """The update that checks each member out at its row's path in `rows`
    where nothing is checked out there, as in a fresh clone (#761), last."""
    return (f"then, where nothing is checked out at {' or '.join(rows)}, as "
            "in a fresh clone, `git submodule update --init --recursive` "
            "checks the member out there")


def _set_aside_part(found: list[Spelled], by: dict[str, list[str]]) -> str:
    """`_spellings_refusal`'s part that sets aside what is in the way of the
    move back (#761), or empty; `by` is its targets by remedy. `git mv`,
    `git mv --sparse` and `git rm -r --cached`, each `--sparse` said as the
    index's own are (Codex's P2 1 on #828)."""
    aside = [spelled for spelled in found if spelled.remedy in SET_ASIDE]
    if not aside:
        return ""
    how = []
    if by[ASIDE]:
        how.append("rename each that is on disk as the index holds it with "
                   f"`git mv` ({_each(RENAME, by[ASIDE])})")
    if by[ASIDE_SPARSE]:
        how.append("rename each that the sparse checkout leaves out with `git "
                   f"mv --sparse`, {SPARSE_MV_GIT} "
                   f"({_each(RENAME_SPARSE, by[ASIDE_SPARSE])})")
    if by[ASIDE_OUT]:
        quoted = " ".join(shell_quoted(target, "posix")
                          for target in by[ASIDE_OUT])
        out = any(spelled.sparse for spelled in aside
                  if spelled.remedy == ASIDE_OUT)
        how.append("take each that is not on disk so out of the index, which "
                   f"touches no file (`{UNSTAGE}{' --sparse' if out else ''} "
                   f"-- {quoted}`" + (f", {SPARSE_RM_GIT}" if out else "")
                   + ")")
    # Unmerged (#840): every stage out of the index, then the file moved.
    unmerged = sorted({*by[ASIDE_UNMERGED], *by[ASIDE_UNMERGED_MV]})
    if unmerged:
        quoted = " ".join(shell_quoted(target, "posix") for target in unmerged)
        how.append("take each that is unmerged out of the index, every stage, "
                   "which touches no file, since `git mv` refuses a conflicted "
                   f"entry (`{UNSTAGE} -- {quoted}`)"
                   + (", then move what of it is on disk out of the way ("
                      f"{_each(MOVE, by[ASIDE_UNMERGED_MV])})"
                      if by[ASIDE_UNMERGED_MV] else ""))
    named = ", ".join(f"`{spelled.name}` ({spelled.kind})"
                      for spelled in aside)
    return ("set aside first what the index holds in the way of the move of a "
            f"member's gitlink below, {named}, since git's update-index "
            "replaces a file at the path it records without a word and fails "
            f"beside one under it or at {MEMBERS_DIR} itself, and taking the "
            "gitlink out instead un-registers the member: "
            + " and ".join(how))


def _move_back_parts(found: list[Spelled], by: dict[str, list[str]]
                     ) -> tuple[str, list[str]]:
    """`(the part, the closing sentences)` of `_spellings_refusal` that move
    each member's own gitlink back to its row's path (#646, #761), or empty
    ones; `by` is its targets by remedy. Per row, every variant found, the
    index's before HEAD's, the first of which names the commit; the move is
    committed where it, a pending change or what is set aside leaves a
    change to commit. Each row a section is pointed back to (`POINT_BACK`,
    #840) is checked out by the same closing update."""
    moved = {row: [spelled for spelled in found
                   if spelled.remedy == RESTORE and spelled.target == row]
             for row in by[RESTORE]}
    if not moved:
        # A section pointed back with no move back closes on the update
        # alone, for a fresh clone (#840).
        return "", ([_update_sentence(by[POINT_BACK])] if by[POINT_BACK]
                    else [])
    variants = sorted(spelled.name for held in moved.values()
                      for spelled in held)
    committed = bool(by[COMMIT]) or any(
        spelled.committed for spelled in found
        if spelled.remedy == RESTORE or spelled.remedy in SET_ASIDE)
    rows = {spelled.name: row for row, held in moved.items()
            for spelled in held}
    # A section pointed back beside the move (#840) is checked out by the
    # same update.
    return (_move_back_line(moved, variants, committed),
            _closing_sentences(variants, rows,
                               sorted({*moved, *by[POINT_BACK]})))


def _move_back_line(moved: dict[str, list[Spelled]], variants: list[str],
                    committed: bool) -> str:
    """The move back's own part, `moved` the variants by row: the variants
    taken out of the index, each row's gitlink recorded at the commit named,
    each section a `git mv` of a mount left naming a variant pointed back,
    and the commit where `committed`."""
    pairs = " and ".join(
        f"`{name}` for the row {row}" for row in moved
        for name in sorted(spelled.name for spelled in moved[row]
                           if spelled.where != IN_GITMODULES))
    # A member whose removal is staged (#761), put back at HEAD's commit.
    staged = " and ".join(
        f"{row}, whose section gives `{spelled.name}`"
        for row, held in moved.items() for spelled in held
        if spelled.where == IN_GITMODULES)
    recorded = " and ".join(
        "`git update-index --add --cacheinfo "
        f"{shell_quoted(f'160000,{held[0].recorded},{row}', 'posix')}`"
        for row, held in moved.items())
    taken_out = " ".join(shell_quoted(name, "posix") for name in variants)
    # `--sparse` only where a variant needs it, so that everywhere else the
    # line is the validator's word for word (#646's review, S1), and `-f`
    # likewise (#761): measured, `git rm --cached` refused a staged variant
    # whose checkout held one commit, or one untracked file, of its own
    # (`staged content different from both the file and the HEAD`, exit 1),
    # and took it with `-f`, touching no file.
    every = [spelled for held in moved.values() for spelled in held]
    flag = " --sparse" if any(spelled.sparse for spelled in every) else ""
    force = any(spelled.forced for spelled in every)
    # Each section a `git mv` of a mount left naming the variant (#761).
    pointed = sorted({(name, row) for row, held in moved.items()
                      for spelled in held for name in spelled.sections})
    sections = _section_lines(pointed)
    moves = []
    if pairs:
        moves.append("move each member's gitlink held only under another "
                     f"spelling of its row's path, {pairs}, to that path, at "
                     "the commit it records")
    if staged:
        moves.append("put back at its row's path each member's gitlink whose "
                     f"removal is staged though a section of {GITMODULES} "
                     f"gives it another spelling, {staged}, at the commit "
                     "HEAD records")
    return (
        ", and ".join(moves) + ", in the index alone, which touches no file"
        + (f", and point each section of {GITMODULES} that gives one of them "
           "another spelling of its row's path, as a `git mv` of its mount "
           "leaves it, at that path" if pointed else "")
        + f" (`git rm -r --cached{flag}{' -f' if force else ''} "
        f"--ignore-unmatch -- {taken_out}`, "
        + (f"{SPARSE_RM_GIT}, " if flag else "")
        + (f"{FORCED_SAID}, " if force else "")
        + f"then {recorded}"
        + (f", then {sections} and `git add -- {GITMODULES}`" if pointed
           else "") + ")"
        + (", and commit that" if committed else ""))


def _closing_sentences(variants: list[str], rows: dict[str, str],
                       moved: list[str]) -> list[str]:
    """The move back's closing sentences (#681, #761), after every other
    remedy: what a directory left at a variant is, its guarded `mv`, where a
    checkout's commits are kept and that it is deleted by hand, a clone of
    its own moved out whole, and the update, last. `rows` is each variant's
    row path, and `moved` the rows."""
    # #839's form, the validator's: a link there is always moved, the link
    # alone (rv865b's NIT 4); nothing there moves nothing and exits 0
    # (Codex's P2 2 on #828): a plain `mv` of it failed and stopped the
    # update.
    guarded = " and ".join(
        f"`[ ! -L {shell_quoted(name, 'posix')} ] && {{ "
        f"[ ! -e {shell_quoted(name, 'posix')} ] || "
        f"[ {shell_quoted(name, 'posix')} -ef "
        f"{shell_quoted(rows[name], 'posix')} ] || "
        f"[ -e {shell_quoted(name + '/.git', 'posix')} ]; }} || mv -- "
        f"{shell_quoted(name, 'posix')} "
        f"{shell_quoted('../' + name.replace('/', '-'), 'posix')}`"
        for name in variants)
    status = " or ".join(f"`git -C {shell_quoted(name, 'posix')} status`"
                         for name in variants)
    unpushed = " or ".join(
        f"`git -C {shell_quoted(name, 'posix')} log --oneline HEAD "
        "--branches --not --remotes`" for name in variants)
    return [
        f"a directory left at {' or '.join(variants)} is the row's own where "
        "the disk folds case, as macOS's and Windows' usually do and a Linux "
        "mount can (WSL's /mnt/c)",
        "where the disk holds the two apart it stays there, untracked, and "
        "add refuses it as family-members-dir-variant: move each one that is "
        "there out of the holder, in a POSIX shell (Git Bash on Windows), "
        f"{guarded}, which moves nothing where nothing is there, where the "
        "two names are one directory or where it holds a .git entry, a "
        "checkout, and moves a symbolic link there wherever it points, the "
        "link and never what it points at",
        "a checkout there that git submodule add or git mv made holds a .git "
        "file naming its store by a path relative to it, which a move would "
        "leave pointing nowhere: its commits are kept under this holder's "
        ".git/modules/, in the directory its .git file names, whatever "
        "becomes of the checkout, and only what is not committed is in the "
        f"checkout alone ({status} shows it, except where a plain mv brought "
        "the checkout to that path: git cannot open it there, so check its "
        "files by hand), so delete such a checkout by hand once nothing only "
        "it holds is needed, before the update below, which points a store "
        "the row shares at the row's path",
        "a checkout whose .git is a directory, a clone of its own, holds its "
        f"commits there and nowhere else, and {unpushed} lists the ones not "
        "pushed: move it out of the holder whole, by hand, rather than delete "
        "it",
        _update_sentence(moved)]


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
    spec = None
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
    try:
        listed = git_out(["config", "-z", *source, "--list"], cwd=root,
                         binary=True)
    except Refusal as exc:
        remedy = GITMODULES_UNREADABLE
        if spec is not None:
            # NONE IN THE WORKING TREE: git read the index's copy, or HEAD's,
            # and that copy, put back, is the file to mend.
            index = spec.startswith(":")
            remedy += (f" With no {GITMODULES} in the working tree, git read "
                       f"{'the index' if index else 'HEAD'}'s copy: put it "
                       f"back first, `git checkout {'' if index else 'HEAD '}"
                       f"-- {GITMODULES}`.")
        raise Refusal(
            "gitmodules-unreadable",
            f"{GITMODULES} could not be read as git reads it: {exc.detail}",
            remedy) from exc
    found: dict[str, dict[str, str]] = {}
    for record in listed.split(b"\0"):
        key, _, value = record.decode("utf-8",
                                      "surrogateescape").partition("\n")
        section, _, variable = key.rpartition(".")
        if section.startswith("submodule."):
            found.setdefault(section[len("submodule."):], {})[variable] = value
    return {name: (keys["path"], keys.get("url"), tuple(keys))
            for name, keys in found.items() if "path" in keys}


def _members_file_left_in_head(root: Path, path: str) -> Refusal | None:
    """`member-path-unaddable` for a `members` FILE that HEAD holds and the
    work tree no longer does, or None (#684, #612's review E1): the move
    `_members_is_a_file`'s remedy names (`git mv -- members <new name>`),
    staged and not committed, or the file's removal, staged; or its
    deletion from the work tree, not staged, which the index still holds.

    IT PASSED EVERY CHECK, AND THE ADD'S COMMIT TOOK HALF OF IT. Nothing is
    at `members` on disk or in the index, so the mount went ahead, and its
    commit, which names `.gitmodules`, the mount path and `family.yaml`,
    took the deletion of the file into itself, git putting a directory
    where the file was (`D members` beside `A members/<Project>`), and left
    the new name staged alone, half a move in the holder's history
    (measured by #612's review). The change is the person's and is committed
    on its own first, as #363 has a change HEAD holds and the index no
    longer does committed first (`_spellings_refusal`). HEAD's ROOT TREE is
    asked, `git ls-tree` with no path (`_tree_entries`); a holder with no
    commit yet holds nothing there.

    THE DELETION NOT STAGED is the same commit: the index still holds the
    file, nothing but a directory a hand made there, if any, is at
    `members` on disk, and the mount's `git submodule add`, putting a
    directory where the file was, takes the entry out of the index, so the
    commit says `D members` all the same. It is taken out of the index,
    which touches no file, and the removal committed, as #318 takes out of
    the index what has nothing on disk (`UNSTAGE`). Not moved with the `git
    mv` the issue proposed, which fails there (`fatal: bad source`, exit
    128, measured on git 2.43), nor put back first with `git checkout --
    members`, which would put the file back over such a directory and take
    the directory away. A link on disk is left to git's own dry run, which
    refuses a path beyond one.

    ONE A SPARSE CHECKOUT MARKS OR LEAVES OUT (#761, Codex's P2 1 on #828)
    is off disk the same way, and the removal takes `--sparse`, which says
    the git it needs: plain `git rm --cached` refuses it (`exist outside of
    your sparse-checkout definition`, exit 1, measured on git 2.43 and
    2.47.1), as `_set_aside` names such an entry off disk."""
    held = [kind for name, kind in _index_entries(root, MEMBERS_DIR)
            if name == MEMBERS_DIR]
    if any(kind != "a file" for kind in held) or (
            held and os.path.islink(root / MEMBERS_DIR)):
        return None
    try:
        head = _tree_entries(root, "HEAD")
    except Refusal:
        return None
    if not any(name == MEMBERS_DIR and kind == "a file"
               for name, kind, _ in head):
        return None
    if held:
        sparse = MEMBERS_DIR in _skip_worktree(root) or bool(
            _sparse_rules_exclude(root, [MEMBERS_DIR]))
        return Refusal(
            "member-path-unaddable",
            f"git would add the mount path {path} and take `{MEMBERS_DIR}` "
            f"out of the holder with it: `{MEMBERS_DIR}` is a file HEAD and "
            "the index hold and the work tree no longer does, "
            + ("as the sparse checkout leaves it out" if sparse else
               "its deletion not staged")
            + ", and the add's mount, putting a directory where the file "
            "was, would take it out of the index, and its commit would take "
            f"that deletion into itself (`D {MEMBERS_DIR}`). No git command "
            "that writes was run and nothing was written.",
            f"Remediation: every member is mounted under {MEMBERS_DIR}/, "
            "which must be a plain directory of the holder's own. Take the "
            "file out of the index, which touches no file (`git rm --cached "
            + (f"--sparse -- {MEMBERS_DIR}`, {SPARSE_RM_GIT}" if sparse else
               f"-- {MEMBERS_DIR}`")
            + "), and commit the removal on its own first "
            "(`git commit`, with nothing else staged: a bare `git commit` "
            "takes every staged change, and `git status` lists them), since "
            f"the add's own commit names {GITMODULES}, {path} and {MANIFEST} "
            "alone, and run the same command again.")
    return Refusal(
        "member-path-unaddable",
        f"git would add the mount path {path} and take `{MEMBERS_DIR}` out of "
        f"the holder with it: `{MEMBERS_DIR}` is a file HEAD holds and the "
        "index no longer does, a move or a removal staged and not committed, "
        "and the add's commit, putting a directory where the file was, would "
        f"take that deletion into itself (`D {MEMBERS_DIR}`) and leave any "
        "new name staged alone. No git command that writes was run and "
        "nothing was written.",
        f"Remediation: every member is mounted under {MEMBERS_DIR}/, which "
        "must be a plain directory of the holder's own. Commit that change "
        "on its own first (`git commit`, with nothing else staged: a bare "
        "`git commit` takes every staged change, and `git status` lists "
        f"them), since the add's own commit names {GITMODULES}, {path} and "
        f"{MANIFEST} alone, and run the same command again.")


def _members_is_a_file(root: Path, path: str) -> Refusal:
    """`member-path-unaddable` for a `members` that is a FILE (#612, 574/5):
    what it says, and the move that makes room. A file git tracks is moved
    with `git mv` and the move committed first. Left staged, the move is not
    left alone by the add: its commit names three paths, and git, putting a
    directory where the file was, takes the deletion half of the move into
    that commit (`A .gitmodules`, `M family.yaml`, `D members`, `A
    members/<Project>`) and leaves the new name staged alone (`A
    members-file`), which is half a move in the holder's history (#612's
    review, N3). One git does not track is moved with `mv`.

    ONE THE INDEX HOLDS UNMERGED (#840, rv828's SHOULD 3), which `git mv`
    refuses (`fatal: conflicted, source=members`, exit 128, measured on git
    2.43), is taken out of the index, every stage, with `git rm --cached`,
    which touches no file, and then moved with `mv`; the removal is
    committed on its own first where HEAD holds the file, as
    `_members_file_left_in_head` would ask next."""
    records = _index_records(root).get(MEMBERS_DIR.encode(), [])
    tracked = bool(records)
    unmerged = any(record.split()[2] != b"0" for record in records)
    if unmerged:
        try:
            in_head = any(name == MEMBERS_DIR and kind == "a file"
                          for name, kind, _ in _tree_entries(root, "HEAD"))
        except Refusal:
            in_head = False
        move = (f"take it out of the index, every stage, which touches no "
                f"file, since `git mv` refuses a conflicted entry (`git rm "
                f"--cached -- {MEMBERS_DIR}`), then move it aside, `mv -- "
                f"{MEMBERS_DIR} <new name>`"
                + (", and commit the removal on its own first, since the "
                   f"add's own commit names {GITMODULES}, {path} and "
                   f"{MANIFEST} alone" if in_head else ""))
    else:
        move = (f"move the file aside, `{'git mv' if tracked else 'mv'} -- "
                f"{MEMBERS_DIR} <new name>`"
                + (", and commit the move on its own first, since the add's "
                   f"own commit names {GITMODULES}, {path} and {MANIFEST} "
                   "alone" if tracked else ""))
    return Refusal(
        "member-path-unaddable",
        f"git will not add the mount path {path}: `{MEMBERS_DIR}` is "
        f"{'a tracked' if tracked else 'an untracked'} file in the family "
        "root, not a directory, so nothing can be mounted under it, and "
        "`git submodule add` would fail at its mount (`Not a directory`) "
        "after the member was read. No git command that writes was run and "
        "nothing was written.",
        f"Remediation: every member is mounted under {MEMBERS_DIR}/, which "
        f"must be a plain directory of the holder's own. {move[0].upper()}"
        f"{move[1:]}, and run the same command again.")


def _gitmodules_first(root: Path, spelled: list[Spelled]) -> str:
    """What `_spellings_refusal` says first of the work tree's `.gitmodules`
    for what `_members_spellings` found (`spelled`), as `_gitmodules_beside`
    tells it apart, or a refusal of its own that comes first.

    WHERE A REMEDY RUNS `git mv` OR `git rm` OF A GITLINK (#685), OR POINTS A
    SECTION BACK OR TAKES ONE OUT WITH `git config -f` (#761, #840), a
    change to the file nobody has staged is staged first, and a copy the
    work tree lacks put back from the index. So is a copy a sparse checkout
    marks, as `gitmodules-sparse`, where a section is pointed back or taken
    out: `git config -f` would write a new file of that one line, or find no
    section to take out, and `git add` refuses the file there.

    WHEREVER ANYTHING IS FOUND, since every commit the remedy prints meets
    them (#840): an unmerged copy is `gitmodules-unstaged`'s to name, with
    its own restore, first, git cannot rewrite it, nor read conflict
    markers, and a `git add` of it stages them, and one the work tree lacks
    too is `gitmodules-missing`'s, as `remove` names it
    (`_gitmodules_missing`): typed as printed, the rename back's commit
    failed (`Committing is not possible because you have unmerged files`,
    measured on git 2.43). A deletion staged while HEAD holds one is put
    back from HEAD first, `GITMODULES_DELETED`: typed as printed, the rename
    back's commit took it, and every member's section, out of HEAD, and the
    gate found `member-gitmodules-absent` for each member. With a copy in
    the work tree that git does not track, which copy to keep is the
    person's, so `gitmodules-unstaged` names it first: the move back's
    commit took the deletion as well."""
    beside = _gitmodules_beside(root)
    pointed = any(spelled_one.sections for spelled_one in spelled)
    if beside == GITMODULES_UNMERGED and not os.path.lexists(
            root / GITMODULES):
        raise _gitmodules_missing(
            "add", {stage for _, _, stage in _gitmodules_in_index(root)},
            _head_oid(root, GITMODULES) is not None)
    if beside in (GITMODULES_UNMERGED, GITMODULES_UNTRACKED) or pointed and any(
            tag.upper() == "S" for tag, _, _ in _gitmodules_in_index(root)):
        _checked_gitmodules_as_staged(root, "add")
        return ""
    if beside in (GITMODULES_MODIFIED, GITMODULES_MISSING) and not (
            pointed or any(spelled_one.where == IN_INDEX
                           and spelled_one.kind == INDEX_ENTRY_KINDS[0o160000]
                           for spelled_one in spelled)):
        return ""
    return beside


def _rows_paths(rows: list[dict]) -> frozenset[str]:
    """The path of every `members:` row that has one of its own (#646): the
    one path `_member_path` gives it, `members/<project>`. A row it refuses
    is `member-path`'s, and has none to be moved back to."""
    paths = set()
    for row in rows:
        project = row.get("project")
        if not isinstance(project, str):
            continue
        try:
            paths.add(_member_path(project, row))
        except Refusal:
            continue
    return frozenset(paths)


def _checked_mount_path(root: Path, project: str, path: str,
                        rows: frozenset[str] = frozenset()) -> None:
    """Every refusal about the MOUNT PATH, made before the member is read or
    anything is mounted (#242). `rows` is `_rows_paths` of the holder's
    `members:` rows.

    `git submodule add` makes each of these refusals on its own. But the
    mount passes `--force`, to get past the operator's ignore rules (see
    `_mount_and_pin`), and `--force` turns them off or moves them to after
    the clone. So each is asked here first, the way git asks it, and named:

    - SOMETHING AT THE PATH. On disk, by a listing of `members/` in which
      the path's own spelling is found (`_members_on_disk`, #364), so a
      dangling link counts as well as a directory a half-finished add or a
      hand left there; and by `lexists` too, last of all, for a directory no
      listing could read. `members/` is listed under whichever spelling this
      disk keeps it (`_members_dir_on_disk`): on macOS and Windows that can
      be `Members`, one directory with `members/`, and the path in it is
      there all the same — unless the index holds it under that other
      spelling, which the next two questions name. In the INDEX, any entry
      at the path or under it, in any case, with nothing on disk in its own
      spelling: given `--force`, git accepts a gitlink there and replaces it
      with the member's, and whatever the human had staged is gone without
      a word. That takes it out of the index (#318); a variant that IS on
      disk is renamed with a committed `git mv` instead, below.
    - ANOTHER SPELLING OF `members/` OR OF THE PATH, ANYWHERE (#362, #363,
      #364): in the index, in HEAD and no longer in the index, or on disk
      untracked, `_members_spellings` reads it and `_spellings_refusal`
      names it, with a remedy for each entry and never for the other
      spelling's own directory, which on macOS and Windows holds the
      members. Brett Heap ruled on 2026-10-14, "Refuse on every disk":
      macOS and Windows hold `Members/` and `members/` as one directory, and
      with `core.ignorecase` set git files a new member's gitlink in the
      spelling it already holds, which the add's commit, naming the path,
      then cannot record (#362) or records where `.gitmodules` and
      `family.yaml` do not say (#363). So it is refused on all three, Linux
      included, where a `Members/` of a holder's own is harmless until a
      clone of it is made on the other two; the cost is that such a holder
      renames it first. `member-path-taken` where a path is a case variant
      of the mount path, `family-members-dir-variant` where it is under a
      spelling of `members/` alone. A member's own gitlink held only under
      another spelling of its row's path keeps that code, since the add is
      refused for it as for any path there, and its remedy moves it back to
      the row's path instead (#646), with its section of `.gitmodules`
      where that names the other spelling too; and a section that does,
      for a member whose gitlink's removal is staged, is named as found in
      `.gitmodules` (#761).
    - A FILE NAMED `members` (#612, 574/5). Git's own dry run, below, does
      not refuse it (measured on git 2.43), and the mount's `git submodule
      add --force` then dies cloning into it (`could not create leading
      directories ... Not a directory`), after the member was read, and the
      unwind restores the holder. It is asked of the listing already made
      (`_members_on_disk`): `members` itself, spelled so and a file. It is
      refused as `member-path-unaddable`, the code of a mount path git will
      not take, whose remediation says already that `members/` must be a
      plain directory of the holder's own (a link and a submodule are the
      other two ways it is not). A file under another spelling of `members`
      is `_members_spellings`'s, below. One HEAD holds and the work tree no
      longer does, its move or removal staged and not committed, or its
      deletion not staged, is refused under the same code
      (`_members_file_left_in_head`, #684): the add's commit took the
      deletion half of that change into itself.
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
    taken = Refusal(
        "member-path-taken",
        f"{path} already exists in the family root but no `members:` row "
        "names it",
        "Remediation: this is a half-finished add or a hand-made "
        "directory. Remove it (`git rm -r` if it is tracked), then re-run.")
    on_disk = _members_on_disk(root)
    canon = _members_dir_on_disk(root, on_disk)
    if on_disk.get(MEMBERS_DIR, ("",))[0] == "a file":
        raise _members_is_a_file(root, path)
    moved = _members_file_left_in_head(root, path)
    if moved is not None:
        raise moved
    held = _index_entries(root, path)
    # Each spelling of the mount path the index holds other than its own,
    # and whether git tracks a directory there.
    variants = {(name[:len(path)],
                 len(name) > len(path) or kind == "a submodule")
                for name, kind in held if name[:len(path)] != path}
    if canon is not None and project in (on_disk[canon][1] or ()) and (
            canon == MEMBERS_DIR or not variants):
        raise taken
    if held and not any(_on_disk_as_named(root, variant, directory)
                        for variant, directory in variants):
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
        spellings = sorted({entry[0][:len(path)] for entry in held})
        # QUOTED (#486), each one: it names an index entry somebody else
        # made, and that is not held to a member's alphabet.
        spelled = " ".join(shell_quoted(name) for name in spellings)
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
            + ("then " if spellings == [path] else
               "where HEAD holds it too, commit that removal first, since the "
               f"add's own commit names {path} alone: otherwise HEAD keeps "
               "the other spelling beside the member, or, with "
               "`core.ignorecase` set, records the member's gitlink under a "
               f"spelling other than the {path} that {GITMODULES} and "
               f"{MANIFEST} say, or both; then ")
            + "re-run.")
    spelled = _members_spellings(root, project, on_disk, rows)
    if spelled:
        raise _spellings_refusal(path, spelled,
                                 _gitmodules_first(root, spelled))
    # A DIRECTORY NO LISTING COULD READ hides nothing: `lexists` asks the
    # path itself, as it always did, after every listing has answered.
    if os.path.lexists(root / path):
        raise taken
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
            f"out, by hand, then `git add {GITMODULES}` and re-run. Mounting "
            f"over the name would rewrite its section to point at {project} "
            f"(git before 2.51), or mount {project} under another name this "
            "tool does not follow (git 2.51 and later, with the `--force` "
            "this tool mounts with).")
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


def _deletion(store: Path) -> list[str]:
    """The lines that let a person delete an object store `git rm` left
    behind: the directory alone on its own line, to be checked before
    anything is pasted, then the one command that deletes it and nothing
    else (#486).

    THE ONE DESTRUCTIVE COMMAND THIS FILE PRINTS, and it printed its path
    bare: under a holder at `.../my work/Sonata/Sonata` a shell split `rm
    -rf .../my work/Sonata/Sonata/.git/modules/members/Beacon` into `rm -rf
    .../my`, an absolute directory that is NOT the store (a `Code` beside
    the `Code Projects` the holder is in), and a second argument relative to
    wherever the person stood. So its one argument is quoted, by
    `repo_shape.shell_quoted`, for the POSIX shell `rm -rf` is a command of
    (Git Bash is one on Windows; PowerShell refuses `-rf` and deletes
    nothing), and the sentence says which shell.

    NAMED IN POSIX, as git spells `.git/modules/<path>` and as the person
    who retypes it does.
    """
    shown = store.as_posix()
    return ["It is this directory:", f"    {shown}",
            "and in a POSIX shell (Git Bash on Windows) this deletes it and "
            "nothing else:", f"    rm -rf {shell_quoted(shown, 'posix')}"]


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
    _checked_mount_path(family.root, project, path,
                        _rows_paths(family.members))
    # Then a work tree's `.gitmodules` that is not the index's copy (#407):
    # `git submodule add` writes the member's section into it and stages all
    # of it, so a change nobody staged went into the commit too. Asked after
    # the mount path's refusals, which name what they find in the same file.
    _checked_gitmodules_as_staged(family.root, "add")
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
            "re-run. "
            + "\n".join(_deletion(cached))
            + "\nIt is left behind by `git rm` on purpose, which is why this "
            "tool will not remove it for you.")
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


def _row_recording(family: Family, project_id: str,
                   besides: str | None = None) -> dict | None:
    """The first row that records `project_id` as its `id:`, or None, asked
    the way `_checked_member_id` says the validator asks it: a row with no
    `project:` or no `id:`, and a row whose `project:` an earlier row
    already spells exactly, are skipped.

    `besides` IS THE `project:` OF THE ROW `bump` MOVES, spelled exactly
    (#541). `bump` replaces that row, and every row spelled the same way,
    with the one it writes, so the id it records today is no other
    project's; every other row is asked as `add` asks it.
    """
    projects: set[str] = set()
    for row in family.members:
        name = row.get("project")
        if not isinstance(name, str) or not name or name in projects:
            continue
        projects.add(name)
        if name != besides and row.get("id") and \
                str(row["id"]) == project_id:
            return row
    return None


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
    row = _row_recording(family, project_id)
    if row is not None:
        name = row["project"]
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


def _names_no_commit(code: str, flag: str, value: str, kind: str,
                     repository: str, where: str) -> Refusal:
    """The refusal for a `--at` or `--to` whose 40 hex names a tree or a
    blob in the member, or an annotated tag of one: `kind` is what it names
    once any tag is peeled (`<id>^{}`), and `where` is where `git log` lists
    the commits to pass instead.

    ONE WORDING FOR `add --at` AND `bump --to` (#541). The two worded a tag
    of a tree differently, `names a tree` and `is an annotated tag of a
    tree`. `bump` now peels a tag of a commit as `add` does, so it names a
    tag of a tree as `add` does too, by the tree it tags (`_probe_commit`),
    and each verb keeps only its own code.
    """
    return Refusal(
        code, f"{flag} {value} names a {kind} in {repository}, not a commit",
        "Remediation: pass the commit itself — `git log --format=%H` in "
        f"{where} lists them. A tree's or a blob's sha is part of a commit "
        "and never one, and a pin is a commit or it is nothing.")


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
        raise _names_no_commit("member-at-unknown", "--at", at, kind,
                               repository, "the member") from missing
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
    commit's pathspec then matches nothing. `_checked_mount_path` refuses
    such an index before the mount now (#362); this stays behind it, for
    anything else git stages under a name no step names. So the WHOLE index
    is recorded too, and `undo` compares it after its steps. Only when the
    two agree does the sentence say the holder is as it was. When they do
    not, it names what differs and sends the human to `git ls-files -s`,
    and the one command that changes anything, `git rm -r --cached`,
    touches no file.
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
                 trailers: list[str], suggested: str) -> int:
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
    `bump --dry-run` does for the checkout's own refusal. A file a sparse
    checkout leaves out never gets here: `_checked_add_target` refuses it
    first (`gitmodules-sparse`, #407), since that restore would not work.
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
    for line in _branch_said(family, "add", suggested):
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

    IN THIS ORDER, AND ONLY THIS ORDER: an act git has unfinished in the holder
    (`_checked_no_operation_in_progress`, #612), a `family.yaml` holding a
    change HEAD does not (`_checked_manifest_committed`, #684), the holder's
    refusals (`_checked_add_target`, which includes a `members` that is a file,
    `_checked_mount_path`, #612), the paths the sparse rules leave out
    (`_checked_inside_sparse_rules`, #612), then the branch the commit lands
    on, which the real run refuses on the tracking branch or none
    (`_checked_branch`, #487) and a dry run only reports, then the clone URL
    `--local-remote-dir` makes, which `.gitmodules` will hold
    (`_refuse_an_unwritable_member_url`, #693), then the member's
    (`_probe_member`, of a throwaway clone), then the member's id against the
    rows (`_checked_member_id`, #330), and only then the mount, the pin and the
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
    # A merge, cherry-pick, revert, rebase or `am` unfinished in the holder
    # is asked after `Family.open`, which parses `family.yaml` (so a merge
    # conflicted there reads as `yaml-unparsable`, #612 N4), and before every
    # refusal about the holder's own state: the commit goes wrong however
    # the rest is, refused after the writes or made inside the act (#612,
    # 571(e)).
    _checked_no_operation_in_progress(family.root, "add")
    # A `family.yaml` holding a change HEAD does not, staged or not, next:
    # the commit would take it beside the row (#684).
    _checked_manifest_committed(family.root, "add")
    at = _checked_add_target(family, repository, project, path, args.at)
    # What the sparse rules leave out, after the refusals that read the same
    # paths by their marks (`gitmodules-sparse`), before the member is read.
    _checked_inside_sparse_rules(family.root, "add",
                                 [GITMODULES, path, MANIFEST])
    suggested = _suggested_branch("add", project)
    branch = None if args.dry_run else _checked_branch(family, "add",
                                                         suggested)

    url = _member_url(repository, args.local_remote_dir)
    # THE CLONE URL IS A PATH `.gitmodules` WILL HOLD (#693): asked as
    # `init` asks the holder's (#433), before the member is read or anything
    # is mounted, and `--dry-run` refuses alike.
    _refuse_an_unwritable_member_url(args.local_remote_dir is not None, url)
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
                            protocol, commit, at, args.trailer, suggested)

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
    _print_next(family, branch)
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
    return at, (ref[len(HEADS_PREFIX):] if ref.startswith(HEADS_PREFIX)
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


def _checked_bumped_id(family: Family, row: dict, commit: str,
                       project_id: str) -> None:
    """`member-duplicate-id` for a `bump` whose `--to` records, in the
    member's own `project.yaml`, the `id` another row already records
    (#541): the question `add` asks since #330 (`_checked_member_id`), asked
    of the row `bump` writes.

    `bump` READ THE ID AND NEVER ASKED IT. A member whose `project.yaml` at
    `--to` records another member's id was committed, exit 0, and the
    holder's own `validate-family.py` then refused it as
    `member-duplicate-id`. So the dry run and the real run both ask it,
    before the checkout, of the id `_member_id_at` reads from the member's
    objects, and the real run asks it again of the id its checkout reads,
    which is what the row records: a linked `project.yaml`, which only a
    checkout reads through, is refused there and put back like any other
    refusal after the first write (#365).

    THE MEMBER'S OWN ROW IS NOT ASKED (`_row_recording`'s `besides`): the
    bump replaces it, so the id it records today is no other project's.
    Every other row is asked as `add` asks it, so `bump` refuses what the
    gate would refuse and nothing it would pass.
    """
    project = str(row["project"])
    held = _row_recording(family, project_id, besides=project)
    if held is None:
        return
    repository = row.get("repository")
    raise Refusal(
        "member-duplicate-id",
        f"{repository} at {commit[:12]} is already a member of "
        f"{family.data.get('name')} under another name: its project.yaml "
        f"there records id {project_id!r}, and the row {held['project']} "
        f"pins {held.get('repository')} with that id. Bumping {project} to "
        "it would pin one project twice, which `validate-family.py` refuses",
        "Remediation: a family pins each project once. Pass `--to` a commit "
        f"of {repository} whose project.yaml records an id no other row "
        f"records. If {repository} and {held.get('repository')} are one "
        f"project, `family.py remove --member {held['project']}` takes the "
        "other row out first. Two projects that record one id are a fault in "
        "one of their `project.yaml` files, mended in that project, not in "
        "the family.")


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

    WHAT THE DRY RUNS ASK GIT WITH (#326). `git_out`'s failure was a
    `Refusal` that carried `repo_shape`'s default remediation, which was a
    LEG's (run `validate-pins.py`, advance `contracts/<leg>-pin.yaml`), and
    a holder has neither; since #370 it carries none. A `CommandFailed` is
    printed as every failed git command in this file is: the exact command,
    where, and git's own words, exit 2, which is how the real run reports the
    same failure.
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


def _on_a_remote_branch(member: Path, commit: str) -> bool:
    """Whether `commit` is reachable from one of the member's remote-tracking
    branches, `refs/remotes/origin/*` (#613): the refs `bump`'s `git fetch
    origin` has just updated, every branch of `origin` whatever refspec the
    mount carries and none `origin` has deleted since (#686), or, when that
    fetch failed, the ones the mount already had.

    THE QUESTION `bump-leg.py`'s `on_a_remote_branch` ASKS OF A LEG, in the
    same git words, `for-each-ref --contains` over `refs/remotes/origin/`,
    and under the same name. Written again here rather than called: that
    file's name has a hyphen, so it is loaded only by path, which would run a
    whole command-line tool's top level for one `git for-each-ref`, and no
    module both tools import (`repo_shape`, `shape_materialize`) holds the
    question. This file asks it here and nowhere else.

    A FAILURE OF THE QUESTION ITSELF IS GIT'S, never an answer: `run` raises
    it as `CommandFailed`, quoted as every failed git command in this file
    is, exit 2, before anything is written. It is asked only of an id the
    member holds as a commit, so `--contains` has an object to walk from.
    """
    return bool(run(["git", "for-each-ref", "--contains", commit,
                     "--format=%(refname)", "refs/remotes/origin/"],
                    cwd=member))


#: What `bump`'s fetch always asks of `origin` (#686): every branch, into the
#: namespace `_on_a_remote_branch` reads, forced as a remote-tracking ref is.
_ORIGIN_BRANCHES = "+refs/heads/*:refs/remotes/origin/*"


def _origin_fetch_refspecs(member: Path) -> list[str]:
    """The refspecs `bump`'s fetch of `origin` carries (#686): every branch of
    `origin`, then what the mount's own `remote.origin.fetch` keeps under
    `refs/remotes/origin/`, and none of what it excludes.

    WHY THE MOUNT'S OWN ARE ADDED. `--prune` deletes every ref under
    `refs/remotes/origin/` that no refspec on the command line maps a ref of
    `origin` to, and a refspec on the command line replaces the configured
    ones. A mount that keeps pull requests there (`+refs/pull/*/head:
    refs/remotes/origin/pr/*`) lost them to a prune made for a deleted
    branch, in a dry run too, where `git fetch origin` kept them, pruning
    only what its own refspec maps. So each positive refspec of the mount
    whose destination is under `refs/remotes/origin/` goes on the command
    line as well, forced as the first is (a remote-tracking ref only mirrors
    the remote, and a refspec without `+` would fail the fetch on a branch
    force-pushed), and is pruned only against itself. Beyond the branches the
    first refspec is there for, that asks `origin` for nothing `git fetch
    origin` did not. One whose destination is outside `refs/remotes/origin/`,
    a mirror's `+refs/*:refs/*` or `+refs/heads/*:refs/heads/*`, is never
    added, so no refspec this fetch names writes outside it. A ref put under
    `origin/` by hand, which no refspec maps, is still pruned.

    A NEGATIVE REFSPEC (`^refs/heads/wip`) IS SKIPPED. A narrowing refspec
    never decides reachability (#686): a positive one that leaves a branch
    out is overridden by the first refspec, as R613 p07 found it must be, and
    a negative one is left out, so that it does not decide either. Git
    applies the configured negative refspecs only to a fetch with none on the
    command line (measured, git 2.43), so skipping is enough. Honouring it
    refused a commit only the excluded branch reaches with #613's words,
    "reachable from no branch of <repository>", which are untrue there: the
    branch is on the remote.

    A mount whose refspec git cannot satisfy, one that names a ref `origin`
    lacks or two that map to one destination, fails this fetch as it fails
    the person's own `git fetch origin`, and `bump` says so as it says any
    failed fetch. One refspec of the mount's own can also clash with the
    first, which that `git fetch origin` never meets: a mount whose only
    refspec maps tags into `origin/` (`+refs/tags/*:refs/remotes/origin/*`),
    and a remote with a branch and a tag of one name, fail this fetch with
    128 ("Cannot fetch both refs/heads/feat and refs/tags/feat to
    refs/remotes/origin/feat") where `git fetch origin` exits 0. That is
    left for #459's checklist.

    READ BY A LISTING, `git config --list`, not `--get-all`: the dry run's
    test holds every `git config` it runs to a listing, the one form that
    cannot write, and a listing exits 0 whether or not the mount has a
    refspec (an `origin` with a URL and nothing else has none, and gets the
    first refspec alone). A config git cannot read fails it with 128, which is
    the caller's fetch failure, as the fetch's own would be.
    """
    listed = run(["git", "config", "--list"], cwd=member)
    configured = [value for key, _, value in
                  (line.partition("=") for line in listed.splitlines())
                  if key == "remote.origin.fetch"]
    refspecs = [_ORIGIN_BRANCHES]
    for spec in (value.strip() for value in configured):
        if spec.startswith("^"):
            continue  # a narrowing refspec never decides reachability (p07)
        spec = spec if spec.startswith("+") else "+" + spec
        if not spec.partition(":")[2].startswith("refs/remotes/origin/"):
            continue
        if spec not in refspecs:
            refspecs.append(spec)
    return refspecs


def _has_origin(member: Path) -> bool:
    """Whether the member's mount has a remote named `origin`, the only one
    `bump` fetches and asks (#686). Asked once its fetch has failed: a mount
    whose `origin` was renamed (to `upstream`, say) or removed fails that
    fetch with no network or credential at fault, and was told to fix one.

    `git remote get-url origin` exits 2 for "No such remote" and for nothing
    else, so that exit is the answer "none"; any other failure is git's,
    raised as `CommandFailed` and quoted, exit 2, before anything is written.
    """
    try:
        run(["git", "remote", "get-url", "origin"], cwd=member)
    except CommandFailed as exc:
        if exc.code == 2:
            return False
        raise
    return True


def _origin_tag_reaches(member: Path, commit: str) -> bool:
    """Whether a tag of the member's `origin` reaches `commit` (#686, #982):
    a tag the mount has whose commit contains it, at a commit `origin` lists
    a tag at too. Asked only for the refusal's words, after a fetch that
    worked, of a commit no branch of `origin` reaches; the rule stays
    branches.

    WHY IT IS ASKED. Such a commit was refused with "A pin the rest of the
    world cannot fetch", which is untrue of one a tag of the remote holds: a
    fresh clone brings every tag, so it holds the commit, and a fetch by sha
    works. The mount's own tags cannot say it alone: a tag made inside the
    mount is one only the mount has, so `git ls-remote --tags` asks `origin`
    whether it has one of them, or a tag at a commit one of them names, by
    object id, which names a tag's target for ever. Only when a tag of the
    mount contains the commit is the remote asked, so a commit made in the
    mount and never tagged asks nothing more. A listing that fails is no
    answer, and the words stay the plain ones.

    THE COMMITS TAGS POINT TO ARE COMPARED, NOT THE TAG OBJECTS ALONE (#982).
    An annotated tag's own id is the id of its tag object, which two tags at
    one commit have apart when each was made on its own, and which a
    lightweight tag does not have at all, so comparing them alone missed a
    lightweight `v1` of the mount beside an annotated `v1` of `origin` at
    the same commit, and two annotated `v1` made apart (measured, git
    2.43). Each tag of the mount is read as its own id and as the commit
    `git rev-parse <id>^{}` peels it to, through a tag of a tag too;
    `%(*objectname)` would not do, since git before 2.44 reads `*` one
    level, to the tag a tag of a tag tags (measured, git 2.43). `origin` is
    listed WITHOUT `--refs`, so each annotated tag has its `<tag>^{}` line,
    the commit, beside its own, and a lightweight tag has its own line, the
    commit. Every id on either side is compared, so the tag object of a tag
    the two share still matches as it did. `bump-leg.py`'s
    `_remote_tag_reaches`, asked of a leg, reads it the same way.
    """
    tags = run(["git", "for-each-ref", "--contains", commit,
                "--format=%(objectname)", "refs/tags/"],
               cwd=member).lower().split()
    if not tags:
        return False
    held = set(tags) | set(run(["git", "rev-parse",
                                *[f"{tag}^{{}}" for tag in tags]],
                               cwd=member).lower().split())
    try:
        listed = run(["git", "ls-remote", "--tags", "origin"], cwd=member)
    except CommandFailed:
        return False
    return any(line.split("\t", 1)[0].lower() in held
               for line in listed.splitlines())


def _origin_back(path: str, repository: str | None) -> str:
    """What a mount with no `origin` is told to do (#686): give it back, and
    why nothing else will do."""
    return (f"give {path} back a remote named `origin`, for {repository}, "
            "and run the same command again: `bump` fetches the member's "
            "branches from `origin` and asks no other remote")


def _checked_on_a_remote_branch(member: Path, path: str,
                                repository: str | None, typed: str,
                                commit: str, fetched: bool) -> str:
    """`commit`, the commit `--to` (`typed`) names, when a branch of the
    member's remote reaches it, or the refusal `member-to-local-only` (#613),
    which `_checked_to_names_a_commit` says why it makes. `typed` is not
    `commit` where an annotated tag was peeled: the refusal names both, since
    the line saying what the tag names is printed only once this returns.

    The words are `bump-leg.py`'s `bump-leg-commit-local-only`, said of a
    member: where the commit is, what it is not reachable from, to push it to
    a branch and run the same command again, and why. When the fetch failed
    they end with its stale-refs sentence, adapted: the answer came from
    remote-tracking refs the fetch did not refresh, so a commit pushed since
    may be refused here, and the network or the credential is the thing to
    fix before believing it.

    TWO STATES THOSE WORDS WERE UNTRUE OF (#686), each said as what it is,
    with the rule and the code kept. A commit a TAG of the remote reaches
    (`_origin_tag_reaches`) is refused as one no branch reaches, which it
    is, with the way out, a push to a branch, and without "a pin the rest of
    the world cannot fetch", which a fresh clone disproves. A mount with NO
    `origin` (`_has_origin`) failed its fetch with no network at fault: the
    words say it has none, that whether a branch reaches the commit is
    therefore not known, and to give the mount its `origin` back, since
    `bump` asks no other remote, where they said the commit was on no branch
    and to fix the network or the credential.
    """
    if _on_a_remote_branch(member, commit):
        return commit
    named = (f"--to {commit}" if typed == commit else
             f"--to {typed} is an annotated tag, and the commit it names, "
             f"{commit},")
    if not fetched and not _has_origin(member):
        raise Refusal(
            "member-to-local-only",
            f"{named} is in the member's own object store, in {path}, but "
            f"{path} has no remote named `origin`, so whether a branch of "
            f"{repository} reaches it is not known",
            f"Remediation: {_origin_back(path, repository)}. If the commit "
            f"is not pushed yet, push it to a branch of {repository} first.")
    if fetched and _origin_tag_reaches(member, commit):
        raise Refusal(
            "member-to-local-only",
            f"{named} is in the member's own object store, in {path}, and a "
            f"tag of {repository} reaches it, but no branch of {repository} "
            "does",
            f"Remediation: push it to a branch of {repository} and run the "
            "same command again: `bump` pins only a commit a branch of the "
            "member's remote reaches, and a tag is not a branch.")
    stale = ("" if fetched else
             f" The fetch of {path} FAILED, as the note above says, so this "
             "was answered from stale remote-tracking refs: fix the network "
             "or the credential and run it again before believing it.")
    raise Refusal(
        "member-to-local-only",
        f"{named} is in the member's own object store, in {path}, but is "
        f"reachable from no branch of {repository}",
        f"Remediation: push it to a branch of {repository} and run the same "
        f"command again; the commonest such commit was made inside {path} and "
        "never pushed. A pin the rest of the world cannot fetch is a family "
        "the rest of the world cannot bootstrap." + stale)


def _checked_to_names_a_commit(member: Path, path: str, row: dict,
                               commit: str, fetched: bool) -> str:
    """The COMMIT `--to` names in the member's objects: `--to` itself, or the
    commit an annotated tag's own id names (#541), a commit a branch of the
    member's remote reaches (#613), or the refusal saying why there is none.
    `bump` and `bump --dry-run` both ask it, after the fetch (`fetched` False
    when it failed) and before the dry run leaves or the checkout, so the two
    runs go on with one commit or make one refusal, and the holder is left
    byte for byte as it was.

    AN ANNOTATED TAG'S OWN ID IS PEELED, as `add --at` peels one (Brett
    Heap, 2026-10-14, on #541). It is 40 hex, and it is what `git rev-parse
    v2` prints for a release tag. Once the checkout peeled it while the row
    recorded the tag's id as typed, so `bump` committed a holder its own
    `validate-family.py` refused as `member-gitlink-mismatch`; #405 made
    both runs refuse it instead, naming the commit for the person to type.
    A tag object's id fixes its content, so it names one commit for ever
    and, unlike a tag NAME, cannot be moved. The caller goes on with that
    commit, in both runs, so the gitlink, the row's `commit:`, the digest
    and the commit message carry it and never the tag's id. `^{}` peels
    through a tag of a tag too.

    A TREE OR A BLOB IS NAMED AS ONE, and so is a tag of either, in `add
    --at`'s words (`_names_no_commit`): its id is in the member, so "not
    pushed" would send the person looking for a push that is not missing.
    Before #405 both runs failed on it in git's words, exit 2.

    AN ID THE MEMBER DOES NOT HOLD AFTER THE FETCH is refused
    `member-to-unknown` (#541), saying to push it first. The dry run's
    resolve and the real run's checkout failed on it in git's words,
    `fatal: reference is not a tree`, exit 2, which never said what was
    wrong: the commonest such `--to` is a commit made in the member's
    working clone beside the holder and not pushed yet, and the fetch of the
    mount brings only what the member's remote has. When that fetch failed,
    the refusal says so and does not claim the remote lacks it.

    A COMMIT THE MEMBER HOLDS THAT NO BRANCH OF ITS REMOTE REACHES is
    refused `member-to-local-only` (#613: the triage's D2, option 1, which
    Brett Heap approved at 2026-10-15T16:49:38Z). The object check alone,
    `cat-file -t`, passed a commit made inside `members/<Project>` and never
    pushed, because the object is in the mount's own store: `bump` pinned
    it, exit 0, `validate-family.py` passed, and the holder could then be
    bootstrapped nowhere else, since nobody else can fetch that commit.
    `bump-leg.py` refuses its twin as `bump-leg-commit-local-only`, and the
    question is its question (`_on_a_remote_branch`): REACHABILITY, NOT A
    FETCH THAT EXITED 0, which proves nothing about one object. It is asked
    after the peel, of the commit a tag names, which the refusal names, and
    only of a commit: an id the member does not hold keeps
    `member-to-unknown`, and a tree, a blob or a tag of either keeps its own
    words. WHEN THE FETCH FAILED it is answered from the remote-tracking
    refs the mount already has, as `bump-leg.py` answers it, and a bump is
    never refused for being offline: a commit those refs contain is pinned,
    after the note that the fetch failed, and one they do not is refused with
    the sentence that says the answer came from stale refs. A mount with no
    `origin` at all is told that instead, in this refusal and in
    `member-to-unknown`'s (#686): its fetch failed with no network or
    credential at fault.

    A TAG WHOSE COMMIT IS ON NO BRANCH is refused too, and so is that
    commit, while `add --at` pins the same tag's id. Where the mount does
    not hold it, it is `member-to-unknown`: the fetch here brings every
    branch and, by git's own rule, only the tags that point into the
    history those branches bring, while `add`'s bare clone brings every tag,
    and a `git push origin v2` without the branch makes one. Where the mount
    does hold it, a tag made in the mount or one its own clone brought, it
    is `member-to-local-only` (#613), naming the commit the tag names: no
    branch of the remote reaches it. Either way the refusal's push to a
    branch is what lets `bump` pin it. Left as it is: `bump-leg.py` refuses
    its twins the same two ways, as `bump-leg-commit-not-on-remote` and
    `bump-leg-commit-local-only`, and fetching every tag would write refs the
    person's member did not have, which is a new act; reachability from a
    tag is not the question either tool asks. Where a tag of the remote
    reaches the commit, the refusal says so (#686), and still refuses: that
    tag is asked for the words, never for the rule.

    SO A PIN `add --at` MADE FROM SUCH A TAG cannot be named by `bump --to`
    again: its clone brought the tag, so the mount holds the commit, and a
    re-run that said `nothing to do`, or `validate-family.py`'s own repair
    of a digest that does not recompute, is `member-to-local-only` too.
    Accepted as ruled (D2, option 1; D1 of #625's review, option (a)):
    pushing the commit to a branch of the member lets the same command
    through, and `bump-leg.py` refuses its twin alike. Exempting a `--to`
    equal to the row's own pin would need a new ruling.
    """
    repository = row.get("repository")
    try:
        kind = run(["git", "cat-file", "-t", commit], cwd=member)
    except CommandFailed:
        kind = None
    if kind is None and fetched:
        raise Refusal(
            "member-to-unknown",
            f"--to {commit} is not a commit any branch of {repository} "
            f"reaches: {path} fetched from its origin and holds no object "
            "with that id",
            f"Remediation: push it first, to a branch of {repository}, and "
            "run the same command again. A pin the rest of the world cannot "
            "fetch is a family the rest of the world cannot bootstrap. If it "
            "is pushed, check the commit: it belongs to the member's "
            "ASSEMBLY ROOT, not to one of its legs.")
    if kind is None and not _has_origin(member):
        raise Refusal(
            "member-to-unknown",
            f"--to {commit} is not a commit {path} holds, and {path} has no "
            "remote named `origin` to fetch it from, so whether a branch of "
            f"{repository} reaches it is not known",
            f"Remediation: push it first, to a branch of {repository}, if it "
            f"is not pushed yet; {_origin_back(path, repository)}. A pin the "
            "rest of the world cannot fetch is a family the rest of the world "
            "cannot bootstrap.")
    if kind is None:
        raise Refusal(
            "member-to-unknown",
            f"--to {commit} is not a commit {path} holds, and its fetch from "
            f"its origin failed, so whether a branch of {repository} reaches "
            "it is not known",
            f"Remediation: push it first, to a branch of {repository}, if it "
            f"is not pushed yet; make {repository} readable from here — if it "
            "is PRIVATE, check `gh auth status` or your SSH key — and run the "
            "same command again. A pin the rest of the world cannot fetch is "
            "a family the rest of the world cannot bootstrap.")
    if kind == "commit":
        return _checked_on_a_remote_branch(member, path, repository, commit,
                                           commit, fetched)
    peeled, names = "", ""
    if kind == "tag":
        try:
            peeled = run(["git", "rev-parse", "-q", "--verify",
                          f"{commit}^{{}}"], cwd=member).lower()
            names = run(["git", "cat-file", "-t", peeled], cwd=member)
        except CommandFailed:
            peeled, names = "", ""
        if names == "commit":
            return _checked_on_a_remote_branch(member, path, repository,
                                               commit, peeled, fetched)
    named = names if kind == "tag" else kind
    if named in ("tree", "blob"):
        raise _names_no_commit("member-to-not-a-commit", "--to", commit,
                               named, repository, path)
    raise Refusal(
        "member-to-not-a-commit",
        f"--to {commit} is an annotated tag in {repository}, not a commit",
        "Remediation: pass the commit itself — `git log --format=%H` in "
        f"{path} lists them. A pin is a commit or it is nothing.")


def _bump_dry_run(family: Family, row: dict, path: str, commit: str,
                  trailers: list[str], fetched: bool, suggested: str) -> int:
    """`bump --dry-run`, entered after the member is fetched (or the fetch
    failed, `fetched` False, and said so) and before it is checked out
    (#326): the answers a real `bump` gives, and no write.

    THE REAL RUN'S QUESTIONS, IN ITS ORDER, ASKED OF THE MEMBER'S OBJECTS.
    `commit` is the one `_checked_to_names_a_commit` returned, which both
    runs asked after the fetch: an annotated tag's own id is already peeled,
    an id the member does not hold is already refused (#541), and so is a
    commit it holds that no branch of its remote reaches (#613). It is
    resolved as the checkout would take it (`^{commit}`, which is what `git
    checkout` accepts). The manifest is read by `_member_id_at`, its id is
    asked against the other rows by `_checked_bumped_id` as the real run
    asks it (#541), and the digest is computed by `tree_digest`, which reads
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
    else:
        _checked_bumped_id(family, row, commit, project_id)
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
    for line in _branch_said(family, "bump", suggested):
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
    # Asked again of THIS reading, which is the id the row records (#541),
    # as `add` asks it of its mount's: a linked `project.yaml` is read
    # through only here, and a refusal is put back like any other.
    _checked_bumped_id(family, row, commit, project_id)
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
    `project.yaml` at `--to`, read from its objects (`_member_id_at`), the
    id it records against the other rows (`_checked_bumped_id`, #541), and
    a `members:` block this tool will not rewrite.

    THE REAL RUN ASKED THEM AFTER ITS FIRST WRITE, OR NEVER. A `--to` whose
    tree has no `project.yaml` was refused `member-not-a-project` with the
    member left checked out at `--to`, which the holder's own validator then
    reported, while `bump --dry-run` refused the same commit and changed
    nothing; and an id another row records was committed. Asked here, before
    the rollback is even recorded, the two runs refuse at the same point in
    the same words, and the holder is byte for byte as it was. A `--to` the
    member's objects do not hold never gets here: `_checked_to_names_a_commit`
    refused it after the fetch (#541), as it refused a commit no branch of
    the member's remote reaches (#613). A symbolic link is left to the read
    through the checkout, as the dry run leaves it, and `_bump_and_pin` asks
    the id of that reading.
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
    else:
        _checked_bumped_id(family, row, commit, project_id)
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
    # BEFORE `member-uninitialized`, whose remedy a merge in progress or a
    # sparse checkout that leaves the mount out would make wrong (#612).
    _checked_no_operation_in_progress(family.root, "bump")
    _checked_manifest_committed(family.root, "bump")
    _checked_inside_sparse_rules(family.root, "bump", [path, MANIFEST])
    if not (member / ".git").exists():
        raise Refusal(
            "member-uninitialized",
            f"{path} is not an initialized submodule checkout, so the new "
            "commit cannot be resolved or digested",
            "Remediation: `git submodule update --init " + path + "`, or "
            "`make bootstrap`, which resolves a credential for a private "
            "member first.")
    # THE BRANCH BEFORE THE FETCH (#487): the real run's commit needs one
    # that is not the tracking branch, and a refusal is cheaper before the
    # member's remote is asked anything. The dry run reports it instead.
    suggested = _suggested_branch("bump", str(row.get("id") or project),
                                  commit)
    branch = None if args.dry_run else _checked_branch(family, "bump",
                                                         suggested)
    # EVERY BRANCH OF `origin`, BY AN EXPLICIT REFSPEC (#686), as
    # `bump-leg.py` fetches a leg: a plain `git fetch origin` obeys the
    # mount's own `remote.origin.fetch`, and one narrowed by hand (a
    # single-branch clone, or an `origin` with a URL and no refspec) left no
    # remote-tracking ref for the branch that holds `--to`, so a pushed
    # commit was refused `member-to-local-only` as on no branch.
    # AND NO REF NOTHING ON `origin` BACKS (#686; #459's line 105, on Brett
    # Heap's word "prune the fetch the tool already makes"): a branch deleted
    # on the remote after the last fetch kept its remote-tracking ref, which
    # passed the reachability check for a commit nothing on the remote may
    # keep. `--prune` drops every ref under `refs/remotes/origin/` that no
    # refspec of this fetch maps a ref of `origin` to, so the mount's own
    # refspecs that write there ride along (`_origin_fetch_refspecs`): a pull
    # request ref its configuration keeps is kept and pruned only against its
    # own refspec, as `git fetch origin` did. A ref put there by hand, which
    # no refspec maps, is dropped, and `origin/HEAD` stays, dangling where it
    # named a deleted branch. `--no-prune-tags` keeps a `pruneTags` setting
    # from reaching the mount's tags. The prune touches no local branch or
    # tag.
    fetched = True
    try:
        run(["git", "fetch", "-q", "--prune", "--no-prune-tags", "origin",
             *_origin_fetch_refspecs(member)], cwd=member)
    except CommandFailed:
        fetched = False
        why = (" from its origin" if _has_origin(member) else
               ": it has no remote named `origin`")
        print(f"  note: could not fetch {path}{why}; the commit must already "
              "be in its object store and on a branch of its remote as last "
              "fetched", file=sys.stderr)
    # WHAT `--to` NAMES IS ASKED OF THE FETCHED OBJECTS (#405, #541), before
    # the dry run leaves and before the checkout. From here on `commit` is
    # the one it returns, in both runs: an annotated tag's own id is peeled
    # to the commit it names, and said; an id the member does not hold, a
    # tree or a blob is refused alike, with nothing in the holder moved.
    # `suggested` keeps the id as typed: the real run's branch refusal named
    # it before the fetch, and the dry run's `branch` line names the same.
    # The line says WOULD BE PINNED: the dry run prints it, and so does a
    # run refused by a question asked after it, and neither pins anything.
    typed = commit
    commit = _checked_to_names_a_commit(member, path, row, typed, fetched)
    if commit != typed:
        print(f"--to {typed[:12]} is an annotated tag in "
              f"{row.get('repository')}; the commit it names, "
              f"{commit[:12]}, is what would be pinned", flush=True)
    if args.dry_run:
        return _bump_dry_run(family, row, path, commit, args.trailer,
                             fetched, suggested)
    _checked_bump_target(family, row, path, commit)
    rollback = PinRollback(family.root, path, "bump", (MANIFEST,))
    code = _put_back_on_failure(rollback, lambda: _bump_and_pin(
        family, row, path, commit, args.trailer, rollback))
    if code == 0:
        _print_next(family, branch)
    return code


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


def _gitmodules_in_index(root: Path) -> list[tuple[str, str, int]]:
    """`(tag, blob, stage)` of every record the holder's index holds for
    `.gitmodules`, as `git ls-files -s -v -z` lists them (#407). `tag` is
    git's `-v` letter for the entry: `S` where it is marked skip-worktree,
    and a lower-case letter where it is marked assume-unchanged. `stage` is
    0 for a merged entry and 1, 2 or 3 for an unmerged one. The whole index,
    with no pathspec, as `_index_records` reads it, and nothing is written.
    """
    listed = git_out(["ls-files", "-s", "-v", "-z"], cwd=root, binary=True)
    found = []
    for record in listed.split(b"\0"):
        meta, _, name = record.partition(b"\t")
        if name == GITMODULES.encode():
            tag, _, blob, stage = meta.decode("ascii").split()
            found.append((tag, blob, int(stage)))
    return found


def _stages_as(root: Path, blob: str) -> bool:
    """Whether git would stage the work tree's `.gitmodules` as `blob`: a
    regular file, not a link, whose bytes `git hash-object` reads as that
    blob through the file's own attributes, which is how `git add` reads
    them. Without `-w` it writes nothing."""
    if not stat.S_ISREG(os.lstat(root / GITMODULES).st_mode):
        return False
    hashed = _git_bytes(["hash-object", f"--path={GITMODULES}", "--",
                         GITMODULES], root)
    return hashed.decode("ascii").strip() == blob


#: What `gitmodules-missing` says of each verb (#407), `add`'s before a
#: spelling remedy alone (#840).
MISSING_SAID = {
    "add": (f"The remedy for what `add` found under another spelling of "
            f"{MEMBERS_DIR}/ edits each member's section in the work tree's "
            f"{GITMODULES}, and its commit fails while an entry is unmerged "
            "(`Committing is not possible because you have unmerged files`)"),
    "remove": (f"`git rm` edits only a {GITMODULES} the work tree has, and "
               f"`remove` commits {GITMODULES} as the work tree has it: "
               f"committed as it stands, {GITMODULES} would leave HEAD, and "
               "every other member's section with it, so that a recursive "
               "clone of the holder leaves each of them empty"),
}


def _gitmodules_missing(verb: str, stages: set[int],
                        in_head: bool) -> Refusal:
    """`gitmodules-missing` (#407) for `verb`, where the work tree has no
    `.gitmodules` though the index holds one at `stages` or HEAD holds one
    (`in_head`), with the restore git takes in that state: an unmerged entry
    with both sides' copies is written back with `--merge`, one with only
    one side's with `--ours` or `--theirs`, and one with neither with
    `checkout-index --stage=1`. `remove` refuses each
    (`_checked_gitmodules_as_staged`); `add` an unmerged one before a
    spelling remedy alone (`_gitmodules_first`, #840)."""
    if stages - {0}:
        held = ("the index holds one unmerged"
                + (" and HEAD holds one" if in_head else ""))
        # The restore git takes in each of these (`git checkout --merge`
        # needs both sides' copies, `--ours` and `--theirs` one each).
        if {2, 3} <= stages:
            put_back = ("write the conflicted file back, `git checkout "
                        f"--merge -- {GITMODULES}`, resolve it and stage "
                        "the result")
        elif 2 in stages:
            put_back = ("the other side deleted it, so put back this "
                        "side's copy, `git checkout --ours -- "
                        f"{GITMODULES}`, stage it")
        elif 3 in stages:
            put_back = ("this side deleted it, so put back the other "
                        "side's copy, `git checkout --theirs -- "
                        f"{GITMODULES}`, stage it")
        else:
            put_back = ("both sides deleted it, so put back the copy they "
                        "started from, `git checkout-index -f --stage=1 "
                        f"-- {GITMODULES}`, stage it")
        put_back += f", `git add {GITMODULES}`"
    elif 0 in stages:
        held = ("the index and HEAD each hold one" if in_head else
                "the index holds one")
        put_back = ("put back the index's copy, `git checkout -- "
                    f"{GITMODULES}`")
    else:
        held = "HEAD holds one and its deletion is staged"
        put_back = ("put back HEAD's copy, in the index and the work "
                    f"tree, `git checkout HEAD -- {GITMODULES}`")
    return Refusal(
        "gitmodules-missing",
        f"{GITMODULES} is not in the work tree, though {held}. "
        f"{MISSING_SAID[verb]}. No git command that writes was run and "
        "nothing was written.",
        f"Remediation: {put_back}, and run the same command again.")


def _checked_gitmodules_as_staged(root: Path, verb: str) -> None:
    """`gitmodules-missing`, `gitmodules-unstaged` and `gitmodules-sparse`
    (#407): `verb` refuses, before any git command that writes and under
    `--dry-run` alike, a work tree's `.gitmodules` that is not the copy the
    index holds.

    `remove` and `add` commit the file as git leaves it in the work tree:
    `git rm` and `git submodule add` edit the work tree's copy, and
    `_commit_one` stages what is there. So a change to it nobody staged went
    into the commit. With no file in the work tree, `git rm` edited nothing
    and `remove` committed the deletion, taking every other member's section
    out of HEAD, with exit 0, while the holder it ran in still looked whole:
    its git config kept their registrations and its gate passed. Once that
    commit was pushed, a recursive clone left each of those members empty.
    `add` committed an unstaged edit to another member's section beside the
    new one, and the whole of an untracked file in a holder with no
    `.gitmodules` yet.

    WHAT THE INDEX HOLDS IS THE PERSON'S AND GOES IN: the remediations of
    #300 and #360 have them edit the file and `git add` it before running
    the verb again. What is refused is a work tree's copy that is not the
    index's:
    - none (`gitmodules-missing`, `remove` only). Its restore is the one git
      takes in that state: an unmerged entry with both sides' copies is
      written back with `--merge`, one with only one side's with `--ours` or
      `--theirs`, and one with neither with `checkout-index --stage=1`.
    - as `gitmodules-unstaged`: one git lists as modified; one the index
      holds unmerged; one whose deletion is staged while HEAD has it; one
      the index marks assume-unchanged, which git does not compare, whose
      content `git add` would not stage as the index's blob (`_stages_as`);
      and an untracked one, which neither the index nor HEAD holds.
    - as `gitmodules-sparse`: one the index marks skip-worktree, as a sparse
      checkout that leaves the file out does. git neither compares that copy
      nor stages it (`git add` refuses a path outside the sparse checkout,
      and `git checkout -- .gitmodules` matches nothing), so `git
      sparse-checkout disable` is the restore that works as typed. `add`
      refuses it on disk or not, since `git submodule add` cannot stage it;
      `remove` refuses it where it is missing or is not the index's copy,
      and commits a clean one on disk rightly, as it did before #407. The
      MARK is all this reads: a file the rules leave out, put back on disk,
      has none, and is `_checked_inside_sparse_rules`'s (`family-sparse-
      excluded`, #612), which asks git's rules.

    "Modified" is git's own answer, `git ls-files -m`, which writes nothing:
    the comparison `git status` lists a file as modified by, and the one
    `git rm` refuses an unstaged change to the file with (`please stage your
    changes to .gitmodules`). So a copy that differs from the index only in
    its line endings is refused here as `git rm` refuses it, and the refusal
    says so where `git add` would stage the index's own blob from it. With
    neither the index, HEAD nor the work tree holding a `.gitmodules`,
    nothing is asked here; `remove` then asks `_checked_gitmodules_held`
    (#611).

    `add` LEAVES A MISSING FILE TO GIT. `git submodule add` refuses to write
    a `.gitmodules` the work tree lacks while the index or HEAD holds one,
    before it writes anything, and `add --dry-run` names that refusal in a
    note (`_add_dry_run`). A sparse checkout's is refused here first, where
    the restore that note prints would not work. BUT NOT BEFORE A SPELLING
    REMEDY (#840): `_gitmodules_first` refuses an unmerged copy missing from
    the work tree too as `gitmodules-missing` (`_gitmodules_missing`) before
    `_spellings_refusal`, whose printed commit git refuses while one is
    unmerged, with the restore git takes there, as for `remove`.
    """
    records = _gitmodules_in_index(root)
    stages = {stage for _, _, stage in records}
    tag, blob = next(((tag, blob) for tag, blob, stage in records
                      if stage == 0), ("", ""))
    in_head = _head_oid(root, GITMODULES) is not None
    on_disk = os.path.lexists(root / GITMODULES)
    if not stages and not in_head:
        if not on_disk:
            return
        raise _unstaged(
            verb, f"the work tree has a {GITMODULES} that neither the index "
            "nor HEAD holds: it is untracked, and nobody has staged it",
            "whether it belongs in the holder is a person's to say. To keep "
            f"it, stage it, `git add -f {GITMODULES}` (`-f`, since an "
            "operator's excludes may match it), and commit it on its own "
            "first if the command's commit should carry only its own change; "
            "to leave it out, move it out of the holder. Then")
    # `add` cannot stage a skip-worktree `.gitmodules` at all; `remove`
    # commits a clean one on disk rightly, as it did before #407.
    if tag.upper() == "S" and (verb == "add" or not on_disk
                               or not _stages_as(root, blob)):
        raise Refusal(
            "gitmodules-sparse",
            f"the index marks {GITMODULES} skip-worktree, as a sparse "
            "checkout that leaves it out does, so git neither compares the "
            "work tree's copy with the index's nor stages it, and "
            f"`{verb}` edits {GITMODULES} and commits it as the work tree "
            "has it. No git command that writes was run and nothing was "
            "written.",
            "Remediation: bring it back into the work tree as git compares "
            "and stages it, `git sparse-checkout disable`, which brings back "
            "every path the sparse checkout leaves out and leaves a copy "
            "already there as it is, and run the same command again.")
    staged = 0 in stages
    unmerged = bool(stages - {0})
    if not on_disk:
        if verb == "add":
            return
        raise _gitmodules_missing(verb, stages, in_head)
    keep_or_drop = (
        "which change to keep is a person's to say. To commit the work "
        "tree's copy, changes and all, {stage}; to drop its changes, put back "
        f"the index's copy, `git checkout -- {GITMODULES}`. Then")
    if unmerged:
        said = f"{GITMODULES} is unmerged in the index"
        remedy = ("resolve the conflict in it and stage the result, `git add "
                  f"{GITMODULES}`, then")
    elif not staged:
        said = (f"the work tree has a {GITMODULES} and the index does not: "
                "its deletion is staged")
        remedy = ("which copy to keep is a person's to say. To keep the work "
                  f"tree's, stage it, `git add {GITMODULES}`; to put back "
                  "HEAD's, in the index and the work tree, `git checkout HEAD "
                  f"-- {GITMODULES}`. Then")
    elif GITMODULES.encode() in _git_bytes(["ls-files", "-m", "-z"],
                                           root).split(b"\0"):
        said = (f"the work tree's {GITMODULES} is not the copy the index "
                "holds: git lists it as modified, a change nobody has staged"
                + (", though `git add` would stage the index's own content "
                   "from it: the difference may be its line endings alone"
                   if _stages_as(root, blob) else ""))
        remedy = keep_or_drop.format(
            stage=f"stage it first, `git add {GITMODULES}`")
    elif tag.islower() and not _stages_as(root, blob):
        said = (f"the work tree's {GITMODULES} is not the copy the index "
                "holds, a change nobody has staged, and git does not list it "
                "as modified: the index marks it assume-unchanged, so git "
                "does not compare it")
        remedy = keep_or_drop.format(
            stage="take the mark off and stage it first, `git update-index "
            f"--no-assume-unchanged -- {GITMODULES}` and `git add "
            f"{GITMODULES}`")
    else:
        return
    raise _unstaged(verb, said, remedy)


def _unstaged(verb: str, said: str, remedy: str) -> Refusal:
    """`gitmodules-unstaged`, around what is said of the work tree's copy
    and the remedy that leads into "run the same command again"."""
    return Refusal(
        "gitmodules-unstaged",
        f"{said}. `{verb}` edits the work tree's copy and commits "
        f"{GITMODULES} with its own change in it, so the work tree's copy "
        "must be the one the index holds: a change nobody has staged is not "
        "this command's to commit. No git command that writes was run and "
        "nothing was written.",
        f"Remediation: {remedy} run the same command again.")


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


def _checked_gitmodules_held(family: Family, path: str) -> None:
    """`member-gitmodules-absent`: `remove` refuses, before any git command
    that writes and under `--dry-run` alike, a holder that holds no
    `.gitmodules` at all, in the work tree, the index or HEAD, while its
    index records the member's gitlink at any stage (#611).

    A HOLDER WHOSE HEAD LOST `.gitmodules`, as #407's commit left one. `git
    rm` edits only a `.gitmodules` the work tree has, and `remove` commits
    the file as `git rm` leaves it, so with none anywhere the commit's `git
    add` died (`pathspec '.gitmodules' did not match any files`) after
    `deinit` and `git rm` had emptied the member, and the rollback left its
    directory empty; the dry run exited 0. `_checked_gitmodules_as_staged`
    asks nothing here, since no copy exists to compare. It asks only where
    none of the work tree, the index and HEAD holds a `.gitmodules`, and the
    index records the member's gitlink at any stage: `deinit` and `git rm`
    run on a merged or an unmerged gitlink alike, and with no `.gitmodules`
    anywhere the commit cannot stage one.

    REFUSED, NOT COMMITTED WITHOUT IT, as #407 refuses a `.gitmodules` the
    work tree lacks: the holder is left byte for byte as it was. A clone
    checks out none of its members, and the holder's own
    `validate-family.py` finds `member-gitmodules-absent` for each, so the
    remedy writes back, as `family.py add` writes one, the section of every
    member whose gitlink the index records, this one included, which
    `remove` then takes out as it always has. Staged, the file goes into
    `remove`'s commit, as #407's untracked remedy has it, unless the person
    commits it on its own first.
    """
    root = family.root
    if os.path.lexists(root / GITMODULES):
        return
    records = _index_records(root)
    if GITMODULES.encode() in records or _head_oid(root, GITMODULES):
        return
    gitlinks = {name.decode("utf-8", "surrogateescape")
                for name, held in records.items()
                if any(record.startswith(b"160000 ") for record in held)}
    if path not in gitlinks:
        return
    sections = []
    for row in family.members:
        project = str(row.get("project") or "")
        member = f"{MEMBERS_DIR}/{project}"
        if not project or member not in gitlinks:
            continue
        url = _member_url(str(row.get("repository") or ""), None)
        sections += [f"`git config -f {GITMODULES} "
                     f"{shlex.quote(f'submodule.{member}.{key}')} "
                     f"{shlex.quote(value)}`"
                     for key, value in (("path", member), ("url", url))]
    raise Refusal(
        "member-gitmodules-absent",
        f"the holder has no {GITMODULES}: neither the work tree, the index "
        f"nor HEAD holds one, though the index records a gitlink at {path}. "
        f"`git rm` edits only a {GITMODULES} the work tree has, and `remove` "
        f"commits {GITMODULES} as `git rm` leaves it, so with none to commit "
        f"it would fail after `git submodule deinit` and `git rm` had emptied "
        f"{path}. A recursive clone of the holder checks out none of its "
        "members, and its validate-family.py finds member-gitmodules-absent "
        "for each. No git command that writes was run and nothing was "
        "written.",
        "Remediation: write back the section `family.py add` writes for "
        "each member the index records, this one included, in a POSIX shell "
        f"— {' and '.join(sections)} — then stage it, `git add -f "
        f"{GITMODULES}` (`-f`, since an operator's excludes may match it), "
        "and commit it on its own first if the command's commit should "
        "carry only its own change, and run the same command again.")


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

    THE DETAIL NAMES THE LOCK AS `shown_path` NAMES A PATH (#766): it lies
    under the holder, whose path can hold an ESC or a line break. The
    remedy's `rm -f` is quoted for a shell, as it was, and still holds
    the lock's path raw inside those quotes (#459).
    """
    shown = _git_bytes(["rev-parse", "--git-path", "index.lock"],
                       root).decode("utf-8", "surrogateescape").strip()
    lock = root / shown
    if not os.path.lexists(lock):
        return
    raise Refusal(
        "family-index-locked",
        f"the holder's index is locked: {shown_path(lock.as_posix())} "
        "exists. `git submodule deinit` takes no such lock, so `remove` "
        f"would empty {path} and drop its registration and then fail at "
        "`git rm`, its first write to the index; it was refused before "
        "either, and nothing was written.",
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
        # The directory alone on a line, then the command, quoted (#486),
        # exactly as `add`'s `member-git-dir-cached` names the same store.
        print("  NOTE that member's object store is left behind. `git rm` "
              "leaves it on purpose, in case somebody committed inside the "
              "mount; delete it before adding this member back. "
              + "\n  ".join(_deletion(cached)))
    return 0


def _remove_dry_run(family: Family, row: dict, path: str,
                    suggested: str) -> int:
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

    THE NAME `deinit` DROPS IS THE ONE READ HERE (#407, the review's N9).
    `deinit` reads `.gitmodules` from the work tree, else the index's copy,
    else HEAD's; `git rm` and `_gitmodules_names` read the work tree's
    alone. With the work tree's file deleted, the dry run printed no
    registration while `deinit` dropped one. `cmd_remove` now refuses that
    state, and a work tree's copy that is not the index's, before this runs
    (`_checked_gitmodules_as_staged`). So by here the work tree's file is the
    index's copy, or none of the work tree, the index and HEAD holds one, and
    `deinit` reads what this reads.
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
    for line in _branch_said(family, "remove", suggested):
        print(line)
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
    # A merge, cherry-pick, revert, rebase or `am` unfinished in the holder
    # is asked after `Family.open`, `member-unknown` and the row's `path:`
    # check, which read the manifest, and before the refusals about the
    # holder's own files: the commit goes wrong however they are, refused
    # after the writes or made inside the act (#612).
    _checked_no_operation_in_progress(family.root, "remove")
    # A `family.yaml` holding a change HEAD does not, staged or not, next:
    # the commit would take it beside the row's removal (#684).
    _checked_manifest_committed(family.root, "remove")
    # A `.gitmodules` the work tree lacks, or has not as the index has it,
    # is refused first (#407): the commit would take it out of HEAD, or
    # carry a change nobody staged. Where the index holds a copy, every
    # reading of the work tree's file after this one reads that copy.
    _checked_gitmodules_as_staged(family.root, "remove")
    # A holder that holds no `.gitmodules` anywhere, as one whose HEAD lost
    # it does, is refused next (#611): the commit could not stage one.
    _checked_gitmodules_held(family, path)
    # A `.gitmodules` that gives the path to a second submodule is refused
    # here, before any git command that writes (#360), so the dry run makes
    # the same refusal, as it makes every one above.
    _checked_one_section(family.root, project, path)
    # The paths the commit stages, which the sparse rules may leave out
    # though the file is on disk and its mark clear (#612, 571(d)). The
    # gitlink is staged by `git rm`, which refuses it the same way.
    _checked_inside_sparse_rules(family.root, "remove",
                                 [GITMODULES, path, MANIFEST])
    # Every refusal above is the same under `--dry-run`, which leaves here,
    # before the unmount, the real run's first write (#326), and reports the
    # branch the real run refuses (#487) rather than refusing it.
    suggested = _suggested_branch("remove", str(row.get("id") or project))
    if args.dry_run:
        return _remove_dry_run(family, row, path, suggested)
    branch = _checked_branch(family, "remove", suggested)
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
    code = _put_back_on_failure(
        rollback, lambda: _unmount_and_drop(family, row, path))
    if code == 0:
        _print_next(family, branch)
    return code


# ---------------------------------------------------------------------------
# siblings
# ---------------------------------------------------------------------------


def cmd_siblings(args) -> int:
    """The holder's `make siblings`, run from a checkout of the standard.

    ONE IMPLEMENTATION, TWO ENTRY POINTS (Brett Heap, 2026-09-09, ruling 1b:
    *"One implementation, two entry points… No second code path."*). The
    implementation is the HOLDER'S OWN `scripts/siblings.py`, the pinned copy
    its Makefile's `siblings` target runs; this subcommand runs that same file
    against `--family-root`, exactly as the root `bootstrap` shim runs the
    assembly root's `scripts/bootstrap.py`: from a checkout of the standard,
    against a holder anywhere on disk.

    NOT THE STANDARD'S COPY (#543). It used to run this checkout's
    `templates/family-root/scripts/siblings.py`, through `runpy`, so a holder
    pinned at another shape ran other code under the two entry points, and
    did so inside THIS process, whose `repo_shape` its file then imported in
    place of the holder's own. So it runs as `make siblings` runs it: the
    holder's file, by this interpreter, in a process of its own, standing in
    the holder, with the holder's own `repo_shape.py` and `bootstrap.py`
    beside it, and its exit code is the one this subcommand returns,
    unchanged.

    A HOLDER WITHOUT ONE IS REFUSED BY NAME, as its Makefile refuses (#489,
    #503): `siblings-script-missing`, exit 2, before anything is cloned, in
    the Makefile's words, which name `update-shape.py` and its `--add`.
    """
    root = Path(args.family_root).expanduser().resolve()
    if not (root / MANIFEST).is_file():
        raise Refusal(
            "family-root-missing",
            f"{root / MANIFEST} does not exist, so this is not a family root",
            "Remediation: `family.py init --org <org> --family <Name>` creates "
            "one; point --family-root at the HOLDER (the `<Family>/<Family>` "
            "clone), not at the family folder around it.")
    script = root / SIBLINGS_SCRIPT
    if not script.is_file():
        raise Refusal(
            "siblings-script-missing",
            f"family.py siblings needs {SIBLINGS_SCRIPT}, which this holder "
            f"does not have: there is no {script}. It runs the holder's own "
            "copy, as `make siblings` does, and has no second implementation "
            "to fall back on, so nothing was cloned or fetched.",
            "Remediation: update-shape.py copies a changed Makefile but adds "
            "a new file only on the human's word, so a holder updated without "
            f"--add {SIBLINGS_SCRIPT} lands here. From a checkout of "
            "openRepoShape run `"
            + shlex.join(["python3", "update-shape.py", "check", "--root",
                          str(root)])
            + f"`, which reports {SIBLINGS_SCRIPT} as upstream-added. When "
            "the human says to take it, run the apply command it prints with "
            f"--add {SIBLINGS_SCRIPT} added. If it reports copy-missing "
            "instead, a pinned copy was deleted: restore it from this "
            "holder's history rather than with --add.")
    # STANDING IN THE HOLDER, AS MAKE STANDS THERE, so every word of the
    # command is a constant and none is a value from this command line: the
    # holder is the directory it runs in, and `--root .` names it. The child
    # writes into this stdout but takes its encoding from its environment,
    # not from the `reconfigure` `main()` did (#214): told this stdout's own
    # encoding and a handler that cannot raise, it escapes what the stream
    # cannot hold, as the in-process run did, instead of dying on an em dash.
    sys.stdout.flush()
    return subprocess.run(
        [sys.executable or PYTHON, SIBLINGS_SCRIPT, "--root", ".",
         *(["--dry-run"] if args.dry_run else [])],
        cwd=str(root), check=False,
        env=inherited_child_environment()).returncode


# ---------------------------------------------------------------------------


#: What `add`, `bump` and `remove` each say in `--help` about the branch
#: their commit lands on (#487).
BRANCH_RULE = ("Its ONE commit lands on the branch the holder stands on: "
               "the real run refuses the holder's tracking branch and a HEAD "
               "on no branch, naming the `git switch -c` that makes one, and "
               "ends by printing the `git push` of that branch. --dry-run "
               "runs on any branch.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="family.py", description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser(
        "init", help="create a family holder",
        description="Create a family holder. Before anything is created, "
                    "and under --dry-run alike, the family.yaml it would "
                    "write is put through the holder's own YAML reader and "
                    "its own validate-family.py: a value either would not "
                    "hold is refused and named.")
    # GITHUB'S LIMITS, said where each value is typed (#863), as the
    # scaffold says its own (#838), and asked only without
    # `--local-remote-dir`, as the plan asks them.
    init.add_argument("--org", required=True,
                      help="the organisation the holder is created in; at "
                           f"most {GITHUB_OWNER_MAX} characters without "
                           "--local-remote-dir, GitHub's limit on an "
                           "organisation's name")
    init.add_argument("--family", required=True,
                      help="the holder's name, ONE CamelCase token, e.g. "
                           "InkRouter, and its repository's: at most "
                           f"{GITHUB_NAME_MAX} characters without "
                           "--local-remote-dir, GitHub's limit on a "
                           "repository's name")
    init.add_argument("--id", default=None,
                      help="lowercase family id (default: --family "
                           f"lowercased); at most {GITHUB_ID_MAX} characters "
                           "without --local-remote-dir, as GitHub keeps the "
                           f"topic `xf-project-<id>` to {GITHUB_TOPIC_MAX}")
    init.add_argument("--name", default=None,
                      help="display name (default: --family); "
                           "validate-family.py holds it to the same rule")
    init.add_argument("--visibility", choices=VISIBILITY_CHOICES,
                      default="private")
    init.add_argument("--created-by", default=None,
                      help="the human creating the family (default: "
                           "GIT_AUTHOR_NAME, then `git config user.name`); "
                           "not blank")
    init.add_argument("--created-on", default=None,
                      help="YYYY-MM-DD (default: today)")
    init.add_argument("--tracking-branch", default="main",
                      help="the branch the holder is created on (default: "
                           "main)")
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
                           "in (default: the directory you are standing in, "
                           "which is refused inside a checkout of "
                           "openRepoShape: from its root, pass `--into ..`). "
                           "The holder lands at <into>/<Family>/<Family>, "
                           "beside where `make siblings` clones the members.")
    init.add_argument("--work-dir", type=Path, default=None,
                      help="THE OVERRIDE: land the holder at "
                           "<work-dir>/<Family> and make no family folder at "
                           "all. Mutually exclusive with --into.")
    init.add_argument("--no-push", action="store_true")
    init.add_argument("--dry-run", action="store_true",
                      help="print the plan and ask, as the real run does, "
                           "whether each folder it makes can be made (the "
                           "family folder or --work-dir, the holder in it, "
                           "--local-remote-dir) and whether <org>/<Family> "
                           "already exists (`gh repo view` and its commit "
                           "listing; with --local-remote-dir, the bare "
                           "repository), refusing what it refuses; make no "
                           "folder, remote or repository")
    init.set_defaults(func=cmd_init)

    add = subparsers.add_parser(
        "add", help="mount and pin a member",
        description="Mount and pin a member. " + BRANCH_RULE)
    add.add_argument("--family-root", required=True)
    add.add_argument("--member", required=True, metavar="ORG/PROJECT",
                     help="the member's ASSEMBLY ROOT, `<org>/<Project>` — "
                          "never a leg")
    add.add_argument("--at", default=None, metavar="COMMIT",
                     help="pin this 40-hex commit instead of the member's "
                          "current tip (an annotated tag's own 40-hex id is "
                          "peeled to the commit it names)")
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

    bump = subparsers.add_parser(
        "bump", help="move a member's pin",
        description="Move a member's gitlink and pin together. "
                    + BRANCH_RULE)
    bump.add_argument("--family-root", required=True)
    bump.add_argument("--member", required=True, metavar="PROJECT")
    bump.add_argument("--to", required=True, metavar="COMMIT",
                      help="the 40-hex commit to move the gitlink and the pin "
                           "to, together (an annotated tag's own 40-hex id is "
                           "peeled to the commit it names, as `add --at` "
                           "peels one)")
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

    remove = subparsers.add_parser(
        "remove", help="unmount a member",
        description="Unmount a member and drop its row. " + BRANCH_RULE)
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
