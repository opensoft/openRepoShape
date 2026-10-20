# SPDX-License-Identifier: Apache-2.0
"""A value `execute` writes into a file is asked, before anything exists,
whether a file can hold it (#255).

Since #247 the plan writer keeps a lone surrogate -- a byte that is not
UTF-8, as Python decodes argv and paths -- as `\\udce9`, and the reader gives
it back. So `plan --elected-by b'Jos\\xe9'`, `--reference b'ref-\\xe9'`, or a
`--source` under a directory `caf\\xe9` with local remotes (the clone URL
carries it) passed `plan` and `check`, and `execute` created and pushed both
leg remotes before `write_lf` raised `UnicodeEncodeError`, exit 1. Before
#247, `plan` raised on the same input and nothing was created. A hand-edited
`\\ud800` in `elected_by`, `elected_on`, `reference`, `visibility`, a pin or a
follow-up ended the same way; a NUL or a line break there went on into the
manifest; and a hand-edited `\\x00` or surrogate in `local_path` ended
`check` and `execute` in a traceback where main had refused it.

Now `plan` refuses such a flag as `adopt-unwritable-value` and writes no
plan; `check` reports such a plan value as `plan-unwritable-value`, and
`execute` refuses the same finding before any leg exists; `execute` refuses
a local clone URL no file can hold as `adopt-unwritable-value`; and a
`local_path` that is not text is `source-unresolvable`. Every run is read
for a traceback, and asked afterwards whether a leg remote exists.

THE QUESTION IS `one_printable_line` LESS `Cf`, EXCEPT THE NINE BIDI
CONTROLS. A Persian name joins its parts with U+200C ZERO WIDTH NON-JOINER,
which UTF-8 holds and the reader reads back, and `execute` adopted it before
#247 and since: it still adopts, as `José` and a source directory `café` do.
The embedding, override and isolate controls U+202A..U+202E and
U+2066..U+2069 are refused: written raw into `README.md`, one shows the rest
of its line in another order than it is written.

Every subprocess runs under `PYTHONIOENCODING=utf-8:strict`, so that a value
printed raw raises on every platform as it does on a strict terminal, and is
answered in BYTES: a value that is not UTF-8 is not text to decode. Every
invisible character in this file is spelled as an escape: a reader cannot
see one typed raw, and a raw bidi control reorders the line it is on.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

from conftest import (ADOPT, REPO, WINDOWS_SKIP, blank_unnamed_pin_sources,
                      make_source_repo, resolve,
                      skip_where_a_name_cannot_be_not_utf_8,
                      skip_where_the_environment_cannot_carry)

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402
from repo_shape import double_quoted, load_yaml  # noqa: E402

PLAN_FILE = "adoption-plan.yaml"
REMOTES = "remotes"
WORK = "work"
PROJECT = "Northwind"
#: Where `execute` pushes the split commit: back into the source, under
#: `--local-remote-dir`.
SPLIT_BRANCH = "adopt/three-repo-shape"
#: The entries of `SYNTHETIC_TREE` that `plan` asks about, answered.
ANSWERS = (("examples/", "spec"), (".claude/", "root"),
           ("release.yaml", "root"))
#: A stdout that raises on what it cannot encode, as a strict terminal does.
STRICT = {"PYTHONIOENCODING": "utf-8:strict"}
#: What the git that `execute` runs needs, as `conftest.run_script` sets it.
IDENTITY = {"GIT_AUTHOR_NAME": "openRepoShape tests",
            "GIT_AUTHOR_EMAIL": "tests@openreposhape.invalid",
            "GIT_COMMITTER_NAME": "openRepoShape tests",
            "GIT_COMMITTER_EMAIL": "tests@openreposhape.invalid"}

TRACEBACK = b"Traceback"
VERIFIED = b"adoption verified"
PLAN_OK = b"\nplan ok\n"
ADOPT_REFUSED = b"REFUSED adopt-unwritable-value: "
PLAN_REFUSED = b"REFUSED plan-unwritable-value: "
FINDING = b"FINDING plan-unwritable-value: "
#: How `check` begins its one finding about a name-only `pins:` item (#901).
PIN_UNRECORDED = b"FINDING plan-pin-unrecorded: "
SOURCE_REFUSED = b"REFUSED source-unresolvable: "

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")


def adopted(*args: str,
            extra: dict | None = None) -> subprocess.CompletedProcess:
    """`adopt-project.py <args>` on a strict stdout, with `extra` in its
    environment, answered in bytes, each stream with LF line ends whatever
    the platform printed."""
    env = blank_unnamed_pin_sources(
        {**IDENTITY, **os.environ, "LANES_LANE": "", **(extra or {}),
         **STRICT}, STRICT)
    done = subprocess.run([sys.executable, str(ADOPT), *args],
                          capture_output=True, env=env,
                          stdin=subprocess.DEVNULL, check=False)
    done.stdout = done.stdout.replace(b"\r\n", b"\n")
    done.stderr = done.stderr.replace(b"\r\n", b"\n")
    return done


def planned(base: Path, source: Path,
            *flags: str) -> subprocess.CompletedProcess:
    """`plan`, as `conftest.write_plan` runs it, with `flags` after it: a
    flag given twice is read as its last value."""
    return adopted("plan", "--source", str(source), "--project", PROJECT,
                   "--org", "testorg", "--elected-by", "Test Human",
                   "--elected-on", "2026-09-02", "--out",
                   str(base / PLAN_FILE), "--work-dir", str(base / WORK),
                   *flags)


def checked(base: Path,
            extra: dict | None = None) -> subprocess.CompletedProcess:
    return adopted("check", "--plan", str(base / PLAN_FILE), "--work-dir",
                   str(base / WORK), extra=extra)


def executed(base: Path,
             extra: dict | None = None) -> subprocess.CompletedProcess:
    return adopted("execute", "--plan", str(base / PLAN_FILE), "--yes",
                   "--local-remote-dir", str(base / REMOTES), "--work-dir",
                   str(base / WORK), extra=extra)


def answer(base: Path) -> None:
    for path, leg in ANSWERS:
        resolve(base / PLAN_FILE, path, leg)


def plan_check_execute(base: Path, source: Path,
                       *flags: str) -> dict[str, subprocess.CompletedProcess]:
    """`plan` with `flags`, then, if it wrote a plan, that plan answered,
    `check`, and `execute` with local remotes: each run there was."""
    runs = {"plan": planned(base, source, *flags)}
    if runs["plan"].returncode == 0:
        answer(base)
        runs["check"] = checked(base)
        runs["execute"] = executed(base)
    return runs


def said(run: subprocess.CompletedProcess) -> str:
    """A run's output, readable in an assertion message."""
    return (run.stdout + run.stderr).decode("utf-8", "backslashreplace")


