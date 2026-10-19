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

And at #958's first head, 0ef875c0, lane 4's review (RV958) measured:

  * `validate-manifest.py`, a naming policy in a `contracts/` it cannot
    search: named whole, with nothing to put it right, on every Python.
  * `bootstrap.py`, a validator at mode 000 in a `scripts/` it can search:
    the child's own `can't open file` line, and `bootstrap REFUSED`.
  * `bootstrap.py`, a register under a leg whose `path:` is absolute: a
    `ValueError` traceback in step (c), readable or not.
  * `bootstrap.py`, a register whose `stat` was refused: a `register:` line,
    which says that one is there.

THE RULE NOW, lane 1's for every slice. The path is `stat`ed: ENOENT, ENOTDIR,
EBADF and ELOOP (and Windows' 21, 123 and 1921) mean absent, and any other
`OSError` is named `<path relative to the root>: cannot be read (<reason>)`,
in `validate-pins.py`'s words, with its cure: `chmod u+r` a file and `chmod
u+rx` a directory and every one above it, or, for another cause, its
`OTHER_REASON`.
  * A `project.yaml`, the naming policy, a validator or a declared
    referent's pin file is a refusal, exit 2, and one this user cannot OPEN
    says the same line as one it cannot reach.
  * A leg's `.git`, or an operation's marker in its git dir, is a line in
    step (a), and the leg is left as it is; a register is a line in step
    (c), and nothing is claimed from it. Neither step fails the run, as
    neither did before: the validators refuse such a leg. A register whose
    `stat` was refused is `register, if one is there:`, and a name outside
    the root is named whole.

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
from test_bootstrap_non_utf8_branch import (
    NEEDS_A_UTF8_PROCESS, needs_the_byte,
)
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
POLICY = "contracts/repository-naming.yaml"
REGISTER = "governance/review-authority/register.yaml"
#: A register with one row naming the code leg's repository.
ROWS = ("rows:\n  - holder: agent:x\n    act: review\n"
        "    target_repo: testorg/Atlas-code\n    state: active\n")
#: What step (c) calls a register whose `stat` was refused (RV958's N1).
MAYBE = "register, if one is there"
DASH = "\u2014"
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
                  advice: str = PERMISSION,
                  where: str = "[spec] spec") -> list[str]:
    """Step (a)'s two lines for the leg `where` names (the spec leg), where
    `named` cannot be read."""
    return [f"  {where}: {named}: cannot be read ({reason}), so the leg is "
            "left as it is", f"          {advice}{AGAIN}"]


def nothing_claimed(named: str, label: str = MAYBE,
                    reason: str = "Permission denied",
                    advice: str = PERMISSION) -> list[str]:
    """Step (c)'s lines for a register at `named` this user cannot read:
    `label` is `register` where its `stat` worked and only its open was
    refused."""
    return [f"  {label}: {named}",
            f"    unreadable, so nothing is claimed from it: {named}: cannot "
            f"be read ({reason})", f"      {advice}{AGAIN}"]


def not_initialized(shown: str, word: str | None = None) -> str:
    """Step (a)'s line for a spec leg at `shown` that is not there. The
    command that makes it one holds the path as ONE shell word, `word`
    (`shown` itself where the name needs no quoting), after a `--`, which
    keeps a path that begins with `-` from being read as an option (#961)."""
    return (f"  [spec] {shown}: NOT INITIALIZED. Run `git submodule update "
            f"--init -- {shown if word is None else word}` {DASH} the "
            "validators below will refuse until you do.")


def refusing(monkeypatch, name: str, failure: OSError | None,
             method: str = "stat") -> str:
    """The `stat` of each path called `name` refused as Python 3.14 answers
    it (`refused_stat`) where `failure` is None, else `Path.<method>`
    raising `failure`; returns the reason the refusal says."""
    if failure is None:
        refused_stat(monkeypatch, name)
        return "Permission denied"
    failing(monkeypatch, method, {name: failure})
    return failure.strerror


