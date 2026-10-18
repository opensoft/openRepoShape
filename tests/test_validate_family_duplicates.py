# SPDX-License-Identifier: Apache-2.0
"""`validate-family.py` finds `member-duplicate` under `--no-members` too, and
in any case (#331).

TWO FAULTS IN ONE FINDING. `member-duplicate` was raised in
`_member_project_name`, which only the members-checked loop reaches, and
`_check_members` returns before that loop under `--no-members`: the run a
private family's CI falls back to when its members cannot be checked out, so
a `family.yaml` that named one row twice passed the one gate that ran. And it
compared `project:` EXACTLY, so rows `IRRS` and `irrs` with distinct ids
passed everywhere, though `members/IRRS` and `members/irrs` are ONE directory
on macOS and Windows. `family.py add` refuses a case variant now, so only a
hand edit makes such rows; this is the gate that finds the hand edit.

The finding is now its own function, `_check_member_names_unique`, which
reads `members:` alone and is called before the `--no-members` return, as
`member-duplicate-id` (#206, `tests/test_family.py`) is. It is made ONCE,
whatever the mode, and an exact repeat keeps the text it always had. Case is
folded with `str.casefold()`, so a pair a disk holds as one directory and
`str.lower()` keeps apart (the long s, the sigmas) is found too.

The same family and the same offline rules as `tests/test_family.py`: the
fixture is imported rather than rebuilt, because a holder made any other way
would test a different holder. Members are scaffolded into local bare
repositories and nothing is created on GitHub.

THE ROWS ARE BUILT IN `family.yaml` AND NEVER ON DISK, except in the one test
that mounts a second member at `members/irrs`: `--no-members` reads no
member, and a fixture with two directories whose names differ only in case
cannot exist on macOS or Windows (`mount_twice` spells its second row `IRRS2`
for that reason). That one test says so and skips there; every other row of
this module runs on all three platforms. Each member the holder mounts keeps
a row (`keeping_mounts`): a mount no row names is a finding of its own since
#361.
"""

from __future__ import annotations

import pytest

from conftest import git, run_script
from test_family import (  # noqa: F401
    ORG, SPARE, family, family_module, holder, manifest, tree_digest,
    validate,
)

#: The finding an exact repeat has always had, byte for byte. A holder's CI
#: matches on text, so it is pinned here and not rebuilt from a template.
EXACT = "FINDING member-duplicate: IRRS appears more than once in `members:`"

#: A commit nothing can resolve. A repeated row pinned to it is what makes the
#: members-checked loop refuse (`member-commit-unresolvable`, exit 2, and the
#: finding lost) if `_member_project_name` ever stops skipping a name it has
#: already seen: a repeat copied byte for byte checks out as cleanly as the
#: row it repeats, so it would never notice.
NOWHERE = "0" * 40

#: Pairs one case-insensitive disk holds as one directory and `str.lower()`
#: keeps apart, which only `str.casefold()` finds: IRRS and IRR with the long s
#: (U+017F, folds to `s`), and capital sigmas against small ones (`lower()`
#: gives the final sigma U+03C2 where the small spelling has U+03C3). Written as
#: escapes so no editor or console re-encodes them.
FOLDS = {
    "long-s": ("IRRS", "irr\u017f"),
    "sigma": ("\u03a3\u0391\u03a3", "\u03c3\u03b1\u03c3"),
}


def irrs_row(holder) -> dict:
    """IRRS's row, as the manifest reads it back."""
    return next(row for row in manifest(holder)["members"]
                if row["project"] == "IRRS")


def spelled(row: dict, project: str, member_id: str) -> dict:
    """`row` under another spelling of the project, with an id of its own.

    The id is DISTINCT on purpose: `member-duplicate-id` asks whether one
    project is mounted twice, and every row here is a different question —
    whether one DIRECTORY is named twice.
    """
    assert member_id != row["id"], "the point is a distinct id"
    return {**row, "project": project, "id": member_id,
            "repository": f"{ORG}/{project}", "path": f"members/{project}"}


