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

What #919 left, #968, from rv919's review of #952 at `8a7671b3`:

  * gh's stderr that is not UTF-8 ended the run in a `UnicodeDecodeError`
    traceback. It is read with `errors="replace"`, as `git_out` reads git's,
    and the JSON on stdout stays strict: a byte that is not UTF-8 there, or
    JSON that is not a tree listing, is `gh-response-unreadable`.
  * `gh-response-unreadable` and `gh-tree-truncated` name the repository
    as `gh-unreadable` does.
  * A leg's git directory this user cannot search, a `.git` directory or
    the one a gitfile names under `.git/modules/`, ended in
    `pin-commit-unresolvable` under THE LOCKSTEP RULE. It is
    `pin-submodule-unreadable`, by name.
  * `contracts` replaced by a file, a FIFO or a symlink that leads to no
    directory made every pin "does not exist" under THE LOCKSTEP RULE. The
    refusal names what stands there, with a remedy of its own.
  * rv919's surviving mutants r2 (a socket named as a FIFO) and r4 (an
    empty remedy where none was given) each fail a row now.

What #968 left, #1222, from RV1200's review of #1200 (its N2):

  * The `HEAD` of a leg's git directory at mode 000, under `.git/modules/`
    or in a `.git` directory, stats, so #968's `stat` passed it, and git,
    which could not read it, ended the run in `pin-commit-unresolvable`
    under THE LOCKSTEP RULE. It is opened as a gitfile is, and refused
    `pin-submodule-unreadable`, naming that `HEAD`.

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
import hashlib
import json
import os
import socket
import stat
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


def as_bytes(said: str | bytes) -> bytes:
    """`said` as the bytes a child writes: UTF-8 where it is text."""
    return said if isinstance(said, bytes) else said.encode("utf-8")


def gh_saying(where: Path, said: str | bytes, status: int) -> dict:
    """The environment of a run whose `gh`, first on PATH, prints `said` on
    stderr and exits `status`. The script is written as bytes, so its ESC
    and CR, and a byte that is not UTF-8, are the bytes themselves."""
    bin_dir = where / "gh-bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_bytes(b"#!/bin/sh\nprintf '%s' '" + as_bytes(said)
                   + b"' >&2\nexit " + str(status).encode("ascii") + b"\n")
    gh.chmod(0o755)
    return {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}


def skips_of_a_run(project: Path, where: Path, said: str | bytes) -> list:
    """The `skip` lines of the project's own gate, run with a `gh` that
    prints `said` on stderr and exits 1, failing the row on a traceback."""
    result = run_script(project / "scripts" / "validate-pins.py",
                        cwd=project, env=gh_saying(where, said, 1))
    assert "Traceback" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.endswith(LF + "pins ok" + LF), result.stdout
    return [line for line in result.stdout.split(LF)
            if line.startswith("  skip ")]


def the_skip(named: str) -> str:
    """The `skip` line for the pin `declared_with_a_pin` writes, where `gh`
    could not read it and printed what the detail names as `named`."""
    return (f"  skip openXdox: pin commit {COMMIT[:12]} digest NOT rechecked "
            "— no local checkout (gh-unreadable: `gh api` could not read "
            f"testorg/openXdox @ {COMMIT}: {named}). A --pin-source, "
            "SHAPE_PIN_SOURCE_OPENXDOX, or a checkout at ../openXdox beside "
            "this assembly root would verify it offline.")


@WINDOWS_SKIP
def test_gh_s_stderr_in_the_skip_line_is_spelled_on_one_line(project,
                                                             tmp_path):
    """U177: a `gh` that exits 1 printing an ESC, a CR and two line feeds.
    The skip is ONE line, gh's text spelled: the ESC and each break are
    escapes, the CR's too, since a CR is read as a line break, as text mode
    read one. No control reaches stdout, and the run still passes: a skip
    is never a finding."""
    declared_with_a_pin(project)
    skips = skips_of_a_run(project, tmp_path, "one" + ESC + "[31mred" + CR
                           + "two" + LF + "three" + LF)
    assert skips == [the_skip(f"one{BS}x1b[31mred{BS}ntwo{BS}nthree")]
    assert ESC not in LF.join(skips), skips
    assert CR not in LF.join(skips), skips


