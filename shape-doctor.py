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

WHAT IT NEVER DOES. It writes nothing into the repository it is pointed at
but a `--placement-plan <file>` the caller names there, and it never fetches.
ONE FLAG WRITES AT ALL, and it writes one file the caller named and nothing
else: `--placement-plan <file>`, below. The upstream a project's copies are
compared against is THE CHECKOUT THIS FILE IS RUN FROM, which is the whole of
why the verdict is offline: no clone, no authenticated call, and the same
answer on a machine that has never spoken to github.com. A partial clone
(`git clone --filter`) fetches what it lacks on a read, so it is asked first,
without fetching, whether it holds what the comparison reads, and the verdict
is CANNOT ANSWER where it does not (#683). Every git it starts runs with
`GIT_NO_LAZY_FETCH=1`, so a read nothing asked about first fails rather than
fetches (`lazy_fetch_off`, #787). It runs the project's
own validators OFFLINE: `run_validator` starts each child with no token, no
`gh` configuration and a proxy that goes nowhere (#297), so they are offline
whatever their own contract says. ONE ROW IS THE EXCEPTION AND IT IS NAMED:
`machine` asks `gh` who it is logged in as (`setup-project.py --preflight`
runs `gh --version`, `gh auth status` and `gh api user`), which `gh` answers
by talking to its host. That row is `n/a` by status and cannot move the
verdict -- a workstation missing `gh` is not a repository being non-compliant
-- so nothing this command CONCLUDES depends on a network, and a machine with
no `gh` at all is reported rather than refused.

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
inventory plugs in by adding one row to that table. A kind whose check never
runs on THIS kind of root is that failure too, and the same FINDING (#327):
`validate-family.py` is registered for `family-manifest` and runs in a family
holder only, so a `contracts/family.yaml` in an assembly root -- or a
`contracts/project.yaml` in a holder -- is a manifest nothing here reads. So
is one at a path its gate never opens, in a root that runs it (#439): every
gate reads fixed paths, so a `contracts/project.yaml` in an assembly root,
or a `contracts/<x>-pin.yaml` no leg and no product names, is the same
FINDING, and its NEXT takes the file out as git has it (#548).

THE ROWS, for an assembly root, in this order:

    merge             only in the middle of a merge: a FINDING naming the
                      index's unmerged paths, or a `note` once nothing is
                      left unmerged; no row at all otherwise (#424)
    naming            the three leg names against the STANDARD's own
                      `contracts/repository-naming.yaml`
    manifest          the project's own `scripts/validate-manifest.py` when it
                      has one -- it is the pinned copy, and that is the point
                      -- else the standard's template copy, and the row says
                      which ran; the template's NEXT line carries the
                      `PYTHONPATH` the doctor ran it under, because it
                      imports `repo_shape` from the standard's `scripts/` and
                      a bare path pasted anywhere else dies on that import,
                      and the project's own copy is run and printed with none,
                      as its own gate runs it (#238)
    pins              the project's own `scripts/validate-pins.py` likewise:
                      the lockstep invariant, and the shape-copy digests
    manifest kinds    every `kind:`-bearing manifest in the root, against
                      MANIFEST_VALIDATORS, the kind of root it is in and the
                      path it sits at
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

and for a FAMILY holder: `merge` likewise, `family` (its own
`scripts/validate-family.py`), `manifest kinds`, `shape currency`,
`placement` (`n/a`: a holder has no legs of its own), `agent files`,
`members` and `machine`. A directory that
is NEITHER gets `naming` (what it is called, under the policy), `what is
here`, `the way in` -- `adopt-project.py plan` for a repository that already
exists, `setup.sh` for a new one -- and `machine`. A git repository is told
of both: `the way in` is its adoption, with `--org <your-org>` where its
`origin` names no organisation `plan` can read, and `the other way in` is the
scaffold (#545); a directory that is not a repository gets the scaffold alone.

A MANIFEST THAT IS THERE AND DOES NOT LOAD IS NOT AN ABSENT ONE (#205). A
`project.yaml` with a merge conflict left in it, a tab, a construct the
reader refuses or a byte that is not UTF-8 used to read as no manifest at
all: an assembly root with both legs mounted was NOT A SHAPE ROOT, exit 2,
told to `adopt-project.py plan` itself and called "a single repository". Now
the FILENAME names the kind where `kind:` cannot be read, the `manifest` row
(`family` in a holder) is a FINDING quoting `load_yaml`'s own refusal with
the project's own validator as its next command, every row that reads what
the manifest declares says `n/a` and waits on that row, and the verdict is
`INVALID (manifest)` -- `(family)` in a holder -- exit 1. A file that loads
and declares its kind still decides first, so no root that declared one
reads differently.

A ROOT IN THE MIDDLE OF A MERGE IS NOT COMPLIANT (#424). The other rows read
the working tree, and a leg's commit from the index -- or from HEAD, for a
gitlink a conflicted merge holds only at stages 1, 2 and 3. That is right
for a validator and wrong for a verdict: a root whose index holds an
unmerged path is one `git commit` refuses, and it read COMPLIANT, exit 0,
once the conflict markers were out of the files those rows read. So the
`merge` row, FIRST on both kinds of root, asks git for the unmerged paths
and is a FINDING naming them, with `git -C <root> status` as its NEXT, and
the verdict is `INVALID (merge)`, exit 1, on a rung above every other but
CANNOT ANSWER (`merge_verdict` says why). A merge with nothing left unmerged
is a `note`: git commits it as it stands. With neither, there is no row.

AND ONE MORE ROW, `Triad`, WHERE THE RULE SAYS SO. Brett Heap, 2026-10-06:
"ratify 1249 as recommended" (openxFactory `prefer-triad-project-shape`):
the Triad -- this shape, an assembly root with a spec leg and a code leg --
is the PREFERRED project shape, it stays elective and confers nothing, and
this report MAY say so. A repository with no manifest gets one row with the
status `advisory`, saying it once; a family holder, a `<user>-wip` workspace
and a repository carrying a `single-repository.yaml` of the right kind get
no row at all; a leg clone gets the instruction to work from its assembly
root instead, and `the way in` offers it no adoption. An assembly root --
an elected Triad, or a broken one its `manifest` row already explains -- is
not asked. The row never moves the verdict -- NOT A SHAPE ROOT is exit 2
with or without it -- because a project's shape is never a review input;
`check_triad_advisory` says the rest.

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

A SUBMODULE IN A LEG IS NOT JUDGED BY ITS PATH (#176). The policy is globs,
and a glob cannot tell a gitlink from a file: a submodule vendored at
`.cursor` or `.specify/vendored` reads as the assistant instructions or the
Spec-Kit tooling the 2026-09-02 ruling roots. But the assembly root keeps no
submodule but its legs, which is why an adoption keeps such a submodule in a
LEG (#166), and a row that called it `root by rule` would fail every project
adopted that way. So the row reads each leg's index MODES in the same one
`git ls-files`, keeps every gitlink out of the classification, and names each
one in a `note`. The ruling still roots the FILES under those paths, and they
are judged as before. A path is a submodule only when EVERY stage the index
holds for it is a gitlink: an unmerged `.cursor` with a file on one side and
a gitlink on the other still has a file in the leg, and it is classified as
one. And a submodule at a path the doctor never judges for a file -- under
`.github/**`, say -- is named all the same, because the row's promise is that
no gitlink a leg keeps goes unreported.

A SUBMODULE IS CHECKED AGAINST THE ANSWER THE ADOPTION RECORDED (#189). Which
leg a submodule belongs in is the adoption plan's answer: `adopt-project.py
plan` asks it of every entry that holds a gitlink (#166), and `execute` writes
each answer for a submodule it keeps in a leg into `project.yaml`, under
`submodules:` -- its path in the leg, the leg, the plan's `resolution:` and
the source commit. A gitlink in the leg its row names is `recorded`: placed,
named in the row, and no reason to keep it off `ok`. One in the OTHER leg is
`misplaced`, and it is a path in the wrong leg like any other -- a FINDING,
counted in MISPLACED, an entry under `paths:` in the plan -- because the
manifest asserts where it belongs, and a FINDING is exactly something else
asserting it. The same record answers the policy's question about a leg's
`.gitmodules` -- which leg owns the submodules it registers -- where it
places every submodule that leg keeps there and the doctor could read every
name the leg holds, so that file is placed too, and an adoption whose record
places every submodule reads `ok`.

WHERE NO ROW NAMES IT, THE NOTE SAYS WHICH KIND OF PLACEMENT IT FOUND (Codex
review on #186, round 2). A project adopted before the record, or one with a
submodule added by hand, has its gitlink in whichever leg it landed in, and
the doctor cannot tell those from an answered one. So the row says what it
CAN tell. A gitlink whose name no rule names, a root rule names, or the rule
of the leg it is in names, is `kept`: the root keeps no source submodule, so
a leg holds it. A gitlink whose name a rule assigns to the OTHER leg --
`docs/theme` in the code leg, under `spec-governance` -- is `unverifiable`:
named with the rule and the leg, in the row, in `--json` (`placement`,
`rule`) and in the plan, with the words "confirm against the plan, or move
it". Both stay a `note`, never MISPLACED, because a human's answer under #166
that nothing recorded looks exactly like the second, and MISPLACED would put
back the false positive #176 removed.

A PATH THE ADOPTION ANSWERED IS NOT ASKED AGAIN (#525). `execute` records the
plan's answer to each question the policy itself asked -- `examples/` under
`ambiguous-examples` -- under `answered_paths:`, one row per entry kept in a
leg. A walked question whose every file one row answers into the leg it is
in is settled: named in the row, in `--json` under `answered_paths`, and no
reason to keep the row off `ok`. A row naming the OTHER leg settles nothing
and asserts nothing: the path stays the question it was, a `note`, and is
never MISPLACED, because a record confers nothing and a file named like one
the adoption put in the other repository is not that file. A row whose path
no leg holds is silent, because it can only settle a question, never make a
finding. And a leg's `.gitmodules` is answered by `submodules:` alone.

AN ANSWER AGAINST A RULE IS NOT MISPLACED (#655). The plan may keep a path in
a leg its rule does not name -- `docs/`, which `spec-governance` puts in the
spec leg, answered `code` with its reason -- and `execute` records that
answer under `answered_paths:` as it records a question's. A walked path in
the wrong leg whose every file one row answers into the leg it is in is
held to the record as a question is: listed under `answered_paths` with the
rule it overrode, said, and never a finding; a row naming the other leg
settles nothing here either. A directory's row answers for every file under
it, one added since the adoption too: no file is held to the row's
`source_commit:`. A row naming a directory of its leg without the `/` a
directory's row ends with answers nothing under it, as a plan entry spelled
so covers nothing, and the leg's entry names it under `unslashed`, said and
never a finding. A row naming a file of its leg WITH that `/` answers nothing
either, since no file is under it (#914): the leg's entry names it under
`slashed`, said the same way.

AN EMPTY `.gitmodules` ASKS NOTHING (#655, #914). One that holds no section
-- no byte, which a plain `git rm` of a leg's only submodule leaves tracked,
or only blank lines, comments and a byte-order mark, which git's own reader
passes over -- registers no submodule, so in a leg that holds none the
policy's question of it has no subject. The leg's entry names it under
`empty_gitmodules`, the row says so and how to remove it, and it is no
question. Beside a submodule of its leg it stays the question it was, since
no section registers that submodule: the leg's entry names each under
`unregistered_submodules`, and the row says how to register it or remove it.
So it does for a submodule beside a `.gitmodules` whose sections register
other paths, and for one in a leg whose index tracks no `.gitmodules`
(#1080), where the leg's entry says which under `unregistered_beside`. There
git reads the one on this disk, untracked, or else HEAD's copy, and so does
the doctor: a submodule that copy registers is not named. A recursive clone
of the leg leaves each empty. The doctor names nothing, though `git
submodule status` counts the submodule unregistered (exit 128), in these
states: beside a `.gitmodules` the index tracks and this disk lacks, where
git reads the index's copy, `git add .gitmodules` would stage the file's
deletion, and no section can be written in it until it is restored (#1093);
for a submodule whose path is not UTF-8 or holds a control character
(`UNWRITABLE_IN_A_PLAN`); beside a `.gitmodules` that is unmerged; and
beside a `.gitmodules` git refuses, or one on this disk that is not a
regular file: a link, which git reads through, or a directory.

A SUBMODULE MOVED OR REMOVED SINCE THE ADOPTION (#525). Its row is a
person's to change, by hand, in the pull request that bumps the pins; no
command rewrites one. Until then a submodule in a leg its row does not name,
where the leg the row names was read and holds no gitlink there, is still
MISPLACED and is said to have MOVED; where every path the row lists is such
a move, or the `.gitmodules` of the leg it moved into, the NEXT is this
doctor again, as for a file only a person can mend, and not a plan of the
move already made, and the WHY gives both ways out. A row whose path no leg
holds a submodule at, every leg read, is a `note`: removing one is not
wrong.

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

AND THE NEXT IS THE COMMAND AND NOTHING ELSE (#277). The sentence saying why
it is the fix -- "read its output in full", "then apply --at ...", "what
`make bootstrap` runs" -- used to ride on the same line as `   # <comment>`,
because a terminal shows both at once. `sh`, bash and `zsh -c` read that `#`
as a comment. An INTERACTIVE zsh without `interactivecomments` -- zsh's
default, and macOS's login shell, the one a person pastes into -- reads it as
a word: the pasted line handed the comment to the command as arguments, ran
whatever followed a `;` as a second command, and ran whatever sat in
backticks, `make bootstrap` among them. So `next` and the `NEXT` line are the
bare command, pasted whole, and the sentence is the row's `why`: a `WHY` line
under `NEXT` in the table, `"why"` on every row of `--json` (null where there
is none), and a line after `Remediation:` when the report cannot answer.

AND ONLY A `FINDING` MOVES THE VERDICT. A row is `ok`, `note`, `FINDING`,
`n/a` or -- the Triad row alone -- `advisory`, and `FINDING` means exactly
"something ELSE asserts this" -- a
validator, a pin row, a manifest, a gitlink. A difference nothing asserts is
a `note`: it is printed, it is in `--json`, and the verdict steps over it.
That line was drawn after this command printed `INVALID` over a live estate
whose every real gate was green, because a leg was missing a `.gitignore`
that entered the standard after the project was scaffolded. A doctor that
invents a rule to fail somebody by is not believed the next time.

EXIT CODES
    0  COMPLIANT: every row ok and the shape is current
    1  findings: the shape is behind, a copy has drifted, a validator is red,
       a leg is off its pin, a manifest is there and does not load, or a
       tracked path sits in a leg the path policy puts elsewhere -- or, for a
       submodule, a leg other than the one `project.yaml` records for it
       (#189) -- COMPLIANT SHAPE BEHIND, DRIFTED, MISPLACED, INVALID.
       INVALID names `merge` alone while the index holds an unmerged path
       (#424); else its red gates, `naming`, `manifest`, `pins`, `family`,
       `manifest-kinds` and `agent-files`; or, when none of them is red,
       every row that is a FINDING. `manifest-kinds` is a FINDING for a
       manifest that does not load, a `kind:` nothing here validates, a kind
       whose gate this root never runs or never reads at that path, a
       `family.yaml` beside `project.yaml`, or a file declaring one kind
       where a gate here reads it as another and none checks the kind it
       declares (#211, #291, #327, #439); `agent-files`, for a pinned agent
       file that is gone
    2  NOT A SHAPE ROOT: neither `project.yaml` nor `family.yaml` is there
    3  usage or environment -- nothing here is a statement about the tree
       that was pointed at: no such root, a root this user cannot search
       (#430), this file is not sitting in a checkout of the standard, or
       THIS CHECKOUT cannot answer (a pin
       naming a commit it does not carry; a partial clone lacking what the
       comparison reads, #683; a validator of its own that crashed or
       cannot be given its `PYTHONPATH`, its template copy or its naming
       script, #278, #410; or its own naming policy not loading, #678)

THE VERDICT NAMES THE MOST SPECIFIC FINDING; THE TABLE NAMES EVERY ONE. Drift
outranks a red validator on that line for one concrete reason: an edited shape
copy is exactly what makes `validate-pins.py` red, so answering `INVALID
(validate-pins.py)` would send the reader at the symptom while the fix is
`update-shape.py`. The pins row is still printed, with its own next command.
MISPLACED sits between the two, under DRIFTED and over INVALID: a path in the
wrong leg is a fact about the SHAPE -- the subject of this whole standard --
that no validator, pin or manifest here can see, whereas a red validator names
itself in the table either way and loses nothing by not being on the verdict
line. An unfinished merge outranks all three, for the reason drift outranks a
red validator: the conflict it leaves is what turns the other rows red, and
none of their fixes can be committed until it is finished.

STANDARD LIBRARY ONLY, like everything else shipped here. The report's own
words are ASCII: a verdict a cp1252 console cannot render is a verdict nobody
reads, and this tool is run on every platform the standard supports. A NAME
is not the report's own words (#785): a path printed in a command is spelled
so that the reader's shell turns it back into that path, as itself where the
output can show it and escaped where it cannot (`quote_arg`), and a sentence
shows it as itself where the output can and with `?` where it cannot
(`ascii_text`).
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import errno
import importlib.util
import json
import os
import re
import shutil
import signal
import stat
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
    #: ONE RULE FOR "IS THIS THE SAME REPOSITORY" (2026-09-12, #155).
    #: `same_repository` is the definition this report's `members` row counts
    #: a working clone by AND the one
    #: `templates/family-root/scripts/siblings.py` REFUSES to fetch into a
    #: clone by -- ONE function now, imported by both, rather than this
    #: file's half of a pair held together by a parity test (#146, #147).
    #: This module is the one file both may read: the doctor imports nothing
    #: out of `templates/`, and `repo_shape.py` is copied in beside
    #: `siblings.py` in every family holder. `redacted` and `resolved_remote`
    #: are the rest of that arithmetic and came with it -- a row that quotes
    #: an `origin` must not publish a token, and a mount declared `../x.git`
    #: is a url only against the root's own remote. `remote_local_path` is the
    #: string half of the one question that rule cannot finish on its own --
    #: which spelling names a path on a disk -- and `same_repository_here`
    #: below is this file's half, because the symlink is on THIS machine
    #: (#157). `url_repository` is the one reading of an `origin` that
    #: `adopt-project.py plan` takes `--org` from, imported here for the same
    #: reason, in place of a copy of `plan`'s regex (`origin_org`, #521).
    #: `spelled` is how `siblings.py` prints the values that row quotes (#673).
    #: `host_shell_dialect` is which shell a printed line is quoted for, the
    #: one question `quote_arg` and `repo_shape.shell_quoted` both ask (#711).
    from repo_shape import (  # noqa: E402
        COMMIT_RE, NamingPolicy, POWERSHELL_SINGLE_QUOTES, PYTHON,
        Refusal, accepts_role, git_out, host_shell_dialect,
        load_yaml, recorded_gitlink, redacted, remote_local_path,
        resolved_remote, same_repository, shown_path, spelled,
        url_repository,
    )
except ImportError as exc:  # pragma: no cover - exercised as a subprocess
    sys.exit(not_in_the_standard(f"scripts/repo_shape.py ({exc})"))

try:
    #: ONE RULE FOR WHAT A LANE IS (2026-09-11, #111). `LANES_LANE` is read
    #: in `scripts/shape_materialize.py` because `update-shape.py` and
    #: `scripts/family.py` -- the two tools that WRITE these trailers -- both
    #: import it already, and a next command that named a different lane than
    #: the commit it asks for would be worse than one that named none.
    from shape_materialize import (  # noqa: E402
        escape_what_stdout_cannot_encode, lane_trailer_argument,
    )
except ImportError as exc:  # pragma: no cover - exercised as a subprocess
    sys.exit(not_in_the_standard(f"scripts/shape_materialize.py ({exc})"))

try:
    #: The policy's own glob dialect, for the one list this file adds to it.
    #: `fnmatch` is not the same dialect -- its `*` crosses `/`, which would
    #: make `LICENSE.*` match `docs/LICENSE.html` -- and a second dialect
    #: beside a policy written in the first is a bug waiting for its file.
    from path_classify import glob_to_regex  # noqa: E402
except ImportError as exc:  # pragma: no cover - exercised as a subprocess
    sys.exit(not_in_the_standard(f"scripts/path_classify.py ({exc})"))

try:
    #: THE TRIAD ADVISORY (openxFactory `prefer-triad-project-shape`, ratified
    #: by Brett Heap on 2026-10-06). One module says it for all three tools
    #: that may, and decides where it is silent, so this report, the scaffold
    #: and the adoption cannot disagree about which repository is told.
    import shape_advisory  # noqa: E402
except ImportError as exc:  # pragma: no cover - exercised as a subprocess
    sys.exit(not_in_the_standard(f"scripts/shape_advisory.py ({exc})"))

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
#: `advisory` is the TRIAD ADVISORY, and nothing else carries it: a
#: repository that has not elected the Triad is told, in this one row, that
#: the Triad is the preferred project shape and that it confers nothing.
#: Ruled by Brett Heap on 2026-10-06 ("ratify 1249 as recommended",
#: openxFactory `prefer-triad-project-shape`), which is also why it can never
#: move the verdict: a project's shape is never a review input, so a row about
#: it that changed an exit code would be the review warning that ruling
#: rejects. `verdict_for` reads `FINDING` and nothing else, so this is stepped
#: over exactly as `note` is -- and it is lowercase for the reason `note` is.
ADVISORY = "advisory"

#: Which kind of root this is. Read from the tree, never taken as a flag, the
#: same rule `update-shape.py`'s `root_kind` follows and for the same reason.
PROJECT = "project"
FAMILY = "family"
NOT_A_ROOT = "none"

#: The manifest FILENAME for each kind -- distinct from `PROJECT`/`FAMILY`
#: above, which are the `kind:` a manifest DECLARES, not what the file is
#: called. `Context.__init__`, `check_naming`, `manifest_candidates`,
#: `working_clone` and the way-in and what-is-here probes all read a root by
#: this name, so it is spelled once for the five of them.
PROJECT_MANIFEST = "project.yaml"
FAMILY_MANIFEST = "family.yaml"

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

#: One name, so `AGENT_FILES`, `LEG_SHAPE_FILES`, `LEG_RENDERED` and the
#: what-is-here probe below stay in agreement about what an agent reads,
#: rather than four spellings of the same fact.
AGENTS_MD = "AGENTS.md"

#: The three files a scaffolded root carries for an agent. `AGENTS-shape.md`
#: is a PINNED shape copy, so the pins and shape-currency rows already digest
#: it; this row is for a reader, who wants to know whether the file is there
#: before reading two digest tables to find out.
AGENT_FILES = ("AGENTS-shape.md", AGENTS_MD, "CLAUDE.md")

#: The leg files this compares, and the ones a byte comparison is meaningless
#: for. `templates/<role>-root/AGENTS.md` and `README.md` carry
#: `{{PLACEHOLDER}}`s the scaffold renders per project, so "differs" is what
#: they are BY CONSTRUCTION; `CLAUDE.md` and `.gitignore` are verbatim and a
#: comparison of them is a fact. No leg file has a digest row anywhere today
#: -- only the assembly root's copies are pinned -- so this row reports and
#: does not judge, beyond a file that is missing altogether.
LEG_SHAPE_FILES = (AGENTS_MD, "CLAUDE.md", ".gitignore")
LEG_RENDERED = (AGENTS_MD, "README.md")

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

#: A GITLINK's mode, as `git ls-files --stage` prints it: a submodule's commit
#: recorded in the tree of the repository that holds it. It is the one thing
#: that tells a submodule at `.cursor` from a file or a directory of that
#: name, because the path policy reads names and never a mode (#176).
GITLINK_MODE = "160000"

#: What the `placement` row says about each submodule it finds in a leg, in
#: `--json` and in the plan. A NOTE AND NOT A QUESTION. The question of which
#: leg a submodule belongs to is asked when a repository is ADOPTED, by
#: `adopt-project.py plan`, and whoever adopted this one has answered it.
#: Asked again of a project already split, it would be an answered question
#: put back on every run, and the one its name draws from this policy is
#: `default`'s, which offers `root` -- not an answer for a submodule.
#:
#: FOUR CLASSES, SAID APART. A submodule's leg is the adoption plan's answer,
#: and `execute` records each one it keeps in a leg in `project.yaml`'s
#: `submodules:` (#189). `recorded` is a submodule in the leg its row names,
#: and `misplaced` one in the other leg: the manifest asserts where it
#: belongs, so the second is a FINDING. Where no row names its path -- a
#: project adopted before the record, a submodule added by hand -- the row
#: says only what the policy can tell it (Codex review on #186, round 2).
#: `kept` is a submodule whose name no rule claims, a root rule claims, or the
#: rule of the leg it is in claims: the root keeps no source submodule, so a
#: leg holds it, and there is nothing to check it against. `unverifiable` is
#: one whose name a rule assigns to the OTHER leg: that may be the person
#: adopting having answered the question the other way, and may be nobody
#: having answered it, and with no record the doctor cannot tell. Neither of
#: those two is MISPLACED -- that is the false positive #176 removed.
SUBMODULE_RECORDED = "recorded"
SUBMODULE_MISPLACED = "misplaced"
SUBMODULE_KEPT = "kept"
SUBMODULE_UNVERIFIABLE = "unverifiable"
KEPT_SUBMODULE = ("a submodule; the assembly root keeps no source submodule "
                  "(#166), so a leg holds it")
#: Where the record is, said the same way in the row, `--json` and the plan.
THE_RECORD = "project.yaml's `submodules:`"
#: The key naming the leg the record gives a submodule, in `--json` and the
#: plan alike; present only on a submodule a record names.
RECORDED_LEG = "recorded_leg"
#: The key that marks a `misplaced` entry as a submodule the record puts in
#: the other leg, rather than a file the policy judged.
AGAINST_THE_RECORD = "submodule"
#: The key of a leg's entry naming the paths whose policy question the record
#: answered -- its `.gitmodules` -- present only on a leg that has one.
ANSWERED = "answered"
#: Where the plan's answers to the policy's own questions are (#525), said
#: the same way in the row and in `--json`.
THE_ANSWERS = "project.yaml's `answered_paths:`"
#: The key under `detail`, and under `counts`, of the questions that record
#: answered (#525); present only where it answered one.
ANSWERED_PATHS = "answered_paths"
#: The key that marks a `misplaced` submodule as one its recorded leg no
#: longer holds (#525); present only on one.
MOVED = "moved"
#: The key under `detail`, and under `counts`, of the `submodules:` rows no
#: leg holds (#525); present only where there is one.
UNHELD = "unheld"
#: The key of a leg's entry naming its `.gitmodules` where that file holds
#: no section and the leg no submodule, so the policy has nothing to ask of
#: it (#655, #914); present only on a leg that has one.
EMPTY_GITMODULES = "empty_gitmodules"
#: The key of a leg's entry naming each submodule it holds beside a
#: `.gitmodules` that holds no section, so that nothing registers it (#914),
#: or beside one whose sections register other paths, or in a leg whose
#: index tracks none (#1080); present only on a leg that has one.
UNREGISTERED_SUBMODULES = "unregistered_submodules"
#: The key of a leg's entry saying what its `unregistered_submodules` sit
#: beside where that is not a `.gitmodules` with no section (#1080): one
#: of the two values below. Absent beside one with no section, so that the
#: entry #914 gives stays as it was; present only on a leg that has one.
UNREGISTERED_BESIDE = "unregistered_beside"
#: A `.gitmodules` with sections, none of which registers the submodule.
BESIDE_OTHER_SECTIONS = "other_sections"
#: The leg's index tracks no `.gitmodules`, and the copy git reads instead,
#: untracked on this disk or else HEAD's, does not register the submodule,
#: or there is none.
BESIDE_NO_GITMODULES = "no_gitmodules"
#: The key of a leg's entry naming each `answered_paths:` row for that leg
#: whose path is a directory of it written without its `/` (#655); present
#: only on a leg that has one.
UNSLASHED = "unslashed"
#: The key of a leg's entry naming each `answered_paths:` row for that leg
#: whose path is a file of it written with the `/` a directory's row ends
#: with (#914); present only on a leg that has one.
SLASHED = "slashed"
#: The `why` of a row whose every path in the wrong leg is a submodule moved
#: since the adoption (#525). Its NEXT is this doctor again, as the
#: `manifest kinds` row's is for a file only a person can mend
#: (`UNREADABLE_BY_HAND`): no command makes either way out.
MOVED_BY_HAND = (
    "each submodule above is in a leg its row in project.yaml's "
    "`submodules:` does not name, and the leg the row names no longer holds "
    "it, so it was moved. Moved on purpose, its row is a person's to change "
    "by hand, in the pull request that bumps the pins: `leg:` to the leg it "
    "is in, `resolution:` to why, and `source_commit:` deleted, which records "
    "what both legs already carry. Moved by mistake, it goes back: a pull "
    "request on each leg and a pin bump in the root. This row reads it again "
    "once either is done")

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


#: The typography this repository's prose is written in, and the ASCII
#: `ascii_text` spells each one with. `quote_arg` never prints one of them as
#: itself in a value (#785): `Row.__init__` passes every command and every
#: `why` through `ascii_text`, which would make the value another path.
FLATTENED = {"—": "--", "–": "-", "‘": "'", "’": "'", "“": '"', "”": '"',
             "…": "...", "\N{NO-BREAK SPACE}": " "}


#: The encoding the report is written for where that is not stdout's: UTF-8
#: for `--json`, which `main` sets (#785, review S2 on PR #792). `json.dumps`
#: writes ASCII whatever stdout's encoding is, and every character as an
#: escape its reader decodes, so a JSON reader gets each character a UTF-8
#: name holds as itself -- under `LC_ALL=C` and a `PYTHONIOENCODING=cp1252`
#: pipe as under a UTF-8 terminal. None for the table, which IS stdout.
REPORT_ENCODING: str | None = None


def printed_encoding(encoding: str | None = None) -> str:
    """`encoding`, or the one the report is written for: `REPORT_ENCODING`
    where `main` set one, else `sys.stdout`'s, which `pythonw` and a stream
    a caller replaced may not have (#785)."""
    return (encoding or REPORT_ENCODING
            or getattr(sys.stdout, "encoding", None) or "utf-8")


def prints_as_itself(char: str, encoding: str) -> bool:
    """Whether a report written in `encoding` shows `char` as itself (#785):
    a printable character that `ascii_text` does not flatten, and that the
    encoding writes and reads back unchanged.

    PRINTABLE, because a control, a line separator or a bidirectional mark
    is not seen as itself on any terminal: it moves the line it is printed
    on, and a reader cannot copy what they cannot see. And not U+FFFD, the
    mark a lossy read leaves where a byte did not decode, which a row has
    printed as `?` since #385: it stands for no character a path holds."""
    if (char in FLATTENED or char == "\N{REPLACEMENT CHARACTER}"
            or not char.isprintable()):
        return False
    try:
        return char.encode(encoding).decode(encoding) == char
    except (UnicodeError, LookupError):
        return False


def ascii_text(text: str, encoding: str | None = None) -> str:
    """`text` with the typography this repository is written in flattened,
    and each character the report cannot show as itself replaced by `?`.

    Validator output is quoted into rows, and this repository's prose is full
    of em dashes, curly quotes and ellipses. A Windows console in the machine's
    ANSI code page raised on the first of them, in the middle of a report whose
    whole job is to be read -- so the few characters that actually occur are
    spelled out in ASCII on every console.

    ANY OTHER CHARACTER IS REPLACED ONLY WHERE IT CANNOT BE SHOWN (#785). It
    was replaced on every console, so `é` was `?` under a UTF-8 locale, whose
    terminal shows it, and so was every character of a path `quote_arg` had
    quoted for a command: a keep line named `caf?`, which is not there. Now a
    character is kept where `prints_as_itself` says `encoding` (the report's
    own when None, `printed_encoding`) shows it, and is `?` elsewhere, as
    every one was: an ASCII console still reads an ASCII report, and a UTF-8
    one reads the name. A value `quote_arg` spelled holds no character this
    changes, so this pass leaves it whole.
    """
    for source, target in FLATTENED.items():
        text = text.replace(source, target)
    encoding = printed_encoding(encoding)
    return "".join(char if char.isascii() or prints_as_itself(char, encoding)
                   else "?" for char in text)


def path_bytes(char: str) -> bytes:
    """The bytes one character of a path stands for on a POSIX disk (#785).

    A byte of a name that is not in the encoding it was read with is carried
    by `surrogateescape` as U+DC80..U+DCFF, how `os.fsdecode` reads a path
    and how this file reads one git prints, and stands for that byte. Any
    other character is in the filesystem encoding, which is how Python names
    a path on disk, or in UTF-8 where that encoding has no such character,
    which is how git wrote a name it printed (`LC_ALL=C` with Python's
    UTF-8 mode off makes the filesystem encoding ASCII)."""
    if 0xDC80 <= ord(char) <= 0xDCFF:
        return bytes([ord(char) - 0xDC00])
    try:
        return char.encode(sys.getfilesystemencoding())
    except UnicodeEncodeError:
        return char.encode("utf-8", "surrogatepass")


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


def quote_arg(value, platform: str | None = None, *,
              always: bool = False, encoding: str | None = None) -> str:
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

    A VALUE THAT IS NOT ASCII IS SPELLED AS THE PATH IT IS (#785). It was
    flattened to ASCII first (Copilot, PR #102), because `Row.__init__`
    runs `ascii_text` again over the whole assembled command, and a curly
    apostrophe that pass found came out of it bare, breaking the quoting it
    sat in. But the flattening named another path: every character that is
    not ASCII became `?`, so a keep line under `Projets/Équipe` named
    `Projets/?quipe`, which is not there, and the pasted line failed. Now
    each character of such a value is one of two things:

    - ITSELF, inside the quoting above, where `prints_as_itself` says the
      report shows it: printable, not one of the typography `ascii_text`
      flattens, and written by `encoding` (the report's own when None,
      `printed_encoding`) -- for `sh`, as the very bytes the path holds
      (`path_bytes`), so that what a terminal shows is what it pastes back;
    - ESCAPED otherwise, and then the whole value is spelled that way. For
      `sh` that is `$'...'`, every byte of such a character a three-digit
      octal escape (`$'caf\303\251'`, `$'caf\351'` for a name that is not
      UTF-8), which bash, zsh, ksh and a POSIX.1-2024 `sh` turn back into
      those bytes; dash 0.5.12 (Ubuntu's `/bin/sh`, whose login shell is
      bash) reads the `$` as itself. For PowerShell, which has no escape
      inside a verbatim string, it is an expression in parentheses,
      `('C:\Users\' + [char]0x00C9 + 'quipe')`, which is one argument to a
      native command and a value to assign alike (`powershell_expression`).
      On Windows that is rare: Python writes a console as UTF-8, which shows
      every printable character, and only a stdout redirected to a file or a
      pipe is in the ANSI code page.

    So `ascii_text`'s later pass finds nothing in a value to change. The
    report's encoding is stdout's for the table, and UTF-8 for `--json`,
    whatever stdout's is (`REPORT_ENCODING`, review S2 on PR #792): a JSON
    reader decodes each `\u` escape `json.dumps` writes into the character
    it stands for, so a row's `next` holds a UTF-8 name as itself, and only
    a byte that is not UTF-8, or a character `prints_as_itself` refuses, is
    escaped there. The table escapes what its own encoding cannot write. A
    value made of ASCII is quoted exactly as before, in both.

    AND THE ALPHABET CHECK MUST COVER THE VALUE WHOLE. `$` is content to
    match just before a trailing newline, so `.match` alone waved a value
    like `"Atlas\n"` through bare, newline and all -- true to the pattern
    and false to the point of it (Copilot, PR #102). `.fullmatch` is what
    actually requires every character to be in the alphabet, not only the
    ones before wherever `$` was willing to stop.

    `always` QUOTES A VALUE THE ALPHABET WOULD LEAVE BARE, and exists for the
    one position where bare is not a value at all: the right-hand side of a
    PowerShell assignment. `$env:PYTHONPATH = C:\shape\scripts` is not the
    string `C:\shape\scripts`, it is an attempt to RUN it, because what
    follows `=` is a pipeline and a bareword in one is a command name (#238).
    Every other position this file interpolates into is an argument, where
    bare is the value; so it is off unless a caller asks, and the quoting
    itself is still this function's alone -- one place that knows the
    apostrophe is doubled, rather than a second copy of the rule beside the
    one that needs it.

    A WORD THAT BEGINS WITH `=` IS QUOTED IN `sh`'S DIALECT (#532). zsh, the
    login shell macOS ships, expands a bare `=word` to the path of the
    command `word` (its EQUALS option, on by default): `zsh -f -c 'echo =ls'`
    prints `/usr/bin/ls`, and `=x` stops the line with `x not found`. bash
    and dash read it as itself, and `=` anywhere but the front is itself to
    every shell, so only a leading one is quoted. It stood in
    `UNQUOTED_POSIX` as an ordinary character, and reached a line only as a
    value that starts with one (a branch named `=x`), which is the gap #460
    named. `repo_shape.shell_quoted` quotes it already (#486, #507), and
    `tests/test_family_printed_quoting.py` holds the two quoters to one
    answer. PowerShell's dialect is NOT changed: it expands no `=word`, so
    `UNQUOTED_NT` keeps its bare `=`, as in any other place in a word.

    NO `platform` IS THE SHELL THE DOCTOR RUNS IN, which
    `repo_shape.host_shell_dialect` answers, the question
    `repo_shape.shell_quoted` asks too (#711): PowerShell's dialect on
    Windows, and `sh`'s under Git Bash, where `MSYSTEM` is set, and
    everywhere else. It used to be `os.name`, which is `nt` under Git Bash
    as well, so Git Bash was handed lines quoted for PowerShell.
    """
    text = str(value)
    windows = (host_shell_dialect() if platform is None
               else platform) == "nt"
    if not text.isascii():
        # Never bare: neither alphabet holds a character that is not ASCII.
        return quoted_beyond_ascii(text, windows, printed_encoding(encoding))
    # `.fullmatch`, not `.match`: a pattern ending in `$` still matches just
    # before a trailing newline, so `.match` alone would call "Atlas\n" bare
    # (Copilot, PR #102). And a leading `=` is never bare for `sh` (#532).
    if not always and (UNQUOTED_NT if windows else UNQUOTED_POSIX).fullmatch(
            text) and (windows or not text.startswith("=")):
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


def quoted_beyond_ascii(text: str, windows: bool, encoding: str) -> str:
    """`quote_arg` for a value holding a character that is not ASCII (#785):
    quoted as any other value where every such character `prints_as_itself`
    -- for `sh`, as the bytes the path holds -- and escaped whole where one
    does not. See `quote_arg`'s docstring.

    ON POSIX A NAME IS READ AS UTF-8 FIRST (review S2 on PR #792). Under
    `LC_ALL=C` with Python's UTF-8 mode off the filesystem encoding is
    ASCII, so `os.fsdecode` carries each byte of `é` as a `surrogateescape`
    byte of its own, and a report in UTF-8 -- `--json` -- could not show
    it. Those bytes are read again as UTF-8, which joins each run that
    spells a character into that character and leaves every other byte as
    it was. A value that holds a surrogate `surrogateescape` never makes
    (outside U+DC80..U+DCFF) cannot be written back to bytes like that, and
    is left as it is: such a character is not printable, so it is escaped.

    AND THE JOINED NAME IS KEPT ONLY WHERE IT NAMES THE SAME BYTES (review
    M1 on PR #792, round 2). `path_bytes` writes a joined character in the
    filesystem encoding, which is ASCII or UTF-8 under `C` and gives the
    bytes back; but under a legacy multibyte one -- EUC-JP, Big5, EUC-KR --
    a directory named `日` in UTF-8 (`\\xe6\\x97\\xa5`) is read in as three
    escaped bytes, and the joined `日` is written `\\xc6\\xfc` in EUC-JP:
    another directory. So the join is checked byte for byte against the
    value as it was read, and the escaped bytes stay where it differs."""
    if not windows:
        try:
            joined = text.encode("utf-8", "surrogateescape").decode(
                "utf-8", "surrogateescape")
        except UnicodeEncodeError:
            joined = text
        if (b"".join(map(path_bytes, joined))
                == b"".join(map(path_bytes, text))):
            text = joined

    def shown(char: str) -> bool:
        if char.isascii():
            return True
        if not prints_as_itself(char, encoding):
            return False
        return windows or char.encode(encoding) == path_bytes(char)
    if all(shown(char) for char in text):
        if windows:
            return powershell_verbatim(text)
        return "'" + text.replace("'", "'\\''") + "'"
    if windows:
        return powershell_expression(text, shown)
    return "$'" + "".join(
        char if char.isascii() and char.isprintable() and char not in "\\'"
        else "".join(f"\\{byte:03o}" for byte in path_bytes(char))
        for char in text) + "'"


def powershell_verbatim(text: str) -> str:
    """`text` in PowerShell's verbatim string, each of the single quotes
    PowerShell reads as one doubled, as `repo_shape.shell_quoted` doubles
    them: the curly ones end the string too (#486)."""
    return "'" + "".join(char * 2 if char in POWERSHELL_SINGLE_QUOTES
                         else char for char in text) + "'"


def powershell_expression(text: str, shown) -> str:
    """`text` as a PowerShell expression, `('...' + [char]0x00C9 + '...')`,
    where a character of it is not `shown` (#785).

    Each such character is a `[char]` of each of its UTF-16 code units, and
    the characters between them are verbatim strings, joined by `+`. The
    FIRST operand is always a string -- `''` where the value starts with an
    escaped character -- because `+` on two `[char]`s adds them as numbers,
    and a string on the left makes every `+` after it a concatenation. A
    printable ASCII character is always shown; a control is escaped too, as
    it is in `sh`'s `$'...'`."""
    parts, run = [], ""
    for char in text:
        if char.isprintable() and shown(char):
            run += char
            continue
        if run or not parts:
            parts.append(powershell_verbatim(run))
            run = ""
        units = char.encode("utf-16-le", "surrogatepass")
        for at in range(0, len(units), 2):
            unit = int.from_bytes(units[at:at + 2], "little")
            parts.append(f"[char]0x{unit:04X}")
    if run:
        parts.append(powershell_verbatim(run))
    return "(" + " + ".join(parts) + ")"


# ---------------------------------------------------------------------------
# A row, a check, and the registry they live in
# ---------------------------------------------------------------------------


class Row:
    """One line of the report: what was asked, the answer, and the exit.

    `next_command` IS A COMMAND, WHOLE, AND `why` IS WHAT IS SAID ABOUT IT
    (#277). The two were one string, `<command>   # <why>`, and the `#` is a
    comment only to a shell that reads it as one: pasted into an interactive
    zsh it was a word, the comment's text became arguments, a `;` in it ran a
    second command and a pair of backticks ran a third. So a builder hands
    the sentence over as `why`, a keyword of its own, and `next_command`
    holds only what a reader pastes. `why` is never folded back into the
    command line: `report` prints it on a `WHY` line of its own and `as_dict`
    as its own key.
    """

    def __init__(self, check_id: str, label: str, status: str, reason: str,
                 next_command: str | None = None, detail: dict | None = None,
                 *, why: str | None = None):
        self.id = check_id
        self.label = label
        self.status = status
        self.reason = ascii_text(reason)
        # `quote_arg` spells every value it quotes in characters this pass
        # keeps -- each one itself only where `ascii_text` keeps it, and the
        # value escaped otherwise (#785) -- so this pass has nothing to do
        # to a value in a `next_command` or a `why`. It only does its
        # ordinary job, flattening this repository's own typography, on the
        # literal words a caller wrote around those values.
        self.next_command = ascii_text(next_command) if next_command else None
        #: The sentence that explains `next_command`, kept off its line.
        self.why = ascii_text(why) if why else None
        #: Structured facts for `--json`, so a caller reads numbers rather
        #: than parsing the sentence a human is meant to read.
        self.detail = detail or {}

    def as_dict(self) -> dict:
        # `why` ON EVERY ROW, null where there is none, so a caller reads a
        # key rather than testing for its absence -- as `placement_plan` is.
        return {"id": self.id, "label": self.label, "status": self.status,
                "reason": self.reason, "next": self.next_command,
                "why": self.why, "detail": self.detail}


class Check:
    """One question this command knows how to ask.

    `fix` IS THE SLOT A REPAIR MODE HANGS OFF, and it is `None` for every check
    in this file today. A later `--doctor <path> --fix` calls it only after printing
    the plan
    and getting the human's yes -- the same posture `update-shape.py apply`
    takes, for the same reason: putting a repository back into shape rewrites
    somebody's tree.

    `run` RETURNS ONE ROW, OR NONE FOR A CHECK THAT IS SILENT BY RULE. Two
    checks are: the Triad advisory, which the ratified rule makes SILENT in an
    elected Triad, a family holder, a `<user>-wip` workspace and a project
    that recorded staying single -- and silent means no row at all, not a row
    saying so -- and `merge`, which speaks only while a merge is unfinished
    (#424). `run_checks` skips a None.
    """

    def __init__(self, check_id: str, label: str, applies_to: tuple,
                 run, fix=None):
        self.id = check_id
        self.label = label
        self.applies_to = applies_to
        self.run = run
        self.fix = fix


#: Each kind of root that carries manifests, as a sentence names it: the
#: `manifest kinds` row says where a validator runs in these words (#327).
ROOT_IN_WORDS = {PROJECT: "an assembly root", FAMILY: "a family holder"}


class ManifestKind:
    """One `kind:` this standard knows a validator for.

    `covered_by` is the ids of the CHECKS that validate it, one for each kind
    of root it is validated in, so the row about manifest kinds can say where
    a kind was answered rather than merely that it was recognised. A kind
    with no entry here is a FINDING by name: a manifest nobody validates is
    the gap this table exists to close.

    AND A KIND IS ANSWERED ONLY WHERE ONE OF THOSE CHECKS RUNS (#327).
    `runs_in` reads each check's `applies_to` out of `CHECKS`, so this table
    names checks and the registry alone says which root runs each of them --
    there is no second list of root kinds here to drift from it. The `family`
    check applies to a holder and to nothing else, so `family-manifest` is
    answered in a holder only, and a `contracts/family.yaml` in an assembly
    root is a manifest no gate there reads; `manifest` likewise, so a
    `contracts/project.yaml` in a holder is one too. The other kinds a holder
    carries are answered there by `family`: its `validate-family.py` reads
    `contracts/shape-pin.yaml` and loads the naming policy itself.

    `home` is the other exit for a manifest found in a root that never runs
    its gate: a root of the kind that does, named by the commands that make
    one. Only the two kinds a root of the other kind can hold need one. It
    is one sentence on every platform, so it names `setup-project.py` beside
    `setup.sh`, which is a bash script Windows cannot run -- the reason
    `scaffold_command` spells that line per platform (Copilot, PR #102).

    AND ONLY AT A PATH THAT CHECK READS (#439). Each gate opens fixed paths:
    `validate-manifest.py` the root's `project.yaml` (and the naming policy
    at `contracts/repository-naming.yaml`), `validate-pins.py` the shape pin
    and each pin `project.yaml` declares, `validate-family.py` the holder's
    `family.yaml`, the shape pin and the naming policy. So a
    `contracts/project.yaml` in an assembly root, or a
    `contracts/release-pin.yaml` that no leg and no product names, is read
    by nothing, though its kind's check runs here. `read_at(ctx)` says where
    the check that runs here reads the kind, as root paths, and
    `check_manifest_kinds` counts a file `validated` only at one of them.
    None is a kind this row does not decide by path:
    `path-classification-policy`, which the registry covers with this row
    itself, and a pin in an assembly root whose `project.yaml` does not
    load, which declares nothing this run can read (`pins_read_here`).
    """

    def __init__(self, kind: str, covered_by: tuple, how: str,
                 home: str | None = None, read_at=None):
        self.kind = kind
        self.covered_by = covered_by
        self.how = how
        self.home = home
        self.read_at = read_at

    def runs_in(self) -> tuple:
        """The kinds of root a check that `covered_by` names runs on."""
        return tuple(root for root in ROOT_IN_WORDS
                     if any(check.id in self.covered_by
                            and root in check.applies_to
                            for check in CHECKS))

    def reads(self, ctx: Context) -> set | None:
        """The root paths a check that runs here reads this kind at, or None
        where this row does not decide by path (#439)."""
        return None if self.read_at is None else self.read_at(ctx)


#: Where an assembly root keeps the naming policy `validate-manifest.py`
#: reads, and a holder the one `validate-family.py` reads (#439). The same
#: path in the standard is the policy the `naming` rows read (#678).
NAMING_COPY = "contracts/repository-naming.yaml"

#: The standard's own naming script, the one both `naming` rows run (#410).
NAMING_SCRIPT = "scripts/validate-repository-naming.py"


def own_pins(ctx: Context) -> set:
    """The pins the shape itself writes in this kind of root, whatever its
    manifest declares: the shape pin, and in an assembly root
    `contracts/<role>-pin.yaml` for each role the schema has (review of PR
    #555).

    A leg's role is the schema's, and `validate-manifest.py` refuses any
    other (`manifest-roles`). So a `- role: specs` typo leaves
    `contracts/spec-pin.yaml` the spec leg's pin, which the gate reads again
    once the typo is fixed, and not a file nothing reads: `declared_pins`
    alone named `contracts/specs-pin.yaml`, and the row's NEXT took the
    real pin out, over a manifest the `manifest` row already names.
    """
    if ctx.kind == FAMILY:
        return {SHAPE_PIN}
    return {SHAPE_PIN} | {f"contracts/{role}-pin.yaml" for role in LEG_ROLES}


def pins_read_here(ctx: Context) -> set | None:
    """Where this root's gate reads a `pinned_contract_manifest` (#439).

    In a holder, `validate-family.py` reads the shape pin and no other: a
    holder has no legs and declares no product. In an assembly root,
    `validate-pins.py` reads `declared_pins` -- the shape pin, a pin per leg
    and a pin per `neutral_product_pins:` entry -- and `own_pins` are
    counted read whatever the legs declare. Where `project.yaml` does not
    load, it declares nothing this run can read, and None leaves every pin
    counted as before: a pin called read by nothing would be a NEXT that
    takes it out, over a manifest the `manifest` row already names.
    """
    if ctx.kind == FAMILY:
        return own_pins(ctx)
    if ctx.manifest_refusal is not None:
        return None
    return own_pins(ctx) | declared_pins(ctx)


def kinds_read_here(ctx: Context) -> dict:
    """`{path: kind}`: every root path a gate that runs here reads a file
    at, and the kind it reads that file as -- each kind's `read_at`, for the
    kinds whose check runs on this root, and `own_pins` as pins (review of
    PR #555).

    A FILE AT ONE OF THESE PATHS IS NEVER `unread`, AND THE NEXT NEVER TAKES
    IT OUT, whatever this row finds in it. A `contracts/repository-naming.yaml`
    declaring `kind: pinned_contract_manifest` called read by nothing got a
    NEXT that took out the file `validate-manifest.py` reads. What is wrong
    with such a file is the kind it declares, and the row says which kind
    that path is read as (`taking_out`).
    """
    kinds = {pin: "pinned_contract_manifest" for pin in own_pins(ctx)}
    for kind, entry in MANIFEST_VALIDATORS.items():
        if ctx.kind in entry.runs_in():
            kinds.update((path, kind) for path in entry.reads(ctx) or ())
    return kinds


def kind_checked_by(ctx: Context) -> dict:
    """`{path: row}`: the paths whose gate refuses a file declaring another
    kind than it reads the path as, and the row that runs that gate (review
    of PR #555, round 2).

    ONLY THESE, because the row says that gate judges the file, and that
    has to be true. `validate-pins.py` checks the `kind:` of each LEG pin
    `project.yaml` declares (`pin-wrong-kind`), and `NamingPolicy.load`,
    which `validate-manifest.py` and `validate-family.py` both call, that of
    the naming policy (`policy-wrong-kind`). Nothing checks the kind of the
    shape pin (`_check_shape_pin_header` reads its fields, not its kind), of
    a neutral product pin, or of `contracts/spec-pin.yaml` while no leg
    declares the role `spec`. And where the root's own manifest does not
    load, its gate stops there and checks nothing. For every other path in
    `kinds_read_here`, this row is the one that says the kind is wrong.
    """
    if ctx.manifest_refusal is not None:
        return {}
    if ctx.kind == FAMILY:
        return {NAMING_COPY: "family"}
    checked = {NAMING_COPY: "manifest"}
    checked.update((f"contracts/{leg['role']}-pin.yaml", "pins")
                   for leg in ctx.legs()
                   if isinstance(leg.get("role"), str) and leg["role"])
    return checked


MANIFEST_VALIDATORS: dict[str, ManifestKind] = {
    "project-manifest": ManifestKind(
        "project-manifest", ("manifest",), "scripts/validate-manifest.py",
        "an assembly root of its own (`setup.sh`, or `setup-project.py` on "
        "Windows, for a new one; `adopt-project.py plan` for a repository "
        "that exists), which a holder pins with `family.py add`",
        read_at=lambda ctx: {PROJECT_MANIFEST}),
    "family-manifest": ManifestKind(
        "family-manifest", ("family",), "scripts/validate-family.py",
        "a family holder of its own (`family.py init`, then `family.py add` "
        "there)", read_at=lambda ctx: {FAMILY_MANIFEST}),
    "pinned_contract_manifest": ManifestKind(
        "pinned_contract_manifest", ("pins", "family"),
        "scripts/validate-pins.py (or validate-family.py in a holder)",
        read_at=pins_read_here),
    "repository-naming-policy": ManifestKind(
        "repository-naming-policy", ("naming", "family"),
        "scripts/validate-repository-naming.py, through NamingPolicy.load "
        "(validate-family.py, through the same, in a holder)",
        read_at=lambda ctx: {NAMING_COPY}),
    "path-classification-policy": ManifestKind(
        "path-classification-policy", ("manifest-kinds",),
        "scripts/path_classify.py reads it; nothing validates it in a root"),
}


# ---------------------------------------------------------------------------
# The context every check is handed
# ---------------------------------------------------------------------------


class Context:
    """The root, what it is, and the few things every check would recompute.

    `manifest_refusal` IS SET FOR ONE KIND OF ROOT ONLY (#205): a project or a
    family whose manifest is THERE and does not load. Its kind is then the
    one its filename says, `manifest` is None, and the refusal `load_yaml`
    gave is kept whole for the row that owns the file to quote.
    """

    def __init__(self, root: Path):
        self.root = root
        self.shape = SHAPE_ROOT
        self.manifest_path: Path | None = None
        self.manifest: dict | None = None
        self.manifest_refusal: Refusal | None = None
        self.kind = NOT_A_ROOT
        self._update_shape = None
        self._adopt = None
        project = root / PROJECT_MANIFEST
        family = root / FAMILY_MANIFEST
        # Each manifest that is there, read ONCE: what it holds, or why
        # `load_yaml` would not hand it over.
        loaded = {path: self._load(path) for path in (project, family)
                  if self._to_load(path)}

        def declares(path: Path, kind: str) -> bool:
            data = loaded.get(path, (None, None))[0]
            return isinstance(data, dict) and data.get("kind") == kind

        # `kind:` DECIDES, not the filename. A `project.yaml` that declares
        # something else is not a project manifest, and reading the name alone
        # would let a file called the right thing assert whatever it liked.
        if declares(project, "project-manifest"):
            self.kind, self.manifest_path = PROJECT, project
        elif declares(family, "family-manifest"):
            self.kind, self.manifest_path = FAMILY, family
        else:
            # AND WHERE `kind:` CANNOT BE READ AT ALL, THE FILENAME DOES
            # (#205). A manifest that is there and does not load -- a merge
            # conflict left in it, a tab, a construct this reader refuses, a
            # byte that is not UTF-8 (#192) -- used to read as NO manifest,
            # so an assembly root with both legs mounted was NOT A SHAPE
            # ROOT, exit 2, offered `adopt-project.py plan`: an act that cuts
            # two new legs out of a repository that already has them, two
            # rows above a Triad row calling it "a single repository". A file
            # that is there is not a file that is absent. The root is the
            # kind its filename names, it has no manifest to read, and the
            # refusal is kept for the `manifest` (or `family`) row to quote.
            # A file that loads and DECLARES its kind still outranks one that
            # cannot be read, which is why this is the `else`: a holder with
            # a broken stray `project.yaml` beside a good `family.yaml` is
            # the holder its `family.yaml` says it is.
            for path, kind in ((project, PROJECT), (family, FAMILY)):
                refusal = loaded.get(path, (None, None))[1]
                if refusal is not None:
                    self.kind, self.manifest_path = kind, path
                    self.manifest_refusal = refusal
                    break
        if self.manifest_refusal is None and self.manifest_path is not None:
            data = loaded[self.manifest_path][0]
            self.manifest = data if isinstance(data, dict) else None

    @staticmethod
    def _to_load(path: Path) -> bool:
        """Whether the root's manifest `path` is read at all: a regular file
        (`is_a`), or a name whose `stat` the operating system REFUSED, which
        `_load` then meets as `load_yaml` meets a file it cannot open, so the
        `manifest` (or `family`) row names it (#430).

        A `project.yaml` that is a link into a folder this user cannot search
        ended this report in a `PermissionError` traceback on Python 3.12, exit
        1, and on 3.14, where `is_file()` answers False to any `OSError`, was
        no manifest at all: NOT A SHAPE ROOT, exit 2, with `adopt-project.py
        plan` as its NEXT, over a project. A file that is there is not a file
        that is absent (#205), and one the system will not `stat` is not
        absent either: it is the same refusal as one at mode 000."""
        try:
            return is_a(path, stat.S_ISREG)
        except OSError:
            return True

    @staticmethod
    def _load(path: Path) -> tuple:
        """`(what the file holds, None)`, or `(None, the refusal)`.

        `load_yaml` already turns every way a file can fail to become data
        into a `Refusal` -- not openable and not UTF-8 as `yaml-unreadable`
        (#193), not this reader's YAML as `yaml-unparsable` -- so the refusal
        IS the answer for a file that is there, and the caller decides
        whether it matters. For the root's own manifest it does (#205).
        """
        try:
            return load_yaml(path), None
        except Refusal as exc:
            return None, exc

    @staticmethod
    def _read(path: Path):
        try:
            return load_yaml(path)
        except (Refusal, OSError, UnicodeDecodeError):
            return None

    def legs(self) -> list[dict]:
        """The non-assembly legs `project.yaml` declares, in its own order.

        A `legs:` THAT IS NOT A LIST DECLARES NO LEG THIS CAN NAME (#832), as
        `validate-manifest.py` reads it (#714), and an entry that is not a
        mapping is no leg; `legs_unread` says each. Iterated as `legs or []`,
        `legs: 5` ended the whole report in a `TypeError`, in `declared_pins`
        under the `manifest kinds` row, and a scalar `openXdox` or a mapping
        was walked one character, or one key, at a time, so the `legs` row
        called the project one with no legs.
        """
        declared = (self.manifest or {}).get("legs")
        if not isinstance(declared, list):
            return []
        return [leg for leg in declared
                if isinstance(leg, dict) and leg.get("role") != "assembly"]

    def legs_unread(self) -> list[str]:
        """What in `legs:` names no leg `legs` can read, each as
        `validate-manifest.py`'s finding, in its words (#714, #832): a
        `legs:` that is not a list, or each entry of one that is not a
        mapping. Absent or null is neither: it declares no leg, and
        `validate-manifest.py` says `legs is missing or empty` of it."""
        declared = (self.manifest or {}).get("legs")
        if declared is None:
            return []
        if not isinstance(declared, list):
            return [f"manifest-legs: legs is {declared!r}, expected a list of "
                    "`role:`, `repository:` and `path:` mappings"]
        return [f"manifest-leg: a leg is not a mapping: {leg!r}"
                for leg in declared if not isinstance(leg, dict)]

    def members(self) -> list[dict]:
        """The member rows `family.yaml` declares, in its own order.

        A `members:` THAT IS NOT A LIST DECLARES NO MEMBER THIS CAN NAME
        (#864), as the holder's `validate-family.py` reads it, and an entry
        that is not a mapping is no member; `members_unread` says each.
        Iterated as `members or []`, `members: 5` ended the whole report in a
        `TypeError`, and a scalar `openXdox` or a mapping was walked one
        character, or one key, at a time, so the `members` row called the
        holder a family with none.
        """
        declared = (self.manifest or {}).get("members")
        if not isinstance(declared, list):
            return []
        return [row for row in declared if isinstance(row, dict)]

    def members_unread(self) -> list[str]:
        """What in `members:` names no member `members` can read, each in the
        words of the holder's own `validate-family.py` (#864): its
        `family-members-unreadable` refusal of a `members:` that is not a
        list, path and all, or its `member-row` finding for each entry of
        one that is not a mapping. The value is spelled as the gate spells
        it (`repr`), and the path as this row spells what it quotes (#673).
        Absent or null is neither: it declares no member, and the gate calls
        that family empty."""
        declared = (self.manifest or {}).get("members")
        if declared is None:
            return []
        if not isinstance(declared, list):
            return [f"family-members-unreadable: "
                    f"{spelled(self.manifest_path)}: `members:` is "
                    f"{declared!r}, expected a list"]
        return [f"member-row: a member is not a mapping: {row!r}"
                for row in declared if not isinstance(row, dict)]

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


def validator_scripts(shape: Path, own_copy: bool) -> Path | None:
    """The directory a validator run has on `PYTHONPATH`, or None for a run
    that has no `PYTHONPATH` at all: the standard's own `scripts/` for the
    standard's TEMPLATE copy, and nothing for the root's OWN copy (#238).

    ONE DEFINITION OF THE DIRECTORY AND OF THE CONDITION, for the two places
    that have to agree about both. `run_validator` gives the doctor's child
    exactly what this returns -- that directory alone, or no variable -- and
    `validator_command` prints what it returns in the line a row hands over,
    and each is asked with the one `own_copy` that `validator_for` made -- so
    the run and the line apply `PYTHONPATH` under the same condition, and
    there is no second test of `own_copy` to drift from the first (review S1
    on #238).

    THE TEMPLATE'S IS THE STANDARD'S `scripts/`, because that is the only
    place `repo_shape.py` is: the template has none beside it. THE ROOT'S OWN
    COPY GETS NOTHING, because it is the project's own gate and the doctor's
    job is to run it as the project runs it -- as a path, importing
    `repo_shape` from beside itself. A root that has lost its own
    `scripts/repo_shape.py` has a gate that cannot import it, and the row
    must say what that gate says (`ModuleNotFoundError` as a finding), not a
    "passes" the project's own gate would never give. NOTHING IS NOTHING: the
    operator's own `PYTHONPATH` is taken out of that child as well (#306),
    because one that reaches a `repo_shape.py` would stand in for the file the
    root lost, and the row would say what CI never does -- see `run_validator`.
    """
    return None if own_copy else shape / "scripts"


def pythonpath_unnamable(shape: Path, own_copy: bool) -> str | None:
    """Why no `PYTHONPATH` can name the directory `validator_scripts` gives
    this copy, or None when one can (#278).

    `PYTHONPATH` IS A LIST, AND A LIST HAS A SEPARATOR. Python splits the
    variable at `os.pathsep` -- `:` on POSIX, `;` on Windows -- and nothing in
    the variable can quote one, so a standard checked out under
    `/srv/dir:with-colon/` gives the template copy two entries, neither of
    which holds `repo_shape.py`. The doctor's child then died on the import
    and the row read that crash as the project's finding: `INVALID
    (manifest)` for a manifest that is valid, from one directory name. The
    line a row prints has the same limit, because it is the same variable.

    ONE HELPER, FOR EVERY PLACE THAT WOULD GIVE OR PRINT IT: `validator_row`
    must RUN the template to answer, so there it is an environment row and
    nothing is run; `unloaded_manifest_row` already knows its answer, so
    there only the printed line is withheld. Both ask this, with the
    `own_copy` `validator_for` made, so the run and the line cannot disagree
    about which directories are refused. The root's own copy is given no
    `PYTHONPATH` at all, and is never refused here. A `;` on POSIX, or a `:`
    on Windows, is an ordinary character in an entry and is not refused
    either.

    THE SENTENCE NAMES NO DESTINATION. Where the standard should be checked
    out is the person's choice, and a command with a made-up path in it is
    one more thing to correct before it runs.
    """
    scripts = validator_scripts(shape, own_copy)
    if scripts is None or os.pathsep not in str(scripts):
        return None
    return (f"it imports repo_shape from {scripts}, which only PYTHONPATH "
            f"can give it, and that path holds {os.pathsep!r}, the character "
            "PYTHONPATH splits on, so no PYTHONPATH can name it; run the "
            "doctor from a checkout of the standard whose path holds no "
            f"{os.pathsep!r}")


def repo_shape_for(shape: Path, used: Path, own_copy: bool) -> Path:
    """The `repo_shape.py` the validator `used` imports (#298): the one beside
    the root's OWN copy, or the standard's for its TEMPLATE copy, which is
    the directory `validator_scripts` gives that copy and no other.
    """
    directory = validator_scripts(shape, own_copy) or used.parent
    return directory / "repo_shape.py"


def imports_repo_shape(shape: Path, used: Path, own_copy: bool) -> bool:
    """Whether the validator `used` can import `repo_shape` (#298, R298-1).

    DECIDED HERE, ONCE, for both rows that need it: `validator_row` adds it
    to a crash's reason, and `unloaded_manifest_row`, which runs no gate,
    uses it to decide what its NEXT may promise. NOT a fourth value of
    `validator_for`, which three callers unpack: an arity change merges
    cleanly and then fails at run time on whichever change lands second.
    """
    return repo_shape_for(shape, used, own_copy).is_file()


def head_holds(root: Path, relative: str) -> bool:
    """Whether the root's HEAD has a file at `relative`, so that `git
    checkout HEAD -- <relative>` puts it back (#298). `./` makes the path
    the root's, as the restore line's pathspec is, and not the toplevel's.
    A root that is no repository, or has no HEAD, holds nothing.
    """
    try:
        kind = git_out(["cat-file", "-t", f"HEAD:./{relative}"], cwd=root)
    except (Refusal, OSError):
        return False
    return kind == "blob"


def restore_from_head(root: Path, relative: str,
                      platform: str | None = None) -> str:
    """The line that puts `relative` back as the root's HEAD holds it:
    `git -C <root> checkout HEAD -- <relative>`, spelled for the READER'S
    shell (#298, #697).

    ONE SPELLING FOR EVERY ROW THAT RESTORES THE FILE `head_holds` has
    asked about: the unloaded-manifest row and an own-copy validator row
    that crashed on the same loss print the same line, and `platform` is
    passed on to `quote_arg` as `bump_leg_command`'s is, so both dialects
    are asserted from either host.
    """
    target = host_shell_dialect() if platform is None else platform
    return (f"git -C {quote_arg(root, target)} checkout HEAD -- "
            f"{quote_arg(relative, target)}")


#: The four variables `gh` reads a token from, which no validator's child
#: keeps (#297).
GH_TOKEN_VARIABLES = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN",
                      "GITHUB_ENTERPRISE_TOKEN")
#: Where a validator's child is told its proxy is: the discard port on
#: loopback, which nothing a validator talks to answers on, so a request
#: that gets past `gh`'s missing login fails on this machine rather than
#: reaching a host (#297).
UNREACHABLE_PROXY = "http://127.0.0.1:9"
PROXY_VARIABLES = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy")
NO_PROXY_VARIABLES = ("NO_PROXY", "no_proxy")


def offline(env: dict) -> dict:
    """`env`, changed in place so a child started with it cannot reach a
    network through `gh` (#297): no token, no `gh` configuration, and every
    proxy variable pointed at `UNREACHABLE_PROXY` with no exception list.

    `gh` with no token and `GH_CONFIG_DIR` naming the null device knows no
    host and no login, and stops at its own login check before a request;
    `tree_digest_from_gh` turns that failure into `gh-unreadable`, the skip
    `validate-pins.py` documents. The proxy is the second wall, for a
    `gh` that sends a request anyway: it has nowhere to go. NOT A `gh` SHIM
    ON `PATH`: that needs a directory written somewhere, which this command
    never does, and a Windows child finds `gh.exe` past any shim that is
    not one.

    ON WINDOWS A VARIABLE IS ONE VARIABLE WHATEVER ITS CASE, so only the
    upper-case spelling of each proxy name is set there: the two spellings
    are one name to the child, and one entry is what it should be handed.
    """
    for name in GH_TOKEN_VARIABLES + NO_PROXY_VARIABLES:
        env.pop(name, None)
    env["GH_CONFIG_DIR"] = os.devnull
    env["GH_NO_UPDATE_NOTIFIER"] = "1"
    for name in PROXY_VARIABLES:
        if os.name == "nt" and not name.isupper():
            continue
        env[name] = UNREACHABLE_PROXY
    return env


#: The two words every verdict a validator reaches starts with: each finding
#: it reports and each refusal it makes is a line that begins with one of
#: them (#278, #410).
VERDICT_WORDS = ("FINDING", "REFUSED")


def signal_name(number: int) -> str:
    """`SIGKILL` for 9, where this platform names the signal, else `signal
    <number>` (#447)."""
    try:
        return signal.Signals(number).name
    except ValueError:
        return f"signal {number}"


def crashed(code: int, whole: str) -> str | None:
    """What to quote when a validator ended WITHOUT REACHING A VERDICT, or
    None when it reached one (#278, #410, #448, #447).

    A VERDICT IS A PRINTED `FINDING` OR `REFUSED`; ANYTHING ELSE NON-ZERO IS
    A CRASH. The validators' protocol is `0 valid, 1 findings, 2 refusal`,
    and the exit code alone cannot say which of those a child reached: an
    exception that reaches the top of a Python program exits 1 too, so a
    validator that could not import `repo_shape`, or raised on a line of its
    own, read as a project with a finding (#278). What CAN say is the
    output. Every finding and every refusal `validate-pins.py`,
    `validate-manifest.py`, `validate-family.py` and the naming script
    choose to report is a line starting `FINDING` or `REFUSED`, printed
    before the exit 1 or 2 that goes with it, so a non-zero exit with
    neither line is a child that stopped before it had anything to say.

    THE TRACEBACK IS NO LONGER ASKED FOR (#447). #357 required a
    `Traceback (most recent call last):` line as well, and so missed every
    crash that prints none: a child killed by a signal (a NEGATIVE exit,
    `-9` for the OOM killer's SIGKILL, `-15` for a timeout's SIGTERM, which
    no Python program can choose for itself); `os._exit(1)` with nothing
    printed; a validator holding merge-conflict markers, whose `SyntaxError`
    CPython prints with no traceback header; a file the interpreter `can't
    open`, exit 2; and an argparse `usage:` error, exit 2. Each of those read
    as "reports a finding" or "refuses", a statement about the project made
    by a child that never read it. One rule covers them all where a test for
    a traceback covered none.

    A FINDING PRINTED BEFORE THE CHILD DIED IS STILL A VERDICT (#357,
    R278-1): the line is there, and an exception after it does not take it
    back, so any `FINDING` or `REFUSED` line anywhere in the output answers
    None. The NAMING rows ask this too (#410), through `naming_crashed_row`.

    THE QUOTED LINE is the output's last, which for a traceback is the
    exception itself, for a `SyntaxError` its `SyntaxError:` line and for
    argparse its `error:` line -- what a reader needs to see why. With no
    output at all it is words that say so, naming the signal for a negative
    exit (`signal_name`), so a row never ends on an empty quote.
    """
    lines = [line.strip() for line in whole.splitlines() if line.strip()]
    if code == 0 or any(line.startswith(VERDICT_WORDS) for line in lines):
        return None
    if lines:
        return lines[-1][:200]
    if code < 0:
        return f"it printed nothing and was ended by {signal_name(-code)}"
    return "it printed nothing"


#: The `why` of every crash row, the validators' and the naming rows' alike
#: (#278, #410): the NEXT is the child's own line, run to see where it
#: stopped, and the row quotes only the last line of that.
CRASH_WHY = "read its output in full, it shows where the validator stopped"


#: The first line of an ITEM in a validator's report, as against a line that
#: CONTINUES the item above it: an `  ok`, `  skip`, `  note` or `  --` line,
#: a `FINDING`, `REFUSED` or `WARNING`, and the success summary a validator
#: ends on (`pins ok`, `manifest ok: ...`, `family ok: ...`). `  note` is an
#: item since #448: `validate-pins.py` prints its notes beside its skips, and
#: a note printed after a skip was read as the rest of that skip's text.
REPORT_ITEM = re.compile(
    r"  (?:ok|skip|note|--)\s|(?:FINDING|REFUSED|WARNING)\b|[a-z]+ ok\b")


#: What a validator that PASSED can still have said, by the prefix it says it
#: with, as `(prefix, the row's detail key, the words the reason quotes it
#: after)` (#297, #448). Each kind is a `note` on a row whose child exited 0:
#: `validate-pins.py`'s skip of a digest it had no source to recompute,
#: `validate-manifest.py`'s WARNING about a chain link whose tree is not on
#: this disk, and `validate-pins.py`'s note, such as
#: `neutral-pin-source-collides` (#460's pins-note line).
PASS_REPORTS = (
    ("  skip ", "skipped", "did not recheck"),
    ("WARNING ", "warnings", "warns"),
    ("  note ", "notes", "notes"),
)


def reported(whole: str) -> list[tuple[str, str]]:
    """`[(detail key, text)]` for every `  skip `, `WARNING ` and `  note `
    block a validator printed, in the order printed, each `<text>` the block
    less its prefix (#297, #448).

    THE WHOLE BLOCK, NOT ITS FIRST LINE: a skip embeds `gh`'s own stderr
    verbatim, and `gh` prints its not-logged-in help over two lines (four
    under `GITHUB_ACTIONS`), so the text `validate-pins.py` meant to say runs
    on past the first newline -- to the `--pin-source`,
    `SHAPE_PIN_SOURCE_<PRODUCT>` and `../<product>` ways to give it a source,
    which are why the row has no NEXT. Every line after the block's first is
    kept, up to the next `REPORT_ITEM` or the end, and the lines are joined
    with a space. ONE READER FOR THE THREE KINDS, AND `REPORT_ITEM` IS ITS
    ONE DEFINITION OF AN ITEM: every line it matches ends the block before
    it, and a block starts only at one of them. So a note printed after a
    skip, or a skip after a note, starts a block of its own and neither
    swallows the other, because `  note ` is an item. Flattened by
    `ascii_text`, as the machine row's `report` is, so `detail` says what
    the reason says."""
    blocks: list[tuple[str, list[str]]] = []
    inside = False
    for line in whole.splitlines():
        if REPORT_ITEM.match(line):
            kind = next(((prefix, key) for prefix, key, _words in PASS_REPORTS
                         if line.startswith(prefix)), None)
            inside = kind is not None
            if kind is not None:
                prefix, key = kind
                blocks.append((key,
                               [line.strip()[len(prefix.strip()) + 1:]]))
        elif inside and line.strip():
            blocks[-1][1].append(line.strip())
    return [(key, ascii_text(" ".join(lines))) for key, lines in blocks]


def skipped(whole: str) -> list[str]:
    """What each `  skip <text>` block a validator printed did not check, as
    `<text>` (#297): `reported`'s skips alone."""
    return [text for key, text in reported(whole) if key == "skipped"]


def passed_but(said: list[tuple[str, str]]) -> str:
    """The words after "passes, but" for what a passing validator `reported`
    (#297, #448): each kind's words from `PASS_REPORTS`, then its texts, in
    the order printed. A RUN of one kind shares its words, so a validator
    that only skipped reads `did not recheck: <a>; <b>`, as it always did,
    and a skip, a note and a skip read as three runs."""
    words = {key: said_as for _prefix, key, said_as in PASS_REPORTS}
    runs: list[tuple[str, list[str]]] = []
    for key, text in said:
        if runs and runs[-1][0] == key:
            runs[-1][1].append(text)
        else:
            runs.append((key, [text]))
    return "; ".join(f"{words[key]}: {'; '.join(texts)}"
                     for key, texts in runs)


def run_validator(ctx: Context, script: Path, args: list[str],
                  pythonpath: Path | None = None, *,
                  reach_network: bool = False) -> tuple:
    """`(exit code, the line worth quoting, whole output)`: the first
    `FINDING` or `REFUSED` line, else the first `WARNING`, else the last
    (#448).

    THE CHILD'S `PYTHONPATH` IS EXACTLY WHAT THE ROW'S NEXT PRINTS, AND THE
    DOCTOR'S OWN IS NEVER PART OF IT (#306). `pythonpath` is the directory to
    put on it, and `validator_row` passes `validator_scripts`'s answer: given
    one, the child's `PYTHONPATH` is that directory ALONE, the way the printed
    `env PYTHONPATH=<dir> python3 ...` sets it; given none, the child has NO
    `PYTHONPATH`, and the variable is taken OUT of the copy of the doctor's
    environment this builds, not left in it. ONE PLACE DECIDES, and it is the
    `env` block below: it does not ask whether the script is a root's own copy
    and it does not leave the answer to a caller, so a caller that passes
    nothing gets the same child as any other.

    A project's own `scripts/validate-pins.py` sits beside its own copy of
    `repo_shape.py` and imports it from there, so it is run with NONE -- the
    way the project's own gate runs it, in CI, where nothing exports one. A
    `PYTHONPATH` left in would reach a `repo_shape.py` of the operator's and
    stand in for the file a root that lost its own cannot import: the row said
    `passes` for a gate that fails there, the false pass #238 removed for
    everyone whose environment held no such variable. The STANDARD's template
    copy has no `repo_shape.py` beside it -- that file is copied out of the
    shape itself, not out of the template -- so when a row falls back to the
    template it must put `<shape>/scripts` on the path or the fallback dies on
    an ImportError that says nothing about the project being checked, and it
    puts it there ALONE: put in front of the operator's, theirs stayed on the
    path behind it for the validator to import from, which the line the row
    printed does not have. The standard's own scripts (naming, the machine's
    preflight) are given none: the naming script inserts its own directory
    ahead of its `repo_shape` import, and the machine's preflight needs
    nothing from `repo_shape` at all and never imports it (#238), so taking
    the variable out of their child changes nothing they NEED. It does change
    what their row can SAY, for the better: a `sitecustomize.py` or a
    stdlib-shadowing module in an operator's `PYTHONPATH` that acts only in a
    validator's process used to turn a compliant root's `naming` row into a
    FINDING, and it no longer can.

    A PASTED COMMAND IS A SECOND PROCESS, AND THIS `env` IS NOT IN IT. What a
    row prints as its NEXT is run later, by a person, in their own shell -- so
    what is set here reaches the doctor's child and never the reader's, and
    `validator_command` is what puts the same directory in the printed line
    (#238). Both are `validator_scripts`'s, asked with the same `own_copy`, so
    the run and the line apply `PYTHONPATH` under one condition: a template
    copy gets it in both and the root's own copy gets it in neither. A root's
    own copy that cannot import `repo_shape` from beside itself therefore
    fails here as the project's own gate fails, and the row reports that
    failure rather than a pass.

    AND NO `site` IN ANY CHILD, WHICH IS `-S` (#342). `PYTHONPATH` is one way
    a directory reaches `sys.path`, not the only one: at start-up `site`
    appends every directory a `.pth` file names, in the user's site-packages
    and in the interpreter's own -- a virtualenv's, or the system's -- runs
    every line of one that starts with `import`, and imports `sitecustomize`
    and `usercustomize`. With `site` on, a `.pth` naming a directory that holds
    `repo_shape.py` stood in for the copy a root lost, exactly as an exported
    `PYTHONPATH` did before #306: the `manifest` row said `passes`, for that
    operator, over a gate that dies on `ModuleNotFoundError` in CI. A
    validator puts its own directory first, so a `.pth` never shadowed a
    `repo_shape.py` the root still has; it filled the gap a lost one leaves,
    which is the one case #238's row exists to report. `-S` closes every one
    of those routes and keeps the rest of the child: its own directory, the
    standard library, which the interpreter finds without `site`, and
    `PYTHONPATH`, so the template copy keeps its `<shape>/scripts`. `-s`
    (`PYTHONNOUSERSITE`) closes the user's site-packages alone, and a
    virtualenv's `.pth` still stood in; `-I` is `-s` and `-E`, so it closed no
    more `.pth` routes than `-s`, took the template's `PYTHONPATH` away
    (CANNOT ANSWER), and wrote `scripts/__pycache__` into the root, because
    `-E` ignores `PYTHONDONTWRITEBYTECODE` as well. And a `.pth` that runs
    code ran it in every child: coverage's, with `COVERAGE_PROCESS_START`
    exported, left `.coverage.*` files in the root.

    IT COSTS NO CHILD AN IMPORT. Every script this starts -- the three
    validators, the naming script, the preflight -- is a file this standard
    ships, or a root's pinned copy of one, and imports the standard library
    and this standard's own modules and nothing else, which
    `tests/test_repo_hygiene.py` holds the shipped files to. The project's
    own workflow runs its gate on a fresh interpreter with no `pip install`
    ("Standard library only"), so nothing on a `site` path is anything the
    gate can import in CI either. ONE RULE FOR EVERY CHILD, as the `env`
    block is: the flag does not ask which script it starts.

    THAT IS TRUE OF AN UNEDITED COPY ONLY. A root whose own copy of a
    validator gained an `import yaml` read `passes` here while `site` was on,
    wherever the doctor's interpreter could import it, and now reads
    `crashed before reaching a verdict (exit 1): ModuleNotFoundError: No
    module named 'yaml'`, which is the crash its own CI gets, because
    `validate.yml` installs nothing. That row is a fair answer for that root,
    and `-S` stays as it is: it does not ask whether a copy was edited.

    WHICH AGREEMENT THE ROW KEEPS (#306, #342): the row reports the
    project's own GATE as CI runs it, with no inherited `PYTHONPATH` and no
    `site`; it does not predict what a pasted line prints in the reader's
    shell. The pasted line runs under the READER'S environment and their
    interpreter, so a reader whose own `PYTHONPATH`, or a `.pth` in whose
    site-packages, reaches a `repo_shape` can see a pasted own-copy line pass
    where the row says FINDING. That is their variable and their
    site-packages, and the gate has neither: the row is about the gate, and
    the line it prints is the project's own command, with no `-S` in it.
    WHERE THE CRASH IS THE ROOT'S LOST `scripts/repo_shape.py` THE LINE IS
    THE CURE INSTEAD, because that is the one crash the reader's own
    environment can hide (#697): `lost_repo_shape_cure`.

    AND NO CHILD REACHES A NETWORK UNLESS ITS CALLER SAYS SO (#297). A
    project that pins a neutral product has a `validate-pins.py` that, with
    no local checkout of the product to read, asks `gh api` for its tree --
    so the row this command calls offline started a call to GitHub, on the
    operator's login wherever there was one. Every child is now started
    `offline`: no token, no `gh` configuration, a proxy that goes nowhere.
    `gh` fails, the validator prints its `skip` line and exits 0, and
    `validator_row` reports that skip. `reach_network=True` is the ONE
    exception, and its one caller is `check_machine`, whose preflight asks
    `gh` who is logged in: the row the module docstring names as the
    network's.
    """
    env = dict(os.environ)
    if pythonpath is not None:
        env["PYTHONPATH"] = str(pythonpath)
    else:
        env.pop("PYTHONPATH", None)
    if not reach_network:
        offline(env)
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
    # AND NOTHING IT STARTS MAY ASK (#492). Stdin closed is not enough:
    # `setup-project.py` asks at the CONTROLLING terminal when stdin is not
    # one, so the machine row's preflight run from a person's terminal would
    # offer `gh auth login` there and wait. A session of its own has no
    # controlling terminal, so the child has none to ask on (POSIX; Windows
    # has no `/dev/tty` and ignores the flag).
    # `-S`: no `site`, so no `.pth` from any site-packages stands in for a
    # file the root lost (#342, in the docstring above).
    proc = subprocess.run([sys.executable, "-S", str(script), *args],
                          cwd=str(ctx.root), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False,
                          stdin=subprocess.DEVNULL, env=env,
                          start_new_session=True)
    whole = (proc.stdout or "") + (proc.stderr or "")
    # THE QUOTED LINE OF A RED ROW IS A VERDICT LINE (#448, decision 4): the
    # first `FINDING` or `REFUSED`, else the first `WARNING`, else the last
    # line. `validate-manifest.py` prints leg by leg, so an earlier leg's
    # WARNING came before a later leg's FINDING, and a row whose gate went
    # red quoted the note that moved nothing instead of the finding that
    # failed it. A WARNING is still quoted where nothing else would say
    # more: an exit 0 never quotes, and a crash quotes its own last line.
    lines = [line.strip() for line in whole.splitlines() if line.strip()]
    quoted = next(
        (line for line in lines if line.startswith(VERDICT_WORDS)),
        next((line for line in lines if line.startswith("WARNING")),
             lines[-1] if lines else ""))
    return proc.returncode, quoted[:200], whole


def validator_for(ctx: Context, own: str, template: str) -> tuple:
    """`(the validator a row runs, how the row names it, whether it is the
    root's own copy)`: the root's own copy when it has one, else the
    standard's template copy.

    One choice, made in one place, because two rows make it: `validator_row`
    runs what this picks, and `unloaded_manifest_row` names it as the next
    command (#205). A root told to run one copy by one row and another by the
    next would be told two different things about one gate.

    THE THIRD VALUE IS WHAT `validator_command` NEEDS to spell the line, and
    it is returned here, from the one place that made the choice, instead of
    being re-derived from the path by a caller (#238). It is also the row's
    `detail.own_copy`.

    AN OWN COPY THIS USER CANNOT REACH IS NOT ONE THE ROOT LACKS (#430). It
    was asked `own_path.is_file()`, which up to Python 3.13 raised a refused
    `stat` out of the row (`could not be run: [Errno 13] ...`) and from 3.14
    answers False: a `scripts/` this user cannot search then ran the
    standard's TEMPLATE in the project's place and printed `ok manifest the
    standard's templates/assembly-root/scripts/validate-manifest.py passes`,
    a pass of a gate the project does not have, over its own that nobody
    ran. It is asked as `validate-pins.py` asks it (`is_a`), and a refused
    `stat` is RAISED, on every Python: each caller names the copy
    (`unreadable_gate_row`) or names no line (`gate_line`). The template
    stands in only for a copy that is not there at all.
    """
    own_path = ctx.root / own
    if is_a(own_path, stat.S_ISREG):
        return own_path, f"the project's own {own}", True
    return ctx.shape / template, f"the standard's {template}", False


def validator_command(shape: Path, used: Path, own_copy: bool, args: list,
                      platform: str | None = None) -> str:
    r"""The line that runs `used` on `args`, spelled for the READER'S shell,
    and carrying the environment the doctor ran it under (#238).

    A NEXT IS A COMMAND, and a command pasted into the shell it was quoted
    for, from any directory and with no `PYTHONPATH` in the environment, has
    to do what its row says: print the validator's own output and exit with
    the code the row records. The root's OWN copy does, for as long as the
    project keeps its own `repo_shape.py` beside it, as a project copied from
    the shape does: it imports it from there, so that line is the bare
    interpreter, path and arguments it has always been, byte for byte. It is
    the project's own gate and is run, and printed, as the project runs it. A
    root that has lost that file has a gate that dies on the import, pasted
    or not, and the row says so as a finding, because the doctor ran it the
    same way (`validator_scripts`).

    THE STANDARD'S TEMPLATE COPY DOES NOT. It imports `repo_shape` from beside
    itself, and `repo_shape.py` is copied INTO a project's `scripts/` out of
    the standard's `scripts/`, never kept beside the template (`REPO_SHAPE`,
    `scripts/shape_materialize.py`). The doctor's own child runs it with
    `<shape>/scripts` on `PYTHONPATH` (`run_validator`, through
    `validator_scripts`); the line a row printed carried only the path, so
    pasting it died on `ModuleNotFoundError: No module named 'repo_shape'`
    with exit 1 -- the code a validator uses for "findings", so anything keyed
    on the exit code read a crash as the finding the row had already
    reported, and the one command the row hands over to "read its output in
    full" printed a traceback that named nothing about the project. A reader
    whose own shell already exported a `PYTHONPATH` that reached the standard
    never saw it, which is how it went unfound.

    SO THE TEMPLATE'S LINE SETS IT, in the reader's dialect, which is the
    same two this file already speaks (`quote_arg`, `copy_command`,
    `scaffold_command`): `env PYTHONPATH=<shape>/scripts python3
    <template> ...` for `sh`, and `$env:PYTHONPATH = '<shape>\scripts';
    python <template> ...` for PowerShell. Both are ONE directory, so this is
    a plain assignment and not a list, and it is what the doctor's child was
    given: that directory ALONE (#306). The child used to have it PREPENDED
    to whatever the environment already held, which a printed line cannot
    do, because it cannot see the reader's value -- so the run and the line
    named two different `PYTHONPATH`s.

    `env`, NOT A BARE `NAME=value` PREFIX (#277). The prefix is syntax of
    `sh`, bash and zsh, and of nothing else a person may be pasting into:
    csh and tcsh read `PYTHONPATH=...` as the name of a command and say
    `Command not found`, and fish before 3.1 refused it, by those shells'
    own documentation (none of the three was run for this change). `env` is
    a PROGRAM, so the same line runs in every one of them, for four
    characters, and it still sets the variable for this one command only.

    ONLY `PYTHONPATH`, and not the rest of the child's environment.
    `PYTHONIOENCODING` and `PYTHONDONTWRITEBYTECODE` exist so the DOCTOR can
    quote a validator's prose and keep its own promise to write nothing; a
    reader pasting a line is making their own run, and the import is the only
    thing that run cannot do without.

    THE POWERSHELL VALUE IS QUOTED WHETHER OR NOT IT NEEDS IT, which is
    `quote_arg`'s `always`: what follows `=` is a pipeline, so a bare
    `C:\shape\scripts` would be run as a command and not assigned as a
    string. THE ASSIGNMENT LASTS FOR THE POWERSHELL SESSION, not for the one
    command, and it REPLACES any `PYTHONPATH` the reader had: `env` applies
    it to one command and leaves the reader's environment alone, and
    this does not. That is accepted: the issue and the plan for this change
    named this spelling, `$env:` is PowerShell's idiom, and the effect ends
    with the session (review N1 on #238).

    `platform` IS PASSED ON, as `copy_command` says at length: one resolved
    `target` governs the dialect, the interpreter and every quoting, so a
    Windows line built on a POSIX runner is a Windows line, and both are
    asserted from either host. `platform=None` is the host, and asks two
    questions that part only under Git Bash (#711): the shell
    (`host_shell_dialect`, `sh`'s there) for `env` or `$env:` and every
    quoting, and the machine (`python_command`, `python` on Windows) for
    the interpreter, so Git Bash gets `env PYTHONPATH=... python ...`.
    """
    target = host_shell_dialect() if platform is None else platform
    command = " ".join([python_command(platform), quote_arg(used, target),
                        *(quote_arg(arg, target) for arg in args)])
    scripts = validator_scripts(shape, own_copy)
    if scripts is None:
        return command
    if target == "nt":
        return (f"$env:PYTHONPATH = {quote_arg(scripts, target, always=True)}; "
                f"{command}")
    return f"env PYTHONPATH={quote_arg(scripts, target)} {command}"


def lost_repo_shape_cure(ctx: Context, own: str, lost: Path, rerun: str,
                         again: bool = True,
                         purpose: str = "") -> tuple[str | None, str]:
    """`(the NEXT, the why)` for a root's own validator `own` that crashed
    because `lost`, the `repo_shape.py` it imports from beside itself, is not
    there, where `rerun` is the line that runs `own` (#697).

    `again` says "run it AGAIN" where the doctor ran the gate and it crashed,
    as the validator rows' crash does; the `legs` and `members` rows' lockstep
    line is one the reader never ran, and says "run it" (#750). `purpose` is
    what the gate is run for, where the row says (", to confirm the digest",
    #776), and follows "once the file is back".

    THE NEXT IS THE CURE, NOT THE VALIDATOR. The row used to print `rerun`,
    and a reader whose own `PYTHONPATH`, or a `.pth` in whose site-packages,
    reaches another `repo_shape` ran it and saw a pass, or a different
    finding, under a row that said the gate crashed: the doctor starts every
    child with no inherited `PYTHONPATH` and no `site` (#306, #342), and a
    pasted line has neither guard. `-E -S` on the line would have stopped
    both routes and was declined: the line stays the project's own command.
    So the NEXT is the one command that puts the file back, the line the
    unloaded-manifest row prints for the same loss (`restore_from_head`,
    #298), and `rerun` is the why's, to run once the file is back.

    NO NEXT WHERE HEAD DOES NOT HOLD THE FILE (`head_holds`): a deletion
    already committed is not in HEAD, so the line could not restore it, and
    the gate would only crash again. The why says so, where the file comes
    back from, and the gate to run after.

    THE CONDITION IS THE ROW'S REASON'S -- the file is not beside the root's
    own copy (`imports_repo_shape`) -- and it is asked of the root's own copy
    only: the standard's template copy has none beside it by design.
    """
    relative = lost.relative_to(ctx.root).as_posix()
    then = (f"run `{rerun}`{' again' if again else ''} once the file is "
            f"back{purpose}; before that, a reader whose own PYTHONPATH or "
            "site-packages reaches another repo_shape sees it run on that "
            "one, which says nothing about this root's own copy")
    if head_holds(ctx.root, relative):
        return (restore_from_head(ctx.root, relative),
                f"it puts back the {relative} HEAD holds, the copy this "
                f"root committed and {own} imports, where update-shape.py "
                f"apply would copy a newer one. Then {then}")
    return None, (f"HEAD does not hold {relative}, so no git checkout HEAD "
                  f"puts it back and {own} would only crash again: a "
                  "deletion already committed comes back from the parent of "
                  f"the commit that made it. Then {then}")


def unreadable_gate_row(ctx: Context, check_id: str, label: str, own: str,
                        exc: OSError, said: str = "") -> Row:
    """The row of a validator whose OWN copy, `own`, this user cannot reach
    (#430): a FINDING about the repository, in `validate-pins.py`'s words for
    the file (`cannot_be_read`), with this doctor again as the NEXT and the
    gate's advice for the cause as the WHY (`cannot_read_why`), as #847's
    rows give them for a pin. NOTHING IS RUN: not the copy, which cannot be
    opened, and not the standard's template in its place, which is not this
    project's gate (`validator_for`). `said` is what the row says first,
    where it has more to say (`unloaded_manifest_row`)."""
    line = cannot_be_read(own, exc)
    return Row(check_id, label, FINDING,
               f"{said}{line}, so the project's own gate was not run, and the "
               "standard's copy is not run in its place", doctor_line(ctx),
               {"validator": (ctx.root / own).as_posix(), "own_copy": True,
                "exit": None, "cannot_be_read": line},
               why=cannot_read_why([exc]))


def validator_row(ctx: Context, check_id: str, label: str, own: str,
                  template: str, args: list[str], *,
                  output: list[str] | None = None) -> Row:
    """One row for a validator that the ROOT may carry its own copy of.

    THE PROJECT'S OWN COPY FIRST, ALWAYS, AND THE ROW SAYS SO. That copy is
    the pinned one -- it is what the project's own gate runs, and running the
    standard's newer copy instead would answer a question nobody asked: not
    "does this project pass its gate" but "would it pass a gate it does not
    have". The template copy is the fallback for a root that has lost or never
    had one, and the row names which of the two answered.

    A VALIDATOR THAT CRASHED HAS NOT ANSWERED (#278). Exit 1 is a finding
    AND an exception that reached the top, so the row asks `crashed` before
    it believes the code -- and since #447 a crash is ANY non-zero exit that
    printed no `FINDING` or `REFUSED` line: a signal, `os._exit(1)`, a
    `SyntaxError`, an argparse `usage:` error. The verb a verdict row picks
    by its code, "refuses" for 2 and "reports a finding" otherwise, is then
    reached only by a child that printed one of those lines. The root's OWN
    copy crashing is still a FINDING -- a project whose gate cannot run has
    a broken gate, which is a fact about the project (#237 draws the same
    line from the other side) -- but it says it crashed, carries
    `detail.crashed`, and says when the cause is the `repo_shape.py` it
    imports (`imports_repo_shape`). The TEMPLATE copy
    crashing is this checkout's failure and not the project's: it carries
    `detail.environment`, so the verdict is CANNOT ANSWER, exit 3. Either
    way the NEXT is the validator's own line, which shows where it stopped
    -- EXCEPT where the root's own copy crashed for want of that
    `repo_shape.py` (#697): its NEXT is `git checkout HEAD` on the file, or
    none where HEAD does not hold it, and the validator's line is the why's
    (`lost_repo_shape_cure`).

    AND A TEMPLATE THIS CHECKOUT CANNOT GIVE ITS `PYTHONPATH` IS NOT RUN
    (#278): `pythonpath_unnamable` says why, the row is an environment row
    with no NEXT, and no `PYTHONPATH=` line is printed, because no such line
    could be pasted and work.

    A PASS THAT SKIPPED SOMETHING SAYS SO (#297). Exit 0 with `  skip `
    lines is `validate-pins.py` reporting a neutral product's digest it had
    nothing to recompute from. That is its documented answer, never a
    failure, so the row is a `note`, which moves no verdict -- and its
    reason quotes what was not rechecked, because "passes" alone said a
    digest was verified that nobody verified. The skip line already names
    the three ways to give it a source, so there is no NEXT.

    AND SO DOES A PASS THAT WARNED OR NOTED (#448, #460's pins-note line).
    `validate-manifest.py` prints `WARNING naming-referent-chain: ...` and
    exits 0 for a chain link whose tree is not on this disk -- "printed and
    then forgotten by the exit code, deliberately" -- and `validate-pins.py`
    prints `  note neutral-pin-source-collides: ...` beside its skips. Both
    were dropped, so a chain nothing here could check read as checked under
    COMPLIANT, and the one line saying which variable is read for neither
    pin reached nobody. Each is a `note` the same way: its own `detail` key
    (`skipped`, `warnings`, `notes`, from `PASS_REPORTS`), quoted in the
    reason in the order printed (`passed_but`), and no NEXT -- each names
    its own remedies, and which declaration stays is the human's call.

    AN OWN COPY THIS USER CANNOT REACH IS NAMED AND NOTHING IS RUN (#430):
    `validator_for` raises its refused `stat`, and the row is
    `unreadable_gate_row`'s.
    """
    try:
        used, which, own_copy = validator_for(ctx, own, template)
    except OSError as exc:
        return unreadable_gate_row(ctx, check_id, label, own, exc)
    if not used.is_file():
        return Row(check_id, label, FINDING,
                   f"neither {own} nor {template} is readable, so the "
                   "question cannot be asked",
                   f"{PYTHON} "
                   f"{quote_arg(ctx.shape / 'shape-doctor.py')} --root "
                   f"{quote_arg(ctx.root)}",
                   {"validator": None},
                   why="from a complete checkout of the standard; this one "
                       "is missing that file")
    unnamable = pythonpath_unnamable(ctx.shape, own_copy)
    if unnamable is not None:
        return Row(check_id, label, FINDING, f"{which} was not run: "
                   f"{unnamable}", None,
                   {"validator": used.as_posix(), "own_copy": own_copy,
                    "exit": None, "environment": True})
    code, quoted, whole = run_validator(ctx, used, args,
                                        validator_scripts(ctx.shape, own_copy))
    if output is not None:
        # What the validator printed, whole, for a caller that reads more of
        # it than the one line the row quotes: `check_pins` (#478).
        output.append(whole)
    detail = {"validator": used.as_posix(), "own_copy": own_copy,
              "exit": code}
    if code == 0:
        said = reported(whole)
        if not said:
            return Row(check_id, label, OK, f"{which} passes", None, detail)
        for key, text in said:
            detail.setdefault(key, []).append(text)
        return Row(check_id, label, NOTE,
                   f"{which} passes, but {passed_but(said)}", None, detail)
    crash = crashed(code, whole)
    if crash is not None:
        detail["crashed"] = True
        reason = f"{which} crashed before reaching a verdict (exit {code}): " \
            f"{crash}"
        command = validator_command(ctx.shape, used, own_copy, args)
        why = CRASH_WHY
        if not imports_repo_shape(ctx.shape, used, own_copy):
            lost = repo_shape_for(ctx.shape, used, own_copy)
            reason += (f"; {lost.relative_to(ctx.root).as_posix()}, which it "
                       "imports from beside itself, is not there"
                       if own_copy else f"; {lost} is not there")
            if own_copy:
                command, why = lost_repo_shape_cure(ctx, own, lost, command)
        if not own_copy:
            detail["environment"] = True
            reason += ("; that copy is this checkout's, not the project's, "
                       "so nothing here is a statement about the project")
        return Row(check_id, label, FINDING, reason, command, detail,
                   why=why)
    verb = "refuses" if code >= 2 else "reports a finding"
    reason = f"{which} {verb} (exit {code})" + (f": {quoted}" if quoted else "")
    # A COMMAND THAT RUNS WHEN IT IS PASTED. This row used to print
    # `python3 validate-pins.py in <root>`, which is prose wearing a command's
    # clothes: `in` arrives as an argument and argparse refuses it. Every
    # validator here takes `--root`, so the runnable spelling is the absolute
    # path and that flag, and it needs no `cd` (Copilot, PR #96). AND IT NEEDS
    # NO ENVIRONMENT FROM THE READER: where `used` is the standard's template
    # copy the line carries the `PYTHONPATH` the doctor ran it under, or it
    # dies on an import and exits with a finding's code (#238); the root's own
    # copy was run with no `PYTHONPATH` at all (#306), and its line carries
    # none. AND IT IS ONLY THE COMMAND: what to do with its output is the
    # row's `why`, on a line of its own (#277).
    command = validator_command(ctx.shape, used, own_copy, args)
    return Row(check_id, label, FINDING, reason, command, detail,
               why="read its output in full; it names what it refused")


#: The row that OWNS each kind's manifest, by id: the one that quotes its
#: refusal when it does not load, and the one every row that reads it waits
#: on (#205).
MANIFEST_ROW = {PROJECT: "manifest", FAMILY: "family"}


def refusal_line(refusal: Refusal) -> str:
    """`REFUSED <code>: <detail>`: a refusal's own `str()`, less its remedy.

    `Refusal.__str__` is the one place that line is spelled, and the one
    the project's own validators print it from, so the row quotes it from
    there rather than spelling it a second time (#205, review N2). It is
    `str(refusal)` with the `\\n<remediation>` trailer taken OFF THE END, not
    the text up to its first newline: `detail` opens with the path the
    loader was given, and a root whose directory name holds a newline would
    be cut after its first line and quoted short -- a different report from
    the one this row has always printed, with no error to say so. A refusal
    with no remedy has no trailer (#370), and its `str()` is the line whole.
    """
    line = str(refusal)
    if not refusal.remediation:
        return line
    return line.removesuffix("\n" + refusal.remediation)


def remedy_as_why(refusal: Refusal) -> str | None:
    """A refusal's remedy as a row's `why`, less its `Remediation:` label,
    or None where it carries none (#408, #548).

    NEVER AS A ROW'S NEXT. A remedy is prose a tool prints under its own
    refusal, and the one most tools used to print, `repo_shape.REMEDIATION`,
    held `git submodule update` and `validate-pins.py` in backticks, which
    an interactive zsh runs where the line is pasted (#277). Two places --
    `run_checks`, for a check that lets a refusal out, and
    `placement_policy`, for a standard whose own path policy does not load
    -- printed it as the NEXT. They print no NEXT now, and the remedy, when
    there is one, is the row's `why`, so what the refusal had to say is not
    lost.
    """
    said = (refusal.remediation or "").strip()
    said = said.removeprefix("Remediation:").strip()
    return said or None


def unloaded_manifest_row(ctx: Context, check_id: str, label: str, own: str,
                          template: str) -> Row:
    """The `manifest` (or `family`) row for a manifest that is THERE and does
    not load (#205): a FINDING, the loader's refusal, and the gate to re-run.

    THE LOADER'S OWN WORDS, WHOLE. `REFUSED <code>: <detail>` is what
    `load_yaml` raised when `Context` read the file, and it is the line the
    project's own validator prints about the same file, because it reads it
    through the same function -- so the row and the gate say one thing in one
    spelling, and nothing here parses YAML a second way. Quoted from the
    refusal itself rather than from the validator's output, because a quoted
    validator line is cut at 200 characters and this one ends with the line
    number, after a path of any length.

    NOT THE REFUSAL'S REMEDIATION. `yaml-unparsable` carried `repo_shape`'s
    default one, which is about submodules and the lockstep invariant: it
    sent a person resolving a merge conflict to `git submodule update`. It
    carries none since #370, and the row names the gate either way.

    THE NEXT COMMAND IS THE GATE THAT OWNS THE FILE, picked by
    `validator_for` exactly as the row would have run it, AND IT NAMES THE
    FILE, because the file is the fix: it refuses the same way until the file
    loads, and says so the moment it does. What the file should say at that
    line -- which side of a merge conflict, what a hand edit meant -- is a
    person's decision, and the line says that too. Never `adopt-project.py
    plan`, which is what this root was offered while the refusal was read as
    "no manifest".

    BUT THE GATE HAS TO BE ABLE TO RUN FOR THAT TO BE TRUE (#298). This row
    runs no gate, so it asks `imports_repo_shape` instead: a root's own copy
    with no `repo_shape.py` beside it dies on the import, pasted or not, and
    the promise above would send the person to a traceback that says nothing
    about the file. Such a root is told to put the file back FIRST, with the
    one command that restores the copy HEAD holds -- the project's own
    committed bytes, where `update-shape.py apply` would copy a newer
    upstream, as `check_agent_files` restores a deleted copy -- and that the
    gate comes after it. That is the
    order the verdict already gives: `DRIFTED (copy-missing)` outranks
    `INVALID`. A deletion already COMMITTED is not in HEAD, so the line
    could not restore it: the row then has no NEXT, and says the file comes
    back from the parent of the commit that deleted it.

    AND A TEMPLATE LINE THAT CANNOT CARRY ITS `PYTHONPATH` IS NOT PRINTED
    (#278). The finding stands, since the manifest does not load either way,
    but `pythonpath_unnamable` says why the standard's copy cannot be named
    as a command, and the row has no NEXT rather than a line that splits
    when pasted. Only the template copy can be refused that way: the root's
    own copy needs no `PYTHONPATH`, and `validator_for` names it whenever
    the root has one.

    AND AN OWN GATE THIS USER CANNOT REACH IS NAMED BESIDE THE REFUSAL
    (#430), as `validator_row` names it, and no line runs it or the template
    in its place: the person makes it readable, and the doctor names the
    gate's line once it can.
    """
    refusal = ctx.manifest_refusal
    name = ctx.manifest_path.name
    reason = f"{name} does not load: {refusal_line(refusal)}"
    refused = {"manifest": name,
               "refusal": {"code": refusal.code, "detail": refusal.detail}}
    try:
        used, which, own_copy = validator_for(ctx, own, template)
    except OSError as exc:
        row = unreadable_gate_row(ctx, check_id, label, own, exc,
                                  f"{reason}; ")
        row.detail.update(refused)
        return row
    detail = {"validator": used.as_posix(), "own_copy": own_copy, **refused}
    if not used.is_file():
        # Neither copy to name: `validator_row` already says so, for any
        # root, and its next command is the one this row then needs.
        missing = validator_row(ctx, check_id, label, own, template,
                                ["--root", str(ctx.root)])
        return Row(check_id, label, FINDING, f"{reason}; {missing.reason}",
                   missing.next_command, {**missing.detail, **detail},
                   why=missing.why)
    if own_copy and not imports_repo_shape(ctx.shape, used, own_copy):
        lost = repo_shape_for(ctx.shape, used, own_copy).relative_to(
            ctx.root).as_posix()
        if not head_holds(ctx.root, lost):
            return Row(check_id, label, FINDING,
                       f"{reason}; {lost} is gone too, and HEAD does not hold "
                       f"it, so {own}, the gate that owns {name}, cannot "
                       f"import repo_shape to refuse it: a deletion already "
                       "committed comes back from the parent of the commit "
                       f"that deleted it, and then {own} refuses {name} by "
                       "name until it loads", None, detail)
        return Row(check_id, label, FINDING, reason,
                   restore_from_head(ctx.root, lost), detail,
                   why=f"it puts back the {lost} HEAD holds, the copy this "
                       f"root committed and {own} imports, where "
                       "update-shape.py apply would copy a newer one, then "
                       f"run {own} again: it refuses {name} by name until it "
                       "loads. A deletion already committed comes back from "
                       "the parent of the commit that made it, not from HEAD")
    unnamable = pythonpath_unnamable(ctx.shape, own_copy)
    if unnamable is not None:
        return Row(check_id, label, FINDING,
                   f"{reason}; {which}, the gate that owns it, has no line "
                   f"here: {unnamable}", None, detail)
    command = validator_command(ctx.shape, used, own_copy,
                                ["--root", ctx.root])
    return Row(check_id, label, FINDING, reason, command, detail,
               why=f"the file to fix is {quote_arg(ctx.manifest_path)}, "
                   "where the line above says; this refuses it the same way "
                   "until it loads. What it should say there -- a merge "
                   "conflict resolved, a hand edit put right -- is the "
                   "person's call")


def waiting_row(ctx: Context, check_id: str, label: str, needs: str,
                detail: dict | None = None) -> Row | None:
    """The `n/a` a row that READS the manifest gives while it does not load
    (#205), or None when it loads and the row has its question.

    ONE FAULT, ONE FINDING. Each of these rows asks its question of what the
    manifest DECLARES -- the leg names, the legs, the members -- and the
    project's `validate-pins.py` reads `project.yaml` before it checks a
    single pin. With the manifest unloadable none of them has a question, and
    each used to answer one it made up: "project.yaml declares no
    non-assembly leg", "a family with none is empty, not wrong" (an `ok`, on
    a holder whose every member was unknown), or the loader's refusal again
    under a next command whose output sends a person to `git submodule
    update`. So they say that they wait, and on which row; that row quotes
    the refusal and names the fix, and the verdict is `INVALID` naming it.

    `n/a` RATHER THAN A FINDING because the question cannot be asked here,
    which is what `n/a` means in this file; the verdict loses nothing by it,
    since the row these wait on is a FINDING whenever this is said. And
    `waits_on` is in `detail`, so a caller acting on `--json` reads which row
    to act on rather than parsing the sentence.
    """
    if ctx.manifest_refusal is None:
        return None
    owner = MANIFEST_ROW[ctx.kind]
    return Row(check_id, label, NA,
               f"{ctx.manifest_path.name} does not load, so {needs}; the "
               f"`{owner}` row quotes why and names the fix", None,
               {**(detail or {}), "waits_on": owner})


def legs_unread_row(ctx: Context, check_id: str, label: str, needs: str,
                    detail: dict | None = None) -> Row | None:
    """The `n/a` a row that reads the LEGS gives where `legs:` names none it
    can read (#832), or None: where it names a leg, and where it names none
    at all (absent, null or `[]`), which the row's own sentence is about.

    A `legs:` that is not a list, or a list in which no leg but the assembly
    leg is a mapping and some entry is not one, is not a project with no
    legs, which is what these rows said of `openXdox`, `{a: b}` and `[5]`
    ("a one-repository project has none"): it is a manifest nobody can read
    legs out of. ONE FAULT, ONE FINDING, as `waiting_row` reasons: the
    project's own `validate-manifest.py` says the fault, and the `manifest`
    row runs it, so this row is `n/a`, says the same sentence
    (`Context.legs_unread`) and names that row in `waits_on`. A list that
    holds a leg as well as an entry that is not one is checked leg by leg,
    as `validate-pins.py` checks the rest past such an entry, and the entry
    is left to the `manifest` row.
    """
    unread = ctx.legs_unread()
    if not unread or ctx.legs():
        return None
    what = ("holds an entry that is not a mapping"
            if isinstance(ctx.manifest.get("legs"), list) else "is not a list")
    return Row(check_id, label, NA,
               f"{ctx.manifest_path.name}'s `legs:` {what} "
               f"({'; '.join(unread)}), so {needs}; the `manifest` row's "
               "command names the fault", None,
               {**(detail or {}), "waits_on": "manifest"})


def members_unread_row(ctx: Context, needs: str) -> Row | None:
    """The `n/a` the `members` row gives where `members:` holds anything it
    cannot read as a member (#864), or None: where every entry is a row, and
    where there is none at all (absent, null or `[]`), which the row's own
    "no members yet" is about.

    A `members:` that is not a list is not a family with no members, which
    is what the row said of `openXdox`, `{a: b}` and `[5]`, one row under
    the `family` row's refusal of the same value: it is a manifest nobody
    can read members out of. ONE FAULT, ONE FINDING, as `waiting_row`
    reasons: the holder's own `validate-family.py` says the fault, the
    `family` row runs it, so this row is `n/a`, says the same sentence
    (`Context.members_unread`) and names that row in `waits_on`.

    AND A LIST THAT HOLDS ROWS AS WELL AS SUCH AN ENTRY WAITS TOO, unlike a
    project's `legs:` (#832), whose bootstrap places the legs beside such an
    entry: the holder's own `scripts/bootstrap.py`, which this row names to
    fetch a member to its pin, refuses that list (`members_of`), and
    `family.py` refuses it before `add`, `bump` or `remove` does anything.
    Checked row by row, the rows beside a `5` were "mounted at their pins",
    an `ok` under the `family` row's `member-row` finding for it.

    IT SAYS THAT THE `family` ROW'S COMMAND NAMES THE FAULT, as #862's
    `legs_unread_row` says it of the `manifest` row, and no more: that
    command is the gate, which prints the refusal or the `member-row`
    finding and no remedy.
    """
    unread = ctx.members_unread()
    if not unread:
        return None
    what = ("holds an entry that is not a mapping"
            if isinstance(ctx.manifest.get("members"), list)
            else "is not a list")
    return Row("members", "members", NA,
               f"{ctx.manifest_path.name}'s `members:` {what} "
               f"({'; '.join(unread)}), so {needs}; the `family` row's "
               "command names the fault", None,
               {"members": [], "waits_on": "family"})


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------


def check_naming(ctx: Context) -> Row:
    """The leg names, against THE STANDARD's copy of the naming policy.

    The standard's rather than the project's on purpose: this command answers
    "is this compliant with openRepoShape", and openRepoShape is the checkout
    this file is in. A project whose copied policy is older is exactly the
    thing the shape-currency row is for, and it says so there.

    The names are READ OUT OF `project.yaml`, so a manifest that does not
    load leaves none to classify: `waiting_row` (#205).

    A SCRIPT THAT CRASHED HAS NOT ANSWERED (#410). This row read the exit
    code alone, so a checkout of the standard whose own naming script raised
    said `INVALID (naming)`, exit 1, about a compliant project: a statement
    about the project caused by a fault in the checkout asking. It asks
    `crashed` as `validator_row` does, and a crash is `naming_crashed_row`,
    CANNOT ANSWER, exit 3. `--quiet` stays: the script's WARNINGs are about
    a chain link it could not read, and the `manifest` row now carries
    `validate-manifest.py`'s WARNING for that same link (#448), so the fact
    is said once.

    AND A CHECKOUT WHOSE OWN POLICY DOES NOT LOAD HAS NOT ANSWERED EITHER
    (#678). The script refuses, exit 2, before it reads the project, when
    this checkout's `contracts/repository-naming.yaml` does not load, and
    `crashed` answers None for a printed `REFUSED`, so a compliant project
    read `INVALID (naming)`, exit 1, "the naming policy is not satisfied
    (exit 2)": a person failed for the checkout's file, in the wrong verb.
    `run_naming_script` asks the question before it runs the script and reads
    the script's own `REFUSED` for that file after, and the row is
    `naming_policy_row`'s: CANNOT ANSWER, exit 3, as a crash is. Any other
    exit 2 is the script refusing something else -- the project's own
    `project.yaml`, say -- and is worded "refuses (exit 2)" as `validator_row`
    words it, and stays a finding. Exit 1 is the finding it always was.
    """
    waiting = waiting_row(ctx, "naming", "naming",
                          "there are no leg names to classify")
    if waiting is not None:
        return waiting
    script = ctx.shape / NAMING_SCRIPT
    code, quoted, whole, refusal = run_naming_script(
        ctx, script, ["--project", str(ctx.root / PROJECT_MANIFEST),
                      "--quiet"])
    detail = {"policy": (ctx.shape / NAMING_COPY).as_posix(), "exit": code}
    if code == 0:
        return Row("naming", "naming", OK,
                   "every leg name classifies, and each declared role agrees "
                   "with its form", None, detail)
    command = (f"{PYTHON} {quote_arg(script)} --explain --project "
               f"{quote_arg(ctx.root / PROJECT_MANIFEST)}")
    if refusal is not None:
        return naming_policy_row(refusal, command, detail)
    crash = crashed(code, whole)
    if crash is not None:
        return naming_crashed_row(code, crash, command, detail)
    if code >= 2:
        return Row("naming", "naming", FINDING,
                   naming_refuses_words(code, quoted), command, detail)
    return Row("naming", "naming", FINDING,
               f"the naming policy is not satisfied (exit {code})"
               + (f": {quoted}" if quoted else ""), command, detail)


def own_naming_policy(shape: Path) -> tuple:
    """`(policy, None)`, or `(None, what it raised)`, for THIS CHECKOUT's own
    `contracts/repository-naming.yaml` (#707): the ONE place the doctor asks
    whether that file loads.

    `NamingPolicy.load` is the reader `validate-repository-naming.py` itself
    calls before it reads a name, and a refusal from it is that script's exit
    2. What else it raises -- a pattern `re.compile` will not take -- is a
    fault in the same file, and the caller says which kind it wants to know
    of: `own_naming_policy_refusal`, the `naming` rows', leaves that kind to
    the script's own crash row; `way_in_project`, which runs no script, has
    nobody else to say it.
    """
    try:
        return NamingPolicy.load(shape / NAMING_COPY), None
    except Exception as exc:  # noqa: BLE001 - a fault in the file, see above
        return None, exc


def own_naming_policy_refusal(shape: Path) -> Refusal | None:
    """The refusal THIS CHECKOUT's `contracts/repository-naming.yaml` gives
    where it does not load, else None (#678).

    ONLY A REFUSAL IS ANSWERED HERE: a reader that raises anything else -- a
    pattern `re.compile` will not take -- is the script's crash, which
    `crashed` says and `naming_crashed_row` words, so that exception is the
    script's to raise and never this report's. The `the way in` rows ask
    `own_naming_policy` instead, for they run no script (#707).
    """
    _policy, fault = own_naming_policy(shape)
    return fault if isinstance(fault, Refusal) else None


def naming_policy_refusal_of(shape: Path, fault: Exception,
                             code: str = "policy-raised") -> Refusal:
    """`fault`, from `own_naming_policy`, as a `Refusal` a row can quote (#707):
    the loader's own where it is one, else one with `code` naming what was
    raised, so a policy that raises and one that refuses are quoted, and
    carried in `detail.refusal`, in one shape. `code` is `policy-raised` for
    the loader, and `policy-unusable` for a policy that loaded and raised when
    it was asked (`way_in_project`)."""
    if isinstance(fault, Refusal):
        return fault
    kind = type(fault)
    name = (kind.__qualname__ if kind.__module__ == "builtins"
            else f"{kind.__module__}.{kind.__qualname__}")
    return Refusal(code, f"{shape / NAMING_COPY}: {name}: {fault}")


def naming_script_refusal(shape: Path, whole: str) -> Refusal | None:
    """The `REFUSED` line of the naming script's output that names THIS
    CHECKOUT's policy file, as the `Refusal` it was printed from, else None
    (#678).

    A line is that script's `str(Refusal)`, `REFUSED <code>: <detail>`, and
    the `detail` of a refusal about a file STARTS with the path the loader
    was given, so the file is this checkout's where the detail starts with
    its path and `: `. A path found anywhere else in a line is not that
    file: a project whose own path holds this checkout's, a flag, the
    `project.yaml` the script was asked to read -- each is about what the
    script was asked, and is not this.
    """
    policy = f"{shape / NAMING_COPY}: "
    for line in (line.strip() for line in whole.splitlines()):
        if line.startswith("REFUSED "):
            code, _, detail = line.removeprefix("REFUSED ").partition(": ")
            if detail.startswith(policy):
                return Refusal(code, detail)
    return None


def run_naming_script(ctx: Context, script: Path, args: list[str]) -> tuple:
    """`(exit code, the line worth quoting, whole output, refusal)` for the
    naming script, or, where this checkout's own policy does not load, the
    refusal alone, with the script NOT RUN and no exit code (#678).

    BOTH `naming` ROWS ASK THIS QUESTION AND NEITHER MAY ASK IT AFTER. The
    script refuses before it reads the project or a name, so the answer it
    would give is this checkout's, and a refusal read out of its output is
    only the same question asked of a child. It is asked first and in
    process, with the reader the script uses, and the output is read for it
    as well, because a script that refuses naming that file after this
    process read it fine is still this checkout's refusal (`refusal`).
    """
    refusal = own_naming_policy_refusal(ctx.shape)
    if refusal is not None:
        return None, "", "", refusal
    code, quoted, whole = run_validator(ctx, script, args)
    return (code, quoted, whole,
            naming_script_refusal(ctx.shape, whole) if code == 2 else None)


def naming_refuses_words(code: int, quoted: str) -> str:
    """What the naming script's exit 2 reads as when it is not this
    checkout's own policy refusing: "refuses", the verb `validator_row`
    picks for any exit past 1, and not "is not satisfied", which is a
    finding's (#678)."""
    return (f"the standard's {NAMING_SCRIPT} refuses (exit {code})"
            + (f": {quoted}" if quoted else ""))


def naming_row_subject(names: list[str] | None) -> tuple:
    """`(lead, owner, about)`: how a `naming` row about the checkout's own
    script or file says what it does not belong to and what it is not saying
    anything about -- the project, in a root; given the `names`, this
    directory (#410, #678)."""
    if names is None:
        return "", "the project", "the project"
    return f"{', '.join(names)}: ", "this directory", "what it is called"


def naming_policy_words(refusal: Refusal, owner: str, about: str,
                        verb: str = "does not load") -> tuple:
    """`(reason, why)` for a row about a checkout whose own
    `contracts/repository-naming.yaml` does not load (#678, #707): the file
    named, the loader's own line quoted whole, and whose the file is -- the
    checkout's, not `owner`'s -- so that nothing here is a statement about
    `about`. A refusal's remedy, where it has one, leads the `why`. `verb` is
    "cannot be used" for a policy that loaded and raised when it was asked."""
    mend = ("the file belongs to the checkout of the standard this command is "
            f"run from, not to {owner}: repair it there, or run the doctor "
            "from a clone of the standard whose own copy loads")
    return (f"the standard's {NAMING_COPY} {verb}: "
            f"{refusal_line(refusal)}; that file is this checkout's, not "
            f"{owner}'s, so nothing here is a statement about {about}",
            " ".join(filter(None, (remedy_as_why(refusal), mend))))


def naming_policy_row(refusal: Refusal, command: str, detail: dict,
                      names: list[str] | None = None) -> Row:
    """The `naming` row for a checkout whose own
    `contracts/repository-naming.yaml` does not load (#678): `check_naming`'s,
    or, given the `names` it classified, `check_not_a_root_naming`'s.

    THAT FILE IS ALWAYS THIS CHECKOUT'S, never the project's, so this is what
    a crash of the naming script is in `naming_crashed_row` (#410) and what
    a crash of the standard's TEMPLATE validator is in `validator_row`
    (#278): `detail.environment`, so an assembly root's verdict is CANNOT
    ANSWER, exit 3, and the reason says nothing here is a statement about the
    project. In a directory that is not a root the verdict stays NOT A SHAPE
    ROOT, exit 2, as it does for a crash. It carries no `detail.crashed`: the
    script did not crash, it refused, and `detail.refusal` is the loader's
    own `code` and `detail`, as the `manifest` row's is.

    THE LOADER'S OWN LINE, WHOLE, quoted from the refusal rather than from
    the script's output, which `run_validator` cuts at 200 characters, and
    here the line ends with the line number after a path of any length. The
    NEXT is the script's own `--explain` line, which prints the same refusal
    and exits 2; a refusal's remedy, where it has one, leads the `why`.
    """
    detail["environment"] = True
    detail["refusal"] = {"code": refusal.code, "detail": refusal.detail}
    lead, owner, about = naming_row_subject(names)
    reason, why = naming_policy_words(refusal, owner, about)
    return Row("naming", "naming", FINDING, f"{lead}{reason}", command,
               detail, why=why)


def naming_crashed_row(code: int, crash: str, command: str, detail: dict,
                       names: list[str] | None = None) -> Row:
    """The `naming` row for a naming script that ended without a verdict
    (#410): `check_naming`'s, or, given the `names` it classified,
    `check_not_a_root_naming`'s.

    THE NAMING SCRIPT IS ALWAYS THIS CHECKOUT'S, never the project's, so its
    crash is what a crash of the standard's TEMPLATE validator is in
    `validator_row` (#278): `detail.crashed`, and `detail.environment`, so
    an assembly root's verdict is CANNOT ANSWER, exit 3, and the reason
    says nothing here is a statement about the project. In a directory that
    is not a root the same marking leaves the verdict NOT A SHAPE ROOT, exit
    2, because `verdict_for` decides that before `cannot_answer`; what the
    marking changes there is the row, which used to quote the script's
    exception as a fact about the name. The NEXT is the script's own line,
    as before, and its `why` is a crash row's: read the output in full.
    """
    detail["crashed"] = True
    detail["environment"] = True
    lead, owner, about = naming_row_subject(names)
    return Row("naming", "naming", FINDING,
               f"{lead}the standard's {NAMING_SCRIPT} "
               f"crashed before reaching a verdict (exit {code}): {crash}; "
               f"that script is this checkout's, not {owner}'s, so nothing "
               f"here is a statement about {about}", command, detail,
               why=CRASH_WHY)


def check_manifest(ctx: Context) -> Row:
    own = "scripts/validate-manifest.py"
    template = "templates/assembly-root/scripts/validate-manifest.py"
    if ctx.manifest_refusal is not None:
        return unloaded_manifest_row(ctx, "manifest", "manifest", own,
                                     template)
    return validator_row(ctx, "manifest", "manifest", own, template,
                         ["--root", str(ctx.root)])


#: THE TWO LOCKSTEP GATES, as `(the root's own copy, the standard's template)`,
#: spelled ONCE. `check_pins` and `check_family` run them, and the `legs` and
#: `members` rows (`lockstep_next`, #276) hand them over for what no checkout
#: cures; a path typed in each place is a gate the rows can disagree about.
PINS_GATE = ("scripts/validate-pins.py",
             "templates/assembly-root/scripts/validate-pins.py")
FAMILY_GATE = ("scripts/validate-family.py",
               "templates/family-root/scripts/validate-family.py")


def check_pins(ctx: Context) -> Row:
    # `validate-pins.py` reads `project.yaml` FIRST -- the legs it checks are
    # the ones declared there -- and refuses before any pin when it does not
    # load, so with the manifest unloadable this row has no question (#205).
    waiting = waiting_row(ctx, "pins", "pins",
                          "validate-pins.py, which reads it before it checks "
                          "a single pin, has nothing to check yet")
    if waiting is not None:
        return waiting
    output: list[str] = []
    row = validator_row(ctx, "pins", "pins", *PINS_GATE,
                        ["--root", str(ctx.root)], output=output)
    whole = "".join(output)
    return with_merged_away_rows(ctx, with_gitlink_repairs(ctx, row, whole),
                                 whole)


def bump_leg_command(shape: Path, root: Path, role: str, commit: str,
                     platform: str | None = None) -> str:
    """The `scripts/bump-leg.py` line that puts a leg's gitlink, its pin and
    every workflow reference at `commit` in one commit, spelled for the
    READER'S shell (#478).

    From any directory: the standard's own copy of the script by its
    absolute path, `--root` the root's, and every value through `quote_arg`
    for the platform asked for, as `copy_command` and `validator_command`
    spell theirs. It carries the lane's `--trailer` where `LANES_LANE` names
    one, as the `shape currency` row's `apply` does, because it writes a
    commit too (#111).
    """
    target = host_shell_dialect() if platform is None else platform
    return " ".join([
        python_command(platform),
        quote_arg(shape / "scripts" / "bump-leg.py", target),
        "--root", quote_arg(root, target), "--leg", quote_arg(role, target),
        "--to", quote_arg(commit, target)]) + lane_trailer_command(platform)


def gitlinks_off_their_pins(ctx: Context) -> list[dict]:
    """Each declared leg whose gitlink and pin name two different commits,
    as `{"role", "path", "gitlink", "pin"}`, in the manifest's order (#478).

    The `legs` row's two reads, `recorded_gitlink` (the index first, as the
    gate reads it and as `bump-leg.py` reads the commit it replaces) and
    `pin_commit`. A leg where either is not a 40-hex commit is left out:
    `bump-leg.py --to` takes nothing else, and `validate-pins.py` refuses
    such a pin before it compares it.
    """
    off = []
    for leg in ctx.legs():
        role = str(leg.get("role") or "")
        path = str(leg.get("path") or "")
        if not role or not path:
            continue
        pinned = pin_commit(ctx.root, f"contracts/{role}-pin.yaml")
        gitlink = recorded_gitlink(ctx.root, path)
        if pinned and gitlink and COMMIT_RE.match(gitlink) \
                and gitlink != pinned:
            off.append({"role": role, "path": path, "gitlink": gitlink,
                        "pin": pinned})
    return off


#: A finding as every `validate-pins.py` since v0 prints one, at the start of
#: a line: its code, and the rest of that line (#478).
FINDING_LINE = re.compile(r"FINDING (?P<code>[^\s:]+): (?P<rest>.*)")


def bump_clears(code: str, rest: str, leg: dict) -> bool:
    """Whether the `bump-leg.py` line for `leg` clears the gate's finding
    `code`, whose line goes on with `rest` (#478).

    THE THREE FACTS IT REWRITES, read as the gate has spelled each finding
    since v0: the leg's gitlink against its pin (`<path>: gitlink ...`), its
    pin's digest (`contracts/<role>-pin.yaml: ...`, recomputed), and a
    workflow reference to its repository (`` `<repository>@<sha>` ``, every
    one moved). Any other finding still stands after the rewrite, so the
    gate the bump runs is red and the bump is rolled back.
    """
    if code == "pin-gitlink-mismatch":
        return rest.startswith(f"{leg['path']}: gitlink ")
    if code == "pin-digest-mismatch":
        return rest.startswith(f"contracts/{leg['role']}-pin.yaml: ")
    if code == "pin-workflow-ref-mismatch":
        return bool(leg["repository"]) and f"`{leg['repository']}@" in rest
    return False


def findings_no_bump_clears(output: str, off: list[dict], legs: list[dict]
                            ) -> tuple[list[str], list[dict], list[str]]:
    """`(codes, other_legs, stays)` for the findings in the gate's `output`
    that no `bump-leg.py` line for a leg in `off` clears, each code once, in
    the gate's order (#478).

    `other_legs` are the legs in `legs`, the ones not in `off`, whose own
    line clears one of them, its pin's digest or a workflow reference to
    it, as `{"role", "path", "findings"}`: that line can commit only once
    the gitlink is back at its pin. `codes` are those no line for any leg
    clears (#677). `stays` are the paths of the legs in `off` whose own
    `pin-digest-mismatch` the gate reports: it is recomputed at the pin's
    commit, so it outlasts the gitlink put back there."""
    left: list[str] = []
    stays: list[str] = []
    other_legs: dict[str, dict] = {}
    for line in output.splitlines():
        found = FINDING_LINE.match(line)
        if found is None:
            continue
        code, rest = found.group("code", "rest")
        own = next((leg for leg in off if bump_clears(code, rest, leg)), None)
        if own is not None:
            if code == "pin-digest-mismatch" and own["path"] not in stays:
                stays.append(own["path"])
            continue
        whose = next((leg for leg in legs if bump_clears(code, rest, leg)),
                     None)
        codes = left if whose is None else other_legs.setdefault(
            whose["role"], {"role": whose["role"], "path": whose["path"],
                            "findings": []})["findings"]
        if code not in codes:
            codes.append(code)
    return left, list(other_legs.values()), stays


def gitlink_held_then(leg: dict, other_legs: list[dict],
                      stays: list[str]) -> str:
    """What the `pins` row says follows `leg`'s gitlink put back by hand
    while `other_legs` are out of step (#677): the gate, this row's NEXT,
    names their line, and a bump of `leg` to its gitlink keeps the move if
    it was meant. No line while `leg`'s own digest `stays`: two legs are
    then out of step with no gitlink off, and the gate names none."""
    if leg["path"] in stays:
        return (f"the gate then names no line while {leg['path']}'s own "
                "pin-digest-mismatch stands")
    digests = all(other["findings"] == ["pin-digest-mismatch"]
                  for other in other_legs)
    return ("the gate then names the bump-leg.py "
            + ("line" if digests else "lines") + " for "
            + " and ".join(other["path"] for other in other_legs)
            + f", and if {leg['path']}'s move was meant, bumping "
            f"{leg['path']} to {leg['gitlink']} "
            + ("after that line" if digests else "after one of them")
            + " keeps it")


def gitlink_repairs_held_back(off: list[dict], others: list[str],
                              manifest: bool, other_legs: list[dict] = (),
                              stays: list[str] = ()) -> str:
    """Why the `pins` row names no `bump-leg.py` line for a gitlink off its
    pin, and what comes first (#478).

    ANOTHER LEG'S DIGEST OR WORKFLOW REFERENCE IS NO FINDING TO CLEAR FIRST
    (#677). `other_legs` are the legs whose own line clears one, and that
    line is rolled back while this gitlink is off its pin, as this leg's
    lines are while that finding stands: "First clear that finding" named a
    step nothing could take. The step is the one two gitlinks off their
    pins name, by hand, for this leg; `gitlink_held_then` says what
    follows. In either text the gitlink goes back with its leg's workflow
    references, which would otherwise stay at the move and ask for the
    step again, and an undo is followed by `git submodule update` over the
    legs: it puts the gitlink back and leaves the leg checked out at the
    move, a root `bump-leg.py` refuses as dirty."""
    paths = [leg["path"] for leg in off]
    if manifest:
        return ("No single bump-leg.py line can commit while the root's "
                "validate-manifest.py is red (the `manifest` row): bump-leg.py "
                "runs it after validate-pins.py, before it commits, and rolls "
                "the bump back when either is red. First clear that row's "
                "finding; this row then names the two bump-leg.py lines for "
                f"{paths[0]}")
    what, first = [], []
    if len(off) > 1:
        what.append(" and ".join(paths) + (" are both" if len(off) == 2
                                           else " are all") + " off their pins")
    what += [f"{leg['path']} is out of step too ({', '.join(leg['findings'])})"
             for leg in other_legs]
    if others:
        what.append("the gate also reports " + ", ".join(others))
        first.append("clear " + ("that finding" if len(others) == 1
                                 else "those findings"))
    then = f"this row then names the two bump-leg.py lines for {paths[0]}"
    put = None
    if len(off) > 1:
        put = ("one leg's", "them")
        then = ("this row then names the two bump-leg.py lines for the leg "
                "that is left")
    elif other_legs:
        put = (f"{paths[0]}'s", "it")
        then = gitlink_held_then(off[0], other_legs, stays)
    if put is not None:
        legs = " ".join(quote_arg(path) for path in paths)
        first.append(f"put {put[0]} gitlink back at its pin (check that leg "
                     "out at the pin's commit and commit its gitlink in the "
                     "root, with every workflow reference to its repository "
                     "at that commit too), or undo the commit that moved "
                     f"{put[1]} and run `git submodule update -- {legs}` in "
                     "the root")
    return ("No single bump-leg.py line can commit while "
            + " and ".join(what) + ": bump-leg.py moves one leg and runs the "
            "root's whole validate-pins.py before it commits, rolling the bump "
            "back when it is red. First " + ", and ".join(first) + "; " + then)


def with_gitlink_repairs(ctx: Context, row: Row, output: str) -> Row:
    """The `pins` row, naming both repairs for a gitlink that is not its pin
    where one can commit, and what comes first where none can (#478).

    THE DEFECT. A leg moved by hand and committed (`git -C spec pull`, then
    `git add spec && git commit` in the root) made this row a FINDING whose
    NEXT is the gate, and the gate printed THE LOCKSTEP RULE and no command,
    so a person told that "a finding names its fix" was named none.

    WHICH COMMIT STAYS IS THE PERSON'S CALL, so the reason names two
    `bump-leg.py` lines and chooses neither: `--to` the gitlink's commit
    keeps the move, and `--to` the pin's undoes it. `bump-leg.py` either
    way, because it moves the gitlink, the pin and every workflow reference
    in one commit, and its `--dry-run` comes first, as AGENTS.md says.
    `git submodule update` is no undo: it checks the leg out at the gitlink,
    which is the commit being undone. The two lines are in the reason and
    in `detail.gitlink_repairs`, never in the NEXT: a NEXT is run as
    printed, and which commit stays is not the doctor's to choose. The NEXT
    stays the gate, which names the same two.

    ONLY WHERE A LINE CAN COMMIT. `bump-leg.py` runs the root's own
    `validate-pins.py` and `validate-manifest.py` after its rewrite and
    before it commits, and rolls every byte back when either is red. So the
    lines are named only where exactly ONE leg's gitlink is off its pin,
    every other finding in the gate's `output` is one a bump of that leg
    clears (`bump_clears`), and the manifest's gate passes. Two legs off, or
    any other finding, and either line is rolled back: the reason names no
    line, says why, and says what comes first, and
    `detail.gitlink_repairs_held_back` says the same for `--json`. Another
    leg's digest or workflow reference is cleared by THAT leg's line, which
    waits on this gitlink put back by hand, so what comes first is that
    step, and `other_legs` there names each such leg and its findings
    (#677). Where this leg's own digest is wrong too, it outlasts the step,
    and the reason promises no line after it.

    THE COMMIT MUST BE ON A BRANCH OF THE LEG'S REMOTE, and offline that
    cannot be known: `bump-leg.py` fetches before it asks, and a
    remote-tracking ref here says what the remote held at the last fetch,
    not what it holds. So the reason says what the command needs, and the
    doctor still fetches nothing.

    ONLY THE ROOT'S OWN GATE, THAT REPORTED FINDINGS, exit 1, and did not
    crash. A refusal stops `validate-pins.py` before it reports any finding,
    and that is the thing to fix first, and a gate that crashed is one
    `bump-leg.py` would run and find red too. A root with no gate of its
    own was answered by the standard's template copy, and `bump-leg.py`
    runs the root's copy and skips an absent one, so what the template
    reports does not say what the bump's run will. Any other row is
    returned untouched. The row is changed IN PLACE, reason and detail, so
    whatever else a `Row` carries is kept.
    """
    if row.status != FINDING or row.detail.get("exit") != 1 \
            or row.detail.get("crashed") or not row.detail.get("own_copy"):
        return row
    off = gitlinks_off_their_pins(ctx)
    if not off:
        return row
    legs = [{"role": str(leg.get("role") or ""),
             "path": str(leg.get("path") or ""),
             "repository": str(leg.get("repository") or "")}
            for leg in ctx.legs()]
    repository = {leg["role"]: leg["repository"] for leg in legs}
    roles = {leg["role"] for leg in off}
    others, other_legs, stays = findings_no_bump_clears(output, [
        {**leg, "repository": repository.get(leg["role"], "")}
        for leg in off], [leg for leg in legs if leg["role"] and leg["path"]
                          and leg["role"] not in roles])
    manifest = (len(off) == 1 and not others and not other_legs
                and check_manifest(ctx).status == FINDING)
    if len(off) > 1 or others or other_legs or manifest:
        row.reason = ascii_text(
            f"{row.reason}. " + gitlink_repairs_held_back(
                off, others, manifest, other_legs, stays))
        row.detail["gitlink_repairs_held_back"] = {
            "legs": off, "findings": others, "other_legs": other_legs,
            "manifest": manifest}
        return row
    leg = off[0]
    leg["keep_gitlink"] = bump_leg_command(ctx.shape, ctx.root, leg["role"],
                                           leg["gitlink"])
    leg["keep_pin"] = bump_leg_command(ctx.shape, ctx.root, leg["role"],
                                       leg["pin"])
    tracking = str((ctx.manifest or {}).get("tracking_branch") or "main")
    row.reason = ascii_text(
        f"{row.reason}. The gitlink and the pin name two commits, and which "
        "stays is the person's call; bump-leg.py puts the gitlink, the pin "
        f"and every workflow reference at it in one commit: for {leg['path']}"
        f", `{leg['keep_gitlink']}` keeps the gitlink's {leg['gitlink'][:12]} "
        f"and `{leg['keep_pin']}` keeps the pin's {leg['pin'][:12]}; run "
        "either with `--dry-run` first. Either commits on a branch other than "
        f"{tracking}, once the root's own validate-pins.py and "
        "validate-manifest.py pass on its rewrite (it rolls the bump back "
        "when either is red), and refuses a commit no branch of the leg's "
        "remote contains, so a commit made in the leg is pushed first")
    row.detail["gitlink_repairs"] = off
    return row


#: How every `validate-pins.py` since v0 spells a pinned copy that is not
#: there: the code, and the words after `<pin>: <path>` (#502).
COPY_MISSING_CODE = "shape-copy-missing"
COPY_MISSING_TAIL = " is pinned but absent"


def merged_away_findings(ctx: Context, output: str) -> dict | None:
    """`{pinned path: the file it was merged into}` when EVERY finding in
    the gate's `output` is `shape-copy-missing` for a `shape/` collision
    copy `update-shape.py` calls merged-away (#502); None when there is
    none, or when any finding is anything else.

    THE PATH IS READ OUT OF THE GATE'S OWN LINE, `FINDING
    shape-copy-missing: contracts/shape-pin.yaml: <path> is pinned but
    absent`, and judged by `update-shape.py`'s `merged_into`, the function
    `check` classifies the row with, so this row and the `shape currency`
    row cannot disagree about which rows `apply` drops. A line this cannot
    read that way is a finding it cannot vouch for, and the answer is None.
    """
    us = ctx.update_shape()
    lead = f"{SHAPE_PIN}: "
    merged: dict[str, str] = {}
    for line in output.splitlines():
        found = FINDING_LINE.match(line)
        if found is None:
            continue
        code, rest = found.group("code", "rest")
        if code != COPY_MISSING_CODE or not rest.startswith(lead) \
                or not rest.endswith(COPY_MISSING_TAIL):
            return None
        path = rest[len(lead):-len(COPY_MISSING_TAIL)]
        original = us.merged_into(ctx.root, path)
        if original is None:
            return None
        merged[path] = original
    return merged or None


def with_merged_away_rows(ctx: Context, row: Row, output: str) -> Row:
    """The `pins` row, naming `update-shape.py check` as its NEXT where every
    finding the gate reports is a merged-away collision copy's row (#502).

    THE DEFECT. An adopted root that did its follow-up, "merge shape/X into
    X", and removed the merged copy kept the copy's pin row, so its own
    `validate-pins.py` said `shape-copy-missing`, and this row's NEXT was
    that gate, which names no repair. No tool removed the row, and the hand
    edit of the pin that would is the one AGENTS.md forbids. Brett Heap
    ruled that the row goes, with `check` naming it and `apply` dropping it,
    so this row names the same step the `shape currency` row does: `check`,
    which reports the row `merged-away` and prints the `apply` that drops
    it behind the human's yes. The reason says so, and the command is the
    whole NEXT.

    ONLY WHERE THE STEP CLEARS EVERY FINDING, as `with_gitlink_repairs`
    names `bump-leg.py` only where a bump clears them: any other finding, a
    gate that refused or crashed, and the row is returned untouched, its
    NEXT the gate. A NEW ROW rather than this one changed in place, so
    nothing said about the gate's command stays beside a NEXT that is not
    the gate.

    AND ONLY WHERE `check` CAN READ THE ROOT (#286). A root that keeps its
    pin or its manifest as a symlink, or under one, is refused by `check`
    itself, `update-rewrite-symlink`, before it classifies a row: named
    here, `check` exited 2 and reported nothing `merged-away`, and the
    `shape currency` row named replacing the link, not `check`
    (`linked_record_row`), so both of this row's sentences were false. The
    same `linked_record` question that row asks keeps this one the gate
    until the link is replaced; the doctor run again then names `check`.

    AND ONLY WHERE THAT `apply` IS NOT REFUSED (#676). A pinned COPY kept
    as a link is no record `linked_record` asks about: `check` reads that
    root, calls the copy `copy-is-link` and says REFUSAL AHEAD over it, and
    the `apply` it prints is refused, `update-rewrite-symlink`, writing
    nothing. So "the `apply` it prints drops its pin row" was false there,
    and of a `both`, an `upstream-removed`, an `unmapped` row or a file
    `apply` would rewrite that has a hard link. `refusals_ahead` asks
    `check`'s own two questions; where it names anything, the row keeps the
    gate, says what `check` reports, merged-away and REFUSAL AHEAD both,
    and leaves the sentence about `apply` out. Where the doctor cannot ask
    them -- the `shape currency` row says why -- it keeps the gate too.
    """
    if row.status != FINDING or row.detail.get("exit") != 1 \
            or row.detail.get("crashed"):
        return row
    merged = merged_away_findings(ctx, output)
    if merged is None:
        return row
    us = ctx.update_shape()
    if us.linked_record(ctx.root, us.root_kind(ctx.root)) is not None:
        return row
    ahead = refusals_ahead(ctx, us)
    if ahead is None:
        return row
    one = len(merged) == 1
    copies = ", ".join(f"{path} (merged into {original})"
                       for path, original in merged.items())
    said = (f"{row.reason}. {copies} "
            + ("is a collision copy" if one else "are collision copies")
            + " the root merged away, so `update-shape.py check` reports "
            + ("it" if one else "them") + " `merged-away`")
    if ahead:
        refused = ", ".join(f"{path} ({why})" for path, why in ahead.items())
        return Row(row.id, row.label, row.status,
                   f"{said}, but it also says REFUSAL AHEAD over {refused}, "
                   "and the `apply` it prints refuses while "
                   + ("that is" if len(ahead) == 1 else "those are")
                   + " unresolved, so it drops no pin row yet",
                   row.next_command,
                   {**row.detail, "merged_away": merged,
                    "refusal_ahead": ahead}, why=row.why)
    reason = (f"{said}, and the `apply` it prints drops "
              + ("its pin row" if one else "their pin rows")
              + " in the re-pin commit: the step the `shape currency` row "
              "names too")
    return Row(row.id, row.label, row.status, reason,
               f"{PYTHON} {quote_arg(ctx.shape / 'update-shape.py')} check "
               f"--root {quote_arg(ctx.root)} --upstream "
               f"{quote_arg(ctx.shape)}",
               {**row.detail, "merged_away": merged})


def refusals_ahead(ctx: Context, us) -> dict | None:
    """`{path: why}` for what `update-shape.py check` names under `REFUSAL
    AHEAD` for this root, or None where the doctor cannot ask (#676).

    `check`'S OWN TWO QUESTIONS, over the rows its own `prepare` classifies:
    each row that is a conflict (`Row.is_conflict`: `both`,
    `upstream-removed`, `unmapped`, `copy-missing`, `copy-is-link`, never
    `merged-away`), by its state, and each file `apply` would rewrite in
    place that has another name (`hard_linked_rewrites`, #422), as
    `hard-link`. `apply` refuses while any of them is there, so its re-pin
    commit drops no merged-away row.

    NONE WHERE THE QUESTION CANNOT BE ASKED: the pin does not read, the
    checkout of the standard is a partial clone short of what the
    comparison reads, where `prepare` would fetch (`partial_clone_row`,
    #683), or `prepare` refuses. The `shape currency` row says which, and
    the `pins` row keeps its gate.
    """
    try:
        pin, _rows = us.read_pin(ctx.root)
    except Refusal:
        return None
    if partial_clone_row(ctx, str(pin["commit"]).lower()) is not None:
        return None
    args = argparse.Namespace(root=str(ctx.root), upstream=str(ctx.shape),
                              at=None)
    try:
        root, _pin, rows, _added, upstream, _pinned, _target, kind = \
            us.prepare(args)
    except Refusal:
        return None
    try:
        ahead = {row.path: row.state for row in rows if row.is_conflict}
        for path, _names in us.hard_linked_rewrites(root, rows, kind):
            ahead.setdefault(path, "hard-link")
    finally:
        upstream.close()
    return ahead


def check_family(ctx: Context) -> Row:
    own, template = FAMILY_GATE
    if ctx.manifest_refusal is not None:
        return unloaded_manifest_row(ctx, "family", "family", own, template)
    return validator_row(ctx, "family", "family", own, template,
                         ["--root", str(ctx.root)])


# ---------------------------------------------------------------------------
# A file or folder this user cannot read (#847)
# ---------------------------------------------------------------------------
#
# `validate-pins.py` refuses a pin, the manifest or a pinned copy that the
# operating system will not let it reach or open BY NAME, since #712:
# `REFUSED yaml-unreadable: contracts/spec-pin.yaml: cannot be read
# (Permission denied)`, with a remedy for the cause. Three rows here read the
# same files themselves, and said something else: the `legs` row that the pin
# `carries no 40-hex commit`, which the verdict read as DRIFTED; `manifest
# kinds` and `shape currency` a bare `[Errno 13]`, or, for a pin at mode 000,
# a `git checkout HEAD --` that discards what the file holds. They now ask as
# the gate asks, and say what it says.

#: The `OSError`s that mean NOTHING IS THERE to read, where any other is a
#: read the operating system refused: no such file, a part of the path that
#: is not a directory, a bad descriptor, a symlink loop, and Windows' "not
#: ready", "invalid name" and "cannot resolve". They are the ones
#: `Path.is_file()` answered False to on Python 3.9 to 3.13, and
#: `validate-pins.py` and `bump-leg.py` read them so (`_ABSENT_ERRNOS`,
#: #434, #712): read the same way here, a pin the gate calls missing is one
#: these rows call missing, and one it refuses by name they name.
ABSENT_ERRNOS = (errno.ENOENT, errno.ENOTDIR, errno.EBADF, errno.ELOOP)
ABSENT_WINERRORS = (21, 123, 1921)


def refused_read(exc: BaseException | None) -> OSError | None:
    """`exc` where it is an `OSError` with which the operating system
    REFUSED a `stat`, a read or a listing, else None: no `OSError` at all, or
    one that says nothing is there (`ABSENT_ERRNOS`) (#847).

    Asked of a `Refusal`'s `__cause__` too: `load_yaml` raises
    `yaml-unreadable` from the `OSError` of a file it could not open, which
    is how `validate-pins.py` tells that file from one that does not parse
    (`_load`, #712), whatever words the root's `repo_shape` gives it."""
    if not isinstance(exc, OSError):
        return None
    if (exc.errno in ABSENT_ERRNOS
            or getattr(exc, "winerror", None) in ABSENT_WINERRORS):
        return None
    return exc


def is_a(path: Path, kind) -> bool:
    """Whether `path` is there and of `kind` (`stat.S_ISREG`, `stat.S_ISDIR`),
    raising the `OSError` of a `stat` the operating system refused: the
    question `validate-pins.py`'s `_is_a` asks (#434, #847).

    NOT `Path.is_file()` OR `Path.is_dir()`, whose answer depends on the
    Python. Up to 3.13 they raised a refused `stat`, which ended a row in
    `could not be run: [Errno 13] ...`; from 3.14 they answer False to any
    `OSError`, which would call a pin in a `contracts/` this user cannot
    search a pin that is not there. A name the operating system cannot take
    at all is nothing there, as `is_file()` answered it."""
    try:
        mode = path.stat().st_mode
    except OSError as exc:
        if refused_read(exc) is None:
            return False
        raise
    except ValueError:
        return False
    return kind(mode)


def os_reason(exc: OSError) -> str:
    """The operating system's own reason for `exc` (`Permission denied`), or
    the exception's name where it gives none, as `validate-pins.py` names
    one (#712)."""
    return exc.strerror or type(exc).__name__


def cannot_be_read(named: str, exc: OSError) -> str:
    """`<named>: cannot be read (<the operating system's reason>)`: the line
    `validate-pins.py` refuses a file it cannot reach or open with
    (`_cannot_read`, #712), so a row and the gate say one sentence (#847)."""
    return f"{named}: cannot be read ({os_reason(exc)})"


def cannot_be_listed(named: str, exc: OSError) -> str:
    """`<named>: cannot be listed (<the operating system's reason>)`: the
    line `validate-pins.py` refuses a directory it cannot list with (#434),
    for the `contracts/` the `manifest kinds` row lists (#847)."""
    return f"{named}: cannot be listed ({os_reason(exc)})"


#: The key of a leg's or a member's `--json` entry that holds the gate's line
#: for a mount this user cannot reach (#430), or whose git directory it
#: cannot read (#1174), beside a leg's `cannot_be_read`, which is its PIN's
#: (#847).
MOUNT_UNREAD = "mount_cannot_be_read"
#: The key of a leg's `--json` entry that holds the gate's line for the ROOT's
#: own `.git` where this user cannot read it (#1146): the leg's gitlink is
#: then not known, which is not "no gitlink recorded".
GITLINK_UNREAD = "gitlink_cannot_be_read"


def root_git_read(root: Path) -> tuple | None:
    """`(the gate's line, the OSError)` where this user cannot read the
    root's own repository, else None (#1146): the `stat` of its `.git`, the
    open of a `.git` that is a gitfile, and the `stat` of the `HEAD` in the
    git directory that `.git` is or names -- what `validate-pins.py` asks
    before it reads a gitlink (`_refuse_an_unreadable_root`), in its words:
    `.git: cannot be read (<reason>)`, or the git directory a gitfile names,
    relative to the root where it is inside it and whole where it is not.

    GIT SAID NOTHING IS RECORDED. `recorded_gitlink` reads the index through
    git and takes a listing git refused for no gitlink, so a `.git` linked
    into a folder this user cannot search made the `legs` row say `no
    gitlink recorded` of every leg, and the verdict `DRIFTED (2 leg(s) not
    at the pin)`, about gitlinks nobody read. A `.git` that answers absent
    (nothing there, a link that leads nowhere or to itself), a gitfile that
    names no directory, and a git directory with no `HEAD` are None, left to
    git as they always were."""
    dotgit = root / ".git"
    named = Path(".git")
    try:
        if not is_a(dotgit, lambda _mode: True):
            return None
        gitdir = dotgit
        if is_a(dotgit, stat.S_ISREG):
            data = dotgit.read_bytes()
            if not data.startswith(b"gitdir: "):
                return None
            gitdir = dotgit.parent / os.fsdecode(
                data[len(b"gitdir: "):].rstrip(b"\r\n"))
            named = Path(os.path.normpath(gitdir))
        is_a(gitdir / "HEAD", lambda _mode: True)
    except OSError as exc:
        if refused_read(exc) is None:
            return None
        try:
            shown = named.relative_to(root).as_posix()
        except ValueError:
            shown = str(named)
        return cannot_be_read(shown_path(shown), exc), exc
    return None


def git_dir_of(dotgit: Path) -> Path | None:
    """The git directory of a mount whose `.git` is `dotgit`, found as
    `validate-pins.py`'s `_leg_git_dir` finds it (#968, #1174): `dotgit`
    itself where it is no regular file (a checkout's own directory); the
    directory a gitfile's `gitdir: ` line names, joined to the gitfile's own
    directory as git joins it, its `..` left for the system to follow; and
    None where the gitfile names none, which is left to git, as the gate
    leaves it. Raises the `OSError` of a `stat` or a read the operating
    system refused."""
    if not is_a(dotgit, stat.S_ISREG):
        return dotgit
    data = dotgit.read_bytes()
    if not data.startswith(b"gitdir: "):
        return None
    return dotgit.parent / os.fsdecode(data[len(b"gitdir: "):].rstrip(b"\r\n"))


def git_dir_named(root: Path, rel: str, gitdir: Path) -> str:
    """`gitdir` as the gate names it (`_named`, #968): normalized, from the
    root and POSIX (`.git/modules/spec`), or whole where it is not under the
    root. Where it is not under the mount at `rel`, the mount's path goes
    first (`spec: .git/modules/spec`), so the line of every row that reads
    the mount starts with that mount, as `leg_shape_summary`,
    `leg_audit_summary` and `member_problem` print it (#1174)."""
    path = Path(os.path.normpath(gitdir))
    try:
        named = path.relative_to(root).as_posix()
    except ValueError:
        named = str(path)
    mount = root / rel
    if path == mount or mount in path.parents:
        return named
    return f"{rel}: {named}"


def mount_read(root: Path, rel: str, git_dir: bool = True) -> tuple:
    """`(populated, own_git, refused)` for the leg or member mounted at `rel`:
    whether a directory with anything in it is there, whether it holds a
    `.git` of its own, and None, or `(the gate's line, the OSError, whether it
    was the listing)` where the operating system refused the mount's `stat`,
    its listing or its `.git`'s `stat` (#430), or a read of its git
    directory (#1174).

    ONE QUESTION FOR THE FOUR ROWS THAT READ A MOUNT -- `legs`, `leg shape
    files`, `placement` and `members` -- each of which asked `mount.is_dir()
    and any(mount.iterdir())`, and two of them `(mount / ".git").exists()`.
    Up to Python 3.13 a mount this user cannot enter raised out of the row,
    `could not be run: [Errno 13] ...`, and the verdict counted the empty
    `legs` row as a leg off its pin; from 3.14 the same mount was empty, an
    unbootstrapped submodule, or one with no `.git` of its own, and a checkout
    was named over it. Asked here as `validate-pins.py` asks a path (`is_a`),
    a refused read is said in the gate's words on every Python: `<rel>:
    cannot be listed (<reason>)` for a mount it cannot list, `<rel>: cannot
    be read (<reason>)` for one whose own `stat` is refused (a folder above
    it this user cannot search), and `<rel>/.git: cannot be read (<reason>)`
    for one it can list and not search, which is the line the gate refuses
    that mount with (`pin-submodule-unreadable`).

    A MOUNT WITH NOTHING IN IT HAS NO `.git`: its listing says so, so `.git`
    is asked only of a mount with something in it, which is the answer
    `(mount / ".git").exists()` gave an empty, absent or non-folder mount. A
    listing that fails because nothing is there any more is nothing there.

    ITS GIT DIRECTORY IS ASKED AS THE GATE ASKS IT (#1174, the gate's
    `_refuse_an_unreadable_git_dir`, #968): the `.git` itself where it is no
    regular file, else the directory its gitfile's `gitdir: ` line names
    (`git_dir_of`), and then the `stat` of that directory's `HEAD`. Git run
    in a mount whose git directory this user cannot search failed, so the
    `legs` and `members` rows read no HEAD and counted a leg or a member at
    its pin as one off it, and `placement` said "it is not a git
    repository"; and a `.git` DIRECTORY this user cannot search was passed
    over by git, which read the ROOT's HEAD as the leg's and named a
    checkout over it. A refused read of the gitfile is `<rel>/.git: cannot
    be read (<reason>)`, and a refused `stat` of the `HEAD` names the git
    directory as the gate names it (`git_dir_named`): `<rel>/.git`, or
    `<rel>: .git/modules/<rel>` for one outside the mount. A gitfile that
    names no directory, or a git directory with no `HEAD`, is not a read
    this user was refused: it is left to git, which answers for it as it
    always did.

    `git_dir=False` ASKS NO GIT DIRECTORY, for the `leg shape files` row,
    which compares a leg's files on disk and runs no git: a git directory
    this user cannot search keeps no file in the mount from being read, so
    that row compares them as it always did, and the `legs` row names the
    directory and gives its advice (#1174).
    """
    mount = root / rel
    try:
        if not is_a(mount, stat.S_ISDIR):
            return False, False, None
    except OSError as exc:
        return False, False, (cannot_be_read(rel, exc), exc, False)
    try:
        populated = any(mount.iterdir())
    except OSError as exc:
        if refused_read(exc) is None:
            return False, False, None
        return False, False, (cannot_be_listed(rel, exc), exc, True)
    if not populated:
        return False, False, None
    dotgit = mount / ".git"
    named = (Path(rel) / ".git").as_posix()
    try:
        if not is_a(dotgit, lambda _mode: True):
            return True, False, None
        gitdir = git_dir_of(dotgit) if git_dir else None
        if gitdir is not None:
            named = git_dir_named(root, rel, gitdir)
            is_a(gitdir / "HEAD", lambda _mode: True)
    except OSError as exc:
        return True, False, (cannot_be_read(named, exc), exc, False)
    return True, True, None


def mount_unread_said(line: str) -> str:
    """What the `legs` and `members` rows say of a mount this user cannot
    reach (#430), after the gate's line for it: no HEAD is read in it, so
    nothing says whether it is at its pin."""
    return f"{line}, so no HEAD in it is compared with the pin"


def mount_refusals(refused: list) -> str:
    """The gate's advice for the mounts `mount_read` was refused, each a
    `(line, OSError, listed)` (#430): `cannot_read_why`'s, with a refused
    listing told what a folder is told."""
    return cannot_read_why([exc for _, exc, listed in refused if not listed],
                           [exc for _, exc, listed in refused if listed])


#: What a refused PERMISSION is told, in `validate-pins.py`'s words for the
#: same file (`_unreadable_file`, #712): the mode or the owner puts it right.
PERMISSION_ADVICE = (
    "Make what this user may not open readable by this user: `chmod u+r` on "
    "a file, `chmod u+rx` on a directory (and on every directory above it "
    "inside the root), or fix who owns it.")

#: What any OTHER refusal is told, in the same gate's words (`OTHER_REASON`,
#: #712, after `bump-leg.py`, #383): an I/O error or a name the filesystem
#: will not take is not put right by `chmod`.
OTHER_REASON = (
    "Where the operating system gave another reason, put a regular file this "
    "user can open back in its place, or take away one nobody wants, and make "
    "sure nothing is changing the directory while this runs.")

#: What a FOLDER this user cannot list is told for any other reason, in the
#: gate's words for a directory it cannot list (`_workflows_unlistable`,
#: #434): it is a directory that goes back in its place, not a file.
OTHER_REASON_FOLDER = (
    "Where the operating system gave another reason, put a directory this "
    "user can list back in its place, and make sure nothing is changing it "
    "while this runs.")


def cannot_read_why(refused: list, unlisted: list = ()) -> str:
    """The `why` of a row whose NEXT is this doctor again because a file or
    folder it reads cannot be read: `refused` the `OSError` of each file,
    `unlisted` that of each folder it cannot list (#847).

    THE GATE'S ADVICE, BY THE CAUSE, and never a `git checkout`: the file is
    there, and HEAD's copy put in its place would discard whatever it holds
    that no commit does, as `pin_restore`'s `uncommitted` line says of
    itself. A permission, of a file or a folder, is `PERMISSION_ADVICE`; any
    other cause is `OTHER_REASON` for a file and `OTHER_REASON_FOLDER` for a
    folder, as the gate tells the two apart. What a person does about a
    mode or an owner is theirs; then the doctor reads the file again."""
    said = []
    if any(isinstance(exc, PermissionError) for exc in [*refused, *unlisted]):
        said.append(PERMISSION_ADVICE)
    if any(not isinstance(exc, PermissionError) for exc in refused):
        said.append(OTHER_REASON)
    if any(not isinstance(exc, PermissionError) for exc in unlisted):
        said.append(OTHER_REASON_FOLDER)
    return " ".join(said) + " Then run this doctor again"


def doctor_line(ctx: Context) -> str:
    """This doctor, run again over the root: the NEXT of a row that names a
    file or folder only a person can mend (`cannot_read_why`), the same line
    `unreadable_next` spells for a file that does not load."""
    return (f"{PYTHON} {quote_arg(ctx.shape / 'shape-doctor.py')} --root "
            f"{quote_arg(ctx.root)}")


def pin_read(root: Path, relative: str) -> tuple:
    """`(what the file at `relative` holds, None)`; `(None, the OSError)`
    where the operating system refused its `stat` or its read; `(None,
    None)` where no regular file is there, or it does not load for another
    reason (#847).

    ASKED AS `validate-pins.py` ASKS IT (#712): the `stat` first, as its
    `_is_file` does, so a pin in a `contracts/` this user cannot search is
    named on every Python, and then the read, through `load_yaml`, whose
    refusal is raised `from` the `OSError` of a file this user cannot open
    (`_load`). Nothing there, or no regular file, is what the gate calls
    missing, and is None here as it always was."""
    path = root / relative
    try:
        if not is_a(path, stat.S_ISREG):
            return None, None
    except OSError as exc:
        return None, exc
    try:
        return load_yaml(path), None
    except Refusal as exc:
        return None, refused_read(exc.__cause__)


def manifest_candidates(root: Path) -> tuple[list[Path], list[tuple]]:
    """Every file in a root that might DECLARE a `kind:`, and `(line,
    OSError, whether it is a folder this user cannot list)` for each place
    the operating system would not let this user look (#847).

    The two manifests at the top, and everything under `contracts/`. Not the
    whole tree: a leg is its own repository with its own contracts, and a
    holder's `members/<Project>` is a whole project -- walking into either
    would make this command report on repositories it was not pointed at.

    A `contracts/` THIS USER CANNOT LIST, OR A FILE IN IT WHOSE `stat` IS
    REFUSED, IS NAMED, in `validate-pins.py`'s words (`cannot_be_listed`,
    `cannot_be_read`). `iterdir()` and `is_file()` raised the refusal out of
    the row, `could not be run: [Errno 13] Permission denied: '<root>/
    contracts'`, and from Python 3.14 `is_file()` would answer False and the
    row would count the manifests it never read as none (`is_a`). The third
    value is what `cannot_read_why` tells a folder by: a folder this user
    cannot list for another reason than permission is told to put a
    directory back, as the gate tells one, not a file.
    """
    refused: list[tuple] = []

    def regular(path: Path) -> bool:
        try:
            return is_a(path, stat.S_ISREG)
        except OSError as exc:
            refused.append((cannot_be_read(
                path.relative_to(root).as_posix(), exc), exc, False))
            return False

    found = [root / PROJECT_MANIFEST, root / FAMILY_MANIFEST]
    contracts = root / "contracts"
    try:
        listed = sorted(contracts.iterdir()) if is_a(contracts,
                                                     stat.S_ISDIR) else []
    except OSError as exc:
        refused.append((cannot_be_listed("contracts", exc), exc, True))
        listed = []
    found += [path for path in listed if path.suffix in (".yaml", ".yml")]
    return [path for path in found if regular(path)], refused


#: Named once: the row this function returns and its own `CHECKS` entry below
#: must spell the same label, or the two read as two different checks.
LABEL_MANIFEST_KINDS = "manifest kinds"


def gitlinks_under(root: Path, directory: str) -> list[str]:
    """Every gitlink the index records under `directory/`, at stage 0.

    THE INDEX, the listing `recorded_gitlink` asks first, and `-z` so a name
    git would otherwise quote comes back as itself. A conflicted path is
    skipped here for the reason that helper skips it: stages 1, 2 and 3 are
    nobody's next commit. A `directory` that is empty, absolute -- in
    either platform's spelling -- or climbs with `..` lists nothing, rather
    than every gitlink in the root -- the two legs included -- under a
    members directory that is not one.
    """
    clean = directory.strip().rstrip("/")
    if (not clean or clean.startswith(("/", "\\"))
            or re.match(r"[A-Za-z]:[\\/]", clean)
            or any(part in ("", ".", "..") for part in clean.split("/"))):
        return []
    try:
        listing = git_out(["ls-files", "-s", "-z", "--", clean], cwd=root)
    except (Refusal, OSError, ValueError):
        return []
    found = []
    for record in listing.split("\0"):
        meta, _, name = record.partition("\t")
        fields = meta.split()
        if (len(fields) == 3 and fields[0] == GITLINK_MODE
                and fields[2] == "0" and name.startswith(clean + "/")):
            found.append(name)
    return found


def family_beside_project(ctx: Context, data: dict) -> tuple[str, dict]:
    """A `family.yaml` an ASSEMBLY ROOT carries: the sentence, and the facts.

    #211. `Context` reads ONE manifest per root and `project.yaml` wins, so
    a `family.yaml` committed beside it -- hand-copied or mis-merged; no tool
    here writes both -- was listed by `check_manifest_kinds` as a manifest
    whose kind "has a registered validator". It has one, `validate-family.py`,
    and NOTHING RUNS IT HERE: the `family` check applies to a holder, and an
    assembly root's own gate is `validate-manifest.py` and `validate-pins.py`.
    A family holder is not a project -- no `project.yaml`, no legs (README,
    "Families") -- so a root declaring both is a manifest travelling with no
    gate behind it, which is the very case this row exists to report. That
    is why it is a FINDING even when every member below is in lockstep.

    AND THE MEMBERS ARE ASKED WHAT THE FAMILY'S OWN TWO GATES ASK, with
    their helper rather than a second reader. Each row it pins is looked up
    with `recorded_gitlink` -- the function `validate-family.py` refuses a
    row by (`member-gitlink-absent`, `member-gitlink-mismatch`) -- and each
    gitlink under the members directory that no row names is the state
    `family.py add` refuses to mount over (`member-path-taken`). That gate
    stops at the first absent gitlink; this names every one, because a
    reader told about IRRS and not IRSS fixes one and runs it again.

    Rows and paths default exactly as `member_state` defaults them, so this
    and the holder's `members` row cannot disagree about where a member is.
    """
    members = data.get("members")
    rows = ([row for row in members if isinstance(row, dict)]
            if isinstance(members, list) else [])
    members_dir = str(data.get("members_dir") or "members")
    entries: list[dict] = []
    problems: list[str] = []
    for row in rows:
        project = str(row.get("project") or "?")
        rel = str(row.get("path") or f"{members_dir}/{project}")
        pin = row.get("pin") if isinstance(row.get("pin"), dict) else {}
        pinned = str(pin.get("commit") or "").lower()
        pinned = pinned if COMMIT_RE.match(pinned) else None
        try:
            gitlink = recorded_gitlink(ctx.root, rel)
        except (OSError, ValueError):
            gitlink = None
        if gitlink is None:
            state = "no-gitlink"
            problems.append(f"{rel} has no gitlink (mode {GITLINK_MODE})")
        elif pinned is None:
            state = "no-pin"
            problems.append(f"{project}'s row carries no 40-hex "
                            "`pin.commit` to compare against")
        elif gitlink != pinned:
            state = "off-pin"
            problems.append(f"{rel} records gitlink {gitlink[:12]} where "
                            f"{FAMILY_MANIFEST} pins {pinned[:12]}")
        else:
            state = "at-pin"
        entries.append({"project": project, "path": rel, "pin": pinned,
                        "gitlink": gitlink, "state": state})
    declared = {entry["path"] for entry in entries}
    undeclared = [name for name in gitlinks_under(ctx.root, members_dir)
                  if name not in declared]
    problems += [f"{name} is a gitlink no {FAMILY_MANIFEST} row names"
                 for name in undeclared]
    sentence = (f"{FAMILY_MANIFEST} (family-manifest) sits beside "
                f"{PROJECT_MANIFEST} (project-manifest), and validate-family"
                ".py, the validator that kind is registered to, never runs "
                "on an assembly root -- a family holder is not a project -- "
                f"so nothing checks the {len(entries)} member(s) it pins")
    if problems:
        sentence += ": " + ", ".join(problems)
    elif entries:
        sentence += ", though each is recorded at its pin today"
    return sentence, {"manifest": FAMILY_MANIFEST, "members": entries,
                      "undeclared_gitlinks": undeclared}


#: The other way out of #211's finding, a sentence of the `manifest kinds`
#: row's `why` and never its NEXT (#548): the backticks it holds are
#: commands an interactive zsh runs where the line is pasted. NOT `family.py
#: add` here, which is what `validate-family.py`'s own refusal offers: run
#: in an assembly root it would mount the members INSIDE a project, which is
#: the one shape the family ruling rules out. Which exit is right is a fact
#: about the repository, so the row names both and decides neither.
FAMILY_BESIDE_WAY = (
    "Or move the membership family.yaml records to a holder of its own "
    "(`family.py init`, then `family.py add` there), as the human decides "
    "-- never `family.py add` here, which would mount the members inside a "
    "project")


def listed(names: list) -> str:
    """`names` as a sentence lists them."""
    return ", ".join(names)


def register_way(names: list) -> str:
    """The other way out for files of a kind nothing registers, a sentence
    of the `manifest kinds` row's `why` (#548): what its NEXT said, less the
    removal its command now is."""
    one = len(names) == 1
    return (f"Or register the kind{'' if one else 's'} {listed(names)} "
            f"declare{'s' if one else ''} in shape-doctor.py's "
            "MANIFEST_VALIDATORS, beside the check that validates "
            f"{'it' if one else 'each'}, as the human decides")


def registered_elsewhere(ctx: Context, found: list, states: dict,
                         held: set = frozenset()) -> tuple[str, list, list]:
    """Manifests whose kind is registered to a gate this root never runs:
    the sentence, the other way out, and the facts (#327).

    `found` is `(path, kind, entry)` for each, in the row's own order,
    `states` each file's git state, from `git_states`, and `held` the
    files a gate here reads, which are offered no other way out: what is
    wrong with the shape pin declaring `family-manifest` is its kind line,
    not where a family holder is (review of PR #555, round 2).

    The sentence opens the way the unregistered kind's does -- "no
    validator ... is registered for kind" -- because to this root it is the
    same fact: the registry has a validator for the kind, and none that
    runs here. Each file says which validator that is and where it does
    run.

    A FINDING, NOT A NOTE, for the reason an unregistered kind is one. A
    `note` is a difference nothing asserts, and a file declaring `kind:`
    asserts what it is; the registry exists so that no such file is
    answered by nobody, and a kind the registry knows is no better answered
    in a root whose gate never reads it. Nor could the same bytes be a
    FINDING as `family.yaml` (#211) and a note as `contracts/family.yaml`.

    The row's NEXT takes the file out as git has it (`removal_next`), and
    this names the other exit, the kind's `home`, as the human decides --
    a sentence of the row's `why`, never of its NEXT (#548). Renaming the
    file to the root's own manifest name is ruled out in that sentence,
    because that is the one move that looks like a fix: in a holder it
    makes the root read as a project, and in an assembly root it is #211's
    finding instead of this one. Each file's state is `detail`'s `git`.
    """
    clauses, detail = [], []
    for rel, kind, entry in found:
        runs = entry.runs_in()
        where = (f"{entry.how} runs only in "
                 + " or ".join(ROOT_IN_WORDS[root] for root in runs)
                 if runs else f"no check runs {entry.how}")
        clauses.append(f"{rel} ({kind}: {where})")
        detail.append({"manifest": rel, "kind": kind,
                       "validator": entry.how, "runs_in": list(runs),
                       "git": states.get(rel)})
    sentence = (f"no validator that runs in {ROOT_IN_WORDS[ctx.kind]} is "
                "registered for kind " + ", ".join(clauses))
    homes = {rel: entry.home or "a root whose gate runs its validator"
             for rel, _, entry in found if rel not in held}
    if not homes:
        return sentence, [], detail
    names = list(homes)
    one = len(names) == 1
    if len(set(homes.values())) == 1:
        other_exit = (f"move what {listed(names)} "
                      f"describe{'s' if one else ''} to {homes[names[0]]}")
    else:
        other_exit = "move what each describes to " + "; ".join(
            f"{rel}: {home}" for rel, home in homes.items())
    way = (f"Or {other_exit}, as the human decides -- never rename "
           f"{'it' if one else 'one'} to {PROJECT_MANIFEST} or "
           f"{FAMILY_MANIFEST} in this root: a family holder is not a "
           "project, and an assembly root is not a family holder")
    return sentence, [way], detail


def read_nowhere(ctx: Context, found: list,
                 states: dict) -> tuple[str, list, list]:
    """Manifests of a kind whose check runs here, at a path that check never
    reads: the sentence, the other ways out, and the facts (#439).

    `found` is `(path, kind, paths)` for each, in the row's own order, where
    `paths` are the root paths the check that runs here reads that kind at
    (`ManifestKind.read_at`), and `states` each file's git state.

    A FINDING, as Brett Heap ruled on 2026-10-12 ("#439 (registered kind at
    a path no check reads): FINDING"), for #327's reason: a file that
    declares `kind:` asserts what it is, and a kind whose check runs here is
    no better answered at a path that check never opens than in a root
    where it never runs. The sentence names the path, the kind and where a
    gate here does read that kind.

    The row's NEXT takes the file out as git has it (`removal_next`). The
    other way out is the human declaring it, and only a pin in an assembly
    root can be declared: a product this root descends from is named under
    `neutral_product_pins:`, and AGENTS.md says no pin is declared that the
    human has not asked for, so the sentence says that too and never
    declares one itself. Nothing here suggests renaming the file onto a path
    a gate reads -- that would put its bytes where another file's are read
    -- and the last sentence says so.
    """
    clauses, detail = [], []
    for rel, kind, paths in found:
        clauses.append(f"{rel} ({kind}, which a gate here reads only at "
                       f"{listed(paths)})")
        detail.append({"manifest": rel, "kind": kind, "read_at": paths,
                       "git": states.get(rel)})
    sentence = "no gate here reads " + ", ".join(clauses)
    pins = [rel for rel, kind, _ in found
            if ctx.kind == PROJECT and kind == "pinned_contract_manifest"]
    ways = []
    if pins:
        ways.append(
            f"Or, if {listed(pins)} pin{'s' if len(pins) == 1 else ''} a "
            "product this root descends from, the human names that product "
            f"under `neutral_product_pins:` in {PROJECT_MANIFEST} -- and "
            "nobody declares a pin the human has not asked for")
    ways.append(f"Never rename {'it' if len(found) == 1 else 'one'} onto a "
                "path a gate here reads")
    return sentence, ways, detail


def read_here(ctx: Context, path: Path, rel: str, paths) -> str | None:
    """Which of `paths` -- the root paths a gate here reads -- is the file at
    `path` (`rel` from the root), or None where it is none of them (#439).

    BY THE FILE, NOT ONLY BY ITS SPELLING. A filesystem that folds case
    hands `validate-pins.py` the file `contracts/Spec-pin.yaml` when it
    opens `contracts/spec-pin.yaml`, and a hard link is the file its other
    name is. Called read by nothing, such a file would get a NEXT that takes
    out a pin a gate does read. So a name that is not one of `paths` is
    still read where it is the same file as one of them, and the path it
    is read at is the one returned.
    """
    if rel in paths:
        return rel
    for other in paths:
        try:
            if path.samefile(ctx.root / other):
                return other
        except OSError:
            continue
    return None


def git_states(root: Path, names: list) -> dict:
    """`{path: state}` for each of `names`, from ONE `git status`:
    `committed`, `untracked`, `ignored` or `changed` -- or `{}` where git
    cannot say (#327).

    A path `status` does not list is tracked, and HEAD, the index and the
    work tree agree on it: `committed`, the one state `git rm` takes. `??`
    alone is `untracked`, `!!` alone is `ignored` (`--ignored`, so a file
    the root's excludes hide is still named), and anything else -- an edit,
    a staged change, a file staged and never committed, a removal staged
    while the file is still on disk (`D ` and `??` at once) -- is `changed`.

    READ-ONLY AND LITERAL. `--no-optional-locks`, so `status` refreshes the
    index in memory and never writes it back: the doctor writes nothing into
    the repository. `--literal-pathspecs`, so a name holding `[` or `*` is
    that one file and not a pattern. `-z`, so a name comes back as itself,
    and `--untracked-files=all`, so it is the file and not its directory.

    AND ONLY IN A REPOSITORY OF ITS OWN. `git -C` discovers: in a plain
    directory inside another repository, `status` answers about THAT one,
    with paths relative to its top, and a `git rm` there would change it.
    `not_its_own_repository` declines to guess, as it does for a leg.
    """
    if not_its_own_repository(root) is not None:
        return {}
    try:
        raw = git_out(["--no-optional-locks", "--literal-pathspecs", "status",
                       "--porcelain=v1", "-z", "--untracked-files=all",
                       "--ignored", "--", *names], cwd=root, binary=True)
    except (Refusal, OSError):
        return {}
    codes: dict[str, set] = {}
    records = iter(raw.split(b"\0"))
    for record in records:
        if len(record) < 4:
            continue
        code = record[:2].decode("ascii", "replace")
        codes.setdefault(record[3:].decode("utf-8", "surrogateescape"),
                         set()).add(code)
        if code[0] in "RC":
            next(records, None)   # a rename's or copy's source path
    states = {}
    for name in names:
        found = codes.get(name, set())
        states[name] = ("committed" if not found
                        else "untracked" if found == {"??"}
                        else "ignored" if found == {"!!"}
                        else "changed")
    return states


#: What git reads as a pattern in a pathspec. A name holding one is passed
#: after `--literal-pathspecs`, or `git rm -- 'contracts/shape-pin[.]yaml'`
#: would take `contracts/shape-pin.yaml` out with it.
PATHSPEC_MAGIC = re.compile(r"[*?\[\\]")


def removal_next(ctx: Context, names: list,
                 states: dict) -> tuple[str | None, str]:
    """`(command, said)`: the ONE command for taking `names` out of the
    root as git has them, and the sentence that says what it does -- the
    `manifest kinds` row's NEXT and the start of its `why` (#327, #548).

    THE NEXT IS ONE COMMAND AND NOTHING ELSE (#548). It used to be prose:
    "take ... out of this root" with each way in a parenthesis, joined by
    `; ` to the next fault's sentence and holding commands in backticks,
    which an interactive zsh runs where the line is pasted (#277). Now the
    command is the first of these that applies and the sentence goes in the
    row's `why`; a file that comes out another way is named there, and the
    next run names its command.

    FOR THE FILE AS GIT HAS IT. The doctor reads the disk, so the file may
    be one nobody has committed yet, and `git rm` takes out only a file
    whose every byte a commit holds: it says "did not match any files"
    (exit 128) for one git does not track, ignored or not, and refuses one
    with changes no commit holds. So `git_states` asks first, and:
      committed   `git rm`, committed on a branch and landed as a pull
                  request, the way every change here lands, which the
                  history can undo;
      untracked,  `git status --ignored`, which shows them. NEVER the
      ignored     deletion as the NEXT (review of PR #555): no commit
                  holds such a file, so deleting it cannot be undone, and
                  AGENTS.md tells an agent to run the NEXT -- a person's
                  draft would be gone. The `why` names it, `git clean -f`
                  (`-x` too where one is ignored, which `clean` otherwise
                  leaves), for a person to run, as `pin_restore` shows a
                  file a person may have edited rather than putting it back
                  (#291, #358);
      changed     `git status`, which shows the changes, since `git rm`
                  will not discard them: commit or drop them first.
    Each path is quoted for the reader's shell like every path this report
    prints, and passed after `--literal-pathspecs` where git would read it
    as a pattern. Where git cannot say, there is no command, and the
    sentence is #211's, which holds in any state: take it out of this root.
    """
    groups = {state: [name for name in names if states.get(name) in kinds]
              for state, kinds in (("committed", ("committed",)),
                                   ("loose", ("untracked", "ignored")),
                                   ("changed", ("changed",)))}
    groups = {state: group for state, group in groups.items() if group}
    if not groups:
        return None, f"take {listed(names)} out of this root"
    state, group = next(iter(groups.items()))
    git_c = git_on(ctx, group)
    spelled = " ".join(quote_arg(name) for name in group)
    if state == "committed":
        command = f"{git_c} rm -- {spelled}"
        said = (f"takes {listed(group)} out of this root: commit that on a "
                "branch and land it as a pull request")
    elif state == "loose":
        ignored = any(states[name] == "ignored" for name in group)
        command = f"{git_c} status --ignored -- {spelled}"
        them = "it" if len(group) == 1 else "them"
        # The deletion is spelled after a colon and never in backticks,
        # which an interactive zsh or bash would run where this sentence was
        # pasted whole (review of PR #555, round 2).
        said = (f"shows {listed(group)}, which git does not track: no "
                f"commit holds {them}, so deleting {them} cannot be undone "
                f"and is a person's act, never this row's, with nothing to "
                f"commit after. A person deletes {them} with: {git_c} clean "
                f"-f{' -x' if ignored else ''} -- {spelled}")
    else:
        command = f"{git_c} status -- {spelled}"
        said = (f"shows the changes no commit holds in {listed(group)}, "
                "which git rm will not discard: commit or drop them, and "
                "the next run names the way out")
    rest = [name for other, more in groups.items() if other != state
            for name in more]
    if rest:
        said += f". The next run names the way out for {listed(rest)}"
    return command, said


def git_on(ctx: Context, names: list) -> str:
    """`git -C <root>`, quoted for the reader's shell, and
    `--literal-pathspecs` where git would read one of `names` as a
    pattern."""
    literal = (" --literal-pathspecs"
               if any(PATHSPEC_MAGIC.search(name) for name in names) else "")
    return f"git -C {quote_arg(ctx.root)}{literal}"


def showing_the_kind(ctx: Context, rel: str,
                     states: dict) -> tuple[str | None, str | None]:
    """`(command, said)`: the read-only command that shows how `rel`, a file
    a gate here reads, came to declare the kind it does, and what it shows
    (review of PR #555, round 2): its uncommitted change where it has one,
    else the last commit that changed it, else the file itself where git
    does not track it. None where git cannot say."""
    git_c, spelled = git_on(ctx, [rel]), quote_arg(rel)
    state = states.get(rel)
    if state == "changed":
        return (f"{git_c} diff HEAD -- {spelled}",
                f"shows the change to {rel} that no commit holds")
    if state == "committed":
        return (f"{git_c} log -p -1 -- {spelled}",
                f"shows the last commit that changed {rel}")
    if state in ("untracked", "ignored"):
        return (f"{git_c} status --ignored -- {spelled}",
                f"shows {rel}, which git does not track")
    return None, None


def misdeclared_said(rel: str, kind: str, read_as: str,
                     row: str | None) -> str:
    """The sentence of the `manifest kinds` row's `why` for a file a gate
    here reads as `read_as` that declares `kind` instead (review of PR
    #555, round 2): which row judges it -- that gate's own, only where the
    gate checks the kind (`kind_checked_by`), else this one -- and to put
    its kind line back."""
    judge = (f"the {row} row's gate finds that too" if row else
             "no gate here checks the kind it declares, so this row is the "
             "one that says so")
    return (f"{rel} declares kind {kind} where a gate here reads it as "
            f"{read_as}, and {judge}: put its kind line back to {read_as}")


def taking_out(ctx: Context, names: list, states: dict, judged: list,
               ways: list) -> tuple[str | None, str]:
    """`(command, why)` for the `manifest kinds` row's files, `names` being
    those to take out, `judged` those a gate here reads, as `(path, kind,
    read_as, row)`, and `ways` each other fault's other way out, a sentence
    each (#548).

    A FILE A GATE HERE READS IS NEVER TAKEN OUT (review of PR #555). It is
    the shape pin, a leg pin, a neutral product pin or the naming policy,
    and what is wrong with it is the kind it declares. So the NEXT is the
    read-only `showing_the_kind` for the first of them, and the `why` names,
    for each, the kind a gate here reads its path as, the kind it declares
    instead, and which row judges it, and says to put its kind line back.
    No other way out is offered for such a file: registering its kind, or
    moving what it describes to a holder, is no answer for a pin (round 2).
    The files to take out are named for the next run. With none judged, the
    NEXT is `removal_next`'s, as before.
    """
    said = []
    if judged:
        command, shown = showing_the_kind(ctx, judged[0][0], states)
        said += [shown] if shown else []
        said += [misdeclared_said(*entry) for entry in judged]
        if len(judged) > 1:
            said.append("The next run shows "
                        + listed([entry[0] for entry in judged[1:]]))
        if names:
            said.append(f"The next run names the way out for {listed(names)}")
    elif names:
        command, taken = removal_next(ctx, names, states)
        said.append(taken)
    else:
        command = None
    return command, ". ".join([*said, *ways])


def check_manifest_kinds(ctx: Context) -> Row:
    """Every `kind:`-bearing manifest in this root, against the registry.

    A YAML FILE WITH NO `kind:` IS NOT A MANIFEST and is skipped in silence:
    an adopted project's `contracts/policy.yaml` is its own business, and a
    tool that called every file it did not recognise a finding would be
    reporting on somebody else's data. What is reported is the other case --
    a file that DOES declare a kind that nothing here validates, which is a
    manifest travelling in a shape root with no gate behind it.

    A REGISTERED KIND WHOSE GATE THIS ROOT NEVER RUNS IS THAT CASE TOO,
    wherever the file is (#211, #327). A kind counts `validated` only where a
    check it is registered to RUNS -- `ManifestKind.runs_in` -- so a
    `contracts/family.yaml` in an assembly root, or a `contracts/project.yaml`
    in a holder, is listed under `registered_elsewhere` and is a FINDING
    `registered_elsewhere()` explains. A `family.yaml` at the top of an
    assembly root is the same fact with more to say: `family_beside_project`
    also checks the members it pins against the gitlinks.

    AND SO IS ONE AT A PATH ITS GATE NEVER READS, in a root that runs that
    gate (#439, ruled a FINDING by Brett Heap on 2026-10-12). Each gate
    opens fixed paths, and `ManifestKind.read_at` says which, so a
    `contracts/project.yaml` in an assembly root, a `contracts/family.yaml`
    or `contracts/spec-pin.yaml` in a holder, or a `contracts/<x>-pin.yaml`
    no leg and no product names, is listed under `unread` and is the FINDING
    `read_nowhere()` explains. Every file a root's own gates read is
    `validated` as before, so an untouched root's row is byte for byte the
    row it was.

    THE NEXT IS ONE COMMAND, OR NOTHING (#548). Each fault but a file that
    does not load is a file to take out of the root, so the NEXT is the one
    command `removal_next` names for them, as git has them -- a `git rm` of
    what a commit holds, and for the rest a `git status` that shows them,
    never a deletion no history can undo -- and the `why` says what it does
    and then, a sentence each, the other way out of each fault, which is
    the human's to choose: register the kind, move what the file describes
    to its `home`, declare the pin, move a membership to a holder. Those
    sentences were the NEXT, joined by `; `, and held `family.py init` and
    `family.py add` in backticks, which an interactive zsh runs where the
    line is pasted (#277).

    A FILE AT A PATH A GATE HERE READS IS NEVER `unread` AND NEVER TAKEN OUT
    (review of PR #555). `kinds_read_here` says which kind each such path is
    read as. Declaring another, the file is a fault in the kind line, and
    the NEXT shows how it came to say that (`showing_the_kind`). The `why`
    names both kinds and the row that judges it: the gate's own, where that
    gate checks the kind (`kind_checked_by`), else this one. A kind whose
    check runs here is this row's finding only there, as `misdeclared`: the
    shape pin declaring `repository-naming-policy` read COMPLIANT, though
    no gate checks the shape pin's kind (round 2).

    THE ROOT'S OWN MANIFEST, WHEN IT DOES NOT LOAD, IS NOT THIS ROW'S (#205).
    The `manifest` (or `family`) row quotes its refusal and names its gate,
    and the kind of the root was read off its filename for exactly that
    reason. Listed here as well, it would be the same fault twice, under a
    second NEXT beside the gate that row names, and on main before #291
    that NEXT was "register a kind, or remove the file from the root", the
    wrong remedy for a merge conflict in a project's own manifest. So it is
    skipped, and the row says where it went.

    A FILE THAT DOES NOT LOAD IS NOT AN UNREGISTERED KIND (#291). It used to
    share that case's next command -- register the kind, or remove the file
    from the root -- which no file without a readable `kind:` can follow, and
    which told a reader with a conflicted `contracts/shape-pin.yaml` to
    delete the pin. The row now quotes what the loader said about each one,
    and `unreadable_next` picks the command. That sentence stays the
    unregistered kind's alone, and where a row has more than one fault -- an
    unregistered kind, a kind registered to a gate this root never runs, a
    `family.yaml` beside `project.yaml`, a kind at a path no gate reads --
    it names the restore alone, first, because the row cannot say what kind
    a file declares until it loads, and because a command and a sentence
    joined by `;` would be a second command in a pasted line (#277). The
    reason still names every fault, and the next run names the rest.
    `restore` and `refusals` join `detail` only when a file does not load,
    so every other root reports the row it always did.

    A FILE OR A FOLDER THIS USER CANNOT READ IS NEITHER (#847). A pin at
    mode 000 was `unreadable as YAML`, quoting `[Errno 13] Permission
    denied: '<root>/...'`, and `unreadable_next` read its git state: `git
    status` calls a file it cannot open changed (` M`), so the NEXT was `git
    checkout HEAD --` on it, which discards what it holds that no commit
    does. A `contracts/` this user cannot list or search ended the row in
    `could not be run: [Errno 13]`. Each is named now as `validate-pins.py`
    names it (`manifest_candidates`, `cannot_be_read`), and listed under
    `detail`'s `cannot_be_read`, only when there is one. Its NEXT is this
    doctor again and its `why` the gate's advice for the cause, a folder's
    as the gate gives a folder (`cannot_read_why`), and it comes FIRST: the
    row cannot say what kind such a file declares, or whether it loads,
    until it can be read, and a `contracts/` it cannot list hides every
    manifest in it. No git state is asked of it.
    """
    known: list[str] = []
    #: `(path, kind)` for each manifest of a kind the registry does not know.
    unknown: list[tuple] = []
    unreadable: list[str] = []
    refusals: dict[str, dict] = {}
    #: `(path, kind, entry)` for each manifest whose registered gate never
    #: runs on this kind of root (#327).
    ungated: list[tuple] = []
    #: `(path, kind, paths)` for each manifest whose gate runs here and
    #: never reads its path, with the paths it does read that kind at (#439).
    unread: list[tuple] = []
    #: `(path, kind, read_as)` for each file of a kind whose check runs here,
    #: at a path a gate reads as another kind and checks no kind at (review
    #: of PR #555, round 2): this row is the only one that can say so.
    misdeclared: list[tuple] = []
    #: `(path, kind, read_as, row)` for each file this row finds a fault in
    #: at a path a gate here reads: never taken out (`taking_out`).
    judged: list[tuple] = []
    elsewhere = (ctx.manifest_path if ctx.manifest_refusal is not None
                 else None)
    beside: tuple[str, dict] | None = None
    #: Every path a gate here reads, and the kind it reads it as, and the
    #: paths whose gate refuses another kind (review of PR #555).
    read_as = kinds_read_here(ctx)
    checked = kind_checked_by(ctx)
    #: `(line, OSError, folder)` for each file or folder this user cannot
    #: read (#847).
    candidates, refused = manifest_candidates(ctx.root)
    for path in candidates:
        if path == elsewhere:
            continue
        rel = path.relative_to(ctx.root).as_posix()
        # `load_yaml` and not `Context._read`, which says None for both a
        # refusal and an empty file: the row quotes the refusal, less the
        # path it opens with, which the row has just named.
        try:
            data = load_yaml(path)
        except Refusal as exc:
            cause = refused_read(exc.__cause__)
            if cause is not None:
                refused.append((cannot_be_read(rel, cause), cause, False))
                continue
            unreadable.append(rel)
            refusals[rel] = {"code": exc.code,
                             "detail": exc.detail.removeprefix(f"{path}: ")}
            continue
        if not isinstance(data, dict):
            unreadable.append(rel)
            refusals[rel] = {"code": None, "detail": (
                "it holds no YAML document" if data is None else
                f"it loads as a {type(data).__name__}, not a mapping")}
            continue
        kind = data.get("kind")
        if not isinstance(kind, str) or not kind:
            continue
        if (ctx.kind == PROJECT and rel == FAMILY_MANIFEST
                and kind == "family-manifest"):
            beside = family_beside_project(ctx, data)
            continue
        entry = MANIFEST_VALIDATORS.get(kind)
        # The path a gate here reads this file at, as any kind, if any.
        at = read_here(ctx, path, rel, read_as)
        wrong = (rel, kind, read_as[at], checked.get(at)) \
            if at is not None and read_as[at] != kind else None
        if entry is None or ctx.kind not in entry.runs_in():
            if entry is None:
                unknown.append((rel, kind))
            else:
                ungated.append((rel, kind, entry))
            judged += [wrong] if wrong else []
            continue
        paths = entry.reads(ctx)
        if at is None and paths is not None:
            unread.append((rel, kind, sorted(paths)))
        elif wrong is not None and wrong[3] is None:
            # A kind whose check runs here, at a path a gate reads as
            # another kind and never checks the kind of: no row but this
            # one says so (review of PR #555, round 2).
            misdeclared.append(wrong[:3])
            judged.append(wrong)
        else:
            # Its own path, or one whose gate refuses the kind it declares
            # in its own row, which is that gate's finding (round 1).
            known.append(f"{rel} ({kind})")
    detail = {"validated": known,
              "unregistered": [f"{rel} ({kind})" for rel, kind in unknown],
              "unreadable": unreadable,
              "registered_kinds": sorted(MANIFEST_VALIDATORS)}
    #: Every file the row's NEXT takes out of the root, in the row's order,
    #: and how git has each and every file it judges, asked once (#548).
    held = {entry[0] for entry in judged}
    names = [rel for rel in
             ([rel for rel, _ in unknown] + [rel for rel, _, _ in ungated]
              + [rel for rel, _, _ in unread]
              + ([FAMILY_MANIFEST] if beside is not None else []))
             if rel not in held]
    states = (git_states(ctx.root, names + [entry[0] for entry in judged])
              if names or judged else {})
    ungated_said = (registered_elsewhere(ctx, ungated, states, held)
                    if ungated else None)
    if ungated_said is not None:
        # ONLY WHEN THERE IS ONE, like `family_beside` below, so every root
        # without such a file reports the row it reported before #327.
        detail["registered_elsewhere"] = ungated_said[2]
    unread_said = read_nowhere(ctx, unread, states) if unread else None
    if unread_said is not None:
        # Likewise, so every root without one reports the row of #327.
        detail["unread"] = unread_said[2]
    if misdeclared:
        # Likewise.
        detail["misdeclared"] = [
            {"manifest": rel, "kind": kind, "read_as": read,
             "git": states.get(rel)} for rel, kind, read in misdeclared]
    # Only when there is one, so every other root's row is the row it was.
    aside = ""
    if elsewhere is not None:
        owner = MANIFEST_ROW[ctx.kind]
        detail["reported_by"] = {elsewhere.name: owner}
        aside = (f"; {elsewhere.name} does not load, and the `{owner}` row "
                 "reports it")
    if beside is not None:
        # ONLY WHEN THERE IS ONE, so every root without it reports the same
        # row, byte for byte, as it did before #211.
        detail["family_beside"] = beside[1]
    if refused:
        # Likewise (#847).
        detail["cannot_be_read"] = [entry[0] for entry in refused]
    if names or judged or unreadable or refused:
        parts = []
        #: The sentences of the `why` that name the other way out of each
        #: fault, in the row's order: never the NEXT's (#548), and never for
        #: a file a gate here reads (`taking_out`).
        ways = []
        if refused:
            parts.append(", ".join(detail["cannot_be_read"]))
        if unknown:
            parts.append("no validator registered for kind " + ", ".join(
                detail["unregistered"]))
            free = [rel for rel, _ in unknown if rel not in held]
            ways += [register_way(free)] if free else []
        if unreadable:
            said = {rel: ": ".join(filter(None, (why["code"], why["detail"])))
                    for rel, why in refusals.items()}
            parts.append("unreadable as YAML: " + ", ".join(
                f"{rel} ({said[rel]})" for rel in unreadable))
        for found in (ungated_said, unread_said):
            if found is not None:
                parts.append(found[0])
                ways += found[1]
        if misdeclared:
            parts.append(", ".join(
                f"{rel} declares kind {kind} where a gate here reads it as "
                f"{read}, and no gate here checks the kind it declares"
                for rel, kind, read in misdeclared))
        if beside is not None:
            parts.append(beside[0])
            ways.append(FAMILY_BESIDE_WAY)
        if unreadable:
            restore, command, why = unreadable_next(ctx, unreadable, detail)
            detail.update({"restore": restore, "refusals": refusals})
        else:
            command, why = taking_out(ctx, names, states, judged, ways)
        if refused:
            # FIRST, and never a git command (#847): see the docstring.
            command, why = doctor_line(ctx), cannot_read_why(
                [exc for _line, exc, folder in refused if not folder],
                [exc for _line, exc, folder in refused if folder])
        return Row("manifest-kinds", LABEL_MANIFEST_KINDS, FINDING,
                   "; ".join(parts) + aside, command, detail, why=why)
    return Row("manifest-kinds", LABEL_MANIFEST_KINDS, OK,
               f"{len(known)} manifest(s), every declared kind has a "
               f"registered validator{aside}", None, detail)


#: Named once, like `LABEL_MANIFEST_KINDS` above: this function's four
#: returns and the `CHECKS` entry below must all print the same row name.
LABEL_SHAPE_CURRENCY = "shape currency"


def readme_shape_note(ctx: Context, us, repository: str, pinned: str,
                      detail: dict) -> str:
    """One clause about the root README's `Shape:` line, or nothing at all.

    A NOTE, NEVER A FINDING, because a README is prose: the authority on what
    revision this root is a copy of is `contracts/shape-pin.yaml`, and a
    sentence that has fallen behind it is a difference worth a reader's eye
    rather than a verdict about the repository (#148). It fires only on the
    one unambiguous case — exactly one line, in the form
    `templates/family-root/README.md` renders, naming THIS pin's upstream and
    a different commit — because every other reading (no line, two of them,
    another repository's name) is one `update-shape.py apply` leaves alone
    too, and a note about a line nothing will ever rewrite is a chore with no
    exit.

    THE PIN, NOT THIS STANDARD'S HEAD, is what the line is compared against,
    and that is the question the doctor is for: `contracts/shape-pin.yaml` is
    the authority on what revision this root is a copy of, so a README that
    disagrees with it is wrong ABOUT THIS TREE, today, whatever any upstream
    has since done. Comparing against the target instead would fire on every
    project that is merely behind — including one whose README names its own
    pin perfectly — which is the `SHAPE BEHIND` verdict this row already
    carries, said twice (Copilot, PR #152).

    So the clause says what IS true rather than promising a rewrite: a README
    that has run AHEAD of the pin to the commit a re-pin is about to record
    is left alone by `apply` (it already names the target) and is still worth
    a reader's eye here. Either way the next re-pin leaves the two agreeing.

    The reader IS `update-shape.py`'s, loaded through `ctx.update_shape()`,
    so the doctor and the tool that does the rewriting cannot disagree about
    what the line says or about which readings are nobody's to touch.

    RETURNS THE CLAUSE AND RECORDS THE EVIDENCE: the row's `detail` gains a
    `readme_shape_line` entry on the same condition, because `--json` is what
    a scheduled job reads and a note that existed only inside a prose line
    would be invisible to it. Nothing is written to `detail` when there is no
    note, so the key's presence IS the answer.
    """
    readme = us.ReadmeShapeLine(ctx.root, repository, pinned)
    if readme.state != us.README_STALE:
        return ""
    detail["readme_shape_line"] = {"names": readme.named, "pin": pinned}
    return (f"  (note: {us.README}'s Shape: line names "
            f"{readme.named[:12]}, the pin {pinned[:12]} — `apply` owns "
            "that line; the next re-pin leaves them agreeing)")


def what_a_re_pin_would_move(ctx: Context, us, repository: str,
                             target: str) -> str:
    """What `apply` would put in the commit, when no copied file differs.

    A SECOND READING OF THE SAME LINE, AGAINST A SECOND COMMIT, because the
    note and this clause do not ask the same question. `readme_shape_note`
    weighs the README against the PIN — the authority on what revision this
    root is a copy of — while what `apply` would DO is settled against the
    TARGET it is about to re-pin onto. The commonest holder re-pin of all is
    where the two part company: a README naming its own pin, with both of
    them behind this standard, is `current` to the note and `stale` to
    `apply`, so a row that read an empty note as "the README stays put"
    would promise "the pin alone" about exactly the commit where that is
    least true.

    THE SAME DEFECT `update-shape.py check` CARRIED, fixed there by baa77d0
    and missed in the doctor's copy of the wording, where it also read as a
    self-contradiction: "`apply` would move the pin alone" with the note
    appended to it said in one clause that the README moves too (#158).
    """
    readme = us.ReadmeShapeLine(ctx.root, repository, target)
    if readme.state == us.README_STALE:
        return f"the pin and {us.README}'s Shape: line"
    return "the pin alone"


#: The root's own pin, as a path under the root: one spelling for the row's
#: sentence, its `--json` detail and its next command (#237).
SHAPE_PIN = "contracts/shape-pin.yaml"

#: `git status --porcelain=v1`'s codes for an UNMERGED path, as git's own
#: documentation tabulates them. Which side holds the file is NOT read off
#: the letters (`AU` is this side alone, `UA` the other alone): it is read
#: off the index stages `ls-files -u` lists, 2 for `--ours`, 3 for
#: `--theirs`.
UNMERGED_STATUS = ("DD", "AU", "UD", "UA", "DU", "AA", "UU")


def git_answer(args: list, cwd: Path, binary: bool = False):
    """`git_out`, or None where git does not answer: a non-zero exit, no
    repository, no `git` on the path, output that is not UTF-8."""
    try:
        return git_out(args, cwd=cwd, binary=binary)
    except (Refusal, OSError, ValueError):
        return None


#: How far back `pin_restore` looks for a pin that reads before it says
#: that git can name nothing. A pin breaks in one commit, or in a few in a
#: row; fifty is far past any history a NEXT should reach into.
PIN_HISTORY_DEPTH = 50


def pin_reads_at(ctx: Context, rev: str, pin: str = SHAPE_PIN) -> bool:
    """Whether the pin `rev` holds reads as one: `pin_at` names something."""
    return pin_at(ctx, rev, pin) is not None


def pin_at(ctx: Context, rev: str, pin: str = SHAPE_PIN,
           whole: bool = False):
    """What the pin `rev` holds reads as, by `read_pin`'s own checks (#237),
    or None where it does not read: for the shape pin the paths its
    `files:` rows name, never empty, and for any other file the mapping.
    `whole` asks for the shape pin as `check_pin` hands it back, `(the pin,
    its rows)`, which is how `taken_with_the_pin` reads the commit each
    side of a merge names through the same checks (#547).

    READ BEFORE IT IS NAMED: a NEXT that puts back a pin out of history
    must name one that reads. Rolling back to a pin that is broken too
    sends the reader round in a circle (two commits in a row that each broke
    it), and where HEAD's own pin reads, the bytes at fault never reached a
    commit at all, so no rollback is the fix.

    IN MEMORY, NEVER A TEMPORARY FILE, because this command writes nothing
    anywhere. The blob is read the way `load_yaml` reads the file -- strict
    UTF-8, its newlines translated as `read_text` translates them, the same
    `parse_yaml` -- and `check_pin` makes the checks `read_pin` makes, so
    the two cannot disagree about a pin. Where git gives no blob (no such
    path, no such commit) there is no pin that reads, and `files: 5`, which
    `check_pin` refuses as `update-pin-row`, does not read either (#290).

    A `TypeError` IS NOT CAUGHT. It was, for that `files: 5`; nothing in a
    pin's bytes raises one now, so one means a caller out of step with
    `check_pin`, and the doctor fails loudly rather than answer that no
    commit holds a pin to put back.

    ANY OTHER FILE `tool_written` ADMITS READS WHERE IT LOADS AS A MAPPING
    (#291). That is the question the `manifest kinds` row asks of it, and
    the one reader this file holds for a leg pin or a copy, so what the row
    puts back is what the row then reads.

    THE ROWS, NOT A YES, for the shape pin (review of PR #358): `rev` may
    be an index stage, `:2` or `:3`, and the rows of each side of a merge
    are the copies that side's tool wrote, so they are the conflicted files
    `pin_restore`'s `why` takes with the pin or gives a person to merge
    (#485, #687).
    """
    blob = git_answer(["cat-file", "blob", f"{rev}:./{pin}"],
                      ctx.root, binary=True)
    if blob is None:
        return None
    us = ctx.update_shape()
    try:
        text = blob.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        data = us.parse_yaml(text)
        if pin != SHAPE_PIN:
            return data if isinstance(data, dict) else None
        read, rows = us.check_pin(data, f"{rev}:{SHAPE_PIN}", ctx.root)
    except (Refusal, us.YamlError, ValueError):
        return None
    return (read, rows) if whole else [row.path for row in rows]


def pin_restore(ctx: Context, detail: dict | None = None,
                pin: str = SHAPE_PIN) -> tuple[str, str | None, str | None]:
    """`(restore, command, why)`: the git command that puts back a pin a tool
    wrote, chosen from the pin's own git state, read-only (#237), and the
    sentence that says what it does -- the row's `why`, apart from the
    command and never a `   # ` tail on it (#277).

    A PIN IS NEVER MENDED BY HAND, so the fix for one that does not read is
    the last one a tool wrote, out of the root's own history. Which command
    reaches it depends only on where the bad bytes are, and the first of
    these that applies decides, as `detail["restore"]`:

      unmerged     a merge left the pin conflicted. `checkout --ours`, or
                   `--theirs` where only that side holds a pin that reads,
                   of THE PIN, which only a tool writes, so one side taken
                   whole is one tool's output, and of no copy but one
                   PROVED to be tool output on both sides (#547). A side
                   whose pin does not read is never taken, as taken whole
                   it left the pin as it was and this doctor named the same
                   line again; where no side's pin reads, no line is named,
                   `(restore, None, why)`, and the `why` says the merge is a
                   person's call (`side_to_take`, #752).
                   A copy either side may have edited is never named with it
                   (#485), though a merge of two `update-shape.py apply`
                   runs conflicts in the two together: a copy can hold an
                   edit of the project, kept by `apply --accept-local` on one
                   side, and taken whole the other side's copy dropped it,
                   the hunks git merged cleanly with it, and the doctor then
                   said COMPLIANT. The copies are the files EITHER side's
                   pin has `files:` rows for, their collision copies
                   included -- those rows and not this standard's copy
                   lists, since a file neither pin has a row for is not a
                   shape copy, though the lists name its path (review of PR
                   #358). Only the taken side's can be taken (#687).
                   PROVE AND TAKE (Brett Heap, 2026-10-14T23:54:30Z, #547):
                   a conflicted copy whose two stages are each, byte for
                   byte, the standard's own file at the commit THAT side's
                   pin names, in one mode, holds no edit of the project on
                   either side. It is pure tool output, so the command
                   names it beside the pin and takes it whole, and the
                   `why` says so; `taken_with_the_pin` makes the proof, and
                   `detail["taken_with_the_pin"]` lists what it proved.
                   Every other conflicted copy is still a person's: one side
                   that differs, a mode the two sides disagree on, a side's
                   pin naming a commit the checkout this doctor runs from
                   does not hold, a path the standard does not have at that
                   commit, a read that fails. So is every copy where that
                   checkout is a partial clone, where a read can fetch, and
                   the `why` says so (`partial_clone`). Where
                   one of them is conflicted the `why` says a person merges
                   it by hand, keeping the hunks git merged, as a copy
                   conflicted on its own is merged, and that
                   `update-shape.py apply --accept-local` on a copy merged
                   unlike the pin re-pins it from the merge. The `shape
                   currency` row never names it (#501), and the `apply` it
                   names is refused and asks for it: `update-local-drift`
                   where `check` calls the
                   copy `locally-modified`, as it does with the update
                   side's pin taken, and `update-conflict` where it calls
                   it `both`, as it does with the person's side's pin
                   taken, behind the standard the copy was merged from
                   (review of PR #496). Whether the project keeps the merge
                   is the person's word: AGENTS.md's rule 3 is never to
                   pass the flag to make a refusal go away, and nothing
                   here tells a copy merged by hand from one nobody merged.
                   A COPY ONLY THE OTHER SIDE'S PIN HAS A ROW FOR (#687) --
                   a path that side's `apply --add` took from the standard
                   and the side taken here wrote as its own, say -- is
                   never taken either: `as_the_standard_wrote_it` proves
                   nothing of a side whose pin has no row for it. Nor is it
                   left out of the `why`, though the pin taken here makes it
                   the project's own file once the merge is finished: its
                   conflict holds the other side's `apply` output, and the
                   `merge` row lists it unmerged all the same. So the `why`
                   says that the other side's pin calls it a copy and the
                   pin taken here does not, and that a person merges it by
                   hand, keeping the hunks git merged. Where one side
                   deleted the copy, it says a person keeps or deletes it,
                   as there are no hunks to keep (`other_sides_copies`,
                   review of PR #736). The `--accept-local`
                   sentence is not for it, and is said only where a copy the
                   kept pin has a row for is left: `apply` refuses the flag
                   on a path the pin has no row for. In the `manifest kinds`
                   row such a copy under `contracts/` is `unmerged` while
                   the pin is conflicted, as every file the `why` gives a
                   person is, and `project` once the pin taken here reads.
                   A COPY RENAMED ON ONE SIDE (#753) conflicts under its
                   new name, as git carries the other side's edit, or
                   deletion, there, and no pin has a row for that name. Its
                   stage 1 is the merge base's blob of the copy, so
                   `copies_renamed` finds the copy by that blob, where no
                   other path of the base holds it, and the `why` names the
                   path as renamed from the copy and gives it to a person
                   (`renamed_copies`). It is never taken: neither side's
                   pin has a row to prove it by.
                   A COPY RENAMED ON BOTH SIDES (#783) is `DD` at its old
                   name, stage 1 alone, and each new name is added by one
                   side alone, with no stage 1. It is no copy to merge by
                   hunks, as git merged none there, so it leaves `copies`,
                   and the `why` says it is gone on both sides and names
                   each new name a side's own commit holds the base's blob
                   of it at, or the bytes that commit's own pin row for it
                   records, at that one path of the commit, saying where a
                   side's is not proved (`copies_renamed_twice`,
                   `twice_renamed_copies`). Where the pin taken here still
                   lists a copy renamed on one side or both, the `why` says
                   this doctor reports it missing once the merge is
                   finished (`still_listed`).
                   The manifest and README.md are never named either, though
                   `apply` writes lines of them: every other line is the
                   project's own, and one side taken whole drops the other
                   side's edits, the hunks git merged cleanly included
                   (review of PR #267). Where either is conflicted the `why`
                   says a person merges it.
                   `detail["left_for_a_person"]` lists every file the `why`
                   gives a person. A file of the project's own is never
                   named: its merge is theirs. Both pins decide which file
                   that is, not the pin taken here alone: one NEITHER
                   side's pin has a row for, under its name or under the
                   one the merge base held it at. A file only the other
                   side's pin calls a copy is named, as above (#687), and
                   so is a copy's rename, on one side or both (#753, #783).
      uncommitted  HEAD holds a pin that reads, and the tree or the index
                   differs from it. `checkout HEAD`, which drops a change no
                   tool of this standard leaves uncommitted.
      hidden       HEAD holds a pin that reads, and `git status` shows no
                   change to it: an index flag hides the copy here (a sparse
                   checkout, assume-unchanged), or the file cannot be read.
                   No commit broke it, so nothing is put back: the NEXT is
                   the `ls-files -v` that shows which, and clearing it is a
                   person's call.
      committed    a commit broke or removed the pin. `checkout <that
                   commit>~1`, the pin as it was before it. The history is
                   walked newest first, and the commit named is the first
                   whose parent holds a pin that reads, so two commits in a
                   row that each broke it are reached past. A leg pin put
                   back that names another commit than the root's gitlink
                   for that leg -- the slip was in the bump's own commit,
                   whose parent holds the OLD pin -- is still the one to put
                   back, and the `why` says what comes after it:
                   `gitlink_left_behind` (#547).
      partial      the reads above found no pin to put back, and the root
                   is a partial clone (`git clone --filter`) that lacks a
                   pin or a tree they read, HEAD's included
                   (`history_left_out`, #787). This doctor fetches nothing,
                   so those reads failed, and what puts the pin back, a
                   commit or HEAD's own pin, cannot be read here. `fetch
                   --refetch --no-filter` from the first promisor remote
                   puts in every object on its branches, and the doctor run
                   again reads the whole history; the `why` spells out that
                   fetch from each other promisor remote
                   (`partial_history_why`).
      none         nothing above: no history, a root commit, no git, a walk
                   that meets a parent holding no pin, or goes
                   `PIN_HISTORY_DEPTH` commits back, before a pin that reads.
                   Nothing git can name fixes it, and the caller says so:
                   `(restore, None, None)`.

    EVERY PIN THE COMMAND PUTS BACK IS READ FIRST, by `pin_reads_at`, the
    side of a merge included (#752): one tool's output either way, but a
    commit on that side can hold a pin a slip broke.

    THE STATUS IS TWO FIXED-WIDTH LETTERS, READ AS BYTES: `git_out`'s text
    form strips its output, and the leading space of ` M` with it. And
    `--no-optional-locks` (git 2.15) keeps `status` from refreshing the
    index, which would be this command writing into their repository. Every
    path is read relative to the root (`ls-files` and pathspecs are, and
    `<rev>:./<path>` is), so each one names the root's own file even where
    git answers from a checkout the root sits inside.

    ANY FILE UNDER `contracts/` A TOOL WROTE, NOT THE SHAPE PIN ALONE (#291).
    `pin` is the root's own `contracts/shape-pin.yaml` unless the caller
    names another file `tool_written` admits -- a pin `project.yaml`
    declares, for a leg or a neutral product, or a copy the shape pin has a
    row for -- which is how the `manifest kinds` row answers each one that
    does not load. The `why` says `copy` where the file is not a pin, and
    `pin_reads_at` says what reads. Only the shape pin's `why` names other
    paths of a merge, for a person to merge by hand: the copies `apply`
    writes in the same commit, and a conflicted manifest or README.md.
    Every pin is named alone. A leg pin moves with its gitlink, but
    `checkout --ours` on a conflicted gitlink exits 0 and leaves all three
    stages where they were, so naming it would be a command that changes
    nothing. Finishing the merge takes the gitlink, and the `pins` row then
    says whether the two agree.

    A FILE A PERSON MAY HAVE EDITED IS SHOWN, NEVER PUT BACK, in every
    state (review of PR #358). That is a copy, which can hold an edit of
    the project's -- the merge by hand `update-shape.py` asks for where a
    copy changed on both sides above all -- and a neutral product pin,
    which no tool writes after the scaffold, so every change to one is a
    person's. `edited_by_hand` says which. Each of the three commands above
    drops that edit: the other side of their merge and the hunks git merged
    cleanly, their uncommitted work, their commit. So the state picks a
    read-only command instead: `diff` for `unmerged`, which shows the hunks
    git could not merge, `diff HEAD` for `uncommitted`, and `diff
    <that commit>~1` for `committed`, every change since the newest one
    that reads. Mending the file, or merging it, is the person's, as the
    `both` exit of `update-shape.py` says of a copy changed on both sides:
    a merge by hand, then `--accept-local` on it, on the person's word,
    which `update-shape.py check` names in that file's row and the `shape
    currency` row never pre-fills (#501).
    """
    root = ctx.root
    git_c = f"git -C {quote_arg(root)}"
    what = "pin" if pin.endswith("-pin.yaml") else "copy"
    shown = edited_by_hand(ctx, pin)
    # Part of the `why` where the file is `shown`, and not the `why` itself.
    by_hand = BY_HAND_WHY[what]
    raw = git_answer(["--no-optional-locks", "status", "--porcelain=v1",
                      "--", pin], root, binary=True)
    xy = raw.decode("utf-8", "replace")[:2] if raw else ""
    if xy in UNMERGED_STATUS and shown:
        return "unmerged", (
            f"{git_c} diff -- {quote_arg(pin)}"
        ), (f"a merge left the {what} conflicted, and this shows the hunks "
            "git could not merge. "
            f"{by_hand}, so neither side is taken whole: merge it by hand, "
            "keeping the hunks git merged, then finish the merge as git says "
            "and run this doctor again")
    if xy in UNMERGED_STATUS:
        us = ctx.update_shape()
        kind = us.root_kind(root)
        # `<mode> SP <object> SP <stage> TAB <path>`, one record per stage:
        # `{path: {stage: mode}}`, the mode kept for `taken_with_the_pin`,
        # and `{path: object}` of stage 1, the merge base's, which
        # `copies_renamed` reads (#753).
        stages: dict[str, dict] = {}
        bases: dict[str, bytes] = {}
        listing = git_answer(["ls-files", "-u", "-z"], root, binary=True)
        for record in (listing or b"").split(b"\0"):
            meta, _tab, path = record.partition(b"\t")
            if path:
                stages.setdefault(path.decode("utf-8", "replace"), {})[
                    meta.rsplit(b" ", 1)[-1]] = meta.split(b" ", 1)[0]
                if meta.endswith(b" 1"):
                    bases[path.decode("utf-8", "replace")] = meta.split()[1]
        side, stage, note = side_to_take(ctx, pin, stages.get(pin, {}), what)
        if note and not side:
            return "unmerged", None, note
        if side:
            lines, copies, other_side, taken, partial = [], [], [], [], False
            renamed: dict[str, str] = {}
            twice: dict[str, dict] = {}
            kept: set = set()
            if pin == SHAPE_PIN:
                lines = sorted(name for name in (kind.manifest, us.README)
                               if name in stages)
                # Both pins say what is a copy, and the kept one what can be
                # taken: a copy only the other side's is never taken (#687).
                kept = set(pin_at(ctx, f":{stage.decode()}") or ())
                other = set(pin_at(ctx, ":3" if stage == b"2" else ":2")
                            or ())
                copies = sorted(name for name in kept if name in stages)
                other_side = sorted(name for name in other - kept
                                    if name in stages)
                named = kept | other | {pin, *lines}
                # A copy both sides renamed is `DD`, stage 1 alone (#783):
                # never taken, and never a merge of hunks there are not.
                gone = {name: bases[name] for name in copies + other_side
                        if set(stages[name]) == {b"1"}}
                copies = [name for name in copies if name not in gone]
                other_side = [name for name in other_side
                              if name not in gone]
                unnamed = {name: base for name, base in bases.items()
                           if name not in named}
                held = base_holders(ctx) if gone or unnamed else {}
                renamed = copies_renamed(kept | other, unnamed, held)
                # A path a pin has a row for is named as that, never as a
                # copy's new name too (review of PR #789).
                twice = copies_renamed_twice(
                    ctx, gone, {name: held_at for name, held_at
                                in stages.items() if name not in named},
                    held)
                # A read of a partial clone can fetch: prove nothing there.
                partial = bool(copies) and partial_clone(ctx.shape)
                if not partial:
                    taken = taken_with_the_pin(ctx, kind, copies, stages)
                copies = [name for name in copies if name not in taken]
            then, after = ", then finish", ""
            said = []
            if taken:
                if detail is not None:
                    detail["taken_with_the_pin"] = taken
                said.append(
                    f"{' and '.join(taken)} "
                    + ("are" if len(taken) > 1 else "is")
                    + " conflicted too and taken whole with the pin: each "
                    "side holds " + ("them" if len(taken) > 1 else "it")
                    + " byte for byte as the standard wrote "
                    + ("them" if len(taken) > 1 else "it") + " at the "
                    "commit that side's pin names, so neither side holds an "
                    "edit of the project")
            if lines or copies or other_side or renamed or twice:
                if detail is not None:
                    detail["left_for_a_person"] = sorted(
                        {*lines, *copies, *other_side, *renamed, *twice,
                         *(path for went in twice.values()
                           for paths in went.values() for path in paths)})
                if lines:
                    said.append(
                        f"{' and '.join(lines)} "
                        + ("are conflicted too and hold lines of the "
                           "project, so a person merges them" if len(lines) > 1
                           else "is conflicted too and holds lines of the "
                           "project, so a person merges it")
                        + ", keeping the lines update-shape.py writes from "
                        "the side taken here")
                if copies:
                    said.append(
                        f"{' and '.join(copies)} "
                        + ("are copies conflicted too" if len(copies) > 1
                           else "is a copy conflicted too")
                        + f". {BY_HAND_WHY['copy']}, so neither side is "
                        "taken whole: a person merges "
                        + ("each" if len(copies) > 1 else "it")
                        + " by hand, keeping the hunks git merged")
                    if partial:
                        said.append(PARTIAL_CLONE_WHY)
                    after = (". Where a copy as merged differs from the pin, "
                             "update-shape.py apply --accept-local on that "
                             "copy re-pins it from the merge. The shape "
                             "currency row never names it. Where "
                             "update-shape.py check calls the copy "
                             "locally-modified, the apply the row names is "
                             "refused as update-local-drift, and where "
                             "check calls it both, as update-conflict, and "
                             "either refusal asks for --accept-local on that "
                             "path")
                said += other_sides_copies(other_side, stages)
                said += renamed_copies(renamed, stages)
                said += twice_renamed_copies(twice, stage)
                said += still_listed(set(renamed.values()) | set(twice), kept)
            if said:
                then = ". " + ". ".join(said) + ". Then finish"
            return "unmerged", (
                f"{git_c} checkout {side} -- {quote_arg(pin)}"
                + "".join(f" {quote_arg(name)}" for name in taken)
            ), (f"{note} and never a hand-merged {what}{then} the merge as "
                f"git says and run this doctor again{after}")
    elif pin_reads_at(ctx, "HEAD", pin):
        if xy and shown:
            return "uncommitted", (
                f"{git_c} diff HEAD -- {quote_arg(pin)}"
            ), (f"HEAD holds a {what} that reads, and this shows the "
                f"uncommitted change that breaks the {what} here. {by_hand}. "
                "Git keeps no other copy of the change until it is "
                "committed, so nothing is put back. Mend the change, or take "
                f"the {what} as last committed once nothing in it is worth "
                "keeping, then run this doctor again")
        if xy:
            return "uncommitted", (
                f"{git_c} checkout HEAD -- {quote_arg(pin)}"
            ), (f"puts back the {what} as last committed and discards the "
                "uncommitted change that broke it, which no tool of this "
                "standard writes")
        return "hidden", (
            f"{git_c} ls-files -v -- {quote_arg(pin)}"
        ), (f"HEAD holds a {what} that reads and git status shows no change "
            "to the copy here, so no commit broke it and nothing in history "
            "is put back. S in the first column is skip-worktree, as a sparse "
            "checkout sets it, and a lowercase h is assume-unchanged: either "
            "hides the copy here from git. Any other letter means the file "
            "itself cannot be read, as the refusal says. Clearing that is for "
            "a person, then run this doctor again")
    history = git_answer(["rev-list", "-n", str(PIN_HISTORY_DEPTH), "HEAD",
                          "--", pin], root)
    for breaking in (history or "").split():
        before = f"{breaking}~1"
        if git_answer(["cat-file", "-e", f"{before}:./{pin}"],
                      root) is None:
            break
        if not pin_reads_at(ctx, before, pin):
            continue
        if shown:
            return "committed", (
                f"{git_c} diff {quote_arg(before)} -- {quote_arg(pin)}"
            ), (f"the newest {what} in its history that reads is the one "
                f"before {breaking[:12]}, the commit that broke it, and this "
                f"shows every change since. {by_hand}, so nothing is rolled "
                f"back: mend the {what}, commit that and run this doctor "
                "again")
        return "committed", (
            f"{git_c} checkout {quote_arg(before)} -- {quote_arg(pin)}"
        ), (f"the {what} as it was before {breaking[:12]}, the commit that "
            f"broke it, and the newest {what} in its history that reads. "
            f"Commit that rather than editing the {what}"
            + gitlink_left_behind(ctx, before, pin))
    remotes = history_left_out(root, pin)
    if remotes:
        return "partial", refetch_of(git_c, remotes[0]), partial_history_why(
            git_c, what, remotes)
    return "none", None, None


def other_sides_copies(names: list, stages: dict) -> list:
    """The sentences of a conflicted shape pin's `why` for `names`, the
    files conflicted beside it that only the side NOT taken has `files:`
    rows for (#687): never taken, and a person's to resolve. `stages` is
    `{path: {stage: mode}}`, as `pin_restore` reads `ls-files -u`.

    WHAT IS KNOWN, AND NOTHING ELSE (review of PR #736). The pin taken here
    reads, since `side_to_take` takes no side whose pin does not (#752),
    and it has no row for them, so once the merge is finished each is the
    project's own file, and the sentence says so.

    ONE SENTENCE FOR THE FILES BOTH SIDES HOLD, ANOTHER FOR THOSE ONE SIDE
    DELETED (`by_conflict`). A person merges the first by hand, keeping
    the hunks git merged, and keeps or deletes the second.
    """
    said = []
    for group, deleted in by_conflict(names, stages):
        many = len(group) > 1
        each = "each" if many else "it"
        said.append(
            f"{' and '.join(group)} {'are' if many else 'is'} conflicted "
            "too, and the other side's pin calls "
            + ("them copies" if many else "it a copy")
            + " where the pin taken here does not"
            + (f", and one side deleted {each}" if deleted else "")
            + ", so neither side is taken whole: once the merge is finished "
            f"{each} is the project's own file"
            + (f" if kept, and a person keeps or deletes {each} by hand"
               if deleted else f", and a person merges {each} by hand, "
               "keeping the hunks git merged"))
    return said


def by_conflict(names: list, stages: dict) -> list:
    """`names` as `(group, deleted)` pairs: those both sides of the merge
    hold first, then those only one side holds, each pair only where its
    group has a name. `stages` is `{path: {stage: mode}}`, as `pin_restore`
    reads `ls-files -u`. Both sides' stages are there for a content
    conflict, an add/add included, whose hunks a person keeps; one of them
    alone is a delete/modify conflict, or a rename the other side did not
    make, which has no hunks to keep (review of PR #736)."""
    pairs = []
    for deleted in (False, True):
        group = [name for name in names
                 if deleted != ({b"2", b"3"} <= set(stages.get(name, ())))]
        if group:
            pairs.append((group, deleted))
    return pairs


def base_holders(ctx: Context) -> dict:
    """`{blob: [paths]}`, every path of the merge base's whole tree under
    the blob it holds (`tree_holders`), the base being `merge-base HEAD
    MERGE_HEAD`, as `copies_renamed` (#753) and `copies_renamed_twice`
    (#783) weigh a blob; `{}` where git cannot name the base, as for any
    conflict but a merge's.
    """
    base = git_answer(["merge-base", "HEAD", "MERGE_HEAD"], ctx.root)
    return tree_holders(ctx, base) if base else {}


def tree_holders(ctx: Context, rev: str) -> dict:
    """`{blob: [paths]}`, every path of the whole tree `rev` names under
    the blob it holds, read from the root as `ls-tree -r` lists it, so each
    path is named as `ls-files` names it there; `{}` where git cannot read
    it. One read of the merge base (`base_holders`), and of each side's own
    commit, for `copies_renamed_twice` (review of PR #789, round 3)."""
    listing = git_answer(["ls-tree", "-r", "-z", rev], ctx.root, binary=True)
    held: dict[bytes, list] = {}
    for record in (listing or b"").split(b"\0"):
        meta, _tab, path = record.partition(b"\t")
        if path and len(meta.split()) == 3:
            held.setdefault(meta.split()[2], []).append(
                path.decode("utf-8", "replace"))
    return held


def copies_renamed(copies: set, bases: dict, held: dict) -> dict:
    """`{path: copy}` for each path conflicted beside the shape pin whose
    stages came from a rename of `copy`, a path a side's pin has a `files:`
    row for (#753). `bases` is `{path: object}`, stage 1 of each conflicted
    path no pin has a row for, the merge base's blob, and `held` the base's
    whole tree by blob (`base_holders`).

    THE MERGE BASE'S OWN BLOB, AT A NAME THE BASE DID NOT HOLD. A rename on
    one side and an edit on the other conflict under the new name, and git
    gives that path the base's bytes of the old one as its stage 1: a path
    the base did not hold has a stage 1 only where git paired it with one
    the base did. So a path is a copy's rename where the base holds
    nothing at it and its stage 1 is, object for object, the blob the base
    holds at the copy's path. A path the base held is no rename, though its
    bytes be a copy's, as the source's own file beside a collision copy
    under `shape/` can be. Since the whole base is read (below), that check
    is belt and braces: such a path's stage 1 is the blob the base holds at
    that very path, which no pin lists, so the count or the copy check
    below refuses it already. Alone it changes the answer only for a rename
    onto a path the base held (rename/add), which stays unnamed (round 3 of
    the review of PR #781). The base is `merge-base HEAD MERGE_HEAD`, read
    as git keeps it for a merge; for any other kind of conflict, or where
    git cannot say, no path is called a rename, as before.

    ONE PATH IN THE WHOLE BASE TREE HOLDS THAT BLOB, AND IT IS A COPY
    (review of PR #781). Reading the copies' paths alone, a file of the
    project's own whose bytes are a copy's, renamed, was named a rename of
    that copy, though such a file is never named. So the base's whole tree
    is read, one `ls-tree -r`, and a blob two paths hold names nothing, a
    copy's or not. Not git's own rename record (`diff -M` from the base to
    each side): that is a similarity guess of its own, made apart from the
    merge's, and nothing here guesses. What that costs is a copy renamed
    whose exact bytes the base also holds at another path, which is named
    no more than it was before #753; the `merge` row still lists it.
    """
    present = {name for names in held.values() for name in names}
    return {name: held[blob][0] for name, blob in sorted(bases.items())
            if name not in present and len(held.get(blob, ())) == 1
            and held[blob][0] in copies}


#: The commit each side of a merge records its own tree in, by the index
#: stage git gives that side's version of a path.
COMMIT_OF_STAGE = {b"2": "HEAD", b"3": "MERGE_HEAD"}


def copies_renamed_twice(ctx: Context, gone: dict, stages: dict,
                         held: dict) -> dict:
    """`{copy: {stage: [paths]}}` for each copy both sides of the merge
    renamed (#783): `gone` is `{copy: blob}`, the copies conflicted beside
    the shape pin at stage 1 alone (`DD`) with the merge base's blob of
    each, and each path is a new name of the copy on the side git gives
    `stage`, b"2" for the side checked out, b"3" for the side merged in.

    BOTH SIDES RENAMED IT. git leaves the old name `DD` and each new one
    added by one side alone (`AU`, `UA`), with no stage 1, so #781's rule,
    which keys on a path's stage 1, sees neither. And it writes its merge
    of the copy's three versions to both new names, so where a side edited
    the copy no stage holds the base's blob.

    THE BYTES THE SIDE ITSELF COMMITTED ARE THE EVIDENCE (`side_moved_it`).
    A path added by one side alone is that side's new name for the copy
    where the commit that side records (`HEAD`, `MERGE_HEAD`) holds at that
    path the merge base's blob of the copy, object for object, or the bytes
    whose sha256 that same commit's own shape pin records in its row for
    the copy (review of PR #789): where the standard moved the copy between
    the two pins, each side's `apply` rewrote it, and neither commit holds
    the base's blob. A side whose commit holds an edit there is not proved:
    no similarity index is guessed at, and git's merged content, the same
    at both names, is not taken for a pairing.

    NO OTHER PATH OF THE BASE HOLDS THOSE BYTES, as #781 weighs a blob
    (`base_holders`): the base's blob of the copy is held there by the
    copy alone, and bytes the base did not hold at the copy are held there
    by no path at all. So a path of the base holding the very bytes a side
    holds at its new name proves that name nothing, while a twin of the
    copy's old bytes does not stand in the way of bytes the standard moved
    it to. Where git cannot name the base, nothing is proved.

    AND NO OTHER PATH OF THE SIDE'S OWN COMMIT HOLDS THEM (`tree_holders`,
    review of PR #789, round 3): #781's one-path rule, applied to the
    side's tree. A project that keeps its own twin of the copy in step
    with it, and renames the twin too, holds the copy's bytes at two new
    names, and git pairs one of them with the twin: neither is proved, as
    either may be the project's own file. The same holds for the base's
    blob written at two paths.

    Only a path no pin has a row for is a candidate: `pin_restore` names
    the others as what their rows say, never as a new name too (review of
    PR #789). Several proved paths on one side were not reached in that
    review: git pairs one new name per side with the rename, another path
    a side copies the copy to is added cleanly, never conflicted, and two
    proved paths would have to hold different bytes, the base's blob at
    one and the bytes of the side's pin row at the other. The `[paths]`
    keeps them all, should git ever give more.
    """
    if not gone:
        return {}
    added = sorted(name for name, held_at in stages.items()
                   if set(held_at) in ({b"2"}, {b"3"}))
    sides = {number: (commit, pinned_sha256(ctx, commit),
                      tree_holders(ctx, commit))
             for number, commit in COMMIT_OF_STAGE.items()}
    twice: dict[str, dict] = {}
    for copy, blob in sorted(gone.items()):
        found: dict[bytes, list] = {}
        for path in added:
            number = next(iter(stages[path]))
            commit, pinned, tree = sides[number]
            if held and side_moved_it(ctx, commit, path, copy, blob,
                                      pinned.get(copy), tree, held):
                found.setdefault(number, []).append(path)
        twice[copy] = found
    return twice


def pinned_sha256(ctx: Context, rev: str) -> dict:
    """`{path: sha256}` of the `files:` rows of the shape pin `rev` holds,
    read by `pin_at` through `read_pin`'s checks, or `{}` where it does not
    read; a row with no `sha256:` maps to ''."""
    read = pin_at(ctx, rev, whole=True)
    return {row.path: row.recorded for row in read[1]} if read else {}


def side_moved_it(ctx: Context, commit: str, path: str, copy: str,
                  blob: bytes, recorded: str | None, tree: dict,
                  held: dict) -> bool:
    """Whether `path` of `commit`, one side of the merge, holds the copy
    `copy` moved there, by `copies_renamed_twice`'s evidence: bytes that
    `tree`, that commit's whole tree by blob, holds at `path` alone, and
    that are either the merge base's blob of the copy, `blob`, which the
    base `held` holds at the copy alone, or bytes the base holds at no
    path whose sha256 is `recorded`, that side's pin row for the copy."""
    spec = f"{commit}:./{path}"
    committed = git_answer(["rev-parse", "-q", "--verify", spec], ctx.root)
    if committed is None or tree.get(committed.encode("ascii")) != [path]:
        return False
    if committed.encode("ascii") == blob:
        return held.get(blob) == [copy]
    if not recorded or committed.encode("ascii") in held:
        return False
    data = git_answer(["cat-file", "blob", spec], ctx.root, binary=True)
    return (data is not None
            and ctx.update_shape().file_bytes_sha256(data) == recorded)


def twice_renamed_copies(twice: dict, stage: bytes) -> list:
    """The sentences of a conflicted shape pin's `why` for `twice`, from
    `copies_renamed_twice`, `stage` being the side taken here: one for each
    copy both sides renamed (#783), naming the new names proved on each
    side, and saying where a side's is not proved. Never the hunks git
    merged, as git merged none at the old name, and never taken: a person
    keeps one name, or both, or settles where the copy goes."""
    sides = {number: ("the side taken here" if number == stage
                      else "the other side") for number in (b"2", b"3")}
    said = []
    for copy, found in sorted(twice.items()):
        start = f"{copy} is gone on both sides of the merge"
        if not found:
            said.append(f"{start}, and where either side put it is not "
                        "proved here, so neither name is taken: a person "
                        "settles where it goes, by hand")
            continue
        renames = " and ".join(
            f"to {' and '.join(found[number])} on {sides[number]}"
            for number in sorted(found, key=lambda number: number != stage))
        new = ("name" if sum(len(paths) for paths in found.values()) == 1
               else "names")
        if len(found) > 1:
            said.append(f"{start}, renamed {renames}, and no pin lists the "
                        f"new {new}, so neither name is taken: a person "
                        "keeps one name, or both, by hand")
            continue
        unproved = next(number for number in sides if number not in found)
        said.append(f"{start}, renamed {renames}, and no pin lists the new "
                    f"{new}; where {sides[unproved]} put it is not proved "
                    "here, so neither name is taken: a person settles where "
                    "it goes, by hand")
    return said


def still_listed(gone: set, kept: set) -> list:
    """The sentence a conflicted shape pin's `why` adds for the copies in
    `gone`, renamed on one side or both (#753, #783), that `kept`, the rows
    of the pin taken here, still lists (review of PR #781): no file is at
    that name once the merge is finished unless it is renamed back, so
    this doctor reports the copy missing. Said only of such a copy: where
    the pin taken here has no row for it, nothing is missing."""
    listed = sorted(copy for copy in gone if copy in kept)
    if not listed:
        return []
    many = len(listed) > 1
    return [f"The pin taken here still lists {' and '.join(listed)}, so this "
            f"doctor reports {'them' if many else 'it'} missing once the "
            f"merge is finished, unless {'they are' if many else 'it is'} "
            "renamed back"]


def renamed_copies(renamed: dict, stages: dict) -> list:
    """The sentences of a conflicted shape pin's `why` for `renamed`,
    `{path: copy}` from `copies_renamed`: paths conflicted beside the pin
    under a name no pin has a row for, each a rename of a copy (#753).
    Never taken, as a copy only the other side's pin lists is never taken
    (`other_sides_copies`), and a person's to resolve, its old name said so
    the reader knows it for a copy; `still_listed` says what the pin taken
    here still lists.
    """
    said = []
    for group, deleted in by_conflict(sorted(renamed), stages):
        many = len(group) > 1
        each = "each" if many else "it"
        said.append(
            " and ".join(f"{name}, renamed from the copy {renamed[name]},"
                         for name in group)
            + f" {'are' if many else 'is'} conflicted too, and no pin has a "
            f"row for {'them' if many else 'it'} under "
            f"{'their new names' if many else 'its new name'}"
            + (f", and one side alone holds {each}" if deleted else "")
            + ", so neither side is taken whole: a person "
            + (f"keeps or deletes {each} by hand" if deleted
               else f"merges {each} by hand, keeping the hunks git merged"))
    return said


#: The flag of `git checkout` that takes each side's stage of a merge.
SIDE_OF_STAGE = {b"2": "--ours", b"3": "--theirs"}


def side_to_take(ctx: Context, pin: str, pin_stages: dict,
                 what: str) -> tuple:
    """`(side, stage, note)` for `pin`, which a merge left conflicted with
    `pin_stages` (`{stage: mode}`): the side `pin_restore` takes whole, as
    a `checkout` flag and an index stage, and the start of its `why`, that
    says why that side. `(None, None, why)` where no side's pin reads, the
    `why` then whole, and `(None, None, None)` where neither side holds one.

    THE SIDE TAKEN IS ONE WHOSE PIN READS (#752). `--ours` was taken
    wherever ours held a pin, read or not: one tool's output either way,
    but a commit can hold a pin a slip broke, and taken whole it left the
    pin as it was, so this doctor named the same line again. So ours where
    it reads, else theirs where that reads, and the `why` says that only
    that side's pin reads; offering the other side, as `--theirs takes the
    other side` does where both read, would offer that circle.

    NO LINE WHERE NO SIDE'S PIN READS. Taking either side whole leaves a
    pin that does not read, and a pin is never mended by hand, so no
    command is named, and the `why` says that finishing the merge, or
    aborting it to put back first the pin a side broke, is a person's call.
    """
    held = [number for number in (b"2", b"3") if number in pin_stages]
    if not held:
        return None, None, None
    reads = [number for number in held
             if pin_reads_at(ctx, f":{number.decode()}", pin)]
    if not reads:
        whose = (f"neither side's {what} reads as one" if len(held) > 1
                 else f"the one side of it that holds a {what} holds one "
                 "that does not read")
        return None, None, (
            f"a merge left the {what} conflicted, and {whose}, so no side "
            f"taken whole puts back a {what} that reads, and this doctor "
            f"would name the same line again. A {what} is never mended by "
            "hand, so no line is named here: whether to finish the merge, "
            f"or to abort it and first put back the {what} a side broke, is "
            "a person's call")
    if len(reads) > 1:
        note = (f"--theirs takes the other side. Take one side of the "
                f"{what} whole")
    elif len(held) > 1:
        note = (f"only that side's {what} reads as one, and the other side "
                f"taken whole would leave a {what} that does not read. Take "
                "it whole")
    else:
        note = f"only that side of the merge holds a {what}. Take it whole"
    return SIDE_OF_STAGE[reads[0]], reads[0], note


def taken_with_the_pin(ctx: Context, kind, copies: list,
                       stages: dict) -> list:
    """Which of `copies`, conflicted beside the shape pin, `pin_restore`
    takes whole with it: those PROVED to be pure tool output on both sides
    of the merge, in `copies`' order (#547). `stages` is `{path: {stage:
    mode}}`, as `pin_restore` reads `ls-files -u`.

    PROVE AND TAKE, Brett Heap's ruling on #460's L2-8 (2026-10-14T23:54:30Z).
    Before #496 one NEXT took every conflicted copy whole with the pin,
    right for a copy nobody edited and wrong for one kept by `apply
    --accept-local`. Since #496 (#485) every one went to a person, the
    copies two `apply` runs to different targets wrote included, and a hand
    merge that kept both sides of a hunk, then `--accept-local`, pinned a
    stale line as the project's own edit, so every later upgrade of that
    copy was a `both`. A side is proved unedited where its stage is, byte
    for byte, the standard's own file at the commit THAT side's pin names:
    its own `files:` rows and `commit:`, read by `pin_at` through the
    checks `read_pin` makes. Where both sides are, the copy is one tool's
    output either way, and the side the restore takes is the copy that
    matches the pin it keeps.

    THE MODE IS PART OF THE COPY (review of PR #586). The bytes say nothing
    of the executable bit, and a project that changed it on one side holds
    an edit no byte compare sees: taken whole, `--ours` dropped the other
    side's mode, and the `why` said neither side held an edit. So the two
    stages must hold one regular-file mode, `one_regular_mode`, and the
    restore then keeps the mode both sides hold.

    THE STANDARD'S FILE IS `update-shape.py`'s, by its `source_for`, so a
    pinned path maps to the file `check` compares it with, a collision copy
    under `shape/` included. And it comes from the checkout this doctor
    runs from, as AGENTS.md says to run it, read by `git show`: nothing is
    fetched or cloned. `pin_restore` never asks this of a checkout that is a
    partial clone (`partial_clone`), where a read fetches what it lacks.

    ANYTHING NOT PROVED STAYS THE HAND MERGE, as before: a stage that
    differs or is missing, a mode the two sides disagree on, a side's pin
    that does not read or has no row for the copy, a commit that checkout
    does not hold, a path the standard does not have at that commit, a read
    that fails, a checkout that is a partial clone. None of those is a
    guess this makes.
    """
    if not copies:
        return []
    us = ctx.update_shape()
    standard = us.Upstream(ctx.shape, str(ctx.shape))
    sides = []
    for number in ("2", "3"):
        read = pin_at(ctx, f":{number}", whole=True)
        if read is None:
            return []
        held, rows = read
        sides.append((number, str(held["commit"]).lower(),
                      {row.path for row in rows}))
    return [copy for copy in copies
            if one_regular_mode(stages.get(copy, {}))
            and all(as_the_standard_wrote_it(ctx, us, kind, standard, copy,
                                            *side) for side in sides)]


#: The modes `ls-files -u` gives a regular file's stage, executable or not.
REGULAR_FILE_MODES = (b"100644", b"100755")


def one_regular_mode(held: dict) -> bool:
    """Whether the stages the two sides of a merge hold for a copy agree on
    ONE regular-file mode (#547, review of PR #586). `held` is that copy's
    `{stage: mode}`. A side with no stage is not a mode it disagrees on:
    `as_the_standard_wrote_it` finds no stage to read and proves nothing."""
    modes = {held[number] for number in (b"2", b"3") if number in held}
    return len(modes) == 1 and modes <= set(REGULAR_FILE_MODES)


#: What the `why` adds where `pin_restore` proved no copy, because the
#: checkout of the standard is a partial clone (#547).
PARTIAL_CLONE_WHY = (
    "The checkout of the standard this doctor runs from is a partial clone, "
    "which fetches what it lacks on a read, so nothing was read from it to "
    "prove a copy unedited")


def partial_clone(shape: Path) -> bool:
    """Whether the checkout of the standard at `shape` is a partial clone:
    its config names a remote git fetches a missing object from (#547).

    A READ THERE CAN FETCH. `git show` of a blob a `--filter` clone left
    out asks its promisor remote for it, and Brett Heap's ruling for
    `taken_with_the_pin` is never to fetch, clone or touch the network. So
    `pin_restore` proves no copy there and every one stays the hand merge,
    and the `shape currency` row asks first, without fetching, whether the
    clone holds what it reads (`partial_clone_row`, #683). Which remotes
    those are is `promisor_remotes`' answer.
    """
    return bool(promisor_remotes(shape))


#: The config keys `promisor_remotes` reads: git's, in `promisor-remote.c`.
PROMISOR_KEYS = (r"^(remote\..*\.(promisor|partialclonefilter)"
                 r"|extensions\.partialclone)$")


def promisor_remotes(shape: Path) -> list:
    """The remotes git fetches a missing object from in the checkout at
    `shape`, by the rule git 2.43's `promisor-remote.c` reads its config
    with (#683): a remote whose `promisor` is true, a remote with a
    `partialclonefilter`, and the remote `extensions.partialclone` names,
    that one last, as git asks them. Each name once, in the config's order.

    `promisor = false` ALONE IS NOT ONE (#683). `partial_clone` matched
    `remote.<name>.promisor` whatever its value, so `false` counted.
    Measured with git 2.43 on a `--filter=blob:none` clone: with `promisor
    = false` and no `partialclonefilter`, a read of a blob the clone lacks
    fails and fetches nothing; with the filter kept beside it, the read
    fetches, as with `promisor = true`, a bare `promisor` key or
    `extensions.partialclone = origin` alone. So `false` is git's `false`,
    read by `git config --type=bool`, and a filter makes a remote one on
    its own. A missing object where no remote is one is a read that fails,
    which `update-shape.py` refuses (`update-upstream-unreadable`). The
    config is only read, which fetches nothing and writes nothing.
    """
    true = git_answer(["config", "--type=bool", "-z", "--get-regexp",
                       r"^remote\..*\.promisor$"], shape, binary=True)
    promised = {key for key, _newline, value in (
        record.partition(b"\n") for record in (true or b"").split(b"\0"))
        if value == b"true"}
    listed = git_answer(["config", "-z", "--get-regexp", PROMISOR_KEYS],
                        shape, binary=True)
    names: list[str] = []
    named = None
    for record in (listed or b"").split(b"\0"):
        key, _newline, value = record.partition(b"\n")
        if key == b"extensions.partialclone":
            named = value
        elif key.endswith(b".partialclonefilter") or key in promised:
            name = key[len(b"remote."):key.rindex(b".")]
            names.append(name.decode("utf-8", "replace"))
    last = [] if named is None else [named.decode("utf-8", "replace")]
    return [name for name in dict.fromkeys(names) if name not in last] + last


def as_the_standard_wrote_it(ctx: Context, us, kind, standard, copy: str,
                             number: str, commit: str, rows: set) -> bool:
    """Whether index stage `number` holds `copy` byte for byte as the
    standard wrote it at `commit`, the commit that side's pin names, whose
    `files:` rows are `rows` (#547). False wherever any of it cannot be
    read: `taken_with_the_pin` takes nothing it has not proved."""
    if copy not in rows:
        return False
    held = git_answer(["cat-file", "blob", f":{number}:./{copy}"], ctx.root,
                      binary=True)
    if held is None:
        return False
    try:
        source = us.source_for(copy, standard, commit, kind)
        wrote = standard.blob(commit, source) if source else None
    except (Refusal, OSError, ValueError):
        # `Refusal`: a read `Upstream.blob` could not make (#683).
        return False
    return wrote is not None and wrote == held


def gitlink_left_behind(ctx: Context, rev: str, pin: str) -> str:
    """What the `why` adds where `pin_restore` puts back a LEG pin out of
    history, from `rev`, that names another commit than the root's gitlink
    for that leg; otherwise nothing (#547, #460's L2-9).

    THE BUMP'S OWN COMMIT. `bump-leg.py --to X` moves the gitlink, the pin
    and every workflow reference in one commit; amend a slip into that
    commit's pin and the commit before it holds the pin for the OLD leg
    commit. Putting that pin back is still right, since it is the newest
    one that reads, but once it is committed the doctor says DRIFTED, the
    gitlink at X and the pin at the old commit. `with_gitlink_repairs`
    then names the closing step, a `bump-leg.py` line, in the `pins` row's
    reason, and a `bump-leg.py` run before the pin is committed is refused
    `bump-leg-root-dirty`. So the sentence says commit it, then run that
    line, and the NEXT stays the one command it was (#548's rule: every
    addition goes in `why`).

    THE GITLINK THE `pins` ROW READS, `recorded_gitlink` -- the index
    first, then HEAD -- since that row is the one the sentence sends the
    reader to: in a tree whose index holds what HEAD does, HEAD's gitlink.
    Nothing is said where either commit cannot be read, or for the shape
    pin, which has no gitlink.
    """
    if pin == SHAPE_PIN:
        return ""
    for leg in ctx.legs():
        role = str(leg.get("role") or "")
        path = str(leg.get("path") or "")
        if not role or not path or pin != f"contracts/{role}-pin.yaml":
            continue
        commit = str((pin_at(ctx, rev, pin) or {}).get("commit")
                     or "").lower()
        try:
            gitlink = recorded_gitlink(ctx.root, path)
        except (OSError, ValueError):
            return ""
        if not COMMIT_RE.match(commit) or not gitlink or gitlink == commit:
            return ""
        return (f". That pin names {commit[:12]} and the root's gitlink for "
                f"{path} is {gitlink[:12]}, so commit it, then run the "
                f"bump-leg.py line the pins row names for {path}: --to the "
                f"gitlink's {gitlink[:12]} keeps the move, and --to the "
                f"pin's {commit[:12]} undoes it")
    return ""


def declared_pins(ctx: Context) -> set:
    """Every pin this root DECLARES, at the path the tool that writes it
    writes it to (#291).

    The shape pin, which every root carries. `contracts/<role>-pin.yaml`
    for each leg `project.yaml` declares, the spelling `check_legs` reads,
    `validate-pins.py` checks and `bump-leg.py` writes. And
    `contracts/<product lowercased>-pin.yaml` for each name its
    `neutral_product_pins:` lists, which is `shape_materialize`'s
    `neutral_pin_path` and the spelling `validate-pins.py` checks, spelled
    here as `check_legs` spells a leg's. A role or a product that is not
    text names no pin.
    """
    pins = {SHAPE_PIN}
    pins.update(f"contracts/{leg['role']}-pin.yaml" for leg in ctx.legs()
                if isinstance(leg.get("role"), str) and leg["role"])
    return pins | neutral_pins(ctx)


def neutral_pins(ctx: Context) -> set:
    """`contracts/<product lowercased>-pin.yaml` for each name the root's
    `neutral_product_pins:` lists, as `declared_pins` spells them (#291)."""
    products = (ctx.manifest or {}).get("neutral_product_pins")
    if not isinstance(products, list):
        return set()
    return {f"contracts/{product.lower()}-pin.yaml" for product in products
            if isinstance(product, str) and product}


def pinned_copies(ctx: Context) -> set:
    """The root paths the root's own shape pin has `files:` rows for: its
    shape copies, read as `update-shape.py` reads them (review of PR #358).

    THE ROWS, NOT THIS STANDARD'S COPY LISTS. A file with no row is not a
    shape copy (`update-shape.py`'s own rule, and AGENTS.md's): an adopted
    project that merged a copy away drops its row, and the file left at its
    path is the project's own, as is the source's own file at a path an
    adoption collided on, whose copy went under `shape/` with a row naming
    that path. The lists name both paths all the same. Where the pin does
    not read, no row says anything, so nothing is a copy for that run: the
    safe side, as for a `project.yaml` that does not load.
    """
    us = ctx.update_shape()
    try:
        _pin, rows = us.read_pin(ctx.root)
    except (Refusal, us.YamlError, OSError, ValueError):
        return set()
    return {row.path for row in rows}


def edited_by_hand(ctx: Context, rel: str) -> bool:
    """Whether `rel` is a file a tool wrote that a person may have edited
    since, so that `pin_restore` shows it and puts nothing back (review of
    PR #358): a copy the shape pin has a row for, or a neutral product pin.

    A copy can hold the project's own edit: `update-shape.py` calls one
    `locally-modified` and leaves it, and where a copy changed on both
    sides it asks for a merge by hand. A neutral product pin is written by
    `scaffold-project.py --pin` and by no tool after it, and the manifest
    template says to add one by hand, so every change to one is a
    person's. The shape pin and a leg pin are a tool's alone: a person
    re-pins a leg with `bump-leg.py`, and the shape with `update-shape.py`.
    """
    return rel != SHAPE_PIN and (rel in pinned_copies(ctx)
                                 or rel in neutral_pins(ctx))


#: Why `pin_restore` puts nothing back for a file `edited_by_hand`, by what
#: its `why` calls the file: part of that `why`, off the command's line
#: (#277).
BY_HAND_WHY = {
    "copy": ("A copy can hold an edit of the project, such as the merge by "
             "hand update-shape.py asks for where a copy changed on both "
             "sides"),
    "pin": ("No tool of this standard writes a neutral product pin after the "
            "scaffold, and every change to one since was made by a person"),
}


def tool_written(ctx: Context, rel: str) -> bool:
    """Whether `rel`, a root path under `contracts/`, is a file a tool of
    this standard writes, so that git holds the last good bytes (#291).

    WHAT THE ROOT DECLARES DECIDES, NOT THE NAME. A file is a tool's where
    it is one of `declared_pins` or one of `pinned_copies`, the rows of the
    root's own shape pin, which under `contracts/` is the naming policy
    where the root keeps it. The shape pin is written by
    `scaffold-project.py`, `adopt-project.py` and `update-shape.py apply`, a
    leg pin by those and by `bump-leg.py`, and a neutral product pin by
    `scaffold-project.py --pin`. A copy or a neutral product pin can hold a
    person's edit, which is why `pin_restore` shows one and puts nothing
    back (`edited_by_hand`). Anything else under `contracts/`, and
    `project.yaml` or `family.yaml`, is the project's own. A
    `contracts/release-pin.yaml` that no leg and no product names is a file
    the project wrote, whatever it is called, and putting it back from git
    would discard the edit, the merged hunk or the commit somebody made
    (codex, review of PR #358). So is a `contracts/repository-naming.yaml`
    the shape pin has no row for, though this standard copies a file there.

    WHERE `project.yaml` DOES NOT LOAD, IT DECLARES NOTHING. A leg pin or a
    neutral product pin that does not load either is then the project's for
    that run, and is left alone. That is the safe side. Reading the roles
    from HEAD's `project.yaml` instead would decide what git puts back from
    a declaration the tree may disagree with, as the other side of a merge
    that adds or renames a leg does. A file wrongly called a tool's loses a
    person's edit, and one wrongly called the project's costs a run: once
    `project.yaml` loads, the next run names the pin's restore. The shape
    pin and its copies hang on no manifest: the shape pin stays a tool's,
    and the copies are what its rows say, whatever `project.yaml` holds.
    """
    return rel in declared_pins(ctx) or rel in pinned_copies(ctx)


#: The `why` of the `manifest kinds` row's next command where no file that
#: does not load has a copy git can put back (#291): the row's `why`, off
#: the command's line, so a pasted line is one command in any shell (#277).
UNREADABLE_BY_HAND = (
    "the reason names each file that does not load and why, and none is a "
    "file this root declares a tool writes with a copy that reads in its "
    "history, so what each should say -- a merge conflict resolved, a hand "
    "edit put right -- is for a person to decide. This row reads them again "
    "once they load")


def unreadable_next(ctx: Context, unreadable: list,
                    detail: dict | None = None
                    ) -> tuple[dict, str | None, str | None]:
    """`(restore, command, why)` for the `manifest kinds` row's files that
    do not load (#291): each file's case, the one command the row prints,
    and the sentence that goes with that command -- the row's `why`, apart
    from it and never a `   # ` tail on it (#277).

    A FILE A TOOL WROTE IS PUT BACK FROM GIT by `pin_restore`. That is the
    helper the `shape currency` row uses for the shape pin, so both rows
    print the same command for the same file. The shape pin goes first
    where it has a command, then each other file in the row's order. A row
    prints one command, and the next run names the next file. A copy or a
    neutral product pin, which a person may have edited, gets the
    read-only command `pin_restore` picks for it instead, a `git diff`
    that shows what breaks it, and nothing is put back. A pin a merge left
    conflicted where no side's pin reads gets no command (#752): where no
    other file has one, the row names none either, and says `pin_restore`'s
    `why`, as the `shape currency` row does, rather than send the reader to
    this doctor again, which would say the same.

    A FILE OF THE PROJECT'S OWN IS NOT, whatever it is called, and its case
    is `project`, with git not asked. `tool_written` reads what the root
    declares, not the name. The git-state choice does not fit it: each of
    the three commands discards somebody's edit -- the other side of their
    merge, their uncommitted work, their last commit -- and nothing in this
    standard says which bytes are right. Where no file has a command to
    name, the command is this doctor again, to run once a person has mended
    the file, and its `why` says that what the file should say is theirs to
    decide. #205's `manifest` row answers a `project.yaml` that does not
    load the same way: the gate that refuses it, and that `why`.

    WHAT THE SHAPE PIN'S MERGE LEAVES TO A PERSON IS SAID HERE TOO (#485).
    While the shape pin does not read, no row says what is a copy, so a
    copy conflicted beside it is not `tool_written`. The two sides of the
    merge do say, and `pin_restore`'s `why` gives each such copy to a
    person. That copy's case is `unmerged`, and not `project`, and
    `detail` gets the `left_for_a_person` the `shape currency` row's has,
    so both rows say the same of the same command. Where the pin taken
    here has a row for the copy, `unmerged` is the case it has once the
    pin reads. A copy under `contracts/` that only the other side's pin
    lists (#687) is `project` then, as the pin taken here has no row for
    it: `unmerged` is its case only while the pin is conflicted and the
    `why` names it. A copy the NEXT takes whole with the pin, proved tool
    output on both sides (#547), is `unmerged` too, and `detail` gets the
    `taken_with_the_pin` that row's has: the command overwrites it, and
    `project` would say git was not asked about a file the NEXT puts back.
    """
    restore: dict[str, str] = {}
    #: `(command, why)` for each file with a command, in the row's order.
    commands: dict[str, tuple[str, str | None]] = {}
    #: The `why` of each file a tool wrote that git was asked about and no
    #: line puts back: a merge where no side's pin reads (#752).
    stuck: dict[str, str] = {}
    held: dict = {}
    for rel in unreadable:
        if tool_written(ctx, rel):
            restore[rel], found, why = pin_restore(
                ctx, held if rel == SHAPE_PIN else None, pin=rel)
            if found:
                commands[rel] = (found, why)
            elif why:
                stuck[rel] = why
        else:
            restore[rel] = "project"
    left = held.get("left_for_a_person", [])
    taken = held.get("taken_with_the_pin", [])
    for rel in left + taken:
        if restore.get(rel) == "project":
            restore[rel] = "unmerged"
    if left and detail is not None:
        detail["left_for_a_person"] = left
    if taken and detail is not None:
        detail["taken_with_the_pin"] = taken
    command, why = (commands.get(SHAPE_PIN)
                    or next(iter(commands.values()), (None, None)))
    if command is None and stuck:
        why = stuck.get(SHAPE_PIN) or next(iter(stuck.values()))
    elif command is None:
        command = (f"{PYTHON} {quote_arg(ctx.shape / 'shape-doctor.py')} "
                   f"--root {quote_arg(ctx.root)}")
        why = UNREADABLE_BY_HAND
    return restore, command, why


def unreadable_pin_row(ctx: Context, exc: Refusal) -> Row:
    """The `shape currency` row for a root whose OWN pin does not read as one
    (#237): a FINDING, the refusal quoted whole, and the pin put back.

    A STATEMENT ABOUT THEIR REPOSITORY, NOT A FAILURE TO ASK. The pin is a
    file in the root: a merge conflict left in it, a byte that is not UTF-8,
    a `commit:` that is not 40 hex, a deleted file are what somebody did to
    THEIR tree, and no `git fetch` in the standard changes any of them. So
    this row carries no `environment`, which is the only thing that makes
    `verdict_for` answer CANNOT ANSWER, exit 3, before it looks at a single
    other row. The ladder then reaches the gates that are red -- `pins` and
    `manifest kinds` say the same about the same file where they can read it,
    and where neither can (a `digest_definition` this tool does not
    recompute, which `validate-pins.py` passes) this row is the only red one
    and the verdict is `INVALID (shape-currency)`.

    THE REFUSAL, WHOLE, AND NOT ITS REMEDIATION. `REFUSED <code>: <detail>`
    is what `read_pin` raised, in the spelling the project's own validator
    prints for the same file, and it names the line or the field at fault.
    Its `Remediation:` trailer is left off on purpose: `yaml-unparsable`
    carried `repo_shape`'s default one, about submodules and the lockstep
    invariant, which sent a person resolving a merge conflict to `git
    submodule update` (it carries none since #370). This is the wording
    #232's `unloaded_manifest_row` gives a `project.yaml` that does not
    load, so the two files are answered alike.

    THE NEXT PUTS BACK THE PIN A TOOL WROTE, NEVER A FETCH. `pin_restore`
    names the git command from the pin's own state, and run as printed it
    ends at `COMPLIANT` or at a row that reads the pin, but for what its
    `why` gives a person: a conflicted copy, manifest or README.md, or an index
    flag that hides the pin. Naming the tool that refused, `update-shape.py
    check`, was a dead end (review of PR #267): it reads the pin with the
    same `read_pin`, refuses it the same way, and its remediation is about
    submodules, adoption or a hand edit, none of which fits. That command
    stays only where git can name nothing, and its `why` says the rest is a
    person's call. Where a merge left the pin conflicted and no side's pin
    reads, the row names no command at all, and `pin_restore`'s `why` says
    the merge is a person's call (#752). Every sentence is the row's `why`,
    off the command's line, so a pasted line is one command in any shell
    (#277).
    """
    detail = {"error": exc.code, "pin": SHAPE_PIN,
              "refusal": {"code": exc.code, "detail": exc.detail}}
    restore, command, why = pin_restore(ctx, detail)
    detail["restore"] = restore
    if restore == "none":
        command = (f"{PYTHON} {quote_arg(ctx.shape / 'update-shape.py')} "
                   f"check --root {quote_arg(ctx.root)} --upstream "
                   f"{quote_arg(ctx.shape)}")
        why = ("no commit in this root holds a pin to put back, so whether "
               "it was ever scaffolded or adopted is for a person to decide")
    return Row("shape-currency", LABEL_SHAPE_CURRENCY, FINDING,
               f"the copies cannot be compared, because {SHAPE_PIN} does not "
               f"read as a pin: REFUSED {exc.code}: {exc.detail}",
               command, detail, why=why)


def unreadable_copy_row(ctx: Context, named: str, exc: OSError) -> Row:
    """The `shape currency` row for a pin or a copy, `named` from the root,
    that the operating system will not let this user read (#847).

    A STATEMENT ABOUT THEIR REPOSITORY, as `unreadable_pin_row`'s is: the
    file is in the root, and its mode, its owner or its directory's is what
    somebody did to THEIR tree, so no `environment`. NEVER `pin_restore`:
    the file is there, `git status` calls a file it cannot open changed
    (` M`), and the `git checkout HEAD --` it named would put HEAD's copy
    over whatever the file holds that no commit does. The line is
    `validate-pins.py`'s (`cannot_be_read`), the NEXT this doctor again and
    the `why` the gate's advice (`cannot_read_why`), as the `manifest kinds`
    row gives them for the same file."""
    line = cannot_be_read(named, exc)
    return Row("shape-currency", LABEL_SHAPE_CURRENCY, FINDING,
               f"the copies cannot be compared: {line}", doctor_line(ctx),
               {"path": named, "cannot_be_read": line},
               why=cannot_read_why([exc]))


def pin_refusal_row(ctx: Context, exc: Exception) -> Row:
    """The `shape currency` row for a shape pin `read_pin` would not read,
    `exc` being what it raised: a `Refusal`, or the `OSError` of a refused
    `stat` that `is_file()` raises up to Python 3.13 (#847).

    THE PIN IS ASKED AGAIN ONLY HERE, by `pin_read`, as `validate-pins.py`
    asks it: a `stat` or a read the operating system refused is
    `unreadable_copy_row`'s, the gate's line, whatever `read_pin` made of
    it (`update-pin-missing` from 3.14, `yaml-unreadable` quoting `[Errno
    13]`). Any other refusal is `unreadable_pin_row`'s, as it always was,
    and any other `OSError` is raised as it was. A pin that reads is read
    once, by `read_pin` (review of PR #860)."""
    refused = pin_read(ctx.root, SHAPE_PIN)[1]
    if refused is not None:
        return unreadable_copy_row(ctx, SHAPE_PIN, refused)
    if isinstance(exc, Refusal):
        return unreadable_pin_row(ctx, exc)
    raise exc


def refused_in_root(root: Path, exc: OSError) -> str | None:
    """Where `exc` is a read the operating system refused of a file inside
    `root`, that file's path from the root, POSIX; else None (#847): an
    `OSError` that says nothing is there, one that names no file, or one
    about a file elsewhere, the checkout of the standard's own among them."""
    if refused_read(exc) is None or not exc.filename:
        return None
    try:
        return Path(os.fsdecode(exc.filename)).relative_to(root).as_posix()
    except ValueError:
        return None


#: A line `rev-list --missing=print` writes for an object the clone lacks:
#: `?` and the object's id, SHA-1 or SHA-256.
MISSING_OBJECT = re.compile(rb"\?(?:[0-9a-f]{40}|[0-9a-f]{64})")


def objects_lacking(shape: Path, commit: str) -> int | None:
    """How many of the objects `commit` and its tree reach the checkout at
    `shape` lacks, asked without fetching (#683), or None where git cannot
    list them there.

    `git rev-list --objects --no-walk --missing=print` walks the commit's
    tree and prints `?<id>` for each object it does not hold, and
    `--missing=` turns git's lazy fetch off for its run: measured with git
    2.43, no fetch in a trace2 log, and the same objects missing after it.
    It is asked before any `ls-tree`, which fetches a tree a
    `--filter=tree:0` clone lacks.

    A COMMIT THE CLONE DOES NOT HOLD IS NONE, ON EVERY GIT (#754). Before
    git 2.45 `rev-list` refuses it, `bad object`, exit 128; from 2.45 on it
    takes a missing tip as missing too and prints it, `?<commit>`, exit 0
    (git's `rev-list` documentation, "If some tips passed to the traversal
    are missing"). Counted as one object there, the commit was "lacked"
    rather than absent, and `remotes_holding` asked `--contains` of a commit
    the clone does not hold, a read that fetches it. `partial_clone_row`
    counts None as lacking: `update-shape.py`'s first read of that commit,
    its `rev-parse`, fetches it (measured with git 2.43).

    A FLOOR, NOT A COUNT, WHERE A TREE IS MISSING (#754). `rev-list` cannot
    walk into a tree it does not hold, so a `--filter=tree:0` clone's
    missing root tree is one `?<id>` with everything under it uncounted,
    and the id alone does not say it was a tree. So the row says "at
    least" of every count.
    """
    listed = git_answer(["rev-list", "--objects", "--no-walk",
                         "--missing=print", commit], shape, binary=True)
    lines = (listed or b"").split(b"\n")
    if listed is None or b"?" + commit.lower().encode("ascii") in lines:
        return None
    return sum(1 for line in lines if MISSING_OBJECT.fullmatch(line))


#: `partial_clone_row`'s `error` (#683).
PARTIAL_CLONE_LACKS = "shape-doctor-partial-clone"


def partial_clone_row(ctx: Context, pinned: str) -> Row | None:
    """The `shape currency` row for a checkout of the standard that is a
    partial clone and lacks an object the comparison reads, or None where
    it is no partial clone or lacks none of them (#683).

    THE DOCTOR FETCHED, AND OFFLINE IT CALLED UNEDITED COPIES `both`.
    `update-shape.py`'s comparison reads each copy's blob at the pinned
    commit and at this standard's, and a `--filter` clone fetches a blob it
    lacks on that read. Measured on #683 with git 2.43,
    a `--filter=blob:none` clone made five lazy fetches for the five copies
    the standard had changed since the pin; with its remote out of reach
    the reads failed, `Upstream.blob` read each failure as "no such file at
    the pinned commit", and the row said `DRIFTED (5 both)` of copies
    nobody edited. So before anything reads this checkout, where
    `partial_clone` holds, `objects_lacking` asks of the pinned commit and
    of HEAD whether every object their trees reach is here.

    THE WHOLE TREE, NOT THE COPIES' PATHS. `--missing=print` names a missing
    object by its id alone, and which path it sits at is read from the tree
    that holds it, which a `--filter=tree:0` clone lacks too; and the paths
    the comparison reads are `prepare`'s, whose second definition here
    would be one to drift. So a partial clone pinned behind its HEAD, where
    the clone lacks what its checkout never needed, is this row even where
    no copy changed. That is the cost of never fetching, and the NEXT
    below ends it. A partial clone whose pin names its HEAD lacks nothing
    and answers as a full clone does.

    CANNOT ANSWER, as the row for a checkout short of the pin's commit is:
    `environment`, exit 3, nothing said about the repository. THE NEXT IS
    THAT ROW'S, MADE TO FIT: there, the fetch a person runs to put in this
    checkout what it lacks. Here `fetch --all` would put in no blob, since
    a promisor remote's fetch keeps its `partialclonefilter`, so the NEXT
    is `fetch --refetch --no-filter`: measured with git 2.43, it leaves the
    clone lacking nothing at what it fetches and its config as it was, and
    the doctor run again answers. It is the person's fetch, never this
    doctor's, and the `why` names the other way, a full clone of the
    standard, as the precedent's names a clone that has the commit.
    `--refetch` needs git 2.36 or later, and the `why` says so.

    FROM THE REMOTE THAT HOLDS IT, AND OF THE COMMITS IT LACKS (#754). The
    NEXT fetched the first promisor remote whole, and looped where that
    remote's branches do not hold the pinned commit: with two promisor
    remotes and the commit on the second's, and in a `--single-branch`
    clone whose pin is on another branch, which then still does not hold
    it. So it names each commit lacked by id, from the remote
    `partial_clone_fetch` picks, and the `why` says where each commit is.
    """
    remotes = promisor_remotes(ctx.shape)
    if not remotes:
        return None
    standard = head_of(ctx.shape)
    lacking = {commit: objects_lacking(ctx.shape, commit)
               for commit in dict.fromkeys((pinned, standard)) if commit}
    lacking = {commit: count for commit, count in lacking.items()
               if count != 0}
    if not lacking:
        return None
    remote, commits, whence = partial_clone_fetch(ctx.shape, remotes,
                                                  pinned, lacking)
    return Row("shape-currency", LABEL_SHAPE_CURRENCY, FINDING,
               "the copies cannot be compared without fetching: this "
               "checkout of the standard is a partial clone, and "
               + lacking_said(lacking, pinned),
               refetch_command(ctx.shape, remote, commits),
               {"error": PARTIAL_CLONE_LACKS, "environment": True,
                "pinned": pinned, "standard": standard, "remote": remote,
                "lacking": lacking},
               why="this checkout of the standard is a partial clone, and "
                   "a read of an object it lacks fetches it from a promisor "
                   "remote, which this doctor never does; " + whence
                   + ", or run it from a full clone of the standard")


def lacked_commit(commit: str, pinned: str) -> str:
    """How `partial_clone_row` names a commit the clone lacks objects at:
    the pinned commit or this standard's, by its id's first twelve
    digits."""
    if commit == pinned:
        return f"the pinned commit {commit[:12]}"
    return f"this standard's commit {commit[:12]}"


def lacking_said(lacking: dict, pinned: str) -> str:
    """The reason's account of `lacking`: each commit the clone does not
    hold at all, and how many objects at least it lacks at each it does
    hold."""
    said = []
    for commit, count in lacking.items():
        if count is None:
            said.append(f"it does not hold {lacked_commit(commit, pinned)} "
                        "at all")
        else:
            said.append(f"it lacks at least {count} object"
                        f"{'' if count == 1 else 's'} at "
                        f"{lacked_commit(commit, pinned)}")
    return " and ".join(said)


def refetch_command(shape: Path, remote: str, commits: list) -> str:
    """The fetch that puts in `shape` every object at each of `commits`,
    from `remote`, whatever its `partialclonefilter` (#683, #754)."""
    return (f"git -C {quote_arg(shape)} fetch --refetch --no-filter "
            f"{quote_arg(remote)} " + " ".join(commits))


def partial_clone_fetch(shape: Path, remotes: list, pinned: str,
                        lacking: dict) -> tuple:
    """`(remote, commits, whence)` for a partial clone at `shape` that
    lacks objects at `lacking`'s commits: the promisor remote the NEXT
    fetches from, the commits it names, and the `why`'s account of where
    each commit is and what to run (#754).

    ONLY THE COMMITS THE REMOTE IS KNOWN TO HOLD, WHERE ONE IS. A fetch by
    id from a remote that does not have one of the ids fails whole, exit
    128, `not our ref`, and puts in nothing. Measured by RV-f on #773: in
    a sparse clone whose HEAD lacked objects on `origin`'s branches alone,
    with the pinned commit on `second`'s alone, the NEXT fetched both from
    `origin`, git refused it, and the row came back the same, its `why`
    saying no branch held them. So where some remote's branches hold a
    lacking commit, the NEXT fetches from the first remote whose branches
    hold every such commit, else from the first that holds the pinned
    commit, and names only the commits that remote's branches hold. The
    doctor run again names the rest: two runs at most, for two commits.

    THE FIRST PROMISOR REMOTE, AND EVERY COMMIT, WHERE NONE IS. A commit
    the clone does not hold, or holds only on a tag or on no ref, is on no
    branch it tracks, and no read that fetches nothing says which remote
    has it. The NEXT asks the first promisor remote, the one git's own
    lazy fetch asks first, and the `why` spells out the same fetch from
    each other promisor remote, so that each is a line to paste.
    """
    holding = {commit: remotes_holding(shape, remotes, commit)
               for commit, count in lacking.items() if count is not None}
    known = {commit: names for commit, names in holding.items() if names}
    remote = fetch_source(remotes, pinned, known)
    commits = [commit for commit, names in known.items()
               if remote in names] or list(lacking)
    said = [where_lacked(commit, holding.get(commit), pinned)
            for commit in lacking]
    said.append(fetch_said(shape, remotes, remote, commits,
                           fetched_named(commits, lacking, pinned),
                           bool(known)))
    return (remote, commits,
            "; ".join(said) + then_said(commits, lacking, pinned))


def fetch_source(remotes: list, pinned: str, known: dict) -> str:
    """The promisor remote the NEXT fetches from, of `known`, each lacking
    commit some remote's branches hold and the remotes that hold it: the
    first remote that holds every one -- the first promisor remote, where
    `known` is empty -- else the first that holds the pinned commit
    (#754)."""
    for name in remotes:
        if all(name in names for names in known.values()):
            return name
    return (known.get(pinned) or next(iter(known.values())))[0]


def where_lacked(commit: str, holders: list | None, pinned: str) -> str:
    """The `why`'s word on where `commit` is: not in this clone at all,
    where `holders` is None, on no branch this clone tracks, where it is
    empty, or on the branches of each of `holders` (#754)."""
    named = lacked_commit(commit, pinned)
    if holders is None:
        return f"{named} is not in this clone at all"
    if not holders:
        return f"no branch this clone tracks holds {named}"
    return (f"{named} is on "
            + " and ".join(f"{name}'s" for name in holders) + " branches")


def fetch_said(shape: Path, remotes: list, remote: str, commits: list,
               them: str, known: bool) -> str:
    """The `why`'s word on the fetch: every object at `them` from
    `remote`, whose branches hold them, or, where none is `known` to, by
    id from `remote` and else from each other promisor remote, that fetch
    spelled out as a line to paste (#754)."""
    if known:
        return f"so fetch every object at {them} from {remote}"
    said = f"so fetch {them} by id from {remote}"
    others = [f"from {name}: `{refetch_command(shape, name, commits)}`"
              for name in remotes if name != remote]
    if others:
        said += (f", or, where {remote} does not have {them}, "
                 + ", or ".join(others))
    return said


def fetched_named(commits: list, lacking: dict, pinned: str) -> str:
    """How the `why` names the commits the NEXT fetches: `it` or `them`,
    where they are every commit `lacking` holds, else each by name
    (#754)."""
    if len(commits) < len(lacking):
        return " and ".join(lacked_commit(commit, pinned)
                            for commit in commits)
    return "it" if len(commits) == 1 else "them"


def then_said(commits: list, lacking: dict, pinned: str) -> str:
    """The end of the `why`'s word on the fetch: the git it needs, the
    doctor run again, and the commits of `lacking` that run names a fetch
    for, those the NEXT leaves out (#754)."""
    said = " (--refetch needs git 2.36 or later), then run the doctor again"
    rest = [lacked_commit(commit, pinned) for commit in lacking
            if commit not in commits]
    if rest:
        said += ", which names the fetch for " + " and ".join(rest)
    return said


def remotes_holding(shape: Path, remotes: list, commit: str) -> list:
    """Those of `remotes` whose branches here -- their tracking refs,
    `refs/remotes/<name>/` -- hold `commit`, in `remotes`' order (#754).

    `for-each-ref --contains` reads commits alone, and a `--filter` clone
    holds every commit a fetch brought, so it fetches nothing: measured with
    git 2.43, no fetch in a trace2 log. It is never asked of a commit the
    clone does not hold, which no branch here can hold and whose read would
    fetch it: `partial_clone_fetch` asks only of the commits
    `objects_lacking` could list.
    """
    return [name for name in remotes
            if git_answer(["for-each-ref", "--count=1",
                           "--format=%(refname)", f"--contains={commit}",
                           f"refs/remotes/{name}/"], shape)]


def refetch_of(git_c: str, remote: str) -> str:
    """The fetch of every object on `remote`'s branches into the root
    `git_c` names, whatever its `partialclonefilter` (#787)."""
    return f"{git_c} fetch --refetch --no-filter {quote_arg(remote)}"


def partial_history_why(git_c: str, what: str, remotes: list) -> str:
    """`pin_restore`'s `why` for `partial` (#787): the root's partial clone
    lacks the history of its `what`, the NEXT fetches the first of
    `remotes`, and the same fetch from each other one is spelled out.

    HISTORY, HEAD'S INCLUDED, AND NOT "THE COMMIT THAT BROKE IT" (RV-f on
    #791). Where HEAD was moved without a checkout (`reset --soft`), the
    pin HEAD holds is a blob the clone lacks too, and the doctor run after
    the fetch answers `uncommitted`, which no commit broke.

    EVERY PROMISOR REMOTE, EACH A LINE TO PASTE. The NEXT fetches the first
    one's branches, the one git's own lazy fetch asks first. Where the
    history lacked is on another remote's alone, or on a branch forced
    away from the first, that fetch puts in nothing it needs and the row
    comes back the same, so the `why` names the fetch from each other one.
    """
    first, *others = remotes
    said = (f"this root is a partial clone, and the {what}'s history, "
            "HEAD's included, is not all in this clone: git fetches what a "
            "partial clone lacks on a read, which this doctor never does, "
            f"so what puts the {what} back cannot be read here. This "
            f"fetches every object on {first}'s branches (--refetch needs "
            "git 2.36 or later)")
    if others:
        said += (f"; where {first}'s branches do not hold it, the same "
                 "from " + ", or from ".join(
                     f"{name}: `{refetch_of(git_c, name)}`"
                     for name in others))
    return (said + "; then run this doctor again, which names what puts "
            f"the {what} back")


def history_left_out(root: Path, pin: str) -> list:
    """The promisor remotes of `root`, in the order git asks them, where
    `root` is a partial clone that lacks an object `pin_restore`'s walk of
    `pin`'s history reads, asked without fetching; empty where it lacks
    none, or is no partial clone (#787).

    THE WALK'S READS FAIL THERE, AND THE DOCTOR FETCHED THEM BEFORE.
    Measured on #787 with git 2.43: a `--filter=blob:none` clone of a root
    whose HEAD commit broke its pin made one lazy fetch, of the pin before
    it, and a `--filter=tree:0` one two. With `GIT_NO_LAZY_FETCH` set
    (`lazy_fetch_off`) each read fails instead, and the walk, which reads a
    failure as "no pin there", said "none": no commit in this root holds a
    pin to put back, which is not so.

    `rev-list --objects --missing=print` over the commits that touched
    `pin`, one more than the walk reads, lists the pin at each and the
    trees down to it, and prints `?<id>` for each the clone does not hold,
    without fetching (`objects_lacking` says why). Where the clone lacks a
    tree, as a `tree:0` one does, it cannot tell which commits touched the
    pin and fails, as the walk's own `rev-list` does: that is lacking too.
    A root with no HEAD has no history to walk, and is not asked.
    """
    remotes = promisor_remotes(root)
    if not remotes or head_of(root) is None:
        return []
    listed = git_answer(["rev-list", "--objects", "--missing=print", "-n",
                         str(PIN_HISTORY_DEPTH + 1), "HEAD", "--", pin],
                        root, binary=True)
    if listed is not None and not any(
            MISSING_OBJECT.fullmatch(line) for line in listed.split(b"\n")):
        return []
    return remotes


def check_shape_currency(ctx: Context) -> Row:
    """`update-shape.py check`, summarised, against THIS checkout.

    NO NETWORK AND NO CLONE. `update-shape.py` reads a local path as an
    upstream in place -- the same thing that makes its own tests offline -- so
    the shape this project is compared against is the checkout this file sits
    in, at its HEAD. What that costs is honesty about which standard answered,
    which is why both commits are in the row.

    TWO KINDS OF REFUSAL, TOLD APART BY WHICH READ RAISED THEM (#237).
    `prepare` asks two things: what does the ROOT's own pin say, and can THIS
    checkout of the standard answer about the commit it names. A refusal from
    the first is about their repository and is `unreadable_pin_row`'s; one
    from the second is this checkout failing to ask and stays CANNOT ANSWER.
    The pin is read here first, on its own, with `read_pin` -- the function
    `prepare` calls for it -- so the split is made by what was being read and
    not by a list of refusal codes or a match on their text, and a refusal
    `read_pin` or `open_upstream` learns later lands on the right side
    without this file being told.

    A PARTIAL CLONE IS ASKED BEFORE ANYTHING READS IT (#683). Once the pin
    reads, and before `prepare` opens this checkout, `partial_clone_row`
    asks, without fetching, whether a partial clone holds every object the
    comparison reads, and where it does not this row is CANNOT ANSWER with
    a fetch of its own for a person to run. A read that fails anyway --
    a clone that lacks objects and has no promisor remote, a damaged one --
    is `update-upstream-unreadable` from `prepare`, CANNOT ANSWER too, and
    never a copy called `both`.

    A PIN, OR A COPY, THIS USER CANNOT READ IS NAMED (#847), as
    `validate-pins.py` names it: `the copies cannot be compared:
    contracts/shape-pin.yaml: cannot be read (Permission denied)`, a
    FINDING about the repository, with this doctor again as its NEXT and the
    gate's advice for the cause as its `why` (`unreadable_copy_row`), the
    NEXT and `why` the `manifest kinds` row gives the same file. A pin at
    mode 000 was `unreadable_pin_row`'s, whose `pin_restore` read it as
    changed and named `git checkout HEAD --` on it; a `contracts/` this user
    cannot search, or a copy at mode 000, ended the row in `could not be
    run: [Errno 13]`. Where `read_pin` will not read the pin, `pin_read`
    asks why (`pin_refusal_row`): `read_pin`'s `is_file()` raised the
    refused `stat` up to Python 3.13 and, from 3.14, calls the pin missing.
    A copy is asked by `prepare`, and only a refused read of a file inside
    the root is the repository's: any other `OSError` is raised as it was.
    """
    us = ctx.update_shape()
    # A PIN OR MANIFEST KEPT AS A LINK IS ASKED ABOUT FIRST, before anything
    # reads the pin or opens this checkout as the upstream (#286): see
    # `linked_record_row`.
    linked = linked_record_row(ctx, us)
    if linked is not None:
        return linked

    args = argparse.Namespace(root=str(ctx.root), upstream=str(ctx.shape),
                              at=None)
    try:
        pin, _rows = us.read_pin(ctx.root)
    except (Refusal, OSError) as exc:
        return pin_refusal_row(ctx, exc)
    partial = partial_clone_row(ctx, str(pin["commit"]).lower())
    if partial is not None:
        return partial
    try:
        _root, _pin, rows, additions, upstream, pinned, target, _kind = \
            us.prepare(args)
    except Refusal as exc:
        if exc.code == us.UPSTREAM_UNREADABLE:
            # A READ THAT FAILED, NOT A COMMIT THAT IS NOT HERE (#683), so
            # the `fetch --all` below would bring nothing to read it.
            return Row("shape-currency", LABEL_SHAPE_CURRENCY, FINDING,
                       f"the copies cannot be compared: {exc.detail}", None,
                       {"error": exc.code, "environment": True},
                       why="git could not read what this checkout of the "
                           "standard holds at that commit, so no copy was "
                           "compared and none is called both over it; run "
                           "the doctor from a clone of the standard that "
                           "git reads whole")
        # NOT A VERDICT ABOUT THE REPOSITORY. A pin naming a commit THIS
        # checkout does not carry -- a fork, a branch pin, a clone made
        # before the commit landed -- is this standard being unable to
        # answer, which is the documented meaning of exit 3. Labelling it
        # INVALID would tell somebody their repository is wrong on the
        # evidence that our copy of the standard is short a commit.
        return Row("shape-currency", LABEL_SHAPE_CURRENCY, FINDING,
                   f"the copies cannot be compared: {exc.detail}",
                   f"git -C {quote_arg(ctx.shape)} fetch --all",
                   {"error": exc.code, "environment": True},
                   why="this checkout of the standard does not carry the "
                       "commit the pin names; fetch it, or run the doctor "
                       "from a clone that has it")
    except OSError as exc:
        named = refused_in_root(ctx.root, exc)
        if named is None:
            raise
        return unreadable_copy_row(ctx, named, exc)
    try:
        added = [add for add in additions if not add.present]
        reported = list(rows) + added
        counts = us.counted(reported)
        # EVERY STATE `check` COUNTS IS COUNTED WHERE THERE IS ONE (#502,
        # review of PR #512; #676). The five states every root has a word
        # for are always printed; any other state of `update-shape.py`'s
        # `ORDER` follows them, in that order, where its count is not zero.
        # Without them the counts fell one short of the rows for each such
        # row -- `merged-away` until #502, `copy-is-link`, `copy-missing`,
        # `upstream-removed`, `unmapped` and `already-at-target` until #676
        # -- and the path `named` below stood under no count. Zero is left
        # unsaid, so a root with none of them reads as it always did.
        always = (us.UNCHANGED, us.UPSTREAM_CHANGED, us.LOCALLY_MODIFIED,
                  us.BOTH, us.UPSTREAM_ADDED)
        states = always + tuple(state for state in us.ORDER
                                if state not in always and counts.get(state))
        summary = " / ".join(f"{counts.get(state, 0)} {state}"
                             for state in states)
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
                  # A MERGED-AWAY ROW IS DRIFT TOO (#502): the pin names a
                  # copy the tree does not hold, and `apply` drops the row.
                  "drifted": bool(counts.get(us.LOCALLY_MODIFIED)
                                  or counts.get(us.BOTH)
                                  or counts.get(us.MERGED_AWAY)
                                  or conflicts)}
        where = f"pinned {pinned[:12]}, this standard {target[:12]}"
        note = readme_shape_note(ctx, us, upstream.repository, pinned, detail)
        moved = [row for row in reported if row.state != us.UNCHANGED]
        if not moved and pinned == target:
            # `NOTE` RATHER THAN `OK` WHEN THE README DISAGREES, and `note` is
            # the whole of what it is: `verdict_for` steps over a note row, so
            # a prose line naming an old commit never fails a repository whose
            # every pin is current. Same rule as `leg shape files`, which
            # argues it at length; this is the second row to need it.
            return Row("shape-currency", LABEL_SHAPE_CURRENCY,
                       NOTE if note else OK,
                       f"the pin names this standard's commit; {summary} "
                       f"({where}){note}", None, detail)
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
            # AND WHAT ELSE IT WOULD MOVE. `apply` rewrites the README's
            # `Shape:` line in the pin's own commit, so "the pin alone" both
            # described a commit that could have a second file in it and
            # contradicted the `note` printed right after it (#158).
            moving = what_a_re_pin_would_move(ctx, us, upstream.repository,
                                              target)
            return Row("shape-currency", LABEL_SHAPE_CURRENCY, FINDING,
                       "no copied file differs, but the pin names an older "
                       f"commit, so `apply` would move {moving}; "
                       f"{summary} ({where}){note}",
                       f"{PYTHON} "
                       f"{quote_arg(ctx.shape / 'update-shape.py')} check "
                       f"--root {quote_arg(ctx.root)} --upstream "
                       f"{quote_arg(ctx.shape)}", detail,
                       why=f"then apply --at {quote_arg(target)} --yes "
                           "--branch "
                           f"{quote_arg('shape/update-' + target[:12])}"
                           f"{lane_trailer_command()}")
        named = ", ".join(row.path for row in moved[:4])
        if len(moved) > 4:
            named += f", and {len(moved) - 4} more"
        # The `check` is the NEXT, and the `apply` that follows the human's
        # yes is the row's `why`, the lane's trailer included (#111): it is
        # the second of two acts, never pasted with the first, and the `   # `
        # that joined them is what #277 removed.
        #
        # NO `--accept-local` ON THAT `apply` (#501). It carried one for
        # every `locally-modified` row, and pasted, it re-pinned the
        # project's edit as the standard: `update-local-drift`, the refusal
        # that asks the human whether the project keeps it, never fired.
        # Brett Heap ruled on 2026-10-13, "Stop pre-filling it", so the
        # `apply` meets that refusal, whose remediation names the three
        # exits, and `update-shape.py check` names the flag in the row's
        # detail. `both` was never pre-filled: its hand merge comes first.
        return Row("shape-currency", LABEL_SHAPE_CURRENCY, FINDING,
                   f"{summary} ({where}): {named}{note}",
                   f"{PYTHON} "
                   f"{quote_arg(ctx.shape / 'update-shape.py')} check --root "
                   f"{quote_arg(ctx.root)} --upstream {quote_arg(ctx.shape)}",
                   detail,
                   why=f"then apply --at {quote_arg(target)} --yes "
                       f"--branch {quote_arg('shape/update-' + target[:12])}"
                       f"{lane_trailer_command()}")
    finally:
        upstream.close()


def linked_record_row(ctx: Context, us) -> Row | None:
    """The `shape currency` row for a root that keeps its pin or its
    manifest as a symlink, or under one, or None when it keeps neither
    (#286).

    A STATEMENT ABOUT THEIR REPOSITORY, NOT A FAILURE TO ASK. `update-shape.py
    apply` rewrites `contracts/shape-pin.yaml` and the manifest where they
    stand, so it refuses a root that keeps either as a link
    (`update-rewrite-symlink`): the re-pin would land at the link's end,
    outside the root if that is where it points, and git, which holds the
    link, would commit none of it. That is what the root's own tree holds,
    and no `git fetch` in the standard changes it. Filed with `prepare`'s
    other refusals, it read `CANNOT ANSWER`, exit 3, with a fetch for its
    NEXT. So this row carries no `environment`, which is the only thing that
    makes `verdict_for` answer CANNOT ANSWER; the ladder goes on, and where
    every gate reads through the link and is green, the verdict is `INVALID
    (shape-currency)`.

    ASKED FIRST, AND BY THE SAME FUNCTION. `linked_record` is the question
    `read_pin` and `prepare` ask before they refuse, for the KIND of root
    `prepare` would see, so this row and `update-shape.py` cannot disagree
    about which record is linked. Asked before anything reads the pin, so a
    linked pin is answered as a link, whatever else reads it next.

    THE REFUSAL, QUOTED AS `update-shape.py` PRINTS IT, and its remedy for
    the `why`: replace the link with what it points at, commit that, run
    the doctor again. Said, not spelled as a command: what the link points
    at may be shared with other trees, and removing a link -- a junction
    above all -- is a person's call. So the row has no NEXT, which is one
    pasteable command or nothing (#548); the sentence was the NEXT once.
    """
    linked = us.linked_record(ctx.root, us.root_kind(ctx.root))
    if linked is None:
        return None
    record, (name, points) = linked
    refusal = us.rewrite_link_refusal([linked])
    return Row("shape-currency", LABEL_SHAPE_CURRENCY, FINDING,
               "update-shape.py cannot re-pin this root: "
               f"REFUSED {refusal.code}: {refusal.detail}", None,
               {"error": refusal.code, "path": record, "link": name,
                "points": points},
               why=f"replace {name} with the file or directory it points "
                   "at, or with what it replaced where it points at "
                   "nothing, commit that, and run this doctor again -- "
                   f"update-shape.py never rewrites {record} through a link")


def head_of(path: Path) -> str | None:
    try:
        return git_out(["rev-parse", "HEAD"], cwd=path).lower()
    except (Refusal, OSError):
        return None


def pin_commit(root: Path, relative: str) -> str | None:
    """The 40-hex `commit:` of the pin at `relative`, lowercased, or None.

    Read by `pin_read`, as `validate-pins.py` reads a pin (#847): a pin whose
    `stat` or read the operating system refused is None here as one that is
    not there is, and `check_legs` asks `pin_read` why."""
    pin, _refused = pin_read(root, relative)
    if not isinstance(pin, dict):
        return None
    commit = str(pin.get("commit") or "").lower()
    return commit if COMMIT_RE.match(commit) else None


def own_bootstrap(root: Path, make_target: bool = False) -> bool:
    """Can the root's own `scripts/bootstrap.py` RUN? It imports `repo_shape`
    from beside itself, so it and `scripts/repo_shape.py` must both be there:
    a root without either has no bootstrap a NEXT may name (#276).

    `make_target` also asks for the Makefile target `make bootstrap` runs, for
    the one sentence that sends a reader there. ONE DEFINITION, because the
    `legs` and `members` rows each asked it in their own words.

    A COPY THIS USER CANNOT REACH CANNOT RUN EITHER (#430), and that is the
    answer on every Python: up to 3.13 `is_file()` raised the refused `stat`
    out of the row, and from 3.14 it answered False. This chooses only which
    line a row prints, and the `manifest` and `pins` rows name a `scripts/`
    this user cannot search.
    """
    scripts = root / "scripts"
    try:
        if not all(is_a(scripts / name, stat.S_ISREG)
                   for name in ("bootstrap.py", "repo_shape.py")):
            return False
    except OSError:
        return False
    if not make_target:
        return True
    try:
        makefile = (root / "Makefile").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return re.search(r"(?m)^bootstrap\s*:", makefile) is not None


def gate_line(ctx: Context, gate: tuple) -> tuple[Path, bool, str | None]:
    """`(the copy of `gate` a row names, whether it is the root's own, the
    line that runs it on the root)`: the line is None where neither copy is
    readable, or where no `PYTHONPATH` can name the standard's template copy
    (#278), because a line that cannot run is not printed (#276).

    ONE DEFINITION for the rows that hand a reader the lockstep gate:
    `lockstep_next`, for the `legs` and `members` rows, and the `agent-files`
    row's confirm clause (#776). Both asked `validator_for` and
    `pythonpath_unnamable` in the same words.

    No line either where the root's own copy is one this user cannot reach
    (#430): it runs nowhere until it is readable, the gate's own row names
    it, and the template is not its stand-in (`validator_for`).
    """
    try:
        used, _, own_copy = validator_for(ctx, *gate)
    except OSError:
        return ctx.root / gate[0], True, None
    if (not used.is_file()
            or pythonpath_unnamable(ctx.shape, own_copy) is not None):
        return used, own_copy, None
    return used, own_copy, validator_command(
        ctx.shape, used, own_copy, ["--root", str(ctx.root)])


def lockstep_next(ctx: Context, gate: tuple, noun: str) -> tuple:
    """`(the line, why it is the line)` for what NO checkout cures: the
    lockstep gate, built the way the `pins` and `family` rows build their
    own (`PINS_GATE`, `FAMILY_GATE` and the same `--root` argument), so the
    template's line carries the `PYTHONPATH` it needs (#238). `(None, None)`
    when neither copy is readable: that is a standard with a hole in it, the
    gate's own row says so in the same report, and a command that cannot run
    is the defect #276 is about. `(None, None)` too when no `PYTHONPATH` can
    name the template's `scripts/` (#278): the gate's own row is then an
    environment row that says why, and a line that splits when pasted is the
    same defect.

    The `legs` and `members` rows say the same thing about a leg and about a
    member, so the sentence is written here once -- and it is the row's
    `why`, apart from the line, never a `   # ` tail on it (#277).

    A GATE THAT CANNOT IMPORT `repo_shape` IS NOT THE LINE (#750). The root's
    own copy, beside a lost `scripts/repo_shape.py`, dies on that import and
    exits 1, the code it uses for findings, so that line cannot do what the
    sentence says of it, and the `pins` and `family` rows beside it already
    print the cure (#697). So the line is theirs, from
    `lost_repo_shape_cure`: the one command that puts the file back, or none
    where HEAD no longer holds it. Its `why` says to run the gate once the
    file is back, and the sentence above follows it.
    """
    used, own_copy, command = gate_line(ctx, gate)
    if command is None:
        return None, None
    said = (f"no submodule update cures a {noun} whose gitlink "
            "or pin is missing or disagrees, or a mount git cannot "
            f"read a HEAD in. {used.name} prints what it finds and "
            "names the repair where it has one")
    if own_copy and not imports_repo_shape(ctx.shape, used, own_copy):
        cure, why = lost_repo_shape_cure(
            ctx, gate[0], repo_shape_for(ctx.shape, used, own_copy), command,
            again=False)
        return cure, f"{why}. {said[:1].upper()}{said[1:]}"
    return command, said


def gitmodules_entry(root: Path, rel: str) -> tuple[str | None, str | None]:
    """`(name, url)` of the `.gitmodules` section whose `path` is `rel`, read
    as `git submodule update` reads it: `(None, None)` when no section gives
    that path, and `(name, None)` when the one that does gives no url (#414).

    WHY THE GIT LINE ASKS IT FIRST. The line runs `submodule update --init`,
    and `--init` needs a url for every path it names: with none, git prints
    `No url found for submodule path ... in .gitmodules` and exits 128.
    Measured for an empty mount whose section is gone and for one that lost
    only its `url` key, and for a populated mount whose section is gone: a
    mount git already holds is asked for its url all the same. A NEXT that
    exits 128 is the defect #276 was about. A section that gives the path
    and no url is not the end of the question, though: `--init` reads the
    url the root's own config already holds first (`configured_url`), and
    `submodule_url` asks that before it calls a mount url-less.

    READ WHERE GIT READS IT, WHICH IS NOT ALWAYS THE FILE. git reads the
    working tree's `.gitmodules` when there is one, else the copy in the
    index, else the one in HEAD. So a root whose `.gitmodules` was deleted
    from the working tree alone still updates: measured, the line exits 0
    there. `git config -f .gitmodules` by itself would call every mount of
    that root url-less and withhold a line that works.

    AND ONLY THAT ONE COPY: the first that EXISTS, as `rev-parse --verify`
    finds it, which is how git's `config_from_gitmodules` chooses (#668).
    A copy with no section for `rel`, or one git cannot parse before it, is
    no url, and git does not look further: measured, over an index copy of
    either kind beside a HEAD copy that gives the url, `submodule init` exits
    128, `No url found`. Reading the next copy wherever one would not list
    named a url there, and a line that exits 128.

    The copy is read by `gitmodules_listing`, the one reading
    `submodule_config` makes too, and `section_url` picks the section out of
    it. A copy from the index or HEAD is read up to its first bad line, as
    git reads it, and a section before that line still gives its url
    (`submodule_keys`, #733): git refuses only the working tree's file
    whole.

    NO COPY AT ALL WHILE `.gitmodules` IS UNMERGED (#733): git reads none
    then (`is_gitmodules_unmerged`), so `submodule init` says `No url found`,
    exit 128, measured with the conflict resolved in the working tree and
    with that copy deleted, where this named the resolved url or HEAD's.
    """
    if git_answer(["ls-files", "-u", "--", ".gitmodules"], root):
        return None, None
    working_tree = os.path.lexists(root / ".gitmodules")
    if working_tree:
        source = ["--file", ".gitmodules"]
    else:
        found = next((copy for copy in (":.gitmodules", "HEAD:.gitmodules")
                      if git_answer(["rev-parse", "-q", "--verify", copy],
                                    root) is not None), None)
        if found is None:
            return None, None
        source = ["--blob", found]
    listing = gitmodules_listing(root, source, partial=not working_tree)
    if listing is None:
        # The working tree's copy, and one git cannot parse: git dies there.
        return None, None
    return section_url(listing, rel, working_tree)


def section_url(listing: str, rel: str, working_tree: bool = True
                ) -> tuple[str | None, str | None]:
    """`(name, url)` of the section whose `path` is `rel`, read out of one
    `gitmodules_listing`, which is what `gitmodules_entry` asks git for:
    `(None, None)` when no section gives that path, and `(name, None)` when
    the one that does gives no url (#414).

    PURE, so the reading is tested apart from the question of where git
    found the file. Only a section's `path` and `url` keys count
    (`submodule_keys`): `--list` gives every key the file holds, and the
    `path` of a section that is not a submodule's names no mount (#668).

    THE LAST VALUE GIVEN WINS, for a path two sections give and for a key a
    section gives twice, because git reads `.gitmodules` with each later
    value overwriting the one before. An empty `url =` is no url, and a file
    git refuses whole gives no section (#733). `working_tree` says which
    copy the listing is of, as `submodule_keys` reads it.
    """
    keys = submodule_keys(listing, working_tree)
    if keys is None:
        return None, None
    named = None
    urls: dict[str, str] = {}
    for name, field, value in keys:
        if field == "path" and value == rel:
            named = name
        elif field == "url":
            urls[name] = value
    if named is None:
        return None, None
    return named, urls.get(named) or None


#: A `.gitmodules` section name git ignores, every key of it
#: (`check_submodule_name`): `..` as a component, between `/` or `\`. An
#: empty name is ignored too. `a..b` is a name like any other.
DOTDOT_COMPONENT = re.compile(r"(?:^|[/\\])\.\.(?:[/\\]|$)")

#: The keys of a section that git refuses the WHOLE file over when one is
#: given with no value at all, `[submodule "q"]` then a bare `url`
#: (`config_error_nonbool`). Measured on git 2.43: `bad config line N`,
#: exit 128, and `branch` crashes it (exit 139). A bare `shallow`,
#: `fetchRecurseSubmodules` or unknown key is read as true.
VALUED_KEYS = ("path", "url", "ignore", "update", "branch")

#: A boolean as git reads one where a section gives it (`git_config_bool`):
#: one of these words in any case, or an integer `GIT_INT` reads.
GIT_BOOL_WORDS = ("", "true", "yes", "on", "false", "no", "off")

#: An integer as `strtoimax` reads one, base 0, after the white space it
#: skips: a sign, then decimal, `0x` hex or `0` octal digits, then a unit,
#: `k`, `m` or `g`, each a power of 1024 (`git_parse_int`). It must fit an
#: `int`.
GIT_INT = re.compile(r"([+-]?)(0[xX][0-9a-fA-F]+|0[0-7]*|[1-9][0-9]*)"
                     r"([kKmMgG]?)")


def git_bool(value: str) -> bool:
    """Whether git reads `value` as a boolean (`GIT_BOOL_WORDS`, `GIT_INT`)
    rather than dying on it (#733).

    The words are compared as they stand, as `strcasecmp` compares them, so
    `" true"` dies. An integer may follow white space, which `strtoimax`
    skips, so `" 1"` is taken (measured). Its range is the one git 2.55,
    which CI runs, checks: -2**31 to 2**31 - 1, the policy the bare
    `branch` in `submodule_keys` follows too. git 2.43 stops one short
    below, `-max / factor > val`, so `-2147483648` and `-2g` die there.
    """
    if value.lower() in GIT_BOOL_WORDS:
        return True
    number = GIT_INT.fullmatch(value.lstrip(" \t\n\v\f\r"))
    if number is None:
        return False
    sign, digits, unit = number.groups()
    base = 16 if digits[:2] in ("0x", "0X") else 8 if digits[0] == "0" else 10
    # " kmg".index: no unit is 1024 ** 0, `k` 1024 ** 1, and so on.
    scaled = int(digits, base) * 1024 ** " kmg".index(unit.lower() or " ")
    return -2 ** 31 <= (-scaled if sign == "-" else scaled) < 2 ** 31


def git_dies_on(field: str, value: str) -> bool:
    """Whether git `die()`s on this value of a section's key, whichever copy
    of `.gitmodules` it reads, so that no submodule has a url (#733).
    Measured on git 2.43, `invalid value` or `bad boolean config value`,
    exit 128: an `update` other than these four (`!command` included), a
    `shallow` that is no boolean, and a `fetchRecurseSubmodules` that is
    neither a boolean nor `on-demand`. git lists a key's name in lower
    case."""
    if field == "update":
        return value not in ("none", "checkout", "rebase", "merge")
    if field == "shallow":
        return not git_bool(value)
    if field == "fetchrecursesubmodules":
        return value != "on-demand" and not git_bool(value)
    return False


def submodule_keys(listing: str, working_tree: bool = True
                   ) -> list[tuple[str, str, str]] | None:
    """`(name, field, value)` for each `submodule.<name>.path` and `.url`
    key of one `gitmodules_listing` that git reads, in git's order, and no
    other key (#668), or None where git refuses the file whole (#733).
    `working_tree` says which copy it is: the working tree's file, or one
    git reads from the index or HEAD.

    PURE, as `section_url` is. Each record ends in a NUL and is the key, a
    newline and the value: a key holds no newline and a value may, so the
    record is split at its FIRST one. The NAME is all of the key between
    `submodule.` and its last dot, so a name that holds a space, a dot, a
    quote or an `=` is read whole, and the field is what follows that dot,
    which git lists in lower case.

    THE NAME KEEPS GIT'S BYTES AND THE VALUE IS TEXT (#732). The name is
    only ever handed back to git, by `configured_url` and `kept_gitdir`
    through `git_bytes`, so a byte that is not UTF-8 stays the
    `surrogateescape` the listing was decoded with: replaced, a section
    named `caf\\xe9` was looked up as `caf\\ufffd`, a name git has nowhere,
    and a member with a commit on its detached HEAD got the update line
    with no keep line. The value is compared and printed, so it takes the
    replacement, as `make siblings` reads the same file (#432) and
    `origin_url` reads a remote (#385).

    AND ONLY WHAT GIT READS (#733), by git's own tests, each measured
    against `git submodule init -- <path>`, which says `No url found` and
    exits 128 where the doctor and `make siblings` named a url:

    - a section whose name is empty or holds a `..` component is ignored,
      every key of it (`DOTDOT_COMPONENT`);
    - a `path` or `url` whose value begins with `-` is ignored, that key
      alone, so an earlier url of the section still stands;
    - a value git dies on (`git_dies_on`), in a section git reads, refuses
      the whole file, whichever copy it is: None;
    - a key of `VALUED_KEYS` given with no value at all, in a section git
      reads, is where git STOPS reading. The working tree's file is then
      refused whole (`CONFIG_ERROR_DIE`): None. A copy from the index or
      HEAD keeps every key before it (`CONFIG_ERROR_ERROR`), so they are
      handed back: measured, `p`'s section and then a bare `url` registers
      `p` from an index copy, and with the bare `url` first registers none.
      git 2.43 crashes on a bare `branch` (exit 139) where git 2.55 stops
      there as at any other.
    """
    keys = []
    for record in listing.split("\0"):
        key, valued, value = record.partition("\n")
        section, _, field = key.rpartition(".")
        name = section[len("submodule."):]
        if (not section.startswith("submodule.") or not name
                or DOTDOT_COMPONENT.search(name)):
            continue
        if not valued and field in VALUED_KEYS:
            return None if working_tree else keys
        if git_dies_on(field, value):
            return None
        if field in ("path", "url") and not value.startswith("-"):
            keys.append((name, field,
                         value.encode("utf-8", "surrogateescape").decode(
                             "utf-8", "replace")))
    return keys


def gitmodules_listing(root: Path, source: list[str],
                       partial: bool = False) -> str | None:
    """`git config -z <source> --list` in `root`: every key of one copy of
    `.gitmodules`, or None where git reads no such copy (it is not there,
    git cannot parse it, there is no git to run).

    `partial` is for a copy from the index or HEAD, which git reads up to
    its first bad line, keeping every key before it (#733): `--list` prints
    those keys before it exits 128 (measured), and they are handed back
    rather than None. The working tree's file git refuses whole.

    ONE READING, FOR `gitmodules_entry` AND `submodule_config` (#668), and
    the one `validate-family.py`'s `_gitmodules_sections` and `family.py`
    make: the whole file, cut by `submodule_keys`.

    `--list` AND NO REGEXP, because git matches a regexp in the locale's
    character set: under a UTF-8 locale `.*` matches no byte that is not
    UTF-8, so `--get-regexp '^submodule\\..*\\.(path|url)$'` left out a
    section whose name holds one, which `LC_ALL=C` read (measured, git
    2.43), and the mount that section gives was called url-less. `-z`,
    because a value may hold a line break git keeps, NEL and U+2028 among
    them, and a name a space: git's plain listing, split at line breaks and
    at the first space, cut such a url short and such a name in two.

    Decoded with `surrogateescape`, so nothing git listed is lost:
    `submodule_keys` keeps a section's name as git's own bytes and gives
    each value with the replacement (#732). Read only: `--list` writes
    nothing.
    """
    try:
        proc = subprocess.run(["git", "config", "-z", *source, "--list"],
                              cwd=str(root), capture_output=True, check=False)
    except OSError:
        return None
    if proc.returncode != 0 and not partial:
        return None
    return proc.stdout.decode("utf-8", "surrogateescape")


def configured_url(root: Path, name: str) -> str | None:
    """The url the root's own config gives the submodule NAMED `name`, or
    None (#414).

    `git submodule init` copies a mount's url out of `.gitmodules` into the
    root's config, and from then on `--init` reads it there first and asks
    `.gitmodules` only when the config has none. So an initialized mount
    whose `.gitmodules` section kept its `path` and lost its `url` key still
    updates: measured, populated past its pin or emptied by `rm`, the git
    line exits 0 and the row is `ok`. Calling that mount url-less withheld a
    line that cures it. `deinit` removes the configured url, and a section
    that is gone leaves git no NAME to look one up by (`No url found`, exit
    128, measured), so neither is helped by this.

    `git config --get` in the root, which reads what git reads: the
    repository's config and the ones above it. Read only. The key is
    handed to git as the bytes the section was named with (`git_bytes`,
    #732).
    """
    try:
        proc = subprocess.run(["git", "config", "--get",
                               git_bytes(f"submodule.{name}.url")],
                              cwd=str(root), capture_output=True, check=False)
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", "replace").strip() or None


def git_bytes(text: str) -> str | bytes:
    """`text`, read out of git as UTF-8 with `surrogateescape`, as the
    argument that hands git back the same bytes (#732).

    BYTES ON POSIX, whose command line is bytes. A `str` there is encoded
    with the filesystem encoding, which is ASCII under `LC_ALL=C
    PYTHONUTF8=0`: a section named `caf\\xc3\\xa9`, valid UTF-8, then raised
    `UnicodeEncodeError` out of `subprocess`, a traceback with no verdict,
    and one named `caf\\xe9` too. THE TEXT ITSELF ON WINDOWS, whose command
    line is text: `subprocess` would have to decode bytes there, and a byte
    that is not UTF-8 is not text to it.

    SO ON WINDOWS A NAME THAT IS NOT UTF-8 IS STILL NOT FOUND: Git for
    Windows' `xwcstoutf` turns the lone surrogate into the bytes ED B3 A9,
    not E9. A UTF-8 name is found there. What would find the other is a
    lookup with no name on the command line: read the root's config with
    `git config -z --list` and match the key's bytes in Python, and build
    the kept repository's path from `git rev-parse --git-common-dir`,
    `modules/` and the name's bytes.
    """
    if os.name == "nt":
        return text
    return text.encode("utf-8", "surrogateescape")


def submodule_url(root: Path, rel: str) -> tuple[str | None, str | None]:
    """`(name, url)`: the NAME a `.gitmodules` section gives the mount at
    `rel`, and the url `git submodule update --init` fetches it from, each
    None where git finds none (#414). A url None is a mount git stops at,
    `No url found`, exit 128.

    ONE QUESTION, ASKED IN ONE PLACE: by `checkout_reach`, of a mount a line
    would name, and by `url_less_members`, of every member a holder's own
    bootstrap updates. The section first (`gitmodules_entry`), then, for a
    section that names the mount and gives no url, the root's own config
    (`configured_url`). A section that is gone leaves git no name to look a
    configured url up by, so it is not asked there.
    """
    name, url = gitmodules_entry(root, rel)
    if name is not None and url is None:
        url = configured_url(root, name)
    return name, url


def kept_gitdir(root: Path, name: str) -> Path | None:
    """The repository git keeps in `root` for the submodule NAMED `name`, or
    None when it keeps none (#413, #414).

    `git submodule deinit -f` empties a mount and KEEPS its repository under
    the root's `.git/modules/`, and a mount whose `.git` file was deleted
    leaves it there too. `git submodule update` links such a mount to that
    repository again rather than fetching a new one (measured: a branch made
    in it before the update is still there after), so what its HEAD holds is
    what the line moves.

    BY NAME, which is not always the path: `--git-path modules/<name>` says
    where git keeps it, in the common directory of a linked worktree too.

    AND BY THE NAME'S OWN BYTES (#732): the name goes to git through
    `git_bytes`, and the path git answers with is read as a path
    (`os.fsdecode`), which `kept_head` and the keep line hand back to git
    unchanged. A strict decode of it found no repository for a section
    named `caf\\xe9`, and the commit on its detached HEAD got no keep line.

    ASKED AS `validate-pins.py` ASKS A PATH (`is_a`, #430): a `stat` the
    operating system refuses there is raised, on every Python, and
    `run_checks` names it, where Python 3.14's `is_dir()` called a kept
    repository this user cannot reach gone.
    """
    try:
        proc = subprocess.run(["git", "rev-parse", "--git-path",
                               git_bytes(f"modules/{name}")],
                              cwd=str(root), capture_output=True, check=False)
        if proc.returncode != 0:
            return None
        where = os.fsdecode(proc.stdout.rstrip(b"\r\n"))
    except (OSError, ValueError):
        return None
    path = Path(where)
    if not path.is_absolute():
        path = root / path
    return path if is_a(path, stat.S_ISDIR) else None


def kept_head(root: Path, git_dir: Path) -> tuple[bool | None, str | None]:
    """`(detached, commit)` of the HEAD in a repository git kept for a mount
    (`kept_gitdir`), or `(None, None)` when git cannot read one (#413).

    ASKED THROUGH `--git-dir`, NEVER IN THE MOUNT. In an empty mount, or in
    one with no `.git` of its own, git walks up and answers about the ROOT,
    which is how the `legs` row came to quote the root's HEAD as a leg's
    (#414). `detached` is the same function the populated mounts are asked
    through, so one question decides both. The root is the `--work-tree`
    for the reason `checkout_reach` gives: the kept repository's own names
    the mount, which may be gone.
    """
    try:
        proc = subprocess.run(
            ["git", f"--git-dir={git_dir}", f"--work-tree={root}",
             "rev-parse", "--verify", "-q", "HEAD"],
            cwd=str(root), capture_output=True, check=False)
    except OSError:
        return None, None
    if proc.returncode != 0:
        return None, None
    return (detached(root, git_dir=git_dir),
            proc.stdout.decode("ascii", "replace").strip().lower())


def left_in_reflog(is_detached: bool | None, head: str | None,
                   gitlink: str) -> bool:
    """Does checking `gitlink` out leave the commit HEAD is on held by a
    reflog entry alone?

    ONE RULE for a mount the row read a HEAD in and for a repository git
    kept for a mount with no `.git` of its own (#413): HEAD DETACHED, at a
    commit that is not the gitlink. A commit on a branch stays on it, and a
    HEAD at the gitlink does not move.
    """
    return bool(is_detached) and head is not None and head != gitlink


def unborn_branch(path: Path) -> str | None:
    """The branch HEAD names in the checkout at `path` when that branch has
    no commit, an UNBORN HEAD, or None (#414).

    NOT A LOCKSTEP FACT: the gitlink and the pin may agree, and the gate,
    handed over for it, says `pins ok` and changes nothing. Nor does
    `submodule update` cure it: git cannot find a current revision and exits
    128 (measured). No line cures it without choosing a commit for the
    person, so the row says so and names none.

    Asked only of a mount with a `.git` of its own, where `head_of` found no
    commit: `symbolic-ref` names a branch and `rev-parse` finds no commit
    behind it. A HEAD git cannot read at all is neither, and stays the
    lockstep gate's.
    """
    try:
        branch = subprocess.run(["git", "symbolic-ref", "-q", "HEAD"],
                                cwd=str(path), capture_output=True,
                                check=False)
        commit = subprocess.run(["git", "rev-parse", "--verify", "-q",
                                 "HEAD"], cwd=str(path), capture_output=True,
                                check=False)
    except OSError:
        return None
    if branch.returncode != 0 or commit.returncode == 0:
        return None
    ref = branch.stdout.decode("utf-8", "replace").strip()
    return ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else (
        ref or None)


def keeps_modules(mount: Path) -> bool:
    """Does the repository of a mount with a `.git` of its own keep
    repositories for submodules of its own, under its `modules/`?

    A leg whose working tree carries no `.gitmodules` can still mount one at
    the commit the line checks out: past its pin at a commit that dropped
    its submodule, the gitlink's commit mounts it, `--recursive` links the
    repository kept for it again and checks it out, and a commit made there
    on no branch is left in its reflog alone (measured). Asked through
    `rev-parse --absolute-git-dir` in the mount, which has a `.git` of its
    own, so git does not walk up. Read only. A refused `stat` of `modules/`
    is raised, as `kept_gitdir` raises one (#430).
    """
    try:
        where = git_out(["rev-parse", "--absolute-git-dir"], cwd=mount)
    except (Refusal, OSError, UnicodeDecodeError):
        return False
    return is_a(Path(where) / "modules", stat.S_ISDIR)


def nested_kind(carries: bool, keeps: bool) -> set:
    """`checkout_reach`'s `nested`: `{"tree"}` where the mount's working
    tree carries a `.gitmodules`, so each submodule of its own has a
    directory to run `git -C` in; `{"repo"}` where only its repository keeps
    theirs, so the directories may be gone and a keep line names the
    repository instead; else nothing."""
    if carries:
        return {"tree"}
    return {"repo"} if keeps else set()


def checkout_reach(root: Path, rel: str, gitlink: str, populated: bool,
                   own_git: bool,
                   head: str | None) -> tuple[str, object, set]:
    """`(route, keep, nested)` for a mount a CHECKOUT would cure, as the
    `legs` and `members` rows both read it, so the two rows route by one
    definition (#414). `nested` says whether the mount carries submodules of
    its own that the line's `--recursive` checks out too, and how a commit
    in one is kept (`nested_kind`): a `.gitmodules` in its working tree, or
    a repository that keeps theirs under `modules/`, kept for an emptied
    mount (`kept_gitdir`) or the mount's own (`keeps_modules`). A member's
    legs are those (#413 c), and so is anything a leg mounts.

    `route` is:

    - `checkout`: the git line cures it.
    - `relink`: the same, for a mount with files but no `.git` of its own
      whose repository git kept. The update links the two again and the row
      is `ok` (#414 1, measured), so it is not the lockstep gate's.
    - `gone`: files, no `.git` of its own and no kept repository. No update
      links anything: it tries a clone into a directory that is not empty
      and exits 1 (`destination path ... already exists`, measured), so it
      is the lockstep gate's.
    - `no-url`: no `.gitmodules` section gives its path, or the one that does
      gives no url and the root's own config has none either
      (`submodule_url`, #414 3), so the git line would exit 128. No line is
      printed for it.

    `keep` is what the line would leave in a reflog alone (`left_in_reflog`):
    the mount itself, for `git -C <mount> branch NAME`, or `(repository,
    commit, work tree)` for one with no `.git` of its own whose kept
    repository is detached off the gitlink (#413 a). `work tree` is the root
    when the mount directory is GONE, and None otherwise: the kept
    repository's own `core.worktree` names the mount, and git refuses every
    command in it while that directory is missing (`cannot chdir`, exit 128,
    measured), the keep line included, unless a `--work-tree` overrides it.
    Neither the read nor `branch` touches a work tree, so which one is named
    changes nothing else.
    """
    mount = root / rel
    name, url = submodule_url(root, rel)
    if url is None:
        return "no-url", None, set()
    carries = populated and (mount / ".gitmodules").is_file()
    if own_git:
        stranded = left_in_reflog(detached(mount), head, gitlink)
        return "checkout", (mount if stranded else None), nested_kind(
            carries, keeps_modules(mount))
    git_dir = kept_gitdir(root, name)
    if git_dir is None:
        return ("gone" if populated else "checkout"), None, set()
    is_detached, kept_at = kept_head(root, git_dir)
    keep = None
    if left_in_reflog(is_detached, kept_at, gitlink):
        keep = (git_dir, kept_at, None if mount.is_dir() else root)
    return (("relink" if populated else "checkout"), keep,
            nested_kind(carries, is_a(git_dir / "modules", stat.S_ISDIR)))


def kept_branch_line(kept: tuple, platform: str) -> str:
    """`git --git-dir=<repository> branch NAME <commit>`: the line that keeps
    a commit a kept repository holds on a detached HEAD (#413 a).

    It names the REPOSITORY, because in a mount with no `.git` of its own
    `git -C <mount> branch NAME` walks up and would branch the ROOT. And it
    names the COMMIT, so the `why` says which commit is at stake, and the
    line keeps that one wherever the repository's HEAD is by the time it
    runs. Every value through `quote_arg`.
    """
    git_dir, commit, work_tree = kept
    words = ["git", quote_arg(f"--git-dir={git_dir}", platform)]
    if work_tree is not None:
        words.append(quote_arg(f"--work-tree={work_tree}", platform))
    return " ".join([*words, "branch", "NAME", commit])


def nested_sentence(noun: str, nested: set | frozenset) -> str:
    """What `checkout_notes` says of the submodules a mount on the line
    carries of its own, which its `--recursive` checks out too (#413 c), or
    `""` where none does. `nested` is `checkout_reach`'s kinds, gathered
    over every mount the line names.

    TWO KEEP LINES, BECAUSE A DIRECTORY MAY BE GONE. `git -C LEG/SUB branch
    NAME` runs where the submodule has a directory (`tree`). Where the mount
    is empty, or its working tree no longer mounts the submodule (`repo`),
    there is none, and `git -C` exits 128 (`No such file or directory`,
    measured). The line then names the submodule's repository under the
    mount's own, `REPO/modules/SUB`, with the root as the work tree,
    because that repository's `core.worktree` names the missing directory
    and git refuses every command in it otherwise (`cannot chdir`, exit
    128, as `kept_branch_line` found one level up). Measured: it exits 0,
    and the branch holds the commit after the paste. Placeholders, because
    the row walks into none of these submodules.
    """
    if not nested:
        return ""
    if noun == "member":
        moved = ("the legs of each member at the commits that member "
                 "records, and a commit made on no branch in one of those "
                 "legs")
        inner, here = "leg", "LEG"
    else:
        moved = (f"the submodules a {noun} carries of its own, at the "
                 f"commits that {noun} records, and a commit made on no "
                 "branch in one of them")
        inner, here = "submodule", "LEG/SUB"
    tree = (f"git -C {here} branch NAME, with {here} the directory of that "
            f"{inner}")
    spelled = ("git --git-dir=REPO/modules/SUB --work-tree=ROOT branch NAME "
               f"HEAD, with REPO the git directory of that {noun}, SUB the "
               f"name of that {inner} and ROOT the directory of this "
               "repository")
    if "repo" not in nested:
        how = tree
    elif "tree" in nested:
        how = f"{tree}, or, where that directory is not there, {spelled}"
    else:
        how = f"{spelled}, because the directory of that {inner} is not there"
    return (f". It is recursive, so it also checks out {moved} is left only "
            f"in its reflog too. To keep one, run first {how}")


def checkout_notes(noun: str, off_pin: list[Path], kept: list = (),
                   relinked: list = (), nested: set | frozenset = frozenset(),
                   platform: str | None = None) -> str:
    """What a NEXT that moves HEAD owes a reader before it is pasted, as the
    sentences that follow the one saying what it does, or `""` when it owes
    nothing (#276, #413, #414).

    ONE DEFINITION FOR THE GIT LINE AND THE HOLDER'S BOOTSTRAP. #276 wrote
    the keep sentence into `submodule_update_next` alone, and the `members`
    row's other NEXT, the holder's own `scripts/bootstrap.py`, runs the same
    update (`fetch_members`) and moves the same HEADs: a commit made in the
    pinned, detached `members/<P>` was left in its reflog with no word about
    it (#413 b). So both build the sentence here.

    - `relinked`: mounts with files and no `.git` of their own whose
      repository git kept. The line links each to it again, which is why
      they are on it at all (#414 1).
    - `off_pin`: populated mounts detached off the commit the root records,
      each kept first with `git -C <mount> branch NAME`.
    - `kept`: `(repository, commit, work tree)` for mounts with no `.git` of
      their own whose kept repository is detached off it (#413 a), each kept
      first with `kept_branch_line`, which names the commit as well.
    - `nested`: the line is recursive, so it checks out the submodules a
      mount it names carries of its own too, at the commits THAT MOUNT
      records, and a commit made on no branch in one of them is left in its
      reflog the same way. For the `members` row those are each member's
      legs (#413 c); for the `legs` row, whatever a leg mounts. Said in
      general words, with a placeholder keep line, without walking into
      them, and only where a mount the line names carries some
      (`checkout_reach`'s kinds, `nested_sentence`). `--recursive` stays:
      the holder's bootstrap recurses (`fetch_members`), and a git line
      that did not would leave a member's legs where a bootstrap would not.

    A commit made in a mount on a BRANCH stays on that branch, and nothing
    is said where no mount is in any of these states, because a reader told
    about a loss that cannot happen learns to skip the sentence on the day
    it can.
    """
    target = host_shell_dialect() if platform is None else platform
    notes = "".join(f". {rel} has files but no .git of its own, and git kept "
                    "its repository, so this line links the two again"
                    for rel in relinked)
    keeps = [f"git -C {quote_arg(mount, target)} branch NAME"
             for mount in off_pin]
    keeps += [kept_branch_line(entry, target) for entry in kept]
    if keeps:
        notes += (f". A commit made in a {noun} on no branch is left only in "
                  "its reflog by this line. To keep one, run first "
                  f"{' and '.join(keeps)} with a name of your choice")
    if kept:
        notes += (". A mount with no .git of its own is named by the "
                  "repository git kept for it, because git run inside such a "
                  "mount walks up and acts on this repository")
    return notes + nested_sentence(noun, nested)


def rerun_sentence(noun: str) -> str:
    """The sentence the `legs` and `members` rows add to a line that leaves
    something wrong for the next run to name: in another mount, or in a
    mount the line does check out, whose pin is not 40 hex or not the
    gitlink (#414 4)."""
    return (". Run the doctor again afterwards, because what this line "
            f"leaves wrong, in a {noun} it checks out or in another, is named "
            "by the next run")


def unborn_sentence(rel: str, noun: str) -> str:
    """The `why` for an unborn HEAD, the NEXT being None (#414 2) or the
    lockstep gate: it names the state and says that nothing here picks the
    commit. Never the gate's own line for it, which says `pins ok` and
    changes nothing."""
    return (f"HEAD in {rel} names a branch with no commit, so there is no "
            "commit to compare with the pin, and nothing here chooses one "
            f"for you. Check out in that {noun} the commit you mean, then run "
            "the doctor again")


def no_url_sentence(rel: str) -> str:
    """The `why` for a mount git finds no url for, in `.gitmodules` or in the
    root's own config, the NEXT being None (#414 3) or the lockstep gate.
    No command, deliberately: the entry is restored from the
    repository's history by a person, and a `git checkout -- .gitmodules`
    would discard an edit nobody has committed yet."""
    return (f"git finds no url for {rel} in .gitmodules, nor in the config "
            "of this repository, so no submodule update can fetch it or check "
            "it out, and the git line would exit 128. A person restores that "
            "entry from the history of this repository, then runs the doctor "
            "again")


def gone_sentence(rel: str) -> str:
    """What the lockstep gate's `why` adds for a mount with files, no `.git`
    of its own and no kept repository (#414 1): which of the two such a
    mount is, said where the line is the gate's."""
    return (f". {rel} has files but no .git of its own, and git kept no "
            "repository for it, so no submodule update links it again")


def submodule_update_next(root: Path, paths: list[str], off_pin: list[Path],
                          noun: str, after: str = "", rerun: bool = False,
                          platform: str | None = None, *, kept: list = (),
                          relinked: list = (),
                          nested: set | frozenset = frozenset()
                          ) -> tuple[str, str]:
    """`(the line, what it does)`: the script-free command that checks each
    submodule at `paths` out at the commit `root` records for it, and the
    sentence a reader needs before pasting it (#276).

    WHY A GIT LINE AND NOT THE ROOT'S `scripts/bootstrap.py`. The `legs` and
    `members` rows used to hand over `python3 <root>/scripts/bootstrap.py`
    without asking whether the root had it, and a root that had lost it (the
    `shape currency` row says `copy-missing` for the same file) pasted
    `can't open file`, exit 2. Where the file was there it did not cure the
    row's first problem either: bootstrap never initialises a mount, it
    prints `NOT INITIALIZED` and stops. Nor does it move a tracking branch
    whose tip is not the pin, except where that loses nothing: it
    fast-forwards one behind the pin, and moves back one ahead of it with no
    commit of its own (#475, #490), and any other branch holding a commit the
    pin does not contain stays where it is
    (`templates/assembly-root/scripts/bootstrap.py`,
    `checkout_tracking_branch`). `git submodule update --init --recursive --
    <paths>` needs no script and no `PYTHONPATH`, and a probe of both cases
    shows it cures them: an empty mount is filled, and a leg committed past
    its pin is put back AT the gitlink, which is what the row compares HEAD
    with. `--init` registers a mount the clone never initialised (a plain
    `git clone` has `submodule.active` unset, and without it the update
    prints `not initialized` and leaves the row red) and `--recursive` goes
    into the submodule's own submodules, as the holder's bootstrap does
    (`fetch_members`).

    `--checkout` IS THE WORD THE EXPLANATION RESTS ON. `git submodule update`
    obeys a configured `submodule.<name>.update`, in `.git/config` or
    committed in `.gitmodules`: under `rebase` or `merge` the same line
    writes a rebased or a merge commit INTO THE LEG and the row stays red,
    and under `none` it skips the mount. Each exits 0, so the reader is told
    nothing. `--checkout` overrides the setting for this one command, so the
    line checks the commit out whatever the clone has configured.

    IT MOVES HEAD, AND THAT IS NOT FREE, so the sentence says so. A commit
    made in a leg on a BRANCH stays on that branch. A commit made on a
    detached HEAD is left only in the leg's reflog, which is what bootstrap's
    own `checkout <branch>` does to it too. `checkout_notes` names each
    place that can happen with the line that keeps the commit first: `off_pin`,
    the populated mounts whose HEAD is exactly that, and `kept`, the
    repositories git kept for mounts with no `.git` of their own whose HEAD
    is (#413 a). `relinked` and `nested` are its too.

    THE SENTENCE IS THE ROW'S `why`, ON A LINE OF ITS OWN (#277). It was a
    `   # ` tail, pasted with the line, and so was written with none of `;`,
    `'`, a backtick or a parenthesis, each of which a shell that does not
    read `#` as a comment takes as syntax. Off the line nothing in it is
    pasted, so that rule no longer binds it, and the paths in its keep lines
    are spelled by `quote_arg`, which may quote one. `after` is the caller's
    own closing sentence, and `rerun` adds the one the `legs` and `members`
    rows share (`rerun_sentence`): something this line leaves wrong, in
    another leg or member or in one it checks out, is named by the next run.

    `platform` is `quote_arg`'s and `copy_command`'s, and for the same
    reason: the line is spelled for the reader's shell, not the host's.
    """
    target = host_shell_dialect() if platform is None else platform
    line = " ".join(["git", "-C", quote_arg(root, target), "submodule",
                     "update", "--init", "--recursive", "--checkout", "--",
                     *(quote_arg(path, target) for path in paths)])
    why = (f"checks each {noun} out at the commit this repository records "
           "for it, and fetches a mount that is empty"
           + checkout_notes(noun, off_pin, kept, relinked, nested, target)
           + after)
    if rerun:
        why += rerun_sentence(noun)
    return line, why


def root_git_unread_row(ctx: Context, legs: list, line: str,
                        exc: OSError) -> Row:
    """The `legs` row of a root whose own `.git` this user cannot read
    (#1146): the gate's `line` ONCE, since it is one fact about the root and
    not one per leg, and what it leaves unasked. A FINDING, because
    `validate-pins.py` refuses the same path by name; this doctor again as
    the NEXT and the gate's advice for the cause as the `why`, because a
    person mends a mode or an owner and no git line reaches it, as for a
    mount (#430). Each leg's entry has no gitlink and carries `line` in
    `gitlink_cannot_be_read`, so `drifted_reasons` counts none of them. It
    has every key a leg's entry has, each null that this row did not ask, so
    a reader of `--json` finds `pin` or `head` on every entry."""
    entries = []
    for leg in legs:
        role = str(leg.get("role") or "?")
        entries.append({"role": role, "path": str(leg.get("path") or role),
                        "pin": None, "gitlink": None, "populated": None,
                        "head": None, "own_git": None, "unborn": None,
                        GITLINK_UNREAD: line})
    return Row("legs", "legs", FINDING,
               f"{line}, so no gitlink is read and no leg is compared with "
               "its pin", doctor_line(ctx), {"legs": entries},
               why=cannot_read_why([exc]))


def check_legs(ctx: Context) -> Row:
    """Each leg mounted, and its checked-out commit against the pin.

    NOTHING IS FETCHED. The question is what is on this disk right now: an
    empty mount is a clone nobody bootstrapped, and a mount at another commit
    is a leg somebody moved. The GITLINK against the pin file is
    `validate-pins.py`'s question and is left to it; this row reports the
    gitlink it found so the two can be read together.

    THE LEGS ARE THE MANIFEST'S, and a manifest that does not load declares
    none that this row can name -- which is not "declares no non-assembly
    leg", the sentence below, about a project that has none (#205). Nor is
    a `legs:` that is not a list, or one holding only entries that are not
    mappings: `legs_unread_row` says which, in `validate-manifest.py`'s
    words, and waits on the `manifest` row (#832).

    THE NEXT IS CHOSEN BY WHAT IS WRONG, AND IT CURES THE FIRST KIND (#276).
    `make bootstrap` was named for all of it and does not answer it: it
    never initialises an empty mount, it moves a tracking branch whose tip is
    not the pin only where that loses nothing (behind the pin, or ahead of it
    with no commit of its own: #475, #490), and a root can have lost the
    script it runs. So there are two lines, and a third answer that is none.

    - A leg a CHECKOUT cures: an empty mount, a mount with files but no
      `.git` of its own whose repository git kept (the update links the two
      again, #414), or a HEAD that is not the pin where the gitlink IS the
      pin. The line is `git submodule update --init --recursive` over those
      legs (`submodule_update_next`), which needs no script from the root.
    - A leg NO checkout cures: no gitlink, no 40-hex pin, a gitlink that is
      not the pin (a checkout lands on the gitlink, so HEAD would still not
      be the pin), a mount git cannot read a HEAD in, or one with files, no
      `.git` of its own and no kept repository to link it to. These are
      lockstep facts, `validate-pins.py` is the gate that compares them and
      names the repair, and the line is that gate's, from `validator_for`
      and `validator_command` (the root's own copy, else the standard's).
    - A leg NO LINE cures without choosing for the person (#414), so the
      NEXT is None and the `why` names the state. An UNBORN HEAD, one naming
      a branch with no commit: the update exits 128 on it and the gate says
      `pins ok` (`unborn_branch`). And a leg git finds no url for, in
      `.gitmodules` or in the root's own config: the git line exits 128, and
      the gate, measured, names no `.gitmodules` entry. It says
      `pin-submodule-uninitialized` and hands back the same git line
      (`submodule_url`).

    WHEN MORE THAN ONE KIND IS PRESENT THE CHECKOUT WINS AND A RE-RUN NAMES
    THE REST, because it is the one command that changes the row and a reader
    pasting the lockstep gate first would be told nothing new. The re-run is
    asked PER LEG too (#414): a leg the line checks out can carry a lockstep
    fact of its own, a pin that is not 40 hex or not its gitlink, which an
    empty mount hides until the next run.

    NO HEAD IS READ IN A MOUNT WITH NO `.git` OF ITS OWN (#414). `head_of`
    asks git in that directory, git walks up, and the HEAD it answered with
    was the ROOT's, which this row then quoted as the leg's. Such a mount is
    routed by whether git KEPT its repository (`checkout_reach`), because
    that is what `submodule update` routes on: probed, a populated mount
    whose repository is kept is linked to it again and the row is `ok`, and
    one whose repository is gone makes the update try a clone into a
    directory that is not empty. The `why` says which of the two it is.

    "POPULATED, BUT GIT CANNOT READ A HEAD" IS THE SECOND KIND, and it was
    probed: a mount whose gitdir is gone or whose HEAD is corrupt makes `git
    submodule update` exit 128 ("could not get a repository handle") and
    leaves this row exactly as it was, so printing that line would be a NEXT
    that does not cure. An unborn HEAD, a leg left on an orphan branch among
    them, exits 128 too ("Unable to find current revision"), and is the
    third kind, above.

    WHAT THE LINE WOULD LEAVE IN A REFLOG IS NAMED, wherever it is (#413):
    in a populated leg detached off the gitlink, and in the repository git
    kept for a leg with no `.git` of its own, read through `--git-dir` and
    kept with a line that names that repository (`checkout_notes`). A leg
    that carries submodules of its own is said in general words: the line's
    `--recursive` checks those out too, and the row does not walk into them.
    Where their directories may be gone, an emptied leg or one whose working
    tree no longer mounts them, the keep line names their repositories
    (`nested_sentence`).

    WHERE THE GATE IS THE LINE, the legs no line cures are said beside it:
    an unborn HEAD or a leg with no url gets the same sentence it gets with
    no line at all, which ends by saying to run the doctor again.

    A PIN THIS USER CANNOT READ IS NAMED, AND IS NO DRIFT (#847). It read as
    `carries no 40-hex commit`, a lockstep fact, and the verdict counted the
    leg as off its pin: DRIFTED, for a leg nobody moved, where
    `validate-pins.py` refuses the pin by name. `pin_read` asks why the pin
    gave no commit, and a `stat` or a read the operating system refused is
    `<leg>: contracts/<role>-pin.yaml: cannot be read (<reason>)`, the gate's
    line, kept in the leg's `cannot_be_read`, which `drifted_reasons` reads. It
    is asked BEFORE the mount (review of PR #860): where the mount has no
    gitlink, is empty, has no `.git` of its own, or has a HEAD git cannot read
    or one on a branch with no commit, that fact is said first and the pin's
    line follows it (`, and <the gate's line>`), so the leg is never drift for
    a pin the gate refuses by name. A person mends it, on a mode or an owner,
    so where no checkout and no lockstep fact comes first the NEXT is this
    doctor again and the `why` the gate's advice (`cannot_read_why`), as the
    `manifest kinds` and `shape currency` rows give them; beside the checkout
    line or the gate's line, the advice is said in its `why`, after what the
    line does.

    A MOUNT THIS USER CANNOT REACH IS NAMED, AND IS NO DRIFT EITHER (#430).
    At mode 000 the mount's listing raised out of this row, `could not be
    run: [Errno 13] ...`, and the verdict read the empty row as DRIFTED (1
    leg(s) not at the pin); at `r--`, Python 3.14 called it a mount with no
    `.git` of its own and named a checkout over it. `mount_read` asks as the
    gate asks, and the leg says the gate's line (`<rel>: cannot be listed
    (<reason>)`, or `<rel>/.git: cannot be read (<reason>)`, which
    `validate-pins.py` refuses it with), keeps it in `mount_cannot_be_read`,
    which `drifted_reasons` reads, and is routed to no line: a person mends a
    mode or an owner, so where nothing else has a line the NEXT is this
    doctor again, and the advice is the `why`, or follows it, as for a pin.
    Only a missing gitlink is said before it, as the lockstep fact it is.

    A ROOT WHOSE OWN `.git` THIS USER CANNOT READ IS NAMED ONCE, AND IS NO
    DRIFT EITHER (#1146). Every gitlink is read from it, through git, and
    `recorded_gitlink` takes a listing git refused for none, so a `.git`
    linked into a folder this user cannot search was `no gitlink recorded`
    for each leg and the verdict DRIFTED, about gitlinks nobody read.
    `root_git_read` asks it as `validate-pins.py` does, and the row says the
    gate's line once, for the root: no gitlink is known, so no leg is
    compared with its pin. Each leg keeps the line in
    `gitlink_cannot_be_read`, which `drifted_reasons` reads, and the NEXT and
    the `why` are a person's, as for a mount (`root_git_unread_row`).
    """
    needs = ("the legs it declares are not known and none is checked against "
             "its pin")
    waiting = (waiting_row(ctx, "legs", "legs", needs, {"legs": []})
               or legs_unread_row(ctx, "legs", "legs", needs, {"legs": []}))
    if waiting is not None:
        return waiting
    legs = ctx.legs()
    if not legs:
        return Row("legs", "legs", NA,
                   "project.yaml declares no non-assembly leg; a "
                   "one-repository project has none and is not less governed "
                   "for it", None, {"legs": []})
    root_unread = root_git_read(ctx.root)
    if root_unread is not None:
        return root_git_unread_row(ctx, legs, *root_unread)
    rows: list[dict] = []
    problems: list[str] = []
    checkout: list[str] = []
    off_pin: list[Path] = []
    kept: list[tuple] = []
    relinked: list[str] = []
    lockstep: list[str] = []
    gone: list[str] = []
    stuck: list[str] = []
    #: The `OSError` of each pin the operating system refused to read (#847),
    #: and of each mount whose `stat` it refused (#430).
    refused: list[OSError] = []
    #: The `OSError` of each mount it refused to list (#430).
    unlisted: list[OSError] = []
    rerun = False
    nested: set = set()
    for leg in legs:
        role = str(leg.get("role") or "?")
        rel = str(leg.get("path") or role)
        mount = ctx.root / rel
        pin = f"contracts/{role}-pin.yaml"
        pinned = pin_commit(ctx.root, pin)
        # ASKED BEFORE THE MOUNT (#847, review of PR #860): asked only where
        # every mount branch passed, a pin this user cannot read went unnamed
        # beside an empty mount, and the verdict read the leg as drift.
        refusal = pin_read(ctx.root, pin)[1] if pinned is None else None
        gitlink = recorded_gitlink(ctx.root, rel)
        populated, own_git, unread = mount_read(ctx.root, rel)
        head = head_of(mount) if populated and own_git else None
        unborn = (unborn_branch(mount) if populated and own_git
                  and head is None else None)
        entry = {"role": role, "path": rel, "pin": pinned,
                 "gitlink": gitlink, "populated": populated, "head": head,
                 "own_git": own_git, "unborn": unborn}
        rows.append(entry)
        if refusal is not None:
            entry["cannot_be_read"] = cannot_be_read(pin, refusal)
            refused.append(refusal)
        if unread is not None:
            entry[MOUNT_UNREAD] = unread[0]
            (unlisted if unread[2] else refused).append(unread[1])
        problem = None
        cures = False
        #: Whether the problem is the pin's line, which no mount fact came
        #: before.
        named = False
        if gitlink is None:
            problem = (f"{rel}: no gitlink recorded, so this leg is not "
                       "mounted as a submodule at all")
            lockstep.append(rel)
            if unread is not None:
                problem += f", and {unread[0]}"
        elif unread is not None:
            # A PERSON'S, on a mode or an owner (#430): no line reaches it.
            problem = mount_unread_said(unread[0])
        elif not populated:
            problem = (f"{rel}: the gitlink is there and the directory is "
                       "empty -- an unbootstrapped clone")
            cures = True
        elif not own_git:
            problem = (f"{rel}: populated, but with no .git of its own, so "
                       "git cannot read a HEAD in it")
            cures = True
        elif unborn is not None:
            problem = (f"{rel}: HEAD names the branch {unborn}, which has no "
                       "commit")
            stuck.append(unborn_sentence(rel, "leg"))
        elif head is None:
            problem = f"{rel}: populated, but git cannot read a HEAD in it"
            lockstep.append(rel)
        elif pinned is None and refusal is None:
            problem = (f"{rel}: {pin} carries no 40-hex commit to compare "
                       "HEAD against")
            lockstep.append(rel)
        elif pinned is None:
            problem = (f"{rel}: {entry['cannot_be_read']}, so there is no "
                       "pinned commit to compare HEAD against")
            named = True
        elif head != pinned:
            problem = (f"{rel}: checked out at {head[:12]}, pinned at "
                       f"{pinned[:12]}")
            if gitlink == pinned:
                cures = True
            else:
                lockstep.append(rel)
        if cures:
            route, keep, carries = checkout_reach(ctx.root, rel, gitlink,
                                                  populated, own_git, head)
            if route == "no-url":
                problem += (", and git finds no url for it in .gitmodules or "
                            "in the config of this repository")
                stuck.append(no_url_sentence(rel))
            elif route == "gone":
                lockstep.append(rel)
                gone.append(rel)
            else:
                checkout.append(rel)
                nested |= carries
                if route == "relink":
                    relinked.append(rel)
                if isinstance(keep, tuple):
                    kept.append(keep)
                elif keep is not None:
                    off_pin.append(keep)
                # ITS OWN LOCKSTEP FACT (#414): the line checks the gitlink
                # out, and a pin that is not 40 hex, or not that gitlink, is
                # what the next run names.
                if pinned is None or gitlink != pinned:
                    rerun = True
        if refusal is not None and not named:
            # A MOUNT FACT CAME FIRST: the pin is named beside it.
            problem += f", and {entry['cannot_be_read']}"
        if problem:
            problems.append(problem)
    detail = {"legs": rows}
    if problems:
        rerun = (rerun or bool(lockstep) or bool(stuck) or bool(refused)
                 or bool(unlisted))
        said = ([cannot_read_why(refused, unlisted)] if refused or unlisted
                else [])
        if checkout:
            # `make bootstrap` IS NAMED ONLY WHERE IT CAN RUN, and said for
            # what it does: it puts a leg on its tracking branch, and
            # leaves alone one whose branch is already ahead of the pin
            # (`checkout_tracking_branch` prints "not moving an existing
            # branch"), which is the commit-past-the-pin case this line
            # was written for.
            after = ""
            if own_bootstrap(ctx.root, make_target=True):
                after = (". Then make bootstrap puts each leg on its "
                         "tracking branch, and leaves alone one whose branch "
                         "is already ahead of the pin")
            # The line is the NEXT and what it does is the row's `why`, on a
            # line of its own (#277).
            next_command, why = submodule_update_next(
                ctx.root, checkout, off_pin, "leg", after, rerun, kept=kept,
                relinked=relinked, nested=nested)
            # A pin this user cannot read is a person's to mend, so its
            # advice is said beside the line as beside the gate's (#847).
            why += "".join(f". {sentence}" for sentence in said)
        elif lockstep:
            # NO CHECKOUT CURES IT: the lockstep gate, one definition of it
            # for this row and the `pins` row (`lockstep_next`), which mount
            # with no `.git` of its own is the gate's because git kept no
            # repository for it, and what no line cures (#414).
            next_command, why = lockstep_next(ctx, PINS_GATE, "leg")
            if why:
                why += "".join(gone_sentence(rel) for rel in gone)
                why += "".join(f". {sentence}" for sentence in [*said, *stuck])
            elif said or stuck:
                why = ". ".join([*said, *stuck])
        elif refused or unlisted:
            # A PERSON'S, on a mode or an owner, and never a git line (#847,
            # #430).
            next_command, why = doctor_line(ctx), ". ".join([*said, *stuck])
        else:
            # NO LINE CURES IT without choosing for the person (#414).
            next_command, why = None, ". ".join(stuck)
        return Row("legs", "legs", FINDING, "; ".join(problems),
                   next_command, detail, why=why)
    return Row("legs", "legs", OK,
               f"{len(rows)} leg(s) mounted and checked out at their pins",
               None, detail)


def lane_trailer_command(platform: str | None = None) -> str:
    """The ` --trailer 'Lane: <name>'` a next command carries when the
    environment names a lane, and `""` when it does not.

    WHY A NEXT COMMAND CARRIES IT AT ALL. `update-shape.py apply --branch`
    writes its own commit, and the lane-collision protocol wants the `Lane:`
    line on that commit as much as on the pull request -- so a row that
    printed the apply without it handed somebody a command whose result they
    then had to amend by hand. Four InkRouter re-pins landed on 2026-09-11
    with no trailer at all, each one run exactly as the line printed it
    (#111). The `apply` it ends is the `shape currency` row's `why` since
    #277 -- the words that used to follow `   # ` on its NEXT line -- and the
    trailer went with it, unchanged.

    NOTHING WHEN NO LANE IS SET, which is what keeps every row this file has
    ever printed byte-identical for everybody who is not in a lane; and only
    the LANE, never `Co-Authored-By:`, which names a person or a model that
    no environment variable knows.

    `platform` IS PASSED ON, not merely branched on -- the rule
    `copy_command` below states at length: the trailer is spelled by
    `quote_arg` for the platform ASKED FOR, so a line rendered for a Windows
    reader is quoted PowerShell's way whichever host rendered it, and both
    spellings are assertable from either.
    """
    return lane_trailer_argument(lambda value: quote_arg(value, platform))


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
    with no platform reads the REAL host's shell, so a Windows line
    built on a POSIX runner would be quoted by `sh` rules -- the function
    claiming a spelling it did not produce, which is the defect #103 names
    in the neighbouring `scaffold_command`. Here the argument is threaded
    through to every value, so what the test asserts is what a Windows
    reader gets.

    WITH NO `platform`, THE BRANCH ASKS WHAT THE QUOTING ASKS:
    `host_shell_dialect` (#711). `Copy-Item` is a cmdlet, which Git Bash
    does not have, and Git Bash has a `cp`, so a Windows machine run from
    Git Bash is handed `cp` and `sh`'s quoting, the line its shell runs.
    """
    if (host_shell_dialect() if platform is None else platform) == "nt":
        return (f"Copy-Item -LiteralPath {quote_arg(source, platform)} "
                f"-Destination {quote_arg(target, platform)}")
    return f"cp {quote_arg(source, platform)} {quote_arg(target, platform)}"


#: Named once, like `LABEL_MANIFEST_KINDS` above: this function's three
#: returns and the `CHECKS` entry below must all print the same row name.
LABEL_LEG_SHAPE_FILES = "leg shape files"


def shape_file_state(here: Path, there: Path, name: str) -> tuple:
    """`(what ONE leg shape file is, against the template's copy of it, the
    `OSError` of a read the operating system refused or None)`.

    The five answers this returns are the whole vocabulary of the row above,
    and they are five because a byte comparison is only meaningful for two of
    them. `AGENTS.md` and `README.md` are RENDERED from their templates --
    they carry `{{PLACEHOLDER}}`s the scaffold fills in -- so "differs" is
    their permanent state and this says `rendered` rather than pretending a
    byte comparison meant something. A file the template does not carry is
    reported as what it is rather than as a difference, because the standard
    has nothing to compare it against.

    Split out of `check_leg_shape_files` for #134: the chain answers one
    question about one file, and the loop that calls it answers a different
    one about a leg.

    A SIXTH ANSWER, `cannot be read (<reason>)`, for the leg's file whose
    `stat` or read the operating system refuses (#430). It was `absent` on
    Python 3.14, with a `cp` of the template over a file that is there, and
    up to 3.13 the row `could not be run`. `there` is the standard's own copy.

    ITS ERROR IS KEPT BESIDE IT (#1175): the words carry only the reason, and
    the row's `why` is the gate's advice for the cause (`cannot_read_why`),
    which a permission and an I/O error are told apart by.
    """
    try:
        if not is_a(here, stat.S_ISREG):
            return "absent", None
    except OSError as exc:
        return f"cannot be read ({os_reason(exc)})", exc
    if name in LEG_RENDERED:
        return "rendered", None
    if not there.is_file():
        return "present (the template has none)", None
    try:
        mine = here.read_bytes()
    except OSError as exc:
        return f"cannot be read ({os_reason(exc)})", exc
    if mine == there.read_bytes():
        return "identical", None
    return "differs", None


def leg_shape_comparison(ctx: Context, role: str, rel: str) -> tuple:
    """ONE leg's shape files, and the ones that are not there at all.

    Returns the `--json` entry for the leg, the `(role, leg, file)` triples
    the row names as missing and the `OSError` of each file this user cannot
    read (#1175), so that the caller adds them up rather than being handed a
    half-built dictionary to finish.

    EVERY EARLY RETURN IS A LEG THERE IS NOTHING TO COMPARE, and neither of
    them is a fault of the repository's: a leg nobody has bootstrapped has no
    files yet, and a `templates/<role>-root/` this checkout does not carry is
    the STANDARD being short rather than the project being wrong. Both say
    which they are, in the `state` the row prints. A leg this user cannot
    reach is a third, and its `state` is the gate's line for it, kept under
    `mount_cannot_be_read` as the `legs` row keeps it (`mount_read`, #430).
    A leg whose git directory this user cannot read is not: no file here is
    read through git, so its files are compared (#1174).

    Split out of `check_leg_shape_files` for #134.
    """
    mount = ctx.root / rel
    template = ctx.shape / "templates" / f"{role}-root"
    populated, _own_git, unread = mount_read(ctx.root, rel, git_dir=False)
    if unread is not None:
        return ({"role": role, "state": unread[0], MOUNT_UNREAD: unread[0]},
                [], [])
    if not populated:
        return {"role": role, "state": "not populated"}, [], []
    if not template.is_dir():
        return {"role": role,
                "state": f"no templates/{role}-root/ to compare against"}, [], []
    files: dict[str, str] = {}
    absent: list[tuple[str, str, str]] = []
    refused: list[OSError] = []
    for name in LEG_SHAPE_FILES:
        state, exc = shape_file_state(mount / name, template / name, name)
        files[name] = state
        if state == "absent":
            absent.append((role, rel, name))
        if exc is not None:
            refused.append(exc)
    return ({"role": role, "state": "compared", "files": files}, absent,
            refused)


def leg_shape_summary(rel: str, entry: dict) -> str:
    """One leg's half of the row's reason: its state, or its files by name.

    A leg that WAS compared says what each file is rather than the word
    `compared`, which on its own tells a reader nothing they came for.

    Split out of `check_leg_shape_files` for #134.
    """
    if MOUNT_UNREAD in entry:
        # The gate's line already starts with the leg's path (#430).
        return entry[MOUNT_UNREAD]
    if entry["state"] != "compared":
        return f"{rel}: {entry['state']}"
    named = ", ".join(f"{name} {state}"
                      for name, state in entry["files"].items())
    return f"{rel}: {named}"


def missing_shape_file_fix(ctx: Context, missing: list) -> tuple:
    """`(next command, why)` for a leg missing a shape file.

    A COPY IS OFFERED ONLY FOR A FILE A COPY WOULD FIX -- `cp` for a POSIX
    reader and `Copy-Item -LiteralPath` for a PowerShell one, which is
    `copy_command`'s job (#105). The template's `AGENTS.md` and `README.md`
    carry `{{PLACEHOLDER}}`s the scaffold renders, so copying one verbatim
    leaves a leg holding literal `{{PROJECT_NAME}}` -- a command that produces
    an invalid leg is worse than no command at all (Copilot, PR #96). For
    those the row says what the file IS, and the repair is a human's until the
    repair mode lands.

    AND THE COMMAND IS A COMMAND (#277). Where every missing file is
    rendered, the NEXT used to be that sentence itself -- prose in the
    command's place, with a whole command in backticks inside it, which an
    interactive zsh pasted as command substitution. It is now the
    `scaffold-project.py --help` the sentence names, and the sentence is the
    `why`; so is the note a partial copy used to carry after `   # `.

    Split out of `check_leg_shape_files` for #134.
    """
    copyable = [entry for entry in missing if entry[2] not in LEG_RENDERED]
    if not copyable:
        return (f"{PYTHON} {quote_arg(ctx.shape / 'scaffold-project.py')} "
                "--help",
                f"the missing file(s) are RENDERED per project from "
                f"templates/<role>-root/ — `{PYTHON} "
                f"{quote_arg(ctx.shape / 'scaffold-project.py')} --help` "
                "shows what writes them; copying a template verbatim "
                "would leave "
                "`{{PLACEHOLDER}}`s in the leg")
    role, rel, name = copyable[0]
    source = ctx.shape / "templates" / f"{role}-root" / name
    fix = copy_command(source, ctx.root / rel / name)
    if len(copyable) < len(missing):
        return fix, ("and the rest are RENDERED per project "
                     "(placeholders): scaffold-project.py writes those, "
                     "and copying a template verbatim would not")
    return fix, None


def check_leg_shape_files(ctx: Context) -> Row:
    """Each present leg's shape files against `templates/<role>-root/`.

    A COMPARISON, NOT A GATE. No leg file has a digest row anywhere today --
    `contracts/shape-pin.yaml` covers the assembly root's copies and nothing
    else -- so a leg whose `.gitignore` has grown a line is not thereby wrong,
    and saying it were would be a rule this standard has not made. What IS
    reported as a finding is a file that is not there at all, because a leg
    with no `AGENTS.md` is a leg an agent reads nothing in.

    THE COMPARING IS `leg_shape_comparison`'s and the wording is
    `leg_shape_summary`'s, so that this reads as the three sentences it is:
    compare every leg, say what was found, and offer a copy for the files a
    copy would fix.

    A LEG OR A FILE THIS USER CANNOT REACH KEEPS THE ROW OFF `ok` (#430): it
    is a `note`, because what is missing is a read, the `legs` row asserts
    the mount, and "compared" is not a claim to make about a file nobody
    read. It offers no copy: the file is there.

    A FILE THIS USER CANNOT READ IS TOLD THE CURE (#1175): the note's `why`
    is the gate's advice for the cause (`cannot_read_why`), as every other
    path this doctor cannot read is told it, and beside a missing file's
    copy it follows what that line's `why` says. A mount is not: the `legs`
    row names it and gives its advice. The NEXT stays None and the row stays
    a note, so the verdict is what it was: no leg file gates anything, so a
    file nobody could read cannot change it, and the advice ends by saying
    to run this doctor again.
    """
    needs = "there are no legs to compare"
    waiting = (waiting_row(ctx, "leg-shape-files", LABEL_LEG_SHAPE_FILES,
                           needs, {"legs": []})
               or legs_unread_row(ctx, "leg-shape-files",
                                  LABEL_LEG_SHAPE_FILES, needs, {"legs": []}))
    if waiting is not None:
        return waiting
    legs = ctx.legs()
    if not legs:
        return Row("leg-shape-files", LABEL_LEG_SHAPE_FILES, NA,
                   "no legs to compare", None, {"legs": []})
    per_leg: dict[str, dict] = {}
    missing: list[tuple[str, str, str]] = []
    #: The `OSError` of each leg file this user cannot read (#1175).
    refused: list[OSError] = []
    for leg in legs:
        role = str(leg.get("role") or "?")
        rel = str(leg.get("path") or role)
        entry, absent, unread_files = leg_shape_comparison(ctx, role, rel)
        per_leg[rel] = entry
        missing.extend(absent)
        refused.extend(unread_files)
    detail = {"legs": per_leg, "compared": list(LEG_SHAPE_FILES)}
    summary = "; ".join(leg_shape_summary(rel, entry)
                        for rel, entry in per_leg.items())
    advice = cannot_read_why(refused) if refused else None
    if missing:
        named = ", ".join(f"{leg}/{file}" for _, leg, file in missing)
        # `note`, NOT `FINDING`. This is the row that printed `INVALID`
        # over a live estate whose every real gate was green, because
        # `templates/spec-root/.gitignore` entered the standard AFTER that
        # project was scaffolded. No pin names a leg file, no validator
        # asserts one, and the shape-currency row cannot even report it --
        # so every project cut before that template existed was failed by a
        # rule this standard never made. The difference is worth a reader's
        # eye and is not a verdict.
        fix, why = missing_shape_file_fix(ctx, missing)
        # A file this user cannot read beside it: its advice follows (#1175).
        why = ". ".join(said for said in (why, advice) if said) or None
        return Row("leg-shape-files", LABEL_LEG_SHAPE_FILES, NOTE,
                   f"{summary}  (missing: {named})", fix, detail, why=why)
    unread = bool(refused) or any(MOUNT_UNREAD in entry
                                  for entry in per_leg.values())
    return Row("leg-shape-files", LABEL_LEG_SHAPE_FILES,
               NOTE if unread else OK, summary, None, detail, why=advice)


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


def leg_tracked_files(mount: Path) -> tuple:
    """`(path, size)` for every TRACKED file in a leg, in ONE git call.

    `ls-files` reads the INDEX, which is exactly the question this row asks: a
    file staged into a leg is in that leg whether or not anybody has committed
    it yet, and what is on this disk right now is the doctor's subject in
    every other row too.

    `--stage`, SO THE SAME CALL READS EACH PATH'S MODE (#176). It lists exactly
    the paths plain `ls-files` lists, in the same order and with an unmerged
    path once per stage just as before, each prefixed by `<mode> <object>
    <stage>` and a tab. The modes are read from the index as the paths are,
    because a gitlink staged and not yet committed is in the leg as surely as
    a file is, and modes read from `HEAD` instead could disagree with these
    paths about it.

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

    THE THIRD IS THE SET OF PATHS WHOSE EVERY STAGE IS A GITLINK. They stay in
    the first list, because they are tracked and the count of tracked paths is
    the same number it always was; the caller keeps them out of the
    classification. A path with ANY stage that is not a gitlink is not in it:
    an unmerged `.cursor` that is a file on one side and a submodule on the
    other has a file in the leg, and a file is classified (Codex review on
    #186). That is why the mode is kept per STAGE until the last record is
    read, and not as the path's name alone.
    """
    raw = git_out(["ls-files", "--stage", "-z"], cwd=mount, binary=True)
    out = []
    unwritable = []
    modes: dict = {}
    for record in raw.split(b"\x00"):
        if not record:
            continue
        head, _, name = record.partition(b"\t")
        path = name.decode("utf-8", "surrogateescape")
        if UNWRITABLE_IN_A_PLAN.search(path):
            unwritable.append(repr(path))
            continue
        modes.setdefault(path, set()).add(
            head.split(b" ", 1)[0].decode("ascii", "replace"))
        try:
            size = (mount / path).lstat().st_size
        except OSError:
            size = 0
        out.append((path, size))
    gitlinks = {path for path, seen in modes.items() if seen == {GITLINK_MODE}}
    return out, unwritable, gitlinks


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


#: What `not_its_own_repository` says where git names no top level at all,
#: which `audit_leg` tells from git answering from another one (#1146).
NOT_A_GIT_REPOSITORY = ("it is not a git repository, so it has no tracked "
                        "paths of its own to read")


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
        return NOT_A_GIT_REPOSITORY
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


def first_three(names: list) -> str:
    """The first three of `names`, and how many more there are."""
    named = ", ".join(names[:3])
    if len(names) > 3:
        named += f", and {len(names) - 3} more"
    return named


def named_submodules(kept: list, with_rule: bool = True) -> str:
    """The first three submodules of one class, each with the rule that named
    it where one did (Codex review on #186, round 2) -- and without it for a
    submodule checked against the record, which no rule decided (#189).
    """
    def one(item: dict) -> str:
        if not with_rule or item["rule"] is None:
            return item["path"]
        return f"{item['path']} (rule {item['rule']})"

    return first_three([one(item) for item in kept])


def named_against_the_record(rows: list) -> str:
    """The first three submodules in a leg other than the recorded one, each
    with the leg the record names (#189)."""
    return first_three([f"{row['path']} (recorded in the "
                        f"{row['classified_as']} leg)" for row in rows])


def kept_submodules(kept: list) -> str:
    """The clauses naming the submodules the legs keep, one for each class
    the row does not count as misplaced (#176, #189).

    ONE CLAUSE FOR EACH CLASS PRESENT, IN EVERY BRANCH THAT CAN MEET ONE, so
    that a submodule beside a misplaced file, or beside a question, is said
    exactly as it is said on its own. The classes are SAID APART because
    they are not the same claim. `recorded` is a submodule in the leg the
    adoption recorded for it: checked, and placed (#189). `kept` is a
    submodule the root cannot hold, and `unverifiable` is one in the leg a
    rule says it does not belong in, which with no record the doctor cannot
    check against the answer the adoption plan gave (Codex review on #186,
    round 2). The last asks for a human's look in so many words, and is
    still no finding. `misplaced` has no clause here: it is a path in the
    wrong leg, and it is named where those are.
    """
    recorded = [item for item in kept
                if item["placement"] == SUBMODULE_RECORDED]
    placed = [item for item in kept if item["placement"] == SUBMODULE_KEPT]
    asked = [item for item in kept
             if item["placement"] == SUBMODULE_UNVERIFIABLE]
    clauses = []
    if recorded:
        clauses.append(
            f"{len(recorded)} submodule(s) in the leg {THE_RECORD} records "
            f"for them (#189): {named_submodules(recorded, with_rule=False)}")
    if placed:
        clauses.append(
            f"{len(placed)} submodule(s) the path policy does not judge, "
            "which a leg holds because the assembly root keeps no source "
            f"submodule (#166): {named_submodules(placed)}")
    if asked:
        clauses.append(
            f"{len(asked)} submodule(s) at a path a rule assigns to the "
            "other leg, which the doctor cannot verify here because a "
            "submodule's leg is the adoption plan's answer (confirm against "
            f"the plan, or move it): {named_submodules(asked)}")
    return "; ".join(clauses)


def answered_clause(legs: list) -> str:
    """The clause naming each leg's `.gitmodules` whose policy question the
    record answered, or "" where none was (#189).

    SAID, because the row no longer counts it among the paths the policy
    will not call, and a reader who knows the policy asks about every
    `.gitmodules` is owed where this one's answer came from.
    """
    answered = [path for leg in legs for path in leg.get(ANSWERED) or []]
    if not answered:
        return ""
    return (f"{THE_RECORD} answers the question the policy asks of "
            f"{', '.join(answered)}: which leg owns the submodules it "
            "registers")


def held_clauses(detail: dict) -> str:
    """`kept_submodules` and `answered_clause` as the tail of the row's
    sentence: `; ` and their clauses, or nothing where neither has one --
    no submodule at all, or only misplaced ones, which `misplaced_clauses`
    names -- so that no reason ends on a separator with nothing after it.
    """
    legs = detail.get("legs") or []
    clauses = (kept_submodules(detail.get("submodules") or []),
               answered_clause(legs),
               empty_clause(legs),
               unregistered_clause(legs),
               other_sections_clause(legs),
               no_gitmodules_clause(legs),
               answers_clause(detail.get(ANSWERED_PATHS) or []),
               unslashed_clause(legs),
               slashed_clause(legs),
               unheld_clause(detail.get(UNHELD) or []))
    said = "; ".join(clause for clause in clauses if clause)
    return f"; {said}" if said else ""


def answers_clause(answered: list) -> str:
    """The clauses naming the paths `answered_paths:` answered, each with the
    rule behind it, or "" where it answered none: the questions the policy
    asks (#525), then the paths a rule puts in another leg (#655).

    SAID, as the `.gitmodules` the record answers is said: the row no longer
    counts these among the paths the policy will not call, or puts
    elsewhere, and a reader who knows the policy is owed where the answer
    came from. SAID APART, because a question the policy asked and a rule
    the plan answered against are not the same claim, and the second names
    the leg the rule gives.
    """
    asked = [row for row in answered if row["classified_as"] is None]
    against = [row for row in answered if row["classified_as"] is not None]
    clauses = []
    if asked:
        named = first_three([f"{row['path']} (rule {row['rule']})"
                             for row in asked])
        clauses.append(f"{THE_ANSWERS} answers the question the policy asks "
                       f"of {len(asked)} path(s) (#525): {named}")
    if against:
        named = first_three([f"{row['path']} ({row['classified_as']} by rule "
                             f"{row['rule']})" for row in against])
        clauses.append(f"{THE_ANSWERS} answers {len(against)} path(s) into "
                       "the leg they are in, which a rule puts elsewhere "
                       f"(#655): {named}")
    return "; ".join(clauses)


def empty_clause(legs: list) -> str:
    """The clause naming each leg's `.gitmodules` that holds no section, in a
    leg that holds no submodule, or "" where none does (#655, #914). SAID, as
    the one the record answers is: a reader who knows the policy asks about
    every `.gitmodules` is owed why this one was not asked. AND HOW TO REMOVE
    IT (#914), since no record can answer it and nothing needs it. `git rm
    -f`, because a plain `git rm` refuses the file where it is staged and not
    committed (what a plain `git rm` of a leg's only submodule leaves) or
    changed on disk and not staged (measured, git 2.43); `-f` takes it out of
    the index and the disk in each state, and discards no section, since the
    clause is printed only where the disk copy holds none."""
    empty = [path for leg in legs for path in leg.get(EMPTY_GITMODULES) or []]
    if not empty:
        return ""
    return (f"the policy asks nothing of {len(empty)} `.gitmodules` that "
            "hold(s) no section and so register(s) no submodule, in a leg "
            f"that holds none (#655, #914): {', '.join(empty)}; nothing "
            "needs one, and `git rm -f .gitmodules` in its leg removes it")


def unregistered_clause(legs: list) -> str:
    """The clause naming each submodule a leg holds beside a `.gitmodules`
    that holds no section, or "" where there is none (#914).

    SAID, because that `.gitmodules` is not the empty one `empty_clause`
    names: it stays the question it was, and the way out is not to remove
    it. No section registers the submodule, so a recursive clone of the leg
    exits 0 and leaves its directory empty, and `git submodule status` there
    exits 128 with `no submodule mapping found in .gitmodules` (measured,
    git 2.43). Neither record can say where its repository is, and `git
    submodule add` refuses a path the index holds: the person writes its
    section, or removes the gitlink.

    THE REMOVAL TYPED AS PRINTED WORKS (measured, git 2.43). `git rm
    --cached` dies with `please stage your changes to .gitmodules` where the
    leg's tracked `.gitmodules` has an edit that is not staged, so the clause
    says to stage it first; and it names the path as the leg spells it,
    because the row's own `code/vendor/lib` is the project's spelling, which
    the leg does not know.

    ONLY THE LEGS WHOSE ENTRY GIVES NO `unregistered_beside` (#1080): a
    submodule beside other sections, or in a leg whose index tracks no
    `.gitmodules`, has its own clause (`other_sections_clause`,
    `no_gitmodules_clause`).
    """
    held = unregistered_beside(legs, None)
    if not held:
        return ""
    return (f"{len(held)} submodule(s) sit beside a `.gitmodules` of their "
            "leg that holds no section, so nothing registers them and a "
            "recursive clone of the leg leaves each empty (#914): "
            f"{first_three(held)}; give each a section with its `path` and "
            "`url` in that `.gitmodules`, or, once that `.gitmodules` is "
            "staged (`git add .gitmodules`), remove its gitlink with `git rm "
            "--cached <its path in the leg>` in its leg")


def unregistered_beside(legs: list, beside: str | None) -> list:
    """Each submodule a leg's entry names under `unregistered_submodules`,
    where its `unregistered_beside` is `beside` (None: not given) (#1080).
    """
    return [path for leg in legs if leg.get(UNREGISTERED_BESIDE) == beside
            for path in leg.get(UNREGISTERED_SUBMODULES) or []]


def other_sections_clause(legs: list) -> str:
    """The clause naming each submodule a leg holds beside a `.gitmodules`
    whose sections register other paths, or "" where there is none (#1080).

    SAID, as `unregistered_clause` is, and with its way out: a recursive
    clone of the leg exits 0 and leaves the submodule's directory empty,
    and `git submodule status` exits 128 with `no submodule mapping found
    in .gitmodules` (measured, git 2.43). The person writes its section in
    that file, or removes the gitlink. `git rm --cached` dies with `please
    stage your changes to .gitmodules` where that file has an edit not
    staged, as beside a file with no section, so the clause says to stage
    it first; typed in that order each exits 0 (measured).
    """
    held = unregistered_beside(legs, BESIDE_OTHER_SECTIONS)
    if not held:
        return ""
    return (f"{len(held)} submodule(s) sit beside a `.gitmodules` of their "
            "leg with no section for them, so nothing registers them and a "
            "recursive clone of the leg leaves each empty (#1080): "
            f"{first_three(held)}; give each a section with its `path` and "
            "`url` in that `.gitmodules`, or, once that `.gitmodules` is "
            "staged (`git add .gitmodules`), remove its gitlink with `git rm "
            "--cached <its path in the leg>` in its leg")


def no_gitmodules_clause(legs: list) -> str:
    """The clause naming each submodule a leg holds where the leg's index
    tracks no `.gitmodules`, and the copy git reads instead does not
    register it (`unregistered_gitlinks`), or "" where there is none
    (#1080).

    SAID, as `unregistered_clause` is: a recursive clone of the leg leaves
    the submodule empty, and `git submodule status` exits 128 (measured,
    git 2.43). The section goes in a `.gitmodules` the person adds to the
    leg, and with none in the index there is nothing to stage before `git
    rm --cached`, which exits 0 as printed (measured).

    THE INDEX, AND NOT THE LEG, IS WHAT HOLDS NONE: beside an untracked
    `.gitmodules`, and beside HEAD's copy once `git rm .gitmodules` took
    the file away, each way out is typed as printed in the tests. `git rm
    --cached` alone exits 0 there, and a section written in that file, or
    in a new one, then `git add .gitmodules`, gives `git submodule status`
    0 (measured, git 2.43).
    """
    held = unregistered_beside(legs, BESIDE_NO_GITMODULES)
    if not held:
        return ""
    return (f"{len(held)} submodule(s) sit in a leg whose index tracks no "
            "`.gitmodules`, so nothing registers them and a recursive clone "
            f"of the leg leaves each empty (#1080): {first_three(held)}; give "
            "each a section with its `path` and `url` in a `.gitmodules` "
            "added to its leg, or remove its gitlink with `git rm --cached "
            "<its path in the leg>` in its leg")


def slashed_clause(legs: list) -> str:
    """The clause naming each `answered_paths:` row that names a file of its
    leg with the `/` a directory's row ends with, or "" where none does
    (#914). SAID, as `unslashed_clause` says the other spelling, and for
    the same reason: such a row answers nothing, since no file is under a
    file, and never a finding."""
    rows = [path for leg in legs for path in leg.get(SLASHED) or []]
    if not rows:
        return ""
    return (f"{len(rows)} row(s) of {THE_ANSWERS} name a file with the `/` "
            "only a directory's row ends with, so each answers nothing "
            f"(#914): {first_three(rows)}")


def unslashed_clause(legs: list) -> str:
    """The clause naming each `answered_paths:` row that names a directory of
    its leg without its `/`, or "" where none does (#655). SAID, and never a
    finding nor what keeps the row off `ok`: such a row answers nothing,
    which is said so that its writer is not left to wonder why the question
    it was meant to answer is still asked."""
    rows = [path for leg in legs for path in leg.get(UNSLASHED) or []]
    if not rows:
        return ""
    return (f"{len(rows)} row(s) of {THE_ANSWERS} name a directory without "
            "the `/` a directory's row ends with, so each answers nothing "
            f"under it (#655): {first_three(rows)}")


def unheld_clause(unheld: list) -> str:
    """The clause naming each `submodules:` row whose path no leg holds a
    submodule at, or "" where there is none (#525). A NOTE'S CLAUSE: removing
    a submodule is not wrong, so its row lingering is said and never found.
    """
    if not unheld:
        return ""
    named = first_three([f"{row['path']} (recorded in the "
                         f"{row[RECORDED_LEG]} leg)" for row in unheld])
    return (f"{THE_RECORD} records {len(unheld)} submodule(s) no leg holds "
            f"(#525): {named}; one removed on purpose has its row deleted by "
            "hand, in the pull request that bumps the pins")


def classified(detail: dict, what: str) -> str:
    """`every tracked <what> classifies as the leg it is in`, and `or is
    answered there` where `answered_paths:` answered a question (#525),
    because a path the record placed was not classified by the policy."""
    said = f"every tracked {what} classifies as the leg it is in"
    return f"{said} or is answered there" if detail.get(ANSWERED_PATHS) \
        else said


def recorded_placement(role: str, rule, row: dict) -> dict:
    """A submodule held to the row `project.yaml` records for its path (#189).

    THE RECORD DECIDES, NOT THE POLICY. The row is the adoption plan's answer,
    written into the manifest by `execute`: in that leg the submodule is
    `recorded`, and in the other it is `misplaced`. `rule` is the id of the
    policy rule that names the path, or None, kept so that a reader is told
    which rule the doctor did not apply here either. The row's `resolution`
    travels with it, because it is the human's reason.
    """
    leg = str(row["leg"])
    resolution = row.get("resolution")
    found = {"rule": rule, RECORDED_LEG: leg,
             "resolution": resolution if isinstance(resolution, str) else None}
    if leg == role:
        return {"placement": SUBMODULE_RECORDED, **found,
                "note": (f"a submodule {THE_RECORD} records in the {leg} "
                         "leg, where it is (#189)")}
    return {"placement": SUBMODULE_MISPLACED, **found,
            "note": (f"a submodule {THE_RECORD} records in the {leg} leg, "
                     f"and it is in the {role} leg (#189)")}


def submodule_placement(policy, role: str, path: str,
                        recorded: dict | None = None) -> dict:
    """What the record says about the leg a submodule is in, or failing a
    record, what the policy can say about it, and no more (#189; Codex
    review on #186, round 2).

    A ROW OF `project.yaml`'s `submodules:` NAMING THE PATH DECIDES IT, in
    `recorded_placement`.

    WITHOUT ONE, THE RULE THAT NAMES THE PATH, AND WHICH LEG IT ASSIGNS.
    `rule_for` is the policy's own first-match lookup and nothing else: a
    submodule is judged by no extension majority and no `default`, which read
    what a FILE looks like. A rule that assigns the OTHER leg makes the
    placement `unverifiable`; one that assigns this leg, assigns the root, or
    leaves the leg to a human (`ambiguous`) -- or no rule at all -- leaves it
    `kept`. Neither is a finding: the leg of a submodule is the adoption
    plan's answer under #166, an assembly adopted before the record or a
    submodule added by hand records no such answer, and a gitlink in the
    other leg looks the same whether somebody chose it or nobody did.

    The rule's id is in the result whenever one matched, in every class, so
    that a reader is told which rule the doctor did NOT apply to a submodule.
    """
    rule = policy.rule_for(path)
    name = None if rule is None else str(rule["id"])
    if recorded is not None:
        return recorded_placement(role, name, recorded)
    if rule is None:
        return {"placement": SUBMODULE_KEPT, "rule": None,
                "note": KEPT_SUBMODULE}
    leg = rule["leg"]
    if leg in LEG_ROLES and leg != role:
        return {"placement": SUBMODULE_UNVERIFIABLE, "rule": name,
                "note": (f"a submodule at a path rule `{name}` assigns to "
                         f"the {leg} leg; a submodule's leg is the adoption "
                         "plan's answer and the doctor cannot verify it "
                         "here: confirm against the plan, or move it")}
    return {"placement": SUBMODULE_KEPT, "rule": name,
            "note": (f"{KEPT_SUBMODULE} (rule `{name}` matches its name, and "
                     "the doctor does not apply it to a submodule)")}


def recorded_submodules(adopt, manifest) -> dict:
    """`{path in its leg: row}` for each row of `project.yaml`'s
    `submodules:` a submodule can be held to (#189).

    ONLY A ROW THAT SAYS SOMETHING. A row that is not a mapping, has no text
    `path:`, or names a leg that is not `spec` or `code` decides nothing
    here: the project's own `validate-manifest.py` names each of those, in
    the `manifest` row, and a submodule whose row cannot be read is one no
    record covers. A path spelled as Git records no path (`./x`, `x/`) is
    one the validator names too, and no gitlink is ever at it.

    WHERE TWO ROWS NAME ONE PATH, THE FIRST DECIDES, because the validator
    accepts the first and names the second as `recorded twice` -- the same
    reading, so no row it refuses decides anything here. That holds when it
    refuses the first row's `leg:` as well: the path is that row's, it
    decides nothing, and the second does not stand in for it. `execute`
    writes one row per gitlink, so only an edit makes two, and whichever
    row decides, the `manifest` row is a FINDING and the verdict red.

    Read by the key `adopt-project.py execute` writes, through the module
    this row has already loaded, so that the writer and this reader spell it
    once.
    """
    return recorded_rows((manifest or {}).get(adopt.SUBMODULE_RECORD))


def recorded_answers(adopt, manifest) -> dict:
    """`{path in its leg: row}` for each row of `project.yaml`'s
    `answered_paths:` an answer can be read from (#525): the rows the
    project's own `validate-manifest.py` accepts, read as
    `recorded_submodules` reads its record. A directory's path keeps the one
    `/` the adoption plan wrote it with.
    """
    return recorded_rows((manifest or {}).get(adopt.ANSWER_RECORD))


def recorded_rows(rows) -> dict:
    """`{path: row}` for each row of a record that says something, the
    first of two that name one path deciding: see `recorded_submodules`."""
    record: dict = {}
    claimed: set = set()
    for row in rows if isinstance(rows, list) else []:
        path = row.get("path") if isinstance(row, dict) else None
        if not isinstance(path, str) or path in claimed:
            continue
        claimed.add(path)
        if row.get("leg") in LEG_ROLES:
            record[path] = row
    return record


def misplaced_submodule(item: dict) -> dict:
    """The `misplaced` entry for a submodule in a leg its record does not
    name (#189), in the keys a misplaced FILE's entry carries.

    IN THE SAME LIST, because it is the same claim: a tracked path sits in a
    leg other than the one something asserts it belongs in. So it counts in
    MISPLACED, is an entry under `paths:` in the plan with `leg:` the leg
    recorded, and is resolved the way any entry there is. The record decided
    it and no rule did, so `rule` is null, `confidence` is `recorded`, and
    the reason says where the record is and carries the `resolution:` the
    adoption plan gave, on one line, because it is the human's reason and a
    report or plan line it split would break. `files` is the one gitlink and
    `bytes` is 0, which is what `git ls-tree -l` reports for one.
    `submodule` marks the entry so the row names it apart from the files the
    policy judged.
    """
    leg = item[RECORDED_LEG]
    reason = f"{THE_RECORD} records this submodule in the {leg} leg (#189)"
    if item.get("resolution"):
        reason += ": " + " ".join(str(item["resolution"]).split())
    return {"path": item["path"], "leg": item["leg"],
            "path_in_leg": item["path_in_leg"], "classified_as": leg,
            "rule": None, "reason": reason, "confidence": SUBMODULE_RECORDED,
            "question": None, "files": 1, "bytes": 0,
            "review_required": False,
            "direction": f"{leg} in the {item['leg']} leg",
            AGAINST_THE_RECORD: True}


def placement_row(status: str, reason: str, next_command=None,
                  detail=None, why=None) -> Row:
    """One `placement` row with the `--json` keys ALWAYS present.

    A caller reads `detail.misplaced` and `detail.review_required`; a row that
    omitted them on the `n/a` branches would make every consumer write the
    same `or []` this writes once.

    `submodules` IS THE ONE KEY THAT IS NOT. It is there, with
    `counts.submodules`, only when a leg keeps a submodule (#176), so that the
    report about every project without one stays byte for byte the report it
    was. A caller reads it as `detail.get("submodules") or []`.
    """
    base = {"policy": None, "everywhere": [], "legs": [],
            "misplaced": [], "review_required": [],
            "counts": {"misplaced": 0, "review_required": 0}}
    base.update(detail or {})
    return Row("placement", "placement", status, reason, next_command, base,
               why=why)


def leg_submodules(policy, role: str, rel: str, held: list,
                   record: dict) -> tuple:
    """The submodules one leg keeps, each placed by its record or, with
    none, by what the policy can say; and the `misplaced` entries for those
    in a leg other than the one recorded (#189).

    Split out of `audit_leg`, so that one reads as the walk of a leg's files
    and this as what becomes of the gitlinks set aside from it.
    """
    submodules = [{"path": f"{rel}/{path}", "leg": role,
                   "path_in_leg": path,
                   **submodule_placement(policy, role, path, record.get(path))}
                  for path in held]
    wrong = [misplaced_submodule(item) for item in submodules
             if item["placement"] == SUBMODULE_MISPLACED]
    return submodules, wrong


def gitmodules_the_record_answers(adopt, submodules: list,
                                  unread: list) -> str | None:
    """The leg's own `.gitmodules`, when the record answers the policy's
    question about it, or None (#189).

    `.gitmodules` IS THE POLICY'S ONE QUESTION ABOUT SUBMODULES: rule
    `ambiguous-gitmodules` asks which leg owns the submodules it registers.
    An adoption answered it with the leg of every one of them -- `check`
    refuses a plan that sends `.gitmodules` to one leg and a submodule it
    registers to another (#166) -- and `execute` recorded that leg for each
    submodule it kept. So where the record places EVERY submodule this leg
    keeps in this leg, the answer is in the record, and it is this leg: the
    file is placed, and no question is left.

    EVERY ONE, NOT ANY ONE. Beside a recorded submodule a leg may keep one
    added by hand, which `git submodule add` registers in this same file and
    no row names, or one the record puts in the other leg. The record does
    not say this leg owns that one, so it has not answered the question for
    all the file registers: the file stays the question it was, beside the
    note or the finding that names that submodule, and the row does not say
    the record answered it. So does a leg that keeps no submodule at all.

    AND EVERY NAME IN THE LEG READ (#189's second review, F1). A name no
    report or plan can carry -- a control character, or a byte that is not
    UTF-8 -- is set aside by `leg_tracked_files` before its mode is read, so
    a submodule kept under one is in no list here and no row was held to
    it. `unread` is that residue, and a leg with any of it is not one whose
    every submodule the record is known to place: the file stays the
    question it was.
    """
    if (submodules and not unread
            and all(item["placement"] == SUBMODULE_RECORDED
                    for item in submodules)):
        return adopt.GITMODULES
    return None


def walked_row(found, role: str, rel: str) -> dict:
    """One walked path of a leg, in the keys the row, `--json` and the plan
    carry for it."""
    return {
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


def walked_findings(walked: list, role: str, rel: str,
                    answered: str | None) -> tuple:
    """The walked paths of one leg in the wrong leg, the questions, and the
    paths whose question the record `answered` (#189).

    Split out of `audit_leg`. A path the policy will not call is a question,
    except `answered`: the leg's `.gitmodules` where
    `gitmodules_the_record_answers` finds the answer recorded, and that
    answer is this leg, so it is neither a question nor in the wrong leg.
    """
    misplaced: list = []
    review: list = []
    settled: list = []
    for found in walked:
        row = walked_row(found, role, rel)
        if found.leg is None and found.path == answered:
            settled.append(row["path"])
        elif found.leg is None:
            review.append(row)
        elif found.leg != role:
            misplaced.append(row)
    return misplaced, review, settled


def answered_questions(adopt, review: list, role: str, files: list,
                       answers: dict) -> tuple:
    """`review` -- the leg's questions, or its walked paths in the wrong leg
    (#655) -- less those `answered_paths:` answered into THIS leg; and
    those, as entries of their own (#525).

    A QUESTION IS ANSWERED WHEN EVERY FILE UNDER IT IS. The doctor's walk
    folds a leg's files as they fall in that leg, not as they fell in the
    source the adoption plan was written over, so the question is held to
    the record file by file: each tracked file under it is covered by
    exactly one row -- the path's own, or a directory's above it, as
    `adopt-project.py`'s `_covering` reads an entry -- and that row names
    this leg. A file the record does not cover, or covers twice, leaves the
    question asked.

    A PATH IN THE WRONG LEG IS HELD TO THE RECORD THE SAME WAY (#655). The
    plan may keep a path in a leg its rule does not name, and `execute`
    records that answer as it records a question's: a path whose every file
    one row answers into this leg is the plan's answer, not MISPLACED. Its
    entry keeps the rule and the leg the rule gives (`classified_as`), so
    the reader is told which rule the record answered against.

    A ROW NAMING THE OTHER LEG SETTLES NOTHING AND ASSERTS NOTHING. The
    record confers nothing, and a file in this repository named like one the
    adoption put in the other is not that file, so it stays the question it
    was -- a `note` -- and is never MISPLACED; a path in the wrong leg stays
    MISPLACED, by its rule. Nor is the leg's `.gitmodules` answered here:
    `submodules:` answers it, and only where it places every submodule the
    file registers (`gitmodules_the_record_answers`).

    NO RECORD, NO SCAN (#525). A project with no `answered_paths:` --
    every one adopted before #525 -- returns its questions as they are,
    which is what the loop below would return for them, without holding
    each question against every file of its leg.

    ONE PASS OVER THE LEG'S FILES (#655). Each file is looked up by the
    names `_covering` could find covering it (`_covering_names`), in the
    paths found and in the record, rather than every path found being held
    against every file: called twice, for the questions and for the paths
    in the wrong leg, a leg costs its files times their depth.
    """
    if not answers or not review:
        return review, []
    found = {row["path_in_leg"] for row in review}
    under: dict = {}
    covering: dict = {}
    for path in files:
        names = adopt._covering_names(path)
        for name in names:
            if name in found:
                under.setdefault(name, []).append(path)
                covering[path] = [by for by in names if by in answers]
    still: list = []
    answered: list = []
    for row in review:
        paths = under.get(row["path_in_leg"], [])
        if (row["path_in_leg"] == adopt.GITMODULES or not paths
                or any(len(covering[path]) != 1
                       or answers[covering[path][0]].get("leg") != role
                       for path in paths)):
            still.append(row)
            continue
        by = list(dict.fromkeys(covering[path][0] for path in paths))
        resolution = answers[by[0]].get("resolution")
        answered.append({
            **row, "confidence": SUBMODULE_RECORDED, "review_required": False,
            RECORDED_LEG: role, "answered_by": by,
            "resolution": (resolution if len(by) == 1
                           and isinstance(resolution, str) else None)})
    return still, answered


def empty_gitmodules(adopt, review: list, mount: Path, rel: str,
                     paths: list, held: list) -> tuple:
    """The leg's questions less its `.gitmodules` where that file holds no
    section and the leg no submodule, and that file's path in the row, or
    [] (#655, #914); and each submodule the leg holds beside such a file, as
    its path in the row, or [] (#914).

    AN EMPTY `.gitmodules` REGISTERS NO SUBMODULE, so the question rule
    `ambiguous-gitmodules` asks of it -- which leg owns the submodules it
    registers -- has no subject, and no answer could be wrong. It is what a
    plain `git rm` of a leg's only submodule leaves, tracked; the doctor
    asked it on every run, and no record could answer it: `answered_paths:`
    leaves `.gitmodules` out, and `submodules:` answers it only where the
    leg keeps a submodule. Not asking is the fix, rather than a row a
    person writes by hand into the manifest to quiet a question that has
    no subject, and the row says how to remove it (`empty_clause`).

    EMPTY IS NO SECTION (#914), as `holds_no_section` reads it: no byte, or
    only what git's own config reader passes over -- a byte-order mark,
    blank lines, comments. One that holds a section, even one with no key,
    stays the question it was. Read on this disk, a regular file and not a
    link, as `leg_tracked_files` reads a size: the file git's submodule
    commands read. git refuses to index a `.gitmodules` that is a symlink,
    and reads the index's copy where the disk has none, so neither is the
    empty file.

    BUT NOT BESIDE A SUBMODULE (#914). In a leg that holds a gitlink, a
    `.gitmodules` with no section is no emptied file: it fails to register
    that gitlink, and the question of which leg owns the leg's submodules
    has a subject. So it stays the question it was -- asked, or answered by
    `submodules:` (`gitmodules_the_record_answers`) -- and each gitlink
    `held` is returned to be named with what to do (`unregistered_clause`).
    """
    if adopt.GITMODULES not in paths or not holds_no_section(
            mount / adopt.GITMODULES):
        return review, [], []
    if held:
        return review, [], [f"{rel}/{path}" for path in held]
    for row in review:
        if row["path_in_leg"] == adopt.GITMODULES:
            return [other for other in review if other is not row], [
                row["path"]], []
    return review, [], []


#: The bytes git's config reader passes over before the first line of a file
#: (#914): a UTF-8 byte-order mark, as Windows Notepad writes one. Only the
#: whole mark, and only at the start: git refuses a part of one.
UTF8_BOM = b"\xef\xbb\xbf"
#: What git's config reader counts as blank between the lines it reads
#: (#914): its own `isspace`, which leaves out the vertical tab and the form
#: feed Python's `bytes.strip` would take, and which git refuses.
CONFIG_BLANKS = b" \t\r"
#: The two bytes that open a comment for git's config reader, to the line's
#: end (#914).
CONFIG_COMMENTS = (b"#", b";")


def holds_no_section(path: Path) -> bool:
    """Is `path` a regular file, not a link, that holds no section and no
    key: no byte, or only a byte-order mark, blank lines and comments, which
    git's config reader passes over (#655, #914)?

    git's reader at the top of a file is a loop over bytes: a `\\n` ends a
    comment, a blank is passed over, `#` or `;` opens a comment, and
    anything else opens a section (`[`), opens a key, or is a bad line. So
    a file whose every line, after its blanks, is empty or opens a comment
    holds neither, and `git config --file` lists nothing from it and exits
    0 (measured, git 2.43). A file that cannot be read is not known to be
    empty.
    """
    try:
        found = path.lstat()
        if not stat.S_ISREG(found.st_mode):
            return False
        data = path.read_bytes()
    except OSError:
        return False
    if data.startswith(UTF8_BOM):
        data = data[len(UTF8_BOM):]
    for line in data.split(b"\n"):
        line = line.lstrip(CONFIG_BLANKS)
        if line and not line.startswith(CONFIG_COMMENTS):
            return False
    return True


def unregistered_gitlinks(adopt, mount: Path, rel: str, tracked: list,
                          paths: list, held: list) -> tuple:
    """Each submodule `held` that no section of the leg's `.gitmodules`
    registers, as its path in the row, and what it sits beside, or `([],
    None)` (#1080): a `.gitmodules` whose sections register other paths
    (`BESIDE_OTHER_SECTIONS`), or no `.gitmodules` in the leg's index
    (`BESIDE_NO_GITMODULES`). `tracked` is every path the leg's index
    lists, `paths` its files.

    WHERE THE INDEX TRACKS NO `.gitmodules`, the copy git reads instead is
    read (`registered_unindexed`): the untracked file on this disk, or else
    HEAD's. A submodule it registers is not named, since `git submodule
    status` finds its mapping there and exits 0; one it does not, or every
    one where there is no copy at all, is named beside none.

    NOT WHERE THE INDEX TRACKS A `.gitmodules` THIS DISK LACKS (#1093). git
    reads the index's copy there, and `git submodule status` exits 128
    beside one with no section for the submodule, but this names nothing:
    `git add .gitmodules` would stage the file's deletion, and no section
    can be written in a file that is not there until it is restored.

    ASKED ONLY WHERE `empty_gitmodules` NAMED NONE: beside a `.gitmodules`
    that holds no section, #914's clause names each, and the entry #914
    gives stays as it was.

    IN EACH STATE A RECURSIVE CLONE OF THE LEG exits 0 and leaves the
    submodule's directory empty, and `git submodule status` there exits 128
    with `no submodule mapping found in .gitmodules` (measured, git 2.43).
    A `.gitmodules` the doctor cannot read as git does (`registered_paths`)
    names nothing, as `holds_no_section` calls no such file empty: one that
    is unmerged, that git refuses, or that is not a regular file here (a
    link, which git reads through, or a directory).
    """
    if not held:
        return [], None
    if adopt.GITMODULES not in tracked:
        registered = registered_unindexed(adopt, mount)
        beside = BESIDE_NO_GITMODULES
    else:
        registered = (registered_paths(mount / adopt.GITMODULES)
                      if adopt.GITMODULES in paths else None)
        beside = BESIDE_OTHER_SECTIONS
    if registered is None:
        return [], None
    named = [f"{rel}/{path}" for path in held if path not in registered]
    return named, (beside if named else None)


def registered_unindexed(adopt, mount: Path) -> set | None:
    """The paths registered by the `.gitmodules` git reads in a leg whose
    index tracks none, an empty set where there is none to read, or None
    where git refuses the file on this disk, or that file is not a regular
    one (#1080).

    WHERE GIT READS IT, in the order `gitmodules_entry` reads in (#668):
    git's `config_from_gitmodules` reads the working tree's file when there
    is one, tracked or not, else the index's copy, which there is not here,
    else HEAD's. So the file on this disk is read as `registered_paths`
    reads a tracked one, and one it cannot read names nothing, as there.
    With none on this disk, HEAD's copy is read as `gitmodules_entry` reads
    it, up to its first bad line (`submodule_keys`, #733).

    Measured, git 2.43: beside an untracked file with a section for the
    submodule, and beside HEAD's copy with one once `git rm .gitmodules`
    took the file away, `git submodule status` exits 0; beside either with
    a section for another path, 128.
    """
    disk = mount / adopt.GITMODULES
    if os.path.lexists(disk):
        return registered_paths(disk)
    head = f"HEAD:{adopt.GITMODULES}"
    if git_answer(["rev-parse", "-q", "--verify", head], mount) is None:
        return set()
    listing = gitmodules_listing(mount, ["--blob", head], partial=True)
    keys = (None if listing is None
            else submodule_keys(listing, working_tree=False))
    return None if keys is None else registered_by(keys)


def registered_paths(path: Path) -> set | None:
    """The paths the sections of the `.gitmodules` at `path` register, or
    None where that is not a regular file on this disk, or git refuses it
    (#1080). Read on this disk, as `holds_no_section` reads it: the file
    git's submodule commands read.

    AS GIT READS IT: the last `path` each section gives, of a section git
    does not ignore, and no value git ignores (`submodule_keys`), matched to
    a gitlink's path whole. Measured, git 2.43: `git submodule status`
    exits 128 for `vendor/lib` beside a section that gives `vendor/lib/`,
    one named `a/../b`, or one that gives `vendor/lib` and then `other`, and
    0 beside one that gives `other` and then `vendor/lib`.

    The doctor's one reading of a `.gitmodules` (`gitmodules_listing`,
    #668): `git config --list`, and not `--get-regexp`, whose `.*` matches
    no byte that is not UTF-8 under a UTF-8 locale.
    """
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            return None
    except OSError:
        return None
    listing = gitmodules_listing(path.parent, ["--file", path.name])
    keys = None if listing is None else submodule_keys(listing)
    return None if keys is None else registered_by(keys)


def registered_by(keys: list) -> set:
    """The paths one copy's `submodule_keys` register: the last `path` each
    section gives, as git reads it (#1080)."""
    given = {}
    for name, field, value in keys:
        if field == "path":
            given[name] = value
    return set(given.values())


def unslashed_rows(answers: dict, role: str, rel: str, files: list) -> list:
    """Each `answered_paths:` row for THIS leg whose path is a directory of
    it written without the `/` a directory's row ends with, as its path in
    the row (#655).

    SUCH A ROW ANSWERS NOTHING UNDER IT. `_covering` reads a path without
    its `/` as a file's, as `adopt-project.py check` reads a plan entry,
    where the same spelling is `plan-empty-entry` beside a `plan-uncovered`
    for each file under it. `execute` never writes one, a hand edit does,
    and the project's `validate-manifest.py` cannot tell it from a file's
    row, because it runs where the legs are not checked out. Here the leg
    is read, so it is said. It is never read as the directory's row, which
    would make one spelling name two things, and never a finding.
    """
    rows = [path for path, row in answers.items()
            if row.get("leg") == role and not path.endswith("/")]
    if not rows:
        return []
    directories = {path[:index] for path in files
                   for index, char in enumerate(path) if char == "/"}
    return [f"{rel}/{path}" for path in rows if path in directories]


def slashed_rows(answers: dict, role: str, rel: str, files: list) -> list:
    """Each `answered_paths:` row for THIS leg whose path is a file of it
    written with the `/` a directory's row ends with, as its path in the
    row (#914).

    SUCH A ROW ANSWERS NOTHING: `_covering` reads a path with its `/` as a
    directory's, and no file is under a file. It is `unslashed_rows`' other
    spelling, said the same way and for the same reason, and never read as
    the file's row nor made a finding. `execute` never writes one, since
    `check` finds the plan entry spelled so (`plan-empty-entry`, beside
    `plan-uncovered` for the file); a hand edit does.
    """
    rows = [path for path, row in answers.items()
            if row.get("leg") == role and path.endswith("/")]
    if not rows:
        return []
    named = set(files)
    return [f"{rel}/{path}" for path in rows if path[:-1] in named]


def audit_leg(adopt, policy, patterns: list, role: str, rel: str,
              root: Path, record: dict, answers: dict,
              root_line: str | None = None) -> tuple:
    """ONE leg: its summary, the paths in the wrong leg, the questions, and
    the submodules it keeps.

    Split out so the row above reads as three sentences rather than one loop
    with six ways out of it -- and because a leg that cannot be audited has to
    say WHICH of the reasons it is, beside the legs that could.

    EVERY EARLY RETURN IS A LEG THIS ROW DECLINES TO GUESS ABOUT, and the
    caller must not read any of them as a clean leg: `check_placement` says
    `note` rather than `ok` while one is there, because "every tracked path
    classifies as the leg it is in" is not a claim to make about a leg nobody
    read (Copilot, PR #100).

    A GITLINK IS NEVER HANDED TO `walk()` (#176). `walk` sees paths, not
    modes, so it classifies a submodule as the file its path looks like --
    `.cursor` and `.specify/vendored` as `root` by the 2026-09-02 ruling --
    and folds it into the verdict of the files beside it. But the assembly
    root keeps no submodule but its legs, so a leg is where an adopted one
    lives (#166), and the leg's answer was a human's when it was adopted. So
    every gitlink is taken out before the walk and returned on its own, to be
    named in a `note`; the FILES beside it are walked exactly as before, and
    a file under a root-ruled path is still misplaced.

    A GITLINK IS A PATH WHOSE EVERY STAGE IS ONE, AND IT IS NAMED WHEREVER IT
    IS (Codex review on #186). A path that is a file in one stage and a
    gitlink in another is unmerged with a file in the leg, so it is walked as
    that file. And the submodules are collected from EVERY tracked path,
    before the paths the doctor never judges are set aside -- a submodule at
    `.github/actions` or `LICENSE` is dropped from the walk like a file
    there, and is still one a leg keeps, so it is still named.

    AND EACH ONE IS HELD TO THE ANSWER THE ADOPTION RECORDED, WHERE THERE IS
    ONE (#189). `record` is `recorded_submodules`, and `leg_submodules` holds
    each gitlink to it: a row naming the path makes the submodule `recorded`
    in that leg and `misplaced` in the other, and a
    misplaced one is ALSO returned among the paths in the wrong leg, as
    `misplaced_submodule` words it, and counted in the leg's `misplaced`.
    Where no row names it, it is classified as what the doctor can know of
    it, not judged (Codex review on #186, round 2): `submodule_placement`
    reads the rule the policy names its path by, and a rule that assigns the
    OTHER leg makes it `unverifiable`. That `note` is still a note.

    THE RECORD IS CONSULTED BEFORE THE LEG'S QUESTIONS ARE COUNTED (#189).
    The policy asks which leg owns the submodules a `.gitmodules` registers,
    and in a leg whose every submodule the record places there, and whose
    every name could be read, the record is that answer
    (`gitmodules_the_record_answers`): the file is placed, and the leg's
    entry names it under `answered` instead of as a question.
    Otherwise a real adoption, whose leg always holds the `.gitmodules` that
    registers its submodules, could never read `ok`. One that holds no
    section, in a leg that holds no submodule, asks nothing at all
    (`empty_gitmodules`, #655, #914). A submodule no section registers is
    named, beside sections, or in a leg whose index tracks no `.gitmodules`,
    too (`unregistered_gitlinks`, #1080).

    AND `answered_paths:` IS READ FOR THE QUESTIONS AND FOR THE PATHS IN THE
    WRONG LEG ALIKE (#525, #655): `answered_questions` takes from each those
    the record answers into this leg, which are returned apart,
    `unslashed_rows` names the rows for this leg that name a directory
    without its `/`, and `slashed_rows` those that name a file with one
    (#914).

    AND A LEG'S `single-repository.yaml` IS ASKED THE RECORD'S QUESTION ONLY
    WHERE IT IS THE RECORD (#691). The walk asks it by name; `plan`'s own
    `ask_about_a_record_only` reads the file's `kind:` and gives any other
    the general question. It is called here over the leg's INDEX, which is
    what this row lists, so a file edited or deleted on disk and a link are
    read as `plan` reads them.

    AND A LEG GIT CANNOT READ BECAUSE THE ROOT'S `.git` CANNOT BE READ IS
    GIVEN THE ROOT'S LINE (#1146). `root_line` is `root_git_read`'s, where
    the root's own `.git` cannot be read. A leg whose `.git` is there and
    leads to a repository git names no top level for -- a gitfile naming
    `.git/modules/<leg>` under a root's `.git` this user cannot search --
    keeps it in `gitlink_cannot_be_read` and as its `state`, where git had
    said `it is not a git repository`, a claim about the leg. A leg with a
    repository of its own that git reads is audited as before, and a leg
    with no `.git` of its own is not its own repository whatever the root's
    `.git` says, so it keeps git's answer.
    """
    entry = {"role": role, "path": rel}
    mount = root / rel
    escaped = outside_the_root(root, mount)
    if escaped:
        entry["state"] = escaped
        return entry, [], [], [], []
    populated, own_git, unread = mount_read(root, rel)
    if unread is not None:
        # A leg this user cannot reach, in the gate's words, as the `legs`
        # row says it (#430): a READ that is missing, never a clean leg, and
        # never `it is not a git repository`, which git said of a mount it
        # could not enter.
        entry["state"] = entry[MOUNT_UNREAD] = unread[0]
        return entry, [], [], [], []
    if not populated:
        # The `legs` row already reports this, with `make bootstrap` beside
        # it. Here it is only why this leg has no answer.
        entry["state"] = "not populated"
        return entry, [], [], [], []
    if role not in LEG_ROLES:
        entry["state"] = (f"role {role} is not one that the path policy "
                          "classifies")
        return entry, [], [], [], []
    borrowed = not_its_own_repository(mount)
    if (borrowed == NOT_A_GIT_REPOSITORY and own_git
            and root_line is not None):
        # The root's line, not git's (#1146): see the docstring.
        entry["state"] = entry[GITLINK_UNREAD] = root_line
        return entry, [], [], [], []
    if borrowed:
        entry["state"] = borrowed
        return entry, [], [], [], []
    try:
        files, unwritable, gitlinks = leg_tracked_files(mount)
    except Refusal as exc:
        entry["state"] = f"git could not list it: {exc.detail}"
        return entry, [], [], [], []
    entry["unwritable"] = unwritable
    # Once each, in the index's own order: an unmerged gitlink is listed
    # once per stage, and it is one submodule. From `files` and not from what
    # is left after the `everywhere` patterns below: `.github/**` matches a
    # submodule at `.github/actions` as it matches a file, and a gitlink kept
    # there is no less one a leg keeps.
    held = list(dict.fromkeys(path for path, _ in files
                              if path in gitlinks))
    kept = [(path, size) for path, size in files
            if path not in gitlinks
            and not any(regex.match(path) for regex in patterns)]
    # `plan`'s own `ask_about_a_record_only` (#528, #691), over the leg's
    # INDEX -- `""` is git's `:<path>`, the index `leg_tracked_files`
    # lists -- so a link is read as its blob and never followed.
    walked = adopt.ask_about_a_record_only(
        policy, adopt.walk(policy, kept), adopt.Source(mount, None, "", ""))
    submodules, wrong = leg_submodules(policy, role, rel, held, record)
    answered = gitmodules_the_record_answers(adopt, submodules, unwritable)
    misplaced, review, settled = walked_findings(walked, role, rel, answered)
    paths = [path for path, _ in kept]
    review, empty, unregistered = empty_gitmodules(adopt, review, mount, rel,
                                                   paths, held)
    beside = None
    if not unregistered:
        unregistered, beside = unregistered_gitlinks(
            adopt, mount, rel, [path for path, _ in files], paths, held)
    review, recorded = answered_questions(adopt, review, role, paths, answers)
    misplaced, against = answered_questions(adopt, misplaced, role, paths,
                                            answers)
    misplaced += wrong
    # FILES AND PATHS ARE DIFFERENT NUMBERS and the row prints both. `walk`
    # folds a directory whose files agree into ONE entry, so `src/` with two
    # hundred files under it is one PATH and two hundred FILES -- and a reason
    # that reported only one of them would either bury the size of the problem
    # or overstate the number of decisions in it.
    entry.update({"state": "audited", "tracked": len(files),
                  "classified": len(kept), "paths": len(walked),
                  "misplaced": len(misplaced),
                  "review_required": len(review)})
    for key, said in ((ANSWERED, settled), (EMPTY_GITMODULES, empty),
                      (UNREGISTERED_SUBMODULES, unregistered),
                      (UNREGISTERED_BESIDE, beside),
                      (UNSLASHED, unslashed_rows(answers, role, rel, paths)),
                      (SLASHED, slashed_rows(answers, role, rel, paths))):
        if said:
            # Only when there is one, so that no other leg's entry changes.
            entry[key] = said
    return entry, misplaced, review, submodules, recorded + against


def placement_policy(ctx: Context, policy_path: Path) -> tuple:
    """The adoption's classifier and its loaded policy, or the `n/a` row.

    THREE OF THE FOUR WAYS THIS ROW SAYS `n/a` ARE HERE, and every one of
    them is THIS CHECKOUT being short rather than the repository being wrong:
    an `adopt-project.py` this standard does not carry, a
    `contracts/path-classification.yaml` that is not there, and a policy file
    that is there and could not be read. The last is `n/a` and never a
    finding for the reason the `leg shape files` row is a note -- failing
    somebody else's repository on OUR file being wrong is exactly the mistake
    that row was written about.

    Returns `(adopt, policy, None)` when the legs can be classified at all
    and `(None, None, row)` when they cannot, so the caller returns the
    refusal this composed rather than composing a second one.

    Split out of `check_placement` for #134.
    """
    adopt = ctx.adopt()
    if adopt is None or not policy_path.is_file():
        missing = ("adopt-project.py" if adopt is None
                   else "contracts/path-classification.yaml")
        return None, None, placement_row(
            NA,
            f"this checkout of the standard is missing {missing}, so the "
            "adoption's own classification cannot be run over the legs",
            f"{PYTHON} {quote_arg(ctx.shape / 'shape-doctor.py')} --root "
            f"{quote_arg(ctx.root)}",
            {"policy": policy_path.as_posix()},
            why=f"from a COMPLETE checkout of the standard; this one is "
                f"short {missing}")
    try:
        policy = adopt.PathPolicy.load(policy_path)
    except Refusal as exc:
        # No NEXT: a remedy is prose, and goes in the `why` (#408, #548).
        return None, None, placement_row(
            NA,
            f"the standard's own path policy could not be read: {exc.detail}",
            None, {"policy": policy_path.as_posix()},
            why=remedy_as_why(exc))
    return adopt, policy, None


def leg_audit_summary(entry: dict) -> str:
    """One leg's half of the row's reason: its counts, or why it has none.

    A LEG THAT WAS NOT AUDITED PRINTS ITS `state` AND NEVER A ZERO, because a
    leg nobody could read and a leg with nothing wrong in it are not the same
    answer (Copilot, PR #100) -- `audit_leg` already worded which of the
    reasons it is, and this repeats it rather than flattening it into a
    count. An audited leg names up to three of the tracked names no report or
    plan can carry, because a name that cannot be written down is the one
    thing a reader cannot go and look at for themselves.

    Split out of `check_placement` for #134.
    """
    if MOUNT_UNREAD in entry:
        # The gate's line already starts with the leg's path (#430).
        return entry[MOUNT_UNREAD]
    if GITLINK_UNREAD in entry:
        # The gate's line is about the ROOT's `.git` (#1146), so the leg it
        # kept from being read is named before it.
        return (f"{entry['path']}: read through the root's repository, and "
                f"{entry[GITLINK_UNREAD]}")
    if entry.get("state") != "audited":
        return f"{entry['path']}: {entry.get('state')}"
    counted = (f"{entry['paths']} path(s) over {entry['classified']} of "
               f"{entry['tracked']} tracked file(s)")
    unwritable = entry.get("unwritable")
    if unwritable:
        counted += (f", and {len(unwritable)} name(s) no report or plan "
                    f"can carry: {', '.join(unwritable[:3])}")
    return f"{entry['path']}: {counted}"


def misplaced_clauses(misplaced: list) -> str:
    """What the row says of the paths in the wrong leg: the files the policy
    puts elsewhere, then the submodules the record puts elsewhere (#189).

    SAID APART, because what asserts each is different -- a named rule of the
    path policy, or the leg `project.yaml` records for a submodule -- and a
    reader disagrees with the one that decided. Each clause only when there
    is one, so a project with no submodule gets the sentence it always got.
    """
    held = [row for row in misplaced
            if row.get(AGAINST_THE_RECORD) and not row.get(MOVED)]
    moved = [row for row in misplaced if row.get(MOVED)]
    files = [row for row in misplaced if not row.get(AGAINST_THE_RECORD)]
    clauses = []
    if files:
        clauses.append(f"{len(files)} path(s) sit in a leg the policy puts "
                       f"elsewhere: {named_offenders(files)}")
    if held:
        clauses.append(f"{len(held)} submodule(s) sit in a leg other than "
                       f"the one {THE_RECORD} records for them (#189): "
                       f"{named_against_the_record(held)}")
    if moved:
        clauses.append(f"{len(moved)} submodule(s) moved out of the leg "
                       f"{THE_RECORD} records for them, which no longer "
                       f"holds them (#525): {named_against_the_record(moved)}")
    return "; ".join(clauses)


def submodules_verdict(detail: dict, audited: str) -> Row:
    """The row when the legs keep submodules and nothing else is to say.

    `ok` ONLY WHEN THE RECORD PLACES EVERY ONE (#189). A submodule in the leg
    `project.yaml`'s `submodules:` records for it is checked and placed, so
    it does not keep the row off `ok`; the reason says "every tracked FILE",
    because the policy classified the files and the record placed the
    gitlinks, and the clause beside it names those -- and names a leg's
    `.gitmodules` too, where the policy's question about it is the one the
    record answered. One that no record names is the `note` it has been
    since #176: the doctor did not check it.
    """
    kept = detail["submodules"]
    held = held_clauses(detail)
    if (all(item["placement"] == SUBMODULE_RECORDED for item in kept)
            and not detail.get(UNHELD)):
        return placement_row(
            OK, f"{classified(detail, 'file')}{held}  [{audited}]", None,
            detail)
    return placement_row(
        NOTE, f"nothing is in the wrong leg{held}  [{audited}]", None, detail)


def placement_verdict(detail: dict, audited: str, plan: str,
                      plan_why: str) -> Row:
    """What the audited legs add up to, in the order the answers outrank.

    A PATH IN THE WRONG LEG OUTRANKS A QUESTION ABOUT ONE. Misplaced first
    because it is the finding the row exists for; then the paths the policy
    will not call, which are a note because an unanswered question is never a
    finding and never an implicit anything; then the legs that could not be
    read, which are a note because what is missing is a READ and not a fault
    of this repository's; then the submodules the legs keep, which are a note
    where no record names them, because nothing is wrong with them (#176),
    and `ok` where the record places them all (#189). `ok` is last and is
    the only branch that claims every tracked path was classified or placed,
    which is why nothing above it may fall through to it.

    A SUBMODULE THE RECORD PUTS IN THE OTHER LEG IS A PATH IN THE WRONG LEG
    (#189): it is in `misplaced`, it makes this row a FINDING, and the verdict
    MISPLACED, because `project.yaml` asserts where it belongs. And a leg's
    `.gitmodules` whose question the record answered is not in `review`
    (`audit_leg`), so it no longer holds the row of an adoption at `note`.

    ANY OTHER SUBMODULE NEVER MOVES THIS ROW ON ITS OWN ACCOUNT. Beside a
    misplaced path or a question it adds one clause per class to the
    sentence those already make. On its own, one in its recorded leg leaves
    the row `ok`, and one no record names is the `note` that keeps the row
    off `ok`: a gitlink is a tracked path the policy did not classify, so
    "every tracked path classifies as the leg it is in" would not be true of
    it. That holds for the `unverifiable` class too, which names the rule and
    asks for a human's look (Codex review on #186, round 2): it is not
    MISPLACED, because a person adopting under #166 may have answered that
    leg, and with no record the doctor cannot tell that answer from none. Its
    `next` is the plan's only where a misplaced path or a question already
    offers one, because the confirmation it asks for is against the ADOPTION
    plan, a document this row cannot name.

    Reads what it needs out of `detail` rather than taking the same six
    numbers a second time: the row prints that dictionary, so a count this
    judged on and a count the reader is shown cannot drift apart. `plan` is
    the `--placement-plan` command and `plan_why` what it does, which travel
    together onto every row that offers the plan (#277).

    Split out of `check_placement` for #134.
    """
    misplaced = detail["misplaced"]
    review = detail["review_required"]
    counts = detail["counts"]
    kept = detail.get("submodules") or []
    held = held_clauses(detail)
    if counts["unread_legs"] == len(detail["legs"]):
        # NOT `ok` AND NOT A FINDING. Every leg declined for a reason the
        # `legs` row already asserts or the manifest already carries, and a
        # row that answered `ok` here would be answering about nothing.
        return placement_row(
            NA, f"no leg could be read, so nothing was classified: {audited}",
            None, detail)
    if misplaced:
        extra = (f"; {len(review)} more path(s) need a human's reading"
                 if review else "")
        return placement_row(
            FINDING, f"{misplaced_clauses(misplaced)}{extra}{held}  "
            f"[{audited}]",
            plan, detail, plan_why)
    if review:
        return placement_row(
            NOTE,
            f"nothing is in the wrong leg; {len(review)} path(s) the policy "
            f"will not call: {named_offenders(review)}{held}  [{audited}]",
            plan, detail, plan_why)
    if counts["unread_legs"] or counts["unwritable_names"]:
        # `note`, because what is missing is a READ and not a fault of this
        # repository's -- and never `ok`, because "every tracked path
        # classifies as the leg it is in" is a claim about paths nobody read.
        said = ("nothing is in the wrong leg in what could be read, and not "
                "everything could be")
        return placement_row(
            NOTE,
            f"{said}{held}  [{audited}]" if held else f"{said}: {audited}",
            None, detail)
    if kept:
        return submodules_verdict(detail, audited)
    if detail.get(UNHELD):
        # A row no leg holds is a `note` (#525): said, never found.
        return placement_row(
            NOTE, f"nothing is in the wrong leg{held}  [{audited}]", None,
            detail)
    if held:
        return placement_row(
            OK, f"{classified(detail, 'path')}{held}  [{audited}]", None,
            detail)
    return placement_row(
        OK, f"every tracked path classifies as the leg it is in: {audited}",
        None, detail)


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

    FOUR THINGS ARE COUNTED AND THEY ARE NOT THE SAME THING. A path the
    policy classifies as the OTHER leg is a FINDING: code in the spec leg,
    spec in the code leg. So is one it classifies as `root` -- `.specify/`
    inside a leg is the 2026-09-02 ruling's exact counter-example -- minus
    what belongs to every repository, which is `everywhere_patterns` and is
    printed. A path the policy cannot CALL carries `review_required` and is a
    `note`: it is a question for a human, and this standard's rule is that an
    unanswered question is never a finding and never an implicit anything.
    And a SUBMODULE a leg keeps is classified by no rule (#176): the policy
    reads names, a gitlink is not the file its name looks like, and the
    assembly root keeps no source submodule (#166). It is held instead to
    the leg `project.yaml`'s `submodules:` records for it, which
    `adopt-project.py execute` writes from the adoption plan's answer
    (#189): in that leg it is placed, and in the other it is a FINDING like
    any path in the wrong leg.
    One no record names is a `note` naming it, which says which of two it
    is: `kept`, or `unverifiable` when a rule assigns the path to the other
    leg and so the doctor cannot confirm the adoption plan's answer.

    AND NOTHING MOVES. The row's next command writes a plan; the plan is the
    human's to resolve and a later `--fix` is the thing that would carry it
    out. A row that offered a `git mv` would be offering to edit two
    repositories from a command documented as writing nothing.

    THE REFUSALS ARE `placement_policy`'s, ONE LEG IS `audit_leg`'s, THE
    WORDING IS `leg_audit_summary`'s AND THE ANSWER IS `placement_verdict`'s,
    so that this reads as the three sentences it is: load the policy, audit
    every leg with it, and say what the legs came to.
    """
    if ctx.kind == FAMILY:
        return placement_row(
            NA,
            "a family holder has no legs of its own: each member is an "
            "assembly root and answers this in its own report")
    # Before the sentence below, which is about a project that declares no
    # leg, not one whose manifest nobody could read (#205), nor one whose
    # `legs:` names no leg that can be read (#832). And `n/a` is what makes
    # `--placement-plan` refuse by name and write nothing: there is no leg to
    # write a plan about until the manifest loads and names one.
    needs = "there is no leg to classify a path in"
    waiting = (waiting_row(ctx, "placement", "placement", needs)
               or legs_unread_row(ctx, "placement", "placement", needs))
    if waiting is not None:
        return placement_row(NA, waiting.reason, None, waiting.detail)
    legs = ctx.legs()
    if not legs:
        return placement_row(
            NA,
            "project.yaml declares no non-assembly leg, so there is no leg "
            "for a path to be in the wrong one of")
    # THE ROOT'S OWN `.git` MAY NOT BE READ (#1146). A leg's repository is
    # read through it, under `.git/modules/`, and git said `it is not a git
    # repository` of each such leg, a claim about the leg: `audit_leg` gives
    # those legs the root's line, and audits every leg whose repository git
    # reads without it, as it always did.
    root_unread = root_git_read(ctx.root)
    root_line = root_unread[0] if root_unread is not None else None
    policy_path = ctx.shape / "contracts" / "path-classification.yaml"
    adopt, policy, refusal = placement_policy(ctx, policy_path)
    if refusal is not None:
        return refusal

    ignored = everywhere_patterns(ctx.shape)
    patterns = [glob_to_regex(pattern) for pattern in ignored]
    record = recorded_submodules(adopt, ctx.manifest)
    answers = recorded_answers(adopt, ctx.manifest)
    per_leg = []
    misplaced = []
    review = []
    submodules = []
    answered = []
    for leg in legs:
        role = str(leg.get("role") or "?")
        rel = str(leg.get("path") or role)
        entry, wrong, unsure, held, recorded = audit_leg(
            adopt, policy, patterns, role, rel, ctx.root, record, answers,
            root_line)
        per_leg.append(entry)
        misplaced.extend(wrong)
        review.extend(unsure)
        submodules.extend(held)
        answered.extend(recorded)

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
    if submodules:
        # Only when there is one: see `placement_row`.
        detail["submodules"] = submodules
        detail["counts"]["submodules"] = len(submodules)
    unheld = moved_and_unheld(per_leg, submodules, misplaced, record)
    for key, found in ((ANSWERED_PATHS, answered), (UNHELD, unheld)):
        if found:
            # Only when there is one, as `submodules` is (#525).
            detail[key] = found
            detail["counts"][key] = len(found)
    if root_line is not None and all(GITLINK_UNREAD in entry
                                     for entry in per_leg):
        # NO LEG WAS READ, FOR THE ONE REASON (#1146): said once, as the
        # `legs` row says it, and `n/a`, as for a row with no leg it read.
        return placement_row(
            NA, f"{root_line}, so no leg's tracked paths are read and "
            "nothing was classified", None, detail)
    audited = "; ".join(leg_audit_summary(entry) for entry in per_leg)
    if moved_alone(adopt, detail):
        # No command makes either way out of a move already made (#525):
        # the NEXT is this doctor again, as `unreadable_next`'s is.
        return placement_verdict(
            detail, audited,
            f"{PYTHON} {quote_arg(ctx.shape / 'shape-doctor.py')} --root "
            f"{quote_arg(ctx.root)}", MOVED_BY_HAND)
    plan = (f"{PYTHON} {quote_arg(ctx.shape / 'shape-doctor.py')} --root "
            f"{quote_arg(ctx.root)} "
            "--placement-plan placement-plan.yaml")
    return placement_verdict(
        detail, audited, plan,
        "writes the paths above as a plan to resolve by hand. Moving one is "
        "a pull request on each leg and a pin bump in the root, so this "
        "command makes neither")


def moved_and_unheld(per_leg: list, submodules: list, misplaced: list,
                     record: dict) -> list:
    """Mark each misplaced submodule whose recorded leg no longer holds it
    as `moved`, and return the `submodules:` rows no leg holds (#525).

    A MOVE ALREADY MADE. A submodule in the leg its row does not name, where
    the leg the row does name was read and holds no gitlink at that path,
    has changed legs: the pull request on each leg and the pin bump in the
    root are done, and only the row is left. It is still MISPLACED -- the
    manifest asserts the other leg -- and its row is a person's to change.
    Where that leg was not read, nobody can say, and it is MISPLACED as any
    submodule against its record is.

    A ROW NO LEG HOLDS. A submodule removed since the adoption leaves its
    row, and one added at that path later would be judged by it. Removing a
    submodule is not wrong, so this is a `note` and never a finding, and
    only where EVERY leg was read: a leg that was not could hold it. A
    recorded name no report can carry is read no further, as
    `leg_tracked_files` reads none.
    """
    read = {entry["role"] for entry in per_leg
            if entry.get("state") == "audited"}
    held = {(item["leg"], item["path_in_leg"]) for item in submodules}
    for row in misplaced:
        if (row.get(AGAINST_THE_RECORD) and row["classified_as"] in read
                and (row["classified_as"], row["path_in_leg"]) not in held):
            row[MOVED] = True
    if len(read) < len(per_leg):
        return []
    holding = {path for _, path in held}
    return [{"path": path, RECORDED_LEG: str(row["leg"]),
             "resolution": (row.get("resolution")
                            if isinstance(row.get("resolution"), str)
                            else None)}
            for path, row in record.items()
            if path not in holding and not UNWRITABLE_IN_A_PLAN.search(path)]


def moved_alone(adopt, detail: dict) -> bool:
    """Is every path the row lists a submodule moved since the adoption, or
    the `.gitmodules` of a leg the move went into or emptied (#525)?

    THEN NO PLAN IS THE WAY OUT. The `--placement-plan` writes the paths to
    move, and these have moved: what is left is the row in `project.yaml`,
    a person's to change, or a move back. A leg's `.gitmodules` that
    registers what moved in is the policy's question only because the row
    still names the other leg, so it goes with the move -- where every
    submodule that leg keeps is recorded there or moved in, and every name
    in it could be read. So does the `.gitmodules` left in the leg a moved
    submodule LEFT, where that leg now keeps no submodule at all (#525); the
    empty one a plain `git rm` leaves there is no question at all (#655).
    Anything else in the wrong leg, or asked, keeps the plan as the NEXT.
    """
    misplaced = detail["misplaced"]
    if not misplaced or not all(row.get(MOVED) for row in misplaced):
        return False
    moved = {row["path"] for row in misplaced}
    left = {row["classified_as"] for row in misplaced}
    kept = detail.get("submodules") or []
    for question in detail["review_required"]:
        role = question["leg"]
        leg = next(entry for entry in detail["legs"] if entry["role"] == role)
        went = any(path.startswith(f"{leg['path']}/") for path in moved)
        emptied = role in left and not any(item["leg"] == role
                                           for item in kept)
        if (question["path_in_leg"] != adopt.GITMODULES
                or leg.get("unwritable")
                or not (went or emptied)
                or any(item["leg"] == role
                       and item["placement"] != SUBMODULE_RECORDED
                       and item["path"] not in moved
                       for item in kept)):
            return False
    return True


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


def placement_plan_header(ctx: Context, adopt) -> list:
    """The plan's first block: what it is, what wrote it, and about what.

    `kind:` IS THE SAFETY PROPERTY AND IT IS WRITTEN HERE. It is
    `adopt.PLACEMENT_PLAN_KIND` and not `adopt.PLAN_KIND`, which is what stops
    `adopt-project.py execute` -- a command that creates two repositories and
    rewrites history -- from ever being handed one of these by mistake. The
    preamble that follows it is the file's own argument to the human who will
    edit it, and it is a constant because it is read far more often than it is
    written.

    The `standard` and `generated_on` lines say which checkout answered and
    when, so a plan found in a branch months later is readable as evidence
    rather than as an assertion about today.

    Split out of `placement_plan_text` for #134.
    """
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
    return lines


def placement_plan_leg(adopt, leg: dict) -> list:
    """ONE leg under `legs:`: what was read in it, or that it was not read.

    THE COUNTS ARE HERE SO THE `paths:` BELOW CAN BE READ HONESTLY: a plan
    with two entries in it means something different over a leg whose every
    tracked file was classified than over one nobody could open, and a reader
    holding only the entries cannot tell those apart.

    A tracked name no plan can carry is written as a COMMENT and never as a
    value: it is already a `repr`, and its newlines are flattened here as
    well, because a name that split one entry across two lines is the defect
    this whole branch exists to avoid -- the plan it is kept out of must still
    parse.

    Split out of `placement_plan_text` for #134.
    """
    lines = [f"  - role: {adopt.y(leg.get('role'))}"]
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
    return lines


def placement_plan_entry(adopt, entry: dict) -> list:
    """ONE path under `paths:`, in an adoption plan entry's keys exactly.

    THE KEYS ARE THE ADOPTION'S, WHICH IS WHAT MAKES "resolve it as you
    resolve an adoption plan" TRUE: `adopt-project.py`'s own reader is handed
    these entries with nothing changed but the `kind:` above them. `rule:`
    travels with the entry so a human disagrees with a NAMED rule rather than
    with an opaque verdict, `question:` only when the policy asked one, and
    `resolution:` is emitted empty on every entry because it is the human's
    line and a file that did not offer it would not look like one to fill in.

    Split out of `placement_plan_text` for #134.
    """
    lines = [f"  - path: {adopt.y(entry['path'])}"]
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
    return lines


def placement_plan_paths(adopt, entries: list, unread: list) -> list:
    """The `paths:` block: the entries to resolve, or why there are none.

    AN EMPTY PLAN SAYS WHAT ITS EMPTINESS MEANS. `paths: []` over a project
    whose every leg was read is a clean bill of health; the same two words
    over a project whose legs could not be opened is a report about nothing,
    and this names the count of unread legs so the difference cannot be read
    the wrong way round. Written as a comment beside a list the reader's tools
    still parse, because the emptiness has to survive being loaded as YAML.

    Split out of `placement_plan_text` for #134.
    """
    if not entries:
        lines = ["",
                 "# Nothing is in the wrong leg and nothing needs a reading",
                 "# IN WHAT WAS READ: there is nothing here to resolve."]
        if unread:
            lines += ["# The `legs:` block above names "
                      f"{len(unread)} leg(s) that could not be read at all,",
                      "# so this emptiness is not a clean bill of health for "
                      "them."]
        lines.append("paths: []")
        return lines
    lines = ["", "paths:"]
    for entry in entries:
        lines += placement_plan_entry(adopt, entry)
    return lines


#: The comment above the plan's `submodules:` block where no record names
#: any of them (#176; Codex review on #186, round 2).
UNRECORDED_LEGEND = (
    "# Kept in a leg and NOT JUDGED: a submodule is a gitlink, which",
    "# the path policy cannot tell from a file of the same name, and",
    "# the assembly root keeps no source submodule (#166). Nothing",
    "# here is to resolve, and no entry under `paths:` covers one.",
    "# `placement: unverifiable` is a submodule at a path a rule",
    "# assigns to the OTHER leg: its leg is the adoption plan's",
    "# answer, which the doctor cannot verify here, so confirm it",
    "# against the plan, or move it.",
)

#: The same comment where `project.yaml`'s `submodules:` names at least one
#: of them (#189). A misplaced one is under `paths:` too, so this does not
#: say that none is.
RECORDED_LEGEND = (
    "# Kept in a leg, and judged by NO RULE: a submodule is a gitlink,",
    "# which the path policy cannot tell from a file of the same name,",
    "# and the assembly root keeps no source submodule (#166).",
    "# `placement: recorded` is a submodule in the leg project.yaml's",
    "# `submodules:` records for it (`recorded_leg:`), the answer the",
    "# adoption plan gave (#189): placed, and nothing to resolve.",
    "# `placement: misplaced` is one in the OTHER leg from the one",
    "# recorded: it is an entry under `paths:` as well, resolved like",
    "# any there. `placement: kept` is one no record names, which a",
    "# leg holds; `placement: unverifiable` is one no record names at a",
    "# path a rule assigns to the OTHER leg, so confirm it against the",
    "# adoption plan, or move it.",
)


def placement_plan_submodules(adopt, kept: list) -> list:
    """The `submodules:` block: what the legs keep and nobody is asked about.

    A NOTE PER SUBMODULE, AND NOT THE ADOPTION'S QUESTION (#176). Which leg
    owns a submodule is asked when a repository is adopted -- the
    `ambiguous-gitmodules` question, on every entry that holds a gitlink --
    and the leg it is in is the answer somebody gave. This file is for a
    project already split, and an entry under `paths:` is a path a human
    resolves: a submodule there would be an answered question put back on
    every run, asked in the words of the policy's `default`, which offer
    `root` -- the one answer a submodule cannot take. So a kept submodule is
    no entry under `paths:`, and is listed here with the leg it is in and why
    it was not judged, because what a report declined to judge belongs in the
    report.

    EACH ONE CARRIES THE CLASS THE ROW GAVE IT (Codex review on #186, round
    2): `placement: kept`, or `placement: unverifiable` where a rule assigns
    its path to the other leg, with `rule:` -- the id, or null where none
    matched. `unverifiable` is not a question either: it is the doctor saying
    it cannot check the answer the adoption plan gave, so the file carries
    the instruction and nothing to fill in.

    A SUBMODULE `project.yaml` RECORDS IS LISTED WITH THE LEG RECORDED (#189):
    `placement: recorded` in that leg, `placement: misplaced` in the other,
    each with `recorded_leg:`. A misplaced one is ALSO an entry under
    `paths:`, because it is a path in the wrong leg, and the comment above
    the block says so only where a record names one -- the comment a plan
    with no record gets is #186's, word for word.

    NOTHING AT ALL WHEN NO LEG KEEPS ONE, so the plan of every project
    without a submodule is the file it always was.
    """
    if not kept:
        return []
    recorded = any(RECORDED_LEG in item for item in kept)
    lines = ["", *(RECORDED_LEGEND if recorded else UNRECORDED_LEGEND),
             "submodules:"]
    for item in kept:
        lines.append(f"  - path: {adopt.y(item['path'])}")
        adopt.emit(lines, "in_leg", item["leg"], 4)
        adopt.emit(lines, "placement", item["placement"], 4)
        if RECORDED_LEG in item:
            adopt.emit(lines, RECORDED_LEG, item[RECORDED_LEG], 4)
        adopt.emit(lines, "rule", item["rule"], 4)
        adopt.emit(lines, "note", item["note"], 4)
    return lines


def placement_plan_text(ctx: Context, adopt, row: Row) -> str:
    """The placement row's paths, as the YAML a human resolves.

    WRITTEN WITH THE ADOPTION'S OWN EMITTERS. `y` and `emit` write the exact
    subset `repo_shape.parse_yaml` reads back, and an adoption plan is written
    by them too -- so these two files are the same dialect by construction
    rather than by somebody remembering to keep them so.

    THE FILE IS FOUR BLOCKS AND EACH ONE IS COMPOSED BY ITS OWN FUNCTION --
    the header, the legs, the paths and what was never judged, with a fifth,
    the submodules the legs keep, between the last two when there are any
    (#176) -- so that this
    reads as the shape of the file it writes rather than as one run of
    appends in which a reader has to count indents to find out which block
    they are in.
    """
    detail = row.detail
    entries = sorted(list(detail.get("misplaced") or [])
                     + list(detail.get("review_required") or []),
                     key=lambda entry: entry["path"])
    lines = placement_plan_header(ctx, adopt)
    lines += ["", "legs:"]
    for leg in (detail.get("legs") or []):
        lines += placement_plan_leg(adopt, leg)
    unread = [leg.get("path") for leg in (detail.get("legs") or [])
              if leg.get("state") != "audited"]
    lines += placement_plan_paths(adopt, entries, unread)
    lines += placement_plan_submodules(adopt, detail.get("submodules") or [])
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
    # A `files:` that is not a list pins nothing, as a pin that is not a
    # mapping pins nothing (#290): `files: 5` was iterated, a TypeError. The
    # shape-currency row is where that pin is reported.
    rows = pin.get("files")
    if not isinstance(rows, list):
        return set()
    return {str(row.get("path")) for row in rows
            if isinstance(row, dict) and row.get("path")}


#: Named once, like `LABEL_MANIFEST_KINDS` above: this function's two returns
#: and the `CHECKS` entry below must all print the same row name.
LABEL_AGENT_FILES = "agent files"


def confirm_digest(ctx: Context) -> str:
    """The end of the `agent-files` WHY for a pinned copy that is gone: what
    confirms its digest once it is back (#776).

    THE GATE IS THE ROOT KIND'S, as the validator rows have it: an assembly
    root's `validate-pins.py` (`PINS_GATE`), a family holder's
    `validate-family.py` (`FAMILY_GATE`), the root's own copy else the
    standard's template copy, named as the validator rows name it
    (`gate_line`). The row runs in both kinds of root, and a holder has no
    `validate-pins.py`: the assembly-root gate refuses there with a remedy
    that names a file the holder lacks.

    The sentence used to name the assembly root's own copy whether or not the
    root had one, and where the root has lost the `scripts/repo_shape.py`
    that copy imports from beside itself it died on `ModuleNotFoundError` and
    exited 1, as the validator row says. So there the sentence is #737's: put
    the file back first, with the cure `lost_repo_shape_cure` gives that row,
    or, where HEAD does not hold it, why no command does, and the gate after.
    Where the template copy is named because the root has none of its own, it
    also reports that missing copy where the pin has a row for it, and exits
    1, which the sentence says. Where no line can be named (`gate_line`)
    nothing is said of a gate. Everywhere else it is, byte for byte, what it
    was.
    """
    gate = FAMILY_GATE if ctx.kind == FAMILY else PINS_GATE
    used, own_copy, command = gate_line(ctx, gate)
    if command is None:
        return ""
    if own_copy and not imports_repo_shape(ctx.shape, used, own_copy):
        cure, why = lost_repo_shape_cure(
            ctx, gate[0], repo_shape_for(ctx.shape, used, own_copy), command,
            again=False, purpose=", to confirm the digest")
        return ". " + (f"First `{cure}`: {why}" if cure else why)
    said = f", then `{command}` to confirm the digest"
    if not own_copy and gate[0] in pinned_paths(ctx.root):
        said += (f". Until {gate[0]} is back that exits 1, reporting the "
                 "file as pinned but absent")
    return said


def check_agent_files(ctx: Context) -> Row:
    present = {name: (ctx.root / name).is_file() for name in AGENT_FILES}
    absent = [name for name, there in present.items() if not there]
    detail = {"files": present}
    if not absent:
        return Row("agent-files", LABEL_AGENT_FILES, OK,
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
    # Each branch is the COMMAND and, apart from it, the sentence that says
    # why it is that command (#277).
    if detail["pinned"]:
        first = detail["pinned"][0]
        fix = (f"git -C {quote_arg(ctx.root)} checkout -- "
               f"{quote_arg(first)}")
        why = ("the pin has a "
               "`files:` row for it, so it was deleted rather than never "
               "copied; restore it from this repository's own history"
               + confirm_digest(ctx))
    elif "AGENTS-shape.md" in absent:
        fix = (f"{PYTHON} {quote_arg(ctx.shape / 'update-shape.py')} "
               f"check --root {quote_arg(ctx.root)} --upstream "
               f"{quote_arg(ctx.shape)}")
        why = ("no pin row names it, "
               "so it is reported upstream-added and taken, on the human's "
               "word, with `apply --add AGENTS-shape.md`")
    else:
        fix = (f"{PYTHON} {quote_arg(ctx.shape / 'scaffold-project.py')} "
               "--help")
        why = (f"{' and '.join(absent)} is RENDERED per project, "
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
    return Row("agent-files", LABEL_AGENT_FILES, status,
               "absent: " + ", ".join(absent), fix, detail, why=why)


def detached(path: Path, git_dir: Path | None = None) -> bool | None:
    """Is this checkout on a detached HEAD? None when git cannot say.

    `symbolic-ref -q HEAD` succeeds with a branch name and exits 1 when HEAD
    is detached, which is the one question with no ambiguity in it. Any
    other exit is git unable to answer, not an answer: it was read as
    "detached".

    `git_dir` asks it of a repository git KEPT for a mount with no `.git` of
    its own, through `--git-dir`, with `path` as the work tree (`kept_head`):
    asked in such a mount, git walks up and answers about the root (#413).
    """
    if git_dir is None and not (path / ".git").exists():
        return None
    where = ([] if git_dir is None
             else [f"--git-dir={git_dir}", f"--work-tree={path}"])
    proc = subprocess.run(["git", *where, "symbolic-ref", "-q", "HEAD"],
                          cwd=str(path), capture_output=True, check=False)
    if proc.returncode not in (0, 1):
        return None
    return proc.returncode == 1


def is_this_member(manifest: object, row: dict) -> bool:
    """Does the `project.yaml` of the clone beside the holder, as
    `Context._read` gave it, CLAIM to be this member?

    READ ONCE, BY `working_clone`, which asks `verify_sibling`'s `id`
    question of the same reading first, and asks this only of a directory
    with a `.git` of its own (#669).

    `scripts/siblings.py::verify_sibling` asks this before it will touch a
    directory, and for the same reason: a repository that happens to sit at
    `../<Project>` is somebody else's, and a report that counted it would
    tell a person their working clone is there when it is not (Copilot, PR
    #96). The manifest's `id` is the identity `validate-family.py` already
    checks the MOUNT by, so it is the one asked here too.

    HALF THE QUESTION, AND IT SAYS SO NOW. `verify_sibling` asks a second
    one -- is this clone's `origin` the remote the row names -- and refuses
    on it FIRST, as `WRONG ORIGIN`, so a fork or a stale clone of a renamed
    repository carries exactly this manifest and is still not the working
    clone. `working_clone` below puts the two back together (#146).
    """
    if not isinstance(manifest, dict):
        return False
    if manifest.get("kind") != "project-manifest":
        return False
    wanted = row.get("id")
    if wanted:
        return str(manifest.get("id")) == str(wanted)
    return str(manifest.get("name")) == str(row.get("project"))


def origin_url(path: Path) -> str:
    """`origin`'s url for the repository AT `path`, or `""`.

    READ ONLY, AND NEVER A FETCH, like every other question this file asks of
    a checkout it did not make: `remote get-url` reads `.git/config` and
    talks to nothing.

    THE `.git` GUARD IS THE POINT. `git remote get-url` run in a directory
    that has no repository of its own walks UP to the nearest ancestor and
    answers about THAT one -- the trap `repo_local_origin_name` guards the
    naming row against, and it is worse here, where the ancestor of
    `../<Project>` is often the family's own workspace and the answer would
    be the HOLDER'S origin, which every member row would then match.

    THE EMPTY STRING WHEN GIT WILL NOT ANSWER -- a clone with no `origin`, a
    dangling `.git` file left behind by a copied submodule -- because that is
    a directory this report cannot identify, and `same_repository` matches it
    against nothing. `scripts/siblings.py` calls the same state
    `(no origin)` and refuses to fetch into it.

    BOTH THE SIBLING AND THE HOLDER are asked this: the holder's own remote
    is what a relative submodule url is resolved against.

    AND IT IS READ AS `make siblings` READS IT: a byte that is not UTF-8 is
    replaced, which is `siblings.py::git_text`'s `errors="replace"` (#385).
    git keeps a URL as the bytes it was given, so a clone of a mirror under
    a directory named in a legacy code page has one, and read strictly it
    ended this report in a `UnicodeDecodeError` traceback. It is NOT the
    empty string: `verify_sibling` accepts `<dir>/caf\\ufffd/Org/Repo.git`
    as the member's clone by the row's `repository: Org/Repo` tail, so
    `""` here would call the clone `make siblings` fetches into `(no
    origin)` and no working clone -- the two tools disagreeing about one
    directory, which `working_clone` exists to prevent (#146). A URL that
    matches nothing is quoted with the replacement, and a row prints it as
    `?`.
    """
    if not (path / ".git").exists():
        return ""
    try:
        raw = git_out(["remote", "get-url", "origin"], cwd=path, binary=True)
    except (Refusal, OSError):
        return ""
    return raw.decode("utf-8", "replace").strip()


def submodule_config(root: Path) -> dict:
    """`{submodule name: {field: value}}` out of the holder's `.gitmodules`:
    each section's `path` and `url`, the later value winning as git reads
    the file.

    GIT'S OWN PARSER, never a reader of this file's own: `.gitmodules` is
    config syntax, it ESCAPES a backslash on the way in -- a Windows path is
    stored `D:\\\\a\\\\...` -- and reading it as text is how a report ends up
    quoting a url nobody has.

    THE WORKING TREE'S FILE ALONE, as `make siblings` reads it, and read as
    `gitmodules_entry` reads each copy git reads: `gitmodules_listing`
    (#668). The `--get-regexp` listing this split at the first space and at
    every line break `str.splitlines` knows read a section named `members/My
    IRRS`, or a url holding NEL or U+2028, as no url or one cut short, and
    under a UTF-8 locale it held no section whose name is not UTF-8. The
    member's clone beside the holder was then a stranger, and `make
    siblings` fetches into it.

    AND IT IS READ AS `make siblings` READS IT: a byte that is not UTF-8 is
    replaced, which is `siblings.py::submodule_urls`'s `errors="replace"`
    over the same file (#432), and the decode `origin_url` makes of the
    holder's own remote (#385). git keeps a url as the bytes it was given,
    so a member mounted from a directory named in a legacy code page, or a
    hand-edited `.gitmodules`, has one that is not text, and read through
    `git_out`'s strict decode it raised a `UnicodeDecodeError` that the
    `except` there did not name -- it is a `ValueError`, neither a
    `Refusal` nor an `OSError` -- so `--root` ended in a traceback, exit 1,
    which is also the code of a finding, with no verdict. The bytes are
    asked for, and `submodule_keys` says how each part is decoded.

    THE URL IS KEPT, NOT DROPPED. The row exists to agree with `make
    siblings` about one directory (#146): a clone whose own `origin` is the
    same bytes reads back as the same string through `origin_url`, and is
    the member's working clone by the mount comparison, as `verify_sibling`
    calls it. An empty `{}` here would send every such member's comparison
    to the `repository:` tail alone and call that clone a stranger. A url
    that matches nothing is quoted with the replacement character in it, as
    `origin_url` quotes one.

    `validate-family.py` reads the same file as bytes too, and decodes with
    `surrogateescape`. The replacement is chosen over it because this url
    is COMPARED with `origin_url`'s reading of a clone's remote, which is
    the replacement (#385): the same bytes read two ways are two strings,
    so a clone made from this very url would stop being the member's
    working clone. A section's NAME, which is handed back to git and never
    compared, keeps the `surrogateescape` (#732).
    """
    fields: dict = {}
    listing = gitmodules_listing(root, ["--file", ".gitmodules"])
    # A file git refuses whole gives no section (#733).
    for name, field, value in submodule_keys(listing or "") or []:
        fields.setdefault(name, {})[field] = value
    return fields


def mounted_from(root: Path, rel: str, repository: str) -> str:
    """The url THIS HOLDER mounts the member at `rel` from.

    `.gitmodules` FIRST AND `family.yaml`'s `repository:` SECOND, which is
    `scripts/siblings.py::clone_url`'s order and therefore the order that
    names the remote a working clone beside the holder was actually made
    from. `git submodule update` reads `.gitmodules`, so a family whose
    members are mounted from an SSH remote, a mirror or a bare repository on
    disk has a url that `https://github.com/<repository>.git` does not
    resemble at all; deriving the manifest's spelling and never reading the
    mount would call every clone in those estates a stranger.

    A RELATIVE URL IS RESOLVED AGAINST THE HOLDER'S OWN REMOTE, which is
    git's rule for one: `../Repo.git` is arithmetic against the
    SUPERPROJECT'S remote, not a remote, and a clone that took it literally
    would fetch from wherever the process is standing. `resolved_remote` is
    the SAME FUNCTION `siblings.py::resolve_relative` hands the holder's own
    `origin` to -- one definition in `scripts/repo_shape.py`, imported by
    both, rather than two copies and a parity test (#155).

    AND THE TRACKED DECLARATION IS WHAT IS RESOLVED, not the copy git cached
    in `.git/config` when it initialized the mount. The cache can be STALE --
    a `.gitmodules` edited without `git submodule sync` leaves the old url
    there -- and `make siblings` reads the declaration, so reading the cache
    is how this report would come to accept a clone the tool refuses, or
    refuse one it accepts (Copilot, PR #147). A relative url with no remote
    to resolve it against is handed back as it is: it then matches nothing,
    and the row's answer rests on the `repository:` comparison alone --
    which is the state `verify_sibling` is in for the same holder.

    THE LAST SECTION THAT GIVES `rel` A URL WINS, as
    `siblings.py::submodule_urls` maps it (#668), and as git reads a file
    whose sections are written one after another, each later value
    overwriting the one before. The first named a remote that `git
    submodule update` and `make siblings` both pass over. That holds for
    sections written whole: a section REOPENED further down the file is
    ordered here by the first key it gives, in `siblings.py` by its first
    url, and by git by its last `path`, so with one the three can name
    different sections (#733).

    ONLY A SECTION WITH A `path` MOUNTS ANYTHING (#733). One that gives a
    url and no path is mounted nowhere by git (`No url found` for its name
    as a path, measured), so its NAME is not read as a path, here or in
    `siblings.py`.
    """
    url = None
    for mount in submodule_config(root).values():
        # The section's NAME is not the path: a member mounted by hand
        # under another name, which git allows, is found by its `path`.
        if mount.get("path") == rel and mount.get("url"):
            url = mount["url"]
    if url is None:
        return f"https://github.com/{repository}.git"
    return resolved_remote(url, origin_url(root))


def same_repository_here(one: str, two: str) -> bool:
    """`same_repository`, with THIS MACHINE'S SYMLINKS allowed to answer too.

    THE HALF OF "IS THIS THE SAME REPOSITORY" A STRING CANNOT ANSWER (#157).
    `repo_shape.same_repository` compares two filesystem paths by EXACT
    equality -- the trailing `owner/repo` fallback used to call
    `/srv/a/IRRS.git` and `/other/a/IRRS.git` one repository -- and nothing in
    that module may touch a disk, so one directory reached through a SYMLINK
    is two repositories to it: `/var/folders/...` and
    `/private/var/folders/...` are the same temporary directory on macOS, and
    a clone made through one spelling while `.gitmodules` records the other is
    the member's working clone however it was reached.

    THE STRING RULE IS ASKED FIRST AND THE DISK ONLY IF IT SAYS NO, so this
    can ADD an answer and never take one away (Codex, PR #160). Only a path
    that is absolute HERE and exists HERE is resolved: `remote_local_path`
    answers None for a host remote, which names no directory, and for a
    relative one, which `realpath` would resolve against whatever directory
    this process is standing in rather than against the root's own remote,
    while `isabs` is the platform asking the same question of itself --
    `D:/mirrors/Fam.git` is a path on Windows and a directory named `D:`
    under this process's cwd on POSIX (Copilot, PR #160).

    THE SAME FUNCTION AS `siblings.py::same_repository_here`, DELIBERATELY,
    and for the reason the rest of this is shared and this is not: the STRING
    rule is one function both files import (#155), while the half that asks a
    disk belongs to whichever tool has one -- as `resolve_relative` does in
    the holder and `origin_url` and `mounted_from` do here.

    AND WHAT THE DISK SAYS IS WHAT THIS ROW REPORTS. A case-insensitive
    filesystem hands back the spelling it stores (Windows does), so two
    spellings that both open one directory can be one repository on THIS
    machine while the string rule calls them two -- #149 is strict on every
    platform because a string cannot know which it is, and this is the half
    that is looking.
    """
    if same_repository(one, two):
        return True
    resolved = []
    for url in (one, two):
        path = remote_local_path(url)
        if path and os.path.isabs(path) and os.path.exists(path):
            path = os.path.realpath(path)
        else:
            path = url
        resolved.append(path)
    return same_repository(*resolved)


def working_clone(sibling: Path, row: dict,
                  remote: str) -> tuple[str, str | None]:
    """`(what the clone at `sibling` is to this member, the origin found
    there when it is another remote's)`, for a directory with a `.git`.

    BOTH OF `verify_sibling`'S QUESTIONS, WHICH IS THE POINT (#146). The
    manifest says which project a directory is; only `origin` says which
    repository it came from, and a fork, a stale clone of a repository that
    has since been renamed, or any second copy of the same project from
    another remote carries the right manifest and the wrong origin.
    `scripts/siblings.py` calls that directory `WRONG ORIGIN` and leaves it
    alone, so a report that counted it as the working clone would disagree
    with the tool about the same directory on the same disk.

    EITHER SPELLING OF THE REMOTE ANSWERS, exactly as `verify_sibling`
    accepts either: the url the holder MOUNTS the member from, and the bare
    `Org/Repo` the row records, which `same_repository` matches by its tail.
    Nobody's own clone is required to spell a remote the way a manifest does.

    IT REPORTS AND IT NEVER REFUSES. The second half of the pair is the
    origin it FOUND, for the row to say out loud; the verdict for a member
    with no working clone beside the holder is unchanged, because where a
    person keeps their checkouts is the workstation's layout and not a
    compliance fact about the repository.

    AND A REFERENCE THIS ROW COULD NOT RESOLVE CHANGES NOTHING ABOUT THE
    ANSWER. A `.gitmodules` url spelled `../Repo.git` on a holder with no
    remote of its own is not a url, so it matches nothing -- and the
    `repository:` comparison beside it is then the whole of the question,
    which is EXACTLY what `verify_sibling` is left with in that state.
    Accepting any origin at all because the mount reference was unresolvable
    was this row's own invention, and it put back the disagreement this
    change exists to remove: `make siblings` calls a clone from somewhere
    else `WRONG ORIGIN` whether or not the mount url resolved (Copilot, PR
    #147).

    AND A PATH SPELLED UNDER ANOTHER PREFIX IS THE SAME PATH. One directory
    reached through a symlink -- `/var/folders/...` and
    `/private/var/folders/...` on macOS -- is one repository, and since #157
    the rule compares two paths exactly, so the MOUNT comparison is asked
    through `same_repository_here`, which resolves them. The `repository:`
    fallback beside it is asked of the origin exactly as git reported it: a
    mirror may be a symlink onto a storage path whose own tail is a serial
    number, and that row is matched BY its tail.
    `siblings.py::verify_sibling` asks the same two questions the same way,
    which is what keeps the tool and this report answering together about one
    directory (#146).

    THE ORIGIN IS REDACTED ON THE WAY OUT. The comparisons above are on the
    raw value; what a row prints and `--json` carries must not be somebody's
    token (Codex and Copilot, PR #147).

    AND IN `verify_sibling`'S ORDER, ONE WORD PER ANSWER (#669). The origin
    is asked FIRST, whatever the manifest says, as `make siblings` asks it:
    `wrong-origin`. Then the id `project_id` reads, by `verify_sibling`'s
    own comparison: `wrong-project`. A clone at the right origin that it
    passes is fetched as the member, but it is counted here only when its
    `project.yaml` CLAIMS to be this member (`is_this_member`), so one that
    does not is `unidentified`, and the rest are the `working-clone`.
    """
    origin = origin_url(sibling)
    repository = str(row.get("repository") or "")
    if not origin or not (same_repository_here(origin, remote)
                          or (repository
                              and same_repository(origin, repository))):
        return "wrong-origin", redacted(origin) if origin else "(no origin)"
    manifest = Context._read(sibling / PROJECT_MANIFEST)
    if (isinstance(manifest, dict)
            and str(manifest.get("id")) != str(row.get("id"))):
        return "wrong-project", None
    if not is_this_member(manifest, row):
        return "unidentified", None
    return "working-clone", None


def unclonable(sibling: Path) -> str | None:
    """What stands at `sibling`, a path with no `.git` of its own, that
    nothing can be cloned into: `files` (a folder with something in it),
    `file` (anything that is not a folder), `unlistable` (a folder this
    process cannot list) or `dangling` (a link to nothing, #784). None for
    nothing at all, or an empty folder.

    A FOLDER THAT CANNOT BE LISTED IS NOT EMPTY (#669). A directory that
    can be entered and not listed (mode `0311`, or `711`, which is common
    for another user's directory) raised `PermissionError` out of
    `iterdir`, and the `members` row became a FINDING that the check could
    not be run, so a COMPLIANT holder read DRIFTED, exit 1. Nobody can say
    it is empty, and `git clone` refuses a folder it cannot read, so it is
    a slot nothing is cloned into.

    A LINK TO NOTHING IS NOT NOTHING (#784). `exists` follows a link, so a
    dangling one read as `absent`, and the row said `make siblings` places
    the member there, where git ends `CLONE FAILED`: it cannot clone into a
    path that is a link to nothing. A JUNCTION TO NOTHING is one too
    (#793), the link Windows makes without privilege, which `is_symlink`
    does not see: it is asked as `siblings.py` asks it, with Python 3.12's
    `os.path.isjunction`, and before 3.12, which has none, the answer is no.
    """
    try:
        if not sibling.exists():
            junction = getattr(os.path, "isjunction", lambda _: False)
            return ("dangling" if sibling.is_symlink() or junction(sibling)
                    else None)
        if not sibling.is_dir():
            return "file"
        return "files" if any(sibling.iterdir()) else None
    except OSError:
        return "unlistable"


def sibling_slot(root: Path, sibling: Path, row: dict,
                 remote: str) -> tuple[str, str | None]:
    """`(what stands at ../<Project>, the origin found there when it is
    another remote's)`, in `siblings.py::place`'s order (#669).

    The holder itself (`is-the-holder`), then a path nothing can be cloned
    into (`not-a-clone`, `unclonable`), then nothing or an empty folder
    (`absent`, the only slot `make siblings` clones into), and then a clone,
    which `working_clone` answers. This RESTATES `place`'s order, as
    `working_clone` restates `verify_sibling`'s questions (#146), and not
    the parent-folder rule `make siblings` asks before either, which the row
    only names.

    A FILE, A FOLDER THAT CANNOT BE LISTED OR ENTERED, OR A LINK TO NOTHING
    IS `not-a-clone` TOO: nothing can be cloned into it. A holder whose
    pinned `siblings.py` predates #735 ends `make siblings` in a traceback
    on the first two, one that predates #784 ends `CLONE FAILED` on the
    link, and one that has both calls each NOT A CLONE, so the row says
    what is there and nothing of what `make siblings` does with it
    (`beside_sentence`), which is true of every one of them. A folder that
    cannot be entered cannot be asked for its `.git` either, so that
    question's `OSError` reads "no `.git`".
    """
    if sibling == root:
        return "is-the-holder", None
    try:
        present = (sibling / ".git").exists()
    except OSError:
        present = False
    if present:
        return working_clone(sibling, row, remote)
    return ("not-a-clone" if unclonable(sibling) else "absent"), None


def member_state(ctx: Context, row: dict, members_dir: str,
                 refused: list) -> dict:
    """ONE member's `--json` entry: both copies of it, as they are found.

    NOTHING IS ASKED OF A MOUNT THAT IS NOT POPULATED. An unbootstrapped
    submodule is an EMPTY directory, and `git rev-parse HEAD` run inside one
    answers about the HOLDER -- the repository whose working tree that empty
    directory sits in -- so a member that had never been fetched would be
    reported as checked out at the holder's commit. `head` and `detached` are
    `None` there, and the caller says which of the two it is.

    NOR OF ONE WITH NO `.git` OF ITS OWN, for the same reason (#414): a
    populated directory that is not a repository answers with the holder's
    HEAD too, and the row quoted it as the member's. `own_git` says which
    mount that is, and `unborn` names the branch an UNBORN HEAD names
    (`unborn_branch`), a state no line cures without choosing a commit.

    THE PIN IS ONLY BELIEVED WHEN IT IS 40 HEX. A `pin.commit` carrying a
    branch name or a tag is not a commit to compare a HEAD against, and this
    reports no pin at all rather than a comparison that would fail for the
    wrong reason.

    WHAT STANDS AT `../<Project>` IS `sibling` (`sibling_slot`, #669), so
    a caller reads a word rather than parsing the row's sentence.

    A MOUNT THIS USER CANNOT REACH IS NAMED (#430), by `mount_read`, as the
    `legs` row names a leg's: the gate's line under `mount_cannot_be_read`,
    and nothing asked of it. A `members/` at mode 000 was `could not be run`
    up to Python 3.13 and an unbootstrapped submodule from 3.14. `refused`
    collects `mount_read`'s `(line, OSError, listed)` for the row's advice.

    Split out of `check_members` for #134.
    """
    project = str(row.get("project") or "?")
    rel = str(row.get("path") or f"{members_dir}/{project}")
    mount = ctx.root / rel
    pin = row.get("pin") if isinstance(row.get("pin"), dict) else {}
    pinned = str(pin.get("commit") or "").lower()
    pinned = pinned if COMMIT_RE.match(pinned) else None
    populated, own_git, unread = mount_read(ctx.root, rel)
    head = head_of(mount) if populated and own_git else None
    unborn = (unborn_branch(mount) if populated and own_git and head is None
              else None)
    loose = detached(mount) if populated and unread is None else None
    sibling = ctx.root.parent / project
    remote = mounted_from(ctx.root, rel, str(row.get("repository") or ""))
    beside, elsewhere = sibling_slot(ctx.root, sibling, row, remote)
    clone = sibling.as_posix() if beside == "working-clone" else None
    entry = {"project": project, "path": rel, "pin": pinned,
             "populated": populated, "head": head, "own_git": own_git,
             "unborn": unborn, "detached": loose,
             "mounted_from": redacted(remote), "sibling": beside,
             "working_clone": clone, "other_origin": elsewhere}
    if unread is not None:
        entry[MOUNT_UNREAD] = unread[0]
        refused.append(unread)
    return entry


def member_problem(entry: dict) -> str | None:
    """What is wrong with one member's pinned copy, or None.

    THE ORDER IS THE ONLY ORDER THE ANSWERS MAKE SENSE IN: an empty mount, a
    populated one with no `.git` of its own and an unborn HEAD have no HEAD
    to compare (#414), a row with no 40-hex pin has nothing to compare it
    against, and only then is "checked out somewhere else" a thing that can
    be said. Each of these is a member the family's own gate would fail,
    which is why they are the row's findings and the state below them is
    not.

    A MEMBER AT ITS PIN BUT ON A BRANCH IS NOT ONE OF THEM, deliberately; the
    branch in `check_members` that records it says at length why the standard
    does not refuse a holder its own `family.py add` has just made.

    THE PATH, THE PROJECT AND THE BRANCH ARE SPELLED (#673): they are a
    manifest's and git's text, printed as `siblings.py` prints them.

    A MOUNT THIS USER CANNOT REACH COMES FIRST (#430): nothing else could
    be asked of it, and the gate's line says why.

    Split out of `check_members` for #134.
    """
    path = spelled(entry["path"])
    if entry.get(MOUNT_UNREAD):
        return mount_unread_said(spelled(entry[MOUNT_UNREAD]))
    if not entry["populated"]:
        return (f"{path}: not populated -- the pinned copy is an "
                "unbootstrapped submodule")
    if not entry.get("own_git", True):
        return (f"{path}: populated, but with no .git of its own, so "
                "git cannot read a HEAD in it")
    if entry.get("unborn"):
        return (f"{path}: HEAD names the branch {spelled(entry['unborn'])}, "
                "which has no commit")
    if entry["pin"] is None:
        return (f"{spelled(entry['project'])}: the row carries no 40-hex "
                "`pin.commit` to compare against")
    if entry["head"] != entry["pin"]:
        return (f"{path}: checked out at "
                f"{(entry['head'] or '?')[:12]}, pinned at "
                f"{entry['pin'][:12]}")
    return None


def url_less_members(root: Path, rows: list) -> list[str]:
    """The path of every member the holder records a gitlink for and git
    finds no url for (`submodule_url`), whatever the row says of it (#414).

    THE HOLDER'S OWN BOOTSTRAP UPDATES WITH NO PATH NAMED (`fetch_members`),
    so it inits every gitlinked member, and git stops that whole run at the
    first one with no url, before it fetches any other. A member at its pin,
    which the row passes over, or one it hands to the family gate, stops it
    as surely as one a checkout would cure: measured, the bootstrap prints
    `FETCH INCOMPLETE` and `No url found` for it and the row stays red.
    Asking only the members the row sends to a checkout kept the bootstrap
    as the NEXT over them. A member with no gitlink is no submodule to git,
    and is not asked.
    """
    return [entry["path"] for entry in rows
            if recorded_gitlink(root, entry["path"]) is not None
            and submodule_url(root, entry["path"])[1] is None]


#: The folder `make siblings` places the working clones from, as the row
#: words it (#605). EXACTLY, because `parent_folder_warning` compares the
#: name with `==` on every disk, so on macOS and Windows a holder in
#: `inkrouter` is refused for `InkRouter` (#669); `make siblings` prints the
#: rename itself.
FAMILY_FOLDER = "a folder named exactly after its repository (case included)"

#: `(what stands at ../<Project>, the word make siblings says it in)` for each
#: `sibling` state that is not the working clone and not a slot it clones
#: into (#669). `wrong-origin` names the two urls (`beside_sentence`); an
#: `unidentified` clone has no word, because `make siblings` fetches it as
#: the member. `CLONE FAILED` is not predicted: only a run can find it.
BESIDE_THE_HOLDER = {
    "is-the-holder": ("is this holder itself", "IS THE HOLDER"),
    "not-a-clone": ("is neither a git clone nor an empty folder",
                    "NOT A CLONE"),
    "wrong-origin": ("", "WRONG ORIGIN"),
    "wrong-project": ("is a clone of the member's remote whose project.yaml "
                      "and the family's row do not record the same id",
                      "WRONG PROJECT"),
    "unidentified": ("is a clone of the member's remote with no "
                     "project.yaml that says it is this member", ""),
}

#: What stands at a `not-a-clone` slot that a holder's pinned `siblings.py`
#: from before #735 ends in a traceback on, or from before #784 ends `CLONE
#: FAILED` on, as `unclonable` names it: the row says what is there and no
#: word of what `make siblings` does with it.
UNREADABLE_BESIDE = {"file": "is a file, not a folder",
                     "unlistable": "is a folder that cannot be listed",
                     "dangling": "is a link to nothing"}


def beside_sentence(ctx: Context, entry: dict) -> str:
    """One member's sentence about `../<Project>`, for a `sibling` state in
    `BESIDE_THE_HOLDER`: what stands there, and what `make siblings` does
    with it, in its own word (#669).

    EVERY VALUE IT QUOTES IS SPELLED (#673), as `verify_sibling` spells the
    same four in its WRONG ORIGIN finding: the project, the directory, the
    origin and the mount url are a manifest's, a disk's and git's text, and
    an ESC or a CR in one reached the terminal as the control it is.
    `--json` keeps them raw: `json.dumps` escapes them.

    A FILE, A FOLDER THAT CANNOT BE LISTED, OR A LINK TO NOTHING is
    `not-a-clone` with no word from `make siblings`, which ends in a
    traceback on the first two in a holder whose pinned copy predates #735,
    and `CLONE FAILED` on the link in one that predates #784: the sentence
    stops at what stands there (`UNREADABLE_BESIDE`).
    """
    state = entry["sibling"]
    where = ctx.root.parent / entry["project"]
    named = f"{spelled(entry['project'])}: {spelled(where)}"
    found, word = BESIDE_THE_HOLDER[state]
    how = unclonable(where) if state == "not-a-clone" else None
    if how in UNREADABLE_BESIDE:
        return (f"{named} {UNREADABLE_BESIDE[how]}, so it is not counted as "
                "its working clone")
    if state == "wrong-origin":
        found = (f"is a clone of {spelled(entry['other_origin'])}, not of "
                 f"{spelled(entry['mounted_from'])}")
    does = (f"calls the same directory {word} and leaves it exactly as it is"
            if word else "fetches it as the member, and nothing else")
    return (f"{named} {found}, so it is not counted as its working clone "
            f"(`make siblings`, from a holder in {FAMILY_FOLDER}, {does})")


def members_verdict(ctx: Context, detail: dict, members_dir: str,
                    problems: list, refused: list = ()) -> Row:
    """What the members add up to: the one finding, or the two OK wordings.

    ONLY THE PINNED COPIES CAN MAKE THIS ROW RED. A missing working clone is
    the WORKSTATION layout and not a fault of the repository's -- what the
    family gate reads is `<members_dir>/<Project>` -- and a member on a
    branch at its pin is a state worth a person's eye rather than a verdict.
    Both of those are therefore said inside an `ok` row, at length, instead
    of being left out of a report that would then look cleaner than the
    machine it ran on. A directory beside the holder that `make siblings`
    will not clone into and that is not the member's working clone is the
    third of them (#146): `working_clone` declines to count it, and this
    says what stands there and what `make siblings` will do with it (#669),
    because a row that only said "no working clone" would leave a person
    staring at a directory of that exact name.

    A MEMBER THIS USER CANNOT REACH IS ROUTED TO NO LINE (#430), as no such
    leg is: `refused` holds `mount_read`'s `(line, OSError, listed)` for each,
    the gate's advice for the cause is the `why`, or follows the line's, and
    where no other member has a line the NEXT is this doctor again.

    Split out of `check_members` for #134.
    """
    rows = detail["members"]
    on_a_branch = detail["on_a_branch"]
    # WHAT `make siblings` DOES WITH THE DIRECTORY IS CONDITIONAL, AND THE
    # WORDS SAY ON WHAT (#605). Since #578 it asks about the holder's parent
    # folder before it looks at any member, so it calls a directory WRONG
    # ORIGIN, or anything else, only from a holder in a folder named after
    # its repository (or in one a link of that name beside it leads to; the
    # words keep to the shorter, plainer case); from anywhere else it clones
    # nothing and never reaches the directory. THE REPOSITORY'S NAME, NOT
    # THE FAMILY'S `name:`: the rule takes the basename of the holder's
    # `repository:`, and `name:` is a display name that may differ
    # (`family_folder_name`, measured on a holder made with `--family Quill
    # --name QuillWorks`). The rule lives in the holder's pinned
    # `scripts/siblings.py` and is not copied here, where a copy would
    # drift: the words name the condition, and `make siblings` itself prints
    # the exact `mv` when it does not hold.
    beside = [beside_sentence(ctx, entry) for entry in rows
              if entry["sibling"] in BESIDE_THE_HOLDER]
    if problems:
        # WHAT STANDS BESIDE THE HOLDER IS SAID ON THE RED PATH TOO, AND IS
        # NOT ONE OF THE FINDINGS. It was not, until Codex pointed out on PR
        # #147 that a holder with ONE unbootstrapped mount returns here and
        # says nothing about the directory beside it -- so the person
        # bootstraps, re-runs, and only then hears about a clone that has
        # been the wrong one all along. The pinned copies are still the whole
        # of what makes this row red; the sentence says so.
        reason = "; ".join(problems)
        if beside:
            reason += ("; and, though it is not what fails this row: "
                       + "; ".join(beside))
        # THE NEXT IS CHOSEN BY WHAT IS WRONG, as `check_legs`' is and BY ITS
        # RULES (`checkout_reach`, #414), and the members that a CHECKOUT
        # cures win over the ones none does (#276). An empty mount, one with
        # files but no `.git` of its own whose repository the holder kept,
        # or a HEAD that is not the pin where the holder's GITLINK is, is
        # cured by fetching and checking out. No checkout cures a member the
        # holder records no gitlink for (the `family` row says
        # `member-gitlink-absent`, and the git line dies on `pathspec did not
        # match`), a gitlink that is not the pin (a checkout lands on the
        # gitlink, so HEAD would still not be the pin, `member-gitlink-
        # mismatch`), a row with no 40-hex `pin.commit`, a mount git cannot
        # read a HEAD in, or one with files, no `.git` of its own and no
        # kept repository. And no line cures, without choosing for the
        # person, an unborn HEAD or a member `.gitmodules` gives no url for.
        # A member reaches each of #414's four states, as a leg does.
        checkout: list[str] = []
        off_pin: list[Path] = []
        kept: list[tuple] = []
        relinked: list[str] = []
        gone: list[str] = []
        stuck: list[str] = []
        moved: list[Path] = []
        lockstep = False
        rerun = False
        nested: set = set()
        for entry in rows:
            rel = entry["path"]
            mount = ctx.root / rel
            gitlink = recorded_gitlink(ctx.root, rel)
            # WHAT THE HOLDER'S BOOTSTRAP MOVES IS EVERY MEMBER (#413 b): its
            # update names no path, so a member detached off its gitlink is
            # moved whatever this row says of it, and is named for it.
            if (gitlink is not None and entry["populated"]
                    and entry.get("own_git", True)
                    and left_in_reflog(entry["detached"], entry["head"],
                                       gitlink)):
                moved.append(mount)
            if member_problem(entry) is None or MOUNT_UNREAD in entry:
                # A member this user cannot reach is a person's, on a mode
                # or an owner (#430): no line reaches it.
                continue
            own_git = entry.get("own_git", True)
            if gitlink is None:
                lockstep = True
                continue
            if entry["populated"] and own_git:
                if entry.get("unborn"):
                    stuck.append(unborn_sentence(rel, "member"))
                    continue
                if (entry["pin"] is None or entry["head"] is None
                        or gitlink != entry["pin"]):
                    lockstep = True
                    continue
            route, keep, carries = checkout_reach(
                ctx.root, rel, gitlink, entry["populated"], own_git,
                entry["head"])
            if route == "no-url":
                stuck.append(no_url_sentence(rel))
                continue
            if route == "gone":
                lockstep = True
                gone.append(rel)
                continue
            checkout.append(rel)
            nested |= carries
            if route == "relink":
                relinked.append(rel)
            if isinstance(keep, tuple):
                kept.append(keep)
            elif keep is not None:
                off_pin.append(keep)
            # Its own lockstep fact (#414), as `check_legs` asks it.
            if entry["pin"] is None or gitlink != entry["pin"]:
                rerun = True
        rerun = rerun or lockstep or bool(stuck) or bool(refused)
        said = [mount_refusals(list(refused))] if refused else []
        # THE HOLDER'S OWN BOOTSTRAP STAYS THE NEXT WHEN IT CAN RUN: it does
        # what the plain git line does AND carries the credential rewrite a
        # PRIVATE member needs (`fetch_members`), so replacing it would
        # trade a missing script for a fetch that fails on a private member.
        # Each branch is the COMMAND and, apart from it, the sentence that
        # says why it is that command (#277).
        #
        # BUT NOT OVER A MEMBER WITH NO URL (#414). Its update names no path,
        # so it inits every member, and git stops that whole run at a member
        # with no section, or with a section that gives a path and no url
        # where the holder's own config has none either (`No url found`,
        # exit 128, measured), before it fetches any other; the bootstrap
        # reports the fetch incomplete and the row is as red as it was. So
        # EVERY member with a gitlink is asked, not only the ones routed to a
        # checkout above (`url_less_members`). The git line names only the
        # members it cures, and git runs it.
        url_less = url_less_members(ctx.root, rows)
        if checkout and own_bootstrap(ctx.root) and not url_less:
            next_command = (
                f"{PYTHON} "
                f"{quote_arg(ctx.root / 'scripts' / 'bootstrap.py')} "
                f"--root {quote_arg(ctx.root)}")
            # The same sentences the git line carries, built by the same
            # function (#413 b), for every member it moves. Its update is
            # recursive too, into every member that carries legs.
            carried = ({"tree"} if any((ctx.root / entry["path"]
                                        / ".gitmodules").is_file()
                                       for entry in rows
                                       if MOUNT_UNREAD not in entry)
                       else set())
            why = ("what `make bootstrap` runs in a holder: it fetches every "
                   "member at its pin and leaves it detached there"
                   + checkout_notes(
                       "member", moved, kept, relinked,
                       nested | carried))
            if rerun:
                why += rerun_sentence("member")
            why += "".join(f". {sentence}" for sentence in said)
        elif checkout:
            if own_bootstrap(ctx.root):
                # Each member that stops the bootstrap is named, routed or
                # not, so the reader knows which entry to restore.
                after = (". This holder has its own scripts/bootstrap.py, "
                         "but it updates every member at once, and a member "
                         "git finds no url for can stop that run before it "
                         "fetches any other, so this is the plain git line "
                         "over the rest, with no credential rewrite for a "
                         "private member"
                         + "".join(f". {no_url_sentence(rel)}"
                                   for rel in url_less))
            else:
                after = (". This holder has no scripts/bootstrap.py that can "
                         "run, so this is the plain git line, with no "
                         "credential rewrite for a private member")
            next_command, why = submodule_update_next(
                ctx.root, checkout, off_pin, "member", after, rerun,
                kept=kept, relinked=relinked, nested=nested)
            why += "".join(f". {sentence}" for sentence in said)
        elif lockstep:
            # THE FAMILY GATE, one definition of it for this row and the
            # `family` row (`lockstep_next`), and, beside it, what no line
            # cures, as `check_legs` says it (#414).
            next_command, why = lockstep_next(ctx, FAMILY_GATE, "member")
            if why:
                why += "".join(gone_sentence(rel) for rel in gone)
                why += "".join(f". {sentence}" for sentence in [*said, *stuck])
            elif said or stuck:
                why = ". ".join([*said, *stuck])
        elif refused:
            # A PERSON'S, on a mode or an owner, and never a git line (#430).
            next_command, why = doctor_line(ctx), ". ".join([*said, *stuck])
        else:
            # NO LINE CURES IT without choosing for the person (#414).
            next_command, why = None, ". ".join(stuck)
        return Row("members", "members", FINDING, reason, next_command,
                   detail, why=why)
    note = f"{len(rows)} member(s) mounted at their pins"
    if on_a_branch:
        note += ("; on a BRANCH rather than detached: "
                 + ", ".join(spelled(path) for path in on_a_branch)
                 + " (a fresh `clone --recurse-submodules` of this holder is "
                   "detached; `family.py add` leaves a branch behind)")
    # AND ON THE GREEN PATH IT IS SAID, MEMBER BY MEMBER. Every one of these
    # is also in `without_working_clone` -- it is not counted -- and "there
    # is no working clone for IRRS" on its own, about a directory named
    # `IRRS` that is sitting right there, is the sentence that sends a
    # person looking for a bug in this command (#146).
    if beside:
        note += "; " + "; ".join(beside)
    placed = [spelled(entry["project"]) for entry in rows
              if entry["sibling"] == "absent"]
    if placed:
        # THE NOTE SAYS WHEN `make siblings` PLACES THEM, NOT THAT IT DOES
        # (#605). Since #578 it asks about the holder's parent folder before
        # it clones anything: from one named after the holder's REPOSITORY
        # (its `repository:`'s basename, not the family's display `name:`,
        # which `family.py init --name` may make another string), or reached
        # through a link of that name BESIDE it (`family_link` looks only at
        # `<grandparent>/<name>`), it places the working clones; from
        # anywhere else it clones nothing, prints the exact `mv` and exits 1.
        # The rule is the holder's own, in its pinned `scripts/siblings.py`,
        # and is not tested here -- a second copy would drift -- so the words
        # are the same whichever folder this holder is in.
        #
        # AND IT NAMES ONLY THE SLOTS IT CLONES INTO (#669): nothing, or an
        # empty folder. It named every member with no working clone, so one
        # row said both that `make siblings` places IRRS and that it leaves
        # IRRS exactly as it is; every other one is said above, in the word
        # `make siblings` says it in.
        return Row("members", "members", OK,
                   f"{note}; no working clone beside the holder for "
                   + ", ".join(placed)
                   + " (`make siblings` places them when the holder is in "
                     f"{FAMILY_FOLDER}, or in one a link of that name beside "
                     "it leads to; with the holder anywhere else it clones "
                     "nothing and prints the `mv` that moves it into such a "
                     f"folder; the pinned copy under {spelled(members_dir)}/ "
                     "is detached by design)", None, detail)
    if beside:
        return Row("members", "members", OK, note, None, detail)
    return Row("members", "members", OK,
               f"{note}, each with a working clone beside the holder", None,
               detail)


def check_members(ctx: Context) -> Row:
    """Each member pinned under `members/`, and the working clone beside it.

    TWO COPIES OF EVERY MEMBER IS THE LAYOUT, and they are different things.
    `members/<Project>` inside the holder is PINNED AND DETACHED — that is
    what `bootstrap` places and what `validate-family.py` reads — and the
    sibling beside the holder is where a person works. So the mount is asked
    whether it is detached AT the pin, and the sibling is only asked what
    stands there, as `make siblings` asks it (#669).

    FINDING THE STATE IS `member_state`'s, JUDGING IT IS `member_problem`'s
    AND THE WORDING IS `members_verdict`'s, so that this loop reads as the
    one sentence it is: every member is looked at, and each is either a fault
    or a state worth saying.
    """
    # NOT "no members yet", which is an `ok` about an empty family: a holder
    # whose `family.yaml` does not load has members nobody can name (#205),
    # and neither does one whose `members:` this cannot read (#864).
    waiting = (waiting_row(ctx, "members", "members",
                           "the members it pins are not known and none is "
                           "checked against its pin", {"members": []})
               or members_unread_row(ctx,
                                     "no member is checked against its pin"))
    if waiting is not None:
        return waiting
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
    #: `mount_read`'s `(line, OSError, listed)` for each member this user
    #: cannot reach (#430).
    refused: list[tuple] = []
    for row in members:
        entry = member_state(ctx, row, members_dir, refused)
        rows.append(entry)
        problem = member_problem(entry)
        if problem:
            problems.append(problem)
        elif entry["detached"] is False:
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
            on_a_branch.append(entry["path"])
        if not entry["working_clone"]:
            siblings_absent.append(entry["project"])
    detail = {"members": rows, "without_working_clone": siblings_absent,
              "on_a_branch": on_a_branch}
    return members_verdict(ctx, detail, members_dir, problems, refused)


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

    AND A URL THAT IS NOT UTF-8 NAMES NOTHING, as no origin names nothing
    (#385). git keeps a URL as the bytes it was given -- a clone of a
    directory named in a legacy code page has one -- and read strictly it
    ended this report in a `UnicodeDecodeError` traceback, exit 1, from the
    `naming` row, where the same repository with no origin ends NOT A SHAPE
    ROOT, exit 2. No segment of it is salvaged: in a double-byte code page
    the byte `\\` is the second half of many characters, so what the rules
    above split off could be a fragment of a name. It is the answer
    `shape_advisory.repository_names` gives the same URL, so the `naming`
    row, `the way in` and the `Triad` row read one identity.
    """
    try:
        url = git_out(["remote", "get-url", "origin"], cwd=root)
    except (Refusal, OSError, UnicodeDecodeError):
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


def origin_org(root: Path) -> str | None:
    """The organisation `adopt-project.py plan` would read off `root`'s own
    `origin`, or None where it reads none (#545).

    `plan --source <path>` takes its `--org` from the source's `origin` and,
    with none to take, refuses `adopt-no-org` and asks for the flag. It
    reads none in THREE cases, and this is the one question the NEXT of
    `the way in` needs answered: the repository has no `origin`; its URL is
    not UTF-8 (git keeps a URL as the bytes it was given, and `plan` reads
    it strictly, so it is no origin there, as `origin_name` and
    `shape_advisory.repository_names` already say of it, #385); or its URL
    ends in no `org/repo` -- a bare `repo.git` -- or is a path in any
    spelling, which names no repository (#521). The first is the case #545
    was filed for. The other two are the same refusal on the same line, so
    the line is built from the same reading rather than from "has an
    origin".

    THE SAME READING, NOT A COPY OF IT (#521). The pair is
    `repo_shape.url_repository`, which `adopt-project.py` reads the source's
    `origin` with too. This file kept a copy of `plan`'s regex, held to it
    by a test, and when `plan` came to read a url ending `/` and to read no
    path, the copy would have sent a person whose `origin` is
    `/srv/git/acme/Atlas.git` to a line `plan` refuses `adopt-no-org`.

    ONLY WHEN `root` CARRIES ITS OWN `.git`, for `repo_local_origin_name`'s
    reason: `git remote get-url origin` walks UP to the nearest ancestor
    repository, and an ancestor's organisation is not this directory's.
    """
    if not (root / ".git").exists():
        return None
    try:
        url = git_out(["remote", "get-url", "origin"], cwd=root)
    except (Refusal, OSError, UnicodeDecodeError):
        return None
    pair = url_repository(url)
    return pair.split("/")[0] if pair else None


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
    script = ctx.shape / NAMING_SCRIPT
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
    code, quoted, whole, refusal = run_naming_script(
        ctx, script, ["--explain", "--", *names])
    detail = {"names": names, "origin": remote, "exit": code,
              "explain": ascii_text(whole).strip().splitlines()[:40]}
    spelled = " ".join(quote_arg(name) for name in names)
    command = f"{PYTHON} {quote_arg(script)} --explain -- {spelled}"
    # A CHECKOUT WHOSE OWN POLICY DOES NOT LOAD SAID NOTHING ABOUT THE NAME
    # (#678). This row quoted the script's `REFUSED` as the name's finding;
    # the verdict stays NOT A SHAPE ROOT, and the row says whose file it is,
    # as `check_naming`'s does.
    if refusal is not None:
        return naming_policy_row(refusal, command, detail, names)
    # A SCRIPT THAT CRASHED SAID NOTHING ABOUT THE NAME (#410). A directory
    # whose name is not UTF-8 made the script raise as it printed that name,
    # and this row quoted `UnicodeEncodeError: ...` as the name's finding.
    # The verdict stays NOT A SHAPE ROOT; the row says the checkout's script
    # stopped, as `check_naming`'s does.
    crash = crashed(code, whole)
    if crash is not None:
        return naming_crashed_row(code, crash, command, detail, names)
    if code >= 2:
        return Row("naming", "naming", FINDING,
                   f"{', '.join(names)}: {naming_refuses_words(code, quoted)}",
                   command, detail)
    reason = f"{', '.join(names)}: " + (
        "classifies under the naming policy" if code == 0
        else (quoted or "matches no family in the policy"))
    return Row("naming", "naming", OK if code == 0 else FINDING, reason,
               None if code == 0 else command, detail)


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
                       (AGENTS_MD, "an AGENTS.md"),
                       ("Makefile", "a Makefile"),
                       # The optional staying-single record. Named here as
                       # a FILE THAT IS PRESENT, like the rest of this list,
                       # and not read: its only reader is the Triad advisory,
                       # whose row says what it found in it.
                       (shape_advisory.RECORD_FILE,
                        f"a {shape_advisory.RECORD_FILE}")):
        there = (root / name).exists()
        detail[name] = there
        if there:
            facts.append(note)
    detail["project_yaml"] = (root / PROJECT_MANIFEST).is_file()
    detail["family_yaml"] = (root / FAMILY_MANIFEST).is_file()
    if detail["project_yaml"] or detail["family_yaml"]:
        # A manifest is THERE and did not declare the kind that makes it one,
        # which is a different fault from having none, and worth saying. It
        # LOADED and said something else: one that does not load at all is
        # never here, because its filename makes the root that kind (#205).
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

#: The mark the preflight puts on a check that failed. `setup-project.py`'s
#: `CROSS`, spelled again here because that file is run, never imported.
PREFLIGHT_FAILED = "[!!]"
#: How the preflight's closing line opens: `this machine is not ready yet (see
#: above).`, which it prints with the same mark as the checks it points at.
PREFLIGHT_VERDICT = "this machine is not ready yet"


def preflight_failures(whole: str) -> list[str]:
    """What the preflight found NOT READY, as the lines it printed (#549).

    THE ROW USED TO QUOTE THE CHILD'S LAST LINE, which is that closing
    verdict -- `this machine is not ready yet (see above).` -- and above it
    the doctor shows nothing: the preflight's lines are kept only in `--json`
    (`detail.report`). A reader of the table got a pointer at output that was
    never printed. The lines it points at are the `[!!]` ones, one per check
    that failed, in the order the preflight made them; each is returned
    without its mark and flattened by `ascii_text`, as `detail.report` is.

    THE VERDICT IS NOT ONE OF THEM, though it carries the same mark: it is
    the child summarising its own failures, so it is dropped here and a
    machine that failed two checks says two things. Nothing in
    `setup-project.py` had to change for this: the mark was already the one
    thing a line of the report is read by (`check_machine` reads `[ok]` and
    `[??]` by theirs). An empty list is a child that exited non-zero without
    saying which check failed -- a crash, an interpreter that would not
    start -- and the caller falls back to the one line `run_validator` quoted.
    """
    failed: list[str] = []
    for line in whole.splitlines():
        text = line.strip()
        if not text.startswith(PREFLIGHT_FAILED):
            continue
        said = ascii_text(text[len(PREFLIGHT_FAILED):].strip())
        if said and not is_preflight_verdict(said):
            failed.append(said)
    return failed


def is_preflight_verdict(line: str) -> bool:
    """Whether `line` is the preflight's closing verdict, `[!!]` mark on it
    or not -- the one line of its report that summarises the checks above it
    instead of being one of them (#549)."""
    return line.strip().removeprefix(PREFLIGHT_FAILED).strip().startswith(
        PREFLIGHT_VERDICT)


def first_sentence(line: str) -> str:
    """`line` up to its first full stop that ends a sentence: one followed by
    white space or by the end. `3.9` ends nothing; `gh is not installed.
    Install it: ...` says `gh is not installed`.

    A FAILED CHECK'S LINE IS THE FACT, THEN THE PREFLIGHT'S OWN REMEDY FOR
    SOMEBODY RUNNING THE SCAFFOLD (#549, review): `Run: gh auth login`, or
    `re-run with --local-remote-dir <dir>`. This command refuses that flag,
    and `setup-project.py --preflight --local-remote-dir <dir>` then says the
    machine is ready, which is false for this row. The row's NEXT is its one
    remedy, so the reason keeps only what is not ready and
    `detail.not_ready` keeps the whole line."""
    stop = re.search(r"\.(?:\s|$)", line)
    return line[:stop.start()] if stop else line


def check_machine(ctx: Context) -> Row:
    """Can this machine run the fixes the rows above name?

    IT RUNS THE REAL PREFLIGHT rather than a second copy of the check list.
    `setup-project.py --preflight` is section (1) of the scaffold and nothing
    else -- git, a Python 3.9+, the bootstrap interpreter, `gh` and its login,
    the credential helper, and the autocrlf warning -- and re-listing those
    here would be two lists to keep in step, which is the duplication #50
    removed. It is run with stdin CLOSED and in a session of its own, with no
    controlling terminal (`run_validator`, #492), so the "no terminal, no
    offer" rule fires and nothing is offered, prompted for or installed: the
    doctor diagnoses, and installing something is a different act with a
    different consent. It is run with no `site` as well, as every child is
    (#342), which changes nothing it reports: what it asks about -- `git`,
    `gh`, the running interpreter -- it reaches as programs and through
    `sys`, never through site-packages.

    THIS IS THE ONE ROW THAT CAN REACH A NETWORK, and it is `n/a` by status
    for a separate reason. The preflight asks `gh` its version, whether it is
    authenticated and who as (`gh --version`, `gh auth status`, `gh api
    user`) -- three questions `gh` answers by talking to its host; nothing
    else in this command leaves the disk. And a machine's state is not the repository's: a workstation
    with no `gh` cannot open the pull request a fix needs, which is worth
    saying and is not this repository being non-compliant. So the row reports
    and never changes the verdict.

    WHEN IT IS NOT READY THE REASON NAMES WHAT IS NOT (#549): the first
    sentence (`first_sentence`) of each of the preflight's own `[!!]` check
    lines (`preflight_failures`), `; `-joined, and the whole lines in
    `detail.not_ready`. It used to quote the child's last line, a verdict that
    points "above" at output this table does not show, and the first version
    of this change quoted the lines whole, remedies and all, beside a NEXT
    that is the one command.
    """
    entry = ctx.shape / "setup-project.py"
    adoption = shutil.which(ADOPTION_TOOL)
    detail = {"preflight": entry.as_posix(),
              ADOPTION_TOOL: adoption or None}
    if not entry.is_file():
        return Row("machine", "machine", NA,
                   f"{entry} is not here, so the preflight could not be run",
                   None, detail)
    # The ONE child that keeps the operator's `gh` login and proxies: every
    # other is started `offline` (#297), and this row exists to ask `gh`.
    code, quoted, whole = run_validator(ctx, entry, ["--preflight"],
                                        reach_network=True)
    detail["exit"] = code
    # The preflight's own `[ok]`/`[!!]`/`[??]` lines, which are its report.
    marks = [ascii_text(line.strip()) for line in whole.splitlines()
             if line.strip().startswith(("[ok]", "[!!]", "[??]"))]
    detail["report"] = marks
    # WHAT IS NOT READY, in the preflight's own words (#549): its `[!!]`
    # lines, whole in `detail`, and the first sentence of each in the reason.
    # `quoted` is the child's last line and, for a machine that is not ready,
    # that is its verdict pointing "above" at lines this table does not print
    # -- so it is the fallback for a child that said nothing better, and never
    # the verdict itself.
    failures = preflight_failures(whole) if code != 0 else []
    detail["not_ready"] = failures
    ready = "this machine is ready" if code == 0 else \
        "this machine is missing something the fixes above may need"
    reason = f"{ready} (setup-project.py --preflight, exit {code})"
    said = "; ".join(first_sentence(line) for line in failures)
    if not said and code != 0 and not is_preflight_verdict(quoted):
        said = quoted
    if said:
        reason += f": {said}"
    if not adoption:
        reason += (f"; {ADOPTION_TOOL} is not on PATH, which only "
                   "`adopt-project.py` needs")
    if code == 0:
        return Row("machine", "machine", NA, reason, None, detail)
    return Row("machine", "machine", NA, reason,
               f"{PYTHON} {quote_arg(entry)} --preflight", detail,
               why="it names each missing prerequisite and offers to install "
                   "it, on a typed yes")


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


#: The one value a way-in command needs and this report cannot know, spelled
#: the one way the handbook's scaffold commands and this file's own scaffold
#: line have always spelled it. IT IS NOT QUOTED AND MUST NOT BE: it is a
#: placeholder the reader replaces, not a value a command could take, and
#: quoting it would tell them to type the angle brackets.
ORG_PLACEHOLDER = "<your-org>"

#: What both scaffold rows say about their one line (#545): the placeholder
#: the line carries is the reader's to replace, and the scaffold asks before
#: it creates anything. Said once, so the non-repository row and the second
#: row of a repository cannot word it two ways.
SCAFFOLD_WHY = (f"replace {ORG_PLACEHOLDER} with the GitHub organisation to "
                "create it in; without --yes, it asks")


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
    HOST. `quote_arg` defaults to the host when it is passed no platform, so
    with an explicit `platform` half this line followed the argument and half
    followed the machine: `scaffold_command(PureWindowsPath(r"C:\srv\Shape"),
    "Atlas", "nt")` named `setup-project.py` and `python` on every host, as
    asked, and then rendered the path BARE on Windows and QUOTED on Linux and
    macOS -- two different strings for the same arguments, from a function
    whose whole reason to take a `platform` is to spell one line for the
    OTHER one (#103). `\` is in `UNQUOTED_NT` and not in `UNQUOTED_POSIX`,
    so a Windows path is exactly where that shows.

    ONE RESOLUTION PER QUESTION, NEVER ONE PER CALL. An explicit `platform`
    is the whole answer: the branch, the quoting and the interpreter all
    read it, rather than each re-deriving "which platform is this" from its
    own source -- which is the defect above, stated as code. With none, the
    host answers two questions, and Git Bash is where they part (#711): the
    MACHINE picks the entry point and the interpreter, so a Windows machine
    is handed `python setup-project.py` in PowerShell and in Git Bash alike
    (`os.name`, and `python_command`, which keeps the RAW `platform` and so
    the module constant itself); the SHELL picks the quoting, which is
    `host_shell_dialect`, `sh`'s under Git Bash, as `quote_arg(value, None)`
    asks it. Off Git Bash the two answers are one, so that line is unchanged,
    byte for byte.
    """
    machine = os.name if platform is None else platform
    target = host_shell_dialect() if platform is None else platform
    if machine == "nt":
        return (f"{python_command(platform)} "
                f"{quote_arg(shape / 'setup-project.py', target)} "
                f"--org {ORG_PLACEHOLDER} --project "
                f"{quote_arg(project, target)}")
    return (f"{quote_arg(shape / 'setup.sh', target)} --org {ORG_PLACEHOLDER} "
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


def leg_clone(ctx: Context) -> bool:
    """Does the Triad advisory read this directory as a leg clone?

    ASKED OF `shape_advisory`, never answered a second time here, so `the
    way in` and the `Triad` row cannot disagree about one directory. False
    when the advisory cannot answer at all -- `the way in` then says what it
    always said.
    """
    try:
        return shape_advisory.read(ctx.root, ctx.shape).state \
            == shape_advisory.LEG_CLONE
    except Exception:  # noqa: BLE001 - the advisory never fails the report
        return False


def check_the_way_in(ctx: Context) -> Row:
    """The two ways a directory becomes a shape root, and who decides.

    NEITHER IS RUN HERE AND NEITHER IS RECOMMENDED OVER THE OTHER. Adopting an
    existing repository keeps its identity and its history and cuts two legs
    out of it; scaffolding creates three new repositories. Which of those a
    person wants is a fact about their repository, not about this directory
    listing, so both are named and the human chooses.

    A ROW CARRIES ONE NEXT, SO A GIT REPOSITORY GETS TWO ROWS (#545). This
    one is the way a directory's own kind points at -- the adoption for a
    repository, the scaffold for one that is not -- and `check_the_other_way_in`
    is the second command a repository is told of, which `AGENTS.md` asks the
    report to give ("Report the verdict and both commands"). A directory
    that is not a repository has no adoption to offer and gets one row, as it
    always did; a leg clone gets neither (below).

    THE ADOPTION LINE NAMES THE ORGANISATION WHEN IT CANNOT BE READ (#545).
    `adopt-project.py plan` takes `--org` from the source's `origin`, so a
    repository with no `origin` -- or one whose URL names no `org/repo`, or
    is not UTF-8, or is a path -- pasted this line and was refused
    `adopt-no-org`, exit 2.
    `origin_org` asks the question `plan` asks, and where it has no answer
    the line ends `--org <your-org>`, the placeholder this report already
    prints on the scaffold line (`ORG_PLACEHOLDER`). It is a value the
    reader supplies, so the row's `why` says to replace it; where `origin`
    does name an organisation the line is unchanged, and carries none.

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

    A CHECKOUT WHOSE OWN NAMING POLICY DOES NOT LOAD OFFERS NO WAY IN (#707).
    The `--project` is derived through that file, and this row, like
    `naming`, was left to its fault: a tab line was `FINDING the way in
    refused: ...` about the directory, and a pattern that does not compile
    ended the doctor in a traceback. `way_in_project` asks the one question
    (`own_naming_policy`), and the row is `way_in_policy_row`'s, an `n/a`
    environment row naming the checkout's file, in a plain directory and in
    a repository, which is also told of `the other way in` below. A leg
    clone, which is offered no command, is the row it always was.
    """
    root = ctx.root
    is_repo = (root / ".git").exists()
    project, refusal = way_in_project(ctx)
    org = origin_org(root)
    if is_repo and leg_clone(ctx):
        # A LEG IS NOT ADOPTED. Splitting a spec or code leg into two more
        # legs is the one adoption nobody wants, and offering it two rows
        # above a `Triad` row that says "work from its assembly root" would
        # be this report contradicting itself (#164 review). No `next` here:
        # the Triad row names the root to work from.
        fix = why = None
        reason = ("this is a git repository with no shape manifest, NAMED OR "
                  "WRITTEN AS A LEG: a leg is not adopted or scaffolded on "
                  "its own -- see the Triad row for its assembly root")
    elif refusal is not None:
        return way_in_policy_row(
            refusal, "way-in", "the way in",
            {"git_repository": is_repo, "suggested_project": None,
             "origin_org": org})
    elif is_repo:
        fix = (f"{PYTHON} {quote_arg(ctx.shape / 'adopt-project.py')} "
               f"plan --source {quote_arg(root)} --project "
               f"{quote_arg(project)}")
        why = None
        if org is None:
            # NOT QUOTED, for `ORG_PLACEHOLDER`'s reason.
            fix += f" --org {ORG_PLACEHOLDER}"
            why = (f"replace {ORG_PLACEHOLDER} with the GitHub organisation "
                   "to adopt under: this repository's `origin` names none "
                   "that `plan` can read")
        reason = ("this is a git repository with no shape manifest: it is "
                  "ADOPTED in place, keeping its name, identity and history")
    else:
        fix = scaffold_command(ctx.shape, project)
        why = SCAFFOLD_WHY
        reason = ("there is no repository here to adopt: a new project is "
                  "SCAFFOLDED, which creates three repositories and asks "
                  "first")
    return Row("way-in", "the way in", NA, reason, fix,
               {"git_repository": is_repo, "suggested_project": project,
                "origin_org": org},
               why=why)


def way_in_project(ctx: Context) -> tuple:
    """`(project, None)`: the `--project` both ways in are offered, from the
    one identity `check_the_way_in` reads -- `origin`'s repository name where
    `root` carries its own `.git` and one, the directory's name otherwise --
    or `(None, refusal)` where this checkout's own naming policy cannot give
    one (#707).

    THE POLICY HAS TO LOAD AND TO ANSWER, and neither is the directory's
    fault. `own_naming_policy` is the one question the doctor asks of that
    file (#678), so a policy the loader refuses and one that raises --
    a pattern `re.compile` will not take -- are told in one shape, as a
    `Refusal` `naming_policy_refusal_of` makes of either, and `classify`
    raising on one that loaded is the same fault found a step later, told
    as `policy-unusable`, which the row words "cannot be used" and not "does
    not load". This
    called `NamingPolicy.load` with no handler, and `run_checks` catches only
    a `Refusal` and an `OSError`: a tab line became `FINDING the way in
    refused: ...` about the DIRECTORY, and a pattern that does not compile
    ended the doctor in a traceback with exit 1, the code of a finding.
    """
    identity = repo_local_origin_name(ctx.root) or ctx.root.name
    policy, fault = own_naming_policy(ctx.shape)
    if fault is not None:
        return None, naming_policy_refusal_of(ctx.shape, fault)
    try:
        return project_token_for(identity, policy), None
    except Exception as exc:  # noqa: BLE001 - see the docstring
        return None, naming_policy_refusal_of(ctx.shape, exc,
                                              "policy-unusable")


def way_in_policy_row(refusal: Refusal, row_id: str, label: str,
                      detail: dict) -> Row:
    """A `the way in` row for a checkout whose own naming policy does not
    load (#707): `n/a`, and `detail.environment`, as the `naming` row of the
    same directory is (`naming_policy_row`, #678), in the same words.

    NO NEXT AND NO `--project`. The command this row offers is spelled with
    the one name the policy derives, and a policy that does not load derives
    none, so nothing here could be pasted and work: the `why` says where the
    file is, and the next run offers the commands. `n/a` AND NOT A FINDING,
    because the question cannot be asked here and nothing is wrong with the
    directory; the verdict is NOT A SHAPE ROOT, exit 2, as it is for every
    directory that has neither manifest, because `verdict_for` decides that
    before it reads a row.
    """
    reason, why = naming_policy_words(
        refusal, "this directory", "how this directory becomes a shape root",
        "cannot be used" if refusal.code == "policy-unusable"
        else "does not load")
    return Row(row_id, label, NA, reason, None,
               {**detail, "environment": True,
                "refusal": {"code": refusal.code, "detail": refusal.detail}},
               why=why)


#: Named once, as `LABEL_TRIAD_ADVISORY` below is: the row, the registry entry
#: and the tests all print the same words.
LABEL_OTHER_WAY_IN = "the other way in"


def check_the_other_way_in(ctx: Context) -> Row | None:
    """The scaffold, for a git repository that is also told of the adoption
    (#545).

    `check_the_way_in` carries one NEXT, and for a repository it is the
    adoption. `AGENTS.md` says the two ways in are `adopt-project.py plan`
    and `setup.sh` and that the report gives the verdict "and both commands":
    which of them is wanted is a fact about the person's repository, and the
    row that answered only the adoption chose for them. THE SAME LINE THE
    NON-REPOSITORY ROW PRINTS, `scaffold_command`, for the same `--project`
    -- the one identity `way_in_project` reads -- so the two rows cannot
    name two projects.

    SILENT WHERE THE FIRST ROW OFFERS NO ADOPTION: a directory that is not a
    repository already has the scaffold as its one row, and a leg clone is
    sent to its assembly root (`leg_clone`, asked as `check_the_way_in` asks
    it). A row that repeated the scaffold there would be this report
    printing the same line twice, or contradicting the Triad row above it.
    """
    if not (ctx.root / ".git").exists() or leg_clone(ctx):
        return None
    project, refusal = way_in_project(ctx)
    if refusal is not None:
        # The same fault as `the way in` above it says, in the same words
        # (#707): a row each, because each is told of its own command.
        return way_in_policy_row(refusal, "way-in-scaffold",
                                 LABEL_OTHER_WAY_IN,
                                 {"git_repository": True,
                                  "suggested_project": None})
    return Row("way-in-scaffold", LABEL_OTHER_WAY_IN, NA,
               "a NEW project is SCAFFOLDED instead of adopting this "
               "repository: it creates three repositories and asks first",
               scaffold_command(ctx.shape, project),
               {"git_repository": True, "suggested_project": project},
               why=SCAFFOLD_WHY)


#: Named once, like `LABEL_MANIFEST_KINDS` above: this function's three
#: returns and the `CHECKS` entry below must all print the same row name.
#: "Triad" because human-facing text says Triad (the ratified vocabulary);
#: the row's `id` is a machine key and says what the row is.
LABEL_TRIAD_ADVISORY = "Triad"


def check_triad_advisory(ctx: Context) -> Row | None:
    """The Triad advisory, once, for a repository that has not elected it.

    RULED BY BRETT HEAP ON 2026-10-06: "ratify 1249 as recommended", which
    ratified openxFactory's `prefer-triad-project-shape`. The Triad is the
    PREFERRED project shape, it stays elective and confers nothing, and this
    report is one of the three surfaces that MAY say so -- once, beside what
    it already reports, and never on a verdict's account. So the row is
    `advisory` and nothing else: `verdict_for` reads `FINDING` only, NOT A
    SHAPE ROOT stays exit 2 exactly as it was, and an assembly root's verdict
    is whatever its own rows make it. THE SHAPE IS NEVER A REVIEW INPUT, so no
    required check, review lane or merge gate may be built on this row, as
    none may be built on the NOT A SHAPE ROOT it sits beside.

    WHERE IT IS SILENT, `scripts/shape_advisory.py` decides, from declared
    facts only -- an elected Triad, a family holder, a `<user>-wip` workspace,
    a `single-repository.yaml` of the right kind -- and this returns NO ROW
    there. Two silences still have something to say, and say it as what it
    is rather than as the advisory: a LEG CLONE gets the existing instruction
    to work from its assembly root instead (`n/a`, because the leg is part of
    a Triad and the advisory would be false there), and a staying-single
    record that leaves a field out gets a `note` naming the field, because the
    advisory is that record's only reader and this is where its reader says
    what it found.

    A RECORD THAT SILENCES NOTHING IS REPORTED IN THE ADVISORY ROW ITSELF:
    one that does not parse, or declares another `kind`, is named with the
    reason, and nothing fails on its account.

    `next` IS EMPTY ON PURPOSE, in all three statuses. Every other `next`
    here is the command that fixes its row, and nothing is broken: the two
    ways on -- converting with `adopt-project.py`, or recording staying
    single -- are named in the sentence and are a person's to choose, and
    for any repository that is not a leg `the way in` row above already
    carries the adoption command for it (a leg is offered none: it is sent
    to its assembly root).

    ONLY WHERE THERE IS NO MANIFEST. An assembly root whose `project.yaml`
    declares fewer than two legs is not a Triad by the detector, but it is
    not "a single repository" either -- it is a broken project root, and the
    `manifest` row's finding is the guidance there. The same is true of one
    whose `project.yaml` does not load at all, which `Context` reads as the
    project its filename says rather than as no manifest (#205). So the row
    is asked only of a directory with neither manifest, which is also the one
    kind of root whose verdict reads no row at all: nothing here could move a
    verdict even if it tried.

    AND IT NEVER FAILS THE REPORT. `shape_advisory.read` already answers
    rather than raises; this says nothing rather than a traceback for
    whatever is left -- a row nobody needed is the cheapest thing in the
    report to lose, and the ratified rule is that the advisory changes no
    exit status.
    """
    try:
        return _triad_advisory_row(ctx)
    except Exception:  # noqa: BLE001 - see the docstring
        return None


def _triad_advisory_row(ctx: Context) -> Row | None:
    """`check_triad_advisory`'s body: the row, or no row where it is silent."""
    reading = shape_advisory.read(ctx.root, ctx.shape)
    detail = reading.as_dict()
    detail.update({"record": shape_advisory.RECORD_FILE,
                   "schema": shape_advisory.RECORD_SCHEMA,
                   "template": shape_advisory.RECORD_TEMPLATE})
    if reading.advise:
        said = shape_advisory.advisory_lines() + \
            shape_advisory.record_report(reading.record_problems)
        return Row("triad-advisory", LABEL_TRIAD_ADVISORY, ADVISORY,
                   " ".join(said), None, detail)
    if reading.state == shape_advisory.LEG_CLONE:
        return Row("triad-advisory", LABEL_TRIAD_ADVISORY, NA,
                   shape_advisory.leg_instruction(reading.leg), None, detail)
    if reading.state == shape_advisory.RECORDED_SINGLE \
            and reading.field_problems:
        return Row("triad-advisory", LABEL_TRIAD_ADVISORY, NOTE,
                   f"{shape_advisory.RECORD_FILE} records that this project "
                   "stays a single repository, so no advisory is given; "
                   "against its schema ("
                   f"{shape_advisory.RECORD_SCHEMA}): "
                   + "; ".join(reading.field_problems)
                   + ". It stays silent either way; nothing fails on its "
                   "account", None, detail)
    return None


# ---------------------------------------------------------------------------
# A root in the middle of a merge
# ---------------------------------------------------------------------------


#: Named once: `check_merge`'s two rows and the `CHECKS` entry below must
#: print the same row name.
LABEL_MERGE = "merge"

#: How many unmerged paths the `merge` row's sentence names before it counts
#: the rest. `--json` lists every one.
UNMERGED_NAMED = 5


def unmerged_paths(root: Path) -> list[str] | None:
    """Each path the root's index holds UNMERGED, once, in git's order, or
    None where git gives no answer (#424).

    `git ls-files -u` lists one record per STAGE, `<mode> <object> <stage>
    TAB <path>`, so a path both sides changed is listed three times and is
    kept once. `-z`, read as bytes, so a name is never C-quoted and a byte
    that is not UTF-8 survives as itself. Relative to the root, as every
    other row reads a path. `--no-optional-locks`, git's word for a reader
    that must not write into the repository it reads.
    """
    raw = git_answer(["--no-optional-locks", "ls-files", "-u", "-z"], root,
                     binary=True)
    if raw is None:
        return None
    paths: dict[str, None] = {}
    for record in raw.split(b"\0"):
        _meta, tab, path = record.partition(b"\t")
        if tab:
            paths.setdefault(path.decode("utf-8", "surrogateescape"), None)
    return list(paths)


def git_dir_holds(root: Path, name: str) -> bool:
    """Whether the root's git directory holds `name` (#424). `--git-path`
    names it in a linked worktree too, where git keeps it per worktree, and
    a relative answer is relative to the root, where git was asked."""
    where = (git_answer(["rev-parse", "--git-path", name], root,
                        binary=True) or b"").rstrip(b"\r\n")
    if not where:
        return False
    path = Path(os.fsdecode(where))
    return (path if path.is_absolute() else root / path).exists()


#: What a rebase in progress keeps in the git directory: the merge backend's
#: directory and the apply backend's, which `git am` shares.
REBASE_STATE = ("rebase-merge", "rebase-apply")


def merge_in_progress(root: Path) -> bool:
    """Whether git records a MERGE in progress, and no rebase: a
    `MERGE_HEAD` file, and neither of `REBASE_STATE` (#424).

    THE FILE, NOT `rev-parse --verify MERGE_HEAD`, which also resolves a
    branch or a tag of that name. AND NOT A REBASE: `git rebase -r` stopped
    on a merge it replays writes `MERGE_HEAD` too, and `git merge --abort`
    there strands the rebase, so the row sends a rebase to `git status`,
    which names its own `--continue` and `--abort`.
    """
    return git_dir_holds(root, "MERGE_HEAD") and not any(
        git_dir_holds(root, name) for name in REBASE_STATE)


def own_repository(root: Path) -> bool:
    """Whether git answers about the root's OWN repository (#424).

    `git -C` DISCOVERS, so a plain directory inside a checkout in the middle
    of a merge would be told about that checkout's merge -- the reason
    `not_its_own_repository` declines for a leg. Asked here as bytes and
    compared with `samefile`, so neither a toplevel that is not UTF-8 nor a
    root spelled in another case or through a symlink reads as a stranger.
    """
    top = (git_answer(["rev-parse", "--show-toplevel"], root, binary=True)
           or b"").rstrip(b"\r\n")
    if not top:
        return False
    try:
        return os.path.samefile(os.fsdecode(top), root)
    except OSError:
        return False


def check_merge(ctx: Context) -> Row | None:
    """Whether the root is in the middle of a merge git will not commit.

    THE DEFECT (#424). Nothing here asked git whether the index held an
    unmerged path. The validators read the working tree, and
    `recorded_gitlink` answers a gitlink a conflicted merge holds only at
    stages 1, 2 and 3 from HEAD, which its own docstring argues is right for
    a validator. So a root two `bump-leg.py` branches had been merged into
    read `DRIFTED` while the conflict markers sat in its pin, and COMPLIANT,
    exit 0, once `git checkout --ours` had taken them out -- with `UU` still
    on the pin and the gitlink, `MERGE_HEAD` still there, and `git commit`
    refusing. A conflicted file no row reads was COMPLIANT from the start.

    A FINDING, AND WHAT ASSERTS IT IS GIT. A `FINDING` is what something
    ELSE asserts, and git refuses to commit an index that holds an unmerged
    path. The row names the paths -- `UNMERGED_NAMED` of them, then a count
    -- and its NEXT is `git -C <root> status`, which lists every one and,
    for a merge, a rebase or a cherry-pick alike, names the operation and
    how to finish or abandon it. Which side each path takes is the merge's
    owner's call, so no command here takes one. The words about finishing
    are in the reason, not after the command: a NEXT is pasted whole (#277).

    NOT CANNOT ANSWER, AND NO ROW IS MADE TO WAIT ON IT. Exit 3 is THIS
    CHECKOUT failing to ask, and an unfinished merge is a fact about their
    repository. The other rows still answer about the tree in front of them,
    and some of them say what to do with a file the merge left behind -- the
    `shape currency` row's side to take of a conflicted shape pin (#237),
    the project's own validator refusing a pin with conflict markers in it
    -- which the person finishing the merge wants to read.

    A MERGE WITH NOTHING UNMERGED IS A `note`. `git merge --no-commit`, or a
    conflict resolved and added: git commits it as it stands, and the other
    rows read the files that commit is made from, so nothing asserts a
    fault. The row says so, and the verdict steps over it.

    NO ROW AT ALL OTHERWISE, as the Triad row is silent where its rule says
    so. A row saying "no merge" on every run would be a row about a state a
    root is almost never in, and every report and every `--json` caller's
    row set would change for it. Where git gives no answer -- no repository,
    no `git` -- there is no row either: no commit is being refused, and the
    rows that read git say so themselves. Nor where the root is not a
    repository of its own (`own_repository`): the merge `git -C` would find
    is the enclosing checkout's.

    ONLY THE ROOT'S OWN INDEX. A leg is a repository of its own, and a merge
    left unfinished in one is work in progress there, like an uncommitted
    edit, which no row reports: the root records the leg's commit, never its
    index.
    """
    root = ctx.root
    if not own_repository(root):
        return None
    unmerged = unmerged_paths(root)
    merging = merge_in_progress(root)
    if not unmerged and not merging:
        return None
    if not unmerged:
        return Row("merge", LABEL_MERGE, NOTE,
                   "a merge is in progress and nothing in it is unmerged: "
                   "`git commit` concludes it and `git merge --abort` "
                   "abandons it. A note, because git commits it as it "
                   "stands and the other rows read the files it is made "
                   "from", None,
                   {"unmerged": [], "count": 0, "merging": True})
    spelled = [repr(path) if UNWRITABLE_IN_A_PLAN.search(path) else path
               for path in unmerged]
    named = ", ".join(spelled[:UNMERGED_NAMED])
    if len(spelled) > UNMERGED_NAMED:
        named += f" and {len(spelled) - UNMERGED_NAMED} more"
    how = ("A merge is in progress: resolve each path (which side it takes "
           "is the merge owner's call), `git add` it, then `git commit`, or "
           "abandon the merge (`git merge --abort`)" if merging
           else "`git status` says how to resolve each, and how to finish "
           "or abandon what left them")
    return Row("merge", LABEL_MERGE, FINDING,
               f"{len(spelled)} path(s) unmerged in the index, so git "
               f"commits nothing here until each is resolved: {named}. "
               f"{how}. Until then every other row reads a tree no commit "
               "holds",
               f"git -C {quote_arg(root)} status",
               {"unmerged": spelled, "count": len(spelled),
                "merging": merging})


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------


CHECKS = (
    # FIRST, ON BOTH KINDS OF ROOT, and a row only while a merge is
    # unfinished: every row after it then reads a tree no commit holds, and
    # the verdict names it above them all -- see `check_merge` (#424).
    Check("merge", LABEL_MERGE, (PROJECT, FAMILY), check_merge),
    Check("naming", "naming", (PROJECT,), check_naming),
    Check("manifest", "manifest", (PROJECT,), check_manifest),
    Check("pins", "pins", (PROJECT,), check_pins),
    Check("family", "family", (FAMILY,), check_family),
    Check("manifest-kinds", LABEL_MANIFEST_KINDS, (PROJECT, FAMILY),
          check_manifest_kinds),
    Check("shape-currency", LABEL_SHAPE_CURRENCY, (PROJECT, FAMILY),
          check_shape_currency),
    Check("legs", "legs", (PROJECT,), check_legs),
    Check("leg-shape-files", LABEL_LEG_SHAPE_FILES, (PROJECT,),
          check_leg_shape_files),
    # AFTER the two rows about the legs THEMSELVES, because it is about what
    # is INSIDE them, and a leg that is not mounted has no paths to judge --
    # which those rows have just said, with `make bootstrap` beside it.
    Check("placement", "placement", (PROJECT, FAMILY), check_placement),
    Check("agent-files", LABEL_AGENT_FILES, (PROJECT, FAMILY),
          check_agent_files),
    Check("members", "members", (FAMILY,), check_members),
    Check("naming", "naming", (NOT_A_ROOT,), check_not_a_root_naming),
    Check("contents", "what is here", (NOT_A_ROOT,), check_what_is_here),
    Check("way-in", "the way in", (NOT_A_ROOT,), check_the_way_in),
    # RIGHT AFTER IT: a git repository is told of the scaffold too (#545), and
    # the two commands are read together. Silent for anything else.
    Check("way-in-scaffold", LABEL_OTHER_WAY_IN, (NOT_A_ROOT,),
          check_the_other_way_in),
    # AFTER EVERYTHING ABOUT THE REPOSITORY AND BEFORE THE MACHINE, and only
    # where there is no manifest at all. A family holder is never advised; an
    # assembly root whose manifest is short of a Triad is a broken root, which
    # its `manifest` row says better than "this is a single repository" would.
    # The row is `advisory` -- or absent where the rule makes it silent --
    # and never moves the verdict; see `check_triad_advisory`.
    Check("triad-advisory", LABEL_TRIAD_ADVISORY, (NOT_A_ROOT,),
          check_triad_advisory),
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
            row = check.run(ctx)
            if row is not None:
                rows.append(row)
        except Refusal as exc:
            # No NEXT: a refusal's remedy is prose, never a command to paste,
            # so it is the row's `why` (#408, #548).
            rows.append(Row(check.id, check.label, FINDING,
                            f"refused: {exc.detail}", None,
                            {"error": exc.code}, why=remedy_as_why(exc)))
        except OSError as exc:
            named = refused_in_root(ctx.root, exc)
            if named is None:
                rows.append(Row(check.id, check.label, FINDING,
                                f"could not be run: {exc}", None, {}))
                continue
            # A PATH IN THE ROOT THIS USER CANNOT REACH (#430), however the
            # check came to ask it: the gate's line, this doctor again, and
            # the gate's advice, as every row that asks its own path says
            # it, where the row said `could not be run: [Errno 13] <the
            # absolute path>`. A statement about the repository, so no
            # `environment`, and with no entry in it, so no drift either
            # (`drifted_reasons`).
            line = cannot_be_read(named, exc)
            rows.append(Row(check.id, check.label, FINDING, line,
                            doctor_line(ctx),
                            {"cannot_be_read": line, "path": named},
                            why=cannot_read_why([exc])))
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


def drifted_file_reasons(counts: dict) -> list:
    """The drifted shape copies the verdict line quotes, in its own order.

    TWO GROUPS AND THEY SAY DIFFERENT THINGS. `locally-modified` and `both`
    are what MADE this repository drifted -- a copy of the standard carries
    an edit -- so they are named first. `upstream-removed`, `unmapped`,
    `copy-missing` and `copy-is-link` are states in which the standard and
    the copy no longer map onto each other at all, which is worth quoting
    beside the edits because it is the same person's next question.
    `copy-is-link` (#286) is a pinned copy the tree keeps as a symlink, or
    under one: git holds the link, not the bytes the pin's digest describes,
    and `update-shape.py apply` refuses it. It is a conflict there, so the
    row is `drifted`; unnamed here, that drift had no reason to print, and
    the verdict fell through to the catch-all `INVALID (shape-currency)`.

    A state is named only when its count is non-zero: a verdict line reading
    `0 unmapped` would be a parenthetical contradicting the words above it.

    `merged-away` IS NAMED LAST (#502): a `shape/` collision copy merged into
    the file it collided with and removed, whose row `update-shape.py apply`
    drops. Until it does, the pin names a copy the tree does not hold, which
    is what makes the project's own `validate-pins.py` red, so the verdict
    names the cause and not the `pins` row.

    Split out of `verdict_for` for #134.
    """
    merged = ("merged-away",)
    edited = ("locally-modified", "both")
    unmapped = ("upstream-removed", "unmapped", "copy-missing",
                "copy-is-link")
    return [f"{counts[state]} {state}" for state in edited + unmapped
            + merged
            if counts.get(state)]


def drifted_reasons(by_id: dict, detail: dict) -> list:
    """Everything that makes this repository DRIFTED, in the order said.

    THREE DIFFERENT THINGS CAN BE OFF AND ALL OF THEM ARE DRIFT: a copy of
    the standard carrying a local edit, a leg checked out somewhere other
    than the commit the root pins, and a member of a family in that same
    state. They share one verdict because they are one fact -- the tree is
    not the tree the pins describe -- and a reader told only the first of
    them would fix it and still be drifted.

    Returns the empty list when none of them is, which is the caller's signal
    to go on down the ladder rather than a claim that anything is well.

    A LEG WHOSE PIN CANNOT BE READ IS NOT OFF ITS PIN (#847): nothing says
    where its pin is, and `validate-pins.py` refuses the pin by name, which
    is the `pins` row and INVALID. Such a leg carries `cannot_be_read` in
    the `legs` row, and is not counted. Every other leg whose HEAD is not
    its pin is counted as before. Where none is, the red row is drift by
    main's count of one (an empty mount whose pin is gone has no HEAD and no
    pin to differ) only where no leg carries `cannot_be_read`, whichever leg
    made the row red: the gate refuses that pin before it reports anything
    else, and INVALID names it; the run after the pin is mended says the
    drift.

    A ROW THAT COULD NOT ASK IS NOT DRIFT EITHER (#430). The count is read
    from the row's own entries, and a `legs` row with none -- what
    `run_checks` makes of a check that raised, `could not be run` or a path
    it names -- has no leg to be off its pin: with a leg mount at mode 000
    the verdict said `DRIFTED (1 leg(s) not at the pin)` beside the very
    rows that said they could not be run. A leg whose MOUNT cannot be read
    (`mount_cannot_be_read`) is as uncounted as one whose pin cannot be, and
    so is one whose GITLINK cannot be, because the root's own `.git` cannot
    be read (`gitlink_cannot_be_read`, #1146): its `legs` row said `no
    gitlink recorded` of each leg, and the verdict was DRIFTED. The
    `members` row is drift only where a member this user CAN reach has a
    problem. Such a row goes on down the ladder, to the gate that refuses
    the path (`invalid_verdict`) or to the catch-all, which names it: INVALID,
    never DRIFTED, and never CANNOT ANSWER, because a path in the root this
    user cannot reach is a statement about the repository.

    Split out of `verdict_for` for #134.
    """
    reasons: list[str] = []
    if detail.get("drifted"):
        reasons += drifted_file_reasons(detail.get("counts") or {})
    legs = by_id.get("legs")
    if legs is not None and legs.status == FINDING:
        entries = legs.detail.get("legs") or []
        read = [leg for leg in entries
                if "cannot_be_read" not in leg and MOUNT_UNREAD not in leg
                and GITLINK_UNREAD not in leg]
        off = [leg for leg in read if leg.get("head") != leg.get("pin")]
        if entries and (off or len(read) == len(entries)):
            reasons.append(f"{len(off) or 1} leg(s) not at the pin")
    members = by_id.get("members")
    if members is not None and members.status == FINDING and any(
            MOUNT_UNREAD not in entry and member_problem(entry)
            for entry in members.detail.get("members") or []):
        reasons.append("a member is not at its pin")
    return reasons


def merge_verdict(by_id: dict) -> tuple | None:
    """`INVALID (merge)` and its exit code while the root's index holds an
    unmerged path, or None (#424).

    ABOVE DRIFTED, MISPLACED AND EVERY OTHER RUNG, for the reason drift
    outranks a red validator: the verdict names the cause, not what it
    causes. In the issue's merge of two leg bumps the conflict markers in
    the pin turned `pins` and `manifest kinds` red and read as a leg not at
    its pin, so the verdict said `DRIFTED (1 leg(s) not at the pin)` about a
    leg that had not moved. And no row's fix can be committed while git
    refuses to commit at all.

    BELOW CANNOT ANSWER, which is THIS CHECKOUT failing to ask: exit 3 says
    nothing here is a statement about the tree, and the table still carries
    this row.

    `INVALID` AND NOT A NEW VERDICT. AGENTS.md documents the verdicts and
    their exits, and this is a gate somebody else owns gone red -- git's,
    which commits nothing until the index is merged -- which is what
    `INVALID` names everywhere else.

    THE LIST HAS TO BE NON-EMPTY, as `misplaced_verdict` requires of its
    own: `run_checks` turns an exception out of a check into a FINDING with
    an empty `detail`, which falls through to the catch-all instead.
    """
    merge = by_id.get("merge")
    if merge is not None and merge.status == FINDING \
            and merge.detail.get("unmerged"):
        return f"{V_INVALID} (merge)", 1
    return None


def misplaced_verdict(by_id: dict) -> tuple | None:
    """MISPLACED and its exit code, or None when nothing is in the wrong leg.

    UNDER DRIFTED AND OVER INVALID. A path in the wrong leg is a fact about
    the SHAPE that nothing else in this report can see -- no validator, no
    pin row, no manifest asserts where a file lives -- whereas a red
    validator names itself in the table whether or not it also names the
    verdict line. Drift still outranks it: a leg off its pin means the paths
    that row read are not the paths the pin describes.

    THE LIST HAS TO BE NON-EMPTY, not merely the row red. `run_checks` turns
    an exception out of any check into a FINDING row with an empty detail,
    and this branch would then have answered `MISPLACED (0 paths)` about a
    row that never got as far as classifying anything -- a verdict naming a
    count of zero. Such a row falls through to the generic handling further
    down and reads `INVALID (placement)`, which is what it is (Copilot, PR
    #100).

    Split out of `verdict_for` for #134.
    """
    placement = by_id.get("placement")
    misplaced = (placement.detail.get("misplaced") or []) if placement else []
    if placement is not None and placement.status == FINDING and misplaced:
        count = len(misplaced)
        return (f"{V_MISPLACED} ({count} path"
                + ("" if count == 1 else "s") + ")"), 1
    return None


def invalid_verdict(rows: list[Row]) -> tuple | None:
    """INVALID and its exit code, when a NAMED gate is red, or None.

    EVERY ID LISTED HERE IS A GATE SOMEBODY ELSE OWNS -- the naming policy,
    the project's own two validators, the family's, the registry of manifest
    kinds, the agent files -- so this verdict always names a check the reader
    can go and run for themselves. A row that is red and not on this list is
    not thereby harmless: the catch-all at the end of `verdict_for` answers
    `INVALID` for it too, and says why it is written the way it is.

    Split out of `verdict_for` for #134.
    """
    red = [row.id for row in rows
           if row.status == FINDING
           and row.id in ("naming", "manifest", "pins", "family",
                          "manifest-kinds", "agent-files")]
    if red:
        return f"{V_INVALID} ({', '.join(red)})", 1
    return None


def behind_verdict(detail: dict) -> tuple | None:
    """SHAPE BEHIND and its exit code, in either of its two kinds, or None.

    WHICH KIND OF BEHIND IS THE WHOLE POINT OF THERE BEING TWO BRANCHES. A
    pin naming an older commit while not one copied byte differs quotes the
    two commits, because the counts it would otherwise print are zero BY
    CONSTRUCTION on that branch; the ordinary kind quotes the counts. Both
    are exit 1, and both are the `shape-currency` row's `detail` read back --
    this decides nothing the row did not already say.

    Split out of `verdict_for` for #134.
    """
    if detail.get("behind_pin_only"):
        return (f"{V_BEHIND} (pin {str(detail.get('pinned'))[:12]} -> "
                f"{str(detail.get('standard'))[:12]}, no copied file "
                "differs)"), 1
    if detail.get("behind"):
        counts = detail.get("counts") or {}
        changed = counts.get("upstream-changed", 0)
        added = counts.get("upstream-added", 0)
        return (f"{V_BEHIND} ({changed} upstream-changed, "
                f"{added} upstream-added)"), 1
    return None


def verdict_for(ctx: Context, rows: list[Row]) -> tuple[str, int]:
    """ONE line, and the exit code that goes with it.

    The order below IS the precedence, and the docstring at the top of this
    file argues the one that surprises: drift outranks a red validator,
    because an edited shape copy is what makes `validate-pins.py` red and
    naming the validator would send the reader at the symptom.

    EACH RUNG OF THE LADDER IS ITS OWN FUNCTION and each of them argues, in
    its own docstring, why it sits where it does -- so the precedence can be
    read here as the list it is, and the argument for any one place in it is
    found by opening the function that holds that place.
    """
    if ctx.kind == NOT_A_ROOT:
        return V_NOT_A_ROOT, 2
    blocked = cannot_answer(rows)
    if blocked is not None:
        return f"{V_CANNOT_ANSWER} ({blocked.label}: {blocked.reason})", 3
    by_id = {row.id: row for row in rows}
    currency = by_id.get("shape-currency")
    detail = currency.detail if currency else {}

    unfinished = merge_verdict(by_id)
    if unfinished is not None:
        return unfinished
    reasons = drifted_reasons(by_id, detail)
    if reasons:
        return f"{V_DRIFTED} ({', '.join(reasons)})", 1
    misplaced = misplaced_verdict(by_id)
    if misplaced is not None:
        return misplaced
    invalid = invalid_verdict(rows)
    if invalid is not None:
        return invalid
    behind = behind_verdict(detail)
    if behind is not None:
        return behind
    # THE CATCH-ALL, and it is here so that a check ADDED LATER cannot exit 0
    # while its row says FINDING. A new row that belongs in `invalid_verdict`
    # above is a one-line edit; a new row nobody classified still fails
    # loudly. It reads `FINDING` only, so a `note` row is stepped over here
    # too -- which is the whole of what `note` means.
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
    if ctx.manifest_refusal is not None:
        # Said where the kind is, because the kind was read off the
        # FILENAME here and a reader should know that before the rows (#205).
        described = (f"{described[:-1]}, which does not load: see the "
                     f"`{MANIFEST_ROW[ctx.kind]}` row)")
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
        # A LINE OF ITS OWN, UNDER THE COMMAND AND NEVER ON IT (#277): what
        # follows a NEXT on its line is pasted with it, and an interactive
        # zsh runs it.
        if row.why:
            print(f"  {'':<{status_width}}  {'WHY':<{width}}  {row.why}")
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
    # ONLY UNDER THE VERDICT IT EXPLAINS (#410). A crashed naming script in
    # a directory that is not a root marks its row `environment` as it does
    # in a root, and the verdict there is still NOT A SHAPE ROOT, exit 2:
    # a `shape-doctor-cannot-answer` refusal under it would contradict the
    # line above it.
    blocked = (cannot_answer(rows) if verdict.startswith(V_CANNOT_ANSWER)
               else None)
    if blocked is not None:
        print(f"\nREFUSED shape-doctor-cannot-answer: {blocked.reason}",
              file=sys.stderr)
        # A ROW WITH NO NEXT HAS NO REMEDIATION TO PRINT (#278). The separator
        # environment row is a FINDING with a NEXT of None by ruling -- no
        # command could be pasted and work -- and its reason already says what
        # to do instead; `Remediation: None` was a literal `None` after it.
        if blocked.next_command:
            print(f"  Remediation: {blocked.next_command}", file=sys.stderr)
        # AND ITS `why` WHENEVER IT HAS ONE, Remediation or not (#277): the
        # sentence is about the row, and a row with no command to paste can
        # still have something to say about the one it does not offer.
        if blocked.why:
            print(f"  Why: {blocked.why}", file=sys.stderr)


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


#: The variable git reads to leave out the fetch a partial clone makes for
#: an object it lacks (#787).
NO_LAZY_FETCH = "GIT_NO_LAZY_FETCH"


@contextlib.contextmanager
def lazy_fetch_off():
    """This process's environment with `GIT_NO_LAZY_FETCH=1` for as long as
    it runs, and as it was afterwards (#787).

    "IT NEVER FETCHES", BY CONSTRUCTION. A partial clone (`git clone
    --filter`) fetches an object it lacks from a promisor remote on any read
    that needs one, so the promise held read by read: #683 and #754 ask
    `rev-list --missing=print`, which never fetches, before anything reads
    a partial clone of the standard, and never ask `for-each-ref --contains`
    of a commit the clone does not hold. A read added to a row later, or one
    in a project's own partial clone, need not ask first. With the variable
    set, git fails that read instead of fetching: `warning: lazy fetching
    disabled; some objects may not be available`, then the read's own error
    (measured with git 2.43: exit 128, and no `fetch` in a trace2 log). That
    is a read that failed, as one does where the clone's remote is out of
    reach, and every reader here already answers one: `git_answer`'s None,
    `git_out`'s `git-failed`, `update-shape.py`'s
    `update-upstream-unreadable`.

    EVERY GIT THIS PROCESS STARTS, AND NOTHING IT PRINTS. The doctor's own
    reads (`git_out`, `git_answer` and its few `subprocess.run` of git),
    `update-shape.py`'s `Upstream` as `check_shape_currency` drives it in
    this process, the validators `run_validator` starts with a copy of this
    environment, and every git each of those starts, inherit it. A NEXT the
    doctor prints is text for a person's own shell, which does not have it,
    so a `fetch --refetch` printed there fetches. The environment is put
    back on the way out, for a caller that runs `main` in its own process.

    WHICH GIT HONOURS IT. git 2.45.0 and later, and the security releases of
    2024-05-14 back to 2.39.4 (2.39.4, 2.40.2, 2.41.1, 2.42.2, 2.43.4,
    2.44.1), whose fix for CVE-2024-32465 made `promisor-remote.c` read it;
    distributions carry that fix too (Ubuntu's 2.43.0-1ubuntu7.1 and later).
    An older git ignores the variable, harmlessly, and there the guards
    above are what keep the doctor from fetching, as before.
    """
    before = os.environ.get(NO_LAZY_FETCH)
    os.environ[NO_LAZY_FETCH] = "1"
    try:
        yield
    finally:
        if before is None:
            os.environ.pop(NO_LAZY_FETCH, None)
        else:
            os.environ[NO_LAZY_FETCH] = before


#: What a `--root` this user may not search is told for a refused PERMISSION
#: (#430): `PERMISSION_ADVICE` for the root itself, which has no "inside the
#: root" above it.
ROOT_PERMISSION_ADVICE = (
    "Make the root searchable by this user: `chmod u+rx` on it (and on every "
    "directory above it), or fix who owns it.")


def root_refusal(named: str, exc: OSError) -> str:
    """The refusal of a `--root` whose `stat`, or whose search, the operating
    system refused (#430): `shape-doctor-root-unreadable`, the code `main`
    gives a root `resolve()` refuses, with the gate's line for the path and
    its advice for the cause, then "Then run this doctor again".

    BEFORE ANY ROW, BECAUSE NO ROW CAN ASK. Every row reads a name in the
    root, and a root this user cannot search answered each of them with its
    own `[Errno 13]` up to Python 3.13 -- `Context` reading `project.yaml`
    ended the run in a traceback -- and from 3.14 with "nothing is here",
    `NOT A SHAPE ROOT`; a folder above it this user cannot search read as
    `shape-doctor-root-missing`. EXIT 3, the documented "usage or
    environment": nothing here is a statement about the tree, which no row
    could read, and exit 2 is `NOT A SHAPE ROOT`, a verdict about it."""
    advice = (ROOT_PERMISSION_ADVICE if isinstance(exc, PermissionError)
              else OTHER_REASON_FOLDER)
    return (f"REFUSED shape-doctor-root-unreadable: --root {named}: cannot be "
            f"read ({os_reason(exc)})\n  Remediation: {advice} Then run this "
            "doctor again")


@lazy_fetch_off()
def main(argv: list[str] | None = None) -> int:
    # FIRST, so that every `print` after it -- `--help` included -- escapes
    # a name stdout cannot encode rather than raising on it (#214).
    escape_what_stdout_cannot_encode()
    args = build_parser().parse_args(argv)
    # Before any row is built: `quote_arg` and `ascii_text` read it (#785).
    global REPORT_ENCODING
    REPORT_ENCODING = "utf-8" if args.as_json else None
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
    try:
        there = is_a(root, stat.S_ISDIR)
        if there:
            # SEARCH, AND NOT LISTING (#430): every row asks a name it knows,
            # so a root this user can search and not list (mode 111) reads
            # COMPLIANT, and is not refused. `<root>/.` is asked through
            # `os.path`, because a `Path` drops the `.` and would ask the
            # root's own `stat`, which only its parent decides.
            os.stat(os.path.join(root, os.curdir))
    except OSError as exc:
        print(root_refusal(args.root, exc), file=sys.stderr)
        return 3
    if not there:
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
