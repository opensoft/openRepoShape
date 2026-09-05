# SPDX-License-Identifier: Apache-2.0
"""`scripts/bump-leg.py`: one leg advanced, three facts, ONE commit.

NO NETWORK AND NO GITHUB. The session's scaffold made three BARE repositories
on disk and cloned the assembly root recursively; the spec leg is advanced in
a second clone of its own bare remote and pushed back to it, which is the
whole of the "the remote has this commit" story this tool depends on.

THE SPEC LEG'S `main` IS NOT MOVED. The bare repositories are session-scoped,
so an advance pushed onto the leg's default branch would move under every
other module in this suite. It is pushed to a branch of its own instead, and
`bump-leg.py` asks whether the commit is on ANY branch of the remote — which
is the question a pin actually has.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ORG, PROJECT, REPO, git, run_script

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml, tree_digest  # noqa: E402

BUMP = REPO / "scripts" / "bump-leg.py"
VALIDATE_PINS = "scripts/validate-pins.py"

#: Where the advanced spec commit is pushed. See the module docstring.
ADVANCE_BRANCH = "bump-leg-advance"

#: The branch every test bumps on. The tool refuses to commit onto the
#: project's tracking branch, because the next step it prints would then be a
#: push to the default branch and these organisations are pull-request only.
WORKING_BRANCH = "bump/spec"

WORKFLOW = """\
name: legs
on: [pull_request]
jobs:
  spec:
    uses: {org}/{project}-spec/.github/workflows/x.yml@{spec}
  code:
    uses: {org}/{project}-code/.github/workflows/y.yml@{code}
"""


@pytest.fixture(scope="module")
def advanced(scaffolded, tmp_path_factory) -> str:
    """A real new commit on the spec leg's bare remote; returns its sha."""
    work = tmp_path_factory.mktemp("spec-advance") / f"{PROJECT}-spec"
    proc = subprocess.run(
        ["git", "clone", "-q",
         str(scaffolded["remotes"] / f"{PROJECT}-spec.git"), str(work)],
        capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    (work / "NEW-CONTRACT.md").write_text("# a contract the leg gained\n")
    git("add", "--", "NEW-CONTRACT.md", cwd=work)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "Advance the spec leg", cwd=work)
    git("push", "-q", "origin", f"HEAD:refs/heads/{ADVANCE_BRANCH}", cwd=work)
    return git("rev-parse", "HEAD", cwd=work).stdout.strip()


def branched(project: Path, name: str = WORKING_BRANCH) -> Path:
    git("checkout", "-q", "-b", name, cwd=project)
    return project


def bump(project: Path, scaffolded: dict, to: str, *extra: str,
         leg: str = "spec"):
    return run_script(BUMP, "--root", str(project), "--leg", leg, "--to", to,
                      "--local-remote-dir", str(scaffolded["remotes"]), *extra)


def validate(project: Path):
    return run_script(project / VALIDATE_PINS, cwd=project)


def committed(project: Path) -> set:
    return set(git("show", "--name-only", "--format=", "HEAD",
                   cwd=project).stdout.split())


def reference_both_legs(project: Path) -> tuple[str, str]:
    """A workflow naming BOTH legs at their current pins, committed."""
    spec = git("rev-parse", "HEAD:spec", cwd=project).stdout.strip()
    code = git("rev-parse", "HEAD:code", cwd=project).stdout.strip()
    (project / ".github" / "workflows" / "legs.yml").write_text(
        WORKFLOW.format(org=ORG, project=PROJECT, spec=spec, code=code),
        encoding="utf-8")
    git("add", "--", ".github/workflows/legs.yml", cwd=project)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "Reference both legs from a workflow", cwd=project)
    return spec, code


# --- the bump itself --------------------------------------------------------

