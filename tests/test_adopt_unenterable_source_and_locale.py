# SPDX-License-Identifier: Apache-2.0
"""`adopt-project.py`: a `--source`, or a plan's `source.local_path`, that
this user cannot enter is refused by name, and a recorded path this locale
cannot spell is asked as the UTF-8 bytes the plan holds (#918, #457's L1-105
and L1-86).

ON 00f6d7f7 (2026-10-20), Python 3.12.3, a non-root user, a stub `gh` that
refuses every call and local remotes:

- L1-105. `plan --source <dir>`, `<dir>` itself at mode 000 (one under a
  parent at mode 000 is #430's slice H, `source-unreadable` already): a
  `PermissionError` traceback from `git rev-parse` in `_top_level`, exit 1.
  `check` of a plan whose `local_path` is at mode 000: the same traceback;
  recorded as a clone `plan` made, `plan-source-gone`, "a clone `plan` made
  that is no longer whole (git finds no repository there)", or, with a
  `source.repository`, a NOTE and `gh repo clone` of a clone still there.
- L1-86. A plan written in UTF-8 mode for a source directory `Thing\\u00e9`,
  checked under `LC_ALL=C PYTHONUTF8=0`: `plan-source-gone`, "names nothing
  that exists", exit 2, of a source that is there, and `plan ok` in UTF-8
  mode.

Now the first is `source-unreadable`, naming the path and the operating
system's reason, with `chmod u+rx` as the cure, before anything is cloned or
written; and the second reads the source, `plan ok`, as UTF-8 mode does.
Where the UTF-8 bytes name nothing either, `plan-source-gone` says it asked
them and names the locale's encoding, which cannot spell the path.

A real mode runs in a child, skipped on Windows and as root
(`needs_a_mode`); the same questions are asked in-process with git's
`cwd=` refused, which runs everywhere. A C locale is a POSIX idea, so the
locale's tests skip where `c_locale_or_skip` finds none.
"""

from __future__ import annotations

import errno
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ADOPT, git, make_source_repo, run_script, spelled
from test_adopt_c_locale_bytes import in_the_locale
from test_adopt_git_rm_bytes import C_LOCALE
from test_adopt_temp_work_roots import (PLANNED, PROJECT, SMALL_TREE,
                                        planned_from_github, recorded)
from test_adopt_unsearchable_source import (  # noqa: F401
    CURE, DENIED, UNREADABLE, URL, adopter, assert_no_false_answer,
    needs_a_mode, planned_locally, recording_gh, run, said, unsearchable,
)

#: What a refused `cwd=` was read as for a clone `plan` made, on 00f6d7f7.
NO_REPOSITORY = "git finds no repository there"
#: The way past a recorded source `source-unreadable` names.
INSTEAD = ("or pass the source again with --source, which is held to the "
           "plan's `commit:`.")
#: What `source-unreadable` cannot tell of a recorded source, by
#: `source.cloned`.
UNTOLD = {False: "whether the source is still there",
          True: "whether `plan`'s clone is still there, to be read, or gone, "
                "to be cloned again,"}
#: A source directory outside ASCII: `Thing` and U+00E9, as #918 measured.
ACCENTED = "Thing\u00e9"
#: UTF-8 mode under the C locale: how the plan is written.
UTF8_MODE = {"LC_ALL": "C", "PYTHONUTF8": "1"}


def refused_cwd(adopter, monkeypatch, directory: str,
                error: OSError | None = None) -> None:
    """`git_out` run with `cwd=<directory>` raises what `subprocess` raises
    for a directory this user cannot enter, `PermissionError` naming it;
    or `error`, for every call. Every other call is git's own."""
    real = adopter.git_out

    def refusing(args, cwd, *rest, **kwargs):
        if error is not None:
            raise error
        if os.path.realpath(cwd) == os.path.realpath(directory):
            raise PermissionError(errno.EACCES, "Permission denied", str(cwd))
        return real(args, cwd, *rest, **kwargs)

    monkeypatch.setattr(adopter, "git_out", refusing)


# --- L1-105: a `--source` this user cannot enter ----------------------------

@needs_a_mode
def test_a_source_this_user_cannot_enter_is_refused_by_name(tmp_path):
    """`--source` names a repository at mode 000 itself: a traceback on
    00f6d7f7. Now `source-unreadable`, with the cure; no plan is written,
    nothing is cloned and `gh` is never asked."""
    source = make_source_repo(tmp_path / PROJECT, tree=SMALL_TREE, edits=())
    plan = tmp_path / "adoption-plan.yaml"
    env, log = recording_gh(tmp_path / "gh-bin")

    with unsearchable(source):
        proc = run_script(ADOPT, "plan", "--source", str(source), *PLANNED,
                          "--out", str(plan), "--work-dir",
                          str(tmp_path / "work"), env=env)

    assert proc.returncode == 2, said(proc)
    assert (f"{UNREADABLE}--source {str(source)!r}: {DENIED}, so whether a "
            "repository is there cannot be told") in proc.stderr
    assert CURE in proc.stderr
    assert_no_false_answer(said(proc))
    assert not plan.exists()
    assert not (tmp_path / "work" / "source-readonly").exists()
    assert log.read_bytes() == b""


