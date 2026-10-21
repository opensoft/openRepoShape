# SPDX-License-Identifier: Apache-2.0
"""A pin's `commit:` or `tree_sha256:` that ends in a line break is not well
formed (#1017).

THE DEFECT, measured on main 2a119f28 (Python 3.12.3). `repo_shape.COMMIT_RE`
and `SHA256_RE` were `^[0-9a-fA-F]{40}$` and `^[0-9a-fA-F]{64}$`, and every
caller reads them with `.match`. In Python `$` also matches just before a
trailing line feed, so:

| pattern     | value                  | `.match` on main |
|-------------|------------------------|------------------|
| `COMMIT_RE` | 40 hex                 | a match          |
| `COMMIT_RE` | 40 hex and `"\\n"`      | a match          |
| `COMMIT_RE` | 40 hex and `"\\r\\n"`   | None             |
| `COMMIT_RE` | 40 hex and `" "`       | None             |
| `SHA256_RE` | 64 hex                 | a match          |
| `SHA256_RE` | 64 hex and `"\\n"`      | a match          |
| `SHA256_RE` | 64 hex and `"\\r\\n"`   | None             |
| `SHA256_RE` | 64 hex and `" "`       | None             |

A line feed at the end of a value reaches them through YAML: the reader takes
the double-quoted escape `"<hex>\\n"` and a block scalar (`commit: |`) as the
hex and a line feed. Through that, on main:

- `validate-manifest.py` passed a `shape.commit` and a
  `shape.digests.tree_sha256` that ended in one (`manifest ok`, exit 0), and
  `validate-family.py` the same two in `family.yaml`;
- `validate-pins.py` took a leg pin's `commit:` for 40 hex and refused it as
  `pin-commit-unresolvable`, naming the commit as one the leg's object store
  lacks, and a digest as `pin-digest-mismatch`, a recomputation that differs;
- `adopt-project.py check` read a plan's `commit:` as well formed.

THE RULE NOW. Both patterns end in `\\Z`, which matches at the very end of the
value and nowhere else, so each caller's `.match` refuses a value that ends in
a line break, as it refuses one that ends in `"\\r\\n"` or `" "`. The assembly
root's `bootstrap.py` holds a COPY of `COMMIT_RE`, `COMMIT_40`, which ends the
same way. Everything else about the two patterns is unchanged: 40 means 40, a
digit more or fewer is refused, and the case of the hex does not matter.

The caller rows are beside the files they exercise: `test_pin_validator.py`
(`validate-pins.py`), `test_manifest_validator.py` (`validate-manifest.py`),
`test_adopt_pins.py` (`adopt-project.py check`) and `test_shape_doctor.py`
(`update-shape.py`'s `read_pin`, through the doctor). The rows here are the
patterns, their copy, the holder's gate, the two callers that had no row
beside them (the neutral product's pin in `validate-pins.py` and a record
row's `source_commit:` in `validate-manifest.py`) and the two readers that
take a pin's `commit:` without a gate of their own in front of them.

No network and no GitHub: the family is the offline one of `test_family.py`.
"""

from __future__ import annotations

import functools
import re
import sys

import pytest

from conftest import REPO, load_without_bytecode
from test_family import family, validate  # noqa: F401
from test_family_add_refusals import holder  # noqa: F401
from test_manifest_validator import (  # noqa: F401
    ANSWER_RECORD, SUBMODULE_RECORD, assert_refused)
from test_neutral_pin_validator import (
    edit_pin as edit_neutral_pin, scaffold_with_pin,
    validate as validate_pins)

sys.path.insert(0, str(REPO / "scripts"))
import repo_shape  # noqa: E402

BOOTSTRAP = REPO / "templates" / "assembly-root" / "scripts" / "bootstrap.py"
DOCTOR = REPO / "shape-doctor.py"