def rewrite(holder, rows: list) -> None:
    """The holder's `members:` block replaced by `rows`, and committed."""
    family_module().Family.open(holder).write_members(rows)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam",
        "Rewrite the members", cwd=holder)


def keeping_mounts(holder, rows: list) -> list:
    """`rows`, then the holder's own row for each member it mounts that no
    row in `rows` gives the path of. A mount no row names is a finding of
    its own (#361, `member-gitlink-unnamed` and `gitmodules-path-unnamed`),
    and every test here asks about the names `rows` spells, not about that,
    so each member the holder mounts keeps a row."""
    given = {row.get("path") for row in rows}
    return [*rows, *(row for row in manifest(holder)["members"]
                     if row["path"] not in given)]


def findings(result) -> list[str]:
    """Every `FINDING` line, in the order they were printed."""
    return [line for line in result.stderr.splitlines()
            if line.startswith("FINDING")]


def case_pair(first: str, second: str) -> str:
    """The head of the finding for two rows that differ only in case: both
    rows AS WRITTEN, the earlier one first, then what makes them one."""
    return (f"FINDING member-duplicate: {first} and {second} are two rows of "
            "`members:` whose `project:` differs only in case, so "
            f"`members/{first}` and `members/{second}` are one directory on "
            "a case-insensitive disk")


# --- one row written twice ---------------------------------------------------

def test_a_row_written_twice_is_found_under_no_members(holder):
    """The run a private family's CI falls back to. The duplicate is a fact of
    `family.yaml` alone, so it is found beside the members that run skips."""
    row = irrs_row(holder)
    other = next(r for r in manifest(holder)["members"]
                 if r["project"] == "IRSS")
    rewrite(holder, [row, dict(row), other])
    result = validate(holder, "--no-members")
    assert result.returncode == 1, result.stderr + result.stdout
    assert findings(result) == [EXACT], result.stderr
    assert "member(s) SKIPPED (--no-members)" in result.stdout


@pytest.mark.parametrize("extra", [(), ("--pins",)],
                         ids=["members-checked", "pins"])
@pytest.mark.parametrize("repeat", ["identical", "other-pin"])
def test_with_members_checked_a_repeat_is_one_finding_not_two(holder, extra,
                                                              repeat):
    """`_member_project_name` used to make this finding and still stops that
    row's checks, silently. A finding made in both places would be one fault
    reported twice, and the count is what says so.

    THE REPEAT IS ALSO PINNED TO A COMMIT NOWHERE (`other-pin`), because a
    repeat that is byte for byte the row it repeats passes every check the
    first one did, so deleting the skip would cost it nothing: it is the row
    that would be checked, refused `member-commit-unresolvable` (exit 2) and
    lose the finding, that holds the skip in place.
    """
    row = irrs_row(holder)
    again = (dict(row) if repeat == "identical" else
             {**row, "pin": {**row["pin"], "commit": NOWHERE}})
    other = next(r for r in manifest(holder)["members"]
                 if r["project"] == "IRSS")
    rewrite(holder, [row, again, other])
    result = validate(holder, *extra)
    assert result.returncode == 1, result.stderr + result.stdout
    assert findings(result) == [EXACT], result.stderr
    assert result.stderr.count("member-duplicate") == 1, result.stderr
    assert "REFUSED" not in result.stderr, result.stderr


# --- two rows that differ only in case ---------------------------------------

@pytest.mark.parametrize("first,second", [("IRRS", "irrs"), ("irrs", "IRRS")],
                         ids=["upper-first", "lower-first"])
def test_rows_that_differ_only_in_case_are_found_under_no_members(
        holder, first, second):
    """Both rows are named as WRITTEN, the earlier one first, whichever of
    the two spellings that is, and the finding says why they are one."""
    base = irrs_row(holder)
    rewrite(holder, keeping_mounts(holder, [
        spelled(base, first, "irrs-first"),
        spelled(base, second, "irrs-second")]))
    result = validate(holder, "--no-members")
    assert result.returncode == 1, result.stderr + result.stdout
    assert len(findings(result)) == 1, result.stderr
    assert findings(result)[0].startswith(case_pair(first, second)), \
        result.stderr
    assert "member-duplicate-id" not in result.stderr
    assert "member(s) SKIPPED (--no-members)" in result.stdout


