# SPDX-License-Identifier: Apache-2.0
"""`adopt-project.py`: an `org/repo` GitHub cannot hold names no GitHub
repository, for every reader of the name (#1129, RV1122's NIT-1 on #1122).

GitHub gives a user or an organisation a name of at most 39 characters
(`GITHUB_OWNER_MAX`) and a repository one of at most 100 (`GITHUB_NAME_MAX`),
as `tests/test_github_name_limits.py` holds them. `_github_name`, the one
reading of an `owner/repo`, asked neither. AT #1122's HEAD c01c4d73
(2026-10-22), Python 3.12.3, uid 1000, with a `gh` first on PATH that logs
each call and refuses it, in an empty directory:

- `plan --source <50 b's>/Thing --org <50 b's>` asked `gh repo clone <50
  b's>/Thing` (1 call), and so did an owner of 40, a repository of 101 (or
  of 101 and `.git`), both at once, and `https://github.com/<40 c's>/Thing`;
- `plan --source <50 b's>/Thing --org testorg` was refused
  `adopt-not-the-source` and told to run `plan` again with `--org <50 b's>`,
  which `execute` refuses as `adopt-org-too-long`;
- a plan whose clone is gone and whose `source.repository` records such a
  name was cloned from it again by `check` and `execute`; a plan whose
  source names no repository was held to it, with the same `--org` for a
  remedy; and `--source <it>` given to either was cloned as `plan` clones it;
- a directory `./<40 c's>/Thing` here was `source-ambiguous`, as if the
  spelling also named a repository on GitHub.

Now `_github_name` gives no name for an owner over 39 or a repository over
100, counted once the `.git` is dropped, and every reader says so alike: the
spelling is a path, read in place where it is one and `source-unresolvable`
where it is not; a url of it names no `owner/repo` on github.com; and a plan's
record of it names no repository. `gh` is never asked. The rows at each limit
are the controls: still GitHub's names, still asked of `gh`.

A `github.com/` SPELLING PAST THE LIMITS NEVER REACHES THE DISK. #1122 refused
`github.com/<300 a's>/Thing` beside a `./github.com`, and `github.com/<40 a's>
/Thing` whose `stat` was refused, in `_source_there`, as a path is, with no
url. `_repository_in_url` refuses each first now, as a url that names no
`owner/repo`; those rows of tests/test_adopt_unsearchable_source.py are here,
with that answer.

POSIX ONLY. The `gh` each child runs is a `/bin/sh` script that logs its
arguments (`recording_gh`), put ahead of the suite's own guard; nothing here
reaches GitHub, and an `execute` is given `--local-remote-dir` throughout.
"""

from __future__ import annotations

import errno
import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, git, load_without_bytecode, make_source_repo,
                      run_script)
from test_adopt_project_is_the_source import edited
from test_adopt_temp_work_roots import (
    ORG, PROJECT, REPOSITORY, SMALL_TREE, needs_filter_repo, recorded,
)
from test_adopt_unsearchable_source import (
    LONG, assert_both_readings_and_the_url, planned_locally, recording_gh,
    refused_for, said, too_long_here,
)

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="the `gh` that logs each call is a /bin/sh script, and a part "
           "too long for the disk is a POSIX `stat`'s `File name too long`")


@pytest.fixture(scope="module")
def adopter():
    return load_without_bytecode(ADOPT, "adopt_source_github_limits")

#: What GitHub keeps an owner's name and a repository's to, as
#: tests/test_github_name_limits.py writes them.
OWNER_MAX, NAME_MAX = 39, 100
OWNER_AT, OWNER_OVER = "c" * OWNER_MAX, "c" * (OWNER_MAX + 1)
NAME_AT, NAME_OVER = "r" * NAME_MAX, "r" * (NAME_MAX + 1)
#: The issue's own owner.
ISSUE_OWNER = "b" * 50
URL = "https://github.com/"
#: How `_source_spec` refuses a spelling that is neither, and how
#: `_repository_in_url` refuses a url that names no `owner/repo`.
NEITHER = "is neither a path that exists nor an `org/repo` name"
NO_NAME_ON_GITHUB = "names no `owner/repo` on github.com"
UNRESOLVABLE = "REFUSED source-unresolvable: "

