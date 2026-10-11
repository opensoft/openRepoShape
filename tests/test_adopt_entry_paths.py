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

NO NETWORK AND NO GITHUB. `git filter-repo` is needed only by the end-to-end
test at the bottom, which skips without it as `test_adopt_e2e.py` does; the
Windows job installs none, so there it is the tests above it that run. They
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

from conftest import ADOPT, REPO, git, make_source_repo, run_script, write_plan

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


def answer(plan: Path, spelled: str, old: str, new: str) -> None:
    """Re-answer the entry whose `path:` is written `spelled`, from `old` to
    `new`, LF as `plan` wrote it (see `conftest.resolve`)."""
    text = plan.read_text(encoding=UTF8)
    needle = f"  - path: {spelled}\n    leg: {old}\n"
    assert needle in text, f"{spelled} is not an entry with leg: {old}"
    with plan.open("w", encoding=UTF8, newline="\n") as handle:
        handle.write(text.replace(
            needle, f"  - path: {spelled}\n    leg: {new}\n"
                    "    resolution: \"answered by the test\"\n", 1))


def planned(tmp_path: Path, tree: dict, edits: tuple = ()) -> tuple[Path, Path]:
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

REFUSED = [
    ("", "empty or nothing but whitespace"),
    ("   ", "empty or nothing but whitespace"),
    ("-dash.md", "begins with `-`"),
    ("--output=never-written", "begins with `-`"),
    ("tab\there.md", "control character `\\t`"),
    ("docs\nregex:.*", "control character `\\n`"),
    ("Icon\r", "control character `\\r`"),
    ("nul\x00", "control character `\\x00`"),
    ("esc\x1b[31m.md", "control character `\\x1b`"),
    ("del\x7f.md", "control character `\\x7f`"),
    ("nel\x85.md", "control character `\\x85`"),
    ("line\u2028sep.md", "control character `\\u2028`"),
    ("a==>b.md", "`==>`"),
    ("docs/a==>b/", "`==>`"),
]


@pytest.mark.parametrize("path", ADMITTED)
def test_what_a_source_tree_holds_is_admitted(adopter, path):
    """A space, a letter outside ASCII, a `#`, a wildcard, a leading `:` and
    a filter-repo directive's spelling: each reaches `git` literally, as a
    `literal:` line of the filter's path list and a pathspec after `--` to
    `git --literal-pathspecs rm`."""
    assert adopter.entry_path_problem(path) is None


@pytest.mark.parametrize("path,said", REFUSED)
def test_only_what_git_cannot_take_is_refused(adopter, path, said):
    problem = adopter.entry_path_problem(path)
    assert problem is not None and said in problem


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
#: each as the plan file spells it and as the finding must name it.
HAND_EDITS = {
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
    assert any(line.startswith("FINDING plan-uncovered: specs/")
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


@pytest.mark.parametrize("answered", ["root", "drop"])
def test_an_entry_answered_root_or_drop_is_not_judged(adopter, tmp_path,
                                                      answered):
    """A path that is never extracted reaches no line of the filter's list:
    `root` keeps it where it is and `drop` hands it to `git rm` after `--`.
    So the remediation's `drop` is true; answered `spec` it is refused."""
    source, plan = planned(tmp_path, {"-notes.md": "notes\n",
                                      "src/app.py": "VALUE = 1\n",
                                      "docs/spec.md": "# spec\n"})
    findings = [line for line in run_check(plan).stderr.splitlines()
                if line.startswith(f"FINDING {UNSAFE}:")]
    assert findings == [f"FINDING {UNSAFE}: `-notes.md` has leg: spec and "
                        "cannot be extracted into a leg: it begins with `-`, "
                        "and git reads an argument that begins with `-` as an "
                        "option of its own"]
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
    the plan as it stands, and the plan parses. `check` names it and
    `execute` refuses it before any leg exists."""
    source, plan = planned(tmp_path, {"notes\t.md": "notes\n",
                                      "src/app.py": "VALUE = 1\n"})
    result = run_check(plan)
    assert result.returncode == 1, result.stderr + result.stdout
    assert f"FINDING {UNSAFE}: `notes\\t.md` has leg: spec" in result.stderr
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(execute_args(tmp_path, plan))
    assert caught.value.code == UNSAFE
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

@needs_filter_repo
def test_a_source_with_such_names_is_adopted_and_verified(tmp_path):
    """THE ACCEPTANCE: plan, check and execute a source whose entries hold a
    space, a letter outside ASCII, a leading `#` and (where the disk allows)
    a wildcard beside a file it would also match, to `adoption verified`,
    each file in its leg and its history followable there.

    `#notes.md` is what the filter's `literal:` lines are for: as a bare line
    it is a comment, the spec leg came out without it, and the split had
    removed it from the root. `q?.md` beside `q1.md` is what
    `--literal-pathspecs` is for: `git rm -- 'q?.md'` removed `q1.md` too,
    though the plan keeps it in the root. `-notes.md` is dropped, which
    reaches only `git rm`, after `--`."""
    tree = {"My Notes.md": "notes\n", "docs/User Guide.md": "guide\n",
            "docs/architecture.md": "arch\n", "#notes.md": "hash\n",
            "-notes.md": "dash\n", "run tests.py": "print(1)\n",
            "src/app.py": "VALUE = 1\n", "README.md": "# Thing\n"}
    spec_files = {"My Notes.md", "docs/User Guide.md", "docs/architecture.md",
                  "#notes.md"}
    if spellable(UMLAUT):
        tree[UMLAUT] = "ueber\n"
        spec_files.add(UMLAUT)
    if os.name != "nt":
        tree.update({"q?.md": "wild\n", "q1.md": "kept in the root\n"})
        spec_files.add("q?.md")
    edits = (("My Notes.md", "notes\n\nA second paragraph.\n",
              "Extend My Notes"),
             ("docs/User Guide.md", "guide\n\nA second section.\n",
              "Extend the User Guide"))
    source, plan = planned(tmp_path, tree, edits)
    answer(plan, '"-notes.md"', "spec", "drop")
    if os.name != "nt":
        answer(plan, "q1.md", "spec", "root")
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
        "run tests.py", "src/app.py"}
    root = files(source, "adopt/three-repo-shape")
    assert "README.md" in root and "-notes.md" not in root
    assert not spec_files & root
    if os.name != "nt":
        assert "q1.md" in root

    for path, edited in (("My Notes.md", "Extend My Notes"),
                         ("docs/User Guide.md", "Extend the User Guide")):
        log = subprocess.run(["git", "log", "--follow", "--format=%s", "main",
                              "--", path], cwd=str(spec_leg),
                             capture_output=True, check=True
                             ).stdout.decode(UTF8).splitlines()
        assert log == [edited, "Initial import"], f"{path}: {log}"
