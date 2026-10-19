# SPDX-License-Identifier: Apache-2.0
"""Every name, question and rule id `adopt-project.py` prints or writes reads
one way only, and carries no raw control byte (#900).

Measured on c7a3ff16, each by the rows below that ask it:

- `_split_message`, the split commit's message and the pull request's body,
  listed each moved, dropped and kept path as it is. A source that keeps
  `caf<0xE9>.md` and `cr<CR>` in the root adopted to `adoption verified`,
  and the message read `  caf?.md` and `  cr`: `env_commit` writes the byte
  as `?`, and `git commit` strips the carriage return that ends the line,
  so each line named another path. It lists each as `plan` shows it now,
  and `_shown` spells a name that ends in a space, which git strips too.
- `_spelled` wrote a backtick as a backslash and a backtick, which the
  plan's reader keeps as both, and a double quote as it is, which ends the
  plan's quoting: a spelled name copied into the plan named another entry,
  or left the plan unreadable. They are `\\x60` and `\\"` now.
- `_shown` printed the name `` `x` `` as it is, which is how `_spelled`
  prints the name `x`.
- `plan`'s report printed a path policy's `question:` and rule id as they
  are, and `--path-policy` names any policy: an ESC in either reached the
  terminal.
- `_exported_gitlink`'s `git-failed` named the source folder and what git
  printed raw, where `git_out` names them with `shown_path` and `spelled`.
- `_print_entries` padded each name to 34 characters before stdout escaped
  it, so under `LC_ALL=C PYTHONUTF8=0` `caf\\u00e9.md` printed as the 10
  characters of `caf\\xe9.md` and pushed the rest of its row 3 columns
  right of their headings.

Every row here fails on c7a3ff16's `adopt-project.py`.
"""

from __future__ import annotations

import importlib.util
import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, REPO, blank_unnamed_pin_sources, git,
                      make_source_repo, skip_where_a_name_cannot_be_not_utf_8)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import double_quoted, git_out, parse_yaml  # noqa: E402
from shape_materialize import env_commit  # noqa: E402

UTF8 = "utf-8"
PROJECT = "Northwind"
SPLIT_BRANCH = "adopt/three-repo-shape"
POSIX_ONLY = pytest.mark.skipif(
    os.name == "nt", reason="NTFS cannot hold this character in a file name")
needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_spelled_names",
                                                  ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def adopted(*args: str, env: dict | None = None
            ) -> subprocess.CompletedProcess:
    """`adopt-project.py <args>`, answered in BYTES, so that a control
    character it printed is there to be found, and a carriage return is
    not read as a line feed."""
    env = env or blank_unnamed_pin_sources(
        {**os.environ, "LANES_LANE": ""}, {})
    return subprocess.run([sys.executable, str(ADOPT), *args],
                          capture_output=True, env=env,
                          stdin=subprocess.DEVNULL, check=False)


def planned(source: Path, plan: Path, *extra: str,
            env: dict | None = None) -> subprocess.CompletedProcess:
    """`plan`, as `conftest.write_plan` runs it, answered in bytes."""
    return adopted("plan", "--source", str(source), "--project", PROJECT,
                   "--org", "testorg", "--elected-by", "Test Human",
                   "--elected-on", "2026-09-02", "--out", str(plan), *extra,
                   env=env)


def answered(plan: Path, spelled_as: str, leg: str) -> None:
    """Answer the entry whose `path:` is written `spelled_as`, LF as `plan`
    wrote it (see `conftest.resolve`)."""
    text = plan.read_text(encoding=UTF8)
    needle = f"  - path: {spelled_as}\n    leg: null\n"
    assert needle in text, f"{spelled_as} is not an entry with leg: null"
    with plan.open("w", encoding=UTF8, newline="\n") as handle:
        handle.write(text.replace(
            needle, f"  - path: {spelled_as}\n    leg: {leg}\n", 1))


# --- the two spellings, called directly ------------------------------------

#: The issue's four names: `name: (as _spelled writes it, as _shown prints
#: it)`. On c7a3ff16: `a\`b`, `a"b`, `\`x\`` and `x` spelled, and `` `x` ``
#: shown as it is.
DIRECT = {
    "a`b": ("`a\\x60b`", "a`b"),
    'a"b': ('`a\\"b`', 'a"b'),
    "`x`": ("`\\x60x\\x60`", "`\\x60x\\x60`"),
    "x": ("`x`", "x"),
}


