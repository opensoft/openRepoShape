# SPDX-License-Identifier: Apache-2.0
"""`--source` is read by its spelling, an `org/repo` in any spelling is
cloned by its name, the plan records whether `plan` made its clone
(`source.cloned`), a recorded clone that is gone or broken is cloned again
or refused for what it is, and a clone no plan records is removed (#652:
L1-22, L1-23, L1-24, L1-26, L1-27 and L1-43 of #457).

ON MAIN AT 2fac9790 (2026-10-16), probed with a stand-in `gh`:
- L1-24. With `./acme/Atlas` in the current directory, `plan --source
  acme/Atlas` planned that directory, cloned nothing and exited 0; and
  `check`, its plan's clone gone, said the repository "is cloned again"
  and read that directory, `plan-stale`.
- L1-43. `--source acme/Atlas/` was cloned into `source-readonly/` itself,
  or refused by gh's parser with a remedy about `gh auth status`; `//`,
  `.git`, a url and `github.com/acme/Atlas` were each handed to `gh` as
  typed, and none of them wrote a plan.
- L1-22 and L1-27. A local source the person gave, moved away, was handed
  to `gh repo clone` as an `org/repo` where it had no `origin`, and cloned
  again from github.com where it had one, a gitlab one included; on Windows
  it was `source-unresolvable`, naming a `--source` nobody passed.
- L1-26. A clone `plan` made, emptied, half-cleaned or stripped of its
  pack, was refused `git-failed`; emptied inside another repository it was
  read as that one.
- L1-23. `check --source <org/repo>`, `check` where the plan's clone was
  gone, and a `plan` refused after its clone each left the clone, and a
  run given the same `--work-dir` next was refused at it, `source-
  unclonable`, with a remedy about `gh auth status`.

And each `--source` that names no repository's top level, nor a repository
on GitHub, is refused by name before git reads anything else, with no plan
written and no `gh` run (#796). ON MAIN AT bf1f099b (2026-10-17):
- L1-64. A file ended `plan`, `check` and `execute` in a
  `NotADirectoryError` traceback, exit 1.
- L1-88. A directory inside a repository, or `.` run in one, was planned,
  exit 0, holding only what is under it; and the `source` line named the
  `origin`'s repository, whatever directory was read.
- L1-95. `~nouser/x` ended each in `RuntimeError: Could not determine home
  directory.`, and so did a plan recording it.
- L1-96. `--source ''` inside a repository planned that repository, and
  `check` and `execute` dropped the value.
- L1-100 and L1-101. `owner/.git` was handed to `gh`; `www.github.com` was
  refused as another host, or as neither a path nor a name.
- L1-77. A source that lost a blob ended each in a `ValueError` at
  `Source.tree`, exit 1.

NO NETWORK AND NO GITHUB: `gh repo clone` is a `git clone` of a repository
on disk, and only `testorg/Thing` is found (`gh_clones`).
"""

from __future__ import annotations

import errno
import io
import os
import stat
import sys
from pathlib import Path

import pytest

from conftest import ADOPT, git, make_source_repo, rmtree, run_script, spelled
from test_adopt_plan_leg_path_help import HELP_ENV, option_lines
from test_adopt_temp_work_roots import (  # noqa: F401
    CHECK, EXECUTE, GONE, LOCAL_REMOTE_DIR, ORG, OUT, PLAN, PLAN_FLAG,
    PLAN_VERB, PLANNED, PROJECT, REMOTES, REPOSITORY, SMALL_TREE, SOURCE_FLAG,
    adopter, gh_clones, in_a_fresh_temp_folder, left_in, planned_from_github,
    recorded,
)

WORK = "work"
WORK_FLAG = "--work-dir"
SOURCE_READONLY = "source-readonly"
#: The `gh` call that clones the one repository the stand-in knows.
CLONE = ["gh", "repo", "clone", REPOSITORY]
AMBIGUOUS = "REFUSED source-ambiguous: "
GONE_REFUSED = "REFUSED plan-source-gone: "
OCCUPIED = "REFUSED adopt-work-dir-occupied: "
UNRESOLVABLE = "REFUSED source-unresolvable: "
NOT_WHOLE = "is a clone `plan` made that is no longer whole ("
NO_REPOSITORY = "git finds no repository there"
NO_COMMIT = "it no longer holds the plan's commit "
NOT_MADE = ("names nothing that exists, and the plan does not record it as "
            "a clone `plan` made (`source.cloned` is not `true`), so nothing "
            "clones it again")
#: `plan-source-gone`'s way out, which names no recorded `org/repo`: the
#: plan does not record the host a clone's `origin` named (#652's N4).
GONE_REMEDY = ("Remediation: pass the source again with --source: the path "
               "its clone is at now; or, where `plan` cloned it from GitHub, "
               "the `org/repo` it cloned, which clones it again. Either is "
               "held to the plan's `commit:`.")
MINE = "mine\n"
MARKER = "mine.txt"
#: What `source-unresolvable` says of a `--source` that names nothing, and
#: of a url that names no repository on GitHub.
NEITHER = "is neither a path that exists nor an `org/repo` name"
NO_OWNER_REPO = "names no `owner/repo` on github.com"


def run(adopter, capsys, *argv: str) -> tuple[int, str, str]:
    """`adopt-project.py <argv>` in this process: its exit, stdout, stderr."""
    capsys.readouterr()
    code = adopter.main(list(argv))
    said = capsys.readouterr()
    return code, said.out, said.err


def plan_args(source: str, out: Path, *extra: str) -> list[str]:
    """`plan --source <source>` writing `out`."""
    return [PLAN_VERB, SOURCE_FLAG, source, *PLANNED, OUT, str(out), *extra]


def on_github(adopter, monkeypatch, tmp_path: Path) -> list:
    """`gh repo clone` stood in for, `testorg/Thing` found: its calls."""
    return gh_clones(adopter, monkeypatch, make_source_repo(
        tmp_path / "github" / PROJECT, tree=SMALL_TREE, edits=()))


def here_beside_a_directory_of_that_name(monkeypatch, tmp_path: Path):
    """The current directory, holding `./testorg/Thing`: a repository of
    another history than the one on GitHub."""
    here = tmp_path / "here"
    make_source_repo(here / ORG / PROJECT,
                     tree={**SMALL_TREE, "LOCAL.md": "local\n"}, edits=())
    monkeypatch.chdir(here)


def edited(plan: Path, old: bytes, new: bytes) -> None:
    """The plan with its one `old` replaced, as a person edits it."""
    text = plan.read_bytes()
    assert text.count(old) == 1, old
    plan.write_bytes(text.replace(old, new))


def clone_dir(work: Path) -> Path:
    """Where `Source.clone` clones `testorg/Thing` in `work`."""
    return Path(os.path.realpath(work)) / SOURCE_READONLY / PROJECT


def writable(path: Path) -> Path:
    """`path`, made writable: git writes its packs read-only."""
    os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    return path


def contents_out(clone: Path) -> None:
    """Everything in `clone` removed, the directory kept."""
    for child in clone.iterdir():
        if child.is_dir():
            rmtree(child)
        else:
            writable(child).unlink()