#: Sixteen digits in each case, so a value cut from it holds both.
HEX = "0123456789abcdefABCDEF"
COMMIT = (HEX * 2)[:40]
DIGEST = (HEX * 3)[:64]


@functools.cache
def bootstrap_copy():
    """The assembly root's `bootstrap.py`, loaded from the template."""
    return load_without_bytecode(BOOTSTRAP, "bootstrap_line_break")


@functools.cache
def doctor_module():
    return load_without_bytecode(DOCTOR, "shape_doctor_line_break")


#: `(the pattern, how many digits it takes)`: the two of `repo_shape`, and
#: the copy of the first that `bootstrap.py` holds.
PATTERNS = [
    pytest.param(lambda: repo_shape.COMMIT_RE, 40, id="COMMIT_RE"),
    pytest.param(lambda: repo_shape.SHA256_RE, 64, id="SHA256_RE"),
    pytest.param(lambda: bootstrap_copy().COMMIT_40, 40,
                 id="bootstrap-COMMIT_40"),
]

#: What may not follow the digits: a line feed (the one `$` took), a
#: carriage return and line feed, a space, a second line feed, a lone
#: carriage return and a tab.
AFTER = [
    pytest.param("\n", id="line-feed"),
    pytest.param("\r\n", id="crlf"),
    pytest.param(" ", id="space"),
    pytest.param("\n\n", id="two-line-feeds"),
    pytest.param("\r", id="carriage-return"),
    pytest.param("\t", id="tab"),
]


def digits_of(taken: int) -> str:
    return COMMIT if taken == 40 else DIGEST


@pytest.mark.parametrize("pattern, taken", PATTERNS)
@pytest.mark.parametrize("form", [str.lower, str.upper, str],
                         ids=["lower", "upper", "mixed"])
def test_a_pattern_takes_its_digits_in_any_case(pattern, taken, form):
    """What it took on main, and takes now."""
    assert pattern().match(form(digits_of(taken))) is not None


@pytest.mark.parametrize("pattern, taken", PATTERNS)
def test_a_pattern_takes_exactly_its_digits(pattern, taken):
    """40 means 40, and 64 means 64: a digit fewer or more is refused."""
    digits = digits_of(taken)
    assert pattern().match(digits[:-1]) is None
    assert pattern().match(digits + "0") is None


@pytest.mark.parametrize("pattern, taken", PATTERNS)
@pytest.mark.parametrize("after", AFTER)
def test_a_pattern_refuses_a_value_that_ends_in_a_line_break_or_a_space(
        pattern, taken, after):
    """THE ISSUE'S ROWS: `"\\n"`, `"\\r\\n"` and `" "` after the digits. Only
    the first was taken on main, by `$`."""
    assert pattern().match(digits_of(taken) + after) is None


@pytest.mark.parametrize("pattern, taken", PATTERNS)
def test_a_pattern_refuses_a_line_break_before_the_digits(pattern, taken):
    """The start of the value is `^`'s, which is not multiline."""
    assert pattern().match("\n" + digits_of(taken)) is None


# --- the holder's gate -------------------------------------------------------


def with_a_line_feed(text: str, key: str, value: str) -> str:
    """`text` with the first `key: "<value>"` read as `<value>` and a line
    feed: the double-quoted `\\n` escape, which a file spells with a
    backslash and an `n`."""
    old = f'{key}: "{value}"'
    assert old in text, f"fixture drift: {old!r} not in the file"
    return text.replace(old, f'{key}: "{value}\\n"', 1)


def holder_text(root) -> str:
    return (root / "family.yaml").read_text(encoding="utf-8")


def member_pin(root) -> tuple[str, str]:
    """`(commit, tree_sha256)` of the first member's pin in `family.yaml`,
    which the `pin:` block of its row holds."""
    text = holder_text(root)
    commit = re.search(r'^      commit: "([0-9a-f]{40})"', text, re.M)
    digest = re.search(r'^      tree_sha256: "([0-9a-f]{64})"', text, re.M)
    assert commit, f"fixture drift: no member pin commit in {text}"
    assert digest, f"fixture drift: no member pin tree_sha256 in {text}"
    return commit.group(1), digest.group(1)


