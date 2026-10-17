# SPDX-License-Identifier: Apache-2.0
"""A branch no command can be given is named, and never ends `make bootstrap`
in a traceback (#455).

Step (a) of the assembly root's `scripts/bootstrap.py` places each leg on its
tracking branch: `--branch`, else `project.yaml`'s `tracking_branch`, else
`main`, and a leg's own `branch:` over all three. The branch reaches git as an
argument, and `subprocess` cannot hand a command a NUL (`ValueError: embedded
null byte`) or a lone surrogate the system cannot encode (`UnicodeEncodeError`).
`_try_git` catches `Refusal` and nothing else, so `tracking_branch: "a\\ud83db"`,
`tracking_branch: "a\\x00b"` and a leg's `branch:` of either ended
`make bootstrap` (exit 2) in a traceback from `subprocess.py` in step (a), with
`(a) legs on tracking branches` printed and nothing after it. And
`validate-manifest.py` never read either key, so it said `manifest ok` and
exit 0: no tool named the value. It is the sibling of #391, whose value ended
the run in a `print` and was fixed in `test_bootstrap_spelling.py`; here it is
an argument.

Two halves, one change:

- `validate-manifest.py` gives `tracking_branch` and a leg's `branch` holding a
  NUL or a lone surrogate a finding in the style of #280's `manifest-name`
  (`manifest-tracking-branch`, `manifest-leg-branch`), so the person who ran
  `make validate` or `make bootstrap` is told which key and which character.
- Step (a) asks `_argument_fault` BEFORE any command is built from the branch.
  A leg whose branch no command can be given is not touched, and the line says
  why; the run then reaches the validators, which name the key, and ends as
  they end (`bootstrap FAILED: manifest (exit 1)`).

Whether the value must also be a name git will create (`a..b`, `x.lock`) is not
asked: that is `git check-ref-format`'s, and #283 asks it of `--tracking-branch`
at scaffold time.

Every run is in a scaffolded project and its recursive clone (the `project`
fixture), against local bare remotes, with the values as the issue wrote them.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from conftest import (REPO, git, load_without_bytecode, skip_message,
                      skip_where_a_name_cannot_be_not_utf_8,
                      skip_where_fsencode_gives_a_surrogate_no_byte,
                      windows_fsencode)
from test_bootstrap_spelling import (ASSEMBLY_TEMPLATE, DASH, bootstrap_of,
                                     edit, pin12, run)
from test_stdout_encoding import child_environ, run_tool_bytes

ENCODING = "utf-8:strict"

#: `(id, the YAML scalar, what the lines must print of it, the code point the
#: words name, what they call it)`. The scalar is YAML text: `\ud83d` and
#: `\x00` are escapes the project's own reader resolves, as the issue's
#: `sed -i` wrote them; what is PRINTED is the characters escaped, which
#: happens to be the same text without the quotes.
BAD_VALUES = (
    ("lone-surrogate", r'"a\ud83db"', r"a\ud83db", "U+D83D",
     "a lone surrogate"),
    ("nul", r'"a\x00b"', r"a\x00b", "U+0000", "a NUL"),
)
BAD = [pytest.param(*row[1:], id=row[0]) for row in BAD_VALUES]

#: What `validate-manifest.py` says after the code point, by kind.
WHY = {
    "a lone surrogate": ("a lone surrogate: no UTF-8 file or console can hold "
                         "it, so no branch name is spelled with one."),
    "a NUL": "a NUL: no argument, file name or ref name can hold one.",
}
ADVICE = "Name a branch git can create, such as `main` or `release/1.2`."

#: Step (a)'s two lines for a leg whose branch was not tried.
SECOND_LINE = ("          the branch is the leg's `branch:`, else `--branch`, "
               "else `tracking_branch`. Give that one a name git can create "
               "and run bootstrap again.")


def not_tried(leg: str, printed: str, point: str, kind: str) -> list[str]:
    return [f"  [{leg}] {leg}: could not create branch {printed}: it holds "
            f"{point}, {kind}, which no command can be given as an "
            "argument; the leg is left as it is", SECOND_LINE]


def tracking(project: Path, scalar: str) -> None:
    edit(project, "project.yaml", 'tracking_branch: "main"',
         f"tracking_branch: {scalar}")


def leg_branch(project: Path, leg: str, scalar: str) -> None:
    """A `branch:` line under the leg, which wins over `tracking_branch`."""
    edit(project, "project.yaml", f'    path: "{leg}"',
         f'    path: "{leg}"\n    branch: {scalar}')


def validator_of(project: Path) -> Path:
    return project / "scripts" / "validate-manifest.py"


def legs_state(project: Path) -> dict[str, tuple[str, str, str]]:
    """Where each leg stands: its HEAD, what HEAD is on, and every branch it
    holds. A run that did not touch a leg leaves all three as they were."""
    return {leg: (git("rev-parse", "HEAD", cwd=project / leg).stdout,
                  git("symbolic-ref", "--quiet", "HEAD", cwd=project / leg,
                      check=False).stdout,
                  git("for-each-ref", "--format=%(refname) %(objectname)",
                      "refs/heads", cwd=project / leg).stdout)
            for leg in ("spec", "code")}


# --- the validator names the key --------------------------------------------

def test_a_plain_manifest_is_still_ok_and_prints_what_it_printed(
        project, tmp_path):
    """The control, and the byte-identical rule: nothing in a manifest with
    `main` is a finding, and the line is the one it always was."""
    code, out, err = run(validator_of(project), encoding=ENCODING,
                         tmp_path=tmp_path, cwd=project)
    assert (code, out, err) == (0, "manifest ok: Atlas (atlas), 3 legs\n",
                                ""), err


@pytest.mark.parametrize("scalar, printed, point, kind", BAD)
def test_the_validator_names_a_tracking_branch_no_command_can_be_given(
        project, tmp_path, scalar, printed, point, kind):
    """On origin/main both rows said `manifest ok` and exited 0. Now the
    finding names the key, the value spelled, the character and why, once, and
    exits 1 with no traceback."""
    tracking(project, scalar)
    code, out, err = run(validator_of(project), encoding=ENCODING,
                         tmp_path=tmp_path, cwd=project)
    assert code == 1, out + err
    assert out == "", out
    assert err.split("\n") == [
        f"FINDING manifest-tracking-branch: tracking_branch is '{printed}', "
        f"which holds {point}, {WHY[kind]} {ADVICE}",
        "",
        f"1 finding(s) in {project / 'project.yaml'}",
        ""], err
    assert "Traceback" not in err, err


@pytest.mark.parametrize("scalar, printed, point, kind", BAD)
@pytest.mark.parametrize("leg", ("spec", "code"))
def test_the_validator_names_a_legs_branch_no_command_can_be_given(
        project, tmp_path, scalar, printed, point, kind, leg):
    """The same for a leg's own `branch:` (`tracking_branch: main`), which
    names the LEG whose line it is, and none of the others."""
    leg_branch(project, leg, scalar)
    code, out, err = run(validator_of(project), encoding=ENCODING,
                         tmp_path=tmp_path, cwd=project)
    assert code == 1, out + err
    assert out == "", out
    assert err.split("\n") == [
        f"FINDING manifest-leg-branch: leg '{leg}': branch is '{printed}', "
        f"which holds {point}, {WHY[kind]} {ADVICE}",
        "",
        f"1 finding(s) in {project / 'project.yaml'}",
        ""], err
    assert "Traceback" not in err, err


def test_both_keys_are_named_when_both_hold_one(project, tmp_path):
    tracking(project, r'"a\ud83db"')
    leg_branch(project, "spec", r'"c\x00d"')
    code, out, err = run(validator_of(project), encoding=ENCODING,
                         tmp_path=tmp_path, cwd=project)
    assert code == 1, out + err
    findings = [line for line in err.split("\n") if line.startswith("FINDING")]
    assert [line.split(":")[0] for line in findings] == [
        "FINDING manifest-tracking-branch", "FINDING manifest-leg-branch"], err
    assert "tracking_branch is 'a\\ud83db'" in findings[0], findings
    assert "leg 'spec': branch is 'c\\x00d'" in findings[1], findings
    assert err.rstrip("\n").endswith(
        f"2 finding(s) in {project / 'project.yaml'}"), err


@pytest.mark.parametrize("scalar", [
    '"release/1.2"',
    '"feature/日本"',
    '"a\\u200db"',      # a zero-width joiner is text, and is not asked about
    '"a\\xe9b"',        # U+00E9 is a character, not a surrogate
    '"\\U0001F600"',    # the one-escape spelling of an emoji #280 asks for
    "2026",             # not text: `bootstrap.py` turns it into text
    "true",
])
def test_a_value_that_is_not_one_of_the_two_is_left_alone(
        project, tmp_path, scalar):
    """The question is the two characters and no wider: neither key's other
    values are the validator's to judge here."""
    tracking(project, scalar)
    leg_branch(project, "code", scalar)
    code, out, err = run(validator_of(project), encoding=ENCODING,
                         tmp_path=tmp_path, cwd=project)
    assert (code, err) == (0, ""), out + err
    assert out == "manifest ok: Atlas (atlas), 3 legs\n", out


