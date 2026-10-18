# SPDX-License-Identifier: Apache-2.0
"""A command step (a) prints for a person to paste names its path and its ref
in a word a shell reads back as the same name (#932).

`move_back_to_pin` prints `git -C <leg> merge --ff-only <upstream>`, and
`_say_in_progress` a leg's `git -C <leg> <verb> --continue` and `--abort`.
Both went through `spelled(shlex.quote(...))`. `spelled` writes a byte that
is not UTF-8 as #391's `\\udcXX` text, and a control character, a line
separator and a bidirectional control as the escape Python spells it, and a
shell reads `'origin/a\\udcffb'` as the characters it is. RV824 measured it
on #824: for an upstream `origin/a<0xff>b` the line named no ref, and git
answered `not something we can merge`.

THE RULE NOW (`_paste_word`). A name that `spelled` has nothing to escape in,
and this stdout can write, is the word it was, byte for byte: `shlex.quote`.
Any other is `"$(printf -- '<octal escapes>')"`, which `sh` turns back into
the bytes of the name. A name that has no such word (one that ends in a line
feed, which `$(...)` strips, and one `os.fsencode` cannot write) keeps what
`spelled` made of it.

EACH TEST BELOW RUNS WHAT WAS PRINTED, AS PRINTED: the command in the line,
through `/bin/sh -c` from the root, and asks where the branch is, or the
operation, afterwards. Asked of the words themselves it would hold only what
the helper says of itself, which the first fix would have changed with it.

The state is the one `tests/test_bootstrap_non_utf8_branch.py` builds (a
`main` past the pin, with no commit of its own, tracking a remote-tracking
ref, the leg detached at the pin), and a leg mounted at a path of its own
where the path is what is asked. A name holding the byte 0xff skips where the
disk takes no such file name, as there; Windows has no `/bin/sh`.
"""

from __future__ import annotations

import ast
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import IDENTITY_EMAIL, IDENTITY_NAME, REPO, git, run_script
from test_bootstrap_after_bump import (  # noqa: F401
    MAIN, bootstrapped, head_ref, rev, root, skip_validators,
)
from test_bootstrap_branch_bytes import bootstrap_module  # noqa: F401
from test_bootstrap_leg_moves import merging
from test_bootstrap_non_utf8_branch import (
    NEEDS_A_UTF8_PROCESS, LegacyWindowsOs, needs_the_byte, past_the_pin,
    step_a,
)

pytestmark = pytest.mark.skipif(
    os.name == "nt", reason="the printed words are `sh`'s, run by /bin/sh")

TEMPLATE = REPO / "templates" / "assembly-root" / "scripts" / "bootstrap.py"
#: What `bootstrap.py` imports from `repo_shape.py`, as #610 left it. A root
#: re-copies its pinned files one row at a time, so a name added here is a
#: name an older `repo_shape.py` does not have (#370, #932).
FROM_REPO_SHAPE = {"Refusal", "escape_unencodable_stdout", "find_repo_root",
                   "git_out", "load_yaml", "recorded_gitlink", "spelled"}

