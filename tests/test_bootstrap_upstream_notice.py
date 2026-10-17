# SPDX-License-Identifier: Apache-2.0
"""The assembly root's offline upstream notice says nothing where it cannot
read an answer, and never ends `make bootstrap` in a traceback (#764, C1).

THE DEFECT, measured on lane 5's #745 head (f4935e11, Python 3.12.3, git
2.43.0) in a scaffold's recursive clone whose validators all pass:

- `SHAPE_UPSTREAM_PATH` set to a directory this process may not enter ended
  `bootstrap.py` in a `PermissionError` traceback, exit 1. `subprocess`
  raised it for the `cwd` of `git rev-parse HEAD`, naming the directory,
  which `_git_runs` passes on as not git's (#694).
- Set to a directory UNDER one, `Path.is_dir` raised it, as Python 3.12 and
  3.13 do (3.14 answers False there instead).
- A `.shape-upstream-tip` this process may not read ended the same way, and
  one whose bytes are not UTF-8 in a `UnicodeDecodeError`.
- A `contracts/shape-pin.yaml` that is a list ended in an `AttributeError`,
  after `validate-pins.py` had refused it (`shape-pin-unreadable`).
- A `contracts/` this process may not enter ended in a `PermissionError`
  from the notice's own `is_file`, after the validators.
- A `SHAPE_UPSTREAM_PATH` over the longest name or path the system takes
  ended in an `OSError` (`ENAMETOOLONG`) traceback, where Python 3.12 and
  3.13 raise it from `Path.is_dir` too (3.14 answers False).

The notice's docstring says it is silent where it cannot answer and never
fails the bootstrap; the issue's goal is that `make bootstrap` never ends in
a traceback over it.

THE RULE NOW. Each is an absent answer: the notice says nothing, the run
ends as its validators end it, and a clone that cannot be read leaves the
cache to answer, as a missing one does. A git that cannot be STARTED is
still `git-not-runnable`, exit 2 (`tests/test_bootstrap_without_git.py`).

A mode nobody may enter is POSIX's: root reads through it and Windows has no
such mode, so those cases skip there.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from conftest import REPO, load_without_bytecode, run_script

#: A commit the cache can name that no scaffold is pinned at.
TIP = "0123456789abcdef0123456789abcdef01234567"
#: The first words of the notice's one line, over `TIP`.
NOTICE = (f"  shape: the upstream is at {TIP[:12]} and this project is "
          "pinned at ")
#: Where a mode of 000 keeps this process out.
LOCKED_OUT = pytest.mark.skipif(
    os.name == "nt" or os.geteuid() == 0,
    reason="a mode of 000 keeps neither root nor a Windows process out")


def bootstrap(root: Path, upstream: str = ""):
    """`scripts/bootstrap.py` in `root`, the validators included, with
    `SHAPE_UPSTREAM_PATH` set to `upstream` (empty: no clone named)."""
    return run_script(root / "scripts" / "bootstrap.py", cwd=root,
                      env={"SHAPE_UPSTREAM_PATH": upstream})


def ends_ok(result) -> None:
    """Exit 0, no traceback, and `bootstrap ok` the last line."""
    assert result.returncode == 0, result.stderr + result.stdout
    assert "Traceback" not in result.stderr, result.stderr
    assert result.stdout.endswith("\nbootstrap ok\n"), result.stdout


@pytest.fixture
def locked(tmp_path):
    """A directory nobody may list or enter, holding a directory of its own
    (`openRepoShape`). Its mode is given back afterwards, so the basetemp
    can be removed."""
    folder = tmp_path / "locked"
    (folder / "openRepoShape").mkdir(parents=True)
    folder.chmod(0)
    yield folder
    folder.chmod(0o700)


@LOCKED_OUT
@pytest.mark.parametrize("under", [False, True],
                         ids=["the directory", "a directory under it"])
def test_an_upstream_path_nobody_may_enter_is_an_absent_answer(project,
                                                               locked, under):
    """THE ISSUE'S CASE, and its `is_dir` half: exit 0, no traceback, no
    notice."""
    upstream = locked / "openRepoShape" if under else locked
    result = bootstrap(project, str(upstream))
    ends_ok(result)
    assert "  shape:" not in result.stdout, result.stdout


def over_long_name(folder: Path) -> str:
    """A name of 300 characters, over the 255 every system here takes."""
    return f"{folder}/{'a' * 300}"


def over_long_path(folder: Path) -> str:
    """A path of over 5000 characters in names of 49, over the 4096 Linux
    takes (and macOS's 1024)."""
    return str(folder) + ("/" + "a" * 49) * 100


@pytest.mark.parametrize("over", [over_long_name, over_long_path],
                         ids=["a name over the limit",
                              "a path over the limit"])
def test_an_over_long_upstream_path_is_an_absent_answer(project, tmp_path,
                                                        over):
    """`stat` answers `ENAMETOOLONG`, which is an `OSError` and no
    `PermissionError`: a notice that caught only the one the issue's case
    raises would end `make bootstrap` in a traceback again."""
    result = bootstrap(project, over(tmp_path))
    ends_ok(result)
    assert "  shape:" not in result.stdout, result.stdout


@LOCKED_OUT
def test_the_cache_answers_where_the_clone_cannot_be_read(project, locked):
    """An unreadable clone is an ABSENT answer, so the cache is asked next,
    as it is when `SHAPE_UPSTREAM_PATH` names nothing."""
    (project / ".shape-upstream-tip").write_bytes(f"{TIP}\n".encode())
    result = bootstrap(project, str(locked))
    ends_ok(result)
    assert NOTICE in result.stdout, result.stdout


def unreadable(cache: Path) -> None:
    """The cache holds `TIP`, and nobody may read it."""
    if os.name == "nt" or os.geteuid() == 0:
        pytest.skip("a mode of 000 keeps neither root nor a Windows process "
                    "out")
    cache.write_bytes(f"{TIP}\n".encode())
    cache.chmod(0)


def not_utf8(cache: Path) -> None:
    """The cache's first byte is 0xff, which no UTF-8 text begins with."""
    cache.write_bytes(b"\xff" + TIP[1:].encode() + b"\n")


@pytest.mark.parametrize("make", [unreadable, not_utf8],
                         ids=["unreadable", "not UTF-8"])
def test_a_cache_that_cannot_be_read_is_an_absent_answer(project, make):
    make(project / ".shape-upstream-tip")
    result = bootstrap(project)
    ends_ok(result)
    assert "  shape:" not in result.stdout, result.stdout


def test_a_shape_pin_that_is_not_a_mapping_ends_as_the_validators_end_it(
        project):
    """`validate-pins.py` refuses the list by name, and the run goes on to
    step (c) and ends on that refusal, `bootstrap REFUSED: pins (exit 2)`,
    exit 2, with no traceback."""
    (project / "contracts" / "shape-pin.yaml").write_bytes(b"- a\n- b\n")
    result = bootstrap(project)
    assert "Traceback" not in result.stderr, result.stderr
    assert "REFUSED shape-pin-unreadable: " in result.stderr, result.stderr
    assert "\n(c) review authority\n" in result.stdout, result.stdout
    assert result.returncode == 2, result.stdout


@LOCKED_OUT
def test_a_contracts_folder_nobody_may_enter_is_an_absent_answer(project,
                                                                 capsys):
    """Asked of the notice itself, in this process: the validators before
    it in a run have their own answer to such a folder. It says nothing,
    though the cache names a commit the pin is not."""
    notice = load_without_bytecode(
        REPO / "templates" / "assembly-root" / "scripts" / "bootstrap.py",
        "bootstrap_upstream_notice").shape_upstream_notice
    (project / ".shape-upstream-tip").write_bytes(f"{TIP}\n".encode())
    contracts = project / "contracts"
    contracts.chmod(0)
    try:
        notice(project)
    finally:
        contracts.chmod(0o755)
    assert capsys.readouterr().out == ""
