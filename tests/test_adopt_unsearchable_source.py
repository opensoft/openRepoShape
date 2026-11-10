# SPDX-License-Identifier: Apache-2.0
"""`adopt-project.py`: a path this user cannot reach is refused by name, never
read as one that is not there (slice H of #430).

`Path.exists()`, `is_file()` and `is_dir()` raised a refused `stat` up to
Python 3.13 and answer False to ANY `OSError` from 3.14; `os.path.exists`
has always answered False to one. So where `adopt-project.py` asked one of
them about a path the person can make unreadable, the same command gave a
traceback on one Python and a false sentence on the other. ON 5017830
(2026-10-18), Python 3.12.3, and the same Python with a `sitecustomize` that
makes those four answer as 3.14's do, a non-root user, local remotes and a
stub `gh` that refuses every call:

- `plan --source <dir>/Thing`, `<dir>` mode 000: a `PermissionError`
  traceback at `_source_spec`, exit 1; as 3.14, `REFUSED source-unresolvable:
  --source '...' is neither a path that exists nor an `org/repo` name`.
- `plan --source testorg/Thing` beside `./testorg` at mode 000, and
  `github.com/testorg/Thing` beside `./github.com`: the same traceback; as
  3.14, `cloning testorg/Thing (read only)`, `gh repo clone` asked, where
  `source-ambiguous` refuses the spelling once the path can be seen.
- `check` of a plan whose `source.local_path` is under a mode-000 directory:
  the traceback, at `_recorded_source`; as 3.14, `plan-source-gone`, "names
  nothing that exists", and, recorded as a clone `plan` made, `NOTE ... no
  longer exists, so its source.repository, testorg/Thing, is cloned again`
  and `gh repo clone` asked.
- `execute --yes --local-remote-dir <mode 000>`: the traceback at
  `_refuse_a_split_branch_left_behind`, before the leg question that names
  such a directory (`adopt-folder-cannot-be-made`, which 3.14 reached).
- `check` of a plan that keeps `AGENTS.md` in the root, a symlink to a file
  under a mode-000 directory: on both, `FINDING plan-root-symlink: ... and
  nothing is there`, of a place that holds a file.

Now each is `source-unreadable`, naming the path and the operating system's
reason, with `chmod u+rx` as the cure, on every Python; the leg question
names the unsearchable `--local-remote-dir`; and the symlink's finding says
its destination cannot be read.

TWO WAYS TO REFUSE A `stat`, as `tests/test_bump_leg_unopenable.py` has them.
A real mode (`chmod 000`), restored in a `finally`, run in a child: skipped on
Windows and as root, who reads through every mode. And an in-process stand-in
(`refused_stat`) that refuses `Path.stat` for named paths and makes
`Path.exists`, `is_file` and `is_dir` answer as 3.14's do, so a tool that
leans on them fails on every Python, root and Windows included.

NO NETWORK AND NO GITHUB: a child runs with a `gh` first on PATH that records
each call and refuses it, and a test asserts it was never asked; in-process,
`gh repo clone` is a `git clone` of a repository on disk (`gh_clones`).
"""

from __future__ import annotations

import contextlib
import errno
import os
import shlex
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import (ADOPT, git, load_without_bytecode, make_source_repo,
                      run_script, spelled)
from test_adopt_temp_work_roots import (
    ORG, PLANNED, PROJECT, REPOSITORY, SMALL_TREE, needs_filter_repo,
    planned_from_github, recorded,
)

needs_a_mode = pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="a mode that refuses the owner is a POSIX mode, and root reads "
           "through every one (tests/test_bump_leg_unopenable.py)")
needs_a_symlink = pytest.mark.skipif(
    sys.platform == "win32",
    reason="the source keeps a symlink, which Windows makes only with a "
           "privilege CI does not grant")

UNREADABLE = "REFUSED source-unreadable: "
DENIED = "cannot be read (Permission denied)"
CURE = ("Make it readable by this user: `chmod u+rx` on the directory and on "
        "every directory above it, or fix who owns them. Then run the same "
        "command again")
#: What the code before #430's slice H said, on one Python or the other.
FALSE_ANSWERS = ("Traceback", "neither a path that exists",
                 "names nothing that exists", "no longer exists",
                 "is cloned again", "cloning ")
URL = f"https://github.com/{REPOSITORY}"


@pytest.fixture(scope="module")
def adopter():
    return load_without_bytecode(ADOPT, "adopt_unsearchable_source")


@contextlib.contextmanager
def unsearchable(directory: Path):
    """`directory` at mode 000 (no listing, no search) for the `with`, its
    mode given back in a `finally`, so the temporary tree can be removed.
    The mode is asserted to bite: a file system that ignores modes would
    pass every test here for the wrong reason."""
    before = stat.S_IMODE(directory.stat().st_mode)
    directory.chmod(0)
    try:
        assert not os.access(directory, os.X_OK), directory
        yield directory
    finally:
        directory.chmod(before)


