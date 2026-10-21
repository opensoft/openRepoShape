# SPDX-License-Identifier: Apache-2.0
"""A bare `--link-source PATH` is the FIRST chain link's tree and no other's
(#441), and a source that names no path is refused (#442).

#441. `link_pins_from_trees` asked the one bare value for every link no more
specific source answered for. In the chain `openXdox → openYdox → openInk`,
with one bare tree that is `openXdox`'s, `openYdox` was read from that same
`project.yaml`, which declares `openYdox` and not `openInk`: "openYdox
declares openYdox, not openInk", and for `codexInk`, a name with no direct pin
on its referent, a FINDING, exit 1, for a chain that holds. The scaffold
reads its `--pin-source` the same way, so it refused such a chain as
`chain-not-declared`. Now the bare value is asked for the first link alone, a
later link is read from its own source or is declared-unverified, and a run
whose chains begin at two links reads a bare value for neither.

#442. `openXdox=` with nothing after the `=` was `Path("")`, which is `.`:
from a project root the naming gate read the project's own manifest as
`openXdox`'s, and `validate-pins.py` asked `.` for the pinned commit. Both
tools now refuse it, and an empty value, by name, exit 2.

#1053. `validate-pins.py` ended every `--pin-source` key at the first `=`, so
a declared pin whose name holds one, `open=y`, was no key, and `open=y=` was a
bare PATH. A key is now the longest declared pin before an `=` that leaves a
path after it, so `open=y=<path>` is `open=y`'s, and `open=y=` names no path
for it and is refused in `openXdox=`'s words.

Every run is made from a directory of its own under `tmp_path`, and every
manifest is written as bytes, so no checkout beside it answers and no line
ending differs between systems.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import (REPO, SCAFFOLD, clear_ambient_pin_sources, git,
                      run_script)
from test_neutral_pin_validator import declare_by_hand

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import link_pins_from_trees  # noqa: E402

VALIDATOR = REPO / "scripts" / "validate-repository-naming.py"
UNVERIFIED = ("WARNING {name}: declared-unverified: {holder} declaring a pin "
              "on {held} is a fact in {holder}'s own tree, which is not "
              "reachable here (a sibling checkout, SHAPE_PIN_SOURCE_{var}, or "
              "--link-source {holder}=<path> would let it be read). The "
              "recorded chain still classifies.\n")
MORE_SPECIFIC = ("a more specific source (a keyed --link-source, "
                 "SHAPE_PIN_SOURCE_<PRODUCT>, or a checkout beside the "
                 "project)")


def unverified(name: str, holder: str, held: str) -> str:
    """The WARNING the naming gate prints for a link nothing answered for."""
    return UNVERIFIED.format(name=name, holder=holder, held=held,
                             var=holder.upper())


def manifest(path: Path, body: str) -> Path:
    """`path/project.yaml` holding `body`, written as bytes."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "project.yaml").write_bytes(body.encode("utf-8"))
    return path


def tree(path: Path, *pins: str) -> Path:
    """A stand-in for a chain link's checkout, declaring `pins`."""
    return manifest(path, "neutral_product_pins:\n"
                    + "".join(f"  - {pin}\n" for pin in pins))


def project(path: Path, pin: str, chain: str) -> Path:
    """A project whose assembly leg, named for `path`, pins `pin` and
    records `chain`."""
    return manifest(path, (
        f"neutral_product_pins:\n  - {pin}\nlegs:\n"
        f"  - repository: testorg/{path.name}\n    path: \".\"\n"
        f"    role: assembly\n    naming:\n      referent_chain: [{chain}]\n"))


def two_legs(path: Path) -> Path:
    """A project pinning `openXdox` and `openYdox`, whose legs record
    `openXdox → openInk` (`codexInk`) and `openYdox → openQuill`
    (`codexQuill`): its chains begin at two links."""
    return manifest(path, (
        "neutral_product_pins:\n  - openXdox\n  - openYdox\nlegs:\n"
        + "".join(
            f"  - repository: testorg/{name}\n    path: \".\"\n"
            f"    role: assembly\n    naming:\n"
            f"      referent_chain: [{chain}]\n"
            for name, chain in (("codexInk", "openXdox, openInk"),
                                ("codexQuill", "openYdox, openQuill")))))


def two_firsts_note(bare: Path, first: str, second: str) -> str:
    """The NOTE for a bare value that chains beginning at two links left
    unread."""
    return (f"NOTE --link-source {bare}: not used — a bare PATH is one first "
            f"link's tree, and the chains read here begin at {first}, "
            f"{second}: name the link it is, as --link-source <link>=PATH.\n")


