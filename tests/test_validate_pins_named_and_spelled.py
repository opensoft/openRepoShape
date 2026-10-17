# SPDX-License-Identifier: Apache-2.0
"""`validate-pins.py` refuses a pin, the manifest or a shape copy it cannot
reach or read BY NAME, names every file relative to the root and once, gives
each cause its own advice, and spells every name and path it prints (#712).

The issue's lines, from lane 4's checklist triage on #459:

  * L4-103. A `contracts/` this user cannot search ended the run in a
    `PermissionError` traceback, exit 1, at `_load_leg_pin`'s
    `pin_path.is_file()` on Python 3.12 and 3.13, and on 3.14 refused
    `pin-missing`, a present file said not to exist, under the lockstep
    remedy. The five `is_file()` calls (the leg pin, the shape pin, each
    shape copy, each neutral-product pin and the manifest) are `_is_file`
    now: `_is_a`'s answer (#633), where a refused `stat` is a refusal
    naming the file. A shape copy at mode 000 ended in `file_sha256`'s
    `PermissionError` on every Python; it is `shape-copy-unreadable` too.
  * L4-104. A pin this user cannot open was `REFUSED yaml-unreadable:
    <absolute path>: [Errno 13] Permission denied: '<absolute path>'`,
    under THE LOCKSTEP RULE's remedy. It is named relative to the root,
    once, with a remedy of its own, and so is the file in every refusal
    `load_yaml` raises here and every file this validator names.
  * L4-105 (rider). A workflow file whose `stat` or read failed for another
    cause than permission was told to restore read access to it.
  * L4-106 and L4-144. A workflow's name, and a pin's path built from a
    `neutral_product_pins:` entry, reached stderr raw: a newline began a
    line of its own, a bidi control reordered one, a C1 control broke one,
    an ESC was the control it is and a byte that is not UTF-8 was `\\udcXX`.
    Every name and path the file prints is spelled by `_shown` now, with a
    row below for each print.
  * L4-143 (rider). The "not used" note for a `--pin-source` under a
    `neutral_product_pins:` that is not a list points at that finding.
  * L4-102 (rider). `PinSources` keys by `pin_product_key`, the pin file's
    own fold, where `casefold()` took `openss=` for `openss`'s sharp twin.

THE HARNESS. The gate runs as the copy a real scaffold wrote
(`tests/test_validate_pins_unreadable_workflow.py`'s `validate`), and
in-process as that copy loaded as a module (`validator`, from
`tests/test_validate_pins_without_git.py`). `refused_stat`
(`tests/test_bump_leg_unopenable.py`) stands in for a `stat` the operating
system refuses and for Python 3.14's `is_file()`, so those rows run on every
Python, as root and on Windows. The mode rows skip on Windows and as root,
and a row that needs a file whose name holds a control character skips on
Windows, whose file names cannot hold one.

NOTHING HERE REACHES A NETWORK: the scaffold uses `--local-remote-dir`, and
each row that would ask `gh api` replaces `tree_digest_from_gh`.
"""

from __future__ import annotations

import errno
import os
import re
import stat
import sys
from pathlib import Path

import pytest

from conftest import REPO, clear_ambient_pin_sources, run_script
from test_bump_leg_unopenable import refused_stat
from test_load_yaml_refusals import refusal_for
from test_manifest_validator import edit
from test_validate_pins_unreadable_workflow import (
    CANNOT_RUN_AS_ROOT, WORKFLOWS, leg_workflow, not_utf8_line, validate,
)
from test_validate_pins_unreadable_workflows_dir import (
    FILE_ADVICE, mode_of, tree_bytes,
)
# A fixture is used by being named in this module's namespace, which is what
# this import is for: the project's own `validate-pins.py`, loaded as a module.
from test_validate_pins_without_git import validator  # noqa: F401

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import double_quoted  # noqa: E402

#: What the refusal of a file the gate cannot reach or read says first.
READS = (
    "Remediation: this validator reads each leg's pin, the shape pin, each "
    "neutral-product pin, project.yaml and every copy the shape pin lists, "
    "and one it cannot read is a question it cannot answer, never a pass. ")
#: Its advice for a permission, in `bump-leg.py`'s words (#383).
PERMISSION = (
    "Make what this user may not open readable by this user: `chmod u+r` on "
    "a file, `chmod u+rx` on a directory (and on every directory above it "
    "inside the root), or fix who owns it. ")
#: Its advice, and a workflow's, for any other cause (#383's words too).
OTHER = (
    "Where the operating system gave another reason, put a regular file this "
    "user can open back in its place, or take away one nobody wants, and make "
    "sure nothing is changing the directory while this runs. ")
AGAIN = "Then run the same command again."

#: Hex letters: an all-digit `commit:` reads back as a number.
COMMIT = "c" * 40
OTHER_COMMIT = "d" * 40
SHAPE_PIN = "contracts/shape-pin.yaml"

#: A file whose name holds a control character, which Windows cannot hold.
ON_DISK = pytest.mark.skipif(
    os.name == "nt",
    reason="needs a file whose name holds a control character, which a "
           "Windows file name cannot hold")

#: The issue's names that print as something other than themselves: a
#: newline, a bidi control (U+202E), a C1 control (U+0085), an ESC and a
#: byte that is not UTF-8, as `surrogateescape` keeps one.
UNPRINTABLE = [
    pytest.param("a\nb", id="newline"),
    pytest.param("rev\u202eelif", id="bidi-control"),
    pytest.param("c1\u0085x", id="c1-control"),
    pytest.param("x\x1b[31mRED", id="esc"),
    pytest.param("und\udcffx", id="undecodable-byte"),
]
#: The control: a name that prints as itself, and still does.
PRINTABLE = "plain-name"


def refused(code: str, named: str, reason: str = "Permission denied",
            advice: str = PERMISSION) -> str:
    """The whole of stderr for a file the gate cannot reach or open: the
    file named once, relative to the root, with the system's reason, then
    its own remedy and no other."""
    return (f"REFUSED {code}: {named}: cannot be read ({reason})\n"
            f"{READS}{advice}{AGAIN}\n")


def declare_openxdox(project: Path) -> None:
    """`project.yaml` declares one neutral-product pin, whose file is not
    there: the fourth `is_file()` site is reached."""
    edit(project, "neutral_product_pins: []",
         "neutral_product_pins: [openXdox]")


def refusal_of_the_run(validator, project: Path, values=()):
    """The `Refusal` the gate's checks raise over `project`, failing the test
    if they finish or raise anything else. The class is the project's own
    copy's, which is the one its `main()` catches (SonarCloud S5958)."""
    report, given = validator.Report(), list(values)
    with pytest.raises(validator.Refusal) as caught:
        validator._run_all_checks(project, report, given)
    return caught.value


