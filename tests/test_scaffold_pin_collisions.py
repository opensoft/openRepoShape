# SPDX-License-Identifier: Apache-2.0
"""A `--pin` is written where nothing else is (#241).

`scaffold-project.py --pin <product>@<40 hex>` writes the pin at
`neutral_pin_path(product)`, `contracts/<product lowercased>-pin.yaml`, after
the shape's own files and before the copy pin. Nothing asked whether that
file was one the shape writes itself, or one another `--pin` writes. On main
through 39ac59c, `--pin spec@<sha>` (`Spec@`, `code@`, `<owner>/code@`,
`shape@`) and `--pin openGlass@<sha> --pin OpenGlass@<sha>` planned under
`--dry-run`, exit 0. The real run then created all three repositories, pushed
both legs, and died in the materializer (`materialize-collision`) with the
root never committed, so a corrected re-run was `scaffold-remote-exists`.
`--pin openGlass@<A> --pin openGlass@<B>` exited 0 having written `<B>` and
dropped `<A>` without a word.

The rule asks the materializer's own two definitions: a pin's file is
`neutral_pin_path(product)`, the shape's own files are `assembly_root_paths()`
with no pins. A pin over one of the shape's files is refused, and so are two
`--pin`s whose files are one path, whether or not their commits agree, each
argument named as it was typed. Both before anything is created, `--dry-run`
alike, and before #197's leg-path refusal, which would otherwise count a pin
path twice.

`neutral_pin_path` lowercases, so the capital cases are strings compared in
this process: nothing is written to a disk that could fold them, and they
hold on every platform. The tests that call `main()` here refuse every process
start, which shows the refusal comes before `git` and `gh`; the end-to-end
tests run the script against a local remote directory with a `--pin-source`
clone and a `gh` that fails if it is called.
"""

from __future__ import annotations

import importlib.util
import os
import stat
import subprocess
import textwrap
from pathlib import Path

import pytest

from conftest import ORG, SCAFFOLD, WINDOWS_SKIP, git, run_script

PROJECT = "Northwind"
UTF8 = "utf-8"
REFUSED = "REFUSED scaffold-pin-collides"
LEG_REFUSED = "REFUSED scaffold-leg-path-collides"
BASE_ARGS = ("--org", ORG, "--project", PROJECT, "--elected-by", "Test Human",
             "--elected-on", "2026-09-02")

#: How a pin over one of the shape's own files is refused, after naming the
#: argument, the product and the file.
SHAPE_WRITES = ("a file the shape writes into the assembly root itself: name "
                "the product for the repository it pins.")
#: How two pins at one path are refused, after naming both and the file.
ONE_FILE = "which holds one pin: pass each product once."
#: Every refusal's remediation, word for word.
REMEDIATION = (
    "Remediation: nothing was created. A neutral product is named for the "
    "repository it pins, as `--pin openGlass@<40 hex commit>` names "
    "opensoft/openGlass by default, and its pin is written at "
    "`contracts/<openproduct>-pin.yaml`, the name lowercased, beside the "
    "pins the shape writes for its two legs and for itself, so `spec`, "
    "`code` and `shape`, in any case, are names no product can be pinned "
    "under. Pass each product once, by the name of the repository it pins.")

