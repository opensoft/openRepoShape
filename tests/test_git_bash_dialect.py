# SPDX-License-Identifier: Apache-2.0
"""Under Git Bash the lines that follow the host are quoted for `sh` (#711).

`shape-doctor.py`'s lines, `setup-project.py`'s family lines and the lines of
`scripts/family.py` that quote for the host chose PowerShell's dialect
wherever `os.name` was `nt`, and `os.name` is `nt` under Git Bash too: the
Python it runs is the Windows one. So a line printed in Git Bash was quoted
for a shell the person was not in, and Git Bash read `'O''Neill'` as
`ONeill` and a bare `C:\\work\\Atlas` as `C:workAtlas`.

ONE QUESTION NOW ANSWERS IT, `host_shell_dialect`, in `scripts/repo_shape.py`
and as a copy in `setup-project.py`, which runs before any checkout of the
standard exists: a Windows host whose environment has a non-empty `MSYSTEM`
(Git Bash, any MSYS2 shell) is `sh`'s, every other Windows host
PowerShell's, and every other host `sh`'s. An explicit `platform` keeps its
meaning.

EMULATED ON ANY HOST. Each module under test is handed an `os` of its own
whose `name` is the host's (`HostOs`), and `MSYSTEM` is set, set empty or
unset in the real environment, which that `os` reads through. The real
`os.name` is never touched: pathlib reads it. Each line is read back the
way the reader's shell reads it, `shlex.split` for `sh` and
`powershell_words` for PowerShell, and must give back the words it was
built from. `PYTHON` is decided at import, from this host's `os.name`, so
the interpreter a line names is this host's; CI's `tests-git-bash` job is
where a real Git Bash runs.
"""

from __future__ import annotations

import os
import re
import shlex
import sys
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

import pytest

from conftest import REPO, load_without_bytecode
from test_family import FAMILY
#: The values and the PowerShell reader, and the two tools loaded in process,
#: from the module that holds the copies to one answer on the real host.
from test_family_printed_quoting import (  # noqa: F401
    AWKWARD, EVERY_ASCII, LEADING_EQUALS, ORDINARY, doctor, powershell_words,
    setup_tool,
)

sys.path.insert(0, str(REPO / "scripts"))
import repo_shape  # noqa: E402

#: Each host a line may be printed on: its `os.name`, its `MSYSTEM` (None for
#: unset), and the dialect `host_shell_dialect` answers for it.
HOSTS = {
    "powershell": ("nt", None, "nt"),
    "git-bash": ("nt", "MINGW64", "posix"),
    "msys2-ucrt64": ("nt", "UCRT64", "posix"),
    "empty-msystem": ("nt", "", "nt"),
    "posix": ("posix", None, "posix"),
    "posix-with-msystem": ("posix", "MINGW64", "posix"),
}

#: Windows paths with what the two dialects escape differently: a space and
#: an apostrophe.
WINDOWS_SHAPE = PureWindowsPath(r"C:\Users\Jane O'Neill\open Repo Shape")
WINDOWS_ROOT = PureWindowsPath(r"C:\Users\Jane O'Neill\work\Atlas")
COMMIT = "3d46ab5b9c1dcafe0123456789abcdef01234567"


