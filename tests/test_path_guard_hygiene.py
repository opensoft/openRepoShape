# SPDX-License-Identifier: Apache-2.0
"""No shipped tool takes a path it cannot read for a path that is not there:
#430's slice Z, the hygiene and parity test that closes it.

THE RULE (#430, lane 1's plan). Up to Python 3.13 `Path.is_file()`,
`is_dir()`, `exists()` and `is_symlink()` raise a `stat` the operating system
refused, and answer False only where nothing is there; from 3.14 they answer
False to ANY `OSError`, and `os.path.isfile`, `isdir`, `exists`, `lexists`
and `islink` always have. So a `scripts/` this user cannot search was three
validators SKIPPED as absent, and a pin in a `contracts/` at 000 a pin that
is not there. The cure, in every tool: stat the path. ENOENT, ENOTDIR, EBADF
and ELOOP (and Windows' winerror 21, 123 and 1921) mean absent; any other
`OSError` is refused by name, `<path>: cannot be read (<reason>)`, exit 2,
in `validate-pins.py`'s `_unreadable_file`'s words. Slices A to H moved each
tool's guards onto a LOCAL `_is_a` (`is_a` in `shape-doctor.py`), a copy in
each file and never a shared helper: `scripts/repo_shape.py` is a shape copy
every root pins, and a pinned validator must not rely on a newer one (#370,
#610).

  A  scripts/bump-leg.py                                  #934
  B  update-shape.py                                      #976
  C  shape-doctor.py and scripts/shape_advisory.py        #975
  D  the assembly root's validate-manifest.py, bootstrap.py  #958
  E  the family root's validate-family.py                 #956
  F  the family root's siblings.py and bootstrap.py       #951
  G  scripts/family.py                                    #955
  H  adopt-project.py                                     #970

WHAT THIS HOLDS, so that no new guard brings the old answer back:

  * THE HYGIENE TEST. Every shipped tool is parsed (`ast`), and every call
    of `.is_file()`, `.is_dir()`, `.exists()` or `.is_symlink()`, and of
    `os.path.isfile`, `isdir`, `exists`, `lexists` or `islink`, fails
    unless it is on `BENIGN`, a reasoned allowlist keyed by file, enclosing
    function and the call's own text, never by line, as often as the
    function makes it. That covers a call wrapped over lines; the module
    reached as `os.path`, `posixpath` and the like, through `import os as
    o`, `o = os`, `import os.path as p`, `from os import path` or `*`, `p =
    os.path`, or `importlib` or `sys.modules` by a constant name; a name
    bound to it by tuple unpacking, a walrus, a `for` or `with` target, a
    default parameter or a class or instance attribute; a test imported
    from it by name or by `*`; a guard bound to a name, and each later call
    by that name; and a guard passed as a function. `_os_path_names` says
    what it does not cover (a guard named by a string, `getattr`, among
    them). One inside a stat helper fails too: the helper asks `stat` and
    nothing else. The failure names the file and line and says what to do.
  * `BENIGN` holds the sites the plan left out on purpose, each tagged with
    the plan's reason, or `MODEL` for a guard's name on what is no path
    (`TAGS`). `KNOWN_OPEN` holds the real sites this slice found and did
    not fix, each left to the follow-up, #1110, whose body mirrors it site
    for site. An entry that names no guard any more fails too, so neither
    list outlives its site.
  * THE PARITY TEST. Each helper's absent errnos and Windows errors are read
    out of the AST, through the module constants and the functions it calls,
    and must be the one set above. On the way from its `stat` to its answer
    (each `try` that makes a call), a helper may catch only `OSError`,
    `ValueError`, `FileNotFoundError` and `NotADirectoryError`, and its
    `except OSError` must re-raise (`raise`, or `raise exc` of what it
    caught); `errno` and `winerror` may be read only as `in` or `not in
    <set>`. A class or an `async def` by a helper's name is refused.
  * THE BEHAVIOUR TEST. Each helper is loaded by its AST, with nothing of
    its module run but the statements it reads, and ASKED, for a file and
    for a folder, of a path whose `stat` raises: each absent errno and
    Windows error must answer False, and every other errno (EACCES, EPERM,
    EIO, EINVAL and ESTALE among them) and Windows' 5 and 32 must come back
    raised, the same exception, also where only the `stat` of a link to
    nothing is refused and its `lstat` answers. That holds what the parity
    test cannot read: a branch, a handler, a method or a lambda its walk
    does not follow, a constant changed after it is set (an errno it adds
    is named whichever it is, a Windows error only if it is 5 or 32, and a
    top-level `+=` on the constants is refused outright), the helper's name
    bound to another function.

ONE SITE THIS SLICE FIXED: `shape-doctor.py`'s `Context.__init__`, where a
`project.yaml` that is a link into a folder this user cannot search was a
`PermissionError` traceback on 3.12 and NOT A SHAPE ROOT on 3.14, with
`adopt-project.py plan` as the NEXT for a project. It is now the `manifest`
row's `yaml-unreadable`, as a `project.yaml` at mode 000 already was. The
tests at the end hold that.
"""

from __future__ import annotations

import __future__
import ast
import errno
import inspect
import json
import os
import re
import stat
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pytest

from conftest import REPO, load_without_bytecode
#: #827's stand-in for a `stat` the operating system refuses, answering
#: `is_file()` as Python 3.14 does, from the file that owns it (#383).
from test_bump_leg_unopenable import refused_stat
#: #847's stand-in for a read the operating system refuses.
from test_doctor_unreadable_pin import refusing
#: The tools this repository ships, as the standard-library test names them.
from test_repo_hygiene import SHIPPED
#: The one skip for a mode that root reads through and Windows ignores.
from test_validate_pins_unreadable_workflow import CANNOT_RUN_AS_ROOT

#: The methods whose answer to a refused `stat` changed in Python 3.14.
GUARD_METHODS = frozenset({"is_file", "is_dir", "exists", "is_symlink"})
#: The `os.path` tests, which have answered False to any `OSError` always.
OS_PATH_GUARDS = frozenset({"isfile", "isdir", "exists", "lexists", "islink"})
#: The modules those tests are reached through.
OS_PATH_MODULES = frozenset({"os.path", "posixpath", "ntpath", "genericpath"})

#: The stat helper each slice gave its file: the one place a path may be asked
#: bare, and the function the parity test reads.
HELPER_NAMES = frozenset({"_is_a", "is_a"})
#: The errnos that mean nothing is at the name, by name (`errno.<NAME>`), and
#: Windows' "not ready", "invalid name" and "cannot resolve".
ABSENT_ERRNOS = frozenset({"ENOENT", "ENOTDIR", "EBADF", "ELOOP"})
ABSENT_WINERRORS = frozenset({21, 123, 1921})

#: Where each slice put its helper. Each must still be there, and every
#: helper found (these, and any added later) is held to the one set, and
#: asked by the behaviour test, which loads each by its AST.
HELPERS = {
    "adopt-project.py": "_is_a",
    "update-shape.py": "_is_a",
    "shape-doctor.py": "is_a",
    "scripts/bump-leg.py": "_is_a",
    "scripts/family.py": "_is_a",
    "scripts/shape_advisory.py": "_is_a",
    "templates/assembly-root/scripts/validate-pins.py": "_is_a",
    "templates/assembly-root/scripts/validate-manifest.py": "_is_a",
    "templates/assembly-root/scripts/bootstrap.py": "_is_a",
    "templates/family-root/scripts/validate-family.py": "_is_a",
    "templates/family-root/scripts/bootstrap.py": "_is_a",
    "templates/family-root/scripts/siblings.py": "_is_a",
}

#: The follow-up issue the sites in `KNOWN_OPEN` are left to, filed by lane 1
#: after this slice; it is not in v1.2.0 (Brett Heap, 2026-10-21T10:32Z,
#: "leave the follow-ups out of v1.2.0"). #1110's body mirrors `KNOWN_OPEN`
#: site for site, by function, call and effect: a site added to or taken
#: from `KNOWN_OPEN` is added to or taken from that body too. The module
#: docstring names the issue as well, and the two must agree (r1111b's Z11).
FOLLOW_UP = "#1110"

#: Why a bare guard may stay: the plan's own reasons for leaving a site out
#: (lane 1's site table at the v1.1.1 release commit, `5017830`).
TAGS = {
    "OWN": "the tool's own checkout of the standard, its templates or "
           "package, its cache, a temporary or work directory it made, or "
           "what this run wrote",
    "DELIBERATE": "a deliberate `os.path` call or guard whose False the code "
                  "relies on and says why: wording, advice, or a check a "
                  "by-name refusal follows",
    "ASKED": "asked only after the path, or the folder or repository it is "
             "in, was asked by the stat helper, a `stat`, or git, or inside "
             "a `try` that keeps the `OSError`",
    "ROOT": "a name directly in the root, asked by `lstat`, or where a link "
            "at the name is left out or handled as a link first, in a root "
            "the tool refuses by name first where it cannot search it",
    "DEST": "the plan's OPEN-DEST, loud: a destination asked before a create "
            "or a clone, which then fails by name",
    "PINNED": "`scripts/repo_shape.py`'s `find_repo_root`, a shape copy, "
              "left by the plan (pinned, low)",
    # r1111c's NIT 1: not a path the tool owns, as `OWN` says, but no path
    # at all; the scan flags any `.is_dir()` by its name alone.
    "MODEL": "not a filesystem call at all: a method of the run's own model "
             "in memory that shares a guard's name and asks no `stat`",
}


class Site(NamedTuple):
    """One bare guard: where it is, and the key an allowlist names it by."""
    file: str
    line: int
    scope: str
    snippet: str

    @property
    def key(self) -> tuple[str, str, str]:
        return self.file, self.scope, self.snippet


def _entries(table: dict) -> dict:
    """`{key: (tag, reason, count)}`, a count of 1 where none is given."""
    return {key: (value + (1,))[:3] for key, value in table.items()}


AP, US, SD = "adopt-project.py", "update-shape.py", "shape-doctor.py"
SP, SC = "setup-project.py", "scaffold-project.py"
FA, SM = "scripts/family.py", "scripts/shape_materialize.py"
AR, FR = "templates/assembly-root/scripts", "templates/family-root/scripts"
SRC = "src/openreposhape"
GITMODULES_LSTAT = "os.path.lexists(root / GITMODULES)"
HOLDER_GITMODULES = ("the holder's `.gitmodules`, by `lstat`, in a holder "
                     "`Family.open` refuses by name first (#955)")
VF_GITMODULES = ("the holder's `.gitmodules`, by `lstat`; `family.yaml` "
                 "is asked first and refused by name (#956)")
SPELLING = ("a members-spelling `os.path` twin (#840; the plan: BENIGN, "
            "low): ")

