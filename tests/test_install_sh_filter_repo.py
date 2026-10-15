# SPDX-License-Identifier: Apache-2.0
"""`install.sh`'s git-filter-repo step, and the two readinesses it ends with
(#595).

THE DEFECT, ON RAVEN (Arch Linux, `uv` and no `pipx`). The v1.0.1 installer
found no pipx, printed `python3 -m pip install --user git-filter-repo==2.47.0`,
which Arch's externally managed Python refuses (PEP 668), and ended "this
machine is ready", because the preflight does not ask about git-filter-repo.
The next `adopt-project.py execute` refused for the want of it.

WHAT IS TRUE NOW, each held below:

* git-filter-repo is installed with the pipx that is already here, or with
  the uv that is already here when there is no pipx, at the version CI runs;
  installed means found on `$PATH` afterwards, and a directory that is not on
  it yet is named with the tool's own way to put it there;
* with neither, the command printed is never `pip install --user`: Homebrew's,
  pipx from apt, dnf or pacman, or uv's own installer page, and nothing is run;
* the run ends with two readinesses, `adoption:` and then `done:`, which says
  "ready" only when git-filter-repo is there and "ready to scaffold, not yet
  to adopt" when it is not, with the next command on the line above;
* git-filter-repo never changes the exit status, which stays the preflight's
  and the pin's: it is needed to adopt and for nothing else.

THE FAKES ARE `tests/test_install_sh.py`'s `Net`, whose `pipx` places a
`git-filter-repo` where `net.json` says, and whose other names log the call
and exit 0. This file adds one program, `INSTALLERS`, behind `uv`: `uv tool
install` places a `git-filter-repo` where `uv_installs_into` says, or fails
when it names nowhere. Every case also has `sudo`, `python3`, `python`,
`pip` and `pip3` on `$PATH`, so a run that asked any of them for anything is
in `calls.log`, and none may be.
"""

from __future__ import annotations

import shlex
import sys

import pytest

import test_install_sh
from test_install_sh import FILTER_REPO, RELEASE, Net, preflight_call

#: The skip and the set-up of the file whose fakes these are, so the one
#: installer's tests run, or do not, together.
pytestmark = test_install_sh.pytestmark

#: `uv`, as `install.sh` asks it: `uv tool install` places a `git-filter-repo`
#: launcher where `uv_installs_into` names, with `\n` line ends whatever the
#: platform, or fails as a resolver or a network would. Logged first, into the
#: same `calls.log` as every other fake.
INSTALLERS = r'''
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NET = json.loads((HERE / "net.json").read_text(encoding="utf-8"))
NAME, ARGS = sys.argv[1], sys.argv[2:]
with open(HERE / "calls.log", "a", encoding="utf-8") as log:
    log.write(" ".join([NAME] + ARGS) + "\n")
if ARGS[:2] == ["tool", "install"] and NET.get("uv_installs_into"):
    placed = Path(NET["uv_installs_into"]) / "git-filter-repo"
    placed.write_bytes(b"#!/bin/sh\nexit 0\n")
    placed.chmod(0o755)
    sys.exit(0)
sys.stderr.write("fake uv: could not install " + " ".join(ARGS) + "\n")
sys.exit(1)
'''

#: Every way to reach pip, and `sudo`: on `$PATH` in every case, logging,
#: and never run.
PIP_AND_SUDO = ("sudo", "python3", "python", "pip", "pip3")
#: Those, and the package managers the printed commands name, each on `$PATH`
#: in its own case: nothing here may run any of them.
NEVER_RUN = (*PIP_AND_SUDO, "apt-get", "dnf", "pacman", "brew")

UV_PAGE = "https://docs.astral.sh/uv/getting-started/installation/"

#: The `adoption:` line where git-filter-repo is found.
READY = ("adoption: git-filter-repo is installed, which adopt-project.py "
         "needs beyond what the preflight checks.")

#: How the `done:` line ends for each readiness, after the path it names.
DONE_READY = (", pinned to the release tag, and this machine is ready. Run "
              "the same line again to upgrade to the newest release.")
DONE_SCAFFOLD_ONLY = (", pinned to the release tag, and this machine is ready "
                      "to scaffold, not yet to adopt. Run the same line again "
                      "to upgrade to the newest release.")


def not_ready(why: str, then: str) -> str:
    """The `adoption:` line where git-filter-repo is not found."""
    return ("adoption: NOT READY: adopt-project.py needs git-filter-repo, and "
            f"{why}. Before adopting a repository, run: {then}")


def installing(tool: str, command: str) -> str:
    return (f"git-filter-repo: not installed; installing it with {tool}, "
            f"because adopt-project.py needs it: {command}")


