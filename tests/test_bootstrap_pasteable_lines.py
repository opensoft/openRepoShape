# SPDX-License-Identifier: Apache-2.0
"""A command step (a) prints for a person to paste names its path and its ref
in a word a shell reads back as the same name (#932).

`move_back_to_pin` prints `git -C <leg> merge --ff-only <upstream>`, and
`_say_in_progress` a leg's `git -C <leg> <verb> --continue` and `--abort`.
Both went through `spelled(shlex.quote(...))`, and `_initialized` (#961) put
`spelled(path)` in `git submodule update --init <leg>`, for a leg that is not
there, with no quote and no `--`. `spelled` writes a byte that
is not UTF-8 as #391's `\\udcXX` text, and a control character, a line
separator and a bidirectional control as the escape Python spells it, and a
shell reads `'origin/a\\udcffb'` as the characters it is. RV824 measured it
on #824: for an upstream `origin/a<0xff>b` the line named no ref, and git
answered `not something we can merge`.

THE RULE NOW (`_paste_word`). A name that `spelled` has nothing to escape in
is the word it was, byte for byte (`shlex.quote`), where this stdout can
write it as the bytes git is handed: an ASCII name on any stdout, and one
that is not ASCII where the stdout's codec and the filesystem's give the
same bytes for it. A word that begins with `=` is quoted, as zsh expands a
bare one (#961). Any other is `"$(printf -- '<octal escapes>')"`, which `sh`
turns back into the bytes `os.fsencode` gives the name. A name that has no
such word (one that ends in a line feed, which `$(...)` strips, one with a
NUL, which it drops, and one `os.fsencode` cannot write) keeps what
`spelled` made of it. The leg's path in `git submodule update --init -- <leg>`
is such a word too, after a `--`, which keeps a path that begins with `-`
from being read as an option. The bytes git is handed are `os.fsencode`'s on
POSIX and UTF-8 on Windows, where git is handed UTF-16 and stores UTF-8.

THE TESTS THAT TAKE A `root` RUN WHAT WAS PRINTED, AS PRINTED: the command
in the line, through a shell's `-c` from the root, and ask where the branch
is, or the operation, afterwards. Asked of the words themselves it would
hold only what the helper says of itself, which the first fix would have
changed with it. The tests that take `bootstrap_module` ask `_paste_word`
for its words, in process, and where a shell's reading is the question run
the word through that shell; the stdout and the filesystem encoding they
vary are stubs, as `LegacyWindowsOs` is.

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
from repo_shape import shell_quoted
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
    # Two escapes that are the bytes of a character (`spéc`, U+DCC3 U+DCA9):
    # git is handed those bytes, and a `printf` prints them (#961).
    pytest.param("sp\udcc3\udca9c", r"sp\udcc3\udca9c",
                 r'''"$(printf -- 'sp\303\251c')"''', id="UTF-8-as-bytes"),
    # zsh expands a bare `=spec` to the path of a command (#961).
    pytest.param("=spec", "=spec", "'=spec'", id="leading-equals"),
    pytest.param("my spec", "my spec", "'my spec'", id="space"),
    # `git -C -spec` takes the path; a `--init -spec` is an option (#961).
    pytest.param("-spec", "-spec", "-spec", id="leading-dash-ASCII"),
]
SHELLS = [pytest.param(shell, id=shell.rsplit("/", 1)[1]) for shell in
          ("/bin/sh", "/bin/dash", "/bin/bash", "/bin/zsh")]


class Stdout:
    """The one thing `_prints_as_it_is` reads of `sys.stdout`: its codec."""

    def __init__(self, encoding: str):
        self.encoding = encoding


class Latin1Os:
    """`os` where the filesystem encoding is latin-1: git is handed `é` as
    the byte 0xe9, and each byte reads back as the character of that number.
    Only what `bootstrap.py` reads of it differs; everything else is this
    system's `os`, as `LegacyWindowsOs`'s is."""

    @staticmethod
    def fsencode(name: str) -> bytes:
        return name.encode("latin-1", "surrogateescape")

    @staticmethod
    def fsdecode(raw: bytes) -> str:
        return raw.decode("latin-1", "surrogateescape")

    def __getattr__(self, attr: str):
        return getattr(os, attr)


LATIN1_FS = Latin1Os()
#: The `printf` word of `origin/café` as git is handed it under UTF-8.
CAFE_AS_BYTES = r'''"$(printf -- 'origin/caf\303\251')"'''


class WindowsOs:
    """`os` on Windows in its default mode: `nt`, and a UTF-8 `fsencode`,
    which this system's is. Only `name` differs from this system's `os`."""

    name = "nt"

    def __getattr__(self, attr: str):
        return getattr(os, attr)


class LegacyMbcsOs(WindowsOs):
    """`os` on Windows under `PYTHONLEGACYWINDOWSFSENCODING=1`: `fsencode`
    is the code page's (`cp1252` here) with `replace`, so it is not the bytes
    git is handed, which are UTF-8, as `LegacyWindowsOs` is for `fsdecode`."""

    @staticmethod
    def fsencode(name: str) -> bytes:
        return name.encode("cp1252", "replace")

    @staticmethod
    def fsdecode(raw: bytes) -> str:
        return raw.decode("cp1252", "replace")


WINDOWS_FS = WindowsOs()
LEGACY_MBCS_FS = LegacyMbcsOs()


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


def emptied_leg_line(root: Path, tmp_path: Path, path: str
                     ) -> tuple[Path, str]:
    """The spec leg mounted at `path` and emptied (`git submodule deinit`),
    so that step (a) finds it not there: its directory, and the line step
    (a) prints for it (#961)."""
    if "\udcff" in path:
        needs_the_byte(tmp_path)
    leg = mounted_at(root, path)
    # Bytes: git's own line names the path, which may be the byte 0xff.
    emptied = subprocess.run(["git", "submodule", "deinit", "-f", "--", path],
                             cwd=str(root), capture_output=True, check=False)
    assert emptied.returncode == 0, emptied.stderr.decode("utf-8", "replace")
    assert not os.path.lexists(leg / ".git"), "the leg is emptied"
    return leg, not_initialized_line(root)


def not_initialized_line(root: Path) -> str:
    """The one line of step (a) that says a leg is NOT INITIALIZED."""
    result = skip_validators(root)
    assert result.returncode == 0, result.stderr + result.stdout
    lines = [line for line in step_a(result.stdout)
             if "NOT INITIALIZED" in line]
    assert len(lines) == 1, result.stdout
    return lines[0]


def printed_by(shell: str, word: str) -> bytes:
    """What `shell` prints for `printf %s <word>`: the bytes it reads the
    word as. Skips where this system has no such shell."""
    if not os.path.exists(shell):
        pytest.skip(f"this system has no {shell}")
    proc = subprocess.run([shell, "-c", f"printf %s {word}"],
                          capture_output=True, check=False)
    assert proc.returncode == 0, word + "\n" + proc.stderr.decode(
        "utf-8", "replace")
    return proc.stdout


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
    without its escape. A path made of the escapes of a character's bytes
    (`sp<U+DCC3><U+DCA9>c`, the directory `spéc`) is that directory too, and
    one that begins with `=` is quoted, which zsh would expand (#961)."""
    pin, ahead, lines = moved_back_lines(root, tmp_path, path=path)

    command = f"git -C {word} merge --ff-only origin/main"
    assert lines[0] == moved_back_line(label, ahead, pin, "origin/main",
                                       command), lines
    leg = root / path
    assert rev(leg, MAIN) == pin
    pasted(root, command_of(lines[0]))
    assert rev(leg, MAIN) == ahead


@pytest.mark.parametrize("shell", SHELLS)
def test_a_leg_path_that_begins_with_an_equals_sign_is_pasteable_in_a_shell(
        root, tmp_path, shell):
    """THE ISSUE (#961): `git -C =spec merge ...` is read by zsh as the path
    of a command called `spec`, and stops at `zsh: spec not found`. Quoted,
    the printed command brings `main` forward in each shell, zsh included
    (dash and bash read the bare word too, which is why only zsh failed)."""
    pin, ahead, lines = moved_back_lines(root, tmp_path, path="=spec")

    pasted(root, command_of(lines[0]), shell)
    assert rev(root / "=spec", MAIN) == ahead


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


# --- the command that initializes a leg that is not there -------------------

@pytest.mark.parametrize("path, label, word", [
    row for row in PATHS if not row.values[0].startswith("-")])
def test_the_initializing_command_is_pasteable_whatever_the_legs_path_is(
        root, tmp_path, path, label, word):
    """THE ISSUE (#961, rv932's SHOULD 3): `_initialized` printed `git
    submodule update --init {spelled(path)}`, bare, which was two pathspecs
    for `my spec`, expanded by zsh for `=spec`, an option for `-spec` and the
    escape text for a byte that is not UTF-8. The leg is emptied (`git
    submodule deinit`) and step (a) says it is not there; the command it
    prints, run as printed from the root, puts the leg back at its pin:
    its `.git` is there again, and its HEAD is the commit the root's index
    records (the move of the leg is staged, not committed). A path that
    begins with `-` is the next test's, as git holds no submodule there."""
    leg, line = emptied_leg_line(root, tmp_path, path)

    assert line == (f"  [spec] {label}: NOT INITIALIZED. Run `git submodule "
                    f"update --init -- {word}` \u2014 the validators below "
                    "will refuse until you do."), line
    pasted(root, command_of(line))
    assert os.path.lexists(leg / ".git"), "the leg is initialized again"
    pin = git("rev-parse", f":{path}", cwd=root).stdout.strip()
    assert rev(leg) == pin


def test_the_initializing_command_reads_a_path_that_begins_with_a_dash(
        root):
    """Git ignores a `submodule.<name>.path` that begins with `-` (it warns
    that it may be read as an option), so no command can initialize a leg
    there. What `--` changes is what git says of it: that it found no
    submodule at the PATH `-spec` (in words that differ by version), where
    `--init -spec` is an option (#961)."""
    leg = mounted_at(root, "-spec")
    (leg / ".git").unlink()
    line = not_initialized_line(root)

    assert command_of(line) == "git submodule update --init -- -spec", line
    proc = subprocess.run(["/bin/sh", "-c", command_of(line)], cwd=str(root),
                          capture_output=True, check=False)
    assert b"path '-spec'" in proc.stderr, proc.stderr


@pytest.mark.parametrize("shell", SHELLS)
def test_the_initializing_command_of_an_equals_sign_path_pastes_in_a_shell(
        root, tmp_path, shell):
    """A leg at `=spec`: zsh expands the bare word of `--init =spec` to the
    path of a command called `spec` and stops, so the word is quoted, and
    the command puts the leg back in each shell (#961)."""
    leg, line = emptied_leg_line(root, tmp_path, "=spec")

    pasted(root, command_of(line), shell)
    assert os.path.lexists(leg / ".git"), "the leg is initialized again"


# --- every ordinary line is what it was -------------------------------------

@pytest.mark.parametrize("name, word", [
    ("spec", "spec"),
    ("origin/main", "origin/main"),
    ("my spec", "'my spec'"),
    ("it's", "'it'\"'\"'s'"),
    ("", "''"),
    ("a=b", "a=b"),
    pytest.param("origin/café", "'origin/café'", id="printable-UTF-8"),
    pytest.param("日本", "'日本'", id="CJK"),
    pytest.param("a\u00a0b", "'a\u00a0b'", id="no-break-space"),
], ids=lambda value: None if value else "empty")
def test_a_name_with_nothing_to_escape_is_the_word_it_was(
        bootstrap_module, name, word):
    """Byte for byte `spelled(shlex.quote(name))`, which every such word
    was: no `printf`, no new quoting. A U+00A0 is no escape to `spelled`,
    and prints as it is, and an `=` that does not begin the word is itself
    to every shell."""
    assert bootstrap_module._paste_word(name) == word
    assert word == bootstrap_module.spelled(shlex.quote(name))


@pytest.mark.parametrize("name, word", [
    ("=x", "'=x'"),
    ("=ls", "'=ls'"),
    ("=", "'='"),
    ("==x", "'==x'"),
    ("=%", "'=%'"),
    ("=a b", "'=a b'"),
    ("origin/=x", "origin/=x"),
], ids=lambda value: None if value else "empty")
def test_a_word_that_begins_with_an_equals_sign_is_quoted(
        bootstrap_module, name, word):
    """`shell_quoted` quotes a word that begins with `=` (#486), and so does
    `_paste_word` (#961), once: a word `shlex.quote` quotes already is not
    quoted again, and an `=` inside a name is left as it was. The word is
    `shell_quoted`'s, as the doctor and `family.py` word theirs."""
    assert bootstrap_module._paste_word(name) == word
    assert word == shell_quoted(name, "posix")


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("name", ["=x", "=ls", "=", "==x", "=%", "=a b"])
def test_a_word_that_begins_with_an_equals_sign_reads_back_in_every_shell(
        bootstrap_module, shell, name):
    """zsh expands a bare `=ls` to `/usr/bin/ls` and stops at `=x`, so what
    is asked is the shell: the word prints the name, in dash, bash and zsh
    alike (#961)."""
    word = bootstrap_module._paste_word(name)
    assert printed_by(shell, word) == name.encode("ascii")


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


# --- a stdout that does not write the bytes git is handed -------------------

@NEEDS_A_UTF8_PROCESS
@pytest.mark.parametrize("encoding, held", [
    pytest.param("ascii", r"origin/caf\xe9", id="cannot-write-it"),
    pytest.param("latin-1", "origin/café", id="writes-other-bytes"),
])
def test_a_stdout_of_another_codec_than_the_names_gets_the_printf_word(
        root, tmp_path, encoding, held):
    """`PYTHONIOENCODING=ascii` writes `é` as `\\xe9`, which no shell
    reads back as the name, and `latin-1` writes it as the byte 0xe9, where
    git was handed 0xc3 0xa9 (#961): pasted, the quoted word named no ref.
    So the command holds the bytes git is handed, as `printf` does; the
    prose names the upstream as the stdout writes it, read back here in that
    codec."""
    leg = root / "spec"
    pin, ahead = past_the_pin(leg, "café", "main")

    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "bootstrap.py"),
         "--skip-validators"], cwd=str(root), stdin=subprocess.DEVNULL,
        env={**os.environ, "PYTHONIOENCODING": encoding},
        capture_output=True, check=False)
    printed = result.stdout.decode(encoding)
    assert result.returncode == 0, printed + result.stderr.decode(
        encoding, "replace")
    word = r'''"$(printf -- 'origin/caf\303\251')"'''
    command = f"git -C spec merge --ff-only {word}"
    line = moved_back_line("spec", ahead, pin, held, command)
    assert line in printed.split("\n"), printed
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
    # Escapes that are the bytes of a character, which `os.fsdecode` reads
    # as that character: git is handed those bytes, so they have a word.
    ("sp\udcc3\udca9c", r'''"$(printf -- 'sp\303\251c')"'''),
    ("caf\udcc3\udca9\udcff", r'''"$(printf -- 'caf\303\251\377')"'''),
    # An escape is ALWAYS three digits: a digit that follows is the name's.
    ("a\x1b7\udcff", r'''"$(printf -- 'a\0337\377')"'''),
    ("\t1\udcff", r'''"$(printf -- '\0111\377')"'''),
])
def test_the_printf_word_prints_the_bytes_of_the_name(
        bootstrap_module, name, word):
    """The word for each byte class, exactly, and what `/bin/sh` makes of it
    is the bytes `os.fsencode` gives the name: a byte outside the safe set is
    a three-digit octal escape, `%` and the backslash and the apostrophe
    included, and a newline in the middle of a name is kept. So are the
    escapes of a character's bytes (#961): `os.fsdecode` of them is that
    character, which is no reason to keep the escape text."""
    assert bootstrap_module._paste_word(name) == word
    assert printed_by("/bin/sh", word) == os.fsencode(name)


