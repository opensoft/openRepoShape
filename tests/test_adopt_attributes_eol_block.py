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

Each copy is named by the path git tracks: one written through a symlinked
directory the root keeps, `.github -> ci`, is named where the link leads,
then by its pinned path (#807), and
`tests/test_adopt_eol_block_through_links.py` adopts such a source end to
end.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
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
#: The shape's workflow, and where git tracks it when the root keeps
#: `.github -> ci`, or a chain of links that ends there (#807).
WORKFLOW = ".github/workflows/validate.yml"
TRACKED_WORKFLOW = "ci/workflows/validate.yml"
THROUGH_LINKS = [pytest.param({".github": "ci"}, id="a-link"),
                 pytest.param({".github": "l1", "l1": "ci"}, id="a-chain")]

#: A symlink made ON THE DISK, as the other symlink tests of the adoption
#: suites skip one on Windows: there a runner may make one only in Developer
#: Mode or elevated, and one whose target is spelled `config/attributes`
#: leads nowhere, so the materializer took the path for free and wrote
#: through the link (#471's probe 2).
needs_disk_symlinks = pytest.mark.skipif(
    sys.platform == "win32",
    reason="a symlink needs a privilege Windows does not grant by default")


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


def test_each_copy_is_named_where_git_tracks_it():
    """A copy written through `.github -> ci` is tracked at `ci/`, where a
    line naming only the link's spelling governs nothing; that spelling
    follows, and governs the copy once the link is replaced with what it
    points at (#807)."""
    pinned = ["Makefile", WORKFLOW, f"{COLLISION_DIR}/{ATTRIBUTES}"]
    tracked = {WORKFLOW: TRACKED_WORKFLOW,
               f"{COLLISION_DIR}/{ATTRIBUTES}": ATTRIBUTES}
    assert eol_block_paths(pinned, COLLISION_DIR, tracked) == [
        "Makefile", TRACKED_WORKFLOW, WORKFLOW]


@pytest.mark.parametrize("tracked", [
    {}, {WORKFLOW: None}, {WORKFLOW: "my ci/workflows/validate.yml"}],
    ids=["not-mapped", "led-nowhere", "no-literal-name"])
def test_a_copy_tracked_nowhere_nameable_keeps_its_pinned_path(tracked):
    """Where the links lead out of the root or cannot be followed, or to a
    name no line can spell, the pinned line alone is today's."""
    assert eol_block_paths([WORKFLOW], COLLISION_DIR, tracked) == [WORKFLOW]


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


def test_the_last_block_is_extended_when_the_source_held_the_head_already():
    """A source that already held a copy of the head line gets the
    adoption's block after it, so the LAST head is the block: a new line
    goes there, after the source's later `* text eol=crlf`, which would
    otherwise win over it (#471's review, NIT-1)."""
    earlier = (f"{EOL_BLOCK_HEAD}\n/Makefile text eol=lf\n".encode(UTF8)
               + b"* text eol=crlf\n")
    data = earlier + COPIES_BLOCK
    assert extend_eol_block(data, ["AGENTS-x.md"]) == (
        data + b"/AGENTS-x.md text eol=lf\n")


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


@needs_disk_symlinks
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


@needs_disk_symlinks
@pytest.mark.parametrize("links", THROUGH_LINKS)
def test_a_copy_written_through_a_link_is_named_where_git_tracks_it(tmp_path,
                                                                  links):
    """The root keeps `.github -> ci`, or a chain to it: the shape writes its
    workflow through the link, git tracks it at `ci/workflows/validate.yml`,
    and that is its line, before the one for the path it was written at. The
    pin's row keeps that path, which a clone opens through the same link
    (#807)."""
    target = target_holding(tmp_path, {ATTRIBUTES: OWN,
                                       "ci/workflows/ci.yml": b"on: [push]\n"})
    for link, to in links.items():
        try:
            os.symlink(to, target / link)
        except (NotImplementedError, OSError) as exc:
            pytest.skip(f"this platform cannot create a symlink here: {exc}")
    result = materialize_assembly_root(REPO, target, template_values(),
                                       collision_dir=COLLISION_DIR)
    assert WORKFLOW in result.shape_files
    assert (target / TRACKED_WORKFLOW).is_file()
    named = eol_block_paths(result.shape_files, COLLISION_DIR,
                            {WORKFLOW: TRACKED_WORKFLOW})
    assert result.eol_block == named
    at = named.index(TRACKED_WORKFLOW)
    assert named[at + 1] == WORKFLOW
    assert (target / ATTRIBUTES).read_bytes() == with_eol_block(OWN, named)


def index_only_link(repo: Path, link: str, target: str) -> None:
    """`link -> target` in git's INDEX only, mode 120000 with the target as
    its blob, as a tree records it: no symlink on the disk, so no privilege
    is needed on any platform."""
    blob = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                          cwd=str(repo), input=target.encode(UTF8),
                          capture_output=True, check=True)
    git("update-index", "--add", "--cacheinfo",
        f"120000,{blob.stdout.decode(UTF8).strip()},{link}", cwd=repo)


