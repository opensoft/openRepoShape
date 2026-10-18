# SPDX-License-Identifier: Apache-2.0
"""`install.sh`: openRepoShape in one line, pinned to a release (#564).

OFFLINE, ON A `$PATH` THE TEST OWNS ENTIRELY. Each run's `$PATH` holds the
real programs the installer and the command it installs need (`bash`,
`mktemp`, `cp` and the rest of `INSTALL_NEEDS`), and FAKES for everything
that would reach the network or install something: `curl`, `gh`, `pipx`,
and, where a test asks for them, `git-filter-repo`, `git` and `brew`.
Restricted rather than prepended, because the machine running this may have
git-filter-repo and pipx installed for real, and which of the three
git-filter-repo branches runs must be the test's choice, not the machine's.

EVERY FAKE IS ONE PROGRAM. A two-line shell launcher per name hands its
arguments to `FAKE` below, which appends the call to `calls.log` and answers
from `net.json`: the redirect github.com answers `releases/latest` with, the
files raw.githubusercontent.com serves, the tag `gh api` reports, and where
`pipx` puts what it installs. The `setup.sh` it serves is another launcher
into the same program, so the preflight the installer ends with is LOGGED,
with the arguments the installed command handed it: `--shape-ref <release>`
is where the pin shows.

THE COMMAND SERVED IS THIS CHECKOUT'S `openRepoShape`, so the install the
installer runs is the real one. Every run sets `GH_TOKEN=bogus` and an empty
`GH_CONFIG_DIR`, and its `TMPDIR` is a directory each test checks is empty
again afterwards.

On Windows it runs under Git Bash, as `tests/test_openreposhape_command.py`
does (#585): `BASH` is Git for Windows' own, every path is spelled the way
Git Bash spells it, and every script a fake writes has `\n` line ends. What
a fake prints that bash reads into a variable, the redirect's headers and
`gh`'s tag, is written as bytes, because Python on Windows ends a printed
line with `\r\n` and `$(…)` keeps the `\r`.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import BASH, BASH_SKIP, REPO, bash_path
from test_openreposhape_command import (BIN_DIR_SPELLINGS, COMMAND,
                                        COMMAND_REFUSAL_ENDS,
                                        CYGPATH_STATES, HOLDS_A_COLON,
                                        INSTALL_NEEDS, LINKED_BIN_DIRS,
                                        LOCALES, NO_FILE_NAMED_SO,
                                        NO_NON_ASCII_INTO_GIT_BASH,
                                        NOT_CONTROLS,
                                        REFUSED_IN_EVERY_LOCALE, RLO,
                                        UNNAMEABLE_BIN_DIRS,
                                        assert_a_bin_dir_is_refused,
                                        assert_refused_saying,
                                        drawn_as_another,
                                        command_env, machine_path,
                                        put_cygpath, put_on_path, run_cmd,
                                        typed_bin_dir, write_script)

INSTALLER = REPO / "install.sh"

#: `BASH` is by ABSOLUTE path: `subprocess` resolves a bare argv[0] against
#: the child's `$PATH`, and the one each run builds holds only what it chose.
pytestmark = [BASH_SKIP, pytest.mark.usefixtures("git_bash_session")]

SLUG = "opensoft/openRepoShape"
RELEASE = "v9.9.9"
FILTER_REPO = "git-filter-repo==2.47.0"

#: The flags every curl in the installer and the launcher carries, as the
#: fakes log them once the shell has taken the quotes off (SonarCloud
#: shell:S6506: HTTPS only, redirects included, TLS 1.2 or newer).
HTTPS_ONLY = "--proto =https --proto-redir =https --tlsv1.2"


def latest(slug: str = SLUG) -> str:
    return f"https://github.com/{slug}/releases/latest"


def tag_page(tag: str, slug: str = SLUG) -> str:
    return f"https://github.com/{slug}/releases/tag/{tag}"


def raw(name: str, ref: str = RELEASE, slug: str = SLUG) -> str:
    return f"https://raw.githubusercontent.com/{slug}/{ref}/{name}"


#: THE ONE PROGRAM BEHIND EVERY FAKE. `curl -fsSI` answers a configured
#: redirect with the headers github.com sends, CRLF and all, and `curl
#: -fsSL` a configured file, to `-o` or to stdout; anything else is curl's
#: own exit 22. `gh` reports a release only when one is configured. `pipx`
#: places a `git-filter-repo` launcher where it is told to, or fails. Every
#: call is logged first, so what was NOT asked is as plain as what was.
FAKE = r'''
import json
import shlex
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NET = json.loads((HERE / "net.json").read_text(encoding="utf-8"))
NAME, ARGS = sys.argv[1], sys.argv[2:]
with open(HERE / "calls.log", "a", encoding="utf-8") as log:
    log.write(" ".join([NAME] + ARGS) + "\n")


def refuse(message):
    sys.stderr.write(message + "\n")
    return 22 if NAME == "curl" else 1


def launcher(directory, name):
    path = Path(directory) / name
    path.write_bytes(("#!/bin/sh\nexec %s %s %s \"$@\"\n" % (
        shlex.quote(sys.executable), shlex.quote(str(Path(__file__))),
        name)).encode("utf-8"))
    path.chmod(0o755)


def curl():
    url = next((arg for arg in ARGS if arg.startswith("https://")), "")
    if url in NET.get("unreachable", []):
        sys.stderr.write("curl: (6) Could not resolve host\n")
        return 6
    if "-fsSI" in ARGS:
        location = NET["redirects"].get(url)
        if location is None:
            return refuse("curl: (22) The requested URL returned error: 404")
        sys.stdout.buffer.write((
            "HTTP/2 302 \r\n%s: %s\r\ncontent-length: 0\r\n\r\n"
            % (NET.get("location_header", "location"), location)
        ).encode("utf-8"))
        return 0
    served = NET["files"].get(url)
    if served is None:
        return refuse("curl: (22) The requested URL returned error: 404")
    data = Path(served).read_bytes()
    if "-o" in ARGS:
        Path(ARGS[ARGS.index("-o") + 1]).write_bytes(data)
    else:
        sys.stdout.buffer.write(data)
    return 0


def gh():
    if ARGS[:1] == ["api"] and ARGS[1].endswith("/releases/latest") \
            and NET.get("gh_latest"):
        sys.stdout.buffer.write((NET["gh_latest"] + "\n").encode("utf-8"))
        return 0
    return refuse("fake gh: no answer for: " + " ".join(ARGS))


def pipx():
    if NET.get("pipx_installs_into") is None:
        return refuse("fake pipx: could not install " + " ".join(ARGS))
    launcher(NET["pipx_installs_into"], "git-filter-repo")
    return 0


def git():
    if ARGS == ["filter-repo", "--version"] and NET.get("git_filter_repo"):
        print("a40bce548d2c")
        return 0
    return refuse("fake git: no answer for: " + " ".join(ARGS))


def setup_sh():
    print("fake preflight: " + " ".join(ARGS))
    return NET.get("preflight_exit", 0)


sys.exit({"curl": curl, "gh": gh, "pipx": pipx, "git": git,
          "setup.sh": setup_sh}.get(NAME, lambda: 0)())
'''

#: A RELEASE OLDER THAN v1.0.1, as far as the installer can tell: the
#: launcher's first line and its `INSTALLABLES` line, an `--install` that
#: copies itself and records nothing, and a `--version` that therefore says
#: `main`. It is all the installer asks of a command.
OLD_LAUNCHER = """#!/usr/bin/env bash
INSTALLABLES=(openRepoShape)
case "$1" in
--install) mkdir -p "$OPENREPOSHAPE_BIN_DIR" && cp "$0" "$OPENREPOSHAPE_BIN_DIR/openRepoShape" ;;
--version) printf 'openRepoShape (%s @ %s)\\n' "$OPENREPOSHAPE_REPO" "${OPENREPOSHAPE_REF:-main}" ;;
--preflight) printf 'old preflight at %s\\n' "${OPENREPOSHAPE_REF:-main}" ;;
esac
"""


class Net:
    """The fakes, what they answer, the `$PATH` that holds them, and a run.

    `fakes` names the programs on that `$PATH` that answer through `FAKE`;
    `serve` adds a release's two files; `config` is written to `net.json`
    at every `run`, so a test changes an answer between two runs by
    changing it here.
    """

    def __init__(self, tmp_path: Path, fakes=("curl", "gh", "pipx")):
        self.tmp_path = tmp_path
        self.root = tmp_path / "net"
        self.root.mkdir()
        (self.root / "fake.py").write_text(FAKE, encoding="utf-8")
        self.path = tmp_path / "path"
        self.path.mkdir()
        for name in (*INSTALL_NEEDS, "bash"):
            real = shutil.which(name)
            assert real, f"this machine has no {name}, which the install needs"
            put_on_path(self.path, name, real)
        for name in fakes:
            self.fake(name)
        self.temporary = tmp_path / "tmp"
        self.temporary.mkdir()
        self.bin = tmp_path / ".local" / "bin"
        self.config = {"redirects": {latest(): tag_page(RELEASE)},
                       "files": {}, "pipx_installs_into": str(self.path)}
        self.serve(RELEASE)

    def fake(self, name: str, directory: Path | None = None) -> Path:
        """A launcher for `name` into `FAKE`, on this `$PATH` by default."""
        path = (directory or self.path) / name
        write_script(
            path, f"#!/bin/sh\nexec {shlex.quote(sys.executable)} "
            f"{shlex.quote(str(self.root / 'fake.py'))} {name} \"$@\"\n")
        path.chmod(0o755)
        return path

    def serve(self, ref: str, slug: str = SLUG,
              launcher: Path = COMMAND) -> None:
        """`openRepoShape` and `setup.sh` at `ref`, as raw URLs answer."""
        served = self.root / "served" / ref
        served.mkdir(parents=True, exist_ok=True)
        self.config["files"][raw("openRepoShape", ref, slug)] = str(launcher)
        self.config["files"][raw("setup.sh", ref, slug)] = str(
            self.fake("setup.sh", served))

    def run(self, *args: str, piped: bool = False, env: dict | None = None,
            script: str | None = None) -> subprocess.CompletedProcess:
        """`bash install.sh <args>`, or `… | bash -s -- <args>` when piped;
        `script` pipes that text in place of the installer's own."""
        (self.root / "net.json").write_text(json.dumps(self.config),
                                            encoding="utf-8")
        gh_config = self.tmp_path / "gh-config"
        gh_config.mkdir(exist_ok=True)
        how = {"cwd": str(self.tmp_path), "start_new_session": True,
               "env": command_env(home=self.tmp_path, setup_sh=None, env={
                   "PATH": str(self.path), "GH_TOKEN": "bogus",
                   "GH_CONFIG_DIR": str(gh_config),
                   "TMPDIR": str(self.temporary), **(env or {})})}
        if piped or script is not None:
            return subprocess.run(
                [BASH, "-s", "--", *args], capture_output=True, text=True,
                check=False,
                input=script or INSTALLER.read_text(encoding="utf-8"), **how)
        argv = [BASH, bash_path(INSTALLER), *args]
        if os.name == "nt" and any("\n" in arg for arg in args):
            # A NEWLINE IN AN ARGUMENT DOES NOT CROSS INTO GIT BASH (#585).
            # Windows hands a program one command line, Python quotes only
            # an argument holding a space or a tab, and Git Bash splits the
            # line at a newline too, so `v1\nforged` arrived as two
            # versions. A person in Git Bash passes it from bash to bash,
            # where nothing is split; here a bash takes the arguments from
            # the environment, which keeps them whole, and hands them on.
            how["env"].update((f"ARG{at}", arg) for at, arg in enumerate(args))
            argv = [BASH, "-c", 'exec "$BASH" "$0" ' + " ".join(
                f'"$ARG{at}"' for at in range(len(args))), argv[1]]
        return subprocess.run(argv, capture_output=True, text=True,
                              check=False, input="", **how)

    def calls(self) -> list:
        log = self.root / "calls.log"
        return log.read_text(encoding="utf-8").splitlines() \
            if log.exists() else []

    def installed(self, result, ref: str = RELEASE) -> None:
        """The command is placed, byte for byte, with `ref` recorded beside
        it, and the run left nothing in `$TMPDIR`."""
        target = self.bin / "openRepoShape"
        assert target.read_bytes() == COMMAND.read_bytes(), (
            result.stdout + result.stderr)
        assert (self.bin / "openRepoShape.ref").read_text(
            encoding="utf-8") == f"{ref}\n"
        assert list(self.temporary.iterdir()) == []

    def refused(self, result) -> None:
        """Exit 2, nothing placed, no preflight run, nothing left behind."""
        assert result.returncode == 2, result.stdout + result.stderr
        assert not self.bin.exists(), "a refused install placed something"
        assert not any(call.startswith("setup.sh") for call in self.calls())
        assert list(self.temporary.iterdir()) == []


