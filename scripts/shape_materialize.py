#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Materialize an assembly root out of `templates/assembly-root/`.

ONE MATERIALIZER, TWO CALLERS. `scaffold-project.py` builds an assembly root
in an empty directory; `adopt-project.py` builds one INSIDE a repository that
already exists and keeps its history. Those differ in exactly two ways — what
to do when a template file collides with a file the source repository already
has, and whether a Makefile needs the adopted project's `CONTRACTS_DIR` line —
so they differ by two arguments rather than by a second copy of the code.

The alternative was a second copy, and a second copy is how `shape-pin.yaml`
starts digesting a different set of files than the scaffold writes.

STANDARD LIBRARY ONLY, like everything else shipped here.

WHAT A COLLISION IS, AND WHY IT IS NOT AN OVERWRITE. Adopting in place means
the source repository's own `README.md`, `Makefile` and `.gitignore` are
already at the root and are part of its history. The shape's copies of those
names are NOT more important than the project's, and silently overwriting one
would put a byte in the split commit that no `git rm` accounts for — which is
precisely what `adopt-project.py --verify` would then report as a mismatch.
So a colliding template file is written BESIDE the original under
`collision_dir` (`shape/`) and the collision is reported for the plan's
`follow_ups:`. The human merges it; the tool never guesses.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePath

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_shape import (  # noqa: E402
    CHAIN_RECORD_FIELD, NamingPolicy, Refusal, file_sha256,
)

SHAPE_REPOSITORY = "opensoft/openRepoShape"


def root_key(path: PurePath, root: PurePath) -> str:
    """How a file the materializer wrote is NAMED, relative to the root.

    One spelling for both readers of it: the `path:` of a
    `contracts/shape-pin.yaml` row, and the list of what was written that the
    chmod pass matches against the copy lists.

    POSIX, ALWAYS, AND ON EVERY PLATFORM. Pin rows are POSIX paths; on Windows
    `str()` of a relative Path uses backslashes, and a key that does not match
    its own row reports every file as drift — `update-shape.py` looks the row
    up in a table keyed by `scripts/bootstrap.py` and finds nothing, so every
    copy in a directory reads as `unmapped` and `apply` refuses to re-sync a
    project that has not drifted at all. The row is also what a human reads
    and what `validate-pins.py` resolves against the root, and `Path(root,
    row)` opens a forward-slash row on Windows perfectly well — so the one
    spelling that works everywhere is the POSIX one.
    """
    return path.relative_to(root).as_posix()


def write_lf(path: Path, text: str) -> None:
    """Write text with LF line endings, on every platform.

    EVERY materialized file goes through this. `contracts/shape-pin.yaml`
    digests the bytes these writes land on, so a CRLF translation on Windows
    would give the same template a different sha256 there — the pin would
    claim "these are the shape's files" and be false on one platform. The
    shape's output is byte-identical everywhere, which is what makes the
    digest mean anything.

    `Path.write_text` grew a `newline=` parameter in 3.10 and this standard
    runs on 3.9, so the write is spelled with `open` instead.
    """
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)

# ---------------------------------------------------------------------------
# The `reference:` an election followed, and why one default cannot serve
# ---------------------------------------------------------------------------
#
# The doctrine was ratified on 2026-09-02 and lives at openxFactory
# `docs/project-repo-schema.md`. Before that day it existed ONLY as the staged
# fragment, so the standard's own sentence is that "a project elected before
# that date recorded the staged fragment's path, and that is a valid reference
# for it". A single default therefore cannot be right for both: writing the
# ratified path into a project dated 2026-08-30 makes the manifest claim its
# election followed a document that did not yet exist on the day a human
# elected the shape — and the `reference:` is precisely the claim about which
# document that human read.
#
# So the DATE chooses, `--reference` still overrides, and neither tool has to
# remember the rule. `DEFAULT_REFERENCE` keeps its name and its value because
# it is what other modules import and what the ratified path is called; only
# the CHOOSING is new.

DEFAULT_REFERENCE = "openxFactory docs/project-repo-schema.md"
STAGED_REFERENCE = (
    "openxFactory ideation/staging/project-repo-schema/project-repo-schema.md"
)
#: The day `add-project-repo-schema` ratified. An election ON it followed the
#: ratified document; one strictly BEFORE it followed the staged fragment.
RATIFICATION_DATE = _dt.date(2026, 9, 2)


def election_date(elected_on: str) -> _dt.date:
    """`elected_on` as a date, or a refusal that names the flag.

    A date this cannot read is not one it will guess at: the guess would pick
    the reference, and the reference is a claim about a human's act.
    """
    try:
        return _dt.date.fromisoformat(str(elected_on))
    except ValueError as exc:
        raise Refusal(
            "election-date-malformed",
            f"--elected-on {elected_on!r} is not a date; it takes YYYY-MM-DD "
            "(and a plan file's `elected_on:` carries the same form)",
            "Remediation: re-run with a zero-padded ISO date, e.g. "
            "--elected-on 2026-09-02 — not 2026-9-2 and not a word like "
            "'yesterday'. The `reference:` the manifest records is chosen BY "
            "that date, so it has to be readable before anything is written.",
        ) from exc


