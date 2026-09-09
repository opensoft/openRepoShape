# SPDX-License-Identifier: Apache-2.0
"""`make park` / `make resume`, in an assembly root and in a family holder.

The verbs are THIN by ruling (#77, Brett Heap 2026-09-09, ruling 1): the WIP
commit, the push, the `git worktree add`, the `.specify/feature.json` rewrite
and the soft reset belong to the SPECKIT GIT EXTENSION, and this standard
carries the two target names, the `ARGS` pass-through and one refusal that
names `setup-openspeckit`. So this file asserts exactly that much and nothing
about parking: the extension's own suite tests the mechanics, and a test here
that re-asserted them would be testing a copy of somebody else's contract.

NO NETWORK, NO REAL REPOSITORY, and no Speckit installation is needed: the
extension script is a STUB that echoes its arguments and exits with the code
the test chose, which is how the pass-through and the refusal are provable
offline. `make park ARGS=--dry-run` is the rehearsal the docs promise, so the
stub is what proves `--dry-run` arrives.

ONE THING MAKE CANNOT DO, said here because a reader will otherwise call it a
bug: GNU make reports ANY non-zero recipe status as its OWN exit 2 and prints
`Error <code>`. The extension's 1/2/3 therefore cannot come back out of
`make` as 1/2/3 — the Makefile neither swallows nor rewrites a code, and the
code is in make's own diagnostic, which is what these tests read. The
refusal's exit 2 is the one that happens to survive intact.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP, git, rmtree, run_script

sys.path.insert(0, str(REPO / "scripts"))
from shape_materialize import (COPIED_VERBATIM,  # noqa: E402
                               FAMILY_COPIED_FROM_SHAPE,
                               FAMILY_COPIED_VERBATIM)

MAKE = shutil.which("make")

#: Both reasons this whole file cannot run on a machine without a POSIX shell
#: and `make`: the recipes test for an executable and then exec a `#!`-shebang
#: script, and the holder half shells out to `make` a second time.
pytestmark = [
    WINDOWS_SKIP,
    pytest.mark.skipif(MAKE is None, reason="needs `make` on PATH"),
]

#: Where `setup-openspeckit` installs the git extension's bash scripts, and
#: therefore the path both targets test for. Written out here rather than
#: parsed out of the Makefile: a test that read the path from the file under
#: test would pass just as happily if the path were wrong.
OVERLAY = Path(".specify/extensions/git/scripts/bash")

VERBS = ("park", "resume")


def write_stub(root: Path, verb: str, code: int = 0, label: str = "") -> Path:
    """An executable stand-in for the extension's `<verb>.sh`."""
    script = root / OVERLAY / f"{verb}.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        f'#!/bin/sh\necho "{label or verb}.sh ran with: $*"\nexit {code}\n',
        encoding="utf-8")
    script.chmod(0o755)
    return script


def make(root: Path, *args: str) -> subprocess.CompletedProcess:
    """`make` in `root`, with this interpreter as `PYTHON`.

    `PYTHON=<sys.executable>` for the same reason `conftest.run_script` uses
    it: the suite must exercise the interpreter it is running under, not
    whichever `python3` happens to be first on PATH.
    """
    return subprocess.run([MAKE, *args, f"PYTHON={sys.executable}"],
                          cwd=str(root), capture_output=True, text=True,
                          check=False)


# --- the assembly root ------------------------------------------------------

@pytest.mark.parametrize("verb", VERBS)
def test_the_verb_refuses_by_name_when_the_overlay_is_not_installed(project,
                                                                   verb):
    """A scaffolded project has no `.specify/` at all, and the refusal has to
    say what to run — a target that failed with `No such file or directory`
    would leave the person to work out that the missing thing is installable
    and what installs it."""
    assert not (project / ".specify").exists(), "fixture: nothing installed"
    proc = make(project, verb)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert (f"make {verb} needs the Speckit worktree overlay; install it "
            "with: setup-openspeckit") in proc.stderr
    assert not (project / "worktrees").exists(), (
        "a refusal happens BEFORE anything: nothing may be created")


@pytest.mark.parametrize("verb", VERBS)
def test_the_verb_execs_the_extension_script_and_args_arrive(project, verb):
    """`ARGS` is the whole interface: `make park ARGS=--dry-run` is what the
    README and `AGENTS-shape.md` both tell a person to run first."""
    write_stub(project, verb)
    proc = make(project, verb, "ARGS=--dry-run")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert f"{verb}.sh ran with: --dry-run" in proc.stdout


