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
    README_CAP_BASE, README_CAP_FORMAT, handbook_footer_problems,
    handbook_marker_problems, readme_cap_ledger_refusal, readme_cap_raises,
    readme_cap_refusal, readme_cap_sum, readme_fingerprint, readme_segments)

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

#: Which README segments each part of the fixture page reads, in the order
#: its markers are written. `masthead` and `licence` become a `<header>` and
#: a `<footer>`, as on the real page; `notes` reads nothing, as `agents` does.
READS = {
    "masthead": ["preamble", "First"],
    "first": ["First"],
    "second": ["Second: with a colon"],
    "notes": [],
    "licence": ["Second: with a colon"],
}

HEADING_TO_ID = {"First": "first", "Second: with a colon": "second"}

#: git's own blob hashes of three texts (`git hash-object --stdin`), so the
#: fingerprint is held to git rather than to a second copy of its formula.
GIT_BLOBS = {
    "hello\n": "ce013625030ba8dba906f756967f9e9ca394464a",
    "": "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391",
    "a\nb\n": "422c2b7ab3b3c668038da977e4e93a5fc623169c",
}


def table(reads):
    """`reads` as HANDBOOK_READS spells a table: a frozenset per part."""
    return {part: frozenset(names) for part, names in reads.items()}


def blobs_of(readme):
    return {name: readme_fingerprint(text)
            for name, text in readme_segments(readme)}


def marker(name, blob):
    return f"  <!-- reads README.md § {name}: blob {blob} -->"


def page_reading(readme, reads=None, *, blob=None):
    """A page whose parts carry markers for `reads`, at the top of each part,
    alone between blank lines as on the real page, each at the hash `readme`
    gives it now unless `blob` maps `(part, segment)` elsewhere."""
    current = blobs_of(readme)
    lines = ["<html><body><nav><!-- contents --></nav><main>"]
    for part, names in (READS if reads is None else reads).items():
        tag = {"masthead": "header", "licence": "footer"}.get(part, "section")
        lines.append(f'<{tag} id="{part}">')
        for name in names:
            lines += ["", marker(name, (blob or {}).get((part, name))
                                 or current[name])]
        lines += ["", f"  <p>What {part} says.</p>", f"</{tag}>"]
    lines += ["</main></body></html>", ""]
    return "\n".join(lines)


def problems_with(page, readme=README, heading_to_id=None, reads=None):
    return handbook_marker_problems(
        readme, page, HEADING_TO_ID if heading_to_id is None
        else heading_to_id, table(READS if reads is None else reads))


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
    reads = {"only": ["Only"]}
    assert problems_with(page_reading(readme, reads), readme,
                         {"Only": "only"}, reads) == []


def test_crlf_cuts_and_hashes_as_lf_and_is_refused_in_the_readme():
    crlf = README.replace("\n", "\r\n")
    assert [n for n, _ in readme_segments(crlf)] == [
        n for n, _ in readme_segments(README)]
    assert "".join(t for _, t in readme_segments(crlf)) == crlf
    assert blobs_of(crlf) == blobs_of(README)
    problems = problems_with(page_reading(README), crlf)
    said = only(problems, "README.md:1: a carriage return (20 in the file)")
    assert "LF-only" in said and ".gitattributes" in said
    assert len(problems) == 1, problems


def test_a_lone_carriage_return_is_refused_where_it_is():
    readme = README.replace("Body.\n", "Body.\rStill body.\n")
    only(problems_with(page_reading(readme), readme),
         "README.md:13: a carriage return (1 in the file)")


@pytest.mark.parametrize("text", sorted(GIT_BLOBS))
def test_a_fingerprint_is_gits_blob_hash(text):
    assert readme_fingerprint(text) == GIT_BLOBS[text]
    assert readme_fingerprint(text.replace("\n", "\r\n")) == GIT_BLOBS[text]


def test_a_fingerprint_moves_with_one_byte():
    assert readme_fingerprint("a\nb\n") != readme_fingerprint("a\nb \n")


@pytest.mark.parametrize("added", [
    "  ## Indented\n",
    "   ## Indented three\n",
    "##\tTabbed\n",
    "##\n",
    "Paragraph text\n---\n",
    "Paragraph text\n  -\n",
])
def test_a_heading_github_renders_that_the_cut_misses_is_refused(added):
    readme = README + "\n" + added
    said = only(problems_with(page_reading(readme), readme),
                "makes a `##` heading on GitHub")
    line = README.count("\n") + 1 + added.count("\n")
    assert said.startswith(f"README.md:{line}: `{added.splitlines()[-1]}`")
    assert "write it as `## <name>` at the start of the line" in said


