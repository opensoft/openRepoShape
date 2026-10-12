# SPDX-License-Identifier: Apache-2.0
"""A root in the middle of a merge is not COMPLIANT (#424).

THE DEFECT. Nothing in `shape-doctor.py` asked git whether the root's index
held an unmerged path. The validators read the working tree, and
`recorded_gitlink` answers a gitlink a conflicted merge holds only at stages
1, 2 and 3 from HEAD. So the merge of two `bump-leg.py` branches read
`DRIFTED (1 leg(s) not at the pin)` while the conflict markers sat in the
pin, and `COMPLIANT`, exit 0, once `git checkout --ours` had taken them out:
`UU` still on the pin and on the gitlink, `MERGE_HEAD` still there, and `git
commit` refusing. A conflicted file no row reads was `COMPLIANT` from the
start, and so was the same conflict left by a cherry-pick.

WHAT IT DOES NOW. A `merge` row, first on both kinds of root, is a FINDING
naming the unmerged paths, with `git -C <root> status` as its NEXT, and the
verdict is `INVALID (merge)`, exit 1, above every other rung but CANNOT
ANSWER. A merge with nothing left unmerged is a `note`, and the verdict steps
over it. A root with neither gets no row at all, which
`test_every_row_of_a_compliant_project_is_ok_or_na` and
`test_a_family_holder_gets_the_family_rows` in `tests/test_shape_doctor.py`
already hold for a clean root of each kind.

The fixtures are `tests/test_shape_doctor.py`'s, imported rather than rebuilt
(the precedent is `tests/test_doctor_legs_members_next.py`). Every merge is a
real `git merge`, every bump a real `bump-leg.py`, and the remotes a test
pushes to are its own copy, so no other test sees what it pushed.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess

from pathlib import Path

import pytest

from conftest import FILE_PROTOCOL, git, run_script
from test_shape_doctor import (  # noqa: F401
    FAMILY_NAME, PROJECT, doctor, doctor_module, holder, powershell_tokens,
    project, rows_of, scaffolded_here, standard, verdict_line,
)

SPEC_PIN = "contracts/spec-pin.yaml"


# --- helpers ----------------------------------------------------------------

def pasted(line: str) -> list[str]:
    """The argv the reader's own shell makes of a printed NEXT."""
    return powershell_tokens(line) if os.name == "nt" else shlex.split(line)


def merge(root: Path, *args: str) -> subprocess.CompletedProcess:
    """`git merge`, which exits non-zero when it leaves a conflict."""
    return git("merge", "--no-edit", *args, cwd=root, check=False)


def unmerged_index(root: Path) -> str:
    return git("ls-files", "-u", cwd=root).stdout


def what_git_holds(root: Path) -> tuple:
    """The index's every stage and the merge git records, read-only, so a
    test can say the doctor left the merge exactly as it found it."""
    merge_head = Path(git("rev-parse", "--git-path", "MERGE_HEAD",
                          cwd=root).stdout.strip())
    if not merge_head.is_absolute():
        merge_head = root / merge_head
    return (git("ls-files", "--stage", cwd=root).stdout,
            merge_head.read_bytes() if merge_head.is_file() else None)