@pytest.mark.parametrize("verb", VERBS)
def test_more_than_one_arg_arrives_in_order(project, verb):
    write_stub(project, verb)
    proc = make(project, verb, "ARGS=--feature 001-a --dry-run")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert f"{verb}.sh ran with: --feature 001-a --dry-run" in proc.stdout


@pytest.mark.parametrize("verb", VERBS)
def test_the_scripts_own_exit_code_is_neither_swallowed_nor_invented(project,
                                                                    verb):
    """0 comes back as 0, and the extension's PARTIAL 3 comes back as a
    FAILURE naming 3.

    The Makefile does not touch the code. Make flattens every non-zero to its
    own exit 2 (see this file's header), so what is asserted is the property
    that matters: a script that refused is never reported as success, and the
    code it chose is still on screen.
    """
    write_stub(project, verb, code=0)
    assert make(project, verb).returncode == 0

    write_stub(project, verb, code=3)
    proc = make(project, verb)
    assert proc.returncode != 0, "a PARTIAL run must not read as success"
    assert re.search(r"(Error|code) 3\b", proc.stderr), (
        f"make's own diagnostic must carry the script's code:\n{proc.stderr}")


def test_help_names_both_verbs_and_the_rehearsal(project):
    proc = make(project, "help")
    assert proc.returncode == 0, proc.stderr
    for verb in VERBS:
        assert f"make {verb}" in proc.stdout
    assert "ARGS=--dry-run" in proc.stdout


def test_both_verbs_are_phony(project):
    """They produce no file of their own name, so a directory called `park`
    must not be able to make `make park` a no-op."""
    phony = [line for line in (project / "Makefile").read_text().splitlines()
             if line.startswith(".PHONY:")]
    assert len(phony) == 1, phony
    for verb in VERBS:
        assert f" {verb}" in phony[0]




# --- the family holder ------------------------------------------------------
#
# Ruling 5 (#77, 2026-09-09) put both verbs on the holder too. They run in the
# members' WORKING CLONES BESIDE THE HOLDER — `scripts/siblings.py --make
# <target>` — and never in `members/<Project>`, which is pinned, detached and
# holds nobody's features: a holder that parked that copy would report
# "nothing to park" for every member while the work sat next door. So what the
# holder owes a reader is per-member reporting, no stopping at the first
# failure, a NAMED SKIP when a member has no working clone, and a non-zero
# exit when anything was skipped or refused.

MEMBERS = ("Alpha", "Bravo")


def seed_bare_member(base: Path, name: str) -> Path:
    """A bare repository holding one member: `project.yaml` and a Makefile.

    Bare repositories in a temporary directory, exactly as the rest of this
    suite works — no network, and no real repository is ever created. The
    member needs only what the dispatch reads: an `origin` to identify it by,
    its own `project.yaml` id, and a `Makefile` to run the verb from.
    """
    seed = base / "seed" / name
    seed.mkdir(parents=True)
    (seed / "project.yaml").write_text(
        "schema_version: 1\nkind: project-manifest\n"
        f"id: {name.lower()}\nname: {name}\n", encoding="utf-8")
    shutil.copy2(REPO / "templates" / "assembly-root" / "Makefile",
                 seed / "Makefile")
    git("init", "-q", cwd=seed)
    git("add", "-A", cwd=seed)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "seed",
        cwd=seed)
    bare = base / "remotes" / f"{name}.git"
    bare.parent.mkdir(exist_ok=True)
    git("clone", "-q", "--bare", str(seed), str(bare), cwd=base)
    return bare


