# SPDX-License-Identifier: Apache-2.0
"""A `.gitmodules` VALUE git's submodule reader refuses is a finding (#215).

git's submodule reader (submodule-config.c, `parse_config`) types three of
the keys it reads, and dies on a value it refuses: an `update` that is not
`checkout`, `rebase`, `merge` or `none` (a `!command` among them), a
`shallow` that is not a boolean, and a `fetchRecurseSubmodules` that is
neither a boolean nor `on-demand`. `git config --list` reads every one of
them, so on main `check` said `plan ok`, and `execute` died in the `git
fast-export` that `git filter-repo` runs, after both leg repositories were
made, whether the tip held the gitlink or only the history did (#195): a
corrected re-run then met `leg-remote-exists`.

All repositories here are local. Only the end-to-end tests at the bottom
need `git filter-repo`. The rest run `check`, call `cmd_execute` in this
process with its probe for the tool stubbed, because the refusal under test
comes before the tool would be used, or ask the installed git's own
submodule reader, through `git fast-export`, what it makes of a value.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import ADOPT, FILE_PROTOCOL, git, make_source_repo, resolve, \
    run_script, write_plan

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

PROJECT = "Northwind"
GITMODULES = ".gitmodules"
UNREADABLE = "plan-gitmodules-unreadable"
REMOTES = "remotes"
#: The submodule, registered under the name `b`.
GITLINK = "vendor/b"
REGISTRATION = '[submodule "b"]\n\tpath = vendor/b\n\turl = ../b\n'
#: A source whose plan asks about `.gitmodules`, and about `vendor/` where
#: the tip holds the submodule: `specs/` and `src/` classify themselves and
#: `README.md` stays in the root.
SMALL_TREE = {"README.md": "# Thing\n", "src/app/util.py": "VALUE = 1\n",
              "specs/001-feature/tasks.md": "- [ ] one\n"}
#: What every value of `update` that git refuses is told, after the value.
NOT_A_STRATEGY = "which is not one of `checkout`, `rebase`, `merge`, `none`"

#: The issue's table, the lines git refuses: each one more line under
#: `[submodule "b"]`, and what the finding says git dies on. Measured with
#: git 2.43 on main a5b09c3: `check` 0 and `execute` 2 with both leg
#: repositories left behind, the tip holding the gitlink or the history.
REFUSED = {
    "update = bogus":
        f"invalid value for `submodule.b.update`: `bogus`, {NOT_A_STRATEGY}",
    "update =": "invalid value for `submodule.b.update`: an empty value, "
                + NOT_A_STRATEGY,
    "update = !cmd": "invalid value for `submodule.b.update`: `!cmd`, a "
                     "command, which git never takes from a .gitmodules",
    "shallow = maybe":
        "bad boolean config value `maybe` for `submodule.b.shallow`",
    "fetchRecurseSubmodules = bogus":
        "bad `submodule.b.fetchrecursesubmodules` argument: `bogus`, which "
        "is neither a boolean nor `on-demand`",
}
#: The issue's table, the lines git reads, and three more: `ignore = bogus`
#: only warns, `branch` takes any value, and the others are values git takes.
#: Each adopted on main and still does.
ACCEPTED = ["ignore = bogus", "branch =", "update = none", "shallow = 0x10",
            "fetchRecurseSubmodules = on-demand"]


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_gitmodules_values",
                                                  ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def as_human(*args: str, cwd: Path):
    """`git <args>` with an identity, for the commits below."""
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
    an embedded clone records one; no checkout of it is needed."""
    head = git("rev-parse", "main", cwd=source).stdout.strip()
    git("update-index", "--add", "--cacheinfo", f"160000,{head},{GITLINK}",
        cwd=source)


