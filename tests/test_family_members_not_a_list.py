# SPDX-License-Identifier: Apache-2.0
"""A family holder's `members:` that is not a list, or that holds an entry
that is not a mapping, is read by every reader of it as the holder's own
`validate-family.py` reads it, and said in its words (#864).

EACH ITERATED `members or []`: the doctor's `Context.members`,
`scripts/family.py`'s `Family.members`, and the family root's
`scripts/bootstrap.py` `members_of`, which `scripts/siblings.py` and
`family.py siblings` reach. So `members: 5` ended the doctor's whole report,
`add`, `bump` and `remove`, `make bootstrap` and `make siblings` in
`TypeError: 'int' object is not iterable`. A scalar `openXdox`, a mapping
`{a: b}` or a list of entries that are not mappings read as a family with no
members: the doctor's `members` row said `ok` "no members yet" one row under
the `family` row's refusal, `bump` and `remove` said `member-unknown` of a
member mounted there, `add` said `family-members-unrecognised` of a
`members:` line that is there, and bootstrap and siblings said "0 member(s)"
and exited 0. And for a block list of real rows and an entry `5`, `add`,
`bump` and `remove` exited 0 and committed a `family.yaml` without the entry,
while bootstrap and siblings counted the rows beside it and said nothing.

NOW each says the gate's sentence, the value spelled as the gate spells it
(`repr`), so no control character reaches a terminal raw:

    family-members-unreadable: <holder>/family.yaml: `members:` is <value>,
      expected a list
    member-row: a member is not a mapping: <entry>

- the doctor's `members` row is `n/a`, says the sentence and waits on the
  `family` row (`waits_on`), which runs the gate, as it waits on a
  `family.yaml` that does not load (#205);
- `add`, `bump` and `remove` refuse `family-members-unreadable`, exit 2, in
  both runs, in `Family.open`: before anything is fetched, mounted or
  rewritten, so `family.yaml` keeps its bytes and no commit is made;
- bootstrap, siblings and `family.py siblings` refuse it, exit 2, in
  `members_of`, before anything is fetched or placed;
- `validate-family.py --no-members` makes the `member-row` finding, which it
  made only past its own return, so it no longer counts `5` as a member
  and exits 0. A `members:` that is not a list it refused already.

Absent, null and `[]` are a family with no members, and every reader still
says so: the controls at the end.

THE HARNESS is `tests/test_family.py`'s `family`, `holder` and `validate`;
the doctor through `tests/test_shape_doctor.py`'s `doctor` and `rows_of`,
run from this checkout as `tests/test_family.py` runs it; and, for the two
siblings runs, which ask about the holder's parent folder before they place
anything, `tests/test_family_siblings_placement.py`'s `holder_in`.
"""

from __future__ import annotations

import pytest

from conftest import REPO, git, run_script
from test_family import (  # noqa: F401
    FAMILY, NAME, ORG, SPARE, family, holder, siblings, validate,
)
from test_family_siblings_placement import holder_in
from test_shape_doctor import doctor, rows_of
from test_validate_family_duplicates import findings

MANIFEST = "family.yaml"

#: `family.py init` writes `members:` as the manifest's last block, and
#: `family.py add` keeps it last.
MEMBERS_BLOCK = "\nmembers:\n"

#: The block list of the fixture's two real rows and, after them, an entry
#: that is not a mapping: the case the three verbs committed away.
ROWS_AND_A_NUMBER = object()

#: The sentence for an entry, as the gate's `member-row` finding says it.
NOT_A_MAPPING = "a member is not a mapping: "

