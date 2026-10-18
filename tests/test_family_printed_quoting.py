# SPDX-License-Identifier: Apache-2.0
"""Every command `scripts/family.py` and a holder's `scripts/siblings.py`
print for a person to paste spells its paths through ONE quoter,
`repo_shape.shell_quoted` (#486).

They printed every path bare. A family folder whose path holds a space is
ordinary ("My Projects" on macOS, a Windows profile directory), and under a
holder at `.../my work/Sonata/Sonata`:

  * `add`'s `member-git-dir-cached` remedy, `rm -rf <the cached store>`,
    split into `rm -rf .../my`, an absolute directory that is NOT the store,
    and a second argument relative to wherever the person stood;
  * `remove`'s note about the same store named it the same way;
  * `init`'s NEXT STEPS and `add`'s NEXT split `--family-root` and `git -C`
    in two (`fatal: cannot change to '.../my'`, exit 128);
  * `siblings.py`'s `mv` lines for a misnamed family folder pasted as four
    arguments and moved nothing.

THE PROOF IS THE SHELL'S OWN READING. Each printed command, under a holder
whose path holds a space (and, in the second run, an apostrophe), is split
the way the reader's shell splits it, and must come back as the argv it was
meant to be: `shlex.split` for a POSIX shell, and `powershell_words` below
for PowerShell, the dialect `shell_quoted` speaks on Windows. A command for
a POSIX shell only (`rm -rf`, `mv`, `mkdir -p`) is quoted for one on every
host and split with `shlex` on every host. Where a command is safe to run in
a test, it is RUN as split: the `rm -rf` deletes the store and the decoy
directory a bare split would have named survives; the `mv` lines move the
holder where the warning said.

THE SAME FAMILY AS `test_family.py`: members scaffolded into local bare
repositories, no network, and a holder COPIED into the awkward folder.
"""

from __future__ import annotations

import importlib.util
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import NO_BYTECODE, REPO, git, run_script
#: The family fixture and its names, imported from the module that owns them.
from test_family import (  # noqa: F401
    FAMILY, NAME, ORG, SPARE, family, manifest, validate,
)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import (  # noqa: E402
    PYTHON, SHELL_BARE_NT, SHELL_BARE_POSIX, host_shell_dialect, shell_line,
    shell_quoted,
)

#: The two folders a holder is copied into: a space, and a space beside an
#: apostrophe, which is where `sh` and PowerShell escape differently.
FOLDERS = ["my work", "Dana's work"]

#: The characters PowerShell reads as a single quote.
PS_QUOTES = "'\u2018\u2019\u201a\u201b"


def powershell_words(line: str) -> list[str]:
    """PowerShell's reading of a command line, as far as these commands
    need it: whitespace-separated words, where a word may be or hold a
    verbatim `'...'` string, inside which any of PowerShell's five single
    quotes doubled is one of it and nothing else is special. That is the
    only quoting `shell_quoted` emits for PowerShell; a test that split on
    whitespace would tear a quoted path with a space in it in half."""
    words: list[str] = []
    index, length = 0, len(line)
    while index < length:
        if line[index].isspace():
            index += 1
            continue
        word: list[str] = []
        while index < length and not line[index].isspace():
            if line[index] in PS_QUOTES:
                index += 1
                while index < length:
                    if line[index] not in PS_QUOTES:
                        word.append(line[index])
                        index += 1
                    elif index + 1 < length and line[index + 1] in PS_QUOTES:
                        word.append(line[index + 1])
                        index += 2
                    else:
                        index += 1
                        break
                continue
            word.append(line[index])
            index += 1
        words.append("".join(word))
    return words


def host_words(line: str) -> list[str]:
    """`line` as the shell `shell_quoted` speaks on THIS host reads it:
    PowerShell's where `host_shell_dialect` says so, `sh`'s under Git Bash
    and everywhere else (#711)."""
    return (powershell_words(line) if host_shell_dialect() == "nt"
            else shlex.split(line))


# --- the quoter ---------------------------------------------------------------

#: What must survive UNQUOTED, on both platforms: a line whose whole job is
#: to be read should not carry quotes no shell needs.
ORDINARY = ["/srv/work/Atlas", "scripts/family.py", "--family-root",
            "members/IRRS", "family/add-irrs",
            "3d46ab5b9c1dcafe0123456789abcdef01234567", "origin", "-C",
            "KEY=value"]

