# SPDX-License-Identifier: Apache-2.0
"""A `--pin-source` that cannot answer is `pin-source-unreadable` (#339).

`pin_digest_from_source` caught only `Refusal`. A source that is a directory
but no clone is git's own failure, a `Refusal`, and was always the refusal
`pin-source-unreadable` with its remediation, exit 2. A source
`subprocess.run` cannot enter at all never reaches git: `FileNotFoundError`
for one that is not there, `NotADirectoryError` for a file,
`PermissionError` for one under a parent this user cannot search, all raised
out of `cwd=`, and nothing caught them. `scaffold-project.py --pin ...
--pin-source <that>` ended `--dry-run` and the real run alike in a
traceback, exit 1, and since #273 `adopt-project.py plan --pin` reads its
digest through the same function and ended the same way. The symlink loop was
a fourth way in: `Path.resolve()` raised a `RuntimeError` before 3.13 (an
`OSError` since), before the digest was asked for at all.

Both tools reach the one function through `declared_pin_values`, so every case
runs three ways: `scaffold-project.py --dry-run`, the same without it, and
`adopt-project.py plan`. Each must give exit 2 and the refusal NAMING the
source and the reason, with the remediation the not-a-clone refusal already
had, no traceback, and nothing created: no remote directory and no work
directory for the scaffold, no plan file for adopt. The reasons are the
sentences `validate-pins.py` gives the same sources (#295, #312): "no such
directory", "it is a file, not a directory", and the system's own for any
other `OSError`.

NO NETWORK AND NO GITHUB. Every run names `--pin-source`, so `gh` is never
reached; the session's `gh` guard (`conftest.gh_guard`, #296) fails any test
whose run called it, which is the `gh` that fails if called. The sources are
never read except where a case says so: the commit asked for is any 40 hex.
"""

from __future__ import annotations

import errno
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ADOPT, ORG, REPO, SCAFFOLD, git, make_source_repo, run_script

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml, tree_digest  # noqa: E402

PROJECT = "MedxGlass"
#: Any 40 hex: no source below is asked for it, but the clone that is not one.
COMMIT = "0123456789abcdef0123456789abcdef01234567"

#: `validate-pins.py`'s two sentences for a source that is no directory.
NO_SUCH_DIRECTORY = "no such directory"
A_FILE = "it is a file, not a directory"

#: What every refusal is told to do, as the not-a-clone refusal always said it.
REMEDIATION = ("Remediation: point --pin-source at a clone of that repository "
               "that HAS the pinned commit (`git fetch --all` first), or drop "
               "--pin-source and let `gh api` read the forge.")

#: A directory mode denies nothing on Windows, where `chmod` has no search
#: bit to clear, and nothing to root. The skip is a mark, so it comes before
#: any fixture builds a directory or any tool runs.
SEARCH_DENIED = pytest.mark.skipif(
    os.name == "nt" or getattr(os, "geteuid", lambda: 1)() == 0,
    reason="needs a POSIX directory mode that denies search: Windows has no "
           "search bit for chmod to clear, and root is not stopped by one")

#: Windows grants a symlink only to an elevated user or a developer-mode one.
SYMLINKS = pytest.mark.skipif(
    os.name == "nt",
    reason="needs a symlink, which Windows grants only to an elevated user")

#: A Windows command line is text, so it holds no byte that is not UTF-8.
POSIX_ARGV = pytest.mark.skipif(
    os.name == "nt",
    reason="needs a command-line argument that is not UTF-8, which a Windows "
           "command line cannot hold")

#: How a tool is asked, and what it must not have made when it refuses.
RUNS = ["scaffold-dry-run", "scaffold-run", "adopt-plan"]


def run(kind: str, base: Path, adoptable: Path, typed: str,
        commit: str = COMMIT, cwd: Path | None = None,
        env: dict | None = None) -> subprocess.CompletedProcess:
    """`--pin openGlass@<commit> --pin-source <typed>` through `kind`, into
    `base`."""
    if kind == "adopt-plan":
        return run_script(ADOPT, "plan", "--source", str(adoptable),
                          "--project", PROJECT, "--org", ORG,
                          "--elected-by", "Test Human",
                          "--elected-on", "2026-09-02",
                          "--out", str(base / "plan.yaml"),
                          "--pin", f"openGlass@{commit}",
                          "--pin-source", typed, cwd=cwd, env=env)
    return run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                      "--elected-by", "Test Human",
                      "--elected-on", "2026-09-02",
                      "--pin", f"openGlass@{commit}", "--pin-source", typed,
                      "--local-remote-dir", str(base / "remotes"),
                      "--work-dir", str(base / "work"),
                      *(("--dry-run",) if kind == "scaffold-dry-run" else ()),
                      cwd=cwd, env=env)


def made(kind: str, base: Path) -> list[str]:
    """What the run created under `base`: nothing, when it refused."""
    names = ("plan.yaml",) if kind == "adopt-plan" else ("remotes", "work")
    return [name for name in names if (base / name).exists()]


