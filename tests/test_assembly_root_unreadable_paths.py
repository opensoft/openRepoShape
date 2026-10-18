# SPDX-License-Identifier: Apache-2.0
"""The assembly root's pinned `validate-manifest.py` and `bootstrap.py` name a
path this user cannot read, and never read it as absent (#430, slice D of
lane 1's plan, #430 issuecomment-6251069236).

THE DEFECT, measured at the v1.1.1 release commit 50178305 in a scaffold's
recursive clone, on Python 3.12.3 with the mode taken away, and under a
`sitecustomize` that answers as Python 3.14's `Path.is_file()`, `is_dir()`
and `exists()` do, False to ANY `OSError`:

  * `validate-manifest.py`, a `project.yaml` it cannot reach: a
    `PermissionError` traceback, exit 1, on 3.12; `manifest-missing` on 3.14.
  * `validate-manifest.py`, a declared referent's pin file it cannot reach:
    a traceback, exit 1; the finding `naming-referent-missing` on 3.14.
  * `bootstrap.py`, a `project.yaml` it cannot reach: a traceback; on 3.14 a
    project that elected nothing, and `bootstrap ok`, exit 0.
  * `bootstrap.py`, a `scripts/` it cannot search: a traceback in step (b);
    on 3.14 the three validators `SKIPPED` as absent, and `bootstrap ok`.
  * `bootstrap.py`, a leg mount it cannot search: a traceback in step (a);
    on 3.14 the leg NOT INITIALIZED.
  * `bootstrap.py`, a `governance/` it cannot search: a traceback in step
    (c); on 3.14 `authority is not wallet-carried in this org`.
  * `bootstrap.py`, a leg's `sequencer/` it cannot search over a cherry-pick
    that is not done: on EVERY Python `os.path.lexists` read the marker as
    absent, and the leg was put on its tracking branch, where the pick's
    `--continue` goes on.

THE RULE NOW, lane 1's for every slice. The path is `stat`ed: ENOENT, ENOTDIR,
EBADF and ELOOP (and Windows' 21, 123 and 1921) mean absent, and any other
`OSError` is named `<path relative to the root>: cannot be read (<reason>)`,
in `validate-pins.py`'s words, with its cure: `chmod u+r` a file and `chmod
u+rx` a directory and every one above it, or, for another cause, its
`OTHER_REASON`.
  * A `project.yaml`, a validator or a declared referent's pin file is a
    refusal, exit 2, and a `project.yaml` this user cannot OPEN says the same
    line as one it cannot reach.
  * A leg's `.git`, or an operation's marker in its git dir, is a line in
    step (a), and the leg is left as it is; a register is a line in step
    (c), and nothing is claimed from it. Neither step fails the run, as
    neither did before: the validators refuse such a leg.

THE HARNESS. Each refusal is asked twice and must say the same both times:
as a project runs the tool, with the mode taken away (POSIX, and not as
root, who reads through any mode), and in-process under `refused_stat`
(`tests/test_bump_leg_unopenable.py`), which answers as Python 3.14 does on
any Python, as root and on every platform. A `project.yaml` or a pin file is
reached through a symlink into a folder nobody may enter, since the root
itself cannot be one: no tool finds a root it cannot search.
"""

from __future__ import annotations

import errno
import os
import shutil
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import (NO_BYTECODE, REPO, clear_ambient_pin_sources, git,
                      load_without_bytecode, run_script)
from test_bump_leg_unopenable import refused_stat
from test_manifest_validator import as_a_descendant_by_chain, link_tree
from test_validate_pins_named_and_spelled import (
    AGAIN, OTHER, PERMISSION, failing, os_error,
)
from test_validate_pins_unreadable_workflow import CANNOT_RUN_AS_ROOT
from test_validate_pins_unreadable_workflows_dir import mode_of

TEMPLATES = REPO / "templates" / "assembly-root" / "scripts"
#: A symlink a test makes, which a Windows account may not.
POSIX_LINKS = pytest.mark.skipif(
    os.name == "nt", reason="makes a symlink, which Windows may refuse")

#: What each refusal's remedy says the file is read for.
MANIFEST_READS = (
    "Remediation: this validator reads project.yaml, the naming policy and "
    "the pin file each declared referent needs, and one it cannot read is a "
    "question it cannot answer, never a pass. ")