@pytest.fixture
def net(tmp_path):
    return Net(tmp_path)


def preflight_call(ref: str = RELEASE) -> str:
    """How the preflight reaches setup.sh through a command pinned to `ref`."""
    return f"setup.sh --shape-ref {ref} --preflight"


# --- the one line ------------------------------------------------------------

def test_the_one_line_installs_the_newest_release_pinned_to_it(net):
    """`curl … | bash`: the newest release, from the redirect alone.

    One line per step, in order, and the calls behind them in the same
    order: the redirect, the release's command, then the preflight, LAST,
    through the installed command, whose `setup.sh` is fetched at the
    release and handed `--shape-ref` for it. `gh` is never asked for a
    release when the redirect named one.
    """
    result = net.run(piped=True)
    assert result.returncode == 0, result.stdout + result.stderr
    net.installed(result)
    target = bash_path(net.bin / "openRepoShape")
    steps = [
        f"release: {RELEASE}, the newest release of {SLUG} ({latest()})",
        f"fetch: {raw('openRepoShape')}",
        f"install: OPENREPOSHAPE_REF={RELEASE} OPENREPOSHAPE_RECORD_REF=1 "
        "openRepoShape --install",
        f"openRepoShape: pinned to {RELEASE}, recorded in {target}.ref",
        "git-filter-repo: ",
        f"preflight: {target} --preflight",
        f"done: openRepoShape {RELEASE} is installed at {target}, pinned to "
        "the release tag, and this machine is ready. Run the same line again "
        "to upgrade to the newest release.",
    ]
    lines = result.stdout.splitlines()
    at = [next(i for i, line in enumerate(lines) if line.startswith(step))
          for step in steps]
    assert at == sorted(at), result.stdout
    calls = net.calls()
    assert calls[0] == f"curl -fsSI {HTTPS_ONLY} {latest()}"
    assert calls[1].startswith(
        f"curl -fsSL {HTTPS_ONLY} {raw('openRepoShape')} -o ")
    assert f"curl -fsSL {HTTPS_ONLY} {raw('setup.sh')}" in calls
    assert calls[-1] == preflight_call(), calls
    assert not any("releases/latest" in call for call in calls[1:]), calls


