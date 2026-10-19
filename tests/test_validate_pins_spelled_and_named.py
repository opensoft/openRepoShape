# SPDX-License-Identifier: Apache-2.0
"""`validate-pins.py` and `repo_shape.py` spell `--root` and gh's stderr,
name what stands where a pin, the shape pin, a neutral-product pin, the
manifest or a shape copy should be, and refuse by name a leg's `.git`
gitfile that this user cannot open (#919).

The issue's four parts, from lane 3's triage of #459 at the v1.1.1 release
commit `5017830`:

  * U176. `find_repo_root` refused `not-a-git-repo` naming `--root` raw, so
    an ESC in it reached the terminal, from every tool that asks it. The
    path is `shown_path`'s spelling now.
  * U177. `tree_digest_from_gh` put gh's stderr into `gh-unreadable`'s
    detail raw, and `validate-pins.py` prints that detail in its `skip`
    line: an ESC was the control it is, and each line break began a line.
    gh's text is `spelled`, as ONE line, as `git_out` spells git's (#610),
    and the pin's repository in the same detail is `shown_path`'s.
  * U178. A directory, a FIFO, a symlink to nothing or a symlink loop in a
    pin's place was refused under "does not exist" and the lockstep remedy,
    and in a shape copy's place was "pinned but absent". Each site names
    what is there, with a remedy that fits it. The code and the line's form
    stay, and a file that is not there keeps its words byte for byte.
  * U179. A leg's `.git` gitfile at mode 000 stats, so the leg read as a
    checkout and the run ended in `pin-commit-unresolvable` under THE
    LOCKSTEP RULE. It is `pin-submodule-unreadable`, by name, as #827
    refuses a leg checkout this user cannot search.

THE HARNESS is `tests/test_validate_pins_named_and_spelled.py`'s: the gate
runs as the copy a real scaffold wrote (`validate`), and in-process as that
copy loaded as a module (`validator`). A stub `gh` is a `#!` script, so its
row skips on Windows; a FIFO needs `os.mkfifo`, and a symlink one Windows
makes only with a privilege, so those rows skip there too; a mode row skips
on Windows and as root. Every in-process row runs everywhere.

Every control character here is built with `chr`, never typed, and so is
the backslash of each escape the gate prints.
"""

from __future__ import annotations

import errno
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP, run_script
from test_validate_pins_named_and_spelled import (
    AGAIN, CHECKOUT_READS, COMMIT, OTHER, PERMISSION, READS, SHAPE_PIN,
    UNPRINTABLE, declare_openxdox, failing, os_error, refusal_of_the_run,
)
from test_validate_pins_unreadable_workflow import CANNOT_RUN_AS_ROOT, validate
from test_validate_pins_unreadable_workflows_dir import mode_of, tree_bytes
# A fixture is used by being named in this module's namespace, which is what
# this import is for: the project's own `validate-pins.py`, loaded as a module.
from test_validate_pins_without_git import validator  # noqa: F401

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import REMEDIATION  # noqa: E402

#: An ESC, a carriage return, a line feed, and the backslash an escape
#: starts with.
ESC, CR, LF, BS = chr(27), chr(13), chr(10), chr(92)

#: The neutral-product pin `declare_openxdox` declares.
NEUTRAL_PIN = "contracts/openxdox-pin.yaml"


# --- U176: `--root` outside any repository -----------------------------------

def outside_any_repository(tmp_path: Path) -> Path:
    """`tmp_path`, with no `.git` at it or above it, so `find_repo_root`
    walks to the top and refuses; a skip on a machine whose temporary
    directory is inside a repository."""
    for here in (tmp_path, *tmp_path.resolve().parents):
        if (here / ".git").exists():
            pytest.skip(f"{here} holds a .git, so nothing below it is outside "
                        "a repository")
    return tmp_path


def refused_outside(project: Path, where: Path) -> subprocess.CompletedProcess:
    """The project's own gate, `--root` at `where`."""
    return run_script(project / "scripts" / "validate-pins.py", "--root",
                      str(where), cwd=project)


