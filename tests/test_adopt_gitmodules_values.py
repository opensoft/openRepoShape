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
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import ADOPT, FILE_PROTOCOL, GITLINK, GITMODULES, as_human, \
    exported_in_a_clone, findings, git, in_the_history, link, \
    make_source_repo, planned, put_gitmodules, refused_before_any_leg, \
    run_script

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

UNREADABLE = "plan-gitmodules-unreadable"
REMOTES = "remotes"
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
#: Numbers only some of the gits `execute` may run read as a boolean, and
#: what the finding says of each: git 2.50 and later read the first two,
#: and git 2.43 here refuses them (measured on c800efd, `check` 0 and
#: `execute` 2 with both leg repositories left); a git built on glibc 2.38
#: or later, as git 2.43 here is, reads the third. `check` refuses each
#: with the gits that refuse it.
ONLY_SOME_GITS_READ = {
    "shallow = -2147483648":
        "bad boolean config value `-2147483648` for `submodule.b.shallow`, "
        "a number git 2.49 and older refuse, and 2.50 and later read",
    "fetchRecurseSubmodules = -2g":
        "bad `submodule.b.fetchrecursesubmodules` argument: `-2g`, a number "
        "git 2.49 and older refuse, and 2.50 and later read",
    "shallow = 0b1":
        "bad boolean config value `0b1` for `submodule.b.shallow`, a `0b` "
        "number, which a git reads only where its C library reads C23 binary "
        "numbers (glibc 2.38 or later, for one)",
}
#: Every line `check` refuses beside a gitlink.
CHECK_REFUSES = {**REFUSED, **ONLY_SOME_GITS_READ}
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


def type_changes(source: Path) -> None:
    """A file at GITLINK, then a gitlink in its place, then the file again:
    two commits `git log --raw` shows as type changes, `T`, and no commit
    that adds or removes a gitlink."""
    (source / GITLINK).parent.mkdir()
    (source / GITLINK).write_bytes(b"a file\n")
    git("add", "--", GITLINK, cwd=source)
    as_human("commit", "-qm", "vendor/b, a file", cwd=source)
    git("rm", "-q", "--cached", "--", GITLINK, cwd=source)
    link(source)
    as_human("commit", "-qm", "vendor/b, a gitlink", cwd=source)
    git("add", "--", GITLINK, cwd=source)
    as_human("commit", "-qm", "vendor/b, a file again", cwd=source)


def source_with(base: Path, gitmodules: str | bytes, where: str) -> Path:
    """A source whose `.gitmodules` at the tip is `gitmodules`, and whose
    submodule is `where`: at the `tip`; only in the `history`, added and
    removed by two earlier commits under a well-formed `.gitmodules`;
    entered and left by `type-changes` alone, which git's diff never asks
    the submodule reader about; or `nowhere`, in no commit at all."""
    source = make_source_repo(base / "Thing", tree=SMALL_TREE, edits=())
    if where == "history":
        put_gitmodules(source, REGISTRATION)
        link(source)
        as_human("commit", "-qm", "Add vendor/b", cwd=source)
        git("rm", "-q", "--cached", "--", GITLINK, cwd=source)
        as_human("commit", "-qm", "Remove vendor/b", cwd=source)
    elif where == "type-changes":
        type_changes(source)
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


#: Where the plan sends `.gitmodules`, and the entry for `vendor/` where
#: the tip holds something there: to the code leg, as the issue's plan did.
ANSWERS = {"tip": {GITMODULES: "code", "vendor/": "code"},
           "history": {GITMODULES: "code"},
           "type-changes": {GITMODULES: "code", "vendor/": "code"},
           "nowhere": {GITMODULES: "code"}}


def unreadable(said: str) -> str:
    """How the finding begins: what git's submodule reader dies on."""
    return (f"git cannot read the source's .gitmodules for its submodules "
            f"({said}), ")


# --- what `check` finds -----------------------------------------------------

@pytest.mark.parametrize("where", ["tip", "history"])
@pytest.mark.parametrize("line, said", CHECK_REFUSES.items(),
                         ids=list(CHECK_REFUSES))
def test_check_finds_a_value_git_refuses(adopter, tmp_path, line, said,
                                         where):
    """Each row of the issue's table that git refuses, in both of its
    positions. On main each passed `check` and failed `execute` in `git
    fast-export` after both leg repositories were made. So do the numbers
    only some gits read, refused with the gits that refuse them."""
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