def source_with(base: Path, gitmodules: str | bytes, where: str) -> Path:
    """A source whose `.gitmodules` at the tip is `gitmodules`, and whose
    submodule is `where`: at the `tip`; only in the `history`, added and
    removed by two earlier commits under a well-formed `.gitmodules`; or
    `nowhere`, in no commit at all."""
    source = make_source_repo(base / "Thing", tree=SMALL_TREE, edits=())
    if where == "history":
        put_gitmodules(source, REGISTRATION)
        link(source)
        as_human("commit", "-qm", "Add vendor/b", cwd=source)
        git("rm", "-q", "--cached", "--", GITLINK, cwd=source)
        as_human("commit", "-qm", "Remove vendor/b", cwd=source)
    put_gitmodules(source, gitmodules)
    if where == "tip":
        link(source)
    as_human("commit", "-qm", "The tip .gitmodules", cwd=source)
    held = git("ls-tree", "-r", "HEAD", cwd=source).stdout
    assert ("160000" in held) == (where == "tip"), held
    return source


def with_line(line: str) -> str:
    """REGISTRATION and one more line under it, as the issue wrote each."""
    return REGISTRATION + f"\t{line}\n"


#: Where the plan sends `.gitmodules`, and the submodule's entry where the
#: tip holds one: to the code leg, as the issue's plan did.
ANSWERS = {"tip": {GITMODULES: "code", "vendor/": "code"},
           "history": {GITMODULES: "code"}, "nowhere": {GITMODULES: "code"}}


def planned(source: Path, base: Path, answers: dict) -> Path:
    """`plan` for `source`, each entry `answers` names given its leg."""
    plan = base / "plan" / "adoption-plan.yaml"
    plan.parent.mkdir()
    written = write_plan(source, plan, project=PROJECT)
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
    result = run_script(ADOPT, "check", "--plan", str(plan))
    found = [tuple(line.split(" ", 1)[1].split(": ", 1))
             for line in result.stderr.splitlines()
             if line.startswith("FINDING ")]
    assert result.returncode == (1 if found else 0), result.stderr
    return found


def unreadable(said: str) -> str:
    """How the finding begins: what git's submodule reader dies on."""
    return (f"git cannot read the source's .gitmodules for its submodules "
            f"({said}), ")


def in_the_history(adopter) -> re.Pattern:
    """How the finding ends for a submodule only the history holds: the
    commit that removed it, which `git log` meets first."""
    return re.compile(re.escape(adopter.FAILS_IN_THE_HISTORY).replace(
        re.escape("{}"), r"commit [0-9a-f]{12} removes `vendor/b`") + "$")


# --- what `check` finds -----------------------------------------------------

@pytest.mark.parametrize("where", ["tip", "history"])
@pytest.mark.parametrize("line, said", REFUSED.items(), ids=list(REFUSED))
def test_check_finds_a_value_git_refuses(adopter, tmp_path, line, said,
                                         where):
    """Each row of the issue's table that git refuses, in both of its
    positions. On main each passed `check` and failed `execute` in `git
    fast-export` after both leg repositories were made."""
    plan = planned(source_with(tmp_path, with_line(line), where), tmp_path,
                   ANSWERS[where])
    found = findings(plan)
    if where == "tip":
        assert found == [(UNREADABLE, unreadable(said)
                          + adopter.FAILS_IN_THE_EXTRACTION)]
        return
    assert [code for code, _ in found] == [UNREADABLE], found
    assert found[0][1].startswith(unreadable(said)), found
    assert in_the_history(adopter).search(found[0][1]), found


@pytest.mark.parametrize("where", ["tip", "history", "nowhere"])
@pytest.mark.parametrize("line", ACCEPTED)
def test_check_passes_a_value_git_reads(tmp_path, line, where):
    """A value git only warns about, or reads, is no finding wherever the
    submodule is: `ignore = bogus` says `warning: Invalid parameter` and
    goes on, and `git fast-export` exits 0."""
    plan = planned(source_with(tmp_path, with_line(line), where), tmp_path,
                   ANSWERS[where])
    assert findings(plan) == []


@pytest.mark.parametrize("line", REFUSED)
def test_a_refused_value_beside_no_gitlink_anywhere_still_passes(tmp_path,
                                                                  line):
    """#166's S3, for a value: with no gitlink in the tree or its history,
    git never runs its submodule reader on the file, and main adopted and
    cloned each of these."""
    plan = planned(source_with(tmp_path, with_line(line), "nowhere"),
                   tmp_path, ANSWERS["nowhere"])
    assert findings(plan) == []


