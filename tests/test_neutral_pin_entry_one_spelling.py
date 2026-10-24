# SPDX-License-Identifier: Apache-2.0
"""One spelling of a `neutral_product_pins:` entry, whichever tool made the
root (#924).

`scaffold-project.py` wrote a pin's product bare wherever the project's own
reader read it back, and `adopt-project.py execute` wrote it as `y` writes
the plan's `product:`, double-quoted where the reader does not read that
spelling back. So one `--pin` wrote two lines. Measured at v1.1.1's
`5017830`:

    product   scaffold   adopt
    0x1F      0x1F       "0x1F"
    1_000     1_000      "1_000"
    1e3       1e3        "1e3"
    3dGlass   3dGlass    "3dGlass"
    -x        -x         "-x"

`openGlass`, `007` and `yes` came out the same from both. The project's
reader read every one back and no gate failed, but PyYAML's `safe_load`
read the scaffold's `0x1F` as 31 and its `1_000` as 1000. Both tools now
call `shape_materialize.neutral_pin_entry`, which is adopt's rule.

Here one list is rendered through both tools' `_neutral_product_pins` into
the manifest template's own line, and the lines are compared with each
other and with adopt's spelling. No network, no git and no GitHub: the two
tools are loaded as modules, and nothing is run.

#912 (#457's L2-14): the one spelling still wrote `yes`, `no`, `on`, `off`,
`.5`, `.inf` and `.nan` bare, because the project's reader reads each back
as typed, and PyYAML's `safe_load` read them as True, False, 0.5, inf and
nan. Measured on main 6c861635 over every name `--pin` admits of up to three
characters: 132 of those written bare PyYAML read as no text, and 132
ruamel.yaml did (YAML 1.2). A name YAML 1.1 or 1.2's core schema resolves to
a bool, a null or a float is double-quoted now, whatever the project's
reader makes of it, and every other is written as it was.
"""

from __future__ import annotations

import importlib.util
import itertools
import sys
from pathlib import Path

import pytest

from conftest import ADOPT, REPO, SCAFFOLD

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402
from repo_shape import YamlError, double_quoted, parse_yaml  # noqa: E402
from shape_materialize import neutral_pin_entry, render  # noqa: E402

try:
    import yaml as pyyaml  # the oracle only: nothing shipped imports it
except ImportError:  # pragma: no cover - depends on the machine
    pyyaml = None
try:  # a YAML 1.2 reader, and a 1.1 one: the oracle only, as PyYAML is
    from ruamel.yaml import YAML as RuamelYAML
except ImportError:  # pragma: no cover - depends on the machine
    RuamelYAML = None

NEEDS_PYYAML = pytest.mark.skipif(
    pyyaml is None,
    reason="PyYAML is not installed here, so the comparison with a stock "
           "reader is skipped; the project's own reader is asked by the "
           "tests beside this one")

#: The issue's names, each with the line both tools now write for it:
#: adopt's spelling, double-quoted where `y` quotes the plan's `product:`,
#: and where a standard YAML reader takes the name for no text (#912).
SPELLED = {
    "0x1F": '"0x1F"',
    "1_000": '"1_000"',
    "1e3": '"1e3"',
    "3dGlass": '"3dGlass"',
    "-x": '"-x"',
    "openGlass": "openGlass",
    "007": '"007"',
    "yes": '"yes"',
}
#: Every word YAML 1.1 (yaml.org/type/bool.html, null.html) or YAML 1.2's
#: core schema resolves to a bool or a null, as each spec lists them.
YAML_WORDS = ("y", "Y", "yes", "Yes", "YES", "n", "N", "no", "No", "NO",
              "true", "True", "TRUE", "false", "False", "FALSE",
              "on", "On", "ON", "off", "Off", "OFF", "null", "Null", "NULL")
#: Floats a plain scalar can spell, so beginning with a point: YAML 1.1's
#: `.inf` and `.nan`; its pattern as written (`\.[0-9.]*`, `.`, `..` and
#: `.5.5` among it, with a signed exponent); and as its example
#: `685.230_15e+03`, PyYAML and ruamel.yaml read it, with `_` among the
#: digits, and YAML 1.2's unsigned exponent. The last six have exponents
#: of two digits (#1103): every other exponent here has one, and
#: `PIN_NAMES` stops at three characters, so a rule that took one exponent
#: digit passed every row. `.5.5e-10` and `.5.5E-10` only the pattern as
#: written takes, and `.5_e-10` and `.5e10` only the one with `_`, so each
#: of the rule's two exponents is held on its own, and the first in both
#: cases of its `e` (#1131's review, NIT 2).
YAML_FLOATS = (".inf", ".Inf", ".INF", ".nan", ".NaN", ".NAN",
               ".", "..", ".5.5", ".e+5", ".5", ".05", ".5e+3", ".5E-3",
               "._", ".5_", "._5", ".5_5", ".5e3", ".5E3",
               ".5e-10", ".5E+10", ".5_e-10", ".5e10", ".5.5e-10",
               ".5.5E-10")