#: A name step (a) writes as `printf`, as the line spells it for a person
#: (`spelled`: `held`), and the word the command holds, in each class of
#: character `spelled` escapes: a byte that is not UTF-8 (a lone surrogate to
#: Python), a C1 control, a line separator and a bidirectional control.
UPSTREAMS = [
    pytest.param("a\udcffb", r"origin/a\udcffb",
                 r'''"$(printf -- 'origin/a\377b')"''', id="byte-0xff"),
    pytest.param("a\u0085b", r"origin/a\x85b",
                 r'''"$(printf -- 'origin/a\302\205b')"''', id="C1-control",
                 marks=NEEDS_A_UTF8_PROCESS),
    pytest.param("a\u2028b", r"origin/a\u2028b",
                 r'''"$(printf -- 'origin/a\342\200\250b')"''', id="U+2028",
                 marks=NEEDS_A_UTF8_PROCESS),
    pytest.param("a\u202eb", r"origin/a\u202eb",
                 r'''"$(printf -- 'origin/a\342\200\256b')"''',
                 id="bidi-control", marks=NEEDS_A_UTF8_PROCESS),
]
#: The same for a leg's PATH: the label step (a) names the leg by, and the
#: word. A path that begins with `-` is why the word has its `--`, and one
#: with a `%` is why that is an escape, as the backslash is.
PATHS = [
    pytest.param("sp\udcffec", r"sp\udcffec",
                 r'''"$(printf -- 'sp\377ec')"''', id="byte-0xff"),
    pytest.param("-sp\udcffec", r"-sp\udcffec",
                 r'''"$(printf -- '-sp\377ec')"''', id="leading-dash"),
    pytest.param("sp%s\udcffec", r"sp%s\udcffec",
                 r'''"$(printf -- 'sp\045s\377ec')"''', id="percent"),
]
SHELLS = [pytest.param(shell, id=shell.rsplit("/", 1)[1]) for shell in
          ("/bin/sh", "/bin/dash", "/bin/bash", "/bin/zsh")]


def pasted(root: Path, command: str, shell: str = "/bin/sh") -> None:
    """`command`, as step (a) printed it, run from the root by `shell -c` as
    a person pastes it, with an editor that keeps the message git offers and
    an identity for the merge a `--continue` makes."""
    if not os.path.exists(shell):
        pytest.skip(f"this system has no {shell}")
    env = {**os.environ, "GIT_EDITOR": "true",
           "GIT_AUTHOR_NAME": IDENTITY_NAME,
           "GIT_AUTHOR_EMAIL": IDENTITY_EMAIL,
           "GIT_COMMITTER_NAME": IDENTITY_NAME,
           "GIT_COMMITTER_EMAIL": IDENTITY_EMAIL}
    proc = subprocess.run([shell, "-c", command], cwd=str(root), env=env,
                          capture_output=True, check=False)
    assert proc.returncode == 0, (
        command + "\n" + (proc.stderr + proc.stdout).decode("utf-8",
                                                           "replace"))


def mounted_at(root: Path, path: str) -> Path:
    """The spec leg moved to `path`, in the tree and in the manifest, as a
    hand-written manifest holds it (`tests/test_bootstrap_after_bump.py`'s
    leg at `my spec`). `json.dumps` writes the lone surrogate of a byte that
    is not UTF-8 as the `\\udcff` YAML reads back as one."""
    git("mv", "--", "spec", path, cwd=root)
    manifest = root / "project.yaml"
    text = manifest.read_bytes()
    assert text.count(b'path: "spec"\n') == 1, text
    manifest.write_bytes(text.replace(
        b'path: "spec"\n', f"path: {json.dumps(path)}\n".encode("ascii")))
    return root / path


def moved_back_lines(root: Path, tmp_path: Path, upstream: str = "main",
                     path: str = "spec") -> tuple[str, str, list[str]]:
    """Step (a) with the spec leg at `path` and its `main` one commit past
    the pin, no commit of its own, tracking `origin/<upstream>`: the pin,
    that commit, and the lines step (a) printed."""
    if "\udcff" in upstream + path:
        needs_the_byte(tmp_path)
    leg = root / "spec" if path == "spec" else mounted_at(root, path)
    pin, ahead = past_the_pin(leg, upstream, "main")
    result = skip_validators(root)
    assert result.returncode == 0, result.stderr + result.stdout
    return pin, ahead, step_a(result.stdout)


def moved_back_line(label: str, tip: str, pin: str, held: str,
                    command: str) -> str:
    """The line step (a) prints when it moves `main` back to the pin: the
    leg as `label` spells it, the upstream as `held` and the command as
    printed."""
    return (f"  [spec] {label}: branch main moved back {tip[:12]} -> "
            f"{pin[:12]}, the pin; nothing is lost, {held} still holds those "
            f"commits, and `{command}` brings the branch forward")