#: (`--source`, the owner and the repository GitHub would be asked for).
#: Each is a name GitHub can hold: `gh repo clone` is asked for it.
TAKEN = [
    pytest.param(f"{OWNER_AT}/{PROJECT}", OWNER_AT, PROJECT, id="owner-39"),
    pytest.param(f"{ORG}/{NAME_AT}", ORG, NAME_AT, id="repository-100"),
    pytest.param(f"{ORG}/{NAME_AT}.git", ORG, NAME_AT,
                 id="repository-100-dot-git"),
    pytest.param(f"{OWNER_AT}/{NAME_AT}", OWNER_AT, NAME_AT, id="both-at"),
    pytest.param(f"{URL}{OWNER_AT}/{PROJECT}", OWNER_AT, PROJECT,
                 id="url-owner-39"),
    pytest.param(f"github.com/{ORG}/{NAME_AT}", ORG, NAME_AT,
                 id="bare-url-repository-100"),
]
#: (`--source`, the owner and repository it spells, how it is refused).
#: Each is past a limit GitHub keeps: no `gh` call is made.
REFUSED = [
    pytest.param(f"{OWNER_OVER}/{PROJECT}", OWNER_OVER, PROJECT, NEITHER,
                 id="owner-40"),
    pytest.param(f"{ISSUE_OWNER}/{PROJECT}", ISSUE_OWNER, PROJECT, NEITHER,
                 id="owner-50"),
    pytest.param(f"{ORG}/{NAME_OVER}", ORG, NAME_OVER, NEITHER,
                 id="repository-101"),
    pytest.param(f"{ORG}/{NAME_OVER}.git", ORG, NAME_OVER, NEITHER,
                 id="repository-101-dot-git"),
    pytest.param(f"{OWNER_OVER}/{NAME_OVER}", OWNER_OVER, NAME_OVER, NEITHER,
                 id="both-over"),
    pytest.param(f"{URL}{OWNER_OVER}/{PROJECT}", OWNER_OVER, PROJECT,
                 NO_NAME_ON_GITHUB, id="url-owner-40"),
    pytest.param(f"{URL}{ORG}/{NAME_OVER}.git", ORG, NAME_OVER,
                 NO_NAME_ON_GITHUB, id="url-repository-101"),
    pytest.param(f"github.com/{OWNER_OVER}/{PROJECT}", OWNER_OVER, PROJECT,
                 NO_NAME_ON_GITHUB, id="bare-url-owner-40"),
    pytest.param(f"www.github.com/{ORG}/{NAME_OVER}", ORG, NAME_OVER,
                 NO_NAME_ON_GITHUB, id="www-url-repository-101"),
]


def cloned_by_gh(owner: str, repo: str, work: Path) -> str:
    """The one line the logging `gh` keeps for `plan`'s clone of
    `<owner>/<repo>` into `work`."""
    return (f"repo clone {owner}/{repo} {work / 'source-readonly' / repo} "
            "-- --quiet\n")


def planned(here: Path, tmp_path: Path, spec: str, project: str, org: str,
            env: dict):
    """`plan --source <spec> --project <project> --org <org>` in a child run
    in `here`, with its own plan file and work directory under `tmp_path`."""
    return run_script(ADOPT, "plan", "--source", spec, "--project", project,
                      "--org", org, "--elected-by", "Test Human",
                      "--elected-on", "2026-09-02", "--out",
                      str(tmp_path / "adoption-plan.yaml"), "--work-dir",
                      str(tmp_path / "work"), cwd=here, env=env)


# --- `plan --source`, with nothing here -------------------------------------

@pytest.mark.parametrize(("spec", "owner", "repo"), TAKEN)
def test_plan_asks_gh_for_a_name_github_can_hold(tmp_path, spec, owner,
                                                 repo):
    """The control: an owner of 39 and a repository of 100, as typed or in
    a url, are GitHub's names, and `gh repo clone` is asked for each, once,
    with the `.git` dropped. The logging `gh` refuses it, so `plan` ends in
    `source-unclonable` naming the repository."""
    here = tmp_path / "here"
    here.mkdir()
    env, log = recording_gh(tmp_path / "gh-bin")

    proc = planned(here, tmp_path, spec, repo, owner, env)

    assert log.read_text(encoding="utf-8") == cloned_by_gh(
        owner, repo, tmp_path / "work"), said(proc)
    assert proc.returncode == 2, said(proc)
    assert (f"REFUSED source-unclonable: could not clone {owner}/{repo}: "
            in proc.stderr), said(proc)