BOOTSTRAP_READS = (
    "Remediation: this command reads project.yaml for the legs it places and "
    "the validators it runs, and one it cannot read is not one that is "
    "absent, which would place no leg and check nothing. ")
VALIDATOR_READS = (
    "Remediation: step (b) runs each neutral validator it finds and skips "
    "only one that is not there, and one it cannot read is a check that "
    "cannot run, never a pass. ")

#: The pin file `as_a_descendant_by_chain` makes the root hold: its chain's
#: first link's.
PIN = "contracts/openxdox-pin.yaml"
REGISTER = "governance/review-authority/register.yaml"
GRANTS = ("  Grants are read here for REPORTING only. This command confers "
          "nothing and enforces nothing; a required check in the repository "
          "that owns the object is what confers.")
DEGRADE = [
    "authority is not wallet-carried in this org",
    "  (no `governance/review-authority/register.yaml` in the assembly root "
    "or in any leg. Wallet-carried authority is an OVERLAY; the shape confers "
    "nothing without it, and nothing with it.)"]


def refused(code: str, named: str, reads: str,
            reason: str = "Permission denied",
            advice: str = PERMISSION) -> str:
    """The whole of stderr for a file the tool cannot reach or open: the
    file named once, relative to the root, with the system's reason, then
    what it is read for and the cure for that reason."""
    return (f"REFUSED {code}: {named}: cannot be read ({reason})\n"
            f"{reads}{advice}{AGAIN}\n")


def left_as_it_is(named: str, reason: str = "Permission denied",
                  advice: str = PERMISSION) -> list[str]:
    """Step (a)'s two lines for the spec leg, where `named` cannot be read."""
    return [f"  [spec] spec: {named}: cannot be read ({reason}), so the leg "
            "is left as it is", f"          {advice}{AGAIN}"]


def nothing_claimed(named: str) -> list[str]:
    """Step (c)'s lines for a register at `named` this user cannot read."""
    return [f"  register: {named}",
            f"    unreadable, so nothing is claimed from it: {named}: cannot "
            "be read (Permission denied)", f"      {PERMISSION}{AGAIN}"]


def placed(root: Path, role: str) -> str:
    """Step (a)'s line for a leg of a fresh clone, put on `main` at its pin."""
    pin = git("rev-parse", f"HEAD:{role}", cwd=root).stdout.strip()
    return f"  [{role}] {role}: on main at {pin[:12]} (branch tip == pin)"


def skipping_validators(root: Path, step_a: list[str],
                        step_c: list[str]) -> str:
    """The whole of stdout of `bootstrap.py --skip-validators` in `root`."""
    return "\n".join([
        f"bootstrap: Atlas ({root.resolve()})", "",
        "(a) legs on tracking branches, pins untouched", *step_a, "",
        "(b) neutral validators", "  skipped (--skip-validators)", "",
        "(c) review authority", *step_c, "", "bootstrap ok", ""])


def validate(root: Path, *args: str):
    return run_script(root / "scripts" / "validate-manifest.py", *args,
                      cwd=root)


def bootstrap(root: Path, *args: str):
    return run_script(root / "scripts" / "bootstrap.py", *args, cwd=root,
                      env={"SHAPE_UPSTREAM_PATH": ""})


def behind_a_locked_folder(root: Path, relative: str):
    """Move `relative` into a folder beside the root, leave a symlink to it
    in its place, and return the context in which nobody may enter it."""
    locked = root.parent / "locked"
    locked.mkdir()
    real = root / relative
    shutil.move(str(real), str(locked / real.name))
    real.symlink_to(os.path.relpath(locked / real.name, real.parent))
    return mode_of(root.parent, "locked", 0)


def at_mode_000(root: Path, relative: str):
    """The context in which nobody may read `relative`."""
    return mode_of(root, relative, 0)


UNREACHABLE = pytest.mark.parametrize(
    "how", [behind_a_locked_folder, at_mode_000],
    ids=["behind-a-folder-nobody-may-enter", "at-mode-000"])


def still_detached(root: Path, role: str) -> bool:
    """Whether the leg's HEAD is still detached, as a fresh clone left it."""
    return git("symbolic-ref", "-q", "HEAD", cwd=root / role,
               check=False).returncode != 0


