#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The one command an engineer runs after cloning a FAMILY holder.

    git clone --recurse-submodules <family-url>
    cd <Family>
    make bootstrap          # or: python scripts/bootstrap.py

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

  (b) RUNS EACH MEMBER'S OWN `make bootstrap`. Each member is a whole project
      and knows how to bootstrap itself — its legs onto their tracking
      branches at their pinned commits, its own validators, its own
      review-authority readout. This command does not reimplement any of
      that; it walks the members `family.yaml` names and calls theirs.
      `--members-make validate` runs `make validate` instead, which is what
      the family Makefile's `validate` target uses.

  (c) EXITS 0 unless a member's own command failed. A member that is not
      checked out is REPORTED and skipped, not a failure: it is the state a
      missing credential leaves, and it is already reported in (a).

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
from repo_shape import Refusal, find_repo_root, load_yaml  # noqa: E402

MANIFEST = "family.yaml"
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


def fetch_members(root: Path) -> bool:
    """(a) `git submodule update --init --recursive`, authenticated or not."""
    source, token = credential()
    args = ["git"]
    if token:
        for target in REWRITE_TARGETS:
            args += ["-c", f"url.https://x-access-token:{token}@github.com/"
                           f".insteadOf={target}"]
    args += ["submodule", "update", "--init", "--recursive"]
    print(f"  credential source: {source}")
    sys.stdout.flush()
    proc = subprocess.run(args, cwd=str(root), capture_output=True, text=True,
                          check=False)
    if proc.returncode == 0:
        print("  every member and leg fetched")
        return True
    # The token can appear in git's own error text (it is in the URL it tried),
    # so the output is scrubbed before it is printed.
    message = (proc.stderr + proc.stdout).strip()
    if token:
        message = message.replace(token, "<redacted>")
    print(f"  FETCH INCOMPLETE (git exit {proc.returncode}) using credential "
          f"source '{source}':\n{message}", file=sys.stderr)
    print("  If the members are PRIVATE, set SHAPE_LEGS_TOKEN (a fine-grained "
          "PAT with contents:read on them) or export an App-minted "
          "SHAPE_LEGS_APP_TOKEN, then re-run. What did arrive is bootstrapped "
          "below.", file=sys.stderr)
    return False


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


def member_path(root: Path, row: dict) -> Path:
    return root / str(row.get("path")
                      or f"{DEFAULT_MEMBERS_DIR}/{row.get('project')}")


def run_member_target(root: Path, row: dict, target: str) -> str | None:
    """(b) One member's own `make <target>`. Returns a failure line, or None."""
    project = str(row.get("project") or "?")
    path = member_path(root, row)
    if not (path / ".git").exists():
        print(f"  [{project}] {path.name}: NOT CHECKED OUT; skipped. See the "
              "fetch above.")
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
    print(f"  --- {project}: make {target} ---")
    sys.stdout.flush()
    proc = subprocess.run([make, target], cwd=str(path), check=False)
    sys.stdout.flush()
    if proc.returncode != 0:
        return f"{project} (make {target} exited {proc.returncode})"
    return None


def main(argv: list[str] | None = None) -> int:
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

    print(f"bootstrap: {name} ({root}) — {len(rows)} member(s)")

    print("\n(a) members and their legs")
    if args.no_fetch:
        print("  skipped (--no-fetch)")
    else:
        fetch_members(root)

    print(f"\n(b) each member's own `make {args.members_make}`")
    failed: list[str] = []
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