def test_a_root_outside_any_repository_is_named_spelled(project, tmp_path):
    """U176, THE ISSUE'S PROBE: `--root '<dir>/x<ESC>[31mRED'` outside any
    repository. The path is named as `shown_path` names one that is not
    printable, `repr`'d, so the ESC is its escape and no control reaches the
    terminal. It is still `not-a-git-repo`, exit 2, under the lockstep
    remedy the gate gives a refusal that names none of its own."""
    where = outside_any_repository(tmp_path) / ("x" + ESC + "[31mRED")
    result = refused_outside(project, where)
    line = f"REFUSED not-a-git-repo: no .git found at or above {str(where)!r}"
    assert result.stderr == f"{line}\n{REMEDIATION}\n", result.stderr
    assert result.stderr.splitlines()[0].endswith(
        "x" + BS + "x1b[31mRED'"), result.stderr
    assert ESC not in result.stderr, result.stderr
    assert result.returncode == 2, result.stdout + result.stderr


def test_a_printable_root_outside_any_repository_keeps_its_words(project,
                                                                 tmp_path):
    """The control: a printable `--root` is named byte for byte as it
    always was."""
    where = outside_any_repository(tmp_path) / "plain"
    result = refused_outside(project, where)
    assert result.stderr == (
        f"REFUSED not-a-git-repo: no .git found at or above {where}\n"
        f"{REMEDIATION}\n"), result.stderr
    assert result.returncode == 2, result.stdout + result.stderr


@pytest.mark.parametrize("name", [
    param for param in UNPRINTABLE if param.id != "undecodable-byte"])
def test_every_tool_that_asks_for_the_root_names_it_spelled(validator,
                                                            tmp_path, name):
    """The library's own refusal, for every tool that calls `find_repo_root`:
    a newline, a bidi control, a C1 control and an ESC each print as `repr`
    spells them, and none raw. (A byte that is not UTF-8 is not a name every
    platform's paths can hold.)"""
    where = outside_any_repository(tmp_path) / name
    with pytest.raises(validator.Refusal) as caught:
        validator.find_repo_root(where)
    assert caught.value.code == "not-a-git-repo"
    assert caught.value.detail == (
        f"no .git found at or above {str(where)!r}")
    assert name not in caught.value.detail, caught.value.detail


# --- U177: gh's stderr in the `skip` line ------------------------------------

def declared_with_a_pin(project: Path) -> None:
    """`project.yaml` declares `openXdox`, and its pin's fields are well
    formed, so the gate asks `gh api` for the digest: no `--pin-source`, no
    variable (`run_script` blanks every one) and no `../openXdox`."""
    declare_openxdox(project)
    (project / NEUTRAL_PIN).write_bytes((
        "kind: pinned_contract_manifest\nrevision_kind: commit\n"
        f"commit: {COMMIT}\nsource_repository: testorg/openXdox\n"
        f"digests:\n  tree_sha256: {'a' * 64}\n"
        "digest_definition: sorted-ls-tree-r-v1\n").encode("utf-8"))


def gh_saying(where: Path, said: str, status: int) -> dict:
    """The environment of a run whose `gh`, first on PATH, prints `said` on
    stderr and exits `status`. The script is written as bytes, so its ESC
    and CR are the bytes themselves."""
    bin_dir = where / "gh-bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_bytes(b"#!/bin/sh\nprintf '%s' '" + said.encode("utf-8")
                   + b"' >&2\nexit " + str(status).encode("ascii") + b"\n")
    gh.chmod(0o755)
    return {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}


@WINDOWS_SKIP
def test_gh_s_stderr_in_the_skip_line_is_spelled_on_one_line(project,
                                                             tmp_path):
    """U177: a `gh` that exits 1 printing an ESC, a CR and two line feeds.
    The skip is ONE line, gh's text spelled: the ESC and each break are
    escapes, the CR's too, since gh's stderr is read in text mode and the
    CR is a line break by then. No control reaches stdout, and the run
    still passes: a skip is never a finding."""
    declared_with_a_pin(project)
    env = gh_saying(tmp_path, "one" + ESC + "[31mred" + CR + "two" + LF
                    + "three" + LF, 1)
    result = run_script(project / "scripts" / "validate-pins.py",
                        cwd=project, env=env)
    skips = [line for line in result.stdout.split(LF)
             if line.startswith("  skip ")]
    assert skips == [
        f"  skip openXdox: pin commit {COMMIT[:12]} digest NOT rechecked — "
        "no local checkout (gh-unreadable: `gh api` could not read "
        f"testorg/openXdox @ {COMMIT}: one{BS}x1b[31mred{BS}ntwo{BS}nthree)."
        " A --pin-source, SHAPE_PIN_SOURCE_OPENXDOX, or a checkout at "
        "../openXdox beside this assembly root would verify it offline."], \
        result.stdout
    assert ESC not in result.stdout, result.stdout
    assert CR not in result.stdout, result.stdout
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.endswith(LF + "pins ok" + LF), result.stdout


