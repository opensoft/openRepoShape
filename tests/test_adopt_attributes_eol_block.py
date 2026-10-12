# SPDX-License-Identifier: Apache-2.0
"""The shape's line endings, appended to a source's own `.gitattributes` (#471).

Adoption's first run on a Windows runner failed one ordinary case: a source
that tracks its own root `.gitattributes`. The shape's copy, `* text=auto
eol=lf`, is written beside it under `shape/`, and git reads attributes for a
path only from the `.gitattributes` files of its own directory and those above
it, so the copy governs `shape/` alone. Every pinned copy at the root answered
to the source's file, a checkout that writes CRLF (Git for Windows' default)
wrote them with CRLF, and `validate-pins.py`, which digests the bytes on disk,
reported shape-copy-drift on each.

Brett Heap ruled at 2026-10-12T22:48Z that the split APPENDS one marked block
to the source's own file: a comment line, then `/<path> text eol=lf` for each
pinned copy outside `shape/`. This module holds the parts of that to their
contract on hand-made directories and repositories: the block's text, the
materializer's append, the follow-up's words, the split commit's message, and
the verification that counts the file as the source's bytes followed by
exactly that block and nothing else. It needs no `git filter-repo` and no
network, so every CI job runs it. `tests/test_adopt_ignored_shape_files.py`
adopts such a source end to end and clones it with a checkout that writes
CRLF; `tests/test_update_shape_add.py` extends the block with `--add`.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

from conftest import ADOPT, REPO, git

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import Refusal  # noqa: E402
from shape_materialize import (  # noqa: E402
    ATTRIBUTES, EOL_BLOCK_HEAD, PLACEHOLDER_RE, collision_follow_up,
    eol_block, eol_block_paths, eol_line, extend_eol_block,
    materialize_assembly_root, with_eol_block,
)

UTF8 = "utf-8"
COLLISION_DIR = "shape"
#: A source's own attributes, as a repository commonly has them.
OWN = b"* text=auto\n*.png binary\n"
#: Three pinned copies at the root, in a pin's order.
COPIES = ["scripts/validate-pins.py", "Makefile",
          ".github/workflows/validate.yml"]
#: The block's lines for `COPIES`, spelled out rather than computed.
COPIES_BLOCK = (f"{EOL_BLOCK_HEAD}\n"
                "/scripts/validate-pins.py text eol=lf\n"
                "/Makefile text eol=lf\n"
                "/.github/workflows/validate.yml text eol=lf\n").encode(UTF8)
SHAPE_PIN = "contracts/shape-pin.yaml"
TEMPLATE = REPO / "templates" / "assembly-root"


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_attributes_eol_block",
                                                  ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# The block's text
# ---------------------------------------------------------------------------


def test_the_block_is_its_head_and_one_anchored_line_per_copy():
    """A comment naming openRepoShape and #471, then each copy as a literal
    path anchored at the root, in the order given."""
    assert "openRepoShape" in EOL_BLOCK_HEAD and "#471" in EOL_BLOCK_HEAD
    assert EOL_BLOCK_HEAD.startswith("# ")
    assert eol_block(COPIES).encode(UTF8) == COPIES_BLOCK


def test_the_sources_bytes_come_first_and_are_kept():
    appended = with_eol_block(OWN, COPIES)
    assert appended == OWN + COPIES_BLOCK


@pytest.mark.parametrize(("existing", "expected"), [
    (b"* text=auto", b"* text=auto\n" + COPIES_BLOCK),
    (b"", COPIES_BLOCK),
    (b"* text=auto\r\n", b"* text=auto\r\n" + COPIES_BLOCK),
], ids=["no-final-newline", "empty", "crlf-lines-kept"])
def test_a_final_newline_is_the_only_byte_added_outside_the_block(existing,
                                                                  expected):
    """A file that does not end in a newline would have the head read as part
    of its last line, so it gets one; an empty one gets nothing; a CRLF one
    keeps its own lines exactly."""
    assert with_eol_block(existing, COPIES) == expected


def test_copies_under_shape_are_left_to_the_shapes_own_file():
    """`shape/.gitattributes` governs `shape/`, so the block names only what
    is outside it, keeping the pin's order."""
    pinned = ["shape/.gitattributes", "scripts/bootstrap.py", "shape/Makefile",
              "Makefile", "shape-notes/x.md"]
    assert eol_block_paths(pinned, COLLISION_DIR) == [
        "scripts/bootstrap.py", "Makefile", "shape-notes/x.md"]


