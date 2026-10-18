# SPDX-License-Identifier: Apache-2.0
"""`docs/cli.md` says what the assembly root's bootstrap places with the
condition #704 holds it to (#764, C3).

THE DEFECT. The flag-level reference's row for
`templates/assembly-root/scripts/bootstrap.py` said it "places each leg on
its tracking branch AT the pinned commit", with no condition. Since #704
(Brett Heap's R1 and R2, 2026-10-16T13:07:34Z) it places a leg there only
where that loses no commit, and `AGENTS-shape.md`, which every project
carries, says so in R2's words. The row is generated from
`scripts/render-cli-reference.py`, so `tests/test_cli_reference.py` held the
two in step and neither to the rule.

THE RULE NOW. The row carries R2's condition, word for word as the pinned
`AGENTS-shape.md` says it. The other pinned sentences, which say bootstrap
places a leg there "or says why not" (the Makefile's help, the family
holder's `AGENTS-shape.md` and README, and `AGENTS-shape.md`'s own table of
five commands), are true as they stand, so R2 left them and so does this.
"""

from __future__ import annotations

import re

from conftest import REPO

#: R2's condition, as the pinned `AGENTS-shape.md` words it.
CONDITION = ("only where that loses no commit, and otherwise leaves its "
             "checkout where it is, saying why")


def one_line(path) -> str:
    """The file's text with every run of white space made one space, so a
    sentence wrapped across lines reads as one."""
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def test_the_pinned_agent_file_still_says_r2s_condition():
    """The words this file holds the reference to are R2's own."""
    agents = one_line(REPO / "templates" / "assembly-root" /
                      "AGENTS-shape.md")
    assert ("`make bootstrap` places a leg on its tracking branch AT the "
            f"pin {CONDITION}.") in agents


def test_the_reference_row_for_the_assembly_bootstrap_says_the_condition():
    row = next(line for line in (REPO / "docs" / "cli.md").read_text(
        encoding="utf-8").splitlines()
        if line.startswith("| [`templates/assembly-root/scripts/"
                           "bootstrap.py`]"))
    assert (f"places each leg on its tracking branch AT the pinned commit "
            f"{CONDITION}. What `make bootstrap` runs. |") in row, row