NEITHER = ("git-filter-repo: not installed, and there is neither pipx nor uv "
           "to install it with. Only adopt-project.py needs it; before "
           "adopting a repository, run:")

PIPX = f"pipx install {FILTER_REPO}"
UV = f"uv tool install {FILTER_REPO}"
#: What is printed where there is neither installer nor a package manager
#: `install.sh` knows: uv's, because uv installs without one.
UV_FIRST = f"{UV}  # once uv is installed: {UV_PAGE}"
PACMAN = f"sudo pacman -S --needed python-pipx && {PIPX}"


def uv(net: Net) -> None:
    """A `uv` on the run's `$PATH`, answering through `INSTALLERS`."""
    program = net.root / "installers.py"
    program.write_text(INSTALLERS, encoding="utf-8")
    (net.path / "uv").write_bytes((
        f"#!/bin/sh\nexec {shlex.quote(sys.executable)} "
        f"{shlex.quote(str(program))} uv \"$@\"\n").encode("utf-8"))
    (net.path / "uv").chmod(0o755)


def elsewhere(net: Net) -> str:
    """A directory that is not on the run's `$PATH`."""
    directory = net.tmp_path / "tool-bin"
    directory.mkdir(exist_ok=True)
    return str(directory)


# --- the cases: what is on the machine, and what the run must say ------------
#
# Each takes a `Net` with `curl` and `gh` and nothing else answerable, puts
# what its case needs on it, and returns the lines step 3 prints (each the
# start of a line, in order), the installers it runs, and the `adoption:` line.

def existing(net):
    """Already on PATH: said, and neither installer, both there, is run."""
    net.fake("pipx")
    uv(net)
    net.fake("git-filter-repo")
    return ["git-filter-repo: already installed ("], [], READY


def existing_as_git_subcommand(net):
    net.fake("git")
    net.config["git_filter_repo"] = True
    return ["git-filter-repo: already installed (git filter-repo --version "
            "answers)"], [], READY


def pipx_only(net):
    net.fake("pipx")
    return [installing("pipx", PIPX),
            "git-filter-repo: installed with pipx"], [PIPX], READY


def uv_only(net):
    """Raven's machine: uv, and no pipx."""
    uv(net)
    net.config["uv_installs_into"] = str(net.path)
    return [installing("uv", UV), "git-filter-repo: installed with uv"], \
        [UV], READY


def pipx_and_uv(net):
    """pipx first, as before #595; uv is not asked."""
    net.fake("pipx")
    uv(net)
    net.config["uv_installs_into"] = str(net.path)
    return [installing("pipx", PIPX),
            "git-filter-repo: installed with pipx"], [PIPX], READY


def pipx_failing(net):
    net.fake("pipx")
    net.config["pipx_installs_into"] = None
    return [installing("pipx", PIPX),
            "git-filter-repo: pipx could not install it (exit 1). Before "
            f"adopting a repository, install it: {PIPX}"], [PIPX], \
        not_ready("pipx could not install it (exit 1)", PIPX)


def uv_failing(net):
    uv(net)
    return [installing("uv", UV),
            "git-filter-repo: uv could not install it (exit 1). Before "
            f"adopting a repository, install it: {UV}"], [UV], \
        not_ready("uv could not install it (exit 1)", UV)


def pipx_off_path(net):
    net.fake("pipx")
    net.config["pipx_installs_into"] = elsewhere(net)
    return [installing("pipx", PIPX),
            "git-filter-repo: installed with pipx, into a directory that is "
            "not on PATH yet: run `pipx ensurepath` and open a new shell"], \
        [PIPX], not_ready("pipx installed it into a directory that is not on "
                          "PATH yet", "pipx ensurepath, then open a new shell")


def uv_off_path(net):
    uv(net)
    net.config["uv_installs_into"] = elsewhere(net)
    return [installing("uv", UV),
            "git-filter-repo: installed with uv, into a directory that is not "
            "on PATH yet: run `uv tool update-shell` and open a new shell"], \
        [UV], not_ready("uv installed it into a directory that is not on "
                        "PATH yet", "uv tool update-shell, then open a new "
                        "shell")


def neither(manager, command):
    """Neither installer, and `manager` the one package manager on PATH."""
    def arrange(net):
        if manager:
            net.fake(manager)
        return [NEITHER, f"    {command}"], [], \
            not_ready("it is not installed", command)
    arrange.__name__ = f"neither_{manager or 'and_no_package_manager'}"
    return arrange


CASES = [
    existing, existing_as_git_subcommand, pipx_only, uv_only, pipx_and_uv,
    pipx_failing, uv_failing, pipx_off_path, uv_off_path,
    neither("", UV_FIRST),
    neither("brew", "brew install git-filter-repo"),
    neither("apt-get", f"sudo apt-get install -y pipx && {PIPX}"),
    neither("dnf", f"sudo dnf install -y pipx && {PIPX}"),
    neither("pacman", PACMAN),
]


