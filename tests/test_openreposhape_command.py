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
            setup_sh: Path | None = SETUP, command: Path = COMMAND,
            cwd: Path | None = None) -> subprocess.CompletedProcess:
    """The command, run from its file, with that environment.

    `input=""` means stdin is a pipe rather than a terminal, which is what the
    no-tty refusals are about, and a session of its own means there is no
    controlling terminal either (#492): setup asks at that terminal when
    stdin is not one, and the terminal pytest was started from is nobody's
    answer.

    `command` is this checkout's file unless a test names an INSTALLED copy,
    which is how the record `--install` leaves beside one is read (#564).
    `cwd`, where a relative path the command is handed must land.
    """
    return subprocess.run([BASH, bash_path(command), *args],
                          capture_output=True, text=True, check=False,
                          input="", env=command_env(home, env, setup_sh),
                          start_new_session=True,
                          cwd=None if cwd is None else str(cwd))


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


#: `$OPENREPOSHAPE_BIN_DIR` spelled for Windows, as a Git Bash user may type
#: it, in either slash (#649): where a test needs a value that names no
#: directory of its own.
WINDOWS_BIN_DIR = "D:\\tools\\bin"
WINDOWS_BIN_DIR_SLASH = "D:/tools/bin"

#: The spellings a person types, for a test to run over each. Git Bash takes
#: `D:\tools\bin` and `D:/tools/bin` alike, and `--install` has an arm for
#: each; a drive letter is a letter in either case (#667).
BIN_DIR_SPELLINGS = pytest.mark.parametrize(
    "spelling", ["backslash", "slash", "lower-case"])


def typed_bin_dir(bin_dir: Path, spelling: str) -> str:
    """`$OPENREPOSHAPE_BIN_DIR` as a person types it for Windows, in
    `spelling`: "backslash", "slash", or "lower-case", a backslash path
    whose drive letter is lower case. Off Windows it is `D:\\tools\\bin`,
    `D:/tools/bin` or `d:\\tools\\bin`, which name no directory of their own.
    On Windows it is `bin_dir` itself, a real drive path under the test's
    directory, with `str` for the backslash and `as_posix` for the slash: a
    command placed where it should not be then lands where the test can see
    it, and never on the machine's own `D:` drive."""
    if os.name == "nt":
        if spelling == "slash":
            return bin_dir.as_posix()
        typed = str(bin_dir)
        return typed[0].lower() + typed[1:] if spelling == "lower-case" \
            else typed
    return {"slash": WINDOWS_BIN_DIR_SLASH,
            "lower-case": WINDOWS_BIN_DIR.lower()}.get(spelling,
                                                       WINDOWS_BIN_DIR)


def fake_cygpath(directory: Path, typed: str, answer: str | None) -> None:
    """A `cygpath` in `directory` that spells `typed` as `answer`, as Git
    Bash's own `cygpath -u` spells a drive path, or fails when `answer` is
    None. Anything else it is asked fails."""
    directory.mkdir(exist_ok=True)
    answers = "" if answer is None else (
        f'[ "$*" = {shlex.quote("-u -- " + typed)} ] && '
        f"printf '%s\\n' {shlex.quote(answer)} && exit 0\n")
    write_script(directory / "cygpath", f"#!/bin/sh\n{answers}exit 1\n")
    (directory / "cygpath").chmod(0o755)


#: What `cygpath` does where a test builds a `$PATH` (#667): "spells" the
#: value the way bash does, "fails", answers a drive spelling "again", or is
#: not "there" at all.
CYGPATH_STATES = ("spells", "fails", "again", "there-is-none")


def put_cygpath(directory: Path, typed: str, state: str, spelled: str) -> None:
    """A `cygpath` in `directory` in `state`: Git Bash's own where it
    "spells" on Windows, a fake that answers `spelled` elsewhere."""
    if state == "there-is-none":
        return
    if state == "spells" and os.name == "nt":
        directory.mkdir(exist_ok=True)
        put_on_path(directory, "cygpath", shutil.which("cygpath"))
        return
    fake_cygpath(directory, typed, {"spells": spelled, "fails": None,
                                    "again": WINDOWS_BIN_DIR_SLASH}[state])


@BIN_DIR_SPELLINGS
@pytest.mark.parametrize("on_path", [False, True],
                         ids=["not-on-path", "on-path"])
def test_a_windows_spelled_bin_dir_is_spelled_the_way_bash_spells_it(
        tmp_path, on_path, spelling):
    """`OPENREPOSHAPE_BIN_DIR=D:\\tools\\bin` or `D:/tools/bin` in Git Bash
    (#649).

    `--install` named the directory as typed, so its PATH note printed
    `export PATH="D:\\tools\\bin:$PATH"`, which the drive's colon splits in
    two, and never found it on a `$PATH` holding `/d/tools/bin`. It is
    spelled with `cygpath -u` first, so every line names the directory as
    bash does, and the note is printed only when that directory is not on
    `$PATH`. Both slashes are drive paths. On Windows it is a real drive
    path and Git Bash's own `cygpath`; elsewhere a fake answers as that one
    would.
    """
    bin_dir = tmp_path / "bin"
    spelled = bash_path(bin_dir)
    typed = typed_bin_dir(bin_dir, spelling)
    path = os.environ["PATH"]
    if os.name != "nt":
        fake_cygpath(tmp_path / "fake-path", typed, spelled)
        path = f"{tmp_path / 'fake-path'}{os.pathsep}{path}"
    if on_path:
        path = f"{bin_dir}{os.pathsep}{path}"
    result = run_cmd("--install", home=tmp_path, cwd=tmp_path,
                     env={"PATH": path, "OPENREPOSHAPE_BIN_DIR": typed})
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert f"openRepoShape: installed at {spelled}/openRepoShape" in lines, \
        result.stdout
    assert (bin_dir / "openRepoShape").read_bytes() == COMMAND.read_bytes()
    assert (f'    export PATH="{spelled}:$PATH"' in lines) is not on_path, \
        result.stdout
    assert typed not in result.stdout


@BIN_DIR_SPELLINGS
@pytest.mark.parametrize("cygpath_there, answer", [
    pytest.param(False, None, id="no-cygpath"),
    pytest.param(True, None, id="cygpath-fails"),
    pytest.param(True, WINDOWS_BIN_DIR_SLASH, id="cygpath-answers-a-drive"),
])
def test_a_windows_spelled_bin_dir_is_refused_where_no_cygpath_spells_it(
        tmp_path, cygpath_there, answer, spelling):
    """With no `cygpath` to spell it, one that cannot, or one that answers
    with a drive spelling again, the drive's colon would still split the
    directory on `$PATH`, so `--install` refuses before it places anything,
    and says what to set instead (#649). Either slash. The `$PATH` is the
    machine report's own, which holds no `cygpath` but the fake. The typed
    value is under `tmp_path` on Windows, so a refusal that regressed would
    place the command where this test looks, and not on a real drive."""
    env = machine_path(tmp_path, ())
    env.pop("_log")
    typed = typed_bin_dir(tmp_path / "bin", spelling)
    if cygpath_there:
        fake_cygpath(tmp_path / "machine-path", typed, answer)
    result = run_cmd("--install", home=tmp_path, cwd=tmp_path,
                     env={**env, "OPENREPOSHAPE_BIN_DIR": typed})
    assert result.returncode == 2, result.stdout + result.stderr
    said = " ".join(result.stderr.split())
    assert f"--install would place this command in '{typed}', " \
        "which is spelled for Windows" in said, said
    assert "Nothing was placed. Set $OPENREPOSHAPE_BIN_DIR to the directory " \
        "as this shell spells it, then run this again." in said, said
    assert result.stdout == ""
    assert [path.name for path in tmp_path.iterdir()] == ["machine-path"]


