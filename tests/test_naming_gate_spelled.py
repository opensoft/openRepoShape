# SPDX-License-Identifier: Apache-2.0
"""The naming gate prints every name through `repo_shape.spelled` (#1267, the
follow-up of #1202's NIT 2).

THE DEFECT, measured on #1266's head 09697e9c5 (Python 3.12.3, git 2.43.0).
With #1266 a name that ends in a line feed is refused `naming-unclassified`,
but `validate-repository-naming.py` printed the name RAW:

- stdout: `'  Atlas'`, then `'                           NO FAMILY'` on the next
  line, so the row of the table split in two; a name with an inner line feed
  split the same way, and a name with an ESC byte put the byte on the
  terminal;
- stderr: `FINDING naming-unclassified: Atlas`, then a blank line, which reads
  exactly as the finding for a valid `Atlas`.

THE RULE NOW. A name the gate prints is `repo_shape.spelled`: a line feed is
`\\n`, an ESC is `\\x1b`, and a name without such a character prints as it
did. Ten places print a name or a sentence that quotes it, and each has a row:

- the plain listing (`_print_classification`), whose column is worked out from
  the SPELLED name, so every row keeps its label where a plain name's is;
- `--explain`: the NO FAMILY header, the header of a classified name, the
  `[a CLAIM: ...]` note (the referents it derives from the name), and the
  WARNING and OVERLAP sentences, which quote the name;
- the `WARNING <name>: <sentence>` line on stderr;
- the role finding and the broken-chain finding of `--project`, whose
  sentence quotes the name, so the WHOLE line is spelled;
- the `naming-unclassified` finding.

THE ROWS. The shipped contract classifies none of the three names (#1202), so
the table, the `--explain` header and the finding are asked of it. Four more
names pin `spelled` ITSELF and not only that the gate calls it, so that a
rival escaper fails a row: a name with a CR, which a gate that escaped just a
line feed and an ESC would print raw; a name with a backslash, which prints as
it is and which `repr` would double; a name with U+202E (a right-to-left
override, a bidirectional control that is no C0 or C1 control, which a gate
that escaped controls only, or a table of LF, CR and ESC, would print raw); and
a name with U+200D (a zero-width joiner, which `spelled` leaves as it is and
which a gate that escaped every character `str.isprintable` refuses would
write as `\\u200d`). The first three are asked of the table and the finding.
The joiner is asked of the finding only: it takes no column, so a table that
pads by display width would not keep its label where a plain name's is. The
other sites print a CLASSIFIED name,
which only a fork whose patterns take an ESC and a line feed can have, so
those rows read the shipped contract with its character classes widened
(`loosened`). A descendant name ends in its product, which the direct pin
reads, so the control is in its stem; the three kinds are asked wherever the
name's end is free.

No network and no GitHub: the policy is read in process by a script that runs
offline.
"""

from __future__ import annotations

import pytest

from conftest import REPO, run_script
from test_value_pattern_line_break import findings

VALIDATOR = REPO / "scripts" / "validate-repository-naming.py"
POLICY_PATH = REPO / "contracts" / "repository-naming.yaml"
#: A line feed, an ESC and a CR, as the shell would hand them to argv.
LF = chr(10)
ESC = chr(27)
CR = chr(13)
#: The arrow the chain sentences join links with.
ARROW = chr(0x2192)

#: `(raw name, how the gate must print it)`: the three names of the issue.
ENDS_IN_LF = ("Atlas" + LF, "Atlas\\n")
INNER_LF = ("At" + LF + "las", "At\\nlas")
WITH_ESC = ("At" + ESC + "[31mlas", "At\\x1b[31mlas")
NAMES = [pytest.param(*ENDS_IN_LF, id="ends-in-lf"),
         pytest.param(*INNER_LF, id="inner-lf"),
         pytest.param(*WITH_ESC, id="esc")]