@pytest.mark.parametrize("name", list(DIRECT),
                         ids=["backtick", "double-quote", "in-backticks",
                              "plain"])
def test_the_issues_four_names_print_one_way_each(adopter, name):
    """Each name as `_spelled` writes it and as `_shown` prints it, and
    neither as either function prints another of the four. `x` asks the
    last half: on c7a3ff16 it was spelled `` `x` ``, which is how `_shown`
    printed the name `` `x` ``."""
    spelled_as, shown_as = DIRECT[name]
    assert adopter._spelled(name) == spelled_as
    assert adopter._shown(name) == shown_as
    others = [other for other in DIRECT if other != name]
    printed = ({adopter._spelled(other) for other in others}
               | {adopter._shown(other) for other in others})
    assert spelled_as not in printed
    assert shown_as not in printed


#: Names a person may copy, spelled, between the plan's double quotes: a
#: backtick, a double quote, a name between backticks, the quoted name
#: `tests/test_adopt_entry_paths.py` adopts, and all of them at once beside
#: a backslash and an ESC.
COPIED = {
    "backtick": "a`b",
    "double-quote": 'a"b',
    "in-backticks": "`x`",
    "quoted-word": 'say "hi".md',
    "all-at-once": 'a\\`"\x1b\\"b`',
}


@pytest.mark.parametrize("name", list(COPIED.values()), ids=list(COPIED))
def test_a_spelled_name_copied_into_the_plan_is_that_entry(adopter, name):
    """The plan's reader takes the spelling back as the name, byte for
    byte, and the spelling holds no backtick but the two that wrap it. On
    c7a3ff16 `\\`` read back as a backslash and a backtick, another entry,
    and a double quote ended the quoting."""
    body = adopter._spelled(name)[1:-1]
    assert "`" not in body
    assert parse_yaml(f'path: "{body}"\n') == {"path": name}


def test_a_double_quote_and_a_backslash_are_spelled_as_the_plan_writes_them(
        adopter):
    """`_spelled_character` is the plan's own table, `double_quoted`, for
    every character but the backtick, which wraps a name and is `\\x60`, a
    code point the plan's reader resolves. On c7a3ff16 a double quote was
    itself and a backtick was `\\``."""
    assert adopter._spelled_character('"') == double_quoted('"')[1:-1]
    assert adopter._spelled_character("\\") == double_quoted("\\")[1:-1]
    assert adopter._spelled_character("`") == "\\x60"


def test_shown_prints_no_two_texts_alike(adopter):
    """`a<TAB>b` is spelled `` `a\\tb` ``, and on c7a3ff16 the printable text
    of those seven characters printed as it is, the same seven; `x<LF>` and
    `` `x\\n` `` the same way. A text that begins and ends with a backtick
    is spelled now, a single backtick and two of them included."""
    texts = ["a\tb", "`a\\tb`", "x\n", "`x\\n`", "x", "`x`", "`", "``",
             "a`b`", "`a`b", "caf\udce9", "`caf\\udce9`"]
    shown = [adopter._shown(text) for text in texts]
    assert len(set(shown)) == len(texts), shown


def test_a_text_that_ends_in_a_space_is_shown_spelled(adopter):
    """A space that ends a name reads as nothing: `plan`'s table padded
    `trail.md ` and `trail.md` to the same row, and `git commit` strips it
    from the end of a line of the split commit's message. On c7a3ff16 it
    was printed as it is. A space that begins one is seen, and stays."""
    assert adopter._shown("trail.md ") == "`trail.md `"
    assert adopter._shown("   ") == "`   `"
    assert adopter._shown(" lead.md") == " lead.md"


# --- the split commit's message --------------------------------------------

def split_message(adopter, paths_for: dict, follow_ups=()) -> str:
    """`_split_message` for `paths_for`, each list it does not name empty."""
    return adopter._split_message(
        {"assembly": PROJECT, "spec": f"{PROJECT}-spec",
         "code": f"{PROJECT}-code"},
        {"spec": [], "code": [], "drop": [], "root": [], **paths_for},
        {"spec": "a" * 40, "code": "b" * 40}, "spec", "code",
        list(follow_ups), [])


