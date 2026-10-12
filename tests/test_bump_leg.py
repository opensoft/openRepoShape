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

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ORG, PROJECT, REPO, git, run_script
#: The trailer helpers and the two lines a lane's run lands, imported from
#: the file that owns those rules rather than retyped — see
#: `tests/test_commit_trailers.py`.
from test_commit_trailers import TRAILERS, message_of, trailers_of

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml, tree_digest  # noqa: E402

BUMP = REPO / "scripts" / "bump-leg.py"
VALIDATE_PINS = "scripts/validate-pins.py"


@pytest.fixture(scope="module")
def bump_leg_module():
    """`bump-leg.py` as a module, so `commit_once` can be called in-process
    and the `git commit` argv it builds captured directly.

    A hyphenated filename is not importable the ordinary way; this is the
    same `spec_from_file_location` load `test_update_shape.py`'s
    `update_shape` fixture uses. Loading it here executes its own `from
    repo_shape import …` and `from shape_materialize import …`, which
    resolve to the SAME module objects imported above and in `conftest.py` —
    both are cached in `sys.modules` by name, not reloaded.
    """
    spec = importlib.util.spec_from_file_location("bump_leg_entry", BUMP)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

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


#: A workflow nobody has committed yet (#207): `{uses}` is its one job.
DRAFT = """\
name: draft
on: workflow_dispatch
jobs:
  d:
    uses: {uses}
"""


def spec_ref(sha: str) -> str:
    return f"{ORG}/{PROJECT}-spec/.github/workflows/x.yml@{sha}"


def leave_untracked(project: Path, name: str, uses: str) -> Path:
    """A draft workflow written into the working tree and committed nowhere."""
    path = project / ".github" / "workflows" / name
    path.write_text(DRAFT.format(uses=uses), encoding="utf-8")
    return path


def ignore_locally(project: Path, pattern: str) -> None:
    """`.gitignore` is tracked, and editing it would dirty the root; the
    clone's own `info/exclude` ignores a file without touching the tree."""
    exclude = Path(git("rev-parse", "--git-path", "info/exclude",
                       cwd=project).stdout.strip())
    if not exclude.is_absolute():
        exclude = project / exclude
    with exclude.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(pattern + "\n")


def found(project: Path) -> dict:
    """Everything a refusal promises not to have moved: the branch tip, the
    gitlink in the index, the leg's own checkout, the pin, the working-tree
    status and the bytes of every workflow file."""
    workflows = project / ".github" / "workflows"
    return {
        "head": git("rev-parse", "HEAD", cwd=project).stdout.strip(),
        "gitlink": git("ls-files", "-s", "--", "spec", cwd=project).stdout,
        "leg": git("rev-parse", "HEAD", cwd=project / "spec").stdout.strip(),
        "pin": (project / "contracts" / "spec-pin.yaml").read_bytes(),
        "status": git("status", "--porcelain", cwd=project).stdout,
        "workflows": {path.name: path.read_bytes()
                      for path in sorted(workflows.iterdir())},
    }


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


# --- only TRACKED workflows are rewritten and committed (#207) --------------

@pytest.mark.parametrize("name", ["draft.yml", "draft.yaml"])
def test_an_untracked_draft_naming_the_leg_is_refused_by_name_not_committed(
        project, scaffolded, advanced, name):
    """THE BUG: `plan_workflows` walked the directory on disk, so an untracked
    draft that referenced the leg was rewritten and then staged by the commit's
    explicit pathspec — added WHOLE to "Bump spec leg", as a new file. The
    root-clean check says untracked files are skipped because they cannot
    reach that commit, and this one did.

    It is refused rather than skipped: `validate-pins.py` reads every file on
    disk, so a skipped draft would leave its old `@<sha>` to turn the bump red
    after the rewrite. Refused BEFORE anything is written, and under
    `--dry-run` as well, so the dry run is never a promise the real run
    breaks. `.yaml` is read by the validator too, so it counts too.
    """
    was = git("rev-parse", "HEAD:spec", cwd=project).stdout.strip()
    branched(project)
    leave_untracked(project, name, spec_ref(was))
    before = found(project)
    assert before["status"] == f"?? .github/workflows/{name}\n"

    result = bump(project, scaffolded, advanced)
    assert result.returncode == 2, result.stderr + result.stdout
    assert "bump-leg-workflow-untracked" in result.stderr
    assert f".github/workflows/{name}  1 reference(s)" in result.stderr
    assert f"{ORG}/{PROJECT}-spec" in result.stderr
    assert "committed" not in result.stdout
    assert found(project) == before, "a refusal leaves the tree as it was"

    dry = bump(project, scaffolded, advanced, "--dry-run")
    assert dry.returncode == 2, dry.stderr + dry.stdout
    assert "bump-leg-workflow-untracked" in dry.stderr
    assert found(project) == before