def test_a_source_git_cannot_enter_is_refused_on_every_platform(
        adopter, monkeypatch, tmp_path):
    """The same, in-process, with the `cwd=` of git refused, so it runs as
    root and on Windows too."""
    source = make_source_repo(tmp_path / PROJECT, tree=SMALL_TREE, edits=())
    refused_cwd(adopter, monkeypatch, str(source))

    with pytest.raises(adopter.Refusal) as raised:
        adopter._source_spec(str(source))

    assert raised.value.code == "source-unreadable"
    assert raised.value.detail == (f"--source {str(source)!r}: {DENIED}, so "
                                   "whether a repository is there cannot be "
                                   "told")
    assert CURE in raised.value.remediation


def test_a_git_that_cannot_be_started_is_not_read_as_the_source(
        adopter, monkeypatch, tmp_path):
    """Only the directory's own refusal is `source-unreadable`: a git that
    cannot be started names the program, not the directory, and is raised
    as `git_out` leaves it, never said of the source."""
    source = make_source_repo(tmp_path / PROJECT, tree=SMALL_TREE, edits=())
    refused_cwd(adopter, monkeypatch, str(source), FileNotFoundError(
        errno.ENOENT, os.strerror(errno.ENOENT), "git"))

    with pytest.raises(FileNotFoundError):
        adopter._source_spec(str(source))


# --- L1-105: a recorded source this user cannot enter -----------------------

@needs_a_mode
@pytest.mark.parametrize(("verb", "cloned"), [
    ("check", False), ("check", True), ("execute", True),
])
def test_a_recorded_source_this_user_cannot_enter_is_refused_by_name(
        tmp_path, verb, cloned):
    """The plan's `source.local_path` at mode 000: on 00f6d7f7 a traceback
    where `plan` was given the path, and where it is recorded as a clone
    `plan` made, "no longer whole (git finds no repository there)", so the
    plan's `source.repository` was cloned again, `gh` asked. Now
    `source-unreadable` in `check` and `execute` alike, nothing cloned and
    `gh` never asked."""
    source = make_source_repo(tmp_path / PROJECT, tree=SMALL_TREE, edits=())
    git("remote", "add", "origin", f"{URL}.git", cwd=source)
    plan = planned_locally(tmp_path, source, cloned)
    local_path = str(recorded(plan)["local_path"])
    env, log = recording_gh(tmp_path / "gh-bin")
    work = tmp_path / f"{verb}-work"

    with unsearchable(source):
        proc = run_script(ADOPT, verb, "--plan", str(plan), "--work-dir",
                          str(work), "--local-remote-dir",
                          str(tmp_path / "remotes"),
                          *(["--yes"] if verb == "execute" else []), env=env)

    assert proc.returncode == 2, said(proc)
    assert (f"{UNREADABLE}the plan's `source.local_path`, "
            f"{spelled(local_path)}: {DENIED}, so {UNTOLD[cloned]} cannot be "
            "told") in proc.stderr
    assert CURE in proc.stderr
    assert INSTEAD in proc.stderr
    assert "plan-source-gone" not in said(proc)
    assert NO_REPOSITORY not in said(proc)
    assert_no_false_answer(said(proc))
    assert log.read_bytes() == b""
    assert not (work / "source-readonly").exists()
    assert not (tmp_path / "remotes").exists()


