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
network even if the fake `gh` stops matching. What a fake `gh` cannot show is
which way round the real two are tried, so THAT rule — the authenticated call
first, because an organisation can block raw.githubusercontent.com and still
have a working `gh` — stays asserted against the script's text, the way this
suite guards other things it cannot run.
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
    result = run_cmd("--install", home=tmp_path)
    assert result.returncode == 0, result.stderr
    target = tmp_path / ".local" / "bin" / "openRepoShape"
    assert target.is_file(), result.stdout
    assert stat.S_IMODE(target.stat().st_mode) == 0o755
    assert target.read_bytes() == COMMAND.read_bytes()
    assert "installed at" in result.stdout


def test_installing_twice_changes_nothing(tmp_path):
    """Idempotent BY CONTENT: the second run must not rewrite a file that
    already holds these bytes, and must say so rather than claim an install."""
    first = run_cmd("--install", home=tmp_path)
    assert first.returncode == 0, first.stderr
    second = run_cmd("--install", home=tmp_path)
    assert second.returncode == 0, second.stderr
    assert "unchanged" in second.stdout


def test_install_replaces_a_copy_that_has_drifted(tmp_path):
    assert run_cmd("--install", home=tmp_path).returncode == 0
    target = tmp_path / ".local" / "bin" / "openRepoShape"
    target.write_text(target.read_text(encoding="utf-8") + "# drift\n",
                      encoding="utf-8")
    result = run_cmd("--install", home=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "updated" in result.stdout
    assert target.read_bytes() == COMMAND.read_bytes()


def test_bin_dir_overrides_where_it_lands(tmp_path):
    result = run_cmd("--install", home=tmp_path,
                     env={"OPENREPOSHAPE_BIN_DIR": str(tmp_path / "elsewhere")})
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "elsewhere" / "openRepoShape").is_file()
    assert not (tmp_path / ".local" / "bin" / "openRepoShape").exists()


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
    (shim / "gh").write_text(f"#!/bin/sh\ntouch {marker}\nexit 1\n",
                             encoding="utf-8")
    (shim / "gh").chmod(0o755)
    result = run_cmd("--install", home=tmp_path,
                     env={"PATH": f"{shim}:{os.environ['PATH']}"})
    assert result.returncode == 0, result.stderr
    assert not marker.exists(), "--install from a file must not call gh"


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


@pytest.fixture
def offline_github(tmp_path):
    """A fake `gh` first on `$PATH`, and a `curl` that refuses.

    `fetch_from_repo` tries `gh api` before the raw URL, so a `gh` that
    answers the one call the command makes is the whole of the server these
    tests need: `contents/setup.sh` comes back as a stub that says where it
    was run from, `contents/openRepoShape` as this checkout's own bytes.
    `curl` is shadowed by a script that exits 1 — belt and braces, so that a
    fake `gh` which stopped matching could never quietly become a real
    request to raw.githubusercontent.com.
    """
    served = tmp_path / "served"
    served.mkdir()
    (served / "setup.sh").write_text(STUB_SETUP_SH, encoding="utf-8")
    (served / "openRepoShape").write_bytes(COMMAND.read_bytes())

    fake = tmp_path / "fake-path"
    fake.mkdir()
    (fake / "gh").write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        f"*/contents/setup.sh\\?*) exec cat '{served / 'setup.sh'}' ;;\n"
        f"*/contents/openRepoShape\\?*) exec cat '{served / 'openRepoShape'}' ;;\n"
        "esac\n"
        'printf \'fake gh: unexpected call: %s\\n\' "$*" >&2\n'
        "exit 1\n", encoding="utf-8")
    (fake / "gh").chmod(0o755)
    (fake / "curl").write_text(
        "#!/bin/sh\n"
        "printf 'fake curl: no test here may reach the network\\n' >&2\n"
        "exit 1\n", encoding="utf-8")
    (fake / "curl").chmod(0o755)
    return {"PATH": f"{fake}{os.pathsep}{os.environ['PATH']}"}


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


def test_install_from_stdin_fetches_itself_into_a_live_workdir(offline_github,
                                                               tmp_path):
    """The other caller of `workdir()`, and the documented install line:
    `gh api …/contents/openRepoShape … | bash -s -- --install`.

    Run from stdin there is no file to copy from, so `install_self` fetches
    this path at this ref into the temporary directory — the same directory
    #74 had already deleted, which made the one-line install impossible on
    every machine.
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
    target = bin_dir / "openRepoShape"
    assert target.is_file(), result.stdout + result.stderr
    assert stat.S_IMODE(target.stat().st_mode) == 0o755
    assert target.read_bytes() == COMMAND.read_bytes()
    assert "installed at" in result.stdout