def test_an_untracked_draft_refuses_the_whole_bump_and_rewrites_nothing(
        project, scaffolded, advanced):
    """A TRACKED workflow that has to move does not move on its own once an
    untracked one is in the way: half a bump is the failure the lockstep
    commit exists to prevent."""
    was, _ = reference_both_legs(project)
    branched(project)
    leave_untracked(project, "draft.yml", spec_ref(was))
    before = found(project)

    result = bump(project, scaffolded, advanced)
    assert result.returncode == 2, result.stderr + result.stdout
    assert "bump-leg-workflow-untracked" in result.stderr
    assert ".github/workflows/legs.yml" not in result.stderr, (
        "only the file git does not hold is named")
    assert found(project) == before
    assert was in (project / ".github" / "workflows" / "legs.yml").read_text()


def test_every_untracked_draft_is_named_once_with_its_count(
        project, scaffolded, advanced):
    was = git("rev-parse", "HEAD:spec", cwd=project).stdout.strip()
    branched(project)
    leave_untracked(project, "a-draft.yml", spec_ref(was))
    twice = project / ".github" / "workflows" / "b-draft.yml"
    twice.write_text(
        DRAFT.format(uses=spec_ref(was)) + f"  e:\n    uses: {spec_ref(was)}\n",
        encoding="utf-8")

    result = bump(project, scaffolded, advanced)
    assert result.returncode == 2, result.stderr + result.stdout
    assert "2 workflow file(s) that git does not track" in result.stderr
    assert ".github/workflows/a-draft.yml  1 reference(s)" in result.stderr
    assert ".github/workflows/b-draft.yml  2 reference(s)" in result.stderr


def test_moving_the_draft_out_of_the_directory_lets_the_bump_through(
        project, scaffolded, advanced, tmp_path):
    """The first of the two exits the refusal names."""
    was = git("rev-parse", "HEAD:spec", cwd=project).stdout.strip()
    branched(project)
    draft = leave_untracked(project, "draft.yml", spec_ref(was))
    assert bump(project, scaffolded, advanced).returncode == 2

    shutil.move(str(draft), str(tmp_path / "draft.yml"))
    result = bump(project, scaffolded, advanced)
    assert result.returncode == 0, result.stderr + result.stdout
    assert committed(project) == {"spec", "contracts/spec-pin.yaml"}
    assert validate(project).returncode == 0


def test_committing_the_draft_first_makes_it_move_with_the_bump(
        project, scaffolded, advanced):
    """The other exit: a COMMITTED workflow is a tracked file, so it is the
    ordinary case — rewritten and staged with the pin, the dry run having
    listed it."""
    was = git("rev-parse", "HEAD:spec", cwd=project).stdout.strip()
    branched(project)
    draft = leave_untracked(project, "draft.yml", spec_ref(was))
    assert bump(project, scaffolded, advanced).returncode == 2

    git("add", "--", ".github/workflows/draft.yml", cwd=project)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "Add the draft workflow", cwd=project)
    dry = bump(project, scaffolded, advanced, "--dry-run")
    assert dry.returncode == 0, dry.stderr + dry.stdout
    assert ".github/workflows/draft.yml  1 reference(s)" in dry.stdout

    result = bump(project, scaffolded, advanced)
    assert result.returncode == 0, result.stderr + result.stdout
    assert committed(project) == {"spec", "contracts/spec-pin.yaml",
                                  ".github/workflows/draft.yml"}
    assert f"@{advanced}" in draft.read_text()
    assert was not in draft.read_text()
    assert validate(project).returncode == 0


def test_an_untracked_workflow_with_nothing_to_move_is_left_alone(
        project, scaffolded, advanced):
    """Refusing is for a file the bump WOULD have rewritten. One that names no
    leg of this project, or this leg already at `--to`, is not the bump's
    business: not rewritten, not staged, not named, not refused — and the
    project's own gate agrees with it afterwards."""
    _, code = reference_both_legs(project)
    branched(project)
    other = leave_untracked(
        project, "other.yml",
        f"{ORG}/{PROJECT}-code/.github/workflows/y.yml@{code}")
    already = leave_untracked(project, "already.yml", spec_ref(advanced))
    kept = {path: path.read_bytes() for path in (other, already)}

    result = bump(project, scaffolded, advanced)
    assert result.returncode == 0, result.stderr + result.stdout
    assert committed(project) == {"spec", "contracts/spec-pin.yaml",
                                  ".github/workflows/legs.yml"}
    assert "1 reference(s) in 1 file(s)" in result.stdout
    assert "other.yml" not in result.stdout + result.stderr
    assert "already.yml" not in result.stdout + result.stderr
    assert {path: path.read_bytes() for path in kept} == kept
    status = git("status", "--porcelain", cwd=project).stdout.splitlines()
    assert sorted(status) == ["?? .github/workflows/already.yml",
                              "?? .github/workflows/other.yml"]
    assert validate(project).returncode == 0


