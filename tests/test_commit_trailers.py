# SPDX-License-Identifier: Apache-2.0
"""The commit trailers both writing tools take, and the lane a printed next
command offers (#111).

`update-shape.py apply --branch` and `scripts/family.py bump` compose their
own commit messages, so a `Lane:` line — which the lane-collision protocol
wants on every artifact a lane produces, the COMMIT included — reaches one
only through `--trailer`. What a trailer IS, whether this host's git takes the
commit option, and which environment variable names the lane are one
implementation in `scripts/shape_materialize.py`, imported by both tools;
those rules are what this file holds. Each tool's own end-to-end run is in
`tests/test_update_shape.py` and `tests/test_family.py`, and the doctor's
printed row is in `tests/test_shape_doctor.py`.

NO NETWORK, like the rest of the suite: the one test that makes real commits
makes them in a repository `git init` creates in a temporary directory.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

import pytest

from conftest import REPO, git

sys.path.insert(0, str(REPO / "scripts"))
from shape_materialize import (  # noqa: E402
    TRAILER_OPTION_SINCE, commit_trailers, git_takes_trailer_option,
    lane_trailer, lane_trailer_argument, trailer_line,
)

#: The two lines a lane's run lands, exactly as the protocol spells them.
LANE = "openreposhape-2 (openRepoShape-2)"
TRAILERS = (f"Lane: {LANE}",
            "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>")

#: One base message shaped like the two the tools compose: a subject, a blank
#: line, two prose paragraphs, and a trailing newline. The last paragraph is
#: PROSE on purpose — that is what makes the trailers a new block rather than
#: additions to one git already recognises.
BASE = ("Re-sync the shape copies to opensoft/openRepoShape @ 32450eb5c5d1\n"
        "\n1 copied file(s) re-copied from the upstream.\n"
        "\nWritten by a tool; the digests are recomputed, not adjusted.\n")


def message_of(root) -> str:
    """The commit message of HEAD, with the newline `git log` adds removed.

    `--format=%B` prints the message, which itself ends in a newline, and
    then git ends the record with one of its own. Dropping exactly that one
    is what lets a test compare the message to the bytes the tool composed —
    the property this whole file is about is a message ENDING in particular
    lines, which a test that strips whitespace cannot see at all.
    """
    out = git("log", "-1", "--format=%B", cwd=root).stdout
    return out[:-1] if out.endswith("\n") else out


def trailers_of(root) -> list[str]:
    """The trailer block AS GIT READS IT, which is the claim that matters: a
    line that merely looks like a trailer in the message text is not one to
    `git interpret-trailers`, and `Co-Authored-By:` is read by forges off
    exactly this.

    The block git prints ends in a newline and git ends the record with one
    of its own, so a bare `splitlines()` reports an empty trailer that is
    really the format's own punctuation — and a commit with NO trailers is
    `[""]` rather than `[]`, which is a list a test would read as one line.
    """
    out = git("log", "-1", "--format=%(trailers:only=true)", cwd=root).stdout
    return out.strip("\n").splitlines() if out.strip() else []


# --- the grammar ------------------------------------------------------------

@pytest.mark.parametrize("value", [
    "Lane: xfactory-1",
    f"Lane: {LANE}",
    "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>",
    "Signed-off-by: A Human <human@example.invalid>",
    "X: y",
    "Reviewed-By: someone, and someone else",
])
def test_the_grammar_accepts_a_trailer_somebody_would_actually_write(value):
    """Git's own trailer shape: a token, a colon, one space, a value."""
    assert trailer_line(value) == value


@pytest.mark.parametrize("value", [
    "Lane xfactory-1",          # no colon at all
    "Lane:xfactory-1",          # no space after the colon
    "Lane : xfactory-1",        # a space BEFORE the colon
    "Lane: ",                   # no value
    "Lane:",
    "",
    ": xfactory-1",             # no token
    "-Lane: xfactory-1",        # a token that does not start with a letter
    "Lane: trailing ",          # trailing whitespace in the value
    "Lane: two\nlines",         # a second line, which would forge a trailer
    # THE `.match` + `$` HOLE (Copilot, PR #112). A pattern ending in `$`
    # stops just before a FINAL newline, so this was accepted whole and the
    # newline went into the commit message and into argv.
    "Lane: x\n",
    "Lane: x\r\n",
    # AND "one line" IS NOT "no `\n`". Each of these is a line break to some
    # reader, and `[^\n]` in the middle of the pattern admitted all of them.
    "Lane: a\rb",
    "Lane: a\x0bb",
    "Lane: a\x0cb",
    "Lane: a\tb",
    "Lane: x\x7f",
    "Lane: a\x00b",
])
def test_the_grammar_refuses_a_line_that_is_not_a_trailer(value):
    """Refused where argparse can say so, with the usage line beside it.

    THE NEWLINE CASES ARE THE ONES WITH TEETH: a value carrying one puts a
    line of its own into somebody else's commit message, which is a trailer
    nobody passed — and the trailing one got through `re.match` entirely,
    because `$` matches just before a final newline (Copilot, PR #112; the
    same lesson `shape-doctor.py`'s `quote_arg` took on PR #102 against
    `"Atlas\\n"`). Both halves of the fix are asserted here: `.fullmatch`,
    and classes that admit no control character.
    """
    with pytest.raises(argparse.ArgumentTypeError):
        trailer_line(value)


