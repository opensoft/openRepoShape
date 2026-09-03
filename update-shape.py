#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Re-sync a project's COPIED shape files with openRepoShape, and re-pin.

    ./update-shape.py check --root <assembly-root>
    ./update-shape.py apply --root <assembly-root> --at <commit> --yes \\
        [--accept-local <path>] [--branch shape/update-<sha>]

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
    header forbids.
  * A file changed on BOTH sides is refused outright. Two edits to one file is
    a merge, and a merge is a human's judgement, not a byte copy.
  * A copy that is not VERBATIM at the pinned commit — `adopt-project.py`
    appends a `CONTRACTS_DIR` block to an adopted Makefile — is treated as a
    conflict the moment upstream touches it, because copying the target bytes
    over it would delete that block without saying so.
  * Nothing is left red: the root's OWN `validate-pins.py` and
    `validate-manifest.py` run after the rewrite, and every byte is rolled
    back if either refuses.

ONLY THE PIN'S OWN ROWS ARE CONSIDERED. The set of shape files is read from
`contracts/shape-pin.yaml`, never re-derived from this repository's copy
lists. An in-place adoption collides on `Makefile`, `README.md` and
`.gitignore` — the shape's copies land under `shape/` and a human merges them,
usually deleting the `shape/` copy and its pin row (MedxEHR did exactly that).
A file with no row is not a shape copy and is invisible here; re-deriving the
list would resurrect a file the project deliberately merged away.

EXIT CODES
    check   0  the pin names the target and no copied file differs
            1  updates are available, or drift a human must resolve
            2  a REFUSAL: no pin, an unresolvable upstream, an unreadable root
    apply   0  applied (or there was nothing to do)
            2  a REFUSAL, including a validator that went red (rolled back)

STANDARD LIBRARY ONLY, like everything else shipped here.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SHAPE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SHAPE_ROOT / "scripts"))
from repo_shape import (  # noqa: E402
    COMMIT_RE, TREE_DIGEST_DEFINITION, Refusal, checked_value, die,
    file_sha256, git_out, load_yaml, tree_digest,
)
from shape_materialize import (  # noqa: E402
    COPIED_FROM_SHAPE, COPIED_VERBATIM, SHAPE_REPOSITORY, CommandFailed,
    check_program, run,
)

#: `owner/repo`, the only remote spelling `--upstream` accepts.
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

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

#: States a pinned row can be in. The first four are the vocabulary the task
#: of updating a project is actually about; the last three are the ways the
#: question cannot be asked, and each of them refuses rather than guessing.
UNCHANGED = "unchanged"
UPSTREAM_CHANGED = "upstream-changed"
LOCALLY_MODIFIED = "locally-modified"
BOTH = "both"
ALREADY_AT_TARGET = "already-at-target"
UPSTREAM_REMOVED = "upstream-removed"
UNMAPPED = "unmapped"
COPY_MISSING = "copy-missing"

