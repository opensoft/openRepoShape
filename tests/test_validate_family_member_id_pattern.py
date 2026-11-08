# SPDX-License-Identifier: Apache-2.0
"""`validate-family.py` asks whether each member row's `id:` is a project id,
and with the members checked each member's own `project.yaml` `id:` too
(#1204, the follow-up of #1166's `member-bad-id`).

THE DEFECT, measured on #1227's head merged onto main `81eaf757`
(`ccc2c2d2`, Python 3.12.3, git 2.43.0). `PROJECT_ID_RE` was asked of one
id only, the family's own. A row's `id:` met two checks and neither is a
pattern: the mounted `project.yaml` compared with it as text
(`member-id-mismatch`), and `_check_member_ids_unique`. So:

- under `--no-members`, the run a private family's CI falls back to, a row
  `id:` of `"irrs\\n"`, `"irrs\\r"`, `"IRRS Capital"` or `"-x"` was `family
  ok`, exit 0; with the members checked each was `member-id-mismatch`, of a
  row that only had to copy the member's id;
- the holder a `family.py add` older than #1166 wrote for a member whose own
  `project.yaml` reads `id: "irqs\\n"`, its row recording the same, was
  `family ok` in every mode: the two compared equal.

THE RULE NOW. `member-id-malformed`, a finding of its own: of a row's `id:`
in every mode, since it reads `family.yaml` alone, and of the mounted
`project.yaml`'s `id:`, asked exactly as `family.py add` asks it, so the gate
refuses the members `add` refuses (`member-bad-id`) and none it would pin.
Where either id is malformed, `member-id-mismatch` is not said as well. Each
remedy is a `bump`, typed as printed below: to the commit the row pins, which
writes the row from the member's own `project.yaml` and leaves the pin, or to
the commit that mends that file. A number reads as its digits, as the
identity check always compared it, so a row a holder written before #259
keeps as `id: 2026` passes; `null` and no `id:` are `member-id-absent`'s, as
before.

The family is `tests/test_family.py`'s offline one: members scaffolded into
local bare repositories, no network and no GitHub, a `gh` stub on PATH.
"""

from __future__ import annotations

import os
import re
import shlex

import pytest

from conftest import REPO, git, run_script
from repo_shape import PYTHON, double_quoted, tree_digest
#: The family fixture, its names and the helpers that own a hand edit and a
#: member whose own `id:` is written by hand, imported from the modules that
#: own them rather than rebuilt.
from test_family import (  # noqa: F401
    ORG, SPARE, family, family_module, holder, manifest, validate,
)
from test_family_tracking_branch import on_main  # noqa: F401
from test_validate_family_branch_step import BRANCH_LEFT
from test_value_pattern_line_break import (
    ID_PATTERN, a_member_whose_id_is, findings, rewritten,
)

LF = chr(10)
CR = chr(13)

#: IRRS's row `id:` line, as the fixture's `add` wrote it.
IRRS_ID = "    id: irrs\n"

#: Table 3's four values that the pattern refuses, as the reader reads them.
REFUSED = [
    pytest.param("irrs" + LF, id="line-feed"),
    pytest.param("irrs" + CR, id="carriage-return"),
    pytest.param("IRRS Capital", id="space"),
    pytest.param("-x", id="leading-dash"),
]


def with_row_id(holder, spelled: str) -> None:
    """`family.yaml` with IRRS's `id:` written as `spelled`, as a hand edit
    writes it."""
    rewritten(holder / "family.yaml", IRRS_ID, f"    id: {spelled}\n")


def row_finding(project: str, value) -> str:
    """How a row's finding starts, for `value` as the reader read it."""
    return (f"FINDING member-id-malformed: {project}: the row records id "
            f"{value!r}, which does not match {ID_PATTERN}, so it names no "
            "project.")