#: `(the --pin values, what the refusal says)`, `{A}` and `{B}` being two
#: commits of the `--pin-source` clone. The first five are the three names
#: whose file the shape writes, one in capitals and one owner-qualified; the
#: last three are two pins at one file, by case, by a repeat with one commit
#: and by a repeat with two.
REFUSED_CASES = [
    pytest.param(["spec@{A}"],
                 "--pin 'spec@{A}' writes the pin of the product `spec` at "
                 "`contracts/spec-pin.yaml`, " + SHAPE_WRITES, id="spec"),
    pytest.param(["Spec@{A}"],
                 "--pin 'Spec@{A}' writes the pin of the product `Spec` at "
                 "`contracts/spec-pin.yaml`, " + SHAPE_WRITES, id="Spec"),
    pytest.param(["code@{A}"],
                 "--pin 'code@{A}' writes the pin of the product `code` at "
                 "`contracts/code-pin.yaml`, " + SHAPE_WRITES, id="code"),
    pytest.param([f"{ORG}/code@{{A}}"],
                 f"--pin '{ORG}/code@{{A}}' writes the pin of the product "
                 "`code` at `contracts/code-pin.yaml`, " + SHAPE_WRITES,
                 id="owner-code"),
    pytest.param(["shape@{A}"],
                 "--pin 'shape@{A}' writes the pin of the product `shape` at "
                 "`contracts/shape-pin.yaml`, " + SHAPE_WRITES, id="shape"),
    pytest.param(["openGlass@{A}", "OpenGlass@{A}"],
                 "--pin 'openGlass@{A}' and --pin 'OpenGlass@{A}' write the "
                 "pins of the products `openGlass` and `OpenGlass` at one "
                 "file, `contracts/openglass-pin.yaml`, " + ONE_FILE,
                 id="case-pair"),
    pytest.param(["openGlass@{A}", "openGlass@{A}"],
                 "--pin 'openGlass@{A}' and --pin 'openGlass@{A}' write the "
                 "pins of the product `openGlass` at one file, "
                 "`contracts/openglass-pin.yaml`, " + ONE_FILE,
                 id="repeat-one-commit"),
    pytest.param(["openGlass@{A}", "openGlass@{B}"],
                 "--pin 'openGlass@{A}' and --pin 'openGlass@{B}' write the "
                 "pins of the product `openGlass` at one file, "
                 "`contracts/openglass-pin.yaml`, " + ONE_FILE,
                 id="repeat-two-commits"),
]


@pytest.fixture(scope="module")
def scaffold():
    """`scaffold-project.py` loaded as a module, so `main()` runs here."""
    module_spec = importlib.util.spec_from_file_location(
        "scaffold_pin_collisions", SCAFFOLD)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def glass(tmp_path_factory):
    """A local stand-in for `openGlass` with two commits, for `--pin-source`:
    `(path, first commit, second commit)`. A run that gets past the refusal
    reads its pins' digests here, and no network is asked."""
    path = tmp_path_factory.mktemp("glass") / "openGlass"
    path.mkdir()
    git("init", "-q", "-b", "main", cwd=path)
    commits = []
    for name in ("README.md", "NOTES.md"):
        (path / name).write_text(f"# {name}\n", encoding=UTF8)
        git("add", "-A", cwd=path)
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
            name, cwd=path)
        commits.append(git("rev-parse", "HEAD", cwd=path).stdout.strip())
    return (path, *commits)


def pins_of(glass, values) -> list[str]:
    """`values` with `{A}` and `{B}` filled from `glass`."""
    _, first, second = glass
    return [value.format(A=first, B=second) for value in values]


def pin_args(glass, values) -> tuple[str, ...]:
    """`--pin <value>` for each of `values`, and the `--pin-source`."""
    return (*(arg for value in pins_of(glass, values)
              for arg in ("--pin", value)),
            "--pin-source", str(glass[0]))


class ProcessStarted(AssertionError):
    """A process was started where the refusal should already have come."""


@pytest.fixture
def no_process(monkeypatch):
    """Every command the scaffold runs, `git` and `gh` alike, starts through
    `subprocess.Popen`. While this holds, starting one fails the test and
    names the command, so a refusal that passes came before the first `git`
    or `gh`, on every platform."""
    def refuse(args, *_, **__):
        raise ProcessStarted(f"a process was started: {args!r}")
    monkeypatch.setattr(subprocess, "Popen", refuse)


def refusal_of(scaffold, capsys, *args: str) -> str:
    """`main()` with `args`: the pin refusal it printed, checked whole."""
    code = scaffold.main([*BASE_ARGS, *args])
    out, err = capsys.readouterr()
    assert code == 2, out + err
    assert out == "", "the refusal comes before the plan is printed"
    assert err.startswith(f"{REFUSED}: "), err
    assert err.endswith(f"\n{REMEDIATION}\n"), err
    return err