@pytest.fixture
def estate(tmp_path) -> dict:
    """The workstation layout: `<F>/<F>` the holder, `<F>/<Project>` beside it.

    Built from the template bytes themselves rather than from `family.py
    init`: what the dispatch needs is the layout and the three copies a
    materialized holder carries, and each of those is asserted below to be
    one the family materializer copies, so a template that stopped being
    copied fails here instead of making this fixture a fiction.

    `members/<Project>` is present and carries a stub of its own, labelled
    `PINNED-<Project>`: it must NEVER be invoked, and a fixture with nothing
    there could not prove that.
    """
    for rel in ("Makefile", "scripts/bootstrap.py", "scripts/siblings.py"):
        assert rel in FAMILY_COPIED_VERBATIM, rel
    assert "Makefile" in COPIED_VERBATIM
    assert ("scripts/repo_shape.py", "scripts/repo_shape.py") in \
        FAMILY_COPIED_FROM_SHAPE

    folder = tmp_path / "TestFam"
    holder = folder / "TestFam"
    (holder / "scripts").mkdir(parents=True)
    git("init", "-q", cwd=holder)
    template = REPO / "templates" / "family-root"
    shutil.copy2(template / "Makefile", holder / "Makefile")
    for rel in ("scripts/bootstrap.py", "scripts/siblings.py"):
        shutil.copy2(template / rel, holder / rel)
    shutil.copy2(REPO / "scripts" / "repo_shape.py",
                 holder / "scripts" / "repo_shape.py")

    rows, modules, siblings, pinned = [], [], {}, {}
    for name in MEMBERS:
        bare = seed_bare_member(tmp_path, name)
        rows.append(f"  - project: {name}\n"
                    f"    id: {name.lower()}\n"
                    f"    repository: testorg/{name}\n"
                    f"    path: members/{name}\n")
        # An ABSOLUTE url, which is what `family.py add --local-remote-dir`
        # writes for a bare remote on disk.
        modules.append(f'[submodule "members/{name}"]\n'
                       f"\tpath = members/{name}\n\turl = {bare}\n")
        sibling = folder / name
        git("clone", "-q", str(bare), str(sibling), cwd=tmp_path)
        siblings[name] = sibling
        # The PINNED copy: present, with a Makefile and a stub of its own.
        mount = holder / "members" / name
        mount.mkdir(parents=True)
        (mount / ".git").mkdir()
        shutil.copy2(REPO / "templates" / "assembly-root" / "Makefile",
                     mount / "Makefile")
        for verb in VERBS:
            write_stub(mount, verb, label=f"PINNED-{name}")
        pinned[name] = mount

    (holder / "family.yaml").write_text(
        "schema_version: 1\nkind: family-manifest\nid: testfam\n"
        'name: "TestFam"\nrepository: testorg/TestFam\n'
        "members_dir: members\nmembers:\n" + "".join(rows), encoding="utf-8")
    (holder / ".gitmodules").write_text("".join(modules), encoding="utf-8")
    return {"folder": folder, "holder": holder, "siblings": siblings,
            "pinned": pinned}


@pytest.mark.parametrize("verb", VERBS)
def test_the_holder_runs_the_verb_in_every_working_clone(estate, verb):
    for name, sibling in estate["siblings"].items():
        write_stub(sibling, verb, label=name)
    proc = make(estate["holder"], verb, "ARGS=--dry-run")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for name in MEMBERS:
        assert f"--- {name}: make {verb} ---" in proc.stdout
        assert f"{name}.sh ran with: --dry-run" in proc.stdout
    assert "siblings ok:" in proc.stdout


@pytest.mark.parametrize("verb", VERBS)
def test_the_holder_never_runs_the_verb_in_the_pinned_copy(estate, verb):
    """The negative half of the ruling, and the reason this slice was
    reworked: `members/<Project>` is detached and holds nobody's work."""
    for name, sibling in estate["siblings"].items():
        write_stub(sibling, verb, label=name)
    proc = make(estate["holder"], verb)
    both = proc.stdout + proc.stderr
    assert proc.returncode == 0, both
    assert "PINNED-" not in both, (
        "the verb must run in the working clones, never in members/")


@pytest.mark.parametrize("verb", VERBS)
def test_a_member_with_no_working_clone_is_skipped_by_name(estate, verb):
    """A SKIP IS NOT A PASS. A `make resume` on a fresh machine where nobody
    has run `make siblings` skips every member, and an exit 0 there is how
    somebody concludes their work came back when none of it did."""
    rmtree(estate["siblings"]["Alpha"])          # the FIRST row
    write_stub(estate["siblings"]["Bravo"], verb, label="Bravo")
    proc = make(estate["holder"], verb)
    both = proc.stdout + proc.stderr
    assert "SKIPPED no clone" in proc.stdout
    assert "run `make siblings` first" in proc.stderr
    assert f"--- Bravo: make {verb} ---" in proc.stdout, (
        "the skip must not stop the members after it"
    )
    assert "Bravo.sh ran with:" in proc.stdout
    assert proc.returncode != 0, both