#: The sites the plan left out on purpose: `(file, function, call)`:
#: `(tag, reason[, how many such calls the function makes])`.
BENIGN = _entries({
    # --- adopt-project.py ---------------------------------------------------
    (AP, "Source.clone", "os.path.lexists(path)"): (
        "DEST", "the clone target in the run's own --work-dir; "
        "`_occupied_clone_target` or the clone names it (#652)"),
    (AP, "_PlannedRoot._into_git",
     'self._git().is_dir(here.rpartition("/")[0])'): (
        "MODEL", "`_CloneGit.is_dir`, the run's own model in memory of the "
        "names git makes in the clone's `.git` (#904): a set lookup with "
        "no `stat` in it"),
    (AP, "_PlannedRoot._no_directory", "self._git().is_dir(here)"): (
        "MODEL", "the same `_CloneGit.is_dir`, not the disk"),
    (AP, "_PlannedRoot._over", "os.path.isdir(walk.landed)"): (
        "DELIBERATE", "words a refusal, `a directory` or `a file`, for a "
        "path a symlink leads to outside the source tree"),
    (AP, "_SplitRehearsal.place", "target.is_symlink()"): (
        "OWN", "the throwaway work tree `check` writes (#910)"),
    (AP, "_clone_ref_store",
     '(probe / CLONE_GIT_DIR / "reftable").is_dir()'): (
        "OWN", "`git init`'s throwaway, a `mkdtemp` of this user's (0700) "
        "in the run's own work directory (#904); one it cannot write or "
        "search stops at the `mkdtemp`, before this"),
    (AP, "_create_leg_remote", "bare.exists()"): (
        "DEST", "the --local-remote-dir backstop, asked before either leg "
        "was made (#798); `git init --bare` fails by name"),
    (AP, "_first_missing_part", "os.path.lexists(walked)"): (
        "DELIBERATE", "words where --out's folder stops; "
        "`_why_the_folder_holds_no_plan` asks the folder by `os.stat`"),
    (AP, "_holds_a_file", "os.path.islink(os.path.join(top, name))"): (
        "OWN", "the run's own work directory, walked with an `onerror` "
        "that counts a folder it cannot list as holding a file"),
    (AP, "_holds_something", "path.exists()"): (
        "DEST", "a clone or seed destination in the run's own work "
        "directory; `git clone` refuses it by name"),
    (AP, "_holds_something", "path.is_dir()"): (
        "DEST", "the same destination; a listing it cannot make counts as "
        "something there"),
    (AP, "_holds_something", "path.is_symlink()"): (
        "DEST", "the same destination, a link to nothing counted"),
    (AP, "_in_the_way_on_disk", "os.path.lexists(bare)"): (
        "DEST", "--local-remote-dir's bare repository; `folder_in_the_way` "
        "asks the folder by `os.access` next (#798)"),
    (AP, "_made_0755", "path.is_dir()"): (
        "OWN", "after the run's own `mkdir` failed: anything but a "
        "directory re-raises the `mkdir`'s error"),
    (AP, "_made_source_readonly", "os.path.lexists(parent)"): (
        "OWN", "`source-readonly/` in the run's own work directory; a "
        "`mkdir` that fails is `adopt-work-dir-unwritable` (#803)"),
    (AP, "_not_a_top_level_finding", "Path(clone).is_dir()"): (
        "ASKED", "in a `try` whose `OSError` leaves the finding to the "
        "questions after it, which name the path (#800)"),
    (AP, "_not_a_whole_clone", "path.is_dir()"): (
        "ASKED", "asked after `_is_there` stat'ed the recorded source "
        "(slice H, #970)"),
    (AP, "_removed_if_it_holds_no_file", "os.path.lexists(root)"): (
        "OWN", "the run's own work directory, which only `os.rmdir` "
        "removes"),
    (AP, "_the_loop_in", "os.path.islink(part)"): (
        "DELIBERATE", "finds the link a --work-dir loop goes round, then "
        "asks `os.stat` (#978)"),
    (AP, "_top_level", "resolved.is_dir()"): (
        "ASKED", "asked after `_is_there` stat'ed the source (slice H, "
        "#970)"),
    (AP, "_unmade_work_dir", "os.path.islink(given)"): (
        "DELIBERATE", "words a refusal once the work directory's `mkdir` "
        "has failed (#978)"),
    (AP, "_where_it_landed",
     "assembly.joinpath(*parts[:end]).is_symlink()"): (
        "OWN", "the assembly clone this run made and wrote"),
    (AP, "_why_out_cannot_be_written", "os.path.exists(out)"): (
        "DELIBERATE", "--out's checks; the folder is asked by `os.stat` "
        "and `os.access` after (the plan: BENIGN)"),
    (AP, "_why_out_cannot_be_written", "os.path.isdir(out)"): (
        "DELIBERATE", "--out's checks, as above"),
    (AP, "_why_the_file_there_is_no_plan", "os.path.isfile(out)"): (
        "DELIBERATE", "--out's checks, after `os.path.exists` found it"),
    (AP, "_writable_then_removed", "os.path.islink(target)"): (
        "OWN", "`rmtree`'s handler over the run's own clone: a link is "
        "never `chmod`ed"),
    # --- scaffold-project.py ------------------------------------------------
    (SC, "local_remote_is_empty", "bare.exists()"): (
        "DEST", "the test path's local bare remote; git fails by name on "
        "one it cannot read (the plan: BENIGN)"),
    # --- scripts/family.py --------------------------------------------------
    (FA, "_add_dry_run", GITMODULES_LSTAT): ("ROOT", HOLDER_GITMODULES),
    (FA, "_checked_gitmodules_as_staged", GITMODULES_LSTAT): (
        "ROOT", HOLDER_GITMODULES),
    (FA, "_checked_gitmodules_held", GITMODULES_LSTAT): (
        "ROOT", HOLDER_GITMODULES),
    (FA, "_checked_mount_path", GITMODULES_LSTAT): (
        "ROOT", HOLDER_GITMODULES),
    (FA, "_gitmodules_beside", GITMODULES_LSTAT): (
        "ROOT", HOLDER_GITMODULES, 2),
    (FA, "_gitmodules_first", GITMODULES_LSTAT): ("ROOT", HOLDER_GITMODULES),
    (FA, "_submodule_paths", GITMODULES_LSTAT): ("ROOT", HOLDER_GITMODULES),
    (FA, "_checked_index_unlocked", "os.path.lexists(lock)"): (
        "ASKED", "`index.lock` where git's `--git-path` put it: git read "
        "the git directory first"),
    (FA, "_checkouts_under", "os.path.islink(top)"): (
        "DELIBERATE", SPELLING + "a link is never walked into"),
    (FA, "_checkouts_under",
     'os.path.lexists(os.path.join(here, name, ".git"))'): (
        "DELIBERATE", SPELLING + "a folder holding a `.git` is not "
        "walked into"),
    (FA, "_checkouts_under", 'os.path.lexists(top / ".git")'): (
        "DELIBERATE", SPELLING + "a repository is not walked into"),
    (FA, "_checkouts_under", "top.is_dir()"): (
        "DELIBERATE", SPELLING + "asked after `islink`, of an entry of "
        "the holder"),
    (FA, "_disk_spellings", 'os.path.lexists(root / name / entry / ".git")'):
        ("DELIBERATE", SPELLING + "whether a variant's entry is moved "
         "back"),
    (FA, "_forced", 'os.path.lexists(root / name / ".git")'): (
        "DELIBERATE", SPELLING + "whether `git rm --cached` takes `-f`; "
        "git refuses by name without it"),
    (FA, "_free_name", "os.path.lexists(root / name)"): (
        "ROOT", "a free name directly in the holder, by `lstat`"),
    (FA, "_landing", "os.path.isfile(into / family / MANIFEST)"): (
        "DELIBERATE", "#609's ruling, said in its comment: the holder is "
        "named by `_refuse_a_taken_holder`"),
    (FA, "_local_remote_is_empty", "bare.exists()"): (
        "DEST", "the test path's local bare remote, as the scaffold's"),
    (FA, "_members_dir_on_disk", "os.path.isdir(canonical)"): (
        "DELIBERATE", SPELLING + "in a `try`"),
    (FA, "_members_file_left_in_head", "os.path.islink(root / MEMBERS_DIR)"):
        ("ROOT", "`members` directly in the holder, by `lstat`"),
    (FA, "_members_on_disk", "top.is_dir()"): (
        "ROOT", "an entry `os.listdir` of the holder just named; "
        "`is_dir()` follows a link there, but `_disk_kind` names a link "
        "`a symlink` by `lstat`, and `_disk_spellings` moves aside, "
        "unread, every entry that is no directory"),
    (FA, "_members_spellings", 'os.path.lexists(root / name / ".git")'): (
        "DELIBERATE", SPELLING + "the `-f` of a move back"),
    (FA, "_moved_or_kept", "path.is_dir()"): (
        "ASKED", "after its own `lstat`, in a `try` that keeps the "
        "`OSError`"),
    (FA, "_on_disk_as_named", "os.path.islink(here)"): (
        "DELIBERATE", SPELLING + "in a `try`"),
    (FA, "_operation_in_progress", "os.path.lexists(marks[AM_MARK])"): (
        "ASKED", "a mark git's `--git-path` named: git read the git "
        "directory first (the plan: BENIGN)"),
    (FA, "_operation_in_progress",
     "os.path.lexists(marks[REBASE_HEAD_NAMES[mark]])"): (
        "ASKED", "a mark git's `--git-path` named, as above"),
    (FA, "_operation_in_progress", "os.path.lexists(marks[SEQUENCER])"): (
        "ASKED", "a mark git's `--git-path` named, as above"),
    (FA, "_operation_in_progress", "os.path.lexists(where)"): (
        "ASKED", "a mark git's `--git-path` named, as above"),
    (FA, "_renamed_with_git", "os.path.isdir(here)"): (
        "DELIBERATE", SPELLING + "the rename's own paths", 2),
    (FA, "_renamed_with_git", "os.path.isdir(root / spelling)"): (
        "DELIBERATE", SPELLING + "in a `try` with `samefile`"),
    (FA, "_renamed_with_git", "os.path.islink(here)"): (
        "DELIBERATE", SPELLING + "the rename's own paths"),
    (FA, "_renamed_with_git", "os.path.islink(root / canon)"): (
        "DELIBERATE", SPELLING + "a link is never renamed"),
    (FA, "_renamed_with_git", "os.path.islink(root / spelling)"): (
        "DELIBERATE", SPELLING + "a link is never renamed"),
    (FA, "_renamed_with_git", "os.path.lexists(here)"): (
        "DELIBERATE", SPELLING + "the rename's own paths", 2),
    (FA, "_standard_checkout",
     'os.path.isdir(directory / "templates" / "family-root")'): (
        "OWN", "looks for a checkout of the standard, by `os.path` on "
        "purpose (its docstring)"),
    (FA, "_standard_checkout",
     'os.path.isfile(directory / "scripts" / "family.py")'): (
        "OWN", "the same"),
    (FA, "_variant_in_members", "os.path.islink(root / name / entry)"): (
        "DELIBERATE", SPELLING + "a link is never the row's own"),
    # --- the other scripts/ -------------------------------------------------
    ("scripts/render-cli-reference.py", "main", "out.is_file()"): (
        "OWN", "this checkout's `docs/cli.md`"),
    ("scripts/render-cli-reference.py", "require_a_checkout",
     "(Path(toplevel) / name).is_file()"): (
        "OWN", "whether the work tree is a checkout of the standard"),
    ("scripts/repo_shape.py", "find_repo_root",
     '(candidate / ".git").exists()'): (
        "PINNED", "the walk up to a `.git`; the plan left it (pinned, "
        "low)"),
    (SM, "_append_eol_block", "path.is_file()"): (
        "OWN", "the target this materializer writes"),
    (SM, "_append_eol_block", "path.is_symlink()"): (
        "OWN", "the target this materializer writes"),
    (SM, "_blocker", "above.exists()"): (
        "OWN", "the target this materializer writes (the plan: BENIGN)"),
    (SM, "_blocker", "above.is_dir()"): ("OWN", "the same target"),
    (SM, "_blocker", "above.is_symlink()"): ("OWN", "the same target"),
    (SM, "_blocker", "path.is_symlink()"): ("OWN", "the same target"),
    (SM, "_blocker", "target.joinpath(*landed[:-1]).is_dir()"): (
        "OWN", "the same target"),
    (SM, "_followed", "here.is_symlink()"): ("OWN", "the same target"),
    (SM, "_from_a_directory", "here.is_dir()"): ("OWN", "the same target"),
    (SM, "_leg_path_lines", "path.is_file()"): (
        "OWN", "the standard's own templates"),
    (SM, "_materialize.place", "path.exists()"): (
        "OWN", "the target this materializer writes"),
    (SM, "copy_in_the_way", "here.exists()"): (
        "OWN", "the target this materializer writes (#262)"),
    (SM, "copy_in_the_way", "here.is_dir()"): ("OWN", "the same target", 2),
    (SM, "copy_in_the_way", "here.is_symlink()"): ("OWN", "the same target"),
    (SM, "folder_in_the_way", "os.path.lexists(here)"): (
        "DELIBERATE", "#609 and #798: `lexists`, then `os.access` of the "
        "folder it stops at"),
    (SM, "target_in_the_way", "os.path.lexists(target)"): (
        "DELIBERATE", "#609 and #798, as above"),
    (SM, "template_files", "path.is_dir()"): (
        "OWN", "the standard's own templates"),
    ("scripts/validate-repository-naming.py", "LinkSources._also_a_directory",
     "os.path.isdir(typed)"): (
        "DELIBERATE", "words a hint only, by `os.path` on purpose (its "
        "docstring)"),
    # --- setup-project.py ---------------------------------------------------
    (SP, "clone_and_bootstrap", "os.path.lexists(clone)"): (
        "DEST", "#498's backstop before the clone, which fails by name"),
    (SP, "family_manifest_here", "manifest.is_file()"): (
        "DELIBERATE", "advice only: any read failure means none (its "
        "docstring)"),
    (SP, "family_next_command",
     "(landing.holder / FAMILY_MANIFEST).is_file()"): (
        "DELIBERATE", "a printed next command, named and not refused"),
    (SP, "is_shape_checkout",
     '(root / "contracts" / "repository-naming.yaml").is_file()'): (
        "OWN", "whether a directory is a checkout of the standard"),
    (SP, "is_shape_checkout", "(root / SCAFFOLD).is_file()"): (
        "OWN", "the same"),
    (SP, "nearest_entry", "os.path.lexists(path)"): (
        "DELIBERATE", "#608's destination walk; "
        "`refuse_a_parent_nobody_can_write_in` asks `os.access`"),
    (SP, "origin_recorded_in", "os.path.isfile(config)"): (
        "DELIBERATE", "describes a taken clone path, and says less on any "
        "failure"),
    (SP, "refuse_a_file_above", "os.path.isdir(above)"): (
        "DELIBERATE", "#608's destination check, as above"),
    (SP, "refuse_a_taken_clone_path", "os.path.lexists(clone)"): (
        "DELIBERATE", "#608's destination check, as above"),
    (SP, "take_away_the_naming_folder", "os.path.isdir(here)"): (
        "OWN", "setup's own `mkdtemp` folder"),
    (SP, "what_blocks", "os.path.isfile(path)"): (
        "DELIBERATE", "words a refusal about a path already found taken"),
    (SP, "what_blocks", "os.path.islink(path)"): ("DELIBERATE", "the same"),
    (SP, "what_stands_at", "os.path.isdir(clone)"): (
        "DELIBERATE", "words a refusal, in a `try` that says less on any "
        "`OSError`"),
    (SP, "what_stands_at",
     'os.path.isfile(os.path.join(clone, "project.yaml"))'): (
        "DELIBERATE", "the same"),
    (SP, "what_stands_at", "os.path.islink(clone)"): (
        "DELIBERATE", "the same"),
    (SP, "what_stands_at", 'os.path.lexists(os.path.join(clone, ".git"))'): (
        "DELIBERATE", "the same"),
    # --- shape-doctor.py ----------------------------------------------------
    (SD, "Context.adopt", "path.is_file()"): (
        "OWN", "the standard's own `adopt-project.py`"),
    (SD, "check_machine", "entry.is_file()"): (
        "OWN", "the standard's own `setup-project.py`"),
    (SD, "check_what_is_here", "(root / FAMILY_MANIFEST).is_file()"): (
        "ASKED", "a NOT A SHAPE ROOT row: `Context` asked the manifest by "
        "`is_a` first"),
    (SD, "check_what_is_here", "(root / PROJECT_MANIFEST).is_file()"): (
        "ASKED", "the same"),
    (SD, "checkout_reach", '(mount / ".gitmodules").is_file()'): (
        "ASKED", "a mount `mount_read` read, `.git` and all (slice C)"),
    (SD, "checkout_reach", "mount.is_dir()"): (
        "ASKED", "the same mount"),
    (SD, "detached", '(path / ".git").exists()'): (
        "ASKED", "a mount `mount_read` read, or a sibling found, or "
        "given `git_dir`"),
    (SD, "everywhere_patterns", "entry.is_file()"): (
        "OWN", "the standard's own templates"),
    (SD, "everywhere_patterns", "template.is_dir()"): (
        "OWN", "the standard's own templates"),
    (SD, "gate_line", "used.is_file()"): (
        "ASKED", "`validator_for` asked by `is_a` and raised a refused "
        "stat (slice C)"),
    (SD, "git_dir_holds",
     "(path if path.is_absolute() else root / path).exists()"): (
        "ASKED", "a path git's `--git-path` named: git read the git "
        "directory first"),
    (SD, "gitmodules_entry", 'os.path.lexists(root / ".gitmodules")'): (
        "ROOT", "the root's `.gitmodules`, by `lstat`, in a root `main` "
        "searched first"),
    (SD, "imports_repo_shape",
     "repo_shape_for(shape, used, own_copy).is_file()"): (
        "ASKED", "beside the validator `validator_for` asked by `is_a`"),
    (SD, "leg_shape_comparison", "template.is_dir()"): (
        "OWN", "the standard's own templates"),
    (SD, "main", "(SHAPE_ROOT / marker).exists()"): (
        "OWN", "the doctor's own checkout of the standard"),
    (SD, "members_verdict",
     '(ctx.root / entry["path"] / ".gitmodules").is_file()'): (
        "ASKED", "only of members whose mount `mount_read` read"),
    (SD, "not_in_the_standard", "(SHAPE_ROOT / marker).exists()"): (
        "OWN", "the doctor's own checkout of the standard"),
    (SD, "origin_url", '(path / ".git").exists()'): (
        "ASKED", "the root, or a sibling `sibling_slot` found"),
    (SD, "placement_policy", "policy_path.is_file()"): (
        "OWN", "the standard's own path policy"),
    (SD, "registered_unindexed", "os.path.lexists(disk)"): (
        "ASKED", "a leg git listed the index of first, by `lstat`"),
    (SD, "same_repository_here", "os.path.exists(path)"): (
        "DELIBERATE", "resolves a remote's local path when it can; a "
        "string compare otherwise"),
    (SD, "shape_file_state", "there.is_file()"): (
        "OWN", "the standard's own copy; the root's was asked by `is_a`"),
    (SD, "sibling_slot", '(sibling / ".git").exists()'): (
        "DELIBERATE", "#735: in a `try`, a folder it cannot enter reads "
        "no `.git` (its docstring)"),
    (SD, "unclonable", "sibling.exists()"): (
        "DELIBERATE", "#784 and #793: in a `try` whose `OSError` is "
        "`unlistable`"),
    (SD, "unclonable", "sibling.is_dir()"): ("DELIBERATE", "the same"),
    (SD, "unclonable", "sibling.is_symlink()"): ("DELIBERATE", "the same"),
    (SD, "unloaded_manifest_row", "used.is_file()"): (
        "ASKED", "`validator_for` asked by `is_a` (slice C)"),
    (SD, "validator_row", "used.is_file()"): (
        "ASKED", "`validator_for` asked by `is_a` (slice C)"),
    # --- src/openreposhape/ -------------------------------------------------
    (f"{SRC}/cli.py", "doctor", "script.is_file()"): (
        "OWN", "the package's own clone of the standard"),
    (f"{SRC}/cli.py", "print_version", "clone.is_dir()"): (
        "OWN", "the package's own cache"),
    (f"{SRC}/cli.py", "run_tool", "script.is_file()"): (
        "OWN", "the package's own clone of the standard"),
    (f"{SRC}/cli.py", "scaffold", "entry.is_file()"): (
        "OWN", "the package's own clone of the standard"),
    (f"{SRC}/standard.py", "beside_checkout",
     "(root / marker).is_file()"): (
        "OWN", "whether the package sits in a checkout"),
    (f"{SRC}/standard.py", "clone_into", "final.is_dir()"): (
        "OWN", "the package's own cache"),
    (f"{SRC}/standard.py", "clone_into", "incoming.exists()"): (
        "OWN", "the package's own cache"),
    (f"{SRC}/standard.py", "filter_repo_in", "os.path.isfile(candidate)"): (
        "OWN", "the package environment's own scripts directory"),
    (f"{SRC}/standard.py", "move_into_place", "final.exists()"): (
        "OWN", "the package's own cache"),
    (f"{SRC}/standard.py", "preflight_entry", "packaged.is_file()"): (
        "OWN", "the package's own data"),
    (f"{SRC}/standard.py", "prepare", "(cache / commit).is_dir()"): (
        "OWN", "the package's own cache"),
    (f"{SRC}/standard.py", "sweep_incoming", "leftover.is_dir()"): (
        "OWN", "the package's own cache"),
    (f"{SRC}/standard.py", "sweep_incoming", "leftover.is_symlink()"): (
        "OWN", "the package's own cache"),
    (f"{SRC}/standard.py", "tree_digest", "module.is_file()"): (
        "OWN", "the package's own clone of the standard"),
    # --- the assembly root's pinned copies ----------------------------------
    (f"{AR}/bootstrap.py", "_cached_tip", "cache.is_file()"): (
        "OWN", "the tool's own cache, `.shape-upstream-tip` (#764)"),
    (f"{AR}/bootstrap.py", "_clone_tip", "Path(upstream).is_dir()"): (
        "DELIBERATE", "the upstream notice: an absent answer by #764's "
        "ruling, in a `try`"),
    (f"{AR}/bootstrap.py", "shape_upstream_notice", "pin_path.is_file()"): (
        "DELIBERATE", "the same notice, which never fails the bootstrap; "
        "`validate-pins.py` has refused the pin by then"),
    (f"{AR}/validate-pins.py", "_also_a_directory", "os.path.isdir(typed)"):
        ("DELIBERATE", "words a hint only, by `os.path` on purpose (its "
         "docstring)"),
    (f"{AR}/validate-pins.py", "_has_own_gate",
     'os.path.isfile(root / "scripts" / "validate-pins.py")'): (
        "DELIBERATE", "words a remedy line for `bump-leg.py` (#478)"),
    # --- the family root's pinned copies ------------------------------------
    (f"{FR}/bootstrap.py", "gitmodules_sections",
     "os.path.isfile(root / GITMODULES)"): (
        "DELIBERATE", "asked after git failed to read the file: git has "
        "no url then either (its docstring)"),
    (f"{FR}/bootstrap.py", "gitmodules_source", GITMODULES_LSTAT): (
        "ROOT", "the holder's `.gitmodules`, by `lstat`"),
    (f"{FR}/siblings.py", "family_link", "os.path.islink(link)"): (
        "DELIBERATE", "a family-named link, by `os.path` on purpose (its "
        "docstring)"),
    (f"{FR}/siblings.py", "holds_git", '(path / ".git").exists()'): (
        "DELIBERATE", "#735's ruling, in a `try` (slice F left it)"),
    (f"{FR}/siblings.py", "not_a_clone", "target.exists()"): (
        "DELIBERATE", "#735, #784 and #793: in a `try`"),
    (f"{FR}/siblings.py", "not_a_clone", "target.is_dir()"): (
        "DELIBERATE", "the same"),
    (f"{FR}/siblings.py", "not_a_clone", "target.is_symlink()"): (
        "DELIBERATE", "the same"),
    (f"{FR}/siblings.py", "parent_folder_warning", "os.path.exists(wanted)"):
        ("DELIBERATE", "words the printed `mv` only (slice F left it, "
         "#459)"),
    (f"{FR}/siblings.py", "parent_folder_warning", "os.path.lexists(wanted)"):
        ("DELIBERATE", "the same"),
    (f"{FR}/siblings.py", "parent_folder_warning", "wanted.exists()"): (
        "DELIBERATE", "the same"),
    (f"{FR}/siblings.py", "parent_folder_warning", "wanted.is_symlink()"): (
        "DELIBERATE", "the same"),
    (f"{FR}/siblings.py", "same_directory", "one.exists()"): (
        "ASKED", "in a `try` with `samefile`, whose `OSError` is False"),
    (f"{FR}/siblings.py", "same_repository_here", "os.path.exists(path)"): (
        "DELIBERATE", "resolves a remote's local path when it can"),
    (f"{FR}/siblings.py", "staging_path", "os.path.lexists(staged)"): (
        "DELIBERATE", "a free staging name for a printed `mv` (its "
        "docstring)"),
    (f"{FR}/validate-family.py", "_anything_at", "os.path.islink(where)"): (
        "ASKED", "a link's own `lstat` first; the rest is `_asked` "
        "(slice E)"),
    (f"{FR}/validate-family.py", "_on_disk", "os.path.islink(where)"): (
        "ASKED", "after `_anything_at` asked it (slice E)"),
    (f"{FR}/validate-family.py", "_check_gitmodules_values",
     GITMODULES_LSTAT): ("ROOT", VF_GITMODULES),
    (f"{FR}/validate-family.py", "_gitmodules_listed", GITMODULES_LSTAT): (
        "ROOT", VF_GITMODULES),
    (f"{FR}/validate-family.py", "_gitmodules_put_back", GITMODULES_LSTAT): (
        "ROOT", VF_GITMODULES),
    (f"{FR}/validate-family.py", "_plain_rm_said", GITMODULES_LSTAT): (
        "ROOT", VF_GITMODULES),
    (f"{FR}/validate-family.py", "_section_back", GITMODULES_LSTAT): (
        "ROOT", VF_GITMODULES),
    (f"{FR}/validate-family.py", "_sections_as_git_reads",
     GITMODULES_LSTAT): ("ROOT", VF_GITMODULES),
    (f"{FR}/validate-family.py", "_stage_first", GITMODULES_LSTAT): (
        "ROOT", VF_GITMODULES),
    # --- update-shape.py ----------------------------------------------------
    (US, "Rollback._nearest_directory", "os.path.isdir(directory)"): (
        "DELIBERATE", "words a by-hand line after a failed restore (its "
        "docstring)"),
    (US, "Rollback._restore", "os.path.lexists(path)"): (
        "DELIBERATE", "the same by-hand line"),
    (US, "Rollback._restore_by_hand", "os.path.isdir(path.parent)"): (
        "DELIBERATE", "the same by-hand line"),
    (US, "Rollback.write_added", "p.exists()"): (
        "OWN", "the run's own `--add` files; a `mkdir` it cannot make "
        "fails by name"),
    (US, "_extend_the_eol_block", "path.is_file()"): (
        "ROOT", "the root's `.gitattributes`: `prepare` searched the root, "
        "and a link there is left alone"),
})