# --- the PATH note quotes the directory it prints (#667) ---------------------

#: Windows names no file with a `"` or a `\` in it.
POSIX_NAME = pytest.mark.skipif(
    os.name == "nt", reason="a Windows file name holds no \" or \\")

#: One directory name per case, and the `export PATH` line `--install` prints
#: for it, with `{d}` for the directory's parent. The lines are written out,
#: not computed, because the launcher's own rule is what is being held:
#: today's line byte for byte where double quotes are enough (a space and an
#: apostrophe are), and single quotes, an apostrophe as `'\''`, where bash
#: would still read a `"`, `$`, backquote or `\` between double quotes, or a
#: `!` at an interactive prompt.
PATH_NOTE_NAMES = [
    pytest.param("plain", 'export PATH="{d}/plain:$PATH"', id="plain"),
    pytest.param("two words", 'export PATH="{d}/two words:$PATH"',
                 id="a-space"),
    pytest.param("it's", 'export PATH="{d}/it\'s:$PATH"', id="an-apostrophe"),
    pytest.param("a$b", "export PATH='{d}/a$b':\"$PATH\"", id="a-dollar"),
    pytest.param("a`b`", "export PATH='{d}/a`b`':\"$PATH\"",
                 id="a-backquote"),
    pytest.param("a!b", "export PATH='{d}/a!b':\"$PATH\"", id="a-bang"),
    pytest.param("it's $HOME", "export PATH='{d}/it'\\''s $HOME':\"$PATH\"",
                 id="an-apostrophe-and-a-dollar"),
    pytest.param("a'b'c!", "export PATH='{d}/a'\\''b'\\''c!':\"$PATH\"",
                 id="two-apostrophes-and-a-bang"),
    pytest.param('a"b', "export PATH='{d}/a\"b':\"$PATH\"",
                 marks=POSIX_NAME, id="a-double-quote"),
    pytest.param("a\\b", "export PATH='{d}/a\\b':\"$PATH\"",
                 marks=POSIX_NAME, id="a-backslash"),
    pytest.param("a\\", "export PATH='{d}/a\\':\"$PATH\"",
                 marks=POSIX_NAME, id="a-trailing-backslash"),
    pytest.param('a"b$HOME c', "export PATH='{d}/a\"b$HOME c':\"$PATH\"",
                 marks=POSIX_NAME, id="the-issue-probe"),
]


def path_after(line: str) -> str:
    """`$PATH` once bash has run `line` where it held `/sentinel`: the line
    through `eval`, which reads it as a shell reads a pasted line. The line
    travels in the environment and the script on stdin as bytes, which keep
    a `"` and a `\\` whole on Windows."""
    ran = subprocess.run(
        [BASH, "-s"], capture_output=True, check=False,
        input=b'PATH=/sentinel\neval "$LINE"\nprintf %s "$PATH"\n',
        env=command_env(setup_sh=None, env={"LINE": line}))
    assert ran.returncode == 0, ran.stderr.decode("utf-8", "replace")
    return ran.stdout.decode("utf-8")


