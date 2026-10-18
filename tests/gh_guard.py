# SPDX-License-Identifier: Apache-2.0
"""The suite's `gh` (#296): two answers, one refusal, and a log of every call.

WHY IT EXISTS. `tests/conftest.py` says NO NETWORK AND NO GITHUB, and 149
tests broke that without a word. Every doctor run ends in the `machine` row,
which runs `setup-project.py --preflight`, which asks `gh --version`, `gh auth
status` and, when the login answers, `gh api user`; the installed command's
`--install` ends with a `gh auth status` of its own. Nothing stood between
those calls and whatever `gh` the operator had on PATH -- 407 calls over four
files, on a logged-in machine each one a request to GitHub carrying the
operator's token -- and the one stub the doctor tests did have could not see
them, because the preflight captures `gh`'s output.

WHAT IT DOES. `tests/conftest.py` copies this file into a directory under
pytest's temporary root, writes two launchers beside it -- `gh`, a POSIX
`#!/bin/sh`, and `gh.cmd` -- and puts that directory FIRST on PATH for the
whole session, so every child inherits it however it was started. Asked one
of the two `PROBES`, it answers; asked anything else, it refuses with
`GUARD_EXIT` and one line naming `tests/conftest.py`. Every call, the probes
included, is one JSON line in `LOG_NAME` beside this file, carrying its argv
and `$PYTEST_CURRENT_TEST`; `failure` is the decision the per-test check in
`tests/conftest.py` makes over the lines a test added.

WHY THE PROBES ARE ANSWERED RATHER THAN REFUSED. They are how the machine row
and the installed command learn whether `gh` is there and logged in, and
nothing else. Answered as "present, not logged in" -- the state of a CI
runner, which exports no token -- the row is exercised by every doctor test,
says the same thing on every machine off Windows, and needs no flag in the
doctor to leave it out; there a logged-in operator gets the output CI gets. On
Windows the preflight's bare `gh` skips the guard's `gh.cmd`
(`tests/conftest.py`), so a doctor run there asks a real `gh.exe` where one is
installed, and the row reports what that `gh` says. "Not logged in" also stops
the preflight short of `gh api user`, its one call that would fetch something.
Refused, every doctor test would fail at teardown on calls the row is designed
to make. The answers are EXACTLY what the two callers parse and no more:
`program_version` (`setup-project.py`) reads the third word of the first line
of `gh --version`, and `_check_gh` there and `machine_report` in
`openRepoShape` read only the exit status of `gh auth status`. Any other argv
-- `gh version`, `gh auth status --hostname x` -- is not a probe and is
refused.

ONE MORE CALL IS ANSWERED (#798): `gh repo view <owner>/<name> --json
nameWithOwner`, which `adopt-project.py check` asks of each leg repository it
would create, as `execute` does before it makes either. Every `check` in this
suite that is given no `--local-remote-dir`, once nothing before it refuses and
the plan's names and `org:` pass, asks it twice, once of each leg, and refused,
each such test would fail. It is answered as a `gh` with no login answers it,
the state the other two answers describe: exit 4 and gh's own words
(`NEEDS_A_LOGIN`), so `check` prints, off Windows, the NOTE that it could not
ask, and still passes. On Windows a bare `gh` skips the guard's `gh.cmd`
(`tests/conftest.py`), and where a logged-in `gh.exe` is installed it answers
instead: no NOTE is printed, and GitHub is reached. It is logged as a probe.
Only that exact shape is answered: `--json name`, `--json visibility` or any
other field, and any other `repo view`, are refused. SO IT ANSWERS ADOPT'S CALL
ALONE: `scaffold-project.py` and `family.py` ask whether their own repositories
exist with `--json name`, so a test of either that reaches gh with no stub of
its own is still failed at teardown (`tests/test_gh_guard.py`).

STANDARD LIBRARY ONLY, and importable: `tests/conftest.py` and
`tests/test_gh_guard.py` read the same table, the same record format and the
same decision from here, so the guard and the check cannot disagree about
what a probe is.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

#: The exit status of a refused call: not 0, not 1 (a `gh` that failed), not
#: 4 (gh's own "authentication required"), and the number every logging
#: `gh` shim in this estate already exits with.
GUARD_EXIT = 97

#: The log, beside this file in the guard's directory. One JSON object per
#: line: `kind` (`probe` or `refused`), `argv` and `test`.
LOG_NAME = "gh-guard.log"

#: ONE line. Its third word is the version `program_version` reports, so the
#: preflight prints `[ok] gh test-guard`, and the rest says what answered.
VERSION_LINE = ("gh version test-guard (the openRepoShape test suite's gh "
                "guard, tests/conftest.py)")

#: gh's own words for a machine with no login, on stderr, exit 1. Nothing
#: parses them -- both callers read the exit status -- so they are gh's own
#: rather than invented ones.
NOT_LOGGED_IN = ("You are not logged into any GitHub hosts. To log in, run: "
                 "gh auth login")

#: THE TWO PROBES, as exact argv tuples, and the answer to each:
#: `(exit status, stdout, stderr)`.
PROBES = {
    ("--version",): (0, VERSION_LINE + "\n", ""),
    ("auth", "status"): (1, "", NOT_LOGGED_IN + "\n"),
}

#: gh's own words, on stderr with exit 4, for a command that needs a login on
#: a machine that has none (gh 2.x, outside CI): how `ASKS_WHETHER_IT_EXISTS`
#: is answered (#798).
NEEDS_A_LOGIN = (
    "To get started with GitHub CLI, please run:  gh auth login\n"
    "Alternatively, populate the GH_TOKEN environment variable with a GitHub "
    "API authentication token.")
NO_LOGIN_EXIT = 4

#: `repo view <owner>/<name> --json nameWithOwner`: one owner and one name, as
#: a plan names them (an `org:` GitHub would refuse, `a+b`, included), with no
#: space or further `/`, and no option.
ASKS_WHETHER_IT_EXISTS = re.compile(r"[^\s/-][^\s/]*/[^\s/]+")


def answer(argv) -> tuple | None:
    """`(exit status, stdout, stderr)` for a call the guard answers: one of
    the two `PROBES`, or whether a repository exists, as a `gh` with no
    login answers it (#798). None for anything else, which is refused."""
    argv = list(argv)
    probe = PROBES.get(tuple(argv))
    if probe is not None:
        return probe
    if (len(argv) == 5 and argv[:2] == ["repo", "view"]
            and argv[3:] == ["--json", "nameWithOwner"]
            and ASKS_WHETHER_IT_EXISTS.fullmatch(argv[2])):
        return NO_LOGIN_EXIT, "", NEEDS_A_LOGIN + "\n"
    return None


#: The refusal, ONE line on stderr. `{argv}` is the call as `shown` spells it.
REFUSAL = ("gh guard (tests/conftest.py): no test may run the operator's gh, "
           "so `gh {argv}` was refused and logged; a test that means to run "
           "gh puts a stub of its own ahead of the guard on PATH")


#: Every C0 control character, and DEL, spelled `\xNN` by `shown`.
_CONTROLS = {code: f"\\x{code:02x}" for code in (*range(32), 127)}


def is_probe(argv) -> bool:
    """Whether `argv` is a call the guard answers (`answer`): one of the two
    `PROBES`, exactly, or `repo view <owner>/<name> --json nameWithOwner`.
    """
    return answer(argv) is not None


def shown(argv) -> str:
    """`argv` shell-quoted, with every control character spelled `\\xNN`, so
    the refusal and the check's message each name a call on ONE line."""
    return shlex.join(argv).translate(_CONTROLS)


def record(argv, test: str) -> str:
    """The log line for one call: JSON, so an argument holding a newline or
    a tab stays inside its own line and cannot forge another one."""
    return json.dumps({"kind": "probe" if is_probe(argv) else "refused",
                       "argv": list(argv), "test": test})


def failure(lines) -> str | None:
    """The per-test check's decision over the log lines one test added: None
    when every one is a probe, else the message that fails the test.

    THE KIND IS RE-DERIVED FROM THE ARGV, never read from the line, so the
    check and the guard share one definition of a probe (`PROBES`). A line
    this file did not write -- not JSON, or no list of strings under `argv`
    -- FAILS the check rather than being skipped: a log nobody can read is
    not a log that proves nothing was called.
    """
    named = []
    for line in lines:
        try:
            entry = json.loads(line)
            argv, test = entry["argv"], entry.get("test", "")
            if not isinstance(argv, list) or \
                    not all(isinstance(word, str) for word in argv):
                raise TypeError(argv)
        except (ValueError, KeyError, TypeError, AttributeError):
            named.append(f"  a log line the guard did not write: {line!r}")
            continue
        if is_probe(argv):
            continue
        named.append(f"  gh {shown(argv)}    "
                     f"[{test or 'no $PYTEST_CURRENT_TEST'}]")
    if not named:
        return None
    return ("tests/conftest.py's gh guard logged "
            f"{len(named)} line(s) that are not a call it answers (the "
            "machine row's two probes, and `repo view <owner>/<name> --json "
            "nameWithOwner`) -- calls to gh made with no stub of the test's "
            "own ahead of the guard on PATH, each refused:\n"
            + "\n".join(named) + "\n"
            "No test may reach the operator's gh. A test that means to run "
            "gh puts a stub of its own first on PATH, as "
            "tests/test_neutral_pin_validator.py does.")


def main(argv) -> int:
    """Log the call, then answer a probe or refuse anything else."""
    log = Path(__file__).resolve().with_name(LOG_NAME)
    with open(log, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(record(argv, os.environ.get("PYTEST_CURRENT_TEST", ""))
                     + "\n")
    answered = answer(argv)
    if answered is not None:
        code, out, err = answered
        sys.stdout.write(out)
        sys.stderr.write(err)
        return code
    sys.stderr.write(REFUSAL.format(argv=shown(argv)) + "\n")
    return GUARD_EXIT


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