def test_an_ignored_workflow_naming_the_leg_is_refused_untouched(
        project, scaffolded, advanced):
    """Ignored is untracked: `git status` does not show it, but the validator
    reads it, and the commit's `git add` would refuse it after the rewrite,
    in git's words and not this tool's. It is named before anything is
    written, and its bytes are exactly what they were."""
    was = git("rev-parse", "HEAD:spec", cwd=project).stdout.strip()
    branched(project)
    ignore_locally(project, ".github/workflows/local-*.yml")
    leave_untracked(project, "local-draft.yml", spec_ref(was))
    before = found(project)
    assert before["status"] == "", "an ignored file is not in the status"

    result = bump(project, scaffolded, advanced)
    assert result.returncode == 2, result.stderr + result.stdout
    assert "bump-leg-workflow-untracked" in result.stderr
    assert ".github/workflows/local-draft.yml  1 reference(s)" in result.stderr
    assert found(project) == before


def test_an_ignored_workflow_with_nothing_to_move_is_untouched(
        project, scaffolded, advanced):
    _, code = reference_both_legs(project)
    branched(project)
    ignore_locally(project, ".github/workflows/local-*.yml")
    local = leave_untracked(
        project, "local-other.yml",
        f"{ORG}/{PROJECT}-code/.github/workflows/y.yml@{code}")
    kept = local.read_bytes()

    result = bump(project, scaffolded, advanced)
    assert result.returncode == 0, result.stderr + result.stdout
    assert committed(project) == {"spec", "contracts/spec-pin.yaml",
                                  ".github/workflows/legs.yml"}
    assert local.read_bytes() == kept
    assert "local-other.yml" not in result.stdout + result.stderr
    assert git("status", "--porcelain", cwd=project).stdout == ""
    assert validate(project).returncode == 0


def test_a_tracked_workflow_with_a_non_ascii_name_is_not_taken_for_untracked(
        project, scaffolded, advanced):
    """The tracked set is read NUL-separated (`git ls-files -z`), and this is
    what that buys. Asked in the plain form, git QUOTES a name holding a byte
    outside ASCII (`core.quotePath`, on by default) as
    `".github/workflows/l\\303\\251gs.yml"`, which is not the path the
    directory walk yields; a tracked `l\u00e9gs.yml` that names the leg would
    then be refused as untracked, and "commit it first" could never clear it,
    because it is already committed. Non-ASCII is the one quoted character
    every platform this suite runs on can spell in a file name.
    """
    was = git("rev-parse", "HEAD:spec", cwd=project).stdout.strip()
    name = "l\u00e9gs.yml"
    relative = f".github/workflows/{name}"
    path = project / ".github" / "workflows" / name
    path.write_text(DRAFT.format(uses=spec_ref(was)), encoding="utf-8")
    git("add", "--", relative, cwd=project)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "Add a workflow with an accented name", cwd=project)
    branched(project)
    plain = git("-c", "core.quotePath=true", "ls-files", "--",
                ".github/workflows", cwd=project).stdout
    assert "\\303\\251" in plain, (
        "this test only means something while git quotes the name in the "
        f"plain listing: {plain!r}")

    result = bump(project, scaffolded, advanced)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "bump-leg-workflow-untracked" not in result.stderr
    assert f"@{advanced}" in path.read_text(encoding="utf-8")
    assert was not in path.read_text(encoding="utf-8")
    # Bytes, not text: the names come back from `-z` as git stores them.
    names = subprocess.run(
        ["git", "show", "--name-only", "-z", "--format=", "HEAD"],
        cwd=str(project), capture_output=True, check=True).stdout.split(b"\0")
    assert relative.encode("utf-8") in names
    assert validate(project).returncode == 0


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


# --- --trailer: the lines the commit ends with (#150) -----------------------