def assert_no_traceback(runs: dict) -> None:
    for name, run in runs.items():
        assert TRACEBACK not in run.stderr, f"{name}:\n{said(run)}"


def assert_no_traceback_and_no_leg(base: Path, runs: dict) -> None:
    """The issue's two symptoms, asked first so that a failure names them:
    a traceback in any run, and a leg remote left behind."""
    assert_no_traceback(runs)
    remotes = base / REMOTES
    left = (sorted(path.name for path in remotes.iterdir())
            if remotes.exists() else [])
    assert not left, f"leg remotes exist: {left}"


def in_the_split(source: Path, path: str) -> str:
    """`path` as the split commit `execute` pushed into `source` holds it."""
    return subprocess.run(["git", "show", f"{SPLIT_BRANCH}:{path}"],
                          cwd=str(source), capture_output=True,
                          check=True).stdout.decode("utf-8")


# --- `plan`: a flag no file can hold -----------------------------------------

#: `(flag, value)`, as `plan`'s argv carries it. `\udce9` is how Python keeps
#: the byte 0xE9 of a command line that is not UTF-8, which is what a
#: terminal or a script whose encoding is not the locale's sends; the next
#: two are text a file holds, but on no one line; the last two hold a bidi
#: override or isolate, which a file holds and a reader is shown reordered.
FLAGS = [
    ("--elected-by", "Jos\udce9"),
    ("--reference", "ref-\udce9"),
    ("--elected-by", "Jos\u2028e"),
    ("--reference", "openxFactory\tdocs/project-repo-schema.md"),
    ("--elected-by", "\u202eevil"),
    ("--reference", "ref \u2066x\u2069 y"),
]


@pytest.mark.parametrize("flag, value", FLAGS,
                         ids=[f"{flag}={ascii(value)}"
                              for flag, value in FLAGS])
def test_plan_refuses_a_flag_no_file_can_hold(tmp_path, flag, value):
    """The issue's first two rows. On main `plan` exited 0, `check` said
    `plan ok`, and `execute` raised in `write_lf` after both legs were
    pushed (a surrogate), or adopted with the line break, the tab or the
    bidi control in the manifest and the README. Now `plan` refuses, and
    writes no plan. Skipped where this system's file name encoding cannot
    spell `value` (U+2028, U+202E or U+2066 in ASCII under `LC_ALL=C`),
    asked first: `subprocess` cannot put it on `plan`'s command line there,
    and raised `UnicodeEncodeError` in the test, not in the tool."""
    skip_where_the_environment_cannot_carry(value)
    source = make_source_repo(tmp_path / "Thing")
    runs = plan_check_execute(tmp_path, source, flag, value)
    assert_no_traceback_and_no_leg(tmp_path, runs)
    refused = runs["plan"]
    assert refused.returncode == 2, said(refused)
    assert ADOPT_REFUSED + f"{flag} is {value!r}, which ".encode() \
        in refused.stderr, said(refused)
    assert b"no plan was written" in refused.stderr
    assert not (tmp_path / PLAN_FILE).exists()