@WINDOWS_SKIP
def test_gh_s_stderr_that_is_not_utf_8_is_a_skip_and_no_traceback(project,
                                                                 tmp_path):
    """#968, rv919's probe: a `gh` that exits 1 printing a byte that is not
    UTF-8. Both of gh's streams were read in text mode, strictly, so the
    run ended in a `UnicodeDecodeError` traceback, exit 1, where a skip
    belongs. gh's stderr is words for a person: the byte is U+FFFD, as
    `git_out` replaces one of git's, and the run passes with its skip."""
    declared_with_a_pin(project)
    skips = skips_of_a_run(project, tmp_path,
                           b"bad" + bytes([0xFF]) + b"byte")
    assert skips == [the_skip("bad" + chr(0xFFFD) + "byte")]


def gh_answering(monkeypatch, status: int, stderr: str | bytes,
                 stdout: str | bytes = b"") -> None:
    """`subprocess.run` answering as a `gh` that exits `status` and prints
    `stdout` and `stderr`, in-process, so a row runs on every platform. The
    streams are bytes, as `tree_digest_from_gh` reads them (#968)."""
    def gh(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, status, as_bytes(stdout),
                                           as_bytes(stderr))

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
    pytest.param(b"caf" + bytes([0xE9]) + b" ok" + CR.encode("ascii")
                 + LF.encode("ascii"), "caf" + chr(0xFFFD) + " ok",
                 id="not-utf-8"),
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


def refusal_of_gh_saying(validator, monkeypatch, stdout: bytes,
                         repository: str = "testorg/openXdox"):
    """The `Refusal` of `tree_digest_from_gh` where `gh` exits 0 printing
    `stdout`, failing the row if it returns a digest or raises anything
    else."""
    gh_answering(monkeypatch, 0, b"", stdout)
    with pytest.raises(validator.Refusal) as caught:
        validator.tree_digest_from_gh(repository, COMMIT)
    return caught.value


def test_gh_json_that_is_not_utf_8_is_unreadable_and_no_traceback(
        validator, monkeypatch):
    """#968: the JSON stays strict, as #217 asks, since it becomes a digest
    and a replaced byte would be a wrong one. A byte that is not UTF-8 there
    is `gh-response-unreadable`, naming the decoder's reason, where it was a
    `UnicodeDecodeError` traceback."""
    said = b'{"tree": [], "x": "' + bytes([0xFF]) + b'"}'
    with pytest.raises(UnicodeDecodeError) as decoding:
        said.decode("utf-8")
    refusal = refusal_of_gh_saying(validator, monkeypatch, said)
    assert refusal.code == "gh-response-unreadable"
    assert refusal.detail == f"testorg/openXdox @ {COMMIT}: {decoding.value}"


#: A repository, and how every gh refusal names it: `repr`'d where a
#: character in it is not printable, and as it is where none is.
REPOSITORIES = [
    *(pytest.param(param.values[0], repr(param.values[0]), id=param.id)
      for param in UNPRINTABLE if param.id != "undecodable-byte"),
    pytest.param("testorg/openXdox", "testorg/openXdox", id="printable"),
]


@pytest.mark.parametrize("repository, named", REPOSITORIES)
@pytest.mark.parametrize("stdout, code, detail", [
    pytest.param(b"not json", "gh-response-unreadable",
                 "{named} @ {commit}: Expecting value: line 1 column 1 "
                 "(char 0)", id="not-json"),
    pytest.param(b'{"truncated": true, "tree": []}', "gh-tree-truncated",
                 "the forge truncated its tree listing for {named} @ "
                 "{commit}, so the digest would be computed over a PARTIAL "
                 "tree", id="truncated"),
    pytest.param(b"[]", "gh-response-unreadable",
                 "{named} @ {commit}: the answer is not a tree listing "
                 "(AttributeError: 'list' object has no attribute 'get')",
                 id="not-a-listing"),
])
def test_every_gh_refusal_names_the_repository_spelled(
        validator, monkeypatch, repository, named, stdout, code, detail):
    """#968: `gh-response-unreadable` and `gh-tree-truncated` named the
    repository raw, where `gh-unreadable` spelled it (#919), and a
    `validate-pins.py` skip line prints each detail. Each is `shown_path`'s
    now, and so is JSON that is not a listing; a printable repository is
    named byte for byte as it was."""
    refusal = refusal_of_gh_saying(validator, monkeypatch, stdout, repository)
    assert refusal.code == code
    assert refusal.detail == detail.format(named=named, commit=COMMIT)


