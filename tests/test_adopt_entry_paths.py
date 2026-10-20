# SPDX-License-Identifier: Apache-2.0
"""An entry's path is a fact of the source, judged by ONE test (#196).

On main at e4decfb `check` asked nothing of a plan entry's path and `execute`
asked `checked_value`, whose alphabet (`SAFE_ARG_RE`) is meant for the values
that are options -- a branch, a repository name, a leg's mount path. A source
holding `My Notes.md` therefore checked `plan ok`, and `execute` refused the
same plan as `unsafe-value`. Now both ask `entry_path_problem`: `check`
reports `plan-unsafe-path` and `execute` refuses it in `check`'s words before
any leg exists, and what a source tree legitimately holds -- a space, a letter
outside ASCII, `#`, `?`, `[`, `;` -- is extracted, because every place such a
path reaches `git` reads it literally.

`plan` asks the same test since #319: an entry it refuses is written
`leg: null` with a question giving the reason and the only two answers,
`root` and `drop`, where `plan` used to answer `spec` for it and leave
`check` to refuse that answer.

NO NETWORK AND NO GITHUB. `git filter-repo` is needed only by the end-to-end
test at the bottom, which skips without it as `test_adopt_e2e.py` does; on a
machine that has none, it is the tests above it that run. They
load `adopt-project.py` through importlib and stub its probe for the tool, as
`test_adopt_execute_refusals.py` does: every refusal under test is raised
before the tool would be used.

PLAN PATHS STAY POSIX, and a name that only a POSIX disk can hold (a tab, a
`?`) is created only where `os.name` is not `nt`. A name outside ASCII is
created only where the file system's encoding can spell it, which on every
CI runner it can (Windows is UTF-8 since PEP 529).
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import (ADOPT, REPO, blank_unnamed_pin_sources, git,
                      make_source_repo, run_script, write_plan)

PROJECT = "Northwind"
UTF8 = "utf-8"
UNSAFE = "plan-unsafe-path"
REMOTES, WORK = "remotes", "work"
POSIX_ONLY = pytest.mark.skipif(
    os.name == "nt", reason="NTFS cannot hold this character in a file name")
needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

#: A name outside ASCII, in the Latin-1 range, so that a console still on a
#: Windows code page can print `plan`'s table of it too.
UMLAUT = "\u00dcbersicht.md"


def spellable(name: str) -> bool:
    """Whether this file system's encoding can spell `name` at all."""
    try:
        name.encode(sys.getfilesystemencoding())
    except UnicodeEncodeError:
        return False
    return True


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_entry_paths", ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def no_filter_repo_probe(adopter, monkeypatch):
    """No test here that runs `cmd_execute` in process gets as far as using
    `git filter-repo`; the refusal before it is what is under test."""
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)


def execute_args(tmp_path: Path, plan: Path) -> Namespace:
    """What `main` hands `cmd_execute`: `--yes`, a local remote directory that
    does not exist yet, and a work directory."""
    return Namespace(plan=str(plan), source=None,
                     local_remote_dir=tmp_path / REMOTES, allow_empty_leg=[],
                     yes=True, work_dir=tmp_path / WORK)


def no_leg_was_created(tmp_path: Path) -> None:
    assert not (tmp_path / REMOTES).exists()
    for role in ("spec", "code"):
        assert not (tmp_path / WORK / f"{PROJECT}-{role}").exists()


def run_check(plan: Path):
    return run_script(ADOPT, "check", "--plan", str(plan))


#: The `resolution:` line `answer` writes below the `leg:` it answers.
RESOLVED = "    resolution: \"answered by the test\"\n"


def answer(plan: Path, spelled: str, old: str, new: str) -> None:
    """Re-answer the entry whose `path:` is written `spelled`, from `old` to
    `new`, LF as `plan` wrote it (see `conftest.resolve`). An entry this
    helper answered before keeps its one `resolution:` line: a second one
    below it would be a key written twice in one mapping, which the reader
    refuses since #917, and `check` with it."""
    text = plan.read_text(encoding=UTF8)
    needle = f"  - path: {spelled}\n    leg: {old}\n"
    assert needle in text, f"{spelled} is not an entry with leg: {old}"
    if needle + RESOLVED in text:
        needle += RESOLVED
    with plan.open("w", encoding=UTF8, newline="\n") as handle:
        handle.write(text.replace(
            needle, f"  - path: {spelled}\n    leg: {new}\n" + RESOLVED, 1))


def planned(tmp_path: Path, tree: dict,
            edits: tuple = ()) -> tuple[Path, Path]:
    """`(source, plan)` for a source holding `tree`, planned as a person
    would, with nothing left to answer."""
    source = make_source_repo(tmp_path / "Thing", tree, edits=edits)
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    assert "leg: null" not in plan.read_text(encoding=UTF8)
    return source, plan


# --- the one test ----------------------------------------------------------

ADMITTED = [
    "My Notes.md", "docs/User Guide.md", "docs/", UMLAUT, "\u6587\u66f8.md",
    "#notes.md", "q?.md", "*", "[id].tsx", ":!keep.md", "a-b.md",
    "semi;colon$(x)'\"&.md", "a+b~c@d.md", " lead.md", "trail.md ",
    "back\\slash.md", "regex:x.md", "glob:y.md", "literal:z.md", "a=>b.md",
    "x==y.md",
]