#: Real sites this slice found and did not fix: a path this user cannot
#: read is still taken for one that is not there. Each is the follow-up's.
#: `(file, function, call)`: `(follow-up, what happens)`.
KNOWN_OPEN = _entries({
    (FA, "_gitmodules_names", "(root / GITMODULES).is_file()"): (
        FOLLOW_UP, "a `.gitmodules` that is a link into a folder this user "
        "cannot search: 3.12 raises out of `remove`; 3.14 reads no "
        "section, and `remove --dry-run` says none is removed (slice G "
        "left it for this slice to flag)"),
    (FA, "_sections_giving", "(root / GITMODULES).is_file()"): (
        FOLLOW_UP, "the same file, read as giving the path to no section"),
    (f"{FR}/siblings.py", "submodule_urls", "path.is_file()"): (
        FOLLOW_UP, "the same, in the pinned `siblings.py`: no url read, "
        "so a member is cloned from its row's default"),
    (SD, "check_agent_files", "(ctx.root / name).is_file()"): (
        FOLLOW_UP, "an agent file that is a link into a folder this user "
        "cannot search reads `absent` in the `agent files` note"),
    (SD, "check_what_is_here", "(root / name).exists()"): (
        FOLLOW_UP, "the same for the NOT A SHAPE ROOT row's facts"),
    # r1111's M1: the root's `.git`, asked by a `stat` that follows a link.
    (SD, "check_the_way_in", '(root / ".git").exists()'): (
        FOLLOW_UP, "a `.git` that is a link into a folder this user cannot "
        "search: the `way-in` row says there is no repository to adopt and "
        "sends the person to `setup.sh` to scaffold three new ones"),
    (SD, "check_the_other_way_in", '(ctx.root / ".git").exists()'): (
        FOLLOW_UP, "the same `.git`: the `way-in-scaffold` row is left out"),
    (SD, "origin_org", '(root / ".git").exists()'): (
        FOLLOW_UP, "the same `.git`: None, the answer for a folder that is "
        "no repository"),
    (SD, "repo_local_origin_name", '(root / ".git").exists()'): (
        FOLLOW_UP, "the same `.git`: None, so the `naming` row classifies "
        "the folder's name alone and drops the origin's"),
    ("scripts/shape_advisory.py", "_read", '(root / ".git").exists()'): (
        FOLLOW_UP, "the same `.git`: `not-a-repository`, so the Triad "
        "advisory row is left out"),
    ("scripts/shape_advisory.py", "repository_names",
     '(root / ".git").exists()'): (
        FOLLOW_UP, "the same `.git`: the origin's name is not read for the "
        "Triad advice"),
})


def shipped_tools() -> list[Path]:
    """Every shipped tool: `SHIPPED`, and every Python file where a tool
    could be added without it, so a new one is scanned all the same."""
    found = set(SHIPPED)
    found.update(REPO.glob("*.py"))
    found.update(REPO.glob("scripts/*.py"))
    found.update((REPO / "templates").glob("**/scripts/*.py"))
    found.update((REPO / "src" / "openreposhape").glob("*.py"))
    return sorted(path for path in found if path.is_file())


def relative(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def snippet(text: str, node: ast.AST) -> str:
    """The call's own text, with its line breaks and the spaces inside its
    brackets taken out: the same key however the call is wrapped."""
    said = " ".join(ast.get_source_segment(text, node).split())
    said = re.sub(r"([(\[])\s+", r"\1", said)
    return re.sub(r"\s+([)\]])", r"\1", said)


def _dotted(node: ast.AST) -> str | None:
    """`os.path` for the expression `os.path`, else None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        inner = _dotted(node.value)
        return None if inner is None else f"{inner}.{node.attr}"
    return None


#: What the scan follows a name to: the `os` module, the `os.path` module
#: (or `posixpath` and its twins), or a guard (one of its tests, or a
#: `Path` method of `GUARD_METHODS`).
OS, MODULE, GUARD = "os", "os.path", "guard"
#: The calls that look a module up by its name.
LOOKUPS = frozenset({"importlib.import_module", "import_module",
                     "__import__", "sys.modules.get"})


class Reach(NamedTuple):
    """What the scan knows each name of a file can be: `names`, by kind
    (`OS`, `MODULE`, `GUARD`), the names bound to one, and `attrs` the
    attribute names bound to one on any object (`class C: p = os.path`,
    `self.p = os.path`)."""
    names: dict[str, set[str]]
    attrs: dict[str, set[str]]


def _looked_up(node: ast.AST) -> set[str]:
    """`{OS}` or `{MODULE}` where `node` looks the module up by a constant
    name: `importlib.import_module("os.path")`, `__import__("os")` (which
    gives `os` for `"os.path"` too), `sys.modules["os.path"]` or
    `sys.modules.get(...)`; else nothing."""
    if (isinstance(node, ast.Subscript)
            and _dotted(node.value) == "sys.modules"):
        name = node.slice
    elif (isinstance(node, ast.Call) and node.args
          and _dotted(node.func) in LOOKUPS):
        name = node.args[0]
    else:
        return set()
    if not (isinstance(name, ast.Constant) and isinstance(name.value, str)):
        return set()
    module = name.value
    if isinstance(node, ast.Call) and _dotted(node.func) == "__import__":
        module = module.split(".")[0]
    return ({OS} if module == "os"
            else {MODULE} if module in OS_PATH_MODULES else set())


def _reached(node: ast.AST, reach: Reach) -> set[str]:
    """Which of `OS`, `MODULE` and `GUARD` the expression `node` can be: a
    name or an attribute bound to one, `<os>.path`, `<os.path>.<test>`, any
    `.is_file` and the like, or the module looked up by its name."""
    if isinstance(node, ast.NamedExpr):
        return _reached(node.value, reach)
    if isinstance(node, ast.Name):
        return {kind for kind, names in reach.names.items()
                if node.id in names}
    if not isinstance(node, ast.Attribute):
        return _looked_up(node)
    inner = _reached(node.value, reach)
    found = {kind for kind, attrs in reach.attrs.items() if node.attr in attrs}
    if OS in inner and node.attr == "path":
        found.add(MODULE)
    if node.attr in GUARD_METHODS or (MODULE in inner
                                      and node.attr in OS_PATH_GUARDS):
        found.add(GUARD)
    return found


def _paired(target: ast.expr, value: ast.expr) -> list[tuple]:
    """`(target, value)` for each name a binding of `value` to `target`
    binds, a tuple unpacked element by element (`p, q = os.path, 1`)."""
    if (isinstance(target, (ast.Tuple, ast.List))
            and isinstance(value, (ast.Tuple, ast.List))
            and len(target.elts) == len(value.elts)):
        return [pair for inner, given in zip(target.elts, value.elts)
                for pair in _paired(inner, given)]
    return [(target, value)]


def _bindings(tree: ast.Module) -> list[tuple]:
    """`(target, value)` for each binding in the file whose value the scan
    can see: an assignment (unpacked too), an annotated one, a walrus, a
    `for` over a literal (each element), a `with` (its value, and each
    argument of the call that makes it), a default parameter, and a class
    attribute, as an attribute of any object."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            found += [pair for target in node.targets
                      for pair in _paired(target, node.value)]
        elif (isinstance(node, (ast.AnnAssign, ast.NamedExpr))
              and node.value is not None):
            found.append((node.target, node.value))
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            if isinstance(node.iter, (ast.Tuple, ast.List, ast.Set)):
                found += [pair for given in node.iter.elts
                          for pair in _paired(node.target, given)]
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                made = item.context_expr
                given = ([made, *made.args, *(k.value for k in made.keywords)]
                         if isinstance(made, ast.Call) else [made])
                if item.optional_vars is not None:
                    found += [(item.optional_vars, value) for value in given]
        elif isinstance(node, ast.arguments):
            positional = [*node.posonlyargs, *node.args]
            defaulted = [*zip(positional[len(positional)
                                         - len(node.defaults):],
                              node.defaults),
                         *zip(node.kwonlyargs, node.kw_defaults)]
            found += [(ast.Name(arg.arg, ast.Store()), value)
                      for arg, value in defaulted if value is not None]
        elif isinstance(node, ast.ClassDef):
            found += [(ast.Attribute(ast.Name(node.name, ast.Load()),
                                     target.id, ast.Store()), statement.value)
                      for statement in node.body
                      if isinstance(statement, (ast.Assign, ast.AnnAssign))
                      and statement.value is not None
                      for target in (statement.targets
                                     if isinstance(statement, ast.Assign)
                                     else [statement.target])
                      if isinstance(target, ast.Name)]
    return found