class HostOs:
    """`os` as a module under test reads it on another host: `name` is the
    one asked for, and every other attribute is this host's own `os`,
    `environ` included, so `MSYSTEM` is read from the real environment."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __getattr__(self, attribute: str):
        return getattr(os, attribute)


def as_host(monkeypatch, host: str, *functions) -> str:
    """Run `functions` as on `host`, and return the dialect it answers: the
    module of each reads `os.name` as `host`'s, through a `HostOs` put in
    place of the `os` it names, and `MSYSTEM` is set, set empty or unset."""
    name, msystem, dialect = HOSTS[host]
    for function in functions:
        monkeypatch.setitem(function.__globals__, "os", HostOs(name))
    if msystem is None:
        monkeypatch.delenv("MSYSTEM", raising=False)
    else:
        monkeypatch.setenv("MSYSTEM", msystem)
    return dialect


def reader(dialect: str):
    """How the shell of `dialect` splits a line into words."""
    return powershell_words if dialect == "nt" else shlex.split


@pytest.fixture(scope="module")
def family_tool():
    return load_without_bytecode(FAMILY, "family_for_git_bash_dialect")


# --- the question ------------------------------------------------------------

@pytest.mark.parametrize("host", sorted(HOSTS))
def test_the_question_answers_each_host(monkeypatch, host):
    """Asked about a host by its two facts, and asked on it: one answer."""
    name, msystem, dialect = HOSTS[host]
    environ = {} if msystem is None else {"MSYSTEM": msystem}
    assert repo_shape.host_shell_dialect(name, environ) == dialect
    as_host(monkeypatch, host, repo_shape.host_shell_dialect)
    assert repo_shape.host_shell_dialect() == dialect


#: Every `os.name` and environment the two copies are asked about.
NAMES = ["nt", "posix", "java"]
ENVIRONS = [{}, {"MSYSTEM": ""}, {"MSYSTEM": "MINGW64"}, {"MSYSTEM": "MSYS"},
            {"MSYSTEM": "CLANGARM64"}, {"MSYSTEM": " "}, {"msystem": "x"},
            {"PATH": "C:\\Windows"}]


def test_setups_copy_of_the_question_gives_the_same_answer(setup_tool):
    """`setup-project.py` carries its own copy, because it runs before any
    checkout of the standard exists: held to the same answer here, as its
    `shell_word` is to `shell_quoted`."""
    differ = {(name, tuple(environ.items())): (
        setup_tool.host_shell_dialect(name, environ),
        repo_shape.host_shell_dialect(name, environ))
        for name in NAMES for environ in ENVIRONS
        if setup_tool.host_shell_dialect(name, environ)
        != repo_shape.host_shell_dialect(name, environ)}
    assert differ == {}
    assert setup_tool.SHELL_BARE_NT.pattern == repo_shape.SHELL_BARE_NT.pattern
    assert setup_tool.SHELL_BARE_POSIX.pattern == \
        repo_shape.SHELL_BARE_POSIX.pattern


# --- `shell_quoted`, and `setup-project.py`'s `shell_word` -------------------

#: `(value, PowerShell's spelling, sh's spelling)`: a Windows path bare to
#: PowerShell and not to `sh`, and one whose apostrophe the two escape apart.
SPELLINGS = [
    (r"C:\work\Atlas", r"C:\work\Atlas", r"'C:\work\Atlas'"),
    (r"C:\Users\Jane O'Neill\proj", r"'C:\Users\Jane O''Neill\proj'",
     r"'C:\Users\Jane O'\''Neill\proj'"),
]


@pytest.mark.parametrize("host", sorted(HOSTS))
@pytest.mark.parametrize("value,powershell,sh", SPELLINGS)
def test_shell_quoted_spells_a_word_for_the_hosts_shell(monkeypatch, host,
                                                        value, powershell, sh):
    dialect = as_host(monkeypatch, host, repo_shape.shell_quoted)
    quoted = repo_shape.shell_quoted(value)
    assert quoted == (powershell if dialect == "nt" else sh)
    assert reader(dialect)(quoted) == [value]
    assert reader(dialect)(repo_shape.shell_line(["cd", value])) == \
        ["cd", value]


@pytest.mark.parametrize("value,powershell,sh", SPELLINGS)
def test_an_explicit_platform_keeps_its_meaning_under_git_bash(
        monkeypatch, doctor, value, powershell, sh):
    """A test, or a line spelled for the other shell, still names it."""
    as_host(monkeypatch, "git-bash", repo_shape.shell_quoted, doctor.quote_arg)
    assert repo_shape.shell_quoted(value, "nt") == powershell
    assert repo_shape.shell_quoted(value, "posix") == sh
    assert doctor.quote_arg(value, "nt") == powershell
    assert doctor.quote_arg(value, "posix") == sh


@pytest.mark.parametrize("host", sorted(HOSTS))
def test_setup_quotes_by_the_same_rule_on_each_host(monkeypatch, setup_tool,
                                                    host):
    """THE TWO COPIES, ONE ANSWER, on every host and not only this one: the
    alphabet and the escape both follow the question, at each call."""
    dialect = as_host(monkeypatch, host, setup_tool.shell_word,
                      repo_shape.shell_quoted)
    for value in [*ORDINARY, *AWKWARD, *LEADING_EQUALS, *EVERY_ASCII]:
        assert setup_tool.shell_word(value) == \
            repo_shape.shell_quoted(value), value
    for value, powershell, sh in SPELLINGS:
        assert setup_tool.shell_word(value) == \
            (powershell if dialect == "nt" else sh)
        assert setup_tool.shell_word(value, posix=True) == sh


# --- one line per tool -------------------------------------------------------

@pytest.mark.parametrize("host", sorted(HOSTS))
def test_setups_family_lines_paste_whole_in_the_hosts_shell(
        monkeypatch, capsys, setup_tool, host):
    """L2-29: `family_next_command`'s `switch -c` and `add` take the host's
    dialect, so in Git Bash they are `sh`'s."""
    dialect = as_host(monkeypatch, host, setup_tool.shell_word)
    holder = Path(str(WINDOWS_ROOT))
    landing = setup_tool.Landing(holder.parent, "Atlas", holder)
    setup_tool.family_next_command("Sample", "demoorg", landing)
    commands = [line.strip() for line in capsys.readouterr().out.splitlines()
                if line.strip() and not line.strip().startswith("#")]
    words = reader(dialect)
    assert words(commands[0]) == ["git", "-C", str(holder), "switch", "-c",
                                  "family/add-sample"]
    assert words(commands[1]) == [
        setup_tool.PYTHON_CMD, "scripts/family.py", "add", "--family-root",
        str(holder), "--member", "demoorg/Sample"]


