# SPDX-License-Identifier: Apache-2.0
"""The pinned shape copies' text, moved in ONE shape bump (#610, the
checklist triage's D6), so every project re-pins once for v1.1.0.

Four of the five lines are here; THE LOCKSTEP RULE's `bump` (L2-39) is in
`tests/test_validate_family_branch_step.py`, beside the family holder it
runs against, and the adopted half of L2-33 in
`tests/test_adopt_contracts_dir.py`, beside the adoption it reads.

  * L2-33. `AGENTS-shape.md` said "the root Makefile exports
    `$(CURDIR)/spec/contracts` once". No scaffolded root's Makefile exports
    anything (`make contracts-dir` has no rule), and an adoption exports the
    spec leg where its plan mounts it (#522). The sentence is path-free now,
    and the file stays free of placeholders: it is a VERBATIM copy.
  * 576/2. The scaffold's `declared-unverified` WARNING offered "a sibling
    checkout, SHAPE_PIN_SOURCE_<LINK>, or --link-source <link>=<path>": the
    naming validator's sources. The scaffold has no `--link-source` and
    reads no sibling checkout, so it now offers what it reads, the variable
    and, for the first link, its `--pin-source`. The naming validator keeps
    its own words (`tests/test_link_source_chain_defaults.py`'s
    `UNVERIFIED`, `tests/test_naming_policy.py`'s `NOT_REACHED`).
  * L2-30. That WARNING named the `--pin-source` tree it reached raw, so an
    ESC in the path reached stderr. It is spelled as `pin-source-unreadable`
    spells it: `repr` where the path is not printable.
  * L2-31. The root's `validate-pins.py` named an unused `--pin-source` as
    typed in its "not used" note. It is spelled the same way.

No network and no GitHub: scaffolds dry-run, or into local bare remotes.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

import pytest

from conftest import (REPO, SCAFFOLD, clear_ambient_pin_sources, git,
                      load_without_bytecode, run_script)
from test_link_source_chain_defaults import (  # noqa: F401
    manifest, pinned, scaffold, tree, validate_pins,
)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import (  # noqa: E402
    LinkPins, NamingPolicy, link_declarations, link_pins_from_trees,
    shown_path,
)
from shape_materialize import PLACEHOLDER_RE, shown_source  # noqa: E402

TEMPLATE_AGENTS = REPO / "templates" / "assembly-root" / "AGENTS-shape.md"
POLICY = REPO / "contracts" / "repository-naming.yaml"

#: A Windows file name holds no control character, so neither does a path
#: one could mean there (`tests/test_pin_source_unreadable.py`'s mark).
CONTROL_ARGV = pytest.mark.skipif(
    os.name == "nt",
    reason="needs a path holding a control character, which a Windows file "
           "name cannot hold")

#: Names that print as something other than themselves: an ESC, and an ESC
#: beginning a forged line.
CONTROL_NAMES = [
    pytest.param("x\x1b[31mRED", id="esc"),
    pytest.param("x\x1b[31mRED\nWARNING forged-line: this line was not "
                 "printed by the tool\r", id="forged-line"),
]


def flat(path) -> str:
    """`path`'s text with its hard wrapping undone."""
    return " ".join(path.read_text(encoding="utf-8").split())


def scaffold_dry_run(cwd, name: str, source, chain: str):
    """`scaffold(...)` as a dry run into local remotes, recording `chain`."""
    return scaffold(cwd, name, source, "--referent-chain", chain,
                    "--dry-run", "--local-remote-dir", str(cwd / "remotes"))


def warnings_of(result) -> list[str]:
    """The `declared-unverified` WARNING lines the scaffold printed."""
    return [line for line in result.stderr.splitlines()
            if line.startswith("WARNING declared-unverified: ")]


# --- L2-33: the CONTRACTS_DIR sentence --------------------------------------

