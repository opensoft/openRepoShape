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
import shlex
import shutil
import stat
import subprocess

from pathlib import Path

import pytest

from conftest import BASH, BASH_SKIP, REPO, bash_path, git, native_path

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

#: THE FOUR THINGS THIS COMMAND DOES, in the order a person meets them, plus
#: the two that are about the command itself. The order is asserted nowhere —
#: `--help` is checked line by line — but it is the order the file carries,
#: and a reader of this tuple should see what a reader of `--help` sees.
USAGE_LINES = (
    "openRepoShape --install            install (or update) this command into ~/.local/bin",
    "openRepoShape --preflight          check this MACHINE and stop; creates nothing",
    "openRepoShape --doctor [<path>] [--json] [--placement-plan <file>]",
    "openRepoShape <Project> [--org <org>] [setup-project.py options] [-- <scaffold flags>]",
    "openRepoShape --help | --version",
)

#: The scaffold line specifically, for the refusals that print the usage at
#: somebody who was trying to scaffold. Named rather than indexed: the tuple
#: above is free to be reordered, and an index would silently start asserting
#: about a different line.
USAGE_SCAFFOLD = USAGE_LINES[3]

#: Every run is `BASH`: the `bash` on PATH, or on Windows Git Bash, with the
#: PATH Git Bash makes (`git_bash_session`), every path spelled the way Git
#: Bash spells it (`bash_path`) and every script a test writes for it given
#: `\n` line ends (`write_script`) (#585). A `bash -s` run names `BASH` as
#: its `executable` and keeps `bash` as its argv[0], so `$0` is the word
#: `bash`, as a pipe into it gives. The suite wore `WINDOWS_SKIP` until
#: then, and the command its one-line install places was said to work in
#: Git Bash with nothing having run it there. PowerShell still has no twin:
#: there the way in is `py setup-project.py`, the file you downloaded.
pytestmark = [BASH_SKIP, pytest.mark.usefixtures("git_bash_session")]


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
                 "OPENREPOSHAPE_BIN_DIR", "OPENREPOSHAPE_SETUP_SH",
                 "OPENREPOSHAPE_RECORD_REF"):
        environ.pop(name, None)
    if setup_sh is not None:
        environ["OPENREPOSHAPE_SETUP_SH"] = bash_path(setup_sh)
    environ.setdefault("GIT_AUTHOR_NAME", "openRepoShape tests")
    environ.setdefault("GIT_AUTHOR_EMAIL", "tests@openreposhape.invalid")
    environ.setdefault("GIT_COMMITTER_NAME", "openRepoShape tests")
    environ.setdefault("GIT_COMMITTER_EMAIL", "tests@openreposhape.invalid")
    if home is not None:
        environ["HOME"] = str(home)
    environ.update(env or {})
    return environ


def run_cmd(*args: str, home: Path | None = None, env: dict | None = None,
            setup_sh: Path | None = SETUP,
            command: Path = COMMAND) -> subprocess.CompletedProcess:
    """The command, run from its file, with that environment.

    `input=""` means stdin is a pipe rather than a terminal, which is what the
    no-tty refusals are about, and a session of its own means there is no
    controlling terminal either (#492): setup asks at that terminal when
    stdin is not one, and the terminal pytest was started from is nobody's
    answer.

    `command` is this checkout's file unless a test names an INSTALLED copy,
    which is how the record `--install` leaves beside one is read (#564).
    """
    return subprocess.run([BASH, bash_path(command), *args],
                          capture_output=True, text=True, check=False,
                          input="", env=command_env(home, env, setup_sh),
                          start_new_session=True)


def write_script(path: Path, text: str) -> None:
    """A script some bash will read, written with `\\n` line ends everywhere:
    `write_text` writes `\\r\\n` on Windows (#585)."""
    path.write_bytes(text.encode("utf-8"))


def assert_a_command(path: Path) -> None:
    """`--install` placed a command: mode 755, or under Git Bash, which
    keeps no mode bits (its drives are mounted `noacl`, so `chmod` changes
    nothing there), one bash's own `-x` says it will run (#585)."""
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o755, path
        return
    probe = subprocess.run([BASH, "-c", 'test -x "$1"', "-", bash_path(path)],
                           capture_output=True, check=False)
    assert probe.returncode == 0, f"bash will not run {path}"


def put_on_path(directory: Path, name: str, real: str) -> None:
    """`directory/name` runs the program at `real`, for a `$PATH` a test
    builds out of these and nothing else: a symlink, or on Windows a
    `#!/bin/sh` script that execs it (#585). A symlink there needs an
    elevated runner or Developer Mode, a copy of a Git Bash program cannot
    find the DLL it loads from its own directory, and `/bin/sh` is found
    through Git Bash's own mounts with nothing on `$PATH`."""
    link = directory / name
    if os.name != "nt":
        link.symlink_to(real)
        return
    write_script(link, "#!/bin/sh\nexec %s \"$@\"\n"
                 % shlex.quote(bash_path(real)))


# --- what it says about itself ---------------------------------------------