@pytest.mark.parametrize("piped", [False, True], ids=["file", "piped"])
def test_a_named_release_is_installed_and_no_newest_is_asked_for(net, piped):
    """`bash install.sh v9.9.8` and `… | bash -s -- v9.9.8`: that release,
    and no question about which one is newest."""
    net.serve("v9.9.8")
    result = net.run("v9.9.8", piped=piped)
    assert result.returncode == 0, result.stdout + result.stderr
    net.installed(result, "v9.9.8")
    assert "release: v9.9.8, as named" in result.stdout.splitlines()
    assert not any("-fsSI" in call for call in net.calls()), net.calls()
    assert net.calls()[-1] == preflight_call("v9.9.8")


def test_gh_answers_when_the_redirect_names_no_release(net):
    """A redirect to `/releases` names no tag (what github.com answers before
    a repository's first release); `gh api` is asked next, where installed."""
    net.config["redirects"][latest()] = f"https://github.com/{SLUG}/releases"
    net.config["gh_latest"] = RELEASE
    result = net.run()
    assert result.returncode == 0, result.stdout + result.stderr
    net.installed(result)
    assert f"release: {RELEASE}, the newest release of {SLUG} (gh api " \
        f"repos/{SLUG}/releases/latest)" in result.stdout


@pytest.mark.parametrize("location, fakes, redirect_fault, gh_fault", [
    pytest.param(f"https://github.com/{SLUG}/releases", ("curl",),
                 f"it redirects to https://github.com/{SLUG}/releases, which "
                 "names no release", "gh is not installed", id="no-release"),
    pytest.param(None, ("curl", "gh"), "curl failed, exit 22",
                 "gh failed, exit 1", id="both-failed"),
])
def test_no_release_found_names_each_way_that_failed(
        tmp_path, location, fakes, redirect_fault, gh_fault):
    """Each way names its URL or command and why it gave no answer, and the
    way out is to name a release; nothing is fetched or installed."""
    net = Net(tmp_path, fakes)
    if location is None:
        del net.config["redirects"][latest()]
    else:
        net.config["redirects"][latest()] = location
    result = net.run()
    net.refused(result)
    assert f"could not find the newest release of {SLUG}" in result.stderr
    assert f"curl -fsSI {latest()}   ({redirect_fault})" in result.stderr
    assert f"gh api repos/{SLUG}/releases/latest   ({gh_fault})" \
        in result.stderr
    assert "bash install.sh v1.0.1" in result.stderr
    assert not any("-fsSL" in call for call in net.calls())


@pytest.mark.parametrize("args, said", [
    pytest.param(("v1..v2",), "the version is 'v1..v2'", id="a-range"),
    pytest.param(("x.lock",), "the version is 'x.lock'", id="a-lock-file"),
    pytest.param(("/etc",), "the version is '/etc'", id="a-path"),
    pytest.param(("v1\nforged",), "the version carries a control character",
                 id="two-lines"),
    pytest.param(("a" * 256,), "the version is 256 characters long",
                 id="over-long"),
    pytest.param(("-x",), "unknown option '-x'", id="an-option"),
    pytest.param(("-x\nforged",), "an option carries a control character",
                 id="an-option-of-two-lines"),
    pytest.param(("v1.0.1", "v1.0.2"), "two versions given", id="two"),
])
def test_a_version_that_is_not_a_ref_is_refused_before_any_request(
        net, args, said):
    """Checked the way the launcher checks a ref, before any URL is built
    from it; a control character and the over-long value never echoed."""
    result = net.run(*args)
    net.refused(result)
    assert said in result.stderr
    assert net.calls() == []
    assert "forged" not in result.stderr
    assert "a" * 256 not in result.stderr


def test_a_failed_fetch_names_its_url_and_installs_nothing(net):
    """An error from the server asks whether the release exists."""
    del net.config["files"][raw("openRepoShape")]
    result = net.run()
    net.refused(result)
    assert f"could not fetch {raw('openRepoShape')}: the server answered " \
        "with an error (curl exit 22), so nothing was installed. Is " \
        f"{RELEASE} a release of {SLUG}?" in result.stderr


