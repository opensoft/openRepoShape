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
import importlib.util
import os
import re
import shutil
import subprocess
import sys

from pathlib import Path

import pytest

from conftest import REPO, git, rmtree

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
        cwd=str(cwd) if cwd is not None else str(REPO), env=env)


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
    assert "visibility: internal" in manifest


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
    assert "no terminal to confirm on" in result.stderr
    assert not (tmp_path / "remotes").exists()


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


def test_anything_but_yes_refuses_and_creates_nothing(monkeypatch, tmp_path):
    """The one `yes` is EXACT: `no`, `y`, `Yes` and an empty line all refuse.

    Driven in-process rather than through `run_entry` because the prompt only
    happens when stdin is a terminal, and there is no portable way to hand a
    subprocess one - `pty` is POSIX-only and this suite runs on Windows, which
    is the platform this entry point is for. What is asserted is the ruling
    itself: anything but exactly `yes` is exit 1 and nothing was created.
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
    for answer in ("no", "y", "Yes", ""):
        monkeypatch.setattr(module, "ask", lambda prompt, a=answer: a)
        with pytest.raises(module.Refusal) as refused:
            module.plan_and_confirm(opts, REPO, "demoorg", [])
        assert refused.value.code == 1, answer
        assert "not confirmed; nothing was created." in str(refused.value)
    monkeypatch.setattr(module, "ask", lambda prompt: "yes")
    module.plan_and_confirm(opts, REPO, "demoorg", [])


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
# a name. `scaffold-project.py` refuses the same shape in the same words
# (`tests/test_scaffold_pin_and_reuse.py`), through `repo_shape.checked_value`;
# this file's subject carries its own copy because it runs BEFORE there is a
# checkout to import that from, which is the whole of self-bootstrap mode.
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


@pytest.mark.parametrize("ref", ["a b", "a..b", "topic.lock", "-x"])
def test_a_shape_ref_that_is_not_a_ref_is_refused(tmp_path, ref):
    """`--shape-ref` becomes `git checkout <ref>` in the temporary checkout.

    A space is not in any ref name; `..` is a revision RANGE rather than a
    ref; `.lock` is what git calls the lock file it writes beside one; and a
    leading `-` is an option to git.
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
    does - and what the README's Windows path deliberately does NOT do."""
    env = dict(os.environ)
    env.setdefault("GIT_AUTHOR_NAME", "openRepoShape tests")
    env.setdefault("GIT_AUTHOR_EMAIL", "tests@openreposhape.invalid")
    env.setdefault("GIT_COMMITTER_NAME", "openRepoShape tests")
    env.setdefault("GIT_COMMITTER_EMAIL", "tests@openreposhape.invalid")
    return subprocess.run(
        [sys.executable, "-", *args], capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False, env=env,
        input=SETUP_PROJECT.read_text(encoding="utf-8"), cwd=str(cwd))


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
    assert "no terminal to confirm on" in result.stderr
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


# --- setup.sh is a shim, not a second flag list -----------------------------

#: The only flags `setup.sh` may still NAME, and why each of them is about the
#: checkout the SHIM ITSELF makes rather than about the run: it clones
#: (`--quiet`, `--depth`), it may pin a ref (`--shape-ref`), it owns the
#: directory it cloned into (`--keep-shape-checkout`), it asks git one
#: question (`--show-toplevel`), and it tells the child where the person was
#: standing (`--into`).
SHIM_FLAGS = {"--quiet", "--depth", "--show-toplevel", "--into", "--shape-ref",
              "--keep-shape-checkout"}

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
    named = set(re.findall(r"--[a-z][a-z0-9-]*", code)) - SHIM_FLAGS
    assert not named, (
        "setup.sh names flags of its own; it delegates to setup-project.py "
        f"and parses nothing: {sorted(named)}")
    for label in ("-y)", "-h)", "--yes)", "--help)"):
        assert label not in code, (
            f"setup.sh defines a case label {label!r} - a parser growing "
            "back one flag at a time")


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
