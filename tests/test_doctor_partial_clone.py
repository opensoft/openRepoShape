# SPDX-License-Identifier: Apache-2.0
"""`shape-doctor.py` run from a partial clone of the standard (#683).

THE DEFECT, measured on main d4a7fab9 with git 2.43 (#460's L10 and L14).
`check_shape_currency` handed the checkout to `update-shape.py`'s
`prepare`, whose `Upstream.blob` read each copy with `git show`, and a
`--filter=blob:none` clone fetches a blob it lacks on that read: five lazy
fetches, from a doctor whose docstring, AGENTS.md and README.md say it
fetches nothing. With the clone's remote out of reach each read failed,
`Upstream.blob` read the failure as "no such file at the pinned commit",
and the row called the five copies the standard had changed since the pin
`both`: `DRIFTED (5 both)` of copies nobody edited, and `update-shape.py
check`, the row's own NEXT, the same.

NOW a partial clone is asked first, with `rev-list --missing=print`, which
never fetches, whether it holds every object at the pinned commit and at
HEAD. Where it does not, the row is CANNOT ANSWER, exit 3, and its NEXT is
a fetch for a person to run. A read that fails is
`update-upstream-unreadable`, never a None. And `partial_clone` reads a
remote as git does: `promisor = false` alone is not one, a
`partialclonefilter` is, and so is `extensions.partialclone`, which no test
reached before (#460 L14).

"FETCHED NOTHING" IS ASKED OF GIT, NOT OF THE NETWORK: `rev-list --objects
--all --missing=print` lists the same missing objects before and after the
run, and lists one at least, so the question has something to answer.
Every remote is a path on this disk reached through `file://`, as
`tests/test_doctor_pin_restore_merges.py` makes its partial clone, and a
remote out of reach is a URL that leads nowhere. Config is appended as
bytes, and nothing is fed to git as text.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from conftest import FILE_PROTOCOL, git, load_without_bytecode, run_script
from test_shape_doctor import (  # noqa: F401
    UPSTREAM_TARGET, doctor, doctor_module, pasted, project, rows_of,
    run_pasted, scaffolded_here, standard, standard_ahead,
    standard_of_another_history, verdict_line,
)

#: The doctor's `error` for a partial clone that lacks what the comparison
#: reads, and `update-shape.py`'s for a read that failed.
PARTIAL = "shape-doctor-partial-clone"
UNREADABLE = "update-upstream-unreadable"

#: What the verdict line opens with for the row this file is about.
CANNOT_ANSWER = ("CANNOT ANSWER (shape currency: the copies cannot be "
                 "compared without fetching")


def head(repo: Path) -> str:
    """The commit `repo`'s HEAD names, 40 hex."""
    return git("rev-parse", "HEAD", cwd=repo).stdout.strip()


@pytest.fixture
def moved(standard, tmp_path) -> dict:
    """The standard at C1, the commit the project is pinned at, and a copy
    of it one commit on, C2, which changes one copied template. A
    `--filter=blob:none` clone of C2 holds the blobs its checkout needed,
    so it lacks C1's copy of that template: one blob, the one a comparison
    against the pin reads."""
    ahead = standard_ahead(standard, tmp_path, UPSTREAM_TARGET,
                           "\n# an upstream fix, after this project was cut\n",
                           "An upstream fix to a copied file")
    git("config", "uploadpack.allowFilter", "true", cwd=ahead)
    return {"ahead": ahead, "c1": head(standard), "c2": head(ahead)}


def partial_clone_of(source: Path, dest: Path, filter_spec: str = "blob:none",
                     *options: str) -> Path:
    """A `--filter` clone of `source` through `file://`, as a person makes
    one by hand. Its own maintenance is off, so no background `gc` a fetch
    starts outlives the test."""
    cloned = subprocess.run(
        ["git", *FILE_PROTOCOL, "clone", "-q", "--no-local",
         f"--filter={filter_spec}", *options, source.as_uri(), str(dest)],
        capture_output=True, check=False)
    assert cloned.returncode == 0, cloned.stdout + cloned.stderr
    git("config", "gc.auto", "0", cwd=dest)
    git("config", "maintenance.auto", "false", cwd=dest)
    return dest