def test_a_case_variant_is_not_the_exact_finding(holder):
    """The two are different faults in different words: an exact repeat says
    it appears more than once, and a case variant says it is one directory on
    some disks. A reader told the wrong one goes looking for a row that is
    not there."""
    base = irrs_row(holder)
    rewrite(holder, keeping_mounts(
        holder, [base, spelled(base, "irrs", "irrs-twin")]))
    result = validate(holder, "--no-members")
    assert result.returncode == 1, result.stderr + result.stdout
    assert len(findings(result)) == 1, result.stderr
    assert "appears more than once" not in result.stderr, result.stderr


@pytest.mark.parametrize("pair", FOLDS.values(), ids=FOLDS.keys())
def test_rows_that_a_disk_folds_but_lower_does_not_are_found_under_no_members(
        holder, pair):
    """`--no-members` reads any string as a `project:` (the checks that hold a
    name to ASCII run only with members checked), so a hand edit can write a
    pair that `str.lower()` keeps apart and a case-insensitive disk does not.
    The fold is `casefold()`, as the standard's other same-path-in-any-case
    checks use. The child is run in UTF-8 mode so the names print as written
    on every platform."""
    first, second = pair
    assert first.lower() != second.lower(), "the point is that lower() fails"
    base = irrs_row(holder)
    rewrite(holder, keeping_mounts(holder, [
        spelled(base, first, "irrs-first"),
        spelled(base, second, "irrs-second")]))
    result = run_script(holder / "scripts" / "validate-family.py",
                        "--no-members", cwd=holder,
                        env={"PYTHONUTF8": "1"})
    assert result.returncode == 1, result.stderr + result.stdout
    assert len(findings(result)) == 1, result.stderr
    assert findings(result)[0].startswith(case_pair(first, second)), \
        result.stderr


def test_the_case_finding_does_not_assume_one_project(holder):
    """Rows with distinct ids may be two projects (`OrgA/IRRS` and
    `OrgB/irrs`): the fault is one DIRECTORY, not one project pinned twice, so
    the finding says so and says one row has to go. It names no command,
    because `family.py remove` cannot take out a row that was never mounted,
    which is the only kind a macOS or Windows holder can hold."""
    base = irrs_row(holder)
    rewrite(holder, keeping_mounts(
        holder, [base, spelled(base, "irrs", "irrs-twin")]))
    result = validate(holder, "--no-members")
    assert result.returncode == 1, result.stderr + result.stdout
    (line,) = findings(result)
    assert line.startswith(case_pair("IRRS", "irrs")), line
    assert ("and a holder there can keep only one of them. Whether the rows "
            "pin one project or two, one of them has to go: keep the row "
            "whose `repository:` is the member's and drop the other."
            ) in line, line
    assert "pins each project once" not in result.stderr
    assert "family.py" not in line


def test_each_later_row_is_one_finding_against_the_first_that_holds_its_name(
        holder):
    """Three spellings of one name and one of them twice: every row after the
    first is ONE finding, a case variant names the first row it collides with
    and an exact repeat keeps its own text, in file order."""
    base = irrs_row(holder)
    lower = spelled(base, "irrs", "irrs-two")
    title = spelled(base, "Irrs", "irrs-three")
    rewrite(holder, keeping_mounts(holder,
                                   [base, lower, title, dict(lower)]))
    result = validate(holder, "--no-members")
    assert result.returncode == 1, result.stderr + result.stdout
    found = findings(result)
    assert len(found) == 3, result.stderr
    assert found[0].startswith(case_pair("IRRS", "irrs")), found
    assert found[1].startswith(case_pair("IRRS", "Irrs")), found
    assert found[2] == ("FINDING member-duplicate: irrs appears more than "
                        "once in `members:`"), found


