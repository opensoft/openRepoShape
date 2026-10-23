# SPDX-License-Identifier: Apache-2.0
"""A chain link, a declared pin and a `--link-source` key are one product by
`pin_product_key`, the pin file's own fold, and not by `casefold()` (#444).

#275's fix (PR #409) made a product's identity `pin_product_key`: what makes
two declarations one product is the pin file they share,
`contracts/<product lowercased>-pin.yaml`, which `validate-pins.py` reads.
The chain readers of `scripts/repo_shape.py`, and the `--link-source` table
`validate-repository-naming.py` builds, asked the same question with
`casefold()`. The two folds agree over ASCII and part company outside it:
`casefold()` turns `openß` (open + the German sharp s) into `openss`,
which `lower()` leaves alone, so the two names are two pin files to the pin
validator and were one link to the chain. The issue's rows, each a test
below:

  C  a holder whose tree declares `openss` verified a chain that says
     `openß`; now the chain is broken, and the finding names the link;
  D  a chain naming both was refused as a cycle; now it is two links, each
     read from its own tree, and verified;
  E  a project pinning `openss` verified a chain beginning at `openß`;
     now the chain does not begin at a held pin;
  F  `--link-source openss=` answered for the link `openß`; now it keys
     no link, `openß` is declared-unverified, and the value is noted;
  G  `link_pins_from_trees` kept one entry for the pair; now two.

The same fold decided four more answers, measured beside the issue's on
main 8f453d0 and tested here: a direct pin on `openGlaß` reached
`openGlass` (H); two chains beginning at `openß` and `openss` counted
one first link, so a bare `--link-source` was read as both products' trees
(I, #441's rule); `scaffold-project.py --pin openss@<sha>
--referent-chain openß,openInk` planned a descendant through a link no
pin file names (K); and a chain ENDING at `openGlaß` reached the referent
`openGlass` for `codexGlass`, in the naming gate and in a real scaffold
alike, which created all three repositories (L).

The answers that do not move are held too: an ASCII chain, a chain spelled
`openß` throughout, and links that differ from a declaration by ASCII
case alone (`openXdox` and `openxdox` are one pin file). Over ASCII `lower()`
and `casefold()` make the same groups, and `lower()` only ever splits a group
`casefold()` makes, so no name GitHub, `--pin` or the naming policy can spell
answers differently.

Every run is made from a directory of its own under `tmp_path`, and every
manifest is written as bytes.

The plain listing those rows read pads each name by the columns a terminal
gives it (#1217). Measured on main 50ce8ab1, it padded by code points: on a
UTF-8 stdout the label of `\\u65e5\\u672c\\u8a9e` stood 3 columns right of
`codexGlass`'s and that of `e\\u0301cole` 1 left, and on an ASCII stdout,
which writes each as its escapes, 15 and 5 right.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import REPO, SCAFFOLD, clear_ambient_pin_sources, git, run_script
from test_link_source_chain_defaults import (MORE_SPECIFIC, manifest, naming,
                                             project, tree, two_firsts_note,
                                             unverified)
from test_stdout_encoding import run_tool, shown

# `project` here is that module's manifest writer, not conftest's fixture of
# the same name, which no test below asks for.

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import link_pins_from_trees, pin_product_key  # noqa: E402

#: Two pin files, `contracts/openß-pin.yaml` and
#: `contracts/openss-pin.yaml`, that `casefold()` took for one product.
SHARP = "openß"
SS = "openss"
#: The referent `codexGlass` needs is `openGlass`; `openGlaß` is another pin
#: file, which `casefold()` took for it.
GLASS_SHARP = "openGlaß"
CODEX_INK_DESCENDS = "codexInk                         domain-descendant/assembly"
CODEX_INK_DOES_NOT = ("codexInk                         project-leg/assembly"
                      "   also_matches domain-descendant")


def keyed(*pairs: tuple[str, Path]) -> list[str]:
    """`--link-source KEY=PATH` for each pair, as arguments."""
    return [arg for key, path in pairs
            for arg in ("--link-source", f"{key}={path}")]


def broken(chain: str, detail: str, name: str = "codexInk") -> str:
    """The FINDING the naming gate prints for `name`'s broken chain."""
    return (f"FINDING {name}: the declared chain {chain} is broken "
            f"({detail})\n")


def not_a_link(value: str, links: str) -> str:
    """The NOTE for `value`, a `KEY=PATH` whose key names no chain link, so
    it was read as a bare PATH that the first link, keyed, never needed."""
    return (f"NOTE --link-source {value}: not used — a bare PATH is the tree "
            f"of a chain's first link alone, openXdox, which had "
            f"{MORE_SPECIFIC}. It was read as a PATH: `{value.partition('=')[0]}`"
            f" is not a link of a referent chain here (links: {links}).\n")