@pytest.mark.parametrize("name, line", PATH_NOTE_NAMES)
def test_the_path_note_is_a_line_that_does_what_it_says(tmp_path, name, line):
    """`--install` prints `export PATH=…` for a directory that is not on
    `$PATH`, and a person pastes it. It put the directory between double
    quotes as it was, so `a"b$HOME c` printed `export PATH="…/a"b$HOME
    c:$PATH"`, which does not parse, and `$HOME` or a backquote in a name
    was run or read, not kept (#667). The printed line is the one written
    out for that name, and bash, handed it, puts exactly that directory
    ahead of the old `$PATH`: no more, no less, nothing expanded."""
    parent = bash_path(tmp_path)
    result = run_cmd("--install", home=tmp_path, cwd=tmp_path,
                     env={"OPENREPOSHAPE_BIN_DIR": f"{parent}/{name}"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / name / "openRepoShape").is_file()
    printed = [text for text in result.stdout.splitlines()
               if text.startswith("    export PATH=")]
    assert printed == ["    " + line.format(d=parent)], result.stdout
    assert path_after(printed[0]) == f"{parent}/{name}:/sentinel"


@pytest.mark.parametrize("name, line", PATH_NOTE_NAMES)
def test_export_path_line_quotes_any_directory_for_bash(name, line):
    """The same rule on the function alone, so a `"` or a `\\` is held on
    Windows too, where no file can be named with one and the test above
    skips them: the function is lifted out of the launcher and handed the
    directory in the environment, as `set -euo pipefail` runs it there."""
    directory = f"/srv/tools/{name}"
    text = COMMAND.read_text(encoding="utf-8")
    [function] = re.findall(r"^export_path_line\(\) \{\n.*?^\}\n", text,
                            re.M | re.S)
    ran = subprocess.run(
        [BASH, "-s"], capture_output=True, check=False,
        input=("set -euo pipefail\n" + function +
               'export_path_line "$DIR"\n').encode("utf-8"),
        env=command_env(setup_sh=None, env={"DIR": directory}))
    assert ran.returncode == 0, ran.stderr.decode("utf-8", "replace")
    assert ran.stdout.decode("utf-8") == line.format(d="/srv/tools")
    assert path_after(ran.stdout.decode("utf-8")) == f"{directory}:/sentinel"


@POSIX_NAME
@pytest.mark.parametrize("name", ["a!b", "a$b", "plain"])
def test_a_pasted_path_note_reaches_an_interactive_bash_as_printed(
        tmp_path, name):
    """A person pastes the line at a prompt, and an interactive bash reads
    `!` inside double quotes as history (`event not found`), which a profile
    file never does: so a directory holding one is single-quoted too. Run
    through `bash -i`, the line sets `$PATH` to the directory and no
    other."""
    parent = bash_path(tmp_path)
    result = run_cmd("--install", home=tmp_path, cwd=tmp_path,
                     env={"OPENREPOSHAPE_BIN_DIR": f"{parent}/{name}"})
    assert result.returncode == 0, result.stdout + result.stderr
    [line] = [text.strip() for text in result.stdout.splitlines()
              if text.startswith("    export PATH=")]
    reached = tmp_path / "reached"
    script = f'PATH=/sentinel\n{line}\nprintf %s "$PATH" > "$OUT"\nexit\n'
    subprocess.run(
        [BASH, "--norc", "--noprofile", "-i"], capture_output=True,
        check=False, input=script.encode("utf-8"), start_new_session=True,
        env=command_env(setup_sh=None, env={
            "OUT": str(reached), "HISTFILE": os.devnull}))
    assert reached.read_text(encoding="utf-8") == f"{parent}/{name}:/sentinel"


#: Control characters, typed as their numbers: no escape sequence is written
#: into this file, because a tool that writes it may write the raw character
#: (U+009B is the C1 "control sequence introducer" a terminal runs).
ESCAPE = chr(0x1B)
DELETE = chr(0x7F)
C1_CSI = chr(0x9B)
#: A lone 0xE9 byte, which no UTF-8 text holds, as Python hands one to a
#: child's environment (the byte comes back through `surrogateescape`).
NOT_UTF8 = chr(0xDCE9)

#: THE CHARACTERS A TERMINAL DRAWS AS SOMETHING OTHER THAN THEMSELVES (#837),
#: by code point, as the launcher's `MISDRAWN_CHARACTERS` and install.sh's
#: copy list them: the soft hyphen, the twelve bidirectional controls, the
#: line and paragraph separators, and the format characters of no width
#: that nothing needs, three of them past U+FFFF. Written out here, not read
#: from either file, so that a change to that list is a change to this one
#: too.
MISDRAWN = (0x00AD, 0x061C, 0x200B, 0x200E, 0x200F, *range(0x2028, 0x202F),
            *range(0x2060, 0x2070), 0xFEFF, *range(0xFFF9, 0xFFFC),
            *range(0x1D173, 0x1D17B), 0xE0001)

#: U+202E RIGHT-TO-LEFT OVERRIDE, the one of `MISDRAWN` the tests of each
#: place it is refused hold, after a `forged` tail's start.
RLO = chr(0x202E)

HOLDS_A_COLON = "holds a ':'"
HOLDS_A_CONTROL_CHARACTER = "holds a control character"


def drawn_as_another(named: str) -> str:
    """What every refusal of a value holding `named` says of it, in both
    files: the `U+XXXX` of each character of `MISDRAWN` in it,
    comma-separated (#837). Each place goes on in words of its own."""
    return ("holds a character a terminal draws as something other than "
            f"itself ({named}): one that is invisible, is drawn as another "
            "character, ends a line or reorders the text around it")


def bin_dir_drawn_as_another(named: str) -> str:
    """The directory's refusal of `named`, in both files (#837)."""
    return (drawn_as_another(named) + ", so no line about $PATH can print "
            "the name as it reads.")

#: How `--install`'s two refusals end, and how install.sh's do (#760): the
#: remedy is the same sentence in both, less the verb.
COMMAND_REFUSAL_ENDS = (
    "Nothing was placed. Set $OPENREPOSHAPE_BIN_DIR to a directory without "
    "one, then run this again.")

#: What `--install` refuses, before it places anything: a directory no line
#: about `$PATH` can name, and what its refusal says. `{d}` is `tmp_path` as
#: bash spells it. A control character is refused FIRST and its refusal
#: never echoes the value, so every control value ends in `forged`, which
#: shows in no output when the refusal is right; a colon's refusal names the
#: directory, which holds no control character by then (#667, #760).
UNNAMEABLE_BIN_DIRS = [
    pytest.param("{d}/a:b/bin", HOLDS_A_COLON, id="a-colon"),
    pytest.param("{d}/bin:{d}/other", HOLDS_A_COLON, id="two-directories"),
    pytest.param("D:tools", HOLDS_A_COLON, id="a-drive-relative-name"),
    pytest.param("{d}/a\nforged/bin", HOLDS_A_CONTROL_CHARACTER,
                 id="a-newline"),
    pytest.param("{d}/a\rforged/bin", HOLDS_A_CONTROL_CHARACTER,
                 id="a-carriage-return"),
    pytest.param("{d}/a" + ESCAPE + "[31mforged/bin",
                 HOLDS_A_CONTROL_CHARACTER, id="an-escape"),
    pytest.param("{d}/a\tforged/bin", HOLDS_A_CONTROL_CHARACTER,
                 id="a-tab"),
    pytest.param("{d}/a" + DELETE + "forged/bin", HOLDS_A_CONTROL_CHARACTER,
                 id="a-delete"),
    pytest.param("D:\\tools\nforged\\bin", HOLDS_A_CONTROL_CHARACTER,
                 id="a-drive-spelling-and-a-newline"),
    pytest.param("D:\\tools" + ESCAPE + "forged\\bin",
                 HOLDS_A_CONTROL_CHARACTER,
                 id="a-drive-spelling-and-an-escape"),
    pytest.param("{d}/a:b" + ESCAPE + "forged/bin",
                 HOLDS_A_CONTROL_CHARACTER, id="a-colon-and-an-escape"),
]

#: Windows names no file with a control character in it, or with a `:`
#: beyond the drive's.
NO_FILE_NAMED_SO = pytest.mark.skipif(
    os.name == "nt", reason="a Windows file name holds no control character")

#: The two locales a value is tried under: `C` reads one byte at a time, and
#: `C.UTF-8` reads UTF-8 text where it is valid (#760).
LOCALES = ["C", "C.UTF-8"]

NO_NON_ASCII_INTO_GIT_BASH = pytest.mark.skipif(
    os.name == "nt", reason="a non-ASCII value through the environment into "
    "Git Bash is not run here")


def assert_refused_saying(result, said: str) -> str:
    """`result` is a refusal, exit 2, that says `said` on stderr and
    nothing on stdout, and no control character, no character of
    `MISDRAWN` and no `forged` tail reaches either stream (#760, #837).
    The refusal, its whitespace collapsed, is returned."""
    assert result.returncode == 2, result.stdout + result.stderr
    said_in_full = " ".join(result.stderr.split())
    assert said in said_in_full, said_in_full
    for stream in (result.stdout, result.stderr):
        assert "forged" not in stream, stream
        assert ESCAPE not in stream, stream
        assert DELETE not in stream, stream
        assert C1_CSI not in stream, stream
        for code in MISDRAWN:
            assert chr(code) not in stream, (f"U+{code:04X}", stream)
    assert result.stdout == ""
    return said_in_full


def assert_a_bin_dir_is_refused(result, typed: str, said: str,
                                ending: str) -> None:
    """`result` is a refusal, exit 2, of `typed`, a directory no line about
    `$PATH` can name (#667, #760, #837), saying `said` and ending as
    `ending` does. A colon's refusal names the directory; nothing else
    does (see `assert_refused_saying`)."""
    said_in_full = assert_refused_saying(result, said)
    assert ending in said_in_full, said_in_full
    if said == HOLDS_A_COLON:
        assert f"'{typed}', which {said}" in said_in_full, said_in_full


@pytest.mark.parametrize("value, said", UNNAMEABLE_BIN_DIRS)
def test_a_bin_dir_no_path_line_can_name_is_refused_before_it_places_anything(
        tmp_path, value, said):
    """A `:` splits a `$PATH`, a newline breaks the note's line in two, a
    carriage return rewrites it on the terminal and an escape is the
    terminal's to act on, so no `export PATH` line could name such a
    directory (#667, #760): refused with exit 2 beside the Windows
    spelling's refusal, before a file is placed or a directory made, and
    saying what to set instead. Every control character is refused first,
    ahead of the Windows spelling and the colon, and the value is never
    echoed, so it cannot forge a line or reach the terminal."""
    typed = value.format(d=bash_path(tmp_path))
    result = run_cmd("--install", home=tmp_path, cwd=tmp_path,
                     env={"OPENREPOSHAPE_BIN_DIR": typed})
    assert_a_bin_dir_is_refused(result, typed, said, COMMAND_REFUSAL_ENDS)
    assert list(tmp_path.iterdir()) == []


#: Names no check refuses, in either locale (#760, #837): an e with an acute
#: accent; U+00A0, a no-break space, whose bytes `0xC2 0xA0` come right
#: after the C1 range's last (`0xC2 0x9F`); a Persian word (letters) whose
#: two parts U+200C ZERO WIDTH NON-JOINER keeps apart, and an emoji sequence
#: (a woman technologist) that U+200D ZERO WIDTH JOINER makes, which that
#: script and that sequence need; U+2026 and U+FF21, which start with the
#: bytes `0xE2` and `0xEF` that most of `MISDRAWN` start with; and a
#: subdivision flag (England's), which the tags U+E0020 to U+E007F make,
#: whose first three bytes are U+E0001's (`0xF3 0xA0 0x80` and
#: `0xF3 0xA0 0x81`). U+2028 and U+2029 were here until #837 refused them
#: with the rest of `MISDRAWN`.
NOT_CONTROLS = [
    pytest.param("caf" + chr(0xE9), id="an-e-acute"),
    pytest.param("a" + chr(0xA0) + "b", id="a-no-break-space"),
    pytest.param("".join(map(chr, (0x0646, 0x0627, 0x0645, 0x0647, 0x200C,
                                   0x0647, 0x0627))),
                 id="a-persian-word-and-u+200c"),
    pytest.param(chr(0x1F469) + chr(0x200D) + chr(0x1F4BB),
                 id="an-emoji-sequence-and-u+200d"),
    pytest.param("a" + chr(0x2026) + "b", id="u+2026"),
    pytest.param("a" + chr(0xFF21) + "b", id="u+ff21"),
    pytest.param("".join(map(chr, (0x1F3F4, 0xE0067, 0xE0062, 0xE0065,
                                   0xE006E, 0xE0067, 0xE007F))),
                 id="a-subdivision-flag"),
]


@NO_NON_ASCII_INTO_GIT_BASH
@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("name", NOT_CONTROLS)
def test_a_bin_dir_with_an_unprinted_letter_is_placed(
        tmp_path, locale, name):
    """The refusal is `[[:cntrl:]]` and not `[![:print:]]` (#760): under
    `LC_ALL=C` the two bytes of an e with an acute accent are not
    printable, so the second would refuse a directory called `caf` and
    that letter for a fault it has not got. It is placed, in either
    locale, and so is a no-break space, whose first byte is the C1
    controls' (`0xC2`) and whose second is the one past them; and so are
    the zero-width non-joiner and joiner, which a script or an emoji
    needs, and two characters drawn as themselves whose first bytes are
    those of the characters #837 refuses (see `NOT_CONTROLS`)."""
    result = run_cmd("--install", home=tmp_path, cwd=tmp_path, env={
        "OPENREPOSHAPE_BIN_DIR": f"{bash_path(tmp_path)}/{name}",
        "LC_ALL": locale})
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / name / "openRepoShape").read_bytes() \
        == COMMAND.read_bytes()