#: `(YAML spelling, the sentence said)`, the sentence less the path the
#: refusal puts before it: the issue's six values and its block list of real
#: rows and `- 5`, a value holding ESC, and the three FALSY values that are
#: not a list, `0` (which the issue measured too), `false` and `''`. They are
#: what tells `is None` apart from `or []` or `not members`: read either way,
#: each was a family with no members, #864's own defect (RV870's SHOULD-1).
CASES = [
    pytest.param("5", "`members:` is 5, expected a list", id="number"),
    pytest.param("0", "`members:` is 0, expected a list", id="zero"),
    pytest.param("false", "`members:` is False, expected a list",
                 id="false"),
    pytest.param("''", "`members:` is '', expected a list",
                 id="empty-string"),
    pytest.param("openXdox", "`members:` is 'openXdox', expected a list",
                 id="scalar-string"),
    pytest.param("{a: b}", "`members:` is {'a': 'b'}, expected a list",
                 id="mapping"),
    pytest.param("[5]", f"{NOT_A_MAPPING}5", id="list-number"),
    pytest.param("[openXdox]", f"{NOT_A_MAPPING}'openXdox'",
                 id="list-string"),
    pytest.param("[null]", f"{NOT_A_MAPPING}None", id="list-null"),
    pytest.param('"\\x1b[31mRED"',
                 "`members:` is '\\x1b[31mRED', expected a list",
                 id="esc-string"),
    pytest.param(ROWS_AND_A_NUMBER, f"{NOT_A_MAPPING}5",
                 id="rows-and-a-number"),
]

#: Absent (None), null (`members:` alone) and `[]`: no members, not a fault.
CONTROLS = [pytest.param(None, id="absent"), pytest.param("", id="null"),
            pytest.param("[]", id="empty-list")]

#: Each verb's run, the real one and the dry one, which refuse alike.
RUNS = [pytest.param((), id="real-run"),
        pytest.param(("--dry-run",), id="dry-run")]

#: The count bootstrap and siblings print first, after the holder's path.
NO_MEMBERS = f"{chr(0x2014)} 0 member(s)\n"


def members_are(root, spelled) -> None:
    """`members: <spelled>` in place of the block, committed, as a person
    commits a hand edit before a verb (`_checked_manifest_committed`, #684):
    no block at all for None, `members:` alone for `""`, and the fixture's
    rows followed by `- 5` for `ROWS_AND_A_NUMBER`. As BYTES, as
    `tests/test_validate_family_duplicates.py` edits it, so Windows does not
    rewrite the whole manifest with CRLF."""
    path = root / MANIFEST
    text = path.read_bytes().decode("utf-8")
    at = text.index(MEMBERS_BLOCK)
    if spelled is ROWS_AND_A_NUMBER:
        text += "  - 5\n"
    elif spelled is None:
        text = text[:at + 1]
    else:
        text = (text[:at] + "\nmembers:" + (f" {spelled}" if spelled else "")
                + "\n")
    path.write_bytes(text.encode("utf-8"))
    git("commit", "-q", "-m", "members, by hand", "--", MANIFEST, cwd=root)


def is_an_entry(said: str) -> bool:
    """Is the sentence about an entry of the list, not about `members:`?"""
    return said.startswith(NOT_A_MAPPING)


def unreadable(root, said: str) -> str:
    """`family-members-unreadable` and its detail, path and all."""
    return f"family-members-unreadable: {root.resolve() / MANIFEST}: {said}"


def no_traceback(result) -> None:
    """No traceback, and no ESC: a value is spelled where it is said."""
    out = result.stdout + result.stderr
    assert "Traceback" not in out, out
    assert "\x1b" not in out, out


# --- the doctor --------------------------------------------------------------

def doctors_rows(root) -> tuple:
    """The doctor's `--json` run of `root`, and its rows by id."""
    result = doctor(REPO, root, "--json")
    no_traceback(result)
    return result, rows_of(result)


def waiting_reason(root, said: str) -> str:
    """The `members` row's sentence: the gate's words, as the `family` row
    quotes them, inside the row's own."""
    if is_an_entry(said):
        what, quoted = ("holds an entry that is not a mapping",
                        f"member-row: {said}")
    else:
        what, quoted = "is not a list", unreadable(root, said)
    return (f"family.yaml's `members:` {what} ({quoted}), so no member is "
            "checked against its pin; the `family` row's command names the "
            "fault")


@pytest.mark.parametrize("spelled,said", CASES)
def test_the_doctors_members_row_says_the_sentence_and_waits(holder, spelled,
                                                             said):
    """`5` ended the report in a `TypeError`, and the rest made the row an
    `ok`, "no members yet" or the rows beside the entry "mounted at their
    pins", under the `family` row that says the fault. The row is now `n/a`,
    says the sentence and names the `family` row it waits on."""
    members_are(holder, spelled)
    result, rows = doctors_rows(holder)
    assert result.returncode == 1, result.stdout
    assert rows["family"]["status"] == "FINDING", rows["family"]
    row = rows["members"]
    assert row["status"] == "n/a", row
    assert row["reason"] == waiting_reason(holder, said), row
    assert row["next"] is None, row
    assert row["detail"] == {"members": [], "waits_on": "family"}, row