# --- step (a) does not touch git with it ------------------------------------

@pytest.mark.parametrize("scalar, printed, point, kind", BAD)
def test_a_tracking_branch_no_command_can_be_given_reaches_the_validators(
        project, tmp_path, scalar, printed, point, kind):
    """On origin/main: exit 1 with `UnicodeEncodeError` or `ValueError` from
    `subprocess.py`, `(a) legs on tracking branches` and nothing after it.
    Now every leg says why it was not placed and stays where it was, step (b)
    runs, and the run ends as the manifest validator ends it."""
    tracking(project, scalar)
    before = legs_state(project)
    code, out, err = run(bootstrap_of(project), encoding=ENCODING,
                         tmp_path=tmp_path, cwd=project)
    assert code == 1, out + err
    assert "Traceback" not in err and 'bootstrap.py", line' not in err, err
    lines = out.split("\n")
    assert lines[lines.index("(a) legs on tracking branches, pins untouched")
                 + 1:lines.index("(b) neutral validators") - 1] == (
        not_tried("spec", printed, point, kind)
        + not_tried("code", printed, point, kind)), out
    assert "  --- manifest ---" in lines, out
    assert "bootstrap FAILED: manifest (exit 1)" in err, err
    assert f"FINDING manifest-tracking-branch: tracking_branch is '{printed}'" \
        in err, err
    assert legs_state(project) == before