def gh_answering(monkeypatch, status: int, stderr: str) -> None:
    """`subprocess.run` answering as a `gh` that exits `status` and prints
    `stderr`, in-process, so a row runs on every platform."""
    def gh(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, status, "", stderr)

    monkeypatch.setattr(subprocess, "run", gh)


#: gh's stderr, and how `gh-unreadable` names it.
GH_SAID = [
    pytest.param("HTTP 404: Not Found" + LF, "HTTP 404: Not Found",
                 id="one-printable-line"),
    pytest.param("To get started with GitHub CLI, please run:  gh auth login"
                 + LF + "Alternatively, populate the GH_TOKEN variable." + LF,
                 "To get started with GitHub CLI, please run:  gh auth login"
                 + BS + "nAlternatively, populate the GH_TOKEN variable.",
                 id="the-not-logged-in-help"),
    pytest.param("no" + ESC + "[2Jt" + chr(0x85) + "x" + chr(0x202e) + "y",
                 "no" + BS + "x1b[2Jt" + BS + "x85x" + BS + "u202ey",
                 id="controls"),
    pytest.param("caf" + chr(0xe9) + " " + chr(0x65e5) + chr(0x672c),
                 "caf" + chr(0xe9) + " " + chr(0x65e5) + chr(0x672c),
                 id="utf-8-unchanged"),
]


@pytest.mark.parametrize("said, named", GH_SAID)
def test_gh_unreadable_spells_what_gh_printed_as_one_line(
        validator, monkeypatch, said, named):
    """The detail itself, on every platform: what gh printed is `spelled`,
    as `git_out` spells git's stderr (#610), so a control or a bidi control
    is its escape and a line break between two lines of gh's help is one
    too, while printable text, UTF-8 included, is as it was."""
    gh_answering(monkeypatch, 1, said)
    with pytest.raises(validator.Refusal) as caught:
        validator.tree_digest_from_gh("testorg/openXdox", COMMIT)
    assert caught.value.code == "gh-unreadable"
    assert caught.value.detail == (
        f"`gh api` could not read testorg/openXdox @ {COMMIT}: {named}")


@pytest.mark.parametrize("repository", [
    param for param in UNPRINTABLE if param.id != "undecodable-byte"])
def test_gh_unreadable_names_the_repository_spelled(validator, monkeypatch,
                                                    repository):
    """The pin's `source_repository`, which the skip line also names, is
    `shown_path`'s in the same detail: `repr`'d where a character in it is
    not printable, as `git_out` names its directory."""
    gh_answering(monkeypatch, 1, "HTTP 404: Not Found" + LF)
    with pytest.raises(validator.Refusal) as caught:
        validator.tree_digest_from_gh(repository, COMMIT)
    assert caught.value.detail == (
        f"`gh api` could not read {repository!r} @ {COMMIT}: "
        "HTTP 404: Not Found")


# --- U178: what stands where a file should be --------------------------------

def made_directory(path: Path) -> None:
    path.mkdir()


def made_fifo(path: Path) -> None:
    os.mkfifo(path)


def made_link_to_nothing(path: Path) -> None:
    os.symlink("nothing-here-w919", path)


def made_loop(path: Path) -> None:
    os.symlink(path.name, path)


def made_link_to_a_directory(path: Path) -> None:
    (path.parent / "directory-w919").mkdir()
    os.symlink("directory-w919", path)


POSIX_NODES = pytest.mark.skipif(
    os.name == "nt",
    reason="a FIFO needs os.mkfifo, and Windows makes a symlink only with a "
           "privilege")

#: What can stand in a file's place, and the words after the file's name.
NOT_FILES = [
    pytest.param(made_directory, "is a directory, not a file",
                 id="directory"),
    pytest.param(made_fifo, "is a FIFO, not a file", id="fifo",
                 marks=POSIX_NODES),
    pytest.param(made_link_to_nothing, "is a symlink to nothing, not a file",
                 id="symlink-to-nothing", marks=POSIX_NODES),
    pytest.param(made_loop, "is a symlink loop, not a file",
                 id="symlink-loop", marks=POSIX_NODES),
    pytest.param(made_link_to_a_directory,
                 "is a symlink to a directory, not a file",
                 id="symlink-to-a-directory", marks=POSIX_NODES),
]

