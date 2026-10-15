# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures: one real scaffold run, cloned, copied per test.

NO NETWORK AND NO GITHUB. Every test here runs `scaffold-project.py` with
`--local-remote-dir`, which creates three BARE repositories in a temporary
directory and uses them as origins. Nothing in this suite may create a real
repository; if a test ever needs `gh`, it is the wrong test.

AND THAT IS ENFORCED, NOT HOPED FOR (#296). A session fixture at the end of
this file puts a GUARD `gh` (`tests/gh_guard.py`) first on PATH for every
child of every test: it answers the two questions the doctor's `machine` row
and the installed command's machine report ask -- `gh --version` and `gh
auth status` -- as an installed `gh` with no login, and refuses and logs
anything else, and a check after each test fails that test by name if the
guard refused one of its calls. A test that means to run `gh` puts a stub
of its own ahead of the guard, as the existing ones do.

The scaffold and the recursive clone happen ONCE per session because they are
the slow part; each test that mutates a tree gets its own `copytree` of the
clone. A submodule's `.git` is a file holding a RELATIVE path into
`../.git/modules/<name>`, so a plain copy of the whole clone stays internally
consistent — which is what makes the cheap fixture honest rather than merely
fast.
"""

from __future__ import annotations

import functools
import importlib.util
import os
import re
import select
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import time
from argparse import Namespace
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

#: `repo_shape` is the dependency-free module every validator imports (see
#: its own docstring), so importing it here costs nothing at collection
#: time — the same `sys.path.insert` every test module that reads it
#: already does (`tests/test_naming_policy.py` and others).
#: `PIN_SOURCE_ENV_PREFIX` is read from there rather than re-spelled, so
#: `run_script` below and `resolve_link_source` can never name the prefix
#: two different ways.
sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import PIN_SOURCE_ENV_PREFIX  # noqa: E402

SCAFFOLD = REPO / "scaffold-project.py"
PROJECT = "Atlas"
ORG = "testorg"

#: A local-path submodule is a `file://` clone, which git refuses by default
#: since the 2022 advisories. The scaffold passes this itself where it must;
#: the tests pass it for their own clones. It is a TEST-HARNESS concession to
#: using bare repositories on disk as origins, not something a real project
#: ever needs.
FILE_PROTOCOL = ["-c", "protocol.file.allow=always"]


def clone_just_pushed(remote: Path, dest: Path,
                      branch: str | None = None, *, recurse: bool = True,
                      bare: bool = False, config: Sequence[str] = (),
                      env: Mapping[str, str] | None = None
                      ) -> subprocess.CompletedProcess:
    """`git clone --recurse-submodules` of a bare remote a scaffold has JUST
    pushed into, READ THROUGH GIT AND NOT THROUGH ITS FILES (#440).

    A clone of a plain path is git's local clone: it walks the source's
    `objects/` and links or copies each file in turn. The push that ended the
    scaffold can leave maintenance running in the remote, which packs the
    loose objects and deletes them mid-walk, and the clone dies `failed to
    copy file to '<dest>/.git/objects/..': No such file or directory` (the
    macOS runner, twice in 90 minutes on 2026-10-12). Upload-pack reads the
    object store, which a repack does not break.

    `--no-local` does that for the root. The two leg clones
    `--recurse-submodules` makes are git's own, from the plain path
    `.gitmodules` records, so each leg URL is rewritten to `file://` with a
    `url.<base>.insteadOf` for the one command: a `-c` is not stored, so the
    clone's own `origin` and `submodule.<name>.url` keep the plain paths. The
    prefix is the directory RESOLVED, as `scaffold-project.py` writes it into
    `.gitmodules`, in both of a Windows path's spellings.

    `branch` is `-b <branch>`: `adopt-project.py execute` pushes its split
    branch into the SOURCE, a plain repository, which is then `remote`.
    The two legs it pushed into `--local-remote-dir` are read by the
    rewrite only while that directory sits under `remote`'s parent.

    The keywords are for the tests whose subject is the clone itself or the
    environment it is made in (#544). `recurse=False` is a plain `git clone`,
    which leaves a submodule's mount empty; `bare` is a bare copy of the
    remote, with no submodules to read; `config` is more `-c` arguments for
    the one command (`["-c", "core.autocrlf=true"]`); and `env` is variables
    laid over this process's own, as `git_under` and `raw` lay them. The
    output is decoded as UTF-8 whatever the platform's code page: a refusal
    names a path, and a project's name can be any text.
    """
    remote = Path(remote)
    remotes = remote.parent.resolve()
    uri = remotes.as_uri().rstrip("/") + "/"
    prefixes = dict.fromkeys([os.path.join(str(remotes), ""),
                              remotes.as_posix().rstrip("/") + "/"])
    rewrites = [arg for prefix in prefixes
                for arg in ("-c", f"url.{uri}.insteadOf={prefix}")]
    if bare:
        mode = ["--bare"]
    else:
        mode = ["--recurse-submodules"] if recurse else []
    return subprocess.run(
        ["git", *FILE_PROTOCOL, *config, *rewrites, "clone", "-q",
         "--no-local", *(["-b", branch] if branch else []), *mode,
         str(remote), str(dest)],
        capture_output=True, encoding="utf-8", errors="replace", check=False,
        env=None if env is None else {**os.environ, **env})


def cloned_just_pushed(remote: Path, dest: Path, branch: str | None = None,
                       **options) -> Path:
    """`clone_just_pushed`, failing the test where the clone fails; `dest`.
    `options` are the ones `clone_just_pushed` takes."""
    cloned = clone_just_pushed(remote, dest, branch, **options)
    assert cloned.returncode == 0, (f"git clone of {remote} failed:\n"
                                    f"{cloned.stderr}{cloned.stdout}")
    return Path(dest)


def load_without_bytecode(path: Path, name: str):
    """`path` run as a module called `name`, and no bytecode written for it
    (#544; it is `load()` of `test_bootstrap_spelling.py`, #456, moved here).

    `SourceFileLoader` caches what it compiles in a `__pycache__` beside the
    source, and these sources are the TEMPLATES: a tree other tests read file
    by file as text (`test_scaffold_leg_path_collisions.py` does, and a `.pyc`
    is not UTF-8), and a tree a materializer walks. `.gitignore` hides the
    stray, so `git status` never says it is there. The flag is process-wide, so
    it is restored; it also covers the `repo_shape` a root imports as it runs.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    wrote_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = wrote_bytecode
    return module


#: `load_without_bytecode`'s counterpart for a CHILD process (#544). `family.py
#: siblings` runs the standard's `templates/family-root/scripts/siblings.py`
#: through `runpy`, and that file imports `bootstrap` from beside it, so
#: without this in the child's environment the import writes
#: `__pycache__/bootstrap.*.pyc` into the template tree.
NO_BYTECODE = {"PYTHONDONTWRITEBYTECODE": "1"}


#: THE DEFAULT IDENTITY `git()` GIVES GIT (#279). A commit needs an author and
#: a committer, and git guesses them from the passwd entry and a hostname with
#: a domain; a container whose hostname has none cannot, and the commit dies
#: with `Author identity unknown`. `git()` below puts the two values here ahead
#: of every verb as `-c` CONFIG (`IDENTITY_CONFIG`), and `run_script` reuses
#: the same two for the environment of the script it starts, so this file
#: names its default once, for both. Other test files still spell the same
#: pair for their own commits, and are not changed here. It is the spelling
#: the suite already used; the `.invalid` TLD is reserved (RFC 2606), so no
#: address here can ever be a real one.
IDENTITY_NAME = "openRepoShape tests"
IDENTITY_EMAIL = "tests@openreposhape.invalid"

#: THE DEFAULT AS CONFIG, NEVER AS ENVIRONMENT (#279). `GIT_AUTHOR_NAME` and
#: `GIT_COMMITTER_NAME` OUTRANK `user.name` in git's own precedence, so a
#: default exported through `env` would silently replace the identity of every
#: call site that gives its own: `as_human`'s `Source Human`, and the
#: `git("-c", "user.name=t", "-c", "user.email=t@t", "commit", ...)` that is
#: the suite's commonest spelling, would record the default, and the test
#: would assert on the wrong author.
#:
#: WHERE IT RANKS, strongest first: the four `GIT_AUTHOR_NAME`,
#: `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME` and `GIT_COMMITTER_EMAIL` where
#: EXPORTED in the environment, each for its own role (the three CI jobs export
#: all four as `openRepoShape CI`); a `-c` LATER on the same command line,
#: which is how a call site's own `-c user.name=...` beats it; this default;
#: then every identity read from a config FILE, global, system or the
#: repository's own `user.name`. An exported `EMAIL` is NOT in the top group:
#: git reads it only where no `user.email` is set, so the default's address
#: hides it. The default fills a gap and overrides no call site and none of
#: those four variables, but it DOES outrank a developer's own
#: `~/.gitconfig`: a commit through `git()` that gives no identity records
#: `openRepoShape tests` where it used to record the developer. That is
#: harmless here, because no test reads such an author and nothing in the
#: suite writes `user.name` into a repository's config. A test that needs its
#: own identity to take effect through `git()` passes it as `-c` ahead of the
#: verb, or exports the four variables; `git("config", "user.name", ...)`, or
#: an exported `EMAIL`, would lose to this default.
#: `tests/test_git_helper_identity.py` holds all of it to account, on a runner
#: that exports an identity as well as on one that does not.
IDENTITY_CONFIG = ["-c", f"user.name={IDENTITY_NAME}",
                   "-c", f"user.email={IDENTITY_EMAIL}"]

#: THE ENTRY-POINT TESTS THAT CANNOT RUN ON WINDOWS. Two shapes of test wear
#: this: one that runs `bash`, and one that puts a `#!`-shebang script named
#: `gh` on PATH and expects the operating system to execute it. Windows has
#: neither — `bash.exe` IS on the GitHub runner, so a `shutil.which("bash")`
#: guard does not fire, but `setup.sh` is a POSIX shell script that probes
#: `python3` then `python`, and a shebang means nothing to CreateProcess.
#: Skipping is honest because Windows has its OWN entry point and OWN suite:
#: `setup-project.py`, covered case for case in `test_setup_project_py.py`.
#: A shared `skipif` object rather than a named marker because there is no
#: pytest.ini to register one in, and an unregistered marker is a warning.
WINDOWS_SKIP = pytest.mark.skipif(
    os.name == "nt",
    reason="needs a POSIX shell and shebang execution; on Windows the entry "
           "point is setup-project.py (tests/test_setup_project_py.py)")


def _git_for_windows() -> Path | None:
    """Git for Windows' own directory, from the `git` that runs this suite.

    `git --exec-path` answers `<root>/mingw64/libexec/git-core` there, and
    `<root>/usr/bin/bash.exe` is its bash. None off Windows, and where that
    git is some other build, with no such bash beside it.
    """
    if os.name != "nt":
        return None
    try:
        answer = subprocess.run(["git", "--exec-path"], capture_output=True,
                                text=True, check=False).stdout.strip()
    except OSError:
        return None
    parents = Path(answer).parents if answer else ()
    if len(parents) < 3:
        return None
    root = parents[2]
    return root if (root / "usr" / "bin" / "bash.exe").is_file() else None


GIT_FOR_WINDOWS = _git_for_windows()

#: THE BASH THAT `openRepoShape` AND `install.sh` ARE TESTED UNDER (#585).
#: Off Windows, the `bash` on PATH. On Windows, Git Bash: Git for Windows'
#: own `usr\bin\bash.exe`, found beside the git this suite runs and NEVER
#: from PATH, because a bare `bash` there can be `System32\bash.exe`, the WSL
#: launcher, and `subprocess` looks in System32 before it reads PATH at all.
#: `usr\bin` and not `bin`: `bin\bash.exe`, which Git Bash's own shortcut
#: runs, puts Git's `mingw64\bin` and `usr\bin` FIRST on PATH, ahead of a
#: test's fake `curl`, and a test's own PATH of a few programs would hold
#: every one of Git's. `git_bash_session` puts the two there behind the
#: fakes instead. These suites wore `WINDOWS_SKIP` until then.
if os.name == "nt":
    BASH = (str(GIT_FOR_WINDOWS / "usr" / "bin" / "bash.exe")
            if GIT_FOR_WINDOWS is not None else None)
else:
    BASH = shutil.which("bash")

BASH_SKIP = pytest.mark.skipif(
    BASH is None,
    reason="needs bash: on Windows, Git for Windows' own usr\\bin\\bash.exe "
           "beside the git on PATH, which this machine does not have")


@functools.lru_cache(maxsize=None)
def _cygpath(flag: str, path: str) -> str:
    """Git for Windows' `cygpath <flag>`: the spelling bash itself uses."""
    return subprocess.run(
        [str(GIT_FOR_WINDOWS / "usr" / "bin" / "cygpath.exe"), flag, "--",
         path], capture_output=True, text=True, check=True).stdout.strip()


def bash_path(path) -> str:
    """`path` as `BASH` spells it, for its argv, its environment and what it
    prints (#585): unchanged off Windows, and `/d/a/...` under Git Bash, from
    its own `cygpath -u` — the spelling Git Bash gives `$HOME`, `$TMPDIR`,
    `PATH` and `pwd`, and so the one a person there types."""
    if GIT_FOR_WINDOWS is None:
        return str(path)
    return _cygpath("-u", str(path))


def native_path(text: str) -> Path:
    """The other way: a path `BASH` printed, as this interpreter opens it."""
    if GIT_FOR_WINDOWS is None:
        return Path(text)
    return Path(_cygpath("-w", text))


@pytest.fixture
def git_bash_session(monkeypatch):
    """PATH and `MSYSTEM` as Git Bash makes them, for a test that runs
    `BASH` (#585); off Windows, nothing.

    Git Bash puts Git's `mingw64\\bin` and `usr\\bin` ahead of the Windows
    PATH, which is where a person there finds `mktemp`, `cp` and the bash
    that `openRepoShape` runs `setup.sh` with, ahead of System32's WSL
    launcher. Here they go ahead of `os.environ["PATH"]`, so a fake a test
    puts first still comes first. Neither directory holds a `gh`, so the
    session's gh guard still answers. The GitHub runner's own PATH already
    holds both, and Git's `bin` before System32; Git for Windows' default
    install puts only its `cmd` on PATH, and there, without this, `mktemp`
    is not found and `bash` is the WSL launcher.
    """
    if GIT_FOR_WINDOWS is None:
        return
    # Git for Windows on ARM64 ships `clangarm64` where x64 has `mingw64`.
    msystem = "clangarm64" if (GIT_FOR_WINDOWS / "clangarm64").is_dir() \
        else "mingw64"
    monkeypatch.setenv("PATH", os.pathsep.join([
        str(GIT_FOR_WINDOWS / msystem / "bin"),
        str(GIT_FOR_WINDOWS / "usr" / "bin"), os.environ.get("PATH", "")]))
    monkeypatch.setenv("MSYSTEM", msystem.upper())


def rmtree(path: Path) -> None:
    """`shutil.rmtree` that also works over a git object store on Windows.

    Git writes loose objects and packs READ-ONLY, and Windows refuses to
    unlink a read-only file — so a plain `rmtree` over a checkout raises
    PermissionError there and succeeds everywhere else. The handler clears the
    read-only bit and retries the one call that failed. `onerror` rather than
    `onexc`: the newer spelling is 3.12+, and this standard runs on 3.9.
    """
    def clear_readonly(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    shutil.rmtree(path, onerror=clear_readonly)


def git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    """`git <args>` in `cwd`, under `IDENTITY_CONFIG` (#279).

    A test that makes a commit, a tag or a merge through here and gives no
    identity of its own used to depend on git guessing one, and failed with
    `Author identity unknown` wherever git could not (`stage_unmerged`'s
    `commit-tree` in `tests/test_shape_doctor.py`, `commit` in
    `tests/test_pin_validator.py`). The default goes in as CONFIG so that it
    yields to a later `-c` in `args` and to the four `GIT_AUTHOR_*` and
    `GIT_COMMITTER_*` variables where exported, and outranks an identity a
    config file gives, or an exported `EMAIL`; the comment on
    `IDENTITY_CONFIG` says where it ranks and why it must not be an
    environment variable. The failure message below names `args` only: the
    two `-c` pairs are the helper's, not the test's.
    """
    proc = subprocess.run(["git", *IDENTITY_CONFIG, *args], cwd=str(cwd),
                          capture_output=True, text=True, check=False)
    if check and proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} in {cwd} failed:\n"
                             f"{proc.stderr}{proc.stdout}")
    return proc