def failing(monkeypatch, method: str, failures: dict) -> None:
    """`Path.<method>` raising `failures[name]` for each file so named, and
    answering as it does for every other."""
    real = getattr(Path, method)

    def fails(self, *args, **kwargs):
        if self.name in failures:
            raise failures[self.name]
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, method, fails)


def os_error(code: int) -> OSError:
    """The `OSError` the system raises for `code`, with its own words."""
    return OSError(code, os.strerror(code))


# --- L4-103 and L4-104: what the gate prints, run as a project runs it -------

@CANNOT_RUN_AS_ROOT
@pytest.mark.parametrize("relative, mode, code, named", [
    pytest.param("contracts", 0, "yaml-unreadable", "contracts/spec-pin.yaml",
                 id="contracts-000"),
    pytest.param("contracts", stat.S_IRUSR, "yaml-unreadable",
                 "contracts/spec-pin.yaml", id="contracts-r--"),
    pytest.param("contracts/spec-pin.yaml", 0, "yaml-unreadable",
                 "contracts/spec-pin.yaml", id="leg-pin-000"),
    pytest.param(SHAPE_PIN, 0, "yaml-unreadable", SHAPE_PIN,
                 id="shape-pin-000"),
    pytest.param("project.yaml", 0, "yaml-unreadable", "project.yaml",
                 id="manifest-000"),
    pytest.param("AGENTS-shape.md", 0, "shape-copy-unreadable",
                 "AGENTS-shape.md", id="shape-copy-000"),
])
def test_a_file_the_gate_cannot_reach_or_open_is_refused_by_name(
        project, relative, mode, code, named):
    """THE ISSUE'S ROWS. A `contracts/` at 000 or r-- was a `PermissionError`
    traceback, exit 1, on 3.12 and 3.13, and `pin-missing` on 3.14; a pin
    at 000 named its absolute path twice under THE LOCKSTEP RULE's remedy;
    a shape copy at 000 was a traceback on every Python. Each is now one
    refusal, exit 2, and the whole of stderr: the file relative to the root,
    named once, the system's reason, the permission advice. Nothing is
    written, and with the mode put back the same command passes."""
    before = tree_bytes(project)
    with mode_of(project, relative, mode):
        result = validate(project)
    assert result.stderr == refused(code, named), result.stderr
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == "", result.stdout
    assert tree_bytes(project) == before, "a validator writes nothing"
    again = validate(project)
    assert again.returncode == 0, again.stdout + again.stderr
    assert "pins ok" in again.stdout, again.stdout


# --- L4-103 on every Python: the five `is_file()` sites ----------------------

#: Each site, as `(the name whose stat is refused, code, the file named)`.
SITES = [
    pytest.param("spec-pin.yaml", "yaml-unreadable", "contracts/spec-pin.yaml",
                 id="leg-pin"),
    pytest.param("shape-pin.yaml", "yaml-unreadable", SHAPE_PIN,
                 id="shape-pin"),
    pytest.param("AGENTS-shape.md", "shape-copy-unreadable",
                 "AGENTS-shape.md", id="shape-copy"),
    pytest.param("openxdox-pin.yaml", "yaml-unreadable",
                 "contracts/openxdox-pin.yaml", id="neutral-pin"),
    pytest.param("project.yaml", "yaml-unreadable", "project.yaml",
                 id="manifest"),
]


@pytest.mark.parametrize("name, code, named", SITES)
def test_a_refused_stat_is_refused_by_name_on_every_python(
        validator, project, monkeypatch, name, code, named):
    """ON PYTHON 3.14 `is_file()` ANSWERS FALSE to a refused `stat`, so the
    pin in a `contracts/` this user cannot search was "missing" and a shape
    copy "pinned but absent". Asked of the system, the answer is the same on
    every Python, root included: the file, refused by name."""
    declare_openxdox(project)
    refused_stat(monkeypatch, name)
    refusal = refusal_of_the_run(validator, project)
    assert refusal.code == code
    assert refusal.detail == f"{named}: cannot be read (Permission denied)"
    assert refusal.remediation == READS + PERMISSION + AGAIN


@pytest.mark.parametrize("call, code", [
    pytest.param(lambda v, root: v._load_leg_pin(
        root, "a\x00b", "spec", "o/r", v.Report()), "pin-missing",
        id="leg-pin"),
    pytest.param(lambda v, root: v._check_neutral_pin_entry_and_load(
        root, "a\x00b", v.Report()), "neutral-pin-missing", id="neutral-pin"),
    pytest.param(lambda v, root: v._check_pin_digest(
        root, "a\x00b", COMMIT, {}, "rel", v.Report()),
        "pin-submodule-uninitialized", id="leg-checkout"),
])
def test_a_name_the_system_cannot_take_is_still_no_file(validator, project,
                                                        call, code):
    """A NUL in a role or a product is a name no `stat` can be handed (a
    `ValueError`), which `is_file()` answered False: still the missing
    file's refusal, its name spelled, and never a traceback."""
    with pytest.raises(validator.Refusal) as caught:
        call(validator, project)
    assert caught.value.code == code
    assert "\\x00" in caught.value.detail, caught.value.detail


#: What the refusal of a leg checkout this user cannot search says first.
CHECKOUT_READS = (
    "Remediation: this validator reads each leg's checkout, to recompute its "
    "pinned tree digest from the leg's own objects, and one it cannot read "
    "is a question it cannot answer, never a pass. ")


@CANNOT_RUN_AS_ROOT
@pytest.mark.parametrize("mode", [0, stat.S_IRUSR], ids=["000", "r--"])
def test_a_leg_checkout_the_gate_cannot_search_is_refused_by_name(project,
                                                                   mode):
    """RV827'S S1, THE LEG: with `spec/` at 000 or r--, `exists()` on its
    `.git` raised `PermissionError` out of the run, exit 1, on 3.11 to 3.13,
    and on 3.14 would have called the leg an uninitialized submodule. It is
    `pin-submodule-unreadable`, naming the `.git` it could not reach, with
    the permission advice, and nothing is written."""
    before = tree_bytes(project)
    with mode_of(project, "spec", mode):
        result = validate(project)
    assert result.stderr == (
        "REFUSED pin-submodule-unreadable: spec/.git: cannot be read "
        f"(Permission denied)\n{CHECKOUT_READS}{PERMISSION}{AGAIN}\n"), \
        result.stderr
    assert result.returncode == 2, result.stdout + result.stderr
    assert tree_bytes(project) == before, "a validator writes nothing"


