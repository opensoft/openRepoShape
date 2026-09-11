#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Is this repository compliant with openRepoShape, and what is missing?

    ./shape-doctor.py [--root <path>] [--json]       # default --root .
    ./shape-doctor.py --root <path> --placement-plan <file>
    openRepoShape --doctor [<path>]                  # the same, from anywhere

ONE COMMAND, ONE VERDICT, AND IT REIMPLEMENTS NOTHING. Brett Heap asked, on
2026-09-10: "what tools do we have to check a repo to make sure it is
compliant with openRepoShape?" -- and the honest answer was five of them, in
an order nobody had written down. `validate-repository-naming.py` classifies
the names; the project's OWN `scripts/validate-manifest.py` and
`scripts/validate-pins.py` are its pinned gate; `update-shape.py check` says
whether the copies have fallen behind the standard; a FAMILY holder runs
`scripts/validate-family.py` instead of the first two; and a directory
carrying neither manifest is not a shape root at all and wants
`adopt-project.py plan` or `setup.sh`. This runs them in sequence, prints one
row each, and then prints ONE verdict. Every row is somebody else's check.

WHAT IT NEVER DOES. It never writes into the repository it is pointed at and
it never fetches. ONE FLAG WRITES AT ALL, and it writes one file the caller
named and nothing else: `--placement-plan <file>`, below. The upstream a
project's copies are compared against is THE CHECKOUT THIS FILE IS RUN FROM,
which is the whole of why the verdict is offline: no clone, no authenticated
call, and the same answer on a machine that has never spoken to github.com.
It runs the project's own validators, which are offline by their own
contract. ONE ROW IS THE EXCEPTION AND IT IS NAMED: `machine` asks `gh` who
it is logged in as (`setup-project.py --preflight` runs `gh --version`, `gh
auth status` and `gh api user`), which `gh` answers by talking to its host. That row
is `n/a` by status and cannot move the verdict -- a workstation missing `gh`
is not a repository being non-compliant -- so nothing this command CONCLUDES
depends on a network, and a machine with no `gh` at all is reported rather
than refused.

THE CHECKS ARE A REGISTRY, not a function with eight paragraphs in it. Each
one is a `Check` -- an `id`, the root kinds it `applies_to`, a `run(ctx)` that
returns one `Row`, and a `fix` slot that is `None` for every check today. That
shape is deliberate: a repair mode is coming (put a repository back into the
correct three-leg version), and it hangs a repair off `fix` rather than
rewriting this file. A `--fix` that ever calls one does so only after printing
the plan and getting the human's yes, exactly like `update-shape.py apply`.

MANIFEST VALIDATION IS KEYED BY `kind:`. `MANIFEST_VALIDATORS` maps a
manifest's declared `kind:` -- `project-manifest`, `family-manifest`,
`pinned_contract_manifest`, the two policy kinds -- to the check that covers
it, and a `contracts/*.yaml` whose `kind` has no entry is a FINDING that says
so by name. A manifest nobody validates is the failure this whole standard is
against, and "we did not notice it was there" is how it happens; a future
inventory plugs in by adding one row to that table.

THE ROWS, for an assembly root, in this order:

    naming            the three leg names against the STANDARD's own
                      `contracts/repository-naming.yaml`
    manifest          the project's own `scripts/validate-manifest.py` when it
                      has one -- it is the pinned copy, and that is the point
                      -- else the standard's template copy, and the row says
                      which ran
    pins              the project's own `scripts/validate-pins.py` likewise:
                      the lockstep invariant, and the shape-copy digests
    manifest kinds    every `kind:`-bearing manifest in the root, against
                      MANIFEST_VALIDATORS
    shape currency    `update-shape.py check`'s per-file verdicts, summarised
    legs              each leg mounted, and its checked-out commit against the
                      pin (no fetch)
    leg shape files   each present leg's `AGENTS.md`, `CLAUDE.md` and
                      `.gitignore` against `templates/<role>-root/`
    placement         every tracked path of every leg, classified against
                      `contracts/path-classification.yaml`: code in the spec
                      leg, spec in the code leg, the root's own files in
                      either
    agent files       `AGENTS-shape.md`, `AGENTS.md`, `CLAUDE.md` at the root
    machine           whether this workstation can RUN the fixes named above
                      (`setup-project.py --preflight`, plus `git-filter-repo`)

and for a FAMILY holder: `family` (its own `scripts/validate-family.py`),
`manifest kinds`, `shape currency`, `placement` (`n/a`: a holder has no legs
of its own), `members` and `machine`. A directory that
is NEITHER gets `naming` (what it is called, under the policy), `what is
here`, `the way in` -- `adopt-project.py plan` for a repository that already
exists, `setup.sh` for a new one -- and `machine`.

THE PLACEMENT ROW ASKS THE ADOPTION'S QUESTION OF A REPOSITORY ALREADY
SPLIT. Brett Heap, 2026-09-10: "we have to look for code in spec and spec in
code". `adopt-project.py plan` decides which leg every path of an UNSPLIT
repository belongs in, from `contracts/path-classification.yaml`; this row
runs THE SAME POLICY over the legs of a project that has already been cut and
reports the paths it would have sent elsewhere. It imports that tool's own
`walk()` rather than carrying a second copy of the classification, so the
audit and the adoption cannot drift apart, and it costs one `git ls-files` per
leg and one process for the classifying -- a leg of several thousand files
answers in seconds.

WHAT THE PLACEMENT ROW IGNORES, AND IT SAYS SO. `README.md`, `AGENTS.md`,
`CLAUDE.md` and `.gitignore` classify as `root`, correctly, for a repository
being SPLIT -- exactly one of each stays in the assembly root. A leg is a
repository of its own afterwards and carries its own: `templates/spec-root/`
and `templates/code-root/` ship all four, so calling them misplaced would fail
every project this standard has ever cut. That half of the list is READ FROM
THOSE TEMPLATES at run time; the other half is `EVERYWHERE` below -- `LICENSE`,
`.gitattributes`, `CODEOWNERS`, `.github/**` and the rest of the forge
furniture, which every repository carries whatever is in it. `--json` prints
the whole list under `everywhere`, because what a report declined to look at
belongs in the report.

AND THE DOCTOR STILL MOVES NOTHING. A path changing legs is a pull request on
the leg it leaves, a pull request on the leg it joins, and one pin bump in the
assembly root -- a human's act, with a human's review. So the row's next
command is `--placement-plan <file>`, which writes the paths it found as an
adoption-plan-style YAML: `adopt-project.py plan`'s entries exactly, plus
`in_leg:` and an empty `resolution:`, so a person who has resolved an adoption
plan has already resolved this. It carries `kind: placement-plan` and NOT
`adoption-plan`, deliberately -- an adoption plan is the input to
`adopt-project.py execute`, which creates repositories and rewrites history,
and a file that called itself one would be that command aimed at a project
that is already split. A later `--fix --plan <file>` carries a RESOLVED plan
out, after printing what it will do and getting a typed yes.

A FINDING NAMES ITS FIX. Every row that is not `ok` carries the exact next
command, because a refusal that does not say what to run is a refusal the
reader improvises around -- which is the house rule the rest of this standard
is built on.

AND ONLY A `FINDING` MOVES THE VERDICT. A row is `ok`, `note`, `FINDING` or
`n/a`, and `FINDING` means exactly "something ELSE asserts this" -- a
validator, a pin row, a manifest, a gitlink. A difference nothing asserts is
a `note`: it is printed, it is in `--json`, and the verdict steps over it.
That line was drawn after this command printed `INVALID` over a live estate
whose every real gate was green, because a leg was missing a `.gitignore`
that entered the standard after the project was scaffolded. A doctor that
invents a rule to fail somebody by is not believed the next time.

EXIT CODES
    0  COMPLIANT: every row ok and the shape is current
    1  findings: the shape is behind, a copy has drifted, a validator is red,
       a leg is off its pin, or a tracked path sits in a leg the path policy
       puts elsewhere -- COMPLIANT SHAPE BEHIND, DRIFTED, MISPLACED, INVALID
    2  NOT A SHAPE ROOT: neither `project.yaml` nor `family.yaml` is there
    3  usage or environment -- nothing here is a statement about the tree
       that was pointed at: no such root, this file is not sitting in a
       checkout of the standard, or THIS CHECKOUT cannot answer (a pin
       naming a commit it does not carry)

THE VERDICT NAMES THE MOST SPECIFIC FINDING; THE TABLE NAMES EVERY ONE. Drift
outranks a red validator on that line for one concrete reason: an edited shape
copy is exactly what makes `validate-pins.py` red, so answering `INVALID
(validate-pins.py)` would send the reader at the symptom while the fix is
`update-shape.py`. The pins row is still printed, with its own next command.
MISPLACED sits between the two, under DRIFTED and over INVALID: a path in the
wrong leg is a fact about the SHAPE -- the subject of this whole standard --
that no validator, pin or manifest here can see, whereas a red validator names
itself in the table either way and loses nothing by not being on the verdict
line.

STANDARD LIBRARY ONLY, like everything else shipped here. Printed text is
ASCII: a verdict a cp1252 console cannot render is a verdict nobody reads, and
this tool is run on every platform the standard supports.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SHAPE_ROOT = Path(__file__).resolve().parent

#: NOT ONE `.pyc` ANYWHERE, and this line has to be BEFORE the first import
#: of anything beside this file. `PYTHONDONTWRITEBYTECODE=1` further down
#: covers the validators this runs as subprocesses; `repo_shape` below and
#: `update-shape.py` in `Context.update_shape` are imported IN PROCESS, and
#: they were leaving `__pycache__/` in the standard's own checkout. "It
#: writes nothing" is the first promise this file makes, and a caveat about
#: which directory would be a worse sentence than the fix.
sys.dont_write_bytecode = True
sys.path.insert(0, str(SHAPE_ROOT / "scripts"))

#: What the standard has to have around this file for any of this to mean
#: anything. `shape-doctor.py` compares a project against THE CHECKOUT IT IS
#: RUN FROM, so a copy of this one file on its own can answer nothing.
#:
#: SPELLED BEFORE THE FIRST IMPORT because the guard that reads it has to run
#: before one too -- see `not_in_the_standard`.
SHAPE_MARKERS = ("contracts/repository-naming.yaml",
                 "scripts/validate-repository-naming.py",
                 "templates/assembly-root", "update-shape.py")


def not_in_the_standard(detail: str) -> int:
    """The refusal for a `shape-doctor.py` that has no standard around it.

    IT IS A FUNCTION, AND IT IS DEFINED BEFORE THE FIRST IMPORT, because the
    single most obvious way to be "not in the standard" -- this one file
    copied out on its own -- used to be met by a ModuleNotFoundError
    traceback and exit 1. Exit 1 is this tool's code for "the repository has
    findings", so a caller scripting on it read an interpreter crash as a
    verdict about somebody's repository; and a traceback names no fix, which
    is the one rule every refusal in this standard keeps.
    """
    missing = [marker for marker in SHAPE_MARKERS
               if not (SHAPE_ROOT / marker).exists()]
    print(f"REFUSED shape-doctor-not-in-the-standard: this file is at "
          f"{SHAPE_ROOT}, which is missing "
          f"{', '.join(missing) if missing else detail}. shape-doctor.py "
          "compares a repository against THE CHECKOUT IT IS RUN FROM, so it "
          "needs one.\n  Remediation: run it from a clone of openRepoShape, "
          "or `openRepoShape --doctor <path>`, which fetches one for you.",
          file=sys.stderr)
    return 3


try:
    from repo_shape import (  # noqa: E402
        COMMIT_RE, NamingPolicy, PYTHON, Refusal, accepts_role, git_out,
        load_yaml, recorded_gitlink,
    )
except ImportError as exc:  # pragma: no cover - exercised as a subprocess
    sys.exit(not_in_the_standard(f"scripts/repo_shape.py ({exc})"))

try:
    #: The policy's own glob dialect, for the one list this file adds to it.
    #: `fnmatch` is not the same dialect -- its `*` crosses `/`, which would
    #: make `LICENSE.*` match `docs/LICENSE.html` -- and a second dialect
    #: beside a policy written in the first is a bug waiting for its file.
    from path_classify import glob_to_regex  # noqa: E402
except ImportError as exc:  # pragma: no cover - exercised as a subprocess
    sys.exit(not_in_the_standard(f"scripts/path_classify.py ({exc})"))

#: The statuses a row can carry, and only ONE of them moves the verdict.
#:
#: `n/a` is a question this ROOT does not have -- a family has no legs -- or,
#: for the `machine` row, one that is not about the root at all.
#:
#: `note` is a DIFFERENCE NOTHING ASSERTS. It was learnt the hard way: a leg
#: missing `.gitignore` made this command print `INVALID` over a live estate
#: whose every real gate was green, because `templates/spec-root/.gitignore`
#: entered the standard AFTER that project was scaffolded and no pin, no
#: validator and no manifest says a leg must carry one. A doctor that
#: invents a rule to fail somebody by is a doctor nobody believes the next
#: time. So a row says `note`, the reader sees the difference, and
#: `verdict_for` steps over it.
#:
#: `FINDING` is therefore exactly what something ELSE asserts -- a validator,
#: a pin row, a manifest, a gitlink -- and it is the only status that can
#: make this command exit non-zero about the repository.
OK = "ok"
NOTE = "note"
FINDING = "FINDING"
NA = "n/a"

#: Which kind of root this is. Read from the tree, never taken as a flag, the
#: same rule `update-shape.py`'s `root_kind` follows and for the same reason.
PROJECT = "project"
FAMILY = "family"
NOT_A_ROOT = "none"

#: The verdicts, in the order they outrank each other. See the docstring for
#: why DRIFTED sits above INVALID.
V_COMPLIANT = "COMPLIANT"
V_BEHIND = "COMPLIANT, SHAPE BEHIND"
V_DRIFTED = "DRIFTED"
#: A tracked path sits in a leg the path policy puts somewhere else. Under
#: DRIFTED and over INVALID -- see the docstring for why.
V_MISPLACED = "MISPLACED"
V_INVALID = "INVALID"
V_NOT_A_ROOT = "NOT A SHAPE ROOT"
#: Not a verdict about the repository at all: this CHECKOUT could not answer.
#: Exit 3, the documented "usage or environment", because nothing here is a
#: statement about the tree that was pointed at.
V_CANNOT_ANSWER = "CANNOT ANSWER"

#: The three files a scaffolded root carries for an agent. `AGENTS-shape.md`
#: is a PINNED shape copy, so the pins and shape-currency rows already digest
#: it; this row is for a reader, who wants to know whether the file is there
#: before reading two digest tables to find out.
AGENT_FILES = ("AGENTS-shape.md", "AGENTS.md", "CLAUDE.md")