@pytest.fixture(scope="module")
def adoptable(tmp_path_factory) -> Path:
    """The repository `adopt-project.py plan` is asked to plan."""
    return make_source_repo(tmp_path_factory.mktemp("adoptable") / "Thing")


@pytest.fixture(scope="module")
def glass(tmp_path_factory) -> tuple[Path, str]:
    """A local stand-in for `openGlass`, which does answer: `(path, commit)`."""
    path = tmp_path_factory.mktemp("glass") / "openGlass"
    path.mkdir()
    git("init", "-q", "-b", "main", cwd=path)
    (path / "README.md").write_bytes(b"# openGlass\n")
    git("add", "-A", cwd=path)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "seed",
        cwd=path)
    return path, git("rev-parse", "HEAD", cwd=path).stdout.strip()


class Unreadable:
    """A `--pin-source` that cannot answer: what is typed, the path the
    refusal names, the reason it gives (`None` where the system's own differs
    by platform), and the directory a test unlocks again."""

    def __init__(self, typed: str, named: str | None = None,
                 said: str | None = None, cwd: Path | None = None,
                 locked: Path | None = None, git_says: bool = False,
                 names_it: bool = True) -> None:
        self.typed, self.named = typed, named or typed
        self.said, self.cwd, self.locked = said, cwd, locked
        #: The reason is git's own, which names the commit and the path.
        self.git_says = git_says
        #: The refusal names the path as it was built here. False where a
        #: platform answers for the path itself (below), so that only the
        #: refusal and its remediation are asserted there.
        self.names_it = names_it


@pytest.fixture(params=[
    "missing",
    "a-file",
    "beneath-a-file",
    "relative-missing",
    pytest.param("parent-not-searchable", marks=SEARCH_DENIED),
    pytest.param("source-not-searchable", marks=SEARCH_DENIED),
    "name-too-long",
    pytest.param("symlink-loop", marks=SYMLINKS),
    "not-a-clone",
])
def unreadable(request, tmp_path):
    """Each way a source fails to answer, built under `tmp_path`.

    `missing`, `a-file` and `parent-not-searchable` are the issue's table;
    the rest are its neighbours, the other ways `stat()` or git's `cwd=`
    can raise; `not-a-clone` is the refusal that always held, unchanged.
    `relative-missing` is typed relative to the working directory the tool
    runs in and is named absolute, as the not-a-clone refusal always named
    its source.
    """
    case = request.param
    locked = None
    if case == "missing":
        source = Unreadable(str(tmp_path / "missing"), said=NO_SUCH_DIRECTORY)
    elif case == "a-file":
        (tmp_path / "afile").write_bytes(b"not a checkout\n")
        source = Unreadable(str(tmp_path / "afile"), said=A_FILE)
    elif case == "beneath-a-file":
        (tmp_path / "afile").write_bytes(b"not a checkout\n")
        # POSIX answers ENOTDIR for a path beneath a file. Windows answers
        # its own error, so the sentence is asserted only where it is known.
        source = Unreadable(str(tmp_path / "afile" / "x"),
                            said=NO_SUCH_DIRECTORY if os.name != "nt" else None)
    elif case == "relative-missing":
        source = Unreadable("gone", named=str(tmp_path / "gone"),
                            said=NO_SUCH_DIRECTORY, cwd=tmp_path)
    elif case == "parent-not-searchable":
        locked = tmp_path / "locked"
        (locked / "x").mkdir(parents=True)
        source = Unreadable(str(locked / "x"), said=os.strerror(errno.EACCES),
                            locked=locked)
    elif case == "source-not-searchable":
        locked = tmp_path / "locked"
        locked.mkdir()
        source = Unreadable(str(locked), said=os.strerror(errno.EACCES),
                            locked=locked)
    elif case == "name-too-long":
        # One path component the filesystem has to refuse by name. What
        # Windows calls it is its own business: it is an `OSError` there too,
        # so the refusal and the absent traceback are asserted everywhere and
        # the reason only where POSIX says it.
        source = Unreadable(str(tmp_path / ("n" * 300)),
                            said=None if os.name == "nt"
                            else os.strerror(errno.ENAMETOOLONG),
                            names_it=os.name != "nt")
    elif case == "symlink-loop":
        os.symlink("loop", tmp_path / "loop")
        source = Unreadable(str(tmp_path / "loop"),
                            said=os.strerror(errno.ELOOP))
    else:
        (tmp_path / "plain").mkdir()
        source = Unreadable(str(tmp_path / "plain"), git_says=True)
    if locked is not None:
        locked.chmod(0)
    try:
        yield source
    finally:
        if locked is not None:
            locked.chmod(0o700)