def _os_path_names(tree: ast.Module) -> Reach:
    """What each name of the file can be (`Reach`), so that every way the
    module and its tests are reached is a guard. `OS`: `os`, and `o` after
    `import os as o`. `MODULE`: `posixpath`, `ntpath` and `genericpath`,
    `<os>.path`, `p` after `import os.path as p` or `from os import path
    [as p]`, `path` after `from os import *`, and the module looked up by
    its name (`importlib.import_module`, `__import__`, `sys.modules`).
    `GUARD`: `e` after `from os.path import exists [as e]`, each test after
    `from os.path import *`, and a name bound to a guard (`EX =
    os.path.exists`, `IS_DIR = Path.is_dir`), so that each later call of it
    is a guard of its own. And every binding `_bindings` sees, to any
    depth of such names: `o = os`, `p = os.path`, tuple unpacking, a
    walrus, a `for` or `with` target, a default parameter, a class or
    instance attribute. A name is never dropped: one bound to the module
    once is the module everywhere in the file, which flags too much rather
    than too little.

    Not caught: a guard asked by its name as a string (`getattr`,
    `operator.methodcaller`); the module looked up by a name that is not a
    constant, or through an alias of `importlib` or `sys`; a binding
    through a `for` over anything but a literal, `*`-unpacking, `globals()`,
    `setattr` or a function's return; and the other questions of the same
    kind (`ismount`, `isjunction`, `is_fifo`, `os.access` with `F_OK`, a
    hand-written `stat` whose `OSError` is False). Of the first and the
    last kind but the hand-written `stat`, which no scan tells from a
    reasoned one, the shipped tools hold three today (r1111b's SHOULD 1):
    `getattr(os.path, "isjunction", lambda _: False)`, Windows only, in
    `shape-doctor.py`'s `unclonable` and `siblings.py`'s `not_a_clone` and
    `family_link`, each beside an allowlisted `is_symlink()` or
    `os.path.islink`."""
    reach = Reach({OS: {"os"}, GUARD: set(),
                   MODULE: {name for name in OS_PATH_MODULES
                            if "." not in name}},
                  {OS: set(), MODULE: set(), GUARD: set()})
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os" and alias.asname:
                    reach.names[OS].add(alias.asname)
                elif alias.name in OS_PATH_MODULES and alias.asname:
                    reach.names[MODULE].add(alias.asname)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            for alias in node.names:
                if node.module == "os" and alias.name in ("path", "*"):
                    reach.names[MODULE].add(alias.asname or "path")
                elif node.module in OS_PATH_MODULES and alias.name == "*":
                    reach.names[GUARD].update(OS_PATH_GUARDS)
                elif (node.module in OS_PATH_MODULES
                      and alias.name in OS_PATH_GUARDS):
                    reach.names[GUARD].add(alias.asname or alias.name)
    bound = _bindings(tree)
    grown = True
    while grown:
        grown = False
        for target, value in bound:
            if isinstance(target, ast.Name):
                table, name = reach.names, target.id
            elif isinstance(target, ast.Attribute):
                table, name = reach.attrs, target.attr
            else:
                continue
            for kind in _reached(value, reach):
                if name not in table[kind]:
                    table[kind].add(name)
                    grown = True
    return reach


def guards_in(text: str, file: str) -> list[Site]:
    """Every bare guard in the source `text`: a call, or a reference passed
    as a function, with the function and class it is in."""
    tree = ast.parse(text)
    reach = _os_path_names(tree)
    calls = {id(node.func): node for node in ast.walk(tree)
             if isinstance(node, ast.Call)}

    def is_guard(node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            return (node.id in reach.names[GUARD]
                    and isinstance(node.ctx, ast.Load))
        if not isinstance(node, ast.Attribute):
            return False
        if node.attr in GUARD_METHODS or node.attr in reach.attrs[GUARD]:
            return True
        return (node.attr in OS_PATH_GUARDS
                and MODULE in _reached(node.value, reach))

    found: list[Site] = []

    def visit(node: ast.AST, scope: list[str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)):
                visit(child, [*scope, child.name])
                continue
            if is_guard(child):
                said = calls.get(id(child), child)
                found.append(Site(file, child.lineno,
                                  ".".join(scope) or "<module>",
                                  snippet(text, said)))
            visit(child, scope)

    visit(tree, [])
    return found


def in_a_helper(site: Site) -> bool:
    """Whether the guard is inside a stat helper, a top-level `_is_a` or
    `is_a`: NOT an exemption (r1111's S2). A helper must ask `stat` and
    nothing else, or it answers as Python 3.14 does."""
    return site.scope.split(".")[0] in HELPER_NAMES


def unlisted(sites: list[Site], has_helper: bool,
             allowed: dict | None = None) -> list[str]:
    """What the hygiene test says of each guard that `allowed` (BENIGN and
    KNOWN_OPEN) does not list as often as the function makes it, one
    message each, naming the file and line."""
    allowed = {**BENIGN, **KNOWN_OPEN} if allowed is None else allowed
    counts = Counter(site.key for site in sites)
    how = ("this file's own `_is_a(path, stat.S_ISREG)` (or `S_ISDIR`), "
           "which raises a refused `stat` for the caller to name"
           if has_helper else
           "a local `_is_a`, copied from validate-pins.py's: this file has "
           "none, and a pinned file must not import a newer one from "
           "repo_shape.py (#370, #610)")
    messages = []
    for site in sites:
        limit = allowed.get(site.key, (None, None, 0))[2]
        if counts[site.key] <= limit:
            continue
        if in_a_helper(site):
            messages.append(
                f"{site.file}:{site.line}, in `{site.scope}`: `{site.snippet}`"
                " is a bare guard inside the stat helper itself. The helper "
                "must ask `stat` and nothing else: a guard there answers as "
                "Python 3.14 does, False to any OSError, for every caller "
                "(#430).")
            continue
        over = (f" ({counts[site.key]} such calls in the function, "
                f"{limit} allowed)" if limit else "")
        messages.append(
            f"{site.file}:{site.line}, in `{site.scope}`: `{site.snippet}` "
            f"is a bare guard{over}. From Python 3.14 it answers False to "
            "any OSError, so a path this user cannot read reads as absent "
            f"(#430). Ask {how}; or, where the site is benign, add it to "
            "BENIGN in tests/test_path_guard_hygiene.py, keyed "
            f"{site.key!r}, with a tag from TAGS and a one-line reason.")
    return messages


def stale_entries(found: Counter, allowed: dict) -> list[str]:
    """Each entry of `allowed` that names more calls than `found` holds:
    a guard that has gone, moved to another function or changed its text."""
    return [f"{key!r}: {found[key]} found, {count} listed"
            for key, (_, _, count) in allowed.items() if found[key] < count]


@pytest.fixture(scope="module")
def scanned() -> dict[str, tuple[str, list[Site]]]:
    """`{file: (its source, its guards)}` for every shipped tool."""
    result = {}
    for path in shipped_tools():
        text = path.read_text(encoding="utf-8")
        result[relative(path)] = (text, guards_in(text, relative(path)))
    return result


# --- the hygiene test -------------------------------------------------------

def test_the_scan_reads_every_shipped_tool(scanned):
    """Every file `SHIPPED` names is scanned, every tool the slices fixed
    among them, and the scan finds guards to judge: a scan that read nothing
    would pass every test below."""
    assert {relative(path) for path in SHIPPED} <= set(scanned)
    assert set(HELPERS) <= set(scanned)
    assert sum(len(sites) for _, sites in scanned.values()) > 100


@pytest.mark.parametrize("path", shipped_tools(), ids=relative)
def test_no_bare_guard_outside_a_stat_helper_or_the_allowlist(path, scanned):
    """Each guard is on BENIGN or KNOWN_OPEN with its reason, and none is in
    a stat helper. A new one fails here, by file and line, with what to
    do."""
    text, sites = scanned[relative(path)]
    has_helper = any(isinstance(node, ast.FunctionDef)
                     and node.name in HELPER_NAMES
                     for node in ast.parse(text).body)
    messages = unlisted(sites, has_helper)
    assert not messages, "\n\n".join(messages)


def test_every_allowlist_entry_names_a_guard_that_is_there(scanned):
    """An entry whose call has gone, or moved to another function, or whose
    count no longer matches, fails, so the lists say only what is true."""
    found = Counter(site.key for _, sites in scanned.values()
                    for site in sites)
    stale = stale_entries(found, {**BENIGN, **KNOWN_OPEN})
    assert not stale, (
        "these entries name a guard that is no longer there; take each "
        "out, or put its new function or text in its key:\n"
        + "\n".join(stale))


def entry_problems(benign: dict, known_open: dict, follow_up: str = FOLLOW_UP,
                   doc: str = __doc__) -> list[str]:
    """What is wrong with the allowlists' own entries: a `follow_up` that
    is no issue number, or that the module docstring `doc` does not name
    as the follow-up; a `benign` tag that is not in `TAGS`, a `known_open`
    owner that is not `follow_up`, a reason left empty, a count under one,
    a site on both lists, or one in a stat helper."""
    problems = []
    if not re.fullmatch(r"#\d+", follow_up):
        problems.append(f"FOLLOW_UP {follow_up!r} is no issue number")
    if f"the follow-up, {follow_up}," not in " ".join(doc.split()):
        problems.append(f"the module docstring does not name {follow_up} "
                        "as the follow-up")
    problems += [f"{key!r} is on both lists"
                 for key in sorted(set(benign) & set(known_open))]
    for table, owners in ((benign, TAGS), (known_open, {follow_up})):
        for key, (owner, reason, count) in table.items():
            if owner not in owners:
                problems.append(f"{key!r}: {owner!r} is none of "
                                f"{sorted(owners)}")
            if not reason.strip() or count < 1:
                problems.append(f"{key!r}: no reason, or a count under one")
            if in_a_helper(Site(key[0], 0, key[1], key[2])):
                problems.append(f"{key!r} is in a stat helper")
    return problems


def test_every_allowlist_entry_is_tagged_and_reasoned():
    """Each BENIGN entry carries a tag of `TAGS` and a line of its own, and
    each KNOWN_OPEN entry the follow-up that owns it, an issue the module
    docstring names too (r1111b's NIT 5). No site is on both, and none is
    in a stat helper."""
    assert entry_problems(BENIGN, KNOWN_OPEN) == []


def test_each_wrong_allowlist_entry_is_named():
    """The entries' own proof (r1111b's NIT 5, T6 and Z11): a tag that is
    not in `TAGS`, an owner that is not `FOLLOW_UP`, an empty reason, a
    count of none, a site on both lists or one in a stat helper is each
    named, and so is a `FOLLOW_UP` that is no issue number or that the
    module docstring does not name."""
    good = ("a.py", "f", "p.exists()")
    benign = {good: ("OWN", "a reason", 1),
              ("a.py", "g", "p.exists()"): ("MINE", "a reason", 1),
              ("a.py", "h", "p.exists()"): ("OWN", " ", 1),
              ("a.py", "_is_a", "p.exists()"): ("OWN", "a reason", 1)}
    known_open = {good: (FOLLOW_UP, "a reason", 1),
                  ("a.py", "k", "p.exists()"): ("#1101", "a reason", 1),
                  ("a.py", "m", "p.exists()"): (FOLLOW_UP, "a reason", 0)}
    assert entry_problems(benign, known_open) == [
        f"{good!r} is on both lists",
        f"{('a.py', 'g', 'p.exists()')!r}: 'MINE' is none of "
        f"{sorted(TAGS)}",
        f"{('a.py', 'h', 'p.exists()')!r}: no reason, or a count under one",
        f"{('a.py', '_is_a', 'p.exists()')!r} is in a stat helper",
        f"{('a.py', 'k', 'p.exists()')!r}: '#1101' is none of "
        f"['{FOLLOW_UP}']",
        f"{('a.py', 'm', 'p.exists()')!r}: no reason, or a count under one",
    ]
    # r1111b's Z11: a typo in `FOLLOW_UP`, or a value that is no issue.
    assert entry_problems({}, {}, "#1101") == [
        "the module docstring does not name #1101 as the follow-up"]
    assert entry_problems({}, {}, "1110", "the follow-up, 1110, ...") == [
        "FOLLOW_UP '1110' is no issue number"]


#: Each way a guard can be written, and the key the scan gives it.
SPELLINGS = '''
import os
import os as system
import os.path as osp
from os import path as ospath
from os.path import lexists, isdir as is_directory
from pathlib import Path
from typing import Any
held = os.path
again = held
late = early
early = os.path
typed: Any = os.path

def _is_a(path, kind):
    return path.is_file()

def asks(here: Path):
    here.is_file(); here.is_dir(); here.exists(); here.is_symlink()
    os.path.isfile(here); os.path.isdir(here); os.path.exists(here)
    os.path.lexists(here); os.path.islink(here)
    osp.exists(here); ospath.isfile(here); lexists(here)
    is_directory(here); system.path.isfile(here); again.islink(here)
    late.isdir(here); typed.lexists(here)
    list(filter(os.path.exists, [here])); list(map(Path.is_dir, [here]))
    os.stat(here); here.stat(); here.lstat(); system.stat(here)

class Holder:
    def method(self):
        return (self.root
                / "x").exists()
'''


def test_the_scan_finds_every_spelling_and_nothing_else():
    """The scan's own proof, independent of the tree: each spelling of a
    guard it covers is found, wrapped or not, imported or bound under any
    name or passed as a function; a `stat` is not; and the one inside
    `_is_a` is refused as a guard in the helper (r1111's X4). `late` is
    bound before `early` is, so only a second pass of the alias fixpoint
    finds it (r1111b's R2), and `typed` by an annotated assignment (R3)."""
    sites = guards_in(SPELLINGS, "spellings.py")
    assert [(site.scope, site.snippet) for site in sites] == [
        ("_is_a", "path.is_file()"),
        ("asks", "here.is_file()"), ("asks", "here.is_dir()"),
        ("asks", "here.exists()"), ("asks", "here.is_symlink()"),
        ("asks", "os.path.isfile(here)"), ("asks", "os.path.isdir(here)"),
        ("asks", "os.path.exists(here)"), ("asks", "os.path.lexists(here)"),
        ("asks", "os.path.islink(here)"), ("asks", "osp.exists(here)"),
        ("asks", "ospath.isfile(here)"), ("asks", "lexists(here)"),
        ("asks", "is_directory(here)"), ("asks", "system.path.isfile(here)"),
        ("asks", "again.islink(here)"), ("asks", "late.isdir(here)"),
        ("asks", "typed.lexists(here)"), ("asks", "os.path.exists"),
        ("asks", "Path.is_dir"),
        ("Holder.method", '(self.root / "x").exists()'),
    ]
    messages = unlisted(sites, has_helper=True)
    assert len(messages) == len(sites) == 21
    assert messages[0] == (
        "spellings.py:16, in `_is_a`: `path.is_file()` is a bare guard "
        "inside the stat helper itself. The helper must ask `stat` and "
        "nothing else: a guard there answers as Python 3.14 does, False to "
        "any OSError, for every caller (#430).")
    assert messages[1].startswith("spellings.py:19, in `asks`: "
                                  "`here.is_file()` is a bare guard.")
    assert "this file's own `_is_a(" in messages[1]
    assert "a local `_is_a`, copied from validate-pins.py's" in unlisted(
        sites, has_helper=False)[1]


#: r1111b's NIT 2: each way of reaching a guard the scan did not follow,
#: planted in a file of its own, and every guard the scan must find there.
PLANTED = {
    "o-is-os": ("import os\no = os\n\ndef f(x):\n"
                "    return o.path.isfile(x)\n", [("f", "o.path.isfile(x)")]),
    "star-from-os-path": ("from os.path import *\n\ndef f(x):\n"
                          "    return isfile(x)\n", [("f", "isfile(x)")]),
    "star-from-os": ("from os import *\n\ndef f(x):\n"
                     "    return path.isfile(x)\n", [("f", "path.isfile(x)")]),
    "tuple-unpacking": ("import os\np, q = os.path, 1\n\ndef f(x):\n"
                        "    return p.isfile(x)\n", [("f", "p.isfile(x)")]),
    "walrus": ("import os\n\ndef f(x):\n"
               "    return (q := os.path).isfile(x) or q.isdir(x)\n",
               [("f", "(q := os.path).isfile(x)"), ("f", "q.isdir(x)")]),
    "for-target": ("import os\n\ndef f(x):\n    for q in (os.path,):\n"
                   "        return q.isfile(x)\n", [("f", "q.isfile(x)")]),
    "with-target": ("import contextlib\nimport os\n\ndef f(x):\n"
                    "    with contextlib.nullcontext(os.path) as q:\n"
                    "        return q.isfile(x)\n", [("f", "q.isfile(x)")]),
    "default-parameter": ("import os\n\ndef f(x, q=os.path):\n"
                          "    return q.isfile(x)\n", [("f", "q.isfile(x)")]),
    "class-attribute": ("import os\n\nclass C:\n    p = os.path\n\n"
                        "    def f(self, x):\n"
                        "        return self.p.isfile(x)\n",
                        [("C.f", "self.p.isfile(x)")]),
    "instance-attribute": ("import os\n\nclass C:\n    def __init__(self):\n"
                           "        self.p = os.path\n\n    def f(self, x):\n"
                           "        return self.p.isfile(x)\n",
                           [("C.f", "self.p.isfile(x)")]),
    "guard-bound-once": ("import os\nEX = os.path.exists\n\ndef f(x):\n"
                         "    return EX(x)\n\ndef g(x):\n    return EX(x)\n",
                         [("<module>", "os.path.exists"), ("f", "EX(x)"),
                          ("g", "EX(x)")]),
    "test-bound-again": ("from os.path import isfile\nchk = isfile\n\n"
                         "def f(x):\n    return chk(x)\n",
                         [("<module>", "isfile"), ("f", "chk(x)")]),
    "method-bound-once": ("from pathlib import Path\nIS_DIR = Path.is_dir\n\n"
                          "def f(x):\n    return IS_DIR(x)\n",
                          [("<module>", "Path.is_dir"), ("f", "IS_DIR(x)")]),
    "guard-as-attribute": ("import os\n\nclass C:\n    ex = os.path.exists\n\n"
                           "    def f(self, x):\n        return self.ex(x)\n",
                           [("C", "os.path.exists"), ("C.f", "self.ex(x)")]),
    "importlib": ("import importlib\nP = importlib.import_module('os.path')\n"
                  "\ndef f(x):\n    return P.isfile(x)\n",
                  [("f", "P.isfile(x)")]),
    "dunder-import": ("o = __import__('os.path')\n\ndef f(x):\n"
                      "    return o.path.isfile(x)\n",
                      [("f", "o.path.isfile(x)")]),
    "sys-modules": ("import sys\n\ndef f(x):\n"
                    "    return sys.modules['posixpath'].isfile(x)\n",
                    [("f", "sys.modules['posixpath'].isfile(x)")]),
    "sys-modules-get": ("import sys\nP = sys.modules.get('os')\n\ndef f(x):\n"
                        "    return P.path.isfile(x)\n",
                        [("f", "P.path.isfile(x)")]),
    # r1149's NIT 3: one planted file for each binding no row held.
    "nested-tuple": ("import os\n(a, (p, q)) = (1, (os.path, 2))\n\n"
                     "def f(x):\n    return p.isfile(x)\n",
                     [("f", "p.isfile(x)")]),
    "comprehension-target": ("import os\n\ndef f(x):\n"
                             "    return [q.isfile(x) for q in (os.path,)]\n",
                             [("f", "q.isfile(x)")]),
    "keyword-only-default": ("import os\n\ndef f(x, *, q=os.path):\n"
                             "    return q.isfile(x)\n",
                             [("f", "q.isfile(x)")]),
    "annotated-class-attribute": ("import os\n\nclass C:\n"
                                  "    p: object = os.path\n\n"
                                  "    def f(self, x):\n"
                                  "        return self.p.isfile(x)\n",
                                  [("C.f", "self.p.isfile(x)")]),
    "bare-os-path-twins": ("import genericpath\nimport ntpath\n"
                           "import posixpath\n\ndef f(x):\n"
                           "    return (posixpath.isfile(x) or ntpath.isdir(x)"
                           "\n            or genericpath.exists(x))\n",
                           [("f", "posixpath.isfile(x)"),
                            ("f", "ntpath.isdir(x)"),
                            ("f", "genericpath.exists(x)")]),
}


@pytest.mark.parametrize("planted", PLANTED)
def test_the_scan_follows_each_planted_binding(planted):
    """r1111b's NIT 2 (and its Z6 and Z7): each binding the scan did not
    follow is followed now, and finds the guard planted behind it, and
    nothing else in that file."""
    text, found = PLANTED[planted]
    assert [(site.scope, site.snippet)
            for site in guards_in(text, "planted.py")] == found


#: A function that makes one call twice, for the count's own proof.
COUNTED = '''
def twice(here):
    return here.exists() or here.exists()
'''


def test_an_entry_allows_as_many_calls_as_it_counts_and_no_more():
    """The count's own proof (r1111's T2 and T3): an entry for one call does
    not cover two, one for two covers both, and one that names more calls
    than the function makes, or a call it no longer makes, is stale."""
    sites = guards_in(COUNTED, "counted.py")
    key = ("counted.py", "twice", "here.exists()")
    found = Counter(site.key for site in sites)
    once, twice, thrice = ({key: ("OWN", "a test", count)}
                           for count in (1, 2, 3))
    messages = unlisted(sites, True, once)
    assert len(messages) == 2
    assert all("(2 such calls in the function, 1 allowed)" in message
               for message in messages)
    assert unlisted(sites, True, twice) == []
    assert stale_entries(found, twice) == []
    assert stale_entries(found, thrice) == [f"{key!r}: 2 found, 3 listed"]
    assert stale_entries(Counter(), once) == [f"{key!r}: 0 found, 1 listed"]


# --- the parity test --------------------------------------------------------

#: The handlers a helper may hold on the way from its `stat` to its answer:
#: `OSError`, which re-raises what is not absent; `ValueError`, a name no
#: system can take (a NUL in it); and `FileNotFoundError` and
#: `NotADirectoryError`, which are ENOENT and ENOTDIR, two absent errnos.
HANDLERS = frozenset({"OSError", "ValueError", "FileNotFoundError",
                      "NotADirectoryError"})
#: Each kind of `try`, `except*` too where this Python has it.
TRIES = tuple(getattr(ast, name) for name in ("Try", "TryStar")
              if hasattr(ast, name))


class AbsentSets(NamedTuple):
    """What a helper reads as nothing there, and what it may not do: each
    set as the helper spells it, every one it compares with, and each way
    on the path from its `stat` to its `raise` that would answer otherwise."""
    errnos: list[frozenset]
    winerrors: list[frozenset]
    refused: list[str]


def _constants(tree: ast.Module) -> dict[str, ast.expr]:
    """The module's own top-level `NAME = value` assignments."""
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            found[node.targets[0].id] = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None \
                and isinstance(node.target, ast.Name):
            found[node.target.id] = node.value
    return found


def _errno_names(tree: ast.Module) -> frozenset:
    """The names the file binds the `errno` module to: `errno`, and `E`
    after `import errno as E`."""
    return frozenset(alias.asname or alias.name for node in ast.walk(tree)
                     if isinstance(node, ast.Import) for alias in node.names
                     if alias.name == "errno")


def _members(expr: ast.expr, constants: dict, errnos: frozenset) -> frozenset:
    """The values of a set the helper compares with: a module constant or a
    literal, bare or in `frozenset(...)` or `set(...)`, each element
    `errno.<NAME>` (by name, through any of `errnos`, the names the file
    binds the module to) or a number. Anything else is refused, rather
    than guessed at, and named as the source writes it (`ast.unparse`):
    `ast.dump` leaves out `ctx=Load()` and the other defaults from Python
    3.13, so a message built from it reads differently on each Python."""
    if isinstance(expr, ast.Name):
        if expr.id not in constants:
            raise LookupError(f"`{expr.id}` is no constant of the module")
        expr = constants[expr.id]
    if (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name)
            and expr.func.id in ("frozenset", "set")
            and len(expr.args) == 1 and not expr.keywords):
        expr = expr.args[0]
    if not isinstance(expr, (ast.Tuple, ast.List, ast.Set)):
        raise ValueError(f"`{ast.unparse(expr)}` is no literal set")
    members = set()
    for element in expr.elts:
        if (isinstance(element, ast.Attribute)
                and isinstance(element.value, ast.Name)
                and element.value.id in errnos):
            members.add(element.attr)
        elif isinstance(element, ast.Constant) and type(element.value) is int:
            members.add(element.value)
        else:
            raise ValueError(f"`{ast.unparse(element)}` is neither "
                             "`errno.<NAME>` nor a number")
    return frozenset(members)