def default_reference(elected_on: str) -> str:
    """The document an election on `elected_on` followed, absent an explicit
    `--reference`: the staged fragment before ratification, the ratified
    document on that day or after."""
    if election_date(elected_on) < RATIFICATION_DATE:
        return STAGED_REFERENCE
    return DEFAULT_REFERENCE

#: One name, used in three places below: the source path, the target path and
#: the chmod list. Spelling it three times is how the chmod list starts naming
#: a file the copy list no longer writes.
VALIDATE_NAMING = "scripts/validate-repository-naming.py"

#: Copied out of openRepoShape's OWN tree, so the project carries the standard
#: it was cut from rather than a link to it.
COPIED_FROM_SHAPE = (
    ("scripts/repo_shape.py", "scripts/repo_shape.py"),
    (VALIDATE_NAMING, VALIDATE_NAMING),
    ("contracts/repository-naming.yaml", "contracts/repository-naming.yaml"),
)
#: Copied VERBATIM out of the assembly-root template (no substitution).
COPIED_VERBATIM = (
    "scripts/validate-pins.py",
    "scripts/validate-manifest.py",
    "scripts/bootstrap.py",
    "Makefile",
    ".gitignore",
    # WHAT THIS PROJECT'S BYTES ARE, said by the project (2026-09-05, #51).
    # The pin digests these copies as they sit on disk, so a clone that
    # translated line endings on checkout would make every row false on
    # exactly one platform — Git for Windows installs `core.autocrlf=true` by
    # default. `setup-project.py` clones with `core.autocrlf=false` for the
    # run it controls; this file covers the next person to clone the finished
    # project, who never ran anything of ours. PINNED like the rest, because a
    # file that says what the bytes are is worth nothing if it can be edited
    # without the pin noticing.
    ".gitattributes",
    ".github/workflows/validate.yml",
    # The AGENT-FACING rules of the shape (2026-09-04). PINNED, and verbatim
    # for the same reason the validators are: the sentence "never edit a file
    # with a row in shape-pin.yaml" is worthless if the file saying it can be
    # edited. Verbatim also means it carries no `{{placeholders}}` — it names
    # "the paths `project.yaml` names" instead — because one byte of rendered
    # project detail would make every project's copy digest differently and
    # `update-shape.py` unable to say whether it had drifted.
    "AGENTS-shape.md",
)
#: Rendered from the template with `{{PLACEHOLDER}}` substitution. These are
#: NOT digest-pinned in the shape pin: they are this project's own content.
TEMPLATED = (
    "README.md",
    "project.yaml",
    "contracts/spec-pin.yaml",
    "contracts/code-pin.yaml",
    # The project's OWN assistant instructions: a one-line pointer at
    # `AGENTS-shape.md`, the three repositories, and then the project's own
    # text. Rendered rather than pinned on purpose — an upstream fix must
    # never overwrite what a project's agents are told about the project.
    "AGENTS.md",
    "CLAUDE.md",
    # shape-pin.yaml is rendered LAST, because its `files:` block digests the
    # copies above after they have been written.
)
#: Rendered only when the project DECLARES a neutral-product pin, and written
#: once per declared pin as `contracts/<product lowercased>-pin.yaml`.
NEUTRAL_PIN_TEMPLATE = "contracts/neutral-product-pin.yaml"
EXECUTABLE = ("scripts/validate-pins.py", "scripts/validate-manifest.py",
              "scripts/bootstrap.py", VALIDATE_NAMING)

# ---------------------------------------------------------------------------
# The FAMILY root's own lists (2026-09-04)
# ---------------------------------------------------------------------------
#
# A family is a HOLDER, not a project: no legs, no leg pins, no manifest
# validator, and no naming CLI — `validate-family.py` asks the naming policy
# the one question a family has. So it gets its own four lists rather than
# reusing the assembly root's with exceptions, because "the same list minus
# three entries" is a list that starts agreeing with neither.

