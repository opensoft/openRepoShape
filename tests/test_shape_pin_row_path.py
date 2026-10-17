# SPDX-License-Identifier: Apache-2.0
"""A shape pin's `files:` row with no path is refused by name (#681, L2-3).

`_check_one_shape_file` in the holder's `scripts/validate-family.py`, and
`_check_shape_copy` in the assembly root's `scripts/validate-pins.py`, asked
only whether a row is a mapping and then read `str(row.get("path"))`, so a
row `- nopath: x` was `FINDING shape-copy-missing: contracts/shape-pin.yaml:
None is pinned but absent`: the value `None` read as a path. `path: ''`
and `path: 5` were the same, as ` ` and `5`. `update-shape.py` refuses such
a row by name (`update-pin-row`). Both validators now say `shape-pin-row`,
the code their non-mapping branch says, naming the value, and check every
other row as before.

THE SAME ROOTS as `tests/test_shape_pin_files_not_a_list.py` (#290): a
clean scaffold's clone, and a holder `family.py init` made, whose fixtures
are imported. The row is written beside the real ones, as BYTES, so the
pin stays LF on every OS and every other row still matches its file.
"""

from __future__ import annotations

import pytest

from conftest import run_script
from test_shape_pin_files_not_a_list import (  # noqa: F401
    SHAPE_PIN, findings, holder, initialised_holder, no_traceback,
)

#: `(the row written into files:, how the validator shows its path:)`.
ROWS = [
    pytest.param("  - nopath: x\n", "None", id="absent"),
    pytest.param("  - path:\n", "None", id="null"),
    pytest.param("  - path: ''\n", "''", id="empty"),
    pytest.param("  - path: 5\n", "5", id="number"),
    pytest.param("  - path: [a]\n", "['a']", id="list"),
]

#: Each root and the validator it carries.
ROOTS = [
    pytest.param("project", "validate-pins.py", id="assembly-root"),
    pytest.param("holder", "validate-family.py", id="family-holder"),
]


@pytest.mark.parametrize("fixture, validator", ROOTS)
@pytest.mark.parametrize("row, shown", ROWS)
def test_a_files_row_with_no_path_is_shape_pin_row(request, fixture,
                                                   validator, row, shown):
    """One finding, `shape-pin-row`, naming the row's `path:` as the
    validator names any value it cannot use, and no `shape-copy-missing`:
    the value is never read as a path. The real rows are checked as before,
    so it is the only finding, exit 1."""
    root = request.getfixturevalue(fixture)
    pin = root / SHAPE_PIN
    text = pin.read_bytes()
    assert text.count(b"\nfiles:\n") == 1, "fixture drift: the pin's files:"
    pin.write_bytes(text.replace(b"\nfiles:\n",
                                 b"\nfiles:\n" + row.encode("utf-8")))

    result = run_script(root / "scripts" / validator, cwd=root)

    no_traceback(result)
    assert result.returncode == 1, result.stdout + result.stderr
    assert findings(result, "shape-pin-row") == [
        f"FINDING shape-pin-row: {SHAPE_PIN}: a files row's `path:` is "
        f"{shown}, not the path of a file"]
    assert result.stderr.count("FINDING ") == 1, result.stderr