def test_bump_moves_the_gitlink_and_the_pin_in_one_commit(project, scaffolded,
                                                          advanced):
    """THE WHOLE POINT: the gitlink, `commit:` and the digest, together.

    The digest is compared against a FRESH recomputation from the leg's own
    objects rather than against the string the tool printed — a tool that
    wrote its own arithmetic back to itself would pass a test that read its
    output.
    """
    before = git("rev-parse", "HEAD", cwd=project).stdout.strip()
    branched(project)
    result = bump(project, scaffolded, advanced)
    assert result.returncode == 0, result.stderr + result.stdout

    assert git("rev-list", "--count", f"{before}..HEAD",
               cwd=project).stdout.strip() == "1"
    assert git("rev-parse", "HEAD:spec", cwd=project).stdout.strip() == advanced
    pin = load_yaml(project / "contracts" / "spec-pin.yaml")
    assert pin["commit"] == advanced
    assert pin["revision_kind"] == "commit"
    assert pin["digests"]["tree_sha256"] == tree_digest(project / "spec",
                                                        advanced)
    assert committed(project) == {"spec", "contracts/spec-pin.yaml"}
    assert validate(project).returncode == 0, "the project's own gate is green"
    assert git("status", "--porcelain", cwd=project).stdout == "", (
        "a bump leaves nothing behind in the working tree")


def test_the_leg_is_left_at_the_commit_and_bootstrap_re_places_it(
        project, scaffolded, advanced):
    """A bump pins; `bootstrap.py` places. The leg is left DETACHED at the new
    commit and no branch inside the leg is moved — moving one would be this
    tool pushing somebody's branch around from inside a submodule — so the
    output says which command puts it back on its tracking branch."""
    branched(project)
    result = bump(project, scaffolded, advanced)
    assert result.returncode == 0, result.stderr + result.stdout
    assert git("rev-parse", "HEAD", cwd=project / "spec").stdout.strip() == \
        advanced
    assert git("symbolic-ref", "--quiet", "HEAD", cwd=project / "spec",
               check=False).returncode != 0, "the leg is detached"
    assert "make bootstrap" in result.stdout


def test_the_message_and_the_next_step_are_a_pull_request(project, scaffolded,
                                                          advanced):
    was = git("rev-parse", "HEAD:spec", cwd=project).stdout.strip()
    branched(project)
    result = bump(project, scaffolded, advanced)
    assert result.returncode == 0, result.stderr + result.stdout

    assert git("log", "-1", "--format=%s", cwd=project).stdout.strip() == \
        f"Bump spec leg to {advanced[:12]} in {PROJECT}"
    body = git("log", "-1", "--format=%b", cwd=project).stdout
    assert f"{was[:12]} -> {advanced[:12]}" in body
    assert tree_digest(project / "spec", advanced) in body
    assert "validate-pins.py" in body

    assert f"push -u origin {WORKING_BRANCH}" in result.stdout
    assert "pull request" in result.stdout
    assert "push -u origin main" not in result.stdout, (
        "never a direct push to the default branch")


def test_bumping_to_the_commit_already_pinned_does_nothing(project, scaffolded):
    """Exit 1 is `nothing`, not a refusal and not a success: re-running a bump
    that already landed must not write an empty commit."""
    pinned = git("rev-parse", "HEAD:spec", cwd=project).stdout.strip()
    head = git("rev-parse", "HEAD", cwd=project).stdout.strip()
    branched(project)
    result = bump(project, scaffolded, pinned)
    assert result.returncode == 1, result.stderr + result.stdout
    assert "nothing to do" in result.stdout
    assert git("rev-parse", "HEAD", cwd=project).stdout.strip() == head


# --- the third fact: the workflow references --------------------------------

