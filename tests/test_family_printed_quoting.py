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

from conftest import REPO, git, run_script
#: The family fixture and its names, imported from the module that owns them.
from test_family import (  # noqa: F401
    FAMILY, NAME, ORG, SPARE, family, manifest, validate,
)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import PYTHON, shell_line, shell_quoted  # noqa: E402

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
    """`line` as the shell `shell_quoted` speaks on THIS host reads it."""
    return powershell_words(line) if os.name == "nt" else shlex.split(line)


# --- the quoter ---------------------------------------------------------------

#: What must survive UNQUOTED, on both platforms: a line whose whole job is
#: to be read should not carry quotes no shell needs.
ORDINARY = ["/srv/work/Atlas", "scripts/family.py", "--family-root",
            "members/IRRS", "family/add-irrs",
            "3d46ab5b9c1dcafe0123456789abcdef01234567", "origin", "-C"]

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
    `'O''Brien'` as `OBrien`. So the dialect is the platform's."""
    assert shell_quoted("O'Brien", "posix") == "'O'\\''Brien'"
    assert shell_quoted("O'Brien", "nt") == "'O''Brien'"
    assert shlex.split(shell_quoted("O'Brien", "nt")) == ["OBrien"]
    here = "nt" if os.name == "nt" else "posix"
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
             "family/add-irrs"]
    assert shlex.split(shell_line(words, "posix")) == words
    assert powershell_words(shell_line(words, "nt")) == words


@pytest.fixture(scope="module")
def doctor():
    spec = importlib.util.spec_from_file_location(
        "doctor_for_quoting", REPO / "shape-doctor.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("platform", ["posix", "nt"])
@pytest.mark.parametrize("value", ORDINARY + [
    value for value in AWKWARD if value.isascii()] + [r"C:\work,old\Atlas"])
def test_it_is_the_doctors_rule_on_any_ascii_value(doctor, platform, value):
    """ONE RULE IN TWO PLACES, held together here. `shape-doctor.py`'s
    `quote_arg` flattens its value to ASCII first, because its report is
    pure ASCII, and is otherwise this function: the same two alphabets and
    the same two escapes. On an ASCII value the two must agree."""
    assert shell_quoted(value, platform) == doctor.quote_arg(value, platform)


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
    cd = next(line for line in block if line.strip().startswith("cd "))
    assert host_words(cd) == ["cd", str(holder), "&&", "make", "siblings"]


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
                        "--dry-run")
    assert result.returncode == 0, result.stdout + result.stderr
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