def code_leg_line(root: Path) -> str:
    """What step (a) says of the code leg, which is on `main` at its pin."""
    return (f"  [code] code: on main at {rev(root / 'code')[:12]} "
            "(branch tip == pin)")


def command_of(line: str) -> str:
    """The command in the first span of backticks of a line."""
    return line.split("`")[1]


# --- the move-back line names an upstream a shell reads back ----------------

@pytest.mark.parametrize("upstream, held, word", UPSTREAMS)
def test_the_move_back_command_is_pasteable_whatever_the_upstream_is_named(
        root, tmp_path, upstream, held, word):
    """THE ISSUE: for `origin/a<0xff>b` the line read `git -C spec merge
    --ff-only 'origin/a\\udcffb'`, and git refused it. Run as printed, the
    command brings `main` forward to the upstream's commit, for the byte and
    for each character `spelled` writes as an escape of its own. The stdout
    lines are asserted whole: only the command's upstream word differs from
    what they were, and it is ASCII."""
    pin, ahead, lines = moved_back_lines(root, tmp_path, upstream)

    command = f"git -C spec merge --ff-only {word}"
    assert lines == [moved_back_line("spec", ahead, pin, held, command),
                     code_leg_line(root)], lines
    assert command.isascii(), command
    assert rev(root / "spec", MAIN) == pin
    pasted(root, command_of(lines[0]))
    assert rev(root / "spec", MAIN) == ahead
    assert head_ref(root / "spec") == MAIN


@pytest.mark.parametrize("shell", SHELLS)
def test_the_printf_word_is_read_by_every_shell_a_person_pastes_it_into(
        root, tmp_path, shell):
    """The form is chosen for dash, which has no `$'...'` before 0.5.13 and
    reads the spelled text as it is; bash and zsh read the same word."""
    pin, ahead, lines = moved_back_lines(root, tmp_path, "a\udcffb")

    pasted(root, command_of(lines[0]), shell)
    assert rev(root / "spec", MAIN) == ahead


# --- ... and a path ---------------------------------------------------------

@pytest.mark.parametrize("path, label, word", PATHS)
def test_the_move_back_command_is_pasteable_whatever_the_legs_path_is_named(
        root, tmp_path, path, label, word):
    """The leg's own path is a word of the same command, and it is the
    manifest's text. Mounted at a path holding the byte 0xff (as `.gitmodules`
    and `project.yaml` can hold it), the command names that directory when
    run as printed; so with a leading `-`, which `printf` would read as an
    option without its `--`, and a `%`, which it would read as a conversion
    without its escape."""
    pin, ahead, lines = moved_back_lines(root, tmp_path, path=path)

    command = f"git -C {word} merge --ff-only origin/main"
    assert lines[0] == moved_back_line(label, ahead, pin, "origin/main",
                                       command), lines
    leg = root / path
    assert rev(leg, MAIN) == pin
    pasted(root, command_of(lines[0]))
    assert rev(leg, MAIN) == ahead


# --- `_say_in_progress`'s two commands --------------------------------------

@pytest.mark.parametrize("which, done", [
    pytest.param(1, "committed", id="--continue"),
    pytest.param(3, "aborted", id="--abort")])
def test_the_commands_that_end_an_operation_are_pasteable_whatever_the_path(
        root, tmp_path, which, done):
    """A merge in progress in a leg mounted at `sp<0xff>ec`: step (a) names
    nothing to move, and the two commands that end the merge are the leg's
    path as a word. Each is run as printed from the root and the merge is
    over: on main, `git -C sp\\udcffec merge --abort` named no directory."""
    needs_the_byte(tmp_path)
    leg = mounted_at(root, "sp\udcffec")
    merging(leg, rev(leg))
    result = skip_validators(root)
    assert result.returncode == 0, result.stderr + result.stdout

    word = r'''"$(printf -- 'sp\377ec')"'''
    lines = step_a(result.stdout)
    assert lines[:2] == [
        r"  [spec] sp\udcffec: a merge is in progress in the leg (MERGE_HEAD "
        "is in its git dir), so nothing moved",
        f"          finish it (`git -C {word} merge --continue`) or abort it "
        f"(`git -C {word} merge --abort`), then run bootstrap again."], lines
    assert git("rev-parse", "-q", "--verify", "MERGE_HEAD", cwd=leg,
               check=False).returncode == 0, "the merge is in progress"
    pasted(root, lines[1].split("`")[which])
    assert git("rev-parse", "-q", "--verify", "MERGE_HEAD", cwd=leg,
               check=False).returncode == 1, f"the merge is {done}"