def object_store(repo: Path) -> tuple[int, int]:
    """`(loose objects, packs)` of one repository, from `git count-objects -v`
    run in it. A submodule's working tree answers for its own store under the
    superproject's `.git/modules/`."""
    fields = dict(
        line.split(": ", 1)
        for line in git("count-objects", "-v", cwd=repo).stdout.splitlines())
    return int(fields["count"]), int(fields["packs"])


def assert_store_read_through_git(repo: Path, name: str) -> None:
    """`repo`'s object store holds a pack and no loose object (#440).

    A clone that walked the source's object files (git's local clone, which
    is what a plain path gets) leaves them as the source had them: LOOSE, for
    a repository somebody has just pushed 8 or 25 objects into. A clone made
    through the transport receives one pack. That difference is the one
    observable of the two, and it is what the macOS race needs: a clone that
    never lists the source's `objects/` cannot lose a file from the list.
    """
    loose, packs = object_store(repo)
    assert loose == 0, (
        f"{name} holds {loose} loose objects: the clone read the source's "
        "object files one by one (git's local clone) instead of through the "
        "transport")
    assert packs >= 1, f"{name} holds no pack: nothing was received"


def assert_read_through_git(clone: Path,
                            legs: tuple[str, ...] = ("spec", "code")) -> None:
    """The assembly root at `clone` and each of its legs were read through
    git (`assert_store_read_through_git`), not through the source's files.
    The one assertion behind every #440 test that clones a scaffold: the two
    session fixtures, `setup.sh` and `setup-project.py`."""
    assert_store_read_through_git(clone, f"the root of {clone}")
    for leg in legs:
        assert_store_read_through_git(clone / leg, f"the {leg} leg of {clone}")


