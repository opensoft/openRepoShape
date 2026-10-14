# SPDX-License-Identifier: Apache-2.0
"""The machinery #519 put behind the handbook and README.md's line cap.

`tests/test_repo_hygiene.py` runs it on the real files: README.md cut into
segments, each page section of `docs/handbook.html` recording the segments
it reads and their hashes, and the cap read from `tests/readme-cap.d/`. Those
two tests say whether the files agree TODAY; these say whether the checks
would notice when they stop agreeing, and what they would say. So every case
here is a few lines of fixture text, never the real files, and every message
the checks print is held to what it must tell the person who reads it.

OS-neutral on purpose: a fixture spells its own line endings, so nothing here
depends on how the checkout wrote README.md (Windows CI checks out LF only
because `.gitattributes` says so), and nothing runs git.
"""

from __future__ import annotations

import pytest

from test_repo_hygiene import (
    README_CAP_BASE, README_CAP_FORMAT, handbook_marker_problems,
    readme_cap_ledger_refusal, readme_cap_raises, readme_cap_refusal,
    readme_cap_sum, readme_fingerprint, readme_segments)

#: A README in miniature: a preamble, a `## ` heading holding a `### ` and a
#: fenced `## ` line, and a heading with a colon in it holding a tilde fence.
README = (
    "# Thing\n"
    "\n"
    "Intro.\n"
    "\n"
    "## First\n"
    "\n"
    "```sh\n"
    "## not a heading, a shell comment\n"
    "```\n"
    "\n"
    "### Sub\n"
    "\n"
    "Body.\n"
    "\n"
    "## Second: with a colon\n"
    "\n"
    "~~~\n"
    "## nor this\n"
    "~~~\n"
    "Tail.\n"
)

#: Which README segments each part of the fixture page reads. `masthead`
#: and `licence` become a `<header>` and a `<footer>`, as on the real page.
READS = {
    "masthead": ["preamble", "First"],
    "first": ["First"],
    "second": ["Second: with a colon"],
    "notes": [],
    "licence": ["Second: with a colon"],
}

HEADING_TO_ID = {"First": "first", "Second: with a colon": "second"}
READS_NOTHING = frozenset({"notes"})

#: git's own blob hashes of three texts (`git hash-object --stdin`), so the
#: fingerprint is held to git rather than to a second copy of its formula.
GIT_BLOBS = {
    "hello\n": "ce013625030ba8dba906f756967f9e9ca394464a",
    "": "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391",
    "a\nb\n": "422c2b7ab3b3c668038da977e4e93a5fc623169c",
}


def blobs_of(readme):
    return {name: readme_fingerprint(text)
            for name, text in readme_segments(readme)}


def page_reading(readme, reads=None, *, blob=None, extra=""):
    """A page whose parts carry markers for `reads`, each at the hash
    `readme` gives it now unless `blob` maps `(part, segment)` elsewhere.
    Every marker is followed by a line of prose, as on the real page."""
    current = blobs_of(readme)
    lines = ["<html><body><nav><!-- contents --></nav><main>"]
    for part, names in (READS if reads is None else reads).items():
        tag = {"masthead": "header", "licence": "footer"}.get(part, "section")
        lines.append(f'<{tag} id="{part}">')
        for name in names:
            value = (blob or {}).get((part, name)) or current[name]
            lines.append(f"  <!-- reads README.md § {name}: blob {value} -->")
            lines.append(f"  <p>What {part} says of {name}.</p>")
        lines.append(f"  <p>{part}</p>\n</{tag}>")
    lines += [extra, "</main></body></html>", ""]
    return "\n".join(lines)


def problems_with(page, readme=README, heading_to_id=None,
                  reads_nothing=READS_NOTHING):
    return handbook_marker_problems(
        readme, page, HEADING_TO_ID if heading_to_id is None
        else heading_to_id, reads_nothing)


def only(problems, *fragments):
    """The one problem holding every fragment; fails if there is not one."""
    found = [p for p in problems if all(f in p for f in fragments)]
    assert len(found) == 1, (fragments, problems)
    return found[0]


# ------------------------------------------------------------- the segments


def test_the_segments_hold_every_byte_once_in_order():
    segments = readme_segments(README)
    assert [name for name, _ in segments] == [
        "preamble", "First", "Second: with a colon"]
    assert "".join(text for _, text in segments) == README
    assert segments[0][1] == "# Thing\n\nIntro.\n\n"
    assert segments[1][1].startswith("## First\n")
    assert segments[2][1].endswith("Tail.\n")


def test_a_fenced_heading_and_a_subsection_stay_in_their_segment():
    segments = dict(readme_segments(README))
    assert "## not a heading, a shell comment\n" in segments["First"]
    assert "### Sub\n" in segments["First"]
    assert "## nor this\n" in segments["Second: with a colon"]


