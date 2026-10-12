#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Advance ONE leg of an assembly root, in ONE LOCKSTEP COMMIT.

    ./scripts/bump-leg.py --root <assembly root> --leg spec|code
                          --to <40 hex> [--trailer "<Key>: <value>" ...]
                          [--local-remote-dir <dir>] [--dry-run]

Run from a checkout of THIS standard and pointed at a project, exactly as
`scripts/family.py` and `update-shape.py` are run.

THREE FACTS, ONE COMMIT. A leg is pinned three times over, and the project's
own `scripts/validate-pins.py` refuses when the three disagree:

    1. the GITLINK the assembly root records at the leg's path,
    2. `commit:` and `digests.tree_sha256` in `contracts/<role>-pin.yaml`,
    3. every TRACKED `.github/workflows/*.yml` reference of the form
       `<owner>/<leg>/...@<40 hex>` naming THAT leg's repository.

`family.py bump` already did exactly this for a family's MEMBER pins. Nothing
did it for a root's LEG pins, so every project moved its own by hand — which
is the failure the invariant was written down about: in the xFactory
aggregation seven consecutive pin-syncs from 2026-08-25 moved the gitlink
alone and left `validate` red on every pull request until 2026-08-26,
unnoticed for a day because the check runs on pull requests only.

WHAT IT REFUSES, and why each is a refusal rather than a warning:

  * `--to` that is not exactly 40 hex. A tag can be moved and a short oid can
    become ambiguous; a pin is a whole commit or it is nothing.
  * a commit the leg's REMOTE does not have. A pin nobody else can fetch is a
    root nobody else can bootstrap.
  * a dirty root. The commit is made with explicit pathspecs, so unrelated
    edits would not be swept in — but a lockstep commit that cannot be read as
    exactly one change is the thing the rule exists to keep readable.
  * a workflow file git does not TRACK — untracked, or ignored — that names
    the leg at any other commit. The lockstep commit's `git add` names every
    file this rewrites: an untracked one would be added to the commit whole,
    as a new file nobody committed, and an ignored one would stop that
    `git add` after the rewrite, in git's own words. Leaving either alone
    would turn the bump red, because `validate-pins.py` reads every file on
    disk and would still see its old `@<sha>`. Refused by name, before
    anything is written, under `--dry-run` as well. One that names no leg,
    or this leg already at `--to`, is left alone. A TRACKED file the disk
    spells another way — renamed by case alone outside git, on a disk that
    ignores case — is that tracked file, rewritten and committed under
    git's spelling, never refused as untracked.
  * the root standing on its own tracking branch. The next step this prints
    would then be a push to the default branch, and these organisations are
    pull-request only. `--dry-run` commits nothing, so it runs there, and ends
    by naming the `git switch -c` the real run needs (#477).
  * a workflow file under `.github/workflows/`, or the leg's
    `contracts/<role>-pin.yaml`, that is not UTF-8 (a Latin-1 comment, a
    UTF-16 file with a byte-order mark): `bump-leg-workflow-unreadable` and
    `bump-leg-pin-unreadable`, naming each file and its first bad byte, before
    anything is written and under `--dry-run` as well (#289). Never read
    lossily — the rewritten text is written back, and would carry U+FFFD
    where the operator's byte was — and never skipped, since `validate-pins.py`
    reads every workflow file on disk and cannot read it either. A workflow
    file git does not track is refused the same way and marked `(untracked or
    ignored)`: it needs the re-save and no commit, where a tracked one is
    committed after it.
  * the same two ids for a file or a directory this user cannot OPEN (#383):
    a workflow file, `.github/workflows/` itself or the leg's pin that the
    operating system refuses (`Permission denied`) or fails to read, naming
    the path and the system's own reason. The remedy is to make it readable
    by this user (`chmod u+r`, or fix who owns it) and run the same command
    again, not a re-save. Refused before anything is written, under
    `--dry-run` as well, whether or not the file names the leg, and a line
    for a file git does not track is marked as it is for a file that is not
    UTF-8.
  * a validator that goes red after the rewrite. Every byte is rolled back
    first — the pin file, the workflow files, the leg's checkout and the index
    — so a refusal leaves the tree exactly as it was found.
  * any other failure once the leg has been asked to move, up to and
    including a commit git refuses (a signing key that cannot sign, a
    `commit-msg` hook) — a workflow file it cannot write, a stdout that
    cannot encode what a validator printed, an interrupt — is rolled back
    the same way and then reported: as a refusal naming the exception for an
    `OSError` or a `UnicodeError`, and as itself for anything else, an
    interrupt included, after a line saying whether the tree is back. No
    report claims more than the rollback did: a step it could not do is
    named, and so is a leg whose `git status` no longer reads as it did
    before the bump (a checkout cut off part way leaves the files it wrote),
    and the report says THE ROLLBACK WAS NOT COMPLETE. A failure after the
    commit has landed rolls nothing back, and says so.

EXIT CODES: 0 the commit was made, or a `--dry-run` printed a move it would
make · 1 NOTHING TO DO — every fact already names that commit, under
`--dry-run` as well, so a re-run of a bump that already landed writes no empty
commit · 2 a refusal.
"""

from __future__ import annotations

import argparse
import errno
import os
import re
import stat
import subprocess
import sys
from functools import partial
from pathlib import Path
from typing import Callable

SHAPE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHAPE_ROOT / "scripts"))
from repo_shape import (  # noqa: E402
    COMMIT_RE, SAFE_PATH_RE, Refusal, checked_value, git_out, load_yaml,
    recorded_gitlink, repo_basename, tree_digest,
)
from shape_materialize import (  # noqa: E402
    CommandFailed, captured_child_environment, check_program, commit_trailers,
    escape_what_stdout_cannot_encode, is_nested_key, rewrite_fault, run,
    trailer_line, with_scalar, write_lf,
)

MANIFEST = "project.yaml"

#: The root's OWN validators, run after the rewrite and before the commit.
#: Copies, not this checkout's: a project runs its own gate offline, and the
#: only opinion that matters here is the one its pull request will report.
VALIDATORS = ("scripts/validate-pins.py", "scripts/validate-manifest.py")

#: A local-path remote is a `file://` fetch, which git has refused for
#: submodule work since the 2022 advisories. Passed only on the
#: `--local-remote-dir` path, which is the TEST path; a real leg is an https
#: remote and needs none of it.
FILE_PROTOCOL = ["-c", "protocol.file.allow=always"]

#: `owner/repo[/path]@<40 hex>` as it appears in a `uses:` line. CHARACTER FOR
#: CHARACTER the expression `templates/assembly-root/scripts/validate-pins.py`
#: reads the same lines with: this tool writes what that one checks, and a
#: rewriter matching a wider or narrower set than the validator is a rewriter
#: that leaves a reference the gate will still call wrong.
#: `tests/test_bump_leg.py` asserts the two spellings are identical.
WORKFLOW_REF_RE = re.compile(
    r"(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)(?P<path>/[^@\s'\"]*)?"
    r"@(?P<sha>[0-9a-fA-F]{40})"
)


# ---------------------------------------------------------------------------
# project.yaml: reading the leg out of it
# ---------------------------------------------------------------------------


class Project:
    """An assembly root on disk: its manifest, its legs, and where it is."""

    def __init__(self, root: Path, data: dict):
        self.root = root
        self.data = data
        self.path = root / MANIFEST

    @classmethod
    def open(cls, root_spec) -> "Project":
        root = Path(root_spec).expanduser().resolve()
        path = root / MANIFEST
        if not path.is_file():
            raise Refusal(
                "bump-leg-root-not-a-project",
                f"{path} does not exist, so this is not an assembly root of a "
                "project that has elected this shape",
                "Remediation: --root takes the ASSEMBLY ROOT — the repository "
                "an engineer clones — not a leg and not a family holder. A "
                "family's member pins are moved with `scripts/family.py "
                "bump`; a leg has no legs of its own to move.")
        data = load_yaml(path)
        if not isinstance(data, dict):
            raise Refusal("bump-leg-manifest-unreadable",
                          f"{path}: not a mapping")
        if data.get("kind") != "project-manifest":
            raise Refusal(
                "bump-leg-wrong-kind",
                f"{path}: kind is {data.get('kind')!r}, expected "
                "'project-manifest'",
                "Remediation: a family holder declares `kind: "
                "family-manifest` and its members move with `scripts/"
                "family.py bump`.")
        return cls(root, data)

    @property
    def legs(self) -> list[dict]:
        return [row for row in (self.data.get("legs") or [])
                if isinstance(row, dict)]

    def leg(self, role: str) -> dict:
        # `assembly` IS declared, at path `.`, and is refused BEFORE the
        # lookup rather than after it: the manifest names it, so a not-found
        # branch would never be reached, and the root is not a submodule of
        # itself to advance.
        if role == "assembly":
            raise Refusal(
                "bump-leg-assembly-is-not-a-leg",
                "the assembly root is THIS repository, mounted at `.`, and it "
                "is not a submodule of itself",
                "Remediation: --leg takes `spec` or `code`. The assembly "
                "root advances by its own commits; if you meant to move the "
                "project's pin inside a FAMILY, that is `scripts/family.py "
                "bump --member <Project> --to <sha>`.")
        for row in self.legs:
            if str(row.get("role")) == role:
                return row
        declared = ", ".join(sorted(str(row.get("role")) for row in self.legs))
        raise Refusal(
            "bump-leg-unknown-leg",
            f"{self.path} declares no leg with role {role!r}; it declares "
            f"{declared}",
            "Remediation: --leg takes a role this project's own manifest "
            "names. A leg that is missing from the manifest is a manifest "
            "defect, not something to pin around.")

    @property
    def display_name(self) -> str:
        name = str(self.data.get("name") or "").strip()
        if name:
            return name
        for row in self.legs:
            if str(row.get("role")) == "assembly":
                return repo_basename(str(row.get("repository") or ""))
        return str(self.data.get("id") or "this project")

    @property
    def tracking(self) -> str:
        return str(self.data.get("tracking_branch") or "main")


# ---------------------------------------------------------------------------
# the three facts, rewritten
# ---------------------------------------------------------------------------


def rewrite_pin(text: str, commit: str, digest: str) -> str:
    """`commit:` and `digests.tree_sha256:`, and NOTHING else.

    A LINE REWRITE, NOT A YAML DUMP, for the reason `update-shape.py` rewrites
    the shape pin that way and `family.py` rewrites the members block that
    way: the header of `<role>-pin.yaml` is three paragraphs saying what is
    digested and why a tag is never the referent, and a round trip through a
    serialiser would delete every one of them — the argument being the reason
    the file is trusted.

    THOSE TWO FIELDS ARE THE WHOLE DERIVATION. `revision_kind` is the constant
    `commit`; `leg_role`, `source_repository` and `submodule_path` come from
    `project.yaml` rather than from the commit; `digest_algorithm` and
    `digest_definition` name the definition, not a value. The scaffold and
    `adopt-project.py` substitute exactly `{{<ROLE>_COMMIT}}` and
    `{{<ROLE>_TREE_SHA256}}` from the commit being pinned, so those are
    exactly the two lines that move when the commit moves.

    Each replacement must fire exactly once or this refuses: a pin file this
    tool did not recognise is not a pin file it may edit.

    EACH OF THE TWO LINES KEEPS ITS OWN LAYOUT (#323). `commit:` is found at
    column 0 and `tree_sha256:` as any INDENTED line that begins with it, so a
    `digests:` child at any depth the reader accepts is recognised, and only
    the value after the key changes: the indentation, the spacing and a
    trailing `# comment` are the line's own. They were written back as
    `commit: "<sha>"` and `  tree_sha256: "<digest>"`, so a child indented
    four spaces was refused as hand-edited and a comment was dropped.

    WHAT IS RETURNED HAS BEEN READ BACK, as `update-shape.py`'s pin and
    manifest rewrites are (`shape_materialize.rewrite_fault`): a layout this
    line rewrite cannot carry is refused HERE as this tool's failure, before
    any byte is written. The digest is the one this command RECOMPUTED from
    the leg's own objects; the read-back only asks that it landed.
    """
    out: list[str] = []
    seen = {"commit": 0, "tree_sha256": 0}
    for line in text.splitlines():
        if line.startswith("commit:"):
            seen["commit"] += 1
            out.append(with_scalar(line, "commit", commit))
            continue
        if is_nested_key(line, "tree_sha256"):
            seen["tree_sha256"] += 1
            out.append(with_scalar(line, "tree_sha256", digest))
            continue
        out.append(line)
    for key, count in seen.items():
        if count != 1:
            raise Refusal(
                "bump-leg-pin-unrecognised",
                f"the pin file has {count} `{key}` line(s) where exactly one "
                "was expected, so this tool will not rewrite it",
                "Remediation: the pin was hand-edited into a shape this tool "
                "does not recognise. Fix it by hand this once — `commit:` at "
                "column 0 and `tree_sha256:` indented under `digests:` — or "
                "re-scaffold.")
    rewritten = "\n".join(out) + "\n"
    why = rewrite_fault(text, rewritten, commit, digest)
    if why is not None:
        raise Refusal(
            "bump-leg-pin-unrecognised",
            "the pin file reads as it stands, but this tool's rewrite of it "
            f"does not read back to the target ({why}), so this tool will not "
            "write it",
            "Remediation: the fault is this tool's line rewrite, not the "
            "project's pin. Put each of `commit:` and `tree_sha256:` on one "
            "line with its quoted value, as the scaffold writes them, leave "
            "both values as they are — this command recomputes the digest, "
            "nobody edits it to fit — and run the same command again; this "
            "tool will not guess at a pin it does not recognise.")
    return rewritten


def _tracked_workflows(root: Path, workflows: Path) -> set[str]:
    """The paths git TRACKS under `workflows`, as POSIX paths relative to
    `root` — the spelling `plan_workflows` and the commit's pathspecs use.

    The index, by `git ls-files`: `_ensure_root_clean` has already refused a
    root whose tracked files differ from it, so it is also what HEAD holds.
    NUL-separated, so a name git would otherwise quote comes back as the
    bytes it is.
    """
    raw = git_out(["ls-files", "-z", "--",
                   workflows.relative_to(root).as_posix()],
                  cwd=root, binary=True)
    return {os.fsdecode(name) for name in raw.split(b"\0") if name}


def _not_utf8(root: Path, path: Path, exc: UnicodeDecodeError) -> str:
    """`<path relative to root>: not UTF-8 at byte N (<reason>)`, in the
    words `repo_shape.load_yaml` gives the same failure (#192), so a file this
    tool cannot read is named the way every other reader names one."""
    return (f"{path.relative_to(root).as_posix()}: not UTF-8 at byte "
            f"{exc.start} ({exc.reason})")


#: The `OSError`s that `Path.is_file()` and `Path.is_dir()` answered False to
#: on Python 3.9 to 3.13 (pathlib's `_ignore_error`), because each means there
#: is nothing at the name to open: no such file, a part of the path that is
#: not a directory, a bad descriptor, a symlink loop, and Windows' "not
#: ready", "invalid name" and "cannot resolve". Every other one was raised.
_ABSENT_ERRNOS = (errno.ENOENT, errno.ENOTDIR, errno.EBADF, errno.ELOOP)
_ABSENT_WINERRORS = (21, 123, 1921)


def _is_a(path: Path, kind: Callable[[int], bool]) -> bool:
    """Whether `path` is there and of `kind` (`stat.S_ISREG`, `stat.S_ISDIR`),
    raising the `OSError` of a `stat` the operating system REFUSED (#383).

    NOT `Path.is_file()` OR `Path.is_dir()`, whose answer depends on the
    Python. Up to 3.13 they raised a refused `stat` (`PermissionError`) and
    answered False only when nothing was there; from 3.14 they call
    `os.path.isfile` and `isdir`, which answer False to ANY `OSError`. On 3.14
    the pin inside a `contracts/` this user cannot search was "missing"
    (`bump-leg-pin-missing`, whose remedy restores a file that is there), and
    every file in a `.github/workflows/` this user can list but not search
    was skipped as no file at all: the bump went ahead, `validate-pins.py`
    found the workflow "pinned but absent", and the run was rolled back as
    `bump-leg-validators-red`. Asked here, every Python answers as 3.9 to
    3.13 did, and a refused `stat` is a refusal that names the path.
    """
    try:
        mode = path.stat().st_mode
    except OSError as exc:
        if (exc.errno in _ABSENT_ERRNOS
                or getattr(exc, "winerror", None) in _ABSENT_WINERRORS):
            return False
        raise
    except ValueError:
        # a name the operating system cannot take at all (a NUL in it)
        return False
    return kind(mode)


def _os_reason(exc: OSError) -> str:
    """The operating system's own words for `exc` (`Permission denied`), or
    what Python made of it when there are none (an `OSError` raised with no
    errno carries no `strerror`)."""
    return exc.strerror or str(exc)


def _cannot_open(root: Path, path: Path, exc: OSError, *,
                 directory: bool = False) -> str:
    """`<path relative to root>: cannot be read: <reason>` (`cannot be listed`
    for a directory, named with a trailing `/`), in the shape `_not_utf8`
    gives a file this tool cannot decode, so a line says what failed on which
    file and the two causes read alike (#383)."""
    shown = path.relative_to(root).as_posix() + ("/" if directory else "")
    return (f"{shown}: cannot be {'listed' if directory else 'read'}: "
            f"{_os_reason(exc)}")


def _cannot_open_advice(errors: list[OSError]) -> str:
    """What to do about a file or a directory the operating system refused,
    for each cause present in `errors`, ending in a space so it joins the
    sentence after it (#383).

    NOT the re-save advice a file that is not UTF-8 is given: its bytes were
    never the trouble, and no edit to them makes a file readable. A refusal
    of permission (`PermissionError`, which is `EACCES` and `EPERM`) is put
    right by the mode or the owner; any other `OSError` (a file removed or
    replaced while this ran, an I/O error, a path that stopped being a file)
    is not a permission and is not told to `chmod`.
    """
    advice = ""
    if any(isinstance(error, PermissionError) for error in errors):
        advice += ("Make what this user may not open readable by this "
                   "user: `chmod u+r` on a file, `chmod u+rx` on a directory "
                   "(and on every directory above it inside the root), or "
                   "fix who owns it. ")
    if any(not isinstance(error, PermissionError) for error in errors):
        advice += ("Where the operating system gave another reason, put a "
                   "regular file this user can open back in its place, or "
                   "take away one nobody wants, and make sure nothing is "
                   "changing the directory while this runs. ")
    return advice


def _pin_unopened_refusal(root: Path, pin_path: Path,
                          exc: OSError) -> Refusal:
    """`bump-leg-pin-unreadable` for a pin the operating system refused, the
    id a pin that is not UTF-8 has, with this cause's own remedy (#383)."""
    return Refusal(
        "bump-leg-pin-unreadable",
        _cannot_open(root, pin_path, exc),
        "Remediation: this tool must read the leg's pin to rewrite "
        "`commit:` and `digests.tree_sha256` in it, and "
        "`scripts/validate-pins.py` reads it too. "
        + _cannot_open_advice([exc])
        + "Then run the same command again. Nothing in the working "
        "tree, the index or the leg's checkout was changed.")


def _leg_pin_text(root: Path, pin_path: Path) -> str:
    """The leg's `contracts/<role>-pin.yaml` as text, or a refusal naming it
    when it is not UTF-8 (#289) or this user cannot open it (#383).

    Read here rather than through `load_yaml` because `rewrite_pin` is a LINE
    REWRITE of the file's own text, which a parsed mapping cannot be. A
    `UnicodeDecodeError` is a `ValueError`: nothing on the path catches it and
    `main()` names `Refusal` and `CommandFailed` alone, so it ended the run in
    a traceback, exit 1, under `--dry-run` as well, because this read comes
    before that early return. It comes before anything is written, so the
    refusal promises only what is true: the working tree, the index and the
    leg's checkout are as they were. (The leg's object store was fetched into
    already, which `--dry-run` says it does.)

    THE OPERATING SYSTEM'S REFUSAL IS THE SAME REFUSAL, BY ANOTHER CAUSE
    (#383). A pin this user may not open raised `PermissionError`, which is
    an `OSError` and no `Refusal`: the same traceback, exit 1, from this same
    read, with `--dry-run` no different. The id is the one a pin that is not
    UTF-8 has, so one id says "this tool cannot read the leg's pin" whatever
    the reason, with the cause's own detail and its own remedy.
    """
    try:
        return pin_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise _pin_unopened_refusal(root, pin_path, exc) from exc
    except UnicodeDecodeError as exc:
        raise Refusal(
            "bump-leg-pin-unreadable",
            _not_utf8(root, pin_path, exc),
            "Remediation: this tool rewrites `commit:` and "
            "`digests.tree_sha256` in this file as UTF-8 text, and reads no "
            "file lossily, because the rewritten text is written back and "
            "would carry U+FFFD where your byte was. Byte "
            f"{exc.start}, counting from 0 at the start of the file, is the "
            "first that is not UTF-8: re-save the file as UTF-8, or replace "
            "that byte with the character it was meant to be, commit it, and "
            "run the same command again. Nothing in the working tree, the "
            "index or the leg's checkout was changed.") from exc


def _workflow_children(root: Path, workflows: Path) -> list[Path]:
    """The entries of `workflows`, sorted — or a refusal naming the directory
    when this user cannot list it (#383).

    `plan_workflows` lists the directory for the names git is compared with,
    and `_workflow_texts` lists it again to read the files, so both go through
    here. A directory this user may not list raised `PermissionError` out of
    `iterdir`, which `main()` does not catch: a traceback, exit 1, naming
    Python's error and no refusal. It reads as CLEAN to git
    (`git status --porcelain` prints its `Permission denied` on stderr, writes
    nothing to stdout and exits 0), so `_ensure_root_clean` lets the run
    through to here. The listing is before anything is written, under
    `--dry-run` as well, so the refusal promises only what is true: the
    working tree, the index and the leg's checkout are as they were.
    """
    try:
        return sorted(workflows.iterdir())
    except OSError as exc:
        raise _workflows_dir_refusal(root, workflows, exc) from exc


def _workflows_dir_refusal(root: Path, workflows: Path,
                           exc: OSError) -> Refusal:
    """`bump-leg-workflow-unreadable` for the DIRECTORY, named as one."""
    return Refusal(
        "bump-leg-workflow-unreadable",
        _cannot_open(root, workflows, exc, directory=True),
        "Remediation: this tool reads every workflow file in the directory "
        "named above, whether or not it names this leg, and "
        "`scripts/validate-pins.py` reads them too, so a directory it cannot "
        "list is one it cannot bump. "
        + _cannot_open_advice([exc])
        + "Then run the same command again. Nothing in the working tree, "
        "the index or the leg's checkout was changed.")


def _workflow_texts(root: Path, workflows: Path, tracked: set[str],
                    listed: set[str]) -> list[tuple[Path, str]]:
    """Every `.yml` and `.yaml` file in `workflows`, read as UTF-8 — or ONE
    refusal naming each that is not (#289) or that this user cannot open
    (#383).

    EVERY FILE IS READ, whether or not it names the leg, so a file that is not
    UTF-8 is REFUSED BY NAME and never skipped, never read lossily.
    `read_text(encoding="utf-8")` on a Latin-1 comment or a UTF-16 file with a
    byte-order mark raised `UnicodeDecodeError`, which nothing caught: a
    traceback, exit 1, under `--dry-run` too, because this read comes before
    that early return. Skipping the file would leave `validate-pins.py`, which
    reads every workflow on disk, unable to read it either, and
    `errors="replace"` would write U+FFFD over the operator's byte into the
    lockstep commit. All of them are named at once, so the operator re-saves
    each in one pass instead of meeting them one run at a time. The read is
    before anything is written, so the refusal promises only what is true:
    the working tree, the index and the leg's checkout are as they were.

    EACH LINE SAYS WHETHER GIT TRACKS THE FILE, because the advice differs.
    A tracked file is committed after the re-save. One git does not track,
    untracked or ignored, needs only the re-save: committing it would put a
    draft on the bump branch, which `plan_workflows` refuses an untracked
    file for (#207), and `git add` refuses an ignored one. `tracked` and
    `listed` are `plan_workflows`' own, and `_tracked_spelling` answers with
    them, so a tracked file the disk spells another way (#332) is not marked.
    It is asked only of a file already refused and reads no file (`tracked` is
    in hand, `_same_file` is a `stat`), so every read still comes before
    anything is written.

    THE OPERATING SYSTEM'S REFUSAL IS THE SAME REFUSAL, BY ANOTHER CAUSE
    (#383). A file this user may not open raised `PermissionError`, an
    `OSError` that `main()` does not catch either: the same traceback, exit 1,
    `--dry-run` included. Any `OSError` of the read or of the `stat` before
    it (`_is_a`, which a directory this user can list but not search
    refuses) is named the same way, as a line of its own with the system's
    reason, whether or not the file names the leg; a file that is not UTF-8
    and one that cannot be opened meet in ONE refusal, each group with its own
    header and its own advice, because the re-save the first needs does
    nothing for the second. Each line says whether git tracks the file as
    before, and a file that was only unreadable is never told to be
    committed: restoring a mode changes no content, so there is nothing to
    commit for it, tracked or not.
    """
    texts: list[tuple[Path, str]] = []
    unreadable: list[tuple[str, bool]] = []
    unopened: list[tuple[str, bool, OSError]] = []
    for path in _workflow_children(root, workflows):
        try:
            if (path.suffix not in (".yml", ".yaml")
                    or not _is_a(path, stat.S_ISREG)):
                continue
            texts.append((path, path.read_text(encoding="utf-8")))
        except UnicodeDecodeError as exc:
            held = _tracked_spelling(root, path, tracked, listed) is not None
            unreadable.append((_not_utf8(root, path, exc), held))
        except OSError as exc:
            held = _tracked_spelling(root, path, tracked, listed) is not None
            unopened.append((_cannot_open(root, path, exc), held, exc))
    if unreadable or unopened:
        marked = "  (untracked or ignored)"
        detail: list[str] = []
        advice = ""
        if unreadable:
            detail.append(
                f"{len(unreadable)} workflow file(s) are not UTF-8:\n"
                + "\n".join(f"    {line}" + ("" if held else marked)
                            for line, held in unreadable))
            advice += (
                "this tool rewrites each workflow file as UTF-8 "
                "text and reads none lossily, because the rewritten text is "
                "written back and would carry U+FFFD where your byte was; "
                "`scripts/validate-pins.py` reads every workflow file on "
                "disk as UTF-8 too, so skipping one would only move the "
                "failure there. In each line above, the byte is counted from "
                "0 at the start of the file and is the first that is not "
                "UTF-8: re-save every file named as UTF-8 (a UTF-16 file "
                "with a byte-order mark needs converting, not editing), "
                "whether or not it names this leg. ")
            if any(held for _, held in unreadable):
                advice += "Commit each file git tracks. "
            if not all(held for _, held in unreadable):
                advice += ("A file marked (untracked or ignored) needs no "
                           "commit, only the re-save: committing it would "
                           "put it on this branch, so either leave it "
                           "uncommitted or move it out of "
                           ".github/workflows/ until the bump has landed. ")
        if unopened:
            detail.append(
                f"{len(unopened)} workflow file(s) cannot be opened:\n"
                + "\n".join(f"    {line}" + ("" if held else marked)
                            for line, held, _ in unopened))
            advice += (
                "Each file named as cannot be opened is one this tool "
                "cannot rewrite, and `scripts/validate-pins.py` reads every "
                "workflow file on disk too, whether or not it names this "
                "leg, so skipping one would only move the failure there. "
                + _cannot_open_advice([error for _, _, error in unopened])
                + "No commit is needed for a file that could not be opened: "
                "made readable, it has no change to commit. ")
            if not all(held for _, held, _ in unopened):
                advice += ("A file marked (untracked or ignored) is not in "
                           "the repository: it can also be moved out of "
                           ".github/workflows/ until the bump has landed. ")
        raise Refusal(
            "bump-leg-workflow-unreadable", "\n".join(detail),
            "Remediation: " + advice
            + "Then run the same command again. Nothing in the working "
            "tree, the index or the leg's checkout was changed.")
    return texts


def _same_file(first: Path, second: Path) -> bool:
    """Whether the filesystem resolves both names to ONE file — False when
    either cannot be resolved at all.

    THE SEAM a test on a disk that keeps case replaces to stand in for one
    that ignores it (#332): no other line of this tool asks the question.
    """
    try:
        return os.path.samefile(first, second)
    except OSError:
        return False


def _tracked_spelling(root: Path, path: Path, tracked: set[str],
                      listed: set[str]) -> str | None:
    """Git's spelling of the workflow file at `path`, or None when git does
    not track it.

    `path` is a name the directory walk yielded, and `listed` is every name
    that walk yields. A name git holds is its own spelling. Any other is a
    tracked file only when EXACTLY ONE tracked name in the same directory is
    missing from `listed` and the filesystem resolves it to this very file:
    a disk that ignores case, which macOS and Windows use by default, holds
    a tracked `legs.yml` renamed outside git to `Legs.yml` as one file,
    lists it as `Legs.yml` and opens it under either name. A tracked name
    the walk DOES list is a file of its own, never a respelling of another,
    and one no file answers to is not this one. Two that both answer are an
    index carrying two spellings of one file, which no single rewrite can
    keep in step, so that name is left unresolved and refused as untracked.

    THE FILESYSTEM IS ASKED, NOT `core.ignorecase`. The setting is git's
    record of the disk a clone was made on, and a clone copied to another
    disk keeps it. Set true on a disk that keeps case, git lists neither a
    separate `Legs.yml` as untracked nor stages it (`git add Legs.yml` is a
    no-op and `git commit -- Legs.yml` refuses the pathspec): taken from
    git, such a file would be rewritten on disk and be missing from the
    commit. Asked of the filesystem, a second spelling there is a second
    file and is refused by name, whatever the setting says.
    """
    relative = path.relative_to(root).as_posix()
    if relative in tracked:
        return relative
    parent = relative.rsplit("/", 1)[0]
    answering = [other for other in sorted(tracked)
                 if other.rsplit("/", 1)[0] == parent
                 and other.rsplit("/", 1)[1] not in listed
                 and _same_file(root / other, path)]
    return answering[0] if len(answering) == 1 else None


def plan_workflows(root: Path, repository: str,
                   commit: str) -> list[tuple[Path, str, int]]:
    """Every TRACKED workflow file whose `@<sha>` refs to THIS leg have to move.

    Returns `(path, rewritten text, references moved)`, one row per file that
    actually changes. A reference to any OTHER repository is left exactly as
    it is — `actions/checkout@<40 hex>` and the sibling leg's own reusable
    workflow are pinned by somebody else's rule, and a bump that moved them
    would be a supply-chain edit wearing a bookkeeping commit's message.

    `.yaml` is read as well as `.yml` because `validate-pins.py` reads both,
    and a file this rewrote nothing in is a file the gate still calls red.

    TRACKED FILES ONLY (#207). The directory is walked on disk, because that
    is the set `validate-pins.py` reads, but a row is made for a file only
    when git tracks it: the lockstep commit's `git add` names every file it
    rewrote, so a draft that was never committed would be added to "Bump spec
    leg" whole, as a new file, while `_ensure_root_clean` — which skips
    untracked files on exactly the ground that they cannot reach this commit
    — said nothing. (An IGNORED one is no better, only later: `git add`
    refuses it after the rewrite, with its own hint and no word about this
    tool.) An untracked or ignored file that has a reference to move is
    REFUSED by name rather than skipped: skipped, `validate-pins.py` would
    still read its old `@<sha>` off the disk and turn the bump red after the
    rewrite, with a finding that never says the file is not in the
    repository. One with nothing to move — no reference to this leg, or this
    leg already at `commit` — is not this tool's business and is left alone,
    unnamed.

    A TRACKED FILE THE DISK SPELLS ANOTHER WAY IS STILL TRACKED (#332). The
    walk yields the disk's spelling and `git ls-files` the index's, and on a
    disk that ignores case a tracked `legs.yml` renamed to `Legs.yml` outside
    git is one file under both: `git status` is clean under the
    `core.ignorecase` a clone there is given, and an exact comparison
    refused it as untracked with an exit, "commit it first", that could
    never clear it — there is nothing to commit. Its row carries GIT'S
    spelling (`_tracked_spelling`), because git matches a commit's pathspec
    against the index by exact spelling whatever the disk does: the commit
    names the path git tracks and no other, and the rewrite reaches the one
    file through it, read through the disk's name and written through
    git's, which the filesystem has already said are the same file.

    A file that is not UTF-8, or that this user cannot open, is a refusal
    (`_workflow_texts`, #289 and #383), and so is the directory itself when
    this user cannot list it (`_workflow_children`, #383).
    """
    plans: list[tuple[Path, str, int]] = []
    workflows = root / ".github" / "workflows"
    try:
        if not _is_a(workflows, stat.S_ISDIR):
            return plans
    except OSError as exc:
        # a directory above `workflows` this user cannot search (#383)
        raise _workflows_dir_refusal(root, workflows, exc) from exc
    tracked = _tracked_workflows(root, workflows)
    listed = {child.name for child in _workflow_children(root, workflows)}
    untracked: list[tuple[str, int]] = []
    for path, text in _workflow_texts(root, workflows, tracked, listed):
        moved = 0

        def swap(match: re.Match) -> str:
            nonlocal moved
            if match.group("repo") != repository:
                return match.group(0)
            if match.group("sha").lower() == commit:
                return match.group(0)
            moved += 1
            return (f"{match.group('repo')}{match.group('path') or ''}"
                    f"@{commit}")

        rewritten = WORKFLOW_REF_RE.sub(swap, text)
        if not moved:
            continue
        spelled = _tracked_spelling(root, path, tracked, listed)
        if spelled is not None:
            plans.append((root / spelled, rewritten, moved))
        else:
            untracked.append((path.relative_to(root).as_posix(), moved))
    if untracked:
        raise Refusal(
            "bump-leg-workflow-untracked",
            f"{len(untracked)} workflow file(s) that git does not track "
            f"(untracked or ignored) name {repository} at a commit other "
            f"than {commit[:12]}:\n"
            + "\n".join(f"    {relative}  {count} reference(s)"
                        for relative, count in untracked),
            "Remediation: the lockstep commit adds no file the repository "
            "does not already hold, and `scripts/validate-pins.py` reads "
            "every workflow file on disk, so one left where it is would turn "
            "the bump red over its old `@<sha>`. Either commit it first — it "
            "is then tracked and moves with the bump, and the dry run lists "
            "it — or move it out of .github/workflows/ until the bump has "
            "landed, then re-run.")
    return plans


# ---------------------------------------------------------------------------
# the leg's own repository
# ---------------------------------------------------------------------------


def leg_placement(submodule: Path) -> str | None:
    """`refs/heads/<branch>`, or None when the leg is detached.

    Remembered BEFORE the checkout so a rollback puts the leg back where it
    stood rather than merely back at the right commit: `bootstrap.py` leaves
    each leg ON its tracking branch at the pinned commit, and a rollback that
    left it detached would have changed something a refusal promised not to.
    """
    proc = subprocess.run(["git", "symbolic-ref", "--quiet", "HEAD"],
                          cwd=str(submodule), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False)
    return proc.stdout.strip() or None


def restore_leg(submodule: Path, placement: str | None, commit: str) -> None:
    if placement and placement.startswith("refs/heads/"):
        branch = checked_value("the leg's branch",
                               placement[len("refs/heads/"):])
        run(["git", "checkout", "-q", branch], cwd=submodule)
        return
    run(["git", "checkout", "-q", "--detach", commit], cwd=submodule)


def object_present(submodule: Path, commit: str) -> bool:
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}"],
        cwd=str(submodule), capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False)
    return proc.returncode == 0


def on_a_remote_branch(submodule: Path, commit: str) -> bool:
    """Is `commit` reachable from one of this leg's `origin/*` branches?"""
    proc = subprocess.run(
        ["git", "for-each-ref", "--contains", commit, "--format=%(refname)",
         "refs/remotes/origin/"],
        cwd=str(submodule), capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False)
    return proc.returncode == 0 and bool(proc.stdout.strip())


def fetch_leg(submodule: Path, repository: str, commit: str,
              local_remote_dir: Path | None) -> None:
    """Get `commit` into the leg's object store, and prove the REMOTE has it.

    A pin nobody else can fetch is a root nobody else can bootstrap, so
    "present in this checkout" is not the question — "on the leg's remote" is.
    Every branch is fetched into `refs/remotes/origin/*` and the commit must
    then be REACHABLE FROM ONE OF THEM.

    REACHABILITY, NOT A FETCH THAT EXITED 0. `git fetch <remote> <sha>`
    answers success without asking the remote anything at all when the object
    is already in the local store — which is exactly the case this has to
    catch, a commit somebody made inside the mount and never pushed. Measured,
    against a bare repository that demonstrably did not have the object:
    `git fetch <bare> <sha>` exited 0. So the fetch is only ever how the refs
    get here; `for-each-ref --contains` is what answers.

    The fetch itself is BEST EFFORT: a machine that cannot reach the remote
    may still be able to answer from the remote-tracking refs it already has,
    and a refusal below says so rather than blaming the network.
    """
    if local_remote_dir is None:
        remote, protocol = "origin", []
    else:
        # A FILESYSTEM PATH, so it is checked against the path alphabet: this
        # is an absolute path on the operator's machine, and on Windows that
        # is `D:\a\_temp\...` — a drive colon and backslashes, which the
        # branch-and-repository alphabet has no reason to admit and no reason
        # to refuse a path for lacking. A leading `-` is still refused.
        remote = checked_value(
            "--local-remote-dir",
            str(local_remote_dir.expanduser().resolve()
                / f"{repo_basename(repository)}.git"),
            SAFE_PATH_RE)
        protocol = FILE_PROTOCOL
    fetched = True
    try:
        run(["git", *protocol, "fetch", "-q", remote,
             "+refs/heads/*:refs/remotes/origin/*"], cwd=submodule)
    except CommandFailed as exc:
        fetched = False
        print(f"  note: `git fetch {remote}` in {submodule.name} exited "
              f"{exc.code}; answering from the remote-tracking refs this "
              "checkout already has", file=sys.stderr)
    if on_a_remote_branch(submodule, commit):
        return
    stale = ("" if fetched else
             " The fetch above FAILED, so this was answered from stale "
             "remote-tracking refs; fix the network or the credential and "
             "re-run before believing it.")
    if object_present(submodule, commit):
        raise Refusal(
            "bump-leg-commit-local-only",
            f"{commit} is in the leg's own object store but is reachable "
            f"from no branch of {repository}",
            "Remediation: somebody committed inside the leg's mount and "
            "never pushed it. Push it to a branch of the leg and re-run — a "
            "pin the rest of the world cannot fetch is a root the rest of "
            "the world cannot bootstrap." + stale)
    raise Refusal(
        "bump-leg-commit-not-on-remote",
        f"{repository} has no branch containing {commit}",
        "Remediation: check the commit — it belongs to the LEG, not to the "
        f"assembly root — and that it has been pushed. `git ls-remote "
        f"{repository}` lists what the remote actually has." + stale)


# ---------------------------------------------------------------------------
# the commit
# ---------------------------------------------------------------------------


def run_validator(root: Path, script: str) -> tuple[int, str]:
    """The ROOT's own copy of a validator, its output captured for a refusal."""
    if not (root / script).is_file():
        return 0, f"  {script} is absent; SKIPPED\n"
    # THE CHILD IS TOLD WHAT TO WRITE AND IS READ BACK AS THAT (#254). A child
    # takes its stdout configuration from its environment, and this process's
    # own `reconfigure` (#214) does not reach it: under a cp1252 stdout the
    # validator raised `UnicodeEncodeError` on a display name such as `日本`
    # and this refused a bump the pins had no quarrel with. UTF-8 holds every
    # name, and the pipe is read as UTF-8 to match. #217 read it with the
    # locale's codec because the child wrote in the locale's codec; it is now
    # told what to write. `replace` stays, so a validator that wrote bytes
    # UTF-8 cannot read (through `sys.stdout.buffer`, say) is still a refusal
    # and not a traceback on its way to printing the validator's words.
    proc = subprocess.run([sys.executable, script], cwd=str(root),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False,
                          env=captured_child_environment())
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def commit_once(root: Path, message: str, paths: list[str],
                trailers: list[str] = ()) -> str:
    """ONE commit, with EXPLICIT PATHSPECS.

    `git commit -- <paths>` commits the working-tree state of exactly those
    paths and nothing the index happens to be carrying. That matters wherever
    more than one session shares a checkout: a bare `git commit` takes
    whatever anyone staged, which is how a one-line bookkeeping commit swept
    nine unrelated renames into itself in the xFactory aggregation on
    2026-07-29.

    The identity is ENV-BASED and falls back rather than being configured: a
    bump that failed on a machine with no `user.email` would fail for a reason
    that has nothing to do with the leg being advanced, and writing
    `git config --global` to fix that is this tool editing a machine it was
    only asked to read.

    `trailers` ARE THE LINES THE COMMIT ENDS WITH, in the order `--trailer`
    named them (#111 gave `update-shape.py apply` and `scripts/family.py
    bump` this; #150 is this tool's turn, the third pin-moving tool the
    gap left behind). Passed none, `commit_trailers` hands the message back
    unchanged and adds no argument, which is what keeps a plain bump's
    message and `git commit` argv byte-identical to every one before it. See
    `shape_materialize.commit_trailers` for the two ways git is asked.
    """
    run(["git", "add", "--", *paths], cwd=root)
    message, trailer_args = commit_trailers(message, trailers)
    args = ["git", "commit", "-q", "-F", "-", *trailer_args, "--", *paths]
    check_program(args)
    env = dict(os.environ)
    for key, fallback in (("GIT_AUTHOR_NAME", "openRepoShape bump-leg"),
                          ("GIT_COMMITTER_NAME", "openRepoShape bump-leg"),
                          ("GIT_AUTHOR_EMAIL", "bump-leg@openreposhape.invalid"),
                          ("GIT_COMMITTER_EMAIL",
                           "bump-leg@openreposhape.invalid")):
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


def current_branch(root: Path) -> str | None:
    proc = subprocess.run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
                          cwd=str(root), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False)
    return proc.stdout.strip() or None


# ---------------------------------------------------------------------------


def _checked_target_commit(raw: str) -> str:
    """`--to`, lower-cased, refused unless it is exactly 40 hex.

    Split from `cmd_bump` for #136: a tag can be moved and an abbreviated
    oid can become ambiguous, so this is checked before anything else reads
    `--to`.
    """
    commit = checked_value("--to", raw).lower()
    if not COMMIT_RE.match(commit):
        raise Refusal(
            "bump-leg-target-not-a-commit",
            f"--to {raw!r} is not a 40-hex commit",
            "Remediation: pass the full 40 characters. A tag can be moved and "
            "an abbreviated oid can become ambiguous; a pin is a whole commit "
            "or it is nothing.")
    return commit


def _ensure_root_clean(root: Path) -> None:
    """Refuse when the root has uncommitted TRACKED changes.

    Split from `cmd_bump` for #136.
    """
    # THE ROOT MUST BE CLEAN. Tracked changes only: an untracked scratch file
    # cannot reach a commit made with explicit pathspecs, and refusing one
    # would be this tool having an opinion about somebody's working
    # directory. The one kind that could reach it, a workflow file the rewrite
    # would pick up, is never picked up: `plan_workflows` rewrites tracked
    # files only and refuses an untracked one by name (#207). Untracked
    # content INSIDE the leg is ignored for the same reason; the leg sitting
    # at a different commit than the gitlink is NOT, because that is a
    # half-finished bump and this one would land on top of it.
    dirt = git_out(["status", "--porcelain", "--untracked-files=no",
                    "--ignore-submodules=untracked"], cwd=root)
    if dirt:
        raise Refusal(
            "bump-leg-root-dirty",
            f"{root} has uncommitted changes:\n"
            + "\n".join(f"    {line}" for line in dirt.splitlines()),
            "Remediation: commit or stash them first. A lockstep commit that "
            "cannot be read as exactly one change is the thing the rule "
            "exists to keep readable.")


def _branch_to_bump_from(root: Path, project: "Project", role: str,
                         commit: str, *, dry_run: bool = False) -> str:
    """The branch on which the bump commits, refused if there is none or
    it is the project's own tracking branch.

    Split from `cmd_bump` for #136: these organisations are pull-request
    only, so a bump is refused before it ever makes a commit whose only
    next step would be a push to the default branch. A `--dry-run` makes no
    commit, so on the tracking branch it is let through and ends by naming
    the branch the real run needs (#477); a root on no branch at all is
    refused either way.
    """
    branch = current_branch(root)
    if branch is None:
        raise Refusal(
            "bump-leg-root-detached",
            f"{root} is not on a branch, so there is no branch to push and "
            "open a pull request from",
            "Remediation: `git -C " + str(root) + " switch -c bump/"
            + f"{role}-{commit[:12]}` and re-run.")
    if branch == project.tracking and not dry_run:
        raise Refusal(
            "bump-leg-on-tracking-branch",
            f"{root} is on {branch!r}, which {MANIFEST} declares as this "
            "project's tracking branch",
            "Remediation: these organisations are pull-request only, so this "
            "will not make a commit whose only next step is a push to the "
            "default branch. Run:\n    git -C " + str(root)
            + f" switch -c bump/{role}-{commit[:12]}\nand re-run.")
    return branch


def _initialized_submodule(root: Path, path: str) -> Path:
    """The leg's checkout, refused if it was never `git submodule update
    --init`ed.

    Split from `cmd_bump` for #136.
    """
    submodule = root / path
    if not (submodule / ".git").exists():
        raise Refusal(
            "bump-leg-uninitialized",
            f"{path} is not an initialized submodule checkout, so the new "
            "commit cannot be resolved or digested",
            "Remediation: `make bootstrap` in the root, which resolves a "
            "credential for a private leg first, or `git submodule update "
            "--init " + path + "`.")
    return submodule


def _recorded_leg_commit(root: Path, path: str) -> str:
    """The commit currently recorded at the leg's gitlink, refused if there
    is none to advance.

    Split from `cmd_bump` for #136.
    """
    # THE COMMIT BEING REPLACED, read from the INDEX first (`recorded_gitlink`
    # does), because the index is what the next commit will record. Its
    # absence is refused rather than treated as "nothing to roll back to": a
    # declared leg the root records no `160000` entry for is the same defect
    # `validate-pins.py` names `pin-gitlink-absent`, and a bump is not the
    # tool that invents a first gitlink.
    was = recorded_gitlink(root, path)
    if was is None:
        raise Refusal(
            "bump-leg-gitlink-absent",
            f"no gitlink (mode 160000) is recorded at {path!r}, so there is "
            "no pin to advance",
            "Remediation: the leg is declared in project.yaml but this "
            "repository does not record it as a submodule. `git submodule "
            "add` mounted it once; restore that commit, or re-scaffold. "
            "`validate-pins.py` refuses on the same fact.")
    return was


def _leg_pin_path(root: Path, pin_rel: str) -> Path:
    """The leg's `contracts/<role>-pin.yaml`, refused if it does not exist or
    cannot be reached (#383).

    Split from `cmd_bump` for #136.
    """
    pin_path = root / pin_rel
    try:
        present = _is_a(pin_path, stat.S_ISREG)
    except OSError as exc:
        # `contracts/` this user cannot search: the `stat` is refused, which
        # is not an absent file (#383)
        raise _pin_unopened_refusal(root, pin_path, exc) from exc
    if not present:
        raise Refusal(
            "bump-leg-pin-missing",
            f"{pin_rel} does not exist, so half of the invariant has nothing "
            "to be written into",
            "Remediation: `validate-pins.py` refuses the same way. Restore "
            "the file from the project's history, or re-scaffold it.")
    return pin_path


def _print_workflow_plan(root: Path, plans: list) -> None:
    """Print how many workflow `@<sha>` references this bump will move.

    Split from `cmd_bump` for #136.
    """
    if plans:
        moved = sum(count for _, _, count in plans)
        print(f"workflows    {moved} reference(s) in {len(plans)} file(s):")
        for wf_path, _, count in plans:
            # POSIX, on every platform: this is a path in the repository, and
            # `str()` of a relative Path on Windows spells it with backslashes
            # — a path the reader cannot paste back into `git`.
            print(f"  {wf_path.relative_to(root).as_posix()}  "
                  f"{count} reference(s)")
    else:
        print("workflows    no `@<sha>` reference names this leg")


def _print_trailers(trailers: list[str]) -> None:
    """Print the `--trailer` lines this run would end the commit with, read
    off verbatim and in the order `--trailer` was given — the same order
    `commit_trailers` appends them in.

    Printed after the `nothing to do` exit, so it is never shown for a bump
    that will not write anything, and before the `--dry-run` return, so a
    dry run shows it beside the `old -> new` line already printed above,
    exactly like a real run shows the same thing right before it writes them
    (#150).
    """
    if trailers:
        print(f"trailers     {len(trailers)} to append, in order:")
        for line in trailers:
            print(f"  {line}")
    else:
        print("trailers     none")


#: What a report says when the rollback put every byte back, and what it says
#: when it did not. ONE SPELLING EACH: a refusal written before the rollback
#: ran (`bump-leg-validators-red`) carries `ROLLED_BACK`, and the handler
#: replaces exactly that sentence when the rollback did not earn it.
ROLLED_BACK = ("Every byte this command wrote has been rolled back — the "
               "pin, the workflow files, the leg's checkout and the index — "
               "and the tree is exactly as it was.")
NOT_ROLLED_BACK = ("THE ROLLBACK WAS NOT COMPLETE: what it could not put "
                   "back is named above, so read `git status` before "
                   "anything else.")


def _restore_file(target: Path, original: bytes) -> None:
    """Write `original` back, but only over a file that no longer holds it.

    A write that never opened the file — a read-only attribute, a permission
    the operator does not have — changed nothing, and writing the same bytes
    back would meet the same refusal and report a rollback failure for a file
    that was never touched.
    """
    if target.read_bytes() != original:
        target.write_bytes(original)


class LegNotAsFound(Exception):
    """The leg's `git status` does not read as it did before the bump."""


def _leg_status(submodule: Path) -> bytes:
    """The leg's `git status`, untracked files one by one, as raw bytes.

    `-z` and bytes, so nothing strips the leading space of ` M <path>`, and
    `--untracked-files=all`, so a file written into a directory that already
    held an untracked file of the operator's is a line of its own.
    """
    return git_out(["status", "--porcelain", "-z", "--untracked-files=all"],
                   cwd=submodule, binary=True)


def _put_back(what: str, undo) -> bool:
    """Attempt ONE step of a rollback; say so, and carry on, if it fails.

    Each step is attempted whatever the steps before it did, and none of them
    raises: a rollback that stopped at the first byte it could not restore
    would leave the leg moved and the index staged behind a file the operator
    cannot write. Returns whether the step succeeded.

    AN INTERRUPT IS CAUGHT HERE TOO. A second Ctrl-C while the rollback checks
    a large leg out again is the likeliest next keystroke, and let through it
    skipped every step after the one it landed in, leaving the new pin, the
    new workflow and the new gitlink staged with nothing naming the index.
    Caught per step rather than by a signal handler, which a library function
    has no business installing: the step it landed in is named, the steps
    after it (a file, the index: short ones) still run, and the first failure
    is still the one re-raised.
    """
    try:
        undo()
    except CommandFailed as exc:
        print(exc.loudly("rolling the bump back"), file=sys.stderr)
    except KeyboardInterrupt:
        print(f"REFUSED rolling the bump back. {what} could not be put back: "
              "interrupted", file=sys.stderr)
    except LegNotAsFound as exc:
        print(f"REFUSED rolling the bump back. {what} could not be put back: "
              f"{exc}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 - nothing may escape a rollback
        print(f"REFUSED rolling the bump back. {what} could not be put back: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
    else:
        return True
    return False


def _restore_leg_if_moved(submodule: Path, placement: str | None,
                          was: str, status: bytes) -> None:
    """Put the leg back where it stood, if it no longer stands there, and
    fail the step if its `git status` no longer reads as `status` did.

    DECIDED FROM THE LEG, NOT FROM WHETHER THE CHECKOUT RETURNED. git moves
    the leg's HEAD before it runs `post-checkout`, so a hook that exits
    non-zero (git-lfs's does, with no `git-lfs` on PATH) fails a checkout
    that has already moved the leg, and an interrupt can land while the
    checkout is still being waited on after git has moved it. Either way the
    leg is on the new commit and the checkout never returned. A leg that
    still stands where it stood, on the same branch at the same commit, is
    not checked out again, so a checkout that never moved it does not go
    through a refusing hook a second time.

    AND FROM THE LEG'S `git status`, NOT ITS BRANCH AND HEAD ALONE. git
    writes the new commit's files before it moves the leg's index and HEAD,
    so a checkout cut off between the two (a terminal's Ctrl-C reaches git
    and this tool together) leaves the leg on its branch at its commit with
    those files in it. Nothing is removed here: an untracked file of the
    operator's own is allowed in the leg, and only the operator can tell it
    from one the checkout wrote, so the step fails and says where to look.
    """
    if not (leg_placement(submodule) == placement
            and git_out(["rev-parse", "HEAD"],
                        cwd=submodule).lower() == was.lower()):
        restore_leg(submodule, placement, was)
    if _leg_status(submodule) != status:
        raise LegNotAsFound(
            "its `git status` no longer reads as it did before the bump, "
            "which is what a checkout cut off part way leaves behind. Read "
            f"`git -C {submodule} status` before anything else, and remove "
            "only what you did not put there yourself.")


def _roll_back(root: Path, submodule: Path, placement: str | None, was: str,
               status: bytes, staged: list[str],
               written: dict[Path, bytes]) -> bool:
    """Put back every byte `_apply_rewrite` changed: the files it wrote, the
    leg's checkout (when the leg no longer stands where it stood, and checked
    against the leg's `git status` from before the bump) and the index, in
    that order. Returns whether ALL of it went back.

    THE ROLLBACK NEVER RAISES OVER THE FAILURE THAT STARTED IT. Whatever it
    cannot put back is printed and the original failure is still the one the
    caller re-raises: a rollback failure that replaced the validator's finding
    would leave a person with a changed tree and no idea what the gate
    objected to.
    """
    steps = [(target.relative_to(root).as_posix(),
              partial(_restore_file, target, original))
             for target, original in written.items()]
    steps.append((f"the checkout of {submodule.name}/",
                  partial(_restore_leg_if_moved, submodule, placement, was,
                          status)))
    steps.append(("the index", partial(
        run, ["git", "reset", "-q", "HEAD", "--", *staged], cwd=root)))
    return all([_put_back(what, undo) for what, undo in steps])


def _head_guard(root: Path, head_before: str | None) -> str | None:
    """None when the rollback is to run; otherwise the sentence the report
    carries instead, saying why it must not.

    THE ROOT'S HEAD DECIDES, NOT WHICH STATEMENT RAISED. Until the commit is
    asked for (`head_before` is None) nothing can have been committed. Once
    it has been, an unmoved HEAD means git refused the commit, and every
    byte goes back as for any other failure. A moved HEAD means the bump IS
    a commit and the failure came after it (the `git rev-parse` that reads
    it back, an interrupt); putting the files, the leg and the index back
    under that commit would leave a tree that contradicts it. A HEAD that
    cannot be read is treated the same way, since a rollback over a commit
    that landed is the worse of the two mistakes.
    """
    if head_before is None:
        return None
    try:
        head = git_out(["rev-parse", "HEAD"], cwd=root).lower()
    except BaseException as exc:  # noqa: BLE001 - an interrupt included
        return ("Whether the commit landed could not be read "
                f"({type(exc).__name__}), so nothing was rolled back: read "
                "`git log -1` and `git status` before anything else.")
    if head == head_before:
        return None
    return (f"The bump was committed as {head[:12]} before this failed, so "
            "nothing was rolled back: that commit holds the whole bump, and "
            "`git log -1` shows it.")


def _with_verdict(detail: str, verdict: str) -> str:
    """A refusal's `detail`, saying what the rollback actually did: in place
    of the `ROLLED_BACK` it was written with, or else after it."""
    if ROLLED_BACK in detail:
        return detail.replace(ROLLED_BACK, verdict, 1)
    return f"{detail}\n{verdict}"


def _apply_rewrite(root: Path, submodule: Path, commit: str, was: str,
                   pin_path: Path, pin_text: str, digest: str, plans: list,
                   staged: list[str], message: str,
                   trailers: list[str]) -> str:
    """Rewrite the pin and every workflow file, stage them, validate them and
    commit them — or roll every byte back and re-raise. Returns the commit.

    Split from `cmd_bump` for #136: the whole rewrite-or-roll-back sequence
    is one question, asked once, instead of being the tail half of a
    function that also does everything before it. Every git command and
    its order are unchanged: the leg is checked out detached BEFORE any
    file is written, the rewritten files are staged AFTER they are all
    written and BEFORE the validators run (`recorded_gitlink` reads the
    INDEX), and a failure of ANY kind rolls every byte back before it is
    re-raised, never swallowed (#253: the handler named `Refusal` and
    `CommandFailed` alone, so a `PermissionError` on a workflow file, a
    `UnicodeError` from the validator echo or an interrupt left the pin
    rewritten, the leg on the new commit and the index changed).

    THE COMMIT IS INSIDE IT TOO, as the last statement. A commit git refuses
    (a signing key that cannot sign, a `commit-msg` hook) is a failure after
    the leg moved like any other; made after this returned, it left the bump
    staged and the leg on the new commit, and the operator's next act, the
    same command once the signer was fixed, was refused as a dirty root. One
    `git rev-parse HEAD` is read just before it, and `_head_guard` compares
    the root's HEAD with that after any failure: a failure after the commit
    landed is not rolled back.

    WHAT IT REPORTS never claims more than the rollback did: every byte back
    (`ROLLED_BACK`), THE ROLLBACK WAS NOT COMPLETE, or the commit landed and
    nothing was rolled back. A `Refusal` carries that in its own text. An
    `OSError` or a `UnicodeError` that nothing committed leaves as a
    `Refusal` naming it — the repository's own answer to a write that could
    not happen, `update-shape.py`'s `update-readme-unwritable`, never a
    traceback. A `CommandFailed`, an interrupt and anything else leave as
    themselves, after one line on stderr saying it, because neither
    `main()`'s report of a git command nor a traceback says what became of
    the tree.
    """
    written: dict[Path, bytes] = {}
    placement = leg_placement(submodule)
    # Read BEFORE the checkout, as `placement` is: the rollback compares the
    # leg with it (`_restore_leg_if_moved`).
    status = _leg_status(submodule)
    head_before: str | None = None
    try:
        # A BUMP LEAVES THE LEG AT THE COMMIT, detached, and does not move any
        # branch. `bootstrap.py` is what places a leg ON its tracking branch —
        # at the pin — and a bump that also moved `main` in the leg would be
        # this tool pushing somebody's branch around from inside a submodule.
        run(["git", "checkout", "-q", "--detach", commit], cwd=submodule)
        for target, data in [(pin_path, rewrite_pin(pin_text, commit, digest))
                             ] + [(wf_path, text) for wf_path, text, _ in plans]:
            written[target] = target.read_bytes()
            # LF, on every platform. `.github/workflows/validate.yml` is
            # a digest-pinned COPY of the shape's file: `shape-pin.yaml`
            # records a sha256 of the bytes the materializer wrote - and this
            # is the lockstep rewrite the README documents: gitlink, pin and
            # every `@<sha>` in one commit. A CRLF rewrite on Windows would
            # change every line of the file it just re-pinned and the project's
            # own `validate-pins.py` would go red on the commit that fixed it.
            write_lf(target, data)

        # STAGED BEFORE THE VALIDATORS RUN, because `recorded_gitlink` asks
        # the INDEX first: the gitlink the next commit will record is the one
        # the check is about, and an unstaged bump would be reported against
        # the commit it is replacing.
        run(["git", "add", "--", *staged], cwd=root)

        print("\nthe project's own validators")
        for script in VALIDATORS:
            code, output = run_validator(root, script)
            sys.stdout.write(output)
            if code != 0:
                # `ROLLED_BACK` is written before the rollback has run, and
                # the handler below replaces it when the rollback did not
                # earn it.
                raise Refusal(
                    "bump-leg-validators-red",
                    f"{script} exited {code} after the rewrite. "
                    f"{ROLLED_BACK}\n--- its output ---\n"
                    + output.rstrip() + "\n--- end output ---",
                    "Remediation: read the finding above. A tool that left a "
                    "project red would have moved the cost from this command "
                    "to somebody else's pull request.")

        head_before = git_out(["rev-parse", "HEAD"], cwd=root).lower()
        return commit_once(root, message, staged, trailers=trailers)
    except BaseException as failure:
        # `BaseException`, NOT `Exception`: an interrupt during the checkout
        # or the validators is the failure a person causes on purpose, and it
        # leaves the same half-applied bump as any other.
        landed = _head_guard(root, head_before)
        if landed is None:
            verdict = (ROLLED_BACK if _roll_back(root, submodule, placement,
                                                 was, status, staged, written)
                       else NOT_ROLLED_BACK)
        else:
            verdict = landed
        if isinstance(failure, Refusal):
            raise Refusal(failure.code, _with_verdict(failure.detail, verdict),
                          failure.remediation) from failure
        if landed is None and isinstance(failure, (OSError, UnicodeError)):
            raise Refusal(
                "bump-leg-rewrite-failed",
                f"{type(failure).__name__} while the bump was being applied: "
                f"{failure}. {verdict}",
                "Remediation: fix what the exception names — a file this "
                "command cannot write, a stdout that cannot encode what a "
                "validator printed — and run the same command again. "
                "Nothing was committed.") from failure
        lead = ("The command below failed"
                if isinstance(failure, CommandFailed)
                else type(failure).__name__)
        print(f"{lead} while the bump was being applied. {verdict}",
              file=sys.stderr)
        raise


def cmd_bump(args) -> int:
    project = Project.open(args.root)
    root = project.root
    role = checked_value("--leg", args.leg)
    leg = project.leg(role)
    repository = checked_value("the leg's repository",
                               str(leg.get("repository") or ""))
    path = checked_value("the leg's path", str(leg.get("path") or ""))
    commit = _checked_target_commit(args.to)

    _ensure_root_clean(root)
    branch = _branch_to_bump_from(root, project, role, commit,
                                  dry_run=args.dry_run)
    submodule = _initialized_submodule(root, path)
    was = _recorded_leg_commit(root, path)

    print(f"project      {project.display_name} ({project.data.get('id')})")
    print(f"leg          {role:<8} {repository} at {path}/")
    fetch_leg(submodule, repository, commit, args.local_remote_dir)
    digest = tree_digest(submodule, commit)
    pin_rel = f"contracts/{role}-pin.yaml"
    pin_path = _leg_pin_path(root, pin_rel)
    pin_text = _leg_pin_text(root, pin_path)
    plans = plan_workflows(root, repository, commit)

    print(f"commit       {was[:12]} -> {commit[:12]}")
    print(f"tree         {digest[:12]}… ({digest})")
    print(f"pin          {pin_rel}")
    _print_workflow_plan(root, plans)

    if was == commit and not plans and rewrite_pin(pin_text, commit,
                                                   digest) == pin_text:
        print(f"\nnothing to do: {repository} is already pinned at "
              f"{commit[:12]} and every fact agrees.")
        return 1

    _print_trailers(args.trailer)

    if args.dry_run:
        print("\n--dry-run: nothing was changed. The leg's object store was "
              "fetched into, which is how the digest above was computed; the "
              "working tree, the pin, the workflows and the index are "
              "untouched.")
        if branch == project.tracking:
            # LAST, after everything a dry run on a branch prints, so that
            # line is the whole of the difference between the two (#477).
            print(f"\nthe real run needs a branch: {root} is on {branch!r}, "
                  "the tracking branch. Create one first with: git -C "
                  f"{root} switch -c bump/{role}-{commit[:12]}")
        return 0

    # ---- the rewrite and the commit, remembered byte for byte so a failure
    # anywhere up to the commit undoes them
    staged: list[str] = [path, pin_rel] + [
        wf_path.relative_to(root).as_posix() for wf_path, _, _ in plans]
    body = (
        f"{was[:12]} -> {commit[:12]}, tree {digest}.\n\n"
        + (f"{sum(count for _, _, count in plans)} workflow `@<sha>` "
           f"reference(s) in {len(plans)} file(s) moved with it.\n\n"
           if plans else
           "No workflow reference names this leg, so the gitlink and the pin "
           "file are the whole of it.\n\n")
        + f"The gitlink at {path}, `commit:` and `digests.tree_sha256` in "
          f"{pin_rel}, and every workflow reference to {repository} move in "
          "ONE commit because `scripts/validate-pins.py` refuses when they "
          "disagree — a gitlink advanced alone is red on the next pull "
          "request, and on somebody else's change.\n\nWritten by "
          "openRepoShape's `scripts/bump-leg.py`; the digest is recomputed "
          "from the leg's own objects, not adjusted.\n")
    head = _apply_rewrite(
        root, submodule, commit, was, pin_path, pin_text, digest, plans,
        staged,
        f"Bump {role} leg to {commit[:12]} in {project.display_name}\n\n"
        + body, args.trailer)
    print(f"\n  committed {head[:12]}: " + ", ".join(staged))
    print(f"  {path}/ is left DETACHED at {commit[:12]}; `make bootstrap` in "
          "the root re-places it on its tracking branch AT the new pin")
    print(f"\nNEXT  git -C {root} push -u origin {branch}")
    print(f"      then open a pull request against {project.tracking}; never "
          "push the bump to the default branch directly")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bump-leg.py", description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", required=True, metavar="PATH",
                        help="the project's ASSEMBLY ROOT — the repository "
                             "carrying project.yaml")
    parser.add_argument("--leg", required=True, metavar="{spec,code}",
                        help="which leg to advance, by the `role:` its own "
                             "project.yaml declares")
    parser.add_argument("--to", required=True, metavar="COMMIT",
                        help="the 40-hex commit to move the gitlink, the pin "
                             "and every workflow reference to, together")
    parser.add_argument("--trailer", action="append", metavar='"KEY: VALUE"',
                        default=[], type=trailer_line,
                        help="append this `<Key>: <value>` line to the "
                             "commit this writes; repeatable, kept in the "
                             "order given")
    parser.add_argument("--local-remote-dir", type=Path, default=None,
                        help="resolve the leg's remote to a bare repository "
                             "here instead of its origin (the TEST path; no "
                             "network)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would move and change nothing")
    return parser


def main(argv: list[str] | None = None) -> int:
    # FIRST, so that every `print` after it -- `--help` included -- escapes
    # a name stdout cannot encode rather than raising on it (#214).
    escape_what_stdout_cannot_encode()
    args = build_parser().parse_args(argv)
    try:
        return cmd_bump(args)
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except CommandFailed as exc:
        print(exc.loudly("advancing a leg"), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