def out_of_reach(clone: Path, tmp_path: Path) -> Path:
    """`clone`, its remote now a URL that leads nowhere."""
    git("remote", "set-url", "origin", (tmp_path / "nowhere.git").as_uri(),
        cwd=clone)
    return clone


def missing(clone: Path) -> set:
    """Every object `clone` lacks, asked of git without fetching."""
    listed = subprocess.run(
        ["git", "rev-list", "--objects", "--all", "--missing=print"],
        cwd=str(clone), capture_output=True, check=True).stdout
    return {line for line in listed.splitlines() if line.startswith(b"?")}


def currency_of(result) -> dict:
    """The `shape currency` row of a `--json` run."""
    return rows_of(result)["shape-currency"]


def doctored(clone: Path, project: Path) -> tuple:
    """`(result, missing before, missing after)` for a `--json` doctor run
    from `clone`, the missing objects asked of git on either side of it."""
    before = missing(clone)
    assert before, "the clone lacks nothing, so nothing can be fetched"
    result = doctor(clone, project, "--json")
    return result, before, missing(clone)


@pytest.mark.parametrize("filter_spec, reachable", [
    ("blob:none", True), ("blob:none", False), ("tree:0", True),
    ("tree:0", False)])
def test_a_partial_clone_behind_its_pin_cannot_answer_and_fetches_nothing(
        moved, project, tmp_path, filter_spec, reachable):
    """The doctor run from a partial clone of C2, against a root pinned at
    C1: CANNOT ANSWER, exit 3, and nothing fetched, whether the clone's
    remote answers or not. A `tree:0` clone lacks C1's root tree as well,
    and is asked before any `ls-tree`, which would fetch it."""
    clone = partial_clone_of(moved["ahead"], tmp_path / "partial",
                             filter_spec)
    if not reachable:
        out_of_reach(clone, tmp_path)
    result, before, after = doctored(clone, project)
    assert result.returncode == 3, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"].startswith(CANNOT_ANSWER)
    assert currency_of(result)["detail"]["error"] == PARTIAL
    assert after == before, "the doctor fetched"


def test_the_row_names_the_commit_short_and_the_fetch_that_ends_it(
        moved, project, tmp_path):
    """What the row says of the clone it could not read: the pinned commit,
    how many objects it lacks there at least -- a floor, since a missing
    tree hides what is under it (#754) -- the promisor remote, and a NEXT
    that fetches every object at that commit from it, never `fetch --all`,
    which keeps the clone's filter and brings in no blob."""
    clone = partial_clone_of(moved["ahead"], tmp_path / "partial")
    row = currency_of(doctor(clone, project, "--json"))
    assert row["detail"] == {
        "error": PARTIAL, "environment": True, "pinned": moved["c1"],
        "standard": moved["c2"], "remote": "origin",
        "lacking": {moved["c1"]: 1}}, row
    assert row["reason"].endswith(
        f"it lacks at least 1 object at the pinned commit "
        f"{moved['c1'][:12]}"), row["reason"]
    assert pasted(row["next"]) == [
        "git", "-C", str(clone.resolve()), "fetch", "--refetch",
        "--no-filter", "origin", moved["c1"]]
    assert row["why"].startswith("this checkout of the standard is a "
                                 "partial clone"), row["why"]