def files_out(clone: Path) -> None:
    """Every file in `clone` removed, every directory kept: what macOS's
    temp cleaner leaves."""
    for top, _, files in os.walk(clone):
        for name in files:
            writable(Path(top) / name).unlink()


def packs_out(clone: Path) -> None:
    """The clone's packs removed: it no longer holds any commit."""
    for pack in (clone / ".git" / "objects" / "pack").iterdir():
        writable(pack).unlink()


def head_out(clone: Path) -> None:
    (clone / ".git" / "HEAD").unlink()


# --- L1-24: a name that is also a path here --------------------------------

@pytest.mark.parametrize("command", [PLAN_VERB, CHECK, EXECUTE])
def test_a_name_that_is_also_a_path_here_is_refused_naming_both(
        adopter, monkeypatch, capsys, tmp_path, command):
    """Neither is guessed: on main the directory won, and was planned, or
    read by `check` and `execute` as the source. Nothing is cloned, and no
    plan is written."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    here_beside_a_directory_of_that_name(monkeypatch, tmp_path)
    again = tmp_path / "again.yaml"
    argv = (plan_args(REPOSITORY, again) if command == PLAN_VERB else
            [command, PLAN_FLAG, str(planned.plan), SOURCE_FLAG, REPOSITORY])
    code, _, err = run(adopter, capsys, *argv)
    assert code == 2, err
    assert err.splitlines()[:2] == [
        f"{AMBIGUOUS}--source {REPOSITORY!r} names both the path "
        f"`./{REPOSITORY}` here and the GitHub repository `{REPOSITORY}`",
        f"Remediation: pass `./{REPOSITORY}`, or its absolute path, to read "
        f"that directory in place; or `https://github.com/{REPOSITORY}` to "
        "clone the repository from GitHub."]
    assert len(planned.calls) == 1
    assert not again.exists()


def test_each_spelling_the_refusal_names_reads_what_it_says(
        adopter, monkeypatch, capsys, tmp_path):
    """`./testorg/Thing` reads the directory and records no clone; the url
    clones the repository and records that `plan` made it."""
    calls = on_github(adopter, monkeypatch, tmp_path)
    here_beside_a_directory_of_that_name(monkeypatch, tmp_path)
    local, cloned = tmp_path / "local.yaml", tmp_path / "cloned.yaml"
    work = str(tmp_path / WORK)
    assert run(adopter, capsys, *plan_args(f"./{REPOSITORY}", local,
                                           WORK_FLAG, work))[0] == 0
    assert recorded(local)["cloned"] is False
    assert calls == []
    assert run(adopter, capsys, *plan_args(f"https://github.com/{REPOSITORY}",
                                           cloned, WORK_FLAG, work))[0] == 0
    assert recorded(cloned)["cloned"] is True
    assert [call[:4] for call in calls] == [CLONE]


def test_a_recorded_repository_is_cloned_again_wherever_check_runs(
        adopter, monkeypatch, capsys, tmp_path):
    """The plan's repository is a name on GitHub: where its clone is gone,
    it is cloned again, and a directory of that name here is not read."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    rmtree(Path(planned.clone))
    here_beside_a_directory_of_that_name(monkeypatch, tmp_path)
    code, out, err = run(adopter, capsys, CHECK, PLAN_FLAG, str(planned.plan))
    assert code == 0, err
    assert [call[:4] for call in planned.calls] == [CLONE, CLONE]
    assert ("is cloned again from GitHub, as `plan` cloned it." in out), out


# --- L1-43: one name, however it is spelled ---------------------------------

SPELLINGS = {
    "trailing-slash": f"{REPOSITORY}/",
    "trailing-slashes": f"{REPOSITORY}//",
    "double-slash": f"{ORG}//{PROJECT}",
    "dot-git": f"{REPOSITORY}.git",
    "url": f"https://github.com/{REPOSITORY}",
    "url-dot-git-slash": f"https://github.com/{REPOSITORY}.git/",
    "url-upper-case": f"HTTPS://GitHub.com/{REPOSITORY}",
    "scp": f"git@github.com:{REPOSITORY}.git",
    "no-scheme": f"github.com/{REPOSITORY}",
    # #796's L1-101: GitHub's own host, as a browser's address bar spells it.
    # On main the url was refused as a repository on another host, and the
    # form with no scheme as neither a path nor a name.
    "www-url": f"https://www.github.com/{REPOSITORY}",
    "www-no-scheme": f"WWW.GitHub.com/{REPOSITORY}",
    # `.git` dropped in any case, as `.git` is (#831's review, F2).
    "dot-git-upper-case": f"{REPOSITORY}.GIT",
}


@pytest.mark.parametrize("spec", list(SPELLINGS.values()), ids=list(SPELLINGS))
def test_each_spelling_of_a_name_is_cloned_and_recorded_as_owner_repo(
        adopter, monkeypatch, capsys, tmp_path, spec):
    """`gh` is handed `testorg/Thing` and nothing else, the clone is
    `source-readonly/Thing`, and the plan records the name. On main each
    was handed to `gh` as typed; a trailing `/` cloned into
    `source-readonly/` itself; and none of them wrote a plan."""
    calls = on_github(adopter, monkeypatch, tmp_path)
    work, plan = tmp_path / WORK, tmp_path / PLAN
    code, _, err = run(adopter, capsys, *plan_args(spec, plan, WORK_FLAG,
                                                   str(work)))
    assert code == 0, err
    assert calls == [[*CLONE, str(clone_dir(work)), "--", "--quiet"]]
    assert recorded(plan)["repository"] == REPOSITORY


NAMES_NO_REPOSITORY = {
    "another-host": (f"https://gitlab.com/{REPOSITORY}",
                     "names a repository on gitlab.com, and `gh repo clone` "
                     "clones from github.com alone"),
    "three-segments": (f"a/{REPOSITORY}",
                       "is neither a path that exists nor an `org/repo` name"),
    # #796's L1-100: a repository named `.git`, which `gh` was handed, to
    # clone into `source-readonly/.git`, and refused `source-unclonable`
    # with a remedy about `gh auth status`.
    "dot-git-repository": (f"{ORG}/.git", NEITHER),
    # ... in any case, as GitHub and a disk that ignores case read it (#831's
    # review, F2): on main and before it, `gh` was handed each of these.
    "dot-git-upper-case": (f"{ORG}/.GIT", NEITHER),
    "dot-git-mixed-case": (f"{ORG}/.Git.git", NEITHER),
    "url-dot-git-repository": (f"https://github.com/{ORG}/.git.git",
                               NO_OWNER_REPO),
    # Controls: `.` and `..` name no repository either, whatever `.git`
    # follows them, as since #652.
    "dot-dot-git-repository": (f"{ORG}/..git", NEITHER),
    "url-dot-dot-repository": (f"https://github.com/{ORG}/..", NO_OWNER_REPO),
}


@pytest.mark.parametrize(("spec", "words"), list(NAMES_NO_REPOSITORY.values()),
                         ids=list(NAMES_NO_REPOSITORY))