@pytest.mark.parametrize("path", ["notes and more.md", "scripts/*.py",
                                  "docs/[a].md", "dir\\file", "", "/Makefile",
                                  "a//b", "!x"])
def test_a_path_git_would_read_as_a_pattern_is_refused(path):
    """Each line must name ONE file: a space ends a pattern, a glob character
    matches others, a backslash escapes. No pinned copy is spelled so, so one
    that is would be the standard's defect, and is refused rather than
    written."""
    with pytest.raises(Refusal) as caught:
        eol_line(path)
    assert caught.value.code == "materialize-attributes-path"


# ---------------------------------------------------------------------------
# Extending it (`update-shape.py apply --add`)
# ---------------------------------------------------------------------------


def test_a_new_copy_joins_the_block_before_the_lines_after_it():
    """The new line goes after the block's last line, so a line a human
    wrote after the block still comes last; a copy already named is not
    named twice."""
    after = b"*.jpg binary\n"
    extended = extend_eol_block(OWN + COPIES_BLOCK + after,
                                ["AGENTS-x.md", "Makefile"])
    assert extended == (OWN + COPIES_BLOCK + b"/AGENTS-x.md text eol=lf\n"
                        + after)


def test_extending_with_copies_already_named_changes_nothing():
    data = OWN + COPIES_BLOCK
    assert extend_eol_block(data, COPIES) == data


def test_a_file_with_no_block_is_not_extended():
    """A scaffolded root's `.gitattributes` is the shape's own, and one
    adopted before #471 has no block: neither is written."""
    assert extend_eol_block(OWN, ["AGENTS-x.md"]) is None
    assert extend_eol_block(b"", ["AGENTS-x.md"]) is None


def test_a_block_that_ends_the_file_with_no_newline_is_extended_cleanly():
    data = OWN + COPIES_BLOCK.rstrip(b"\n")
    assert extend_eol_block(data, ["AGENTS-x.md", "AGENTS-x.md"]) == (
        OWN + COPIES_BLOCK + b"/AGENTS-x.md text eol=lf\n")


def test_a_crlf_checkout_of_the_file_is_extended_in_its_own_endings():
    """On Windows the source's rules govern `.gitattributes` itself, so a
    checkout can hold it with CRLF: the block is still found, and the new
    line ends as the block's lines do."""
    crlf = (OWN + COPIES_BLOCK).replace(b"\n", b"\r\n")
    assert extend_eol_block(crlf, ["AGENTS-x.md"]) == (
        crlf + b"/AGENTS-x.md text eol=lf\r\n")


# ---------------------------------------------------------------------------
# The materializer appends it, where and only where the shape's copy collided
# ---------------------------------------------------------------------------


def template_values() -> dict:
    return {name[2:-2]: "x" for path in TEMPLATE.rglob("*") if path.is_file()
            for name in PLACEHOLDER_RE.findall(path.read_text(UTF8))}


def target_holding(tmp_path: Path, files: dict) -> Path:
    target = tmp_path / "assembly"
    for name, body in files.items():
        (target / name).parent.mkdir(parents=True, exist_ok=True)
        (target / name).write_bytes(body)
    return target


def test_a_source_attributes_file_gets_the_block_for_the_copies_outside_shape(
        tmp_path):
    target = target_holding(tmp_path, {ATTRIBUTES: OWN,
                                       "README.md": b"# Thing\n"})
    result = materialize_assembly_root(REPO, target, template_values(),
                                       collision_dir=COLLISION_DIR)
    assert (ATTRIBUTES, f"{COLLISION_DIR}/{ATTRIBUTES}") in result.collisions
    outside = eol_block_paths(result.shape_files, COLLISION_DIR)
    assert result.eol_block == outside
    assert {"Makefile", "AGENTS-shape.md", "scripts/bootstrap.py",
            ".github/workflows/validate.yml"} <= set(outside)
    assert f"{COLLISION_DIR}/{ATTRIBUTES}" in result.shape_files
    assert (target / ATTRIBUTES).read_bytes() == with_eol_block(OWN, outside)
    # The shape's own copy is still the template's, beside the source's.
    assert (target / COLLISION_DIR / ATTRIBUTES).read_bytes() == \
        (TEMPLATE / ATTRIBUTES).read_bytes()
    # The source's file is in neither list of what the shape wrote.
    assert ATTRIBUTES not in result.written
    assert ATTRIBUTES not in result.shape_files