def naming(cwd: Path, *args: str):
    return run_script(VALIDATOR, *args, cwd=cwd)


def stdin_naming(cwd: Path, chain: str, *sources: str):
    """`codexInk`, read from stdin with `--referent-chain <chain>`, and each
    of `sources` as a `--link-source`."""
    return run_script(VALIDATOR, "--role", "assembly", "--pins", "openXdox",
                      "--referent-chain", chain,
                      *(arg for source in sources
                        for arg in ("--link-source", source)),
                      cwd=cwd, input="codexInk\n")


def scaffold(cwd: Path, name: str, source: Path, *args: str):
    """`scaffold-project.py` for `codexSoft/<name>`, pinning `openXdox` at a
    commit of `source`, which is made a repository here and is the
    `--pin-source`."""
    git("init", "-q", "-b", "main", cwd=source)
    git("add", "-A", cwd=source)
    git("commit", "-qm", "seed", cwd=source)
    commit = git("rev-parse", "HEAD", cwd=source).stdout.strip()
    return run_script(SCAFFOLD, "--org", "codexSoft", "--project", name,
                      "--elected-by", "Test Human", "--elected-on",
                      "2026-09-05", "--pin", f"openXdox@{commit}",
                      "--pin-source", str(source), *args, cwd=cwd)


@pytest.fixture
def ink(tmp_path) -> dict:
    """#441's own layout: `codexInk` pinning `openXdox`, recording the chain
    `openXdox → openYdox → openInk`, and each link's tree away from it."""
    return {
        "root": project(tmp_path / "ws" / "codexInk", "openXdox",
                        "openXdox, openYdox, openInk"),
        "x": tree(tmp_path / "trees" / "openXdox", "openYdox"),
        "y": tree(tmp_path / "trees" / "openYdox", "openInk"),
    }


# --- #441: the naming gate -------------------------------------------------

def test_one_bare_tree_answers_for_the_first_link_of_a_long_chain(ink):
    """THE ISSUE'S FIRST ROW. The bare tree is `openXdox`'s and verifies
    `openXdox` alone; `openYdox` is declared-unverified, and the WARNING
    names the keyed value that would read it. It was a FINDING, the chain
    "broken" by a tree nobody gave for `openYdox`, exit 1."""
    result = naming(ink["root"], "--project", "project.yaml",
                    "--link-source", str(ink["x"]))
    assert result.returncode == 0, result.stderr
    assert "codexInk                         domain-descendant/assembly" \
        in result.stdout
    assert result.stderr == unverified("codexInk", "openYdox", "openInk")


def test_each_link_keyed_still_verifies_the_whole_chain(ink):
    """The issue's second row, unchanged: every link has its own tree."""
    result = naming(ink["root"], "--project", "project.yaml",
                    "--link-source", f"openXdox={ink['x']}",
                    "--link-source", f"openYdox={ink['y']}")
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert "domain-descendant/assembly" in result.stdout


def test_a_bare_tree_is_never_read_for_a_later_link(ink):
    """`openXdox` keyed and `openYdox`'s tree given bare: the bare value
    used to answer `openYdox`. It is the first link's tree alone, so
    `openYdox` is declared-unverified and the value is a NOTE saying why,
    never counted as the answer for a link it was not asked for."""
    result = naming(ink["root"], "--project", "project.yaml",
                    "--link-source", f"openXdox={ink['x']}",
                    "--link-source", str(ink["y"]))
    assert result.returncode == 0, result.stderr
    assert result.stderr == (
        unverified("codexInk", "openYdox", "openInk")
        + f"NOTE --link-source {ink['y']}: not used — a bare PATH is the "
        "tree of a chain's first link alone, openXdox, which had "
        f"{MORE_SPECIFIC}.\n")


def test_names_read_from_stdin_note_the_first_link_they_read(ink):
    """Names on stdin come only when no other name does, so their chain's
    first link is found as it is read: the NOTE names it as it does for a
    name on the command line."""
    result = stdin_naming(ink["root"], "openXdox,openYdox,openInk",
                          f"openXdox={ink['x']}", str(ink["y"]))
    assert result.returncode == 0, result.stderr
    assert result.stderr.endswith(
        f"NOTE --link-source {ink['y']}: not used — a bare PATH is the "
        "tree of a chain's first link alone, openXdox, which had "
        f"{MORE_SPECIFIC}.\n"), result.stderr


