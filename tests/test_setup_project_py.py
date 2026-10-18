# SPDX-License-Identifier: Apache-2.0
"""`setup-project.py` - the same run as `setup.sh`, on an interpreter alone.

THIS FILE MIRRORS `tests/test_setup_sh.py` CASE FOR CASE. Two entry points
that refuse different things in different words are two standards, so every
assertion there has a twin here: the same end-to-end run, the same refusals,
the same self-bootstrap properties, the same exit codes. What is NEW is what
`setup.sh` cannot have - a positional `<Project>`, a piped-on-stdin run, and
the two tests at the bottom that hold `setup.sh` to being a SHIM over this
file (#50) rather than a second implementation of it.

NO NETWORK AND NO GITHUB, exactly as everywhere else in this suite: every run
that reaches the preflight passes `--local-remote-dir`, which creates three
BARE repositories in a temporary directory and uses them as origins. The
self-bootstrap tests point `OPENREPOSHAPE_REPO` at THIS checkout (a local
path, so `git clone` stays offline) instead of opensoft/openRepoShape.

Unlike `test_setup_sh.py` this file carries NO Windows skip: it is the reason
that skip is honest.
"""

from __future__ import annotations

import ast
import errno
import importlib.util
import ntpath
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

from pathlib import Path

import pytest

from conftest import (FILE_PROTOCOL, REPO, appended_to_command_scope,
                      assert_read_through_git, assert_store_read_through_git,
                      git, rmtree)

from conftest import assert_refuses_for_want_of_a_terminal

from conftest import PTY_SKIP, run_in_a_terminal

from conftest import (DISCARD_IT, DISCARD_IT_IF_UNUSED, KEEP_IT,
                      TAKEN_CLONE_PATHS,
                      assert_a_rehearsals_clone_stops_the_real_run,
                      assert_a_taken_clone_path_is_refused,
                      assert_the_plan_refuses_a_remote_that_exists)

from conftest import (DECLARATIONS, DRY_RUNS, FILE_ABOVE_THE_CLONE,
                      UPSTREAM_CASINGS,
                      assert_a_dry_run_passed_through_ends_at_the_plan,
                      assert_a_file_above_the_clone_path_is_refused,
                      assert_an_upstream_origin_in_any_case_needs_an_org,
                      assert_the_backstop_is_finished_by_hand_as_printed,
                      assert_the_closing_cd_is_one_word,
                      assert_the_naming_check_hears_what_is_passed_through,
                      assert_the_scaffold_leaves_its_next_steps_to_setup,
                      assert_the_upstream_org_is_refused_in_any_case)

from conftest import (CHAIN_LINK_TREES, DRIVE_WAY_OUT, WRITE_IT,
                      assert_a_parent_nobody_can_write_in_is_refused,
                      assert_a_plan_that_never_printed_could_not_be_produced,
                      assert_step_four_reads_a_chain_as_the_plan_does,
                      assert_a_chain_of_one_link_has_no_source_to_note,
                      assert_an_empty_pin_source_is_the_plans_to_refuse)

from conftest import (STEP_FOUR_WORDS, load_without_bytecode,
                      assert_step_four_speaks_in_the_plans_words,
                      clear_ambient_pin_sources)

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402

SETUP_PROJECT = REPO / "setup-project.py"
SETUP_SH = REPO / "setup.sh"
DEGRADE_LINE = "authority is not wallet-carried in this org"

#: The running interpreter's own `major.minor`, which is what the preflight
#: reports. Never a `python3` on PATH: on Windows there is not one, and that
#: fact is the whole reason this file's subject exists.
RUNNING_PYTHON = "python %d.%d" % (sys.version_info[0], sys.version_info[1])