@pytest.fixture
def ink(tmp_path) -> dict:
    """`codexInk`'s project directory and the place its links' trees go."""
    return {"root": tmp_path / "ws" / "codexInk", "trees": tmp_path / "trees"}


# --- the issue's rows: the naming gate --------------------------------------

def test_a_holder_declaring_another_pin_file_breaks_the_chain(ink):
    """ROW C. The chain says `openXdox -> openß -> openInk` and
    `openXdox`'s own tree declares `openss`, another pin file. It was
    `[verified]`, exit 0; the chain is broken there now, and the finding
    quotes what the tree says."""
    project(ink["root"], "openXdox", f"openXdox, {SHARP}, openInk")
    result = naming(ink["root"], "--project", "project.yaml", *keyed(
        ("openXdox", tree(ink["trees"] / "openXdox", SS)),
        (SHARP, tree(ink["trees"] / SHARP, "openInk"))))
    assert result.returncode == 1, result.stderr
    assert CODEX_INK_DOES_NOT in result.stdout
    assert result.stderr == broken(f"openXdox → {SHARP} → openInk",
                                   f"openXdox declares {SS}, not {SHARP}")


def test_a_chain_naming_both_spellings_is_two_links(ink):
    """ROW D. `openß` and `openss` are two products, each with its own
    tree, so the chain repeats no link: it was refused as a cycle, exit 1,
    and both keyed values were NOTEd as unused. Every link is read from its
    own tree now, and the chain holds."""
    project(ink["root"], "openXdox", f"openXdox, {SHARP}, {SS}, openInk")
    result = naming(ink["root"], "--project", "project.yaml", *keyed(
        ("openXdox", tree(ink["trees"] / "openXdox", SHARP)),
        (SHARP, tree(ink["trees"] / SHARP, SS)),
        (SS, tree(ink["trees"] / SS, "openInk"))))
    assert result.returncode == 0, result.stderr
    assert CODEX_INK_DESCENDS in result.stdout
    assert result.stderr == ""
    explained = naming(ink["root"], "--explain", "--project", "project.yaml",
                       *keyed(("openXdox", ink["trees"] / "openXdox"),
                              (SHARP, ink["trees"] / SHARP),
                              (SS, ink["trees"] / SS)))
    assert (f"CHAIN openXdox → {SHARP} → {SS} → openInk   [verified]"
            in explained.stdout), explained.stdout


def test_a_chain_must_begin_at_the_pin_file_the_project_holds(ink):
    """ROW E. The project pins `openss`, so `contracts/openss-pin.yaml` is
    its pin; a chain beginning at `openß` does not begin there. It was
    `[verified]`, exit 0. The keyed source is never read, because a chain
    broken in its shape reads no link (#338), and it is NOTEd so."""
    project(ink["root"], SS, f"{SHARP}, openInk")
    result = naming(ink["root"], "--project", "project.yaml", *keyed(
        (SHARP, tree(ink["trees"] / SHARP, "openInk"))))
    assert result.returncode == 1, result.stderr
    assert CODEX_INK_DOES_NOT in result.stdout
    assert result.stderr == (
        f"NOTE --link-source {SHARP}={ink['trees'] / SHARP}: not used — no "
        f"name classified here reads {SHARP}'s own declaration.\n"
        + broken(f"{SHARP} → openInk",
                 f"it begins at {SHARP}, which is not in this project's "
                 "`neutral_product_pins:` — the first entry is the pin this "
                 "project actually holds"))


def test_a_chain_must_end_at_the_pin_file_the_name_claims(tmp_path):
    """ROW L. `codexGlass` pins `openXdox`, records `openXdox -> openGlaß`,
    and `openXdox`'s own tree declares `openGlaß`. `openGlass` is the
    referent the name claims, `contracts/openglass-pin.yaml`, and the chain
    ends at another pin file. It was `domain-descendant`, exit 0; the chain is
    broken at its end now, and the finding says what the name would need. The
    keyed source is never read, because a chain broken in its shape reads no
    link (#338), and it is NOTEd so."""
    root = project(tmp_path / "ws" / "codexGlass", "openXdox",
                   f"openXdox, {GLASS_SHARP}")
    held = tree(tmp_path / "trees" / "openXdox", GLASS_SHARP)
    result = naming(root, "--project", "project.yaml",
                    *keyed(("openXdox", held)))
    assert result.returncode == 1, result.stderr
    assert (f"{'codexGlass':<32} project-leg/assembly   also_matches "
            "domain-descendant") in result.stdout, result.stdout
    assert result.stderr == (
        f"NOTE --link-source openXdox={held}: not used — no name classified "
        "here reads openXdox's own declaration.\n"
        + broken(f"openXdox → {GLASS_SHARP}",
                 f"it ends at {GLASS_SHARP}, but codexGlass would need "
                 "openGlass or openxGlass", "codexGlass"))


