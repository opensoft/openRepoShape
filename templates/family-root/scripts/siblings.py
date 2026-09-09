#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Clone every member of this family BESIDE the holder, and check the layout.

    cd <Family>/<Family>
    make siblings           # or: python3 scripts/siblings.py

THE WORKSTATION LAYOUT THIS PLACES, and the one the ruling asked for (Brett
Heap, 2026-09-04: *"like a holder FOLDER and some utilities for the family of
services"*, and the layout ruling of 2026-09-09):

    <Family>/                     a PLAIN FOLDER, not a git repository
      <Family>/                   THE HOLDER: family.yaml, members/ (pinned)
      <Project>/                  a WORKING clone, on its tracking branch
      <Project>/                  …one per row in family.yaml
      session-handoff-*.md        the estate's own files live in the folder

TWO COPIES OF EVERY MEMBER, ON PURPOSE. `members/<Project>` inside the holder
is a PINNED, DETACHED checkout: it is what `make bootstrap` and `make
validate` read, and it is detached because a pin is a commit and not a branch.
The clone this command puts BESIDE the holder is where a human works — its own
`origin`, its own tracking branch, its own worktrees — and the family follows
it afterwards with `family.py bump`. Neither copy is the other's mirror, and
this command never touches the pinned one.

WHAT IT DOES, per member row in `family.yaml`:

  ABSENT   `git clone --recurse-submodules` from the SAME url `make bootstrap`
           resolves — `.gitmodules` first, `family.yaml`'s `repository:` as
           the fallback — with the same credential, resolved the same way, and
           then the member's OWN `scripts/bootstrap.py`, which puts its legs
           on their tracking branches AT their pins. The result is a working
           clone on its branch, not a detached one.

  PRESENT  `git fetch`, AND NOTHING ELSE. No checkout, no reset, no pull, no
           stash, no branch switch. Somebody is working in that clone — that
           is what it is for — and a utility that "helpfully" moved their HEAD
           would be the single most destructive thing in this standard. The
           clone is first verified to BE that member (its `origin` names the
           row's repository and its own `project.yaml` id is the row's `id`);
           when it is not, that is reported and SKIPPED, never overwritten.

  THEN     THE PARENT-FOLDER CHECK. When the holder's parent directory is not
           named after the family, this WARNS and prints the exact `mv` — and
           MOVES NOTHING. Relocating a checkout out from under somebody's
           shell, editor and agent lanes breaks linked worktrees, whose `.git`
           files carry absolute paths, and is the one act this standard
           refuses everywhere else: done by surprise, with no hand on it. The
           doctor pattern, not a mover.

IDEMPOTENT. A second run is every member `present`, one `git fetch` each, and
exit 0. That is what makes it safe to put in a handoff document.

IT CONFERS NOTHING, and neither does the layout. A folder is navigation.

EXIT CODES
    0  every member is beside the holder; nothing to report
    1  a FINDING a human can act on: a sibling that is a DIFFERENT repository,
       a clone that failed, a member's own bootstrap that went red
    2  a REFUSAL: the question could not be asked — no `family.yaml`, no
       `git`. An unanswerable question is never an implicit pass.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_shape import (  # noqa: E402
    PYTHON, Refusal, find_repo_root, load_yaml, repo_basename,
)
# THE CREDENTIAL AND THE MEMBER ROWS ARE READ BY `bootstrap.py` ALREADY, and a
# second definition of either is how the two start disagreeing about which
# token they used or where a member is mounted. Both files are copies of
# openRepoShape that travel together in `contracts/shape-pin.yaml`, so the
# import is not a dependency this holder can lose.
from bootstrap import (  # noqa: E402
    REWRITE_TARGETS, credential, member_path, members_of,
)

MANIFEST = "family.yaml"

#: ANY `<scheme>://` prefix, by PATTERN rather than by a list of the schemes
#: git happens to speak. Two reasons, in that order: a list has to be kept in
#: step with git's transports — `ssh`, `git`, `file`, `https`, `git+ssh` and
#: whatever an estate's own helper registers — and a list is also a list of
#: LITERALS, one of them the clear-text HTTP scheme, which a scanner reads as
#: a transport this file chose rather than as a string it strips (SonarCloud
#: python:S5332, on PR #79). Nothing here fetches anything at all: the prefix
#: is removed from both sides before two urls are compared.
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")


# ---------------------------------------------------------------------------
# where a member comes from
# ---------------------------------------------------------------------------


def submodule_urls(root: Path) -> dict[str, str]:
    """`{submodule path: url}` out of `.gitmodules`.

    THE SAME URL `make bootstrap` USES. `git submodule update` reads
    `.gitmodules`, so a family whose members are mounted from an SSH remote,
    a mirror or (in this suite) a bare repository on disk must produce
    siblings from that same string — deriving `https://github.com/<repo>.git`
    from the manifest instead would clone a different remote from the one this
    holder is pinned against, silently, in exactly the estates that do not use
    the default spelling.
    """
    path = root / ".gitmodules"
    if not path.is_file():
        return {}
    proc = subprocess.run(["git", "config", "-f", str(path), "--list"],
                          capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return {}
    paths: dict[str, str] = {}
    urls: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        key, _, value = line.partition("=")
        parts = key.split(".")
        if len(parts) < 3 or parts[0] != "submodule":
            continue
        name, field = ".".join(parts[1:-1]), parts[-1]
        if field == "path":
            paths[name] = value
        elif field == "url":
            urls[name] = value
    return {paths.get(name, name): url for name, url in urls.items()}


def resolve_relative(url: str, root: Path) -> str:
    """A `.gitmodules` url spelled `../<Repo>.git`, against THIS remote.

    Git reads a relative submodule url relative to the SUPERPROJECT'S REMOTE,
    not to any directory — one path component dropped per `..` — so a clone
    that took the string literally would fetch from wherever the process
    happens to be standing. `family.py add` writes absolute urls and never
    produces one of these; a hand-mounted member can, and the honest answer
    is git's own rule rather than a guess.
    """
    if not url.startswith(("./", "../")):
        return url
    base = (git_text(["remote", "get-url", "origin"], root) or "").rstrip("/")
    if not base:
        return url
    for part in url.split("/"):
        if part == "..":
            base = base.rsplit("/", 1)[0]
        elif part not in (".", ""):
            base = f"{base}/{part}"
    return base


def clone_url(root: Path, row: dict, urls: dict[str, str]) -> tuple[str, str]:
    """`(url, where it came from)` for one member."""
    path = str(row.get("path") or "")
    if path in urls:
        return resolve_relative(urls[path], root), ".gitmodules"
    repository = str(row.get("repository") or "")
    return f"https://github.com/{repository}.git", f"{MANIFEST} repository:"


def same_repository(one: str, two: str) -> bool:
    """Do two remote spellings name the SAME repository?

    A HUMAN'S OWN CLONE IS NOT REQUIRED TO SPELL THE REMOTE THE WAY
    `.gitmodules` DOES: `git@github.com:Org/Repo.git`,
    `https://github.com/Org/Repo` and `ssh://git@github.com/Org/Repo.git` are
    one repository, and refusing to fetch somebody's existing clone over a
    punctuation difference would send them to delete it. So the comparison is
    on the normalised `host/owner/repo`, and on the trailing `owner/repo`
    where the hosts are spelled differently (a mirror, an enterprise host).
    Any scheme at all is dropped by `SCHEME_RE`, which is what makes
    `file:///srv/mirrors/Repo.git` and `/srv/mirrors/Repo.git` one answer too.
    """
    def normalise(url: str) -> str:
        text = SCHEME_RE.sub("", url.strip().replace("\\", "/").rstrip("/"))
        head = text.split("/", 1)[0]
        if "@" in head:                      # git@github.com:Org/Repo.git
            text = text.split("@", 1)[1]
        head = text.split("/", 1)[0]
        if ":" in head:                      # the scp-like spelling's colon
            text = text.replace(":", "/", 1)
        if text.lower().endswith(".git"):
            text = text[:-4]
        return text.lower().strip("/")

    left, right = normalise(one), normalise(two)
    if left == right:
        return True
    tail = right.split("/")
    return len(tail) >= 2 and left.endswith("/".join(tail[-2:]))


# ---------------------------------------------------------------------------
# git, with the credential the family already resolves
# ---------------------------------------------------------------------------


def git_prefix() -> tuple[list[str], str, str]:
    """`(the -c rewrite args, the credential source, the token)`.

    Resolved by `bootstrap.py`'s own `credential()`, in the same order, and
    used ONLY through a `url.<...>.insteadOf` rewrite for the duration of one
    command: never written into `.git/config`, never persisted, never printed.
    """
    source, token = credential()
    args: list[str] = []
    if token:
        for target in REWRITE_TARGETS:
            args += ["-c", f"url.https://x-access-token:{token}@github.com/"
                           f".insteadOf={target}"]
    return args, source, token


def scrub(text: str, token: str) -> str:
    """git puts the url it tried into its error text, token and all."""
    return text.replace(token, "<redacted>") if token else text


def git_text(args: list[str], cwd: Path) -> str | None:
    proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else None


def branch_of(path: Path) -> str:
    """The checked-out branch, or `detached` — READ ONLY, like everything
    this command does to a clone somebody else made."""
    name = git_text(["rev-parse", "--abbrev-ref", "HEAD"], path)
    if not name:
        return "?"
    return "detached" if name == "HEAD" else name


# ---------------------------------------------------------------------------
# one member
# ---------------------------------------------------------------------------


class Sibling:
    """One row of the layout table: what is beside the holder, and its state."""

    def __init__(self, project: str, path: Path):
        self.project = project
        self.path = path
        self.state = "?"
        self.branch = "-"
        self.finding: str | None = None

    def row(self, kind: str = "sibling") -> str:
        return (f"  {kind:<9} {self.project:<18} {self.state:<22} "
                f"{self.branch}")


def project_id(path: Path) -> str | None:
    manifest = path / "project.yaml"
    if not manifest.is_file():
        return None
    try:
        data = load_yaml(manifest)
    except Refusal:
        return None
    return str(data.get("id")) if isinstance(data, dict) else None


def run_member_bootstrap(path: Path, sibling: Sibling) -> None:
    """The member's OWN bootstrap, which is what puts its legs on branches.

    Not reimplemented here for the same reason the family's `bootstrap.py`
    does not reimplement it: each member is a whole project and knows how.
    """
    script = path / "scripts" / "bootstrap.py"
    if not script.is_file():
        print(f"  [{sibling.project}] no scripts/bootstrap.py; cloned and "
              "left as it is. A member without one is not misconfigured — it "
              "simply has nothing for this command to call.")
        return
    print(f"  --- {sibling.project}: its own bootstrap ---")
    sys.stdout.flush()
    proc = subprocess.run([sys.executable or PYTHON, str(script)],
                          cwd=str(path), check=False)
    sys.stdout.flush()
    if proc.returncode != 0:
        sibling.finding = (f"{sibling.project}: its own bootstrap exited "
                           f"{proc.returncode}; the clone is there and its "
                           "legs may not be placed")


def place(root: Path, row: dict, urls: dict[str, str], prefix: list[str],
          token: str, dry_run: bool) -> Sibling:
    """Clone or fetch ONE member beside the holder. Never moves a HEAD."""
    project = str(row.get("project") or "?")
    repository = str(row.get("repository") or "")
    target = root.parent / project
    sibling = Sibling(project, target)
    url, source = clone_url(root, row, urls)

    if target == root:
        # A MEMBER NAMED AFTER ITS OWN FAMILY. `<Family>/<Family>` is the
        # holder, so this member's sibling would BE the holder — and this
        # command would then be asked to verify the holder against a member's
        # row. Named rather than attempted: the exit is a folder whose name
        # is not the member's, and that is the human's choice to make.
        sibling.state = "IS THE HOLDER"
        sibling.branch = branch_of(root)
        sibling.finding = (
            f"{project}: its sibling would be {target}, which is this holder "
            "itself — the member is named after its own family. Nothing was "
            "done. Rename the family FOLDER (the holder keeps its name) so "
            f"the two are not the same path, then re-run.")
        return sibling

    present = (target / ".git").exists()
    if not present and target.exists() and any(target.iterdir()):
        sibling.state = "NOT A CLONE"
        sibling.finding = (
            f"{project}: {target} exists, is not empty and is not a git "
            "clone, so this command will not write into it. Move it aside or "
            "name the directory something else; nothing here overwrites a "
            "directory somebody made.")
        return sibling

    if not present:
        if dry_run:
            sibling.state = "would clone"
            print(f"  [{project}] would clone {url} ({source}) -> {target}")
            return sibling
        print(f"  [{project}] cloning {url} ({source})")
        sys.stdout.flush()
        proc = subprocess.run(
            ["git", *prefix, "clone", "-q", "--recurse-submodules", "--",
             url, str(target)],
            capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            sibling.state = "CLONE FAILED"
            sibling.finding = (
                f"{project}: git clone exited {proc.returncode}:\n"
                + scrub((proc.stderr + proc.stdout).strip(), token))
            return sibling
        sibling.state = "cloned"
        run_member_bootstrap(target, sibling)
        sibling.branch = branch_of(target)
        return sibling

    # PRESENT. Verify it is this member, then FETCH ONLY.
    origin = git_text(["remote", "get-url", "origin"], target) or ""
    identity = project_id(target)
    if not same_repository(origin, url) and not (
            repository and same_repository(origin, repository)):
        sibling.state = "WRONG ORIGIN"
        sibling.branch = branch_of(target)
        sibling.finding = (
            f"{project}: {target} is a clone of {origin or '(no origin)'}, "
            f"not of {repository or url}, so it is not this member and is "
            "left exactly as it is. Rename it, or move it aside and re-run; "
            "this command never fetches into a repository it cannot identify.")
        return sibling
    if identity is not None and str(row.get("id")) != identity:
        sibling.state = "WRONG PROJECT"
        sibling.branch = branch_of(target)
        sibling.finding = (
            f"{project}: {target}/project.yaml declares id {identity!r} where "
            f"the family's row records {str(row.get('id'))!r}. A repository at "
            "the right url is not by itself the project the row claims, so "
            "this is reported and skipped rather than fetched.")
        return sibling

    if dry_run:
        sibling.state = "present, would fetch"
        sibling.branch = branch_of(target)
        print(f"  [{project}] present at {target}; would fetch, nothing else")
        return sibling
    print(f"  [{project}] present at {target}; fetching only")
    fetched = subprocess.run(["git", *prefix, "fetch", "--quiet", "origin"],
                             cwd=str(target), capture_output=True, text=True,
                             check=False)
    # NO CHECKOUT, NO RESET, NO PULL: somebody is working in here.
    sibling.state = "present, fetched" if fetched.returncode == 0 \
        else "present, fetch failed"
    if fetched.returncode != 0:
        print(f"  [{project}] fetch exited {fetched.returncode}; the clone is "
              "untouched:\n"
              + scrub((fetched.stderr + fetched.stdout).strip(), token),
              file=sys.stderr)
    sibling.branch = branch_of(target)
    return sibling


# ---------------------------------------------------------------------------
# the parent-folder check
# ---------------------------------------------------------------------------


def family_folder_name(manifest: dict, root: Path) -> str:
    """What the family FOLDER is called.

    THE HOLDER'S REPOSITORY NAME, not `name:`. `family.py init` creates
    `<into>/<Family>/<Family>` out of `--family <Name>`, which is the
    repository's name; `name:` is a DISPLAY name and may carry a space. Where
    a family never set one the two are the same string.
    """
    repository = str(manifest.get("repository") or "")
    if repository:
        return repo_basename(repository)
    return str(manifest.get("name") or root.name)


def parent_folder_warning(root: Path, family: str) -> str | None:
    """The WARNING and the exact `mv`, or None when the layout is right.

    IT MOVES NOTHING, and this is the ruling (issue #76, 2026-09-09): a tool
    that relocated the checkout would do it out from under the shell, the
    editor and every agent lane standing in it, and would break linked
    worktrees, whose `.git` files carry ABSOLUTE paths. The warning plus the
    command gives the same outcome with the human's hand on it.
    """
    folder = root.parent
    if folder.name == family:
        return None
    lines = [
        f"WARNING the holder's parent folder is {folder.name!r}, not "
        f"{family!r}.",
        f"        {root} should sit in a plain folder named {family}, beside "
        "the members'",
        "        working clones — that is the layout `make siblings` places. "
        "The siblings",
        f"        go beside the holder either way, so they are in {folder}.",
        "",
        "        NOTHING WAS MOVED. Relocating a checkout breaks an open "
        "shell, an editor",
        "        and any LINKED WORKTREE (its `.git` file carries an absolute "
        "path), so it",
        "        is yours to run, when nothing is standing in it:",
        "",
    ]
    wanted = folder.parent / family
    if root.name == family and not wanted.exists():
        # The common case: the holder was cloned straight into ~/projects, so
        # `<parent>/<Family>` IS the holder itself and the move needs a
        # staging name — `mv A A/A` cannot be spelled in one command.
        staged = folder.parent / f"{family}.holder"
        lines += [f"            mv {root} {staged}",
                  f"            mkdir -p {wanted}",
                  f"            mv {staged} {wanted / family}"]
    else:
        lines += [f"            mkdir -p {wanted}",
                  f"            mv {root} {wanted / family}"]
    lines += ["",
              "        Then re-run `make siblings` from the moved holder; the "
              "members are",
              "        cloned beside it, in the folder."]
    return "\n".join(lines)


# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None,
                        help="the family holder (default: the enclosing "
                             "repository)")
    parser.add_argument("--dry-run", action="store_true",
                        help="say what would be cloned and fetched; clone "
                             "nothing, fetch nothing, move nothing")
    args = parser.parse_args(argv)

    try:
        root = find_repo_root(args.root or Path(__file__).resolve().parents[1])
        # `members_of` is `bootstrap.py`'s reading of the rows and stays the
        # only one; the manifest is then read again for the two fields the
        # LAYOUT needs and bootstrap has no use for.
        name, rows = members_of(root)
        manifest = load_yaml(root / MANIFEST)
        if not isinstance(manifest, dict):
            raise Refusal("family-manifest-unreadable",
                          f"{root / MANIFEST}: not a mapping")
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2

    family = family_folder_name(manifest, root)
    print(f"siblings: {name} ({root}) — {len(rows)} member(s)")
    print(f"  family folder   {root.parent}")
    print("  each member is cloned BESIDE the holder and stays PINNED inside "
          "it under")
    print("  members/ — the pinned copy is detached for bootstrap and "
          "validate, the")
    print("  sibling is where you work.")

    prefix, source, token = git_prefix()
    urls = submodule_urls(root)
    print(f"\n(a) the members, beside the holder (credential source: "
          f"{source})")
    siblings: list[Sibling] = []
    if not rows:
        print("  no members declared. A family with none is empty, not wrong: "
              "`family.py add` is what puts one here.")
    for row in rows:
        siblings.append(place(root, row, urls, prefix, token, args.dry_run))

    print("\n(b) the layout")
    print(f"  {'what':<9} {'name':<18} {'state':<22} branch")
    holder = Sibling(root.name, root)
    holder.state = "the holder"
    holder.branch = branch_of(root)
    print(holder.row("holder"))
    for sibling in siblings:
        print(sibling.row())
    # THE SECOND COPY, said out loud in the same table: the pinned mount is
    # what `make bootstrap` and `make validate` read, and it is detached
    # because a pin is a commit and not a branch.
    for row in rows:
        mounted = member_path(root, row)
        # The row's OWN `path:` as the label, never a path computed back out
        # of the mount: a hand-edited manifest can carry something that is not
        # under this root, and a table is not the place to discover it.
        pinned = Sibling(str(row.get("path")
                             or f"members/{row.get('project')}"), mounted)
        if (mounted / ".git").exists():
            pinned.state = "pinned in the holder"
            pinned.branch = branch_of(mounted)
        else:
            pinned.state = "not checked out"
            pinned.branch = "make bootstrap"
        print(pinned.row("pinned"))

    warning = parent_folder_warning(root, family)
    if warning:
        print()
        sys.stdout.flush()          # so the warning lands where it belongs
        print(warning, file=sys.stderr)
        sys.stderr.flush()

    findings = [s.finding for s in siblings if s.finding]
    print()
    sys.stdout.flush()
    if findings:
        for finding in findings:
            print(f"FINDING {finding}", file=sys.stderr)
        print(f"siblings: {len(findings)} finding(s); nothing was moved and "
              "no existing clone was touched", file=sys.stderr)
        return 1
    if args.dry_run:
        print("--dry-run: nothing was cloned, fetched or moved.")
        return 0
    print(f"siblings ok: {len(siblings)} member(s) beside the holder in "
          f"{root.parent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