def test_a_link_checked_out_as_a_plain_file_is_not_written_through(tmp_path):
    """Git for Windows' default `core.symlinks=false` checks a tracked
    symlink out as a PLAIN FILE holding the path it leads to, so the disk
    says "not a link" there. The append used to land in the link itself:
    the split kept mode 120000 over the old target followed by the block,
    and the verification called the source's file lost after both legs were
    pushed (#471's review, MUST-1). Git's index says what the file is, and
    this test reads it the same way on every platform."""
    target = target_holding(tmp_path, {"config/attributes": OWN,
                                       "README.md": b"# Thing\n"})
    git("init", "-q", "-b", "main", ".", cwd=target)
    git("add", "-A", "--", ".", cwd=target)
    index_only_link(target, ATTRIBUTES, "config/attributes")
    git("commit", "-qm", "The source", cwd=target)
    git("-c", "core.symlinks=false", "checkout", "--", ATTRIBUTES, cwd=target)
    assert not (target / ATTRIBUTES).is_symlink()
    assert (target / ATTRIBUTES).read_bytes() == b"config/attributes"
    staged = git("ls-files", "--stage", "--", ATTRIBUTES, cwd=target).stdout
    assert staged.startswith("120000 "), staged
    result = materialize_assembly_root(REPO, target, template_values(),
                                       collision_dir=COLLISION_DIR)
    assert (ATTRIBUTES, f"{COLLISION_DIR}/{ATTRIBUTES}") in result.collisions
    assert result.eol_block == []
    assert (target / ATTRIBUTES).read_bytes() == b"config/attributes"
    assert (target / "config" / "attributes").read_bytes() == OWN
    assert git("ls-files", "--stage", "--", ATTRIBUTES,
               cwd=target).stdout == staged


# ---------------------------------------------------------------------------
# What the human reads: the follow-up and the split commit's message
# ---------------------------------------------------------------------------


def test_the_follow_up_says_what_the_block_protects():
    said = collision_follow_up(ATTRIBUTES, f"{COLLISION_DIR}/{ATTRIBUTES}")
    assert not said.startswith("merge "), said
    assert f"`{EOL_BLOCK_HEAD}`" in said
    assert "shape-copy-drift" in said and "Windows" in said
    assert "None of the source's own lines is changed" in said
    # The copy is merged only on that condition and removed only after it,
    # and the row the removal leaves is said in #512's words for every other
    # pinned copy (#502): it returned before them, and said nothing.
    assert said.endswith(
        f"Merge the rest of {COLLISION_DIR}/{ATTRIBUTES} into {ATTRIBUTES} "
        "only if the whole project should check out with LF, and only then "
        f"remove {COLLISION_DIR}/{ATTRIBUTES}: `update-shape.py check` "
        "reports its pin row `merged-away`, and `apply` drops the row"), said
    # A link gets the other follow-up, below.
    assert "symlink" not in said
    # Every other collision keeps its own wording.
    assert collision_follow_up("Makefile", "shape/Makefile").startswith(
        "merge shape/Makefile into Makefile")


def test_the_follow_up_for_a_linked_attributes_file_lists_the_lines_it_needs(
        tmp_path):
    """A `.gitattributes` that is a symlink gets no block, and git reads
    no `.gitattributes` that is one, so the follow-up says that nothing was
    appended, gives the remedy that works, and lists the exact lines: the
    ones a regular file would have had appended. It used to describe a
    block that was never written and send the person to add its lines
    where the link leads, which git never reads (#471's review, SHOULD-2)."""
    target = target_holding(tmp_path, {ATTRIBUTES: OWN, "Makefile": b"all:\n"})
    result = materialize_assembly_root(REPO, target, template_values(),
                                       collision_dir=COLLISION_DIR)
    needed = eol_block(eol_block_paths(result.shape_files,
                                       COLLISION_DIR)).splitlines()
    beside = dict(result.collisions)
    said = collision_follow_up(ATTRIBUTES, beside[ATTRIBUTES], beside,
                               attributes_link=True)
    assert said.startswith(f"{ATTRIBUTES} is a symlink, so the split "
                           "appended nothing to it"), said
    assert (f"Git follows no {ATTRIBUTES} that is a symlink: a checkout "
            "reads only the link's own text, the path it leads to, and a "
            "path names no attribute, so no line-ending rule reaches the "
            "pinned copies outside it") in said
    assert f"replace the link with a regular {ATTRIBUTES}" in said
    assert ", ".join(f"`{line}`" for line in needed) in said
    assert needed[0] == EOL_BLOCK_HEAD
    assert "`/scripts/validate-pins.py text eol=lf`" in said
    # The Makefile went beside the source's, under `shape/`.
    assert "/Makefile text eol=lf" not in said
    assert "keep the block" not in said
    # It never sends anyone to merge or remove the shape's copy, which stays
    # pinned, so it says nothing of a row that removal would leave.
    assert "merged-away" not in said and "remove shape/" not in said


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


