# SPDX-License-Identifier: Apache-2.0
"""What a chain link that is not reachable is offered, by each caller in its
own sources, and how the naming gate spells what it prints (#661).

  * L2-68. The root's `validate-manifest.py` printed the naming gate's
    words, "a sibling checkout, SHAPE_PIN_SOURCE_<LINK>, or --link-source
    <link>=<path> would let it be read", and it takes no `--link-source`:
    typed as printed, `unrecognized arguments`. It offers the variable and
    a checkout beside the root, the two it reads, and passes them as
    `remedies=` only where its root's `scripts/repo_shape.py` takes the
    keyword, so it still runs beside an older library.
  * L2-75. Setup's step (4) showed the gate's offer and its `(--link-source)`
    label for a value typed as `--pin-source`. The gate takes the caller's
    label for a bare source (`--link-source-label`) and the caller's words
    for each holder (`--link-remedy`); setup's own half is in
    `tests/conftest.py` (`assert_step_four_speaks_in_the_plans_words`).
  * L2-69. The gate named `--link-source` values and paths raw, so an ESC
    reached the terminal. One row per print, each with an ESC.
  * #907. `--link-remedy` split its value at the first `=`, so a link
    holding one lost its words to a link no chain names (U170), or to a
    shorter link a chain names too (rv949 on #949); it kept the
    blanks around its words, and a remedy no holder used was dropped with
    no NOTE (U173). And no row gave a labelled run a KEYED `--link-source`,
    so naming that by the label too passed every row (U174).

No network and no GitHub.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from conftest import (REPO, clear_ambient_pin_sources, load_without_bytecode,
                      run_script)
from test_link_source_chain_defaults import (  # noqa: F401
    VALIDATOR, manifest, naming, tree,
)
from test_manifest_validator import as_a_descendant_by_chain, edit, link_tree
from test_pinned_copy_text import CONTROL_ARGV, CONTROL_NAMES

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import shown_path  # noqa: E402

TEMPLATE_MANIFEST = (REPO / "templates" / "assembly-root" / "scripts" /
                     "validate-manifest.py")

#: The sentence a holder's `declared-unverified` WARNING ends with, and what
#: the root's `validate-manifest.py` offers in it (L2-68).
UNREACHED = ("declared-unverified: {holder} declaring a pin on {held} is a "
             "fact in {holder}'s own tree, which is not reachable here "
             "({offer}). The recorded chain still classifies.")
OWN_OFFER = ("SHAPE_PIN_SOURCE_{var}, or a checkout of {link} beside this "
             "root, would let it be read")
#: The naming gate's own words, which an older library still prints.
GATE_OFFER = ("a sibling checkout, SHAPE_PIN_SOURCE_{var}, or --link-source "
              "{link}=<path> would let it be read")

#: Libraries older than the copies: `remedies=` is new with #610 (#634).
#: `pre-634` is main just before #634's squash, the first parent of
#: `30676c90`; `v1.0.1` is the release every project pins today.
OLDER_LIBRARIES = {
    "pre-634": "de926142e69dcd4fcb986f57573f4f35c276c966",
    "v1.0.1": "v1.0.1",
}


def offer(words: str, link: str) -> str:
    return words.format(var=link.upper(), link=link)


def manifest_warnings(result) -> list[str]:
    return [line.partition("leg 'assembly': ")[2]
            for line in result.stderr.splitlines()
            if line.startswith("WARNING naming-referent-chain: ")]


def a_chain_root(project, chain=("openXdox", "openDox")):
    """The scaffolded root recast as `codexDox`, pinning `openXdox` with its
    pin file, and recording `chain`."""
    as_a_descendant_by_chain(project)
    (project / "contracts" / "openxdox-pin.yaml").write_text(
        "schema_version: 1\nkind: pinned_contract_manifest\n")
    if tuple(chain) != ("openXdox", "openDox"):
        # The leg's own record, on a line of its own: the manifest's comment
        # block above it spells a chain the same way.
        edit(project, "\n      referent_chain: [openXdox, openDox]\n",
             f"\n      referent_chain: [{', '.join(chain)}]\n")
    return project


# --- L2-68: the root's validate-manifest.py offers what it reads ------------

@pytest.mark.parametrize("chain", [
    pytest.param(("openXdox", "openDox"), id="two-links"),
    pytest.param(("openXdox", "openYdox", "openDox"), id="three-links"),
    pytest.param(("opensoft/openXdox", "openDox"), id="qualified"),
])
def test_the_manifest_gate_offers_the_sources_it_reads(project, monkeypatch,
                                                       chain):
    """Each holder is offered its variable and a checkout beside the root,
    in its own words, and nothing names `--link-source`. A link recorded
    `<org>/<name>` is the link `<name>`, as the chain's own reader takes it
    (`_chain_links`): its entry, and the words, go by the name alone."""
    clear_ambient_pin_sources(monkeypatch)
    root = a_chain_root(project, chain)
    result = run_script(root / "scripts" / "validate-manifest.py", cwd=root)
    assert result.returncode == 0, result.stderr
    assert "manifest ok" in result.stdout
    names = [link.rpartition("/")[2] for link in chain]
    assert manifest_warnings(result) == [
        UNREACHED.format(holder=holder, held=held,
                         offer=offer(OWN_OFFER, holder))
        for holder, held in zip(names, names[1:])]
    assert "--link-source" not in result.stderr


@pytest.mark.parametrize("where", ["variable", "beside-the-root"])
def test_each_source_the_manifest_gate_offers_reads_the_link(project,
                                                             monkeypatch,
                                                             tmp_path, where):
    """The offer is one the validator HAS: either source it names, given
    the link's tree, verifies the chain."""
    clear_ambient_pin_sources(monkeypatch)
    root = a_chain_root(project)
    env = {}
    if where == "variable":
        env["SHAPE_PIN_SOURCE_OPENXDOX"] = str(
            link_tree(tmp_path / "elsewhere" / "openXdox", "openDox"))
    else:
        link_tree(root.parent / "openXdox", "openDox")
    result = run_script(root / "scripts" / "validate-manifest.py", cwd=root,
                        env=env)
    assert result.returncode == 0, result.stderr
    assert "WARNING" not in result.stderr, result.stderr


