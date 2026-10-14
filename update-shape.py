#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Re-sync a root's COPIED shape files with openRepoShape, and re-pin.

    ./update-shape.py check --root <assembly-root|family-root>
    ./update-shape.py apply --root <root> --at <commit> --yes \\
        [--accept-local <path>] [--add <path>] [--branch shape/update-<sha>]

TWO KINDS OF ROOT, ONE COMMAND. An assembly root mirrors the pin into
`project.yaml` and must leave `validate-pins.py` and `validate-manifest.py`
green; a FAMILY holder (2026-09-04) mirrors it into `family.yaml` and must
leave `validate-family.py` green. Everything else is identical, because both
carry the same COPY pin — per-file sha256 rows over what was copied, plus the
`commit` and `tree_sha256` of the revision it came from. Which one this is, is
read from the tree (`root_kind`), never taken as a flag.

THE GAP THIS CLOSES, as observed on 2026-09-03. `scaffold-project.py` COPIES a
small set of files out of openRepoShape so a project runs its own gate in an
organisation that may never speak to the upstream again (README, "Bootstrap is
COPIED into the project, not fetched"). That is the right trade — but it means
an upstream FIX to one of those files reaches nobody. When the assembly-root
`validate.yml` was fixed, both projects then carrying the shape (MedxSoft/
MedxEHR and MedxSoft/MedxGlass) were updated BY HAND: re-copy the file,
recompute its `sha256` row in `contracts/shape-pin.yaml`, move the pin's
`commit` and `digests.tree_sha256`, mirror both into `project.yaml`'s `shape:`
block, then run `validate-pins.py` and `bootstrap.py`. Five mechanical steps
that must all be right, per project, per file. There was no command. This is
the command.

WHAT IT WILL NOT DO, and why the refusals are the point. Re-pinning is
recording an identity, so this tool never records one it cannot justify:

  * A file the PROJECT edited (`locally-modified`) keeps its bytes and is
    REFUSED, by name, unless the human passes `--accept-local <path>`.
    Recomputing that row silently would turn the drift `validate-pins.py`
    reports today into a digest that agrees with the fork — which is exactly
    the "record the fork as the standard" failure `shape-pin.yaml`'s own
    header forbids. `check`'s NEXT line never passes the flag for them
    (#501): the `apply` it hands over meets that refusal, which is where the
    human is asked.
  * A file changed on BOTH sides is refused outright, UNLESS the human passes
    `--accept-local <path>` on it too — the same exception `locally-modified`
    gets, above. Two edits to one file is a merge, and a merge is a human's
    judgement, not a byte copy; once they have made it and committed it, the
    row is recomputed from what they merged, the same mechanism.
  * A copy that is not VERBATIM at the pinned commit — `adopt-project.py`
    appends a `CONTRACTS_DIR` block to an adopted Makefile — is treated as a
    conflict the moment upstream touches it, because copying the target bytes
    over it would delete that block without saying so.
  * Nothing is committed that was judged from other bytes (#436). Every
    verdict — what to copy, what to re-pin, whether there is anything to
    do — is read from the WORKING TREE, and `--branch` commits HEAD plus
    only the paths this run writes. So before the first write the pin, the
    manifest and every pinned copy are compared with HEAD, and a difference
    is refused by name (`update-branch-uncommitted`): commit those changes
    or put them back. The commit is never widened to take them in. A
    directory where HEAD commits one is HEAD's, not a difference, and a
    FIFO or a socket is never read: the copy is `update-conflict`'s
    `copy-missing`. A copy, the pin or the manifest this run would write or
    re-pin THROUGH a symlink is refused too (`update-rewrite-symlink`): git
    commits the link, not the bytes it leads to. Without `--branch` the run
    writes as it always did, and its NEXT line names those copies instead
    of printing a commit that would leave them out.
  * Nothing is left red: the root's OWN `validate-pins.py` and
    `validate-manifest.py` run after the rewrite, and every byte is rolled
    back if either refuses.
  * A write that fails is a refusal, not a traceback (#285): a copy, an
    addition or the pin this process cannot write is `update-write-failed`,
    and every byte written before it is put back, as below.
  * Nothing is left half-done either (#202). With `--branch`, a branch git
    cannot create, an addition it cannot stage or a commit a hook refuses
    puts back the copies, the pin, the README line, the index and the
    branch, and the refusal names the step that failed and lists what it
    put back. A re-run then finds the tree it found the first time, rather
    than an uncommitted re-pin it would read as already done. What the
    rollback itself cannot put back — a file that will not take its old
    bytes, an `--add` file that will not go, a path a link has reached
    since the write, which it never writes through — it names with the line
    that finishes it by hand, and it goes on to the rest: the refusal that
    started it is still the one reported (#428).
  * Nothing is written THROUGH A SYMLINK (#239, #286). A rewrite opens the
    file where it stands, so a pinned copy, `contracts/shape-pin.yaml` or
    the manifest kept as a link — or under a directory link — would have the
    standard's bytes land at the link's end, outside the root if that is
    where it points, while git, which holds the link, commits none of them.
    `check` calls such a copy `copy-is-link` and `apply` refuses it; both
    refuse a linked pin or manifest. Each refusal is `update-rewrite-symlink`,
    before anything is written, as `--add` refuses a link at a path it would
    create as `update-add-symlink`. Nor through a HARD LINK (#422): a file
    with a second name — outside the root, or in a `cp -al` snapshot of it
    — is the same bytes under both, so a rewrite in place would change the
    other name too, which no pin covers and git does not record. `apply`
    refuses each file it would rewrite that has one — a copy it copies, the
    pin, the manifest, a `.gitattributes` whose block `--add` extends — as
    `update-rewrite-hardlink`, before anything is written, and `check` says
    so first in a `REFUSAL AHEAD` line; the row keeps its verdict, since the
    copy holds the right bytes. A hard-linked `README.md` is kept, as ever.

ONLY THE PIN'S OWN ROWS ARE CONSIDERED. The set of shape files is read from
`contracts/shape-pin.yaml`, never re-derived from this repository's copy
lists. An in-place adoption collides on `Makefile`, `README.md` and
`.gitignore` — the shape's copies land under `shape/` and a human merges them,
usually deleting the `shape/` copy. Its row then names a file that is not
there; MedxEHR dropped such rows by hand, which is the hand edit of a pin
this standard forbids. So `check` calls the row `merged-away` where the root
holds the file the copy was merged into, and `apply` drops it in its re-pin
commit (#502). A file with no row is not a shape copy and is invisible here;
re-deriving the list would resurrect a file the project deliberately merged
away.

WHAT A PIN CANNOT NAME IS THE FILE THE STANDARD ADDED AFTERWARDS (2026-09-04),
and "only the pin's own rows are RE-SYNCED" is a different claim from "only the
pin's own rows are LOOKED AT". A pin records what existed on the day it was
written, so `AGENTS-shape.md` — added to the assembly root and the family
holder after MedxEHR, MedxGlass, MedxScribe and the InkRouter members were cut
— reached none of them. `check` therefore also reports `upstream-added`: a path
the UPSTREAM's copy lists name AT THE TARGET COMMIT that this pin has no row
for AND THE ROOT HAS NO FILE AT. Both halves are load-bearing. The lists are
read out of the upstream's OWN `scripts/shape_materialize.py` at that commit
with `ast` — never this checkout's imports, which describe the openRepoShape
running the command rather than the one being updated to, and never an `exec`
of code out of somebody's git history. And the second half is what keeps a
merged-away `Makefile` invisible: a root that already has a file at that path
is the in-place adoption case, and nothing here may overwrite bytes no row
records. `apply` writes NONE of them unless `--add <path>` names it, one path
at a time, so nothing lands in a project's tree because a tool decided it
should.

EXIT CODES
    check   0  the pin names the target and no copied file differs
            1  updates are available, or drift a human must resolve
            2  a REFUSAL: no pin, an unresolvable upstream, an unreadable root
    apply   0  applied (or there was nothing to do)
            2  a REFUSAL, including a validator that went red or a branch,
               stage or commit that failed (rolled back); or a push or pull
               request failing after the commit, which is KEPT, and the
               NEXT line printed then finishes the job (#204)

STANDARD LIBRARY ONLY, like everything else shipped here.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

SHAPE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SHAPE_ROOT / "scripts"))
from repo_shape import (  # noqa: E402
    COMMIT_RE, PYTHON, TREE_DIGEST_DEFINITION, Refusal, YamlError,
    checked_value, die, file_sha256, git_out, load_yaml, parse_yaml,
    tree_digest,
)
from shape_materialize import (  # noqa: E402
    ATTRIBUTES, COPIED_FROM_SHAPE, COPIED_VERBATIM, FAMILY_COPIED_FROM_SHAPE,
    FAMILY_COPIED_VERBATIM, SHAPE_REPOSITORY, CommandFailed, check_program,
    commit_trailers, escape_what_stdout_cannot_encode, extend_eol_block,
    force_stage,
    inherited_child_environment, lane_trailer_argument, readme_shape_lines,
    is_nested_key, readme_trailing_shape_line, rewrite_fault, run,
    trailer_line, with_scalar,
)
# Where a root keeps its shape pin. The materializer that writes it names it
# once; this module spells the path by that name and never by a literal (#290).
from shape_materialize import SHAPE_PIN  # noqa: E402

#: `owner/repo`, the only remote spelling `--upstream` accepts.
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

#: How `--branch` may be spelled: the alphabet `checked_value` already
#: allowed it, less the `~` git refuses anyway, and a FIRST character that is
#: a letter or a digit, so no value reads as an option (`--upload-pack=…`) or
#: starts with a `/` or a `.`. `checked_branch` holds it to this, then to
#: git's own rules.
BRANCH_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/@+-]{0,254}")

#: Where `adopt-project.py` puts a template file whose name the source
#: repository already uses. Spelled here because this tool must map
#: `shape/Makefile` back to the template it was cut from;
#: `tests/test_update_shape.py` asserts the two spellings agree, so the
#: constant cannot drift out of step with the tool that writes it.
COLLISION_DIR = "shape"

#: Where each copied file came from in the upstream tree, derived from the ONE
#: materializer rather than restated. `templates/assembly-root/<rel>` for the
#: verbatim template copies; the shape's own path for the three files copied
#: out of openRepoShape itself.
COPY_SOURCE: dict[str, str] = {
    rel: f"templates/assembly-root/{rel}" for rel in COPIED_VERBATIM
}
COPY_SOURCE.update({rel: src for src, rel in COPIED_FROM_SHAPE})

#: The same table for a FAMILY holder, and it is a SEPARATE one rather than a
#: merge, for one concrete reason: both roots hold a `scripts/bootstrap.py`
#: and they are DIFFERENT FILES — one puts a project's legs on their tracking
#: branches, the other fetches members and delegates to theirs. A single dict
#: keyed by the path in the root would map a family's copy back to the
#: assembly root's template and re-sync it into the wrong file, silently.
FAMILY_COPY_SOURCE: dict[str, str] = {
    rel: f"templates/family-root/{rel}" for rel in FAMILY_COPIED_VERBATIM
}
FAMILY_COPY_SOURCE.update({rel: src for src, rel in FAMILY_COPIED_FROM_SHAPE})


class Kind:
    """Which shape of root this is, and everything that differs because of it.

    ONE OBJECT, so the five places that differ cannot get out of step: the
    manifest that mirrors the pin, the upstream template directory a copy came
    from, the copy-source table, the NAMES THE UPSTREAM'S COPY LISTS GO BY
    (read at the target commit to find what the standard has since added), and
    the validators that must pass after a rewrite. A family root and an
    assembly root are re-synced by the same command because they carry the
    SAME copy pin — per-file sha256 rows, `commit`, `tree_sha256` — and differ
    only in what was copied.
    """

    def __init__(self, name: str, manifest: str, template_dir: str,
                 copy_source: dict, lists: tuple, validators: tuple,
                 manifest_validator: str):
        self.name = name
        self.manifest = manifest
        self.template_dir = template_dir
        self.copy_source = copy_source
        #: `(verbatim, from_shape, executable)`, as those three lists are
        #: SPELLED in `scripts/shape_materialize.py` for this kind of root.
        #: Names rather than the imported tuples, because the tuples that
        #: matter are the TARGET COMMIT's, not this checkout's.
        self.lists = lists
        self.validators = validators
        #: Which of `validators` checks the manifest's `shape:` block, named
        #: explicitly rather than read off `validators[-1]`: a refusal that
        #: sends the operator to a validator they do not carry is a wrong
        #: answer with a confident tone, same as the ones `Refusal` itself is
        #: for.
        self.manifest_validator = manifest_validator


PROJECT_KIND = Kind("project", "project.yaml", "templates/assembly-root",
                    COPY_SOURCE,
                    ("COPIED_VERBATIM", "COPIED_FROM_SHAPE", "EXECUTABLE"),
                    ("scripts/validate-pins.py",
                     "scripts/validate-manifest.py"),
                    "scripts/validate-manifest.py")
FAMILY_KIND = Kind("family", "family.yaml", "templates/family-root",
                   FAMILY_COPY_SOURCE,
                   ("FAMILY_COPIED_VERBATIM", "FAMILY_COPIED_FROM_SHAPE",
                    "FAMILY_EXECUTABLE"),
                   ("scripts/validate-family.py",),
                   "scripts/validate-family.py")


def root_kind(root: Path) -> Kind:
    """A root carrying `family.yaml` and no `project.yaml` is a family.

    Read from the tree rather than taken as a flag: a human updating a
    checkout should not have to tell the tool what they are standing in, and
    the two manifests are mutually exclusive by construction — a family has no
    legs, so it has no `project.yaml` to mirror a pin into.
    """
    if (root / "family.yaml").is_file() and not (root / "project.yaml").is_file():
        return FAMILY_KIND
    return PROJECT_KIND


#: States a pinned row can be in. The first four are the vocabulary the task
#: of updating a project is actually about; the last four are the ways the
#: question cannot be asked, or its answer written, and each of them refuses
#: rather than guessing.
UNCHANGED = "unchanged"
UPSTREAM_CHANGED = "upstream-changed"
#: Not a state a pinned ROW can be in: a path the upstream's copy lists name at
#: the target commit that the pin carries no row for. It is reported beside the
#: rows because it answers the same question a human is asking — what does this
#: project owe the standard — and `apply` still refuses to act on it unasked.
UPSTREAM_ADDED = "upstream-added"
LOCALLY_MODIFIED = "locally-modified"
BOTH = "both"
ALREADY_AT_TARGET = "already-at-target"
#: A `shape/` collision copy the project merged into the file it collided
#: with, and removed (#502): the root holds `X` and nothing at `shape/X`. Its
#: row is the one thing left of it, and `apply` DROPS that row in its re-pin
#: commit, behind the same yes as every other row it moves. Named for the
#: act the adoption's own follow-up asks for ("merge shape/X into X"), and
#: spelled as the other states are, so a person reading `check` reads what
#: happened to the copy rather than what is missing. Not a conflict: there
#: is nothing to merge and no bytes to keep, so nothing here refuses it.
MERGED_AWAY = "merged-away"
UPSTREAM_REMOVED = "upstream-removed"
UNMAPPED = "unmapped"
COPY_MISSING = "copy-missing"
#: A pinned copy the root keeps as a SYMLINK, or under one (#286). The bytes
#: can be compared — they are read through the link — but the answer cannot be
#: written: a rewrite lands at the link's end, which git does not commit. So
#: it is a fourth way the question cannot be asked, whatever the upstream did,
#: and `apply` refuses it by name. A DANGLING link stays `copy-missing`: there
#: is no file to read, and that refusal already writes nothing.
COPY_IS_LINK = "copy-is-link"

#: Anything here is a merge or a decision, never a byte copy.
CONFLICTS = (BOTH, UPSTREAM_REMOVED, UNMAPPED, COPY_MISSING, COPY_IS_LINK)
ORDER = (UPSTREAM_CHANGED, UPSTREAM_ADDED, BOTH, LOCALLY_MODIFIED,
         MERGED_AWAY,
         ALREADY_AT_TARGET, UPSTREAM_REMOVED, UNMAPPED, COPY_MISSING,
         COPY_IS_LINK, UNCHANGED)


# ---------------------------------------------------------------------------
# The upstream, local or remote
# ---------------------------------------------------------------------------


class Upstream:
    """A git repository this tool reads revisions out of, and nothing more.

    ONE READER FOR BOTH CASES. A local path is used as it stands — which is
    what makes the test suite offline — and `owner/repo` is BARE-CLONED into a
    temporary directory. Both then answer through the same three questions:
    resolve a revision, read a file's bytes at it, digest the tree at it. A
    second code path for the remote case would be a second definition of what
    "the upstream said" means.
    """

    def __init__(self, path: Path, label: str, temporary: Path | None = None):
        self.path = path
        #: WHERE it was read from — a path or an `owner/repo` — so that every
        #: command this tool prints can be pasted back.
        self.label = label
        #: WHAT it is: the repository the pin names. A commit message that
        #: recorded `/tmp/…/openRepoShape` as the shape would have recorded
        #: this machine rather than the standard.
        self.repository = SHAPE_REPOSITORY
        self._temporary = temporary

    def close(self) -> None:
        if self._temporary is not None:
            shutil.rmtree(self._temporary, ignore_errors=True)
            self._temporary = None

    def resolve(self, rev: str | None) -> str:
        """`rev` as a full 40-hex commit; `None` means this upstream's tip.

        The tip is `HEAD`. For the bare clone this tool makes, that IS the
        remote's default branch; for a local path it is whatever that checkout
        has checked out, which is the only answer available offline and the
        one a person pointing at a clone means.
        """
        wanted = rev or "HEAD"
        try:
            out = git_out(["rev-parse", "--verify", "--quiet",
                           f"{wanted}^{{commit}}"], cwd=self.path)
        except Refusal as exc:
            raise Refusal(
                "update-revision-unresolvable",
                f"{self.label} cannot resolve {wanted!r}: {exc.detail}",
                "Remediation: fetch the upstream (`git -C <clone> fetch "
                "--all`) and pass a commit it actually has, or point "
                "--upstream at a clone that has it.") from exc
        if not COMMIT_RE.match(out):
            raise Refusal(
                "update-revision-unresolvable",
                f"{self.label} answered {out!r} for {wanted!r}, not 40 hex")
        return out.lower()

    def blob(self, rev: str, path: str) -> bytes | None:
        """The bytes of `path` at `rev`, or None when it is not there."""
        proc = subprocess.run(["git", "show", f"{rev}:{path}"],
                              cwd=str(self.path), capture_output=True,
                              check=False)
        return proc.stdout if proc.returncode == 0 else None

    def tree_sha256(self, rev: str) -> str:
        return tree_digest(self.path, rev)


def open_upstream(spec: str) -> Upstream:
    """`--upstream` as a repository this tool can read.

    A PATH IS USED IN PLACE AND NOTHING IS FETCHED. That is deliberate: it is
    what lets the tests run with no network, and it is also the honest answer
    for an organisation whose fork is the upstream. `owner/repo` is bare-cloned
    into a temporary directory, which is the one place this tool fetches the
    shape, and it refuses loudly rather than degrading to a guess. It is not
    the only place `apply` can touch a network (#411): the project's own
    `validate-pins.py` runs in this process's environment, so for a project
    declaring `neutral_product_pins:` whose product has no local checkout it
    asks `gh api` for the pinned tree with the operator's `gh` credentials
    (`skip` line and exit 0 without `gh`, a login or a network), and `--push`
    and `--pr` push the branch and open its pull request.
    """
    candidate = Path(spec).expanduser()
    if candidate.exists():
        path = candidate.resolve()
        if not (path / ".git").exists() and not (path / "HEAD").is_file():
            raise Refusal(
                "update-upstream-not-a-repo",
                f"--upstream {spec} exists but is not a git repository",
                "Remediation: point it at a clone of openRepoShape, or pass "
                "`--upstream opensoft/openRepoShape` to clone one.")
        return Upstream(path, str(path))
    if not REPOSITORY_RE.match(spec):
        raise Refusal(
            "update-upstream-unresolvable",
            f"--upstream {spec!r} is neither a path on this machine nor an "
            "`owner/repo` name",
            "Remediation: pass a path to a clone of openRepoShape, or "
            "`--upstream opensoft/openRepoShape`.")
    checked_value("--upstream", spec)
    temporary = Path(tempfile.mkdtemp(prefix="openreposhape-upstream-"))
    url = f"https://github.com/{spec}.git"
    args = ["git", "clone", "--quiet", "--bare", url, str(temporary / "shape.git")]
    check_program(args)
    proc = subprocess.run(args, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False)
    if proc.returncode != 0:
        shutil.rmtree(temporary, ignore_errors=True)
        raise Refusal(
            "update-upstream-unresolvable",
            f"could not clone {url} (git exit {proc.returncode}): "
            f"{(proc.stderr or '').strip()}",
            "Remediation: this is the one step that fetches the shape from a "
            "network. Clone the shape once by hand and pass `--upstream "
            "<path>` instead; nothing after it fetches the shape again.")
    return Upstream(temporary / "shape.git", spec, temporary=temporary)


# ---------------------------------------------------------------------------
# The root, its pin, and what each pinned row is
# ---------------------------------------------------------------------------


class Row:
    """One `files:` row of `contracts/shape-pin.yaml`, and its verdict."""

    def __init__(self, path: str, recorded: str):
        self.path = path
        self.recorded = (recorded or "").lower()
        self.source: str | None = None
        self.state = UNCHANGED
        self.detail = ""
        self.target_bytes: bytes | None = None
        self.digest = self.recorded
        #: `symlink_on_the_way`'s answer for this path — the link and where
        #: it points — when there is one, which makes the row `copy-is-link`.
        self.link: tuple[str, str] | None = None

    @property
    def is_conflict(self) -> bool:
        return self.state in CONFLICTS


def pin_rows_remediation(root: Path) -> str:
    """What `update-pin-row` tells the person whose pin's `files:` does not
    read as rows (#290). Without it the refusal carried `repo_shape`'s
    default trailer, which is about submodules and the lockstep invariant and
    fixes nothing in this file.

    A FUNCTION OF THE ROOT, not a constant, because the `git log` it points
    at has to read the PROJECT's history. This tool is run from a checkout of
    openRepoShape with `--root /path/to/project`, so a bare `git log --
    contracts/shape-pin.yaml` inspects the checkout instead and shows no pin
    history, or the wrong one (codex, PR #343). It is spelled `git -C <root>`
    by `_by_hand`, this module's one quoter for a line a person pastes, so a
    root holding a space is one argument there.
    """
    log = _by_hand(root, "log", "--", SHAPE_PIN)
    return (
        "Remediation: `files:` is a list with one `path:`/`sha256:` row per "
        "copied file. The tool that cut this root wrote it and only "
        "`update-shape.py apply` moves it, so it is never mended by hand: "
        "put back the pin a tool last wrote from this repository's own "
        f"history (`{log}` names the commit that changed it), then run this "
        "again.")


def read_pin(root: Path) -> tuple[dict, list[Row]]:
    """The root's `contracts/shape-pin.yaml` and its rows, or a refusal that
    says why this command cannot use it.

    A PIN KEPT AS A SYMLINK, OR UNDER ONE, IS ONE IT CANNOT USE (#286), and
    that is asked FIRST, by `lstat`: `apply` rewrites the pin where it
    stands, so the re-pin would land at the link's end while the commit
    `--branch` makes holds the unchanged link. Asked before `is_file()`,
    which follows a link, so a dangling one is named as the link it is
    rather than as a pin that "does not exist".
    """
    pin_path = root / "contracts" / "shape-pin.yaml"
    linked = linked_record(root)
    if linked is not None:
        raise rewrite_link_refusal([linked])
    if not pin_path.is_file():
        raise Refusal(
            "update-pin-missing",
            f"{pin_path} does not exist, so there is no record of which files "
            "were copied out of openRepoShape or which revision they came "
            "from. Nothing can be re-synced against nothing.",
            "Remediation: this command updates a project that was scaffolded "
            "or adopted with this shape. A project without a shape pin is "
            "adopted with `adopt-project.py`, not updated.")
    return check_pin(load_yaml(pin_path), pin_path, root)


def check_pin(pin, pin_path, root: Path) -> tuple[dict, list[Row]]:
    """`read_pin`'s checks, over a pin already parsed: the pin and its rows,
    or the refusal `read_pin` raises for it.

    APART FROM THE READ so a pin can be checked where it is not a file on
    disk: `shape-doctor.py` reads the pins in a root's history out of git,
    in memory, before it names one to put back (#237), and a second copy of
    these checks there could pass a pin this tool then refuses. `pin_path`
    only names the pin in a refusal's words, and `root` is the repository
    whose history a refusal's `git log` reads (#290).
    """
    if not isinstance(pin, dict):
        raise Refusal("update-pin-unreadable", f"{pin_path}: not a mapping")
    commit = str(pin.get("commit") or "").lower()
    if not COMMIT_RE.match(commit):
        raise Refusal(
            "update-pin-commit",
            f"{pin_path}: `commit:` is {pin.get('commit')!r}, not 40 hex, so "
            "there is no revision to compare the upstream against")
    if pin.get("digest_definition") != TREE_DIGEST_DEFINITION:
        raise Refusal(
            "update-pin-digest-definition",
            f"{pin_path}: digest_definition is "
            f"{pin.get('digest_definition')!r}, and this tool recomputes "
            f"{TREE_DIGEST_DEFINITION!r}. Rewriting the tree digest under a "
            "definition the pin does not claim would record a number whose "
            "meaning nobody stated.",
            "Remediation: a pin written under another definition is updated "
            "by whatever wrote it.")
    # A LIST IS ASKED FOR, NOT ASSUMED (#290). `or []` rescues only the falsy
    # values -- `files: 0`, `false`, `null`, `[]` reach `update-pin-no-files`
    # below -- and a truthy scalar was iterated: `files: 5`, `true` or `1.5`
    # ended `check`, `apply` and `shape-doctor.py` in a `TypeError`, exit 1,
    # with nothing naming the pin. A string or a mapping lands here too, and
    # is named for what it is rather than as its first character or key.
    files = pin.get("files") or []
    if not isinstance(files, list):
        raise Refusal(
            "update-pin-row",
            f"{pin_path}: `files:` is {files!r}, not a list of "
            "`path:`/`sha256:` rows, so no copied file can be read from it",
            pin_rows_remediation(root))
    rows: list[Row] = []
    for raw in files:
        if not isinstance(raw, dict) or not raw.get("path"):
            raise Refusal("update-pin-row",
                          f"{pin_path}: a `files:` row is not `path:`/`sha256:`",
                          pin_rows_remediation(root))
        rows.append(Row(str(raw["path"]), str(raw.get("sha256") or "")))
    if not rows:
        raise Refusal(
            "update-pin-no-files",
            f"{pin_path}: no `files:` rows, so the pin asserts nothing about "
            "any copied file and there is nothing to re-sync")
    return pin, rows


def source_for(rel: str, upstream: Upstream, rev: str,
               kind: Kind = PROJECT_KIND) -> str | None:
    """Where a pinned root path came from in the upstream tree.

    The materializer's own tables answer first, for the KIND of root this is —
    a family holder and an assembly root both carry a `scripts/bootstrap.py`
    and they are different files. The two fallbacks exist for a pin written by
    a DIFFERENT openRepoShape than the one running this: the tables here
    describe today's copy lists, and a project pinned three revisions back may
    name a file those lists have since renamed. Each fallback is confirmed
    against the target tree before it is used, so a guess that is not there is
    reported as `unmapped` rather than acted on.
    """
    stripped = rel
    prefix = f"{COLLISION_DIR}/"
    if stripped.startswith(prefix):
        stripped = stripped[len(prefix):]
    known = kind.copy_source.get(stripped)
    candidates = [known] if known else []
    candidates += [f"{kind.template_dir}/{stripped}", stripped]
    for candidate in candidates:
        if candidate and upstream.blob(rev, candidate) is not None:
            return candidate
    return known or None


def merged_into(root: Path, rel: str) -> str | None:
    """The file a pinned `shape/` collision copy was merged into, or None
    when `rel` is not a merged-away copy (#502).

    THREE FACTS, ALL READ FROM THE ROOT, AND ALL THREE HAVE TO HOLD. `rel`
    lies under `COLLISION_DIR`, where only an in-place adoption puts a shape
    copy, and only because the source already used its name; the root holds
    NOTHING at `rel`, not even a dangling link (`lexists`: a FIFO or a
    directory there is something, so either stays `copy-missing`); and the root
    holds a FILE at the path the copy was cut for, `shape/X` -> `X`, which
    is what the adoption's follow-up said to merge it into. Where `X` is
    gone too, nothing says a merge happened, and the row stays
    `copy-missing` with its own refusal, as does a pinned copy deleted
    anywhere else.

    WHAT MERGING MEANS IS NOT JUDGED. The row is dropped and nothing is
    copied, so no byte of `X` is compared with the shape's: the follow-up is
    the person's, and `X` was never a shape copy of this pin. Read by
    `classify` and by the doctor's `pins` row, so the two cannot disagree
    about which rows go.
    """
    prefix = f"{COLLISION_DIR}/"
    if not rel.startswith(prefix):
        return None
    original = rel[len(prefix):]
    if not original or os.path.lexists(root / rel):
        return None
    return original if (root / original).is_file() else None


def classify(root: Path, rows: list[Row], upstream: Upstream, pinned: str,
             target: str, kind: Kind = PROJECT_KIND) -> None:
    """Fill in every row's verdict. Four byte-strings decide it:

        D  the sha256 the pin RECORDS for this file
        R  the ROOT's bytes now
        P  the UPSTREAM's bytes at the PINNED commit
        T  the UPSTREAM's bytes at the TARGET commit

    `upstream-changed` is P != T — a comparison between two upstream
    revisions, so an adopted Makefile carrying an appended block does not read
    as an upstream change merely for being appended to. `locally-modified` is
    sha256(R) != D, which is the same question `validate-pins.py` asks and the
    same answer it gives.

    A MERGED-AWAY `shape/` COPY IS ASKED ABOUT FIRST (#502), because none of
    the four is there to decide it: R is absent and the row is going, so the
    upstream is not read for it. `merged_into` says which rows those are.
    """
    for row in rows:
        original = merged_into(root, row.path)
        if original is not None:
            row.state = MERGED_AWAY
            row.detail = (f"merged into {original} and removed; `apply` "
                          "drops this pin row in its re-pin commit and "
                          "copies nothing")
            continue
        _classify_row(root, row, upstream, pinned, target, kind)


def _classify_row(root: Path, row: Row, upstream: Upstream, pinned: str,
                  target: str, kind: Kind) -> None:
    """One pinned row's verdict, split out of `classify` for #133.

    THE THREE EXITS HERE ARE THE ONES WHERE THERE IS NOTHING TO COMPARE: the
    root has no file at this path, no upstream path corresponds to it, or the
    upstream has none at the target commit. A FOURTH COMES SECOND (#286):
    the file is there, but the path is a symlink or sits under one, so
    whatever the comparison said could not be written where git would commit
    it. It is asked after `is_file()`, which follows the link, so a DANGLING
    link is still `copy-missing`. Each is a decision for a human
    rather than a difference this tool can act on, so `_row_verdict` below is
    only ever reached holding the root's bytes and the target's bytes for
    certain. THE PINNED BLOB IS THE EXCEPTION and is passed on as `None` when
    the standard carried no such source at the pinned commit: that is not a
    hole in the comparison but an upstream change, and the ladder reads it as
    one. The reads are left in the order they were written in — the root's
    bytes, then the pinned blob, then the target blob — because
    `Upstream.blob` shells out to git and a reordering would change what a
    failing run prints.
    """
    target_path = root / row.path
    if not target_path.is_file():
        row.state = COPY_MISSING
        row.detail = ("pinned but absent from the root; a human decides "
                      "whether it was deleted on purpose")
        return
    link = symlink_on_the_way(root, row.path)
    if link is not None:
        row.state = COPY_IS_LINK
        row.link = link
        row.detail = linked_copy_detail(row.path, link)
        return
    source = source_for(row.path, upstream, target, kind)
    row.source = source
    if source is None:
        row.state = UNMAPPED
        row.detail = ("no file in the upstream tree corresponds to this "
                      "pinned path")
        return
    here = target_path.read_bytes()
    pinned_bytes = upstream.blob(pinned, source)
    target_bytes = upstream.blob(target, source)
    if target_bytes is None:
        row.state = UPSTREAM_REMOVED
        row.detail = (f"{source} is gone from the upstream at the target "
                      "commit; deleting a project's copy is a decision, "
                      "not a copy")
        return
    row.target_bytes = target_bytes
    _row_verdict(row, source, here, pinned_bytes, target_bytes,
                 file_sha256(target_path))


def _row_verdict(row: Row, source: str, here: bytes,
                 pinned_bytes: bytes | None, target_bytes: bytes,
                 local_digest: str) -> None:
    """The verdict ladder itself, split out of `classify` for #133.

    Reached with the root's bytes and the target's bytes both in hand, so
    this is the ladder and nothing else: the three derived booleans the
    parent's docstring argues for, and the first branch that matches.
    `pinned_bytes` is the one that may be `None` — the standard carried no
    such source at the pinned commit — and that is deliberately not treated
    as a missing comparison: it makes `upstream_changed` true, and it makes
    `verbatim_at_pin` false, because a copy cannot be a verbatim copy of a
    blob that was never there. The order of the branches is the order of the
    argument — already at the target, then the two ways to be a `both`, then
    the two single-sided answers — and moving one would change a verdict.
    """
    locally_modified = local_digest != row.recorded
    upstream_changed = pinned_bytes is None or pinned_bytes != target_bytes
    verbatim_at_pin = (pinned_bytes is not None
                       and file_bytes_sha256(pinned_bytes) == row.recorded)

    if here == target_bytes:
        # Already holding the target's bytes. Only the row is stale, and
        # recomputing it hides nothing: these ARE the upstream's bytes.
        row.state = (ALREADY_AT_TARGET if locally_modified else UNCHANGED)
        row.digest = local_digest
        return
    if locally_modified and upstream_changed:
        row.state = BOTH
        row.detail = "edited here AND upstream since the pin"
        # Precomputed the same way `locally-modified` precomputes it,
        # below: IF `--accept-local` later names this path, `cmd_apply`
        # must re-pin from what is on disk NOW, not from whatever was
        # true when the pin was written. Dead weight when nobody accepts
        # it — an unaccepted `both` row is refused before any digest is
        # written anywhere.
        row.digest = local_digest
        return
    if upstream_changed and not verbatim_at_pin:
        row.state = BOTH
        row.detail = (
            "upstream changed, but this copy is not a verbatim copy of "
            f"{source} at the pinned commit — an in-place adoption "
            "appends to it — so copying the target bytes would delete "
            "what was appended")
        row.digest = local_digest
        return
    if upstream_changed:
        row.state = UPSTREAM_CHANGED
        row.digest = file_bytes_sha256(target_bytes)
        return
    if locally_modified:
        row.state = LOCALLY_MODIFIED
        row.detail = "edited in this project since the pin"
        row.digest = local_digest
        return
    row.state = UNCHANGED


def file_bytes_sha256(data: bytes) -> str:
    """`file_sha256`'s answer for bytes that are not on disk yet."""
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# What the UPSTREAM's copy lists name at the target commit (2026-09-04)
# ---------------------------------------------------------------------------
#
# READ FROM THE UPSTREAM'S BYTES, NOT FROM THIS MODULE'S IMPORTS. The
# `COPIED_VERBATIM` imported at the top of this file is what the openRepoShape
# RUNNING this command copies; the question a project asks is what the
# openRepoShape it is updating TO copies. Those two differ by exactly the file
# the standard has just added, which is the whole point — so answering from the
# imports would report an addition a target commit does not have, or miss one
# it does, whenever the checkout and the target are not the same revision.
#
# `ast` READS THE MODULE AND NOTHING IS EXECUTED. An `exec` of a file taken out
# of a git history is arbitrary code, written by whoever wrote that history,
# run with this process's authority, to learn a dozen strings. So the lists are
# parsed as literals, with the module's own top-level string constants resolved
# BY NAME because `COPIED_FROM_SHAPE` names `VALIDATE_NAMING` rather than
# repeating the path. An entry that is not a string or a pair of them is
# skipped rather than guessed at: a guess about where a file comes from is the
# thing `unmapped` exists to refuse.

#: The one upstream file this reads, and the reason a target commit that has no
#: such file yields no additions rather than a refusal: it is an older
#: openRepoShape, and an older standard has added nothing.
MATERIALIZER = "scripts/shape_materialize.py"


class Copy:
    """One file a root's copy lists write, at one upstream commit.

    `path` is where it lands in the root, `source` is where the upstream keeps
    it, and `executable` is the bit the materializer's chmod pass would set.
    """

    def __init__(self, path: str, source: str, executable: bool):
        self.path = path
        self.source = source
        self.executable = executable


def as_literal(node, constants: dict[str, str]):
    """A string, a tuple of them, or None for anything this will not guess at."""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, (ast.Tuple, ast.List)):
        return tuple(as_literal(element, constants) for element in node.elts)
    return None


def inside_a_root(rel: str) -> bool:
    """Is `rel` a path a root can actually hold?

    An absolute path or one with a `..` segment would put a copy OUTSIDE the
    root this command was pointed at. Nothing in openRepoShape's lists has ever
    looked like that, and this is not a defence against the standard — it is
    that these strings arrive from a file read out of a git history, and a
    write that leaves the directory a human named is the one mistake that
    cannot be rolled back by putting the tree as it was.
    """
    parts = Path(rel).parts
    return bool(parts) and not Path(rel).is_absolute() and ".." not in parts


def upstream_copies(upstream: Upstream, rev: str, kind: Kind) -> dict[str, Copy]:
    """`{path in the root: Copy}` for `kind`, as of `rev` in the upstream.

    THE MAPPING MIRRORS `_materialize`, because a second definition of where a
    copy comes from is how the two start disagreeing. A VERBATIM entry is one
    path that is both the template-relative source and the destination, so its
    source is `templates/<root>/<path>`; a `..._FROM_SHAPE` entry is
    `(source, path)` with the source read out of openRepoShape's own tree; and
    the executable bit is the `..._EXECUTABLE` list, which is keyed by the path
    in the root.
    """
    data = upstream.blob(rev, MATERIALIZER)
    if data is None:
        return {}
    try:
        module = ast.parse(data.decode("utf-8"))
    except (SyntaxError, ValueError):
        # Not also `UnicodeDecodeError`: it IS a `ValueError` (by way of
        # `UnicodeError`), so `.decode("utf-8")`'s own failure is already
        # caught here, under the name that reaches every ValueError alike.
        return {}
    return _listed_copies(_tuple_constants(module), kind)


def _tuple_constants(module: ast.Module) -> dict[str, tuple]:
    """The materializer's top-level TUPLE constants, by the name each is
    assigned to. Split out of `upstream_copies` for #133.

    The string constants are harvested in the same pass and then thrown away,
    because they are not the answer: they exist so `as_literal` can resolve
    `COPIED_FROM_SHAPE`'s `VALUE_NAMING`-style references BY NAME as it walks
    the module, and a copy list is a tuple. Anything that is neither — a
    call, a comprehension, an entry this will not guess at — is skipped, for
    the reason the section header above gives: a guess about where a file
    comes from is what `unmapped` exists to refuse.
    """
    constants: dict[str, str] = {}
    tuples: dict[str, tuple] = {}
    for node in module.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        value = as_literal(node.value, constants)
        if isinstance(value, str):
            constants[target.id] = value
        elif isinstance(value, tuple):
            tuples[target.id] = value
    return tuples


def _listed_copies(tuples: dict[str, tuple], kind: Kind) -> dict[str, Copy]:
    """`{path in the root: Copy}` for the three lists `kind` names, out of
    the constants `_tuple_constants` harvested. Split out of
    `upstream_copies` for #133, which documents the mapping itself.

    The shape of each entry is CHECKED rather than assumed: these tuples came
    out of a file read from somebody's git history, so a verbatim entry that
    is not a string, a `..._FROM_SHAPE` entry that is not a pair of them, and
    any path `inside_a_root` refuses are all dropped instead of raising. The
    `..._FROM_SHAPE` pass runs second and may overwrite a verbatim entry of
    the same path, exactly as it did when both loops sat in one body.
    """
    verbatim, from_shape, executable = kind.lists
    executables = {entry for entry in tuples.get(executable, ())
                   if isinstance(entry, str)}
    copies: dict[str, Copy] = {}
    for rel in tuples.get(verbatim, ()):
        if isinstance(rel, str) and inside_a_root(rel):
            copies[rel] = Copy(rel, f"{kind.template_dir}/{rel}",
                               rel in executables)
    for entry in tuples.get(from_shape, ()):
        if (isinstance(entry, tuple) and len(entry) == 2
                and all(isinstance(part, str) for part in entry)
                and inside_a_root(entry[1])):
            source, rel = entry
            copies[rel] = Copy(rel, source, rel in executables)
    return copies


class Addition(Row):
    """A path the upstream's copy lists name at the target that has NO PIN ROW.

    NOT A ROW'S QUESTION, AND NOT ANSWERED LIKE ONE. There is no recorded
    digest to compare against, so `classify`'s four byte-strings collapse to
    two states: the standard added this file, or the root ALREADY HAS ONE AT
    THAT PATH and this is silent. The second case is the in-place adoption —
    MedxEHR's `Makefile` collided, was merged by hand and had its row dropped —
    and telling that project on every `check` that the standard has a
    `Makefile` would be noise about a file it knows it has, ahead of an
    overwrite nothing here is allowed to perform. So `present` is remembered
    rather than filtered away: `--add` on such a path must refuse BY NAME, and
    a refusal that cannot say which of three things went wrong sends a human to
    read this file's source.

    A SYMLINK IS THE OPERATOR'S, AND IS NEVER "NOTHING THERE" (#239). `present`
    is the root's own answer from `lstat`, which a dangling link gives where
    `exists()` follows it and says no, and `link` names the first symlink (or
    Windows junction) on the path's way down from the root — the path itself
    or a directory above it — and where it points. A write at such a path goes
    THROUGH the link, to wherever it leads, outside the root included.

    AND A DIRECTORY THE ROOT HOLDS AS SOMETHING ELSE IS IN THE WAY (#285).
    `blocked` names the first directory above the path that the root keeps as
    a plain file, a FIFO, anything but a directory. The path is NOT present —
    nothing can be under a file, and `lexists` says so — so it is still
    reported; but `--add` cannot write it without moving the operator's file,
    which it never does, so `check` says why instead of offering the flag.
    """

    def __init__(self, copy: Copy, present: bool, target_bytes: bytes,
                 link: tuple[str, str] | None = None,
                 blocked: str | None = None, left_dead: str = ""):
        super().__init__(copy.path, "")
        self.source = copy.source
        self.executable = copy.executable
        self.present = present
        self.link = link
        self.blocked = blocked
        self.left_dead = left_dead
        self.target_bytes = target_bytes
        self.digest = file_bytes_sha256(target_bytes)
        self.state = UPSTREAM_ADDED
        self.detail = ("the standard added this file after this pin; `apply` "
                       "writes it only when --add names that path")
        if blocked is not None:
            self.detail = ("the standard added this file after this pin, but "
                           f"{blocked} in this root is not a directory, so "
                           f"--add refuses it until {blocked} is moved")
        if left_dead:
            self.detail += f"; {left_dead}"


#: AN ADDED FILE THAT A COPIED FILE CALLS (#489): `{the added path: (the pinned
#: copy that calls it, what stops working without it)}`. `apply` copies the
#: copy the moment it changes and takes the added file only on `--add`, which
#: is the human's word and per file, so a holder updated the way AGENTS.md
#: prescribes holds the Makefile of a standard that has `scripts/siblings.py`
#: and not the script. `check` and `apply` SAY so, in the line that already
#: reports the file, rather than leave the person to find three make targets
#: that cannot run; the Makefile refuses by name in the same case, and
#: neither writes the file nor refuses the run. A fact about the standard's
#: own files, so it is spelled here once, and
#: `tests/test_family_makefile_siblings.py` holds the Makefile to it.
CALLED_BY_A_COPY = {
    "scripts/siblings.py": (
        "Makefile", "`make siblings`, `make park` and `make resume`"),
}


def left_dead_by(path: str, rows: list[Row]) -> str:
    """What a copy that calls `path` leaves that cannot run while `path` is not
    added, or "" (#489).

    TWO CALLERS COUNT, and they are the two the root can hold the standard's
    own bytes in. `upstream-changed` is the one verdict whose bytes `apply`
    writes on its own, so the copy it is about to put in front of a file it
    does not add. `unchanged` is the root AFTER that `apply`: pinned at the
    target, holding the target's copy, and every later `check` finds the
    script `upstream-added` still, so the sentence has to be there on the
    second `check` as much as on the first. A `locally-modified` or `both`
    copy is kept or refused, and says nothing about what it calls.
    """
    called = CALLED_BY_A_COPY.get(path)
    if called is None:
        return ""
    caller, what = called
    states = {row.state for row in rows if row.path == caller}
    if UPSTREAM_CHANGED in states:
        return (f"the {caller} that `apply` copies calls it, so {what} "
                "cannot run until it is added")
    if UNCHANGED in states:
        return (f"this root's {caller} already calls it, so {what} cannot "
                "run until it is added")
    return ""


#: An NTFS junction's reparse tag. `stat` names IO_REPARSE_TAG_MOUNT_POINT on
#: Windows only — it comes from `_stat` there, and naming it bare is an
#: AttributeError everywhere else — so it is looked up, with the value
#: Windows' own headers give it as the fallback.
JUNCTION_TAG = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)


def is_link_info(info: os.stat_result) -> bool:
    """A symlink, or on Windows a JUNCTION, from an `lstat` result (#239).

    A junction is Windows' ordinary directory link, and `lstat` reads it as
    a directory: CPython sets `S_IFLNK` for IO_REPARSE_TAG_SYMLINK only, which
    is why 3.12 added `os.path.isjunction` as a call of its own. That call is
    too new for the 3.9 this standard runs on, so this asks what it asks:
    `st_reparse_tag` (3.8+), absent on POSIX and 0 for anything that is not
    a reparse point. NOT the `FILE_ATTRIBUTE_REPARSE_POINT` bit, which
    `lstat` keeps for a OneDrive placeholder or a deduplicated file it has
    traversed, and which would call a plain directory in a synced checkout a
    link.
    """
    return (stat.S_ISLNK(info.st_mode)
            or getattr(info, "st_reparse_tag", 0) == JUNCTION_TAG)


def symlink_on_the_way(root: Path, rel: str) -> tuple[str, str] | None:
    """The first link on `rel`'s way down from `root`, `rel` itself
    included, as `(its path inside the root, where it points)`; None when
    nothing on that way is one (#239). A link is a symlink, or a junction on
    Windows (`is_link_info`); `os.readlink` reads either since 3.8.

    `lstat`, ONE COMPONENT AT A TIME, because every other question this file
    asks of a path FOLLOWS a link: `Path.exists()` says no for a link whose
    target is missing, and a write at the path or under a directory link then
    creates what the link points at, which a root is free to point outside
    itself. The first component that cannot be `lstat`ed ends the walk: the
    ones after a missing component are missing too.
    """
    here = root
    walked: list[str] = []
    for part in Path(rel).parts:
        here = here / part
        walked.append(part)
        try:
            info = os.lstat(here)
        except (OSError, ValueError):
            return None
        if is_link_info(info):
            return "/".join(walked), os.readlink(here)
    return None


def not_a_directory_on_the_way(root: Path, rel: str) -> str | None:
    """The first directory `rel` needs that the root holds as something
    ELSE — a plain file, a FIFO — as its path inside the root; None when
    every one there is a directory (#285).

    `symlink_on_the_way`'s walk, over the components ABOVE `rel` only: what
    is AT `rel` is `present`'s question. A file at `docs` makes
    `docs/shape-guide.md` absent, since the kernel answers `ENOTDIR`, so
    the path was offered and `--add` taken, and `Rollback.write_added` then
    died making `docs/` after the copies were written. A link ends the walk
    with no answer, because it is `symlink_on_the_way`'s and refused first;
    so does a component that cannot be `lstat`ed, as there.
    """
    here = root
    walked: list[str] = []
    for part in Path(rel).parts[:-1]:
        here = here / part
        walked.append(part)
        try:
            info = os.lstat(here)
        except (OSError, ValueError):
            return None
        if is_link_info(info):
            return None
        if not stat.S_ISDIR(info.st_mode):
            return "/".join(walked)
    return None


def find_additions(root: Path, rows: list[Row], upstream: Upstream,
                   target: str, kind: Kind) -> list[Addition]:
    """Everything the upstream's lists name at `target` that the pin does not.

    A path is skipped when the pin names it UNDER `shape/` as well as under
    its own name: that is where an in-place adoption's collision landed, so a
    root whose pin carries `shape/Makefile` has a row for the shape's Makefile
    and is not owed another one.

    A PATH THE ROOT HOLDS ANYTHING AT IS PRESENT (#239): `lexists`, not
    `exists`, so a symlink whose target is missing, and a symlink above the
    path, are the operator's and not an absence this tool may write into.
    A path under a FILE is absent, and is remembered as `blocked` (#285).
    """
    pinned = {row.path for row in rows}
    additions: list[Addition] = []
    for copy in upstream_copies(upstream, target, kind).values():
        if copy.path in pinned or f"{COLLISION_DIR}/{copy.path}" in pinned:
            continue
        data = upstream.blob(target, copy.source)
        if data is None:
            # Named by a list but not in the tree at that commit. There is
            # nothing to copy, and inventing a row for absent bytes is the one
            # thing a pin may never do.
            continue
        link = symlink_on_the_way(root, copy.path)
        additions.append(Addition(
            copy, link is not None or os.path.lexists(root / copy.path),
            data, link, not_a_directory_on_the_way(root, copy.path),
            left_dead_by(copy.path, rows)))
    return additions


def link_said(path: str, link: tuple[str, str]) -> str:
    """`<name> in this root is a symlink[, on the way to <path>], pointing at
    '<where>'`: the one phrase every refusal and verdict about a link on
    `path`'s way prints, `link` being `symlink_on_the_way`'s answer.

    WHERE THE LINK POINTS IS QUOTED, `!r`, because it is the operator's text
    and a file name may hold a newline: printed as it is, a target spelled
    `out<LF>REFUSED fake` puts a line on stderr that reads as a second
    refusal (#239).
    """
    name, points = link
    above = "" if name == path else f", on the way to {path}"
    return f"{name} in this root is a symlink{above}, pointing at {points!r}"


def link_refusal(path: str, link: tuple[str, str]) -> Refusal:
    """`update-add-symlink`: `--add <path>` with a link at the path or above
    it, `link` being `symlink_on_the_way`'s answer (#239). Raised where
    `resolve_additions` finds the link, and again by `Rollback.write_added`
    for one that arrived after that.

    THE PROMISE IS THE WHOLE COMMAND'S (#286). It said `--add`'s alone while
    a pinned copy, or the pin, kept as a link was still rewritten through
    it; `rewrite_link_refusal` now refuses those, so the sentence is true of
    every write `apply` makes. It says SYMLINK, not "link": a HARD link is
    another name for the same bytes, refused in words of its own
    (`update-rewrite-hardlink`, #422).
    """
    name = link[0]
    return Refusal(
        "update-add-symlink",
        f"--add {path} names a file the upstream's lists add, but "
        f"{link_said(path, link)}. A write at "
        f"{path} would go THROUGH it, to wherever it leads — outside this "
        "root, if that is where it points — and this command never writes "
        "through a symlink",
        f"Remediation: if the link is yours to keep, leave {path} alone: "
        "`check` stops reporting a path the root holds, and the standard's "
        "file is yours to carry in whatever the link leads to. To take the "
        f"standard's file instead, remove or move {name} and run this command "
        f"again with the same --add: with nothing at {path} it is written "
        "there, as for any addition.")


def linked_copy_detail(path: str, link: tuple[str, str]) -> str:
    """A `copy-is-link` row's detail: the link, and what is done about it.
    `check` prints it under the row, and `apply` names the same link in
    `rewrite_link_refusal` (#286)."""
    return (f"{link_said(path, link)}; `apply` never writes through one, so "
            "replace the link with what it points at, or take the update by "
            "hand at the link's end")


def linked_record(root: Path, kind: Kind | None = None
                  ) -> tuple[str, tuple[str, str]] | None:
    """The first RECORD `apply` rewrites that the root keeps as a symlink,
    or under one, as `(record, link)`, `link` being `symlink_on_the_way`'s
    answer for it; None when neither is (#286). The records are
    `contracts/shape-pin.yaml` and then `kind.manifest`; with no `kind`, the
    pin alone, which is all `read_pin` reads.

    ONE QUESTION, AND EVERYONE WHO NEEDS IT ASKS THIS ONE. `read_pin`
    refuses a linked pin and `prepare` a linked manifest, each with
    `rewrite_link_refusal` over this answer. `shape-doctor.py` asks it
    FIRST, before it reads the pin or opens this checkout as the upstream:
    a linked record is a fact about the ROOT, which keeps a link where
    `apply` has to write, and not this checkout of the standard failing to
    ask about a commit. Asking the same function is how the doctor tells the
    two apart by which read refused, rather than by a list of refusal codes.
    """
    records = ["contracts/shape-pin.yaml"]
    if kind is not None:
        records.append(kind.manifest)
    for record in records:
        link = symlink_on_the_way(root, record)
        if link is not None:
            return record, link
    return None


def rewrite_link_refusal(linked: list[tuple[str, tuple[str, str]]],
                         arrived: bool = False) -> Refusal:
    """`update-rewrite-symlink`: a file `apply` REWRITES is a symlink in the
    root, or sits under one (#286). `linked` is `[(path, link)]`, `link`
    being `symlink_on_the_way`'s answer for `path`.

    `--add`'s `update-add-symlink` is the same refusal for a file `apply`
    would CREATE. This one is for the three it OVERWRITES — a pinned copy,
    `contracts/shape-pin.yaml`, the kind's manifest — which `Rollback.write`
    opens where they stand, so each write lands at the link's end, outside
    the root if that is where it points. git holds the LINK there, not those
    bytes, so the commit `--branch` makes would leave them out while the run
    printed them among what it committed, and the pin would record a digest
    of bytes no commit carries. Raised before any write: by `read_pin` for
    the pin, by `prepare` for the manifest, by `cmd_apply` for every
    `copy-is-link` row at once — and, with `arrived`, by `Rollback.write`
    for a link that came after `prepare` looked.

    ONE PATH IS ONE LINE, as `update-add-symlink` is. `read_pin` and
    `prepare` always name one, and the doctor quotes this refusal, for the
    record `linked_record` names, inside one line of its table, which a
    detail spread over three lines broke into three. Several `copy-is-link`
    rows are a list, one path a line, as `update-conflict` lists its own.
    """
    many = len(linked) > 1
    sentences = (["It was not there when this run looked: it arrived while "
                  "`apply` ran, after this run had decided what to write."]
                 if arrived else [])
    sentences.append(
        "A rewrite goes THROUGH a link, to wherever it leads — outside this "
        "root, if that is where it points — and git, which holds the link "
        "and not those bytes, commits none of them: the commit `--branch` "
        "makes would not hold what this run wrote. This command never "
        "writes through a symlink")
    if many:
        detail = ("`apply` would rewrite these files, but each is a symlink "
                  "in this root, or sits under one:\n"
                  + "\n".join(f"    {path}: {link_said(path, link)}"
                              for path, link in linked)
                  + "".join(f"\n  {sentence}" for sentence in sentences))
    else:
        path, link = linked[0]
        detail = " ".join([f"`apply` would rewrite {path}, but "
                           f"{link_said(path, link)}.", *sentences])
    return Refusal(
        "update-rewrite-symlink",
        detail,
        "Remediation: replace "
        + ("each link" if many else "the link")
        + " with what it points at — the same bytes at the same path, so git "
        "holds them there rather than a link — commit that, and run this "
        "command again. A root that keeps a link takes the update by hand, "
        "at the link's end, and re-pins by hand: the upstream's bytes are "
        "`git show <target>:<source path>` in a shape clone.")


def resolve_additions(rows: list[Row], additions: list[Addition],
                      asked: list[str], target: str) -> list[Addition]:
    """The `--add` paths as additions, or a refusal that names the path.

    THREE WAYS TO BE WRONG AND THREE SEPARATE ANSWERS. A path the pin already
    carries is not an addition at all — `apply` re-syncs it like every other
    row. A path the upstream's copy lists do not name at the target commit is
    not a shape copy there, so there are no bytes to copy and no row to write.
    And a path the ROOT ALREADY HAS A FILE AT is a merge: that is the
    `--accept-local` posture, taken for the same reason, because overwriting
    bytes no row records would delete somebody's work without saying so.

    A FOURTH, ASKED BEFORE THAT ONE: a SYMLINK at the path, or above it, is
    refused as its own answer (#239), and so is a Windows junction there. It
    is not a file to merge — a dangling one holds nothing — and a write there
    goes through the link to wherever it points, so the remedy is the
    operator's own link, not a merge.

    A FIFTH, ASKED NEXT (#285): a directory the path needs that the root
    holds as a file or a FIFO (`Addition.blocked`). Nothing is at the path,
    so it is not a merge either, and the write would fail making the
    directory — after the copies — so it is refused here, before the first
    byte, by the name of what is in the way.
    """
    by_path = {add.path: add for add in additions}
    pinned = {row.path for row in rows}
    taking: list[Addition] = []
    for path in asked:
        if path in pinned:
            raise Refusal(
                "update-add-already-pinned",
                f"--add {path} is already a `files:` row in "
                "contracts/shape-pin.yaml, so it is not an addition",
                "Remediation: drop the flag. A pinned copy is re-synced "
                "anyway, and its verdict is in `check`'s report under its own "
                "name.")
        add = by_path.get(path)
        if add is None:
            raise Refusal(
                "update-add-not-upstream",
                f"--add {path} is not named by the upstream's copy lists at "
                f"{target[:12]}, so there are no bytes to copy and no row to "
                "write",
                "Remediation: `check --at <commit>` prints every "
                f"`{UPSTREAM_ADDED}` path at that commit; a path in none of "
                "them is not a shape copy there. Check the spelling, and the "
                "commit.")
        if add.link is not None:
            raise link_refusal(path, add.link)
        if add.blocked is not None:
            raise Refusal(
                "update-add-not-a-directory",
                f"--add {path} names a file the upstream's lists add, but "
                f"{add.blocked} in this root is not a directory: the file "
                f"goes inside {add.blocked}, and the root keeps something "
                "else under that name. `--add` never moves or replaces what "
                "a root holds",
                f"Remediation: {add.blocked} is the project's. To take the "
                f"standard's file, move {add.blocked} out of the way and run "
                "this command again with the same --add: with nothing at "
                f"{add.blocked}, the directory is made and the file written "
                f"there, as for any addition. To keep {add.blocked} as it "
                f"is, leave the flag off; `check` goes on listing {path}, "
                "with no --add for it.")
        if add.present:
            raise Refusal(
                "update-add-would-overwrite",
                f"--add {path} names a file the upstream's lists add, but this "
                f"root already HAS a file at {path} and no pin row records it. "
                "Two files with one name is a merge, and this command copies "
                "bytes rather than merging them",
                "Remediation: the same posture as --accept-local — a human "
                "merges. The upstream's bytes are `git show <commit>:"
                f"{add.source}` in a shape clone. Once a file the project owns "
                f"sits at {path}, `check` stops reporting it: a path the root "
                "has and the pin does not record is the in-place adoption "
                "state, which this tool leaves alone by design.")
        taking.append(add)
    return taking


# ---------------------------------------------------------------------------
# Rewriting the two files that carry the pin
# ---------------------------------------------------------------------------


def rewrite_shape_pin(text: str, commit: str, tree: str,
                      rows: list[Row]) -> str:
    """`commit:`, `digests.tree_sha256:` and the whole `files:` block.

    A LINE REWRITE, NOT A YAML DUMP. The header of `shape-pin.yaml` is four
    paragraphs arguing why a copy pin is not a submodule pin; a round trip
    through a serialiser would delete every one of them, and the argument is
    the reason the file is trusted. Each replacement must fire exactly once or
    this refuses — a pin file this tool did not recognise is not a pin file it
    may edit.

    EACH OF THE TWO LINES KEEPS ITS OWN LAYOUT (#323). `commit:` is found at
    column 0 and `tree_sha256:` as any INDENTED line that begins with it, so a
    `digests:` child at any depth the reader accepts is recognised, and only
    the value after the key changes: the indentation, the spacing and a
    trailing `# comment` are the line's own. They were written back as
    `commit: "<sha>"` and `  tree_sha256: "<digest>"`, so a child indented
    four spaces was refused as hand-edited and a comment was dropped. The
    `files:` block below them is still written whole, as before.

    WHAT IS RETURNED HAS BEEN READ BACK, as `rewrite_manifest`'s is
    (`shape_materialize.rewrite_fault`): a layout this line rewrite cannot
    carry is refused HERE as this tool's failure, before any byte is written.
    """
    lines = text.splitlines()
    out: list[str] = []
    seen = {"commit": 0, "tree": 0, "files": 0}
    for index, line in enumerate(lines):
        if line.startswith("commit:"):
            seen["commit"] += 1
            out.append(with_scalar(line, "commit", commit))
            continue
        if is_nested_key(line, "tree_sha256"):
            seen["tree"] += 1
            out.append(with_scalar(line, "tree_sha256", tree))
            continue
        if line.rstrip() == "files:":
            seen["files"] += 1
            out.append("files:")
            for row in rows:
                out.append(f"  - path: {row.path}")
                out.append(f'    sha256: "{row.digest}"')
            break
        out.append(line)
    for key, count in seen.items():
        if count != 1:
            raise Refusal(
                "update-pin-unrecognised",
                f"contracts/shape-pin.yaml has {count} `{key}` line(s) where "
                "exactly one was expected, so this tool will not rewrite it",
                "Remediation: the pin was hand-edited into a shape this tool "
                "does not recognise. Fix it by hand this once, or re-scaffold.")
    rewritten = "\n".join(out) + "\n"
    why = rewrite_fault(text, rewritten, commit, tree)
    if why is not None:
        raise Refusal(
            "update-pin-unrecognised",
            f"contracts/shape-pin.yaml reads as it stands, but this tool's "
            f"rewrite of it does not read back to the target ({why}), so "
            "this tool will not write it",
            "Remediation: the fault is this tool's line rewrite, not the "
            "project's pin. Put each of `commit:` and `tree_sha256:` on one "
            "line with its quoted value, as the scaffold writes them, leave "
            "both values as they are — this command recomputes the digest, "
            "nobody edits it to fit — and run the same command again; this "
            "tool will not guess at a pin it does not recognise.")
    return rewritten


def rewrite_manifest(text: str, commit: str, tree: str, kind: Kind) -> str:
    """The two fields the kind's manifest validator checks, inside `shape:`.

    Scoped to the block on purpose: `commit:` and `tree_sha256:` are spelled
    the same way in every pin, and a whole-file replacement would move a leg's
    pin while claiming to move the shape's.

    EACH LINE KEEPS ITS OWN INDENTATION (#208). The two lines are FOUND by
    their stripped text, so a block at any indentation `load_yaml` accepts is
    recognised; they were then WRITTEN at a fixed two and four spaces, which
    turned a block indented four spaces — accepted by the reader and by both
    validators — into one the reader refuses, and the validators' refusal
    that followed blamed the project for this tool's write. Only the value
    after the key changes now; the whitespace in front of it is the line's,
    and so is a trailing `# comment` (#323: it was dropped, as the pin
    rewrites dropped theirs; `shape_materialize.with_scalar`).

    WHAT IS RETURNED HAS BEEN READ BACK. A layout this line rewrite cannot
    carry — a value on the line below its key — is refused HERE, as this
    tool's failure, rather than by a validator after the fact
    (`_refuse_unless_it_reads_back`).
    """
    lines = text.splitlines()
    start, end = _shape_block_bounds(lines, kind)
    seen = {"commit": 0, "tree": 0}
    for index in range(start + 1, end):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith("commit:"):
            seen["commit"] += 1
            lines[index] = with_scalar(line, "commit", commit)
        elif stripped.startswith("tree_sha256:"):
            seen["tree"] += 1
            lines[index] = with_scalar(line, "tree_sha256", tree)
    for key, count in seen.items():
        if count != 1:
            raise Refusal(
                "update-manifest-unrecognised",
                f"{kind.manifest}'s `shape:` block has {count} `{key}` line(s) "
                "where exactly one was expected",
                "Remediation: fix the block by hand this once; this tool will "
                "not guess at a manifest it does not recognise.")
    rewritten = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    _refuse_unless_it_reads_back(text, rewritten, commit, tree, kind)
    return rewritten


def _refuse_unless_it_reads_back(before: str, after: str, commit: str,
                                 tree: str, kind: Kind) -> None:
    """Refuse a rewrite that does not read back to the target (#208).

    THE REFUSAL IS THIS TOOL'S, SO IT IS RAISED ONLY WHEN THE FAULT IS. A
    manifest that read correctly before the rewrite and does not after it
    was broken by the rewrite, and the remedy says so. One that did not read
    before — unparsable, or no pin where the validator looks — was red
    before this command ran: that is left to the validators, which name the
    project's own line, and blaming this tool for it would be the same wrong
    answer turned around. The reading, and that question, are
    `shape_materialize.rewrite_fault`'s, shared with the two pin rewrites
    (#323).
    """
    why = rewrite_fault(before, after, commit, tree, within=("shape",))
    if why is None:
        return
    raise Refusal(
        "update-manifest-unrecognised",
        f"{kind.manifest}'s `shape:` block reads as it stands, but this "
        f"tool's rewrite of it does not read back to the target ({why}), so "
        "this tool will not write it",
        "Remediation: the fault is this tool's line rewrite, not the "
        "project's manifest. Put each of `commit:` and `tree_sha256:` on one "
        "line with its quoted value, as the scaffold writes them, and run "
        "the same command again; this tool will not guess at a manifest it "
        "does not recognise.")


def _shape_block_bounds(lines: list[str], kind: Kind) -> tuple[int, int]:
    """Where the manifest's `shape:` block starts and ends, as line indices.
    Split out of `rewrite_manifest` for #133.

    FINDING THE BLOCK IS A SEPARATE QUESTION FROM EDITING IT, and the answer
    is what scopes the edit: `commit:` and `tree_sha256:` are spelled the same
    way in every pin the manifest carries, so a rewrite that ran past the end
    of this block would move a leg's pin while claiming to move the shape's.
    The block ends at the next line that is non-blank and not indented — the
    next top-level key — or at the end of the file, which is the `shape:`
    block a scaffold writes last. No `shape:` block at all is the one
    refusal, raised here because there is nothing to return.
    """
    start = None
    for index, line in enumerate(lines):
        if line.rstrip() == "shape:":
            start = index
            break
    if start is None:
        raise Refusal(
            "update-manifest-no-shape",
            f"{kind.manifest} has no `shape:` block, so there is nothing to "
            "mirror the pin into",
            f"Remediation: `{Path(kind.manifest_validator).name}` requires "
            "one; add it, or re-scaffold.")
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.strip() and not line.startswith((" ", "\t")):
            return start, index
    return start, len(lines)


# ---------------------------------------------------------------------------
# The README line that names the standard (#148)
# ---------------------------------------------------------------------------

#: The root's own document, which is NOT a pinned copy: it has no row in
#: `contracts/shape-pin.yaml`, it is a project's to write, and the only thing
#: this tool ever changes in it is the 40 hex characters of the line below.
README = "README.md"

#: What a root's README says about the standard: the nine answers `check`
#: prints and `apply` acts on. Only ONE of them is a write.
README_ABSENT = "absent"
README_CURRENT = "current"
README_STALE = "stale"
README_AMBIGUOUS = "ambiguous"
README_OTHER_REPOSITORY = "other-repository"
README_UNREADABLE = "unreadable"
README_UNCOMMITTED = "uncommitted"
README_SYMLINK = "symlink"
README_HARDLINK = "hard-link"


def _git_answer(root: Path, args: list) -> "str | None":
    """`git <args>` run in `root`: its stdout, or None when git would not
    answer at all — a non-zero exit, no repository, no git on the path.

    None rather than an empty string because "git said nothing" and "git
    could not be asked" are different facts and `readme_is_committed`
    treats them differently. `Rollback` reads HEAD through it too (#202),
    where neither answer may raise over the refusal it is rolling back
    for, and a missing one reads as "not where it was", which the rollback
    then says. `subprocess.run` is what raises when there is no
    `git` binary, and `readme_is_committed` documents that case as NOT
    committed, so the raise is caught here rather than left to escape a
    classification that must not raise.

    READ AS UTF-8, NEVER WITH THE LOCALE'S CODEC (#217). Git writes a branch
    or path name as UTF-8 whatever the locale says. Where the codec is the
    ANSI code page — Windows without `PYTHONUTF8=1` — `feature/café` came
    back as `feature/cafÃ©`, so `Rollback` kept a start branch git has never
    heard of and could not return HEAD to the real one, and a name holding a
    byte that code page leaves undefined raised `UnicodeDecodeError` out of
    the very answer that "may not raise". `errors="replace"` keeps a name
    that is not UTF-8 at all from doing the same.
    """
    try:
        proc = subprocess.run(["git", *args], cwd=str(root),
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace", check=False)
    except OSError:
        return None
    return proc.stdout if proc.returncode == 0 else None


def readme_is_committed(root: Path) -> bool:
    """Is `README.md` exactly what HEAD has, with nothing else in it?

    THE ONE FILE THIS TOOL WRITES THAT HAS NO DRIFT CHECK. A pinned copy
    carrying a local edit is refused (`update-local-drift`) precisely so that
    `git commit -- <path>` lands this tool's bytes and nobody else's; the
    README has no pin row, so without this it would be the one path where a
    human's half-finished paragraph — staged or not — rode into a shape
    re-pin commit that `check` never showed them (Copilot, PR #152). That is
    the xFactory sweep `commit_on_branch` documents, arriving through a door
    this feature opened.

    ANY output means no: modified, staged, untracked — or IGNORED, which is
    why `--ignored` is passed. Plain `git status --porcelain` says nothing at
    all about an ignored untracked file, so a root whose `README.md` is
    ignored would have read as clean, been rewritten, and then handed `git
    commit -- README.md` a pathspec git has never heard of — a failure
    arriving after every other byte was written, on the one path
    `cmd_apply`'s `except CommandFailed` arm did not roll back until #202
    (Copilot, PR #152). Untracked-but-not-ignored was already caught; this is
    the same hazard wearing the one hat `--porcelain` hides.

    TWO QUESTIONS, BECAUSE NEITHER ANSWERS THE OTHER. `git status` reads the
    INDEX, and `git update-index --assume-unchanged` / `--skip-worktree` tell
    it to stop looking at the file: a README carrying an editor's unfinished
    paragraph under either flag reports nothing at all, while `git commit --
    README.md` goes on recording the complete working-tree file (Codex,
    PR #152). So the bytes are asked for as well — what `git hash-object`
    makes of the file on disk, against the blob `HEAD` records for that path
    — and that comparison is blind to index flags, to ignore rules and to
    whether the file is tracked at all. `hash-object` applies the same clean
    filter `git add` would, so a CRLF checkout under `core.autocrlf` hashes to
    the same blob it was committed as rather than reading as a whole-file
    edit.

    NO `--path` IS PASSED, AND THAT IS NOT AN OMISSION. A file handed to
    `hash-object` as an argument is hashed AS the path it was handed, so the
    attributes that govern `README.md` — the `* text=auto eol=lf` these
    templates ship among them — are the ones that run: `--no-filters` is the
    flag that turns the conversion OFF, and `--path` is for stdin and for
    files outside the working tree. Without that, a Windows holder's CRLF
    checkout would hash unequal to its own LF blob, read as `uncommitted`,
    and keep its stale line for ever — this feature's byte-preserving CRLF
    support defeated on the one platform that needs it (Copilot, PR #152).
    `test_a_readme_checked_out_with_crlf_is_committed_and_keeps_its_endings`
    hashes one file three ways so that stays a fact rather than a claim.

    The status question is still asked, and first: it is the one that catches
    a change STAGED but reverted in the working tree, where the bytes on disk
    do match HEAD and the commit would quietly drop what the human staged.

    A git that cannot answer (no repository, no git) is treated as NOT
    committed, which costs a rewrite in a place that could not have committed
    it anyway.
    """
    status = _git_answer(root, ["status", "--porcelain", "--ignored", "--",
                                README])
    if status is None or status.strip():
        return False
    head = _git_answer(root, ["rev-parse", f"HEAD:{README}"])
    disk = _git_answer(root, ["hash-object", "--", README])
    return bool(head and disk and head.strip() == disk.strip())


class ReadmeShapeLine:
    """The root README's ``Shape: `<repository>` @ `<sha>`.`` line, judged.

    WHY THIS EXISTS. A family holder's README is rendered with the commit the
    holder was cut from, and nothing moved it afterwards: InkRouter's holder
    named a commit four re-pins old while its pin was current (#148). The
    line is prose in a file this standard does not own, so it is never a
    refusal and never a finding — it is one sha, moved in the same commit as
    the pin it claims to name, and left strictly alone in every case where
    moving it would be a guess.

    ONE READING, TWO COMMANDS. `check` prints what `apply` WOULD do to the
    line and `apply` does it, from this same classification — two readings
    would be two answers, and the human says yes to the first.

    A REWRITE IS BYTES, not a re-rendering: only the `commit` group's span is
    replaced, so a README with CRLF endings, a BOM or a trailing form feed
    comes back byte for byte what it was apart from those 40 characters.
    """

    def __init__(self, root: Path, repository: str, target: str):
        self.root = root
        self.path = root / README
        self.repository = repository
        self.target = target
        self.text: str | None = None
        #: EVERY match, and THE match: the count is what makes a README
        #: ambiguous, and the trailing one is the only line a rewrite may
        #: move. They are two questions, so they are two attributes.
        self.matches: list = []
        self.match = None
        #: Why `unreadable` was the answer, in the clause both commands
        #: print. Bytes that are not UTF-8 and a file the OS will not hand
        #: over are the same verdict with different next moves for a human.
        self.unreadable = "not valid UTF-8"
        self.rewritten = False
        self.state = self._classify()

    def _classify(self) -> str:
        """Which of the nine answers this README gives, read once.

        NOTHING HERE RAISES, and that is not bookkeeping: `check` and the
        doctor read every root they are pointed at, and an exception escaping
        into either is a traceback about somebody else's prose. The
        `UnicodeDecodeError` branch has always been that; an `OSError` — a
        README the OS will not hand over — is the same hazard under another
        name (Copilot, PR #152). Both are READINGS rather than failures: the
        file is left alone and the reason is said.

        THE GIT QUESTION IS ASKED LAST AND ONLY OF A LINE THAT WOULD MOVE, so
        the common answers cost no subprocess at all and a README nobody is
        editing is classified exactly as before.
        """
        if self.path.is_symlink():
            # NOT WRITTEN THROUGH, EVER. `is_file()` follows the link, and a
            # rewrite would then put these bytes into the link's TARGET —
            # which a root is free to point outside itself — while the
            # symlink git tracks is unchanged, so the commit this tool makes
            # would not contain the edit it just made somebody else's file
            # (Copilot, PR #152).
            return README_SYMLINK
        if not self.path.is_file():
            return README_ABSENT
        try:
            if self.path.stat().st_nlink > 1:
                # ANOTHER NAME FOR THESE SAME BYTES. `Rollback.write`
                # overwrites a file where it stands, so a rewrite here would
                # change whatever else that inode is called — a file outside
                # the root, that no `check` showed and no pin covers — while
                # git records only `README.md` (Copilot, PR #152). For every
                # other file the ledger REFUSES such a write now (#422); the
                # README is KEPT instead, and said, because refusing the
                # re-pin over prose is no answer. Replacing the inode (a
                # temp file and `os.replace`) would make this the one write
                # in the command the ledger cannot undo: the other name
                # would keep the old bytes and the link would be broken, and
                # breaking a link is not something a rollback puts back.
                return README_HARDLINK
            self.text = self.path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            return README_UNREADABLE
        except OSError as exc:
            self.unreadable = f"not readable — {exc.strerror or exc}"
            return README_UNREADABLE
        self.matches = readme_shape_lines(self.text)
        if len(self.matches) > 1:
            return README_AMBIGUOUS
        # THE TRAILING LINE OR NOTHING. A README that carries the form
        # somewhere in the middle is showing an example of it, and an example
        # is prose about the standard rather than this root's claim about its
        # own pin — `absent` is the true answer there, and the reader is told
        # which absent it is (Copilot, PR #152).
        self.match = readme_trailing_shape_line(self.text)
        if self.match is None:
            return README_ABSENT
        if self.match["repository"] != self.repository:
            return README_OTHER_REPOSITORY
        if self.match["commit"] == self.target:
            return README_CURRENT
        if not readme_is_committed(self.root):
            return README_UNCOMMITTED
        return README_STALE

    @property
    def named(self) -> str | None:
        """The commit the TRAILING line names, or None when there is not
        exactly one line for `apply` to move."""
        return self.match["commit"] if self.match else None

    @property
    def verdict(self) -> str:
        """`check`'s row: what `apply` would do, before anybody says yes."""
        if self.state == README_STALE:
            return (f"{README_STALE} ({self.named[:12]}, pin will read "
                    f"{self.target[:12]})")
        if self.state == README_AMBIGUOUS:
            return (f"{README_AMBIGUOUS} ({len(self.matches)} Shape: lines; "
                    f"`apply` leaves {README} alone)")
        if self.state == README_OTHER_REPOSITORY:
            return (f"{README_OTHER_REPOSITORY} (names "
                    f"{self.match['repository']}, this pin is "
                    f"{self.repository}; `apply` leaves {README} alone)")
        if self.state == README_UNREADABLE:
            return f"{README_UNREADABLE} ({README} is {self.unreadable})"
        if self.state == README_ABSENT and self.matches:
            return (f"{README_ABSENT} ({README} carries a Shape: line, but "
                    "not as its last line — an example rather than this "
                    f"root's own claim; `apply` leaves {README} alone)")
        if self.state == README_UNCOMMITTED:
            # THE SAME TWO COMMITS `stale` NAMES, and in the same order: the
            # line is `uncommitted` on any disagreement with the target, and
            # `--at` can aim a re-pin BACKWARDS, so a README that has run
            # ahead of the pin would be told it is "behind" (Copilot,
            # PR #152). Naming both is true whichever way they lie.
            return (f"{README_UNCOMMITTED} ({self.named[:12]}, pin will read "
                    f"{self.target[:12]}, but {README} has changes of its "
                    "own; `apply` leaves it alone rather than commit "
                    "somebody else's edit)")
        if self.state == README_SYMLINK:
            return (f"{README_SYMLINK} ({README} is a symlink; `apply` never "
                    "writes through one)")
        if self.state == README_HARDLINK:
            return (f"{README_HARDLINK} ({README} has another name on this "
                    f"filesystem; `apply` never writes through one)")
        return self.state

    @property
    def said(self) -> str:
        """`apply`'s line, in the verb column its copies are reported in."""
        if self.state == README_STALE and self.rewritten:
            return (f"  rewrote  {README}: Shape: line {self.named[:12]} -> "
                    f"{self.target[:12]}")
        if self.state == README_CURRENT:
            return (f"  kept     {README}: Shape: line already names "
                    f"{self.target[:12]}")
        if self.state == README_AMBIGUOUS:
            return (f"  kept     {README}: {len(self.matches)} Shape: lines, "
                    "untouched — a rewrite would have to choose which of "
                    "them is the project's")
        if self.state == README_OTHER_REPOSITORY:
            return (f"  kept     {README}: its Shape: line names "
                    f"{self.match['repository']}, not {self.repository}, "
                    "untouched")
        if self.state == README_UNREADABLE:
            return f"  kept     {README}: {self.unreadable}, untouched"
        if self.state == README_UNCOMMITTED:
            return (f"  kept     {README}: its Shape: line names "
                    f"{self.named[:12]} and the pin will read "
                    f"{self.target[:12]}, but the file has uncommitted "
                    "changes, untouched — commit them and the next re-pin "
                    "carries the line")
        if self.state == README_SYMLINK:
            return (f"  kept     {README}: a symlink, untouched — a rewrite "
                    "would land in its target rather than in this root")
        if self.state == README_HARDLINK:
            return (f"  kept     {README}: another name points at these same "
                    "bytes, untouched — a rewrite would change that file too, "
                    "and git would record only this one")
        if self.state == README_ABSENT and self.matches:
            return (f"  kept     {README}: its Shape: line is not the last "
                    "line, so it is an example rather than this root's own "
                    "claim, untouched")
        return f"  kept     {README}: no Shape: line, untouched"

    def rewrite(self, ledger: Rollback) -> bool:
        """Move the sha, and only the sha, through the rollback ledger.

        Through the ledger like every other byte `apply` writes, so the red
        validator that rolls the copies back restores this too: a README
        naming a pin the tree no longer carries would be the same drift this
        fixes, made by the fix.
        """
        if self.state != README_STALE:
            return False
        start, end = self.match.span("commit")
        ledger.write(self.path, (self.text[:start] + self.target
                                 + self.text[end:]).encode("utf-8"))
        self.rewritten = True
        return True


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def accept_local_exit(path: str) -> str:
    """The one sentence `check` appends to a `both` row's detail: the exit
    AGENTS.md documents for it, once a human has merged the file by hand and
    committed that merge.

    A DISPLAY-ONLY ADDITION, not folded into `row.detail` itself: the same
    field also renders inside `apply`'s `update-conflict` refusal, whose
    wording an unaccepted `both` must keep exactly as it was.
    """
    return (f". Merge it by hand, commit it, then `apply --accept-local "
            f"{path}` so the row is recomputed from what you merged")


def keep_local_exits(path: str) -> str:
    """The sentence `check` appends to a `locally-modified` row's detail: the
    three exits `update-local-drift` names, the human's word first (#501).

    THE FLAG IS NAMED HERE, WHERE NO PASTE REACHES IT. `check`'s NEXT line
    carried `--accept-local <path>` for every such row, beside `--yes`, so
    the `apply` it handed over re-pinned the project's edit as the standard
    and the refusal that asks the human never fired. Brett Heap ruled on
    2026-10-13, "Stop pre-filling it": the NEXT leaves the flag out, and the
    row's detail may still name it, as `accept_local_exit` does for `both`.
    Display only, for the reason that function gives.
    """
    return (". Whether the project keeps the edit is the human's decision: "
            "revert it, carry it upstream, or, on their word, `apply "
            f"--accept-local {path}`")


def report(root: Path, upstream: Upstream, pinned: str, target: str,
           pin_tree: str, target_tree: str, rows: list[Row]) -> None:
    print(f"root        {root}")
    print(f"shape       {upstream.label}")
    print(f"pinned      {pinned[:12]} (tree {pin_tree[:12]}…)")
    print(f"target      {target[:12]} (tree {target_tree[:12]}…)")
    if pinned == target:
        print("            the pin already names the target commit")
    print()
    width = max(len(state) for state in ORDER)
    for state in ORDER:
        for row in rows:
            if row.state != state:
                continue
            detail = row.detail
            if row.state == BOTH and detail:
                detail += accept_local_exit(row.path)
            elif row.state == LOCALLY_MODIFIED and detail:
                detail += keep_local_exits(row.path)
            line = f"  {state:<{width}}  {row.path}"
            if detail:
                line += f"\n  {'':<{width}}  ({detail})"
            print(line)


def counted(rows: list[Row]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.state] = counts.get(row.state, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------


def prepare(args) -> tuple[Path, dict, list[Row], list[Addition], Upstream,
                           str, str, Kind]:
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        raise Refusal("update-root-missing", f"{root} is not a directory")
    kind = root_kind(root)
    pin, rows = read_pin(root)
    # THE MANIFEST IS THE OTHER RECORD `apply` REWRITES, so a link at it, or
    # above it, is refused here as `read_pin` refuses one at the pin (#286):
    # before the upstream is opened, and before any byte is written.
    linked = linked_record(root, kind)
    if linked is not None:
        raise rewrite_link_refusal([linked])
    pinned = str(pin["commit"]).lower()
    declared = str(pin.get("source_repository") or SHAPE_REPOSITORY)
    upstream = open_upstream(str(args.upstream or declared))
    upstream.repository = declared
    try:
        target = upstream.resolve(checked_value("--at", args.at)
                                  if args.at else None)
        # The pinned revision must be READABLE or the comparison is a guess.
        upstream.resolve(pinned)
        classify(root, rows, upstream, pinned, target, kind)
        additions = find_additions(root, rows, upstream, target, kind)
    except Refusal:
        upstream.close()
        raise
    return root, pin, rows, additions, upstream, pinned, target, kind


def apply_command(root: Path, label: str, target: str) -> str:
    """The `apply` that `check`'s NEXT line hands a person to paste: this
    tool run again from the checkout of the standard, pointed at `root`.

    EVERY ARGUMENT IS QUOTED FOR A POSIX SHELL (#325), the root and the
    upstream first: both are paths on somebody's disk, and a root under
    `my projects/` or `it's here/` or `$HOME` printed bare was two
    arguments, an unterminated quotation or an expansion in front of whoever
    pasted the line, which `landing_failed`'s and the rollback's lines were
    already quoted against (#202, #204). So is the branch. `shlex.join`
    leaves a value it has nothing to say about exactly as it was, so a plain
    root prints what it always printed. On POSIX: `_by_hand` says what a
    Windows root, which always holds a backslash, prints instead.

    NEVER AN `--accept-local` (#501). The line carried one for every
    `locally-modified` row, and pasted, it re-pinned the project's edit FROM
    ITS OWN BYTES: `update-local-drift`, the refusal that asks the human
    whether the project keeps that edit, never fired, and AGENTS.md tells an
    assistant both to run the line a row names and never to pass the flag
    on its own initiative. So the `apply` meets that refusal, whose
    remediation names the three exits, and `check` names the flag in the
    row's detail (`keep_local_exits`). The `--yes` stays: it is the yes the
    human gives after reading `check`, which the line follows.

    THE LANE, WHEN THE ENVIRONMENT NAMES ONE (2026-09-11, #111). A run that
    pastes this line then lands a commit carrying the `Lane:` trailer the
    protocol asks for, instead of one that has to be amended afterwards —
    which is how four InkRouter re-pins landed without it. `Co-Authored-By:`
    is NOT added here: it names a person or a model, which no environment
    variable knows. With no lane set this adds nothing at all.

    THE TRAILER IS SPELLED BY `shlex.quote` LIKE THE REST (#325), where it
    used to be wrapped in double quotes by hand: `LANE_NAME_RE` keeps those
    safe today, and a line whose every other argument goes through one quoter
    should not keep a second rule for the last one. The value has a space in
    it, so it prints in single quotes now — the form the doctor's `shape
    currency` row has always printed it in.
    """
    words = [PYTHON, Path(__file__).name, "apply", "--root", str(root),
             "--upstream", label, "--at", target, "--yes",
             "--branch", f"shape/update-{target[:12]}"]
    return shlex.join(words) + lane_trailer_argument(shlex.quote)


def cmd_check(args) -> int:
    # `pin` and `kind` are `prepare`'s own return shape, unpacked the same way
    # every caller does; this command's report never needs either -- `pinned`
    # (the commit `pin["commit"]` names, already read) and `kind.manifest`'s
    # callers are `cmd_apply`'s business, not this read-only one's.
    root, _, rows, additions, upstream, pinned, target, _ = prepare(args)
    try:
        pin_tree = upstream.tree_sha256(pinned)
        target_tree = upstream.tree_sha256(target)
        # Reported TOGETHER, because "what does this project owe the standard"
        # is one question, and an addition is as much of an answer as a changed
        # copy is. An addition the root already has a file at is reported by
        # nobody; see `Addition`.
        added = [add for add in additions if not add.present]
        reported = rows + added
        report(root, upstream, pinned, target, pin_tree, target_tree, reported)
        counts = counted(reported)
        moved = [row for row in reported if row.state != UNCHANGED]
        print()
        print("  ".join(f"{state} {counts[state]}" for state in ORDER
                        if counts.get(state)))
        # THE README'S OWN LINE, REPORTED BEFORE THE YES IS ASKED FOR. It is
        # not a pinned copy and has no verdict above; `apply` moves its sha
        # with the pin, and a human who is about to approve a re-pin should
        # read what that will do to a file this standard does not own. It
        # never moves this command's exit code: the line is prose.
        readme = ReadmeShapeLine(root, upstream.repository, target)
        print(f"readme-shape-line: {readme.verdict}")
        if not moved and pinned == target:
            print("nothing to do")
            if readme.state == README_STALE:
                # The exact state #148 was filed over, and the one run that
                # cannot fix it: `apply` writes nothing when the pin already
                # names the target, so the line moves with the NEXT re-pin.
                print(f"  ({README}'s Shape: line is stale, and this pin is "
                      "already at the target, so there is no commit to move "
                      "it in; the next re-pin carries it)")
            return 0
        if not moved:
            # AND WHAT ELSE IT WOULD MOVE. `apply` rewrites the README's
            # `Shape:` line in the pin's own commit, so on the commonest
            # holder re-pin of all — a pin behind the standard with not one
            # copied byte different — "the pin alone" was a preview of a
            # commit that would have had a second file in it (Copilot,
            # PR #152).
            alone = ("the pin alone" if readme.state != README_STALE
                     else f"the pin and {README}'s Shape: line")
            print(f"no copied file differs; `apply` would move {alone}")
        conflicts = [row for row in rows if row.is_conflict]
        if conflicts:
            print("REFUSAL AHEAD: `apply` will refuse while these are "
                  "unresolved — " + ", ".join(row.path for row in conflicts))
        _say_hard_links_ahead(root, rows)
        # NOT AN --add `apply` WOULD REFUSE (#285): a path under a file the
        # root keeps is reported above, with why, but a flag to paste that
        # is known to fail is the tool handing a human a wrong answer.
        offered = [add for add in added if add.blocked is None]
        if offered:
            # Spelled out, but deliberately NOT folded into the NEXT command:
            # a file the standard has added lands in a project because a human
            # named it, and a command line that names it for them is the tool
            # deciding.
            print("ADDED UPSTREAM: the standard has gained these since this "
                  "pin, and `apply` writes none of them unless it is told to, "
                  "one path at a time — "
                  + " ".join(f"--add {add.path}" for add in offered))
        # QUOTED WHOLE, THE LANE'S TRAILER INCLUDED, AND NEVER AN
        # `--accept-local` (#501): see `apply_command`.
        print("NEXT  " + apply_command(root, upstream.label, target))
        return 1
    finally:
        upstream.close()


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


def confirm(args, rows: list[Row], taking: list[Addition],
            target: str) -> None:
    if args.yes:
        return
    if not sys.stdin.isatty():
        raise Refusal(
            "update-unconfirmed",
            "this is not an interactive terminal and --yes was not passed, so "
            "there is nobody to ask. Overwriting a project's copies of the "
            "shape and re-recording what revision it is a copy of is not "
            "something to do on an assumption.",
            "Remediation: run it where a human can answer, or pass --yes once "
            "they have read `check`.")
    changed = [row.path for row in rows if row.state == UPSTREAM_CHANGED]
    adding = (f", adds the {len(taking)} file(s) --add named" if taking else "")
    # THE SAME YES COVERS A DROPPED ROW (#502): it is a row this re-pin
    # moves, like any other, so it is said here before anybody answers.
    merged = [row.path for row in rows if row.state == MERGED_AWAY]
    dropping = (f", drops the pin row(s) of {', '.join(merged)} (merged "
                "away)" if merged else "")
    print(f"\nThis re-copies {len(changed)} file(s) from {target[:12]}"
          f"{adding}{dropping} and re-pins this project onto it.")
    try:
        answered = input("Type yes to proceed: ").strip().lower()
    except EOFError:
        # A stream that claims to be a terminal and then ends is a place
        # nobody can be asked either: on Windows an inherited console handle
        # reports isatty() True even under CI, where the isatty() check above
        # cannot catch it. Same refusal, same wording, same exit code.
        raise Refusal(
            "update-unconfirmed",
            "this is not an interactive terminal and --yes was not passed, so "
            "there is nobody to ask. Overwriting a project's copies of the "
            "shape and re-recording what revision it is a copy of is not "
            "something to do on an assumption.",
            "Remediation: run it where a human can answer, or pass --yes once "
            "they have read `check`.")
    if answered != "yes":
        raise Refusal("update-declined", "not answered 'yes'",
                      "Remediation: nothing was written. Re-run when ready.")


def run_validator(root: Path, script: str) -> int:
    if not (root / script).is_file():
        print(f"  {script} is absent; SKIPPED")
        return 0
    sys.stdout.flush()
    # The child writes straight into this process's stdout, and takes its
    # encoding from its environment, not from the `reconfigure` `main()` did
    # (#214): under a cp1252 stdout `validate-manifest.py` raised on a display
    # name such as `日本` and this refused an `apply` the pins had no quarrel
    # with (#254). So it is told this stdout's own encoding and a handler that
    # cannot raise.
    proc = subprocess.run([sys.executable, script], cwd=str(root), check=False,
                          env=inherited_child_environment())
    sys.stdout.flush()
    return proc.returncode


def current_branch(root: Path) -> str | None:
    """The branch HEAD is on, or None when it is detached.

    Named the same as `bump-leg.py`'s own helper for the same one-line read:
    two different tools reading two different checkouts, so a shared import
    would be the wrong coupling, but no reason for the name to drift.
    """
    proc = subprocess.run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
                          cwd=str(root), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False)
    return proc.stdout.strip() or None


BRANCH_REMEDIATION = (
    "Remediation: pass a branch name such as `shape/update-<sha>`. It starts "
    "with a letter or a digit, holds only letters, digits and `. _ / @ + -`, "
    "and is one `git check-ref-format --branch <name>` accepts: no `..`, no "
    "`//`, no `@{`, no trailing `/` or `.`, and no part that starts with `.` "
    "or ends in `.lock`.")


def checked_branch(value: str) -> str:
    """`--branch`, CHECKED ONCE, in `main`, before this tool reads, writes or
    runs anything (#204).

    The value becomes `git` arguments (the branch `apply` creates and pushes,
    and the ref its re-run reads), `gh pr create --head`, and a word in the
    NEXT line a human or an agent pastes and runs. A value that starts with
    `-` is an option to whichever of those reads it first, so the alphabet
    is checked before anything else, and only a value `BRANCH_RE` admits is
    put to `git check-ref-format --branch`, which is the authority on what a
    branch name is: it is asked, not copied. A spelling it would expand
    rather than echo is refused too: `apply` names the branch it creates.
    """
    if not BRANCH_RE.fullmatch(value):
        raise Refusal(
            "update-branch-invalid",
            f"--branch {value!r} is not a branch name this tool will put on a "
            "`git` or `gh` command line: it must start with a letter or a "
            "digit and hold only letters, digits and `. _ / @ + -`",
            BRANCH_REMEDIATION)
    try:
        verdict = subprocess.run(["git", "check-ref-format", "--branch", value],
                                 capture_output=True, text=True,
                                 encoding="utf-8", errors="replace",
                                 check=False)
    except OSError as exc:
        raise Refusal(
            "update-branch-invalid",
            f"--branch {value!r} could not be checked: `git check-ref-format "
            f"--branch` could not be run ({exc})", BRANCH_REMEDIATION) from exc
    if verdict.returncode != 0 or verdict.stdout.strip() != value:
        said = (verdict.stderr or verdict.stdout).strip()
        raise Refusal(
            "update-branch-invalid",
            f"--branch {value!r} is not a branch name git will create: `git "
            "check-ref-format --branch` refuses it"
            + (f" ({said})" if said else ""), BRANCH_REMEDIATION)
    return value


def branch_exists(root: Path, branch: str) -> bool:
    """Is `branch` a local branch of `root` — checked out or not?"""
    proc = subprocess.run(
        ["git", "show-ref", "--quiet", "--verify", f"refs/heads/{branch}"],
        cwd=str(root), check=False)
    return proc.returncode == 0


def tracking_branch_of(manifest: dict | None) -> str:
    """This root's tracking branch, out of an already-loaded manifest — the
    same field `pull_request_target` lands `--pr`'s pull request on, and the
    one base `next_line` prints in the `gh pr create` it hands a human
    (#209).
    `--branch` may never commit onto it directly: these organisations are
    pull-request only, and a commit whose only next step is a push to the
    default branch is not one this tool will make.

    `main` where the manifest records none: the default `bootstrap.py`,
    `bump-leg.py` and `family.py` read the field with. The remote's own HEAD
    is never asked: a base taken from the network could disagree with the
    one the `--branch` refusal and `--pr` read from the manifest.
    """
    return str((manifest or {}).get("tracking_branch") or "main")


def pull_request_repository(manifest: dict | None,
                            kind: Kind = PROJECT_KIND) -> tuple[str, str]:
    """`(repository, why_none)`: the repository a shape update's pull request
    is opened against, out of an already-loaded manifest, and what to say
    where it names none (#209). One of the two values `pull_request_target`
    and `next_line` both have to agree on, beside `tracking_branch_of`: they
    used to settle them separately, and the printed line said `main` and
    `<org>/<Project>` whatever the manifest recorded.

    A project's is its ASSEMBLY leg's `repository:`. A family declares its
    own, having no legs to read one from, being a holder rather than a
    project: its `repository:`, or its `org:` and `name:` joined where there
    is no `repository:`. An empty answer is the caller's to act on:
    `pull_request_target` refuses with `why_none` under `--pr`, before the
    commit, since there is nothing to open a pull request against;
    `next_line` keeps the placeholder it always printed, since it runs
    after the commit and a manifest that names no repository is no reason
    to take that back; and `pull_request_line`'s bare form, the one a
    failed `--push` prints, leaves `--repo` off (#204).
    """
    manifest = manifest or {}
    if kind is FAMILY_KIND:
        # A family declares its own repository: it has no legs to read one
        # from, being a holder rather than a project.
        repository = str(manifest.get("repository") or "")
        if not repository and manifest.get("org") and manifest.get("name"):
            repository = f"{manifest['org']}/{manifest['name']}"
        return repository, (
            f"{kind.manifest} declares neither `repository:` nor an "
            "`org:`/`name:` pair, so there is no repository to open a "
            "pull request against")
    legs = [leg for leg in manifest.get("legs") or []
            if isinstance(leg, dict) and leg.get("role") == "assembly"]
    return (str(legs[0].get("repository") or "") if legs else ""), (
        "project.yaml declares no assembly leg, so there is no "
        "repository to open a pull request against")


def commit_on_branch(root: Path, branch: str, paths: list[str], target: str,
                     upstream: Upstream, count: int, kind: Kind,
                     added: list[str] = (), trailers: list[str] = (), *,
                     ledger: Rollback, dropped: list[str] = ()) -> None:
    """A branch and ONE commit, with EXPLICIT PATHSPECS.

    `git commit -- <paths>` commits the working-tree state of exactly those
    paths and nothing the index happens to be carrying. That matters wherever
    more than one session shares a checkout: a bare `git commit` takes whatever
    anyone staged, which is how a one-line bookkeeping commit swept nine
    unrelated renames into itself in the xFactory aggregation on 2026-07-29.

    A FILE `--add` JUST WROTE IS UNKNOWN TO GIT, and `git commit -- <path>`
    refuses a pathspec it has never heard of ("did not match any file(s) known
    to git"). So the additions — and ONLY the additions, by name — are staged
    first. `git add -A` here would sweep in whatever else is in the tree, which
    is the very thing the explicit pathspecs exist to prevent.

    AND THEY ARE STAGED FORCED, past the operator's own excludes
    (`force_stage`, #202). A plain `git add` honours a global
    `core.excludesFile` and `.git/info/exclude`, and one that named the path
    refused it AFTER the copies, the pin and the branch were written. A
    pinned copy the commit lacks is a red `validate-pins.py` on the next
    clone, which is why #175 forces the scaffold's own files the same way.

    EVERY ACT HERE GOES THROUGH `ledger`, and names itself first (#202):
    creating the branch, staging the additions, committing. A failure in
    any of them is rolled back by `cmd_apply` along with the copies and the
    pin — the index entries put back, HEAD returned to where it was, the
    branch this created deleted — and the refusal names the act that failed
    instead of calling every one of them "committing the re-synced shape".
    `ledger.land()` closes the ledger once the commit exists: from there on
    the commit is the result, and nothing is put back.

    THREE POSTURES FOR `--branch <name>`, decided from git rather than
    assumed, because AGENTS.md's documented `both` exit needs the second one:
    the hand merge is committed on a branch FIRST, and `apply --accept-local
    <path> --branch <that branch>` must be able to land ON it rather than
    finding `git checkout -b` refusing a branch that is already there.

      * `<name>` is the tracking branch — refused, current or not. These
        organisations are pull-request only, and a commit whose only next
        step is a push to the default branch is not one this tool will make.
      * `<name>` is the CURRENT branch (so, by the rule just above, not the
        tracking branch) — committed onto it directly, with no checkout at
        all.
      * `<name>` names a branch that exists and is NOT current — refused by
        name: committing there would land this change beside whatever a
        human already put on that branch, which is theirs to decide.
      * Anything else is created fresh, as before.

    `trailers` ARE THE LINES THIS COMMIT ENDS WITH, in the order `--trailer`
    named them (2026-09-11, #111). The lane-collision protocol wants `Lane:
    <name>` on every artifact a lane produces and the commit is one of them,
    and this estate adds `Co-Authored-By:` — neither of which a tool that
    writes its own commit message can be told any other way. Passed none, the
    message is exactly the one this function has always written; see
    `shape_materialize.commit_trailers` for the two ways git is asked.
    """
    checked_value("--branch", branch)
    manifest = load_yaml(root / kind.manifest)
    tracking = tracking_branch_of(manifest)
    if branch == tracking:
        raise Refusal(
            "update-branch-tracking",
            f"--branch {branch} names {kind.manifest}'s tracking branch, "
            "and this tool never commits a shape update directly onto it",
            "Remediation: pass a different --branch. These organisations "
            "are pull-request only; a shape update lands as a pull request "
            "onto the tracking branch, never a commit made on it directly.")
    here = current_branch(root)
    if branch != here:
        if branch_exists(root, branch):
            checked_out = (f"{here!r} is checked out" if here
                          else "HEAD is detached")
            raise Refusal(
                "update-branch-exists",
                f"--branch {branch} already exists and is not the current "
                f"branch ({checked_out})",
                "Remediation: check out that branch first — `git -C "
                f"{root} checkout {branch}` — if that is where the hand "
                "merge AGENTS.md describes was already committed, or pass "
                "a different --branch to create a new one.")
        ledger.step = f"creating the branch {branch}"
        ledger.new_branch(branch)
    if added:
        ledger.step = (f"staging the --add file(s) {', '.join(added)} on "
                       f"{branch}")
        ledger.stage(list(added))
    ledger.step = f"committing the re-synced shape on {branch}"
    gained = (f"; {len(added)} new upstream file(s) added because --add named "
              "them" if added else "")
    # `dropped` ARE THE MERGED-AWAY ROWS (#502): a pin change no copied byte
    # explains, so the message says which rows went and why.
    if dropped:
        gained += (f"; the pin row(s) of {', '.join(dropped)} dropped, each "
                   "a collision copy merged into the file it collided with")
    # READ OFF THE PATHSPECS RATHER THAN PASSED IN: `README.md` is in `paths`
    # only when `_rewrite_readme` moved its sha, so the message names the one
    # file in this commit that carries no pin row and would otherwise read as
    # an unexplained edit to a document the project owns (#148).
    prose = (f", and {README}'s `Shape:` line now names it too"
             if README in paths else "")
    message = (
        f"Re-sync the shape copies to {upstream.repository} @ {target[:12]}\n\n"
        f"{count} copied file(s) re-copied from the upstream{gained}; "
        f"contracts/shape-pin.yaml and {kind.manifest}'s `shape:` block now "
        f"record {target}{prose}.\n\nWritten by update-shape.py; the copies "
        f"are not hand-edited and the digests are recomputed, not "
        f"adjusted.\n")
    env = dict(os.environ)
    for key, fallback in (("GIT_AUTHOR_NAME", "openRepoShape update"),
                          ("GIT_COMMITTER_NAME", "openRepoShape update"),
                          ("GIT_AUTHOR_EMAIL", "update@openreposhape.invalid"),
                          ("GIT_COMMITTER_EMAIL", "update@openreposhape.invalid")):
        if not env.get(key):
            env[key] = fallback
    message, trailer_args = commit_trailers(message, trailers)
    args = ["git", "commit", "-q", "-F", "-", *trailer_args, "--", *paths]
    check_program(args)
    proc = subprocess.run(args, cwd=str(root), input=message,
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False,
                          env=env)
    if proc.returncode != 0:
        raise CommandFailed(args, root, proc.returncode,
                            proc.stderr + proc.stdout)
    ledger.land()


class Rollback:
    """Every byte `apply` writes, every change it makes to git before its
    commit lands, and how to put all of it back.

    ONE LEDGER, TWO KINDS OF WRITE, because the undo differs. A file the root
    already had is restored from the original bytes kept here; a file `--add`
    created has to be DELETED, along with any directory that had to be made to
    hold it. `cmd_apply` carried both as closures over two of its own locals
    and the undo as two loops in an `except` arm — together about a third of
    the 47 Sonar scored that function at. Split out for #133, with the same
    writes in the same order and the same undo.

    THE BRANCH AND THE INDEX ARE WRITES TOO (#202). `--branch` creates a
    branch and checks it out, and `--add` stages its files, BEFORE the commit
    both exist for. A failure between them — an addition the operator's
    excludes ignore, a pre-commit hook that says no, a branch name git cannot
    create — printed `REFUSED committing the re-synced shape` and returned
    with the copies, the pin and the new branch all left in place, so the
    next `check` read that uncommitted re-pin as the truth and said "nothing
    to do". So both go through here, and `undo` puts them back with the rest.

    UNTIL THE COMMIT LANDS, AND NEVER AFTER. `land` closes the ledger: from
    then on the commit IS the result, and writing the old bytes back would
    leave a tree that reverts it. A push or a pull request that fails after
    that rolls nothing back (#204 is about what it says instead).
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.written: dict[Path, bytes] = {}
        self.created: list[Path] = []
        #: The act `apply` is in, which is what a failed git command's
        #: refusal names. `commit_on_branch` moves it before each act.
        self.step = "re-syncing the shape"
        #: `(the branch created, the branch HEAD was on — None when it was
        #: detached — and the commit HEAD named)`, once `new_branch` has
        #: been asked for, whether or not git then managed it.
        self.branch: tuple[str, str | None, str] | None = None
        #: The paths `stage` forced, and the index's `--stage` records for
        #: them as they were before, NUL-terminated (`ls-files -s -z`).
        self.staged: list[str] = []
        self.index_before = b""
        self.landed = False

    def write(self, path: Path, data: bytes) -> None:
        """Overwrite a file the root already has, keeping its first bytes.

        `setdefault` so a path written twice is still restored to what it held
        before the FIRST write; nothing does that today, and a ledger that
        remembered the second write would silently stop being a rollback.

        ONE HANDLE, OPENED FOR WRITING BEFORE ANYTHING IS RECORDED. A path
        this process cannot write — a read-only README, a permission a
        sandbox took away — used to be READ into the ledger and only then
        fail on the write, which left the undo trying to write that same
        unwritable path: the rollback would raise part way through and the
        copies and the pin would stay half-updated, which is the tree
        `except Refusal` exists to prevent (Copilot, PR #152). `r+b` fails
        before the ledger has promised anything, so a refusal raised over a
        write that could not happen rolls back a tree this ledger can
        actually restore.

        NEVER THROUGH A SYMLINK (#286). `r+b` follows a link, at the path or
        on its way down. `prepare` refuses a linked pin or manifest and
        `apply` a `copy-is-link` row, but this runs later — after `confirm`
        has waited for a human — and a link can arrive in between. So the
        path is walked again here and a link refused by name before anything
        is read or recorded, and `cmd_apply`'s refusal arm puts back what
        was written before it. What the walk cannot see is a link that
        arrives in the instant between it and the open, as
        `write_added` cannot see one that arrives above its path.

        NOR THROUGH A HARD LINK (#422). `r+b` overwrites the bytes where they
        are, and a file with a second name — anywhere on this filesystem, a
        `cp -al` snapshot of the whole root included — is the same bytes
        under both, so that other name would change too: a file no `check`
        showed and no pin covers, while git records only this one. `apply`
        refuses every such file before `confirm` waits
        (`_refuse_hard_linked_rewrites`); this asks the same question,
        `hard_links`, after the symlink walk and before anything is read or
        recorded, for a name that arrived while it waited, and the same
        refusal arm puts back what was written before it. NOT BY REPLACE,
        which is the other way to write and the one the README's own guard
        rejects: a new file moved in with `os.replace` leaves the other name
        holding the old bytes and the link broken, and a broken link is not
        something `undo` can put back.
        """
        rel = self._name(path)
        link = symlink_on_the_way(self.root, rel)
        if link is not None:
            raise rewrite_link_refusal([(rel, link)], arrived=True)
        names = hard_links(path)
        if names:
            raise hard_link_refusal(self.root, [(rel, names)], arrived=True)
        with path.open("r+b") as handle:
            self.written.setdefault(path, handle.read())
            handle.seek(0)
            handle.write(data)
            handle.truncate()

    def write_added(self, path: Path, data: bytes, executable: bool) -> None:
        """A file the root does not have yet, remembered for the rollback.

        `write` cannot serve it: there are no original bytes to keep, so the
        rollback has to DELETE what this made — including any directory it had
        to create to put the file in. The mode is set the way `_materialize`
        sets it, which is to chmod the executables and leave everything else to
        the umask.

        CREATED EXCLUSIVELY, AND RECORDED ONLY ONCE IT EXISTS (#239). `prepare`
        looked at the path, but this runs later — after `confirm` has waited
        for a human — and a link or a file can arrive in between. `xb` is
        `O_CREAT|O_EXCL`, which POSIX fails on any name already there, a
        dangling link included, where `write_bytes` followed the link and
        created what it points at; `mkdir` fails the same way on a dangling
        directory link above the path. The ledger had recorded the path before
        writing it, so a red validator's undo then unlinked the operator's link
        and left the file at its end. Now a path is recorded once this run has
        made it, and a name already taken is a refusal, which `cmd_apply`'s
        arm answers by putting back the copies written before it. What an
        exclusive create cannot see is a LIVE directory link that arrives
        ABOVE the path in that window: the create follows it, as every `open`
        does.
        """
        try:
            for parent in reversed([p for p in path.parents
                                    if not p.exists()]):
                parent.mkdir()
                self.created.append(parent)
            handle = path.open("xb")
        except FileExistsError:
            raise self._taken(path) from None
        self.created.append(path)
        with handle:
            handle.write(data)
        if executable:
            path.chmod(0o755)

    def _taken(self, path: Path) -> Refusal:
        """The refusal for a name `write_added` found taken: the link, by
        name, when there is one on the way to `path`, and otherwise whatever
        the root now has there."""
        rel = self._name(path)
        link = symlink_on_the_way(self.root, rel)
        if link is not None:
            return link_refusal(rel, link)
        return Refusal(
            "update-add-would-overwrite",
            f"--add {rel}: this root had nothing at {rel} when this run "
            "looked, and has something there now. Writing over it would "
            "replace bytes no pin row records",
            f"Remediation: look at what is at {rel}. If it is the project's, "
            "a human merges, as for any path the root holds, and `check` "
            "stops reporting it; if it is not, remove it and run this command "
            "again with the same --add.")

    @contextlib.contextmanager
    def writing(self, step: str) -> Iterator[None]:
        """`step`, a phase that writes bytes through this ledger, with an
        `OSError` out of it turned into a refusal that names the step, the
        path and the error (#285).

        A WRITE THAT FAILS IS A REFUSAL, NEVER A TRACEBACK, for the reason
        `_rewrite_readme` gives for its own: `cmd_apply` rolls back on
        `Refusal` and `CommandFailed` and on nothing else. A directory this
        process cannot write, a file where `--add` has to make a directory,
        a read-only pin, a disk that filled — each escaped as a traceback
        with every copy written before it left in place and the pin
        unmoved, so the next `check` read those copies as
        `already-at-target`. Named as a refusal, the arm that exists puts
        every byte back, and lists what it put back under this detail
        (`_rolled_back`), so the detail does not claim it as well.

        `step` is the refusal's own, not `self.step`, which names the git
        act a `CommandFailed` is reported under.
        """
        try:
            yield
        except OSError as exc:
            name = exc.filename
            at = (f" at {self._name(Path(os.fsdecode(name)))}"
                  if isinstance(name, (str, bytes, os.PathLike)) else "")
            raise Refusal(
                "update-write-failed",
                f"{step} failed{at}: {exc.strerror or exc}",
                "Remediation: clear what stopped the write — a permission, "
                "a read-only or full disk, a file where a directory has to "
                "be — and run the same command again.") from exc

    def new_branch(self, branch: str) -> None:
        """`git checkout -b <branch>`, remembered so `undo` can take it back.

        Recorded BEFORE git is asked, so a checkout that fails part way is
        undone from what is actually there afterwards rather than from what
        was hoped for. The branch HEAD was on is kept as git spells it under
        `refs/heads/`, never `--short`'s answer: with a tag of the same name
        that is `heads/main`, and `git checkout heads/main` DETACHES HEAD
        rather than returning to the branch.
        """
        head = _symbolic_head(self.root)
        start = (head[len("refs/heads/"):]
                 if head and head.startswith("refs/heads/") else None)
        commit = run(["git", "rev-parse", "HEAD"], cwd=self.root)
        self.branch = (branch, start, commit)
        run(["git", "checkout", "-q", "-b", branch], cwd=self.root)

    def stage(self, paths: list[str]) -> None:
        """`force_stage` the additions, remembering what the index held for
        each so `undo` can put exactly that back.

        NOT `git reset -- <paths>` on the way back, which writes HEAD's entry
        rather than the one that was there: a path somebody had staged as
        DELETED would come back staged as present, and an index this tool
        changed without being asked is the xFactory sweep `commit_on_branch`
        exists to prevent, arriving the other way round.
        """
        self.index_before = self._index_entries(paths)
        self.staged = list(paths)
        force_stage(self.root, paths)

    def land(self) -> None:
        """The commit exists. It is the result now, and nothing is undone."""
        self.landed = True

    def undo(self) -> str | None:
        """Put the tree back exactly as it was, and say what was put back.

        Returns the lines a refusal prints, or None when there was nothing to
        put back: no write had been made yet, or the commit landed and IS
        the result.

        LAST WRITE FIRST: the index, then the branch, then the bytes. The
        branch this run created names the commit HEAD named, so returning to
        the branch it started on moves HEAD and nothing else, and the bytes
        are restored whichever branch is checked out. Restores, then unwinds
        the creations in reverse so a directory is only considered after the
        file it was made for is gone. A directory that is not empty is LEFT:
        something nobody here wrote is in it, and removing that is not a
        rollback.

        NEITHER HALF RAISES OVER THE REFUSAL (#428), which is the rule
        `bump-leg.py`'s own rollback states (#253): what it cannot put back
        is NAMED, with the command that finishes it by hand, and the failure
        that started the rollback is still the one reported. The git half
        always kept it. The byte half wrote each file back with a bare
        `write_bytes` and took away what `--add` made with a bare `rmdir` or
        `unlink`, so one file that would not take its old bytes — a
        permission a validator took away, a full disk, a lock — escaped
        `_rolled_back` and `main` as a traceback, exit 1, the refusal that
        started it surviving only as the exception's context, and no path
        after it was tried: a pin put back under a manifest left re-pinned,
        the lockstep break this ledger exists to prevent. So every restore
        and every removal is attempted, each under its own handler, and each
        one that fails is listed with its line (`_restore`, `_remove`). And
        each git undo is judged by READING THE STATE AFTERWARDS rather than
        by git's exit code — a `post-checkout` hook's exit status is `git
        checkout`'s own, so a switch that happened can still exit non-zero.
        """
        if self.landed or not (self.written or self.created or self.branch
                               or self.staged):
            return None
        done: list[str] = []
        left: list[str] = []
        self._undo_index(done, left)
        self._undo_branch(done, left)
        for path, original in self.written.items():
            self._restore(path, original, done, left)
        stuck: list[Path] = []
        for path in reversed(self.created):
            self._remove(path, stuck, done, left)
        return self._said(done, left)

    def _restore(self, path: Path, original: bytes, done: list[str],
                 left: list[str]) -> None:
        """`path` given back `original`, the bytes it held before this run
        first wrote it, or listed under `left` with the line that does it
        by hand (#428).

        WRITTEN ONLY OVER A FILE THAT NO LONGER HOLDS THEM, as `bump-leg.py`
        restores its own (`_restore_file`, #253): a file that holds what it
        held is back, and a write it never needed must not list it as left
        because that write would have failed. One that cannot even be READ
        is written all the same.

        NEVER THROUGH A LINK THAT ARRIVED AFTER THE WRITE (review of PR
        #560). `write` walked the path for a symlink and counted its names
        before it wrote, but the project's own validators run between that
        write and this one, and so can anything else on the machine: a
        validator that moved `project.yaml` out of the root and linked it
        back had the old bytes written at the link's end, outside the root,
        under "the tree is exactly as it was" over a root holding a link.
        So the same two questions are asked again here first, and a path
        either one answers is not written at all: it is listed under `left`,
        with what stands there and the line that puts the bytes back once
        it is a plain file of its own again.
        """
        name = self._name(path)
        link = symlink_on_the_way(self.root, name)
        names = hard_links(path) if link is None else 0
        if link is not None or names:
            left.append(f"file      {name} was not put back: "
                        + self._linked_by_hand(path, name, original, link,
                                               names))
            return
        try:
            held = path.read_bytes()
        except OSError:
            held = None
        try:
            if held != original:
                path.write_bytes(original)
        except OSError as exc:
            where, command = self._restore_by_hand(path, name, original)
            # "MAKE IT WRITABLE" IS SAID OF A FILE THAT IS THERE (review of
            # PR #560, round 2). A directory a validator deleted took the
            # file with it, and a file that is not there cannot be made
            # writable: the line is then the command alone, which creates it.
            how = (f"{where}, so make it writable, then: {command}"
                   if os.path.lexists(path) else f"{where}, then: {command}")
            left.append(f"file      {name} was not put back "
                        f"({exc.strerror or exc}); "
                        + (how if command else where))
            return
        done.append(f"restored  {name}")

    def _linked_by_hand(self, path: Path, name: str, original: bytes,
                        link: tuple[str, str] | None, names: int) -> str:
        """The rest of `_restore`'s `left` line for a path it would not
        write: what arrived there, and how the bytes go back by hand.

        A SYMLINK is the operator's, or whoever made it, so the line never
        removes it: the bytes go back once it is not a link, which is the
        same exit `update-rewrite-symlink` gives before a write. One ABOVE
        the path is a directory moved out of the root and linked back, and
        is said as that: once it is this root's own directory again, since
        a command run over a link merely removed has no directory to write
        into (probed in the round-2 review). A SECOND
        NAME is broken from this side first, with the line
        `update-rewrite-hardlink` prints (`_copy_over_itself`), so the
        other name keeps the bytes it holds: a `cat-file` redirect writes
        in place, and would change it too.
        """
        where, command = self._restore_by_hand(path, name, original)
        if link is not None:
            said = (f"since this run wrote it, {link_said(name, link)}, and "
                    "this run never writes through one")
            # A link ABOVE the path is a directory that is no longer this
            # root's own (review of PR #560, round 2): "is not a link" read
            # as "remove it", and with the link gone and nothing in its
            # place the command fails, "Directory nonexistent".
            again = (f"{link[0]} is not a link" if link[0] == name else
                     f"{link[0]} is this root's own directory again")
            fix = (f"{where}, so once {again}: {command}"
                   if command else where)
        else:
            said = (f"since this run wrote it, it has gained another name "
                    f"on this filesystem ({names} names), and a write in "
                    "place would change that file too")
            fix = (f"{where}, so replace it with a copy of itself first: "
                   f"{_copy_over_itself(path)}, then: {command}"
                   if command else where)
        return f"{said}; {fix}"

    def _restore_by_hand(self, path: Path, name: str,
                         original: bytes) -> tuple[str, str]:
        """Where `original` is to be had, and the command that writes it at
        `path` by hand, once whatever stopped the write is cleared; or, when
        it is nowhere, the sentence saying so and no command.

        HEAD'S, WHERE `git checkout HEAD -- <path>` WOULD WRITE EXACTLY THOSE
        BYTES AND CHANGE NOTHING ELSE (`_head_restores`). That is not a
        given, and it was measured: a `--branch` run over a clean tree holds
        HEAD's bytes at every path it writes, but an `apply` without
        `--branch` writes over whatever the tree holds — after an earlier
        `apply` left uncommitted, not one of the copy, the pin and the
        manifest was HEAD's — and even `--branch` takes a working-tree file
        whose CRLF `hash-object` normalises away (`_not_what_head_commits`),
        which a checkout would then write back as LF. AND ONLY WHERE THE
        DIRECTORY TAKES A NEW FILE (review of PR #560): a checkout unlinks
        the path and creates it again, which a directory nobody may write
        into refuses however writable the file is made, while a redirect
        writes into the file where it stands. The directory asked is the
        NEAREST ONE THAT EXISTS (`_nearest_directory`): a validator that
        deleted `contracts/` left none to ask at the path's own parent, and
        git makes the missing ones, so the question is whether what is
        there takes them (round 2 of the review).

        ELSE FROM THE OBJECT STORE. The bytes are written into this
        repository with `git hash-object -w --stdin` — on stdin, so no
        filter touches them — and `git cat-file blob <id>`, redirected to
        the file's own path, writes back exactly those bytes. The object is
        referenced by nothing, so a `git gc` prunes it, two weeks on by
        default: long enough for a line meant to be run now. A directory
        that is gone is made first, `mkdir -p <directory> && ...`, which
        keeps it one pasteable command. Where git will not store them
        either, the line says so, and that the bytes are
        nowhere this run can point at.
        """
        if (os.access(self._nearest_directory(path.parent), os.W_OK)
                and self._head_restores(name, original)):
            return ("it held HEAD's bytes",
                    _by_hand(self.root, "--literal-pathspecs", "checkout",
                             "HEAD", "--", name))
        kept = self._kept(original)
        if kept:
            # A redirect creates the file and never the directory above it,
            # so a directory a validator deleted is made first, in the same
            # command (round 2 of the review): "Directory nonexistent".
            make = ("" if os.path.isdir(path.parent) else
                    "mkdir -p " + shlex.quote(str(path.parent)) + " && ")
            return (f"its bytes before this run are kept as blob "
                    f"{kept[:12]} in this repository",
                    make + _by_hand(self.root, "cat-file", "blob", kept)
                    + " > " + shlex.quote(str(path)))
        return ("and git would not keep its bytes before this run either, "
                "so they are nowhere this run can point at: only a copy of "
                f"{name} made before it can put it back", "")

    @staticmethod
    def _nearest_directory(directory: Path) -> Path:
        """`directory` when it is one, else the nearest directory above it
        that is: the one `git checkout` would have to write into to make
        what is missing. `os.path.isdir`, which answers False rather than
        raising for a path it may not look at."""
        while not os.path.isdir(directory) and directory != directory.parent:
            directory = directory.parent
        return directory

    def _head_restores(self, name: str, original: bytes) -> bool:
        """Would `git checkout HEAD -- <name>` write exactly `original` and
        leave the index as it is? Three answers from git, any one missing a
        no: HEAD commits a blob at `name`; the index holds that same blob
        there, so the checkout, which writes the index too, changes nothing
        in it (the hazard `Rollback.stage` names); and that blob as a
        checkout writes it — `cat-file --filters`, smudge and line-ending
        conversion included — is `original`, byte for byte."""
        head = _head_blob(self.root, name)
        staged = _git_answer(self.root, ["rev-parse", "--verify", "--quiet",
                                         f":0:{name}"])
        if not head or (staged or "").strip() != head:
            return False
        proc = _git_quietly(["git", "cat-file", "--filters", f"HEAD:{name}"],
                            self.root)
        return (proc is not None and proc.returncode == 0
                and proc.stdout == original)

    def _kept(self, original: bytes) -> str:
        """The id of `original`, written into this repository's objects as
        BYTES on stdin, or "" when git will not store it."""
        proc = _git_quietly(["git", "hash-object", "-w", "--stdin"],
                            self.root, original)
        if proc is None or proc.returncode != 0:
            return ""
        kept = proc.stdout.decode("ascii", "replace").strip()
        return (kept if re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", kept)
                else "")

    def _remove(self, path: Path, stuck: list[Path], done: list[str],
                left: list[str]) -> None:
        """What `write_added` made at `path` — an `--add` file, or a
        directory made to hold one — taken away, or listed under `left`
        with the POSIX line that does it by hand (#428).

        `stuck` collects what could not be taken away. A directory still
        holding one of those is listed as left after it, with its own line,
        never as kept for "something this run did not write": what is in it
        is this run's own file. A path is a directory here when
        `write_added` made it to hold another path it made, which is what
        names the line's verb when even asking what stands there fails.

        NOTHING IS REMOVED AT OR THROUGH A SYMLINK that arrived after the
        write (review of PR #560), for `_restore`'s reason: unlinking one at
        the path deletes the operator's link (#239 measured that), and
        removing under one deletes at its end. It is listed instead.
        """
        name = self._name(path)
        directory = any(path in made.parents for made in self.created)
        link = symlink_on_the_way(self.root, name)
        if link is not None:
            stuck.append(path)
            what = (f"directory {name}/, made to hold an --add file,"
                    if directory else f"file      {name}, written by --add,")
            left.append(f"{what} was not removed: since this run wrote it, "
                        f"{link_said(name, link)}, and this run never "
                        "removes at or through a link it did not make; "
                        "what it leads to is yours to judge")
            return
        try:
            if path.is_dir():
                if not any(path.iterdir()):
                    path.rmdir()
                    done.append(f"removed   {name}/ (made to hold an --add "
                                "file)")
                elif any(path in kept.parents for kept in stuck):
                    stuck.append(path)
                    left.append(f"directory {name}/, made to hold an --add "
                                "file, still holds the one above; once that "
                                "is gone: "
                                + shlex.join(["rmdir", "--", str(path)]))
                else:
                    done.append(f"kept      {name}/ (made to hold an --add "
                                "file, and something this run did not "
                                "write is in it now)")
            elif path.exists():
                path.unlink()
                done.append(f"removed   {name} (written by --add)")
        except OSError as exc:
            stuck.append(path)
            what, verb = ((f"directory {name}/, made to hold an --add file,",
                           "rmdir") if directory else
                          (f"file      {name}, written by --add,", "rm"))
            left.append(f"{what} was not removed ({exc.strerror or exc}): "
                        + shlex.join([verb, "--", str(path)]))

    def _name(self, path: Path) -> str:
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return str(path)

    def _index_entries(self, paths: list[str]) -> bytes:
        """What the index records for `paths`, as `ls-files -s -z` prints
        it — which is also the form `update-index --index-info` reads back.
        BYTES, never text: a path is whatever bytes git holds, and Windows
        must not translate a record on its way back to git. LITERALLY, as
        `force_stage` names them: read as globs, `docs/guide[1].md` would
        also record `docs/guide1.md`, an entry this run never touched."""
        args = ["git", "--literal-pathspecs", "ls-files", "--stage", "-z",
                "--", *paths]
        check_program(args)
        proc = subprocess.run(args, cwd=str(self.root), capture_output=True,
                              check=False)
        if proc.returncode != 0:
            raise CommandFailed(args, self.root, proc.returncode,
                                proc.stderr.decode("utf-8", "replace"))
        return proc.stdout

    def _undo_index(self, done: list[str], left: list[str]) -> None:
        """Every path `stage` forced, back to the entry it had before:
        removed, then the old record written back if there was one."""
        if not self.staged:
            return
        names = " ".join(self.staged)
        _git_quietly(["git", "update-index", "-z", "--force-remove",
                      "--stdin"], self.root,
                     b"".join(os.fsencode(path) + b"\0"
                              for path in self.staged))
        if self.index_before:
            _git_quietly(["git", "update-index", "-z", "--index-info"],
                         self.root, self.index_before)
        try:
            restored = self._index_entries(self.staged) == self.index_before
        except CommandFailed:
            restored = False
        if restored:
            done.append(f"unstaged  {names} (the index holds what it held "
                        "before this run)")
        else:
            left.extend(_index_by_hand(self.root, self.staged,
                                       self.index_before))

    def _undo_branch(self, done: list[str], left: list[str]) -> None:
        """HEAD back where it was, and the branch this run created gone —
        but only while that branch still names the commit it was created
        at, which `update-ref -d <ref> <old>` checks for itself, and never
        while HEAD is still attached to it.

        THE BRANCH HEAD IS ON IS NOT DELETED (#202). The switch back is a
        `git checkout`, and it can fail — a `.git/index.lock` an editor's
        `git status` holds for a moment is enough. `update-ref -d` does not
        take that lock, so it went on to delete the branch under HEAD, which
        then named no commit: `git status` said "No commits yet" and listed
        every file as staged for a first commit, in a repository with a
        history. The branch is LEFT and listed, with the switch and then
        the deletion, in the order that works: git itself refuses `branch
        -D` on the branch that is checked out.
        """
        if self.branch is None:
            return
        branch, start, commit = self.branch
        ref = f"refs/heads/{branch}"
        where = start or f"{commit[:12]} (detached)"
        back = [start] if start else ["--detach", commit]
        moved = _symbolic_head(self.root) == ref
        if moved:
            _git_quietly(["git", "checkout", "-q", start, "--"] if start
                         else ["git", "checkout", "-q", "--detach", commit,
                               "--"], self.root)
        if self._head_is(start, commit):
            done.append(f"switched  HEAD back to {where}" if moved
                        else f"kept      HEAD on {where}, where it started")
        else:
            left.append(f"HEAD      is not back on {where}: "
                        + _by_hand(self.root, "checkout", *back))
        if not branch_exists(self.root, branch):
            done.append(f"absent    {branch} (never created)")
            return
        if _symbolic_head(self.root) == ref:
            left.append(f"branch    {branch}, which this run created, was not "
                        "deleted because HEAD is still on it (HEAD would "
                        "name no commit); switch first, then delete: "
                        + _by_hand(self.root, "checkout", *back) + " && "
                        + _by_hand(self.root, "branch", "-D", branch))
            return
        _git_quietly(["git", "update-ref", "-d", ref, commit], self.root)
        if branch_exists(self.root, branch):
            left.append(f"branch    {branch}, which this run created, is "
                        "still there: "
                        + _by_hand(self.root, "branch", "-D", branch))
        else:
            done.append(f"deleted   {branch} (this run created it; nothing "
                        "was committed on it)")

    def _head_is(self, start: str | None, commit: str) -> bool:
        head = _symbolic_head(self.root)
        if start:
            return head == f"refs/heads/{start}"
        named = _git_answer(self.root, ["rev-parse", "HEAD"])
        return head is None and (named or "").strip() == commit

    @staticmethod
    def _said(done: list[str], left: list[str]) -> str:
        """The block a refusal prints under its own first line. A rollback
        that put nothing back says `nothing` there, rather than run its
        heading straight into the list of what is left (#428): every restore
        can fail, on a disk that filled, now that one failing no longer
        stops the rest."""
        lines = (["ROLLED BACK IN PART: the tree is NOT as it was. Put back:"]
                 if left else
                 ["ROLLED BACK: every byte this command wrote has been put "
                  "back, and the tree is exactly as it was:"])
        lines += [f"    {line}" for line in done] or ["    nothing"]
        if left:
            lines.append("  NOT put back — finish these by hand:")
            lines += [f"    {line}" for line in left]
        return "\n".join(lines)


def _symbolic_head(root: Path) -> str | None:
    """The FULL ref HEAD is attached to (`refs/heads/<name>`), or None when
    it is detached — the spelling `Rollback` keeps, for the reason
    `Rollback.new_branch` gives. Asked through `_git_answer`, as
    `readme_is_committed` asks its own, rather than a second copy of it."""
    answer = _git_answer(root, ["symbolic-ref", "--quiet", "HEAD"])
    return (answer or "").strip() or None


def _by_hand(root: Path, *args: str) -> str:
    """`git -C <root> <args>` as a line a person pastes, every argument
    quoted for a POSIX shell: a root or a name holding a space is one
    argument there, not two (#202).

    ALL THREE HAND FIXES A PARTIAL ROLLBACK PRINTS — the index's, HEAD's and
    the branch's — are spelled here, so one block never quotes two ways.
    `shlex`, the standard library's, because this tool has no quoter of its
    own: the doctor's platform-aware `quote_arg` lives in `shape-doctor.py`
    by that file's own contract. A value that needs no quoting comes back
    exactly as it went in, so ON POSIX an ordinary root prints what it
    always printed. ON WINDOWS IT DOES NOT: every root there holds a
    backslash, which is outside `shlex`'s safe set, so `shlex.join` quotes
    the root and a line that used to print it bare now prints it in single
    quotes. That is deliberate, and not worth a second quoter: these are
    lines for a POSIX shell — Git Bash is one, cmd.exe and PowerShell are
    not — as this tool's other `NEXT` lines are too.
    """
    return shlex.join(["git", "-C", str(root), *args])


def _index_by_hand(root: Path, paths: list[str], before: bytes) -> list[str]:
    """What a partial rollback prints for an index it could not put back:
    for each path `Rollback.stage` forced, the command that writes back
    exactly the entry it had before this run — or none, when it had none.
    `before` is `Rollback.index_before`, `ls-files --stage -z` records.

    NEVER `git reset -- <path>`, which this used to print (#202). That
    writes HEAD's entry rather than the one that was there — the hazard
    `Rollback.stage` names — so a draft somebody had staged at the path
    would have been "put back" as HEAD's, or as nothing, by the very line
    that claimed to finish the rollback. So each path gets its own fix:
    none before is `update-index --force-remove`; one staged entry before
    is that entry, through `--cacheinfo` (with `--add`, because the undo
    that failed may already have removed it); an UNMERGED path is its
    stages, through `--index-info`, the only way git takes them back.
    `update-index` reads a path literally, never as a pathspec, and
    `_by_hand` quotes it, so the shell does not glob it either.
    """
    had: dict[str, list[tuple[str, str, str]]] = {}
    for record in before.split(b"\0"):
        if record:
            meta, _, name = record.partition(b"\t")
            mode, sha, stage = meta.decode("ascii").split(" ")
            had.setdefault(os.fsdecode(name), []).append((mode, sha, stage))
    lines = []
    for path in paths:
        entries = had.get(path, [])
        said = f"index     {path} may still hold this run's entry; it "
        if not entries:
            lines.append(f"{said}had none before: " + _by_hand(
                root, "update-index", "--force-remove", "--", path))
        elif len(entries) == 1 and entries[0][2] == "0":
            mode, sha, _ = entries[0]
            lines.append(
                f"{said}had {mode} {sha[:12]} staged before, and `git "
                "reset` would write HEAD's entry in its place, which is "
                "not necessarily that one: " + _by_hand(
                    root, "update-index", "--add", "--cacheinfo",
                    f"{mode},{sha},{path}"))
        else:
            fields = [field for mode, sha, stage in entries
                      for field in (mode, sha, stage, path)]
            lines.append(
                f"{said}was unmerged before (stages "
                f"{', '.join(stage for _, _, stage in entries)}), which "
                "`git reset` would resolve to HEAD's: "
                + _by_hand(root, "update-index", "--force-remove", "--", path)
                + " && printf " + shlex.quote("%s %s %s\\t%s\\0") + " "
                + shlex.join(fields) + " | "
                + _by_hand(root, "update-index", "-z", "--index-info"))
    return lines


def _git_quietly(args: list[str], root: Path, data: bytes | None = None
                 ) -> subprocess.CompletedProcess | None:
    """`args` run in `root` for a rollback, with `data` as BYTES on stdin:
    the completed process, or None when git could not be started at all.

    Never raises on git's exit: a rollback that raised part way would leave
    the tree half put back AND replace the refusal that explains why it was
    rolled back with one about the rollback. Every caller reads the state
    afterwards instead, and says what it found.
    """
    check_program(args)
    try:
        return subprocess.run(args, cwd=str(root), input=data,
                              capture_output=True, check=False)
    except OSError:
        return None


def _refuse_unknown_accept_local(rows: list[Row], accepted: set) -> None:
    """`--accept-local` on a path the pin carries no row for. Split out of
    `cmd_apply` for #133, and asked FIRST for the reason the remediation
    gives: a mistyped path reported as a drift refusal sends a human looking
    for drift that is not there.
    """
    stray = accepted - {row.path for row in rows}
    if stray:
        raise Refusal(
            "update-accept-local-unknown",
            f"--accept-local names {sorted(stray)}, which the shape pin "
            "does not carry a row for",
            "Remediation: only a pinned copy can be accepted; a file with "
            "no row is not a shape copy. Checked FIRST, before the drift "
            "refusal, so a mistyped path is reported as a mistyped path.")


def _refuse_linked_copies(rows: list[Row]) -> None:
    """`update-rewrite-symlink` for every `copy-is-link` row at once (#286).

    ASKED BEFORE `update-conflict`, though the rows count among the
    conflicts `check` names: that refusal's remedy is a hand merge and
    `--accept-local`, and neither is the answer for a link. `--accept-local`
    on such a path accepts nothing — there is no local edit to trust, only
    a place this command does not write.
    """
    linked = [(row.path, row.link) for row in rows
              if row.state == COPY_IS_LINK and row.link is not None]
    if linked:
        raise rewrite_link_refusal(linked)


def hard_links(path: Path) -> int:
    """How many names `path` has on this filesystem when it is a REGULAR
    FILE with more than one — a hard link — and 0 otherwise: one name, not
    a regular file, or nothing `lstat` can read (#422).

    THE ONE QUESTION, AND EVERY CALLER ASKS THIS ONE: `check`'s `REFUSAL
    AHEAD` line and `apply`'s refusal before `confirm`, both through
    `hard_linked_rewrites`, and `Rollback.write` at the write itself.
    `lstat`, so a symlink at the path is never followed to the count of
    the file it leads to: it is not a regular file here, and it is #286's,
    refused before this is asked. NTFS fills `st_nlink` as POSIX does,
    which is how the README's own guard (`ReadmeShapeLine`) already reads
    it on every platform.
    """
    try:
        info = os.lstat(path)
    except (OSError, ValueError):
        return 0
    if not stat.S_ISREG(info.st_mode) or info.st_nlink < 2:
        return 0
    return info.st_nlink


def hard_linked_rewrites(root: Path, rows: list[Row], kind: Kind,
                         taking: list[Addition] = ()
                         ) -> list[tuple[str, int]]:
    """Every file `apply` will rewrite IN PLACE that has another name on
    this filesystem, as `(path, names)`, in the order it writes them (#422).

    What `apply` rewrites is what is asked about: each copy it copies (an
    `upstream-changed` row), `contracts/shape-pin.yaml` and the manifest,
    which every run that writes at all rewrites, and the root's own
    `.gitattributes` when the `--add` files in `taking` would extend its
    line-ending block (#511) — asked of `extend_eol_block` as
    `_extend_the_eol_block` asks it, without writing. `check` passes no
    `taking`: it has no `--add` to know about.

    NOT `README.md`. Its reader already keeps a hard-linked README and says
    so (`README_HARDLINK`), which is the answer for prose this standard does
    not own; refusing the whole re-pin over it would take that answer away.
    Nor a row `apply` keeps, re-pins from its own bytes or drops: nothing
    is written at its path.
    """
    paths = [row.path for row in rows if row.state == UPSTREAM_CHANGED]
    attributes = root / ATTRIBUTES
    if taking and hard_links(attributes):
        try:
            before = attributes.read_bytes()
        except OSError:
            before = None
        after = (extend_eol_block(before, [add.path for add in taking])
                 if before is not None else None)
        if after is not None and after != before:
            paths.append(ATTRIBUTES)
    paths += [SHAPE_PIN, kind.manifest]
    linked = []
    for path in dict.fromkeys(paths):
        names = hard_links(root / path)
        if names:
            linked.append((path, names))
    return linked


def hard_link_refusal(root: Path, linked: list[tuple[str, int]],
                      arrived: bool = False) -> Refusal:
    """`update-rewrite-hardlink`: a file `apply` rewrites in place has
    another name on this filesystem (#422). `linked` is `[(path, names)]`,
    `names` being `hard_links`' count for `path`.

    `update-rewrite-symlink`'s twin, for a second NAME rather than a link,
    and raised the same two ways: before `confirm`, by
    `_refuse_hard_linked_rewrites`, for every such file at once; and, with
    `arrived`, by `Rollback.write` for a name that arrived while `confirm`
    waited. One path is one line, several are a list, as there.

    THE REMEDY BREAKS THE LINK FROM THIS SIDE. A copy of the file put in
    its place — the same bytes, as a new file — leaves the other name
    holding its own, and git sees no change at the path, so there is
    nothing to commit before the same command is run again. Each line is
    quoted for a POSIX shell, as `_by_hand`'s are, and `cp -p` keeps the
    mode, so a validator that was executable stays so.
    """
    many = len(linked) > 1
    sentences = (["It had no other name when this run looked: one arrived "
                  "while `apply` ran, after this run had decided what to "
                  "write."] if arrived else [])
    sentences.append(
        "A rewrite in place changes the bytes under every name they have, "
        "so it would change "
        + ("those other files" if many else "that other file")
        + " too — outside this root, or in a snapshot of it — which no "
        "`check` showed, no pin covers and git does not record. This "
        "command never writes through a hard link")
    if many:
        detail = ("`apply` would rewrite these files in place, but each has "
                  "another name on this filesystem:\n"
                  + "\n".join(f"    {path}: {names} names"
                              for path, names in linked)
                  + "".join(f"\n  {sentence}" for sentence in sentences))
    else:
        path, names = linked[0]
        detail = " ".join([f"`apply` would rewrite {path} in place, but it "
                           f"has {names} names on this filesystem.",
                           *sentences])
    return Refusal(
        "update-rewrite-hardlink", detail,
        "Remediation: replace " + ("each file" if many else "the file")
        + " with a copy of itself — the same bytes as a new file at the "
        "same path, so the other name keeps its own — then run this "
        "command again. git sees no change there, so there is nothing to "
        "commit:" + "".join(f"\n    {_copy_over_itself(root / path)}"
                            for path, _ in linked))


def _copy_over_itself(path: Path) -> str:
    """The POSIX line that puts a copy of `path` in its place: the same
    bytes as a new file, so a second name keeps its own (#422). `cp -p`
    keeps the mode, so a validator that was executable stays so; the
    copy is moved over the name, never the name written through."""
    here = str(path)
    copy = f"{here}.update-shape-copy"
    return (shlex.join(["cp", "-p", "--", here, copy]) + " && "
            + shlex.join(["mv", "-f", "--", copy, here]))


def _refuse_hard_linked_rewrites(root: Path, rows: list[Row], kind: Kind,
                                 taking: list[Addition]) -> None:
    """`update-rewrite-hardlink` for every file this run will rewrite that
    has another name, before `confirm` and before any write (#422).

    ASKED RIGHT AFTER `update-rewrite-symlink`'s copies, and before
    `update-conflict` and `update-local-drift`: like a link, a second name
    is no merge and no local edit, so neither remedy is its answer.
    """
    linked = hard_linked_rewrites(root, rows, kind, taking)
    if linked:
        raise hard_link_refusal(root, linked)


def _say_hard_links_ahead(root: Path, rows: list[Row]) -> None:
    """`check`'s `REFUSAL AHEAD` line for the files `apply` would refuse to
    rewrite because each has another name (#422): the copies it would
    copy, the pin and the manifest. The manifest is the one `root_kind`
    reads from the tree, as `prepare` read it.

    A LINE, NEVER A ROW STATE. A hard-linked copy holds the right bytes, so
    it is not drift, and a state of its own — or `copy-is-link`'s — would
    have the doctor's `shape currency` row call the project DRIFTED over
    nothing wrong in its tree. Every row keeps its verdict, and the doctor,
    which reads the rows, reads what it always read.
    """
    linked = hard_linked_rewrites(root, rows, root_kind(root))
    if linked:
        print("REFUSAL AHEAD: `apply` will refuse to rewrite these in place "
              "while each has another name on this filesystem (a hard "
              "link; replace it with a copy of itself) — "
              + ", ".join(f"{path} ({names} names)"
                          for path, names in linked))


def _refuse_conflicts(rows: list[Row], accepted: set) -> None:
    """The `update-conflict` refusal, split out of `cmd_apply` for #133.

    ITS REMEDIATION IS `conflict_remediation`'s, per kind of row (#502): a
    `copy-missing` row was told to re-run with `--accept-local`, which this
    function never honours for it, so the re-run printed the same refusal.

    `both` ALONE has an accepted exit: `--accept-local <path>` on it means the
    human already did the merge this refusal asks for, so that row is excluded
    here and handled with LOCALLY_MODIFIED further down — never copied over,
    and re-pinned from what is on disk. The other three conflict states
    (upstream-removed, unmapped, copy-missing) have no such exit: there is no
    local edit to trust a word about, so `--accept-local` naming one of those
    is simply not among the paths this can ever exclude. The fifth,
    `copy-is-link`, never reaches here: `_refuse_linked_copies` refuses it
    first, under its own name.
    """
    conflicts = [row for row in rows
                 if row.is_conflict
                 and not (row.state == BOTH and row.path in accepted)]
    if conflicts:
        raise Refusal(
            "update-conflict",
            "these files changed on BOTH sides, or cannot be compared, and "
            "a merge is a human's judgement rather than a byte copy:\n"
            + "\n".join(f"    {row.path}: {row.detail or row.state}"
                        for row in conflicts),
            conflict_remediation(conflicts))


#: What `update-conflict` tells a row it can name a merge for: `both`, and
#: the two states that cannot be compared. The words it always printed, so a
#: refusal naming no `copy-missing` row reads exactly as it did.
MERGE_BY_HAND = (
    "merge each one by hand (the upstream bytes are `git show "
    "<target>:<source path>` in a shape clone), commit it, then re-run this "
    "with --accept-local on that path so the row is recomputed from what "
    "you merged.")


def conflict_remediation(conflicts: list[Row]) -> str:
    """`update-conflict`'s remediation, a sentence per kind of row it names
    (#502).

    A `copy-missing` ROW HAS AN EXIT OF ITS OWN, AND IT IS NOT
    `--accept-local`. The one remediation this refusal had told every row to
    merge by hand and re-run with that flag, which `_refuse_conflicts`
    honours on a `both` row alone, so for a pinned copy the root no longer
    holds the re-run printed the same refusal. Such a copy has no bytes for
    the flag to keep, and this command never records the deletion of a copy
    the project still needs -- the only rows it drops are merged-away
    copies', below -- so the copy goes back from the project's own history.
    WHERE IN THAT HISTORY DEPENDS ON WHETHER THE DELETION WAS COMMITTED
    (review of PR #512): an `rm` or `git rm` not yet committed leaves the
    copy in HEAD, and `git checkout HEAD -- <path>` puts it back, as the
    doctor's own line for a lost `repo_shape.py` does; a committed one is in
    the parent of the commit that removed it, which `git log -1 -- <path>`
    names. Naming the parent alone sent the common case -- an `rm`, then
    `apply` -- to a removing commit that does not exist, and that `git log`
    names the commit that ADDED the copy instead. A `shape/` copy merged
    into the file it collided with does not reach here while that file is
    at the root: `classify` calls it `merged-away`, and `apply` drops its
    row. The sentence says so, because a person who removed the copy
    without the merge reads it here.

    The other three states keep `MERGE_BY_HAND`, after it where a
    `copy-missing` row is named too.
    """
    missing = [row.path for row in conflicts if row.state == COPY_MISSING]
    if not missing:
        return f"Remediation: {MERGE_BY_HAND}"
    verb = "is" if len(missing) == 1 else "are"
    said = (f"Remediation: {', '.join(missing)} {verb} pinned and gone from "
            "the root, so --accept-local has no bytes to keep, and this "
            "command never records the deletion of a copy the project "
            "still needs. Put each copy back from this project's own "
            "history: a deletion not yet committed comes back with "
            "`git checkout HEAD -- <path>` in the project, and a committed "
            "one from the parent of the commit that removed it, which "
            "`git log -1 -- <path>` names. Then run this again. A `shape/` "
            "copy merged into the file it collided with is not refused: "
            "with that file at the root, `check` reports it merged-away and "
            "`apply` drops its row.")
    if len(missing) < len(conflicts):
        said += f" For the others, {MERGE_BY_HAND}"
    return said


def _refuse_local_drift(rows: list[Row], accepted: set) -> None:
    """The `update-local-drift` refusal, split out of `cmd_apply` for #133:
    a file the project edited since the pin, which nobody has said to accept.
    """
    unaccepted = [row for row in rows
                  if row.state == LOCALLY_MODIFIED and row.path not in accepted]
    if unaccepted:
        raise Refusal(
            "update-local-drift",
            "these files were edited in this project since the pin:\n"
            + "\n".join(f"    {row.path}" for row in unaccepted)
            + "\n  Re-pinning them from the root's own bytes would make "
              "the drift `validate-pins.py` reports today invisible, "
              "which is the fork recorded as the standard.",
            "Remediation: revert each edit, or carry it upstream, or — "
            "having decided the project keeps it — re-run with "
            + " ".join(f"--accept-local {row.path}" for row in unaccepted))


def _note_untaken_additions(additions: list[Addition],
                            taking: list[Addition]) -> None:
    """One `note` line per `upstream-added` path `--add` did not name. Split
    out of `cmd_apply` for #133.

    Printed before the nothing-to-do exit and before any refusal, because it
    is the report rather than the act: a run that then refuses has still told
    the human which files the standard has gained and what to pass to take
    one. An addition the root already HAS a file at is silent here for the
    reason `Addition` gives, and one under a file the root keeps says what
    is in the way rather than name an `--add` that is refused (#285).
    """
    for add in additions:
        if not add.present and add not in taking:
            take = (f"pass --add {add.path}" if add.blocked is None else
                    f"{add.blocked} in this root is not a directory, so "
                    f"--add refuses it until {add.blocked} is moved")
            dead = f" ({add.left_dead})" if add.left_dead else ""
            print(f"  note     {add.path} is new upstream; not added; "
                  f"{take}{dead}")


def _nothing_to_do(rows: list[Row], pinned: str, target: str,
                   taking: list[Addition]) -> bool:
    """Is there no write to make at all? Split out of `cmd_apply` for #133.

    All three have to hold: no copied file differs, the pin already names the
    target, and `--add` named nothing. A pin that names a different commit is
    a write even when every file matches, which is the re-pin `check` reports
    as "`apply` would move the pin alone".
    """
    return (all(row.state == UNCHANGED for row in rows)
            and pinned == target and not taking)


def _write_copies(root: Path, rows: list[Row], taking: list[Addition],
                  ledger: Rollback) -> list[Row]:
    """Write every byte this run copies, and say what happened to each row.
    Split out of `cmd_apply` for #133. Returns the rows actually re-copied.

    THE ORDER IS THE REPORT'S ORDER: the copies, then what was kept and why,
    then the additions. `rows` GROWS here — an `--add` row is appended rather
    than inserted, so the pin keeps the order the scaffold wrote it in and the
    new row reads as what it is: a file this project took later, by name.
    """
    copied = [row for row in rows if row.state == UPSTREAM_CHANGED]
    for row in copied:
        ledger.write(root / row.path, row.target_bytes or b"")
        print(f"  copied   {row.path}")
    for row in rows:
        if row.state in (LOCALLY_MODIFIED, BOTH):
            print(f"  kept     {row.path} (local bytes; row recomputed "
                  "from them because --accept-local named it)")
        elif row.state == ALREADY_AT_TARGET:
            print(f"  kept     {row.path} (already the target's bytes; "
                  "the row was stale)")
        elif row.state == MERGED_AWAY:
            # NOTHING IS WRITTEN AT ITS PATH (#502): `_repin` leaves its row
            # out of the pin, and that is the whole of what dropping it is.
            original = row.path[len(COLLISION_DIR) + 1:]
            print(f"  dropped  {row.path} (merged into {original} and "
                  "removed; its pin row goes, and nothing is copied)")
    for add in taking:
        ledger.write_added(root / add.path, add.target_bytes or b"",
                           add.executable)
        rows.append(add)
        print(f"  added    {add.path} (new upstream file, copied from "
              f"{add.source}; its row is appended to the pin)")
    return copied


def _extend_the_eol_block(root: Path, taking: list[Addition],
                          ledger: Rollback) -> list[str]:
    """Name each `--add` file in the line-ending block of the root's own
    `.gitattributes`; the paths this wrote, for the commit (#471).

    An ADOPTED root whose source kept its own `.gitattributes` carries the
    shape's `* text=auto eol=lf` under `shape/`, where it governs that
    directory alone, and a block that `adopt-project.py` appended to its own
    file names each pinned copy outside it, so a Windows checkout keeps their
    bytes. An `--add` file is written at its own path, never under `shape/`,
    so it is one more such copy, and without its line a Windows clone reports
    shape-copy-drift on it. A root with no block -- a scaffolded one, whose
    `.gitattributes` IS the shape's, or one adopted before #471 -- is left
    alone, as is a `.gitattributes` that is a symlink: this tool never
    writes through one. Through the ledger, so a refusal after it puts the
    file back.
    """
    path = root / ATTRIBUTES
    if not taking or symlink_on_the_way(root, ATTRIBUTES) is not None \
            or not path.is_file():
        return []
    before = path.read_bytes()
    after = extend_eol_block(before, [add.path for add in taking])
    if after is None or after == before:
        return []
    ledger.write(path, after)
    print(f"  extended {ATTRIBUTES}' line-ending block with the --add "
          "files, so every checkout keeps their bytes")
    return [ATTRIBUTES]


def _repin(root: Path, kind: Kind, ledger: Rollback, rows: list[Row],
           pinned: str, target: str, target_tree: str) -> None:
    """Rewrite `contracts/shape-pin.yaml` and the kind's manifest onto the
    target, through the ledger so both roll back. Split out of `cmd_apply`
    for #133; the two rewriters are where the refusals about an unrecognised
    pin or manifest live.

    A MERGED-AWAY ROW IS LEFT OUT OF THE PIN (#502), in this same rewrite and
    behind the same yes: the row names a copy the project merged into the
    file it collided with and removed, and Brett Heap ruled that its pin row
    goes. Every other row is written as `classify` left it.
    """
    pin_path = root / "contracts" / "shape-pin.yaml"
    manifest_path = root / kind.manifest
    kept = [row for row in rows if row.state != MERGED_AWAY]
    ledger.write(pin_path, rewrite_shape_pin(
        pin_path.read_text(encoding="utf-8"), target, target_tree, kept
    ).encode("utf-8"))
    ledger.write(manifest_path, rewrite_manifest(
        manifest_path.read_text(encoding="utf-8"), target, target_tree, kind
    ).encode("utf-8"))
    print(f"  re-pinned contracts/shape-pin.yaml and {kind.manifest} "
          f"{pinned[:12]} -> {target[:12]}")


def _read_readme(root: Path, upstream: Upstream,
                 target: str) -> ReadmeShapeLine:
    """Classify the README BEFORE the first copied byte lands (#158).

    `.gitattributes` IS A PINNED COPY, and `readme_is_committed` asks git two
    questions about `README.md` — `git status` and `git hash-object` — that
    git answers through the attributes in the WORKING TREE. Read after
    `_write_copies`, an upstream edit to `* text=auto eol=lf` would therefore
    decide this root's README's fate: a CRLF working tree that hashes to its
    own LF blob under the pinned attributes hashes to something else under a
    new `README.md -text`, reads `uncommitted`, and keeps its stale line —
    `apply` declining to move it for a reason that has nothing to do with the
    README, and one no `check` run before the copies landed could have
    predicted (Copilot, PR #152).

    Root, repository and target are all known before the first copy, so the
    READING is taken here. The WRITE stays where the ledger wants it, in
    `_rewrite_readme` below.
    """
    return ReadmeShapeLine(root, upstream.repository, target)


def _rewrite_readme(readme: ReadmeShapeLine, ledger: Rollback) -> None:
    """The README's `Shape:` line phase of `apply`, added for #148.

    AFTER THE PIN MOVE AND BEFORE THE VALIDATORS, which is where it belongs
    twice over: the line claims the commit `_repin` has just written, and the
    write goes through the same ledger, so `_refuse_red_validators` rolling
    the copies back restores this too. Only the READING runs earlier, in
    `_read_readme` — the ledger's order is what it was.

    Says what happened either way. A README with no such line, two of them,
    or one naming another repository is LEFT ALONE — and the reader is told
    which of those it was, because silence there reads as "done" and this
    is the one file `apply` touches that nobody pinned.

    A FAILED WRITE IS A REFUSAL, NEVER A TRACEBACK. `_classify` turns every
    way of failing to READ this file into one of those readings, so what is
    left here is the write itself — a disk that filled, a permission that
    changed under the run — and this phase runs AFTER the copies and the pin.
    An `OSError` escaping would leave that tree behind, because `cmd_apply`
    rolls back on `Refusal` and `CommandFailed` and on nothing else (Copilot,
    PR #152). Named as a refusal, the arm that already exists puts every byte
    back — and says so itself, listing what it put back under this detail
    (`_rolled_back`, #202), so the detail does not claim it a second time.
    """
    try:
        readme.rewrite(ledger)
    except OSError as exc:
        raise Refusal(
            "update-readme-unwritable",
            f"the copies and the pin were written, but {README}'s Shape: "
            f"line could not be: {exc.strerror or exc}.",
            f"Remediation: make {README} writable and run the same command "
            "again. The line is prose in a file this standard does not own, "
            "so a root that would rather keep it as it is can also take the "
            "line out and `apply` will say `absent` and move on.") from exc
    print(readme.said)


def _refuse_red_validators(root: Path, kind: Kind) -> None:
    """Run the root's OWN validators over what was just written, and refuse
    if either goes red. Split out of `cmd_apply` for #133; the rollback is
    the caller's `except Refusal` arm, which is why this only has to raise.
    That arm also SAYS what it put back, under this detail (`_rolled_back`,
    #202), which is why the detail no longer claims the rollback itself: one
    refusal made the same promise twice, in two spellings.
    """
    print(f"\nthe {kind.name}'s own validators")
    failed = [name for name in kind.validators
              if run_validator(root, name) != 0]
    if failed:
        raise Refusal(
            "update-validators-red",
            "after the rewrite, " + " and ".join(failed) + " refused.",
            "Remediation: read the finding above. A tool that left a "
            "project red would have moved the cost from this command to "
            "somebody else's pull request.")


def _land(root: Path, args, paths: list[str], added: list[str], target: str,
          upstream: Upstream, kind: Kind, count: int,
          ledger: Rollback, dropped: list[str] = ()) -> None:
    """The three optional acts after a clean rewrite — commit, push, open a
    pull request — each done only because a flag asked for it. Split out of
    `cmd_apply` for #133. `dropped` names the merged-away rows the re-pin
    left out (#502), for the commit message.

    Nested the way the flags are: `--push` and `--pr` have nothing to act on
    without `--branch`, which `main` refuses before this is ever reached.
    The commit goes through `ledger` and closes it (#202), so a failure up
    to and including the commit is rolled back and one after it is not.

    THE COMMIT IS WHERE ROLLING BACK STOPS (#204). A push or a pull request
    that fails after it is `landing_failed`'s: named by its own step, the
    commit kept, and a NEXT line that finishes the job. The `gh pr create`
    that line ends with is built HERE, BEFORE the commit, so a root with no
    repository for `--pr` to open against is refused while there is still
    nothing committed to keep, and the failure path reads no file at all.
    """
    if not args.branch:
        return
    create = (pull_request_line(root, args, target, upstream, kind)
              if args.push or args.pr else [])
    commit_on_branch(root, args.branch, paths, target, upstream,
                     count, kind, added, args.trailer, ledger=ledger,
                     dropped=dropped)
    print(f"\n  committed on {args.branch}: " + ", ".join(paths))
    if args.push:
        push_branch(root, args, create)
    if args.pr:
        open_pull_request(root, args, create)


def cmd_apply(args) -> int:
    # `pin` (the raw mapping `read_pin` returned) is not read again below:
    # `pinned` is the commit string this command compares and writes back.
    root, _, rows, additions, upstream, pinned, target, kind = prepare(args)
    ledger = Rollback(root)
    try:
        accepted = {str(path) for path in (args.accept_local or [])}
        _refuse_unknown_accept_local(rows, accepted)
        taking = resolve_additions(rows, additions,
                                   [str(path) for path in (args.add or [])],
                                   target)
        _note_untaken_additions(additions, taking)
        nothing = _nothing_to_do(rows, pinned, target, taking)
        rerun = nothing and _awaits_its_pull_request(root, args, kind)
        if args.branch:
            # BEFORE THE FIRST WRITE, AND BEFORE "NOTHING TO DO" (#436): that
            # answer is read from the working tree too, and over a re-pin
            # left uncommitted it made no branch where one was asked for.
            _refuse_what_head_does_not_commit(root, rows, kind, args.branch,
                                              pinned, target, rerun)
        if rerun:
            return _finish_landing(root, args, upstream, target, kind)
        if nothing:
            print(f"nothing to do: every copied file matches "
                  f"{upstream.repository} @ {target[:12]}, which the pin "
                  "already names")
            return 0
        _refuse_linked_copies(rows)
        _refuse_hard_linked_rewrites(root, rows, kind, taking)
        _refuse_conflicts(rows, accepted)
        _refuse_local_drift(rows, accepted)
        if args.branch:
            _refuse_writes_through_a_link(root, rows, kind, args.branch)
        confirm(args, rows, taking, target)
        target_tree = upstream.tree_sha256(target)
        # READ BEFORE THE COPIES, REWRITTEN AFTER THE PIN. `.gitattributes`
        # is a pinned copy and the README's commit-state question is answered
        # through it, so a classification taken after `_write_copies` would
        # be made under the standard's NEW attributes (#158).
        readme = _read_readme(root, upstream, target)
        with ledger.writing("writing the copies and the --add files"):
            copied = _write_copies(root, rows, taking, ledger)
        with ledger.writing(f"extending {ATTRIBUTES}' line-ending block"):
            attributes = _extend_the_eol_block(root, taking, ledger)
        with ledger.writing("re-pinning contracts/shape-pin.yaml and "
                            f"{kind.manifest}"):
            _repin(root, kind, ledger, rows, pinned, target, target_tree)
        _rewrite_readme(readme, ledger)
        _refuse_red_validators(root, kind)
        added = [add.path for add in taking]
        paths = sorted({row.path for row in copied} | set(added)
                       | {SHAPE_PIN, kind.manifest} | set(attributes)
                       | ({README} if readme.rewritten else set()))
        # A DROPPED ROW IS NOT A PINNED PATH ANY MORE (#502): the pin this
        # run wrote has no row for it, so it is neither said in the commit
        # as re-copied nor asked about as a copy the commit leaves out.
        dropped = [row.path for row in rows if row.state == MERGED_AWAY]
        _land(root, args, paths, added, target, upstream, kind, len(copied),
              ledger, dropped)
        print()
        next_line(root, args, paths, target, added, kind,
                  pinned_paths=[row.path for row in rows
                                if row.state != MERGED_AWAY])
        return 0
    except (Refusal, CommandFailed) as exc:
        return _rolled_back(exc, ledger)
    finally:
        upstream.close()


def _rolled_back(exc: Exception, ledger: Rollback) -> int:
    """`apply`'s one failure arm: undo what `ledger` holds, then refuse,
    saying which step failed and what was put back (#202).

    A REFUSAL keeps its own id and remediation, and gains the list of what
    was put back under its detail — every refusal raised after the first
    write, not only the validators' — so nobody reads `copied` and
    `re-pinned` above it and believes the copies are still there. A failed
    GIT COMMAND is named by the step `ledger` was in (creating the branch,
    staging the additions, committing) rather than always "committing".

    NOTHING TO PUT BACK keeps the answer each exit always gave: a refusal
    before the first write is re-raised as it was. A push or a pull request
    that fails after the commit never reaches here: `landing_failed` names
    it and raises `LandingIncomplete`, which is neither of this arm's two
    classes, so the commit `ledger.land()` closed on stays (#204).
    """
    undone = ledger.undo()
    if undone is not None:
        # The `copied` / `re-pinned` lines first, then the refusal: a log that
        # merged the two streams would otherwise show the rollback before the
        # writes it rolled back.
        sys.stdout.flush()
    if isinstance(exc, Refusal):
        if undone is None:
            raise exc
        raise Refusal(exc.code, f"{exc.detail}\n{undone}",
                      exc.remediation) from exc
    if undone is None:
        print(exc.loudly("committing the re-synced shape"), file=sys.stderr)
        return 2
    print(f"{exc.loudly(ledger.step)}\n{undone}", file=sys.stderr)
    return 2


class LandingIncomplete(Exception):
    """The re-pin is COMMITTED on its branch and a step after the commit
    failed (#204). Already reported, NEXT line included, by `landing_failed`.

    ITS OWN CLASS, NEITHER A `Refusal` NOR A `CommandFailed`, because
    `cmd_apply` has an arm for each and both are wrong here: the `Refusal`
    arm rolls the working tree back under a commit that already holds those
    bytes, and the `CommandFailed` arm names the commit as the step that
    failed and prints no NEXT line, which is how a `gh pr create` that failed
    after the commit and the push both landed came out as "REFUSED committing
    the re-synced shape". `main` turns it into exit 2 and says nothing more.
    """


def landing_failed(root: Path, args, exc: CommandFailed, act: str,
                   create: list[str]) -> LandingIncomplete:
    """Report a step that failed AFTER the commit: the step by name, what
    stands, and the one command that finishes the job.

    WHAT STANDS IS READ FROM GIT, not from the flags: `push -u` moves
    `refs/remotes/origin/<branch>`, so "origin has it" is that ref agreeing
    with HEAD. Git is asked which remote-tracking refs point at HEAD and the
    branch is looked for in its answer, so the name is never a `git`
    argument here. A NEXT line that cannot vouch for the push carries it in
    front of the `gh pr create` (a push origin already has is a no-op). The
    `gh pr create` is `create` itself, quoted to be pasted: under `--pr` the
    very command `--pr` runs, title and body included, so the pull request
    opened by hand is the one the tool would have opened.

    A RE-RUN IS PROMISED ONLY UNDER `--pr`, because only then does one finish
    the job: `_awaits_its_pull_request` recognises it. A failed `--push`
    without `--pr` is finished by the NEXT line alone. The re-run named
    carries `--push` whenever origin is not known to have the branch: a
    re-run pushes only when asked to, and `gh` opens no pull request from a
    branch origin lacks.

    STDOUT IS FLUSHED FIRST, so a combined log reads in the order things
    happened: the commit and the push above the refusal, not below it.
    """
    branch = args.branch
    head = (_git_answer(root, ["rev-parse", "HEAD"]) or "").strip()
    at_head = (_git_answer(root, ["for-each-ref", "--format=%(refname)",
                                  "--points-at", "HEAD", "refs/remotes/origin/"])
               or "").splitlines()
    pushed = bool(head) and f"refs/remotes/origin/{branch}" in at_head
    sys.stdout.flush()
    print(exc.loudly(act), file=sys.stderr)
    left = ("its pull request: the NEXT line opens it" if pushed
            else "the push and the pull request: the NEXT line makes both")
    rerun = "apply --pr" if pushed else "apply --push --pr"
    again = (f", and so does `{rerun}` run again on {branch} once the "
             "step above can succeed, because with nothing left to write it "
             "opens the pull request that is still missing" if args.pr
             else "")
    print(f"{branch} carries the re-pin at {head[:12] or 'HEAD'}"
          + (", and origin has it" if pushed
             else ", and origin does not have it yet")
          + f": that commit stands and nothing was rolled back. What is left "
          f"is {left}{again}.", file=sys.stderr)
    sys.stderr.flush()
    push = ("" if pushed else shlex.join(["git", "-C", str(root), "push", "-u",
                                          "--", "origin", branch]) + " && ")
    print()
    print(f"NEXT  {push}{shlex.join(create)}")
    return LandingIncomplete(act)


def _landing_run(command: list[str], root: Path) -> str:
    """`run`, for the steps after the commit (#204), with a program that
    cannot be started reported as the failed step it is. `gh` not installed,
    or not on PATH, is the likeliest way `gh` fails on a fresh machine, and
    `subprocess` raises `OSError` for it rather than returning an exit code,
    so it escaped every arm as a traceback after the commit and the push had
    landed. It becomes a `CommandFailed` with the exit 127 a shell gives a
    command it cannot find, which `landing_failed` then names, NEXT line
    included."""
    try:
        return run(command, cwd=root)
    except OSError as exc:
        raise CommandFailed(
            command, root, 127,
            f"`{command[0]}` could not be started "
            f"({exc.strerror or exc}): is it installed and on PATH?") from exc


def push_branch(root: Path, args, create: list[str]) -> None:
    """`git push -u -- origin <branch>`, for the first run and for the re-run
    alike, `--` ending git's options before the two positionals. A refusal
    from origin is `landing_failed`'s (#204): the commit it was pushing
    stands, so the step is named and nothing is rolled back."""
    try:
        _landing_run(["git", "push", "-q", "-u", "--", "origin", args.branch],
                     root)
    except CommandFailed as exc:
        raise landing_failed(root, args, exc, f"pushing {args.branch}",
                             create) from exc
    print(f"  pushed {args.branch} to origin")


def _awaits_its_pull_request(root: Path, args, kind: Kind) -> bool:
    """Is this no-write run a RE-RUN on the branch whose pull request `--pr`
    still owes (#204)? Without this, the run that follows a failed `gh pr
    create` found the pin already at the target, said "nothing to do" and
    exited 0, so the tool never opened the pull request it was asked for.

    `--pr` was passed; `--branch` is the branch checked out, which is where
    the earlier run left the checkout; it is not the tracking branch, which
    has no pull request to open onto itself; and the branch PROPOSES A PIN —
    its `contracts/shape-pin.yaml` is not the one `origin/<tracking>` holds,
    as far as this clone has seen. A branch cut from a tracking branch that
    already carries the re-pin proposes nothing, however many other commits
    it holds, and stays "nothing to do". A clone that has never seen
    `origin/<tracking>` cannot tell, and asks `gh`, which answers for itself.

    THIS READS HEAD, AND "NOTHING TO DO" READ THE WORKING TREE (#333). What
    it recognises is finished only once `_refuse_what_head_does_not_commit`
    has found the two to be the same bytes wherever either was read.
    """
    if not (args.pr and args.branch) or current_branch(root) != args.branch:
        return False
    base = tracking_branch_of(load_yaml(root / kind.manifest))
    if args.branch == base:
        return False
    pin = SHAPE_PIN
    proposed = _git_answer(root, ["rev-parse", "--verify", "--quiet",
                                  f"HEAD:{pin}"])
    landed = _git_answer(root, ["rev-parse", "--verify", "--quiet",
                                f"refs/remotes/origin/{base}:{pin}"])
    return proposed is not None and proposed != landed


def _refuse_what_head_does_not_commit(root: Path, rows: list[Row],
                                      kind: Kind, branch: str, pinned: str,
                                      target: str, rerun: bool) -> None:
    """Every `--branch` run lands what HEAD commits, so the working tree
    must hold HEAD's bytes wherever this run read it, or the run is refused
    by name before its first write (#333, #436).

    TWO SOURCES, ONE ANSWER EXPECTED. Everything this run decides is read
    from the working tree — `read_pin` and `classify`: what to copy, what to
    re-pin, whether there is anything to do at all — and the pull request's
    base and repository are read from the manifest there too. What it lands
    is HEAD's: the re-run `_awaits_its_pull_request` recognises (`rerun`)
    pushes HEAD as it stands, and any other `--branch` run commits HEAD plus
    only the paths it writes (`commit_on_branch`). Over a tree that IS
    HEAD's that is one answer. Over an in-place `apply` left uncommitted it
    was two, each case measured:

      * the re-run (#333) pushed B under a pull request titled C;
      * a first run (#436) committed D's re-pin without C's copies, exit 0
        with the commit's own `validate-pins.py` red; or re-pinned back to
        what HEAD held and died on git's "nothing to commit"; or found
        "nothing to do" in a re-pin HEAD never committed, and made no branch.

    So the pin, the manifest and every pinned copy are compared with HEAD
    BY BYTES (`_not_what_head_commits`) and a difference is refused, in the
    words for the run it is: `update-rerun-uncommitted` for the re-run,
    `update-branch-uncommitted` for a run that would commit. The commit's
    pathspec is NOT widened to take the difference in: what a person left
    uncommitted is theirs to commit or put back. The index is not asked: no
    decision here reads a staged entry. Nor is any other path, a README or
    an untracked note, which no decision reads. Nothing is written yet, so
    there is nothing to roll back.
    """
    pin = "contracts/shape-pin.yaml"
    differ = _not_what_head_commits(
        root, list(dict.fromkeys([pin, kind.manifest,
                                  *(row.path for row in rows)])))
    if not differ:
        return
    head = (_git_answer(root, ["rev-parse", "HEAD"]) or "").strip()
    committed = _committed_pin(root, pin)
    if rerun:
        raise _rerun_uncommitted(branch, head, target, differ, pinned,
                                 committed)
    raise _branch_uncommitted(branch, head, differ, pinned, committed)


def _rerun_uncommitted(branch: str, head: str, target: str,
                       differ: list[str], pinned: str,
                       committed: str) -> Refusal:
    """`update-rerun-uncommitted` (#333): the re-run would push HEAD under a
    pull request named for the working tree."""
    carried = (f"; there the pin names {pinned[:12]} and HEAD's names "
               f"{committed[:12]}, so the pull request would name one commit "
               "and carry another" if committed and committed != pinned
               else "")
    return Refusal(
        "update-rerun-uncommitted",
        f"--pr would finish the landing of {branch} from what HEAD "
        f"({head[:12]}) commits, under a pull request naming {target[:12]}, "
        "but the working tree does not hold what HEAD commits at "
        + ", ".join(differ) + ". \"Nothing to write\" was judged from the "
        "working tree, and the pull request's base and repository are read "
        f"from it too{carried}.",
        f"Remediation: a re-run finishes only what {branch} already "
        "commits. Commit those changes on it if they are the re-pin to "
        "propose, or put them back to HEAD's bytes if they are not, then "
        "run the same command again. Nothing was written or pushed, and gh "
        "was not asked.")


def _branch_uncommitted(branch: str, head: str, differ: list[str],
                        pinned: str, committed: str) -> Refusal:
    """`update-branch-uncommitted` (#436): a `--branch` run that would
    commit HEAD plus its own paths over a working tree it judged instead.

    The remedy is the one #333's gives, for a run that has not committed
    yet: commit those changes, or put them back. Putting back is the exit
    for an earlier `apply` left uncommitted, which this command then makes
    again from HEAD; committing is the exit for changes the re-pin is to
    carry, and never onto the tracking branch, which `commit_on_branch`
    refuses for this tool's own commit too.
    """
    moved = (f"; there the pin names {pinned[:12]} and HEAD's names "
             f"{committed[:12]}" if committed and committed != pinned
             else "")
    return Refusal(
        "update-branch-uncommitted",
        f"--branch {branch} would commit what HEAD "
        f"({head[:12] or 'no commit'}) commits plus only the paths this run "
        "writes, but the working tree does not hold what HEAD commits at "
        + ", ".join(differ) + ". What to copy, what to re-pin and whether "
        "there is anything to do at all are judged from the working "
        f"tree{moved}, so the commit would not hold what this run judged.",
        "Remediation: commit those changes first if this re-pin is to carry "
        "them — on a branch, since the tracking branch takes no direct "
        "commit — or put them back to HEAD's bytes if it is not, as for an "
        "earlier `apply` left uncommitted, which this command then makes "
        "again from HEAD. Then run the same command again. Nothing was "
        "written, committed or pushed.")


def _refuse_writes_through_a_link(root: Path, rows: list[Row], kind: Kind,
                                  branch: str) -> None:
    """`update-rewrite-symlink` under `--branch` (#436, codex review of
    1af060e): this run would write, or re-pin from, a file it reaches
    THROUGH a symlink, so the commit would not hold what it judged.

    `_not_what_head_commits` compares a link's own text with HEAD, because
    that is what git commits there. But `classify` and `file_sha256` read
    the bytes the link leads to, and `Rollback.write` writes through it. So
    a copy upstream rewrote, a local edit `--accept-local` took at the
    link's end, and the pin and the manifest themselves land at the far end
    of a link, while the commit holds HEAD's link unchanged: exit 0 over a
    commit whose own `validate-pins.py` reports `shape-copy-drift`, or the
    pin and the manifest disagreeing, in a clean checkout (measured on main
    and on 1af060e alike). Refused here, before the first write.

    ASKED AFTER `update-conflict` AND `update-local-drift`, so every row
    still not UNCHANGED is one this run writes or re-pins, and those
    refusals keep main's answers. A linked copy the run leaves UNCHANGED is
    not refused: the pin keeps HEAD's row for it, so the commit claims
    nothing new about it. The name is the rewrite twin of `--add`'s
    `update-add-symlink` (#239), for a file this run overwrites rather than
    creates. Without `--branch` nothing is committed, and a write through
    a link is made as on main (#286). A `merged-away` row is not asked
    about either (#502): its row is dropped, and nothing is read or written
    at its path.
    """
    pin = "contracts/shape-pin.yaml"
    paths = [pin, kind.manifest] + [row.path for row in rows
                                    if row.state not in (UNCHANGED,
                                                         MERGED_AWAY)]
    linked = []
    for path in paths:
        link = symlink_on_the_way(root, path)
        if link is not None:
            name, points = link
            above = "" if name == path else " above it"
            linked.append(f"    {path}: {name} is a symlink{above}, "
                          f"pointing at {points!r}")
    if not linked:
        return
    raise Refusal(
        "update-rewrite-symlink",
        f"--branch {branch} would commit HEAD plus the paths this run "
        "writes, but this run would write, or re-pin from, bytes it reaches "
        "THROUGH a symlink, and git commits the link, never what it leads "
        "to:\n" + "\n".join(linked)
        + "\n  The commit would hold each link as HEAD does, under a pin "
          "recording bytes it does not carry, so its own validate-pins.py "
          "would refuse it in a clean checkout.",
        "Remediation: replace each link with what it points at — a plain "
        "file, or directory, at that path, so git holds the bytes there — "
        "commit that, on a branch, since the tracking branch takes no "
        "direct commit, and run the same command again. A root that keeps "
        "a link takes the update by hand, at the link's end. Nothing was "
        "written, committed or pushed.")


def _not_what_head_commits(root: Path, paths: list[str]) -> list[str]:
    """Those of `paths` whose bytes on disk are not the blob HEAD commits
    at that path, or that HEAD does not commit at all, in the order given
    (#333). A path git will not hash is one this cannot vouch for, and is
    named with them.

    `git hash-object` on the file, against `HEAD:<path>`: the clean filter
    runs, so a CRLF checkout of an LF blob is HEAD's, and no index flag
    hides an edit — `readme_is_committed`'s second question, asked of each
    path.

    FOUR ANSWERS THAT ARE NOT DIFFERENCES (#436), now that every `--branch`
    run asks rather than only #333's re-run, whose rows were all present
    and none of them links. A path neither the disk nor HEAD holds — a
    pinned copy deleted and committed — is the same on both sides, and is
    `update-conflict`'s to name as missing. Where a symlink stands on
    the path's way (`symlink_on_the_way`, the path itself or a directory
    above it), what git commits is THE LINK, its target as text, never the
    bytes it leads to, which `hash-object` on the path would read: so the
    link's own text is hashed against HEAD's entry for the link. A pinned
    copy kept as a link HEAD commits is then HEAD's, as it is to git; the
    bytes it leads to, which this run reads and may write, are
    `_refuse_writes_through_a_link`'s question. And a directory
    where HEAD commits a directory (`_head_holds_a_directory`) is HEAD's
    too: a pinned copy replaced by a directory, that type change committed,
    has nothing for `hash-object` to read, so it was named a difference
    for good, though no edit is left to commit and no remedy this refusal
    gives changes it. It is not a file, so `classify` calls it
    `copy-missing` and `update-conflict` names it before anything is
    written, as it does for a deletion HEAD commits. Any OTHER pair of
    kinds is a difference: a directory over a file HEAD commits, a file
    over a directory HEAD commits, or a directory where HEAD commits
    nothing, is a type change nobody has committed.

    And a node that is NOT A FILE, A DIRECTORY OR A LINK — a FIFO, a
    socket, a device — is never READ (codex review of 1af060e): `lstat`
    says what it is first. `hash-object` opens what it is given, and a
    FIFO with no writer blocks that open for good, so `apply --branch`
    hung over a pinned copy replaced by one, where main refused. git
    commits none of them, so there is nothing of HEAD's to compare, and
    `classify`, whose `is_file()` says no, already calls it `copy-missing`:
    `update-conflict` names it before anything is written, as on main.
    """
    return [path for path in paths if _differs_from_head(root, path)]


def _differs_from_head(root: Path, path: str) -> bool:
    """`_not_what_head_commits`' question for one path. What stands there
    is `lstat`ed before git is asked to read it, so git is handed a regular
    file or nothing, and never opens what could block."""
    link = symlink_on_the_way(root, path)
    if link is not None:
        name, points = link
        disk = _blob_of(root, os.fsencode(points))
        return not disk or disk != _head_blob(root, name)
    try:
        mode = os.lstat(root / path).st_mode
    except (OSError, ValueError):
        # Nothing on disk: a difference only where HEAD commits something.
        return bool(_head_blob(root, path))
    if stat.S_ISDIR(mode):
        # Nothing here to hash: `hash-object` on a directory fails.
        return not _head_holds_a_directory(root, path)
    if not stat.S_ISREG(mode):
        # A FIFO, a socket or a device: not read, and `classify`'s.
        return False
    disk = (_git_answer(root, ["hash-object", "--", path]) or "").strip()
    return not disk or disk != _head_blob(root, path)


def _head_holds_a_directory(root: Path, path: str) -> bool:
    """Does HEAD commit a directory at `path`: a tree, or a gitlink, which
    git checks out as one (#436)? True for any entry that is not a blob,
    and False where HEAD commits nothing there.

    `cat-file -t` names a tree, and fails for a gitlink, whose commit is
    not an object of this repository — so the answer is "is not a blob",
    never "is a tree". A symlink is a blob whose text is the target.
    """
    entry = _head_blob(root, path)
    return bool(entry) and (_git_answer(
        root, ["cat-file", "-t", entry]) or "").strip() != "blob"


def _head_blob(root: Path, path: str) -> str:
    """The object HEAD commits at `path`, or "" where it commits none."""
    return (_git_answer(root, ["rev-parse", "--verify", "--quiet",
                               f"HEAD:{path}"]) or "").strip()


def _blob_of(root: Path, data: bytes) -> str:
    """The blob id git gives `data`, as BYTES on stdin (no filter runs on
    stdin without `--path`), or "" when git will not say."""
    proc = _git_quietly(["git", "hash-object", "--stdin"], root, data)
    if proc is None or proc.returncode != 0:
        return ""
    return proc.stdout.decode("ascii", "replace").strip()


def _committed_pin(root: Path, pin: str) -> str:
    """The `commit:` HEAD's shape pin names, or "" when that pin does not
    read as a mapping (#333). Said in the refusal, never decided on."""
    try:
        parsed = parse_yaml(_git_answer(root, ["show", f"HEAD:{pin}"]) or "")
    except YamlError:
        return ""
    return (str(parsed.get("commit") or "").lower()
            if isinstance(parsed, dict) else "")


def _pull_requests(answer: str) -> "list[tuple[str, str]] | None":
    """`(STATE, url)` per pull request in `gh pr list --json state,url`'s
    answer, or None when the answer is not that shape."""
    try:
        pulls = json.loads(answer or "[]")
    except ValueError:
        return None
    if not isinstance(pulls, list) or \
            not all(isinstance(pull, dict) for pull in pulls):
        return None
    return [(str(pull.get("state") or "").upper(), str(pull.get("url") or ""))
            for pull in pulls]


def _finish_landing(root: Path, args, upstream: Upstream, target: str,
                    kind: Kind) -> int:
    """The re-run `_awaits_its_pull_request` recognised: nothing to write,
    and the landing the flags asked for finished instead (#204).

    `gh` IS ASKED FIRST, before anything is pushed or opened: a branch that
    already has a pull request — open, merged or closed — gets no second one
    and no push, and the run says which it has (pushing first would put back
    a merged branch its remote had deleted). Only a branch with none is
    pushed again under `--push` (a no-op when origin has it) and handed to
    `open_pull_request` with the same `gh pr create` the first run built.
    Every failure on the way is `landing_failed`'s, named by its own step.
    """
    branch = args.branch
    print(f"nothing to write: every copied file matches {upstream.repository}"
          f" @ {target[:12]}, which the pin on {branch} already names; "
          f"--pr asked for {branch}'s pull request")
    repository, _ = pull_request_target(root, kind)
    create = pull_request_line(root, args, target, upstream, kind)
    listing = ["gh", "pr", "list", "--repo", repository, "--head", branch,
               "--state", "all", "--json", "state,url"]
    asking = f"asking gh for {branch}'s pull request"
    try:
        answer = _landing_run(listing, root)
    except CommandFailed as exc:
        raise landing_failed(root, args, exc, asking, create) from exc
    pulls = _pull_requests(answer)
    if pulls is None:
        raise landing_failed(root, args,
                             CommandFailed(listing, root, 0, answer),
                             asking + " (the answer is not a JSON list)",
                             create)
    opened = [url for state, url in pulls if state == "OPEN"]
    if opened:
        print(f"  pull request {opened[0]} is already open")
    elif pulls:
        state, url = pulls[0]
        print(f"  pull request {url} for {branch} is {state.lower()}; a "
              "re-run opens no second one")
        return 0
    else:
        if args.push:
            push_branch(root, args, create)
        open_pull_request(root, args, create)
    print()
    print("NEXT  the pull request is open; ask a human to review and merge it")
    return 0


def pull_request_target(root: Path, kind: Kind) -> tuple[str, str]:
    """`(repository, base)` the pull request is opened against, out of the
    kind's manifest. Split out of `open_pull_request` (#204) so the command
    is built once, before the commit, and a re-run asks `gh` about the same
    pair."""
    manifest = load_yaml(root / kind.manifest)
    base = tracking_branch_of(manifest)
    repository, missing = pull_request_repository(manifest, kind)
    if not repository:
        raise Refusal("update-pr-no-repository", missing)
    return repository, base


def pull_request_line(root: Path, args, target: str, upstream: Upstream,
                      kind: Kind) -> list[str]:
    """The `gh pr create` that lands `--branch` (#204): under `--pr` the one
    `--pr` runs, title and body included, so the NEXT line a failure prints
    is that same command; without it, the bare form the plain `--branch`
    NEXT line prints (#209): `--repo` the manifest's repository, then
    `--base`/`--head` against this root's own tracking branch.

    WITHOUT `--pr` A MANIFEST NAMING NO REPOSITORY LEAVES `--repo` OFF rather
    than refusing: nothing is opened, so nothing is wrong yet, and the
    `<org>/<Project>` placeholder `next_line` prints would be one literal
    argument in a line quoted to be pasted as an argv."""
    if not args.pr:
        manifest = load_yaml(root / kind.manifest)
        repository, _ = pull_request_repository(manifest, kind)
        where = ["--repo", repository] if repository else []
        return ["gh", "pr", "create", *where, "--base",
                tracking_branch_of(manifest), "--head", args.branch]
    repository, base = pull_request_target(root, kind)
    return ["gh", "pr", "create", "--repo", repository, "--base", base,
            "--head", args.branch, "--title",
            f"Re-sync the shape copies to {upstream.repository} @ "
            f"{target[:12]}",
            "--body",
            "Written by openRepoShape's `update-shape.py`: the copied "
            "shape files were re-copied from the upstream and "
            "`contracts/shape-pin.yaml` and `project.yaml` re-pinned onto "
            f"{target}. No copy was hand-edited and every digest was "
            "recomputed."]


def open_pull_request(root: Path, args, create: list[str]) -> None:
    """Run `create`, the `gh pr create` `pull_request_line` built, for
    `args.branch`, which already carries the re-pin.

    A FAILED `gh pr create` IS REPORTED HERE, as what it is (#204): the
    commit, and the push when there was one, have already landed, so the
    refusal names this step, rolls nothing back, and ends on a NEXT line.
    """
    try:
        url = _landing_run(create, root)
    except CommandFailed as exc:
        raise landing_failed(root, args, exc,
                             f"opening the pull request for {args.branch}",
                             create) from exc
    print(f"  pull request {url}")


def _unwritten_changes(root: Path, paths: list[str],
                       pinned_paths: list[str]) -> list[str]:
    """The pinned copies this run did NOT write whose bytes HEAD does not
    commit (#436): what a branchless run's commit line would leave out.

    THE PIN THIS RUN WROTE RECORDS EVERY ROW FROM THE WORKING TREE, so a
    pinned copy that differs from HEAD and is not among `paths` — an
    earlier `apply` left uncommitted, a local edit `--accept-local` took —
    would be HEAD's bytes in that commit under a digest of the disk's: the
    red commit `--branch` now refuses to make. Asked only where HEAD names
    a commit: a root with none has no commit line to get wrong, and prints
    the one it always printed.
    """
    rest = [path for path in pinned_paths if path not in paths]
    if not rest or _git_answer(root, ["rev-parse", "--verify", "--quiet",
                                      "HEAD"]) is None:
        return []
    return _not_what_head_commits(root, rest)


def next_line(root: Path, args, paths: list[str], target: str,
              added: list[str] = (), kind: Kind = PROJECT_KIND, *,
              pinned_paths: list[str] = ()) -> None:
    if args.branch and args.pr:
        print("NEXT  the pull request is open; ask a human to review and merge it")
        return
    if args.branch:
        # The base and the repository the pull request `--pr` would have
        # opened lands on, read the way `pull_request_target` reads them
        # (#209).
        manifest = load_yaml(root / kind.manifest)
        base = shlex.quote(tracking_branch_of(manifest))
        repository, _ = pull_request_repository(manifest, kind)
        # `--repo` in BOTH forms: the bare one's `gh` runs wherever the line
        # is pasted, and `check`'s own NEXT line sends a human to paste from
        # the openRepoShape checkout, whose `origin` is not this project's.
        # Where the manifest names no repository, `--push` keeps the
        # placeholder it always printed and the bare form leaves `--repo` off.
        if repository:
            where = f" --repo {shlex.quote(repository)}"
        else:
            where = " --repo <org>/<Project>" if args.push else ""
        # THE BRANCH TOO (#325). `checked_branch`'s alphabet is already one
        # `shlex.quote` leaves alone, so this prints the bytes it always
        # printed; it is quoted so that widening that alphabet one day cannot
        # reopen a line that has a whole argument to itself.
        create = (f"gh pr create{where} --base {base} --head "
                  f"{shlex.quote(args.branch)}")
        if args.push:
            print(f"NEXT  {create}")
        else:
            # THE ROOT, QUOTED (#325): `git -C <root>` is the one place a
            # path with a space, a quote or a `$` was printed bare in front of
            # `&&`, so the push the line starts with went to the wrong place
            # or not at all and the `gh pr create` after it never ran.
            push = shlex.join(["git", "-C", str(root), "push", "-u", "origin",
                               args.branch])
            print(f"NEXT  {push} && {create}")
        return
    # NO COMMIT LINE OVER CHANGES THIS RUN DID NOT WRITE (#436). The line
    # below commits HEAD plus only this run's paths, which is the commit
    # `update-branch-uncommitted` refuses to make under `--branch`; here the
    # copies are already written, so the answer is a NEXT line that names
    # what that commit would leave out, rather than one that makes it red.
    unwritten = _unwritten_changes(root, paths, pinned_paths)
    if unwritten:
        print("NEXT  no commit line: the working tree does not hold what "
              f"HEAD commits at {', '.join(unwritten)}, paths this run did "
              "not write and whose bytes the pin it wrote records, so a "
              f"commit of {', '.join(paths)} alone would record digests for "
              "bytes it does not carry. Commit those changes with them if "
              "this re-pin is to carry them, or put both back to HEAD's "
              "bytes and run apply again")
        return
    # A `git add` for the ADDITIONS only. A hint that a human pastes has to
    # work when they paste it, and `git commit -- <path>` refuses a path git
    # has never heard of — which every file `--add` just wrote is. FORCED,
    # as `commit_on_branch` stages them (#202): a plain `git add` refuses a
    # path the operator's own excludes ignore, and a pinned copy left out of
    # the commit is a red `validate-pins.py` on the next clone.
    #
    # QUOTED, AND LITERAL (#202). `-f` is what makes a glob dangerous here: a
    # name holding `[`, pasted bare, is a pattern the SHELL expands to an
    # ignored neighbour (`docs/guide[1].md` -> `docs/guide1.md`), and `-f`
    # forces the neighbour in. Quoting stops the shell and not git, which
    # reads the pathspec as a glob too, so the add also says
    # `--literal-pathspecs`, as `force_stage` does. The commit's own list is
    # quoted for the shell the same way, so the whole line pastes whole. No
    # copy-list entry holds a glob character today; an ordinary name prints
    # exactly as it did.
    #
    # AND THE ROOT (#325): `git -C <root>` opens each of the line's commands
    # and was the one word in it printed bare, so a root with a space in it
    # made the branch in the wrong repository, or none.
    where = shlex.quote(str(root))
    stage = (f"--literal-pathspecs add -f -- {shlex.join(added)} && git -C "
             f"{where} " if added else "")
    print(f"NEXT  git -C {where} checkout -b shape/update-{target[:12]} && git "
          f"-C {where} {stage}commit -m 'Re-sync the shape @ {target[:12]}' -- "
          + shlex.join(paths))


# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="update-shape.py", description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
            ("check", "report what the upstream has changed; write nothing"),
            ("apply", "re-copy the changed files and re-pin")):
        sub = subparsers.add_parser(name, help=help_text)
        sub.add_argument("--root", required=True,
                         help="the assembly root to update")
        sub.add_argument("--upstream", default=None,
                         help="a path to a clone of openRepoShape, or "
                              "`owner/repo` (default: the pin's "
                              "`source_repository`)")
        sub.add_argument("--at", default=None,
                         help="the upstream revision to update to "
                              "(default: the upstream's tip)")
    apply_parser = subparsers.choices["apply"]
    apply_parser.add_argument("--yes", action="store_true",
                              help="the human has read `check` and said yes")
    apply_parser.add_argument("--accept-local", action="append", metavar="PATH",
                              default=[],
                              help="re-pin this locally-modified file FROM THE "
                                   "ROOT'S OWN BYTES; repeatable")
    apply_parser.add_argument("--add", action="append", metavar="PATH",
                              default=[],
                              help="copy this `upstream-added` file into the "
                                   "root and append its pin row; repeatable, "
                                   "and never passed for a file a human has "
                                   "not said to take")
    apply_parser.add_argument("--branch", default=None,
                              help="create this branch and commit the change "
                                   "to it, with explicit pathspecs")
    apply_parser.add_argument("--trailer", action="append",
                              metavar='"KEY: VALUE"', default=[],
                              type=trailer_line,
                              help="append this `<Key>: <value>` line to the "
                                   "commit, after any already there; "
                                   "repeatable, kept in the order given, and "
                                   "needs --branch — there is no commit to "
                                   "put a line on without one")
    apply_parser.add_argument("--push", action="store_true",
                              help="push the branch to origin (needs --branch)")
    apply_parser.add_argument("--pr", action="store_true",
                              help="open a pull request with `gh` (needs "
                                   "--branch); a later run on that branch "
                                   "with nothing left to write opens it if "
                                   "it is still missing")
    return parser


def main(argv: list[str] | None = None) -> int:
    # FIRST, so that every `print` after it -- `--help` included -- escapes
    # a name stdout cannot encode rather than raising on it (#214).
    escape_what_stdout_cannot_encode()
    args = build_parser().parse_args(argv)
    try:
        if args.command == "check":
            return cmd_check(args)
        if args.branch:
            # BEFORE ANY USE (#204): every path below may run `git` or `gh`
            # with it or print it in a NEXT line, the re-run's included,
            # which never reaches the commit's own check.
            args.branch = checked_branch(args.branch)
        # NAMED BY WHAT WAS ACTUALLY PASSED. The three fail for one
        # reason — there is no commit — and a refusal listing flags nobody
        # typed reads as a refusal of something else. `--trailer` joined them
        # on 2026-09-11 (#111): a trailer is a LINE ON THE COMMIT this tool
        # writes, so without --branch there is no commit for it to be a line
        # on, and writing one onto the current branch is the very thing the
        # posture rules in `commit_on_branch` exist to refuse.
        offered = [name for name, given in (("--push", args.push),
                                            ("--pr", args.pr),
                                            ("--trailer", bool(args.trailer)))
                   if given]
        if offered and not args.branch:
            raise Refusal(
                "update-branch-required",
                " and ".join(offered)
                + (" has" if len(offered) == 1 else " have")
                + " nothing to act on without --branch",
                "Remediation: pass --branch <name>; this tool never pushes to "
                "a default branch, never commits without being asked to, and "
                "a trailer is a line on a commit it has not been asked to "
                "make.")
        return cmd_apply(args)
    except Refusal as exc:
        return die(exc)
    except CommandFailed as exc:
        print(exc.loudly("updating the shape"), file=sys.stderr)
        return 2
    except LandingIncomplete:
        # Reported where it happened, NEXT line included (#204); the exit
        # code is all that is left to give.
        return 2


if __name__ == "__main__":
    sys.exit(main())