@pytest.mark.parametrize("verb", VERBS)
def test_a_members_refusal_is_reported_and_the_rest_still_run(estate, verb):
    """Exit 3 is the extension's PARTIAL, and exit 2 its refusal; either way
    the holder prints it, carries on, and does not read as success."""
    write_stub(estate["siblings"]["Alpha"], verb, code=3, label="Alpha")
    write_stub(estate["siblings"]["Bravo"], verb, label="Bravo")
    proc = make(estate["holder"], verb)
    both = proc.stdout + proc.stderr
    assert f"make {verb} exited 2" in proc.stdout, (
        "make flattens the script's 3 to its own 2; the state says so")
    assert re.search(r"(Error|code) 3\b", both), (
        f"the member's own code must still be on screen:\n{both}")
    assert f"--- Bravo: make {verb} ---" in proc.stdout
    assert "Bravo.sh ran with:" in proc.stdout
    assert proc.returncode != 0, both


@pytest.mark.parametrize("verb", VERBS)
def test_a_member_with_no_overlay_refuses_and_is_named(estate, verb):
    """The member's own refusal, printed where it happened."""
    write_stub(estate["siblings"]["Bravo"], verb, label="Bravo")
    proc = make(estate["holder"], verb)
    both = proc.stdout + proc.stderr
    assert (f"make {verb} needs the Speckit worktree overlay; install it "
            "with: setup-openspeckit") in both
    assert "Bravo.sh ran with:" in proc.stdout
    assert proc.returncode != 0, both


def test_a_sibling_that_is_a_different_repository_is_skipped_not_run(estate):
    """The identity check is the dispatch's too, and it is the reason the
    dispatch lives in this file: a verb run in a directory that is not this
    member is worse than a verb not run at all. `verify_sibling` is one
    definition, used by the placement half and by this one."""
    alpha, bravo = estate["siblings"]["Alpha"], estate["siblings"]["Bravo"]
    write_stub(alpha, "park", label="Alpha")
    write_stub(bravo, "park", label="Bravo")
    git("remote", "set-url", "origin", str(estate["folder"].parent / "remotes"
                                          / "Bravo.git"), cwd=alpha)
    proc = make(estate["holder"], "park")
    both = proc.stdout + proc.stderr
    assert "WRONG ORIGIN" in proc.stdout
    assert "Alpha.sh ran with:" not in proc.stdout, (
        "the verb must not run in a clone that is not this member")
    assert "Bravo.sh ran with:" in proc.stdout
    assert proc.returncode != 0, both


@pytest.mark.parametrize("verb", VERBS)
def test_make_arg_carries_args_with_no_make_above_it(estate, verb):
    """The flag itself, with no `make` anywhere above it.

    Under `make park ARGS=...` the assignment also travels in `MAKEFLAGS`, so
    the end-to-end test would pass even if `--make-arg` did nothing at all.
    This one empties `MAKEFLAGS` and calls the dispatch directly: `ARGS`
    reaches the member because the holder passed it, and for no other reason.
    """
    for name, sibling in estate["siblings"].items():
        write_stub(sibling, verb, label=name)
    proc = run_script(estate["holder"] / "scripts" / "siblings.py",
                      "--make", verb, "--make-arg", "ARGS=--dry-run",
                      cwd=estate["holder"], env={"MAKEFLAGS": ""})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for name in MEMBERS:
        assert f"{name}.sh ran with: --dry-run" in proc.stdout


