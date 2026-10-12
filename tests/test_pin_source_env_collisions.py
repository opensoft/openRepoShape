# SPDX-License-Identifier: Apache-2.0
"""Two neutral products must not share one `SHAPE_PIN_SOURCE_<PRODUCT>` (#275).

`pin_source_env_name` turns every character outside `[A-Z0-9_]` into `_`, so
`open-glass`, `open_glass` and `open.glass` are three legal product names, with
three pin files (`contracts/<product lowercased>-pin.yaml`), and ONE variable,
`SHAPE_PIN_SOURCE_OPEN_GLASS`. A project that pinned two of them got whichever
checkout the variable named for BOTH, and a `neutral-pin-source-unreadable`
FINDING (exit 1, a red `validate.yml`) for the one it was not a checkout of;
with no source given the same variable was offered as the way to verify either.

Every existing variable name is kept: an operator may have set one and the docs
name them. What is refused instead is DECLARING a set of products whose
variables collide, in each place that declares or reads pins:

- `scaffold-project.py --pin`, beside #241's file collisions, dry run and real
  run alike, before any process starts;
- the project's own `validate-pins.py`, as the finding
  `neutral-pin-source-collides`, after which neither product reads the
  variable;
- the chain readers in `repo_shape.py`, which never read a variable two links
  of one chain share and never offer it.

`adopt-project.py --pin` is not here: its half arrives with #273's change,
which routes adopt through the one function this file pins.

The tests that call `main()` refuse every process start, which shows the
refusal comes before `git` and `gh`. The validator runs against a copy of the
session's scaffolded project, whose own `validate-pins.py` and `repo_shape.py`
are the copies under test, with a `gh` that exits 97 and records its arguments
where the run would otherwise have reached the forge.
"""

from __future__ import annotations

import os
import stat
import sys
import textwrap
from pathlib import Path

import pytest

from conftest import (
    REPO, SCAFFOLD, WINDOWS_SKIP, clear_ambient_pin_sources, git, run_script,
)
from test_scaffold_pin_and_reuse import product_repo
# Fixtures and constants of #241's file, shared rather than re-made: the
# stand-in `openGlass` with two commits, the module-level `scaffold`, the
# refusal of every process start, and the remote and `gh` world.
from test_scaffold_pin_collisions import (  # noqa: F401
    BASE_ARGS, LEG_REFUSED, ONE_FILE, REFUSED, REMEDIATION, SHAPE_WRITES,
    glass, listing, nothing_was_created, no_process, pin_args, pins_of,
    scaffold, world,
)

sys.path.insert(0, str(REPO / "scripts"))
import repo_shape  # noqa: E402
from repo_shape import NamingPolicy, tree_digest  # noqa: E402

UTF8 = "utf-8"
POLICY_PATH = REPO / "contracts" / "repository-naming.yaml"

#: The two refusals' remediation for the variable, word for word. Alone it
#: stands after `Remediation: nothing was created.`, and beside a file
#: collision it follows #241's remediation after a space.
VARIABLE_REMEDIATION = (
    "`SHAPE_PIN_SOURCE_<PRODUCT>` names the local checkout of a product, and "
    "is its name upper-cased with every character outside `A-Z`, `0-9` and "
    "`_` turned into `_`, so names that differ only in `-`, `.` or `_` share "
    "one. The project's own `validate-pins.py` reports such a pair as "
    "`neutral-pin-source-collides`, and a variable two pins share is read "
    "for neither. Pass one product of each such group, or products whose "
    "names differ by more.")
ALONE = f"Remediation: nothing was created. {VARIABLE_REMEDIATION}"
BESIDE_A_FILE = f"{REMEDIATION} {VARIABLE_REMEDIATION}"


def shared(variable: str) -> str:
    """What the refusal says after it has named the products."""
    return (f", and one variable, `{variable}`, names the local checkout of "
            "each: it cannot say which it holds.")


# --- the one function, and the names it must not change -----------------------