#: `(the list, a name in it, the line that names it)`: each kind of name
#: `_shown` spells, in each list the message names paths in.
LISTED = {
    "spec-in-backticks": ("spec", "`notes`", "  `\\x60notes\\x60`"),
    "code-in-backticks": ("code", "`tools`", "  `\\x60tools\\x60`"),
    "drop-esc": ("drop", "d\x1b[2Jx", "  `d\\x1b[2Jx`"),
    "root-byte": ("root", "caf\udce9.md", "  `caf\\udce9.md`"),
    "root-carriage-return": ("root", "cr\r", "  `cr\\r`"),
    "root-trailing-space": ("root", "trail.md ", "  `trail.md `"),
}


@pytest.mark.parametrize("role, name, line", list(LISTED.values()),
                         ids=list(LISTED))
def test_the_split_message_lists_each_path_as_plan_shows_it(adopter, role,
                                                             name, line):
    """Every line of the message is printable text UTF-8 carries, and the
    name is the line that `plan`'s report would print for it."""
    paths_for = {"root": ["README.md"]}
    paths_for[role] = paths_for.get(role, []) + [name]
    message = split_message(adopter, paths_for)
    assert f"\n{line}\n" in message, message
    assert f"\n  {name}\n" not in message
    assert [part for part in message.split("\n")
            if not part.isprintable()] == []
    assert message.encode(UTF8).decode(UTF8) == message