@pytest.mark.parametrize("gitmodules, said", [
    # git reads the file in order and dies on the first key it refuses.
    (with_line("shallow = maybe") + "\tpath\n",
     "bad boolean config value `maybe` for `submodule.b.shallow`"),
    (with_line("update") + "\tshallow = maybe\n",
     "missing value for 'submodule.b.update'"),
    # A key given twice: git reads the checked-out file with `overwrite`
    # set, so every value is read, and a good one first does not help.
    (with_line("update = checkout") + "\tupdate = bogus\n",
     f"invalid value for `submodule.b.update`: `bogus`, {NOT_A_STRATEGY}"),
    # Under a name that registers nothing: git reads the whole file.
    (REGISTRATION + '[submodule "c"]\n\tupdate = bogus\n',
     f"invalid value for `submodule.c.update`: `bogus`, {NOT_A_STRATEGY}"),
    # git lower-cases the key, and so does the finding.
    (with_line("FetchRecurseSubmodules = maybe"),
     "bad `submodule.b.fetchrecursesubmodules` argument: `maybe`, which is "
     "neither a boolean nor `on-demand`"),
    # Under a name git ignores, nothing is read, and nothing dies.
    (REGISTRATION + '[submodule "../x"]\n\tupdate = bogus\n', None),
    (REGISTRATION + '[submodule ""]\n\tshallow = maybe\n', None),
], ids=["first-of-two-is-a-value", "first-of-two-has-no-value",
        "a-key-given-twice", "under-another-name", "upper-case-key",
        "under-a-suspicious-name", "under-an-empty-name"])
def test_the_finding_names_the_key_git_dies_on(adopter, tmp_path, gitmodules,
                                               said):
    plan = planned(source_with(tmp_path, gitmodules, "tip"), tmp_path,
                   ANSWERS["tip"])
    expected = [] if said is None else [
        (UNREADABLE, unreadable(said) + adopter.FAILS_IN_THE_EXTRACTION)]
    assert findings(plan) == expected


@pytest.mark.parametrize("gitmodules, said", [
    (with_line(r'update = "bo\ngus"'),
     f"invalid value for `submodule.b.update`: `bo\\ngus`, {NOT_A_STRATEGY}"),
    (with_line("shallow = caf").encode()[:-1] + b"\xe9\n",
     "bad boolean config value `caf\\xe9` for `submodule.b.shallow`"),
    (b'[submodule "b\x1bc"]\n\tpath = vendor/b\n\turl = ../b\n'
     b"\tfetchRecurseSubmodules = `x`\n",
     "bad `submodule.b\\x1bc.fetchrecursesubmodules` argument: `\\`x\\``, "
     "which is neither a boolean nor `on-demand`"),
], ids=["a-newline-in-the-value", "a-byte-that-is-not-utf-8",
        "an-escape-in-the-name-and-backticks-in-the-value"])
def test_the_key_and_the_value_are_spelled_on_one_line(adopter, tmp_path,
                                                       gitmodules, said):
    """The key holds the submodule's name and the value is whatever the
    file says: both are spelled as `plan` spells a path, so a finding is
    one line of printable text."""
    plan = planned(source_with(tmp_path, gitmodules, "tip"), tmp_path,
                   ANSWERS["tip"])
    found = findings(plan)
    assert found == [(UNREADABLE, unreadable(said)
                      + adopter.FAILS_IN_THE_EXTRACTION)]
    assert found[0][1].isprintable()


# --- what `execute` refuses -------------------------------------------------

@pytest.mark.parametrize("where", ["tip", "history"])
@pytest.mark.parametrize("line", REFUSED)
def test_execute_refuses_it_before_any_leg_exists(adopter, tmp_path,
                                                  monkeypatch, line, where):
    """The refusal is `check`'s finding, raised by `_refuse_what_check_finds`
    before `_create_leg_remotes`: the directory the legs go in is never
    made."""
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)
    plan = planned(source_with(tmp_path, with_line(line), where), tmp_path,
                   ANSWERS[where])
    found = findings(plan)
    remotes = tmp_path / REMOTES
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(Namespace(
            plan=str(plan), source=None, local_remote_dir=remotes,
            allow_empty_leg=[], yes=True, work_dir=tmp_path / "work"))
    refusal = caught.value
    assert refusal.code == UNREADABLE
    assert refusal.detail.splitlines()[1:] == [
        f"  FINDING {code}: {detail}" for code, detail in found]
    assert "no leg repository was created" in refusal.remediation
    assert not remotes.exists()


