# SPDX-License-Identifier: Apache-2.0
"""rv1227c's scratch edge probes for PR #1227 (#1150). NOT FOR COMMIT.

Each probe builds a state, then records git's own answer, the gate's output
in every mode, with the head's script (the holder's own) and with main's
script (bd3e9c148, blob 172647b3e, run by `--root` from a copy outside the
holder), and each printed line typed in order with its exit code, to
`$RV1227C_OUT/<probe>.log`. Nothing here asserts the gate's behaviour: the
logs are read by hand.
"""

from __future__ import annotations

import os
import shlex
import shutil
from pathlib import Path

from conftest import run_script
from test_family import NAME, SPARE, family, validate  # noqa: F401
from test_family_add_refusals import holder, offline  # noqa: F401
from test_family_bootstrap_gate_order import cloned, hand_mounted
from test_family_head_lost_gitmodules import committed_gitmodules
from test_family_holder_remedies_compose import (
    MODES, OTHER_ROW, cloning, committed_with_its_checkout,
)
from test_family_member_path import raw
from test_family_unnamed_gitlink import section_taken_out_alone
from test_validate_family_index_gitmodules import head_bytes, valued
from test_validate_family_index_value_unmerged import unmerged
from test_validate_family_typed_states import ROW
from test_validate_family_unnamed_mounts import commands, findings

OUT = Path(os.environ.get("RV1227C_OUT", "/nonexistent-rv1227c"))
MAIN = Path(os.environ.get("RV1227C_MAIN", "/nonexistent-rv1227c-main"))
G = ".gitmodules"
BANG_TRUE = b"\tupdate = !true\n"
BANG_FALSE = b"\tupdate = !false\n"
BARE_UPDATE = b"\tupdate\n"
FRS_BAD = b"\tfetchRecurseSubmodules = sometimes\n"


def log(name: str, text: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / f"{name}.log", "a", encoding="utf-8") as fh:
        fh.write(text.rstrip("\n") + "\n")


def main_script(root: Path, tmp_path: Path) -> Path:
    where = tmp_path / "mainscripts"
    if not where.exists():
        where.mkdir()
        shutil.copy2(MAIN, where / "validate-family.py")
        shutil.copy2(root / "scripts" / "repo_shape.py",
                     where / "repo_shape.py")
    return where / "validate-family.py"


def gate_all(root: Path, name: str, tag: str, tmp_path: Path, modes=MODES,
             main: bool = True):
    last = None
    for extra in modes:
        result = validate(root, *extra)
        log(name, f"== gate HEAD-SCRIPT {tag} {list(extra)} "
            f"rc={result.returncode}\n-- stdout\n{result.stdout}"
            f"-- stderr\n{result.stderr}")
        last = result
    if main:
        script = main_script(root, tmp_path)
        for extra in modes:
            result = run_script(script, "--root", str(root), *extra,
                                cwd=root)
            log(name, f"== gate MAIN-SCRIPT {tag} {list(extra)} "
                f"rc={result.returncode}\n-- stdout\n{result.stdout}"
                f"-- stderr\n{result.stderr}")
    return last


def git_said(root: Path, env: dict, name: str, *args: str):
    result = raw(root, env, *args, check=False)
    log(name, f"== git {' '.join(args)} rc={result.returncode}\n"
        f"{result.stdout.decode(errors='replace')}"
        f"{result.stderr.decode(errors='replace')}")
    return result


def type_all(root: Path, env: dict, name: str, result,
             only_first: bool = False) -> None:
    for finding in findings(result):
        for line in commands(finding):
            if line.startswith("git "):
                argv = shlex.split(line)[1:]
                typed = raw(root, env, *argv, check=False)
                log(name, f"== typed {line!r} rc={typed.returncode} "
                    f"{typed.stdout.decode(errors='replace').strip()} "
                    f"{typed.stderr.decode(errors='replace').strip()}")
                if only_first:
                    return


def commit_plain(root: Path, env: dict, name: str) -> None:
    git_said(root, env, name, "commit", "-q", "-m", "What is staged")
    head = raw(root, env, "show", f"HEAD:{G}", check=False)
    log(name, f"== HEAD:.gitmodules rc={head.returncode}\n"
        f"{head.stdout.decode(errors='replace')}")
    git_said(root, env, name, "status", "--porcelain")