@pytest.mark.parametrize("failure, advice", [
    pytest.param(PermissionError(errno.EACCES, "Permission denied"),
                 PERMISSION, id="permission"),
    pytest.param(os_error(errno.EIO), OTHER, id="io-error"),
])
def test_a_leg_checkout_whose_stat_is_refused_is_refused_on_every_python(
        validator, project, monkeypatch, failure, advice):
    """The same leg, in-process, so on every Python, as root and on Windows:
    `refused_stat` answers as Python 3.14's `exists()` does, which is what
    read the leg as uninitialized. Each cause has its advice."""
    failing(monkeypatch, "stat", {".git": failure})
    monkeypatch.setattr(Path, "exists", lambda self: False)
    refusal = refusal_of_the_run(validator, project)
    assert refusal.code == "pin-submodule-unreadable"
    assert refusal.detail == (
        f"spec/.git: cannot be read ({failure.strerror})")
    assert refusal.remediation == CHECKOUT_READS + advice + AGAIN


def beside_the_root(project: Path) -> Path:
    """`../openXdox`, the checkout a declared `openXdox` pin is looked for
    beside the root, holding a `.git`."""
    sibling = project.parent / "openXdox"
    (sibling / ".git").mkdir(parents=True)
    return sibling


def test_a_checkout_beside_the_root_whose_stat_is_refused_is_the_source(
        validator, project, monkeypatch):
    """RV827'S S1, THE SIBLING, on every Python: something is at
    `../openXdox`, so it is the source, where `exists()` raised its
    `PermissionError` out of the run up to 3.13 and from 3.14 would have
    passed it over for `gh api`."""
    clear_ambient_pin_sources(monkeypatch)
    sibling = beside_the_root(project)
    refused_stat(monkeypatch, ".git")
    found = validator.resolve_neutral_pin_source(
        project, "openXdox", "testorg/openXdox",
        validator.PinSources([], ["openXdox"]))
    assert found == (sibling, f"sibling checkout ({sibling})", None)


@CANNOT_RUN_AS_ROOT
def test_a_checkout_beside_the_root_this_user_cannot_search_cannot_answer(
        validator, project, monkeypatch):
    """With `../openXdox` at 000, the source cannot answer: the pin's
    `neutral-pin-source-unreadable` finding names it and the system's
    reason, and the run goes on."""
    clear_ambient_pin_sources(monkeypatch)
    sibling = beside_the_root(project)
    report = validator.Report()
    sources = validator.PinSources([], ["openXdox"])
    with mode_of(project.parent, "openXdox", 0):
        found = validator._recompute_neutral_pin_digest(
            project, "openXdox", "testorg/openXdox", COMMIT, "rel", sources,
            report)
    assert found is None
    assert report.findings[0].startswith(
        f"FINDING neutral-pin-source-unreadable: rel: {sibling} (sibling "
        f"checkout ({sibling})) could not answer for testorg/openXdox @ "
        f"{COMMIT}: Permission denied\n"), report.findings


@pytest.mark.parametrize("call, code, pin", [
    pytest.param(lambda v, root, name: v._load_leg_pin(
        root, name, "spec", "o/r", v.Report()), "pin-missing",
        lambda name: f"{name}-pin.yaml", id="leg-role"),
    pytest.param(lambda v, root, name: v._check_neutral_pin_entry_and_load(
        root, name, v.Report()), "neutral-pin-missing",
        lambda name: f"{name.lower()}-pin.yaml", id="neutral-product"),
])
def test_a_name_spelled_as_an_absolute_path_is_refused_by_name(
        validator, project, call, code, pin):
    """RV827'S S2: a role or a product spelled as an absolute path puts its
    pin outside the root, where `relative_to` raised a `ValueError` out of
    the run, exit 1. It is the missing pin's refusal, naming the path whole:
    `_named`'s fallback."""
    name = str(project.parent / "nonexistent-w712" / "x")
    with pytest.raises(validator.Refusal) as caught:
        call(validator, project, name)
    assert caught.value.code == code
    assert caught.value.detail.endswith(
        f"{project / 'contracts' / pin(name)} does not exist"), \
        caught.value.detail


# --- L4-104: every file named relative to the root ---------------------------

def unlinked(relative: str):
    def break_it(project: Path) -> None:
        (project / relative).unlink()
    return break_it


def written(relative: str, data: bytes):
    def break_it(project: Path) -> None:
        declare_openxdox(project)
        (project / relative).write_bytes(data)
    return break_it


@pytest.mark.parametrize("break_it, code, detail", [
    pytest.param(unlinked("project.yaml"), "manifest-missing",
                 "project.yaml does not exist, so there is no declaration of "
                 "which legs to check. A one-repository project has no legs "
                 "and does not run this validator.", id="manifest-missing"),
    pytest.param(lambda project: (project / "project.yaml").write_bytes(
        b"- a\n"), "manifest-unreadable", "project.yaml: not a mapping",
        id="manifest-not-a-mapping"),
    pytest.param(lambda project: (project / "project.yaml").write_bytes(
        b"legs: []\n"), "manifest-no-legs",
        "project.yaml: no non-assembly legs declared", id="manifest-no-legs"),
    pytest.param(written("contracts/spec-pin.yaml", b"- a\n"),
                 "pin-unreadable", "contracts/spec-pin.yaml: not a mapping",
                 id="leg-pin-not-a-mapping"),
    pytest.param(unlinked(SHAPE_PIN), "shape-pin-missing",
                 f"{SHAPE_PIN} does not exist", id="shape-pin-missing"),
    pytest.param(written(SHAPE_PIN, b"- a\n"), "shape-pin-unreadable",
                 f"{SHAPE_PIN}: not a mapping", id="shape-pin-not-a-mapping"),
    pytest.param(written("contracts/openxdox-pin.yaml", b"- a\n"),
                 "neutral-pin-unreadable",
                 "contracts/openxdox-pin.yaml: not a mapping",
                 id="neutral-pin-not-a-mapping"),
])
def test_every_file_is_named_relative_to_the_root(validator, project,
                                                  break_it, code, detail):
    """The coordinator's ruling on #712: one rule for every file this gate
    names. `not a mapping`, a missing shape pin and the three manifest
    refusals named the ABSOLUTE path, raw; each is the path relative to the
    root, POSIX, as #633's `workflow-unreadable` lines are."""
    break_it(project)
    refusal = refusal_of_the_run(validator, project)
    assert (refusal.code, refusal.detail) == (code, detail)
    assert str(project) not in str(refusal)