def holder_shape(root) -> tuple[str, str]:
    """`(commit, tree_sha256)` of the holder's own `shape:` block."""
    text = holder_text(root)
    commit = re.search(r'^  commit: "([0-9a-f]{40})"', text, re.M)
    digest = re.search(r'^    tree_sha256: "([0-9a-f]{64})"', text, re.M)
    assert commit, f"fixture drift: no shape commit in {text}"
    assert digest, f"fixture drift: no shape tree_sha256 in {text}"
    return commit.group(1), digest.group(1)


def test_the_holders_gate_passes_the_family_as_scaffolded(holder):
    """The baseline of the rows below: no finding, exit 0."""
    gate = validate(holder)
    assert gate.returncode == 0, gate.stderr + gate.stdout


def test_a_member_pin_commit_that_ends_in_a_line_break_is_refused(holder):
    """`member-pin-commit`, the refusal a pin of 12 digits gets; a commit
    that `$` let through was named as one the member's object store lacks."""
    commit, _ = member_pin(holder)
    (holder / "family.yaml").write_bytes(with_a_line_feed(
        holder_text(holder), "      commit", commit).encode("utf-8"))
    gate = validate(holder)
    assert gate.returncode == 2, gate.stderr + gate.stdout
    assert gate.stderr.startswith("REFUSED member-pin-commit: "), gate.stderr


def test_a_member_pin_digest_that_ends_in_a_line_break_is_malformed(holder):
    _, digest = member_pin(holder)
    (holder / "family.yaml").write_bytes(with_a_line_feed(
        holder_text(holder), "      tree_sha256", digest).encode("utf-8"))
    gate = validate(holder)
    assert gate.returncode == 1, gate.stderr + gate.stdout
    assert "FINDING member-digest-malformed: " in gate.stderr, gate.stderr


def test_a_family_shape_commit_that_ends_in_a_line_break_is_a_finding(holder):
    commit, _ = holder_shape(holder)
    (holder / "family.yaml").write_bytes(with_a_line_feed(
        holder_text(holder), "  commit", commit).encode("utf-8"))
    gate = validate(holder)
    assert gate.returncode == 1, gate.stderr + gate.stdout
    assert "FINDING family-shape-commit: " in gate.stderr, gate.stderr


def test_a_family_shape_digest_that_ends_in_a_line_break_is_a_finding(holder):
    _, digest = holder_shape(holder)
    (holder / "family.yaml").write_bytes(with_a_line_feed(
        holder_text(holder), "    tree_sha256", digest).encode("utf-8"))
    gate = validate(holder)
    assert gate.returncode == 1, gate.stderr + gate.stdout
    assert "FINDING family-shape-digest: " in gate.stderr, gate.stderr


# --- the two callers with no row beside them --------------------------------
#
# Each reads a value with `COMMIT_RE` or `SHA256_RE` and no other gate, so
# nothing but the pattern refuses a line feed there: a `.rstrip("\n")` before
# the match would leave every row above green.


def test_a_neutral_pin_commit_that_ends_in_a_line_break_is_refused(tmp_path):
    """`validate-pins.py` reads the neutral product's pin with `COMMIT_RE`
    and no other gate. On main a commit of 40 hex and a line feed passed
    it, and the finding was the product's checkout refusing the name
    (`neutral-pin-source-unreadable`), not that it is not 40 hex."""
    root, product, commit = scaffold_with_pin(tmp_path)
    edit_neutral_pin(root, f'commit: "{commit}"', f'commit: "{commit}\\n"')
    gate = validate_pins(root, "--pin-source", str(product))
    assert gate.returncode == 2, gate.stderr + gate.stdout
    assert "REFUSED neutral-pin-tag-only: " in gate.stderr, gate.stderr