def test_a_source_keyed_by_the_other_spelling_answers_for_no_link(ink):
    """ROW F. No tree is given for `openß`; one is given as
    `--link-source openss=`, which `casefold()` read as `openß`'s, and
    the chain was `[verified]` from a tree filed under another product.
    `openss` keys no link of this chain now: the value is a bare PATH, which
    the keyed first link never needed, and `openß` is
    declared-unverified, a warning, exit 0, as any link with no tree is."""
    project(ink["root"], "openXdox", f"openXdox, {SHARP}, openInk")
    other = tree(ink["trees"] / SS, "openInk")
    result = naming(ink["root"], "--project", "project.yaml", *keyed(
        ("openXdox", tree(ink["trees"] / "openXdox", SHARP)), (SS, other)))
    assert result.returncode == 0, result.stderr
    assert CODEX_INK_DESCENDS in result.stdout
    assert result.stderr == (
        unverified("codexInk", SHARP, "openInk")
        + not_a_link(f"{SS}={other}", f"openXdox, {SHARP}, openInk"))


def test_the_table_keeps_one_entry_for_each_pin_file(tmp_path, monkeypatch):
    """ROW G, in this process. A checkout of each beside the project: the
    table kept one entry, `openss`, and the later tree won for both. It keeps
    two now, each holding its own tree's declaration, keyed as
    `pin_product_key` keys them."""
    clear_ambient_pin_sources(monkeypatch)
    tree(tmp_path / SHARP, "openAAA")
    tree(tmp_path / SS, "openBBB")
    (tmp_path / "codexInk").mkdir()
    found = link_pins_from_trees([SHARP, SS], tmp_path / "codexInk")
    assert found == {SHARP: {"openAAA"}, SS: {"openBBB"}}
    assert set(found) == {pin_product_key(SHARP), pin_product_key(SS)}


# --- the answers that do not move -------------------------------------------

@pytest.mark.parametrize("pins,chain,declares,expected_chain", [
    pytest.param("openXdox", "openXdox, openYdox, openInk",
                 {"openXdox": "openYdox", "openYdox": "openInk"},
                 "openXdox → openYdox → openInk", id="A-ascii"),
    pytest.param("openXdox", f"openXdox, {SHARP}, openInk",
                 {"openXdox": SHARP, SHARP: "openInk"},
                 f"openXdox → {SHARP} → openInk", id="B-sharp-s-throughout"),
    pytest.param("openXdox", "openxdox, openYdox, openInk",
                 {"OPENXDOX": "OPENYDOX", "OpenYdox": "openink"},
                 "openxdox → openYdox → openInk", id="ascii-case-alone"),
])
def test_a_chain_that_holds_still_holds(ink, pins, chain, declares,
                                        expected_chain):
    """THE CONTROLS. The issue's rows A and B, and a chain whose links differ
    from the pin, the keys and the trees' declarations by ASCII case alone,
    which is one pin file (`contracts/openxdox-pin.yaml`): each is
    `[verified]`, exit 0, with nothing said, as on main."""
    project(ink["root"], pins, chain)
    sources = [(key, tree(ink["trees"] / key, held))
               for key, held in declares.items()]
    result = naming(ink["root"], "--explain", "--project", "project.yaml",
                    *keyed(*sources))
    assert result.returncode == 0, result.stderr
    assert "codexInk: domain-descendant / assembly" in result.stdout
    assert f"CHAIN {expected_chain}   [verified]" in result.stdout
    assert "WARNING" not in result.stdout + result.stderr
    assert "NOTE" not in result.stderr


# --- the same fold elsewhere ------------------------------------------------