@pytest.mark.parametrize("first, keyed", [
    pytest.param("open-x", "open-x", id="lowercase"),
    pytest.param("Open-X", "open-x", id="mixed-case"),
])
def test_a_shared_variable_is_not_offered_by_the_manifest_gate(first, keyed):
    """Two holders that share one variable (#275): the validator reads it
    for neither, so neither is offered it, and the entry is keyed by
    `pin_product_key`, the key `_chain_link_findings` looks it up by."""
    module = load_without_bytecode(TEMPLATE_MANIFEST, "chain_remedy_manifest")
    assert module._link_remedies((first, "open_x", "openDox")) == {
        keyed: f"a checkout of {first} beside this root would let it be read",
        "open_x": "a checkout of open_x beside this root would let it be read"}


def older_library(ref: str) -> bytes:
    """`scripts/repo_shape.py` at `ref`, or a skip where this checkout does
    not hold that history. It must be a library with no `remedies` at all,
    or the row would test nothing older than the copies."""
    shown = subprocess.run(["git", "show", f"{ref}:scripts/repo_shape.py"],
                           cwd=str(REPO), capture_output=True, check=False)
    if shown.returncode != 0:
        pytest.skip(f"needs {ref} in this checkout's history")
    assert b"def link_pins_from_trees(" in shown.stdout, ref
    assert b"remedies" not in shown.stdout, ref
    return shown.stdout


@pytest.mark.parametrize("ref", list(OLDER_LIBRARIES.values()),
                         ids=list(OLDER_LIBRARIES))