# --- family.py add, bump and remove ------------------------------------------

def verb_args(family: dict, verb: str) -> tuple[str, ...]:
    """The member each verb names: the spare for `add`, a real one for the
    other two, and for `bump` a commit that member has."""
    if verb == "add":
        return ("--member", f"{ORG}/{SPARE}",
                "--local-remote-dir", str(family["remotes"]))
    if verb == "bump":
        first = git("rev-parse", "HEAD~1",
                    cwd=family["work"] / "IRRS").stdout.strip()
        return ("--member", "IRRS", "--to", first)
    return ("--member", "IRRS")


def held(root) -> tuple:
    """What a refused verb leaves alone: `family.yaml`'s bytes, HEAD, and
    everything `git status` says."""
    return ((root / MANIFEST).read_bytes(),
            git("rev-parse", "HEAD", cwd=root).stdout,
            git("status", "--porcelain", "--untracked-files=all",
                cwd=root).stdout)


#: What the three verbs say under the refusal.
VERB_REMEDY = (
    "Remediation: `members:` is the list of rows `family.py add` writes, one "
    "mapping per member, and this tool rewrites no `members:` it cannot read. "
    "The holder's own `scripts/validate-family.py` names this same fault: "
    "mend `family.yaml` by hand, commit it (`git commit -- family.yaml`), "
    "then run the same command again.")


@pytest.mark.parametrize("extra", RUNS)
@pytest.mark.parametrize("verb", ("add", "bump", "remove"))
@pytest.mark.parametrize("spelled,said", CASES)
def test_add_bump_and_remove_refuse_it_and_leave_the_holder_as_it_was(
        family, holder, spelled, said, verb, extra):
    """`5` was a `TypeError`; the others were `member-unknown` of a member
    mounted there, or `family-members-unrecognised` of a line that is there;
    and the rows beside an entry `5` were rewritten without it and
    committed, exit 0. Each verb now refuses in `Family.open`, both runs
    alike, and the holder is as it was."""
    members_are(holder, spelled)
    before = held(holder)
    result = run_script(FAMILY, verb, "--family-root", str(holder),
                        *verb_args(family, verb), *extra)
    no_traceback(result)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == "", result.stdout
    assert result.stderr == (f"REFUSED {unreadable(holder, said)}\n"
                             f"{VERB_REMEDY}\n")
    assert held(holder) == before


# --- bootstrap.py and siblings.py, the holder's own copies -------------------

def bootstrap(root):
    """`make bootstrap`'s script, with nothing fetched or made: the count
    it prints first, and its refusal, come before either step."""
    return run_script(root / "scripts" / "bootstrap.py", "--no-fetch",
                      "--skip-members", cwd=root)


def siblings_dry_run(root):
    """`make siblings`' script, placing nothing."""
    return siblings(root, "--dry-run")


def family_siblings(root):
    """`family.py siblings`, which runs the holder's own `siblings.py`."""
    return run_script(FAMILY, "siblings", "--family-root", str(root),
                      "--dry-run")


#: The holder's `members_of` readers, each as a person runs it.
MEMBERS_OF_READERS = [
    pytest.param(bootstrap, id="bootstrap"),
    pytest.param(siblings_dry_run, id="siblings"),
    pytest.param(family_siblings, id="family-siblings"),
]


@pytest.mark.parametrize("reader", MEMBERS_OF_READERS)
@pytest.mark.parametrize("spelled,said", CASES)
def test_bootstrap_and_siblings_refuse_it_before_anything_is_placed(
        family, tmp_path, spelled, said, reader):
    """`5` was a `TypeError` in `members_of`; the others were "0
    member(s)", "family bootstrap ok" and "no members declared", exit 0, and
    the rows beside an entry `5` were counted and the entry unsaid. Each
    now refuses, exit 2, with nothing printed before it."""
    root = holder_in(family, tmp_path / NAME)
    members_are(root, spelled)
    result = reader(root)
    no_traceback(result)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == "", result.stdout
    assert result.stderr == f"REFUSED {unreadable(root, said)}\n"


