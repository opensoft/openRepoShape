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
"""

from __future__ import annotations

import importlib.util
import itertools
import sys
from pathlib import Path

import pytest

from conftest import ADOPT, REPO, SCAFFOLD

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import YamlError, double_quoted, parse_yaml  # noqa: E402
from shape_materialize import neutral_pin_entry, render  # noqa: E402

try:
    import yaml as pyyaml  # the oracle only: nothing shipped imports it
except ImportError:  # pragma: no cover - depends on the machine
    pyyaml = None

NEEDS_PYYAML = pytest.mark.skipif(
    pyyaml is None,
    reason="PyYAML is not installed here, so the comparison with a stock "
           "reader is skipped; the project's own reader is asked by the "
           "tests beside this one")

#: The issue's names, each with the line both tools now write for it:
#: adopt's spelling, double-quoted where `y` quotes the plan's `product:`.
SPELLED = {
    "0x1F": '"0x1F"',
    "1_000": '"1_000"',
    "1e3": '"1e3"',
    "3dGlass": '"3dGlass"',
    "-x": '"-x"',
    "openGlass": "openGlass",
    "007": '"007"',
    "yes": "yes",
}
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


def test_an_entry_is_bare_exactly_where_y_writes_the_plan_bare(adopter):
    """The shared function is adopt's rule, moved: for every short text
    YAML gives a meaning to, and the issue's names, it writes what adopt's
    own function wrote, which is `y`'s spelling of the plan's `product:`
    wherever the entry reads back. A change to `y`'s rule that left the
    entry's behind, or the other way round, fails here."""
    differ = {text: (neutral_pin_entry(text), adopts_old_entry(adopter, text))
              for text in (*TEXTS, *SPELLED)
              if neutral_pin_entry(text) != adopts_old_entry(adopter, text)}
    assert differ == {}


@NEEDS_PYYAML
def test_a_stock_reader_reads_a_name_that_opens_with_a_digit_as_text(
        scaffolder):
    """The point of #924: PyYAML reads the scaffold's `0x1F` and `1_000` as
    the text typed, as it reads adopt's. A bare `yes` it still reads as
    True, from both tools alike: the project's own reader reads it back,
    and whether to quote it is #457's L2-14, on #912."""
    names = [name for name in sorted(SPELLED) if not name[0].isalpha()]
    entries = scaffolder._neutral_product_pins(names)
    assert pyyaml.safe_load(rendered(entries))["neutral_product_pins"] \
        == names