@pytest.fixture(scope="module")
def manifest_gate():
    """The standard's `validate-manifest.py`, loaded by path."""
    return load_without_bytecode(TEMPLATES / "validate-manifest.py",
                                 "unreadable_paths_validate_manifest")


@pytest.fixture(scope="module")
def boot():
    """The standard's assembly-root `bootstrap.py`, loaded by path."""
    return load_without_bytecode(TEMPLATES / "bootstrap.py",
                                 "unreadable_paths_bootstrap")


def held_by_chain(root: Path) -> None:
    """The manifest declares descent through a chain whose first link's pin
    file the root holds, with the link's tree beside it: a valid manifest
    that asks whether `PIN` is there."""
    as_a_descendant_by_chain(root)
    (root / PIN).write_text("schema_version: 1\n"
                            "kind: pinned_contract_manifest\n")
    link_tree(root.parent / "openXdox", "openDox")


# --- validate-manifest.py: project.yaml --------------------------------------

@CANNOT_RUN_AS_ROOT
@UNREACHABLE
def test_a_manifest_the_gate_cannot_reach_or_open_is_refused_by_name(
        project, how):
    """Behind a folder nobody may enter, the base's 3.12 ended in a
    traceback; at mode 000 it named the absolute path, with no remedy. Both
    are one refusal now, and with the mode put back the gate passes."""
    with how(project, "project.yaml"):
        result = validate(project)
    assert result.stderr == refused("yaml-unreadable", "project.yaml",
                                    MANIFEST_READS), result.stderr
    assert result.returncode == 2, result.stdout
    assert result.stdout == ""
    assert validate(project).returncode == 0


def test_a_manifest_whose_stat_is_refused_is_the_same_refusal(
        manifest_gate, project, monkeypatch, capsys):
    """On every Python: 3.14's `is_file()` said False, and the base refused
    `manifest-missing` over a file that is there."""
    refused_stat(monkeypatch, "project.yaml")
    assert manifest_gate.main(["--root", str(project)]) == 2
    seen = capsys.readouterr()
    assert seen.err == refused("yaml-unreadable", "project.yaml",
                               MANIFEST_READS)
    assert seen.out == ""


# --- validate-manifest.py: a declared referent's pin file --------------------

@CANNOT_RUN_AS_ROOT
@POSIX_LINKS
def test_a_referent_pin_the_gate_cannot_reach_is_refused_not_missing(
        project):
    """The base's 3.12 ended in a traceback, and 3.14 found
    `naming-referent-missing`, a file that is there said not to exist."""
    held_by_chain(project)
    with behind_a_locked_folder(project, PIN):
        result = validate(project)
    assert result.stderr == refused("yaml-unreadable", PIN, MANIFEST_READS)
    assert result.returncode == 2, result.stdout
    assert validate(project).returncode == 0


@CANNOT_RUN_AS_ROOT
def test_a_contracts_folder_the_gate_cannot_search_names_the_pin(project,
                                                                 tmp_path):
    """`contracts/` at mode 000, the naming policy given elsewhere with
    `--policy`: the pin file is the first thing in it the gate looks for."""
    held_by_chain(project)
    policy = tmp_path / "repository-naming.yaml"
    shutil.copy2(project / "contracts" / "repository-naming.yaml", policy)
    with at_mode_000(project, "contracts"):
        result = validate(project, "--policy", str(policy))
    assert result.stderr == refused("yaml-unreadable", PIN, MANIFEST_READS)
    assert result.returncode == 2, result.stdout


@pytest.mark.parametrize("failure, advice", [
    pytest.param(None, PERMISSION, id="permission"),
    pytest.param(os_error(errno.EIO), OTHER, id="io-error"),
])
def test_a_referent_pin_whose_stat_is_refused_is_refused_on_every_python(
        manifest_gate, project, monkeypatch, capsys, failure, advice):
    """`refused_stat` answers as 3.14 does, where the base said the pin was
    missing; an I/O error is no permission, and is not told to `chmod`."""
    held_by_chain(project)
    clear_ambient_pin_sources(monkeypatch)
    if failure is None:
        refused_stat(monkeypatch, "openxdox-pin.yaml")
    else:
        failing(monkeypatch, "stat", {"openxdox-pin.yaml": failure})
    assert manifest_gate.main(["--root", str(project)]) == 2
    reason = "Permission denied" if failure is None else failure.strerror
    assert capsys.readouterr().err == refused(
        "yaml-unreadable", PIN, MANIFEST_READS, reason, advice)