def test_a_fetch_with_no_answer_points_at_the_network_not_the_release(net):
    """No answer at all (DNS, a proxy, TLS) is not a question about the
    release, and the refusal does not send anyone looking there."""
    net.config["unreachable"] = [raw("openRepoShape")]
    result = net.run()
    net.refused(result)
    assert f"could not fetch {raw('openRepoShape')}: curl got no answer " \
        "(curl exit 6), so nothing was installed. Check this machine's " \
        "network, DNS and proxy" in result.stderr
    assert "a release of" not in result.stderr


def test_a_page_that_is_not_the_command_is_refused(net):
    """A proxy's or a portal's page can arrive with a 200; it is refused
    before anything runs it."""
    page = net.root / "page.html"
    page.write_text("<!doctype html><title>Sign in</title>\n",
                    encoding="utf-8")
    net.config["files"][raw("openRepoShape")] = str(page)
    result = net.run()
    net.refused(result)
    assert f"{raw('openRepoShape')} is not the openRepoShape command" \
        in result.stderr


# --- git-filter-repo ---------------------------------------------------------

def present_on_path(net):
    net.fake("git-filter-repo")
    return "git-filter-repo: already installed " \
        f"({bash_path(net.path)}/git-filter-repo)"


def answering_git(net):
    net.fake("git")
    net.config["git_filter_repo"] = True
    return "git-filter-repo: already installed (git filter-repo --version " \
        "answers)"


def pipx_onto_path(net):
    return "git-filter-repo: installed with pipx"


def pipx_off_path(net):
    elsewhere = net.tmp_path / "pipx-bin"
    elsewhere.mkdir()
    net.config["pipx_installs_into"] = str(elsewhere)
    return "git-filter-repo: installed with pipx, into a directory that is " \
        "not on PATH yet: run `pipx ensurepath` and open a new shell"


def pipx_failing(net):
    net.config["pipx_installs_into"] = None
    return f"git-filter-repo: pipx could not install it (exit 1). Before " \
        f"adopting a repository, install it: pipx install {FILTER_REPO}"


def no_pipx(net):
    (net.path / "pipx").unlink()
    return f"    uv tool install {FILTER_REPO}"


def no_pipx_but_brew(net):
    no_pipx(net)
    net.fake("brew")
    net.fake("apt-get")
    return "    brew install git-filter-repo"


def no_pipx_but_apt(net):
    no_pipx(net)
    net.fake("apt-get")
    return f"    sudo apt-get install -y pipx && pipx install {FILTER_REPO} " \
        "&& pipx ensurepath"


@pytest.mark.parametrize("arrange", [
    present_on_path, answering_git, pipx_onto_path, pipx_off_path,
    pipx_failing, no_pipx, no_pipx_but_brew, no_pipx_but_apt])
def test_git_filter_repo_is_said_installed_or_printed(net, arrange):
    """The three branches, and the ways each can end.

    PRESENT, on `$PATH` or as `git filter-repo`: said, and pipx is never
    run. NOT PRESENT AND PIPX IS THERE: said first, then `pipx install` at
    CI's version, then what came of it. NEITHER PIPX NOR uv: the one command
    for this machine, printed and never run: brew's where brew is, pipx from
    apt where apt-get is (Debian 12 and Ubuntu 23.04 on refuse `pip install
    --user`), and uv's otherwise, never pip's (#595; uv, dnf, pacman and the
    summary are `tests/test_install_sh_filter_repo.py`'s). Nothing runs
    `sudo` or `apt-get`. None changes the exit status, and the step sits
    between the install and the preflight.
    """
    expected = arrange(net)
    result = net.run()
    assert result.returncode == 0, result.stdout + result.stderr
    net.installed(result)
    lines = result.stdout.splitlines()
    assert expected in lines, result.stdout
    ran_pipx = [call for call in net.calls() if call.startswith("pipx")]
    if arrange in (pipx_onto_path, pipx_off_path, pipx_failing):
        assert ran_pipx == [f"pipx install {FILTER_REPO}"], net.calls()
        assert "git-filter-repo: not installed; installing it with pipx, "\
            "because adopt-project.py needs it: pipx install " \
            f"{FILTER_REPO}" in lines
        assert net.calls().index(ran_pipx[0]) < \
            net.calls().index(preflight_call())
    else:
        assert ran_pipx == [], net.calls()
    if arrange in (no_pipx, no_pipx_but_brew, no_pipx_but_apt):
        assert lines[lines.index(expected) - 1].startswith(
            "git-filter-repo: not installed, and there is neither pipx nor uv "
            "to install it with. Only adopt-project.py needs it; before "
            "adopting a repository, ")
    assert lines.index(expected) < lines.index(
        f"preflight: {bash_path(net.bin)}/openRepoShape --preflight")
    assert not any(call.split()[0] in ("apt-get", "brew", "sudo")
                   for call in net.calls()), net.calls()


# --- the preflight, the exit status, and running it again --------------------

@pytest.mark.parametrize("status, said", [
    pytest.param(1, "but the preflight did not pass (exit 1); it names what "
                 "is missing above.", id="not-ready"),
    pytest.param(2, "but the preflight did not run to the end (exit 2); the "
                 "REFUSED line above says why.", id="did-not-run"),
])
def test_a_preflight_that_does_not_pass_exits_one_with_the_command_placed(
        net, status, said):
    """Exit 1 is the preflight's own "not ready", which names what is
    missing; anything else stopped before it could say."""
    net.config["preflight_exit"] = status
    result = net.run()
    assert result.returncode == 1, result.stdout + result.stderr
    net.installed(result)
    assert f"done: openRepoShape {RELEASE} is installed at " \
        f"{bash_path(net.bin)}/openRepoShape, {said}" in result.stdout


def test_a_variable_in_the_shell_is_named_and_the_preflight_runs_the_pin(net):
    """`$OPENREPOSHAPE_REF` exported in the person's shell overrides the pin
    on every run while it stays set, so the installer says so; the release
    is still what is recorded, and the preflight still runs through it."""
    result = net.run(env={"OPENREPOSHAPE_REF": "v0.0.1"})
    assert result.returncode == 0, result.stdout + result.stderr
    net.installed(result)
    assert "install: $OPENREPOSHAPE_REF is set in this shell, by your " \
        "shell profile or by hand, and while it is, every run uses it " \
        f"instead of {RELEASE}. Remove it from your shell profile to run " \
        f"{RELEASE}." in result.stdout
    assert net.calls()[-1] == preflight_call()