def source_finding(project: str, value) -> str:
    """How a mounted member's own finding starts."""
    return (f"FINDING member-id-malformed: members/{project}/project.yaml: "
            f"the member's own `id:` is {value!r}, which does not match "
            f"{ID_PATTERN}, so the tree mounted at members/{project} is no "
            "project, and `family.py add` and `bump` refuse it as "
            "`member-bad-id`.")


def commands(line: str) -> list[str]:
    """The `git -C` switch and the `family.py` line a finding names, in
    order."""
    return [command for command in re.findall(r"`([^`]*)`", line)
            if command.startswith(("git -C", PYTHON))]


def row_of(holder, project: str) -> dict:
    return next(row for row in manifest(holder)["members"]
                if row["project"] == project)


def mounted_as_add_wrote_it(family, holder, tmp_path, row_id: str) -> None:
    """IRQS mounted from a copy of its remote whose `project.yaml` reads `id:
    "irqs\\n"` (`a_member_whose_id_is`, which leaves its work clone at
    `tmp_path / "edit"`), and its row written as a `family.py add` older
    than #1166 wrote it, with its `id:` spelled `row_id` (#1166 refuses that
    member now, so the row is written by hand). Committed, the pin and the
    digest those of the mount: the id is the only thing wrong."""
    remotes = a_member_whose_id_is(family, tmp_path, 'id: "irqs\\n"\n')
    git("-c", "protocol.file.allow=always", "submodule", "add", "-q", "--",
        str(remotes / f"{SPARE}.git"), f"members/{SPARE}", cwd=holder)
    mounted = holder / "members" / SPARE
    commit = git("rev-parse", "HEAD", cwd=mounted).stdout.strip()
    text = (holder / "family.yaml").read_text(encoding="utf-8")
    (holder / "family.yaml").write_bytes((text.rstrip("\n") + "\n" + "\n".join([
        f"  - project: {SPARE}",
        f"    id: {row_id}",
        f"    repository: {ORG}/{SPARE}",
        f"    path: members/{SPARE}",
        "    pin:",
        "      revision_kind: commit",
        f'      commit: "{commit}"',
        "      digest_algorithm: sha256",
        "      digest_definition: sorted-ls-tree-r-v1",
        f'      tree_sha256: "{tree_digest(mounted, commit)}"',
    ]) + "\n").encode("utf-8"))
    git("add", "--", ".gitmodules", f"members/{SPARE}", "family.yaml",
        cwd=holder)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "Mount IRQS as add mounted it before #1166", cwd=holder)


# --- a row's `id:`, under --no-members ---------------------------------------

@pytest.mark.parametrize("value", REFUSED)
def test_a_row_id_the_pattern_refuses_is_found_under_no_members(holder,
                                                                value):
    """THE ISSUE'S ROW, table 3: each was `family ok`, exit 0. It reads
    `family.yaml` alone, so the run that skips the members finds it, and
    it is the one finding."""
    with_row_id(holder, double_quoted(value))
    result = validate(holder, "--no-members")
    assert result.returncode == 1, result.stdout + result.stderr
    found = findings(result.stderr)
    assert len(found) == 1, result.stderr
    assert found[0].startswith(row_finding("IRRS", value) + " "), found[0]
    assert "member(s) SKIPPED (--no-members)" in result.stdout


@pytest.mark.parametrize("spelled", ['"0"', "irrs"], ids=["zero", "irrs"])
def test_a_well_formed_row_id_is_family_ok_under_no_members(holder, spelled):
    """Table 3's controls: `0` is an id the pattern takes, and `irrs` is the
    fixture's own. Each is `family ok`, before and after."""
    with_row_id(holder, spelled)
    result = validate(holder, "--no-members")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1].startswith("family ok: "), \
        result.stdout


@pytest.mark.parametrize("extra", [(), ("--no-members",), ("--pins",)],
                         ids=["members", "no-members", "pins"])
def test_the_fixture_is_family_ok_in_every_mode(holder, extra):
    """The well-formed fixture, untouched: no new finding in any mode."""
    result = validate(holder, *extra)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "member-id-malformed" not in result.stderr