@pytest.mark.parametrize("verb", VERBS)
def test_dry_run_says_what_would_run_and_runs_nothing(estate, verb):
    for name, sibling in estate["siblings"].items():
        write_stub(sibling, verb, label=name)
    proc = run_script(estate["holder"] / "scripts" / "siblings.py",
                      "--make", verb, "--make-arg", "ARGS=--dry-run",
                      "--dry-run", cwd=estate["holder"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for name in MEMBERS:
        assert f"would run `make {verb} ARGS=--dry-run`" in proc.stdout
        assert f"{name}.sh ran with:" not in proc.stdout
    assert "--dry-run: nothing was run." in proc.stdout


def test_the_dispatch_clones_and_fetches_nothing(estate):
    """It only dispatches. A member that is absent stays absent — a `make
    park` that cloned would be doing `make siblings`' job, in the middle of
    somebody parking their work."""
    rmtree(estate["siblings"]["Alpha"])
    write_stub(estate["siblings"]["Bravo"], "park", label="Bravo")
    before = git("rev-parse", "HEAD", cwd=estate["siblings"]["Bravo"]).stdout
    proc = make(estate["holder"], "park")
    assert proc.returncode != 0
    assert not estate["siblings"]["Alpha"].exists(), (
        "the dispatch must not clone the member it reported as skipped")
    assert git("rev-parse", "HEAD",
               cwd=estate["siblings"]["Bravo"]).stdout == before


# --- what may reach make's argv (SonarCloud pythonsecurity:S8705, PR #80) ---
#
# `--make` and `--make-arg` come off a command line and end up in a
# subprocess's argv. Nothing is injectable — the call is a list with no shell,
# so `park; rm -rf /` is ONE argument make has no rule for — but the values
# are validated by pattern anyway, at parse time, BEFORE any member runs: a
# bad value found after the first member's verb has committed and pushed
# somebody's work would be a refusal that came too late to be one.


def dispatch_directly(estate, *args) -> subprocess.CompletedProcess:
    return run_script(estate["holder"] / "scripts" / "siblings.py", *args,
                      cwd=estate["holder"])


# `-park` is not in this list: argparse refuses a value that looks like an
# option before this file's own check ever sees it, which is its business and
# not this pattern's.
@pytest.mark.parametrize("bad", ["park; rm -rf /", "", "../park", "park park",
                                 "park\nrm -rf /", "park$(id)"])
def test_a_make_target_that_is_not_one_is_refused_by_name(estate, bad):
    for name, sibling in estate["siblings"].items():
        write_stub(sibling, "park", label=name)
    proc = dispatch_directly(estate, "--make", bad)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "REFUSED make-target-invalid" in proc.stderr
    assert repr(bad) in proc.stderr, "the refusal names the offending value"
    assert "ran with:" not in proc.stdout, "nothing may run"
    assert "Nothing was run." in proc.stderr


@pytest.mark.parametrize("bad", ["ARGS=x\ny", "not an assignment", "=x",
                                 "9ARGS=x", "ARGS"])
def test_a_make_arg_that_is_not_an_assignment_is_refused_by_name(estate, bad):
    for name, sibling in estate["siblings"].items():
        write_stub(sibling, "park", label=name)
    proc = dispatch_directly(estate, "--make", "park", "--make-arg", bad)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "REFUSED make-arg-invalid" in proc.stderr
    assert repr(bad) in proc.stderr
    assert "ran with:" not in proc.stdout, "nothing may run"


@pytest.mark.parametrize("good", ["ARGS=--dry-run", "ARGS=", "ARGS=--feature "
                                  "001-a --dry-run", "SPECKIT_LANE=xfactory-2"])
def test_a_real_make_assignment_is_accepted(estate, good):
    """The shape the holder actually passes, and nothing narrower: `ARGS=`
    (empty, which is what `make park` with no ARGS produces) must pass too."""
    for name, sibling in estate["siblings"].items():
        write_stub(sibling, "park", label=name)
    proc = dispatch_directly(estate, "--make", "park", "--make-arg", good)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for name in MEMBERS:
        assert f"{name}.sh ran with:" in proc.stdout


def test_make_set_to_something_unexecutable_is_refused(estate):
    """`$MAKE` is resolved through `shutil.which` like the PATH lookup, so
    what reaches the subprocess is a program this file resolved."""
    write_stub(estate["siblings"]["Alpha"], "park", label="Alpha")
    proc = run_script(estate["holder"] / "scripts" / "siblings.py",
                      "--make", "park", cwd=estate["holder"],
                      env={"MAKE": str(estate["holder"] / "family.yaml")})
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "REFUSED make-not-executable" in proc.stderr
    assert "ran with:" not in proc.stdout


def test_make_arg_alone_is_refused(estate):
    """`--make-arg` with no `--make` is a person expecting a dispatch that is
    not happening; argparse refuses it by name rather than ignoring it."""
    proc = run_script(estate["holder"] / "scripts" / "siblings.py",
                      "--make-arg", "ARGS=--dry-run", cwd=estate["holder"])
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "--make-arg is only meaningful with --make" in proc.stderr


def test_the_holders_help_names_both_verbs_and_the_working_clones(estate):
    proc = make(estate["holder"], "help")
    assert proc.returncode == 0, proc.stderr
    for verb in VERBS:
        assert f"make {verb}" in proc.stdout
    assert "WORKING CLONE" in proc.stdout
    assert "make siblings places one" in proc.stdout
