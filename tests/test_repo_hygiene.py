# SPDX-License-Identifier: Apache-2.0
"""Properties of THIS repository that a fork depends on and nobody re-checks."""

from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO, SCAFFOLD, WINDOWS_SKIP

SHIPPED = [
    REPO / "setup-project.py",
    REPO / "scaffold-project.py",
    REPO / "bootstrap",
    REPO / "adopt-project.py",
    REPO / "update-shape.py",
    REPO / "scripts" / "repo_shape.py",
    REPO / "scripts" / "shape_materialize.py",
    REPO / "scripts" / "path_classify.py",
    REPO / "scripts" / "validate-repository-naming.py",
    REPO / "scripts" / "family.py",
    REPO / "scripts" / "bump-leg.py",
    REPO / "templates" / "assembly-root" / "scripts" / "validate-pins.py",
    REPO / "templates" / "assembly-root" / "scripts" / "validate-manifest.py",
    REPO / "templates" / "assembly-root" / "scripts" / "bootstrap.py",
    REPO / "templates" / "family-root" / "scripts" / "validate-family.py",
    REPO / "templates" / "family-root" / "scripts" / "bootstrap.py",
]
LOCAL_MODULES = {"repo_shape", "shape_materialize", "path_classify",
                 "conftest"}

#: The two bash scripts a person runs BEFORE they have a checkout: the front
#: door itself, and the command that fetches it. Both are shipped executables
#: and are held to the same shebang, mode bit and `set -euo pipefail` rule.
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
    folds them into a pipe has removed the one `yes` this file opens with."""
    lines = (REPO / "AGENTS.md").read_text().splitlines()
    assert len(lines) <= 273, f"AGENTS.md is {len(lines)} lines; the cap is 273"


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
    assert len(lines) <= 872, (
        f"README.md is {len(lines)} lines; the cap is 872")


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

    [run] = re.findall(r"(?:^|`)py\s+([^\s`]+)", text, re.M)
    assert run == out_file, (
        f"{name} saves {out_file} and then runs {run}")


def test_setup_sh_is_the_documented_front_door():
    assert "./setup.sh --project" in (REPO / "README.md").read_text()
    assert "What setup.sh does" in (REPO / "README.md").read_text()
    agents = (REPO / "AGENTS.md").read_text()
    assert "without `--yes`" in agents
    assert "--allow-upstream-org" in agents
