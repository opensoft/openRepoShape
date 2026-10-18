# SPDX-License-Identifier: Apache-2.0
"""The `legs` and `members` NEXT cures the row it sits on, and needs no
script the root may lack (#276).

THE DEFECT. Both rows printed `python3 <root>/scripts/bootstrap.py
--root <root>` without asking whether the root had it, so a root that had lost
the file (the `shape currency` row says `copy-missing` for it) pasted `can't
open file`, exit 2. And where the file was there it did not cure the row:
bootstrap never initialises an empty mount (it prints `NOT INITIALIZED` and
stops), and it moves a tracking branch whose tip is not the pin only where
that loses nothing, behind the pin or ahead of it with no commit of its own
(#475, #490), so the re-run doctor said the same thing.

WHAT THE LINE IS NOW is `git -C <root> submodule update --init --recursive
--checkout -- <paths>`, which needs no script and no `PYTHONPATH`. A lockstep
fact no checkout cures (no gitlink, no 40-hex pin, a gitlink that is not the
pin, a mount git cannot read a HEAD in) gets the lockstep gate instead, built
the way the `pins` and `family` rows build theirs. A holder's own bootstrap
stays the NEXT when it can run, because it carries the credential rewrite a
private member needs.

EVERY NEXT HERE IS PASTED AND RUN, from a directory that is not the root,
through `sh -c` exactly as the row printed it, and the row is asked again.
Those tests are `WINDOWS_SKIP`: `sh` is a POSIX shell, and on Windows the
reader's shell is PowerShell. The text-level assertions about what the line
IS carry no skip, so they run on whatever host the suite is run on.

THE POWERSHELL FORM OF A LINE IS CHECKED AS TEXT AND NEVER RUN (#415).
`test_the_line_is_spelled_for_the_readers_shell` asks `quote_arg` for it
(`platform="nt"`, from any host) and compares the string; no test here pastes
a line into `powershell`. A Windows-only test would not change that, because
no job runs this file on Windows: `tests.yml` runs the suite on ubuntu-latest
alone (the macOS and Windows jobs were dropped, #597), and its one Windows
job, `tests-git-bash`, runs three files of the launcher's and the installer's
suites and no other. A `skipif(os.name != "nt")` test added here would be
skipped by every runner there is. The one test that does paste a PowerShell
line, for a template validator's (`test_shape_doctor.py`,
`test_a_template_validators_next_runs_when_pasted_into_powershell`), is no
better placed: no job runs it either. What this file holds of a Windows
reader's line is its text.

A git paste gets the file protocol per subprocess through
git's `GIT_CONFIG_COUNT` entries -- the fixtures' remotes are bare
repositories on disk, which git refuses as a submodule URL by default --
appended at the call to the entries the environment holds (`paste_env`), and
never through `GIT_ALLOW_PROTOCOL`, which would override git's `user` policy
for the whole run. Where it may clone a mount, it also gets the rewrite every
other clone of the suite carries, so that the remote is read through git and
not through its files (`paste(row, cwd, remotes)`, #835).

WHAT IS ASSERTED IS WHAT THE COMMAND DOES, and the explanation beside it is
read through `why_of` alone, so that moving the `   # ` tail into a field of
its own (#277) changed one helper here and not every test.

The fixtures are `test_shape_doctor`'s, imported rather than rebuilt: a
project or a holder made any other way would be a different one.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess

from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from conftest import (WINDOWS_SKIP, appended_to_command_scope,
                      cloned_just_pushed, git, insteadof_entries, rmtree,
                      submodule_update_through_git)
from test_doctor_gitmodules_not_utf8 import listed_locale
from test_shape_doctor import (  # noqa: F401
    AWKWARD, FAMILY_MEMBER, FAMILY_NAME, GIT_IDENTITY, PROJECT, commit_all,
    doctor, doctor_module, holder, project, record_gitlink, rows_of,
    scaffolded_here, siblings, standard,
)


def paste_env(remotes: Path | None = None) -> dict:
    """What every pasted git line runs under: the identity a commit needs
    (this container has none, and neither does a fresh CI runner), the file
    protocol for ONE process tree, and no `PYTHONPATH` from the person
    running the suite -- a template line that needed one from the reader is
    exactly what these tests are not allowed to depend on.

    With `remotes`, the directory the fixtures' bare repositories are in, the
    `url.<file URI>.insteadOf` entries every other read of them carries
    (`insteadof_entries`, #662) follow the file protocol in the same count:
    for the directory resolved, which is how `.gitmodules` records each url.
    A mount a pasted `git submodule update --init` clones from a plain path
    gets git's LOCAL clone, which links the remote's loose objects one file
    at a time (#440) and starts `upload-pack` only to list the refs. With the
    rewrite the objects arrive as a pack (`pack-objects`, `index-pack`) that
    `upload-pack` reads from the object store, and the clone's `origin` keeps
    the plain path.

    BUILT AT THE CALL, from the `os.environ` of that moment, and the file
    protocol is APPENDED to the `GIT_CONFIG_COUNT` entries it holds
    (`appended_to_command_scope`): the session's own (`no_auto_maintenance`
    keeps git's automatic maintenance off, #645) and the two the Windows job
    sets. This was a dict built when the module was imported, at collection,
    before the session fixture ran, so it held none of those, and its own
    `GIT_CONFIG_COUNT` of 1 would have dropped the ones the environment did
    hold (#758)."""
    entries = [("protocol.file.allow", "always")]
    if remotes is not None:
        entries += insteadof_entries(remotes)
    return {**{k: v for k, v in os.environ.items() if k != "PYTHONPATH"},
            **GIT_IDENTITY,
            **appended_to_command_scope(os.environ, entries),
            "PYTHONDONTWRITEBYTECODE": "1"}


#: The git line's own words after `git -C <root>`: `--init` for a mount the
#: clone never registered, `--recursive` for a member's own legs, and
#: `--checkout` so that a configured `submodule.<name>.update` (rebase, merge,
#: none) cannot turn the line into something else.
UPDATE = "submodule update --init --recursive --checkout"


# --- reading a row ----------------------------------------------------------

def command_of(row: dict) -> str:
    """The command a row hands over: its NEXT, which is only the command
    (#277)."""
    return row["next"] or ""


def why_of(row: dict) -> str:
    """The sentence that explains the command: the row's own `why`, which
    used to be the NEXT's `   # ` tail (#277)."""
    return row["why"] or ""


def row_of(standard: Path, root: Path, row_id: str) -> dict:
    return rows_of(doctor(standard, root, "--json"))[row_id]


#: What a shell reads as syntax where a `#` starts no comment.
SHELL_SYNTAX = (";", "'", "`", "(", ")")


def assert_fixed_words_are_plain(why: str, *spelled: str) -> None:
    """The explanation's FIXED words hold none of `SHELL_SYNTAX`.

    `spelled` is each path the sentence names, as `quote_arg` spelled it. It
    is asked for, so a sentence that names nothing fails here, and it is put
    as `PATH` before the words are read: a path is the root's and not the
    sentence's, and a root that needs quoting puts a `'` into it (#415). A
    check over the whole sentence holds only for a root that needs none,
    which pytest's temporary roots are."""
    words = why
    for each in spelled:
        assert each in why, (each, why)
        words = words.replace(each, "PATH")
    for character in SHELL_SYNTAX:
        assert character not in words, (character, words)


def remotes_of(fixture: dict) -> Path:
    """The directory a session fixture (`scaffolded_here`, `holder`)
    scaffolded its bare repositories into."""
    return fixture["base"] / "remotes"


def paste(row: dict, cwd: Path,
          remotes: Path | None = None) -> subprocess.CompletedProcess:
    """The row's NEXT exactly as it was printed, in a POSIX shell, from a
    directory that is not the root, under `paste_env(remotes)`: every
    caller that pastes a root made from the fixtures hands `remotes`, as
    `remotes_of(holder)` or `remotes_of(scaffolded_here)` on a fixture its
    test takes, and `tests/test_doctor_paste_through_git.py` holds each of
    them to that."""
    cwd.mkdir(exist_ok=True)
    return subprocess.run(["sh", "-c", row["next"]], cwd=str(cwd),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False,
                          env=paste_env(remotes),
                          stdin=subprocess.DEVNULL)


def commit_in(leg: Path, message: str = "work in the leg, past the pin"
              ) -> str:
    """One commit made INSIDE a mount, which is how a leg walks off its pin;
    its sha. Two commits on one parent need two messages: empty commits made
    in the same second with the same message are the SAME commit."""
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", message],
                   cwd=str(leg),
                   capture_output=True, check=True,
                   env={**os.environ, **GIT_IDENTITY})
    return git("rev-parse", "HEAD", cwd=leg).stdout.strip()


# --- ways a root can be wrong -----------------------------------------------

def unbootstrap(root: Path, mount: str) -> None:
    """An unbootstrapped clone's mount: empty, NOT registered, and with no
    gitdir to re-attach, so putting it right has to FETCH."""
    git("submodule", "deinit", "-q", "-f", "--", mount, cwd=root)
    modules = root / ".git" / "modules" / Path(mount)
    if modules.is_dir():
        rmtree(modules)


def make_empty_mount(root: Path) -> dict:
    unbootstrap(root, "code")
    return {"paths": ["code"], "off_pin": []}


def make_branch_past_the_pin(root: Path) -> dict:
    """A commit on the leg's own TRACKING BRANCH, which is the case the old
    NEXT could not cure even with the script there: bootstrap never moves an
    existing branch whose tip is not the pin, and leaves the leg where it
    is. (On any other branch it would have checked `main` out at the pin and
    cured it.)"""
    git("checkout", "-q", "-B", "main", cwd=root / "spec")
    return {"paths": ["spec"], "off_pin": [], "commit": commit_in(
        root / "spec"), "branch": "main"}


def make_detached_past_the_pin(root: Path) -> dict:
    """A fresh recursive clone leaves every leg DETACHED at its pin, so a
    commit made in one is on no branch."""
    return {"paths": ["spec"], "off_pin": ["spec"],
            "commit": commit_in(root / "spec")}


def make_script_absent(root: Path) -> dict:
    """The issue's own reproduction: the shape copy gone AND an empty mount."""
    git("rm", "-q", "scripts/bootstrap.py", cwd=root)
    unbootstrap(root, "spec")
    return {"paths": ["spec"], "off_pin": []}


def make_repo_shape_absent(root: Path) -> dict:
    """`scripts/bootstrap.py` is there but imports `repo_shape` from beside
    itself, so a root without that file has a bootstrap that dies on import:
    it is no more a script the NEXT may name than an absent one."""
    git("rm", "-q", "scripts/repo_shape.py", cwd=root)
    unbootstrap(root, "spec")
    return {"paths": ["spec"], "off_pin": []}


CHECKOUT_SCENARIOS = {
    "empty-mount": make_empty_mount,
    "branch-past-the-pin": make_branch_past_the_pin,
    "detached-past-the-pin": make_detached_past_the_pin,
    "bootstrap-absent": make_script_absent,
    "repo-shape-absent": make_repo_shape_absent,
}


def make_gitlink_moved(root: Path) -> dict:
    """HEAD and the gitlink agree with each other and not with the pin: a
    checkout lands on the gitlink, so it cannot make HEAD the pin."""
    record_gitlink(root, "spec", commit_in(root / "spec"))
    return {}


def make_pin_not_a_commit(root: Path) -> dict:
    pin = root / "contracts" / "spec-pin.yaml"
    text = pin.read_text(encoding="utf-8")
    edited, count = re.subn(r'(?m)^commit: "[0-9a-f]{40}"$', 'commit: "main"',
                            text)
    assert count == 1, text
    pin.write_text(edited, encoding="utf-8")
    return {}


def make_head_unreadable(root: Path) -> dict:
    """The mount keeps its files and its `.git` file; the gitdir it points at
    is gone, so git cannot read a HEAD in it."""
    rmtree(root / ".git" / "modules" / "spec")
    return {}


def make_mount_with_no_git_of_its_own(root: Path) -> dict:
    """A populated directory that is not a repository. Asked in it, git walks
    up and answers with the ROOT's HEAD, so the row reads a HEAD that is not
    the leg's; and with the gitdir gone too there is nothing for an update to
    re-attach."""
    (root / "spec" / ".git").unlink()
    rmtree(root / ".git" / "modules" / "spec")
    return {}


def make_no_gitlink(root: Path) -> dict:
    """The superproject records NO gitlink for `spec` -- in the index or in
    HEAD, which `recorded_gitlink` falls back to -- so it is not a submodule
    here at all, whatever sits in the directory."""
    git("rm", "-q", "--cached", "--", "spec", cwd=root)
    subprocess.run(["git", "commit", "-q", "-m", "unmount spec"],
                   cwd=str(root), capture_output=True, check=True,
                   env={**os.environ, **GIT_IDENTITY})
    return {}


LOCKSTEP_SCENARIOS = {
    "no-gitlink": make_no_gitlink,
    "gitlink-moved": make_gitlink_moved,
    "pin-not-a-commit": make_pin_not_a_commit,
    "head-unreadable": make_head_unreadable,
    "mount-with-no-git-of-its-own": make_mount_with_no_git_of_its_own,
}


def pins_gate(module, standard: Path, root: Path, own_copy: bool) -> str:
    """What `validator_command` makes of `validate-pins.py` for this root:
    the root's own copy, or the standard's template copy."""
    used = (root / "scripts" / "validate-pins.py" if own_copy else
            standard / "templates" / "assembly-root" / "scripts"
            / "validate-pins.py")
    return module.validator_command(standard, used, own_copy,
                                    ["--root", str(root.resolve())])


# --- the legs row: what the line IS (text only, no OS skip) ----------------

@pytest.mark.parametrize("scenario", sorted(CHECKOUT_SCENARIOS))
def test_a_leg_a_checkout_cures_is_handed_a_script_free_git_line(
        standard, project, scenario):
    """Five roots, one answer, and none of them names a script.

    The line is `git -C <root> submodule update --init --recursive --checkout
    -- <the legs>`: no interpreter, no path into the root's own `scripts/`,
    so a root that lost `bootstrap.py` (or `repo_shape.py`, which it imports)
    is handed something that can run.
    """
    made = CHECKOUT_SCENARIOS[scenario](project)
    module = doctor_module(standard)
    row = row_of(standard, project, "legs")
    assert row["status"] == "FINDING", row
    root = project.resolve()
    assert command_of(row) == (
        f"git -C {module.quote_arg(root)} {UPDATE} -- "
        f"{' '.join(made['paths'])}"), row["next"]
    # (The equality above is the whole claim: a git line, no script. A
    # substring test of the command would read the TEST'S OWN tmp path.)


def test_a_legs_next_that_lists_two_legs_lists_both(standard, project):
    unbootstrap(project, "spec")
    unbootstrap(project, "code")
    module = doctor_module(standard)
    row = row_of(standard, project, "legs")
    assert command_of(row) == (
        f"git -C {module.quote_arg(project.resolve())} {UPDATE} -- spec code"
    ), row["next"]


def test_the_line_is_spelled_for_the_readers_shell(standard):
    """`quote_arg`'s two dialects, asked for on whichever host this runs on
    (the rule `copy_command` and `scaffold_command` already follow): a root
    with a space in it is single-quoted for `sh`, and PowerShell gets its own
    verbatim string, backslashes and all, in the line AND in the keep line
    the explanation names.

    THE ONLY CHECK OF THE POWERSHELL FORM, AND IT IS OF THE TEXT: no test in
    this file runs it in `powershell`, and no job could (module docstring,
    #415)."""
    module = doctor_module(standard)
    posix_root = PurePosixPath("/srv/my atlas")
    line, why = module.submodule_update_next(
        posix_root, ["spec", "code"], [posix_root / "spec"], "leg",
        platform="posix")
    assert line == f"git -C '/srv/my atlas' {UPDATE} -- spec code", line
    assert "git -C '/srv/my atlas/spec' branch NAME" in why, why
    nt_root = PureWindowsPath("C:/Work/My Atlas")
    line, why = module.submodule_update_next(
        nt_root, ["members/IRRS"], [nt_root / "members" / "IRRS"], "member",
        platform="nt")
    assert line == (f"git -C 'C:\\Work\\My Atlas' {UPDATE} -- "
                    "members/IRRS"), line
    assert "git -C 'C:\\Work\\My Atlas\\members\\IRRS' branch NAME" in why
    assert "a member on no branch" in why, why


# --- the explanation: the reflog note, when and only when ------------------

def test_the_reflog_note_is_printed_when_a_leg_is_detached_off_its_pin(
        standard, project):
    """A commit made on a detached HEAD is left only in the leg's reflog by
    the line, so the explanation says so in plain words and names the line
    that keeps it first: `git -C <leg> branch NAME`."""
    make_detached_past_the_pin(project)
    module = doctor_module(standard)
    why = why_of(row_of(standard, project, "legs"))
    leg = module.quote_arg((project / "spec").resolve())
    assert "reflog" in why, why
    assert "on no branch" in why, why
    assert f"git -C {leg} branch NAME" in why, why


@pytest.mark.parametrize("scenario", ["empty-mount", "branch-past-the-pin",
                                      "bootstrap-absent",
                                      "repo-shape-absent"])
def test_the_reflog_note_is_not_printed_when_nothing_is_detached_off_a_pin(
        standard, project, scenario):
    """Nothing can be lost in these four, so nothing is said: an empty mount
    has no commit, a commit on a branch stays on it, and a note printed
    where there is nothing to lose is a note nobody reads on the day there
    is."""
    CHECKOUT_SCENARIOS[scenario](project)
    why = why_of(row_of(standard, project, "legs"))
    assert why, "the line must say what it does"
    assert "reflog" not in why, why
    assert "branch NAME" not in why, why


def test_the_reflog_note_names_only_the_detached_leg(standard, project):
    """Two off-pin legs, one on a branch and one on a detached HEAD: only the
    detached one is named."""
    git("checkout", "-q", "-b", "work", cwd=project / "code")
    commit_in(project / "code")
    commit_in(project / "spec")
    module = doctor_module(standard)
    row = row_of(standard, project, "legs")
    assert command_of(row).endswith("-- spec code"), row["next"]
    why = why_of(row)
    assert f"git -C {module.quote_arg((project / 'spec').resolve())} " \
        "branch NAME" in why, why
    assert "code branch NAME" not in why, why
    assert why.count("branch NAME") == 1, why


def test_a_leg_at_its_pin_on_a_branch_has_no_finding_and_so_no_note(
        standard, project):
    """The control: detached is not the question when HEAD is the pin."""
    git("checkout", "-q", "-B", "tracking", cwd=project / "spec")
    row = row_of(standard, project, "legs")
    assert row["status"] == "ok", row
    assert row["next"] is None, row


#: Two roots a shell cannot be handed bare: one with a space, and one with a
#: space and an apostrophe, where a naive `'...'` wrapper closes early.
#: pytest's own temporary roots are neither, so a test over them alone cannot
#: see what `quote_arg` puts into a sentence (#415).
QUOTED_ROOTS = [pytest.param("my atlas", id="a-space"),
                pytest.param(AWKWARD, id="a-space-and-an-apostrophe")]


@pytest.mark.parametrize("name", QUOTED_ROOTS)
@pytest.mark.parametrize("scenario", sorted(CHECKOUT_SCENARIOS))
def test_the_explanations_fixed_words_hold_no_shell_syntax_over_a_quoted_root(
        standard, project, tmp_path, scenario, name):
    """The sentence's own words hold none of `;`, `'`, a backtick or a
    parenthesis, and each keep line in it is one command whose path is one
    argument, for a root that needs quoting.

    #277 moved the sentence off the NEXT, into the row's `why`, so it is not
    pasted with the line, but a reader still copies a keep line out of it.
    The words around the path are fixed and plain. The path is the root's,
    spelled by `quote_arg`, which quotes it, so a `'` there is the quoting,
    and `shlex.split`, which is how `sh` reads the line, gives the path back
    as one argument. This test used to read the whole sentence over pytest's
    own roots, which need no quoting: it held none of the five characters by
    that accident, and never read the path as a word (#415).
    """
    root = tmp_path / name
    shutil.copytree(project, root, symlinks=True)
    made = CHECKOUT_SCENARIOS[scenario](root)
    module = doctor_module(standard)
    why = why_of(row_of(standard, root, "legs"))
    mounts = [(root / rel).resolve() for rel in made["off_pin"]]
    spelled = [module.quote_arg(mount) for mount in mounts]
    keeps = re.findall(r"git -C .+? branch NAME", why)
    assert len(keeps) == len(mounts), why
    for keep, mount, quoted in zip(keeps, mounts, spelled):
        assert quoted != str(mount), "this root needs no quoting"
        if os.name != "nt":  # PowerShell quotes an apostrophe by doubling it
            assert shlex.split(keep) == [
                "git", "-C", str(mount), "branch", "NAME"], keep
    assert_fixed_words_are_plain(why, *spelled)


def test_the_bootstrap_sentence_is_said_only_where_the_script_can_run(
        standard, project, tmp_path):
    """`then make bootstrap puts each leg on its tracking branch` is what the
    old NEXT's tail said and the line now leaves to a script the root may
    not have. It is kept when the root has what `make bootstrap` needs (the
    script, the `repo_shape.py` it imports and a Makefile target) and left
    out when it has not -- a sentence that sends a reader to a command that
    cannot run is the defect over again."""
    make_empty_mount(project)
    assert "make bootstrap" in why_of(row_of(standard, project, "legs"))
    # Said for what it does, and not as "at the pinned commit": it leaves a
    # leg whose tracking branch is already ahead of the pin where it is.
    assert "already ahead of the pin" in why_of(row_of(standard, project,
                                                       "legs"))
    no_target = tmp_path / "NoTarget"
    shutil.copytree(project, no_target, symlinks=True)
    makefile = no_target / "Makefile"
    makefile.write_text(re.sub(r"(?m)^bootstrap:", "unrelated:",
                               makefile.read_text(encoding="utf-8")),
                        encoding="utf-8")
    assert "bootstrap" not in why_of(row_of(standard, no_target, "legs"))
    no_makefile = tmp_path / "NoMakefile"
    shutil.copytree(project, no_makefile, symlinks=True)
    git("rm", "-q", "Makefile", cwd=no_makefile)
    assert "bootstrap" not in why_of(row_of(standard, no_makefile, "legs"))
    lost = tmp_path / "Lost"
    shutil.copytree(project, lost, symlinks=True)
    git("rm", "-q", "scripts/bootstrap.py", cwd=lost)
    assert "bootstrap" not in why_of(row_of(standard, lost, "legs"))
    lost_import = tmp_path / "LostImport"
    shutil.copytree(project, lost_import, symlinks=True)
    git("rm", "-q", "scripts/repo_shape.py", cwd=lost_import)
    assert "bootstrap" not in why_of(row_of(standard, lost_import, "legs"))


# --- the legs row: pasted, and the row asked again (POSIX shells) ----------

@WINDOWS_SKIP
@pytest.mark.parametrize("scenario", ["empty-mount", "branch-past-the-pin",
                                      "bootstrap-absent",
                                      "repo-shape-absent"])
def test_a_pasted_legs_next_exits_zero_and_the_legs_row_is_ok(
        standard, project, scaffolded_here, tmp_path, scenario):
    """The point of the whole change: paste what the row printed, from
    somewhere else, and the row is green. Four of the five roots of
    `CHECKOUT_SCENARIOS`; the detached one has a commit to keep first and is
    the next test."""
    made = CHECKOUT_SCENARIOS[scenario](project)
    row = row_of(standard, project, "legs")
    assert row["status"] == "FINDING", row
    result = paste(row, tmp_path / "elsewhere", remotes_of(scaffolded_here))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "can't open file" not in result.stdout + result.stderr
    after = row_of(standard, project, "legs")
    assert after["status"] == "ok", (after, result.stdout, result.stderr)
    assert after["next"] is None, after
    if scenario == "branch-past-the-pin":
        # A commit made on a branch stays on that branch.
        contains = git("branch", "--contains", made["commit"],
                       cwd=project / "spec").stdout
        assert made["branch"] in contains, contains


@WINDOWS_SKIP
def test_the_keep_line_in_the_explanation_keeps_a_detached_commit(
        standard, project, scaffolded_here, tmp_path):
    """The note's own advice is pasted too: run the `git -C <leg> branch
    NAME` it names BEFORE the line, and the commit is on that branch after
    the leg has moved. Without it the commit is reachable from no branch and
    is only in the reflog, which is what the note says."""
    made = make_detached_past_the_pin(project)
    row = row_of(standard, project, "legs")
    keep = re.search(r"git -C \S+ branch NAME", why_of(row))
    assert keep, why_of(row)
    kept = subprocess.run(["sh", "-c", keep.group(0).replace("NAME", "kept")],
                          capture_output=True, text=True, check=False,
                          env=paste_env())
    assert kept.returncode == 0, kept.stdout + kept.stderr
    result = paste(row, tmp_path / "elsewhere", remotes_of(scaffolded_here))
    assert result.returncode == 0, result.stdout + result.stderr
    assert row_of(standard, project, "legs")["status"] == "ok"
    assert "kept" in git("branch", "--contains", made["commit"],
                         cwd=project / "spec").stdout


@WINDOWS_SKIP
def test_without_the_keep_line_the_detached_commit_is_in_no_branch(
        standard, project, scaffolded_here, tmp_path):
    """The other half of the note, so it is true and not merely printed: the
    row is cured and the commit is reachable from no branch."""
    made = make_detached_past_the_pin(project)
    result = paste(row_of(standard, project, "legs"), tmp_path / "elsewhere",
                   remotes_of(scaffolded_here))
    assert result.returncode == 0, result.stdout + result.stderr
    assert row_of(standard, project, "legs")["status"] == "ok"
    assert git("branch", "--contains", made["commit"],
               cwd=project / "spec").stdout.strip() == ""
    # Still in the object store and the reflog: nothing was destroyed.
    assert git("cat-file", "-t", made["commit"],
               cwd=project / "spec").stdout.strip() == "commit"
    assert made["commit"] in git("reflog", cwd=project / "spec").stdout


@WINDOWS_SKIP
@pytest.mark.parametrize("mode", ["merge", "rebase", "none"])
def test_a_configured_update_mode_cannot_turn_the_line_into_a_merge(
        standard, project, scaffolded_here, tmp_path, mode):
    """`git submodule update` obeys `submodule.<name>.update`: under `merge`
    or `rebase` the same line WRITES a merge or a rebased commit into the
    leg and the row stays red, and under `none` it skips the mount, each
    with exit 0. `--checkout` overrides the setting for the one command.

    A DIVERGED leg is what shows it: a teammate's bump records P2 as the
    gitlink and the pin, and this leg is detached at Y on the OLD pin, which
    does not contain P2. Pasted, the row is `ok` and HEAD is P2 itself, so
    nothing was merged or rebased."""
    spec = project / "spec"
    old_pin = git("rev-parse", "HEAD", cwd=spec).stdout.strip()
    bumped = commit_in(spec, "a teammate's bump")
    record_gitlink(project, "spec", bumped)
    pin = project / "contracts" / "spec-pin.yaml"
    pin.write_text(re.sub(r'(?m)^commit: "[0-9a-f]{40}"$',
                          f'commit: "{bumped}"',
                          pin.read_text(encoding="utf-8")), encoding="utf-8")
    git("checkout", "-q", "--detach", old_pin, cwd=spec)
    ours = commit_in(spec)
    assert ours != bumped
    git("config", "submodule.spec.update", mode, cwd=project)
    row = row_of(standard, project, "legs")
    assert row["status"] == "FINDING", row
    assert "--checkout" in command_of(row), row["next"]
    result = paste(row, tmp_path / "elsewhere", remotes_of(scaffolded_here))
    assert result.returncode == 0, result.stdout + result.stderr
    assert row_of(standard, project, "legs")["status"] == "ok", (
        result.stdout, result.stderr)
    assert git("rev-parse", "HEAD", cwd=spec).stdout.strip() == bumped, (
        "a merge or a rebase wrote a commit into the leg")


@WINDOWS_SKIP
def test_a_plain_clones_empty_mounts_are_cured_by_the_pasted_line(
        standard, scaffolded_here, tmp_path):
    """The real unbootstrapped clone the row names: a plain `git clone`, with
    no `--recurse-submodules`, leaves `submodule.active` unset and both
    mounts empty. Without `--init` the update prints `not initialized` and
    the row stays red; the fixture's own recursive clone sets
    `submodule.active`, so every other paste here would pass without it."""
    plain = cloned_just_pushed(
        scaffolded_here["base"] / "remotes" / f"{PROJECT}.git",
        tmp_path / "Plain", recurse=False, env=paste_env())
    row = row_of(standard, plain, "legs")
    assert row["status"] == "FINDING", row
    assert command_of(row).endswith("-- spec code"), row["next"]
    result = paste(row, tmp_path / "elsewhere", remotes_of(scaffolded_here))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "not initialized" not in result.stdout + result.stderr
    after = row_of(standard, plain, "legs")
    assert after["status"] == "ok", (after, result.stdout, result.stderr)


# --- the legs row: what no checkout cures, and the lockstep gate -----------

@pytest.mark.parametrize("scenario", sorted(LOCKSTEP_SCENARIOS))
def test_a_leg_no_checkout_cures_is_handed_the_lockstep_gate(
        standard, project, scenario):
    """A checkout lands on the gitlink and never on the pin, so a gitlink
    that is not the pin, a pin that is not a commit, or a mount git cannot
    read a HEAD in is not cured by `submodule update` -- and the line that
    claims to is a NEXT that does not cure. They get `validate-pins.py`,
    through `validator_command`, which is what the `pins` row hands over for
    the same gate."""
    LOCKSTEP_SCENARIOS[scenario](project)
    module = doctor_module(standard)
    legs = row_of(standard, project, "legs")
    assert legs["status"] == "FINDING", legs
    assert command_of(legs) == pins_gate(module, standard, project, True), \
        legs["next"]
    assert " submodule update " not in command_of(legs), legs["next"]
    assert "scripts/bootstrap.py" not in command_of(legs), legs["next"]
    assert why_of(legs), "the line must say why it is not a checkout"


def test_the_lockstep_line_is_the_one_the_pins_row_hands_over(standard,
                                                              project):
    """One gate, built in two places from the same two functions: the
    `legs` row's command and the `pins` row's are the same string, so a
    reader told two things about one gate is told one."""
    make_gitlink_moved(project)
    rows = rows_of(doctor(standard, project, "--json"))
    assert rows["pins"]["status"] == "FINDING", rows["pins"]
    assert command_of(rows["legs"]) == command_of(rows["pins"]), (
        rows["legs"]["next"], rows["pins"]["next"])


def test_the_lockstep_line_names_the_template_copy_with_its_environment(
        standard, project):
    """A root without its own `scripts/validate-pins.py` falls back to the
    standard's template copy, which imports `repo_shape` from the standard
    and so needs the `PYTHONPATH` that `validator_command` prints (#238).
    The line is built by that function, not retyped."""
    git("rm", "-q", "scripts/validate-pins.py", cwd=project)
    make_gitlink_moved(project)
    module = doctor_module(standard)
    legs = row_of(standard, project, "legs")
    assert command_of(legs) == pins_gate(module, standard, project, False), \
        legs["next"]
    assert "PYTHONPATH" in command_of(legs), legs["next"]
    assert "templates" in command_of(legs), legs["next"]


@WINDOWS_SKIP
@pytest.mark.parametrize("own_copy", [True, False])
def test_a_pasted_lockstep_line_runs_and_prints_the_gate_finding(
        standard, project, scaffolded_here, tmp_path, own_copy):
    """Pasted from elsewhere, with no `PYTHONPATH` in the environment: the
    gate runs (the template's line carries what it needs), exits 1, and says
    which fact is wrong. It is a finding, as it was before the paste -- no
    command cures a lockstep fact, which is the reason it is not a git
    line -- and neither a missing file nor a missing import."""
    if not own_copy:
        git("rm", "-q", "scripts/validate-pins.py", cwd=project)
    make_gitlink_moved(project)
    row = row_of(standard, project, "legs")
    result = paste(row, tmp_path / "elsewhere", remotes_of(scaffolded_here))
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "pin-gitlink-mismatch" in output, output
    assert "can't open file" not in output
    assert "ModuleNotFoundError" not in output


def test_the_git_line_does_not_cure_a_mount_git_cannot_read_a_head_in(
        standard, project):
    """WHY `head-unreadable` IS THE LOCKSTEP GATE'S AND NOT THE GIT LINE'S,
    pinned by what git does so that the day it changes this says so. With the
    gitdir gone `submodule update` cannot get a repository handle, and with
    an orphan branch it cannot find a current revision: it exits non-zero and
    leaves the row exactly as it was. (The case the plan left unprobed.)"""
    make_head_unreadable(project)
    before = row_of(standard, project, "legs")
    assert "cannot read a HEAD" in before["reason"], before
    result = subprocess.run(
        ["git", "-C", str(project), "submodule", "update", "--init",
         "--recursive", "--", "spec"], capture_output=True, text=True,
        check=False, env=paste_env())
    assert result.returncode != 0, result.stdout + result.stderr
    after = row_of(standard, project, "legs")
    assert after["status"] == "FINDING", after
    assert "cannot read a HEAD" in after["reason"], after


def test_a_checkout_wins_over_a_lockstep_fact_and_a_rerun_names_the_other(
        standard, project, scaffolded_here):
    """One leg a checkout cures (an empty mount) and one it does not (a
    gitlink that is not the pin): the line is the checkout, over the first
    leg only, and it says to run the doctor again. The re-run names the
    lockstep gate."""
    unbootstrap(project, "code")
    make_gitlink_moved(project)
    module = doctor_module(standard)
    first = row_of(standard, project, "legs")
    assert command_of(first) == (
        f"git -C {module.quote_arg(project.resolve())} {UPDATE} -- code"
    ), first["next"]
    assert "doctor again" in why_of(first), why_of(first)
    # The fix, applied by hand (no sh needed): the empty leg is now cured.
    submodule_update_through_git(project, scaffolded_here["base"] / "remotes",
                                 "--init", "--recursive", "--", "code")
    second = row_of(standard, project, "legs")
    assert second["status"] == "FINDING", second
    assert command_of(second) == pins_gate(module, standard, project, True), \
        second["next"]
    assert "doctor again" not in why_of(second), why_of(second)


def test_no_line_is_better_than_one_that_cannot_run(standard, tmp_path,
                                                    project):
    """If neither copy of the lockstep gate is readable the row prints no
    command: the `pins` row of the same report says so, and a NEXT that
    cannot run is the defect this row is being fixed for."""
    hollow = tmp_path / "hollow-standard"
    shutil.copytree(standard, hollow, symlinks=True)
    (hollow / "templates" / "assembly-root" / "scripts"
     / "validate-pins.py").unlink()
    git("rm", "-q", "scripts/validate-pins.py", cwd=project)
    make_gitlink_moved(project)
    rows = rows_of(doctor(hollow, project, "--json"))
    assert rows["legs"]["status"] == "FINDING", rows["legs"]
    assert rows["legs"]["next"] is None, rows["legs"]
    assert "neither" in rows["pins"]["reason"], rows["pins"]


# --- the members row -------------------------------------------------------

def holder_copy(holder, tmp_path) -> Path:
    root = tmp_path / FAMILY_NAME
    shutil.copytree(holder["root"], root, symlinks=True)
    return root


def member_unbootstrapped(root: Path) -> None:
    unbootstrap(root, f"members/{FAMILY_MEMBER}")


def holder_without(root: Path, *names: str) -> None:
    for name in names:
        git("rm", "-q", f"scripts/{name}", cwd=root)


def test_a_holder_that_can_run_its_own_bootstrap_keeps_it_as_the_next(
        standard, holder, tmp_path):
    """The holder's bootstrap does what the git line does AND carries the
    credential rewrite a PRIVATE member needs, so it stays the NEXT where it
    can run: `python3 <root>/scripts/bootstrap.py --root <root>`, with the
    explanation it always had."""
    root = holder_copy(holder, tmp_path)
    member_unbootstrapped(root)
    module = doctor_module(standard)
    row = row_of(standard, root, "members")
    assert row["status"] == "FINDING", row
    resolved = root.resolve()
    assert command_of(row) == (
        f"{module.PYTHON} "
        f"{module.quote_arg(resolved / 'scripts' / 'bootstrap.py')} "
        f"--root {module.quote_arg(resolved)}"), row["next"]
    assert " submodule update " not in command_of(row), row["next"]


@WINDOWS_SKIP
def test_a_pasted_members_next_with_the_holders_bootstrap_cures_the_row(
        standard, holder, tmp_path):
    root = holder_copy(holder, tmp_path)
    member_unbootstrapped(root)
    row = row_of(standard, root, "members")
    result = paste(row, tmp_path / "elsewhere", remotes_of(holder))
    assert result.returncode == 0, result.stdout + result.stderr
    after = row_of(standard, root, "members")
    assert after["status"] == "ok", (after, result.stdout, result.stderr)


@pytest.mark.parametrize("lost", [("bootstrap.py",), ("repo_shape.py",),
                                  ("bootstrap.py", "repo_shape.py")])
def test_a_holder_that_cannot_run_its_bootstrap_is_handed_the_git_line(
        standard, holder, tmp_path, lost):
    """Without `scripts/bootstrap.py`, or without the `repo_shape.py` it
    imports from beside itself, the holder's NEXT used to be a command that
    died with `can't open file` or on its import. It is the plain git line
    over the member's path, and the explanation says it carries no credential
    rewrite."""
    root = holder_copy(holder, tmp_path)
    holder_without(root, *lost)
    member_unbootstrapped(root)
    module = doctor_module(standard)
    row = row_of(standard, root, "members")
    assert row["status"] == "FINDING", row
    assert command_of(row) == (
        f"git -C {module.quote_arg(root.resolve())} {UPDATE} -- "
        f"members/{FAMILY_MEMBER}"), row["next"]
    assert "scripts/bootstrap.py" not in command_of(row), row["next"]
    assert "credential" in why_of(row), why_of(row)
    assert_fixed_words_are_plain(why_of(row))
    assert "reflog" not in why_of(row), why_of(row)


@WINDOWS_SKIP
def test_a_pasted_members_git_line_cures_the_row(standard, holder, tmp_path):
    root = holder_copy(holder, tmp_path)
    holder_without(root, "bootstrap.py")
    member_unbootstrapped(root)
    row = row_of(standard, root, "members")
    result = paste(row, tmp_path / "elsewhere", remotes_of(holder))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "can't open file" not in result.stdout + result.stderr
    after = row_of(standard, root, "members")
    assert after["status"] == "ok", (after, result.stdout, result.stderr)


def test_the_members_reflog_note_is_printed_for_a_detached_member_only(
        standard, holder, tmp_path):
    """The git line moves a member's HEAD too: a commit made on its detached
    HEAD is left only in the reflog, and a commit made on a branch is not.
    The branched member is still named in general words for its own legs,
    which the recursive line checks out too (#413 c), but not by a keep
    line of its own."""
    detached = holder_copy(holder, tmp_path / "detached")
    holder_without(detached, "bootstrap.py")
    member = detached / "members" / FAMILY_MEMBER
    head = git("rev-parse", "HEAD", cwd=member).stdout.strip()
    git("checkout", "-q", "--detach", head, cwd=member)
    commit_in(member)
    module = doctor_module(standard)
    why = why_of(row_of(standard, detached, "members"))
    assert "reflog" in why, why
    assert f"git -C {module.quote_arg(member.resolve())} branch NAME" in why

    branched = holder_copy(holder, tmp_path / "branched")
    holder_without(branched, "bootstrap.py")
    member = branched / "members" / FAMILY_MEMBER
    git("checkout", "-q", "-B", "local-work", cwd=member)
    commit_in(member)
    why = why_of(row_of(standard, branched, "members"))
    assert why, "the line must say what it does"
    assert "A commit made in a member on no branch" not in why, why
    assert f"git -C {module.quote_arg(member.resolve())} branch NAME" \
        not in why, why


@WINDOWS_SKIP
def test_a_pasted_members_git_line_keeps_a_detached_commit_on_the_kept_branch(
        standard, holder, tmp_path):
    root = holder_copy(holder, tmp_path)
    holder_without(root, "bootstrap.py")
    member = root / "members" / FAMILY_MEMBER
    git("checkout", "-q", "--detach", "HEAD", cwd=member)
    commit = commit_in(member)
    row = row_of(standard, root, "members")
    keep = re.search(r"git -C \S+ branch NAME", why_of(row))
    assert keep, why_of(row)
    subprocess.run(["sh", "-c", keep.group(0).replace("NAME", "kept")],
                   capture_output=True, check=True, env=paste_env())
    result = paste(row, tmp_path / "elsewhere", remotes_of(holder))
    assert result.returncode == 0, result.stdout + result.stderr
    assert row_of(standard, root, "members")["status"] == "ok"
    assert "kept" in git("branch", "--contains", commit, cwd=member).stdout


def make_member_gitlink_absent(root: Path) -> None:
    """The holder records NO gitlink for the member, and the row is kept
    (the `family` row says `member-gitlink-absent`): the directory is empty
    and `git submodule update -- members/<P>` dies on `pathspec did not
    match`."""
    unbootstrap(root, f"members/{FAMILY_MEMBER}")
    git("rm", "-q", "--cached", "--", f"members/{FAMILY_MEMBER}", cwd=root)
    subprocess.run(["git", "commit", "-q", "-m", "unmount the member"],
                   cwd=str(root), capture_output=True, check=True,
                   env={**os.environ, **GIT_IDENTITY})


def make_member_gitlink_mismatch(root: Path) -> None:
    """The holder's gitlink is a commit that is not the row's `pin.commit`
    (`member-gitlink-mismatch`): a checkout lands on the gitlink, so HEAD
    would still not be the pin and the row would be unchanged."""
    member = root / "members" / FAMILY_MEMBER
    record_gitlink(root, f"members/{FAMILY_MEMBER}", commit_in(member))


MEMBER_GITLINK_STATES = {"gitlink-absent": make_member_gitlink_absent,
                         "gitlink-mismatch": make_member_gitlink_mismatch}


@pytest.mark.parametrize("state", sorted(MEMBER_GITLINK_STATES))
@pytest.mark.parametrize("bootstrap", ["with-its-own-bootstrap",
                                       "without-it"])
def test_a_member_whose_gitlink_is_not_its_pin_is_handed_the_family_gate(
        standard, holder, tmp_path, state, bootstrap):
    """No checkout cures a member the holder records no gitlink for, or one
    whose gitlink is not its `pin.commit`: `check_legs` routes the same two
    states of a leg to `validate-pins.py`, and the members row routes them
    to `validate-family.py`, with or without the holder's own bootstrap. Both
    NEXTs used to exit 0 or die and leave the row exactly as it was."""
    root = holder_copy(holder, tmp_path)
    MEMBER_GITLINK_STATES[state](root)
    if bootstrap == "without-it":
        holder_without(root, "bootstrap.py")
    module = doctor_module(standard)
    rows = rows_of(doctor(standard, root, "--json"))
    members = rows["members"]
    assert members["status"] == "FINDING", members
    resolved = root.resolve()
    assert command_of(members) == module.validator_command(
        standard, resolved / "scripts" / "validate-family.py", True,
        ["--root", str(resolved)]), members["next"]
    assert " submodule update " not in command_of(members), members["next"]
    assert "scripts/bootstrap.py" not in command_of(members), members["next"]
    assert why_of(members), "the line must say why it is not a checkout"
    # The `family` row of the same report names the same fact, and gate.
    assert rows["family"]["status"] == "FINDING", rows["family"]
    assert command_of(rows["family"]) == command_of(members), (
        rows["family"]["next"], members["next"])


def test_an_empty_member_with_a_gitlink_that_is_its_pin_is_still_a_checkout(
        standard, holder, tmp_path):
    """The control for the two states above: the gitlink is the pin, the
    mount is empty, and the line is the checkout."""
    root = holder_copy(holder, tmp_path)
    holder_without(root, "bootstrap.py")
    member_unbootstrapped(root)
    module = doctor_module(standard)
    row = row_of(standard, root, "members")
    assert command_of(row) == (
        f"git -C {module.quote_arg(root.resolve())} {UPDATE} -- "
        f"members/{FAMILY_MEMBER}"), row["next"]


def make_member_pin_not_a_commit(root: Path) -> None:
    """The MEMBER's `pin.commit` becomes a branch name. `family.yaml` carries
    a `shape:` block with a 40-hex `commit:` of its own, above `members:`, and
    that one is left alone."""
    manifest = root / "family.yaml"
    text = manifest.read_text(encoding="utf-8")
    head, marker, rows = text.partition("\nmembers:\n")
    assert marker, text
    edited, count = re.subn(r'(?m)^(\s+commit: )"[0-9a-f]{40}"$',
                            r'\1"main"', rows, count=1)
    assert count == 1, rows
    manifest.write_text(head + marker + edited, encoding="utf-8")


def test_a_member_row_with_no_40_hex_pin_is_handed_the_family_gate(
        standard, holder, tmp_path):
    """No checkout gives a row a `pin.commit`, so the line is the family
    gate -- through `validator_command`, the way the `family` row builds its
    own -- and not a bootstrap that would fetch and still leave the row red.
    The holder HAS its bootstrap here: it does not matter."""
    root = holder_copy(holder, tmp_path)
    make_member_pin_not_a_commit(root)
    module = doctor_module(standard)
    rows = rows_of(doctor(standard, root, "--json"))
    members = rows["members"]
    assert members["status"] == "FINDING", members
    assert "pin.commit" in members["reason"], members
    resolved = root.resolve()
    gate = module.validator_command(
        standard, resolved / "scripts" / "validate-family.py", True,
        ["--root", str(resolved)])
    assert command_of(members) == gate, members["next"]
    assert "validate-family.py" in command_of(members)
    assert "scripts/bootstrap.py" not in command_of(members), members["next"]
    assert " submodule update " not in command_of(members), members["next"]
    assert rows["family"]["status"] == "FINDING", rows["family"]
    assert command_of(rows["family"]) == command_of(members), (
        rows["family"]["next"], members["next"])


@pytest.mark.parametrize("breakage", ["head-unreadable",
                                      "no-git-of-its-own"])
def test_a_member_git_cannot_read_a_head_in_is_handed_the_family_gate(
        standard, holder, tmp_path, breakage):
    """The `legs` row's second kind, for a member: the gitdir is gone (the
    mount's `.git` file points at nothing), or the mount is a populated
    directory with no `.git` at all -- where git walks up and answers with
    the HOLDER's HEAD (`member_state`). `submodule update` and the holder's
    own bootstrap, which runs it, cure neither, and the holder HAS its
    bootstrap here: it does not matter."""
    root = holder_copy(holder, tmp_path)
    member = root / "members" / FAMILY_MEMBER
    rmtree(root / ".git" / "modules" / "members" / FAMILY_MEMBER)
    if breakage == "no-git-of-its-own":
        (member / ".git").unlink()
    module = doctor_module(standard)
    row = row_of(standard, root, "members")
    assert row["status"] == "FINDING", row
    resolved = root.resolve()
    assert command_of(row) == module.validator_command(
        standard, resolved / "scripts" / "validate-family.py", True,
        ["--root", str(resolved)]), row["next"]
    assert "scripts/bootstrap.py" not in command_of(row), row["next"]
    assert " submodule update " not in command_of(row), row["next"]


def test_a_holder_missing_its_own_family_gate_gets_the_templates(
        standard, holder, tmp_path):
    root = holder_copy(holder, tmp_path)
    make_member_pin_not_a_commit(root)
    git("rm", "-q", "scripts/validate-family.py", cwd=root)
    module = doctor_module(standard)
    members = row_of(standard, root, "members")
    gate = module.validator_command(
        standard, standard / "templates" / "family-root" / "scripts"
        / "validate-family.py", False, ["--root", str(root.resolve())])
    assert command_of(members) == gate, members["next"]
    assert "PYTHONPATH" in command_of(members), members["next"]


def test_a_holder_with_no_readable_family_gate_gets_no_line(
        standard, holder, tmp_path):
    """The `legs` row's rule, for the `members` row: no command is better
    than one that cannot run."""
    hollow = tmp_path / "hollow-standard"
    shutil.copytree(standard, hollow, symlinks=True)
    (hollow / "templates" / "family-root" / "scripts"
     / "validate-family.py").unlink()
    root = holder_copy(holder, tmp_path / "holder")
    make_member_pin_not_a_commit(root)
    git("rm", "-q", "scripts/validate-family.py", cwd=root)
    rows = rows_of(doctor(hollow, root, "--json"))
    assert rows["members"]["status"] == "FINDING", rows["members"]
    assert rows["members"]["next"] is None, rows["members"]


@WINDOWS_SKIP
def test_a_pasted_family_gate_line_runs_and_prints_its_finding(
        standard, holder, tmp_path):
    root = holder_copy(holder, tmp_path)
    make_member_pin_not_a_commit(root)
    git("rm", "-q", "scripts/validate-family.py", cwd=root)
    row = row_of(standard, root, "members")
    result = paste(row, tmp_path / "elsewhere", remotes_of(holder))
    output = result.stdout + result.stderr
    assert result.returncode in (1, 2), output
    assert "can't open file" not in output
    assert "ModuleNotFoundError" not in output


def test_an_empty_member_with_no_pin_is_still_a_checkout_first(
        standard, holder, tmp_path):
    """The members row keeps the legs row's precedence: what a checkout cures
    comes first. The fixture's holder has ONE member, so the two kinds are
    asserted on that one row, where `member_problem` reports the empty mount
    before the missing pin; the line is the checkout, and a re-run names the
    gate once the mount is there."""
    root = holder_copy(holder, tmp_path)
    make_member_pin_not_a_commit(root)
    holder_without(root, "bootstrap.py")
    member_unbootstrapped(root)
    module = doctor_module(standard)
    row = row_of(standard, root, "members")
    assert command_of(row) == (
        f"git -C {module.quote_arg(root.resolve())} {UPDATE} -- "
        f"members/{FAMILY_MEMBER}"), row["next"]
    submodule_update_through_git(root, holder["base"] / "remotes", "--init",
                                 "--recursive", "--",
                                 f"members/{FAMILY_MEMBER}")
    again = row_of(standard, root, "members")
    assert again["status"] == "FINDING", again
    assert "validate-family.py" in command_of(again), again["next"]


# --- #413: every detached commit the line moves is named --------------------
#
# The keep sentence named a mount only where the row had read a HEAD in it,
# detached off its pin. The line moves three more HEADs that can hold the
# only copy of a commit: the repository git kept for an emptied mount (a),
# every member the holder's own bootstrap updates (b), and a member's own
# legs, which `--recursive` checks out (c). Each test has the shape of
# `test_the_keep_line_in_the_explanation_keeps_a_detached_commit`: the
# commit is named before the paste, the keep line the row names, run first,
# leaves it on a branch, and without that line no ref holds it afterwards.

#: The keep line for a repository git kept (#413 a): it names the
#: REPOSITORY and the commit, and a work tree only where the mount directory
#: itself is gone.
KEPT_LINE = re.compile(r"git --git-dir=\S+(?: --work-tree=\S+)? branch NAME "
                       r"[0-9a-f]{40}")


def sh(line: str, cwd: Path) -> subprocess.CompletedProcess:
    """A line the row's `why` names, run as a reader pastes it: in a POSIX
    shell, from a directory that is not the root."""
    cwd.mkdir(exist_ok=True)
    return subprocess.run(["sh", "-c", line], cwd=str(cwd),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False, env=paste_env(),
                          stdin=subprocess.DEVNULL)


def kept_repository(root: Path, name: str) -> Path:
    """Where git keeps the repository of the submodule NAMED `name`."""
    where = Path(git("rev-parse", "--git-path", f"modules/{name}",
                     cwd=root).stdout.strip())
    return where if where.is_absolute() else root / where


def emptied_with_its_repository_kept(root: Path, mount: str) -> str:
    """A commit made on a mount's detached HEAD, and then the mount emptied
    with `git submodule deinit -f`, which KEEPS its repository: that
    commit's sha. The row reads no HEAD in an empty mount, and the update
    links the mount to the kept repository again and checks the gitlink out
    over the commit."""
    commit = commit_in(root / mount, "work on a detached HEAD, then deinit")
    git("submodule", "deinit", "-q", "-f", "--", mount, cwd=root)
    assert not any((root / mount).iterdir())
    return commit


def detached_member(root: Path) -> Path:
    """The fixture's member is on a branch (`git submodule add` checks one
    out); a fresh recursive clone of a holder leaves it detached, which is
    where a commit made in it is on no branch."""
    member = root / "members" / FAMILY_MEMBER
    git("checkout", "-q", "--detach", "HEAD", cwd=member)
    return member


def with_its_own_legs(root: Path, holder: dict) -> Path:
    """`family.py add` does not recurse, so the fixture's member has empty
    legs: fill them, as a recursive clone of the holder does, from the
    remotes the `holder` fixture made. Each is then detached at the commit
    the MEMBER records for it."""
    submodule_update_through_git(root, holder["base"] / "remotes", "--init",
                                 "--recursive", "--",
                                 f"members/{FAMILY_MEMBER}")
    return root / "members" / FAMILY_MEMBER


def test_413a_an_emptied_legs_kept_repository_names_its_detached_commit(
        standard, project):
    """(a) The mount is empty, so the row read no HEAD in it, and the line
    said nothing. git kept its repository, detached at a commit no branch
    holds, and the line moves it. The commit is named, by a keep line that
    names the REPOSITORY: run in the empty mount, git walks up and would
    branch the root."""
    commit = emptied_with_its_repository_kept(project, "spec")
    module = doctor_module(standard)
    row = row_of(standard, project, "legs")
    resolved = project.resolve()
    assert command_of(row) == (
        f"git -C {module.quote_arg(resolved)} {UPDATE} -- spec"), row["next"]
    why = why_of(row)
    repository = kept_repository(resolved, "spec")
    assert (f"git {module.quote_arg(f'--git-dir={repository}')} branch NAME "
            f"{commit}") in why, why
    assert "reflog" in why, why
    assert f"git -C {module.quote_arg(resolved / 'spec')} branch" not in why
    assert_fixed_words_are_plain(
        why, module.quote_arg(f"--git-dir={repository}"))


def test_413a_a_kept_repository_on_a_branch_or_at_the_gitlink_is_not_named(
        standard, project):
    """The same rule as a populated mount's, `left_in_reflog`: a kept HEAD
    on a branch keeps its commit there, and one at the gitlink does not
    move, so neither is a loss to warn about."""
    commit_in(project / "spec")
    git("checkout", "-q", "-B", "work", cwd=project / "spec")
    git("submodule", "deinit", "-q", "-f", "--", "spec", cwd=project)
    git("submodule", "deinit", "-q", "-f", "--", "code", cwd=project)
    why = why_of(row_of(standard, project, "legs"))
    assert "reflog" not in why, why
    assert "--git-dir" not in why, why


@WINDOWS_SKIP
def test_413a_the_keep_line_keeps_the_emptied_legs_commit_through_the_paste(
        standard, project, scaffolded_here, tmp_path):
    commit = emptied_with_its_repository_kept(project, "spec")
    row = row_of(standard, project, "legs")
    keep = KEPT_LINE.search(why_of(row))
    assert keep, why_of(row)
    kept = sh(keep.group(0).replace("NAME", "kept"), tmp_path / "keep")
    assert kept.returncode == 0, kept.stdout + kept.stderr
    result = paste(row, tmp_path / "elsewhere", remotes_of(scaffolded_here))
    assert result.returncode == 0, result.stdout + result.stderr
    assert row_of(standard, project, "legs")["status"] == "ok"
    assert "kept" in git("branch", "--contains", commit,
                         cwd=project / "spec").stdout


@WINDOWS_SKIP
def test_413a_without_the_keep_line_the_emptied_legs_commit_is_in_no_ref(
        standard, project, scaffolded_here, tmp_path):
    commit = emptied_with_its_repository_kept(project, "spec")
    result = paste(row_of(standard, project, "legs"), tmp_path / "elsewhere",
                   remotes_of(scaffolded_here))
    assert result.returncode == 0, result.stdout + result.stderr
    assert row_of(standard, project, "legs")["status"] == "ok"
    spec = project / "spec"
    assert git("for-each-ref", "--contains", commit,
               cwd=spec).stdout.strip() == ""
    assert git("rev-parse", "HEAD", cwd=spec).stdout.strip() != commit
    assert commit in git("reflog", cwd=spec).stdout


@WINDOWS_SKIP
def test_413a_with_the_mount_directory_gone_the_keep_line_still_runs(
        standard, project, scaffolded_here, tmp_path):
    """The kept repository's own `core.worktree` names the mount, and with
    that directory gone git refuses every command in the repository, the
    keep line included (`cannot chdir`, exit 128). The line then carries a
    `--work-tree`, and runs."""
    commit = emptied_with_its_repository_kept(project, "spec")
    (project / "spec").rmdir()
    row = row_of(standard, project, "legs")
    keep = KEPT_LINE.search(why_of(row))
    assert keep, why_of(row)
    assert "--work-tree=" in keep.group(0), why_of(row)
    kept = sh(keep.group(0).replace("NAME", "kept"), tmp_path / "keep")
    assert kept.returncode == 0, kept.stdout + kept.stderr
    result = paste(row, tmp_path / "elsewhere", remotes_of(scaffolded_here))
    assert result.returncode == 0, result.stdout + result.stderr
    assert row_of(standard, project, "legs")["status"] == "ok"
    assert "kept" in git("branch", "--contains", commit,
                         cwd=project / "spec").stdout


def test_413a_the_kept_repositorys_keep_line_is_spelled_for_the_readers_shell(
        standard):
    """`quote_arg` over the whole `--git-dir=` word, in both dialects: a
    root with a space is one argument to `sh` and to PowerShell."""
    module = doctor_module(standard)
    commit = "a" * 40
    _, why = module.submodule_update_next(
        PurePosixPath("/srv/my atlas"), ["spec"], [], "leg",
        platform="posix",
        kept=[(PurePosixPath("/srv/my atlas/.git/modules/spec"), commit,
               None)])
    assert (f"git '--git-dir=/srv/my atlas/.git/modules/spec' branch NAME "
            f"{commit}") in why, why
    _, why = module.submodule_update_next(
        PureWindowsPath("C:/Work/My Atlas"), ["spec"], [], "leg",
        platform="nt",
        kept=[(PureWindowsPath("C:/Work/My Atlas/.git/modules/spec"), commit,
               PureWindowsPath("C:/Work/My Atlas"))])
    assert ("git '--git-dir=C:\\Work\\My Atlas\\.git\\modules\\spec' "
            "'--work-tree=C:\\Work\\My Atlas' branch NAME " + commit) in why


def test_413a_an_emptied_members_kept_repository_names_its_detached_commit(
        standard, holder, tmp_path):
    """The members row takes the same rule: the holder's own bootstrap is
    the NEXT here, and it names the commit the kept repository holds."""
    root = holder_copy(holder, tmp_path)
    detached_member(root)
    commit = emptied_with_its_repository_kept(root, f"members/{FAMILY_MEMBER}")
    module = doctor_module(standard)
    row = row_of(standard, root, "members")
    assert row["status"] == "FINDING", row
    assert "bootstrap.py" in command_of(row), row["next"]
    repository = kept_repository(root.resolve(), f"members/{FAMILY_MEMBER}")
    assert (f"git {module.quote_arg(f'--git-dir={repository}')} branch NAME "
            f"{commit}") in why_of(row), why_of(row)


def test_413b_the_holders_own_bootstrap_names_a_detached_members_keep_line(
        standard, holder, tmp_path):
    """(b) The holder's own bootstrap runs the same update the git line does
    (`fetch_members`), so a commit made in the pinned, detached member is
    left in its reflog by it too. Its `why` carries the same sentence, built
    by the same function, `checkout_notes`, and the recursive one (c)."""
    root = holder_copy(holder, tmp_path)
    member = detached_member(root)
    commit_in(member)
    module = doctor_module(standard)
    row = row_of(standard, root, "members")
    assert row["status"] == "FINDING", row
    resolved = root.resolve()
    assert command_of(row) == (
        f"{module.PYTHON} "
        f"{module.quote_arg(resolved / 'scripts' / 'bootstrap.py')} "
        f"--root {module.quote_arg(resolved)}"), row["next"]
    why = why_of(row)
    assert module.checkout_notes("member", [member.resolve()]) in why, why
    assert f"git -C {module.quote_arg(member.resolve())} branch NAME" in why
    assert "git -C LEG branch NAME" in why, why


@WINDOWS_SKIP
def test_413b_the_keep_line_keeps_a_members_commit_through_the_bootstrap(
        standard, holder, tmp_path):
    root = holder_copy(holder, tmp_path)
    member = detached_member(root)
    commit = commit_in(member)
    row = row_of(standard, root, "members")
    keep = re.search(r"git -C \S+ branch NAME", why_of(row))
    assert keep, why_of(row)
    assert "LEG" not in keep.group(0), why_of(row)
    kept = sh(keep.group(0).replace("NAME", "kept"), tmp_path / "keep")
    assert kept.returncode == 0, kept.stdout + kept.stderr
    result = paste(row, tmp_path / "elsewhere", remotes_of(holder))
    assert result.returncode == 0, result.stdout + result.stderr
    assert row_of(standard, root, "members")["status"] == "ok"
    assert "kept" in git("branch", "--contains", commit, cwd=member).stdout


@WINDOWS_SKIP
def test_413b_without_it_the_holders_bootstrap_leaves_the_commit_in_no_ref(
        standard, holder, tmp_path):
    root = holder_copy(holder, tmp_path)
    member = detached_member(root)
    commit = commit_in(member)
    result = paste(row_of(standard, root, "members"), tmp_path / "elsewhere",
                   remotes_of(holder))
    assert result.returncode == 0, result.stdout + result.stderr
    assert row_of(standard, root, "members")["status"] == "ok"
    assert git("for-each-ref", "--contains", commit,
               cwd=member).stdout.strip() == ""
    assert commit in git("reflog", cwd=member).stdout


def made_in_a_members_own_leg(root: Path, holder: dict) -> tuple[Path, str]:
    """A commit in the member, so the row is red, and one in the member's
    own detached `spec` leg, which the row never reads: the leg and the
    second commit's sha."""
    member = with_its_own_legs(root, holder)
    git("checkout", "-q", "--detach", "HEAD", cwd=member)
    commit_in(member, "work in the member")
    leg = member / "spec"
    return leg, commit_in(leg, "work in the member's own leg")


def test_413c_the_members_git_line_says_it_checks_out_each_members_legs(
        standard, holder, tmp_path):
    """(c) `--recursive` checks out the member's own legs at the commits the
    MEMBER records, and the row walks into none of them. The `why` says so
    in general words, with the keep line to run in that leg first."""
    root = holder_copy(holder, tmp_path)
    holder_without(root, "bootstrap.py")
    leg, _ = made_in_a_members_own_leg(root, holder)
    module = doctor_module(standard)
    row = row_of(standard, root, "members")
    assert command_of(row) == (
        f"git -C {module.quote_arg(root.resolve())} {UPDATE} -- "
        f"members/{FAMILY_MEMBER}"), row["next"]
    why = why_of(row)
    assert "It is recursive" in why, why
    assert "the legs of each member" in why, why
    assert "git -C LEG branch NAME" in why, why
    assert_fixed_words_are_plain(why, module.quote_arg(leg.parent.resolve()))


@WINDOWS_SKIP
def test_413c_the_leg_keep_line_keeps_a_members_leg_commit_through_the_paste(
        standard, holder, tmp_path):
    root = holder_copy(holder, tmp_path)
    holder_without(root, "bootstrap.py")
    leg, commit = made_in_a_members_own_leg(root, holder)
    module = doctor_module(standard)
    row = row_of(standard, root, "members")
    keep = re.search(r"git -C LEG branch NAME", why_of(row))
    assert keep, why_of(row)
    kept = sh(keep.group(0).replace("LEG", module.quote_arg(leg.resolve()))
              .replace("NAME", "kept"), tmp_path / "keep")
    assert kept.returncode == 0, kept.stdout + kept.stderr
    result = paste(row, tmp_path / "elsewhere", remotes_of(holder))
    assert result.returncode == 0, result.stdout + result.stderr
    assert row_of(standard, root, "members")["status"] == "ok"
    assert "kept" in git("branch", "--contains", commit, cwd=leg).stdout


@WINDOWS_SKIP
def test_413c_without_it_the_members_leg_commit_is_in_no_ref(
        standard, holder, tmp_path):
    root = holder_copy(holder, tmp_path)
    holder_without(root, "bootstrap.py")
    leg, commit = made_in_a_members_own_leg(root, holder)
    result = paste(row_of(standard, root, "members"), tmp_path / "elsewhere",
                   remotes_of(holder))
    assert result.returncode == 0, result.stdout + result.stderr
    assert row_of(standard, root, "members")["status"] == "ok"
    assert git("for-each-ref", "--contains", commit,
               cwd=leg).stdout.strip() == ""
    assert commit in git("reflog", cwd=leg).stdout


# --- #414: four states the routing did not fit -----------------------------
#
# Each NEXT, pasted, turns the row `ok`, or the NEXT is None and the `why` or
# the reason names the state. A member reaches all four, so each is asked of
# the `members` row too.

def root_head(root: Path) -> str:
    return git("rev-parse", "HEAD", cwd=root).stdout.strip()


def test_414_1_a_mount_with_no_git_whose_repository_is_kept_gets_the_line(
        standard, project):
    """(1) The repository git kept is what `submodule update` routes on: it
    links the mount to it again. The row reads no HEAD in the mount, where
    git walks up and answered with the ROOT's, and quoted it as the leg's."""
    head = root_head(project)
    (project / "spec" / ".git").unlink()
    module = doctor_module(standard)
    row = row_of(standard, project, "legs")
    assert row["status"] == "FINDING", row
    assert head[:12] not in row["reason"], row["reason"]
    assert "no .git of its own" in row["reason"], row["reason"]
    [spec] = [leg for leg in row["detail"]["legs"] if leg["path"] == "spec"]
    assert spec["head"] is None, spec
    assert command_of(row) == (
        f"git -C {module.quote_arg(project.resolve())} {UPDATE} -- spec"
    ), row["next"]
    assert "git kept its repository" in why_of(row), why_of(row)
    assert "links the two again" in why_of(row), why_of(row)


@WINDOWS_SKIP
def test_414_1_pasted_the_line_links_the_mount_again_and_the_row_is_ok(
        standard, project, scaffolded_here, tmp_path):
    (project / "spec" / ".git").unlink()
    result = paste(row_of(standard, project, "legs"), tmp_path / "elsewhere",
                   remotes_of(scaffolded_here))
    assert result.returncode == 0, result.stdout + result.stderr
    after = row_of(standard, project, "legs")
    assert after["status"] == "ok", (after, result.stdout, result.stderr)


def test_414_1_with_the_repository_gone_too_the_gate_says_which(standard,
                                                                project):
    """The other half: no kept repository, so no update links anything. The
    lockstep gate stays the line, its `why` says why, and no HEAD is
    quoted."""
    head = root_head(project)
    make_mount_with_no_git_of_its_own(project)
    module = doctor_module(standard)
    row = row_of(standard, project, "legs")
    assert command_of(row) == pins_gate(module, standard, project, True), \
        row["next"]
    assert head[:12] not in row["reason"], row["reason"]
    assert "git kept no repository for it" in why_of(row), why_of(row)


def test_414_1_a_member_with_no_git_whose_repository_is_kept_is_a_checkout(
        standard, holder, tmp_path):
    """A member reaches (1): the holder's own bootstrap runs the update that
    links it again, and the row quotes no HEAD for it, the holder's least
    of all."""
    root = holder_copy(holder, tmp_path)
    head = root_head(root)
    (root / "members" / FAMILY_MEMBER / ".git").unlink()
    row = row_of(standard, root, "members")
    assert row["status"] == "FINDING", row
    assert head[:12] not in row["reason"], row["reason"]
    assert row["detail"]["members"][0]["head"] is None, row["detail"]
    assert "bootstrap.py" in command_of(row), row["next"]
    assert "links the two again" in why_of(row), why_of(row)


@WINDOWS_SKIP
def test_414_1_pasted_the_holders_bootstrap_links_the_member_again(
        standard, holder, tmp_path):
    root = holder_copy(holder, tmp_path)
    (root / "members" / FAMILY_MEMBER / ".git").unlink()
    result = paste(row_of(standard, root, "members"), tmp_path / "elsewhere",
                   remotes_of(holder))
    assert result.returncode == 0, result.stdout + result.stderr
    after = row_of(standard, root, "members")
    assert after["status"] == "ok", (after, result.stdout, result.stderr)


def test_414_2_an_unborn_head_in_a_leg_gets_no_line_and_a_why_naming_it(
        standard, project):
    """(2) An unborn HEAD is no lockstep fact: the gate says `pins ok` and
    the row stays red. No line cures it without choosing a commit for the
    person, so there is none, and the `why` says what the state is."""
    git("symbolic-ref", "HEAD", "refs/heads/never-made", cwd=project / "spec")
    row = row_of(standard, project, "legs")
    assert row["status"] == "FINDING", row
    assert row["next"] is None, row
    assert "never-made" in row["reason"], row["reason"]
    assert "no commit" in row["reason"], row["reason"]
    assert "names a branch with no commit" in why_of(row), why_of(row)
    assert "chooses" in why_of(row), why_of(row)
    assert "validate-pins" not in why_of(row), why_of(row)


def test_414_2_an_unborn_head_in_a_member_gets_no_line_either(
        standard, holder, tmp_path):
    """And in a member, though the holder HAS its own bootstrap: the
    update it runs cannot find a current revision either."""
    root = holder_copy(holder, tmp_path)
    git("symbolic-ref", "HEAD", "refs/heads/never-made",
        cwd=root / "members" / FAMILY_MEMBER)
    row = row_of(standard, root, "members")
    assert row["status"] == "FINDING", row
    assert row["next"] is None, row
    assert "never-made" in row["reason"], row["reason"]
    assert "names a branch with no commit" in why_of(row), why_of(row)


def without_a_url(root: Path, mount: str, how: str) -> None:
    """An emptied mount whose `.gitmodules` section is gone, or keeps its
    path and has lost its `url`: `git submodule update --init -- <mount>`
    exits 128 on both (`No url found`)."""
    git("submodule", "deinit", "-q", "-f", "--", mount, cwd=root)
    if how == "section":
        git("config", "-f", ".gitmodules", "--remove-section",
            f"submodule.{mount}", cwd=root)
    else:
        git("config", "-f", ".gitmodules", "--unset",
            f"submodule.{mount}.url", cwd=root)


@pytest.mark.parametrize("how", ["section", "url"])
def test_414_3_a_leg_gitmodules_gives_no_url_for_gets_no_line(
        standard, project, how):
    """(3) The git line would exit 128, and the gate names no `.gitmodules`
    entry (the next test pins both), so the NEXT is None and the `why`
    names the missing entry and who restores it. No command: one that
    restored `.gitmodules` from HEAD would discard an uncommitted edit."""
    without_a_url(project, "spec", how)
    row = row_of(standard, project, "legs")
    assert row["status"] == "FINDING", row
    assert row["next"] is None, row
    assert "no url for it in .gitmodules" in row["reason"], row["reason"]
    why = why_of(row)
    assert "no url for spec in .gitmodules" in why, why
    assert "history" in why, why
    assert "person" in why, why


def test_414_3_a_populated_leg_off_its_pin_with_no_url_gets_no_line_either(
        standard, project):
    """`--init` asks for the url of every path it is given, populated or
    not, so a leg the line would check out is held to it too."""
    make_detached_past_the_pin(project)
    git("config", "-f", ".gitmodules", "--remove-section", "submodule.spec",
        cwd=project)
    row = row_of(standard, project, "legs")
    assert row["status"] == "FINDING", row
    assert row["next"] is None, row
    assert "no url for spec in .gitmodules" in why_of(row), why_of(row)


@WINDOWS_SKIP
def test_414_3_neither_the_git_line_nor_the_gate_cures_a_leg_with_no_url(
        standard, project, tmp_path):
    """WHY THE NEXT IS NONE AND NOT THE GATE, pinned by what both do, so
    that the day either changes this says so: the git line exits 128 on `No
    url found`, and the gate refuses `pin-submodule-uninitialized` and
    names no `.gitmodules` entry at all."""
    without_a_url(project, "spec", "section")
    module = doctor_module(standard)
    line, _ = module.submodule_update_next(project.resolve(), ["spec"], [],
                                           "leg")
    result = sh(line, tmp_path / "elsewhere")
    assert result.returncode == 128, result.stdout + result.stderr
    assert "No url found" in result.stderr, result.stderr
    gate = sh(pins_gate(module, standard, project, True),
              tmp_path / "elsewhere")
    output = gate.stdout + gate.stderr
    assert gate.returncode != 0, output
    assert "pin-submodule-uninitialized" in output, output
    assert ".gitmodules" not in output, output


def test_414_3_a_gitmodules_deleted_from_the_working_tree_alone_is_read(
        standard, project):
    """git reads `.gitmodules` from the index when the working tree has
    none, and so does `gitmodules_entry`: the line is still handed over."""
    unbootstrap(project, "spec")
    (project / ".gitmodules").unlink()
    module = doctor_module(standard)
    row = row_of(standard, project, "legs")
    assert command_of(row) == (
        f"git -C {module.quote_arg(project.resolve())} {UPDATE} -- spec"
    ), row["next"]


#: `.gitmodules` UNMERGED, as a merge that changed one url two ways leaves
#: it: the base, ours and theirs, staged as stages 1, 2 and 3 (#733).
UNMERGED = tuple(b'[submodule "p"]\n\tpath = p\n\turl = /r/%s.git\n' % side
                 for side in (b"base", b"ours", b"theirs"))

#: `p`'s section in an index copy, with a url HEAD's copy does not give, and
#: a section after it with a bare `url`: git reads an index or HEAD copy up
#: to its first bad line and keeps what it read before (#733).
P_IN_THE_INDEX = b'[submodule "p"]\n\tpath = p\n\turl = /r/index.git\n'
BARE_URL = b'[submodule "q"]\n\tpath = q\n\turl\n'

#: What the index holds in place of `.gitmodules`, for a root whose working
#: tree has none and whose HEAD's copy gives the mount `p` its url, and the
#: `(name, url)` git then finds for `p` (#668). None stages no copy.
INDEX_COPIES = [
    pytest.param(b'[submodule "q"]\n\tpath = q\n\turl = /r/index.git\n',
                 (None, None), id="no-section-for-the-path"),
    pytest.param(None, ("p", "/r/head.git"), id="no-copy"),
    pytest.param(b'[submodule "p"\n\tpath = p\n', (None, None),
                 id="unparsable"),
    pytest.param(UNMERGED, (None, None), id="unmerged"),
    pytest.param(P_IN_THE_INDEX + BARE_URL, ("p", "/r/index.git"),
                 id="bare-url-after-the-path"),
    pytest.param(BARE_URL + P_IN_THE_INDEX, (None, None),
                 id="bare-url-before-the-path"),
    pytest.param(P_IN_THE_INDEX + b'[submodule "q"\n', ("p", "/r/index.git"),
                 id="unparsable-after-the-path"),
    pytest.param(P_IN_THE_INDEX + b'[submodule "q"]\n\tupdate = !echo\n',
                 (None, None), id="a-value-git-dies-on"),
    pytest.param(P_IN_THE_INDEX + BARE_URL + b"\tupdate = !echo\n",
                 ("p", "/r/index.git"), id="dies-on-past-a-bare-url"),
    pytest.param(P_IN_THE_INDEX + b'[submodule "q"]\n\tpath = q\n\tbranch\n',
                 ("p", "/r/index.git"), id="bare-branch-after-the-path"),
]


def repository_mounting_p(root: Path) -> None:
    """`root`, a new repository whose index holds a gitlink at `p`."""
    git("init", "-q", "-b", "main", ".", cwd=root)
    git("update-index", "--add", "--cacheinfo", f"160000,{'1' * 40},p",
        cwd=root)


def blob_of(root: Path, content: bytes) -> bytes:
    """The blob `content` is stored as in `root`, fed to git as bytes."""
    return subprocess.run(["git", "hash-object", "-w", "--stdin"],
                          cwd=str(root), input=content, capture_output=True,
                          check=True).stdout.strip()


def gitmodules_in_head_and_index(root: Path,
                                 index_copy: bytes | tuple | None):
    """`root`, a new repository with a gitlink at `p` and HEAD's
    `.gitmodules` giving it `/r/head.git`, with no `.gitmodules` in the
    working tree and `index_copy` staged in its place: a tuple of copies
    is staged unmerged, as stages 1, 2 and 3. Each copy and index record
    reaches git as bytes on stdin."""
    repository_mounting_p(root)
    (root / ".gitmodules").write_bytes(
        b'[submodule "p"]\n\tpath = p\n\turl = /r/head.git\n')
    git("add", ".gitmodules", cwd=root)
    git("commit", "-q", "-m", "Mount p", cwd=root)
    (root / ".gitmodules").unlink()
    if index_copy is None:
        git("rm", "-q", "--cached", ".gitmodules", cwd=root)
        return
    if isinstance(index_copy, bytes):
        git("update-index", "--cacheinfo", "100644,%s,.gitmodules"
            % blob_of(root, index_copy).decode("ascii"), cwd=root)
        return
    records = [b"0 %s\t.gitmodules\n" % (b"0" * 40)]
    records += [b"100644 %s %d\t.gitmodules\n" % (blob_of(root, copy), stage)
                for stage, copy in enumerate(index_copy, start=1)]
    subprocess.run(["git", "update-index", "--index-info"], cwd=str(root),
                   input=b"".join(records), capture_output=True, check=True)


def url_git_finds(root: Path, rel: str, name: str | None = None
                  ) -> str | None:
    """The url `git submodule init -- <rel>` copies into the root's config
    for the submodule NAMED `name` (`rel` by default), or None where git
    stops at `No url found` or refuses the file, exiting non-zero.

    A git that CRASHES answers nothing, and the test is skipped: git 2.43
    does on a bare `branch` (`xstrdup(NULL)`, exit 139), where git 2.55
    stops there as at any other bare key (#733)."""
    init = subprocess.run(["git", "submodule", "init", "--", rel],
                          cwd=str(root), capture_output=True, check=False)
    if init.returncode < 0 or init.returncode > 128:
        pytest.skip(f"this git crashed on `submodule init` (exit "
                    f"{init.returncode}), as git 2.43 does on a bare "
                    "`branch`: it gives no answer to compare")
    if init.returncode != 0:
        return None
    return git("config", "--get", f"submodule.{name or rel}.url",
               cwd=root).stdout.strip()


@pytest.mark.parametrize(("index_copy", "found"), INDEX_COPIES)
def test_668_with_none_in_the_working_tree_the_first_copy_alone_is_read(
        standard, tmp_path, index_copy, found):
    """With no `.gitmodules` in the working tree, git reads the index's
    copy, else HEAD's, and ONLY the first that exists, whatever it holds
    (#668). Each answer is git's own, from `git submodule init`:

    - an index copy with no section for the path: no url, although HEAD's
      copy gives one;
    - no copy in the index: HEAD's url. Main called the mount url-less
      there: its `--get-regexp` exits 1 over a blob that is not there,
      which it took for "read, and no section";
    - an index copy git cannot parse: no url, for git stops there. Reading
      on to HEAD's copy named a url and handed over a line that exits 128.
    - an unmerged `.gitmodules`: no url, for git reads no copy at all while
      it is unmerged (#733). Reading HEAD's named a url there.
    - an index copy git stops reading at a bad line: a bare valued key, or
      a line it cannot parse. The section before the line keeps its url,
      and one after it has none (#733).
    - a value git dies on (`git_dies_on`): no url for any path, unless git
      stopped reading before it.
    """
    gitmodules_in_head_and_index(tmp_path, index_copy)
    assert doctor_module(standard).gitmodules_entry(tmp_path, "p") == found
    assert url_git_finds(tmp_path, "p") == found[1]


def test_733_while_gitmodules_is_unmerged_a_resolved_copy_is_not_read(
        standard, tmp_path):
    """The conflict resolved in the working tree and not yet added: git
    still reads no copy, and says `No url found`. The doctor named the
    resolved url there (#733)."""
    gitmodules_in_head_and_index(tmp_path, UNMERGED)
    (tmp_path / ".gitmodules").write_bytes(
        b'[submodule "p"]\n\tpath = p\n\turl = /r/resolved.git\n')
    assert doctor_module(standard).gitmodules_entry(tmp_path, "p") == (
        None, None)
    assert url_git_finds(tmp_path, "p") is None


#: `p`'s section, then one line in another section, named first (#733).
P_THEN_A_LINE = (b'[submodule "p"]\n\tpath = p\n\turl = /r/p.git\n'
                 b'[submodule "%s"]\n\t%s\n')

#: `.gitmodules` files for a gitlink at `p` that git reads otherwise than as
#: they are written, each with the `(name, url)` git then finds for `p`, as
#: `git submodule init` says (#733). The controls git reads as written are
#: `a..b`, a plain `path = -p`, a bare `shallow`, an empty `ignore =` or
#: `branch =`, a bare key in a section git ignores, and each value of
#: `update`, `shallow` and `fetchRecurseSubmodules` git takes
#: (`git_dies_on`) or ignores.
GIT_SKIPS = [
    pytest.param(b'[submodule ""]\n\tpath = p\n\turl = /r/u.git\n',
                 (None, None), id="empty-name"),
    pytest.param(b'[submodule "../evil"]\n\tpath = p\n\turl = /r/u.git\n',
                 (None, None), id="dotdot-name"),
    pytest.param(b'[submodule "a/../b"]\n\tpath = p\n\turl = /r/u.git\n',
                 (None, None), id="dotdot-component"),
    pytest.param(b'[submodule "a\\\\..\\\\b"]\n\tpath = p\n'
                 b"\turl = /r/u.git\n", (None, None), id="dotdot-backslash"),
    pytest.param(b'[submodule "a..b"]\n\tpath = p\n\turl = /r/u.git\n',
                 ("a..b", "/r/u.git"), id="dots-in-a-name"),
    pytest.param(b'[submodule "q"]\n\tpath = p\n\turl = -u\n',
                 ("q", None), id="url-option"),
    pytest.param(b'[submodule "q"]\n\tpath = p\n\turl = /r/first.git\n'
                 b"\turl = -u\n", ("q", "/r/first.git"),
                 id="url-option-after-a-url"),
    pytest.param(b'[submodule "q"]\n\tpath = -p\n\turl = /r/u.git\n',
                 (None, None), id="path-option"),
    pytest.param(b'[submodule "q"]\n\tpath = p\n\tpath = -p\n'
                 b"\turl = /r/u.git\n", ("q", "/r/u.git"),
                 id="path-option-after-a-path"),
    pytest.param(b'[submodule "p"]\n\turl = /r/u.git\n', (None, None),
                 id="no-path"),
    *(pytest.param(b'[submodule "q"]\n\tpath = p\n\turl = /r/u.git\n\t%s\n'
                   % key, (None, None), id=f"bare-{key.decode()}")
      for key in (b"ignore", b"update", b"branch")),
    pytest.param(b'[submodule "q"]\n\tpath = p\n\turl\n', (None, None),
                 id="bare-url"),
    pytest.param(b'[submodule "q"]\n\tpath\n[submodule "r"]\n\tpath = p\n'
                 b"\turl = /r/r.git\n", (None, None), id="bare-path"),
    pytest.param(b'[submodule "q"]\n\tpath = p\n\turl = /r/u.git\n'
                 b"\tshallow\n", ("q", "/r/u.git"), id="bare-shallow"),
    # A key of `VALUED_KEYS` given an EMPTY value lists with a newline, and
    # git takes it: `valued` is the newline, not the value.
    pytest.param(b'[submodule "q"]\n\tpath = p\n\turl = /r/u.git\n'
                 b"\tignore =\n", ("q", "/r/u.git"), id="empty-ignore"),
    pytest.param(b'[submodule "q"]\n\tpath = p\n\turl = /r/u.git\n'
                 b"\tbranch =\n", ("q", "/r/u.git"), id="empty-branch"),
    pytest.param(b'[submodule "../evil"]\n\tpath\n[submodule "q"]\n'
                 b"\tpath = p\n\turl = /r/u.git\n", ("q", "/r/u.git"),
                 id="bare-path-in-an-ignored-section"),
    *(pytest.param(P_THEN_A_LINE % (section, line), found, id=label)
      for section, line, found, label in (
          (b"q", b"update = !echo", (None, None), "update-command"),
          (b"q", b"update = Merge", (None, None), "update-unknown"),
          (b"q", b"update = -x", (None, None), "update-dash"),
          (b"q", b"update = rebase", ("p", "/r/p.git"), "update-rebase"),
          (b"q", b"shallow = maybe", (None, None), "shallow-no-boolean"),
          (b"q", b"shallow = 2k", ("p", "/r/p.git"), "shallow-an-integer"),
          (b"q", b"shallow = 2g", (None, None), "shallow-past-an-int"),
          (b"q", b"shallow = 0x10", ("p", "/r/p.git"), "shallow-hex"),
          (b"q", b"shallow = 08", (None, None), "shallow-08-no-octal"),
          (b"q", b'shallow = " 1"', ("p", "/r/p.git"),
           "shallow-after-a-space"),
          (b"q", b'shallow = "\\t1"', ("p", "/r/p.git"),
           "shallow-after-a-tab"),
          (b"q", b'shallow = " true"', (None, None),
           "shallow-word-after-a-space"),
          (b"q", b"shallow = -2147483647", ("p", "/r/p.git"),
           "shallow-above-int-min"),
          (b"q", b"shallow = -2147483649", (None, None),
           "shallow-below-int-min"),
          (b"q", b"fetchRecurseSubmodules = sometimes", (None, None),
           "fetch-recurse-no-boolean"),
          (b"q", b"fetchRecurseSubmodules = on-demand", ("p", "/r/p.git"),
           "fetch-recurse-on-demand"),
          (b"../evil", b"update = !echo", ("p", "/r/p.git"),
           "update-command-in-an-ignored-section"))),
]


@pytest.mark.parametrize(("gitmodules", "found"), GIT_SKIPS)
def test_733_the_doctor_and_make_siblings_skip_what_git_skips(
        standard, siblings, tmp_path, gitmodules, found):
    """A section git ignores, a `path` or `url` it ignores, and a file it
    refuses whole name no url for `p`, in `gitmodules_entry`, in the
    `members` row's `mounted_from` and in `make siblings`, where git says
    `No url found` or `bad config line` and exits non-zero. Both tools read
    each of them as a member before (#733). Each `found` is git's own."""
    repository_mounting_p(tmp_path)
    (tmp_path / ".gitmodules").write_bytes(gitmodules)
    module = doctor_module(standard)
    assert module.gitmodules_entry(tmp_path, "p") == found
    assert url_git_finds(tmp_path, "p", found[0]) == found[1]
    assert module.mounted_from(tmp_path, "p", "Org/Repo") == (
        found[1] or "https://github.com/Org/Repo.git")
    assert siblings.submodule_urls(tmp_path).get("p") == found[1]


@pytest.mark.parametrize("value", [b"-2147483648", b"-2097152k", b"-2048m",
                                   b"-2g"])
def test_733_a_shallow_of_int_min_is_a_boolean_as_git_2_55_reads_it(
        standard, siblings, tmp_path, value):
    """-2**31, however it is spelled, is a boolean to git 2.55, which CI
    runs, and to the doctor and `make siblings`, which follow it (#733).
    git 2.43 dies on it (`-max / factor > val`), so the git at hand is
    asked last, and a git that dies on it skips the test with the
    reason."""
    repository_mounting_p(tmp_path)
    (tmp_path / ".gitmodules").write_bytes(
        P_THEN_A_LINE % (b"q", b"shallow = " + value))
    assert doctor_module(standard).gitmodules_entry(tmp_path, "p") == (
        "p", "/r/p.git")
    assert siblings.submodule_urls(tmp_path).get("p") == "/r/p.git"
    if url_git_finds(tmp_path, "p") is None:
        pytest.skip("this git dies on a `shallow` of -2**31, as git 2.43 "
                    "does; git 2.55, which CI runs, takes it")


@WINDOWS_SKIP
def test_414_3_pasted_there_the_line_runs_and_the_row_is_ok(
        standard, project, scaffolded_here, tmp_path):
    unbootstrap(project, "spec")
    (project / ".gitmodules").unlink()
    result = paste(row_of(standard, project, "legs"), tmp_path / "elsewhere",
                   remotes_of(scaffolded_here))
    assert result.returncode == 0, result.stdout + result.stderr
    assert row_of(standard, project, "legs")["status"] == "ok"


def test_414_3_a_member_gitmodules_gives_no_url_for_gets_no_line(
        standard, holder, tmp_path):
    """A member reaches (3), and the holder's own bootstrap is no line for
    it: it exits 0 with the fetch incomplete and the row as red as it was,
    and the family gate says `member-uninitialized`."""
    root = holder_copy(holder, tmp_path)
    without_a_url(root, f"members/{FAMILY_MEMBER}", "section")
    row = row_of(standard, root, "members")
    assert row["status"] == "FINDING", row
    assert row["next"] is None, row
    assert f"no url for members/{FAMILY_MEMBER} in .gitmodules" in \
        why_of(row), why_of(row)


def add_member_row(root: Path, project: str) -> None:
    """A second row in `family.yaml`, `project` at `members/<project>`, a
    copy of the first member's row, pin included."""
    manifest = root / "family.yaml"
    text = manifest.read_text(encoding="utf-8")
    first = text[text.index(f"  - project: {FAMILY_MEMBER}\n"):]
    row = first
    for was, now in ((f"project: {FAMILY_MEMBER}", f"project: {project}"),
                     (f"id: {FAMILY_MEMBER.lower()}",
                      f"id: {project.lower()}"),
                     (f"{FAMILY_NAME}/{FAMILY_MEMBER}",
                      f"{FAMILY_NAME}/{project}"),
                     (f"members/{FAMILY_MEMBER}", f"members/{project}")):
        assert row.count(was) == 1, (was, row)
        row = row.replace(was, now)
    with open(manifest, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.rstrip("\n") + "\n" + row)


def with_a_member_that_has_no_url(root: Path) -> None:
    """A second member, `Ghost`, at the first one's commit, whose
    `.gitmodules` section gives its path and NO url; and the first member
    emptied, so a checkout cures it. The holder's own bootstrap updates
    every member with no path named, and git stops that run at Ghost."""
    add_member_row(root, "Ghost")
    record_gitlink(root, "members/Ghost",
                   git("rev-parse", f"HEAD:members/{FAMILY_MEMBER}",
                       cwd=root).stdout.strip())
    git("config", "-f", ".gitmodules", "submodule.members/Ghost.path",
        "members/Ghost", cwd=root)
    (root / "members" / "Ghost").mkdir()
    member_unbootstrapped(root)


def test_414_3_a_member_with_no_url_takes_the_holders_bootstrap_off_the_line(
        standard, holder, tmp_path):
    """With a member the update cannot fetch beside one a checkout cures,
    the holder's own bootstrap would be stopped at the first (the next test
    pins it), so the line is the git line over the second alone, and says
    why it is not the bootstrap."""
    root = holder_copy(holder, tmp_path)
    with_a_member_that_has_no_url(root)
    module = doctor_module(standard)
    row = row_of(standard, root, "members")
    assert row["status"] == "FINDING", row
    assert command_of(row) == (
        f"git -C {module.quote_arg(root.resolve())} {UPDATE} -- "
        f"members/{FAMILY_MEMBER}"), row["next"]
    why = why_of(row)
    assert "can stop that run" in why, why
    assert "doctor again" in why, why


@WINDOWS_SKIP
def test_414_3_there_the_bootstrap_cures_nothing_and_the_git_line_cures_one(
        standard, holder, tmp_path):
    root = holder_copy(holder, tmp_path)
    with_a_member_that_has_no_url(root)
    module = doctor_module(standard)
    tried = tmp_path / "tried"
    shutil.copytree(root, tried, symlinks=True)
    bootstrap = sh(f"{module.PYTHON} "
                   f"{module.quote_arg(tried / 'scripts' / 'bootstrap.py')} "
                   f"--root {module.quote_arg(tried)}", tmp_path / "boot")
    output = bootstrap.stdout + bootstrap.stderr
    # It cures nothing, and since #648 it says so and fails: git stopped
    # at Ghost, whose section gives no url, before it checked out either.
    assert bootstrap.returncode == 1, output
    assert "git stopped at members/Ghost" in output, output
    assert "No url found" in output, output
    assert not any((tried / "members" / FAMILY_MEMBER).iterdir()), output
    result = paste(row_of(standard, root, "members"), tmp_path / "elsewhere",
                   remotes_of(holder))
    assert result.returncode == 0, result.stdout + result.stderr
    again = row_of(standard, root, "members")
    assert again["next"] is None, again
    assert "no url for members/Ghost" in why_of(again), why_of(again)


def make_gitlink_not_the_pin_in_an_emptied_mount(root: Path) -> None:
    """The gitlink moved to a commit made in the leg, the pin left, and the
    mount emptied with its repository kept, so the update can check the
    gitlink out: HEAD is then the gitlink and not the pin."""
    record_gitlink(root, "spec", commit_in(root / "spec"))
    git("submodule", "deinit", "-q", "-f", "--", "spec", cwd=root)


def make_pin_not_a_commit_in_an_emptied_mount(root: Path) -> None:
    make_pin_not_a_commit(root)
    unbootstrap(root, "spec")


@pytest.mark.parametrize("make", [make_pin_not_a_commit_in_an_emptied_mount,
                                  make_gitlink_not_the_pin_in_an_emptied_mount
                                  ], ids=["pin-not-40-hex",
                                          "gitlink-not-the-pin"])
def test_414_4_a_leg_the_line_checks_out_with_a_lockstep_fact_says_run_again(
        standard, project, make):
    """(4) The re-run sentence is asked per leg: the line checks the gitlink
    out, and a pin that is not 40 hex, or not the gitlink, is what the next
    run names. It was said only when ANOTHER leg was a lockstep one."""
    make(project)
    module = doctor_module(standard)
    row = row_of(standard, project, "legs")
    assert command_of(row) == (
        f"git -C {module.quote_arg(project.resolve())} {UPDATE} -- spec"
    ), row["next"]
    assert "doctor again" in why_of(row), why_of(row)


@WINDOWS_SKIP
def test_414_4_pasted_the_line_runs_and_the_rerun_names_the_pin(
        standard, project, scaffolded_here, tmp_path):
    make_pin_not_a_commit_in_an_emptied_mount(project)
    module = doctor_module(standard)
    result = paste(row_of(standard, project, "legs"), tmp_path / "elsewhere",
                   remotes_of(scaffolded_here))
    assert result.returncode == 0, result.stdout + result.stderr
    again = row_of(standard, project, "legs")
    assert again["status"] == "FINDING", again
    assert "40-hex" in again["reason"], again["reason"]
    assert command_of(again) == pins_gate(module, standard, project, True), \
        again["next"]


@pytest.mark.parametrize("bootstrap", ["with-its-own-bootstrap",
                                       "without-it"])
def test_414_4_a_member_the_line_checks_out_with_no_pin_says_run_again(
        standard, holder, tmp_path, bootstrap):
    """And a member: the holder's own bootstrap says it too."""
    root = holder_copy(holder, tmp_path)
    make_member_pin_not_a_commit(root)
    if bootstrap == "without-it":
        holder_without(root, "bootstrap.py")
    member_unbootstrapped(root)
    row = row_of(standard, root, "members")
    assert row["status"] == "FINDING", row
    assert (" submodule update " in command_of(row)) == (
        bootstrap == "without-it"), row["next"]
    assert "doctor again" in why_of(row), why_of(row)


# --- after review: a url the root's config keeps, a leg's own submodules, ---
# --- every member the holder's bootstrap moves, and `detached` ------------

def make_url_in_config_only(root: Path, how: str) -> None:
    """An INITIALIZED leg whose `.gitmodules` section kept its `path` and
    lost its `url` key. The root's own config still has the url `submodule
    init` copied into it, and `--init` reads that first, so the git line
    exits 0 here. Past its pin, or emptied by `rm`, which unlike `deinit`
    leaves the configured url where it is."""
    if how == "past-the-pin":
        make_detached_past_the_pin(root)
    else:
        rmtree(root / "spec")
        (root / "spec").mkdir()
    git("config", "-f", ".gitmodules", "--unset", "submodule.spec.url",
        cwd=root)
    assert git("config", "--get", "submodule.spec.url", cwd=root).stdout


@pytest.mark.parametrize("how", ["past-the-pin", "emptied-by-rm"])
def test_414_3_a_url_the_roots_config_keeps_still_gets_the_line(
        standard, project, how):
    """`.gitmodules` alone does not decide that git has no url: only a
    section that is gone, or one with no url where the root's config has
    none either, makes the line exit 128. Here the line is handed over, as
    main handed it over."""
    make_url_in_config_only(project, how)
    module = doctor_module(standard)
    row = row_of(standard, project, "legs")
    assert row["status"] == "FINDING", row
    assert command_of(row) == (
        f"git -C {module.quote_arg(project.resolve())} {UPDATE} -- spec"
    ), row["next"]
    assert "no url" not in row["reason"] + why_of(row), row


@WINDOWS_SKIP
@pytest.mark.parametrize("how", ["past-the-pin", "emptied-by-rm"])
def test_414_3_pasted_there_the_line_cures_the_row(
        standard, project, scaffolded_here, tmp_path, how):
    make_url_in_config_only(project, how)
    result = paste(row_of(standard, project, "legs"), tmp_path / "elsewhere",
                   remotes_of(scaffolded_here))
    assert result.returncode == 0, result.stdout + result.stderr
    after = row_of(standard, project, "legs")
    assert after["status"] == "ok", (after, result.stdout, result.stderr)


def member_url_in_config_only(root: Path) -> None:
    """The member's case: detached past its pin, its `.gitmodules` section
    without a `url` key, and the holder's config still holding one."""
    member = detached_member(root)
    commit_in(member)
    git("config", "-f", ".gitmodules", "--unset",
        f"submodule.members/{FAMILY_MEMBER}.url", cwd=root)
    assert git("config", "--get", f"submodule.members/{FAMILY_MEMBER}.url",
               cwd=root).stdout


def test_414_3_a_member_url_the_holders_config_keeps_still_gets_the_line(
        standard, holder, tmp_path):
    root = holder_copy(holder, tmp_path)
    member_url_in_config_only(root)
    row = row_of(standard, root, "members")
    assert row["status"] == "FINDING", row
    assert "bootstrap.py" in command_of(row), row["next"]
    assert "no url" not in why_of(row), why_of(row)


@WINDOWS_SKIP
def test_414_3_pasted_the_holders_bootstrap_cures_that_member(
        standard, holder, tmp_path):
    root = holder_copy(holder, tmp_path)
    member_url_in_config_only(root)
    result = paste(row_of(standard, root, "members"), tmp_path / "elsewhere",
                   remotes_of(holder))
    assert result.returncode == 0, result.stdout + result.stderr
    after = row_of(standard, root, "members")
    assert after["status"] == "ok", (after, result.stdout, result.stderr)


#: Section NAMES that are not ASCII (#732): one in Latin-1, which is not
#: UTF-8 at all, and one in UTF-8.
BYTE_NAMES = [pytest.param(b"members/caf\xe9", id="latin-1"),
              pytest.param(b"members/caf\xc3\xa9", id="utf-8")]

#: The locales the doctor runs under (#732): a UTF-8 one, `C`, and `C` with
#: Python's UTF-8 mode off, where its filesystem encoding is ASCII.
NAME_LOCALES = [pytest.param("UTF-8", {}, id="utf-8-locale"),
                pytest.param("C", {}, id="C"),
                pytest.param("C", {"PYTHONUTF8": "0"}, id="C-ascii-fs")]


def member_named(holder, tmp_path, monkeypatch, name: bytes, codeset: str,
                 env: dict) -> Path:
    """A copy of the holder whose member is the submodule NAMED `name`, as
    `git submodule add --name` names it: the `.gitmodules` header (then
    committed), the holder's config section, the repository git keeps and
    the mount's `.git` file all renamed, at the same path. The doctor is
    run under `codeset` and `env`. Skipped on Windows, whose command line is
    text and cannot carry a byte that is not UTF-8."""
    if os.name == "nt":
        pytest.skip("a Windows command line cannot carry the byte 0xE9")
    monkeypatch.setenv("LC_ALL", listed_locale(codeset))
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    root = holder_copy(holder, tmp_path)
    old = f"members/{FAMILY_MEMBER}".encode("ascii")
    gitmodules = root / ".gitmodules"
    gitmodules.write_bytes(gitmodules.read_bytes().replace(
        b'[submodule "' + old + b'"]', b'[submodule "' + name + b'"]'))
    subprocess.run(["git", "config", "--rename-section",
                    b"submodule." + old, b"submodule." + name],
                   cwd=str(root), capture_output=True, check=True)
    modules = os.fsencode(root / ".git" / "modules") + b"/"
    os.rename(modules + old, modules + name)
    gitfile = root / os.fsdecode(old) / ".git"
    gitfile.write_bytes(gitfile.read_bytes().replace(
        b"/modules/" + old, b"/modules/" + name))
    commit_all(root, "Name the member's section otherwise")
    return root


@pytest.mark.parametrize("name", BYTE_NAMES)
@pytest.mark.parametrize(("codeset", "env"), NAME_LOCALES)
def test_732_a_member_named_in_bytes_gets_its_keep_line(
        standard, holder, tmp_path, monkeypatch, name, codeset, env):
    """A commit on the detached HEAD of an emptied member whose section is
    named `caf\\xe9` gets the keep line, under every locale, as the ASCII
    one does (`test_413a_an_emptied_members_kept_repository_names_...`).
    The name was looked up as `caf\\ufffd`, so `kept_gitdir` found no
    repository and the commit was left in a reflog; and with Python's
    filesystem encoding ASCII, either name raised `UnicodeEncodeError`
    there, a traceback with no report."""
    root = member_named(holder, tmp_path, monkeypatch, name, codeset, env)
    detached_member(root)
    commit = emptied_with_its_repository_kept(root, f"members/{FAMILY_MEMBER}")
    assert f"branch NAME {commit}" in why_of(row_of(standard, root, "members"))


@pytest.mark.parametrize("name", BYTE_NAMES)
@pytest.mark.parametrize(("codeset", "env"), NAME_LOCALES)
def test_732_a_member_named_in_bytes_whose_url_the_config_keeps_has_one(
        standard, holder, tmp_path, monkeypatch, name, codeset, env):
    """A member whose section kept its path and lost its url, named
    `caf\\xe9`, has the url the holder's config keeps, under every locale,
    as the ASCII one does (`test_414_3_a_member_url_the_holders_config_
    keeps_still_gets_the_line`). `configured_url` asked git for
    `caf\\ufffd`'s url, and the member was called url-less."""
    root = member_named(holder, tmp_path, monkeypatch, name, codeset, env)
    commit_in(detached_member(root))
    subprocess.run(["git", "config", "-f", ".gitmodules", "--unset",
                    b"submodule." + name + b".url"],
                   cwd=str(root), capture_output=True, check=True)
    assert "no url" not in why_of(row_of(standard, root, "members"))


def test_a_leg_that_carries_submodules_says_the_line_moves_them_too(
        standard, project):
    """The `legs` line's `--recursive` checks out the submodules a leg
    carries of its own, at the commits the leg records, so a commit made on
    no branch in one of them is left in its reflog as a member's leg's is
    (#413 c). The row walks into none of them: a `.gitmodules` in the leg is
    what it asks, and the sentence is general, with a placeholder keep
    line. A leg with none gets no such sentence."""
    make_detached_past_the_pin(project)
    assert "LEG/SUB" not in why_of(row_of(standard, project, "legs"))
    (project / "spec" / ".gitmodules").write_bytes(
        b'[submodule "vendor/lib"]\n\tpath = vendor/lib\n'
        b"\turl = ../lib.git\n")
    why = why_of(row_of(standard, project, "legs"))
    assert "submodules a leg carries of its own" in why, why
    assert "git -C LEG/SUB branch NAME" in why, why


def with_a_submodule_in_the_leg(project: Path, tmp_path: Path) -> Path:
    """The spec leg mounts `vendor/lib` at a commit of its own, the root's
    gitlink and pin record that spec commit, a commit is made on the
    nested submodule's detached HEAD, and the leg walks past its pin: the
    line checks the leg out, and `--recursive` the nested one. Its sha."""
    lib = tmp_path / "lib"
    git("init", "-q", "-b", "main", str(lib), cwd=tmp_path)
    commit_in(lib, "the library")
    spec = project / "spec"
    git("-c", "protocol.file.allow=always", "submodule", "add", "-q",
        lib.as_posix(), "vendor/lib", cwd=spec)
    git("commit", "-q", "-m", "mount the library", cwd=spec)
    mounted = git("rev-parse", "HEAD", cwd=spec).stdout.strip()
    record_gitlink(project, "spec", mounted)
    pin = project / "contracts" / "spec-pin.yaml"
    pin.write_text(re.sub(r'(?m)^commit: "[0-9a-f]{40}"$',
                          f'commit: "{mounted}"',
                          pin.read_text(encoding="utf-8")), encoding="utf-8")
    nested = spec / "vendor" / "lib"
    git("checkout", "-q", "--detach", cwd=nested)
    commit = commit_in(nested, "work in the leg's own submodule")
    commit_in(spec)
    return commit


@WINDOWS_SKIP
def test_a_legs_own_submodule_keep_line_keeps_its_commit_through_the_paste(
        standard, project, scaffolded_here, tmp_path):
    commit = with_a_submodule_in_the_leg(project, tmp_path)
    module = doctor_module(standard)
    row = row_of(standard, project, "legs")
    keep = re.search(r"git -C LEG/SUB branch NAME", why_of(row))
    assert keep, why_of(row)
    nested = project / "spec" / "vendor" / "lib"
    kept = sh(keep.group(0).replace(
        "LEG/SUB", module.quote_arg(nested.resolve())).replace(
        "NAME", "kept"), tmp_path / "keep")
    assert kept.returncode == 0, kept.stdout + kept.stderr
    result = paste(row, tmp_path / "elsewhere", remotes_of(scaffolded_here))
    assert result.returncode == 0, result.stdout + result.stderr
    assert row_of(standard, project, "legs")["status"] == "ok"
    assert "kept" in git("branch", "--contains", commit, cwd=nested).stdout


@WINDOWS_SKIP
def test_without_it_the_legs_own_submodule_commit_is_in_no_ref(
        standard, project, scaffolded_here, tmp_path):
    commit = with_a_submodule_in_the_leg(project, tmp_path)
    nested = project / "spec" / "vendor" / "lib"
    result = paste(row_of(standard, project, "legs"), tmp_path / "elsewhere",
                   remotes_of(scaffolded_here))
    assert result.returncode == 0, result.stdout + result.stderr
    assert row_of(standard, project, "legs")["status"] == "ok"
    assert git("for-each-ref", "--contains", commit,
               cwd=nested).stdout.strip() == ""
    assert commit in git("reflog", cwd=nested).stdout


def clone_member(first: Path, ghost: Path) -> None:
    """`ghost`, a plain clone of the member at `first`, read through git
    (`cloned_just_pushed`): its own legs stay empty, as the first member's
    are, which a recursive clone would fill from the urls `.gitmodules`
    gives."""
    cloned_just_pushed(first, ghost, recurse=False)
    assert not any((ghost / "spec").iterdir()), "the clone filled a leg"


def with_a_second_member_off_its_gitlink(root: Path) -> tuple[Path, str]:
    """A second member, `Ghost`, a clone of the first, recorded at a commit
    that is not its pin and detached at another past that one; and the
    first member emptied, so the holder's own bootstrap is the NEXT. The row
    sends Ghost to the family gate, yet the bootstrap's update names no path
    and checks Ghost's gitlink out over its HEAD (#413 b): the commit that
    HEAD is on is the sha returned."""
    first = root / "members" / FAMILY_MEMBER
    ghost = root / "members" / "Ghost"
    url = git("config", "-f", ".gitmodules", "--get",
              f"submodule.members/{FAMILY_MEMBER}.url", cwd=root).stdout
    clone_member(first, ghost)
    add_member_row(root, "Ghost")
    git("config", "-f", ".gitmodules", "submodule.members/Ghost.path",
        "members/Ghost", cwd=root)
    git("config", "-f", ".gitmodules", "submodule.members/Ghost.url",
        url.strip(), cwd=root)
    git("checkout", "-q", "--detach", cwd=ghost)
    record_gitlink(root, "members/Ghost",
                   commit_in(ghost, "the commit the holder records"))
    stranded = commit_in(ghost, "work on no branch, past it")
    member_unbootstrapped(root)
    return ghost, stranded


def test_413b_the_bootstrap_names_every_member_it_moves_not_only_checkouts(
        standard, holder, tmp_path):
    """The holder's bootstrap moves a member the row hands to the gate as
    surely as one it hands to a checkout, so its keep line is named."""
    root = holder_copy(holder, tmp_path)
    ghost, _ = with_a_second_member_off_its_gitlink(root)
    module = doctor_module(standard)
    row = row_of(standard, root, "members")
    assert "bootstrap.py" in command_of(row), row["next"]
    assert f"git -C {module.quote_arg(ghost.resolve())} branch NAME" in \
        why_of(row), why_of(row)


@WINDOWS_SKIP
@pytest.mark.parametrize("keep_first", [True, False])
def test_413b_pasted_the_bootstrap_moves_that_member_off_its_commit(
        standard, holder, tmp_path, keep_first):
    """Run first, its keep line leaves the commit on a branch; without it,
    after the paste no ref holds the commit. The paste's exit is not the
    question: the member's own bootstrap may refuse a clone that is not its
    project, after the update has moved it."""
    root = holder_copy(holder, tmp_path)
    ghost, stranded = with_a_second_member_off_its_gitlink(root)
    row = row_of(standard, root, "members")
    if keep_first:
        keep = re.search(r"git -C (\S+) branch NAME", why_of(row))
        assert keep, why_of(row)
        kept = sh(keep.group(0).replace("NAME", "kept"), tmp_path / "keep")
        assert kept.returncode == 0, kept.stdout + kept.stderr
    paste(row, tmp_path / "elsewhere", remotes_of(holder))
    assert git("rev-parse", "HEAD", cwd=ghost).stdout.strip() != stranded
    holding = git("for-each-ref", "--contains", stranded,
                  "--format=%(refname:short)", cwd=ghost).stdout.split()
    assert holding == (["kept"] if keep_first else []), holding


def test_detached_answers_none_where_git_cannot_say(standard, project):
    """`symbolic-ref -q HEAD` exits 1 for a detached HEAD and 0 on a branch;
    any other exit is git unable to answer, which main read as detached."""
    module = doctor_module(standard)
    spec = project / "spec"
    assert module.detached(spec) is True
    git("checkout", "-q", "-B", "work", cwd=spec)
    assert module.detached(spec) is False
    rmtree(project / ".git" / "modules" / "spec")
    assert module.detached(spec) is None


def test_a_member_whose_gitdir_is_gone_is_not_called_detached(
        standard, holder, tmp_path):
    root = holder_copy(holder, tmp_path)
    rmtree(root / ".git" / "modules" / "members" / FAMILY_MEMBER)
    row = row_of(standard, root, "members")
    assert row["detail"]["members"][0]["detached"] is None, row["detail"]


def test_where_the_gate_is_the_line_the_states_no_line_cures_are_said(
        standard, project):
    """An unborn HEAD in one leg and a gitlink off the pin in the other: the
    gate is the NEXT, for the second, and the first is said beside it, with
    the same sentence it gets when it is the only one."""
    git("symbolic-ref", "HEAD", "refs/heads/never-made", cwd=project / "spec")
    record_gitlink(project, "code", commit_in(project / "code"))
    module = doctor_module(standard)
    row = row_of(standard, project, "legs")
    assert command_of(row) == pins_gate(module, standard, project, True), \
        row["next"]
    assert "names a branch with no commit" in why_of(row), why_of(row)
    assert "doctor again" in why_of(row), why_of(row)


# --- after verification: every member the holder's bootstrap stops at, the ---
# --- url read apart from git, a submodule whose directory is gone, and the ---
# --- members row's gate --------------------------------------------------

def with_a_second_member(root: Path, at_pin: bool, section: str) -> Path:
    """`Ghost`, a clone of the first member at that member's HEAD, with a
    `family.yaml` row copied from the first, pin included. Recorded at that
    pin, where the row has nothing to say of it, or at a commit made past
    it, which the row hands to the family gate. `section` is what
    `.gitmodules` says of it: `full`, `path-only` or `none`. It is never
    `submodule init`ed, so the holder's own config gives it no url."""
    first = root / "members" / FAMILY_MEMBER
    ghost = root / "members" / "Ghost"
    url = git("config", "-f", ".gitmodules", "--get",
              f"submodule.members/{FAMILY_MEMBER}.url", cwd=root).stdout
    clone_member(first, ghost)
    add_member_row(root, "Ghost")
    if section != "none":
        git("config", "-f", ".gitmodules", "submodule.members/Ghost.path",
            "members/Ghost", cwd=root)
    if section == "full":
        git("config", "-f", ".gitmodules", "submodule.members/Ghost.url",
            url.strip(), cwd=root)
    if at_pin:
        record_gitlink(root, "members/Ghost",
                       git("rev-parse", "HEAD", cwd=ghost).stdout.strip())
    else:
        git("checkout", "-q", "--detach", cwd=ghost)
        record_gitlink(root, "members/Ghost",
                       commit_in(ghost, "the commit the holder records"))
    return ghost


def beside_a_member_git_finds_no_url_for(root: Path, section: str,
                                         at_pin: bool) -> None:
    """IRRS emptied, so a checkout cures it, beside a populated `Ghost`
    that git finds no url for (`with_a_second_member`). The row never sends
    Ghost to a checkout: at its pin it passes it over, and off it hands it
    to the family gate. The holder's own bootstrap inits every gitlinked
    member all the same, and git stops it at Ghost."""
    with_a_second_member(root, at_pin=at_pin, section=section)
    member_unbootstrapped(root)


UNROUTED_NO_URL = pytest.mark.parametrize(
    "section, at_pin",
    [("none", True), ("path-only", True), ("none", False),
     ("path-only", False)],
    ids=["no-section-at-pin", "path-only-at-pin", "no-section-gate",
         "path-only-gate"])


@UNROUTED_NO_URL
def test_a_member_the_row_never_routes_with_no_url_takes_the_bootstrap_off(
        standard, holder, tmp_path, section, at_pin):
    """The holder's own bootstrap names no path, so a member git finds no
    url for stops it whether the row sends that member to a checkout or
    not. Every member with a gitlink is asked, the NEXT is the git line
    over the member a checkout cures, and the `why` names the one with no
    url."""
    root = holder_copy(holder, tmp_path)
    beside_a_member_git_finds_no_url_for(root, section, at_pin)
    module = doctor_module(standard)
    row = row_of(standard, root, "members")
    assert row["status"] == "FINDING", row
    assert command_of(row) == (
        f"git -C {module.quote_arg(root.resolve())} {UPDATE} -- "
        f"members/{FAMILY_MEMBER}"), row["next"]
    why = why_of(row)
    assert "can stop that run" in why, why
    assert "no url for members/Ghost" in why, why


@WINDOWS_SKIP
@UNROUTED_NO_URL
def test_pasted_there_the_git_line_fills_the_member_the_bootstrap_would_not(
        standard, holder, tmp_path, section, at_pin):
    """Pasted, the line exits 0 and fills IRRS, which the bootstrap left
    empty. With Ghost at its pin the row is then `ok`; off it, the row
    names Ghost alone, for the gate."""
    root = holder_copy(holder, tmp_path)
    beside_a_member_git_finds_no_url_for(root, section, at_pin)
    result = paste(row_of(standard, root, "members"), tmp_path / "elsewhere",
                   remotes_of(holder))
    assert result.returncode == 0, result.stdout + result.stderr
    assert any((root / "members" / FAMILY_MEMBER).iterdir())
    after = row_of(standard, root, "members")
    if at_pin:
        assert after["status"] == "ok", (after, result.stdout, result.stderr)
    else:
        assert after["status"] == "FINDING", after
        assert FAMILY_MEMBER not in after["reason"], after["reason"]
        assert "members/Ghost" in after["reason"], after["reason"]


def test_section_url_reads_gits_listing_and_the_last_value_wins(standard,
                                                                 tmp_path):
    """`section_url` is the pure half of `gitmodules_entry`: one `git config
    -z --list` listing in, `(name, url)` out. Fed git's own listing of a
    `.gitmodules` whose section NAME holds a space and a dot and gives its
    url twice, and of a path two sections give: the last value given wins
    each time, as git reads the file, and an empty url is no url.

    `--list` gives every key (#668), so the file holds keys no submodule
    has: a `path` and `url` in a section that is not `submodule`, given
    last, and in a `[submodule]` section with no subsection, which git
    ignores. A reading that cut `submodule.` off every key by its length
    took the first for a section named `gin` and the second for one named
    `''`."""
    module = doctor_module(standard)
    (tmp_path / ".gitmodules").write_bytes(
        b'[submodule "my lib.v2"]\n\tpath = vendor/lib\n'
        b"\turl = ../first.git\n\turl = ../second.git\n"
        b'[submodule "old"]\n\tpath = vendor/both\n\turl = ../old.git\n'
        b'[submodule "new"]\n\tpath = vendor/both\n\turl =\n'
        b"\tbranch = main\n"
        b"[submodule]\n\tpath = vendor/none\n\turl = ../nameless.git\n"
        b'[remote "origin"]\n\tpath = vendor/lib\n\turl = ../other.git\n')
    listing = git("config", "-z", "--file", ".gitmodules", "--list",
                  cwd=tmp_path).stdout
    assert module.section_url(listing, "vendor/lib") == (
        "my lib.v2", "../second.git"), listing
    assert module.section_url(listing, "vendor/both") == ("new", None), \
        listing
    assert module.section_url(listing, "vendor/none") == (None, None), \
        listing


#: The keep line for a commit in a submodule whose directory is gone: it
#: names that submodule's repository under the mount's own, with the root
#: as the work tree.
SPELLED = "git --git-dir=REPO/modules/SUB --work-tree=ROOT branch NAME HEAD"


def spelled_filled(module, repository: Path, sub: str, root: Path) -> str:
    """`SPELLED` with its placeholders filled in as a reader fills them:
    REPO the mount's git directory, SUB the submodule's name, ROOT the
    root, and the branch `kept`."""
    return (SPELLED
            .replace("--git-dir=REPO/modules/SUB", module.quote_arg(
                f"--git-dir={repository.as_posix()}/modules/{sub}"))
            .replace("--work-tree=ROOT", module.quote_arg(
                f"--work-tree={root.as_posix()}"))
            .replace("NAME", "kept"))


@WINDOWS_SKIP
def test_an_emptied_legs_own_submodule_is_kept_through_its_repository(
        standard, project, scaffolded_here, tmp_path):
    """`deinit` empties the leg and takes its submodule's directory with
    it, so `git -C LEG/SUB branch NAME` has nowhere to run and exits 128.
    The repository git kept for the leg keeps its submodule's under
    `modules/`, and the `why` spells the line through it: filled in and run
    first, it exits 0, and after the paste the commit is on that branch."""
    commit = with_a_submodule_in_the_leg(project, tmp_path)
    git("submodule", "deinit", "-q", "-f", "--", "spec", cwd=project)
    module = doctor_module(standard)
    row = row_of(standard, project, "legs")
    why = why_of(row)
    assert SPELLED in why, why
    assert "git -C LEG/SUB" not in why, why
    resolved = project.resolve()
    kept = sh(spelled_filled(module, kept_repository(resolved, "spec"),
                             "vendor/lib", resolved), tmp_path / "keep")
    assert kept.returncode == 0, kept.stdout + kept.stderr
    result = paste(row, tmp_path / "elsewhere", remotes_of(scaffolded_here))
    assert result.returncode == 0, result.stdout + result.stderr
    assert row_of(standard, project, "legs")["status"] == "ok"
    nested = project / "spec" / "vendor" / "lib"
    assert git("rev-parse", "HEAD", cwd=nested).stdout.strip() != commit
    assert "kept" in git("branch", "--contains", commit, cwd=nested).stdout


@WINDOWS_SKIP
def test_an_emptied_members_own_leg_is_kept_through_its_repository(
        standard, holder, tmp_path):
    """The members twin: the member is emptied by `deinit`, its legs'
    directories with it, and the line spelled through the repository git
    kept for the member keeps a commit made in its own `spec` leg."""
    root = holder_copy(holder, tmp_path)
    holder_without(root, "bootstrap.py")
    leg, commit = made_in_a_members_own_leg(root, holder)
    git("submodule", "deinit", "-q", "-f", "--", f"members/{FAMILY_MEMBER}",
        cwd=root)
    module = doctor_module(standard)
    row = row_of(standard, root, "members")
    why = why_of(row)
    assert SPELLED in why, why
    assert "git -C LEG branch" not in why, why
    resolved = root.resolve()
    repository = kept_repository(resolved, f"members/{FAMILY_MEMBER}")
    kept = sh(spelled_filled(module, repository, "spec", resolved),
              tmp_path / "keep")
    assert kept.returncode == 0, kept.stdout + kept.stderr
    result = paste(row, tmp_path / "elsewhere", remotes_of(holder))
    assert result.returncode == 0, result.stdout + result.stderr
    assert row_of(standard, root, "members")["status"] == "ok"
    assert git("rev-parse", "HEAD", cwd=leg).stdout.strip() != commit
    assert "kept" in git("branch", "--contains", commit, cwd=leg).stdout


@WINDOWS_SKIP
def test_a_leg_past_a_commit_that_dropped_its_submodule_still_names_it(
        standard, project, scaffolded_here, tmp_path):
    """The leg walks past its pin at a commit that removes its submodule,
    `.gitmodules` included, so its working tree carries none. The gitlink's
    commit still mounts it, and `--recursive` links the repository the leg
    keeps for it again and checks it out. The leg's own repository is asked
    for its `modules/`, the `why` spells the line through it, and that
    line, run first, keeps the commit."""
    commit = with_a_submodule_in_the_leg(project, tmp_path)
    spec = project / "spec"
    git("rm", "-q", "-f", "vendor/lib", cwd=spec)
    if (spec / ".gitmodules").exists():
        git("rm", "-q", "-f", ".gitmodules", cwd=spec)
    commit_in(spec, "drop the library")
    assert not (spec / ".gitmodules").exists()
    module = doctor_module(standard)
    row = row_of(standard, project, "legs")
    why = why_of(row)
    assert SPELLED in why, why
    repository = Path(git("rev-parse", "--absolute-git-dir",
                          cwd=spec).stdout.strip())
    resolved = project.resolve()
    kept = sh(spelled_filled(module, repository, "vendor/lib", resolved),
              tmp_path / "keep")
    assert kept.returncode == 0, kept.stdout + kept.stderr
    result = paste(row, tmp_path / "elsewhere", remotes_of(scaffolded_here))
    assert result.returncode == 0, result.stdout + result.stderr
    assert row_of(standard, project, "legs")["status"] == "ok"
    nested = spec / "vendor" / "lib"
    assert git("rev-parse", "HEAD", cwd=nested).stdout.strip() != commit
    assert "kept" in git("branch", "--contains", commit, cwd=nested).stdout


def test_where_the_gate_is_the_members_line_the_states_no_line_cures_are_said(
        standard, holder, tmp_path):
    """The members twin of the test above: an unborn HEAD in IRRS, and
    `Ghost` recorded off its pin. The family gate is the NEXT, for Ghost,
    and IRRS is said beside it, with the sentence it gets when it is the
    only one."""
    root = holder_copy(holder, tmp_path)
    with_a_second_member(root, at_pin=False, section="full")
    git("symbolic-ref", "HEAD", "refs/heads/never-made",
        cwd=root / "members" / FAMILY_MEMBER)
    module = doctor_module(standard)
    row = row_of(standard, root, "members")
    assert row["status"] == "FINDING", row
    resolved = root.resolve()
    assert command_of(row) == module.validator_command(
        standard, resolved / "scripts" / "validate-family.py", True,
        ["--root", str(resolved)]), row["next"]
    assert "names a branch with no commit" in why_of(row), why_of(row)
    assert "doctor again" in why_of(row), why_of(row)