#: JSON that is not gh's tree listing, and the error that ended the run in a
#: traceback for it.
NOT_A_LISTING = [
    pytest.param(b"[]", "AttributeError", id="a-list"),
    pytest.param(b"null", "AttributeError", id="null"),
    pytest.param(b'{"tree": 5}', "TypeError", id="tree-a-number"),
    pytest.param(b'{"tree": ["x"]}', "AttributeError", id="a-row-no-mapping"),
    pytest.param(b'{"tree": [{"type": "blob", "sha": "a", "path": "p"}]}',
                 "KeyError", id="a-row-without-its-mode"),
    pytest.param(b'{"tree": [{"mode": "100644", "type": "blob", "sha": "a", '
                 b'"path": "' + BS.encode("ascii") + b'ud800"}]}',
                 "UnicodeEncodeError", id="a-lone-surrogate"),
]


@pytest.mark.parametrize("stdout, error", NOT_A_LISTING)
def test_json_that_is_not_a_tree_listing_is_unreadable(validator, monkeypatch,
                                                       stdout, error):
    """#968: JSON that is not the listing's object (a list, a row that is
    no mapping or lacks a column, a path holding a lone surrogate) is what
    gh said, `gh-response-unreadable` naming the repository, where `.get`,
    a subscript or `.encode` ended the run in a traceback."""
    refusal = refusal_of_gh_saying(validator, monkeypatch, stdout)
    assert refusal.code == "gh-response-unreadable"
    assert refusal.detail.startswith(
        f"testorg/openXdox @ {COMMIT}: the answer is not a tree listing "
        f"({error}: "), refusal.detail


def test_a_tree_listing_digests_as_it_always_did(validator, monkeypatch):
    """The control: a listing, CR LF between its lines, digests as the
    definition says: each row that is no tree as `<mode> <type> <sha>`, a
    TAB and its path, UTF-8, sorted, and each ended by a line feed."""
    rows = [{"mode": "100644", "type": "blob", "sha": "b" * 40,
             "path": "caf" + chr(0xE9) + ".txt"},
            {"mode": "040000", "type": "tree", "sha": "c" * 40, "path": "d"},
            {"mode": "100755", "type": "blob", "sha": "a" * 40,
             "path": "d/run.sh"}]
    listing = (CR + LF).join(["{", '"truncated": false,', '"tree": '
                              + json.dumps(rows, ensure_ascii=False), "}", ""])
    gh_answering(monkeypatch, 0, b"", listing)
    records = sorted(
        f"{row['mode']} {row['type']} {row['sha']}{chr(9)}{row['path']}"
        .encode("utf-8") for row in rows if row["type"] != "tree")
    assert validator.tree_digest_from_gh("testorg/openXdox", COMMIT) == (
        hashlib.sha256(b"".join(record + LF.encode("ascii")
                                for record in records)).hexdigest())


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


def made_socket(path: Path) -> None:
    """A socket bound at `path` by its name, from inside its directory: the
    whole path of a socket must fit in about a hundred bytes, and a
    temporary directory's need not (rv919's r2). Closed, it stays."""
    here = Path.cwd()
    os.chdir(path.parent)
    try:
        with socket.socket(socket.AF_UNIX) as bound:
            bound.bind(path.name)
    finally:
        os.chdir(here)


POSIX_NODES = pytest.mark.skipif(
    os.name == "nt",
    reason="a FIFO needs os.mkfifo, a socket's name AF_UNIX, and Windows "
           "makes a symlink only with a privilege")

#: What can stand in a file's place, and the words after the file's name.
NOT_FILES = [
    pytest.param(made_directory, "is a directory, not a file",
                 id="directory"),
    pytest.param(made_fifo, "is a FIFO, not a file", id="fifo",
                 marks=POSIX_NODES),
    pytest.param(made_socket, "is a socket, not a file", id="socket",
                 marks=POSIX_NODES),
    pytest.param(made_link_to_nothing, "is a symlink to nothing, not a file",
                 id="symlink-to-nothing", marks=POSIX_NODES),
    pytest.param(made_loop, "is a symlink loop, not a file",
                 id="symlink-loop", marks=POSIX_NODES),
    pytest.param(made_link_to_a_directory,
                 "is a symlink to a directory, not a file",
                 id="symlink-to-a-directory", marks=POSIX_NODES),
]

