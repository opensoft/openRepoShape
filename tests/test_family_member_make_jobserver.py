# SPDX-License-Identifier: Apache-2.0
"""A member's make under the family holder's `make -jN` (#888).

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
import shutil
import subprocess
import sys
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


@pytest.mark.parametrize("verb", VERBS)
def test_no_member_s_make_warns_under_make_j2_and_its_jobs_run_serially(
        family, holder, offline, tmp_path, verb):
    """#888's LINE, every path that runs a member's make: under the
    holder's `make -j2 <verb>`, no `jobserver unavailable` line, and each
    member's make ran its two jobs one at a time, with no `-j` and no
    jobserver in its flags. At 50178305 each printed the warning and ran
    with `-j1`."""
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


# --- the two scripts' `member_make_env`, one answer ------------------------

#: `{case: (MAKEFLAGS as a make writes it, as the member's make gets it)}`,
#: as each make spells its jobserver: GNU make 4.2 to 4.3 a pipe's two
#: descriptors (measured, 4.3); 4.4 a named pipe, `fifo:<path>`; make before
#: 4.2, macOS's 3.81 among them, `--jobserver-fds` and a bare `-j`; and make
#: on Windows a semaphore's name. The last three are read from make's
#: documentation, not run. And 4.3's with `-j16`, and with a value that
#: holds a no-break space (U+00A0), a narrow one (U+202F) or a newline:
#: make splits only at a space or a tab, and passes each of those three
#: through raw (measured), so each stays inside its word.
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
        " -j2 --jobserver-auth=3,4 -- NOTE=x\u00a0EXTRA=injected",
        "-- NOTE=x\u00a0EXTRA=injected"),
    "4.3-narrow-no-break-space": (" -j2 --jobserver-auth=3,4 -- NOTE=x\u202f!",
                                  "-- NOTE=x\u202f!"),
    "4.3-newline": (" -j2 --jobserver-auth=3,4 -- NOTE=x\nEXTRA=injected",
                    "-- NOTE=x\nEXTRA=injected"),
}
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
        scripts, monkeypatch, script, flags, kept):
    """Each make's spelling of its jobserver, and the `-j` beside it, taken
    out by both scripts alike; every other word kept, a blank a backslash
    keeps in a variable's value included, and nothing else in the
    environment touched."""
    monkeypatch.setenv("MAKEFLAGS", flags)

    env = scripts[script].member_make_env()

    assert env.pop("MAKEFLAGS") == kept
    assert env == {key: value for key, value in os.environ.items()
                   if key != "MAKEFLAGS"}


@pytest.mark.parametrize("script", ["bootstrap.py", "siblings.py"])
@pytest.mark.parametrize("flags", [None, *LEFT.values()],
                         ids=["unset", *LEFT])
def test_each_script_leaves_a_makeflags_that_names_no_jobserver(
        scripts, monkeypatch, script, flags):
    """No jobserver named, nothing taken out: the environment is this
    run's own, `MAKEFLAGS` byte for byte, and unset where it was."""
    if flags is None:
        monkeypatch.delenv("MAKEFLAGS", raising=False)
    else:
        monkeypatch.setenv("MAKEFLAGS", flags)

    assert scripts[script].member_make_env() == dict(os.environ)


@pytest.mark.parametrize("script", ["bootstrap.py", "siblings.py"])
def test_each_script_hands_back_a_copy_and_leaves_its_own_environment(
        scripts, monkeypatch, script):
    """The environment a member's make gets is a copy: this run's own
    `MAKEFLAGS`, which names a jobserver here, is as it was after the
    call, and the copy is a plain `dict`, not `os.environ`."""
    monkeypatch.setenv("MAKEFLAGS", " -j2 --jobserver-auth=3,4")
    before = dict(os.environ)

    env = scripts[script].member_make_env()

    assert type(env) is dict
    assert env["MAKEFLAGS"] == ""
    assert dict(os.environ) == before