#: Each site that REFUSES, as `(the file, the code, what its line says before
#: what stands there)`: the words before "does not exist", which stay.
REFUSALS = [
    pytest.param("contracts/spec-pin.yaml", "pin-missing",
                 "leg 'spec' declares testorg/Atlas-spec at 'spec' but "
                 "contracts/spec-pin.yaml", id="leg-pin"),
    pytest.param(SHAPE_PIN, "shape-pin-missing", SHAPE_PIN, id="shape-pin"),
    pytest.param(NEUTRAL_PIN, "neutral-pin-missing",
                 f"project.yaml declares a pin on 'openXdox' but "
                 f"{NEUTRAL_PIN}", id="neutral-pin"),
    pytest.param("project.yaml", "manifest-missing", "project.yaml",
                 id="manifest"),
]

#: The remedy of each of those, where something that is not a file stands
#: in the file's place: no lockstep move puts it right.
NOT_A_FILE_REMEDY = (
    READS + "Something that is not a file stands in its place: move it "
    "aside, or take it away if nobody wants it, and restore the file from the "
    "project's history. " + AGAIN)

#: The line under a shape copy's finding, in the same case.
COPY_REMEDY = (
    "A shape file's place is taken by something that is not a file. Move it "
    "aside, or take it away if nobody wants it, and restore the copy from the "
    "project's history.")


def in_its_place(project: Path, relative: str, make) -> None:
    """`relative` taken away, and `make` putting what it makes at its name.
    For the neutral-product pin, `project.yaml` declares `openXdox` first,
    whose pin file is not there."""
    if relative == NEUTRAL_PIN:
        declare_openxdox(project)
    (project / relative).unlink(missing_ok=True)
    make(project / relative)


@pytest.mark.parametrize("make, what", NOT_FILES)
@pytest.mark.parametrize("relative, code, said", REFUSALS)
def test_what_stands_in_a_files_place_is_named_with_a_remedy_that_fits(
        project, relative, code, said, make, what):
    """U178, the refusals: each was "does not exist" under the lockstep
    remedy, which moves a pin and runs `git submodule update`, and neither
    takes a directory or a FIFO away. The code and the words before stay;
    what stands there is named, and the remedy says to move it aside and
    restore the file. The whole of stderr, exit 2, and nothing on stdout."""
    in_its_place(project, relative, make)
    result = validate(project)
    assert result.stderr == (
        f"REFUSED {code}: {said} {what}\n{NOT_A_FILE_REMEDY}\n"), \
        result.stderr
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == "", result.stdout


@pytest.mark.parametrize("make, what", NOT_FILES)
def test_what_stands_in_a_shape_copys_place_is_named(project, make, what):
    """U178, the finding: a shape copy so replaced was "pinned but absent".
    The code and `<pin>: <path> is pinned but` stay, what stands there is
    named, and a line under it says what to do, as `shape-copy-drift` has
    one. Still a finding the lockstep rule is not about: the count alone."""
    in_its_place(project, "Makefile", make)
    result = validate(project)
    assert result.stderr == (
        f"FINDING shape-copy-missing: {SHAPE_PIN}: Makefile is pinned but "
        f"{what}\n  {COPY_REMEDY}\n\n1 finding(s).\n"), result.stderr
    assert result.returncode == 1, result.stdout + result.stderr


#: A file that is not there, the whole of stderr, and the exit: the words
#: each site always had.
ABSENT = [
    pytest.param("contracts/spec-pin.yaml",
                 "REFUSED pin-missing: leg 'spec' declares testorg/Atlas-spec "
                 "at 'spec' but contracts/spec-pin.yaml does not exist\n"
                 f"{REMEDIATION}\n", 2, id="leg-pin"),
    pytest.param(SHAPE_PIN, f"REFUSED shape-pin-missing: {SHAPE_PIN} does not "
                 f"exist\n{REMEDIATION}\n", 2, id="shape-pin"),
    pytest.param(NEUTRAL_PIN,
                 "REFUSED neutral-pin-missing: project.yaml declares a pin on "
                 f"'openXdox' but {NEUTRAL_PIN} does not exist\n"
                 "Remediation: `scaffold-project.py --pin openXdox@<commit>` "
                 "writes that file. A declaration in project.yaml with no pin "
                 "file beside it is a claim with no referent — either restore "
                 "the file or remove the declaration.\n", 2, id="neutral-pin"),
    pytest.param("project.yaml",
                 "REFUSED manifest-missing: project.yaml does not exist, so "
                 "there is no declaration of which legs to check. A "
                 "one-repository project has no legs and does not run this "
                 f"validator.\n{REMEDIATION}\n", 2, id="manifest"),
    pytest.param("Makefile",
                 f"FINDING shape-copy-missing: {SHAPE_PIN}: Makefile is "
                 "pinned but absent\n\n1 finding(s).\n", 1, id="shape-copy"),
]