@pytest.mark.parametrize(("spec", "owner", "repo", "refused"), REFUSED)
def test_plan_never_asks_gh_for_a_name_github_cannot_hold(
        tmp_path, spec, owner, repo, refused):
    """The issue's first case: `plan --source <50 b's>/Thing --org <50 b's>`
    with nothing here asked `gh repo clone` for a name GitHub cannot hold,
    and so did an owner of 40, a repository of 101 and both, as typed or in
    a url. Now each names no GitHub repository: refused
    `source-unresolvable`, exit 2, with no `gh` call, no plan and no work
    directory. `--org` and `--project` are the spelling's own, so no other
    refusal comes first."""
    here = tmp_path / "here"
    here.mkdir()
    env, log = recording_gh(tmp_path / "gh-bin")

    proc = planned(here, tmp_path, spec, repo, owner, env)

    assert log.read_bytes() == b"", said(proc)
    assert proc.returncode == 2, said(proc)
    assert f"{UNRESOLVABLE}--source {spec!r} {refused}\n" in proc.stderr, \
        said(proc)
    assert "cloning " not in said(proc)
    assert not (tmp_path / "adoption-plan.yaml").exists()
    assert not (tmp_path / "work").exists()


@pytest.mark.parametrize(("written", "holder", "length", "code"), [
    pytest.param("github.com/{}/" + PROJECT, "github.com", len(LONG), None,
                 id="bare-url-too-long-for-the-disk"),
    pytest.param("www.github.com/{}/" + PROJECT, "www.github.com",
                 len(LONG), None, id="www-url-too-long-for-the-disk"),
    pytest.param("github.com/{}/" + PROJECT, None, OWNER_MAX + 1, errno.EIO,
                 id="bare-url-owner-40-EIO"),
    pytest.param("github.com/{}/" + PROJECT, None, OWNER_MAX + 1,
                 errno.EACCES, id="bare-url-owner-40-EACCES"),
])
def test_a_github_url_past_the_limits_is_refused_before_any_stat(
        adopter, monkeypatch, tmp_path, written, holder, length, code):
    """`github.com/<300 a's>/Thing` beside a `./github.com`, its `stat`
    `File name too long`, and `github.com/<40 a's>/Thing`, its `stat`
    refused for an I/O error or a permission: #1122 refused each in
    `_source_there`, as a path is, with no url. The spelling is a url, and
    names no `owner/repo` GitHub can hold, so `_repository_in_url` refuses
    it before the disk is asked, as it refuses any url that names none:
    `source-unresolvable`, with no url. The control: at GitHub's limit,
    its `stat` refused alike, it names a repository, both readings stay
    open and its url is offered (#430)."""
    monkeypatch.chdir(tmp_path)
    spec = written.format("a" * length)
    if holder is not None:
        (tmp_path / holder).mkdir()
        too_long_here(Path(spec))
    else:
        refused_for(monkeypatch, code)

    with pytest.raises(adopter.Refusal) as raised:
        adopter._source_spec(spec)

    refusal = raised.value
    assert (refusal.code, refusal.detail) == (
        "source-unresolvable", f"--source {spec!r} {NO_NAME_ON_GITHUB}")
    assert refusal.remediation == ("Remediation: pass a local clone's path, "
                                   "or `org/repo`.")

    refused_for(monkeypatch, code or errno.EIO)
    assert_both_readings_and_the_url(
        adopter, written.format("a" * OWNER_MAX),
        f"{'a' * OWNER_MAX}/{PROJECT}")


# --- the remedy that names `--org` ------------------------------------------