def _caught(handler: ast.ExceptHandler) -> list[str]:
    """What an `except` names, `except:` as `BaseException`."""
    if handler.type is None:
        return ["BaseException"]
    names = (handler.type.elts if isinstance(handler.type, ast.Tuple)
             else [handler.type])
    return [_dotted(name) or ast.unparse(name) for name in names]


def _asked(node: ast.AST) -> str | None:
    """`errno` or `winerror` where `node` reads one off an exception:
    `<exc>.errno`, `<exc>.winerror` or `getattr(<exc>, "winerror", ...)`."""
    if isinstance(node, ast.Attribute) and node.attr in ("errno",
                                                         "winerror"):
        return node.attr
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "getattr" and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value in ("errno", "winerror")):
        return node.args[1].value
    return None


def _calls_out(nodes: list, functions: dict, followed: tuple = ()) -> bool:
    """Whether `nodes` make a call that could reach a `stat`: any call but
    one of a function of the module that makes none itself."""
    for node in (inner for outer in nodes for inner in ast.walk(outer)):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else None
        if name not in functions:
            return True
        if name not in followed and _calls_out(
                functions[name].body, functions, (*followed, name)):
            return True
    return False


def _reraises(node: ast.AST, handler: ast.ExceptHandler) -> bool:
    """Whether `node` raises again what `handler` caught: a bare `raise`,
    or `raise exc` of the name it caught it as."""
    return isinstance(node, ast.Raise) and node.cause is None and (
        node.exc is None or (isinstance(node.exc, ast.Name)
                             and node.exc.id == handler.name))


def absent_sets(text: str, helper: str) -> AbsentSets:
    """The helper's sets, read through every function of the module it
    calls (`_absent`, `_mode_of`, `_says_absent`, `refused_read`): each
    `<exc>.errno in <set>` and `getattr(<exc>, "winerror", None) in <set>`,
    or `not in <set>`.

    `refused` names, on that path (r1111's S1), which is each `try` that
    makes a call (`_calls_out`; one that calls nothing, a dict's
    `KeyError` say, cannot catch a refused `stat`): a handler for anything
    but `HANDLERS` (`PermissionError`, `Exception`, `except:`), which would
    answer before the set is asked; an `except OSError` that does not
    re-raise (`_reraises`); and, anywhere in those functions, an `errno`
    or `winerror` read any other way than `in` or `not in <set>` (`==
    errno.EACCES`), which would put another errno beside the set. The
    behaviour test asks what this cannot read."""
    tree = ast.parse(text)
    defined = {node.name: node for node in tree.body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                    ast.ClassDef))}
    if helper not in defined:
        raise LookupError(f"no function `{helper}` in the module")
    if not isinstance(defined[helper], ast.FunctionDef):
        kind = ("a class" if isinstance(defined[helper], ast.ClassDef)
                else "an async def")
        raise LookupError(f"`{helper}` is {kind}, not a plain function")
    functions = {name: node for name, node in defined.items()
                 if isinstance(node, ast.FunctionDef)}
    constants, names = _constants(tree), _errno_names(tree)
    seen, queue = [], [helper]
    while queue:
        name = queue.pop(0)
        if name in seen or name not in functions:
            continue
        seen.append(name)
        queue.extend(node.func.id for node in ast.walk(functions[name])
                     if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Name))
    errnos, winerrors, refused, approved = [], [], [], set()
    for name in seen:
        for node in ast.walk(functions[name]):
            for handler in (node.handlers if isinstance(node, TRIES)
                            and _calls_out(node.body, functions) else []):
                caught = _caught(handler)
                if not set(caught) <= HANDLERS:
                    refused.append(f"`{name}` catches "
                                   f"{', '.join(caught)}, which answers "
                                   "before the set is asked")
                elif "OSError" in caught and not any(
                        _reraises(inner, handler)
                        for inner in ast.walk(handler)):
                    refused.append(f"`{name}`'s `except OSError` does not "
                                   "re-raise what is not absent")
            if not (isinstance(node, ast.Compare) and len(node.ops) == 1
                    and isinstance(node.ops[0], (ast.In, ast.NotIn))):
                continue
            kind = _asked(node.left)
            if kind is None or _asked(node.comparators[0]) is not None:
                continue
            approved.add(id(node.left))
            (errnos if kind == "errno" else winerrors).append(
                _members(node.comparators[0], constants, names))
        refused += [f"`{name}` reads "
                    f"`{ast.get_source_segment(text, node)}` other than "
                    "as `in` or `not in <set>`"
                    for node in ast.walk(functions[name])
                    if _asked(node) and id(node) not in approved]
    return AbsentSets(errnos, winerrors, refused)