def leg_path(root: Path, role: str, typed: str) -> str:
    """The `role` leg's `path:` set to `typed`, a character that does not
    print written as its YAML escape; returns `typed` as `bootstrap.py`
    spells it, which, for the ASCII names these tests give, is that
    escape."""
    manifest = root / "project.yaml"
    text = manifest.read_text(encoding="utf-8")
    old = f'    path: "{role}"'
    assert text.count(old) == 1, text
    escaped = typed.encode("unicode_escape").decode("ascii")
    manifest.write_text(text.replace(old, f'    path: "{escaped}"'),
                        encoding="utf-8")
    return escaped


def placed(root: Path, role: str) -> str:
    """Step (a)'s line for a leg of a fresh clone, put on `main` at its pin."""
    pin = git("rev-parse", f"HEAD:{role}", cwd=root).stdout.strip()
    return f"  [{role}] {role}: on main at {pin[:12]} (branch tip == pin)"


def up_to_step_b(root: Path) -> str:
    """The whole of stdout of a run refused before step (b) runs any
    validator, both legs placed by step (a)."""
    return "\n".join([
        f"bootstrap: Atlas ({root.resolve()})", "",
        "(a) legs on tracking branches, pins untouched",
        placed(root, "spec"), placed(root, "code"), "",
        "(b) neutral validators", ""])


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


def test_a_manifest_that_is_a_directory_is_no_manifest_to_either_tool(
        boot, project):
    """THE OTHER HALF, which the base answered the same: a directory where
    `project.yaml` goes is no manifest, never a file that cannot be read.
    The gate refuses `manifest-missing`, and `bootstrap.py` reads a project
    that has not elected the schema."""
    manifest = project / "project.yaml"
    manifest.unlink()
    manifest.mkdir()
    result = validate(project)
    assert result.stderr == (
        f"REFUSED manifest-missing: {project.resolve() / 'project.yaml'} "
        "does not exist. A project that has elected this schema declares it "
        "in `project.yaml`; a project that has not, does not run this "
        "validator.\n"), result.stderr
    assert result.returncode == 2
    loaded = boot._load_root_and_manifest(SimpleNamespace(root=project))
    assert loaded[1] is None


# --- validate-manifest.py: the naming policy ---------------------------------

@CANNOT_RUN_AS_ROOT
def test_a_naming_policy_the_gate_cannot_reach_is_refused_by_name(project):
    """`contracts/` at mode 000 and no `--policy`, the case a project meets:
    the base named the policy whole, with nothing to put it right, on every
    Python (RV958's S1)."""
    with at_mode_000(project, "contracts"):
        result = validate(project)
    assert result.stderr == refused("yaml-unreadable", POLICY,
                                    MANIFEST_READS), result.stderr
    assert result.returncode == 2, result.stdout


@pytest.mark.parametrize("given, failure, advice", [
    pytest.param(False, os_error(errno.EIO), OTHER, id="io-error"),
    pytest.param(True, PermissionError(errno.EACCES, "Permission denied"),
                 PERMISSION, id="given-outside-the-root-with-an-esc"),
])
def test_a_naming_policy_the_gate_cannot_open_is_named_on_every_python(
        manifest_gate, project, tmp_path, monkeypatch, capsys, given,
        failure, advice):
    """In-process, as root and on every platform. An I/O error is no
    permission, and is not told to `chmod`. A `--policy` outside the root is
    named whole, and spelled as `repr` spells a name that does not print, as
    `validate-pins.py` spells one (RV958's N3)."""
    policy = tmp_path / "loc\x1bked" / "repository-naming.yaml"
    given_args = ["--policy", str(policy)] if given else []
    failing(monkeypatch, "read_text", {"repository-naming.yaml": failure})
    assert manifest_gate.main(["--root", str(project), *given_args]) == 2
    assert capsys.readouterr().err == refused(
        "yaml-unreadable", repr(str(policy)) if given else POLICY,
        MANIFEST_READS, failure.strerror, advice)


def test_a_name_that_does_not_print_is_spelled_under_the_root_too(
        manifest_gate, tmp_path):
    """The other branch of `_unreadable_file`'s naming, under the root,
    where the names this gate reads are fixed or a referent's: spelled, as
    outside it."""
    refusal = manifest_gate._unreadable_file(
        tmp_path, tmp_path / "loc\x1bked" / "x.yaml",
        PermissionError(errno.EACCES, "Permission denied"))
    assert refusal.detail == (
        "'loc\\x1bked/x.yaml': cannot be read (Permission denied)")


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
    reason = refusing(monkeypatch, "openxdox-pin.yaml", failure)
    assert manifest_gate.main(["--root", str(project)]) == 2
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