@POSIX_LINKS
@pytest.mark.parametrize("target", ["nowhere-pin.yaml", "openxdox-pin.yaml"],
                         ids=["dangling-link", "link-to-itself"])
def test_a_referent_pin_that_is_not_there_is_still_missing(project, target):
    """THE OTHER HALF, which the base answered the same: a link to nothing
    (ENOENT) or to itself (ELOOP) is no pin file, and the finding stands."""
    held_by_chain(project)
    pin = project / PIN
    pin.unlink()
    pin.symlink_to(target)
    result = validate(project)
    assert result.stderr == (
        "FINDING naming-referent-missing: leg 'assembly': openXdox is the "
        "first link of this leg's recorded chain, reaching openDox, but "
        f"{PIN} does not exist. A declared pin that is not in the tree is a "
        "claim wearing the costume of a referent.\n\n1 finding(s) in "
        f"{project.resolve() / 'project.yaml'}\n"), result.stderr
    assert result.returncode == 1


# --- bootstrap.py: project.yaml ----------------------------------------------

@CANNOT_RUN_AS_ROOT
@UNREACHABLE
def test_a_manifest_bootstrap_cannot_reach_or_open_is_refused_first(project,
                                                                   how):
    """The base's 3.12 ended in a traceback, and its 3.14 placed no leg, ran
    no validator and said `bootstrap ok`; at mode 000 it named the absolute
    path, with no remedy. Refused before the first line, and no leg moves."""
    with how(project, "project.yaml"):
        result = bootstrap(project)
    assert result.stderr == refused("yaml-unreadable", "project.yaml",
                                    BOOTSTRAP_READS), result.stderr
    assert result.returncode == 2
    assert result.stdout == ""
    assert still_detached(project, "spec")


def test_a_manifest_bootstrap_cannot_stat_is_the_same_refusal(boot, project,
                                                              monkeypatch):
    refused_stat(monkeypatch, "project.yaml")
    with pytest.raises(boot.Refusal) as caught:
        boot._load_root_and_manifest(SimpleNamespace(root=project))
    assert f"{caught.value}\n" == refused("yaml-unreadable", "project.yaml",
                                          BOOTSTRAP_READS)


# --- bootstrap.py: the validators --------------------------------------------

@CANNOT_RUN_AS_ROOT
def test_a_scripts_folder_bootstrap_cannot_search_is_refused_not_skipped(
        project):
    """THE FALSE PASS. Run as this standard's `bootstrap` runs a project's,
    from outside its `scripts/`: on the base's 3.14 each validator was
    `SKIPPED` as absent and the run said `bootstrap ok`. The first one is
    refused by name, after step (a) and before any validator runs."""
    with at_mode_000(project, "scripts"):
        result = run_script(REPO / "bootstrap", cwd=project,
                            env={"SHAPE_UPSTREAM_PATH": "", **NO_BYTECODE})
    assert result.stderr == refused(
        "validator-unreadable", "scripts/validate-repository-naming.py",
        VALIDATOR_READS), result.stderr
    assert result.returncode == 2
    assert result.stdout == "\n".join([
        f"bootstrap: Atlas ({project.resolve()})", "",
        "(a) legs on tracking branches, pins untouched",
        placed(project, "spec"), placed(project, "code"), "",
        "(b) neutral validators", ""])


def test_a_validator_whose_stat_is_refused_stops_step_b_before_any_runs(
        boot, project, monkeypatch, capsys):
    """On every Python, the second validator: the base SKIPPED it and ran
    the other two. Nothing is run or said before the refusal."""
    manifest = boot.load_yaml(project / "project.yaml")
    refused_stat(monkeypatch, "validate-manifest.py")
    with pytest.raises(boot.Refusal) as caught:
        boot._run_neutral_validators(project, manifest, False)
    assert f"{caught.value}\n" == refused(
        "validator-unreadable", "scripts/validate-manifest.py",
        VALIDATOR_READS)
    assert capsys.readouterr().out == ""