def test_bump_with_two_trailers_ends_the_commit_message_in_the_order_given(
        scaffolded, advanced, tmp_path):
    """`bump-leg.py` composes its own commit message, so a `Lane:` line —
    which the lane-collision protocol wants on every artifact a lane
    produces, the COMMIT included — reaches it no other way, and this
    estate's convention adds `Co-Authored-By:` beside it (#111 gave the other
    two pin-moving tools this; #150 is this one's turn).

    TWO BUMPS OF THE SAME LEG TO THE SAME COMMIT, from two independent copies
    of the same starting clone, one with the flag and one without, so the
    trailer block is the ONLY difference between the two messages: the
    ordering claim and the "a run passing none writes what it always wrote"
    claim, in one assertion, with no pasted copy of today's wording to go
    stale.
    """
    plain = tmp_path / "plain"
    trailed = tmp_path / "trailed"
    shutil.copytree(scaffolded["clone"], plain, symlinks=True)
    shutil.copytree(scaffolded["clone"], trailed, symlinks=True)
    branched(plain)
    branched(trailed)

    plain_result = bump(plain, scaffolded, advanced)
    trailed_result = bump(trailed, scaffolded, advanced,
                          "--trailer", TRAILERS[0], "--trailer", TRAILERS[1])
    assert plain_result.returncode == 0, plain_result.stderr + plain_result.stdout
    assert trailed_result.returncode == 0, (
        trailed_result.stderr + trailed_result.stdout)

    assert message_of(trailed) == \
        message_of(plain) + "\n" + "\n".join(TRAILERS) + "\n"
    assert trailers_of(trailed) == list(TRAILERS), (
        "and git reads them back as the trailer block, in order")
    assert trailers_of(plain) == [], "the run without the flag carries none"
    # Still ONE commit touching the same paths either way: a trailer changes
    # the message and nothing else.
    assert committed(trailed) == committed(plain)
    assert validate(trailed).returncode == 0
    assert validate(plain).returncode == 0


def test_no_trailers_leaves_the_commit_argv_byte_identical(bump_leg_module,
                                                           tmp_path,
                                                           monkeypatch):
    """THE CLAIM `--dry-run` CANNOT SHOW, because it makes no commit at all:
    passed no `--trailer`, `commit_once` must build the exact `git commit`
    argv it has always built. `shape_materialize.commit_trailers` returns an
    EMPTY argument list for no trailers, by construction — this asserts that
    `commit_once` actually uses that empty list rather than, say, always
    inserting `--trailer` markers even when there is nothing to put in them.
    """
    root = tmp_path / "repo"
    root.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=root)
    (root / "a.txt").write_text("x\n", encoding="utf-8")

    captured: dict = {}
    real_run = subprocess.run

    def spy(args, **kwargs):
        if args[:2] == ["git", "commit"]:
            captured["args"] = list(args)
        return real_run(args, **kwargs)

    monkeypatch.setattr(bump_leg_module.subprocess, "run", spy)
    head = bump_leg_module.commit_once(root, "A commit\n", ["a.txt"])

    assert captured["args"] == ["git", "commit", "-q", "-F", "-", "--",
                                "a.txt"], (
        "no --trailer means no extra arguments before `--` — the exact argv "
        "this tool has always built")
    assert git("rev-parse", "HEAD", cwd=root).stdout.strip() == head


def test_dry_run_prints_the_trailers_after_the_old_to_new_line(project,
                                                               scaffolded,
                                                               advanced):
    """`--dry-run` shows what a real run would end the commit with,
    positioned after the `old -> new` line it already prints — the same
    "read it before it lands" property AGENTS.md's "Advancing a leg" already
    asks of that line."""
    was = git("rev-parse", "HEAD:spec", cwd=project).stdout.strip()
    branched(project)
    result = bump(project, scaffolded, advanced, "--dry-run",
                 "--trailer", TRAILERS[0], "--trailer", TRAILERS[1])
    assert result.returncode == 0, result.stderr + result.stdout

    old_to_new = f"{was[:12]} -> {advanced[:12]}"
    assert old_to_new in result.stdout
    for line in TRAILERS:
        assert line in result.stdout
    assert result.stdout.index(old_to_new) < result.stdout.index(TRAILERS[0]), (
        "the trailers are printed after the `old -> new` line, not before it")
    assert git("status", "--porcelain", cwd=project).stdout == ""


def test_dry_run_with_no_trailer_says_so(project, scaffolded, advanced):
    branched(project)
    result = bump(project, scaffolded, advanced, "--dry-run")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "trailers     none" in result.stdout


@pytest.mark.parametrize("value", ["Lane xfactory-1", "Lane:xfactory-1",
                                   "Lane: "])
def test_a_malformed_trailer_is_refused_before_the_project_is_read(
        project, scaffolded, advanced, value):
    """ARGPARSE'S OWN ERROR PATH: a malformed trailer is a malformed command
    line, refused with the usage line beside it — before `cmd_bump` ever
    runs, so nothing is fetched, nothing is staged and HEAD does not move,
    even though `--to` and the project both are otherwise entirely valid."""
    branched(project)
    head = git("rev-parse", "HEAD", cwd=project).stdout.strip()
    result = bump(project, scaffolded, advanced, "--trailer", value)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "--trailer" in result.stderr
    assert "usage:" in result.stderr
    assert git("rev-parse", "HEAD", cwd=project).stdout.strip() == head, (
        "argparse refuses before the tool reads anything, let alone commits")
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
