# SPDX-License-Identifier: Apache-2.0
"""A remedy that names `family.py bump` names `--family-root`, so the line
runs as printed (#927).

`bump` requires `--family-root` (its usage line, `family.py`'s head). Three
remedies named the verb without it, and typed as printed each ended in
`family.py bump: error: the following arguments are required: --family-root`:

* `member-already-present`, which `add` says of a member the holder already
  pins, and `member-duplicate-id`, which `add` says of a member that records
  an id another row records. Both KNOW the holder, so each names it, in the
  one word `shell_quoted` makes of its path, as `add`'s own line does.
* `bump-leg-assembly-is-not-a-leg`, which says a family's member pin moves
  with `family.py bump`. `bump-leg.py` has no holder to name, so it says
  `<holder>`, the way it says `<Project>` and `<sha>`.

Each family case is measured three ways, in a holder under a plain folder and
under two with a space and an apostrophe in their names (the paths a shell
would tear in half): the line names the holder as ONE word that comes back as
the holder, `family.py`'s own parser accepts it, and it is RUN as printed and
moves the pin. The `bump-leg.py` line is read the same way once its three
placeholders are filled in.

The fixtures are the ones the tests of these codes already use:
`tests/test_family.py`'s family, `tests/test_family_add_member_id.py`'s
renamed copy and `tests/test_bump_leg.py`'s project. No network: `gh` is a
shim that exits non-zero.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from conftest import git, run_script
from repo_shape import shell_quoted
#: The fixtures and helpers of the tests that already trigger these codes,
#: imported from the files that own them rather than rebuilt: a holder or a
#: project made any other way would test a different one.
from test_bump_leg import advanced, branched, bump  # noqa: F401
from test_family import FAMILY, family, manifest  # noqa: F401
from test_family_add_member_id import PINNED, RENAMED, renamed_copy
from test_family_add_refusals import offline  # noqa: F401
from test_family_printed_quoting import copied_holder, host_words

#: Where the holder stands: a folder a shell reads whole, one with a space,
#: and one with a space beside an apostrophe, where `sh` and PowerShell
#: escape differently.
PLACES = ["plain", "my work", "Dana's work"]


@pytest.fixture(params=PLACES)
def placed(request, family, tmp_path) -> Path:
    """A private copy of the family's holder, clean, under `request.param`."""
    base = tmp_path / ("holders" if request.param == "plain"
                       else request.param)
    return copied_holder(family, base)