def test_plan_names_the_elector_it_took_from_git_config(tmp_path):
    """With no --elected-by, `plan` records `git config user.name`. A TAB
    there is refused like a TAB passed with the flag, and named by where
    it came from, as #181 names a value `plan` filled in: not as a flag
    the person never passed."""
    config = tmp_path / "gitconfig"
    config.write_bytes(b'[user]\n\tname = "Jo\\tSmith"\n')
    extra = {"GIT_CONFIG_GLOBAL": str(config)}
    read = subprocess.run(["git", "config", "user.name"], cwd=str(REPO),
                          capture_output=True, env={**os.environ, **extra},
                          check=False)
    if read.stdout.rstrip(b"\r\n") != b"Jo\tSmith":
        pytest.skip("`git config user.name` here is not read from "
                    f"GIT_CONFIG_GLOBAL: {read.stdout!r}")
    source = make_source_repo(tmp_path / "Thing")
    refused = adopted("plan", "--source", str(source), "--project", PROJECT,
                      "--org", "testorg", "--elected-on", "2026-09-02",
                      "--out", str(tmp_path / PLAN_FILE), "--work-dir",
                      str(tmp_path / WORK), extra=extra)
    assert_no_traceback({"plan": refused})
    assert refused.returncode == 2, said(refused)
    assert ADOPT_REFUSED + b"--elected-by (not given, so `git config " \
        b"user.name`) is 'Jo\\tSmith', which " in refused.stderr, said(refused)
    assert not (tmp_path / PLAN_FILE).exists()


# --- `execute`: a local clone URL no file can hold ---------------------------

#: What the clone-URL refusal tells the person to do. `refused_then_moved`
#: does it, as it is worded.
MOVE_REMEDIATION = (
    b"Remediation: nothing was created. Rename or move the source repository "
    b"so that its path is one line of UTF-8 text with no control character "
    b"in it, then run `plan --source <its new path>`, `check` and `execute` "
    b"again")


def refused_then_moved(base: Path, parent: Path, reason: bytes) -> None:
    """A source in the directory `parent`: `plan` and `check` pass it, as
    #247 made them, and `execute` refuses its path as the assembly root's
    clone URL, giving `reason`, before any leg exists. Then the remediation
    the refusal gives, followed as it is worded -- `parent` renamed, then
    `plan --source <its new path>`, `check` and `execute` run again -- ends
    `adoption verified`.

    The source repository is made under `parent` with no guard: the caller
    has asked whether this system can carry the name, and git works under
    any directory a system carries, so a failure of git there (a disk that
    filled after the `mkdir`) is the test's own and is raised, for a name
    that is not UTF-8 (#853) as for one that is valid text (#834)."""
    source = make_source_repo(parent / "Thing")
    runs = plan_check_execute(base, source)
    assert_no_traceback_and_no_leg(base, runs)
    assert runs["plan"].returncode == 0, said(runs["plan"])
    assert runs["check"].returncode == 0, said(runs["check"])
    assert PLAN_OK in runs["check"].stdout, said(runs["check"])
    refused = runs["execute"]
    assert refused.returncode == 2, said(refused)
    assert ADOPT_REFUSED + b"under --local-remote-dir the assembly root's " \
        b"clone URL is the source's own path, " \
        + repr(str(source.resolve())).encode() + b", which " \
        in refused.stderr, said(refused)
    assert reason in refused.stderr, said(refused)
    assert MOVE_REMEDIATION in refused.stderr, said(refused)

    moved = parent.rename(parent.with_name("cafe")) / "Thing"
    again = base / "again"
    again.mkdir()
    runs = plan_check_execute(again, moved)
    assert_no_traceback(runs)
    assert runs["check"].returncode == 0, said(runs["check"])
    done = runs["execute"]
    assert done.returncode == 0, said(done)
    assert VERIFIED in done.stdout, said(done)


@needs_filter_repo
def test_execute_refuses_a_local_source_directory_that_is_not_utf8(tmp_path):
    """The issue's third row. Under `--local-remote-dir` the assembly root's
    clone URL is the source's own path, which its `README.md` names: `plan`
    and `check` pass such a directory, and `execute` refuses it before any
    leg exists, where it raised after both were pushed. Its remediation
    once said to clone the source to a UTF-8 path and pass that with
    --source, which ended in a traceback: the clone's `origin` is the old
    path, which `_remote_repository` reads as UTF-8. Skipped where no
    directory can be named with the byte 0xE9 (Windows, macOS's APFS); a
    failure of git under it fails the test (#853)."""
    skip_where_a_name_cannot_be_not_utf_8(tmp_path)
    parent = Path(os.fsdecode(os.path.join(os.fsencode(tmp_path),
                                           b"caf\xe9")))
    parent.mkdir()
    refused_then_moved(tmp_path, parent, b"a byte that is not UTF-8")