# --- read as git reads it ---------------------------------------------------

#: Values whose reading is the same in git 2.39.5 through 2.51 and in every
#: C library CI runs on. Left out: the four bounds git 2.50 moved below
#: zero, which an older git refuses, and a `0b` number, which only glibc
#: 2.38 and later reads; `test_the_numbers_check_reads_as_a_boolean` has those.
BOOLEAN_VALUES = ["", "true", "Off", "YES", "maybe", "t", "1", "-1", "+1",
                  "007", "08", "0x10", "0x", "1k", "1G", "2g", "-1g",
                  "2097151k", "2097152k", "2147483647", "2147483648",
                  "-2147483647", "1e3", "1.0", "1_000", "k", "-", '" 1"',
                  '"1 "', '" true"', "１", "trüe", "on-demand",
                  "On-Demand"]
READ_AS_GIT_READS = (
    [f"shallow = {value}" for value in BOOLEAN_VALUES]
    + [f"fetchRecurseSubmodules = {value}" for value in BOOLEAN_VALUES]
    + [f"update = {value}" for value in
       ["none", "checkout", "rebase", "merge", "Checkout", "", "!cmd", "!",
        "bogus", '" checkout"']]
    + ["ignore = bogus", "ignore =", "branch =", "path =", "url = -x",
       "shallow", "fetchRecurseSubmodules"])


@pytest.fixture(scope="module")
def reader(tmp_path_factory) -> Path:
    """A repository whose second commit adds a gitlink, so that `git
    fast-export --all` there runs git's submodule reader on whatever
    `.gitmodules` the worktree holds -- as it does in the clone `git
    filter-repo` rewrites."""
    repository = tmp_path_factory.mktemp("reader")
    git("init", "-q", "-b", "main", ".", cwd=repository)
    (repository / "README.md").write_bytes(b"# Reader\n")
    git("add", "README.md", cwd=repository)
    as_human("commit", "-qm", "one", cwd=repository)
    link(repository)
    as_human("commit", "-qm", "Add vendor/b", cwd=repository)
    return repository


@pytest.mark.parametrize("line", READ_AS_GIT_READS)
def test_check_reads_a_value_as_the_installed_git_reads_it(adopter, reader,
                                                           line):
    """Whatever git runs this test: `_registrations` refuses the line
    exactly where git's own submodule reader dies on it, in the `git
    fast-export` `git filter-repo` runs."""
    gitmodules = with_line(line).encode()
    (reader / GITMODULES).write_bytes(gitmodules)
    exported = subprocess.run(["git", "fast-export", "--all"], cwd=reader,
                              stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.PIPE, check=False)
    listed = subprocess.run(
        ["git", "config", "-z", "--no-includes", "--file", "-", "--list"],
        input=gitmodules, capture_output=True, check=True)
    read = adopter._registrations(listed.stdout)
    assert isinstance(read, str) == bool(exported.returncode), (
        read, exported.stderr.decode(errors="replace"))


@pytest.mark.parametrize("value, read", [
    # git 2.50 lets in one more number below zero, for each unit; an older
    # git refuses it, and `check` leaves it to the extraction, as on main.
    ("-2147483648", True), ("-2147483649", False),
    ("-2097152k", True), ("-2097153k", False),
    ("-2048m", True), ("-2049m", False), ("-2g", True), ("-3g", False),
    ("-0x80000000", True),
    # Above zero every version agrees.
    ("2147483647", True), ("2147483648", False), ("1g", True),
    ("2g", False),
    # Read as binary by a git built against glibc 2.38 or later (git 2.43
    # here does), and refused elsewhere: not refused, so as not to refuse
    # what git reads.
    ("0b1", True), ("0B0", True), ("0b", False), ("0b2", False),
])
def test_the_numbers_check_reads_as_a_boolean(adopter, value, read):
    assert adopter._git_reads_as_a_boolean(value) is read