def test_the_pinned_agent_file_names_no_leg_path_and_no_placeholder():
    """The sentence is true whatever the spec leg's mount is: it names no
    path, so neither `spec/contracts` nor `$(CURDIR)`, and the file is still
    a verbatim copy with no `{{PLACEHOLDER}}` to render."""
    text = TEMPLATE_AGENTS.read_text(encoding="utf-8")
    assert "$(CURDIR)" not in text
    assert "spec/contracts" not in text
    assert PLACEHOLDER_RE.findall(text) == []
    said = flat(TEMPLATE_AGENTS)
    assert ("the code leg's tooling now takes `CONTRACTS_DIR` from the "
            "environment rather than each script guessing at `../`.") in said


def test_a_scaffolded_root_is_told_its_makefile_exports_none(project):
    """THE ISSUE'S MEASUREMENT. A scaffolded root's Makefile has no
    `CONTRACTS_DIR`, and its pinned `AGENTS-shape.md` said the root Makefile
    exported `$(CURDIR)/spec/contracts`. It now says the scaffolded root's
    exports none, and why."""
    assert "CONTRACTS_DIR" not in (project / "Makefile").read_text(
        encoding="utf-8")
    said = flat(project / "AGENTS-shape.md")
    assert "the root Makefile exports" not in said
    assert ("A SCAFFOLDED root's Makefile exports none: its legs start "
            "empty, so nothing reads across them yet.") in said
    assert ("Where this root was ADOPTED, its Makefile exports "
            "`CONTRACTS_DIR` once, as the `contracts/` of the spec leg at "
            "the path `project.yaml` mounts it, and `make contracts-dir` "
            "prints it.") in said


@pytest.mark.skipif(shutil.which("make") is None or sys.platform == "win32",
                    reason="needs make")
def test_make_has_no_contracts_dir_in_a_scaffolded_root(project):
    """What the sentence says of a scaffolded root, asked of `make`."""
    made = subprocess.run(["make", "--no-print-directory", "contracts-dir"],
                          cwd=str(project), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False)
    assert made.returncode != 0, made.stdout
    assert "No rule to make target 'contracts-dir'" in made.stderr, (
        made.stderr)


# --- 576/2: the scaffold offers the sources it reads -------------------------

def test_a_later_link_is_offered_its_variable_alone(tmp_path):
    """`--pin-source` is the first link's tree alone (#441), so for a later
    link the scaffold reads `SHAPE_PIN_SOURCE_<LINK>` and nothing else: the
    WARNING offers that, and neither `--link-source`, which the scaffold
    does not take, nor a sibling checkout, which it never reads."""
    result = scaffold_dry_run(tmp_path, "codexInk",
                              tree(tmp_path / "openXdox", "openYdox"),
                              "openXdox,openYdox,openInk")
    assert result.returncode == 0, result.stderr + result.stdout
    assert warnings_of(result) == [
        "WARNING declared-unverified: openYdox declaring a pin on openInk is "
        "a fact in openYdox's own tree, which is not reachable here "
        "(SHAPE_PIN_SOURCE_OPENYDOX would let it be read). The recorded "
        "chain still classifies."]
    assert "--link-source" not in result.stderr
    assert "sibling checkout" not in result.stderr


def test_the_variable_the_warning_offers_reads_the_later_link(tmp_path):
    """The remedy is one the scaffold HAS: the variable it offers, set to
    `openYdox`'s tree, verifies the link, and no WARNING is printed."""
    later = tree(tmp_path / "trees" / "openYdox", "openInk")
    source = tree(tmp_path / "openXdox", "openYdox")
    result = run_script(
        SCAFFOLD, "--org", "codexSoft", "--project", "codexInk",
        "--elected-by", "Test Human", "--elected-on", "2026-09-05",
        "--pin", f"openXdox@{_committed(source)}", "--pin-source",
        str(source), "--referent-chain", "openXdox,openYdox,openInk",
        "--dry-run", "--local-remote-dir", str(tmp_path / "remotes"),
        cwd=tmp_path, env={"SHAPE_PIN_SOURCE_OPENYDOX": str(later)})
    assert result.returncode == 0, result.stderr + result.stdout
    assert warnings_of(result) == []
    assert "declared pin chain openXdox → openYdox → openInk →" in (
        result.stdout), result.stdout