@needs_filter_repo
def test_execute_refuses_a_local_source_directory_holding_a_bidi_control(
        tmp_path):
    """A source under a directory whose name begins with U+202E RIGHT-TO-LEFT
    OVERRIDE: on main `execute` adopted it, and the shape's README showed
    the rest of its `git clone` line reversed. Now it is refused as the
    byte is, and moving the source adopts. Skipped where this system's file
    name encoding cannot spell U+202E (ASCII under `LC_ALL=C`), which is
    asked before the `mkdir`, where it raised `UnicodeEncodeError` (#854).
    Nothing else is guarded: U+202E is valid text, which a POSIX disk, NTFS
    and APFS hold and git works under (reasoned, not run, on the last two),
    so an error of the disk when the directory is made, and a failure of git
    when the source is, are the test's own and are raised, not skipped
    (#834)."""
    parent = tmp_path / "\u202ecaf"
    skip_where_the_environment_cannot_carry(parent.name)
    parent.mkdir()
    refused_then_moved(tmp_path, parent, b"a bidirectional control")


# --- `check` and `execute`: a plan value edited by hand ----------------------

@pytest.fixture(scope="module")
def answered(tmp_path_factory) -> tuple[Path, str]:
    """A source and the plan `plan` wrote for it, answered and `plan ok`:
    the text each test edits a line of, in a copy of its own."""
    base = tmp_path_factory.mktemp("answered")
    source = make_source_repo(base / "Thing")
    written = planned(base, source)
    assert written.returncode == 0, said(written)
    answer(base)
    ok = checked(base)
    assert ok.returncode == 0, said(ok)
    return source, (base / PLAN_FILE).read_text(encoding="utf-8")


def with_line(text: str, line: str) -> str:
    """`text` with the one line holding `line`'s key -- `elected_by`, or an
    indented `  spec_path` -- replaced by `line`."""
    key = line.split(": ", 1)[0]
    text, done = re.subn(rf"^{re.escape(key)}: .*$", lambda _: line, text,
                         count=1, flags=re.M)
    assert done == 1, line
    return text


def edited_plan(base: Path, answered: tuple[Path, str], line: str,
                follow_up: bool = False) -> None:
    """The answered plan, its `local_path:` a copy of the source made for
    this test alone (on main `execute` pushes its split branch into the
    source), with `line` in place of the line of its key -- or, as
    `follow_up`, added as the first `follow_ups:` item -- written LF as
    `plan` writes it."""
    source, text = answered
    copy = base / "Thing"
    shutil.copytree(source, copy, symlinks=True)
    text = with_line(text, f"  local_path: {double_quoted(str(copy))}")
    if follow_up:
        text, done = re.subn(r"^follow_ups:$",
                             lambda _: f"follow_ups:\n{line}", text, count=1,
                             flags=re.M)
        assert done == 1
    else:
        text = with_line(text, line)
    with (base / PLAN_FILE).open("w", encoding="utf-8",
                                 newline="\n") as handle:
        handle.write(text)


#: `(id, key, value, what the FINDING calls it)`. Each value is spelled in
#: the plan by `double_quoted`, as the plan writer escapes it and as a person
#: editing the plan would. A name-only `pins:` item is #273's to name, as
#: `plan-pin-unrecorded`, and since #901 that is its one finding: #255 asks
#: only the pins `execute` writes (`PIN_UNRECORDED`).
EDITS = [
    ("elected_by-surrogate", "elected_by", "T\ud800", "elected_by"),
    ("elected_by-byte", "elected_by", "T\udce9", "elected_by"),
    ("elected_by-nul", "elected_by", "T\x00", "elected_by"),
    ("elected_by-cr", "elected_by", "T\rX", "elected_by"),
    ("elected_by-nel", "elected_by", "T\x85X", "elected_by"),
    ("elected_by-u2028", "elected_by", "T\u2028X", "elected_by"),
    ("elected_by-tab", "elected_by", "T\tX", "elected_by"),
    ("elected_on-surrogate", "elected_on", "2026-09-02\ud800", "elected_on"),
    ("reference-surrogate", "reference", "x\ud800", "reference"),
    ("reference-nul", "reference", "x\x00", "reference"),
    ("visibility-surrogate", "visibility", "priv\ud800ate", "visibility"),
    ("pins-surrogate", "pins", "openX\ud800", "`pins:` entry 1,"),
    ("follow_ups-surrogate", "follow_ups", "fix x\ud800",
     "a `follow_ups:` item"),
    ("elected_by-override", "elected_by", "\u202eevil", "elected_by"),
    ("visibility-override", "visibility", "private\u202e", "visibility"),
    ("follow_ups-isolate", "follow_ups", "fix \u2066x",
     "a `follow_ups:` item"),
]