# --- a row's `id:`, with the members checked --------------------------------

@pytest.mark.parametrize("value", REFUSED)
def test_with_members_checked_it_is_the_one_finding_not_a_mismatch(holder,
                                                                   value):
    """With the members checked each value was `member-id-mismatch`, which
    tells a person to copy the member's id and names no command. It is the
    row's own finding now, in `--pins` too, and only that: one finding for
    one fault."""
    with_row_id(holder, double_quoted(value))
    for extra in ((), ("--pins",)):
        result = validate(holder, *extra)
        assert result.returncode == 1, result.stdout + result.stderr
        found = findings(result.stderr)
        assert len(found) == 1, result.stderr
        assert found[0].startswith(row_finding("IRRS", value)), found[0]


def test_a_well_formed_row_id_that_is_not_the_members_is_still_a_mismatch(
        holder):
    """The control of the one above: `0` is an id, so `member-id-mismatch`
    stays its finding, word for word."""
    with_row_id(holder, '"0"')
    result = validate(holder)
    assert result.returncode == 1, result.stdout + result.stderr
    assert findings(result.stderr) == [
        "FINDING member-id-mismatch: members/IRRS: project.yaml declares id "
        "'irrs' but family.yaml records '0' for IRRS. The project's own "
        "manifest is the source; this row is a pin of it."], result.stderr


# --- a row `id:` that is not a string ---------------------------------------

@pytest.mark.parametrize("spelled", ["true", "1.5", "-3", "[irrs]",
                                     "{irrs: 1}"],
                         ids=["bool", "float", "negative", "list", "mapping"])
def test_a_row_id_whose_text_is_no_id_is_found(holder, spelled):
    """THE DECISION FOR A VALUE THAT IS NOT A STRING: it is asked as its
    text, `str()`, the text the identity check compares, and none of these
    reads as an id. Named as the reader read it."""
    with_row_id(holder, spelled)
    value = row_of(holder, "IRRS")["id"]
    assert not isinstance(value, str), value
    result = validate(holder, "--no-members")
    assert result.returncode == 1, result.stdout + result.stderr
    found = findings(result.stderr)
    assert len(found) == 1, result.stderr
    assert found[0].startswith(row_finding("IRRS", value)), found[0]


def test_a_row_id_that_reads_as_a_number_is_its_digits(holder):
    """A holder written before #259 keeps `id: 2026` for a member scaffolded
    with `--id 2026`, which the reader reads as a number; `family.py`'s
    `_member_id` says the validator passes it, and it still does."""
    with_row_id(holder, "2026")
    assert row_of(holder, "IRRS")["id"] == 2026
    result = validate(holder, "--no-members")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("spelled", ["null", None], ids=["null", "no-id"])
def test_a_row_with_no_id_is_still_member_id_absent_alone(holder, spelled):
    """`id: null` reads as no `id:`, and a row with none is
    `member-id-absent`'s where it was, members checked, and nothing under
    `--no-members`, as before."""
    if spelled is None:
        rewritten(holder / "family.yaml", IRRS_ID, "")
    else:
        with_row_id(holder, spelled)
    assert validate(holder, "--no-members").returncode == 0
    result = validate(holder)
    assert result.returncode == 1, result.stdout + result.stderr
    assert findings(result.stderr) == [
        "FINDING member-id-absent: IRRS: the row records no `id:`, so nothing "
        "checks that the tree mounted here is the project this row claims"], \
        result.stderr


# --- a mounted member's own `id:` --------------------------------------------

