# SPDX-License-Identifier: Apache-2.0
"""The tools' own read and write keep the byte-order mark, and the cut in
front of line 1 takes U+FEFF and nothing else (#1176, from rv1050's NITs 1
and 2 on #1050).

WHAT `tests/test_bom_rewrites.py` HOLDS, AND WHAT IT DOES NOT. Its rows call
the three line rewriters (`rewrite_shape_pin`, `rewrite_manifest`,
`rewrite_pin`) and check what each returns. #933's Direction says more: "the
marked first-key file is written, its first bytes are the mark". A file is
written by a tool, which reads it first, and neither the read nor the write
is in that file's rows:

- `update-shape.py`'s `_repin` reads `contracts/shape-pin.yaml` and the
  manifest as `utf-8` and writes what the two rewriters return, through the
  `Rollback` ledger;
- `scripts/bump-leg.py`'s `_leg_pin_text` reads the leg's pin as `utf-8`,
  `rewrite_pin` rewrites it, and `write_lf` writes it.

`read_text(encoding="utf-8-sig")` in place of `encoding="utf-8"` at any of
the three reads passed `tests/test_bom_rewrites.py` and
`tests/test_bom_reads.py`: a file with one mark was written with none, and a
file with two marks was written with one. Every reader reads both forms, so
nothing read wrong, and the first bytes of the file were not what #933 says
they are. The rows below run each tool's own read and write in process
(`_repin`; `_leg_pin_text`, `rewrite_pin` and `write_lf`, in the order
`bump-leg.py`'s `main` calls them), and then each tool end to end, through
its entry point: `update-shape.py apply` against a local `--upstream`, and
`bump-leg.py`.

ONLY U+FEFF IS CUT, AND ONLY IN FRONT OF LINE 1. The cut is `lstrip` of
`BYTE_ORDER_MARK` in `_marks_off` and in `rewrite_pin`. An `lstrip` that
also takes a space and a line feed passed `tests/test_bom_rewrites.py` and
the files that read a pin: a pin whose line 1 is ` commit: ...` was
written, exit 0, where it is refused as `0 commit line(s)`, as it was before
#1050. The rows below hold the answer the cut as it is gives, so a cut that
is wider, narrower or somewhere else fails one:

- a space or a tab in front of the key, before a mark or after one, and a
  file indented two spaces on every line: refused, in each tool's words;
- another zero-width or format (`Cf`) character as the SECOND character, in
  front of the key: it is not a mark, so it stays, the key is not found and
  the file is refused, unchanged;
- the same characters as the second character of a first line that is a key
  of its own: the reader reads the file, and the tool writes it with that
  character where it was;
- a mark that is the second character of a comment, with or without marks
  in front of it: text, written back where it was.

Every mark is written by this file as bytes (`codecs.BOM_UTF8`), never
typed, and every other character from `chr` of its code point.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest

from conftest import PROJECT, cloned_just_pushed, git
from test_bom_rewrites import (
    FINDERS, MARK, MARK_TEXT, key_first, read, the_file,
)
from test_bump_leg import (
    SPEC_PIN, branched, bump, commit_spec_pin, validate,
)
from test_pin_rewrite_layout import (  # noqa: F401
    NEW_COMMIT, NEW_ROWS, NEW_TREE, OLD_COMMIT, OLD_ROWS, OLD_TREE, tools,
)
from test_update_shape import (  # noqa: F401
    apply, commit_manifest, commit_shape_pin, root, upstream_and_project,
    validators_are_green,
)

from repo_shape import Refusal, load_yaml, tree_digest

#: Where each finder's file is, in the root the tool reads it from.
WHERE = {
    "shape-pin-commit": "contracts/shape-pin.yaml",
    "manifest-shape-header": "project.yaml",
    "leg-pin-commit": "contracts/spec-pin.yaml",
}
#: What a finder's file starts with once the marks are off, as bytes.
KEY = {"shape-pin-commit": b"commit:", "manifest-shape-header": b"shape:",
       "leg-pin-commit": b"commit:"}
#: The code each finder's tool refuses a file it finds no key in with.
REFUSED_AS = {
    "shape-pin-commit": "update-pin-unrecognised",
    "manifest-shape-header": "update-manifest-no-shape",
    "leg-pin-commit": "bump-leg-pin-unrecognised",
}
#: The characters that are zero-width or format (`Cf`) and no mark. A cut
#: widened to the category takes every one of them.
FORMAT_CHARACTERS = {
    "zero-width-space": 0x200B,
    "zero-width-non-joiner": 0x200C,
    "zero-width-joiner": 0x200D,
    "word-joiner": 0x2060,
    "soft-hyphen": 0x00AD,
    "left-to-right-mark": 0x200E,
}
#: A first line that is a key of its own, which the reader reads and no tool
#: looks for. A format character in front of it is part of the key's name.
OTHER_KEY = "other: 1\n"
#: A comment the second character of which is a mark: text, to the reader
#: and to the tools.
COMMENT_WITH_A_MARK = "#" + MARK_TEXT + " saved by hand\n"


def format_character(name: str) -> str:
    char = chr(FORMAT_CHARACTERS[name])
    assert unicodedata.category(char) == "Cf", "fixture: a format character"
    assert char != MARK_TEXT, "fixture: and not the mark"
    return char


def written_by_the_tool(loaded, base: Path, finder: str, text: str) -> bytes:
    """The finder's file as bytes, after its tool has read and written it.

    `text` is the finder's file as it is in `base`, written as bytes. For
    `update-shape.py` that is `_repin`, which reads and writes both of its
    files, so the other is there as the scaffold writes it; for `bump-leg.py`
    it is what `main` does with the leg's pin, in its order: `_leg_pin_text`,
    `rewrite_pin`, `write_lf`. A refusal is raised, and the file is as it
    was where the tool read it before it wrote.
    """
    path = base / WHERE[finder]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    if finder == "leg-pin-commit":
        bump = loaded.bump_leg
        bump.write_lf(path, bump.rewrite_pin(
            bump._leg_pin_text(base, path), NEW_COMMIT, NEW_TREE))
        return path.read_bytes()
    other = ("manifest-shape-header" if finder == "shape-pin-commit"
             else "shape-pin-commit")
    (base / WHERE[other]).parent.mkdir(parents=True, exist_ok=True)
    (base / WHERE[other]).write_bytes(
        the_file(other, OLD_COMMIT, OLD_TREE, OLD_ROWS).encode("utf-8"))
    update = loaded.update_shape
    update._repin(base, update.PROJECT_KIND, update.Rollback(base),
                  [update.Row(path, digest) for path, digest in NEW_ROWS],
                  OLD_COMMIT, NEW_COMMIT, NEW_TREE)
    return path.read_bytes()


def after(finder: str) -> bytes:
    """The finder's file at the target, key on line 1, as bytes."""
    return the_file(finder, NEW_COMMIT, NEW_TREE, NEW_ROWS).encode("utf-8")