def refused_stat(monkeypatch, *names: str) -> None:
    """`Path.stat` refused (`Permission denied`) for each path whose last
    part is one of `names`, as it is for a name inside a directory this user
    may not search; and `Path.is_file`, `is_dir` and `exists` answering as
    Python 3.14's do, False to ANY `OSError`. In-process, so it runs on every
    Python, every platform and as root (`tests/test_bump_leg_unopenable.py`'s
    `refused_stat`)."""
    real = Path.stat

    def refusing(self, *args, **kwargs):
        if self.name in names:
            raise PermissionError(errno.EACCES, "Permission denied", str(self))
        return real(self, *args, **kwargs)

    def as_python_314(kind):
        def answer(self, *args, **kwargs):
            try:
                return kind(self.stat(*args, **kwargs).st_mode)
            except (OSError, ValueError):
                return False
        return answer

    monkeypatch.setattr(Path, "stat", refusing)
    monkeypatch.setattr(Path, "is_file", as_python_314(stat.S_ISREG))
    monkeypatch.setattr(Path, "is_dir", as_python_314(stat.S_ISDIR))
    monkeypatch.setattr(Path, "exists", as_python_314(lambda mode: True))


def recording_gh(directory: Path) -> tuple[dict, Path]:
    """A `gh` that records each call in a log and refuses it, put first on
    PATH: `(the environment a child is run with, the log)`. Ahead of the
    suite's own guard, so a call is this test's to assert on."""
    directory.mkdir()
    log = directory / "gh-calls.log"
    log.write_bytes(b"")
    script = directory / "gh"
    script.write_bytes(
        f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> {shlex.quote(str(log))}\n"
        "echo 'w430h: gh is not to be asked here' >&2\nexit 4\n"
        .encode("utf-8"))
    script.chmod(0o755)
    return {"PATH": f"{directory}{os.pathsep}{os.environ['PATH']}"}, log


def said(proc) -> str:
    """What a child printed, stdout then stderr."""
    return proc.stdout + proc.stderr


def assert_no_false_answer(text: str) -> None:
    """None of the words the code before the fix said, on either Python."""
    for words in FALSE_ANSWERS:
        assert words not in text, (words, text)


def run(adopter, capsys, *argv: str) -> tuple[int, str, str]:
    """`adopt-project.py <argv>` in this process: its exit, stdout, stderr."""
    capsys.readouterr()
    code = adopter.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def planned_locally(tmp_path: Path, source: Path, cloned: bool = False
                    ) -> Path:
    """`plan --source <source>` in a child, with a work directory of its own,
    and the plan it wrote; recorded as a clone `plan` made where `cloned`
    says so, as `plan --source <org/repo>` records its clone."""
    plan = tmp_path / "adoption-plan.yaml"
    written = run_script(ADOPT, "plan", "--source", str(source), *PLANNED,
                         "--out", str(plan), "--work-dir",
                         str(tmp_path / "plan-work"))
    assert written.returncode == 0, said(written)
    if cloned:
        text = plan.read_bytes()
        assert text.count(b"\n  cloned: false\n") == 1, text
        plan.write_bytes(text.replace(b"\n  cloned: false\n",
                                      b"\n  cloned: true\n"))
    return plan


# --- the helper, asked as Python 3.9 to 3.13 asked it ------------------------

@pytest.mark.parametrize("code", [errno.ENOENT, errno.ENOTDIR, errno.EBADF,
                                  errno.ELOOP])
def test_a_stat_that_finds_nothing_is_nothing_there(adopter, monkeypatch,
                                                    tmp_path, code):
    """The four `OSError`s that `Path.exists()` answered False to on 3.9 to
    3.13, and that `scripts/bump-leg.py`'s `_is_a` reads as absent (#383)."""
    def refusing(self, *args, **kwargs):
        raise OSError(code, os.strerror(code), str(self))

    monkeypatch.setattr(Path, "stat", refusing)
    assert adopter._is_there(tmp_path / "x") is False


@pytest.mark.parametrize("code", [errno.EACCES, errno.EPERM, errno.EIO,
                                  errno.ENAMETOOLONG])
def test_any_other_refused_stat_is_raised_never_read_as_absent(
        adopter, monkeypatch, tmp_path, code):
    """Every other `OSError` is the operating system declining to say, which
    3.14's `Path.exists()` answers False to, and `_is_there` raises."""
    def refusing(self, *args, **kwargs):
        raise OSError(code, os.strerror(code), str(self))

    monkeypatch.setattr(Path, "stat", refusing)
    with pytest.raises(OSError) as raised:
        adopter._is_there(tmp_path / "x")
    assert raised.value.errno == code