def test_git_commit_keeps_every_line_of_the_split_message(adopter, tmp_path):
    """The message `env_commit` hands `git commit -F -`, read back from the
    commit object byte for byte: git changes no line of it. On c7a3ff16 it
    stripped the carriage return and the space that ended two names, and
    the byte 0xE9 reached it as `?`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=repo)
    (repo / "README.md").write_text("# Thing\n", encoding=UTF8)
    git("add", "README.md", cwd=repo)
    message = split_message(adopter, {"root": [
        "README.md", "caf\udce9.md", "cr\r", "trail.md ", "`x`"]})
    env_commit(repo, message)
    stored = subprocess.run(["git", "cat-file", "commit", "HEAD"],
                            cwd=str(repo), capture_output=True,
                            check=True).stdout.split(b"\n\n", 1)[1]
    assert stored.decode(UTF8).split("\n") == message.split("\n")


def test_a_follow_up_is_shown_in_the_message_as_execute_prints_it(adopter):
    """A follow-up is the plan's text, which a person may edit: `execute`
    prints it `_shown` before it begins, and the message now writes it the
    same way. On c7a3ff16 the ESC went into the commit raw."""
    message = split_message(adopter, {"root": ["README.md"]},
                            follow_ups=["merge a\x1b[2J into b"])
    assert "\n  - `merge a\\x1b[2J into b`\n" in message, message
    assert "\x1b" not in message


@needs_filter_repo
@POSIX_ONLY
def test_the_issues_source_adopts_and_the_message_names_each_kept_path(
        tmp_path):
    """THE ISSUE'S CASE, END TO END: a source that keeps `caf<0xE9>.md` and
    `cr<CR>` in the root, through `check` and `execute` with local remotes.
    On c7a3ff16 both ran to `adoption verified`, and the split commit's
    message read `  caf?.md` and `  cr`."""
    skip_where_a_name_cannot_be_not_utf_8(tmp_path)
    source = make_source_repo(tmp_path / "Thing",
                              {"README.md": "# Thing\n",
                               "docs/guide.md": "guide\n",
                               "src/app.py": "VALUE = 1\n"}, edits=())
    for name in (b"caf\xe9.md", b"cr\r"):
        with open(os.path.join(os.fsencode(source), name), "wb") as handle:
            handle.write(b"kept\n")
    git("add", "-A", "--", ".", cwd=source)
    git("commit", "-q", "-m", "Keep two names in the root", cwd=source)
    plan = tmp_path / "adoption-plan.yaml"
    written = planned(source, plan)
    assert written.returncode == 0, written.stderr + written.stdout
    answered(plan, '"caf\\udce9.md"', "root")
    answered(plan, '"cr\\r"', "root")
    checked = adopted("check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    ran = adopted("execute", "--plan", str(plan), "--yes",
                  "--local-remote-dir", str(tmp_path / "remotes"),
                  "--work-dir", str(tmp_path / "work"))
    assert ran.returncode == 0, ran.stderr + ran.stdout
    assert b"\nadoption verified" in ran.stdout, ran.stdout
    message = subprocess.run(
        ["git", "log", "-1", "--format=%B", SPLIT_BRANCH], cwd=str(source),
        capture_output=True, check=True).stdout
    kept = message.split(b"\nSTAYS IN THE ASSEMBLY ROOT:\n", 1)[1]
    assert kept.split(b"\n\n", 1)[0].split(b"\n") == [
        b"  README.md", b"  `caf\\udce9.md`", b"  `cr\\r`"], message


# --- plan's report: a policy's question and rule id ------------------------

#: A path policy whose rule ids and questions hold what a terminal acts on:
#: an ESC in a rule id, in a question asked and in one asked with a
#: default, and a rule id that begins and ends with a backtick.
POLICY = (
    b"schema_version: 1\nkind: path-classification-policy\nrules:\n"
    b'  - id: "docs\\x1b[31m-red"\n    paths:\n      - "docs/**"\n'
    b"    leg: spec\n    reason: A test rule.\n"
    b'  - id: "`asked`"\n    paths:\n      - "notes/**"\n'
    b"    leg: ambiguous\n    reason: A test rule.\n"
    b'    question: "Keep notes\\x1b[2J? It is asked."\n'
    b"  - id: test-defaulted\n    paths:\n      - \"scratch/**\"\n"
    b"    leg: ambiguous\n    default: drop\n    reason: A test rule.\n"
    b'    question: "Drop scratch\\x1b[2J?"\n'
    b"  - id: test-everything-else\n    paths:\n      - \"**\"\n"
    b"    leg: code\n    reason: Everything else.\n")


def test_plan_prints_a_policys_question_and_rule_id_as_check_does(tmp_path):
    """`plan --path-policy`: the table's rule column and both lists of
    questions, `_shown`. On c7a3ff16 each ESC reached stdout raw."""
    policy = tmp_path / "policy.yaml"
    policy.write_bytes(POLICY)
    source = make_source_repo(tmp_path / "Thing",
                              {"README.md": "# Thing\n",
                               "docs/guide.md": "guide\n",
                               "notes/a.md": "a\n", "scratch/b.md": "b\n"},
                              edits=())
    written = planned(source, tmp_path / "adoption-plan.yaml",
                      "--path-policy", str(policy))
    assert written.returncode == 0, written.stderr + written.stdout
    report = written.stdout.decode(UTF8)
    assert "\x1b" not in report, report
    rows = {row.split()[0]: row.split()[-1] for row in report.splitlines()
            if row.startswith(("docs/ ", "notes/ ", "scratch/ "))}
    assert rows == {"docs/": "`docs\\x1b[31m-red`",
                    "notes/": "`\\x60asked\\x60`",
                    "scratch/": "test-defaulted"}, report
    assert ("\n  scratch/ (leg: drop)\n      `Drop scratch\\x1b[2J?`\n"
            in report), report
    assert ("\n  notes/\n      `Keep notes\\x1b[2J? It is asked.`\n"
            in report), report


#: A rule id with a backtick in it and an ESC, and its spelling.
RULE, RULE_SPELLED = "r`1\x1b", "`r\\x601\\x1b`"


def test_a_question_names_the_rule_it_replaces_as_a_path_is_named(adopter):
    """`_refused_as_named` and `_asked_about` name the rule whose answer
    they replace inside the question, which the plan carries and `check`
    repeats. On c7a3ff16 it sat raw between two backticks."""
    rule = adopter.Verdict("spec", RULE, "A test rule.", "high")
    refused = adopter._refused_as_named(
        adopter.Entry("a.md", rule, 1, 5), "it is a test", False)
    assert f"leg (rule {RULE_SPELLED}), but `execute`" in refused.question
    assert refused.question.isprintable()
    gitmodules = adopter.Verdict(None, "ambiguous-gitmodules", "Asked.",
                                 "high", "Which leg?")
    asked = adopter._asked_about(adopter.Entry("vendor/b", rule, 1, 5),
                                 ["vendor/b"], gitmodules, ["vendor/b"])
    assert asked.question.endswith(
        f"not classified by its rule {RULE_SPELLED}."), asked.question


# --- `_exported_gitlink`'s refusal -----------------------------------------

@POSIX_ONLY
def test_exported_gitlinks_refusal_is_one_line_spelled_as_git_out_spells(
        adopter, tmp_path):
    """A source folder named with a line break, an ESC and U+0085, whose
    `.git` git can no longer read once `plan` has opened it: git echoes the
    folder, passing the line break and U+0085 through. The refusal is still
    `git-failed`, on one printable line, and says what `git_out` says of
    the same failure after the command. On c7a3ff16 both parts were raw."""
    folder = tmp_path / "Thing\nWARNING forged-line\x1b[2J\x85"
    make_source_repo(folder, {"README.md": "# Thing\n"}, edits=())
    source = adopter.Source.open(str(folder), tmp_path / "read")
    (folder / ".git").rename(folder / "git-aside")
    (folder / ".git").write_text("not a gitfile\n", encoding=UTF8)
    with pytest.raises(adopter.Refusal) as caught:
        adopter._exported_gitlink(source)
    assert caught.value.code == "git-failed"
    detail = caught.value.detail
    assert detail.isprintable(), detail
    with pytest.raises(adopter.Refusal) as by_git_out:
        git_out(["log", "-1"], cwd=source.path)
    assert by_git_out.value.code == "git-failed"
    assert (detail.partition("` in ")[2]
            == by_git_out.value.detail.partition("` in ")[2]), detail


# --- plan's table: a name padded as stdout prints it -----------------------

def table_of(text: str) -> tuple[str, list[str]]:
    """`(the heading, its rows)` of `plan`'s table in `text`."""
    lines = text.split("\n")
    start = next(at for at, line in enumerate(lines)
                 if line.startswith("path "))
    end = lines.index("", start)
    return lines[start], lines[start + 1:end]