#: A C1 control (U+0080 to U+009F) is two bytes in UTF-8, `0xC2` and a byte
#: from `0x80` to `0x9F`, and a terminal that reads the two as one acts on
#: it (#760). Each is refused in every locale, and whatever else the value
#: holds: under a UTF-8 locale `[[:cntrl:]]` matches a C1 control only in a
#: value that is valid UTF-8, and a lone `0xE9` byte before it makes bash
#: match byte by byte. The first and the last of the range are named, so an
#: arm that stops one short at either end is caught, and a colon beside the
#: control shows the control arm comes first.
C1_BIN_DIRS = [
    pytest.param("{d}/a" + C1_CSI + "forged/bin", id="a-c1-csi"),
    pytest.param("{d}/a" + chr(0x80) + "forged/bin", id="the-first-c1-control"),
    pytest.param("{d}/a" + chr(0x9F) + "forged/bin", id="the-last-c1-control"),
    pytest.param("{d}/caf" + NOT_UTF8 + C1_CSI + "31mforged/bin",
                 id="a-byte-that-is-not-utf-8-then-a-c1-csi"),
    pytest.param("{d}/a:caf" + NOT_UTF8 + C1_CSI + "31mforged/bin",
                 id="a-colon-then-a-byte-that-is-not-utf-8-and-a-c1-csi"),
]

#: Each of `MISDRAWN` in a directory, refused by the words that name it by
#: its code point (#837); then two at once, which are both named, in
#: `MISDRAWN`'s order; one after a byte that is not UTF-8; and one beside a
#: `:` and one in a drive spelling, whose own refusals name the directory,
#: so this one has to come before them.
MISDRAWN_BIN_DIRS = [
    *(pytest.param("{d}/a" + chr(code) + "forged/bin",
                   bin_dir_drawn_as_another(f"U+{code:04X}"),
                   id=f"u+{code:04x}")
      for code in MISDRAWN),
    pytest.param("{d}/a" + RLO + "b" + chr(0x200B) + "forged/bin",
                 bin_dir_drawn_as_another("U+200B, U+202E"),
                 id="two-at-once"),
    pytest.param("{d}/caf" + NOT_UTF8 + RLO + "forged/bin",
                 bin_dir_drawn_as_another("U+202E"),
                 id="a-byte-that-is-not-utf-8-then-u+202e"),
    pytest.param("{d}/a:b" + RLO + "forged/bin",
                 bin_dir_drawn_as_another("U+202E"),
                 id="a-colon-and-u+202e"),
    pytest.param("D:\\tools" + RLO + "forged\\bin",
                 bin_dir_drawn_as_another("U+202E"),
                 id="a-drive-spelling-and-u+202e"),
]

#: Every value refused alike under `C` and under `C.UTF-8`, with what its
#: refusal says: each of `C1_BIN_DIRS` as a control character (#760), each
#: of `MISDRAWN_BIN_DIRS` by what it holds (#837), and a tab before U+202E
#: as a control character, because the control check comes first.
REFUSED_IN_EVERY_LOCALE = [
    *(pytest.param(*value.values, HOLDS_A_CONTROL_CHARACTER, id=value.id)
      for value in C1_BIN_DIRS),
    *MISDRAWN_BIN_DIRS,
    pytest.param("{d}/a\t" + RLO + "forged/bin", HOLDS_A_CONTROL_CHARACTER,
                 id="a-tab-then-u+202e"),
]


@NO_NON_ASCII_INTO_GIT_BASH
@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("value, said", REFUSED_IN_EVERY_LOCALE)
def test_a_bin_dir_is_refused_in_every_locale_whatever_else_it_holds(
        tmp_path, value, said, locale):
    """Refused, exit 2, nothing placed, and never echoed, under `C` and
    under `C.UTF-8`. A C1 control is refused as an escape is (#760): under
    `C`, `[[:cntrl:]]` reads its two bytes one at a time and matches
    neither, and under `C.UTF-8` a byte that is not UTF-8 anywhere in the
    value makes bash match byte by byte. A character a terminal draws as
    something other than itself is refused in words that name it by its
    code point, because nobody can see it (#837), and its bytes are looked
    for as bytes, so the locale changes nothing there either."""
    typed = value.format(d=bash_path(tmp_path))
    result = run_cmd("--install", home=tmp_path, cwd=tmp_path,
                     env={"OPENREPOSHAPE_BIN_DIR": typed, "LC_ALL": locale})
    assert_a_bin_dir_is_refused(result, typed, said, COMMAND_REFUSAL_ENDS)
    assert list(tmp_path.iterdir()) == []


def shell_function(path: Path, name: str) -> str:
    """The function `name`, from its first line to its closing brace, as
    the file at `path` carries it."""
    [function] = re.findall(rf"^{name}\(\) \{{\n.*?^\}}\n",
                            path.read_text(encoding="utf-8"), re.M | re.S)
    return function


def misdrawn_check(path: Path) -> str:
    """`MISDRAWN_CHARACTERS` and `misdrawn_characters`, as the file at
    `path` carries them (#837)."""
    text = path.read_text(encoding="utf-8")
    [listed] = re.findall(r"^MISDRAWN_CHARACTERS=\(.*?\)\n", text, re.M)
    return listed + shell_function(path, "misdrawn_characters")


def test_install_sh_carries_the_launchers_misdrawn_check_as_it_is():
    """install.sh arrives alone down a pipe, so it carries a copy of the
    launcher's list and function, as it carries the control check (#837).
    The two are one text, so neither file can refuse a directory the other
    places, or name it otherwise."""
    assert misdrawn_check(REPO / "install.sh") == misdrawn_check(COMMAND)