@pytest.mark.parametrize(("owner", "repo"), [
    pytest.param(OWNER_OVER, PROJECT, id="owner-40"),
    pytest.param(ISSUE_OWNER, PROJECT, id="owner-50"),
    pytest.param(OWNER_OVER, NAME_OVER, id="both-over"),
])
def test_no_remedy_offers_an_org_github_cannot_hold(tmp_path, owner, repo):
    """`plan --source <50 b's>/Thing --org testorg` was refused
    `adopt-not-the-source`, and told to run `plan` again with `--org <50
    b's>`, a name `execute` refuses as `adopt-org-too-long`. The spelling
    names no GitHub repository now, so it is not the source's name either:
    `source-unresolvable`, and no `--org` is offered. The control: an owner
    of 39 is still the source's own organisation, and the remedy names it."""
    here = tmp_path / "here"
    here.mkdir()
    env, log = recording_gh(tmp_path / "gh-bin")
    spec = f"{owner}/{repo}"

    proc = planned(here, tmp_path, spec, PROJECT, ORG, env)

    assert f"--org {owner}" not in said(proc), said(proc)
    assert "adopt-not-the-source" not in said(proc)
    assert proc.returncode == 2, said(proc)
    assert f"{UNRESOLVABLE}--source {spec!r} {NEITHER}\n" in proc.stderr
    assert log.read_bytes() == b""

    held = repo[:NAME_MAX]
    control = planned(here, tmp_path, f"{OWNER_AT}/{held}", PROJECT, ORG,
                      env)
    assert control.returncode == 2, said(control)
    assert "REFUSED adopt-not-the-source: " in control.stderr
    assert (f"Run `plan` again with `--project {held} --org {OWNER_AT}`, the "
            "source's own name,") in control.stderr, said(control)
    assert log.read_bytes() == b""


# --- `plan --source`, with a directory of that spelling here ----------------

@pytest.mark.parametrize(("owner", "repo"), [
    pytest.param(OWNER_OVER, PROJECT, id="owner-40"),
    pytest.param(ORG, NAME_OVER, id="repository-101"),
])
def test_a_directory_github_cannot_name_is_read_in_place(tmp_path, owner,
                                                          repo):
    """`./<40 c's>/Thing`, a repository here: `--source <40 c's>/Thing` was
    `source-ambiguous`, naming a GitHub repository that cannot exist. It
    names only the path, which is read in place, as any spelling that names
    no `owner/repo` is: the plan is written, recording that directory and
    no repository, and `gh` is never asked. The control: at GitHub's limit
    the same spelling still names both, and is refused."""
    here = tmp_path / "here"
    source = make_source_repo(here / owner / repo, tree=SMALL_TREE, edits=())
    env, log = recording_gh(tmp_path / "gh-bin")
    spec = f"{owner}/{repo}"

    proc = planned(here, tmp_path, spec, PROJECT, ORG, env)

    assert proc.returncode == 0, said(proc)
    assert "source-ambiguous" not in said(proc)
    record = recorded(tmp_path / "adoption-plan.yaml")
    assert record["local_path"] == str(source.resolve()), record
    assert record["repository"] is None, record
    assert record["cloned"] is False, record
    assert log.read_bytes() == b""

    at = (OWNER_AT, repo) if owner == OWNER_OVER else (owner, NAME_AT)
    make_source_repo(here.joinpath(*at), tree=SMALL_TREE, edits=())
    control = planned(here, tmp_path / "control", "/".join(at), PROJECT, ORG,
                      env)
    assert control.returncode == 2, said(control)
    assert ("REFUSED source-ambiguous: --source '{0}' names both the path "
            "`./{0}` here and the GitHub repository `{0}`").format(
                "/".join(at)) in control.stderr, said(control)
    assert log.read_bytes() == b""


# --- `check` and `execute`: the plan's record, and `--source` ---------------

#: (the name, the owner, the repository), at GitHub's limits or past them.
AT_THE_LIMITS = [
    pytest.param(f"{OWNER_AT}/{PROJECT}", OWNER_AT, PROJECT, id="owner-39"),
    pytest.param(f"{ORG}/{NAME_AT}", ORG, NAME_AT, id="repository-100"),
]
PAST_THE_LIMITS = [
    pytest.param(f"{OWNER_OVER}/{PROJECT}", OWNER_OVER, PROJECT,
                 id="owner-40"),
    pytest.param(f"{ORG}/{NAME_OVER}", ORG, NAME_OVER, id="repository-101"),
    pytest.param(f"{OWNER_OVER}/{NAME_OVER}", OWNER_OVER, NAME_OVER,
                 id="both-over"),
]
VERBS = pytest.mark.parametrize("verb", ["check", "execute"])