def test_the_same_line_again_changes_nothing_and_then_upgrades(net):
    """Idempotent while the newest release is the same one; the next
    release, once it is the newest, replaces the record and says which it
    replaced."""
    assert net.run().returncode == 0
    again = net.run()
    assert again.returncode == 0, again.stdout + again.stderr
    assert "openRepoShape: already installed at " \
        f"{bash_path(net.bin)}/openRepoShape (unchanged)" in again.stdout
    assert f"openRepoShape: already pinned to {RELEASE} in " \
        f"{bash_path(net.bin)}/openRepoShape.ref (unchanged)" in again.stdout

    net.config["redirects"][latest()] = tag_page("v10.0.0")
    net.serve("v10.0.0")
    upgrade = net.run()
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr
    net.installed(upgrade, "v10.0.0")
    assert f"openRepoShape: pinned to v10.0.0 (was {RELEASE}), recorded in " \
        f"{bash_path(net.bin)}/openRepoShape.ref" in upgrade.stdout


def test_a_release_whose_command_records_no_ref_exits_one(net):
    """A release before v1.0.1 installs a command that follows main. The
    installer asks the installed command, says so, and exits 1; and the
    preflight it ends with is still handed the release's tag, so it is not
    main's setup.sh that checks the machine."""
    old = net.root / "old-openRepoShape"
    write_script(old, OLD_LAUNCHER)
    net.serve(RELEASE, launcher=old)
    result = net.run(env={"OPENREPOSHAPE_BIN_DIR": bash_path(net.bin),
                          "OPENREPOSHAPE_REPO": SLUG})
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"install: {bash_path(net.bin)}/openRepoShape does not stay on " \
        f"{RELEASE}: " \
        f"it says 'openRepoShape ({SLUG} @ main)' to --version." \
        in result.stdout
    assert "A release older than v1.0.1 cannot record the tag it was " \
        "installed at: install v1.0.1 or newer, or export " \
        f"OPENREPOSHAPE_REF={RELEASE} in your shell profile to keep it " \
        "there." in result.stdout
    assert f"old preflight at {RELEASE}" in result.stdout.splitlines()
    assert result.stdout.splitlines()[-1].endswith(
        f"but the command does not stay on {RELEASE} (see above).")


@pytest.mark.parametrize("header, location", [
    pytest.param("Location", tag_page(RELEASE), id="upper-case"),
    pytest.param("location", f"/{SLUG}/releases/tag/{RELEASE}",
                 id="relative"),
])
def test_the_redirect_is_read_in_any_case_and_relative(net, header, location):
    """HTTP/1.1 may send `Location:`, and a location may be relative; both
    name the release the same way."""
    net.config["location_header"] = header
    net.config["redirects"][latest()] = location
    result = net.run()
    assert result.returncode == 0, result.stdout + result.stderr
    net.installed(result)
    assert f"release: {RELEASE}, the newest release of {SLUG} ({latest()})" \
        in result.stdout.splitlines()


def test_openreposhape_bin_dir_is_where_the_command_and_its_record_go(net):
    """The installer places, pins and preflights the command where the
    launcher puts it, and leaves `~/.local/bin` alone."""
    default = net.bin
    net.bin = net.tmp_path / "elsewhere"
    result = net.run(env={"OPENREPOSHAPE_BIN_DIR": bash_path(net.bin)})
    assert result.returncode == 0, result.stdout + result.stderr
    net.installed(result)
    assert f"preflight: {bash_path(net.bin)}/openRepoShape --preflight" \
        in result.stdout.splitlines()
    assert not default.exists()


@pytest.mark.parametrize("dangling", [False, True], ids=["live", "dangling"])
def test_a_command_that_is_a_symlink_is_refused_before_any_request(
        net, dangling):
    """pipx places the openreposhape package's `openRepoShape` as a LINK
    into the package's own environment, in this same directory (#563).

    The command's `--install` would copy through it, so install.sh refuses
    the target ITSELF, before it asks the network anything: the release it
    installs may carry a command older than that command's own check. The
    link stays as it was, the file it names keeps its bytes, and nothing is
    left in `$TMPDIR`.
    """
    packaged = net.tmp_path / "pipx" / "venvs" / "openreposhape" / "bin" / \
        "openRepoShape"
    original = b"#!/usr/bin/env python3\n# the package's own command\n"
    if not dangling:
        packaged.parent.mkdir(parents=True)
        packaged.write_bytes(original)
    net.bin.mkdir(parents=True)
    link = net.bin / "openRepoShape"
    link.symlink_to(packaged)
    result = net.run()
    assert result.returncode == 2, result.stdout + result.stderr
    said = " ".join(result.stderr.split())
    assert f"{bash_path(link)} is a symbolic link, so nothing was installed" \
        in said, said
    assert "pipx upgrade openreposhape" in said
    assert "pipx uninstall openreposhape" in said
    assert net.calls() == [], net.calls()
    assert link.is_symlink()
    # Windows reads a link back with `\\?\` ahead of its target.
    assert str(link.readlink()).removeprefix("\\\\?\\") == str(packaged)
    if not dangling:
        assert packaged.read_bytes() == original
    assert sorted(path.name for path in net.bin.iterdir()) == \
        ["openRepoShape"]
    assert list(net.temporary.iterdir()) == []


# --- a Windows-spelled `$OPENREPOSHAPE_BIN_DIR` (#667) -----------------------

def in_its_own_directory(tmp_path: Path, name: str) -> Path:
    """`tmp_path/name`, made: one run's whole world, so that two runs of one
    test cannot see each other's files."""
    directory = tmp_path / name
    directory.mkdir()
    return directory