@pytest.mark.parametrize("added", [
    "##Name with no space is a paragraph\n",
    "---\n",
    "| a | b |\n|---|---|\n| 1 | 2 |\n",
    "- item\n---\n",
    "# Title\n---\n",
    "```\n  ## inside a fence\n```\n",
    "    ## indented code\n",
])
def test_what_github_does_not_render_as_a_heading_passes(added):
    readme = README + "\n" + added
    assert problems_with(page_reading(readme), readme) == []


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
    only(problems, "HANDBOOK_READS lists README.md § First for `first`")


def test_a_segment_nobody_reads_is_named_with_the_marker_to_write():
    reads = dict(READS, second=[], licence=[])
    problems = problems_with(page_reading(README, reads),
                             heading_to_id={"First": "first"}, reads=reads)
    blob = blobs_of(README)["Second: with a colon"]
    said = only(problems, "§ Second: with a colon is read by no page section")
    assert (f"<!-- reads README.md § Second: with a colon: blob {blob} -->"
            in said)
    assert "row in HANDBOOK_READS" in said
    assert len(problems) == 1, problems


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


def test_a_dropped_marker_the_table_lists_is_refused():
    """The review of PR #551 dropped the five secondary § Starting markers
    and the old check passed: a section had to carry one marker, not every
    one its reading needs. The table makes each of them owed."""
    page = page_reading(README, dict(READS, masthead=["preamble"]))
    blob = blobs_of(README)["First"]
    said = only(problems_with(page), "page section `masthead` reads "
                                     "README.md § First by its row")
    assert f"<!-- reads README.md § First: blob {blob} -->" in said
    assert "changes when the page's structure does" in said


def test_a_marker_the_table_does_not_list_is_refused():
    page = page_reading(README, dict(READS, notes=["First"]))
    said = only(problems_with(page), "page section `notes` carries a marker "
                                     "for README.md § First")
    assert "add it to the row" in said and "drop the marker" in said


def test_the_table_has_a_row_for_every_part_and_no_other():
    reads = dict(READS, extra=["First"])
    page = page_reading(README, reads)
    said = only(problems_with(page), "page section `extra` has no row in "
                                     "HANDBOOK_READS")
    assert "changes when the page's structure does" in said
    assert "a section added is a row added" in said
    only(problems_with(page_reading(README), reads=reads),
         "HANDBOOK_READS has a row for `extra`, and the page has no section")


def test_the_table_names_only_segments_the_readme_has():
    reads = dict(READS, first=["First", "Nope"])
    only(problems_with(page_reading(README), reads=reads),
         "HANDBOOK_READS lists README.md § Nope for `first`")


def test_a_mapped_heading_is_in_its_own_sections_row():
    problems = problems_with(page_reading(README),
                             heading_to_id={"First": "second"})
    said = only(problems, "maps README.md § First to page section `second`")
    assert "`second`'s row in HANDBOOK_READS does not list it" in said


FIRST = marker("First", blobs_of(README)["First"])
PREAMBLE = marker("preamble", blobs_of(README)["preamble"])


@pytest.mark.parametrize("before, after, why", [
    (f"{PREAMBLE}\n\n{FIRST}\n", f"{PREAMBLE} {FIRST.strip()}\n",
     "shares its line"),
    (f'<section id="first">\n\n{FIRST}', f'<section id="first">\n{FIRST}',
     "has no blank line above it"),
    (f"{FIRST}\n\n  <p>What first says.</p>",
     f"{FIRST}\n  <p>What first says.</p>", "has no blank line below it"),
    (f"{FIRST}\n\n  <p>What first says.</p>",
     f"{FIRST} <p>What first says.</p>", "shares its line"),
])
def test_a_marker_stands_alone_between_blank_lines(before, after, why):
    """A marker beside page text conflicts with the pull request that
    rewords that text for another README section; two on one line conflict
    with each other. The review of PR #551 merged exactly that conflict."""
    page = page_reading(README)
    assert before in page
    said = only(problems_with(page.replace(before, after, 1)), why)
    assert "stands alone on its line, with a blank line above and below" \
        in said


@pytest.mark.parametrize("comment", [
    "<!-- read README.md § First: blob 0123 -->",
    "<!-- reads README.md § First: blob ABCDEF -->",
    "<!--reads README.md § First: blob "
    "ce013625030ba8dba906f756967f9e9ca394464a-->",
    "<!-- the README says so -->",
])
def test_a_mistyped_marker_is_refused_rather_than_skipped(comment):
    page = page_reading(README).replace("<p>What first says.</p>", comment)
    said = only(problems_with(page), "reads like a marker and is not one")
    assert comment in said and "docs/handbook.html:" in said


def test_a_marker_outside_every_page_section_is_refused():
    page = page_reading(README).replace("<!-- contents -->", FIRST.strip())
    only(problems_with(page), "§ First sits in no page section",
         "docs/handbook.html:1:")