def test_a_pin_that_is_not_utf8_keeps_its_words_and_names_it_relative(
        validator, project):
    """`load_yaml`'s other refusals keep their id, their words and their
    remedy, and name the file as this gate names every file (#712)."""
    pin = project / "contracts" / "spec-pin.yaml"
    data = pin.read_bytes() + b"# caf\xe9\n"
    pin.write_bytes(data)
    refusal = refusal_of_the_run(validator, project)
    assert refusal.code == "yaml-unreadable"
    assert refusal.detail == not_utf8_line("contracts/spec-pin.yaml", data)
    assert refusal.remediation.startswith(
        "Remediation: every YAML file this tool reads must be UTF-8. ")


def test_a_pin_that_does_not_parse_names_it_relative(validator, project):
    (project / "contracts" / "spec-pin.yaml").write_bytes(
        b"commit: [unclosed\n")
    refusal = refusal_of_the_run(validator, project)
    assert refusal.code == "yaml-unparsable"
    assert refusal.detail.startswith("contracts/spec-pin.yaml: "), refusal
    assert str(project) not in str(refusal)


def test_the_gate_names_the_pin_so_beside_an_older_library(
        validator, project, monkeypatch):
    """THE SKEW RULE (#370, #610): a root may keep a `repo_shape.py` older
    than its `validate-pins.py`, whose `load_yaml` gave an `OSError` as
    `<path>: [Errno 13] Permission denied: '<path>'`. The gate's line is read
    off the `OSError` the refusal was raised from, which `load_yaml` has
    always chained, and not off those words."""
    real = validator.load_yaml

    def older(path):
        if Path(path).name != "spec-pin.yaml":
            return real(path)
        exc = PermissionError(errno.EACCES, "Permission denied", str(path))
        raise validator.Refusal("yaml-unreadable", f"{path}: {exc}") from exc

    monkeypatch.setattr(validator, "load_yaml", older)
    refusal = refusal_of_the_run(validator, project)
    assert refusal.detail == (
        "contracts/spec-pin.yaml: cannot be read (Permission denied)")
    assert refusal.remediation == READS + PERMISSION + AGAIN


def test_load_yaml_names_a_file_it_cannot_open_once(tmp_path):
    """The library's own line, for every tool that reads YAML: the path once
    and the system's reason, where `str()` of the `OSError` named the path a
    second time in Python's quoting (#712)."""
    path = tmp_path / "absent.yaml"
    refusal = refusal_for(path)
    assert refusal.code == "yaml-unreadable"
    assert refusal.detail == (
        f"{path}: cannot be read ({os.strerror(errno.ENOENT)})")
    assert isinstance(refusal.__cause__, FileNotFoundError)


# --- L4-105: each cause its own advice ---------------------------------------

CAUSES = [
    pytest.param("stat", errno.EIO, id="stat-io-error"),
    pytest.param("stat", errno.ENAMETOOLONG, id="stat-name-too-long"),
    pytest.param("read_text", errno.EIO, id="read-io-error"),
]


@pytest.mark.parametrize("method, code", CAUSES)
def test_a_workflow_that_fails_for_another_cause_is_not_told_to_chmod(
        validator, project, monkeypatch, method, code):
    """A workflow file whose `stat` or read fails with an I/O error or a name
    too long is not put right by a mode: it gets `OTHER`, and not the
    permission sentence it was given whatever the cause."""
    (project / WORKFLOWS / "legs.yml").write_bytes(leg_workflow(project))
    failing(monkeypatch, method, {"legs.yml": os_error(code)})
    with pytest.raises(validator.Refusal) as caught:
        validator._workflow_refs(project)
    refusal = caught.value
    assert refusal.code == "workflow-unreadable"
    assert refusal.detail == (
        f"{WORKFLOWS}/legs.yml: cannot be read ({os.strerror(code)})")
    assert OTHER in refusal.remediation, refusal.remediation
    assert FILE_ADVICE not in refusal.remediation, refusal.remediation
    assert "chmod" not in refusal.remediation, refusal.remediation


def test_each_cause_in_one_refusal_gets_its_own_advice(validator, project,
                                                       monkeypatch):
    """One refusal names every file (#359), so a permission and an I/O error
    in one run are told both, the permission's first."""
    for name in ("legs.yml", "other.yml"):
        (project / WORKFLOWS / name).write_bytes(b"on: [push]\n")
    failing(monkeypatch, "stat", {"legs.yml": PermissionError(
        errno.EACCES, "Permission denied")})
    failing(monkeypatch, "read_text", {"other.yml": os_error(errno.EIO)})
    with pytest.raises(validator.Refusal) as caught:
        validator._workflow_refs(project)
    refusal = caught.value
    assert refusal.detail.splitlines() == [
        f"{WORKFLOWS}/legs.yml: cannot be read (Permission denied)",
        f"{WORKFLOWS}/other.yml: cannot be read "
        f"({os.strerror(errno.EIO)})"]
    assert FILE_ADVICE in refusal.remediation, refusal.remediation
    assert OTHER in refusal.remediation, refusal.remediation
    assert (refusal.remediation.index(FILE_ADVICE)
            < refusal.remediation.index(OTHER)), refusal.remediation


@pytest.mark.parametrize("name, code, named", SITES)
@pytest.mark.parametrize("failure", [errno.EIO, errno.ENAMETOOLONG],
                         ids=lambda code: errno.errorcode[code])
def test_a_file_whose_stat_fails_for_another_cause_is_told_so(
        validator, project, monkeypatch, name, code, named, failure):
    """The same rule at the five sites: the system's own reason, and
    `OTHER`, which never says `chmod`."""
    declare_openxdox(project)
    failing(monkeypatch, "stat", {name: os_error(failure)})
    refusal = refusal_of_the_run(validator, project)
    assert refusal.code == code
    assert refusal.detail == (
        f"{named}: cannot be read ({os.strerror(failure)})")
    assert refusal.remediation == READS + OTHER + AGAIN


def read_refused(validator, monkeypatch, name: str, error: OSError) -> None:
    """Reading `name` fails with `error`: `load_yaml`'s `read_text` for a
    YAML file, `file_sha256` for a shape copy."""
    if name.endswith(".yaml"):
        failing(monkeypatch, "read_text", {name: error})
        return
    real = validator.file_sha256

    def sha256(path):
        if Path(path).name == name:
            raise error
        return real(path)

    monkeypatch.setattr(validator, "file_sha256", sha256)


@pytest.mark.parametrize("name, code, named", [
    row for row in SITES if row.id != "neutral-pin"])
