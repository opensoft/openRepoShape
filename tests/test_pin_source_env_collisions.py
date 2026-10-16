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
name them. What is done instead, in each place that declares or reads pins:

- `scaffold-project.py --pin` REFUSES a set of products whose variables
  collide, beside #241's file collisions, dry run and real run alike, before
  any process starts: no new project is made with a variable it cannot use;
- the project's own `validate-pins.py` NOTES a pair a project already declares
  (`neutral-pin-source-collides`) and never fails it, after which neither
  product reads the variable and each is verified from its own source. It was
  a finding in the first round, and a project declaring such a pair could not
  take `update-shape.py apply` (`update-validators-red`) until a person dropped
  a true declaration; the second round made it a note, and
  `test_a_project_declaring_a_colliding_pair_takes_a_shape_update` holds that;
- the chain readers in `repo_shape.py` never read a variable two links of one
  chain share and never offer it.

Two declarations are one product when they are one PIN FILE (`pin_product_key`,
`lower()`), and not when `casefold()` says so: `openß` and `openss` share
`SHAPE_PIN_SOURCE_OPENSS` and have two files.

`adopt-project.py --pin` is not here: its half arrives with #273's change,
which routes adopt through the one function this file pins.

The tests that call `main()` refuse every process start, which shows the
refusal comes before `git` and `gh`. The validator runs against a copy of the
session's scaffolded project, whose own `validate-pins.py` and `repo_shape.py`
are the copies under test, with a `gh` that exits 97 and records its arguments
where the run would otherwise have reached the forge.
"""

from __future__ import annotations

import itertools
import json
import os
import shutil
import stat
import subprocess
import sys
import textwrap
import types
from pathlib import Path

import pytest

from conftest import (
    REPO, SCAFFOLD, WINDOWS_SKIP, clear_ambient_pin_sources, git, run_script,
)
from test_scaffold_pin_and_reuse import product_repo
from test_update_shape import (
    PROJECT, commit_upstream_changes, scaffold_upstream_and_project, verdicts,
)
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
from repo_shape import NamingPolicy, Refusal, tree_digest  # noqa: E402
from shape_materialize import neutral_pin_path  # noqa: E402

UTF8 = "utf-8"
POLICY_PATH = REPO / "contracts" / "repository-naming.yaml"
VALIDATE_PINS = (REPO / "templates" / "assembly-root" / "scripts"
                 / "validate-pins.py")

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


# --- two declarations are one product when they are one PIN FILE (#275, N2) ---

#: Pairs of names that share a variable and have TWO pin files, though
#: `casefold()` makes one of each. Hand-written `project.yaml` cases only:
#: scaffold's `--pin` and adopt's `pins:` take ASCII, as a GitHub repository
#: name is.
FOLDED_APART = [
    pytest.param("open\u00df", "openss", "SHAPE_PIN_SOURCE_OPENSS",
                 id="sharp-s"),
    pytest.param("open\u017f", "opens", "SHAPE_PIN_SOURCE_OPENS",
                 id="long-s"),
    pytest.param("open\ufb01", "openfi", "SHAPE_PIN_SOURCE_OPENFI",
                 id="fi-ligature"),
    pytest.param("open\u03c2", "open\u03c3", "SHAPE_PIN_SOURCE_OPEN_",
                 id="final-sigma"),
]


@pytest.mark.parametrize("first, second, variable", FOLDED_APART)
def test_names_one_variable_cannot_tell_apart_are_found_beyond_ascii(
        first, second, variable):
    """The four pairs the first round missed. Each shares a variable and has
    two pin files, so one checkout answered for both and the pin it was not a
    checkout of was reported against the project; `casefold()`, which was the
    rule, made each pair one product."""
    assert first.casefold() == second.casefold(), "the reason they were missed"
    assert neutral_pin_path(first) != neutral_pin_path(second)
    assert repo_shape.pin_source_env_name(first) == variable
    assert repo_shape.pin_source_env_name(second) == variable
    assert repo_shape.pin_source_env_collisions([first, second]) == {
        variable: [first, second]}
    assert repo_shape.pin_source_env_collisions([second, first]) == {
        variable: [second, first]}
    assert repo_shape.pin_source_env_shared([first, second]) == {first, second}


#: A pool of names covering every way two of them can relate: the same name in
#: another case, punctuation that folds to `_`, a non-ASCII letter whose
#: upper-case is ASCII (`\u0131` is `I`, `\u017f` is `S`), a character that
#: upper-cases to two (`\u00df`, `\ufb01`), one that upper-cases to a letter
#: that is no ASCII (`\u03c2`, `\u03c3`) and one that is only `_` once folded.
NAME_POOL = [
    "openGlass", "OpenGlass", "OPENGLASS", "open-glass", "Open-Glass",
    "open_glass", "open.glass", "open-x", "open_x", "open.x", "openPane",
    "open\u0131", "openi", "openI", "open\u00e9", "open-", "open_",
    "open\uff47", "open\u00df", "openss", "openSS", "open\u017f", "opens",
    "openS", "open\ufb01", "openfi", "openFI", "open\u03c2", "open\u03c3",
    "open\u03a3", "open\u0130",
]


def test_every_pair_sharing_a_variable_with_two_pin_files_is_found():
    """Over every pair of the pool: found exactly when the variable is shared
    AND the pin files are two. The oracle is `neutral_pin_path`, which names
    the pin file, and `pin_source_env_name`, which names the variable; no
    casefold, no case rule of this test's own."""
    for first, second in itertools.combinations(NAME_POOL, 2):
        shares = (repo_shape.pin_source_env_name(first)
                  == repo_shape.pin_source_env_name(second))
        two_files = neutral_pin_path(first) != neutral_pin_path(second)
        found = repo_shape.pin_source_env_collisions([first, second])
        assert bool(found) is (shares and two_files), (first, second, found)
        if found:
            (variable, group), = found.items()
            assert group == [first, second]
            assert variable == repo_shape.pin_source_env_name(first)
            assert repo_shape.pin_source_env_shared([first, second]) == {
                repo_shape.pin_product_key(first),
                repo_shape.pin_product_key(second)}