#: Names that only look like one of those, which every reader reads as
#: text: each is written bare, as on main.
LOOK_ALIKES = ("openGlass", "openYes", "yEs", "nO", "oN", "Nan", "inf", "_",
               "y_", "no_", "NULL_", "True1", ".x", ".5x", "x.5", ".e5",
               "._.", ".nan_", ".infinity", "..x")
#: Text `y`'s rule is asked of: every text of one or two characters from
#: the characters YAML gives a meaning to, beside letters and digits.
YAML_ALPHABET = "aZ09_.-:@/+ #'\"&*!?[{%|>,"
TEXTS = tuple("".join(chars) for size in (1, 2)
              for chars in itertools.product(YAML_ALPHABET, repeat=size))


def load(path: Path, name: str):
    """`path` loaded as a module called `name`, so its functions are asked
    here and nothing it does at its entry point runs."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def scaffolder():
    """`scaffold-project.py`, to ask how it lists a manifest's pins."""
    return load(SCAFFOLD, "scaffold_one_pin_spelling")


@pytest.fixture(scope="module")
def adopter():
    """`adopt-project.py`, to ask how it lists a manifest's pins."""
    return load(ADOPT, "adopt_one_pin_spelling")


def rendered(entries: str) -> str:
    """`entries`, a `NEUTRAL_PRODUCT_PINS` value, in the manifest template's
    own `neutral_product_pins:` line, rendered by `render` as both tools
    render it."""
    template = REPO / "templates" / "assembly-root" / "project.yaml"
    line, = (line for line in template.read_text(encoding="utf-8")
             .splitlines() if "{{NEUTRAL_PRODUCT_PINS}}" in line)
    return render(f"{line}\n", {"NEUTRAL_PRODUCT_PINS": entries},
                  "project.yaml")


def test_one_list_renders_the_same_lines_through_both_tools(scaffolder,
                                                            adopter):
    """The issue's names as one list, through the scaffold (in the order
    given, here adopt's sorted order) and through adopt: the same lines,
    each adopt's spelling, and the project's reader reads each back as the
    name typed."""
    names = sorted(SPELLED)
    scaffolded = rendered(scaffolder._neutral_product_pins(names))
    adopted = rendered(adopter._neutral_product_pins(set(names)))
    assert scaffolded == adopted
    assert scaffolded.splitlines()[1:] == [f"  - {SPELLED[name]}"
                                           for name in names]
    assert parse_yaml(scaffolded)["neutral_product_pins"] == names


def test_both_tools_call_the_one_function(scaffolder, adopter):
    """Each tool's `_neutral_pin_entry` is `shape_materialize`'s
    `neutral_pin_entry`, not a copy of it, so the two cannot drift apart
    again."""
    shared = (REPO / "scripts" / "shape_materialize.py").resolve()
    for tool in (scaffolder, adopter):
        entry = tool._neutral_pin_entry
        assert (entry.__module__, entry.__qualname__) == (
            "shape_materialize", "neutral_pin_entry"), tool.__name__
        assert Path(entry.__code__.co_filename).resolve() == shared


def adopts_old_entry(adopter, text: str) -> str:
    """How `adopt-project.py`'s own `_neutral_pin_entry` spelled `text` until
    #924: `y`'s spelling where the entry reads back as `text`, and `text`
    double-quoted where it does not."""
    spelled = adopter.y(text)
    try:
        if parse_yaml(f"neutral_product_pins:\n  - {spelled}\n") \
                == {"neutral_product_pins": [text]}:
            return spelled
    except YamlError:
        pass
    return double_quoted(text)


#: The names #912 moved among those: bare in adopt's own spelling, and
#: double-quoted now, because a standard YAML reader takes each for no text.
MOVED_BY_912 = (".", "..", ".0", ".9", "._", "yes")