def test_the_holder_add_wrote_before_1166_is_refused_in_every_mode(
        family, holder, tmp_path):
    """THE ISSUE'S HOLDER. Its row and its member's own `project.yaml` both
    read `id: "irqs\\n"`, so the two compared equal and every mode was
    `family ok`, exit 0. The row is found in every mode; with the members
    checked, the member's own file too, named as the source."""
    mounted_as_add_wrote_it(family, holder, tmp_path,
                            double_quoted("irqs" + LF))
    alone = validate(holder, "--no-members")
    assert alone.returncode == 1, alone.stdout + alone.stderr
    found = findings(alone.stderr)
    assert len(found) == 1, alone.stderr
    assert found[0].startswith(row_finding(SPARE, "irqs" + LF)), found[0]
    for extra in ((), ("--pins",)):
        result = validate(holder, *extra)
        assert result.returncode == 1, result.stdout + result.stderr
        found = findings(result.stderr)
        assert len(found) == 2, result.stderr
        assert found[0].startswith(row_finding(SPARE, "irqs" + LF)), found[0]
        assert found[1].startswith(source_finding(SPARE, "irqs" + LF)), \
            found[1]
        assert "member-id-mismatch" not in result.stderr


@pytest.mark.parametrize("row_id", [double_quoted("irqs" + LF), "irqs"],
                         ids=["equal-to-its-row", "row-well-formed"])
def test_a_mounted_member_whose_own_id_is_malformed_is_found(
        family, holder, tmp_path, row_id):
    """A mounted member whose own `id:` is malformed is found whatever its
    row says: equal to it (both refused, no mismatch), or a well-formed
    `irqs`, which was `member-id-mismatch`, a finding that told the person
    to copy the malformed id into the row. Its text names the file as the
    source and the `bump` that pins it once mended."""
    mounted_as_add_wrote_it(family, holder, tmp_path, row_id)
    result = validate(holder)
    assert result.returncode == 1, result.stdout + result.stderr
    found = findings(result.stderr)
    own = [line for line in found if line.startswith(
        "FINDING member-id-malformed: members/")]
    assert len(own) == 1, result.stderr
    assert own[0].startswith(source_finding(SPARE, "irqs" + LF) + " "), own[0]
    assert "That file is the source every row pins" in own[0]
    argv = shlex.split(commands(own[0])[1])
    assert argv[:3] == [PYTHON, "scripts/family.py", "bump"], argv
    assert os.path.samefile(argv[argv.index("--family-root") + 1], holder)
    assert argv[argv.index("--member") + 1:] == [SPARE, "--to", "<commit>"]
    assert own[0].endswith(". " + BRANCH_LEFT), own[0]
    assert "member-id-mismatch" not in result.stderr
    assert len(found) == (2 if row_id != "irqs" else 1), result.stderr


# --- the remedies, typed as printed ------------------------------------------

def test_the_rows_remedy_runs_as_printed_from_the_tracking_branch(on_main):
    """A row `id:` written by hand and committed, on the tracking branch,
    where a person stands after `init`. The finding's two commands, typed as
    printed from a checkout of openRepoShape: the switch makes a branch,
    and the `bump` to the commit the row pins writes the row's `id:` from
    the member's own `project.yaml`, the pin where it was. The gate is
    green after it, in every mode."""
    holder = on_main
    with_row_id(holder, double_quoted("irrs" + LF))
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam",
        "A row id written by hand", cwd=holder)
    pinned = row_of(holder, "IRRS")["pin"]["commit"]
    found = validate(holder, "--no-members")
    assert found.returncode == 1, found.stdout + found.stderr
    line = found.stderr.split("FINDING member-id-malformed: ",
                              1)[1].splitlines()[0]
    assert line.endswith(". " + BRANCH_LEFT), line
    switch, bump = commands(line)
    argv = shlex.split(bump)
    assert argv[:3] == [PYTHON, "scripts/family.py", "bump"], bump
    assert argv[argv.index("--member") + 1] == "IRRS", bump
    assert argv[argv.index("--to") + 1] == pinned, bump
    assert os.path.samefile(argv[argv.index("--family-root") + 1], holder)
    git(*shlex.split(switch)[1:], cwd=holder.parent)
    done = run_script(REPO / argv[1], *argv[2:], cwd=REPO)
    assert done.returncode == 0, done.stdout + done.stderr
    row = row_of(holder, "IRRS")
    assert (row["id"], row["pin"]["commit"]) == ("irrs", pinned)
    assert git("status", "--porcelain", cwd=holder).stdout == ""
    for extra in ((), ("--no-members",)):
        assert validate(holder, *extra).returncode == 0