#: What git or `git filter-repo` would NOT take as the path it is, with what
#: the finding says: the misreadings `entry_path_problem` refuses.
MISREAD = [
    ("", "it is empty: a `literal:` line with nothing after it matches"),
    ("docs\nregex:.*", "line feed (`\\n`), which ends its line"),
    ("Icon\r", "ends in a carriage return (`\\r`), which `git filter-repo` "
                "strips from the end of each line of the path list it reads, "
                "so its line would name `Icon`, another path"),
    # Nothing is left once the carriage returns are stripped: the line is
    # `literal:` alone, which matches every path, as the empty path's does.
    ("\r", "so its line would be `literal:` alone, which matches every path, "
            "so `git filter-repo` would put the whole tree in the leg"),
    ("\r\r", "so its line would be `literal:` alone, which matches every"),
    ("nul\x00", "NUL (`\\x00`), which no command line can carry"),
    # A surrogate no byte of a path is read as: `write_paths_listing` cannot
    # write it. U+DC80 to U+DCFF, the bytes that are not UTF-8, are POLICY's.
    ("\ud800.md", "`\\ud800`, a surrogate no byte of a path is read as"),
    ("x\udc7f.md", "`\\udc7f`, a surrogate no byte of a path is read as"),
    ("y\udd00.md", "`\\udd00`, a surrogate no byte of a path is read as"),
    ("a==>b.md", "`==>`"),
    ("docs/a==>b/", "`==>`"),
    # A misreading is told before a policy reason the same name also has.
    ("tab\t==>b.md", "`==>`"),
]

#: What git and `git filter-repo` take literally -- measured, each as one
#: `literal:` line and as `git --literal-pathspecs rm` -- and this tool still
#: refuses to move into a leg, as policy, with what the finding says.
POLICY = [
    ("   ", "nothing but whitespace"),
    (" ", "nothing but whitespace"),
    ("-dash.md", "begins with `-`"),
    ("--output=never-written", "begins with `-`"),
    ("tab\there.md", "control character `\\t`"),
    ("a\rb.md", "control character `\\r`"),
    ("esc\x1b[31m.md", "control character `\\x1b`"),
    ("del\x7f.md", "control character `\\x7f`"),
    ("nel\x85.md", "control character `\\x85`"),
    ("vt\x0b.md", "control character `\\x0b`"),
    ("line\u2028sep.md", "line separator `\\u2028`"),
    # A byte that is not UTF-8, as `Source.tree` keeps it: since #199 the
    # path list carries it byte-exact.
    ("caf\udce9.md", "`\\udce9`, which is not UTF-8"),
    ("docs/\udcff/", "`\\udcff`, which is not UTF-8"),
    ("\udc80.md", "`\\udc80`, which is not UTF-8"),
]


@pytest.mark.parametrize("path", ADMITTED)
def test_what_a_source_tree_holds_is_admitted(adopter, path):
    """A space, a letter outside ASCII, a `#`, a wildcard, a leading `:` and
    a filter-repo directive's spelling: each reaches `git` literally, as a
    `literal:` line of the filter's path list and a pathspec after `--` to
    `git --literal-pathspecs rm`."""
    assert adopter.entry_path_problem(path) is None


@pytest.mark.parametrize("path,said", MISREAD)
def test_what_git_or_filter_repo_would_misread_is_refused(adopter, path,
                                                           said):
    """Each finding says what would be misread, and never calls it policy."""
    problem = adopter.entry_path_problem(path)
    assert problem is not None and said in problem
    assert "as policy" not in problem


@pytest.mark.parametrize("path,said", POLICY)
def test_what_policy_refuses_says_it_is_policy_and_not_a_misreading(
        adopter, path, said):
    """A name git and `git filter-repo` take literally is refused as policy,
    and the finding says so: it must not give a misreading's reason, as it
    did when a tab was told that a line break would end its line."""
    problem = adopter.entry_path_problem(path)
    assert problem is not None and said in problem
    assert ("which `execute` refuses as policy, though git and `git "
            "filter-repo` would take it literally") in problem
    for misreading in ("line of its own", "ends its line", "strips",
                       "matches every path", "rename"):
        assert misreading not in problem


# --- `check` and `execute` agree -------------------------------------------

def test_a_source_with_spaces_and_letters_beyond_ascii_checks_ok_and_runs(
        adopter, tmp_path):
    """THE ISSUE'S OWN CASE, where every runner can make it: `check` prints
    `plan ok`, and `execute` raises no refusal over the entries' paths and
    hands each one on as the source spells it."""
    tree = {"My Notes.md": "notes\n", "docs/User Guide.md": "guide\n",
            "docs/architecture.md": "arch\n", "run tests.py": "print(1)\n",
            "src/app.py": "VALUE = 1\n", "README.md": "# Thing\n"}
    if spellable(UMLAUT):
        tree[UMLAUT] = "ueber\n"
    source, plan = planned(tmp_path, tree)
    checked = run_check(plan)
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert "plan ok" in checked.stdout
    loaded = adopter.Plan.load(plan)
    assert adopter._refuse_what_check_finds(
        loaded, loaded.open_source(str(source), tmp_path / "read")) is None
    paths_for = adopter._leg_paths(loaded)
    assert "My Notes.md" in paths_for["spec"]
    assert "docs/" in paths_for["spec"]
    assert "run tests.py" in paths_for["code"]
    if spellable(UMLAUT):
        assert UMLAUT in paths_for["spec"]