def assert_refused(result: subprocess.CompletedProcess, kind: str, base: Path,
                   source: Unreadable) -> None:
    """The refusal `pin-source-unreadable`, exit 2: naming the source and the
    reason, with its remediation, and with nothing created."""
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    head = ("REFUSED pin-source-unreadable: "
            f"{source.named} could not answer for opensoft/openGlass "
            f"@ {COMMIT}: ")
    if not source.names_it:
        head = "REFUSED pin-source-unreadable: "
    assert head in result.stderr, result.stderr
    if source.said is not None:
        assert f"{head}{source.said}\n{REMEDIATION}\n" in result.stderr, \
            result.stderr
    else:
        assert REMEDIATION in result.stderr, result.stderr
    assert made(kind, base) == [], (
        "a refusal comes before anything exists, `--dry-run` or not")


@pytest.mark.parametrize("kind", RUNS)
def test_a_pin_source_that_cannot_answer_is_pin_source_unreadable(
        kind, unreadable, tmp_path, adoptable):
    """The issue's table, and its neighbours, through every way in. The one
    case that held before is `not-a-clone`, git's own failure, whose
    sentence is git's and is asserted as the part of it that does not depend
    on where the repository is kept."""
    result = run(kind, tmp_path, adoptable, unreadable.typed,
                 cwd=unreadable.cwd)
    if unreadable.git_says:
        assert result.returncode == 2, result.stdout + result.stderr
        assert (f"REFUSED pin-source-unreadable: {unreadable.named} could "
                f"not answer for opensoft/openGlass @ {COMMIT}: `git ls-tree "
                f"-r -z {COMMIT}` in {unreadable.named} exited"
                in result.stderr), result.stderr
        assert REMEDIATION in result.stderr
        assert made(kind, tmp_path) == []
    else:
        assert_refused(result, kind, tmp_path, unreadable)


def test_the_dry_run_and_the_real_run_refuse_in_the_same_words(
        unreadable, tmp_path, adoptable):
    """`--dry-run` is the real run's plan, so a source that cannot answer is
    refused identically by both: the same exit, the same stderr, the same
    stdout, and neither makes anything. Through `setup.sh`, which hands the
    flags to the scaffold's `--dry-run`, it is the refusal an operator reads
    in the middle of the plan block."""
    dry = run("scaffold-dry-run", tmp_path, adoptable, unreadable.typed,
              cwd=unreadable.cwd)
    real = run("scaffold-run", tmp_path, adoptable, unreadable.typed,
               cwd=unreadable.cwd)
    assert dry.returncode == real.returncode == 2, (
        dry.stdout + dry.stderr + real.stdout + real.stderr)
    assert (dry.stderr, dry.stdout) == (real.stderr, real.stdout)
    assert "Traceback" not in dry.stderr
    assert made("scaffold-run", tmp_path) == []


@pytest.mark.parametrize("kind", RUNS)
@pytest.mark.parametrize("name, spelled, env", [
    pytest.param("日本-missing", "\\u65e5\\u672c-missing",
                 {"PYTHONIOENCODING": "ascii"}, id="not-ascii"),
    pytest.param("miss\udcffing", "miss\\udcffing", {},
                 marks=POSIX_ARGV, id="not-utf-8"),
])
def test_the_source_is_printed_escaped_and_never_raised_on(
        kind, name, spelled, env, tmp_path, adoptable):
    """The refusal names a path a person typed, and a stderr that cannot
    encode it prints it escaped, as it does for every other path the tools
    name: the refusal is never a `UnicodeEncodeError` in its place. The
    second row is a name that is not UTF-8 (POSIX only: a Windows command
    line has no such byte), read with `surrogateescape`, so it prints as
    the surrogate it was read as."""
    typed = str(tmp_path / name)
    result = run(kind, tmp_path, adoptable, typed, env=env)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert spelled in result.stderr, result.stderr
    assert "REFUSED pin-source-unreadable: " in result.stderr
    assert made(kind, tmp_path) == []


# --- a source that answers is read exactly as before -------------------------
#
# Nothing about a source that DOES answer moved: a relative path is resolved
# against the working directory the tool runs in, a symlink to a clone is
# followed, and the digest is the one `repo_shape.tree_digest` gives.

@pytest.mark.parametrize("kind", ["scaffold-dry-run", "adopt-plan"])
@pytest.mark.parametrize("spelling", [
    "relative",
    pytest.param("symlinked", marks=SYMLINKS),
])
def test_a_source_that_answers_is_read_as_before(kind, spelling, tmp_path,
                                                 adoptable, glass):
    product, commit = glass
    digest = tree_digest(product, commit)
    if spelling == "relative":
        typed, cwd = "openGlass", product.parent
    else:
        typed, cwd = str(tmp_path / "link"), None
        os.symlink(product, tmp_path / "link", target_is_directory=True)
    result = run(kind, tmp_path, adoptable, typed, commit=commit, cwd=cwd)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    if kind == "adopt-plan":
        pin = load_yaml(tmp_path / "plan.yaml")["pins"][0]
        assert pin["commit"] == commit
        assert pin["tree_sha256"] == digest
        assert pin["digest_source"] == f"local-clone ({typed})"
    else:
        assert f"tree {digest[:12]}" in result.stdout, result.stdout
        assert f"(local-clone ({typed}))" in result.stdout, result.stdout
        assert "--dry-run: nothing was created." in result.stdout
