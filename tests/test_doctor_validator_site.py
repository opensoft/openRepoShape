# SPDX-License-Identifier: Apache-2.0
"""`shape-doctor.py` starts every validator child with no `site` (#342).

THE DEFECT. #306 took the operator's `PYTHONPATH` out of the child that runs
a root's OWN validator, so a root that lost its `scripts/repo_shape.py` is
told what its gate says in CI: `ModuleNotFoundError`, a FINDING. But
`PYTHONPATH` is one route onto `sys.path`, and `site` is another: at
start-up it appends every directory a `.pth` file names, in the user's
site-packages and in the interpreter's own. A `.pth` naming a directory that
holds `repo_shape.py` -- here, as in the issue, the standard's own
`scripts/` -- stood in for the lost file, and the `manifest` row said `ok ...
passes` for a gate that fails in CI. `-s` closes the user's site-packages and
not a virtualenv's, and `-I` no more of them; `run_validator` now starts
every child with `-S`, which closes both.

THE CASES, the issue's own:
- a `.pth` in the user's site-packages (`PYTHONUSERBASE`), with the doctor
  started by this interpreter;
- a `.pth` in a virtualenv's site-packages, with the doctor started by that
  virtualenv's interpreter;
- for each of the two, a root that KEEPS its own `repo_shape.py`, whose gate
  still passes, because `-S` keeps the validator's own directory;
- the child itself, asked in process: no `site`, whichever kind of caller
  starts it, and a template's `PYTHONPATH` still on its path.
An exported `PYTHONPATH` is #306's case, and its tests stay in
`tests/test_shape_doctor.py`.

The fixtures are that file's, imported, so the standard, the project and the
holder are the ones every other doctor test reads. NOTHING HERE REACHES A
NETWORK: the scaffolds use local bare remotes, and the `machine` row asks the
session's `gh` guard.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import run_script
#: The standard, the project, the holder and the helpers every doctor test
#: reads, imported from the module that owns them. Importing a fixture gives
#: this module its own instance of it.
from test_shape_doctor import (  # noqa: F401
    DOCTOR, FAMILY_NAME, TEMPLATE_FALLBACK, doctor_module, holder, project,
    root_without_its_repo_shape, rows_of, scaffolded_here, standard,
)

#: The `.pth` file both routes write: ONE LINE, the standard's `scripts/`,
#: which is the issue's input.
PTH = "standard.pth"
#: What the root's own gate says when it cannot import the file it lost.
LOST = "ModuleNotFoundError: No module named 'repo_shape'"

#: `run_script` starts `sys.executable`, and the virtualenv case needs the
#: doctor started by the VIRTUALENV'S interpreter. So `run_script` starts this
#: hand-off, with the environment it builds, and the hand-off starts the rest
#: of its own argv with that environment and its own output streams.
HAND_OFF = ("import subprocess\n"
            "import sys\n"
            "sys.exit(subprocess.run(sys.argv[1:],\n"
            "                        stdin=subprocess.DEVNULL).returncode)\n")


def probe_env(**extra: str) -> dict:
    """The environment a probe of an interpreter runs in: this one's, with no
    `PYTHONPATH`, so the only route a probe can find `repo_shape` by is the
    `.pth` under test, and no `__pycache__` left in the session's standard."""
    env = {name: value for name, value in os.environ.items()
           if name.upper() != "PYTHONPATH"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(extra)
    return env


def ask(python: Path | str, code: str, env: dict, cwd: Path) -> str:
    """What `python -c <code>` prints, stripped, run from `cwd`."""
    proc = subprocess.run([str(python), "-c", code], cwd=str(cwd),
                          capture_output=True, text=True, check=False,
                          stdin=subprocess.DEVNULL, env=env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout.strip()


def repo_shape_reached_by(python: Path | str, env: dict,
                          cwd: Path) -> Path | None:
    """The `repo_shape.py` that `python` imports from `cwd` under `env`, or
    None where it imports none: whether the route under test EXISTS for that
    interpreter, so a test of the doctor proves something."""
    proc = subprocess.run(
        [str(python), "-c", "import repo_shape; print(repo_shape.__file__)"],
        cwd=str(cwd), capture_output=True, text=True, check=False,
        stdin=subprocess.DEVNULL, env=env)
    if proc.returncode != 0:
        return None
    return Path(proc.stdout.strip()).resolve()


def write_pth(site_packages: Path, standard: Path) -> None:
    """`standard.pth` in `site_packages`, naming the standard's `scripts/`."""
    site_packages.mkdir(parents=True, exist_ok=True)
    (site_packages / PTH).write_text(f"{standard.resolve() / 'scripts'}\n",
                                     encoding="utf-8")


@pytest.fixture(scope="module")
def user_base(standard, tmp_path_factory) -> Path:
    """A `PYTHONUSERBASE` whose user site-packages holds `standard.pth`.

    SKIPPED WHERE THIS INTERPRETER READS NO USER SITE-PACKAGES -- one inside
    a virtualenv, or run with `-s` -- because there the route does not exist,
    and a doctor that ignores it proves nothing about the fix.
    """
    base = tmp_path_factory.mktemp("userbase")
    env = probe_env(PYTHONUSERBASE=str(base))
    write_pth(Path(ask(sys.executable,
                       "import site; print(site.getusersitepackages())",
                       env, base)), standard)
    reached = repo_shape_reached_by(sys.executable, env, base)
    if reached is None:
        pytest.skip("this interpreter reads no user site-packages, so a "
                    ".pth there reaches no validator child")
    assert reached == (standard / "scripts" / "repo_shape.py").resolve(), \
        reached
    return base


@pytest.fixture(scope="module")
def venv_python(standard, tmp_path_factory) -> Path:
    """A virtualenv's interpreter whose site-packages holds `standard.pth`,
    made as the issue made it: `python -m venv --without-pip`."""
    home = tmp_path_factory.mktemp("venv") / "venv"
    made = subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(home)],
        capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL)
    if made.returncode != 0:
        pytest.skip("no virtualenv can be made with this interpreter: "
                    f"{(made.stdout + made.stderr).strip()[-200:]}")
    python = home / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    env = probe_env()
    purelib = "import sysconfig; print(sysconfig.get_path('purelib'))"
    write_pth(Path(ask(python, purelib, env, home)), standard)
    reached = repo_shape_reached_by(python, env, home)
    assert reached == (standard / "scripts" / "repo_shape.py").resolve(), (
        "a .pth in a virtualenv's site-packages is read by its interpreter, "
        f"or this test proves nothing: {reached}")
    return python