@pytest.mark.parametrize("scalar, printed, point, kind", BAD)
def test_a_legs_branch_no_command_can_be_given_leaves_that_leg_alone(
        project, tmp_path, scalar, printed, point, kind):
    """The other leg, whose branch is `main`, is placed as it always was."""
    leg_branch(project, "spec", scalar)
    before = legs_state(project)
    code, out, err = run(bootstrap_of(project), encoding=ENCODING,
                         tmp_path=tmp_path, cwd=project)
    assert code == 1, out + err
    assert "Traceback" not in err and 'bootstrap.py", line' not in err, err
    lines = out.split("\n")
    placed = (f"  [code] code: on main at {pin12(project, 'code')} "
              "(branch tip == pin)")
    assert lines[lines.index("(a) legs on tracking branches, pins untouched")
                 + 1:lines.index("(b) neutral validators") - 1] == (
        not_tried("spec", printed, point, kind) + [placed]), out
    assert "bootstrap FAILED: manifest (exit 1)" in err, err
    assert (f"FINDING manifest-leg-branch: leg 'spec': branch is '{printed}'"
            in err), err
    after = legs_state(project)
    assert after["spec"] == before["spec"], after
    assert after["code"][1] == "refs/heads/main\n", after


@pytest.mark.parametrize("scalar, printed, point, kind", BAD)
def test_with_the_validators_skipped_the_run_says_so_and_exits_0(
        project, tmp_path, scalar, printed, point, kind):
    """`--skip-validators` is the person's word that nothing else judges the
    manifest. Step (a) still names the value on each leg, as it does a branch
    git refuses (`could not create branch ...`, exit 0), and ends in neither
    a traceback nor a leg moved."""
    tracking(project, scalar)
    before = legs_state(project)
    code, out, err = run(bootstrap_of(project), "--skip-validators",
                         encoding=ENCODING, tmp_path=tmp_path, cwd=project)
    assert code == 0 and err == "", out + err
    lines = out.split("\n")
    assert lines[lines.index("(a) legs on tracking branches, pins untouched")
                 + 1:lines.index("(b) neutral validators") - 1] == (
        not_tried("spec", printed, point, kind)
        + not_tried("code", printed, point, kind)), out
    assert out.endswith("bootstrap ok\n"), out
    assert legs_state(project) == before