def test_a_validator_that_is_not_there_is_still_skipped(boot, project,
                                                        monkeypatch, capsys):
    """THE OTHER HALF, which the base answered the same. The validators are
    stood in for: what is asked is which of them step (b) runs, and a
    pinned copy taken away is `validate-pins.py`'s own finding."""
    monkeypatch.delenv("SHAPE_UPSTREAM_PATH", raising=False)
    ran = []
    monkeypatch.setattr(boot, "_run",
                        lambda root, argv: ran.append(argv[0]) or 0)
    manifest = boot.load_yaml(project / "project.yaml")
    (project / "scripts" / "validate-repository-naming.py").unlink()
    assert boot._run_neutral_validators(project, manifest, False) == []
    assert ran == ["scripts/validate-manifest.py", "scripts/validate-pins.py"]
    assert capsys.readouterr().out == (
        "  naming: scripts/validate-repository-naming.py is absent; "
        "SKIPPED\n  --- manifest ---\n  --- pins ---\n")


# --- bootstrap.py: a leg -----------------------------------------------------

@CANNOT_RUN_AS_ROOT
def test_a_leg_bootstrap_cannot_search_is_left_as_it_is(project):
    """The base's 3.12 ended in a traceback in step (a), and its 3.14 said
    NOT INITIALIZED of an initialized leg. Step (a) names the `.git` it
    cannot reach and goes on, and so does step (c), where a register could
    be; the validators refuse the leg, so the run ends refused."""
    with at_mode_000(project, "spec"):
        skipped = bootstrap(project, "--skip-validators")
        result = bootstrap(project)
    assert skipped.stdout == skipping_validators(
        project, [*left_as_it_is("spec/.git"), placed(project, "code")],
        [*nothing_claimed(f"spec/{REGISTER}"), GRANTS]), skipped.stdout
    assert skipped.stderr == ""
    assert skipped.returncode == 0
    assert result.stderr.splitlines()[-1] == (
        "bootstrap REFUSED: pins (exit 2)"), result.stderr
    assert result.returncode == 2
    assert still_detached(project, "spec")


@pytest.mark.parametrize("failure, advice", [
    pytest.param(None, PERMISSION, id="permission"),
    pytest.param(os_error(errno.EIO), OTHER, id="io-error"),
])
def test_a_leg_whose_stat_is_refused_is_not_uninitialized(
        boot, project, monkeypatch, capsys, failure, advice):
    if failure is None:
        refused_stat(monkeypatch, ".git")
    else:
        failing(monkeypatch, "stat", {".git": failure})
    boot.checkout_tracking_branch(project.resolve(),
                                  {"role": "spec", "path": "spec"}, "main")
    reason = "Permission denied" if failure is None else failure.strerror
    assert capsys.readouterr().out.splitlines() == left_as_it_is(
        "spec/.git", reason, advice)


@CANNOT_RUN_AS_ROOT
def test_an_operation_bootstrap_cannot_see_keeps_the_leg_where_it_is(
        project):
    """A cherry-pick of several commits stopped and committed by hand
    leaves `sequencer/todo`. With `sequencer/` at mode 000 the base, on
    every Python, put the leg on `main`; now it is named and the leg stays
    detached at its pin."""
    spec = project / "spec"
    gitdir = Path(git("rev-parse", "--absolute-git-dir",
                      cwd=spec).stdout.strip())
    (gitdir / "sequencer").mkdir()
    head = git("rev-parse", "HEAD", cwd=spec).stdout.strip()
    (gitdir / "sequencer" / "todo").write_text(f"pick {head} x\n")
    named = (gitdir / "sequencer" / "todo").relative_to(project.resolve())
    with mode_of(gitdir, "sequencer", 0):
        result = bootstrap(project, "--skip-validators")
    assert result.stdout == skipping_validators(
        project, [*left_as_it_is(named.as_posix()), placed(project, "code")],
        DEGRADE), result.stdout
    assert result.returncode == 0
    assert still_detached(project, "spec")


@pytest.mark.parametrize("marker, named", [
    ("MERGE_HEAD", "MERGE_HEAD"), ("todo", "sequencer/todo")],
    ids=["a-merge", "a-sequence"])
