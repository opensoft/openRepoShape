#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The one command an engineer runs after cloning a FAMILY holder.

    git clone --recurse-submodules <family-url>
    cd <Family>
    make bootstrap          # or: python3 scripts/bootstrap.py (python on Windows)

WHAT IT DOES, in order:

  (a) FETCHES EVERY MEMBER, RECURSIVELY, WITH A CREDENTIAL IF ONE IS THERE.
      A member is an assembly root that itself mounts two legs, so `--init
      --recursive` has to reach three repositories deep — and in most
      organisations all of them are PRIVATE. This resolves the same
      credentials the `validate` workflow does, in the same order: a GitHub
      App installation token (`SHAPE_LEGS_APP_TOKEN`, minted by whatever
      called this) first, then a `SHAPE_LEGS_TOKEN` PAT, then nothing at all.
      Whichever it finds is used ONLY through a `git -c
      url.<...>.insteadOf=<...>` rewrite for the duration of the one command,
      covering both the HTTPS and SSH spellings a submodule URL may carry. It
      is never written into `.git/config`, never persisted, never printed.

      With no credential this is a plain `git submodule update --init
      --recursive`, exactly as it was for a family whose members are public.
      A fetch that fails is REPORTED and does not stop the run: the members
      that did arrive are still worth bootstrapping, and a family that
      refused to do anything because one member is unreachable would be worse
      than one that says which.

      "every member and leg fetched" is said only where git exited 0 AND
      every row's member is checked out (#648). A member left NOT CHECKED
      OUT where no credential would check it out is said here instead, with
      why, and fails the run (c): this holder records no gitlink at the
      row's path (a gitlink recorded only in another case, #363), no
      section of `.gitmodules` gives that path (a holder whose HEAD lost the
      file, #611), or git exited 0 and checked nothing out there. Git exits
      0 over the second where a recursive clone ran first, and 128 (`No url
      found for submodule path`) in a plain clone, as it does for a missing
      credential, so what the holder records is the test, never git's
      words. The line names `validate-family.py`, which says what to commit.

  (b) RUNS EACH MEMBER'S OWN `make bootstrap`. Each member is a whole project
      and knows how to bootstrap itself — it puts its legs on their
      tracking branches at their pins where that loses no commit, and says
      why where it does not; its own validators; its own
      review-authority readout. This command does not reimplement any of
      that; it walks the members `family.yaml` names and calls theirs.
      `--members-make validate` runs `make validate` instead, which is what
      the family Makefile's `validate` target uses.

  (c) EXITS 0 unless a member's own command failed, or (a) left a member not
      checked out that no credential would check out. Any other member that
      is not checked out is REPORTED and skipped, not a failure: it is the
      state a missing credential leaves, and it is already reported in (a).
      Where (a) cannot start git, the run STOPS there, exit 2, refused
      `git-not-runnable` as `validate-family.py` refuses it (#694): each
      member's own bootstrap runs git too, so (b) would only say it again.

THE FAMILY CONFERS NOTHING and neither does this command. It fetches, it
delegates, and it says what it could not reach.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_shape import (  # noqa: E402
    PYTHON, Refusal, escape_unencodable_stdout, find_repo_root, git_out,
    load_yaml, recorded_gitlink, spelled,
)

MANIFEST = "family.yaml"
GITMODULES = ".gitmodules"
DEFAULT_MEMBERS_DIR = "members"

#: The two environment variables a leg/member credential may arrive in, in the
#: order the `validate` workflow resolves them. An App-minted installation
#: token is short-lived and per-owner; the PAT is the standing fallback.
CREDENTIAL_ENV = ("SHAPE_LEGS_APP_TOKEN", "SHAPE_LEGS_TOKEN")

#: Both spellings a submodule URL may carry, rewritten to an authenticated
#: HTTPS one for the duration of a single command.
REWRITE_TARGETS = ("https://github.com/", "git@github.com:")


def credential() -> tuple[str, str]:
    """`(source, token)`; `("none", "")` when the environment carries none."""
    for name in CREDENTIAL_ENV:
        value = (os.environ.get(name) or "").strip()
        if value:
            return name, value
    return "none", ""


def fetch_members(root: Path, rows: list[dict]) -> list[str]:
    """(a) `git submodule update --init --recursive`, authenticated or not.

    Returns a failure line for each of `rows` whose member it leaves not
    checked out where no credential would check it out (`unfetchable`), for
    the run to end FAILED on (#648); every member and leg is said to be
    fetched only where there is none and git exited 0. Raises the
    `git-not-runnable` refusal where git cannot be started (#694)."""
    source, token = credential()
    args = ["git"]
    if token:
        for target in REWRITE_TARGETS:
            args += ["-c", f"url.https://x-access-token:{token}@github.com/"
                           f".insteadOf={target}"]
    args += ["submodule", "update", "--init", "--recursive"]
    print(f"  credential source: {source}")
    sys.stdout.flush()
    try:
        proc = subprocess.run(args, cwd=str(root), capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              check=False)
    except OSError as exc:
        refusal = git_not_started(exc)
        if refusal is None:
            raise
        raise refusal from exc
    if proc.returncode != 0:
        # The token can appear in git's own error text (it is in the URL it
        # tried), so the output is scrubbed before it is printed.
        message = (proc.stderr + proc.stdout).strip()
        if token:
            message = message.replace(token, "<redacted>")
        print(f"  FETCH INCOMPLETE (git exit {proc.returncode}) using "
              f"credential source '{source}':\n{message}", file=sys.stderr)
        print("  If the members are PRIVATE, set SHAPE_LEGS_TOKEN (a "
              "fine-grained PAT with contents:read on them) or export an "
              "App-minted SHAPE_LEGS_APP_TOKEN, then re-run. What did arrive "
              "is bootstrapped below.", file=sys.stderr)
    left = unfetchable(root, rows, proc.returncode == 0)
    if left:
        print("  NOT CHECKED OUT, and not for want of a credential: "
              + ", ".join(f"{spelled(path)} ({why})" for _, path, why in left)
              + f". `{PYTHON} scripts/validate-family.py` names the cause and "
              "the commit that cures it.", file=sys.stderr)
    elif proc.returncode == 0:
        print("  every member and leg fetched")
    return [f"{spelled(row.get('project') or '?')} (not checked out)"
            for row, _, _ in left]


def git_not_started(exc: OSError) -> Refusal | None:
    """The `git-not-runnable` refusal for an `OSError` that says git could
    not be STARTED (#694), else `None`, and the error goes on as it did.

    Nothing caught one: `make bootstrap` with no git on PATH ended (a) in a
    `FileNotFoundError` traceback, exit 1, the code of `family bootstrap
    FAILED`, though nothing had failed. Git's is told by its NAME, as
    `validate-pins.py` tells it: a `filename` of `git`, or none at all on a
    `FileNotFoundError` or a `PermissionError`, as Windows raises them; one
    naming a directory is not git's. The code, and the remedy's first
    sentence, are `validate-family.py`'s."""
    nameless = exc.filename is None and isinstance(
        exc, (FileNotFoundError, PermissionError))
    if exc.filename != "git" and not nameless:
        return None
    return Refusal(
        "git-not-runnable",
        f"the members could not be fetched: git could not be run "
        f"({exc.strerror or exc})",
        "Remediation: put git on PATH and run this again. Step (a) fetches "
        "every member through git, and each member's own bootstrap places "
        "its legs through git too, so without it nothing here can be "
        "fetched or bootstrapped.")


def gitmodules_paths(root: Path) -> set[str]:
    """Every path a section of `.gitmodules` gives, read as git reads it:
    the work tree's file, the one `git submodule update` reads, which a
    fresh clone takes from HEAD. None where there is no such file, or one
    git cannot read: git has no url for any submodule then either."""
    if not os.path.lexists(root / GITMODULES):
        return set()
    try:
        listed = git_out(["config", "-z", "--file", GITMODULES, "--list"],
                         cwd=root, binary=True)
    except Refusal:
        return set()
    paths: set[str] = set()
    for record in listed.split(b"\0"):
        key, _, value = record.decode("utf-8",
                                      "surrogateescape").partition("\n")
        if key.startswith("submodule.") and key.endswith(".path"):
            paths.add(value)
    return paths


def unfetchable(root: Path, rows: list[dict],
                exited_0: bool) -> list[tuple[dict, str, str]]:
    """`(row, path, why)` for each row whose member (a) left NOT CHECKED OUT
    where no credential would check it out (#648), in row order.

    Asked of this holder's own records, never of git's words: a row at
    whose path the holder records no gitlink (`recorded_gitlink`,
    as `validate-family.py`'s `member-gitlink-absent` reads one), or whose
    gitlink no section of `.gitmodules` gives a path (as its
    `member-gitmodules-absent` reads HEAD's file, which is the work tree's
    in a clone); and, where git exited 0, any row at all, since git then
    lacked nothing a credential gives. Any other row not checked out is the
    missing credential's, and stays the skip it always was. A path two rows
    give is said once."""
    left: dict[str, dict] = {}
    for row in rows:
        if not (member_path(root, row) / ".git").exists():
            left.setdefault(row_path(row), row)
    if not left:
        return []
    given = gitmodules_paths(root)
    found: list[tuple[dict, str, str]] = []
    for path, row in left.items():
        if recorded_gitlink(root, path) is None:
            found.append((row, path, "no gitlink is recorded at that path"))
        elif path not in given:
            found.append((row, path, f"no section of {GITMODULES} gives that "
                                     "path"))
        elif exited_0:
            found.append((row, path, "git exited 0 and checked nothing out "
                                     "there"))
    return found


def members_of(root: Path) -> tuple[str, list[dict]]:
    manifest_path = root / MANIFEST
    if not manifest_path.is_file():
        raise Refusal(
            "family-manifest-missing",
            f"{manifest_path} does not exist, so there is no declaration of "
            "which members to bootstrap",
            "Remediation: this command bootstraps a FAMILY holder. A project "
            "runs its own `scripts/bootstrap.py` instead.")
    manifest = load_yaml(manifest_path)
    if not isinstance(manifest, dict):
        raise Refusal("family-manifest-unreadable",
                      f"{manifest_path}: not a mapping")
    name = str(manifest.get("name") or root.name)
    rows = [row for row in (manifest.get("members") or [])
            if isinstance(row, dict)]
    return name, rows


def row_path(row: dict) -> str:
    """The path a row mounts its member at, as the holder spells it."""
    return str(row.get("path")
               or f"{DEFAULT_MEMBERS_DIR}/{row.get('project')}")


def member_path(root: Path, row: dict) -> Path:
    return root / row_path(row)


def run_member_target(root: Path, row: dict, target: str) -> str | None:
    """(b) One member's own `make <target>`. Returns a failure line, or None."""
    # A member row is the family manifest's text (#391): what is PRINTED of it,
    # and of `--members-make`, is spelled. The path is built from the raw row.
    project = spelled(row.get("project") or "?")
    path = member_path(root, row)
    named = spelled(target)
    if not (path / ".git").exists():
        print(f"  [{project}] {spelled(path.name)}: NOT CHECKED OUT; skipped. "
              "See the fetch above.")
        return None
    if not (path / "Makefile").is_file():
        print(f"  [{project}] no Makefile; skipped. A member without one is "
              "not misconfigured — it simply has nothing for this command to "
              "call.")
        return None
    make = os.environ.get("MAKE") or shutil.which("make")
    if not make:
        print(f"  [{project}] `make` is not on PATH; skipped.")
        return None
    print(f"  --- {project}: make {named} ---")
    sys.stdout.flush()
    proc = subprocess.run([make, target], cwd=str(path), check=False)
    sys.stdout.flush()
    if proc.returncode != 0:
        return f"{project} (make {named} exited {proc.returncode})"
    return None


def main(argv: list[str] | None = None) -> int:
    escape_unencodable_stdout()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--no-fetch", action="store_true",
                        help="skip step (a); the members are already there "
                             "(what `make validate` passes)")
    parser.add_argument("--members-make", default="bootstrap", metavar="TARGET",
                        help="the make target to run in each member "
                             "(default: bootstrap)")
    parser.add_argument("--skip-members", action="store_true",
                        help="fetch only; run nothing in the members")
    args = parser.parse_args(argv)

    try:
        root = find_repo_root(args.root or Path(__file__).resolve().parents[1])
        name, rows = members_of(root)
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"bootstrap: {spelled(name)} ({spelled(root)}) — "
          f"{len(rows)} member(s)")

    print("\n(a) members and their legs")
    failed: list[str] = []
    if args.no_fetch:
        print("  skipped (--no-fetch)")
    else:
        try:
            failed += fetch_members(root, rows)
        except Refusal as exc:
            print(str(exc), file=sys.stderr)
            return 2

    print(f"\n(b) each member's own `make {spelled(args.members_make)}`")
    if args.skip_members:
        print("  skipped (--skip-members)")
    elif not rows:
        print("  no members declared. A family with none is empty, not wrong: "
              "`family.py add` is what puts one here.")
    else:
        for row in rows:
            failure = run_member_target(root, row, args.members_make)
            if failure:
                failed.append(failure)

    print()
    if failed:
        print("family bootstrap FAILED: " + ", ".join(failed), file=sys.stderr)
        return 1
    print("family bootstrap ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