@pytest.mark.skipif(shutil.which("make") is None or
                    shutil.which("python3") is None,
                    reason="the Makefile runs `python3` under `make`")
@pytest.mark.parametrize("where", ("tracking_branch", "spec", "code"))
@pytest.mark.parametrize("scalar, printed, point, kind", BAD)
def test_make_bootstrap_ends_at_the_validator_not_in_a_traceback(
        project, tmp_path, scalar, printed, point, kind, where):
    """`make bootstrap` exited 2 with the traceback and `make: *** [Makefile:
    44: bootstrap] Error 1` for each of the four rows of the issue; it still
    exits 2 (make's own code for a failed recipe), and now for the
    validator's reason."""
    if where == "tracking_branch":
        tracking(project, scalar)
    else:
        leg_branch(project, where, scalar)
    proc = subprocess.run(["make", "bootstrap"], cwd=str(project),
                          env=child_environ(tmp_path, ENCODING),
                          capture_output=True, stdin=subprocess.DEVNULL,
                          check=False)
    out, err = (text.decode("utf-8", "replace")
                for text in (proc.stdout, proc.stderr))
    assert proc.returncode == 2, out + err
    assert "Traceback" not in err and 'bootstrap.py", line' not in err, err
    assert f"could not create branch {printed}: it holds {point}" in out, out
    code_name = "tracking" if where == "tracking_branch" else "leg"
    assert f"FINDING manifest-{code_name}-branch:" in err, err
    assert "bootstrap FAILED: manifest (exit 1)" in err, err


# --- no command is handed the value ------------------------------------------

@pytest.mark.skipif(os.name == "nt", reason="a `git` that logs is a `#!` "
                    "script, which Windows does not run")