@pytest.mark.parametrize("method, failure, advice", [
    pytest.param("stat", None, PERMISSION, id="stat-refused"),
    pytest.param("stat", os_error(errno.EIO), OTHER, id="stat-io-error"),
    pytest.param("read_text", os_error(errno.EIO), OTHER, id="open-io-error"),
])
def test_a_manifest_bootstrap_cannot_stat_or_open_is_the_same_refusal(
        boot, project, monkeypatch, method, failure, advice):
    """On every Python: the `stat` refused as 3.14 answers it, and an I/O
    error from the `stat` or the open, which is no permission and is not
    told to `chmod`."""
    reason = refusing(monkeypatch, "project.yaml", failure, method)
    with pytest.raises(boot.Refusal) as caught:
        boot._load_root_and_manifest(SimpleNamespace(root=project))
    assert f"{caught.value}\n" == refused("yaml-unreadable", "project.yaml",
                                          BOOTSTRAP_READS, reason, advice)


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
    assert result.stdout == up_to_step_b(project)


@CANNOT_RUN_AS_ROOT
def test_a_validator_at_mode_000_is_refused_before_any_runs(project):
    """Its `stat` works and the child cannot open it: the base ran the two
    before it, and the child said Python's own `can't open file` line, with
    nothing to put it right (RV958's S2). It is refused by name, as
    `bump-leg.py` refuses it (#934), and none runs."""
    with at_mode_000(project, "scripts/validate-pins.py"):
        result = bootstrap(project)
    assert result.stderr == refused(
        "validator-unreadable", "scripts/validate-pins.py",
        VALIDATOR_READS), result.stderr
    assert result.returncode == 2
    assert result.stdout == up_to_step_b(project)


@pytest.mark.parametrize("method, failure, advice", [
    pytest.param("stat", None, PERMISSION, id="stat-refused"),
    pytest.param("stat", os_error(errno.EIO), OTHER, id="stat-io-error"),
    pytest.param("open", os_error(errno.EIO), OTHER, id="open-io-error"),
])
def test_a_validator_whose_stat_is_refused_stops_step_b_before_any_runs(
        boot, project, monkeypatch, capsys, method, failure, advice):
    """On every Python, the second validator: the base SKIPPED it and ran
    the other two, or, where only its open failed, ran it, and the child
    said why. Nothing is run or said before the refusal."""
    manifest = boot.load_yaml(project / "project.yaml")
    reason = refusing(monkeypatch, "validate-manifest.py", failure, method)
    with pytest.raises(boot.Refusal) as caught:
        boot._run_neutral_validators(project, manifest, False)
    assert f"{caught.value}\n" == refused(
        "validator-unreadable", "scripts/validate-manifest.py",
        VALIDATOR_READS, reason, advice)
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("in_its_place", [False, True],
                         ids=["taken-away", "a-directory-in-its-place"])
def test_a_validator_that_is_not_there_is_still_skipped(boot, project,
                                                        monkeypatch, capsys,
                                                        in_its_place):
    """THE OTHER HALF, which the base answered the same. The validators are
    stood in for: what is asked is which of them step (b) runs, and a
    pinned copy taken away is `validate-pins.py`'s own finding. A directory
    is no validator, and is not opened."""
    monkeypatch.delenv("SHAPE_UPSTREAM_PATH", raising=False)
    ran = []
    monkeypatch.setattr(boot, "_run",
                        lambda root, argv: ran.append(argv[0]) or 0)
    manifest = boot.load_yaml(project / "project.yaml")
    naming = project / "scripts" / "validate-repository-naming.py"
    naming.unlink()
    if in_its_place:
        naming.mkdir()
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
    reason = refusing(monkeypatch, ".git", failure)
    boot.checkout_tracking_branch(project.resolve(),
                                  {"role": "spec", "path": "spec"}, "main")
    assert capsys.readouterr().out.splitlines() == left_as_it_is(
        "spec/.git", reason, advice)