def test_an_entry_is_bare_exactly_where_y_writes_the_plan_bare(adopter):
    """The shared function is adopt's rule, moved: for every short text
    YAML gives a meaning to, and the issue's names, it writes what adopt's
    own function wrote, which is `y`'s spelling of the plan's `product:`
    wherever the entry reads back, but for a name a standard YAML reader
    takes for no text, which #912 double-quotes; and those are the only
    ones that differ. A change to `y`'s rule that left the entry's behind,
    or the other way round, fails here."""
    differ = {text: (neutral_pin_entry(text), adopts_old_entry(adopter, text))
              for text in (*TEXTS, *SPELLED)
              if neutral_pin_entry(text) != adopts_old_entry(adopter, text)}
    assert differ == {text: (double_quoted(text), text)
                      for text in MOVED_BY_912}


@NEEDS_PYYAML
def test_a_stock_reader_reads_the_issues_names_as_text(scaffolder):
    """The point of #924: PyYAML reads the scaffold's `0x1F` and `1_000` as
    the text typed, as it reads adopt's; and since #912 the bare `yes` it
    read as True from both tools alike, the project's own reader reading it
    back, is double-quoted, and read as `yes`."""
    names = sorted(SPELLED)
    entries = scaffolder._neutral_product_pins(names)
    assert pyyaml.safe_load(rendered(entries))["neutral_product_pins"] \
        == names


# --- a name a standard YAML reader takes for no text (#912) ------------------

@pytest.mark.parametrize("name", [*YAML_WORDS, *YAML_FLOATS])
def test_a_name_yaml_takes_for_no_text_is_double_quoted(name):
    """Each is written double-quoted, and the project's own reader reads it
    back as the name, through the manifest template's own line."""
    entry = neutral_pin_entry(name)
    assert entry == double_quoted(name)
    assert parse_yaml(rendered(f"\n  - {entry}"))["neutral_product_pins"] \
        == [name]


@pytest.mark.parametrize("name", [*YAML_WORDS, *YAML_FLOATS])
def test_the_rule_quotes_it_whatever_the_projects_reader_reads(monkeypatch,
                                                               name):
    """The rule is the YAML specs', not the project's reader's: with that
    reader made to read every spelling back, each is double-quoted all the
    same. The project's reader quotes `true` and `null` itself (#181), so
    this is what holds the rule to them."""
    monkeypatch.setattr(shape_materialize, "_reads_back", lambda *_: True)
    assert neutral_pin_entry(name) == double_quoted(name)


@pytest.mark.parametrize("name", LOOK_ALIKES)
def test_a_name_that_only_looks_like_one_is_written_bare(name):
    """`openGlass` byte for byte, and each name that only looks like a
    bool, a null or a float: bare, as on main, and read back as the
    name."""
    assert neutral_pin_entry(name) == name
    assert parse_yaml(rendered(f"\n  - {name}"))["neutral_product_pins"] \
        == [name]


#: The characters `PIN_ARG_RE` admits in a product's name.
PIN_ALPHABET = ("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
                "0123456789_.-")
#: Every name `--pin` admits of one or two characters, every one of three
#: that begins with a point, and the words and look-alikes above.
PIN_NAMES = tuple(dict.fromkeys((
    *("".join(chars) for size in (1, 2)
      for chars in itertools.product(PIN_ALPHABET, repeat=size)),
    *("." + "".join(chars)
      for chars in itertools.product(PIN_ALPHABET, repeat=2)),
    *YAML_WORDS, *LOOK_ALIKES)))


def stock_readers() -> dict:
    """The standard readers installed here, by name: PyYAML's `safe_load`
    (YAML 1.1), and ruamel.yaml's safe loader as YAML 1.2 and as 1.1."""
    readers = {}
    if pyyaml is not None:
        readers["PyYAML"] = pyyaml.safe_load
    if RuamelYAML is not None:
        for version in ((1, 2), (1, 1)):
            loader = RuamelYAML(typ="safe", pure=True)
            loader.version = version
            readers[f"ruamel.yaml {version}"] = loader.load
    return readers


@pytest.mark.skipif(not stock_readers(),
                    reason="neither PyYAML nor ruamel.yaml is installed "
                           "here; the rows above hold the rule without them")
def test_every_stock_reader_reads_every_entry_as_the_name(scaffolder):
    """The issue's Goal: any YAML reader reads a pinned product back as
    text. Every name in `PIN_NAMES`, in one list through the scaffold, is
    read by each standard reader here as the name; on main 6c861635
    PyYAML read `yes`, `on` and `.5` as True, True and 0.5, and ruamel.yaml
    failed on `._`."""
    names = list(PIN_NAMES)
    text = rendered(scaffolder._neutral_product_pins(names))
    for reader, load in stock_readers().items():
        read = load(text)["neutral_product_pins"]
        assert len(read) == len(names), reader
        misread = {name: got for name, got in zip(names, read)
                   if got != name}
        assert misread == {}, reader
