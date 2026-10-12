# SPDX-License-Identifier: Apache-2.0
"""A pin rewrite keeps each line's own layout and is read back (#323).

`update-shape.py`'s `rewrite_shape_pin` and `scripts/bump-leg.py`'s
`rewrite_pin` found `tree_sha256:` by exactly two leading spaces and wrote
both lines back as `commit: "<sha>"` and `  tree_sha256: "<digest>"`. So a pin
whose `digests:` child is indented four spaces — which `load_yaml` and both
validators accept — was refused as hand-edited, and a trailing `# comment` on
either line was dropped. `rewrite_manifest` dropped the comment too (#224
fixed its indentation, #208). The three now replace only the VALUE and read
what they return back with the reader.

NO SCAFFOLD AND NO GIT HERE. A pin is built by rendering the template the
scaffold renders, with the function the scaffold renders it with, so "a
scaffold-shaped pin" is the scaffold's own text; the rewrites are called
in-process. `test_update_shape.py` and `test_bump_leg.py` carry the same
property end to end, through `apply` and through `bump-leg.py`.
"""

from __future__ import annotations

import importlib.util
import sys
from types import SimpleNamespace

import pytest

from conftest import ORG, PROJECT, REPO

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import (  # noqa: E402
    TREE_DIGEST_DEFINITION, Refusal, parse_yaml,
)
from shape_materialize import SHAPE_REPOSITORY, render  # noqa: E402

OLD_COMMIT, OLD_TREE = "a" * 40, "b" * 64
NEW_COMMIT, NEW_TREE = "c" * 40, "d" * 64
#: Two `files:` rows, before and after, so the shape pin's block is rewritten
#: too and the expected text for it is the scaffold's own rendering.
OLD_ROWS = [("scripts/validate-pins.py", "1" * 64), ("Makefile", "2" * 64)]
NEW_ROWS = [("scripts/validate-pins.py", "3" * 64), ("Makefile", "4" * 64)]

PIN_KINDS = ["assembly shape pin", "family shape pin", "spec pin", "code pin"]