@pytest.mark.parametrize("failure, reason, advice", [
    pytest.param(PermissionError(errno.EACCES, "Permission denied"),
                 "Permission denied", PERMISSION, id="permission"),
    pytest.param(os_error(errno.EIO), os.strerror(errno.EIO), OTHER,
                 id="io-error"),
])
def test_a_file_that_cannot_be_opened_is_refused_by_name(
        validator, project, monkeypatch, name, code, named, failure, reason,
        advice):
    """THE OPEN, AFTER THE `stat`: a pin or the manifest at mode 000 was
    `load_yaml`'s line under the lockstep remedy, and a shape copy at 000
    `file_sha256`'s traceback. The file is named once, relative to the
    root, with its cause's advice. (A neutral-product pin is opened by the
    same `_load` as the others; this root declares none to open.)"""
    read_refused(validator, monkeypatch, name, failure)
    refusal = refusal_of_the_run(validator, project)
    assert refusal.code == code
    assert refusal.detail == f"{named}: cannot be read ({reason})"
    assert refusal.remediation == READS + advice + AGAIN


# --- L4-106, L4-144 and every other print: each name and path spelled --------

def refusal_text(validator, call, *args) -> str:
    """`str()` of the `Refusal` `call(*args)` raises: what `main` prints."""
    with pytest.raises(validator.Refusal) as caught:
        call(*args)
    return str(caught.value)


def report_text(report) -> str:
    """Every finding and note a check added, as the gate prints them."""
    return "\n".join(report.findings + report.notes)


def no_git(*_args, **_kwargs):
    """A git that is not there, as `subprocess` names it."""
    raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), "git")


def gitlink(validator, monkeypatch, answer) -> None:
    """`recorded_gitlink` answering `answer`, or raising it."""
    def recorded(root, path):
        if isinstance(answer, BaseException):
            raise answer
        return answer
    monkeypatch.setattr(validator, "recorded_gitlink", recorded)


def initialized(monkeypatch, value: str) -> None:
    """The leg at `value` is a checkout: a `stat` of its `.git`, which is
    what `_is_there` asks, finds a directory, on any platform."""
    real = Path.stat
    found = os.stat_result((stat.S_IFDIR | 0o755,) + (0,) * 9)

    def answer(self, *args, **kwargs):
        if self.name == ".git" and self.parent.name == value:
            return found
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", answer)


def valid_pin(validator) -> dict:
    """A pin whose digest fields are well formed."""
    return {"revision_kind": "commit", "commit": COMMIT,
            "digests": {"tree_sha256": "a" * 64},
            "digest_definition": validator.TREE_DIGEST_DEFINITION,
            "source_repository": "o/r"}


def written_pin(root: Path, name: str, body: bytes) -> None:
    (root / "contracts" / f"{name}-pin.yaml").write_bytes(body)


def leg_pin_text(v, root, value, body: bytes | None = None) -> str:
    """What `_load_leg_pin` raises for the leg `value`, its pin `body`."""
    if body is not None:
        written_pin(root, value, body)
    return refusal_text(v, v._load_leg_pin, root, value, "spec", "o/r",
                        v.Report())


def leg_pin_path(value: str) -> str:
    return f"contracts/{value}-pin.yaml"


# Each print site: `(validator, root, monkeypatch, value) -> (printed, the
# values in it that must be spelled, one entry per time each is printed)`.

def pin_missing_path(v, root, mp, value):
    return leg_pin_text(v, root, value), [leg_pin_path(value)]


def pin_missing_repository(v, root, mp, value):
    return refusal_text(v, v._load_leg_pin, root, "nosuch", "spec", value,
                        v.Report()), [value]


def pin_cannot_be_read(v, root, mp, value):
    refused_stat(mp, f"{value}-pin.yaml")
    return leg_pin_text(v, root, value), [leg_pin_path(value)]


def pin_not_a_mapping(v, root, mp, value):
    return leg_pin_text(v, root, value, b"- a\n"), [leg_pin_path(value)]


def pin_not_utf8(v, root, mp, value):
    return leg_pin_text(v, root, value, b"a: caf\xe9\n"), [leg_pin_path(value)]


def pin_unparsable(v, root, mp, value):
    return (leg_pin_text(v, root, value, b"commit: [unclosed\n"),
            [leg_pin_path(value)])


def pin_commit_refused(v, root, mp, value):
    return (leg_pin_text(v, root, value, b"kind: pinned_contract_manifest\n"
                         b"revision_kind: commit\ncommit: abc\n"),
            [leg_pin_path(value)])


def pin_findings(v, root, mp, value):
    """pin-wrong-kind, pin-tag-only, pin-path-mismatch and
    pin-repository-mismatch each name the pin; the path line names the
    leg's role too."""
    written_pin(root, value, (
        f"kind: other\nrevision_kind: tag\ncommit: {COMMIT}\n"
        "submodule_path: elsewhere\nsource_repository: o/other\n").encode())
    report = v.Report()
    v._load_leg_pin(root, value, "spec", "o/r", report)
    assert len(report.findings) == 4, report.findings
    return report_text(report), [leg_pin_path(value)] * 4 + [value]


def gitlink_absent(v, root, mp, value):
    gitlink(v, mp, None)
    return refusal_text(v, v._check_gitlink_matches_pin, root, value, "spec",
                        COMMIT, "rel", v.Report()), [value]


def gitlink_unread(v, root, mp, value):
    gitlink(v, mp, FileNotFoundError(errno.ENOENT, "No such file", "git"))
    return refusal_text(v, v._check_gitlink_matches_pin, root, value, "spec",
                        COMMIT, "rel", v.Report()), [value]


def gitlink_mismatch(v, root, mp, value):
    gitlink(v, mp, OTHER_COMMIT)
    report = v.Report()
    v._check_gitlink_matches_pin(root, "spec", value, COMMIT, "rel", report)
    return report_text(report), [value]


def gitlink_note(v, root, mp, value):
    gitlink(v, mp, COMMIT)
    report = v.Report()
    v._check_gitlink_matches_pin(root, "spec", value, COMMIT, "rel", report)
    return report_text(report), [value]


def digest_text(v, root, value, code: str, pin=None) -> str:
    """`_check_pin_digest`'s refusal for the leg at `value`, which must be
    `code`'s: a row spelled in another refusal would test nothing."""
    text = refusal_text(v, v._check_pin_digest, root, value, COMMIT,
                        pin or {}, "rel", v.Report())
    assert text.startswith(f"REFUSED {code}: "), text
    return text


def digest_uninitialized(v, root, mp, value):
    return digest_text(v, root, value, "pin-submodule-uninitialized"), [
        value]


def digest_lookup_unrun(v, root, mp, value):
    initialized(mp, value)
    mp.setattr(v, "git_out", no_git)
    return digest_text(v, root, value, "git-not-runnable"), [value]