@pytest.mark.parametrize("product, variable", [
    pytest.param("openGlass", "SHAPE_PIN_SOURCE_OPENGLASS", id="camel"),
    pytest.param("open-glass", "SHAPE_PIN_SOURCE_OPEN_GLASS", id="hyphen"),
    pytest.param("open_glass", "SHAPE_PIN_SOURCE_OPEN_GLASS", id="underscore"),
    pytest.param("open.glass", "SHAPE_PIN_SOURCE_OPEN_GLASS", id="dot"),
    pytest.param("OpenGlass", "SHAPE_PIN_SOURCE_OPENGLASS", id="capital"),
    pytest.param("openXdox", "SHAPE_PIN_SOURCE_OPENXDOX", id="openXdox"),
])
def test_every_existing_variable_name_is_kept(product, variable):
    """The refusal is the fix, so no name an operator may have set moves."""
    assert repo_shape.pin_source_env_name(product) == variable


def test_the_variable_two_products_share_is_found_with_all_of_them():
    found = repo_shape.pin_source_env_collisions(
        ["open-glass", "openGlass", "open_glass", "open.glass"])
    assert found == {
        "SHAPE_PIN_SOURCE_OPEN_GLASS": ["open-glass", "open_glass",
                                        "open.glass"]}


def test_each_variable_and_each_product_keeps_the_order_first_given():
    found = repo_shape.pin_source_env_collisions(
        ["x.y", "a-b", "lone", "a_b", "x_y", "x-y"])
    assert list(found) == ["SHAPE_PIN_SOURCE_X_Y", "SHAPE_PIN_SOURCE_A_B"]
    assert found == {"SHAPE_PIN_SOURCE_X_Y": ["x.y", "x_y", "x-y"],
                     "SHAPE_PIN_SOURCE_A_B": ["a-b", "a_b"]}


@pytest.mark.parametrize("products", [
    pytest.param([], id="none"),
    pytest.param(["openGlass"], id="one"),
    pytest.param(["openGlass", "openPane"], id="two-that-differ"),
    pytest.param(["open-glass", "openGlass"], id="hyphen-and-none"),
    pytest.param(["openGlass", "OpenGlass", "OPENGLASS"], id="case-only"),
    pytest.param(["open-glass", "open-glass", "Open-Glass"], id="repeats"),
    pytest.param(["open-glass", None, "", 7, ["open_glass"]],
                 id="not-names-are-left-out"),
])
def test_products_that_do_not_share_a_variable_are_no_collision(products):
    """The same product declared twice, in any case, is ONE product: whether
    that is wrong is #241's `scaffold-pin-collides` and not this function's.
    An entry that is not a name is not one for this either."""
    assert repo_shape.pin_source_env_collisions(products) == {}
    assert repo_shape.pin_source_env_shared(products) == set()


def test_what_is_shared_is_every_product_a_variable_cannot_tell_apart():
    assert repo_shape.pin_source_env_shared(
        ["open-glass", "openGlass", "Open_Glass", "openPane"]
    ) == {"open-glass", "open_glass"}


def test_it_reads_a_generator_once():
    """`link_pins_from_trees` and the scaffold hand it generators."""
    products = (p for p in ("a-b", "a_b"))
    assert repo_shape.pin_source_env_collisions(products) == {
        "SHAPE_PIN_SOURCE_A_B": ["a-b", "a_b"]}


# --- scaffold-project.py --pin: refused, dry and real, before any process ----