def test_a_name_the_system_cannot_take_is_nothing_there(adopter):
    """A NUL in a name is no path at all, as `Path.exists()` answered it."""
    assert adopter._is_there(Path("no\0such")) is False


# --- `--source` under a directory this user cannot search (:1826) ------------

@needs_a_mode
def test_a_source_under_an_unsearchable_parent_is_refused_by_name(tmp_path):
    """A local `--source` whose parent is mode 000: a traceback on 3.12 and
    `source-unresolvable`, "neither a path that exists nor an `org/repo`",
    on 3.14. Now `source-unreadable`, naming it, with the cure, and no plan
    is written."""
    locked = tmp_path / "locked"
    source = make_source_repo(locked / PROJECT, tree=SMALL_TREE, edits=())
    plan = tmp_path / "adoption-plan.yaml"
    env, log = recording_gh(tmp_path / "gh-bin")

    with unsearchable(locked):
        proc = run_script(ADOPT, "plan", "--source", str(source), *PLANNED,
                          "--out", str(plan), "--work-dir",
                          str(tmp_path / "work"), env=env)

    assert proc.returncode == 2, said(proc)
    assert (f"{UNREADABLE}--source {str(source)!r}: {DENIED}, so whether a "
            "repository is there cannot be told") in proc.stderr
    assert CURE in proc.stderr
    assert_no_false_answer(said(proc))
    assert not plan.exists()
    assert log.read_bytes() == b""


@pytest.mark.parametrize(("spec", "untold"), [
    pytest.param("{locked}", "whether a repository is there", id="a-path"),
    pytest.param(REPOSITORY, "whether it names the path `./testorg/Thing` "
                 f"here, or only the GitHub repository `{REPOSITORY}`,",
                 id="org-repo"),
    pytest.param(f"{REPOSITORY}/", "whether it names the path "
                 f"`./testorg/Thing` here, or only the GitHub repository "
                 f"`{REPOSITORY}`,", id="org-repo-slash"),
    pytest.param(f"github.com/{REPOSITORY}", "whether it names the path "
                 f"`./github.com/testorg/Thing` here, or only the GitHub "
                 f"repository `{REPOSITORY}`,", id="bare-github-url"),
])
def test_a_source_whose_stat_is_refused_is_refused_on_every_python(
        adopter, monkeypatch, tmp_path, spec, untold):
    """The same question with the `stat` refused in-process, as 3.14 answers
    `exists()`: a path is never "neither a path that exists nor an
    `org/repo`", and a spelling that may be a path here is never handed to
    `gh repo clone`; `_source_spec` returning `(None, "testorg/Thing")` was
    that clone. The url is offered, as `source-ambiguous` offers it."""
    spec = spec.format(locked=tmp_path / "locked" / PROJECT)
    monkeypatch.chdir(tmp_path)
    refused_stat(monkeypatch, PROJECT)

    with pytest.raises(adopter.Refusal) as raised:
        adopter._source_spec(spec)

    refusal = raised.value
    assert refusal.code == "source-unreadable"
    assert refusal.detail == (f"--source {spec!r}: {DENIED}, so {untold} "
                              "cannot be told")
    assert CURE in refusal.remediation
    assert (f"pass `{URL}` to clone the repository from GitHub" in
            refusal.remediation) == (spec != str(tmp_path / "locked" /
                                                 PROJECT))


def test_a_stat_refused_for_another_reason_is_not_told_to_chmod(
        adopter, monkeypatch, tmp_path):
    """A `stat` refused for another reason than permission (an I/O error)
    is `source-unreadable` too, told to put right what it names: no `chmod`
    puts that right."""
    def refusing(self, *args, **kwargs):
        raise OSError(errno.EIO, os.strerror(errno.EIO), str(self))

    monkeypatch.setattr(Path, "stat", refusing)
    with pytest.raises(adopter.Refusal) as raised:
        adopter._source_spec(str(tmp_path / PROJECT))

    refusal = raised.value
    assert refusal.code == "source-unreadable"
    assert f"cannot be read ({os.strerror(errno.EIO)})" in refusal.detail
    assert ("which no `chmod` puts right: put right what it names"
            in refusal.remediation)
    assert "chmod u+rx" not in refusal.remediation


# --- an `org/repo`-shaped directory here that cannot be searched -------------

