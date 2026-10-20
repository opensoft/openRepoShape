# SPDX-License-Identifier: Apache-2.0
"""`setup-project.py`'s self-bootstrap refuses an `$OPENREPOSHAPE_REPO`
holding a character a terminal draws as something other than itself
(#953).

The value was held to `checked_value(..., PATH_RE)`, which refuses a leading
`-` and a control character and takes every character of the launcher's
`MISDRAWN_CHARACTERS`. So `acme/r`, U+202E, `forged` was printed raw in the
clone line and handed to `git clone`, which exited 128. Two ways in reach
it: `python3 setup-project.py --org acme`, the documented self-bootstrap
mode, and the package's `openRepoShape` beside a source tree with no `.git`
(a "Download ZIP" tree, or an sdist installed with `pip install -e .`),
which hands over to that tree's `setup-project.py`, and that one finds no
checkout and self-bootstraps.

`checked_repo` now asks the launcher's list first, by code point, and
refuses in the launcher's words (its `checked_repo`, and the package's
`clone_url`): exit 2, no line on stdout from `setup-project.py`, no
character of the list and no `forged` tail in either stream, and no git
call but the one `is_shape_checkout` makes before it, which asks git about
the directory the file sits in and names nothing of the value. The copy of
the list is held to the launcher's, as the package's is.

`setup.sh` has no twin of these cases: its guard asks the launcher's rule
for a control character and the two separators, and no other character of
the list, which the launcher refuses first where it is the way in (#940).
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

import pytest

from conftest import REPO
from test_openreposhape_command import (MISDRAWN, NOT_CONTROLS, RLO,
                                        SHARING_ITS_BYTES,
                                        assert_refused_saying,
                                        repo_drawn_as_another)
from test_openreposhape_package import (PACKAGE, call_loggers, package_env,
                                        run_package)
from test_setup_project_py import (entry_point_module, make_outside_checkout,
                                   run_entry)

#: `call_loggers`' `git` is a shell script, and a `.cmd` beside it on
#: Windows, where `subprocess` starts `git.exe` by that name and never the
#: `.cmd`: the stub would log nothing there.
SHELL_STUB = pytest.mark.skipif(
    os.name == "nt", reason="the logging git stub is not run on Windows")

#: The value #953 measured: an owner/name, U+202E, and a tail no stream may
#: show.
ISSUE_VALUE = "acme/r" + RLO + "forged"

#: The two runs straight from a downloaded `setup-project.py`: the issue's,
#: and the one with only the organisation self-bootstrap mode requires.
RUNS = [pytest.param(("Atlas", "--org", "acme"), id="atlas-org"),
        pytest.param(("--org", "acme"), id="org-only")]

#: Each value refused, and the code points its refusal names: U+202E, then
#: others of the list, in two, three and four bytes of UTF-8, so that it is
#: the list and not one character; two at once, named in code point order;
#: and U+202E after a tab, which the launcher's `checked_repo` refuses by
#: the code point first, before it asks for a control character.
REFUSED = [
    pytest.param(ISSUE_VALUE, "U+202E", id="u+202e"),
    pytest.param("acme/r" + chr(0x00AD) + "forged", "U+00AD", id="u+00ad"),
    pytest.param("acme/r" + chr(0x200B) + "forged", "U+200B", id="u+200b"),
    pytest.param("acme/r" + chr(0xE0001) + "forged", "U+E0001",
                 id="u+e0001"),
    pytest.param("acme/r" + RLO + "b" + chr(0x200B) + "forged",
                 "U+200B, U+202E", id="two-at-once"),
    pytest.param("acme/r\t" + RLO + "forged", "U+202E",
                 id="a-tab-then-u+202e"),
]


def calls_logged(log: Path) -> list:
    """Every call `call_loggers`' stubs logged, one line each."""
    return log.read_text(encoding="utf-8").splitlines() \
        if log.exists() else []


def checkout_probe(directory: Path) -> str:
    """The call `is_shape_checkout` makes before anything else, as the stub
    logs it: git asked whether `directory`, where the file sits, is a
    checkout. It names nothing of `$OPENREPOSHAPE_REPO`."""
    return f"git -C {directory} rev-parse --show-toplevel"


def a_tree_with_no_git(directory: Path) -> Path:
    """A source tree of the standard with no `.git`, as "Download ZIP"
    leaves one: the package's modules under `src/openreposhape/`, and this
    checkout's `setup-project.py` and the other files the package's
    `beside_checkout` looks for (`CHECKOUT_MARKERS`). Resolved, as the
    package names it."""
    tree = (directory / "openRepoShape-main").resolve()
    (tree / "src" / "openreposhape").mkdir(parents=True)
    for module in sorted(PACKAGE.glob("*.py")):
        shutil.copyfile(module, tree / "src" / "openreposhape" / module.name)
    for marker in ("setup-project.py", "scaffold-project.py",
                   "shape-doctor.py", "contracts/repository-naming.yaml"):
        (tree / marker).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / marker, tree / marker)
    return tree