#: Hand edits that put a path `execute` cannot extract where `specs/` was,
#: each as the plan file spells it and as the finding must name it: one for
#: each class `entry_path_problem` refuses. An empty path is the one whose
#: `literal:` line would be worst: `git filter-repo` matches an empty path
#: against every path, so the leg would take the whole tree.
HAND_EDITS = {
    "empty": ('""', "``", "it is empty"),
    "whitespace-only": ('"   "', "`   `", "nothing but whitespace"),
    "leading-dash": ("--output=never-written", "`--output=never-written`",
                     "begins with `-`"),
    "control-character": ('"spe\\tcs/"', "`spe\\tcs/`",
                          "control character `\\t`"),
    "rename-arrow": ('"specs==>elsewhere/"', "`specs==>elsewhere/`", "`==>`"),
}
ONE_PER_EDIT = pytest.mark.parametrize("edit", sorted(HAND_EDITS))


def hand_edited(tmp_path: Path, edit: str) -> tuple[Path, Path]:
    """`(source, plan)`: the synthetic source, its questions answered, and
    the `specs/` entry's path replaced as `HAND_EDITS[edit]` says."""
    source = make_source_repo(tmp_path / "Thing")
    plan = tmp_path / "adoption-plan.yaml"
    assert write_plan(source, plan, project=PROJECT).returncode == 0
    text = plan.read_text(encoding=UTF8)
    for path, leg in (("examples/", "spec"), (".claude/", "root"),
                      ("release.yaml", "root")):
        text = text.replace(f"  - path: {path}\n    leg: null\n",
                            f"  - path: {path}\n    leg: {leg}\n", 1)
    assert "leg: null" not in text
    spelled = HAND_EDITS[edit][0]
    text = text.replace("  - path: specs/\n", f"  - path: {spelled}\n", 1)
    with plan.open("w", encoding=UTF8, newline="\n") as handle:
        handle.write(text)
    return source, plan


@ONE_PER_EDIT
def test_check_reports_the_path_first_and_says_what_to_do(tmp_path, edit):
    """The finding names the path as `_spelled` spells it, comes before the
    uncovered files the same edit leaves, and the remediation says the plan
    cannot respell a path of the source."""
    _, plan = hand_edited(tmp_path, edit)
    _, named, said = HAND_EDITS[edit]
    result = run_check(plan)
    assert result.returncode == 1, result.stderr + result.stdout
    findings = [line for line in result.stderr.splitlines()
                if line.startswith("FINDING ")]
    assert findings[0].startswith(f"FINDING {UNSAFE}: {named} has leg: spec")
    assert said in findings[0]
    assert any(line.startswith("FINDING plan-uncovered: `specs/")
               for line in findings)
    assert "Rename the path in the source, commit, and re-run `plan`" \
        in result.stderr
    assert "plan ok" not in result.stdout


@ONE_PER_EDIT
def test_execute_refuses_it_in_checks_words_before_any_leg(adopter, tmp_path,
                                                           edit):
    _, plan = hand_edited(tmp_path, edit)
    printed = [line for line in run_check(plan).stderr.splitlines()
               if line.startswith("FINDING ")]
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(execute_args(tmp_path, plan))
    assert caught.value.code == UNSAFE
    assert f"  {printed[0]}" in caught.value.detail.splitlines()
    assert "Rename the path in the source" in caught.value.remediation
    no_leg_was_created(tmp_path)


def asked(tmp_path: Path, tree: dict, answers: dict) -> tuple[Path, Path]:
    """`(source, plan)` for a source holding `tree`, with each entry
    `answers` names, as the plan file spells it, answered as `answers`
    says. Every other entry needs no answer: `plan` asks only about those
    (#319)."""
    source = make_source_repo(tmp_path / "Thing", tree, edits=())
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    for spelled, leg in answers.items():
        answer(plan, spelled, "null", leg)
    assert "leg: null" not in plan.read_text(encoding=UTF8)
    return source, plan


@pytest.mark.parametrize("answered", ["root", "drop"])
def test_an_entry_answered_root_or_drop_is_not_judged(adopter, tmp_path,
                                                      answered):
    """A path that is never extracted reaches no line of the filter's list:
    `root` keeps it where it is and `drop` hands it to `git rm` after `--`.
    So the remediation's `drop` is true; answered `spec` it is refused.
    `plan` asks about it since #319, so `spec` is answered here by hand, as
    `plan` used to write it."""
    source, plan = asked(tmp_path, {"-notes.md": "notes\n",
                                    "src/app.py": "VALUE = 1\n",
                                    "docs/spec.md": "# spec\n"},
                         {'"-notes.md"': "spec"})
    findings = [line for line in run_check(plan).stderr.splitlines()
                if line.startswith(f"FINDING {UNSAFE}:")]
    assert findings == [f"FINDING {UNSAFE}: `-notes.md` has leg: spec, and "
                        "`execute` will not extract it into a leg: "
                        f"{adopter.entry_path_problem('-notes.md')}"]
    assert "refuses as policy" in findings[0]
    answer(plan, '"-notes.md"', "spec", answered)
    checked = run_check(plan)
    assert checked.returncode == 0, checked.stderr + checked.stdout
    loaded = adopter.Plan.load(plan)
    assert adopter._refuse_what_check_finds(
        loaded, loaded.open_source(str(source), tmp_path / "read")) is None