@needs_a_mode
@pytest.mark.parametrize(("spec", "holder"), [
    (REPOSITORY, ORG),
    (f"github.com/{REPOSITORY}", "github.com"),
])
def test_an_org_repo_beside_an_unsearchable_directory_is_not_sent_to_github(
        tmp_path, spec, holder):
    """`./testorg/Thing` is a repository here, under a `./testorg` this user
    cannot search, and `--source testorg/Thing` names it as well as the
    GitHub repository. On 3.14 it was cloned from GitHub, where the same
    spelling beside a directory that can be searched is `source-ambiguous`.
    Now `source-unreadable`, and `gh` is never asked."""
    here = tmp_path / "here"
    make_source_repo(here.joinpath(*spec.split("/")), tree=SMALL_TREE,
                     edits=())
    env, log = recording_gh(tmp_path / "gh-bin")

    with unsearchable(here / holder):
        proc = run_script(ADOPT, "plan", "--source", spec, *PLANNED, "--out",
                          str(tmp_path / "adoption-plan.yaml"), "--work-dir",
                          str(tmp_path / "work"), cwd=here, env=env)

    assert proc.returncode == 2, said(proc)
    assert (f"{UNREADABLE}--source {spec!r}: {DENIED}, so whether it names "
            f"the path `./{spec}` here, or only the GitHub repository "
            f"`{REPOSITORY}`, cannot be told") in proc.stderr
    assert f"pass `{URL}` to clone the repository from GitHub" in proc.stderr
    assert_no_false_answer(said(proc))
    assert log.read_bytes() == b""
    assert not (tmp_path / "work" / "source-readonly").exists()


# --- an `org/repo` spelling GitHub cannot hold (#1003) -----------------------

#: A part of a spelling longer than a file system lets a file name be, and
#: so longer than GitHub lets an owner or a repository be named
#: (`GITHUB_OWNER_MAX`, `GITHUB_NAME_MAX`): `stat` is `File name too long`.
LONG = "a" * 300
TOO_LONG = f"cannot be read ({os.strerror(errno.ENAMETOOLONG)})"
#: What GitHub keeps an owner's name and a repository's to, as
#: tests/test_github_name_limits.py writes them.
OWNER_MAX, NAME_MAX = 39, 100
#: The end of `source-unreadable`'s remedy for a cause other than permission.
OTHER_CURE = ("which no `chmod` puts right: put right what it names. Then run "
              "the same command again")
needs_a_name_too_long = pytest.mark.skipif(
    sys.platform == "win32",
    reason="`File name too long` (ENAMETOOLONG) is a POSIX `stat`'s answer "
           "to a name over the file system's limit; Windows answers it with "
           "errors of its own")


def too_long_here(path: Path) -> None:
    """`stat` of `path`, relative to the directory the test runs in, is
    refused with `File name too long`, asserted so a file system that took
    the name would not pass a test here for the wrong reason."""
    with pytest.raises(OSError) as raised:
        path.stat()
    assert raised.value.errno == errno.ENAMETOOLONG, raised.value


def refused_for(monkeypatch, code: int) -> None:
    """`Path.stat` refused with `code` for every path, as the operating
    system refuses it: `EACCES` is a `PermissionError`, `EIO` an `OSError`.
    In-process, so it runs on every platform and as root."""
    def refusing(self, *args, **kwargs):
        raise OSError(code, os.strerror(code), str(self))

    monkeypatch.setattr(Path, "stat", refusing)


def assert_both_readings_and_the_url(adopter, spec: str, name: str) -> None:
    """`--source spec`, its `stat` refused, names a repository GitHub can
    hold: `source-unreadable` leaves both readings open and offers the url,
    as `source-ambiguous` offers it (#430)."""
    with pytest.raises(adopter.Refusal) as raised:
        adopter._source_spec(spec)
    refusal = raised.value
    assert refusal.code == "source-unreadable"
    assert (f"or only the GitHub repository `{name}`, cannot be told"
            in refusal.detail), refusal.detail
    assert (f"pass `https://github.com/{name}` to clone the repository from "
            "GitHub.") in refusal.remediation, refusal.remediation