#: The leg files this compares, and the ones a byte comparison is meaningless
#: for. `templates/<role>-root/AGENTS.md` and `README.md` carry
#: `{{PLACEHOLDER}}`s the scaffold renders per project, so "differs" is what
#: they are BY CONSTRUCTION; `CLAUDE.md` and `.gitignore` are verbatim and a
#: comparison of them is a fact. No leg file has a digest row anywhere today
#: -- only the assembly root's copies are pinned -- so this row reports and
#: does not judge, beyond a file that is missing altogether.
LEG_SHAPE_FILES = ("AGENTS.md", "CLAUDE.md", ".gitignore")
LEG_RENDERED = ("AGENTS.md", "README.md")

#: A tracked path this row can neither classify honestly nor write into a
#: plan. Git allows any byte but `/` and NUL in a name, so a file can carry a
#: newline, a control character, or a sequence that is not UTF-8 at all.
#: `surrogateescape` keeps those bytes readable as a Python string, but they
#: cannot be WRITTEN: a newline splits one plan entry across two lines of
#: YAML, and a surrogate raises `UnicodeEncodeError` in the writer -- a
#: traceback out of a command whose whole promise is that it reports. So such
#: a path is excluded from the classification and REPORTED by `repr`, which is
#: the only spelling that is safe in every output this command has (Copilot,
#: PR #100).
UNWRITABLE_IN_A_PLAN = re.compile(r"[\x00-\x1f\x7f\ud800-\udfff]")

#: The leg roles the `placement` row can judge. The path policy's classes are
#: `spec`, `code`, `root` and ambiguous, so a leg declaring any other role is
#: one this policy has no opinion about: it is recorded as unaudited and named
#: in the row, rather than guessed at against a class that does not exist.
LEG_ROLES = ("spec", "code")

#: What belongs to EVERY repository, so the `placement` row never calls it
#: misplaced in a leg.
#:
#: THE PATH POLICY HAS NO SUCH LIST, and this is the one place this row goes
#: beyond it. `contracts/path-classification.yaml` answers "which leg does
#: this path belong in when a repository is SPLIT", and under that question
#: `README.md` and `AGENTS.md` are `root` -- rightly, because the split leaves
#: exactly one of each in the assembly root. Afterwards a leg is a repository
#: of its own and carries its own, which is why `templates/spec-root/` and
#: `templates/code-root/` ship four of them; `everywhere_patterns` reads THOSE
#: at run time, so a template that gains a file needs no edit here and the
#: standard's own scaffold can never produce a finding.
#:
#: What is spelled here is the rest: the front door and the forge furniture,
#: which a repository carries whatever is inside it. `.github/**` is here
#: WHOLE and deliberately -- a leg runs its own CI, and
#: `.github/workflows/**` classifies as `code`, which would make every spec
#: leg with a lint workflow a finding.
EVERYWHERE = (
    "LICENSE", "LICENSE.*", "LICENCE", "NOTICE", "COPYING",
    "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "SECURITY.md", "SUPPORT.md",
    "CHANGELOG.md", ".gitattributes", ".editorconfig", ".mailmap",
    "CODEOWNERS", ".github/**",
)


def ascii_text(text: str) -> str:
    """`text` with the typography this repository is written in flattened.

    Validator output is quoted into rows, and this repository's prose is full
    of em dashes, curly quotes and ellipses. A Windows console in the machine's
    ANSI code page raises on the first of them, in the middle of a report whose
    whole job is to be read -- so the few characters that actually occur are
    spelled out and anything else is replaced rather than raised on.
    """
    for source, target in (("—", "--"), ("–", "-"), ("‘", "'"),
                           ("’", "'"), ("“", '"'), ("”", '"'),
                           ("…", "..."), (" ", " ")):
        text = text.replace(source, target)
    return text.encode("ascii", "replace").decode("ascii")


#: A value `sh` needs no quoting for: letters, digits, and the punctuation a
#: path, a flag, a commit id or a branch name is actually spelled with. `~` is
#: deliberately absent -- a leading one is expanded -- and so is every
#: character the shell reads as syntax.
UNQUOTED_POSIX = re.compile(r"^[A-Za-z0-9_./:@%+=,-]+$")
#: PowerShell's alphabet, and it is NOT the same one, which is the whole
#: reason there are two constants here. It GAINS the backslash a Windows path
#: is spelled with (the drive letter's colon is already admitted above) and it
#: LOSES two characters `sh` is indifferent to (Copilot, PR #102):
#:
#:   `,`  is PowerShell's list separator, so `C:\work,old\Atlas` bare is a
#:        value that may reach the command as something other than one
#:        argument;
#:   `@`  leading, is splatting syntax (`@args`), so a name like `@Atlas` is
#:        read as an expansion rather than as itself.
#:
#: `%` STAYS, and is named here so the next reader need not wonder: it is an
#: alias for `ForEach-Object` in COMMAND position only -- the first token of a
#: pipeline element -- and every value this file interpolates is an argument.
#: (`%VAR%` expansion is `cmd.exe`'s, and the Windows shell this standard
#: documents is PowerShell; see `setup-project.py`.)
UNQUOTED_NT = re.compile(r"^[A-Za-z0-9_./:%+=\\-]+$")


def quote_arg(value, platform: str | None = None) -> str:
    # A RAW docstring, because the Windows examples below are Windows paths:
    # `C:\Users\...` is a `\U` escape to the interpreter, and a docstring that
    # had to spell a reader's path with doubled backslashes would be a
    # docstring nobody could compare to what they see on screen.
    r"""One interpolated value, spelled so the READER'S shell hands it
    back whole.

    THE DEFECT WAS `--root {ctx.root}`, ON EVERY ROW SINCE #96. A root at
    `/srv/my projects/Atlas` produced a next command that argparse reads
    as three arguments and refuses -- in front of whoever pasted it, which is
    the exact failure `validator_row` already carries a comment about
    (`python3 validate-pins.py in <root>`, Copilot on PR #96). Copilot found
    it again on PR #100, against the placement row; it was never that row's,
    it was every row's.

    AND THE TWO SHELLS ARE NOT ONE DIALECT. PowerShell escapes an apostrophe
    inside a verbatim string by DOUBLING it and `sh` by closing, escaping and
    reopening -- and each reads the other's form as a different value with no
    error to say so: `sh` hands `'O''Brien'` on as `OBrien`, the apostrophe
    silently gone, and `\` is a literal character to PowerShell, whose escape
    is the backtick. A path is exactly where that bites, so one function knows
    both, and `platform` lets a test ask it for either on whichever host it is
    running on.

    `shlex.quote` COULD NOT BE THAT FUNCTION. Its own module is documented as
    designed for Unix shells only, so it carries no promise at all about the
    shell a Windows reader is in -- and since #49 this standard has a native
    Windows entry point and this file runs there by contract. Nor would its
    spelling do: `'C:\Users\Jane O'"'"'Neill\proj'` is a line a person is
    meant to RETYPE, on a machine whose stock shell is Windows PowerShell
    5.1 (see `setup-project.py`), where the same value is written
    `'C:\Users\Jane O''Neill\proj'`. A remediation nobody can read is the
    defect this whole file is against, one step along.

    IT QUOTES WHAT NEEDS IT AND NOTHING ELSE. A table whose whole job is to be
    read would be worse, not better, for `--root '/srv/work/Atlas'` on every
    line of every clean run, and a caller lifting a path back out of a `--json`
    `next` would have to strip quotes that were never load-bearing. So a value
    matching the platform's alphabet is returned unchanged and everything
    else is quoted whole. The two alphabets are not the same one: see
    `UNQUOTED_POSIX` and `UNQUOTED_NT`.

    IT LIVES HERE AND NOT IN `scripts/repo_shape.py`, which is where the
    standard's other platform-aware constant (`PYTHON`) sits. That file is a
    SHAPE COPY: `scripts/shape_materialize.py` writes it into every assembly
    root and every family holder, and `contracts/shape-pin.yaml` digests it --
    so one function added there would put an `upstream-changed
    scripts/repo_shape.py` row in front of every project in the estate on its
    next `update-shape.py check`, for a helper no project's own copy would
    ever call. `shape-doctor.py` is in no copy list, by its own contract: it
    compares a project against THE CHECKOUT IT IS RUN FROM, so the only file
    that builds these strings is the only file that carries the quoter. And
    `repo_shape.SAFE_PATH_RE` answers a different question anyway -- what may
    become an argument to `git`, where every command is a list run with
    `shell=False` and the threat is argument injection, not a shell.

    AND IT NORMALIZES BEFORE IT QUOTES, NOT AFTER. `Row.__init__` runs
    `ascii_text` again, over the WHOLE assembled `next_command`, once every
    value in it already sits quoted -- so a curly apostrophe that reached
    this function unconverted came out the far side of THAT pass as a bare,
    undoubled one, breaking the very quoting it sat inside (Copilot, PR
    #102): `'O'Neill'` is an unterminated quotation to `sh`, and an
    un-doubled apostrophe is exactly as broken to PowerShell's own verbatim
    string. Normalizing HERE first leaves that later pass nothing to touch:
    `ascii_text` maps this repository's own typography to ASCII, so calling
    it twice on an already-ASCII string is a no-op. What the reader then sees
    is the ASCII FLATTENING of their path rather than its own bytes -- which
    is this file's PURE ASCII rule, stated at the top and true of every other
    string in the report, and a command that names a path plainly and is
    refused by name beats one no shell will parse.

    AND THE ALPHABET CHECK MUST COVER THE VALUE WHOLE. `$` is content to
    match just before a trailing newline, so `.match` alone waved a value
    like `"Atlas\n"` through bare, newline and all -- true to the pattern
    and false to the point of it (Copilot, PR #102). `.fullmatch` is what
    actually requires every character to be in the alphabet, not only the
    ones before wherever `$` was willing to stop.
    """
    # ASCII first, so the alphabet check and the quoting below it both see
    # what `Row.__init__` will (Copilot, PR #102); see the docstring above.
    text = ascii_text(str(value))
    windows = (os.name if platform is None else platform) == "nt"
    # `.fullmatch`, not `.match`: a pattern ending in `$` still matches just
    # before a trailing newline, so `.match` alone would call "Atlas\n" bare
    # (Copilot, PR #102).
    if (UNQUOTED_NT if windows else UNQUOTED_POSIX).fullmatch(text):
        return text
    if windows:
        # PowerShell's verbatim string: nothing inside is expanded, and the
        # apostrophe is escaped by doubling it.
        return "'" + text.replace("'", "''") + "'"
    # `sh`'s: close the quote, escape one apostrophe, reopen. `shlex.quote`
    # spells the same meaning `'"'"'`; this is the form a person reading the
    # report can see through, and both come back out of `shlex.split` as the
    # value that went in -- which is what `tests/test_shape_doctor.py` asserts.
    return "'" + text.replace("'", "'\\''") + "'"


# ---------------------------------------------------------------------------
# A row, a check, and the registry they live in
# ---------------------------------------------------------------------------


class Row:
    """One line of the report: what was asked, the answer, and the exit."""

    def __init__(self, check_id: str, label: str, status: str, reason: str,
                 next_command: str | None = None, detail: dict | None = None):
        self.id = check_id
        self.label = label
        self.status = status
        self.reason = ascii_text(reason)
        # `quote_arg` ascii-normalizes every value it quotes BEFORE it
        # quotes it (Copilot, PR #102), so this pass has nothing left to do
        # to a `next_command` already built from it -- it only does its
        # ordinary job, flattening this repository's own typography, on the
        # literal words a caller wrote around those values.
        self.next_command = ascii_text(next_command) if next_command else None
        #: Structured facts for `--json`, so a caller reads numbers rather
        #: than parsing the sentence a human is meant to read.
        self.detail = detail or {}

    def as_dict(self) -> dict:
        return {"id": self.id, "label": self.label, "status": self.status,
                "reason": self.reason, "next": self.next_command,
                "detail": self.detail}


class Check:
    """One question this command knows how to ask.

    `fix` IS THE SLOT A REPAIR MODE HANGS OFF, and it is `None` for every check
    in this file today. A later `--doctor <path> --fix` calls it only after printing
    the plan
    and getting the human's yes -- the same posture `update-shape.py apply`
    takes, for the same reason: putting a repository back into shape rewrites
    somebody's tree.
    """

    def __init__(self, check_id: str, label: str, applies_to: tuple,
                 run, fix=None):
        self.id = check_id
        self.label = label
        self.applies_to = applies_to
        self.run = run
        self.fix = fix


class ManifestKind:
    """One `kind:` this standard knows a validator for.

    `covered_by` is the id of the CHECK that validates it, so the row about
    manifest kinds can say where a kind was answered rather than merely that
    it was recognised. A kind with no entry here is a FINDING by name: a
    manifest nobody validates is the gap this table exists to close.
    """

    def __init__(self, kind: str, covered_by: str, how: str):
        self.kind = kind
        self.covered_by = covered_by
        self.how = how


MANIFEST_VALIDATORS: dict[str, ManifestKind] = {
    "project-manifest": ManifestKind(
        "project-manifest", "manifest", "scripts/validate-manifest.py"),
    "family-manifest": ManifestKind(
        "family-manifest", "family", "scripts/validate-family.py"),
    "pinned_contract_manifest": ManifestKind(
        "pinned_contract_manifest", "pins",
        "scripts/validate-pins.py (or validate-family.py in a holder)"),
    "repository-naming-policy": ManifestKind(
        "repository-naming-policy", "naming",
        "scripts/validate-repository-naming.py, through NamingPolicy.load"),
    "path-classification-policy": ManifestKind(
        "path-classification-policy", "manifest-kinds",
        "scripts/path_classify.py reads it; nothing validates it in a root"),
}


# ---------------------------------------------------------------------------
# The context every check is handed
# ---------------------------------------------------------------------------