def load_tool(name: str, path):
    """A hyphenated tool as a module, the way `test_update_shape.py` and
    `test_bump_leg.py` load theirs."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tools():
    return SimpleNamespace(
        update_shape=load_tool("pin_layout_update_shape",
                               REPO / "update-shape.py"),
        bump_leg=load_tool("pin_layout_bump_leg",
                           REPO / "scripts" / "bump-leg.py"))


def make_pin(kind: str, commit: str, tree: str, rows) -> str:
    """The pin as the scaffold renders it, from the template it renders."""
    if kind.endswith("shape pin"):
        root = ("assembly-root" if kind.startswith("assembly")
                else "family-root")
        text = (REPO / "templates" / root / "contracts"
                / "shape-pin.yaml").read_text(encoding="utf-8")
        block = "\n".join(f'  - path: {path}\n    sha256: "{digest}"'
                          for path, digest in rows)
        return render(text, {
            "SHAPE_REPOSITORY": SHAPE_REPOSITORY, "SHAPE_COMMIT": commit,
            "DIGEST_DEFINITION": TREE_DIGEST_DEFINITION,
            "SHAPE_TREE_SHA256": tree, "SHAPE_FILES": block}, "shape-pin.yaml")
    role = kind.split()[0]
    upper = role.upper()
    text = (REPO / "templates" / "assembly-root" / "contracts"
            / f"{role}-pin.yaml").read_text(encoding="utf-8")
    return render(text, {
        f"{upper}_REPOSITORY": f"{ORG}/{PROJECT}-{role}",
        f"{upper}_PATH": role, f"{upper}_COMMIT": commit,
        f"{upper}_TREE_SHA256": tree,
        "DIGEST_DEFINITION": TREE_DIGEST_DEFINITION}, f"{role}-pin.yaml")


def rewrite(tools, kind: str, text: str, commit: str, tree: str,
            rows=NEW_ROWS) -> str:
    """The function that rewrites this kind of pin, called as its tool does."""
    if kind.endswith("shape pin"):
        return tools.update_shape.rewrite_shape_pin(
            text, commit, tree,
            [tools.update_shape.Row(path, digest) for path, digest in rows])
    return tools.bump_leg.rewrite_pin(text, commit, tree)


def refusal_code(kind: str) -> str:
    return ("update-pin-unrecognised" if kind.endswith("shape pin")
            else "bump-leg-pin-unrecognised")


def read_back(text: str) -> tuple:
    """What the validators read out of a pin: `commit` and
    `digests.tree_sha256`, through the same reader."""
    pin = parse_yaml(text)
    return pin["commit"], pin["digests"]["tree_sha256"]


# --- the layouts a pin may be written in, as text transformations ---------
#
# Each takes a pin's text and returns it laid out another way, and each is
# applied to the text before AND to the text the rewrite must produce, so the
# expected result is the scaffold's rendering for the target in that layout:
# exactly the two values moved, whatever the layout.

def is_commit_line(line: str) -> bool:
    return line.startswith("commit:")


def is_tree_line(line: str) -> bool:
    return line.startswith(" ") and line.lstrip().startswith("tree_sha256:")


def indent_digests_child(width: int):
    def apply(text: str) -> str:
        assert "\n  tree_sha256:" in text, "fixture: the scaffold's layout"
        return text.replace("\n  tree_sha256:",
                            "\n" + " " * width + "tree_sha256:", 1)
    return apply


def comment_both_lines(comment: str):
    def apply(text: str) -> str:
        return "\n".join(line + comment
                         if is_commit_line(line) or is_tree_line(line)
                         else line for line in text.split("\n"))
    return apply


def space_after_colons(spaces: str):
    def apply(text: str) -> str:
        return "\n".join(
            line.replace(":", ":" + spaces, 1) if is_commit_line(line)
            or is_tree_line(line) else line for line in text.split("\n"))
    return apply


def both(first, second):
    return lambda text: second(first(text))


LAYOUTS = {
    "digests child at 4": indent_digests_child(4),
    "digests child at 3": indent_digests_child(3),
    "digests child at 1": indent_digests_child(1),
    "digests child at 8": indent_digests_child(8),
    "comment after two spaces": comment_both_lines("  # the cut we reviewed"),
    "comment after one space": comment_both_lines(" # reviewed"),
    "comment after a tab": comment_both_lines("\t# reviewed"),
    "comment holding quotes and a hash":
        comment_both_lines('  # a "quoted" word, then # another'),
    "comment with nothing in it": comment_both_lines(" #"),
    "values aligned after wide spacing": space_after_colons("    "),
    "digests child at 4 and a comment": both(
        indent_digests_child(4), comment_both_lines("  # recomputed by hand")),
}


# --- a scaffold-shaped pin is rewritten as it always was -------------------

@pytest.mark.parametrize("kind", PIN_KINDS)
def test_a_scaffold_shaped_pin_is_rewritten_to_what_the_scaffold_renders(
        tools, kind):
    """UNCHANGED FOR THE LAYOUT EVERY PROJECT HAS. The expectation is the
    scaffold's own rendering of the same template for the target values, so
    the rewrite must be byte for byte what a fresh scaffold would have
    written. This test passes on the code before #323 as well: that is the
    point of it."""
    before = make_pin(kind, OLD_COMMIT, OLD_TREE, OLD_ROWS)
    expected = make_pin(kind, NEW_COMMIT, NEW_TREE, NEW_ROWS)
    assert before != expected

    assert rewrite(tools, kind, before, NEW_COMMIT, NEW_TREE) == expected


# --- another layout the reader accepts takes the update --------------------

@pytest.mark.parametrize("layout", LAYOUTS)
@pytest.mark.parametrize("kind", PIN_KINDS)
def test_a_pin_in_any_layout_moves_its_two_values_and_nothing_else(
        tools, kind, layout):
    """THE ISSUE'S TWO SYMPTOMS, and the cases around them. A `digests:`
    child at any depth the reader accepts was refused (`0 tree line(s)`); a
    comment, and the spacing in front of a value, were rewritten away. The
    result is the scaffold's rendering of the target values in the same
    layout, and it is read back through the reader to prove the validators
    would see the target."""
    lay = LAYOUTS[layout]
    before = lay(make_pin(kind, OLD_COMMIT, OLD_TREE, OLD_ROWS))
    expected = lay(make_pin(kind, NEW_COMMIT, NEW_TREE, NEW_ROWS))
    assert read_back(before) == (OLD_COMMIT, OLD_TREE), (
        "fixture: the reader accepts the layout")

    new = rewrite(tools, kind, before, NEW_COMMIT, NEW_TREE)

    assert new == expected
    assert read_back(new) == (NEW_COMMIT, NEW_TREE)


@pytest.mark.parametrize("layout", LAYOUTS)
@pytest.mark.parametrize("kind", PIN_KINDS)
def test_a_pin_already_at_the_target_is_returned_as_it_stands(
        tools, kind, layout):
    """`bump-leg.py` says `nothing to do` when the pin it would write is the
    pin it has. A commented pin, or one indented its own way, used to differ
    from its own rewrite (the comment dropped, or a refusal), so a bump that
    had already landed was not recognised as having landed."""
    before = LAYOUTS[layout](make_pin(kind, OLD_COMMIT, OLD_TREE, OLD_ROWS))

    assert rewrite(tools, kind, before, OLD_COMMIT, OLD_TREE,
                   OLD_ROWS) == before


def test_the_new_value_is_double_quoted_whatever_the_old_one_was(tools):
    """Only the VALUE moves, and the scaffold writes it double-quoted. A
    single-quoted or plain value is replaced by the quoted one, and its
    comment stays."""
    before = make_pin("spec pin", OLD_COMMIT, OLD_TREE, OLD_ROWS)
    before = before.replace(f'commit: "{OLD_COMMIT}"',
                            f"commit: '{OLD_COMMIT}'  # single")
    before = before.replace(f'tree_sha256: "{OLD_TREE}"',
                            f"tree_sha256: {OLD_TREE} # plain")

    new = tools.bump_leg.rewrite_pin(before, NEW_COMMIT, NEW_TREE)

    assert f'commit: "{NEW_COMMIT}"  # single\n' in new
    assert f'  tree_sha256: "{NEW_TREE}" # plain\n' in new
    assert read_back(new) == (NEW_COMMIT, NEW_TREE)


# --- what a line rewrite cannot carry is refused, as this tool's fault -----

def fold_onto_next_line(text: str, key: str) -> str:
    """`key`'s value moved to the line below it, as a folded scalar: it reads,
    and validates, and the one thing a line rewrite cannot move."""
    lines = text.split("\n")
    for index, line in enumerate(lines):
        if line.lstrip().startswith(key + ":"):
            head, value = line.split(":", 1)
            pad = " " * (len(head) - len(head.lstrip()) + 2)
            lines[index:index + 1] = [f"{head}: >-", pad + value.strip('" ')]
            break
    return "\n".join(lines)


@pytest.mark.parametrize("key", ["commit", "tree_sha256"])
@pytest.mark.parametrize("kind", PIN_KINDS)
def test_a_layout_the_rewrite_cannot_carry_is_refused_before_it_is_written(
        tools, kind, key):
    """READ BACK, AS `rewrite_manifest`'s IS. A value on the line below its
    key replaces the key's line and strands the value's, which the reader then
    refuses. That is this tool's failure, said so, and raised before a byte is
    written rather than left to the validators' lockstep remedy."""
    before = make_pin(kind, OLD_COMMIT, OLD_TREE, OLD_ROWS)
    folded = fold_onto_next_line(before, key)
    assert folded != before
    assert read_back(folded) == (OLD_COMMIT, OLD_TREE), (
        "fixture: it reads as it stands")

    with pytest.raises(Refusal) as caught:
        rewrite(tools, kind, folded, NEW_COMMIT, NEW_TREE)

    assert caught.value.code == refusal_code(kind)
    assert "does not read back to the target" in caught.value.detail
    assert "unexpected indentation" in caught.value.detail
    assert "the fault is this tool's line rewrite" in caught.value.remediation
    assert "recomputes the digest" in caught.value.remediation