@pytest.fixture(scope="module")
def family_module():
    """`family.py` as a module, for its own argument parser."""
    spec = importlib.util.spec_from_file_location("family_bump_remedies",
                                                  FAMILY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def already_present(family, holder, offline, tmp_path):
    """`add` of the member the holder already pins: `member-already-present`
    (the case `tests/test_family.py` refuses)."""
    return offline.add(holder, PINNED, remotes=family["remotes"])


def duplicate_id(family, holder, offline, tmp_path):
    """`add` of a copy of the pinned member under a new name, whose
    `project.yaml` records the id the row `IRRS` pins: `member-duplicate-id`
    (the case `tests/test_family_add_member_id.py` refuses)."""
    return offline.add(holder, RENAMED,
                       remotes=renamed_copy(family, tmp_path))


#: Each code, and the `add` that is refused with it.
CASES = {"member-already-present": already_present,
         "member-duplicate-id": duplicate_id}


def refused_as(code, family, holder, offline, tmp_path):
    """The stderr of the `add` that `code` refuses, checked to be it and
    exit 2."""
    result = CASES[code](family, holder, offline, tmp_path)
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"REFUSED {code}: " in result.stderr
    return result.stderr


def the_bump_line(stderr: str, lead: str = "") -> str:
    """The one `family.py bump ...` a remedy prints, from `bump` to the
    closing backtick, with `lead` before `family.py` (a path, for
    `bump-leg.py`'s)."""
    found = re.findall(re.escape(f"`{lead}family.py ") + r"(bump [^`]*)`",
                       stderr)
    assert len(found) == 1, stderr
    return found[0]


def parsed(family_module, words, capsys):
    """What `family.py`'s own parser makes of `words`; a failure to parse is
    the failure, said in argparse's own words."""
    try:
        return family_module.build_parser().parse_args(words)
    except SystemExit:
        pytest.fail(f"family.py {' '.join(words)}\n"
                    + capsys.readouterr().err)


@pytest.mark.parametrize("code", CASES)
def test_the_bump_a_remedy_names_carries_the_holder_whole(
        code, family, placed, offline, tmp_path):
    """The line is `bump --family-root <holder> --member IRRS --to
    <commit>`, and the holder is ONE word that is the holder's own path, as
    the host's shell reads it, however many spaces and apostrophes it has."""
    stderr = refused_as(code, family, placed, offline, tmp_path)
    line = the_bump_line(stderr)
    assert line == (f"bump --family-root {shell_quoted(placed)} "
                    f"--member {PINNED} --to <commit>")
    assert host_words(line) == ["bump", "--family-root", str(placed),
                                "--member", PINNED, "--to", "<commit>"]


@pytest.mark.parametrize("code", CASES)
def test_the_bump_a_remedy_names_parses(
        code, family, placed, offline, tmp_path, family_module, capsys):
    """Fed to `family.py`'s own parser, with a commit for `<commit>`, the
    printed words are accepted: no `the following arguments are required`."""
    stderr = refused_as(code, family, placed, offline, tmp_path)
    commit = "0123456789abcdef0123456789abcdef01234567"
    words = host_words(the_bump_line(stderr).replace("<commit>", commit))
    capsys.readouterr()
    args = parsed(family_module, words, capsys)
    assert args.family_root == str(placed)
    assert args.member == PINNED
    assert args.to == commit
    assert args.func is family_module.cmd_bump


@pytest.mark.parametrize("code", CASES)
def test_the_bump_a_remedy_names_runs_as_printed(
        code, family, placed, offline, tmp_path):
    """The remediation is the repair. Typed as printed, with a real commit
    of the member for `<commit>`, `bump` moves the row that is there: exit 0,
    the pin at that commit, and the holder clean."""
    stderr = refused_as(code, family, placed, offline, tmp_path)
    older = git("rev-parse", "main~1",
                cwd=family["remotes"] / f"{PINNED}.git").stdout.strip()
    words = host_words(the_bump_line(stderr).replace("<commit>", older))
    done = run_script(FAMILY, *words, env=offline.env)
    assert "the following arguments are required" not in done.stderr
    assert done.returncode == 0, done.stdout + done.stderr
    rows = {row["project"]: row for row in manifest(placed)["members"]}
    assert rows[PINNED]["pin"]["commit"] == older
    assert git("status", "--porcelain", cwd=placed).stdout == ""


def test_the_assembly_remedy_of_bump_leg_names_the_holder(
        project, scaffolded, advanced, family_module, capsys):
    """`bump-leg.py` has no holder to name, so the line it prints says
    `<holder>` as it says `<Project>` and `<sha>`: the remedy for `--leg
    assembly` names `--family-root`, and with its three placeholders filled
    in, `family.py`'s own parser accepts it."""
    branched(project)
    result = bump(project, scaffolded, advanced, leg="assembly")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED bump-leg-assembly-is-not-a-leg: " in result.stderr
    line = the_bump_line(result.stderr, "scripts/")
    assert line == "bump --family-root <holder> --member <Project> --to <sha>"
    filled = (line.replace("<holder>", str(project.parent))
              .replace("<Project>", PINNED).replace("<sha>", advanced))
    capsys.readouterr()
    args = parsed(family_module, host_words(filled), capsys)
    assert args.family_root == str(project.parent)
    assert args.member == PINNED
    assert args.to == advanced