def test_one_section_reads_one_segment_once():
    page = page_reading(README, dict(READS, first=["First", "First"]))
    only(problems_with(page), "page section `first` carries 2 markers for "
                              "README.md § First")


def test_two_segments_of_one_name_are_refused_and_offered_no_hash():
    readme = README + "\n## First\n\nAgain.\n"
    problems = problems_with(page_reading(README), readme)
    only(problems, "more than one segment called `First`")
    assert not [p for p in problems if "§ First has moved" in p], problems


# --------------------------------------------------------------- the footer

FOOTER = ('<footer id="licence"><p class="meta">First cut (#71); a row '
          "added (#97); the verdict added (#502). That\n      list is "
          "history, and it ends there.</p>\n<p class=\"meta\">Each section "
          "that reads the README records it (#519).</p></footer>")


def test_a_closed_footer_history_has_no_problem():
    assert handbook_footer_problems(FOOTER) == []


def test_a_clause_merged_into_the_history_before_it_closes_is_history():
    merged = FOOTER.replace("(#502). That", "(#502); a block added (#471). "
                                             "That")
    assert handbook_footer_problems(merged) == []


@pytest.mark.parametrize("retired", [
    "README.md blob ae817c5fdb324ff60440b959a15f3ad3b2a18b43",
    "README.md\n      blob ae817c5",
    "README.md blob AE817C5FDB324FF6",
])
def test_a_hash_of_the_whole_readme_is_refused_in_any_spelling(retired):
    said = only(handbook_footer_problems(FOOTER.replace(
        "</footer>", f"<p>{retired}</p></footer>")), "retired by #519")
    assert " ".join(retired.split()) in said


def test_an_added_clause_after_the_history_closes_is_refused():
    late = FOOTER.replace("records it (#519).",
                          "records it (#519); a section added (#560).")
    only(handbook_footer_problems(late), "adds ['added (#560)'] after the "
                                         "footer's history closed")


def test_the_history_closes_once():
    only(handbook_footer_problems(FOOTER.replace("it ends there", "it is")),
         "must close the footer's history once", "it does 0 times")


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
        "1001.txt": b"\xef\xbb\xbf+2\r\n2026-10-16\r\nPowerShell's BOM.\r\n",
    })
    raises, problems = readme_cap_raises(ledger)
    assert problems == []
    assert [(path.name, n) for path, n in raises] == [
        ("519.txt", 8), ("1000.txt", 3), ("1001.txt", 2)]
    assert readme_cap_sum(raises) == (
        f"{README_CAP_BASE} + 8 (519.txt) + 3 (1000.txt) + 2 (1001.txt) = "
        f"{README_CAP_BASE + 13}")


def test_dotfiles_and_editor_backups_are_not_read(tmp_path):
    ledger = write_ledger(tmp_path, {
        "519.txt": b"+8\n2026-10-14\nA good one.\n",
        ".DS_Store": b"\x00\x00\x00\x01Bud1",
        "519.txt~": b"old",
        ".519.txt.swp": b"\x00swap",
        "519.txt.bak": b"+80\n",
        "519.txt.orig": b"+80\n",
    })
    raises, problems = readme_cap_raises(ledger)
    assert problems == []
    assert [path.name for path, _ in raises] == ["519.txt"]


@pytest.mark.parametrize("name, data, fragment", [
    ("notes.md", b"+3\n2026-10-14\nr\n", "is not named `<issue or PR number>"),
    ("0519.txt", b"+3\n2026-10-14\nr\n", "is not named"),
    ("519.txt.new", b"+3\n2026-10-14\nr\n", "is not named"),
    ("520.txt", b"8\n2026-10-14\nr\n", "line 1 must be `+N`"),
    ("521.txt", b"+0\n2026-10-14\nr\n", "line 1 must be `+N`"),
    ("522.txt", b"", "line 1 must be `+N`"),
    ("523.txt", b"+3\n14 October 2026\nr\n", "line 2 must be"),
    ("524.txt", b"+3\n2026-02-30\nr\n", "line 2 must be"),
    ("525.txt", b"+3\n2026-10-14\n", "gives no reason"),
    ("526.txt", b"+3\n2026-10-14\n\n  \n", "gives no reason"),
    ("527.txt", b"+3\n2026-10-14\n\xff\n",
     "is not UTF-8 (invalid start byte at byte 14); save it as UTF-8 "
     "(PowerShell: Set-Content -Encoding utf8)"),
    ("528.txt", "+3\n2026-10-14\nr\n".encode("utf-16"),
     "is UTF-16; save it as UTF-8 (PowerShell: Set-Content -Encoding utf8)"),
    ("529.txt", "+3\n2026-10-14\nr\n".encode("utf-16-le"), "is UTF-16"),
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
                 "tests/readme-cap.d/519.txt", "UTF-8"):
        assert part in said, part