#: `(the --pin values, what the refusal says, its remediation)`, `{A}` and
#: `{B}` being two commits of the `--pin-source` clone.
REFUSED_CASES = [
    pytest.param(
        ["open-glass@{A}", "open_glass@{B}"],
        "--pin 'open-glass@{A}' and --pin 'open_glass@{B}' name the products "
        "`open-glass` and `open_glass`" + shared("SHAPE_PIN_SOURCE_OPEN_GLASS"),
        ALONE, id="hyphen-underscore"),
    pytest.param(
        ["open.glass@{A}", "open-glass@{B}"],
        "--pin 'open.glass@{A}' and --pin 'open-glass@{B}' name the products "
        "`open.glass` and `open-glass`" + shared("SHAPE_PIN_SOURCE_OPEN_GLASS"),
        ALONE, id="dot-hyphen"),
    pytest.param(
        ["open-glass@{A}", "openGlass@{A}", "open.glass@{B}", "open_glass@{A}"],
        "--pin 'open-glass@{A}' and --pin 'open.glass@{B}' and --pin "
        "'open_glass@{A}' name the products `open-glass` and `open.glass` and "
        "`open_glass`" + shared("SHAPE_PIN_SOURCE_OPEN_GLASS"),
        ALONE, id="three-with-a-bystander"),
    pytest.param(
        ["opensoft/open-glass@{A}", "open_glass@{B}"],
        "--pin 'opensoft/open-glass@{A}' and --pin 'open_glass@{B}' name the "
        "products `open-glass` and `open_glass`"
        + shared("SHAPE_PIN_SOURCE_OPEN_GLASS"),
        ALONE, id="owner-qualified-as-typed"),
    pytest.param(
        ["Open-Glass@{A}", "open_glass@{B}"],
        "--pin 'Open-Glass@{A}' and --pin 'open_glass@{B}' name the products "
        "`Open-Glass` and `open_glass`" + shared("SHAPE_PIN_SOURCE_OPEN_GLASS"),
        ALONE, id="capitals"),
    pytest.param(
        ["a-b@{A}", "x.y@{A}", "a_b@{B}", "x_y@{B}"],
        "--pin 'a-b@{A}' and --pin 'a_b@{B}' name the products `a-b` and "
        "`a_b`" + shared("SHAPE_PIN_SOURCE_A_B")
        + " --pin 'x.y@{A}' and --pin 'x_y@{B}' name the products `x.y` and "
        "`x_y`" + shared("SHAPE_PIN_SOURCE_X_Y"),
        ALONE, id="two-groups-in-the-order-typed"),
    pytest.param(
        ["spec@{A}", "open-glass@{A}", "open_glass@{B}"],
        "--pin 'spec@{A}' writes the pin of the product `spec` at "
        "`contracts/spec-pin.yaml`, " + SHAPE_WRITES
        + " --pin 'open-glass@{A}' and --pin 'open_glass@{B}' name the "
        "products `open-glass` and `open_glass`"
        + shared("SHAPE_PIN_SOURCE_OPEN_GLASS"),
        BESIDE_A_FILE, id="and-a-file-the-shape-writes"),
    pytest.param(
        ["open-glass@{A}", "Open-Glass@{B}", "open_glass@{A}"],
        "--pin 'open-glass@{A}' and --pin 'Open-Glass@{B}' write the pins of "
        "the products `open-glass` and `Open-Glass` at one file, "
        "`contracts/open-glass-pin.yaml`, " + ONE_FILE
        + " --pin 'open-glass@{A}' and --pin 'Open-Glass@{B}' and --pin "
        "'open_glass@{A}' name the products `open-glass` and `open_glass`"
        + shared("SHAPE_PIN_SOURCE_OPEN_GLASS"),
        BESIDE_A_FILE, id="and-one-product-typed-twice"),
]


def refusal(scaffold, capsys, said: str, remediation: str, *args: str) -> str:
    """`main()` with `args`: the pin refusal it printed, checked whole."""
    code = scaffold.main([*BASE_ARGS, *args])
    out, err = capsys.readouterr()
    assert code == 2, out + err
    assert out == "", "the refusal comes before the plan is printed"
    assert err == f"{REFUSED}: {said}\n{remediation}\n", err
    return err


@pytest.mark.parametrize("dry", [pytest.param(True, id="dry-run"),
                                 pytest.param(False, id="real-run")])
@pytest.mark.parametrize("values, said, remediation", REFUSED_CASES)
def test_pins_sharing_a_variable_are_refused_before_any_process(
        scaffold, glass, no_process, capsys, tmp_path, values, said,
        remediation, dry):
    """The sentence names each argument as typed, the products and the
    variable. A real run that got past it would read each pin's digest from
    the `--pin-source` with `git`, which `no_process` refuses; and the remote
    and work directories it was given were never made."""
    remotes, work = tmp_path / "remotes", tmp_path / "work"
    _, first, second = glass
    refusal(scaffold, capsys, said.format(A=first, B=second), remediation,
            *pin_args(glass, values), "--local-remote-dir", str(remotes),
            "--work-dir", str(work), *(("--dry-run",) if dry else ()))
    assert not remotes.exists() and not work.exists()


@pytest.mark.parametrize("values, said, remediation", REFUSED_CASES)
def test_a_dry_run_refuses_exactly_as_the_real_run(glass, world, values, said,
                                                   remediation):
    """On main through c7c02fa the dry run said yes and the real run made
    three repositories holding two pins one variable named. Now both say the
    same no, word for word, and nothing exists afterwards."""
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
                           f"{remediation}\n")
    nothing_was_created(world)