def test_a_reference_to_this_leg_moves_and_other_references_do_not(
        project, scaffolded, advanced):
    """Fact 3, and the blast radius of it.

    The CODE leg's reference and the scaffold's own
    `actions/create-github-app-token@<40 hex>` are both `@<sha>` references in
    the same directory. A bump that moved either would be a supply-chain edit
    wearing a bookkeeping commit's message.
    """
    was, code = reference_both_legs(project)
    untouched = (project / ".github" / "workflows" / "validate.yml").read_bytes()
    branched(project)
    result = bump(project, scaffolded, advanced)
    assert result.returncode == 0, result.stderr + result.stdout

    text = (project / ".github" / "workflows" / "legs.yml").read_text()
    assert f"{ORG}/{PROJECT}-spec/.github/workflows/x.yml@{advanced}" in text
    assert f"{ORG}/{PROJECT}-code/.github/workflows/y.yml@{code}" in text
    assert was not in text
    assert (project / ".github" / "workflows" /
            "validate.yml").read_bytes() == untouched
    assert "1 reference(s) in 1 file(s)" in result.stdout
    assert committed(project) == {"spec", "contracts/spec-pin.yaml",
                                  ".github/workflows/legs.yml"}
    assert validate(project).returncode == 0


def test_the_reference_expression_is_the_validators_own():
    """One expression, two files. A rewriter matching a wider or a narrower
    set than the checker is a rewriter that leaves a reference the gate still
    calls wrong, which is the failure this whole invariant is about."""
    def expression(path: Path) -> str:
        text = path.read_text(encoding="utf-8")
        start = text.index("WORKFLOW_REF_RE = re.compile(")
        return text[start:text.index(")\n", start)]

    assert expression(BUMP) == expression(
        REPO / "templates" / "assembly-root" / "scripts" / "validate-pins.py")


# --- --dry-run --------------------------------------------------------------

def test_dry_run_prints_the_move_and_changes_nothing(project, scaffolded,
                                                     advanced):
    was, _ = reference_both_legs(project)
    branched(project)
    head = git("rev-parse", "HEAD", cwd=project).stdout.strip()
    pin = (project / "contracts" / "spec-pin.yaml").read_bytes()
    workflow = (project / ".github" / "workflows" / "legs.yml").read_bytes()

    result = bump(project, scaffolded, advanced, "--dry-run")
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"{was[:12]} -> {advanced[:12]}" in result.stdout
    assert ".github/workflows/legs.yml" in result.stdout
    assert "--dry-run: nothing was changed." in result.stdout

    assert git("rev-parse", "HEAD", cwd=project).stdout.strip() == head
    assert git("rev-parse", "HEAD:spec", cwd=project).stdout.strip() == was
    assert git("rev-parse", "HEAD", cwd=project / "spec").stdout.strip() == was
    assert (project / "contracts" / "spec-pin.yaml").read_bytes() == pin
    assert (project / ".github" / "workflows" /
            "legs.yml").read_bytes() == workflow
    assert git("status", "--porcelain", cwd=project).stdout == ""


# --- the refusals -----------------------------------------------------------

def test_a_short_sha_is_refused(project, scaffolded, advanced):
    branched(project)
    result = bump(project, scaffolded, advanced[:12])
    assert result.returncode == 2
    assert "bump-leg-target-not-a-commit" in result.stderr


def test_a_commit_the_remote_does_not_have_is_refused(project, scaffolded):
    branched(project)
    result = bump(project, scaffolded, "0123456789abcdef" * 2 + "01234567")
    assert result.returncode == 2
    assert "bump-leg-commit-not-on-remote" in result.stderr
    assert git("status", "--porcelain", cwd=project).stdout == ""


def test_a_commit_that_was_never_pushed_is_refused(project, scaffolded):
    """A pin the rest of the world cannot fetch is a root the rest of the
    world cannot bootstrap. `git fetch <remote> <sha>` answers success without
    asking the remote anything when the object is already local, so the tool
    asks for REACHABILITY from a remote branch instead — this is the test that
    would have passed on the fetch and fails on the reachability."""
    was = git("rev-parse", "HEAD:spec", cwd=project).stdout.strip()
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
        "--allow-empty", "-m", "never pushed", cwd=project / "spec")
    local = git("rev-parse", "HEAD", cwd=project / "spec").stdout.strip()
    git("checkout", "-q", "--detach", was, cwd=project / "spec")
    branched(project)
    result = bump(project, scaffolded, local)
    assert result.returncode == 2
    assert "bump-leg-commit-local-only" in result.stderr