def is_pin_source_name(name: str) -> bool:
    """Whether `name` is a `PIN_SOURCE_ENV_PREFIX`-named variable.

    WINDOWS ENVIRONMENT NAMES ARE CASE-INSENSITIVE (Copilot, PR #128) —
    `SHAPE_PIN_SOURCE_OPENXDOX` and any other-cased spelling of the same
    name are THE SAME VARIABLE there — so the check folds to uppercase
    before comparing. Shared by `blank_unnamed_pin_sources` and
    `clear_ambient_pin_sources` below rather than written out twice: the
    second copy is exactly how this rule went missing from
    `clear_ambient_pin_sources` in the first place (Copilot again, a
    round later, on that very function) after `blank_unnamed_pin_sources`
    had already been fixed — one predicate cannot drift out of step with
    itself.
    """
    return name.upper().startswith(PIN_SOURCE_ENV_PREFIX)


def blank_unnamed_pin_sources(env: dict, asked: dict) -> dict:
    """`env`, but every inherited `PIN_SOURCE_ENV_PREFIX`-named variable
    THIS CALL did not ask for is blanked to `""`, and an inherited
    case-variant alias of one it DID ask for is dropped outright.

    `""` rather than deleting a blanked key matches how
    `resolve_link_source` already reads an empty value as absent
    (`if env_value:`, `scripts/repo_shape.py`) and how `lane_trailer`
    already reads an empty `LANES_LANE` as "no lane"
    (`scripts/shape_materialize.py`) — the same convention on both
    variables, not a new one. An inherited alias whose CASE does not
    match the caller's own spelling is DELETED rather than blanked,
    though: leaving both behind would hand a real Windows child two keys
    that its own case-folding treats as one, disagreeing about the value,
    which is exactly the ambiguity naming one of them was supposed to
    resolve. `asked`'s own keys are folded the same way `is_pin_source_
    name` folds `env`'s, so "did the caller ask for THIS one" cannot
    disagree with "is this a pin-source name at all" about what case
    means here.
    """
    asked_by_fold = {name.upper(): name for name in asked}
    result = dict(env)
    for name in env:
        if not is_pin_source_name(name):
            continue
        caller_spelling = asked_by_fold.get(name.upper())
        if caller_spelling is None:
            result[name] = ""
        elif name != caller_spelling:
            del result[name]
    return result