def test_the_variable_refusal_comes_before_the_leg_path_refusal(
        scaffold, glass, no_process, capsys, monkeypatch):
    """Where #241's file refusal runs, in `_refuse_colliding_pins`, and so
    ahead of `_refuse_colliding_leg_paths`: a leg path over one of the two
    pins' files is the pin refusal, and the leg-path question is never asked.
    The control is the same leg path with one pin: the leg-path refusal."""
    asked = []
    original = scaffold._refuse_colliding_leg_paths

    def spy(*args, **kwargs):
        asked.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(scaffold, "_refuse_colliding_leg_paths", spy)
    legs = ("--code-path", "contracts/open-glass-pin.yaml")
    _, first, second = glass
    err = refusal(
        scaffold, capsys,
        f"--pin 'open-glass@{first}' and --pin 'open_glass@{second}' name "
        "the products `open-glass` and `open_glass`"
        + shared("SHAPE_PIN_SOURCE_OPEN_GLASS"), ALONE, *legs,
        *pin_args(glass, ["open-glass@{A}", "open_glass@{B}"]), "--dry-run")
    assert LEG_REFUSED not in err and asked == []
    code = scaffold.main([*BASE_ARGS, *legs, "--dry-run",
                          *pin_args(glass, ["open-glass@{A}"])])
    assert code == 2
    assert capsys.readouterr().err.startswith(f"{LEG_REFUSED}: ")
    assert len(asked) == 1


@WINDOWS_SKIP  # the stub `gh` is a `#!` script; Windows executes none
def test_no_gh_command_runs_before_the_variable_refusal(world):
    """Pointed at GitHub, with no `--pin-source`, so `gh api` would read each
    pin's digest, the refusal comes first and `gh` is never run. The control
    is the same run with one of the two pins: it reaches `gh`."""
    commit = "1" * 40
    common = (*BASE_ARGS, "--pin", f"open-glass@{commit}",
              "--work-dir", str(world["work"]))
    refused = run_script(SCAFFOLD, *common, "--pin", f"open_glass@{commit}",
                         env=world["env"])
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert refused.stderr.startswith(f"{REFUSED}: --pin 'open-glass@{commit}' "
                                     f"and --pin 'open_glass@{commit}' ")
    nothing_was_created(world)

    control = run_script(SCAFFOLD, *common, env=world["env"])
    assert control.returncode == 2, control.stdout + control.stderr
    assert "pin-unreadable" in control.stderr
    assert world["log"].read_text(encoding=UTF8).startswith(
        "api repos/opensoft/open-glass")