def test_with_no_attributes_of_its_own_nothing_is_appended(tmp_path):
    """Today's behaviour, unchanged: the shape's own file is the root's."""
    target = target_holding(tmp_path, {"README.md": b"# Thing\n"})
    result = materialize_assembly_root(REPO, target, template_values(),
                                       collision_dir=COLLISION_DIR)
    assert result.eol_block == []
    assert (target / ATTRIBUTES).read_bytes() == \
        (TEMPLATE / ATTRIBUTES).read_bytes()


def test_an_attributes_symlink_is_not_written_through(tmp_path):
    """What a link leads to may be another of the source's files, and git
    reads no `.gitattributes` through a link anyway: it is left alone."""
    target = target_holding(tmp_path, {"config/attributes": OWN})
    try:
        os.symlink("config/attributes", target / ATTRIBUTES)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"this platform cannot create a symlink here: {exc}")
    result = materialize_assembly_root(REPO, target, template_values(),
                                       collision_dir=COLLISION_DIR)
    assert (ATTRIBUTES, f"{COLLISION_DIR}/{ATTRIBUTES}") in result.collisions
    assert result.eol_block == []
    assert (target / "config" / "attributes").read_bytes() == OWN


# ---------------------------------------------------------------------------
# What the human reads: the follow-up and the split commit's message
# ---------------------------------------------------------------------------


def test_the_follow_up_says_what_the_block_protects():
    said = collision_follow_up(ATTRIBUTES, f"{COLLISION_DIR}/{ATTRIBUTES}")
    assert not said.startswith("merge "), said
    assert f"`{EOL_BLOCK_HEAD}`" in said
    assert "shape-copy-drift" in said and "Windows" in said
    assert "None of the source's own lines is changed" in said
    assert "symlink" in said
    # Every other collision keeps its own wording.
    assert collision_follow_up("Makefile", "shape/Makefile").startswith(
        "merge shape/Makefile into Makefile")


def split_message(adopter, appended=()) -> str:
    return adopter._split_message(
        {"assembly": "Northwind", "spec": "Northwind-spec",
         "code": "Northwind-code"},
        {"spec": ["specs/"], "code": ["src/"], "drop": [], "root": [ATTRIBUTES]},
        {"spec": "a" * 40, "code": "b" * 40}, "spec", "code", [],
        [(ATTRIBUTES, f"{COLLISION_DIR}/{ATTRIBUTES}")], appended=appended)


def test_the_split_message_lists_every_line_it_appended(adopter):
    message = split_message(adopter, COPIES)
    assert f"APPENDED TO {ATTRIBUTES}, after this repository's own lines, " \
           "which are unchanged" in message
    for path in COPIES:
        assert f"\n  {eol_line(path)}\n" in message, path
    assert "APPENDED TO" not in split_message(adopter)


# ---------------------------------------------------------------------------
# The verification counts the source's file, and only in that one shape
# ---------------------------------------------------------------------------


def pin_of(paths) -> bytes:
    rows = "".join(f"  - path: {path}\n    sha256: \"{'0' * 64}\"\n"
                   for path in paths)
    return (f"schema_version: 1\nkind: pinned_contract_manifest\nfiles:\n"
            f"{rows}").encode(UTF8)


#: The split's pin: the shape's `.gitattributes` beside the source's, and two
#: copies at the root.
PINNED = [f"{COLLISION_DIR}/{ATTRIBUTES}", "Makefile",
          "scripts/validate-pins.py"]
ROOT_COPIES = ["Makefile", "scripts/validate-pins.py"]


