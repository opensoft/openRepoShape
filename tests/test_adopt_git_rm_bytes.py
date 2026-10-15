# SPDX-License-Identifier: Apache-2.0
"""`execute` hands `git rm` each path the split moves or drops as the bytes
the tree holds, under any locale (#527).

`_mount_the_legs` removes from the assembly, one `git rm` at a time, every
path the plan sends to a leg or drops. On main at bfed143 it passed each one
to `subprocess` as a `str`, and on POSIX `subprocess` encodes a `str`
argument with the filesystem encoding, which is the locale's codec when
Python is not in UTF-8 mode. Under `LC_ALL=C PYTHONUTF8=0` that codec is
ASCII, so a path such as `café.md` raised `UnicodeEncodeError`: `plan`
and `check` passed, both legs were made and pushed, and `execute` stopped
with `REFUSED mounting the legs. UnicodeEncodeError: ...`, exit 2.

Ruled 2026-10-12: pass git the exact bytes the tree holds, under any locale.
A path in the plan is the text `Source.tree` decoded from those bytes
(`_git_path`: UTF-8, a byte that is not UTF-8 kept as a surrogate), so
encoding it back the same way gives git the tree's own bytes: the NFC and
the NFD spelling of one name stay two paths, and a byte that is not UTF-8
is that byte again.

A C LOCALE IS A POSIX IDEA. On Windows `subprocess` hands the command line
to `CreateProcessW` as UTF-16 and no locale codec is involved, and macOS
always encodes a file name as UTF-8. Each test asks a child interpreter
what its filesystem encoding is under `LC_ALL=C PYTHONUTF8=0` and skips
where that is UTF-8, as `test_git_output_decoding.py` does: there is no
locale there to reproduce the failure in. Only names are compared, as the
bytes git records, so nothing here depends on how `Path.write_text` ends a
line.
"""

from __future__ import annotations

import codecs
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ADOPT, make_source_repo, run_script

NORTHWIND = "Northwind"
UTF8 = "utf-8"
#: The split branch `execute` pushes back to the source.
SPLIT_BRANCH = "adopt/three-repo-shape"

#: Each name and its twin are ONE word in two Unicode spellings, so two
#: different paths: the precomposed (NFC) `é` and `e` followed by the
#: combining acute accent U+0301 (NFD). One of each pair moves and the other
#: stays in the root, which only the exact bytes can tell apart.
NFC_RESUME = "résumé.md"
NFD_RESUME = "résumé.md"
NFC_CAFE = "café.md"
NFD_CAFE = "café.md"
#: Outside Latin-1 altogether.
CJK = "文書.md"
#: A directory, moved as one entry, beside a file whose name starts with it.
UMLAUT_DIR = "Übersicht"
UMLAUT_FILE = "Übersicht.md"
NAIVE = "naïve.md"
#: The byte 0xE9 where UTF-8 has none, as `Source.tree` keeps it: the
#: surrogate U+DC00 plus the byte. A `drop` entry may hold one.
NOT_UTF8 = "caf\udce9.txt"
#: The source's front door, in every tree here.
README = "README.md"

#: What the C locale is: `PYTHONUTF8=0`, because the C locale turns Python's
#: UTF-8 mode on by itself, and so does 3.15 everywhere.
C_LOCALE = {"LC_ALL": "C", "PYTHONUTF8": "0"}
#: The keys `C_LOCALE` must not meet in a child's environment.
LOCALE_KEYS = ("LC_", "LANG", "PYTHONUTF8", "PYTHONIOENCODING",
               "PYTHONCOERCE")

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")


def tree_bytes(path: str) -> bytes:
    """`path` as git records it: the inverse of `adopt-project.py`'s
    `_git_path`."""
    return path.encode(UTF8, "surrogateescape")


