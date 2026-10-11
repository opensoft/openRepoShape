# SPDX-License-Identifier: Apache-2.0
"""A source's name is a NAME wherever adopt hands it to git (#216).

`plan`'s follow-ups come from `git grep` over the source commit: one search
per directory the plan sends to the spec leg, for that directory's name,
restricted to the entries it sends to the code leg. Both inputs are names the
source chose, and git read each as something else. The spec directory sat
where git reads OPTIONS: `-notes/` was a usage error that left no follow-up,
and `-O<cmd>/` was `--open-files-in-pager`, a command git runs through a
shell. The code entries were PATHSPECS: `:cache` read as the magic `:` and
`*` matched files in the spec leg. `-l` C-quoted a name outside printable
ASCII, `color.ui=always` wrapped each name in escapes, and a grep that failed
was read as "no file names it". Each of those is one test here, through
`plan` itself except the failing grep, which `plan` cannot provoke, and each
measured failing on main at a5b09c3; `notes/` and `s?c/` are the controls
that already passed there.

The split's forced `git add -f` asks the same question of a path the shape
wrote THROUGH a symlink the plan kept in the root: where it landed is the
link's target, a source name, and git read `:ci/...` as magic, `:!ci/...` as
an exclude and `ga[0]/...` as a glob.

Local repositories only, no network, no `git filter-repo`. The tests whose
names an NTFS disk cannot hold (`:`, `*`, `?`, a line break) or that make a
symlink on the disk skip on Windows; the rest run there.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ADOPT, REPO, git, make_source_repo, write_plan

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml  # noqa: E402
from shape_materialize import CommandFailed, Materialized  # noqa: E402

#: Names Windows cannot put on its disk -- `:`, `*`, `?` and a line break are
#: illegal in an NTFS name, and git for Windows refuses them in the index
#: under its default `core.protectNTFS` -- and symlinks it checks out as
#: plain files. The defects these guard are POSIX layouts, and the POSIX legs
#: of CI run them.
posix_only = pytest.mark.skipif(
    sys.platform == "win32",
    reason="NTFS cannot hold this name, or this symlink, on the disk")

#: A code file that names a spec directory, the way a harness names
#: `contracts/`.
READER = "SPEC = '{}'\n"
SPEC_PATH = "spec"
CODE_PATH = "code"


def follow_up(hit: str, spec_dir: str) -> str:
    """The line `plan` writes for a code file that names `spec_dir`: the
    wording main has always written, so an ordinary name is unchanged."""
    return (f"{CODE_PATH}/{hit} names `{spec_dir}`, which moves to the spec "
            f"leg: it must read across the assembly root — "
            f"`../{SPEC_PATH}/{spec_dir}` relative to `{CODE_PATH}/` — or "
            "take the path from the environment")


def planned(source: Path, base: Path) -> dict:
    out = base / "adoption-plan.yaml"
    result = write_plan(source, out)
    assert result.returncode == 0, result.stderr + result.stdout
    return load_yaml(out)


def named(plan: dict) -> list[str]:
    """Every follow-up that says a code file names a spec directory."""
    return [str(item) for item in plan["follow_ups"] if " names `" in str(item)]


def legs(plan: dict) -> dict:
    return {str(entry["path"]): entry["leg"] for entry in plan["paths"]}


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_literal_names", ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# `plan`'s follow-ups: the spec directory is a pattern, each code entry a path
# ---------------------------------------------------------------------------

NOTES = {"notes/one.md": "# notes\n", "notes/two.md": "# more\n"}

#: `(tree, the spec directory, the code entries, the files that name it)`.
#: The spec directories hold `.md` files and the code entries `.py` files, so
#: extension-majority puts each in the leg the case needs.
NAME_CLASSES = [
    pytest.param(
        {**NOTES, "src/reader.py": READER.format("notes/"),
         "src/other.py": "VALUE = 1\n"},
        "notes/", ["src/"], ["src/reader.py"], id="control-notes"),
    pytest.param(
        {"-notes/one.md": "# notes\n", "-notes/two.md": "# more\n",
         "src/reader.py": READER.format("-notes/"),
         "src/other.py": "VALUE = 1\n"},
        "-notes/", ["src/"], ["src/reader.py"],
        id="a-spec-directory-starting-with-a-dash"),
    pytest.param(
        {**NOTES, ":cache/a.py": READER.format("notes/"),
         ":cache/b.py": "VALUE = 2\n", "src/other.py": "VALUE = 1\n"},
        "notes/", [":cache/", "src/"], [":cache/a.py"],
        id="a-code-entry-starting-with-a-colon", marks=posix_only),
    pytest.param(
        {"notes/one.md": "# notes\n", "notes/two.md": "see notes/ above\n",
         "*/a.py": "VALUE = 1\n", "*/b.py": "VALUE = 2\n",
         "src/reader.py": READER.format("notes/")},
        "notes/", ["*/", "src/"], ["src/reader.py"],
        id="a-code-entry-named-star", marks=posix_only),
    pytest.param(
        {**NOTES, "sec/plan.md": "see notes/ for the plan\n",
         "sec/other.md": "# other\n", "s?c/a.py": "VALUE = 1\n",
         "s?c/b.py": "VALUE = 2\n", "src/reader.py": READER.format("notes/")},
        "notes/", ["s?c/", "src/"], ["src/reader.py"],
        id="control-a-code-entry-with-a-question-mark", marks=posix_only),
    pytest.param(
        {**NOTES, "src/Übersicht.py": READER.format("notes/"),
         "src/other.py": "VALUE = 1\n"},
        "notes/", ["src/"], ["src/Übersicht.py"],
        id="a-code-file-named-outside-ascii"),
]


@pytest.mark.parametrize(("tree", "spec_dir", "code", "hits"), NAME_CLASSES)
def test_each_file_that_names_a_spec_directory_is_a_follow_up(
        tmp_path, tree, spec_dir, code, hits):
    """Exactly the code files that name the spec directory, each spelled as
    the tree spells it. On main: `-notes/` was git's usage error (exit 129)
    and no follow-up; `:cache` was searched as the pathspec `cache` and
    found nothing; `*` also searched the spec leg and named
    `code/notes/two.md`; and `Übersicht.py` was written
    `code/"src/\\303\\234bersicht.py"`. `?` never widened, and does not."""
    source = make_source_repo(tmp_path / "Thing", tree=tree, edits=())
    plan = planned(source, tmp_path)
    rows = legs(plan)
    assert rows[spec_dir] == "spec", rows
    assert all(rows[entry] == "code" for entry in code), rows
    assert named(plan) == [follow_up(hit, spec_dir) for hit in hits]


def test_a_spec_directory_named_like_the_pager_option_runs_nothing(tmp_path):
    """`-O<cmd>` is `git grep --open-files-in-pager`, which git runs through
    a shell. Read as that option, the directory's name made the planned
    commit's hash the PATTERN, the WORKTREE was searched for it, and a
    tracked file holding it was handed to `<cmd>`: on main this created
    `pager-ran` in the source and wrote no follow-up. Now the name is the
    pattern, the commit is the commit, and nothing runs."""
    spec_dir = "-Otouch pager-ran;/"
    source = make_source_repo(
        tmp_path / "Thing", edits=(),
        tree={f"{spec_dir}one.md": "# notes\n", f"{spec_dir}two.md": "# more\n",
              "src/reader.py": READER.format(spec_dir),
              "src/other.py": "VALUE = 1\n"})
    commit = git("rev-parse", "HEAD", cwd=source).stdout.strip()
    # The premise the issue measured: a file under a code entry, in the index
    # and holding the planned commit's hash. A clean checkout of that commit
    # cannot hold its own hash, and git skips an untracked file.
    (source / "src" / "scratch.txt").write_text(f"checked against {commit}\n",
                                               encoding="utf-8")
    git("add", "--", "src/scratch.txt", cwd=source)
    before = sorted(os.listdir(source))

    plan = planned(source, tmp_path)

    assert sorted(os.listdir(source)) == before, "git ran the pager"
    assert legs(plan)[spec_dir] == "spec"
    assert named(plan) == [follow_up("src/reader.py", spec_dir)]


def test_a_colour_setting_in_the_source_is_not_in_a_follow_up(tmp_path):
    """`color.ui=always` in the source's own config made git colour each
    name it listed even into a pipe: on main the follow-up read
    `code/src/reader.py\\x1b[m names ...`, an escape byte in the plan."""
    source = make_source_repo(
        tmp_path / "Thing", edits=(),
        tree={**NOTES, "src/reader.py": READER.format("notes/"),
              "src/other.py": "VALUE = 1\n"})
    git("config", "color.ui", "always", cwd=source)
    plan = planned(source, tmp_path)
    assert named(plan) == [follow_up("src/reader.py", "notes/")]
    assert not any("\x1b" in str(item) for item in plan["follow_ups"])


@posix_only
def test_a_name_with_a_line_break_or_a_byte_outside_utf8_is_one_spelled_line(
        tmp_path):
    """git's `-z` gives a name as its bytes, and the follow-up spells it as a
    question spells a path: `\\n` for the line break, `\\xe9` for the byte,
    on one line of UTF-8. On main each came back in git's C-quoted
    spelling, quotes and octal included. The two files are put in the TREE
    (`update-index -z --index-info`) and never on the disk, which macOS
    refuses for a name that is not UTF-8."""
    source = make_source_repo(
        tmp_path / "Thing", edits=(),
        tree={**NOTES, "src/other.py": "VALUE = 1\n"})
    blob = subprocess.run(
        ["git", "hash-object", "-w", "--stdin"], cwd=str(source),
        input=READER.format("notes/").encode(), capture_output=True,
        check=True).stdout.decode().strip()
    records = b"".join(b"100644 " + blob.encode() + b"\t" + name + b"\x00"
                       for name in (b"src/line\nbreak.py", b"src/caf\xe9.py"))
    subprocess.run(["git", "update-index", "-z", "--index-info"],
                   cwd=str(source), input=records, check=True)
    git("-c", "user.name=Source Human", "-c", "user.email=human@source.invalid",
        "commit", "-qm", "Two awkward names", cwd=source)

    plan = planned(source, tmp_path)

    assert named(plan) == [follow_up("src/caf\\xe9.py", "notes/"),
                           follow_up("src/line\\nbreak.py", "notes/")]


def test_a_grep_that_fails_is_said_and_never_read_as_no_file(adopter,
                                                            tmp_path):
    """A `git grep` that exits past 1 has answered nothing. On main its
    stdout was read anyway -- empty -- and the plan said nothing about the
    spec directory; now the follow-up says git could not search, what git
    said, and what to look for by hand. The commit here is one the source
    does not have, which git refuses with exit 128."""
    path = make_source_repo(
        tmp_path / "Thing", edits=(),
        tree={**NOTES, "src/reader.py": READER.format("notes/"),
              "src/other.py": "VALUE = 1\n"})
    source = adopter.Source.open(str(path), tmp_path / "work")
    entries = adopter.walk(adopter.PathPolicy.load(adopter.PATH_POLICY),
                           [(name, size) for name, _, _, size in source.tree()])
    assert adopter.cross_leg_references(source, entries, SPEC_PATH,
                                        CODE_PATH) \
        == [follow_up("src/reader.py", "notes/")]

    missing = adopter.Source(source.path, None, source.branch, "f" * 40)
    said = adopter.cross_leg_references(missing, entries, SPEC_PATH, CODE_PATH)

    # git's own words differ between versions; its exit and its `fatal:` do
    # not, and the sentence around them is this tool's.
    assert len(said) == 1, said
    assert said[0].startswith(
        "git could not search the files moving to the code leg for `notes/` "
        "(`git grep` exited 128: fatal: "), said[0]
    assert said[0].endswith(
        "); find the ones that name it by hand: each must read across the "
        "assembly root once `notes/` moves to the spec leg"), said[0]
    assert "\n" not in said[0]


# ---------------------------------------------------------------------------
# The split's forced add: a path that landed through a link is a path
# ---------------------------------------------------------------------------

WORKFLOW = ".github/workflows/validate.yml"
PIN = "contracts/shape-pin.yaml"
#: The source hides every `validate.yml`, so the shape's workflow is staged
#: by the forced add alone, wherever the link put it: the case that add is
#: for (#167). `ga0/` and `*.env` hide what must never be forced.
IGNORE = "validate.yml\nga0/\n*.env\n"
#: Hidden by IGNORE, and so never in the clone `execute` splits until
#: something writes them there. The test does, so that a forced add reading a
#: name as more than its path has something to sweep in.
STRAY = ("ga0/workflows/validate.yml", "secret.env")


@posix_only
@pytest.mark.parametrize("target", [":ci", ":!ci", "ga[0]"],
                         ids=["magic-colon", "magic-exclude", "glob"])
def test_a_shape_file_written_through_a_link_is_staged_by_its_own_name(
        adopter, tmp_path, target):
    """The plan kept `.github -> <target>` and `<target>/` in the root, so
    the shape's workflow landed at `<target>/workflows/validate.yml`, which
    the source's `.gitignore` hides: only the forced add stages it, by that
    name. On main git read the name as a pathspec. `:ci/...` was the magic
    `:` and the path `ci/...`, which matched nothing, and the add died
    (`fatal: pathspec ... did not match any files`); `:!ci/...` was an
    exclude, which forced nothing by that name, so the split lacked the
    workflow; and `ga[0]/...` was a glob that also forced the ignored
    `ga0/workflows/validate.yml`. Now each name is the path it spells: that
    file and the pin are staged, and nothing else."""
    source = make_source_repo(
        tmp_path / "source", edits=(),
        tree={"README.md": "# Thing\n", ".gitignore": IGNORE,
              f"{target}/workflows/ci.yml": "on: [push]\n"})
    os.symlink(target, source / ".github")
    git("add", "-A", "--", ".", cwd=source)
    git("-c", "user.name=Source Human", "-c", "user.email=human@source.invalid",
        "commit", "-qm", "Link .github", cwd=source)
    assembly = tmp_path / "assembly"
    git("clone", "-q", str(source), str(assembly), cwd=tmp_path)
    for name in (WORKFLOW, PIN, *STRAY):
        (assembly / name).parent.mkdir(parents=True, exist_ok=True)
        (assembly / name).write_text(f"{name}\n", encoding="utf-8")
    landed = f"{target}/workflows/validate.yml"
    assert (assembly / landed).is_file()
    # The premise: each is ignored, so no `git add -A` stages it. Asked of
    # the whole tree, because `check-ignore` takes each name as a pathspec.
    ignored = git("status", "--porcelain", "-z", "--ignored=traditional",
                  "--untracked-files=all", cwd=assembly).stdout.split("\0")
    assert {f"!! {name}" for name in (landed, *STRAY)} <= set(ignored), ignored

    materialized = Materialized()
    materialized.written = [WORKFLOW, PIN]
    try:
        adopter._stage_the_split(assembly, materialized)
    except CommandFailed as exc:
        pytest.fail(f"the forced add read a name as a pathspec: {exc}")

    staged = git("diff", "--cached", "--name-status", "-z",
                 cwd=assembly).stdout.split("\0")
    pairs = sorted(zip(staged[0:-1:2], staged[1::2]))
    assert pairs == sorted([("A", landed), ("A", PIN)])