def test_help_prints_every_usage_line():
    """Every line `--help` promises, including the `--preflight` one #59
    added: a usage line nobody asserts on is a usage line that can go
    stale without anything noticing."""
    result = run_cmd("--help")
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    for line in USAGE_LINES:
        assert line in lines, f"--help never printed:\n    {line}"


def test_the_doctor_line_keeps_its_description_column():
    """#500 gave the doctor's synopsis its two flags, and the full form
    filled the column the other lines describe themselves in, so its
    description went (#546). It is back, on the line under the form and in
    that same column, where argparse puts the help of an option too long for
    it; the form itself stays one line."""
    lines = run_cmd("--help").stdout.splitlines()
    column = USAGE_LINES[0].index("install (or update)")
    assert USAGE_LINES[1].index("check this MACHINE") == column
    doctor = lines.index(next(line for line in USAGE_LINES if "--doctor" in line))
    assert lines[doctor + 1] == \
        " " * column + "diagnose a REPOSITORY against this standard", (
            lines[doctor:doctor + 2])


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
        assert_a_command(target)
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
        ["bash", "-s", "--", "--install"], executable=BASH,
        capture_output=True, text=True, check=False,
        input=COMMAND.read_text(encoding="utf-8"),
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
    assert f'export PATH="{bash_path(tmp_path)}/.local/bin:$PATH"' \
        in result.stdout