FAMILY_TEMPLATED = (
    "README.md",
    "family.yaml",
    "AGENTS.md",
    "CLAUDE.md",
    # shape-pin.yaml is rendered LAST by the materializer, over the copies.
)
FAMILY_COPIED_VERBATIM = (
    "scripts/validate-family.py",
    "scripts/bootstrap.py",
    # The workstation utility (2026-09-09, #76): it clones each member BESIDE
    # the holder, on its tracking branch, and warns about the parent folder
    # without moving anything. Copied and pinned like the other two, which is
    # what carries it to an existing holder through `update-shape.py check` ->
    # `upstream-added` -> `apply --add scripts/siblings.py`.
    "scripts/siblings.py",
    "Makefile",
    ".gitignore",
    # The holder carries the same copy pin, so it carries the same statement
    # about its bytes, and for the same reason (2026-09-05, #51).
    ".gitattributes",
    ".github/workflows/validate.yml",
    # The holder's own agent-facing rules, pinned like the assembly root's and
    # for the same reason. It is a SEPARATE document rather than the same one:
    # a holder has no legs, no leg pins and no lockstep workflow refs, so half
    # of the assembly root's file would be instructions about things that are
    # not here — and a file that is right about the wrong repository is read
    # once and then not at all.
    "AGENTS-shape.md",
)
#: The family validator reads the naming policy through `repo_shape`, so those
#: two travel with it. It does NOT copy `validate-repository-naming.py`: the
#: family has one name to classify and asks the library directly.
FAMILY_COPIED_FROM_SHAPE = (
    ("scripts/repo_shape.py", "scripts/repo_shape.py"),
    ("contracts/repository-naming.yaml", "contracts/repository-naming.yaml"),
)
FAMILY_EXECUTABLE = (
    "scripts/validate-family.py",
    "scripts/bootstrap.py",
    "scripts/siblings.py",
)

PLACEHOLDER_RE = re.compile(r"\{\{[A-Z_]+\}\}")

#: The one line an existing assistant-instruction file needs, and the exact
#: bytes of the pointer the templated `AGENTS.md` opens with.
SHAPE_POINTER_LINE = ("Read AGENTS-shape.md first — the rules of this "
                      "repository's shape.")
#: The shape files whose collision follow-up is ADD A LINE, not MERGE
#: (2026-09-04). `contracts/path-classification.yaml`'s
#: `root-assistant-instructions` keeps a source's own `AGENTS.md`/`CLAUDE.md`
#: at the root because "it addresses the whole project", which is the same
#: reason the shape must not replace one: that file is what this project's
#: agents ALREADY read, and telling a human to "merge" two agent instruction
#: files is how the project's own instructions get lost inside the shape's.
ASSISTANT_INSTRUCTIONS = ("AGENTS.md", "CLAUDE.md")


def collision_follow_up(intended: str, actual: str) -> str:
    """The follow-up for ONE collision, in one place.

    Both callers say it: `adopt-project.py plan` PREDICTS the collisions from
    the plan's surviving root paths, and `execute` reports the ones that
    actually happened. Two spellings of the same instruction is how the plan a
    human approves stops matching the commit message they read afterwards.
    """
    if intended in ASSISTANT_INSTRUCTIONS:
        return (
            f"add the line `{SHAPE_POINTER_LINE}` to the existing {intended} "
            f"rather than replacing it with {actual}: {intended} is what this "
            "project's agents ALREADY read, and "
            "`contracts/path-classification.yaml` keeps it at the root "
            "(`root-assistant-instructions`) because it addresses the whole "
            f"project. Then delete {actual}. Nothing was overwritten.")
    return (
        f"merge {actual} into {intended}: the source repository already has "
        "that name, so the shape's copy was written beside it and NOTHING was "
        "overwritten")


#: Appended to the assembly root's Makefile by `adopt-project.py` ONLY. A
#: scaffolded project's legs are empty, so nothing reads across them yet; an
#: ADOPTED project's code leg holds tooling that used to read `contracts/`
#: from beside it and now reads it from the other leg through the root.
ADOPT_MAKEFILE_BLOCK = """
# --- adopted project: reading ACROSS the legs -------------------------------
# The spec leg owns `contracts/`; the code leg holds the tooling that reads
# them. Mounted here, `spec/contracts` is one relative path from `code/`, so
# the root exports it once and the code leg takes it from the environment
# rather than each script guessing at `../`.
CONTRACTS_DIR ?= $(CURDIR)/spec/contracts
export CONTRACTS_DIR

.PHONY: contracts-dir
contracts-dir:
\t@echo $(CONTRACTS_DIR)
"""


class CommandFailed(Exception):
    def __init__(self, args, cwd, code, output):
        super().__init__(" ".join(args))
        self.args_list = args
        self.cwd = cwd
        self.code = code
        self.output = output.strip()

    def loudly(self, what: str) -> str:
        where = f"    (in {self.cwd})\n" if self.cwd else ""
        return (
            f"REFUSED {what}. THE EXACT COMMAND WAS:\n"
            f"    {' '.join(self.args_list)}\n{where}"
            f"    exit {self.code}\n"
            f"--- output ---\n{self.output}\n--- end output ---"
        )


RULESET_HINT = """
If the organisation applies a ruleset requiring changes to arrive by pull
request, a direct push to the default branch is refused BY DESIGN and must not
be worked around. Two legitimate exits:

  (1) have an operator holding the bypass right seed the default branch once,
      then re-run this scaffold; or
  (2) push a seed BRANCH and open a pull request:
          git -C {work} push -u origin main:seed/scaffold
          gh pr create --repo {repo} --base main --head seed/scaffold \\
              --title 'Seed the {role} leg' --body 'Scaffolded shape.'

NOTHING has been rolled back. What already exists is listed above; delete it
by hand if you want a clean re-run.
"""


