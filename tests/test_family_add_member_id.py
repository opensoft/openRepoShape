# SPDX-License-Identifier: Apache-2.0
"""`family.py add` asks whether the member's `project.yaml` `id` is one the
family already pins, before anything is mounted (#330).

`add` compared the new member's NAMES with the rows — its project and its
repository, which #206 made case-blind — and a repository renamed at the forge
keeps its `project.yaml`. So `--member testorg/Atlas2`, a copy of the pinned
`testorg/Atlas` under a new name, passed every check, was mounted, and
committed a second row recording id `atlas`; the holder's own
`validate-family.py` then refused that commit as `member-duplicate-id`, and
the holder's CI went red on a commit `add` had written.

The id is now asked of the throwaway clone #203 reads the member from, under
the validator's own code, while the holder is exactly as it was, and again of
the mount's reading, which is what the row records — so a linked
`project.yaml`, which the probe leaves to the mount, and a member that moved
in between are refused there and unwound. Where a section under another name
already gives the mount path (#300), that refusal of the holder's is said
first, with nothing cloned, and the id on the re-run. The last test runs the
holder's own validator over each manifest `add` would write, so "refuses what
the gate would refuse, and nothing it would pass" is measured, not asserted.

THE ISSUE'S MEMBERS ARE `Atlas` and `Atlas2`; this family's are `IRRS` and
`IRSS`, so the renamed copy is `IRRS2`. The same family and the same rules as
`test_family.py` and `test_family_add_refusals.py`: members are scaffolded into
local bare repositories, nothing is created on GitHub, a `gh` on PATH logs and
exits non-zero, and no test writes to the fixture's own remotes.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from conftest import git, run_script
#: The family fixture, its names and the offline environment, imported from
#: the modules that own them rather than rebuilt: a holder made any other way
#: would test a different holder.
from test_family import (  # noqa: F401
    FAMILY, MEMBERS, NAME, ORG, SPARE, family, manifest, validate,
)
from test_family_add_refusals import (  # noqa: F401
    GHOST_REMOVAL, assert_unchanged, family_module, ghost_remediation,
    gitmodules_with, holder, mount_undone, offline, refusal, snapshot,
    take_out_as_printed,
)

#: The project the renamed copy is of, and the name it is added under.
PINNED = "IRRS"
RENAMED = "IRRS2"

#: What `add` says when the member records an id the row `IRRS` pins. `{who}`
#: is the member's name, `{after}` what follows the detail: nothing before the
#: mount, the unwind's sentence after it.
DUPLICATE_ID = (
    f"REFUSED member-duplicate-id: {{who}} is already a member of "
    f"{NAME} under another name: {ORG}/{{who}}'s project.yaml records id "
    f"'irrs', and the row {PINNED} pins {ORG}/{PINNED} with that id. Adding "
    "it would pin one project twice, which `validate-family.py` refuses"
    "{after}")

DUPLICATE_ID_REMEDIATION = (
    f"Remediation: a family pins each project once. If {ORG}/{{who}} is "
    f"{ORG}/{PINNED} renamed at the forge, `family.py remove --member "
    f"{PINNED}` takes the old row out and this `add` then pins it under the "
    f"new name; `family.py bump --member {PINNED} --to <commit>` moves the "
    "row that is there instead. Two projects that record one id are a fault "
    "in one of their `project.yaml` files, mended in that project, not in "
    "the family.")


def renamed_copy(family, tmp_path: Path) -> Path:
    """A directory of remotes holding `IRRS2.git`: a bare clone of the pinned
    `IRRS`, every commit and its `project.yaml` (id `irrs`) included — what a
    repository renamed at the forge is to anybody who clones it by the new
    name. The fixture's own remotes are not written to."""
    remotes = tmp_path / "remotes"
    remotes.mkdir()
    git("clone", "-q", "--bare", str(family["remotes"] / f"{PINNED}.git"),
        str(remotes / f"{RENAMED}.git"), cwd=tmp_path)
    return remotes


