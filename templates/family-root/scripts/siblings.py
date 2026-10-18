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

WHICH NAME `<Family>` IS (#629). It is the holder's REPOSITORY name: the
basename of `repository:` in `family.yaml`, which is what `family.py init
--family` took and what `git clone` names the holder's directory. It is
NEVER `name:`, the display name (`--name`), which is only a title and can
differ: `--family Quill --name QuillWorks` is a holder cloned as `Quill`, in
a folder named `Quill`, and a run still says `QuillWorks` on its first line.
The holder's own README names the folder the same way (`{{FAMILY}}`, not
`{{FAMILY_NAME}}`), and a run says which name it means, on a line of its own,
wherever the two differ (`family_name_note`).

TWO COPIES OF EVERY MEMBER, ON PURPOSE. `members/<Project>` inside the holder
is a PINNED, DETACHED checkout: it is what `make bootstrap` and `make
validate` read, and it is detached because a pin is a commit and not a branch.
The clone this command puts BESIDE the holder is where a human works — its own
`origin`, its own tracking branch, its own worktrees — and the family follows
it afterwards with `family.py bump`. Neither copy is the other's mirror, and
this command never touches the pinned one.

WHAT IT DOES:

  FIRST    THE PARENT-FOLDER CHECK, BEFORE ANYTHING IS CLONED (#543). When
           the holder's parent directory is not named after the family, this
           WARNS, prints the exact `mv` and STOPS, exit 1: nothing is cloned,
           fetched or moved. A member cloned first would land in the wrong
           folder, and the re-run after the move would clone it a second time
           beside the moved holder. It MOVES NOTHING itself. Relocating a
           checkout out from under somebody's shell, editor and agent lanes
           breaks linked worktrees, whose `.git` files carry absolute paths,
           and is the one act this standard refuses everywhere else: done by
           surprise, with no hand on it. The doctor pattern, not a mover.

           A LINK named after the family, beside the holder's (resolved)
           parent directory and leading to it, passes the check: that is the
           family folder reached through a link, and the members are cloned
           into the directory it leads to.

  then, per member row in `family.yaml`:

  ABSENT   `git clone --recurse-submodules` from the SAME url `make bootstrap`
           resolves — `.gitmodules` first, `family.yaml`'s `repository:` as
           the fallback — with the same credential, resolved the same way, ON
           THE MEMBER'S TRACKING BRANCH, and then the member's OWN
           `scripts/bootstrap.py`, which puts its legs on their tracking
           branches AT their pins. The result is a working clone on its
           branch, not a detached one.

           THE TRACKING BRANCH IS THE ONE THE MEMBER DECLARES (#543): the
           `tracking_branch:` of its own `project.yaml`, read in the PINNED
           copy under `members/`, which is this holder's record of the member.
           A plain clone checks out the remote's DEFAULT branch, and the two
           differ when a member tracks another branch. A member whose pinned
           copy is not checked out (`make bootstrap` checks it out), or that
           declares none, or a value that is no branch name (`5`, a control
           character), is cloned on its remote's default branch, as it
           always was, and its line says so. Nothing else is read for it:
           `.gitmodules` carries no `branch=`, and `family.yaml`'s
           `tracking_branch:` is the HOLDER's branch, the one `family.py`
           refuses to commit on.

           `--no-local` (#461): a url that is a path on this machine is read
           through git, as a remote is, and not copied file by file, so a
           repack running in it cannot fail the clone half way (#440).

  PRESENT  `git fetch`, AND NOTHING ELSE. No checkout, no reset, no pull, no
           stash, no branch switch. Somebody is working in that clone — that
           is what it is for — and a utility that "helpfully" moved their HEAD
           would be the single most destructive thing in this standard. The
           clone is first verified to BE that member (its `origin` names the
           row's repository and its own `project.yaml` id is the row's `id`);
           when it is not, that is reported and SKIPPED, never overwritten.

IDEMPOTENT. A second run is every member `present`, one `git fetch` each, and
exit 0. That is what makes it safe to put in a handoff document.

DISPATCHING A VERB INTO THE SIBLINGS: `--make <target>`

    make park                 # = scripts/siblings.py --make park
    python3 scripts/siblings.py --make park --make-arg ARGS=--dry-run

`--make <target>` runs `make <target>` in each member's WORKING CLONE beside
the holder — the estate half of #77's ruling 5 (2026-09-09) and what the
holder's `park` and `resume` targets use. It CLONES NOTHING AND FETCHES
NOTHING: dispatching is all it does, so a `make park` cannot move a member
under somebody's hand. The sibling is the same path this command places and
is verified the same way (its `origin`, and its own `project.yaml` id), for
the reason the whole file exists: a verb run in a directory that is not this
member is worse than a verb not run at all.

WHY THE SIBLING AND NOT `members/<Project>`. The pinned copy in the holder is
DETACHED and exists for `bootstrap` and `validate`; the sibling is where a
human works, so it is where the features, the worktrees and the in-flight
work are. A `make park` walking `members/` would report "nothing to park" for
every member while the person's work sat untouched beside it — the wrong
question, answered confidently.

Per member: a verified clone gets `make <target>` with every `--make-arg`
appended verbatim to its command line (that is how the holder's `make park
ARGS=--dry-run` reaches every member), its own output streamed where it
happens under a `--- <Project>: make <target> ---` header; a member with NO
working clone is reported and SKIPPED, naming `make siblings`; one that is
not this member is reported and skipped exactly as it is above. Every member
is tried — a refusal never stops the ones after it — and the summary names
each outcome. `--dry-run` prints what would run and runs nothing.

IT CONFERS NOTHING, and neither does the layout. A folder is navigation.

WHAT IT PRINTS IS A PERSON'S TEXT (#454). `family.yaml`'s `name:`, a member's
`project:` and `path:`, a url, a branch and every directory name come from a
manifest or a disk, and this file does not choose them. A stdout that cannot
hold what they say raised: `name: "a\\ud83db"` (a lone surrogate) or `日本`
under `PYTHONIOENCODING=ascii` ended `make siblings`, `make park` and `make
resume` in a `UnicodeEncodeError` on the first line, before a member was
touched (`park`, which exists to save work, parked nothing), and this file's
own dash raised for EVERY name on that stdout. A raw ESC or CR in a value
reached the terminal as the control it is. So, as both roots' `bootstrap.py`
do (#391): `main` makes a stdout that would raise escape what it cannot
encode (`escape_unencodable_stdout`), and every value a line prints from a
manifest, a member row or a disk goes through `spelled`, which writes the
controls, the surrogates, the line and paragraph separators and the
bidirectional controls as the escape Python spells them and prints every
other character as it is. What a member's own `make` is handed is the RAW
target, and the `mv` lines a person pastes are quoted, never spelled: an
escape in a command would not run as typed. Git's own words are left as git
wrote them.

EXIT CODES
    0  every member is beside the holder; nothing to report. With `--make`:
       every member RAN and exited 0
    1  a FINDING a human can act on: a holder whose parent folder is not
       named after the family, nor linked as it (nothing is cloned until
       it is moved), a
       sibling that is a DIFFERENT repository, a clone that failed (a
       tracking branch its remote does not have included), a member's own
       bootstrap that went red. With
       `--make`: any member that was skipped or whose verb exited non-zero —
       a `make resume` that skipped every member because nobody had run `make
       siblings` must never read as success
    2  a REFUSAL: the question could not be asked — no `family.yaml`, no
       `git`, no `make` for a `--make` run. An unanswerable question is never
       an implicit pass.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# "IS THIS THE SAME REPOSITORY" IS IMPORTED, NEVER RE-SPELLED (2026-09-12,
# #155). This file REFUSES to fetch into a clone beside the holder whose
# `origin` is not the member's remote (`verify_sibling` below), and
# `shape-doctor.py`'s `members` row REPORTS whether that same directory is
# the member's working clone. While each answered out of its OWN copy of the
# rule they could disagree about one directory, and for three commits they
# did (#146, #147). `repo_shape.py` is copied in beside this file by
# `family.py init` and travels with it in `contracts/shape-pin.yaml`, so the
# rule is one function both tools import — and `join_remote` is the
# arithmetic `resolve_relative` hands git's relative-url rule to.
# WHAT IT PRINTS IS SPELLED, AND THE TWO FUNCTIONS ARE #391's (#454).
# `escape_unencodable_stdout` and `spelled` are written once, in
# `repo_shape.py`, and both roots' `bootstrap.py` import them from there; this
# file imports `bootstrap` already, so it needs nothing a holder does not
# carry.
from repo_shape import (  # noqa: E402
    PYTHON, Refusal, escape_unencodable_stdout, find_repo_root, join_remote,
    load_yaml, remote_local_path, repo_basename, same_repository, spelled,
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

#: A `make` TARGET NAME, and the whole of what `--make` may be: a letter, then
#: letters, digits, `_`, `.` and `-`. `--make-arg` is narrower still — a make
#: `NAME=value` ASSIGNMENT whose value carries no control character, the
#: newline especially.
#:
#: WHY THEY EXIST. Both values arrive on this command's own command line and
#: both end up in the argv of a subprocess, so they are checked by pattern
#: before anything runs — and checked again at the `subprocess.run` itself, so
#: the check and the call are one screen apart for the next reader and for a
#: scanner (SonarCloud `pythonsecurity:S8705` on PR #80). Nothing was
#: injectable to begin with: the call is a LIST with no shell, so `park; rm
#: -rf /` would be ONE argument make has no rule for, never a second command.
#: They are narrow because the holder only ever passes one shape of either —
#: `make park` and `ARGS=<flags>` — so anything else is a mistake worth
#: refusing by name rather than a case worth carrying.
MAKE_TARGET_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.-]*")
MAKE_ASSIGNMENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=[^\x00-\x1f\x7f]*")

#: A `.gitmodules` section name git ignores, every key of it
#: (`check_submodule_name`): `..` as a component, between `/` or `\`. An
#: empty name is ignored too. The doctor's `members` row skips the same
#: (#733).
DOTDOT_COMPONENT = re.compile(r"(?:^|[/\\])\.\.(?:[/\\]|$)")

#: The keys of a section that git refuses the WHOLE `.gitmodules` over when
#: one is given with no value at all (measured, git 2.43: `bad config line
#: N`, exit 128, and a bare `branch` crashes it) (#733).
VALUED_KEYS = ("path", "url", "ignore", "update", "branch")

#: A boolean as git reads one in `.gitmodules` (`git_config_bool`): one of
#: these words in any case, as they stand, or an integer as `strtoimax`
#: reads it after the white space it skips, base 0, times 1024 per `k`, `m`
#: or `g`, from -2**31 to 2**31 - 1, the range git 2.55 checks (#733).
GIT_BOOL_WORDS = ("", "true", "yes", "on", "false", "no", "off")
GIT_INT = re.compile(r"([+-]?)(0[xX][0-9a-fA-F]+|0[0-7]*|[1-9][0-9]*)"
                     r"([kKmMgG]?)")


# ---------------------------------------------------------------------------
# where a member comes from
# ---------------------------------------------------------------------------


def git_dies_on(field: str, value: str) -> bool:
    """Whether git `die()`s on this value of a `.gitmodules` key, and so
    reads no submodule at all (#733), as the doctor's `members` row asks
    it: an `update` other than these four (`!command` included), a
    `shallow` that is no boolean, a `fetchRecurseSubmodules` that is
    neither a boolean nor `on-demand`. git lists a key in lower case."""
    if field == "update":
        return value not in ("none", "checkout", "rebase", "merge")
    if (field not in ("shallow", "fetchrecursesubmodules")
            or value.lower() in GIT_BOOL_WORDS
            or (field == "fetchrecursesubmodules" and value == "on-demand")):
        return False
    number = GIT_INT.fullmatch(value.lstrip(" \t\n\v\f\r"))
    if number is None:
        return True
    sign, digits, unit = number.groups()
    base = 16 if digits[:2] in ("0x", "0X") else 8 if digits[0] == "0" else 10
    # " kmg".index: no unit is 1024 ** 0, `k` 1024 ** 1, and so on.
    scaled = int(digits, base) * 1024 ** " kmg".index(unit.lower() or " ")
    return not -2 ** 31 <= (-scaled if sign == "-" else scaled) < 2 ** 31


def submodule_urls(root: Path) -> dict[str, str]:
    """`{submodule path: url}` out of `.gitmodules`.

    THE SAME URL `make bootstrap` USES. `git submodule update` reads
    `.gitmodules`, so a family whose members are mounted from an SSH remote,
    a mirror or (in this suite) a bare repository on disk must produce
    siblings from that same string — deriving `https://github.com/<repo>.git`
    from the manifest instead would clone a different remote from the one this
    holder is pinned against, silently, in exactly the estates that do not use
    the default spelling.

    AND READ AS GIT READS IT (#690): `git config -z --list`, the reading
    `validate-family.py`'s `_gitmodules_sections` makes and #668 gives the
    doctor's `members` row, so the two tools name one url for one member
    (#146). Each record ends in a NUL and is the key and, where it is given
    a value, a newline and the value; a key holds no newline and a value
    may, so a record is split at its FIRST one. The plain listing this read
    was split by `str.splitlines` and at the first `=`: a url holding NEL,
    U+2028, U+2029, VT, FF or U+001C to U+001E, which git keeps whole, was
    cut there (`<remotes>/caf` of `caf<NEL>e/IRRS.git`), and a section named
    `members/a=b` gave no url, so its member was cloned from the
    `repository:` guess. A section's NAME is all of its key between
    `submodule.` and the last dot, so a name holding a space, a dot, a quote
    or an `=` is read whole; only its `path` and `url` count, and the later
    value wins, as git reads the file. A byte that is not UTF-8 is still
    replaced in a VALUE (#432). A NAME keeps git's bytes, as the doctor's
    `submodule_keys` keeps them (#732): replaced, `caf\\xe9` and `caf\\xe8`
    were one section, and the path of one was given the url of the other.

    AND OF THAT LISTING, ONLY WHAT GIT READS (#733), by git's own tests, as
    the doctor's `members` row cuts the same listing (`submodule_keys`): a
    section whose name is empty or holds a `..` component is ignored whole
    (`DOTDOT_COMPONENT`); a `path` or `url` beginning with `-` is ignored,
    that key alone, so an earlier value of it still stands; a key of
    `VALUED_KEYS` given with no value at all, or a value git dies on
    (`git_dies_on`), refuses the whole file, `{}`. A key given no value at
    all is a record with NO newline (`submodule.q.url`), where `url =` is
    one with a newline and an empty value. And a section with no `path`
    mounts nothing, so its name is not read as one. git names no url for
    any of these: `git submodule init` says `No url found` or `bad config
    line`, or that the value is invalid, and a clone made from the url
    would be of a member git does not mount.
    """
    path = root / ".gitmodules"
    if not path.is_file():
        return {}
    proc = subprocess.run(["git", "config", "-z", "-f", str(path), "--list"],
                          capture_output=True, check=False)
    if proc.returncode != 0:
        return {}
    paths: dict[str, str] = {}
    urls: dict[str, str] = {}
    for record in proc.stdout.decode("utf-8", "surrogateescape").split("\0"):
        # `valued` is the newline: a key given no value at all has none.
        key, valued, value = record.partition("\n")
        # A NAME keeps git's bytes, as `submodule_keys` keeps them, so two
        # names are one only where git has one; a value is replaced (#432).
        value = value.encode("utf-8", "surrogateescape").decode(
            "utf-8", "replace")
        section, _, field = key.rpartition(".")
        if not section.startswith("submodule."):
            continue
        name = section[len("submodule."):]
        if not name or DOTDOT_COMPONENT.search(name):
            continue
        if (not valued and field in VALUED_KEYS) or git_dies_on(field, value):
            return {}
        if value.startswith("-"):
            continue
        if field == "path":
            paths[name] = value
        elif field == "url":
            urls[name] = value
    return {paths[name]: url for name, url in urls.items() if name in paths}


def resolve_relative(url: str, root: Path) -> str:
    """A `.gitmodules` url spelled `../<Repo>.git`, against THIS remote.

    Git reads a relative submodule url relative to the SUPERPROJECT'S REMOTE,
    not to any directory — one path component dropped per `..` — so a clone
    that took the string literally would fetch from wherever the process
    happens to be standing. `family.py add` writes absolute urls and never
    produces one of these; a hand-mounted member can, and the honest answer
    is git's own rule rather than a guess. The arithmetic itself is
    `repo_shape.join_remote`, which knows nothing about this machine; THIS
    function is the half that does — it reads the holder's own `origin`, and
    that is the only reason it is still here rather than beside the rest.
    """
    if not url.startswith(("./", "../")):
        return url
    base = (git_text(["remote", "get-url", "origin"], root) or "").strip()
    if not base:
        return url
    return join_remote(base, url)


def same_repository_here(one: str, two: str) -> bool:
    """`same_repository`, with THIS MACHINE'S SYMLINKS allowed to answer too.

    THE HALF OF "IS THIS THE SAME REPOSITORY" THAT NEEDS A MACHINE
    (2026-09-13, #157), and it is here for the same reason `resolve_relative`
    above is: `repo_shape.same_repository` is string arithmetic that may not
    touch a disk, and a symlink is not a fact about a string. It answers for
    two filesystem paths by EXACT equality now — the trailing `owner/repo`
    fallback used to call `/srv/a/IRRS.git` and `/other/a/IRRS.git` one
    repository — so one directory reached two ways would be two repositories
    to it: `/var/folders/…` and `/private/var/folders/…` are the same
    temporary directory on macOS, and a member cloned through one spelling
    while `.gitmodules` records the other is exactly what `verify_sibling`
    would otherwise refuse to fetch into.

    THE STRING RULE IS ASKED FIRST AND THE DISK ONLY IF IT SAYS NO, so this
    can ADD an answer and never take one away (Codex, PR #160) — which
    matters, because a mirror is allowed to be a symlink onto a storage path
    whose own tail is a serial number, and resolving one before comparing it
    against a manifest's `Org/Repo` would throw the name away.

    ONLY A PATH THAT IS ABSOLUTE HERE AND EXISTS HERE IS RESOLVED, and
    everything else is compared exactly as it was read.
    `repo_shape.remote_local_path` is the string half, imported rather than
    re-spelled (#155): it says None for a host remote, which has no path to
    resolve, and None for a relative one, because `../mirrors/Fam.git` handed
    to `realpath` would resolve against whatever directory this process is
    standing in — the trap `resolve_relative` exists to avoid. `isabs` is the
    platform asking the same question of itself: `D:/mirrors/Fam.git` is a
    path on Windows and a directory called `D:` under the process's own cwd
    on POSIX, and only one of those is worth a `realpath` (Copilot, PR #160).

    AND THE DISK'S ANSWER IS THE DISK'S, which is the whole reason one is
    asked: a case-insensitive filesystem hands back the spelling it stores
    (Windows does), so two spellings that both open one directory can be one
    repository HERE while the string rule still calls them two. #149 is
    strict on every platform because a STRING cannot know which it is; this
    half is looking at the directory.
    """
    if same_repository(one, two):
        return True
    resolved = []
    for url in (one, two):
        path = remote_local_path(url)
        if path and os.path.isabs(path) and os.path.exists(path):
            path = os.path.realpath(path)
        else:
            path = url
        resolved.append(path)
    return same_repository(*resolved)


def clone_url(root: Path, row: dict, urls: dict[str, str]) -> tuple[str, str]:
    """`(url, where it came from)` for one member."""
    path = str(row.get("path") or "")
    if path in urls:
        return resolve_relative(urls[path], root), ".gitmodules"
    repository = str(row.get("repository") or "")
    return f"https://github.com/{repository}.git", f"{MANIFEST} repository:"


def tracking_branch(root: Path, row: dict) -> tuple[str | None, str]:
    """`(the member's tracking branch, where it was read)`, or `(None, why
    there is none)` — the branch a NEW working clone is checked out on.

    THE MEMBER'S OWN DECLARATION, as this holder pins it (#543): the
    `tracking_branch:` of `project.yaml` in the pinned copy under `members/`,
    the file the member's own bootstrap reads for the same answer. It is
    read from disk, as `validate-family.py` reads that copy's `id:`, and
    only `load_yaml` is used to read it, a name every `repo_shape.py` a
    holder may have kept carries. None, with the reason, when the copy is
    not checked out or declares no branch: the clone then takes the remote's
    default branch, as it always did, and says so.

    A VALUE THAT IS NOT A BRANCH NAME IS NOT USED AS ONE, and is shown in its
    `repr`: `5` or `[main]`, and a string holding a character that does not
    print. An ESC or a newline would reach this command's output raw, where
    the member's own bootstrap escapes the same field (#391); `repr` escapes
    exactly what `isprintable` refuses, so the two agree with no import.
    """
    label = (str(row.get("path") or f"members/{row.get('project')}")
             + "/project.yaml")
    manifest = member_path(root, row) / "project.yaml"
    if not manifest.is_file():
        return None, (f"{label} is not checked out, so its tracking branch "
                      "is not known here (`make bootstrap` checks it out)")
    try:
        data = load_yaml(manifest)
    except (Refusal, OSError, ValueError):
        return None, f"{label} could not be read"
    branch = data.get("tracking_branch") if isinstance(data, dict) else None
    if branch is None or branch == "":
        return None, f"{label} declares no tracking_branch"
    if not isinstance(branch, str) or not branch.strip():
        return None, (f"{label} declares tracking_branch {branch!r}, which "
                      "is not a branch name")
    if not branch.isprintable():
        return None, (f"{label} declares tracking_branch {branch!r}, which "
                      "holds a character that does not print, so it is not "
                      "used as a branch")
    return branch, label


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


def said_of_url(text: str, url: str | None) -> str:
    """git's own text, with the url it quotes written as `spelled` writes it
    (#690).

    A `.gitmodules` url is read whole now, line feed and all, as git reads
    it, and git's `die` and `error` quote a url RAW: a line feed stays, so
    the url's second line stood at column 0 of the finding that relays the
    text, and `FINDING IRSS: forged` in a url was a FINDING line of its own.
    Every other control is written as a `?` (a tab stays), so a url holding
    an ESC as well is quoted in that form; both forms are replaced, and
    nothing is, where the url prints as it is. `place` relays git's text
    twice, and both go through here: the clone's, with the member's url,
    and a failed fetch's, with the origin of a clone made from such a url.

    A URL LONGER THAN GIT'S MESSAGE is quoted cut short, in neither form (a
    message is formatted into 4096 bytes), so the forged line survived the
    replacement: where the text holds neither, each of its lines is spelled
    and every line after the first is indented, which no FINDING line is.
    """
    if not url or spelled(url) == url:
        return text
    quoted = "".join("?" if (char < " " or char == "\x7f")
                     and char not in "\t\n" else char for char in url)
    if url not in text and quoted not in text:
        # git cuts a message at 4096 bytes, so a long url is quoted in
        # neither form: each line is spelled, and none after the first
        # starts a line of this output.
        return "\n    ".join(spelled(line) for line in text.split("\n"))
    for form in dict.fromkeys((url, quoted)):
        text = text.replace(form, spelled(url))
    return text


def git_text(args: list[str], cwd: Path) -> str | None:
    proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          check=False)
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
        # `project` is a manifest's text and `branch` a clone's (#454), so a
        # row prints them spelled; the fields still hold the raw values, which
        # the paths and the commands are made from.
        return (f"  {kind:<9} {spelled(self.project):<18} {self.state:<22} "
                f"{spelled(self.branch)}")


def project_id(path: Path) -> str | None:
    manifest = path / "project.yaml"
    if not manifest.is_file():
        return None
    try:
        data = load_yaml(manifest)
    except Refusal:
        return None
    return str(data.get("id")) if isinstance(data, dict) else None


def holds_git(path: Path) -> bool:
    """Does `path` hold a `.git`? False where that cannot be asked (#735):
    in a folder that cannot be entered (mode `000`), Python 3.12's
    `Path.exists` raises `PermissionError`, and `make siblings` and `make
    park` ended in that traceback."""
    try:
        return (path / ".git").exists()
    except OSError:
        return False


def not_a_clone(target: Path) -> tuple[str, str] | None:
    """`(what stands at target, what kind of thing it is)` for a `target`
    with no `.git` that this command will not write into, in the words its
    `NOT A CLONE` finding says it in; None for nothing at all, or an empty
    folder, which a clone goes into.

    A FILE, OR A FOLDER THAT CANNOT BE LISTED, IS NOT A CLONE TOO (#735).
    Only a folder with something in it was asked about, and `iterdir`
    raised on the other two: `NotADirectoryError` for a file, and
    `PermissionError` for a folder that can be entered and not listed (mode
    `0311`; `711` is common for another user's directory) or cannot be
    entered at all. Each ended `make siblings` in a traceback, exit 1, and
    the members after it were never placed. Nothing can tell that such a
    folder is empty, and `git clone` refuses one it cannot read. The words
    are the ones the doctor's `members` row says of the same two slots.
    """
    try:
        if not target.exists():
            return None
        if not target.is_dir():
            return "is a file, not a folder", "file"
        if any(target.iterdir()):
            return "exists, is not empty and is not a git clone", "directory"
        return None
    except OSError:
        return "is a folder that cannot be listed", "directory"


def verify_sibling(row: dict, target: Path, url: str, repository: str,
                   sibling: Sibling) -> bool:
    """Is the clone at `target` the member this row names?

    ONE definition of "is this the right clone", used by the placement half
    and by the `--make` dispatch: both of them are about to act on somebody
    else's checkout, and two readings of that question is how one of them
    starts acting on the wrong one. It sets `state` and `finding` and returns
    False when the answer is no, and touches nothing either way.
    """
    origin = git_text(["remote", "get-url", "origin"], target) or ""
    identity = project_id(target)
    # A finding is printed, and what it names comes from a manifest, a disk
    # and a clone's own config (#454): spelled where it is named.
    project = spelled(row.get("project") or "?")
    where = spelled(target)
    # THE MOUNT COMPARISON MAY ASK THE DISK; THE MANIFEST'S NAME MAY NOT
    # (#157). A mirror is allowed to be a symlink onto a storage path whose
    # own tail is a serial number, and the row's `repository: Org/Repo` is
    # matched BY that tail — so the origin goes to the `repository:` fallback
    # exactly as git reported it, which is also the spelling the finding
    # below quotes back to the human.
    if not same_repository_here(origin, url) and not (
            repository and same_repository(origin, repository)):
        sibling.state = "WRONG ORIGIN"
        sibling.branch = branch_of(target)
        sibling.finding = (
            f"{project}: {where} is a clone of "
            f"{spelled(origin or '(no origin)')}, not of "
            f"{spelled(repository or url)}, so it is not this member and is "
            "left exactly as it is. Rename it, or move it aside and re-run; "
            "this command never fetches into a repository it cannot identify.")
        return False
    if identity is not None and str(row.get("id")) != identity:
        sibling.state = "WRONG PROJECT"
        sibling.branch = branch_of(target)
        sibling.finding = (
            f"{project}: {where}/project.yaml declares id {identity!r} where "
            f"the family's row records {str(row.get('id'))!r}. A repository at "
            "the right url is not by itself the project the row claims, so "
            "this is reported and skipped rather than fetched.")
        return False
    return True


def run_member_bootstrap(path: Path, sibling: Sibling) -> None:
    """The member's OWN bootstrap, which is what puts its legs on branches.

    Not reimplemented here for the same reason the family's `bootstrap.py`
    does not reimplement it: each member is a whole project and knows how.
    """
    script = path / "scripts" / "bootstrap.py"
    project = spelled(sibling.project)
    if not script.is_file():
        print(f"  [{project}] no scripts/bootstrap.py; cloned and "
              "left as it is. A member without one is not misconfigured — it "
              "simply has nothing for this command to call.")
        return
    print(f"  --- {project}: its own bootstrap ---")
    sys.stdout.flush()
    proc = subprocess.run([sys.executable or PYTHON, str(script)],
                          cwd=str(path), check=False)
    sys.stdout.flush()
    if proc.returncode != 0:
        sibling.finding = (f"{project}: its own bootstrap exited "
                           f"{proc.returncode}; the clone is there and its "
                           "legs may not be placed")


def argument_fault(value: str) -> str | None:
    """The character that stops `value` being an argument to a command, or
    None (#690): #455's rule, as `make bootstrap` asks it of a branch.

    `place` hands a member's `project:` (as the clone's path) and its url
    to `git clone` as argv, and `subprocess` cannot give a command a NUL
    (`ValueError: embedded null byte`) or a lone surrogate the system cannot
    encode (`UnicodeEncodeError`): `project: "IR\\ud83dRS"` ended `make
    siblings` in a traceback at the clone, and the members after it were
    never placed. A surrogate that is ONE BYTE of a name (POSIX spells a
    name that is not UTF-8 with U+DC80 to U+DCFF) is handed on as that
    byte, as before; whether one is, is `os.fsencode`'s own answer.
    """
    for char in value:
        if char == "\x00":
            return "U+0000, a NUL"
        if "\ud800" <= char <= "\udfff" and _bytes_for(char) != 1:
            return f"U+{ord(char):04X}, a lone surrogate"
    return None


def _bytes_for(char: str) -> int:
    """How many bytes `os.fsencode` writes for `char`; 0 when it cannot."""
    try:
        return len(os.fsencode(char))
    except UnicodeEncodeError:
        return 0


def place(root: Path, row: dict, urls: dict[str, str], prefix: list[str],
          token: str, dry_run: bool) -> Sibling:
    """Clone or fetch ONE member beside the holder. Never moves a HEAD.

    A ROW NO COMMAND CAN BE GIVEN IS A FINDING, BEFORE ANYTHING (#690): a
    `project:` or url holding a NUL or a lone surrogate (`argument_fault`)
    is never made a path or handed to git, the dry run says so alike, and
    the members after it are still placed. And a `tracking_branch:` that
    names only a TAG of the member's remote is cloned DETACHED at it, which
    `git clone --branch` does with a tag, so the line after the clone says
    the name is no branch of that remote.
    """
    project = str(row.get("project") or "?")
    repository = str(row.get("repository") or "")
    target = root.parent / project
    sibling = Sibling(project, target)
    url, source = clone_url(root, row, urls)
    # What a line names of this member is a manifest's and a disk's text
    # (#454), so the lines below print `who`, `at` and `src`, and the raw
    # `project`, `target` and `url` stay what the paths and git are given.
    who, at, src = spelled(project), spelled(target), spelled(url)

    for named, value in ((f"its `project:` in {MANIFEST}", project),
                         (f"its url {src} ({source})", url)):
        fault = argument_fault(value)
        if fault is not None:
            sibling.state = "NOT AN ARGUMENT"
            sibling.finding = (
                f"{who}: {named} holds {fault}, which no command can be "
                "given as an argument, so nothing was cloned or fetched for "
                "this member: git was never run with it.")
            return sibling

    if target == root:
        # A MEMBER NAMED AFTER ITS OWN FAMILY. `<Family>/<Family>` is the
        # holder, so this member's sibling would BE the holder — and this
        # command would then be asked to verify the holder against a member's
        # row. Named rather than attempted: the exit is a folder whose name
        # is not the member's, and that is the human's choice to make.
        sibling.state = "IS THE HOLDER"
        sibling.branch = branch_of(root)
        sibling.finding = (
            f"{who}: its sibling would be {at}, which is this holder "
            "itself — the member is named after its own family. Nothing was "
            "done. Rename the family FOLDER (the holder keeps its name) so "
            f"the two are not the same path, then re-run.")
        return sibling

    present = holds_git(target)
    occupied = None if present else not_a_clone(target)
    if occupied:
        found, thing = occupied
        sibling.state = "NOT A CLONE"
        sibling.finding = (
            f"{who}: {at} {found}, so this command will not write into it. "
            f"Move it aside or name the {thing} something else; nothing here "
            f"overwrites a {thing} somebody made.")
        return sibling

    if not present:
        branch, where = tracking_branch(root, row)
        on = spelled(f"on {branch}, its tracking branch ({where})" if branch
                     else f"on its remote's default branch: {where}")
        if dry_run:
            sibling.state = "would clone"
            print(f"  [{who}] would clone {src} ({source}) -> {at}, {on}")
            return sibling
        print(f"  [{who}] cloning {src} ({source}) {on}")
        sys.stdout.flush()
        proc = subprocess.run(
            ["git", *prefix, "clone", "-q", "--no-local",
             "--recurse-submodules",
             *([f"--branch={branch}"] if branch else []), "--",
             url, str(target)],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", check=False)
        if proc.returncode != 0:
            sibling.state = "CLONE FAILED"
            sibling.finding = (
                f"{who}: git clone exited {proc.returncode}:\n"
                + said_of_url(scrub((proc.stderr + proc.stdout).strip(),
                                    token), url))
            return sibling
        sibling.state = "cloned"
        if branch and branch_of(target) == "detached":
            print(f"  [{who}] {spelled(branch)} is not a branch of {src} but "
                  "a tag, which git clone checks out DETACHED: this clone is "
                  "on no branch")
        run_member_bootstrap(target, sibling)
        sibling.branch = branch_of(target)
        return sibling

    # PRESENT. Verify it is this member, then FETCH ONLY.
    if not verify_sibling(row, target, url, repository, sibling):
        return sibling

    if dry_run:
        sibling.state = "present, would fetch"
        sibling.branch = branch_of(target)
        print(f"  [{who}] present at {at}; would fetch, nothing else")
        return sibling
    print(f"  [{who}] present at {at}; fetching only")
    fetched = subprocess.run(["git", *prefix, "fetch", "--quiet", "origin"],
                             cwd=str(target), capture_output=True, text=True,
                             encoding="utf-8", errors="replace", check=False)
    # NO CHECKOUT, NO RESET, NO PULL: somebody is working in here.
    sibling.state = "present, fetched" if fetched.returncode == 0 \
        else "present, fetch failed"
    if fetched.returncode != 0:
        print(f"  [{who}] fetch exited {fetched.returncode}; the clone is "
              "untouched:\n"
              + said_of_url(scrub((fetched.stderr + fetched.stdout).strip(),
                                  token),
                            git_text(["remote", "get-url", "origin"], target)),
              file=sys.stderr)
    sibling.branch = branch_of(target)
    return sibling


# ---------------------------------------------------------------------------
# dispatching a verb into the WORKING CLONES (--make)
# ---------------------------------------------------------------------------


def make_program() -> str:
    """`make`, resolved to an EXECUTABLE PATH, or a named refusal.

    `$MAKE` first — make itself exports it, so a run started from a Makefile
    uses the same binary — then `make` on PATH, and BOTH go through
    `shutil.which`, which answers with an absolute path to something
    executable or with nothing at all. What reaches `subprocess.run` is
    therefore a program this function resolved, never a string somebody left
    in an environment variable.
    """
    named = (os.environ.get("MAKE") or "").strip()
    if named:
        resolved = shutil.which(named)
        if not resolved:
            raise Refusal(
                "make-not-executable",
                f"$MAKE is {named!r}, which is not an executable this "
                "machine can run, so no member's verb was started",
                "Remediation: point $MAKE at the make binary, or unset it "
                "and let PATH answer.")
        return resolved
    resolved = shutil.which("make")
    if not resolved:
        raise Refusal(
            "make-not-found",
            "`make` is not on PATH, so a member's verb cannot be run in any "
            "working clone",
            "Remediation: install make (or set $MAKE to it) and re-run. The "
            "estate's verbs are POSIX shell and make; on Windows they run "
            "under WSL2.")
    return resolved


def is_a_make_call(target: str, assignments: list[str]) -> bool:
    """Is this a make TARGET plus nothing but `NAME=value` ASSIGNMENTS?

    The predicate both the parse-time refusal and the call site use, so there
    is ONE definition of what may reach `make`'s argv.
    """
    return bool(MAKE_TARGET_RE.fullmatch(target)) and all(
        MAKE_ASSIGNMENT_RE.fullmatch(one) for one in assignments)


def validated_make_call(target: str,
                        assignments: list[str]) -> tuple[str, list[str]]:
    """`--make` and its `--make-arg`s, CHECKED, or a refusal naming which.

    Called at parse time and BEFORE ANYTHING RUNS: a bad value must refuse
    the whole run rather than be discovered after the first member's verb has
    already committed and pushed somebody's work. `MAKE_TARGET_RE` and
    `MAKE_ASSIGNMENT_RE` carry why the patterns are what they are.
    """
    if not MAKE_TARGET_RE.fullmatch(target):
        raise Refusal(
            "make-target-invalid",
            f"--make {target!r} is not a make target name: it must match "
            f"{MAKE_TARGET_RE.pattern} (a letter, then letters, digits, "
            "'_', '.' or '-')",
            "Remediation: pass the target itself — `--make park`, `--make "
            "resume` — with its flags in `--make-arg 'ARGS=<flags>'`. "
            "Nothing was run.")
    for one in assignments:
        if not MAKE_ASSIGNMENT_RE.fullmatch(one):
            raise Refusal(
                "make-arg-invalid",
                f"--make-arg {one!r} is not a make assignment: it must match "
                f"{MAKE_ASSIGNMENT_RE.pattern} — `NAME=value`, and the value "
                "carries no control character (a newline especially)",
                "Remediation: pass one `NAME=value` per --make-arg, as the "
                "holder's Makefile does with `ARGS=$(ARGS)`. Nothing was "
                "run.")
    return target, list(assignments)


def dispatch(root: Path, row: dict, urls: dict[str, str], target: str,
             make_args: list[str], make: str, dry_run: bool) -> Sibling:
    """`make <target>` in ONE member's working clone. Clones and fetches NOT.

    The path and the identity check are `place()`'s, deliberately: the verb
    goes to the clone this command would have placed there, or nowhere.
    """
    project = str(row.get("project") or "?")
    repository = str(row.get("repository") or "")
    path = root.parent / project
    sibling = Sibling(project, path)
    url, _ = clone_url(root, row, urls)
    # What a line names is a manifest's, a disk's or the command line's text
    # (#454; a `--make-arg` value may hold a surrogate or a C1 control): the
    # lines print `who`, `at` and `spelling`, and the raw `project`, `path`
    # and `make_args` stay what the paths and `make` are given.
    who, at = spelled(project), spelled(path)
    spelling = spelled(" ".join([f"make {target}", *make_args]))

    if path == root:
        sibling.state = "IS THE HOLDER"
        sibling.branch = branch_of(root)
        sibling.finding = (
            f"{who}: its working clone would be {at}, which is this "
            "holder itself — the member is named after its own family. "
            f"`{spelling}` was not run for it; rename the family FOLDER (the "
            "holder keeps its name) so the two are not the same path.")
        return sibling

    if not holds_git(path):
        sibling.state = "SKIPPED no clone"
        sibling.finding = (
            f"{who}: skipped: no working clone at {at}; run `make "
            "siblings` first. The verb runs in the clone BESIDE the holder "
            "and never in the pinned copy under members/, which is detached "
            "and is not where anybody's work is.")
        return sibling

    sibling.branch = branch_of(path)
    if not verify_sibling(row, path, url, repository, sibling):
        return sibling

    if not (path / "Makefile").is_file():
        sibling.state = "SKIPPED no Makefile"
        sibling.finding = (
            f"{who}: {at} has no Makefile, so there is no `{spelling}` "
            "to run in it. A member that carries the shape has one; this is "
            "reported rather than passed over silently, because a member "
            "nothing ran in is not a member that succeeded.")
        return sibling

    if dry_run:
        sibling.state = f"would make {target}"
        print(f"  [{who}] would run `{spelling}` in {at}")
        return sibling

    # THE CHECK, BESIDE THE CALL. `validated_make_call` already refused a
    # target or an assignment that is not one at parse time, so this cannot
    # fire — and it is restated here anyway, because a reader (or a scanner)
    # looking at a `subprocess.run` should find what constrains its argv on
    # the same screen rather than three hundred lines up.
    if not is_a_make_call(target, make_args):
        sibling.state = "REFUSED not a make call"
        sibling.finding = (
            f"{who}: refused: `make {target}` with {make_args!r} is not a "
            "make target plus `NAME=value` assignments, so nothing was run "
            "in this member. This is a BUG if you see it — the same check "
            "refuses at parse time, before any member runs.")
        return sibling

    # THE SANITIZED VALUES, one screen from the sink: `make` is an absolute
    # executable `shutil.which` resolved, `checked_target` matched
    # MAKE_TARGET_RE, and every entry of `checked_assignments` matched
    # MAKE_ASSIGNMENT_RE. No shell: this is a list, and make gets exactly
    # these words.
    checked_target = target
    checked_assignments = list(make_args)
    print(f"  --- {who}: make {checked_target} ---")
    sys.stdout.flush()
    proc = subprocess.run([make, checked_target, *checked_assignments],
                          cwd=str(path), check=False)
    sys.stdout.flush()
    if proc.returncode != 0:
        sibling.state = f"make {target} exited {proc.returncode}"
        sibling.finding = (
            f"{who}: `{spelling}` in {at} exited {proc.returncode}; "
            "its own output above says what it refused and what to run. "
            "Nothing else was stopped by it.")
    else:
        sibling.state = f"make {target} ok"
    return sibling


def dispatch_all(root: Path, name: str, rows: list[dict],
                 target: str, make_args: list[str], dry_run: bool) -> int:
    """`--make <target>` across every member, reporting each and continuing.

    EXIT 0 ONLY IF EVERY MEMBER RAN AND EXITED 0. A skip is not a pass: a
    `make resume` on a fresh machine where nobody has run `make siblings`
    skips every member, and reading that as success is how somebody concludes
    their work came back when none of it did.
    """
    try:
        make = make_program()
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"siblings: {spelled(name)} ({spelled(root)}) — "
          f"{len(rows)} member(s)")
    print(f"  family folder   {spelled(root.parent)}")
    print(f"  `make {target}` runs in each member's WORKING CLONE beside the "
          "holder. This")
    print("  command clones nothing and fetches nothing: it only dispatches.")

    urls = submodule_urls(root)
    print(f"\n(a) make {target}, one member at a time")
    dispatched: list[Sibling] = []
    if not rows:
        print("  no members declared. A family with none is empty, not wrong: "
              "`family.py add` is what puts one here.")
    for row in rows:
        dispatched.append(dispatch(root, row, urls, target, make_args, make,
                                   dry_run))

    print("\n(b) what ran")
    print(f"  {'what':<9} {'name':<18} {'state':<22} branch")
    for sibling in dispatched:
        print(sibling.row())

    findings = [s.finding for s in dispatched if s.finding]
    print()
    sys.stdout.flush()
    if findings:
        for finding in findings:
            print(f"FINDING {finding}", file=sys.stderr)
        print(f"siblings: `make {target}` did not run everywhere — "
              f"{len(dispatched) - len(findings)} of {len(dispatched)} "
              "member(s) ran and exited 0. Nothing was cloned or fetched.",
              file=sys.stderr)
        return 1
    if dry_run:
        print(f"--dry-run: nothing was run. `make {target}` would run in "
              f"{len(dispatched)} member(s).")
        return 0
    print(f"siblings ok: `make {target}` ran in {len(dispatched)} member(s) "
          f"beside the holder in {spelled(root.parent)}")
    return 0


# ---------------------------------------------------------------------------
# the parent-folder check
# ---------------------------------------------------------------------------


def family_folder_name(manifest: dict, root: Path) -> str:
    """What the family FOLDER is called.

    THE HOLDER'S REPOSITORY NAME, not `name:`. `family.py init` creates
    `<into>/<Family>/<Family>` out of `--family <Name>`, which is the
    repository's name; `name:` is a DISPLAY name (`--name`) and may differ
    from it. Where a family never set one the two are the same string.

    ONE ANSWER FOR EVERY FILE THAT NAMES THE FOLDER (#629). The holder's
    README spells the folder `{{FAMILY}}`, the same repository name this
    returns, where it said `{{FAMILY_NAME}}` and so told a holder made with
    `--family Quill --name QuillWorks` to `cd QuillWorks` and lay itself out
    as `QuillWorks/QuillWorks`: a layout this function then refuses, with the
    WARNING and the `mv`, and clones nothing.
    """
    repository = str(manifest.get("repository") or "")
    if repository:
        return repo_basename(repository)
    return str(manifest.get("name") or root.name)


def family_name_note(name: str, family: str) -> str | None:
    """The line that says which name names the folder, or None where the
    manifest's `name:` and the folder's name are one string (#629).

    A run printed the display name, `siblings: QuillWorks (...)`, and then
    asked for a folder named `Quill`, so one run named the family two ways
    and said nothing about which one it meant. Where the two are one string
    there is nothing to tell apart and the run prints no extra line, so a
    holder whose `name:` is its repository (the usual one) reads exactly as
    it did. Both names are a manifest's text, so both are spelled (#454).
    """
    if name == family:
        return None
    return ("  the folder is named after the holder's REPOSITORY, "
            f"{spelled(family)}, and never after name: {spelled(name)}, "
            "which is only a display name")


def same_directory(one: Path, two: Path) -> bool:
    """`one` and `two` are one directory: the same path, or on THIS disk.

    Equal paths first, which needs no disk, so a drive root can be asked
    with a `PureWindowsPath` (whose equality already ignores case). Then the
    disk's own answer, `os.path.samefile`, which is how `C:\\p\\InkRouter`
    and `C:\\p\\inkrouter` are found to be one folder on a disk that ignores
    case and two on one that does not.
    """
    if one == two:
        return True
    try:
        return one.exists() and os.path.samefile(one, two)
    except OSError:
        return False


def family_link(root: Path, family: str) -> Path | None:
    """`<grandparent>/<Family>` when it is a LINK to the holder's parent
    folder, or None: the family folder reached through a link (#543).

    The holder's path is RESOLVED before it is asked about (`find_repo_root`
    for `make siblings`, and `family.py siblings` runs this file standing in
    the resolved holder), so `~/p/InkRouter`, a link to `~/p/real-x`, reads
    as `real-x`. The holder is then reachable as `~/p/InkRouter/InkRouter`
    and its members are cloned into `real-x`, the link's own target, so the
    family layout holds through the link and the run goes on. A link named
    `<Family>` that leads anywhere else is no family folder of this holder.

    Only a LINK: a symbolic link (`os.path.islink`), or a Windows directory
    junction (`os.path.isjunction`, Python 3.12 and later), the link Windows
    makes without privilege and that `Path.resolve()` follows the same way.
    Never a second spelling: on a disk that ignores case, `InkRouter` beside
    `inkrouter` is one directory entry and no link, so it is the strict
    test's case-only rename below.
    """
    folder = root.parent
    link = folder.parent / family
    junction = getattr(os.path, "isjunction", lambda _: False)
    if ((os.path.islink(link) or junction(link))
            and same_directory(link, folder)):
        return link
    return None


def staging_path(parent: Path, name: str) -> Path:
    """`<parent>/<name>`, or the first `<parent>/<name>.<n>` (n = 1, 2, ...)
    at which nothing is: a name one step of the printed move passes through
    (#690).

    `os.path.lexists`, which follows no link: a link to nothing is
    something there, and so is the name in another case on a disk that
    ignores case. `mv` onto what is there does not make the name: it moves
    the holder INTO a folder, or fails on a link or a file.
    """
    staged, number = parent / name, 0
    while os.path.lexists(staged):
        number += 1
        staged = parent / f"{name}.{number}"
    return staged


def parent_folder_warning(root: Path, family: str) -> str | None:
    """The WARNING and the exact `mv`, or None when the layout is right.

    IT MOVES NOTHING, and this is the ruling (issue #76, 2026-09-09): a tool
    that relocated the checkout would do it out from under the shell, the
    editor and every agent lane standing in it, and would break linked
    worktrees, whose `.git` files carry ABSOLUTE paths. The warning plus the
    command gives the same outcome with the human's hand on it.

    AND IT IS ASKED BEFORE ANYTHING IS CLONED (#543), which is why it says
    nothing was. It used to come after the placement: every member was
    cloned into the wrong folder first, and the re-run the warning asked for
    cloned each one again beside the moved holder.

    THE NAME TEST IS EXACT ON EVERY DISK, so the printed move has to run as
    typed on every disk too (#543). Three shapes of it:
    - `<parent>/<Family>` is the HOLDER ITSELF, because the parent is a
      filesystem or drive root (`/`, `C:\\`): the holder is moved through a
      staging name, as when `<parent>/<Family>` does not exist at all.
    - `<parent>/<Family>` is THIS FOLDER under another case, on a disk that
      ignores case (macOS, Windows): the FOLDER is renamed, through a
      staging name, because a rename that changes only the case is a move
      onto itself there. Linux, where the two are two folders, is unchanged.
    - otherwise the holder moves into `<parent>/<Family>`, made if missing.

    A LINK named `<Family>` beside this folder that leads to it passes the
    check (`family_link`): it is the family folder, reached through a link.
    One that leads elsewhere does not, and its move runs as typed: the
    holder moves into the link's target, where the link then passes.

    AND NOTHING ALREADY THERE SENDS IT ASTRAY (#690). A staging name was
    printed whether or not something held it: with `<Family>.holder` a
    directory already, `mv` put the holder INSIDE it, and the three lines
    all exited 0 and left it at `<Family>/<Family>/<Family>`, one level too
    deep. Each staging name is now the first of `<Family>.holder`,
    `<Family>.holder.1`, `<Family>.holder.2` ... (`.folder` alike) at which
    nothing is (`staging_path`). A LINK TO NOTHING named `<Family>` is not
    a folder to move into: `mkdir -p` fails on it, after the holder's first
    move has run. It is named, to be moved aside first, and the moves under
    it are the ones that run once it is gone. The prose names the holder,
    the folders and the family spelled (#454); the commands stay as typed.
    """
    folder = root.parent
    if folder.name == family or family_link(root, family) is not None:
        return None
    lines = [
        f"WARNING the holder's parent folder is {folder.name or str(folder)!r}"
        f", not {family!r}.",
        f"        {spelled(root)} should sit in a plain folder named "
        f"{spelled(family)}, beside the members'",
        "        working clones — that is the layout `make siblings` places. "
        "So",
        "        NOTHING WAS CLONED: a member cloned now would land in "
        f"{spelled(folder)}, and",
        "        the re-run after the move would clone it a second time, "
        "beside the",
        "        moved holder.",
        "",
        "        NOTHING WAS MOVED either. Relocating a checkout breaks an "
        "open",
        "        shell, an editor and any LINKED WORKTREE (its `.git` file "
        "carries",
        "        an absolute path), so it is yours to run, when nothing is "
        "standing",
        "        in it, in a POSIX shell (Git Bash on Windows):",
        "",
    ]
    wanted = folder.parent / family
    if same_directory(wanted, root) or (root.name == family
                                        and not wanted.exists()):
        # The common case: the holder was cloned straight into ~/projects, so
        # `<parent>/<Family>` IS the holder itself and the move needs a
        # staging name — `mv A A/A` cannot be spelled in one command. At a
        # filesystem or drive root it is the holder even though it exists.
        # A LINK TO NOTHING named <Family> is here too: `exists` follows it,
        # and these are the moves once it is moved aside (said below).
        staged = staging_path(folder.parent, f"{family}.holder")
        steps = [["mv", root, staged], ["mkdir", "-p", wanted],
                 ["mv", staged, wanted / family]]
    elif (folder.name.casefold() == family.casefold()
          and not wanted.is_symlink() and same_directory(wanted, folder)):
        # THIS FOLDER under another case, on a disk that ignores case: the
        # folder is renamed, in two steps, and the holder stays inside it.
        # Never a link: a link to this folder passed above (`family_link`),
        # and a case-only alias is one directory entry, never a link. They
        # differ by disk at one edge: a LINK spelled in another case
        # (`inkrouter` to `real-x`) stops on Linux, with a staged move that
        # runs, and passes as the family's link on a disk that ignores case.
        staged = staging_path(folder.parent, f"{family}.folder")
        steps = [["mv", folder, staged], ["mv", staged, wanted]]
    else:
        steps = [["mkdir", "-p", wanted], ["mv", root, wanted / family]]
    if os.path.lexists(wanted) and not os.path.exists(wanted):
        lines += [f"        First move {spelled(wanted)} aside: it is a link "
                  "to nothing,",
                  "        named after the family, and in the way of the "
                  "move. Then:",
                  ""]
    # EVERY PATH QUOTED (#486): under `my work/` a bare `mv` moved nothing
    # and pasted as four arguments. Quoted for the POSIX shell `mv` and
    # `mkdir -p` are commands of, as the sentence above says, by the standard
    # library's `shlex.join` and NOT `repo_shape.shell_line`: a holder that
    # kept an older `repo_shape.py` (`update-shape.py apply --accept-local`)
    # must still be able to run this file, and an import of a name its copy
    # lacks would stop `make siblings`, `park` and `resume` dead.
    lines += [f"            {shlex.join(str(word) for word in step)}"
              for step in steps]
    lines += ["",
              "        Then re-run `make siblings` from the moved holder; the "
              "members are",
              "        cloned beside it, in the folder, once."]
    return "\n".join(lines)


# ---------------------------------------------------------------------------


def _resolve_make_target(args: argparse.Namespace) -> tuple[str | None,
                                                            list[str]]:
    """`--make`/`--make-arg`, VALIDATED HERE, BEFORE ANYTHING RUNS.

    Split from `main` for #137. Not at the first member: a bad value must
    refuse the whole run rather than be found after one member has already
    committed and pushed somebody's work. Raises `Refusal` for one, exactly
    as `main` always caught it.
    """
    if args.make is None:
        return None, list(args.make_arg)
    return validated_make_call(args.make, args.make_arg)


def _load_family(args: argparse.Namespace) -> tuple[Path, str, list[dict],
                                                     dict]:
    """The family this run acts on: its root, name, member rows and manifest.

    Split from `main` for #137. Raises `Refusal` exactly as `main` always
    caught it — no `family.yaml`, or one that is not a mapping.
    """
    root = find_repo_root(args.root or Path(__file__).resolve().parents[1])
    # `members_of` is `bootstrap.py`'s reading of the rows and stays the
    # only one; the manifest is then read again for the two fields the
    # LAYOUT needs and bootstrap has no use for.
    name, rows = members_of(root)
    manifest = load_yaml(root / MANIFEST)
    if not isinstance(manifest, dict):
        raise Refusal("family-manifest-unreadable",
                      f"{root / MANIFEST}: not a mapping")
    return root, name, rows, manifest


def _place_all_members(root: Path, rows: list[dict], urls: dict[str, str],
                       prefix: list[str], token: str,
                       dry_run: bool) -> list[Sibling]:
    """Every member, placed, in the order `family.yaml` lists them.

    Split from `main` for #137 — "(a) the members, beside the holder".
    """
    if not rows:
        print("  no members declared. A family with none is empty, not wrong: "
              "`family.py add` is what puts one here.")
    return [place(root, row, urls, prefix, token, dry_run) for row in rows]


def _print_pinned_row(root: Path, row: dict) -> None:
    """One `members/<Project>` row of the layout table: the PINNED copy,
    detached, that `make bootstrap` and `make validate` read.

    Split from `main` for #137 — the body of its second layout-table loop.
    """
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


def _print_layout_table(root: Path, siblings: list[Sibling],
                        rows: list[dict]) -> None:
    """"(b) the layout": the holder, every sibling, then every PINNED mount.

    Split from `main` for #137.
    """
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
        _print_pinned_row(root, row)


def _report_placement(root: Path, siblings: list[Sibling],
                      dry_run: bool) -> int:
    """The findings (or the ok / dry-run line), and the exit code that
    matches. Split from `main` for #137.
    """
    findings = [s.finding for s in siblings if s.finding]
    print()
    sys.stdout.flush()
    if findings:
        for finding in findings:
            print(f"FINDING {finding}", file=sys.stderr)
        print(f"siblings: {len(findings)} finding(s); nothing was moved and "
              "no existing clone was touched", file=sys.stderr)
        return 1
    if dry_run:
        print("--dry-run: nothing was cloned, fetched or moved.")
        return 0
    print(f"siblings ok: {len(siblings)} member(s) beside the holder in "
          f"{spelled(root.parent)}")
    return 0


def _run_placement(root: Path, name: str, rows: list[dict], manifest: dict,
                   dry_run: bool) -> int:
    """THE PLACEMENT RUN: the parent-folder check, then every member cloned
    or fetched beside the holder, the layout table, and the exit code.

    Split from `main` for #137: once `_resolve_make_target` and
    `_load_family` are also lifted out of it, `main` is left with only the
    dispatch-or-placement choice.

    THE FOLDER IS ASKED FIRST (#543). A holder whose parent folder is not
    named after the family stops here, exit 1, before any `git` command
    runs or any member is cloned, and `--dry-run` stops in the same words:
    once the holder is moved, the run after it clones each member once, in
    the right folder. Until the check passes, the header calls that folder
    the PARENT folder, not the family's. Passed through a link named after
    the family, it names the folder the clones go into, and the link.

    THE HEADER SAYS WHICH NAME IT MEANS (#629). Its first line is `name:`, the
    display name, and the folder it asks about is named after the
    repository, so where those differ a line under the folder's says so
    (`family_name_note`), on a stopped run and a passing one alike. And it
    is all one spelling (#454): the name, the paths and the link are text a
    manifest or a disk gave, so each is printed spelled.
    """
    family = family_folder_name(manifest, root)
    warning = parent_folder_warning(root, family)
    link = None if warning else family_link(root, family)
    print(f"siblings: {spelled(name)} ({spelled(root)}) — "
          f"{len(rows)} member(s)")
    print(f"  {'parent' if warning else 'family'} folder   "
          f"{spelled(root.parent)}"
          + (f"   (through the link {spelled(link)})" if link else ""))
    note = family_name_note(name, family)
    if note:
        print(note)
    print("  each member is cloned BESIDE the holder and stays PINNED inside "
          "it under")
    print("  members/ — the pinned copy is detached for bootstrap and "
          "validate, the")
    print("  sibling is where you work.")

    if warning:
        print()
        sys.stdout.flush()          # so the warning lands where it belongs
        print(warning, file=sys.stderr)
        print(f"\nsiblings: stopped before cloning: the holder is not in a "
              f"folder named {spelled(family)}. Nothing was cloned, fetched "
              "or moved.", file=sys.stderr)
        sys.stderr.flush()
        return 1

    prefix, source, token = git_prefix()
    urls = submodule_urls(root)
    print(f"\n(a) the members, beside the holder (credential source: "
          f"{source})")
    siblings = _place_all_members(root, rows, urls, prefix, token, dry_run)

    _print_layout_table(root, siblings, rows)

    return _report_placement(root, siblings, dry_run)


def main(argv: list[str] | None = None) -> int:
    # FIRST, before the parser or anything is printed (#454): every line below
    # may hold a value a stdout cannot encode, and a stdout that raised on the
    # first one ended `make park` before it parked anything.
    escape_unencodable_stdout()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None,
                        help="the family holder (default: the enclosing "
                             "repository)")
    parser.add_argument("--dry-run", action="store_true",
                        help="say what would be cloned and fetched (or, with "
                             "--make, what would be run); clone nothing, "
                             "fetch nothing, run nothing, move nothing")
    parser.add_argument("--make", metavar="TARGET", default=None,
                        help="run `make TARGET` in each member's WORKING "
                             "CLONE beside the holder instead of placing "
                             "them; clones nothing and fetches nothing. What "
                             "the holder's `make park` / `make resume` use")
    parser.add_argument("--make-arg", action="append", default=[],
                        metavar="ARG",
                        help="appended verbatim to each member's `make` "
                             "command line (the holder passes `ARGS=...` "
                             "through this way); repeatable, --make only")
    args = parser.parse_args(argv)
    if args.make_arg and args.make is None:
        parser.error("--make-arg is only meaningful with --make <target>")

    try:
        make_target, make_assignments = _resolve_make_target(args)
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        root, name, rows, manifest = _load_family(args)
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if make_target is not None:
        # THE DISPATCH IS NOT THE PLACEMENT, and it does not borrow half of
        # it: no credential is resolved, nothing is cloned, nothing is
        # fetched and the parent-folder check is the placement's business.
        # `is not None` rather than truthiness, so `--make ''` reaches the
        # refusal above instead of quietly becoming a placement run.
        return dispatch_all(root, name, rows, make_target, make_assignments,
                            args.dry_run)

    return _run_placement(root, name, rows, manifest, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
