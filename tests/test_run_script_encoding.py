# SPDX-License-Identifier: Apache-2.0
"""`run_script` decodes a child's output in the encoding the caller names
(#1196, from #1185's review).

A child told `PYTHONIOENCODING=utf-8` writes U+00E9 as the two bytes 0xC3
0xA9. `run_script` read them in the PARENT's locale, and a parent in a locale
of one byte to a character, Latin-1 say, read two characters: the rows of
`tests/test_adopt_plan_paths_spelled.py` that name `pl\\u00e9an.yaml` failed
on a tool that was right. They name `encoding="utf-8"` now. Each row here
names an encoding that reads the two bytes one way and no other, so the
keyword is held in any locale the suite runs in, with no Latin-1 locale
built: the child is the same, and only the name differs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import run_script

#: A child that writes the two bytes of U+00E9 in UTF-8 to stdout and to
#: stderr, as one told `PYTHONIOENCODING=utf-8` does.
SAYS_E_ACUTE = ("import sys\n"
                "sys.stdout.buffer.write(bytes([0xC3, 0xA9]))\n"
                "sys.stderr.buffer.write(bytes([0xC3, 0xA9]))\n")


@pytest.mark.parametrize("encoding, read", [
    pytest.param("utf-8", "\u00e9", id="utf-8-reads-one-character"),
    pytest.param("latin-1", "\u00c3\u00a9",
                 id="latin-1-reads-two"),
])
def test_the_output_is_read_in_the_encoding_the_caller_names(
        tmp_path, encoding, read):
    """Stdout and stderr both, as the named encoding reads the two bytes:
    one character in UTF-8 and two in Latin-1. A `run_script` that dropped
    the keyword would read both in this process's own locale, which is one
    answer for the two rows, so one of them would fail."""
    script = tmp_path / "say_e_acute.py"
    script.write_text(SAYS_E_ACUTE, encoding="ascii")
    result = run_script(script, encoding=encoding)
    assert result.returncode == 0, result.stderr
    assert result.stdout == read
    assert result.stderr == read