@POSIX_ONLY
def test_a_control_character_in_the_source_is_found_and_refused(adopter,
                                                                tmp_path):
    """Not a hand edit: the SOURCE holds `notes\\t.md`, `plan` writes it into
    the plan as it stands, and the plan parses. Answered `spec` -- what
    `plan` wrote for it before #319 -- `check` names it and `execute`
    refuses it before any leg exists."""
    source, plan = asked(tmp_path, {"notes\t.md": "notes\n",
                                    "src/app.py": "VALUE = 1\n"},
                         {'"notes\\t.md"': "spec"})
    result = run_check(plan)
    assert result.returncode == 1, result.stderr + result.stdout
    assert f"FINDING {UNSAFE}: `notes\\t.md` has leg: spec" in result.stderr
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(execute_args(tmp_path, plan))
    assert caught.value.code == UNSAFE
    no_leg_was_created(tmp_path)
    assert git("branch", "--format=%(refname:short)",
               cwd=source).stdout.split() == ["main"]


# --- `plan` asks about them (#319) ----------------------------------------
#
# On main at 71b58a1 `plan` asked `entry_path_problem` nothing: each name
# below that a rule places was written `leg: spec`, `review_required:
# false`, no question, and `check` then refused that answer as
# `plan-unsafe-path`; `Icon\r` and `   `, which no rule places, were asked
# the policy's question, which offers `spec` and `code` too. Now each is
# asked, with the reason, and offered the only two answers `execute` takes.

#: `(the name as git records it, as the plan file spells it, a piece of the
#: question as the plan FILE shows it)`: one of each kind
#: `entry_path_problem` refuses that a source tree can hold, at the top
#: level, where it is an entry of its own. `.md` is spec by the extension
#: table; `Icon\r` and `   ` no rule places. The piece is the writer's
#: escaping measured (`repo_shape.double_quoted`): the question spells a
#: character as `_spelled` does, `\t` as a backslash and a `t`, and the
#: file doubles that backslash, so the line reads back as the question.
#: `{byte}` is the byte 0xE9 as `_spelled_character` spells it, doubled as
#: the file doubles it: `\xe9` at 71b58a1, and #329 respells it.
REFUSED_IN_THE_SOURCE = [
    pytest.param(b"-notes.md", '"-notes.md"',
                 "because it begins with `-`, which `execute` refuses as "
                 "policy", id="leading-dash"),
    pytest.param(b"notes\t.md", '"notes\\t.md"',
                 "because it holds the control character `\\\\t`, which",
                 id="tab"),
    pytest.param(b"a\rb.md", '"a\\rb.md"',
                 "because it holds the control character `\\\\r`, which",
                 id="carriage-return-inside"),
    pytest.param(b"Icon\r", '"Icon\\r"',
                 "because it ends in a carriage return (`\\\\r`), which `git "
                 "filter-repo` strips from the end of each line of the path "
                 "list it reads, so its line would name `Icon`, another "
                 "path. So", id="carriage-return-at-the-end"),
    pytest.param(b"a\nb.md", '"a\\nb.md"',
                 "because it holds a line feed (`\\\\n`), which ends its line",
                 id="line-feed"),
    pytest.param(b"caf\xe9.md", '"caf\\udce9.md"',
                 "because it holds `{byte}`, which is not UTF-8",
                 id="not-utf8"),
    pytest.param(b"a==>b.md", '"a==>b.md"',
                 "because it holds `==>`, which `git filter-repo "
                 "--paths-from-file` reads as a rename", id="rename-arrow"),
    pytest.param(b"   ", '"   "', "because it is nothing but whitespace",
                 id="whitespace-only"),
]

#: How the question `plan` asks about such a path ends, whatever it is.
ONLY_ROOT_OR_DROP = (
    "So `root` or `drop` is the only answer `execute` takes for it. To put "
    "it in a leg, rename it in the source, commit, and re-run `plan`.")

#: The files beside it, which `plan` places with no question.
BESIDE = {"README.md": "# Thing\n", "docs/guide.md": "# guide\n",
          "src/main.py": "print(1)\n"}


def indexed_source(base: Path, name: bytes) -> Path:
    """A source holding `BESIDE` and `name` at the top level, the name put
    straight into git's index and committed as `git add` records it, so no
    file system has to hold it (NTFS holds no tab or carriage return, APFS
    no byte that is not UTF-8). `core.protectNTFS` is off for the two calls
    that write it, as in `test_adopt_plan_escapes.py`: nothing here checks
    it out. Skipped where git does not keep the name in the tree, which
    only git can say: `update-index` ignores a path it will not record."""
    source = make_source_repo(base / "Thing", BESIDE, edits=())
    unguarded = ("-c", "core.protectNTFS=false")
    blob = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                          cwd=str(source), input=b"notes\n",
                          capture_output=True, check=True).stdout.strip()
    added = subprocess.run(
        ["git", *unguarded, "update-index", "--add", "-z", "--index-info"],
        cwd=str(source), input=b"100644 " + blob + b"\t" + name + b"\0",
        capture_output=True, check=False)
    if added.returncode:
        pytest.skip(f"git update-index refuses {name!r} here: "
                    f"{added.stderr!r}")
    git(*unguarded, "-c", "user.name=Source Human",
        "-c", "user.email=human@source.invalid",
        "commit", "-q", "-m", "Add a name execute refuses", cwd=source)
    held = subprocess.run(["git", "ls-tree", "-r", "-z", "--name-only",
                           "HEAD"], cwd=str(source), capture_output=True,
                          check=True).stdout.split(b"\0")
    if name not in held:
        pytest.skip(f"git does not keep {name!r} in a tree here")
    return source