def test_the_misdrawn_table_is_the_launchers_list():
    """`setup-project.py` runs before there is a checkout to read the
    launcher from, so it carries a copy of the launcher's
    `MISDRAWN_CHARACTERS` (#953), as the package and install.sh carry one:
    the same entries, in the same order. `misdrawn_characters` names all of
    `MISDRAWN`, the code points the launcher's tests write out, each once
    and in code point order."""
    module = entry_point_module()
    [listed] = re.findall(r"^MISDRAWN_CHARACTERS=\((.*?)\)\n",
                          (REPO / "openRepoShape").read_text(
                              encoding="utf-8"), re.M)
    assert module.MISDRAWN_CHARACTERS == tuple(listed.split())
    every = "".join(chr(code) for code in reversed(MISDRAWN)) * 2
    assert module.misdrawn_characters(every) == ", ".join(
        f"U+{code:04X}" for code in MISDRAWN)


def test_misdrawn_characters_names_the_launchers_and_nothing_else():
    """The launcher's case for its own function (#837), for this copy: over
    one value for each code point whose UTF-8 starts with the bytes one of
    `MISDRAWN` starts with (`SHARING_ITS_BYTES`), it names exactly the code
    points of `MISDRAWN`, each as `U+XXXX`, and nothing for the rest."""
    module = entry_point_module()
    assert {code: module.misdrawn_characters(f"/a{chr(code)}b")
            for code in SHARING_ITS_BYTES} == {
        code: f"U+{code:04X}" if code in MISDRAWN else ""
        for code in SHARING_ITS_BYTES}


@SHELL_STUB
@pytest.mark.parametrize("value, named", REFUSED)
@pytest.mark.parametrize("args", RUNS)
def test_a_repository_drawn_as_another_is_refused_before_a_line_names_it(
        tmp_path, args, value, named):
    """A downloaded `setup-project.py`, run with `--org` and a repository
    holding a character of the list: refused, exit 2, in the launcher's
    words, before `(0) self-bootstrap` prints and before the clone. No part
    of the value reaches either stream (`assert_refused_saying` reads
    U+202E's bytes, `E2 80 AE`, as the character), and the one git call is
    the checkout probe. Before, the clone line printed the value raw and
    `git clone` was handed it."""
    outside = make_outside_checkout(tmp_path)
    path, log = call_loggers(tmp_path)
    result = run_entry(*args, cwd=outside, script=outside / "setup-project.py",
                       extra_env={"OPENREPOSHAPE_REPO": value, "PATH": path})
    said = repo_drawn_as_another(named)
    assert calls_logged(log) == [checkout_probe(outside)]
    assert assert_refused_saying(result, said) == f"REFUSED: {said}"


@SHELL_STUB
@pytest.mark.parametrize("tail", NOT_CONTROLS)
def test_a_repository_holding_none_of_the_list_is_cloned_as_before(
        tmp_path, tail):
    """The launcher's `NOT_CONTROLS`, each after `acme/`: letters past
    ASCII, U+200C and U+200D where a script or an emoji needs them, and
    characters whose UTF-8 starts as one of the list's does. None is
    refused: the clone line names the value and `git clone` is handed it,
    as before. The stub's clone fails, and the run exits with its status."""
    value = "acme/" + tail
    outside = make_outside_checkout(tmp_path)
    path, log = call_loggers(tmp_path)
    result = run_entry("--org", "acme", cwd=outside,
                       script=outside / "setup-project.py",
                       extra_env={"OPENREPOSHAPE_REPO": value, "PATH": path})
    calls = calls_logged(log)
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"  git clone --quiet -- {value} " in result.stdout
    assert calls[:1] == [checkout_probe(outside)]
    assert [call.startswith(f"git clone --quiet -- {value} ")
            for call in calls[1:]] == [True]


@SHELL_STUB
def test_the_package_beside_a_tree_with_no_git_hands_over_and_is_refused(
        tmp_path):
    """The issue's run through the package (#953): `openRepoShape Atlas
    --org acme` from a tree with no `.git`, which the package takes for a
    checkout it sits in, so it names that tree and hands over to the tree's
    `setup-project.py`. That one finds no checkout, self-bootstraps, and
    refuses the repository, exit 2, in the launcher's words. The package's
    line is the only one on stdout, no part of the value reaches either
    stream, and the one git call is the checkout probe."""
    tree = a_tree_with_no_git(tmp_path)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    path, log = call_loggers(tmp_path)
    result = run_package(tree / "src", "openreposhape",
                         ["Atlas", "--org", "acme"],
                         package_env(tmp_path, detached=True, env={
                             "OPENREPOSHAPE_REPO": ISSUE_VALUE,
                             "PATH": path}), cwd=cwd)
    assert calls_logged(log) == [checkout_probe(tree)]
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout.splitlines() == [
        f"openRepoShape: the standard is the checkout this package sits in, "
        f"{tree}."]
    assert " ".join(result.stderr.split()) == \
        f"REFUSED: {repo_drawn_as_another('U+202E')}"
    for stream in (result.stdout, result.stderr):
        assert "forged" not in stream, stream
        assert RLO not in stream, stream
