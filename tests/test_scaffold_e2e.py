# SPDX-License-Identifier: Apache-2.0
"""End to end: scaffold into local bare remotes, clone recursively, bootstrap.

NO REAL REPOSITORY IS EVER CREATED. `--local-remote-dir` makes three bare
repositories on disk and uses them as origins; `gh` is never invoked.
"""

from __future__ import annotations

import os
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
    env = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
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
    submodule fetch fails without `SHAPE_LEGS_TOKEN` configured.

    String/YAML-structure assertions only, no live run: this workflow never
    executes in the test suite (no network, no GitHub Actions runner here).
    """
    workflow = (project / ".github" / "workflows" / "validate.yml").read_text()

    checkout = _step_block(workflow, "uses: actions/checkout@")
    assert "token: ${{ secrets.SHAPE_LEGS_TOKEN || github.token }}" in checkout
    assert "submodules: false" in checkout

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
        workflow, "fail — SHAPE_LEGS_TOKEN is set but the legs still")
    assert ("if: steps.submodules.outputs.legs_available != 'true' && "
            "env.SHAPE_LEGS_TOKEN_SET == 'true'") in fail_step
    assert "exit 1" in fail_step

    # Naming and manifest checks read no leg working tree, so neither is
    # conditioned on `legs_available`.
    naming_step = _step_block(workflow, "name: naming policy")
    assert "if:" not in naming_step
    manifest_step = _step_block(workflow, "name: project manifest")
    assert "if:" not in manifest_step


def test_no_if_expression_reads_the_secrets_context(project):
    """The `secrets` context is not available in a step-level `if:`
    expression — GitHub rejects the whole workflow file as unparseable
    ("unrecognized named-value 'secrets'") rather than failing just that
    step, and the observed symptom is a push-event run with ZERO jobs. This
    was the defect on the first real projects (MedxSoft/MedxEHR PR #8,
    MedxSoft/MedxGlass PR #1).

    The fix moves the presence check into a job-level `env:` value (`secrets`
    IS allowed there, and in `with:` — see the checkout step's `token:`,
    still asserted above) and has every `if:` read `env.*`/`steps.*` instead.
    This test guards the class of defect, not just the one instance: it
    walks every `if:` line in the rendered workflow, not only the step named
    above.
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
