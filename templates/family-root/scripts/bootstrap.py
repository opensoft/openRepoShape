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
      than one that says which. The advice to set a credential is given only
      where git asked for one: not where its init died at a gitlink it has
      no url for, nor where it read nothing from `.gitmodules`, both below,
      since it fetched nothing then (#839).

      Where every row's member is checked out and git's init died all the
      same, at a gitlink it has no url for or at a `.gitmodules` a merge
      left unmerged, git updated none of them, so the run fails, saying
      where git stopped and what cures it, as below, with no advice
      (#879). It said `family bootstrap ok` there, beside git's exit 128,
      as a run with every member checked out passes (#648), and gave the
      advice where git stopped at a gitlink.

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
      parser's answer, not `git config`'s (`gitmodules_sections`), from
      the work tree's file or, where the work tree has none, the index's,
      then HEAD's, and while a merge leaves `.gitmodules` unmerged in the
      index git reads none at all: every such member is said to be that,
      and the cure is the file resolved and added. Where the file gives a
      submodule a value git dies on as it reads it (`refused_value`, #768),
      every such member is said to be that, naming each key and its value,
      and the cure is the key given a value git takes or its line taken
      out; where every member was checked out the run fails all the same,
      since git updated none of them. A work tree file git cannot parse at
      all, a conflict marker or an open quote left in it, is said and
      failed on the same way, and its cure is the file mended by hand; in
      the index's or HEAD's file git reads the sections before such a line
      and goes on, and so does this (#856). Git exits 0 over the second
      where a recursive clone ran first, and 128 (`No url found for
      submodule path`) in a plain clone; a missing
      credential exits non-zero too, so what the holder records is the
      test, never git's words. The line says what cures each (`cures`):
      `validate-family.py` names the commit for the first two; for the
      fourth it prints the `git submodule update --init --checkout` that
      checks the member out whatever the clone chose. For the third and
      the last, `validate-family.py --no-members` names a path two
      sections give, or a gitlink in members/ that no row names; `git rm
      --cached` takes out one outside members/, as every mode of the
      validator says (#878); and where it is a row's own, with one section,
      the line says to write its section back. Where git read the index's
      or HEAD's file only up to a line it cannot parse, or up to a key it
      takes no value for (a bare `url` line, which `git config --list`
      takes), a section or url it did not read may be past that line, so
      for those three the line says to put that file back, mend the line
      or give the key a value or take it out, and commit it, and writes
      no section back (#856).

  (b) RUNS EACH MEMBER'S OWN `make bootstrap`. Each member is a whole project
      and knows how to bootstrap itself — it puts its legs on their
      tracking branches at their pins where that loses no commit, and says
      why where it does not; its own validators; its own
      review-authority readout. This command does not reimplement any of
      that; it walks the members `family.yaml` names and calls theirs.
      `--members-make validate` runs `make validate` instead, which is what
      the family Makefile's `validate` target uses. A member whose command
      fails is named with that command's exit code, read from make's
      `Error <code>` line, since make exits 2 for any command that fails,
      so a member's finding (1) and its refusal (2) are told apart, and
      from a failure of make's own, which prints no such line (#839).

  (c) EXITS 0 unless a member's own command failed, or (a) left a member not
      checked out that no credential would check out, or found a line or a
      value in `.gitmodules` that git cannot read (#768), or found that,
      with every member checked out, git's init died at a gitlink it has
      no url for or at an unmerged `.gitmodules` (#879). Any
      other member that is not checked out is REPORTED and skipped, not a
      failure: it is the state a missing credential leaves, and it is
      already reported in (a).
      Where (a) cannot start git, the run STOPS there, exit 2, refused
      `git-not-runnable` as `validate-family.py` refuses it (#694): each
      member's own bootstrap runs git too, so (b) would only say it again.

THE FAMILY CONFERS NOTHING and neither does this command. It fetches, it
delegates, and it says what it could not reach.
"""

from __future__ import annotations

import argparse
import os
import re
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
#: filled with the gitlink git's init died at (`init_stop`), and `REFUSED`
#: with each entry of `.gitmodules` git refused (`reason`). `UNREADABLE` is
#: a work tree file git cannot parse at all (#768).
UNMERGED = f"git reads no {GITMODULES} while a merge leaves it unmerged"
REFUSED = f"git cannot read {GITMODULES}: {{}}"
UNREADABLE = f"git cannot parse {GITMODULES}"
NO_GITLINK = "no gitlink is recorded at that path"
NO_SECTION = f"no section of {GITMODULES} gives that path"
NO_URL = "git has no url for that path"
EXITED_0 = "git exited 0 and checked nothing out there"
STOPPED = "git stopped at {}, a gitlink it has no url for"
#: The whys a `.gitmodules` git read only up to a line it cannot parse, or
#: up to a key with no value it stops at, may be the cause of, since what
#: it did not read is past that line (`Gitmodules.cut`, #856).
CUT_WHYS = frozenset({NO_SECTION, NO_URL, STOPPED})
#: HEAD's `.gitmodules`, as `git config --blob` is given it.
HEAD_GITMODULES = f"HEAD:{GITMODULES}"

#: What git 2.43 dies on in a `.gitmodules` it reads (#768), as
#: `parse_config` in its submodule-config.c reads a submodule's key: these
#: keys with no value (a `branch` with none crashes it, `BRANCH_READ_SINCE`),
#: and an `update` other than these four. A `shallow` must be a boolean and
#: a `fetchrecursesubmodules` a boolean or `on-demand` (`git_bool`). The
#: gate's `_values_refused`, `_git_takes_bool` and `GIT_TAKES` say the same,
#: and `tests/test_family_gitmodules_values.py` holds the two scripts to one
#: answer: a change made here is made there too (#856).
NO_VALUE_REFUSED = frozenset({"path", "url", "update", "ignore", "branch"})
#: The first git that reads a `branch` with no value as it reads a `url`
#: with none, `missing value` and `bad config line`, which dies in the work
#: tree's file and ends the reading of the index's or HEAD's, a blob: 2.43.1,
#: and 2.44.0 on its main line, by their submodule-config.c, and 2.47.1 as
#: measured. A git before it crashes reading any `.gitmodules` that gives
#: one, a blob too: 2.43.0 as measured (exit 139), and 2.42.4 and 2.39.5 by
#: their source, which has the same `xstrdup` of no value
#: (`crashes_on_branch`).
BRANCH_READ_SINCE = (2, 43, 1)
#: `git version 2.43.0`, `git version 2.45.1.windows.1`, `git version
#: 2.39.3 (Apple Git-146)`: three numbers, since the third decides here.
GIT_VERSION_RE = re.compile(r"git version (\d+)\.(\d+)\.(\d+)")
UPDATE_VALUES = ("none", "checkout", "rebase", "merge")
#: What git takes for a key whose value it refused, as (a)'s cure says it.
TAKES = {"update": "one of `none`, `checkout`, `rebase` or `merge`",
         "shallow": "a boolean, `true` or `false`",
         "fetchrecursesubmodules": "a boolean or `on-demand`",
         "ignore": "one of `untracked`, `dirty`, `all` or `none`",
         "path": "a path", "url": "a url", "branch": "a branch name"}

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

    Where every member is checked out and git died on a value in
    `.gitmodules`, or on a work tree file it cannot parse, or its init
    died at a `.gitmodules` a merge left unmerged, so it updated none of
    them, the one failure line it returns is for `.gitmodules` (#768,
    #879); where its init died at a gitlink it has no url for, it is for
    that gitlink (`updated_none`, #879).

    Returns a failure line for each of `rows` whose member it leaves not
    checked out where no credential would check it out (`unfetchable`), for
    the run to end FAILED on (#648); every member and leg is said to be
    fetched only where there is none and git exited 0. The advice to set a
    credential is printed only where git asked for one
    (`credential_advice`, #839). Raises the `git-not-runnable` refusal
    where git cannot be started (#694)."""
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
    left, stopper, modules = unfetchable(root, rows, proc.returncode == 0)
    if proc.returncode != 0:
        fetch_incomplete(proc, source, token,
                         credential_advice(bool(left), stopper, modules))
    whole = updated_none(left, stopper, modules)
    if left:
        print("  NOT CHECKED OUT, and not for want of a credential: "
              + ", ".join(f"{spelled(path)} ({reason(why, stopper, modules)})"
                          for _, path, why in left)
              + ". " + cures(left, stopper, rows, modules), file=sys.stderr)
    elif whole is not None:
        print("  NO MEMBER UPDATED, and not for want of a credential: "
              + reason(whole, stopper, modules) + ". "
              + cures(left, stopper, rows, modules, (whole,)),
              file=sys.stderr)
        return [f"{spelled(stopper)} (git stopped at it)" if whole == STOPPED
                else f"{GITMODULES} (git cannot read it)"]
    elif proc.returncode == 0:
        print("  every member and leg fetched")
    return [f"{spelled(row.get('project') or '?')} (not checked out)"
            for row, _, _ in left]


def fetch_incomplete(proc: subprocess.CompletedProcess, source: str,
                     token: str, advice: str) -> None:
    """(a)'s report of a `git submodule update` that exited non-zero: git's
    own words, then `advice`, where there is any (`credential_advice`)."""
    # The token can appear in git's own error text (it is in the URL it
    # tried), so the output is scrubbed before it is printed.
    message = (proc.stderr + proc.stdout).strip()
    if token:
        message = message.replace(token, "<redacted>")
    print(f"  FETCH INCOMPLETE (git exit {proc.returncode}) using "
          f"credential source '{source}':\n{message}", file=sys.stderr)
    if advice:
        print(advice, file=sys.stderr)


def credential_advice(denied: bool, stopper: str | None,
                      modules: Gitmodules) -> str:
    """(a)'s advice to set a credential, or nothing where git asked for none
    (#839): where its init died at a gitlink it has no url for (`stopper`),
    or it read nothing from `.gitmodules`, a merge leaving it unmerged, a
    value git dies on or a file it cannot parse, it fetched nothing. Every
    row (a) then leaves not checked out is said to be no credential's, and
    the advice beside that was its denial (w768's candidate 1 on #819).
    Anywhere else a fetch git made failed, a member's, or a leg's in a
    member checked out, and the advice stands; where a row is said to be no
    credential's beside it (`denied`), it is for the members that line does
    not name."""
    if (stopper is not None or modules.unmerged or modules.refused
            or modules.unreadable):
        return ""
    which = ("the members the next line does not name" if denied
             else "the members")
    return (f"  If {which} are PRIVATE, set SHAPE_LEGS_TOKEN (a fine-grained "
            "PAT with contents:read on them) or export an App-minted "
            "SHAPE_LEGS_APP_TOKEN, then re-run. What did arrive is "
            "bootstrapped below.")


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
          rows: list[dict], modules: Gitmodules,
          whole: tuple[str, ...] = ()) -> str:
    """What (a)'s line says cures the rows `left` names, one sentence for
    each kind of cause among them (#648), or, where it names none, what
    cures `whole`, why git updated no member (`updated_none`, #879), one
    reason or none:

    - A `.gitmodules` a merge left unmerged in the index, which git reads
      nothing from (`Gitmodules.unmerged`): the file resolved and added.
    - A `.gitmodules` that gives a value git dies on (`Gitmodules.refused`,
      #768): each key given a value git takes (`TAKES`), or its line taken
      out, and the file committed, with `validate-family.py --no-members`,
      whose `gitmodules-value-refused` prints the commands.
    - A work tree `.gitmodules` git cannot parse (`Gitmodules.unreadable`):
      the file mended by hand and committed.
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
      names. A gitlink outside `members/` is taken out of the index, as
      every mode of the validator says (#878): no row names it, and with
      no url no clone can check it out.
    - A row git exited 0 over: the update that checks it out whatever the
      clone chose. `--init` with the path registers a member a subset
      clone left out, and `--checkout` overrides an `update = none`.
    - The index's or HEAD's `.gitmodules`, a blob, which git read only up
      to a line it cannot parse, or up to a key with no value it stops at
      (`Gitmodules.cut`, #856), for a row with no section or no url there,
      or the gitlink git stopped at (`CUT_WHYS`): that file put back,
      mended and committed, which `gitmodules_cures` says. A section or
      url git did not read may be past the line, so no other cure is said
      for those: a section written back where the work tree holds no file
      would be the only one in it, and `validate-family.py` reads HEAD's
      file alone, not the index's."""
    whys = {why for _, _, why in left} | set(whole)
    said = gitmodules_cures(whys, modules)
    if modules.cut:
        left = [entry for entry in left if entry[2] not in CUT_WHYS]
        whys -= CUT_WHYS
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


def gitmodules_cures(whys: set[str], modules: Gitmodules) -> list[str]:
    """`cures`' sentences for a `.gitmodules` git reads nothing from, each
    in the order `cures` says them (#648, #768): a merge left unmerged,
    for a row `whys` names so; each value git dies on; a work tree file
    git cannot parse. And for a blob git read only up to such a line, or
    up to a key with no value it stops at, where a row `whys` names is
    one of `CUT_WHYS` (#856): the command that puts that file back in the
    work tree, `git checkout` from the index where git read the index's,
    which keeps what was staged, and from HEAD where it read HEAD's, then
    the file mended, or the key given a value git takes (`TAKES`) or its
    line taken out, and committed. The index's is put back with
    `--ignore-skip-worktree-bits`: in a sparse checkout that leaves
    `.gitmodules` out, its entry is skip-worktree, and `git checkout --
    .gitmodules` matches no file there (RV877's NIT-3, measured, git
    2.43.0); with the flag it puts the file back there and in any other
    work tree. HEAD's is put back only where the index holds no entry,
    so no skip-worktree bit, and `git checkout HEAD` puts it back in a
    sparse checkout too. `git config -f .gitmodules --list`
    takes a key with no value, so it is pointed at for the line alone."""
    said = []
    if UNMERGED in whys:
        said.append(f"Resolve the merge in {GITMODULES} and `git add "
                    f"{GITMODULES}`, then run this again.")
    if modules.refused:
        given = "; ".join(
            f"give `{spelled(key)}` a value git takes, "
            f"{TAKES[key.rpartition('.')[2]]}, or take that line out"
            for key in dict.fromkeys(key for key, _ in modules.refused))
        said.append(f"{given[:1].upper()}{given[1:]}, and commit "
                    f"{GITMODULES}. `{PYTHON} "
                    "scripts/validate-family.py --no-members` prints the "
                    "commands.")
    if modules.unreadable:
        said.append(f"Mend {GITMODULES} by hand (`git config -f "
                    f"{GITMODULES} --list` says where it breaks), and "
                    "commit it.")
    if modules.cut and whys & CUT_WHYS:
        head = modules.cut == HEAD_GITMODULES
        put_back = shlex.join([
            "git", "checkout",
            *(["HEAD"] if head else ["--ignore-skip-worktree-bits"]),
            "--", GITMODULES])
        whose = f"{'HEAD' if head else 'the index'}'s {GITMODULES}"
        key = modules.cut_key
        mend = (f"`{spelled(key)}`, a key with no value: give it a value "
                f"git takes, {TAKES[key.rpartition('.')[2]]}, or take that "
                "line out" if key else
                "a line it cannot parse: mend it by hand (`git config -f "
                f"{GITMODULES} --list` says where it breaks)")
        said.append(f"`{put_back}` puts back {whose}, which git read only "
                    f"up to {mend}, and commit it.")
    return said


def reason(why: str, stopper: str | None, modules: Gitmodules) -> str:
    """`why` as (a)'s line says it: `STOPPED` names the gitlink git stopped
    at, and `REFUSED` each entry of `.gitmodules` git refused, as "`<key>`
    is `<value>`", or "has no value" (#768)."""
    if why == STOPPED:
        return STOPPED.format(spelled(stopper))
    if why == REFUSED:
        return REFUSED.format(" and ".join(
            f"`{spelled(key)}` " + ("has no value" if value is None
                                     else f"is `{spelled(value)}`")
            for key, value in modules.refused))
    return why


class Gitmodules(NamedTuple):
    """`.gitmodules` as (a) asks it (#648), read by `gitmodules_sections`.

    `given` counts the sections that give each path, every section kept, as
    `validate-family.py` reads them for the findings (a)'s line names:
    `member-gitmodules-absent` and `gitmodules-path-twice`. `read` is
    `{path: name}`, the section git reads for each path, and `urls` is
    `{name: url}`, the url git takes from each, as git's own parser has
    them. `unmerged` says a merge left the file unmerged in the index, and
    `refused` holds each `(submodule.<name>.<key>, value)` git dies on as
    it reads the file, None for a key with no value (#768): git reads
    nothing from it then, and the three are empty. `unreadable` says the
    work tree's file is one `git config --list` cannot parse, which git
    dies reading: the three are empty then too. `cut` is the blob git read
    only up to such a line, as `gitmodules_source` names it,
    `HEAD:.gitmodules` or the index's object id, where it read an entry
    before it, or the blob is the index's (`gitmodules_listed`, #856):
    the three hold what it read,
    and `cures` writes no section back. Empty where git read the whole
    file, or nothing. `cut_key` is the `submodule.<name>.<key>` with no
    value that cut it, where that is what git stopped at
    (`ends_blob_reading`), a line `git config --list` takes, and empty
    where a line it cannot parse did."""

    given: Counter
    read: dict[str, str]
    urls: dict[str, str]
    unmerged: bool = False
    refused: tuple[tuple[str, str | None], ...] = ()
    unreadable: bool = False
    cut: str = ""
    cut_key: str = ""


def gitmodules_sections(root: Path) -> Gitmodules:
    """`.gitmodules` as `git submodule update` reads it: the work tree's
    file, which a fresh clone takes from HEAD, or, where the work tree has
    none, as a deletion not yet committed or a sparse checkout leaves it,
    the index's, then HEAD's (`gitmodules_source`, #768), each of the
    last two, a blob, up to a line git cannot parse, as git reads it,
    and `cut` where it read an entry before that line, or the blob is
    the index's (`gitmodules_listed`, #856), or up to a key with no value
    git stops at, `cut` and `cut_key` (`gitmodules_entries`). Nothing
    where none holds one, or git cannot read it: git has no url for any
    submodule then either.
    Nothing, and `unreadable`, where that is the
    work tree's file and `git config --list` cannot parse it: git dies
    reading it (`bad config line`), before it checks out any member.
    Nothing, and `unmerged`, where the index holds the file only at a
    merge's conflict stages (`git ls-files -s`): git reads no
    `.gitmodules` at all then, whatever the work tree holds
    (`repo_read_gitmodules`), and its init dies at the first gitlink.
    Nothing, and `refused`, where git dies on an entry as it reads the
    file (`refused_value`, #768), before it checks out any member.

    `read` and `urls` keep git's own rules (submodule-config.c), which
    drop what `git config --list` keeps (`gitmodules_entries`,
    `read_sections`)."""
    nothing = Gitmodules(Counter(), {}, {})
    source = gitmodules_source(root)
    if source is None:
        return nothing._replace(unmerged=True)
    listed = gitmodules_listed(root, source)
    if listed is None:
        return nothing._replace(unreadable=os.path.isfile(root / GITMODULES))
    printed, cut = listed
    entries, ended = gitmodules_entries(root, printed, source[0] == "--blob")
    refused = tuple(dict.fromkeys(
        (f"submodule.{name}.{key}", value)
        for name, key, value, ignored in entries
        if not ignored and refused_value(root, key, value)))
    if refused:
        return nothing._replace(refused=refused)
    return read_sections(entries)._replace(
        cut=source[1] if cut or ended else "", cut_key=ended)


def gitmodules_source(root: Path) -> list[str] | None:
    """What `git config` is given to read the `.gitmodules` git reads
    (`config_from_gitmodules`, #768): `--file` for the work tree's, where
    there is one, else `--blob` for the index's at stage 0, else HEAD's.
    None where the index holds it only at a merge's conflict stages."""
    try:
        stages = git_out(["ls-files", "-s", "-z", "--", GITMODULES],
                         cwd=root, binary=True)
    except Refusal:
        stages = b""
    source = ["--blob", HEAD_GITMODULES]
    for record in stages.split(b"\0"):
        meta, _, name = record.partition(b"\t")
        fields = meta.split()
        if name != GITMODULES.encode() or len(fields) != 3:
            continue
        if fields[2] != b"0":
            return None
        source = ["--blob", fields[1].decode("ascii")]
    if os.path.lexists(root / GITMODULES):
        return ["--file", GITMODULES]
    return source


def gitmodules_listed(root: Path, source: list[str]
                      ) -> tuple[bytes, bool] | None:
    """What `git config -z --no-includes --list` prints of the
    `.gitmodules` that `source` names (`gitmodules_source`), and whether
    git stopped short of the file's end at a line it cannot parse, or
    None where git cannot read it (#856).

    A BLOB IS READ UP TO A LINE GIT CANNOT PARSE. `git config --blob`
    prints the entries before that line, then `bad config line`, and
    exits 128. Git's submodule reader, which reads the index's or HEAD's
    file where the work tree has none, takes those same entries, says
    the same line as an error, not a die, and goes on (measured, git
    2.43.0): so what was printed is what git read, and a bad line before
    the first section leaves nothing, as git reads nothing. A work tree
    file with such a line is None: git dies reading it. Git is run as
    `git_out` runs it.

    TOLD BY THE EXIT CODE, NEVER GIT'S WORDS, which a git built with its
    translations prints in the person's language: a blob's listing that
    exits 128 is read for what it printed, whatever it says on stderr.
    The other 128 met is a blob git cannot find (`HEAD:.gitmodules`
    where HEAD holds none, #611), which prints nothing, and empty
    stdout reads as the same `Gitmodules` that None gives for a blob:
    no entry, and nothing `unreadable`, since a blob is read only where
    the work tree holds no file. So HEAD's, printing nothing, is no
    `cut`: it may be no file at all. The index's is, printing nothing or
    not: `git ls-files -s` gave its object id, so the blob is there, and
    a 128 can only be a line git cannot parse, the first included
    (RV877's SHOULD-2).

    NO `[include]` IS FOLLOWED (`--no-includes`), as git's submodule
    reader follows none. `git config --blob` follows one by default: a
    relative one stopped its listing there (`relative config includes
    must come from files`), where git reads on, and an absolute one's file
    was listed with the blob's own entries, where git reads the blob's
    alone. A work tree file's includes are not followed by default
    either."""
    proc = subprocess.run(["git", "config", "-z", "--no-includes", *source,
                           "--list"],
                          cwd=str(root), capture_output=True, check=False)
    if proc.returncode == 0:
        return proc.stdout, False
    if source[0] == "--blob" and proc.returncode == 128:
        return proc.stdout, bool(proc.stdout) or source[1] != HEAD_GITMODULES
    return None


def gitmodules_entries(root: Path, listed: bytes, blob: bool
                       ) -> tuple[list[tuple[str, str, str | None, bool]],
                                  str]:
    """`(name, key, value, ignored)` for each `submodule.<name>.<key>` that
    `git config -z --list` printed in `listed`, in file order, as git's
    submodule reader meets them: None for a key with no value, and
    `ignored` for a section git ignores whole, whose name is empty or has
    a `..` component, split on `/` and on a backslash (git warns `ignoring
    suspicious submodule name`), a value git would die on included. In the
    index's or HEAD's file, a `blob`, git reads nothing after a key it
    refuses with no value (`ends_blob_reading`), and that key, as
    `submodule.<name>.<key>`, is returned beside them; else nothing."""
    entries: list[tuple[str, str, str | None, bool]] = []
    for record in listed.split(b"\0"):
        key, valued, value = record.decode("utf-8",
                                           "surrogateescape").partition("\n")
        section, _, variable = key.rpartition(".")
        if not section.startswith("submodule."):
            continue
        name = section[len("submodule."):]
        ignored = not name or ".." in name.replace("\\", "/").split("/")
        if blob and not ignored and not valued and ends_blob_reading(
                root, variable):
            return entries, f"submodule.{name}.{variable}"
        entries.append((name, variable, value if valued else None, ignored))
    return entries, ""


def ends_blob_reading(root: Path, key: str) -> bool:
    """Whether a `key` with no value ends git's reading of the index's or
    HEAD's `.gitmodules`, a blob, where `bad config line` is an error and
    no die (#768): each key git refuses with no value, but a `branch` only
    where git does not crash on it (`crashes_on_branch`); before 2.43.1
    git crashes on it there too, and `refused_value` names it. Measured on
    git 2.43.0 (#856): a bare `url`, `path`, `update` or `ignore` in a
    blob is `missing value` and `bad config line`, and git reads no
    further; a bare `branch` crashes it (exit 139); a bare `shallow`,
    `fetchRecurseSubmodules` or `active` is read as true, and git reads
    on."""
    return key in NO_VALUE_REFUSED and (key != "branch"
                                        or not crashes_on_branch(root))


def read_sections(entries: list[tuple[str, str, str | None, bool]]
                  ) -> Gitmodules:
    """`Gitmodules` of `entries` (`gitmodules_entries`) where git refuses
    none. `given` counts every section that gives a path, an ignored one
    too. `read` and `urls` keep git's rules: a section git ignores gives
    neither; a `path` or `url` that begins with `-` is dropped, and the
    value before it stands (`may be interpreted as a command-line
    option`); where two sections give one path, the later in the file
    decides, as a later value in one section replaces an earlier, and a
    section that gives a path again lets go of the one it gave, even where
    a later section gave that one too: git then reads no section there."""
    sections: dict[str, dict[str, str]] = {}
    read: dict[str, str] = {}
    held: dict[str, str] = {}
    urls: dict[str, str] = {}
    for name, key, value, ignored in entries:
        sections.setdefault(name, {})[key] = "" if value is None else value
        if ignored or value is None or value.startswith("-"):
            continue
        if key == "path":
            if name in held:
                read.pop(held[name], None)
            held[name] = value
            read[value] = name
        elif key == "url":
            urls[name] = value
    return Gitmodules(Counter(keys["path"] for keys in sections.values()
                              if "path" in keys), read, urls)


def refused_value(root: Path, key: str, value: str | None) -> bool:
    """Whether git 2.43 dies reading a `.gitmodules` that gives a submodule
    `value` for `key`, None for no value (#768), as `parse_config` in its
    submodule-config.c reads the key: a `path`, `url`, `update` or
    `ignore` with no value (`bad config line`), and a `branch` with none
    (it crashes, and git 2.43.1 and later refuse it as they refuse a `url`
    with none); an `update` other than `none`, `checkout`, `rebase` or
    `merge`, in that case, a `!command` included (`invalid value`); a
    `shallow` that is no boolean (`bad boolean config value`); and a
    `fetchrecursesubmodules` that is neither a boolean nor `on-demand`. An
    `ignore` it does not know is a warning, and any other key takes any
    value."""
    if value is None:
        return key in NO_VALUE_REFUSED
    if key == "update":
        return value not in UPDATE_VALUES
    if key == "shallow" or (key == "fetchrecursesubmodules"
                            and value != "on-demand"):
        return git_bool(root, value) is None
    return False


def crashes_on_branch(root: Path, version: str | None = None) -> bool:
    """Whether this git crashes reading a `.gitmodules` that gives a
    submodule a `branch` with no value (#768): every git before 2.43.1
    does, in the index's or HEAD's file too, where a later git reads that
    line as the end of the file (`BRANCH_READ_SINCE`). `version` is what
    `git version` printed, for a test to give; None asks this git. A git
    whose version cannot be read is taken for one that crashes: the run
    then fails naming the key, a cure true on every git, rather than pass
    a member git never asked for as the missing credential's."""
    if version is None:
        try:
            version = git_out(["version"], cwd=root)
        except Refusal:
            return True
    found = GIT_VERSION_RE.match(version)
    return (found is None
            or tuple(map(int, found.groups())) < BRANCH_READ_SINCE)


def git_bool(root: Path, value: str | None) -> bool | None:
    """`value` read as a boolean by git itself, which reads one so for
    every key (`git config --type=bool`, its `git_parse_maybe_bool`):
    `true`, `yes`, `on` in any case, a number other than 0, or no value at
    all are true, and `false`, `no`, `off`, 0 and an empty value false.
    None where git takes it for no boolean, and dies. It is asked as the
    `--default` of a key looked up in an empty file, so no `probe.value`
    in any of the person's own config scopes is read in its place."""
    if value is None:
        return True
    try:
        answer = git_out(["config", "--file", os.devnull, "--type=bool",
                          f"--default={value}", "--get", "probe.value"],
                         cwd=root)
    except Refusal:
        return None
    return answer == "true"


def submodule_config(root: Path) -> dict[str, list[str | None]]:
    """Every `submodule.` key this repository's git config sets, in every
    scope git reads, with each value it gives, None for no value, as git's
    init asks them: `submodule.active` and its patterns, a section's own
    `submodule.<name>.active` (#768), and `submodule.<name>.url` as an
    earlier init writes it. Empty where git lists none."""
    try:
        config = git_out(["config", "-z", "--get-regexp", r"^submodule\."],
                         cwd=root, binary=True)
    except Refusal:
        return {}
    found: dict[str, list[str | None]] = {}
    for record in filter(None, config.split(b"\0")):
        key, valued, value = record.decode("utf-8",
                                           "surrogateescape").partition("\n")
        found.setdefault(key, []).append(value if valued else None)
    return found


def has_url(modules: Gitmodules, config: dict[str, list[str | None]],
            path: str) -> bool:
    """Whether git's init finds a url for the gitlink at `path`: in the
    section git reads for that path (`Gitmodules.read`), or in the git
    config under that section's name, as an earlier init writes it. Where
    git reads no section there it has none, whatever the config holds."""
    name = modules.read.get(path)
    return name is not None and (name in modules.urls
                                 or f"submodule.{name}.url" in config)


def init_stop(root: Path, modules: Gitmodules,
              config: dict[str, list[str | None]]) -> str | None:
    """The gitlink `git submodule update --init` dies at, or None: the first
    in the index, in index order, that its init step asks about and has no
    url for (`No url found for submodule path`, exit 128), before it
    checks out any member (#648).

    ASKED AS GIT 2.43 ASKS IT, of the index, `modules` and `config`, this
    repository's git config. Every gitlink the index records is asked, but
    where the config sets `submodule.active`, as a recursive clone sets it
    (`.`), only those git counts active (`active`), and never one no
    section git reads gives a path. A gitlink git has no url for
    (`has_url`) stops it. So a stray case variant or a member mounted by
    hand stops a plain clone's update, and leaves a recursive clone's to
    the credential. Read nothing, it answers None."""
    try:
        index = git_out(["ls-files", "-s", "-z"], cwd=root, binary=True)
    except Refusal:
        return None
    for record in index.split(b"\0"):
        meta, _, entry = record.partition(b"\t")
        if meta.split()[:1] != [GITLINK_MODE]:
            continue
        path = entry.decode("utf-8", "surrogateescape")
        if ("submodule.active" in config
                and not active(root, modules, config, path)):
            continue
        if not has_url(modules, config, path):
            return path
    return None


def active(root: Path, modules: Gitmodules,
           config: dict[str, list[str | None]], path: str) -> bool:
    """Whether git's init counts the gitlink at `path` active where the
    config sets `submodule.active` (`is_tree_submodule_active` in git
    2.43's submodule.c): never where no section git reads gives that path;
    else as the section's own `submodule.<name>.active` says, its last
    value read as a boolean (`git_bool`), where the config sets one that
    is (#768); else where one of `submodule.active`'s patterns names it
    (`pattern_names`)."""
    name = modules.read.get(path)
    if name is None:
        return False
    own = config.get(f"submodule.{name}.active")
    flag = git_bool(root, own[-1]) if own else None
    if flag is not None:
        return flag
    return any(pattern_names(pattern, path)
               for pattern in config["submodule.active"])


def pattern_names(pattern: str | None, path: str) -> bool:
    """Whether a `submodule.active` pattern names `path` (#768). A plain
    path, as `git clone --recurse-submodules=<path>` writes one, names
    itself and every path under it, as git's pathspec does, and `.` names
    every path. A pattern with pathspec magic (a leading `:`), a glob
    character or a backslash, or with an empty, `.` or `..` component past
    a leading `./`, is read as naming every path, as every pattern was
    before: this does not match those as git does."""
    if (pattern is None or pattern.startswith(":")
            or any(char in pattern for char in "*?[\\")):
        return True
    while pattern.startswith("./"):
        pattern = pattern[2:]
    pattern = pattern.rstrip("/")
    if pattern in ("", ".") or any(part in ("", ".", "..")
                                   for part in pattern.split("/")):
        return True
    return path == pattern or path.startswith(pattern + "/")


def unfetchable(root: Path, rows: list[dict], exited_0: bool
                ) -> tuple[list[tuple[dict, str, str]], str | None,
                           Gitmodules]:
    """`(row, path, why)` for each row whose member (a) left NOT CHECKED OUT
    where no credential would check it out (#648), in row order; the
    gitlink git's init died at (`init_stop`), or None; and `.gitmodules`
    as it was read, for `cures`.

    Asked of this holder's own records, never of git's words: any row at
    all while a merge leaves `.gitmodules` unmerged in the index, since git
    then reads no section and asks for no credential, or while the file
    gives a value git dies on (`Gitmodules.refused`, #768), or is a work
    tree file git cannot parse (`Gitmodules.unreadable`); a row at
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
    was. A path two rows give is said once. Where every row's member is
    checked out and git did not exit 0, `.gitmodules` is read all the
    same, and git's init asked where it stopped, for `fetch_members` to
    ask why git updated none (`updated_none`): this returned before
    `init_stop` there, so a run whose update git's init stopped said
    `family bootstrap ok` (#879)."""
    left: dict[str, dict] = {}
    for row in rows:
        if not (member_path(root, row) / ".git").exists():
            left.setdefault(row_path(row), row)
    if not left and exited_0:
        return [], None, Gitmodules(Counter(), {}, {})
    modules = gitmodules_sections(root)
    config = submodule_config(root)
    stopper = None if exited_0 else init_stop(root, modules, config)
    found: list[tuple[dict, str, str]] = []
    for path, row in left.items():
        why = row_reason(root, path, modules, config, exited_0, stopper)
        if why is not None:
            found.append((row, path, why))
    return found, stopper, modules


def row_reason(root: Path, path: str, modules: Gitmodules,
               config: dict[str, list[str | None]], exited_0: bool,
               stopper: str | None) -> str | None:
    """Why `unfetchable` says the member at `path`, not checked out, is
    none a credential would check out (#648, #768), in the order it asks,
    or None where it is the missing credential's."""
    unread = file_reason(modules)
    if unread is not None:
        return unread
    if recorded_gitlink(root, path) is None:
        return NO_GITLINK
    if not modules.given[path]:
        return NO_SECTION
    if not has_url(modules, config, path):
        return NO_URL
    if exited_0:
        return EXITED_0
    return None if stopper is None else STOPPED


def file_reason(modules: Gitmodules) -> str | None:
    """Why git read nothing from `.gitmodules` (#648, #768), as (a)'s line
    says it, or None where it read the file: a merge left it unmerged, it
    gives a value git dies on, or it is a work tree file git cannot
    parse."""
    if modules.unmerged:
        return UNMERGED
    if modules.refused:
        return REFUSED
    return UNREADABLE if modules.unreadable else None


def updated_none(left: list[tuple[dict, str, str]], stopper: str | None,
                 modules: Gitmodules) -> str | None:
    """Why git updated no member, where every row's member is checked out
    (`left` empty) and git did not exit 0, or None: what `file_reason`
    says, or `STOPPED` where git's init died at a gitlink it has no url
    for (`stopper`, `init_stop`), before it updated any (#879). None
    where it asked for a credential, as a leg's fetch does, and where
    `left` names a row, which (a)'s line says why of."""
    if left:
        return None
    return file_reason(modules) or (None if stopper is None else STOPPED)


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
    """(b) One member's own `make <target>`. Returns a failure line, or None:
    one naming the exit code of the member's command where make names it,
    else make's own (`run_make`, #839)."""
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
    returncode, own = run_make(make, target, path)
    sys.stdout.flush()
    if returncode == 0:
        return None
    if own is not None:
        return f"{project} (make {named}: the member's command exited {own})"
    return (f"{project} (make {named} exited {returncode} and printed no "
            "`Error <code>` line for a command of the member's: make's own "
            "message above says what failed)")


#: The line GNU make prints where a command of the target exits non-zero,
#: `make: *** [Makefile:44: bootstrap] Error 1` (`make[1]:` in a make run by
#: make, `*** [bootstrap] Error 1` before make 4.0): the command's own exit
#: code, which make's does not carry, since make exits 2 for any command
#: that fails (#839).
MAKE_ERROR_RE = re.compile(rb"\*\*\* \[[^\n]*\] Error (\d+)\s*$")


def run_make(make: str, target: str, cwd: Path) -> tuple[int, int | None]:
    """(b) `make <target>` in a member, as `(make's exit code, the exit code
    of the member's command it names)`, the second None where make printed
    no `MAKE_ERROR_RE` line (#839).

    MAKE'S OWN CODE TELLS NOTHING APART. GNU make exits 2 for any command
    that fails, measured (GNU Make 4.3) for a command exiting 1, 2, 3 or
    126, and 2 for a failure of its own (`No rule to make target`), so the
    line said `make bootstrap exited 2` for the member's own `bootstrap
    FAILED` (1, a finding), for a refusal (2) and for make's own failure
    alike (w764b, for lane 4). The command's code is the one make names
    in its `Error <code>` line, the last on stderr, so make's stderr is
    passed on to this run's own as it comes and that line read from the
    end of it; a make that prints none, one of its own failures, a command
    killed by a signal, or a make speaking another language, leaves make's
    code alone. The member's command is never run around make: another
    target than `bootstrap` (`--members-make validate`) has no script of
    its own to call, as `make siblings` calls a member's
    `scripts/bootstrap.py`."""
    proc = subprocess.Popen([make, target], cwd=str(cwd),
                            stderr=subprocess.PIPE)
    tail = b""
    for chunk in iter(lambda: proc.stderr.read1(65536), b""):
        passed_on(chunk)
        tail = (tail + chunk)[-4096:]
    proc.stderr.close()
    returncode = proc.wait()
    found = [MAKE_ERROR_RE.search(line) for line in tail.splitlines()]
    named = [int(match.group(1)) for match in found if match]
    return returncode, (named[-1] if named else None)


def passed_on(chunk: bytes) -> None:
    """`chunk` of what a member's make wrote to its stderr, written to this
    run's as it came (#839): as its bytes, after what this run wrote there
    before, or as text where stderr has no byte buffer."""
    stream = sys.stderr
    if stream is None:
        return
    stream.flush()
    sink = getattr(stream, "buffer", None)
    if sink is None:
        stream.write(chunk.decode("utf-8", "replace"))
        stream.flush()
        return
    sink.write(chunk)
    sink.flush()


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