def commit_files(repo: Path, files: dict, message: str) -> str:
    for name, body in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_bytes(body)
    git("add", "-A", "--", ".", cwd=repo)
    git("-c", "user.name=T", "-c", "user.email=t@invalid.example", "commit",
        "-qm", message, cwd=repo)
    return git("rev-parse", "HEAD", cwd=repo).stdout.strip()


def accounted(adopter, tmp_path: Path, attributes: bytes,
              pin_path: str = SHAPE_PIN) -> tuple:
    """A source commit holding `OWN`, and a split commit over it whose root
    `.gitattributes` is `attributes`: `(lines counted, findings, counts,
    the source's oid, after)` from the verification's own steps."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=repo)
    source = commit_files(repo, {ATTRIBUTES: OWN, "README.md": b"# Thing\n"},
                          "The source")
    split = commit_files(repo, {
        ATTRIBUTES: attributes, pin_path: pin_of(PINNED),
        f"{COLLISION_DIR}/{ATTRIBUTES}": (TEMPLATE / ATTRIBUTES).read_bytes(),
        "Makefile": b"all:\n", "scripts/validate-pins.py": b"print()\n"},
        "The split")
    before = {path: oid for path, _, oid, _ in adopter._tree_of(repo, source)}
    tree = adopter._tree_of(repo, split)
    after: dict = {}
    assert adopter._land_the_root_tree(after, tree, before, {}) == []
    lines = adopter._land_the_eol_block(repo, tree, before, after)
    counts, findings = adopter._account_for(before, after, [])
    return lines, findings, counts, before[ATTRIBUTES], after


def test_the_sources_bytes_then_the_block_is_the_source_landed_in_the_root(
        adopter, tmp_path):
    lines, findings, counts, oid, after = accounted(
        adopter, tmp_path, with_eol_block(OWN, ROOT_COPIES))
    assert lines == 2
    assert after[ATTRIBUTES] == [f"root:{oid}"]
    assert findings == []
    assert counts["root"] == 2


def test_the_shapes_pin_is_read_from_shape_when_the_source_kept_its_own(
        adopter, tmp_path):
    """The source's own `contracts/shape-pin.yaml` kept in the root sends the
    shape's to `shape/`, and that one says which copies the block names."""
    lines, findings, _, _, _ = accounted(
        adopter, tmp_path, with_eol_block(OWN, ROOT_COPIES),
        pin_path=f"{COLLISION_DIR}/{SHAPE_PIN}")
    assert (lines, findings) == (2, [])


def test_the_sources_own_bytes_untouched_need_no_exception(adopter, tmp_path):
    """No block (no collision, or a symlink): the blob is the source's, and
    the accounting is the ordinary one."""
    lines, findings, counts, _, _ = accounted(adopter, tmp_path, OWN)
    assert (lines, findings, counts["root"]) == (0, [], 2)


#: Every way the root's file can differ from the source's and the block, and
#: each one leaves the source's bytes in no place: `adopt-lost`.
NOT_THE_BLOCK = [
    pytest.param(with_eol_block(OWN, ROOT_COPIES[:1]), id="a-copy-missing"),
    pytest.param(with_eol_block(OWN, [*ROOT_COPIES, "README.md"]),
                 id="a-line-too-many"),
    pytest.param(with_eol_block(OWN, PINNED), id="a-shape-copy-named"),
    pytest.param(with_eol_block(OWN, ROOT_COPIES) + b"*.jpg binary\n",
                 id="a-line-after-it"),
    pytest.param(with_eol_block(b"* text=auto eol=crlf\n*.png binary\n",
                                ROOT_COPIES), id="a-source-line-changed"),
    pytest.param(eol_block(ROOT_COPIES).encode(UTF8), id="the-source-gone"),
]


@pytest.mark.parametrize("attributes", NOT_THE_BLOCK)
def test_anything_but_exactly_the_block_is_the_source_lost(adopter, tmp_path,
                                                           attributes):
    lines, findings, _, oid, after = accounted(adopter, tmp_path, attributes)
    assert lines == 0
    assert f"root:{oid}" not in after[ATTRIBUTES]
    assert len(findings) == 1, findings
    assert findings[0].startswith(
        f"FINDING adopt-lost: `{ATTRIBUTES}` ({oid[:12]}) is in no leg, not "
        "in the root tree"), findings