def plain_clone_update(root: Path, env: dict, family, tmp_path: Path,
                       name: str, tag: str) -> None:
    where = tmp_path / f"clone-{tag}"
    where.mkdir()
    clone = cloned(root, env, family, where, recurse=False)
    said = raw(clone, env, "submodule", "update", "--init", "--recursive",
               check=False)
    log(name, f"== plain clone of HEAD ({tag}): submodule update --init "
        f"--recursive rc={said.returncode}\n"
        f"{said.stderr.decode(errors='replace')}")


def versions(root: Path, env: dict, name: str) -> None:
    git_said(root, env, name, "--version")


# --- 1. a truly unnamed tools/x while unmerged -------------------------------

def unnamed_unmerged(family, holder, offline, tmp_path, left: str) -> None:
    name = f"p1-unnamed-tools-x-unmerged-{left}"
    env = cloning(offline, tmp_path, family)
    versions(holder, env, name)
    section_taken_out_alone(holder, env, family)
    data = head_bytes(holder, env)
    log(name, "== HEAD:.gitmodules\n" + data.decode())
    git_said(holder, env, name, "ls-files", "-s", "--", "tools/x")
    plain_clone_update(holder, env, family, tmp_path, name, "head")
    gate_all(holder, name, "before-unmerged", tmp_path)
    unmerged(holder, env, data, data, data)
    if left == "deleted":
        (holder / G).unlink()
    git_said(holder, env, name, "ls-files", "-s", "--", G)
    git_said(holder, env, name, "submodule", "status")
    result = gate_all(holder, name, "unmerged", tmp_path)
    type_all(holder, env, name, result)
    # Resolved as the merge's sides all are, HEAD's, and staged.
    (holder / G).write_bytes(data)
    git_said(holder, env, name, "add", "--", G)
    result = gate_all(holder, name, "resolved-and-staged", tmp_path,
                      main=False)
    type_all(holder, env, name, result)
    commit_plain(holder, env, name)
    gate_all(holder, name, "after-typed-and-commit", tmp_path, main=False)
    plain_clone_update(holder, env, family, tmp_path, name, "after")


def test_p1_unnamed_tools_x_unmerged_on_disk(family, holder, offline,
                                             tmp_path):
    unnamed_unmerged(family, holder, offline, tmp_path, "on-disk")


def test_p1_unnamed_tools_x_unmerged_deleted(family, holder, offline,
                                             tmp_path):
    unnamed_unmerged(family, holder, offline, tmp_path, "deleted")


# --- 2. S1 with three values -------------------------------------------------

def three(family, holder, offline, tmp_path, name, staged_edit, work_edit,
          commit_staged: bool = False) -> None:
    env = cloning(offline, tmp_path, family)
    data = head_bytes(holder, env)
    first = staged_edit(data)
    if commit_staged:
        committed_gitmodules(holder, env, first)
    else:
        (holder / G).write_bytes(first)
        git_said(holder, env, name, "add", "--", G)
    (holder / G).write_bytes(work_edit(first))
    log(name, "== work tree file\n" + (holder / G).read_text())
    log(name, "== index file\n" + raw(holder, env, "show", f":{G}").stdout
        .decode())
    result = gate_all(holder, name, "three-values", tmp_path)
    type_all(holder, env, name, result)
    commit_plain(holder, env, name)
    gate_all(holder, name, "after-typed-and-commit", tmp_path, main=False)
    log(name, f"== HEAD equals the start: {head_bytes(holder, env) == data}")


def test_p2a_staged_then_two_work_only(family, holder, offline, tmp_path):
    """IRRS `update = !true` staged; IRSS `update = !false` and
    `fetchRecurseSubmodules = sometimes` in the work tree alone."""
    three(family, holder, offline, tmp_path, "p2a-staged-then-two-work-only",
          lambda d: valued(d, ROW, BANG_TRUE),
          lambda d: valued(d, OTHER_ROW, BANG_FALSE + FRS_BAD))