def test_a_two_link_chain_read_from_stdin_counts_its_first_link(tmp_path):
    """A chain of TWO links is a first link read: `openXdox` is keyed, so the
    bare tree goes unused, and the NOTE says each link whose declaration is
    read had a more specific source. Were a two-link chain not counted (the
    one-link rule taken one link too far), the first-link list would be empty
    and the sentence would name no link: `first link alone, , which had`."""
    work = tmp_path / "ws"
    work.mkdir()
    bare = tree(tmp_path / "trees" / "other", "openInk")
    result = stdin_naming(
        work, "openXdox,openInk",
        f"openXdox={tree(tmp_path / 'trees' / 'openXdox', 'openInk')}",
        str(bare))
    assert result.returncode == 0, result.stderr
    assert result.stderr == (
        f"NOTE --link-source {bare}: not used — each link whose own "
        f"declaration is read had {MORE_SPECIFIC}.\n")


def test_chains_that_begin_at_two_links_read_a_bare_tree_for_neither(
        tmp_path):
    """A name on the command line reads `openXdox → openInk` and the
    project's leg reads `openYdox → openQuill`. One tree cannot be both
    first links': it answered both, and `codexQuill`'s chain was broken by
    a tree that declares `openInk`. Now neither reads it, and it is noted."""
    root = project(tmp_path / "ws" / "codexQuill", "openYdox",
                   "openYdox, openQuill")
    bare = tree(tmp_path / "trees" / "openXdox", "openInk")
    result = naming(root, "--role", "assembly", "--pins", "openXdox",
                    "--referent-chain", "openXdox,openInk",
                    "--project", "project.yaml", "--link-source", str(bare),
                    "codexInk")
    assert result.returncode == 0, result.stderr
    assert result.stderr == (
        unverified("codexInk", "openXdox", "openInk")
        + unverified("codexQuill", "openYdox", "openQuill")
        + two_firsts_note(bare, "openXdox", "openYdox"))


def test_a_project_whose_legs_begin_at_two_links_reads_a_bare_tree_for_neither(
        tmp_path):
    """One `--project`, two legs: `codexInk` records `openXdox → openInk` and
    `codexQuill` records `openYdox → openQuill`, and the bare tree is
    `openXdox`'s. It is found before either leg is classified that the legs
    begin at two links. Were it not, the first classification pass would read
    the bare tree for `openXdox` and count it used, while the pass that
    prints says `openXdox` is unverified: two WARNINGs and no NOTE."""
    root = two_legs(tmp_path / "ws" / "codexSoft")
    bare = tree(tmp_path / "trees" / "openXdox", "openInk")
    result = naming(root, "--project", "project.yaml",
                    "--link-source", str(bare))
    assert result.returncode == 0, result.stderr
    assert result.stderr == (
        unverified("codexInk", "openXdox", "openInk")
        + unverified("codexQuill", "openYdox", "openQuill")
        + two_firsts_note(bare, "openXdox", "openYdox"))


def test_a_chain_of_one_link_is_no_first_link_read(tmp_path):
    """`codexInk` records the chain `openInk`: one link, so no holder, so no
    declaration read, so no first link. Beside `codexQuill`'s
    `openXdox → openQuill`, the chains read begin at `openXdox` alone, and
    the bare tree, which is `openXdox`'s, verifies it: no WARNING, no NOTE.
    A one-link chain was counted as a second first link, the bare tree went
    to neither, and `codexQuill` was declared-unverified."""
    root = project(tmp_path / "ws" / "codexQuill", "openXdox",
                   "openXdox, openQuill")
    bare = tree(tmp_path / "trees" / "openXdox", "openQuill")
    result = naming(root, "--role", "assembly", "--pins", "openInk",
                    "--referent-chain", "openInk", "--project",
                    "project.yaml", "--link-source", str(bare), "codexInk")
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert "codexQuill" in result.stdout


# --- #441: the lookup itself, and the scaffold -------------------------------

@pytest.mark.parametrize("chain", [
    ("openXdox",), ("openXdox", "openYdox"),
    ("openXdox", "openYdox", "openInk")], ids=["one", "two", "three"])
def test_the_lookup_asks_the_bare_source_for_the_first_link_alone(
        tmp_path, monkeypatch, chain):
    """In this process: a chain of any length reads `default_source` for its
    first link, and asks it for no later one."""
    clear_ambient_pin_sources(monkeypatch)
    source = tree(tmp_path / "trees" / "openXdox", "openYdox")
    tried: dict = {}
    found = link_pins_from_trees(chain, tmp_path / "ws" / "codexInk",
                                 default_source=source, tried=tried)
    assert found == {"openxdox": {"openYdox"}}
    assert [rule for rule, *_ in tried["openXdox"]] == ["sibling", "bare"]
    assert {link: [rule for rule, *_ in tried[link]]
            for link in chain[1:]} == {link: ["sibling"] for link in chain[1:]}