def plan_in_bytes(source: Path, plan: Path) -> subprocess.CompletedProcess:
    """`plan`, as `conftest.write_plan` runs it, answered in BYTES and in
    UTF-8 on every platform: a name printed raw, `Icon\\r`, would read as
    `Icon\\n` through text mode, and the policy's question holds an em
    dash."""
    env = blank_unnamed_pin_sources(
        {**os.environ, "LANES_LANE": "", "PYTHONIOENCODING": UTF8}, {})
    return subprocess.run(
        [sys.executable, str(ADOPT), "plan", "--source", str(source),
         "--project", PROJECT, "--org", "testorg", "--elected-by",
         "Test Human", "--elected-on", "2026-09-02", "--out", str(plan)],
        capture_output=True, env=env, stdin=subprocess.DEVNULL, check=False)


def expected_question(adopter, name: str) -> str:
    """The question `plan` asks about `name`: after the policy's own, when it
    asks one, or after where the rules put it; then why `execute` will not
    extract it, in `entry_path_problem`'s words, and the two answers."""
    verdict = adopter.PathPolicy.load(adopter.PATH_POLICY).classify_file(name)
    tail = (f" into a leg as it is named, because "
            f"{adopter.entry_path_problem(name)}. {ONLY_ROOT_OR_DROP}")
    if verdict.leg:
        return (f"The rules put this path in the {verdict.leg} leg (rule "
                f"`{verdict.rule}`), but `execute` will not extract it"
                + tail)
    return f"{verdict.question} But `execute` will not extract this path" \
        + tail


@pytest.mark.parametrize("name, spelled, in_the_file", REFUSED_IN_THE_SOURCE)
def test_plan_asks_about_a_path_execute_refuses(adopter, tmp_path, name,
                                                spelled, in_the_file):
    """THE ISSUE. `plan` writes `leg: null`, `review_required: true` and a
    question saying `execute` will not extract the path as it is named, why,
    and that `root` or `drop` is the only answer; it prints that question
    with the paths still to answer. `check` and `execute` say of the plan as
    written what they say of any entry still asked: `plan-unsafe-path`
    (`leg: null`, judged so the person knows what `spec` would meet) and
    `plan-unresolved`, and `execute` refuses before any leg exists."""
    text_name = name.decode(UTF8, "surrogateescape")
    in_the_file = in_the_file.replace(
        "{byte}", adopter._spelled_character("\udce9").replace("\\", "\\\\"))
    source = indexed_source(tmp_path, name)
    plan = tmp_path / "adoption-plan.yaml"
    written = plan_in_bytes(source, plan)
    assert written.returncode == 0, written.stderr + written.stdout
    question = expected_question(adopter, text_name)
    assert in_the_file.replace("\\\\", "\\") in question
    assert ONLY_ROOT_OR_DROP in question

    row = {str(row["path"]): row
           for row in adopter.load_yaml(plan)["paths"]}[text_name]
    assert (row["leg"], row["review_required"], row["confidence"]) == (
        None, True, "review")
    assert row["question"] == question
    raw = plan.read_bytes().decode(UTF8)
    question_line = f"    question: {adopter.y(question)}"
    assert raw.count(f"\n  - path: {spelled}\n") == 1
    assert raw.count(f"\n{question_line}\n") == 1
    assert question_line.isprintable() and in_the_file in question_line

    report = written.stdout.replace(os.linesep.encode(), b"\n").decode(UTF8)
    if not text_name.isprintable():
        assert name not in written.stdout, written.stdout
    assert f"\n  {adopter._shown(text_name)}\n      {question}\n" in report

    checked = run_check(plan)
    assert checked.returncode == 1, checked.stderr + checked.stdout
    found = [line for line in checked.stderr.splitlines()
             if line.startswith("FINDING ")]
    named = adopter._spelled(text_name)
    assert found[0] == (
        f"FINDING {UNSAFE}: {named} has leg: null, and `execute` will not "
        f"extract it into a leg: {adopter.entry_path_problem(text_name)}")
    assert found[1].startswith(f"FINDING plan-unresolved: {named} still has "
                               "`leg: null`. The question was: ")
    assert len(found) == 2, found
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(execute_args(tmp_path, plan))
    assert caught.value.code == "plan-unresolved"
    no_leg_was_created(tmp_path)


@pytest.mark.parametrize("answered", ["root", "drop"])
def test_the_answer_the_question_offers_checks_ok(adopter, tmp_path,
                                                  answered):
    """The question's answers are answers: `-notes.md` answered `root` or
    `drop` checks ok, and `execute` raises nothing over the plan before it
    would make a leg. (`test_the_answers_it_offers_are_adopted_and_verified`
    runs it to the end, where `git filter-repo` is installed.)"""
    source = make_source_repo(tmp_path / "Thing",
                              {**BESIDE, "-notes.md": "notes\n"}, edits=())
    plan = tmp_path / "adoption-plan.yaml"
    assert write_plan(source, plan, project=PROJECT).returncode == 0
    answer(plan, '"-notes.md"', "null", answered)
    assert "leg: null" not in plan.read_text(encoding=UTF8)
    checked = run_check(plan)
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert "plan ok" in checked.stdout
    loaded = adopter.Plan.load(plan)
    assert adopter._refuse_what_check_finds(
        loaded, loaded.open_source(str(source), tmp_path / "read")) is None