def test_the_new_copies_run_beside_an_older_library(project, monkeypatch, ref):
    """THE SKEW RULE. A root may keep a `scripts/repo_shape.py` older than its
    copies (`update-shape.py apply --accept-local`), and before #610 the
    library had no `remedies=`: passing it ended both validators in a
    `TypeError`. Beside such a library each runs, and its WARNING keeps that
    library's words."""
    clear_ambient_pin_sources(monkeypatch)
    root = a_chain_root(project)
    (root / "scripts" / "repo_shape.py").write_bytes(older_library(ref))
    own = run_script(root / "scripts" / "validate-manifest.py", cwd=root)
    assert own.returncode == 0, own.stderr
    assert "Traceback" not in own.stderr, own.stderr
    assert manifest_warnings(own) == [UNREACHED.format(
        holder="openXdox", held="openDox", offer=offer(GATE_OFFER,
                                                       "openXdox"))]
    gate = run_script(root / "scripts" / "validate-repository-naming.py",
                      "--project", "project.yaml", "--link-remedy",
                      "openXdox=OURS would do", cwd=root)
    assert gate.returncode == 0, gate.stderr
    assert "Traceback" not in gate.stderr, gate.stderr
    assert offer(GATE_OFFER, "openXdox") in gate.stderr, gate.stderr


# --- L2-75: the gate takes the caller's label and words ----------------------

THREE = ("--pins", "openXdox", "--referent-chain", "openXdox,openYdox,openInk")


def gate_warnings(result) -> list[str]:
    return [line.partition("codexInk: ")[2]
            for line in result.stderr.splitlines()
            if line.startswith("WARNING codexInk: ")]


def test_the_gate_offers_each_holder_the_callers_words(tmp_path, monkeypatch):
    """One offer per holder, each in its own words, found by
    `pin_product_key` (the second is typed in capitals)."""
    clear_ambient_pin_sources(monkeypatch)
    result = naming(tmp_path, *THREE, "--link-remedy",
                    "openXdox=FIRST would do", "--link-remedy",
                    "OPENYDOX=LATER would do", "codexInk")
    assert result.returncode == 0, result.stderr
    assert gate_warnings(result) == [
        UNREACHED.format(holder="openXdox", held="openYdox",
                         offer="FIRST would do"),
        UNREACHED.format(holder="openYdox", held="openInk",
                         offer="LATER would do")]
    assert "--link-source" not in result.stderr
    assert "NOTE" not in result.stderr, result.stderr


def test_a_holder_given_no_words_keeps_the_gates_own(tmp_path, monkeypatch):
    clear_ambient_pin_sources(monkeypatch)
    result = naming(tmp_path, *THREE, "--link-remedy",
                    "openYdox=LATER would do", "codexInk")
    assert gate_warnings(result) == [
        UNREACHED.format(holder="openXdox", held="openYdox",
                         offer=offer(GATE_OFFER, "openXdox")),
        UNREACHED.format(holder="openYdox", held="openInk",
                         offer="LATER would do")]


def test_the_last_words_for_a_link_win(tmp_path, monkeypatch):
    clear_ambient_pin_sources(monkeypatch)
    result = naming(tmp_path, *THREE, "--link-remedy", "openXdox=A",
                    "--link-remedy", "openXdox=B", "codexInk")
    assert gate_warnings(result)[0].endswith(
        "not reachable here (B). The recorded chain still classifies.")


@pytest.mark.parametrize("value", [
    pytest.param("openXdox", id="no-equals"),
    pytest.param("=words", id="no-link"),
    pytest.param("openXdox= ", id="no-words"),
])
def test_words_that_are_not_link_equals_text_are_refused(tmp_path, value):
    result = naming(tmp_path, *THREE, "--link-remedy", value, "codexInk")
    assert result.returncode == 2, result.stderr
    assert "argument --link-remedy:" in result.stderr, result.stderr
    assert "is not LINK=TEXT" in result.stderr, result.stderr


def test_a_labelled_bare_source_is_named_by_its_label(tmp_path, monkeypatch):
    """A source the gate could not read, named by the caller's flag."""
    clear_ambient_pin_sources(monkeypatch)
    nowhere = tmp_path / "nowhere"
    result = naming(tmp_path, *THREE, "--link-source", str(nowhere),
                    "--link-source-label=--pin-source", "codexInk")
    assert (f"WARNING link-source-unreadable: {nowhere} (--pin-source) could "
            "not answer for openXdox: no such file or directory\n"
            ) in result.stderr, result.stderr