def listed(repository: Path, *command: str) -> set[bytes]:
    """The names `git <command>` lists in `repository`, NUL-separated, as
    the bytes git records: read as text, the byte 0xE9 would not decode."""
    raw = subprocess.run(["git", *command], cwd=str(repository),
                         capture_output=True, check=True).stdout
    return {name for name in raw.split(b"\0") if name}


def c_locale_or_skip() -> dict:
    """`C_LOCALE` over this environment, once a child started in it has said
    that its filesystem encoding is not UTF-8, and once this process can
    spell every name the tests create. A platform without such a locale
    (Windows, macOS) skips: there is no failure there to reproduce."""
    if os.name == "nt":
        pytest.skip("a C locale is a POSIX idea: Windows hands a command line "
                    "to CreateProcessW as UTF-16")
    for name in (NFC_RESUME, NFD_RESUME, CJK, UMLAUT_DIR, NOT_UTF8):
        try:
            os.fsencode(name)
        except UnicodeEncodeError:
            pytest.skip(f"this process cannot spell {name!r} as a file name")
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(LOCALE_KEYS)}
    env.update(C_LOCALE)
    asked = subprocess.run(
        [sys.executable, "-c",
         "import codecs, sys; "
         "print(codecs.lookup(sys.getfilesystemencoding()).name)"],
        capture_output=True, env=env, stdin=subprocess.DEVNULL, check=True)
    encoding = asked.stdout.decode("ascii").strip()
    if encoding == codecs.lookup(UTF8).name:
        pytest.skip("this platform encodes a file name as UTF-8 under "
                    "LC_ALL=C PYTHONUTF8=0, so there is no locale to "
                    "reproduce the failure in")
    return env


# --- `_mount_the_legs`, in a child under the C locale -----------------------

#: The child: `_mount_the_legs` of the assembly in argv[2], whose legs are
#: in the work directory in argv[3], for the plan paths in argv[4]. Every
#: argument is ASCII: the two directories travel as the hex of their bytes,
#: and the paths as JSON, which spells each character and each surrogate as
#: an escape. It prints one line of ASCII JSON: what `_mount_the_legs`
#: raised, if anything, and for a `CommandFailed` the block `execute` prints
#: of it after both legs exist (`loudly`).
MOUNT_IN_THE_C_LOCALE = r"""
import importlib.util, json, os, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location(
    "adopt_in_the_c_locale", os.fsdecode(bytes.fromhex(sys.argv[1])))
adopter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adopter)
assembly = Path(os.fsdecode(bytes.fromhex(sys.argv[2])))
work = Path(os.fsdecode(bytes.fromhex(sys.argv[3])))
names = {"assembly": "Northwind", "spec": "Northwind-spec",
         "code": "Northwind-code"}
urls = {role: str(work / names[role]) for role in ("spec", "code")}
answer = {}
try:
    adopter._mount_the_legs(assembly, work, names, urls,
                            json.loads(sys.argv[4]), "spec", "code")
except Exception as exc:
    answer["raised"] = type(exc).__name__ + ": " + str(exc)
    if isinstance(exc, adopter.CommandFailed):
        answer["loudly"] = exc.loudly("mounting the legs")
print(json.dumps(answer))
"""

#: The paths the plan moves or drops, by leg, as a plan spells them.
MOVED = {"spec": [NFC_RESUME, NFD_CAFE, UMLAUT_DIR + "/"], "code": [CJK],
         "drop": [NAIVE, NOT_UTF8]}
#: The paths the plan keeps in the root: each moved name's twin, and a file
#: whose name starts with the moved directory's.
KEPT = [NFD_RESUME, NFC_CAFE, UMLAUT_FILE, README]