@pytest.mark.parametrize("host", sorted(HOSTS))
def test_familys_next_steps_paste_whole_in_the_hosts_shell(
        monkeypatch, capsys, family_tool, host):
    """`init`'s NEXT STEPS: the `switch -c`, the `add` and the `cd` lane 5
    named on the issue, each read back by the shell of the host."""
    dialect = as_host(monkeypatch, host, family_tool.shell_line)
    work = WINDOWS_ROOT
    args = SimpleNamespace(org="demoorg", tracking_branch="main")
    family_tool._print_next_steps(args, work, work.parent)
    block = [line.strip() for line in capsys.readouterr().out.splitlines()]
    words = reader(dialect)
    switch = next(line for line in block if line.startswith("git -C "))
    add = next(line for line in block if " add --family-root " in line)
    cd = next(line for line in block if line.startswith("cd "))
    assert words(switch) == ["git", "-C", str(work), "switch", "-c",
                             "family/add-<Project>"]
    assert words(add) == [family_tool.PYTHON, family_tool._family_script(),
                          "add", "--family-root", str(work), "--member",
                          "demoorg/<Project>"]
    assert words(cd) == ["cd", str(work)]


def doctor_lines(doctor, dialect: str, machine: str) -> dict:
    """`{name: (the line, the words its reader must get back)}` for each of
    the doctor's lines that asks the host when it is given no platform."""
    shape, root = WINDOWS_SHAPE, WINDOWS_ROOT
    python = doctor.python_command()
    source, target = shape / "templates" / "x.md", root / "x.md"
    keep = doctor.checkout_notes("leg", [root / "spec"])
    lines = {
        "quote_arg": (doctor.quote_arg(root), [str(root)]),
        "restore_from_head": (
            doctor.restore_from_head(root, "scripts/repo_shape.py"),
            ["git", "-C", str(root), "checkout", "HEAD", "--",
             "scripts/repo_shape.py"]),
        "bump_leg_command": (
            doctor.bump_leg_command(shape, root, "spec", COMMIT),
            [python, str(shape / "scripts" / "bump-leg.py"), "--root",
             str(root), "--leg", "spec", "--to", COMMIT, "--trailer",
             "Lane: lane 2"]),
        "submodule_update_next": (
            doctor.submodule_update_next(root, ["spec"], [], "leg")[0],
            ["git", "-C", str(root), "submodule", "update", "--init",
             "--recursive", "--checkout", "--", "spec"]),
        "checkout_notes": (
            re.search(r"run first (.*) with a name of your choice",
                      keep).group(1),
            ["git", "-C", str(root / "spec"), "branch", "NAME"]),
        "copy_command": (
            doctor.copy_command(source, target),
            ["Copy-Item", "-LiteralPath", str(source), "-Destination",
             str(target)] if dialect == "nt" else
            ["cp", str(source), str(target)]),
        "scaffold_command": (
            doctor.scaffold_command(shape, "Atlas"),
            [python, str(shape / "setup-project.py"), "--org", "<your-org>",
             "--project", "Atlas"] if machine == "nt" else
            [str(shape / "setup.sh"), "--org", "<your-org>", "--project",
             "Atlas"]),
    }
    return lines