def indented(text: str, pad: str) -> str:
    """`text` with `pad` in front of every line that is not blank."""
    return "\n".join(pad + line if line else line
                     for line in text.split("\n"))


def refused_and_unchanged(loaded, base: Path, finder: str,
                          before: str) -> None:
    """The finder's tool refuses `before` in the finder's words and leaves
    the file as the bytes it held."""
    with pytest.raises(Refusal) as refused:
        written_by_the_tool(loaded, base, finder, before)
    assert refused.value.code == REFUSED_AS[finder]
    assert FINDERS[finder].refused in refused.value.detail
    assert (base / WHERE[finder]).read_bytes() == before.encode("utf-8")


# ---------------------------------------------------------------------------
# NIT 1: the tools' own read and write
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("marks", [0, 1, 2], ids=["no-mark", "mark",
                                                  "two-marks"])
@pytest.mark.parametrize("finder", list(FINDERS))
def test_the_tools_own_write_starts_with_the_marks_its_read_met(
        tools, tmp_path, finder, marks):  # noqa: F811
    """THE ISSUE'S ROWS, one per file the tools write. #933's Direction:
    "the marked first-key file is written, its first bytes are the mark".
    `read_text(encoding="utf-8-sig")` at `_repin`'s two reads or at
    `_leg_pin_text`'s drops them before the rewriter is called, and the
    tool writes one mark fewer than it read (none for one, one for two), a
    file every reader reads and the rewriters' return values do not show.
    The control with no mark is the file as it always was: not a byte in
    front of it, as a write that puts a mark on every file would give."""
    before = MARK_TEXT * marks + the_file(finder, OLD_COMMIT, OLD_TREE,
                                          OLD_ROWS)
    assert read(finder, before) == (OLD_COMMIT, OLD_TREE), (
        "fixture: the reader reads the marked file")

    written = written_by_the_tool(tools, tmp_path, finder, before)

    assert written.startswith(MARK * marks + KEY[finder])
    assert not written[len(MARK) * marks:].startswith(MARK)
    assert written == MARK * marks + after(finder), (
        "every byte after the marks is the rewrite of the file without them")
    assert read(finder, written.decode("utf-8")) == (NEW_COMMIT, NEW_TREE)


