# SPDX-License-Identifier: Apache-2.0
"""`load_yaml` refuses a file it cannot read, under one code and never bare.

Three ways a YAML file can fail to become data, and the refusal each one is:

- not there, or not openable (`OSError`): `yaml-unreadable`;
- there, opened, and not UTF-8 (`UnicodeDecodeError`): `yaml-unreadable`;
- decoded, and not the YAML this reader implements (`YamlError`):
  `yaml-unparsable`.

The middle one used to be no refusal at all (#192). `UnicodeDecodeError` is a
`ValueError`, and `Path.read_text` raises it AFTER the open succeeded, so the
`except OSError` beside it never saw it and every reader that goes through
`load_yaml` -- `adopt-project.py check` and `execute`, the manifest and pin
validators, `bootstrap.py`, `update-shape.py` -- died with a Python traceback
instead of a `REFUSED` line with a remediation. The readers' own tests are in
`test_adopt_execute_refusals.py` (the adoption plan) and
`test_manifest_validator.py` (`project.yaml`); this file is the function.

NO NETWORK AND NO GITHUB: a temporary file and an import.
"""

from __future__ import annotations

import sys

import pytest

from conftest import REPO

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import Refusal, load_yaml  # noqa: E402

#: `(bytes, offset of the first byte that is not UTF-8)`. Each is a way a file
#: reaches this state: a Latin-1 `é` where UTF-8 has two bytes, a UTF-16 byte
#: order mark at the very start, a UTF-8 sequence cut off by the end of the
#: file, and the same bad byte in a comment, which the parser would never have
#: looked at -- the whole file is decoded before it is parsed.
NOT_UTF8 = {
    "latin-1-e-acute": (b"name: caf\xe9\n", 9),
    "utf-16-byte-order-mark": (b"\xff\xfen\x00a\x00m\x00e\x00", 0),
    "sequence-cut-off-by-the-end": (b"name: caf\xc3", 9),
    "in-a-comment": (b"# caf\xe9\nname: cafe\n", 5),
}


def refusal_for(path) -> Refusal:
    with pytest.raises(Refusal) as caught:
        load_yaml(path)
    return caught.value


@pytest.mark.parametrize("case", sorted(NOT_UTF8))
def test_a_file_that_is_not_utf8_is_yaml_unreadable(tmp_path, case):
    body, offset = NOT_UTF8[case]
    path = tmp_path / "plan.yaml"
    path.write_bytes(body)
    refusal = refusal_for(path)
    assert refusal.code == "yaml-unreadable"
    assert str(path) in refusal.detail, "the file is named"
    assert f"not UTF-8 at byte {offset}" in refusal.detail
    assert refusal.__cause__.reason in refusal.detail, (
        "and so is why Python would not decode it")
    assert isinstance(refusal.__cause__, UnicodeDecodeError)


@pytest.mark.parametrize("case", sorted(NOT_UTF8))
def test_the_remediation_says_utf8_and_names_the_byte(tmp_path, case):
    """Said in the remediation as well as the detail, because `main` prints
    `str(exc)` and a caller that keeps only the remedy still tells a person
    where to look; and not the default remediation, which is about
    submodules and would send them to the wrong place."""
    body, offset = NOT_UTF8[case]
    path = tmp_path / "plan.yaml"
    path.write_bytes(body)
    refusal = refusal_for(path)
    assert refusal.remediation.startswith("Remediation: ")
    assert "UTF-8" in refusal.remediation
    assert f"Byte {offset}" in refusal.remediation
    assert "git submodule" not in refusal.remediation
    assert str(refusal).startswith(f"REFUSED yaml-unreadable: {path}")
    assert str(refusal).endswith(refusal.remediation)


def test_a_missing_file_is_still_yaml_unreadable(tmp_path):
    path = tmp_path / "absent.yaml"
    refusal = refusal_for(path)
    assert refusal.code == "yaml-unreadable"
    assert str(path) in refusal.detail
    assert isinstance(refusal.__cause__, OSError)


def test_yaml_this_reader_does_not_implement_is_still_yaml_unparsable(tmp_path):
    path = tmp_path / "tabbed.yaml"
    path.write_text("legs:\n\t- role: spec\n", encoding="utf-8")
    refusal = refusal_for(path)
    assert refusal.code == "yaml-unparsable"
    assert str(path) in refusal.detail


def test_utf8_that_is_not_ascii_is_read_not_refused(tmp_path):
    """The new `except` is for bytes that are not UTF-8, not for text that is
    not ASCII: a name with an accent is a valid file."""
    path = tmp_path / "plan.yaml"
    path.write_bytes("name: café\nnote: \"—\"\n".encode("utf-8"))
    assert load_yaml(path) == {"name": "café", "note": "—"}