# --- every ordinary line is what it was -------------------------------------

@pytest.mark.parametrize("name, word", [
    ("spec", "spec"),
    ("origin/main", "origin/main"),
    ("my spec", "'my spec'"),
    ("it's", "'it'\"'\"'s'"),
    ("", "''"),
    ("=x", "=x"),
    pytest.param("origin/café", "'origin/café'", id="printable-UTF-8"),
    pytest.param("日本", "'日本'", id="CJK"),
    pytest.param("a\u00a0b", "'a\u00a0b'", id="no-break-space"),
], ids=lambda value: None if value else "empty")
def test_a_name_with_nothing_to_escape_is_the_word_it_was(
        bootstrap_module, name, word):
    """Byte for byte `spelled(shlex.quote(name))`, which every such word
    was: no `printf`, no new quoting. A U+00A0 is no escape to `spelled`,
    and prints as it is."""
    assert bootstrap_module._paste_word(name) == word
    assert word == bootstrap_module.spelled(shlex.quote(name))


@pytest.mark.parametrize("upstream, word", [
    pytest.param("main", "origin/main", id="ASCII"),
    pytest.param("it's", "'origin/it'\"'\"'s'", id="a-quote"),
    pytest.param("café", "'origin/café'", id="printable-UTF-8",
                 marks=NEEDS_A_UTF8_PROCESS),
])
def test_the_move_back_line_of_a_printable_upstream_is_the_one_it_was(
        root, tmp_path, upstream, word):
    """`origin/main`, an upstream with an apostrophe and one with `é` in
    it print exactly as `spelled(shlex.quote(...))` printed them, and run
    as printed."""
    pin, ahead, lines = moved_back_lines(root, tmp_path, upstream)

    held = "origin/" + upstream
    command = f"git -C spec merge --ff-only {word}"
    assert lines == [moved_back_line("spec", ahead, pin, held, command),
                     code_leg_line(root)], lines
    pasted(root, command_of(lines[0]))
    assert rev(root / "spec", MAIN) == ahead


# --- a stdout that cannot write the name ------------------------------------

@NEEDS_A_UTF8_PROCESS
def test_a_stdout_that_cannot_write_the_name_gets_the_printf_word(
        root, tmp_path):
    """`PYTHONIOENCODING=ascii` writes `é` as `\\xe9`, which no shell
    reads back as the name, so the command holds its bytes as `printf`
    does; the prose names the upstream as the stdout writes it."""
    leg = root / "spec"
    pin, ahead = past_the_pin(leg, "café", "main")

    result = run_script(root / "scripts" / "bootstrap.py", "--skip-validators",
                        cwd=root, env={"PYTHONIOENCODING": "ascii"})
    assert result.returncode == 0, result.stderr + result.stdout
    word = r'''"$(printf -- 'origin/caf\303\251')"'''
    command = f"git -C spec merge --ff-only {word}"
    line = moved_back_line("spec", ahead, pin, r"origin/caf\xe9", command)
    assert line in result.stdout.split("\n"), result.stdout
    pasted(root, command_of(line))
    assert rev(leg, MAIN) == ahead


# --- the helper's limits and its edges --------------------------------------