def run_entry(*args: str, stdin: str = "", cwd: Path | None = None,
              extra_env: dict | None = None,
              script: Path | None = None) -> subprocess.CompletedProcess:
    """The entry point, run as a person runs it: `<interpreter> <file> ...`.

    `script` is what the self-bootstrap cases need - a lone COPY of the file
    somewhere that is not a checkout - and defaults to this checkout's own.
    Stdin is a pipe and the run has NO controlling terminal: a session of its
    own (#492), because the file asks at the controlling terminal when stdin
    is not one, and the terminal pytest was started from is nobody's answer.
    """
    env = dict(os.environ)
    env.setdefault("GIT_AUTHOR_NAME", "openRepoShape tests")
    env.setdefault("GIT_AUTHOR_EMAIL", "tests@openreposhape.invalid")
    env.setdefault("GIT_COMMITTER_NAME", "openRepoShape tests")
    env.setdefault("GIT_COMMITTER_EMAIL", "tests@openreposhape.invalid")
    env.update(extra_env or {})
    return subprocess.run(
        [sys.executable, str(script or SETUP_PROJECT), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False, input=stdin,
        cwd=str(cwd) if cwd is not None else str(REPO), env=env,
        start_new_session=True)


def entry_point_module():
    """`setup-project.py` imported as a module.

    The filename has a hyphen in it, so it cannot be imported by name; and it
    is imported at all only by the two tests that assert on values rather than
    on a run - the usage banner, and the one `yes` - because a terminal cannot
    be faked in a subprocess on every platform this suite runs on.
    """
    spec = importlib.util.spec_from_file_location("setup_project_entry",
                                                  SETUP_PROJECT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_fork_dir(tmp_path: Path, origin_url: str, upstream_url: str) -> Path:
    """A directory that IS a git repo (so the origin/upstream remote reads
    have something to find) but is not itself an openRepoShape checkout.

    The remotes are read from the directory the run was STARTED IN, not from
    the one the file lives in - the two are the same for a real fork clone,
    and deliberately different here so this test does not depend on this
    checkout's own `origin`, whatever that happens to be.
    """
    fork = tmp_path / "fork"
    fork.mkdir()
    git("init", "-q", cwd=fork)
    git("remote", "add", "origin", origin_url, cwd=fork)
    git("remote", "add", "upstream", upstream_url, cwd=fork)
    return fork


def make_outside_checkout(tmp_path: Path) -> Path:
    """A directory holding a standalone COPY of the entry point that is not
    inside any git checkout at all - no `.git`, no `scaffold-project.py`, no
    `contracts/`. This is what a downloaded `setup-project.py` looks like on
    disk: one file with nothing beside it, run from wherever the person
    happened to be standing.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    copy = outside / "setup-project.py"
    shutil.copy(SETUP_PROJECT, copy)
    copy.chmod(0o755)
    return outside


@pytest.fixture(scope="module")
def setup_run(tmp_path_factory) -> dict:
    """One real run, end to end, with no network.

    `--org` is explicit here (not what this fixture is testing) because local
    mode reads the real `origin` remote of the directory it runs in, and this
    suite must pass identically whether that is a fork or opensoft's own clone.
    """
    base = tmp_path_factory.mktemp("setup-project")
    result = run_entry("--project", "Sample", "--yes", "--org", "demoorg",
                       "--local-remote-dir", str(base / "remotes"),
                       "--into", str(base / "work"))
    return {"base": base, "result": result, "clone": base / "work" / "Sample"}


def test_setup_project_runs_end_to_end(setup_run):
    result = setup_run["result"]
    assert result.returncode == 0, result.stderr + result.stdout


def test_it_creates_the_three_bare_remotes(setup_run):
    remotes = setup_run["base"] / "remotes"
    for name in ("Sample.git", "Sample-spec.git", "Sample-code.git"):
        assert (remotes / name).is_dir(), f"{name} was not created"


def test_the_assembly_root_is_cloned_where_into_says(setup_run):
    clone = setup_run["clone"]
    assert clone.is_dir(), f"{clone} does not exist"
    assert (clone / "project.yaml").is_file()
    assert (clone / ".gitmodules").is_file()


def test_the_entry_points_clone_was_read_through_git_not_through_files(
        setup_run):
    """#440, through the interpreter alone: see `assert_read_through_git`."""
    assert_read_through_git(setup_run["clone"])


def test_the_rewrite_reads_a_plain_path_through_git_in_an_awkward_directory(
        tmp_path):
    """#440: the two leg clones `--recurse-submodules` makes are git's own,
    from the plain path `.gitmodules` records, and no flag reaches them. What
    does is `local_remotes_by_url`'s `url.<file URI>.insteadOf` rewrite, and
    this is it ALONE (no `--no-local`) on a plain path, in a directory whose
    name a URL must encode: a space, and a `%` that would read as an escape
    if the base were spelled by hand. Source objects pushed into a bare
    repository are loose; the clone holds one pack."""
    remotes = tmp_path / "odd dir 100%" / "remotes"
    source = tmp_path / "source"
    source.mkdir()
    git("init", "-q", "-b", "main", cwd=source)
    (source / "leg.txt").write_bytes(b"a leg\n")
    git("add", "leg.txt", cwd=source)
    git("commit", "-q", "-m", "one", cwd=source)
    bare = remotes / "Leg.git"
    git("init", "-q", "--bare", str(bare), cwd=tmp_path)
    git("push", "-q", str(bare), "main", cwd=source)

    args = entry_point_module().local_remotes_by_url(str(remotes))
    clone = tmp_path / "clone"
    proc = subprocess.run(["git", *FILE_PROTOCOL, *args, "clone", "-q",
                           str(bare), str(clone)],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    assert_store_read_through_git(clone, "the clone")


def test_the_root_is_read_through_git_when_the_remotes_are_spelled_by_a_symlink(
        tmp_path):
    """#440: `--no-local` is what covers the ROOT, and not the rewrite.

    The rewrite's prefix is the directory RESOLVED, as the scaffold wrote it
    into `.gitmodules`, so it reaches the legs; the root's own URL is the
    directory as it was TYPED (`abspath`, never `resolve()`), which a symlink
    makes another spelling of the same directory (on macOS the temporary
    root, `/var`, is one: `/private/var`) and the prefix does not match.
    Only `--no-local` is left to read the root through git."""
    base = tmp_path / "run"
    real, link = tmp_path / "real", tmp_path / "link"
    real.mkdir()
    try:
        os.symlink(real, link, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"this platform cannot create a symlink here: {exc}")
    result = run_entry("--project", "Sample", "--yes", "--org", "demoorg",
                       "--local-remote-dir", str(link / "remotes"),
                       "--into", str(base / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    assert_read_through_git(base / "work" / "Sample")


def test_both_legs_are_on_main_after_bootstrap(setup_run):
    """The whole point of step (7): nobody is left staring at a detached HEAD.

    And it is `scripts/bootstrap.py` that got them there, run directly rather
    than through `make bootstrap` - the difference this file exists for.
    """
    for leg in ("spec", "code"):
        branch = git("rev-parse", "--abbrev-ref", "HEAD",
                     cwd=setup_run["clone"] / leg).stdout.strip()
        assert branch == "main", f"{leg} is on {branch!r}, expected 'main'"


def test_bootstrap_ran_and_printed_the_degrade_line(setup_run):
    out = setup_run["result"].stdout
    assert DEGRADE_LINE in out
    assert "bootstrap ok" in out
    assert "pins ok" in out


def test_the_final_block_names_the_path_and_the_three_urls(setup_run):
    """`os.path.abspath` on both sides, never `Path.resolve()`.

    The entry point absolutises the way `setup.sh:103-108` did (pre-#50 line
    numbers; the shim has no abspath of its own now) - join onto the
    invocation directory, normalise, stop. `resolve()` would additionally
    rewrite an 8.3 short component on Windows, and then the path it printed
    and the path the test holds would be two spellings of one directory.
    """
    out = setup_run["result"].stdout
    assert "DONE. Sample is scaffolded and bootstrapped." in out
    assert os.path.abspath(str(setup_run["clone"])) in out
    for name in ("Sample.git", "Sample-spec.git", "Sample-code.git"):
        assert name in out
    assert "make validate" in out


def test_preflight_reports_each_prerequisite(setup_run):
    out = setup_run["result"].stdout
    assert "(1) preflight" in out
    assert "git " in out
    assert RUNNING_PYTHON in out, (
        "the preflight must report the RUNNING interpreter, not a probe for "
        "one on PATH")
    assert "make is not required" in out
    assert "gh not required" in out, "local mode must skip the gh preflight"


def test_bootstrap_runs_as_names_the_platform_python(setup_run):
    """`PYTHON_CMD` is the platform's own word for a message a person
    retypes - `python3` on POSIX, `python` on Windows (`os.name == "nt"`) -
    exactly like `scripts/repo_shape.py`'s `PYTHON` constant, never a
    basename derived from `sys.executable`."""
    out = setup_run["result"].stdout
    expected = "python" if os.name == "nt" else "python3"
    assert ("bootstrap runs as `%s scripts/bootstrap.py`" % expected) in out


def test_the_naming_policy_runs_before_anything_is_created(setup_run):
    out = setup_run["result"].stdout
    assert out.index("(4) naming policy") < out.index("(6) scaffold")
    # `--explain` form: the winner, then every family the name satisfies.
    assert "Sample: project-leg / assembly" in out
    assert "Sample-spec: project-leg / spec" in out
    assert "Sample-code: project-leg / code" in out


def test_the_entry_point_never_names_python3():
    """It runs `sys.executable` for every child process, never a probe for
    one on PATH.

    `PYTHON_CMD` is the one deliberate exception, and is exempted below by
    the line it is assigned on: exactly like `scripts/repo_shape.py`'s
    `PYTHON` constant, it spells the platform's own word - `python3` on
    POSIX, `python` on Windows - for a MESSAGE a person retypes, never for an
    argv (`PYTHON`, i.e. `sys.executable`, still runs every child process
    regardless of platform). Anywhere else, `python3` is the one defect this
    file cannot have: it is what `setup.sh` does and what makes `setup.sh`
    unrunnable on Windows. The module docstring is exempt too, because it is
    the paragraph EXPLAINING that, and prose in a comment cannot be executed.
    """
    source = SETUP_PROJECT.read_text(encoding="utf-8")
    exempt_lines = {i for i, line in enumerate(source.splitlines(), 1)
                    if line.startswith("PYTHON_CMD = ")}
    tree = ast.parse(source)
    docstring = ast.get_docstring(tree, clean=False)
    named = [node.value for node in ast.walk(tree)
             if isinstance(node, ast.Constant) and isinstance(node.value, str)
             and node.value is not docstring and "python3" in node.value
             and node.lineno not in exempt_lines]
    assert not named, f"these strings name python3: {named}"
    assert 'which("python3")' not in source
    assert source.splitlines()[0] == "#!/usr/bin/env python3", (
        "the shebang is the ONE place the name belongs: it is read by a "
        "POSIX kernel, which is a machine that has one")


# --- the refusals ----------------------------------------------------------

def test_help_exits_zero():
    result = run_entry("--help")
    assert result.returncode == 0
    assert "usage: setup-project.py" in result.stdout


def test_an_unknown_argument_refuses():
    result = run_entry("--project", "Sample", "--wat")
    assert result.returncode == 2
    assert "unknown argument: --wat" in result.stderr


def test_a_bad_visibility_refuses():
    result = run_entry("--project", "Sample", "--visibility", "secret")
    assert result.returncode == 2
    assert "must be 'private', 'public' or 'internal'" in result.stderr


def test_an_internal_visibility_is_accepted(tmp_path):
    """`internal` is a real GitHub visibility (an enterprise org-internal
    repository, `gh repo view --json visibility` -> `INTERNAL`), not a typo."""
    result = run_entry("--project", "Sample", "--yes", "--org", "demoorg",
                       "--visibility", "internal",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "visibility   internal" in result.stdout
    manifest = (tmp_path / "work" / "Sample" / "project.yaml").read_text()
    assert 'visibility: "internal"' in manifest


def test_a_name_outside_the_naming_policy_stops_before_the_scaffold(tmp_path):
    result = run_entry("--project", "Sample_One", "--yes", "--org", "demoorg",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"))
    assert result.returncode == 1
    assert "naming-unclassified" in result.stderr
    assert "(6) scaffold" not in result.stdout
    assert not (tmp_path / "remotes").exists()


def test_scaffolding_into_the_upstream_org_refuses(tmp_path):
    """`--org opensoft` is almost never what anyone means: opensoft is the
    UPSTREAM owner of openRepoShape itself, not a place to scaffold three
    fresh repositories into."""
    result = run_entry("--project", "Sample", "--yes", "--org", "opensoft",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "which is the UPSTREAM" in result.stderr
    assert "--allow-upstream-org" in result.stderr
    assert not (tmp_path / "remotes").exists()


def test_allow_upstream_org_lets_it_through(tmp_path):
    result = run_entry("--project", "Sample", "--yes", "--org", "opensoft",
                       "--allow-upstream-org",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"))
    assert result.returncode == 0, result.stderr
    manifest = (tmp_path / "work" / "Sample" / "project.yaml").read_text()
    assert "repository: opensoft/Sample" in manifest


def test_org_is_detected_from_the_origin_remote_ssh_url(tmp_path):
    """`origin` is read directly and parsed by hand, never `gh repo view` with
    no argument: a fork clone carries an `upstream` pointing at opensoft, and
    `gh` can prefer it and report `opensoft` for a perfectly correct fork."""
    fork = make_fork_dir(tmp_path,
                         origin_url="git@github.com:ExampleOrg/openRepoShape.git",
                         upstream_url="git@github.com:opensoft/openRepoShape.git")
    result = run_entry("--project", "Sample", "--yes",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"), cwd=fork)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "which is the UPSTREAM" not in result.stderr
    assert "organisation ExampleOrg" in result.stdout
    assert "upstream is opensoft; scaffolding into ExampleOrg" in result.stdout
    manifest = (tmp_path / "work" / "Sample" / "project.yaml").read_text()
    assert "repository: ExampleOrg/Sample" in manifest
    assert "repository: ExampleOrg/Sample-spec" in manifest
    assert "repository: ExampleOrg/Sample-code" in manifest


def test_org_is_detected_from_the_origin_remote_https_url(tmp_path):
    """Same defect, HTTPS remotes instead of SSH."""
    fork = make_fork_dir(tmp_path,
                         origin_url="https://github.com/ExampleOrg/openRepoShape.git",
                         upstream_url="https://github.com/opensoft/openRepoShape.git")
    result = run_entry("--project", "Sample", "--yes",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"), cwd=fork)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "which is the UPSTREAM" not in result.stderr
    assert "organisation ExampleOrg" in result.stdout
    assert "upstream is opensoft; scaffolding into ExampleOrg" in result.stdout
    manifest = (tmp_path / "work" / "Sample" / "project.yaml").read_text()
    assert "repository: ExampleOrg/Sample" in manifest
    assert "repository: ExampleOrg/Sample-spec" in manifest
    assert "repository: ExampleOrg/Sample-code" in manifest


def test_no_confirmation_and_no_terminal_refuses_after_showing_the_plan(tmp_path):
    result = run_entry("--project", "Sample", "--org", "demoorg",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "--dry-run: nothing was created." in result.stdout
    assert_refuses_for_want_of_a_terminal(result.stderr)
    assert not (tmp_path / "remotes").exists()


def test_agents_md_quotes_the_line_the_refusal_prints(tmp_path):
    """#476: AGENTS.md tells an assistant that a run with no terminal stops
    after the plan with a quoted line, and the line is the one the tool
    prints, so a reworded refusal that left the document behind fails here.
    The same paragraph is what the assistant is sent to by the first rule."""
    agents = " ".join((REPO / "AGENTS.md").read_text(encoding="utf-8").split())
    [quoted] = re.findall(r"`(no terminal[^`]*)`", agents)
    result = run_entry("--project", "Sample", "--org", "demoorg",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"))
    assert result.returncode == 2
    assert quoted in result.stderr
    assert "you never answer it for them. No terminal: section 2." in agents


def test_no_project_and_no_terminal_refuses(tmp_path):
    # `--local-remote-dir` is what keeps this offline. Without it the run
    # reaches the real `gh auth status` preflight and refuses for THAT reason
    # instead - which is how the setup.sh twin of this test passed on an
    # authenticated laptop and failed in CI.
    result = run_entry("--org", "demoorg",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "no --project given" in result.stderr
    assert not (tmp_path / "remotes").exists()


def test_passthrough_reaches_the_scaffold(tmp_path):
    result = run_entry("--project", "Sample", "--yes", "--org", "demoorg",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"),
                       "--", "--reference", "a-staged-fragment.md")
    assert result.returncode == 0, result.stderr
    manifest = (tmp_path / "work" / "Sample" / "project.yaml").read_text()
    assert 'reference: "a-staged-fragment.md"' in manifest


def test_a_rehearsals_clone_stops_the_real_run_before_anything(tmp_path):
    """#498, on an interpreter alone: `conftest.assert_a_rehearsals_clone_
    stops_the_real_run`."""
    assert_a_rehearsals_clone_stops_the_real_run(run_entry, tmp_path)


@pytest.mark.parametrize("kind", TAKEN_CLONE_PATHS)
def test_a_taken_clone_path_is_refused_before_anything(tmp_path, kind):
    """#498, on an interpreter alone: `conftest.assert_a_taken_clone_path_
    is_refused`."""
    assert_a_taken_clone_path_is_refused(run_entry, tmp_path, kind)


def test_the_plan_refuses_a_remote_that_exists_before_the_yes(tmp_path):
    """#537, on an interpreter alone: `conftest.assert_the_plan_refuses_a_
    remote_that_exists`."""
    assert_the_plan_refuses_a_remote_that_exists(run_entry, tmp_path)


#: What the scaffold's plan starts with, and a few of the lines after it.
A_PRINTED_PLAN = ("project      Sample (sample)   topic xf-project-sample\n"
                  "triad        the Triad\n"
                  "topics       skipped for local remotes\n")


def a_refused_plan(monkeypatch, tmp_path, code, asked, again=None):
    """`plan_and_confirm` with the scaffold's plan exiting `code`, and `asked`
    the stdout a second, captured run of that same plan gives, which exits
    `again` (`code`, unless it is given: the two runs need not agree): the
    refusal it raises and every call it made, as `(argv, cwd, capture)`."""
    module = entry_point_module()
    calls = []

    def run(argv, cwd=None, capture=False):
        calls.append((list(argv), cwd, capture))
        exits = again if again is not None and len(calls) > 1 else code
        return subprocess.CompletedProcess(argv, exits,
                                           asked if capture else None, None)

    monkeypatch.setattr(module, "run", run)
    opts = module.parse_args(["--project", "Sample", "--org", "demoorg"],
                             str(tmp_path))
    with pytest.raises(module.Refusal) as refused:
        module.plan_and_confirm(opts, REPO, "demoorg", [],
                                str(tmp_path / "Sample"))
    return refused.value, calls


def test_a_plan_that_printed_and_was_refused_is_said_to_be_refused(
        monkeypatch, tmp_path):
    """#608, L2-37: after #573 the scaffold's `--dry-run` prints the plan and
    then refuses an existing remote, so "the plan could not be produced"
    pointed at a plan that was right above it. Setup's own run inherits the
    terminal, so it asks the question the scaffold asked once more, captured,
    to learn whether the plan was there."""
    refusal, calls = a_refused_plan(monkeypatch, tmp_path, 2, A_PRINTED_PLAN)
    assert str(refusal) == "the plan was refused (see above)."
    assert refusal.code == 2
    [(first, first_cwd, first_captured),
     (again, again_cwd, again_captured)] = calls
    assert first_captured is False
    assert again_captured is True
    assert again == first
    assert first[-1] == "--dry-run", calls
    # Both are asked from the shape checkout: a relative `--pin-source` or
    # `--work-dir` means what it means to the first run.
    assert first_cwd == REPO
    assert again_cwd == REPO


@pytest.mark.parametrize("shown", [
    "", "NOTE demoorg/Sample is already private.\n",
    "  [ok] project      Sample (sample)\n", "a project      Sample\n",
    "projects of the family were read\n"])
def test_a_plan_that_never_printed_could_not_be_produced(monkeypatch, tmp_path,
                                                         shown):
    """#608, L2-37: the old words stay for a plan that was not printed. The
    plan's own first line, at the start of a line, is what says it was; a
    line that only holds those words, one that starts with the word and not
    its column of spaces, or a NOTE the scaffold prints before the plan, is
    not."""
    refusal, calls = a_refused_plan(monkeypatch, tmp_path, 2, shown)
    assert str(refusal) == "the plan could not be produced (see above)."
    assert refusal.code == 2
    assert len(calls) == 2, calls


def test_a_plan_whose_scaffold_was_killed_is_not_asked_again(monkeypatch,
                                                             tmp_path):
    """A child killed by a signal (`-2`, Ctrl-C) is not refusing anything:
    setup says what it said, with the exit status a shell reports (130), and
    does not start the scaffold again to ask."""
    refusal, calls = a_refused_plan(monkeypatch, tmp_path, -2, A_PRINTED_PLAN)
    assert str(refusal) == "the plan could not be produced (see above)."
    assert refusal.code == 130
    assert len(calls) == 1, calls


#: What step (5) says when the plan stopped the first time and did not the
#: second: it names neither a plan above nor a refusal, because it cannot know
#: what the first run printed, and it says what to do.
PLAN_STOPPED_ONCE = ("the scaffold stopped at the plan (see above). Asked a "
                     "second time it did not stop, so the refusal did not "
                     "happen again: run setup again.")


@pytest.mark.parametrize("asked", [A_PRINTED_PLAN, ""])
def test_a_plan_refused_once_and_not_again_says_to_run_setup_again(
        monkeypatch, tmp_path, asked):
    """#608, rv608 on #623: the words follow the second run, which the person
    never sees, so they are only as good as its agreeing with the first. A
    passing gh or network failure before the plan, or a remote made between
    the two runs, makes the first run refuse and the second print the plan and
    exit 0; "the plan was refused (see above)" then pointed at a plan that was
    not there. A second run that exits 0 refused nothing, whatever it
    printed, so the person is told it did not happen again and to run setup
    again. The exit code stays the first run's: that is the refusal."""
    refusal, calls = a_refused_plan(monkeypatch, tmp_path, 2, asked, again=0)
    assert str(refusal) == PLAN_STOPPED_ONCE
    assert refusal.code == 2
    assert len(calls) == 2, calls


def test_a_plan_refused_twice_is_not_told_to_run_again(monkeypatch, tmp_path):
    """The counterpart: a second run that refuses too, with the plan or
    without it, keeps the two wordings it had, so the new sentence is for a
    refusal that did not repeat and no other."""
    printed, _ = a_refused_plan(monkeypatch, tmp_path, 2, A_PRINTED_PLAN,
                                again=1)
    assert str(printed) == "the plan was refused (see above)."
    never, _ = a_refused_plan(monkeypatch, tmp_path, 2, "", again=1)
    assert str(never) == "the plan could not be produced (see above)."


def test_a_plan_that_was_produced_is_run_once(monkeypatch, tmp_path):
    """The second run is the refusal's alone: a plan that exits 0 is run once,
    and its output is the terminal's, not captured."""
    module = entry_point_module()
    calls = []

    def run(argv, cwd=None, capture=False):
        calls.append(capture)
        return subprocess.CompletedProcess(argv, 0, None, None)

    monkeypatch.setattr(module, "run", run)
    opts = module.parse_args(["--project", "Sample", "--org", "demoorg",
                              "--yes"], str(tmp_path))
    assert module.plan_and_confirm(opts, REPO, "demoorg", [],
                                   str(tmp_path / "Sample")) is True
    assert calls == [False]


def test_anything_but_yes_refuses_and_creates_nothing(monkeypatch, tmp_path):
    """The one `yes` is EXACT: `no`, `y`, `Yes` and an empty line all refuse.

    Driven in-process rather than through `run_entry` because the prompt only
    happens where there is a terminal to ask on, and there is no portable way
    to hand a subprocess one - `pty` is POSIX-only and this suite runs on
    Windows, which is the platform this entry point is for. What is asserted
    is the ruling itself: anything but exactly `yes` is exit 1 and nothing was
    created. The POSIX terminal itself is driven at the end of this file.
    """
    module = entry_point_module()

    class _Terminal:
        def isatty(self):
            return True

    monkeypatch.setattr(sys, "stdin", _Terminal())
    monkeypatch.setattr(module, "run", lambda *a, **k: subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr=""))
    opts = module.parse_args(["--project", "Sample", "--org", "demoorg"],
                             str(tmp_path))
    clone = str(tmp_path / "Sample")
    for answer in ("no", "y", "Yes", ""):
        monkeypatch.setattr(module, "ask", lambda prompt, a=answer: a)
        with pytest.raises(module.Refusal) as refused:
            module.plan_and_confirm(opts, REPO, "demoorg", [], clone)
        assert refused.value.code == 1, answer
        assert "not confirmed; nothing was created." in str(refused.value)
    monkeypatch.setattr(module, "ask", lambda prompt: "yes")
    module.plan_and_confirm(opts, REPO, "demoorg", [], clone)


def test_no_test_here_depends_on_gh_being_authenticated():
    """Every invocation either stops before the preflight or runs offline.

    The ones that stop early are argument-parsing refusals - `--help`, an
    unknown flag, an empty argument, a flag with no value, a bad
    `--visibility`, two project names - which the entry point answers before
    it looks at the machine. Everything else must pass `--local-remote-dir`,
    or it reaches `gh auth status` and passes only on a laptop that happens to
    be logged in.

    `run_piped` as well as `run_entry`: it starts the same entry point with
    the same arguments and reaches the same preflight, so a piped run added
    without `--local-remote-dir` fails in CI for exactly the reason this test
    exists to prevent.
    """
    source = Path(__file__).read_text(encoding="utf-8")
    early = ("--help", "--wat", '"secret"', '"Other"', '"Novalue"', '"Empty"')
    for match in re.finditer(r"(?<!def )run_(entry|piped)\(", source):
        start = match.end()
        depth, index = 1, start
        while depth:
            if source[index] == "(":
                depth += 1
            elif source[index] == ")":
                depth -= 1
            index += 1
        call = source[start:index - 1]
        if any(marker in call for marker in early):
            continue
        assert "--local-remote-dir" in call, (
            "this run_entry call reaches the gh preflight and will fail "
            f"wherever gh is not authenticated:\n    {' '.join(call.split())}")


# --- the positional --------------------------------------------------------

def test_a_positional_project_is_folded_into_project(tmp_path):
    """`py setup-project.py Atlas --org <org>` is the README's Windows line,
    and it is the `openRepoShape` command's shape folded into the file itself
    - there is no command to install on the platform this is for."""
    result = run_entry("Sample", "--yes", "--org", "demoorg",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "project      Sample" in result.stdout
    assert (tmp_path / "work" / "Sample" / "project.yaml").is_file()


def test_two_positionals_refuse():
    result = run_entry("Sample", "Other")
    assert result.returncode == 2
    assert "two project names, 'Sample' and 'Other'" in result.stderr
    assert "One positional <Project>, then flags." in result.stderr


def test_a_positional_and_a_project_flag_refuse_in_either_order():
    """Two names for one thing is two names whichever arrives first.

    `--project Other Sample` is the case above with the arguments swapped and
    was always refused; `Sample --project Other` reached the same end by
    silently taking the second one, and the person who typed both got a
    project they did not name. The refusal is the same sentence, and it names
    them in the order they were typed.
    """
    result = run_entry("Sample", "--project", "Other")
    assert result.returncode == 2
    assert "two project names, 'Sample' and 'Other'" in result.stderr
    assert "One positional <Project>, then flags." in result.stderr


def test_an_empty_argument_refuses():
    """`""` is not a project name.

    `setup.sh`'s `case` falls through to `*)` on an empty argument and refuses
    `unknown argument: ` with nothing after the colon; taking it as the
    positional instead would leave this file scaffolding a project called ``,
    which is the one thing the two entry points must not disagree about.
    """
    result = run_entry("--project", "Empty", "")
    assert result.returncode == 2
    assert "unknown argument: " in result.stderr
    assert "usage: setup-project.py" in result.stderr


def test_a_flag_with_no_value_refuses():
    """A flag at the end of the line has no value, and 2 is the code.

    Pinned deliberately. This USED to be the one exit code the two entry
    points did not share: `setup.sh` spelled the same case
    `${2:?--visibility needs a value}`, and a bash parameter expansion that
    fails exits 1 where every other refusal in either file exits 2. #50
    settled it by deleting the second parser - `setup.sh` execs this file, so
    this line is the only one that answers, under either name.
    """
    result = run_entry("--project", "Novalue", "--visibility")
    assert result.returncode == 2
    assert "--visibility needs a value" in result.stderr


# --- what may become an argument to git -------------------------------------
#
# ARGUMENT injection, not shell injection: every command this entry point runs
# is a list with `shell=False`, so there is no shell - but git reads its own
# arguments, and a value that starts with `-` is an option to git rather than
# a name. `scaffold-project.py` refuses the same values
# (`tests/test_scaffold_pin_and_reuse.py`), through `repo_shape.checked_value`,
# each in a sentence of its own: this file's subject names the check a value
# failed (`tests/test_setup_project_name_edges.py`). It carries its own copy
# because it runs BEFORE there is a checkout to import that from, which is the
# whole of self-bootstrap mode.
#
# Every run here passes `--local-remote-dir` even though none of them reaches
# it: the refusal is a parse-time one, and the flag is what keeps
# `test_no_test_here_depends_on_gh_being_authenticated` true if it ever stops
# being.

def test_an_org_that_is_a_git_option_is_refused(tmp_path):
    result = run_entry("--project", "Sample", "--org", "-evil",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "--org is '-evil'" in result.stderr
    assert "git reads its own arguments" in result.stderr
    assert not (tmp_path / "remotes").exists()


@pytest.mark.parametrize("ref", ["a b", "a..b", "topic.lock", "-x",
                                 pytest.param("a" * 256, id="256-chars")])
def test_a_shape_ref_that_is_not_a_ref_is_refused(tmp_path, ref):
    """`--shape-ref` becomes `git checkout <ref>` in the temporary checkout.

    A space is not in any ref name; `..` is a revision RANGE rather than a
    ref; `.lock` is what git calls the lock file it writes beside one; a
    leading `-` is an option to git; and 256 characters is one past `REF_RE`'s
    own bound of 255 - the same bound `setup.sh`'s shim mirrors with a
    dedicated length check of its own, since a bash `case` cannot count
    (openRepoShape #63).
    """
    result = run_entry("--project", "Sample", "--shape-ref", ref,
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"))
    assert result.returncode == 2
    assert f"--shape-ref is '{ref}'" in result.stderr
    assert not (tmp_path / "remotes").exists()


def test_a_value_carrying_a_newline_is_refused(tmp_path):
    """A newline ends a line in every terminal, prompt and log this output
    reaches, so a value carrying one could print a `REFUSED:` line nobody
    refused. It is refused, and quoted back ESCAPED - `ascii()`, not `%r`,
    which is also what keeps this file's output pure ASCII.
    """
    result = run_entry("--project", "Sample", "--name", "Atlas\nREFUSED: nope",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "--name is 'Atlas\\nREFUSED: nope'" in result.stderr
    assert "\nREFUSED: nope" not in result.stderr, (
        "the newline reached the terminal and printed a line nobody wrote")


def test_the_ordinary_values_still_parse(tmp_path):
    """The check must not become the naming policy.

    `Display Name` with a space, a CamelCase project, a kebab-case id and a
    person's name are all legitimate here; which of them this standard accepts
    is `scripts/validate-repository-naming.py --explain`'s ruling at step (4),
    and it is not re-implemented at parse time.
    """
    module = entry_point_module()
    opts = module.parse_args(["Atlas", "--org", "ExampleOrg",
                              "--id", "atlas-one", "--name", "Atlas Display",
                              "--elected-by", "Brett Heap",
                              "--shape-ref", "refs/tags/v1.0"], str(tmp_path))
    assert opts.project == "Atlas"
    assert opts.org == "ExampleOrg"
    assert opts.project_id == "atlas-one"
    assert opts.display_name == "Atlas Display"
    assert opts.elected_by == "Brett Heap"
    assert opts.shape_ref == "refs/tags/v1.0"


def test_a_version_line_shorter_than_the_field_is_not_an_index_error():
    """`git --version` is `git version 2.43.0` and the field wanted is the
    third. A program that answers with fewer words - or with nothing, which is
    what `run` returns for a program that is not installed at all - is a
    program, not an IndexError out of the preflight.
    """
    module = entry_point_module()
    assert module.program_version([sys.executable, "-c", "print('a b c')"],
                                  2) == "c"
    assert module.program_version([sys.executable, "-c", "print('one')"],
                                  2) == "(unknown version)"
    assert module.program_version([sys.executable, "-c", "pass"],
                                  2) == "(unknown version)"
    assert module.program_version(["openreposhape-no-such-program"],
                                  2) == "(unknown version)"


# --- piped on stdin ---------------------------------------------------------

def run_piped(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    """The file's own text on stdin, which is what `Get-Content ... | py -`
    does - and what the README's Windows path deliberately does NOT do. No
    controlling terminal either, as `run_entry` (#492)."""
    env = dict(os.environ)
    env.setdefault("GIT_AUTHOR_NAME", "openRepoShape tests")
    env.setdefault("GIT_AUTHOR_EMAIL", "tests@openreposhape.invalid")
    env.setdefault("GIT_COMMITTER_NAME", "openRepoShape tests")
    env.setdefault("GIT_COMMITTER_EMAIL", "tests@openreposhape.invalid")
    return subprocess.run(
        [sys.executable, "-", *args], capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False, env=env,
        input=SETUP_PROJECT.read_text(encoding="utf-8"), cwd=str(cwd),
        start_new_session=True)


def test_a_piped_script_scaffolds_when_told_yes(tmp_path):
    """With no file on disk there is no `__file__`, so the checkout is found
    by asking git about the directory the run started in - here, this one."""
    result = run_piped("--project", "Sample", "--yes", "--org", "demoorg",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"), cwd=REPO)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (tmp_path / "work" / "Sample" / "project.yaml").is_file()


def test_a_piped_script_without_yes_refuses(tmp_path):
    """A script that ARRIVED on stdin has an exhausted stdin, so there is no
    terminal left to ask on and three repositories are never created without
    an answer. This is why the README's Windows path downloads the file first
    and then runs it."""
    result = run_piped("--project", "Sample", "--org", "demoorg",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"), cwd=REPO)
    assert result.returncode == 2
    assert_refuses_for_want_of_a_terminal(result.stderr)
    assert not (tmp_path / "remotes").exists()


# --- self-bootstrap ---------------------------------------------------------
#
# A downloaded `setup-project.py` has no checkout on disk at all. These tests
# reproduce that shape: a lone COPY in a directory with no `.git` and no
# `scaffold-project.py`, run with $OPENREPOSHAPE_REPO pointed at THIS checkout
# so the clone it does is local and offline.

def test_self_bootstrap_scaffolds_from_a_temporary_checkout(tmp_path):
    outside = make_outside_checkout(tmp_path)
    base = tmp_path / "run"
    result = run_entry("--org", "demoorg", "--project", "Sample", "--yes",
                       "--local-remote-dir", str(base / "remotes"),
                       "--into", str(base / "work"),
                       cwd=outside, script=outside / "setup-project.py",
                       extra_env={"OPENREPOSHAPE_REPO": str(REPO)})
    assert result.returncode == 0, result.stderr + result.stdout
    assert "(0) self-bootstrap" in result.stdout
    assert DEGRADE_LINE in result.stdout
    clone = base / "work" / "Sample"
    assert clone.is_dir()
    assert (clone / "project.yaml").is_file()

    match = re.search(r"checkout: (.+)", result.stdout)
    assert match, f"the shape checkout path was never printed:\n{result.stdout}"
    # It is a git object store, and git writes its objects read-only. That the
    # directory is GONE is what proves the removal handles that on Windows.
    assert not Path(match.group(1).rstrip()).exists(), (
        "the temporary shape checkout should have been removed on exit")


def test_self_bootstrap_keeps_the_checkout_when_asked(tmp_path):
    outside = make_outside_checkout(tmp_path)
    base = tmp_path / "run"
    result = run_entry("--org", "demoorg", "--project", "Sample", "--yes",
                       "--keep-shape-checkout",
                       "--local-remote-dir", str(base / "remotes"),
                       "--into", str(base / "work"),
                       cwd=outside, script=outside / "setup-project.py",
                       extra_env={"OPENREPOSHAPE_REPO": str(REPO)})
    assert result.returncode == 0, result.stderr + result.stdout
    assert "kept the shape checkout:" in result.stdout

    match = re.search(r"checkout: (.+)", result.stdout)
    assert match, f"the shape checkout path was never printed:\n{result.stdout}"
    # `(.+)` and `.rstrip()`, not `(\S+)`: a temporary directory can sit
    # under a path with a space in it - `C:\Users\Some One\AppData\...` is
    # an ordinary Windows profile - and `\S+` would silently keep the first
    # word of it and assert about a directory that never existed.
    kept = Path(match.group(1).rstrip())
    try:
        assert kept.is_dir(), "--keep-shape-checkout should have kept the clone"
        assert (kept / "scaffold-project.py").is_file()
    finally:
        rmtree(kept)


def test_self_bootstrap_clones_into_the_directory_it_was_run_from(tmp_path):
    """#39: the re-run happens from a temporary checkout, so the child's own
    default parent was `..` of THAT - the system temp directory - and the new
    project was cloned there, then left behind when the temporary checkout
    beside it was deleted. It belongs where the person was standing, and no
    `--into` is passed here: the default is the whole point.
    """
    outside = make_outside_checkout(tmp_path)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    result = run_entry("--org", "demoorg", "--project", "Sample", "--yes",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       cwd=cwd, script=outside / "setup-project.py",
                       extra_env={"OPENREPOSHAPE_REPO": str(REPO)})
    assert result.returncode == 0, result.stderr + result.stdout
    clone = cwd / "Sample"
    assert clone.is_dir(), (
        f"Sample was not cloned into {cwd}, the directory the run started "
        f"in:\n{result.stdout}")
    assert (clone / "project.yaml").is_file()
    assert f"clone       {os.path.abspath(str(clone))}" in result.stdout

    match = re.search(r"checkout: (.+)", result.stdout)
    assert match, f"the shape checkout path was never printed:\n{result.stdout}"
    assert not (Path(match.group(1).rstrip()).parent / "Sample").exists(), (
        "the clone landed beside the TEMPORARY checkout, which is the defect "
        "#39 is about")


def test_a_symlinked_entry_point_self_bootstraps(tmp_path):
    """`os.path.abspath`, never `Path.resolve()` - the symlink case.

    Putting `setup-project.py` on your PATH means a symlink pointing into a
    checkout of this standard. `resolve()` follows it, so the file's directory
    becomes that checkout, the run takes the DEVELOPER path, and the
    `--into <invocation dir>` that self-bootstrap passes is never passed at
    all: the new project lands beside the checkout the symlink points at
    instead of where the person was standing. That is #39, resurrected by a
    symlink. `abspath` keeps the link's own directory, and a directory holding
    one symlink is not a checkout of anything.
    """
    link_dir = tmp_path / "bin"
    link_dir.mkdir()
    link = link_dir / "setup-project.py"
    try:
        os.symlink(SETUP_PROJECT, link)
    except (AttributeError, NotImplementedError, OSError) as exc:
        # Windows needs Developer Mode or an elevated shell to make one, and a
        # runner without either is not a reason to fail: the defect this
        # guards is a POSIX habit, and the POSIX legs of CI do run it.
        pytest.skip(f"this platform cannot create a symlink here: {exc}")

    cwd = tmp_path / "cwd"
    cwd.mkdir()
    result = run_entry("--project", "Sym", "--org", "demoorg", "--yes",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       cwd=cwd, script=link,
                       extra_env={"OPENREPOSHAPE_REPO": str(REPO)})
    assert result.returncode == 0, result.stderr + result.stdout
    assert "(0) self-bootstrap" in result.stdout, (
        "the symlink was followed into a checkout and the developer path "
        f"taken:\n{result.stdout}")
    clone = cwd / "Sym"
    assert clone.is_dir(), (
        f"Sym was not cloned into {cwd}, the directory the run started in:"
        f"\n{result.stdout}")
    assert (clone / "project.yaml").is_file()
    assert f"clone       {os.path.abspath(str(clone))}" in result.stdout


def test_into_still_wins_in_self_bootstrap_mode(tmp_path):
    """The invocation directory is passed as `--into` BEFORE the person's own
    arguments, so an explicit `--into` of theirs is parsed after it and wins."""
    outside = make_outside_checkout(tmp_path)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    result = run_entry("--org", "demoorg", "--project", "Sample", "--yes",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"),
                       cwd=cwd, script=outside / "setup-project.py",
                       extra_env={"OPENREPOSHAPE_REPO": str(REPO)})
    assert result.returncode == 0, result.stderr + result.stdout
    assert (tmp_path / "work" / "Sample" / "project.yaml").is_file()
    assert not (cwd / "Sample").exists(), "--into was overridden, not honoured"


def test_running_from_the_upstream_checkout_without_org_refuses(tmp_path):
    """`origin` pointing at opensoft/openRepoShape itself means this checkout
    IS the upstream: there is no fork to inherit an organisation from, so the
    ask is the same as self-bootstrap's - pass --org."""
    checkout = tmp_path / "upstream-checkout"
    checkout.mkdir()
    git("init", "-q", cwd=checkout)
    git("remote", "add", "origin",
        "git@github.com:opensoft/openRepoShape.git", cwd=checkout)
    result = run_entry("--project", "Sample", "--yes",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"), cwd=checkout)
    assert result.returncode == 2
    assert "upstream checkout" in result.stderr
    assert "--org" in result.stderr
    assert not (tmp_path / "remotes").exists()


def test_self_bootstrap_without_org_refuses(tmp_path):
    """There is no fork `origin` to read an organisation from outside a
    checkout, so `--org` cannot be optional the way it is from inside one."""
    outside = make_outside_checkout(tmp_path)
    result = run_entry("--project", "Sample", "--yes",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"),
                       cwd=outside, script=outside / "setup-project.py")
    assert result.returncode == 2
    assert "--org" in result.stderr
    assert not (tmp_path / "remotes").exists()


def test_the_shim_handshake_requires_an_org(tmp_path):
    """#50: `setup.sh` clones a checkout and hands over, so the refusal above
    has to survive the hand-over.

    From inside a checkout `--org` is optional because `origin` is the
    person's fork and the organisation is read off it. The checkout
    `setup.sh` makes in its section 0 is a real one, but its `origin` is
    opensoft's own and the person's fork is nowhere in it - so a run arriving
    here under `OPENREPOSHAPE_SELF_BOOTSTRAP=1` is the self-bootstrap case
    wearing the developer path's clothes, and it is refused in the
    self-bootstrap case's own words. Without this, `curl ... | bash` started
    inside an unrelated repository would scaffold into THAT repository's
    organisation.
    """
    fork = make_fork_dir(tmp_path,
                         origin_url="git@github.com:ExampleOrg/openRepoShape.git",
                         upstream_url="git@github.com:opensoft/openRepoShape.git")
    result = run_entry("--project", "Sample", "--yes",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"), cwd=fork,
                       extra_env={"OPENREPOSHAPE_SELF_BOOTSTRAP": "1"})
    assert result.returncode == 2
    assert "self-bootstrap" in result.stderr, (
        "the refusal must be the self-bootstrap one, in its own words - "
        f"not whatever else this checkout's `origin` happens to say:\n"
        f"{result.stderr}")
    assert "--org" in result.stderr
    assert not (tmp_path / "remotes").exists()


def test_a_hostile_openreposhape_repo_refuses(tmp_path):
    """`OPENREPOSHAPE_REPO` reaches `git clone` as the repository argument,
    which is exactly the argument git itself will never refuse for us: a
    leading `-` there is an OPTION to git, not a name. `-c core.x=y` is the
    shape of a value that would turn the clone into a config injection, and
    it is refused before `git` ever sees it - by the same `checked_value`
    rule as every flag on the command line - naming the environment
    variable so the person fixing this knows what to change."""
    outside = make_outside_checkout(tmp_path)
    result = run_entry("--org", "demoorg", "--project", "Sample", "--yes",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       cwd=outside, script=outside / "setup-project.py",
                       extra_env={"OPENREPOSHAPE_REPO": "-c core.x=y"})
    assert result.returncode == 2
    assert "OPENREPOSHAPE_REPO" in result.stderr
    assert not (tmp_path / "remotes").exists()


def test_self_bootstrap_clone_guards_the_repository_argument(tmp_path):
    """Defense in depth for the same value: even a repository that passed
    the `checked_value` guard is clone'd after a `--`, so git never reads it
    as an option regardless of what reaches this line."""
    outside = make_outside_checkout(tmp_path)
    base = tmp_path / "run"
    result = run_entry("--org", "demoorg", "--project", "Sample", "--yes",
                       "--local-remote-dir", str(base / "remotes"),
                       "--into", str(base / "work"),
                       cwd=outside, script=outside / "setup-project.py",
                       extra_env={"OPENREPOSHAPE_REPO": str(REPO)})
    assert result.returncode == 0, result.stderr + result.stdout
    match = re.search(r"^  git clone .*$", result.stdout, re.MULTILINE)
    assert match, f"the clone command was never echoed:\n{result.stdout}"
    assert " -- %s " % str(REPO) in match.group(0), (
        f"the clone command has no `--` before the repository: "
        f"{match.group(0)!r}")


def test_an_empty_openreposhape_repo_means_unset(tmp_path):
    """`self_bootstrap` reads `$OPENREPOSHAPE_REPO` with
    `checked_value(...) if raw_shape_repo else DEFAULT_SHAPE_REPO` - a
    truthiness test, so `OPENREPOSHAPE_REPO=` (set, explicitly EMPTY) never
    reaches `checked_value` at all and falls to the default exactly like an
    unset variable does. `setup.sh` reads the same variable as
    `${OPENREPOSHAPE_REPO:-<default>}`, the shell's own "unset or empty"
    reading, so the two entry points already agree - the ruling on
    openRepoShape #63, after a comment above that line (fixed alongside this
    test) was found still claiming `checked_value` refuses "an empty value"
    for this variable, which is never reached for one.

    Offline: git's `GIT_CONFIG_*` entries, appended to the ones the
    environment holds, hand this one process a
    `url.<file-uri-of-this-checkout>.insteadOf <default>` rewrite, so `git
    clone` resolves the DEFAULT repository to THIS checkout without a
    network - which is what makes the echoed clone line naming the default
    URL proof that the empty value fell through to it, rather than a network
    call that happened to succeed.
    """
    default_repo = "https://github.com/opensoft/openRepoShape.git"
    source_default = re.search(r'^DEFAULT_SHAPE_REPO = "([^"]+)"',
                               SETUP_PROJECT.read_text(encoding="utf-8"),
                               re.MULTILINE)
    assert source_default, "DEFAULT_SHAPE_REPO not found in setup-project.py"
    assert source_default.group(1) == default_repo, (
        "this test's literal has drifted from setup-project.py's own "
        "DEFAULT_SHAPE_REPO")

    outside = make_outside_checkout(tmp_path)
    base = tmp_path / "run"
    result = run_entry("--org", "demoorg", "--project", "Sample", "--yes",
                       "--local-remote-dir", str(base / "remotes"),
                       "--into", str(base / "work"),
                       cwd=outside, script=outside / "setup-project.py",
                       extra_env={
                           "OPENREPOSHAPE_REPO": "",
                           **appended_to_command_scope(os.environ, [
                               ("url.%s.insteadOf" % REPO.as_uri(),
                                default_repo)]),
                       })
    assert result.returncode == 0, result.stderr + result.stdout
    match = re.search(r"^  git clone .*$", result.stdout, re.MULTILINE)
    assert match, f"the clone command was never echoed:\n{result.stdout}"
    assert default_repo in match.group(0), (
        f"the clone did not name the default repository: {match.group(0)!r}")


# --- the preflight offers to install what is missing (#59) -----------------

#: NOTHING IN THIS SECTION EVER INSTALLS ANYTHING, on any platform, in CI or
#: on a laptop, and that is STRUCTURAL rather than a promise. An offer needs
#: a terminal to ask on (`can_ask`: stdin, or the controlling terminal, #492),
#: and no run in this suite has one: `run_entry` and
#: `test_openreposhape_command.run_cmd` pass a pipe in a session with no
#: controlling terminal, and `conftest.run_script` forces `stdin=DEVNULL`
#: (the doctor starts its preflight in a session of its own). The tests that
#: DO exercise an offer are in-process with a fake terminal and with
#: `module.run` replaced by a recorder that executes nothing at all - so
#: `brew`, `apt-get`, `dnf`, `winget`, `xcode-select` and `gh auth login` are
#: named here and run nowhere; the one that drives a real terminal answers a
#: stub `gh` (`tests/test_setup_sh.py`).


class _Terminal:
    """A stdin that says it is a terminal. It is asked nothing else."""

    def isatty(self):
        return True


class _NoTerminal:
    def isatty(self):
        return False


def _no_terminal(monkeypatch, module) -> None:
    """No terminal at all: stdin is not one, and there is no controlling
    terminal to open (#492) - which the pytest process may well have, and
    which is nobody's answer to a question a test asks."""
    monkeypatch.setattr(sys, "stdin", _NoTerminal())
    monkeypatch.setattr(module, "open_terminal", lambda: None)


class _Runs:
    """A stand-in for `module.run` that RECORDS an argv and executes none.

    `answers` maps a substring of the joined argv to `(returncode, stdout)`;
    anything unmatched gets `returncode` and no output, which is what the
    version probes and `gh auth status` want in the ordinary case.
    """

    def __init__(self, answers=None, returncode=0):
        self.calls = []
        self.answers = answers or {}
        self.returncode = returncode

    def __call__(self, argv, cwd=None, capture=False):
        self.calls.append(list(argv))
        line = " ".join(argv)
        for marker, (code, out) in self.answers.items():
            if marker in line:
                return subprocess.CompletedProcess(argv, code, out, "")
        return subprocess.CompletedProcess(argv, self.returncode, "", "")


def _which(*present):
    """A `shutil.which` that finds exactly these programs and nothing else."""
    found = set(present)
    return lambda name: ("/usr/bin/" + name) if name in found else None


#: Every package manager at once, for the tests that care about a MISSING
#: prerequisite rather than about which platform is running them: with all
#: four present there is an offer to make on macOS, Linux and Windows alike.
EVERY_MANAGER = ("brew", "apt-get", "dnf", "winget")


def _shell_argv(command_text: str) -> list:
    """The argv one offered command is run through on THIS platform."""
    return (["cmd", "/c", command_text] if os.name == "nt"
            else ["bash", "-c", command_text])


def _answers(monkeypatch, module, answer: str) -> list:
    """A terminal that types `answer` at every prompt, and the prompts it
    was shown."""
    prompts = []
    monkeypatch.setattr(sys, "stdin", _Terminal())
    monkeypatch.setattr(module, "ask",
                        lambda prompt: (prompts.append(prompt), answer)[1])
    return prompts


def test_the_offer_table_names_a_command_for_every_platform():
    """The table of #59, row for row, whatever platform this is running on.

    `offer_for` takes the platform and the `which` as ARGUMENTS, so the
    Windows rows are asserted on Linux and the macOS rows on Windows: the
    table is a fact about the tool, not about the runner, and there is
    nothing to monkeypatch to see it.
    """
    module = entry_point_module()
    every = _which(*EVERY_MANAGER)
    offer_for = module.offer_for

    assert offer_for("git", "darwin", _which()) == "xcode-select --install"
    assert offer_for("git", "linux", _which("apt-get")) == \
        "sudo apt-get install -y git"
    assert offer_for("git", "linux", _which("dnf")) == "sudo dnf install -y git"
    assert offer_for("git", "linux", _which()) is None
    assert offer_for("git", "win32", _which("winget")) == \
        "winget install --id Git.Git -e"
    assert offer_for("git", "win32", _which()) is None

    assert offer_for("gh", "darwin", _which("brew")) == "brew install gh"
    # HOMEBREW IS NEVER INSTALLED BY US: no brew, no offer, and the machine
    # owner's decision stays theirs.
    assert offer_for("gh", "darwin", _which()) is None
    assert offer_for("gh", "linux", _which("apt-get")) is module.GH_APT_BLOCK
    assert offer_for("gh", "linux", _which("dnf")) is module.GH_DNF_BLOCK
    assert offer_for("gh", "linux", _which()) is None
    assert offer_for("gh", "win32", _which("winget")) == \
        "winget install --id GitHub.cli -e"

    # First row wins: a machine with both is a Debian that installed dnf.
    assert offer_for("gh", "linux", every) is module.GH_APT_BLOCK

    # An unrecognised platform, and the three prerequisites with no row at
    # all - `make` is never used, and no install can replace the interpreter
    # that is already running.
    assert offer_for("git", "aix7", every) is None
    assert offer_for("gh", "sunos5", every) is None
    assert offer_for("make", "linux", every) is None
    assert offer_for("python", "darwin", every) is None

    for rows in module.INSTALL_OFFERS.values():
        for _, command in rows:
            assert command.strip()
            assert command.isascii()
            assert "brew.sh" not in command


def test_an_offer_runs_the_command_on_yes(monkeypatch):
    """The typed `yes` runs the platform's own command, through the
    platform's own shell, and re-checks EXACTLY once."""
    module = entry_point_module()
    prompts = _answers(monkeypatch, module, "yes")
    runs = _Runs()
    monkeypatch.setattr(module, "run", runs)
    probes = []
    installed = module.offer_install(
        "gh", "brew install gh", lambda: (probes.append(1), True)[1], "darwin")
    assert installed is True
    assert runs.calls == [_shell_argv("brew install gh")]
    assert len(probes) == 1, "the re-check happens once, never in a loop"
    assert prompts == ["  Run `brew install gh` now? Type yes to continue: "]


def test_a_block_of_commands_is_shown_before_it_is_offered(monkeypatch,
                                                           capsys):
    """GitHub's apt instructions are nine lines. Nine lines inside a one-line
    question is a question nobody can read before answering it."""
    module = entry_point_module()
    prompts = _answers(monkeypatch, module, "yes")
    runs = _Runs()
    monkeypatch.setattr(module, "run", runs)
    assert module.offer_install("gh", module.GH_APT_BLOCK, lambda: True,
                                "linux") is True
    shown = capsys.readouterr().out
    assert "sudo apt install gh -y" in shown
    assert prompts == ["  Run the commands above now? Type yes to continue: "]
    assert runs.calls == [_shell_argv(module.GH_APT_BLOCK)]


def test_a_refused_offer_is_todays_text_and_todays_exit(monkeypatch, capsys,
                                                        tmp_path):
    """`no` leaves the screen and the exit code exactly as they were before
    the offers existed: today's `[!!]` line, then one refusal, exit 2."""
    module = entry_point_module()
    monkeypatch.setattr(module.shutil, "which", _which("git", *EVERY_MANAGER))
    runs = _Runs()
    monkeypatch.setattr(module, "run", runs)
    asked = _answers(monkeypatch, module, "no")
    opts = module.parse_args([], str(tmp_path))
    with pytest.raises(module.Refusal) as refused:
        module.preflight(opts)
    assert refused.value.code == 2
    assert "one or more prerequisites are missing" in str(refused.value)
    assert ("gh is not installed. Install it: https://cli.github.com"
            in capsys.readouterr().err)
    assert asked, "the offer was never made"
    for call in runs.calls:
        assert call[:2] not in (["bash", "-c"], ["cmd", "/c"]), (
            "a refused offer ran a command: %r" % (call,))


def test_no_terminal_makes_no_offer(monkeypatch, capsys, tmp_path):
    """The only gate is `can_ask()`, so a run with no terminal at all -
    scheduled, or in an assistant's shell - is byte for byte what it was
    before any of this existed."""
    module = entry_point_module()
    _no_terminal(monkeypatch, module)
    monkeypatch.setattr(module.shutil, "which", _which("git", *EVERY_MANAGER))
    monkeypatch.setattr(module, "run", _Runs())

    def _never(prompt):
        raise AssertionError("asked with no terminal: %r" % prompt)

    monkeypatch.setattr(module, "ask", _never)
    opts = module.parse_args([], str(tmp_path))
    with pytest.raises(module.Refusal) as refused:
        module.preflight(opts)
    assert refused.value.code == 2
    assert "gh is not installed" in capsys.readouterr().err


def test_yes_does_not_answer_an_install_prompt(monkeypatch, capsys, tmp_path):
    """`--yes` skips ONE question - the one about creating three
    repositories. An install is a different question and is still asked."""
    module = entry_point_module()
    monkeypatch.setattr(module.shutil, "which", _which("git", *EVERY_MANAGER))
    monkeypatch.setattr(module, "run", _Runs())
    asked = _answers(monkeypatch, module, "no")
    opts = module.parse_args(["--yes"], str(tmp_path))
    assert opts.assume_yes is True
    with pytest.raises(module.Refusal):
        module.preflight(opts)
    capsys.readouterr()
    assert asked, "--yes answered an install prompt for the human"


def test_the_offer_helpers_cannot_see_the_yes_flag():
    """Structural, not careful: the offer helpers are never handed `Options`,
    so `assume_yes` is not in scope and cannot be consulted by a future edit
    however well meant."""
    source = SETUP_PROJECT.read_text(encoding="utf-8")
    helpers = {"offer", "offer_install", "offer_missing", "run_command_text"}
    seen = set()
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name in helpers:
            seen.add(node.name)
            body = ast.get_source_segment(source, node)
            assert "assume_yes" not in body, (
                f"{node.name} consults --yes; an install is not the question "
                "that flag answers")
            names = [argument.arg for argument in node.args.args]
            assert "opts" not in names, (
                f"{node.name} takes the parsed options; it must not be able "
                "to see --yes at all")
    assert seen == helpers, f"these helpers have been renamed: {helpers - seen}"


def test_an_install_that_fails_says_nothing_extra(monkeypatch, capsys):
    """The package manager (or sudo) has just printed its own account of the
    failure on this terminal; a vaguer sentence of ours would compete with
    it."""
    module = entry_point_module()
    _answers(monkeypatch, module, "yes")
    monkeypatch.setattr(module, "run", _Runs(returncode=1))
    probes = []
    assert module.offer_install("gh", "brew install gh",
                                lambda: (probes.append(1), True)[1],
                                "darwin") is False
    printed = capsys.readouterr()
    assert probes == [], "a command that failed is not re-checked"
    for invented in ("still not there", "new terminal", "installer is running"):
        assert invented not in printed.out + printed.err


def test_a_command_that_needs_a_new_terminal_says_so(monkeypatch, capsys):
    """A running process keeps the PATH it started with, so `winget install`
    lands somewhere this terminal cannot see. That is not a failure and is
    not reported as one."""
    module = entry_point_module()
    _answers(monkeypatch, module, "yes")
    monkeypatch.setattr(module, "run", _Runs())
    assert module.offer_install("git", "winget install --id Git.Git -e",
                                lambda: False, "win32") is False
    assert "open a new terminal and run this again." in capsys.readouterr().out
    assert module.offer_install("git", "sudo apt-get install -y git",
                                lambda: False, "linux") is False
    assert "git is still not there." in capsys.readouterr().out


def test_the_command_line_tools_are_never_re_checked(monkeypatch, capsys):
    """`xcode-select --install` returns as soon as Apple's dialog is on
    screen, minutes before the Tools arrive. There is nothing to re-check
    yet, and waiting would be this tool polling a window it cannot answer."""
    module = entry_point_module()
    _answers(monkeypatch, module, "yes")
    monkeypatch.setattr(module, "run", _Runs())
    probes = []
    assert module.offer_install("git", module.TOOLS_INSTALL,
                                lambda: (probes.append(1), True)[1],
                                "darwin") is False
    assert probes == []
    assert "run this again when it has finished." in capsys.readouterr().out


def test_gh_login_is_offered_as_an_argv_and_never_through_a_shell(monkeypatch):
    """It is a terminal UI that ends in a browser: gh needs the person's own
    stdin, stdout and terminal, and there is nothing in it to quote."""
    module = entry_point_module()
    prompts = _answers(monkeypatch, module, "yes")
    runs = _Runs({"auth status": (1, "")})
    monkeypatch.setattr(module, "run", runs)
    monkeypatch.setattr(module.shutil, "which", _which("gh"))
    opts = module.parse_args([], "/")
    assert module._check_gh(opts) is False, (
        "gh still says it is not authenticated, so the check still fails")
    assert ["gh", "auth", "login"] in runs.calls
    assert prompts == ["  Run `gh auth login` now? Type yes to continue: "]


def test_the_credential_helper_is_a_warning_not_a_refusal(monkeypatch, capsys,
                                                          tmp_path):
    """A machine with NO helper creates three repositories and then fails on
    the first push over HTTPS, which is worth saying before any of them
    exists - and is worth saying with `[??]`, because an SSH remote and every
    system helper make a refusal wrong."""
    module = entry_point_module()
    _no_terminal(monkeypatch, module)
    monkeypatch.setattr(module.shutil, "which", _which("git", "gh"))
    monkeypatch.setattr(module, "run", _Runs({"config --get-all": (1, "")}))
    opts = module.parse_args([], str(tmp_path))
    assert module.preflight_checks(opts) is True, (
        "a missing credential helper must not fail the preflight")
    printed = capsys.readouterr()
    assert "[??]" in printed.err
    assert "no credential helper for github.com" in printed.err
    assert "gh auth setup-git" in printed.err


def test_a_credential_helper_that_is_not_ghs_is_left_alone(monkeypatch,
                                                           capsys, tmp_path):
    """osxkeychain, Windows' `manager`, `store`, a devcontainer's own: they
    all answer git's question for github.com without gh being involved, and
    warning about them would be this tool disliking somebody's
    ~/.gitconfig."""
    module = entry_point_module()
    _no_terminal(monkeypatch, module)
    monkeypatch.setattr(module.shutil, "which", _which("git", "gh"))
    monkeypatch.setattr(module, "run",
                        _Runs({"credential.helper": (0, "osxkeychain\n"),
                               "github.com.helper": (1, "")}))
    opts = module.parse_args([], str(tmp_path))
    assert module.preflight_checks(opts) is True
    assert "credential helper" not in capsys.readouterr().err


# --- --preflight ------------------------------------------------------------

def test_preflight_exits_zero_when_the_machine_is_ready(tmp_path):
    """`--local-remote-dir` so `gh` is neither required nor asked about (the
    rule the whole suite runs under), and the directory it names is NOT
    created: the preflight examines the machine and nothing else."""
    remotes = tmp_path / "remotes"
    result = run_entry("--preflight", "--local-remote-dir", str(remotes))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "(1) preflight" in result.stdout
    assert "this machine is ready." in result.stdout
    assert "nothing was created" in result.stdout
    for later in ("(2) organisation", "(3) project", "(4) naming policy",
                  "(5) the plan", "(6) scaffold"):
        assert later not in result.stdout, f"--preflight reached {later}"
    assert not remotes.exists()


def test_preflight_exits_one_when_a_prerequisite_is_missing(monkeypatch, capsys,
                                                         tmp_path):
    """In-process on purpose: a PATH-stripped subprocess is a POSIX trick and
    this file carries no Windows skip."""
    module = entry_point_module()
    _no_terminal(monkeypatch, module)
    monkeypatch.setattr(module.shutil, "which", _which())
    monkeypatch.setattr(module, "run", _Runs())
    opts = module.parse_args([], str(tmp_path))
    assert module.preflight_only(opts) == 1
    printed = capsys.readouterr()
    assert "this machine is not ready yet" in printed.err
    assert "nothing was created" in printed.out


def test_preflight_needs_no_org_and_clones_nothing(tmp_path):
    """It returns before the checkout probe, before self-bootstrap and before
    the `--org` handshake - so the organisation those need is never asked
    for. The mechanism is POSITION in `_main`, not a rule about `--preflight`
    written into any of them."""
    outside = make_outside_checkout(tmp_path)
    result = run_entry("--preflight",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       cwd=outside, script=outside / "setup-project.py",
                       extra_env={"OPENREPOSHAPE_SELF_BOOTSTRAP": "1"})
    assert result.returncode == 0, result.stderr + result.stdout
    assert "(1) preflight" in result.stdout
    assert "there is no fork origin" not in result.stderr
    assert "(0) self-bootstrap" not in result.stdout
    assert not (tmp_path / "remotes").exists()


# --- --family, and the family FOLDER ----------------------------------------

#: A holder name that appears NOWHERE else in this standard, so a test can
#: assert the new project's tree does not mention it and mean it.
FAMILY = "Zephyr"

#: `family.yaml` as `scripts/family.py init` renders it, cut down to the three
#: facts the scaffold reads: the kind that makes a directory a family FOLDER,
#: and a `name:` that has to agree with the folder it sits in. Written by hand
#: rather than by `family.py init` on purpose - the detection contract is
#: those three lines, and a test that materialized a whole holder would also
#: be asserting how `init` lands, which is a different issue's subject.
FAMILY_YAML = ('schema_version: 1\nkind: family-manifest\n'
               'id: {id}\nname: "{name}"\norg: demoorg\n')


def make_family_folder(root: Path, family: str = FAMILY,
                       name: str | None = None) -> Path:
    """`<root>/<family>/<family>/family.yaml` - the layout #76 placed.

    Returns the FAMILY FOLDER (`<root>/<family>`), which is what a person
    stands in and what `--into` is pointed at. The holder clone is the
    directory inside it that carries the manifest: the doubled
    `<Family>/<Family>` the RULING of 2026-09-09 kept, so the holder
    repository keeps its own name and `family.yaml` disambiguates.

    `name` overrides what the manifest CALLS the family, for the one test
    that needs a manifest which does not agree with its folder.
    """
    folder = root / family
    holder = folder / family
    holder.mkdir(parents=True)
    (holder / "family.yaml").write_text(
        FAMILY_YAML.format(id=family.lower(), name=name or family),
        encoding="utf-8")
    return folder


def test_family_lands_the_clone_inside_the_family_folder(tmp_path):
    """The landing rule: `<into>/<Family>/<Project>`, folder created.

    `<into>` here does not exist at all when the run starts, which is the
    ordinary case for a first member: the flag has to make both levels.
    """
    work = tmp_path / "work"
    result = run_entry("Sample", "--yes", "--org", "demoorg",
                       "--family", FAMILY,
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(work))
    assert result.returncode == 0, result.stderr + result.stdout
    clone = work / FAMILY / "Sample"
    assert clone.is_dir(), f"{clone} does not exist"
    assert (clone / "project.yaml").is_file()
    assert "family       %s" % FAMILY in result.stdout
    assert "lands at     %s" % clone in result.stdout


def test_the_family_is_recorded_in_no_file_of_the_new_project(tmp_path):
    """DOCTRINE, not an omission: the shape confers nothing and membership
    confers nothing, so the holder's `family.yaml` is the only record.

    A project that carried its family in `project.yaml` would be asserting a
    fact about a tree it does not own, and the two could then disagree.
    """
    work = tmp_path / "work"
    result = run_entry("Sample", "--yes", "--org", "demoorg",
                       "--family", FAMILY,
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(work))
    assert result.returncode == 0, result.stderr + result.stdout
    clone = work / FAMILY / "Sample"
    named = []
    for path in clone.rglob("*"):
        if not path.is_file() or ".git" in path.parts or path.name == ".git":
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if FAMILY in body:
            named.append(str(path.relative_to(clone)))
    assert not named, f"these files in the new project name the family: {named}"


def test_standing_in_the_family_folder_does_not_nest_a_second_level(tmp_path):
    """`--family Zephyr` from inside `.../Zephyr` means THIS folder.

    Without this the first member of a family scaffolded from inside its own
    folder lands at `Zephyr/Zephyr/Sample` - inside the holder clone.
    """
    folder = make_family_folder(tmp_path / "work")
    result = run_entry("Sample", "--yes", "--org", "demoorg",
                       "--family", FAMILY,
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(folder))
    assert result.returncode == 0, result.stderr + result.stdout
    assert (folder / "Sample" / "project.yaml").is_file()
    assert not (folder / FAMILY / "Sample").exists(), (
        "the project was nested inside the holder clone")
    assert "you are standing in the %s folder" % FAMILY in result.stdout


def test_standing_in_the_family_folder_needs_no_flag_at_all(tmp_path):
    """Detection, ADVISORY: one plan line, and the landing is what it was.

    The person did not ask for a family here, so nothing about the run
    changes - the line is a report, and the next-commands block names the
    `family.py add` they will want.
    """
    folder = make_family_folder(tmp_path / "work")
    result = run_entry("Sample", "--yes", "--org", "demoorg",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(folder))
    assert result.returncode == 0, result.stderr + result.stdout
    assert ("family       standing in the %s family folder; the project "
            "lands beside its holder" % FAMILY) in result.stdout
    assert (folder / "Sample" / "project.yaml").is_file()
    assert "scripts/family.py add --family-root %s" % (folder / FAMILY) \
        in result.stdout


@pytest.mark.parametrize("manifest_name", [None, "Other"])
def test_a_directory_named_after_a_family_is_only_a_directory(tmp_path,
                                                              manifest_name):
    """`manifest_name=None`: no `family.yaml` at all - a plain folder that
    happens to be called `Zephyr`. `"Other"`: a manifest that names a
    DIFFERENT family from the folder it sits in.

    All three facts have to agree - the folder's name, `kind:
    family-manifest`, and a `name:` equal to that folder - or the detection
    says nothing and the run is exactly what it was. A folder's name alone
    would have made every directory in an estate a family folder.
    """
    folder = tmp_path / "work" / FAMILY
    if manifest_name is None:
        folder.mkdir(parents=True)
    else:
        make_family_folder(tmp_path / "work", name=manifest_name)
    result = run_entry("Sample", "--yes", "--org", "demoorg",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(folder))
    assert result.returncode == 0, result.stderr + result.stdout
    # `[ok] family` - the plan's own line. A bare `family` would match the
    # naming validator's `--explain` table, which names every form.
    assert "[ok] family" not in result.stdout
    assert "scripts/family.py add" not in result.stdout
    assert (folder / "Sample" / "project.yaml").is_file()


def test_nesting_a_family_inside_a_different_family_refuses(tmp_path):
    """Both names, and both ways out. Nothing is moved and there is no
    --force: `Northwind/Zephyr/Sample` is a member of one family filed
    inside another, which no `family.yaml` can describe."""
    folder = make_family_folder(tmp_path / "work", family="Northwind")
    result = run_entry("Sample", "--yes", "--org", "demoorg",
                       "--family", FAMILY,
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(folder))
    assert result.returncode == 2
    assert "--family %s" % FAMILY in result.stderr
    assert "Northwind family folder" in result.stderr
    assert "never nested inside a family" in result.stderr
    assert "`cd` out of Northwind" in result.stderr
    assert "drop --family" in result.stderr
    assert not (tmp_path / "remotes").exists()
    assert not (folder / FAMILY).exists()


def test_the_next_commands_name_the_add_that_records_the_membership(tmp_path):
    """The last line of the hand-over, and the note when the holder is not
    there yet.

    The member can exist before the holder does, so an absent
    `family.yaml` is NAMED rather than refused - the scaffold has already
    succeeded, and refusing something about another repository's tree at
    that point would be refusing after the fact.
    """
    work = tmp_path / "work"
    result = run_entry("Sample", "--yes", "--org", "demoorg",
                       "--family", FAMILY,
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(work))
    assert result.returncode == 0, result.stderr + result.stdout
    holder = work / FAMILY / FAMILY
    assert ("scripts/family.py add --family-root %s --member demoorg/Sample"
            % holder) in result.stdout
    assert "from a checkout of openRepoShape" in result.stdout
    assert "no family.yaml there yet" in result.stdout
    assert "run `family.py init`" in result.stdout


def test_the_holder_note_is_absent_once_the_holder_is_on_disk(tmp_path):
    """The other half of the pair above: the note is about a FILE, so a
    holder already cloned there gets the command and no note."""
    folder = make_family_folder(tmp_path / "work")
    result = run_entry("Sample", "--yes", "--org", "demoorg",
                       "--family", FAMILY,
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(folder))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "scripts/family.py add --family-root %s" % (folder / FAMILY) \
        in result.stdout
    assert "no family.yaml there yet" not in result.stdout


@pytest.mark.parametrize("family,expected", [
    ("zephyr-holder", "matches no family in the naming policy"),
    ("Zephyr_Holder", "matches no family in the naming policy"),
    ("openGlass", "not as a family holder"),
    ("Zephyr-Install", "not as a family holder"),
])
def test_a_family_name_outside_the_holder_form_refuses(tmp_path, family,
                                                       expected):
    """The naming policy's own reading, through the same classifier
    `scripts/family.py init` asks - a name that is a holder here and not
    there would be two standards.

    Exit 1, like the three-name check: a FINDING about a name, not a
    refusal to ask the question.
    """
    result = run_entry("Sample", "--yes", "--org", "demoorg",
                       "--family", family,
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"))
    assert result.returncode == 1, result.stderr + result.stdout
    assert expected in result.stderr
    assert "one CamelCase token" in result.stderr
    assert "(6) scaffold" not in result.stdout
    assert not (tmp_path / "remotes").exists()


def test_a_rehearsal_that_stops_at_the_plan_makes_no_family_folder(tmp_path):
    """A run that creates nothing must leave the disk as it found it.

    No `--yes` and no terminal, so the plan prints and the confirm refuses -
    and `<into>/<Family>/` is made in step (7) and nowhere earlier, or the
    rehearsal would leave a folder the person never asked for.
    """
    work = tmp_path / "work"
    result = run_entry("Sample", "--org", "demoorg", "--family", FAMILY,
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(work))
    assert result.returncode == 2
    assert "no terminal to confirm on" in result.stderr
    assert "lands at     %s" % (work / FAMILY / "Sample") in result.stdout
    assert "--dry-run: nothing was created." in result.stdout
    # The plan an assistant relays names the clone path too, family level
    # included (#498), though the confirm refuses.
    assert "clone into   %s" % (work / FAMILY / "Sample") in result.stdout
    assert not work.exists(), f"{work} was created by a run that created nothing"
    assert not (tmp_path / "remotes").exists()


# --- what stands at a taken clone path (#498) --------------------------------
#
# The runs through both entry points are `conftest`'s, wrapped above. These
# ask the pieces in-process: what the refusal can tell about a clone, a
# symbolic link, and the step (7) backstop, which a run reaches only when the
# path appears while it is going.

#: An `origin` carrying a token, as an HTTPS clone can record one.
WITH_A_TOKEN = "https://dana:ghp_notreal@github.com/Northwind/Sample.git"

#: A password holding a bare `@`: a malformed URL, and still no part of it
#: is echoed (#509's review, NIT-1).
WITH_AN_AT = "https://dana:p@SECRET3@github.com/Northwind/Sample.git"

REHEARSALS = ("It looks like the clone a rehearsal left behind: its `origin` "
              "is %s, a repository on this disk, as `--local-remote-dir` "
              "makes one.")

HOLDS_A_GIT = "It is a directory holding a `.git`."


def _a_clone(taken: Path, origin=None, shape_root: bool = False) -> None:
    """`taken` as `git init` leaves it, with `origin` and a `project.yaml`
    if asked; no commit, so no identity is needed."""
    taken.mkdir(parents=True)
    git("init", "-q", cwd=taken)
    if origin is not None:
        git("remote", "add", "origin", str(origin), cwd=taken)
    if shape_root:
        (taken / "project.yaml").write_bytes(b"schema_version: 1\n")


def _an_origin_with_controls(taken: Path) -> None:
    """`taken` with a `project.yaml` and an `origin` named `Sample.git` on
    this disk whose value holds an ESC sequence and a newline before a
    forged `REFUSED:` line. Appended to `.git/config` as BYTES, so no argv
    and no code page carries it; git reads it back as written, which the
    test asserts first, so the filter and not a parse failure is what keeps
    it off the screen."""
    _a_clone(taken, shape_root=True)
    with open(taken / ".git" / "config", "ab") as config:
        config.write(b'[remote "origin"]\n'
                     b'\turl = "/srv\x1b[2J\\nREFUSED: forged/Sample.git"\n')


@pytest.mark.parametrize("case", [
    "github", "a-password-with-an-at", "the-rehearsals",
    "the-rehearsals-as-a-file-url", "a-file-url-with-credentials",
    "a-mirror-under-another-name", "rehearsal-shaped-with-no-project-yaml",
    "no-origin", "a-git-file", "an-empty-git-inside-another-repository",
    "an-origin-with-control-characters"])
def test_what_stands_at_a_taken_clone_path(tmp_path, case):
    """`what_stands_at`: a sentence, and the way out it offers.

    What LOOKS like a rehearsal's clone - an `origin` on this disk, named
    `<Project>.git`, and a `project.yaml` - is said to look like one, and
    deleting it is offered only if nothing in it is the person's (#509's
    review, MUST-1). A mirror under another name and a clone with no
    manifest are somebody's, and so is anything this cannot read. No
    credential and no control character is echoed. And the `origin` is
    read from the directory's OWN `.git/config`: an empty `.git` inside a
    repository that has one must not be reported as a clone of THAT
    repository, which is what `git -C` finds by walking up."""
    module = entry_point_module()
    taken = tmp_path / "here" / "Sample"
    rehearsal = tmp_path / "here" / "rehearsal" / "Sample.git"
    mirror = tmp_path / "mirrors" / "Mirror.git"
    on_disk = "/" + rehearsal.as_posix().lstrip("/")
    github = ("It is a clone of https://github.com/Northwind/Sample.git.",
              KEEP_IT)
    if case == "github":
        _a_clone(taken, WITH_A_TOKEN, shape_root=True)
        expected = github
    elif case == "a-password-with-an-at":
        _a_clone(taken, WITH_AN_AT, shape_root=True)
        expected = github
    elif case == "the-rehearsals":
        _a_clone(taken, rehearsal, shape_root=True)
        expected = (REHEARSALS % rehearsal, DISCARD_IT_IF_UNUSED)
    elif case == "the-rehearsals-as-a-file-url":
        _a_clone(taken, rehearsal.as_uri(), shape_root=True)
        expected = (REHEARSALS % rehearsal.as_uri(), DISCARD_IT_IF_UNUSED)
    elif case == "a-file-url-with-credentials":
        _a_clone(taken, "file://dana:SECRET7@" + on_disk, shape_root=True)
        expected = (REHEARSALS % ("file://" + on_disk), DISCARD_IT_IF_UNUSED)
    elif case == "a-mirror-under-another-name":
        _a_clone(taken, mirror, shape_root=True)
        expected = ("It is a clone of %s." % mirror, KEEP_IT)
    elif case == "rehearsal-shaped-with-no-project-yaml":
        _a_clone(taken, rehearsal)
        expected = ("It is a clone of %s." % rehearsal, KEEP_IT)
    elif case == "no-origin":
        _a_clone(taken)
        expected = (HOLDS_A_GIT, KEEP_IT)
    elif case == "a-git-file":
        taken.mkdir(parents=True)
        (taken / ".git").write_bytes(b"gitdir: ../elsewhere/.git\n")
        expected = (HOLDS_A_GIT, KEEP_IT)
    elif case == "an-empty-git-inside-another-repository":
        _a_clone(taken.parent, "https://example.invalid/Outer.git")
        (taken / ".git").mkdir(parents=True)
        expected = (HOLDS_A_GIT, KEEP_IT)
    else:
        _an_origin_with_controls(taken)
        read = git("config", "--file", str(taken / ".git" / "config"),
                   "--get", "remote.origin.url", cwd=tmp_path).stdout
        assert "\x1b[2J" in read and "\nREFUSED: forged" in read, repr(read)
        expected = (HOLDS_A_GIT, KEEP_IT)
    said = module.what_stands_at(str(taken), "Sample")
    assert said == expected
    for leaked in ("ghp_notreal", "SECRET3", "SECRET7", "\x1b", "forged"):
        assert leaked not in said[0], said


def test_a_working_clone_of_a_local_repository_is_not_called_a_rehearsals(
        tmp_path):
    """#509's review, MUST-1: a clone of a local bare repository setup never
    made, holding a commit nobody has pushed, meets every sign a rehearsal's
    clone does - an `origin` on this disk named `Sample.git`, and a
    `project.yaml`. It may be somebody's work, so the refusal says only that
    it LOOKS like a rehearsal's clone, and offers deleting it only if
    nothing in it is theirs: never "It is the clone a rehearsal left
    behind", and never the bare "Move or delete it"."""
    module = entry_point_module()
    bare = tmp_path / "srv" / "Sample.git"
    git("init", "-q", "--bare", str(bare), cwd=tmp_path)
    work = tmp_path / "here" / "Sample"
    work.parent.mkdir()
    git("clone", "-q", str(bare), str(work), cwd=tmp_path)
    (work / "project.yaml").write_bytes(b"schema_version: 1\n")
    git("add", "project.yaml", cwd=work)
    git("commit", "-q", "-m", "real work, not pushed", cwd=work)
    with pytest.raises(module.Refusal) as refused:
        module.refuse_a_taken_clone_path(str(work), "Sample")
    said = str(refused.value)
    assert ("It looks like the clone a rehearsal left behind: its `origin` "
            "is ") in said, said
    assert said.endswith("makes one. " + DISCARD_IT_IF_UNUSED), said
    assert "It is the clone a rehearsal left behind" not in said, said
    assert DISCARD_IT not in said, said


@pytest.mark.parametrize("target", ["nowhere", "an-empty-directory"])
def test_a_symbolic_link_takes_the_clone_path_and_is_said_to_be_one(tmp_path,
                                                                   target):
    """`os.path.exists` reads a link to nothing as absent, and `git clone`
    still refuses it (`could not create work tree dir`), so step (3) asks
    `lexists`. A link is said to be a link, and is never offered for
    deletion: `os.path.isdir` follows one to an empty directory, and `rm -r
    Sample/` on "delete it" would act on the target (#509's review, NIT-2).
    A free path is the control: it is not refused."""
    module = entry_point_module()
    aim = tmp_path / target
    if target != "nowhere":
        aim.mkdir()
    link = tmp_path / "Sample"
    try:
        os.symlink(aim, link, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"this platform cannot create a symlink here: {exc}")
    assert module.refuse_a_taken_clone_path(str(tmp_path / "Free"),
                                            "Free") is None
    with pytest.raises(module.Refusal) as refused:
        module.refuse_a_taken_clone_path(str(link), "Sample")
    assert refused.value.code == 2
    said = str(refused.value)
    assert said.startswith(
        "%s already exists, and that is where this project would be cloned, "
        "so the run stops here and nothing was created. It is a symbolic "
        "link to " % link), said
    assert said.endswith("%s. %s" % (target, KEEP_IT)), said


@pytest.mark.parametrize("taken", ["a-directory", "a-link-to-nothing"])
def test_a_path_taken_after_step_three_is_the_backstops(monkeypatch, tmp_path,
                                                        taken):
    """Step (7) still asks, for a path that appeared while the run was going,
    after all three repositories exist, and asks `lexists` as step (3) does:
    a link to nothing is a path `git clone` refuses (#509's review,
    SHOULD-2). Its way out moves the thing aside and clones from the clone's
    PARENT: as it used to read, the printed `git clone` met the same
    directory, and `cd <Project>` from anywhere else entered whatever stood
    there. Each path is one word, and the local clone can read its legs
    (#538). Nothing is cloned."""
    module = entry_point_module()
    runs = _Runs()
    monkeypatch.setattr(module, "run", runs)
    opts = module.parse_args(["--project", "Sample", "--org", "demoorg",
                              "--local-remote-dir", str(tmp_path / "remotes"),
                              "--into", str(tmp_path / "work")],
                             str(tmp_path))
    parent = Path(opts.into)
    parent.mkdir(parents=True)
    if taken == "a-directory":
        (parent / "Sample").mkdir()
    else:
        try:
            os.symlink(tmp_path / "nowhere", parent / "Sample",
                       target_is_directory=True)
        except (NotImplementedError, OSError) as exc:
            pytest.skip(f"this platform cannot create a symlink here: {exc}")
    with pytest.raises(module.Refusal) as refused:
        module.clone_and_bootstrap(opts, "demoorg",
                                   module.Landing(parent, "", None))
    assert refused.value.code == 2
    assert str(refused.value) == (
        "%s already exists - it was not there when step (3) looked - so "
        "there is nowhere to clone into. The three repositories WERE "
        "created. Move it aside, then finish by hand:\n"
        "    cd %s\n"
        "    git -c protocol.file.allow=always clone --recurse-submodules %s\n"
        "    cd Sample && %s scripts/bootstrap.py"
        % (parent / "Sample", module.shell_word(parent, posix=True),
           module.shell_word(os.path.join(opts.local_remote_dir,
                                          "Sample.git"), posix=True),
           module.PYTHON_CMD))
    assert runs.calls == [], f"something was run: {runs.calls}"


def test_a_folder_step_seven_cannot_make_is_refused_with_the_way_on(
        monkeypatch, tmp_path):
    """#538: a file that appeared at `<into>/<Family>` after step (3)
    looked is a refusal naming it, with the lines that finish the run by
    hand, not the `FileExistsError` traceback `os.makedirs` raised after all
    three repositories existed. Nothing is cloned."""
    module = entry_point_module()
    runs = _Runs()
    monkeypatch.setattr(module, "run", runs)
    opts = module.parse_args(["--project", "Sample", "--org", "demoorg",
                              "--family", FAMILY,
                              "--local-remote-dir", str(tmp_path / "remotes"),
                              "--into", str(tmp_path / "work")],
                             str(tmp_path))
    folder = Path(opts.into) / FAMILY
    folder.parent.mkdir(parents=True)
    folder.write_bytes(b"not a folder\n")
    with pytest.raises(module.Refusal) as refused:
        module.clone_and_bootstrap(opts, "demoorg",
                                   module.Landing(folder, FAMILY,
                                                  folder / FAMILY))
    assert refused.value.code == 2
    said = str(refused.value)
    assert said.startswith("%s could not be made a folder (" % folder), said
    assert said.endswith(
        "), so there is nowhere to clone into. The three repositories WERE "
        "created. Make it one, then finish by hand:\n"
        + module.finish_by_hand(str(folder),
                                os.path.join(opts.local_remote_dir,
                                             "Sample.git"),
                                "Sample", True)), said
    assert runs.calls == [], f"something was run: {runs.calls}"
    assert folder.read_bytes() == b"not a folder\n"


#: `(a Windows clone path, the word the printed lines spell it as)`. The
#: spelling is `sh`'s: Git Bash is the shell a Windows person pastes these
#: into, and #532 rules the printed commands POSIX-only. PowerShell's rule
#: leaves the first bare, so Git Bash reads `C:workSample`, and doubles the
#: apostrophe of the third, so Git Bash reads `ONeill`.
WINDOWS_CLONES = (
    (r"C:\work\Sample", r"'C:\work\Sample'"),
    (r"C:\Users\a b\work\Sample", r"'C:\Users\a b\work\Sample'"),
    (r"C:\Users\Jane O'Neill\work\Sample",
     r"'C:\Users\Jane O'\''Neill\work\Sample'"),
)
WINDOWS_ASSEMBLY = (r"C:\Users\Jane O'Neill\remotes\Sample.git",
                    r"'C:\Users\Jane O'\''Neill\remotes\Sample.git'")


@pytest.mark.parametrize("clone,spelled", WINDOWS_CLONES)
def test_the_changed_paste_lines_are_posix_quoted_on_windows_too(
        monkeypatch, capsys, clone, spelled):
    """#538, under #532's ruling that printed commands are POSIX-only: the
    hand-over's `cd <clone>` and the backstop's `cd <parent>` and `<assembly>`
    are spelled for `sh` on every host, as the scaffold's own NEXT STEPS
    clone is (`shell_line(..., "posix")`). `os.name` is switched and
    `MSYSTEM` unset for the calls, which is what `host_shell_dialect` reads
    to answer PowerShell's dialect (#711), so this holds on any host; the
    lines are then read back by `shlex.split`, as Git Bash reads them. The
    family lines are #532's and are not asked."""
    module = entry_point_module()
    assembly, assembly_spelled = WINDOWS_ASSEMBLY
    urls = {"assembly": assembly, "spec": assembly, "code": assembly}
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.delenv("MSYSTEM", raising=False)
    module.hand_over("Sample", clone, urls, "demoorg",
                     module.Landing(None, "", None))
    local = module.finish_by_hand(clone, assembly, "Sample", True)
    github = module.finish_by_hand(
        clone, "https://github.com/demoorg/Sample.git", "Sample", False)
    monkeypatch.undo()
    [closing] = [line for line in capsys.readouterr().out.splitlines()
                 if line.startswith("    cd ")]
    assert closing == "    cd " + spelled, closing
    assert shlex.split(closing) == ["cd", clone], closing
    assert local == (
        "    cd %s\n"
        "    git -c protocol.file.allow=always -c core.autocrlf=false clone "
        "--recurse-submodules %s\n"
        "    cd Sample && %s scripts/bootstrap.py"
        % (spelled, assembly_spelled, module.PYTHON_CMD)), local
    assert [shlex.split(line) for line in local.splitlines()[:2]] == [
        ["cd", clone],
        ["git", *FILE_PROTOCOL, *LF_ON_WINDOWS, "clone",
         "--recurse-submodules", assembly]]
    assert github.splitlines()[:2] == [
        "    cd " + spelled,
        "    git -c core.autocrlf=false clone --recurse-submodules "
        "https://github.com/demoorg/Sample.git"], github


#: What setup's own clone passes on Windows (`clone_and_bootstrap`), and
#: since #926 its finish-by-hand clone too.
LF_ON_WINDOWS = ["-c", "core.autocrlf=false"]


class _OsNamed:
    """This process's `os`, answering `name` with another platform's, for
    the module under test alone: `pathlib` keeps reading the real one, and
    on Python 3.12 a `Path` made while `os.name` itself says `nt` is a
    `WindowsPath`, which cannot be made on a POSIX host."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __getattr__(self, attr):
        return getattr(os, attr)


@pytest.mark.parametrize("name", ["nt", "posix"])
@pytest.mark.parametrize("local", [True, False], ids=["local", "github"])
def test_the_backstops_clone_checks_out_as_setups_own_does(monkeypatch,
                                                          tmp_path, name,
                                                          local):
    """#926 (U041): under an emulated `nt` the finish-by-hand clone carries
    `-c core.autocrlf=false`, as setup's own clone does, and on any other
    host neither does. The module's `os` answers `name` (`_OsNamed`), so
    this holds on any host; the printed line is read back by `shlex.split`,
    as Git Bash reads it, and setup's own clone is the argv
    `clone_and_bootstrap` hands `run`. On main the printed line had no
    `-c core.autocrlf=false` on Windows, and a clone made by hand under Git
    for Windows' default `core.autocrlf=true` was not the clone setup
    makes."""
    module = entry_point_module()
    runs = _Runs()
    monkeypatch.setattr(module, "run", runs)
    flags = ["--project", "Sample", "--org", "demoorg",
             "--into", str(tmp_path / "work")]
    if local:
        flags += ["--local-remote-dir", str(tmp_path / "remotes")]
    opts = module.parse_args(flags, str(tmp_path))
    assembly = (os.path.join(opts.local_remote_dir, "Sample.git") if local
                else "https://github.com/demoorg/Sample.git")
    monkeypatch.setattr(module, "os", _OsNamed(name))
    module.clone_and_bootstrap(opts, "demoorg",
                               module.Landing(Path(opts.into), "", None))
    printed = module.finish_by_hand(opts.into, assembly, "Sample", local)
    [own] = [argv for argv in runs.calls if "clone" in argv]
    lf = LF_ON_WINDOWS if name == "nt" else []
    assert shlex.split(printed.splitlines()[1]) == [
        "git", *(FILE_PROTOCOL if local else []), *lf, "clone",
        "--recurse-submodules", assembly], printed
    assert any(own[at:at + 2] == LF_ON_WINDOWS
               for at in range(own.index("clone"))) is (name == "nt"), own


@pytest.mark.parametrize("case", ["a-file-two-levels-up", "a-link-to-nothing",
                                  "a-link-to-a-folder", "nothing-there"])
def test_what_stands_above_a_clone_path(tmp_path, case):
    """#538, step (3): the first thing on the way up from the clone's parent
    must be a folder, or there is nowhere to make the folders between. A
    file is said to be one; a link is said to be one, by its target; a link
    TO a folder is a folder; and a path nothing stands on at all is left to
    the clone, as it was."""
    module = entry_point_module()
    blocker = tmp_path / "work" / FAMILY
    blocker.parent.mkdir()
    clone = blocker / "Sample"
    expected = None
    if case == "a-file-two-levels-up":
        blocker.write_bytes(b"not a folder\n")
        clone = blocker / "deeper" / "Sample"
        expected = "a file"
    elif case == "nothing-there":
        clone = blocker / "deeper" / "Sample"
    else:
        target = tmp_path / ("real" if case == "a-link-to-a-folder"
                             else "nowhere")
        if case == "a-link-to-a-folder":
            target.mkdir()
        try:
            os.symlink(target, blocker, target_is_directory=True)
        except (NotImplementedError, OSError) as exc:
            pytest.skip(f"this platform cannot create a symlink here: {exc}")
        if case == "a-link-to-nothing":
            # THE TARGET AS THE LINK HOLDS IT, not as it was given:
            # `os.readlink` on Windows returns the substitute name with its
            # `\\?\` prefix (Python 3.8+), and the refusal names that.
            expected = ("a symbolic link to %s, which is not a folder"
                        % os.readlink(blocker))
    if expected is None:
        assert module.refuse_a_taken_clone_path(str(clone), "Sample") is None
        return
    with pytest.raises(module.Refusal) as refused:
        module.refuse_a_taken_clone_path(str(clone), "Sample")
    assert refused.value.code == 2
    assert str(refused.value) == (
        "%s is %s, and this project would be cloned inside it, at %s, so the "
        "run stops here and nothing was created. %s"
        % (blocker, expected, clone, KEEP_IT))


@pytest.mark.parametrize("number,reason", [(13, "Permission denied"),
                                           (30, "Read-only file system")])
def test_a_parent_nobody_can_write_in_is_refused_by_name(monkeypatch, tmp_path,
                                                         number, reason):
    """#608, L2-26, on every platform and as every user: step (3) asks the
    folder it finds above the clone for a folder of its own
    (`tempfile.mkdtemp`), and what the system answers is the reason it gives.
    `refuse_a_file_above` read only that what it found was a folder, so a
    parent at mode 555, or on a read-only disk, passed and the three
    repositories were created before step (7) said so."""
    module = entry_point_module()

    def refuses(*args, **kwargs):
        raise OSError(number, reason)

    monkeypatch.setattr(tempfile, "mkdtemp", refuses)
    clone = tmp_path / "work" / "Sample"
    with pytest.raises(module.Refusal) as refused:
        module.refuse_a_taken_clone_path(str(clone), "Sample")
    assert refused.value.code == 2
    assert str(refused.value) == (
        "%s is a folder you cannot write in (%s), and this project would be "
        "cloned inside it, at %s, so the run stops here and nothing was "
        "created. %s" % (tmp_path, reason, clone, WRITE_IT))


@pytest.mark.parametrize("depth", [0, 1, 2])
def test_the_write_probe_is_made_in_the_nearest_folder_and_taken_away(
        monkeypatch, tmp_path, depth):
    """#608, L2-26: the folder the probe makes is made in the NEAREST folder
    that exists - the clone's own parent when it is there, else the first one
    above it - and is gone again, so a rehearsal leaves the disk as it found
    it."""
    module = entry_point_module()
    made_in = []
    real = tempfile.mkdtemp

    def spy(*args, **kwargs):
        made = real(*args, **kwargs)
        made_in.append(made)
        return made

    monkeypatch.setattr(tempfile, "mkdtemp", spy)
    base = tmp_path / "base"
    base.mkdir()
    clone = base.joinpath(*("below%d" % n for n in range(depth)), "Sample")
    assert module.refuse_a_taken_clone_path(str(clone), "Sample") is None
    [made] = made_in
    assert Path(made).parent == base, made
    assert not os.path.lexists(made), made
    assert list(base.iterdir()) == []


def test_a_probe_folder_that_will_not_go_is_no_reason_to_refuse(
        monkeypatch, tmp_path, capsys):
    """#608, rv608 on #623: the refusal is for a folder that could not be MADE.
    Taking the probe away again is best-effort: where a handle on the new
    folder (an indexer, an antivirus, on Windows) makes `rmdir` fail after
    the folder was made, the parent is still one the person can write in, so
    the clone path is not refused for it, and the folder left behind is named
    rather than lost."""
    module = entry_point_module()
    real_rmdir = os.rmdir

    def held(path, *args, **kwargs):
        if ".openreposhape-write-probe-" in os.path.basename(str(path)):
            raise OSError(errno.EBUSY, "Device or resource busy")
        return real_rmdir(path, *args, **kwargs)

    monkeypatch.setattr(os, "rmdir", held)
    base = tmp_path / "base"
    base.mkdir()
    assert module.refuse_a_taken_clone_path(str(base / "Sample"),
                                            "Sample") is None
    [left] = list(base.iterdir())
    real_rmdir(str(left))
    said = capsys.readouterr()
    assert said.out == "", said.out
    assert str(left) in said.err, said.err
    assert "could not be taken away again" in said.err, said.err
    assert "Device or resource busy" in said.err, said.err
    assert "cannot write in" not in said.err, said.err


def test_the_drive_is_what_the_os_path_module_splits_off(monkeypatch):
    """#608: `drive_of` is `os.path.splitdrive`'s drive, which a POSIX host
    never has, so the Windows module is put in its place for the three calls:
    a letter, a network share, and a path with neither."""
    module = entry_point_module()
    with monkeypatch.context() as windows:
        windows.setattr(os, "path", ntpath)
        found = [module.drive_of(path) for path in (
            "C:\\work\\Sample", "\\\\server\\share\\work\\Sample",
            "work\\Sample")]
    assert found == ["C:", "\\\\server\\share", ""]


@pytest.mark.parametrize("drive,said", [
    ("Z:", "The drive Z: is not there"),
    ("\\\\server\\share", "The drive \\\\server\\share is not there"),
    ("", "Not even the top of the path is there")])
def test_a_path_whose_drive_is_not_there_is_refused_by_name(
        monkeypatch, tmp_path, drive, said):
    """#608, L2-26: `nearest_entry` is None where not even the top of the
    path is there, which on Windows is a drive that does not exist and on a
    POSIX host cannot happen, so it is made to here, with the drive `drive_of`
    names. On main that None passed (`refuse_a_file_above` left it "to the
    clone"). Nothing is asked of the disk."""
    module = entry_point_module()
    monkeypatch.setattr(module, "nearest_entry", lambda path: None)
    monkeypatch.setattr(module, "drive_of", lambda path: drive)

    def asked(*args, **kwargs):
        raise AssertionError("the disk was asked for a folder to probe in")

    monkeypatch.setattr(tempfile, "mkdtemp", asked)
    clone = str(tmp_path / "work" / "Sample")
    with pytest.raises(module.Refusal) as refused:
        module.refuse_a_taken_clone_path(clone, "Sample")
    assert refused.value.code == 2
    assert str(refused.value) == (
        "%s, and this project would be cloned at %s, so the run stops here "
        "and nothing was created. %s" % (said, clone, DRIVE_WAY_OUT))


#: 40 hex, for a `--pin` nothing reads the digest of.
A_COMMIT = "0123456789abcdef0123456789abcdef01234567"


@pytest.mark.parametrize("passthrough,dry", [
    ([], False), (["--dry-run"], True), (["--d"], True),
    (["--work-dir", "w", "--dry-ru"], True), (["--name=--dry-run"], False),
    (["--", "--dry-run"], False), (["--d=x"], True), (["--"], False)])
def test_a_dry_run_is_read_as_the_scaffold_reads_one(passthrough, dry):
    """#538: `--dry-run`, or a prefix of it, up to an inner `--`; never a
    value given with `=` to another flag."""
    assert entry_point_module().passes_a_dry_run(passthrough) is dry


@pytest.mark.parametrize("passthrough,declared", [
    ([], []),
    (["--pin", f"acme/openGlass@{A_COMMIT}", f"--pin=openChart@{A_COMMIT}"],
     ["--pins=openGlass,openChart"]),
    (["--referent-chain", "openA,openB", "--referent=openXdox,openDox"],
     ["--referent-chain=openXdox,openDox"]),
    (["--pin-owner", "acme", "--pin-source", "src", "--reference", "doc.md",
      "--referen", "x"], []),
    (["--pin", f"openGlass@{A_COMMIT}", "--",
      "--pin", f"openChart@{A_COMMIT}"], ["--pins=openGlass"]),
    (["--pin"], []), (["--pin", f"@{A_COMMIT}"], []),
    # L2-25 (#608): a chain is verified from the tree `--pin-source` names, so
    # that is passed as a bare `--link-source`: the last one, in any spelling
    # the scaffold takes for the flag, and only where there is a chain (a
    # source no link used is a NOTE the plan never prints).
    (["--referent-chain", "openXdox,openDox", "--pin-source", "src"],
     ["--referent-chain=openXdox,openDox", "--link-source=src"]),
    (["--pin-source=a", "--referent-chain=openXdox,openDox", "--pin-s", "b",
      "--pin-so=c"],
     ["--referent-chain=openXdox,openDox", "--link-source=c"]),
    (["--pin", f"openXdox@{A_COMMIT}", "--referent-chain", "openXdox,openDox",
      "--pin-source", "/x/src"],
     ["--pins=openXdox", "--referent-chain=openXdox,openDox",
      "--link-source=/x/src"]),
    (["--pin-source", "src"], []),
    (["--referent-chain", " , ", "--pin-source", "src"],
     ["--referent-chain= , "]),
    (["--referent-chain", "openXdox,openDox", "--pin-", "x", "--pin-sourc"],
     ["--referent-chain=openXdox,openDox"]),
    (["--referent-chain", "openXdox,openDox", "--", "--pin-source", "src"],
     ["--referent-chain=openXdox,openDox"]),
    # ...as the scaffold's `Path` reads it: a value that starts with `-` is
    # not given as the next word (argparse reads it as a flag), and is kept
    # after an `=`. A value `PRODUCT=PATH` would be read as keyed by the
    # naming check where the scaffold reads one path; joined to the
    # standard's checkout it has a separator before its first `=`, which no
    # link's name holds, so it is one path to the naming check too (#907).
    (["--referent-chain", "openXdox,openDox", "--pin-source", "--wat"],
     ["--referent-chain=openXdox,openDox"]),
    (["--referent-chain", "openXdox,openDox", "--pin-source"],
     ["--referent-chain=openXdox,openDox"]),
    (["--referent-chain", "openXdox,openDox", "--pin-source=-odd"],
     ["--referent-chain=openXdox,openDox", "--link-source=-odd"]),
    (["--referent-chain", "openXdox,openDox", "--pin-source",
      "openXdox=layer"],
     ["--referent-chain=openXdox,openDox", "--link-source=openXdox=layer"]),
    (["--referent-chain", "openXdox,openDox", "--pin-source", "a/b=c"],
     ["--referent-chain=openXdox,openDox", "--link-source=a/b=c"]),
    # ...and where `=` follows a Windows separator or a drive, the text before
    # it cannot be a link's name either.
    (["--referent-chain", "openXdox,openDox", "--pin-source", "a\\b=c"],
     ["--referent-chain=openXdox,openDox", "--link-source=a\\b=c"]),
    (["--referent-chain", "openXdox,openDox", "--pin-source", "C:x=y"],
     ["--referent-chain=openXdox,openDox", "--link-source=C:x=y"]),
    (["--referent-chain", "openXdox,openDox", "--pin-source",
      "C:\\src\\openXdox=layer"],
     ["--referent-chain=openXdox,openDox",
      "--link-source=C:\\src\\openXdox=layer"]),
    # An EMPTY value is left to the plan: the scaffold refuses it as
    # `pin-source-no-path` (#570), so no `--link-source` goes at all, where
    # `--link-source=` is refused by the naming check as `link-source-no-path`
    # (#576) and `--link-source=.` WARNs about a flag the person never typed
    # and a folder the plan never reads. The LAST value is the one that
    # counts, empty or not, and a blank one is not an empty one.
    (["--referent-chain", "openXdox,openDox", "--pin-source", ""],
     ["--referent-chain=openXdox,openDox"]),
    (["--referent-chain", "openXdox,openDox", "--pin-source="],
     ["--referent-chain=openXdox,openDox"]),
    (["--referent-chain", "openXdox,openDox", "--pin-source", "src",
      "--pin-source", ""],
     ["--referent-chain=openXdox,openDox"]),
    (["--referent-chain", "openXdox,openDox", "--pin-source", "",
      "--pin-source", "src"],
     ["--referent-chain=openXdox,openDox", "--link-source=src"]),
    (["--referent-chain", "openXdox,openDox", "--pin-source", " "],
     ["--referent-chain=openXdox,openDox", "--link-source= "]),
    (["--pin-source", ""], []),
    # The naming check reads a source for a chain's holders, and a chain of
    # one link has none: it says `NOTE --link-source ...: not used`, which the
    # plan never prints for the same chain. So a source goes with a chain of
    # TWO links at least, counted as the scaffold counts them (stripped,
    # blanks dropped), and the chain is passed either way.
    (["--referent-chain", "openDox", "--pin-source", "src"],
     ["--referent-chain=openDox"]),
    (["--referent-chain", "openDox, ", "--pin-source", "src"],
     ["--referent-chain=openDox, "]),
    (["--referent-chain", " , openDox ,", "--pin-source=src"],
     ["--referent-chain= , openDox ,"]),
    (["--referent-chain", "openXdox, ,openDox", "--pin-source", "src"],
     ["--referent-chain=openXdox, ,openDox", "--link-source=src"]),
    # A repeated `--referent-chain` keeps its last, and so does the source's
    # reading of whether there is a chain to read it for.
    (["--referent-chain", "openXdox,openDox", "--referent-chain", " , ",
      "--pin-source", "src"],
     ["--referent-chain= , "]),
    (["--referent-chain", " , ", "--referent-chain", "openXdox,openDox",
      "--pin-source", "src"],
     ["--referent-chain=openXdox,openDox", "--link-source=src"]),
    # L2-27 (#608): `--pin` followed by a flag has no value.
    (["--pin", "--referent-chain", "x"], ["--referent-chain=x"]),
    (["--pin", "--pin", f"openGlass@{A_COMMIT}"], ["--pins=openGlass"])])
def test_the_declarations_are_read_as_the_scaffold_reads_them(passthrough,
                                                              declared):
    """#538: each `--pin`'s product, at its last `/` and before `@`; the
    last `--referent-chain`, in any spelling the scaffold takes for it; and
    nothing from a flag that only shares a prefix with one of them. A
    `--link-source` in the table is the `--pin-source` as typed, and goes
    as the plan names it (`as_named_by_the_plan`)."""
    assert entry_point_module().naming_declarations(
        passthrough, REPO) == as_named_by_the_plan(declared)


def as_named_by_the_plan(declared: list) -> list:
    """`declared` with each `--link-source=<path>` as step (4) passes it
    since #907 (U171): joined to the standard's checkout, the folder the
    scaffold runs in, and resolved, as step (5) names it."""
    return [("--link-source=%s" % Path(REPO, arg.partition("=")[2]).resolve()
             if arg.startswith("--link-source=") else arg)
            for arg in declared]


@pytest.mark.parametrize("passthrough,flag,values", [
    # L2-27 (#608), the issue's own case and its counterpart.
    (["--pin", "--referent-chain", "x"], "--pin", []),
    (["--pin", "--referent-chain", "x"], "--referent-chain", ["x"]),
    (["--pin", "-x", "--pin", "a@b"], "--pin", ["a@b"]),
    (["--pin", "a@b", "--pin"], "--pin", ["a@b"]),
    # The `=` spelling takes what follows it whatever it starts with, and the
    # word after a flag that has its value is not read again as one.
    (["--pin=-x"], "--pin", ["-x"]),
    (["--pin=a", "--pin", "b", "c"], "--pin", ["a", "b"]),
    (["--pin", "a", "--", "--pin", "b"], "--pin", ["a"])])
def test_a_word_that_starts_with_a_dash_is_not_a_value(passthrough, flag,
                                                       values):
    """#608, L2-27: `passed_values` says a value never starts with `-` in the
    second spelling, because argparse reads such a word as a flag; on main
    `--pin --referent-chain x` gave `--pin` the value `--referent-chain`, and
    step (4) was handed `--pins=--referent-chain`."""
    assert entry_point_module().passed_values(passthrough, flag) == values


def test_each_passed_flag_is_spelled_as_the_scaffold_takes_it():
    """`PASSED_FLAGS` against the scaffold's own `--help`: each flag is one
    of its options; a shortest spelling shorter than the flag names that
    flag alone; and one character less is not that flag alone any more, so
    the row is the shortest. A flag the scaffold renamed, or one it grew a
    sibling of, fails here instead of being misread."""
    module = entry_point_module()
    helped = subprocess.run([sys.executable, str(REPO / "scaffold-project.py"),
                             "--help"], capture_output=True, text=True,
                            check=True).stdout
    usage = helped.split("\n\n", 1)[0]
    options = sorted(set(re.findall(r"--[a-z][a-z-]*", usage)))
    for flag, shortest in module.PASSED_FLAGS.items():
        assert flag in options, flag
        assert flag.startswith(shortest), flag
        if shortest != flag:
            assert [o for o in options if o.startswith(shortest)] == [flag]
        if len(shortest) > 3:
            assert [o for o in options if o.startswith(shortest[:-1])] != [
                flag], flag


# --- #538, on an interpreter alone: each is `conftest`'s helper of that name -

def test_the_closing_cd_names_the_clone_as_one_word(tmp_path):
    assert_the_closing_cd_is_one_word(run_entry, tmp_path)


def test_the_backstop_is_finished_by_hand_as_printed(tmp_path):
    assert_the_backstop_is_finished_by_hand_as_printed(run_entry, tmp_path)


def test_the_scaffold_leaves_its_next_steps_to_setup(setup_run):
    assert_the_scaffold_leaves_its_next_steps_to_setup(setup_run["result"])


@pytest.mark.parametrize("where", FILE_ABOVE_THE_CLONE)
def test_a_file_above_the_clone_path_is_refused(tmp_path, where):
    assert_a_file_above_the_clone_path_is_refused(run_entry, tmp_path, where)


@pytest.mark.parametrize("spelling,yes", DRY_RUNS)
def test_a_dry_run_passed_through_ends_at_the_plan(tmp_path, spelling, yes):
    assert_a_dry_run_passed_through_ends_at_the_plan(run_entry, tmp_path,
                                                     spelling, yes)


@pytest.mark.parametrize("how", DECLARATIONS)
def test_the_naming_check_hears_what_is_passed_through(tmp_path, how):
    assert_the_naming_check_hears_what_is_passed_through(run_entry, tmp_path,
                                                         how)


# --- #608, on an interpreter alone: each is `conftest`'s helper of that name -

def test_a_parent_nobody_can_write_in_is_refused(tmp_path):
    assert_a_parent_nobody_can_write_in_is_refused(run_entry, tmp_path)


def test_a_plan_that_never_printed_could_not_be_produced_end_to_end(tmp_path):
    assert_a_plan_that_never_printed_could_not_be_produced(run_entry, tmp_path)


@pytest.mark.parametrize("how", CHAIN_LINK_TREES)
def test_step_four_reads_a_chain_as_the_plan_does(tmp_path, how):
    assert_step_four_reads_a_chain_as_the_plan_does(run_entry, tmp_path, how)


def test_an_empty_pin_source_is_the_plans_to_refuse(tmp_path):
    assert_an_empty_pin_source_is_the_plans_to_refuse(run_entry, tmp_path)


def test_a_chain_of_one_link_has_no_source_to_note(tmp_path):
    assert_a_chain_of_one_link_has_no_source_to_note(run_entry, tmp_path)


@pytest.mark.parametrize("org", UPSTREAM_CASINGS)
def test_the_upstream_org_is_refused_in_any_case(tmp_path, org):
    assert_the_upstream_org_is_refused_in_any_case(run_entry, tmp_path, org)


def test_an_upstream_origin_in_any_case_needs_an_org(tmp_path):
    assert_an_upstream_origin_in_any_case_needs_an_org(run_entry, tmp_path)


# --- setup.sh is a shim, not a second flag list -----------------------------

#: The only flags `setup.sh` may still NAME, and why each of them is about the
#: checkout the SHIM ITSELF makes rather than about the run: it clones
#: (`--quiet`, `--depth`), it may pin a ref (`--shape-ref`), it owns the
#: directory it cloned into (`--keep-shape-checkout`), it asks git one
#: question (`--show-toplevel`), and it tells the child where the person was
#: standing (`--into`). And `--help` since #341, which decides whether there
#: is a checkout to make AT ALL: outside one, the shim answers it itself with
#: a few lines that list no flag, rather than cloning the standard to print
#: this file's usage. THE EXCUSE IS FOR TWO PLACES, NOT FOR THE SPELLING:
#: those few lines and the one case label, both pinned below.
SHIM_FLAGS = {"--quiet", "--depth", "--show-toplevel", "--into", "--shape-ref",
              "--keep-shape-checkout", "--help"}

#: THE ONE SPELLING IN `setup.sh` THAT LOOKS LIKE A FLAG AND IS NOT ONE.
#: `xcode-select --install` is APPLE'S command, inside the Darwin sentence
#: both of the shim's refusals carry since #59, and the regex below cannot
#: tell a command quoted in a message from a flag a parser reads. Named here
#: rather than dropped from the regex, so a `--install` that ever DID mean
#: something to this shim would still have to be argued for.
SHIM_TEXT_ONLY = {"--install"}

#: The three lines a person READS during a self-bootstrap: printed by
#: `setup.sh` when the shim makes the checkout, and by this file when it makes
#: its own. Same run, same words, whichever entry point was typed.
SELF_BOOTSTRAP_LINES = ("(0) self-bootstrap", "  checkout: ",
                        "kept the shape checkout: ")


def test_setup_sh_parses_no_flags_of_its_own():
    """#50: there is ONE flag list, and `setup.sh` is not a second one.

    What this replaces held the two usage BANNERS together and asserted they
    agreed. They can no longer disagree: there is one banner, in this file,
    and `setup.sh` execs this file to print it. What can still go wrong is the
    other direction - a `--project`, a `--visibility`, a `--yes` reappearing
    in the shim is a second implementation growing back one argument at a
    time, and the person who found out would be whoever typed the flag into
    one entry point and not the other.

    COMMENT LINES ARE STRIPPED FIRST. The shim's header quotes the `curl ...
    | bash -s -- --org <your-org> --project Atlas` one-liner, which is the
    README's line and not a flag this file's subject parses.

    A SECOND, NARROWER ASSERTION GUARDS SHORT FLAGS TOO. The regex above only
    catches a re-grown DOUBLE-dash flag; a single-dash one (`-y` for `--yes`,
    `-h` for `--help`) is invisible to it. Widening the regex to catch every
    single-dash token would have to carve out every genuine one the shim
    already uses - `-c` (the Python version probe), `-C`/`-n`/`-f`/`-d` (git,
    test and mktemp options about the checkout) - which is more surface than
    it is worth. Checking for the exact CASE LABEL shapes a re-grown `--yes`
    or `--help` would need is simpler and just as honest.
    """
    code = "\n".join(line for line in
                     SETUP_SH.read_text(encoding="utf-8").splitlines()
                     if not line.lstrip().startswith("#"))
    named = (set(re.findall(r"--[a-z][a-z0-9-]*", code))
             - SHIM_FLAGS - SHIM_TEXT_ONLY)
    assert not named, (
        "setup.sh names flags of its own; it delegates to setup-project.py "
        f"and parses nothing: {sorted(named)}")
    # SHIM_TEXT_ONLY EXCUSES A SPELLING, NOT A LOCATION. `--install` is
    # excused because it is Apple's command quoted inside a refusal string;
    # excusing it as a bare token would excuse a real `--install)` case
    # equally, which is the one thing this test exists to catch. So the
    # excuse is tied to the two words it was granted for: every `--install`
    # in this file must be the one in `xcode-select --install`.
    assert (len(re.findall(r"--install\b", code))
            == len(re.findall(r"xcode-select --install\b", code))), (
        "setup.sh names --install somewhere other than inside "
        "`xcode-select --install`; SHIM_TEXT_ONLY excuses that spelling only "
        "as Apple's command quoted in a message")
    for label in ("-y)", "-h)", "--yes)"):
        assert label not in code, (
            f"setup.sh defines a case label {label!r} - a parser growing "
            "back one flag at a time")
    # THE HELP IS THE ONE LABEL ALLOWED (#341), spelled exactly once and
    # exactly so: section 0's scan answers `-h` and `--help` together
    # outside a checkout, before any clone. A second `--help)` anywhere, or
    # a help label of another shape, is a parser growing back after all.
    assert code.count("--help)") == code.count("-h|--help)") == 1, (
        "setup.sh's one help label must be section 0's `-h|--help)`, once")
    # ...AND EVERY OTHER `--help` IS THE SHIM'S OWN TEXT, which is `say`
    # lines and nothing else. `SHIM_FLAGS` excuses a SPELLING, and a second
    # reader needs no case label to be one: a quoted `"--help")`, a
    # `[[ $1 == --help ]]` in the developer path or inside the scan, or a
    # `--help` read from a command substitution inside a `say`. So the
    # spelling is excused in exactly two places, the text and the label, and
    # the text is held to one double-quoted string per line, with no command
    # substitution, no `${...}` and no backtick in it.
    text = re.search(r"^shim_help\(\) \{\n(.*?)^\}\n", code,
                     re.MULTILINE | re.DOTALL)
    assert text, "setup.sh no longer defines shim_help()"
    prints_only = re.compile(r'say "(?:[^"\\`$]|\\.|\$(?![({]))*"')
    assert all(prints_only.fullmatch(line.strip())
               for line in text.group(1).splitlines()), (
        "shim_help() does something other than print its text: every line "
        "must be one `say \"...\"` with no command substitution in it")
    rest = code.replace(text.group(0), "")
    assert rest.count("--help") == rest.count("-h|--help)") == 1, (
        "setup.sh reads --help somewhere other than section 0's one label")
    assert len(re.findall(r"(?<![\w-])-h(?![\w-])", rest)) == 1, (
        "setup.sh reads -h somewhere other than section 0's one label")


def test_the_shim_names_the_command_line_tools_on_a_mac():
    """#59: both of the shim's refusals carry a Darwin-only sentence.

    A bare Mac dies in `find_python`, NOT on the git probe: since macOS 12.3
    `/usr/bin/git` and the interpreter beside it are Command Line Tools
    stubs, so the name is found, the version probe fails, and the interpreter
    refusal fires first. One Apple command answers both, so both refusals
    name it - and only name it. It opens a dialog no script can answer, and
    printing one sentence buys the same outcome as running it.

    The OFFERS stay in `setup-project.py`. An offer table transcribed into
    bash here would be the duplication #50 removed, growing back.
    """
    shim = SETUP_SH.read_text(encoding="utf-8")
    assert 'case "$(uname -s' in shim, "the sentence is not Darwin-only"
    assert "xcode-select --install" in shim
    carriers = [line for line in shim.splitlines() if "$MAC_TOOLS" in line]
    assert len(carriers) == 2, (
        "the Command Line Tools sentence must reach BOTH refusals and "
        f"nothing else: {carriers}")
    assert any("git is not installed" in line for line in carriers)
    assert any("no Python 3.9 or newer" in line for line in carriers)
    for offered in ("brew install", "apt-get", "winget", "read -r"):
        assert offered not in shim, (
            "the offer table has grown back into the shim; it lives in "
            "setup-project.py, which is the flow")


def test_the_two_entry_points_say_self_bootstrap_the_same_way():
    """One flag list is not enough on its own: the shim still PRINTS.

    Section 0 is the one part of the run that exists twice - transcribed into
    bash in `setup.sh` and written in Python here - because it is what happens
    before there is a checkout to run Python from. A person reading the output
    of a `curl | bash` run and a person reading the output of
    `py setup-project.py` are reading a report of the same three moments, and
    a wording that drifted in one file would make two standards out of one.
    """
    shim = SETUP_SH.read_text(encoding="utf-8")
    entry = SETUP_PROJECT.read_text(encoding="utf-8")
    for line in SELF_BOOTSTRAP_LINES:
        assert line in shim, f"setup.sh no longer prints {line!r}"
        assert line in entry, f"setup-project.py no longer prints {line!r}"


# --- every question at the person's own terminal (#492) ---------------------
#
# `curl … | bash -s --` hands this file the rest of `setup.sh` as its stdin,
# so every question - the project name, each install offer, the one `yes` -
# is asked at the CONTROLLING terminal when stdin is not a terminal, and an
# answer is never read from the pipe. With no controlling terminal at all, as
# in an AI assistant's shell, nothing is asked and the run refuses as #476
# words it. The one-liner itself, through `setup.sh`, is driven in
# `tests/test_setup_sh.py`.


def test_every_question_is_asked_through_one_helper():
    """`ask` is the one function that reads an answer and `can_ask` the one
    gate: nothing else calls `input` or decides for itself whether stdin is a
    terminal, and nothing reads stdin at all. A prompt with a gate of its own
    is how one of them came to read the pipe, or to refuse where the others
    ask."""
    source = SETUP_PROJECT.read_text(encoding="utf-8")
    readers, deciders = set(), set()
    for node in ast.parse(source).body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for inner in ast.walk(node):
            if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
                    and inner.func.id == "input"):
                readers.add(node.name)
            if (isinstance(inner, ast.Attribute) and inner.attr == "isatty"
                    and isinstance(inner.value, ast.Attribute)
                    and inner.value.attr == "stdin"):
                deciders.add(node.name)
    assert readers == {"ask"}, f"these read an answer themselves: {readers}"
    assert deciders == {"can_ask", "ask", "run_at_the_terminal"}, (
        f"these decide for themselves whether there is a terminal: {deciders}")
    assert "stdin.read" not in source, "stdin is read somewhere"


def test_a_controlling_terminal_that_is_a_file_never_answers(monkeypatch,
                                                             tmp_path):
    """Whether a thing is a terminal is the device's answer, not its name's:
    a `/dev` populated by hand - a chroot, a container image - can hold a
    regular FILE called `tty`, and a file holding `yes` is nobody's answer.
    So there is no terminal, and the one `yes` refuses as #476 words it."""
    module = entry_point_module()
    planted = tmp_path / "tty"
    planted.write_bytes(b"yes\nyes\n")
    monkeypatch.setattr(sys, "stdin", _NoTerminal())
    monkeypatch.setattr(module, "CONTROLLING_TERMINAL", str(planted))
    assert module.open_terminal() is None
    assert module.can_ask() is False
    assert module.ask("Type yes to continue: ") == ""
    monkeypatch.setattr(module, "run", lambda *a, **k: subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr=""))
    opts = module.parse_args(["--project", "Sample", "--org", "demoorg"],
                             str(tmp_path))
    with pytest.raises(module.Refusal) as refused:
        module.plan_and_confirm(opts, REPO, "demoorg", [],
                                str(tmp_path / "Sample"))
    assert refused.value.code == 2
    assert_refuses_for_want_of_a_terminal(str(refused.value))


def test_a_yes_down_the_pipe_with_no_terminal_still_refuses(tmp_path):
    """An assistant's shell that pipes `yes` in: no controlling terminal, so
    nobody is there to ask, and the pipe is not somebody. It refuses with the
    route (#476) and creates nothing - on every platform."""
    result = run_entry("--project", "Sample", "--org", "demoorg",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"), stdin="yes\nyes\n")
    assert result.returncode == 2, result.stderr + result.stdout
    assert "--dry-run: nothing was created." in result.stdout
    assert_refuses_for_want_of_a_terminal(result.stderr)
    assert not (tmp_path / "remotes").exists()


def terminal_env() -> dict:
    """The environment of a run in a terminal: the suite's identity, and a
    `gh` that reaches nothing were one asked."""
    env = dict(os.environ)
    env.setdefault("GIT_AUTHOR_NAME", "openRepoShape tests")
    env.setdefault("GIT_AUTHOR_EMAIL", "tests@openreposhape.invalid")
    env.setdefault("GIT_COMMITTER_NAME", "openRepoShape tests")
    env.setdefault("GIT_COMMITTER_EMAIL", "tests@openreposhape.invalid")
    env["GH_TOKEN"] = "bogus"
    return env


def piped(text: str, *args: str) -> list:
    """This file run with `text` on its stdin, from a pipe, as `curl |
    bash` runs it: everything else is the terminal's."""
    return ["sh", "-c", 'text=$1; shift; printf "%s" "$text" | "$0" "$@"',
            sys.executable, text, str(SETUP_PROJECT), *args]


@PTY_SKIP
def test_a_yes_down_the_pipe_is_never_an_answer(tmp_path):
    """The pipe on stdin holds `yes`, the person types `no` at the terminal:
    the terminal's answer is the one taken, and nothing is created."""
    status, screen, answered = run_in_a_terminal(
        piped("yes\nyes\n", "--project", "Sample", "--org", "demoorg",
              "--local-remote-dir", str(tmp_path / "remotes"),
              "--into", str(tmp_path / "work")),
        cwd=REPO, env=terminal_env(), answers=["no\n"])
    assert answered == 1, f"it never asked at the terminal:\n{screen}"
    assert status == 1, screen
    assert "REFUSED: not confirmed; nothing was created." in screen
    assert not (tmp_path / "remotes").exists()


@PTY_SKIP
def test_a_missing_project_is_asked_for_at_the_terminal(tmp_path):
    """The project name is a question too, and the same helper asks it: at
    the terminal, though stdin is a pipe, and the name typed there is the one
    the plan names. The `no` after it creates nothing."""
    status, screen, answered = run_in_a_terminal(
        piped("", "--org", "demoorg",
              "--local-remote-dir", str(tmp_path / "remotes"),
              "--into", str(tmp_path / "work")),
        cwd=REPO, env=terminal_env(), answers=["Sample\n", "no\n"],
        prompt=["project name (ONE CamelCase token, e.g. Atlas): ",
                "Type yes to continue:"])
    assert answered == 2, f"it never asked at the terminal:\n{screen}"
    assert "project      Sample" in screen, screen
    assert status == 1, screen
    assert "REFUSED: not confirmed; nothing was created." in screen
    assert not (tmp_path / "remotes").exists()


def assert_refuses_on_a_terminal_it_cannot_answer_on(tmp_path, **how):
    """A terminal that opens is not always one the run can be answered on.
    Here the run has one, and stdin is a pipe holding `yes`; `how` says what
    is wrong with the terminal (`raw`, or `background`, as
    `run_in_a_terminal` spells them). Setup must not draw the prompt at it:
    it refuses with the route as it does with no terminal at all (#476) and
    creates nothing. The wait is 30 s, so that a run that asks anyway FAILS
    with its screen instead of waiting for a person who cannot answer."""
    status, screen, _ = run_in_a_terminal(
        piped("yes\nyes\n", "--project", "Sample", "--org", "demoorg",
              "--local-remote-dir", str(tmp_path / "remotes"),
              "--into", str(tmp_path / "work")),
        cwd=REPO, env=terminal_env(), timeout=30, **how)
    assert "Type yes to continue" not in screen, (
        f"it asked at a terminal nobody can answer on:\n{screen}")
    assert "Traceback" not in screen, screen
    assert status == 2, f"status {status}:\n{screen}"
    assert "--dry-run: nothing was created." in screen
    assert_refuses_for_want_of_a_terminal(
        screen[screen.index("REFUSED"):])
    assert not (tmp_path / "remotes").exists()
    assert not (tmp_path / "work").exists()


@PTY_SKIP
def test_a_terminal_in_raw_mode_is_no_terminal_to_ask_on(tmp_path):
    """An assistant's full-screen interface owns the pane in raw mode, and
    its tool shell shares that terminal: the person's Enter is a carriage
    return there, so a read for the end of a line never ends, nothing is
    echoed, and the run waits for the assistant's timeout with the route
    unseen. A terminal that reads no whole lines is no terminal to ask on."""
    assert_refuses_on_a_terminal_it_cannot_answer_on(tmp_path, raw=True)


@PTY_SKIP
def test_a_background_process_group_is_no_terminal_to_ask_on(tmp_path):
    """`cat setup.sh | timeout N bash -s -- ...` typed in a shell, or any
    runner that backgrounds a job sharing the terminal: a read of the
    terminal from a background process group stops the run on SIGTTIN, and it
    stays stopped. A terminal the run is not in the foreground of is no
    terminal to ask on. Typed without the pipe the run's stdin IS the
    terminal, and it never reaches this check."""
    assert_refuses_on_a_terminal_it_cannot_answer_on(tmp_path,
                                                     background=True)


class _HungUpOs:
    """`os`, as `ask` uses it, over a terminal that opened and whose read now
    fails with EIO: the last process of its group orphaned, SIGTTIN ignored,
    or the terminal hung up."""

    def __init__(self):
        self.closed = []

    def write(self, descriptor, data):
        return len(data)

    def read(self, descriptor, count):
        raise OSError(5, "Input/output error")

    def close(self, descriptor):
        self.closed.append(descriptor)


def test_a_terminal_whose_read_fails_is_the_end_of_the_answer(monkeypatch):
    """EIO from the read is end of input, never a traceback: the answer is an
    empty line, which no question takes for a yes, and the terminal is closed
    all the same."""
    module = entry_point_module()
    hung_up = _HungUpOs()
    monkeypatch.setattr(sys, "stdin", _NoTerminal())
    monkeypatch.setattr(module, "open_terminal", lambda: 7)
    monkeypatch.setattr(module, "os", hung_up)
    assert module.ask("Type yes to continue: ") == ""
    assert hung_up.closed == [7]


# --- #661 (L2-75): step (4) speaks in the plan's words ----------------------

@pytest.mark.parametrize("passthrough,spoken", [
    # A chain of two links at least: the label, and each HOLDER's words, in
    # the scaffold's own (`shape_materialize.scaffold_link_remedies`).
    (["--referent-chain", "openXdox,openDox"],
     ["--referent-chain=openXdox,openDox", "--link-source-label=--pin-source",
      "--link-remedy=openxdox=SHAPE_PIN_SOURCE_OPENXDOX, or a --pin-source "
      "clone of openXdox that holds its project.yaml, would let it be read"]),
    (["--referent-chain", "openXdox,openYdox,openDox", "--pin-source", "src"],
     ["--referent-chain=openXdox,openYdox,openDox", "--link-source=src",
      "--link-source-label=--pin-source",
      "--link-remedy=openxdox=SHAPE_PIN_SOURCE_OPENXDOX, or a --pin-source "
      "clone of openXdox that holds its project.yaml, would let it be read",
      "--link-remedy=openydox=SHAPE_PIN_SOURCE_OPENYDOX would let it be "
      "read"]),
    # ...read as the scaffold reads the chain: blanks dropped, the last kept.
    (["--referent-chain", "openXdox, ,openDox"],
     ["--referent-chain=openXdox, ,openDox",
      "--link-source-label=--pin-source",
      "--link-remedy=openxdox=SHAPE_PIN_SOURCE_OPENXDOX, or a --pin-source "
      "clone of openXdox that holds its project.yaml, would let it be read"]),
    # A chain of one link has no holder, so nothing is said for it.
    (["--referent-chain", "openDox", "--pin-source", "src"],
     ["--referent-chain=openDox"]),
    (["--referent-chain", "openXdox,openDox", "--referent-chain", " , "],
     ["--referent-chain= , "]),
    ([], [])])
def test_each_holder_is_given_the_plans_words(passthrough, spoken):
    """#661, L2-75: with the scaffold's words, step (4) tells the naming
    check `--pin-source` is the flag and what each holder is offered."""
    module = entry_point_module()
    assert module.naming_declarations(
        passthrough, REPO, shape_materialize.scaffold_link_remedies
    ) == as_named_by_the_plan(spoken)


def test_step_four_and_the_plan_share_one_set_of_words():
    """ONE definition: setup asks the checkout's `shape_materialize` for the
    words the scaffold's own `_link_remedies` is."""
    module = entry_point_module()
    assert module.scaffold_link_remedies(REPO) is (
        shape_materialize.scaffold_link_remedies)
    scaffold = load_without_bytecode(REPO / "scaffold-project.py",
                                     "scaffold_for_setup_words")
    assert scaffold._link_remedies is shape_materialize.scaffold_link_remedies


@pytest.mark.parametrize("case", STEP_FOUR_WORDS)
def test_step_four_speaks_in_the_plans_words(tmp_path, monkeypatch, case):
    assert_step_four_speaks_in_the_plans_words(run_entry, tmp_path,
                                               monkeypatch, case)


# --- #907 (U061, U169): step (4) reads no checkout beside the standard ------

#: What step (4) runs, out of this checkout: the naming check, the library
#: it imports and the policy it finds beside itself.
NAMING_CHECK_FILES = ("scripts/validate-repository-naming.py",
                      "scripts/repo_shape.py",
                      "contracts/repository-naming.yaml")


def declaring(tree: Path, pin: str) -> Path:
    """`tree`, a chain link's checkout as the naming check reads one: a
    `project.yaml` that declares a pin on `pin`."""
    tree.mkdir(parents=True)
    (tree / "project.yaml").write_bytes(
        ("schema_version: 1\nkind: project-manifest\n"
         f"neutral_product_pins:\n  - {pin}\n").encode("utf-8"))
    return tree


def test_step_four_reads_no_checkout_beside_the_standard(tmp_path,
                                                         monkeypatch, capfd):
    """The issue's own row: a standard whose parent folder holds `openXdox/`
    declaring `openDox`, and a `--pin-source` declaring `openYdox`, with the
    chain `openXdox,openYdox,openDox`. Step (5) reads no checkout beside
    anything, so it reads the `--pin-source` tree for `openXdox` and the
    name is a descendant through the chain. On main step (4) ran the naming
    check from the standard's checkout, which read `openXdox/` beside it
    first: the `--pin-source` tree was "not used" and the chain broken,
    exit 1. It runs from an empty folder now, inside a temporary folder
    holding nothing else, and the temporary folders are made in that same
    parent, so a run from an empty folder with the parent beside it would
    read `openXdox/` too. Both are gone when the check is done."""
    clear_ambient_pin_sources(monkeypatch)
    module = entry_point_module()
    parent = tmp_path / "parent"
    standard = parent / "standard"
    for name in NAMING_CHECK_FILES:
        (standard / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / name, standard / name)
    declaring(parent / "openXdox", "openDox")
    source = declaring(tmp_path / "source", "openYdox")
    monkeypatch.setattr(tempfile, "tempdir", str(parent))
    declared = module.naming_declarations(
        ["--pin", f"openXdox@{A_COMMIT}",
         "--referent-chain", "openXdox,openYdox,openDox",
         "--pin-source", str(source)],
        standard, shape_materialize.scaffold_link_remedies)
    module.check_names(standard, "codexDox", "", declared)
    said = capfd.readouterr()
    heard = said.out + said.err
    assert "codexDox: domain-descendant" in said.out, heard
    assert ("CHAIN openXdox → openYdox → openDox   "
            "[declared-unverified]") in said.out, heard
    assert "broken" not in heard, heard
    assert "NOTE" not in heard, heard
    assert sorted(entry.name for entry in parent.iterdir()) == [
        "openXdox", "standard"]


#: Why no folder could be made for the naming check, and the reason step
#: (4)'s refusal gives for it: any `OSError`, with its `strerror`, or its
#: class's name where it has none (rv949 on #949: S1, S3).
NO_FOLDER = {
    "permission-denied": (PermissionError(errno.EACCES, "Permission denied"),
                          "Permission denied"),
    "no-such-folder": (FileNotFoundError(errno.ENOENT,
                                         "No such file or directory"),
                       "No such file or directory"),
    "no-reason": (OSError("odd"), "OSError"),
}


def no_empty_folder(reason: str) -> str:
    """Step (4)'s refusal where no folder could be made, for `reason`."""
    return ("the naming check runs from an empty folder, and none could be "
            f"made in the temporary folder ({reason}), so nothing was "
            "created. Point TMPDIR (TEMP on Windows) at a folder you can "
            "write in, then run this again.")


@pytest.mark.parametrize("case", NO_FOLDER)
def test_step_four_without_an_empty_folder_is_refused_with_the_way_on(
        monkeypatch, case):
    """No empty folder can be made for the naming check to run from: a
    refusal naming the system's reason and the way on, before anything
    exists, and no naming check is run. Not a traceback."""
    module = entry_point_module()
    runs = _Runs()
    monkeypatch.setattr(module, "run", runs)
    raised, reason = NO_FOLDER[case]

    def no_folder(*_args, **_kwargs):
        raise raised

    monkeypatch.setattr(module.tempfile, "mkdtemp", no_folder)
    with pytest.raises(module.Refusal) as refused:
        module.check_names(REPO, "Sample")
    assert refused.value.code == 2
    assert str(refused.value) == no_empty_folder(reason)
    assert runs.calls == [], f"something was run: {runs.calls}"


class _OsWith:
    """This process's `os`, with the functions named replaced, for the
    module under test alone, as `_OsNamed` answers `name`: `tempfile`, which
    makes the temporary folder, keeps the real ones."""

    def __init__(self, **replaced) -> None:
        self.__dict__.update(replaced)

    def __getattr__(self, attr):
        return getattr(os, attr)


def test_step_four_takes_its_folder_away_when_it_cannot_make_one_inside(
        tmp_path, monkeypatch):
    """The temporary folder was made and the empty folder inside it was
    not: the same refusal, no naming check run, and the temporary folder
    taken away again (rv949 on #949, S2). It was left to
    `TemporaryDirectory`'s finalizer, a `ResourceWarning` at exit."""
    module = entry_point_module()
    runs = _Runs()
    monkeypatch.setattr(module, "run", runs)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

    def no_room(path, *_args, **_kwargs):
        raise OSError(errno.ENOSPC, "No space left on device", path)

    monkeypatch.setattr(module, "os", _OsWith(mkdir=no_room))
    with pytest.raises(module.Refusal) as refused:
        module.check_names(REPO, "Sample")
    assert str(refused.value) == no_empty_folder("No space left on device")
    assert runs.calls == [], f"something was run: {runs.calls}"
    assert list(tmp_path.iterdir()) == []


def test_step_four_names_a_folder_it_cannot_take_away(tmp_path, monkeypatch,
                                                     capfd):
    """SHOULD-1 (rv949 on #949): a folder that cannot be taken away once the
    names are judged, as on Windows while an indexer or an antivirus holds a
    handle on it, is a `[??]` naming it, and step (4) goes on. Under
    `TemporaryDirectory` it was a `PermissionError` traceback out of
    `check_names`, which `main` does not catch."""
    module = entry_point_module()
    ran = []

    def run(argv, cwd=None, capture=False, stdin=None, env=None):
        ran.append(cwd)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(module, "run", run)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    held = ("The process cannot access the file because it is being used by "
            "another process")

    def in_use(path, *_args, **_kwargs):
        raise PermissionError(errno.EACCES, held, path)

    monkeypatch.setattr(module, "os", _OsWith(rmdir=in_use))
    assert module.check_names(REPO, "Sample") is None
    [aside] = tmp_path.iterdir()
    assert ran == [os.path.join(str(aside), "here")]
    assert [entry.name for entry in aside.iterdir()] == ["here"]
    assert capfd.readouterr().err == (
        f"  [??] {aside}, the folder made in the temporary folder for the "
        f"naming check to run from, could not be taken away again ({held}); "
        "setup put nothing in it but an empty folder, and it is yours to "
        "delete.\n")


# --- #907, rv949 on #949 (MUST-1): a relative SHAPE_PIN_SOURCE_<LINK> -------

#: `SHAPE_PIN_SOURCE_OPENYDOX` names `openYdox`'s tree relative to the
#: standard's checkout, and `--pin-source` is `openXdox`'s, declaring
#: `openYdox`: each case's project, chain, what `openYdox`'s tree declares,
#: and the verdict on the chain that steps (4) and (5) both give.
RELATIVE_VARIABLE = {
    "verified": ("codexDox", "openXdox,openYdox,openDox", "openDox",
                 "verified"),
    "breaking": ("codexInk", "openXdox,openYdox,openInk", "openZdox",
                 "broken"),
}


def step_four_verdict(step_four: str) -> str:
    """What step (4)'s naming check says of the assembly root's chain: the
    status its first `CHAIN` line ends with."""
    statuses = re.findall(r"^\s*CHAIN .*\[([a-z-]+)\]$", step_four,
                          re.MULTILINE)
    return statuses[0] if statuses else "no CHAIN line"


def step_five_verdict(plan: str, stderr: str) -> str:
    """What step (5)'s plan says of the chain: broken where it refused it,
    declared-unverified where it warned so, and verified where its
    `declared` line reaches the referent through the chain and says
    neither."""
    if "REFUSED chain-not-declared:" in stderr:
        return "broken"
    if "WARNING declared-unverified:" in stderr:
        return "declared-unverified"
    declared = [line for line in plan.splitlines()
                if line.startswith("declared     ")]
    if declared and "through the declared pin chain" in declared[0] and (
            "declared-unverified" not in declared[0]):
        return "verified"
    return "no verdict"


@pytest.mark.parametrize("case", RELATIVE_VARIABLE)
def test_step_four_reads_a_relative_variable_where_step_five_does(
        tmp_path, monkeypatch, case):
    """MUST-1: step (5) reads a relative `SHAPE_PIN_SOURCE_<LINK>` from the
    standard's checkout, the folder the scaffold runs in, and step (4) now
    reads it there too (`pin_sources_joined`), so the two steps give the
    chain one verdict. Read from the empty folder step (4) runs in, the
    variable named nothing: the chain step (5) verified was
    `[declared-unverified]` in step (4), which offered the variable that
    was set, and the chain step (5) refused as `chain-not-declared` passed
    step (4) as a descendant. On main step (4) ran in the checkout and
    agreed. The variable is the path from this checkout to the tree, which
    leaves it by `..`."""
    clear_ambient_pin_sources(monkeypatch)
    project, chain, declares, verdict = RELATIVE_VARIABLE[case]
    first = declaring(tmp_path / "openXdox", "openYdox")
    git("init", "-q", "-b", "main", cwd=first)
    git("add", "project.yaml", cwd=first)
    git("commit", "-q", "-m", "seed", cwd=first)
    commit = git("rev-parse", "HEAD", cwd=first).stdout.strip()
    later = declaring(tmp_path / "yy", declares)
    try:
        relative = os.path.relpath(later.resolve(), REPO.resolve())
    except ValueError:
        pytest.skip("the temporary folder is on another drive than this "
                    "checkout, so no relative path leads from one to the "
                    "other")
    result = run_entry("--project", project, "--org", "demoorg",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"),
                       "--", "--pin", f"openXdox@{commit}",
                       "--referent-chain", chain, "--pin-source", str(first),
                       "--dry-run",
                       extra_env={"SHAPE_PIN_SOURCE_OPENYDOX": relative})
    heard = result.stdout + result.stderr
    assert not os.path.isabs(relative), relative
    assert "(5) the plan" in result.stdout, heard
    step_four, _, plan = result.stdout.partition("(4) naming policy")[
        2].partition("(5) the plan")
    assert step_four_verdict(step_four) == step_five_verdict(
        plan, result.stderr) == verdict, heard
    assert "SHAPE_PIN_SOURCE_OPENYDOX would let it be read" not in heard, (
        heard)
    assert "link-source-unreadable" not in result.stderr, result.stderr
    assert not (tmp_path / "remotes").exists()


def test_only_a_pin_source_variable_that_names_a_path_is_joined():
    """`pin_sources_joined` joins a relative `SHAPE_PIN_SOURCE_<LINK>` to the
    standard's checkout and leaves an absolute one as it is. An empty one
    stays empty: neither step reads it, and joined it would name the
    checkout itself. Every other variable is handed on as it is, one whose
    name only holds the prefix too."""
    module = entry_point_module()
    elsewhere = str(Path(REPO, os.pardir, "elsewhere").resolve())
    relative = os.path.join(os.pardir, "yy")
    unjoined = {"SHAPE_PIN_SOURCE_OPENXDOX": elsewhere,
                "SHAPE_PIN_SOURCE_OPENDOX": "",
                "PYTHONIOENCODING": "utf-8:backslashreplace",
                "NOT_SHAPE_PIN_SOURCE_OPENYDOX": relative}
    assert module.pin_sources_joined(REPO, {
        "SHAPE_PIN_SOURCE_OPENYDOX": relative, **unjoined}) == {
        "SHAPE_PIN_SOURCE_OPENYDOX": os.path.join(str(REPO), relative),
        **unjoined}


@pytest.mark.parametrize("raised", [
    pytest.param(RuntimeError("Symlink loop from 'loop'"), id="runtime-error"),
    pytest.param(OSError(errno.ELOOP, "Too many levels of symbolic links"),
                 id="os-error"),
])
def test_a_pin_source_that_cannot_be_resolved_goes_joined(monkeypatch,
                                                          raised):
    """Where `resolve()` fails, as on a symlink loop, the `--pin-source` goes
    to the naming check joined to the standard's checkout and unresolved,
    and step (4) goes on: the scaffold names it as typed then
    (`_resolved_pin_source`), and a path the naming check is given has to
    be absolute (rv949 on #949, S4)."""
    module = entry_point_module()

    def cannot(self, strict=False):
        raise raised

    monkeypatch.setattr(module.Path, "resolve", cannot)
    assert module.as_the_plan_reads_it(REPO, "loop") == str(Path(REPO,
                                                                 "loop"))