def test_a_source_that_names_no_github_repository_never_reaches_gh(
        adopter, monkeypatch, capsys, tmp_path, spec, words):
    """On main both were handed to `gh repo clone`, the second as
    `HOST/OWNER/REPO`, and refused with a remedy about `gh auth status`."""
    calls = gh_clones(adopter, monkeypatch, tmp_path / "nowhere")
    code, _, err = run(adopter, capsys, *plan_args(
        spec, tmp_path / PLAN, WORK_FLAG, str(tmp_path / WORK)))
    assert code == 2
    assert err.startswith(f"{UNRESOLVABLE}--source {spec!r} {words}\n"), err
    assert calls == []


def test_a_recorded_name_with_a_trailing_slash_is_cloned_by_its_name(
        adopter, monkeypatch, capsys, tmp_path):
    """A plan whose `repository:` was written `testorg/Thing/`, by hand: no
    run of `plan` writes one."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    edited(planned.plan, f"  repository: {REPOSITORY}\n".encode(),
           f"  repository: {REPOSITORY}/\n".encode())
    rmtree(Path(planned.clone))
    code, _, err = run(adopter, capsys, CHECK, PLAN_FLAG, str(planned.plan))
    assert code == 0, err
    assert [call[:4] for call in planned.calls] == [CLONE, CLONE]


# --- L1-22, L1-27: a path given to `plan`, gone -----------------------------

ORIGINS = {"no-origin": None,
           "github": f"https://github.com/{REPOSITORY}.git",
           "gitlab": f"https://gitlab.com/{REPOSITORY}.git"}


@pytest.mark.parametrize("command", [CHECK, EXECUTE])
@pytest.mark.parametrize("origin", list(ORIGINS.values()), ids=list(ORIGINS))
def test_a_path_given_to_plan_that_is_gone_is_refused_and_never_cloned(
        adopter, monkeypatch, capsys, tmp_path, origin, command):
    """Named by its key, with no word of `gh`, and `--source` as the way
    past it, naming no recorded `org/repo` as GitHub's. On main the path
    itself went to `gh repo clone`, or the `origin`'s name was cloned from
    github.com, a gitlab clone's too."""
    calls = gh_clones(adopter, monkeypatch, tmp_path / "nowhere")
    source = make_source_repo(tmp_path / "src" / PROJECT, tree=SMALL_TREE,
                              edits=())
    if origin is not None:
        git("remote", "add", "origin", origin, cwd=source)
    plan, work = tmp_path / PLAN, str(tmp_path / WORK)
    assert run(adopter, capsys, *plan_args(str(source), plan,
                                           WORK_FLAG, work))[0] == 0
    local_path = recorded(plan)["local_path"]
    rmtree(source)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    code, _, err = run(adopter, capsys, command, PLAN_FLAG, str(plan),
                       WORK_FLAG, work)
    assert code == 2, err
    assert err.splitlines()[:2] == [
        f"{GONE_REFUSED}the plan's `source.local_path`, {spelled(local_path)},"
        f" {NOT_MADE}", GONE_REMEDY]
    assert calls == []


def test_a_recorded_drive_letter_path_that_is_not_there_is_named_by_its_key(
        adopter, monkeypatch, capsys, tmp_path):
    """What Windows met: the refusal named `--source`, which nobody passed."""
    gh_clones(adopter, monkeypatch, tmp_path / "nowhere")
    source = make_source_repo(tmp_path / PROJECT, tree=SMALL_TREE, edits=())
    plan = tmp_path / PLAN
    assert run(adopter, capsys, *plan_args(str(source), plan, WORK_FLAG,
                                           str(tmp_path / WORK)))[0] == 0
    drive = "D:\\work\\Thing"
    edited(plan, f"  local_path: {adopter.y(recorded(plan)['local_path'])}"
           .encode(), f"  local_path: {adopter.y(drive)}".encode())
    code, _, err = run(adopter, capsys, CHECK, PLAN_FLAG, str(plan))
    assert code == 2
    assert err.startswith(f"{GONE_REFUSED}the plan's `source.local_path`, "
                          f"{spelled(drive)}, {NOT_MADE}\n"), err


def test_a_clone_plan_made_that_records_no_repository_is_refused_when_gone(
        adopter, monkeypatch, capsys, tmp_path):
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    edited(planned.plan, f"  repository: {REPOSITORY}\n".encode(),
           b"  repository: null\n")
    rmtree(Path(planned.clone))
    code, _, err = run(adopter, capsys, CHECK, PLAN_FLAG, str(planned.plan))
    assert code == 2
    assert err.startswith(
        f"{GONE_REFUSED}the plan's `source.local_path`, "
        f"{spelled(planned.clone)}, no longer exists, and the plan records no "
        "`source.repository` to clone again\n"), err
    assert len(planned.calls) == 1


def test_a_plan_that_records_no_clone_is_never_cloned_again(
        adopter, monkeypatch, capsys, tmp_path):
    """A plan written before `cloned:` was recorded, as main writes one:
    its path may be one the person gave, so it is refused, never cloned."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    edited(planned.plan, b"  cloned: true\n", b"")
    rmtree(Path(planned.clone))
    code, _, err = run(adopter, capsys, CHECK, PLAN_FLAG, str(planned.plan))
    assert code == 2
    assert err.startswith(f"{GONE_REFUSED}the plan's `source.local_path`, "
                          f"{spelled(planned.clone)}, {NOT_MADE}\n"), err
    assert len(planned.calls) == 1


# --- L1-26: a clone `plan` made, broken --------------------------------------

CLEANINGS = {"contents": (contents_out, NO_REPOSITORY),
             "files": (files_out, NO_REPOSITORY),
             "packs": (packs_out, NO_COMMIT),
             "head": (head_out, NO_REPOSITORY)}


@pytest.mark.parametrize(("clean", "why"), list(CLEANINGS.values()),
                         ids=list(CLEANINGS))
def test_a_clone_plan_made_that_a_cleaner_broke_is_cloned_again(
        adopter, monkeypatch, capsys, tmp_path, clean, why):
    """On main each was refused `git-failed`. git is kept from looking above
    the clone, as it would in a temp folder no repository holds."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    clone = Path(planned.clone)
    clean(clone)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(clone.parent))
    code, out, err = run(adopter, capsys, CHECK, PLAN_FLAG, str(planned.plan))
    assert code == 0, err
    [note] = [line for line in out.splitlines() if line.startswith(GONE)]
    assert note.startswith(f"{GONE}{spelled(clone)}, {NOT_WHOLE}{why}"), note
    assert [call[:4] for call in planned.calls] == [CLONE, CLONE]


