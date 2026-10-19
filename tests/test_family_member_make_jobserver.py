# SPDX-License-Identifier: Apache-2.0
"""A member's make under the family holder's `make -jN` (#888, #987).

THE ISSUE'S LINE, measured on 50178305 under GNU Make 4.3: under the
holder's `make -j2 bootstrap`, each member's make printed `make[1]:
warning: jobserver unavailable: using -j1.  Add '+' to parent make rule.`
and ran its jobs one at a time, and so did each under `make -j2 validate`,
`park` and `resume`. The holder's rules run `scripts/bootstrap.py` and
`scripts/siblings.py` with no `+`, so make closes the jobserver's two
descriptors for them, `Popen` closes the rest, and the member's make still
found `-j2 --jobserver-auth=3,4` in the `MAKEFLAGS` it inherits. The rule
the warning names is the holder's pinned Makefile, which the person does
not own.

BOTH SCRIPTS NOW TAKE THE JOBSERVER, and the `-j` that comes with it, out
of the `MAKEFLAGS` a member's make inherits (`member_make_env`): each
member's make runs its jobs one at a time, as it did, and says nothing.
`bootstrap.py`'s `member_make_env` says why the jobserver is not handed on
instead. `make siblings` runs no member's make: it runs a member's own
`scripts/bootstrap.py`, which runs none.

BUT NOT GNU MAKE 4.4's NAMED PIPE (#987), `--jobserver-auth=fifo:<path>`,
which a make opens by its path: both scripts hand the holder's `MAKEFLAGS`
on as it is where every jobserver it names is such a pipe, there now at an
absolute path, and the member's make says it is GNU make 4.4 or later on
`make --version`, asked once in a run. No GNU make 4.4 was on the host
these tests were written on (GNU Make 4.3, as in CI), so a fake `make` that
answers `--version` as each make does stands in for the member's
(`fake_make`), under the `MAKEFLAGS` a 4.4 holder writes and a named pipe
of the test's own. The one test that needs a real 4.4 is skipped where
`make -j2` writes no named pipe, and #888's two that need a pipe's
descriptors are skipped where it does.

THE STATE is `tests/test_family.py`'s family, its two members scaffolded
and added by this repository's own tools, in a private copy (`holder`),
each member's Makefile replaced in its work tree by `TRACED`: the target's
two prerequisites, neither needing the other, each write a `start` and a
`stop` line to the member's trace a second apart. Run one at a time they
write the four lines in order; run together, they would interleave them.
The tests read that order, never a clock. For `park` and `resume`, each
member is cloned BESIDE the holder too, where those verbs run, with the
same Makefile. No network: the gh guard first on PATH (`offline`), and
local remotes.

Skipped where there is no `make`, or no POSIX shell for its recipes.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP, git, load_without_bytecode
from test_family import MEMBERS, family  # noqa: F401
from test_family_add_refusals import holder, offline  # noqa: F401
from test_family_bootstrap_gate_order import fetching
from test_family_dry_run import isolated
from test_family_holder_bootstrap_texts import without_make

MAKE = shutil.which("make")

pytestmark = [WINDOWS_SKIP,
              pytest.mark.skipif(MAKE is None, reason="needs `make` on PATH")]

#: What a member's make printed under the holder's `make -j2` (#888).
WARNING = "jobserver unavailable"
#: The family root's two scripts that run a member's make.
SCRIPTS = REPO / "templates" / "family-root" / "scripts"
#: How GNU make 4.4 and later name a named pipe for their jobserver in
#: `MAKEFLAGS`, before its path (#987).
FIFO = "--jobserver-auth=fifo:"

#: A member's Makefile, written over its own in the work tree: each target
#: the holder runs in a member has two prerequisites that need nothing of
#: each other, and then says the flags its make runs with.
TRACED = (b".PHONY: bootstrap validate park resume one two\n"
          b"bootstrap validate park resume: one two\n"
          b"\t@echo \"flags $$MAKEFLAGS\" >> trace.log\n"
          b"one two:\n"
          b"\t@echo 'start $@' >> trace.log; sleep 1; "
          b"echo 'stop $@' >> trace.log\n")
#: `TRACED`'s trace of a run that ran the two one at a time.
SERIAL = ["start one", "stop one", "start two", "stop two"]


def traced(directory: Path) -> Path:
    """`directory`, a member's checkout, with `TRACED` for its Makefile;
    returns where its trace will be."""
    (directory / "Makefile").write_bytes(TRACED)
    return directory / "trace.log"


def environment(offline, tmp_path: Path) -> dict:
    """A whole environment for the holder's make: no make above it, as from
    a shell, the gh guard first on PATH, a git configuration of the test's
    own, the file transport the local members need (`fetching`), and this
    interpreter for `$(PYTHON)`, given here and not on make's command line
    so that `MAKEFLAGS` carries no variable a test did not give."""
    return {**without_make(), **fetching(isolated(offline, tmp_path)),
            "PYTHON": sys.executable}


def holder_make(root: Path, env: dict, *args: str) -> tuple[int, str]:
    """`make <args>` in the holder `root`: its exit code, and its stdout
    and stderr together."""
    proc = subprocess.run([MAKE, *args], cwd=str(root), env=env,
                          stdin=subprocess.DEVNULL, capture_output=True,
                          check=False)
    return proc.returncode, (proc.stdout + proc.stderr).decode(
        "utf-8", "replace")


def traced_members(holder: Path, family, beside: bool) -> list[Path]:
    """Each member's checkout a verb runs its make in, traced: the pinned
    copy in the holder, `members/<P>`, for `bootstrap` and `validate`;
    for `park` and `resume` (`siblings.py --make`), which never run in
    that copy, its working clone BESIDE the holder, cloned here from its
    own remote."""
    traces = []
    for project in MEMBERS:
        checkout = holder / "members" / project
        if beside:
            checkout = holder.parent / project
            git("clone", "-q", str(family["remotes"] / f"{project}.git"),
                str(checkout), cwd=holder.parent)
        traces.append(traced(checkout))
    return traces


#: `{verb: whether it runs a member's make in a clone beside the holder}`,
#: each verb the holder's make runs a member's make for.
VERBS = {"bootstrap": False, "validate": False, "park": True, "resume": True}


def read(trace: Path) -> list[str]:
    return trace.read_text(encoding="utf-8").splitlines()


#: A word of `MAKEFLAGS` as make reads it: split only at a space or a tab,
#: and a backslash keeps the character after it, either of those
#: included, in the word.
WORD = re.compile(r"(?:\\.|[^ \t])+", re.DOTALL)


def jobs_words(flags: str) -> list[str]:
    """The words of a member's `flags` line that ask for jobs or name a
    jobserver."""
    return [word for word in WORD.findall(flags)
            if word.startswith(("-j", "--jobserver"))]


def jobserver_of_make_j2(tmp_path: Path) -> str:
    """The jobserver word this host's make writes into a recipe's
    `MAKEFLAGS` under `make -j2`, or "" where it writes none: a pipe's
    descriptors before GNU make 4.4 (`--jobserver-auth=3,4`, measured on
    4.3), and from 4.4 on, where there is `mkfifo`, a named pipe (`FIFO`,
    read in make's NEWS, not run)."""
    probe = tmp_path / "make-j2"
    probe.mkdir()
    (probe / "Makefile").write_bytes(b"all:\n\t@echo \"$$MAKEFLAGS\"\n")
    said = subprocess.run([MAKE, "-s", "-j2"], cwd=str(probe),
                          env=without_make(), stdin=subprocess.DEVNULL,
                          capture_output=True, check=True)
    return next((word for word in WORD.findall(
        said.stdout.decode("utf-8", "replace").strip())
        if word.startswith("--jobserver-auth=")), "")


def needs_a_pipe_s_descriptors(tmp_path: Path) -> None:
    """Skips a test of #888's jobserver, a pipe's descriptors, where this
    host's `make -j2` writes GNU make 4.4's named pipe instead, which a
    member's make of 4.4 shares (#987): there
    `test_under_make_4_4_a_member_s_make_shares_the_holder_s_named_pipe`
    runs instead."""
    word = jobserver_of_make_j2(tmp_path)
    if word.startswith(FIFO):
        pytest.skip(f"`make -j2` here writes {word}, a named pipe, which a "
                    "member's make shares (#987)")


@pytest.mark.parametrize("verb", VERBS)
def test_no_member_s_make_warns_under_make_j2_and_its_jobs_run_serially(
        family, holder, offline, tmp_path, verb):
    """#888's LINE, every path that runs a member's make: under the
    holder's `make -j2 <verb>`, no `jobserver unavailable` line, and each
    member's make ran its two jobs one at a time, with no `-j` and no
    jobserver in its flags. At 50178305 each printed the warning and ran
    with `-j1`."""
    needs_a_pipe_s_descriptors(tmp_path)
    traces = traced_members(holder, family, VERBS[verb])
    env = environment(offline, tmp_path)

    code, said = holder_make(holder, env, "-j2", verb)

    assert code == 0, said
    assert WARNING not in said, said
    for trace in traces:
        lines = read(trace)
        assert lines[:4] == SERIAL, (trace, lines)
        (flags,) = lines[4:]
        assert flags.startswith("flags "), lines
        assert jobs_words(flags) == [], (trace, flags)


def test_a_member_s_make_keeps_every_other_flag_and_a_plain_run_is_as_it_was(
        family, holder, offline, tmp_path):
    """No misfire. Under `make -k -j2 bootstrap NOTE='a -j3'`, each
    member's make runs with exactly the flags it runs with under `make -k
    bootstrap NOTE='a -j3'`, with no `-j`: `-k` kept, and the variable
    whole, though its value holds ` -j3`. The plain run, no `-j`, names no
    jobserver, so its `MAKEFLAGS` reaches the member as it always did, and
    neither run warns."""
    needs_a_pipe_s_descriptors(tmp_path)
    traces = traced_members(holder, family, beside=False)
    env = environment(offline, tmp_path)
    flags = {}

    for jobs in ((), ("-j2",)):
        for trace in traces:
            trace.unlink(missing_ok=True)
        code, said = holder_make(holder, env, "-k", *jobs, "bootstrap",
                                 "NOTE=a -j3")
        assert code == 0, said
        assert WARNING not in said, said
        for trace in traces:
            lines = read(trace)
            assert lines[:4] == SERIAL, (jobs, trace, lines)
            flags[jobs, trace] = lines[4:]

    for trace in traces:
        assert flags[(), trace] == flags[("-j2",), trace], flags
        (said,) = flags[(), trace]
        words = WORD.findall(said)
        assert "k" in words[1], said
        assert r"NOTE=a\ -j3" in words, said
        assert jobs_words(said) == [], said


# --- GNU make 4.4's named pipe, through the holder's rules (#987) ----------

#: `{verb: the line of the holder's rule that runs a member's make}`, as
#: `templates/family-root/Makefile` writes it. `run_rule` runs it with
#: `$(PYTHON)` this interpreter and `$(ARGS)` empty, as the holder's make
#: would.
RULES = {
    "bootstrap": "$(PYTHON) scripts/bootstrap.py",
    "validate": "$(PYTHON) scripts/bootstrap.py --no-fetch --members-make "
                "validate",
    "park": "$(PYTHON) scripts/siblings.py --make park --make-arg "
            "'ARGS=$(ARGS)'",
    "resume": "$(PYTHON) scripts/siblings.py --make resume --make-arg "
              "'ARGS=$(ARGS)'",
}
#: `{verb: what each verb's rule gives a member's make on its command
#: line}`.
TARGETS = {"bootstrap": "bootstrap", "validate": "validate",
           "park": "park ARGS=", "resume": "resume ARGS="}


def run_rule(holder: Path, env: dict, verb: str) -> tuple[int, str]:
    """`verb`'s line of the holder's rule (`RULES`), found in its Makefile
    and run straight in `holder` under `env`, as a GNU make 4.4 holder's
    make would run it there: its exit code, and its stdout and stderr
    together. Not run by this host's make, which would write a jobserver
    of its own into `MAKEFLAGS`."""
    line = RULES[verb]
    assert f"\t{line}\n" in (holder / "Makefile").read_text(encoding="utf-8")
    argv = shlex.split(line.replace("$(PYTHON)", shlex.quote(sys.executable))
                       .replace("$(ARGS)", ""))
    proc = subprocess.run(argv, cwd=str(holder), env=env,
                          stdin=subprocess.DEVNULL, capture_output=True,
                          check=False)
    return proc.returncode, (proc.stdout + proc.stderr).decode(
        "utf-8", "replace")


def named_pipe(directory: Path) -> Path:
    """A named pipe made in `directory`, as GNU make 4.4 makes its
    jobserver: there for as long as the test is."""
    pipe = directory / "GMfifo987"
    os.mkfifo(pipe)
    return pipe


def fake_make(directory: Path, said: bytes = b"GNU Make 4.4.1\n",
              code: int = 0, *, waits: bool = False) -> Path:
    """An executable `make` in `directory`, which it makes, standing in for
    a member's make: each call adds a line to `calls.log` beside it, its
    arguments and the `MAKEFLAGS` it was given (`calls`); then `--version`
    prints `said` and exits `code`, or, where it `waits`, sleeps 30
    seconds in the same process; any other call exits 0."""
    directory.mkdir()
    (directory / "version").write_bytes(said)
    answer = "exec sleep 30" if waits else f'cat "$here/version"; exit {code}'
    make = directory / "make"
    make.write_text("#!/bin/sh\n"
                    "here=${0%/*}\n"
                    "printf '%s|%s\\n' \"$*\" \"$MAKEFLAGS\" "
                    ">> \"$here/calls.log\"\n"
                    f"if [ \"$1\" = --version ]; then {answer}; fi\n"
                    "exit 0\n", encoding="utf-8")
    make.chmod(0o755)
    return make


def calls(make: Path) -> list[str]:
    """`fake_make`'s calls, in order, each `<arguments>|<MAKEFLAGS>`."""
    log = make.parent / "calls.log"
    if not log.exists():
        return []
    return log.read_text(encoding="utf-8").splitlines()


def version_of(make: str) -> tuple[int, int]:
    """`make`'s GNU make version, as its `make --version` says it, read
    here rather than by the scripts' own `reads_fifo`; (0, 0) where it
    says none."""
    said = subprocess.run([make, "--version"], env=without_make(),
                          stdin=subprocess.DEVNULL, capture_output=True,
                          check=False).stdout
    found = re.match(rb"GNU Make (\d+)\.(\d+)", said)
    return (int(found[1]), int(found[2])) if found else (0, 0)


@pytest.mark.parametrize("verb", VERBS)
def test_a_member_s_make_that_reads_a_named_pipe_is_handed_the_holder_s(
        family, holder, offline, tmp_path, verb):
    """#987, every path that runs a member's make: each verb's rule run
    under the `MAKEFLAGS` a GNU make 4.4 holder's `make -j2` gives it,
    `-j2` and a named pipe that is there, with `$MAKE` a make that says it
    is GNU make 4.4.1. Each member's make is handed that `MAKEFLAGS` byte
    for byte, and that make was asked its version once in the run, with no
    jobserver in its own `MAKEFLAGS`. At 3864b18c each was handed none."""
    traced_members(holder, family, VERBS[verb])
    make = fake_make(tmp_path / "bin")
    flags = f" -j2 {FIFO}{named_pipe(tmp_path)}"
    env = {**environment(offline, tmp_path), "MAKE": str(make),
           "MAKEFLAGS": flags, "MAKELEVEL": "1"}

    code, said = run_rule(holder, env, verb)

    assert code == 0, said
    assert calls(make) == ["--version|",
                           *[f"{TARGETS[verb]}|{flags}"] * len(MEMBERS)], said


@pytest.mark.parametrize("verb", VERBS)
def test_under_a_named_pipe_a_member_s_make_before_4_4_runs_serially(
        family, holder, offline, tmp_path, verb):
    """#987's second verify line, a holder's make of 4.4 and an older
    `make` on PATH: each verb's rule run under the `MAKEFLAGS` 4.4 gives
    it, `-j2` and a named pipe that is there, and this host's make for
    each member's. Given that word, GNU make 4.3 stops (`invalid
    --jobserver-auth string`, exit 2, measured). It is not given it: it
    runs its two jobs one at a time, with no `-j` in its flags, and
    nothing says a word of a jobserver. Skipped where the make on PATH is
    4.4 or later."""
    found = version_of(MAKE)
    if found >= (4, 4):
        pytest.skip(f"the make on PATH is GNU make {found[0]}.{found[1]}, "
                    "which reads a named pipe")
    traces = traced_members(holder, family, VERBS[verb])
    env = {**environment(offline, tmp_path),
           "MAKEFLAGS": f" -j2 {FIFO}{named_pipe(tmp_path)}",
           "MAKELEVEL": "1"}

    code, said = run_rule(holder, env, verb)

    assert code == 0, said
    assert "jobserver" not in said, said
    for trace in traces:
        lines = read(trace)
        assert lines[:4] == SERIAL, (trace, lines)
        (flags,) = lines[4:]
        assert jobs_words(flags) == [], (trace, flags)


def test_under_make_4_4_a_member_s_make_shares_the_holder_s_named_pipe(
        family, holder, offline, tmp_path):
    """#987's first verify line, where this host's make is GNU make 4.4 or
    later and `make -j2` writes a named pipe: under the holder's `make -j2
    bootstrap`, each member's make runs its two jobs together, within the
    holder's jobserver, which its flags name, and nothing says a word of a
    jobserver. Skipped where `make -j2` writes no named pipe, by what it
    writes: GNU Make 4.3 writes a pipe's descriptors (measured), and it is
    the make on the host this test was written on and in CI, so this test
    has not been run."""
    word = jobserver_of_make_j2(tmp_path)
    if not word.startswith(FIFO):
        pytest.skip(f"`make -j2` here writes {word or 'no jobserver'}, not "
                    "GNU make 4.4's named pipe")
    traces = traced_members(holder, family, beside=False)
    env = environment(offline, tmp_path)

    code, said = holder_make(holder, env, "-j2", "bootstrap")

    assert code == 0, said
    assert "jobserver" not in said, said
    for trace in traces:
        lines = read(trace)
        assert sorted(lines[:2]) == ["start one", "start two"], (trace, lines)
        (flags,) = lines[4:]
        assert [word for word in jobs_words(flags)
                if word.startswith(FIFO)], (trace, flags)


# --- the two scripts' `member_make_env`, one answer ------------------------

#: `{case: (MAKEFLAGS as a make writes it, as the member's make gets it)}`,
#: as each make spells its jobserver: GNU make 4.2 to 4.3 a pipe's two
#: descriptors (measured, 4.3); 4.4 a named pipe, `fifo:<path>`; make before
#: 4.2, macOS's 3.81 among them, `--jobserver-fds` and a bare `-j`; and make
#: on Windows a semaphore's name. The last three are read from make's
#: documentation, not run. And 4.3's with `-j16`, and with a value that
#: holds a no-break space (U+00A0), a narrow one (U+202F) or a newline:
#: make splits only at a space or a tab, and passes each of those three
#: through raw (measured), so each stays inside its word. The member's
#: make says it is GNU make 4.3, which reads no named pipe (#987).
TAKEN_OUT = {
    "4.3": (" -j2 --jobserver-auth=3,4", ""),
    "4.3-k-s-variables": (r"ks -j2 --jobserver-auth=3,4 -- B=a\ b F=x",
                          r"ks -- B=a\ b F=x"),
    "4.3-variable-holds-j": (r" -j2 --jobserver-auth=3,4 -- C=-O2\ -j4",
                             r"-- C=-O2\ -j4"),
    "4.4-fifo": (" -j4 --jobserver-auth=fifo:/tmp/GMfifo1234", ""),
    "4.4-fifo-blank-in-path": (r" -j4 --jobserver-auth=fifo:/t\ x/GMfifo1",
                               ""),
    "3.81": (" --jobserver-fds=3,4 -j", ""),
    "3.81-k": ("k --jobserver-fds=3,4 -j", "k"),
    "windows": (" -j2 --jobserver-auth=gmake_semaphore_1234", ""),
    "4.3-j16-k": ("k -j16 --jobserver-auth=3,4", "k"),
    "4.3-no-break-space": (
        " -j2 --jobserver-auth=3,4 -- NOTE=x EXTRA=injected",
        "-- NOTE=x EXTRA=injected"),
    "4.3-narrow-no-break-space": (" -j2 --jobserver-auth=3,4 -- NOTE=x !",
                                  "-- NOTE=x !"),
    "4.3-newline": (" -j2 --jobserver-auth=3,4 -- NOTE=x\nEXTRA=injected",
                    "-- NOTE=x\nEXTRA=injected"),
}
#: `TAKEN_OUT`'s spellings that name no named pipe: taken out for a member's
#: make of 4.4 too (#987).
NO_NAMED_PIPE = {case: spelling for case, spelling in TAKEN_OUT.items()
                 if FIFO not in spelling[0]}
#: `MAKEFLAGS` that names no jobserver, left exactly as it is: no flags,
#: `make -j` with no number (which starts no jobserver), a person's own
#: `-j8` with no make above, and a variable whose value only looks like one.
LEFT = {"empty": "", "unlimited": " -j", "a-person-s": "-j8",
        "variables-only": " -- NOTE=x",
        "variable-like-a-jobserver": " -- X=--jobserver-auth=3,4"}


@pytest.fixture
def scripts(monkeypatch) -> dict:
    """`{name: module}`: the family root's `bootstrap.py` and
    `siblings.py`, loaded with no bytecode written under `templates/`;
    `siblings.py`'s `bootstrap` import is answered by the template's own,
    the copy beside it in a holder. `sys.path` and `sys.modules` are put
    back when the test ends."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    boot = load_without_bytecode(SCRIPTS / "bootstrap.py",
                                 "jobserver_family_bootstrap")
    monkeypatch.setitem(sys.modules, "bootstrap", boot)
    return {"bootstrap.py": boot,
            "siblings.py": load_without_bytecode(
                SCRIPTS / "siblings.py", "jobserver_family_siblings")}


@pytest.mark.parametrize("script", ["bootstrap.py", "siblings.py"])
@pytest.mark.parametrize("flags, kept", TAKEN_OUT.values(), ids=TAKEN_OUT)
def test_each_script_takes_out_a_jobserver_and_its_j_and_nothing_else(
        scripts, monkeypatch, tmp_path, script, flags, kept):
    """Each make's spelling of its jobserver, and the `-j` beside it, taken
    out by both scripts alike for a member's make of GNU make 4.3; every
    other word kept, a blank a backslash keeps in a variable's value
    included, and nothing else in the environment touched."""
    make = fake_make(tmp_path / "bin", b"GNU Make 4.3\n")
    monkeypatch.setenv("MAKEFLAGS", flags)

    env = scripts[script].member_make_env(str(make))

    assert env.pop("MAKEFLAGS") == kept
    assert env == {key: value for key, value in os.environ.items()
                   if key != "MAKEFLAGS"}


@pytest.mark.parametrize("script", ["bootstrap.py", "siblings.py"])
@pytest.mark.parametrize("flags, kept", NO_NAMED_PIPE.values(),
                         ids=NO_NAMED_PIPE)
def test_each_script_hands_no_other_jobserver_to_make_4_4(
        scripts, monkeypatch, tmp_path, script, flags, kept):
    """#987 hands on a named pipe and nothing else: for a member's make
    that says it is GNU make 4.4.1, a pipe's descriptors, make 3.81's
    `--jobserver-fds` and Windows' semaphore are taken out as for 4.3,
    with the `-j` beside them, and that make is not even asked."""
    make = fake_make(tmp_path / "bin")
    monkeypatch.setenv("MAKEFLAGS", flags)

    env = scripts[script].member_make_env(str(make))

    assert env.pop("MAKEFLAGS") == kept
    assert env == {key: value for key, value in os.environ.items()
                   if key != "MAKEFLAGS"}
    assert calls(make) == []


@pytest.mark.parametrize("script", ["bootstrap.py", "siblings.py"])
@pytest.mark.parametrize("flags", [None, *LEFT.values()],
                         ids=["unset", *LEFT])
def test_each_script_leaves_a_makeflags_that_names_no_jobserver(
        scripts, monkeypatch, tmp_path, script, flags):
    """No jobserver named, nothing taken out: the environment is this
    run's own, `MAKEFLAGS` byte for byte, and unset where it was; and the
    member's make is not asked its version."""
    make = fake_make(tmp_path / "bin")
    if flags is None:
        monkeypatch.delenv("MAKEFLAGS", raising=False)
    else:
        monkeypatch.setenv("MAKEFLAGS", flags)

    assert scripts[script].member_make_env(str(make)) == dict(os.environ)
    assert calls(make) == []


@pytest.mark.parametrize("script", ["bootstrap.py", "siblings.py"])
def test_each_script_hands_back_a_copy_and_leaves_its_own_environment(
        scripts, monkeypatch, tmp_path, script):
    """The environment a member's make gets is a copy: this run's own
    `MAKEFLAGS`, which names a jobserver here, is as it was after the
    call, and the copy is a plain `dict`, not `os.environ`."""
    make = fake_make(tmp_path / "bin")
    monkeypatch.setenv("MAKEFLAGS", " -j2 --jobserver-auth=3,4")
    before = dict(os.environ)

    env = scripts[script].member_make_env(str(make))

    assert type(env) is dict
    assert env["MAKEFLAGS"] == ""
    assert dict(os.environ) == before


#: `{case: the first lines of `make --version`}` from a member's make that
#: reads GNU make 4.4's named pipe: 4.4, 4.4.1, and a 4.10 and a 5.0 to
#: come, whose versions are read as numbers.
READERS = {"4.4": b"GNU Make 4.4\n",
           "4.4.1": b"GNU Make 4.4.1\nBuilt for x86_64-pc-linux-gnu\n",
           "4.10": b"GNU Make 4.10\n", "5.0": b"GNU Make 5.0\n"}


@pytest.mark.parametrize("script", ["bootstrap.py", "siblings.py"])
@pytest.mark.parametrize("said", READERS.values(), ids=READERS)
def test_each_script_hands_a_named_pipe_to_a_make_that_reads_it(
        scripts, monkeypatch, tmp_path, script, said):
    """#987: GNU make 4.4's `MAKEFLAGS`, `-j2` and a named pipe that is
    there, reaches a member's make that says it is 4.4 or later byte for
    byte, the `-j2` with it, in a copy of this run's environment; that
    make was asked its version once, with no jobserver."""
    make = fake_make(tmp_path / "bin", said)
    monkeypatch.setenv("MAKEFLAGS", f" -j2 {FIFO}{named_pipe(tmp_path)}")

    env = scripts[script].member_make_env(str(make))

    assert type(env) is dict
    assert env == dict(os.environ)
    assert calls(make) == ["--version|"]


@pytest.mark.parametrize("script", ["bootstrap.py", "siblings.py"])
@pytest.mark.parametrize("folder", ["t x", "t\tx", "t\\x"],
                         ids=["space", "tab", "backslash"])
def test_each_script_reads_a_named_pipe_s_path_as_make_reads_it(
        scripts, monkeypatch, tmp_path, script, folder):
    """A blank or a backslash in the named pipe's path, which make writes
    into `MAKEFLAGS` with a backslash before it, is read as make reads it,
    a backslash keeping the character after it: the pipe is found, and
    `MAKEFLAGS` handed on as it is."""
    directory = tmp_path / folder
    directory.mkdir()
    written = re.sub(r"([ \t\\])", r"\\\1", str(named_pipe(directory)))
    monkeypatch.setenv("MAKEFLAGS", f" -j2 {FIFO}{written}")
    make = fake_make(tmp_path / "bin")

    assert scripts[script].member_make_env(str(make)) == dict(os.environ)
    assert calls(make) == ["--version|"]


@pytest.mark.parametrize("script", ["bootstrap.py", "siblings.py"])
def test_each_script_asks_a_make_once_a_run_and_hands_it_no_jobserver(
        scripts, monkeypatch, tmp_path, script):
    """`make --version` is asked once in a run, however many members' makes
    the run starts, and with the jobserver taken out of its own
    `MAKEFLAGS`, every other word kept: a make asked its version is handed
    no jobserver to open. Each member's make then gets 4.4's `MAKEFLAGS`
    as it is, its `-k`, `-s` and variable included."""
    make = fake_make(tmp_path / "bin")
    flags = rf"ks -j2 {FIFO}{named_pipe(tmp_path)} -- NOTE=a\ -j3"
    monkeypatch.setenv("MAKEFLAGS", flags)
    module = scripts[script]

    handed = [module.member_make_env(str(make))["MAKEFLAGS"]
              for _ in range(3)]

    assert handed == [flags] * 3
    assert calls(make) == [r"--version|ks -- NOTE=a\ -j3"]


#: `{case: (the first lines of `make --version`, its exit code)}` from a
#: member's make that does not say it reads GNU make 4.4's named pipe: GNU
#: make before 4.4 (4.3 measured: given the word, it stops with `invalid
#: --jobserver-auth string`, exit 2), a make that names itself otherwise,
#: one that names 4.4.1 and exits 1, and one that says nothing.
NOT_READERS = {"4.3": (b"GNU Make 4.3\nBuilt for x86_64-pc-linux-gnu\n", 0),
               "4.2.1": (b"GNU Make 4.2.1\n", 0),
               "3.81": (b"GNU Make 3.81\n", 0),
               "another-make": (b"bmake 20240711\n", 0),
               "4.4.1-exit-1": (b"GNU Make 4.4.1\n", 1),
               "silent": (b"", 0)}


@pytest.mark.parametrize("script", ["bootstrap.py", "siblings.py"])
@pytest.mark.parametrize("said, code", NOT_READERS.values(), ids=NOT_READERS)
def test_each_script_takes_a_named_pipe_from_a_make_not_known_to_read_it(
        scripts, monkeypatch, tmp_path, script, said, code):
    """#987's other half: under 4.4's `MAKEFLAGS`, a named pipe that is
    there, a member's make that does not say it is GNU make 4.4 or later
    gets neither the pipe nor the `-j2`, as #888 left it; every other word
    kept, and that make asked its version once."""
    make = fake_make(tmp_path / "bin", said, code)
    monkeypatch.setenv("MAKEFLAGS",
                       f" -j2 {FIFO}{named_pipe(tmp_path)} -- NOTE=x")

    env = scripts[script].member_make_env(str(make))

    assert env.pop("MAKEFLAGS") == "-- NOTE=x"
    assert env == {key: value for key, value in os.environ.items()
                   if key != "MAKEFLAGS"}
    assert calls(make) == ["--version|-- NOTE=x"]


@pytest.mark.parametrize("script", ["bootstrap.py", "siblings.py"])
def test_each_script_takes_a_named_pipe_from_a_make_that_is_not_there(
        scripts, monkeypatch, tmp_path, script):
    """A member's make that cannot be started is asked nothing it can
    answer, and the run goes on: the pipe and its `-j2` are taken out,
    and nothing is raised here."""
    monkeypatch.setenv("MAKEFLAGS", f" -j2 {FIFO}{named_pipe(tmp_path)}")

    env = scripts[script].member_make_env(str(tmp_path / "no-make"))

    assert env["MAKEFLAGS"] == ""


@pytest.mark.parametrize("script", ["bootstrap.py", "siblings.py"])
def test_each_script_takes_a_named_pipe_from_a_make_too_slow_to_answer(
        scripts, monkeypatch, tmp_path, script):
    """A member's make that does not answer `--version` within
    `VERSION_TIMEOUT` seconds, here 1, is a no, and the run is not held
    for it: the fake sleeps 30 seconds, and is stopped."""
    module = scripts[script]
    monkeypatch.setattr(module, "VERSION_TIMEOUT", 1)
    make = fake_make(tmp_path / "bin", waits=True)
    monkeypatch.setenv("MAKEFLAGS", f" -j2 {FIFO}{named_pipe(tmp_path)}")
    began = time.monotonic()

    env = module.member_make_env(str(make))

    assert time.monotonic() - began < 20
    assert env["MAKEFLAGS"] == ""
    assert calls(make) == ["--version|"]


@pytest.mark.parametrize("script", ["bootstrap.py", "siblings.py"])
@pytest.mark.parametrize("case", ["gone", "a-file", "relative",
                                  "beside-descriptors"])
def test_each_script_takes_out_a_named_pipe_a_member_s_make_cannot_open(
        scripts, monkeypatch, tmp_path, script, case):
    """A named pipe's word whose path holds no named pipe now, which would
    make a 4.4 member's make warn that it cannot open the jobserver, is
    taken out with its `-j2` though the member's make says it is 4.4.1,
    and that make is not asked: a pipe that is gone, a path that holds a
    file, a pipe named relative to this run's directory, which is not
    the member's; and a pipe named beside a pipe's descriptors."""
    make = fake_make(tmp_path / "bin")
    pipe = named_pipe(tmp_path)
    (tmp_path / "GMfifo-file").write_bytes(b"")
    monkeypatch.chdir(tmp_path)
    word = {"gone": f"{FIFO}{tmp_path / 'GMfifo-gone'}",
            "a-file": f"{FIFO}{tmp_path / 'GMfifo-file'}",
            "relative": f"{FIFO}{pipe.name}",
            "beside-descriptors": f"--jobserver-auth=3,4 {FIFO}{pipe}"}[case]
    monkeypatch.setenv("MAKEFLAGS", f" -j2 {word}")

    env = scripts[script].member_make_env(str(make))

    assert env["MAKEFLAGS"] == ""
    assert calls(make) == []