def listing(directory: Path) -> list[str]:
    return sorted(path.relative_to(directory).as_posix()
                  for path in directory.rglob("*"))


# --- refused, in this process, dry and real ---------------------------------

@pytest.mark.parametrize("dry", [pytest.param(True, id="dry-run"),
                                 pytest.param(False, id="real-run")])
@pytest.mark.parametrize("values, said", REFUSED_CASES)
def test_a_colliding_pin_is_refused_before_any_process(
        scaffold, glass, no_process, capsys, tmp_path, values, said, dry):
    """The sentence names each argument as typed, the product and the file.
    A real run that got past it would read the pin's digest from the
    `--pin-source` with `git`, which `no_process` refuses; and the remote
    and work directories it was given were never made."""
    remotes, work = tmp_path / "remotes", tmp_path / "work"
    err = refusal_of(scaffold, capsys, *pin_args(glass, values),
                     "--local-remote-dir", str(remotes),
                     "--work-dir", str(work), *(("--dry-run",) if dry else ()))
    _, first, second = glass
    assert err == (f"{REFUSED}: {said.format(A=first, B=second)}\n"
                   f"{REMEDIATION}\n")
    assert not remotes.exists() and not work.exists()


def test_every_collision_is_named_in_the_order_typed(scaffold, glass,
                                                     no_process, capsys):
    """One refusal, one sentence per file, in the order each file's first
    `--pin` was typed: two pins over the shape's own file are both named
    with both products, a repeat in capitals is a repeat, and a pin that
    collides with nothing is not mentioned."""
    _, first, second = glass
    err = refusal_of(scaffold, capsys, *pin_args(glass, [
        "Spec@{A}", "openGlass@{A}", "openPane@{A}", "spec@{B}",
        "OPENGLASS@{B}", "shape@{A}"]), "--dry-run")
    assert err.split("\n", 1)[0] == (
        f"{REFUSED}: --pin 'Spec@{first}' and --pin 'spec@{second}' write the "
        "pins of the products `Spec` and `spec` at `contracts/spec-pin.yaml`, "
        f"{SHAPE_WRITES} --pin 'openGlass@{first}' and --pin "
        f"'OPENGLASS@{second}' write the pins of the products `openGlass` and "
        "`OPENGLASS` at one file, `contracts/openglass-pin.yaml`, "
        f"{ONE_FILE} --pin 'shape@{first}' writes the pin of the product "
        f"`shape` at `contracts/shape-pin.yaml`, {SHAPE_WRITES}")
    assert "openPane" not in err


def test_a_malformed_pin_is_still_its_own_refusal(scaffold, glass, no_process,
                                                  capsys):
    """Every `--pin` is read by `parse_pin` before any is judged, so a
    malformed one is `pin-malformed` wherever it stands, as before."""
    code = scaffold.main([*BASE_ARGS, "--dry-run",
                          *pin_args(glass, ["spec@{A}"]),
                          "--pin", "openGlass@abc"])
    err = capsys.readouterr().err
    assert code == 2
    assert err.startswith("REFUSED pin-malformed: --pin 'openGlass@abc' "), err


# --- the order: before the leg paths, `_identity` and `_declaration` --------

@pytest.mark.parametrize("values, legs", [
    pytest.param(["spec@{A}"], ("--spec-path", "contracts"), id="shape-file"),
    pytest.param(["openGlass@{A}", "OpenGlass@{A}"],
                 ("--code-path", "contracts/openglass-pin.yaml"),
                 id="case-pair"),
])
def test_the_pin_refusal_comes_before_the_leg_path_refusal(
        scaffold, glass, no_process, capsys, monkeypatch, values, legs):
    """A bad pin beside a leg path over a pin's file is the pin refusal, and
    `_refuse_colliding_leg_paths` is never asked, so the leg-path count
    never sees a pin path twice (#197's re-review, N1: "and 4 more" of
    three). The control is the same leg path with a pin that collides with
    nothing: the leg-path refusal, asked once."""
    asked = []
    original = scaffold._refuse_colliding_leg_paths

    def spy(*args, **kwargs):
        asked.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(scaffold, "_refuse_colliding_leg_paths", spy)
    err = refusal_of(scaffold, capsys, *legs, *pin_args(glass, values),
                     "--dry-run")
    assert LEG_REFUSED not in err and " more" not in err
    assert asked == []
    code = scaffold.main([*BASE_ARGS, *legs, "--dry-run",
                          *pin_args(glass, ["openGlass@{A}"])])
    err = capsys.readouterr().err
    assert code == 2
    assert err.startswith(f"{LEG_REFUSED}: {legs[0]} {legs[1]!r} "), err
    assert len(asked) == 1


