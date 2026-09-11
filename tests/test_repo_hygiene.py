# SPDX-License-Identifier: Apache-2.0
"""Properties of THIS repository that a fork depends on and nobody re-checks."""

from __future__ import annotations

import ast
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO, SCAFFOLD, WINDOWS_SKIP

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import NamingPolicy  # noqa: E402

SHIPPED = [
    REPO / "setup-project.py",
    REPO / "scaffold-project.py",
    REPO / "bootstrap",
    REPO / "adopt-project.py",
    REPO / "update-shape.py",
    REPO / "shape-doctor.py",
    REPO / "scripts" / "repo_shape.py",
    REPO / "scripts" / "shape_materialize.py",
    REPO / "scripts" / "path_classify.py",
    REPO / "scripts" / "validate-repository-naming.py",
    REPO / "scripts" / "family.py",
    REPO / "scripts" / "bump-leg.py",
    REPO / "scripts" / "render-cli-reference.py",
    REPO / "templates" / "assembly-root" / "scripts" / "validate-pins.py",
    REPO / "templates" / "assembly-root" / "scripts" / "validate-manifest.py",
    REPO / "templates" / "assembly-root" / "scripts" / "bootstrap.py",
    REPO / "templates" / "family-root" / "scripts" / "validate-family.py",
    REPO / "templates" / "family-root" / "scripts" / "bootstrap.py",
    REPO / "templates" / "family-root" / "scripts" / "siblings.py",
]
#: `bootstrap` joins them on 2026-09-09 (#76): the holder's `siblings.py`
#: imports the credential resolution and the member rows from the
#: `bootstrap.py` beside it rather than defining either a second time, and the
#: two files travel together in `contracts/shape-pin.yaml`. It is a local
#: module in exactly the sense the other four are — a file this standard
#: ships, never a package anybody installs.
#:
#: `scripts/render-cli-reference.py` joins them on 2026-09-11 (#97). It
#: reaches no scaffolded project — it renders `docs/cli.md` from the other
#: tools' own `--help` — but it is non-test code in this repository, and a
#: fork that cannot install anything still has to be able to regenerate the
#: reference after it changes a tool. The rule costs it nothing and the
#: category it would otherwise sit in is "nothing checks this file".
LOCAL_MODULES = {"repo_shape", "shape_materialize", "path_classify",
                 "conftest", "bootstrap"}

#: The bash scripts a person runs BEFORE they have a checkout, or with no
#: checkout in sight at all: the front door itself and the command that
#: fetches it. `park` and `resume` were here from #82 until the carve (#92)
#: and are opensoft/openRepoTools' now, held to these same rules by that
#: repository's own copy of this test. Every one is a shipped executable and
#: is held to the same shebang, mode bit and `set -euo pipefail` rule.
SHIPPED_BASH = ["setup.sh", "openRepoShape"]

#: The entry point a person runs BEFORE they have a checkout on a machine with
#: no bash: the same front door, on an interpreter alone. Held to the same
#: shebang and mode bit, and to one rule the bash pair is not - see
#: `test_setup_project_py_is_pure_ascii`.
SHIPPED_PYTHON_ENTRY = ["setup-project.py"]