def test_a_renamed_repository_is_refused_before_anything_is_mounted(
        family, holder, offline, tmp_path):
    """THE ISSUE'S CASE. The copy has a name no row has, so `holding` passes
    it, and its `project.yaml` records the id the row `IRRS` pins: refused as
    `member-duplicate-id`, naming that row, with the two commands that move
    or replace it — and refused BEFORE THE MOUNT, so no `mounting` line is
    printed and the holder is exactly as it was, its gate still green."""
    remotes = renamed_copy(family, tmp_path)
    before = snapshot(holder)
    result = offline.add(holder, RENAMED, remotes=remotes)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == f"checking {ORG}/{RENAMED} before mounting it\n"
    assert refusal(result.stderr) == (
        DUPLICATE_ID.format(who=RENAMED, after=""),
        DUPLICATE_ID_REMEDIATION.format(who=RENAMED))
    assert_unchanged(holder, before, RENAMED)
    assert validate(holder).returncode == 0
    offline.assert_left_nothing()


def test_a_section_already_at_the_mount_path_is_refused_first_then_the_id(
        family, holder, offline, tmp_path):
    """BOTH REFUSALS APPLY, AND THE HOLDER'S IS SAID FIRST. The renamed
    copy's mount path, `members/IRRS2`, is also given to a committed section
    named `ghost` (#300). `member-path-registered` is one of the holder's
    refusals, asked before the member is read: not one line on stdout,
    nothing cloned, the holder byte for byte as it was. Its commands, run as
    printed, take the section out, and the same `add` is then refused as
    `member-duplicate-id` after the probe, with the holder again exactly as
    the removal left it."""
    remotes = renamed_copy(family, tmp_path)
    gitmodules_with(holder, (f'[submodule "ghost"]\n\tpath = members/'
                             f"{RENAMED}\n\turl = /nowhere/ghost.git\n"
                             ).encode("utf-8"), "the work tree")
    before = snapshot(holder)
    first = offline.add(holder, RENAMED, remotes=remotes)
    assert first.returncode == 2, first.stdout + first.stderr
    assert first.stdout == ""
    said, remediation = refusal(first.stderr)
    assert said == (
        "REFUSED member-path-registered: .gitmodules already gives the path "
        f"members/{RENAMED} to the submodule named `ghost` (url "
        f"/nowhere/ghost.git), and that is the path {RENAMED} is mounted at")
    assert remediation == ghost_remediation(GHOST_REMOVAL)
    assert_unchanged(holder, before, RENAMED)
    offline.assert_left_nothing()

    assert len(take_out_as_printed(holder, remediation)) == 2, remediation
    cleared = snapshot(holder)
    second = offline.add(holder, RENAMED, remotes=remotes)
    assert second.returncode == 2, second.stdout + second.stderr
    assert second.stdout == f"checking {ORG}/{RENAMED} before mounting it\n"
    assert refusal(second.stderr) == (
        DUPLICATE_ID.format(who=RENAMED, after=""),
        DUPLICATE_ID_REMEDIATION.format(who=RENAMED))
    assert snapshot(holder) == cleared
    assert not (holder / "members" / RENAMED).exists()
    assert not (holder / ".git" / "modules" / "members" / RENAMED).exists()
    assert validate(holder).returncode == 0
    offline.assert_left_nothing()


@pytest.mark.parametrize("verb", ["remove", "bump"])
def test_each_command_the_refusal_names_runs_on_the_row_it_names(
        family, holder, offline, tmp_path, verb):
    """The remediation is the repair. Typed as printed — with the
    `--family-root` every verb takes, and a real commit for `<commit>` —
    `remove` takes the old row out and the refused `add` then pins the
    project under its new name, and `bump` moves the row that is there; the
    gate is green after either, with one row recording id `irrs`."""
    remotes = renamed_copy(family, tmp_path)
    refused = offline.add(holder, RENAMED, remotes=remotes)
    assert refused.returncode == 2, refused.stdout + refused.stderr
    commands = re.findall(rf"`family\.py ({verb} [^`]*)`", refused.stderr)
    assert len(commands) == 1, refused.stderr
    older = git("rev-parse", "main~1",
                cwd=family["remotes"] / f"{PINNED}.git").stdout.strip()
    argv = commands[0].replace("<commit>", older).split()
    assert argv[argv.index("--member") + 1] == PINNED
    done = run_script(FAMILY, *argv, "--family-root", str(holder),
                      env=offline.env)
    assert done.returncode == 0, done.stdout + done.stderr
    if verb == "remove":
        added = offline.add(holder, RENAMED, remotes=remotes)
        assert added.returncode == 0, added.stdout + added.stderr
        expected = sorted([RENAMED, *MEMBERS[1:]])
    else:
        expected = list(MEMBERS)
    rows = {row["project"]: row for row in manifest(holder)["members"]}
    assert sorted(rows) == expected
    assert [p for p, row in rows.items() if row["id"] == "irrs"] == [
        RENAMED if verb == "remove" else PINNED]
    if verb == "bump":
        assert rows[PINNED]["pin"]["commit"] == older
    assert git("status", "--porcelain", cwd=holder).stdout == ""
    assert validate(holder).returncode == 0