def assert_invalid_for_the_merge(standard: Path, root: Path,
                                 paths: list[str], merging: bool) -> dict:
    """The verdict, the row and its NEXT for a root left unmerged; the row.

    The NEXT is pasted and run: `git status` exits 0 in a merge, and the
    doctor leaves the index and `MERGE_HEAD` as it found them.
    """
    before = what_git_holds(root)
    result = doctor(standard, root, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "INVALID (merge)", payload["verdict"]
    assert payload["exit"] == 1
    row = rows_of(result)["merge"]
    assert payload["rows"][0]["id"] == "merge", "the merge row reads first"
    assert row["status"] == "FINDING", row
    assert row["detail"] == {"unmerged": paths, "count": len(paths),
                             "merge_head": merging}, row["detail"]
    assert f"{len(paths)} path(s) unmerged in the index" in row["reason"]
    for path in paths:
        assert path in row["reason"], (path, row["reason"])
    said = ("finish it (`git add` each path, then `git commit`) or abandon "
            "it (`git merge --abort`)")
    assert (said in row["reason"]) is merging, row["reason"]
    argv = pasted(row["next"])
    assert argv[:2] == ["git", "-C"] and argv[3:] == ["status"], row["next"]
    assert Path(argv[2]).resolve() == root.resolve(), argv
    status = subprocess.run(argv, capture_output=True, check=False)
    assert status.returncode == 0, status.stderr
    assert what_git_holds(root) == before, "the doctor moved the merge"
    plain = doctor(standard, root)
    assert plain.returncode == 1, plain.stdout + plain.stderr
    assert verdict_line(plain).startswith("INVALID (merge)   (exit 1)"), \
        plain.stdout
    return row


def assert_compliant_with_no_merge_row(standard: Path, root: Path) -> None:
    result = doctor(standard, root, "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == "COMPLIANT"
    assert "merge" not in rows_of(result), rows_of(result)["merge"]


def spec_commits_on_branches(remotes: Path, tmp_path: Path) -> tuple:
    """Two commits on the spec leg's remote, siblings of its pin, each on a
    branch of its own, so a merge of two bumps conflicts on the gitlink."""
    work = tmp_path / "spec-work"
    git(*FILE_PROTOCOL, "clone", "-q", str(remotes / f"{PROJECT}-spec.git"),
        str(work), cwd=tmp_path)
    base = git("rev-parse", "HEAD", cwd=work).stdout.strip()
    made = []
    for side in ("a", "b"):
        git("checkout", "-q", "-b", f"side-{side}", base, cwd=work)
        (work / "specs").mkdir(exist_ok=True)
        (work / "specs" / f"{side}.md").write_bytes(f"# {side}\n".encode())
        git("add", "--", f"specs/{side}.md", cwd=work)
        git("commit", "-q", "-m", f"spec side {side}", cwd=work)
        made.append(git("rev-parse", "HEAD", cwd=work).stdout.strip())
    git("push", "-q", "origin", "side-a", "side-b", cwd=work)
    return made[0], made[1]


def bump_on(standard: Path, root: Path, remotes: Path, branch: str,
            to: str) -> None:
    """`branch`, cut from `main`, with the spec leg bumped `to` a commit by
    the standard's own `bump-leg.py`."""
    git("checkout", "-q", "-b", branch, "main", cwd=root)
    git(*FILE_PROTOCOL, "submodule", "update", "-q", cwd=root)
    bumped = run_script(standard / "scripts" / "bump-leg.py", "--root",
                        str(root), "--leg", "spec", "--to", to,
                        "--local-remote-dir", str(remotes))
    assert bumped.returncode == 0, bumped.stdout + bumped.stderr


# --- the issue's merge ------------------------------------------------------

def test_two_leg_bumps_merged_are_invalid_until_the_merge_is_committed(
        standard, project, scaffolded_here, tmp_path):
    """The issue's reproduction, end to end.

    `bump/a` and `bump/b` each move the spec leg, to sibling commits, and
    `bump/b` is merged into `bump/a`: the pin and the gitlink are both
    `UU`. Main read that `DRIFTED (1 leg(s) not at the pin)`, about a leg
    that had not moved, and `COMPLIANT`, exit 0, once `checkout --ours` had
    taken the markers out of the pin. Both are `INVALID (merge)` now, and
    once the merge is committed the root is `COMPLIANT` with no merge row.
    """
    remotes = tmp_path / "remotes"
    shutil.copytree(scaffolded_here["base"] / "remotes", remotes,
                    symlinks=True)
    new1, new2 = spec_commits_on_branches(remotes, tmp_path)
    bump_on(standard, project, remotes, "bump/b", new2)
    bump_on(standard, project, remotes, "bump/a", new1)
    git(*FILE_PROTOCOL, "submodule", "update", "-q", cwd=project)
    assert_compliant_with_no_merge_row(standard, project)
    merged = merge(project, "bump/b")
    assert merged.returncode != 0, merged.stdout + merged.stderr
    status = git("status", "--porcelain=v1", cwd=project).stdout
    assert f"UU {SPEC_PIN}" in status and "UU spec" in status, status
    assert b"<<<<<<<" in (project / SPEC_PIN).read_bytes()

    assert_invalid_for_the_merge(standard, project, [SPEC_PIN, "spec"],
                                 merging=True)

    git("checkout", "--ours", "--", SPEC_PIN, cwd=project)
    assert b"<<<<<<<" not in (project / SPEC_PIN).read_bytes()
    assert f"UU {SPEC_PIN}" in git("status", "--porcelain=v1",
                                   cwd=project).stdout
    assert_invalid_for_the_merge(standard, project, [SPEC_PIN, "spec"],
                                 merging=True)
    # The defect, said by the rows: with the markers gone every other row is
    # green, so the merge row is the only thing between this root and
    # COMPLIANT.
    rows = rows_of(doctor(standard, project, "--json"))
    assert [name for name, row in rows.items()
            if row["status"] == "FINDING"] == ["merge"], rows

    # Finished as one side, and committed: the merge row goes.
    git("add", "--", SPEC_PIN, cwd=project)
    git("update-index", "--cacheinfo", f"160000,{new1},spec", cwd=project)
    git("commit", "-q", "--no-edit", cwd=project)
    assert unmerged_index(project) == ""
    assert_compliant_with_no_merge_row(standard, project)


def own_file_conflicted(root: Path, operation: str) -> None:
    """`NOTES.md`, a file no row reads, left conflicted by `operation`: a
    `merge` (git writes `MERGE_HEAD`) or a `cherry-pick` (it does not)."""
    base = git("rev-parse", "HEAD", cwd=root).stdout.strip()
    for side in ("one", "two"):
        git("checkout", "-q", "-b", f"notes-{side}", base, cwd=root)
        (root / "NOTES.md").write_bytes(f"{side}\n".encode())
        git("add", "--", "NOTES.md", cwd=root)
        git("commit", "-q", "-m", f"notes {side}", cwd=root)
    if operation == "merge":
        done = merge(root, "notes-one")
    else:
        done = git("cherry-pick", "notes-one", cwd=root, check=False)
    assert done.returncode != 0, done.stdout + done.stderr
    assert "AA NOTES.md" in git("status", "--porcelain=v1",
                                cwd=root).stdout


def test_a_merge_left_conflicted_in_a_file_no_row_reads_is_invalid(
        standard, project):
    """`AA NOTES.md`: main was `COMPLIANT`, exit 0, before `checkout --ours`
    and after it. Abandoned, the root is `COMPLIANT` again."""
    own_file_conflicted(project, "merge")
    assert_invalid_for_the_merge(standard, project, ["NOTES.md"],
                                 merging=True)
    git("checkout", "--ours", "--", "NOTES.md", cwd=project)
    assert_invalid_for_the_merge(standard, project, ["NOTES.md"],
                                 merging=True)
    git("merge", "--abort", cwd=project)
    assert_compliant_with_no_merge_row(standard, project)


def test_a_cherry_pick_left_conflicted_is_invalid_and_sends_to_git_status(
        standard, project):
    """No `MERGE_HEAD`, and `git commit` refuses all the same. The row does
    not tell a cherry-pick to `git merge --abort`: `git status` says how to
    resolve each path and how to finish or abandon the cherry-pick."""
    own_file_conflicted(project, "cherry-pick")
    row = assert_invalid_for_the_merge(standard, project, ["NOTES.md"],
                                       merging=False)
    assert "merge --abort" not in row["reason"], row["reason"]
    assert ("`git status` says how to resolve each, and how to finish or "
            "abandon what left them") in row["reason"], row["reason"]


def test_a_merge_with_nothing_unmerged_is_a_note_and_stays_compliant(
        standard, project):
    """`git merge --no-commit`: `MERGE_HEAD` and nothing unmerged. Git
    commits it as it stands, so nothing asserts a fault: a `note`, no NEXT,
    and the verdict steps over it."""
    git("checkout", "-q", "-b", "plain", cwd=project)
    (project / "X.md").write_bytes(b"x\n")
    git("add", "--", "X.md", cwd=project)
    git("commit", "-q", "-m", "x", cwd=project)
    git("checkout", "-q", "main", cwd=project)
    merged = merge(project, "--no-commit", "--no-ff", "plain")
    assert merged.returncode == 0, merged.stdout + merged.stderr
    assert unmerged_index(project) == ""
    result = doctor(standard, project, "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == "COMPLIANT"
    row = rows_of(result)["merge"]
    assert row["status"] == "note", row
    assert row["next"] is None, row
    assert row["detail"] == {"unmerged": [], "count": 0,
                             "merge_head": True}, row["detail"]
    assert "nothing in it is unmerged" in row["reason"], row["reason"]


def test_a_family_holder_in_the_middle_of_a_merge_is_invalid_too(
        standard, holder, tmp_path):
    """The row is registered for both kinds of root, and answers alike."""
    root = tmp_path / FAMILY_NAME
    shutil.copytree(holder["root"], root, symlinks=True)
    assert_compliant_with_no_merge_row(standard, root)
    own_file_conflicted(root, "merge")
    assert_invalid_for_the_merge(standard, root, ["NOTES.md"], merging=True)
    result = doctor(standard, root, "--json")
    assert json.loads(result.stdout)["kind"] == "family"


# --- what the row says, read in process -------------------------------------

def unmerged_in_the_index(root: Path, names: list[bytes]) -> bool:
    """Each of `names` at stages 1, 2 and 3 of `root`'s index, as a
    conflicted merge leaves a path, written straight in (`update-index -z
    --index-info`, bytes in) and never on the disk, so no file system has to
    hold a name. `core.protectNTFS` is off, as in `test_adopt_entry_paths.py`:
    on Windows it refuses a control character in a name the index holds all
    the same. False where git will not record a name, which only git can
    say."""
    blob = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                          cwd=str(root), input=b"x\n", capture_output=True,
                          check=True).stdout.decode("ascii").strip()
    records = b"".join(f"100644 {blob} {stage}\t".encode() + name + b"\0"
                       for name in names for stage in (1, 2, 3))
    written = subprocess.run(["git", "-c", "core.protectNTFS=false",
                              "update-index", "-z", "--index-info"],
                             cwd=str(root), input=records,
                             capture_output=True, check=False)
    held = subprocess.run(["git", "ls-files", "-u", "-z"], cwd=str(root),
                          capture_output=True, check=True).stdout
    return written.returncode == 0 and all(
        b"\t" + name + b"\0" in held for name in names)


def merge_row(standard: Path, root: Path):
    module = doctor_module(standard)
    return module, module.check_merge(module.Context(root.resolve()))


def test_the_row_names_five_paths_then_counts_the_rest(standard, project):
    """Seven paths unmerged and no operation git records: five named, then
    `and 2 more`, each once however many stages it holds, and every one in
    `detail`. The verdict is the merge's."""
    names = [f"{letter}.md".encode() for letter in "abcdefg"]
    assert unmerged_in_the_index(project, names)
    module, row = merge_row(standard, project)
    spelled = [name.decode() for name in names]
    assert row.status == module.FINDING, row.as_dict()
    assert row.detail == {"unmerged": spelled, "count": 7,
                          "merge_head": False}, row.detail
    assert ("7 path(s) unmerged in the index, so git commits nothing here "
            "until each is resolved: a.md, b.md, c.md, d.md, e.md and 2 "
            "more. ") in row.reason, row.reason
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == "INVALID (merge)"


def test_an_awkward_unmerged_name_is_spelled_on_one_line(standard, project):
    """A name holding a line break, and one holding a byte that is not
    UTF-8, are spelled by `repr`, as the placement row spells one, so the
    report stays one line per row and the name is still the name."""
    names = [b"line\nbreak.md", b"caf\xe9.md"]
    if not unmerged_in_the_index(project, names):
        pytest.skip("git does not hold these names in the index here")
    module, row = merge_row(standard, project)
    spelled = [repr("caf\udce9.md"), repr("line\nbreak.md")]
    assert row.detail["unmerged"] == spelled, row.detail
    assert ", ".join(spelled) in row.reason, row.reason
    assert "\n" not in row.reason and "\n" not in row.next_command
    text = doctor(standard, project)
    assert text.returncode == 1, text.stdout + text.stderr
    [line] = [line for line in text.stdout.splitlines()
              if " merge " in line and "unmerged in the index" in line]
    assert ", ".join(spelled) in line, line


def test_the_merge_rung_outranks_drift_and_asks_for_its_list(standard):
    """The ladder, asked in process. An unmerged index outranks a leg off
    its pin and a red validator: it is what made them so. But a `merge`
    FINDING with an empty `detail` -- what `run_checks` makes of a check
    that raised -- names no path, so it is not the merge verdict: the rungs
    above the catch-all answer first, as they do for a placement row with
    no list."""
    module = doctor_module(standard)
    ctx = module.Context.__new__(module.Context)
    ctx.kind = module.PROJECT
    off_pin = module.Row("legs", "legs", module.FINDING, "off its pin", None,
                         {"legs": [{"role": "spec", "head": "1" * 40,
                                    "pin": "2" * 40}]})
    red = module.Row("pins", "pins", module.FINDING, "red", None, {})
    unfinished = module.Row("merge", "merge", module.FINDING, "unmerged",
                            None, {"unmerged": ["spec"], "count": 1,
                                   "merge_head": True})
    assert module.verdict_for(ctx, [off_pin, red]) == (
        "DRIFTED (1 leg(s) not at the pin)", 1)
    assert module.verdict_for(ctx, [unfinished, off_pin, red]) == (
        "INVALID (merge)", 1)
    raised = module.Row("merge", "merge", module.FINDING, "could not be run",
                        None, {})
    assert module.verdict_for(ctx, [raised, off_pin, red]) == (
        "DRIFTED (1 leg(s) not at the pin)", 1)
    assert module.verdict_for(ctx, [raised, red]) == ("INVALID (pins)", 1)