@pytest.mark.parametrize("relative, stderr, code", ABSENT)
def test_a_file_that_is_not_there_keeps_its_words_byte_for_byte(
        project, relative, stderr, code):
    """The control: nothing at the name is what each site always said, the
    lockstep remedy included where it was given. `shape-doctor.py` reads a
    copy's `is pinned but absent` to find a merged-away `shape/` copy."""
    in_its_place(project, relative, lambda _path: None)
    result = validate(project)
    assert result.stderr == stderr, result.stderr
    assert result.returncode == code, result.stdout + result.stderr


# --- U179: a leg's `.git` gitfile this user cannot open ----------------------

@CANNOT_RUN_AS_ROOT
def test_a_leg_gitfile_this_user_cannot_open_is_refused_by_name(project):
    """U179, RV827'S N6: `spec/.git`, the gitfile a recursive clone gives a
    leg, at mode 000. It stats, so the leg read as a checkout and the run
    ended in `pin-commit-unresolvable` under THE LOCKSTEP RULE. It is
    `pin-submodule-unreadable`, naming the gitfile, with the permission
    advice; nothing is written, and the mode is put back in a `finally`."""
    assert (project / "spec" / ".git").is_file(), \
        "fixture drift: a recursive clone's leg holds a gitfile"
    before = tree_bytes(project)
    with mode_of(project, "spec/.git", 0):
        result = validate(project)
    assert result.stderr == (
        "REFUSED pin-submodule-unreadable: spec/.git: cannot be read "
        f"(Permission denied)\n{CHECKOUT_READS}{PERMISSION}{AGAIN}\n"), \
        result.stderr
    assert result.returncode == 2, result.stdout + result.stderr
    assert tree_bytes(project) == before, "a validator writes nothing"


@pytest.mark.parametrize("failure, advice", [
    pytest.param(PermissionError(errno.EACCES, "Permission denied"),
                 PERMISSION, id="permission"),
    pytest.param(os_error(errno.EIO), OTHER, id="io-error"),
])
def test_a_leg_gitfile_whose_open_is_refused_is_refused_on_every_python(
        validator, project, monkeypatch, failure, advice):
    """The same gitfile in-process, so on every platform and as root: its
    open refused, each cause with its own advice."""
    failing(monkeypatch, "open", {".git": failure})
    refusal = refusal_of_the_run(validator, project)
    assert refusal.code == "pin-submodule-unreadable"
    assert refusal.detail == f"spec/.git: cannot be read ({failure.strerror})"
    assert refusal.remediation == CHECKOUT_READS + advice + AGAIN


def test_a_gitfile_gone_when_it_is_opened_is_an_uninitialized_leg(
        validator, project, monkeypatch):
    """Asked as `_is_a` asks a `stat`: an open that finds nothing at the
    name is the leg with no `.git`, `pin-submodule-uninitialized`, and not a
    file this user cannot read."""
    failing(monkeypatch, "open", {".git": os_error(errno.ENOENT)})
    refusal = refusal_of_the_run(validator, project)
    assert refusal.code == "pin-submodule-uninitialized"
    assert refusal.detail.startswith(
        "spec is not an initialized submodule checkout"), refusal.detail


@pytest.mark.parametrize("make", [
    pytest.param(made_directory, id="directory"),
    pytest.param(made_fifo, id="fifo", marks=POSIX_NODES),
])
def test_a_git_that_is_no_regular_file_is_not_opened(validator, tmp_path,
                                                     monkeypatch, make):
    """Only a gitfile is opened: a checkout's own `.git` directory is git's
    to read, and the open of a FIFO would wait for a writer. An open of
    either fails the row rather than hanging it."""
    dotgit = tmp_path / "leg" / ".git"
    dotgit.parent.mkdir()
    make(dotgit)
    failing(monkeypatch, "open", {".git": AssertionError("opened")})
    assert validator._gitfile_opens(dotgit) is True
