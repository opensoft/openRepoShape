# SPDX-License-Identifier: Apache-2.0
"""The chain readers ask each pin source once per run and say why one that is
there could not answer, and a chain link is recorded in the spelling its pin
file uses (#909, from #459's lines U172, U113, U145, U114 and U146).

  * U172. The root's `validate-manifest.py` asked the lookup neither what it
    tried nor why a tree it reached could not be read. A checkout of
    `openXdox` beside the root holding no `project.yaml`, or a
    `SHAPE_PIN_SOURCE_OPENXDOX` naming no folder, was offered as what would
    let the tree be read while it was there, in the words said when nothing
    was, and a manifest beside the root that is not a declaration was "not
    reachable here". Each source that is there is named now, with why it
    could not answer, and only a source that is not there is offered. The
    copies still run beside a library older than the keywords they pass.
  * U113, U145. #275's variable guard was asked over one chain's links, and
    the naming gate and `validate-manifest.py` read one chain per leg. In a
    project whose two legs' chains begin at `openß` and `openss`,
    `SHAPE_PIN_SOURCE_OPENSS` was read for both, and its one tree broke the
    chain of the product it is not, exit 1; with nothing set, each leg was
    offered that variable. The guard is asked over the declared pins and
    every chain the run reads now (`link_pins_from_trees`' `run_products`),
    and the variable is read for neither and offered to neither.
  * U114, U146. `scaffold-project.py` recorded the first `--referent-chain`
    link as typed, though it is matched to its `--pin` by `pin_product_key`,
    which folds U+212A KELVIN SIGN to `k`: `open<KELVIN SIGN>dox` beside
    `--pin openKdox@<sha>` was planned and recorded in that spelling, beside
    the one pin file `contracts/openkdox-pin.yaml`. It is recorded in the
    `--pin`'s spelling now.

No network and no GitHub: scaffolds dry-run, or into local bare remotes.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (REPO, SCAFFOLD, clear_ambient_pin_sources,
                      load_without_bytecode, run_script)
from test_chain_link_fold import SHARP, SS, scaffold_pinning
from test_chain_remedy_callers import (UNREACHED, a_chain_root,
                                       manifest_warnings)
from test_link_source_chain_defaults import VALIDATOR, manifest, tree
from test_manifest_validator import as_a_descendant_by_chain

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import (  # noqa: E402
    LINK_SOURCE_ABSENT, LinkPins, link_pins_from_trees, load_yaml, shown_path,
)

TEMPLATE_MANIFEST = (REPO / "templates" / "assembly-root" / "scripts" /
                     "validate-manifest.py")

VARIABLE = "SHAPE_PIN_SOURCE_OPENXDOX"
VARIABLE_OFFER = f"{VARIABLE} would let it be read"
CHECKOUT_OFFER = "a checkout of openXdox beside this root would let it be read"
ABSENT = "no such file or directory"
NO_MANIFEST = "it holds no project.yaml"

#: The v1.1.1 release commit. Its library takes `remedies=`, `tried=` and
#: `with_reasons=`, and no `run_products=`: a root that kept it under copies
#: from this change (`update-shape.py apply --accept-local`) runs both.
V1_1_1 = "50178305e4229275d18e71c2152403b4e9d3004e"

KELVIN = chr(0x212A)
KDOX = f"open{KELVIN}dox"


def beside(root: Path) -> Path:
    """Where `resolve_link_source` looks for `openXdox` beside `root`."""
    return root.resolve().parent / "openXdox"


def said(source: str, path, why: str) -> str:
    """The clause naming a source that is there and could not answer."""
    return f"{source}, {path}, could not answer: {why}"


def unreached(*clauses: str) -> str:
    """The root's WARNING for `openXdox`, whose tree was not read."""
    return UNREACHED.format(holder="openXdox", held="openDox",
                            offer="; ".join(clauses))


def validate(root: Path, env: dict | None = None):
    return run_script(root / "scripts" / "validate-manifest.py", cwd=root,
                      env=env)


# --- U172: the root's validate-manifest.py says what is there ---------------

def _checkout_with_no_manifest(root, _tmp_path):
    beside(root).mkdir()
    return {}, [said("the openXdox beside this root", beside(root),
                     NO_MANIFEST), VARIABLE_OFFER]


