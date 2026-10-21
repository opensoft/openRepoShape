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
    function makes it. That covers a call wrapped over lines, the module
    reached as `os.path`, `posixpath` and the like, through `import os as
    o`, `import os.path as p`, `from os import path` or `p = os.path`, a
    test imported from it by name, and a guard passed as a function; it
    does not cover a guard named by a string (`getattr`). One inside a stat
    helper fails too: the helper asks `stat` and nothing else. The failure
    names the file and line and says what to do.
  * `BENIGN` holds the sites the plan left out on purpose, each tagged with
    the plan's reason (`TAGS`). `KNOWN_OPEN` holds the real sites this slice
    found and did not fix, each with the follow-up that will. An entry that
    names no guard any more fails too, so neither list outlives its site.
  * THE PARITY TEST. Each helper's absent errnos and Windows errors are read
    out of the AST, through the module constants and the functions it calls,
    and must be the one set above. On that path a helper may catch only
    `OSError` and `ValueError`, its `except OSError` must hold a bare
    `raise`, and `errno` and `winerror` may be read only as `in <set>`. A
    class or an `async def` by a helper's name is refused.

ONE SITE THIS SLICE FIXED: `shape-doctor.py`'s `Context.__init__`, where a
`project.yaml` that is a link into a folder this user cannot search was a
`PermissionError` traceback on 3.12 and NOT A SHAPE ROOT on 3.14, with
`adopt-project.py plan` as the NEXT for a project. It is now the `manifest`
row's `yaml-unreadable`, as a `project.yaml` at mode 000 already was. The
tests at the end hold that.
"""

from __future__ import annotations

import ast
import errno
import json
import os
import re
import subprocess
import sys
from collections import Counter
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
#: helper found (these, and any added later) is held to the one set.
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
#: "leave the follow-ups out of v1.2.0").
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
        "OWN", "not the disk: `_CloneGit`, the run's own model in memory of "
        "the names git makes in the clone's `.git` (#904), a set lookup "
        "with no `stat` in it"),
    (AP, "_PlannedRoot._no_directory", "self._git().is_dir(here)"): (
        "OWN", "the same model of the clone's `.git`, not the disk"),
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
    (SD, "unregistered_gitlinks",
     "os.path.lexists(mount / adopt.GITMODULES)"): (
        "ASKED", "a leg git listed the index of first, by `lstat` (#1093)"),
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


def _os_path_names(tree: ast.Module) -> tuple[set[str], set[str]]:
    """`(each expression the os.path module is reached through, each name
    bound to one of its tests)`. The module: `os.path`, `posixpath`,
    `ntpath` and `genericpath` as written, `o.path` after `import os as o`,
    `p` after `import os.path as p`, `from os import path [as p]` or `p =
    os.path` (to any depth of such names). The tests: `from os.path import
    exists [as e]`. Not caught, and in no shipped tool today: a guard asked
    by its name as a string (`getattr`, `operator.methodcaller`), and the
    other questions of the same kind (`ismount`, `is_fifo`, `os.access`
    with `F_OK`, a hand-written `stat` whose `OSError` is False)."""
    modules = set(OS_PATH_MODULES)
    tests: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os" and alias.asname:
                    modules.add(f"{alias.asname}.path")
                elif alias.name in OS_PATH_MODULES and alias.asname:
                    modules.add(alias.asname)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            for alias in node.names:
                if node.module == "os" and alias.name == "path":
                    modules.add(alias.asname or "path")
                elif (node.module in OS_PATH_MODULES
                      and alias.name in OS_PATH_GUARDS):
                    tests.add(alias.asname or alias.name)
    bound = [(node.targets if isinstance(node, ast.Assign)
              else [node.target], node.value)
             for node in ast.walk(tree)
             if isinstance(node, (ast.Assign, ast.AnnAssign))
             and node.value is not None]
    grown = True
    while grown:
        grown = False
        for targets, value in bound:
            if _dotted(value) not in modules:
                continue
            for target in targets:
                if isinstance(target, ast.Name) and target.id not in modules:
                    modules.add(target.id)
                    grown = True
    return modules, tests


def guards_in(text: str, file: str) -> list[Site]:
    """Every bare guard in the source `text`: a call, or a reference passed
    as a function, with the function and class it is in."""
    tree = ast.parse(text)
    modules, tests = _os_path_names(tree)
    calls = {id(node.func): node for node in ast.walk(tree)
             if isinstance(node, ast.Call)}

    def is_guard(node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            return node.id in tests and isinstance(node.ctx, ast.Load)
        if not isinstance(node, ast.Attribute):
            return False
        if node.attr in GUARD_METHODS:
            return True
        return node.attr in OS_PATH_GUARDS and _dotted(node.value) in modules

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


def test_every_allowlist_entry_is_tagged_and_reasoned():
    """Each BENIGN entry carries one of the plan's reasons (`TAGS`) and a
    line of its own, and each KNOWN_OPEN entry the follow-up that owns it.
    No site is on both, and none is in a stat helper."""
    assert not set(BENIGN) & set(KNOWN_OPEN)
    for key, (tag, reason, count) in BENIGN.items():
        assert tag in TAGS, key
        assert reason.strip() and count >= 1, key
    for key, (owner, reason, count) in KNOWN_OPEN.items():
        assert owner == FOLLOW_UP, key
        assert reason.strip() and count >= 1, key
    for file, scope, said in {**BENIGN, **KNOWN_OPEN}:
        assert not in_a_helper(Site(file, 0, scope, said)), (file, scope)


#: Each way a guard can be written, and the key the scan gives it.
SPELLINGS = '''
import os
import os as system
import os.path as osp
from os import path as ospath
from os.path import lexists, isdir as is_directory
from pathlib import Path
held = os.path
again = held

def _is_a(path, kind):
    return path.is_file()

def asks(here: Path):
    here.is_file(); here.is_dir(); here.exists(); here.is_symlink()
    os.path.isfile(here); os.path.isdir(here); os.path.exists(here)
    os.path.lexists(here); os.path.islink(here)
    osp.exists(here); ospath.isfile(here); lexists(here)
    is_directory(here); system.path.isfile(here); again.islink(here)
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
    `_is_a` is refused as a guard in the helper (r1111's X4)."""
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
        ("asks", "again.islink(here)"), ("asks", "os.path.exists"),
        ("asks", "Path.is_dir"),
        ("Holder.method", '(self.root / "x").exists()'),
    ]
    messages = unlisted(sites, has_helper=True)
    assert len(messages) == len(sites) == 19
    assert messages[0] == (
        "spellings.py:12, in `_is_a`: `path.is_file()` is a bare guard "
        "inside the stat helper itself. The helper must ask `stat` and "
        "nothing else: a guard there answers as Python 3.14 does, False to "
        "any OSError, for every caller (#430).")
    assert messages[1].startswith("spellings.py:15, in `asks`: "
                                  "`here.is_file()` is a bare guard.")
    assert "this file's own `_is_a(" in messages[1]
    assert "a local `_is_a`, copied from validate-pins.py's" in unlisted(
        sites, has_helper=False)[1]


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