#: Names that pin `spelled` itself. A gate that escaped only a line feed and
#: an ESC would print the CR raw, and one that spelled with `repr` would
#: double the backslash: `spelled` writes a CR as `\\r` and leaves a backslash
#: as it is (the line feed beside it is still `\\n`), so the name holding it
#: is not doubled.
ENDS_IN_CR = ("Atlas" + CR, "Atlas\\r")
WITH_BACKSLASH = ("At\\las" + LF, "At\\las\\n")
#: U+202E (RLO) is a bidirectional control that reorders the text around it, so
#: a name holding it can read as another name. `spelled` writes it as
#: `\\u202e`, and a rival that escaped only the C0 controls, only the category
#: Cc, or only LF, CR and ESC would print it raw. It is ASCII once spelled, so
#: the table row can hold it too.
RLO = chr(0x202E)
WITH_RLO = ("At" + RLO + "las", "At\\u202elas")
SPELLED_ITSELF = [pytest.param(*ENDS_IN_CR, id="ends-in-cr"),
                  pytest.param(*WITH_BACKSLASH, id="backslash"),
                  pytest.param(*WITH_RLO, id="rlo")]

#: U+200D (ZWJ) is a format character `spelled` leaves as it is, so a person's
#: emoji sequence or Indic name reads as typed; a rival built on
#: `str.isprintable` would write it as `\\u200d`. It takes no column, so only
#: the finding is asked of it, never the table (a table padded by display width
#: would not keep its label in the plain rows' column).
ZWJ = chr(0x200D)
KEPT_AS_IT_IS = [pytest.param("At" + ZWJ + "las", "At" + ZWJ + "las",
                              id="zwj")]


def spelled_of(raw: str) -> str:
    """How `raw` must be printed, worked out by hand and not by the library
    under test: the two controls of the rows are written as Python spells
    them."""
    return raw.replace(LF, "\\n").replace(ESC, "\\x1b")


def lines_after_the_header(stdout: str) -> list[str]:
    """What `--explain` prints after a name's header line; each starts with
    four spaces. A name that split its header would leave a line that does
    not."""
    return stdout.splitlines()[1:]


def not_indented(lines: list[str]) -> list[str]:
    return [line for line in lines if not line.startswith("    ")]


@pytest.fixture(scope="module")
def unclassified_tail() -> list[str]:
    """The two lines after the finding, as a plain unclassified name gets
    them."""
    return run_script(VALIDATOR, "Atlas_spec").stderr.splitlines()[1:]


@pytest.fixture(scope="module")
def plain_explain() -> list[str]:
    """The lines `--explain` prints for a plain name that matches no family
    after its header."""
    return lines_after_the_header(
        run_script(VALIDATOR, "--explain", "Atlas_spec").stdout)


def loosened() -> str:
    """The shipped contract with every character class `[A-Za-z0-9]` widened
    by an ESC, a line feed and `[` (a YAML double-quoted `\\\\x1b` is the
    regex `\\x1b`), so a fork's pattern takes the names of the rows."""
    text = POLICY_PATH.read_text(encoding="utf-8")
    assert text.count("A-Za-z0-9]") == 12, "fixture drift: the contract moved"
    return text.replace("A-Za-z0-9]", r"A-Za-z0-9\\x1b\\n\\[]")


@pytest.fixture(scope="module")
def loose(tmp_path_factory) -> str:
    """The path of that fork's policy, as the `--policy` value."""
    path = tmp_path_factory.mktemp("loose") / "repository-naming.yaml"
    path.write_text(loosened(), encoding="utf-8")
    return str(path)


# --- the shipped contract: the table, the header and the finding --------------

@pytest.mark.parametrize("raw, said", NAMES + SPELLED_ITSELF + KEPT_AS_IT_IS)
def test_the_finding_prints_the_spelled_name_on_one_line(raw, said,
                                                         unclassified_tail):
    """THE ISSUE'S ROW: on 09697e9c5 `Atlas` plus a line feed gave a blank
    line after `FINDING naming-unclassified: Atlas`, and an ESC reached the
    terminal. The last four names pin what `spelled` writes: `\\r`, a
    backslash as it is, a right-to-left override as `\\u202e`, and a
    zero-width joiner as it is."""
    result = run_script(VALIDATOR, raw)
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stderr.splitlines() == [
        f"FINDING naming-unclassified: {said}", *unclassified_tail]


@pytest.mark.parametrize("raw, said", NAMES + SPELLED_ITSELF)
def test_the_table_has_one_row_for_the_name_with_its_label_in_place(raw, said):
    """The row is `  <name padded to 32> NO FAMILY`, the width worked out
    from the SPELLED name: the escape is longer than the byte it writes, so a
    width taken from the raw name leaves the label one column (or three) off
    the plain rows'."""
    result = run_script(VALIDATOR, raw)
    assert result.stdout == f"  {said:<32} NO FAMILY\n"