def test_p2b_work_only_staged_work_only(family, holder, offline, tmp_path):
    """IRSS `update = !true` staged; IRRS `update = !false` (first in the
    file) and IRSS `fetchRecurseSubmodules = sometimes` in the work tree
    alone: work-only, staged, work-only, in the file's order."""
    three(family, holder, offline, tmp_path, "p2b-work-only-staged-work-only",
          lambda d: valued(d, OTHER_ROW, BANG_TRUE),
          lambda d: valued(valued(d, ROW, BANG_FALSE), OTHER_ROW, FRS_BAD))


def test_p2c_committed_then_two_work_only(family, holder, offline, tmp_path):
    """IRRS `update = !true` committed; IRSS's two values in the work tree
    alone."""
    three(family, holder, offline, tmp_path,
          "p2c-committed-then-two-work-only",
          lambda d: valued(d, ROW, BANG_TRUE),
          lambda d: valued(d, OTHER_ROW, BANG_FALSE + FRS_BAD),
          commit_staged=True)


def test_p2d_head_only_then_two_work_only(family, holder, offline, tmp_path):
    """IRRS `update = !true` committed, then taken out of the work tree's
    file by hand (not staged); IRSS's two values in the work tree alone:
    the head-only finding (`_value_not_here`) stages, and comes last."""
    name = "p2d-head-only-then-two-work-only"
    env = cloning(offline, tmp_path, family)
    data = head_bytes(holder, env)
    committed_gitmodules(holder, env, valued(data, ROW, BANG_TRUE))
    (holder / G).write_bytes(valued(data, OTHER_ROW, BANG_FALSE + FRS_BAD))
    result = gate_all(holder, name, "three-values", tmp_path)
    type_all(holder, env, name, result)
    commit_plain(holder, env, name)
    gate_all(holder, name, "after-typed-and-commit", tmp_path, main=False)
    log(name, f"== HEAD equals the start: {head_bytes(holder, env) == data}")


# --- 3. N4 with an index key that has no value -------------------------------

def index_other(family, holder, offline, tmp_path, name, index_line,
                work_line) -> None:
    env = cloning(offline, tmp_path, family)
    data = head_bytes(holder, env)
    (holder / G).write_bytes(valued(data, ROW, index_line))
    git_said(holder, env, name, "add", "--", G)
    (holder / G).write_bytes(valued(data, ROW, work_line))
    git_said(holder, env, name, "config", "--blob", f":{G}", "--list")
    git_said(holder, env, name, "submodule", "status")
    result = gate_all(holder, name, "differs", tmp_path)
    type_all(holder, env, name, result)
    commit_plain(holder, env, name)
    gate_all(holder, name, "after-typed-and-commit", tmp_path, main=False)
    log(name, f"== HEAD equals the start: {head_bytes(holder, env) == data}")


def test_p3a_index_key_with_no_value(family, holder, offline, tmp_path):
    """The index's file gives IRRS a bare `update` (no value), the work
    tree's `update = !true`; HEAD clean."""
    index_other(family, holder, offline, tmp_path,
                "p3a-index-bare-key-work-bang-true", BARE_UPDATE, BANG_TRUE)


def test_p3b_work_key_with_no_value(family, holder, offline, tmp_path):
    """The reverse: the index's file gives `update = !true`, the work
    tree's a bare `update`."""
    index_other(family, holder, offline, tmp_path,
                "p3b-index-bang-true-work-bare-key", BANG_TRUE, BARE_UPDATE)


def test_p3c_index_same_and_another(family, holder, offline, tmp_path):
    """The index's file gives `update = !true` then `update = !false`, the
    work tree's `update = !true` alone."""
    index_other(family, holder, offline, tmp_path,
                "p3c-index-two-values-work-one", BANG_TRUE + BANG_FALSE,
                BANG_TRUE)


# --- 4. member-gitlink-removal-staged while unmerged -------------------------