def test_the_members_remedy_pins_the_mended_commit_as_printed(
        family, holder, tmp_path):
    """The member's own `id:` mended in its own repository, then the
    finding's two commands typed as printed, `<commit>` the mended one: the
    `bump` pins it and writes the row's `id:` from it, and the gate is
    green."""
    mounted_as_add_wrote_it(family, holder, tmp_path,
                            double_quoted("irqs" + LF))
    found = validate(holder)
    line = found.stderr.split(
        f"FINDING member-id-malformed: members/{SPARE}/project.yaml: ",
        1)[1].splitlines()[0]
    switch, bump = commands(line)
    work = tmp_path / "edit"
    rewritten(work / "project.yaml", 'id: "irqs\\n"\n', 'id: "irqs"\n')
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam",
        "The id, mended", cwd=work)
    git("push", "-q", "origin", "HEAD", cwd=work)
    mended = git("rev-parse", "HEAD", cwd=work).stdout.strip()
    git(*shlex.split(switch)[1:], cwd=holder.parent)
    argv = shlex.split(bump.replace("<commit>", mended))
    done = run_script(REPO / argv[1], *argv[2:], cwd=REPO)
    assert done.returncode == 0, done.stdout + done.stderr
    row = row_of(holder, SPARE)
    assert (row["id"], row["pin"]["commit"]) == ("irqs", mended)
    assert validate(holder).returncode == 0


# --- `add` and the gate ask one question ------------------------------------

#: `(the id, whether it is malformed)`: table 3's values and its controls,
#: and the edges of the pattern either side.
ONE_QUESTION = [
    pytest.param("irrs" + LF, True, id="line-feed"),
    pytest.param("irrs" + CR, True, id="carriage-return"),
    pytest.param("IRRS Capital", True, id="space"),
    pytest.param("-x", True, id="leading-dash"),
    pytest.param("", True, id="empty"),
    pytest.param(" irrs", True, id="leading-space"),
    pytest.param("IRRS", True, id="capitals"),
    pytest.param("irrs.docs", True, id="dot"),
    pytest.param("0", False, id="zero"),
    pytest.param("irrs", False, id="irrs"),
    pytest.param("irrs-2", False, id="hyphen"),
    pytest.param("9-lives", False, id="digit-first"),
]


@pytest.mark.parametrize("value, malformed", ONE_QUESTION)
def test_add_refuses_exactly_the_ids_the_holders_own_validator_finds(
        holder, tmp_path, value, malformed):
    """THE GATE'S OWN ANSWER, in `test_family_add_member_id.py`'s way. For
    each id, `add`'s question (`_read_member_project`, of a `project.yaml`
    recording it, no clone) and the holder's `validate-family.py
    --no-members` over IRRS's row recording it: `add` refuses
    `member-bad-id` exactly when the gate finds `member-id-malformed`, and
    both exactly when the id is malformed."""
    member = tmp_path / "member"
    member.mkdir()
    (member / "project.yaml").write_bytes(
        ("schema_version: 1\nkind: project-manifest\n"
         f"id: {double_quoted(value)}\nname: IRRS\n").encode("utf-8"))
    module = family_module()
    try:
        module._read_member_project(member, "IRRS", f"{ORG}/IRRS")
    except module.Refusal as exc:
        assert exc.code == "member-bad-id", str(exc)
        refused = True
    else:
        refused = False
    with_row_id(holder, double_quoted(value))
    result = validate(holder, "--no-members")
    found = "FINDING member-id-malformed: IRRS: " in result.stderr
    assert (refused, found) == (malformed, malformed), result.stderr
    assert result.returncode == (1 if malformed else 0), result.stderr