#: The handlers a helper may hold: `OSError`, which re-raises what is not
#: absent, and `ValueError`, a name no system can take (a NUL in it).
HANDLERS = frozenset({"OSError", "ValueError"})


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


def _members(expr: ast.expr, constants: dict) -> frozenset:
    """The values of a set the helper compares with: a module constant or a
    literal, each element `errno.<NAME>` (by name) or a number. Anything
    else is refused, rather than guessed at."""
    if isinstance(expr, ast.Name):
        if expr.id not in constants:
            raise LookupError(f"`{expr.id}` is no constant of the module")
        expr = constants[expr.id]
    if not isinstance(expr, (ast.Tuple, ast.List, ast.Set)):
        raise ValueError(f"`{ast.dump(expr)}` is no literal set")
    members = set()
    for element in expr.elts:
        if (isinstance(element, ast.Attribute)
                and isinstance(element.value, ast.Name)
                and element.value.id == "errno"):
            members.add(element.attr)
        elif isinstance(element, ast.Constant) and type(element.value) is int:
            members.add(element.value)
        else:
            raise ValueError(f"`{ast.dump(element)}` is neither "
                             "`errno.<NAME>` nor a number")
    return frozenset(members)


def _caught(handler: ast.ExceptHandler) -> list[str]:
    """What an `except` names, `except:` as `BaseException`."""
    if handler.type is None:
        return ["BaseException"]
    names = (handler.type.elts if isinstance(handler.type, ast.Tuple)
             else [handler.type])
    return [_dotted(name) or ast.dump(name) for name in names]


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