def test_a_labelled_source_holding_an_equals_is_not_said_to_be_a_path(
        tmp_path, monkeypatch):
    """The caller's flag has no `LINK=` form, so "It was read as a PATH"
    would be about a reading nobody asked for."""
    clear_ambient_pin_sources(monkeypatch)
    result = naming(tmp_path, *THREE, "--link-source", "./openXdox=layer",
                    "--link-source-label=--pin-source", "codexInk")
    assert ("WARNING link-source-unreadable: openXdox=layer (--pin-source) "
            "could not answer for openXdox") in result.stderr, result.stderr
    assert "read as a PATH" not in result.stderr, result.stderr


def test_an_unused_labelled_source_is_noted_by_its_label(tmp_path,
                                                         monkeypatch):
    """The first link's variable answered, so the bare source was not asked:
    the NOTE names it by the caller's flag, and lists only the sources such
    a caller has."""
    clear_ambient_pin_sources(monkeypatch)
    first = tree(tmp_path / "trees" / "openXdox", "openInk")
    spare = tree(tmp_path / "spare", "openInk")
    result = run_script(VALIDATOR, "--pins", "openXdox", "--referent-chain",
                        "openXdox,openInk", "--link-source", str(spare),
                        "--link-source-label=--pin-source", "codexInk",
                        cwd=tmp_path,
                        env={"SHAPE_PIN_SOURCE_OPENXDOX": str(first)})
    assert (f"NOTE --pin-source {spare}: not used — each link whose own "
            "declaration is read had a more specific source "
            "(SHAPE_PIN_SOURCE_<PRODUCT>, or a checkout beside the project)."
            "\n") in result.stderr, result.stderr
    assert "--link-source" not in result.stderr


def test_a_labelled_run_names_a_keyed_source_by_its_own_flag(tmp_path,
                                                             monkeypatch):
    """#907, U174: the label names the bare PATH and nothing else. A keyed
    value is the person's own `--link-source <link>=PATH`, so it is named
    `(--link-source openXdox=...)` under a label too. Every labelled row
    above passes a bare value, so naming a keyed one `(--pin-source)`, a
    flag nobody typed for it, passed them all."""
    clear_ambient_pin_sources(monkeypatch)
    missing = tmp_path / "missing"
    result = naming(tmp_path, *THREE, "--link-source-label=--pin-source",
                    "--link-source", f"openXdox={missing}", "codexInk")
    assert (f"WARNING link-source-unreadable: {missing} (--link-source "
            "openXdox=...) could not answer for openXdox: no such file or "
            "directory\n") in result.stderr, result.stderr
    assert "(--pin-source)" not in result.stderr, result.stderr


# --- #907: --link-remedy's link is the longest one a chain here names -------

#: A chain whose middle link holds `=`, as setup's step (4) hands one over
#: (U170). Step (5) refuses it as `chain-link-malformed`; the gate asks no
#: link's form.
EQUALS = ("--pins", "openXdox", "--referent-chain", "openXdox,open=y,openInk")


@pytest.mark.parametrize("chain, remedy, holder, held, words", [
    pytest.param(EQUALS, "open=y=OURS for y", "open=y", "openInk",
                 "OURS for y", id="a-link-holding-an-equals"),
    pytest.param(EQUALS, "OPEN=Y=OURS for y", "open=y", "openInk",
                 "OURS for y", id="in-capitals"),
    pytest.param(EQUALS, " open=y =OURS for y", "open=y", "openInk",
                 "OURS for y", id="padded"),
    pytest.param(THREE, "openXdox=a=b", "openXdox", "openYdox", "a=b",
                 id="words-holding-an-equals"),
])
def test_a_remedys_link_is_the_one_a_chain_names(tmp_path, monkeypatch, chain,
                                                 remedy, holder, held, words):
    """U170: the link ends at the LAST `=` that leaves a link of a chain
    here before it, stripped, and the rest is the words, `=` and all. Split
    at the first `=`, `open=y=OURS for y` was the words `y=OURS for y` for a
    link `open` that no chain names, and `open=y` was offered the gate's own
    `--link-source open=y=<path>`, a flag setup does not take. Unstripped,
    ` open=y ` names no link, and the value fell back to `open`."""
    clear_ambient_pin_sources(monkeypatch)
    result = naming(tmp_path, *chain, "--link-remedy", remedy, "codexInk")
    assert result.returncode == 0, result.stderr
    assert UNREACHED.format(holder=holder, held=held, offer=words) in (
        gate_warnings(result)), result.stderr
    assert f"--link-source {holder}=" not in result.stderr, result.stderr
    assert "NOTE" not in result.stderr, result.stderr


