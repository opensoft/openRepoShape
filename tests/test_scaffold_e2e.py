# SPDX-License-Identifier: Apache-2.0
"""End to end: scaffold into local bare remotes, clone recursively, bootstrap.

NO REAL REPOSITORY IS EVER CREATED. `--local-remote-dir` makes three bare
repositories on disk and uses them as origins; `gh` is never invoked.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

from conftest import (FILE_PROTOCOL, ORG, PROJECT, REPO, SCAFFOLD, git,
                      run_script)

DEGRADE_LINE = "authority is not wallet-carried in this org"


# --- the scaffold ----------------------------------------------------------

def test_dry_run_creates_nothing(tmp_path):
    remotes = tmp_path / "remotes"
    result = run_script(SCAFFOLD, "--org", ORG, "--project", "Northwind",
                        "--elected-by", "Test Human", "--dry-run",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 0, result.stderr
    assert "--dry-run: nothing was created." in result.stdout
    assert "xf-project-northwind" in result.stdout
    assert not remotes.exists()


def test_a_bad_project_name_refuses_before_creating_anything(tmp_path):
    """A naming mistake costs a message, not three repositories and a rename."""
    remotes = tmp_path / "remotes"
    result = run_script(SCAFFOLD, "--org", ORG, "--project", "Atlas-tests",
                        "--elected-by", "Test Human",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "naming-unclassified" in result.stderr
    assert not remotes.exists()


def test_a_descendant_form_project_scaffolds_and_records_the_overlap(tmp_path):
    """THE PILOT CASE, end to end.

    `./setup.sh --project MedxScribe --org MedxSoft` used to die at step (5)
    with `naming-role-mismatch: 'MedxScribe' classifies as domain-descendant`.
    Every project in a `<Domainx>` family organisation hit it. Since the
    2026-09-02 ruling the descendant form is a CLAIM that needs a REFERENT: no
    pin on `openScribe` is declared, so the declared role wins and the manifest
    RECORDS that the name also matches the descendant form.
    """
    remotes, work = tmp_path / "remotes", tmp_path / "work"
    result = run_script(SCAFFOLD, "--org", "MedxSoft", "--project", "MedxScribe",
                        "--elected-by", "Brett Heap",
                        "--elected-on", "2026-09-02",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(work))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "naming-role-mismatch" not in result.stderr

    # the one-line NOTE in the plan, naming the pin that would change the answer
    assert ("NOTE MedxScribe also matches the descendant form; it is not a "
            "descendant because no pin on openScribe is declared — declare "
            "`contracts/openscribe-pin.yaml` later if it becomes one"
            ) in result.stdout

    manifest = (work / "MedxScribe" / "project.yaml").read_text()
    assert "neutral_product_pins: []" in manifest
    assert ("  - role: assembly\n"
            "    repository: MedxSoft/MedxScribe\n"
            '    path: "."\n'
            "    naming:\n"
            "      form: project-leg\n"
            "      role: assembly\n"
            "      also_matches: [domain-descendant]\n"
            "      descendant_referent: openScribe\n"
            "      referent_declared: false\n") in manifest
    # a leg whose name does NOT match the claim form records an empty overlap
    assert ("  - role: spec\n"
            "    repository: MedxSoft/MedxScribe-spec\n"
            "    path: spec\n"
            "    naming:\n"
            "      form: project-leg\n"
            "      role: spec\n"
            "      also_matches: []\n") in manifest

    # and the project's own gate agrees with what was written into it
    for validator in ("validate-manifest.py", "validate-repository-naming.py"):
        args = ["--project", "project.yaml"] if "naming" in validator else []
        check = run_script(work / "MedxScribe" / "scripts" / validator, *args,
                           cwd=work / "MedxScribe")
        assert check.returncode == 0, f"{validator}: {check.stderr}{check.stdout}"


def test_a_neutral_product_form_is_still_refused_as_a_leg(tmp_path):
    """The overlap that was relaxed is descendant/assembly ONLY. `open` in
    front says what a name is, and no declared role overrides that."""
    remotes = tmp_path / "remotes"
    result = run_script(SCAFFOLD, "--org", ORG, "--project", "openScribe",
                        "--elected-by", "Test Human",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "naming-role-mismatch" in result.stderr
    assert "neutral-product" in result.stderr
    assert not remotes.exists()


def test_a_spec_name_offered_as_the_assembly_root_is_refused(tmp_path):
    """The other refusal that must survive: a `-spec` name is not a root."""
    remotes = tmp_path / "remotes"
    result = run_script(SCAFFOLD, "--org", ORG, "--project", "MedxScribe-spec",
                        "--elected-by", "Test Human",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "naming-role-mismatch" in result.stderr
    assert "project-leg/spec" in result.stderr
    assert not remotes.exists()


def test_an_install_form_is_still_refused_as_a_leg(tmp_path):
    remotes = tmp_path / "remotes"
    result = run_script(SCAFFOLD, "--org", ORG, "--project", "Hermes-Install",
                        "--elected-by", "Test Human",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "naming-role-mismatch" in result.stderr
    assert "install" in result.stderr
    assert not remotes.exists()


def test_a_bad_project_id_refuses_before_creating_anything(tmp_path):
    remotes = tmp_path / "remotes"
    result = run_script(SCAFFOLD, "--org", ORG, "--project", "North_Wind",
                        "--elected-by", "Test Human",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "scaffold-bad-id" in result.stderr
    assert not remotes.exists()


def test_the_scaffold_refuses_with_no_elector(tmp_path):
    """Electing the shape is a human's act and the manifest records whose.

    `git config user.name` is the only fallback, so the global and system
    config are suppressed to make the no-elector path reachable at all.
    """
    remotes = tmp_path / "remotes"
    # `env` is an OVERRIDE map merged over the process environment by
    # run_script, and the fixtures set GIT_AUTHOR_NAME there; the scaffold
    # takes that per-invocation identity as an elector before the config, so
    # the no-elector path is reachable only with BOTH blanked (empty string
    # falls through to the config, which is /dev/null here).
    env = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
           "GIT_AUTHOR_NAME": "", "GIT_COMMITTER_NAME": ""}
    result = run_script(SCAFFOLD, "--org", ORG, "--project", "Northwind",
                        "--elected-by", "", "--dry-run",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / "work"), env=env)
    assert result.returncode == 2, result.stdout
    assert "scaffold-no-elector" in result.stderr
    assert not remotes.exists()


def test_the_scaffold_creates_three_bare_remotes(scaffolded):
    for name in (PROJECT, f"{PROJECT}-spec", f"{PROJECT}-code"):
        assert (scaffolded["remotes"] / f"{name}.git").is_dir()
    assert "NEXT STEPS" in scaffolded["stdout"]
    assert "make bootstrap" in scaffolded["stdout"]


def test_rescaffolding_over_an_existing_remote_refuses(scaffolded, tmp_path):
    """There is no --force: re-running over a live project is not a scaffold."""
    result = run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                        "--elected-by", "Test Human",
                        "--local-remote-dir", str(scaffolded["remotes"]),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "scaffold-remote-exists" in result.stderr
    assert "There is no --force" in result.stderr


def test_the_topic_is_set_on_the_manifest(project):
    assert "topic: xf-project-atlas" in (project / "project.yaml").read_text()


def test_the_legs_are_submodules_at_the_declared_paths(project):
    status = git("submodule", "status", cwd=project).stdout
    assert " code" in status and " spec" in status
    modules = (project / ".gitmodules").read_text()
    assert 'path = spec' in modules and 'path = code' in modules
    assert "branch =" not in modules, (
        "`.gitmodules` must carry no `branch=`: that would buy the ergonomics "
        "by weakening the pin, and then 'what commit is this project' has two "
        "answers")


# --- the clone and the bootstrap -------------------------------------------

def test_a_recursive_clone_leaves_the_legs_detached(scaffolded, tmp_path):
    """The submodule tax bootstrap exists to pay, demonstrated."""
    target = tmp_path / "fresh"
    proc = subprocess.run(
        ["git", *FILE_PROTOCOL, "clone", "-q", "--recurse-submodules",
         str(scaffolded["remotes"] / f"{PROJECT}.git"), str(target)],
        capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    head = git("rev-parse", "--abbrev-ref", "HEAD", cwd=target / "spec").stdout
    assert head.strip() == "HEAD", "expected a detached HEAD before bootstrap"


def test_bootstrap_succeeds_and_puts_the_legs_on_tracking_branches(project):
    result = run_script(project / "scripts" / "bootstrap.py", cwd=project)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "bootstrap ok" in result.stdout
    for leg in ("spec", "code"):
        branch = git("rev-parse", "--abbrev-ref", "HEAD",
                     cwd=project / leg).stdout.strip()
        assert branch == "main", f"{leg} is on {branch!r}, expected 'main'"


def test_bootstrap_does_not_move_the_pin(project):
    before = git("rev-parse", "HEAD:spec", cwd=project).stdout.strip()
    run_script(project / "scripts" / "bootstrap.py", cwd=project)
    after = git("rev-parse", "HEAD:spec", cwd=project).stdout.strip()
    assert before == after
    tip = git("rev-parse", "HEAD", cwd=project / "spec").stdout.strip()
    assert tip == before, "the tracking branch must be created AT the pin"


def test_bootstrap_prints_the_degrade_line_when_no_register_exists(project):
    result = run_script(project / "scripts" / "bootstrap.py", cwd=project)
    assert DEGRADE_LINE in result.stdout
    assert result.returncode == 0


def test_bootstrap_reports_a_pin_that_disagrees_with_a_branch_tip(project):
    """It prints both and moves neither."""
    run_script(project / "scripts" / "bootstrap.py", cwd=project)
    git("commit", "-q", "--allow-empty", "-m", "local work",
        cwd=project / "spec")
    result = run_script(project / "scripts" / "bootstrap.py", cwd=project)
    assert "!= branch main tip" in result.stdout
    assert "not moving an existing branch" in result.stdout


def test_bootstrap_fails_when_a_validator_fails(project):
    (project / "scripts" / "repo_shape.py").write_text(
        (project / "scripts" / "repo_shape.py").read_text() + "\n# edited\n")
    result = run_script(project / "scripts" / "bootstrap.py", cwd=project)
    assert result.returncode == 1
    assert "bootstrap FAILED" in result.stderr


def test_bootstrap_reads_a_wallet_register_when_one_exists(project):
    register = project / "governance" / "review-authority" / "register.yaml"
    register.parent.mkdir(parents=True, exist_ok=True)
    register.write_text(
        "register_version: 1\n"
        "rows:\n"
        "  - row_id: row-test-0001\n"
        "    holder_ref: agent:merge-readiness-council\n"
        "    target_repo: testorg/Atlas-code\n"
        "    act: review\n"
        "    state: active\n"
        "    expires_at: \"2026-11-23T12:00:00Z\"\n"
        "  - row_id: row-test-0002\n"
        "    holder_ref: agent:somebody-else\n"
        "    target_repo: otherorg/Unrelated\n"
        "    act: review\n"
        "    state: active\n")
    result = run_script(project / "scripts" / "bootstrap.py", cwd=project)
    assert result.returncode == 0, result.stderr
    assert DEGRADE_LINE not in result.stdout
    assert "agent:merge-readiness-council" in result.stdout
    assert "testorg/Atlas-code" in result.stdout
    assert "agent:somebody-else" not in result.stdout
    assert "confers nothing and enforces nothing" in result.stdout


def test_bootstrap_is_schema_neutral(project, tmp_path):
    """A one-repository project runs the same command: the submodule step is a
    no-op and the authority readout is unchanged."""
    plain = tmp_path / "plain"
    plain.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(plain)], check=True)
    (plain / "scripts").mkdir()
    for name in ("bootstrap.py", "repo_shape.py"):
        (plain / "scripts" / name).write_text(
            (project / "scripts" / name).read_text())
    result = run_script(plain / "scripts" / "bootstrap.py", cwd=plain)
    assert result.returncode == 0, result.stderr
    assert "no submodule legs declared" in result.stdout
    assert "has not elected the schema" in result.stdout
    assert DEGRADE_LINE in result.stdout


def test_make_targets_exist(project):
    makefile = (project / "Makefile").read_text()
    for target in ("bootstrap:", "validate:", "pins:"):
        assert target in makefile


def test_the_ci_workflow_checks_out_submodules(project):
    workflow = (project / ".github" / "workflows" / "validate.yml").read_text()
    # `submodules: true` directly on `actions/checkout` is the reverted
    # defect: it hard-fails the whole job the instant a private leg cannot
    # be cloned. The fetch is now a separate, failure-capturing step; only
    # the checkout step itself must not carry the old setting.
    assert "with:\n          submodules: true" not in workflow
    assert "submodules: false" in workflow
    assert "git submodule update --init --recursive" in workflow
    assert "on:\n  pull_request:" in workflow
    for validator in ("validate-repository-naming.py", "validate-manifest.py",
                      "validate-pins.py"):
        assert validator in workflow


def _step_block(workflow: str, marker: str) -> str:
    """The text of one `- ` step block, from its `marker` line to the next
    top-level (six-space-indented) `- ` step or end of file.

    String/structural, not a real YAML parse — deliberately, so this test
    depends on nothing outside the standard library, like everything this
    repository ships. `marker` should be unique enough to find one step
    (a `name:`, `id:` or `uses:` line makes a good one).
    """
    lines = workflow.splitlines()
    start = next(i for i, line in enumerate(lines) if marker in line)
    # walk back to the start of this step (`      - ` at 6-space indent)
    while not lines[start].startswith("      - "):
        start -= 1
    end = start + 1
    while end < len(lines) and not lines[end].startswith("      - "):
        end += 1
    return "\n".join(lines[start:end])


def test_the_ci_workflow_checkout_uses_shape_legs_token(project):
    """The exact token expression the fix specifies, and the guarded steps
    that let the job degrade instead of hard-failing when a private leg's
    submodule fetch fails without a leg credential (App token or
    `SHAPE_LEGS_TOKEN`) configured.

    String/YAML-structure assertions only, no live run: this workflow never
    executes in the test suite (no network, no GitHub Actions runner here).
    """
    workflow = (project / ".github" / "workflows" / "validate.yml").read_text()

    fetch = _step_block(workflow, "id: submodules")
    assert "git submodule update --init --recursive" in fetch
    assert "legs_available=true" in fetch
    assert "legs_available=false" in fetch
    assert "SHAPE_LEGS_TOKEN" in fetch
    assert "::warning::" in fetch

    pins_step = _step_block(workflow, "name: lockstep pins")
    assert "if: steps.submodules.outputs.legs_available == 'true'" in pins_step
    assert "validate-pins.py" in pins_step

    skipped = _step_block(
        workflow, "name: lockstep pins (skipped — legs unavailable)")
    assert "if: steps.submodules.outputs.legs_available != 'true'" in skipped
    assert "::warning::" in skipped

    fail_step = _step_block(
        workflow, "fail — a leg credential is configured but the legs "
        "still")
    assert ("if: steps.submodules.outputs.legs_available != 'true' && "
            "(env.SHAPE_LEGS_TOKEN_SET == 'true' || "
            "env.SHAPE_LEGS_APP_SET == 'true')") in fail_step
    assert "exit 1" in fail_step
    # The root checkout no longer depends on this token, so the failure
    # message must say the token cannot read a LEG repository, not the root.
    assert "does not use this token" in fail_step
    assert "LEG repositories" in fail_step

    # Naming and manifest checks read no leg working tree, so neither is
    # conditioned on `legs_available`.
    naming_step = _step_block(workflow, "name: naming policy")
    assert "if:" not in naming_step
    manifest_step = _step_block(workflow, "name: project manifest")
    assert "if:" not in manifest_step


def test_the_ci_workflow_root_checkout_uses_the_default_token(project):
    """The design flaw this fixes: `token: ${{ secrets.SHAPE_LEGS_TOKEN ||
    github.token }}` on the ROOT checkout meant a token correctly scoped to
    `contents:read` on the LEGS only (or a mis-scoped/unapproved one) broke
    `actions/checkout` itself with a 403 — before any check ran — on the
    first real use of the secret (MedxSoft/MedxEHR and MedxSoft/MedxGlass,
    runs 33821509948 and 33821512605). The root repository is always
    readable by the workflow's own default token, so the checkout step must
    carry no `token:` override at all, and must not persist whatever
    credential it does use into the local git config, since the submodule
    step authenticates the legs on its own terms.
    """
    workflow = (project / ".github" / "workflows" / "validate.yml").read_text()

    checkout = _step_block(workflow, "uses: actions/checkout@")
    assert "token:" not in checkout, (
        "the root checkout must use the default github.token — no `token:` "
        f"override of any kind: {checkout!r}")
    assert "submodules: false" in checkout
    assert "persist-credentials: false" in checkout


def test_the_submodule_fetch_step_scopes_the_token_to_itself(project):
    """The leg credential — whichever one resolved — is read only by the
    guarded submodule-fetch step, via that step's own `env:` — never the
    job's, never the checkout step's `with:` — and used through a
    `git -c url.<...>.insteadOf=<...>` rewrite rather than a bare `token:`
    field, so it authenticates the legs alone and never the root. Both
    submodule URL forms an adopted repository may carry are covered:
    `https://github.com/...` and SSH `git@github.com:`.
    """
    workflow = (project / ".github" / "workflows" / "validate.yml").read_text()
    fetch = _step_block(workflow, "id: submodules")

    assert "env:" in fetch
    assert "SHAPE_LEGS_APP_TOKEN: ${{ steps.app-token.outputs.token }}" in fetch
    assert "SHAPE_LEGS_TOKEN: ${{ secrets.SHAPE_LEGS_TOKEN }}" in fetch
    assert "insteadOf=https://github.com/" in fetch
    assert "insteadOf=git@github.com:" in fetch
    assert "x-access-token:${LEG_TOKEN}@github.com" in fetch
    # Falls back to a plain, unauthenticated fetch when neither is set.
    assert "else" in fetch
    assert "git submodule update --init --recursive" in fetch


def test_the_ci_workflow_mints_an_app_token_before_falling_back(project):
    """Ruled by Brett Heap on 2026-09-04: move the legs credential to a
    GitHub App installation token minted at run time, with the existing
    `SHAPE_LEGS_TOKEN` PAT staying as fallback. The mint step must be pinned
    by a 40-hex commit (this repository's own pinning rule — see
    `.github/workflows/tests.yml`), scoped to `contents: read`, guarded by a
    job-level env boolean rather than `secrets` in its `if:`, and the
    leg-fetch step must prefer the minted token over the PAT.
    """
    workflow = (project / ".github" / "workflows" / "validate.yml").read_text()

    mint_step = _step_block(workflow, "id: app-token")
    sha_line = next(line for line in mint_step.splitlines()
                     if "actions/create-github-app-token@" in line)
    sha = sha_line.split("@", 1)[1].split()[0]
    assert re.fullmatch(r"[0-9a-f]{40}", sha), (
        "actions/create-github-app-token must be pinned by a 40-hex commit "
        f"sha, not a tag: {sha_line!r}")
    assert "# v2." in sha_line, "keep the version as a trailing comment"
    assert "permission-contents: read" in mint_step
    assert "app-id: ${{ secrets.SHAPE_LEGS_APP_ID }}" in mint_step
    assert "private-key: ${{ secrets.SHAPE_LEGS_APP_PRIVATE_KEY }}" in mint_step
    assert "owner: ${{ github.repository_owner }}" in mint_step
    assert "repositories: ${{ steps.leg-names.outputs.legs }}" in mint_step
    assert "continue-on-error: false" in mint_step
    if_lines = [line for line in mint_step.splitlines()
                if line.lstrip().startswith("if:")]
    assert if_lines
    assert all("secrets." not in line for line in if_lines)

    env_block = workflow.split("steps:", 1)[0]
    assert "SHAPE_LEGS_APP_SET" in env_block
    assert ("SHAPE_LEGS_APP_SET: ${{ secrets.SHAPE_LEGS_APP_ID != '' && "
            "secrets.SHAPE_LEGS_APP_PRIVATE_KEY != '' }}") in env_block
    assert "SHAPE_LEGS_TOKEN_SET" in env_block

    # The fetch step must reference the App-minted token's output BEFORE
    # SHAPE_LEGS_TOKEN, so the App wins the resolution order when both are
    # configured.
    fetch = _step_block(workflow, "id: submodules")
    app_ref = fetch.index("steps.app-token.outputs.token")
    pat_ref = fetch.index("SHAPE_LEGS_TOKEN:")
    assert app_ref < pat_ref, (
        "the leg-fetch step must reference steps.app-token.outputs.token "
        "before SHAPE_LEGS_TOKEN")
    assert "legs_credential=app" in fetch
    assert "legs_credential=pat" in fetch
    assert "legs_credential=none" in fetch
    assert "legs_credential" in fetch and "GITHUB_OUTPUT" in fetch

    # A misconfigured App must fail loudly, naming both secrets and the
    # required installation, rather than silently degrading like a missing
    # SHAPE_LEGS_TOKEN does.
    explain_step = _step_block(
        workflow, "fail — the GitHub App could not mint an installation "
        "token")
    assert "if: failure() && steps.app-token.outcome == 'failure'" in \
        explain_step
    assert "SHAPE_LEGS_APP_ID" in explain_step
    assert "SHAPE_LEGS_APP_PRIVATE_KEY" in explain_step
    assert "Contents: read" in explain_step
    assert "exit 1" in explain_step


def _step_run_script(workflow: str, marker: str) -> str:
    """The dedented `run: |` body of the step block containing `marker`.

    Mirrors YAML block-scalar semantics rather than just taking the rest of
    `_step_block`'s window: the block ends at the first non-blank line whose
    indentation is LESS than the body's own (the comment block introducing
    the next step sits exactly there, at the step's 6-space indent, which is
    less than the `run:` body's 10), not at `_step_block`'s end-of-window.
    """
    block = _step_block(workflow, marker)
    lines = block.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "run: |")
    body = lines[start + 1:]
    indent = len(body[0]) - len(body[0].lstrip(" "))
    end = len(body)
    for i, line in enumerate(body):
        if line.strip() and len(line) - len(line.lstrip(" ")) < indent:
            end = i
            break
    return "\n".join(line[indent:] for line in body[:end])


def test_the_leg_name_extraction_reads_gitmodules_https_ssh_and_excludes_foreign_owners(project, tmp_path):
    """The `.gitmodules` -> `legs` extraction is tested as the REAL shell it
    is, not a Python reimplementation asserted "equal" to it (which could
    silently drift): this pulls the exact `run:` body of the "leg
    repository names from .gitmodules" step out of the rendered workflow and
    runs it, unmodified, against a crafted `.gitmodules` covering both URL
    forms and a leg owned by a different account.
    """
    workflow = (project / ".github" / "workflows" / "validate.yml").read_text()
    script = _step_run_script(workflow, "id: leg-names")

    work = tmp_path / "leg-names-fixture"
    work.mkdir()
    (work / ".gitmodules").write_text(
        '[submodule "spec"]\n'
        "\tpath = spec\n"
        "\turl = https://github.com/acme/Widget-spec\n"
        '[submodule "code"]\n'
        "\tpath = code\n"
        "\turl = git@github.com:acme/Widget-code.git\n"
        '[submodule "vendor"]\n'
        "\tpath = vendor\n"
        "\turl = https://github.com/other-org/Vendor-thing\n")
    output_file = tmp_path / "github_output"
    output_file.write_text("")

    result = subprocess.run(
        ["bash", "-c", script], cwd=work, capture_output=True, text=True,
        env={**os.environ, "REPO_OWNER": "acme",
             "GITHUB_OUTPUT": str(output_file)})
    assert result.returncode == 0, result.stderr

    [legs_line] = [line for line in output_file.read_text().splitlines()
                   if line.startswith("legs=")]
    legs = set(legs_line.split("=", 1)[1].split(","))
    # The foreign-owned leg is excluded from `legs` (an installation token
    # is per-owner) and reported instead as a warning naming it by name.
    assert legs == {"Widget-spec", "Widget-code"}
    assert "other-org/Vendor-thing" in result.stdout
    assert "::warning::" in result.stdout


def test_no_if_expression_reads_the_secrets_context(project):
    """The `secrets` context is not available in a step-level `if:`
    expression — GitHub rejects the whole workflow file as unparseable
    ("unrecognized named-value 'secrets'") rather than failing just that
    step, and the observed symptom is a push-event run with ZERO jobs. This
    was the defect on the first real projects (MedxSoft/MedxEHR PR #8,
    MedxSoft/MedxGlass PR #1).

    The fix moves the presence check into a job-level `env:` value (`secrets`
    IS allowed there — see the submodule-fetch step's own `env:`, asserted
    in `test_the_submodule_fetch_step_scopes_the_token_to_itself` above) and
    has every `if:` read `env.*`/`steps.*` instead. This test guards the
    class of defect, not just the one instance: it walks every `if:` line in
    the rendered workflow, not only the step named above.
    """
    workflow = (project / ".github" / "workflows" / "validate.yml").read_text()

    if_lines = [line for line in workflow.splitlines()
                if line.lstrip().startswith("if:")]
    assert if_lines, "expected at least one `if:` step condition"
    for line in if_lines:
        assert "secrets." not in line, (
            f"step-level `if:` must not read the `secrets` context: {line!r}")

    assert "SHAPE_LEGS_TOKEN_SET" in workflow
    # The job-level `env:` sits above `steps:` in the job block.
    env_block = workflow.split("steps:", 1)[0]
    assert "env:" in env_block
    assert ("SHAPE_LEGS_TOKEN_SET: ${{ secrets.SHAPE_LEGS_TOKEN != '' }}"
            in env_block)


def test_the_shape_pin_records_the_openreposhape_commit(project):
    sys.path.insert(0, str(REPO / "scripts"))
    from repo_shape import load_yaml
    pin = load_yaml(project / "contracts" / "shape-pin.yaml")
    assert pin["revision_kind"] == "commit"
    assert pin["materialization"] == "copied"
    assert pin["source_repository"] == "opensoft/openRepoShape"
    assert len(pin["files"]) >= 9
    manifest = load_yaml(project / "project.yaml")
    assert manifest["shape"]["commit"] == pin["commit"]


# --- visibility --------------------------------------------------------

def test_the_default_visibility_is_private(project):
    """No `--visibility` was passed for this fixture's scaffold."""
    sys.path.insert(0, str(REPO / "scripts"))
    from repo_shape import load_yaml
    manifest = load_yaml(project / "project.yaml")
    assert manifest["visibility"] == "private"


def test_internal_visibility_is_accepted(tmp_path):
    """`internal` is a real GitHub visibility (an enterprise org-internal
    repository: `gh repo create --internal`, `gh repo view --json visibility`
    -> `INTERNAL`) — not a typo of `private`/`public`, and this standard must
    accept it. Local bare repositories have no visibility of their own, so
    what is checked is the printed plan and what the manifest records."""
    remotes = tmp_path / "remotes"
    # NOT --local-remote-dir here: `--dry-run` returns before any `gh` or
    # `git` command runs, so this prints the REAL (non-local) plan line —
    # `gh repo create --internal` — with no network involved at all.
    dry = run_script(SCAFFOLD, "--org", ORG, "--project", "Fernwood",
                     "--elected-by", "Test Human", "--visibility", "internal",
                     "--dry-run", "--work-dir", str(tmp_path / "work"))
    assert dry.returncode == 0, dry.stderr
    assert "gh repo create --internal" in dry.stdout

    result = run_script(SCAFFOLD, "--org", ORG, "--project", "Fernwood",
                        "--elected-by", "Test Human", "--visibility", "internal",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / "work2"))
    assert result.returncode == 0, result.stderr + result.stdout
    sys.path.insert(0, str(REPO / "scripts"))
    from repo_shape import load_yaml
    manifest = load_yaml(tmp_path / "work2" / "Fernwood" / "project.yaml")
    assert manifest["visibility"] == "internal"


def test_a_bad_visibility_is_refused_by_argparse(tmp_path):
    result = run_script(SCAFFOLD, "--org", ORG, "--project", "Fernwood",
                        "--elected-by", "Test Human", "--visibility", "secret",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode != 0
    assert "invalid choice: 'secret'" in result.stderr
    assert "'internal'" in result.stderr