@needs_a_name_too_long
@pytest.mark.parametrize(("written", "holder", "names", "limit"), [
    pytest.param("{}/" + PROJECT, None, "{}/" + PROJECT, OWNER_MAX,
                 id="owner"),
    pytest.param(ORG + "/{}", ORG, ORG + "/{}", NAME_MAX, id="repository"),
    # A `github.com/` spelling past GitHub's limits names no `owner/repo`,
    # and `_repository_in_url` refuses it before any `stat` (#1129):
    # tests/test_adopt_source_github_limits.py holds it.
])
def test_a_spelling_too_long_for_the_disk_is_offered_no_url(
        adopter, monkeypatch, tmp_path, written, holder, names, limit):
    """`--source <300 a's>/Thing` is `source-unreadable`, `File name too
    long` (#430's slice H), and was told "whether it names the path ...
    here, or only the GitHub repository ..., cannot be told", with
    `https://github.com/<300 a's>/Thing` offered: a url that can never clone,
    for a name GitHub gives no owner or repository (#1003). It is refused
    as a path too long is, and offered no url. `written` spells the source
    with `{}` for the long part, and `names` the GitHub repository it names;
    `limit` is what GitHub keeps that part to. `holder` is the directory the
    spelling's first part names here, made so the `stat` reaches the long
    part."""
    spec = written.format(LONG)
    monkeypatch.chdir(tmp_path)
    if holder is not None:
        (tmp_path / holder).mkdir()
    too_long_here(Path(spec))

    with pytest.raises(adopter.Refusal) as raised:
        adopter._source_spec(spec)

    refusal = raised.value
    assert refusal.code == "source-unreadable"
    assert refusal.detail == (f"--source {spec!r}: {TOO_LONG}, so whether a "
                              "repository is there cannot be told")
    assert refusal.remediation.endswith(OTHER_CURE + "."), refusal.remediation
    assert "https://" not in refusal.remediation

    # The control: the part as long as GitHub lets it be, its `stat` refused
    # for another reason (an I/O error), names a repository GitHub can hold,
    # so both readings stay open and its url is offered.
    refused_for(monkeypatch, errno.EIO)
    assert_both_readings_and_the_url(adopter, written.format("a" * limit),
                                     names.format("a" * limit))


@pytest.mark.parametrize("code", [errno.EIO, errno.EACCES],
                         ids=["EIO", "EACCES"])
@pytest.mark.parametrize(("written", "names", "limit", "length"), [
    pytest.param("{}/" + PROJECT, "{}/" + PROJECT, OWNER_MAX, OWNER_MAX + 1,
                 id="owner-one-over"),
    pytest.param("{}/" + PROJECT, "{}/" + PROJECT, OWNER_MAX, len(LONG),
                 id="owner-too-long-for-the-disk"),
    pytest.param(ORG + "/{}", ORG + "/{}", NAME_MAX, NAME_MAX + 1,
                 id="repository-one-over"),
    pytest.param(ORG + "/{}", ORG + "/{}", NAME_MAX, len(LONG),
                 id="repository-too-long-for-the-disk"),
    # A `github.com/` spelling: tests/test_adopt_source_github_limits.py.
])
def test_a_name_github_cannot_hold_is_offered_no_url_whatever_the_reason(
        adopter, monkeypatch, tmp_path, code, written, names, limit, length):
    """An owner over 39 characters, or a repository over 100, is no name
    GitHub holds (#1003), whatever the operating system refused the `stat`
    for. #1122's first head read the reason, not the name: only `File name
    too long` lost the url, so `testorg/<300 a's>` beside a `./testorg` this
    user cannot search, which stops at `Permission denied` before the long
    part, was offered `https://github.com/testorg/<300 a's>`, which can never
    clone. Now it is refused as a path is, with the cure for its cause and
    no url. The control: the part as long as GitHub lets it be, refused
    alike, keeps both readings and its url."""
    monkeypatch.chdir(tmp_path)
    refused_for(monkeypatch, code)
    spec = written.format("a" * length)

    with pytest.raises(adopter.Refusal) as raised:
        adopter._source_spec(spec)

    refusal = raised.value
    assert refusal.code == "source-unreadable"
    assert refusal.detail == (f"--source {spec!r}: cannot be read "
                              f"({os.strerror(code)}), so whether a "
                              "repository is there cannot be told")
    assert refusal.remediation.endswith(
        (CURE if code == errno.EACCES else OTHER_CURE) + "."
    ), refusal.remediation
    assert "https://" not in refusal.remediation

    assert_both_readings_and_the_url(adopter, written.format("a" * limit),
                                     names.format("a" * limit))


@needs_a_name_too_long
def test_plan_of_a_spelling_too_long_for_the_disk_offers_no_url(tmp_path):
    """The same, as `plan` is run: `source-unreadable`, exit 2, naming no
    GitHub repository and offering no url; no plan is written, nothing is
    made and `gh` is never asked."""
    here = tmp_path / "here"
    here.mkdir()
    spec = f"{LONG}/{PROJECT}"
    plan = tmp_path / "adoption-plan.yaml"
    env, log = recording_gh(tmp_path / "gh-bin")

    proc = run_script(ADOPT, "plan", "--source", spec, *PLANNED, "--out",
                      str(plan), "--work-dir", str(tmp_path / "work"),
                      cwd=here, env=env)

    assert proc.returncode == 2, said(proc)
    assert (f"{UNREADABLE}--source {spec!r}: {TOO_LONG}, so whether a "
            "repository is there cannot be told\n") in proc.stderr
    assert "GitHub repository" not in said(proc)
    assert "https://" not in said(proc)
    assert_no_false_answer(said(proc))
    assert not plan.exists()
    assert not (tmp_path / "work").exists()
    assert log.read_bytes() == b""