@pytest.mark.parametrize("kind", PIN_KINDS)
def test_a_pin_that_did_not_read_before_is_left_to_its_validators(
        tools, kind):
    """THE READ-BACK BLAMES THIS TOOL ONLY WHEN THE FAULT IS ITS OWN. A pin
    the reader refused before a byte was rewritten was red before the command
    ran; refusing it as the rewrite's fault would blame the tool for the
    project's own line. It is rewritten as before."""
    before = make_pin(kind, OLD_COMMIT, OLD_TREE, OLD_ROWS)
    broken = before.replace("\nrevision_kind: commit\n",
                            "\nrevision_kind: commit\n\tstray: tab\n", 1)
    assert broken != before, "fixture: the line to break was found"

    new = rewrite(tools, kind, broken, NEW_COMMIT, NEW_TREE)

    assert f'commit: "{NEW_COMMIT}"' in new
    assert "\tstray: tab" in new


def assert_refused_for_its_count(tools, kind: str, text: str, count: int):
    with pytest.raises(Refusal) as caught:
        rewrite(tools, kind, text, NEW_COMMIT, NEW_TREE)
    assert caught.value.code == refusal_code(kind)
    assert f"has {count} `" in caught.value.detail
    assert "where exactly one was expected" in caught.value.detail


@pytest.mark.parametrize("kind", PIN_KINDS)
def test_one_of_each_line_is_still_required(tools, kind):
    """UNCHANGED, and it passes on the code before #323 too. Found by their
    spelling and counted: two `tree_sha256:` lines, a `tree_sha256:` at
    column 0 (not a `digests:` child) and no `commit:` line are refused by
    name, and nothing is written."""
    before = make_pin(kind, OLD_COMMIT, OLD_TREE, OLD_ROWS)
    twice = before.replace(f'  tree_sha256: "{OLD_TREE}"\n',
                           f'  tree_sha256: "{OLD_TREE}"\n'
                           f'  tree_sha256: "{OLD_TREE}"\n', 1)
    flush = before.replace(f'  tree_sha256: "{OLD_TREE}"',
                           f'tree_sha256: "{OLD_TREE}"', 1)
    no_commit = before.replace(f'commit: "{OLD_COMMIT}"',
                               f'last: "{OLD_COMMIT}"', 1)
    for broken, count in [(twice, 2), (flush, 0), (no_commit, 0)]:
        assert broken != before
        assert_refused_for_its_count(tools, kind, broken, count)