def arranged(tmp_path, arrange):
    """A `Net` with no installer on it, every `PIP_AND_SUDO` name logging,
    and `arrange`'s case put on it."""
    net = Net(tmp_path, fakes=("curl", "gh"))
    for name in PIP_AND_SUDO:
        net.fake(name)
    return (net, *arrange(net))


def starts_in_order(lines, starts):
    """The index of the first line starting with each of `starts`, which
    must exist and come in that order."""
    at = []
    for start in starts:
        found = [i for i, line in enumerate(lines) if line.startswith(start)]
        assert found, f"no line starts {start!r}:\n" + "\n".join(lines)
        at.append(found[0])
    assert at == sorted(at), "\n".join(lines)
    return at


@pytest.mark.parametrize("arrange", CASES, ids=lambda case: case.__name__)
def test_git_filter_repo_and_the_two_readinesses(tmp_path, arrange):
    """Every acceptance case of #595, held to the same five things.

    Step 3 says what it found and what it did, before the preflight. The
    installers run are exactly the case's: pipx where it is there, uv where
    pipx is not, neither where git-filter-repo already is, each once, at
    CI's version, and nothing in `NEVER_RUN` at all. No line names `pip
    install` or `--user`. The run ends `adoption:` then `done:`, both after
    the preflight, and the `done:` line says "ready" only when the
    `adoption:` line does. And the exit status is 0 in every case, because
    the preflight passed: git-filter-repo is not needed to scaffold.
    """
    net, steps, ran, adoption = arranged(tmp_path, arrange)
    result = net.run()
    assert result.returncode == 0, result.stdout + result.stderr
    net.installed(result)
    lines = result.stdout.splitlines()

    at = starts_in_order(lines, [*steps, "preflight: "])

    calls = net.calls()
    assert [call for call in calls
            if call.split()[0] in ("pipx", "uv")] == ran, calls
    assert not any(call.split()[0] in NEVER_RUN for call in calls), calls
    assert calls[-1] == preflight_call(), calls

    assert "pip install" not in result.stdout + result.stderr
    assert "--user" not in result.stdout + result.stderr

    assert lines[-2] == adoption, result.stdout
    done = DONE_READY if adoption == READY else DONE_SCAFFOLD_ONLY
    assert lines[-1].startswith(f"done: openRepoShape {RELEASE} is installed "
                                "at "), result.stdout
    assert lines[-1].endswith(done), result.stdout
    assert lines.index(adoption) > at[-1]


@pytest.mark.parametrize("arrange", [existing, neither("", UV_FIRST)],
                         ids=["git-filter-repo-there", "git-filter-repo-not"])
def test_a_preflight_that_fails_is_its_own_verdict_either_way(
        tmp_path, arrange):
    """The two readinesses are two: a preflight that did not pass exits 1
    with git-filter-repo there or not, and the `adoption:` line still says
    which, above the `done:` line that says the preflight did not pass."""
    net, _, _, adoption = arranged(tmp_path, arrange)
    net.config["preflight_exit"] = 1
    result = net.run()
    assert result.returncode == 1, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert lines[-2] == adoption, result.stdout
    assert lines[-1].endswith(", but the preflight did not pass (exit 1); it "
                              "names what is missing above."), result.stdout


#: A command older than v1.0.1, as far as the installer can tell, that places
#: itself where the real one does by default and records no ref.
UNPINNED = """#!/usr/bin/env bash
INSTALLABLES=(openRepoShape)
case "$1" in
--install) mkdir -p "$HOME/.local/bin" && cp "$0" "$HOME/.local/bin/openRepoShape" ;;
--version) printf 'openRepoShape (opensoft/openRepoShape @ main)\\n' ;;
--preflight) printf 'old preflight\\n' ;;
esac
"""


def test_a_command_that_does_not_stay_on_the_release_says_both_readinesses(
        tmp_path):
    """The `done:` line for a release that records no ref carries the
    machine's readiness too, and says "ready to scaffold, not yet to adopt"
    where git-filter-repo is missing; the exit status is the pin's, 1."""
    net, _, _, adoption = arranged(tmp_path, neither("pacman", PACMAN))
    old = net.root / "unpinned-openRepoShape"
    old.write_bytes(UNPINNED.encode("utf-8"))
    net.serve(RELEASE, launcher=old)
    result = net.run()
    assert result.returncode == 1, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert lines[-2] == adoption, result.stdout
    assert lines[-1].endswith(
        " and this machine is ready to scaffold, not yet to adopt, but the "
        f"command does not stay on {RELEASE} (see above)."), result.stdout