@pytest.mark.parametrize("path", SHIPPED, ids=lambda p: p.name)
def test_shipped_code_imports_only_the_standard_library(path):
    """No pip, ever.

    The shape must run in an organisation that forked it and cannot install
    anything on the machine where the scaffold runs. That constraint is what
    forces the small YAML reader in `repo_shape.py`; this test is what keeps
    somebody from quietly undoing it with a one-line `import yaml`.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    foreign = imported - sys.stdlib_module_names - LOCAL_MODULES
    assert not foreign, f"{path.name} imports outside the standard library: {foreign}"


def test_every_shipped_script_compiles():
    for path in SHIPPED:
        compile(path.read_text(encoding="utf-8"), str(path), "exec")


@pytest.mark.parametrize("template", ["assembly-root", "family-root"])
def test_the_materializers_account_for_every_template_file(template):
    """A file added to a root template but named in no copy list would
    silently never reach a scaffolded project or family.

    The lists moved into `scripts/shape_materialize.py` when the scaffold and
    `adopt-project.py` stopped carrying one each, so every caller is read
    here: the property is "some materializer names this file", not "one
    particular module does". `spec-root/` and `code-root/` are absent on
    purpose — they are copied WHOLESALE by `copy_tree`, so there is no list
    for a file there to fall out of.
    """
    source = "\n".join(path.read_text(encoding="utf-8") for path in (
        SCAFFOLD, REPO / "scripts" / "shape_materialize.py",
        REPO / "scripts" / "family.py", REPO / "adopt-project.py"))
    template_root = REPO / "templates" / template
    for path in sorted(template_root.rglob("*")):
        if path.is_dir() or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(template_root).as_posix()
        assert f'"{rel}"' in source, (
            f"{rel} is in templates/{template}/ but is named in none of the "
            "copy lists in scripts/shape_materialize.py, so no materializer "
            "would ever write it"
        )


#: The one line that makes a digest pin survive a clone on a machine set up
#: the way Git for Windows sets one up (#51, 2026-09-05). Spelled here so a
#: rewrite of the comment block above it cannot quietly drop the rule.
EOL_RULE = "* text=auto eol=lf"


@pytest.mark.parametrize("template", ["assembly-root", "family-root"])
def test_a_root_template_says_what_its_bytes_are(template):
    """Both roots pin copies by sha256, so both must state their line endings.

    `scripts/validate-pins.py` digests the bytes ON DISK. Git for Windows'
    installer default is `core.autocrlf=true`, so without this file a clone
    there writes CRLF and every pinned row is false — for a colleague who did
    nothing but clone. `setup-project.py` covers the run the tool controls;
    only a file IN the project covers the next person.
    """
    path = REPO / "templates" / template / ".gitattributes"
    assert path.is_file(), (
        f"templates/{template}/ pins its copies by digest and must say what "
        "their line endings are")
    data = path.read_bytes()
    assert b"\r" not in data, "the file that says LF is itself LF"
    text = data.decode("utf-8")
    assert EOL_RULE in text, (
        f"templates/{template}/.gitattributes must carry `{EOL_RULE}`; an "
        "`eol` attribute is what overrides a cloner's core.autocrlf")
    assert "#51" in text and "2026-09-05" in text, (
        "the rule is cited by issue and date, like every other ruling here")


def test_the_two_root_templates_agree_about_line_endings():
    """BYTE-IDENTICAL, because the two are one rule.

    A family holder and an assembly root carry the same kind of copy pin, so a
    fix to the reasoning in one that never reached the other would leave half
    the standard explaining itself and the other half asserting it.
    """
    assembly = REPO / "templates" / "assembly-root" / ".gitattributes"
    family = REPO / "templates" / "family-root" / ".gitattributes"
    assert assembly.read_bytes() == family.read_bytes()


def _only_rule_lines(text: str) -> list:
    """Every non-comment, non-blank line of a `.gitattributes` file.

    Shared by the root's own test and the agreement test below it, so a
    header that grows a blank line or an extra `#` paragraph never touches
    either assertion — only the RULE does.
    """
    return [line for line in text.splitlines()
           if line.strip() and not line.lstrip().startswith("#")]


def test_the_repository_root_carries_the_rule_too():
    """Copilot's comment on PR #58 (#51's PR), read after the merge and
    acted on at #63: the two TEMPLATES got `.gitattributes` so a SCAFFOLDED
    project's clone would not turn LF into CRLF, but the standard's own
    checkout - the one `tests/` itself runs from - had none.
    `unname_everywhere()` in `tests/test_update_shape_add.py` strips a
    copy-list entry by matching it as a WHOLE LINE, so a checkout made under
    Git for Windows' `core.autocrlf=true` installer default turns this
    repository's own `\n` into `\r\n` and that match goes blind - CI never
    saw it because it pins `autocrlf=false`.
    """
    path = REPO / ".gitattributes"
    assert path.is_file(), "the repository's own root has no .gitattributes"
    data = path.read_bytes()
    assert b"\r" not in data, "the file that says LF is itself LF"
    text = data.decode("utf-8")
    assert _only_rule_lines(text) == [EOL_RULE], (
        f"the root .gitattributes' only rule line must be `{EOL_RULE}`")
    assert "#63" in text, "the rule is cited by the issue that added it"


def test_the_root_and_both_templates_agree_about_the_rule():
    """Three copies, one rule: the two templates (for a SCAFFOLDED project's
    clone) and the repository's own root (for a clone of openRepoShape
    itself). Their headers differ on purpose - each explains the rule for
    its own audience - so this compares the RULE LINE alone, not the bytes,
    which is what `test_the_two_root_templates_agree_about_line_endings`
    already does for the two templates.
    """
    root = _only_rule_lines((REPO / ".gitattributes").read_text(encoding="utf-8"))
    assembly = _only_rule_lines((REPO / "templates" / "assembly-root" /
                                ".gitattributes").read_text(encoding="utf-8"))
    family = _only_rule_lines((REPO / "templates" / "family-root" /
                              ".gitattributes").read_text(encoding="utf-8"))
    assert root == [EOL_RULE] == assembly == family


def test_the_shape_pin_template_carries_a_files_block():
    text = (REPO / "templates" / "assembly-root" / "contracts" /
            "shape-pin.yaml").read_text()
    assert "{{SHAPE_FILES}}" in text
    assert "materialization: copied" in text


def test_agents_md_is_short_enough_to_be_read():
    """The cap moved 80 -> 140 on 2026-09-02, once, because the file now
    carries THREE procedures rather than one: scaffold, adopt an existing
    repository, and scaffold a declared descendant. An adopt procedure that
    lived outside the file an assistant is told to read is an adopt procedure
    performed from memory, which is the failure this file exists to prevent.
    The cap still bites: it is what stops the third procedure from growing
    into an essay.

    140 -> 175 on 2026-09-03, for the FOURTH procedure: updating a project
    whose copied shape files have fallen behind. It earns its lines the same
    way adopt did — the copies are what make a project self-contained, and
    before this there was no command to move them, so both projects carrying
    the shape were updated by hand. A procedure performed from memory is the
    failure this file exists to prevent.

    175 -> 235 on 2026-09-04, for two more of them, both from the same
    ruling. Adopting a repository with NO CODE YET seeds the empty leg and
    takes `--allow-empty-leg`, which an assistant must get a human's word for
    rather than pass because the tool asked; and a FAMILY holder is created
    and grown by a tool that has no prompt of its own, which makes getting
    the yes the assistant's job and is exactly the kind of thing that must be
    written down rather than remembered.

    235 -> 266 on 2026-09-05, for the SEVENTH: advancing a leg. The lockstep
    rule was written down in three places and performed by hand in every
    project, which is the arrangement that let seven consecutive pin-syncs in
    the xFactory aggregation move the gitlink alone. `bump-leg.py` moves the
    three facts together, so the procedure block is mostly what an assistant
    must NOT do — hand-edit the pin to satisfy the validator, push to the
    default branch, or work around a refusal by pinning a commit the leg's
    remote does not have.

    266 -> 269 on 2026-09-05, for the `openRepoShape` command (#38): three
    lines saying that `openRepoShape <Project> --org <org> ...` is the same
    run as the one-liner, still without `--yes`. A second way in that this
    file does not name is a way in performed from memory, and the rule it
    must not lose on the way is the one this file opens with.

    269 -> 273 on 2026-09-05, for the NATIVE WINDOWS way in (#49): three lines
    saying that `Invoke-WebRequest ... -OutFile setup-project.py` and then
    `py setup-project.py <Project> --org <org> ...` is that same run a THIRD
    time. Same argument as #38's, with one thing added that an assistant
    cannot work out for itself: it is two commands rather than one pipe
    because a piped script cannot ask, so an assistant that "helpfully"
    folds them into a pipe has removed the one `yes` this file opens with.

    273 -> 277 on 2026-09-05, for the GUIDED PREFLIGHT (#59). Brett Heap, in
    session: "why not have an install program that will do all this? so the
    user gets our program and then runs that and we do all this?" — then
    "yes" to an offer rather than an installer. The preflight now asks `Type
    yes to continue:` for an INSTALL as well, and this file's first rule
    covers only the repository-creation prompt. An assistant that reasoned
    from the first rule to "so I may answer the other one" would be
    installing software on somebody's machine on its own initiative, which is
    a bigger act than the one already forbidden — so the rule is written down
    beside it rather than left to be inferred.

    277 -> 282 on 2026-09-09, for `--family` and the family FOLDER (#76,
    RULING ruling 2). One line is the flag's row in section 1's table; four
    are the sentence in section 2 saying that standing in a family folder is
    DETECTED and said in the plan with no flag. An assistant cannot work
    either out: the row has to say that the flag lands the clone one level
    deeper AND records nothing in the project — membership lives in the
    holder's `family.yaml` and nowhere else — and the sentence has to say
    that a plan line about a family is a REPORT rather than a thing the
    assistant asked for, or the next assistant "corrects" it by adding the
    flag.

    282 -> 308 the same day, for the other half of the same ruling (#76, and
    the family side of it): the procedure gained the WORKSTATION LAYOUT.
    Seven lines say where `family.py init` LANDS, because the doubled
    `<Family>/<Family>` reads like a mistake until somebody explains it and
    an assistant that "fixed" it would move a checkout. The rest is `make
    siblings` / `family.py siblings` and, mostly, what they NEVER do: they
    move nothing — and neither may the assistant, `mv` in hand, because the
    warning prints one — and they touch no existing clone beyond a fetch. A
    rule about not moving somebody's checkout is the one an assistant cannot
    infer from the others, which is why it is written down beside them rather
    than left to the tool to enforce.

    308 -> 342 the same day, for `make park` and `make resume` (#77, RULING
    2026-09-09, rulings 1 and 5). Six lines and a command block are the
    procedure — the two verbs, the rehearsal, and the clone-then-bootstrap-
    then-resume order on the far machine. The four numbered rules are the
    part an assistant gets WRONG, and each one costs somebody's work if it
    is inferred instead of read: the overlay is a PREREQUISITE and the
    refusal names `setup-openspeckit`, so a refused target is never a cue to
    hand-roll the WIP commit or the soft reset; `resume` refusing on
    DIVERGENCE means somebody else's commit is on that branch, so it is not
    a thing to reset over or re-park on top of; a parked WIP commit is a real
    pushed commit, so the `--force-with-lease` the tool prints is the
    person's to run and never the assistant's; and nothing under
    `worktrees/` is ever committed, the workspace manifest is the person's in
    a repository they own, and a holder's per-member lines have to be read
    before anyone is told the estate is parked — a member SKIPPED for want of
    a working clone beside the holder was never asked at all, which is the
    one outcome an assistant reads as success. The mechanics themselves are
    the Speckit git extension's and are deliberately NOT described here.

    342 -> 344 on 2026-09-10, for point 4's exception (#84). `apply` had
    refused every `both` row before it ever consulted `--accept-local`, so
    the exit this file already documented — merge by hand, commit, re-run
    with `--accept-local <path>` — could never actually be taken; the tool
    was fixed to match the file rather than the other way around. The one
    sentence added says where that commit goes: on the branch `apply` is
    then pointed at with `--branch`, because that is the checkout the
    documented exit leaves behind, and an assistant that recreated the
    branch instead of committing onto the one already there would be
    re-running the tool at the wrong git state.

    344 -> 366 on 2026-09-09, for the two INSTALLED COMMANDS (#82, RULING
    2026-09-09). Nine lines are the paragraph: that `park <Name>` and `resume
    <Name>` are the same verbs on PATH, how they find the estate, and that
    their per-repository lines are to be relayed rather than summarised — an
    assistant that did not know the commands existed would hand somebody a
    hand-built `cd`-and-`make` sequence for a thing that is one word. The two
    numbered rules are the part that costs work if it is inferred: `park`
    with no estate around the cwd REFUSES and lists what it found, which is
    not an invitation to pick one, and `resume` refusing a dirty or
    feature-branched clone BY NAME is not a state to `git reset`, `git stash`
    or `git checkout -f` out of the way — that clone holds the very work the
    refusal exists to protect, and an assistant tidying it away is the worst
    outcome this whole object has. The last rule is about the one file this
    standard writes outside a repository: which private repository holds
    somebody's unfinished work is theirs to name, so `--workspace` is never
    passed on an assistant's own initiative.

    366 -> 370 on 2026-09-09, for the adversarial review on PR #83. Four
    lines, all of them one refusal an assistant would otherwise "fix": a root
    whose LEG sits on a feature branch is refused BY THE LEG'S NAME, because
    the superproject is CLEAN in that state and the thing that would move the
    leg is the root's own `make bootstrap`. An assistant that read only "dirty
    or on a feature branch" would look at a clean root, conclude the refusal
    was spurious, and run `git checkout main` in the leg — which is the exact
    loss the guard exists to prevent, performed by hand. The other half-line
    says a refused clone is not given the verb either, so nobody reports the
    estate resumed because the verb ran somewhere.

    370 -> 374 on 2026-09-10, for the sixth naming form (#81). Three lines,
    and all three are one sentence in "What you must not tell them": that a
    `<user>-wip` workspace repository confers nothing either. That section
    already refuses the shape and family membership, and an assistant
    reasoning from those two to a third kind of name would be reasoning about
    the one repository in this standard that holds somebody's unfinished work
    — an index of what a person has not finished reads like standing unless
    somebody says it is not one, and it is also the one name here that no tool
    here creates.

    374 -> 381 the same day, for park-everything (#91, RULING 2026-09-10):
    bare `park` with no `<Name>` and no estate around the cwd now PARKS EVERY
    ESTATE instead of refusing, superseding ruling 3 of #82 for that one case.
    Point 5's opening sentence is the part an assistant gets wrong if it is
    inferred rather than read: that refusal is GONE, so telling somebody to
    name one estate when they typed a bare `park` in the wrong folder is now
    stale advice, not a courtesy. The second half is the part that stays a
    refusal: `resume`'s own bare form keeps ruling 3 deliberately, because
    rebuilding every estate on a fresh machine by accident is the opposite
    risk, and an assistant is never to name one estate on the person's behalf
    to route around it.

    381 -> 351 on 2026-09-10, DOWNWARD, for the carve (#92): `park` and
    `resume` are opensoft/openRepoTools' commands now, so the
    installed-commands paragraph and points 5 and 6 left this file for that
    repository's AGENTS.md, and two lines pointing at it replace them. The
    cap follows the file down rather than banking thirty lines nobody argued
    for — the two entries above it earn their headroom with rules that are no
    longer here, and a cap left at 381 would let the next procedure spend
    them without anybody making the case. Points 1-4 stay: they are about
    `make park` and `make resume`, which this standard still ships in both
    root templates.


    2026-09-10: 351 -> 390 — `## Checking a repository's compliance` (#95).
    Thirty-eight lines and one clause, for a command that did not exist: the
    procedures above each describe ONE act, and nothing here told an
    assistant how to find out which of them a repository needs. The five
    numbered points are the five ways an agent gets a doctor's report wrong.
    Reading the VERDICT and not the rows, because the verdict names the most
    specific finding and the table names every one. Improvising a repair
    instead of running the command the row NAMES — the same hand-edited-pin
    failure `update-shape.py`'s own points are about, arriving through a new
    door. Treating `NOT A SHAPE ROOT` as a task, when adopting and
    scaffolding are two different acts and choosing between them is the
    human's. Reading the `machine` row as a fault in the repository, when it
    is `n/a` and about the workstation. And `--json`, one line, because an
    agent acting on a row should not be parsing a table. The clause is one
    more item in the opening paragraph's list of what the sections cover.

    2026-09-10: 390 -> 395 — the two shim behaviours (#95, on Brett Heap's
    "add the two shim behaviours too"). Five lines under section 2, where an
    assistant already reads what the installed command does: that a BARE run
    prints usage and exits 1 rather than refusing about an organisation
    nobody asked about, that `--install` ends with a read-only `machine:`
    block, and — the half an assistant gets wrong — that NEITHER installs
    anything, so the block is relayed and `--preflight` is the human's to
    run. An assistant who read only the first half would answer the block by
    installing something.

    2026-09-10: 395 -> 400 — the adversarial review on PR #96. Five lines:
    one numbered point saying `note` is not a finding and is not "fixed"
    (the row that answered INVALID over a live estate now says `note`, and
    an assistant who reads it as a finding would go and change somebody's
    leg), and the `CANNOT ANSWER` / exit 3 half-sentence in point 1 —
    because that verdict is THIS CHECKOUT failing to ask, and an assistant
    who relays it as a verdict about the repository has relayed the
    opposite of what happened.

    2026-09-11: 400 -> 408 — `docs/cli.md` (#97). Brett Heap: "do we have
    documentation designed for an AI to understand what our CLI can do and
    how to use it?" -> "add the docs/cli.md". Seven lines and a blank one, in
    the opening, for a file that did not exist until that ruling: this file
    is PROCEDURE-first by design and the flags lived only inside seventeen
    separate `--help` texts, so an assistant that needed a spelling either
    ran seventeen commands or worked from memory. The paragraph says four
    things, and an assistant can infer none of them. That the reference
    EXISTS at all. That it is GROUPED, because six of the tools are copies
    that run from inside a scaffolded project and not from a checkout of this
    standard, and a flat list would have an agent running `validate-pins.py`
    where there is no manifest. That THIS FILE STILL OUTRANKS IT — a flag
    being documented is not permission to pass it, which is the failure a
    flag list invites and the reason one was not written before. And that it
    is GENERATED, so a line that has gone stale is fixed by regenerating and
    never by editing the document, which is the hand-edited-pin rule arriving
    through a new door.

    2026-09-11: 408 -> 423 — the `placement` row (#99), landing after #97 the
    same day. Twelve lines are one numbered point, because the way an
    assistant gets THIS row wrong is specific and expensive: it names paths
    that are in the wrong REPOSITORY, and the obvious repair is wrong twice
    over. A path changing legs is a pull request on the leg it leaves, a pull
    request on the leg it joins and one pin bump in the root — none of which
    an agent does on its own initiative — and a `review_required` entry is a
    question the POLICY is asking, so answering it on the human's behalf puts
    a fact in their tree that nobody decided. That is the same shape of
    mistake as hand-editing a pin, arriving through a door that did not exist
    yesterday. Two lines put `MISPLACED` and its exit code in point 1's
    verdict list, which is what a scheduled job reads. One is the
    `--placement-plan` caveat on the opening paragraph: "it writes nothing"
    was absolute and is not any more, and an absolute sentence with an
    undocumented exception is how the exception gets found by surprise.

    2026-09-11: 423 -> 433 — the commit `--trailer` (#111), later the same
    day. Eight lines are one numbered point under "Updating a project's
    shape" and two a clause in the family section, and they buy the one
    thing `docs/cli.md` cannot: PERMISSION. A flag listed there is not
    permission to pass it — this file's own opening paragraph says so — and
    the flag an assistant now has to pass is the one the lane-collision
    protocol requires on a commit. Four InkRouter re-pins landed carrying
    neither `Lane:` nor `Co-Authored-By:` because both tools were run
    exactly as their own `NEXT` lines printed them; a point saying which
    trailers to pass, and that the printed line already carries the lane, is
    what makes the next run land complete rather than amended by hand."""
    lines = (REPO / "AGENTS.md").read_text().splitlines()
    assert len(lines) <= 433, f"AGENTS.md is {len(lines)} lines; the cap is 433"


def test_claude_md_points_at_agents_md():
    assert "AGENTS.md" in (REPO / "CLAUDE.md").read_text()


def test_readme_is_short_enough_to_be_read():
    """The cap moved 150 -> 172 -> 245 on 2026-09-02, twice in one day and
    both times for a rule the standard actually gained: first the referent
    ruling, then adoption in place — a second tool, a second policy file and
    the MedxEHR worked example that makes the three decisions arguable rather
    than folkloric. A cap that never moves for a rule pushes the rule into
    tribal memory instead; a cap that moves for prose is not a cap.

    It moved again, 245 -> 265, on 2026-09-03: the `SHAPE_LEGS_TOKEN` rule
    that fixed the first real adoption's red `validate` check on private
    legs (MedxSoft/MedxEHR #7).

    And again, 265 -> 267, later the same day: the `SHAPE_LEGS_TOKEN`
    paragraph now also notes that its presence check is a job-level `env:`
    value rather than the `secrets` context in a step `if:` — the fix for
    the next real-adoption defect (MedxSoft/MedxEHR PR #8, MedxSoft/MedxGlass
    PR #1: `secrets` in a step `if:` makes GitHub reject the whole workflow
    file, a push-event run with zero jobs).

    267 -> 324, the same day again, for "Keeping a project's shape current".
    The copies are the standard's central trade — a project that runs its own
    gate offline is a project an upstream fix reaches never — and until that
    day the other half of the trade was two projects updated by hand and no
    command at all. What the tool REFUSES is most of the section, because a
    re-pin that hid drift would have been worse than the hand edit it
    replaced.

    324 -> 331, the next day: the `SHAPE_LEGS_TOKEN` paragraph now also
    explains why the ROOT checkout never carries `token:` at all — the
    first real use of the secret put a legs-scoped token onto the root
    checkout and `actions/checkout` itself failed with a 403
    (MedxSoft/MedxEHR and MedxSoft/MedxGlass, runs 33821509948 and
    33821512605) — and that the token is now read only inside the guarded
    submodule-fetch step, via a `git -c url.<...>.insteadOf=<...>` rewrite
    covering both HTTPS and SSH leg URLs.

    331 -> 359, the next day again: Brett Heap ruled *move this to a GitHub
    App*. The `SHAPE_LEGS_TOKEN` section became "Reading private legs in
    CI" — a GitHub App (minted at run time, scoped to the legs the owner
    itself owns) tried first, the PAT kept as fallback — because a standing
    PAT is a credential that sits in a secret indefinitely and a per-run
    installation token is not.

    359 -> 388, on 2026-09-04: Brett Heap ruled *drop the fork*. Every
    scaffolded project already pins `opensoft/openRepoShape` directly and
    `update-shape.py` reads straight from upstream, so a per-organisation
    fork never did anything but host `setup.sh` — and its origin-based org
    detection was itself a defect. The Quick start is now one `curl | bash`
    line (plus the `gh api` form for orgs that block raw downloads) that
    self-bootstraps a temporary checkout, scaffolds, and cleans up; the "from
    a checkout" form survives as the developer path. A cap that grew for
    dropping an instruction, not adding one, is still a cap earning its
    lines: the one-liner and its self-bootstrap explanation replace a
    fork-and-clone paragraph with a longer one, because "how to run this
    safely with no fork" takes more words than "fork it first".

    388 -> 401, on 2026-09-04 again: `validate-pins.py` now RECHECKS a
    declared `neutral_product_pins:` referent, not merely trusts the
    declaration — the pin's commit, `revision_kind` and digest are
    recomputed the way `scaffold-project.py --pin` computed them the first
    time, from a local checkout (`--pin-source`, an env var, or a sibling
    checkout) or `gh api`, and a named SKIP rather than a failure when
    neither can answer. A rule that only the tool WRITING a pin ever checked
    it again was a gap the standard's own claim-needs-a-referent ruling had
    not closed.

    401 -> 508, the same day: two additions the standard gained rather than
    prose. A leg with NOTHING IN IT is seeded from its template instead of
    extracted (InkRouter's services are specifications with no code), which
    is a paragraph because the consent flag and the verification row both
    need explaining. And the FAMILY shape is a whole section, because the
    first question anyone asks about it — family or one project? — is
    answered by a table and an example rather than by a definition, and
    because "what a holder does NOT confer" is the half that keeps it from
    becoming a governance boundary."""
    lines = (REPO / "README.md").read_text().splitlines()
    # 2026-09-04: 508 -> 509 — the election reference paragraph now names the
    #   ratified docs/project-repo-schema.md and keeps the staged path valid for
    #   projects elected before ratification (Brett Heap's edit, PR #19).
    # 2026-09-04: 509 -> 513 — the same paragraph now says WHICH of the two the
    #   tools write by default, because PR #19 left one default for two eras
    #   and a project dated before ratification recorded the ratified path.
    #   Four lines for a rule the reader would otherwise have to read the
    #   scaffold's source to learn.
    # 2026-09-04: 513 -> 532 — `upstream-added` and `--add`. The section said
    #   the file list is never re-derived from the copy lists, which is right
    #   about what is RE-SYNCED and was silently also true of what is LOOKED
    #   AT: a file the standard added after a project was cut reached that
    #   project never, and `AGENTS-shape.md` was the first one to prove it.
    #   The paragraph is long because the verdict is only half of it — the
    #   three refusals and the open question (a project cannot yet decline an
    #   addition) are the half a reader would otherwise learn from a surprise.
    # 2026-09-04: 532 -> 544 — a scaffolded project now carries an AGENT FILE.
    #   One line names `AGENTS-shape.md` among the copies and one names it in
    #   the layout; the other ten are the paragraph saying WHY the shape's own
    #   text is pinned (a rule against editing pinned files is worthless if
    #   the file carrying it can be edited, which is also why it holds no
    #   rendered project detail) while the project's `AGENTS.md` and
    #   `CLAUDE.md` are rendered and are not. That trade is the same one the
    #   copies themselves are, and it was nowhere in this file.
    # 2026-09-05: 544 -> 573 — "Advancing a leg", the command that moves the
    #   three lockstep facts together. The section defined the invariant and
    #   named the validator that refuses when it breaks, and said nothing at
    #   all about how to MOVE it, so every project moved it by hand — which is
    #   the arrangement the invariant was written down about. Most of the
    #   added lines are the refusals, for the same reason the update section's
    #   are: a bump that hid drift would be worse than the hand edit it
    #   replaced. One more line names it in the Layout block.
    # 2026-09-05: 573 -> 659 — "A worked example: Northwind starts Atlas"
    #   (#36). The one-liner, the naming policy and the private-legs
    #   credential were each documented in the abstract already; nothing
    #   showed what a first run of the whole thing produces. The section adds
    #   one continuous walk-through instead — who needs to do what before
    #   starting and why (the `gh` account that creates the repositories is
    #   not the same fact as the `--elected-by` name), the one-liner filled
    #   in, what Dana sees at each prompt, the tree a scaffold writes today,
    #   advancing a leg, and the variants — without repeating the one-liner,
    #   the `gh api` alternative, the `--org` rule or the no-fork rule
    #   already said above it.
    # 2026-09-05: 659 -> 699 — the way in, restructured around the
    #   `openRepoShape` command (#38). The example's PREREQUISITES are now two
    #   parts, the requirements and the login, because the `gh` account that
    #   creates the three repositories is the half a newcomer gets wrong and
    #   is not the same fact as the `--elected-by` name. Then the two ways in
    #   — install the command, or type the long line — and the run itself.
    #   Most of the added lines are the two install forms and what installing
    #   does to the machine (idempotent by content, and the PATH line), which
    #   a reader is owed before piping anything to bash. Two more name the
    #   short form under the one-liner at the top and one names the file in
    #   the Layout block.
    # 2026-09-05: 699 -> 700 — one line, for #39: the example now says WHERE
    #   the clone lands (the directory you ran the command from, as
    #   ./Atlas), because self-bootstrap mode used to leave it in /tmp and
    #   the sentence that said `../Atlas` was true of neither path.
    # 2026-09-05: 700 -> 725 — the referent may be reached through a CHAIN of
    #   pins ("follow the pin chain", Brett Heap, openxFactory#656). Two
    #   paragraphs rather than a sentence because the rule has two halves that
    #   fail differently: WHAT is recorded (the chain, in the descendant's own
    #   manifest, first entry the pin it holds and last the referent it
    #   claims) and WHAT HAPPENS TO A LINK IN ANOTHER TREE — verified where
    #   that tree is on the disk, `declared-unverified` where it is not, and
    #   broken only where a readable tree says otherwise. A reader who learnt
    #   only the first half would read the warning as a failure, which is the
    #   offline principle inverted.
    # 2026-09-05: 725 -> 743 — a NEUTRAL PRODUCT may elect the shape and be its
    #   own assembly root (the second half of "elect the shape for both",
    #   Brett Heap, openxFactory#656; issue #41). One paragraph, and it is a
    #   paragraph rather than a sentence because the rule has two halves a
    #   reader gets wrong separately: the form still WINS the classification
    #   (`form: neutral-product, role: assembly`, the leg form recorded in
    #   `also_matches`), and electing confers NOTHING, which is the only
    #   reason a neutral product carrying two legs is a layout fact instead of
    #   a claim about its neutrality. The last two lines say what is still
    #   refused — `<X>-Install` is admitted into no role — because a relaxation
    #   whose edge nobody states is read as a general one. It is its own `###`
    #   subsection, not a paragraph tacked onto the descendant-form one above
    #   it, so a reader scanning headings finds the rule.
    # 2026-09-05: 743 -> 821 — "Quick start for a first-time user" (#43). A
    #   first-time user could not find how to install `gh` at all, and the
    #   simplest way in — install the `openRepoShape` command, then
    #   `openRepoShape <Project> --org <org>` — sat inside the worked example,
    #   after the `curl | bash` one-liner and its `gh api` variant, where a
    #   newcomer reading top to bottom met it last instead of first. The new
    #   section is four numbered steps ahead of both: install `gh` (with the
    #   official Debian/Ubuntu and Fedora package commands, copied from
    #   cli.github.com's own install page, and a platform paragraph for
    #   Windows, which has no native path today and needs WSL2), log in and
    #   configure the credential helper, install the command, then run it.
    #   The existing one-liner is relabelled as the alternative it is
    #   ("without installing anything") rather than deleted, and the
    #   Requirements line in the worked example now points at the install page
    #   instead of assuming the reader already has `gh`.
    # 2026-09-05: 821 -> 872 — a NATIVE WINDOWS path (#49). The Quick start
    #   said Windows had none and to install WSL2 first, which made every
    #   Windows reader install a second operating system to run two Python
    #   scripts. `setup-project.py` is `setup.sh`'s twin on an interpreter
    #   alone, so the platform paragraph becomes the install list (python.org
    #   with *Add python.exe to PATH*, git-scm.com, `winget`), the one machine
    #   setting `core.autocrlf false` and WHY a digest-pinned copy makes it
    #   matter, the two-liner itself, and the paragraph that keeps it two
    #   commands: PowerShell 5.1 re-encodes piped text as ASCII and writes
    #   UTF-16 through `>`, and a script arriving on stdin cannot ask for the
    #   one `yes`. Most of the added lines are those two explanations, and
    #   they earn them — a reader who does not know either one will "simplify"
    #   the pair into a pipe. Three more say the same run spells itself
    #   `python …` on a machine the Store's Python installed, which has no
    #   `py` at all. WSL2 stays, demoted to what it actually is: how to run
    #   the BASH entry points. Two more lines name the file under "What
    #   setup.sh does" and in the Layout block.
    # 2026-09-05: 872 -> 881 — `.gitattributes` (#51). Six lines are the
    #   paragraph under "Bootstrap is COPIED into the project", and they are a
    #   paragraph rather than a clause because the reader has to be told the
    #   mechanism to believe the file: the pin digests the bytes ON DISK, Git
    #   for Windows installs `core.autocrlf=true`, and the failure therefore
    #   lands on a colleague who did nothing but clone — the one person with
    #   no reason to suspect a line-ending setting. #49 fixed the clone the
    #   TOOL performs; only a file in the project reaches the next one. The
    #   other three lines name it in the worked example's tree, in the Layout
    #   block, and nowhere else.
    # 2026-09-05: 881 -> 945 — the MAC path, a rehearsal that creates nothing,
    #   and what a failed scaffold leaves (#54), on Brett Heap's words: "we
    #   have the case for windows only and wsl/linux users and mac users. we
    #   need to make sure it is explained for all." The Quick start's one line
    #   for two platforms becomes a Linux line and a macOS paragraph — where
    #   `git`, `make` and a `python3` come from (the Xcode Command Line
    #   Tools), that Homebrew is itself an install and prints the `PATH` line
    #   Apple Silicon needs, that the stock `/bin/bash` 3.2 is enough, and
    #   that the zsh login shell is beside the point because both entry points
    #   run under `bash` explicitly. The bash-3.2 half is the one a document
    #   cannot hold true on its own, so `.github/workflows/tests.yml` gained a
    #   `macos-latest` job that runs the whole suite there and parses both
    #   entry points with `/bin/bash` itself. A parse settles SYNTAX and
    #   nothing else, so SYNTAX is the only word the paragraph claims, and it
    #   says CI parsed on `macos-latest` rather than asserting which bash
    #   answered there — the job prints `--version` because a document cannot
    #   know that either.
    #   The other two additions are things a novice could not do at all.
    #   `--local-remote-dir` rehearses the whole run against three bare
    #   repositories: `gh` is never called, nothing is created on GitHub, and
    #   `--org` is a string nothing checks, so the organisation need not
    #   exist. Its paragraph also says what is NOT offline — the
    #   `openRepoShape` command fetches `setup.sh`, and `setup.sh` then
    #   self-bootstraps a clone of this standard, both over the network,
    #   before any of the rest runs — because the first draft said "no
    #   network" of a route that has two, and only `./setup.sh` from a
    #   checkout touches none. The failing-part-way paragraph says which
    #   phases write nothing, that the three are created spec, code, root —
    #   the root LAST — that there is NO rollback, whose message it is
    #   quoting when it says so (a failed push's), and which exits are real
    #   (`--reuse-empty-repo` for a zero-commit ROOT only, `gh repo delete`
    #   with the `delete_repo` scope, or a different name). Both are
    #   paragraphs rather than sentences because a reader who learns half of
    #   either acts on the half.
    #   Three more lines close a gap Copilot flagged in PR #57: the paragraph
    #   also names the exit when the Tools' python3 is too old, because the
    #   original read as claiming the Tools' python3 always suffices.
    # 2026-09-05: 945 -> 948 — three lines under "What setup.sh does" (#50).
    #   `setup.sh` is a SHIM over `setup-project.py` now, not a second
    #   implementation of the same flow, and the section that lists the
    #   commands has to say so before it lists them. A reader who took the old
    #   opening sentence at face value would go into `setup.sh` looking for
    #   the preflight, the naming check and the plan, and find a clone and a
    #   hand-over. The three lines are that sentence, and the paragraph that
    #   follows the block now says what `setup-project.py` is by the same
    #   measure rather than repeating the list of substitutions.
    # 2026-09-05: 948 -> 967 — the GUIDED PREFLIGHT (#59). Brett Heap, in
    #   session: "why not have an install program that will do all this? so
    #   the user gets our program and then runs that and we do all this?" —
    #   then "yes" to an offer rather than an installer. Twelve lines are the
    #   lead that says the four steps are the REFERENCE and the tool offers
    #   the rest, on what terms (a typed `yes` each time, never `--yes`, never
    #   Homebrew, no terminal no offer), and that `--preflight` checks a
    #   and creates nothing. Four more are the `git` install commands for the
    #   four platforms: a command this tool would RUN that no document shows
    #   is exactly what `test_the_offer_commands_are_the_ones_the_readme_
    #   documents` refuses, and the person who declines an offer reads the
    #   same line to type by hand. The rest are one clause in the worked
    #   example's preflight sentence and one naming `--preflight` in its
    #   requirements, because a reader who meets the offers only in the Quick
    #   start meets them once.
    # 2026-09-06: 967 -> 971 — issue #68, Brett Heap's ruling in session: "fix
    #   the two readme lines and merge on green too". One line is the fifth
    #   naming family the Layout block had not caught up with — the FAMILY
    #   shape (v0.4, #16) made it five and the block still said four; one word
    #   fixes it. The rest is the Windows spelling of the rehearsal flag:
    #   `--local-remote-dir` was documented only in the bash one-liner, so
    #   "Rehearse first, creating nothing" now also gives `py
    #   setup-project.py Atlas --org <your-org> --local-remote-dir
    #   .\rehearsal` and says what it still does over the network — the same
    #   self-bootstrap clone into a temporary directory when run from a
    #   download, and nothing when run from a checkout, that the paragraph
    #   already said of `./setup.sh`.
    # 2026-09-06: 971 -> 1014 — issue #72, Brett Heap's ruling in session: "do
    #   the github-native readme pass and merge on green too". Structure only:
    #   NO SENTENCE CHANGED, and the pass is provable in reverse — strip these
    #   43 lines and the file is byte for byte what it was. Twelve are a
    #   contents list of anchor links, one per `##` section plus the Quick
    #   start, which is the whole navigation a 971-line front page had none of.
    #   Three are callout markers on paragraphs that were already there, one
    #   each by role: `> [!IMPORTANT]` on "the shape confers nothing",
    #   `> [!NOTE]` on the consent rules ("The tool offers the rest"),
    #   `> [!WARNING]` on what a failed scaffold leaves behind. Fifteen are
    #   three `<details>` wrappers — macOS, Windows natively, Windows via WSL2
    #   — so a first-time reader opens their own machine instead of reading
    #   four platforms in sequence; the Linux line and the four shared steps
    #   stay visible. Thirteen are one Mermaid flowchart under § The three
    #   legs, drawing what the table states: the assembly root mounting both
    #   legs as submodules, each pinned TWICE (the gitlink and
    #   `contracts/<role>-pin.yaml`), and the shape pin to
    #   `opensoft/openRepoShape`. Wrappers cost lines and no prose; a cap that
    #   refused them would be a cap on legibility rather than on words.
    # 2026-09-09: 1014 -> 1028 — `--family` on the scaffold (#76, RULING
    #   ruling 2). Eight lines are a "Joining a family" paragraph in the Quick
    #   start: the landing rule (`<Family>/<Project>`, the folder created if
    #   absent), the no-double-nesting rule (already standing in `<Family>/`
    #   lands at `<Project>`, because a family is never nested inside a
    #   family), and that the flag records NOTHING in the project — membership
    #   is the holder's `family.yaml` and the run's last next-command is the
    #   `family.py add` that writes it. Four are the same fact under "What
    #   setup.sh does": one command line in the block (`mkdir -p
    #   <into>/<Family>`) and the sentence that it is the ONLY step the flag
    #   changes. A reader who learns half of the landing rule files the first
    #   member of a family one level too deep, and a reader who learns none of
    #   the last sentence goes looking in `project.yaml` for a family field
    #   that is deliberately not there.
    # 2026-09-09: 1028 -> 1073 — the family WORKSTATION layout, the other half
    #   of the same day's ruling (#76). The Families section described a holder
    #   and said nothing about the folder around it, so the first question
    #   anyone asked — "is `InkRouter/InkRouter` the family, and what is the
    #   parent folder?" — had no answer in this file, and the layout existed
    #   anyway, arranged by hand. Its own `###` subsection, not a paragraph, because
    #   three of its four halves are things a reader gets wrong separately:
    #   where `init` LANDS (`<into>/<Family>/<Family>`, and why the doubled
    #   name is kept), that there are TWO COPIES of every member on purpose
    #   and which one you work in, and that nothing ever MOVES a checkout —
    #   the warning-plus-`mv` instead, for the reason the deliberately-not-
    #   proposed mover would have broken (linked worktrees carry absolute
    #   paths). Six more lines extend the InkRouter tree to show the folder
    #   and name `family.py siblings` in the command block.
    # 2026-09-09: 1073 -> 1141 — `make park` / `make resume` (#77, RULING
    #   2026-09-09). A whole `##` section plus its row in the contents list,
    #   because carrying half-finished work to another workstation was a thing
    #   people were doing BY HAND — folder copies, and a stash somebody hoped
    #   was still there — and this file said nothing about it at all. Sixteen
    #   lines are the two verbs and the four-command sequence they sit in.
    #   The rest is the four facts a reader who learns only the commands then
    #   gets wrong: that this repository implements NEITHER (the mechanics are
    #   the Speckit git extension's, one implementation, and the targets refuse
    #   by name — the refusal is quoted, because a person who has not installed
    #   it meets that line first); that the record is the PERSON'S, one file
    #   per family or project in a repository they own and named once in
    #   `~/.agents/workspace.yaml`, not in `project.yaml` and not in the
    #   assembly root; that nothing is synced and nothing under `worktrees/` is
    #   ever committed, because a linked worktree's path is absolute and
    #   machine-local, so the record carries commits and no path; and that
    #   `resume` REFUSES on divergence, in an `> [!IMPORTANT]` callout, since a
    #   reader who thinks that refusal is a bug will go looking for the flag
    #   that overrides it. Eleven more give the family holder's half (ruling
    #   5) and WHERE it runs — the members' WORKING CLONES beside the holder,
    #   never the pinned `members/<Project>`, because that copy is detached
    #   and a holder that parked it would report "nothing to park" for every
    #   member while the work sat next door; and that a member with no
    #   working clone is SKIPPED naming `make siblings`, since a skip that
    #   read as success is how somebody concludes their work came back when
    #   none of it did. Five are a `> [!WARNING]` that native Windows parks
    #   nothing: the extension's mirror has neither script, WSL2 is the way.
    # 2026-09-09: 1141 -> 1197 — `park <Name>` and `resume <Name>` as INSTALLED
    #   COMMANDS (#82, RULING 2026-09-09). The section above it told a reader
    #   to `cd` to a root and type `make park`, which is the mechanism and not
    #   the way in — the same gap the `openRepoShape` command closed over
    #   `setup.sh` (#38), and this is its own `###` subsection for the same
    #   reason that one is. Forty-nine lines: two command blocks (the two
    #   words on the two machines, and the `--workspace` line that is typed
    #   once per machine), then the three facts a reader who learns only the
    #   two words then gets wrong. HOW THE ESTATE IS FOUND, because `<Name>`
    #   is a folder and not a repository, both spellings of the projects
    #   directory are real, a family folder beating a standalone root is why
    #   `park InkRouter` parks the estate rather than one service, and `park`
    #   REFUSING with no estate around the cwd reads as a bug until the reason
    #   is written down. WHAT `--repo` DOES, because it matches a clone you
    #   already have and never fetches one — a reader who expects it to clone
    #   will file the refusal as a defect. And WHAT THEY LEAVE BEHIND, because
    #   "as if I am still on A" has edges: an unpushed `main` commit, a dirty
    #   root mid pin-bump, ignored files that never travel, a clone refused by
    #   name and skipped rather than reset, and no agent session at all. Seven
    #   more lines are the two install paragraphs saying THREE commands rather
    #   than one, and two extend the Windows warning to the commands
    #   themselves, which are bash like everything else on that path. Three
    #   are structural and are the price of the new `###`: a second one,
    #   `### Who implements it, and what the record is`, so that the doctrine,
    #   the record, the divergence callout, the holder's half and the Windows
    #   warning stay in the SECTION rather than falling under the commands'
    #   heading in the outline — plus its row in the contents list, which is
    #   the navigation #73's pass added and a section with one of two
    #   subsections listed would be worse than either.
    # 2026-09-09: 1200 -> 1203 — the adversarial review on PR #83. Three
    #   lines, and all three are a sentence that was WRONG being made right:
    #   "a green run is the only green run" is true of `resume`, which exits
    #   non-zero on a refusal, and false of `park`, which passes `make park`'s
    #   own status through and can exit 0 with a report of what it left
    #   behind. A reader who trusts the exit code of `park` skips the report
    #   that is the whole point of the paragraph, so the paragraph now says
    #   which of the two to read — plus the half-sentence that a refused clone
    #   is not given the verb either, which is what the fix to that finding
    #   made true.
    # 2026-09-10: 1203 -> 1219 — the sixth naming form, `<user>-wip` (#81).
    #   Three lines widen the naming-families sentence in "The three legs":
    #   the count, the form itself, and a link to the section that says where
    #   such a repository lives — a family listed by name and explained
    #   nowhere is the "checked by whoever remembers it" failure the contract
    #   file opens by refusing. Twelve are the paragraph in "Who implements
    #   it, and what the record is", and each fact in it is one a reader
    #   cannot get from "a repository they own". WHAT IT IS CALLED, because
    #   two engineers need two of them and the name is now a classified form
    #   rather than a habit. That ONE of them, in the home organisation,
    #   indexes work in EVERY organisation, which is the ruling and not the
    #   obvious reading — the obvious reading is one per org. That an
    #   organisation whose work must not be indexed outside it gets its own
    #   under an `orgs:` map that is opt-in, and therefore invisible unless it
    #   is written down. The `--workspace <owner>/<user>-wip` spelling,
    #   because the subsection above says `<owner>/<your-wip-repo>` and a
    #   reader left to guess the `-wip` half will guess wrong on the one
    #   command that writes a file outside a repository. And that nothing here
    #   CREATES one, which is what stops somebody waiting for a tool that is
    #   never coming.
    # 2026-09-10: 1219 -> 1225 — park-everything (#91, RULING 2026-09-10).
    #   Six lines rewrite the "How the estate is found" sentence that used to
    #   say bare `park` REFUSES with no estate around the cwd: it now PARKS
    #   EVERY ESTATE it finds instead, in name order, continuing past a
    #   refusal — ruling 3 of #82 superseded for that one case — and the same
    #   sentence now says `resume` deliberately keeps the old refusal, so a
    #   reader of one paragraph gets both halves rather than one turning
    #   stale next to the other.
    # 2026-09-10: 1225 -> 1230 — `park` and `resume` carve out into
    #   opensoft/openRepoTools (#92). The two install paragraphs go from THREE
    #   commands to one, which is a saving; the five lines are what a reader
    #   cannot work out from the shorter text. WHERE THE VERBS WENT, in both
    #   places somebody reads an install line, because a person who ran the
    #   old one-liner has `park` on PATH and no way to learn from this file
    #   why it stopped being replaced. And openRepoTools' OWN one-liner, in a
    #   `sh` block, because it is the thing they now have to type and a
    #   sentence naming a repository is not a command — the same argument the
    #   `openRepoShape` install block itself won over "fetch the file and run
    #   it" (#38). It is byte-identical to the line `openRepoShape --install`
    #   prints, which `test_the_openrepotools_install_line_is_the_same_
    #   everywhere` is what keeps true. What did NOT cost a line: the whole of
    #   "Carrying in-flight work to another workstation", which documents two
    #   commands that still exist and still work exactly as it says — they are
    #   installed from somewhere else, which is one clause of one sentence.
    # 2026-09-10: 1230 -> 1298 — the repository doctor (#95). Brett Heap:
    #   "what tools do we have to check a repo to make sure it is compliant
    #   with openRepoShape?" -> "add that". Sixty-six lines are its `###`
    #   subsection under "Keeping a project's shape current", one is its row
    #   in the contents list, and one names `shape-doctor.py` in the Layout
    #   block. It is a subsection rather than a paragraph because five of its
    #   parts are things a reader gets wrong separately, and each of them
    #   would otherwise be learnt from a surprise. WHAT IT COMPARES AGAINST
    #   — the checkout the script is run from, which is the whole of why the
    #   run is offline and is not guessable from the command line. THE ROWS,
    #   because "it checks the repo" does not say that the project's OWN
    #   validators run in preference to this standard's, which is the point
    #   of a pinned copy. THE VERDICT TABLE WITH ITS EXIT CODES, because the
    #   codes are what a scheduled job reads. WHY DRIFT OUTRANKS A RED
    #   VALIDATOR on that one line, since a reader who does not know that an
    #   edited copy is what makes `validate-pins.py` red will read `DRIFTED`
    #   as the tool having missed the validator. And that `machine` is `n/a`
    #   and cannot move the verdict — the one row that reaches a network, on
    #   a page that has just promised none — because a reader who takes it
    #   for a compliance row will read a missing `gh` as their repository
    #   being wrong. The registry paragraph is three lines and is the only
    #   forward-looking one: it says a repair mode hangs off an empty slot,
    #   so nobody proposes the rewrite it exists to avoid.
    # 2026-09-10: 1298 -> 1313 — the two shim behaviours (#95). Brett Heap:
    #   "add the two shim behaviours too". Eight lines are the read-only
    #   `machine:` block `--install` now ends with, and they are eight rather
    #   than one because the useful half is what it does NOT do: it installs
    #   nothing, asks nothing and changes no exit code, so a reader who meets
    #   it as "the installer checked my machine" would wait for a prompt that
    #   is not coming. `--preflight` is named as where the offers live, which
    #   is the same "a refusal names its fix" rule the rest of this file is
    #   built on. Seven are the bare run: it prints usage and exits 1 now
    #   instead of refusing about an organisation nobody named, and the
    #   sentence says both what the four lines are and that ANY scaffold
    #   argument brings today's behaviour and today's refusals back — a
    #   reader who learns only the first half will file the refusal they
    #   earned as the new usage page misfiring.
    # 2026-09-10: 1313 -> 1324 — the adversarial review on PR #96. Eleven
    #   lines, and every one of them is a rule the first cut got wrong in
    #   front of a reader. Seven are the `note` status and WHY it exists:
    #   only a `FINDING` moves the verdict, `FINDING` means something ELSE
    #   asserts it, and the line was drawn after this command answered
    #   `INVALID` about a live estate whose every real gate was green
    #   because a leg was missing a `.gitignore` that entered the standard
    #   after that project was scaffolded. A reader who does not know that
    #   distinction cannot tell a report from a verdict. Three widen exit 3
    #   to what it actually covers, `CANNOT ANSWER` included — a pin naming
    #   a commit THIS checkout does not carry is not the repository being
    #   wrong. One corrects a sentence that was simply false: the machine
    #   row asks `gh` three questions, not one.
    # 2026-09-11: 1324 -> 1328 — `docs/cli.md` (#97). Three lines in the
    #   Layout block and one in the sentence that already sent a reader to
    #   `openRepoShape --help` and `setup.sh --help` for the flags — it now
    #   names the file that has all seventeen tools' help instead of the two.
    #   The block claims to list what this repository ships and named nothing
    #   under `docs/` at all, so `docs/handbook.html` — shipped since #71 —
    #   goes in beside the new file rather than remaining the one shipped
    #   thing the layout does not mention. The generator gets its own row
    #   next to what it generates, because a reader who finds `docs/cli.md`
    #   and edits it has undone the whole point of it, and a layout row is
    #   where they find that out before they type.
    # 2026-09-11: 1328 -> 1374 — the `placement` row and the plan it writes
    #   (#99), landing after #97 the same day. Brett Heap: "we have to look
    #   for code in spec and spec in code". Forty-six lines, and they are
    #   that many because five separate things about this row are surprises a
    #   reader would otherwise meet one at a time. WHAT IT RUNS — the
    #   ADOPTION's policy, over a project that has already been split, with
    #   that tool's own `walk()` — because a reader who thinks this is a
    #   second classifier will expect it to disagree with `adopt-project.py
    #   plan` and will not trust either. WHAT IT REFUSES TO JUDGE, and why
    #   there is a list at all: the four files the leg templates ship
    #   classify as `root`, correctly, and a row that read that literally
    #   would fail every leg this standard has ever cut. `review_required`
    #   IS A NOTE, which is the same line #96 drew for the leg files and has
    #   to be redrawn here because this row can reach the same wrong answer
    #   by a different route. THE VERDICT ROW AND ITS PLACE IN THE ORDER,
    #   since the codes are what a scheduled job reads and `MISPLACED`
    #   sitting above `INVALID` is a choice worth one sentence. And THE PLAN,
    #   which is most of the second half: it is the only thing this command
    #   writes, its entries are an adoption plan's entries so that resolving
    #   one teaches the other, and it carries a different `kind:` ON PURPOSE
    #   — a reader who does not learn that from the page could hand it to
    #   `adopt-project.py execute`, which creates repositories and rewrites
    #   history, with `--yes` the only thing in the way. One more line, at
    #   1374 -> 1375, for the review on PR #100: the FAMILY row list named
    #   five rows and the command returns six, `placement` among them at
    #   `n/a`. A page that lists the rows and is short one is a page a reader
    #   checks their report against and finds a row nobody documented.
    assert len(lines) <= 1375, (
        f"README.md is {len(lines)} lines; the cap is 1375")


@pytest.mark.parametrize("name", SHIPPED_BASH)
def test_shipped_bash_is_executable_and_fails_loudly(name):
    script = REPO / name
    assert script.is_file()
    assert os.access(script, os.X_OK), f"{name} must be executable: chmod +x"
    text = script.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in text, (
        "the first script a person runs must stop on the first failure, not "
        "carry on with an unset variable")


@WINDOWS_SKIP
@pytest.mark.parametrize("name", SHIPPED_BASH)
def test_shipped_bash_parses_under_bash(name):
    """`bash -n` on the two shipped bash scripts, everywhere there is a bash.

    SKIPPED ON WINDOWS, AND `shutil.which` IS NOT ENOUGH TO SEE WHY. The
    `bash` a stock Windows install puts on PATH is
    `C:\\Windows\\System32\\bash.exe`, the WSL launcher — `which` finds it, it
    exits 1 with "no installed distributions" in UTF-16, and the failure reads
    as a syntax error in `setup.sh`. The bash that IS a bash there, Git Bash,
    is handed `D:\\a\\...\\setup.sh` by this test and converts the path on its
    way in. Neither one answers the question this test asks, and the question
    is answered on every other platform in CI. Windows runs the shape through
    `setup-project.py`, which has its own suite.
    """
    if shutil.which("bash") is None:
        pytest.skip("bash is not installed")
    proc = subprocess.run(["bash", "-n", str(REPO / name)],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize("name", SHIPPED_PYTHON_ENTRY)
def test_shipped_python_entry_is_executable_and_has_a_shebang(name):
    """The Python twin of `test_shipped_bash_is_executable_and_fails_loudly`.

    `python setup-project.py` works with no mode bit at all and is how the
    README's Windows line runs it, but `./setup-project.py` is how a macOS or
    Linux reader runs everything else in this repository, and a front door
    that works one way and not the other is a front door that gets reported
    as broken.
    """
    script = REPO / name
    assert script.is_file()
    assert os.access(script, os.X_OK), f"{name} must be executable: chmod +x"
    text = script.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env python3\n")


@pytest.mark.parametrize("name", SHIPPED_PYTHON_ENTRY)
def test_setup_project_py_is_pure_ascii(name):
    """No character in this file may need more than one byte.

    Windows PowerShell 5.1 is still the default shell on a stock Windows
    install. It renders a console in the machine's ANSI code page, re-encodes
    piped text as ASCII by default (its `$OutputEncoding`), and writes UTF-16
    when `>` redirects to a file, so no byte above 0x7F survives all three
    routes: a tick, an arrow or an em dash in this file arrives as mojibake,
    as a question mark, or raises an encoding error on the way out - in the
    FIRST thing a person runs, before they have any reason to trust it.
    `[ok]` and `[!!]` cost a reader nothing. Every other file here is free to
    use the punctuation the rest of this repository is written in; this one
    is the front door on the platform that cannot render it.
    """
    assert (REPO / name).read_bytes().isascii(), (
        f"{name} must be pure ASCII; find the offending line with "
        f"`grep -nP '[^\\x00-\\x7F]' {name}`")


#: THE ONE LINE THAT INSTALLS THE COMMANDS THIS REPOSITORY NO LONGER SHIPS
#: (#92). `park` and `resume` moved to opensoft/openRepoTools, and what is
#: left here is a pointer at its installer: printed by `openRepoShape
#: --install`, written down in README.md, quoted on the handbook page. It is
#: COPIED AND PASTED by somebody who cannot check it, which is the argument
#: `test_the_windows_commands_name_files_that_exist` already makes about the
#: Windows two-liner - and a copy that drifted would send them at a URL that
#: 404s or at a repository that installs something else. Held here rather than
#: in `tests/test_openreposhape_command.py` because the property is a parity
#: between three files of this REPOSITORY, which is what this file holds.
#:
#: THE STRING IS SPLIT ACROSS TWO SOURCE LINES AND JOINED, so this file can be
#: read at 79 columns; the assertion is on the joined line.
OPENREPOTOOLS_INSTALL = (
    "curl -fsSL https://raw.githubusercontent.com/opensoft/openRepoTools/"
    "main/openRepoTools | bash -s -- --install")

#: Every file that carries it. The shim is where a person meets it, README.md
#: is where they look it up, and `docs/handbook.html` is the README's designed
#: reading - a page a reader copies from as readily as either.
OPENREPOTOOLS_INSTALL_IN = ["openRepoShape", "README.md", "docs/handbook.html"]


@pytest.mark.parametrize("name", OPENREPOTOOLS_INSTALL_IN)
def test_the_openrepotools_install_line_is_the_same_everywhere(name):
    """One line, byte for byte, wherever it appears.

    Two copies that disagree is one wrong copy in front of whoever was not
    looking, and neither half of the pair would be caught by anything else:
    the shim's copy is a `say` string and the other two sit inside a fenced
    or a `<pre>` block, so nothing runs any of them.
    """
    text = (REPO / name).read_text(encoding="utf-8")
    assert OPENREPOTOOLS_INSTALL in text, (
        f"{name} must carry openRepoTools' install line byte for byte:\n"
        f"    {OPENREPOTOOLS_INSTALL}")


def test_nothing_here_installs_park_or_resume():
    """The carve, asserted rather than remembered (#92).

    `park` and `resume` are opensoft/openRepoTools' commands. This repository
    keeps the two MAKE TARGETS of the same name — `templates/*/Makefile`, and
    `tests/test_park_resume_targets.py` is their suite — so the words stay in
    the tree and a grep is not the check. What must not come back is a file at
    this root called either, or a name in the shim's `INSTALLABLES`: the first
    is the carve undone by a copy, the second is `--install` reaching for a
    file that is not here.
    """
    for name in ("park", "resume"):
        assert not (REPO / name).exists(), (
            f"{name} is back at the repository root; it is "
            "opensoft/openRepoTools' file since #92")
    shim = (REPO / "openRepoShape").read_text(encoding="utf-8")
    [installables] = re.findall(r"^INSTALLABLES=\((.*)\)$", shim, re.M)
    assert installables.split() == ["openRepoShape"], (
        f"the shim installs {installables.split()}; `--install` places this "
        "command and prints openRepoTools' one-liner for the other two")


#: Every file carrying the Windows two-liner. The README is where a person
#: reads it and AGENTS.md is where an assistant does, and a rename that fixed
#: one and not the other would leave the broken copy in front of whoever was
#: not looking.
WINDOWS_TWO_LINER = ["README.md", "AGENTS.md"]

#: The raw URL the download must use, PINNED AT `main` and not merely at this
#: repository. A ref that does not exist 404s, and a ref that is somebody's
#: branch hands a first-time reader a file nobody reviewed - neither of which
#: a prefix check on the org alone would notice.
RAW_MAIN = "https://raw.githubusercontent.com/opensoft/openRepoShape/main/"


@pytest.mark.parametrize("name", WINDOWS_TWO_LINER)
def test_the_windows_commands_name_files_that_exist(name):
    """The two-liner is COPIED AND PASTED by someone who cannot check it.

    A renamed file leaves the download 404ing and the run failing on a machine
    with nothing else to fall back to, and neither half of the pair would be
    caught by anything else in this suite: the URL is a string, and the file
    it names is a file.
    """
    text = (REPO / name).read_text(encoding="utf-8")

    [url] = re.findall(r"Invoke-WebRequest\s+(\S+)", text)
    assert url.startswith(RAW_MAIN), (
        f"{name} downloads {url}; it must be {RAW_MAIN}<file>")
    downloaded = url[len(RAW_MAIN):]
    assert "/" not in downloaded, (
        f"{name} downloads {url}, which is not a file at the repository root")
    assert (REPO / downloaded).is_file(), (
        f"{name} downloads {url}, which names no file in this repository")

    # `[^\s`]+` rather than `\S+`: AGENTS.md writes the pair inside backticks,
    # so the filename is followed by one.
    [out_file] = re.findall(r"-OutFile\s+([^\s`]+)", text)
    assert (REPO / out_file).is_file(), out_file
    assert out_file == downloaded, (
        "the file downloaded and the file saved must be the same name")

    # ALL of them, not the only one. The README names a second `py` line
    # since #59 (`py setup-project.py --preflight`, the Windows spelling of
    # preflight-and-stop run), and an unpack of a single match would have
    # raised a ValueError on a README that is not wrong. The honest rule is
    # the one asserted here anyway: EVERY `py <file>` in these documents
    # names the file the two-liner downloads, because there is only one file
    # on that machine.
    runs = re.findall(r"(?:^|`)py\s+([^\s`]+)", text, re.M)
    assert runs and all(run == out_file for run in runs), (
        f"{name} saves {out_file} and then runs {runs}")


def entry_point_module():
    """`setup-project.py` imported as a module, for the tables in it.

    The filename has a hyphen and cannot be imported by name.
    `tests/test_setup_project_py.py` has the same helper for the same reason;
    this copy is here because the parity between an offer table and the
    README is a property of the REPOSITORY, which is what this file holds.
    """
    spec = importlib.util.spec_from_file_location("setup_project_offers",
                                                  REPO / "setup-project.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_offer_commands_are_the_ones_the_readme_documents():
    """A command this tool would RUN that no document shows is the defect.

    The preflight offers to install a missing prerequisite and runs the
    command on a typed `yes` (#59). Those commands are the README's own
    per-platform steps, and this holds the two together in the direction that
    matters: table -> README. The README may say more than the table does - a
    reader on a platform this tool makes no offer for still needs the words -
    but nothing may be RUN that a reader cannot find written down, both
    because it is what the person who declines the offer types by hand and
    because a command nobody documented is a command nobody reviewed.

    WHITESPACE IS COLLAPSED ON BOTH SIDES, so GitHub's tab-indented apt block
    matches however the README wraps it, and a re-wrap of a one-liner does not
    fail a test about what runs.
    """
    module = entry_point_module()
    readme = " ".join((REPO / "README.md").read_text(encoding="utf-8").split())
    for (tool, platform), rows in module.INSTALL_OFFERS.items():
        for program, command in rows:
            assert command.strip(), f"{tool}/{platform} has an empty command"
            assert command.isascii(), (
                f"{tool}/{platform} is not ASCII: {command!r}")
            assert "brew.sh" not in command, (
                "Homebrew's own installer is never run by this tool; the "
                "darwin/no-brew row is None by construction")
            assert " ".join(command.split()) in readme, (
                f"the {tool} offer for {platform} runs a command README.md "
                f"does not document:\n    {' '.join(command.split())}")


def test_setup_sh_is_the_documented_front_door():
    assert "./setup.sh --project" in (REPO / "README.md").read_text()
    assert "What setup.sh does" in (REPO / "README.md").read_text()
    agents = (REPO / "AGENTS.md").read_text()
    assert "without `--yes`" in agents
    assert "--allow-upstream-org" in agents


#: A host-absolute path baked into a committed file (the estate's Rule 1):
#: it names one machine, one user, or one session, and silently breaks the
#: moment the repository moves to a different machine or a different user's
#: checkout - which is exactly what #61 found in `tests/test_adopt_plan.py`,
#: a scratchpad path from one session that no other machine could ever match.
#:
#: Each alternative requires a REAL-LOOKING segment rather than matching on
#: the word alone, checked against what this repository's tracked text
#: actually carries today:
#:   - `/opt/homebrew` (README.md) is the only "/home"-adjacent string, and
#:     it matches none of these.
#:   - Windows examples in scripts/repo_shape.py, tests/test_setup_project_py
#:     .py and tests/test_windows_paths.py illustrate a SPACE in a username
#:     ("Jane Doe", "Some One") to make a quoting point; requiring the
#:     segment to contain no whitespace excludes them.
#:   - .github/workflows/tests.yml names the GitHub-hosted Windows runner's
#:     own fixed account - a shared, nobody's-machine-in-particular login
#:     the same way `/opt/homebrew` is a shared install location - and it is
#:     excluded by name rather than matched.
#:   - This definition would otherwise flag ITSELF: the Claude-scratchpad
#:     tmp-directory prefix this guard exists to catch is therefore spelled
#:     as two concatenated pieces, not written out contiguously.
_CLAUDE_TMP_PREFIX = "/tmp/" + "claude-"
HOST_ABSOLUTE_PATH = re.compile(
    r"/home/[a-z][a-z0-9_-]*/"
    "|" + re.escape(_CLAUDE_TMP_PREFIX) +
    r"|/Users/[A-Za-z][A-Za-z0-9_-]*/"
    r"|C:\\Users\\(?!runneradmin\\)[^\s\\]+\\"
)


def test_no_committed_file_names_a_host_absolute_path():
    """#61: the suite stayed green on every machine but the one the fixed
    path was written on, because the ONE test that read it SKIPPED when it
    was absent. Nothing checked the path itself for being the kind of thing
    that should never have been committed. This is that check.

    Every file `git ls-files` tracks, decoded as UTF-8 - a file that fails to
    decode is skipped rather than failed, because this test is about paths
    written in text, not about what counts as text.
    """
    tracked = subprocess.run(["git", "ls-files"], cwd=str(REPO),
                             capture_output=True, text=True,
                             check=True).stdout.splitlines()
    offenders = {}
    for rel in tracked:
        try:
            text = (REPO / rel).read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue
        hits = HOST_ABSOLUTE_PATH.findall(text)
        if hits:
            offenders[rel] = hits
    assert not offenders, (
        f"committed file(s) name a host-absolute path: {offenders}")


#: Spelled counts, not numerals: no sentence in this repository writes "6
#: naming families", so a numeral would be exactly as wrong as the wrong
#: word. Carried a little past the current six so the mapping does not need
#: to grow again the next time a form is added.
NAMING_FAMILIES_NUMBER_WORDS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
}

#: The two words every prose count of the policy's top-level forms shares,
#: whichever number spells it: "five naming families", "the four naming
#: families", "six naming families, as data".
NAMING_FAMILIES_COUNT_RE = re.compile(r"(\w+) naming families")


def test_every_naming_families_count_matches_the_policy():
    """#87: three files disagreed with `contracts/repository-naming.yaml`,
    and with each other. `docs/handbook.html` said "five naming families" in
    "The three legs" and "four naming families" in the Layout table, plus an
    aside quoting the README's own now-stale "four naming families" - the
    README itself had already moved to six. `templates/assembly-root/
    README.md`, a TEMPLATED file whose bytes are copied into every newly
    scaffolded project, had said "the four naming families" since #1.
    Nothing tied any of the three sentences to the DATA, so the sixth form
    landing in #86 (`workspace`, `<user>-wip`) moved the count and none of
    the prose that quotes it.

    The expected word comes from the policy itself, never written here as a
    literal: `NamingPolicy.load(...).families` is the same top-level list
    `scripts/validate-repository-naming.py --explain` reports the length of,
    and that `tests/test_naming_policy.py` parametrizes over as
    `FAMILY_IDS`. `project-leg`'s three `roles:` (assembly/spec/code) nest
    one level deeper, under THAT family's own `roles:` key, and are not
    counted again - `NamingPolicy.__init__` reads only the top-level
    `families:` list. A SEVENTH form added to the data moves what this test
    requires without anybody having to remember to update it too, which is
    the point: the drift #87 found cannot recur silently.

    The search is tree-wide, in the style of the host-absolute-path test
    just above: every file `git ls-files` tracks whose name ends `.md` or
    `.html`, decoded as UTF-8 (a decode failure is skipped, not failed -
    this test is about prose, not encoding). Grepping the tree once by hand
    while writing this test found the phrase in exactly three of the
    repository's eighteen tracked `.md`/`.html` files: `README.md`,
    `docs/handbook.html` and `templates/assembly-root/README.md`, all three
    fixed above. `templates/family-root/README.md` - named in #87 as a file
    carrying the same risk - has no "naming families" sentence at all
    today, so it contributes no match; the dynamic scan still walks it, so
    a copy of the sentence landing there later is caught the same way, with
    no change to this test required.
    """
    policy = NamingPolicy.load(REPO / "contracts" / "repository-naming.yaml")
    expected = NAMING_FAMILIES_NUMBER_WORDS[len(policy.families)]
    tracked = subprocess.run(["git", "ls-files"], cwd=str(REPO),
                             capture_output=True, text=True,
                             check=True).stdout.splitlines()
    offenders = {}
    for rel in tracked:
        if not rel.lower().endswith((".md", ".html")):
            continue
        try:
            text = (REPO / rel).read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue
        wrong = [w for w in NAMING_FAMILIES_COUNT_RE.findall(text)
                 if w.lower() != expected]
        if wrong:
            offenders[rel] = wrong
    assert not offenders, (
        f"'<word> naming families' should say {expected!r} "
        f"(contracts/repository-naming.yaml declares {len(policy.families)} "
        f"top-level families) but found: {offenders}")


#: `docs/handbook.html` is the DESIGNED READING of `README.md` (#69, PR #71):
#: one self-contained page a person opens from a checkout. It REORDERS the
#: README for a newcomer and folds some of it together, so its sections are
#: not the README's sections in the README's order. What it must not do is
#: fall BEHIND the README — and between PR #71 (cut at `c093813`) and #89 it
#: did, in six places at once: the README gained `--family`, the family
#: WORKSTATION layout, the whole of "Carrying in-flight work to another
#: workstation" and its two subsections, three installed commands where there
#: had been one, a sixth naming form, and the rehearsal flag's Windows
#: spelling (#70). The page said none of it, nothing was red, and the drift
#: was found by reading rather than by running the suite. #87/#88 had just fixed the same shape of drift in the same file for
#: a single word ("five naming families"), and that fix is what made the
#: larger one visible.
#:
#: THIS TABLE IS THE TIE, and it is deliberately explicit: every `## ` heading
#: of README.md, and the id of the element of the page that carries it. A
#: heading the page folds into a neighbouring section maps to THAT NEIGHBOUR,
#: so an omission is a named decision rather than silence. Adding a `## ` to
#: the README and nothing to the page now fails here, naming the heading.
README_HEADING_TO_HANDBOOK_ID = {
    "Starting a project in a new organisation": "start",
    "The three legs": "legs",
    "Adopting an existing repository": "adopt",
    "Families: a holder for projects that ship separately": "families",
    "The double pin, and the lockstep invariant": "doublepin",
    "Bootstrap is COPIED into the project, not fetched": "copied",
    "Keeping a project's shape current": "current",
    "Carrying in-flight work to another workstation": "park",
    "The degrade rule": "degrade",
    "Layout of this repository": "layout",
    #: The page's `<footer>`, which carries the licence line rather than a
    #: section of its own. The one mapped id that is not a `<section>`, which
    #: is why the checks below ask for an ELEMENT with that id.
    "Licence": "licence",
}

#: The other direction, and the reason it is written down too: the page has
#: four sections that are NOT a README `## ` heading, because the reading
#: promotes what a newcomer needs first (the rule that the shape confers
#: nothing), keeps a `> [!WARNING]` that a reader mid-failure will look for
#: by itself, gives the CI credential its own section because it was the
#: first real adoption's defect, and reads AGENTS.md rather than README.md
#: for the assistant rules. A section appearing with no entry in either table
#: fails, so a page section can never become unexplained.
HANDBOOK_SECTION_WITHOUT_A_README_H2 = {
    "confers": "the README's `> [!IMPORTANT]` callout, promoted to the top",
    "partway": "the `> [!WARNING]` inside `### A worked example: Northwind "
               "starts Atlas`",
    "ci": "`### Reading private legs in CI: a GitHub App first, "
          "SHAPE_LEGS_TOKEN as fallback`",
    "agents": "AGENTS.md — the rules that outrank the rest, not README.md",
    #: `### Is this repository compliant? openRepoShape --doctor`, which sits
    #: under § Keeping a project's shape current in the README (#95). Its own
    #: page section rather than a block inside `current`, because a reader
    #: looking for "how do I check a repository" scans the section list, and
    #: a doctor folded into a section about re-syncing copies is a doctor
    #: they do not find.
    "doctor": "`### Is this repository compliant? openRepoShape --doctor`, "
              "inside § Keeping a project's shape current",
}

#: The footer carries the page's history as PROSE — "first cut from README.md
#: at c093813 (#71); regenerated at cbca5b4 (#89)" — and, separately, its ONE
#: MACHINE-CHECKED fact: `README.md blob <hash>` (#91). A commit sha named
#: where the page came FROM and had to exist as a commit object to diff
#: against; a blob hash names WHAT THE PAGE SAYS and needs no history at all
#: — `git hash-object README.md` on the bare working tree file, in a shallow
#: clone or a deep one, is the whole check. Matched on the literal word
#: "blob" rather than a bare hex run, so it can never pick up either commit
#: sha sitting in the prose sentence beside it, and `{40}` rather than
#: `{7,40}` because `git hash-object` always prints the full hash.
HANDBOOK_README_BLOB = re.compile(r"README\.md blob ([0-9a-f]{40})\b")


def _readme_h2s(path):
    """Every `## ` heading of a Markdown file, fenced code blocks skipped.

    `## ` opens a shell comment as readily as a heading, and this README's
    own fenced blocks already carry two lines a naive grep reads as headings
    (`# on the other workstation:`, and the `#   ... a human or an AI
    answers` line in the adopt sequence). Neither is `## ` today, which is
    precisely the kind of thing that stops being true quietly, so the fences
    are tracked rather than assumed harmless.
    """
    headings, fence = [], None
    for line in path.read_bytes().decode("utf-8").splitlines():
        stripped = line.strip()
        if fence is not None:
            if stripped.startswith(fence):
                fence = None
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence = stripped[:3]
            continue
        if line.startswith("## "):
            headings.append(line[3:].strip())
    return headings


def test_the_handbook_follows_the_readmes_outline():
    """#89: the page is a reading of the README, and this is what keeps it one.

    Four checks, and the fourth is the one with teeth:

    1. Every `## ` heading in README.md has an entry in
       `README_HEADING_TO_HANDBOOK_ID`. A new section in the README with no
       entry fails NAMING THE HEADING, so the choice — write the section,
       or fold it into a neighbour and say which — has to be made rather
       than forgotten.
    2. No entry names a heading README.md no longer has. A reworded heading
       also moves its GitHub anchor, so the page's `Full text` link into that
       heading is stale at the same moment; failing here is what sends
       somebody to look at both.
    3. Every mapped id is a real element id on the page - `<section id=...>`
       for ten of them and the `<footer id="licence">` for the eleventh.
    4. And the page names README.md's own BLOB HASH, which must equal
       `git hash-object README.md` on the working tree file (#91). No
       commit needed, no diff, no history: two files with identical bytes
       hash identically regardless of which commit either sits on, or
       whether either is on a commit at all.

    THE FIX WHEN (4) GOES RED IS TO REGENERATE THE PAGE, and #89 is the
    precedent for what that means: read what changed in README.md since the
    page was last regenerated — the footer's prose names that regeneration's
    commit — add or amend the page's sections in the page's own design and
    voice, keep every code block byte-identical to the README's (modulo the
    README's line-wrapping), then set the footer's `README.md blob <hash>`
    to the new `git hash-object README.md`. A README change that touches
    nothing the page says is the one case where moving the hash alone is
    honest — and saying so in the commit message is part of it. Editing the
    hash to quiet this test without reading what changed is the
    documentation equivalent of hand-editing a pin to make the validator
    agree, which is the thing this repository spends a whole section
    refusing.

    CHECK (4) USED TO BE `git diff <sha> -- README.md` against the commit
    the page named, SKIPPED when that commit was not in this clone — the
    case a SHALLOW clone always hits, `git clone --depth 1` having exactly
    one. CI itself was such a clone, so the one check that should have
    caught the page falling behind skipped itself there and could only fail
    on the machine where the page gets regenerated: green in CI, red only
    where it was too late to matter. #89's fix was `fetch-depth: 0` on all
    three jobs in `.github/workflows/tests.yml`, naming this test as why.
    #91 fixed the design instead of only working around it in CI: hashing
    the WORKING TREE file needs no commit object and skips nothing, so the
    check is exact in a shallow clone, a fresh `git init`, or no history at
    all. `fetch-depth: 0` stays in the workflow — a generally useful default
    for whatever history-based check this suite grows next — but nothing
    about THIS test's correctness depends on it any more.
    """
    readme_h2s = _readme_h2s(REPO / "README.md")
    page = (REPO / "docs" / "handbook.html").read_bytes().decode("utf-8")

    unmapped = [h for h in readme_h2s
                if h not in README_HEADING_TO_HANDBOOK_ID]
    assert not unmapped, (
        f"README.md has `## ` heading(s) no entry accounts for: {unmapped}. "
        "Add the section to docs/handbook.html and map the heading to its id "
        "in README_HEADING_TO_HANDBOOK_ID, or map it to the page section it "
        "is deliberately folded into - an omission must be a named decision.")

    stale = [h for h in README_HEADING_TO_HANDBOOK_ID if h not in readme_h2s]
    assert not stale, (
        f"README_HEADING_TO_HANDBOOK_ID names heading(s) README.md no longer "
        f"has: {stale}. A reworded heading moves its GitHub anchor too, so "
        "check the page's `Full text` links into it while you are here.")

    ids = set(re.findall(r'\sid="([^"]+)"', page))
    absent = sorted(set(README_HEADING_TO_HANDBOOK_ID.values()) - ids)
    assert not absent, (
        f"docs/handbook.html has no element with id(s) {absent}, which "
        "README_HEADING_TO_HANDBOOK_ID maps README headings to")

    sections = set(re.findall(r'<section id="([^"]+)">', page))
    accounted = (set(README_HEADING_TO_HANDBOOK_ID.values())
                 | set(HANDBOOK_SECTION_WITHOUT_A_README_H2))
    unaccounted = sorted(sections - accounted)
    assert not unaccounted, (
        f"docs/handbook.html section(s) {unaccounted} appear in neither "
        "table. A section that is a README `## ` heading belongs in "
        "README_HEADING_TO_HANDBOOK_ID; one that is not belongs in "
        "HANDBOOK_SECTION_WITHOUT_A_README_H2, with where it came from.")

    blobs = HANDBOOK_README_BLOB.findall(page)
    assert len(blobs) == 1, (
        "docs/handbook.html must name README.md's blob hash exactly once, "
        f"as `README.md blob <hash>`; found {blobs}")
    actual_blob = subprocess.run(
        ["git", "hash-object", "README.md"], cwd=str(REPO),
        capture_output=True, text=True, check=True).stdout.strip()
    assert blobs[0] == actual_blob, (
        f"docs/handbook.html says README.md blob {blobs[0]}, but the "
        f"working tree's README.md hashes to {actual_blob} - it has moved "
        "since the page was cut. Regenerate the page - read what changed, "
        "add or amend its sections in the page's own design, then set the "
        "footer's `README.md blob <hash>` to the new `git hash-object "
        "README.md` (#89 is the precedent for what regenerating means, and "
        "the docstring above says so). Do not move the hash alone unless "
        "the change genuinely touched nothing the page says.")
