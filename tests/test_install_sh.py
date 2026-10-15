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

WINDOWS_SKIP, for the reason `tests/test_openreposhape_command.py` gives: the
installer and the command are bash, run where `bash` is a bash, and on
Windows the way in is `setup-project.py`.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP
from test_openreposhape_command import COMMAND, INSTALL_NEEDS, command_env

INSTALLER = REPO / "install.sh"

#: Bash by ABSOLUTE path: `subprocess` resolves a bare argv[0] against the
#: child's `$PATH`, and the one each run builds holds only what it chose.
BASH = shutil.which("bash")

pytestmark = [pytest.mark.skipif(BASH is None, reason="install.sh is bash"),
              WINDOWS_SKIP]

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
    path.write_text("#!/bin/sh\nexec %s %s %s \"$@\"\n" % (
        shlex.quote(sys.executable), shlex.quote(str(Path(__file__))), name),
        encoding="utf-8")
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
        sys.stdout.write("HTTP/2 302 \r\n%s: %s\r\n"
                         "content-length: 0\r\n\r\n"
                         % (NET.get("location_header", "location"), location))
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
        print(NET["gh_latest"])
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
            (self.path / name).symlink_to(real)
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
        path.write_text(
            f"#!/bin/sh\nexec {shlex.quote(sys.executable)} "
            f"{shlex.quote(str(self.root / 'fake.py'))} {name} \"$@\"\n",
            encoding="utf-8")
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
        piped = piped or script is not None
        argv = [BASH, "-s", "--", *args] if piped \
            else [BASH, str(INSTALLER), *args]
        return subprocess.run(
            argv, capture_output=True, text=True, check=False,
            input=(script or INSTALLER.read_text(encoding="utf-8"))
            if piped else "",
            cwd=str(self.tmp_path), start_new_session=True,
            env=command_env(home=self.tmp_path, setup_sh=None, env={
                "PATH": str(self.path), "GH_TOKEN": "bogus",
                "GH_CONFIG_DIR": str(gh_config),
                "TMPDIR": str(self.temporary), **(env or {})}))

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
    target = net.bin / "openRepoShape"
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
    return f"git-filter-repo: already installed ({net.path}/git-filter-repo)"


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
    return f"    python3 -m pip install --user {FILTER_REPO}"


def no_pipx_but_brew(net):
    no_pipx(net)
    net.fake("brew")
    net.fake("apt-get")
    return "    brew install git-filter-repo"


def no_pipx_but_apt(net):
    no_pipx(net)
    net.fake("apt-get")
    return f"    sudo apt-get install -y pipx && pipx install {FILTER_REPO}"


@pytest.mark.parametrize("arrange", [
    present_on_path, answering_git, pipx_onto_path, pipx_off_path,
    pipx_failing, no_pipx, no_pipx_but_brew, no_pipx_but_apt])
def test_git_filter_repo_is_said_installed_or_printed(net, arrange):
    """The three branches, and the ways each can end.

    PRESENT, on `$PATH` or as `git filter-repo`: said, and pipx is never
    run. NOT PRESENT AND PIPX IS THERE: said first, then `pipx install` at
    CI's version, then what came of it. NEITHER: the one command for this
    machine, printed and never run: brew's where brew is, pipx from apt where
    apt-get is (Debian 12 and Ubuntu 23.04 on refuse `pip install --user`),
    and pip otherwise. Nothing runs `sudo` or `apt-get`. None changes the
    exit status, and the step sits between the install and the preflight.
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
        assert lines[lines.index(expected) - 1] == (
            "git-filter-repo: not installed, and there is no pipx to install "
            "it with. Only adopt-project.py needs it; before adopting a "
            "repository, run:")
    assert lines.index(expected) < lines.index(
        f"preflight: {net.bin}/openRepoShape --preflight")
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
        f"{net.bin}/openRepoShape, {said}" in result.stdout


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
    assert f"openRepoShape: already installed at {net.bin}/openRepoShape " \
        "(unchanged)" in again.stdout
    assert f"openRepoShape: already pinned to {RELEASE} in " \
        f"{net.bin}/openRepoShape.ref (unchanged)" in again.stdout

    net.config["redirects"][latest()] = tag_page("v10.0.0")
    net.serve("v10.0.0")
    upgrade = net.run()
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr
    net.installed(upgrade, "v10.0.0")
    assert f"openRepoShape: pinned to v10.0.0 (was {RELEASE}), recorded in " \
        f"{net.bin}/openRepoShape.ref" in upgrade.stdout


def test_a_release_whose_command_records_no_ref_exits_one(net):
    """A release before v1.0.1 installs a command that follows main. The
    installer asks the installed command, says so, and exits 1; and the
    preflight it ends with is still handed the release's tag, so it is not
    main's setup.sh that checks the machine."""
    old = net.root / "old-openRepoShape"
    old.write_text(OLD_LAUNCHER, encoding="utf-8")
    net.serve(RELEASE, launcher=old)
    result = net.run(env={"OPENREPOSHAPE_BIN_DIR": str(net.bin),
                          "OPENREPOSHAPE_REPO": SLUG})
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"install: {net.bin}/openRepoShape does not stay on {RELEASE}: " \
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
    result = net.run(env={"OPENREPOSHAPE_BIN_DIR": str(net.bin)})
    assert result.returncode == 0, result.stdout + result.stderr
    net.installed(result)
    assert f"preflight: {net.bin}/openRepoShape --preflight" \
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
    assert f"{link} is a symbolic link, so nothing was installed" in said, said
    assert "pipx upgrade openreposhape" in said
    assert "pipx uninstall openreposhape" in said
    assert net.calls() == [], net.calls()
    assert link.is_symlink() and link.readlink() == packaged
    if not dangling:
        assert packaged.read_bytes() == original
    assert sorted(path.name for path in net.bin.iterdir()) == \
        ["openRepoShape"]
    assert list(net.temporary.iterdir()) == []


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
        [BASH, str(INSTALLER), "--help"], capture_output=True, text=True,
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
