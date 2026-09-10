# SPDX-License-Identifier: Apache-2.0
"""`openRepoShape` — the installable command that runs `setup.sh` for you.

OFFLINE, LIKE THE REST OF THIS SUITE. Every run here sets
`$OPENREPOSHAPE_SETUP_SH` to THIS checkout's own `setup.sh` — the command's
local-copy path — so nothing is ever fetched, `gh` is never invoked and no real
repository is created. The end-to-end test drives the real thing against BARE
REPOSITORIES IN A TEMPORARY DIRECTORY through setup.sh's `--local-remote-dir`,
exactly as `tests/test_setup_sh.py` does.

The FETCHING path is exercised too, and still offline: the last two tests put
a fake `gh` first on `$PATH` — `fetch_from_repo` tries the API before the raw
URL, so answering that one call is the whole of the server they need — and
shadow `curl` with a script that refuses, so a run cannot fall through to the
network even if the fake `gh` stops matching. `#82` made `--install` place
three files and `#92` took it back to one: `park` and `resume` are
opensoft/openRepoTools' now, and the fake server answers for whatever
`INSTALLED` names. What a fake `gh` cannot show is which way round the real
two are tried, so THAT rule — the authenticated call first, because an
organisation can block raw.githubusercontent.com and still have a working
`gh` — stays asserted against the script's text, the way this suite guards
other things it cannot run.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess

from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP

COMMAND = REPO / "openRepoShape"
SETUP = REPO / "setup.sh"

#: EVERY FILE `--install` PLACES. Three of them from #82 until 2026-09-10 and
#: one again since (#92): `park` and `resume` carved out into
#: opensoft/openRepoTools, which installs them with a one-liner of its own.
#: A TUPLE STILL, and every test below still loops over it, because what #82
#: bought is the all-or-none structure and that is what has to keep working at
#: one name — an installer whose guarantee only holds while the list is long
#: loses it the next time somebody shortens the list.
INSTALLED = ("openRepoShape",)

#: The line `--install` prints instead of placing those two, byte for byte.
#: README.md carries the same one, and
#: `tests/test_repo_hygiene.py::test_the_openrepotools_install_line_is_the_
#: same_everywhere` is what holds the copies together.
OPENREPOTOOLS_INSTALL = (
    "curl -fsSL https://raw.githubusercontent.com/opensoft/openRepoTools/"
    "main/openRepoTools | bash -s -- --install")

USAGE_LINES = (
    "openRepoShape <Project> [--org <org>] [setup-project.py options] [-- <scaffold flags>]",
    "openRepoShape --install            install (or update) this command into ~/.local/bin",
    "openRepoShape --doctor             check this machine and stop; creates nothing",
    "openRepoShape --help | --version",
)

#: Same two reasons as `test_setup_sh.py`: no bash, or a Windows runner where
#: bash.exe exists and the `python3` the fetched `setup.sh` calls does not.
#: The command is a macOS/Linux/WSL2 convenience and has no Windows twin —
#: there the way in is `py setup-project.py`, which needs no command to fetch
#: it because it IS the file you downloaded.
pytestmark = [pytest.mark.skipif(shutil.which("bash") is None,
                                 reason="openRepoShape is a bash script"),
              WINDOWS_SKIP]


def command_env(home: Path | None = None, env: dict | None = None,
                setup_sh: Path | None = SETUP) -> dict:
    """The environment this suite controls, for a run of the command.

    Every `$OPENREPOSHAPE_*` variable the command reads is cleared first, so a
    developer's own shell cannot change what these tests assert, and
    `$OPENREPOSHAPE_SETUP_SH` is then pointed at this checkout: no test can
    reach the network even by mistake. `setup_sh=None` leaves it unset, which
    is the FETCHING path — taken only by the tests that hold the
    `offline_github` fixture, whose fake `gh` and refusing `curl` are what
    keeps that path offline too.
    """
    environ = dict(os.environ)
    for name in ("OPENREPOSHAPE_ORG", "OPENREPOSHAPE_REF", "OPENREPOSHAPE_REPO",
                 "OPENREPOSHAPE_BIN_DIR", "OPENREPOSHAPE_SETUP_SH"):
        environ.pop(name, None)
    if setup_sh is not None:
        environ["OPENREPOSHAPE_SETUP_SH"] = str(setup_sh)
    environ.setdefault("GIT_AUTHOR_NAME", "openRepoShape tests")
    environ.setdefault("GIT_AUTHOR_EMAIL", "tests@openreposhape.invalid")
    environ.setdefault("GIT_COMMITTER_NAME", "openRepoShape tests")
    environ.setdefault("GIT_COMMITTER_EMAIL", "tests@openreposhape.invalid")
    if home is not None:
        environ["HOME"] = str(home)
    environ.update(env or {})
    return environ


def run_cmd(*args: str, home: Path | None = None, env: dict | None = None,
            setup_sh: Path | None = SETUP) -> subprocess.CompletedProcess:
    """The command, run from its file, with that environment.

    `input=""` means stdin is a pipe rather than a terminal, which is what the
    no-tty refusals are about.
    """
    return subprocess.run(["bash", str(COMMAND), *args], capture_output=True,
                          text=True, check=False, input="",
                          env=command_env(home, env, setup_sh))


# --- what it says about itself ---------------------------------------------

def test_help_prints_every_usage_line():
    """Every line `--help` promises, including the `--doctor` one #59
    added: a usage line nobody asserts on is a usage line that can go
    stale without anything noticing."""
    result = run_cmd("--help")
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    for line in USAGE_LINES:
        assert line in lines, f"--help never printed:\n    {line}"


def test_help_points_at_openrepotools():
    """`--help` used to list the other two commands; it names their new home.

    A person who read the old `--help`, or who has `park` on PATH from an
    install before 2026-09-10, comes here first when it stops being placed.
    `--help` saying nothing at all would send them looking for a defect in
    this command, so it says which repository owns those verbs now and prints
    the one line that installs them (#92).
    """
    result = run_cmd("--help")
    assert result.returncode == 0, result.stderr
    assert "places ONE command" in result.stdout
    assert "opensoft/openRepoTools" in result.stdout
    assert "`park` and `resume`" in result.stdout
    assert OPENREPOTOOLS_INSTALL in result.stdout, (
        "--help must print openRepoTools' install line, byte for byte")


def test_version_names_the_repository_and_the_ref():
    """There is no version number in this repository, so the honest answer to
    `--version` is WHICH BYTES it will run: repo and ref."""
    result = run_cmd("--version")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "openRepoShape (opensoft/openRepoShape @ main)"


def test_version_follows_the_ref_it_would_fetch():
    result = run_cmd("--version", env={"OPENREPOSHAPE_REF": "v1.2.3"})
    assert result.returncode == 0, result.stderr
    assert "@ v1.2.3" in result.stdout


# --- --install --------------------------------------------------------------

def test_install_writes_an_executable_copy(tmp_path):
    """Every name in `INSTALLED`, each 755 and byte-identical to this
    checkout's.

    A copy that is not executable is not a command, and a near-copy is a
    command whose refusals nobody reviewed — so the bytes are compared rather
    than the presence of a file.
    """
    result = run_cmd("--install", home=tmp_path)
    assert result.returncode == 0, result.stderr
    for name in INSTALLED:
        target = tmp_path / ".local" / "bin" / name
        assert target.is_file(), result.stdout + f" (missing {name})"
        assert stat.S_IMODE(target.stat().st_mode) == 0o755, name
        assert target.read_bytes() == (REPO / name).read_bytes(), name
        assert f"{name}: installed at" in result.stdout
    assert f"openRepoShape: {len(INSTALLED)} of {len(INSTALLED)} placed" \
        in result.stdout, (
        "a person reading N lines cannot tell whether an N+1th was meant to "
        "be there; the count says so, and it says so at one as well (#92)")


def test_installing_twice_changes_nothing(tmp_path):
    """Idempotent BY CONTENT, per file: the second run must not rewrite one
    that already holds these bytes, and must say so rather than claim an
    install."""
    first = run_cmd("--install", home=tmp_path)
    assert first.returncode == 0, first.stderr
    second = run_cmd("--install", home=tmp_path)
    assert second.returncode == 0, second.stderr
    for name in INSTALLED:
        assert f"{name}: already installed at" in second.stdout, name
    assert second.stdout.count("unchanged") == len(INSTALLED)


@pytest.mark.parametrize("name", INSTALLED)
def test_install_replaces_a_copy_that_has_drifted(tmp_path, name):
    """Per file, and only the one that drifted: an install that rewrote every
    file every time would have nothing to say about which one was stale."""
    assert run_cmd("--install", home=tmp_path).returncode == 0
    target = tmp_path / ".local" / "bin" / name
    target.write_text(target.read_text(encoding="utf-8") + "# drift\n",
                      encoding="utf-8")
    result = run_cmd("--install", home=tmp_path)
    assert result.returncode == 0, result.stderr
    assert f"{name}: updated at" in result.stdout
    assert target.read_bytes() == (REPO / name).read_bytes()
    for other in INSTALLED:
        if other != name:
            assert f"{other}: already installed at" in result.stdout, other


def test_bin_dir_overrides_where_it_lands(tmp_path):
    result = run_cmd("--install", home=tmp_path,
                     env={"OPENREPOSHAPE_BIN_DIR": str(tmp_path / "elsewhere")})
    assert result.returncode == 0, result.stderr
    for name in INSTALLED:
        assert (tmp_path / "elsewhere" / name).is_file(), name
        assert not (tmp_path / ".local" / "bin" / name).exists(), name


def test_install_points_at_openrepotools(tmp_path):
    """THE POINTER IS TEXT, and both halves of that are asserted here (#92).

    `park` and `resume` are opensoft/openRepoTools' now, so `--install` says
    where they come from — after the count line and before the PATH note,
    which is the order the three facts are useful in: what was placed, what
    was not, and how to reach either. The line is compared to
    `OPENREPOTOOLS_INSTALL` rather than searched for, because it is a line
    somebody copies and pastes.

    AND IT DOES NOT FETCH FROM THAT REPOSITORY. This is the FETCHING install —
    run from stdin, so every file is requested — through a `gh` and a `curl`
    that append every argument list they are handed to a log. The log has to
    hold at least one request, or the test proves nothing, and no request in
    it may name openRepoTools: a command that reached into another repository
    to finish its own install would make this standard depend on its tools at
    runtime, which is the direction the carve exists to forbid.
    """
    bin_dir = tmp_path / "bin"
    log = tmp_path / "requests.log"
    served = fake_github(tmp_path, INSTALLED, log=log)
    result = subprocess.run(
        ["bash", "-s", "--", "--install"], capture_output=True, text=True,
        check=False, input=COMMAND.read_text(encoding="utf-8"),
        cwd=str(tmp_path),
        env=command_env(home=tmp_path, setup_sh=None,
                        env={**served,
                             "OPENREPOSHAPE_BIN_DIR": str(bin_dir)}))
    assert result.returncode == 0, result.stderr + result.stdout

    lines = result.stdout.splitlines()
    count = f"openRepoShape: {len(INSTALLED)} of {len(INSTALLED)} placed"
    at = [i for i, line in enumerate(lines) if line.startswith(count)]
    assert len(at) == 1, result.stdout
    assert lines[at[0] + 1] == (
        "  park and resume are installed by openRepoTools, not by this "
        "command:"), result.stdout
    assert lines[at[0] + 2] == f"    {OPENREPOTOOLS_INSTALL}", result.stdout
    assert lines[at[0] + 3].endswith("is not on $PATH. Add it:"), (
        "the PATH note must still come last:\n" + result.stdout)

    requests = log.read_text(encoding="utf-8")
    assert requests.strip(), "nothing was requested, so nothing is proven"
    assert "openRepoTools" not in requests, (
        "--install made a request naming openRepoTools:\n" + requests)


def test_install_says_how_to_put_it_on_path(tmp_path):
    result = run_cmd("--install", home=tmp_path)
    assert f'export PATH="{tmp_path}/.local/bin:$PATH"' in result.stdout


def test_install_from_a_file_never_calls_gh(tmp_path):
    """`--install` run from a file copies THOSE bytes. A machine with no `gh`
    — or no network — must still be able to install the command, so a `gh` on
    $PATH that fails loudly may not be reached at all."""
    shim = tmp_path / "bin"
    shim.mkdir()
    marker = tmp_path / "gh-was-called"
    # QUOTED for the reason `fake_github`'s log is: an unquoted path with a
    # space in it makes `touch` create two files, neither of them $marker, and
    # a witness nobody can find is a test that passes without guarding.
    (shim / "gh").write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 1\n",
                             encoding="utf-8")
    (shim / "gh").chmod(0o755)
    result = run_cmd("--install", home=tmp_path,
                     env={"PATH": f"{shim}:{os.environ['PATH']}"})
    assert result.returncode == 0, result.stderr
    assert not marker.exists(), "--install from a file must not call gh"
    for name in INSTALLED:
        assert (tmp_path / ".local" / "bin" / name).is_file(), name


def test_install_refuses_to_also_scaffold(tmp_path):
    result = run_cmd("--install", "Atlas", "--org", "TestOrg", home=tmp_path)
    assert result.returncode == 2
    assert "--install takes no other arguments" in result.stderr


# --- the real thing, offline ------------------------------------------------

def test_it_scaffolds_through_setup_sh(tmp_path):
    """The whole point: the positional <Project> becomes `--project`, every
    other argument reaches setup.sh unchanged, and three bare repositories and
    a bootstrapped clone come out the other end."""
    remotes = tmp_path / "remotes"
    result = run_cmd("Atlas", "--org", "TestOrg", "--yes",
                     "--local-remote-dir", str(remotes),
                     "--into", str(tmp_path), "--elected-by", "Test")
    assert result.returncode == 0, result.stderr + result.stdout
    for name in ("Atlas.git", "Atlas-spec.git", "Atlas-code.git"):
        assert (remotes / name).is_dir(), f"{name} was not created"
    clone = tmp_path / "Atlas"
    assert (clone / "project.yaml").is_file()
    manifest = (clone / "project.yaml").read_text(encoding="utf-8")
    assert "repository: TestOrg/Atlas" in manifest
    assert 'elected_by: "Test"' in manifest


def test_scaffold_flags_after_a_double_dash_still_reach_the_scaffold(tmp_path):
    """`-- <scaffold flags>` is setup.sh's own passthrough, and this command
    must not eat it."""
    result = run_cmd("Atlas", "--org", "TestOrg", "--yes",
                     "--local-remote-dir", str(tmp_path / "remotes"),
                     "--into", str(tmp_path),
                     "--", "--reference", "a-staged-fragment.md")
    assert result.returncode == 0, result.stderr + result.stdout
    manifest = (tmp_path / "Atlas" / "project.yaml").read_text(encoding="utf-8")
    assert 'reference: "a-staged-fragment.md"' in manifest


def test_a_family_value_is_never_taken_as_the_project(tmp_path):
    """`--family` joins the value-taking case list, and that is the point.

    Anything beginning with a dash that the list does NOT name travels as a
    lone flag, so `openRepoShape Atlas --family InkRouter --org Northwind`
    would have handed `InkRouter` to the `*)` branch as a second positional
    and been refused as "two project names" - a person who typed one project
    name being told they typed two. The same defect `--into`, `--visibility`
    and the rest are on the list for.

    No `--yes`: the run reaches setup-project.py's confirmation with no
    terminal to answer it and stops there, which is what proves both values
    were parsed as values without creating anything.
    """
    result = run_cmd("Atlas", "--family", "InkRouter", "--org", "Northwind",
                     "--local-remote-dir", str(tmp_path / "remotes"),
                     "--into", str(tmp_path))
    assert result.returncode == 2
    assert "two project names" not in result.stderr, (
        "--family's value was read as a second <Project>")
    assert "[ok] family       InkRouter" in result.stdout
    assert "no terminal to confirm on" in result.stderr
    assert not (tmp_path / "remotes").exists()


# --- --doctor ---------------------------------------------------------------

def test_doctor_passes_through_without_an_org(tmp_path):
    """`openRepoShape --doctor` is the "install program" without a second
    program: the preflight, the offers it makes, and stop.

    This command insists on an organisation and on a `<Project>` because a
    run that gets past it CREATES three repositories. A doctor run creates
    nothing, so both refusals are skipped rather than answered - and with
    `input=""` there is no terminal here either, so the preflight makes no
    offer and installs nothing, which is the rule this whole suite runs
    under.
    """
    remotes = tmp_path / "remotes"
    result = run_cmd("--doctor", "--local-remote-dir", str(remotes))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "(1) preflight" in result.stdout
    assert "this machine is ready." in result.stdout
    assert "organisation to scaffold into" not in result.stdout, (
        "--doctor prompted for an organisation it has no use for")
    assert "no organisation to scaffold into" not in result.stderr
    assert "no <Project> given" not in result.stderr
    assert not remotes.exists()


def test_doctor_forwards_an_org_it_was_given(tmp_path):
    """A flag this command ATE would be a flag the person has to type twice
    to find out about. The doctor ignores it; it still travels."""
    result = run_cmd("--doctor", "--org", "TestOrg",
                     "--local-remote-dir", str(tmp_path / "remotes"))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "(2) organisation" not in result.stdout


# --- the refusals -----------------------------------------------------------

def test_no_org_and_no_terminal_refuses_before_setup_sh_runs(tmp_path):
    """An organisation is never guessed: the wrong one creates three
    repositories in somebody else's namespace."""
    result = run_cmd("Atlas", "--local-remote-dir", str(tmp_path / "remotes"))
    assert result.returncode == 2
    assert "--org" in result.stderr
    assert "openRepoShape setup" not in result.stdout, (
        "setup.sh should not have been reached at all")
    assert not (tmp_path / "remotes").exists()


def test_the_org_can_come_from_the_environment(tmp_path):
    """$OPENREPOSHAPE_ORG answers for `--org`. The run then gets as far as
    setup.sh's confirmation and stops there, with nothing created — which is
    what proves the organisation was resolved."""
    result = run_cmd("Atlas", "--local-remote-dir", str(tmp_path / "remotes"),
                     "--into", str(tmp_path),
                     env={"OPENREPOSHAPE_ORG": "TestOrg"})
    assert result.returncode == 2
    assert "organisation TestOrg" in result.stdout
    assert "no terminal to confirm on" in result.stderr
    assert not (tmp_path / "remotes").exists()


def test_no_project_and_no_terminal_refuses_with_the_usage(tmp_path):
    result = run_cmd("--org", "TestOrg",
                     "--local-remote-dir", str(tmp_path / "remotes"))
    assert result.returncode == 2
    assert "no <Project> given" in result.stderr
    assert USAGE_LINES[0] in result.stderr
    assert not (tmp_path / "remotes").exists()


def test_a_local_setup_sh_that_is_not_a_file_refuses(tmp_path):
    result = run_cmd("Atlas", "--org", "TestOrg",
                     env={"OPENREPOSHAPE_SETUP_SH": str(tmp_path / "nope.sh")})
    assert result.returncode == 2
    assert "not a file" in result.stderr


# --- the fetch order, asserted against the text -----------------------------

def test_the_api_is_tried_before_the_raw_url():
    """ORDER IS THE RULE. `gh api` is authenticated and works inside an
    organisation whose policy blocks raw.githubusercontent.com; the raw URL is
    the fallback for a machine with no `gh` on it. Fetching cannot be tested
    offline, so the order is read out of the script itself."""
    text = COMMAND.read_text(encoding="utf-8")
    body = text.split("fetch_from_repo() {", 1)[1].split("\n}", 1)[0]
    assert "gh api" in body and "curl -fsSL" in body
    assert body.index("gh api") < body.index("curl -fsSL"), (
        "the raw URL is fetched before the API in fetch_from_repo(); the "
        "authenticated call must be tried first")
    assert "raw.githubusercontent.com" in body


def test_it_forwards_the_ref_so_setup_sh_clones_the_same_commit():
    """Fetched at $OPENREPOSHAPE_REF, setup.sh must self-bootstrap its checkout
    at that same ref, or the script that runs and the standard it clones are
    two different commits."""
    text = COMMAND.read_text(encoding="utf-8")
    assert '--shape-ref "$REF"' in text


# --- the fetch path, offline, through a fake `gh` ---------------------------

#: What the stub `setup.sh` prints. It says WHERE it ran from, because the
#: defect #74 is about that directory: `openRepoShape` fetched into a
#: temporary directory it had already deleted.
STUB_MARKER = "STUB-SETUP-RAN"

STUB_SETUP_SH = """#!/usr/bin/env bash
printf '%s in %s args: %s\\n' '{marker}' "$(cd "$(dirname "$0")" && pwd)" "$*"
""".format(marker=STUB_MARKER)


def fake_github(tmp_path, served_names, log: Path | None = None) -> dict:
    """A fake `gh` serving exactly `served_names`, and a `curl` that refuses.

    Factored out of the fixture so one test can WITHHOLD a file: `--install`
    places every one of them or none (#82, F10 of the review on #83), and the
    only way to prove "or none" is a server that cannot answer for one of
    them. `served_names` may be EMPTY, which is what withholding looks like
    now that `INSTALLED` is one name (#92).

    `log`, when given, is a file both fakes APPEND every argument list to, so
    a test can assert on what was actually requested rather than on what the
    script looks like. `test_install_points_at_openrepotools` is the caller:
    the pointer it prints must not become a fetch.
    """
    served = tmp_path / "served"
    served.mkdir(exist_ok=True)
    (served / "setup.sh").write_text(STUB_SETUP_SH, encoding="utf-8")
    for name in served_names:
        (served / name).write_bytes((REPO / name).read_bytes())

    fake = tmp_path / "fake-path"
    fake.mkdir(exist_ok=True)
    routes = "".join(
        f"*/contents/{name}\\?*) exec cat '{served / name}' ;;\n"
        for name in ("setup.sh", *served_names))

    #: QUOTED, like the `exec cat` route above it: `tmp_path` is pytest's and
    #: a `--basetemp` (or a $TMPDIR) with a space in it would otherwise split
    #: the redirection target, so the log would land in the wrong place and
    #: the assertion that reads it would pass on an empty file.
    def logging(program):
        return "" if log is None else \
            f'printf \'{program} %s\\n\' "$*" >> \'{log}\'\n'

    (fake / "gh").write_text(
        "#!/bin/sh\n"
        + logging("gh") +
        'case "$*" in\n'
        + routes +
        "esac\n"
        'printf \'fake gh: unexpected call: %s\\n\' "$*" >&2\n'
        "exit 1\n", encoding="utf-8")
    (fake / "gh").chmod(0o755)
    (fake / "curl").write_text(
        "#!/bin/sh\n"
        + logging("curl") +
        "printf 'fake curl: no test here may reach the network\\n' >&2\n"
        "exit 1\n", encoding="utf-8")
    (fake / "curl").chmod(0o755)
    return {"PATH": f"{fake}{os.pathsep}{os.environ['PATH']}"}


@pytest.fixture
def offline_github(tmp_path):
    """A fake `gh` first on `$PATH`, and a `curl` that refuses.

    `fetch_from_repo` tries `gh api` before the raw URL, so a `gh` that
    answers the calls the command makes is the whole of the server these tests
    need: `contents/setup.sh` comes back as a stub that says where it was run
    from, and `contents/<command>` as this checkout's own bytes for every file
    `--install` places. `curl` is shadowed by a script that exits 1 — belt and
    braces, so that a fake `gh` which stopped matching could never quietly
    become a real request to raw.githubusercontent.com.
    """
    return fake_github(tmp_path, INSTALLED)


def test_the_fetched_setup_sh_lands_in_a_workdir_that_still_exists(offline_github):
    """#74: `workdir()` set its EXIT trap inside a `$(...)` SUBSHELL.

    The trap therefore fired the instant the substitution closed, `rm -rf`
    took the directory away before `fetch_from_repo` could write into it, and
    every run WITHOUT `$OPENREPOSHAPE_SETUP_SH` — which is every real run —
    died with `No such file or directory` and then the misleading `could not
    fetch setup.sh`. Two halves of one fact are asserted here: the fetched
    script RAN, and the directory it ran from is gone AFTERWARDS — the trap
    belongs to the main shell, so it fires at the end and not in the middle.
    """
    result = run_cmd("--doctor", setup_sh=None, env=offline_github)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "No such file or directory" not in result.stdout + result.stderr
    assert "could not fetch" not in result.stderr
    match = re.search(rf"{STUB_MARKER} in (.+) args: (.*)", result.stdout)
    assert match, ("the fetched setup.sh never ran:\n"
                   + result.stdout + result.stderr)
    ran_in, forwarded = match.group(1), match.group(2).split()
    assert "--doctor" in forwarded, forwarded
    assert not Path(ran_in).exists(), (
        f"{ran_in} outlived the command; the EXIT trap did not fire")


def test_a_failed_fetch_replaces_nothing(tmp_path):
    """F10 of the review on #83, AND THAT IT SURVIVED THE CARVE (#92).

    One file at a time, dying on the first fetch that failed, left a person
    with a NEW `openRepoShape` and no `park` — a half-install that prints
    `installed at` and is not one — with nothing on screen to say which file
    was missing. The collection that fixed it is kept at one installable, so
    this is the same test with the whole of `INSTALLED` withheld: the refusal
    names the file, nothing is placed, and nothing already in that directory
    is touched.

    TWO WITNESSES, and the second is the carve's own. The older
    `openRepoShape` is what "nothing was replaced" is a claim about. The
    `park` beside it is what an install before 2026-09-10 left there, and it
    must come out byte for byte: this command does not place `park`, so it
    also does not update, truncate or tidy one away — that file is
    opensoft/openRepoTools' business and a person's working copy until its
    installer replaces it.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "openRepoShape").write_text("# an older copy\n",
                                           encoding="utf-8")
    (bin_dir / "park").write_text("# placed by an install before the carve\n",
                                  encoding="utf-8")
    withheld = fake_github(tmp_path, [])
    result = subprocess.run(
        ["bash", "-s", "--", "--install"], capture_output=True, text=True,
        check=False, input=COMMAND.read_text(encoding="utf-8"),
        cwd=str(tmp_path),
        env=command_env(home=tmp_path, setup_sh=None,
                        env={**withheld,
                             "OPENREPOSHAPE_BIN_DIR": str(bin_dir)}))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "could not fetch openRepoShape" in result.stderr
    assert "NOTHING was installed" in result.stderr
    assert "nothing already installed was replaced" in result.stderr
    assert (bin_dir / "openRepoShape").read_text(encoding="utf-8") == \
        "# an older copy\n", "the older copy was replaced by a half-install"
    assert (bin_dir / "park").read_text(encoding="utf-8") == \
        "# placed by an install before the carve\n", (
        "a park this command no longer places was written to anyway")
    assert "placed" not in result.stdout


def test_all_or_none_still_holds_at_more_than_one_installable(tmp_path):
    """F10 OF THE REVIEW ON #83, KEPT HONEST AFTER THE CARVE (#92).

    At one installable, "collect everything, then place it" and "fetch and
    place one file at a time, dying on the first failure" cannot be told
    apart by any test: there is one file, so there is no half-install to
    produce. `test_a_failed_fetch_replaces_nothing` therefore covers the
    refusal but not the STRUCTURE, and the pre-#82 shape would pass this
    suite green — which is the whole of the argument for keeping
    `collect_commands` when the list went back to one name.

    So this test lengthens the list. A COPY of the shim in a temporary
    directory gets a second, synthetic name in `INSTALLABLES`; the copy is
    run FROM ITS FILE, so `openRepoShape` is taken from the sibling beside it
    and only `witness` has to be fetched — and the fake server does not serve
    `witness`. Nothing may be placed: the older `openRepoShape` already in
    the bin directory has to come out byte for byte, and the refusal has to
    name the file it could not get. A shim that placed per file would have
    overwritten that copy before ever discovering `witness` was missing.

    THE COPY IS THE POINT. Editing the real `INSTALLABLES` would be a test
    that changes the thing it measures; this one asserts a property of the
    machinery, at a list length this repository does not currently ship.
    """
    shimdir = tmp_path / "shimdir"
    shimdir.mkdir()
    shim = shimdir / "openRepoShape"
    source = COMMAND.read_text(encoding="utf-8")
    assert "\nINSTALLABLES=(openRepoShape)\n" in source, (
        "the array this test lengthens has moved or been reshaped")
    shim.write_text(
        source.replace("\nINSTALLABLES=(openRepoShape)\n",
                       "\nINSTALLABLES=(openRepoShape witness)\n", 1),
        encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "openRepoShape").write_text("# an older copy\n",
                                           encoding="utf-8")
    withheld = fake_github(tmp_path, ["openRepoShape"])
    result = subprocess.run(
        ["bash", str(shim), "--install"], capture_output=True, text=True,
        check=False, input="",
        env=command_env(home=tmp_path, setup_sh=None,
                        env={**withheld,
                             "OPENREPOSHAPE_BIN_DIR": str(bin_dir)}))
    # THE STRUCTURAL ASSERTION FIRST, and deliberately: a per-file installer
    # refuses too, and it may refuse in words that look right. What tells the
    # two shapes apart is whether the file it COULD place was placed before
    # it discovered the one it could not.
    assert (bin_dir / "openRepoShape").read_text(encoding="utf-8") == \
        "# an older copy\n", (
        "a file that COULD be placed was placed before the missing one was "
        "discovered; that is the half-install F10 removed\n"
        + result.stdout + result.stderr)
    assert not (bin_dir / "witness").exists()
    assert "placed" not in result.stdout
    assert result.returncode == 2, result.stdout + result.stderr
    assert "could not fetch witness" in result.stderr, result.stderr
    assert "NOTHING was installed" in result.stderr


def test_install_from_stdin_fetches_itself_into_a_live_workdir(offline_github,
                                                               tmp_path):
    """The other caller of `workdir()`, and the documented install line:
    `gh api …/contents/openRepoShape … | bash -s -- --install`.

    Run from stdin there is no file to copy from, so `install_commands`
    fetches every name in `INSTALLED` at this ref into the temporary
    directory: the same directory #74 had already deleted, which made the
    one-line install impossible on every machine.
    """
    bin_dir = tmp_path / "bin"
    result = subprocess.run(
        ["bash", "-s", "--", "--install"], capture_output=True, text=True,
        check=False, input=COMMAND.read_text(encoding="utf-8"),
        # cwd: `bash -s` leaves $BASH_SOURCE unset, so the command's $SELF is
        # the literal `bash`, and `[ -f "$SELF" ]` must be false for the
        # fetching branch to be the one under test. A directory holding
        # nothing of that name is what guarantees it.
        cwd=str(tmp_path),
        env=command_env(home=tmp_path, setup_sh=None,
                        env={**offline_github,
                             "OPENREPOSHAPE_BIN_DIR": str(bin_dir)}))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "No such file or directory" not in result.stdout + result.stderr
    assert "could not fetch" not in result.stderr
    for name in INSTALLED:
        target = bin_dir / name
        assert target.is_file(), result.stdout + result.stderr + f" ({name})"
        assert stat.S_IMODE(target.stat().st_mode) == 0o755, name
        assert target.read_bytes() == (REPO / name).read_bytes(), name
        assert f"{name}: installed at" in result.stdout