@pytest.mark.skipif(sys.platform == "win32",
                    reason="a tracked symlink is a plain file in a Windows "
                           "checkout")
def test_a_linked_manifest_with_a_pinned_id_is_refused_by_the_mount_unwound(
        holder, offline, tmp_path):
    """A LINKED `project.yaml` IS LEFT TO THE MOUNT (#203): the object store
    holds only the link's text, so the probe returns no id, and the mount's
    reading — through the link — is the one that finds `irrs`. Refused there,
    and the mount undone: the holder is exactly as it was and the sentence
    says what was put back. (The link is built in the member's INDEX, not on
    a disk, as `test_family_add_refusals.py` builds its linked member.)"""
    remotes = tmp_path / "remotes"
    remotes.mkdir()
    work = tmp_path / "IRLN-work"
    git("init", "-q", str(work), cwd=tmp_path)
    (work / "manifest").mkdir()
    (work / "manifest" / "project.yaml").write_bytes(
        b"schema_version: 1\nkind: project-manifest\nid: irrs\nname: IRLN\n")
    git("add", "--", "manifest/project.yaml", cwd=work)
    link = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                          cwd=str(work), input=b"manifest/project.yaml",
                          capture_output=True, check=True).stdout
    git("update-index", "--add", "--cacheinfo",
        f"120000,{link.decode('ascii').strip()},project.yaml", cwd=work)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "A linked manifest recording a pinned id", cwd=work)
    git("clone", "-q", "--bare", str(work), str(remotes / "IRLN.git"),
        cwd=tmp_path)

    before = snapshot(holder)
    result = offline.add(holder, "IRLN", remotes=remotes)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == (f"checking {ORG}/IRLN before mounting it\n"
                             f"mounting {ORG}/IRLN at members/IRLN\n")
    assert refusal(result.stderr) == (
        DUPLICATE_ID.format(who="IRLN",
                            after=". " + mount_undone("IRLN")),
        DUPLICATE_ID_REMEDIATION.format(who="IRLN"))
    assert_unchanged(holder, before, "IRLN")
    assert validate(holder).returncode == 0
    offline.assert_left_nothing()


def test_a_member_whose_id_changes_between_the_probe_and_the_mount_is_unwound(
        family, holder, offline, tmp_path, family_module, monkeypatch,
        capsys):
    """THE BACKSTOP, ON EVERY PLATFORM. The probe reads `IRQS` recording
    `irqs`, which no row pins; a commit pushed before the mount changes the
    id to `irrs`, and the mount's reading — the one the row would record —
    is refused and unwound like any refusal after the mount."""
    remotes = tmp_path / "remotes"
    shutil.copytree(family["remotes"] / f"{SPARE}.git",
                    remotes / f"{SPARE}.git", symlinks=True)
    probe = family_module._probe_member

    def renumbered(*args, **kwargs):
        probed = probe(*args, **kwargs)
        work = tmp_path / "moving"
        git("clone", "-q", str(remotes / f"{SPARE}.git"), str(work),
            cwd=tmp_path)
        text = (work / "project.yaml").read_bytes()
        changed = re.sub(rb"(?m)^id: irqs$", b"id: irrs", text)
        assert changed != text
        (work / "project.yaml").write_bytes(changed)
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam",
            "Record IRRS's id", cwd=work)
        git("push", "-q", "origin", "HEAD", cwd=work)
        return probed

    monkeypatch.setattr(family_module, "_probe_member", renumbered)
    monkeypatch.setattr(tempfile, "tempdir", str(offline.temp))
    monkeypatch.setenv("PATH", offline.env["PATH"])
    before = snapshot(holder)
    code = family_module.main(["add", "--family-root", str(holder),
                               "--member", f"{ORG}/{SPARE}",
                               "--local-remote-dir", str(remotes)])
    out, err = capsys.readouterr()
    assert code == 2, out + err
    assert out == (f"checking {ORG}/{SPARE} before mounting it\n"
                   f"mounting {ORG}/{SPARE} at members/{SPARE}\n")
    assert refusal(err) == (
        DUPLICATE_ID.format(who=SPARE, after=". " + mount_undone(SPARE)),
        DUPLICATE_ID_REMEDIATION.format(who=SPARE))
    assert_unchanged(holder, before, SPARE)
    offline.assert_left_nothing()