def test_the_refusal_comes_before_git_is_asked_who_elected(
        scaffold, glass, no_process, capsys, monkeypatch):
    """Without `--elected-by`, `_identity` asks `git config user.name`; the
    control shows it, so the refusal that starts no process came before it.
    `GIT_AUTHOR_NAME` answers first when it is set, and CI sets it, so it is
    unset here."""
    monkeypatch.delenv("GIT_AUTHOR_NAME", raising=False)
    unelected = ["--org", ORG, "--project", PROJECT,
                 "--elected-on", "2026-09-02", "--dry-run"]
    with pytest.raises(ProcessStarted, match="user.name"):
        scaffold.main([*unelected, *pin_args(glass, ["openGlass@{A}"])])
    code = scaffold.main([*unelected, *pin_args(glass, ["shape@{A}"])])
    out, err = capsys.readouterr()
    assert (code, out) == (2, ""), err
    assert err.startswith(f"{REFUSED}: --pin 'shape@"), err


def test_the_refusal_comes_before_the_declaration_is_read(
        scaffold, no_process, capsys, monkeypatch):
    """`_declaration` reads each `--pin`'s digest, with `gh api` when no
    `--pin-source` is given. This shows on every platform that it is never
    called for a colliding pin, and the control that the same command line
    reaches it once nothing collides; the `gh` stub below shows `gh` never
    runs, on POSIX."""
    called = []

    def declaration(args):
        called.append(list(args.pin))
        return {}, set(), (), {}

    monkeypatch.setattr(scaffold, "_declaration", declaration)
    commit = "1" * 40
    refusal_of(scaffold, capsys, "--dry-run", "--pin", f"openGlass@{commit}",
               "--pin", f"OpenGlass@{commit}")
    assert called == []
    with pytest.raises(ProcessStarted):
        scaffold.main([*BASE_ARGS, "--dry-run", "--pin",
                       f"openGlass@{commit}"])
    assert called == [[f"openGlass@{commit}"]]


# --- end to end: nothing is created, and `gh` is never run ------------------

@pytest.fixture
def world(tmp_path):
    """A remote directory holding only `KEEP`, an empty temporary directory,
    a work directory that must not appear, and a `gh` on PATH that records
    its arguments and fails. Windows runs no `#!` script, so there the
    record stays empty whatever happens; `no_process` above carries the
    claim on every platform."""
    remotes, temporary = tmp_path / "remotes", tmp_path / "tmp"
    remotes.mkdir()
    temporary.mkdir()
    (remotes / "KEEP").write_text("here before the run\n", encoding=UTF8)
    bin_dir, log = tmp_path / "fakebin", tmp_path / "gh.log"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(textwrap.dedent("""\
        #!/usr/bin/env python3
        import os, sys
        with open(os.environ["GH_STUB_LOG"], "a", encoding="utf-8") as log:
            log.write(" ".join(sys.argv[1:]) + "\\n")
        print("HTTP 404: Not Found", file=sys.stderr)
        sys.exit(97)
        """), encoding=UTF8)
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
           "GH_STUB_LOG": str(log), "TMPDIR": str(temporary),
           "TEMP": str(temporary), "TMP": str(temporary)}
    return {"remotes": remotes, "tmp": temporary, "work": tmp_path / "work",
            "log": log, "env": env}


def nothing_was_created(world) -> None:
    assert listing(world["remotes"]) == ["KEEP"]
    assert not world["work"].exists()
    assert list(world["tmp"].iterdir()) == []
    assert not world["log"].exists(), (
        f"gh was run: {world['log'].read_text(encoding=UTF8)}")