def test_a_recorded_clone_git_cannot_enter_is_not_cloned_again(
        adopter, monkeypatch, capsys, tmp_path):
    """`plan --source testorg/Thing` records its clone, and git cannot enter
    it: on 00f6d7f7 it was "no longer whole (git finds no repository
    there)", and cloned again from GitHub. Now `source-unreadable`, and no
    second clone is asked for. In-process, so it runs everywhere."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    assert len(planned.calls) == 1, planned.calls
    refused_cwd(adopter, monkeypatch, planned.clone)

    code, out, err = run(adopter, capsys, "check", "--plan",
                         str(planned.plan), "--work-dir",
                         str(tmp_path / "check-work"), "--local-remote-dir",
                         str(tmp_path / "remotes"))

    assert code == 2, out + err
    assert (f"{UNREADABLE}the plan's `source.local_path`, "
            f"{spelled(planned.clone)}: {DENIED}, so {UNTOLD[True]} cannot be "
            "told") in err
    assert NO_REPOSITORY not in out + err
    assert_no_false_answer(out + err)
    assert len(planned.calls) == 1, planned.calls


def test_a_clone_whose_git_cannot_be_started_is_still_no_repository(
        adopter, monkeypatch, tmp_path):
    """`_not_a_whole_clone` raises only the directory's own refusal: a git
    that cannot be started is what it always was, no repository there."""
    clone = make_source_repo(tmp_path / PROJECT, tree=SMALL_TREE, edits=())
    refused_cwd(adopter, monkeypatch, str(clone), FileNotFoundError(
        errno.ENOENT, os.strerror(errno.ENOENT), "git"))

    assert adopter._not_a_whole_clone(clone, "") == NO_REPOSITORY


# --- L1-86: a plan written in UTF-8 mode, checked under the C locale ---------

def written_in_utf8_mode(monkeypatch, tmp_path: Path, cloned: bool
                         ) -> tuple[Path, Path, Path, dict]:
    """A source at `<tmp>/Thing\\u00e9`, its `origin` on GitHub, and the plan
    `plan` writes for it in UTF-8 mode, recorded as a clone `plan` made
    where `cloned` says so: `(source, plan, gh log, gh environment)`."""
    in_the_locale(monkeypatch, UTF8_MODE)
    source = make_source_repo(tmp_path / ACCENTED, tree=SMALL_TREE, edits=())
    git("remote", "add", "origin", f"{URL}.git", cwd=source)
    env, log = recording_gh(tmp_path / "gh-bin")
    plan = tmp_path / "adoption-plan.yaml"
    written = run_script(ADOPT, "plan", "--source", str(source), *PLANNED,
                         "--out", str(plan), "--work-dir",
                         str(tmp_path / "plan-work"), env=env)
    assert written.returncode == 0, said(written)
    assert recorded(plan)["local_path"].endswith(f"/{ACCENTED}"), (
        "premise: the plan holds the character itself")
    if cloned:
        text = plan.read_bytes()
        assert text.count(b"\n  cloned: false\n") == 1, text
        plan.write_bytes(text.replace(b"\n  cloned: false\n",
                                      b"\n  cloned: true\n"))
    return source, plan, log, env


def checked(plan: Path, tmp_path: Path, name: str, env: dict):
    """`check --plan <plan>` in a child, in the locale this test set."""
    return run_script(ADOPT, "check", "--plan", str(plan), "--work-dir",
                      str(tmp_path / name), "--local-remote-dir",
                      str(tmp_path / "remotes"), env=env)


@pytest.mark.parametrize("cloned", [False, True], ids=["given", "cloned"])
def test_a_plan_written_in_utf8_mode_is_read_under_the_c_locale(
        monkeypatch, tmp_path, cloned):
    """#918's measurement: on 00f6d7f7 `plan-source-gone`, "names nothing
    that exists", and, recorded as a clone `plan` made, "no longer exists"
    and `gh repo clone` asked. Now `check` reads the source where it is,
    `plan ok`, exit 0, as it does in UTF-8 mode, and `gh` is never asked."""
    _, plan, log, env = written_in_utf8_mode(monkeypatch, tmp_path, cloned)
    utf8 = checked(plan, tmp_path, "utf8-work", env)
    in_the_locale(monkeypatch, C_LOCALE)

    proc = checked(plan, tmp_path, "c-work", env)

    assert utf8.returncode == 0, said(utf8)
    assert proc.returncode == 0, said(proc)
    assert "plan ok" in proc.stdout
    assert "Traceback" not in proc.stderr
    assert "plan-source-gone" not in said(proc)
    assert "no longer exists" not in said(proc)
    assert log.read_bytes() == b""


def test_a_plan_path_this_locale_cannot_spell_and_utf8_does_not_find(
        monkeypatch, tmp_path):
    """The source moved away after `plan`: under the C locale its UTF-8
    bytes name nothing either, and `plan-source-gone` says it asked them,
    naming this locale's encoding; in UTF-8 mode, which spells the path as
    written, the refusal is as it always was."""
    source, plan, log, env = written_in_utf8_mode(monkeypatch, tmp_path,
                                                  False)
    source.rename(tmp_path / "moved")
    utf8 = checked(plan, tmp_path, "utf8-work", env)
    in_the_locale(monkeypatch, C_LOCALE)
    encoding = subprocess.run(
        [sys.executable, "-c",
         "import sys; print(sys.getfilesystemencoding())"],
        capture_output=True, text=True, check=True,
        stdin=subprocess.DEVNULL).stdout.strip()

    proc = checked(plan, tmp_path, "c-work", env)

    gone = "REFUSED plan-source-gone: the plan's `source.local_path`, "
    rest = (", and the plan does not record it as a clone `plan` made "
            "(`source.cloned` is not `true`), so nothing clones it again")
    assert utf8.returncode == 2, said(utf8)
    assert f"`, names nothing that exists{rest}" in utf8.stderr
    assert gone in utf8.stderr
    assert proc.returncode == 2, said(proc)
    assert gone in proc.stderr
    assert (f"`, names nothing that exists as UTF-8 spells it (this locale's "
            f"file names, {encoding}, cannot spell it){rest}") in proc.stderr
    assert "Traceback" not in proc.stderr
    assert log.read_bytes() == b""


def test_a_surrogate_no_byte_is_read_as_is_asked_as_written(adopter):
    """A lone surrogate outside U+DC80 to U+DCFF, which a hand edit can put
    in a plan, is no byte `surrogateescape` reads: no name on the disk holds
    it, and it is asked as written, as `Path.exists()` asked it."""
    assert adopter._recorded_spelling("Thing\ud800") == ("Thing\ud800", "")