def row_lines(row: dict) -> list[str]:
    """A `members:` row with only the keys it has — the validator's
    `--no-members` run reads no pin, so a row needs none, and a hand-edited
    row with no `project:` or no `id:` is written as such."""
    lines = [f"{key}: {value}" for key, value in row.items()]
    return ([f"  - {lines[0]}"] + [f"    {line}" for line in lines[1:]]
            if lines else [])


def write_rows(root: Path, rows: list[dict]) -> None:
    """`family.yaml` with its `members:` block replaced by `rows`, LF."""
    text = (root / "family.yaml").read_text(encoding="utf-8")
    head = text[:text.index("\nmembers:") + 1]
    body = [line for row in rows for line in row_lines(row)]
    (root / "family.yaml").write_bytes(
        (head + ("members:\n" + "\n".join(body) if body else "members: []")
         + "\n").encode("utf-8"))


def row(project: str | None, member_id: str | None) -> dict:
    found = {"project": project, "id": member_id,
             "repository": f"{ORG}/{project or 'Nameless'}"}
    return {key: value for key, value in found.items() if value is not None}


@pytest.mark.parametrize("rows, named", [
    # One project under another name: the issue's case.
    ([row(PINNED, "irrs")], PINNED),
    # Another project, another id.
    ([row(PINNED, "irrt")], None),
    # Exact comparison, as the validator's: a hand-typed `IRRS` is not `irrs`.
    ([row(PINNED, "IRRS")], None),
    # A row with no `id:` is `member-id-absent`'s, not this rule's.
    ([row(PINNED, None)], None),
    # A row with no `project:` is `member-project`'s, not this rule's.
    ([row(None, "irrs")], None),
    # A row whose `project:` an earlier row spells exactly is
    # `member-duplicate`'s; the earlier row's id is the one asked.
    ([row(PINNED, "irrt"), row(PINNED, "irrs")], None),
    ([row(PINNED, "irrs"), row(PINNED, "irrt")], PINNED),
    # A row sorting after the new one is asked as well as one before it.
    ([row("Zeta", "irrs")], "Zeta"),
])
def test_add_refuses_exactly_what_the_holders_own_validator_would_find(
        holder, family_module, rows, named):
    """THE GATE'S OWN ANSWER. For each set of rows, `add`'s question
    (`_checked_member_id`, no disk) and the holder's `validate-family.py
    --no-members` — the run that reads `family.yaml` alone — over the rows
    `add` would write, sorted by project as `add` sorts them: the rows
    before are clean, and `add` refuses, naming the row the validator pairs
    the new one with, exactly when the rows after carry a
    `member-duplicate-id` finding."""
    new = row(RENAMED, "irrs")
    write_rows(holder, rows)
    clean = validate(holder, "--no-members")
    assert "member-duplicate-id" not in clean.stderr, clean.stderr
    write_rows(holder, sorted([*rows, new],
                              key=lambda r: str(r.get("project"))))
    found = validate(holder, "--no-members")
    findings = re.findall(r"FINDING member-duplicate-id: (\S+) and (\S+) "
                          r"both record id 'irrs'", found.stderr)
    assert [set(pair) for pair in findings] == (
        [{RENAMED, named}] if named else []), found.stderr
    asked = family_module.Family(holder, {"name": NAME, "members": rows})
    try:
        family_module._checked_member_id(asked, f"{ORG}/{RENAMED}", RENAMED,
                                         "irrs")
    except family_module.Refusal as exc:
        assert named is not None, str(exc)
        assert exc.code == "member-duplicate-id"
        assert f"the row {named} pins {ORG}/{named} with that id" \
            in exc.detail, exc.detail
    else:
        assert named is None