def test_the_preamble_comes_first_and_an_empty_one_asks_for_no_marker():
    readme = "## Only\n\ntext\n"
    assert readme_segments(readme) == [("preamble", ""),
                                       ("Only", "## Only\n\ntext\n")]
    page = page_reading(readme, {"only": ["Only"]})
    assert problems_with(page, readme, {"Only": "only"}, frozenset()) == []


def test_crlf_and_lf_cut_and_hash_the_same():
    crlf = README.replace("\n", "\r\n")
    assert [n for n, _ in readme_segments(crlf)] == [
        n for n, _ in readme_segments(README)]
    assert "".join(t for _, t in readme_segments(crlf)) == crlf
    assert blobs_of(crlf) == blobs_of(README)
    assert problems_with(page_reading(README), crlf) == []


@pytest.mark.parametrize("text", sorted(GIT_BLOBS))
def test_a_fingerprint_is_gits_blob_hash(text):
    assert readme_fingerprint(text) == GIT_BLOBS[text]
    assert readme_fingerprint(text.replace("\n", "\r\n")) == GIT_BLOBS[text]


def test_a_fingerprint_moves_with_one_byte():
    assert readme_fingerprint("a\nb\n") != readme_fingerprint("a\nb \n")


# -------------------------------------------------------------- the markers


def test_a_page_that_read_every_segment_as_it_is_has_no_problem():
    assert problems_with(page_reading(README)) == []


def test_a_renamed_heading_names_the_marker_and_the_headings_there_are():
    renamed = README.replace("## First\n", "## Primero\n")
    problems = problems_with(page_reading(README), renamed,
                             {"Primero": "first"})
    said = only(problems, "names README.md § First,", "`first`")
    assert "<!-- reads README.md § First: blob " in said
    assert "Its segments are: preamble; Primero; Second: with a colon." in said
    assert "`Full text` link" in said


def test_a_segment_nobody_reads_is_named_with_the_marker_to_write():
    reads = dict(READS, second=[], licence=[], notes=["First"])
    problems = problems_with(page_reading(README, reads),
                             heading_to_id={"First": "first"},
                             reads_nothing=frozenset())
    blob = blobs_of(README)["Second: with a colon"]
    said = only(problems, "§ Second: with a colon is read by no marker")
    assert (f"<!-- reads README.md § Second: with a colon: blob {blob} -->"
            in said)
    assert "own design and voice" in said


def test_a_stale_segment_names_every_section_reading_it_and_the_new_value():
    moved = README.replace("Body.\n", "Body, changed.\n")
    old, new = blobs_of(README)["First"], blobs_of(moved)["First"]
    problems = problems_with(page_reading(README), moved)
    said = only(problems, "README.md § First has moved")
    assert "Page sections that read it: `masthead`, `first`." in said
    assert f"blob {old}" in said
    assert f"set each of their markers to blob {new}" in said
    for meaning in ("Re-read what changed", "own design and voice",
                    "#89 is the precedent",
                    "moving the markers alone is honest",
                    "hand-editing a pin"):
        assert meaning in said, meaning
    assert len(problems) == 1, problems


def test_a_half_moved_segment_names_only_the_marker_still_behind():
    moved = README.replace("Body.\n", "Body, changed.\n")
    new = blobs_of(moved)["First"]
    page = page_reading(README, blob={("masthead", "First"): new})
    said = only(problems_with(page, moved), "README.md § First has moved")
    assert "the marker in `first` (docs/handbook.html:" in said
    assert "`masthead` (" not in said
    assert "Page sections that read it: `masthead`, `first`." in said


def test_a_mapped_heading_must_be_read_inside_its_own_section():
    problems = problems_with(page_reading(README),
                             heading_to_id={"First": "second"})
    said = only(problems, "maps README.md § First to page section `second`")
    assert "no marker inside `second` reads it" in said
    assert f"blob {blobs_of(README)['First']}" in said


def test_a_section_reading_nothing_is_declared_and_reads_nothing():
    reads = dict(READS, notes=["First"], extra=[])
    problems = problems_with(page_reading(README, reads),
                             reads_nothing=frozenset({"notes", "gone"}))
    only(problems, "page section `extra` carries no marker")
    only(problems, "page section `notes` is declared to read no README",
         "§ First")
    only(problems, "names `gone`, and the page has no section with that id")
    assert len(problems) == 3, problems


@pytest.mark.parametrize("comment", [
    "<!-- read README.md § First: blob 0123 -->",
    "<!-- reads README.md § First: blob ABCDEF -->",
    "<!--reads README.md § First: blob "
    "ce013625030ba8dba906f756967f9e9ca394464a-->",
    "<!-- the README says so -->",
])
def test_a_mistyped_marker_is_refused_rather_than_skipped(comment):
    page = page_reading(README).replace("<p>first</p>", comment)
    said = only(problems_with(page), "reads like a marker and is not one")
    assert comment in said and "docs/handbook.html:" in said