def absent_sets(text: str, helper: str) -> AbsentSets:
    """The helper's sets, read through every function of the module it
    calls (`_absent`, `_mode_of`, `_says_absent`, `refused_read`): each
    `<exc>.errno in <set>` and `getattr(<exc>, "winerror", None) in <set>`.

    `refused` names, on that path (r1111's S1): a handler for anything but
    `OSError` and `ValueError` (`PermissionError`, `Exception`, `except:`),
    which would answer before the set is asked; an `except OSError` with no
    bare `raise` in it; and an `errno` or `winerror` read any other way
    than `in <set>` (`== errno.EACCES`), which would put another errno
    beside the set."""
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
    constants = _constants(tree)
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
            if isinstance(node, ast.ExceptHandler):
                caught = _caught(node)
                if not set(caught) <= HANDLERS:
                    refused.append(f"`{name}` catches "
                                   f"{', '.join(caught)}, which answers "
                                   "before the set is asked")
                elif "OSError" in caught and not any(
                        isinstance(inner, ast.Raise) and inner.exc is None
                        for inner in ast.walk(node)):
                    refused.append(f"`{name}`'s `except OSError` does not "
                                   "re-raise what is not absent")
            if not (isinstance(node, ast.Compare) and len(node.ops) == 1
                    and isinstance(node.ops[0], ast.In)):
                continue
            kind = _asked(node.left)
            if kind is None or _asked(node.comparators[0]) is not None:
                continue
            approved.add(id(node.left))
            (errnos if kind == "errno" else winerrors).append(
                _members(node.comparators[0], constants))
        refused += [f"`{name}` reads "
                    f"`{ast.get_source_segment(text, node)}` other than "
                    "as `in <set>`"
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
    1921, as absent, asks `errno` and `winerror` only as `in` those sets,
    catches nothing but `OSError` and `ValueError` on the way, and re-raises
    in its `except OSError`."""
    problems = [f"{file}'s `{helper}`: {problem}"
                for file, helper in _helpers(scanned)
                for problem in parity_problems(scanned[file][0], helper)]
    assert not problems, "\n".join(problems)


def test_every_absent_constant_is_the_one_set(scanned):
    """Each module constant named `*ABSENT_ERRNOS` or `*ABSENT_WINERRORS`
    is the one set, where a helper reads it or not (`validate-pins.py`'s
    `_digest_from_source` reads `_ABSENT_ERRNOS` inline)."""
    wrong, seen = [], 0
    for file, (text, _) in scanned.items():
        for name, value in _constants(ast.parse(text)).items():
            expected = (ABSENT_ERRNOS if name.endswith("ABSENT_ERRNOS")
                        else ABSENT_WINERRORS
                        if name.endswith("ABSENT_WINERRORS") else None)
            if expected is None:
                continue
            seen += 1
            if _members(value, {}) != expected:
                wrong.append(f"{file}: {name}")
    assert seen >= 2 * len(HELPERS), seen
    assert not wrong, wrong


#: A helper as slice A wrote it, and the variants the parity test refuses.
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
     "`_absent` reads `exc.errno` other than as `in <set>`"),
    (("def _is_a(path, kind):", "async def _is_a(path, kind):"),
     "its sets cannot be read: `_is_a` is an async def, not a plain "
     "function"),
    (("def _is_a(path, kind):",
      "class _is_a:\n    pass\n\ndef _is_b(path, kind):"),
     "its sets cannot be read: `_is_a` is a class, not a plain function"),
])
def test_the_parity_test_refuses_another_set(change, said):
    """The parity test's own proof: slice A's helper passes, and each
    one-line change to its set, its handlers, its `errno` question or its
    kind is named (r1111's X5, X6, X15 and X18 among them)."""
    assert parity_problems(HELPER, "_is_a") == []
    old, new = change
    assert HELPER.count(old) == 1
    assert said in parity_problems(HELPER.replace(old, new), "_is_a")


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