def commit_files(repo: Path, files: dict, message: str,
                 links: dict | None = None) -> str:
    for name, body in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_bytes(body)
    git("add", "-A", "--", ".", cwd=repo)
    for link, target in (links or {}).items():
        index_only_link(repo, link, target)
    git("-c", "user.name=T", "-c", "user.email=t@invalid.example", "commit",
        "-qm", message, cwd=repo)
    return git("rev-parse", "HEAD", cwd=repo).stdout.strip()


def accounted(adopter, tmp_path: Path, attributes: bytes,
              pin_path: str = SHAPE_PIN, links: dict | None = None,
              workflow: str | None = None) -> tuple:
    """A source commit holding `OWN`, and a split commit over it whose root
    `.gitattributes` is `attributes`: `(lines counted, findings, counts,
    the source's oid, after)` from the verification's own steps. `links`
    go into the split's tree only (`index_only_link`). With `workflow`, the
    pin names `WORKFLOW` too, and the split holds it at `workflow`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=repo)
    source = commit_files(repo, {ATTRIBUTES: OWN, "README.md": b"# Thing\n"},
                          "The source")
    copies = {workflow: b"on: [push]\n"} if workflow else {}
    split = commit_files(repo, {
        ATTRIBUTES: attributes,
        pin_path: pin_of([*PINNED, WORKFLOW] if workflow else PINNED),
        f"{COLLISION_DIR}/{ATTRIBUTES}": (TEMPLATE / ATTRIBUTES).read_bytes(),
        "Makefile": b"all:\n", "scripts/validate-pins.py": b"print()\n",
        **copies}, "The split", links=links)
    before = {path: oid for path, _, oid, _ in adopter._tree_of(repo, source)}
    tree = adopter._tree_of(repo, split)
    after: dict = {}
    assert adopter._land_the_root_tree(after, tree, before, {}) == []
    lines = adopter._land_the_eol_block(repo, split, tree, before, after)
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


def test_the_pin_is_read_through_a_link_the_root_kept(adopter, tmp_path):
    """`contracts -> meta` kept in the root: the materializer wrote the pin
    through the link, to `meta/shape-pin.yaml`, and `_shape_file_findings`
    finds it by its pinned name. A lookup among the tree's plain files found
    none, so the appended file was `adopt-lost` where main verified the
    same source (#471's review, SHOULD-3)."""
    lines, findings, _, oid, after = accounted(
        adopter, tmp_path, with_eol_block(OWN, ROOT_COPIES),
        pin_path="meta/shape-pin.yaml", links={"contracts": "meta"})
    assert (lines, findings) == (2, [])
    assert after[ATTRIBUTES] == [f"root:{oid}"]


@pytest.mark.parametrize("links", THROUGH_LINKS)
def test_a_copy_written_through_a_link_is_counted_where_git_tracks_it(
        adopter, tmp_path, links):
    """The split keeps `.github -> ci`, or a chain to it, and the workflow
    at `ci/`: the block the materializer wrote names it there, then by its
    pinned path, and the verification reads the same path through the
    split's links (#807)."""
    lines, findings, _, oid, after = accounted(
        adopter, tmp_path, with_eol_block(OWN, [*ROOT_COPIES,
                                                TRACKED_WORKFLOW, WORKFLOW]),
        links=links, workflow=TRACKED_WORKFLOW)
    assert (lines, findings) == (4, [])
    assert after[ATTRIBUTES] == [f"root:{oid}"]


def test_a_copy_whose_link_leads_out_of_the_split_keeps_its_pinned_path(
        adopter, tmp_path):
    """A link out of the split tracks nothing there: the line is the one the
    pin names, as before, and `_shape_file_findings` reports the copy."""
    lines, findings, _, _, _ = accounted(
        adopter, tmp_path, with_eol_block(OWN, [*ROOT_COPIES, WORKFLOW]),
        links={".github": "/etc"}, workflow=TRACKED_WORKFLOW)
    assert (lines, findings) == (3, [])


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