#: Values each shell must be handed whole: a space, an apostrophe, both, a
#: Windows path with both, a name no ASCII flattening may touch, the
#: typographic apostrophe a macOS folder name carries, shell syntax, and the
#: empty string.
AWKWARD = [
    "/srv/my projects/Atlas",
    "/srv/O'Brien/Atlas",
    "/srv/Code Projects/Sonata/Sonata/.git/modules/members/Beacon",
    r"C:\Users\Jane O'Neill\proj",
    "/srv/José/Atlas",
    "/srv/Dana\u2019s work/Atlas",
    "$HOME/a;b`c`|d&e",
    "~/x", "a,b", "@a", "",
]


@pytest.mark.parametrize("platform", ["posix", "nt"])
@pytest.mark.parametrize("value", ORDINARY)
def test_an_ordinary_word_is_left_alone(platform, value):
    assert shell_quoted(value, platform) == value


@pytest.mark.parametrize("value", AWKWARD)
def test_the_posix_form_is_one_word_to_sh(value):
    quoted = shell_quoted(value, "posix")
    assert shlex.split(quoted) == [value], quoted


@pytest.mark.parametrize("value", AWKWARD)
def test_the_powershell_form_is_one_word_to_powershell(value):
    quoted = shell_quoted(value, "nt")
    assert powershell_words(quoted) == [value], quoted


def test_the_two_dialects_escape_an_apostrophe_differently():
    """Each reads the other's escape as a different value: `sh` reads
    `'O''Brien'` as `OBrien`. So the dialect is the shell's (#711)."""
    assert shell_quoted("O'Brien", "posix") == "'O'\\''Brien'"
    assert shell_quoted("O'Brien", "nt") == "'O''Brien'"
    assert shlex.split(shell_quoted("O'Brien", "nt")) == ["OBrien"]
    here = host_shell_dialect()
    assert shell_quoted("O'Brien") == shell_quoted("O'Brien", here)


def test_nothing_is_flattened_and_a_typographic_apostrophe_is_doubled():
    """A command that deletes a directory must name THAT directory: `é`
    stays `é`, where the doctor's ASCII report would flatten it. PowerShell
    reads `’` as an apostrophe, so its form doubles it."""
    assert shell_quoted("/srv/José", "posix") == "'/srv/José'"
    assert shell_quoted("Dana\u2019s", "nt") == "'Dana\u2019\u2019s'"
    assert shell_quoted("Dana\u2019s", "posix") == "'Dana\u2019s'"


def test_a_line_is_its_words_each_quoted():
    words = ["git", "-C", "/srv/my work/Sonata", "push", "-u", "origin",
             "refs/heads/family/add-irrs:refs/heads/family/add-irrs"]
    assert shlex.split(shell_line(words, "posix")) == words
    assert powershell_words(shell_line(words, "nt")) == words


#: Words that begin with `=`, which zsh (macOS's login shell) expands to a
#: command's path when bare: `=ls` reaches the command as `/bin/ls`.
LEADING_EQUALS = ["=ls", "=", "==x", "=/srv/work"]


@pytest.mark.parametrize("platform", ["posix", "nt"])
@pytest.mark.parametrize("value", LEADING_EQUALS)
def test_a_word_that_begins_with_equals_is_quoted(platform, value):
    quoted = shell_quoted(value, platform)
    assert quoted == f"'{value}'"
    assert shlex.split(quoted) == [value]
    assert powershell_words(quoted) == [value]


@pytest.mark.skipif(os.name == "nt", reason="a POSIX shell's own reading")
@pytest.mark.parametrize("shell", ["sh", "bash", "zsh"])
def test_a_real_shell_hands_each_word_back_whole(shell):
    """The shells themselves, where the host has them: each value, quoted,
    comes back from `printf` byte for byte, and zsh's `=` is among them."""
    if shutil.which(shell) is None:
        pytest.skip(f"no {shell} on this host")
    values = [*LEADING_EQUALS, "KEY=value", *AWKWARD,
              *(chr(code) for code in range(0x21, 0x7f))]
    line = "printf '%s\\0' " + shell_line(values, "posix")
    argv = [shell, "-f", "-c", line] if shell == "zsh" else \
        [shell, "-c", line]
    printed = subprocess.run(argv, capture_output=True, check=True).stdout
    assert printed.decode("utf-8").split("\0")[:-1] == values


