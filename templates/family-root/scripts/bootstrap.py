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
      file, #611); git has no url for that path, in the section it reads
      for it or in its config (a section that lost its url, or a second
      one for the path after the member's); git exited 0 and checked
      nothing out there; or git stopped at another gitlink it has no url
      for (a stray case variant, a member mounted by hand), since git's
      init dies at the first such gitlink it asks about, before it checks
      out any member. Which section and which url git reads is its own
      parser's answer, not `git config`'s (`gitmodules_sections`), and
      while a merge leaves `.gitmodules` unmerged in the index git reads
      none at all: every such member is said to be that, and the cure is
      the file resolved and added. Git exits 0 over the second where a
      recursive clone ran first, and 128 (`No url found for submodule
      path`) in a plain clone; a missing credential exits non-zero too,
      so what the holder records is the test, never git's words. The line
      says what cures each (`cures`):
      `validate-family.py` names the commit for the first two; for the
      fourth it prints the `git submodule update --init --checkout` that
      checks the member out whatever the clone chose. For the third and
      the last, `validate-family.py --no-members` names a path two
      sections give, or a gitlink in members/ that no row names; `git rm
      --cached` takes out one outside members/, which the validator does
      not read; and where the gitlink is a row's own, with one section,
      the line says to write its section back.

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
import shlex
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import NamedTuple

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
UNMERGED = f"git reads no {GITMODULES} while a merge leaves it unmerged"
NO_GITLINK = "no gitlink is recorded at that path"
NO_SECTION = f"no section of {GITMODULES} gives that path"
NO_URL = "git has no url for that path"
EXITED_0 = "git exited 0 and checked nothing out there"
STOPPED = "git stopped at {}, a gitlink it has no url for"

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
    left, stopper, modules = unfetchable(root, rows, proc.returncode == 0)
    if left:
        print("  NOT CHECKED OUT, and not for want of a credential: "
              + ", ".join(f"{spelled(path)} ("
                          + (STOPPED.format(spelled(stopper))
                             if why == STOPPED else why) + ")"
                          for _, path, why in left)
              + ". " + cures(left, stopper, rows, modules), file=sys.stderr)
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


def cures(left: list[tuple[dict, str, str]], stopper: str | None,
          rows: list[dict], modules: Gitmodules) -> str:
    """What (a)'s line says cures the rows `left` names, one sentence for
    each kind of cause among them (#648):

    - A `.gitmodules` a merge left unmerged in the index, which git reads
      nothing from (`Gitmodules.unmerged`): the file resolved and added.
    - A gitlink or a section the holder lacks at the row's path:
      `validate-family.py`, which names it and the commit that cures it,
      `member-gitlink-absent` (with the move, for a gitlink recorded only
      in another case, #363) or `member-gitmodules-absent`.
    - A path git has no url for (`has_url`), a row's own or the gitlink git
      stopped at. Where more than one section gives it, as a merge that
      kept both sides leaves them, `validate-family.py --no-members`, whose
      `gitmodules-path-twice` says which to keep and to take the others
      out: a section written back would be one more. Otherwise a row's own
      is its section written back. A gitlink in `members/` no row names is
      `--no-members` too, whose `member-gitlink-unnamed` names it and the
      commit that cures it: members checked, the validator refuses
      `member-uninitialized` for the first row where every row's gitlink
      is there, as with a stray or a hand mount, and `member-gitlink-absent`
      where a row's is only in another case, which the first sentence
      names. A gitlink outside `members/`, which no mode of the validator
      asks about, is taken out of the index: no row names it, and with no
      url no clone can check it out.
    - A row git exited 0 over: the update that checks it out whatever the
      clone chose. `--init` with the path registers a member a subset
      clone left out, and `--checkout` overrides an `update = none`."""
    whys = {why for _, _, why in left}
    said = []
    if UNMERGED in whys:
        said.append(f"Resolve the merge in {GITMODULES} and `git add "
                    f"{GITMODULES}`, then run this again.")
    if whys & {NO_GITLINK, NO_SECTION}:
        said.append(f"`{PYTHON} scripts/validate-family.py` names the cause "
                    "and the commit that cures it.")
    unread = [path for _, path, why in left if why == NO_URL]
    if STOPPED in whys and stopper not in {path for _, path, _ in left}:
        unread.append(stopper)
    named = {row_path(row) for row in rows}
    twice = [path for path in unread if modules.given[path] > 1]
    own = [path for path in unread if path in named and path not in twice]
    if twice:
        said.append(f"`{PYTHON} scripts/validate-family.py --no-members` "
                    f"names each path more than one section of {GITMODULES} "
                    "gives, and how to take the others out.")
    if own:
        said.append(f"Write {'the' if len(own) == 1 else 'each'} section of "
                    f"{GITMODULES} for {', '.join(map(spelled, own))} back "
                    "as `family.py add` writes one, with its path and url, "
                    f"and commit {GITMODULES}.")
    for path in unread:
        if path in named or path in twice:
            continue
        if path.split("/", 1)[0].casefold() == DEFAULT_MEMBERS_DIR:
            said.append(f"`{PYTHON} scripts/validate-family.py --no-members` "
                        f"names each gitlink in {DEFAULT_MEMBERS_DIR}/ that "
                        "no row names, and the commit that cures it.")
        else:
            removal = shlex.join(["git", "rm", "--cached", "--", path])
            said.append(f"No row names {spelled(path)} and no clone can check "
                        f"it out: `{spelled(removal)}` takes its gitlink "
                        "out, then commit that.")
    exited = [path for _, path, why in left if why == EXITED_0]
    if exited:
        update = shlex.join(["git", "submodule", "update", "--init",
                             "--checkout", "--recursive", "--", *exited])
        said.append(f"`{spelled(update)}` checks "
                    f"{'it' if len(exited) == 1 else 'them'} out.")
    return " ".join(said)


class Gitmodules(NamedTuple):
    """`.gitmodules` as (a) asks it (#648), read by `gitmodules_sections`.

    `given` counts the sections that give each path, every section kept, as
    `validate-family.py` reads them for the findings (a)'s line names:
    `member-gitmodules-absent` and `gitmodules-path-twice`. `read` is
    `{path: name}`, the section git reads for each path, and `urls` is
    `{name: url}`, the url git takes from each, as git's own parser has
    them. `unmerged` says a merge left the file unmerged in the index, and
    then git reads nothing from it, and the three are empty."""

    given: Counter
    read: dict[str, str]
    urls: dict[str, str]
    unmerged: bool = False


def gitmodules_sections(root: Path) -> Gitmodules:
    """`.gitmodules` as `git submodule update` reads it: the work tree's
    file, which a fresh clone takes from HEAD. Nothing where there is no
    such file, or one git cannot read: git has no url for any submodule
    then either. Nothing, and `unmerged`, where the index holds the file
    only at a merge's conflict stages (`git ls-files -u`): git reads no
    `.gitmodules` at all then, whatever the work tree holds
    (`repo_read_gitmodules`), and its init dies at the first gitlink.

    `read` and `urls` keep git 2.43's own rules (submodule-config.c), which
    drop what `git config --list` keeps. Entry by entry, in file order:

    - a section whose name is empty or has a `..` component, split on `/`
      and on a backslash, is ignored whole (git warns `ignoring suspicious
      submodule name`);
    - a `path` or `url` that begins with `-` is dropped, and the value
      before it stands (`may be interpreted as a command-line option`);
    - where two sections give one path, the later in the file decides, as
      a later value in one section replaces an earlier. A section that
      gives a path again lets go of the one it gave, even where a later
      section gave that one too: git then reads no section there."""
    nothing = Gitmodules(Counter(), {}, {})
    try:
        stages = git_out(["ls-files", "-u", "-z", "--", GITMODULES],
                         cwd=root, binary=True)
    except Refusal:
        stages = b""
    if any(record.partition(b"\t")[2] == GITMODULES.encode()
           for record in stages.split(b"\0")):
        return nothing._replace(unmerged=True)
    if not os.path.lexists(root / GITMODULES):
        return nothing
    try:
        listed = git_out(["config", "-z", "--file", GITMODULES, "--list"],
                         cwd=root, binary=True)
    except Refusal:
        return nothing
    sections: dict[str, dict[str, str]] = {}
    read: dict[str, str] = {}
    held: dict[str, str] = {}
    urls: dict[str, str] = {}
    for record in listed.split(b"\0"):
        key, _, value = record.decode("utf-8",
                                      "surrogateescape").partition("\n")
        section, _, variable = key.rpartition(".")
        if not section.startswith("submodule."):
            continue
        name = section[len("submodule."):]
        sections.setdefault(name, {})[variable] = value
        if (not name or ".." in name.replace("\\", "/").split("/")
                or value.startswith("-")):
            continue
        if variable == "path":
            if name in held:
                read.pop(held[name], None)
            held[name] = value
            read[value] = name
        elif variable == "url":
            urls[name] = value
    return Gitmodules(Counter(keys["path"] for keys in sections.values()
                              if "path" in keys), read, urls)


def submodule_config(root: Path) -> set[str]:
    """Every `submodule.` key this repository's git config sets, in every
    scope git reads, as git's init asks them: `submodule.active`, and
    `submodule.<name>.url` as an earlier init writes it. None where git
    lists none."""
    try:
        config = git_out(["config", "-z", "--get-regexp", r"^submodule\."],
                         cwd=root, binary=True)
    except Refusal:
        return set()
    return {record.decode("utf-8", "surrogateescape").partition("\n")[0]
            for record in config.split(b"\0")}


def has_url(modules: Gitmodules, config: set[str], path: str) -> bool:
    """Whether git's init finds a url for the gitlink at `path`: in the
    section git reads for that path (`Gitmodules.read`), or in the git
    config under that section's name, as an earlier init writes it. Where
    git reads no section there it has none, whatever the config holds."""
    name = modules.read.get(path)
    return name is not None and (name in modules.urls
                                 or f"submodule.{name}.url" in config)


def init_stop(root: Path, modules: Gitmodules, config: set[str]
              ) -> str | None:
    """The gitlink `git submodule update --init` dies at, or None: the first
    in the index, in index order, that its init step asks about and has no
    url for (`No url found for submodule path`, exit 128), before it
    checks out any member (#648).

    ASKED AS GIT 2.43 ASKS IT, of the index, `modules` and `config`, this
    repository's git config. Every gitlink the index records is asked, but
    where the config sets `submodule.active`, as a recursive clone sets it
    (`.`), only those a section git reads gives a path: git counts no other
    active. A gitlink git has no url for (`has_url`) stops it. So a stray
    case variant or a member mounted by hand stops a plain clone's update,
    and leaves a recursive clone's to the credential. Read nothing, it
    answers None."""
    try:
        index = git_out(["ls-files", "-s", "-z"], cwd=root, binary=True)
    except Refusal:
        return None
    for record in index.split(b"\0"):
        meta, _, entry = record.partition(b"\t")
        if meta.split()[:1] != [GITLINK_MODE]:
            continue
        path = entry.decode("utf-8", "surrogateescape")
        if path not in modules.read and "submodule.active" in config:
            continue
        if not has_url(modules, config, path):
            return path
    return None


def unfetchable(root: Path, rows: list[dict], exited_0: bool
                ) -> tuple[list[tuple[dict, str, str]], str | None,
                           Gitmodules]:
    """`(row, path, why)` for each row whose member (a) left NOT CHECKED OUT
    where no credential would check it out (#648), in row order; the
    gitlink git's init died at (`init_stop`), or None; and `.gitmodules`
    as it was read, for `cures`.

    Asked of this holder's own records, never of git's words: any row at
    all while a merge leaves `.gitmodules` unmerged in the index, since git
    then reads no section and asks for no credential; a row at
    whose path the holder records no gitlink (`recorded_gitlink`,
    as `validate-family.py`'s `member-gitlink-absent` reads one), or whose
    gitlink no section of `.gitmodules` gives a path (as its
    `member-gitmodules-absent` reads HEAD's file, which is the work tree's
    in a clone); one git has no url for (`has_url`), where no credential
    helps either, whatever git exited; where git exited 0, any row at all,
    since git then lacked nothing a credential gives; and where git's init
    died at a gitlink it has no url for, any row at all, since git then
    checked out no member and asked for no credential. Any other row not
    checked out is the missing credential's, and stays the skip it always
    was. A path two rows give is said once."""
    left: dict[str, dict] = {}
    for row in rows:
        if not (member_path(root, row) / ".git").exists():
            left.setdefault(row_path(row), row)
    if not left:
        return [], None, Gitmodules(Counter(), {}, {})
    modules = gitmodules_sections(root)
    config = submodule_config(root)
    stopper = None if exited_0 else init_stop(root, modules, config)
    found: list[tuple[dict, str, str]] = []
    for path, row in left.items():
        if modules.unmerged:
            found.append((row, path, UNMERGED))
        elif recorded_gitlink(root, path) is None:
            found.append((row, path, NO_GITLINK))
        elif not modules.given[path]:
            found.append((row, path, NO_SECTION))
        elif not has_url(modules, config, path):
            found.append((row, path, NO_URL))
        elif exited_0:
            found.append((row, path, EXITED_0))
        elif stopper is not None:
            found.append((row, path, STOPPED))
    return found, stopper, modules


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
    # A `members:` THAT IS NOT A LIST, OR HOLDS AN ENTRY THAT IS NOT A
    # MAPPING, IS REFUSED BY NAME (#864), in `validate-family.py`'s words:
    # read as `members or []`, `5` ended `make bootstrap` and `make siblings`
    # in a `TypeError`, `openXdox` or `[5]` was "0 member(s)" and "family
    # bootstrap ok", and the rows beside a `5` were fetched with the `5`
    # unsaid. Absent or null is a family with no members.
    rows = manifest.get("members")
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        raise Refusal("family-members-unreadable",
                      f"{manifest_path}: `members:` is {rows!r}, expected a "
                      "list")
    unread = [f"a member is not a mapping: {row!r}" for row in rows
              if not isinstance(row, dict)]
    if unread:
        raise Refusal("family-members-unreadable",
                      f"{manifest_path}: {'; '.join(unread)}")
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