def test_a_leg_only_a_refused_path_fed_is_recorded_as_seeded(adopter,
                                                             tmp_path):
    """What the rules imply is read with such a path ASKED: it is in no leg
    whatever the answer, so a leg it alone fed is seeded, and the plan says
    so -- the `seeding:` record and the warning naming `--allow-empty-leg` --
    as `check` says of the plan as written and once it is answered, with no
    note that the record is stale. On main at 71b58a1 `plan` wrote
    `-spec.md: spec`, recorded the spec leg as extracted, and warned of
    nothing."""
    source = make_source_repo(tmp_path / "Thing",
                              {"-spec.md": "# spec\n", "README.md": "# T\n",
                               "src/main.py": "print(1)\n"}, edits=())
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    assert adopter.load_yaml(plan)["seeding"]["spec"] == {
        "seeded_from_template": True, "template": "templates/spec-root",
        "reason": "no entry assigns a path to the spec leg"}
    assert "WARNING the spec leg will be SEEDED" in written.stdout
    assert "--allow-empty-leg spec" in written.stdout
    for answered in (None, "drop"):
        if answered:
            answer(plan, '"-spec.md"', "null", answered)
        checked = run_check(plan)
        assert "WARNING the spec leg will be SEEDED" in checked.stdout
        assert "the `seeding:` record says" not in checked.stdout
    assert checked.returncode == 0, checked.stderr + checked.stdout


# --- a byte that is not UTF-8 ---------------------------------------------

#: A name holding the byte 0xE9 -- Latin-1's e-acute, and not UTF-8 -- below
#: `docs/`, so that `plan` writes the entry `docs/` and never the name itself.
NOT_UTF8 = b"docs/caf\xe9.md"


def with_a_name_that_is_not_utf8(adopter, tmp_path: Path):
    """`(source, plan)`: a source whose `docs/` holds `NOT_UTF8`, and its
    plan, LOADED, with `docs/` split into an entry for each file in it, as a
    person splitting the directory would write it.

    The name is put straight into git's index, as `git add` records it, so
    that no file system has to hold it (APFS refuses one). Before #199 no
    plan FILE could carry it -- `plan` raised writing a surrogate, and the
    reader had no escape that gives one back -- and #199's writer spells it
    `"docs/caf\\udce9.md"`, which its reader returns as the lone surrogate:
    what the loaded entry holds here, with #199 or without it. Skipped
    where git will not record the name or keep it in the tree, which only
    git can say."""
    source = make_source_repo(tmp_path / "Thing",
                              {"docs/architecture.md": "arch\n",
                               "src/app.py": "VALUE = 1\n",
                               "README.md": "# Thing\n"}, edits=())
    blob = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                          cwd=str(source), input=b"latin1\n",
                          capture_output=True, check=True).stdout.strip()
    added = subprocess.run(
        ["git", "update-index", "--add", "-z", "--index-info"],
        cwd=str(source), input=b"100644 " + blob + b"\t" + NOT_UTF8 + b"\0",
        capture_output=True, check=False)
    if added.returncode:
        pytest.skip(f"git update-index refuses {NOT_UTF8!r} here: "
                    f"{added.stderr!r}")
    git("-c", "user.name=Source Human",
        "-c", "user.email=human@source.invalid",
        "commit", "-q", "-m", "Add a name that is not UTF-8", cwd=source)
    held = subprocess.run(["git", "ls-tree", "-r", "-z", "--name-only",
                           "HEAD"], cwd=str(source), capture_output=True,
                          check=True).stdout.split(b"\0")
    if NOT_UTF8 not in held:
        pytest.skip(f"git does not keep {NOT_UTF8!r} in a tree here")
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    loaded = adopter.Plan.load(plan)
    docs = next(e for e in loaded.entries if e.get("path") == "docs/")
    at = loaded.entries.index(docs)
    loaded.entries[at:at + 1] = [
        {**docs, "path": "docs/architecture.md"},
        {**docs, "path": NOT_UTF8.decode(UTF8, "surrogateescape")}]
    return source, loaded


#: The finding `check` must print first for `NOT_UTF8`, spelled as
#: `_spelled` spells a byte that is not UTF-8.
NOT_UTF8_FINDING = (
    f"FINDING {UNSAFE}: `docs/caf\\udce9.md` has leg: spec, and `execute` "
    "will not extract it into a leg: it holds `\\udce9`, which is not UTF-8 "
    "and which `execute` refuses as policy, though git and `git filter-repo` "
    "would take it literally: a name that holds one prints as an escape and "
    "never as itself, the split commit's message would list it with a `?` "
    "for that byte, and adopting one is not yet measured on macOS or Windows")