#: Every code point whose UTF-8 starts with the bytes one of `MISDRAWN`
#: starts with: U+0080 to U+00BF (`0xC2`), U+0600 to U+063F (`0xD8`),
#: U+2000 to U+20FF (`0xE2 0x80` to `0xE2 0x83`), U+FE00 to U+FFFF
#: (`0xEF 0xB8` to `0xEF 0xBF`), U+1D100 to U+1D1FF (`0xF0 0x9D 0x84` to
#: `0xF0 0x9D 0x87`) and U+E0000 to U+E007F (`0xF3 0xA0 0x80` and
#: `0xF3 0xA0 0x81`); and a sample of the other planes past U+FFFF: their
#: first and last code points, an emoji, a CJK ideograph, the variation
#: selectors past U+FFFF, and the format characters a script needs, which
#: stay allowed (the Kaithi number signs, the Egyptian hieroglyph and the
#: shorthand format controls).
SHARING_ITS_BYTES = (*range(0x80, 0xC0), *range(0x600, 0x640),
                     *range(0x2000, 0x2100), *range(0xFE00, 0x10000),
                     *range(0x1D100, 0x1D200), *range(0xE0000, 0xE0080),
                     0x10000, 0x110BD, 0x110CD, *range(0x13430, 0x13440),
                     *range(0x1BCA0, 0x1BCA4), 0x1F600, 0x20000, 0xE0100,
                     0xE01EF, 0xFFFFD, 0x10FFFF)


@pytest.mark.parametrize("name", ["openRepoShape", "install.sh"])
def test_misdrawn_characters_names_its_own_and_nothing_else(tmp_path, name):
    """The function alone, lifted out of the file and run under `LC_ALL=C`,
    as both call sites run it, over one directory name for each code point
    that starts with the bytes one it refuses starts with (#837): it names
    exactly the code points of `MISDRAWN`, each as `U+XXXX`, and nothing
    for the rest, so a name that merely holds a byte such as `0xE2`, `0xEF`
    or `0xF3` is never refused, and the four-byte form is built right. The
    names travel on stdin, as bytes, so this runs under Git Bash too, where
    no such name crosses the environment."""
    script = tmp_path / "misdrawn.sh"
    write_script(script, "LC_ALL=C\n" + misdrawn_check(REPO / name)
                 + 'while IFS= read -r -d "" value; do\n'
                 '\tmisdrawn_characters "$value"\n'
                 "\tprintf '\\n'\n"
                 "done\n")
    ran = subprocess.run(
        [BASH, bash_path(script)], capture_output=True, check=False,
        input=b"".join(f"/a{chr(code)}b".encode("utf-8") + b"\0"
                       for code in SHARING_ITS_BYTES),
        env=command_env(setup_sh=None))
    assert ran.returncode == 0, ran.stderr.decode("utf-8", "replace")
    named = ran.stdout.decode("ascii").split("\n")[:-1]
    assert dict(zip(SHARING_ITS_BYTES, named)) == {
        code: f"U+{code:04X}" if code in MISDRAWN else ""
        for code in SHARING_ITS_BYTES}


def test_install_sh_carries_the_launchers_locale_reading_as_it_is():
    """install.sh carries the launcher's `locale_reading` as well (#858),
    so the two read a directory the bytes refuse alike, and neither places
    one the other refuses."""
    assert shell_function(REPO / "install.sh", "locale_reading") \
        == shell_function(COMMAND, "locale_reading")


#: HOW A `locale` OR AN `iconv` A TEST PUTS FIRST ON `$PATH` BEHAVES (#858).
#: Every `locale` answers `locale charmap` as glibc's does, from the first of
#: `$LC_ALL`, `$LC_CTYPE` and `$LANG` that is set and not empty: a marker
#: locale `xx_XX.<charmap>` gives that charmap, `C.UTF-8` gives `UTF-8`, and
#: anything else `ANSI_X3.4-1968`. `HONEST` stops there; `FAILS` answers and
#: then exits 1; `MISSING` exits 127, as a shell answers a name it cannot
#: find. An `iconv` is this machine's (None), or `MISSING`, or `EMPTY`, one
#: that prints nothing and exits 0, as no working one does, or
#: `READS_THEN_FAILS`, this machine's run in full and then exit 1, so that
#: the whole reading is printed by an `iconv` that failed, or `MARKS`, one
#: that leaves `iconv-ran` beside itself and exits 1, so that a run which
#: must not ask it shows whether it did.
HONEST, FAILS, MISSING, EMPTY, READS_THEN_FAILS, MARKS = (
    "honest", "fails", "missing", "empty", "reads-then-fails", "marks")

#: What a `locale` stub answers `locale charmap` with, as described above.
CHARMAP_ANSWER = (
    '[ "$1" = charmap ] || exit 2\n'
    'name=${LC_ALL:-${LC_CTYPE:-$LANG}}\n'
    'case "$name" in\n'
    'xx_XX.*) printf \'%s\\n\' "${name#xx_XX.}" ;;\n'
    "C.UTF-8) printf 'UTF-8\\n' ;;\n"
    "*) printf 'ANSI_X3.4-1968\\n' ;;\n"
    "esac\n")


def put_a_locale(directory: Path, kind: str = HONEST,
                 iconv: str | None = None) -> None:
    """A `locale` in `directory` that behaves as `kind` says, and an
    `iconv` beside it that behaves as `iconv` says (#858). No GB18030, GBK
    or Shift_JIS locale is installed here or on CI, and none can be built,
    so the person's locale is a marker name the stub alone knows, and bash
    itself runs in `C` under it."""
    write_script(directory / "locale", "#!/bin/sh\n" + {
        HONEST: CHARMAP_ANSWER, FAILS: CHARMAP_ANSWER + "exit 1\n",
        MISSING: "exit 127\n"}[kind])
    (directory / "locale").chmod(0o755)
    real = shutil.which("iconv")
    assert real, "this machine has no iconv, which these cases read with"
    if iconv is None:
        put_on_path(directory, "iconv", real)
        return
    write_script(directory / "iconv", "#!/bin/sh\n" + {
        MISSING: "exit 127\n", EMPTY: "cat >/dev/null\nexit 0\n",
        READS_THEN_FAILS: f'{shlex.quote(real)} "$@"\nexit 1\n',
        MARKS: f": > {shlex.quote(str(directory / 'iconv-ran'))}\nexit 1\n",
    }[iconv])
    (directory / "iconv").chmod(0o755)


def the_persons_locale(charmap: str) -> dict:
    """The environment of a person whose locale reads `charmap`: `LANG` the
    marker locale, and `LC_ALL` and `LC_CTYPE` empty, as unset (#858). bash
    says nothing of a `LANG` that is not installed, and runs in `C`."""
    return {"LANG": f"xx_XX.{charmap}", "LC_ALL": "", "LC_CTYPE": ""}


#: One of the 32 hanzi that GBK, GB18030 and CP936 read `0xC2 0x80` to
#: `0xC2 0x9F` as, which in UTF-8 are a C1 control's two bytes: Python
#: hands `chr(0x9B)` to a child as `0xC2 0x9B`, U+8078 in GB18030 (#858).
A_HANZI_OF_C1_BYTES = "a" + C1_CSI + "b"

