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
NOT_MADE = ("names nothing that exists, and it is a path given to `plan`, "
            "not a clone `plan` made (`source.cloned` is not `true`), so "
            "nothing clones it again")
MINE = "mine\n"
MARKER = "mine.txt"


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
    past it, naming the plan's repository where it records one. On main the
    path itself went to `gh repo clone`, or the `origin`'s name was cloned
    from github.com, a gitlab clone's too."""
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
    again = f"`--source {REPOSITORY}`" if origin else "`--source <org>/<repo>`"
    assert code == 2, err
    assert err.splitlines()[:2] == [
        f"{GONE_REFUSED}the plan's `source.local_path`, {spelled(local_path)},"
        f" {NOT_MADE}",
        "Remediation: pass the source again with --source: the path of a "
        f"clone of it, or {again} to clone it from GitHub. Either is held to "
        "the plan's `commit:`."]
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
    `--work-dir`, where the next `plan` given it was refused at the clone."""
    calls = on_github(adopter, monkeypatch, tmp_path)
    temporary = in_a_fresh_temp_folder(monkeypatch, tmp_path / "plan-temp")
    work = tmp_path / WORK
    code, _, err = run(adopter, capsys, PLAN_VERB, SOURCE_FLAG, REPOSITORY,
                       "--project", "Wrong", *PLANNED[2:], OUT,
                       str(tmp_path / PLAN),
                       *((WORK_FLAG, str(work)) if given else ()))
    assert code == 2
    assert "REFUSED adopt-not-the-source: " in err
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
    `source-readonly` that is a symlink leads somewhere else."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    work, elsewhere = tmp_path / WORK, tmp_path / "elsewhere"
    work.mkdir()
    elsewhere.mkdir()
    try:
        os.symlink(elsewhere, work / SOURCE_READONLY, target_is_directory=True)
    except OSError:
        pytest.skip("this machine makes no symlink")
    assert run(adopter, capsys, CHECK, PLAN_FLAG, str(planned.plan),
               SOURCE_FLAG, REPOSITORY, WORK_FLAG, str(work))[0] == 0
    assert (elsewhere / PROJECT / ".git").is_dir()


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
    code, _, err = run(adopter, capsys, CHECK, PLAN_FLAG, str(planned.plan),
                       SOURCE_FLAG, REPOSITORY)
    assert code == 0, err
    assert left_in(temporary) == []


# --- what `--help` says -------------------------------------------------------

@pytest.mark.parametrize(("command", "code"), [
    (PLAN_VERB, "source-ambiguous"), (CHECK, "plan-source-gone"),
    (EXECUTE, "plan-source-gone")])
def test_the_source_help_names_its_refusal_whole_on_one_line(command, code):
    """`docs/cli.md` is grepped for the code a tool prints."""
    result = run_script(ADOPT, command, "--help", env=HELP_ENV)
    assert result.returncode == 0, result.stderr
    assert any(f"`{code}`" in line
               for line in option_lines(result.stdout, SOURCE_FLAG))