@pytest.fixture(scope="module")
def doctor():
    spec = importlib.util.spec_from_file_location(
        "doctor_for_quoting", REPO / "shape-doctor.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: Every printable ASCII character, alone, before a word, inside one and
#: after one: a character the two alphabets disagree about cannot hide from
#: this the way it could from a hand-picked sample.
EVERY_ASCII = sorted({form for code in range(0x20, 0x7f)
                      for form in (chr(code), f"{chr(code)}a",
                                   f"a{chr(code)}b", f"a{chr(code)}")})


@pytest.mark.parametrize("platform", ["posix", "nt"])
def test_it_is_the_doctors_rule_on_any_ascii_value(doctor, platform):
    """ONE RULE IN TWO PLACES, held together here. `shape-doctor.py`'s
    `quote_arg` flattens its value to ASCII first, because its report is
    pure ASCII, and is otherwise this function: the same two alphabets and
    the same two escapes. On an ASCII value the two must agree, but for a
    leading `=` in PowerShell's dialect: this function quotes it in both,
    because zsh expands a bare `=word`, and the doctor quotes it for `sh`
    only (#532), because PowerShell expands nothing there."""
    values = [*ORDINARY, *LEADING_EQUALS,
              *(value for value in AWKWARD if value.isascii()),
              r"C:\work,old\Atlas", *EVERY_ASCII]
    differ = {value: (shell_quoted(value, platform),
                      doctor.quote_arg(value, platform))
              for value in values
              if not (platform == "nt" and value.startswith("="))
              and shell_quoted(value, platform)
              != doctor.quote_arg(value, platform)}
    assert differ == {}
    for value in EVERY_ASCII:
        quoted = shell_quoted(value, platform)
        reader = powershell_words if platform == "nt" else shlex.split
        assert reader(quoted) == [value], quoted


@pytest.mark.parametrize("value", LEADING_EQUALS)
def test_the_doctor_quotes_a_word_that_begins_with_equals_for_sh(doctor,
                                                                value):
    """#532. `quote_arg` left a leading `=` bare, so a NEXT line holding one
    (a branch named `=x`) ran in zsh, macOS's login shell, with `=x` read as
    the path of a command `x`. Quoted, `sh` reads the value that went in."""
    quoted = doctor.quote_arg(value, "posix")
    assert quoted == f"'{value}'"
    assert shlex.split(quoted) == [value]


@pytest.mark.parametrize("value", ["KEY=value", "--root=/srv/work", "a=",
                                   "x==y"])
def test_an_equals_sign_anywhere_but_the_front_stays_bare(doctor, value):
    """Only a LEADING `=` is expanded, so the doctor's lines that carry
    `KEY=value` words print as they always did."""
    assert doctor.quote_arg(value, "posix") == value


@pytest.mark.parametrize("value", LEADING_EQUALS)
def test_the_doctors_powershell_dialect_leaves_a_leading_equals_alone(doctor,
                                                                      value):
    """PowerShell expands no `=word`, so the dialect that quotes for it has no
    such gap and is not changed (#532): the doctor's lines on Windows print
    as they did."""
    assert doctor.quote_arg(value, "nt") == value


@pytest.mark.skipif(os.name == "nt", reason="a POSIX shell's own reading")
@pytest.mark.parametrize("shell", ["sh", "bash", "zsh"])
def test_a_real_shell_hands_back_each_word_the_doctor_quoted(doctor, shell):
    """The shells themselves, where the host has them: each value, quoted by
    the doctor for `sh`, comes back from `printf` byte for byte. `zsh -f` is
    the one that matters here, and the one that expands a bare `=ls`."""
    if shutil.which(shell) is None:
        pytest.skip(f"no {shell} on this host")
    values = [*LEADING_EQUALS, "KEY=value",
              *(value for value in AWKWARD if value.isascii()),
              *(chr(code) for code in range(0x21, 0x7f))]
    line = "printf '%s\\0' " + " ".join(doctor.quote_arg(value, "posix")
                                        for value in values)
    argv = [shell, "-f", "-c", line] if shell == "zsh" else \
        [shell, "-c", line]
    printed = subprocess.run(argv, capture_output=True, check=True).stdout
    assert printed.decode("utf-8").split("\0")[:-1] == values


def test_the_two_alphabets_are_the_doctors(doctor):
    """The same two character sets, spelled as the same two patterns: the
    doctor anchors its with `^...$`, and these are asked with `fullmatch`."""
    assert doctor.UNQUOTED_POSIX.pattern == f"^{SHELL_BARE_POSIX.pattern}$"
    assert doctor.UNQUOTED_NT.pattern == f"^{SHELL_BARE_NT.pattern}$"


# --- the commands, under a folder with a space in it --------------------------

def copied_holder(family, base: Path) -> Path:
    """A private copy of the family's holder at `<base>/InkRouter`."""
    base.mkdir(parents=True, exist_ok=True)
    holder = base / NAME
    shutil.copytree(family["root"], holder, symlinks=True)
    return holder.resolve()


@pytest.mark.parametrize("folder", FOLDERS)
def test_init_next_steps_paste_whole(tmp_path, folder):
    """`add --family-root <holder>` and `cd <holder>`, each one line, each
    path one word."""
    into = tmp_path / folder
    into.mkdir()
    result = run_script(FAMILY, "init", "--org", ORG, "--family", "Orbit",
                        "--created-by", "Test Human",
                        "--created-on", "2026-10-12",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--into", str(into), cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    holder = into.resolve() / "Orbit" / "Orbit"
    block = result.stdout.split("NEXT STEPS", 1)[1].splitlines()
    add = next(line for line in block if " add --family-root " in line)
    script = os.path.relpath(FAMILY.resolve(), tmp_path.resolve())
    assert host_words(add) == [PYTHON, script, "add", "--family-root",
                               str(holder), "--member", f"{ORG}/<Project>"]
    at = next(index for index, line in enumerate(block)
              if line.strip().startswith("cd "))
    # Two lines, no `&&`: Windows PowerShell 5.1 rejects it between two
    # statements, and these lines are quoted for the host's shell.
    assert host_words(block[at]) == ["cd", str(holder)]
    assert block[at + 1].strip() == "make siblings"


@pytest.mark.parametrize("folder", FOLDERS)
def test_add_next_names_the_holder_whole(family, tmp_path, folder):
    """`git -C <holder> push ...`: the holder is one word, and that word is
    the holder, as git itself says when it is handed it."""
    holder = copied_holder(family, tmp_path / folder)
    result = run_script(FAMILY, "add", "--family-root", str(holder),
                        "--member", f"{ORG}/{SPARE}",
                        "--local-remote-dir", str(family["remotes"]))
    assert result.returncode == 0, result.stdout + result.stderr
    line = next(line for line in result.stdout.splitlines()
                if line.startswith("NEXT  "))
    words = host_words(line[len("NEXT  "):])
    assert words[:4] == ["git", "-C", str(holder), "push"], line
    toplevel = subprocess.run(["git", "-C", words[2], "rev-parse",
                               "--show-toplevel"], capture_output=True,
                              text=True, check=True).stdout.strip()
    assert os.path.samefile(toplevel, holder)


def deletion(lines: list[str], store: Path) -> list[str]:
    """The directory line and the command line after it, checked: the
    directory alone, as git spells it, then `rm -rf` and that directory as
    ONE word to a POSIX shell. Returns the command's argv."""
    shown = store.as_posix()
    at = lines.index(f"    {shown}")
    assert "POSIX shell" in lines[at + 1], lines
    command = lines[at + 2].strip()
    argv = shlex.split(command)
    assert argv == ["rm", "-rf", shown], command
    return argv


@pytest.mark.parametrize("folder", FOLDERS)
def test_the_cached_store_is_named_and_deleted_whole(family, tmp_path,
                                                     folder):
    """THE P1 ROW. `remove` leaves the member's object store behind and its
    note names it; `add` of the same member is refused over it and its
    remedy names it. Each prints the directory alone on its own line, then
    the `rm -rf` that deletes it, its one argument quoted. Run as split, the
    command deletes the store and nothing else: the decoy a bare split would
    have deleted (`<tmp>/my`, for `<tmp>/my work/...`) is still there, and
    the add then goes through."""
    decoy = tmp_path / folder.split(" ")[0]
    decoy.mkdir()
    (decoy / "keep.txt").write_text("not the store\n", encoding="utf-8")
    holder = copied_holder(family, tmp_path / folder)
    store = holder / ".git" / "modules" / "members" / "IRSS"

    removed = run_script(FAMILY, "remove", "--family-root", str(holder),
                         "--member", "IRSS")
    assert removed.returncode == 0, removed.stdout + removed.stderr
    assert store.is_dir()
    note = [line[2:] for line in removed.stdout.splitlines()]
    deletion(note, store)

    again = run_script(FAMILY, "add", "--family-root", str(holder),
                       "--member", f"{ORG}/IRSS",
                       "--local-remote-dir", str(family["remotes"]))
    assert again.returncode == 2, again.stdout + again.stderr
    assert "REFUSED member-git-dir-cached:" in again.stderr
    argv = deletion(again.stderr.splitlines(), store)

    if os.name == "nt":
        # `rm` is no program of Windows' own; the path is what the command
        # was split into, and that is what is deleted.
        shutil.rmtree(argv[2], onerror=lambda f, p, _e: (
            os.chmod(p, 0o700), f(p)))
    else:
        subprocess.run(argv, check=True)
    assert not store.exists()
    assert (decoy / "keep.txt").read_text(encoding="utf-8") == \
        "not the store\n"
    assert (holder / "family.yaml").is_file()
    back = run_script(FAMILY, "add", "--family-root", str(holder),
                      "--member", f"{ORG}/IRSS",
                      "--local-remote-dir", str(family["remotes"]))
    assert back.returncode == 0, back.stdout + back.stderr
    assert validate(holder).returncode == 0


@pytest.mark.parametrize("folder", FOLDERS)
def test_the_siblings_mv_lines_paste_whole_and_move_the_holder(family,
                                                              tmp_path,
                                                              folder):
    """`siblings.py`'s parent-folder warning: the holder sits in a folder
    not named after the family, and the warning prints the `mv` and `mkdir
    -p` that put it right and moves nothing. Each line is one command to a
    POSIX shell with every path one word, and run in order, as split, they
    move the holder to `<tmp>/InkRouter/InkRouter`."""
    holder = copied_holder(family, tmp_path / folder)
    result = run_script(FAMILY, "siblings", "--family-root", str(holder),
                        "--dry-run", env=NO_BYTECODE)
    assert result.returncode == 1, result.stdout + result.stderr  # #543
    assert "NOTHING WAS MOVED" in result.stderr
    assert "in a POSIX shell (Git Bash" in result.stderr
    commands = [shlex.split(line) for line in result.stderr.splitlines()
                if line.startswith(" " * 12) and line.strip()[:3] in
                ("mv ", "mkd")]
    staged = holder.parent.parent / f"{NAME}.holder"
    wanted = holder.parent.parent / NAME
    assert commands == [["mv", str(holder), str(staged)],
                        ["mkdir", "-p", str(wanted)],
                        ["mv", str(staged), str(wanted / NAME)]]
    assert holder.is_dir(), "the warning moves nothing"
    if os.name == "nt":
        return  # `mv` and `mkdir -p` are a POSIX shell's, as the line says
    for argv in commands:
        subprocess.run(argv, check=True)
    assert not holder.exists()
    moved = wanted / NAME
    assert (moved / "family.yaml").is_file()
    assert git("rev-parse", "--show-toplevel", cwd=moved).stdout.strip() \
        == str(moved)


# --- a holder that kept an older `repo_shape.py` ------------------------------

#: What #486 added to `repo_shape.py`. A holder that kept its own copy through
#: `update-shape.py apply --accept-local scripts/repo_shape.py` (a `both` row)
#: takes the new `siblings.py` without them.
ADDED_BY_486 = ("SHELL_BARE_POSIX", "SHELL_BARE_NT", "POWERSHELL_SINGLE_QUOTES",
                "shell_quoted", "shell_line")
#: And what #711 added: the question `shell_quoted` asks. No holder copy cut
#: before it has it, so the older library here lacks it too.
ADDED_BY_711 = ("host_shell_dialect",)
#: Every name the older library is stripped of.
OLDER_LIBRARY_LACKS = ADDED_BY_486 + ADDED_BY_711


def test_siblings_runs_beside_a_repo_shape_without_the_quoter(family,
                                                             tmp_path):
    """`siblings.py` imported `shell_line`, so a holder whose `repo_shape.py`
    predates it died with an ImportError at `make siblings`, `park` and
    `resume`, and `update-shape.py check` and the validator both read the
    holder as fine. It quotes its POSIX lines with `shlex.join` instead:
    `--help`, the misnamed-folder warning (the lines that were quoted with
    `shell_line`) and `--make park` all run beside a `repo_shape.py` that
    lacks every name #486 added, and the one #711 added."""
    holder = copied_holder(family, tmp_path / "Dana's work")
    library = holder / "scripts" / "repo_shape.py"
    text = library.read_text(encoding="utf-8")
    assert "def shell_line(" in text, "the holder's copy is not current"
    library.write_text(f"{text}\ndel {', '.join(OLDER_LIBRARY_LACKS)}\n",
                       encoding="utf-8")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam",
        "keep an older repo_shape.py", cwd=holder)
    lacks = subprocess.run(
        [sys.executable, "-c", "import repo_shape, sys; sys.exit(any("
         f"hasattr(repo_shape, name) for name in {OLDER_LIBRARY_LACKS!r}))"],
        cwd=holder / "scripts", capture_output=True, text=True, check=False)
    assert lacks.returncode == 0, lacks.stdout + lacks.stderr
    siblings = holder / "scripts" / "siblings.py"

    helped = run_script(siblings, "--help", cwd=holder)
    assert helped.returncode == 0, helped.stdout + helped.stderr
    assert helped.stdout.startswith("usage: siblings.py"), helped.stdout

    warned = run_script(siblings, "--dry-run", cwd=holder)
    assert warned.returncode == 1, warned.stdout + warned.stderr  # #543
    assert "NOTHING WAS MOVED" in warned.stderr, warned.stderr
    commands = [shlex.split(line) for line in warned.stderr.splitlines()
                if line.startswith(" " * 12) and line.strip()[:3] in
                ("mv ", "mkd")]
    staged = holder.parent.parent / f"{NAME}.holder"
    wanted = holder.parent.parent / NAME
    assert commands == [["mv", str(holder), str(staged)],
                        ["mkdir", "-p", str(wanted)],
                        ["mv", str(staged), str(wanted / NAME)]]

    # No member is cloned beside this copy, so `park` runs nowhere and says
    # so, exit 1: the report is the proof it ran at all.
    parked = run_script(siblings, "--make", "park", "--make-arg",
                        "ARGS=--dry-run", cwd=holder)
    said = parked.stdout + parked.stderr
    assert "Traceback" not in said, said
    assert "SKIPPED no clone" in said, said
    assert "`make park` did not run everywhere" in said, said


# --- setup-project.py's hand-over ---------------------------------------------

@pytest.fixture(scope="module")
def setup_tool():
    spec = importlib.util.spec_from_file_location(
        "setup_for_quoting", REPO / "setup-project.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_setup_quotes_by_the_same_rule(setup_tool):
    """`setup-project.py` runs before any checkout exists, so it carries its
    own copy of the rule, for the host it runs on. One answer, every value."""
    for value in [*ORDINARY, *AWKWARD, *LEADING_EQUALS, *EVERY_ASCII]:
        assert setup_tool.shell_word(value) == shell_quoted(value), value


@pytest.mark.parametrize("folder", FOLDERS)
def test_setup_names_the_branch_then_the_add_each_path_whole(setup_tool,
                                                            tmp_path,
                                                            folder, capsys):
    """The last of `setup-project.py`'s next commands, for a member of a
    family: the `git switch -c` that `add` needs first (it refuses the
    holder's tracking branch, #487), then the `add`, the holder one word in
    each (#486)."""
    holder = tmp_path / folder / "Orbit" / "Orbit"
    landing = setup_tool.Landing(tmp_path / folder / "Orbit", "Orbit",
                                   holder)
    setup_tool.family_next_command("Sample", "demoorg", landing)
    commands = [line.strip() for line in capsys.readouterr().out.splitlines()
                if line.strip() and not line.strip().startswith("#")]
    assert host_words(commands[0]) == ["git", "-C", str(holder), "switch",
                                       "-c", "family/add-sample"]
    assert host_words(commands[1]) == [
        setup_tool.PYTHON_CMD, "scripts/family.py", "add", "--family-root",
        str(holder), "--member", "demoorg/Sample"]