def test_the_next_run_as_printed_lets_the_doctor_answer(moved, project,
                                                        tmp_path):
    """The NEXT, run as a person pastes it, leaves the clone lacking
    nothing, and the doctor run again answers what a full clone of C2
    answers: one copy behind."""
    clone = partial_clone_of(moved["ahead"], tmp_path / "partial")
    run_pasted(currency_of(doctor(clone, project, "--json"))["next"])
    assert missing(clone) == set()
    again = doctor(clone, project)
    assert again.returncode == 1, again.stdout + again.stderr
    assert verdict_line(again).startswith(
        "COMPLIANT, SHAPE BEHIND (1 upstream-changed, 0 upstream-added)"), \
        again.stdout


def checked_out_at_c1(moved: dict, tmp_path: Path) -> Path:
    """A partial clone of C2 that checked out C1 and never C2: it holds
    every object at C1, and lacks C2's copy of the template."""
    clone = partial_clone_of(moved["ahead"], tmp_path / "partial",
                             "blob:none", "--no-checkout")
    git(*FILE_PROTOCOL, "checkout", "-q", "--detach", moved["c1"], cwd=clone)
    return clone


def test_a_partial_clone_pinned_at_its_own_head_answers_as_a_full_clone(
        moved, standard, project, tmp_path):
    """HEAD is C1, the commit the pin names: the clone lacks C2's copy of
    the template, which nothing here reads, and nothing at C1. The verdict
    is the full clone's, and the blob it lacks is still not fetched."""
    clone = checked_out_at_c1(moved, tmp_path)
    result, before, after = doctored(clone, project)
    full = doctor(standard, project, "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == \
        json.loads(full.stdout)["verdict"]
    assert after == before, "the doctor fetched"


def test_the_commit_head_names_is_asked_too(moved, project, tmp_path):
    """The clone holds every object at C1, the pinned commit, and HEAD is
    moved to C2 without a checkout, so the template's blob the comparison
    reads at the target is the one it lacks. The row names HEAD's commit
    alone, and nothing is fetched, with the remote in reach."""
    clone = checked_out_at_c1(moved, tmp_path)
    git("update-ref", "--no-deref", "HEAD", moved["c2"], cwd=clone)
    result, before, after = doctored(clone, project)
    assert currency_of(result)["detail"]["lacking"] == {moved["c2"]: 1}
    assert after == before, "the doctor fetched"


def holds(clone: Path, commit: str) -> bool:
    """Whether `clone` holds `commit`, asked of git without fetching:
    `rev-list --missing=print` refuses a commit it does not hold."""
    return subprocess.run(
        ["git", "rev-list", "--objects", "--no-walk", "--missing=print",
         commit], cwd=str(clone), capture_output=True,
        check=False).returncode == 0


@pytest.fixture
def elsewhere(standard, moved, tmp_path) -> dict:
    """A standard whose `main` is a history of its own, `S`, that holds C1,
    the commit the project is pinned at, on another branch only, `pinned`.
    Its `main` holds the same tools and templates, so the doctor runs from
    a clone of it as from the standard."""
    stranger = standard_of_another_history(standard, tmp_path)
    git(*FILE_PROTOCOL, "fetch", "-q", str(moved["ahead"]),
        f"{moved['c1']}:refs/heads/pinned", cwd=stranger)
    git("config", "uploadpack.allowFilter", "true", cwd=stranger)
    return {"stranger": stranger, "c1": moved["c1"]}


@pytest.fixture
def single_branch(elsewhere, tmp_path) -> Path:
    """A `--single-branch` partial clone of `elsewhere`'s `main`: it does
    not hold C1 at all, which only another branch has (#754)."""
    clone = partial_clone_of(elsewhere["stranger"], tmp_path / "partial",
                             "blob:none", "--single-branch", "--branch",
                             "main")
    assert not holds(clone, elsewhere["c1"]), "the clone holds C1"
    return clone


def test_a_partial_clone_without_the_pinned_commit_cannot_answer(
        elsewhere, single_branch, project):
    """A partial clone that does not hold the pinned commit at all (#754
    S1): `objects_lacking` is None there, which no test reached, and a
    mutant reading it as "lacks nothing" fetched six times and answered.
    CANNOT ANSWER, exit 3, `lacking == {C1: None}`, the `why` says the
    commit is not in the clone, and the clone still does not hold it."""
    result = doctor(single_branch, project, "--json")
    assert result.returncode == 3, result.stdout + result.stderr
    row = currency_of(result)
    assert row["detail"]["lacking"] == {elsewhere["c1"]: None}, row
    assert (f"the pinned commit {elsewhere['c1'][:12]} is not in this "
            "clone at all") in row["why"], row["why"]
    assert not holds(single_branch, elsewhere["c1"]), "the doctor fetched"


def run_the_next_and_ask_again(clone: Path, project: Path) -> dict:
    """The row's NEXT run as a person pastes it, then the `shape currency`
    row the doctor gives after it."""
    run_pasted(currency_of(doctor(clone, project, "--json"))["next"])
    return currency_of(doctor(clone, project, "--json"))


def test_the_next_fetches_a_pinned_commit_only_another_branch_holds(
        elsewhere, single_branch, project):
    """The NEXT names the commit by id (#754 S2): fetching the clone's one
    branch again left it without C1, and the row printed the same NEXT. Run
    as printed, the clone holds C1 and the doctor answers."""
    again = run_the_next_and_ask_again(single_branch, project)
    assert again["detail"].get("error") != PARTIAL, again


@pytest.fixture
def two_promisors(elsewhere, single_branch, moved) -> Path:
    """`single_branch`'s partial clone of `elsewhere`'s `main`, `origin`,
    with the standard one commit on as a second promisor remote,
    `second`, fetched with the same filter: it holds C1's commit, on
    `second`'s branches only, and not C1's blobs that `main` does not
    share."""
    clone = single_branch
    git("remote", "add", "second", moved["ahead"].as_uri(), cwd=clone)
    git("config", "remote.second.promisor", "true", cwd=clone)
    git("config", "remote.second.partialclonefilter", "blob:none",
        cwd=clone)
    git(*FILE_PROTOCOL, "fetch", "-q", "second", cwd=clone)
    assert holds(clone, elsewhere["c1"]), "the clone lacks C1's commit"
    return clone


def test_the_next_names_the_promisor_remote_that_holds_the_commit(
        elsewhere, two_promisors, project):
    """Two promisor remotes, the pinned commit on the second's branches
    only (#754 S2): the NEXT named the first, `origin`, which exits 0 and
    brings in nothing at C1, so the row came back the same. It names
    `second`, and run as printed, the doctor answers."""
    row = currency_of(doctor(two_promisors, project, "--json"))
    assert pasted(row["next"])[-2:] == ["second", elsewhere["c1"]], \
        row["next"]
    again = run_the_next_and_ask_again(two_promisors, project)
    assert again["detail"].get("error") != PARTIAL, again


def test_promisor_false_alone_is_a_read_that_fails_never_a_fetch_or_both(
        moved, project, tmp_path):
    """`remote.origin.promisor = false` with no `partialclonefilter` beside
    it: git fetches nothing there, with its remote in reach, so the doctor
    does not call the clone partial. The read of C1's blob fails, and the
    row is `update-upstream-unreadable`, CANNOT ANSWER, with no fetch to
    name; never `both`."""
    clone = partial_clone_of(moved["ahead"], tmp_path / "partial")
    git("config", "remote.origin.promisor", "false", cwd=clone)
    git("config", "--unset", "remote.origin.partialclonefilter", cwd=clone)
    result, before, after = doctored(clone, project)
    assert result.returncode == 3, result.stdout + result.stderr
    row = currency_of(result)
    assert row["detail"]["error"] == UNREADABLE, row
    assert row["next"] is None, row
    assert after == before, "git fetched"


@pytest.mark.parametrize("filter_spec", ["blob:none", "tree:0"])
def test_update_shape_check_refuses_a_read_that_failed(moved, project,
                                                       tmp_path, filter_spec):
    """`update-shape.py check --upstream` an unreachable partial clone of
    C2: the read of C1's copy fails, and `check` refuses, naming the read,
    rather than print the copy `both`. A `tree:0` clone cannot list C1's
    files either, and that is the same refusal."""
    clone = out_of_reach(partial_clone_of(
        moved["ahead"], tmp_path / "partial", filter_spec), tmp_path)
    result = run_script(clone / "update-shape.py", "check", "--root",
                        str(project), "--upstream", str(clone))
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"REFUSED {UNREADABLE}: {clone.resolve()}" in result.stderr, \
        result.stderr
    assert "both" not in result.stdout, result.stdout


#: Config appended to a full clone's `.git/config`, as bytes, and the
#: remotes git fetches a missing object from under it, in the order it
#: asks them: `promisor-remote.c`'s reading in git 2.43, measured on #683.
PROMISOR_CONFIGS = {
    "none": (b"", []),
    "extensions.partialclone": (
        b"[extensions]\n\tpartialclone = origin\n", ["origin"]),
    "promisor = false": (b'[remote "origin"]\n\tpromisor = false\n', []),
    "promisor = true": (b'[remote "origin"]\n\tpromisor = true\n',
                        ["origin"]),
    "a bare promisor": (b'[remote "origin"]\n\tpromisor\n', ["origin"]),
    "a filter beside promisor = false": (
        b'[remote "origin"]\n\tpromisor = false\n'
        b"\tpartialclonefilter = blob:none\n", ["origin"]),
    "the extension's remote last": (
        b"[extensions]\n\tpartialclone = origin\n"
        b'[remote "origin"]\n\tpromisor = true\n'
        b'[remote "mirror"]\n\tpromisor = true\n', ["mirror", "origin"]),
}


@pytest.mark.parametrize("case", list(PROMISOR_CONFIGS))
def test_partial_clone_reads_a_promisor_remote_as_git_does(standard,
                                                           tmp_path, case):
    """`partial_clone` on a full `--no-local` clone of the standard, with
    `case`'s config appended. With none appended it is False, and with
    `extensions.partialclone` alone True (#460 L14: no test reached that
    alternative, and a regexp without it survived every one). `promisor =
    false` alone is False: git fetches nothing there, a read of a missing
    object fails, and that is `update-upstream-unreadable`'s to refuse."""
    appended, remotes = PROMISOR_CONFIGS[case]
    clone = tmp_path / "full"
    cloned = subprocess.run(
        ["git", *FILE_PROTOCOL, "clone", "-q", "--no-local",
         standard.as_uri(), str(clone)], capture_output=True, check=False)
    assert cloned.returncode == 0, cloned.stdout + cloned.stderr
    with (clone / ".git" / "config").open("ab") as config:
        config.write(appended)
    module = doctor_module(standard)
    assert module.promisor_remotes(clone) == remotes
    assert module.partial_clone(clone) is bool(remotes)


@pytest.mark.parametrize("path, found", [
    (UPSTREAM_TARGET, True), ("templates/assembly-root", False),
    ("templates/assembly-root/no-such-file", False)])
def test_upstream_blob_is_a_files_bytes_or_none_where_there_is_no_file(
        standard, path, found):
    """`Upstream.blob` on a full clone: a file's bytes, as git holds them,
    and None for a path the tree does not have AND for a directory, whose
    `git show` listing it once returned as though it were a file's bytes."""
    module = load_without_bytecode(standard / "update-shape.py",
                                   "update_shape_partial_clone")
    upstream = module.Upstream(standard, str(standard))
    held = subprocess.run(["git", "cat-file", "blob",
                           f"{head(standard)}:{path}"], cwd=str(standard),
                          capture_output=True, check=False).stdout
    assert upstream.blob(head(standard), path) == (held if found else None)