@needs_a_name_too_long
@needs_a_symlink
def test_a_name_github_can_hold_keeps_its_url_through_a_link_too_long(
        adopter, monkeypatch, tmp_path):
    """`testorg/Thing`, with `./testorg` a symlink to a name too long: the
    `stat` is `File name too long`, from the link's destination and not from
    the spelling, which names a repository GitHub can hold. #1122's first
    head read the reason and refused it as a path, with no url; it names
    both readings again, as main did, and offers
    `https://github.com/testorg/Thing`."""
    monkeypatch.chdir(tmp_path)
    os.symlink(LONG, ORG)
    too_long_here(Path(REPOSITORY))

    with pytest.raises(adopter.Refusal) as raised:
        adopter._source_spec(REPOSITORY)

    refusal = raised.value
    assert refusal.code == "source-unreadable"
    assert refusal.detail == (
        f"--source {REPOSITORY!r}: {TOO_LONG}, so whether it names the path "
        f"`./{REPOSITORY}` here, or only the GitHub repository "
        f"`{REPOSITORY}`, cannot be told")
    assert refusal.remediation.endswith(
        f"{OTHER_CURE}; or pass `{URL}` to clone the repository from GitHub."
    ), refusal.remediation


@needs_a_mode
def test_plan_of_a_name_github_cannot_hold_in_an_unsearchable_place(
        tmp_path):
    """`plan --source testorg/<300 a's>` beside a `./testorg` at mode 000:
    the `stat` stops at `Permission denied` before it reaches the long part,
    and #1122's first head, which read the reason and not the name, offered
    `https://github.com/testorg/<300 a's>`, a url that can never clone
    (#1003). Now `source-unreadable` as a path is, with the cure for a
    permission, naming no GitHub repository and offering no url; no plan is
    written, nothing is made and `gh` is never asked."""
    here = tmp_path / "here"
    (here / ORG).mkdir(parents=True)
    spec = f"{ORG}/{LONG}"
    plan = tmp_path / "adoption-plan.yaml"
    env, log = recording_gh(tmp_path / "gh-bin")

    with unsearchable(here / ORG):
        with pytest.raises(PermissionError):
            (here / spec).stat()
        proc = run_script(ADOPT, "plan", "--source", spec, *PLANNED, "--out",
                          str(plan), "--work-dir", str(tmp_path / "work"),
                          cwd=here, env=env)

    assert proc.returncode == 2, said(proc)
    assert (f"{UNREADABLE}--source {spec!r}: {DENIED}, so whether a "
            "repository is there cannot be told\n") in proc.stderr
    assert CURE in proc.stderr
    assert "GitHub repository" not in said(proc)
    assert "https://" not in said(proc)
    assert_no_false_answer(said(proc))
    assert not plan.exists()
    assert not (tmp_path / "work").exists()
    assert log.read_bytes() == b""


# --- a recorded source this user cannot reach (:5735) ------------------------