@BIN_DIR_SPELLINGS
@pytest.mark.parametrize("state", CYGPATH_STATES)
def test_the_installer_and_the_command_answer_one_drive_directory_alike(
        tmp_path, spelling, state):
    """ONE `$OPENREPOSHAPE_BIN_DIR`, spelled for Windows, through install.sh
    and through the command it installs (#667).

    The command respells it with `cygpath -u`, or refuses it where no
    `cygpath` can (#649), and install.sh carries a copy of that `case`,
    because it arrives alone and cannot share the command's. The two must
    never answer one value differently, so each is given the same value,
    in each spelling, with `cygpath` in each state: spelled, failing,
    answering a drive spelling again, or not there. Where it spells, both
    place the command at the directory as bash does and name no other; where
    it does not, both refuse with exit 2, and install.sh has asked the
    network nothing.
    """
    net = Net(in_its_own_directory(tmp_path, "installer"))
    net.bin = net.tmp_path / "drive" / "bin"
    command_home = in_its_own_directory(tmp_path, "command")
    command_bin = command_home / "drive" / "bin"
    typed_installer = typed_bin_dir(net.bin, spelling)
    typed_command = typed_bin_dir(command_bin, spelling)
    put_cygpath(net.path, typed_installer, state, bash_path(net.bin))
    command_env_path = machine_path(command_home, ())
    command_env_path.pop("_log")
    put_cygpath(command_home / "machine-path", typed_command, state,
                bash_path(command_bin))

    installer = net.run(env={"OPENREPOSHAPE_BIN_DIR": typed_installer})
    command = run_cmd("--install", home=command_home, cwd=command_home,
                      env={**command_env_path,
                           "OPENREPOSHAPE_BIN_DIR": typed_command})

    if state == "spells":
        assert installer.returncode == 0, installer.stdout + installer.stderr
        assert command.returncode == 0, command.stdout + command.stderr
        net.installed(installer)
        assert (command_bin / "openRepoShape").read_bytes() \
            == COMMAND.read_bytes()
        assert f"preflight: {bash_path(net.bin)}/openRepoShape --preflight" \
            in installer.stdout.splitlines()
        assert "openRepoShape: installed at " \
            f"{bash_path(command_bin)}/openRepoShape" \
            in command.stdout.splitlines()
        assert typed_installer not in installer.stdout
        assert typed_command not in command.stdout
        return
    net.refused(installer)
    assert command.returncode == 2, command.stdout + command.stderr
    for result in (installer, command):
        said = " ".join(result.stderr.split())
        assert "is spelled for Windows" in said, said
        assert "no cygpath here spells it the way bash does" in said, said
        assert "Set $OPENREPOSHAPE_BIN_DIR to the directory as this shell " \
            "spells it, then run this" in said, said
    assert net.calls() == [], net.calls()
    assert not command_bin.exists()
    assert typed_installer not in installer.stderr


#: An old launcher that answers as Git Bash makes every launcher answer:
#: the drive spelling and the bash spelling name one directory, so it places
#: itself where `cygpath -u` says whichever it was handed. `OLD_LAUNCHER`
#: takes the variable as typed, which off Windows is a directory of its own.
OLD_LAUNCHER_IN_GIT_BASH = OLD_LAUNCHER.replace(
    'mkdir -p "$OPENREPOSHAPE_BIN_DIR" && '
    'cp "$0" "$OPENREPOSHAPE_BIN_DIR/openRepoShape"',
    'dir="$(cygpath -u -- "$OPENREPOSHAPE_BIN_DIR")" && mkdir -p "$dir" && '
    'cp "$0" "$dir/openRepoShape"')
assert OLD_LAUNCHER_IN_GIT_BASH != OLD_LAUNCHER


@pytest.mark.parametrize("preflight_exit, old, ends", [
    pytest.param(0, False, "pinned to the release tag, and this machine is "
                 "ready. Run the same line again to upgrade to the newest "
                 "release.", id="done"),
    pytest.param(1, False, "but the preflight did not pass (exit 1); it "
                 "names what is missing above.", id="preflight-not-ready"),
    pytest.param(2, False, "but the preflight did not run to the end (exit "
                 "2); the REFUSED line above says why.",
                 id="preflight-did-not-run"),
    pytest.param(0, True, "and this machine is ready, but the command does "
                 "not stay on v9.9.9 (see above).", id="does-not-stay"),
])
def test_every_line_names_a_windows_spelled_bin_dir_the_way_bash_does(
        tmp_path, preflight_exit, old, ends):
    """`D:\\tools\\bin` was echoed as typed by `install:`, `preflight:` and
    each of the four `done:` lines, where the command's own lines said
    `/d/tools/bin` (#667). With `cygpath` spelling it, every one of them says
    the directory the way bash does, and none says it as typed. The fourth
    `done:` is the one after `install:`, which an old release earns."""
    net = Net(tmp_path)
    net.bin = tmp_path / "drive" / "bin"
    typed = typed_bin_dir(net.bin, "backslash")
    target = f"{bash_path(net.bin)}/openRepoShape"
    put_cygpath(net.path, typed, "spells", bash_path(net.bin))
    net.config["preflight_exit"] = preflight_exit
    if old:
        launcher = net.root / "old-openRepoShape"
        write_script(launcher, OLD_LAUNCHER_IN_GIT_BASH)
        net.serve(RELEASE, launcher=launcher)
    result = net.run(env={"OPENREPOSHAPE_BIN_DIR": typed,
                          "OPENREPOSHAPE_REPO": SLUG})
    assert result.returncode == (0 if preflight_exit == 0 and not old else 1), \
        result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert f"preflight: {target} --preflight" in lines, result.stdout
    assert lines[-1] == f"done: openRepoShape {RELEASE} is installed at " \
        f"{target}{' ' if old else ', '}{ends}", result.stdout
    if old:
        assert any(line.startswith(f"install: {target} does not stay on "
                                   f"{RELEASE}: ") for line in lines), \
            result.stdout
    assert typed not in result.stdout


def test_the_symlink_check_looks_at_the_directory_as_bash_spells_it(tmp_path):
    """The link check names a target it can find: with the drive spelling
    respelled first, pipx's link at the directory as bash spells it is the
    one that is found and refused, before any request (#563, #667). Read as
    typed, `D:\\tools\\bin/openRepoShape` is no link here, and the install
    would go on and copy through the one that is."""
    net = Net(tmp_path)
    net.bin = tmp_path / "drive" / "bin"
    typed = typed_bin_dir(net.bin, "backslash")
    put_cygpath(net.path, typed, "spells", bash_path(net.bin))
    packaged = tmp_path / "pipx" / "openRepoShape"
    packaged.parent.mkdir(parents=True)
    packaged.write_bytes(b"#!/usr/bin/env python3\n# the package's own\n")
    net.bin.mkdir(parents=True)
    (net.bin / "openRepoShape").symlink_to(packaged)
    result = net.run(env={"OPENREPOSHAPE_BIN_DIR": typed})
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"{bash_path(net.bin)}/openRepoShape is a symbolic link, so " \
        "nothing was installed" in " ".join(result.stderr.split())
    assert net.calls() == [], net.calls()
    assert packaged.read_bytes() == b"#!/usr/bin/env python3\n# the package's own\n"