#: The ONLY programs anything here will execute. Every call is a fixed verb
#: with values from the command line as ARGUMENTS — never a shell string, so
#: `shell=False` keeps the arguments out of a shell — and this list keeps the
#: PROGRAM out of the caller's hands as well. The tools take a repository
#: name, a path and a commit from whoever runs them, including from an AI
#: assistant reading a plan file; the pair of constraints is what stops a
#: crafted value from becoming a command.
ALLOWED_PROGRAMS = ("git", "gh")


def check_program(args: list[str]) -> None:
    """Refuse to execute anything but the two tools this standard drives."""
    program = Path(args[0]).name if args else ""
    if program not in ALLOWED_PROGRAMS:
        raise Refusal(
            "program-not-allowed",
            f"refusing to execute {program!r}: this module runs only "
            + " and ".join(ALLOWED_PROGRAMS),
            "Remediation: this is a defect in the tool that built the command "
            "line, not in your invocation.")
    for argument in args:
        if not isinstance(argument, str):
            raise Refusal(
                "argument-not-a-string",
                f"a command argument is {argument!r}, not a string",
                "Remediation: this is a defect in the tool that built the "
                "command line.")


def run(args: list[str], cwd: Path | None = None, capture: bool = True) -> str:
    check_program(args)
    proc = subprocess.run(args, cwd=str(cwd) if cwd else None,
                          capture_output=capture, text=True, check=False)
    if proc.returncode != 0:
        raise CommandFailed(args, cwd, proc.returncode,
                            (proc.stderr or "") + (proc.stdout or ""))
    return (proc.stdout or "").strip()


#: `-F -` reads the message from STDIN. Every argument is then a literal, and
#: the one value a caller controls — the message, which carries a project's
#: display name and, in an adoption, every moved path out of a plan file —
#: never reaches the command line at all. `-m <message>` was safe too (there
#: is no shell, and the value sits after `-m`), but "safe because of where it
#: sits in argv" is an argument somebody has to re-derive every time they read
#: it, and not putting it there is one fewer thing to be right about.
COMMIT_COMMAND = ["git", "commit", "-q", "-F", "-"]


def env_commit(work: Path, message: str) -> None:
    """Commit with an identity that always resolves, reading the message
    from stdin.

    A scaffold that fails on a machine with no `user.email` configured fails
    for a reason that has nothing to do with the project being scaffolded, so
    a fallback identity is supplied rather than assumed.
    """
    env = dict(os.environ)
    for key, fallback in (("GIT_AUTHOR_NAME", "openRepoShape scaffold"),
                          ("GIT_COMMITTER_NAME", "openRepoShape scaffold"),
                          ("GIT_AUTHOR_EMAIL", "scaffold@openreposhape.invalid"),
                          ("GIT_COMMITTER_EMAIL", "scaffold@openreposhape.invalid")):
        env.setdefault(key, fallback)
        if not env.get(key):
            env[key] = fallback
    check_program(COMMIT_COMMAND)
    proc = subprocess.run(COMMIT_COMMAND, cwd=str(work), input=message,
                          capture_output=True, text=True, check=False, env=env)
    if proc.returncode != 0:
        raise CommandFailed(COMMIT_COMMAND, work, proc.returncode,
                            proc.stderr + proc.stdout)


def git_init_commit(work: Path, message: str, branch: str) -> str:
    run(["git", "init", "-q", "-b", branch, str(work)])
    run(["git", "add", "-A", "--", "."], cwd=work)
    env_commit(work, message)
    return run(["git", "rev-parse", "HEAD"], cwd=work)


# ---------------------------------------------------------------------------
# Commit trailers (2026-09-11, #111)
# ---------------------------------------------------------------------------
#
# WHAT WAS WRONG. `update-shape.py apply --branch` and `scripts/family.py
# bump` compose and write their own commits, and neither had any way to put a
# line on one. The lane-collision protocol wants `Lane: <name>` on every
# artifact a lane produces — the COMMIT included — and this estate's own
# convention adds `Co-Authored-By:`; four InkRouter re-pins landed on
# 2026-09-11 carrying neither, because both tools were run exactly as their
# own `NEXT` lines printed them and nothing in either wrote a trailer (#111).
# So both take a repeatable `--trailer`, and what a trailer IS, whether this
# host's git can be asked for one, and which environment variable names the
# lane are ONE implementation here rather than two that agree until they do
# not.
#
# AND NOT IN `scripts/repo_shape.py`, which is where this standard's other
# shared helpers sit. That file is a SHAPE COPY: the materializer below
# writes it into every assembly root and every family holder and
# `contracts/shape-pin.yaml` digests it — so one function added there would
# put an `upstream-changed scripts/repo_shape.py` row in front of every
# project in the estate on its next `update-shape.py check`, for a helper no
# project's own copy would ever call. `shape-doctor.py` makes exactly that
# argument about its own quoter. This module is in no copy list and is
# already imported by both tools that write these commits.