def recorded_clone_gone(tmp_path: Path, name: str) -> Path:
    """A plan recording its source as a clone `plan` made (`cloned: true`)
    of `name`, `source.repository`, with that clone gone: the plan `plan`
    wrote for a local source whose `origin` is `testorg/Thing`, its record
    edited, and the source moved away. Returns the plan."""
    source = make_source_repo(tmp_path / "clone" / PROJECT, tree=SMALL_TREE,
                              edits=())
    git("remote", "add", "origin", f"{URL}{REPOSITORY}.git", cwd=source)
    plan = planned_locally(tmp_path, source, cloned=True)
    edited(plan, (f"  repository: {REPOSITORY}", f"  repository: {name}"))
    source.parent.rename(tmp_path / "moved")
    return plan


def run_verb(verb: str, plan: Path, tmp_path: Path, env: dict, *more: str):
    """`check` or `execute --yes` of `plan` in a child, with its own work
    directory and `--local-remote-dir`, so nothing is asked of GitHub but
    what the logging `gh` records."""
    return run_script(ADOPT, verb, "--plan", str(plan), "--work-dir",
                      str(tmp_path / f"{verb}-work"), "--local-remote-dir",
                      str(tmp_path / "remotes"), *more,
                      *(["--yes"] if verb == "execute" else []), env=env)


@VERBS
@pytest.mark.parametrize(("name", "owner", "repo"), AT_THE_LIMITS)
def test_a_recorded_name_github_can_hold_is_cloned_again(tmp_path, verb,
                                                         name, owner, repo):
    """The control: the plan's clone is gone, and its `source.repository`
    is a name GitHub can hold, so `check` and `execute` clone it again, as
    `plan` cloned it: the NOTE says so, and `gh` is asked once."""
    plan = recorded_clone_gone(tmp_path, name)
    env, log = recording_gh(tmp_path / "gh-bin")

    proc = run_verb(verb, plan, tmp_path, env)

    assert log.read_text(encoding="utf-8") == cloned_by_gh(
        owner, repo, tmp_path / f"{verb}-work"), said(proc)
    assert proc.returncode == 2, said(proc)
    assert (f"so its `source.repository`, {name}, is cloned again from "
            "GitHub, as `plan` cloned it.") in proc.stdout, said(proc)
    assert f"REFUSED source-unclonable: could not clone {name}: " in \
        proc.stderr, said(proc)


@VERBS
@pytest.mark.parametrize(("name", "owner", "repo"), PAST_THE_LIMITS)
def test_a_recorded_name_github_cannot_hold_is_never_cloned_again(
        tmp_path, verb, name, owner, repo):
    """The plan's clone is gone, and its `source.repository` names an owner
    over 39 characters or a repository over 100: `check` and `execute` said
    it "is cloned again from GitHub" and asked `gh repo clone` for it. It
    names no repository on GitHub, so it is refused as any record that
    names no `owner/repo` is, and `gh` is never asked."""
    plan = recorded_clone_gone(tmp_path, name)
    env, log = recording_gh(tmp_path / "gh-bin")

    proc = run_verb(verb, plan, tmp_path, env)

    assert log.read_bytes() == b"", said(proc)
    assert proc.returncode == 2, said(proc)
    assert (f"{UNRESOLVABLE}the plan's `source.repository`, {name}, names no "
            "`owner/repo` on github.com\n") in proc.stderr, said(proc)
    assert "cloned again" not in said(proc)
    assert not (tmp_path / f"{verb}-work" / "source-readonly").exists()
    assert not (tmp_path / "remotes").exists()


@VERBS
@pytest.mark.parametrize(("name", "owner", "repo"),
                         AT_THE_LIMITS + PAST_THE_LIMITS)