#: Names a multibyte charset reads as text, each with that charset and its
#: `iconv` (#858): the first, the issue's and the last of the 32 hanzi, so
#: that a C1 range that stops one short at either end, where it decides
#: whether to ask the locale, is caught; U+00AD's two bytes, U+9885 in GBK;
#: U+2028's three, a kanji and a half-width katakana in Shift_JIS; in
#: Shift_JIS a half-width katakana (`0xC2`) before a character whose first
#: byte is `0x81`, read as U+FF82 and then U+3005 or U+FF3F, whose UTF-8
#: holds a `0x80` or a `0xBF`, the first and the last byte that continues a
#: character, which the count of the reading's characters must not count;
#: and a name the bytes do not refuse, which is never read again: the
#: `iconv` there would leave its mark.
PLACED_AS_THE_LOCALE_READS = [
    pytest.param("GB18030", None, "a" + chr(0x80) + "b",
                 id="gb18030-0xc2-0x80"),
    pytest.param("GB18030", None, A_HANZI_OF_C1_BYTES,
                 id="gb18030-0xc2-0x9b"),
    pytest.param("GB18030", None, "a" + chr(0x9F) + "b",
                 id="gb18030-0xc2-0x9f"),
    pytest.param("GBK", None, "a" + chr(0xAD) + "b", id="gbk-u+00ad-bytes"),
    pytest.param("SHIFT_JIS", None, "a" + chr(0x2028) + "b",
                 id="shift_jis-u+2028-bytes"),
    pytest.param("SHIFT_JIS", None, "a" + chr(0x81) + "Xb",
                 id="shift_jis-0xc2-0x81-0x58"),
    pytest.param("SHIFT_JIS", None, "a" + chr(0x81) + "Qb",
                 id="shift_jis-0xc2-0x81-0x51"),
    pytest.param("GB18030", MARKS, "caf" + chr(0xE9),
                 id="no-byte-refused-never-read-again"),
]

#: Names refused under a marker locale, and what the refusal says (#858).
#: The locale's reading is checked itself: GB18030 writes U+009B as
#: `0x81 0x30 0x83 0x37` and U+202E as `0x81 0x36 0xA7 0x31`, which are no
#: UTF-8, so a name holding either beside a hanzi the bytes refuse is
#: refused as its reading says. And the bytes decide, in #804's and #837's
#: words, where `locale` fails or is not there; where `iconv` is not there,
#: prints nothing, or prints the whole reading and then fails, which the
#: round trip alone would let through; where GB18030 cannot read a byte
#: (`0xFF`); under a single-byte charset, as Latin-1 reads U+FEFF's three
#: bytes, each alone; with a newline at the end, which `$(…)` drops from a
#: reading; and where `locale` answers nothing, UTF-8 or ASCII, under which
#: `iconv` is never asked.
REFUSED_AS_THE_BYTES_SAY = [
    pytest.param("GB18030", HONEST, None,
                 A_HANZI_OF_C1_BYTES + "\udc81" + "0" + "\udc83" + "7",
                 HOLDS_A_CONTROL_CHARACTER, id="gb18030-reads-u+009b"),
    pytest.param("GB18030", HONEST, None,
                 A_HANZI_OF_C1_BYTES + "\udc81" + "6" + "\udca7" + "1",
                 bin_dir_drawn_as_another("U+202E"),
                 id="gb18030-reads-u+202e"),
    pytest.param("GB18030", FAILS, None, A_HANZI_OF_C1_BYTES,
                 HOLDS_A_CONTROL_CHARACTER, id="a-locale-that-fails"),
    pytest.param("GB18030", MISSING, None, A_HANZI_OF_C1_BYTES,
                 HOLDS_A_CONTROL_CHARACTER, id="no-locale"),
    pytest.param("GB18030", HONEST, MISSING, A_HANZI_OF_C1_BYTES,
                 HOLDS_A_CONTROL_CHARACTER, id="no-iconv"),
    pytest.param("GB18030", HONEST, EMPTY, A_HANZI_OF_C1_BYTES,
                 HOLDS_A_CONTROL_CHARACTER, id="an-iconv-that-prints-nothing"),
    pytest.param("GB18030", HONEST, READS_THEN_FAILS, A_HANZI_OF_C1_BYTES,
                 HOLDS_A_CONTROL_CHARACTER,
                 id="an-iconv-that-reads-then-fails"),
    pytest.param("GB18030", HONEST, None, A_HANZI_OF_C1_BYTES + chr(0xDCFF),
                 HOLDS_A_CONTROL_CHARACTER, id="a-byte-gb18030-cannot-read"),
    pytest.param("ISO-8859-1", HONEST, None, "a" + chr(0xFEFF) + "b",
                 bin_dir_drawn_as_another("U+FEFF"),
                 id="a-single-byte-charset"),
    pytest.param("GB18030", HONEST, None, A_HANZI_OF_C1_BYTES + "\n",
                 HOLDS_A_CONTROL_CHARACTER, id="a-newline-at-the-end"),
    *(pytest.param(answer, HONEST, MARKS, A_HANZI_OF_C1_BYTES,
                   HOLDS_A_CONTROL_CHARACTER,
                   id=f"iconv-unasked-under-{answer or 'no-answer'}")
      for answer in ("", "UTF-8", "utf8", "ANSI_X3.4-1968", "US-ASCII")),
]

#: Names refused when the person's locale is `C` or `C.UTF-8` themselves
#: (#858), in #804's and #837's words, `iconv` never asked: three of
#: `PLACED_AS_THE_LOCALE_READS`.
REFUSED_UNDER_C_OR_UTF_8 = [
    pytest.param(A_HANZI_OF_C1_BYTES, HOLDS_A_CONTROL_CHARACTER,
                 id="0xc2-0x9b"),
    pytest.param("a" + chr(0xAD) + "b", bin_dir_drawn_as_another("U+00AD"),
                 id="u+00ad"),
    pytest.param("a" + chr(0x2028) + "b", bin_dir_drawn_as_another("U+2028"),
                 id="u+2028"),
]


def install_under_a_locale(tmp_path: Path, typed: str, environment: dict,
                           kind: str, iconv: str | None):
    """`--install` into `typed`, with `put_a_locale`'s `locale` and `iconv`
    first on `$PATH` in `tmp_path/tools`, and `environment` naming the
    person's locale (#858)."""
    tools = tmp_path / "tools"
    tools.mkdir()
    put_a_locale(tools, kind, iconv)
    return run_cmd("--install", home=tmp_path, cwd=tmp_path, env={
        "OPENREPOSHAPE_BIN_DIR": typed, **environment,
        "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}"})


@NO_NON_ASCII_INTO_GIT_BASH
@pytest.mark.parametrize("charmap, iconv, name", PLACED_AS_THE_LOCALE_READS)
def test_a_bin_dir_a_multibyte_locale_reads_as_text_is_placed(
        tmp_path, charmap, iconv, name):
    """The control check and `misdrawn_characters` look for UTF-8's bytes,
    and GB18030 reads `0xC2 0x9B` as a hanzi, not as U+009B: the directory
    was refused as holding a control character, in a locale where it holds
    none (#858). Where the bytes are refused, `locale charmap` is asked
    under the person's own `LANG`, and a multibyte charset's reading of the
    name, through `iconv`, has the last word. So a name GB18030, GBK or
    Shift_JIS reads as text is placed; and a name the bytes do not refuse
    is placed without `iconv` being asked."""
    result = install_under_a_locale(
        tmp_path, f"{bash_path(tmp_path)}/{name}",
        the_persons_locale(charmap), HONEST, iconv)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / name / "openRepoShape").read_bytes() \
        == COMMAND.read_bytes()
    assert not (tmp_path / "tools" / "iconv-ran").exists()


@NO_NON_ASCII_INTO_GIT_BASH
@pytest.mark.parametrize("charmap, kind, iconv, name, said",
                         REFUSED_AS_THE_BYTES_SAY)
def test_a_bin_dir_is_refused_as_its_bytes_or_its_reading_say(
        tmp_path, charmap, kind, iconv, name, said):
    """Where the locale's reading still holds a C1 control or a character
    drawn as another, it is refused as the reading says; and where the
    locale's charset is UTF-8, ASCII, single-byte or not said, where
    `iconv` is not there, prints nothing or cannot read the name, the bytes
    decide, as before (#858): refused, exit 2, nothing placed, never
    echoed, in #804's or #837's words. A newline at the end is looked for
    in the bytes as typed, not in the reading."""
    typed = f"{bash_path(tmp_path)}/{name}"
    result = install_under_a_locale(tmp_path, typed,
                                    the_persons_locale(charmap), kind, iconv)
    assert_a_bin_dir_is_refused(result, typed, said, COMMAND_REFUSAL_ENDS)
    assert [path.name for path in tmp_path.iterdir()] == ["tools"]
    assert not (tmp_path / "tools" / "iconv-ran").exists()


