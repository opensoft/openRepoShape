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
      row's path (a gitlink recorded only in another case, #363); no
      section of `.gitmodules` gives that path (a holder whose HEAD lost the
      file, #611); git exited 0 and checked nothing out there; or git
      stopped at a gitlink no section gives a url, the row's own or another
      (a stray case variant, a member mounted by hand, a section that lost
      its url), since git's init dies at the first such gitlink it asks
      about, before it checks out any member. Git exits 0 over the second
      where a recursive clone ran first, and 128 (`No url found for
      submodule path`) in a plain clone; a missing credential exits
      non-zero too, so what the holder records is the test, never git's
      words. The line says what cures each: `validate-family.py` names the
      commit for the first two; for the third it prints the `git submodule
      update --init --checkout` that checks the member out whatever the
      clone chose; and for the last, `validate-family.py --no-members`
      names a gitlink no row names, and where the gitlink is a row's own
      the line says to write its section back.

  (b) RUNS EACH MEMBER'S OWN `make bootstrap`. Each member is a whole project
      and knows how to bootstrap itself — its legs onto their tracking
      branches at their pinned commits, its own validators, its own
      review-authority readout. This command does not reimplement any of
      that; it walks the members `family.yaml` names and calls theirs.
      `--members-make validate` runs `make validate` instead, which is what
      the family Makefile's `validate` target uses.

  (c) EXITS 0 unless a member's own command failed, or (a) left a member not
      checked out that no credential would check out. Any other member that
      is not checked out is REPORTED and skipped, not a failure: it is the
      state a missing credential leaves, and it is already reported in (a).

THE FAMILY CONFERS NOTHING and neither does this command. It fetches, it
delegates, and it says what it could not reach.
"""

from __future__ import annotations

import argparse
import os
import shlex
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
#: A submodule's entry in the index, as `ls-files -s` spells its mode.
GITLINK_MODE = b"160000"

#: Why (a) left a row's member NOT CHECKED OUT where no credential would
#: check it out (#648), in the order `unfetchable` asks. `STOPPED` is
#: filled with the gitlink git's init died at (`init_stop`).
NO_GITLINK = "no gitlink is recorded at that path"
NO_SECTION = f"no section of {GITMODULES} gives that path"
EXITED_0 = "git exited 0 and checked nothing out there"
STOPPED = ("git stopped at {}, a gitlink no section of " + GITMODULES
           + " gives a url")

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
    fetched only where there is none and git exited 0."""
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
                          encoding="utf-8", errors="replace", check=False)
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
    left, stopper = unfetchable(root, rows, proc.returncode == 0)
    if left:
        print("  NOT CHECKED OUT, and not for want of a credential: "
              + ", ".join(f"{spelled(path)} ("
                          + (STOPPED.format(spelled(stopper))
                             if why == STOPPED else why) + ")"
                          for _, path, why in left)
              + ". " + cures(left, stopper, rows), file=sys.stderr)
    elif proc.returncode == 0:
        print("  every member and leg fetched")
    return [f"{spelled(row.get('project') or '?')} (not checked out)"
            for row, _, _ in left]


def cures(left: list[tuple[dict, str, str]], stopper: str | None,
          rows: list[dict]) -> str:
    """What (a)'s line says cures the rows `left` names, one sentence for
    each why among them (#648). `validate-family.py`, which names the
    commit, for a gitlink or a section the holder lacks at the row's path.
    For the gitlink git stopped at, `validate-family.py --no-members`, which
    names a gitlink no row names and the commit that cures it (members
    checked, it refuses `member-uninitialized` for the first row there
    instead), or, where a row names it, its section written back. For a row
    git exited 0 over, the update that checks it out whatever the clone
    chose: `--init` with the path registers a member a subset clone left
    out, and `--checkout` overrides an `update = none`."""
    whys = {why for _, _, why in left}
    said = []
    if whys & {NO_GITLINK, NO_SECTION}:
        said.append(f"`{PYTHON} scripts/validate-family.py` names the cause "
                    "and the commit that cures it.")
    if STOPPED in whys and stopper in {row_path(row) for row in rows}:
        said.append(f"Write the section of {GITMODULES} for "
                    f"{spelled(stopper)} back as `family.py add` writes one, "
                    f"with its path and url, and commit {GITMODULES}.")
    elif STOPPED in whys:
        said.append(f"`{PYTHON} scripts/validate-family.py --no-members` "
                    f"names each gitlink in {DEFAULT_MEMBERS_DIR}/ that no "
                    "row names, and the commit that cures it.")
    exited = [path for _, path, why in left if why == EXITED_0]
    if exited:
        update = shlex.join(["git", "submodule", "update", "--init",
                             "--checkout", "--recursive", "--", *exited])
        said.append(f"`{spelled(update)}` checks "
                    f"{'it' if len(exited) == 1 else 'them'} out.")
    return " ".join(said)