@pytest.mark.parametrize("name, word", [
    ("a\udcffb", r'''"$(printf -- 'a\377b')"'''),
    ("-x\udcff", r'''"$(printf -- '-x\377')"'''),
    ("50%\udcff", r'''"$(printf -- '50\045\377')"'''),
    ("a\\b\udcff", r'''"$(printf -- 'a\134b\377')"'''),
    ("it's\udcff", r'''"$(printf -- 'it\047s\377')"'''),
    ("a b\udcff", r'''"$(printf -- 'a\040b\377')"'''),
    ("a\tb", r'''"$(printf -- 'a\011b')"'''),
    ("a\x1bb", r'''"$(printf -- 'a\033b')"'''),
    ("a\nb", r'''"$(printf -- 'a\012b')"'''),
    ("dé\udcff", r'''"$(printf -- 'd\303\251\377')"'''),
    ("=x\udcff", r'''"$(printf -- '=x\377')"'''),
    # An escape is ALWAYS three digits: a digit that follows is the name's.
    ("a\x1b7\udcff", r'''"$(printf -- 'a\0337\377')"'''),
    ("\t1\udcff", r'''"$(printf -- '\0111\377')"'''),
])
def test_the_printf_word_prints_the_bytes_of_the_name(
        bootstrap_module, name, word):
    """The word for each byte class, exactly, and what `/bin/sh` makes of it
    is the bytes `os.fsencode` gives the name: a byte outside the safe set is
    a three-digit octal escape, `%` and the backslash and the apostrophe
    included, and a newline in the middle of a name is kept."""
    assert bootstrap_module._paste_word(name) == word
    out = subprocess.run(["/bin/sh", "-c", f"printf %s {word}"],
                         capture_output=True, check=True).stdout
    assert out == os.fsencode(name)


@pytest.mark.parametrize("name", ["a\udcffb\n", "sp\n", "\ud83d"],
                         ids=["byte-then-LF", "ends-in-LF", "lone-surrogate"])
def test_a_name_with_no_printf_word_keeps_the_text_it_had(
        bootstrap_module, name):
    """`$(...)` strips a trailing line feed, so a word for such a name would
    be another path, and a lone surrogate has no byte at all: both keep what
    `spelled(shlex.quote(name))` made of them, as before, and are never the
    stripped word."""
    assert bootstrap_module._paste_word(name) == bootstrap_module.spelled(
        shlex.quote(name))


def test_a_name_the_codec_would_not_read_back_keeps_the_text_it_had(
        bootstrap_module, monkeypatch):
    """The word is the bytes `os.fsencode` gives the name, so it is the name
    only where `os.fsdecode` gives the name back from them. Under Windows'
    legacy code page (`LegacyWindowsOs`: `fsdecode` replaces what the page
    lacks) it does not, and a word would name another path: the name keeps
    what `spelled(shlex.quote(name))` made of it."""
    monkeypatch.setattr(bootstrap_module, "os", LegacyWindowsOs())
    name = "a\udcffb"
    assert bootstrap_module._paste_word(name) == bootstrap_module.spelled(
        shlex.quote(name))


def test_a_stdout_that_is_not_there_is_asked_as_utf8(
        bootstrap_module, monkeypatch):
    """`pythonw` has no stdout (`sys.stdout` is None): the word is the one
    a UTF-8 stdout gets, and nothing raises."""
    monkeypatch.setattr(sys, "stdout", None)
    assert bootstrap_module._paste_word("origin/café") == (
        "'origin/café'")
    assert bootstrap_module._paste_word("a\udcffb") == (
        r'''"$(printf -- 'a\377b')"''')


def test_bootstrap_imports_nothing_new_from_the_pinned_library():
    """`_paste_word` is a copy of what the library has, as the root's other
    helpers are (#370, #610): a root re-copies its pinned files one row at a
    time, so a `repo_shape` name added to `bootstrap.py` may not be in the
    copy an older root has."""
    tree = ast.parse(TEMPLATE.read_text(encoding="utf-8"))
    imports = [node for node in ast.walk(tree)
               if isinstance(node, ast.ImportFrom)
               and node.module == "repo_shape"]
    names = {alias.name for node in imports for alias in node.names}
    assert names == FROM_REPO_SHAPE, names