@pytest.mark.parametrize("name", NAME_POOL)
def test_no_single_product_is_ever_a_collision(name):
    """Nor is one product declared twice, in any spelling of its pin file."""
    assert repo_shape.pin_source_env_collisions([name]) == {}
    assert repo_shape.pin_source_env_collisions([name, name]) == {}
    assert repo_shape.pin_source_env_shared([name]) == set()
    assert repo_shape.pin_source_env_collisions([name, name.lower()]) == {}


@pytest.mark.parametrize("name", NAME_POOL)
def test_the_key_is_the_name_the_pin_file_carries(name):
    """`pin_product_key` is not a second rule: it is the stem of the file
    `shape_materialize.neutral_pin_path` writes, and `validate-pins.py` reads
    the same file under `contracts/<product lowercased>-pin.yaml`."""
    assert neutral_pin_path(name) == (
        f"contracts/{repo_shape.pin_product_key(name)}-pin.yaml")


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
    # Its first `gh` call asks the forge what the id names (#651).
    assert world["log"].read_text(encoding=UTF8).splitlines()[0].endswith(
        f"-f owner=opensoft -f name=open-glass -f oid={commit}")


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


# --- validate-pins.py: a note naming each product and the variable -------------

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


#: The note's line, and what it says after naming the products and the
#: variable, word for word. It is a NOTE (#275, fix round 1, S1): the lines the
#: validator prints that fail nothing are `ok`, `skip` and `note`.
NOTE = "  note neutral-pin-source-collides: "


def collides(names: str, variable: str) -> str:
    """The whole note, after its code, for the products `names` quotes."""
    return (f"project.yaml neutral_product_pins declares {names}, and one "
            f"variable, {variable}, names the local checkout of each: it "
            "cannot say which it holds, so it is read for none of them. Each "
            "pin still verifies from the keyed `--pin-source "
            "<product>=<path>` or from a checkout beside this assembly "
            "root; a bare `--pin-source` answers for every pin that has no "
            "more specific source. Which declaration stays is the human's "
            "decision, and nothing here fails on it.")


def collision_notes(result) -> list[str]:
    return [line for line in result.stdout.splitlines()
            if line.startswith(NOTE)]