@pytest.mark.parametrize("kind", PIN_KINDS)
def test_a_second_tree_line_is_counted_at_whatever_depth_it_has(tools, kind):
    """The line is found by its spelling at ANY indentation now, so a second
    one at another depth is still two. Found at two spaces only, it would
    have been one, and the other would have been rewritten around."""
    before = make_pin(kind, OLD_COMMIT, OLD_TREE, OLD_ROWS)
    deeper = before.replace(f'  tree_sha256: "{OLD_TREE}"\n',
                            f'  tree_sha256: "{OLD_TREE}"\n'
                            f'    tree_sha256: "{OLD_TREE}"\n', 1)
    assert deeper != before
    assert_refused_for_its_count(tools, kind, deeper, 2)


# --- the manifest's `shape:` block keeps its comments too ------------------

MANIFEST = """schema_version: 1
kind: project-manifest

legs:
  - role: spec
    commit: "{member}"

shape:
  repository: opensoft/openRepoShape  # upstream
  revision_kind: commit
  commit: "{commit}"  # the cut we reviewed
  digest_algorithm: sha256
  digests:
    tree_sha256: "{tree}"   # recomputed by hand

visibility: private
"""


@pytest.mark.parametrize("kind_name", ["PROJECT_KIND", "FAMILY_KIND"])
def test_the_manifest_rewrite_keeps_a_comment_on_each_of_its_two_lines(
        tools, kind_name):
    """`rewrite_manifest` wrote `commit: "<sha>"` and `tree_sha256: "<digest>"`
    back and the comments with them (#323). Only the two values move now, and
    the member row's own `commit:` above the block, spelled the same way, is
    left alone."""
    member = "e" * 40
    text = MANIFEST.format(member=member, commit=OLD_COMMIT, tree=OLD_TREE)

    new = tools.update_shape.rewrite_manifest(
        text, NEW_COMMIT, NEW_TREE, getattr(tools.update_shape, kind_name))

    assert new == MANIFEST.format(member=member, commit=NEW_COMMIT,
                                  tree=NEW_TREE)
    shape = parse_yaml(new)["shape"]
    assert (shape["commit"], shape["digests"]["tree_sha256"]) == (
        NEW_COMMIT, NEW_TREE)
