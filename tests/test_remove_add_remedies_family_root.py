# SPDX-License-Identifier: Apache-2.0
"""A remedy that names `family.py remove` or `family.py add` names
`--family-root`, so the line runs as printed (#1005, which follows #927).

`remove` and `add` require `--family-root` (their usage lines, `family.py`'s
head), as `bump` does. #927 gave every remedy that names `bump` the holder;
three more named another verb without it. Typed as printed, each ended in
`family.py <verb>: error: the following arguments are required:
--family-root`:

* `add`'s `member-duplicate-id`, which says `remove` takes the old row out,
  and `bump`'s own `member-duplicate-id`, which says `remove` takes the other
  row out first. Both KNOW the holder, so each names it, in the one word
  `shell_quoted` makes of its path, as #927's `bump` line does.
* `bump`'s `member-unknown`, which says `add` puts the member in the family
  first. It names the holder the same way, and the owner `family.yaml`'s
  `org:` names (#1127; `tests/test_family_remedy_lines.py` has the rest).

Each case is measured two ways, over a holder in a plain folder, under two
with a space in their names (one of them with an apostrophe too: the paths a
shell would tear in half), reached by a RELATIVE `--family-root`, and
reached through a SYMLINK. The refused run names the holder as it likes; the
line it prints names the holder resolved, as ONE word. First, the printed
words are the holder whole and `family.py`'s own parser accepts them. Then
the line is RUN as printed, from a folder that is not the holder's, and does
what the remedy says it does: `remove` takes the row out and the refused act
then goes through; `add` pins the member the refused `bump` named.

The fixtures are the ones the tests of these codes already use:
`tests/test_family_add_member_id.py`'s renamed copy,
`tests/test_family_bump_to_checks.py`'s member that records its neighbour's
id, and `tests/test_family.py`'s family, whose spare member `IRQS` is in its
remotes and not in the holder. No network: `gh` is a shim that exits non-zero.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest

from conftest import git, run_script
from repo_shape import shell_quoted
#: The fixtures and helpers of the tests that already trigger these codes,
#: imported from the files that own them rather than rebuilt: a holder or a
#: member made any other way would test a different one.
from test_bump_remedies_family_root import (  # noqa: F401
    PLACES, family_module, parsed,
)
from test_family import (  # noqa: F401
    FAMILY, MEMBERS, ORG, SPARE, family, manifest, validate,
)
from test_family_add_member_id import RENAMED, renamed_copy
from test_family_add_refusals import offline  # noqa: F401
from test_family_bump_to_checks import records_the_neighbours_id
from test_family_dry_run import commit_in_mount, isolated
from test_family_member_path import MEMBER, OTHER
from test_family_printed_quoting import copied_holder, family_lead, host_words

#: A commit id for a `--to` that is never read: `member-unknown` is said
#: before `--to` is.
COMMIT = "0123456789abcdef0123456789abcdef01234567"

#: How the refused run reaches the holder: the three places a holder stands
#: (`test_bump_remedies_family_root.PLACES`), then a `--family-root` that is
#: RELATIVE to where the run stands, and one reached through a SYMLINK. The
#: line a remedy prints names the holder resolved, whichever it was.
REACHED = [*PLACES, "relative", pytest.param(
    "symlink", marks=pytest.mark.skipif(
        sys.platform == "win32",
        reason="a symbolic link needs privileges on Windows that a runner "
               "does not grant"))]


@dataclass(frozen=True)
class Reach:
    """A holder, and how a run that is refused is pointed at it."""

    holder: Path        # the holder, resolved: the path a remedy prints
    spec: str           # what that run's `--family-root` says
    cwd: Path | None    # where that run stands: None, anywhere


@pytest.fixture(params=REACHED)
def reach(request, family, tmp_path) -> Reach:
    """A private copy of the family's holder, clean, reached as
    `request.param` says."""
    where = request.param
    holder = copied_holder(
        family, tmp_path / (where if where in PLACES else "holders"))
    if where == "relative":
        return Reach(holder, holder.name, holder.parent)
    if where == "symlink":
        via = tmp_path / "via link"
        via.mkdir()
        (via / "the holder").symlink_to(holder, target_is_directory=True)
        assert (via / "the holder").resolve() == holder, "premise: a link"
        return Reach(holder, str(via / "the holder"), None)
    return Reach(holder, str(holder), None)


@pytest.fixture
def elsewhere(tmp_path) -> Path:
    """A folder that is not the holder's, which every printed line is typed
    from: its `--family-root` is the only thing that says where the holder
    is."""
    stand = tmp_path / "elsewhere"
    stand.mkdir()
    return stand


@dataclass(frozen=True)
class Case:
    """One refusal, the verb its remedy names, and how to tell the line
    does what the remedy says."""

    code: str
    verb: str                # the verb the remedy names
    member: str              # the `--member` its line carries
    refuse: Callable         # (reach, family, env, tmp_path) -> (stderr, kept)
    fill: Callable           # (line, kept) -> the line with its blanks filled
    extra: Callable          # (family, kept) -> arguments only a test adds
    mended: Callable         # (reach, family, env, kept) -> asserts the repair


def add_the_renamed_copy(reach, remotes, env):
    """`add` of the pinned member's copy under a new name, whose
    `project.yaml` records the id the row `IRRS` pins:
    `member-duplicate-id`."""
    return run_script(FAMILY, "add", "--family-root", reach.spec, "--member",
                      f"{ORG}/{RENAMED}", "--local-remote-dir", str(remotes),
                      cwd=reach.cwd, env=env)


def refuse_add_duplicate_id(reach, family, env, tmp_path):
    remotes = renamed_copy(family, tmp_path)
    return add_the_renamed_copy(reach, remotes, env).stderr, remotes


def mend_add_duplicate_id(reach, family, env, remotes):
    """The old row is out, and the `add` that was refused pins the project
    under its new name: one row records the id."""
    assert MEMBER not in {row["project"]
                          for row in manifest(reach.holder)["members"]}
    added = add_the_renamed_copy(reach, remotes, env)
    assert added.returncode == 0, added.stdout + added.stderr
    rows = {row["project"]: row for row in manifest(reach.holder)["members"]}
    assert sorted(rows) == sorted([RENAMED, *MEMBERS[1:]])
    assert [name for name, row in rows.items() if row["id"] == "irrs"] == [
        RENAMED]


def refuse_bump_duplicate_id(reach, family, env, tmp_path):
    """`bump` of `IRRS` to a commit whose `project.yaml` records the id of
    its neighbour `IRSS`: `member-duplicate-id`."""
    to = commit_in_mount(
        reach.holder, env, lambda mount: records_the_neighbours_id(
            mount / "project.yaml"))
    refused = run_script(FAMILY, "bump", "--family-root", reach.spec,
                         "--member", MEMBER, "--to", to, cwd=reach.cwd,
                         env=env)
    return refused.stderr, to


def mend_bump_duplicate_id(reach, family, env, to):
    """The other row is out, and the `bump` that was refused moves the row
    that is there."""
    assert OTHER not in {row["project"]
                         for row in manifest(reach.holder)["members"]}
    bumped = run_script(FAMILY, "bump", "--family-root", str(reach.holder),
                        "--member", MEMBER, "--to", to, env=env)
    assert bumped.returncode == 0, bumped.stdout + bumped.stderr
    rows = {row["project"]: row for row in manifest(reach.holder)["members"]}
    assert sorted(rows) == [MEMBER]
    assert rows[MEMBER]["pin"]["commit"] == to


def refuse_bump_unknown(reach, family, env, tmp_path):
    """`bump` of `IRQS`, which is in the family's remotes and not in the
    holder: `member-unknown`."""
    refused = run_script(FAMILY, "bump", "--family-root", reach.spec,
                         "--member", SPARE, "--to", COMMIT, cwd=reach.cwd,
                         env=env)
    return refused.stderr, None


def mend_bump_unknown(reach, family, env, kept):
    """The member the refused `bump` named is in the family now, under the
    row `add` writes."""
    rows = {row["project"]: row for row in manifest(reach.holder)["members"]}
    assert sorted(rows) == sorted([*MEMBERS, SPARE])
    assert rows[SPARE]["path"] == f"members/{SPARE}"
    assert rows[SPARE]["repository"] == f"{ORG}/{SPARE}"


CASES = {
    "add-member-duplicate-id": Case(
        "member-duplicate-id", "remove", MEMBER, refuse_add_duplicate_id,
        lambda line, kept: line, lambda family, kept: [],
        mend_add_duplicate_id),
    "bump-member-duplicate-id": Case(
        "member-duplicate-id", "remove", OTHER, refuse_bump_duplicate_id,
        lambda line, kept: line, lambda family, kept: [],
        mend_bump_duplicate_id),
    "bump-member-unknown": Case(
        "member-unknown", "add", f"{ORG}/{SPARE}", refuse_bump_unknown,
        lambda line, kept: line,
        # `add` reads the member from the family's own bare repositories,
        # as every `add` in this suite does: nothing here reaches a forge.
        lambda family, kept: ["--local-remote-dir", str(family["remotes"])],
        mend_bump_unknown),
}


def the_line(stderr: str, case: Case, reach: Reach) -> str:
    """The one `<verb> ...` the refusal prints, from the verb to the closing
    backtick, after the interpreter and the path to `family.py` from where
    the refused run stood (#1127), and the refusal checked to be the case's
    code."""
    assert f"REFUSED {case.code}: " in stderr, stderr
    lead = re.escape(f"`{family_lead(reach.cwd)}")
    found = re.findall(rf"{lead}({case.verb} [^`]*)`", stderr)
    assert len(found) == 1, stderr
    return found[0]


def expected(case: Case, reach: Reach) -> str:
    return (f"{case.verb} --family-root {shell_quoted(reach.holder)} "
            f"--member {case.member}")


@pytest.mark.parametrize("case", CASES.values(), ids=CASES)
def test_the_line_a_remedy_names_carries_the_holder_whole(
        case, family, reach, offline, tmp_path):
    """The line is `<verb> --family-root <holder> --member <name>`, and the
    holder is ONE word that is the holder's own path, as the host's shell
    reads it, however many spaces and apostrophes it has and however the
    refused run was pointed at it."""
    stderr, kept = case.refuse(reach, family, isolated(offline, tmp_path),
                               tmp_path)
    line = the_line(stderr, case, reach)
    assert line == expected(case, reach)
    assert host_words(line) == [case.verb, "--family-root",
                                str(reach.holder), "--member", case.member]


@pytest.mark.parametrize("case", CASES.values(), ids=CASES)
def test_the_line_a_remedy_names_parses(
        case, family, reach, offline, tmp_path, family_module, capsys):
    """Fed to `family.py`'s own parser, with `<org>` filled in, the printed
    words are accepted: no `the following arguments are required`."""
    stderr, kept = case.refuse(reach, family, isolated(offline, tmp_path),
                               tmp_path)
    words = host_words(case.fill(the_line(stderr, case, reach), kept))
    capsys.readouterr()
    args = parsed(family_module, words, capsys)
    assert args.family_root == str(reach.holder)
    assert args.member == case.fill(case.member, kept)
    assert args.func is getattr(family_module, f"cmd_{case.verb}")


@pytest.mark.parametrize("case", CASES.values(), ids=CASES)
def test_the_line_a_remedy_names_runs_as_printed_and_does_what_it_says(
        case, family, reach, elsewhere, offline, tmp_path):
    """The remediation is the repair. Typed as printed, from a folder that
    is not the holder's, the line exits 0 and leaves the holder clean and
    its own gate green, and the refused act then goes through, or the member
    is in the family: whichever the remedy says it is for."""
    env = isolated(offline, tmp_path)
    stderr, kept = case.refuse(reach, family, env, tmp_path)
    words = host_words(case.fill(the_line(stderr, case, reach), kept))
    done = run_script(FAMILY, *words, *case.extra(family, kept),
                      cwd=elsewhere, env=env)
    assert "the following arguments are required" not in done.stderr
    assert done.returncode == 0, done.stdout + done.stderr
    assert git("status", "--porcelain", cwd=reach.holder).stdout == ""
    assert validate(reach.holder).returncode == 0
    case.mended(reach, family, env, kept)
    assert git("status", "--porcelain", cwd=reach.holder).stdout == ""
    assert validate(reach.holder).returncode == 0