def digest_commit_unresolvable(v, root, mp, value):
    initialized(mp, value)

    def refused_by_git(*_args, **_kwargs):
        raise v.Refusal("git-failed", "it said no")

    mp.setattr(v, "git_out", refused_by_git)
    return digest_text(v, root, value, "pin-commit-unresolvable"), [value]


def digest_recompute_unrun(v, root, mp, value):
    initialized(mp, value)
    mp.setattr(v, "git_out", lambda *_args, **_kwargs: "")
    mp.setattr(v, "tree_digest", no_git)
    return digest_text(v, root, value, "git-not-runnable",
                       valid_pin(v)), [value]


def digest_note(v, root, mp, value):
    initialized(mp, value)
    mp.setattr(v, "git_out", lambda *_args, **_kwargs: "")
    mp.setattr(v, "tree_digest", lambda *_args, **_kwargs: "a" * 64)
    report = v.Report()
    v._check_pin_digest(root, value, COMMIT, valid_pin(v), "rel", report)
    return report_text(report), [value]


def workflow_reference(v, root, mp, value):
    report = v.Report()
    v._check_workflow_refs_for_leg(
        [(Path(WORKFLOWS) / f"{value}.yml", "o/r", OTHER_COMMIT)], "o/r",
        "spec", COMMIT, report, "spec")
    return report_text(report), [f"{value}.yml"]


def workflow_named(root: Path, value: str, data: bytes) -> str:
    rel = f"{WORKFLOWS}/{value}.yml"
    (root / rel).write_bytes(data)
    return rel


def workflow_not_utf8(v, root, mp, value):
    rel = workflow_named(root, value, b"# caf\xe9\n")
    return refusal_text(v, v._workflow_refs, root), [rel]


def workflow_unopened(v, root, mp, value):
    rel = workflow_named(root, value, b"on: [push]\n")
    failing(mp, "read_text", {f"{value}.yml": PermissionError(
        errno.EACCES, "Permission denied")})
    return refusal_text(v, v._workflow_refs, root), [rel]


def workflow_stat_refused(v, root, mp, value):
    rel = workflow_named(root, value, b"on: [push]\n")
    refused_stat(mp, f"{value}.yml")
    return refusal_text(v, v._workflow_refs, root), [rel]


def bump_root(v, root, mp, value):
    where = root / value
    return v._bump_command(where, "spec"), [str(where)]


def bump_role(v, root, mp, value):
    return v._bump_command(root, value), [value]


def put_back(v, root, mp, value):
    """It names the leg, and then in `git submodule update -- <leg>`."""
    return v._put_back([value]), [value, value]


def held_while_digest_stands(v, root, mp, value):
    return v._held_then("the bump-leg.py line", "that leg",
                        v.Back(value, OTHER_COMMIT, True), None), [value]


def held_move_kept(v, root, mp, value):
    return v._held_then("the bump-leg.py line", "x",
                        v.Back(value, OTHER_COMMIT, False),
                        {"code": ["pin-digest-mismatch"]}), [value, value]


def held_two_off(v, root, mp, value):
    return v._gitlink_repairs_held_back([value, "code"], []), [value, value]


def held_other_leg(v, root, mp, value):
    return v._gitlink_repairs_held_back(
        ["spec"], [], "the bump-leg.py line",
        v.Back("spec", OTHER_COMMIT, False),
        {value: ["pin-digest-mismatch"]}), [value, value]


def held_back_off(v, root, mp, value):
    return v._gitlink_repairs_held_back(
        ["code"], ["pin-wrong-kind"], "the bump-leg.py line",
        v.Back(value, OTHER_COMMIT, False)), [value] * 3


def held_for_whom(v, root, mp, value):
    return v._gitlink_repairs_held_back(
        [value], [], "the bump-leg.py line",
        v.Back("spec", OTHER_COMMIT, False)), [value]


def curable_under_gitlink(v, root, mp, value):
    one = v.Curable(0, "spec", value, COMMIT, None)
    return v._curable_ending(root, one, ["spec"], [], {
        "spec": v.Back(value, OTHER_COMMIT, False)}, "spec"), [value]


def shape_commits(v, root, mp, value):
    """shape-pin-manifest-disagree names the pin's commit and the
    manifest's, neither of which is asked to be 40 hex first. The pin's is
    named twice: `shape-pin-commit` has always `repr`'d it."""
    pin = root / SHAPE_PIN
    text = pin.read_bytes().decode("utf-8")
    line = "commit: " + double_quoted(value)
    pin.write_bytes(re.sub(r"^commit: .*$", lambda _match: line, text,
                           count=1, flags=re.M).encode("utf-8"))
    report = v.Report()
    v._check_shape_pin_header(root, {"shape": {"commit": value + "x"}}, report)
    return report_text(report), [value, value, value + "x"]


def copy_missing(v, root, mp, value):
    report = v.Report()
    v._check_shape_copy(root, {"path": value, "sha256": "0" * 64}, SHAPE_PIN,
                        report)
    return report_text(report), [value]


def copy_drift(v, root, mp, value):
    """The copy's path and the digest its row records."""
    (root / value).write_bytes(b"x\n")
    report = v.Report()
    v._check_shape_copy(root, {"path": value, "sha256": value}, SHAPE_PIN,
                        report)
    return report_text(report), [value, value]


def copy_unreadable(v, root, mp, value):
    refused_stat(mp, value)
    return refusal_text(v, v._check_shape_copy, root,
                        {"path": value, "sha256": "0" * 64}, SHAPE_PIN,
                        v.Report()), [value]


def source_no_path(v, root, mp, value):
    return refusal_text(v, v.PinSources, [f"{value}="], [value]), [
        f"{value}=", value]


def source_read_as_path(v, root, mp, value):
    return v.PinSources(["k=x"], [value]).read_as_path("k=x"), [value]


def recompute(v, root, mp, product, repository, sources, shared=frozenset()):
    """`_recompute_neutral_pin_digest`'s report, with no ambient variable
    and no `gh` to answer."""
    clear_ambient_pin_sources(mp)

    def no_gh(*_args, **_kwargs):
        raise v.Refusal("gh-not-found", "no gh here")

    mp.setattr(v, "tree_digest_from_gh", no_gh)
    report = v.Report()
    v._recompute_neutral_pin_digest(root, product, repository, COMMIT, "rel",
                                    sources, report, shared)
    return report_text(report)


def keyed_source(v, root, mp, value):
    """The keyed source's `how` names the product."""
    sources = v.PinSources([f"{value}={root / 'nowhere'}"], [value])
    return recompute(v, root, mp, value, "o/r", sources), [value]