# --- a directory no line about `$PATH` can name (#760) -----------------------

#: How install.sh's refusals of one end: the command's remedy, for this file.
INSTALLER_REFUSAL_ENDS = (
    "Nothing was installed. Set $OPENREPOSHAPE_BIN_DIR to a directory "
    "without one, then run this line again.")


@pytest.mark.parametrize("value, said", UNNAMEABLE_BIN_DIRS)
def test_the_installer_refuses_what_the_command_refuses_before_any_request(
        tmp_path, value, said):
    """ONE `$OPENREPOSHAPE_BIN_DIR`, a `:` or a control character, through
    install.sh and through the command it installs (#760).

    The command refuses it with exit 2, but install.sh learnt of it only
    after its fetch, said only "the <version> openRepoShape's --install
    refused (exit 2)", and a release older than the refusal placed the
    command under it and printed it as typed. So install.sh carries a copy
    of both `case` arms, and the two must never answer one value
    differently: each is refused with exit 2 and the remedy, nothing is
    placed or made, and install.sh has asked the network nothing. A colon's
    refusal names the directory; a control character's never does."""
    net = Net(in_its_own_directory(tmp_path, "installer"))
    command_home = in_its_own_directory(tmp_path, "command")
    seen = {path.name for path in net.tmp_path.iterdir()}
    typed_installer = value.format(d=bash_path(net.tmp_path))
    typed_command = value.format(d=bash_path(command_home))

    installer = net.run(env={"OPENREPOSHAPE_BIN_DIR": typed_installer})
    command = run_cmd("--install", home=command_home, cwd=command_home,
                      env={"OPENREPOSHAPE_BIN_DIR": typed_command})

    assert net.calls() == [], net.calls()
    assert_a_bin_dir_is_refused(installer, typed_installer, said,
                                INSTALLER_REFUSAL_ENDS)
    assert_a_bin_dir_is_refused(command, typed_command, said,
                                COMMAND_REFUSAL_ENDS)
    net.refused(installer)
    assert {path.name for path in net.tmp_path.iterdir()} - seen \
        <= {"gh-config"}
    assert list(command_home.iterdir()) == []


@NO_FILE_NAMED_SO
def test_the_installer_holds_the_default_directory_to_the_colon_refusal(
        tmp_path):
    """No variable at all, and a `$HOME` that holds a `:`: the directory is
    `$HOME/.local/bin`, and install.sh refuses it as the command does,
    naming it (#667, #760)."""
    net = Net(tmp_path)
    home = tmp_path / "a:b"
    result = net.run(env={"HOME": str(home)})
    assert net.calls() == [], net.calls()
    assert_a_bin_dir_is_refused(result, f"{home}/.local/bin", HOLDS_A_COLON,
                                INSTALLER_REFUSAL_ENDS)
    net.refused(result)


@NO_FILE_NAMED_SO
@pytest.mark.parametrize("name, said", LINKED_BIN_DIRS)
def test_a_bin_dir_is_refused_before_the_symlink_check_names_it(
        tmp_path, name, said):
    """The symlink refusal (#563) names `$target`, so a directory holding a
    carriage return or U+202E that has pipx's link in it would have
    install.sh print the value as typed (#760, #837): the value is refused
    first, and the link stays as it was."""
    net = Net(tmp_path)
    bin_dir = tmp_path / name / "bin"
    bin_dir.mkdir(parents=True)
    link = bin_dir / "openRepoShape"
    link.symlink_to(tmp_path / "nowhere")
    result = net.run(env={"OPENREPOSHAPE_BIN_DIR": str(bin_dir)})
    assert net.calls() == [], net.calls()
    assert_a_bin_dir_is_refused(result, str(bin_dir), said,
                                INSTALLER_REFUSAL_ENDS)
    assert link.is_symlink()


@NO_NON_ASCII_INTO_GIT_BASH
@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("name", NOT_CONTROLS)
def test_the_installer_places_a_directory_with_an_unprinted_letter(
        tmp_path, locale, name):
    """The refusal is `[[:cntrl:]]` and not `[![:print:]]`, which
    `checked_repo` uses (#760): under `LC_ALL=C` the two bytes of an e with
    an acute accent are not printable, so the second would refuse a
    directory called `caf` and that letter for a fault it has not got. It
    is installed into, in either locale, and named as typed, and so is a
    no-break space, whose first byte is the C1 controls' (`0xC2`) and
    whose second is the one past them, and so are the zero-width
    non-joiner and joiner and the other names in `NOT_CONTROLS` (#837).
    The line is looked for among the lines split at a newline and nothing
    else, as `splitlines` splits at other characters too."""
    net = Net(tmp_path)
    net.bin = tmp_path / name
    result = net.run(env={"OPENREPOSHAPE_BIN_DIR": bash_path(net.bin),
                          "LC_ALL": locale})
    assert result.returncode == 0, result.stdout + result.stderr
    net.installed(result)
    assert f"preflight: {bash_path(net.bin)}/openRepoShape --preflight" \
        in result.stdout.split("\n"), result.stdout


@NO_NON_ASCII_INTO_GIT_BASH
@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("value, said", REFUSED_IN_EVERY_LOCALE)
def test_the_installer_refuses_in_every_locale_before_any_request(
        tmp_path, value, said, locale):
    """A C1 control (U+0080 to U+009F) in the directory (#760), or a
    character a terminal draws as something other than itself (#837),
    under `C` and under `C.UTF-8`, alone, after a byte that is not UTF-8,
    and beside a colon: exit 2 with the refusal that says what it holds,
    no request, and nothing of the value in either stream. Under a UTF-8
    locale a byte that is not UTF-8 anywhere in the value makes bash match
    byte by byte, and `[[:cntrl:]]` then matches neither byte of U+009B, as
    it matches neither under `C`; the second check looks for bytes in any
    locale, and names what it found by its code point."""
    net = Net(tmp_path)
    typed = value.format(d=bash_path(tmp_path))
    result = net.run(env={"OPENREPOSHAPE_BIN_DIR": typed, "LC_ALL": locale})
    assert net.calls() == [], net.calls()
    assert_a_bin_dir_is_refused(result, typed, said, INSTALLER_REFUSAL_ENDS)
    net.refused(result)


# A version, an option, the repository, the newest release's tag or the
# location github.com redirects to, holding U+202E (#837). Each arranges
# `net` and returns the arguments, the environment, what the refusal says,
# and whether the value comes from the network, so that the run asks it.