def parity_problems(text: str, helper: str) -> list[str]:
    """What is wrong with the helper against the one rule, or nothing."""
    try:
        found = absent_sets(text, helper)
    except (LookupError, ValueError) as exc:
        return [f"its sets cannot be read: {exc}"]
    problems = []
    if not found.errnos:
        problems.append("it compares `errno` with no set")
    if not found.winerrors:
        problems.append("it compares `winerror` with no set")
    problems += [f"its errnos are {sorted(map(str, wrong))}"
                 for wrong in found.errnos if wrong != ABSENT_ERRNOS]
    problems += [f"its Windows errors are {sorted(map(str, wrong))}"
                 for wrong in found.winerrors if wrong != ABSENT_WINERRORS]
    return problems + found.refused


def _helpers(scanned) -> list[tuple[str, str]]:
    """`(file, helper)` for every top-level `_is_a` or `is_a` shipped, a
    class or an `async def` of that name among them (r1111's N2), which the
    parity test then refuses."""
    return sorted((file, node.name) for file, (text, _) in scanned.items()
                  for node in ast.parse(text).body
                  if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                       ast.ClassDef))
                  and node.name in HELPER_NAMES)


def test_each_slices_helper_is_still_there(scanned):
    """The helpers slices A to H wrote are found by the parity test, so
    none is held to nothing because it was renamed."""
    assert set(HELPERS.items()) <= set(_helpers(scanned))


def test_every_stat_helper_holds_the_one_errno_set(scanned):
    """Every `_is_a` (and the doctor's `is_a`), the twelve and any added
    later, reads ENOENT, ENOTDIR, EBADF and ELOOP, and Windows' 21, 123 and
    1921, as absent, asks `errno` and `winerror` only as `in` or `not in`
    those sets, catches nothing on the way from its `stat` to its answer
    but `OSError`, `ValueError` and the two absent subclasses,
    `FileNotFoundError` and `NotADirectoryError`, and re-raises in its
    `except OSError`, by `raise` or by `raise exc` of the name it caught."""
    problems = [f"{file}'s `{helper}`: {problem}"
                for file, helper in _helpers(scanned)
                for problem in parity_problems(scanned[file][0], helper)]
    assert not problems, "\n".join(problems)


def _augmented(tree: ast.Module) -> list[str]:
    """The `*ABSENT_ERRNOS` and `*ABSENT_WINERRORS` constants a top-level
    augmented assignment (`+=`, `|=`) changes after they are set: the one
    change `_constants`, which keeps each name's last plain assignment,
    never sees (r1149's S1). The behaviour test asks every errno, but only
    two Windows errors; this holds the rest."""
    return [node.target.id for node in tree.body
            if isinstance(node, ast.AugAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id.endswith(("ABSENT_ERRNOS",
                                         "ABSENT_WINERRORS"))]


def absent_constant_problems(text: str, file: str) -> tuple[int, list[str]]:
    """How many `*ABSENT_ERRNOS` and `*ABSENT_WINERRORS` constants `text`
    holds, and which are wrong: not the one set, or changed by a top-level
    augmented assignment after it is set."""
    tree = ast.parse(text)
    wrong = [f"{file}: {name} is changed by an augmented assignment"
             for name in _augmented(tree)]
    seen = 0
    for name, value in _constants(tree).items():
        expected = (ABSENT_ERRNOS if name.endswith("ABSENT_ERRNOS")
                    else ABSENT_WINERRORS
                    if name.endswith("ABSENT_WINERRORS") else None)
        if expected is None:
            continue
        seen += 1
        if _members(value, {}, _errno_names(tree)) != expected:
            wrong.append(f"{file}: {name}")
    return seen, wrong


def test_every_absent_constant_is_the_one_set(scanned):
    """Each module constant named `*ABSENT_ERRNOS` or `*ABSENT_WINERRORS`
    is the one set, where a helper reads it or not (`validate-pins.py`'s
    `_digest_from_source` reads `_ABSENT_ERRNOS` inline), and none is
    changed by a top-level `+=` after it is set."""
    wrong, seen = [], 0
    for file, (text, _) in scanned.items():
        more, bad = absent_constant_problems(text, file)
        seen += more
        wrong += bad
    assert seen >= 2 * len(HELPERS), seen
    assert not wrong, wrong


def test_a_wrong_or_augmented_absent_constant_is_named():
    """The constants check's own proof (r1149's S1): the right sets are
    taken; a wrong set is named; a top-level `+=` or `|=` on either
    constant is named, one on another name is not, and neither is one
    inside a function."""
    sets = ("import errno\n_ABSENT_ERRNOS = (errno.ENOENT, errno.ENOTDIR, "
            "errno.EBADF, errno.ELOOP)\n_ABSENT_WINERRORS = (21, 123, 1921)"
            "\n")
    assert absent_constant_problems(sets, "a.py") == (2, [])
    assert absent_constant_problems(
        sets.replace("errno.ELOOP", "errno.EACCES"), "a.py") == (
        2, ["a.py: _ABSENT_ERRNOS"])
    assert absent_constant_problems(
        sets + "_ABSENT_ERRNOS += (errno.ESTALE,)\n_ABSENT_WINERRORS |= {5}\n"
        "ABSENT_ERRNOS += (errno.EIO,)\n_OTHER = (1,)\n_OTHER += (2,)\n\n"
        "def f():\n    _ABSENT_ERRNOS = ()\n    _ABSENT_ERRNOS += (1,)\n",
        "a.py") == (2, [
            "a.py: _ABSENT_ERRNOS is changed by an augmented assignment",
            "a.py: _ABSENT_WINERRORS is changed by an augmented assignment",
            "a.py: ABSENT_ERRNOS is changed by an augmented assignment"])


@pytest.mark.parametrize("spelled, wanted", [
    ("frozenset({errno.ENOENT, 2})", {"ENOENT", 2}),
    ("set([errno.EBADF])", {"EBADF"}),
    ("sorted((errno.ENOENT, 2))", ValueError),
    ("tuple({errno.ENOENT})", ValueError),
], ids=["frozenset", "set", "sorted", "tuple"])
def test_members_unwrap_a_frozenset_or_a_set_and_no_other_call(spelled,
                                                               wanted):
    """r1149's V15: `_members` takes a literal bare or in `frozenset(...)`
    or `set(...)`, as the parity test's twin table has it, and refuses a
    literal in any other call, which could change it (`sorted`, `tuple`),
    naming it as the source writes it."""
    expr = ast.parse(spelled, mode="eval").body
    if wanted is ValueError:
        with pytest.raises(ValueError) as refused:
            _members(expr, {}, frozenset({"errno"}))
        assert str(refused.value) == f"`{spelled}` is no literal set"
    else:
        assert _members(expr, {}, frozenset({"errno"})) == wanted


#: A helper in `adopt-project.py`'s and `scripts/family.py`'s shape (slices
#: H and G), without their docstrings and annotations: its two sets module
#: constants, asked in an `_absent` of its own. Slice A's
#: `scripts/bump-leg.py` asks the same sets inline, with no `_absent`. And
#: the variants the parity test refuses.
HELPER = '''
import errno
_ABSENT_ERRNOS = (errno.ENOENT, errno.ENOTDIR, errno.EBADF, errno.ELOOP)
_ABSENT_WINERRORS = (21, 123, 1921)

def _absent(exc):
    return (exc.errno in _ABSENT_ERRNOS
            or getattr(exc, "winerror", None) in _ABSENT_WINERRORS)

def _is_a(path, kind):
    try:
        mode = path.stat().st_mode
    except OSError as exc:
        if _absent(exc):
            return False
        raise
    except ValueError:
        return False
    return kind(mode)
'''
ANSWERS = "    except OSError as exc:\n"
LAST = "    except ValueError:\n        return False\n"


@pytest.mark.parametrize("change, said", [
    (("errno.ELOOP)", "errno.ELOOP, errno.EACCES)"),
     "its errnos are ['EACCES', 'EBADF', 'ELOOP', 'ENOENT', 'ENOTDIR']"),
    ((", errno.EBADF", ""), "its errnos are ['ELOOP', 'ENOENT', 'ENOTDIR']"),
    (("123, 1921", "123"), "its Windows errors are ['123', '21']"),
    (("        raise\n", "        return False\n"),
     "`_is_a`'s `except OSError` does not re-raise what is not absent"),
    (("in _ABSENT_ERRNOS", "in ABSENT"),
     "its sets cannot be read: `ABSENT` is no constant of the module"),
    ((ANSWERS, "    except PermissionError:\n        return False\n"
      + ANSWERS),
     "`_is_a` catches PermissionError, which answers before the set is "
     "asked"),
    ((ANSWERS, "    except Exception:\n        return False\n" + ANSWERS),
     "`_is_a` catches Exception, which answers before the set is asked"),
    ((LAST, LAST + "    except:\n        return False\n"),
     "`_is_a` catches BaseException, which answers before the set is "
     "asked"),
    (("in _ABSENT_WINERRORS)",
      "in _ABSENT_WINERRORS\n            or exc.errno == errno.EACCES)"),
     "`_absent` reads `exc.errno` other than as `in` or `not in <set>`"),
    (("def _is_a(path, kind):", "async def _is_a(path, kind):"),
     "its sets cannot be read: `_is_a` is an async def, not a plain "
     "function"),
    (("def _is_a(path, kind):",
      "class _is_a:\n    pass\n\ndef _is_b(path, kind):"),
     "its sets cannot be read: `_is_a` is a class, not a plain function"),
    # r1111b's R13: an element it cannot read is refused, never skipped.
    (("errno.ELOOP)", "errno.ELOOP, EACCES)"),
     "its sets cannot be read: `EACCES` is neither `errno.<NAME>` nor a "
     "number"),
    # The row above once said `Name(id='EACCES', ctx=Load())`, which is what
    # `ast.dump` prints up to 3.12; from 3.13 it leaves `ctx=Load()` out, and
    # CI's first run of this file, on 3.14, failed on it. Each message that
    # names a piece of the helper writes it as the source does now, and these
    # two rows pin the other two ways it is built (`_members`, `_caught`).
    (("in _ABSENT_ERRNOS", "in sorted(_ABSENT_ERRNOS)"),
     "its sets cannot be read: `sorted(_ABSENT_ERRNOS)` is no literal set"),
    ((ANSWERS, "    except errors():\n        return False\n" + ANSWERS),
     "`_is_a` catches errors(), which answers before the set is asked"),
])
def test_the_parity_test_refuses_another_set(change, said):
    """The parity test's own proof: the `HELPER` passes, and each one-line
    change to its set, its handlers, its `errno` question or its kind is
    named (r1111's X5, X6, X15 and X18 among them, and r1111b's R13). A
    message that names a piece of the helper names it as the source writes
    it (`ast.unparse`), the same on every Python."""
    assert parity_problems(HELPER, "_is_a") == []
    old, new = change
    assert HELPER.count(old) == 1
    assert said in parity_problems(HELPER.replace(old, new), "_is_a")


def _changed(text: str, changes: list) -> str:
    """`text` with each `(old, new)` of `changes` made in turn, each `old`
    found exactly once, so that no change is silently a no-op."""
    for old, new in changes:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    return text


#: The `HELPER`'s set, as it spells it.
SET = "(errno.ENOENT, errno.ENOTDIR, errno.EBADF, errno.ELOOP)"
#: `_absent`, spelled with `not in`.
NOT_IN = ('    return (exc.errno in _ABSENT_ERRNOS\n'
          '            or getattr(exc, "winerror", None) in '
          '_ABSENT_WINERRORS)',
          '    return not (exc.errno not in _ABSENT_ERRNOS\n'
          '                and getattr(exc, "winerror", None)\n'
          '                not in _ABSENT_WINERRORS)')
#: A function the helper calls, with a `try` of its own.
NOTE = ("def _note(x):\n    try:\n        return {}\n    except {}:\n"
        "        return None\n\ndef _is_a(path, kind):\n    _note(path)\n")
IS_A = "def _is_a(path, kind):\n"


@pytest.mark.parametrize("right, wrong, said", [
    ([NOT_IN], [NOT_IN, ("not in _ABSENT_ERRNOS",
                         "not in (errno.ENOENT, errno.EACCES)")],
     "its errnos are ['EACCES', 'ENOENT']"),
    ([("        raise\n", "        raise exc\n")],
     [("        raise\n",
       "        raise FileNotFoundError(errno.ENOENT, str(exc))\n")],
     "`_is_a`'s `except OSError` does not re-raise what is not absent"),
    # r1149's V22: another name is not what the handler caught.
    ([("        raise\n", "        raise exc\n")],
     [("        raise\n", "        other = FileNotFoundError(errno.ENOENT, "
       "str(exc))\n        raise other\n")],
     "`_is_a`'s `except OSError` does not re-raise what is not absent"),
    ([(SET, f"frozenset({{{SET[1:-1]}}})")],
     [(SET, f"frozenset({{{SET[1:-1]}}}) | {{errno.EACCES}}")],
     f"`frozenset({{{SET[1:-1]}}}) | {{errno.EACCES}}` is no literal set"),
    ([("import errno\n", "import errno as E\n"),
      (SET, SET.replace("errno.", "E."))],
     [("import errno\n", "import errno\n\nclass E:\n"
       "    ENOENT = ENOTDIR = EBADF = ELOOP = errno.EACCES\n"),
      (SET, SET.replace("errno.", "E."))],
     "`E.ENOENT` is neither `errno.<NAME>` nor a number"),
    ([(ANSWERS, "    except (FileNotFoundError, NotADirectoryError):\n"
       "        return False\n" + ANSWERS)],
     [(ANSWERS, "    except (FileNotFoundError, PermissionError):\n"
       "        return False\n" + ANSWERS)],
     "`_is_a` catches FileNotFoundError, PermissionError, which answers "
     "before the set is asked"),
    ([(IS_A, NOTE.format("{}[x]", "KeyError"))],
     [(IS_A, NOTE.format("x.stat()", "PermissionError"))],
     "`_note` catches PermissionError, which answers before the set is "
     "asked"),
], ids=["not-in", "raise-exc", "raise-other-name", "frozenset", "errno-as",
        "absent-handlers", "unrelated-handler"])
def test_the_parity_test_takes_a_correct_spelling_and_refuses_its_twin(
        right, wrong, said, tmp_path):
    """r1111b's NIT 3: each correct spelling the parity test refused is
    taken now (`errno not in`, `raise exc`, a `frozenset({...})`, `import
    errno as E`, `except (FileNotFoundError, NotADirectoryError)`, an
    unrelated `except KeyError` in a function the helper calls), and the
    nearest wrong one beside it is still refused, by name. The behaviour
    test agrees: the first answers as it should, and the twin does not."""
    assert parity_problems(_changed(HELPER, right), "_is_a") == []
    assert behaviour_problems(_changed(HELPER, right), "_is_a",
                              tmp_path) == []
    refused = parity_problems(_changed(HELPER, wrong), "_is_a")
    assert any(said in problem for problem in refused), refused
    assert behaviour_problems(_changed(HELPER, wrong), "_is_a", tmp_path)


def test_a_class_or_an_async_def_by_a_helpers_name_is_held_to_parity():
    """`_helpers` lists a class and an `async def` by a helper's name, so
    that the parity test refuses them (r1111b's R7), and no other name."""
    found = _helpers({
        "a.py": ("class _is_a:\n    pass\n", []),
        "b.py": ("async def is_a(path, kind):\n    pass\n", []),
        "c.py": ("def is_b(path, kind):\n    pass\n\n\nclass Holder:\n"
                 "    def _is_a(self):\n        pass\n", []),
    })
    assert found == [("a.py", "_is_a"), ("b.py", "is_a")]


# --- the behaviour test -----------------------------------------------------

#: What a function, class, lambda or comprehension keeps to itself.
SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda,
          ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
#: `loaded_helper` compiles as `from __future__ import annotations` does,
#: so no annotation is ever evaluated, and none needs its import.
ANNOTATIONS = __future__.annotations.compiler_flag
#: The name whose `stat` the behaviour test refuses.
ASKED = "asked-by-the-behaviour-test"
#: How many problems a failing run prints, so that a helper wrong for every
#: errno does not print a page of them.
SHOWN = 20
#: The errnos a helper must raise back: every errno there is but the absent
#: ones, `EACCES`, `EPERM`, `EIO`, `EINVAL` and `ESTALE` among them, so that a
#: set widened after it is set (`_ABSENT_ERRNOS += (errno.ESTALE,)`) is
#: named whichever errno it adds (r1149's S1).
REFUSED_ERRNOS = tuple(sorted(
    name for code, name in errno.errorcode.items()
    if code not in {getattr(errno, absent) for absent in ABSENT_ERRNOS}))
#: Windows' "access denied" and "sharing violation", as it raises them: errno
#: `EACCES` with `winerror` set. A refusal as much as `EACCES` alone is.
REFUSED_WINERRORS = (5, 32)


def _stored(nodes: list) -> set[str]:
    """The names `nodes` bind in their own scope: assigned, deleted,
    defined, imported, or caught as (`except ... as`); not those a
    function, class, lambda or comprehension among them binds inside."""
    names, stack = set(), list(nodes)
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
            names.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update((alias.asname or alias.name).split(".")[0]
                         for alias in node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            names.add(node.name)
        if not isinstance(node, SCOPES):
            stack.extend(ast.iter_child_nodes(node))
    return names


def _reads(nodes: list) -> set[str]:
    """The names `nodes` read from the scope around them, annotations left
    out: a function's parameters and locals are its own, unless `global`."""
    names = set()
    for node in nodes:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.Lambda)):
            given = node.args
            body = node.body if isinstance(node.body, list) else [node.body]
            own = {arg.arg for arg in (*given.posonlyargs, *given.args,
                                       *given.kwonlyargs, given.vararg,
                                       given.kwarg) if arg}
            shared = {name for statement in body
                      for inner in ast.walk(statement)
                      if isinstance(inner, ast.Global)
                      for name in inner.names}
            names |= _reads(body) - ((own | _stored(body)) - shared)
            names |= _reads([*getattr(node, "decorator_list", []),
                             *given.defaults,
                             *(value for value in given.kw_defaults
                               if value is not None)])
        elif isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Load):
                names.add(node.id)
        else:
            names |= _reads([child for field, value in ast.iter_fields(node)
                             if field not in ("annotation", "returns")
                             for child in (value if isinstance(value, list)
                                           else [value])
                             if isinstance(child, ast.AST)])
    return names