@pytest.mark.parametrize("name", ["a\udcffb\n", "sp\n", "\ud83d", "a\x00b"],
                         ids=["byte-then-LF", "ends-in-LF", "lone-surrogate",
                              "NUL"])
def test_a_name_with_no_printf_word_keeps_the_text_it_had(
        bootstrap_module, name):
    """`$(...)` strips a trailing line feed and drops a NUL, so a word for
    such a name would be another path (the NUL's was `ab` in dash and bash,
    #961), and a lone surrogate has no byte at all: each keeps what
    `spelled(shlex.quote(name))` made of it, as before, and is never the
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


@pytest.mark.parametrize("encoding, filesystem, word", [
    pytest.param("utf-8", None, "'origin/café'", id="both-UTF-8"),
    pytest.param("latin-1", None, CAFE_AS_BYTES, id="stdout-latin-1"),
    pytest.param("cp1252", None, CAFE_AS_BYTES, id="stdout-cp1252"),
    pytest.param("utf-8", LATIN1_FS, r'''"$(printf -- 'origin/caf\351')"''',
                 id="filesystem-latin-1"),
    pytest.param("latin-1", LATIN1_FS, "'origin/café'", id="both-latin-1"),
    pytest.param("cp1252", LATIN1_FS, "'origin/café'",
                 id="two-codecs-one-byte-for-this-name"),
])
def test_a_name_that_is_not_ascii_is_quoted_where_both_codecs_give_its_bytes(
        bootstrap_module, monkeypatch, encoding, filesystem, word):
    """A quoted `é` is what the terminal shows, and a paste of it is the
    bytes the stdout's codec made of it: only where those are the bytes
    `os.fsencode` gives the name, the ones git is handed, does the paste name
    the same. Under a latin-1 stdout and a UTF-8 filesystem (a stdout the
    locale does not set, `PYTHONIOENCODING`, a terminal emulator that is
    not UTF-8) the word was `'origin/café'`, pasted as 0xe9 where the ref is
    0xc3 0xa9; under a latin-1 filesystem and a UTF-8 stdout it was the
    reverse (#961). `cp1252` and `latin-1` are two codecs and one byte for
    `é`, and that is all the name asks. The filesystem encoding is the
    shim's `os.fsencode`, as `LegacyWindowsOs`'s is."""
    monkeypatch.setattr(sys, "stdout", Stdout(encoding))
    if filesystem is not None:
        monkeypatch.setattr(bootstrap_module, "os", filesystem)
    assert bootstrap_module._paste_word("origin/café") == word


@pytest.mark.parametrize("encoding", ["latin-1", "ascii", "utf-16"])
def test_an_ascii_name_is_the_word_it_was_on_any_stdout(
        bootstrap_module, monkeypatch, encoding):
    """An ASCII name shows as itself on every stdout that can write it, so
    the filesystem's codec is not asked of it (#961): `origin/main` stays
    bare, under a UTF-16 stdout too, whose bytes are not git's."""
    monkeypatch.setattr(sys, "stdout", Stdout(encoding))
    monkeypatch.setattr(bootstrap_module, "os", LATIN1_FS)
    assert bootstrap_module._paste_word("origin/main") == "origin/main"


@pytest.mark.parametrize("encoding, filesystem, word", [
    pytest.param("utf-8", LEGACY_MBCS_FS, "'origin/café'",
                 id="legacy-mode-UTF-8-stdout"),
    pytest.param("cp1252", WINDOWS_FS, CAFE_AS_BYTES,
                 id="default-mode-cp1252-stdout"),
    pytest.param("utf-8", WINDOWS_FS, "'origin/café'",
                 id="default-mode-UTF-8-stdout"),
])
def test_on_windows_the_bytes_git_is_handed_are_utf_8(
        bootstrap_module, monkeypatch, encoding, filesystem, word):
    """git for Windows is handed UTF-16 and stores UTF-8, and Git Bash reads
    a paste as UTF-8, so the stdout is compared with the UTF-8 of the name
    and not with `os.fsencode`: under `PYTHONLEGACYWINDOWSFSENCODING=1` that
    is `mbcs`, and a UTF-8 stdout got `origin/caf\\351`, a name Git Bash does
    not hold, where the quoted word was right (rv973's NIT 1, #961). In
    the default mode the two are the same bytes. The `printf` word of a name
    a legacy-mode stdout cannot write is still made of `os.fsencode`'s
    bytes, and no row here says it is right."""
    monkeypatch.setattr(sys, "stdout", Stdout(encoding))
    monkeypatch.setattr(bootstrap_module, "os", filesystem)
    assert bootstrap_module._paste_word("origin/café") == word


def test_the_euro_sign_is_quoted_on_a_utf_8_stdout_under_the_legacy_mode(
        bootstrap_module, monkeypatch):
    """The euro sign is one byte in `cp1252`, 0x80, and three in UTF-8: the
    `printf` word of `os.fsencode`'s bytes was `\\2005` for `<euro>5`, which
    is no name Git Bash holds (rv973's NIT 1, #961)."""
    monkeypatch.setattr(sys, "stdout", Stdout("utf-8"))
    monkeypatch.setattr(bootstrap_module, "os", LEGACY_MBCS_FS)
    assert bootstrap_module._paste_word("\u20ac5") == "'\u20ac5'"


def test_a_name_the_filesystem_encoding_cannot_write_keeps_the_text_it_had(
        bootstrap_module, monkeypatch):
    """`日本` is printable and this stdout writes it, but a latin-1 filesystem
    has no bytes for it, so git cannot be handed it: the word is the text it
    was, and the comparison of the bytes, asked inside `_prints_as_it_is`'s
    `try`, raises nothing (rv973's NIT 2: moved out of it, `os.fsencode`
    raised `UnicodeEncodeError`)."""
    monkeypatch.setattr(sys, "stdout", Stdout("utf-8"))
    monkeypatch.setattr(bootstrap_module, "os", LATIN1_FS)
    assert bootstrap_module._paste_word("日本") == "'日本'"


def test_a_stdout_with_no_such_codec_gets_the_printf_word(
        bootstrap_module, monkeypatch):
    """A stream a caller replaced may name any encoding, and `str.encode`
    answers an unknown one with a `LookupError`, which is no
    `UnicodeEncodeError`: no codec holds the name, so it gets the `printf`
    word, which is ASCII, and nothing raises (#961)."""
    monkeypatch.setattr(sys, "stdout", Stdout("no-such-codec"))
    assert bootstrap_module._paste_word("origin/main") == (
        r'''"$(printf -- 'origin/main')"''')


def test_the_printf_word_is_the_bytes_the_filesystem_encoding_gives(
        bootstrap_module, monkeypatch):
    """Git is handed `os.fsencode`'s bytes, so the word prints those: under
    a latin-1 filesystem `é` is the byte 0xe9, and the UTF-8 bytes of the
    character (`name.encode("utf-8", "surrogateescape")`) would name another
    path, `cafÃ©`. Run through `/bin/sh`, the word prints what the shim's
    `fsencode` gives (#961)."""
    monkeypatch.setattr(bootstrap_module, "os", LATIN1_FS)
    word = bootstrap_module._paste_word("café\t")
    assert word == r'''"$(printf -- 'caf\351\011')"'''
    assert printed_by("/bin/sh", word) == b"caf\xe9\t"


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