#: `<token>: <value>`, which is git's own trailer grammar narrowed to what a
#: tool can be handed on a command line: a token of letters, digits and
#: hyphens (`Co-Authored-By`), a colon, ONE space, and a value that is not
#: empty, is ONE line, carries no control character, and neither starts nor
#: ends in whitespace. Narrow BECAUSE THE VALUE ENDS UP IN A COMMIT MESSAGE
#: somebody else reads as a trailer: `git interpret-trailers` recognises a
#: block by exactly this shape, so a "trailer" missing the space after the
#: colon is a line that reads like one and is not.
#:
#: MATCHED WITH `.fullmatch`, AND THE CLASSES EXCLUDE EVERY CONTROL
#: CHARACTER, because "is ONE line" was neither (Copilot, PR #112).
#: `re.match` with a pattern ending in `$` stops just before a FINAL
#: NEWLINE, so `--trailer "Lane: x\n"` was accepted whole and the newline
#: went into the commit message and into argv -- a second line inside a
#: value, which is a trailer nobody passed. And `[^\n]` in the middle is not
#: "one line": it admitted `\r`, `\v` and `\f` as well, each of which some
#: reader renders as a line break of its own. `shape-doctor.py`'s
#: `quote_arg` learnt the `.fullmatch` half of this on PR #102, against
#: `"Atlas\n"`; this is the same defect one file along.
TRAILER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*: [^\s\x00-\x1f\x7f]"
                        r"(?:[^\x00-\x1f\x7f]*[^\s\x00-\x1f\x7f])?$")


def trailer_line(text: str) -> str:
    """One `--trailer` value, validated where argparse can refuse it.

    ARGPARSE'S OWN ERROR PATH RATHER THAN A `Refusal`, and deliberately: a
    malformed trailer is a malformed COMMAND LINE, which is the one class of
    mistake argparse already reports with the usage line beside it. Both
    exits are 2, so a caller scripting on the exit code sees no difference;
    what it buys is that `--trailer 'Lane xfactory-1'` is refused before the
    tool has read a repository, copied a byte or checked out a branch.
    """
    value = str(text)
    if not TRAILER_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(
            f"{value!r} is not a `<Key>: <value>` trailer. It needs a token "
            "of letters, digits and hyphens, a colon, ONE space, and a "
            "non-empty value that is one line, carries no control character "
            'and does not end in whitespace — e.g. "Lane: xfactory-1" or '
            '"Co-Authored-By: Someone <someone@example.invalid>"')
    return value


#: The git that learned `commit --trailer` (2.32, 2021-06-06). An older one
#: still has `git interpret-trailers`, but not the commit option — so on that
#: host the trailer is appended to the message TEXT instead, which produces
#: the same commit. See `commit_trailers`.
TRAILER_OPTION_SINCE = (2, 32)

#: `git version 2.43.0` on Linux, `git version 2.45.1.windows.1`, `git
#: version 2.39.3 (Apple Git-146)`. TWO numbers, because two answer the
#: question and the third field is spelled differently on all three
#: platforms; anchored, so a number from anywhere else in the line cannot be
#: read as a version.
GIT_VERSION_RE = re.compile(r"^git version (\d+)\.(\d+)")

#: Probed once per process; see `git_takes_trailer_option`.
_trailer_option: bool | None = None


def git_takes_trailer_option(version: str | None = None) -> bool:
    """Does THIS host's `git commit` take `--trailer`?

    PROBED ONCE AND CACHED. Both callers write ONE commit per run, so the
    cost is one `git --version` either way; what the cache buys is that a
    tool cannot answer the question twice and differently inside one run.

    `version` IS THE PARSE, EXPOSED. Passed a string it parses that and
    caches nothing, so both branches are assertable on any host — the same
    thing `shape-doctor.py`'s `platform=` argument does for its quoter, and
    for the same reason: a branch that only ever runs on one machine is a
    branch nothing checks.

    CONSERVATIVE ON PURPOSE: a version line this cannot parse, a `git` that
    is not on PATH, a probe that fails for any reason at all — all read as
    "no", and "no" is the path that works on every git there is.
    """
    global _trailer_option
    if version is not None:
        found = GIT_VERSION_RE.match(version.strip())
        return bool(found) and (int(found.group(1)),
                                int(found.group(2))) >= TRAILER_OPTION_SINCE
    if _trailer_option is None:
        try:
            _trailer_option = git_takes_trailer_option(
                run(["git", "--version"]))
        except (CommandFailed, Refusal, OSError):
            _trailer_option = False
    return _trailer_option