def test_two_pins_sharing_a_variable_are_one_note_naming_both(
        project, tmp_path):
    """Every source named by product answers, so what is said about the
    declaration is a note and nothing else: one line, both products, the
    variable, and a run that passes."""
    stand_ins = declare_pins(project, tmp_path / "products",
                             ["open-glass", "open_glass"])
    result = validate(project, "--pin-source",
                      f"open-glass={stand_ins['open-glass']}",
                      "--pin-source", f"open_glass={stand_ins['open_glass']}")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FINDING" not in result.stderr and "finding(s)" not in result.stderr
    assert collision_notes(result) == [
        NOTE + collides("'open-glass' and 'open_glass'",
                        "SHAPE_PIN_SOURCE_OPEN_GLASS")]
    assert result.stdout.rstrip().endswith("pins ok")
    for name in ("open-glass", "open_glass"):
        assert f"  ok  {name}: pin commit " in result.stdout
        assert f"digest recomputes (--pin-source {name}=...)" in result.stdout


def test_three_products_one_variable_are_one_note_naming_all_three(
        project, tmp_path):
    names = ["open-glass", "open.glass", "open_glass"]
    stand_ins = declare_pins(project, tmp_path / "products",
                             [*names, "openGlass"])
    result = validate(project, *(arg for name in names
                                 for arg in ("--pin-source",
                                             f"{name}={stand_ins[name]}")),
                      "--pin-source", f"openGlass={stand_ins['openGlass']}")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FINDING" not in result.stderr
    assert collision_notes(result) == [
        NOTE + collides("'open-glass' and 'open.glass' and 'open_glass'",
                        "SHAPE_PIN_SOURCE_OPEN_GLASS")]
    assert "openGlass'" not in collision_notes(result)[0]
    assert result.stdout.count("digest recomputes (--pin-source") == 4


def test_a_quiet_run_prints_no_note_and_still_passes(project, tmp_path):
    """`--quiet` prints the notes of no kind, as it always did: nothing else
    is said about a pair that nothing fails on."""
    stand_ins = declare_pins(project, tmp_path / "products",
                             ["open-glass", "open_glass"])
    result = validate(project, "--quiet", "--pin-source",
                      f"open-glass={stand_ins['open-glass']}",
                      "--pin-source", f"open_glass={stand_ins['open_glass']}")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "pins ok" and result.stderr == ""