def mounted_in_the_c_locale(tmp_path: Path, files: list,
                            moved: dict) -> tuple[Path, dict]:
    """`(assembly, answer)`: an assembly holding `files`, beside its two
    legs in a work directory, and what the child said of `_mount_the_legs`
    for the plan paths `moved`, run under the C locale."""
    env = c_locale_or_skip()
    work = tmp_path / "work"
    assembly = make_source_repo(work / NORTHWIND,
                                {name: "x\n" for name in files}, edits=())
    for role in ("spec", "code"):
        make_source_repo(work / f"{NORTHWIND}-{role}", {"leg.md": "x\n"},
                         edits=())
    child = subprocess.run(
        [sys.executable, "-c", MOUNT_IN_THE_C_LOCALE,
         os.fsencode(ADOPT).hex(), os.fsencode(assembly).hex(),
         os.fsencode(work).hex(), json.dumps(moved)],
        capture_output=True, env=env, stdin=subprocess.DEVNULL, check=False)
    stderr = child.stderr.decode(UTF8, "replace")
    assert child.returncode == 0, f"the child died:\n{stderr}"
    return assembly, json.loads(child.stdout.decode("ascii"))


def test_the_mount_hands_git_rm_each_path_as_the_bytes_the_tree_holds(
        tmp_path):
    """On bfed143 the child raised `UnicodeEncodeError` at the first `git
    rm` of a name outside ASCII. Now every moved and dropped path is gone
    from the assembly's index, byte for byte, and each twin kept in the
    root is still there: no other path was removed."""
    files = [NFC_RESUME, NFD_CAFE, CJK, NAIVE, NOT_UTF8,
             f"{UMLAUT_DIR}/a.md", f"{UMLAUT_DIR}/b.md", *KEPT]
    assembly, answer = mounted_in_the_c_locale(tmp_path, files, MOVED)
    assert "raised" not in answer, answer
    assert listed(assembly, "ls-files", "-z") == {
        tree_bytes(name) for name in [*KEPT, ".gitmodules", "spec", "code"]}


def test_a_path_git_refuses_is_refused_as_the_command_reads(tmp_path):
    """`_git_rm`'s failure path (r527's review). A `git rm` git refuses
    raises `CommandFailed` as `run` raised it: naming the command as the
    person reads it (the path as text, not the bytes git was handed) and the
    directory it ran in, and carrying git's own words, which `execute`
    prints after both legs exist.
    On bfed143 the child raised `UnicodeEncodeError` before git ran. Naming
    the bytes command raised `TypeError`, not one of `LATE_FAILURES`, so the
    run would end in a traceback after both legs are pushed; and a refusal
    left unraised went on to mount the legs as if the path were gone."""
    missing = "missing-" + NFC_CAFE
    _, answer = mounted_in_the_c_locale(
        tmp_path, [README], {"spec": [missing], "code": [], "drop": []})
    command = f"git --literal-pathspecs rm -r -q -- {missing}"
    assert answer.get("raised") == f"CommandFailed: {command}", answer
    told = answer["loudly"].splitlines()
    assert told[:2] == ["REFUSED mounting the legs. THE EXACT COMMAND WAS:",
                        f"    {command}"]
    # Only the head of the line: the child spells the directory under ASCII,
    # so what follows need not be this process's spelling of a temporary path.
    assert told[2].startswith("    (in "), told
    assert f"fatal: pathspec '{missing}' did not match any files" in told


# --- the whole adoption, from the command line ------------------------------

def spelled_in_the_plan(adopter, path: str) -> str:
    """`path` as `plan` writes an entry's `path:`."""
    return adopter.y(path)


def answered(plan: Path, adopter, legs: dict) -> None:
    """Give each entry `legs` names that leg, whatever `plan` answered, as a
    person editing the plan would. Bytes in, bytes out: the plan stays LF."""
    text = plan.read_bytes().decode(UTF8)
    for path, leg in legs.items():
        spelled = spelled_in_the_plan(adopter, path)
        entry = re.search(rf"  - path: {re.escape(spelled)}\n    leg: \S+\n",
                          text)
        assert entry, f"no entry {path!r} in the plan"
        text = text.replace(entry[0], f"  - path: {spelled}\n    leg: {leg}\n"
                            "    resolution: \"answered by the test\"\n", 1)
    plan.write_bytes(text.encode(UTF8))


