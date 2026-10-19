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
  * #990. A variable that is SET, and that the guard passes over because
    two products of the run share it, was named by no line in either chain
    reader, so the `declared-unverified` WARNING, which leaves it out of
    its offer, read as if nothing were set. Each reader says it once now,
    naming the variable and the products: a NOTE in the gate and a
    `  note` in the root's validator, as `validate-pins.py` prints one.
    Nothing fails on it, and an unset variable stays unsaid.

No network and no GitHub: scaffolds dry-run, or into local bare remotes.
"""

from __future__ import annotations

import functools
import subprocess
import sys
from pathlib import Path

import pytest

import test_chain_link_fold
from conftest import (REPO, SCAFFOLD, clear_ambient_pin_sources,
                      load_without_bytecode, run_script)
from test_chain_link_fold import SHARP, SS, scaffold_pinning
from test_chain_remedy_callers import (UNREACHED, a_chain_root,
                                       manifest_warnings)
from test_link_source_chain_defaults import VALIDATOR, manifest, tree
from test_manifest_validator import as_a_descendant_by_chain

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import (  # noqa: E402
    LINK_SOURCE_ABSENT, LinkPins, NamingPolicy, link_pins_from_trees,
    load_yaml, shown_path,
)
import shape_materialize  # noqa: E402

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

#: The gate's NOTE for a variable that is set and that products of the run
#: share, so that it is read for no link (#990).
GATE_SHARED = ("NOTE link-source-collides: {variable} is set, but {products}, "
               "products this run reads, share it: it cannot say which it "
               "holds, so it is read for none of them. A link's own tree is "
               "read from a sibling checkout or --link-source <link>=<path>.")

#: The root's own note for the same, spelled as `validate-pins.py` spells a
#: note (#990).
ROOT_SHARED = ("  note link-source-collides: {variable} is set, but "
               "{products}, products this run reads, share it: it cannot say "
               "which it holds, so it is read for none of them. A link's own "
               "tree is read from a checkout of it beside this root.")


def said_shared(template: str, variable: str, *products: str) -> str:
    """`template`, `GATE_SHARED` or `ROOT_SHARED`, for `variable` and the
    products that share it, joined as both readers join them."""
    return template.format(variable=variable, products=(
        ", ".join(products[:-1]) + f" and {products[-1]}"))


def collision_lines(result) -> list[str]:
    """Every line a chain reader printed about a shared variable."""
    return [line for line in result.stderr.splitlines()
            if "link-source-collides" in line]


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


#: How a row hands `SHAPE_PIN_SOURCE_OPENSS` to the child: set to `openß`'s
#: tree, set to nothing, or not handed at all. An empty variable is read
#: for no product (`resolve_link_source` asks only a value), so it is no
#: more said than an unset one (#990, RV1011's NIT-1): the conftest's
#: `blank_unnamed_pin_sources` hands children `""`, and so does a person
#: who exported the variable empty.
HANDED = ["set", "empty", "unset"]


def handed(tmp_path: Path, how: str, declares: str) -> dict:
    """The child's `SHAPE_PIN_SOURCE_OPENSS`, as `HANDED` names `how`."""
    if how == "set":
        return sharp_tree(tmp_path, declares)
    return {"SHAPE_PIN_SOURCE_OPENSS": ""} if how == "empty" else {}


@pytest.mark.parametrize("variable", HANDED)
def test_the_gate_reads_a_shared_variable_for_no_chain(tmp_path, variable):
    """R444. Set to `openß`'s tree, the variable was read for both chains,
    and the gate said "FINDING codexQuill: the declared chain openss ->
    openQuill is broken (openss declares openInk, not openQuill)", exit 1;
    unset, each leg was offered it. It is read for neither now, and offered
    to neither, and both chains are declared-unverified, exit 0. Set, one
    NOTE names it and both products (#990); empty or unset, nothing
    does."""
    root = two_firsts(tmp_path / "ws" / "codexSoft")
    result = run_script(VALIDATOR, "--project", "project.yaml", cwd=root,
                        env=handed(tmp_path, variable, "openInk"))
    assert result.returncode == 0, result.stderr
    assert result.stderr == (
        GATE_UNREACHED.format(name="codexInk", holder=SHARP, held="openInk")
        + GATE_UNREACHED.format(name="codexQuill", holder=SS,
                                held="openQuill")
        + (said_shared(GATE_SHARED, "SHAPE_PIN_SOURCE_OPENSS", SHARP, SS)
           + "\n" if variable == "set" else ""))