@CANNOT_RUN_AS_ROOT
@pytest.mark.parametrize("outside", [False, True],
                         ids=["inside-the-root", "outside-the-root"])
def test_a_leg_in_a_folder_nobody_may_search_is_named_and_spelled(project,
                                                                 outside):
    """The code leg's `path:` holds an ESC and is in a folder at mode 000,
    inside the root, or outside it as an absolute path, which the gate finds
    (`manifest-leg-path`). Each line spells the name (#391); one outside the
    root is named whole, where the base's step (c) ended in a `ValueError`
    traceback from `relative_to` (RV958's M1 and S3); and step (c) does not
    say that a register is there (RV958's N1)."""
    folder = (project.parent if outside else project) / "loc\x1bked"
    folder.mkdir()
    shown = leg_path(project, "code", (folder / "code").as_posix() if outside
                     else "loc\x1bked/code")
    with mode_of(folder.parent, folder.name, 0):
        result = bootstrap(project, "--skip-validators")
    assert result.stdout == skipping_validators(
        project, [placed(project, "spec"),
                  *left_as_it_is(f"{shown}/.git", where=f"[code] {shown}")],
        [*nothing_claimed(f"{shown}/{REGISTER}"), GRANTS]), result.stdout
    assert result.returncode == 0, result.stderr


def test_a_register_under_a_leg_path_outside_the_root_is_read(project):
    """A register this user can read, under a leg whose `path:` is
    absolute: the base's step (c) ended in the same `ValueError` traceback
    (RV958's M1). It is named whole, and its row is read."""
    spec = project.parent / "elsewhere" / "spec"
    (spec / REGISTER).parent.mkdir(parents=True)
    (spec / REGISTER).write_text(ROWS)
    shown = leg_path(project, "spec", spec.as_posix())
    result = bootstrap(project, "--skip-validators")
    assert result.stdout == skipping_validators(
        project, [not_initialized(shown), placed(project, "code")],
        [f"  register: {spec / REGISTER}",
         "    agent:x \u00b7 review \u00b7 testorg/Atlas-code \u00b7 active "
         "\u00b7 expires -", GRANTS]), result.stdout
    assert result.returncode == 0, result.stderr


def test_a_leg_path_holding_a_nul_is_not_initialized(project):
    """Passes on the base too, and is here to keep it: no file name holds a
    NUL, so no leg is there, as `exists()` answered, and step (c) finds no
    register under it. `_is_a` without its `ValueError` clause ended the run
    in `ValueError: embedded null byte` (RV958's S3)."""
    shown = leg_path(project, "spec", "sp\x00ec")
    result = bootstrap(project, "--skip-validators")
    assert result.stdout == skipping_validators(
        project, [not_initialized(shown, f"'{shown}'"),
                  placed(project, "code")],
        DEGRADE), result.stdout
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("typed, word", [
    pytest.param("my spec", "'my spec'", id="space"),
    pytest.param("=spec", "'=spec'", id="leading-equals"),
    pytest.param("-spec", "-spec", id="leading-dash"),
    pytest.param("sp\x1bec", r'''"$(printf -- 'sp\033ec')"''', id="escape"),
    pytest.param("sp\u2028ec", r'''"$(printf -- 'sp\342\200\250ec')"''',
                 id="line-separator", marks=NEEDS_A_UTF8_PROCESS),
    pytest.param("sp\udcffec", r'''"$(printf -- 'sp\377ec')"''',
                 id="byte-0xff"),
])
def test_the_command_that_initializes_a_leg_holds_its_path_as_one_word(
        project, tmp_path, typed, word):
    """THE ISSUE (#961, rv932's SHOULD 3): the line printed
    `--init my spec` (two pathspecs), `--init =spec` (zsh expands it),
    `--init sp\\x1bec` and `--init sp\\udcffec` (the escape text, which
    names no path) and `--init -spec` (an option). The path is one word,
    `_paste_word`'s, after a `--`; `tests/test_bootstrap_pasteable_lines.py`
    pastes each into a shell."""
    if "\udcff" in typed:
        needs_the_byte(tmp_path)
    shown = leg_path(project, "spec", typed)
    result = bootstrap(project, "--skip-validators")
    assert result.stdout == skipping_validators(
        project, [not_initialized(shown, word), placed(project, "code")],
        DEGRADE), result.stdout
    assert result.returncode == 0, result.stderr


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