def test_a_run_of_all_three_and_a_plain_name_has_four_rows_in_line():
    """The table keeps one row per name, and the labels stand in one column."""
    raws = [ENDS_IN_LF[0], INNER_LF[0], WITH_ESC[0]]
    result = run_script(VALIDATOR, *raws, "Atlas")
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines() == [
        f"  {ENDS_IN_LF[1]:<32} NO FAMILY",
        f"  {INNER_LF[1]:<32} NO FAMILY",
        f"  {WITH_ESC[1]:<32} NO FAMILY",
        f"  {'Atlas':<32} project-leg/assembly"]
    assert findings(result.stderr) == [
        "FINDING naming-unclassified: "
        f"{ENDS_IN_LF[1]}, {INNER_LF[1]}, {WITH_ESC[1]}"]


def test_a_plain_valid_name_prints_exactly_as_it_did():
    """The control: no name without a control changes a byte. Fixed here as
    the text the table has always had."""
    result = run_script(VALIDATOR, "Atlas", "Atlas-spec", "Atlas-code",
                        "openChart", "Hermes-Install")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""
    assert result.stdout.splitlines() == [
        f"  {'Atlas':<32} project-leg/assembly",
        f"  {'Atlas-spec':<32} project-leg/spec",
        f"  {'Atlas-code':<32} project-leg/code",
        f"  {'openChart':<32} neutral-product   "
        "also_matches project-leg/assembly",
        f"  {'Hermes-Install':<32} install"]


@pytest.mark.parametrize("raw, said", NAMES)
def test_explain_names_the_spelled_name_in_the_no_family_header(
        raw, said, plain_explain):
    result = run_script(VALIDATOR, "--explain", raw)
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines()[0] == f"  {said}: NO FAMILY"
    assert lines_after_the_header(result.stdout) == plain_explain


def test_a_name_on_stdin_is_spelled_too(unclassified_tail):
    """Stdin strips a line, so it can hold the ESC and not the line feed."""
    raw, said = WITH_ESC
    result = run_script(VALIDATOR, input=raw + LF)
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout == f"  {said:<32} NO FAMILY\n"
    assert result.stderr.splitlines() == [
        f"FINDING naming-unclassified: {said}", *unclassified_tail]


# --- a fork whose patterns take the names: the sites of a classified name -----

@pytest.mark.parametrize("raw, said", NAMES)
def test_a_classified_name_has_one_row_in_the_listing(raw, said, loose):
    """The same print site as the table above, for a name a fork classifies:
    on 09697e9c5 the row split after the name, and the ESC was raw."""
    result = run_script(VALIDATOR, "--policy", loose, raw)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == f"  {said:<32} project-leg/assembly\n"


@pytest.mark.parametrize("raw, said", NAMES)
def test_explain_names_the_spelled_name_in_the_header_of_a_classified_name(
        raw, said, loose):
    result = run_script(VALIDATOR, "--policy", loose, "--explain", raw)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines()[0] == f"  {said}: project-leg / assembly"
    assert not_indented(lines_after_the_header(result.stdout)) == []


#: The product of a descendant name is where its referents come from, so the
#: three kinds are asked there.
PRODUCTS = [
    pytest.param("InkxRouter" + LF, "openRouter\\n", "openxRouter\\n",
                 id="ends-in-lf"),
    pytest.param("InkxRou" + LF + "ter", "openRou\\nter", "openxRou\\nter",
                 id="inner-lf"),
    pytest.param("InkxRou" + ESC + "[31mter", "openRou\\x1b[31mter",
                 "openxRou\\x1b[31mter", id="esc"),
]


@pytest.mark.parametrize("raw, direct, wide", PRODUCTS)
def test_the_claim_note_spells_the_referents_it_derives_from_the_name(
        raw, direct, wide, loose):
    """`[a CLAIM: needs a declared pin on openRouter or openxRouter ...]`
    quotes two names made from the product, and the product holds the
    control."""
    result = run_script(VALIDATOR, "--policy", loose, "--explain", "--role",
                        "assembly", raw)
    assert result.returncode == 0, result.stdout + result.stderr
    claim = [line for line in result.stdout.splitlines() if "a CLAIM" in line]
    assert len(claim) == 1, result.stdout
    assert (f"[a CLAIM: needs a declared pin on {direct} or {wide}, or a "
            "declared chain (`naming.referent_chain`)") in claim[0]
    assert not_indented(lines_after_the_header(result.stdout)) == []