def test_a_byte_that_is_not_utf8_is_found_and_refused_before_any_leg(
        adopter, tmp_path, monkeypatch, capsys):
    """CATEGORY Cs. `Source.tree` keeps a byte that is not UTF-8 as a lone
    surrogate. Before #199's `write_paths_listing`, on this branch merged
    with #199's first head, `check` said `plan ok` and `execute` raised
    `UnicodeEncodeError` writing the path list, after both leg repositories
    existed. With it the name is extracted byte for byte, and it is still
    refused, as policy, until adopting it end to end is measured on macOS
    and Windows: `check` names it first, and `execute` refuses it in
    `check`'s words before any leg exists."""
    source, loaded = with_a_name_that_is_not_utf8(adopter, tmp_path)
    monkeypatch.setattr(adopter.Plan, "load", staticmethod(lambda _: loaded))
    assert adopter.cmd_check(Namespace(plan=str(loaded.path), source=None,
                                       work_dir=tmp_path / "read")) == 1
    findings = [line for line in capsys.readouterr().err.splitlines()
                if line.startswith("FINDING ")]
    assert findings == [NOT_UTF8_FINDING]
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(execute_args(tmp_path, loaded.path))
    assert caught.value.code == UNSAFE
    assert f"  {NOT_UTF8_FINDING}" in caught.value.detail.splitlines()
    no_leg_was_created(tmp_path)
    assert git("branch", "--format=%(refname:short)",
               cwd=source).stdout.split() == ["main"]


# --- the split commit's message --------------------------------------------

#: Run in a child whose locale is NOT UTF-8 and whose Python is not in UTF-8
#: mode: cp1252 on Windows, ASCII under a POSIX `C` locale. `env_commit` must
#: hand git the message as UTF-8 there too.
#: The message is a Python literal in the code, spelled in ASCII: argv would
#: be decoded in that same foreign locale before `env_commit` saw it.
COMMIT_IN_A_FOREIGN_LOCALE = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from shape_materialize import env_commit
env_commit(Path(sys.argv[2]), {message})
"""


def test_the_split_message_reaches_git_as_utf8_whatever_the_locale(tmp_path):
    """The split commit's message names every entry path it moved. On main at
    e4decfb `env_commit` wrote it to `git commit -F -` in the locale's codec,
    so this child raised `UnicodeEncodeError` -- after both legs had been
    pushed, in a real run."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=repo)
    (repo / "f.txt").write_text("x\n", encoding=UTF8)
    git("add", "f.txt", cwd=repo)
    message = f"Split\n\n  {UMLAUT}\n  \u6587\u66f8.md\n  My Notes.md\n"
    env = {**os.environ, "PYTHONUTF8": "0"}
    if os.name != "nt":
        env.update({"LC_ALL": "C", "LANG": "C", "PYTHONCOERCECLOCALE": "0"})
    child = subprocess.run(
        [sys.executable, "-c",
         COMMIT_IN_A_FOREIGN_LOCALE.format(message=ascii(message)),
         str(REPO / "scripts"), str(repo)],
        capture_output=True, check=False, env=env)
    assert child.returncode == 0, child.stderr.decode(UTF8, "replace")
    raw = subprocess.run(["git", "cat-file", "commit", "HEAD"], cwd=str(repo),
                         capture_output=True, check=True).stdout
    body = raw.split(b"\n\n", 1)[1]
    assert body.decode(UTF8) == message


# --- end to end ------------------------------------------------------------

#: Names only a POSIX disk holds, each with the leg the test gives it. `?`,
#: `*`, `"`, `:`, `>` and `\\` are not file-name characters on NTFS, and
#: Windows drops a trailing space. Beside each wildcard and `:!` name is a
#: file it would match as a pattern, which the plan keeps in the root, and
#: which SORTS BEFORE it: git stops reading a pathspec as a pattern once it
#: has matched a path exactly, and `git rm` walks the index in order, so a
#: decoy sorting after the name (`star-kept.md`) was never at risk.
POSIX_NAMES = {
    "q?.md": "spec", "q1.md": "root",
    "star*.md": "spec", "star(1).md": "root",
    ":!keep.md": "spec", "keep.md": "root",
    'say "hi".md': "spec", " lead.md": "spec", "trail.md ": "spec",
    "back\\slash.md": "spec", "glob:y.md": "spec", "regex:x.md": "spec",
    "literal:z.md": "spec", "a=>b.md": "spec",
}
#: How `plan` answers the names above where the test answers otherwise:
#: `(as the plan file spells it, plan's answer, the test's answer)`.
POSIX_ANSWERS = (("q1.md", "spec", "root"), ('"star(1).md"', "spec", "root"),
                 ("keep.md", "spec", "root"), ('"trail.md "', "null", "spec"))