def a_register(root: Path) -> Path:
    """A register in the root, holding `ROWS`."""
    register = root / REGISTER
    register.parent.mkdir(parents=True)
    register.write_text(ROWS)
    return register


@CANNOT_RUN_AS_ROOT
@pytest.mark.parametrize("locked, label", [
    pytest.param("governance", MAYBE, id="a-folder-nobody-may-enter"),
    pytest.param(REGISTER, "register", id="at-mode-000"),
])
def test_a_register_bootstrap_cannot_read_is_named_not_absent(project,
                                                             locked, label):
    """The base's 3.12 ended in a traceback in step (c), and its 3.14 said
    `authority is not wallet-carried in this org`; at mode 000 it named the
    absolute path. Step (c) names it, claims nothing from it, and the run
    goes on as it does for a register that does not parse. Only where its
    `stat` worked does the line say that a register is there."""
    a_register(project)
    with at_mode_000(project, locked):
        result = bootstrap(project, "--skip-validators")
    assert result.stdout == skipping_validators(
        project, [placed(project, "spec"), placed(project, "code")],
        [*nothing_claimed(REGISTER, label), GRANTS]), result.stdout
    assert result.returncode == 0


@pytest.mark.parametrize("failure", [None, os_error(errno.EIO)],
                         ids=["permission", "io-error"])
def test_a_register_whose_stat_is_refused_is_not_dropped(boot, project,
                                                         monkeypatch,
                                                         failure):
    """On every Python: 3.14's `is_file()` dropped it, and step (c) said the
    org has no wallet-carried authority. Nor is one dropped for an I/O
    error."""
    refusing(monkeypatch, "register.yaml", failure)
    legs = [{"role": "spec", "path": "spec"}]
    assert boot._register_paths(project, legs) == [
        (project / REGISTER, MAYBE), (project / "spec" / REGISTER, MAYBE)]


@pytest.mark.parametrize("directory", [False, True],
                         ids=["a-file", "a-directory"])
def test_only_a_file_is_a_register_where_the_stat_works(boot, project,
                                                        directory):
    """THE OTHER HALF, which the base answered the same: a file is a
    register, and a directory at its name is none."""
    if directory:
        (project / REGISTER).mkdir(parents=True)
    else:
        a_register(project)
    assert boot._register_paths(project, []) == (
        [] if directory else [(project / REGISTER, "register")])


def test_a_register_that_cannot_be_opened_claims_nothing_on_every_python(
        boot, project, monkeypatch, capsys):
    """In-process, as root and on every platform: an I/O error from the
    open, which is no permission and is not told to `chmod`."""
    a_register(project)
    failing(monkeypatch, "read_text", {"register.yaml": os_error(errno.EIO)})
    boot.read_authority(project, [])
    assert capsys.readouterr().out.splitlines() == [
        *nothing_claimed(REGISTER, "register", os.strerror(errno.EIO), OTHER),
        GRANTS]


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


@pytest.mark.parametrize("name", ["a\x00b", "a\ud83db"],
                         ids=["a-nul", "a-lone-surrogate"])
def test_a_name_no_file_can_have_is_absent(copy_of_is_a, tmp_path, name):
    """A NUL, or a lone surrogate the file system's encoding cannot write
    (where it has one): no file has such a name, so nothing is there, as
    `is_file()` answered. Without the `ValueError` clause the run ended in
    its traceback (RV958's S3)."""
    assert copy_of_is_a(tmp_path / name, stat.S_ISREG) is False


@pytest.mark.parametrize("make, link", [
    pytest.param(Path.mkdir, False, id="a-directory"),
    pytest.param(lambda path: path.symlink_to("nowhere"), True,
                 id="a-link-to-nothing-asked-of-the-name", marks=POSIX_LINKS),
])
def test_anything_at_a_name_in_a_leg_is_found(boot, tmp_path, make, link):
    """A leg's `.git` that is a directory (a leg cloned on its own) is
    there, and so is an operation's marker that is a link to nothing, as
    `os.path.lexists` answered."""
    asked = tmp_path / "asked"
    make(asked)
    assert boot._found(asked, link=link) is True
