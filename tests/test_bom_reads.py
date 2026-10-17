# SPDX-License-Identifier: Apache-2.0
"""A file a Windows editor saved with a byte-order mark is read as the text
it holds, by every reader of it (#855).

THE DEFECT, measured on main 9f235da2 by loading the shipped scripts and
calling them, and by running them in a scaffold:

- `.shape-upstream-tip` holding the bytes EF BB BF and a commit, with LF or
  CRLF, made the assembly root's upstream notice say nothing:
  `read_text(encoding="utf-8").strip()` kept U+FEFF, which `COMMIT_40`
  does not match.
- `repo_shape.load_yaml` read the mark as the first character of the first
  key (`commit` was U+FEFF and `commit`), and refused a file whose first
  line is a comment, at line 1. So a marked `project.yaml` was `FINDING
  manifest-schema-version: schema_version is None, expected 1`, `make
  bootstrap` ended `bootstrap FAILED: manifest (exit 1)`, and a marked
  `contracts/shape-pin.yaml` left the notice silent.

THE RULE NOW. The cache is read as `utf-8-sig`. `parse_yaml` takes off
every byte-order mark the text starts with, so `load_yaml` and each reader
that hands the parser a pin's text without reading a file (the doctor's
`pin_at`, `update-shape.py`'s `_committed_pin`, `adopt-project.py`'s
`_pinned_shape_paths`, `pin_values_in`) read the same mapping, as
`shape_advisory.py` already did. A fix in `load_yaml` alone left `pin_at`
reading a committed pin every validator reads as broken, and the doctor's
NEXT put back the pin from before it; the regression row below is that run.

Every mark is written by this file as bytes (`codecs.BOM_UTF8`), never
typed.
"""

from __future__ import annotations

import codecs
from pathlib import Path

import pytest

from conftest import REPO, git, load_without_bytecode, run_script
from test_doctor_pin_restore_merges import apply_on, moved_on
from test_shape_doctor import (  # noqa: F401
    SHAPE_PIN, SPEC_PIN, UPSTREAM_TARGET, commit_in, doctor, project, rows_of,
    scaffolded_here, standard,
)

import shape_advisory  # noqa: E402
import shape_materialize  # noqa: E402
from repo_shape import Refusal, load_yaml  # noqa: E402

MARK = codecs.BOM_UTF8
#: The line a person may put above the file's first key before saving it.
COMMENT = b"# saved by hand\n"
PINNED = "a" * 40
TIP = "b" * 40
#: The first words of the notice's one line, naming the cache's commit.
NOTICE = (f"  shape: the upstream is at {TIP[:12]} and this project is "
          f"pinned at {PINNED[:12]}. ")
BOOTSTRAP = REPO / "templates" / "assembly-root" / "scripts" / "bootstrap.py"
#: The issue's two shapes of a hand-saved file, each holding the same keys.
SHAPES = {
    "first-key": f"commit: {PINNED}\nother: 1\n".encode(),
    "comment-first": COMMENT + f"commit: {PINNED}\nother: 1\n".encode(),
}


@pytest.fixture(scope="module")
def notice():
    """The assembly root's `shape_upstream_notice`, loaded from the template
    beside this checkout's `scripts/repo_shape.py`."""
    return load_without_bytecode(BOOTSTRAP,
                                 "bootstrap_bom_reads").shape_upstream_notice


@pytest.fixture(scope="module")
def tools():
    """The three tools whose readers hand `parse_yaml` a pin's text."""
    return {name: load_without_bytecode(REPO / f"{name}.py",
                                        f"{name.replace('-', '_')}_bom")
            for name in ("update-shape", "shape-doctor", "adopt-project")}


def a_root(base: Path, pin: bytes, cache: bytes) -> Path:
    """A root holding only `contracts/shape-pin.yaml` and the cache."""
    (base / "contracts").mkdir(parents=True)
    (base / SHAPE_PIN).write_bytes(pin)
    (base / ".shape-upstream-tip").write_bytes(cache)
    return base


@pytest.mark.parametrize("cache", [
    pytest.param(f"{TIP}\n".encode(), id="no-mark"),
    pytest.param(MARK + f"{TIP}\n".encode(), id="mark"),
    pytest.param(MARK + f"{TIP}\r\n".encode(), id="mark-and-crlf"),
])
def test_the_notice_names_the_tip_a_marked_cache_holds(notice, tmp_path,
                                                       capsys, cache):
    """THE ISSUE'S FIRST LINE: each says the upstream's tip."""
    notice(a_root(tmp_path, f"commit: {PINNED}\n".encode(), cache))
    assert capsys.readouterr().out.startswith(NOTICE)


@pytest.mark.parametrize("marks", [0, 1, 2], ids=["no-mark", "mark",
                                                  "two-marks"])
@pytest.mark.parametrize("shape", list(SHAPES))
def test_load_yaml_reads_a_marked_file_as_the_keys_it_holds(tmp_path, shape,
                                                            marks):
    """THE ISSUE'S SECOND LINE, its first two shapes: no first key spelled
    with U+FEFF, and no refusal at line 1. Two marks read as one does, as
    `shape_advisory.py` reads them."""
    path = tmp_path / "hand-saved.yaml"
    path.write_bytes(MARK * marks + SHAPES[shape])
    assert sorted(load_yaml(path)) == ["commit", "other"]


@pytest.mark.parametrize("marks", [0, 1, 2], ids=["no-mark", "mark",
                                                  "two-marks"])
def test_the_notice_reads_a_marked_shape_pin(notice, tmp_path, capsys,
                                             marks):
    """The second line's third shape: the pin as the notice reads it."""
    notice(a_root(tmp_path, MARK * marks + f"commit: {PINNED}\n".encode(),
                  f"{TIP}\n".encode()))
    assert capsys.readouterr().out.startswith(NOTICE)