def test_each_link_is_given_its_own_words_where_one_holds_another(
        tmp_path, monkeypatch):
    """NIT-1 (rv949 on #949): in a chain naming `openXdox` and `openXdox=y`
    both, the longest link is read first, so each is given its own words.
    Read from the first `=`, `openxdox=y=SECOND words` was `y=SECOND words`
    for `openXdox`, which replaced its `FIRST words`, and `openXdox=y` kept
    the gate's own. Step (5) refuses such a chain anyway."""
    clear_ambient_pin_sources(monkeypatch)
    result = naming(tmp_path, "--pins", "openXdox", "--referent-chain",
                    "openXdox,openXdox=y,openInk",
                    "--link-remedy=openxdox=FIRST words",
                    "--link-remedy=openxdox=y=SECOND words", "codexInk")
    assert result.returncode == 0, result.stderr
    assert gate_warnings(result) == [
        UNREACHED.format(holder="openXdox", held="openXdox=y",
                         offer="FIRST words"),
        UNREACHED.format(holder="openXdox=y", held="openInk",
                         offer="SECOND words")], result.stderr
    assert "NOTE" not in result.stderr, result.stderr


def test_a_remedys_words_are_stripped(tmp_path, monkeypatch):
    """U173: the words are offered without the blanks around them, as the
    link is read without its own. `openXdox= padded ` offered
    `( padded )`."""
    clear_ambient_pin_sources(monkeypatch)
    result = naming(tmp_path, *THREE, "--link-remedy", "openXdox= padded ",
                    "codexInk")
    assert gate_warnings(result)[0] == UNREACHED.format(
        holder="openXdox", held="openYdox", offer="padded"), result.stderr


@pytest.mark.parametrize("args, why", [
    pytest.param((*THREE, "--link-remedy", "openNope=words", "codexInk"),
                 "`openNope` is not a link of a referent chain here (links: "
                 "openXdox, openYdox, openInk)", id="a-link-no-chain-names"),
    pytest.param((*THREE, "--link-remedy", "openNope=words",
                  "--link-source-label=--pin-source", "codexInk"),
                 None, id="under-a-label"),
    pytest.param((*THREE, "--link-remedy", "openInk=words", "codexInk"),
                 "no name classified here reads openInk's own declaration",
                 id="the-last-link"),
    # Named as the chain spells it, not as typed (rv949 on #949, G3).
    pytest.param((*THREE, "--link-remedy", "OPENINK=words", "codexInk"),
                 "no name classified here reads openInk's own declaration",
                 id="the-last-link-in-capitals"),
    # `open=y` leaves no words, so it is not read as the link, and the text
    # before the first `=` is, which no chain names (rv949 on #949, G1).
    pytest.param((*EQUALS, "--link-remedy", "open=y=", "codexInk"),
                 "`open` is not a link of a referent chain here (links: "
                 "openXdox, open=y, openInk)", id="a-link-left-no-words"),
    pytest.param((*THREE, "--link-remedy", "openXdox=words", "Atlas"),
                 "no name classified here reads openXdox's own declaration",
                 id="a-holder-no-name-reads"),
    pytest.param(("--link-remedy", "openXdox=words", "codexInk"),
                 "no name classified here records a referent chain",
                 id="no-chain"),
])
def test_a_remedy_no_holder_used_is_noted(tmp_path, monkeypatch, args, why):
    """U173: a `--link-remedy` no holder's lookup asked for is a NOTE, as a
    `--link-source` no link used is, named as typed, with why. Under a
    label it is not: a caller's remedies are its own words (setup's step
    (4) passes one per holder), and the NOTE would name `--link-remedy`, a
    flag the person never typed. On main each was dropped without a word."""
    clear_ambient_pin_sources(monkeypatch)
    result = naming(tmp_path, *args)
    noted = [line for line in result.stderr.splitlines()
             if line.startswith("NOTE --link-remedy ")]
    remedy = args[args.index("--link-remedy") + 1]
    assert noted == ([] if why is None else [
        f"NOTE --link-remedy {remedy}: not used — {why}."]), result.stderr