# --- validate-family.py --no-members -----------------------------------------

@pytest.mark.parametrize("spelled,said", CASES)
def test_the_gate_without_its_members_says_the_sentence(holder, spelled,
                                                        said):
    """`--no-members`, what CI runs when the members could not be checked
    out, refused a `members:` that is not a list already, and made the
    `member-row` finding only past its own return: so it counted `5` as a
    member, and beside the fixture's rows said `family ok`, exit 0."""
    members_are(holder, spelled)
    result = validate(holder, "--no-members")
    no_traceback(result)
    if not is_an_entry(said):
        assert result.returncode == 2, result.stdout + result.stderr
        assert result.stderr == f"REFUSED {unreadable(holder, said)}\n"
        return
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"FINDING member-row: {said}" in findings(result), result.stderr


@pytest.mark.parametrize("extra", [pytest.param((), id="members-checked"),
                                   pytest.param(("--no-members",),
                                                id="no-members")])
def test_the_gate_says_an_entry_once_in_either_mode(holder, extra):
    """The finding moved, it was not added: with the members checked as
    without, the rows beside the entry pass and it is the one finding."""
    members_are(holder, ROWS_AND_A_NUMBER)
    result = validate(holder, *extra)
    assert result.returncode == 1, result.stdout + result.stderr
    assert findings(result) == [f"FINDING member-row: {NOT_A_MAPPING}5"]


# --- the controls: no members is not a fault ---------------------------------

@pytest.mark.parametrize("spelled", CONTROLS)
def test_the_doctor_still_calls_no_members_an_empty_family(holder, spelled):
    members_are(holder, spelled)
    _, rows = doctors_rows(holder)
    row = rows["members"]
    assert row["status"] == "ok", row
    assert row["reason"] == (
        "no members yet: a family with none is empty, not wrong"), row
    assert "waits_on" not in row["detail"], row


@pytest.mark.parametrize("reader", MEMBERS_OF_READERS)
@pytest.mark.parametrize("spelled", CONTROLS)
def test_bootstrap_and_siblings_still_run_over_no_members(family, tmp_path,
                                                          spelled, reader):
    root = holder_in(family, tmp_path / NAME)
    members_are(root, spelled)
    result = reader(root)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"({root.resolve()}) {NO_MEMBERS}" in result.stdout, result.stdout
    assert "family-members-unreadable" not in result.stderr, result.stderr


@pytest.mark.parametrize("extra", RUNS)
@pytest.mark.parametrize("verb", ("bump", "remove"))
@pytest.mark.parametrize("spelled", CONTROLS)
def test_bump_and_remove_still_call_the_member_unknown(family, holder,
                                                       spelled, verb, extra):
    members_are(holder, spelled)
    result = run_script(FAMILY, verb, "--family-root", str(holder),
                        *verb_args(family, verb), *extra)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(
        f"REFUSED member-unknown: IRRS is not a member of {NAME}\n"), \
        result.stderr


@pytest.mark.parametrize("extra", RUNS)
@pytest.mark.parametrize("spelled", CONTROLS)
def test_add_still_mounts_into_no_members_or_names_a_missing_block(
        family, holder, spelled, extra):
    """Null and `[]` take the member, exit 0; with no block at all `add`
    has no line to rewrite and says so, as it always did."""
    members_are(holder, spelled)
    result = run_script(FAMILY, "add", "--family-root", str(holder),
                        *verb_args(family, "add"), *extra)
    if spelled is None:
        assert result.returncode == 2, result.stdout + result.stderr
        assert result.stderr.startswith(
            "REFUSED family-members-unrecognised: "), result.stderr
        return
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("spelled", CONTROLS)
def test_the_gate_without_its_members_finds_no_row_fault(holder, spelled):
    """Its findings are the fixture's two mounts, which no row names, true
    of a holder whose rows were taken out by hand; it refuses nothing, and
    no finding is about a row."""
    members_are(holder, spelled)
    result = validate(holder, "--no-members")
    assert result.returncode == 1, result.stdout + result.stderr
    codes = {line.split(":")[0] for line in findings(result)}
    assert "FINDING member-row" not in codes, result.stderr
    assert "family-members-unreadable" not in result.stderr, result.stderr