def _slice(tree: ast.Module, helper: str) -> list[ast.stmt]:
    """The module's top-level statements that bind `helper`, or a name one
    of them reads, to any depth, in the module's own order: the `def`, any
    later binding of its name (`_is_a = _lenient`), the functions and
    classes it calls, its constants and every statement that changes one
    (`_ABSENT_ERRNOS += ...`), and the imports they need. No `__future__`
    import: `ANNOTATIONS` stands for it."""
    wanted, chosen = {helper}, set()
    grown = True
    while grown:
        grown = False
        for index, statement in enumerate(tree.body):
            if index not in chosen and _stored([statement]) & wanted:
                chosen.add(index)
                wanted |= _reads([statement])
                grown = True
    return [statement for index, statement in enumerate(tree.body)
            if index in chosen and not (isinstance(statement, ast.ImportFrom)
                                        and statement.module == "__future__")]


def loaded_helper(text: str, helper: str,
                  filename: str = "<helper>") -> Callable:
    """`helper` from the source `text`, loaded by its AST, as each of the
    twelve is: of the module, only `_slice` runs. No shipped tool is
    imported by its path, because none of the twelve is free of what its
    import does: each puts its own folder on `sys.path` and imports
    `repo_shape` and the like from there (`siblings.py` the holder's
    `bootstrap` too), and the copies of `repo_shape` in `scripts/` and in
    each template's `scripts/` would meet in `sys.modules`. Every import
    the slice makes is the standard library's, or it is refused: a helper
    keeps its own copy (#370, #610)."""
    statements = _slice(ast.parse(text), helper)
    if not statements:
        raise LookupError(f"nothing in the module binds `{helper}`")
    for node in (inner for outer in statements for inner in ast.walk(outer)):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for module in ([alias.name for alias in node.names]
                           if isinstance(node, ast.Import)
                           else [node.module or "." * node.level]):
                if module.split(".")[0] not in sys.stdlib_module_names:
                    raise LookupError(
                        f"`{helper}` needs `{module}`, which is no module "
                        "of the standard library: a helper keeps its own "
                        "copy of what it asks (#370, #610)")
    namespace = {"__name__": f"loaded {helper}", "__file__": filename}
    exec(compile(ast.Module(statements, type_ignores=[]), filename, "exec",
                 flags=ANNOTATIONS, dont_inherit=True), namespace)
    return namespace[helper]


def _refusing(real: Callable, asked: str, error: OSError,
              follows: bool = False) -> Callable:
    """`os.stat` or `os.lstat`, raising `error` for `asked` alone; with
    `follows`, only for a `stat` that follows a link, so that the link's own
    `lstat` answers (`os.lstat`, `Path.lstat`, `os.stat(...,
    follow_symlinks=False)`, which `Path.lstat` is on Python 3.12)."""
    def ask(path, *args, **kwargs):
        if (not isinstance(path, int) and os.fspath(path) == asked
                and (kwargs.get("follow_symlinks", True) or not follows)):
            raise error
        return real(path, *args, **kwargs)
    return ask