def clear_ambient_pin_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every `PIN_SOURCE_ENV_PREFIX`-named variable THIS PROCESS's own
    `os.environ` carries, cleared for the rest of the test `monkeypatch`
    belongs to.

    `blank_unnamed_pin_sources` above only reaches a SPAWNED CHILD's
    environment; it cannot do anything for a test that calls
    `resolve_link_source` (or `link_pins_from_trees`, built on it)
    directly, in this same process, the way the "reading a link's own
    declaration" section of `tests/test_naming_policy.py` does (Copilot,
    PR #128, three times over: first for the one product such a test
    names itself, then again once it was clear `link_pins_from_trees`
    resolves EVERY name it is given, not only the first, then a third
    time because this function's own prefix check did not yet fold case
    the way `blank_unnamed_pin_sources`'s did). Every name, not one
    product picked by hand, so a test that names a second product — or a
    third, tomorrow — is not exposed again the way naming `openXdox`
    alone here would still have left `SHAPE_PIN_SOURCE_OPENDOX` free to
    answer for `openDox`.
    """
    for name in list(os.environ):
        if is_pin_source_name(name):
            monkeypatch.delenv(name, raising=False)


def run_script(script: Path, *args: str, cwd: Path | None = None,
               env: dict | None = None, input: str | None = None,
               stdin: int | None = None,
               merge_stderr: bool = False) -> subprocess.CompletedProcess:
    """Run one tool under test, with stdin closed by default.

    A test in this suite is often asserting what a tool does when nobody is
    there to answer a prompt — the whole point is that the run is
    unattended. Leaving stdin unset would inherit the pytest process's own
    console handle, and on Windows an inherited console reports isatty() as
    True even under CI, where the test runner has no real terminal either —
    the same assertion would then pass or fail depending on the OS, not on
    the tool. `subprocess.DEVNULL` makes every run non-interactive by
    default so the behaviour under test does not depend on how the test
    process itself was launched. A caller that DOES want to exercise the
    non-tty-but-readable path passes `input=` (a pipe), and one that wants
    something else entirely — a real pty, say — passes `stdin=` explicitly;
    `subprocess.run` itself refuses to accept `input` together with `stdin`,
    so there is nothing to reconcile between the two here.

    `merge_stderr` sends stderr into the same pipe as stdout, as `> log 2>&1`
    does, and leaves `stderr` None. A tool's piped stdout is block-buffered
    and its stderr is not, so this is the only way a test sees the order a
    person reading that log sees.
    """
    asked = env or {}
    env = {**os.environ, **asked}
    #: THE LANE IS NOT INHERITED (Copilot, PR #112). `LANES_LANE` changes
    #: what `update-shape.py check` and `shape-doctor.py` print — by design
    #: — so a suite that passed it through would assert a different line
    #: depending on whether the person running it happened to be inside a
    #: lane, and the baseline half of a with/without comparison would
    #: quietly become a second lane run. Blanked for every tool under test
    #: unless the CALLER named it, which is how a test asks for a lane.
    if "LANES_LANE" not in asked:
        env["LANES_LANE"] = ""
    #: NOR IS ANY PIN-SOURCE OVERRIDE (2026-09-11, #114, #120, #126). Every
    #: `SHAPE_PIN_SOURCE_<PRODUCT>` name (`repo_shape.PIN_SOURCE_ENV_PREFIX`)
    #: changes what `resolve_link_source` resolves a link to — rule 2 there
    #: reads it BEFORE rule 3, the cwd-derived sibling checkout — for
    #: exactly the same reason `LANES_LANE` is blanked above: a suite that
    #: passed one through would verify or fail to verify a link depending
    #: on what the person (or the CI box) running it happens to have
    #: exported, not on what the test wrote. PR #120 hit this directly:
    #: `SHAPE_PIN_SOURCE_OPENXDOX`, inherited from a workstation shell where
    #: it pointed at a real `openDox`-declaring checkout, made an
    #: offline-link warning stop printing, and that PR could only fix it
    #: locally, one test at a time, because this rule did not exist yet.
    #: Blanked for every product-specific variable unless the CALLER named
    #: that exact name, which is how a test asks for one — see
    #: `blank_unnamed_pin_sources` above for the Windows case-folding this
    #: needs that `LANES_LANE`, a single fixed name, never did.
    env = blank_unnamed_pin_sources(env, asked)
    env.setdefault("GIT_AUTHOR_NAME", IDENTITY_NAME)
    env.setdefault("GIT_AUTHOR_EMAIL", IDENTITY_EMAIL)
    env.setdefault("GIT_COMMITTER_NAME", IDENTITY_NAME)
    env.setdefault("GIT_COMMITTER_EMAIL", IDENTITY_EMAIL)
    if input is None and stdin is None:
        stdin = subprocess.DEVNULL
    return subprocess.run([sys.executable, str(script), *args],
                          cwd=str(cwd) if cwd else None,
                          stdout=subprocess.PIPE,
                          stderr=(subprocess.STDOUT if merge_stderr
                                  else subprocess.PIPE),
                          text=True, check=False, env=env, input=input,
                          stdin=stdin)


@pytest.fixture(scope="session")
def scaffolded(tmp_path_factory) -> dict:
    """One real scaffold into local bare remotes, plus a recursive clone."""
    base = tmp_path_factory.mktemp("shape")
    remotes, work, clones = base / "remotes", base / "work", base / "clones"
    result = run_script(
        SCAFFOLD, "--org", ORG, "--project", PROJECT,
        "--elected-by", "Test Human", "--elected-on", "2026-09-02",
        "--local-remote-dir", str(remotes), "--work-dir", str(work),
    )
    assert result.returncode == 0, result.stderr + result.stdout
    clones.mkdir()
    cloned_just_pushed(remotes / f"{PROJECT}.git", clones / PROJECT)
    return {
        "base": base, "remotes": remotes, "work": work,
        "clone": clones / PROJECT, "stdout": result.stdout,
        "stderr": result.stderr,
    }


@pytest.fixture
def project(scaffolded, tmp_path) -> Path:
    """A private, mutable copy of the cloned assembly root."""
    target = tmp_path / PROJECT
    shutil.copytree(scaffolded["clone"], target, symlinks=True)
    return target


ADOPT = REPO / "adopt-project.py"

#: A repository shaped like the ones this standard is asked to adopt: a
#: specification side, an implementation side, project-level workflow tooling
#: that belongs to neither, and two genuinely ambiguous corners. Small enough
#: to assert every row of the plan against, which is the point.
SYNTHETIC_TREE = {
    # spec
    "specs/001-feature/spec.md": "# The feature\n",
    "specs/001-feature/tasks.md": "- [ ] one\n",
    "openspec/changes/add-thing/proposal.md": "## Why\n",
    "contracts/policy.yaml": "schema_version: 1\nkind: policy\n",
    "docs/architecture.md": "# Architecture\n",
    # code
    "src/app/main.py": "import contracts_reader\n",
    "src/app/util.py": "VALUE = 1\n",
    "tests/test_main.py": "def test_ok():\n    assert True\n",
    ".github/workflows/ci.yml": "on: [push]\n",
    "pyproject.toml": "[project]\nname = 'thing'\n",
    "sonar-project.properties": "sonar.projectKey=thing\n",
    "docker/Dockerfile": "FROM python:3.12\n",
    # code, by extension majority alone: no rule names this directory
    "pkg_core/__init__.py": "",
    "pkg_core/engine.py": "def run():\n    return 1\n",
    "pkg_core/table.json": "{}\n",
    # root
    "README.md": "# Thing\n",
    "LICENSE": "Apache-2.0\n",
    ".gitignore": "__pycache__/\n",
    "Makefile": "test:\n\tpytest\n",
    "AGENTS.md": "Follow the procedure.\n",
    "CLAUDE.md": "Follow the procedure.\n",
    ".specify/scripts/plan.sh": "#!/bin/sh\necho plan\n",
    ".specify/templates/spec.md": "# template\n",
    ".github/CODEOWNERS": "* @team\n",
    # ambiguous
    "examples/golden-run/expected.yaml": "result: ok\n",
    ".claude/commands/ship.md": "ship it\n",
    "release.yaml": "channel: stable\n",
}


#: The second and third commits of `make_source_repo`: `(path, new body,
#: message)`. They are DATA rather than statements so that a caller passing
#: its own `tree` can say which of ITS files the later commits touch — a
#: spec-only repository has no `src/app/main.py` to implement.
DEFAULT_EDITS = (
    ("specs/001-feature/spec.md", "# The feature\n\nA second paragraph.\n",
     "Extend the specification"),
    ("src/app/main.py",
     "import contracts_reader\n\n\ndef main():\n    return 0\n",
     "Implement main"),
)


def make_source_repo(path: Path, tree: dict | None = None,
                     branch: str = "main", edits: tuple | None = None) -> Path:
    """A local repository with SEVERAL commits, so history can be verified.

    Three commits, each touching a different side of the tree: an extraction
    that kept only the tip would still pass a file-count check, and would fail
    this one.
    """
    tree = dict(tree or SYNTHETIC_TREE)
    edits = DEFAULT_EDITS if edits is None else edits
    path.mkdir(parents=True, exist_ok=True)
    git("init", "-q", "-b", branch, ".", cwd=path)
    env = {"GIT_AUTHOR_NAME": "Source Human",
           "GIT_AUTHOR_EMAIL": "human@source.invalid",
           "GIT_COMMITTER_NAME": "Source Human",
           "GIT_COMMITTER_EMAIL": "human@source.invalid"}

    def commit(message: str) -> None:
        proc = subprocess.run(["git", "add", "-A", "--", "."], cwd=str(path),
                              capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stderr
        proc = subprocess.run(["git", "commit", "-q", "-m", message],
                              cwd=str(path), capture_output=True, text=True,
                              check=False, env={**os.environ, **env})
        assert proc.returncode == 0, proc.stderr + proc.stdout

    for name, body in tree.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    commit("Initial import")
    for name, body, message in edits:
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        commit(message)
    return path


@pytest.fixture
def source_repo(tmp_path) -> Path:
    return make_source_repo(tmp_path / "Thing")


def write_plan(source: Path, out: Path, project: str = "Northwind",
               org: str = "testorg", extra: tuple = ()) -> subprocess.CompletedProcess:
    return run_script(ADOPT, "plan", "--source", str(source),
                      "--project", project, "--org", org,
                      "--elected-by", "Test Human",
                      "--elected-on", "2026-09-02",
                      "--out", str(out), *extra)


def resolve(plan_path: Path, path: str, leg: str,
            why: str = "answered by the test") -> None:
    """Answer one `review_required` entry the way a human or an AI would.

    The plan goes back LF, as `plan` wrote it: `Path.write_text` translates
    every `\\n` to CRLF on Windows, and a helper that reads the plan as bytes
    afterwards (`edited` in `test_adopt_submodules.py`) then finds none of its
    lines. `open` with `newline`, because `write_text` has no such parameter
    before 3.10 and this standard runs on 3.9.
    """
    text = plan_path.read_text(encoding="utf-8")
    needle = f"  - path: {path}\n    leg: null\n"
    assert needle in text, f"{path} is not an unresolved entry in the plan"
    with plan_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.replace(
            needle, f"  - path: {path}\n    leg: {leg}\n"
                    f"    resolution: \"{why}\"\n", 1))


# --- `.gitmodules` sources, and what `check` and `execute` say of them -----
#
# Shared by `test_adopt_history_gitlinks.py` (#195) and
# `test_adopt_gitmodules_values.py` (#215), which build sources that hold a
# submodule at GITLINK, at the tip or only in the history, beside a
# `.gitmodules` git's submodule reader may die on.

GITMODULES = ".gitmodules"
#: The submodule those sources hold, registered under the name `b`.
GITLINK = "vendor/b"


def as_human(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    """`git <args>` with an identity, for the commits and merges a test
    makes in a source."""
    return git("-c", "user.name=Source Human",
               "-c", "user.email=source@invalid.example", *args, cwd=cwd)


def put_gitmodules(source: Path, text: str | bytes) -> None:
    """`text` as the source's `.gitmodules`, staged: BYTES, so it is LF on
    every platform, as a hand edit would leave it."""
    (source / GITMODULES).write_bytes(
        text if isinstance(text, bytes) else text.encode())
    git("add", "--", GITMODULES, cwd=source)


def link(source: Path) -> None:
    """A gitlink at GITLINK, staged straight into the index, as `git add` of
    an embedded clone records one; no checkout of it is needed. It names
    `main`'s commit, which an orphan branch's first commit has no HEAD to
    give."""
    head = git("rev-parse", "main", cwd=source).stdout.strip()
    git("update-index", "--add", "--cacheinfo", f"160000,{head},{GITLINK}",
        cwd=source)


def named(verb: str = "(adds|removes|changes)") -> str:
    """How `_exported_gitlink` names a commit's change to the gitlink, as a
    pattern: `verb` is what that commit does to it."""
    return rf"commit [0-9a-f]{{12}} {verb} `vendor/b`"


def exported_in_a_clone(source: Path,
                        base: Path) -> subprocess.CompletedProcess:
    """`git fast-export --all` in a clone of `source`, as `git filter-repo`
    runs it in the extraction's clone: the run whose failure the scan
    foretells. It needs git alone, so it runs where `git filter-repo` is
    not installed; bytes, because it exports the source's own content."""
    clone = base / "export-clone"
    git("clone", "-q", "--", str(source), str(clone), cwd=base)
    return subprocess.run(["git", "fast-export", "--all"], cwd=clone,
                          capture_output=True, check=False)


