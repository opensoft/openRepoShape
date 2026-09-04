# SPDX-License-Identifier: Apache-2.0
"""Properties of THIS repository that a fork depends on and nobody re-checks."""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO, SCAFFOLD

SHIPPED = [
    REPO / "scaffold-project.py",
    REPO / "bootstrap",
    REPO / "adopt-project.py",
    REPO / "update-shape.py",
    REPO / "scripts" / "repo_shape.py",
    REPO / "scripts" / "shape_materialize.py",
    REPO / "scripts" / "path_classify.py",
    REPO / "scripts" / "validate-repository-naming.py",
    REPO / "scripts" / "family.py",
    REPO / "templates" / "assembly-root" / "scripts" / "validate-pins.py",
    REPO / "templates" / "assembly-root" / "scripts" / "validate-manifest.py",
    REPO / "templates" / "assembly-root" / "scripts" / "bootstrap.py",
    REPO / "templates" / "family-root" / "scripts" / "validate-family.py",
    REPO / "templates" / "family-root" / "scripts" / "bootstrap.py",
]
LOCAL_MODULES = {"repo_shape", "shape_materialize", "path_classify",
                 "conftest"}


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
    written down rather than remembered."""
    lines = (REPO / "AGENTS.md").read_text().splitlines()
    assert len(lines) <= 235, f"AGENTS.md is {len(lines)} lines; the cap is 235"


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
    assert len(lines) <= 544, (
        f"README.md is {len(lines)} lines; the cap is 544")


def test_setup_sh_is_executable_and_fails_loudly():
    setup = REPO / "setup.sh"
    assert setup.is_file()
    assert os.access(setup, os.X_OK), "setup.sh must be executable: chmod +x"
    text = setup.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in text, (
        "the first script a person runs in a fork must stop on the first "
        "failure, not carry on with an unset variable")


def test_setup_sh_parses_under_bash():
    if shutil.which("bash") is None:
        pytest.skip("bash is not installed")
    proc = subprocess.run(["bash", "-n", str(REPO / "setup.sh")],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr


def test_setup_sh_is_the_documented_front_door():
    assert "./setup.sh --project" in (REPO / "README.md").read_text()
    assert "What setup.sh does" in (REPO / "README.md").read_text()
    agents = (REPO / "AGENTS.md").read_text()
    assert "without `--yes`" in agents
    assert "--allow-upstream-org" in agents