def _answer(asks: Callable, *args, **kwargs) -> tuple[str, object]:
    """`("answers", what it returned)` or `("raises", what it raised)`."""
    try:
        return "answers", asks(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 -- what it raises is its answer
        return "raises", exc


def _dangling_link(where: Path) -> Path | None:
    """A link in `where` to `nothing`, which `lstat` answers and `stat`
    cannot; None where this system makes no links."""
    link = where / f"{ASKED}-link"
    if not link.is_symlink():
        try:
            link.symlink_to(where / "nothing")
        except (OSError, NotImplementedError):
            return None
    return link


def behaviour_problems(text: str, helper: str, where: Path,
                       filename: str = "<helper>") -> list[str]:
    """What `helper`, loaded by `loaded_helper`, answers wrongly. Asked of
    a file, a folder and nothing, in the folder `where`, it must answer as
    the disk does. Asked, with `S_ISREG` and with `S_ISDIR`, of a name whose
    `stat` raises (`os.stat` and `os.lstat` refused for it, which `Path.stat`
    and `lstat` call): each absent errno, and each absent Windows error
    beside `EINVAL`, an errno that is not absent, must answer False; every
    other errno (`REFUSED_ERRNOS`), and EACCES with Windows' 5 and 32
    (`REFUSED_WINERRORS`), must come back raised, the very exception the
    `stat` raised. Each of them is asked again of a link to nothing, whose
    `stat` alone is refused and whose `lstat` answers a link: a helper that
    answers the refusal from that `lstat` is wrong (skipped where no link
    can be made). A keyword-only flag with a default (`link=False`) is asked
    both ways, the link only without it, for the flag may ask `lstat`."""
    try:
        asks = loaded_helper(text, helper, filename)
    except Exception as exc:  # noqa: BLE001 -- a module that cannot load
        return [f"`{helper}` cannot be loaded: {type(exc).__name__}: {exc}"]
    try:
        flags = [{}] + [{name: not parameter.default} for name, parameter
                        in inspect.signature(asks).parameters.items()
                        if parameter.kind is parameter.KEYWORD_ONLY
                        and isinstance(parameter.default, bool)]
    except (TypeError, ValueError):
        flags = [{}]
    (where / "a-file").write_text("", encoding="utf-8")
    link = _dangling_link(where)
    asked, problems = str(where / ASKED), []
    # `(errno name, winerror, whether it means nothing is there)`
    cases = ([(name, None, True) for name in sorted(ABSENT_ERRNOS)]
             + [("EINVAL", code, True) for code in sorted(ABSENT_WINERRORS)]
             + [(name, None, False) for name in REFUSED_ERRNOS]
             + [("EACCES", code, False) for code in REFUSED_WINERRORS])
    for flag in flags:
        called = f"`{helper}`" + "".join(f" with {name}={value}"
                                         for name, value in flag.items())
        for path, kind, want in (
                (where / "a-file", stat.S_ISREG, True),
                (where, stat.S_ISDIR, True),
                (where / "a-file", stat.S_ISDIR, False),
                (where / "nothing", stat.S_ISREG, False)):
            got = _answer(asks, path, kind, **flag)
            if got != ("answers", want):
                problems.append(f"{called} {got[0]} {got[1]!r} for "
                                f"{path.name}, {kind.__name__}, where the "
                                f"disk says {want}")
        # `(what is asked, the calls refused, only a following one, how
        # the problem names it)`
        targets = [(Path(asked), ("stat", "lstat"), False, "its `stat`")]
        if link is not None and not flag:
            targets.append((link, ("stat",), True,
                            "only the `stat` of a link"))
        for errno_name, winerror, absent in cases:
            code = getattr(errno, errno_name)
            error = OSError(code, os.strerror(code), asked)
            said = f"errno {errno_name}"
            if winerror is not None:
                error.winerror = winerror
                said += f" with winerror {winerror}"
            for path, refused, follows, what in targets:
                for kind in (stat.S_ISREG, stat.S_ISDIR):
                    with pytest.MonkeyPatch.context() as patch:
                        for name in refused:
                            patch.setattr(os, name, _refusing(
                                getattr(os, name), str(path), error, follows))
                        got = _answer(asks, path, kind, **flag)
                    asking = (f"{called} {got[0]} {got[1]!r} for "
                              f"{kind.__name__} where {what} raises {said}")
                    if absent and got != ("answers", False):
                        problems.append(f"{asking}: nothing is at the name, "
                                        "so the answer is False")
                    elif not absent and (got[0] != "raises"
                                         or got[1] is not error):
                        problems.append(
                            f"{asking}: the operating system refused it, so "
                            "that very exception comes back raised (#430)")
    return problems


def asked_problems(scanned: dict, where: Path) -> list[str]:
    """What the behaviour test says of every helper `_helpers` finds in
    `scanned`, the twelve and any added later (r1149's V18), each problem
    led by its file."""
    return [f"{file}: {problem}" for file, helper in _helpers(scanned)
            for problem in behaviour_problems(
                scanned[file][0], helper, where, str(REPO / file))]


def _shown(problems: list[str]) -> str:
    """The first `SHOWN` of `problems`, and how many more there are."""
    more = len(problems) - SHOWN
    return "\n".join(problems[:SHOWN]) + (f"\n... and {more} more"
                                         if more > 0 else "")


def test_every_stat_helper_answers_absent_false_and_raises_a_refusal(
        scanned, tmp_path):
    """r1111b's NIT 1: every helper found, the twelve and any added later,
    loaded by its AST (`loaded_helper`) and ASKED, with `S_ISREG` and with
    `S_ISDIR`, answers False to each absent errno and Windows error, raises
    every other errno back (EACCES with Windows' 5 and 32 among them), the
    same exception, also for a link whose `stat` alone is refused, and
    answers a file, a folder and nothing as the disk does. The parity test
    reads the sets; this asks them, so that a route its walk cannot see
    fails here: `or isinstance(exc, PermissionError)`, a dead `return
    False` before the `raise`, `_ABSENT_ERRNOS += (errno.EACCES,)` or any
    other errno, `exc.args[0] ==`, `exc.strerror ==`,
    `contextlib.suppress(PermissionError)`, a method or a lambda,
    `_is_a = _lenient`, a branch on the kind, or an answer from the link's
    own `lstat`."""
    assert set(HELPERS.items()) <= set(_helpers(scanned))
    problems = asked_problems(scanned, tmp_path)
    assert not problems, _shown(problems)


def test_a_long_list_of_problems_is_cut_and_counted():
    """A helper wrong for every errno gives hundreds of problems; a failing
    run prints the first `SHOWN` and says how many more there are."""
    assert _shown(["p"] * SHOWN) == "\n".join(["p"] * SHOWN)
    assert _shown(["p"] * (SHOWN + 3)) == (
        "\n".join(["p"] * SHOWN) + "\n... and 3 more")


def test_a_helper_added_later_is_asked_like_the_twelve(tmp_path):
    """r1149's V18: a file `HELPERS` does not name, with a helper in it, is
    asked all the same: a right one passes, a wrong one is named by its
    file, and only that one."""
    wrong = _changed(HELPER, [("        raise\n", "        return False\n")])
    scanned = {"a-tool.py": (HELPER, []), "new-tool.py": (wrong, [])}
    problems = asked_problems(scanned, tmp_path)
    assert problems
    assert all(problem.startswith("new-tool.py: `_is_a` answers False for ")
               for problem in problems), problems


#: r1111b's NIT 1: routes from a refused `stat` to False that the parity
#: test does not read, each made in the `HELPER`, and an error it shows;
#: and two the parity test does read, which this must name all the same.
ROUTES = {
    "winerror-dropped": ([('"winerror", None) in _ABSENT_WINERRORS)',
                           '"winerror", None) in (21, 123))')],
                         "EINVAL with winerror 1921"),
    "flag-branch": ([(IS_A, "def _is_a(path, kind, *, link=False):\n"),
                     ("        if _absent(exc):",
                      "        if link or _absent(exc):")], "EACCES"),
    "isinstance": ([("in _ABSENT_WINERRORS)", "in _ABSENT_WINERRORS\n"
                     "            or isinstance(exc, PermissionError))")],
                   "EACCES"),
    "dead-return": ([("        raise\n", "        return False\n"
                      "        raise\n")], "EIO"),
    "augmented-constant": ([("_ABSENT_WINERRORS = (21, 123, 1921)\n",
                             "_ABSENT_WINERRORS = (21, 123, 1921)\n"
                             "_ABSENT_ERRNOS += (errno.EACCES,)\n")],
                           "EACCES"),
    "args": ([("in _ABSENT_WINERRORS)", "in _ABSENT_WINERRORS\n"
               "            or exc.args[0] == errno.EIO)")], "EIO"),
    "strerror": ([("import errno\n", "import errno\nimport os\n"),
                  ("in _ABSENT_WINERRORS)", "in _ABSENT_WINERRORS\n"
                   "            or exc.strerror == "
                   "os.strerror(errno.EPERM))")], "EPERM"),
    "suppress": ([("import errno\n", "import contextlib\nimport errno\n"),
                  ("        raise\n", "        with contextlib.suppress("
                   "PermissionError):\n            raise\n"
                   "        return False\n")], "EPERM"),
    "method": ([("        if _absent(exc):",
                 "        if _absent(exc) or _POLICY.lenient(exc):"),
                (IS_A, "class _Policy:\n    def lenient(self, exc):\n"
                 "        return exc.errno == errno.EACCES\n\n"
                 "_POLICY = _Policy()\n\n" + IS_A)], "EACCES"),
    "lambda": ([("def _absent(exc):\n    return (",
                 "_lenient = lambda exc: exc.errno == errno.EPERM\n\n"
                 "def _absent(exc):\n    return _lenient(exc) or (")],
               "EPERM"),
    "rebound": ([(LAST + "    return kind(mode)\n",
                  LAST + "    return kind(mode)\n\ndef _lenient(path, kind):\n"
                  "    try:\n        return kind(path.stat().st_mode)\n"
                  "    except OSError:\n        return False\n\n"
                  "_is_a = _lenient\n")], "EIO"),
    "inverted": ([("        if _absent(exc):",
                   "        if not _absent(exc):")], "ENOENT"),
    # r1149's S1: a set widened after it is set, by any errno or by the
    # Windows errors of a refusal, which come with EACCES.
    "augmented-other-errno": ([("_ABSENT_WINERRORS = (21, 123, 1921)\n",
                                "_ABSENT_WINERRORS = (21, 123, 1921)\n"
                                "_ABSENT_ERRNOS += (errno.ESTALE,)\n")],
                              "ESTALE"),
    "augmented-einval": ([("_ABSENT_WINERRORS = (21, 123, 1921)\n",
                           "_ABSENT_WINERRORS = (21, 123, 1921)\n"
                           "_ABSENT_ERRNOS += (errno.EINVAL,)\n")], "EINVAL"),
    "winerror-5": ([("_ABSENT_WINERRORS = (21, 123, 1921)\n",
                     "_ABSENT_WINERRORS = (21, 123, 1921)\n"
                     "_ABSENT_WINERRORS += (5,)\n")],
                   "EACCES with winerror 5"),
    "winerror-32": ([("_ABSENT_WINERRORS = (21, 123, 1921)\n",
                      "_ABSENT_WINERRORS = (21, 123, 1921)\n"
                      "_ABSENT_WINERRORS += (32,)\n")],
                    "EACCES with winerror 32"),
    # r1149's S2: a refusal read as absent only for one kind, each.
    "kind-branch": ([("import errno\n", "import errno\nimport stat\n"),
                     ("        if _absent(exc):",
                      "        if _absent(exc) or (kind is stat.S_ISDIR\n"
                      "                            and isinstance(exc, "
                      "PermissionError)):")], "EACCES"),
    "kind-branch-file": ([("import errno\n", "import errno\nimport stat\n"),
                          ("        if _absent(exc):",
                           "        if _absent(exc) or (kind is stat.S_ISREG\n"
                           "                            and isinstance(exc, "
                           "PermissionError)):")], "EPERM"),
}

#: The routes made for one kind (r1149's S2), and the kind each is wrong for.
KIND_ROUTES = {"kind-branch": "S_ISDIR", "kind-branch-file": "S_ISREG"}

#: r1149's S2: routes only a link shows, whose `stat` alone is refused, so
#: that its `lstat` answers a link: the helper answers the refusal from
#: that `lstat`, however it asks for it, or reads a link to nothing as
#: there. Where the name is not there both raise, and these pass; each is
#: named for the link alone, by the errno it is wrong for.
FALLBACK = ("        raise\n",
            "        try:\n            mode = {}.st_mode\n"
            "        except FileNotFoundError:\n            raise exc\n")
LINK_ROUTES = {
    "os-lstat": ([("import errno\n", "import errno\nimport os\n"),
                  (FALLBACK[0], FALLBACK[1].format("os.lstat(path)"))],
                 "EACCES"),
    "path-lstat": ([(FALLBACK[0], FALLBACK[1].format("path.lstat()"))],
                   "EACCES"),
    "stat-no-follow": ([("import errno\n", "import errno\nimport os\n"),
                        (FALLBACK[0], FALLBACK[1].format(
                            "os.stat(path, follow_symlinks=False)"))],
                       "EACCES"),
    "link-is-there": ([("        if _absent(exc):\n            return False\n",
                        "        if _absent(exc):\n"
                        "            return path.is_symlink()\n")], "ENOENT"),
}


@pytest.mark.parametrize("route", ROUTES)
def test_the_behaviour_test_names_each_route_to_false(route, tmp_path):
    """The behaviour test's own proof: the `HELPER` answers as it should,
    and each route in `ROUTES` is named, by the errno it answers wrongly.
    A route made for one kind is named for that kind and no other."""
    assert behaviour_problems(HELPER, "_is_a", tmp_path) == []
    changes, said = ROUTES[route]
    problems = behaviour_problems(_changed(HELPER, changes), "_is_a",
                                  tmp_path)
    assert any(f"where its `stat` raises errno {said}:" in problem
               for problem in problems), problems
    if route in KIND_ROUTES:
        assert all(f"for {KIND_ROUTES[route]} where" in problem
                   for problem in problems), problems


def test_the_dangling_link_is_a_link_to_nothing(tmp_path):
    """r1149's S2: the link the behaviour test refuses the `stat` of is a
    link, which `lstat` answers, to a name nothing is at, which `stat`
    cannot. Links are made everywhere but on Windows without the right."""
    (tmp_path / "a-file").write_text("", encoding="utf-8")
    link = _dangling_link(tmp_path)
    if link is None and os.name == "nt":
        pytest.skip("no symlink here")
    assert link is not None
    assert stat.S_ISLNK(os.lstat(link).st_mode)
    with pytest.raises(FileNotFoundError):
        os.stat(link)
    assert _dangling_link(tmp_path) == link


@pytest.mark.parametrize("route", LINK_ROUTES)
def test_the_behaviour_test_names_a_wrong_answer_for_a_link_to_nothing(
        route, tmp_path):
    """r1149's S2 (its U3, G4 and G5): a helper that falls back to the
    link's own `lstat` where its `stat` is refused, or reads a link to
    nothing as there, is right for a name nothing is at and wrong for a
    link to nothing: named for the link, and for that alone."""
    if _dangling_link(tmp_path) is None:
        pytest.skip("no symlink here")
    assert behaviour_problems(HELPER, "_is_a", tmp_path) == []
    changes, said = LINK_ROUTES[route]
    problems = behaviour_problems(_changed(HELPER, changes), "_is_a",
                                  tmp_path)
    assert any(f"where only the `stat` of a link raises errno {said}:"
               in problem for problem in problems), problems
    assert all("where only the `stat` of a link raises" in problem
               for problem in problems), problems


@pytest.mark.parametrize("spelled", [
    "os.stat(path).st_mode", "os.stat(path, follow_symlinks=True).st_mode"])
def test_a_helper_that_stats_through_os_stat_is_right_for_a_link_too(
        spelled, tmp_path):
    """r1149's S2: the link's `stat` is refused only where it follows the
    link, as `os.stat` does with no argument or with `follow_symlinks=True`,
    so a helper that asks `os.stat` itself, and is right, passes."""
    assert behaviour_problems(_changed(HELPER, [
        ("import errno\n", "import errno\nimport os\n"),
        ("path.stat().st_mode", spelled)]), "_is_a", tmp_path) == []


def test_the_behaviour_test_asks_the_disk_too(tmp_path):
    """A helper whose `stat` is never refused but whose answer is the wrong
    way round is named by the disk's own answers; so is one right only for
    the names the test refuses (r1149's V16), by `nothing` alone."""
    assert behaviour_problems(_changed(HELPER, [(
        "    return kind(mode)\n", "    return not kind(mode)\n")]),
        "_is_a", tmp_path) == [
        "`_is_a` answers False for a-file, S_ISREG, where the disk says True",
        f"`_is_a` answers False for {tmp_path.name}, S_ISDIR, where the "
        "disk says True",
        "`_is_a` answers True for a-file, S_ISDIR, where the disk says False"]
    assert behaviour_problems(_changed(HELPER, [(
        "        if _absent(exc):\n            return False\n",
        "        if _absent(exc):\n"
        f"            return not path.name.startswith({ASKED!r})\n")]),
        "_is_a", tmp_path) == [
        "`_is_a` answers True for nothing, S_ISREG, where the disk says "
        "False"]


def test_the_behaviour_test_loads_only_what_the_helper_reads(tmp_path):
    """`loaded_helper` runs the statements the helper reads and no other:
    not a module's `sys.path.insert`, its sibling imports or its `main`;
    and a helper that needs a module outside the standard library is
    refused by name, as one that is not there is."""
    text = ("import sys\nsys.path.insert(0, 'nowhere')\n"
            "from repo_shape import load_yaml\n" + HELPER
            + "\nif __name__ == '__main__':\n    raise SystemExit(1)\n")
    before = list(sys.path)
    assert behaviour_problems(text, "_is_a", tmp_path) == []
    assert sys.path == before
    assert [type(node).__name__ for node in _slice(ast.parse(text), "_is_a")
            ] == ["Import", "Assign", "Assign", "FunctionDef", "FunctionDef"]
    needs = text.replace("def _absent(exc):\n",
                         "def _absent(exc):\n    load_yaml(exc)\n")
    refused = [
        "`_is_a` cannot be loaded: LookupError: `_is_a` needs `repo_shape`, "
        "which is no module of the standard library: a helper keeps its "
        "own copy of what it asks (#370, #610)"]
    assert behaviour_problems(needs, "_is_a", tmp_path) == refused
    # r1149's V19: `import x` is held to the same rule as `from x import`.
    plain = needs.replace("from repo_shape import load_yaml",
                          "import repo_shape").replace(
        "    load_yaml(exc)\n", "    repo_shape.load_yaml(exc)\n")
    assert behaviour_problems(plain, "_is_a", tmp_path) == refused
    assert behaviour_problems(text, "_is_b", tmp_path) == [
        "`_is_b` cannot be loaded: LookupError: nothing in the module "
        "binds `_is_b`"]


@pytest.mark.parametrize("module, kept", [
    ("COUNT = 0\n\ndef _is_a(path, kind):\n    global COUNT\n"
     "    COUNT = COUNT + 1\n    return kind(path)\n",
     ["COUNT = 0", "def _is_a(path, kind):"]),
    ("COUNT = 0\n\ndef _is_a(path, kind):\n    COUNT = 1\n"
     "    COUNT = COUNT + 1\n    return kind(path)\n",
     ["def _is_a(path, kind):"]),
], ids=["global", "local"])
def test_the_slice_reads_a_global_a_function_changes_and_not_a_local(
        module, kept):
    """r1149's V7: a function that changes a module name it declares
    `global` reads it, so its statement is kept; the same name made local
    is the function's own, and its statement is not."""
    assert [ast.unparse(node).splitlines()[0]
            for node in _slice(ast.parse(module), "_is_a")] == kept


# --- the site this slice fixed: the doctor's own manifest -------------------

MANIFEST = "schema_version: 1\nkind: project-manifest\nid: atlas\n"


@pytest.fixture
def doctor_module(monkeypatch):
    """This working tree's `shape-doctor.py`, loaded by path with no
    bytecode written beside it, and `sys.path` put back after."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    return load_without_bytecode(REPO / "shape-doctor.py",
                                 "doctor_path_guard_hygiene")


@pytest.mark.parametrize("code", [errno.EACCES, errno.EIO],
                         ids=["permission", "io-error"])
def test_a_manifest_whose_stat_is_refused_is_read_and_named(
        doctor_module, tmp_path, monkeypatch, code):
    """`project.yaml`'s `stat` refused, as for a link into a folder this
    user cannot search, with its read refused too, in process, so on every
    Python and as root: the root is the project its filename names, and the
    refusal `load_yaml` gives is kept for the `manifest` row, as for a
    `project.yaml` at mode 000 (#205). Before, `is_file()` answered as 3.14
    does: no manifest, NOT A SHAPE ROOT. An I/O error is refused as a
    permission is (r1111's X12)."""
    reason = os.strerror(code)
    error = (PermissionError if code == errno.EACCES else OSError)(
        code, reason)
    (tmp_path / "project.yaml").write_text(MANIFEST, encoding="utf-8")
    refused_stat(monkeypatch, "project.yaml")
    refusing(monkeypatch, "stat", "project.yaml", error)
    refusing(monkeypatch, "read_text", "project.yaml", error)

    ctx = doctor_module.Context(tmp_path)

    assert ctx.kind == doctor_module.PROJECT
    assert ctx.manifest_path == tmp_path / "project.yaml"
    assert ctx.manifest is None
    assert ctx.manifest_refusal.code == "yaml-unreadable"
    assert ctx.manifest_refusal.detail.endswith(
        f"project.yaml: cannot be read ({reason})")


@pytest.mark.parametrize("make", ["absent", "a-directory"])
def test_a_manifest_that_is_not_there_is_still_none(
        doctor_module, tmp_path, make):
    """The controls: nothing at the name, or a directory there, is no
    manifest, as it always was."""
    if make == "a-directory":
        (tmp_path / "project.yaml").mkdir()

    ctx = doctor_module.Context(tmp_path)

    assert ctx.kind == doctor_module.NOT_A_ROOT
    assert ctx.manifest_refusal is None


@CANNOT_RUN_AS_ROOT
def test_a_manifest_linked_into_a_folder_nobody_may_search_is_invalid(
        tmp_path):
    """The case as a person meets it: `project.yaml` a link into a folder
    at mode 000, the doctor run as a person runs it. It was a traceback,
    exit 1, on 3.12, and NOT A SHAPE ROOT, exit 2, with an `adopt-project.py
    plan` NEXT, on 3.14. Now the `manifest` row names it, INVALID, exit 1."""
    root, locked = tmp_path / "root", tmp_path / "locked"
    root.mkdir()
    locked.mkdir()
    (locked / "project.yaml").write_text(MANIFEST, encoding="utf-8")
    try:
        (root / "project.yaml").symlink_to(Path("..", "locked",
                                                "project.yaml"))
    except OSError as exc:
        pytest.skip(f"no symlink here: {exc}")
    locked.chmod(0)
    try:
        result = subprocess.run(
            [sys.executable, str(REPO / "shape-doctor.py"), "--root",
             str(root), "--json"],
            capture_output=True, text=True, encoding="utf-8", check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    finally:
        locked.chmod(0o755)
    assert "Traceback" not in result.stderr, result.stderr
    report = json.loads(result.stdout)
    rows = {row["id"]: row for row in report["rows"]}
    assert result.returncode == 1, result.stdout
    assert report["kind"] == "project"
    assert report["verdict"].startswith("INVALID (manifest")
    assert rows["manifest"]["status"] == "FINDING"
    assert rows["manifest"]["reason"].endswith(
        "project.yaml: cannot be read (Permission denied)")