def test_a_recorded_clone_whose_stat_is_refused_is_not_cloned_again(
        adopter, monkeypatch, capsys, tmp_path):
    """`plan --source testorg/Thing` records its clone, and `check` finds the
    clone's `stat` refused. As 3.14 answered, it "no longer exists" and was
    cloned again from GitHub beside the one still there. Now it is
    `source-unreadable`, and no second clone is asked for."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    assert len(planned.calls) == 1, planned.calls
    refused_stat(monkeypatch, Path(planned.clone).name)

    code, out, err = run(adopter, capsys, "check", "--plan",
                         str(planned.plan), "--work-dir",
                         str(tmp_path / "check-work"), "--local-remote-dir",
                         str(tmp_path / "remotes"))

    assert code == 2, out + err
    assert (f"{UNREADABLE}the plan's `source.local_path`, "
            f"{spelled(planned.clone)}: {DENIED}, so whether `plan`'s clone "
            "is still there, to be read, or gone, to be cloned again, cannot "
            "be told") in err
    assert CURE in err
    assert_no_false_answer(out + err)
    assert len(planned.calls) == 1, planned.calls


@needs_a_mode
@pytest.mark.parametrize(("verb", "cloned", "untold"), [
    ("check", False, "whether the source is still there"),
    ("check", True, "whether `plan`'s clone is still there, to be read, or "
                    "gone, to be cloned again,"),
    ("execute", True, "whether `plan`'s clone is still there, to be read, "
                      "or gone, to be cloned again,"),
])
def test_a_recorded_source_under_an_unsearchable_parent_is_refused_by_name(
        tmp_path, verb, cloned, untold):
    """The plan's `source.local_path` under a mode-000 directory: on 3.12 a
    traceback; on 3.14 `plan-source-gone`, "names nothing that exists", or,
    a clone `plan` made, "no longer exists" and `gh repo clone` asked. Now
    `source-unreadable` in `check` and `execute` alike, nothing cloned and
    `gh` never asked."""
    locked = tmp_path / "locked"
    source = make_source_repo(locked / PROJECT, tree=SMALL_TREE, edits=())
    git("remote", "add", "origin", f"{URL}.git", cwd=source)
    plan = planned_locally(tmp_path, source, cloned)
    local_path = str(recorded(plan)["local_path"])
    env, log = recording_gh(tmp_path / "gh-bin")
    work = tmp_path / f"{verb}-work"

    with unsearchable(locked):
        proc = run_script(ADOPT, verb, "--plan", str(plan), "--work-dir",
                          str(work), "--local-remote-dir",
                          str(tmp_path / "remotes"),
                          *(["--yes"] if verb == "execute" else []), env=env)

    assert proc.returncode == 2, said(proc)
    assert (f"{UNREADABLE}the plan's `source.local_path`, "
            f"{spelled(local_path)}: {DENIED}, so {untold} cannot be told"
            ) in proc.stderr
    assert CURE in proc.stderr
    assert ("or pass the source again with --source, which is held to the "
            "plan's `commit:`.") in proc.stderr
    assert "plan-source-gone" not in said(proc)
    assert_no_false_answer(said(proc))
    assert log.read_bytes() == b""
    assert not (work / "source-readonly").exists()
    assert not (tmp_path / "remotes").exists()


# --- a `--local-remote-dir` this user cannot search (:11216, :8538) ----------

@needs_a_mode
@needs_filter_repo
def test_execute_into_an_unsearchable_local_remote_dir_names_it(tmp_path):
    """`execute --local-remote-dir` given a directory at mode 000: on 3.12 a
    `PermissionError` traceback at the split branch's question, which asked
    `Path.exists()` whether a leg was there. Now that question defers, as it
    does to a leg already there, and the leg question names the directory,
    before either leg is made."""
    source = make_source_repo(tmp_path / PROJECT, tree=SMALL_TREE, edits=())
    plan = planned_locally(tmp_path, source)
    remotes = tmp_path / "remotes"
    remotes.mkdir()

    with unsearchable(remotes):
        proc = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                          "--local-remote-dir", str(remotes), "--work-dir",
                          str(tmp_path / "execute-work"))

    assert proc.returncode == 2, said(proc)
    named = spelled(os.path.realpath(remotes))
    assert "REFUSED adopt-folder-cannot-be-made: " in proc.stderr
    assert (f"--local-remote-dir {named} cannot hold the two leg "
            f"repositories: {named} is a folder this user cannot write in"
            ) in proc.stderr
    assert "Traceback" not in said(proc)
    assert list(remotes.iterdir()) == []


def _split_branch_left_behind(adopter, source, urls) -> None:
    adopter._refuse_a_split_branch_left_behind(source, urls, "w430h-left",
                                               True)


def _branch_in_the_split_branchs_way(adopter, source, urls) -> None:
    adopter._refuse_a_branch_in_the_split_branchs_way(
        SimpleNamespace(path=Path("adoption-plan.yaml")), source, {}, urls,
        "w430h-in-the-way/split", True, False)


@pytest.mark.parametrize(("ask", "code"), [
    (_split_branch_left_behind, "adopt-branch-exists"),
    (_branch_in_the_split_branchs_way, "plan-split-branch-taken"),
], ids=["left-behind", "in-the-way"])
def test_a_leg_whose_stat_is_refused_defers_the_split_branch_questions(
        adopter, monkeypatch, tmp_path, ask, code):
    """Each split-branch question defers to the leg question where a leg is
    on disk under `--local-remote-dir`; where the leg's `stat` is refused it
    may be, and it defers too. The source holds what each would refuse: a
    branch of the split's name at a commit not behind the source's
    (`adopt-branch-exists`), and one whose name git cannot hold beside the
    split branch (`plan-split-branch-taken`). As 3.14 answered `exists()`,
    each was refused first; on 3.12 the `stat` raised out of `execute`."""
    source_path = make_source_repo(tmp_path / PROJECT, tree=SMALL_TREE,
                                   edits=())
    tree = git("rev-parse", "HEAD^{tree}", cwd=source_path).stdout.strip()
    orphan = git("commit-tree", tree, "-m", "elsewhere",
                 cwd=source_path).stdout.strip()
    git("branch", "w430h-left", orphan, cwd=source_path)
    git("branch", "w430h-in-the-way", cwd=source_path)
    work = tmp_path / "work"
    work.mkdir()
    source = adopter.Source.in_place(Path(os.path.realpath(source_path)),
                                     work)
    remotes = tmp_path / "remotes"
    urls = {"assembly": str(source.path),
            "spec": str(remotes / f"{PROJECT}-spec.git"),
            "code": str(remotes / f"{PROJECT}-code.git")}
    with pytest.raises(adopter.Refusal) as control:
        # The control: with nothing refused, each question refuses.
        ask(adopter, source, urls)
    assert control.value.code == code
    refused_stat(monkeypatch, f"{PROJECT}-spec.git", f"{PROJECT}-code.git")

    assert ask(adopter, source, urls) is None


# --- a symlink the root keeps, to a place this user cannot search (:9017) ---

def linked_out(tmp_path: Path) -> tuple[Path, Path]:
    """A source that keeps `AGENTS.md` in the root as a symlink to a file
    outside it, by absolute path, and the plan for it: `(the file, plan)`.
    `AGENTS.md` is a path the shape writes, and `place` writes its copy
    beside a link to something that is there."""
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "AGENTS.md"
    target.write_text("theirs\n", encoding="utf-8")
    source = make_source_repo(tmp_path / PROJECT, tree=SMALL_TREE, edits=())
    os.symlink(str(target), source / "AGENTS.md")
    git("add", "-A", cwd=source)
    git("commit", "-qm", "Link AGENTS.md out", cwd=source)
    return target, planned_locally(tmp_path, source)


def checked(plan: Path, tmp_path: Path, name: str):
    """`check --plan <plan>` in a child, asking the disk about the legs."""
    return run_script(ADOPT, "check", "--plan", str(plan), "--work-dir",
                      str(tmp_path / name), "--local-remote-dir",
                      str(tmp_path / "remotes"))


@needs_a_mode
def test_a_symlink_to_an_unsearchable_place_is_not_called_empty(tmp_path):
    """The link's destination is under a mode-000 directory: `check` said
    "and nothing is there", on every Python (`os.path.exists`), of a place
    that holds a file. It is still a finding, because the shape cannot ask
    what is there either; and the finding says why, with the cure."""
    target, plan = linked_out(tmp_path)
    control = checked(plan, tmp_path, "control-work")
    assert control.returncode == 0, said(control)
    assert "plan-root-symlink" not in said(control)

    with unsearchable(target.parent):
        proc = checked(plan, tmp_path, "check-work")

    assert proc.returncode == 1, said(proc)
    finding = next(line for line in proc.stderr.splitlines()
                   if line.startswith("FINDING plan-root-symlink: "))
    assert (f"the symlink `AGENTS.md` leads to {spelled(target)}, an absolute "
            "path: a place on this machine, not in the assembly, and "
            f"{spelled(target)}: {DENIED}, so whether anything is there "
            "cannot be told until this user can search every directory "
            "above it (`chmod u+rx`). ") in finding
    assert "nothing is there" not in said(proc)
    assert "Traceback" not in said(proc)


@needs_a_symlink
def test_a_symlink_to_a_place_whose_stat_is_refused_is_named(
        adopter, monkeypatch, capsys, tmp_path):
    """The same, in-process, with the `stat` of the link's destination
    refused, so it runs as root too: `os.path.exists` read the refusal as
    nothing there."""
    target, plan = linked_out(tmp_path)
    real = os.stat

    def refusing(path, *args, **kwargs):
        if os.fspath(path) == str(target):
            raise PermissionError(errno.EACCES, "Permission denied",
                                  os.fspath(path))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", refusing)
    code, out, err = run(adopter, capsys, "check", "--plan", str(plan),
                         "--work-dir", str(tmp_path / "check-work"),
                         "--local-remote-dir", str(tmp_path / "remotes"))

    assert code == 1, out + err
    assert (f"and {spelled(target)}: {DENIED}, so whether anything is there "
            "cannot be told until this user can search every directory above "
            "it (`chmod u+rx`). Send `AGENTS.md` to a leg or `drop` it") in err
    assert "nothing is there" not in out + err


@needs_a_symlink
def test_a_symlink_place_refused_for_another_reason_is_not_told_to_chmod(
        adopter, monkeypatch, capsys, tmp_path):
    """The same, in-process, with the `stat` of the link's destination
    refused for another reason than permission (an I/O error): the finding
    names that reason and stops there, since no `chmod` puts it right.
    `(chmod u+rx)` is said of a permission only."""
    target, plan = linked_out(tmp_path)
    real = os.stat

    def refusing(path, *args, **kwargs):
        if os.fspath(path) == str(target):
            raise OSError(errno.EIO, os.strerror(errno.EIO), os.fspath(path))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", refusing)
    code, out, err = run(adopter, capsys, "check", "--plan", str(plan),
                         "--work-dir", str(tmp_path / "check-work"),
                         "--local-remote-dir", str(tmp_path / "remotes"))

    assert code == 1, out + err
    assert (f"and {spelled(target)}: cannot be read "
            f"({os.strerror(errno.EIO)}), so whether anything is there "
            "cannot be told. Send `AGENTS.md`") in err