def test_distinct_names_are_not_folded_into_one(holder):
    """A name that merely starts with another's, or ends with a digit, is its
    own row: the fold is CASE alone."""
    base = irrs_row(holder)
    other = next(r for r in manifest(holder)["members"]
                 if r["project"] == "IRSS")
    rewrite(holder, [base, spelled(base, "IRRS2", "irrs2"),
                     spelled(base, "IRR", "irr"), other])
    result = validate(holder, "--no-members")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "family ok: InkRouter (inkrouter), 4 member(s)" in result.stdout


# --- a holder with nothing wrong ---------------------------------------------

@pytest.mark.parametrize("extra", [(), ("--pins",), ("--no-members",)],
                         ids=["members-checked", "pins", "no-members"])
def test_distinct_names_pass_in_every_mode(holder, extra):
    """The family `init` and `add` made: two members, two names."""
    result = validate(holder, *extra)
    assert result.returncode == 0, result.stderr + result.stdout
    assert findings(result) == []
    assert "family ok: InkRouter (inkrouter), 2 member(s)" in result.stdout


def test_a_row_with_no_project_is_not_this_findings_to_make(holder):
    """A row with no `project:` is `member-project`'s, which only the
    members-checked loop asks, and a row that is no mapping is
    `member-row`'s, which `--no-members` asks too since #864. This one skips
    both rather than crash on them or call either a duplicate: a traceback
    exits 1, which is a finding's code, so the one finding is
    `member-row`'s."""
    # BYTES, so Windows does not rewrite the whole manifest with CRLF.
    text = (holder / "family.yaml").read_bytes().decode("utf-8")
    (holder / "family.yaml").write_bytes(
        (text + "  - nameless\n  - id: nameless\n").encode("utf-8"))
    result = validate(holder, "--no-members")
    assert result.returncode == 1, result.stderr + result.stdout
    assert "Traceback" not in result.stderr
    assert findings(result) == [
        "FINDING member-row: a member is not a mapping: 'nameless'"]


# --- both rows mounted -------------------------------------------------------

@pytest.fixture
def case_sensitive(tmp_path):
    """Skips on a disk that holds `Dir` and `dir` as one, as macOS and
    Windows do by default: the second mount cannot exist there."""
    (tmp_path / "CaseProbe").mkdir()
    if (tmp_path / "caseprobe").exists():
        pytest.skip("this disk is case-insensitive, so members/IRRS and "
                    "members/irrs cannot both be mounted; every other row "
                    "of this module builds its rows in family.yaml and runs "
                    "here")


@pytest.mark.parametrize("extra", [(), ("--pins",), ("--no-members",)],
                         ids=["members-checked", "pins", "no-members"])
def test_two_mounted_rows_that_differ_only_in_case_are_one_finding(
        family, holder, case_sensitive, extra):
    """BOTH ROWS REAL, in every way the gate asks about: mounted at the path
    their name makes, pinned at the commit mounted there, digested, and the
    `project.yaml` inside says the id the row says — `irrs` mounts a
    different member (IRQS, id `irqs`) so the ids are distinct and the only
    thing wrong is the name. Members checked or not, it is ONE finding."""
    git("-c", "protocol.file.allow=always", "submodule", "add", "-q", "--",
        str(family["remotes"] / f"{SPARE}.git"), "members/irrs", cwd=holder)
    mounted = holder / "members" / "irrs"
    commit = git("rev-parse", "HEAD", cwd=mounted).stdout.strip()
    base = irrs_row(holder)
    twin = spelled(base, "irrs", SPARE.lower())
    twin["pin"] = {**base["pin"], "commit": commit,
                   "tree_sha256": tree_digest(mounted, commit)}
    family_module().Family.open(holder).write_members(
        [*manifest(holder)["members"], twin])
    git("add", "--", ".gitmodules", "members/irrs", "family.yaml",
        cwd=holder)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "Mount a second member that differs from IRRS only in case",
        cwd=holder)
    result = validate(holder, *extra)
    assert result.returncode == 1, result.stderr + result.stdout
    assert len(findings(result)) == 1, result.stderr
    assert findings(result)[0].startswith(case_pair("IRRS", "irrs")), \
        result.stderr