def edit(base: Path, answered: tuple[Path, str], key: str,
         value: str) -> None:
    """The answered plan, with `key` given `value`."""
    if key == "follow_ups":
        edited_plan(base, answered, f"  - {double_quoted(value)}",
                    follow_up=True)
    elif key == "pins":
        edited_plan(base, answered, f"pins: [{double_quoted(value)}]")
    else:
        edited_plan(base, answered, f"{key}: {double_quoted(value)}")


@needs_filter_repo
@pytest.mark.parametrize("key, value, what", [row[1:] for row in EDITS],
                         ids=[row[0] for row in EDITS])
def test_check_finds_and_execute_refuses_a_hand_edited_value(
        tmp_path, answered, key, value, what):
    """On main `check` said `plan ok` (or raised printing the value), and
    `execute` raised in `write_lf` after both legs were pushed, or adopted
    with the NUL, the line break or the bidi control in the manifest or the
    split commit's message. Now `check` has a FINDING, and `execute` refuses
    it through `_refuse_what_check_finds`, in `check`'s words, before any
    leg exists."""
    edit(tmp_path, answered, key, value)
    runs = {"check": checked(tmp_path), "execute": executed(tmp_path)}
    assert_no_traceback_and_no_leg(tmp_path, runs)
    found, refused = runs["check"], runs["execute"]
    finding = FINDING + f"{what} is {value!r}, which `execute` writes " \
        "into ".encode()
    if key == "pins":
        finding = PIN_UNRECORDED + f"{what} {value!r}, is a name ".encode()
        assert FINDING not in found.stderr, said(found)
    assert found.returncode == 1, said(found)
    assert finding in found.stderr, said(found)
    assert refused.returncode == 2, said(refused)
    # A name-only `pins:` item is `plan-pin-unrecorded` first (#273).
    headline = (b"REFUSED plan-pin-unrecorded: " if key == "pins"
                else PLAN_REFUSED)
    assert headline in refused.stderr, said(refused)
    assert b"\n  " + finding in refused.stderr, said(refused)
    assert b"no leg repository was created" in refused.stderr


def test_plan_and_check_say_the_same_sentence(tmp_path, answered):
    """`plan`'s refusal of `--elected-by` and `check`'s finding about
    `elected_by` are one sentence about one value, each naming it as the
    person has it in front of them."""
    value = "Jos\udce9"
    flagged, by_hand = tmp_path / "flag", tmp_path / "edit"
    flagged.mkdir()
    by_hand.mkdir()
    refused = planned(flagged, answered[0], "--elected-by", value)
    edit(by_hand, answered, "elected_by", value)
    found = checked(by_hand)
    assert_no_traceback({"plan": refused, "check": found})
    assert refused.returncode == 2, said(refused)
    assert found.returncode == 1, said(found)
    assert ADOPT_REFUSED in refused.stderr, said(refused)
    assert FINDING in found.stderr, said(found)
    detail = refused.stderr.split(ADOPT_REFUSED, 1)[1].split(b"\n", 1)[0]
    finding = found.stderr.split(FINDING, 1)[1].split(b"\n", 1)[0]
    assert detail.startswith(b"--elected-by is "), said(refused)
    assert finding.startswith(b"elected_by is "), said(found)
    assert detail[len(b"--elected-by"):] == finding[len(b"elected_by"):] + b"."


# --- a value `check` prints, edited by hand ----------------------------------

#: `(id, line key, value, how `check` shows it, check's exit, what it says,
#: execute's refusal)`: a value `check` printed raw under `WHAT WILL
#: HAPPEN`, which raised on a strict stdout before any finding about it was
#: printed. It is shown as a name is (`_shown`), a byte that is not UTF-8 as
#: `\udce9`, as the plan's own `path:` spells it (#329). A leg path is
#: `plan-bad-leg-path`; the adopt branch is `unsafe-value` to `execute`, as
#: on main before #247, and since #520 (L2-1 on #457) a finding of `check`'s
#: too, in `execute`'s words, where it passed `check` before.
PRINTED = [
    ("spec_path-surrogate", "  spec_path", "sp\ud800ec", rb"`sp\ud800ec`/",
     1, b"FINDING plan-bad-leg-path: legs.spec_path is ",
     b"plan-bad-leg-path"),
    ("code_path-byte", "  code_path", "co\udce9de", rb"`co\udce9de`/", 1,
     b"FINDING plan-bad-leg-path: legs.code_path is ", b"plan-bad-leg-path"),
    ("adopt_branch-surrogate", "adopt_branch", "adopt/x\ud800",
     rb"`adopt/x\ud800` of", 1, b"FINDING unsafe-value: adopt_branch is ",
     b"unsafe-value"),
]


