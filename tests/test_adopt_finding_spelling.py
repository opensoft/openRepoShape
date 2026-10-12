# SPDX-License-Identifier: Apache-2.0
"""Every path a FINDING or a refusal names is `_spelled`, so it is one line.

On main at 20e13f0 `check` and `execute` printed a source path RAW in every
finding that named one (#212), while `plan`'s questions spelled the same path
with `_spelled` (#166). A name holding a carriage return sent the cursor back
over the line and hid which path it was; a line feed, and the line boundaries
U+0085 and U+2028 that `str.splitlines` and a viewer honour, split one finding
into two lines, the second no longer starting with `FINDING`; an ESC began a
terminal escape sequence out of a name the adopted repository's author chose.
`execute` printed the same lines in its refusal, "as `check` prints them".

So each finding that names a path is asked here over those five characters:
its line is ONE line of printable text (`str.isprintable` refuses every one of
them), it holds the name as `_spelled` writes it, and it holds no raw
character. Most cases call the function that writes the finding and need no
git at all. The end-to-end cases put the names into a source with `git mktree`
and `git commit-tree`, so that no filesystem has to hold them (NTFS cannot),
then run `check` as a person runs it and read its BYTES, and run `execute` in
this process with its `git filter-repo` probe stubbed, as
`tests/test_adopt_execute_refusals.py` does: the refusal comes before the tool
would be used.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path

import pytest

from conftest import (ADOPT, blank_unnamed_pin_sources, git, make_source_repo,
                      resolve, write_plan)

#: Each character, by the id its tests wear: `(raw, as _spelled writes it)`.
CHARACTERS = {
    "carriage-return": ("\r", "\\r"),
    "line-feed": ("\n", "\\n"),
    "next-line": ("\x85", "\\x85"),
    "line-separator": ("\u2028", "\\u2028"),
    "escape": ("\x1b", "\\x1b"),
}
EACH_CHARACTER = pytest.mark.parametrize(
    ("char", "spelled"), list(CHARACTERS.values()), ids=list(CHARACTERS))

PROJECT = "Northwind"
UTF8 = "utf-8"
NUL = b"\x00"
#: The plan entries `plan` writes a question for in `make_source_repo`'s
#: tree, answered as `tests/test_adopt_execute_refusals.py` answers them.
ANSWERS = (("examples/", "spec"), (".claude/", "root"),
           ("release.yaml", "root"))
SRC_ENTRY = "  - path: src/\n"
#: The pin the shape's files are checked against in the split commit.
PIN = "contracts/shape-pin.yaml"


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_finding_spelling",
                                                  ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def no_filter_repo_probe(adopter, monkeypatch):
    """`cmd_execute` asks for `git filter-repo` first, and no test here gets
    as far as using it."""
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)


def assert_one_readable_line(line: str, char: str, *spelled: str) -> None:
    """`line` is one line a terminal shows as written: no line break, no ESC,
    no other character `str.isprintable` refuses, and each of `spelled`."""
    assert char not in line, f"the raw character is printed: {line!r}"
    assert line.isprintable(), f"not one line of printable text: {line!r}"
    for name in spelled:
        assert name in line, (name, line)


def with_code(findings: list[str], code: str) -> list[str]:
    """The findings in `findings` of the one code under test."""
    return [line for line in findings if line.startswith(f"FINDING {code}: ")]


def plan_of(adopter, entries: list[dict], spec_path: str = "spec"):
    """An adoption plan holding `entries`, read as `Plan.load` reads one. Built
    in memory, because the YAML reader on main cannot take a carriage return,
    U+0085 or U+2028 back out of a file (#199); the finding is what is under
    test here, not the reader."""
    return adopter.Plan(Path("adoption-plan.yaml"), {
        "kind": adopter.PLAN_KIND, "mode": "in-place",
        "legs": {"spec_path": spec_path, "code_path": "code"},
        "paths": entries})


# --- `_coverage_findings` --------------------------------------------------

@EACH_CHARACTER
def test_plan_uncovered_spells_the_source_path(adopter, char, spelled):
    """The issue's own expectation, word for word."""
    findings = adopter._coverage_findings(["README.md"],
                                          ["README.md", f"Icon{char}"])
    assert findings == [f"FINDING plan-uncovered: `Icon{spelled}` is in the "
                        "source tree and in no plan entry"]
    assert_one_readable_line(findings[0], char, f"`Icon{spelled}`")


@EACH_CHARACTER
def test_plan_covered_twice_spells_the_path_and_each_entry(adopter, char,
                                                          spelled):
    entries = ["src/", f"src/a{char}p/"]
    [finding] = with_code(adopter._coverage_findings(
        entries, [f"src/a{char}p/Icon{char}"]), "plan-covered-twice")
    assert finding == (f"FINDING plan-covered-twice: `src/a{spelled}p/"
                       f"Icon{spelled}` is covered by `src/`, "
                       f"`src/a{spelled}p/`")
    assert_one_readable_line(finding, char)


@EACH_CHARACTER
def test_plan_duplicate_path_spells_the_entry(adopter, char, spelled):
    entries = [f"Icon{char}", f"Icon{char}"]
    [finding] = with_code(adopter._coverage_findings(entries, [f"Icon{char}"]),
                          "plan-duplicate-path")
    assert finding == (f"FINDING plan-duplicate-path: `Icon{spelled}` "
                       "appears 2 times")
    assert_one_readable_line(finding, char)


@EACH_CHARACTER
def test_plan_empty_entry_spells_the_entry(adopter, char, spelled):
    [finding] = with_code(adopter._coverage_findings(
        ["README.md", f"go{char}ne/"], ["README.md"]), "plan-empty-entry")
    assert finding == (f"FINDING plan-empty-entry: `go{spelled}ne/` covers "
                       "nothing in the source tree at this commit")
    assert_one_readable_line(finding, char)


# --- `_leg_findings` -------------------------------------------------------

@EACH_CHARACTER
def test_plan_unresolved_spells_the_entry(adopter, char, spelled):
    plan = plan_of(adopter, [{"path": f"Icon{char}", "leg": None,
                              "question": "Which leg?"}])
    findings = adopter._leg_findings(plan, [])
    assert findings == [
        f"FINDING plan-unresolved: `Icon{spelled}` still has `leg: null`. "
        "The question was: Which leg?"]
    assert_one_readable_line(findings[0], char)


@EACH_CHARACTER
def test_plan_bad_leg_spells_the_entry(adopter, char, spelled):
    plan = plan_of(adopter, [{"path": f"Icon{char}", "leg": "Spec"}])
    [finding] = adopter._leg_findings(plan, [])
    assert finding.startswith(f"FINDING plan-bad-leg: `Icon{spelled}` "
                              "declares leg 'Spec'; it is one of "), finding
    assert_one_readable_line(finding, char)


@EACH_CHARACTER
def test_plan_leg_path_collides_spells_the_kept_path_and_its_entry(
        adopter, char, spelled):
    """`legs.spec_path` `odd` over a file the plan keeps in the root: the file
    is named once and its entry twice, in `check`'s sentence and `plan`'s
    NOTE alike (`_kept_collisions`)."""
    entry, path = f"odd/s{char}ub/", f"odd/s{char}ub/Icon{char}"
    plan = plan_of(adopter, [{"path": entry, "leg": "root"}], spec_path="odd")
    [finding] = adopter._leg_findings(plan, [(path, "100644", "0" * 40, 1)])
    assert finding.startswith(
        f"FINDING plan-leg-path-collides: legs.spec_path 'odd' contains the "
        f"file `odd/s{spelled}ub/Icon{spelled}`. The plan keeps it in the "
        f"assembly root under the entry `odd/s{spelled}ub/`, "), finding
    assert finding.endswith(f", or send `odd/s{spelled}ub/` to a leg or "
                            "`drop` it."), finding
    assert_one_readable_line(finding, char)


# --- the source's own submodules (`_as_entry`) -----------------------------

def gitlink_row(path: str) -> tuple:
    return (path, "160000", "1" * 40, 0)


def submodule_findings(adopter, entries: list[dict], tree: list,
                       registered) -> list[str]:
    """`submodule_plan_problems`, as `check` prints each one."""
    return [f"FINDING {code}: {detail}" for code, detail in
            adopter.submodule_plan_problems(entries, tree, registered)]


@EACH_CHARACTER
def test_plan_submodule_root_spells_the_submodule_and_its_entry(
        adopter, char, spelled):
    entries = [{"path": f"ven{char}dor/", "leg": "root"}]
    [finding] = submodule_findings(adopter, entries,
                                   [gitlink_row(f"ven{char}dor/d{char}p")],
                                   adopter.Registrations())
    assert finding.startswith(
        f"FINDING plan-submodule-root: `ven{spelled}dor/d{spelled}p` (entry "
        f"`ven{spelled}dor/`) has leg: root, "), finding
    assert_one_readable_line(finding, char)


@EACH_CHARACTER
def test_plan_submodule_root_spells_a_submodule_that_is_its_own_entry(
        adopter, char, spelled):
    entries = [{"path": f"d{char}p", "leg": "root"}]
    [finding] = submodule_findings(adopter, entries,
                                   [gitlink_row(f"d{char}p")],
                                   adopter.Registrations())
    assert finding.startswith(f"FINDING plan-submodule-root: `d{spelled}p` "
                              "has leg: root, "), finding
    assert_one_readable_line(finding, char)


@EACH_CHARACTER
def test_plan_submodule_unregistered_spells_the_submodule_and_its_entry(
        adopter, char, spelled):
    entries = [{"path": f"ven{char}dor/", "leg": "code"}]
    [finding] = submodule_findings(adopter, entries,
                                   [gitlink_row(f"ven{char}dor/d{char}p")],
                                   adopter.Registrations())
    assert finding.startswith(
        f"FINDING plan-submodule-unregistered: the submodule "
        f"`ven{spelled}dor/d{spelled}p` (entry `ven{spelled}dor/`) has leg: "
        "code but no .gitmodules entry in the source registers its path "
        "with a url, "), finding
    assert_one_readable_line(finding, char)


@EACH_CHARACTER
def test_plan_submodule_split_spells_the_submodule_and_its_entry(
        adopter, char, spelled):
    gitlink = f"ven{char}dor/d{char}p"
    registered = adopter.Registrations()
    registered.read("dep", "path", gitlink)
    registered.read("dep", "url", "../dep")
    entries = [{"path": f"ven{char}dor/", "leg": "code"},
               {"path": ".gitmodules", "leg": "spec"}]
    tree = [gitlink_row(gitlink), (".gitmodules", "100644", "2" * 40, 1)]
    [finding] = submodule_findings(adopter, entries, tree, registered)
    assert finding.startswith(
        f"FINDING plan-submodule-split: the submodule "
        f"`ven{spelled}dor/d{spelled}p` (entry `ven{spelled}dor/`) has leg: "
        "code but the source's .gitmodules has leg: spec, "), finding
    assert_one_readable_line(finding, char)


# --- `execute`: its own refusal, and the verification after the split -----

@EACH_CHARACTER
def test_execute_refuses_an_unresolved_entry_on_readable_lines(adopter, char,
                                                               spelled):
    """`_refuse_an_unrunnable_plan` lists the unresolved entries itself,
    before `_refuse_what_check_finds` would."""
    plan = plan_of(adopter, [{"path": "README.md", "leg": "root"},
                             {"path": f"Icon{char}", "leg": None}])
    with pytest.raises(adopter.Refusal) as caught:
        adopter._refuse_an_unrunnable_plan(plan, None)
    assert caught.value.code == "plan-unresolved"
    assert caught.value.detail == ("1 path(s) still have `leg: null`: "
                                   f"`Icon{spelled}`")
    for line in str(caught.value).split("\n"):
        assert_one_readable_line(line, char)


@EACH_CHARACTER
def test_adopt_lost_spells_the_source_path(adopter, char, spelled):
    _, findings = adopter._account_for({f"Icon{char}": "a" * 40}, {}, [])
    assert findings == [f"FINDING adopt-lost: `Icon{spelled}` (aaaaaaaaaaaa) "
                        "is in no leg, not in the root tree, and not listed "
                        "as drop"]
    assert_one_readable_line(findings[0], char)


@EACH_CHARACTER
def test_adopt_duplicated_spells_the_source_path(adopter, char, spelled):
    oid = "b" * 40
    _, findings = adopter._account_for(
        {f"Icon{char}": oid}, {f"Icon{char}": [f"spec:{oid}", f"root:{oid}"]},
        [])
    assert findings == [f"FINDING adopt-duplicated: `Icon{spelled}` is in "
                        f"spec:{oid}, root:{oid}"]
    assert_one_readable_line(findings[0], char)


@EACH_CHARACTER
def test_adopt_mount_occupied_spells_the_kept_path_under_the_mount(
        adopter, char, spelled):
    """`execute`'s last guard before `git submodule add --force` (#174) names
    the first index entry under the leg mount path. The mount path itself is
    a leg path, which `checked_value`'s alphabet already keeps printable; the
    entry under it is a source name the plan kept in the root. Asked of the
    function itself, as `tests/test_adopt_mount_ignored.py` asks it."""
    held = [("a file", f"spec/Icon{char}"), ("a symlink", f"spec/l{char}nk")]
    refusal = adopter._refusal_for_held("spec", held)
    assert refusal.code == "adopt-mount-occupied"
    assert refusal.detail == (
        "the assembly's index already holds paths under spec, the leg mount "
        f"path: `spec/Icon{spelled}` (a file) and 1 more")
    assert_one_readable_line(refusal.detail, char)


def test_adopt_mount_occupied_spells_a_byte_that_is_not_utf8(adopter,
                                                             tmp_path):
    """`_index_entries` reads the index as `Source.tree` reads a tree: a byte
    that is not UTF-8 is kept, so the refusal spells 0xFE `\\udcfe`, as
    `plan-uncovered` would, and as the plan's own `path:` does (#329).
    Decoded with `replace`, `a<0xFE>` and `a<0xFF>` both read `a<U+FFFD>`.
    The entries go in with `git update-index --index-info`, fed bytes, so no
    filesystem has to hold them."""
    repo = tmp_path / "assembly"
    repo.mkdir()
    git_out(repo, "init", "-q")
    blob = git_out(repo, "hash-object", "-w", "--stdin", stdin=b"x\n").strip()
    git_out(repo, "update-index", "--index-info", stdin=b"".join(
        b"100644 " + blob + b"\t" + name + b"\n"
        for name in (b"spec/a\xfe", b"spec/a\xff")))
    assert [adopter._entry_named(entry) for entry in
            adopter._index_entries(repo, ["spec"])] == [
        "`spec/a\\udcfe` (a file)", "`spec/a\\udcff` (a file)"]
    with pytest.raises(adopter.Refusal) as caught:
        adopter._refuse_an_unmountable_path(repo, "spec")
    assert caught.value.code == "adopt-mount-occupied"
    assert caught.value.detail == (
        "the assembly's index already holds paths under spec, the leg mount "
        "path: `spec/a\\udcfe` (a file) and 1 more")


#: The root tree's two leg mounts, as `_verify` passes them to
#: `_land_the_root_tree`: each gitlink the shape adds, at the plan's path.
MOUNTS = {"spec": "spec", "code": "code"}


def root_gitlink_findings(adopter, path: str, oid: str,
                          before: dict) -> list[str]:
    """What `_land_the_root_tree` finds in a root tree holding the two leg
    mounts and one more gitlink, at `path`."""
    tree = [(mount, adopter.GITLINK_MODE, "c" * 40, 0) for mount in MOUNTS]
    tree.append((path, adopter.GITLINK_MODE, oid, 0))
    return adopter._land_the_root_tree({}, tree, before, MOUNTS)


@EACH_CHARACTER
def test_adopt_root_submodule_spells_the_source_submodule(adopter, char,
                                                          spelled):
    """The source's own submodule at its own commit, left in the root
    (#165). Its path is a source name."""
    oid = "d" * 40
    [finding] = root_gitlink_findings(adopter, f"ven{char}dor/d{char}p", oid,
                                      {f"ven{char}dor/d{char}p": oid})
    assert finding.startswith(
        f"FINDING adopt-root-submodule: `ven{spelled}dor/d{spelled}p` is a "
        f"gitlink to {oid[:12]} in the root tree, the source's own "
        "submodule at its own commit, "), finding
    assert_one_readable_line(finding, char)


@EACH_CHARACTER
def test_adopt_unexpected_gitlink_spells_the_gitlink(adopter, char, spelled):
    """Any other gitlink in the root. The mount paths beside it are leg
    paths, which `checked_value`'s alphabet already keeps printable."""
    oid = "e" * 40
    [finding] = root_gitlink_findings(adopter, f"ex{char}tra", oid, {})
    assert finding.startswith(
        f"FINDING adopt-unexpected-gitlink: `ex{spelled}tra` is a gitlink to "
        f"{oid[:12]} in the root tree, and neither a leg mount as the plan "
        "spells their paths (code, spec) nor the source's own submodule at "
        "that commit; "), finding
    assert_one_readable_line(finding, char)


def git_out(repo: Path, *args: str, stdin: bytes | None = None) -> bytes:
    """`git <args>` in `repo`, fed and answering BYTES: text mode would turn a
    carriage return into a line break, and Windows would add one. Skipped
    where git refuses outright to build a name, which is git's to say on its
    platform and not a failure of the finding under test."""
    done = subprocess.run(
        ["git", "-c", "user.name=openRepoShape tests",
         "-c", "user.email=tests@openreposhape.invalid", *args],
        cwd=str(repo), input=stdin, capture_output=True, check=False)
    if done.returncode:
        pytest.skip(f"git {args[0]} refuses it here: {done.stderr!r}")
    return done.stdout


def tree_with(repo: Path, base: str | None, files: dict) -> str:
    """The tree `base` (an id, or None for an empty tree) with `files` added:
    `{path: (mode, body)}`, each body a blob. `git mktree` writes each level,
    and checks no name against a filesystem, so a name NTFS cannot hold is
    built on Windows too."""
    listing: dict[bytes, bytes] = {}
    if base:
        for record in git_out(repo, "ls-tree", "-z", base).split(NUL):
            if record:
                listing[record.split(b"\t", 1)[1]] = record
    nested: dict[str, dict] = {}
    for path, (mode, body) in files.items():
        head, slash, rest = path.partition("/")
        if slash:
            nested.setdefault(head, {})[rest] = (mode, body)
            continue
        blob = git_out(repo, "hash-object", "-w", "--no-filters", "--stdin",
                       stdin=body).strip()
        listing[head.encode(UTF8)] = (mode.encode() + b" blob " + blob + b"\t"
                                      + head.encode(UTF8))
    for head, below in nested.items():
        name = head.encode(UTF8)
        old = listing.get(name)
        subtree = tree_with(repo, old.split(b"\t")[0].split()[2].decode()
                            if old else None, below)
        listing[name] = b"040000 tree " + subtree.encode() + b"\t" + name
    return git_out(repo, "mktree", "-z",
                   stdin=b"".join(r + NUL for r in listing.values())
                   ).strip().decode()


def commit_tree(repo: Path, tree: str, parents: tuple = ()) -> str:
    args = [arg for parent in parents for arg in ("-p", parent)]
    return git_out(repo, "commit-tree", tree, *args, "-m",
                   "names a terminal acts on").strip().decode()


def assert_names_are_in(repo: Path, commit: str, names: list[str]) -> None:
    """Every one of `names` is in `commit`'s tree, as git reads it back."""
    held = git_out(repo, "ls-tree", "-r", "-z", "--name-only",
                   commit).split(NUL)
    missing = [name for name in names if name.encode(UTF8) not in held]
    if missing:
        pytest.skip(f"git does not keep {missing!r} in a tree here")


#: `(case, pinned path, link name, link target, the words the finding uses)`
#: for a split commit that holds each link. `{c}` is the character and `{s}`
#: its spelling, `{commit}` the split commit's short id.
SPLIT_TREE_CASES = {
    "missing": ("mis{c}sing", None, None,
                "`mis{s}sing` is named by contracts/shape-pin.yaml but is "
                "not in the split commit {commit}, so "),
    "leads-out": ("l{c}nk/validate.yml", "l{c}nk", "/out{c}side",
                  "`l{s}nk/validate.yml` is named by contracts/shape-pin.yaml "
                  "but leads out of the split commit {commit} at the symlink "
                  "`l{s}nk`, to `/out{s}side`, so "),
    "climbs-above": ("u{c}p/x", "u{c}p", "../x",
                     "climbs above the root of the split commit {commit} at "
                     "the symlink `u{s}p`, so "),
    "a-loop": ("lo{c}op/x", "lo{c}op", "lo{c}op",
               "follows too many symlinks at `lo{s}op` in the split commit "
               "{commit}, so "),
    "through-a-non-directory": ("t{c}hru/x", "t{c}hru", "n{c}owhere/../x",
                                "passes through `n{s}owhere`, which is not a "
                                "directory in the split commit {commit}, "
                                "so "),
}


@pytest.fixture(scope="module", params=list(CHARACTERS.values()),
                ids=list(CHARACTERS))
def split_commit(request, tmp_path_factory):
    """`(repo, commit, char, spelled)`: a split commit holding every link of
    `SPLIT_TREE_CASES` for one character, and its pin."""
    char, spelled = request.param
    repo = tmp_path_factory.mktemp("split")
    git("init", "-q", "-b", "main", ".", cwd=repo)
    files = {PIN: ("100644", b"files: []\n")}
    for _, link, target, _ in SPLIT_TREE_CASES.values():
        if link:
            files[link.format(c=char)] = ("120000",
                                          target.format(c=char).encode(UTF8))
    commit = commit_tree(repo, tree_with(repo, None, files))
    assert_names_are_in(repo, commit, [name for name in files])
    return repo, commit, char, spelled


@pytest.mark.parametrize("case", list(SPLIT_TREE_CASES))
def test_adopt_shape_file_missing_spells_every_path_it_names(
        adopter, split_commit, case):
    """The pinned path, the symlink a lookup met, its target, and a path
    that is no directory: each is a name of the source's when its plan keeps
    a link, or its own pin, in the root (#167)."""
    repo, commit, char, spelled = split_commit
    pinned, _, _, words = SPLIT_TREE_CASES[case]
    tree = adopter._SplitTree(repo, commit)
    finding = adopter._pinned_file_finding(tree, pinned.format(c=char))
    assert finding.startswith("FINDING adopt-shape-file-missing: `"), finding
    assert words.format(s=spelled, commit=commit[:12]) in finding, finding
    assert_one_readable_line(finding, char)


# --- end to end: `check` as a person runs it, and `execute` ----------------

@dataclass(frozen=True)
class World:
    """A source whose head adds `Icon<char>` at the top and under `src/app/`,
    and a plan for that head with every question answered and a `src/app/`
    entry beside `src/`: `Icon<char>` is uncovered, `src/app/Icon<char>` is
    covered twice."""

    source: Path
    plan: Path
    char: str
    spelled: str

    @property
    def uncovered(self) -> str:
        return (f"FINDING plan-uncovered: `Icon{self.spelled}` is in the "
                "source tree and in no plan entry")

    @property
    def covered_twice(self) -> str:
        return (f"FINDING plan-covered-twice: `src/app/Icon{self.spelled}` "
                "is covered by `src/app/`, `src/`")


@pytest.fixture(scope="module", params=list(CHARACTERS.values()),
                ids=list(CHARACTERS))
def world(request, tmp_path_factory) -> World:
    char, spelled = request.param
    base = tmp_path_factory.mktemp("spelling")
    source = make_source_repo(base / "Thing")
    plan = base / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    # The names arrive AFTER the plan, as the issue's route 2 has them: on
    # main `plan` cannot write an entry for a carriage return (#199).
    old = git_out(source, "rev-parse", "HEAD").strip().decode()
    names = [f"Icon{char}", f"src/app/Icon{char}"]
    tree = tree_with(source, f"{old}^{{tree}}",
                     {name: ("100644", b"x\n") for name in names})
    head = commit_tree(source, tree, (old,))
    assert_names_are_in(source, head, names)
    git_out(source, "update-ref", "HEAD", head)
    text = plan.read_text(encoding=UTF8).replace(old, head)
    assert SRC_ENTRY in text
    text = text.replace(SRC_ENTRY,
                        "  - path: src/app/\n    leg: code\n" + SRC_ENTRY, 1)
    with plan.open("w", encoding=UTF8, newline="\n") as handle:
        handle.write(text)
    return World(source=source, plan=plan, char=char, spelled=spelled)


def check_bytes(plan: Path, work: Path) -> subprocess.CompletedProcess:
    """`check --plan <plan>` as a person runs it, its output kept as BYTES:
    `conftest.run_script` decodes text, which turns a carriage return into a
    line break before a test can see it."""
    env = blank_unnamed_pin_sources(
        {**os.environ, "LANES_LANE": "", "PYTHONIOENCODING": UTF8}, {})
    return subprocess.run(
        [sys.executable, str(ADOPT), "check", "--plan", str(plan),
         "--work-dir", str(work)],
        capture_output=True, stdin=subprocess.DEVNULL, env=env, check=False)


def printed_lines(output: bytes) -> list[str]:
    """`output` as the lines a terminal shows, split ONLY where the tool
    ended a line. Python ends one with `os.linesep`, which is `\\r\\n` on
    Windows; any other carriage return, line feed or separator is the
    tool's to have spelled."""
    return output.replace(os.linesep.encode(), b"\n").decode(UTF8).split("\n")


def test_check_prints_each_finding_on_one_readable_line(world, tmp_path):
    """THE ISSUE'S ROUTE 2, read as bytes: each FINDING is one line that
    starts with `FINDING`, and nothing `check` prints, on either stream,
    holds a character `str.isprintable` refuses."""
    done = check_bytes(world.plan, tmp_path / "work")
    assert done.returncode == 1, done.stderr + done.stdout
    stderr = printed_lines(done.stderr)
    for line in stderr + printed_lines(done.stdout):
        assert_one_readable_line(line, world.char)
    assert world.uncovered in stderr
    assert world.covered_twice in stderr
    named = [line for line in stderr if "Icon" in line]
    assert named == [world.uncovered, world.covered_twice], named


def test_execute_refuses_on_the_lines_check_prints(adopter, world, tmp_path):
    """`execute` refuses the same plan in `check`'s words, each one line, and
    creates nothing."""
    remotes = tmp_path / "remotes"
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(Namespace(
            plan=str(world.plan), source=None, local_remote_dir=remotes,
            allow_empty_leg=[], yes=True, work_dir=tmp_path / "work"))
    refusal = caught.value
    assert refusal.code == "plan-uncovered"
    said = str(refusal).split("\n")
    for line in said:
        assert_one_readable_line(line, world.char)
    assert f"  {world.uncovered}" in said
    assert f"  {world.covered_twice}" in said
    assert not remotes.exists(), "not even the directory the legs go in"


# --- `plan-stale`: the branch it names ------------------------------------

#: The two characters above that git's ref-name rules let into a branch
#: name: they refuse every ASCII control character, so a carriage return, a
#: line feed and an ESC never reach `plan-stale`.
REF_CHARACTERS = {name: CHARACTERS[name]
                  for name in ("next-line", "line-separator")}


@EACH_CHARACTER
def test_execute_refuses_a_stale_plan_spelling_the_branch(adopter, char,
                                                         spelled):
    """`_refuse_an_unrunnable_plan`'s `plan-stale` names the branch the
    source is read from. It is not a path, but it is a name a person chose,
    printed on the line beside the commits."""
    plan = adopter.Plan(Path("adoption-plan.yaml"), {
        "kind": adopter.PLAN_KIND, "mode": "in-place",
        "source": {"commit": "a" * 40},
        "legs": {"spec_path": "spec", "code_path": "code"},
        "paths": [{"path": "README.md", "leg": "root"}]})
    with pytest.raises(adopter.Refusal) as caught:
        adopter._refuse_an_unrunnable_plan(
            plan, Namespace(commit="b" * 40, branch=f"ma{char}in"))
    assert caught.value.code == "plan-stale"
    assert caught.value.detail == (
        f"the plan was written against {'a' * 12} and `ma{spelled}in` is now "
        f"at {'b' * 12}")
    assert_one_readable_line(caught.value.detail, char)


@pytest.fixture(scope="module", params=list(REF_CHARACTERS.values()),
                ids=list(REF_CHARACTERS))
def stale_world(request, tmp_path_factory):
    """A plan with every question answered, then the source's branch renamed
    to `ma<char>in` and moved on by one commit: `(plan, head, char,
    spelled)`."""
    char, spelled = request.param
    base = tmp_path_factory.mktemp("stale")
    source = make_source_repo(base / "Thing")
    plan = base / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    git_out(source, "branch", "-m", f"ma{char}in")
    old = git_out(source, "rev-parse", "HEAD").strip().decode()
    head = commit_tree(source, f"{old}^{{tree}}", (old,))
    git_out(source, "update-ref", "HEAD", head)
    return plan, head, char, spelled


def test_check_spells_the_branch_a_stale_plan_names(stale_world, tmp_path):
    plan, head, char, spelled = stale_world
    done = check_bytes(plan, tmp_path / "work")
    assert done.returncode == 1, done.stderr + done.stdout
    [stale] = [line for line in printed_lines(done.stderr)
               if line.startswith("FINDING plan-stale: ")]
    assert f" but `ma{spelled}in` is now at {head[:12]}. " in stale, stale
    assert_one_readable_line(stale, char)