def assert_each_column_under_its_heading(heading: str, rows: list[str]
                                         ) -> None:
    """Each row's leg begins where `leg` does in the heading, after the
    one space that ends the padded name."""
    column = heading.index("leg")
    assert column == 35, heading
    for row in rows:
        assert row[column - 1] == " ", (heading, row)
        assert row[column] != " ", (heading, row)


def test_the_table_pads_a_name_as_an_ascii_stdout_prints_it(adopter,
                                                            monkeypatch):
    """`_print_entries` on a stdout that writes `caf\\u00e9.md` as the 10
    characters `caf\\xe9.md`, as `escape_what_stdout_cannot_encode` has one
    do: the row is padded by those 10."""
    stream = io.TextIOWrapper(io.BytesIO(), encoding="ascii",
                              errors="backslashreplace", newline="\n")
    monkeypatch.setattr(sys, "stdout", stream)
    adopter._print_entries([
        adopter.Entry(path, adopter.Verdict(leg, rule, "Why.", "high"), 1, 1)
        for path, leg, rule in (("README.md", "root", "root-front-door"),
                                ("café.md", "spec", "extension-majority"))
    ])
    stream.flush()
    heading, rows = table_of(stream.buffer.getvalue().decode("ascii") + "\n")
    assert [row.split()[0] for row in rows] == ["README.md", "caf\\xe9.md"]
    assert_each_column_under_its_heading(heading, rows)


#: What a child reports its own redirected stdout to be.
STDOUT_PROBE = ("import codecs, sys; "
                "print(codecs.lookup(sys.stdout.encoding).name, "
                "sys.stdout.errors)")


@POSIX_ONLY
def test_plan_under_the_c_locale_keeps_each_column_under_its_heading(
        tmp_path):
    """THE ISSUE'S TABLE: `plan` under `LC_ALL=C PYTHONUTF8=0`, which gives
    a redirected stdout ASCII, over a source holding `caf\\u00e9.md`. On
    c7a3ff16 its row's leg stood 3 columns right of `leg`. A Python whose
    stdout there holds the name skips: no name is escaped."""
    env = blank_unnamed_pin_sources(
        {key: value for key, value in os.environ.items()
         if key.upper() != "PYTHONIOENCODING"}, {})
    env.update({"LANES_LANE": "", "LC_ALL": "C", "PYTHONUTF8": "0"})
    probe = subprocess.run([sys.executable, "-c", STDOUT_PROBE],
                           capture_output=True, env=env,
                           stdin=subprocess.DEVNULL, check=True)
    codec = probe.stdout.decode("ascii").split()[0]
    try:
        "é".encode(codec)
    except UnicodeEncodeError:
        pass
    else:
        pytest.skip(f"this Python gives a redirected stdout {codec} under "
                    "the C locale, which holds the name")
    source = make_source_repo(tmp_path / "Thing",
                              {"README.md": "# Thing\n",
                               "café.md": "x\n",
                               "src/app.py": "VALUE = 1\n"}, edits=())
    written = planned(source, tmp_path / "adoption-plan.yaml", env=env)
    assert written.returncode == 0, written.stderr + written.stdout
    heading, rows = table_of(written.stdout.decode("ascii", "replace"))
    assert "caf\\xe9.md" in [row.split()[0] for row in rows], rows
    assert_each_column_under_its_heading(heading, rows)