DOCTOR_LINES = ["quote_arg", "restore_from_head", "bump_leg_command",
                "submodule_update_next", "checkout_notes", "copy_command",
                "scaffold_command"]


@pytest.mark.parametrize("host", sorted(HOSTS))
@pytest.mark.parametrize("line", DOCTOR_LINES)
def test_the_doctors_lines_paste_whole_in_the_hosts_shell(monkeypatch, doctor,
                                                          host, line):
    """Each is read back by the shell of the host. Under Git Bash that is
    `sh`, with `cp` and not `Copy-Item`, and the way in is still `python
    setup-project.py`: the entry point is the machine's, and only its
    quoting is the shell's."""
    monkeypatch.setenv("LANES_LANE", "lane 2")
    dialect = as_host(monkeypatch, host, doctor.quote_arg,
                      doctor.host_shell_dialect)
    printed, words = doctor_lines(doctor, dialect, HOSTS[host][0])[line]
    assert reader(dialect)(printed) == words, printed


@pytest.mark.parametrize("host", sorted(HOSTS))
def test_the_doctors_validator_line_sets_pythonpath_in_the_hosts_shell(
        monkeypatch, doctor, host):
    """`$env:PYTHONPATH = ...;` is PowerShell's, and Git Bash reads it as an
    empty `$env` and a command `:PYTHONPATH`: under Git Bash the line is
    `env PYTHONPATH=... python ...`, the interpreter still the machine's."""
    dialect = as_host(monkeypatch, host, doctor.quote_arg,
                      doctor.host_shell_dialect)
    shape = WINDOWS_SHAPE
    used = shape / "templates" / "assembly-root" / "scripts" / \
        "validate-pins.py"
    scripts = doctor.validator_scripts(shape, False)
    args = ["--root", WINDOWS_ROOT]
    words = [doctor.python_command(), str(used), "--root", str(WINDOWS_ROOT)]
    printed = doctor.validator_command(shape, used, False, args)
    if dialect == "nt":
        prefix = (f"$env:PYTHONPATH = "
                  f"{doctor.quote_arg(scripts, 'nt', always=True)}; ")
        assert printed.startswith(prefix), printed
        assert powershell_words(printed[len(prefix):]) == words
    else:
        assert shlex.split(printed) == ["env", f"PYTHONPATH={scripts}",
                                        *words], printed