def gitmodules_sections(root: Path) -> dict[str, dict[str, str]]:
    """`{name: {key: value}}` of every section of `.gitmodules`, read as git
    reads it: the work tree's file, the one `git submodule update` reads,
    which a fresh clone takes from HEAD. An empty mapping where there is no
    such file, or one git cannot read: git has no url for any submodule
    then either."""
    if not os.path.lexists(root / GITMODULES):
        return {}
    try:
        listed = git_out(["config", "-z", "--file", GITMODULES, "--list"],
                         cwd=root, binary=True)
    except Refusal:
        return {}
    sections: dict[str, dict[str, str]] = {}
    for record in listed.split(b"\0"):
        key, _, value = record.decode("utf-8",
                                      "surrogateescape").partition("\n")
        section, _, variable = key.rpartition(".")
        if section.startswith("submodule."):
            sections.setdefault(section[len("submodule."):],
                                {})[variable] = value
    return sections


def init_stop(root: Path, sections: dict[str, dict[str, str]]) -> str | None:
    """The gitlink `git submodule update --init` dies at, or None: the first
    in the index, in index order, that its init step asks about and finds
    no url for (`No url found for submodule path`, exit 128), before it
    checks out any member (#648).

    ASKED AS GIT 2.43 ASKS IT, of the index, `sections` and this
    repository's git config. Every gitlink the index records is asked, but
    where the config sets `submodule.active`, as a recursive clone sets it
    (`.`), only those a section gives a path: git counts no other active.
    One no section gives stops it; so does one whose section gives no url,
    unless the config has one under the section's name, as an earlier init
    writes it. So a stray case variant or a member mounted by hand stops a
    plain clone's update, and leaves a recursive clone's to the credential.
    Read nothing, it answers None."""
    try:
        index = git_out(["ls-files", "-s", "-z"], cwd=root, binary=True)
    except Refusal:
        return None
    try:
        config = git_out(["config", "-z", "--get-regexp", r"^submodule\."],
                         cwd=root, binary=True)
    except Refusal:
        config = b""
    keys = {record.decode("utf-8", "surrogateescape").partition("\n")[0]
            for record in config.split(b"\0")}
    names: dict[str, list[str]] = {}
    for name, held in sections.items():
        if "path" in held:
            names.setdefault(held["path"], []).append(name)
    for record in index.split(b"\0"):
        meta, _, entry = record.partition(b"\t")
        if meta.split()[:1] != [GITLINK_MODE]:
            continue
        path = entry.decode("utf-8", "surrogateescape")
        given = names.get(path, [])
        if not given and "submodule.active" in keys:
            continue
        if not any("url" in sections[name] or f"submodule.{name}.url" in keys
                   for name in given):
            return path
    return None


def unfetchable(root: Path, rows: list[dict], exited_0: bool
                ) -> tuple[list[tuple[dict, str, str]], str | None]:
    """`(row, path, why)` for each row whose member (a) left NOT CHECKED OUT
    where no credential would check it out (#648), in row order, and the
    gitlink git's init died at (`init_stop`), or None.

    Asked of this holder's own records, never of git's words: a row at
    whose path the holder records no gitlink (`recorded_gitlink`,
    as `validate-family.py`'s `member-gitlink-absent` reads one), or whose
    gitlink no section of `.gitmodules` gives a path (as its
    `member-gitmodules-absent` reads HEAD's file, which is the work tree's
    in a clone); where git exited 0, any row at all, since git then lacked
    nothing a credential gives; and where git's init died at a gitlink no
    section gives a url, any row at all, since git then checked out no
    member and asked for no credential. Any other row not checked out is
    the missing credential's, and stays the skip it always was. A path two
    rows give is said once."""
    left: dict[str, dict] = {}
    for row in rows:
        if not (member_path(root, row) / ".git").exists():
            left.setdefault(row_path(row), row)
    if not left:
        return [], None
    sections = gitmodules_sections(root)
    given = {held["path"] for held in sections.values() if "path" in held}
    stopper = None if exited_0 else init_stop(root, sections)
    found: list[tuple[dict, str, str]] = []
    for path, row in left.items():
        if recorded_gitlink(root, path) is None:
            found.append((row, path, NO_GITLINK))
        elif path not in given:
            found.append((row, path, NO_SECTION))
        elif exited_0:
            found.append((row, path, EXITED_0))
        elif stopper is not None:
            found.append((row, path, STOPPED))
    return found, stopper


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
        failed += fetch_members(root, rows)

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