def test_a_neutral_pin_digest_that_ends_in_a_line_break_is_malformed(tmp_path):
    """On main the digest passed `SHA256_RE` and was recomputed and compared
    (`neutral-pin-digest-mismatch`); it is not 64 hex."""
    root, product, _ = scaffold_with_pin(tmp_path)
    pin = (root / "contracts" / "openglass-pin.yaml").read_text()
    recorded = pin.split('tree_sha256: "')[1].split('"')[0]
    edit_neutral_pin(root, f'tree_sha256: "{recorded}"',
                     f'tree_sha256: "{recorded}\\n"')
    gate = validate_pins(root, "--pin-source", str(product))
    assert gate.returncode == 1, gate.stderr + gate.stdout
    assert "FINDING neutral-pin-digest-malformed: " in gate.stderr, gate.stderr


@pytest.mark.parametrize("record, code", [
    pytest.param(SUBMODULE_RECORD, "manifest-submodule-commit",
                 id="submodules"),
    pytest.param(ANSWER_RECORD, "manifest-answered-commit",
                 id="answered-paths"),
])
def test_a_recorded_source_commit_that_ends_in_a_line_break_is_a_finding(
        project, record, code):
    """`validate-manifest.py` reads a record row's `source_commit:` with
    `COMMIT_RE`, and the two records share the check. On main a commit of 40
    hex and a line feed was `manifest ok`."""
    found = re.search(r'source_commit: "([0-9a-f]{40})"', record)
    assert found, "fixture drift: the record names no source_commit"
    commit = found.group(1)
    assert_refused(project, record, f'source_commit: "{commit}"',
                   f'source_commit: "{commit}\\n"', code)


# --- the two readers with no gate in front of them ----------------------------

#: A commit the cache can name that the pin below is not at.
TIP = "b" * 40
#: The first words of the notice's one line, over `TIP`.
NOTICE = f"  shape: the upstream is at {TIP[:12]} and this project is pinned at "


def a_root(base, pin: bytes):
    """A root holding only `contracts/shape-pin.yaml` and a cached tip."""
    (base / "contracts").mkdir(parents=True)
    (base / "contracts" / "shape-pin.yaml").write_bytes(pin)
    (base / ".shape-upstream-tip").write_bytes(f"{TIP}\n".encode())
    return base


def test_the_upstream_notice_names_a_pin_that_is_40_hex(tmp_path, capsys):
    """The baseline of the row below: the notice is not silent for a reason
    of its own."""
    bootstrap_copy().shape_upstream_notice(
        a_root(tmp_path, f'commit: "{COMMIT.lower()}"\n'.encode()))
    assert capsys.readouterr().out.startswith(NOTICE)


def test_the_upstream_notice_is_silent_over_a_pin_that_ends_in_a_line_break(
        tmp_path, capsys):
    """An absent answer is no finding: a pin that is not a commit leaves the
    notice silent, and `COMMIT_40` took one that ends in a line feed for one."""
    bootstrap_copy().shape_upstream_notice(
        a_root(tmp_path, f'commit: "{COMMIT.lower()}\\n"\n'.encode()))
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("value, said", [
    pytest.param(COMMIT.lower(), COMMIT.lower(), id="40-hex"),
    pytest.param(COMMIT.lower() + "\\n", None, id="40-hex-and-a-line-feed"),
])
def test_the_doctor_reads_a_pins_commit_as_the_validators_do(tmp_path, value,
                                                             said):
    """`shape-doctor.py`'s `pin_commit` is the commit a leg's pin names, or
    None for one the validators refuse."""
    (tmp_path / "contracts").mkdir()
    (tmp_path / "contracts" / "spec-pin.yaml").write_bytes(
        f'commit: "{value}"\n'.encode())
    assert doctor_module().pin_commit(
        tmp_path, "contracts/spec-pin.yaml") == said