def commit_trailers(message: str, trailers=()) -> tuple[str, list[str]]:
    """`(message, extra git-commit arguments)` that put `trailers` at the END
    of the commit message, in the order given, on whichever git this is.

    TWO PATHS, ONE RESULT. With `--trailer` available, git appends each line
    itself through `interpret-trailers`, which is the implementation that
    knows where a trailer block goes. Without it, the lines are appended to
    the message text after one blank line — and the commit that comes out is
    byte-identical to the one the option produces, because that is all the
    option had left to do for a message whose last paragraph is prose.

    THE MESSAGE STILL ARRIVES ON STDIN either way (`-F -`; see
    `COMMIT_COMMAND`), and the trailers are literal arguments after it. Both
    callers already commit with EXPLICIT PATHSPECS, so the returned arguments
    go BEFORE the `--` that starts them.

    NO TRAILERS IS NO CHANGE AT ALL: the message is handed back as it came
    and the argument list is empty, which is what keeps every commit these
    tools have ever written byte-identical when nobody passes the flag.
    """
    lines = [str(line) for line in (trailers or ())]
    if not lines:
        return message, []
    if git_takes_trailer_option():
        return message, [part for line in lines
                         for part in ("--trailer", line)]
    body = message if message.endswith("\n") else message + "\n"
    return body + "\n" + "\n".join(lines) + "\n", []


#: The environment variable that names the LANE a run belongs to — the one
#: `lanes-edit.sh` already reads. Read in ONE place so a printed next command
#: and the commit it asks for cannot disagree about which lane is running.
LANE_ENV = "LANES_LANE"

#: What a lane name may be AND STILL SURVIVE BEING PASTED. A next command is
#: a line somebody copies into a shell, and the trailer inside it is quoted
#: by whoever prints it — so a name carrying a quote character would break
#: the very quoting it sits inside, in front of whoever pasted it. Rather
#: than guess which printer is asking, a name outside this alphabet gets NO
#: trailer offered on the printed line; `--trailer` typed by hand still takes
#: anything `TRAILER_RE` accepts. Today's lane names (`openreposhape-2
#: (openRepoShape-2)`) are inside it. No newline, tab or carriage return is
#: in it, which is the point of checking the RAW value below.
LANE_NAME_RE = re.compile(r"[A-Za-z0-9 ()._:/@+-]+")


def lane_trailer(env: dict | None = None) -> str | None:
    """`Lane: <name>` when the environment names a lane, else `None`.

    UNSET OR ALL WHITESPACE IS `None`, and a caller prints nothing for it —
    which is what makes every line this standard printed yesterday
    byte-identical today for everybody who is not in a lane.

    THE VALUE IS CHECKED RAW, AND STRIPPING ONLY RECOGNISES "no lane"
    (Copilot, PR #112). Checking a `.strip()`ed name meant
    `LANES_LANE="xfactory-1\n"` was offered as `Lane: xfactory-1` — a name
    the contract says is not offered, trimmed into one that is, silently. So
    the alphabet above is asked about the bytes the environment actually
    carries, and a value with whitespace around it is NOT a lane name:
    `TRAILER_RE` refuses a value that starts or ends in whitespace, and a
    printed line that offered a trailer this tool's own `--trailer` would
    then refuse is worse than a line that offers none. The ONE thing
    stripping decides is whether an all-whitespace variable means "no lane",
    which it does — that is `LANES_LANE=` spelled with a space in it.
    """
    raw = str((os.environ if env is None else env).get(LANE_ENV) or "")
    if not raw.strip() or not LANE_NAME_RE.fullmatch(raw):
        return None
    line = f"Lane: {raw}"
    return line if TRAILER_RE.fullmatch(line) else None


def lane_trailer_argument(quote=None, env: dict | None = None) -> str:
    """The ` --trailer <Lane: ...>` a printed next command carries, or `""`.

    `quote` IS THE CALLER'S OWN SPELLING FUNCTION, passed in rather than
    chosen here. `shape-doctor.py` hands over its platform-aware `quote_arg`,
    because every other value on those rows is spelled by that one function
    and a line half-quoted by two rules is a line no shell reads the way its
    writer meant. With none, the trailer is spelled inside double quotes —
    which is how `AGENTS.md`, `docs/cli.md` and the issue all write it, and
    is what `update-shape.py`'s own NEXT line, which quotes nothing, can
    carry without pretending to a quoting rule it does not have.

    ONE ARGUMENT, NOT TWO. `Co-Authored-By:` is the caller's to pass: it
    names a person or a model, which no environment variable knows, and a
    tool that invented one would be putting a name nobody chose on somebody
    else's commit.
    """
    line = lane_trailer(env)
    if not line:
        return ""
    spelled = quote(line) if quote else '"' + line + '"'
    return f" --trailer {spelled}"


def render(text: str, values: dict[str, str], source: str) -> str:
    out = text
    for key, value in values.items():
        out = out.replace("{{" + key + "}}", str(value))
    left = PLACEHOLDER_RE.findall(out)
    if left:
        raise Refusal("template-unsubstituted",
                      f"{source}: no value for {sorted(set(left))}",
                      "Remediation: this is a defect in the substitution table "
                      "of the tool you ran, not in your invocation.")
    return out