def test_the_scaffold_reads_its_pin_source_for_the_first_link_alone(
        tmp_path):
    """`--pin-source` is the pinned `openXdox`'s checkout. It was read as
    `openYdox`'s too, and the scaffold refused `chain-not-declared`; now
    `openYdox` is declared-unverified, a warning, and the dry run plans."""
    result = scaffold(tmp_path, "codexInk",
                      tree(tmp_path / "openXdox", "openYdox"),
                      "--referent-chain", "openXdox,openYdox,openInk",
                      "--dry-run",
                      "--local-remote-dir", str(tmp_path / "remotes"))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "chain-not-declared" not in result.stderr
    assert ("WARNING declared-unverified: openYdox declaring a pin on openInk"
            in result.stderr)
    assert "--dry-run: nothing was created." in result.stdout


# --- #442: the naming gate ---------------------------------------------------

@pytest.fixture
def two(tmp_path) -> dict:
    """#442's own layout: `codexInk` recording `openXdox → openInk`."""
    return {"root": project(tmp_path / "ws" / "codexInk", "openXdox",
                            "openXdox, openInk"),
            "x": tree(tmp_path / "trees" / "openXdox", "openInk"),
            "elsewhere": tmp_path / "trees"}


@pytest.mark.parametrize("value,said", [
    pytest.param("openXdox=", "`--link-source openXdox=` names no path for "
                 "openXdox", id="keyed"),
    pytest.param("OPENXDOX=", "`--link-source OPENXDOX=` names no path for "
                 "openXdox", id="keyed-in-capitals"),
    pytest.param("", "`--link-source ''` names no path", id="bare"),
])
@pytest.mark.parametrize("where", ["project-root", "elsewhere"])
def test_a_link_source_that_names_no_path_is_refused(two, value, said,
                                                     where):
    """From the project root it read the project's own manifest as
    `openXdox`'s and called the chain broken, exit 1; anywhere else it was a
    warning about `.`. Both are now one refusal, before anything is
    classified, naming the link."""
    cwd, manifest_arg = ((two["root"], "project.yaml") if where ==
                         "project-root" else
                         (two["elsewhere"], str(two["root"] / "project.yaml")))
    result = naming(cwd, "--project", manifest_arg, "--link-source", value)
    assert result.returncode == 2, result.stderr
    assert result.stderr == (
        f"REFUSED link-source-no-path: {said}. An empty path would be read "
        "as the directory this runs in. Give the tree's path (`--link-source "
        "<link>=<path>`), or `.` to mean this directory.\n")
    assert result.stdout == ""


def test_a_path_typed_after_the_equals_sign_is_still_read(two):
    """The control, and the edges of the refusal: the real tree verifies; a
    typed `.` is still the current directory; and `openZdox=` keys no link
    of this chain, so it is the bare PATH `openZdox=`, which is not empty."""
    keyed = naming(two["root"], "--project", "project.yaml",
                   "--link-source", f"openXdox={two['x']}")
    assert keyed.returncode == 0, keyed.stderr
    assert keyed.stderr == ""
    dot = naming(two["elsewhere"], "--project",
                 str(two["root"] / "project.yaml"),
                 "--link-source", "openXdox=.")
    assert dot.returncode == 0, dot.stderr
    assert ("WARNING link-source-unreadable: . (--link-source openXdox=...) "
            "could not answer for openXdox: it holds no project.yaml\n"
            in dot.stderr), dot.stderr
    other = naming(two["root"], "--project", "project.yaml",
                   "--link-source", "openZdox=")
    assert other.returncode == 0, other.stderr
    assert "REFUSED" not in other.stderr
    assert ("It was read as a PATH: `openZdox` is not a link of a referent "
            "chain here" in other.stderr), other.stderr


# --- #442: validate-pins.py --------------------------------------------------