def test_install_from_a_file_never_calls_gh(tmp_path):
    """`--install` run from a file copies THOSE bytes. A machine with no `gh`
    — or no network — must still be able to install the command, so a `gh` on
    $PATH that fails loudly may not be FETCHED through.

    ONE CALL IS ALLOWED, AND IT IS NAMED: `gh auth status`, from the
    read-only machine report the install now ends with. That is a question
    about this machine and not a fetch, it happens after every byte is
    placed, and it cannot change the exit code — so the assertion is on WHAT
    was asked rather than on whether `gh` was reached, which is the stronger
    claim anyway.
    """
    shim = tmp_path / "bin"
    shim.mkdir()
    log = tmp_path / "gh-calls.log"
    # QUOTED for the reason `fake_github`'s log is: an unquoted path with a
    # space in it makes the redirection land somewhere else, and a witness
    # nobody can find is a test that passes without guarding.
    write_script(shim / "gh",
                 f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> '{log}'\nexit 1\n")
    (shim / "gh").chmod(0o755)
    result = run_cmd("--install", home=tmp_path,
                     env={"PATH": f"{shim}{os.pathsep}{os.environ['PATH']}"})
    assert result.returncode == 0, result.stderr
    called = log.read_text(encoding="utf-8").split("\n")[:-1] \
        if log.exists() else []
    assert called == ["auth status"], (
        "--install from a file must not FETCH through gh; the only call it "
        f"may make is the machine report's `gh auth status`. Got: {called}")
    for name in INSTALLED:
        assert (tmp_path / ".local" / "bin" / name).is_file(), name


def test_install_refuses_to_also_scaffold(tmp_path):
    result = run_cmd("--install", "Atlas", "--org", "TestOrg", home=tmp_path)
    assert result.returncode == 2
    assert "--install takes no other arguments" in result.stderr


@pytest.mark.parametrize("dangling", [False, True], ids=["live", "dangling"])
def test_install_refuses_a_target_that_is_a_symlink(tmp_path, dangling):
    """pipx places the openreposhape package's `openRepoShape` as a LINK
    into the package's own environment, in this same directory (#563).

    `cp` writes through a link, so an install over it would overwrite the
    package's command and leave the link standing. It is refused before
    anything is collected or placed, a dangling link too: the link stays as
    it was, the file it names keeps its bytes, nothing is recorded, and the
    refusal names both ways out.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    packaged = tmp_path / "pipx" / "venvs" / "openreposhape" / "bin" / \
        "openRepoShape"
    original = b"#!/usr/bin/env python3\n# the package's own command\n"
    if not dangling:
        packaged.parent.mkdir(parents=True)
        packaged.write_bytes(original)
    link = bin_dir / "openRepoShape"
    link.symlink_to(packaged)
    result = run_cmd("--install", home=tmp_path,
                     env={"OPENREPOSHAPE_BIN_DIR": bash_path(bin_dir),
                          "OPENREPOSHAPE_REF": "v9.9.9",
                          "OPENREPOSHAPE_RECORD_REF": "1"})
    assert result.returncode == 2, result.stdout + result.stderr
    said = " ".join(result.stderr.split())
    assert f"{bash_path(link)} is a symbolic link, so --install will not " \
        "copy this command through it" in said, said
    assert "pipx upgrade openreposhape" in said
    assert "pipx uninstall openreposhape" in said
    assert link.is_symlink()
    # Windows reads a link back with `\\?\` ahead of its target.
    assert os.readlink(link).removeprefix("\\\\?\\") == str(packaged)
    if not dangling:
        assert packaged.read_bytes() == original
    assert not packaged.with_name("openRepoShape.ref").exists()
    assert sorted(path.name for path in bin_dir.iterdir()) == \
        ["openRepoShape"]
    assert "placed" not in result.stdout


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


# --- a bare run ------------------------------------------------------------

def test_a_bare_run_prints_the_usage_and_exits_one():
    """No arguments at all: say what this command does, and stop.

    It used to fall through into the scaffold path and refuse "no
    organisation to scaffold into" — an answer about a run the person had not
    asked for, and about the one of four things this command does that is
    hardest to undo. Exit 1 rather than 0 because typing a command and
    getting a page of text is a mistake being reported; `--help` is the same
    page and exits 0, because asking is not.
    """
    result = run_cmd()
    assert result.returncode == 1, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    for line in USAGE_LINES:
        assert line in lines, f"a bare run never printed:\n    {line}"
    assert "no organisation to scaffold into" not in result.stderr


def test_a_bare_run_fetches_nothing(tmp_path):
    """And it stops BEFORE anything is fetched.

    The fake `gh` and `curl` here log every call they get, so "nothing was
    fetched" is asserted against what was actually asked for rather than
    against the absence of an error — a usage page printed after a
    round-trip to github.com would look identical on screen.
    """
    log = tmp_path / "calls.log"
    served = fake_github(tmp_path, INSTALLED, log=log)
    result = subprocess.run(
        [BASH, bash_path(COMMAND)], capture_output=True, text=True,
        check=False, input="",
        env=command_env(home=tmp_path, setup_sh=None, env=served))
    assert result.returncode == 1, result.stdout + result.stderr
    assert USAGE_LINES[0] in result.stdout
    assert not log.exists(), (
        f"a bare run called out to the network:\n{log.read_text()}")


@pytest.mark.parametrize("args", [
    ("Atlas",),
    ("--org", "TestOrg"),
    ("--visibility", "private"),
])
def test_any_scaffold_argument_keeps_the_old_behaviour(args, tmp_path):
    """One argument is enough to mean a scaffold, refusals included.

    A person who typed something meant something, and answering them with a
    usage page instead of the refusal they earned would hide WHICH of their
    arguments was the problem — which is the whole value of the refusal.
    """
    result = run_cmd(*args, "--local-remote-dir", str(tmp_path / "remotes"))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED:" in result.stderr, result.stderr
    assert not (tmp_path / "remotes").exists()


def test_help_still_exits_zero():
    """The same page, and asking for it is not a mistake."""
    assert run_cmd("--help").returncode == 0


# --- the machine report `--install` ends with -------------------------------

#: The external programs `--install` itself runs, symlinked into the
#: restricted `$PATH` the machine-report tests build. Everything else it uses
#: is a bash builtin. The list is short because the installer is: make a
#: temporary directory, copy a file into place, compare, chmod, tidy up.
#: `tests/test_setup_sh.py::test_the_shim_refuses_before_cloning_when_git_is_
#: missing` is the precedent for the whole shape of this — an absolute bash
#: and a `$PATH` the test owns entirely, because there is no other way to
#: make `command -v git` answer "no" on a machine that has git.
INSTALL_NEEDS = ("mktemp", "cp", "chmod", "cmp", "mkdir", "rm", "dirname")


def machine_path(tmp_path, present, logged_in=True) -> dict:
    """A `$PATH` holding `present` and nothing else answerable.

    Every fake LOGS ITS OWN ARGV AND THEN FAILS LOUDLY. `command -v`
    executes nothing, so a report that only asks whether a program exists
    leaves that log empty — and anything that RAN one wrote a line into it,
    which is how "the report never runs an installer" is asserted rather
    than assumed. `gh` is the one exception by design: a login state can
    only be learnt by asking, so `gh auth status` is the single call allowed
    to happen, and `logged_in` is its exit code.
    """
    binaries = tmp_path / "machine-path"
    binaries.mkdir(exist_ok=True)
    log = tmp_path / "ran.log"
    for name in INSTALL_NEEDS:
        real = shutil.which(name)
        assert real, f"this machine has no {name}, which --install needs"
        if not (binaries / name).exists():
            put_on_path(binaries, name, real)
    for name in present:
        script = binaries / name
        if name == "gh":
            write_script(
                script,
                "#!/bin/sh\n"
                f"printf 'gh %s\\n' \"$*\" >> '{log}'\n"
                'case "$*" in "auth status") exit '
                f'{0 if logged_in else 1};; esac\n'
                "exit 1\n")
        else:
            write_script(
                script,
                "#!/bin/sh\n"
                f"printf '{name} %s\\n' \"$*\" >> '{log}'\n"
                f"printf 'fake {name} was EXECUTED by a read-only report\\n' >&2\n"
                "exit 1\n")
        script.chmod(0o755)
    return {"PATH": str(binaries), "_log": str(log)}


def install_with_machine(tmp_path, present, logged_in=True):
    """`--install` from this file, onto a $PATH holding only `present`."""
    env = machine_path(tmp_path, present, logged_in)
    log = Path(env.pop("_log"))
    bin_dir = tmp_path / "bin"
    # The bash by ABSOLUTE path: `subprocess` resolves a bare argv[0] against
    # the CHILD's PATH, and this one holds no bash on purpose.
    result = subprocess.run(
        [BASH, bash_path(COMMAND), "--install"],
        capture_output=True, text=True, check=False, input="",
        env=command_env(home=tmp_path, setup_sh=None,
                        env={**env, "OPENREPOSHAPE_BIN_DIR": str(bin_dir)}))
    return result, log, bin_dir


def test_install_ends_with_a_machine_report(tmp_path):
    """Four lines, and every one of them either `present` or `MISSING`."""
    result, _log, bin_dir = install_with_machine(
        tmp_path, ("git", "gh", "python3", "git-filter-repo"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert (bin_dir / "openRepoShape").is_file()
    body = result.stdout
    assert "  machine:" in body
    for name in ("git", "gh", "python3", "git-filter-repo"):
        assert re.search(rf"^    {re.escape(name)} +\S", body, re.M), (
            f"the machine block has no line for {name}:\n{body}")
    assert "MISSING" not in body
    assert "present, logged in" in body
    assert "--preflight" not in body, (
        "with everything present and logged in there is nothing to point at")


def test_the_machine_report_names_what_is_missing(tmp_path):
    """A missing one reads MISSING, and the closing line appears — once."""
    result, _log, bin_dir = install_with_machine(
        tmp_path, ("git", "gh", "python3"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert (bin_dir / "openRepoShape").is_file(), (
        "the report is informational; it must not stop the install")
    assert re.search(r"^    git-filter-repo +MISSING$", result.stdout, re.M), \
        result.stdout
    assert result.stdout.count(
        "  run: openRepoShape --preflight   (offers what is missing; each "
        "install asks first)") == 1, result.stdout


def test_a_gh_that_is_not_logged_in_is_reported_and_points_at_preflight(
        tmp_path):
    result, _log, _bin = install_with_machine(
        tmp_path, ("git", "gh", "python3", "git-filter-repo"),
        logged_in=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "present, not logged in" in result.stdout
    assert "--preflight" in result.stdout
    assert "MISSING" not in result.stdout


def test_the_machine_report_runs_no_installer(tmp_path):
    """It PROBES. The only program it may execute is `gh auth status`.

    Every fake on that `$PATH` logs its own argv and then fails loudly, so a
    report that had shelled out to any of them — to read a version, to
    install something, to "just check" — would leave a line here.
    """
    result, log, _bin = install_with_machine(
        tmp_path, ("git", "gh", "python3", "git-filter-repo"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert log.is_file(), "gh auth status is the one call that must happen"
    assert log.read_text(encoding="utf-8").split("\n")[:-1] == \
        ["gh auth status"], log.read_text(encoding="utf-8")
    assert "was EXECUTED by a read-only report" not in result.stderr


# --- the fix round on PR #96 ------------------------------------------------

@pytest.mark.parametrize("args", [
    ("--doctor", "--install"),
    ("--install", "--doctor"),
])
def test_two_modes_is_a_refusal_not_last_wins(args, tmp_path):
    """`--doctor <path> --install` used to install and drop the diagnosis,
    and the other order dropped the install (Copilot, PR #96).

    Each of these does a different thing to a different place. A person who
    typed both meant one of them, and quietly picking the last is how they
    find out which, later, from the wrong outcome.
    """
    bin_dir = tmp_path / "bin"
    result = run_cmd(*args, home=tmp_path,
                     env={"OPENREPOSHAPE_BIN_DIR": str(bin_dir)})
    assert result.returncode == 2, result.stdout + result.stderr
    assert "two different runs" in result.stderr
    # "and writes nothing" was false of a `--placement-plan` typed inside the
    # repository (#546): it says which one file the doctor does write.
    assert "--doctor reads a repository and writes nothing into it but a " \
        "--placement-plan <file> you name." in " ".join(result.stderr.split())
    assert not bin_dir.exists(), "a refused run placed a command anyway"


@pytest.mark.parametrize("ref", ["-x", "--upload-pack=touch /tmp/pwned",
                                 "a" * 256, "refs/heads/..", "x.lock"])
def test_a_ref_the_doctor_would_check_out_is_validated(ref, tmp_path):
    """$OPENREPOSHAPE_REF reaches `git checkout`, so it is checked first.

    `setup.sh` validates `--shape-ref` in three steps and this value lands
    in the same place, which the first cut of `--doctor` missed (Copilot,
    PR #96): a leading dash is an option to git, not a ref. Run from STDIN
    so the clone path is the one taken, and the refusal has to arrive before
    any clone does.
    """
    result = subprocess.run(
        ["bash", "-s", "--", "--doctor", str(tmp_path)], executable=BASH,
        capture_output=True, text=True, check=False,
        input=COMMAND.read_text(encoding="utf-8"), cwd=str(tmp_path),
        env=command_env(home=tmp_path, setup_sh=None,
                        env={"OPENREPOSHAPE_REPO": bash_path(REPO),
                             "OPENREPOSHAPE_REF": ref}))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "OPENREPOSHAPE_REF" in result.stderr
    assert "git checkout" in result.stderr
    # The over-long and control-character refusals must not echo the value
    # back; the shape refusal may, having passed both.
    if len(ref) > 255:
        assert ref not in result.stderr


def test_a_checkout_without_the_doctor_refuses_by_name(tmp_path):
    """A ref older than `shape-doctor.py` produced `can't open file` from
    python3 and a stack of nothing useful. The ref is the thing to change,
    so the refusal says so.

    AND THE CLONE IT REFUSED IS GONE. `--doctor` keeps its clone once the
    doctor has run, because the NEXT lines name files in it (#500); a
    refusal before that printed none, so nothing is left in `$TMPDIR`.
    """
    temporary = tmp_path / "tmp"
    temporary.mkdir()
    bare = tmp_path / "old.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)],
                   capture_output=True, check=True)
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", "-q", str(bare), str(seed)],
                   capture_output=True, check=True)
    (seed / "README.md").write_text("# an older standard\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(seed), capture_output=True,
                   check=True)
    subprocess.run(["git", "commit", "-qm", "before the doctor"],
                   cwd=str(seed), capture_output=True, check=True,
                   env=command_env(home=tmp_path, setup_sh=None))
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=str(seed),
                   capture_output=True, check=True)
    result = subprocess.run(
        ["bash", "-s", "--", "--doctor", str(tmp_path)], executable=BASH,
        capture_output=True, text=True, check=False,
        input=COMMAND.read_text(encoding="utf-8"), cwd=str(tmp_path),
        env=command_env(home=tmp_path, setup_sh=None,
                        env={"OPENREPOSHAPE_REPO": bash_path(bare),
                             "TMPDIR": str(temporary)}))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "has no shape-doctor.py" in result.stderr
    assert "OPENREPOSHAPE_REF" in result.stderr
    assert list(temporary.iterdir()) == [], (
        "a refused clone outlived the run; only a doctor that RAN keeps one")


# --- --preflight ------------------------------------------------------------

def test_preflight_passes_through_without_an_org(tmp_path):
    """`openRepoShape --preflight` is the "install program" without a second
    program: the preflight, the offers it makes, and stop.

    This command insists on an organisation and on a `<Project>` because a
    run that gets past it CREATES three repositories. A preflight run creates
    nothing, so both refusals are skipped rather than answered - and with
    `input=""` there is no terminal here either, so the preflight makes no
    offer and installs nothing, which is the rule this whole suite runs
    under.
    """
    remotes = tmp_path / "remotes"
    result = run_cmd("--preflight", "--local-remote-dir", str(remotes))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "(1) preflight" in result.stdout
    assert "this machine is ready." in result.stdout
    assert "organisation to scaffold into" not in result.stdout, (
        "--preflight prompted for an organisation it has no use for")
    assert "no organisation to scaffold into" not in result.stderr
    assert "no <Project> given" not in result.stderr
    assert not remotes.exists()


def test_preflight_forwards_an_org_it_was_given(tmp_path):
    """A flag this command ATE would be a flag the person has to type twice
    to find out about. The preflight ignores it; it still travels."""
    result = run_cmd("--preflight", "--org", "TestOrg",
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
    assert USAGE_SCAFFOLD in result.stderr
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
    assert "gh api" in body
    assert "curl -fsSL" in body
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
    write_script(served / "setup.sh", STUB_SETUP_SH)
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

    write_script(
        fake / "gh",
        "#!/bin/sh\n"
        + logging("gh") +
        'case "$*" in\n'
        + routes +
        "esac\n"
        'printf \'fake gh: unexpected call: %s\\n\' "$*" >&2\n'
        "exit 1\n")
    (fake / "gh").chmod(0o755)
    write_script(
        fake / "curl",
        "#!/bin/sh\n"
        + logging("curl") +
        "printf 'fake curl: no test here may reach the network\\n' >&2\n"
        "exit 1\n")
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
    result = run_cmd("--preflight", setup_sh=None, env=offline_github)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "No such file or directory" not in result.stdout + result.stderr
    assert "could not fetch" not in result.stderr
    match = re.search(rf"{STUB_MARKER} in (.+) args: (.*)", result.stdout)
    assert match, ("the fetched setup.sh never ran:\n"
                   + result.stdout + result.stderr)
    ran_in, forwarded = match.group(1), match.group(2).split()
    assert "--preflight" in forwarded, forwarded
    ran_dir = native_path(ran_in)
    # The directory it was made in is still there, so the line after this
    # one reads a path this interpreter can open, and cannot pass on one it
    # cannot: `/tmp/...` read as a Windows path names no directory at all.
    assert ran_dir.parent.is_dir(), ran_in
    assert not ran_dir.exists(), (
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
        ["bash", "-s", "--", "--install"], executable=BASH,
        capture_output=True, text=True, check=False,
        input=COMMAND.read_text(encoding="utf-8"),
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
    write_script(
        shim, source.replace("\nINSTALLABLES=(openRepoShape)\n",
                             "\nINSTALLABLES=(openRepoShape witness)\n", 1))

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "openRepoShape").write_text("# an older copy\n",
                                           encoding="utf-8")
    withheld = fake_github(tmp_path, ["openRepoShape"])
    result = subprocess.run(
        [BASH, bash_path(shim), "--install"], capture_output=True,
        text=True, check=False, input="",
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
        ["bash", "-s", "--", "--install"], executable=BASH,
        capture_output=True, text=True, check=False,
        input=COMMAND.read_text(encoding="utf-8"),
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
        assert_a_command(target)
        assert target.read_bytes() == (REPO / name).read_bytes(), name
        assert f"{name}: installed at" in result.stdout


# --- the ref `--install` records, and the installed command runs (#564) -----

#: A ref for an install to record. Nothing fetches it: every install below
#: runs from this checkout's file, which copies its own bytes, and every run
#: after it is offline. `OTHER` is what `$OPENREPOSHAPE_REF` names for one
#: run, over the record.
PINNED = "v9.9.9"
OTHER = "other"


def install_at(tmp_path, ref=None, command=COMMAND, opt_in=True):
    """`--install` from `command` into `<tmp_path>/bin`, with
    `$OPENREPOSHAPE_REF` set to `ref` when one is given, and asked to record
    it (`$OPENREPOSHAPE_RECORD_REF=1`) unless `opt_in` is false; the result,
    and the path of the command it places."""
    bin_dir = tmp_path / "bin"
    env = {"OPENREPOSHAPE_BIN_DIR": bash_path(bin_dir)}
    if ref is not None:
        env["OPENREPOSHAPE_REF"] = ref
        if opt_in:
            env["OPENREPOSHAPE_RECORD_REF"] = "1"
    return (run_cmd("--install", home=tmp_path, env=env, command=command),
            bin_dir / "openRepoShape")


def record_of(installed: Path) -> Path:
    """Where `--install` records the ref of the command at `installed`."""
    return installed.with_name(installed.name + ".ref")


def version_of(installed: Path, env: dict | None = None) -> str:
    result = run_cmd("--version", command=installed, env=env)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_install_records_the_ref_beside_a_command_it_leaves_unchanged(
        tmp_path):
    """THE RECORD IS A FILE BESIDE THE COMMAND, AND THE COMMAND IS THE FILE.

    The placed bytes must still be the bytes it was installed from, because
    everything that asks whether an installed command IS a release compares
    bytes: this installer's own `(unchanged)` verdict, and a copy vendored
    elsewhere and checked by sha256 against the release's own file. So the
    ref goes in `openRepoShape.ref`, said on its own line between the
    command's line and the count, and `--version` then names it with no
    variable set, while the variable still wins for the one run it is set
    for.
    """
    result, installed = install_at(tmp_path, PINNED)
    assert result.returncode == 0, result.stderr
    record = record_of(installed)
    assert record.read_bytes() == f"{PINNED}\n".encode("ascii")
    assert installed.read_bytes() == COMMAND.read_bytes(), (
        "the command must stay byte for byte the file it was installed from")
    assert result.stdout.splitlines()[:3] == [
        f"openRepoShape: installed at {bash_path(installed)}",
        f"openRepoShape: pinned to {PINNED}, recorded in {bash_path(record)}",
        f"openRepoShape: 1 of 1 placed in {bash_path(installed.parent)}"]
    assert version_of(installed) == \
        f"openRepoShape (opensoft/openRepoShape @ {PINNED})"
    assert version_of(installed, {"OPENREPOSHAPE_REF": OTHER}) == \
        f"openRepoShape (opensoft/openRepoShape @ {OTHER})"


def test_an_install_with_no_ref_records_nothing_and_follows_main(tmp_path):
    """No ref at install time is the install as it always was: the same
    lines, no record, and `main`, unnamed, in `--version`."""
    result, installed = install_at(tmp_path)
    assert result.returncode == 0, result.stderr
    assert not record_of(installed).exists()
    assert "pinned" not in result.stdout
    assert version_of(installed) == \
        "openRepoShape (opensoft/openRepoShape @ main)"


def test_installing_again_keeps_moves_or_drops_the_record(tmp_path):
    """Idempotent at the same ref, moved by a new one, dropped by none.

    A second install at the same ref changes neither file and says so twice.
    A newer ref replaces the record and names the one it replaced, which is
    what an upgrade looks like. The installed command re-installing itself
    with no variable set keeps ITS ref, because that is the ref it runs at.
    And an install with no ref at all removes the record, so a command put
    back at main follows main however it was installed before.
    """
    install_at(tmp_path, PINNED)
    same, installed = install_at(tmp_path, PINNED)
    record = record_of(installed)
    assert same.returncode == 0, same.stderr
    assert f"openRepoShape: already pinned to {PINNED} in " \
        f"{bash_path(record)} " \
        "(unchanged)" in same.stdout
    assert same.stdout.count("(unchanged)") == 2, same.stdout

    newer, _ = install_at(tmp_path, "v10.0.0")
    assert f"openRepoShape: pinned to v10.0.0 (was {PINNED}), recorded in " \
        f"{bash_path(record)}" in newer.stdout
    itself, _ = install_at(tmp_path, command=installed)
    assert "openRepoShape: already pinned to v10.0.0" in itself.stdout
    assert record.read_text(encoding="utf-8") == "v10.0.0\n"

    dropped, _ = install_at(tmp_path)
    assert dropped.returncode == 0, dropped.stderr
    assert "openRepoShape: no longer pinned to v10.0.0; it follows main" \
        in dropped.stdout
    assert not record.exists()
    assert version_of(installed).endswith("@ main)")


def test_a_ref_that_is_not_one_is_refused_before_anything_is_placed(
        tmp_path):
    """The ref is about to be written down and read by every later run, so
    it is checked first, the way the doctor checks it before a checkout."""
    result, installed = install_at(tmp_path, "bad..ref")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "$OPENREPOSHAPE_REF is 'bad..ref'" in result.stderr
    assert not installed.parent.exists(), "a refused install placed something"


@pytest.mark.parametrize("text, shown", [
    pytest.param(b"", "is empty", id="empty"),
    pytest.param(b"-x\n", "is '-x'", id="an-option"),
    pytest.param(b"v1..v2\n", "is 'v1..v2'", id="a-range"),
    pytest.param(b"v1\nforged\n", "carries a control character",
                 id="two-lines"),
    pytest.param(b"a" * 256 + b"\n", "is 256 characters long",
                 id="over-long"),
])
def test_a_record_that_is_not_a_ref_is_refused_by_name(tmp_path, text, shown):
    """A record is a file on disk that every run reads, so it is checked
    when it is read, before `--version` can print it, and the refusal names
    the file and the two ways out. The control character and the over-long
    value are refused without being echoed. `$OPENREPOSHAPE_REF`, set, is
    the way past it for one run, because then the record is not read."""
    _result, installed = install_at(tmp_path, PINNED)
    record_of(installed).write_bytes(text)
    result = run_cmd("--version", command=installed)
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"the ref recorded in {bash_path(record_of(installed))} {shown}" \
        in result.stderr
    assert "Run the installer again to record a release, or delete that " \
        "file to follow main." in result.stderr
    assert "forged" not in result.stderr
    assert "a" * 256 not in result.stderr
    assert result.stdout == ""
    assert run_cmd("--help", command=installed).returncode == 0, (
        "--help must answer past a broken record")
    assert version_of(installed, {"OPENREPOSHAPE_REF": OTHER}).endswith(
        f"@ {OTHER})")


def test_a_ref_set_without_the_opt_in_is_never_recorded(tmp_path):
    """`$OPENREPOSHAPE_REF` alone is not a request for a pin (the review on
    #577). A script that sets it around `--install` for its own reasons
    (workBenches sets one that names no ref, so that any fetch fails loudly)
    gets the install it always got: the same bytes, no record, `main` in
    `--version`, and no check of a value it never meant to be read. A record
    already there is removed, exactly as by an install with no ref."""
    install_at(tmp_path, PINNED)
    result, installed = install_at(
        tmp_path, "pinned-by-workBenches-no-fetch", opt_in=False)
    assert result.returncode == 0, result.stderr
    assert installed.read_bytes() == COMMAND.read_bytes()
    assert not record_of(installed).exists()
    assert f"no longer pinned to {PINNED}" in result.stdout
    assert version_of(installed).endswith("@ main)")

    again, _ = install_at(tmp_path, "bad..ref", opt_in=False)
    assert again.returncode == 0, again.stderr
    assert "pinned" not in again.stdout
    assert not record_of(installed).exists()


#: Links to the installed command from `<tmp>/links`: each pair is a link's
#: name and what it points at, `None` meaning the command's absolute path,
#: and the run goes through the LAST one.
LINKS = [
    pytest.param([("ors", "../bin/openRepoShape")], id="relative"),
    pytest.param([("ors", None)], id="absolute"),
    pytest.param([("ors", "../bin/openRepoShape"), ("again", "ors")],
                 id="a-chain"),
]


@pytest.mark.parametrize("links", LINKS)
def test_a_link_to_the_installed_command_reads_its_record(tmp_path, links):
    """The record sits beside the FILE `--install` placed, so a symlink to
    the command from another directory follows the link, or a chain of them,
    to read it."""
    _result, installed = install_at(tmp_path, PINNED)
    directory = tmp_path / "links"
    directory.mkdir()
    for name, points_at in links:
        (directory / name).symlink_to(points_at or installed)
    through = directory / links[-1][0]
    assert version_of(through) == \
        f"openRepoShape (opensoft/openRepoShape @ {PINNED})"


@pytest.mark.parametrize("msys", [None, "winsymlinks:nativestrict"],
                         ids=["ln-default", "ln-nativestrict"])
def test_a_link_made_with_ln_s_reads_the_record_and_a_copy_follows_main(
        tmp_path, msys):
    """`ln -s` IN GIT BASH MAKES A COPY unless `$MSYS` says
    `winsymlinks:nativestrict` (#585), which makes a Windows symlink. A copy
    has no record beside it, so it follows main and `--version` says so;
    a link, made anywhere else or with that setting, reads the record of
    the command it leads to. `$MSYS` means nothing off Windows. A `$MSYS`
    of the caller's own is dropped first, so the default is the default;
    the setting, like every symlink test here, needs Windows' right to make
    a symlink (Developer Mode, or an elevated shell)."""
    _result, installed = install_at(tmp_path, PINNED)
    link = tmp_path / "ors"
    env = {name: value for name, value in os.environ.items()
           if name != "MSYS"}
    if msys:
        env["MSYS"] = msys
    made = subprocess.run([BASH, "-c", 'ln -s "$1" "$2"', "-",
                           bash_path(installed), bash_path(link)],
                          capture_output=True, text=True, check=False,
                          env=env)
    assert made.returncode == 0, made.stderr
    copied = os.name == "nt" and msys is None
    assert link.is_symlink() is not copied
    assert version_of(link) == "openRepoShape (opensoft/openRepoShape @ " \
        f"{'main' if copied else PINNED})"


def test_a_record_that_is_a_directory_is_refused_in_the_usual_form(tmp_path):
    """Not a raw bash error, by every run that reads it and by an install
    that would write or remove it, which places nothing."""
    _result, installed = install_at(tmp_path, PINNED)
    record = record_of(installed)
    record.unlink()
    record.mkdir()
    for result in (run_cmd("--version", command=installed),
                   install_at(tmp_path, PINNED)[0]):
        assert result.returncode == 2, result.stdout + result.stderr
        assert result.stderr.startswith(
            f"\nREFUSED: {bash_path(record)} is not a file")
        assert "Is a directory" not in result.stderr
    assert installed.read_bytes() == COMMAND.read_bytes()


#: WHICH REF EACH LATER RUN USES: recorded at install, then overridden by the
#: variable for one run, then neither. The third column is what the run must
#: be handed; `None` is `main`, unnamed, which nothing is told.
RECORDED_RUNS = [
    pytest.param(PINNED, None, PINNED, id="the-record"),
    pytest.param(PINNED, OTHER, OTHER, id="the-variable-over-the-record"),
    pytest.param(None, None, None, id="no-record"),
]


@pytest.mark.parametrize("recorded, variable, expected", RECORDED_RUNS)
def test_setup_sh_clones_the_standard_at_the_ref_in_force(
        tmp_path, recorded, variable, expected):
    """`--shape-ref` reaches setup.sh whenever a ref was NAMED, and the
    record names one: the setup.sh this command fetched at that ref then
    clones the standard at the same ref, not at main."""
    _result, installed = install_at(tmp_path, recorded)
    stub = tmp_path / "setup.sh"
    write_script(stub, STUB_SETUP_SH)
    result = run_cmd("--preflight", command=installed, setup_sh=stub,
                     env=None if variable is None
                     else {"OPENREPOSHAPE_REF": variable})
    assert result.returncode == 0, result.stdout + result.stderr
    match = re.search(rf"{STUB_MARKER} in .+ args: (.*)", result.stdout)
    assert match, result.stdout + result.stderr
    forwarded = match.group(1).split()
    if expected is None:
        assert "--shape-ref" not in forwarded, forwarded
    else:
        at = forwarded.index("--shape-ref")
        assert forwarded[at + 1] == expected, forwarded


def standard_at_three_refs(tmp_path) -> Path:
    """A bare repository whose `shape-doctor.py` says which ref it is.

    Three commits: the `PINNED` tag, the `OTHER` branch and `main`, each
    with a doctor that prints its own name and nothing else, so a run
    reports which ref the command checked its clone out at.
    """
    seed = tmp_path / "seed"
    seed.mkdir()
    git("init", "-q", "-b", "main", cwd=seed)

    def commit(name):
        (seed / "shape-doctor.py").write_text(
            f"print('STUB DOCTOR AT {name}')\n", encoding="utf-8")
        git("add", "-A", cwd=seed)
        git("commit", "-q", "-m", name, cwd=seed)

    commit(PINNED)
    git("tag", PINNED, cwd=seed)
    git("switch", "-q", "-c", OTHER, cwd=seed)
    commit(OTHER)
    git("switch", "-q", "main", cwd=seed)
    commit("main")
    bare = tmp_path / "standard.git"
    git("clone", "-q", "--bare", str(seed), str(bare), cwd=tmp_path)
    return bare


@pytest.mark.parametrize("recorded, variable, expected", RECORDED_RUNS)
def test_the_doctor_checks_its_clone_out_at_the_ref_in_force(
        tmp_path, recorded, variable, expected):
    """The installed `--doctor` clones the standard, and checks the clone
    out at the ref in force: the record, the variable over it, or neither,
    which leaves the clone on its default branch."""
    _result, installed = install_at(tmp_path, recorded)
    temporary = tmp_path / "tmp"
    temporary.mkdir()
    env = {"OPENREPOSHAPE_REPO": bash_path(standard_at_three_refs(tmp_path)),
           "TMPDIR": str(temporary)}
    if variable is not None:
        env["OPENREPOSHAPE_REF"] = variable
    result = run_cmd("--doctor", str(tmp_path), command=installed, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"STUB DOCTOR AT {expected or 'main'}" in result.stdout, (
        result.stdout + result.stderr)