@WINDOWS_SKIP  # the stub `gh` is a `#!` script; Windows executes none
@pytest.mark.parametrize("named", ["open-glass", "open_glass"])
def test_a_shared_variable_answers_for_neither_pin(project, tmp_path, gh_shim,
                                                   named):
    """THE ISSUE'S PROBE. The variable names one product's checkout and, on
    main through c7c02fa, answered for both: the other was reported
    `neutral-pin-source-unreadable`, a finding about the project made by a
    checkout of another. Now it answers for neither, so both fall through to
    `gh` (stubbed, and asked about each); the declaration is a note, so the
    run passes with the two skips; and the hint offers the keyed
    `--pin-source <product>=<path>`, the one source that says which pin it is
    for, and never the variable or the bare form."""
    stand_ins = declare_pins(project, tmp_path / "products",
                             ["open-glass", "open_glass"])
    env = {**gh_shim["env"],
           "SHAPE_PIN_SOURCE_OPEN_GLASS": str(stand_ins[named])}
    result = validate(project, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "neutral-pin-source-unreadable" not in result.stderr
    assert "FINDING" not in result.stderr
    assert len(collision_notes(result)) == 1
    calls = gh_shim["log"].read_text(encoding=UTF8).splitlines()
    assert [call.split("/git/trees")[0] for call in calls] == [
        "api repos/opensoft/open-glass", "api repos/opensoft/open_glass"]
    skips = [line for line in result.stdout.splitlines()
             if line.startswith("  skip ")]
    assert len(skips) == 2
    for name, line in zip(("open-glass", "open_glass"), skips):
        assert "SHAPE_PIN_SOURCE" not in line
        assert f"A --pin-source {name}=<path> or a checkout at ../{name} " \
            "beside this assembly root would verify it offline." in line


@pytest.mark.parametrize("named", ["open-glass", "open_glass"])
def test_a_shared_variable_answers_for_neither_pin_with_no_gh(project, named):
    """THE SAME GUARD, WITH NO `gh` AT ALL, so it runs on Windows too (the
    test above needs a `#!` stub). Each pin has a checkout BESIDE the project,
    `../open-glass` and `../open_glass`, and the variable names ONE of them.
    On ab623dd the variable answered for both pins, so the other was
    `neutral-pin-source-unreadable` (a commit its checkout does not hold), exit
    1. Now neither reads it: each pin is recomputed from its own sibling, the
    variable is named by no line, and only the note is said. No pin reaches
    `gh`, which the session's guard would fail this test for."""
    stand_ins = declare_pins(project, project.parent,
                             ["open-glass", "open_glass"])
    result = validate(project, env={
        "SHAPE_PIN_SOURCE_OPEN_GLASS": str(stand_ins[named])})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "neutral-pin-source-unreadable" not in result.stderr
    assert "FINDING" not in result.stderr
    assert len(collision_notes(result)) == 1
    for name in ("open-glass", "open_glass"):
        line = next(line for line in result.stdout.splitlines()
                    if line.startswith(f"  ok  {name}: pin commit "))
        assert "digest recomputes (sibling checkout (" in line, line
    assert "($SHAPE_PIN_SOURCE" not in result.stdout


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


# --- the skip hint, with no `gh` and no filesystem: runs on every OS ---------

@pytest.fixture(scope="module")
def validate_pins():
    """The template's `validate-pins.py` as a module, so its functions are
    called in-process. A hyphenated name is not importable, and
    `importlib.util.spec_from_file_location` (which `tests/test_update_shape.py`
    uses for `update-shape.py`) would write `__pycache__` BESIDE the template,
    inside `templates/assembly-root`, where `tests/test_scaffold_leg_path_
    collisions.py` reads every file under that directory as text and dies on
    the bytecode. So the source is compiled and run into a module here, and
    nothing is written. `repo_shape` resolves to the module cached above, so
    `Refusal` is the one the file raises."""
    module = types.ModuleType("validate_pins_under_test")
    module.__file__ = str(VALIDATE_PINS)
    exec(compile(VALIDATE_PINS.read_bytes(), str(VALIDATE_PINS), "exec",
                 dont_inherit=True), module.__dict__)
    return module


def skip_hint(validate_pins, monkeypatch, tmp_path, products, product):
    """The `skip` line `product` gets when nothing answers for it: no source,
    no sibling, and a `gh` that is not there (`tree_digest_from_gh` refuses as
    it does when `gh` is not on PATH, which is no process at all)."""
    clear_ambient_pin_sources(monkeypatch)

    def no_gh(repository, commit):
        raise Refusal("gh-not-found", "the `gh` CLI is not on PATH")

    monkeypatch.setattr(validate_pins, "tree_digest_from_gh", no_gh)
    report = validate_pins.Report()
    answered = validate_pins._recompute_neutral_pin_digest(
        tmp_path / PROJECT, product, f"opensoft/{product}", "1" * 40,
        f"contracts/{product}-pin.yaml",
        validate_pins.PinSources([], products), report,
        frozenset(repo_shape.pin_source_env_shared(products)))
    assert answered is None
    assert len(report.notes) == 1 and report.findings == []
    assert report.notes[0].startswith(f"  skip {product}: pin commit ")
    return report.notes[0]


def test_a_product_two_pins_share_is_offered_the_keyed_pin_source(
        validate_pins, monkeypatch, tmp_path):
    """A shared product's hint offers `--pin-source <product>=<path>` (N3): the
    bare `--pin-source` answers for every pin with no more specific source,
    so with two pins it gives the other the finding #275 was about, and the
    variable answers for neither. The keyed form is the one source that says
    which pin it is for."""
    for product in ("open-glass", "open_glass"):
        line = skip_hint(validate_pins, monkeypatch, tmp_path,
                         ["open-glass", "open_glass"], product)
        assert line.endswith(
            f"A --pin-source {product}=<path> or a checkout at ../{product} "
            "beside this assembly root would verify it offline.")
        assert "SHAPE_PIN_SOURCE" not in line
        assert "A --pin-source or" not in line


@pytest.mark.parametrize("products", [
    pytest.param(["open-glass"], id="alone"),
    pytest.param(["open-glass", "openGlass"], id="variables-differ"),
    pytest.param(["open-glass", "Open-Glass"], id="one-product-twice"),
])
def test_a_product_with_a_variable_to_itself_is_offered_it_as_before(
        validate_pins, monkeypatch, tmp_path, products):
    """The control: the hint's text for every product no other shares a
    variable with is unchanged, the variable and the bare `--pin-source`."""
    line = skip_hint(validate_pins, monkeypatch, tmp_path, products,
                     "open-glass")
    assert line.endswith(
        "A --pin-source, SHAPE_PIN_SOURCE_OPEN_GLASS, or a checkout at "
        "../open-glass beside this assembly root would verify it offline.")


@pytest.mark.parametrize("first, second, variable", FOLDED_APART)
def test_the_note_is_made_for_names_casefold_took_for_one_product(
        validate_pins, tmp_path, first, second, variable):
    """A hand-written `project.yaml` naming `openß` and `openss` (and the
    three other pairs) declares two pins one variable names: the manifest is
    READ, as the validator reads it, and `_report_pin_source_collisions` is
    asked of what it declares. Every name is written as an escape in this
    file, and the manifest holds it as UTF-8, so no part of the run depends
    on the console's code page."""
    manifest = tmp_path / "project.yaml"
    write(manifest, f"schema_version: 1\nneutral_product_pins:\n"
                    f"  - {first}\n  - {second}\n")
    products = repo_shape.load_yaml(manifest)["neutral_product_pins"]
    assert products == [first, second]
    report = validate_pins.Report()
    validate_pins._report_pin_source_collisions(products, report)
    assert report.findings == []
    assert report.notes == [
        NOTE + collides(f"{first!r} and {second!r}", variable)]


# --- a project that already declares such a pair takes a shape update ---------

#: The two copied files #275's change ships into every project, as upstream
#: commit B changes them: a line appended to each, which is all an update that
#: carries `validate-pins.py` and `repo_shape.py` has to be for `apply` to
#: rewrite both and then run the project's validators.
VALIDATE_PINS_SOURCE = "templates/assembly-root/scripts/validate-pins.py"
SHIPPED = {VALIDATE_PINS_SOURCE: "validate-pins",
           "scripts/repo_shape.py": "repo_shape"}
SHIPPED_COPIES = ("scripts/validate-pins.py", "scripts/repo_shape.py")


@pytest.fixture(scope="module")
def behind(tmp_path_factory) -> dict:
    """A clone of this repository at A, and B, which changes the two files a
    project's pin validator is made of."""
    _base, upstream, commit_a, clone = scaffold_upstream_and_project(
        tmp_path_factory, "pin-source-collides-update")
    commit_b = commit_upstream_changes(
        upstream, "Ship the pin validator's change",
        {source: f"\n# {label}, as an update ships it.\n"
         for source, label in SHIPPED.items()})
    return {"upstream": upstream, "clone": clone, "a": commit_a, "b": commit_b}


def declared_project(behind, base: Path, names) -> Path:
    """A copy of the project as it was scaffolded at A, then declaring a pin
    on each of `names` as an older scaffold's project does (main through
    ab623dd scaffolded `--pin open-glass@A --pin open_glass@B`, exit 0, and
    this is what that left), committed. A stand-in repository for each name
    sits BESIDE the project, so each pin is recomputed offline and no `gh` is
    asked."""
    root = base / PROJECT
    shutil.copytree(behind["clone"], root, symlinks=True)
    declare_pins(root, base, names)
    git("add", "-A", cwd=root)
    git("commit", "-q", "-m", "Declare the pins", cwd=root)
    return root


def update(behind, root: Path, verb: str, *args: str):
    return run_script(behind["upstream"] / "update-shape.py", verb, "--root",
                      str(root), "--upstream", str(behind["upstream"]),
                      "--at", behind["b"], *args)


def doctor_of(behind, root: Path) -> dict:
    result = run_script(behind["upstream"] / "shape-doctor.py", "--root",
                        str(root), "--json")
    payload = json.loads(result.stdout)
    return {"exit": result.returncode, "verdict": payload["verdict"],
            "rows": {row["id"]: row for row in payload["rows"]}}


def pins_row_says_the_collision(row: dict, names) -> None:
    """The doctor's `pins` row over a `validate-pins.py` that passed and
    printed the `neutral-pin-source-collides` note: a `note`, with the note
    in `detail.notes` and quoted in the reason, and no NEXT, because which
    declaration stays is the human's decision (#460's pins-note line). The
    row used to say `ok`, and the note reached nobody."""
    assert row["status"] == "note", row
    assert row["next"] is None, row
    (note,) = row["detail"]["notes"]
    assert note.startswith("neutral-pin-source-collides: "), row
    assert "SHAPE_PIN_SOURCE_OPEN_GLASS" in note, row
    assert all(repr(name) in note for name in names), row
    assert row["reason"].endswith(f"passes, but notes: {note}"), row


@pytest.mark.parametrize("names", [
    pytest.param(["open-glass", "open_glass"], id="hyphen-underscore"),
    pytest.param(["open-glass", "open.glass", "open_glass"], id="three"),
])
def test_a_project_declaring_a_colliding_pair_takes_a_shape_update(
        behind, tmp_path, names):
    """THE FIRST ROUND'S FINDING LOCKED SUCH A PROJECT OUT. Main through
    ab623dd scaffolds `--pin open-glass@A --pin open_glass@B`, and the first
    round made `neutral-pin-source-collides` a finding, so the NEW
    `validate-pins.py` that `update-shape.py apply` runs over the rewritten
    root exited 1 and the whole apply ended `REFUSED update-validators-red`,
    rolled back, for this update and every later one, until a person dropped a
    true declaration of descent. Now it is a note: the update applies, the
    project's validator passes and says the note, each pin still verifies from
    its own checkout, and the doctor's `pins` row carries the note before and
    after, as a `note` row (#460's pins-note line, #448's ruling), which moves
    no verdict a project declaring no pair does not have."""
    root = declared_project(behind, tmp_path, names)
    control = declared_project(behind, tmp_path / "control", ["openGlass"])

    before, before_control = doctor_of(behind, root), doctor_of(behind,
                                                                control)
    pins_row_says_the_collision(before["rows"]["pins"], names)
    assert before_control["rows"]["pins"]["status"] == "ok", before_control
    assert before["rows"]["shape-currency"]["status"] == "FINDING"
    assert (before["verdict"], before["exit"]) == (
        before_control["verdict"], before_control["exit"]), (before,
                                                              before_control)

    checked = update(behind, root, "check")
    assert checked.returncode == 1, checked.stdout + checked.stderr
    behind_by = verdicts(checked.stdout)
    for copy in SHIPPED_COPIES:
        assert behind_by[copy] == "upstream-changed", checked.stdout

    applied = update(behind, root, "apply", "--yes")
    assert applied.returncode == 0, applied.stdout + applied.stderr
    assert "update-validators-red" not in applied.stdout + applied.stderr
    # The blob at B, never the upstream's working-tree file: a helper that
    # appended to it with `write_text` wrote CRLF on Windows.
    shipped = subprocess.run(
        ["git", "show", f"{behind['b']}:{VALIDATE_PINS_SOURCE}"],
        cwd=str(behind["upstream"]), capture_output=True, check=True).stdout
    assert (root / "scripts" / "validate-pins.py").read_bytes() == shipped, (
        "the update was applied")

    result = validate(root)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FINDING" not in result.stderr
    (note,) = collision_notes(result)
    assert "SHAPE_PIN_SOURCE_OPEN_GLASS" in note
    assert all(repr(name) in note for name in names)
    for name in names:
        assert f"  ok  {name}: pin commit " in result.stdout
    assert result.stdout.count("digest recomputes (sibling checkout (") == len(
        names)

    controlled = update(behind, control, "apply", "--yes")
    assert controlled.returncode == 0, controlled.stdout + controlled.stderr
    after, after_control = doctor_of(behind, root), doctor_of(behind, control)
    pins_row_says_the_collision(after["rows"]["pins"], names)
    assert after_control["rows"]["pins"]["status"] == "ok", after_control
    assert after["rows"]["shape-currency"]["status"] == "ok"
    assert (after["verdict"], after["exit"]) == (
        after_control["verdict"], after_control["exit"]), (after,
                                                            after_control)
    assert after["exit"] == 0, after


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