# --- which git this is ------------------------------------------------------

@pytest.mark.parametrize("line,takes", [
    ("git version 2.43.0", True),
    ("git version 2.32.0", True),               # the release that gained it
    ("git version 2.31.1", False),              # the one before
    ("git version 2.45.1.windows.1", True),
    ("git version 2.39.3 (Apple Git-146)", True),
    ("git version 3.0.0", True),
    ("git version 1.9.5", False),
    ("git version", False),                     # nothing to read
    ("", False),
    ("not a git at all", False),
    ("2.43.0", False),                          # unanchored would match this
])
def test_the_version_probe_reads_the_commit_option_off_the_version_line(
        line, takes):
    """Conservative both ways: anything unparseable reads as "no", and "no"
    is the path that works on every git there is."""
    assert git_takes_trailer_option(line) is takes


def test_the_probe_asked_for_a_version_touches_no_cache():
    """`version=` is the parse, exposed — the same thing
    `shape-doctor.py`'s `platform=` does for its quoter, and for the same
    reason: a branch that can only run on one machine is a branch nothing
    checks. Asking for one must not decide the answer for this process."""
    before = git_takes_trailer_option()
    assert git_takes_trailer_option("git version 1.0.0") is False
    assert git_takes_trailer_option("git version 9.9.9") is True
    assert git_takes_trailer_option() is before


def test_the_option_arrived_in_2_32():
    """Spelled here rather than imported into the assertion: 2.32 is a fact
    about git (2021-06-06), and a test that read the constant would agree
    with a typo in it."""
    assert TRAILER_OPTION_SINCE == (2, 32)


# --- what the tools are handed ---------------------------------------------

def test_no_trailers_is_the_message_unchanged_and_no_arguments():
    """The byte-identity that keeps every commit these tools have already
    written exactly as it was: passed nothing, this returns the message it
    was given and an empty argument list, so the `git commit` argv is the
    one the tool always built."""
    assert commit_trailers(BASE) == (BASE, [])
    assert commit_trailers(BASE, []) == (BASE, [])
    assert commit_trailers(BASE, ()) == (BASE, [])


def test_the_commit_option_is_used_where_git_has_it(monkeypatch):
    monkeypatch.setattr("shape_materialize.git_takes_trailer_option",
                        lambda: True)
    message, args = commit_trailers(BASE, list(TRAILERS))
    assert message == BASE, "git appends them; the message is untouched"
    assert args == ["--trailer", TRAILERS[0], "--trailer", TRAILERS[1]]


def test_the_text_fallback_appends_the_lines_after_one_blank_line(monkeypatch):
    monkeypatch.setattr("shape_materialize.git_takes_trailer_option",
                        lambda: False)
    message, args = commit_trailers(BASE, list(TRAILERS))
    assert args == [], "a git without the option is asked for nothing"
    assert message == BASE + "\n" + "\n".join(TRAILERS) + "\n"
    assert message.endswith(f"\n{TRAILERS[0]}\n{TRAILERS[1]}\n")


def test_the_fallback_supplies_the_newline_a_message_is_missing(monkeypatch):
    monkeypatch.setattr("shape_materialize.git_takes_trailer_option",
                        lambda: False)
    message, _args = commit_trailers("No trailing newline", ["Lane: x"])
    assert message == "No trailing newline\n\nLane: x\n"


@pytest.mark.skipif(not git_takes_trailer_option(),
                    reason="this host's git predates `commit --trailer` "
                           "(2.32), so only the fallback path can run here")
def test_both_paths_write_the_same_commit_message(tmp_path, monkeypatch):
    """THE CLAIM THE FALLBACK RESTS ON, asserted rather than believed.

    `commit --trailer` runs the message through `interpret-trailers`, which
    knows where a trailer block goes; appending the lines to the text is this
    module doing that job for a git that cannot. The two are only
    interchangeable if the commit that comes out is the same one — so both
    are written here, into one real repository, and compared.
    """
    root = tmp_path / "either-way"
    root.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=root)
    identity = ["-c", "user.name=t", "-c", "user.email=t@t.invalid"]

    def commit(name: str, message: str, extra: list[str]) -> str:
        (root / name).write_text("x\n", encoding="utf-8")
        git("add", "--", name, cwd=root)
        proc = subprocess.run(
            ["git", *identity, "commit", "-q", "-F", "-", *extra, "--", name],
            cwd=str(root), input=message, capture_output=True, text=True,
            check=False)
        assert proc.returncode == 0, proc.stderr + proc.stdout
        return message_of(root)

    monkeypatch.setattr("shape_materialize.git_takes_trailer_option",
                        lambda: True)
    option_message, option_args = commit_trailers(BASE, list(TRAILERS))
    through_git = commit("a", option_message, option_args)

    monkeypatch.setattr("shape_materialize.git_takes_trailer_option",
                        lambda: False)
    text_message, text_args = commit_trailers(BASE, list(TRAILERS))
    by_hand = commit("b", text_message, text_args)

    assert through_git == by_hand
    assert by_hand.endswith(f"\n{TRAILERS[0]}\n{TRAILERS[1]}\n")
    assert trailers_of(root) == list(TRAILERS), (
        "and git reads them back as the trailer block, in order")