def _committed(source) -> str:
    """`source` made a repository with one commit, and that commit."""
    git("init", "-q", "-b", "main", cwd=source)
    git("add", "-A", cwd=source)
    git("commit", "-qm", "seed", cwd=source)
    return git("rev-parse", "HEAD", cwd=source).stdout.strip()


@pytest.fixture(scope="module")
def scaffold_module():
    """`scaffold-project.py`, loaded for `_link_remedies`."""
    return load_without_bytecode(SCAFFOLD, "scaffold_pinned_copy_text")


def test_each_holder_is_offered_the_scaffolds_own_sources(scaffold_module):
    """In this process, a chain of three: the first link is offered its
    variable and the `--pin-source` clone, a later holder its variable,
    and the chain's end, which holds no pin, nothing."""
    assert scaffold_module._link_remedies(
        ("openXdox", "openYdox", "openInk")) == {
        "openxdox": "SHAPE_PIN_SOURCE_OPENXDOX, or a --pin-source clone of "
                    "openXdox that holds its project.yaml, would let it be "
                    "read",
        "openydox": "SHAPE_PIN_SOURCE_OPENYDOX would let it be read"}


def test_a_shared_variable_is_offered_to_neither_link(scaffold_module):
    """A hand-written chain whose two holders share one variable (#275):
    the scaffold reads it for neither, so the first is offered its
    `--pin-source` alone, and the second, which has no other source here,
    is told so rather than offered one the scaffold would not read."""
    assert scaffold_module._link_remedies(
        ("open-x", "open_x", "openInk")) == {
        "open-x": "a --pin-source clone of open-x that holds its "
                  "project.yaml would let it be read",
        "open_x": "the scaffold reads no source for it: SHAPE_PIN_SOURCE_"
                  "OPEN_X is another link's too, and --pin-source is the "
                  "first link's tree alone"}


def test_a_caller_s_remedies_reach_the_warning_and_no_one_else_s(
        tmp_path, monkeypatch):
    """`link_pins_from_trees(..., remedies=)` hands them to the WARNING for
    the link they name; a link they do not name, and a reader that passes
    none, keep the naming validator's words."""
    clear_ambient_pin_sources(monkeypatch)
    policy = NamingPolicy.load(POLICY)
    chain = ("openXdox", "openYdox", "openInk")
    found = link_pins_from_trees(chain, None,
                                 remedies={"openydox": "OURS would do"})
    assert type(found) is LinkPins
    assert found == {}
    assert found.unreadable == {}
    said = policy.resolve_referent("codexInk", {"openXdox"}, chain,
                                   found).warnings
    assert said[0].endswith(
        "which is not reachable here (a sibling checkout, SHAPE_PIN_SOURCE_"
        "OPENXDOX, or --link-source openXdox=<path> would let it be read). "
        "The recorded chain still classifies.")
    assert said[1].endswith(
        "which is not reachable here (OURS would do). The recorded chain "
        "still classifies.")
    plain = link_pins_from_trees(chain, None)
    assert type(plain) is dict
    assert "OURS" not in " ".join(policy.resolve_referent(
        "codexInk", {"openXdox"}, chain, plain).warnings)


def test_remedies_without_reasons_remember_no_reason(tmp_path, monkeypatch):
    """A tree that WAS reached and cannot be read: with `with_reasons` the
    `LinkPins` keeps why, and with `remedies` alone it does not, as a plain
    mapping does not."""
    clear_ambient_pin_sources(monkeypatch)
    source = manifest(tmp_path / "openXdox", "neutral_product_pins: 5\n")
    chain = ("openXdox", "openInk")
    asked = link_pins_from_trees(chain, None, None, source,
                                 with_reasons=True, remedies={"x": "y"})
    assert set(asked.unreadable) == {"openxdox"}
    assert asked.remedies == {"x": "y"}
    alone = link_pins_from_trees(chain, None, None, source,
                                 remedies={"x": "y"})
    assert alone.unreadable == {}
    assert alone.remedies == {"x": "y"}