def doctor_rows(standard: Path, root: Path, tmp_path: Path,
                python: Path | None = None, **env: str) -> dict:
    """`rows_of` this root, from a doctor with NO `PYTHONPATH` and `env`
    added, started by `python` (by default, this interpreter).

    `PYTHONPATH` is the empty value, which is no entry to Python: `run_script`
    can set a variable but not remove one (`doctor_with_no_pythonpath`)."""
    asked = {"PYTHONPATH": "", **env}
    argv = [str(standard / DOCTOR), "--root", str(root), "--json"]
    if python is None:
        return rows_of(run_script(Path(argv[0]), *argv[1:], env=asked))
    hand_off = tmp_path / "hand_off.py"
    hand_off.write_text(HAND_OFF, encoding="utf-8")
    return rows_of(run_script(hand_off, str(python), *argv, env=asked))


def assert_the_gates_own_failure(row: dict) -> None:
    """The row says what the root's own gate says in CI: it crashed on the
    import of the file the root lost. Never `passes`, and never another
    finding the gate only reaches by importing a `repo_shape` it lacks."""
    assert row["status"] == "FINDING", row
    assert "passes" not in row["reason"], row
    assert row["detail"]["own_copy"] is True, row
    assert row["detail"]["exit"] == 1, row
    assert row["detail"].get("crashed") is True, row
    assert LOST in row["reason"], row


def root_that_keeps_its_own(case: str, project: Path, holder: dict,
                            tmp_path: Path) -> Path:
    """The root whose `case` gate is its own and imports its own
    `scripts/repo_shape.py`, untouched: the session project's private copy,
    or a copy of the holder, so the session's stays intact."""
    if case == "family":
        root = tmp_path / FAMILY_NAME
        shutil.copytree(holder["root"], root, symlinks=True)
    else:
        root = project
    root = root.resolve()
    assert (root / TEMPLATE_FALLBACK[case]["own"]).is_file(), case
    assert (root / "scripts" / "repo_shape.py").is_file(), case
    return root