def removal_unmerged(family, holder, offline, tmp_path, left: str) -> None:
    name = f"p4-removal-staged-unmerged-{left}"
    env = cloning(offline, tmp_path, family)
    data = head_bytes(holder, env)
    theirs = valued(data, OTHER_ROW, b"\tbranch = theirs\n")
    hand = valued(data, OTHER_ROW, b"\tbranch = resolved-by-hand\n")
    unmerged(holder, env, data, data, theirs)
    if left == "deleted":
        (holder / G).unlink()
    elif left == "on-disk-hand-resolution":
        (holder / G).write_bytes(hand)
    elif left == "on-disk-without-irrs":
        # A hand resolution that drops IRRS's section, as a plain git rm
        # would have, had git let it.
        lines = hand.decode().splitlines(keepends=True)
        start = lines.index(f'[submodule "{ROW}"]\n')
        end = next(i for i in range(start + 1, len(lines))
                   if lines[i].startswith("["))
        (holder / G).write_text("".join(lines[:start] + lines[end:]))
    git_said(holder, env, name, "rm", "-q", "--cached", "--", ROW)
    git_said(holder, env, name, "ls-files", "-s", "--", G, ROW)
    if (holder / G).exists():
        log(name, "== work tree file before\n" + (holder / G).read_text())
    result = gate_all(holder, name, "unmerged-removal-staged", tmp_path)
    type_all(holder, env, name, result)
    git_said(holder, env, name, "ls-files", "-s", "--", G, ROW)
    if (holder / G).exists():
        log(name, "== work tree file after\n" + (holder / G).read_text())
    git_said(holder, env, name, "status", "--porcelain")
    git_said(holder, env, name, "diff", "HEAD", "--", G)
    gate_all(holder, name, "after-typed", tmp_path, main=False)


def test_p4_removal_staged_unmerged_deleted(family, holder, offline,
                                            tmp_path):
    removal_unmerged(family, holder, offline, tmp_path, "deleted")


def test_p4_removal_staged_unmerged_on_disk_hand(family, holder, offline,
                                                 tmp_path):
    removal_unmerged(family, holder, offline, tmp_path,
                     "on-disk-hand-resolution")


def test_p4_removal_staged_unmerged_on_disk_without_irrs(family, holder,
                                                         offline, tmp_path):
    removal_unmerged(family, holder, offline, tmp_path,
                     "on-disk-without-irrs")


# --- 5. `git switch -c` in a real merge with MERGE_HEAD ----------------------

def real_merge(holder, env, name, conflict: str) -> None:
    """A real `git merge` left in progress (MERGE_HEAD): a modify/delete
    conflict on .gitmodules (stages 1 and 2), a content conflict on a
    scratch file, or a clean merge stopped with --no-commit."""
    data = head_bytes(holder, env)
    git_said(holder, env, name, "switch", "-q", "-c", "side")
    if conflict == "gitmodules-modify-delete":
        git_said(holder, env, name, "rm", "-q", "--", G)
    elif conflict == "other-file":
        (holder / "scratch.txt").write_text("side\n")
        git_said(holder, env, name, "add", "--", "scratch.txt")
    else:
        (holder / "scratch2.txt").write_text("side\n")
        git_said(holder, env, name, "add", "--", "scratch2.txt")
    git_said(holder, env, name, "commit", "-q", "-m", "side")
    git_said(holder, env, name, "switch", "-q", "-")
    if conflict == "gitmodules-modify-delete":
        committed_gitmodules(holder, env,
                             valued(data, OTHER_ROW, b"\tbranch = ours\n"))
    elif conflict == "other-file":
        (holder / "scratch.txt").write_text("ours\n")
        git_said(holder, env, name, "add", "--", "scratch.txt")
        git_said(holder, env, name, "commit", "-q", "-m", "ours")
    if conflict == "clean-no-commit":
        git_said(holder, env, name, "merge", "--no-commit", "--no-ff",
                 "side")
    else:
        git_said(holder, env, name, "merge", "side")
    git_said(holder, env, name, "rev-parse", "--verify", "-q", "MERGE_HEAD")
    git_said(holder, env, name, "ls-files", "-u")


def switch_in_merge(family, holder, offline, tmp_path, conflict: str,
                    mount) -> None:
    name = f"p5-switch-c-in-a-real-merge-{conflict}-{mount.__name__}"
    env = cloning(offline, tmp_path, family)
    versions(holder, env, name)
    mount(holder, env, family)
    real_merge(holder, env, name, conflict)
    result = gate_all(holder, name, "in-merge", tmp_path)
    type_all(holder, env, name, result, only_first=False)
    git_said(holder, env, name, "branch", "--show-current")
    git_said(holder, env, name, "status", "--porcelain")