@pytest.mark.parametrize("values, said", REFUSED_CASES)
def test_a_dry_run_refuses_exactly_as_the_real_run(glass, world, values,
                                                   said):
    """On main through 39ac59c the dry run said yes and the real run made three
    repositories and died in the materializer, or dropped a pin. Now both
    say the same no, word for word, and nothing exists afterwards."""
    args = (*BASE_ARGS, *pin_args(glass, values),
            "--local-remote-dir", str(world["remotes"]),
            "--work-dir", str(world["work"]))
    dry = run_script(SCAFFOLD, *args, "--dry-run", env=world["env"])
    real = run_script(SCAFFOLD, *args, env=world["env"])
    assert (dry.returncode, real.returncode) == (2, 2), (
        dry.stdout + dry.stderr + real.stdout + real.stderr)
    assert dry.stderr == real.stderr
    assert dry.stdout == real.stdout == ""
    _, first, second = glass
    assert real.stderr == (f"{REFUSED}: {said.format(A=first, B=second)}\n"
                           f"{REMEDIATION}\n")
    assert "creating remotes" not in real.stdout
    nothing_was_created(world)


@WINDOWS_SKIP  # the stub `gh` is a `#!` script; Windows executes none
def test_no_gh_command_runs_before_the_refusal(world):
    """Pointed at GitHub, with no `--pin-source`, so `gh api` would read each
    pin's digest, the refusal comes first and `gh` is never run. The control
    is the same run with one of the two pins: it reaches `gh`, so the stub
    would have recorded a call."""
    commit = "1" * 40
    common = (*BASE_ARGS, "--pin", f"openGlass@{commit}",
              "--work-dir", str(world["work"]))
    refused = run_script(SCAFFOLD, *common, "--pin", f"OpenGlass@{commit}",
                         env=world["env"])
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert refused.stderr.startswith(f"{REFUSED}: --pin 'openGlass@{commit}' "
                                     f"and --pin 'OpenGlass@{commit}' ")
    nothing_was_created(world)

    control = run_script(SCAFFOLD, *common, env=world["env"])
    assert control.returncode == 2, control.stdout + control.stderr
    assert "pin-unreadable" in control.stderr
    # Its first `gh` call asks the forge what the id names (#651).
    assert world["log"].read_text(encoding=UTF8).splitlines()[0].endswith(
        f"-f owner=opensoft -f name=openGlass -f oid={commit}")


# --- accepted: one pin, and two different products ---------------------------

@pytest.mark.parametrize("values, files", [
    pytest.param(["openGlass@{A}"], ["contracts/openglass-pin.yaml"],
                 id="one-pin"),
    pytest.param(["openGlass@{A}", "ExplicitOwner/openPane@{B}"],
                 ["contracts/openglass-pin.yaml",
                  "contracts/openpane-pin.yaml"], id="two-products"),
])
def test_pins_that_collide_with_nothing_still_scaffold(glass, world, values,
                                                       files):
    """The plan names each pin's file, and the pushed root holds each pin
    at its own file with its own commit: nothing typed is dropped."""
    args = (*BASE_ARGS, *pin_args(glass, values),
            "--local-remote-dir", str(world["remotes"]),
            "--work-dir", str(world["work"]))
    dry = run_script(SCAFFOLD, *args, "--dry-run", env=world["env"])
    assert dry.returncode == 0, dry.stdout + dry.stderr
    planned = [line for line in dry.stdout.splitlines()
               if line.startswith("pin ")]
    assert [line.split(" -> ")[1].split(" (")[0]
            for line in planned] == files
    result = run_script(SCAFFOLD, *args, env=world["env"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert REFUSED not in result.stderr
    root = world["remotes"] / f"{PROJECT}.git"
    for path, value in zip(files, pins_of(glass, values)):
        pin = git("show", f"main:{path}", cwd=root).stdout
        assert f'commit: "{value.rsplit("@", 1)[1]}"' in pin, pin
    assert not world["log"].exists()