def test_a_dirty_root_is_refused(project, scaffolded, advanced):
    branched(project)
    (project / "README.md").write_text("edited\n", encoding="utf-8")
    result = bump(project, scaffolded, advanced)
    assert result.returncode == 2
    assert "bump-leg-root-dirty" in result.stderr
    assert "README.md" in result.stderr


def test_the_tracking_branch_is_refused(project, scaffolded, advanced):
    """The commit is not made where the only next step would be a push to the
    default branch. The refusal carries the exact `git switch -c` to run."""
    result = bump(project, scaffolded, advanced)
    assert result.returncode == 2
    assert "bump-leg-on-tracking-branch" in result.stderr
    assert "switch -c bump/spec-" in result.stderr


def test_the_assembly_root_is_not_a_leg(project, scaffolded, advanced):
    branched(project)
    result = bump(project, scaffolded, advanced, leg="assembly")
    assert result.returncode == 2
    assert "bump-leg-assembly-is-not-a-leg" in result.stderr


def test_a_leg_the_manifest_does_not_declare_is_refused(project, scaffolded,
                                                        advanced):
    branched(project)
    result = bump(project, scaffolded, advanced, leg="docs")
    assert result.returncode == 2
    assert "bump-leg-unknown-leg" in result.stderr


def test_a_family_holder_is_refused(project, scaffolded, advanced, tmp_path):
    """A family's member pins move with `family.py bump`; a root's leg pins
    move with this. Pointing either at the other's manifest is a mistake worth
    naming rather than half-performing."""
    holder = tmp_path / "Holder"
    holder.mkdir()
    (holder / "family.yaml").write_text("kind: family-manifest\n")
    result = run_script(BUMP, "--root", str(holder), "--leg", "spec",
                        "--to", advanced)
    assert result.returncode == 2
    assert "bump-leg-root-not-a-project" in result.stderr
    assert "family.py" in result.stderr


# --- the rollback -----------------------------------------------------------

def test_a_red_validator_rolls_every_byte_back(project, scaffolded, advanced):
    """The CODE pin is corrupted and COMMITTED first, so the root is clean
    when the bump starts and `validate-pins.py` is red for a reason the bump
    did not cause. Everything the bump wrote — the pin, the workflow file, the
    leg's checkout and the index — must be exactly as it was found."""
    was, _ = reference_both_legs(project)
    code_pin = project / "contracts" / "code-pin.yaml"
    digest = load_yaml(code_pin)["digests"]["tree_sha256"]
    code_pin.write_text(code_pin.read_text().replace(digest, "b" * 64),
                        encoding="utf-8")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "Corrupt the code pin's digest", "--", "contracts/code-pin.yaml",
        cwd=project)
    branched(project)

    head = git("rev-parse", "HEAD", cwd=project).stdout.strip()
    index = git("ls-files", "-s", "--", "spec", cwd=project).stdout
    pin = (project / "contracts" / "spec-pin.yaml").read_bytes()
    workflow = (project / ".github" / "workflows" / "legs.yml").read_bytes()

    result = bump(project, scaffolded, advanced)
    assert result.returncode == 2
    assert "bump-leg-validators-red" in result.stderr
    assert "pin-digest-mismatch" in result.stderr, (
        "the validator's own output is what the refusal carries")

    assert git("rev-parse", "HEAD", cwd=project).stdout.strip() == head
    assert git("ls-files", "-s", "--", "spec", cwd=project).stdout == index
    assert git("rev-parse", "HEAD", cwd=project / "spec").stdout.strip() == was
    assert (project / "contracts" / "spec-pin.yaml").read_bytes() == pin
    assert (project / ".github" / "workflows" /
            "legs.yml").read_bytes() == workflow
    assert git("status", "--porcelain", cwd=project).stdout == "", (
        "the tree is exactly as it was found")