def test_check_and_execute_read_a_source_name_as_plan_reads_it(
        tmp_path, verb, name, owner, repo):
    """`--source <owner>/<repo>` given to `check` or `execute` is read as
    `plan` reads it: at GitHub's limits it is cloned (`gh` asked once, and
    refused); past them it names no repository and is refused, with no
    `gh` call. The plan's own clone is gone, so `--source` is the way
    on."""
    plan = recorded_clone_gone(tmp_path, REPOSITORY)
    env, log = recording_gh(tmp_path / "gh-bin")

    proc = run_verb(verb, plan, tmp_path, env, "--source", name)

    assert proc.returncode == 2, said(proc)
    if len(owner) <= OWNER_MAX and len(repo) <= NAME_MAX:
        assert log.read_text(encoding="utf-8") == cloned_by_gh(
            owner, repo, tmp_path / f"{verb}-work"), said(proc)
        assert f"REFUSED source-unclonable: could not clone {name}: " in \
            proc.stderr, said(proc)
    else:
        assert log.read_bytes() == b"", said(proc)
        assert f"{UNRESOLVABLE}--source {name!r} {NEITHER}\n" in \
            proc.stderr, said(proc)


# --- `check` and `execute`: the record a source with no `origin` is held to -

def held_to_the_record(tmp_path: Path, name: str) -> Path:
    """The plan for a local source whose `origin` was `testorg/Thing`, with
    `origin` then removed and the plan's `source.repository` edited to
    `name`: the plan is held to its record (#716). Returns the plan."""
    source = make_source_repo(tmp_path / PROJECT, tree=SMALL_TREE, edits=())
    git("remote", "add", "origin", f"{URL}{REPOSITORY}.git", cwd=source)
    plan = planned_locally(tmp_path, source)
    git("remote", "remove", "origin", cwd=source)
    edited(plan, (f"  repository: {REPOSITORY}", f"  repository: {name}"))
    return plan


def unconfirmed(verb: str, plan: Path, tmp_path: Path, env: dict):
    """`check`, or `execute` WITHOUT `--yes`, of `plan` in a child, with
    `--local-remote-dir`: stdin is no terminal, so `execute` stops at its
    confirmation, before anything is made, once every refusal before it has
    passed."""
    return run_script(ADOPT, verb, "--plan", str(plan), "--work-dir",
                      str(tmp_path / f"{verb}-work"), "--local-remote-dir",
                      str(tmp_path / "remotes"), env=env)


@needs_filter_repo
@VERBS
@pytest.mark.parametrize("owner", [
    pytest.param(OWNER_OVER, id="owner-40"),
    pytest.param(ISSUE_OWNER, id="owner-50"),
])
def test_a_record_github_cannot_hold_offers_no_org(tmp_path, verb, owner):
    """A source with no `origin` holds the plan to its record, and a record
    of `<40 c's>/Thing` held it there: `plan-not-the-source`, told to run
    `plan` again with `--org <40 c's>`, which `execute` refuses. It names no
    repository on GitHub now, so it holds the plan to nothing, as a record
    that names no `owner/repo` does: `check` says `plan ok`, and `execute`
    goes on, here to the confirmation it is not given. The control: an
    owner of 39 still holds it, and the remedy names it."""
    plan = held_to_the_record(tmp_path, f"{owner}/{PROJECT}")
    env, log = recording_gh(tmp_path / "gh-bin")

    proc = unconfirmed(verb, plan, tmp_path, env)

    assert f"--org {owner}" not in said(proc), said(proc)
    assert "plan-not-the-source" not in said(proc), said(proc)
    if verb == "check":
        assert proc.returncode == 0, said(proc)
        assert "\nplan ok\n" in proc.stdout, said(proc)
    else:
        assert "REFUSED adopt-unconfirmed: " in proc.stderr, said(proc)
        assert not (tmp_path / "remotes").exists()
    assert log.read_bytes() == b""

    edited(plan, (f"  repository: {owner}/{PROJECT}",
                  f"  repository: {OWNER_AT}/{PROJECT}"))
    control = unconfirmed(verb, plan, tmp_path, env)
    assert "plan-not-the-source" in control.stderr, said(control)
    assert (f"Run `plan` again with `--project {PROJECT} --org {OWNER_AT}`, "
            "the source's own name,") in control.stderr, said(control)
    assert log.read_bytes() == b""