# --- end to end -------------------------------------------------------------

def execute_in(plan: Path, base: Path):
    return run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                      "--local-remote-dir", str(base / REMOTES),
                      "--work-dir", str(base / "work"))


@needs_filter_repo
def test_the_issue_shape_is_refused_and_the_repaired_source_then_adopts(
        tmp_path):
    """#215 as the issue measured it, step by step (the tip, `update =
    bogus`): `check` 0, `execute` 2 with both leg repositories left, and the
    corrected re-run refused as `leg-remote-exists`. Now `check` finds it,
    `execute` refuses it with no leg made, and once the source's
    `.gitmodules` is repaired the same `--local-remote-dir` takes the
    adoption."""
    source = source_with(tmp_path, with_line("update = bogus"), "tip")
    plan = planned(source, tmp_path, ANSWERS["tip"])
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 1, checked.stderr + checked.stdout
    assert (f"FINDING {UNREADABLE}: "
            + unreadable(REFUSED["update = bogus"])) in checked.stderr
    refused = execute_in(plan, tmp_path)
    assert refused.returncode == 2, refused.stderr + refused.stdout
    assert f"REFUSED {UNREADABLE}: 1 finding(s) in " in refused.stderr
    assert "creating the leg repositories" not in refused.stdout
    remotes = tmp_path / REMOTES
    assert not remotes.exists() or not any(remotes.iterdir()), \
        "a refused plan left a leg repository behind"

    put_gitmodules(source, with_line("update = checkout"))
    as_human("commit", "-qm", "Repair .gitmodules", cwd=source)
    repaired = tmp_path / "repaired"
    repaired.mkdir()
    plan = planned(source, repaired, ANSWERS["tip"])
    assert run_script(ADOPT, "check", "--plan", str(plan)).returncode == 0
    adopted = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                         "--local-remote-dir", str(remotes), "--work-dir",
                         str(repaired / "work"))
    assert adopted.returncode == 0, adopted.stderr + adopted.stdout
    assert "adoption verified" in adopted.stdout


@needs_filter_repo
@pytest.mark.parametrize("where", ["tip", "history"])
@pytest.mark.parametrize("line", ["ignore = bogus", "branch ="])
def test_a_value_git_reads_still_adopts(tmp_path, line, where):
    """The issue's two rows git reads, end to end: `check` passes them and
    `execute` verifies, as on main."""
    plan = planned(source_with(tmp_path, with_line(line), where), tmp_path,
                   ANSWERS[where])
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    adopted = execute_in(plan, tmp_path)
    assert adopted.returncode == 0, adopted.stderr + adopted.stdout
    assert "adoption verified" in adopted.stdout


@needs_filter_repo
def test_a_refused_value_beside_no_gitlink_anywhere_adopts_and_clones(
        tmp_path):
    """#166's S3, for a value, end to end: `update = bogus` in a source no
    commit of which ever held a gitlink, kept in the code leg. Nothing runs
    git's submodule reader on it: `execute` verifies, and the assembly's
    `git clone --recurse-submodules` exits 0."""
    source = source_with(tmp_path, with_line("update = bogus"), "nowhere")
    plan = planned(source, tmp_path, ANSWERS["nowhere"])
    assert run_script(ADOPT, "check", "--plan", str(plan)).returncode == 0
    adopted = execute_in(plan, tmp_path)
    assert adopted.returncode == 0, adopted.stderr + adopted.stdout
    assert "adoption verified" in adopted.stdout
    clone = tmp_path / "clone"
    cloned = git(*FILE_PROTOCOL, "clone", "-q", "--recurse-submodules", "-b",
                 "adopt/three-repo-shape", str(source), str(clone),
                 cwd=tmp_path, check=False)
    assert cloned.returncode == 0, cloned.stderr
    assert (clone / "code" / GITMODULES).read_bytes() \
        == with_line("update = bogus").encode()