def planned(source: Path, base: Path, answers: dict) -> Path:
    """`plan` for `source` into `base/plan/` (project Northwind), each entry
    `answers` names given its leg: an entry `plan` asks about is resolved,
    and any other has its `leg:` set."""
    plan = base / "plan" / "adoption-plan.yaml"
    plan.parent.mkdir()
    written = write_plan(source, plan)
    assert written.returncode == 0, written.stderr + written.stdout
    text = plan.read_bytes().decode()
    for path, leg in answers.items():
        entry = re.search(rf"  - path: {re.escape(path)}\n    leg: (\S+)\n",
                          text)
        assert entry, f"no entry {path} in the plan"
        if entry[1] == "null":
            resolve(plan, path, leg)
            text = plan.read_bytes().decode()
        else:
            text = text.replace(entry[0],
                                f"  - path: {path}\n    leg: {leg}\n", 1)
    plan.write_bytes(text.encode())
    return plan


def findings(plan: Path) -> list[tuple[str, str]]:
    """`check`'s findings on `plan`, as `(code, detail)`; its exit is 1 when
    there is one and 0 when there is none."""
    result = run_script(ADOPT, "check", "--plan", str(plan))
    found = [tuple(line.split(" ", 1)[1].split(": ", 1))
             for line in result.stderr.splitlines()
             if line.startswith("FINDING ")]
    assert result.returncode == (1 if found else 0), result.stderr
    return found