@pytest.mark.parametrize("values, files", [
    pytest.param(["open_glass@{A}"], ["contracts/open_glass-pin.yaml"],
                 id="one-punctuated-pin"),
    pytest.param(["open-glass@{A}", "openGlass@{B}"],
                 ["contracts/open-glass-pin.yaml",
                  "contracts/openglass-pin.yaml"], id="variables-differ"),
    pytest.param(["open-glass@{A}", "open-glass-2@{B}", "open.pane@{A}"],
                 ["contracts/open-glass-pin.yaml",
                  "contracts/open-glass-2-pin.yaml",
                  "contracts/open.pane-pin.yaml"], id="three-that-differ"),
])
def test_pins_whose_variables_differ_still_scaffold(glass, world, values,
                                                    files):
    """Nothing the refusal does touches a set whose variables differ: the
    plan names each pin's file, and the pushed root holds each pin at its own
    file with its own commit."""
    args = (*BASE_ARGS, *pin_args(glass, values),
            "--local-remote-dir", str(world["remotes"]),
            "--work-dir", str(world["work"]))
    dry = run_script(SCAFFOLD, *args, "--dry-run", env=world["env"])
    assert dry.returncode == 0, dry.stdout + dry.stderr
    planned = [line for line in dry.stdout.splitlines()
               if line.startswith("pin ")]
    assert [line.split(" -> ")[1].split(" (")[0] for line in planned] == files
    result = run_script(SCAFFOLD, *args, env=world["env"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert REFUSED not in result.stderr
    root = world["remotes"] / "Northwind.git"
    for path, value in zip(files, pins_of(glass, values)):
        pin = git("show", f"main:{path}", cwd=root).stdout
        assert f'commit: "{value.rsplit("@", 1)[1]}"' in pin, pin
    assert not world["log"].exists()


# --- validate-pins.py: a finding naming each product and the variable ---------

PIN_FILE = textwrap.dedent("""\
    schema_version: 1
    kind: pinned_contract_manifest
    pin_role: neutral-product
    product: {name}
    source_repository: opensoft/{name}
    materialization: referenced
    commit: "{commit}"
    revision_kind: commit
    digest_algorithm: sha256
    digest_definition: sorted-ls-tree-r-v1
    digests:
      tree_sha256: "{digest}"
    digest_source: stand-in
    declared_in: project.yaml
    verify_pin: scripts/validate-manifest.py
    """)


def write(path: Path, text: str) -> None:
    """LF on every platform, as the shape's own writers do."""
    with open(path, "w", encoding=UTF8, newline="\n") as handle:
        handle.write(text)


def declare_pins(project: Path, base: Path, names) -> dict[str, Path]:
    """Declare a pin on each of `names` in the scaffolded `project`, by hand:
    a stand-in repository per name under `base`, a pin file written from it
    and a `neutral_product_pins:` entry, as a hand-edited manifest, or one an
    older scaffold wrote, holds them. `{name: the stand-in}`; `base` is no
    sibling of `project`, so rule 3 of the lookup finds none of them."""
    stand_ins = {}
    for name in names:
        path, commit = product_repo(base, name)
        stand_ins[name] = path
        write(project / "contracts" / f"{name.lower()}-pin.yaml",
              PIN_FILE.format(name=name, commit=commit,
                              digest=tree_digest(path, commit)))
    manifest = project / "project.yaml"
    text = manifest.read_text(encoding=UTF8)
    assert "neutral_product_pins: []" in text, "fixture drift"
    write(manifest, text.replace(
        "neutral_product_pins: []",
        "neutral_product_pins:\n" + "\n".join(f"  - {name}" for name in names),
        1))
    return stand_ins


def validate(project: Path, *args: str, env=None):
    return run_script(project / "scripts" / "validate-pins.py", *args,
                      cwd=project, env=env)


@pytest.fixture
def gh_shim(tmp_path):
    """A `gh` that records its arguments and fails, first on PATH: the run
    that reaches the forge says so in `log`, and a project whose pins were
    all answered locally leaves it absent. Windows executes no `#!` script,
    so the tests that need it are skipped there."""
    bin_dir, log = tmp_path / "shim", tmp_path / "gh.log"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    write(gh, textwrap.dedent("""\
        #!/usr/bin/env python3
        import os, sys
        with open(os.environ["GH_STUB_LOG"], "a", encoding="utf-8") as log:
            log.write(" ".join(sys.argv[1:]) + "\\n")
        print("gh shim: refused", file=sys.stderr)
        sys.exit(97)
        """))
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return {"log": log, "env": {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "GH_STUB_LOG": str(log)}}


COLLIDES = "FINDING neutral-pin-source-collides: "


def test_two_pins_sharing_a_variable_are_one_finding_naming_both(
        project, tmp_path):
    """Every source named by product answers, so what is reported is the
    declaration and nothing else: one finding, both products, the variable."""
    stand_ins = declare_pins(project, tmp_path / "products",
                             ["open-glass", "open_glass"])
    result = validate(project, "--pin-source",
                      f"open-glass={stand_ins['open-glass']}",
                      "--pin-source", f"open_glass={stand_ins['open_glass']}")
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stderr.count("FINDING") == 1, result.stderr
    assert (f"{COLLIDES}project.yaml neutral_product_pins declares "
            "'open-glass' and 'open_glass', and one variable, "
            "SHAPE_PIN_SOURCE_OPEN_GLASS, names the local checkout of each: "
            "it cannot say which it holds, so it is read for none of them."
            ) in result.stderr
    assert "Remediation: `SHAPE_PIN_SOURCE_<PRODUCT>`" in result.stderr
    assert "1 finding(s)" in result.stderr
    for name in ("open-glass", "open_glass"):
        assert f"  ok  {name}: pin commit " in result.stdout
        assert f"digest recomputes (--pin-source {name}=...)" in result.stdout


def test_three_products_one_variable_are_one_finding_naming_all_three(
        project, tmp_path):
    names = ["open-glass", "open.glass", "open_glass"]
    stand_ins = declare_pins(project, tmp_path / "products",
                             [*names, "openGlass"])
    result = validate(project, *(arg for name in names
                                 for arg in ("--pin-source",
                                             f"{name}={stand_ins[name]}")),
                      "--pin-source", f"openGlass={stand_ins['openGlass']}")
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stderr.count("FINDING") == 1, result.stderr
    assert (f"{COLLIDES}project.yaml neutral_product_pins declares "
            "'open-glass' and 'open.glass' and 'open_glass', and one "
            "variable, SHAPE_PIN_SOURCE_OPEN_GLASS,") in result.stderr
    assert "openGlass'" not in result.stderr.split("Remediation")[0]


@WINDOWS_SKIP  # the stub `gh` is a `#!` script; Windows executes none
@pytest.mark.parametrize("named", ["open-glass", "open_glass"])
def test_a_shared_variable_answers_for_neither_pin(project, tmp_path, gh_shim,
                                                   named):
    """THE ISSUE'S PROBE. The variable names one product's checkout and, on
    main through c7c02fa, answered for both: the other was reported
    `neutral-pin-source-unreadable`, a finding about the project made by a
    checkout of another. Now it answers for neither, so both fall through to
    `gh` (stubbed, and asked about each) and the only finding is the
    declaration's; the hint no longer offers the variable."""
    stand_ins = declare_pins(project, tmp_path / "products",
                             ["open-glass", "open_glass"])
    env = {**gh_shim["env"],
           "SHAPE_PIN_SOURCE_OPEN_GLASS": str(stand_ins[named])}
    result = validate(project, env=env)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "neutral-pin-source-unreadable" not in result.stderr
    assert result.stderr.count("FINDING") == 1, result.stderr
    assert COLLIDES in result.stderr
    calls = gh_shim["log"].read_text(encoding=UTF8).splitlines()
    assert [call.split("/git/trees")[0] for call in calls] == [
        "api repos/opensoft/open-glass", "api repos/opensoft/open_glass"]
    skips = [line for line in result.stdout.splitlines()
             if line.startswith("  skip ")]
    assert len(skips) == 2
    for line in skips:
        assert "SHAPE_PIN_SOURCE" not in line
        assert "A --pin-source or a checkout at ../open" in line


@WINDOWS_SKIP  # the stub `gh` is a `#!` script; Windows executes none
def test_a_pin_no_other_shares_a_variable_with_is_offered_it(project, tmp_path,
                                                             gh_shim):
    """The control: one punctuated pin keeps its variable in the hint, as it
    always did, and the run is green with no source (a skip is no finding)."""
    declare_pins(project, tmp_path / "products", ["open-glass"])
    result = validate(project, env=gh_shim["env"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FINDING" not in result.stderr
    skip = next(line for line in result.stdout.splitlines()
                if line.startswith("  skip open-glass"))
    assert ("A --pin-source, SHAPE_PIN_SOURCE_OPEN_GLASS, or a checkout at "
            "../open-glass beside this assembly root") in skip


def test_pins_whose_variables_differ_each_read_their_own(project, tmp_path):
    """The names are kept: `open-glass` is still `SHAPE_PIN_SOURCE_OPEN_GLASS`
    and `openGlass` is still `SHAPE_PIN_SOURCE_OPENGLASS`, two variables for
    two pins, and each answers for its own product."""
    stand_ins = declare_pins(project, tmp_path / "products",
                             ["open-glass", "openGlass"])
    result = validate(project, env={
        "SHAPE_PIN_SOURCE_OPEN_GLASS": str(stand_ins["open-glass"]),
        "SHAPE_PIN_SOURCE_OPENGLASS": str(stand_ins["openGlass"])})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FINDING" not in result.stderr
    assert ("open-glass: pin commit" in result.stdout
            and "digest recomputes ($SHAPE_PIN_SOURCE_OPEN_GLASS)"
            in result.stdout)
    assert "digest recomputes ($SHAPE_PIN_SOURCE_OPENGLASS)" in result.stdout
    assert "pins ok" in result.stdout


def test_a_product_declared_twice_is_not_a_shared_variable(project, tmp_path):
    """`open-glass` and `Open-Glass` are one pin file and so one product, and
    one variable rightly: no collision, and the variable answers."""
    stand_ins = declare_pins(project, tmp_path / "products", ["open-glass"])
    manifest = project / "project.yaml"
    write(manifest, manifest.read_text(encoding=UTF8).replace(
        "  - open-glass", "  - open-glass\n  - Open-Glass", 1))
    result = validate(project, env={
        "SHAPE_PIN_SOURCE_OPEN_GLASS": str(stand_ins["open-glass"])})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "neutral-pin-source-collides" not in result.stderr
    assert result.stdout.count("digest recomputes ($SHAPE_PIN_SOURCE_OPEN_GLASS)"
                               ) == 2


# --- the chain readers: a variable two links share is read for neither --------

def tree(path: Path, *pins: str) -> Path:
    """A stand-in for a link's checkout: a manifest and its declaration."""
    path.mkdir(parents=True, exist_ok=True)
    write(path / "project.yaml",
          "schema_version: 1\nkind: project-manifest\nneutral_product_pins:\n"
          + "".join(f"  - {pin}\n" for pin in pins))
    return path


def test_a_variable_two_links_share_is_read_for_neither(tmp_path, monkeypatch):
    """`open-x` and `open_x` are two links of one hand-written chain and one
    variable. On main through c7c02fa the tree it named answered for both, so
    `open_x` was read as declaring what `open-x`'s tree declares."""
    clear_ambient_pin_sources(monkeypatch)
    only = tree(tmp_path / "open-x", "openDox")
    monkeypatch.setenv("SHAPE_PIN_SOURCE_OPEN_X", str(only))
    assert repo_shape.link_pins_from_trees(
        ("open-x", "open_x", "openDox"), root=None) == {}


def test_a_link_no_other_shares_a_variable_with_still_reads_it(tmp_path,
                                                               monkeypatch):
    """The control: the same variable answers for `open-x` in a chain with no
    other link it names, which is what every chain read before."""
    clear_ambient_pin_sources(monkeypatch)
    only = tree(tmp_path / "open-x", "openDox")
    monkeypatch.setenv("SHAPE_PIN_SOURCE_OPEN_X", str(only))
    assert repo_shape.link_pins_from_trees(
        ("open-x", "openY", "openDox"), root=None) == {"open-x": {"openDox"}}


def test_links_sharing_a_variable_are_still_read_by_name(tmp_path,
                                                         monkeypatch):
    """`--link-source <link>=<path>` is not the variable, and answers each."""
    clear_ambient_pin_sources(monkeypatch)
    first = tree(tmp_path / "one", "open_x")
    second = tree(tmp_path / "two", "openDox")
    assert repo_shape.link_pins_from_trees(
        ("open-x", "open_x", "openDox"), root=None,
        keyed_sources={"open-x": first, "open_x": second}
    ) == {"open-x": {"open_x"}, "open_x": {"openDox"}}


def test_a_shared_variable_is_not_offered_as_the_way_to_read_a_link():
    """The `declared-unverified` hint names the variable for a link that has
    it to itself, as before, and names `--link-source` alone for two links
    that share one."""
    policy = NamingPolicy.load(POLICY_PATH)
    apart = policy.resolve_referent(
        "MedxGlass", {"openXglass"}, ["openXglass", "openGlass"], {})
    assert list(apart.warnings) == [
        "declared-unverified: openXglass declaring a pin on openGlass is a "
        "fact in openXglass's own tree, which is not reachable here (a "
        "sibling checkout, SHAPE_PIN_SOURCE_OPENXGLASS, or --link-source "
        "openXglass=<path> would let it be read). The recorded chain still "
        "classifies."]
    together = policy.resolve_referent(
        "MedxGlass", {"open-x"}, ["open-x", "open_x", "openGlass"], {})
    assert [w.split(" (")[1].split(" would")[0]
            for w in together.warnings] == [
        "a sibling checkout or --link-source open-x=<path>",
        "a sibling checkout or --link-source open_x=<path>"]
    assert "SHAPE_PIN_SOURCE" not in " ".join(together.warnings)