class Context:
    """The root, what it is, and the few things every check would recompute."""

    def __init__(self, root: Path):
        self.root = root
        self.shape = SHAPE_ROOT
        self.manifest_path: Path | None = None
        self.manifest: dict | None = None
        self.kind = NOT_A_ROOT
        self._update_shape = None
        self._adopt = None
        project = root / "project.yaml"
        family = root / "family.yaml"
        # `kind:` DECIDES, not the filename. A `project.yaml` that declares
        # something else is not a project manifest, and reading the name alone
        # would let a file called the right thing assert whatever it liked.
        if project.is_file() and self._declares(project, "project-manifest"):
            self.kind, self.manifest_path = PROJECT, project
        elif family.is_file() and self._declares(family, "family-manifest"):
            self.kind, self.manifest_path = FAMILY, family
        if self.manifest_path is not None:
            data = self._read(self.manifest_path)
            self.manifest = data if isinstance(data, dict) else None

    @staticmethod
    def _read(path: Path):
        try:
            return load_yaml(path)
        except (Refusal, OSError, UnicodeDecodeError):
            return None

    def _declares(self, path: Path, kind: str) -> bool:
        data = self._read(path)
        return isinstance(data, dict) and data.get("kind") == kind

    def legs(self) -> list[dict]:
        """The non-assembly legs `project.yaml` declares, in its own order."""
        return [leg for leg in ((self.manifest or {}).get("legs") or [])
                if isinstance(leg, dict) and leg.get("role") != "assembly"]

    def members(self) -> list[dict]:
        return [row for row in ((self.manifest or {}).get("members") or [])
                if isinstance(row, dict)]

    def update_shape(self):
        """`update-shape.py` as a module, loaded once.

        BY PATH, because the filename has a hyphen and cannot be imported by
        name -- the same reason `tests/test_repo_hygiene.py` loads
        `setup-project.py` that way. Importing it rather than shelling out to
        it is what gives this command the per-file verdicts instead of a
        screenful of somebody else's report to parse back.
        """
        if self._update_shape is None:
            path = self.shape / "update-shape.py"
            spec = importlib.util.spec_from_file_location(
                "openreposhape_update_shape", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self._update_shape = module
        return self._update_shape

    def adopt(self):
        """`adopt-project.py` as a module, or None when it is not here.

        BY PATH, for the same reason `update_shape` is: the filename has a
        hyphen in it. What the `placement` row wants from it is `walk()` --
        the recursive classify-and-fold that turns a file list into ONE entry
        per decision -- and `PathPolicy`, `y`, `emit` and `write_lf`, so that
        a placement plan is written by the same three functions that write an
        adoption plan and cannot come out in a dialect the reader of one
        would not recognise.

        NONE RATHER THAN A REFUSAL when the file is absent. `adopt-project.py`
        is not in `SHAPE_MARKERS` and must not join it: the other eight rows
        answer perfectly well without it, and a whole report refusing because
        one row's dependency is missing would be this command failing somebody
        for a gap in OUR checkout. The row says `n/a` and names the file.
        """
        if self._adopt is None:
            path = self.shape / "adopt-project.py"
            if not path.is_file():
                return None
            spec = importlib.util.spec_from_file_location(
                "openreposhape_adopt_project", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self._adopt = module
        return self._adopt


# ---------------------------------------------------------------------------
# Running somebody else's validator
# ---------------------------------------------------------------------------


def run_validator(ctx: Context, script: Path, args: list[str]) -> tuple:
    """`(exit code, first line worth quoting, whole output)`.

    THE PYTHONPATH IS THE POINT OF THE `env` BLOCK. A project's own
    `scripts/validate-pins.py` sits beside its own copy of `repo_shape.py` and
    imports it from there. The STANDARD's template copy has no `repo_shape.py`
    beside it -- that file is copied out of the shape itself, not out of the
    template -- so when this command falls back to the template it must put
    `<shape>/scripts` on the path or the fallback dies on an ImportError that
    says nothing about the project being checked.
    """
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    scripts = str(ctx.shape / "scripts")
    env["PYTHONPATH"] = (f"{scripts}{os.pathsep}{existing}" if existing
                         else scripts)
    # UTF-8 whatever the console is: these validators print this repository's
    # own prose, and `ascii_text` flattens it for the report afterwards.
    env["PYTHONIOENCODING"] = "utf-8"
    # AND NOT ONE BYTE INTO THE TREE. Running a project's own
    # `scripts/validate-pins.py` as a subprocess makes CPython write
    # `scripts/__pycache__/` beside it -- in somebody else's repository, from
    # a command whose first promise is that it writes nothing. A `.pyc` is
    # the interpreter's cache and not this tool's output, which is exactly
    # why it must not be left behind: nobody would look for it here.
    # `tests/test_shape_doctor.py::test_the_doctor_writes_nothing` is what
    # holds the promise, and it found this.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run([sys.executable, str(script), *args],
                          cwd=str(ctx.root), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False,
                          stdin=subprocess.DEVNULL, env=env)
    whole = (proc.stdout or "") + (proc.stderr or "")
    quoted = ""
    for line in whole.splitlines():
        stripped = line.strip()
        if stripped.startswith(("FINDING", "REFUSED", "WARNING")):
            quoted = stripped
            break
    if not quoted:
        lines = [line.strip() for line in whole.splitlines() if line.strip()]
        quoted = lines[-1] if lines else ""
    return proc.returncode, quoted[:200], whole


def validator_row(ctx: Context, check_id: str, label: str, own: str,
                  template: str, args: list[str]) -> Row:
    """One row for a validator that the ROOT may carry its own copy of.

    THE PROJECT'S OWN COPY FIRST, ALWAYS, AND THE ROW SAYS SO. That copy is
    the pinned one -- it is what the project's own gate runs, and running the
    standard's newer copy instead would answer a question nobody asked: not
    "does this project pass its gate" but "would it pass a gate it does not
    have". The template copy is the fallback for a root that has lost or never
    had one, and the row names which of the two answered.
    """
    own_path = ctx.root / own
    used, which = (own_path, f"the project's own {own}") if own_path.is_file() \
        else (ctx.shape / template, f"the standard's {template}")
    if not used.is_file():
        return Row(check_id, label, FINDING,
                   f"neither {own} nor {template} is readable, so the "
                   "question cannot be asked",
                   f"{PYTHON} "
                   f"{quote_arg(ctx.shape / 'shape-doctor.py')} --root "
                   f"{quote_arg(ctx.root)}   # from a complete checkout of "
                   "the standard; this one is missing that file",
                   {"validator": None})
    code, quoted, _ = run_validator(ctx, used, args)
    detail = {"validator": used.as_posix(), "own_copy": own_path.is_file(),
              "exit": code}
    if code == 0:
        return Row(check_id, label, OK, f"{which} passes", None, detail)
    verb = "refuses" if code >= 2 else "reports a finding"
    reason = f"{which} {verb} (exit {code})" + (f": {quoted}" if quoted else "")
    # A COMMAND THAT RUNS WHEN IT IS PASTED. This row used to print
    # `python3 validate-pins.py in <root>`, which is prose wearing a command's
    # clothes: `in` arrives as an argument and argparse refuses it. Every
    # validator here takes `--root`, so the runnable spelling is the absolute
    # path and that flag, and it needs no `cd` (Copilot, PR #96).
    spelled = " ".join(quote_arg(arg) for arg in args)
    return Row(check_id, label, FINDING, reason,
               f"{PYTHON} {quote_arg(used)} {spelled}   # read its output in "
               "full; it names what it refused", detail)


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------


def check_naming(ctx: Context) -> Row:
    """The leg names, against THE STANDARD's copy of the naming policy.

    The standard's rather than the project's on purpose: this command answers
    "is this compliant with openRepoShape", and openRepoShape is the checkout
    this file is in. A project whose copied policy is older is exactly the
    thing the shape-currency row is for, and it says so there.
    """
    script = ctx.shape / "scripts" / "validate-repository-naming.py"
    code, quoted, _ = run_validator(
        ctx, script, ["--project", str(ctx.root / "project.yaml"), "--quiet"])
    detail = {"policy": (ctx.shape / "contracts" /
                         "repository-naming.yaml").as_posix(), "exit": code}
    if code == 0:
        return Row("naming", "naming", OK,
                   "every leg name classifies, and each declared role agrees "
                   "with its form", None, detail)
    return Row("naming", "naming", FINDING,
               f"the naming policy is not satisfied (exit {code})"
               + (f": {quoted}" if quoted else ""),
               f"{PYTHON} {quote_arg(script)} --explain --project "
               f"{quote_arg(ctx.root / 'project.yaml')}", detail)


def check_manifest(ctx: Context) -> Row:
    return validator_row(
        ctx, "manifest", "manifest", "scripts/validate-manifest.py",
        "templates/assembly-root/scripts/validate-manifest.py",
        ["--root", str(ctx.root)])


def check_pins(ctx: Context) -> Row:
    return validator_row(
        ctx, "pins", "pins", "scripts/validate-pins.py",
        "templates/assembly-root/scripts/validate-pins.py",
        ["--root", str(ctx.root)])


def check_family(ctx: Context) -> Row:
    return validator_row(
        ctx, "family", "family", "scripts/validate-family.py",
        "templates/family-root/scripts/validate-family.py",
        ["--root", str(ctx.root)])


def manifest_candidates(root: Path) -> list[Path]:
    """Every file in a root that might DECLARE a `kind:`.

    The two manifests at the top, and everything under `contracts/`. Not the
    whole tree: a leg is its own repository with its own contracts, and a
    holder's `members/<Project>` is a whole project -- walking into either
    would make this command report on repositories it was not pointed at.
    """
    found = [root / "project.yaml", root / "family.yaml"]
    contracts = root / "contracts"
    if contracts.is_dir():
        found += sorted(p for p in contracts.iterdir()
                        if p.is_file() and p.suffix in (".yaml", ".yml"))
    return [path for path in found if path.is_file()]


def check_manifest_kinds(ctx: Context) -> Row:
    """Every `kind:`-bearing manifest in this root, against the registry.

    A YAML FILE WITH NO `kind:` IS NOT A MANIFEST and is skipped in silence:
    an adopted project's `contracts/policy.yaml` is its own business, and a
    tool that called every file it did not recognise a finding would be
    reporting on somebody else's data. What is reported is the other case --
    a file that DOES declare a kind that nothing here validates, which is a
    manifest travelling in a shape root with no gate behind it.
    """
    known: list[str] = []
    unknown: list[str] = []
    unreadable: list[str] = []
    for path in manifest_candidates(ctx.root):
        data = Context._read(path)
        if not isinstance(data, dict):
            unreadable.append(path.relative_to(ctx.root).as_posix())
            continue
        kind = data.get("kind")
        if not isinstance(kind, str) or not kind:
            continue
        rel = path.relative_to(ctx.root).as_posix()
        entry = MANIFEST_VALIDATORS.get(kind)
        (known if entry else unknown).append(f"{rel} ({kind})")
    detail = {"validated": known, "unregistered": unknown,
              "unreadable": unreadable,
              "registered_kinds": sorted(MANIFEST_VALIDATORS)}
    if unknown or unreadable:
        parts = []
        if unknown:
            parts.append("no validator registered for kind "
                         + ", ".join(unknown))
        if unreadable:
            parts.append("unreadable as YAML: " + ", ".join(unreadable))
        return Row("manifest-kinds", "manifest kinds", FINDING,
                   "; ".join(parts),
                   "register the kind in shape-doctor.py's "
                   "MANIFEST_VALIDATORS, beside the check that validates it, "
                   "or remove the file from the root", detail)
    return Row("manifest-kinds", "manifest kinds", OK,
               f"{len(known)} manifest(s), every declared kind has a "
               "registered validator", None, detail)


def check_shape_currency(ctx: Context) -> Row:
    """`update-shape.py check`, summarised, against THIS checkout.

    NO NETWORK AND NO CLONE. `update-shape.py` reads a local path as an
    upstream in place -- the same thing that makes its own tests offline -- so
    the shape this project is compared against is the checkout this file sits
    in, at its HEAD. What that costs is honesty about which standard answered,
    which is why both commits are in the row.
    """
    us = ctx.update_shape()
    args = argparse.Namespace(root=str(ctx.root), upstream=str(ctx.shape),
                              at=None)
    try:
        _root, _pin, rows, additions, upstream, pinned, target, _kind = \
            us.prepare(args)
    except Refusal as exc:
        # NOT A VERDICT ABOUT THE REPOSITORY. A pin naming a commit THIS
        # checkout does not carry -- a fork, a branch pin, a clone made
        # before the commit landed -- is this standard being unable to
        # answer, which is the documented meaning of exit 3. Labelling it
        # INVALID would tell somebody their repository is wrong on the
        # evidence that our copy of the standard is short a commit.
        return Row("shape-currency", "shape currency", FINDING,
                   f"the copies cannot be compared: {exc.detail}",
                   f"git -C {quote_arg(ctx.shape)} fetch --all   # this "
                   "checkout of the standard does not carry the commit the "
                   "pin names; fetch "
                   "it, or run the doctor from a clone that has it",
                   {"error": exc.code, "environment": True})
    try:
        added = [add for add in additions if not add.present]
        reported = list(rows) + added
        counts = us.counted(reported)
        summary = " / ".join(f"{counts.get(state, 0)} {state}"
                             for state in (us.UNCHANGED, us.UPSTREAM_CHANGED,
                                           us.LOCALLY_MODIFIED, us.BOTH,
                                           us.UPSTREAM_ADDED))
        by_state: dict[str, list[str]] = {}
        for row in reported:
            by_state.setdefault(row.state, []).append(row.path)
        conflicts = [row.path for row in rows if row.is_conflict]
        detail = {"pinned": pinned, "standard": target,
                  "counts": {state: counts.get(state, 0)
                             for state in us.ORDER if counts.get(state)},
                  "paths": by_state, "conflicts": conflicts,
                  "behind": bool(counts.get(us.UPSTREAM_CHANGED)
                                 or counts.get(us.UPSTREAM_ADDED)),
                  "drifted": bool(counts.get(us.LOCALLY_MODIFIED)
                                  or counts.get(us.BOTH) or conflicts)}
        where = f"pinned {pinned[:12]}, this standard {target[:12]}"
        moved = [row for row in reported if row.state != us.UNCHANGED]
        if not moved and pinned == target:
            return Row("shape-currency", "shape currency", OK,
                       f"the pin names this standard's commit; {summary} "
                       f"({where})", None, detail)
        if not moved:
            # A PIN THAT NAMES AN OLDER COMMIT IS BEHIND, even when not one
            # copied byte differs. COMPLIANT is documented as "every row ok
            # AND the pin names this standard's commit", and `update-shape.py
            # check` exits 1 here for the same reason — `apply` would move the
            # pin alone. Reporting `ok` would have made the verdict disagree
            # with the sentence defining it (Copilot, PR #96).
            detail["behind"] = True
            # WHICH KIND OF BEHIND, because the verdict line quotes counts
            # that are zero BY CONSTRUCTION on this branch -- it is only
            # reached when nothing differs -- and `(0 upstream-changed, 0
            # upstream-added)` under the words SHAPE BEHIND is a parenthetical
            # that contradicts its own verdict. It fires on both real estates
            # on this machine, so it is the common case and not an edge.
            detail["behind_pin_only"] = True
            return Row("shape-currency", "shape currency", FINDING,
                       "no copied file differs, but the pin names an older "
                       f"commit, so `apply` would move the pin alone; "
                       f"{summary} ({where})",
                       f"{PYTHON} "
                       f"{quote_arg(ctx.shape / 'update-shape.py')} check "
                       f"--root {quote_arg(ctx.root)} --upstream "
                       f"{quote_arg(ctx.shape)}   # then apply --at "
                       f"{quote_arg(target)} --yes --branch "
                       f"{quote_arg('shape/update-' + target[:12])}", detail)
        accept = "".join(f" --accept-local {quote_arg(row.path)}"
                         for row in rows
                         if row.state == us.LOCALLY_MODIFIED)
        named = ", ".join(row.path for row in moved[:4])
        if len(moved) > 4:
            named += f", and {len(moved) - 4} more"
        return Row("shape-currency", "shape currency", FINDING,
                   f"{summary} ({where}): {named}",
                   f"{PYTHON} "
                   f"{quote_arg(ctx.shape / 'update-shape.py')} check --root "
                   f"{quote_arg(ctx.root)} --upstream {quote_arg(ctx.shape)}"
                   f"   # then apply --at {quote_arg(target)} --yes{accept} "
                   f"--branch {quote_arg('shape/update-' + target[:12])}",
                   detail)
    finally:
        upstream.close()


def head_of(path: Path) -> str | None:
    try:
        return git_out(["rev-parse", "HEAD"], cwd=path).lower()
    except (Refusal, OSError):
        return None


def pin_commit(root: Path, relative: str) -> str | None:
    pin = Context._read(root / relative)
    if not isinstance(pin, dict):
        return None
    commit = str(pin.get("commit") or "").lower()
    return commit if COMMIT_RE.match(commit) else None


def check_legs(ctx: Context) -> Row:
    """Each leg mounted, and its checked-out commit against the pin.

    NOTHING IS FETCHED. The question is what is on this disk right now: an
    empty mount is a clone nobody bootstrapped, and a mount at another commit
    is a leg somebody moved -- both of which `make bootstrap` answers, and
    neither of which needs a remote to be asked about. The GITLINK against the
    pin file is `validate-pins.py`'s question and is left to it; this row
    reports the gitlink it found so the two can be read together.
    """
    legs = ctx.legs()
    if not legs:
        return Row("legs", "legs", NA,
                   "project.yaml declares no non-assembly leg; a "
                   "one-repository project has none and is not less governed "
                   "for it", None, {"legs": []})
    rows: list[dict] = []
    problems: list[str] = []
    for leg in legs:
        role = str(leg.get("role") or "?")
        rel = str(leg.get("path") or role)
        mount = ctx.root / rel
        pinned = pin_commit(ctx.root, f"contracts/{role}-pin.yaml")
        gitlink = recorded_gitlink(ctx.root, rel)
        populated = mount.is_dir() and any(mount.iterdir())
        head = head_of(mount) if populated else None
        entry = {"role": role, "path": rel, "pin": pinned,
                 "gitlink": gitlink, "populated": populated, "head": head}
        rows.append(entry)
        if gitlink is None:
            problems.append(f"{rel}: no gitlink recorded, so this leg is not "
                            "mounted as a submodule at all")
        elif not populated:
            problems.append(f"{rel}: the gitlink is there and the directory "
                            "is empty -- an unbootstrapped clone")
        elif head is None:
            problems.append(f"{rel}: populated, but git cannot read a HEAD in "
                            "it")
        elif pinned is None:
            problems.append(f"{rel}: contracts/{role}-pin.yaml carries no "
                            "40-hex commit to compare HEAD against")
        elif head != pinned:
            problems.append(f"{rel}: checked out at {head[:12]}, pinned at "
                            f"{pinned[:12]}")
    detail = {"legs": rows}
    if problems:
        return Row("legs", "legs", FINDING, "; ".join(problems),
                   f"{PYTHON} "
                   f"{quote_arg(ctx.root / 'scripts' / 'bootstrap.py')} "
                   f"--root {quote_arg(ctx.root)}   # what `make bootstrap` "
                   "runs: it puts every leg on its tracking branch AT the "
                   "pinned commit", detail)
    return Row("legs", "legs", OK,
               f"{len(rows)} leg(s) mounted and checked out at their pins",
               None, detail)


def copy_command(source, target, platform: str | None = None) -> str:
    r"""One file copied to one place, spelled for the READER'S SHELL.

    `cp` IS NOT A PROGRAM ON WINDOWS. It is an alias of `Copy-Item`, and the
    documentation says so in as many words -- "PowerShell includes the
    following aliases for `Copy-Item`: ... Windows: `cp`". So the line this
    row printed was never `cp` at all on the one platform this standard has
    a native entry point for (#49): it was a cmdlet, read by cmdlet rules.

    AND `Copy-Item -Path` DOES NOT TAKE A PATH, IT TAKES A PATTERN. Its own
    parameter reference reads "Wildcard characters are permitted", so `[`,
    `]`, `*` and `?` inside the value are SYNTAX to it -- and quoting cannot
    reach that, because quoting decides where the argument ENDS and the
    cmdlet decides how to read what arrived. A root at `C:\work[old]\Atlas`
    therefore gives a reader one of two outcomes from a line this file told
    them to run: `Cannot find path` for a directory that is plainly there,
    or -- where `[old]` is a character class with a sibling that matches, a
    `C:\workd\Atlas` next door -- A COPY OUT OF THE WRONG DIRECTORY, with
    nothing said. #102's quoter cannot fix it and is not wrong: that is
    tokenization, this is parameter semantics, one layer past it.

    `-LiteralPath` IS THE PARAMETER THAT MEANS "THIS PATH": "The value of
    LiteralPath is used exactly as it's typed. No characters are interpreted
    as wildcards." It is the whole repair, and the value still passes through
    `quote_arg` -- the two answer different questions, and a destination with
    a space in it needs the quoting exactly as much as a bracket needs the
    literal parameter.

    THE DESTINATION NEEDS NO TWIN AND HAS NONE. `Copy-Item` has no
    `-LiteralDestination`, and wants none: `-Destination` is documented
    "Supports wildcards: False" -- it names where the copy LANDS rather than
    searching for what to copy, so a `[` in it is already a character and
    not a class. It is passed through `quote_arg` for the same reason every
    other interpolated value is, and that is all it needs.

    POSIX KEEPS `cp`, unchanged and correct: there `cp` is `/bin/cp`, the
    shell does the globbing, and a single-quoted argument reaches it with
    every bracket intact. Two shells, two spellings, one function -- the
    shape `scaffold_command` already has, and `platform` is here for the
    same reason it is there: so BOTH lines are asserted byte for byte from
    whichever host the suite is running on, rather than the Windows half
    being exercised only where nobody is looking.

    AND `platform` IS PASSED ON, not merely branched on. `quote_arg(value)`
    with no platform reads the REAL host's `os.name`, so a Windows line
    built on a POSIX runner would be quoted by `sh` rules -- the function
    claiming a spelling it did not produce, which is the defect #103 names
    in the neighbouring `scaffold_command`. Here the argument is threaded
    through to every value, so what the test asserts is what a Windows
    reader gets.
    """
    if (os.name if platform is None else platform) == "nt":
        return (f"Copy-Item -LiteralPath {quote_arg(source, platform)} "
                f"-Destination {quote_arg(target, platform)}")
    return f"cp {quote_arg(source, platform)} {quote_arg(target, platform)}"


def check_leg_shape_files(ctx: Context) -> Row:
    """Each present leg's shape files against `templates/<role>-root/`.

    A COMPARISON, NOT A GATE. No leg file has a digest row anywhere today --
    `contracts/shape-pin.yaml` covers the assembly root's copies and nothing
    else -- so a leg whose `.gitignore` has grown a line is not thereby wrong,
    and saying it were would be a rule this standard has not made. What IS
    reported as a finding is a file that is not there at all, because a leg
    with no `AGENTS.md` is a leg an agent reads nothing in.

    `AGENTS.md` and `README.md` are RENDERED from their templates -- they
    carry `{{PLACEHOLDER}}`s the scaffold fills in -- so "differs" is their
    permanent state and the row says `rendered` rather than pretending a byte
    comparison meant something.
    """
    legs = ctx.legs()
    if not legs:
        return Row("leg-shape-files", "leg shape files", NA,
                   "no legs to compare", None, {"legs": []})
    per_leg: dict[str, dict] = {}
    missing: list[tuple[str, str, str]] = []
    for leg in legs:
        role = str(leg.get("role") or "?")
        rel = str(leg.get("path") or role)
        mount = ctx.root / rel
        template = ctx.shape / "templates" / f"{role}-root"
        if not (mount.is_dir() and any(mount.iterdir())):
            per_leg[rel] = {"role": role, "state": "not populated"}
            continue
        if not template.is_dir():
            per_leg[rel] = {"role": role,
                            "state": f"no templates/{role}-root/ to compare "
                                     "against"}
            continue
        files: dict[str, str] = {}
        for name in LEG_SHAPE_FILES:
            here, there = mount / name, template / name
            if not here.is_file():
                files[name] = "absent"
                missing.append((role, rel, name))
            elif name in LEG_RENDERED:
                files[name] = "rendered"
            elif not there.is_file():
                files[name] = "present (the template has none)"
            elif here.read_bytes() == there.read_bytes():
                files[name] = "identical"
            else:
                files[name] = "differs"
        per_leg[rel] = {"role": role, "state": "compared", "files": files}
    detail = {"legs": per_leg, "compared": list(LEG_SHAPE_FILES)}
    summary = "; ".join(
        f"{rel}: " + (entry["state"] if entry["state"] != "compared" else
                      ", ".join(f"{name} {state}"
                                for name, state in entry["files"].items()))
        for rel, entry in per_leg.items())
    if missing:
        named = ", ".join(f"{leg}/{file}" for _, leg, file in missing)
        # A COPY IS OFFERED ONLY FOR A FILE A COPY WOULD FIX -- `cp` for a
        # POSIX reader and `Copy-Item -LiteralPath` for a PowerShell one,
        # which is `copy_command`'s job (#105). The template's `AGENTS.md`
        # and `README.md` carry `{{PLACEHOLDER}}`s the scaffold
        # renders, so copying one verbatim leaves a leg holding literal
        # `{{PROJECT_NAME}}` — a command that produces an invalid leg is
        # worse than no command at all (Copilot, PR #96). For those the row
        # says what the file IS, and the repair is a human's until the repair
        # mode lands.
        copyable = [entry for entry in missing if entry[2] not in LEG_RENDERED]
        if copyable:
            role, rel, name = copyable[0]
            source = ctx.shape / "templates" / f"{role}-root" / name
            fix = copy_command(source, ctx.root / rel / name)
            if len(copyable) < len(missing):
                fix += ("   # and the rest are RENDERED per project "
                        "(placeholders): scaffold-project.py writes those, "
                        "and copying a template verbatim would not")
        else:
            fix = (f"the missing file(s) are RENDERED per project from "
                   f"templates/<role>-root/ — `{PYTHON} "
                   f"{quote_arg(ctx.shape / 'scaffold-project.py')} --help` "
                   "shows what writes them; copying a template verbatim "
                   "would leave "
                   "`{{PLACEHOLDER}}`s in the leg")
        # `note`, NOT `FINDING`. This is the row that printed `INVALID`
        # over a live estate whose every real gate was green, because
        # `templates/spec-root/.gitignore` entered the standard AFTER that
        # project was scaffolded. No pin names a leg file, no validator
        # asserts one, and the shape-currency row cannot even report it --
        # so every project cut before that template existed was failed by a
        # rule this standard never made. The difference is worth a reader's
        # eye and is not a verdict.
        return Row("leg-shape-files", "leg shape files", NOTE,
                   f"{summary}  (missing: {named})", fix, detail)
    return Row("leg-shape-files", "leg shape files", OK, summary, None, detail)


# ---------------------------------------------------------------------------
# Where a path LIVES, against where the path policy puts it
# ---------------------------------------------------------------------------


def everywhere_patterns(shape: Path) -> list:
    """`EVERYWHERE`, plus whatever the two leg templates themselves ship.

    READ FROM THE TEMPLATES, not listed a second time here, so that the
    standard's own scaffold can never write a leg this row then calls
    misplaced -- the files `templates/<role>-root/` puts in a leg are in a leg
    BY THIS STANDARD'S OWN HAND. Top-level files only: `spec-root/`'s
    `requirements/` and `code-root/`'s `src/` are leg CONTENT, and the policy
    classifies both of them correctly.
    """
    names = set(EVERYWHERE)
    for role in LEG_ROLES:
        template = shape / "templates" / f"{role}-root"
        if template.is_dir():
            names.update(entry.name for entry in template.iterdir()
                         if entry.is_file())
    return sorted(names)


def leg_tracked_files(mount: Path) -> list:
    """`(path, size)` for every TRACKED file in a leg, in ONE git call.

    `ls-files` reads the INDEX, which is exactly the question this row asks: a
    file staged into a leg is in that leg whether or not anybody has committed
    it yet, and what is on this disk right now is the doctor's subject in
    every other row too.

    THE SIZE IS AN `lstat`, NEVER A SUBPROCESS AND NEVER A FOLLOWED LINK.
    The plan records it, and one `git cat-file` per path would turn a leg of
    several thousand files into minutes of forking for a number nothing
    decides on. `lstat` rather than `stat` for two reasons that agree: a
    tracked symlink's BLOB is the target path it holds, so the link's own
    length is the honest size and the target's is a different file's; and
    `secret -> /outside/file` would otherwise have this row read metadata
    outside the very root `outside_the_root` keeps it inside of, and put that
    size in the report (Copilot, PR #100). A path in the index with nothing
    on disk reports zero rather than raising: it is somebody mid-`git rm`,
    and the classification of its NAME is unaffected.

    THE SECOND RETURN IS THE RESIDUE: the names this command cannot put in a
    report or a plan without breaking one, as `repr`. See
    `UNWRITABLE_IN_A_PLAN`.
    """
    raw = git_out(["ls-files", "-z"], cwd=mount, binary=True)
    out = []
    unwritable = []
    for record in raw.split(b"\x00"):
        if not record:
            continue
        path = record.decode("utf-8", "surrogateescape")
        if UNWRITABLE_IN_A_PLAN.search(path):
            unwritable.append(repr(path))
            continue
        try:
            size = (mount / path).lstat().st_size
        except OSError:
            size = 0
        out.append((path, size))
    return out, unwritable


def outside_the_root(root: Path, mount: Path) -> str | None:
    """Why this mount is not a directory of the repository being checked.

    `path:` COMES OUT OF `project.yaml`, WHICH THIS COMMAND DOES NOT OWN. An
    absolute path, a `..`, or a symlink makes `root / rel` a directory
    somewhere else entirely, and a `git ls-files` there would put another
    checkout's paths and sizes into this report and into the plan (Copilot,
    PR #100). The manifest validator has its own opinion about such a
    `path:`; this row must not act on it in the meantime.

    A leg mounted AT the root is refused by the same function and for the
    neighbouring reason: it is the assembly root's own repository, whose
    contents are the root's, and reading them as a leg's would call every
    file in the root misplaced.
    """
    try:
        here, base = mount.resolve(), root.resolve()
    except OSError as exc:
        return f"the mount cannot be resolved on this machine: {exc}"
    if here == base:
        return ("the manifest mounts this leg at the assembly root itself, "
                "whose contents are the root's and not a leg's")
    if base not in here.parents:
        return (f"the manifest points this leg outside {base}, and nothing "
                "outside the root that was named is read")
    return None


def not_its_own_repository(mount: Path) -> str | None:
    """Why `git ls-files` here would answer about somebody else's index.

    `git -C` DISCOVERS. Run in a plain directory it walks UP and answers from
    the enclosing repository, so a leg that is not a submodule at all would
    have the ASSEMBLY ROOT's index read as if it were the leg's contents
    (Copilot, PR #100). The `legs` row already reports a missing gitlink with
    `make bootstrap` beside it; this one simply declines to guess.
    """
    try:
        top = Path(git_out(["rev-parse", "--show-toplevel"], cwd=mount))
    except (Refusal, OSError):
        return ("it is not a git repository, so it has no tracked paths of "
                "its own to read")
    try:
        if top.resolve() == mount.resolve():
            return None
    except OSError as exc:  # pragma: no cover - a path git named and we cannot
        return f"git named a top level this machine cannot resolve: {exc}"
    return (f"it is not a repository of its own -- `git` answers from "
            f"{top.as_posix()} -- so `ls-files` there would report that "
            "repository's paths, not this leg's")


def named_offenders(rows: list) -> str:
    """The first three PER DIRECTION, and every direction's total.

    Per direction rather than three overall: "code in the spec leg" and "spec
    in the code leg" are two different mistakes with two different repairs,
    and a reason that showed three of the first and none of the second would
    hide half of what the row found.
    """
    grouped: dict = {}
    for row in rows:
        grouped.setdefault(row["direction"], []).append(row)
    named = []
    totals = []
    for direction, items in grouped.items():
        line = "; ".join(
            f"{item['path']}: {item['classified_as'] or 'ambiguous'} by rule "
            f"{item['rule']}" for item in items[:3])
        if len(items) > 3:
            line += f"; and {len(items) - 3} more"
        named.append(line)
        totals.append(f"{len(items)} {direction}")
    return "; ".join(named) + " (" + ", ".join(totals) + ")"


def placement_row(status: str, reason: str, next_command=None,
                  detail=None) -> Row:
    """One `placement` row with the `--json` keys ALWAYS present.

    A caller reads `detail.misplaced` and `detail.review_required`; a row that
    omitted them on the `n/a` branches would make every consumer write the
    same `or []` this writes once.
    """
    base = {"policy": None, "everywhere": [], "legs": [],
            "misplaced": [], "review_required": [],
            "counts": {"misplaced": 0, "review_required": 0}}
    base.update(detail or {})
    return Row("placement", "placement", status, reason, next_command, base)


def audit_leg(adopt, policy, patterns: list, role: str, rel: str,
              root: Path) -> tuple:
    """ONE leg: its summary, the paths in the wrong leg, and the questions.

    Split out so the row above reads as three sentences rather than one loop
    with six ways out of it -- and because a leg that cannot be audited has to
    say WHICH of the reasons it is, beside the legs that could.

    EVERY EARLY RETURN IS A LEG THIS ROW DECLINES TO GUESS ABOUT, and the
    caller must not read any of them as a clean leg: `check_placement` says
    `note` rather than `ok` while one is there, because "every tracked path
    classifies as the leg it is in" is not a claim to make about a leg nobody
    read (Copilot, PR #100).
    """
    entry = {"role": role, "path": rel}
    mount = root / rel
    escaped = outside_the_root(root, mount)
    if escaped:
        entry["state"] = escaped
        return entry, [], []
    if not (mount.is_dir() and any(mount.iterdir())):
        # The `legs` row already reports this, with `make bootstrap` beside
        # it. Here it is only why this leg has no answer.
        entry["state"] = "not populated"
        return entry, [], []
    if role not in LEG_ROLES:
        entry["state"] = (f"role {role} is not one that the path policy "
                          "classifies")
        return entry, [], []
    borrowed = not_its_own_repository(mount)
    if borrowed:
        entry["state"] = borrowed
        return entry, [], []
    try:
        files, unwritable = leg_tracked_files(mount)
    except Refusal as exc:
        entry["state"] = f"git could not list it: {exc.detail}"
        return entry, [], []
    entry["unwritable"] = unwritable
    kept = [(path, size) for path, size in files
            if not any(regex.match(path) for regex in patterns)]
    walked = adopt.walk(policy, kept)
    misplaced: list = []
    review: list = []
    for found in walked:
        row = {
            "path": f"{rel}/{found.path}",
            "leg": role,
            "path_in_leg": found.path,
            "classified_as": found.leg,
            "rule": found.rule,
            "reason": found.reason,
            "confidence": found.confidence,
            "question": found.question,
            "files": found.files,
            "bytes": found.bytes,
            "review_required": found.leg is None,
            "direction": (f"{found.leg} in the {role} leg" if found.leg
                          else f"unclassified in the {role} leg"),
        }
        if found.leg is None:
            review.append(row)
        elif found.leg != role:
            misplaced.append(row)
    # FILES AND PATHS ARE DIFFERENT NUMBERS and the row prints both. `walk`
    # folds a directory whose files agree into ONE entry, so `src/` with two
    # hundred files under it is one PATH and two hundred FILES -- and a reason
    # that reported only one of them would either bury the size of the problem
    # or overstate the number of decisions in it.
    entry.update({"state": "audited", "tracked": len(files),
                  "classified": len(kept), "paths": len(walked),
                  "misplaced": len(misplaced),
                  "review_required": len(review)})
    return entry, misplaced, review


def check_placement(ctx: Context) -> Row:
    """Every tracked path of every leg, against the ADOPTION'S own policy.

    THE QUESTION IS BRETT HEAP'S, 2026-09-10: "we have to look for code in
    spec and spec in code". `adopt-project.py plan` already answers which leg
    a path belongs in, for a repository being split, out of
    `contracts/path-classification.yaml`; this row asks the same policy the
    same question about a project that is ALREADY split, one leg at a time,
    and reports every path the policy would have put somewhere else.

    IT REIMPLEMENTS NOTHING, like every other row here. The classification is
    `PathPolicy`, the walk is `adopt-project.py`'s `walk()`, and the folding
    of a directory whose files all agree into ONE entry is that walk's --
    which is why `src/` with two hundred files under it in the spec leg is one
    line of this report and one entry of the plan, rather than two hundred of
    each. A second copy of that logic here would answer differently from the
    adoption the day one of them was fixed.

    THREE THINGS ARE COUNTED AND THEY ARE NOT THE SAME THING. A path the
    policy classifies as the OTHER leg is a FINDING: code in the spec leg,
    spec in the code leg. So is one it classifies as `root` -- `.specify/`
    inside a leg is the 2026-09-02 ruling's exact counter-example -- minus
    what belongs to every repository, which is `everywhere_patterns` and is
    printed. A path the policy cannot CALL carries `review_required` and is a
    `note`: it is a question for a human, and this standard's rule is that an
    unanswered question is never a finding and never an implicit anything.

    AND NOTHING MOVES. The row's next command writes a plan; the plan is the
    human's to resolve and a later `--fix` is the thing that would carry it
    out. A row that offered a `git mv` would be offering to edit two
    repositories from a command documented as writing nothing.
    """
    if ctx.kind == FAMILY:
        return placement_row(
            NA,
            "a family holder has no legs of its own: each member is an "
            "assembly root and answers this in its own report")
    legs = ctx.legs()
    if not legs:
        return placement_row(
            NA,
            "project.yaml declares no non-assembly leg, so there is no leg "
            "for a path to be in the wrong one of")
    adopt = ctx.adopt()
    policy_path = ctx.shape / "contracts" / "path-classification.yaml"
    if adopt is None or not policy_path.is_file():
        missing = ("adopt-project.py" if adopt is None
                   else "contracts/path-classification.yaml")
        return placement_row(
            NA,
            f"this checkout of the standard is missing {missing}, so the "
            "adoption's own classification cannot be run over the legs",
            f"{PYTHON} {quote_arg(ctx.shape / 'shape-doctor.py')} --root "
            f"{quote_arg(ctx.root)}   # from a COMPLETE checkout of the "
            f"standard; this one is short {missing}",
            {"policy": policy_path.as_posix()})
    try:
        policy = adopt.PathPolicy.load(policy_path)
    except Refusal as exc:
        # `n/a`, NOT a finding. A path policy this checkout cannot read is
        # OUR file being wrong, and failing somebody's repository on it would
        # be the `leg shape files` mistake with a different file.
        return placement_row(
            NA,
            f"the standard's own path policy could not be read: {exc.detail}",
            exc.remediation or None, {"policy": policy_path.as_posix()})

    ignored = everywhere_patterns(ctx.shape)
    patterns = [glob_to_regex(pattern) for pattern in ignored]
    per_leg = []
    misplaced = []
    review = []
    for leg in legs:
        role = str(leg.get("role") or "?")
        rel = str(leg.get("path") or role)
        entry, wrong, unsure = audit_leg(adopt, policy, patterns, role, rel,
                                         ctx.root)
        per_leg.append(entry)
        misplaced.extend(wrong)
        review.extend(unsure)

    detail = {"policy": policy_path.as_posix(), "everywhere": ignored,
              "legs": per_leg, "misplaced": misplaced,
              "review_required": review,
              "counts": {"misplaced": len(misplaced),
                         "review_required": len(review)}}
    unread = [entry for entry in per_leg if entry.get("state") != "audited"]
    unwritable = [name for entry in per_leg
                  for name in (entry.get("unwritable") or [])]
    detail["counts"]["unread_legs"] = len(unread)
    detail["counts"]["unwritable_names"] = len(unwritable)
    audited = "; ".join(
        f"{entry['path']}: " + (
            f"{entry['paths']} path(s) over {entry['classified']} of "
            f"{entry['tracked']} tracked file(s)"
            + (f", and {len(entry['unwritable'])} name(s) no report or plan "
               f"can carry: {', '.join(entry['unwritable'][:3])}"
               if entry.get("unwritable") else "")
            if entry.get("state") == "audited" else str(entry.get("state")))
        for entry in per_leg)
    if len(unread) == len(per_leg):
        # NOT `ok` AND NOT A FINDING. Every leg declined for a reason the
        # `legs` row already asserts or the manifest already carries, and a
        # row that answered `ok` here would be answering about nothing.
        return placement_row(
            NA, f"no leg could be read, so nothing was classified: {audited}",
            None, detail)
    plan = (f"{PYTHON} {quote_arg(ctx.shape / 'shape-doctor.py')} --root "
            f"{quote_arg(ctx.root)} "
            "--placement-plan placement-plan.yaml   # writes the paths above "
            "as a plan to resolve by hand. Moving one is a pull request on "
            "each leg and a pin bump in the root, so this command makes "
            "neither")
    if misplaced:
        extra = (f"; {len(review)} more path(s) need a human's reading"
                 if review else "")
        return placement_row(
            FINDING,
            f"{len(misplaced)} path(s) sit in a leg the policy puts "
            f"elsewhere: {named_offenders(misplaced)}{extra}  [{audited}]",
            plan, detail)
    if review:
        return placement_row(
            NOTE,
            f"nothing is in the wrong leg; {len(review)} path(s) the policy "
            f"will not call: {named_offenders(review)}  [{audited}]",
            plan, detail)
    if unread or unwritable:
        # `note`, because what is missing is a READ and not a fault of this
        # repository's -- and never `ok`, because "every tracked path
        # classifies as the leg it is in" is a claim about paths nobody read.
        return placement_row(
            NOTE,
            "nothing is in the wrong leg in what could be read, and not "
            f"everything could be: {audited}",
            None, detail)
    return placement_row(
        OK, f"every tracked path classifies as the leg it is in: {audited}",
        None, detail)


#: The header of the file `--placement-plan` writes. It is long because the
#: file is EDITED by somebody who may never have seen one, and because the
#: single most expensive mistake available here -- handing it to
#: `adopt-project.py execute` -- is one the header can talk them out of.
PLACEMENT_PLAN_PREAMBLE = (
    "# Written by `shape-doctor.py --placement-plan`. IT IS MEANT TO BE",
    "# EDITED, and it is NOT an adoption plan: the `kind:` above differs so",
    "# that `adopt-project.py execute` -- which creates two repositories and",
    "# rewrites history -- can never be handed one of these by mistake. The",
    "# ENTRIES are an adoption plan's entries exactly, so a reader who has",
    "# resolved one of those has already resolved this one.",
    "#",
    "# EVERY ENTRY SAYS A TRACKED PATH IS IN THE WRONG REPOSITORY.",
    "#   in_leg:     the leg it is in today.",
    "#   leg:        where contracts/path-classification.yaml puts it, and",
    "#               EDITABLE: setting it back to the value of `in_leg` is",
    "#               how you record that the policy is wrong about this path.",
    "#               `null` with a `question:` is the policy saying it does",
    "#               not know, and an unanswered question is never an",
    "#               implicit anything.",
    "#   rule:       the rule id that decided it, so you disagree with a",
    "#               NAMED rule rather than with an opaque verdict.",
    "#   resolution: empty on every entry, and the human's line.",
    "#",
    "# NOTHING HERE HAS MOVED AND THIS FILE MOVES NOTHING. A path changing",
    "# legs is a pull request on the leg it leaves, a pull request on the leg",
    "# it joins, and one pin bump in the assembly root. A later",
    "# `shape-doctor.py --fix --plan <this file>` will carry a RESOLVED plan",
    "# out that way, printing what it will do and asking first. Until it",
    "# lands, the moves are yours.",
)


def placement_plan_text(ctx: Context, adopt, row: Row) -> str:
    """The placement row's paths, as the YAML a human resolves.

    WRITTEN WITH THE ADOPTION'S OWN EMITTERS. `y` and `emit` write the exact
    subset `repo_shape.parse_yaml` reads back, and an adoption plan is written
    by them too -- so these two files are the same dialect by construction
    rather than by somebody remembering to keep them so.
    """
    detail = row.detail
    entries = sorted(list(detail.get("misplaced") or [])
                     + list(detail.get("review_required") or []),
                     key=lambda entry: entry["path"])
    manifest = ctx.manifest or {}
    lines = ["schema_version: 1",
             f"kind: {adopt.PLACEMENT_PLAN_KIND}", ""]
    lines += list(PLACEMENT_PLAN_PREAMBLE)
    lines.append("")
    adopt.emit(lines, "generated_on", _dt.date.today().isoformat())
    adopt.emit(lines, "tool", f"{adopt.SHAPE_REPOSITORY} shape-doctor.py")
    adopt.emit(lines, "policy", "contracts/path-classification.yaml")
    adopt.emit(lines, "standard", ctx.shape.as_posix())
    lines.append("")
    lines.append("root:")
    adopt.emit(lines, "path", ctx.root.as_posix(), 2)
    adopt.emit(lines, "project", manifest.get("name") or ctx.root.name, 2)
    adopt.emit(lines, "id", manifest.get("id"), 2)
    lines += ["", "legs:"]
    for leg in (detail.get("legs") or []):
        lines.append(f"  - role: {adopt.y(leg.get('role'))}")
        adopt.emit(lines, "path", leg.get("path"), 4)
        adopt.emit(lines, "state", leg.get("state"), 4)
        if leg.get("state") == "audited":
            adopt.emit(lines, "tracked", leg.get("tracked"), 4)
            adopt.emit(lines, "classified", leg.get("classified"), 4)
            adopt.emit(lines, "paths", leg.get("paths"), 4)
            adopt.emit(lines, "misplaced", leg.get("misplaced"), 4)
            adopt.emit(lines, "review_required", leg.get("review_required"), 4)
            for name in (leg.get("unwritable") or []):
                lines.append("    # a tracked name no plan can carry: "
                             + name.replace("\n", " "))
    unread = [leg.get("path") for leg in (detail.get("legs") or [])
              if leg.get("state") != "audited"]
    if not entries:
        lines += ["",
                  "# Nothing is in the wrong leg and nothing needs a reading",
                  "# IN WHAT WAS READ: there is nothing here to resolve."]
        if unread:
            lines += ["# The `legs:` block above names "
                      f"{len(unread)} leg(s) that could not be read at all,",
                      "# so this emptiness is not a clean bill of health for "
                      "them."]
        lines.append("paths: []")
    else:
        lines += ["", "paths:"]
    for entry in entries:
        lines.append(f"  - path: {adopt.y(entry['path'])}")
        adopt.emit(lines, "in_leg", entry["leg"], 4)
        adopt.emit(lines, "leg", entry["classified_as"], 4)
        adopt.emit(lines, "confidence", entry["confidence"], 4)
        adopt.emit(lines, "rule", entry["rule"], 4)
        adopt.emit(lines, "reason", entry["reason"], 4)
        adopt.emit(lines, "files", entry["files"], 4)
        adopt.emit(lines, "bytes", entry["bytes"], 4)
        adopt.emit(lines, "review_required", entry["review_required"], 4)
        if entry.get("question"):
            adopt.emit(lines, "question", entry["question"], 4)
        adopt.emit(lines, "resolution", "", 4)
    lines += ["",
              "# What was NOT judged: a path matching one of these belongs to",
              "# every repository, so it is never misplaced in a leg. Four of",
              "# them are read from templates/<role>-root/ -- files this",
              "# standard's own scaffold writes INTO a leg.",
              "ignored:"]
    for pattern in (detail.get("everywhere") or []):
        lines.append(f"  - {adopt.y(pattern)}")
    return "\n".join(lines) + "\n"


def write_placement_plan(ctx: Context, rows: list, out: Path) -> str:
    """Write the plan, or refuse by name. Returns the path written.

    THE ONE THING THIS COMMAND WRITES, and it writes it where the caller said
    and nowhere else. It creates no directory: a `--placement-plan` naming a
    path whose parent is not there is a typo, and a command that answered a
    typo by making a directory tree is a command that writes where nobody
    looked.
    """
    row = next((row for row in rows if row.id == "placement"), None)
    if row is None or row.status == NA:
        raise Refusal(
            "shape-doctor-no-placement-audit",
            f"{ctx.root} has no placement audit to write a plan from"
            + (f": {row.reason}" if row is not None
               else f", because it is not an assembly root ({ctx.kind})"),
            "Remediation: --placement-plan is for an assembly root whose legs "
            "are mounted. Run the doctor without it and read the `placement` "
            "row, which says why this root has none.")
    adopt = ctx.adopt()
    try:
        adopt.write_lf(out, placement_plan_text(ctx, adopt, row))
    except OSError as exc:
        raise Refusal(
            "shape-doctor-placement-plan-unwritable",
            f"--placement-plan {out}: {exc}",
            "Remediation: name a file in a directory that already exists. "
            "This command creates no directory, and writes nothing else "
            "anywhere.") from exc
    return out.as_posix()


def pinned_paths(root: Path) -> set:
    """Every path `contracts/shape-pin.yaml` carries a `files:` row for.

    Read here rather than taken from the shape-currency row because the two
    checks are independent by design — one may refuse while the other still
    has something true to say — and because this is one `load_yaml` of a file
    that is already open in the page cache.
    """
    pin = Context._read(root / "contracts" / "shape-pin.yaml")
    if not isinstance(pin, dict):
        return set()
    return {str(row.get("path")) for row in (pin.get("files") or [])
            if isinstance(row, dict) and row.get("path")}


def check_agent_files(ctx: Context) -> Row:
    present = {name: (ctx.root / name).is_file() for name in AGENT_FILES}
    absent = [name for name, there in present.items() if not there]
    detail = {"files": present}
    if not absent:
        return Row("agent-files", "agent files", OK,
                   ", ".join(f"{name} present" for name in AGENT_FILES),
                   None, detail)
    pinned = pinned_paths(ctx.root)
    detail["pinned"] = sorted(name for name in absent if name in pinned)
    # WHICH FIX DEPENDS ON WHETHER THE PIN ALREADY NAMES IT, and getting that
    # backwards hands somebody a command that refuses. A path the pin has a
    # row for and the tree has no file at is `copy-missing` to
    # `update-shape.py`, and `--add` refuses it BY NAME as already pinned; a
    # path with no row is `upstream-added`, which is exactly what `--add`
    # takes (Copilot, PR #96).
    if detail["pinned"]:
        first = detail["pinned"][0]
        fix = (f"git -C {quote_arg(ctx.root)} checkout -- "
               f"{quote_arg(first)}   # the pin has a "
               "`files:` row for it, so it was deleted rather than never "
               "copied; restore it from this repository's own history, then "
               f"`{PYTHON} "
               f"{quote_arg(ctx.root / 'scripts' / 'validate-pins.py')} "
               f"--root {quote_arg(ctx.root)}` to confirm the digest")
    elif "AGENTS-shape.md" in absent:
        fix = (f"{PYTHON} {quote_arg(ctx.shape / 'update-shape.py')} "
               f"check --root {quote_arg(ctx.root)} --upstream "
               f"{quote_arg(ctx.shape)}   # no pin row names it, "
               "so it is reported upstream-added and taken, on the human's "
               "word, with `apply --add AGENTS-shape.md`")
    else:
        fix = (f"{PYTHON} {quote_arg(ctx.shape / 'scaffold-project.py')} "
               f"--help   # {' and '.join(absent)} is RENDERED per project, "
               "not copied; "
               "write it, or take a rendered one from a scaffolded root")
    # FINDING ONLY FOR A FILE SOMETHING ELSE ASSERTS. `AGENTS-shape.md` is a
    # pinned copy, so its absence is already a `shape-copy-missing` finding
    # from the project's own `validate-pins.py` and this row agrees with it.
    # `AGENTS.md` and `CLAUDE.md` are RENDERED and pinned by nothing: a root
    # without one is a root nothing in this standard says anything about, and
    # failing it here would be the `leg shape files` mistake again, one file
    # along.
    status = FINDING if detail["pinned"] else NOTE
    return Row("agent-files", "agent files", status,
               "absent: " + ", ".join(absent), fix, detail)


def detached(path: Path) -> bool | None:
    """Is this checkout on a detached HEAD? None when git cannot say.

    `symbolic-ref -q HEAD` succeeds with a branch name and fails when HEAD
    is detached, which is the one question with no ambiguity in it.
    """
    if not (path / ".git").exists():
        return None
    proc = subprocess.run(["git", "symbolic-ref", "-q", "HEAD"],
                          cwd=str(path), capture_output=True, check=False)
    return proc.returncode != 0


def is_this_member(sibling: Path, row: dict) -> bool:
    """Is the directory beside the holder THIS member, or just a clone?

    `scripts/siblings.py::verify_sibling` asks the same question before it
    will touch a directory, and for the same reason: a repository that
    happens to sit at `../<Project>` is somebody else's, and a report that
    counted it would tell a person their working clone is there when it is
    not (Copilot, PR #96). The manifest's `id` is the identity
    `validate-family.py` already checks the MOUNT by, so it is the one asked
    here too.
    """
    if not (sibling / ".git").exists():
        return False
    manifest = Context._read(sibling / "project.yaml")
    if not isinstance(manifest, dict):
        return False
    if manifest.get("kind") != "project-manifest":
        return False
    wanted = row.get("id")
    if wanted:
        return str(manifest.get("id")) == str(wanted)
    return str(manifest.get("name")) == str(row.get("project"))


def check_members(ctx: Context) -> Row:
    """Each member pinned under `members/`, and the working clone beside it.

    TWO COPIES OF EVERY MEMBER IS THE LAYOUT, and they are different things.
    `members/<Project>` inside the holder is PINNED AND DETACHED — that is
    what `bootstrap` places and what `validate-family.py` reads — and the
    sibling beside the holder is where a person works. So the mount is asked
    whether it is detached AT the pin, and the sibling is only asked whether
    it exists and is this project.
    """
    members = ctx.members()
    members_dir = str((ctx.manifest or {}).get("members_dir") or "members")
    if not members:
        return Row("members", "members", OK,
                   "no members yet: a family with none is empty, not wrong",
                   None, {"members": []})
    rows: list[dict] = []
    problems: list[str] = []
    siblings_absent: list[str] = []
    on_a_branch: list[str] = []
    for row in members:
        project = str(row.get("project") or "?")
        rel = str(row.get("path") or f"{members_dir}/{project}")
        mount = ctx.root / rel
        pin = row.get("pin") if isinstance(row.get("pin"), dict) else {}
        pinned = str(pin.get("commit") or "").lower()
        pinned = pinned if COMMIT_RE.match(pinned) else None
        populated = mount.is_dir() and any(mount.iterdir())
        head = head_of(mount) if populated else None
        loose = detached(mount) if populated else None
        sibling = ctx.root.parent / project
        has_sibling = is_this_member(sibling, row)
        rows.append({"project": project, "path": rel, "pin": pinned,
                     "populated": populated, "head": head,
                     "detached": loose,
                     "working_clone": sibling.as_posix() if has_sibling
                     else None})
        if not populated:
            problems.append(f"{rel}: not populated -- the pinned copy is an "
                            "unbootstrapped submodule")
        elif pinned is None:
            problems.append(f"{project}: the row carries no 40-hex "
                            "`pin.commit` to compare against")
        elif head != pinned:
            problems.append(f"{rel}: checked out at "
                            f"{(head or '?')[:12]}, pinned at {pinned[:12]}")
        elif loose is False:
            # AT THE PIN BUT ON A BRANCH: RECORDED AND SAID, NEVER A FINDING.
            # Copilot asked for this on PR #96, and asked for it as a
            # failure — but `family.py add` ITSELF leaves the member on a
            # branch (`git submodule add` checks one out), and only a fresh
            # `clone --recurse-submodules` of the holder is detached. A row
            # that refused here would refuse a holder the standard's own
            # tool had just made, which is a rule this standard has not
            # made. So the state is reported, because a branch in the copy
            # the gate reads is worth a person's attention, and the verdict
            # is left to the facts `validate-family.py` actually asserts.
            on_a_branch.append(rel)
        if not has_sibling:
            siblings_absent.append(project)
    detail = {"members": rows, "without_working_clone": siblings_absent,
              "on_a_branch": on_a_branch}
    if problems:
        return Row("members", "members", FINDING, "; ".join(problems),
                   f"{PYTHON} "
                   f"{quote_arg(ctx.root / 'scripts' / 'bootstrap.py')} "
                   f"--root {quote_arg(ctx.root)}   # what `make bootstrap` "
                   "runs in a holder: it fetches every member at its pin and "
                   "leaves it detached there", detail)
    note = f"{len(rows)} member(s) mounted at their pins"
    if on_a_branch:
        note += ("; on a BRANCH rather than detached: "
                 + ", ".join(on_a_branch)
                 + " (a fresh `clone --recurse-submodules` of this holder is "
                   "detached; `family.py add` leaves a branch behind)")
    if siblings_absent:
        # NOT A FINDING. The working clones are the WORKSTATION layout, and a
        # holder on a machine that has not placed them is not thereby
        # non-compliant -- `members/<Project>` is what the gate reads.
        return Row("members", "members", OK,
                   f"{note}; no working clone beside the holder for "
                   + ", ".join(siblings_absent)
                   + " (`make siblings` places them; the pinned copy under "
                     f"{members_dir}/ is detached by design)", None, detail)
    return Row("members", "members", OK,
               f"{note}, each with a working clone beside the holder", None,
               detail)


# ---------------------------------------------------------------------------
# What is here instead, when this is not a shape root
# ---------------------------------------------------------------------------


#: A Windows path, recognized by its OWN spelling rather than by "has a
#: backslash in it": a drive letter (`D:\` or `D:/`) or a UNC share (`\\
#: server\share`). Only a remote spelled ONE of these two ways gets its
#: backslashes read as separators -- everywhere else a `\` is left alone,
#: because it is an ORDINARY character in a POSIX path or a repository name
#: (`/tmp/foo\bar.git`'s basename is `foo\bar`, literally, and rewriting
#: every `\` in that path would have answered `bar` instead, silently
#: discarding half of it -- Copilot, PR #110).
_WINDOWS_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")


#: `[user@]host:path` with the host itself bracketed -- the only way this
#: grammar has to write an IPv6 host, since the address is already
#: colon-separated (`[::1]:repo.git`) and would otherwise swallow the real
#: separator whole. The captured group is everything after the `:` that
#: follows the closing `]` (Copilot, PR #110, fourth review).
_BRACKETED_HOST_RE = re.compile(r"^(?:[^@/\\]*@)?\[[^\]]*\]:(.*)$")


def origin_name(root: Path) -> str | None:
    """`origin`'s own repository name, however its URL spells the path to it.

    A WINDOWS PATH IS NORMALIZED TO `/` FIRST. `git remote get-url origin`
    answering `D:\\a\\_work\\1\\s\\Atlas.git` -- the shape's own CI runner
    lays a checkout out exactly like that -- carries no `/` at all, so the
    old `rsplit("/", 1)` found nothing to split on and returned the WHOLE
    path as the "name": every caller downstream (`project_token_for` among
    them) then read a colon and a run of backslashes as part of an identity
    (Copilot, PR #110). `_WINDOWS_PATH_RE` is what keeps this from ALSO
    rewriting a POSIX path whose basename merely contains a `\\` of its own.

    AND SCP-LIKE SYNTAX IS READ BY ITS OWN GRAMMAR, not assumed to carry a
    `/`. `[user@]host:path` -- `git@example.com:Atlas.git`, no group prefix
    at all -- has no `/` in it either, so it hit the exact same "nothing to
    split on, return the whole string" failure, and a caller derived
    `GitExampleComAtlas` from it (Copilot, PR #110).

    BUT NOT EVERY COLON IS THAT SEPARATOR. A local path's basename can
    carry one of its own -- `/tmp/openRepo:Project.git` -- and reading
    everything after the LAST `:` once a URL scheme was ruled out treated
    THAT colon exactly like the one in `git@example.com:Atlas.git`,
    truncating `openRepo:Project` down to `Project` (Copilot, third review
    of PR #110). The text BEFORE the colon is what tells the two apart: a
    drive letter (`D`) or an SCP host (`git@example.com`) never itself
    contains a `/` or `\\`, so a colon right after one of those IS the
    separator; everywhere else -- a path that already has one inside it,
    included -- the colon is just an ordinary character, and the string is
    left alone.

    AND WHEN THE HOST'S COLON IS NOT THE ONLY ONE, IT IS STILL THE FIRST.
    `git@example.com:team:repo.git` -- a group prefix in the repository's
    OWN path, ordinary enough -- has two colons, and the fix above reached
    for `rpartition`, the LAST one: `team:` read as more of the path the
    host's colon already separated, and vanished along with it, leaving
    `repo` where `team:repo` belonged (Copilot, fourth review of PR #110).
    The host ends at ITS OWN colon, the first one after it, however many
    the path that follows goes on to contain.

    AND A BRACKETED HOST HIDES ITS COLONS FROM THAT RULE ENTIRELY. An IPv6
    host is written `[host]` in this grammar for exactly this reason --
    `::1` is already colon-separated -- so the first colon in
    `[::1]:repo.git`, by plain text position, sits INSIDE the brackets,
    part of the host, and splitting there would cut the host in half.
    `_BRACKETED_HOST_RE` reads a bracketed host whole and takes the
    separator from right after its closing `]`, before the first-colon
    rule below ever runs. A drive letter is excluded from that rule the
    same explicit way, rather than by the accident of also never
    containing a second colon of its own: `D` in `D:/a/.../Atlas.git` is a
    PATH, never a host, however this function is later changed to use
    what comes after it.
    """
    try:
        url = git_out(["remote", "get-url", "origin"], cwd=root)
    except (Refusal, OSError):
        return None
    if _WINDOWS_PATH_RE.match(url):
        url = url.replace("\\", "/")
    url = url.rstrip("/")
    if "://" not in url:
        bracketed = _BRACKETED_HOST_RE.match(url)
        if bracketed:
            url = bracketed.group(1)
        elif ":" in url and not _WINDOWS_PATH_RE.match(url):
            prefix, _, rest = url.partition(":")
            if "/" not in prefix and "\\" not in prefix:
                url = rest
    name = url.rsplit("/", 1)[-1]
    return name[:-4] if name.endswith(".git") else name or None


def repo_local_origin_name(root: Path) -> str | None:
    """`origin`'s name, but only when `root` ITSELF carries the `.git` it
    belongs to.

    `git remote get-url origin` does not stop at `root` looking for one --
    run from a directory that has none, it walks UP to the nearest ancestor
    repository and answers for THAT one, which is a fact about the
    ANCESTOR, not about `root`: a loose folder with no `.git` of its own,
    sitting inside a clone of `openRepoProject`, is not `openRepoProject`
    (Copilot, PR #110). Both callers that read an origin's name for `root`'s
    OWN identity -- `naming` and `the way in` -- share this guard rather
    than each re-deriving "is this directory itself a repository" on its
    own.
    """
    return origin_name(root) if (root / ".git").exists() else None


def check_not_a_root_naming(ctx: Context) -> Row:
    """Classify what this directory is CALLED, under the naming policy.

    The directory name and, when there is one, `origin`'s repository name.
    They are usually the same and are not always: a clone into a differently
    named folder is ordinary, and the name that matters for the policy is the
    repository's -- ITS OWN, never an ancestor's: `repo_local_origin_name`
    answers only when `ctx.root` carries the `.git` that origin belongs to,
    so a loose directory nested inside somebody else's checkout is classified
    on its own name alone, the same fact `the way in` row now reads it by
    (Copilot, PR #110).
    """
    script = ctx.shape / "scripts" / "validate-repository-naming.py"
    names = [ctx.root.name]
    remote = repo_local_origin_name(ctx.root)
    if remote and remote not in names:
        names.append(remote)
    # `--` BEFORE THE NAMES. Without it a directory literally named `--help`
    # or `-x` is not a name to argparse, it is an OPTION: `--explain --help`
    # exits 0 through argparse's OWN help action before either positional is
    # read, which this row would have reported as "classifies under the
    # naming policy" -- a false COMPLIANT for a name that classifies under
    # nothing. Quoting (#101/#102) cannot fix this: `quote_arg` promises a
    # value survives the READER'S SHELL as one argument, and `--help` needs
    # no shell quoting at all to do that -- the token argparse then reads is
    # exactly what was typed. `--` is argparse's own end-of-options marker,
    # not a shell's, and `scripts/validate-repository-naming.py`'s parser
    # accepts it because every `argparse.ArgumentParser` does by default.
    code, quoted, whole = run_validator(ctx, script,
                                        ["--explain", "--", *names])
    detail = {"names": names, "origin": remote, "exit": code,
              "explain": ascii_text(whole).strip().splitlines()[:40]}
    reason = f"{', '.join(names)}: " + (
        "classifies under the naming policy" if code == 0
        else (quoted or "matches no family in the policy"))
    spelled = " ".join(quote_arg(name) for name in names)
    return Row("naming", "naming", OK if code == 0 else FINDING, reason,
               None if code == 0 else
               f"{PYTHON} {quote_arg(script)} --explain -- {spelled}", detail)


def check_what_is_here(ctx: Context) -> Row:
    """What IS in this directory, said plainly, so the reader can place it."""
    root = ctx.root
    facts: list[str] = []
    detail = {}
    for name, note in ((".git", "a git repository"),
                       (".gitmodules", "a .gitmodules"),
                       ("contracts", "a contracts/ directory"),
                       ("spec", "a spec/ directory"),
                       ("code", "a code/ directory"),
                       ("AGENTS.md", "an AGENTS.md"),
                       ("Makefile", "a Makefile")):
        there = (root / name).exists()
        detail[name] = there
        if there:
            facts.append(note)
    detail["project_yaml"] = (root / "project.yaml").is_file()
    detail["family_yaml"] = (root / "family.yaml").is_file()
    if detail["project_yaml"] or detail["family_yaml"]:
        # A manifest is THERE and did not declare the kind that makes it one,
        # which is a different fault from having none, and worth saying.
        facts.append("a manifest file that declares neither `kind: "
                     "project-manifest` nor `kind: family-manifest`")
    return Row("contents", "what is here", NA,
               ", ".join(facts) if facts else
               "no git repository, no manifest, no contracts/ -- an ordinary "
               "directory", None, detail)


#: Named in the `machine` row because the doctor's OWN next commands need it
#: and the preflight does not ask about it: `adopt-project.py` extracts a
#: leg's history with `git filter-repo` and refuses without it, and
#: `adopt-project.py plan` is what the NOT A SHAPE ROOT verdict sends a person
#: at. Absent is not a finding -- it is needed to ADOPT and for nothing else.
ADOPTION_TOOL = "git-filter-repo"


def check_machine(ctx: Context) -> Row:
    """Can this machine run the fixes the rows above name?

    IT RUNS THE REAL PREFLIGHT rather than a second copy of the check list.
    `setup-project.py --preflight` is section (1) of the scaffold and nothing
    else -- git, a Python 3.9+, the bootstrap interpreter, `gh` and its login,
    the credential helper, and the autocrlf warning -- and re-listing those
    here would be two lists to keep in step, which is the duplication #50
    removed. It is run with stdin CLOSED, so the "no terminal, no offer" rule
    fires and nothing is offered, prompted for or installed: the doctor
    diagnoses, and installing something is a different act with a different
    consent.

    THIS IS THE ONE ROW THAT CAN REACH A NETWORK, and it is `n/a` by status
    for a separate reason. The preflight asks `gh` its version, whether it is
    authenticated and who as (`gh --version`, `gh auth status`, `gh api
    user`) -- three questions `gh` answers by talking to its host; nothing
    else in this command leaves the disk. And a machine's state is not the repository's: a workstation
    with no `gh` cannot open the pull request a fix needs, which is worth
    saying and is not this repository being non-compliant. So the row reports
    and never changes the verdict.
    """
    entry = ctx.shape / "setup-project.py"
    adoption = shutil.which(ADOPTION_TOOL)
    detail = {"preflight": entry.as_posix(),
              ADOPTION_TOOL: adoption or None}
    if not entry.is_file():
        return Row("machine", "machine", NA,
                   f"{entry} is not here, so the preflight could not be run",
                   None, detail)
    code, quoted, whole = run_validator(ctx, entry, ["--preflight"])
    detail["exit"] = code
    # The preflight's own `[ok]`/`[!!]`/`[??]` lines, which are its report.
    marks = [ascii_text(line.strip()) for line in whole.splitlines()
             if line.strip().startswith(("[ok]", "[!!]", "[??]"))]
    detail["report"] = marks
    ready = "this machine is ready" if code == 0 else \
        "this machine is missing something the fixes above may need"
    extra = ("" if adoption else
             f"; {ADOPTION_TOOL} is not on PATH, which only `adopt-project.py`"
             " needs")
    reason = f"{ready} (setup-project.py --preflight, exit {code}){extra}"
    if code != 0 and quoted:
        reason += f": {quoted}"
    return Row("machine", "machine", NA, reason,
               None if code == 0 else
               f"{PYTHON} {quote_arg(entry)} --preflight   # it names each "
               "missing prerequisite and offers to install it, on a typed "
               "yes",
               detail)


def python_command(platform: str | None = None) -> str:
    """`PYTHON`, for the platform ASKED FOR rather than the one running.

    `repo_shape.PYTHON` is decided ONCE, at import, from `os.name` -- rightly,
    because every other caller is spelling a command for the machine it is
    on. This file has one caller that is not: `scaffold_command` takes a
    `platform` so both spellings can be asserted from either host, and reading
    the module constant there made the Windows branch print `python3` on a
    POSIX runner -- the function claiming a spelling it did not produce, with
    a `startswith("python")` assertion too loose to notice (Copilot, PR #102).

    THE RULE IS `repo_shape`'s OWN, mirrored and not re-argued: `python` on
    Windows, where python.org and the Microsoft Store both put that name on
    PATH and there is usually no `python3` at all, and `python3` everywhere
    else, the command every POSIX install of a supported Python answers to.
    `platform=None` returns the constant itself, so the host-default path is
    the same object every other line in this file uses rather than a second
    derivation of it that could drift.
    """
    if platform is None:
        return PYTHON
    return "python" if platform == "nt" else "python3"


def scaffold_command(shape: Path, project: str,
                     platform: str | None = None) -> str:
    # RAW, for `quote_arg`'s reason one function along: the paragraph below
    # spells a Windows path, and `\s` is not an escape sequence -- a
    # docstring that had to double its backslashes would be a docstring
    # nobody could compare to the line they see in the report.
    r"""How a NEW project is created, spelled for the READER'S platform.

    `setup.sh` IS A BASH SCRIPT AND WINDOWS HAS NO BASH. This row's whole job
    is to hand somebody a line they can run, and on the one platform where
    this file has no shell to run that line in it was handing them a path
    PowerShell cannot execute at all (Copilot, PR #102). The standard's own
    answer has been `setup-project.py` since #49 -- it IS the flow and
    `setup.sh` is a shim over it (#50), which is why the README's Windows
    two-liner downloads that file and runs it, and why there is no `--install`
    twin on Windows: there is nothing to install.

    `platform` for the same reason `quote_arg` has one: so both spellings are
    asserted on whichever host the suite is running on, rather than half of
    them only ever being exercised where nobody is looking. Which is also why
    the INTERPRETER comes from `python_command(platform)` and not from the
    module-global `PYTHON`: that constant is the HOST's, so reading it here
    made the Windows branch print `python3` on a POSIX runner -- this function
    claiming a spelling it did not produce, in the one place written to be
    read from the other platform (Copilot, PR #102).

    AND THE QUOTING IS THAT PLATFORM'S TOO, which is the third of the three
    decisions this one line makes and was the last one still reading the
    HOST. `quote_arg` defaults to `os.name` when it is passed no platform, so
    with an explicit `platform` half this line followed the argument and half
    followed the machine: `scaffold_command(PureWindowsPath(r"C:\srv\Shape"),
    "Atlas", "nt")` named `setup-project.py` and `python` on every host, as
    asked, and then rendered the path BARE on Windows and QUOTED on Linux and
    macOS -- two different strings for the same arguments, from a function
    whose whole reason to take a `platform` is to spell one line for the
    OTHER one (#103). `\` is in `UNQUOTED_NT` and not in `UNQUOTED_POSIX`,
    so a Windows path is exactly where that shows.

    ONE RESOLUTION, USED THREE TIMES. `target` is decided once and the
    branch, the quoting and the interpreter all read it rather than each
    re-deriving "which platform is this" from its own source -- which is the
    defect above, stated as code. `python_command` is the one that keeps the
    RAW `platform`: `None` there returns the module constant itself rather
    than a second derivation of the same rule (see its docstring), and
    `quote_arg(value, None)` resolves the host identically to
    `quote_arg(value, os.name)`, so the host-default line is unchanged, byte
    for byte.
    """
    target = os.name if platform is None else platform
    if target == "nt":
        return (f"{python_command(platform)} "
                f"{quote_arg(shape / 'setup-project.py', target)} "
                f"--org <your-org> --project {quote_arg(project, target)}")
    return (f"{quote_arg(shape / 'setup.sh', target)} --org <your-org> "
            f"--project {quote_arg(project, target)}")


def project_token_for(name: str, policy: NamingPolicy) -> str:
    """The `--project` `adopt-project.py` (and the scaffold) will accept for
    `name`, unchanged where `name` is already one.

    `accepts_role` is the ONE definition of which forms may be an assembly
    root -- `adopt-project.py`'s own `_check_names` runs exactly this,
    role `assembly`, over the value it is handed, and the scaffold's gate
    agrees. A name that already passes it is therefore a name those tools
    take VERBATIM, and respelling it first can hand them a DIFFERENT one:
    `openRepoProject` classifies as `neutral-product`, which admits the
    `assembly` role unchanged (2026-09-05) -- but the unconditional
    `"".join(part.capitalize() ...)` derivation below turned it into
    `Openrepoproject`, a bare `project-leg/assembly` token that still
    classified, so nothing in the naming policy caught the mismatch. Run
    live, the emitted `adopt-project.py plan --project Openrepoproject`
    named the two new legs off a token that loses the repository's own
    family, beside a root still called `openRepoProject`.

    The derivation is kept as the fallback for a name the policy admits no
    form of at all: `my-repo` has no valid `--project` to preserve, so
    `MyRepo` is offered instead, exactly as before.

    IT SPLITS ON ANYTHING THE POLICY DOES NOT ADMIT, not only `-` and `_`.
    A `.` is an ordinary character in a repository name -- `my.repo` is
    exactly as reachable through `origin`'s name now that this function is
    handed it, not only a directory's -- and the policy admits it in no
    family at all, so the old rule's narrower split fed it straight through
    into the suggested `--project`, which `adopt-project.py` then refused
    outright (Copilot, PR #110). AND THE RESULT MUST ITSELF START WITH A
    LETTER, because every family the policy declares does: a derivation
    that begins with a digit (`9lives`) classifies nothing either, the same
    finding at the other end of the string, and falls back to the same
    `"Project"` placeholder a name with no letters or digits in it at all
    already did.
    """
    if accepts_role(policy.classify(name, "assembly"), "assembly"):
        return name
    parts = [part for part in re.split(r"[^A-Za-z0-9]+", name) if part]
    derived = "".join(part.capitalize() for part in parts)
    return derived if re.match(r"^[A-Za-z]", derived) else "Project"


def check_the_way_in(ctx: Context) -> Row:
    """The two ways a directory becomes a shape root, and who decides.

    NEITHER IS RUN HERE AND NEITHER IS RECOMMENDED OVER THE OTHER. Adopting an
    existing repository keeps its identity and its history and cuts two legs
    out of it; scaffolding creates three new repositories. Which of those a
    person wants is a fact about their repository, not about this directory
    listing, so both are named and the human chooses.

    THE SUGGESTED `--project` READS THE SAME IDENTITY THE `naming` ROW DOES:
    `origin`'s repository name where there is one, the directory's own name
    otherwise -- `check_not_a_root_naming`'s own docstring, "the name that
    matters for the policy is the repository's" -- because a clone into a
    differently named folder does not change what would actually be adopted.
    `project_token_for` decides whether that identity is handed back
    verbatim or respelled.

    `origin` IS CONSULTED ONLY WHEN `root` CARRIES ITS OWN `.git`, through
    `repo_local_origin_name`: `git` itself does not stop at `root` looking
    for one, so a loose folder sitting inside somebody else's checkout would
    otherwise have picked up THAT checkout's `origin` -- a directory named
    `Loose` under a clone of `openRepoProject` suggesting `--project
    openRepoProject` to the SCAFFOLD line, which is about to create a
    project named after a repository this directory is not (Copilot, PR
    #110). The `naming` row shares the same guard, for the same reason.
    """
    root = ctx.root
    is_repo = (root / ".git").exists()
    identity = repo_local_origin_name(root) or root.name
    policy = NamingPolicy.load(ctx.shape / "contracts" /
                               "repository-naming.yaml")
    project = project_token_for(identity, policy)
    if is_repo:
        fix = (f"{PYTHON} {quote_arg(ctx.shape / 'adopt-project.py')} "
               f"plan --source {quote_arg(root)} --project "
               f"{quote_arg(project)}")
        reason = ("this is a git repository with no shape manifest: it is "
                  "ADOPTED in place, keeping its name, identity and history")
    else:
        # `<your-org>` IS NOT QUOTED and must not be: it is a placeholder
        # the reader replaces, not a value this command knows. Quoting it
        # would tell them to type the angle brackets.
        fix = (scaffold_command(ctx.shape, project)
               + "   # without --yes; it asks")
        reason = ("there is no repository here to adopt: a new project is "
                  "SCAFFOLDED, which creates three repositories and asks "
                  "first")
    return Row("way-in", "the way in", NA, reason, fix,
               {"git_repository": is_repo, "suggested_project": project})


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------


CHECKS = (
    Check("naming", "naming", (PROJECT,), check_naming),
    Check("manifest", "manifest", (PROJECT,), check_manifest),
    Check("pins", "pins", (PROJECT,), check_pins),
    Check("family", "family", (FAMILY,), check_family),
    Check("manifest-kinds", "manifest kinds", (PROJECT, FAMILY),
          check_manifest_kinds),
    Check("shape-currency", "shape currency", (PROJECT, FAMILY),
          check_shape_currency),
    Check("legs", "legs", (PROJECT,), check_legs),
    Check("leg-shape-files", "leg shape files", (PROJECT,),
          check_leg_shape_files),
    # AFTER the two rows about the legs THEMSELVES, because it is about what
    # is INSIDE them, and a leg that is not mounted has no paths to judge --
    # which those rows have just said, with `make bootstrap` beside it.
    Check("placement", "placement", (PROJECT, FAMILY), check_placement),
    Check("agent-files", "agent files", (PROJECT, FAMILY), check_agent_files),
    Check("members", "members", (FAMILY,), check_members),
    Check("naming", "naming", (NOT_A_ROOT,), check_not_a_root_naming),
    Check("contents", "what is here", (NOT_A_ROOT,), check_what_is_here),
    Check("way-in", "the way in", (NOT_A_ROOT,), check_the_way_in),
    # LAST, AND ON EVERY KIND OF ROOT. It reports the machine rather than
    # the repository, so it is `n/a` by status and never moves the verdict
    # -- see `check_machine`. It reads last because it is about the
    # commands the rows ABOVE it named.
    Check("machine", "machine", (PROJECT, FAMILY, NOT_A_ROOT),
          check_machine),
)


def run_checks(ctx: Context) -> list[Row]:
    rows: list[Row] = []
    for check in CHECKS:
        if ctx.kind not in check.applies_to:
            continue
        try:
            rows.append(check.run(ctx))
        except Refusal as exc:
            rows.append(Row(check.id, check.label, FINDING,
                            f"refused: {exc.detail}", exc.remediation or None,
                            {"error": exc.code}))
        except OSError as exc:
            rows.append(Row(check.id, check.label, FINDING,
                            f"could not be run: {exc}", None, {}))
    return rows


# ---------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------


def cannot_answer(rows: list[Row]) -> Row | None:
    """The first row that says this CHECKOUT could not ask its question."""
    for row in rows:
        if row.detail.get("environment"):
            return row
    return None


def verdict_for(ctx: Context, rows: list[Row]) -> tuple[str, int]:
    """ONE line, and the exit code that goes with it.

    The order below IS the precedence, and the docstring at the top of this
    file argues the one that surprises: drift outranks a red validator,
    because an edited shape copy is what makes `validate-pins.py` red and
    naming the validator would send the reader at the symptom.
    """
    if ctx.kind == NOT_A_ROOT:
        return V_NOT_A_ROOT, 2
    blocked = cannot_answer(rows)
    if blocked is not None:
        return f"{V_CANNOT_ANSWER} ({blocked.label}: {blocked.reason})", 3
    by_id = {row.id: row for row in rows}
    currency = by_id.get("shape-currency")
    detail = currency.detail if currency else {}
    counts = detail.get("counts") or {}

    reasons: list[str] = []
    if detail.get("drifted"):
        for state in ("locally-modified", "both"):
            if counts.get(state):
                reasons.append(f"{counts[state]} {state}")
        for state in ("upstream-removed", "unmapped", "copy-missing"):
            if counts.get(state):
                reasons.append(f"{counts[state]} {state}")
    legs = by_id.get("legs")
    if legs is not None and legs.status == FINDING:
        off = [leg for leg in (legs.detail.get("legs") or [])
               if leg.get("head") != leg.get("pin")]
        reasons.append(f"{len(off) or 1} leg(s) not at the pin")
    members = by_id.get("members")
    if members is not None and members.status == FINDING:
        reasons.append("a member is not at its pin")
    if reasons:
        return f"{V_DRIFTED} ({', '.join(reasons)})", 1

    # UNDER DRIFTED AND OVER INVALID. A path in the wrong leg is a fact about
    # the SHAPE that nothing else in this report can see -- no validator, no
    # pin row, no manifest asserts where a file lives -- whereas a red
    # validator names itself in the table whether or not it also names the
    # verdict line. Drift still outranks it: a leg off its pin means the
    # paths this row read are not the paths the pin describes.
    placement = by_id.get("placement")
    misplaced = (placement.detail.get("misplaced") or []) if placement else []
    # THE LIST HAS TO BE NON-EMPTY, not merely the row red. `run_checks` turns
    # an exception out of any check into a FINDING row with an empty detail,
    # and this branch would then have answered `MISPLACED (0 paths)` about a
    # row that never got as far as classifying anything -- a verdict naming a
    # count of zero. Such a row falls through to the generic handling below
    # and reads `INVALID (placement)`, which is what it is (Copilot, PR #100).
    if placement is not None and placement.status == FINDING and misplaced:
        count = len(misplaced)
        return (f"{V_MISPLACED} ({count} path"
                + ("" if count == 1 else "s") + ")"), 1

    red = [row.id for row in rows
           if row.status == FINDING
           and row.id in ("naming", "manifest", "pins", "family",
                          "manifest-kinds", "agent-files")]
    if red:
        return f"{V_INVALID} ({', '.join(red)})", 1

    if detail.get("behind_pin_only"):
        return (f"{V_BEHIND} (pin {str(detail.get('pinned'))[:12]} -> "
                f"{str(detail.get('standard'))[:12]}, no copied file "
                "differs)"), 1
    if detail.get("behind"):
        changed = counts.get("upstream-changed", 0)
        added = counts.get("upstream-added", 0)
        return (f"{V_BEHIND} ({changed} upstream-changed, "
                f"{added} upstream-added)"), 1
    # THE CATCH-ALL, and it is here so that a check ADDED LATER cannot exit 0
    # while its row says FINDING. A new row that belongs in `red` above is a
    # one-line edit; a new row nobody classified still fails loudly. It reads
    # `FINDING` only, so a `note` row is stepped over here too -- which is
    # the whole of what `note` means.
    other = [row.id for row in rows if row.status == FINDING]
    if other:
        return f"{V_INVALID} ({', '.join(other)})", 1
    return V_COMPLIANT, 0


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def report(ctx: Context, rows: list[Row], verdict: str, code: int,
           plan_written: str | None = None) -> None:
    described = {PROJECT: "assembly root (project.yaml)",
                 FAMILY: "family holder (family.yaml)",
                 NOT_A_ROOT: "not a shape root"}[ctx.kind]
    print(f"root        {ctx.root}")
    print(f"kind        {described}")
    print(f"standard    {ctx.shape}")
    print()
    width = max([len(row.label) for row in rows] + [10])
    status_width = max(len(row.status) for row in rows)
    for row in rows:
        print(f"  {row.status:<{status_width}}  {row.label:<{width}}  "
              f"{row.reason}")
        if row.next_command:
            print(f"  {'':<{status_width}}  {'NEXT':<{width}}  "
                  f"{row.next_command}")
    print()
    # BEFORE THE VERDICT, because the verdict is the conclusion and reads
    # last, and this line belongs with the row it came out of.
    if plan_written:
        print(f"placement plan written to {plan_written}   # nothing moved: "
              "answer every `resolution:` before a repair runs it")
        print()
    print(f"{verdict}   (exit {code})")
    note = verdict_note(ctx)
    if note:
        print(note)
    blocked = cannot_answer(rows)
    if blocked is not None:
        print(f"\nREFUSED shape-doctor-cannot-answer: {blocked.reason}\n"
              f"  Remediation: {blocked.next_command}", file=sys.stderr)


#: The line NOT A SHAPE ROOT adds, and the one thing in this file that is
#: about a HABIT rather than about a repository. `--doctor` meant "check this
#: machine" until 2026-09-10; a person who types it out of that habit, in a
#: directory that is not a shape root, would otherwise read a verdict about
#: their repository as an answer about their machine. One line tells them
#: where the old verb went. It is printed under the verdict, never instead of
#: it, and it changes no exit code.
PREFLIGHT_MOVED = ("the machine check is `openRepoShape --preflight` now; "
                   "`--doctor` is this report")


def verdict_note(ctx: Context) -> str | None:
    return PREFLIGHT_MOVED if ctx.kind == NOT_A_ROOT else None


def as_json(ctx: Context, rows: list[Row], verdict: str, code: int,
            plan_written: str | None = None) -> str:
    return json.dumps({
        "root": ctx.root.as_posix(),
        "standard": ctx.shape.as_posix(),
        "kind": ctx.kind,
        "rows": [row.as_dict() for row in rows],
        "verdict": verdict,
        "note": verdict_note(ctx),
        #: `null` on every run that did not ask for one, so a caller reads a
        #: key rather than testing for its absence.
        "placement_plan": plan_written,
        "exit": code,
    }, indent=2, sort_keys=False)


# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shape-doctor.py", description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".",
                        help="the repository to check (default: .)")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="the same report as one JSON object")
    parser.add_argument("--placement-plan", metavar="FILE", default=None,
                        help="write the `placement` row's paths to FILE as "
                             "an adoption-plan-style YAML to resolve by hand. "
                             "The only thing this command writes, and it "
                             "still moves nothing: a path changing legs is a "
                             "pull request on each leg and a pin bump in the "
                             "root")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if [marker for marker in SHAPE_MARKERS
            if not (SHAPE_ROOT / marker).exists()]:
        return not_in_the_standard("")
    root = Path(args.root).expanduser()
    try:
        root = root.resolve()
    except OSError as exc:
        print(f"REFUSED shape-doctor-root-unreadable: --root {args.root}: "
              f"{exc}", file=sys.stderr)
        return 3
    if not root.is_dir():
        print(f"REFUSED shape-doctor-root-missing: --root {args.root} is not a "
              "directory on this machine.\n  Remediation: pass a path to a "
              "checkout. This command reads a tree; it never clones one.",
              file=sys.stderr)
        return 3
    ctx = Context(root)
    rows = run_checks(ctx)
    verdict, code = verdict_for(ctx, rows)
    plan_written = None
    if args.placement_plan:
        try:
            plan_written = write_placement_plan(
                ctx, rows, Path(args.placement_plan).expanduser())
        except Refusal as exc:
            # EXIT 3, the documented "usage or environment". Asking for a
            # placement plan of a family holder is a question about the
            # command, and printing a verdict about the repository underneath
            # a refusal about the flag would answer something nobody asked.
            print(str(exc), file=sys.stderr)
            return 3
    if args.as_json:
        print(as_json(ctx, rows, verdict, code, plan_written))
    else:
        report(ctx, rows, verdict, code, plan_written)
    return code


if __name__ == "__main__":
    sys.exit(main())