def test_a_marker_outside_every_page_section_is_refused():
    marker = page_reading(README, {"x": ["First"]}).splitlines()[2]
    page = page_reading(README).replace("<!-- contents -->", marker.strip())
    only(problems_with(page), "§ First sits in no page section",
         "docs/handbook.html:1:")


def test_one_section_reads_one_segment_once():
    page = page_reading(README, dict(READS, first=["First", "First"]))
    only(problems_with(page), "page section `first` carries 2 markers for "
                              "README.md § First")


def test_two_markers_on_adjacent_lines_are_refused():
    """Two README pull requests changing two segments a section reads each
    move one marker, and git merges the two only when the markers are not
    neighbours; the fixture's own markers always have a line between."""
    page = page_reading(README).replace(
        "  <p>What masthead says of preamble.</p>\n", "")
    said = only(problems_with(page), "on adjacent lines")
    assert "README.md § preamble and § First" in said


def test_two_segments_of_one_name_are_refused():
    readme = README + "\n## First\n\nAgain.\n"
    only(problems_with(page_reading(README), readme),
         "more than one segment called `First`")


# ---------------------------------------------------------- the cap ledger


def write_ledger(root, files):
    ledger = root / "readme-cap.d"
    ledger.mkdir()
    for name, data in files.items():
        (ledger / name).write_bytes(data)
    return ledger


def test_no_ledger_raises_nothing(tmp_path):
    assert readme_cap_raises(tmp_path / "readme-cap.d") == ([], [])
    assert readme_cap_sum([]).startswith(f"{README_CAP_BASE}, with no raise")


def test_each_raise_adds_its_lines_whatever_the_line_endings(tmp_path):
    ledger = write_ledger(tmp_path, {
        "519.txt": b"+8\n2026-10-14\nWhy the README earns eight lines.\n",
        "1000.txt": b"+3\r\n2026-10-15\r\nA reason, on\r\ntwo lines.\r\n",
    })
    raises, problems = readme_cap_raises(ledger)
    assert problems == []
    assert [(path.name, n) for path, n in raises] == [("519.txt", 8),
                                                      ("1000.txt", 3)]
    assert readme_cap_sum(raises) == (
        f"{README_CAP_BASE} + 8 (519.txt) + 3 (1000.txt) = "
        f"{README_CAP_BASE + 11}")


@pytest.mark.parametrize("name, data, fragment", [
    ("notes.md", b"+3\n2026-10-14\nr\n", "is not named `<issue or PR number>"),
    ("0519.txt", b"+3\n2026-10-14\nr\n", "is not named"),
    ("520.txt", b"8\n2026-10-14\nr\n", "line 1 must be `+N`"),
    ("521.txt", b"+0\n2026-10-14\nr\n", "line 1 must be `+N`"),
    ("522.txt", b"", "line 1 must be `+N`"),
    ("523.txt", b"+3\n14 October 2026\nr\n", "line 2 must be"),
    ("524.txt", b"+3\n2026-02-30\nr\n", "line 2 must be"),
    ("525.txt", b"+3\n2026-10-14\n", "gives no reason"),
    ("526.txt", b"+3\n2026-10-14\n\n  \n", "gives no reason"),
    ("527.txt", b"+3\n2026-10-14\n\xff\n", "is not UTF-8"),
])
def test_a_malformed_raise_is_named_by_its_path(tmp_path, name, data,
                                                fragment):
    ledger = write_ledger(tmp_path, {
        "519.txt": b"+8\n2026-10-14\nA good one.\n", name: data})
    raises, problems = readme_cap_raises(ledger)
    assert [path.name for path, _ in raises] == ["519.txt"]
    assert len(problems) == 1 and fragment in problems[0], problems
    assert problems[0].startswith((ledger / name).as_posix())
    said = readme_cap_ledger_refusal(problems)
    assert said.startswith(problems[0]) and README_CAP_FORMAT in said


def test_a_directory_in_the_ledger_is_named_too(tmp_path):
    ledger = write_ledger(tmp_path, {})
    (ledger / "530.txt").mkdir()
    _, problems = readme_cap_raises(ledger)
    assert problems == [f"{(ledger / '530.txt').as_posix()} is not a file, "
                        "and the ledger holds nothing else"]


def test_a_readme_over_the_cap_is_told_how_to_raise_it(tmp_path):
    ledger = write_ledger(tmp_path, {"519.txt": b"+8\n2026-10-14\nWhy.\n"})
    raises, _ = readme_cap_raises(ledger)
    said = readme_cap_refusal(README_CAP_BASE + 9, raises)
    assert said.startswith(
        f"README.md is {README_CAP_BASE + 9} lines; the cap is "
        f"{README_CAP_BASE} + 8 (519.txt) = {README_CAP_BASE + 8}.")
    assert README_CAP_FORMAT in said
    for part in ("line 1 `+N`", "line 2 the date, `YYYY-MM-DD`",
                 "tests/readme-cap.d/519.txt"):
        assert part in said, part