def in_the_history(adopter, verb: str = "removes") -> re.Pattern:
    """How the finding ends for a gitlink only the history holds: the
    commit `git log` meets first, which `verb`s it."""
    return re.compile(re.escape(adopter.FAILS_IN_THE_HISTORY).replace(
        re.escape("{}"), named(verb)) + "$")


def refused_before_any_leg(adopter, monkeypatch: pytest.MonkeyPatch,
                           plan: Path, base: Path):
    """`execute --yes` on `plan`, in this process, its probe for `git
    filter-repo` stubbed, because the refusal under test comes before the
    tool would be used. The refusal must be `check`'s findings, raised by
    `_refuse_what_check_finds` before `_create_leg_remotes`, so the
    directory the legs go in is never made; it is returned."""
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)
    found = findings(plan)
    remotes = base / "remotes"
    args = Namespace(plan=str(plan), source=None, local_remote_dir=remotes,
                     allow_empty_leg=[], yes=True, work_dir=base / "work")
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(args)
    refusal = caught.value
    assert refusal.detail.splitlines()[1:] == [
        f"  FINDING {code}: {detail}" for code, detail in found]
    assert "no leg repository was created" in refusal.remediation
    assert not remotes.exists()
    return refusal


#: A file the shape's pin names, which `a_hook_that_unstages` takes out of
#: the split commit in the tests that need a verification to fail.
PINNED_COPY = "scripts/validate-pins.py"


def a_hook_that_unstages(hooks: Path, path: str = PINNED_COPY) -> Path:
    """`hooks`, holding a `pre-commit` hook that takes `path` out of the
    index before every commit, and nothing else: a commit without `path` is
    left as it is (`--ignore-unmatch`). Pointed at by `core.hooksPath`, it
    leaves `execute`'s split commit without a file the shape's pin names, so
    the verification fails, after both legs are pushed. The plan answer that
    stood for that failure until #524, the source's own
    `contracts/shape-pin.yaml` kept in the root, is refused before any leg
    now. LF, because `sh` reads it on every platform."""
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "pre-commit"
    with hook.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("#!/bin/sh\n"
                     f"exec git rm -q --cached --ignore-unmatch -- {path}\n")
    hook.chmod(0o755)
    return hooks


# --- the `gh` guard (#296) ---------------------------------------------------
#
# NO TEST REACHES THE OPERATOR'S `gh`, and the doctor's `machine` row is still
# tested. 149 tests in four files used to run whatever `gh` was on PATH -- the
# doctor's `machine` row runs `setup-project.py --preflight`, which asks `gh
# --version`, `gh auth status` and, logged in, `gh api user`, and the
# installed command's `--install` asks `gh auth status` -- and the module
# docstring's promise above was a sentence nothing held to. `tests/gh_guard.py`
# says what the guard answers and why it answers the two probes instead of
# refusing them; this block puts it in front of every child and fails a test
# whose calls it refused.
#
# ONE SCRIPT, TWO LAUNCHERS. `gh` is a POSIX `#!/bin/sh` that `exec`s this
# interpreter on the script; `gh.cmd` does the same for Windows, where a
# shebang means nothing. WHAT REACHES THE GUARD ON WINDOWS IS LESS, and the
# code under test decides it, not this block: every tool here starts `gh` as
# a bare `["gh", ...]` argv, and CreateProcess looks that up as `gh.exe` alone
# -- it does not read PATHEXT -- so on Windows every such call bypasses the
# guard. A doctor run there still asks a real `gh.exe` where one is
# installed: two calls on the runner, which holds no login, and three on a
# machine that is logged in, whose preflight goes on to `gh api user`. Where
# none is installed those calls cannot start, yet `shutil.which("gh")`, which
# does read PATHEXT, finds `gh.cmd` -- so during a test the preflight there
# reports `[ok] gh (unknown version)` and `[!!] gh is not authenticated`
# rather than `gh is not installed`. That same lookup is how
# `tests/test_gh_guard.py` reaches the launcher on Windows. The guard can
# never fail a Windows test spuriously: only a call made through a
# PATHEXT-aware lookup can reach it at all.
#
# NO PRODUCT SEAM. No flag or variable in the doctor, `setup-project.py` or
# `openRepoShape` leaves the row out: PATH alone does it, so no CLI surface
# and no line of `docs/cli.md` moved for a test's sake.
#
# THE SCRIPT IS IMPORTED HERE TOO: the probe table, the log format and the
# decision the teardown check makes are the ones the guard itself uses.
from gh_guard import LOG_NAME as GH_GUARD_LOG  # noqa: E402
from gh_guard import failure as gh_guard_failure  # noqa: E402

GH_GUARD_SCRIPT = Path(__file__).resolve().with_name("gh_guard.py")


def install_gh_guard(directory: Path) -> Path:
    """`tests/gh_guard.py` and its two launchers in `directory`, and an empty
    log beside them; returns the log.

    A COPY of the script, so that the log it writes beside itself lands in
    `directory` and never in this checkout. The launchers name this
    interpreter and that copy by absolute path, quoted for their own shell;
    they are written as BYTES because `Path.write_text` has no `newline=`
    before 3.10, and `gh.cmd` keeps cmd.exe's CRLF.
    """
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / GH_GUARD_SCRIPT.name
    shutil.copyfile(GH_GUARD_SCRIPT, script)
    posix = directory / "gh"
    posix.write_bytes(
        f"#!/bin/sh\nexec {shlex.quote(sys.executable)} "
        f"{shlex.quote(str(script))} \"$@\"\n".encode("utf-8"))
    posix.chmod(0o755)
    # `exit /b %ERRORLEVEL%` hands the script's status back as the batch
    # file's own, so 0, 1 and 97 survive the trip through cmd.exe.
    (directory / "gh.cmd").write_bytes(
        f"@echo off\r\n\"{sys.executable}\" \"{script}\" %*\r\n"
        "exit /b %ERRORLEVEL%\r\n".encode("utf-8"))
    log = directory / GH_GUARD_LOG
    log.write_bytes(b"")
    return log


class GhGuard:
    """The session's guard: its directory, its log, and how much of the log
    has been read.

    `take` is the ONE way a line is marked read. `pytest_runtest_teardown`
    below takes once a test's whole teardown is over -- its own fixtures and
    every module, class or session fixture that teardown finalized -- so a
    line counts against the test whose setup, call or teardown wrote it, a
    scoped fixture's finalizer and a session fixture its setup started
    included. ONE CALL IT CANNOT PLACE: a child a test left running that runs
    `gh` after that test's teardown lands on the next test whose teardown
    reads the log, and the message still names the test and phase that made
    it. A test that runs the guard on purpose (`tests/test_gh_guard.py`) takes
    its own lines and asserts on them, which is what keeps them out of the
    check: no marker is needed for that, and none is added.
    """

    def __init__(self, directory: Path, log: Path) -> None:
        self.directory = directory
        self.log = log
        self.read = 0

    def take(self) -> list:
        """Every line logged since the last `take`, now marked read."""
        lines = self.log.read_text(encoding="utf-8").splitlines()
        taken, self.read = lines[self.read:], len(lines)
        return taken