@pytest.mark.parametrize("pin,answer", [
    pytest.param("openGlaß", "project-leg/assembly   also_matches "
                 "domain-descendant", id="openGla-sharp-s"),
    pytest.param("openglass", "domain-descendant/assembly   also_matches "
                 "project-leg/assembly", id="ascii-case-control"),
])
def test_a_direct_pin_reaches_only_its_own_pin_file(tmp_path, pin, answer):
    """ROW H. `codexGlass` needs a pin on `openGlass`,
    `contracts/openglass-pin.yaml`. A pin on `openGlaß` is another pin
    file, and it classified `codexGlass` as `openGlass`'s descendant; it no
    longer does, and the role it declares still classifies it. `openglass`,
    the same pin file in another case, still does."""
    result = run_script(REPO / "scripts" / "validate-repository-naming.py",
                        "--role", "assembly", "--pins", pin, "codexGlass",
                        cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"  {'codexGlass':<32} {answer}\n"
    assert result.stderr == ""


# --- the listing's columns (#1217) ------------------------------------------

#: Three wide characters, and a name whose acute is a combining mark.
WIDE = "\u65e5\u672c\u8a9e"
COMBINING = "e\u0301cole"
#: The columns a UTF-8 stdout's terminal gives each, counted by hand: two
#: to a wide character and none to the combining acute. On an ASCII stdout
#: each is written as its escapes, ASCII, one column to a character.
NAME_COLUMNS = {WIDE: 6, COMBINING: 5}
#: Where every label begins: the 2 of the indent, the 32 of the name, and a
#: space.
LABEL_COLUMN = 35


@pytest.mark.parametrize("encoding", ["utf-8:strict", "ascii:strict"])
def test_a_wide_or_combining_name_has_its_label_under_codexglass_s(
        tmp_path, encoding):
    """THE ISSUE'S ROWS: the ASCII control, `codexGlass`, then a name of
    three wide characters and one with a combining acute, which no family
    classifies. On main their labels began at columns 38 and 34 on a UTF-8
    stdout, and 50 and 40 on an ASCII one, whose `backslashreplace` writes
    each as its escapes. Each begins at column 35 now, as `codexGlass`'s
    does, and the control's line is byte for byte what it was. Bytes,
    decoded strictly in the encoding the run was given."""
    code, out, err = run_tool(
        REPO / "scripts" / "validate-repository-naming.py", "--role",
        "assembly", "codexGlass", WIDE, COMBINING, encoding=encoding,
        tmp_path=tmp_path, cwd=tmp_path)
    assert code == 1, err
    lines = out.split("\n")
    assert lines[0] == (f"  {'codexGlass':<32} project-leg/assembly   "
                        "also_matches domain-descendant"), out
    assert lines[3:] == [""], out
    for line, name in zip(lines[1:3], (WIDE, COMBINING)):
        written = shown(name, encoding)
        assert line.startswith(f"  {written} "), (line, out)
        rest = line[2 + len(written):]
        assert rest.lstrip(" ") == "NO FAMILY", (line, out)
        takes = NAME_COLUMNS.get(written, len(written))
        assert 2 + takes + len(rest) - len(rest.lstrip(" ")) == \
            LABEL_COLUMN, (line, out)


def test_chains_beginning_at_both_spellings_read_a_bare_tree_for_neither(
        tmp_path):
    """ROW I. Two legs, `codexInk` recording `openß -> openInk` and
    `codexQuill` recording `openss -> openQuill`, and one bare tree. The
    first links were counted as one, so the bare tree answered for both, and
    `codexQuill`'s chain was broken by a tree that is not `openss`'s: "openss
    declares openInk, not openQuill", exit 1. They are two first links now,
    and #441's rule reads a bare tree for neither."""
    root = manifest(tmp_path / "ws" / "codexSoft", (
        f"neutral_product_pins:\n  - {SHARP}\n  - {SS}\nlegs:\n"
        + "".join(
            f"  - repository: testorg/{name}\n    path: \".\"\n"
            f"    role: assembly\n    naming:\n"
            f"      referent_chain: [{chain}]\n"
            for name, chain in (("codexInk", f"{SHARP}, openInk"),
                                ("codexQuill", f"{SS}, openQuill")))))
    bare = tree(tmp_path / "trees" / "bare", "openInk")
    result = naming(root, "--project", "project.yaml",
                    "--link-source", str(bare))
    assert result.returncode == 0, result.stderr
    assert "FINDING" not in result.stderr
    # Each WARNING is asserted to the link it names and no further: the
    # variable it offers is #275's business, not this issue's.
    lines = result.stderr.splitlines(keepends=True)
    assert len(lines) == 3, result.stderr
    assert lines[0].startswith(f"WARNING codexInk: declared-unverified: "
                               f"{SHARP} declaring a pin on openInk is a "
                               f"fact in {SHARP}'s own tree, which is not "
                               "reachable here"), result.stderr
    assert lines[1].startswith("WARNING codexQuill: declared-unverified: "
                               f"{SS} declaring a pin on openQuill is a fact "
                               f"in {SS}'s own tree, which is not reachable "
                               "here"), result.stderr
    assert lines[2] == two_firsts_note(bare, SHARP, SS)


# --- the scaffold -----------------------------------------------------------

def scaffold_pinning(tmp_path: Path, product: str, chain: str, *args: str,
                     name: str = "codexInk", declares: str = "openInk"):
    """`scaffold-project.py` for `codexSoft/<name>`, pinning `product` at a
    commit of a checkout declaring `declares`, which is its `--pin-source`,
    and recording `chain`. Remotes and the work tree go under `tmp_path`."""
    source = tree(tmp_path / "src", declares)
    for step in (("init", "-q", "-b", "main"), ("add", "-A"),
                 ("commit", "-qm", "seed")):
        git(*step, cwd=source)
    commit = git("rev-parse", "HEAD", cwd=source).stdout.strip()
    return run_script(SCAFFOLD, "--org", "codexSoft", "--project", name,
                      "--elected-by", "Test Human", "--elected-on",
                      "2026-09-05", "--pin", f"{product}@{commit}",
                      "--pin-source", str(source), "--referent-chain", chain,
                      "--local-remote-dir", str(tmp_path / "remotes"),
                      "--work-dir", str(tmp_path / "work"), *args,
                      cwd=tmp_path)


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real"])
def test_the_scaffold_refuses_a_chain_beginning_at_another_pin_file(
        tmp_path, dry_run):
    """ROW K. `--pin openss@<sha>` writes `contracts/openss-pin.yaml`, and
    `--referent-chain openß,openInk` begins at another pin file. The dry
    run planned a descendant reaching `openInk` through `openß`, reading
    `openss`'s checkout as `openß`'s tree. Both runs now refuse
    `chain-not-declared` before anything is created."""
    result = scaffold_pinning(tmp_path, SS, f"{SHARP},openInk",
                              *(["--dry-run"] if dry_run else []))
    assert result.returncode == 2, result.stderr + result.stdout
    assert result.stderr == (
        f"REFUSED chain-not-declared: --referent-chain {SHARP},openInk: the "
        f"declared chain {SHARP} → openInk is broken (it begins at {SHARP}, "
        "which is not in this project's `neutral_product_pins:` — the first "
        "entry is the pin this project actually holds)\n"
        "Remediation: the first entry is the product this project PINS "
        "(pass it as --pin <product>@<40 hex>) and the last is the "
        "`open<Product>` the name claims; every link between them is "
        "declared by that link's own project.yaml.\n")
    assert not (tmp_path / "remotes").exists()
    assert not (tmp_path / "work").exists()


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real"])
def test_the_scaffold_refuses_a_chain_ending_at_another_pin_file(
        tmp_path, dry_run):
    """ROW L. `codexGlass` pins `openXdox`, whose `--pin-source` declares
    `openGlaß`, and `--referent-chain openXdox,openGlaß` ends at a pin file
    that is not `openGlass`'s. The dry run planned a descendant reaching
    `openGlass` through the chain, and the REAL run created all three
    repositories and recorded `referent_chain: [openXdox, openGlaß]`. Both
    runs now refuse `chain-not-declared` before anything is created."""
    result = scaffold_pinning(tmp_path, "openXdox",
                              f"openXdox,{GLASS_SHARP}",
                              *(["--dry-run"] if dry_run else []),
                              name="codexGlass", declares=GLASS_SHARP)
    assert result.returncode == 2, result.stderr + result.stdout
    assert result.stderr == (
        f"REFUSED chain-not-declared: --referent-chain openXdox,"
        f"{GLASS_SHARP}: the declared chain openXdox → {GLASS_SHARP} is "
        f"broken (it ends at {GLASS_SHARP}, but codexGlass would need "
        "openGlass or openxGlass)\n"
        "Remediation: the first entry is the product this project PINS "
        "(pass it as --pin <product>@<40 hex>) and the last is the "
        "`open<Product>` the name claims; every link between them is "
        "declared by that link's own project.yaml.\n")
    assert not (tmp_path / "remotes").exists()
    assert not (tmp_path / "work").exists()


def test_the_scaffold_still_plans_a_chain_beginning_at_its_pin(tmp_path):
    """The control: the same run with the chain beginning at the pinned
    `openss` itself plans, and its `--pin-source` verifies the link."""
    result = scaffold_pinning(tmp_path, SS, f"{SS},openInk", "--dry-run")
    assert result.returncode == 0, result.stderr + result.stdout
    assert (f"reaching openInk through the declared pin chain {SS} → openInk"
            in result.stdout), result.stdout
    assert "--dry-run: nothing was created." in result.stdout
    assert not (tmp_path / "remotes").exists()