# --- L2-30: the tree the WARNING names is spelled ----------------------------

@CONTROL_ARGV
@pytest.mark.parametrize("name", CONTROL_NAMES)
def test_the_scaffold_spells_a_pin_source_it_could_not_read(tmp_path, name):
    """THE ISSUE'S MEASUREMENT: `--pin-source` at `x<ESC>[31mRED`, whose
    `project.yaml` holds `neutral_product_pins: 5`, exited 0 with a raw ESC
    in the WARNING on stderr. The tree is named as `pin-source-unreadable`
    names one, so no ESC and no line of the path's own reach stderr."""
    source = manifest(tmp_path / "trees" / name,
                      "schema_version: 1\nneutral_product_pins: 5\n")
    result = scaffold_dry_run(tmp_path, "codexInk", source,
                              "openXdox,openInk")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "\x1b" not in result.stderr + result.stdout
    assert not [line for line in result.stderr.splitlines()
                if line.startswith("WARNING forged-line")], result.stderr
    shown = repr(str(source / "project.yaml"))
    assert warnings_of(result) == [
        "WARNING declared-unverified: openXdox declaring a pin on openInk is "
        "a fact in openXdox's own tree, which was reached but could not be "
        f"read as a declaration ({shown}: neutral_product_pins is not a "
        "list). The recorded chain still classifies."]


#: Each way a manifest the lookup reached cannot answer, and the words after
#: its path.
UNANSWERED = [
    pytest.param(b"- openInk\n", "not a mapping", id="not-a-mapping"),
    pytest.param(b"neutral_product_pins: 5\n",
                 "neutral_product_pins is not a list", id="not-a-list"),
    pytest.param(b"neutral_product_pins:\n  - 5\n",
                 "neutral_product_pins holds an entry that is not text",
                 id="not-text"),
    pytest.param(b"neutral_product_pins: [openInk\n",
                 "not a flow collection: '[openInk'", id="does-not-parse"),
    pytest.param(b"neutral_product_pins: \xff\n",
                 "not UTF-8 at byte 22 (invalid start byte)",
                 id="not-utf-8"),
]


@CONTROL_ARGV
@pytest.mark.parametrize("body,said", UNANSWERED)
@pytest.mark.parametrize("name", ["plain", *CONTROL_NAMES])
def test_every_reason_names_the_manifest_spelled(tmp_path, body, said, name):
    """`link_declarations` names the manifest the same way in every reason
    it gives: as it is where it is printable, and as `repr` spells it where
    it is not, including the reason the YAML reader wrote itself."""
    tree_path = tmp_path / name
    tree_path.mkdir()
    (tree_path / "project.yaml").write_bytes(body)
    pins, why = link_declarations(tree_path)
    assert pins is None
    path = str(tree_path / "project.yaml")
    assert why == f"{shown_path(path)}: {said}"
    assert why.startswith(path if name == "plain" else repr(path))
    assert "\x1b" not in why


#: A file mode denies nothing to root, and Windows has no mode bits for
#: `chmod` to clear.
UNOPENABLE = pytest.mark.skipif(
    os.name == "nt" or getattr(os, "geteuid", lambda: 1)() == 0,
    reason="needs a POSIX file mode that denies reading, which root is not "
           "stopped by")