# --- the lane a printed next command offers --------------------------------

def test_the_lane_comes_from_the_environment_and_is_a_trailer():
    assert lane_trailer({"LANES_LANE": LANE}) == f"Lane: {LANE}"
    assert trailer_line(lane_trailer({"LANES_LANE": LANE}))


@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_an_unset_or_blank_lane_is_no_lane(value):
    """And the caller then prints nothing, which is what keeps every line
    this standard printed yesterday byte-identical for everybody who is not
    in a lane."""
    assert lane_trailer({"LANES_LANE": value}) is None
    assert lane_trailer({}) is None
    assert lane_trailer_argument(env={"LANES_LANE": value}) == ""
    assert lane_trailer_argument(env={}) == ""


@pytest.mark.parametrize("value", [
    'say "hello"',          # the quote the default spelling uses
    "O'Brien",              # the quote both of the doctor's spellings use
    "back`tick",
    "dollar$sign",
    "back\\slash",
    "two\nlines",
])
def test_a_lane_name_that_could_not_be_pasted_is_not_offered(value):
    """A next command is a line somebody copies into a shell, and the
    trailer inside it is quoted by whoever prints it — so a name carrying
    that quote character would break the very quoting it sits inside, in
    front of whoever pasted it. Offering nothing is the honest answer;
    `--trailer` typed by hand still takes anything the grammar accepts."""
    assert lane_trailer({"LANES_LANE": value}) is None
    assert lane_trailer_argument(env={"LANES_LANE": value}) == ""


@pytest.mark.parametrize("raw", [
    "xfactory-1\n",            # the shape `LANES_LANE=$(cat …)` produces
    "xfactory-1\r\n",
    "xfactory-1 ",
    " xfactory-1",
    "xfactory-1\t",
])
def test_a_lane_name_with_whitespace_around_it_is_not_a_lane_name(raw):
    """CHECKED RAW, NOT STRIPPED (Copilot, PR #112).

    Asking the alphabet about a `.strip()`ed name meant
    `LANES_LANE="xfactory-1\\n"` was offered as `Lane: xfactory-1`: a name
    the contract says is not offered, trimmed into one that is, with nothing
    said. It is decided the other way on purpose — a value with whitespace
    around it is not a lane name — because `TRAILER_RE` refuses a value that
    starts or ends in whitespace, and a printed line offering a trailer this
    tool's own `--trailer` would then refuse is worse than one offering none.
    """
    assert lane_trailer({"LANES_LANE": raw}) is None
    assert lane_trailer_argument(env={"LANES_LANE": raw}) == ""


def test_a_lane_that_is_offered_is_a_trailer_the_tool_would_accept():
    """THE INVARIANT THE TWO RULES EXIST TO KEEP, asserted directly: every
    lane line a printed next command offers must be one `--trailer` would
    take, or the line hands somebody a command that refuses itself."""
    for raw in ["xfactory-1", LANE, "openreposhape-2", "a/b (c) @ d",
                "x" * 200]:
        offered = lane_trailer({"LANES_LANE": raw})
        assert offered is not None, raw
        assert trailer_line(offered) == offered


def test_the_printed_argument_is_spelled_by_the_callers_own_quoter():
    """`quote` is passed in rather than chosen here: `shape-doctor.py` hands
    over its platform-aware `quote_arg`, because every other value on those
    rows is spelled by that one function and a line half-quoted by two rules
    is a line no shell reads the way its writer meant."""
    env = {"LANES_LANE": LANE}
    assert lane_trailer_argument(env=env) == \
        f' --trailer "Lane: {LANE}"'
    assert lane_trailer_argument(lambda value: "<" + value + ">", env) == \
        f" --trailer <Lane: {LANE}>"


def test_the_lane_line_is_the_only_thing_derived_from_the_environment():
    """`Co-Authored-By:` names a person or a model, which no environment
    variable knows — so a tool that added one would be putting a name nobody
    chose on somebody else's commit. It is the caller's to pass."""
    offered = lane_trailer_argument(env={"LANES_LANE": LANE})
    assert offered.count("--trailer") == 1
    assert "Co-Authored-By" not in offered