def a_version(net):
    return (("v1" + RLO + "forged",), {},
            f"the version {drawn_as_another('U+202E')}.", False)


def an_option(net):
    return (("-x" + RLO + "forged",), {},
            f"an option {drawn_as_another('U+202E')}.", False)


def the_repository(net):
    return ((), {"OPENREPOSHAPE_REPO": "acme/x" + RLO + "forged"},
            f"$OPENREPOSHAPE_REPO {drawn_as_another('U+202E')}.", False)


def the_newest_tag(net):
    net.config["redirects"][latest()] = tag_page("v1" + RLO + "forged")
    return ((), {}, "the newest release's tag "
            f"{drawn_as_another('U+202E')}.", True)


def a_location(net):
    net.config["redirects"][latest()] = (
        f"https://github.com/{SLUG}/releases/" + RLO + "forged")
    return ((), {}, "it redirects to a location that names no release",
            True)


@NO_NON_ASCII_INTO_GIT_BASH
@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("arrange", [a_version, an_option, the_repository,
                                     the_newest_tag, a_location],
                         ids=lambda arrange: arrange.__name__)
def test_the_installer_refuses_a_value_drawn_as_another_unechoed(
        net, arrange, locale):
    """`checked_repo`, `checked_version`, the option check and the
    redirect's reading held their value to `[![:print:]]`, which a UTF-8
    locale's U+202E passes, and the refusal or fault after it printed the
    value as typed (#837). Each now looks for a character of `MISDRAWN`
    first and names it by its code point, under `C` and `C.UTF-8` alike:
    exit 2, nothing placed, nothing fetched, no request at all where the
    value is not the network's, and neither stream holds the value."""
    args, env, said, asks = arrange(net)
    result = net.run(*args, env={**env, "LC_ALL": locale})
    assert_refused_saying(result, said)
    net.refused(result)
    calls = net.calls()
    assert not any("-fsSL" in call for call in calls), calls
    assert bool(calls) is asks, calls


#: A curl that RUNS, in either script: tab-indented, alone or as the value
#: of an assignment. Usage text and refusals carry curl lines too, indented
#: with spaces, and are printed, never run.
CURL_RUN = re.compile(r"\t+(\w+=\"\$\()?curl -fsS")


@pytest.mark.parametrize("name", ["install.sh", "openRepoShape"])
def test_every_curl_that_runs_is_https_only_redirects_included(name):
    """SonarCloud shell:S6506, held here rather than found there: each curl
    line refuses any protocol but HTTPS, for its redirects too, written out
    on the line itself."""
    runs = [line for line in (REPO / name).read_text(
        encoding="utf-8").splitlines() if CURL_RUN.match(line)]
    assert runs, f"{name} runs no curl; this guard has nothing to hold"
    for line in runs:
        assert "--proto '=https' --proto-redir '=https' --tlsv1.2" in line, (
            f"{name}: a curl that is not HTTPS only:\n{line}")


#: Where a download can stop in the last line. Right after the word `main`
#: is the one the braces are for: unbraced, that line would run `main` with
#: none of the arguments, and install the newest release where one was named.
CUTS = [
    pytest.param(lambda text: text[:text.rindex("{ main")], id="before-it"),
    pytest.param(lambda text: text[:text.rindex(" ${1+")], id="after-main"),
    pytest.param(lambda text: text[:text.rindex(" }")], id="before-the-brace"),
]


@pytest.mark.parametrize("cut", CUTS)
def test_a_download_cut_off_in_the_last_line_runs_nothing(net, cut):
    """Everything runs from `main`, called on the last line inside braces:
    a script that stops anywhere in or before that line asks for nothing,
    installs nothing and leaves nothing behind."""
    result = net.run("v9.9.8",
                     script=cut(INSTALLER.read_text(encoding="utf-8")))
    assert net.calls() == []
    assert result.stdout == ""
    assert not net.bin.exists()


# --- the repository it installs from ----------------------------------------

def test_openreposhape_repo_names_where_everything_comes_from(net):
    """A fork named once is where the release, the command and the
    preflight's setup.sh all come from, and the installed command says so."""
    fork = "acme/openRepoShape"
    net.config["redirects"] = {latest(fork): tag_page(RELEASE, fork)}
    net.config["files"] = {}
    net.serve(RELEASE, fork)
    result = net.run(env={"OPENREPOSHAPE_REPO": fork})
    assert result.returncode == 0, result.stdout + result.stderr
    net.installed(result)
    assert all(SLUG not in call for call in net.calls()), net.calls()
    assert f"curl -fsSL {HTTPS_ONLY} {raw('setup.sh', RELEASE, fork)}" \
        in net.calls()


@pytest.mark.parametrize("value", [
    "https://github.com/acme/openRepoShape.git", "acme", "acme/x/y",
    "/srv/openRepoShape"])
def test_a_repository_that_is_not_an_owner_and_name_is_refused(net, value):
    result = net.run(env={"OPENREPOSHAPE_REPO": value})
    net.refused(result)
    assert f"$OPENREPOSHAPE_REPO is '{value}', which is not an owner/name " \
        "on github.com" in result.stderr
    assert net.calls() == []


# --- what the file says about itself ------------------------------------------

def test_help_prints_the_one_line_and_exits_zero(tmp_path):
    result = subprocess.run(
        [BASH, bash_path(INSTALLER), "--help"], capture_output=True, text=True,
        check=False, input="",
        env=command_env(home=tmp_path, setup_sh=None,
                        env={"GH_TOKEN": "bogus",
                             "GH_CONFIG_DIR": str(tmp_path)}))
    assert result.returncode == 0, result.stderr
    assert "curl -fsSL https://github.com/opensoft/openRepoShape/releases/" \
        "latest/download/install.sh | bash" in result.stdout


def test_it_installs_the_git_filter_repo_ci_runs():
    """What the installer puts on a machine is what the adoption suites ran
    against: the pin it names is every pin `.github/workflows/tests.yml`
    installs."""
    [pinned] = re.findall(r'^FILTER_REPO_PIN="(git-filter-repo==[^"]+)"$',
                          INSTALLER.read_text(encoding="utf-8"), re.M)
    ci = re.findall(r"git-filter-repo==[0-9.]+", (
        REPO / ".github" / "workflows" / "tests.yml").read_text(
        encoding="utf-8"))
    assert ci, "tests.yml installs no git-filter-repo"
    assert set(ci) == {pinned}, (pinned, ci)