def test_p5_gitmodules_modify_delete_hand_mounted(family, holder, offline,
                                                  tmp_path):
    switch_in_merge(family, holder, offline, tmp_path,
                    "gitmodules-modify-delete", hand_mounted)


def test_p5_gitmodules_modify_delete_checkout(family, holder, offline,
                                              tmp_path):
    switch_in_merge(family, holder, offline, tmp_path,
                    "gitmodules-modify-delete", committed_with_its_checkout)


def test_p5_other_file_conflict_hand_mounted(family, holder, offline,
                                             tmp_path):
    switch_in_merge(family, holder, offline, tmp_path, "other-file",
                    hand_mounted)


def test_p5_clean_merge_no_commit_hand_mounted(family, holder, offline,
                                               tmp_path):
    switch_in_merge(family, holder, offline, tmp_path, "clean-no-commit",
                    hand_mounted)


# --- 6. a work-tree-only value beside a staged deletion of .gitmodules ------

def test_p6_work_only_value_with_the_deletion_staged(family, holder, offline,
                                                     tmp_path):
    """`git rm --cached .gitmodules` (the deletion staged), the work tree's
    file on disk giving IRRS `update = !true`, HEAD's clean: the M3 row's
    state, with the value in the work tree alone."""
    name = "p6-work-only-value-deletion-staged"
    env = cloning(offline, tmp_path, family)
    data = head_bytes(holder, env)
    git_said(holder, env, name, "rm", "-q", "--cached", "--", G)
    (holder / G).write_bytes(valued(data, ROW, BANG_TRUE))
    git_said(holder, env, name, "status", "--porcelain")
    result = gate_all(holder, name, "deletion-staged", tmp_path)
    type_all(holder, env, name, result)
    commit_plain(holder, env, name)
    gate_all(holder, name, "after-typed-and-commit", tmp_path, main=False)
    log(name, f"== HEAD equals the start: {head_bytes(holder, env) == data}")


# --- 7. the hand mount's reads while unmerged (the body's M2 claim) ---------

def test_p7_hand_clone_a_section_names_while_unmerged(family, holder, offline,
                                                      tmp_path):
    """IRQS cloned by hand into members/IRQS (.git a directory), then `git
    submodule add` of it (its section), committed; then .gitmodules
    unmerged at stages 1 to 3, the work tree's file on disk as HEAD's. The
    head's lines typed in the holder, main's in a copy."""
    from test_family_hand_mount_git_rm_lines import clone_a_section_names
    name = "p7-hand-clone-section-unmerged"
    env = cloning(offline, tmp_path, family)
    clone_a_section_names(holder, env, family)
    data = head_bytes(holder, env)
    unmerged(holder, env, data, data, data)
    copy = tmp_path / "main-copy" / NAME
    shutil.copytree(holder, copy, symlinks=True)
    head_result = gate_all(holder, name, "unmerged", tmp_path)
    main_result = run_script(main_script(holder, tmp_path), "--root",
                             str(copy), cwd=copy)
    log(name, "== HEAD-SCRIPT lines typed in the holder")
    type_all(holder, env, name, head_result)
    git_said(holder, env, name, "ls-files", "-s", "--", "members/IRQS", G)
    git_said(holder, env, name, "status", "--porcelain")
    log(name, f"== holder: members/IRQS/.git on disk: "
        f"{(holder / 'members' / 'IRQS' / '.git').exists()}")
    log(name, "== MAIN-SCRIPT lines typed in the copy\n" + main_result.stderr)
    type_all(copy, env, name, main_result)
    git_said(copy, env, name, "ls-files", "-s", "--", "members/IRQS", G)
    git_said(copy, env, name, "status", "--porcelain")
    log(name, f"== copy: members/IRQS/.git on disk: "
        f"{(copy / 'members' / 'IRQS' / '.git').exists()}")


# --- 2m. p2a's state under another script (a mutant), its lines typed -------

ALT = Path(os.environ.get("RV1227C_ALT", "/nonexistent-rv1227c-alt"))