def test_an_emptied_clone_inside_another_repository_is_never_read_as_it(
        adopter, monkeypatch, capsys, tmp_path):
    """git reads an emptied clone as the repository around it: on main
    `check` read that one, until a `git ls-remote` of the path failed."""
    calls = on_github(adopter, monkeypatch, tmp_path)
    enclosing = make_source_repo(tmp_path / "enclosing",
                                 tree={"OUTER.md": "outer\n"}, edits=())
    plan = tmp_path / PLAN
    assert run(adopter, capsys, *plan_args(
        REPOSITORY, plan, WORK_FLAG, str(enclosing / WORK)))[0] == 0
    contents_out(Path(recorded(plan)["local_path"]))
    code, out, err = run(adopter, capsys, CHECK, PLAN_FLAG, str(plan))
    outer = git("rev-parse", "HEAD", cwd=enclosing).stdout.strip()
    assert code == 0, err
    assert f"{NOT_WHOLE}git reads it as part of the repository at " in out
    assert outer[:12] not in out + err
    assert len(calls) == 2


def test_the_plans_own_clone_broken_in_its_work_dir_is_refused_and_kept(
        adopter, monkeypatch, capsys, tmp_path):
    """Given the `--work-dir` `plan` was given, `check` would clone again
    where the broken clone is: it says so, before any NOTE, and removes
    nothing there."""
    calls = on_github(adopter, monkeypatch, tmp_path)
    work, plan = tmp_path / WORK, tmp_path / PLAN
    assert run(adopter, capsys, *plan_args(REPOSITORY, plan, WORK_FLAG,
                                           str(work)))[0] == 0
    clone = Path(recorded(plan)["local_path"])
    packs_out(clone)
    code, out, err = run(adopter, capsys, CHECK, PLAN_FLAG, str(plan),
                         WORK_FLAG, str(work))
    assert code == 2
    assert err.startswith(f"{OCCUPIED}the plan's `source.local_path`, "
                          f"{spelled(clone)}, {NOT_WHOLE}{NO_COMMIT}"), err
    assert ("Remediation: It is no longer a whole clone: delete "
            f"`{SOURCE_READONLY}/{PROJECT}` and run the command again") in err
    assert GONE not in out
    assert (clone / ".git" / "HEAD").is_file()
    assert len(calls) == 1


def test_the_plans_own_clone_made_again_in_its_work_dir_is_kept(
        adopter, monkeypatch, capsys, tmp_path):
    """A clone made again where the plan records it is the plan's source
    again: kept, and the next `check` reads it with no clone."""
    calls = on_github(adopter, monkeypatch, tmp_path)
    work, plan = tmp_path / WORK, tmp_path / PLAN
    assert run(adopter, capsys, *plan_args(REPOSITORY, plan, WORK_FLAG,
                                           str(work)))[0] == 0
    rmtree(clone_dir(work))
    argv = (CHECK, PLAN_FLAG, str(plan), WORK_FLAG, str(work))
    assert run(adopter, capsys, *argv)[0] == 0
    assert (clone_dir(work) / ".git").is_dir()
    assert run(adopter, capsys, *argv)[0] == 0
    assert len(calls) == 2


# --- L1-23: a clone no plan records is removed -------------------------------

@pytest.mark.parametrize("gone", [False, True], ids=["source", "plan-clone-gone"])
def test_check_removes_the_clone_it_made(adopter, monkeypatch, capsys,
                                         tmp_path, gone):
    """`check --source <org/repo>`, and `check` where the plan's clone is
    gone: on main each left its clone in the system temp folder."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    if gone:
        rmtree(Path(planned.clone))
    temporary = in_a_fresh_temp_folder(monkeypatch, tmp_path / "check-temp")
    extra = () if gone else (SOURCE_FLAG, REPOSITORY)
    code, _, err = run(adopter, capsys, CHECK, PLAN_FLAG, str(planned.plan),
                       *extra)
    assert code == 0, err
    assert len(planned.calls) == 2
    assert left_in(temporary) == []


@pytest.mark.parametrize("given", [False, True], ids=["temp", WORK_FLAG])
def test_a_plan_refused_after_its_clone_removes_it(adopter, monkeypatch,
                                                   capsys, tmp_path, given):
    """No plan records it: on main it stayed, in the temp folder or in the
    `--work-dir`, where the next `plan` given it was refused at the clone.
    The refusal is the write's own, a plan that cannot be written after the
    whole plan is built: `--project Wrong` stood here, and is
    `adopt-not-the-source` before the clone since #903."""
    calls = on_github(adopter, monkeypatch, tmp_path)
    temporary = in_a_fresh_temp_folder(monkeypatch, tmp_path / "plan-temp")
    work = tmp_path / WORK

    def cannot_write(_path, _text):
        raise OSError(errno.ENAMETOOLONG, os.strerror(errno.ENAMETOOLONG))

    monkeypatch.setattr(adopter, "write_lf", cannot_write)
    code, _, err = run(adopter, capsys, PLAN_VERB, SOURCE_FLAG, REPOSITORY,
                       *PLANNED, OUT, str(tmp_path / PLAN),
                       *((WORK_FLAG, str(work)) if given else ()))
    assert code == 2
    assert "REFUSED adopt-out-unwritable: " in err
    assert len(calls) == 1
    assert left_in(temporary) == []
    assert not os.path.lexists(work / SOURCE_READONLY)