#: Where `gh_guard` leaves itself for `pytest_runtest_teardown` to read.
GH_GUARD_KEY = pytest.StashKey()


@pytest.fixture(scope="session", autouse=True)
def gh_guard(tmp_path_factory, pytestconfig):
    """The guard, FIRST on `os.environ["PATH"]` for the whole session.

    `os.environ`, so every child inherits it however it is started:
    `run_script`, `run_cmd` in `tests/test_openreposhape_command.py`, or a
    bare `subprocess.run`. A test that installs its own `gh` stub puts its
    directory ahead of this one and keeps winning, as it always did. Session
    scope and autouse, so it is set up before any other session fixture --
    `scaffolded` included -- and torn down after all of them, inside the
    last test's teardown, where `pytest_runtest_teardown` reads whatever
    they logged; PATH is put back as it was.
    """
    directory = tmp_path_factory.mktemp("gh-guard")
    guard = GhGuard(directory, install_gh_guard(directory))
    pytestconfig.stash[GH_GUARD_KEY] = guard
    before = os.environ.get("PATH")
    os.environ["PATH"] = str(directory) + (os.pathsep + before
                                           if before else "")
    try:
        yield guard
    finally:
        if before is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = before


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item, nextitem):
    """Fail a test, at its teardown, when the guard refused one of its calls,
    naming each call and the phase that made it; the two probes pass.

    A HOOK WRAPPER, NOT AN AUTOUSE FIXTURE (#296, the review of b111b51). A
    function fixture is torn down BEFORE the module, class and session
    fixtures a test's teardown finalizes, so a call one of those made in its
    own finalizer was charged to the NEXT test, and under `-x` the run
    stopped on an innocent one. Everything after `yield` here runs once the
    whole teardown -- every finalizer it triggered -- is over, so the call is
    charged to the test whose teardown made it; and the LAST test's teardown
    finalizes every session fixture, the guard's own included, so nothing a
    session fixture logs goes unread. A teardown that raised on its own
    account reports that instead, and its lines are read by the next one.
    """
    result = yield
    guard = item.config.stash.get(GH_GUARD_KEY, None)
    found = gh_guard_failure(guard.take()) if guard is not None else None
    if found:
        pytest.fail(found, pytrace=False)
    return result


def assert_refuses_for_want_of_a_terminal(stderr: str) -> None:
    """What a run with no terminal prints where it would have asked (#476),
    held to ONE reading by every test that reaches it.

    The refusal is read by an AI assistant whose shell has no terminal and
    whom AGENTS.md forbids `--yes`, so it must open with the exit that keeps
    the human in charge, and `--yes` may appear only as the person's own
    answer. That exit is the same command in the person's own terminal,
    which asks there even piped (#492); only Windows, with no controlling
    terminal to ask on, still needs the downloaded file. It is
    `setup-project.py`'s one wording: `setup.sh` and the `openRepoShape`
    command pass it through, so their tests hold the same text rather than
    each spelling it again.
    """
    assert "no terminal to confirm on" in stderr, stderr
    assert not re.search(r"re-?run\s+with\s+--yes|if you mean it", stderr,
                         re.IGNORECASE), (
        f"the refusal invites a re-run with --yes, the flag an assistant "
        f"may not pass: {stderr!r}")
    assert ("this same command in a terminal of their own, and it asks them "
            "there" in stderr), stderr
    assert "on Windows, from the downloaded file" in stderr, stderr
    [yes_sentence] = [sentence for sentence in re.split(r"(?<=\.)\s+", stderr)
                      if "--yes" in sentence]
    assert "never an assistant's" in yes_sentence, yes_sentence
    assert stderr.index("terminal of their own") < stderr.index("--yes"), (
        f"the exit that keeps the human in charge comes first: {stderr!r}")


# --- a clone path that is already taken (#498) -------------------------------
#
# ONE READING, TWO ENTRY POINTS. `tests/test_setup_sh.py` and
# `tests/test_setup_project_py.py` each hand their own runner (`run_setup`,
# `run_entry`) to the two helpers below, so the same runs are asserted once
# whichever name a person typed. Every run here passes `--local-remote-dir`,
# which is what those files' `test_no_test_here_depends_on_gh_being_
# authenticated` looks for in each call it can see; it cannot see these, so
# they keep it themselves.

#: What can stand where the project would be cloned, as
#: `assert_a_taken_clone_path_is_refused` makes each one.
TAKEN_CLONE_PATHS = ("empty directory", "file", "directory")

#: The refusal's ways out: deleting is offered outright only for what holds
#: nothing of anybody's, and for what only LOOKS like a rehearsal's clone on
#: the person's own condition (#498, review round 1).
DISCARD_IT = "Move or delete it, then run this again."
DISCARD_IT_IF_UNUSED = ("Move it, or delete it if nothing in it is yours, then "
                        "run this again.")
KEEP_IT = "Move it, or choose another --into, then run this again."


def refused_in_step_three(result, clone: str) -> str:
    """`result` refused in step (3), before the naming check, the plan or
    the scaffold, naming `clone` and saying nothing was created; returns the
    refusal's text after that first sentence."""
    head = (f"REFUSED: {clone} already exists, and that is where this project "
            "would be cloned, so the run stops here and nothing was created.")
    assert result.returncode == 2, result.stderr + result.stdout
    assert head in result.stderr, result.stderr
    assert "(3) project" in result.stdout, result.stdout
    for later in ("(4) naming policy", "(5) the plan", "(6) scaffold"):
        assert later not in result.stdout, f"the run reached {later}"
    return result.stderr.split(head, 1)[1].strip()


def assert_a_rehearsals_clone_stops_the_real_run(run, tmp_path: Path) -> None:
    """README's own order, in one folder: rehearse with `--local-remote-dir
    ./rehearsal`, then run for real (a second `--local-remote-dir` stands in
    for GitHub). The rehearsal names its clone path in the plan and leaves
    `./Sample` behind; the real run refuses in step (3), says that clone
    LOOKS like the rehearsal's, offers deleting it only if nothing in it is
    the person's, and creates nothing. On main it created all three
    repositories and only then refused, in step (7)."""
    here = tmp_path / "here"
    clone = os.path.abspath(str(here / "Sample"))
    rehearsal = run("--project", "Sample", "--yes", "--org", "demoorg",
                    "--local-remote-dir", str(here / "rehearsal"),
                    "--into", str(here))
    assert rehearsal.returncode == 0, rehearsal.stderr + rehearsal.stdout
    out = rehearsal.stdout
    assert (out.index("--dry-run: nothing was created.")
            < out.index(f"\nclone into   {clone}\n")
            < out.index("(6) scaffold")), out
    real = run("--project", "Sample", "--yes", "--org", "demoorg",
               "--local-remote-dir", str(here / "real"), "--into", str(here))
    rest = refused_in_step_three(real, clone)
    assert rest.startswith("It looks like the clone a rehearsal left behind: "
                           "its `origin` is "), rest
    assert rest.endswith("a repository on this disk, as `--local-remote-dir` "
                         "makes one. " + DISCARD_IT_IF_UNUSED), rest
    assert not (here / "real").exists(), "the real run created repositories"
    assert (here / "Sample" / "project.yaml").is_file()