@UNOPENABLE
@pytest.mark.parametrize("name", ["plain", *CONTROL_NAMES])
def test_a_manifest_it_cannot_open_is_named_spelled(tmp_path, name):
    """The one reason that is the system's own: a manifest this user may not
    read is named the same way, beside `strerror`."""
    tree_path = tmp_path / name
    tree_path.mkdir()
    path = tree_path / "project.yaml"
    path.write_bytes(b"neutral_product_pins: []\n")
    path.chmod(0)
    try:
        pins, why = link_declarations(tree_path)
    finally:
        path.chmod(0o600)
    assert pins is None
    assert why == f"{shown_path(str(path))}: Permission denied"
    assert "\x1b" not in why


@pytest.mark.parametrize("path", [
    "plain/dir", "x\x1b[31mRED", "a\nb", "a\rb", "café", "\udcff",
    "tab\there", "",
])
def test_the_scaffolds_two_lines_spell_a_pin_source_one_way(path):
    """`pin-source-unreadable` and the chain WARNING name one `--pin-source`
    with one function: printable as it is, anything else as `repr`."""
    assert shown_source(path) == shown_path(path)
    assert shown_path(path) == (path if path.isprintable() else repr(path))


# --- L2-31: validate-pins.py's "not used" note -------------------------------

#: Why the root's gate did not use a bare value a keyed one answered for.
MORE_SPECIFIC = ("each declared pin had a more specific source (a keyed "
                 "--pin-source, SHAPE_PIN_SOURCE_<PRODUCT>, or a checkout "
                 "beside this assembly root) or was not recomputed")


def notes(result) -> list[str]:
    """The `--pin-source` notes the root's gate printed."""
    return [line.strip() for line in result.stdout.splitlines()
            if line.strip().startswith("note --pin-source ")]


@CONTROL_ARGV
@pytest.mark.parametrize("name", CONTROL_NAMES)
def test_an_unused_pin_source_is_named_spelled(pinned, tmp_path, name):
    """A bare value every pin had a more specific source for: the note named
    it as typed, and an ESC in it reached the terminal (the issue's
    measurement on a freshly scaffolded root)."""
    typed = str(tmp_path / name)
    result = validate_pins(pinned, "--pin-source",
                           f"openXdox={pinned['product']}",
                           "--pin-source", typed)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "\x1b" not in result.stdout + result.stderr
    assert notes(result) == [
        f"note --pin-source {typed!r}: not used — {MORE_SPECIFIC}."]


@CONTROL_ARGV
def test_a_replaced_pin_source_and_its_replacement_are_spelled(pinned,
                                                               tmp_path):
    """The note for a value a later one replaced names both."""
    first = str(tmp_path / "x\x1b[31mRED")
    later = str(tmp_path / "y\x1b[32mGREEN")
    result = validate_pins(pinned, "--pin-source", first,
                           "--pin-source", later,
                           "--pin-source", str(pinned["product"]))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "\x1b" not in result.stdout + result.stderr
    assert (f"note --pin-source {first!r}: not used — the later "
            f"`--pin-source {later!r}` replaced it.") in notes(result), (
        result.stdout)


def test_a_key_read_as_a_path_is_spelled(pinned):
    """A value holding `=` whose key is no declared pin is read as a PATH,
    and the note's second sentence names the key: spelled too."""
    key = "o\x1b[1m"
    typed = f"{key}=x"
    result = validate_pins(pinned, "--pin-source",
                           f"openXdox={pinned['product']}",
                           "--pin-source", typed)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "\x1b" not in result.stdout + result.stderr
    assert notes(result) == [
        f"note --pin-source {typed!r}: not used — {MORE_SPECIFIC}. It was "
        "read as a PATH: "
        f"`{key!r}` is not a declared neutral-product pin "
        "(declared: openXdox)."]


def test_a_printable_pin_source_is_named_as_typed(pinned, tmp_path):
    """The control: a printable value is the bytes it always was."""
    typed = str(tmp_path / "unused")
    result = validate_pins(pinned, "--pin-source",
                           f"openXdox={pinned['product']}",
                           "--pin-source", typed)
    assert result.returncode == 0, result.stdout + result.stderr
    assert notes(result) == [
        f"note --pin-source {typed}: not used — {MORE_SPECIFIC}."]