def test_a_byte_that_is_not_utf_8_is_counted_from_the_files_first_byte(
        tmp_path):
    """The mark's three bytes are counted: `load_yaml` decodes as `utf-8`,
    and the parser, not the decode, takes the mark off. `utf-8-sig` would
    count from after the mark and name byte 4 of a file whose 0xff is its
    byte 7, where the remedy says to count from the file's start."""
    path = tmp_path / "hand-saved.yaml"
    path.write_bytes(MARK + b"k: v\xff\n")
    with pytest.raises(Refusal) as refused:
        load_yaml(path)
    assert refused.value.detail.endswith(
        ": not UTF-8 at byte 7 (invalid start byte)"), refused.value.detail


@pytest.mark.parametrize("marks", [1, 2], ids=["mark", "two-marks"])
def test_the_advisory_reads_a_marked_manifest_as_load_yaml_does(project,
                                                               marks):
    """`shape_advisory.py` took every mark off before #855; the two read the
    same mapping now."""
    manifest = project / "project.yaml"
    manifest.write_bytes(MARK * marks + manifest.read_bytes())
    tree = shape_advisory.Tree(project, None)
    assert shape_advisory._read_mapping(tree, "project.yaml") == \
        load_yaml(manifest)


def test_a_root_whose_hand_saved_files_carry_the_mark_bootstraps_ok(project):
    """Every reader a root runs agrees: the three validators and the notice.
    On main this run ended `bootstrap FAILED: manifest (exit 1)`."""
    for name in ("project.yaml", SHAPE_PIN, SPEC_PIN,
                 "contracts/code-pin.yaml"):
        (project / name).write_bytes(MARK + (project / name).read_bytes())
    (project / ".shape-upstream-tip").write_bytes(MARK + f"{TIP}\r\n".encode())
    result = run_script(project / "scripts" / "bootstrap.py", cwd=project,
                        env={"SHAPE_UPSTREAM_PATH": ""})
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"  shape: the upstream is at {TIP[:12]} " in result.stdout
    assert result.stdout.endswith("\nbootstrap ok\n"), result.stdout


# ---------------------------------------------------------------------------
# The readers that hand `parse_yaml` a pin's text, with a committed shape pin
# saved by hand: the mark, a comment line, then the pin the scaffold wrote.
# Each reads what `load_yaml` reads of the same bytes.
# ---------------------------------------------------------------------------


@pytest.fixture
def hand_saved(project) -> Path:
    """`project` with that shape pin committed on `main`."""
    pin = project / SHAPE_PIN
    pin.write_bytes(MARK + COMMENT + pin.read_bytes())
    git("add", "--", SHAPE_PIN, cwd=project)
    commit_in(project, "the shape pin, saved by hand")
    return project


def pinned_paths(root: Path) -> list[str]:
    """The `files:` paths of `root`'s shape pin, as `load_yaml` reads it."""
    return [str(row["path"]) for row in load_yaml(root / SHAPE_PIN)["files"]]


def test_committed_pin_reads_the_commit_load_yaml_reads(hand_saved, tools):
    committed = tools["update-shape"]._committed_pin(hand_saved, SHAPE_PIN)
    assert committed == load_yaml(hand_saved / SHAPE_PIN)["commit"]


def test_pin_at_reads_the_rows_load_yaml_reads(hand_saved, tools):
    doctor_module = tools["shape-doctor"]
    rows = doctor_module.pin_at(doctor_module.Context(hand_saved), "HEAD")
    assert rows == pinned_paths(hand_saved)


def test_pinned_shape_paths_reads_the_rows_load_yaml_reads(hand_saved,
                                                           tools):
    blob = git("rev-parse", f"HEAD:{SHAPE_PIN}", cwd=hand_saved).stdout
    rows = tools["adopt-project"]._pinned_shape_paths(hand_saved,
                                                      blob.strip())
    assert rows == pinned_paths(hand_saved)


def test_pin_values_in_reads_the_leg_pin_load_yaml_reads(project):
    """As `bump-leg.py` hands it the text of a leg pin it is to rewrite."""
    pin = project / SPEC_PIN
    pin.write_bytes(MARK + COMMENT + pin.read_bytes())
    read = load_yaml(pin)
    assert shape_materialize.pin_values_in(pin.read_text(encoding="utf-8")) \
        == (read["commit"], read["digests"]["tree_sha256"])


def test_the_doctor_puts_back_a_hand_saved_pin_from_head_after_a_re_pin(
        standard, hand_saved, tmp_path):
    """THE REGRESSION ROW. `update-shape.py apply` re-pins the hand-saved
    pin onto a newer standard, keeping the mark and the comment, and the
    validators read it. The working pin is then broken. Its NEXT puts back
    HEAD's pin, the one every validator reads; with the mark taken off in
    `load_yaml` alone it was `checkout '<the hand-saved commit>~1'`: the
    pin from before the hand-save, naming the commit the re-pin moved it
    off."""
    moved = tmp_path / "moved" / "openRepoShape"
    moved.parent.mkdir()
    git("clone", "-q", str(standard), str(moved), cwd=tmp_path)
    target = moved_on(moved, "c2", UPSTREAM_TARGET)
    apply_on(moved, hand_saved, target, "shape/re-pin")
    pin = hand_saved / SHAPE_PIN
    pin.write_bytes(pin.read_bytes() + b"files: [\n")
    row = rows_of(doctor(moved, hand_saved, "--json"))["shape-currency"]
    assert row["detail"]["restore"] == "uncommitted", row["detail"]
    assert f"checkout HEAD -- {SHAPE_PIN}" in row["next"], row["next"]