def test_a_marker_whose_lstat_is_refused_keeps_the_leg_on_every_python(
        boot, project, monkeypatch, capsys, marker, named):
    """`os.path.lexists` answered False to a refused `lstat` on every
    Python, so the leg was placed. Each of the two places a marker is
    asked, the operations' and the sequence's."""
    failing(monkeypatch, "lstat", {
        marker: PermissionError(errno.EACCES, "Permission denied")})
    boot.checkout_tracking_branch(project.resolve(),
                                  {"role": "spec", "path": "spec"}, "main")
    assert capsys.readouterr().out.splitlines() == left_as_it_is(
        f".git/modules/spec/{named}")
    assert still_detached(project, "spec")


# --- bootstrap.py: a register ------------------------------------------------

@CANNOT_RUN_AS_ROOT
@pytest.mark.parametrize("locked", ["governance", REGISTER],
                         ids=["a-folder-nobody-may-enter", "at-mode-000"])
def test_a_register_bootstrap_cannot_read_is_named_not_absent(project,
                                                             locked):
    """The base's 3.12 ended in a traceback in step (c), and its 3.14 said
    `authority is not wallet-carried in this org`; at mode 000 it named the
    absolute path. Step (c) names it, claims nothing from it, and the run
    goes on as it does for a register that does not parse."""
    register = project / REGISTER
    register.parent.mkdir(parents=True)
    register.write_text("rows:\n  - holder: agent:x\n    act: review\n"
                        "    target_repo: testorg/Atlas-code\n")
    with at_mode_000(project, locked):
        result = bootstrap(project, "--skip-validators")
    assert result.stdout == skipping_validators(
        project, [placed(project, "spec"), placed(project, "code")],
        [*nothing_claimed(REGISTER), GRANTS]), result.stdout
    assert result.returncode == 0


def test_a_register_whose_stat_is_refused_is_not_dropped(boot, project,
                                                         monkeypatch):
    """On every Python: 3.14's `is_file()` dropped it, and step (c) said the
    org has no wallet-carried authority."""
    refused_stat(monkeypatch, "register.yaml")
    legs = [{"role": "spec", "path": "spec"}]
    assert boot._register_paths(project, legs) == [
        project / REGISTER, project / "spec" / REGISTER]


# --- the one errno set (slice Z holds every copy to it) ----------------------

ABSENT = [
    pytest.param(errno.ENOENT, None, id="ENOENT"),
    pytest.param(errno.ENOTDIR, None, id="ENOTDIR"),
    pytest.param(errno.EBADF, None, id="EBADF"),
    pytest.param(errno.ELOOP, None, id="ELOOP"),
    pytest.param(errno.EINVAL, 21, id="winerror-21"),
    pytest.param(errno.EINVAL, 123, id="winerror-123"),
    pytest.param(errno.EINVAL, 1921, id="winerror-1921"),
]
REFUSED = [
    pytest.param(errno.EACCES, None, id="EACCES"),
    pytest.param(errno.EPERM, None, id="EPERM"),
    pytest.param(errno.EIO, None, id="EIO"),
    pytest.param(errno.ENAMETOOLONG, None, id="ENAMETOOLONG"),
]


@pytest.fixture(params=["validate-manifest.py", "bootstrap.py"])
def copy_of_is_a(request, manifest_gate, boot):
    """Each of the two files' own `_is_a`."""
    module = manifest_gate if request.param.startswith("validate") else boot
    return module._is_a


def stat_failing(monkeypatch, tmp_path: Path, code: int,
                 winerror: int | None) -> tuple[Path, OSError]:
    error = OSError(code, os.strerror(code))
    if winerror is not None:
        error.winerror = winerror
    failing(monkeypatch, "stat", {"asked": error})
    return tmp_path / "asked", error


@pytest.mark.parametrize("code, winerror", ABSENT)
def test_a_name_that_is_not_there_is_absent(copy_of_is_a, monkeypatch,
                                            tmp_path, code, winerror):
    path, _ = stat_failing(monkeypatch, tmp_path, code, winerror)
    assert copy_of_is_a(path, stat.S_ISREG) is False


@pytest.mark.parametrize("code, winerror", REFUSED)
def test_every_other_refusal_is_raised(copy_of_is_a, monkeypatch, tmp_path,
                                       code, winerror):
    path, error = stat_failing(monkeypatch, tmp_path, code, winerror)
    with pytest.raises(OSError) as caught:
        copy_of_is_a(path, stat.S_ISREG)
    assert caught.value is error