@pytest.mark.parametrize("remedies, words, noted", [
    pytest.param(("openXdox=A", "OPENXDOX=B"), "B",
                 ["NOTE --link-remedy openXdox=A: not used — the later "
                  "`--link-remedy OPENXDOX=B` replaced it."], id="a-b"),
    # A, typed again, is the last value: it replaced B, and nothing replaced
    # it (rv949 on #949, G4).
    pytest.param(("openXdox=A", "openXdox=B", "openXdox=A"), "A",
                 ["NOTE --link-remedy openXdox=B: not used — the later "
                  "`--link-remedy openXdox=A` replaced it."], id="a-b-a"),
    # The same value twice is one value, which nothing replaced (G5).
    pytest.param(("openXdox=A", "openXdox=A"), "A", [], id="a-a"),
])
def test_a_remedy_a_later_one_replaced_is_noted(tmp_path, monkeypatch,
                                                remedies, words, noted):
    """The last value for a link wins, found by `pin_product_key`, and the
    one it replaced is a NOTE saying so, as a replaced `--link-source` is.
    A value typed again is the one that wins, and is never said to have
    been replaced, by another value or by itself."""
    clear_ambient_pin_sources(monkeypatch)
    result = naming(tmp_path, *THREE, *(arg for remedy in remedies
                                        for arg in ("--link-remedy", remedy)),
                    "codexInk")
    assert gate_warnings(result)[0] == UNREACHED.format(
        holder="openXdox", held="openYdox", offer=words), result.stderr
    assert [line for line in result.stderr.splitlines()
            if line.startswith("NOTE ")] == noted, result.stderr


def test_a_remedy_for_a_holder_whose_tree_answered_is_not_noted(tmp_path,
                                                                monkeypatch):
    """A holder that was asked used its words, whether its tree answered or
    not: the words are offered only where it did not, which is the disk's
    answer and not a mistake in the value."""
    clear_ambient_pin_sources(monkeypatch)
    first = tree(tmp_path / "trees" / "openXdox", "openYdox")
    result = naming(tmp_path, *THREE, "--link-source", f"openXdox={first}",
                    "--link-remedy", "openXdox=words", "codexInk")
    assert result.returncode == 0, result.stderr
    assert "words" not in result.stderr, result.stderr
    assert "NOTE" not in result.stderr, result.stderr


# --- L2-69: every --link-source value and path the gate prints is spelled ---

def assert_clean(result) -> None:
    said = result.stdout + result.stderr
    assert "\x1b" not in said, said
    assert not [line for line in said.splitlines()
                if line.startswith("WARNING forged-line")], said


@CONTROL_ARGV
@pytest.mark.parametrize("name", CONTROL_NAMES)
def test_a_key_read_as_a_path_is_spelled(tmp_path, monkeypatch, name):
    """`read_as_path`: the text before `=`, which names no link."""
    clear_ambient_pin_sources(monkeypatch)
    result = naming(tmp_path, *THREE, "--link-source", f"{name}=b/openXdox",
                    "codexInk")
    assert_clean(result)
    assert f"It was read as a PATH: `{shown_path(name)}` is not a link" in (
        result.stderr), result.stderr


@CONTROL_ARGV
@pytest.mark.parametrize("name", CONTROL_NAMES)
def test_a_keyed_value_that_is_also_a_directory_is_spelled(tmp_path,
                                                           monkeypatch, name):
    """`_also_a_directory`: the value, in the sentence and in the command."""
    clear_ambient_pin_sources(monkeypatch)
    typed = f"openXdox={name}"
    (tmp_path / typed).mkdir()
    result = naming(tmp_path, *THREE, "--link-source", typed, "codexInk")
    assert_clean(result)
    named = shown_path(typed)
    assert (f"`{named}` is also a directory; `--link-source ./{named}` reads "
            "it as one.") in result.stderr, result.stderr