def test_p2m_staged_then_two_work_only_under_alt(family, holder, offline,
                                                 tmp_path):
    """p2a's state; the script at $RV1227C_ALT (a mutant of the head's)
    gives the lines, which are typed in order, then a plain commit; the
    holder's own script then gates."""
    name = "p2m-staged-then-two-work-only-under-alt"
    env = cloning(offline, tmp_path, family)
    data = head_bytes(holder, env)
    first = valued(data, ROW, BANG_TRUE)
    (holder / G).write_bytes(first)
    git_said(holder, env, name, "add", "--", G)
    (holder / G).write_bytes(valued(first, OTHER_ROW, BANG_FALSE + FRS_BAD))
    where = tmp_path / "altscripts"
    where.mkdir()
    shutil.copy2(ALT, where / "validate-family.py")
    shutil.copy2(holder / "scripts" / "repo_shape.py", where / "repo_shape.py")
    alt = run_script(where / "validate-family.py", "--root", str(holder),
                     "--no-members", cwd=holder)
    log(name, f"== gate ALT-SCRIPT ['--no-members'] rc={alt.returncode}\n"
        f"{alt.stderr}")
    type_all(holder, env, name, alt)
    commit_plain(holder, env, name)
    gate_all(holder, name, "after-typed-and-commit", tmp_path, main=False)
    log(name, f"== HEAD equals the start: {head_bytes(holder, env) == data}")


def test_p6b_clean_with_the_deletion_staged(family, holder, offline,
                                            tmp_path):
    """`git rm --cached .gitmodules`, the work tree's file on disk and
    clean (HEAD's): does any check name the staged deletion?"""
    name = "p6b-clean-deletion-staged"
    env = cloning(offline, tmp_path, family)
    git_said(holder, env, name, "rm", "-q", "--cached", "--", G)
    git_said(holder, env, name, "status", "--porcelain")
    gate_all(holder, name, "deletion-staged", tmp_path)
    commit_plain(holder, env, name)
    gate_all(holder, name, "after-commit", tmp_path, main=False)


# --- 8. a committed value the index's file lacks, then a work-tree-only one -

ALT2 = Path(os.environ.get("RV1227C_ALT2", "/nonexistent-rv1227c-alt2"))


def committed_not_staged(family, holder, offline, tmp_path, name,
                         script: Path | None) -> None:
    """IRRS `update = !true` committed; the index's file then staged
    without it; the work tree's file giving IRRS `!true` again and IRSS
    `update = !false`: IRRS's finding is `committed` and not `staged`.
    `script` None types the holder's own lines, else that script's."""
    env = cloning(offline, tmp_path, family)
    data = head_bytes(holder, env)
    given = valued(data, ROW, BANG_TRUE)
    committed_gitmodules(holder, env, given)
    (holder / G).write_bytes(data)
    git_said(holder, env, name, "add", "--", G)
    (holder / G).write_bytes(valued(given, OTHER_ROW, BANG_FALSE))
    if script is None:
        result = validate(holder, "--no-members")
    else:
        where = tmp_path / "alt2scripts"
        where.mkdir()
        shutil.copy2(script, where / "validate-family.py")
        shutil.copy2(holder / "scripts" / "repo_shape.py",
                     where / "repo_shape.py")
        result = run_script(where / "validate-family.py", "--root",
                            str(holder), "--no-members", cwd=holder)
    log(name, f"== gate {'HOLDER' if script is None else 'ALT2'}-SCRIPT "
        f"['--no-members'] rc={result.returncode}\n{result.stderr}")
    type_all(holder, env, name, result)
    commit_plain(holder, env, name)
    gate_all(holder, name, "after-typed-and-commit", tmp_path, main=False)
    log(name, f"== HEAD equals the start: {head_bytes(holder, env) == data}")


def test_p8_committed_not_staged_then_work_only_head(family, holder, offline,
                                                     tmp_path):
    committed_not_staged(family, holder, offline, tmp_path,
                         "p8-committed-not-staged-head", None)


def test_p8_committed_not_staged_then_work_only_alt2(family, holder, offline,
                                                     tmp_path):
    committed_not_staged(family, holder, offline, tmp_path,
                         "p8-committed-not-staged-alt2", ALT2)