def broken_said(said: str, held: str, tail: str = "") -> str:
    """The sentence `resolve_referent` gives a chain from the pin `held` that
    ends at `openQ`, for the name `said`: it quotes the name."""
    return (f"the declared chain {held} {ARROW} openQ is broken (it ends at "
            f"openQ, but {said} would need openDox or openxDox){tail}")


DIRECT = "; the direct pin on openDox is what classifies this name"
PINS = ("--pins", "openDox", "--referent-chain", "openDox,openQ")
NO_DIRECT_PINS = ("--pins", "openAdox", "--referent-chain", "openAdox,openQ")


STEMS = [
    pytest.param("co" + LF + "dexDox", id="inner-lf"),
    pytest.param("co" + ESC + "[31mdexDox", id="esc"),
]


@pytest.mark.parametrize("raw", STEMS)
def test_the_warning_on_stderr_spells_the_name_it_starts_with_and_quotes(
        raw, loose):
    """`WARNING <name>: <sentence>`, and the sentence says the name again
    (`but <name> would need`): spelling the first leaves the second raw."""
    said = spelled_of(raw)
    result = run_script(VALIDATOR, "--policy", loose, *PINS, raw)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == (
        f"WARNING {said}: {broken_said(said, 'openDox', DIRECT)}\n")
    assert result.stdout == (f"  {said:<32} domain-descendant   "
                             "also_matches project-leg/assembly\n")


@pytest.mark.parametrize("raw", STEMS)
def test_explain_spells_the_warning_that_quotes_the_name(raw, loose):
    said = spelled_of(raw)
    result = run_script(VALIDATOR, "--policy", loose, "--explain", *PINS, raw)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines()[0] == f"  {said}: domain-descendant"
    assert (f"    WARNING {broken_said(said, 'openDox', DIRECT)}"
            in result.stdout.splitlines()), result.stdout
    assert not_indented(lines_after_the_header(result.stdout)) == []


@pytest.mark.parametrize("raw", STEMS)
def test_explain_spells_the_overlap_sentence_that_quotes_the_name(raw, loose):
    """No direct pin: the chain is broken, the name is a project leg, and the
    OVERLAP line quotes the broken chain's sentence, name included."""
    said = spelled_of(raw)
    result = run_script(VALIDATOR, "--policy", loose, "--explain",
                        *NO_DIRECT_PINS, raw)
    assert result.returncode == 0, result.stdout + result.stderr
    overlap = [line for line in result.stdout.splitlines()
               if line.startswith("    OVERLAP ")]
    assert overlap == [
        f"    OVERLAP descendant form, {broken_said(said, 'openAdox')} "
        f"{ARROW} assembly root by its residual project-leg form"]


def write_manifest(tmp_path, raw: str, role: str, naming: str = "",
                   pins: str = "") -> str:
    """A manifest with ONE leg named `raw`, as a person's editor writes the
    name: a double-quoted scalar with a YAML escape."""
    path = tmp_path / "project.yaml"
    path.write_text(
        "id: atlas\n" + pins + "legs:\n"
        f"  - role: {role}\n"
        f'    repository: "testorg/{spelled_of(raw)}"\n' + naming,
        encoding="utf-8")
    return str(path)


@pytest.mark.parametrize("raw, said", NAMES)
def test_the_role_finding_spells_the_name(raw, said, loose, tmp_path):
    """`<name>: declared role 'code' but the name is the 'assembly' form of
    the project-leg family`: the leg is declared `code` and named like an
    assembly root."""
    manifest = write_manifest(tmp_path, raw, "code")
    result = run_script(VALIDATOR, "--policy", loose, "--project", manifest)
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stderr == (
        f"FINDING {said}: declared role 'code' but the name is the "
        "'assembly' form of the project-leg family\n")
    assert result.stdout == f"  {said:<32} project-leg/assembly\n"


@pytest.mark.parametrize("raw", STEMS)
def test_the_broken_chain_finding_spells_the_name_it_starts_with_and_quotes(
        raw, loose, tmp_path):
    said = spelled_of(raw)
    manifest = write_manifest(
        tmp_path, raw, "assembly",
        naming="    naming:\n      referent_chain: [openAdox, openQ]\n",
        pins="neutral_product_pins:\n  - openAdox\n")
    result = run_script(VALIDATOR, "--policy", loose, "--project", manifest)
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stderr == (
        f"FINDING {said}: {broken_said(said, 'openAdox')}\n")