@CONTROL_ARGV
@pytest.mark.parametrize("name", CONTROL_NAMES)
def test_a_variable_the_gate_could_not_read_is_spelled(tmp_path, name):
    """`unread_lines`' second loop, for `SHAPE_PIN_SOURCE_<LINK>`."""
    folder = tmp_path / name
    result = run_script(VALIDATOR, *THREE, "codexInk", cwd=tmp_path,
                        env={"SHAPE_PIN_SOURCE_OPENXDOX": str(folder)})
    assert_clean(result)
    assert (f"WARNING link-source-unreadable: {shown_path(str(folder))} "
            "($SHAPE_PIN_SOURCE_OPENXDOX) could not answer for openXdox"
            ) in result.stderr, result.stderr


@CONTROL_ARGV
@pytest.mark.parametrize("name", CONTROL_NAMES)
def test_a_checkout_beside_the_project_the_gate_could_not_read_is_spelled(
        tmp_path, monkeypatch, name):
    """`unread_lines`' second loop, for a checkout beside the project: its
    path, and the path inside its `how`."""
    clear_ambient_pin_sources(monkeypatch)
    parent = tmp_path / name
    (parent / "codexInk").mkdir(parents=True)
    beside = manifest(parent / "openXdox", "neutral_product_pins: 5\n")
    result = naming(parent / "codexInk", *THREE, "codexInk")
    assert_clean(result)
    shown = shown_path(str(beside))
    assert (f"WARNING link-source-unreadable: {shown} (sibling checkout "
            f"({shown})) could not answer for openXdox") in result.stderr, (
        result.stderr)


@CONTROL_ARGV
def test_a_value_that_names_no_path_is_spelled(tmp_path):
    """`no_path_refusal`: a keyed value names a link of the chain, so the
    value holds a control character only where the link does; the value is
    spelled, and the link, a chain's name, is printed as the chain gives
    it, as every chain line is."""
    link = "openX\x1b[31mdox"
    result = naming(tmp_path, "--pins", link, "--referent-chain",
                    f"{link},openInk", "--link-source", f"{link}=",
                    "codexInk")
    assert result.returncode == 2, result.stderr
    assert (f"`--link-source {shown_path(link + '=')}` names no path for "
            ) in result.stderr, result.stderr
    assert f"--link-source {link}=" not in result.stderr


@CONTROL_ARGV
@pytest.mark.parametrize("name", CONTROL_NAMES)
def test_an_unused_link_source_and_its_replacement_are_spelled(tmp_path,
                                                               name):
    """`unused_lines`: the value, and the later value that replaced it."""
    result = naming(tmp_path, "--link-source", "plain", "--link-source",
                    name, "codexInk")
    assert_clean(result)
    assert (f"NOTE --link-source plain: not used — the later `--link-source "
            f"{shown_path(name)}` replaced it.") in result.stderr
    assert (f"NOTE --link-source {shown_path(name)}: not used — no name "
            "classified here records a referent chain.") in result.stderr


@CONTROL_ARGV
@pytest.mark.parametrize("name", CONTROL_NAMES)
def test_an_unused_remedy_and_its_link_are_spelled(tmp_path, monkeypatch,
                                                   name):
    """`_unused_remedy_lines` (#907): the value as typed, and the text read
    as its link, which no chain names."""
    clear_ambient_pin_sources(monkeypatch)
    result = naming(tmp_path, *THREE, "--link-remedy", f"{name}=words",
                    "codexInk")
    assert_clean(result)
    assert (f"NOTE --link-remedy {shown_path(name + '=words')}: not used — "
            f"`{shown_path(name.strip())}` is not a link of a referent chain "
            "here") in result.stderr, result.stderr


def test_a_printable_value_is_named_as_typed(tmp_path):
    """The control: a printable value and its replacement, byte for byte."""
    result = naming(tmp_path, "--link-source", "a", "--link-source",
                    "café", "codexInk")
    assert ("NOTE --link-source a: not used — the later `--link-source "
            "café` replaced it.") in result.stderr, result.stderr