@needs_filter_repo
@pytest.mark.parametrize("key, value, shown, exit_code, says, code",
                         [row[1:] for row in PRINTED],
                         ids=[row[0] for row in PRINTED])
def test_check_prints_a_hand_edited_value_spelled(tmp_path, answered, key,
                                                  value, shown, exit_code,
                                                  says, code):
    edited_plan(tmp_path, answered, f"{key}: {double_quoted(value)}")
    runs = {"check": checked(tmp_path), "execute": executed(tmp_path)}
    assert_no_traceback_and_no_leg(tmp_path, runs)
    found, refused = runs["check"], runs["execute"]
    assert found.returncode == exit_code, said(found)
    assert says in found.stdout + found.stderr, said(found)
    assert shown in found.stdout, said(found)
    assert refused.returncode == 2, said(refused)
    assert b"REFUSED " + code + b": " in refused.stderr, said(refused)


# --- `local_path`, edited by hand --------------------------------------------

#: How each `local_path` is made from the source's own path: the path that
#: exists with a NUL or a surrogate after it, and paths that do not exist.
LOCAL_PATHS = {
    "nul": lambda source: f"{source}\x00",
    "surrogate": lambda source: f"{source}\ud800",
    "missing-nul": lambda _: "/nonexistent\x00/Thing",
    "missing-byte": lambda _: "/nonexistent/caf\udce9",
}


#: How `check` and `execute` refuse a plan's `local_path:` that names
#: nothing that exists and that `plan` did not clone (#652): by its key. They
#: said `source-unresolvable`, naming a `--source` nobody passed.
LOCAL_PATH_GONE = b"REFUSED plan-source-gone: the plan's `source.local_path`, "
NOT_PLANS_CLONE = (b"names nothing that exists, and the plan does not record "
                   b"it as a clone `plan` made")


def assert_refused_as_gone(runs: dict) -> None:
    """Each run refused the plan's `local_path:` by its key, exit 2."""
    for name, run in runs.items():
        assert run.returncode == 2, f"{name}:\n{said(run)}"
        assert run.stderr.startswith(LOCAL_PATH_GONE), f"{name}:\n{said(run)}"
        assert NOT_PLANS_CLONE in run.stderr, f"{name}:\n{said(run)}"


@pytest.mark.parametrize("make", list(LOCAL_PATHS.values()),
                         ids=list(LOCAL_PATHS))
def test_a_local_path_that_is_not_text_is_refused_as_gone(tmp_path, answered,
                                                          make):
    """On main `check` and `execute` ended in a traceback: `print` raised on
    the surrogate and `subprocess` on the NUL, as the value was about to be
    handed to `gh repo clone` as an `org/repo`. Then it was
    `source-unresolvable`, naming `--source`. It names no path that exists,
    and is no clone `plan` made, which is what `plan-source-gone` says."""
    value = make(tmp_path / "Thing")
    edited_plan(tmp_path, answered, f"  local_path: {double_quoted(value)}")
    assert load_yaml(tmp_path / PLAN_FILE)["source"]["local_path"] == value
    runs = {"check": checked(tmp_path), "execute": executed(tmp_path)}
    assert_no_traceback_and_no_leg(tmp_path, runs)
    assert_refused_as_gone(runs)


# --- `--source`: a name `gh` would read as one of its options ----------------

#: `--source` values that begin with `-`. Neither is a path that exists, and
#: each holds a `/`, so `Source.open` took it for an `org/repo` name and ran
#: `gh repo clone <it> <directory> -- --quiet`, where gh's own parser read it
#: as an option: `-u` is `--upstream-remote-name`, and `--upload-pack=x/y`
#: is a flag gh does not know. No GitHub owner name begins with `-`.
OPTION_SOURCES = ["-u/x", "--upload-pack=x/y"]