# ---------------------------------------------------------------------------
# NIT 2: only U+FEFF is cut
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("marks", [1, 2], ids=["mark", "two-marks"])
@pytest.mark.parametrize("name", list(FORMAT_CHARACTERS))
@pytest.mark.parametrize("finder", list(FINDERS))
def test_a_format_character_after_the_marks_is_not_cut_so_the_file_is_refused(
        tools, tmp_path, finder, name, marks):  # noqa: F811
    """THE SECOND CHARACTER, WHEN IT IS NOT A MARK. The mark is the one
    character of the `Cf` category the reader takes off the start of a file.
    Another is the first character of line 1 once the marks are off, so it
    is part of the key's name, to the reader (which finds no pin) and to the
    tool (which finds 0 `commit` lines). A cut widened to the category took
    it, found the key and wrote a file without the character, exit 0."""
    char = format_character(name)
    before = MARK_TEXT * marks + char + the_file(finder, OLD_COMMIT,
                                                 OLD_TREE, OLD_ROWS)
    with pytest.raises(ValueError):
        read(finder, before)

    refused_and_unchanged(tools, tmp_path, finder, before)


@pytest.mark.parametrize("marks", [1, 2], ids=["mark", "two-marks"])
@pytest.mark.parametrize("name", list(FORMAT_CHARACTERS))
@pytest.mark.parametrize("finder", list(FINDERS))
def test_a_format_character_after_the_marks_stays_where_it_was_written(
        tools, tmp_path, finder, name, marks):  # noqa: F811
    """THE SAME CHARACTER, BEFORE A KEY THE TOOL IS NOT LOOKING FOR. The
    reader reads `<char>other: 1` as a key of its own, and the pin after
    it. The tool takes the marks off, finds its key, and writes every byte
    that was not a mark as it was, the character among them: not one of the
    two characters cut, and not the category."""
    char = format_character(name)
    before = MARK_TEXT * marks + char + OTHER_KEY + the_file(
        finder, OLD_COMMIT, OLD_TREE, OLD_ROWS)
    assert read(finder, before) == (OLD_COMMIT, OLD_TREE), (
        "fixture: the reader reads the file")

    written = written_by_the_tool(tools, tmp_path, finder, before)

    assert written == (MARK * marks + (char + OTHER_KEY).encode("utf-8")
                       + after(finder))


@pytest.mark.parametrize("marks", [0, 1], ids=["no-mark", "mark"])
@pytest.mark.parametrize("lead", [" ", "\t"], ids=["space", "tab"])
@pytest.mark.parametrize("finder", list(FINDERS))
def test_a_space_or_a_tab_in_front_of_the_key_is_not_cut(
        tools, tmp_path, finder, lead, marks):  # noqa: F811
    """THE ISSUE'S SECOND ROW. An `lstrip` that also cuts spaces and line
    feeds wrote a leg pin or a shape pin whose line 1 is ` commit: ...`,
    exit 0, where it is refused as `0 commit line(s)`, as it was before
    #1050, and the reader refuses it too. Before a mark or after one makes
    no difference, because the cut stops at the first character that is not
    a mark."""
    before = MARK_TEXT * marks + lead + the_file(finder, OLD_COMMIT,
                                                 OLD_TREE, OLD_ROWS)
    with pytest.raises(ValueError):
        read(finder, before)

    refused_and_unchanged(tools, tmp_path, finder, before)


@pytest.mark.parametrize("marks", [0, 1], ids=["no-mark", "mark"])
@pytest.mark.parametrize("finder", list(FINDERS))
def test_a_file_indented_on_every_line_is_refused_as_it_was(
        tools, tmp_path, finder, marks):  # noqa: F811
    """THE ISSUE'S THIRD BULLET. The reader reads a file whose every line is
    indented two spaces, and no tool finds a key at column 0 of it. With the
    cut widened to spaces, line 1 alone was cut, and the file was written
    with its first line at column 0 and the rest as they were."""
    before = MARK_TEXT * marks + indented(
        the_file(finder, OLD_COMMIT, OLD_TREE, OLD_ROWS), "  ")
    assert read(finder, before) == (OLD_COMMIT, OLD_TREE), (
        "fixture: the reader reads the indented file")

    refused_and_unchanged(tools, tmp_path, finder, before)


@pytest.mark.parametrize("marks", [0, 1, 2], ids=["no-mark", "mark",
                                                  "two-marks"])