@NO_NON_ASCII_INTO_GIT_BASH
@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("name, said", REFUSED_UNDER_C_OR_UTF_8)
def test_a_bin_dir_is_refused_as_its_bytes_say_under_c_or_c_utf_8(
        tmp_path, name, said, locale):
    """The person's locale is `C` or `C.UTF-8`, as `LC_ALL` says, and
    `locale charmap` answers `ANSI_X3.4-1968` or `UTF-8`, as glibc's does:
    the bytes decide, in #804's and #837's words, and `iconv` is never
    asked (#858)."""
    typed = f"{bash_path(tmp_path)}/{name}"
    result = install_under_a_locale(tmp_path, typed, {"LC_ALL": locale},
                                    HONEST, MARKS)
    assert_a_bin_dir_is_refused(result, typed, said, COMMAND_REFUSAL_ENDS)
    assert not (tmp_path / "tools" / "iconv-ran").exists()


#: The Python codec that reads as each charset of
#: `PLACED_AS_THE_LOCALE_READS` does, and Latin-1's.
CODECS = {"GB18030": "gb18030", "GBK": "gbk", "SHIFT_JIS": "shift_jis",
          "ISO-8859-1": "latin-1"}


@NO_NON_ASCII_INTO_GIT_BASH
@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("name", ["openRepoShape", "install.sh"])
def test_locale_reading_counts_bytes_whatever_bash_itself_reads(
        tmp_path, name, locale):
    """`locale_reading` alone, lifted out of each file, with a `locale`
    function that answers each name's charset, under bash's own `C` and
    `C.UTF-8` (#858). In a GB18030 locale bash itself reads GB18030, and
    no such locale can be installed here, so `C.UTF-8` stands in for a
    multibyte locale of bash's own. For each name of
    `PLACED_AS_THE_LOCALE_READS` the bytes refuse, the reading is the one
    Python's codec gives; for Latin-1's U+FEFF bytes and a byte GB18030
    cannot read there is none. So the count is of bytes in either."""
    rows = [(param.values[0], param.values[2])
            for param in PLACED_AS_THE_LOCALE_READS
            if param.values[1] is None]
    rows += [("ISO-8859-1", "a" + chr(0xFEFF) + "b"),
             ("GB18030", A_HANZI_OF_C1_BYTES + chr(0xDCFF))]
    script = tmp_path / "reading.sh"
    write_script(script, f"LC_ALL={locale}\n"
                 "locale() { printf '%s\\n' \"$CHARMAP\"; }\n"
                 + shell_function(REPO / name, "locale_reading")
                 + 'while IFS= read -r -d "" CHARMAP && '
                 'IFS= read -r -d "" value; do\n'
                 '\tif reading="$(locale_reading "$value")"; then\n'
                 "\t\tprintf 'read %s\\0' \"$reading\"\n"
                 "\telse\n"
                 "\t\tprintf 'none\\0'\n"
                 "\tfi\n"
                 "done\n")
    ran = subprocess.run(
        [BASH, bash_path(script)], capture_output=True, check=False,
        input=b"".join(charmap.encode("ascii") + b"\0"
                       + value.encode("utf-8", "surrogateescape") + b"\0"
                       for charmap, value in rows),
        env=command_env(setup_sh=None))
    assert ran.returncode == 0, ran.stderr.decode("utf-8", "replace")
    expected = [b"read " + value.encode("utf-8", "surrogateescape").decode(
        CODECS[charmap]).encode("utf-8") for charmap, value in rows[:-2]]
    assert ran.stdout.split(b"\0")[:-1] == [*expected, b"none", b"none"]


#: A directory that already holds pipx's link (#563), whose name holds a
#: carriage return (#760) or U+202E (#837), and what its refusal says.
LINKED_BIN_DIRS = [
    pytest.param("a\rforged", HOLDS_A_CONTROL_CHARACTER,
                 id="a-carriage-return"),
    pytest.param("a" + RLO + "forged", bin_dir_drawn_as_another("U+202E"),
                 id="u+202e"),
]


@NO_FILE_NAMED_SO
@pytest.mark.parametrize("name, said", LINKED_BIN_DIRS)
def test_a_bin_dir_is_refused_before_a_link_in_it_names_it(
        tmp_path, name, said):
    """The symlink refusal (#563) names `$dir/openRepoShape`, so a directory
    holding a carriage return or U+202E that already has pipx's link in it
    would have the refusal print the value as typed (#760, #837): the value
    is refused first, and the link stays as it was."""
    bin_dir = tmp_path / name / "bin"
    bin_dir.mkdir(parents=True)
    link = bin_dir / "openRepoShape"
    link.symlink_to(tmp_path / "nowhere")
    result = run_cmd("--install", home=tmp_path, cwd=tmp_path,
                     env={"OPENREPOSHAPE_BIN_DIR": str(bin_dir)})
    assert_a_bin_dir_is_refused(result, str(bin_dir), said,
                                COMMAND_REFUSAL_ENDS)
    assert link.is_symlink()


# A ref or a repository the command would print, holding U+202E (#837). Each
# arranges its run in `tmp_path` and returns the arguments, the
# environment, the command to run, whose value the refusal names, and a
# path the run must not make (or None).

def a_ref_to_record(tmp_path):
    """`$OPENREPOSHAPE_REF`, which `--install` is asked to record (#564)."""
    return (("--install",),
            {"OPENREPOSHAPE_BIN_DIR": bash_path(tmp_path / "bin"),
             "OPENREPOSHAPE_REF": "v1" + RLO + "forged",
             "OPENREPOSHAPE_RECORD_REF": "1"},
            COMMAND, "$OPENREPOSHAPE_REF", tmp_path / "bin")


def a_recorded_ref(tmp_path):
    """The record beside an installed command, which every run reads."""
    _result, installed = install_at(tmp_path, PINNED)
    record = record_of(installed)
    record.write_bytes(("v1" + RLO + "forged\n").encode("utf-8"))
    return (("--version",), {}, installed,
            f"the ref recorded in {bash_path(record)}", None)


def a_repository_to_clone(tmp_path):
    """`$OPENREPOSHAPE_REPO`, which `--doctor` would clone, run from a copy
    of the command with no checkout beside it, and a `git` that leaves a
    mark if it runs."""
    fake = tmp_path / "fake-path"
    fake.mkdir()
    ran = tmp_path / "git-ran"
    write_script(fake / "git", f"#!/bin/sh\n: > '{ran}'\nexit 1\n")
    (fake / "git").chmod(0o755)
    copy = tmp_path / "copy" / "openRepoShape"
    copy.parent.mkdir()
    copy.write_bytes(COMMAND.read_bytes())
    return (("--doctor", str(tmp_path)),
            {"OPENREPOSHAPE_REPO": "acme/x" + RLO + "forged",
             "TMPDIR": str(tmp_path),
             "PATH": f"{fake}{os.pathsep}{os.environ['PATH']}"},
            copy, "OPENREPOSHAPE_REPO", ran)


@NO_NON_ASCII_INTO_GIT_BASH
@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("arrange", [a_ref_to_record, a_recorded_ref,
                                     a_repository_to_clone],
                         ids=lambda arrange: arrange.__name__)
