# SPDX-License-Identifier: Apache-2.0
"""A hand-edited `path:` is `member-path`, and nothing is read through it
(#367); `recorded_gitlink` takes its path literally, for every caller.

THREE THINGS COMBINED. `_check_member` found a row's `path:` wrong, recorded
`member-path`, and then went on to check the member's gitlink, tree and
identity AT that path. `recorded_gitlink` handed the path to `git ls-files`
as a pathspec, so `members/*` was a glob and answered with the first
member's gitlink, gathered as a false `member-gitlink-mismatch` for this
one. The tree check then refused `member-uninitialized`, whose remedy (`git
submodule update --init`, `make bootstrap`) cannot help, and a refusal
prints none of the findings gathered before it, so the one naming the hand
edit was never seen.

Two of the issue's three decisions are taken. A row whose path is wrong
stops after its pin is read, and the finding names the one path it may
have. `recorded_gitlink` passes git's global `--literal-pathspecs` to both
of its listings, never `:(literal)` magic, which a caller's exported
`GIT_LITERAL_PATHSPECS=1` turns off; and the two pathspec settings git
refuses beside that option are kept out of those two calls, so a caller who
exports one does not read every gitlink as absent. The third decision, a
refusal that prints the findings gathered before it, is not taken.

The row's own mount is then a gitlink and a section no row names (#361,
`tests/test_validate_family_unnamed_mounts.py`), reported beside
`member-path`: the row names the path it gives, as written.

The same family and offline rules as `tests/test_family.py`. The hand edit
is to `family.yaml` alone, written as bytes; nothing named `*` is ever put
on disk, so every test here runs on Windows too.
"""

from __future__ import annotations

import pytest

from conftest import run_script
from repo_shape import recorded_gitlink
from test_family import family, holder, manifest, validate  # noqa: F401

#: What a hand edit can leave in IRSS's `path:`, from the issue: globs,
#: pathspec magic, a `..` and a trailing slash. Each is `member-path`.
SPELLINGS = ["members/*", "members/I*", "members/[I]*", ":(glob)members/IRSS",
             "members/IRSS/..", "members/IRSS/"]


def hand_edit(holder, spelling: str) -> None:
    """IRSS's row given `path: "<spelling>"`, as BYTES, so Windows does not
    rewrite the manifest with CRLF."""
    manifest_path = holder / "family.yaml"
    text = manifest_path.read_bytes()
    line = b"    path: members/IRSS\n"
    assert text.count(line) == 1, "fixture drift: IRSS's path line"
    manifest_path.write_bytes(text.replace(
        line, f'    path: "{spelling}"\n'.encode("utf-8")))


def codes(result) -> list[str]:
    return [line.split(":", 1)[0][len("FINDING "):]
            for line in result.stderr.splitlines()
            if line.startswith("FINDING ")]


def gitlinks(holder) -> dict[str, str]:
    return {row["project"]: row["pin"]["commit"]
            for row in manifest(holder)["members"]}


@pytest.mark.parametrize("extra", [(), ("--pins",)],
                         ids=["members-checked", "pins"])
@pytest.mark.parametrize("spelling", SPELLINGS)
def test_a_hand_edited_path_is_member_path_and_nothing_read_through_it(
        holder, spelling, extra):
    """THE ISSUE'S REPRO, in both modes that check members: the run used to
    end in `REFUSED member-uninitialized`, exit 2, with the `member-path`
    finding and a false `member-gitlink-mismatch` gathered and dropped. Now
    `member-path` is printed, naming the one path the row may have, nothing
    is read at the path the row gives, and the run is a finding, exit 1.
    IRSS's own mount is then a gitlink and a section no row names (#361),
    and nothing else is said."""
    hand_edit(holder, spelling)
    result = validate(holder, *extra)
    assert result.returncode == 1, result.stderr + result.stdout
    assert "REFUSED" not in result.stderr, result.stderr
    assert "member-uninitialized" not in result.stderr
    assert "member-gitlink-mismatch" not in result.stderr
    assert codes(result) == ["member-gitlink-unnamed",
                             "gitmodules-path-unnamed", "member-path"]
    assert (f"FINDING member-path: IRSS: path is {spelling!r}, expected "
            "'members/IRSS', the one path a row for IRSS may have. Its "
            "gitlink, digest and project id are not checked through any "
            "other.") in result.stderr.splitlines()


def test_the_other_rows_are_still_checked(holder):
    """Only the edited row stops: IRRS's gitlink, digest and id are read as
    before, and say so."""
    hand_edit(holder, "members/*")
    result = validate(holder)
    assert "  ok  members/IRRS: gitlink == pin" in result.stdout
    assert "  ok  members/IRRS: project.yaml id irrs" in result.stdout
    assert "members/IRSS: gitlink" not in result.stdout


@pytest.mark.parametrize("spelling", ["members/*", "members/I*",
                                      "members/[I]*", ":(glob)members/IRRS"])
def test_recorded_gitlink_takes_its_path_literally(holder, spelling):
    """In a holder with members, and no file named `*` on disk, a glob or a
    magic pathspec names no entry, so there is no gitlink there; the
    member's own path still answers with its pin. The standard's
    `repo_shape.py` is the one under test: every holder and every project
    receives a copy of it."""
    pins = gitlinks(holder)
    assert not any("*" in entry.name
                   for entry in (holder / "members").iterdir())
    assert recorded_gitlink(holder, spelling) is None
    assert recorded_gitlink(holder, "members/IRRS") == pins["IRRS"]


@pytest.mark.parametrize("variable", [
    "GIT_GLOB_PATHSPECS", "GIT_ICASE_PATHSPECS", "GIT_LITERAL_PATHSPECS",
    "GIT_NOGLOB_PATHSPECS"])
def test_a_callers_pathspec_setting_neither_widens_nor_breaks_it(
        holder, monkeypatch, variable):
    """git refuses `--literal-pathspecs` beside an exported
    `GIT_GLOB_PATHSPECS` or `GIT_ICASE_PATHSPECS` (exit 128), and a listing
    git refused reads as no gitlink, so those two are kept out of the
    listings' environment: the gitlink is found, and a glob still finds
    none. `GIT_LITERAL_PATHSPECS`, which turns `:(literal)` magic off, and
    `GIT_NOGLOB_PATHSPECS` change nothing either. The holder's own gate,
    run with the variable exported, passes."""
    monkeypatch.setenv(variable, "1")
    pins = gitlinks(holder)
    assert recorded_gitlink(holder, "members/IRRS") == pins["IRRS"]
    assert recorded_gitlink(holder, "members/*") is None
    result = run_script(holder / "scripts" / "validate-family.py", "--pins",
                        cwd=holder, env={variable: "1"})
    assert result.returncode == 0, result.stderr + result.stdout