def copy_tree(src: Path, dst: Path, values: dict[str, str]) -> None:
    """Copy a template tree, substituting placeholders in every text file."""
    for path in sorted(src.rglob("*")):
        if path.is_dir():
            continue
        target = dst / path.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        write_lf(target, render(path.read_text(encoding="utf-8"), values,
                                str(path)))


def naming_block(policy: NamingPolicy, name: str, role: str,
                 pins, indent: str = "    ", chain=()) -> str:
    """The `naming:` block `project.yaml` records for one leg.

    It records the classification AND what was not chosen. A name in
    `<Domainx><Product>` form is a CLAIM of descent that needs a REFERENT
    (2026-09-02): with no declared pin on `open<Product>` the declared role
    wins, and the descendant form survives in `also_matches` so the next reader
    sees the overlap that was resolved rather than wondering whether anyone
    noticed it. WITH the pin the answer is `domain-descendant` in the declared
    `assembly` role, because a descendant may carry legs.

    An `open<Product>` root records the same shape for the same reason
    (2026-09-05): `form: neutral-product`, `role: assembly`,
    `also_matches: [project-leg/assembly]`. The form won and the role was
    ADDED to it, because a neutral product may elect the shape — and electing
    confers nothing, so the record is a layout, not a claim about neutrality.

    `chain` is the pin chain the project declares it reaches its referent
    through (2026-09-05) and is RECORDED here, under `referent_chain:`,
    because a chain that were re-derived on each read would be an inference
    rather than the declaration the classifier is meant to consult. Nothing
    here confers anything; it is a record.
    """
    found = policy.classify(name, role, pins, chain)
    lines = [
        f"{indent}naming:",
        f"{indent}  form: {found.family}",
        f"{indent}  role: {found.role or '~'}",
        f"{indent}  also_matches: [{', '.join(found.also_matches)}]",
    ]
    referents = policy.descendant_referents(name)
    if referents:
        # THESE TWO LINES FOLLOW THE FORM, not the family that won. They
        # record that the NAME also spells a claim of descent, and whether
        # that claim's referent is declared in this tree — regardless of
        # whether the classification actually asserts descent. So a neutral
        # product in `openx<Product>` form (`openxFactory`, `openxDox`) shows
        # the overlap here instead of hiding it, even though it classifies as
        # `neutral-product` and elects its own shape. The classification
        # itself is `form:` above, and only `form: domain-descendant` asserts
        # descent; these two lines are the record of what the SPELLING also
        # claims, not of what won.
        #
        # The CANONICAL spelling is what is recorded, whichever one is pinned.
        lines.append(f"{indent}  descendant_referent: {referents[0]}")
        lines.append(f"{indent}  referent_declared: "
                     + ("true" if found.referent.reached else "false"))
        if found.referent.chain:
            lines.append(f"{indent}  {CHAIN_RECORD_FIELD}: ["
                         + ", ".join(found.referent.chain) + "]")
    return "\n".join(lines)


def descendant_note(policy: NamingPolicy, name: str, role: str,
                    pins, chain=()) -> str | None:
    """The one line the plan prints when a name also matches the claim form."""
    found = policy.classify(name, role, pins, chain)
    if "domain-descendant" not in found.also_matches:
        return None
    referent = policy.descendant_referent(name)
    if found.referent.status == "broken":
        return (f"NOTE {name} also matches the descendant form; it is not a "
                f"descendant because {found.referent.reason}")
    return (f"NOTE {name} also matches the descendant form; it is not a "
            f"descendant because no pin on {referent} is declared — declare "
            f"`contracts/{referent.lower()}-pin.yaml` later if it becomes one, "
            f"or record the chain that reaches it")


class Materialized:
    """What `materialize_assembly_root` wrote, and where it had to write it.

    `shape_files` is the ordered list of paths the shape pin digests, at the
    paths they ACTUALLY landed on — a pin that names a path nothing is at is
    a refusal in `validate-pins.py`, and rightly.
    """

    def __init__(self) -> None:
        self.written: list[str] = []
        self.collisions: list[tuple[str, str]] = []
        self.shape_files: list[str] = []

    def follow_ups(self) -> list[str]:
        return [collision_follow_up(intended, actual)
                for intended, actual in self.collisions]