def gh_stub(base: Path) -> tuple[dict, Path]:
    """The environment that puts a `gh` first on PATH, and the file it
    records each call's arguments in, one to a line. It refuses every call.
    It is a `#!` script, which Windows does not execute: there nothing is
    recorded, and the refusal's id alone says that `gh` did not run."""
    binary = base / "bin"
    binary.mkdir()
    script = binary / "gh"
    script.write_bytes(b"#!/bin/sh\n"
                       b"printf '%s\\n' \"$@\" >> \"$GH_STUB_LOG\"\n"
                       b"echo 'stub gh: refusing' >&2\n"
                       b"exit 1\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    log = base / "gh.log"
    return ({"PATH": f"{binary}{os.pathsep}{os.environ.get('PATH', '')}",
             "GH_STUB_LOG": str(log)}, log)


def gh_calls(log: Path) -> str:
    """What the stub was given, readable in an assertion message."""
    return log.read_text(encoding="utf-8") if log.exists() else ""


@pytest.mark.parametrize("spec", OPTION_SOURCES, ids=OPTION_SOURCES)
def test_plan_refuses_a_source_gh_would_read_as_an_option(tmp_path, spec):
    """On main `plan` handed `spec` to `gh repo clone` as its first
    argument (SonarCloud's S8705 asked the question). Now it is
    `source-unresolvable` before anything runs: no path that exists, and no
    `org/repo` name."""
    stub, log = gh_stub(tmp_path)
    refused = adopted("plan", f"--source={spec}", "--project", PROJECT,
                      "--org", "testorg", "--elected-by", "Test Human",
                      "--elected-on", "2026-09-02", "--out",
                      str(tmp_path / PLAN_FILE), "--work-dir",
                      str(tmp_path / WORK), extra=stub)
    assert not log.exists(), f"gh was run with:\n{gh_calls(log)}"
    assert_no_traceback({"plan": refused})
    assert refused.returncode == 2, said(refused)
    assert SOURCE_REFUSED + f"--source {spec!r} is neither".encode() \
        in refused.stderr, said(refused)
    assert not (tmp_path / PLAN_FILE).exists()


@pytest.mark.parametrize("spec", OPTION_SOURCES, ids=OPTION_SOURCES)
def test_check_and_execute_refuse_a_hand_edited_source_gh_would_read(
        tmp_path, answered, spec):
    """The plan file is edited between `plan` and `execute`, on purpose, and
    its `local_path:` is read as a path, never as a `--source` (#652). On
    main `check` and `execute` each ran `gh repo clone` with it first."""
    edited_plan(tmp_path, answered, f"  local_path: {double_quoted(spec)}")
    assert load_yaml(tmp_path / PLAN_FILE)["source"]["local_path"] == spec
    stub, log = gh_stub(tmp_path)
    runs = {"check": checked(tmp_path, stub),
            "execute": executed(tmp_path, stub)}
    assert not log.exists(), f"gh was run with:\n{gh_calls(log)}"
    assert_no_traceback_and_no_leg(tmp_path, runs)
    assert_refused_as_gone(runs)


@WINDOWS_SKIP  # the stub `gh` is a `#!` script; Windows executes none
def test_the_gh_stub_records_an_org_repo_source(tmp_path):
    """The control for the two tests above: an `org/repo` name is handed to
    `gh repo clone`, and the stub records the call it refuses. A stub that
    recorded nothing would let them pass without asking anything."""
    stub, log = gh_stub(tmp_path)
    refused = adopted("plan", "--source=testorg/Thing", "--project", "Thing",
                      "--org", "testorg", "--elected-by", "Test Human",
                      "--elected-on", "2026-09-02", "--out",
                      str(tmp_path / PLAN_FILE), "--work-dir",
                      str(tmp_path / WORK), extra=stub)
    assert_no_traceback({"plan": refused})
    assert refused.returncode == 2, said(refused)
    assert b"REFUSED source-unclonable: " in refused.stderr, said(refused)
    assert gh_calls(log).splitlines()[:3] == ["repo", "clone",
                                              "testorg/Thing"], gh_calls(log)


# --- controls: valid text still adopts, as on main ---------------------------

@needs_filter_repo
@pytest.mark.parametrize("elected_by", ["José", "Ali\u200cReza"],
                         ids=["accented", "zero-width-non-joiner"])
def test_a_valid_non_ascii_elector_still_adopts(tmp_path, elected_by):
    """`José`, and a name joined with U+200C, which `one_printable_line`
    refuses and a file holds: adopted, read back from the manifest as
    itself, and named in the shape's README.

    The manifest is asked through the reader, not for a line: since #250 a
    YAML template's value is written as `double_quoted` spells it, so the
    line holds U+200C as an escape there, and as it stands before.

    Skipped where this system's file name encoding cannot spell the name
    (ASCII under `LC_ALL=C`), asked first: `subprocess` cannot put it on
    `plan`'s command line there, and raised `UnicodeEncodeError` in the
    test, not in the tool."""
    skip_where_the_environment_cannot_carry(elected_by)
    source = make_source_repo(tmp_path / "Thing")
    runs = plan_check_execute(tmp_path, source, "--elected-by", elected_by)
    assert_no_traceback(runs)
    assert runs["check"].returncode == 0, said(runs["check"])
    done = runs["execute"]
    assert done.returncode == 0, said(done)
    assert VERIFIED in done.stdout, said(done)
    manifest = tmp_path / "project.yaml"
    manifest.write_bytes(in_the_split(source, "project.yaml").encode("utf-8"))
    assert load_yaml(manifest)["elected_by"] == elected_by
    assert f"Elected by {elected_by} on 2026-09-02" in in_the_split(
        source, "shape/README.md")


@needs_filter_repo
def test_a_utf8_source_directory_still_adopts_with_local_remotes(tmp_path):
    """A source under a directory `café`: its path is the clone URL, which a
    file holds, so it adopts, and the shape's README (beside the source's
    own) names it. Skipped where this system's file name encoding cannot
    spell the directory's name (ASCII under `LC_ALL=C`), asked before the
    directory is made, where `mkdir` raised `UnicodeEncodeError` in the
    test."""
    parent = tmp_path / "caf\u00e9"
    skip_where_the_environment_cannot_carry(parent.name)
    source = make_source_repo(parent / "Thing")
    runs = plan_check_execute(tmp_path, source)
    assert_no_traceback(runs)
    assert runs["check"].returncode == 0, said(runs["check"])
    done = runs["execute"]
    assert done.returncode == 0, said(done)
    assert VERIFIED in done.stdout, said(done)
    readme = in_the_split(source, "shape/README.md")
    assert f"git clone --recurse-submodules {source.resolve()}\n" in readme


# --- the question itself -----------------------------------------------------

#: Text a file holds: the empty value `plan` records when `git config
#: user.name` names nobody, a name, a date, the default reference, a literal
#: backslash, a space that is not ASCII's, and the invisible `Cf` characters
#: that are not bidi controls -- the joiners U+200C and U+200D, a byte-order
#: mark, a soft hyphen, and the marks U+200E, U+200F and U+061C, which set
#: no span's direction.
WRITABLE = ["", "José", "Ali\u200cReza", "2026-09-02",
            "openxFactory docs/project-repo-schema.md", "CORP\\rsmith",
            "日本", "a\u00a0b", "\ufeffbom", "a\u00adb", "a\u200db",
            "a\u200eb", "a\u200fb", "a\u061cb"]

#: The nine bidi embedding, override and isolate controls, by code point.
BIDI_CONTROLS = [*range(0x202A, 0x202F), *range(0x2066, 0x206A)]

#: `(value, the words its reason holds)`.
UNWRITABLE = [
    ("Jos\udce9", "a byte that is not UTF-8"),
    ("x\ud800", "a lone surrogate"),
    ("x\udfff", "a lone surrogate"),
    ("a\nb", "a line break"), ("a\rb", "a line break"),
    ("a\r\nb", "a line break"), ("end\n", "a line break"),
    ("a\x0bb", "a line break"), ("a\x0cb", "a line break"),
    ("a\x1cb", "a line break"), ("a\x85b", "a line break"),
    ("a\u2028b", "a line break"), ("a\u2029b", "a line break"),
    ("a\x00b", "a control character"), ("a\tb", "a control character"),
    ("a\x1bb", "a control character"), ("a\x7fb", "a control character"),
    ("a\x9fb", "a control character"),
    ("\u202eevil", "a bidirectional control"),
    ("\u202a", "a bidirectional control"),
    ("\u2066x\u2069", "a bidirectional control"),
    ("\u2069", "a bidirectional control"),
]


@pytest.mark.parametrize("value", WRITABLE, ids=[ascii(v) for v in WRITABLE])
def test_text_a_file_holds_has_no_reason(value):
    assert shape_materialize.unwritable_reason(value) is None
    assert value.encode("utf-8").decode("utf-8") == value


@pytest.mark.parametrize("value, words", UNWRITABLE,
                         ids=[ascii(v) for v, _ in UNWRITABLE])
def test_what_no_file_holds_is_named(value, words):
    reason = shape_materialize.unwritable_reason(value)
    assert reason is not None, ascii(value)
    assert words in reason, reason
    assert reason.isprintable(), reason
    assert reason.isascii(), reason


def test_the_question_is_one_printable_line_less_cf_but_the_bidi_controls():
    """Every code point, alone: refused exactly when `one_printable_line`
    refuses it and it is not `Cf`, or when it is one of the nine bidi
    controls, which are `Cf` and still refused."""
    reason = shape_materialize.unwritable_reason
    printable = shape_materialize.one_printable_line
    assert {unicodedata.category(chr(code))
            for code in BIDI_CONTROLS} == {"Cf"}
    wrong = [hex(code) for code in range(sys.maxunicode + 1)
             if (reason(chr(code)) is None)
             != (code not in BIDI_CONTROLS
                 and (printable(chr(code))
                      or unicodedata.category(chr(code)) == "Cf"))]
    assert not wrong, wrong[:20]