@pytest.fixture(scope="module")
def pinned(tmp_path_factory) -> dict:
    """One `codexDox` scaffolded with a declared pin on `openXdox`, and a
    clone of the product away from it."""
    base = tmp_path_factory.mktemp("link441-pins")
    product = tree(base / "src" / "openXdox", "openDox")
    result = scaffold(base, "codexDox", product,
                      "--local-remote-dir", str(base / "remotes"),
                      "--work-dir", str(base / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    return {"root": base / "work" / "codexDox", "product": product}


def validate_pins(pinned: dict, *args: str):
    root = pinned["root"]
    return run_script(root / "scripts" / "validate-pins.py", *args, cwd=root)


def pin_source_no_path(said: str) -> str:
    """`validate-pins.py`'s whole stderr refusing a value that names no
    path, `said` naming each value and its pin."""
    return (f"REFUSED pin-source-no-path: {said}. An empty path would be read "
            "as the directory this runs in.\nRemediation: give the "
            "checkout's path (`--pin-source <product>=<path>`), or `.` to "
            "mean this directory.\n")


@pytest.mark.parametrize("value,said", [
    pytest.param("openXdox=", "`--pin-source openXdox=` names no path for "
                 "openXdox", id="keyed"),
    pytest.param("OPENXDOX=", "`--pin-source OPENXDOX=` names no path for "
                 "openXdox", id="keyed-in-capitals"),
    pytest.param("", "`--pin-source ''` names no path", id="bare"),
])
def test_a_pin_source_that_names_no_path_is_refused(pinned, value, said):
    """It asked the project root for the pinned commit, and the
    `neutral-pin-source-unreadable` FINDING named `.`. Now it is refused, by
    the pin it is keyed to, with its own remedy and not the lockstep one."""
    result = validate_pins(pinned, "--pin-source", value)
    assert result.returncode == 2, result.stderr + result.stdout
    assert result.stderr == pin_source_no_path(said)
    assert result.stdout == ""


def test_a_pin_source_path_after_the_equals_sign_is_still_read(pinned):
    """The control: the product's clone recomputes the digest, and a typed
    `.` is still the project root, asked and named."""
    keyed = validate_pins(pinned, "--pin-source",
                          f"openXdox={pinned['product']}")
    assert keyed.returncode == 0, keyed.stderr + keyed.stdout
    assert "pins ok" in keyed.stdout
    dot = validate_pins(pinned, "--pin-source", "openXdox=.")
    assert dot.returncode == 1, dot.stderr + dot.stdout
    assert ("FINDING neutral-pin-source-unreadable: contracts/openxdox-pin.yaml"
            ": . (--pin-source openXdox=...) could not answer" in dot.stderr)


# --- #1053: validate-pins.py, a pin whose name holds `=` --------------------

@pytest.fixture(scope="module")
def equals_pinned(tmp_path_factory) -> dict:
    """`codexDox` scaffolded as `pinned` is, with its pin on `openXdox`
    then declared BY HAND as a pin on `open=y` over the same tree (#1053):
    no scaffold writes a pin holding `=`."""
    base = tmp_path_factory.mktemp("pin1053-pins")
    product = tree(base / "src" / "openXdox", "openDox")
    result = scaffold(base, "codexDox", product,
                      "--local-remote-dir", str(base / "remotes"),
                      "--work-dir", str(base / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    root = base / "work" / "codexDox"
    commit = git("rev-parse", "HEAD", cwd=product).stdout.strip()
    declare_by_hand(root, ("open=y", product, commit), seed="openXdox")
    return {"root": root, "product": product}


@pytest.mark.parametrize("value,said", [
    pytest.param("open=y=", "`--pin-source open=y=` names no path for "
                 "open=y", id="keyed"),
    pytest.param("OPEN=Y=", "`--pin-source OPEN=Y=` names no path for "
                 "open=y", id="keyed-in-capitals"),
])
def test_a_pin_source_that_ends_at_a_pin_holding_an_equals_sign_is_refused(
        equals_pinned, value, said):
    """`open=y=` ends at the declared pin `open=y` and no shorter pin leaves
    a path, so it names no path for `open=y` and is refused as `openXdox=`
    is, in the same words, exit 2 (#1053). Read at the first `=`, `open`
    named no pin, so it was the bare PATH `open=y=` for every pin with no
    more specific answer."""
    result = validate_pins(equals_pinned, "--pin-source", value)
    assert result.returncode == 2, result.stderr + result.stdout
    assert result.stderr == pin_source_no_path(said)
    assert result.stdout == ""


def test_a_path_after_a_pin_holding_an_equals_sign_is_still_read(
        equals_pinned):
    """The control: the product's clone recomputes `open=y`'s digest, and
    a typed `.` is still the project root, asked and named."""
    keyed = validate_pins(equals_pinned, "--pin-source",
                          f"open=y={equals_pinned['product']}")
    assert keyed.returncode == 0, keyed.stderr + keyed.stdout
    assert "digest recomputes (--pin-source open=y=...)\n" in keyed.stdout
    assert "pins ok" in keyed.stdout
    dot = validate_pins(equals_pinned, "--pin-source", "open=y=.")
    assert dot.returncode == 1, dot.stderr + dot.stdout
    assert ("FINDING neutral-pin-source-unreadable: contracts/open=y-pin.yaml"
            ": . (--pin-source open=y=...) could not answer" in dot.stderr), (
        dot.stderr)