def source_repository(v, root, mp, value):
    """The finding, and its remedy, name the pin's `source_repository`."""
    sources = v.PinSources([f"openX={root / 'nowhere'}"], ["openX"])
    return recompute(v, root, mp, "openX", value, sources), [value, value]


def sibling_source(v, root, mp, value):
    """A checkout beside the root, named for the repository: the source and
    its `how` name it."""
    sibling = root.parent / value
    (sibling / ".git").mkdir(parents=True)
    text = recompute(v, root, mp, "openX", f"o/{value}",
                     v.PinSources([], ["openX"]))
    return text, [str(sibling), str(sibling), f"o/{value}", f"o/{value}"]


def skip_line(v, root, mp, value):
    return recompute(v, root, mp, value, "o/r",
                     v.PinSources([], [value])), [value]


def skip_line_shared(v, root, mp, value):
    shared = frozenset({v.pin_product_key(value)})
    return recompute(v, root, mp, value, "o/r", v.PinSources([], [value]),
                     shared), [value, value]


def skip_line_beside(v, root, mp, value):
    return recompute(v, root, mp, "openX", f"o/{value}",
                     v.PinSources([], ["openX"])), [f"../{value}"]


def neutral_pin_missing(v, root, mp, value):
    """L4-144: the pin's path, built from the entry, and the remedy's
    `--pin`; the entry itself was already `repr`'d."""
    text = refusal_text(v, v._check_neutral_pin_entry_and_load, root, value,
                        v.Report())
    return text, [f"contracts/{value.lower()}-pin.yaml", value, value]


def neutral_pin_not_a_mapping(v, root, mp, value):
    (root / "contracts" / f"{value.lower()}-pin.yaml").write_bytes(b"- a\n")
    text = refusal_text(v, v._check_neutral_pin_entry_and_load, root, value,
                        v.Report())
    return text, [f"contracts/{value.lower()}-pin.yaml"]


def neutral_note(v, root, mp, value):
    mp.setattr(v, "_check_neutral_pin_entry_and_load",
               lambda *_args: (valid_pin(v), "rel"))
    mp.setattr(v, "_recompute_neutral_pin_digest",
               lambda *_args, **_kwargs: ("a" * 64, "how"))
    report = v.Report()
    v._check_one_neutral_product_pin(root, value, report,
                                     v.PinSources([], [value]))
    return report_text(report), [value]


def unused_keyed(v, root, mp, value):
    report = v.Report()
    v._note_unused_pin_sources(v.PinSources([f"{value}=x"], [value]), report)
    return report_text(report), [f"{value}=x", value]


PRINTS = [
    pytest.param(pin_missing_path, id="pin-missing-path"),
    pytest.param(pin_missing_repository, id="pin-missing-repository"),
    pytest.param(pin_cannot_be_read, id="pin-cannot-be-read"),
    pytest.param(pin_not_a_mapping, id="pin-not-a-mapping", marks=ON_DISK),
    pytest.param(pin_not_utf8, id="pin-not-utf-8", marks=ON_DISK),
    pytest.param(pin_unparsable, id="pin-unparsable", marks=ON_DISK),
    pytest.param(pin_commit_refused, id="pin-commit-not-40-hex",
                 marks=ON_DISK),
    pytest.param(pin_findings, id="pin-findings", marks=ON_DISK),
    pytest.param(gitlink_absent, id="gitlink-absent"),
    pytest.param(gitlink_unread, id="gitlink-git-not-runnable"),
    pytest.param(gitlink_mismatch, id="gitlink-mismatch"),
    pytest.param(gitlink_note, id="gitlink-note"),
    pytest.param(digest_uninitialized, id="digest-uninitialized"),
    pytest.param(digest_lookup_unrun, id="digest-lookup-git-not-runnable"),
    pytest.param(digest_commit_unresolvable, id="digest-commit-unresolvable"),
    pytest.param(digest_recompute_unrun, id="digest-git-not-runnable"),
    pytest.param(digest_note, id="digest-note"),
    pytest.param(workflow_reference, id="workflow-reference-mismatch"),
    pytest.param(workflow_not_utf8, id="workflow-not-utf-8", marks=ON_DISK),
    pytest.param(workflow_unopened, id="workflow-unopened", marks=ON_DISK),
    pytest.param(workflow_stat_refused, id="workflow-stat-refused",
                 marks=ON_DISK),
    pytest.param(bump_root, id="bump-line-root"),
    pytest.param(bump_role, id="bump-line-leg"),
    pytest.param(put_back, id="put-back"),
    pytest.param(held_while_digest_stands, id="held-while-digest-stands"),
    pytest.param(held_move_kept, id="held-move-kept"),
    pytest.param(held_two_off, id="held-two-legs-off"),
    pytest.param(held_other_leg, id="held-other-leg-out-of-step"),
    pytest.param(held_back_off, id="held-back-off-its-pin"),
    pytest.param(held_for_whom, id="held-names-its-leg"),
    pytest.param(curable_under_gitlink, id="curable-under-gitlink"),
    pytest.param(shape_commits, id="shape-pin-commits"),
    pytest.param(copy_missing, id="shape-copy-missing"),
    pytest.param(copy_drift, id="shape-copy-drift", marks=ON_DISK),
    pytest.param(copy_unreadable, id="shape-copy-unreadable"),
    pytest.param(source_no_path, id="pin-source-no-path"),
    pytest.param(source_read_as_path, id="pin-source-read-as-path"),
    pytest.param(keyed_source, id="pin-source-keyed"),
    pytest.param(source_repository, id="pin-source-repository"),
    pytest.param(sibling_source, id="pin-source-sibling", marks=ON_DISK),
    pytest.param(skip_line, id="skip-product"),
    pytest.param(skip_line_shared, id="skip-shared-variable"),
    pytest.param(skip_line_beside, id="skip-checkout-beside"),
    pytest.param(neutral_pin_missing, id="neutral-pin-missing"),
    pytest.param(neutral_pin_not_a_mapping, id="neutral-pin-not-a-mapping",
                 marks=ON_DISK),
    pytest.param(neutral_note, id="neutral-pin-note"),
    pytest.param(unused_keyed, id="pin-source-not-used"),
]