@needs_filter_repo
def test_a_source_with_such_names_is_adopted_and_verified(tmp_path):
    """THE ACCEPTANCE: plan, check and execute a source whose entries hold
    every kind of name `entry_path_problem` admits -- a space, a letter
    outside ASCII, a leading `#`, `;`, `$`, `(`, `&`, a quote, a wildcard, a
    leading `:`, a leading or trailing space, a backslash, and the spelling
    of each `git filter-repo` directive -- to `adoption verified`, each file
    in its leg and its history followable there.

    `#notes.md` is what the filter's `literal:` lines are for: as a bare line
    it is a comment, the spec leg came out without it, and the split had
    removed it from the root. So are `glob:y.md` and `literal:z.md`, which a
    bare line reads as the pattern `y.md` and the path `z.md`. `[ID].tsx`
    beside `D.tsx` is what `--literal-pathspecs` is for: as a pathspec
    `[ID]` is a character class, so `git rm -- '[ID].tsx'` removed `D.tsx`
    too, though the plan keeps it in the root; and so, where the disk
    allows, did `q?.md` and `star*.md` the files beside them, while
    `git rm -r -- ':!keep.md'` removed every path but `keep.md` and the run
    died at the next `git rm`, after both legs were pushed. `-notes.md` is
    dropped, which reaches only `git rm`, after `--`."""
    tree = {"My Notes.md": "notes\n", "docs/User Guide.md": "guide\n",
            "docs/architecture.md": "arch\n", "#notes.md": "hash\n",
            "-notes.md": "dash\n", "run tests.py": "print(1)\n",
            "src/app.py": "VALUE = 1\n", "README.md": "# Thing\n",
            "semi;colon$(x)'&.md": "shell\n", "[ID].tsx": "page\n",
            "D.tsx": "kept in the root\n"}
    spec_files = {"My Notes.md", "docs/User Guide.md", "docs/architecture.md",
                  "#notes.md", "semi;colon$(x)'&.md"}
    root_files = {"README.md", "D.tsx"}
    if spellable(UMLAUT):
        tree[UMLAUT] = "ueber\n"
        spec_files.add(UMLAUT)
    if os.name != "nt":
        tree.update({name: f"{name}\n" for name in POSIX_NAMES})
        spec_files.update(name for name, leg in POSIX_NAMES.items()
                          if leg == "spec")
        root_files.update(name for name, leg in POSIX_NAMES.items()
                          if leg == "root")
    edits = (("My Notes.md", "notes\n\nA second paragraph.\n",
              "Extend My Notes"),
             ("docs/User Guide.md", "guide\n\nA second section.\n",
              "Extend the User Guide"))
    source = make_source_repo(tmp_path / "Thing", tree, edits=edits)
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    answer(plan, '"-notes.md"', "null", "drop")
    answer(plan, "D.tsx", "code", "root")
    if os.name != "nt":
        for spelled, old, new in POSIX_ANSWERS:
            answer(plan, spelled, old, new)
    assert "leg: null" not in plan.read_text(encoding=UTF8)
    checked = run_check(plan)
    assert checked.returncode == 0, checked.stderr + checked.stdout

    remotes = tmp_path / REMOTES
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / WORK))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "adoption verified" in result.stdout
    assert "drop       1 of" in result.stdout

    def files(repo: Path, rev: str) -> set[str]:
        raw = subprocess.run(["git", "ls-tree", "-r", "-z", "--name-only",
                              rev], cwd=str(repo), capture_output=True,
                             check=True).stdout
        return {name.decode(UTF8) for name in raw.split(b"\0") if name}

    spec_leg = remotes / f"{PROJECT}-spec.git"
    assert files(spec_leg, "main") == spec_files
    assert files(remotes / f"{PROJECT}-code.git", "main") == {
        "run tests.py", "src/app.py", "[ID].tsx"}
    root = files(source, "adopt/three-repo-shape")
    assert root_files <= root and "-notes.md" not in root
    assert not (spec_files | {"[ID].tsx"}) & root

    for path, edited in (("My Notes.md", "Extend My Notes"),
                         ("docs/User Guide.md", "Extend the User Guide")):
        log = subprocess.run(["git", "log", "--follow", "--format=%s", "main",
                              "--", path], cwd=str(spec_leg),
                             capture_output=True, check=True
                             ).stdout.decode(UTF8).splitlines()
        assert log == [edited, "Initial import"], f"{path}: {log}"


@needs_filter_repo
@pytest.mark.parametrize("answered", ["root", "drop"])
@pytest.mark.parametrize("name", [
    "-notes.md", pytest.param("notes\t.md", marks=POSIX_ONLY)])
def test_the_answers_it_offers_are_adopted_and_verified(adopter, tmp_path,
                                                        name, answered):
    """#319's ACCEPTANCE: `plan` asks about the path, the person gives one of
    the two answers its question offers, `check` says `plan ok`, and
    `execute` runs to `adoption verified`, the path where that answer put
    it: in the root tree of the split, or nowhere. A tab is a name only a
    POSIX disk holds, and `execute` checks the source out."""
    source = make_source_repo(tmp_path / "Thing", {**BESIDE, name: "n\n"},
                              edits=())
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    row = {str(row["path"]): row
           for row in adopter.load_yaml(plan)["paths"]}[name]
    assert row["leg"] is None and row["question"].endswith(ONLY_ROOT_OR_DROP)
    answer(plan, adopter.y(name), "null", answered)
    checked = run_check(plan)
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert "plan ok" in checked.stdout

    remotes = tmp_path / REMOTES
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / WORK))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "adoption verified" in result.stdout
    root = subprocess.run(["git", "ls-tree", "-r", "-z", "--name-only",
                           "adopt/three-repo-shape"], cwd=str(source),
                          capture_output=True, check=True).stdout
    held = {path.decode(UTF8) for path in root.split(b"\0") if path}
    assert (name in held) == (answered == "root")
    spec = subprocess.run(["git", "ls-tree", "-r", "--name-only", "main"],
                          cwd=str(remotes / f"{PROJECT}-spec.git"),
                          capture_output=True, text=True, check=True).stdout
    assert spec.split() == ["docs/guide.md"]