#: Anything here is a merge or a decision, never a byte copy.
CONFLICTS = (BOTH, UPSTREAM_REMOVED, UNMAPPED, COPY_MISSING)
ORDER = (UPSTREAM_CHANGED, BOTH, LOCALLY_MODIFIED, ALREADY_AT_TARGET,
         UPSTREAM_REMOVED, UNMAPPED, COPY_MISSING, UNCHANGED)


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
    into a temporary directory, which is the one place this tool touches a
    network, and it refuses loudly rather than degrading to a guess.
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
    proc = subprocess.run(args, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        shutil.rmtree(temporary, ignore_errors=True)
        raise Refusal(
            "update-upstream-unresolvable",
            f"could not clone {url} (git exit {proc.returncode}): "
            f"{(proc.stderr or '').strip()}",
            "Remediation: this is the one step that needs a network. Clone "
            "the shape once by hand and pass `--upstream <path>` instead; "
            "everything after it is offline.")
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

    @property
    def is_conflict(self) -> bool:
        return self.state in CONFLICTS


def read_pin(root: Path) -> tuple[dict, list[Row]]:
    pin_path = root / "contracts" / "shape-pin.yaml"
    if not pin_path.is_file():
        raise Refusal(
            "update-pin-missing",
            f"{pin_path} does not exist, so there is no record of which files "
            "were copied out of openRepoShape or which revision they came "
            "from. Nothing can be re-synced against nothing.",
            "Remediation: this command updates a project that was scaffolded "
            "or adopted with this shape. A project without a shape pin is "
            "adopted with `adopt-project.py`, not updated.")
    pin = load_yaml(pin_path)
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
    rows: list[Row] = []
    for raw in pin.get("files") or []:
        if not isinstance(raw, dict) or not raw.get("path"):
            raise Refusal("update-pin-row",
                          f"{pin_path}: a `files:` row is not `path:`/`sha256:`")
        rows.append(Row(str(raw["path"]), str(raw.get("sha256") or "")))
    if not rows:
        raise Refusal(
            "update-pin-no-files",
            f"{pin_path}: no `files:` rows, so the pin asserts nothing about "
            "any copied file and there is nothing to re-sync")
    return pin, rows


def source_for(rel: str, upstream: Upstream, rev: str) -> str | None:
    """Where a pinned root path came from in the upstream tree.

    The materializer's own tables answer first. The two fallbacks exist for a
    pin written by a DIFFERENT openRepoShape than the one running this: the
    tables here describe today's copy lists, and a project pinned three
    revisions back may name a file those lists have since renamed. Each
    fallback is confirmed against the target tree before it is used, so a
    guess that is not there is reported as `unmapped` rather than acted on.
    """
    stripped = rel
    prefix = f"{COLLISION_DIR}/"
    if stripped.startswith(prefix):
        stripped = stripped[len(prefix):]
    known = COPY_SOURCE.get(stripped)
    candidates = [known] if known else []
    candidates += [f"templates/assembly-root/{stripped}", stripped]
    for candidate in candidates:
        if candidate and upstream.blob(rev, candidate) is not None:
            return candidate
    return known or None


def classify(root: Path, rows: list[Row], upstream: Upstream, pinned: str,
             target: str) -> None:
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
    """
    for row in rows:
        target_path = root / row.path
        if not target_path.is_file():
            row.state = COPY_MISSING
            row.detail = ("pinned but absent from the root; a human decides "
                          "whether it was deleted on purpose")
            continue
        source = source_for(row.path, upstream, target)
        row.source = source
        if source is None:
            row.state = UNMAPPED
            row.detail = ("no file in the upstream tree corresponds to this "
                          "pinned path")
            continue
        here = target_path.read_bytes()
        pinned_bytes = upstream.blob(pinned, source)
        target_bytes = upstream.blob(target, source)
        if target_bytes is None:
            row.state = UPSTREAM_REMOVED
            row.detail = (f"{source} is gone from the upstream at the target "
                          "commit; deleting a project's copy is a decision, "
                          "not a copy")
            continue
        row.target_bytes = target_bytes
        local_digest = file_sha256(target_path)
        locally_modified = local_digest != row.recorded
        upstream_changed = pinned_bytes is None or pinned_bytes != target_bytes
        verbatim_at_pin = (pinned_bytes is not None
                           and file_bytes_sha256(pinned_bytes) == row.recorded)

        if here == target_bytes:
            # Already holding the target's bytes. Only the row is stale, and
            # recomputing it hides nothing: these ARE the upstream's bytes.
            row.state = (ALREADY_AT_TARGET if locally_modified else UNCHANGED)
            row.digest = local_digest
            continue
        if locally_modified and upstream_changed:
            row.state = BOTH
            row.detail = "edited here AND upstream since the pin"
            continue
        if upstream_changed and not verbatim_at_pin:
            row.state = BOTH
            row.detail = (
                "upstream changed, but this copy is not a verbatim copy of "
                f"{source} at the pinned commit — an in-place adoption "
                "appends to it — so copying the target bytes would delete "
                "what was appended")
            continue
        if upstream_changed:
            row.state = UPSTREAM_CHANGED
            row.digest = file_bytes_sha256(target_bytes)
            continue
        if locally_modified:
            row.state = LOCALLY_MODIFIED
            row.detail = "edited in this project since the pin"
            row.digest = local_digest
            continue
        row.state = UNCHANGED


def file_bytes_sha256(data: bytes) -> str:
    """`file_sha256`'s answer for bytes that are not on disk yet."""
    return hashlib.sha256(data).hexdigest()


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
    """
    lines = text.splitlines()
    out: list[str] = []
    seen = {"commit": 0, "tree": 0, "files": 0}
    for index, line in enumerate(lines):
        if line.startswith("commit:"):
            seen["commit"] += 1
            out.append(f'commit: "{commit}"')
            continue
        if line.startswith("  tree_sha256:"):
            seen["tree"] += 1
            out.append(f'  tree_sha256: "{tree}"')
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
    return "\n".join(out) + "\n"


def rewrite_manifest(text: str, commit: str, tree: str) -> str:
    """The two fields `validate-manifest.py` checks, inside `shape:`.

    Scoped to the block on purpose: `commit:` and `tree_sha256:` are spelled
    the same way in every pin, and a whole-file replacement would move a leg's
    pin while claiming to move the shape's.
    """
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.rstrip() == "shape:":
            start = index
            break
    if start is None:
        raise Refusal(
            "update-manifest-no-shape",
            "project.yaml has no `shape:` block, so there is nothing to "
            "mirror the pin into",
            "Remediation: `validate-manifest.py` requires one; add it, or "
            "re-scaffold.")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.strip() and not line.startswith((" ", "\t")):
            end = index
            break
    seen = {"commit": 0, "tree": 0}
    for index in range(start + 1, end):
        stripped = lines[index].strip()
        if stripped.startswith("commit:"):
            seen["commit"] += 1
            lines[index] = f'  commit: "{commit}"'
        elif stripped.startswith("tree_sha256:"):
            seen["tree"] += 1
            lines[index] = f'    tree_sha256: "{tree}"'
    for key, count in seen.items():
        if count != 1:
            raise Refusal(
                "update-manifest-unrecognised",
                f"project.yaml's `shape:` block has {count} `{key}` line(s) "
                "where exactly one was expected",
                "Remediation: fix the block by hand this once; this tool will "
                "not guess at a manifest it does not recognise.")
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


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
            line = f"  {state:<{width}}  {row.path}"
            if row.detail:
                line += f"\n  {'':<{width}}  ({row.detail})"
            print(line)


def counted(rows: list[Row]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.state] = counts.get(row.state, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------


def prepare(args) -> tuple[Path, dict, list[Row], Upstream, str, str]:
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        raise Refusal("update-root-missing", f"{root} is not a directory")
    pin, rows = read_pin(root)
    pinned = str(pin["commit"]).lower()
    declared = str(pin.get("source_repository") or SHAPE_REPOSITORY)
    upstream = open_upstream(str(args.upstream or declared))
    upstream.repository = declared
    try:
        target = upstream.resolve(checked_value("--at", args.at)
                                  if args.at else None)
        # The pinned revision must be READABLE or the comparison is a guess.
        upstream.resolve(pinned)
        classify(root, rows, upstream, pinned, target)
    except Refusal:
        upstream.close()
        raise
    return root, pin, rows, upstream, pinned, target


def cmd_check(args) -> int:
    root, pin, rows, upstream, pinned, target = prepare(args)
    try:
        pin_tree = upstream.tree_sha256(pinned)
        target_tree = upstream.tree_sha256(target)
        report(root, upstream, pinned, target, pin_tree, target_tree, rows)
        counts = counted(rows)
        moved = [row for row in rows if row.state != UNCHANGED]
        print()
        print("  ".join(f"{state} {counts[state]}" for state in ORDER
                        if counts.get(state)))
        if not moved and pinned == target:
            print("nothing to do")
            return 0
        if not moved:
            print("no copied file differs; `apply` would move the pin alone")
        conflicts = [row for row in rows if row.is_conflict]
        local = [row for row in rows if row.state == LOCALLY_MODIFIED]
        if conflicts:
            print("REFUSAL AHEAD: `apply` will refuse while these are "
                  "unresolved — " + ", ".join(row.path for row in conflicts))
        accept = "".join(f" --accept-local {row.path}" for row in local)
        print(f"NEXT  python3 {Path(__file__).name} apply --root {root} "
              f"--upstream {upstream.label} --at {target} --yes{accept} "
              f"--branch shape/update-{target[:12]}")
        return 1
    finally:
        upstream.close()


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


def confirm(args, rows: list[Row], target: str) -> None:
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
    print(f"\nThis re-copies {len(changed)} file(s) from {target[:12]} and "
          f"re-pins this project onto it.")
    if input("Type yes to proceed: ").strip().lower() != "yes":
        raise Refusal("update-declined", "not answered 'yes'",
                      "Remediation: nothing was written. Re-run when ready.")


def run_validator(root: Path, script: str) -> int:
    if not (root / script).is_file():
        print(f"  {script} is absent; SKIPPED")
        return 0
    sys.stdout.flush()
    proc = subprocess.run([sys.executable, script], cwd=str(root), check=False)
    sys.stdout.flush()
    return proc.returncode


def commit_on_branch(root: Path, branch: str, paths: list[str], target: str,
                     upstream: Upstream, count: int) -> None:
    """A branch and ONE commit, with EXPLICIT PATHSPECS.

    `git commit -- <paths>` commits the working-tree state of exactly those
    paths and nothing the index happens to be carrying. That matters wherever
    more than one session shares a checkout: a bare `git commit` takes whatever
    anyone staged, which is how a one-line bookkeeping commit swept nine
    unrelated renames into itself in the xFactory aggregation on 2026-07-29.
    """
    checked_value("--branch", branch)
    run(["git", "checkout", "-q", "-b", branch], cwd=root)
    message = (
        f"Re-sync the shape copies to {upstream.repository} @ {target[:12]}\n\n"
        f"{count} copied file(s) re-copied from the upstream; "
        f"contracts/shape-pin.yaml and project.yaml's `shape:` block now "
        f"record {target}.\n\nWritten by update-shape.py; the copies are not "
        f"hand-edited and the digests are recomputed, not adjusted.\n")
    env = dict(os.environ)
    for key, fallback in (("GIT_AUTHOR_NAME", "openRepoShape update"),
                          ("GIT_COMMITTER_NAME", "openRepoShape update"),
                          ("GIT_AUTHOR_EMAIL", "update@openreposhape.invalid"),
                          ("GIT_COMMITTER_EMAIL", "update@openreposhape.invalid")):
        if not env.get(key):
            env[key] = fallback
    args = ["git", "commit", "-q", "-F", "-", "--", *paths]
    check_program(args)
    proc = subprocess.run(args, cwd=str(root), input=message,
                          capture_output=True, text=True, check=False, env=env)
    if proc.returncode != 0:
        raise CommandFailed(args, root, proc.returncode,
                            proc.stderr + proc.stdout)


def cmd_apply(args) -> int:
    root, pin, rows, upstream, pinned, target = prepare(args)
    written: dict[Path, bytes] = {}
    try:
        accepted = {str(path) for path in (args.accept_local or [])}
        stray = accepted - {row.path for row in rows}
        if stray:
            raise Refusal(
                "update-accept-local-unknown",
                f"--accept-local names {sorted(stray)}, which the shape pin "
                "does not carry a row for",
                "Remediation: only a pinned copy can be accepted; a file with "
                "no row is not a shape copy. Checked FIRST, before the drift "
                "refusal, so a mistyped path is reported as a mistyped path.")
        if all(row.state == UNCHANGED for row in rows) and pinned == target:
            print(f"nothing to do: every copied file matches "
                  f"{upstream.repository} @ {target[:12]}, which the pin "
                  "already names")
            return 0
        conflicts = [row for row in rows if row.is_conflict]
        if conflicts:
            raise Refusal(
                "update-conflict",
                "these files changed on BOTH sides, or cannot be compared, and "
                "a merge is a human's judgement rather than a byte copy:\n"
                + "\n".join(f"    {row.path}: {row.detail or row.state}"
                            for row in conflicts),
                "Remediation: merge each one by hand (the upstream bytes are "
                "`git show <target>:<source path>` in a shape clone), commit "
                "it, then re-run this with --accept-local on that path so the "
                "row is recomputed from what you merged.")
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
        confirm(args, rows, target)
        target_tree = upstream.tree_sha256(target)
        pin_path = root / "contracts" / "shape-pin.yaml"
        manifest_path = root / "project.yaml"

        def write(path: Path, data: bytes) -> None:
            written.setdefault(path, path.read_bytes())
            path.write_bytes(data)

        copied = [row for row in rows if row.state == UPSTREAM_CHANGED]
        for row in copied:
            write(root / row.path, row.target_bytes or b"")
            print(f"  copied   {row.path}")
        for row in rows:
            if row.state == LOCALLY_MODIFIED:
                print(f"  kept     {row.path} (local bytes; row recomputed "
                      "from them because --accept-local named it)")
            elif row.state == ALREADY_AT_TARGET:
                print(f"  kept     {row.path} (already the target's bytes; "
                      "the row was stale)")
        write(pin_path, rewrite_shape_pin(
            pin_path.read_text(encoding="utf-8"), target, target_tree, rows
        ).encode("utf-8"))
        write(manifest_path, rewrite_manifest(
            manifest_path.read_text(encoding="utf-8"), target, target_tree
        ).encode("utf-8"))
        print(f"  re-pinned contracts/shape-pin.yaml and project.yaml "
              f"{pinned[:12]} -> {target[:12]}")

        print("\nthe project's own validators")
        failed = [name for name in ("scripts/validate-pins.py",
                                    "scripts/validate-manifest.py")
                  if run_validator(root, name) != 0]
        if failed:
            raise Refusal(
                "update-validators-red",
                "after the rewrite, " + " and ".join(failed) + " refused. "
                "Every byte this command wrote has been rolled back; the tree "
                "is exactly as it was.",
                "Remediation: read the finding above. A tool that left a "
                "project red would have moved the cost from this command to "
                "somebody else's pull request.")

        paths = sorted({row.path for row in copied}
                       | {"contracts/shape-pin.yaml", "project.yaml"})
        if args.branch:
            commit_on_branch(root, args.branch, paths, target, upstream,
                             len(copied))
            print(f"\n  committed on {args.branch}: " + ", ".join(paths))
            if args.push:
                run(["git", "push", "-q", "-u", "origin", args.branch], cwd=root)
                print(f"  pushed {args.branch} to origin")
            if args.pr:
                open_pull_request(root, args.branch, target, upstream)
        print()
        next_line(root, args, paths, target)
        return 0
    except Refusal:
        for path, original in written.items():
            path.write_bytes(original)
        raise
    except CommandFailed as exc:
        print(exc.loudly("committing the re-synced shape"), file=sys.stderr)
        return 2
    finally:
        upstream.close()


def open_pull_request(root: Path, branch: str, target: str,
                      upstream: Upstream) -> None:
    manifest = load_yaml(root / "project.yaml")
    legs = [leg for leg in (manifest or {}).get("legs") or []
            if isinstance(leg, dict) and leg.get("role") == "assembly"]
    repository = str(legs[0].get("repository")) if legs else ""
    base = str((manifest or {}).get("tracking_branch") or "main")
    if not repository:
        raise Refusal("update-pr-no-repository",
                      "project.yaml declares no assembly leg, so there is no "
                      "repository to open a pull request against")
    url = run(["gh", "pr", "create", "--repo", repository, "--base", base,
               "--head", branch, "--title",
               f"Re-sync the shape copies to {upstream.repository} @ "
               f"{target[:12]}",
               "--body",
               "Written by openRepoShape's `update-shape.py`: the copied "
               "shape files were re-copied from the upstream and "
               "`contracts/shape-pin.yaml` and `project.yaml` re-pinned onto "
               f"{target}. No copy was hand-edited and every digest was "
               "recomputed."], cwd=root)
    print(f"  pull request {url}")


def next_line(root: Path, args, paths: list[str], target: str) -> None:
    if args.branch and args.pr:
        print("NEXT  the pull request is open; ask a human to review and merge it")
        return
    if args.branch and args.push:
        print(f"NEXT  gh pr create --repo <org>/<Project> --base main --head "
              f"{args.branch}")
        return
    if args.branch:
        print(f"NEXT  git -C {root} push -u origin {args.branch} && gh pr "
              f"create --base main --head {args.branch}")
        return
    print(f"NEXT  git -C {root} checkout -b shape/update-{target[:12]} && git "
          f"-C {root} commit -m 'Re-sync the shape @ {target[:12]}' -- "
          + " ".join(paths))


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
    apply_parser.add_argument("--branch", default=None,
                              help="create this branch and commit the change "
                                   "to it, with explicit pathspecs")
    apply_parser.add_argument("--push", action="store_true",
                              help="push the branch to origin (needs --branch)")
    apply_parser.add_argument("--pr", action="store_true",
                              help="open a pull request with `gh` (needs "
                                   "--branch)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "check":
            return cmd_check(args)
        if (args.push or args.pr) and not args.branch:
            raise Refusal(
                "update-branch-required",
                "--push and --pr have nothing to act on without --branch",
                "Remediation: pass --branch <name>; this tool never pushes to "
                "a default branch and never commits without being asked to.")
        return cmd_apply(args)
    except Refusal as exc:
        return die(exc)
    except CommandFailed as exc:
        print(exc.loudly("updating the shape"), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