@pytest.mark.parametrize("scalar, printed, point, kind", BAD)
def test_no_command_is_run_with_the_branch(project, tmp_path, scalar,
                                           printed, point, kind):
    """Step (a) falls back to nothing. A `git` first on PATH logs every
    command it is given: the control, `main`, shows step (a) reading
    `refs/heads/main`; a branch no command can be given shows no command that
    names a branch, or that could move a leg or read where it is, at all. (On
    POSIX the commands that would have carried the value never start, so this
    cannot tell the check from a caught exception: it holds that nothing else
    runs in their place.)"""
    log = tmp_path / "git.log"
    bindir = tmp_path / "bin"
    bindir.mkdir()
    shim = bindir / "git"
    shim.write_text(f'#!/bin/sh\nprintf \'%s\\n\' "$*" >> "{log}"\n'
                    f'exec "{shutil.which("git")}" "$@"\n', encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
    changes = {"PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"}

    def commands(*args: str) -> list[str]:
        log.write_text("", encoding="utf-8")
        code, out, err = run_tool_bytes(
            bootstrap_of(project), *args, encoding=ENCODING,
            tmp_path=tmp_path, cwd=project, changes=changes)
        assert b"Traceback" not in err, err
        return log.read_text(encoding="utf-8").splitlines()

    control = commands("--skip-validators")
    assert any("rev-parse --verify --quiet refs/heads/main" in line
               for line in control), control
    tracking(project, scalar)
    bad = commands("--skip-validators")
    assert not [line for line in bad if "refs/heads/" in line
                or line.startswith(("checkout", "branch", "merge",
                                    "-c merge", "symbolic-ref", "for-each-ref"
                                    ))], bad


# --- what is carried is not refused ------------------------------------------

def test_a_name_that_is_not_utf8_is_still_carried_and_the_branch_made(
        project, tmp_path):
    """U+DCFF is the byte 0xff POSIX spells a name that is not UTF-8 with:
    `os.fsencode` carries it, and git is handed that byte, as on origin/main.
    `--branch` is the only way it reaches step (a) with the validators out of
    it (the manifest validator names it, #280's rule for a surrogate). Made on
    a system and a disk that take the byte, skipped on one that does not: the
    shared helper asks `os.fsencode` first, which is what Windows answers
    (NTFS takes the name, and `_argument_fault` refuses the branch there,
    which `test_where_a_surrogate_is_three_bytes_and_no_byte_it_is_refused`
    holds), and then the disk, which macOS refuses (#663)."""
    skip_where_a_name_cannot_be_not_utf_8(tmp_path)
    code, out, err = run(bootstrap_of(project), "--skip-validators",
                         "--branch", "a\udcffb", encoding=ENCODING,
                         tmp_path=tmp_path, cwd=project)
    assert code == 0 and "Traceback" not in err, out + err
    for leg in ("spec", "code"):
        assert (f"  [{leg}] {leg}: branch a\\udcffb created at "
                f"{pin12(project, leg)} {DASH} at the pin") in out.split(
                    "\n"), out
        assert "could not create branch" not in out, out
        head = subprocess.run(["git", "symbolic-ref", "--quiet", "HEAD"],
                              cwd=str(project / leg), capture_output=True,
                              check=True).stdout
        assert head == b"refs/heads/a\xffb\n", head


def test_the_branch_test_skips_where_fsencode_makes_no_byte_of_the_surrogate(
        project, tmp_path, monkeypatch):
    """THE WINDOWS GUARD, EMULATED (#663, R455 F1): on NTFS the disk takes
    `probe\\udcff`, the child is given `--branch a\\udcffb`, and
    `_argument_fault` refuses U+DCFF where `os.fsencode` writes three bytes,
    so the `branch a\\udcffb created` line the test expects is absent. With
    Windows' `os.fsencode` the test is therefore SKIPPED, before it runs
    bootstrap: it is called here as it is, under the emulation, and the legs
    stand as they were."""
    before = legs_state(project)
    monkeypatch.setattr(os, "fsencode", windows_fsencode)
    reason = skip_message(
        test_a_name_that_is_not_utf8_is_still_carried_and_the_branch_made,
        project, tmp_path)
    assert reason is not None, "the test ran where `os.fsencode` gives no byte"
    assert "os.fsencode" in reason, reason
    assert legs_state(project) == before


@pytest.fixture(scope="module")
def bootstrap_module():
    """The template run as a module, no bytecode written beside it."""
    return load_without_bytecode(ASSEMBLY_TEMPLATE, "bootstrap_branch_bytes")


@pytest.fixture(scope="module")
def validator_module():
    """`validate-manifest.py`, the same template, as a module: the file is a
    pinned copy, so its functions are read and never changed here."""
    return load_without_bytecode(
        REPO / "templates" / "assembly-root" / "scripts"
        / "validate-manifest.py", "validate_manifest_branch_bytes")


@pytest.mark.parametrize("branch", [
    "main", "release/1.2", "feature/日本", "a‍b", "a\xe9b", "a b",
    "a\x1bb", "a..b", "", "\udc80", "a\udcffb"])
def test_a_branch_the_system_carries_has_no_fault(bootstrap_module, branch):
    """Nothing but a NUL and a lone surrogate with no byte is a fault: a
    control, a space, `..`, a character the system's encoding may lack, and
    the byte-carrying surrogates U+DC80 to U+DCFF are the commands'. On a
    system whose `os.fsencode` does not carry U+DC80 and U+DCFF (Windows) the
    next test is the one that holds."""
    skip_where_fsencode_gives_a_surrogate_no_byte(branch)
    assert bootstrap_module._argument_fault(branch) is None


@pytest.mark.parametrize("branch, skipped", [
    pytest.param("a\udcffb", True, id="byte-carrying-surrogate"),
    pytest.param("\udc80", True, id="the-first-one"),
    pytest.param("release/1.2", False, id="plain"),
    pytest.param("a\xe9b", False, id="text"),
])
def test_the_no_fault_test_skips_where_fsencode_makes_no_byte_of_the_branch(
        bootstrap_module, monkeypatch, branch, skipped):
    """THE WINDOWS GUARD, EMULATED (#663): under Windows' `os.fsencode` the
    test above skips a branch holding a byte-carrying surrogate, which
    `_argument_fault` refuses there, and runs every other (the next test
    holds the refusal)."""
    monkeypatch.setattr(os, "fsencode", windows_fsencode)
    reason = skip_message(test_a_branch_the_system_carries_has_no_fault,
                          bootstrap_module, branch)
    assert (reason is not None) is skipped, reason


@pytest.mark.parametrize("branch, fault", [
    ("a\x00b", "U+0000, a NUL"),
    ("\x00", "U+0000, a NUL"),
    ("a\ud83db", "U+D83D, a lone surrogate"),
    ("a\ude00", "U+DE00, a lone surrogate"),
    ("a\ud800", "U+D800, a lone surrogate"),
    ("a\udc00", "U+DC00, a lone surrogate"),
    ("a\udfffb", "U+DFFF, a lone surrogate"),
    # The FIRST one is named, whichever kind it is.
    ("a\ud83d\x00", "U+D83D, a lone surrogate"),
    ("a\x00\ud83d", "U+0000, a NUL"),
])
def test_a_nul_and_a_surrogate_without_a_byte_are_the_fault(
        bootstrap_module, branch, fault):
    assert bootstrap_module._argument_fault(branch) == fault


@pytest.mark.parametrize("branch", ["a\udcffb", "\udc80", "a\udcfeb"])
def test_where_a_surrogate_is_three_bytes_and_no_byte_it_is_refused(
        bootstrap_module, monkeypatch, branch):
    """Windows' `os.fsencode` is UTF-8 with `surrogatepass`: it writes the
    three bytes of a sequence that is not UTF-8 for EVERY surrogate, none of
    them a byte of a name, and a `CreateProcess` would pass the string on
    mangled. Emulated here, so that a Linux run holds the rule: the
    byte-carrying surrogates are refused where they carry no byte."""
    monkeypatch.setattr(
        bootstrap_module.os, "fsencode",
        lambda text: text.encode("utf-8", "surrogatepass"))
    fault = bootstrap_module._argument_fault(branch)
    assert fault is not None and fault.endswith(", a lone surrogate"), fault
    assert fault.startswith("U+DC"), fault


def test_the_two_templates_agree_on_what_a_fault_is(bootstrap_module,
                                                    validator_module):
    """`validate-manifest.py` finds ANY surrogate (#280's rule, which a UTF-8
    file settles), where `bootstrap.py` asks only whether a command can be
    given the value: so every value bootstrap refuses, the validator names."""
    for branch in ("a\x00b", "a\ud83db", "a\ude00", "\udc00"):
        assert bootstrap_module._argument_fault(branch) is not None
        assert validator_module._branch_finding("c", "w", branch) != []


@pytest.mark.parametrize("role", ["spec", "code"])
def test_the_leg_finding_names_the_leg_by_its_role_and_not_its_path(
        validator_module, role):
    """THE NAME IS THE ROLE (#663, R455 F3, mutant R2: naming `path` passed
    all 54 tests). The templates' roles equal their paths (`spec` is mounted
    at `spec`), so nothing the scaffold writes can tell the two apart, and
    the finding is asked of a leg whose path is not its role, as a spec leg
    mounted at `contracts` is. A unit test on the validator, which this file
    loads for its last test too: it is a pinned copy and is not edited."""
    [finding] = validator_module._leg_branch_findings(
        [{"role": role, "path": "contracts", "branch": "a\x00b"}])
    assert finding.startswith(
        f"FINDING manifest-leg-branch: leg '{role}': branch is 'a\\x00b', "
        "which holds U+0000, a NUL"), finding
    assert "contracts" not in finding, finding