@pytest.mark.parametrize("finder", list(FINDERS))
def test_a_mark_that_is_the_second_character_is_text_and_is_written_back(
        tools, tmp_path, finder, marks):  # noqa: F811
    """THE CUT IS THE START OF THE TEXT. `#<mark> saved by hand` is a comment
    whose second character is U+FEFF: it is not in front of line 1, so it is
    text, to the reader and to the tool, and the tool writes it back with
    the marks that are. A cut that also took the next character, or every
    mark in the file, wrote it without."""
    before = MARK_TEXT * marks + COMMENT_WITH_A_MARK + the_file(
        finder, OLD_COMMIT, OLD_TREE, OLD_ROWS)
    assert read(finder, before) == (OLD_COMMIT, OLD_TREE), (
        "fixture: the reader reads the file")

    written = written_by_the_tool(tools, tmp_path, finder, before)

    assert written == (MARK * marks + COMMENT_WITH_A_MARK.encode("utf-8")
                       + after(finder))


@pytest.mark.parametrize("marks", [1, 2], ids=["mark", "two-marks"])
@pytest.mark.parametrize("finder", list(FINDERS))
def test_the_key_moved_down_a_line_keeps_the_marks_where_they_were(
        tools, tmp_path, finder, marks):  # noqa: F811
    """THE MARKS ARE IN FRONT OF WHATEVER LINE 1 IS. A comment above the
    key, as `tests/test_bom_rewrites.py` writes one, with the marks in front
    of it: written back as it was, marks and all, and the key is found."""
    plain = the_file(finder, OLD_COMMIT, OLD_TREE, OLD_ROWS)
    before = MARK_TEXT * marks + "# saved by hand\n" + plain
    assert read(finder, before) == (OLD_COMMIT, OLD_TREE), (
        "fixture: the reader reads the file")

    written = written_by_the_tool(tools, tmp_path, finder, before)

    assert written == (MARK * marks + b"# saved by hand\n" + after(finder))


# ---------------------------------------------------------------------------
# Each tool, end to end, through its entry point
# ---------------------------------------------------------------------------

#: Where the advanced spec commit is pushed. Not another module's branch: the
#: bare remotes are session-scoped, and a second, different commit pushed to
#: a name already taken is refused as non-fast-forward.
ADVANCE_BRANCH = "bom-tool-io-advance"


@pytest.fixture(scope="module")
def advanced(scaffolded, tmp_path_factory) -> str:
    """A real new commit on the spec leg's bare remote; returns its sha.

    THIS FILE'S OWN, AND NOT `tests/test_bump_leg.py`'s. A module-scoped
    fixture runs once for every module that names it, and that one pushes to
    `bump-leg-advance` on the session's one remote: imported here it ran
    twice in one session, and whichever pushed second was refused as
    non-fast-forward (47 setup errors in `tests/test_bump_leg.py` in CI's
    full suite, #1188's first run). This one pushes to a branch of its own,
    as every other module that advances the leg does.
    """
    work = cloned_just_pushed(
        scaffolded["remotes"] / f"{PROJECT}-spec.git",
        tmp_path_factory.mktemp("spec-advance-bom-io") / f"{PROJECT}-spec")
    (work / "BOM-TOOL-IO-CONTRACT.md").write_text("# a contract gained\n")
    git("add", "--", "BOM-TOOL-IO-CONTRACT.md", cwd=work)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "Advance the spec leg for the byte-order-mark tool rows", cwd=work)
    git("push", "-q", "origin", f"HEAD:refs/heads/{ADVANCE_BRANCH}", cwd=work)
    return git("rev-parse", "HEAD", cwd=work).stdout.strip()


def values_moved(text: str, was: dict, now: dict) -> str:
    """`text` with the two lines the tools move, and nothing else: each
    `<key>: "<value>"` that held `was[key]` holds `now[key]`."""
    for key in ("commit", "tree_sha256"):
        text = text.replace(f'{key}: "{was[key]}"', f'{key}: "{now[key]}"')
    return text