@pytest.mark.parametrize("case", sorted(TEMPLATE_FALLBACK))
def test_a_user_site_pth_does_not_stand_in_for_a_lost_repo_shape(
        standard, project, holder, tmp_path, user_base, case):
    """The issue's first case: the operator's user site-packages holds a
    `.pth` naming the standard's `scripts/`, and the root has lost its own
    `repo_shape.py`. The row used to say `ok ... passes` for `manifest`, and
    quote `shape-copy-missing` for `pins` and `family`, a finding those gates
    reach only by importing a `repo_shape` the root does not have."""
    root = root_without_its_repo_shape(case, project, holder, tmp_path,
                                       red=False)
    rows = doctor_rows(standard, root, tmp_path,
                       PYTHONUSERBASE=str(user_base))
    assert_the_gates_own_failure(rows[case])


@pytest.mark.parametrize("case", sorted(TEMPLATE_FALLBACK))
def test_a_virtualenvs_pth_does_not_stand_in_for_a_lost_repo_shape(
        standard, project, holder, tmp_path, venv_python, case):
    """The issue's second case, the one `-s` and `-I` leave open: the `.pth`
    is in a virtualenv's own site-packages, and that virtualenv's interpreter
    runs the doctor, so it runs every child too."""
    root = root_without_its_repo_shape(case, project, holder, tmp_path,
                                       red=False)
    rows = doctor_rows(standard, root, tmp_path, python=venv_python)
    assert_the_gates_own_failure(rows[case])


@pytest.mark.parametrize("route", ["user-site", "virtualenv"])
@pytest.mark.parametrize("case", sorted(TEMPLATE_FALLBACK))
def test_a_root_that_keeps_its_own_repo_shape_still_passes(
        standard, project, holder, tmp_path, request, case, route):
    """The other half of the issue's sentence: a validator puts its own
    directory first, so a `.pth` never shadowed a `repo_shape.py` the root
    still has, and with no `site` the gate still imports that one. Its row
    is the pass it always was, under either route."""
    root = root_that_keeps_its_own(case, project, holder, tmp_path)
    if route == "user-site":
        rows = doctor_rows(standard, root, tmp_path, PYTHONUSERBASE=str(
            request.getfixturevalue("user_base")))
    else:
        rows = doctor_rows(standard, root, tmp_path,
                           python=request.getfixturevalue("venv_python"))
    row = rows[case]
    assert row["status"] == "ok", row
    assert row["reason"] == \
        f"the project's own {TEMPLATE_FALLBACK[case]['own']} passes", row
    assert row["detail"]["own_copy"] is True, row
    assert row["detail"]["exit"] == 0, row


#: The three kinds of caller `run_validator` has, by what each passes: a
#: root's own copy and the naming script pass no `pythonpath`; the template
#: copy passes `<shape>/scripts`; the machine's preflight passes none and
#: reaches the network. One rule covers them all.
CALLERS = {
    "own-copy-or-naming": (None, False),
    "template-copy": ("scripts-dir", False),
    "machine-preflight": (None, True),
}


@pytest.mark.parametrize("caller", sorted(CALLERS))
def test_run_validator_starts_every_child_with_no_site(
        standard, tmp_path, monkeypatch, caller):
    """The contract of the flag, asked of the child itself, as
    `test_run_validator_gives_the_child_exactly_the_pythonpath_it_is_given`
    asks it of `PYTHONPATH`: `site` was never imported, no site-packages
    directory is on `sys.path`, and what the child still has is its own
    directory first, the standard library (the probe imports `json`), and the
    `PYTHONPATH` its caller gave it, where it gave one.

    ON EVERY INTERPRETER, because it reads `sys.flags.no_site` rather than
    whether this one happens to have a user site-packages.
    """
    module = doctor_module(standard)
    monkeypatch.delenv("PYTHONPATH", raising=False)
    given, reach_network = CALLERS[caller]
    root = tmp_path / "root"
    root.mkdir()
    probe = root / "probe.py"
    probe.write_text(
        "import json, sys\n"
        "print(json.dumps({'no_site': sys.flags.no_site,\n"
        "                  'path': sys.path}))\n",
        encoding="utf-8")
    pythonpath = None if given is None else tmp_path / given
    code, _quoted, whole = module.run_validator(
        module.Context(root), probe, [], pythonpath,
        reach_network=reach_network)
    assert code == 0, whole
    seen = json.loads(whole)
    assert seen["no_site"] == 1, (caller, seen)
    path = [Path(entry) for entry in seen["path"]]
    assert path[0].resolve() == root.resolve(), (caller, seen)
    assert not [entry for entry in path
                if entry.name in ("site-packages", "dist-packages")], \
        (caller, seen)
    if pythonpath is not None:
        assert pythonpath in path, (caller, seen)