def test_a_ref_or_repository_drawn_as_another_is_refused_unechoed(
        tmp_path, arrange, locale):
    """`ref_fault` and `shape_checkout` held a ref and a repository to
    `[![:print:]]`, which a UTF-8 locale's U+202E passes: the shape
    refusal then printed the ref as typed, and the clone's refusal the
    repository (#837). Both now refuse a character of `MISDRAWN` first, by
    its code point, under `C` and `C.UTF-8` alike: exit 2, nothing placed,
    no clone, and neither stream holds the value."""
    args, env, command, what, untouched = arrange(tmp_path)
    result = run_cmd(*args, home=tmp_path, cwd=tmp_path, command=command,
                     env={**env, "LC_ALL": locale})
    assert_refused_saying(result, f"{what} {drawn_as_another('U+202E')}.")
    if untouched is not None:
        assert not untouched.exists(), untouched


@POSIX_NAME
def test_the_default_directory_is_held_to_the_same_refusal(tmp_path):
    """No variable at all, and a `$HOME` that holds a `:`: the directory is
    `$HOME/.local/bin`, and it is refused the same, naming it."""
    home = tmp_path / "a:b"
    result = run_cmd("--install", home=home, cwd=tmp_path)
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"--install would place this command in '{home}/.local/bin', " \
        "which holds a ':'" in " ".join(result.stderr.split())
    assert list(tmp_path.iterdir()) == []


@POSIX_NAME
def test_a_respelled_bin_dir_is_held_to_the_same_refusal(tmp_path):
    """`cygpath` may answer a directory with a `:` of its own: the colon is
    refused after the Windows spelling, not before it, or this one would
    pass, and `D:\\tools\\bin` would be refused whatever `cygpath` said."""
    env = machine_path(tmp_path, ())
    env.pop("_log")
    fake_cygpath(tmp_path / "machine-path", WINDOWS_BIN_DIR, "/d/a:b/bin")
    result = run_cmd("--install", home=tmp_path, cwd=tmp_path,
                     env={**env, "OPENREPOSHAPE_BIN_DIR": WINDOWS_BIN_DIR})
    assert result.returncode == 2, result.stdout + result.stderr
    assert "--install would place this command in '/d/a:b/bin', which " \
        "holds a ':'" in " ".join(result.stderr.split())
    assert [path.name for path in tmp_path.iterdir()] == ["machine-path"]


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
#: `cygpath` is left off on purpose: `--install` asks it only to respell a
#: directory written for Windows (#649), and a test that hands this `$PATH`
#: one is a test of the refusal where no `cygpath` answers.
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
    # the CHILD's PATH, and this one holds no bash on purpose. The directory
    # as bash spells it, because this PATH holds no `cygpath` to respell a
    # Windows one (#649).
    result = subprocess.run(
        [BASH, bash_path(COMMAND), "--install"],
        capture_output=True, text=True, check=False, input="",
        env=command_env(home=tmp_path, setup_sh=None,
                        env={**env,
                             "OPENREPOSHAPE_BIN_DIR": bash_path(bin_dir)}))
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


@pytest.mark.parametrize("pythons, row", [
    pytest.param(("python",), "present, as python", id="python-alone"),
    pytest.param(("python3", "python"), "present", id="both"),
    pytest.param((), "MISSING", id="neither"),
])
def test_the_machine_report_finds_a_python_by_either_name(tmp_path, pythons,
                                                           row):
    """`python3`, THEN `python`, the order `--preflight` finds one in (#649).

    Where Python came from python.org, Git Bash has `python` and no
    `python3`, and the row said `python3 MISSING`, with the line pointing at
    `--preflight`, which then passed. It keeps its name and says which name
    answered, and only a machine with neither is short of one. Still by
    `command -v` alone: every fake here logs a run, and only `gh auth
    status` may be in the log.
    """
    result, log, _bin = install_with_machine(
        tmp_path, ("git", "gh", *pythons, "git-filter-repo"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert re.search(rf"^    python3 +{re.escape(row)}$", result.stdout,
                     re.M), result.stdout
    assert ("--preflight" in result.stdout) is (row == "MISSING"), \
        result.stdout
    assert log.read_text(encoding="utf-8").split("\n")[:-1] == \
        ["gh auth status"], log.read_text(encoding="utf-8")


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
    so the clone path is the one taken: the command clones this checkout
    first, then checks the ref, and refuses before `git checkout` is ever
    handed it.
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


# --- what `git clone` is handed for `$OPENREPOSHAPE_REPO` (#649) -------------

#: `$OPENREPOSHAPE_REPO` as a person sets it, and what a clone is handed for
#: it, `None` meaning the value itself. An owner/name becomes its github.com
#: URL; a URL, an scp address and a path go through as they are, and a
#: Windows path with a drive letter is a path in either slash (#649).
CLONE_URLS = [
    pytest.param("acme/openRepoShape",
                 "https://github.com/acme/openRepoShape.git", id="owner-name"),
    pytest.param("https://example.invalid/acme/openRepoShape.git", None,
                 id="url"),
    pytest.param("git@example.invalid:acme/openRepoShape.git", None,
                 id="scp"),
    pytest.param("/srv/git/openRepoShape.git", None, id="posix-path"),
    pytest.param("C:/src/openRepoShape", None, id="drive-slash"),
    pytest.param("C:\\src\\openRepoShape", None, id="drive-backslash"),
    pytest.param("d:\\work\\openRepoShape.git", None, id="drive-lower-case"),
]


def cloned_for(tmp_path, repo: str, caller: str) -> list:
    """What the clone `caller` makes is handed for `$OPENREPOSHAPE_REPO`:
    the value setup.sh is given to clone, through a setup.sh that prints
    it, or the URL `--doctor`'s own `git clone` names, through a `git` that
    prints it and fails, from a copy of the command with no checkout of the
    standard beside it. Nothing is cloned and nothing is fetched."""
    if caller == "setup.sh":
        stub = tmp_path / "setup.sh"
        write_script(stub, '#!/usr/bin/env bash\n'
                     'printf "CLONES %s\\n" "$OPENREPOSHAPE_REPO"\n')
        result = run_cmd("--preflight", setup_sh=stub,
                         env={"OPENREPOSHAPE_REPO": repo})
        assert result.returncode == 0, result.stdout + result.stderr
    else:
        fake = tmp_path / "fake-path"
        fake.mkdir()
        write_script(fake / "git", '#!/bin/sh\n[ "$1" = clone ] && '
                     'printf "CLONES %s\\n" "$4"\nexit 1\n')
        (fake / "git").chmod(0o755)
        copy = tmp_path / "openRepoShape"
        copy.write_bytes(COMMAND.read_bytes())
        result = run_cmd("--doctor", str(tmp_path), command=copy, env={
            "OPENREPOSHAPE_REPO": repo, "TMPDIR": str(tmp_path),
            "PATH": f"{fake}{os.pathsep}{os.environ['PATH']}"})
        assert result.returncode == 2, result.stdout + result.stderr
        assert "could not clone" in result.stderr
    return re.findall(r"^CLONES (.*)$", result.stdout, re.M)


@pytest.mark.parametrize("caller", ["setup.sh", "doctor"])
@pytest.mark.parametrize("repo, url", CLONE_URLS)
def test_a_clone_is_handed_a_path_or_url_as_it_is(tmp_path, repo, url,
                                                  caller):
    """`shape_clone_url`, through both of its callers (#649). A drive
    letter was read as an owner, so `C:/src/openRepoShape` became
    `https://github.com/C:/src/openRepoShape.git`, a repository on
    github.com that nobody named, for setup.sh's clone and the doctor's."""
    assert cloned_for(tmp_path, repo, caller) == [url or repo]


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