def materialize_assembly_root(shape_root: Path, target: Path,
                              values: dict[str, str], *,
                              collision_dir: str | None = None,
                              append: dict[str, str] | None = None,
                              neutral_pins: dict[str, dict] | None = None,
                              ) -> Materialized:
    """Write the assembly-root skeleton into `target`.

    `collision_dir` — where a template file goes when the target path is
    already taken. `None` means "there can be no collision" and a collision
    raises, which is the scaffold's case: it built the directory itself.

    `append` maps a template-relative path to text appended after rendering
    (the adopt tool's `CONTRACTS_DIR` block).

    `neutral_pins` maps a neutral product name to the values for its pin file,
    each rendered from `contracts/neutral-product-pin.yaml`.
    """
    return _materialize(
        shape_root, shape_root / "templates" / "assembly-root", target, values,
        templated=TEMPLATED, verbatim=COPIED_VERBATIM,
        from_shape=COPIED_FROM_SHAPE, executable=EXECUTABLE,
        collision_dir=collision_dir, append=append, neutral_pins=neutral_pins)


def materialize_family_root(shape_root: Path, target: Path,
                            values: dict[str, str]) -> Materialized:
    """Write the FAMILY-root skeleton into `target`.

    A THIRD CALLER OF THE ONE MATERIALIZER, and the reason it was worth
    generalising rather than copying: a family root carries the same copy pin
    an assembly root does — `contracts/shape-pin.yaml`, per-file sha256 rows
    over the copies, `commit` and `tree_sha256` for the revision they came
    from — so `update-shape.py` re-syncs one exactly as it re-syncs the other.
    A second implementation of the digest-writing loop is how the two would
    start disagreeing about which files are pinned.

    No collision directory: `family.py init` builds the directory itself (or
    reuses an EMPTY repository, which by definition collides with nothing).
    """
    return _materialize(
        shape_root, shape_root / "templates" / "family-root", target, values,
        templated=FAMILY_TEMPLATED, verbatim=FAMILY_COPIED_VERBATIM,
        from_shape=FAMILY_COPIED_FROM_SHAPE, executable=FAMILY_EXECUTABLE)


def _materialize(shape_root: Path, template_root: Path, target: Path,
                 values: dict[str, str], *, templated, verbatim, from_shape,
                 executable, collision_dir: str | None = None,
                 append: dict[str, str] | None = None,
                 neutral_pins: dict[str, dict] | None = None) -> Materialized:
    """The shared body. Four lists in, one `Materialized` out.

    The order is load-bearing and is the same for every root: templated files
    first, then the verbatim copies and the copies out of openRepoShape's own
    tree (those two are what the shape pin digests), then any neutral-product
    pins, then the executable bits, and LAST `contracts/shape-pin.yaml` —
    rendered over the paths the copies actually landed on, because a pin that
    names a path nothing is at is a refusal in the validator, and rightly.
    """
    result = Materialized()

    def place(rel: str, write) -> str:
        """Write `rel`, or, if it is taken, the same name under `collision_dir`."""
        path = target / rel
        if path.exists():
            if collision_dir is None:
                raise Refusal(
                    "materialize-collision",
                    f"{path} already exists and this materializer was given no "
                    "collision directory",
                    "Remediation: scaffold into an empty directory, or call "
                    "with collision_dir set (which is what adopt does).")
            actual = f"{collision_dir}/{rel}"
            result.collisions.append((rel, actual))
            path = target / actual
        path.parent.mkdir(parents=True, exist_ok=True)
        write(path)
        rel_written = root_key(path, target)
        result.written.append(rel_written)
        return rel_written

    for rel in templated:
        text = render((template_root / rel).read_text(encoding="utf-8"),
                      values, rel)
        text += (append or {}).get(rel, "")
        place(rel, lambda p, t=text: write_lf(p, t))
    for rel in verbatim:
        text = (template_root / rel).read_text(encoding="utf-8")
        text += (append or {}).get(rel, "")
        result.shape_files.append(
            place(rel, lambda p, t=text: write_lf(p, t)))
    for src, rel in from_shape:
        text = (shape_root / src).read_text(encoding="utf-8")
        result.shape_files.append(
            place(rel, lambda p, t=text: write_lf(p, t)))
    for product, pin_values in (neutral_pins or {}).items():
        rel = f"contracts/{product.lower()}-pin.yaml"
        text = render((template_root / NEUTRAL_PIN_TEMPLATE)
                      .read_text(encoding="utf-8"), {**values, **pin_values}, rel)
        place(rel, lambda p, t=text: write_lf(p, t))
    for rel in executable:
        actual = next((w for w in result.written if w.endswith(rel)), None)
        if actual:
            (target / actual).chmod(0o755)

    # The shape pin's `files:` block digests the copies just written, so it is
    # rendered LAST and over the paths they actually landed on.
    rows = "\n".join(f"  - path: {rel}\n    sha256: \"{file_sha256(target / rel)}\""
                     for rel in result.shape_files)
    text = render((template_root / "contracts" / "shape-pin.yaml")
                  .read_text(encoding="utf-8"),
                  {**values, "SHAPE_FILES": rows}, "contracts/shape-pin.yaml")
    place("contracts/shape-pin.yaml",
          lambda p, t=text: write_lf(p, t))
    return result


def copy_out(src: Path, dst: Path) -> None:
    """A byte copy that makes the parent directory first."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