def assert_a_taken_clone_path_is_refused(run, tmp_path: Path,
                                         kind: str) -> None:
    """Anything at `<into>/<Project>` - one of `TAKEN_CLONE_PATHS` - is
    refused in step (3) of a run told `--yes`, with what is there said where
    the tool can tell, and left exactly as it was. An EMPTY directory too,
    though `git clone` would take one: #498's option 1. On main each of
    these created all three repositories first."""
    work = tmp_path / "work"
    taken = work / "Sample"
    if kind == "file":
        work.mkdir()
        taken.write_bytes(b"not a project\n")
        said, way_out = "", KEEP_IT
    elif kind == "directory":
        taken.mkdir(parents=True)
        (taken / "notes.txt").write_bytes(b"somebody's\n")
        said, way_out = "It is a directory that is not a git clone. ", KEEP_IT
    else:
        taken.mkdir(parents=True)
        said, way_out = "It is an empty directory. ", DISCARD_IT
    before = sorted(p.name for p in taken.iterdir()) if taken.is_dir() else (
        taken.read_bytes())
    result = run("--project", "Sample", "--yes", "--org", "demoorg",
                 "--local-remote-dir", str(tmp_path / "remotes"),
                 "--into", str(work))
    rest = refused_in_step_three(result, os.path.abspath(str(taken)))
    assert rest == said + way_out, rest
    assert not (tmp_path / "remotes").exists()
    after = sorted(p.name for p in taken.iterdir()) if taken.is_dir() else (
        taken.read_bytes())
    assert after == before, f"{taken} was changed by a run that refused"


#: THE PERSON'S OWN TERMINAL, IN A TEST (#492). The one-liner reads its yes
#: from the CONTROLLING terminal when its stdin is the pipe the script came
#: down, so a test that says it asks has to give the run one: a
#: pseudo-terminal, made the controlling terminal of a session of the run's
#: own. `subprocess` hands a child file descriptors and nothing more, so
#: `_CONTROLLING`, run first by this interpreter, claims the terminal on its
#: stdin (`TIOCSCTTY`) and then becomes the command. POSIX only: Windows has
#: no controlling terminal to give, and its way in is the downloaded file.
PTY_SKIP = pytest.mark.skipif(
    os.name == "nt",
    reason="a controlling terminal is POSIX; on Windows the way in is the "
           "downloaded setup-project.py, and there is no /dev/tty to ask on")

_CONTROLLING = ("import fcntl, os, sys, termios; "
                "fcntl.ioctl(0, termios.TIOCSCTTY, 0); "
                "os.execvp(sys.argv[1], sys.argv[1:])")

#: The same terminal, the command run in a BACKGROUND process group of it: a
#: piped run, `cat setup.sh | timeout N bash -s -- ...`, typed in a shell
#: (GNU `timeout` puts its command in a group of its own), or any runner that
#: backgrounds a job sharing the terminal. `_CONTROLLING_IN_THE_BACKGROUND`
#: stays the session's leader and its foreground group, and the command is a
#: child in a group of its own, so a read of the terminal from it stops on
#: SIGTTIN. A stopped command is killed and shows as a status of 128 + the
#: signal, so a run that waits where it should have refused fails at once and
#: leaves nothing stopped behind it.
_CONTROLLING_IN_THE_BACKGROUND = """
import fcntl, os, signal, sys, termios
fcntl.ioctl(0, termios.TIOCSCTTY, 0)
child = os.fork()
if child == 0:
    os.setpgid(0, 0)
    os.execvp(sys.argv[1], sys.argv[1:])
status = os.waitpid(child, os.WUNTRACED)[1]
if os.WIFSTOPPED(status):
    os.killpg(child, signal.SIGKILL)
    sys.exit(128 + os.WSTOPSIG(status))
sys.exit(os.WEXITSTATUS(status) if os.WIFEXITED(status)
         else 128 + os.WTERMSIG(status))
"""


def run_in_a_terminal(argv: list, *, cwd: Path, env: dict, answers=(),
                      prompt="Type yes to continue:",
                      timeout: float = 180, raw: bool = False,
                      background: bool = False) -> tuple:
    """`argv` run as a person runs it in their own terminal: a
    pseudo-terminal is its controlling terminal and its stdin, stdout and
    stderr, so a pipe inside `argv` (`cat setup.sh | bash -s -- ...`) is the
    only thing that is not the terminal. Each of `answers` is typed once the
    screen shows its prompt after the answer before it - `prompt` is one
    prompt for every answer, or one per answer, in order - `"EOF"` as Ctrl-D,
    and nothing is typed anywhere else.

    Returns `(exit status, the screen, how many answers were typed)`, with
    the terminal's `\\r\\n` read as `\\n`. A run still going after `timeout`
    seconds is killed and FAILS the test with its screen: a run waiting on a
    prompt nobody answers is the defect this exists to show. Reading stops
    once the run has exited and its output is drained, so a detached child
    still holding the terminal cannot keep the test waiting.

    `raw` puts the terminal in RAW mode before the run starts, as an
    assistant's full-screen interface leaves the pane it owns: nothing is
    echoed and the Enter key sends a carriage return, so a read for the end
    of a line never ends. `background` runs the command in a background
    process group of the terminal, not its foreground one.
    """
    master, slave = os.openpty()
    if raw:
        import tty  # POSIX only, like the pty itself
        tty.setraw(slave)
    try:
        proc = subprocess.Popen([sys.executable, "-c",
                                 _CONTROLLING_IN_THE_BACKGROUND if background
                                 else _CONTROLLING, *argv],
                                cwd=str(cwd), env=env, stdin=slave,
                                stdout=slave, stderr=slave,
                                start_new_session=True)
    finally:
        os.close(slave)
    prompts = ([prompt] * len(answers) if isinstance(prompt, str)
               else list(prompt))
    screen, typed, since = b"", 0, 0
    deadline = time.monotonic() + timeout
    try:
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise AssertionError(
                    f"still running after {timeout}s, waiting on its "
                    "terminal:\n" + screen.decode("utf-8", "replace"))
            if not select.select([master], [], [], min(left, 1.0))[0]:
                if proc.poll() is not None:
                    break
                continue
            try:
                chunk = os.read(master, 4096)
            except OSError:  # EIO: the last holder of the terminal is gone
                break
            if not chunk:
                break
            screen += chunk
            if typed < len(answers) and \
                    prompts[typed].encode("utf-8") in screen[since:]:
                answer = answers[typed]
                os.write(master, b"\x04" if answer == "EOF"
                         else answer.encode("utf-8"))
                typed, since = typed + 1, len(screen)
        status = proc.wait(timeout=max(deadline - time.monotonic(), 1.0))
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
        os.close(master)
    return (status, screen.decode("utf-8", "replace").replace("\r\n", "\n"),
            typed)


def spelled(path) -> str:
    """`path` as `adopt-project.py` names one in a finding, a refusal or the
    late-failure notice (#212): between backticks, with a backslash or a
    backtick escaped. A path a test builds is otherwise printable, which
    `_spelled` writes as it is; a Windows path keeps its separators, each
    one escaped."""
    return "`" + str(path).replace("\\", "\\\\").replace("`", "\\`") + "`"