def names_at(repository: Path, rev: str) -> set[bytes]:
    """Every file name at `rev`, as the bytes git records."""
    return listed(repository, "ls-tree", "-r", "-z", "--name-only", rev)


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_git_rm_bytes", ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: `(source tree, answers, the locale `plan` runs in)`. The first is the
#: issue's run: `plan`, `check` and `execute` all under the C locale. The
#: second moves a DIRECTORY whose name is not ASCII; `plan` cannot plan one
#: under that locale (its `git grep` for the follow-ups hands git the name
#: as text too), so the plan is written in UTF-8 mode, as on another
#: machine, and `check` and `execute` run under the C locale.
ADOPTIONS = {
    "every-command-under-the-c-locale": (
        [NFC_RESUME, NFD_RESUME, NFC_CAFE, NFD_CAFE, CJK, NAIVE, NOT_UTF8],
        {NFC_RESUME: "spec", NFD_CAFE: "spec", CJK: "code", NAIVE: "drop",
         NOT_UTF8: "drop", NFD_RESUME: "root", NFC_CAFE: "root"},
        C_LOCALE),
    "a-directory-planned-in-utf-8-mode": (
        [f"{UMLAUT_DIR}/a.md", f"{UMLAUT_DIR}/b.md", UMLAUT_FILE],
        {UMLAUT_DIR + "/": "spec", UMLAUT_FILE: "root"},
        {"LC_ALL": "C", "PYTHONUTF8": "1"}),
}


@needs_filter_repo
@pytest.mark.parametrize("names, legs, planned_in", ADOPTIONS.values(),
                         ids=ADOPTIONS.keys())
def test_a_source_with_names_outside_ascii_adopts_under_a_c_locale(
        adopter, tmp_path, names, legs, planned_in):
    """THE ISSUE'S RUN. On bfed143 `check` said `plan ok` and `execute`
    exited 2 with `REFUSED mounting the legs. UnicodeEncodeError`, after
    both legs were pushed. Now it says `adoption verified`, every moved name
    is in its leg as the bytes the source holds, and every name kept in the
    root is in the split, beside its twin's absence."""
    c_locale_or_skip()
    tree = {README: "# Northwind\n", "docs/guide.md": "guide\n",
            "src/app.py": "VALUE = 1\n", **{name: "x\n" for name in names}}
    source = make_source_repo(tmp_path / NORTHWIND, tree, edits=())
    plan = tmp_path / "adoption-plan.yaml"
    written = run_script(ADOPT, "plan", "--source", str(source), "--project",
                         NORTHWIND, "--org", "testorg", "--elected-by",
                         "Test Human", "--elected-on", "2026-09-02", "--out",
                         str(plan), env=planned_in)
    assert written.returncode == 0, written.stderr + written.stdout
    answered(plan, adopter, legs)
    checked = run_script(ADOPT, "check", "--plan", str(plan), env=C_LOCALE)
    assert checked.returncode == 0, checked.stderr + checked.stdout

    remotes = tmp_path / "remotes"
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(remotes), "--work-dir",
                        str(tmp_path / "work"), env=C_LOCALE)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "adoption verified" in result.stdout

    def given(leg: str) -> set[bytes]:
        """The files the test's answers send to `leg`, as bytes."""
        return {tree_bytes(path) for path, answer in legs.items()
                if answer == leg and not path.endswith("/")}

    under_the_dir = {tree_bytes(name) for name in names
                     if name.startswith(UMLAUT_DIR + "/")}
    spec = names_at(remotes / f"{NORTHWIND}-spec.git", "main")
    assert spec == {b"docs/guide.md"} | given("spec") | under_the_dir
    code = names_at(remotes / f"{NORTHWIND}-code.git", "main")
    assert code == {b"src/app.py"} | given("code")
    root = names_at(source, SPLIT_BRANCH)
    assert given("root") <= root
    gone = given("spec") | given("code") | given("drop") | under_the_dir
    assert not gone & root