def test_execute_given_the_work_dir_check_was_given_clones_there(
        adopter, monkeypatch, capsys, tmp_path):
    """`check --work-dir W`, then `execute --work-dir W`, as `check`'s help
    says: on main `execute` was refused at the clone `check` left, as
    `source-unclonable`. What the person keeps in W stays."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    work = tmp_path / WORK
    work.mkdir()
    (work / MARKER).write_text(MINE, encoding="utf-8")
    given = (PLAN_FLAG, str(planned.plan), SOURCE_FLAG, REPOSITORY,
             WORK_FLAG, str(work))
    assert run(adopter, capsys, CHECK, *given)[0] == 0
    code, _, err = run(adopter, capsys, EXECUTE, *given, LOCAL_REMOTE_DIR,
                       str(tmp_path / REMOTES))
    assert code == 2
    assert "REFUSED adopt-unconfirmed: " in err
    assert len(planned.calls) == 3
    assert (work / MARKER).read_text(encoding="utf-8") == MINE


def test_check_of_a_local_source_leaves_it_and_its_work_dir_alone(
        adopter, monkeypatch, capsys, tmp_path):
    """A path the person passed is read in place and never removed, and a
    `--work-dir` keeps what they put in it."""
    gh_clones(adopter, monkeypatch, tmp_path / "nowhere")
    source = make_source_repo(tmp_path / PROJECT, tree=SMALL_TREE, edits=())
    plan, work = tmp_path / PLAN, tmp_path / WORK
    work.mkdir()
    (work / MARKER).write_text(MINE, encoding="utf-8")
    assert run(adopter, capsys, *plan_args(str(source), plan, WORK_FLAG,
                                           str(work)))[0] == 0
    assert run(adopter, capsys, CHECK, PLAN_FLAG, str(plan), SOURCE_FLAG,
               str(source), WORK_FLAG, str(work))[0] == 0
    assert sorted(os.listdir(work)) == [MARKER]
    assert (source / ".git").is_dir()


def test_plan_into_a_work_dir_holding_its_clone_is_refused_by_name(
        adopter, monkeypatch, capsys, tmp_path):
    """The plan written first records the clone there, so it stays; on main
    the second `plan` was refused `source-unclonable`, with a remedy about
    `gh auth status`."""
    calls = on_github(adopter, monkeypatch, tmp_path)
    work = tmp_path / WORK
    assert run(adopter, capsys, *plan_args(REPOSITORY, tmp_path / PLAN,
                                           WORK_FLAG, str(work)))[0] == 0
    code, _, err = run(adopter, capsys, *plan_args(
        REPOSITORY, tmp_path / "again.yaml", WORK_FLAG, str(work)))
    assert code == 2
    assert err == (
        f"{OCCUPIED}--work-dir {spelled(os.path.realpath(work))} already "
        f"holds `{SOURCE_READONLY}/{PROJECT}`, where this run clones "
        f"{REPOSITORY}, and `git clone` clones only into a directory that is "
        "new or empty\nRemediation: Pass a --work-dir that does not hold it, "
        "or none: without one, each run makes a new one.\n")
    assert len(calls) == 1
    assert (clone_dir(work) / ".git").is_dir()


def test_a_clone_reached_through_a_symlink_is_never_removed(
        adopter, monkeypatch, capsys, tmp_path):
    """Nothing outside the work directory's own `source-readonly/` goes: a
    `source-readonly` that is a symlink leads somewhere else, so no clone
    is made through it (#803). Until #803 the clone was made there and
    kept, and nothing said so (#457's L1-99 (a)); the link's target is
    named."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    work, elsewhere = tmp_path / WORK, tmp_path / "elsewhere"
    work.mkdir()
    elsewhere.mkdir()
    try:
        os.symlink(elsewhere, work / SOURCE_READONLY, target_is_directory=True)
    except OSError:
        pytest.skip("this machine makes no symlink")
    code, _, err = run(adopter, capsys, CHECK, PLAN_FLAG, str(planned.plan),
                       SOURCE_FLAG, REPOSITORY, WORK_FLAG, str(work))
    assert code == 2, err
    assert err.startswith(
        f"{OCCUPIED}--work-dir {spelled(os.path.realpath(work))} already "
        f"holds `{SOURCE_READONLY}`, a symlink to {spelled(elsewhere)}, where "
        f"this run clones {REPOSITORY} into a directory of its own\n"), err
    assert len(planned.calls) == 1
    assert os.listdir(elsewhere) == []


def test_a_clone_is_removed_where_a_read_only_file_cannot_be_unlinked(
        adopter, monkeypatch, capsys, tmp_path):
    """Windows refuses to unlink a read-only file, and git writes a clone's
    packs read-only: emulated here, the clone still goes."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    assert any(not path.stat().st_mode & stat.S_IWRITE
               for path in Path(planned.clone).rglob("*") if path.is_file())
    temporary = in_a_fresh_temp_folder(monkeypatch, tmp_path / "check-temp")
    unlink = os.unlink

    def as_windows(path, *, dir_fd=None):
        if not os.lstat(path, dir_fd=dir_fd).st_mode & stat.S_IWRITE:
            raise PermissionError(errno.EACCES, "Access is denied", path)
        unlink(path, dir_fd=dir_fd)

    monkeypatch.setattr(os, "unlink", as_windows)
    monkeypatch.setattr(os, "remove", as_windows)
    # Nor, as on Windows, any removal by descriptor (#803).
    monkeypatch.setattr(adopter, "FD_REMOVAL", False, raising=False)
    code, _, err = run(adopter, capsys, CHECK, PLAN_FLAG, str(planned.plan),
                       SOURCE_FLAG, REPOSITORY)
    assert code == 0, err
    assert left_in(temporary) == []


# --- what the removal never does (#652's review, F1, F2, F4) -----------------

#: How the NOTE for a clone the run could not remove begins.
KEPT = "NOTE the clone this run made, "


def then(adopter, monkeypatch, act) -> None:
    """`act(clone)` right after `gh repo clone` has made the clone."""
    inner = adopter.run

    def and_then(args, *rest, **keywords):
        done = inner(args, *rest, **keywords)
        if args[0] == "gh":
            act(Path(args[4]))
        return done

    monkeypatch.setattr(adopter, "run", and_then)


def symlinks_are_made(base: Path) -> None:
    """Skip where this machine makes no directory symlink: one is tried in
    `base`."""
    (base / "link-probe").mkdir()
    try:
        os.symlink(base / "link-probe", base / "link-probe-link",
                   target_is_directory=True)
    except OSError:
        pytest.skip("this machine makes no symlink")


def test_a_work_dir_swapped_for_a_symlink_during_the_run_loses_nothing(
        adopter, monkeypatch, capsys, tmp_path):
    """The work directory is moved aside and replaced by a symlink to
    another directory after the clone: the removal is of the real path the
    clone had, so nothing the symlink leads to goes. Before the review the
    run removed `elsewhere/source-readonly/Thing`, a file in it, and
    `elsewhere/source-readonly/` itself (r652's S1a)."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    symlinks_are_made(tmp_path)
    work, aside = tmp_path / WORK, tmp_path / "aside"
    precious = tmp_path / "elsewhere" / SOURCE_READONLY / PROJECT / MARKER
    precious.parent.mkdir(parents=True)
    precious.write_text(MINE, encoding="utf-8")

    def swapped(_clone: Path):
        os.rename(work, aside)
        os.symlink(tmp_path / "elsewhere", work, target_is_directory=True)
        raise adopter.CommandFailed(["gh"], None, 1, "swapped")

    then(adopter, monkeypatch, swapped)
    code, _, err = run(adopter, capsys, CHECK, PLAN_FLAG, str(planned.plan),
                       SOURCE_FLAG, REPOSITORY, WORK_FLAG, str(work))
    assert code == 2, err
    assert precious.read_text(encoding="utf-8") == MINE
    assert (aside / SOURCE_READONLY / PROJECT / ".git").is_dir()


def test_a_plan_cut_short_after_it_is_written_keeps_its_clone(
        adopter, monkeypatch, capsys, tmp_path):
    """The plan that records the clone is written before its report is
    printed, and a report cut short (a closed pipe, Ctrl-C) removed the
    clone that plan records, and an `--out` the person put in it (r652's
    S3b)."""
    on_github(adopter, monkeypatch, tmp_path)
    work = tmp_path / WORK
    out = clone_dir(work) / "my-plan.yaml"

    def cut_short(*_args, **_keywords):
        raise RuntimeError("the report is cut short")

    monkeypatch.setattr(adopter, "_print_plan_report", cut_short)
    argv = plan_args(REPOSITORY, out, WORK_FLAG, str(work))
    with pytest.raises(RuntimeError, match="cut short"):
        adopter.main(argv)
    assert out.is_file()
    assert (clone_dir(work) / ".git").is_dir()


@pytest.fixture
def modes_hold(tmp_path):
    """Skip where a directory's mode does not stop this user: as root, or
    on Windows, where it is never asked."""
    probe = tmp_path / "w652-mode-probe"
    probe.mkdir()
    os.chmod(probe, 0o555)
    try:
        holds = not os.access(probe, os.W_OK)
    finally:
        os.chmod(probe, 0o755)
    if not holds:
        pytest.skip("a directory's mode does not stop this user")


def modes_under(clone: Path) -> dict[Path, int]:
    """The mode of every directory in `clone`."""
    return {path: stat.S_IMODE(path.lstat().st_mode)
            for path in [clone, *clone.rglob("*")] if path.is_dir()}


UNREMOVABLE = {"unreadable": ("src/app", 0o000), "unwritable": ("src", 0o555)}


@pytest.mark.parametrize(("relative", "mode"), list(UNREMOVABLE.values()),
                         ids=list(UNREMOVABLE))
def test_a_clone_that_cannot_be_removed_is_named_and_no_mode_lowered(
        adopter, monkeypatch, capsys, tmp_path, modes_hold, relative, mode):
    """The run's exit is its own, a NOTE names the clone it keeps, and no
    directory loses a permission. Before the review a directory nobody can
    read ended `check` in a TypeError traceback from the removal's handler,
    exit 1; one nobody can write in was kept and nothing said so; and the
    handler set a mode to exactly `S_IWRITE` (r652's S1c, S1d)."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    in_a_fresh_temp_folder(monkeypatch, tmp_path / "check-temp")
    before: dict[Path, int] = {}

    def lock(clone: Path):
        before.update(modes_under(clone))
        os.chmod(clone / relative, mode)
        before[clone / relative] = mode

    then(adopter, monkeypatch, lock)
    try:
        code, _, err = run(adopter, capsys, CHECK, PLAN_FLAG,
                           str(planned.plan), SOURCE_FLAG, REPOSITORY)
        lowered = [path for path, was in before.items() if path.exists()
                   and was & ~stat.S_IMODE(path.lstat().st_mode)]
    finally:
        for path in before:
            if path.is_dir():
                os.chmod(path, 0o755)
    clone = os.path.realpath(min(before, key=lambda path: len(path.parts)))
    assert code == 0, err
    [note] = [line for line in err.splitlines() if line.startswith(KEPT)]
    assert note.startswith(f"{KEPT}{spelled(clone)}, is kept: removing it "
                           "failed ("), note
    assert note.endswith("Delete it once nothing in it is needed."), note
    assert lowered == []


def test_execute_into_a_work_dir_holding_its_clone_says_nothing_exists(
        adopter, monkeypatch, capsys, tmp_path):
    """`execute` keeps the clone it makes, so a re-run given its
    `--work-dir` meets it: refused as `execute`'s other early refusals are,
    saying that no leg repository exists yet, and what the occupant may
    be."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    work = tmp_path / WORK
    clone_dir(work).mkdir(parents=True)
    (clone_dir(work) / MARKER).write_text(MINE, encoding="utf-8")
    code, _, err = run(adopter, capsys, EXECUTE, PLAN_FLAG, str(planned.plan),
                       SOURCE_FLAG, REPOSITORY, WORK_FLAG, str(work),
                       LOCAL_REMOTE_DIR, str(tmp_path / REMOTES))
    assert code == 2, err
    assert err.splitlines()[1] == (
        "Remediation: no leg repository was created and nothing was pushed. "
        "Pass a --work-dir that does not hold it, or none: without one, each "
        "run makes a new one. An earlier `execute` given this --work-dir "
        "keeps the clone it made there: where that is what it holds, delete "
        "it once nothing in it is needed.")


# --- #796: a `--source` that names no repository's top level -----------------

NOT_TOP_LEVEL = "REFUSED source-not-top-level: "
#: What `source-not-top-level` says a source is, after what was given.
TOP_LEVEL_ONLY = "a source is the top-level directory of a repository"
#: Its way out, for a `--source` and a recorded `local_path` alike.
TOP_LEVEL_REMEDY = (
    "Remediation: pass --source the repository's top-level directory, which "
    "`git rev-parse --show-toplevel` prints in any directory of it, or its "
    "`org/repo`.")
README = "README.md"
#: A path inside the local source that is no top level: a file, a directory
#: of its work tree, a directory of its git directory.
INSIDE = {"file": README, "directory": "src", "git-directory": ".git/objects"}
#: A `~user` no machine running the suite has, which bash passes through as
#: typed, and `os.path.expanduser` leaves as typed.
NO_SUCH_USER = "~no-such-user-796/Thing"
#: The empty `--source`, as `--source "$SRC"` passes it with `SRC` unset.
EMPTY_REFUSED = [
    f"{UNRESOLVABLE}--source '' names no path: an empty one would be read "
    "as the directory this runs in",
    "Remediation: pass the repository's top-level directory (`.` for this "
    "directory), or its `org/repo`. Without --source, `check` and `execute` "
    "read the plan's own source."]
AGAIN = "again.yaml"


def local_source(tmp_path: Path) -> Path:
    """A clone of `testorg/Thing` on this machine: its `origin` names it."""
    source = make_source_repo(tmp_path / "local" / PROJECT, tree=SMALL_TREE,
                              edits=())
    git("remote", "add", "origin", f"https://github.com/{REPOSITORY}.git",
        cwd=source)
    return source


def no_github(adopter, monkeypatch, tmp_path: Path) -> list:
    """`gh repo clone` stood in for, finding nothing: its calls."""
    return gh_clones(adopter, monkeypatch, tmp_path / "nowhere")


def planned_here(adopter, monkeypatch, capsys,
                 tmp_path: Path) -> tuple[Path, Path, list]:
    """`(source, plan, gh calls)`: `plan` of `local_source`, in this
    process, with `gh repo clone` stood in for; stdin is no terminal, and
    `git filter-repo` is not asked for, as in `planned_from_github`:
    `execute` asks for it before it reads the source's tree, so without
    it on PATH a lost blob would never be reached."""
    calls = no_github(adopter, monkeypatch, tmp_path)
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    source = local_source(tmp_path)
    plan = tmp_path / PLAN
    code, _, err = run(adopter, capsys, *plan_args(
        str(source), plan, WORK_FLAG, str(tmp_path / WORK)))
    assert code == 0, err
    return source, plan, calls


def given_source(command: str, plan: Path, given: str,
                 tmp_path: Path) -> list[str]:
    """`command --source given`: `plan`, writing `AGAIN`; or `check` or
    `execute` of `plan`, given a `--local-remote-dir` in `tmp_path`."""
    if command == PLAN_VERB:
        return plan_args(given, tmp_path / AGAIN)
    return [command, PLAN_FLAG, str(plan), SOURCE_FLAG, given,
            *remotes(tmp_path)]


def remotes(tmp_path: Path) -> list[str]:
    """`--local-remote-dir`, in `tmp_path`: `execute` makes no `gh` call."""
    return [LOCAL_REMOTE_DIR, str(tmp_path / REMOTES)]


def nothing_was_made(tmp_path: Path, calls: list) -> None:
    """No plan written, no leg repository made, no `gh` run."""
    assert not (tmp_path / AGAIN).exists()
    assert not (tmp_path / REMOTES).exists()
    assert calls == []


def not_top_level(named: str, source: Path, inside: str) -> str:
    """The first line of `source-not-top-level` for `inside`, a path in
    `source`, which the refusal calls `named`."""
    if inside == INSIDE["file"]:
        return (f"{NOT_TOP_LEVEL}{named} is not a directory, and "
                f"{TOP_LEVEL_ONLY}")
    if inside == INSIDE["git-directory"]:
        return in_a_git_directory(named, source / ".git")
    return (f"{NOT_TOP_LEVEL}{named} is `{inside}/` inside the repository at "
            f"{spelled(os.path.realpath(source))}, and {TOP_LEVEL_ONLY}: read "
            f"from there, it would be only what is under `{inside}/`")


def in_a_git_directory(named: str, git_dir: Path) -> str:
    """The first line of `source-not-top-level` for a directory inside
    `git_dir`, which the refusal calls `named`."""
    return (f"{NOT_TOP_LEVEL}{named} is inside the git directory "
            f"{spelled(os.path.realpath(git_dir))}, and {TOP_LEVEL_ONLY}")


def local_path_now(adopter, plan: Path, value: str) -> None:
    """The plan's `source.local_path` edited to `value`, as a person may."""
    edited(plan, f"  local_path: {adopter.y(recorded(plan)['local_path'])}"
           .encode(), f"  local_path: {adopter.y(value)}".encode())


@pytest.mark.parametrize("command", [PLAN_VERB, CHECK, EXECUTE])
@pytest.mark.parametrize("inside", list(INSIDE.values()), ids=list(INSIDE))
def test_a_source_that_is_no_top_level_is_refused_by_name(
        adopter, monkeypatch, capsys, tmp_path, command, inside):
    """L1-64 and L1-88. On main a file ended each command in a
    `NotADirectoryError` traceback, exit 1; `plan` of a directory inside the
    repository planned only what is under it, exit 0, and `check` then
    refused `git-failed` and `execute` `adopt-remote-unreadable`. Now each
    is refused before git reads anything else in it."""
    source, plan, calls = planned_here(adopter, monkeypatch, capsys, tmp_path)
    given = str(source / inside)
    code, out, err = run(adopter, capsys,
                         *given_source(command, plan, given, tmp_path))
    assert code == 2, err
    assert err.splitlines() == [
        not_top_level(f"--source {given!r}", source, inside), TOP_LEVEL_REMEDY]
    assert out == ""
    nothing_was_made(tmp_path, calls)


@pytest.mark.parametrize("command", [CHECK, EXECUTE])
@pytest.mark.parametrize("inside", list(INSIDE.values()), ids=list(INSIDE))
def test_a_recorded_local_path_that_is_no_top_level_is_named_by_its_key(
        adopter, monkeypatch, capsys, tmp_path, command, inside):
    """A plan whose `local_path:` names a file or a directory inside the
    repository, as a plan main wrote for one does: on main the first ended
    in a traceback, and the second was read as the source."""
    source, plan, calls = planned_here(adopter, monkeypatch, capsys, tmp_path)
    value = str(source / inside)
    local_path_now(adopter, plan, value)
    code, _, err = run(adopter, capsys, command, PLAN_FLAG, str(plan),
                       *remotes(tmp_path))
    assert code == 2, err
    assert err.splitlines() == [not_top_level(
        f"the plan's `source.local_path`, {spelled(value)},", source, inside),
        TOP_LEVEL_REMEDY]
    nothing_was_made(tmp_path, calls)


def test_dot_in_a_directory_inside_the_repository_is_refused(
        adopter, monkeypatch, capsys, tmp_path):
    """L1-88: on main `plan --source .` run in `<repo>/src` planned what is
    under `src/`, exit 0."""
    calls = no_github(adopter, monkeypatch, tmp_path)
    source = local_source(tmp_path)
    monkeypatch.chdir(source / INSIDE["directory"])
    code, _, err = run(adopter, capsys, *plan_args(".", tmp_path / AGAIN))
    assert code == 2, err
    assert err.splitlines()[0] == not_top_level(
        "--source '.'", source, INSIDE["directory"])
    nothing_was_made(tmp_path, calls)


def git_directories(source: Path, tmp_path: Path) -> dict[str, Path]:
    """The git directories of `source`'s repository: its own `.git`, a bare
    clone of it, and a linked worktree's."""
    bare = tmp_path / "bare.git"
    git("clone", "-q", "--bare", str(source), str(bare), cwd=tmp_path)
    git("worktree", "add", "-q", str(tmp_path / "wt"), "-b", "wt", cwd=source)
    return {"dot-git": source / ".git", "bare": bare,
            "worktree": source / ".git" / "worktrees" / "wt"}


@pytest.mark.parametrize("which", ["dot-git", "bare", "worktree"])
def test_a_git_directory_itself_is_read_whole(adopter, monkeypatch, capsys,
                                              tmp_path, which):
    """The controls of #831's review, F1: a git directory is a repository's
    own, and is read whole, as on main."""
    calls = no_github(adopter, monkeypatch, tmp_path)
    given = git_directories(local_source(tmp_path), tmp_path)[which]
    plan = tmp_path / PLAN
    code, _, err = run(adopter, capsys, *plan_args(str(given), plan))
    assert code == 0, err
    assert recorded(plan)["local_path"] == os.path.realpath(given)
    assert calls == []


def test_a_directory_inside_a_bare_repository_is_refused(
        adopter, monkeypatch, capsys, tmp_path):
    """#831's review, F1: inside a git directory `--show-prefix` prints
    nothing, so `plan` planned the whole repository from `<bare>.git/refs`,
    exit 0, and recorded that directory, which `check` and `execute` could
    not read as a repository. `.git/objects` is in `INSIDE`."""
    calls = no_github(adopter, monkeypatch, tmp_path)
    bare = git_directories(local_source(tmp_path), tmp_path)["bare"]
    given = str(bare / "refs")
    code, _, err = run(adopter, capsys, *plan_args(given, tmp_path / AGAIN))
    assert code == 2, err
    assert err.splitlines() == [
        in_a_git_directory(f"--source {given!r}", bare), TOP_LEVEL_REMEDY]
    nothing_was_made(tmp_path, calls)


@pytest.mark.parametrize("command", [CHECK, EXECUTE])
def test_an_empty_recorded_local_path_is_refused_and_never_cloned(
        adopter, monkeypatch, capsys, tmp_path, command):
    """#831's review, F3, L1-96's cause in the plan: on main `if
    local_path:` read `local_path: ""` as none, and the plan's
    `source.repository` was cloned from GitHub, though `plan` made no clone
    of it."""
    _, plan, calls = planned_here(adopter, monkeypatch, capsys, tmp_path)
    local_path_now(adopter, plan, "")
    code, _, err = run(adopter, capsys, command, PLAN_FLAG, str(plan),
                       *remotes(tmp_path))
    assert code == 2, err
    assert err.splitlines()[:2] == [
        f"{GONE_REFUSED}the plan's `source.local_path` is empty: it names no "
        "path, and an empty path would be read as the directory this runs in",
        GONE_REMEDY]
    nothing_was_made(tmp_path, calls)


@pytest.mark.parametrize("dot", [False, True], ids=["top-level", "dot-there"])
def test_the_top_level_is_read_in_place(adopter, monkeypatch, capsys,
                                        tmp_path, dot):
    """The controls: the top-level directory, and `.` run there, plan the
    whole repository, read where it is, as on main."""
    calls = no_github(adopter, monkeypatch, tmp_path)
    source = local_source(tmp_path)
    if dot:
        monkeypatch.chdir(source)
    plan = tmp_path / PLAN
    code, _, err = run(adopter, capsys,
                       *plan_args("." if dot else str(source), plan))
    assert code == 0, err
    assert recorded(plan)["local_path"] == os.path.realpath(source)
    assert recorded(plan)["cloned"] is False
    assert calls == []


def test_the_source_line_names_the_directory_read_beside_its_repository(
        adopter, monkeypatch, capsys, tmp_path):
    """L1-88's rider: on main `plan` of a local directory said only the
    repository its `origin` names, so the line read the same whatever
    directory was read. A clone `plan` made is named by its repository."""
    source = local_source(tmp_path)
    calls = on_github(adopter, monkeypatch, tmp_path)
    assert source_line(adopter, capsys, str(source), tmp_path / PLAN) \
        .startswith(f"source     {os.path.realpath(source)} (origin: "
                    f"{REPOSITORY}) @ ")
    assert source_line(adopter, capsys, REPOSITORY, tmp_path / AGAIN) \
        .startswith(f"source     {REPOSITORY} @ ")
    assert len(calls) == 1


def source_line(adopter, capsys, spec: str, out: Path) -> str:
    """The `source` line of `plan --source spec`'s report."""
    code, said, err = run(adopter, capsys, *plan_args(spec, out))
    assert code == 0, err
    [line] = [line for line in said.splitlines()
              if line.startswith("source ")]
    return line


@pytest.mark.parametrize("command", [PLAN_VERB, CHECK, EXECUTE])
def test_an_unknown_user_in_the_source_is_unresolvable(
        adopter, monkeypatch, capsys, tmp_path, command):
    """L1-95. On main `Path.expanduser` raised `RuntimeError: Could not
    determine home directory.`, exit 1. One mistyped user name was enough."""
    _, plan, calls = planned_here(adopter, monkeypatch, capsys, tmp_path)
    code, _, err = run(adopter, capsys,
                       *given_source(command, plan, NO_SUCH_USER, tmp_path))
    assert code == 2, err
    assert err.startswith(
        f"{UNRESOLVABLE}--source {NO_SUCH_USER!r} {NEITHER}\n"), err
    nothing_was_made(tmp_path, calls)


@pytest.mark.parametrize("command", [CHECK, EXECUTE])
def test_a_recorded_path_under_an_unknown_user_is_gone(
        adopter, monkeypatch, capsys, tmp_path, command):
    """A path the person gave: on main `check` and `execute` ended in the
    same `RuntimeError` at `Plan._recorded_source`."""
    _, plan, calls = planned_here(adopter, monkeypatch, capsys, tmp_path)
    local_path_now(adopter, plan, NO_SUCH_USER)
    code, _, err = run(adopter, capsys, command, PLAN_FLAG, str(plan))
    assert code == 2, err
    assert err.splitlines()[:2] == [
        f"{GONE_REFUSED}the plan's `source.local_path`, "
        f"{spelled(NO_SUCH_USER)}, {NOT_MADE}", GONE_REMEDY]
    assert calls == []


def test_a_recorded_clone_under_an_unknown_user_is_cloned_again(
        adopter, monkeypatch, capsys, tmp_path):
    """A clone `plan` made, recorded under a path that is gone, is cloned
    again, as any clone of its that is gone is."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    local_path_now(adopter, planned.plan, NO_SUCH_USER)
    code, out, err = run(adopter, capsys, CHECK, PLAN_FLAG, str(planned.plan))
    assert code == 0, err
    assert f"{GONE}{spelled(NO_SUCH_USER)}, no longer exists, so its " in out
    assert [call[:4] for call in planned.calls] == [CLONE, CLONE]


@pytest.mark.parametrize("command", [PLAN_VERB, CHECK, EXECUTE])
def test_an_empty_source_names_no_path_and_is_refused(
        adopter, monkeypatch, capsys, tmp_path, command):
    """L1-96. On main `plan --source ''` run inside a repository planned that
    repository, exit 0, as `--source "$SRC"` did with `SRC` unset; `check`
    and `execute` dropped the value and read the plan's own source."""
    source, plan, calls = planned_here(adopter, monkeypatch, capsys, tmp_path)
    monkeypatch.chdir(source)
    code, _, err = run(adopter, capsys,
                       *given_source(command, plan, "", tmp_path))
    assert code == 2, err
    assert err.splitlines() == EMPTY_REFUSED
    nothing_was_made(tmp_path, calls)


def blob_lost(source: Path, path: str) -> None:
    """The blob of `path` at the source's tip removed from its object store,
    as a cleaner or a bad copy loses one."""
    oid = git("rev-parse", f"HEAD:{path}", cwd=source).stdout.strip()
    writable(source / ".git" / "objects" / oid[:2] / oid[2:]).unlink()


@pytest.mark.parametrize("command", [PLAN_VERB, CHECK, EXECUTE])
def test_a_source_that_lost_a_blob_is_refused_naming_it_and_git_fsck(
        adopter, monkeypatch, capsys, tmp_path, command):
    """L1-77. `git ls-tree -r -l` prints `BAD` for the size of a blob it
    cannot read and still exits 0: on main each command ended in a
    `ValueError` traceback at `Source.tree`, exit 1."""
    source, plan, calls = planned_here(adopter, monkeypatch, capsys, tmp_path)
    blob_lost(source, README)
    code, _, err = run(adopter, capsys,
                       *given_source(command, plan, str(source), tmp_path))
    assert code == 2, err
    first, remedy = err.splitlines()[:2]
    assert first.startswith("REFUSED git-failed: `git ls-tree -r -l -z "), err
    assert f" gives no size for `{README}`, " in first, err
    assert remedy.startswith(
        f"Remediation: run `git fsck` in {os.path.realpath(source)}: "), err
    nothing_was_made(tmp_path, calls)


# --- what `--help` says -------------------------------------------------------

@pytest.mark.parametrize(("command", "code"), [
    (PLAN_VERB, "source-ambiguous"), (CHECK, "plan-source-gone"),
    (EXECUTE, "plan-source-gone"),
    # #796: a path that is no repository's top level, and an empty value.
    (PLAN_VERB, "source-not-top-level"), (CHECK, "source-not-top-level"),
    (EXECUTE, "source-not-top-level"), (PLAN_VERB, "source-unresolvable")])
def test_the_source_help_names_its_refusal_whole_on_one_line(command, code):
    """`docs/cli.md` is grepped for the code a tool prints."""
    result = run_script(ADOPT, command, "--help", env=HELP_ENV)
    assert result.returncode == 0, result.stderr
    assert any(f"`{code}`" in line
               for line in option_lines(result.stdout, SOURCE_FLAG))