#: What the leg pin's refusal says before "does not exist".
LEG_PIN_SAID = ("leg 'spec' declares testorg/Atlas-spec at 'spec' but "
                "contracts/spec-pin.yaml")

#: Each site that REFUSES, as `(the file, the code, what its line says before
#: what stands there)`: the words before "does not exist", which stay.
REFUSALS = [
    pytest.param("contracts/spec-pin.yaml", "pin-missing", LEG_PIN_SAID,
                 id="leg-pin"),
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
                 f"REFUSED pin-missing: {LEG_PIN_SAID} does not exist\n"
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


#: A remedy no site gives, standing for the lockstep one that `Refusal` gave
#: every refusal built without one before #370.
OLD_DEFAULT = "Remediation: the default of a repo_shape.py older than #370."


def refusals_defaulting(monkeypatch, validator) -> None:
    """`Refusal`, where the gate builds one, as a `repo_shape.py` older than
    #370 builds it: with a remedy of its own where none is given."""
    class Defaulting(validator.Refusal):
        def __init__(self, code, detail, remediation=OLD_DEFAULT):
            super().__init__(code, detail, remediation)

    monkeypatch.setattr(validator, "Refusal", Defaulting)


@pytest.mark.parametrize("relative, code", [
    pytest.param("contracts/spec-pin.yaml", "pin-missing", id="leg-pin"),
    pytest.param(SHAPE_PIN, "shape-pin-missing", id="shape-pin"),
    pytest.param("project.yaml", "manifest-missing", id="manifest"),
])
def test_a_refusal_with_no_remedy_of_its_own_is_built_with_none(
        validator, project, monkeypatch, relative, code):
    """rv919's r4: a file that is not there, at a site that names no remedy
    of its own, is refused with none, and not with an empty one. Beside the
    `repo_shape.py` of today the two print the same, which is why the
    mutant lived; beside one older than #370, the default is the lockstep
    remedy, and an empty one printed a blank line in its place (#370,
    #610)."""
    (project / relative).unlink()
    refusals_defaulting(monkeypatch, validator)
    refusal = refusal_of_the_run(validator, project)
    assert refusal.code == code
    assert refusal.remediation == OLD_DEFAULT


# --- #968: what stands where `contracts` should be ---------------------------

def made_file(path: Path) -> None:
    path.write_bytes(b"not a directory")


def made_link_to_a_file(path: Path) -> None:
    (path.parent / "file-w968").write_bytes(b"not a directory")
    os.symlink("file-w968", path)


#: What can stand where the directory that holds a pin should be, and the
#: words after its name.
NOT_DIRECTORIES = [
    pytest.param(made_file, "which is a file, not a directory", id="file"),
    pytest.param(made_fifo, "which is a FIFO, not a directory", id="fifo",
                 marks=POSIX_NODES),
    pytest.param(made_socket, "which is a socket, not a directory",
                 id="socket", marks=POSIX_NODES),
    pytest.param(made_link_to_nothing,
                 "which is a symlink to nothing, not a directory",
                 id="symlink-to-nothing", marks=POSIX_NODES),
    pytest.param(made_loop, "which is a symlink loop, not a directory",
                 id="symlink-loop", marks=POSIX_NODES),
    pytest.param(made_link_to_a_file,
                 "which is a symlink to a file, not a directory",
                 id="symlink-to-a-file", marks=POSIX_NODES),
]

#: The remedy where the directory that holds a pin is not a directory.
NOT_A_DIRECTORY_REMEDY = (
    READS + "Something that is not a directory stands where the directory "
    "that holds it should be: move it aside, or take it away if nobody wants "
    "it, and restore the directory from the project's history. " + AGAIN)


def contracts_replaced(project: Path, make) -> None:
    """`contracts` moved aside, and `make` putting what it makes at its
    name."""
    (project / "contracts").rename(project / "contracts-aside-w968")
    make(project / "contracts")


@pytest.mark.parametrize("make, what", NOT_DIRECTORIES)
def test_what_stands_where_contracts_should_be_is_named(project, make, what):
    """#968: `contracts` replaced by a file, a FIFO, a socket or a symlink
    that leads to no directory. Nothing can be at any pin's name, so each
    was "does not exist" under the lockstep remedy, which moves a pin and
    puts back no directory. The first pin asked, the leg's, names what
    stands there, with a remedy that says to move it aside and restore the
    directory. The whole of stderr, exit 2, nothing on stdout, and nothing
    written."""
    contracts_replaced(project, make)
    before = tree_bytes(project)
    result = validate(project)
    assert result.stderr == (
        f"REFUSED pin-missing: {LEG_PIN_SAID} is under contracts, {what}\n"
        f"{NOT_A_DIRECTORY_REMEDY}\n"), result.stderr
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == "", result.stdout
    assert tree_bytes(project) == before, "a validator writes nothing"


def shape_pin_checked(validator, root: Path) -> None:
    validator._check_shape_pin_header(root, {}, validator.Report())


def neutral_pin_checked(validator, root: Path) -> None:
    validator._check_neutral_pin_entry_and_load(root, "openXdox",
                                                validator.Report())


@pytest.mark.parametrize("check, code, said", [
    pytest.param(shape_pin_checked, "shape-pin-missing", SHAPE_PIN,
                 id="shape-pin"),
    pytest.param(neutral_pin_checked, "neutral-pin-missing",
                 f"project.yaml declares a pin on 'openXdox' but "
                 f"{NEUTRAL_PIN}", id="neutral-pin"),
])
def test_every_pin_site_names_what_stands_where_contracts_should_be(
        validator, project, check, code, said):
    """The shape pin's and a neutral-product pin's sites, which a run
    reaches only after every leg's, each asked in-process with `contracts`
    a file, on every platform."""
    contracts_replaced(project, made_file)
    with pytest.raises(validator.Refusal) as caught:
        check(validator, project)
    assert caught.value.code == code
    assert caught.value.detail == (
        f"{said} is under contracts, which is a file, not a directory")
    assert caught.value.remediation == NOT_A_DIRECTORY_REMEDY


def test_contracts_that_is_not_there_keeps_its_words(project):
    """The control: no `contracts` at all is the leg pin that "does not
    exist", under the lockstep remedy, byte for byte as it always was."""
    contracts_replaced(project, lambda _path: None)
    result = validate(project)
    assert result.stderr == (
        f"REFUSED pin-missing: {LEG_PIN_SAID} does not exist\n"
        f"{REMEDIATION}\n"), result.stderr
    assert result.returncode == 2, result.stdout + result.stderr


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
    assert_the_checkout_refused(project, "spec/.git", 0, "spec/.git")


def assert_the_checkout_refused(project: Path, relative: str, mode: int,
                                named: str) -> None:
    """The project's own gate, `relative` at `mode` (put back after): ONE
    `pin-submodule-unreadable` naming `named`, with the leg checkout's
    remedy and the permission advice, exit 2, and nothing written."""
    before = tree_bytes(project)
    with mode_of(project, relative, mode):
        result = validate(project)
    assert result.stderr == (
        f"REFUSED pin-submodule-unreadable: {named}: cannot be read "
        f"(Permission denied)\n{CHECKOUT_READS}{PERMISSION}{AGAIN}\n"), \
        result.stderr
    assert result.returncode == 2, result.stdout + result.stderr
    assert tree_bytes(project) == before, "a validator writes nothing"


#: A refused `stat` or open, and the advice its refusal gives.
CAUSES = [
    pytest.param(PermissionError(errno.EACCES, "Permission denied"),
                 PERMISSION, id="permission"),
    pytest.param(os_error(errno.EIO), OTHER, id="io-error"),
]


@pytest.mark.parametrize("failure, advice", CAUSES)
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


# --- #968: a leg's git directory this user cannot search ---------------------

#: A directory this user cannot search: no mode bit at all, and read alone.
UNSEARCHABLE = pytest.mark.parametrize("mode", [0, stat.S_IRUSR],
                                       ids=["000", "r--"])


@CANNOT_RUN_AS_ROOT
@UNSEARCHABLE
def test_the_git_directory_a_leg_gitfile_names_unsearchable_is_refused(
        project, mode):
    """#968: `.git/modules/spec`, where the leg's readable gitfile says its
    git directory is, at mode 000 or r--. Git said `fatal: not a git
    repository`, and the run ended `pin-commit-unresolvable` under THE
    LOCKSTEP RULE, which says the pinned commit is missing. It is
    `pin-submodule-unreadable`, naming that directory."""
    assert_the_checkout_refused(project, ".git/modules/spec", mode,
                                ".git/modules/spec")


def leg_with_its_own_git_directory(project: Path) -> None:
    """The leg's git directory moved from `.git/modules/spec` into the leg as
    `spec/.git`, where a checkout git has not absorbed keeps it, and its
    `worktree` line dropped, since the leg is that directory's own work tree
    now. The file is edited as text: no `git config` is run."""
    dotgit = project / "spec" / ".git"
    dotgit.unlink()
    (project / ".git" / "modules" / "spec").rename(dotgit)
    config = dotgit / "config"
    lines = config.read_bytes().split(LF.encode("ascii"))
    config.write_bytes(LF.encode("ascii").join(
        line for line in lines if not line.strip().startswith(b"worktree")))


@CANNOT_RUN_AS_ROOT
@UNSEARCHABLE
def test_a_leg_git_directory_this_user_cannot_search_is_refused(project,
                                                               mode):
    """#968: `spec/.git` a directory, the leg's own, at mode 000 or r--. Git
    passed over it and walked up to the root's own repository, so the run
    ended `pin-commit-unresolvable` with an empty reason, under THE LOCKSTEP
    RULE. It is `pin-submodule-unreadable`, naming `spec/.git`. The control
    first: searchable, the same leg passes."""
    leg_with_its_own_git_directory(project)
    passed = validate(project)
    assert passed.returncode == 0, passed.stdout + passed.stderr
    assert_the_checkout_refused(project, "spec/.git", mode, "spec/.git")


@pytest.mark.parametrize("failure, advice", CAUSES)
def test_a_leg_git_directory_whose_stat_is_refused_is_refused_everywhere(
        validator, project, monkeypatch, failure, advice):
    """The same in-process, so on every platform and as root: the `stat` of
    the `HEAD` in the git directory the gitfile names, refused, each cause
    with its own advice."""
    failing(monkeypatch, "stat", {"HEAD": failure})
    refusal = refusal_of_the_run(validator, project)
    assert refusal.code == "pin-submodule-unreadable"
    assert refusal.detail == (
        f".git/modules/spec: cannot be read ({failure.strerror})")
    assert refusal.remediation == CHECKOUT_READS + advice + AGAIN


def test_a_leg_git_directory_with_no_head_is_left_to_git(validator, project,
                                                        monkeypatch):
    """A `HEAD` that is not there is no refusal of this check's: git answers
    for that git directory, as it always did, and here git reads it, so the
    run finds nothing."""
    failing(monkeypatch, "stat", {"HEAD": os_error(errno.ENOENT)})
    report = validator.Report()
    validator._run_all_checks(project, report, [])
    assert report.findings == []


@pytest.mark.parametrize("written, named", [
    pytest.param(b"gitdir: ../.git/modules/spec" + LF.encode("ascii"),
                 "../.git/modules/spec", id="relative"),
    pytest.param(b"gitdir: ../m" + (CR + LF).encode("ascii"), "../m",
                 id="cr-lf"),
    pytest.param(b"gitdir: ../m", "../m", id="no-line-end"),
    pytest.param(b"gitdir: ../m" + (LF + LF).encode("ascii"), "../m",
                 id="blank-line-after"),
])
def test_a_gitfile_names_its_git_directory_as_git_reads_it(
        validator, tmp_path, written, named):
    """The `gitdir: ` line, its line ends stripped as git strips them, joined
    to the gitfile's own directory, its `..` left for the system to follow
    as it follows git's."""
    dotgit = tmp_path / "leg" / ".git"
    dotgit.parent.mkdir()
    dotgit.write_bytes(written)
    assert validator._leg_git_dir(dotgit) == dotgit.parent / named


def test_a_gitfile_may_name_its_git_directory_whole(validator, tmp_path):
    """An absolute `gitdir: ` is that directory, wherever the gitfile is."""
    dotgit = tmp_path / "leg" / ".git"
    dotgit.parent.mkdir()
    elsewhere = tmp_path / "elsewhere"
    dotgit.write_bytes(b"gitdir: " + os.fsencode(str(elsewhere)))
    assert validator._leg_git_dir(dotgit) == elsewhere


def test_a_git_directory_is_its_own_and_a_gitfile_naming_none_is_gits(
        validator, tmp_path):
    """A `.git` that is a directory is the leg's git directory; a gitfile
    with no `gitdir: ` line names none, and git refuses it as it always
    did."""
    leg = tmp_path / "leg"
    (leg / ".git").mkdir(parents=True)
    assert validator._leg_git_dir(leg / ".git") == leg / ".git"
    other = tmp_path / "other" / ".git"
    other.parent.mkdir()
    other.write_bytes(b"not a gitfile" + LF.encode("ascii"))
    assert validator._leg_git_dir(other) is None


# --- #1222: a leg git directory's `HEAD` this user cannot open ---------------

#: `(whether the leg's git directory is its own, its `HEAD`)`: a gitfile
#: leg's, under `.git/modules/`, and a `.git` directory's (#1222). Each
#: `HEAD` is the path the gate names.
HEADS = [
    pytest.param(False, ".git/modules/spec/HEAD", id="gitfile-leg"),
    pytest.param(True, "spec/.git/HEAD", id="git-directory-leg"),
]


@CANNOT_RUN_AS_ROOT
@pytest.mark.parametrize("own_directory, head", HEADS)
def test_a_leg_git_directory_head_this_user_cannot_open_is_refused(
        project, own_directory, head):
    """#1222, RV1200's N2: the `HEAD` of the leg's git directory at mode
    000. It stats, so #968's `stat` of it passed, and git, which could not
    read it, ended the run in `pin-commit-unresolvable` under THE LOCKSTEP
    RULE, which says the pinned commit is not in the leg's object store. It
    is `pin-submodule-unreadable`, naming that `HEAD`. The control first:
    readable, the same leg passes."""
    if own_directory:
        leg_with_its_own_git_directory(project)
    passed = validate(project)
    assert passed.returncode == 0, passed.stdout + passed.stderr
    assert_the_checkout_refused(project, head, 0, head)


@pytest.mark.parametrize("own_directory, head", HEADS)
@pytest.mark.parametrize("failure, advice", CAUSES)
def test_a_leg_git_directory_head_whose_open_is_refused_is_refused_everywhere(
        validator, project, monkeypatch, own_directory, head, failure,
        advice):
    """The same in-process, so on every platform and as root: the open of
    the `HEAD` refused, each cause with its own advice."""
    if own_directory:
        leg_with_its_own_git_directory(project)
    failing(monkeypatch, "open", {"HEAD": failure})
    refusal = refusal_of_the_run(validator, project)
    assert refusal.code == "pin-submodule-unreadable"
    assert refusal.detail == f"{head}: cannot be read ({failure.strerror})"
    assert refusal.remediation == CHECKOUT_READS + advice + AGAIN


def test_a_head_gone_when_it_is_opened_is_left_to_git(validator, project,
                                                     monkeypatch):
    """Asked as `_is_a` asks a `stat`: an open of the `HEAD` that finds
    nothing at the name is a git directory with no `HEAD`, which git answers
    for, and not a file this user cannot read. Here git reads it, so the run
    finds nothing."""
    failing(monkeypatch, "open", {"HEAD": os_error(errno.ENOENT)})
    report = validator.Report()
    validator._run_all_checks(project, report, [])
    assert report.findings == []


@pytest.mark.parametrize("make", [
    pytest.param(made_directory, id="directory"),
    pytest.param(made_fifo, id="fifo", marks=POSIX_NODES),
])
def test_a_head_that_is_no_regular_file_is_not_opened(validator, tmp_path,
                                                      monkeypatch, make):
    """Only a `HEAD` that is a regular file is opened: one that is anything
    else is git's to answer for, and the open of a FIFO would wait for a
    writer. An open of either fails the row rather than hanging it."""
    dotgit = tmp_path / "leg" / ".git"
    dotgit.mkdir(parents=True)
    make(dotgit / "HEAD")
    failing(monkeypatch, "open", {"HEAD": AssertionError("opened")})
    assert validator._refuse_an_unreadable_git_dir(tmp_path, dotgit) is None


def test_a_head_no_system_call_can_name_is_left_to_git(validator, tmp_path):
    """A `gitdir: ` line that holds a NUL names a git directory no system
    call can take, so its `HEAD` is nothing there, as `_is_there` answers a
    name the system cannot take: nothing is opened, no `ValueError` ends
    the run, and git refuses the gitfile as it always did."""
    dotgit = tmp_path / "leg" / ".git"
    dotgit.parent.mkdir()
    dotgit.write_bytes(b"gitdir: ../m" + chr(0).encode("ascii") + b"x")
    assert validator._refuse_an_unreadable_git_dir(tmp_path, dotgit) is None