@pytest.mark.parametrize("marks", [1, 2], ids=["mark", "two-marks"])
def test_update_shape_apply_writes_the_marks_of_the_pin_and_the_manifest(
        root, upstream_and_project, marks):  # noqa: F811
    """`update-shape.py apply`, against a local `--upstream`, on a root whose
    shape pin and manifest are both committed with their first key on line 1
    after the marks. Both are written with the marks they had, and every
    byte after them is the file with the two values moved: the `files:`
    block of the pin is written whole, so it is compared above that line,
    as `tests/test_update_shape.py` compares it."""
    a, target = upstream_and_project["a"], upstream_and_project["b"]
    upstream = upstream_and_project["upstream"]
    pin = root / "contracts" / "shape-pin.yaml"
    manifest = root / "project.yaml"
    was = {"commit": a,
           "tree_sha256": load_yaml(pin)["digests"]["tree_sha256"]}
    marked_pin = MARK_TEXT * marks + key_first(
        pin.read_text(encoding="utf-8"), "commit")
    marked_manifest = MARK_TEXT * marks + key_first(
        manifest.read_text(encoding="utf-8"), "shape")
    commit_shape_pin(root, marked_pin, "Mark the pin, its first key first")
    commit_manifest(root, marked_manifest,
                    "Mark the manifest, its first key first")
    validators_are_green(root)

    result = apply(root, upstream_and_project)

    assert result.returncode == 0, result.stdout + result.stderr
    now = {"commit": target,
           "tree_sha256": tree_digest(upstream, target)}
    pin_bytes, manifest_bytes = pin.read_bytes(), manifest.read_bytes()
    assert pin_bytes.startswith(MARK * marks + b"commit:")
    assert manifest_bytes.startswith(MARK * marks + b"shape:")
    assert not pin_bytes[len(MARK) * marks:].startswith(MARK)
    assert not manifest_bytes[len(MARK) * marks:].startswith(MARK)
    assert pin_bytes.split(b"\nfiles:\n", 1)[0] == values_moved(
        marked_pin.split("\nfiles:\n", 1)[0], was, now).encode("utf-8")
    assert manifest_bytes == values_moved(marked_manifest, was,
                                          now).encode("utf-8")
    validators_are_green(root)


@pytest.mark.parametrize("marks", [1, 2], ids=["mark", "two-marks"])
def test_bump_leg_writes_the_marks_of_the_leg_pin(
        project, scaffolded, advanced, marks):
    """`bump-leg.py`, on a leg pin committed with `commit:` on line 1 after
    the marks. The pin is written with the marks it had, every byte after
    them is the pin with the two values moved, and the project's own gate is
    green."""
    branched(project)
    pin = project / SPEC_PIN
    before = load_yaml(pin)
    was = {"commit": before["commit"],
           "tree_sha256": before["digests"]["tree_sha256"]}
    marked = MARK_TEXT * marks + key_first(pin.read_text(encoding="utf-8"),
                                           "commit")
    commit_spec_pin(project, marked, "Mark the pin, its first key first")

    result = bump(project, scaffolded, advanced)

    assert result.returncode == 0, result.stderr + result.stdout
    now = {"commit": advanced,
           "tree_sha256": tree_digest(project / "spec", advanced)}
    written = pin.read_bytes()
    assert written.startswith(MARK * marks + b"commit:")
    assert not written[len(MARK) * marks:].startswith(MARK)
    assert written == values_moved(marked, was, now).encode("utf-8")
    assert validate(project).returncode == 0, "the project's own gate is green"
    assert git("status", "--porcelain", cwd=project).stdout == ""


def test_update_shape_apply_refuses_a_pin_indented_on_every_line_unchanged(
        root, upstream_and_project):  # noqa: F811
    """The reader reads a shape pin indented two spaces on every line, and
    `apply` finds no `commit:` at column 0 of it: refused as it was, in the
    rewrite's words, and the pin and the manifest are as they were."""
    pin = root / "contracts" / "shape-pin.yaml"
    manifest = root / "project.yaml"
    laid = indented(pin.read_text(encoding="utf-8"), "  ")
    commit_shape_pin(root, MARK_TEXT + laid, "Indent the whole pin")
    before = pin.read_bytes(), manifest.read_bytes()

    result = apply(root, upstream_and_project)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "update-pin-unrecognised" in result.stderr
    assert "has 0 `commit` line(s)" in result.stderr
    assert (pin.read_bytes(), manifest.read_bytes()) == before


def test_bump_leg_refuses_a_pin_indented_on_every_line_unchanged(
        project, scaffolded, advanced):
    """The same for a leg pin: refused as it was, nothing written."""
    branched(project)
    pin = project / SPEC_PIN
    laid = indented(pin.read_text(encoding="utf-8"), "  ")
    commit_spec_pin(project, MARK_TEXT + laid, "Indent the whole pin")
    before = pin.read_bytes()

    result = bump(project, scaffolded, advanced)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "bump-leg-pin-unrecognised" in result.stderr
    assert "has 0 `commit` line(s)" in result.stderr
    assert pin.read_bytes() == before
    assert git("status", "--porcelain", cwd=project).stdout == ""