@pytest.mark.parametrize("value", UNPRINTABLE)
@pytest.mark.parametrize("site", PRINTS)
def test_every_name_and_path_it_prints_is_spelled(validator, project,
                                                  monkeypatch, site, value):
    """ONE ROW FOR EACH PRINT (#712). Every name and path that comes from the
    disk, the manifest, a pin or the command line is printed as `_shown`
    spells it: `repr` where a character in it is not printable, so a newline
    does not begin a line, a bidi control does not reorder the line it is
    on, a C1 control does not break it and an ESC is not the control it is.
    Each value is printed spelled, as many times as it is printed, and
    never raw."""
    printed, values = site(validator, project, monkeypatch, value)
    for one in values:
        assert one not in printed, (one, printed)
        assert printed.count(repr(one)) >= values.count(one), (one, printed)


@pytest.mark.parametrize("site", PRINTS)
def test_a_printable_name_is_printed_as_it_always_was(validator, project,
                                                      monkeypatch, site):
    """The control: `_shown` leaves a printable name the bytes it always
    was. Each value is printed as many times, and at least one of those
    prints is bare: only a print that `repr`'d the value before #712 (an
    entry, a commit) still quotes it."""
    printed, values = site(validator, project, monkeypatch, PRINTABLE)
    for one in values:
        assert printed.count(one) >= values.count(one), (one, printed)
        assert printed.count(repr(one)) < values.count(one), (one, printed)


# --- the issue's own inputs, as a project runs the gate ----------------------

def test_the_issue_s_pin_entry_reaches_stderr_spelled(project):
    """L4-144'S MEASUREMENT: `neutral_product_pins: ["<ESC>[31mRED"]` is a
    list, so the entry is one pin. Its path and the remedy's `--pin` carried
    the ESC (octal 033) to stderr; the entry itself was already `repr`'d."""
    edit(project, "neutral_product_pins: []",
         "neutral_product_pins: [" + double_quoted("\x1b[31mRED") + "]")
    result = validate(project)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "\x1b" not in result.stderr, result.stderr
    assert result.stderr == (
        "REFUSED neutral-pin-missing: project.yaml declares a pin on "
        "'\\x1b[31mRED' but 'contracts/\\x1b[31mred-pin.yaml' does not exist\n"
        "Remediation: `scaffold-project.py --pin '\\x1b[31mRED'@<commit>` "
        "writes that file. A declaration in project.yaml with no pin file "
        "beside it is a claim with no referent — either restore the file "
        "or remove the declaration.\n"), result.stderr


@ON_DISK
def test_the_issue_s_workflow_names_are_one_line_each(project):
    """L4-106'S MEASUREMENT: a `.yml` named with a newline printed as two
    lines, so `N workflow file(s)` was followed by N+1. Each name holding a
    newline, a bidi control, a C1 control, an ESC or a byte that is not
    UTF-8 is now one line, spelled, so the refusal is N lines and the
    remedy. The files are not UTF-8, so no mode is needed and root sees the
    same refusal."""
    data = b"# caf\xe9\n"
    names = sorted(f"{param.values[0]}.yml" for param in UNPRINTABLE)
    for name in names:
        (project / WORKFLOWS / name).write_bytes(data)
    result = validate(project)
    assert result.returncode == 2, result.stdout + result.stderr
    lines = result.stderr.splitlines()
    named = [not_utf8_line(repr(f"{WORKFLOWS}/{name}"), data)
             for name in names]
    assert lines[:len(names)] == [
        "REFUSED workflow-unreadable: " + named[0], *named[1:]], lines
    assert len(lines) == len(names) + 1, lines
    assert lines[-1].startswith(
        f"Remediation: {len(names)} workflow file(s) under "), lines[-1]


# --- L4-143: the note points at the finding ----------------------------------

@pytest.mark.parametrize("spelled, why, code", [
    pytest.param("openXdox", "project.yaml's neutral_product_pins is not a "
                 "list, so it declares no neutral-product pin (see the "
                 "manifest-neutral-product-pins finding)", 1,
                 id="not-a-list"),
    pytest.param("[]", "project.yaml declares no neutral-product pin", 0,
                 id="an-empty-list"),
])
def test_an_unused_pin_source_says_why_nothing_is_declared(project, spelled,
                                                           why, code):
    """L4-143'S MEASUREMENT: under a scalar `neutral_product_pins:`, which
    declares no pin and is `manifest-neutral-product-pins`'s finding, the
    note said only that nothing is declared. It points at the finding; an
    empty list, which is no finding, says what it always said."""
    edit(project, "neutral_product_pins: []",
         f"neutral_product_pins: {spelled}")
    result = run_script(project / "scripts" / "validate-pins.py",
                        "--pin-source", "openXdox=../nowhere", cwd=project)
    assert result.returncode == code, result.stdout + result.stderr
    assert (f"  note --pin-source openXdox=../nowhere: not used — {why}."
            in result.stdout.splitlines()), result.stdout
    assert ("manifest-neutral-product-pins" in result.stderr) == bool(code)


# --- L4-102: a `--pin-source` key is the pin file's fold ---------------------

SHARP, SS = "openß", "openss"


def test_a_key_another_pin_file_s_name_folds_to_is_no_key(validator, project,
                                                          monkeypatch):
    """`openss=` is not `openß`'s key: the two are two pin files, and
    `casefold()` took one for the other. It is read as a bare PATH, and the
    note's sentence says why."""
    clear_ambient_pin_sources(monkeypatch)
    sources = validator.PinSources([f"{SS}=/x"], [SHARP])
    assert sources.reading == {f"{SS}=/x": None}
    assert sources.keyed == {}
    assert sources.read_as_path(f"{SS}=/x") == (
        f"It was read as a PATH: `{SS}` is not a declared neutral-product pin "
        f"(declared: {SHARP}).")
    _, how, _ = validator.resolve_neutral_pin_source(
        project, SHARP, f"o/{SHARP}", sources)
    assert how == "--pin-source", "the bare reading, not the keyed one"


def test_case_still_folds_as_the_pin_file_folds_it(validator):
    """`lower()` is the pin file's fold: `OPENß=` is `openß`'s key."""
    sources = validator.PinSources(["OPENß=/x"], [SHARP])
    assert sources.reading == {"OPENß=/x": SHARP}


def test_two_pin_files_one_casefold_each_keep_their_own_source(
        validator, project, monkeypatch):
    """Both declared: each keyed value answers for its own pin, and neither
    replaces the other."""
    clear_ambient_pin_sources(monkeypatch)
    sources = validator.PinSources([f"{SS}=/a", f"{SHARP}=/b"], [SHARP, SS])
    assert sources.replaced == {}
    for product, path in ((SS, "/a"), (SHARP, "/b")):
        found, how, typed = validator.resolve_neutral_pin_source(
            project, product, f"o/{product}", sources)
        assert (found, how, typed) == (
            Path(path), f"--pin-source {product}=...", f"{product}={path}")