def _variable_naming_nothing(_root, tmp_path):
    nowhere = tmp_path / "nowhere"
    return {VARIABLE: str(nowhere)}, [said(VARIABLE, nowhere, ABSENT),
                                      CHECKOUT_OFFER]


def _variable_naming_a_folder_with_no_manifest(_root, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    return {VARIABLE: str(elsewhere)}, [said(VARIABLE, elsewhere, NO_MANIFEST),
                                       CHECKOUT_OFFER]


def _both_there(root, tmp_path):
    nowhere = tmp_path / "nowhere"
    beside(root).mkdir()
    return {VARIABLE: str(nowhere)}, [
        said(VARIABLE, nowhere, ABSENT),
        said("the openXdox beside this root", beside(root), NO_MANIFEST)]


@pytest.mark.parametrize("there", [
    pytest.param(_checkout_with_no_manifest, id="checkout-with-no-manifest"),
    pytest.param(_variable_naming_nothing, id="variable-naming-nothing"),
    pytest.param(_variable_naming_a_folder_with_no_manifest,
                 id="variable-naming-a-folder-with-no-manifest"),
    pytest.param(_both_there, id="both"),
])
def test_a_source_that_is_there_is_said_and_not_offered(project, monkeypatch,
                                                        tmp_path, there):
    """Lane 2's three measurements (L2-101): the WARNING was the same with
    nothing beside the root, with an empty `openXdox/` beside it, and with
    the variable naming a folder that is not there. Each source that is
    there is named with why it could not answer, and only what is not there
    is offered; where both are there, nothing is."""
    clear_ambient_pin_sources(monkeypatch)
    root = a_chain_root(project)
    env, clauses = there(root, tmp_path)
    result = validate(root, env)
    assert result.returncode == 0, result.stderr
    assert "manifest ok" in result.stdout
    assert manifest_warnings(result) == [unreached(*clauses)]


def test_with_nothing_there_both_sources_are_offered(project, monkeypatch):
    """The control: nothing beside the root and no variable, the words
    #661 gave the WARNING."""
    clear_ambient_pin_sources(monkeypatch)
    root = a_chain_root(project)
    result = validate(root)
    assert result.returncode == 0, result.stderr
    assert manifest_warnings(result) == [unreached(
        f"{VARIABLE}, or a checkout of openXdox beside this root, would let "
        "it be read")]


def test_a_manifest_beside_the_root_that_is_not_a_declaration_says_why(
        project, monkeypatch):
    """A tree that was REACHED and could not be read as a declaration was
    "not reachable here": the lookup now keeps why (`with_reasons`), as the
    scaffold's does (#338)."""
    clear_ambient_pin_sources(monkeypatch)
    root = a_chain_root(project)
    manifest(beside(root), "- one\n")
    result = validate(root)
    assert result.returncode == 0, result.stderr
    assert manifest_warnings(result) == [
        "declared-unverified: openXdox declaring a pin on openDox is a fact "
        "in openXdox's own tree, which was reached but could not be read as "
        f"a declaration ({beside(root) / 'project.yaml'}: not a mapping). "
        "The recorded chain still classifies."]


def test_a_variable_holding_a_control_character_is_spelled(project,
                                                           monkeypatch,
                                                           tmp_path):
    """The variable's value is named as `shown_path` spells a path, so an
    ESC in it does not reach the terminal raw."""
    clear_ambient_pin_sources(monkeypatch)
    root = a_chain_root(project)
    value = str(tmp_path / f"no{chr(27)}[31mwhere")
    result = validate(root, {VARIABLE: value})
    assert result.returncode == 0, result.stderr
    assert chr(27) not in result.stdout + result.stderr
    assert manifest_warnings(result) == [unreached(
        said(VARIABLE, shown_path(value), ABSENT), CHECKOUT_OFFER)]


def test_the_copy_reads_absence_in_the_librarys_words():
    """`validate-manifest.py` spells `LINK_SOURCE_ABSENT` for itself, since
    it imports nothing a kept library may lack, and tells a checkout that is
    not there from one that is by it."""
    module = load_without_bytecode(TEMPLATE_MANIFEST,
                                   "chain_pin_sources_manifest")
    assert module.SOURCE_ABSENT == LINK_SOURCE_ABSENT


def library_at(ref: str) -> bytes:
    """`scripts/repo_shape.py` at `ref`, or a skip where this checkout does
    not hold that history. It takes the keywords the reasons need and not
    `run_products=`, or the row would test nothing."""
    shown = subprocess.run(["git", "show", f"{ref}:scripts/repo_shape.py"],
                           cwd=str(REPO), capture_output=True, check=False)
    if shown.returncode != 0:
        pytest.skip(f"needs {ref} in this checkout's history")
    assert b"remedies: dict | None = None" in shown.stdout, ref
    assert b"with_reasons: bool = False" in shown.stdout, ref
    assert b"run_products" not in shown.stdout, ref
    return shown.stdout


def test_both_copies_run_beside_a_library_with_no_run_products(project,
                                                            monkeypatch):
    """THE SKEW RULE (#661). Beside v1.1.1's library each copy runs, with
    no `TypeError` for `run_products=`, and the root's WARNING says what is
    there, because every library that takes `remedies=` says what it
    tried."""
    clear_ambient_pin_sources(monkeypatch)
    root = a_chain_root(project)
    (root / "scripts" / "repo_shape.py").write_bytes(library_at(V1_1_1))
    beside(root).mkdir()
    own = validate(root)
    assert own.returncode == 0, own.stderr
    assert "Traceback" not in own.stderr, own.stderr
    assert manifest_warnings(own) == [unreached(
        said("the openXdox beside this root", beside(root), NO_MANIFEST),
        VARIABLE_OFFER)]
    gate = run_script(root / "scripts" / "validate-repository-naming.py",
                      "--project", "project.yaml", cwd=root)
    assert gate.returncode == 0, gate.stderr
    assert "Traceback" not in gate.stderr, gate.stderr


# --- U113, U145: one variable, one product of the run ----------------------

#: The naming gate's WARNING for a holder whose variable another product of
#: the run shares: no variable is offered.
GATE_UNREACHED = ("WARNING {name}: declared-unverified: {holder} declaring a "
                  "pin on {held} is a fact in {holder}'s own tree, which is "
                  "not reachable here (a sibling checkout or --link-source "
                  "{holder}=<path> would let it be read). The recorded chain "
                  "still classifies.\n")


def two_firsts(path: Path) -> Path:
    """R444's project: pins on `openß` and `openss`, which share
    `SHAPE_PIN_SOURCE_OPENSS` and are two pin files, and two legs whose
    chains begin at each."""
    return manifest(path, (
        f"neutral_product_pins:\n  - {SHARP}\n  - {SS}\nlegs:\n"
        + "".join(
            f"  - repository: testorg/{name}\n    path: \".\"\n"
            f"    role: assembly\n    naming:\n"
            f"      referent_chain: [{chain}]\n"
            for name, chain in (("codexInk", f"{SHARP}, openInk"),
                                ("codexQuill", f"{SS}, openQuill")))))


def one_chain(path: Path, *pins: str) -> Path:
    """`codexQuill` recording `openss -> openQuill`, pinning `pins`."""
    return manifest(path, (
        "neutral_product_pins:\n" + "".join(f"  - {pin}\n" for pin in pins)
        + "legs:\n  - repository: testorg/codexQuill\n    path: \".\"\n"
        "    role: assembly\n    naming:\n"
        f"      referent_chain: [{SS}, openQuill]\n"))


def sharp_tree(tmp_path: Path, declares: str) -> dict:
    """`SHAPE_PIN_SOURCE_OPENSS` set to `openß`'s tree, declaring
    `declares`."""
    return {"SHAPE_PIN_SOURCE_OPENSS": str(
        tree(tmp_path / "trees" / "sharp", declares))}


@pytest.mark.parametrize("variable", [True, False], ids=["set", "unset"])
def test_the_gate_reads_a_shared_variable_for_no_chain(tmp_path, variable):
    """R444. Set to `openß`'s tree, the variable was read for both chains,
    and the gate said "FINDING codexQuill: the declared chain openss ->
    openQuill is broken (openss declares openInk, not openQuill)", exit 1;
    unset, each leg was offered it. It is read for neither now, and offered
    to neither, and both chains are declared-unverified, exit 0."""
    root = two_firsts(tmp_path / "ws" / "codexSoft")
    env = sharp_tree(tmp_path, "openInk") if variable else {}
    result = run_script(VALIDATOR, "--project", "project.yaml", cwd=root,
                        env=env)
    assert result.returncode == 0, result.stderr
    assert result.stderr == (
        GATE_UNREACHED.format(name="codexInk", holder=SHARP, held="openInk")
        + GATE_UNREACHED.format(name="codexQuill", holder=SS,
                                held="openQuill"))


def test_a_variable_two_declared_pins_share_is_read_for_no_chain(tmp_path):
    """#275's rule, that a variable two declared products share answers for
    neither, holds for a chain too. One chain begins at `openss`, and the
    project pins `openß` as well, on no chain: the variable was read for
    `openss`, the one link of the one chain that names it, and `openß`'s
    tree broke the chain, exit 1."""
    root = one_chain(tmp_path / "ws" / "codexSoft", SHARP, SS)
    result = run_script(VALIDATOR, "--project", "project.yaml", cwd=root,
                        env=sharp_tree(tmp_path, "openInk"))
    assert result.returncode == 0, result.stderr
    assert result.stderr == GATE_UNREACHED.format(
        name="codexQuill", holder=SS, held="openQuill")


def test_a_variable_a_link_of_another_chain_shares_is_read_for_no_chain(
        tmp_path):
    """The chains half. The project pins `openss` alone, and its spec leg
    records a chain beginning at `openß`: a link of the run, though no
    classification consults that chain. The variable was read for `openss`,
    and `openß`'s tree broke `codexQuill`'s chain, exit 1."""
    root = manifest(tmp_path / "ws" / "codexSoft", (
        f"neutral_product_pins:\n  - {SS}\nlegs:\n"
        "  - repository: testorg/codexQuill\n    path: \".\"\n"
        "    role: assembly\n    naming:\n"
        f"      referent_chain: [{SS}, openQuill]\n"
        "  - repository: testorg/codexQuill-spec\n    path: spec\n"
        "    role: spec\n    naming:\n"
        f"      referent_chain: [{SHARP}, openInk]\n"))
    result = run_script(VALIDATOR, "--project", "project.yaml", cwd=root,
                        env=sharp_tree(tmp_path, "openInk"))
    assert result.returncode == 0, result.stderr
    assert result.stderr == GATE_UNREACHED.format(
        name="codexQuill", holder=SS, held="openQuill")


def test_a_variable_one_product_of_the_run_names_is_still_read(tmp_path):
    """The control: one pin, one chain, and one link naming the variable,
    which is read and verifies the chain."""
    root = one_chain(tmp_path / "ws" / "codexSoft", SS)
    env = {"SHAPE_PIN_SOURCE_OPENSS": str(
        tree(tmp_path / "trees" / SS, "openQuill"))}
    result = run_script(VALIDATOR, "--explain", "--project", "project.yaml",
                        cwd=root, env=env)
    assert result.returncode == 0, result.stderr
    assert f"CHAIN {SS} → openQuill   [verified]" in result.stdout, (
        result.stdout)
    assert "WARNING" not in result.stderr, result.stderr


def a_root_sharing_one_variable(project: Path, where: str) -> Path:
    """The scaffolded root as `codexDox`, pinning `openss` with its pin file
    and recording `openss -> openDox`, and naming `openß` too: as the first
    link of a chain its spec leg records (this validator reads every chain a
    leg records, whatever that leg's name claims), or as a pin on no
    chain."""
    as_a_descendant_by_chain(project, first=SS)
    (project / "contracts" / f"{SS}-pin.yaml").write_text(
        "schema_version: 1\nkind: pinned_contract_manifest\n",
        encoding="utf-8")
    if where == "chain":
        anchor = "      role: spec\n      also_matches: []\n"
        added = f"{anchor}      referent_chain: [{SHARP}, openQuill]\n"
    else:
        anchor = f"neutral_product_pins:\n  - {SS}\n"
        added = f"{anchor}  - {SHARP}\n"
    written = project / "project.yaml"
    text = written.read_text(encoding="utf-8")
    assert anchor in text, f"fixture drift: {anchor!r} not in project.yaml"
    written.write_text(text.replace(anchor, added, 1), encoding="utf-8")
    return project


@pytest.mark.parametrize("variable", [True, False], ids=["set", "unset"])
@pytest.mark.parametrize("where", ["chain", "pin"])
def test_the_manifest_gate_reads_a_shared_variable_for_no_chain(
        project, monkeypatch, tmp_path, where, variable):
    """The same defect in the root's own validator, which reads every leg's
    chain: set to `openß`'s tree, the variable was read for `openss` and
    broke `codexDox`'s chain, exit 1; unset, it was offered. It is read for
    neither now, and the holder is offered a checkout beside the root
    alone."""
    clear_ambient_pin_sources(monkeypatch)
    root = a_root_sharing_one_variable(project, where)
    result = validate(root, sharp_tree(tmp_path, "openQuill")
                      if variable else {})
    assert result.returncode == 0, result.stderr
    assert "manifest ok" in result.stdout
    assert manifest_warnings(result) == [UNREACHED.format(
        holder=SS, held="openDox",
        offer=f"a checkout of {SS} beside this root would let it be read")]


def test_the_library_asks_the_guard_over_the_run(tmp_path, monkeypatch):
    """`run_products` widens the guard to the run; without it, the guard is
    the chain's own, as it was."""
    clear_ambient_pin_sources(monkeypatch)
    monkeypatch.setenv("SHAPE_PIN_SOURCE_OPENSS",
                       str(tree(tmp_path / SS, "openQuill")))
    chain = [SS, "openQuill"]
    assert link_pins_from_trees(chain) == {SS: {"openQuill"}}
    found = link_pins_from_trees(chain, run_products=[SHARP, *chain])
    assert isinstance(found, LinkPins)
    assert found == {}
    assert found.env_shared == {SHARP, SS}


# --- U114, U146: the first link in its pin's spelling ------------------------

@pytest.fixture(scope="module")
def scaffold_module():
    """`scaffold-project.py` loaded as a module."""
    return load_without_bytecode(SCAFFOLD, "scaffold_chain_pin_sources")


@pytest.mark.parametrize("raw,pins,links", [
    pytest.param(f"{KDOX},openInk", {"openKdox"}, ("openKdox", "openInk"),
                 id="kelvin-sign"),
    pytest.param("OPENKDOX, openInk", {"openKdox"}, ("openKdox", "openInk"),
                 id="ascii-case"),
    pytest.param(f"opensoft/{KDOX},openInk", {"openKdox"},
                 ("opensoft/openKdox", "openInk"), id="owner-kept"),
    pytest.param(f"{KDOX},openInk", (), (KDOX, "openInk"), id="no-pin"),
    pytest.param("openXdox,openkdox,openInk", {"openXdox", "openKdox"},
                 ("openXdox", "openkdox", "openInk"), id="first-link-alone"),
    pytest.param(f"{SHARP},openInk", {SS}, (SHARP, "openInk"),
                 id="another-pin-file"),
    pytest.param(" , ", {"openKdox"}, (), id="no-link"),
])
def test_a_first_link_that_is_a_pin_is_spelled_as_the_pin(scaffold_module,
                                                          raw, pins, links):
    """The first link alone, and only where `pin_product_key` makes it the
    `--pin`'s product; `openß` is another pin file than `openss`."""
    assert scaffold_module.referent_chain_links(raw, pins) == links


def test_the_plan_names_the_chain_in_the_pins_spelling(tmp_path):
    """The issue's probe: `--pin openKdox@<sha> --referent-chain
    'open<KELVIN SIGN>dox,openInk' --dry-run` planned the pin file
    `contracts/openkdox-pin.yaml` and printed the chain with the Kelvin
    sign."""
    result = scaffold_pinning(tmp_path, "openKdox", f"{KDOX},openInk",
                              "--dry-run")
    assert result.returncode == 0, result.stderr + result.stdout
    assert ("reaching openInk through the declared pin chain openKdox → "
            "openInk") in result.stdout, result.stdout
    assert "contracts/openkdox-pin.yaml" in result.stdout, result.stdout
    assert KELVIN not in result.stdout + result.stderr


def test_the_manifest_records_the_chain_in_the_pins_spelling(tmp_path):
    """A real run recorded the Kelvin sign in `project.yaml`."""
    result = scaffold_pinning(tmp_path, "openKdox", f"{KDOX},openInk")
    assert result.returncode == 0, result.stderr + result.stdout
    written = tmp_path / "work" / "codexInk" / "project.yaml"
    assert KELVIN not in written.read_text(encoding="utf-8")
    assembly = next(leg for leg in load_yaml(written)["legs"]
                    if leg["role"] == "assembly")
    assert assembly["naming"]["referent_chain"] == ["openKdox", "openInk"]