def test_a_variable_two_declared_pins_share_is_read_for_no_chain(tmp_path):
    """#275's rule, that a variable two declared products share answers for
    neither, holds for a chain too. One chain begins at `openss`, and the
    project pins `openß` as well, on no chain: the variable was read for
    `openss`, the one link of the one chain that names it, and `openß`'s
    tree broke the chain, exit 1. The NOTE names the pin that is on no
    chain too (#990)."""
    root = one_chain(tmp_path / "ws" / "codexSoft", SHARP, SS)
    result = run_script(VALIDATOR, "--project", "project.yaml", cwd=root,
                        env=sharp_tree(tmp_path, "openInk"))
    assert result.returncode == 0, result.stderr
    assert result.stderr == GATE_UNREACHED.format(
        name="codexQuill", holder=SS, held="openQuill") + said_shared(
        GATE_SHARED, "SHAPE_PIN_SOURCE_OPENSS", SS, SHARP) + "\n"


def test_a_variable_a_link_of_another_chain_shares_is_read_for_no_chain(
        tmp_path):
    """The chains half. The project pins `openss` alone, and its spec leg
    records a chain beginning at `openß`: a link of the run, though no
    classification consults that chain. The variable was read for `openss`,
    and `openß`'s tree broke `codexQuill`'s chain, exit 1. The NOTE names
    the other chain's link too (#990)."""
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
        name="codexQuill", holder=SS, held="openQuill") + said_shared(
        GATE_SHARED, "SHAPE_PIN_SOURCE_OPENSS", SS, SHARP) + "\n"


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
    leg records, whatever that leg's name claims), there with its owner,
    `opensoft/`, before it, which is still that link (`repo_basename`), or
    as a pin on no chain."""
    as_a_descendant_by_chain(project, first=SS)
    (project / "contracts" / f"{SS}-pin.yaml").write_text(
        "schema_version: 1\nkind: pinned_contract_manifest\n",
        encoding="utf-8")
    owners = {"chain": "", "qualified-chain": "opensoft/"}
    if where in owners:
        anchor = "      role: spec\n      also_matches: []\n"
        added = (f"{anchor}      referent_chain: "
                 f"[{owners[where]}{SHARP}, openQuill]\n")
    else:
        anchor = f"neutral_product_pins:\n  - {SS}\n"
        added = f"{anchor}  - {SHARP}\n"
    written = project / "project.yaml"
    text = written.read_text(encoding="utf-8")
    assert anchor in text, f"fixture drift: {anchor!r} not in project.yaml"
    written.write_text(text.replace(anchor, added, 1), encoding="utf-8")
    return project


@pytest.mark.parametrize("variable", HANDED)
@pytest.mark.parametrize("where", ["chain", "qualified-chain", "pin"])
def test_the_manifest_gate_reads_a_shared_variable_for_no_chain(
        project, monkeypatch, tmp_path, where, variable):
    """The same defect in the root's own validator, which reads every leg's
    chain: set to `openß`'s tree, the variable was read for `openss` and
    broke `codexDox`'s chain, exit 1; unset, it was offered. It is read for
    neither now, and the holder is offered a checkout beside the root
    alone. The products are read by `repo_basename` (RV981's S2): this
    validator hands them over as its manifest spells them, and read whole,
    the owner-qualified link names `SHAPE_PIN_SOURCE_OPENSOFT_OPENSS` and
    shares nothing. Set, one note names it and both products, and fails
    nothing (#990); empty or unset, nothing does."""
    clear_ambient_pin_sources(monkeypatch)
    root = a_root_sharing_one_variable(project, where)
    result = validate(root, handed(tmp_path, variable, "openQuill"))
    assert result.returncode == 0, result.stderr
    assert "manifest ok" in result.stdout
    assert manifest_warnings(result) == [UNREACHED.format(
        holder=SS, held="openDox",
        offer=f"a checkout of {SS} beside this root would let it be read")]
    assert collision_lines(result) == ([said_shared(
        ROOT_SHARED, "SHAPE_PIN_SOURCE_OPENSS", SS, SHARP)]
        if variable == "set" else []), result.stderr


# --- #990: a set variable the guard passes over is said, once ----------------

#: #990's probes of the gate, `MedxGlass --role assembly`, each as `(--pins,
#: --referent-chain, what the tree `SHAPE_PIN_SOURCE_OPEN_X` names declares,
#: the chain's status with it set, and the products the NOTE names)`. Unset,
#: every chain is declared-unverified and nothing is said.
PROBES = {
    "two-links-of-one-chain": ("open-x", "open-x,open_x,openGlass", "open_x",
                               "declared-unverified", ("open-x", "open_x")),
    "a-link-and-a-declared-pin": ("open-x,open_x", "open-x,openGlass",
                                  "openGlass", "declared-unverified",
                                  ("open-x", "open_x")),
    "a-variable-to-itself": ("open-x", "open-x,openGlass", "openGlass",
                             "verified", ()),
}


def probe(tmp_path: Path, pins: str, chain: str, env: dict, *args: str):
    """The gate on `MedxGlass` from an empty folder, so that nothing beside
    it answers for a link."""
    here = tmp_path / "here"
    here.mkdir(exist_ok=True)
    return run_script(VALIDATOR, "MedxGlass", "--role", "assembly", "--pins",
                      pins, "--referent-chain", chain, *args, cwd=here,
                      env=env)


def open_x_tree(tmp_path: Path, declares: str) -> dict:
    """`SHAPE_PIN_SOURCE_OPEN_X` set to a tree declaring `declares`."""
    return {"SHAPE_PIN_SOURCE_OPEN_X": str(
        tree(tmp_path / "trees" / "open-x", declares))}


@pytest.mark.parametrize("variable", [True, False], ids=["set", "unset"])
@pytest.mark.parametrize("case", PROBES)
def test_the_gate_says_a_set_variable_it_passed_over_once(tmp_path, case,
                                                         variable):
    """#990's probes. Two links of one chain share the variable, or a link
    and a declared pin do (#909): set, the output was the same bytes as
    unset, and the second chain, verified through the variable before
    #909, became declared-unverified with no word why. One NOTE names the
    variable and both products now, and the exit is the same set or unset.
    The control, a variable a link has to itself, is read and says
    nothing."""
    pins, chain, declares, status, products = PROBES[case]
    env = open_x_tree(tmp_path, declares) if variable else {}
    result = probe(tmp_path, pins, chain, env, "--explain")
    assert result.returncode == 0, result.stderr
    assert f"   [{status if variable else 'declared-unverified'}]\n" in (
        result.stdout), result.stdout
    assert collision_lines(result) == (
        [said_shared(GATE_SHARED, "SHAPE_PIN_SOURCE_OPEN_X", *products)]
        if variable and products else []), result.stderr


@pytest.mark.parametrize("args", [
    pytest.param(("--explain", "--link-source-label=--pin-source"),
                 id="under-a-label"),
    pytest.param(("--quiet",), id="quiet"),
])
def test_the_gate_says_it_nowhere_it_says_no_note(tmp_path, args):
    """`--quiet` drops it with every NOTE. Under a label the caller speaks
    for someone else in its own sources: setup's step (4) speaks for the
    scaffold, which asks the guard over its one chain and reads a variable
    a declared pin shares, and its words for a link say where another link
    shares the variable (#990)."""
    pins, chain, declares, _status, _products = PROBES[
        "two-links-of-one-chain"]
    result = probe(tmp_path, pins, chain, open_x_tree(tmp_path, declares),
                   *args)
    assert result.returncode == 0, result.stderr
    assert "link-source-collides" not in result.stdout + result.stderr


def test_a_variable_only_a_chains_end_shares_is_not_said(tmp_path):
    """Only a holder's declaration is read, so a variable passed over for
    the chain's END alone decided nothing (#990). `openGla<SHARP S>`, a
    declared pin, and `openGlass`, the chain's end, are two pin files and
    one `SHAPE_PIN_SOURCE_OPENGLASS`."""
    sharp = "openGla" + chr(0xDF)
    env = {"SHAPE_PIN_SOURCE_OPENGLASS": str(
        tree(tmp_path / "trees" / "openGlass", "openGlass"))}
    result = probe(tmp_path, f"openXglass,{sharp}", "openXglass,openGlass",
                   env, "--explain")
    assert result.returncode == 0, result.stderr
    assert "   [declared-unverified]\n" in result.stdout, result.stdout
    assert collision_lines(result) == [], result.stderr


@pytest.mark.parametrize("chain, run, kept", [
    pytest.param(("open-x", "openGlass"), ("open_x",),
                 {"SHAPE_PIN_SOURCE_OPEN_X": ["open-x", "open_x"]},
                 id="a-holder"),
    pytest.param(("openXglass", "openGlass"), ("openGla" + chr(0xDF),), {},
                 id="the-end-alone"),
])
def test_the_root_keeps_a_variable_only_for_a_holder(monkeypatch, chain, run,
                                                     kept):
    """The root's copy keeps a set variable the guard passes over only where
    a holder is among the products that share it, as the gate does (#990):
    the chain's end holds no pin. No scaffolded root's chain can show it,
    since nothing folds onto `openDox`'s variable but its own spellings."""
    clear_ambient_pin_sources(monkeypatch)
    for variable in ("SHAPE_PIN_SOURCE_OPEN_X", "SHAPE_PIN_SOURCE_OPENGLASS"):
        monkeypatch.setenv(variable, "somewhere")
    module = load_without_bytecode(TEMPLATE_MANIFEST,
                                   "chain_pin_sources_shared")
    shared: dict = {}
    module._record_shared_variables(shared, chain, run)
    assert {variable: list(named.values())
            for variable, named in shared.items()} == kept


@pytest.mark.parametrize("library", ["v1.1.1", "this-checkout"])
def test_each_copy_says_it_only_where_the_library_passed_it_over(
        project, monkeypatch, tmp_path, library):
    """THE SKEW RULE (#990). A library with no `run_products=` asks the
    guard over the chain alone, so it READS a variable that a declared pin
    shares with a holder: beside v1.1.1's library the chain is verified
    through it, and neither copy says it was read for none. Beside this
    checkout's library it is passed over, and each copy says so once."""
    clear_ambient_pin_sources(monkeypatch)
    root = a_root_sharing_one_variable(project, "pin")
    if library == "v1.1.1":
        (root / "scripts" / "repo_shape.py").write_bytes(library_at(V1_1_1))
    env = {"SHAPE_PIN_SOURCE_OPENSS": str(
        tree(tmp_path / "trees" / SS, "openDox"))}
    passed_over = library == "this-checkout"
    own = validate(root, env)
    assert own.returncode == 0, own.stderr
    assert bool(manifest_warnings(own)) is passed_over, own.stderr
    assert collision_lines(own) == ([said_shared(
        ROOT_SHARED, "SHAPE_PIN_SOURCE_OPENSS", SS, SHARP)]
        if passed_over else []), own.stderr
    gate = run_script(root / "scripts" / "validate-repository-naming.py",
                      "--project", "project.yaml", cwd=root, env=env)
    assert gate.returncode == 0, gate.stderr
    assert collision_lines(gate) == ([said_shared(
        GATE_SHARED, "SHAPE_PIN_SOURCE_OPENSS", SS, SHARP)]
        if passed_over else []), gate.stderr


def test_the_doctor_reads_the_roots_note_as_a_note(project, monkeypatch,
                                                   tmp_path):
    """The root's note is spelled as `validate-pins.py` spells one, so the
    doctor's `manifest` row reads it as a note of its own (`reported`), as
    its `pins` row reads `neutral-pin-source-collides`. A line it does not
    know as an item it reads as the tail of the WARNING before it."""
    clear_ambient_pin_sources(monkeypatch)
    root = a_root_sharing_one_variable(project, "pin")
    result = validate(root, sharp_tree(tmp_path, "openQuill"))
    assert result.returncode == 0, result.stderr
    doctor = load_without_bytecode(REPO / "shape-doctor.py",
                                   "chain_pin_sources_doctor")
    said = doctor.reported(result.stdout + result.stderr)
    assert [key for key, _text in said] == ["warnings", "notes"], said
    assert said[1][1].startswith(
        "link-source-collides: SHAPE_PIN_SOURCE_OPENSS is set, but "), said


@pytest.mark.parametrize("where", ["chain", "pin"])
def test_the_standard_reads_the_roots_note_as_no_finding(project, monkeypatch,
                                                        tmp_path, where):
    """RV1011's SHOULD-1 on #990. The standard asks the root's validator
    in process (`shape_materialize._validator_notes`, behind the
    scaffold's `manifest_invalid` and adopt's `manifest_judged`), and it
    dropped only the WARNINGs `_findings` returns. So the root's
    `link-source-collides` note read as a finding: `manifest_invalid`
    gave it as a refusal and `manifest_judged` said None, where the
    root's own `main` counts it as none. The root here is its own
    template: its `project.yaml` holds no placeholder."""
    clear_ambient_pin_sources(monkeypatch)
    root = a_root_sharing_one_variable(project, where)
    for variable, path in sharp_tree(tmp_path, "openQuill").items():
        monkeypatch.setenv(variable, path)
    policy = NamingPolicy.load(REPO / "contracts" / "repository-naming.yaml")
    manifest = shape_materialize.parse_yaml(
        (root / "project.yaml").read_text(encoding="utf-8"))
    said = shape_materialize.manifest_validator(root)._findings(
        manifest, policy, None)
    assert [note for note in said if "link-source-collides" in note] == [
        said_shared(ROOT_SHARED, "SHAPE_PIN_SOURCE_OPENSS", SS, SHARP)], said
    assert shape_materialize._validator_notes({}, policy, root, ()) == []
    assert shape_materialize.manifest_invalid({}, policy, {}, root) == []
    assert shape_materialize.manifest_judged({}, policy, root) == frozenset()


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


def scaffold_reading(monkeypatch, tmp_path: Path, env: dict, *args: str):
    """The issue's probe, `--pin openKdox@<sha> --referent-chain
    'open<KELVIN SIGN>dox,openInk'`, run by `scaffold_pinning` with `env`
    given to the scaffold: that helper passes none, and `run_script` blanks
    every `SHAPE_PIN_SOURCE_<PRODUCT>` its caller does not name."""
    monkeypatch.setattr(test_chain_link_fold, "run_script",
                        functools.partial(run_script, env=env))
    return scaffold_pinning(tmp_path, "openKdox", f"{KDOX},openInk", *args)


def test_the_kelvin_link_is_not_read_through_another_products_variable(
        monkeypatch, tmp_path):
    """RV981's S1: the fix changes which variable is read for that link.
    Read as typed, `open<KELVIN SIGN>dox` was read through
    `SHAPE_PIN_SOURCE_OPEN_DOX`: the Kelvin sign is upper case and not in
    `[A-Z0-9_]`, so `pin_source_env_name` turns it into `_`, and that is the
    variable of `open-dox`, `open_dox` and `open.dox`. Set to a tree
    declaring `openQuill`, it refused a chain that holds,
    `chain-not-declared`, exit 2. The link is the pin `openKdox` now, so
    that variable is not its own, and the `--pin-source` verifies it."""
    other = tree(tmp_path / "trees" / "open_dox", "openQuill")
    result = scaffold_reading(monkeypatch, tmp_path,
                              {"SHAPE_PIN_SOURCE_OPEN_DOX": str(other)},
                              "--dry-run")
    assert result.returncode == 0, result.stderr + result.stdout
    assert ("reaching openInk through the declared pin chain openKdox → "
            "openInk") in result.stdout, result.stdout
    assert "declared-unverified" not in result.stderr, result.stderr
    assert KELVIN not in result.stdout + result.stderr


def test_the_kelvin_link_is_read_through_its_pins_variable(monkeypatch,
                                                           tmp_path):
    """The reverse: `SHAPE_PIN_SOURCE_OPENKDOX`, the pin's own variable, is
    read for that link before its `--pin-source` (`resolve_link_source`'s
    rule 2), so a tree there declaring `openQuill` refuses the chain."""
    other = tree(tmp_path / "trees" / "openKdox", "openQuill")
    result = scaffold_reading(monkeypatch, tmp_path,
                              {"SHAPE_PIN_SOURCE_OPENKDOX": str(other)},
                              "--dry-run")
    assert result.returncode == 2, result.stderr + result.stdout
    assert ("REFUSED chain-not-declared: --referent-chain openKdox,openInk: "
            "the declared chain openKdox → openInk is broken (openKdox "
            "declares openQuill, not openInk)\n") in result.stderr, (
        result.stderr)
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