@pytest.mark.parametrize("line", CHECK_REFUSES)
def test_a_refused_value_beside_no_gitlink_anywhere_still_passes(tmp_path,
                                                                  line):
    """#166's S3, for a value: with no gitlink in the tree or its history,
    git never runs its submodule reader on the file, and main adopted and
    cloned each of these."""
    plan = planned(source_with(tmp_path, with_line(line), "nowhere"),
                   tmp_path, ANSWERS["nowhere"])
    assert findings(plan) == []


@pytest.mark.parametrize("line", CHECK_REFUSES)
def test_a_refused_value_beside_a_gitlink_only_type_changes_move_passes(
        tmp_path, line):
    """#195's type change, for a value: git's diff asks the submodule
    reader about a changed path only when both of its sides are gitlinks,
    so `git fast-export` in a clone of the source never reads this
    `.gitmodules` and exits 0, and `check` passes it. Before #226's fix
    round (f48c669) was merged here, `check` refused it."""
    source = source_with(tmp_path, with_line(line), "type-changes")
    exported = exported_in_a_clone(source, tmp_path)
    assert exported.returncode == 0, exported.stderr
    plan = planned(source, tmp_path, ANSWERS["type-changes"])
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
@pytest.mark.parametrize("line", CHECK_REFUSES)
def test_execute_refuses_it_before_any_leg_exists(adopter, tmp_path,
                                                  monkeypatch, line, where):
    """The refusal is `check`'s finding, raised by `_refuse_what_check_finds`
    before `_create_leg_remotes`: the directory the legs go in is never
    made (`refused_before_any_leg`)."""
    plan = planned(source_with(tmp_path, with_line(line), where), tmp_path,
                   ANSWERS[where])
    refusal = refused_before_any_leg(adopter, monkeypatch, plan, tmp_path)
    assert refusal.code == UNREADABLE


# --- read as git reads it ---------------------------------------------------

#: Values whose reading is the same in git 2.39.5 through 2.51 and in every
#: C library CI runs on. Left out: the four bounds git 2.50 moved below
#: zero, which an older git refuses, and a `0b` number, which only a C
#: library that reads C23 binary numbers (glibc 2.38 or later) reads:
#: `check` refuses those with the gits that refuse them, and
#: `test_who_refuses_a_number_as_a_boolean` has them.
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


@pytest.mark.parametrize("value, refusers", [
    # git 2.50 lets in one more number below zero, for each unit, and an
    # older git refuses it: `check` refuses it with the older git, so that
    # `execute` cannot die on it after both leg repositories exist.
    ("-2147483648", "OLDER_GITS_REFUSE"), ("-2147483649", "EVERY_GIT"),
    ("-2097152k", "OLDER_GITS_REFUSE"), ("-2097153k", "EVERY_GIT"),
    ("-2048m", "OLDER_GITS_REFUSE"), ("-2049m", "EVERY_GIT"),
    ("-2g", "OLDER_GITS_REFUSE"), ("-3g", "EVERY_GIT"),
    ("-0x80000000", "OLDER_GITS_REFUSE"),
    # One above each, every version reads.
    ("-2147483647", None), ("-2097151k", None), ("-2047m", None),
    ("-1g", None),
    # Above zero every version agrees.
    ("2147483647", None), ("2147483648", "EVERY_GIT"), ("1g", None),
    ("2g", "EVERY_GIT"),
    # Read as binary by a git whose C library reads C23 binary numbers
    # (glibc 2.38 or later; git 2.43 here is one), and refused by any other:
    # `check` refuses it too.
    ("0b1", "SOME_LIBRARIES_REFUSE"), ("0B0", "SOME_LIBRARIES_REFUSE"),
    ("-0b1", "SOME_LIBRARIES_REFUSE"), ("0b", "EVERY_GIT"),
    ("0b2", "EVERY_GIT"),
])
def test_who_refuses_a_number_as_a_boolean(adopter, value, refusers):
    expected = None if refusers is None else getattr(adopter, refusers)
    assert adopter._who_refuses_a_boolean(value) == expected


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
@pytest.mark.parametrize("where", ["nowhere", "type-changes"])
def test_a_refused_value_git_never_reads_adopts_and_clones(tmp_path, where):
    """#166's S3, for a value, end to end: `update = bogus`, kept in the
    code leg, in a source no commit of which ever held a gitlink, or whose
    gitlink only type changes moved (#195's fix round). Nothing runs git's
    submodule reader on it: `execute` verifies, and the assembly's `git
    clone --recurse-submodules` exits 0."""
    source = source_with(tmp_path, with_line("update = bogus"), where)
    plan = planned(source, tmp_path, ANSWERS[where])
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
