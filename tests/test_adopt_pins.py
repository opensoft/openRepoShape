# SPDX-License-Identifier: Apache-2.0
"""`adopt-project.py plan --pin` takes a pin and `execute` writes its file (#273).

On main through c7c02fa, `adopt-project.py plan --pin` took a NAME only
(`--pin openGlass`, `--pin opensoft/openGlass`) and refused a trailing
`@<commit>` as `adopt-pin-malformed`. `plan`, `check` and `execute` each exited
0, `execute` said `adoption verified`, and the manifest listed the name in
`neutral_product_pins:` with no `contracts/<product>-pin.yaml` beside it, so
the adopted root's own `validate-pins.py` refused it as `neutral-pin-missing`
on its first run. `--pin opensoft/openGlass` put the owner in the manifest,
naming a file in a directory; `--pin spec` and `--pin shape` passed the gate
on the leg's or the shape's own pin; a repeated `--pin` was listed twice.

Brett Heap ruled on 2026-10-12 for the scaffold's contract: `--pin
[owner/]product@<40 hex>`, with `--pin-owner` and `--pin-source` meaning what
they mean for `scaffold-project.py`, the digest read at `plan` time and
recorded in the plan with the product, the repository and the commit, so that
`check` and `execute` read no network for a pin; `execute` writes the pin file
through the materializer the scaffold uses, and the manifest lists the product
with its owner stripped. The refusals the scaffold makes (#241) are adopt's:
`spec`, `code` and `shape` in any case, and one product twice. A plan that
holds a name alone, or a pin missing its commit or digest, is a `check` finding
and an `execute` refusal before any leg exists. So, since #449, is a commit
or a digest edited after `plan` read them, where the clone `plan` read the
digest from is still on this machine to recompute it; where it is not, a NOTE
says the digest was not rechecked.

NO NETWORK AND NO GITHUB. The neutral product is a stand-in repository made
here; `--pin-source` points at it, and a `gh` on PATH records its arguments and
exits 97, so a run that called it would say so (Windows runs no `#!` script,
so there the record stays empty whatever happens). The end-to-end tests need
`git filter-repo`, as `tests/test_adopt_e2e.py` does, and skip without it.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from conftest import (ADOPT, REPO, SCAFFOLD, SYNTHETIC_TREE, WINDOWS_SKIP,
                      as_human, cloned_just_pushed, findings, git,
                      make_source_repo, planned, refused_before_any_leg,
                      resolve, rmtree, run_script)

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402
from repo_shape import (Refusal, double_quoted, load_yaml,  # noqa: E402
                        parse_yaml, pin_source_env_name, tree_digest)

UTF8 = "utf-8"
PROJECT = "MedxGlass"
ORG = "testorg"
BRANCH = "adopt/three-repo-shape"
ANSWERS = (("examples/", "spec"), (".claude/", "root"),
           ("release.yaml", "root"))
#: What `conftest.planned` answers, for a plan written with no pin.
PLANNED = dict(ANSWERS)
PIN_FILE = "contracts/openglass-pin.yaml"
#: The plan file the end-to-end runs write.
PLAN_NAME = "adoption-plan.yaml"
#: How the gate this test vouches for says the pin's digest was RECOMPUTED
#: from the stand-in, never skipped (#272).
RECOMPUTES = "openGlass: pin commit {commit} digest recomputes"

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")


@pytest.fixture(scope="module")
def adopter():
    """`adopt-project.py` loaded as a module, so `cmd_execute` runs here."""
    module_spec = importlib.util.spec_from_file_location("adopt_pins", ADOPT)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def make_product(path: Path) -> tuple[Path, str, str]:
    """A local stand-in for `openGlass` with two commits: `(path, first,
    second)`. Its files are written as bytes, so the tree is the same on
    every platform."""
    path.mkdir(parents=True)
    git("init", "-q", "-b", "main", cwd=path)
    commits = []
    for name, body in (("README.md", b"# openGlass\n"),
                       ("contracts/glass.yaml", b"schema_version: 1\n")):
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_bytes(body)
        git("add", "-A", cwd=path)
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
            name, cwd=path)
        commits.append(git("rev-parse", "HEAD", cwd=path).stdout.strip())
    return (path, *commits)


@pytest.fixture(scope="module")
def glass(tmp_path_factory):
    return make_product(tmp_path_factory.mktemp("glass") / "openGlass")


def stub_gh(directory: Path) -> dict:
    """A `gh` that records its arguments in `gh.log` beside it and exits 97,
    and the environment that puts it first on PATH; with `GH_STUB_TREE`
    set, it prints that file and exits 0 instead, as `gh api` prints a
    tree listing."""
    bin_dir = directory / "fakebin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(textwrap.dedent("""\
        #!/usr/bin/env python3
        import os, sys
        with open(os.environ["GH_STUB_LOG"], "a", encoding="utf-8") as log:
            log.write(" ".join(sys.argv[1:]) + "\\n")
        tree = os.environ.get("GH_STUB_TREE")
        if tree:
            with open(tree, encoding="utf-8") as listing:
                sys.stdout.write(listing.read())
            sys.exit(0)
        print("HTTP 404: Not Found", file=sys.stderr)
        sys.exit(97)
        """), encoding=UTF8)
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "GH_STUB_LOG": str(directory / "gh.log")}


def gh_calls(env: dict) -> str:
    log = Path(env["GH_STUB_LOG"])
    return log.read_text(encoding=UTF8) if log.exists() else ""


@pytest.fixture
def gh_env(tmp_path):
    return stub_gh(tmp_path)


def plan_with(source: Path, out: Path, *pins: str, extra: tuple = (),
              env: dict | None = None,
              project: str = PROJECT) -> subprocess.CompletedProcess:
    """`plan` for `source` with a `--pin` for each of `pins`."""
    return run_script(ADOPT, "plan", "--source", str(source),
                      "--project", project, "--org", ORG,
                      "--elected-by", "Test Human",
                      "--elected-on", "2026-09-02", "--out", str(out),
                      *(arg for pin in pins for arg in ("--pin", pin)),
                      *extra, env=env)


def pin_entry(product: str = "openGlass",
              repository: str = "opensoft/openGlass", commit: str = "",
              digest: str = "", source: str = "local-clone (openGlass)",
              omit: tuple = ()) -> str:
    """One `pins:` mapping as `plan` writes it, its keys in `plan`'s order,
    with each key in `omit` left out."""
    fields = (("product", product), ("repository", repository),
              ("commit", f'"{commit}"'), ("tree_sha256", f'"{digest}"'),
              ("digest_source", f'"{source}"'))
    lines = [f"{key}: {value}" for key, value in fields if key not in omit]
    return "".join(("  - " if index == 0 else "    ") + line + "\n"
                   for index, line in enumerate(lines))


def with_pins(plan: Path, block: str) -> None:
    """The plan's `pins: []` replaced by `block` (which starts with
    `pins:`), as a hand edit would leave it: bytes, so LF everywhere."""
    text = plan.read_bytes().decode(UTF8)
    assert text.count("pins: []\n") == 1, "the plan was written with no pin"
    plan.write_bytes(text.replace("pins: []\n", block, 1).encode(UTF8))


def a_good_pin(glass) -> str:
    path, commit, _ = glass
    return pin_entry(commit=commit, digest=tree_digest(path, commit))


# --- the two spellings of #273's table, end to end --------------------------
#
# `openGlass` and `opensoft/openGlass` were the first two rows: each exited 0
# through `execute` with no pin file, the second with the owner in the
# manifest. Each now records the pin at `plan`, writes the file at `execute`
# and leaves a root whose own gate passes, with no network: the stand-in the
# digest was read from is DELETED before `check`, so neither `check` nor
# `execute` can have read it, and `gh` is never run.

#: `(the --pin name, the repository it pins)`.
SPELLINGS = [
    pytest.param(("openGlass", "opensoft/openGlass"), id="name"),
    pytest.param(("opensoft/openGlass", "opensoft/openGlass"), id="owner"),
    pytest.param(("ExplicitOwner/openGlass", "ExplicitOwner/openGlass"),
                 id="another-owner"),
]


@pytest.fixture(scope="module", params=SPELLINGS)
def adopted(request, tmp_path_factory, glass):
    """One real adoption with one `--pin`: plan, answer, check, execute;
    and, for the same pin read from the same stand-in, one real scaffold,
    whose pin file the adoption's is compared with."""
    if shutil.which("git-filter-repo") is None:
        pytest.skip("git filter-repo is not installed")
    spelling, repository = request.param
    base = tmp_path_factory.mktemp("adopt-pin")
    env = stub_gh(base)
    _, commit, _ = glass
    # A copy the digest is read from, deleted before `check`.
    readable = base / "openGlass-copy"
    shutil.copytree(glass[0], readable, symlinks=True)
    scaffolded = run_script(
        SCAFFOLD, "--org", ORG, "--project", PROJECT,
        "--elected-by", "Test Human", "--elected-on", "2026-09-02",
        "--pin", f"{spelling}@{commit}", "--pin-source", str(readable),
        "--local-remote-dir", str(base / "scaffold-remotes"),
        "--work-dir", str(base / "scaffold-work"), env=env)
    assert scaffolded.returncode == 0, scaffolded.stderr + scaffolded.stdout
    source = make_source_repo(base / "Thing")
    plan = base / PLAN_NAME
    planned_run = plan_with(source, plan, f"{spelling}@{commit}",
                            extra=("--pin-source", str(readable)), env=env)
    assert planned_run.returncode == 0, planned_run.stderr + planned_run.stdout
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    rmtree(readable)
    checked = run_script(ADOPT, "check", "--plan", str(plan), env=env)
    executed = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                          "--local-remote-dir", str(base / "remotes"),
                          "--work-dir", str(base / "work"), env=env)
    clone = base / "clone" / PROJECT
    if executed.returncode == 0:
        cloned_just_pushed(source, clone, BRANCH)
    return {"base": base, "source": source, "plan": plan, "env": env,
            "repository": repository, "commit": commit,
            "readable": readable, "planned": planned_run,
            "checked": checked, "executed": executed, "clone": clone,
            "scaffold_root": base / "scaffold-remotes" / f"{PROJECT}.git"}


@needs_filter_repo
def test_plan_records_the_pin_whole(adopted, glass):
    """Product, repository, commit, digest and how it was read: everything
    `execute` writes the file from, so that it reads no network."""
    pins = load_yaml(adopted["plan"])["pins"]
    assert pins == [{
        "product": "openGlass",
        "repository": adopted["repository"],
        "commit": adopted["commit"],
        "tree_sha256": tree_digest(glass[0], adopted["commit"]),
        "digest_source": f"local-clone ({adopted['readable']})",
    }]
    assert (f"pin        {adopted['repository']} @ {adopted['commit'][:12]}"
            in adopted["planned"].stdout)
    assert f"-> {PIN_FILE}" in adopted["planned"].stdout


@needs_filter_repo
def test_check_and_execute_read_neither_the_source_nor_gh(adopted):
    """The stand-in was deleted after `plan`, and `gh` records any call: the
    two commands ran on what the plan recorded, and nothing else."""
    checked, executed = adopted["checked"], adopted["executed"]
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert (f"  write {PIN_FILE}: {adopted['repository']} @ "
            f"{adopted['commit'][:12]}") in checked.stdout
    assert executed.returncode == 0, executed.stderr + executed.stdout
    assert "adoption verified" in executed.stdout
    assert not adopted["readable"].exists()
    assert gh_calls(adopted["env"]) == "", gh_calls(adopted["env"])


@needs_filter_repo
def test_the_split_holds_the_pin_the_scaffold_writes(adopted):
    """The file is the one `scaffold-project.py --pin` writes for the same
    pin, byte for byte, both read from git and not from a working tree; and
    the manifest lists the product with its owner stripped, so the entry and
    the file agree (#273 decision 3)."""
    split = git("show", f"{BRANCH}:{PIN_FILE}", cwd=adopted["source"]).stdout
    scaffold = git("show", f"main:{PIN_FILE}",
                   cwd=adopted["scaffold_root"]).stdout
    assert split == scaffold
    pin = load_yaml(adopted["clone"] / PIN_FILE)
    assert pin["pin_role"] == "neutral-product"
    assert pin["product"] == "openGlass"
    assert pin["source_repository"] == adopted["repository"]
    assert pin["commit"] == adopted["commit"]
    assert pin["revision_kind"] == "commit"
    manifest = load_yaml(adopted["clone"] / "project.yaml")
    assert manifest["neutral_product_pins"] == ["openGlass"]
    assembly = next(leg for leg in manifest["legs"]
                    if leg["role"] == "assembly")
    assert assembly["naming"]["form"] == "domain-descendant"
    assert assembly["naming"]["referent_declared"] is True


@needs_filter_repo
def test_the_adopted_root_passes_its_own_gate(adopted, glass):
    """The point of #273: the validators the root carries, and the bootstrap
    `make bootstrap` runs, pass on the root `execute` called verified, with
    the pin's digest recomputed from the stand-in (`SHAPE_PIN_SOURCE_*`)."""
    clone = adopted["clone"]
    env = {**adopted["env"], "SHAPE_PIN_SOURCE_OPENGLASS": str(glass[0])}
    for validator, args in (("validate-repository-naming.py",
                             ["--project", "project.yaml"]),
                            ("validate-manifest.py", []),
                            ("validate-pins.py", [])):
        result = run_script(clone / "scripts" / validator, *args, cwd=clone,
                            env=env)
        assert result.returncode == 0, \
            f"{validator}: {result.stderr}{result.stdout}"
        if validator == "validate-pins.py":
            assert RECOMPUTES.format(commit=adopted["commit"][:12]) \
                in result.stdout, result.stdout
    booted = run_script(clone / "scripts" / "bootstrap.py", cwd=clone,
                        env=env)
    assert booted.returncode == 0, booted.stderr + booted.stdout
    assert "bootstrap ok" in booted.stdout
    assert RECOMPUTES.format(commit=adopted["commit"][:12]) in booted.stdout
    assert gh_calls(adopted["env"]) == ""


# --- a product the project's reader would take for a number (#514) ----------
#
# `plan` records the product quoted (`product: "007"`, `_pin_lines`), and
# `check` and `execute` pass it. On main 631f087 `execute` then listed it in
# `neutral_product_pins:` bare, `  - 007`, which the project's own reader
# reads back as the number 7 (and `2026` and `1.5` as numbers), so the root
# `execute` called verified failed its own `validate-pins.py` with
# `neutral-pin-entry-malformed`. Each entry is now spelled so that it reads
# back as the text `plan` recorded. `openGlass` is the control: its line
# does not move by a byte.

#: The project the products below are pinned by, a name no product here
#: makes a domain descendant of.
TEXT_PROJECT = "Northwind"
#: `(the product, how its `neutral_product_pins:` entry is spelled)`.
AS_TEXT = [
    pytest.param(("007", '"007"'), id="007"),
    pytest.param(("2026", '"2026"'), id="2026"),
    pytest.param(("1.5", '"1.5"'), id="1.5"),
    pytest.param(("openGlass", "openGlass"), id="openGlass"),
]


@pytest.fixture(scope="module", params=AS_TEXT)
def adopted_as_text(request, tmp_path_factory):
    """One real adoption with `--pin <product>@<commit> --pin-source <a local
    clone>`: plan, answer, check, execute, and a recursive clone of the split,
    which is the root a person gets."""
    if shutil.which("git-filter-repo") is None:
        pytest.skip("git filter-repo is not installed")
    product, spelled = request.param
    base = tmp_path_factory.mktemp("adopt-pin-text")
    env = stub_gh(base)
    readable, commit, _ = make_product(base / "product")
    source = make_source_repo(base / "Thing")
    plan = base / PLAN_NAME
    planned_run = plan_with(source, plan, f"{product}@{commit}",
                            extra=("--pin-source", str(readable)), env=env,
                            project=TEXT_PROJECT)
    assert planned_run.returncode == 0, planned_run.stderr + planned_run.stdout
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    checked = run_script(ADOPT, "check", "--plan", str(plan), env=env)
    executed = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                          "--local-remote-dir", str(base / "remotes"),
                          "--work-dir", str(base / "work"), env=env)
    clone = base / "clone" / TEXT_PROJECT
    if executed.returncode == 0:
        cloned_just_pushed(source, clone, BRANCH)
    return {"product": product, "spelled": spelled, "commit": commit,
            "readable": readable, "source": source, "plan": plan, "env": env,
            "checked": checked, "executed": executed, "clone": clone}


@needs_filter_repo
def test_a_pinned_product_is_listed_as_the_text_plan_recorded(
        adopted_as_text):
    """The manifest lists the product so that the project's own reader reads
    it back as the text `plan` recorded: `"007"`, and `openGlass` as it always
    was. The line is read from git, as bytes, and not from a working tree."""
    adopted = adopted_as_text
    product = adopted["product"]
    assert load_yaml(adopted["plan"])["pins"][0]["product"] == product
    checked, executed = adopted["checked"], adopted["executed"]
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert executed.returncode == 0, executed.stderr + executed.stdout
    assert "adoption verified" in executed.stdout
    blob = subprocess.run(["git", "show", f"{BRANCH}:project.yaml"],
                          cwd=str(adopted["source"]), capture_output=True,
                          check=True).stdout
    line = f"\nneutral_product_pins: \n  - {adopted['spelled']}\n\n"
    text = blob.decode(UTF8, "replace")
    at = text.find("\nneutral_product_pins:")
    assert line.encode(UTF8) in blob, text[at:at + len(line) + 16]
    manifest = load_yaml(adopted["clone"] / "project.yaml")
    assert manifest["neutral_product_pins"] == [product]
    assert gh_calls(adopted["env"]) == ""


@needs_filter_repo
def test_a_pinned_product_passes_the_adopted_roots_own_gate(adopted_as_text):
    """The point of #514: `execute` said `adoption verified`, so the root's
    own `validate-manifest.py` and `validate-pins.py` pass, the second with
    the pin's digest recomputed from the stand-in."""
    adopted = adopted_as_text
    product, clone = adopted["product"], adopted["clone"]
    env = {**adopted["env"],
           pin_source_env_name(product): str(adopted["readable"])}
    for validator in ("validate-manifest.py", "validate-pins.py"):
        result = run_script(clone / "scripts" / validator, "--root", ".",
                            cwd=clone, env=env)
        said = result.stderr + result.stdout
        assert result.returncode == 0, f"{validator}: {said}"
        assert "neutral-pin-entry-malformed" not in said, said
    assert (f"{product}: pin commit {adopted['commit'][:12]} digest "
            "recomputes") in result.stdout, result.stdout
    assert gh_calls(adopted["env"]) == ""


#: Product names `PIN_ARG_RE` admits, by how the project's reader takes each
#: written bare: as a number, as a bool or None, or as the text itself.
NUMBERS = ("007", "2026", "1.5", "-1", "-0.5", "20261011")
KEYWORDS = ("true", "True", "TRUE", "false", "False", "FALSE", "null",
            "Null", "NULL")
PLAIN = ("openGlass", "open-glass", "open_glass", "openGlass2", ".5", "x.y",
         "_x", "Openglass")
#: Text to the reader bare, and quoted all the same, as `plan` quotes them in
#: `product:`: `y` writes bare only a name that begins with a letter, `_` or
#: `.`, and a YAML reader other than the project's takes `0x1F` and `1e3`
#: for numbers.
QUOTED_BY_Y = ("3dGlass", "-x", "0x1F", "1e3")


def entries_read_back(entries: str) -> object:
    """`entries`, the `NEUTRAL_PRODUCT_PINS` value, rendered into the
    template's own line and read as the project reads its manifest."""
    template = (REPO / "templates" / "assembly-root" / "project.yaml")
    line = next(line for line in template.read_text(encoding=UTF8)
                .splitlines() if "{{NEUTRAL_PRODUCT_PINS}}" in line)
    rendered = shape_materialize.render(
        line + "\n", {"NEUTRAL_PRODUCT_PINS": entries}, "project.yaml")
    return parse_yaml(rendered)["neutral_product_pins"]


@pytest.mark.parametrize("product", [
    *(pytest.param(name, id=f"number-{name}") for name in NUMBERS),
    *(pytest.param(name, id=f"keyword-{name}") for name in KEYWORDS),
    *(pytest.param(name, id=f"plain-{name}") for name in PLAIN),
    *(pytest.param(name, id=f"quoted-by-y-{name}") for name in QUOTED_BY_Y),
])
def test_each_entry_reads_back_as_the_product(adopter, product):
    """Every product reads back as its text. A name `y` writes bare and the
    reader reads back is written bare, as on main, so a root's `openGlass`
    line does not move by a byte; every other is double-quoted, as `plan`
    quotes it in `product:`. A keyword is the one `y` writes bare and the
    reader takes for a bool or None (#181). It reaches `execute` only from a
    plan edited by hand, because `plan` writes `product: true` bare and
    `check` then refuses it, but the manifest reads back as the plan does,
    edited or not."""
    entries = adopter._neutral_product_pins({product})
    assert entries_read_back(entries) == [product]
    if product in PLAIN:
        assert entries == f"\n  - {product}"
    else:
        assert entries == f'\n  - "{product}"'


def test_every_entry_together_reads_back_in_order(adopter):
    """All of them in one list, as a plan with many pins writes it: one line
    each, sorted, and each read back as its text."""
    every = {*NUMBERS, *KEYWORDS, *PLAIN, *QUOTED_BY_Y}
    entries = adopter._neutral_product_pins(every)
    assert len(entries.splitlines()) == len(every) + 1
    assert entries_read_back(entries) == sorted(every)


def test_no_pin_is_an_empty_list(adopter):
    """A plan with no pin lists none, as it always has."""
    assert adopter._neutral_product_pins(set()) == "[]"
    assert entries_read_back("[]") == []


# --- what `plan` refuses, in the scaffold's words ---------------------------

@pytest.mark.parametrize("value", ["openGlass", "opensoft/openGlass"])
def test_a_name_with_no_commit_is_refused_by_plan(source_repo, tmp_path,
                                                  gh_env, value):
    """The old spelling. A name alone is a declaration with no referent,
    and the refusal says the spelling that is one, as the scaffold's does."""
    out = tmp_path / "plan.yaml"
    result = plan_with(source_repo, out, value, env=gh_env)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(
        f"REFUSED pin-malformed: --pin {value!r} is not "
        "`[owner/]<openProduct>@<40 hex commit>`"), result.stderr
    assert ("--pin openGlass@0123456789abcdef0123456789abcdef01234567"
            in result.stderr)
    assert not out.exists()
    assert gh_calls(gh_env) == ""


#: `(the --pin values, what the refusal says)`, as
#: `tests/test_scaffold_pin_collisions.py` spells the scaffold's: `{A}` and
#: `{B}` are the stand-in's two commits. The first five name a file the shape
#: writes; the last three are two pins at one file.
SHAPE_WRITES = ("a file the shape writes into the assembly root itself: name "
                "the product for the repository it pins.")
ONE_FILE = "which holds one pin: pass each product once."
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
    pytest.param(["openGlass@{A}", "opensoft/openGlass@{B}"],
                 "--pin 'openGlass@{A}' and --pin 'opensoft/openGlass@{B}' "
                 "write the pins of the product `openGlass` at one file, "
                 "`contracts/openglass-pin.yaml`, " + ONE_FILE,
                 id="repeat-two-commits"),
]


@pytest.mark.parametrize("values, said", REFUSED_CASES)
def test_a_colliding_pin_is_refused_by_plan(source_repo, tmp_path, glass,
                                            gh_env, values, said):
    """#273 decisions 4 and 5, answered as the scaffold answers them (#241):
    a product named for a file the shape writes, and one product twice,
    refused before a plan is written and before any digest is read, in the
    scaffold's sentence and remediation under adopt's own code."""
    path, first, second = glass
    out = tmp_path / "plan.yaml"
    result = plan_with(source_repo, out,
                       *(value.format(A=first, B=second) for value in values),
                       extra=("--pin-source", str(path)), env=gh_env)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr == (
        f"REFUSED adopt-pin-collides: {said.format(A=first, B=second)}\n"
        f"{shape_materialize.PIN_COLLISION_REMEDIATION}\n")
    assert not out.exists()
    assert gh_calls(gh_env) == ""


def test_two_products_one_source_variable_names_are_refused_by_plan(
        source_repo, tmp_path, glass, gh_env):
    """#275's adopt half, through the function the scaffold refuses with:
    `open-glass` and `open_glass` are two pin files and one
    `SHAPE_PIN_SOURCE_OPEN_GLASS`, which the root's own `validate-pins.py`
    would report as `neutral-pin-source-collides`."""
    path, first, second = glass
    out = tmp_path / "plan.yaml"
    result = plan_with(source_repo, out, f"open-glass@{first}",
                       f"open_glass@{second}",
                       extra=("--pin-source", str(path)), env=gh_env)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr == (
        f"REFUSED adopt-pin-collides: --pin 'open-glass@{first}' and --pin "
        f"'open_glass@{second}' name the products `open-glass` and "
        "`open_glass`, and one variable, `SHAPE_PIN_SOURCE_OPEN_GLASS`, names "
        "the local checkout of each: it cannot say which it holds.\n"
        "Remediation: nothing was created. "
        f"{shape_materialize.PIN_VARIABLE_REMEDIATION}\n")
    assert not out.exists()
    assert gh_calls(gh_env) == ""


def test_a_leg_mounted_over_a_pins_file_is_refused_by_plan(source_repo,
                                                           tmp_path, glass):
    """`execute` mounts the legs and then writes each pin, so a leg at the
    pin's file would take it. The control is the same leg path with no pin,
    where that path is no file the shape writes."""
    path, commit, _ = glass
    legs = ("--spec-path", PIN_FILE, "--pin-source", str(path))
    refused = plan_with(source_repo, tmp_path / "refused.yaml",
                        f"openGlass@{commit}", extra=legs)
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert refused.stderr.startswith(
        f"REFUSED adopt-leg-path-collides: --spec-path '{PIN_FILE}' is "
        f"`{PIN_FILE}`."), refused.stderr
    assert f"`{PIN_FILE}`, `contracts/shape-pin.yaml`) or `shape`" \
        in refused.stderr
    assert not (tmp_path / "refused.yaml").exists()
    control = plan_with(source_repo, tmp_path / "control.yaml", extra=legs)
    assert control.returncode == 0, control.stdout + control.stderr


@WINDOWS_SKIP  # the stub `gh` is a `#!` script; Windows executes none
def test_with_no_pin_source_plan_reads_the_digest_from_gh(source_repo,
                                                          tmp_path, glass,
                                                          gh_env):
    """The scaffold's other way to the digest: `gh api` over the forge's
    tree listing, under `opensoft` for an unqualified name. The stub answers
    with the stand-in's own tree, so the recorded digest is the one a clone
    gives; and when the forge does not answer, the refusal is the
    scaffold's, and no plan is written."""
    path, commit, _ = glass
    listing = git("ls-tree", "-r", commit, cwd=path).stdout.splitlines()
    rows = []
    for line in listing:
        head, name = line.split("\t", 1)
        mode, kind, sha = head.split()
        rows.append({"mode": mode, "type": kind, "sha": sha, "path": name})
    tree = tmp_path / "tree.json"
    tree.write_text(json.dumps({"tree": rows, "truncated": False}),
                    encoding=UTF8)
    out = tmp_path / "plan.yaml"
    result = plan_with(source_repo, out, f"openGlass@{commit}",
                       env={**gh_env, "GH_STUB_TREE": str(tree)})
    assert result.returncode == 0, result.stdout + result.stderr
    assert gh_calls(gh_env).splitlines() == [
        f"api repos/opensoft/openGlass/git/trees/{commit}?recursive=1"]
    pin = load_yaml(out)["pins"][0]
    assert pin["tree_sha256"] == tree_digest(path, commit)
    assert pin["digest_source"] == "gh-api-tree-recursive"

    unanswered = plan_with(source_repo, tmp_path / "unanswered.yaml",
                           f"openGlass@{commit}", env=gh_env)
    assert unanswered.returncode == 2
    assert unanswered.stderr.startswith(
        f"REFUSED pin-unreadable: `gh api` could not read opensoft/openGlass "
        f"@ {commit}: HTTP 404: Not Found"), unanswered.stderr
    assert not (tmp_path / "unanswered.yaml").exists()


def test_pin_owner_resolves_an_unqualified_name(source_repo, tmp_path,
                                               glass, gh_env):
    """`--pin-owner` means what it means for the scaffold: the owner an
    unqualified name resolves under, never `--org`, and a value checked like
    any other that reaches a command line. An owner named in `--pin` itself
    wins, as the `another-owner` adoption above shows."""
    path, commit, _ = glass
    out = tmp_path / "plan.yaml"
    result = plan_with(source_repo, out, f"openGlass@{commit}",
                       extra=("--pin-owner", "MedxCorp",
                              "--pin-source", str(path)), env=gh_env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert load_yaml(out)["pins"][0]["repository"] == "MedxCorp/openGlass"

    unsafe = plan_with(source_repo, tmp_path / "unsafe.yaml",
                       f"openGlass@{commit}",
                       extra=("--pin-owner=--upload-pack=touch pwned",
                              "--pin-source", str(path)), env=gh_env)
    assert unsafe.returncode == 2, unsafe.stdout + unsafe.stderr
    assert unsafe.stderr.startswith("REFUSED unsafe-value: --pin-owner"), \
        unsafe.stderr
    assert not (tmp_path / "unsafe.yaml").exists()
    assert gh_calls(gh_env) == ""


def test_a_pin_the_source_does_not_have_is_refused_by_plan(source_repo,
                                                           tmp_path, glass):
    path, _, _ = glass
    out = tmp_path / "plan.yaml"
    result = plan_with(source_repo, out, "openGlass@" + "0" * 40,
                       extra=("--pin-source", str(path)))
    assert result.returncode == 2
    assert "REFUSED pin-source-unreadable" in result.stderr
    assert not out.exists()


# --- no `gh` on PATH (#273's review, S2) -------------------------------------
#
# `gh api` is the DEFAULT way to a pin's digest: `--pin-source` is the test
# path. With no `gh` installed, `subprocess.run(["gh", ...])` raised
# `FileNotFoundError` out of the shared reader, a traceback, exit 1, from the
# scaffold and, since #273, from `adopt-project.py plan --pin`, which needed
# no `gh` before. It is `gh-not-found`, as the validator's twin
# (`repo_shape.tree_digest_from_gh`) names it.

GH_NOT_FOUND = ("REFUSED gh-not-found: the `gh` CLI is not on PATH, so `gh "
                "api` cannot read opensoft/openGlass @ {commit}: ")
GH_NOT_FOUND_REMEDIATION = (
    "Remediation: pass --pin-source <a local clone of that repository> to "
    "compute the digest with no network at all, or put `gh` on PATH and run "
    "this again (`openRepoShape --preflight` names each missing prerequisite "
    "and offers to install it, on a typed yes).")


def test_with_no_gh_on_path_the_forge_reader_is_gh_not_found(monkeypatch,
                                                             tmp_path):
    """The shared reader itself, with a PATH that holds nothing at all: on
    every platform, and with no `gh` of anybody's reachable."""
    nothing = tmp_path / "nothing"
    nothing.mkdir()
    monkeypatch.setenv("PATH", str(nothing))
    commit = "0" * 40
    with pytest.raises(Refusal) as refused:
        shape_materialize.pin_digest_from_gh("opensoft/openGlass", commit)
    assert refused.value.code == "gh-not-found"
    assert str(refused.value).startswith(GH_NOT_FOUND.format(commit=commit))
    assert refused.value.remediation == GH_NOT_FOUND_REMEDIATION


#: A PATH that finds `git` and no `gh` is a directory holding a link to git
#: alone, and Windows grants a symlink only to an elevated user.
GIT_ALONE = pytest.mark.skipif(
    os.name == "nt",
    reason="needs a PATH that finds git and no gh, made with a symlink to "
           "git, which Windows grants only to an elevated user")


@GIT_ALONE
@pytest.mark.parametrize("kind", ["scaffold-dry-run", "adopt-plan"])
def test_with_no_gh_on_path_a_pin_is_gh_not_found(kind, source_repo,
                                                  tmp_path, glass):
    """Both tools, end to end, with no `--pin-source`: exit 2, the refusal
    and its remediation, no traceback, and nothing made -- no plan, no
    remote and no work directory."""
    _, commit, _ = glass
    alone = tmp_path / "git-alone"
    alone.mkdir()
    os.symlink(shutil.which("git"), alone / "git")
    assert shutil.which("gh", path=str(alone)) is None
    env = {"PATH": str(alone)}
    if kind == "adopt-plan":
        made = [tmp_path / "plan.yaml"]
        result = plan_with(source_repo, made[0], f"openGlass@{commit}",
                           env=env)
    else:
        made = [tmp_path / "remotes", tmp_path / "work"]
        result = run_script(
            SCAFFOLD, "--org", ORG, "--project", PROJECT,
            "--elected-by", "Test Human", "--elected-on", "2026-09-02",
            "--pin", f"openGlass@{commit}",
            "--local-remote-dir", str(made[0]), "--work-dir", str(made[1]),
            "--dry-run", env=env)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert result.stderr.startswith(GH_NOT_FOUND.format(commit=commit)), \
        result.stderr
    assert result.stderr.endswith(f"\n{GH_NOT_FOUND_REMEDIATION}\n"), \
        result.stderr
    assert not [path for path in made if path.exists()]


# --- a `--pin-source` `plan` cannot record (#273's review, N2) ---------------
#
# `plan` records the path in each pin's `digest_source:`, and `check` holds
# that to one printable line. A path with a line break, an ESC or a byte
# that is not UTF-8 was planned, exit 0, and printed raw in `plan`'s report,
# and `check` then found `plan-pin-malformed` with advice that wrote the
# same plan again. `plan` now asks `check`'s question first, before any
# digest is read: nothing is made and nothing is read.

UNRECORDABLE_REMEDIATION = (
    "Remediation: no plan was written. Point --pin-source at a clone whose "
    "path is one line of printable UTF-8 text, or drop --pin-source and let "
    "`gh api` read the forge. `check` refuses a `digest_source:` that is not "
    "one printable line as `plan-pin-malformed`, because `execute` writes it "
    "into the pin file as it stands.")

#: A command line and a file name on Windows hold none of these.
POSIX_NAMES = pytest.mark.skipif(
    os.name == "nt",
    reason="needs a command-line argument holding a control character or a "
           "byte that is not UTF-8, which a Windows file name cannot hold")

LINE_BREAK = "it holds a line break, and it is written as one line"


@pytest.mark.parametrize("name, reason", [
    pytest.param("gl\x1bass", "it holds a control character", id="esc",
                 marks=POSIX_NAMES),
    pytest.param("gl\nass", LINE_BREAK, id="lf", marks=POSIX_NAMES),
    pytest.param("gl\rass", LINE_BREAK, id="cr", marks=POSIX_NAMES),
    pytest.param("gl\x1b[31mRED\nREFUSED forged-line: not the tool's\r",
                 LINE_BREAK, id="forged-line", marks=POSIX_NAMES),
    pytest.param("gl\udcffass", "it holds a byte that is not UTF-8",
                 id="not-utf-8", marks=POSIX_NAMES),
])
def test_a_pin_source_check_would_refuse_is_refused_by_plan(
        source_repo, tmp_path, gh_env, name, reason):
    """Before any digest is read, so the path need not exist: in `check`'s
    terms and #270's words, with the value `repr`'d, so the refusal is one
    line of the tool's and nothing of the path's reaches the terminal raw."""
    typed = str(tmp_path / name)
    out = tmp_path / "plan.yaml"
    result = plan_with(source_repo, out, "openGlass@" + "0" * 40,
                       extra=("--pin-source", typed), env=gh_env)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr == (
        f"REFUSED adopt-unwritable-value: --pin-source is {typed!r}, which "
        "`plan` records in each pin's `digest_source:` and `execute` writes "
        f"into `{PIN_FILE}`, and {reason}.\n{UNRECORDABLE_REMEDIATION}\n")
    assert not out.exists()
    assert gh_calls(gh_env) == ""


def test_a_clone_at_a_path_check_would_refuse_is_refused_by_plan(
        source_repo, tmp_path, glass, gh_env):
    """A clone that DOES answer, at a path `check` refuses: a zero-width
    joiner is text a file holds (`unwritable_reason` passes it) and is not
    one printable line (`check` does not), so `plan` says so in its own
    words. It is the case #270's words do not name."""
    path, commit, _ = glass
    clone = tmp_path / "open‍Glass"
    shutil.copytree(path, clone, symlinks=True)
    out = tmp_path / "plan.yaml"
    result = plan_with(source_repo, out, f"openGlass@{commit}",
                       extra=("--pin-source", str(clone)), env=gh_env)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(
        f"REFUSED adopt-unwritable-value: --pin-source is {str(clone)!r}, "
        f"which `plan` records"), result.stderr
    assert (f"into `{PIN_FILE}`, and it holds an invisible formatting "
            "character.\n") in result.stderr
    assert not out.exists()


#: The leaf of a `--pin-source` no `--pin` records, spelled so that the plan
#: and the report can be searched for it: neither holds the word otherwise.
UNREAD = "unreadclone"


@pytest.mark.parametrize("name", [
    pytest.param(f"{UNREAD}\x1bx", id="esc", marks=POSIX_NAMES),
    pytest.param(f"{UNREAD}‍x", id="zwj"),
])
def test_a_pin_source_no_pin_records_is_not_asked_about(source_repo,
                                                        tmp_path, gh_env,
                                                        name):
    """`plan` asks the question above only of a path a `--pin` will record
    (#273's review, n1). With no `--pin`, `--pin-source` names nothing `plan`
    records, reads or prints: the plan is written with `pins: []`, and
    neither it nor the report names the path, in any spelling. Asked
    anyway, `plan` refused a plan that writes no pin file, in a sentence
    naming none ("`execute` writes into , and ..."). Whether an unused
    `--pin-source` is refused or noted instead is #339's third decision,
    left open by this change; this test holds its answer today, silence, so
    that whoever decides it changes this test on purpose. The path need not
    exist, because nothing reads it."""
    typed = str(tmp_path / name)
    out = tmp_path / "plan.yaml"
    result = plan_with(source_repo, out, extra=("--pin-source", typed),
                       env=gh_env)
    assert result.returncode == 0, result.stdout + result.stderr
    text = out.read_bytes().decode(UTF8)
    assert "\npins: []\n" in text, text
    assert load_yaml(out)["pins"] == []
    said = result.stdout + result.stderr
    assert UNREAD not in text + said, said
    assert "\x1b" not in said and "‍" not in said, said
    assert not [line for line in result.stdout.splitlines()
                if line.startswith("pin ")], result.stdout
    assert gh_calls(gh_env) == ""


def test_a_pin_source_printed_in_a_report_is_spelled(source_repo, tmp_path,
                                                     glass, gh_env):
    """A path that IS one printable line for `check` and still not
    `str.isprintable` -- a no-break space -- is planned, and `plan`'s report
    and `check`'s `write` line spell it, as every other path either prints
    (`_shown`); the plan records it exactly."""
    path, commit, _ = glass
    clone = tmp_path / "open Glass"
    shutil.copytree(path, clone, symlinks=True)
    out = tmp_path / "plan.yaml"
    result = plan_with(source_repo, out, f"openGlass@{commit}",
                       extra=("--pin-source", str(clone)), env=gh_env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert load_yaml(out)["pins"][0]["digest_source"] \
        == f"local-clone ({clone})"
    line = next(line for line in result.stdout.splitlines()
                if line.startswith("pin        "))
    assert line.endswith("open\\xa0Glass)`)"), line
    assert " " not in result.stdout

    plan = planned(source_repo, tmp_path, PLANNED)
    with_pins(plan, "pins:\n" + pin_entry(
        commit=commit, digest=tree_digest(path, commit),
        source="local-clone (open\\u00a0Glass)"))
    checked = run_script(ADOPT, "check", "--plan", str(plan), env=gh_env)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert f"tree {tree_digest(path, commit)[:12]}… (`local-clone " \
        "(open\\xa0Glass)`)\n" in checked.stdout, checked.stdout
    assert " " not in checked.stdout
    assert gh_calls(gh_env) == ""


def test_a_printable_pin_source_is_printed_as_it_is(source_repo, tmp_path,
                                                    glass, gh_env):
    """The other half of `_shown` (#273's review, n2): a printable
    `--pin-source` is printed byte for byte, with no backtick and no escape,
    in `plan`'s `pin` line and in `check`'s `write` line for the plan `plan`
    wrote, as the report prints every other printable path, a Windows
    drive's backslashes among them. Spelled whatever it holds, the line
    read `(`local-clone (<path>)`)`."""
    path, commit, _ = glass
    digest = tree_digest(path, commit)
    out = tmp_path / "plan.yaml"
    result = plan_with(source_repo, out, f"openGlass@{commit}",
                       extra=("--pin-source", str(path)), env=gh_env)
    assert result.returncode == 0, result.stdout + result.stderr
    pin = (f"opensoft/openGlass @ {commit[:12]} tree {digest[:12]}… -> "
           f"{PIN_FILE} (local-clone ({path}))")
    assert [line for line in result.stdout.splitlines()
            if line.startswith("pin ")] == [f"pin        {pin}"], \
        result.stdout
    for answered, leg in ANSWERS:
        resolve(out, answered, leg)
    checked = run_script(ADOPT, "check", "--plan", str(out), env=gh_env)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert [line for line in checked.stdout.splitlines()
            if line.startswith("  write ")] == [
        f"  write {PIN_FILE}: opensoft/openGlass @ {commit[:12]} tree "
        f"{digest[:12]}… (local-clone ({path}))"], checked.stdout
    assert gh_calls(gh_env) == ""


# --- what `check` finds, and `execute` refuses before any leg exists ---------
#
# The plan is a file a person or an AI edits between `plan` and `execute`, and
# an old plan carries `pins: [openGlass]`. Each case below is written into a
# plan `plan` wrote with no pin: `check` names it, and `execute` refuses it
# with `check`'s own findings before the leg remotes' directory is made
# (`conftest.refused_before_any_leg`).

def unrecorded(glass) -> dict:
    """Each pin a plan holds with no commit or no digest: a name alone, as
    an old plan holds it, or a mapping missing one of the two."""
    path, commit, _ = glass
    digest = tree_digest(path, commit)
    named = ("is a name with no commit and no digest. `execute` writes each "
             f"declared pin's file, `{PIN_FILE}` for this one")
    return {
        "old-plan-name": ("pins: [openGlass]\n",
                          f"`pins:` entry 1, 'openGlass', {named}"),
        "old-plan-owner": ("pins:\n  - opensoft/openGlass\n",
                           f"`pins:` entry 1, 'opensoft/openGlass', {named}"),
        "no-commit": ("pins:\n" + pin_entry(digest=digest, omit=("commit",)),
                      "`pins:` entry 1 ('openGlass') records no `commit:`."),
        "no-digest": ("pins:\n" + pin_entry(commit=commit,
                                            omit=("tree_sha256",)),
                      "`pins:` entry 1 ('openGlass') records no "
                      "`tree_sha256:`."),
        "both-blank": ("pins:\n" + pin_entry(commit="", digest=""),
                       "`pins:` entry 1 ('openGlass') records no `commit:` "
                       "and no `tree_sha256:`."),
        # A name no `--pin` takes, holding an ESC and a line break that
        # would begin a forged line: the entry is `repr`'d, and neither the
        # file it names nor the `plan` it offers is spelled from it (#273's
        # review, N3: the two name guards).
        "old-plan-forged": ('pins:\n  - "open\\x1bGlass\\nREFUSED forged"\n',
                            "`pins:` entry 1, 'open\\x1bGlass\\nREFUSED "
                            "forged', is a name with no commit and no "
                            "digest. `execute` writes each declared pin's "
                            "file, one, from the commit and the digest "
                            "`plan` records, and without it the root's own "
                            "`validate-pins.py` refuses the declaration "
                            "(`neutral-pin-missing`): re-run `plan` with "
                            "`--pin <openProduct>@<40 hex commit>`"),
    }


def malformed(glass) -> dict:
    """Each `pins:` value `plan` never writes: not a list, not a pin, or a
    pin whose values are not of the form `plan` records them in."""
    path, commit, _ = glass
    digest = tree_digest(path, commit)
    entry = "`pins:` entry 1 ('openGlass') records"
    return {
        "not-a-list": ("pins: openGlass\n",
                       "`pins:` is 'openGlass', not a list of pins"),
        "a-number": ("pins:\n  - 7\n", "`pins:` entry 1 is 7, not a pin"),
        "short-commit": ("pins:\n" + pin_entry(commit=commit[:12],
                                               digest=digest),
                         f"{entry} `commit: '{commit[:12]}'`, which is not "
                         "40 hex"),
        "short-digest": ("pins:\n" + pin_entry(commit=commit,
                                               digest=digest[:12]),
                         f"{entry} `tree_sha256: '{digest[:12]}'`, which is "
                         "not 64 hex"),
        "another-product": ("pins:\n" + pin_entry(
                                repository="opensoft/openPane",
                                commit=commit, digest=digest),
                            f"{entry} `product: 'openGlass'` and "
                            "`repository: 'opensoft/openPane'`"),
        "no-owner": ("pins:\n" + pin_entry(repository="openGlass",
                                           commit=commit, digest=digest),
                     f"{entry} `product: 'openGlass'` and `repository: "
                     "'openGlass'`"),
        "no-source": ("pins:\n" + pin_entry(commit=commit, digest=digest,
                                            omit=("digest_source",)),
                      f"{entry} no `digest_source:`."),
        # `execute` writes `digest_source:` into the pin file bare, so a
        # line break there would be a line of the file (N3).
        "source-line-break": ("pins:\n" + pin_entry(
                                  commit=commit, digest=digest,
                                  source="local-clone (/x\\nforged: y)"),
                              f"{entry} `digest_source: 'local-clone "
                              "(/x\\nforged: y)'`, which is not one "
                              "printable line"),
        # Unquoted, the reader reads a number: `not text`, and never a
        # `TypeError` out of `COMMIT_RE` (N3).
        "a-number-commit": ("pins:\n  - product: openGlass\n"
                            "    repository: opensoft/openGlass\n"
                            "    commit: 1234567\n"
                            f'    tree_sha256: "{digest}"\n'
                            '    digest_source: "local-clone (openGlass)"\n',
                            f"{entry} `commit: 1234567`, which is not text"),
    }


def colliding(glass) -> dict:
    """Two pins at one file, and one at a file the shape writes: what
    `plan` refuses as `adopt-pin-collides`, written into a plan by hand."""
    path, commit, _ = glass
    digest = tree_digest(path, commit)
    return {
        "case-pair": ("pins:\n" + pin_entry(commit=commit, digest=digest)
                      + pin_entry(product="OpenGlass",
                                  repository="opensoft/OpenGlass",
                                  commit=commit, digest=digest),
                      "`pins:` entry 1 ('openGlass') and `pins:` entry 2 "
                      "('OpenGlass') write the pins of the products "
                      "`openGlass` and `OpenGlass` at one file, "
                      f"`{PIN_FILE}`, {ONE_FILE}"),
        "shape": ("pins:\n" + pin_entry(product="shape",
                                        repository="opensoft/shape",
                                        commit=commit, digest=digest),
                  "`pins:` entry 1 ('shape') writes the pin of the product "
                  "`shape` at `contracts/shape-pin.yaml`, " + SHAPE_WRITES),
        # Two files, one `SHAPE_PIN_SOURCE_<PRODUCT>` (#275).
        "variable-pair": ("pins:\n" + pin_entry(
                              product="open-glass",
                              repository="opensoft/open-glass",
                              commit=commit, digest=digest)
                          + pin_entry(product="open_glass",
                                      repository="opensoft/open_glass",
                                      commit=commit, digest=digest),
                          "`pins:` entry 1 ('open-glass') and `pins:` entry 2 "
                          "('open_glass') name the products `open-glass` and "
                          "`open_glass`, and one variable, "
                          "`SHAPE_PIN_SOURCE_OPEN_GLASS`, names the local "
                          "checkout of each: it cannot say which it holds."),
    }


@pytest.fixture(scope="module")
def cases(glass):
    """Every hand-edited `pins:` block below and the code `check` names it
    with, built once from the stand-in's commit and digest."""
    return {
        "plan-pin-unrecorded": unrecorded(glass),
        "plan-pin-malformed": malformed(glass),
        "plan-pin-collides": colliding(glass),
    }


CASE_IDS = [("plan-pin-unrecorded", name) for name in (
    "old-plan-name", "old-plan-owner", "no-commit", "no-digest", "both-blank",
    "old-plan-forged")]
CASE_IDS += [("plan-pin-malformed", name) for name in (
    "not-a-list", "a-number", "short-commit", "short-digest",
    "another-product", "no-owner", "no-source", "source-line-break",
    "a-number-commit")]
CASE_IDS += [("plan-pin-collides", name)
             for name in ("case-pair", "shape", "variable-pair")]


def test_every_case_is_asked(cases):
    """The table below names every case the builders above make."""
    assert sorted(CASE_IDS) == sorted((code, name) for code, built
                                      in cases.items() for name in built)


@pytest.mark.parametrize("code, name", CASE_IDS,
                         ids=[f"{code}-{name}" for code, name in CASE_IDS])
def test_a_plan_whose_pin_execute_cannot_write_is_found_and_refused(
        adopter, monkeypatch, source_repo, tmp_path, glass, gh_env, cases,
        code, name):
    """`check` finds the pin, and `execute` refuses it with `check`'s own
    findings before any leg remote exists; the finding names the `plan` that
    records the pin whole, and neither command runs `gh`. Whatever the plan
    holds, nothing of it reaches the terminal raw: no ESC, and no line the
    plan's text began."""
    block, said = cases[code][name]
    plan = planned(source_repo, tmp_path, PLANNED)
    with_pins(plan, block)
    checked = run_script(ADOPT, "check", "--plan", str(plan), env=gh_env)
    assert checked.returncode == 1, checked.stdout + checked.stderr
    lines = [line for line in checked.stderr.splitlines()
             if line.startswith(f"FINDING {code}: ")]
    assert len(lines) == 1, checked.stderr
    assert lines[0].startswith(f"FINDING {code}: {said}"), lines[0]
    assert ("re-run `plan`" in lines[0]), lines[0]
    assert "\x1b" not in checked.stderr + checked.stdout, checked.stderr
    assert not [line for line in checked.stderr.splitlines()
                if line.startswith(("REFUSED forged", "forged"))], \
        checked.stderr
    refusal = refused_before_any_leg(adopter, monkeypatch, plan, tmp_path)
    assert refusal.code == code
    assert gh_calls(gh_env) == ""


# --- a commit or a digest edited after `plan` read them (#449) ---------------
#
# `check` held a pin's commit and digest to the form `plan` writes them in and
# to nothing else, so a commit or a digest edited into the plan after `plan`
# read them checked ok, `execute` said `adoption verified`, and the root's own
# `validate-pins.py` found `neutral-pin-digest-mismatch` on its first run. The
# comment `plan` writes above `pins:` says such an edit is one nobody read,
# and nothing held it. Where the clone `plan` read the digest from is still
# on this machine, `check` now recomputes the digest there at the plan's
# commit, with `plan`'s own reader and no network: a digest that differs, or
# a commit the clone cannot answer for, is a finding `execute` refuses before
# any leg exists. Where the clone is gone, or `gh api` read the digest, a NOTE
# says it was not rechecked, and `gh` is never asked.

PIN_DIGEST_MISMATCH = "plan-pin-digest-mismatch"
PIN_SOURCE_UNREADABLE = "plan-pin-source-unreadable"
#: How `check` names the one pin these plans hold.
ENTRY = "`pins:` entry 1 ('openGlass')"
#: Where every NOTE about a pin `check` did not recheck says it is.
NOT_RECHECKED = f"NOTE {ENTRY}: digest NOT rechecked here: "
GATE_RECOMPUTES = ("The root's own `validate-pins.py` recomputes it wherever "
                   "it can read the product.")
#: A commit the stand-in does not hold.
NOT_IN_THE_CLONE = "c0ffee" * 6 + "c0ff"
#: How `plan-pin-source-unreadable` says both causes and each way out.
WAYS_OUT = ("Either the commit was edited after `plan` read it, or that path "
            "no longer holds the clone `plan` read it in: run `check` where "
            "`plan` ran, or `git fetch` in that clone, or re-run `plan`")


@pytest.fixture
def recorded_clone(tmp_path, glass) -> Path:
    """A copy of the stand-in: the clone a pin below records that `plan`
    read its digest from, so that a test can delete it."""
    clone = tmp_path / "openGlass-clone"
    shutil.copytree(glass[0], clone, symlinks=True)
    return clone


def read_from(clone: Path, commit: str, digest: str) -> str:
    """`pins:` holding one pin as `plan --pin-source <clone>` records it,
    with `commit` and `digest` in place of what `plan` read; the path is
    quoted as the plan quotes it, so a Windows drive's backslashes stay
    the path's."""
    recorded = double_quoted(f"local-clone ({clone})")[1:-1]
    return "pins:\n" + pin_entry(commit=commit, digest=digest, source=recorded)


def pin_notes(result: subprocess.CompletedProcess) -> list[str]:
    """`check`'s lines about whether it recomputed a pin's digest."""
    return [line for line in result.stdout.splitlines()
            if line.startswith(f"NOTE {ENTRY}")]


def edits(glass) -> dict:
    """`(commit, digest, the finding's code, what the clone recomputes)` for
    each edit: the commit moved to the stand-in's other commit, the digest
    moved to that commit's, the first upper-cased, and a commit the clone
    does not hold, which it recomputes nothing at."""
    path, first, second = glass
    at_first, at_second = tree_digest(path, first), tree_digest(path, second)
    return {
        "commit": (second, at_first, PIN_DIGEST_MISMATCH, at_second),
        "digest": (first, at_second, PIN_DIGEST_MISMATCH, at_first),
        "commit-upper": (second.upper(), at_first, PIN_DIGEST_MISMATCH,
                         at_second),
        "commit-absent": (NOT_IN_THE_CLONE, at_first, PIN_SOURCE_UNREADABLE,
                          None),
    }


@pytest.mark.parametrize("edit", ["commit", "digest", "commit-upper",
                                  "commit-absent"])
def test_a_pin_edited_after_plan_is_found_and_refused(
        adopter, monkeypatch, source_repo, tmp_path, glass, gh_env,
        recorded_clone, edit):
    """The clone `plan` read the digest from is still here, so `check`
    recomputes it at the plan's commit and names the pin, and `execute`
    refuses it with `check`'s own finding before any leg remote exists; the
    finding names the `plan` that records the pin whole, and nothing runs
    `gh`."""
    commit, digest, code, recomputed = edits(glass)[edit]
    plan = planned(source_repo, tmp_path, PLANNED)
    with_pins(plan, read_from(recorded_clone, commit, digest))
    checked = run_script(ADOPT, "check", "--plan", str(plan), env=gh_env)
    assert checked.returncode == 1, checked.stdout + checked.stderr
    lines = [line for line in checked.stderr.splitlines()
             if line.startswith("FINDING ")]
    assert len(lines) == 1, checked.stderr
    assert lines[0].startswith(f"FINDING {code}: {ENTRY} records `commit: "
                               f"{commit.lower()}`"), lines[0]
    if recomputed:
        assert (f"`tree_sha256: {digest}`, and the clone `plan` read the "
                f"digest from, {recorded_clone}, recomputes {recomputed} at "
                "that commit") in lines[0], lines[0]
    else:
        assert (f"`, and the clone its `digest_source:` names cannot answer "
                f"for it: {recorded_clone} could not answer for "
                f"opensoft/openGlass @ {commit}: ") in lines[0], lines[0]
        assert WAYS_OUT in lines[0], lines[0]
    assert lines[0].endswith("re-run `plan` with `--pin opensoft/openGlass@"
                             "<40 hex commit>`, which reads the digest there "
                             "(from `--pin-source <clone>` with no network, "
                             "or `gh api`) and records both, as "
                             "`scaffold-project.py --pin` takes it."), lines[0]
    assert pin_notes(checked) == [], checked.stdout
    refusal = refused_before_any_leg(adopter, monkeypatch, plan, tmp_path)
    assert refusal.code == code
    assert gh_calls(gh_env) == ""


@pytest.mark.parametrize("upper", [
    pytest.param(False, id="another-commit-whole"),
    pytest.param(True, id="upper-cased"),
])
def test_a_pin_the_clone_recomputes_checks_ok(adopter, source_repo, tmp_path,
                                             glass, gh_env, recorded_clone,
                                             upper):
    """The controls. A commit and a digest both moved to the stand-in's
    other commit are a pin of that commit, which the clone recomputes, so
    it is the pin `execute` writes; and an upper-cased pin is the same pin.
    `check` says each digest recomputes, and nothing else about it."""
    path, first, second = glass
    commit = first if upper else second
    digest = tree_digest(path, commit)
    typed = (commit.upper(), digest.upper()) if upper else (commit, digest)
    plan = planned(source_repo, tmp_path, PLANNED)
    with_pins(plan, read_from(recorded_clone, *typed))
    checked = run_script(ADOPT, "check", "--plan", str(plan), env=gh_env)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert pin_notes(checked) == [
        f"NOTE {ENTRY}: digest recomputes at {commit[:12]} in the clone "
        f"`plan` read it from, {recorded_clone}."], checked.stdout
    assert "not read again here" not in checked.stdout, checked.stdout
    recorded = adopter._recorded_pins(adopter.Plan.load(plan))
    assert recorded["openGlass"]["PIN_COMMIT"] == commit
    assert recorded["openGlass"]["PIN_TREE_SHA256"] == digest
    assert gh_calls(gh_env) == ""


def test_a_pin_whose_clone_is_gone_is_said_not_rechecked(source_repo,
                                                          tmp_path, glass,
                                                          gh_env,
                                                          recorded_clone):
    """What (b) cannot see: the commit edited, and the clone `plan` read the
    digest from deleted. `check` reads no network for a pin, so it says, in
    one NOTE, that the digest was not rechecked and where it is, and the
    plan checks ok."""
    path, first, second = glass
    plan = planned(source_repo, tmp_path, PLANNED)
    with_pins(plan, read_from(recorded_clone, second,
                              tree_digest(path, first)))
    rmtree(recorded_clone)
    checked = run_script(ADOPT, "check", "--plan", str(plan), env=gh_env)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert pin_notes(checked) == [
        f"{NOT_RECHECKED}the clone `plan` read it from is not at "
        f"{recorded_clone}. {GATE_RECOMPUTES}"], checked.stdout
    assert gh_calls(gh_env) == ""


@pytest.mark.parametrize("source, why", [
    pytest.param("gh-api-tree-recursive",
                 "`plan` read it with `gh api`, and `check` reads no network",
                 id="gh-api"),
    pytest.param("read by hand",
                 "`digest_source: read by hand` names no clone `plan` read it "
                 "from", id="no-clone-named"),
])
def test_a_pin_read_from_no_clone_is_said_not_rechecked(source_repo,
                                                        tmp_path, glass,
                                                        gh_env, source, why):
    """A digest `gh api` read is never asked of the forge again: `check`
    reads no network, so `gh` is not run, and one NOTE says so. A
    `digest_source:` naming no clone at all is said the same way."""
    path, first, second = glass
    plan = planned(source_repo, tmp_path, PLANNED)
    with_pins(plan, "pins:\n" + pin_entry(commit=second,
                                          digest=tree_digest(path, first),
                                          source=source))
    checked = run_script(ADOPT, "check", "--plan", str(plan), env=gh_env)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert pin_notes(checked) == [
        f"{NOT_RECHECKED}{why}. {GATE_RECOMPUTES}"], checked.stdout
    assert gh_calls(gh_env) == ""


def test_a_pin_read_from_a_partial_clone_is_said_not_rechecked(
        source_repo, tmp_path, glass, gh_env, recorded_clone):
    """A partial clone (`git clone --filter`) fetches what it lacks from its
    promisor remote, so `git` there could reach the forge: `check` reads no
    network, and says in one NOTE that the digest was not rechecked. The
    copy is marked partial by its config alone; nothing is fetched."""
    path, first, second = glass
    for setting in (("core.repositoryformatversion", "1"),
                    ("extensions.partialClone", "origin"),
                    ("remote.origin.promisor", "true")):
        git("config", *setting, cwd=recorded_clone)
    plan = planned(source_repo, tmp_path, PLANNED)
    with_pins(plan, read_from(recorded_clone, second,
                              tree_digest(path, first)))
    checked = run_script(ADOPT, "check", "--plan", str(plan), env=gh_env)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert pin_notes(checked) == [
        f"{NOT_RECHECKED}the clone at {recorded_clone} is a partial clone "
        "(`git clone --filter`), whose `git` fetches what it lacks over the "
        f"network, and `check` reads no network. {GATE_RECOMPUTES}"], \
        checked.stdout
    assert gh_calls(gh_env) == ""


@pytest.mark.parametrize("edited", [
    pytest.param(False, id="recomputes"),
    pytest.param(True, id="commit-edited"),
])
def test_a_relative_clone_is_read_from_where_check_runs(source_repo,
                                                        tmp_path, glass,
                                                        gh_env,
                                                        recorded_clone,
                                                        edited):
    """`plan` records `--pin-source` as typed, so a relative path names the
    clone from the directory `plan` ran in. `check` reads it from the one it
    runs in, here the directory holding the copy, and the line naming the
    clone says where that is: the NOTE that its digest recomputes, or the
    finding that it does not."""
    path, first, second = glass
    name = recorded_clone.name
    plan = planned(source_repo, tmp_path, PLANNED)
    with_pins(plan, "pins:\n" + pin_entry(commit=second if edited else first,
                                          digest=tree_digest(path, first),
                                          source=f"local-clone ({name})"))
    checked = run_script(ADOPT, "check", "--plan", str(plan), cwd=tmp_path,
                         env=gh_env)
    assert checked.returncode == int(edited), checked.stdout + checked.stderr
    said = [line for line in (checked.stderr if edited else checked.stdout)
            .splitlines() if line.startswith(("FINDING ", f"NOTE {ENTRY}"))]
    assert len(said) == 1, checked.stdout + checked.stderr
    assert f"from, {name} (read from this directory as " in said[0], said[0]
    assert f"{os.sep}{name})" in said[0], said[0]
    assert gh_calls(gh_env) == ""


def test_the_issues_edit_is_found_until_the_clone_is_gone(
        adopter, monkeypatch, source_repo, tmp_path, glass, gh_env,
        recorded_clone):
    """#449's own path: `plan --pin openGlass@<A> --pin-source <clone>`,
    then the plan's `commit:` edited to B with A's digest left. `check`
    finds it and `execute` refuses it while the clone is there; once it is
    deleted, `check` passes with the NOTE, and the root's gate is what
    finds it."""
    path, first, second = glass
    plan = tmp_path / PLAN_NAME
    planned_run = plan_with(source_repo, plan, f"openGlass@{first}",
                            extra=("--pin-source", str(recorded_clone)),
                            env=gh_env)
    assert planned_run.returncode == 0, planned_run.stdout + planned_run.stderr
    for answered, leg in ANSWERS:
        resolve(plan, answered, leg)
    text = plan.read_bytes().decode(UTF8)
    assert text.count(f'commit: "{first}"') == 1, text
    plan.write_bytes(text.replace(f'commit: "{first}"', f'commit: "{second}"')
                     .encode(UTF8))
    found = findings(plan)
    assert [code for code, _ in found] == [PIN_DIGEST_MISMATCH], found
    refused_before_any_leg(adopter, monkeypatch, plan, tmp_path)
    rmtree(recorded_clone)
    assert findings(plan) == []
    assert gh_calls(gh_env) == ""


@pytest.mark.parametrize("kept, aside", [
    pytest.param(PIN_FILE, "", id="same-case"),
    pytest.param("contracts/OpenGlass-pin.yaml",
                 shape_materialize.CASE_ASIDE, id="folded"),
])
def test_a_kept_path_where_the_pin_is_written_is_found_and_refused(
        adopter, monkeypatch, tmp_path, glass, kept, aside):
    """The materializer writes a shape file the root holds beside it, under
    `shape/`; for a pin that is the wrong file, because the root's own
    `validate-pins.py` reads `contracts/<product>-pin.yaml`, the source's.
    The source's `contracts/` answered `root` keeps such a file there."""
    source = make_source_repo(tmp_path / "Thing", tree={
        **SYNTHETIC_TREE, kept: "schema_version: 1\n"})
    plan = planned(source, tmp_path, {**PLANNED, "contracts/": "root"})
    with_pins(plan, "pins:\n" + a_good_pin(glass))
    found = findings(plan)
    assert [code for code, _ in found] == ["plan-root-holds-pin"], found
    assert found[0][1] == (
        f"the plan keeps the file `{kept}` in the assembly root under the "
        f"entry `contracts/`, at `{PIN_FILE}`{aside}, where `execute` writes "
        "the pin the plan declares on `openGlass`. The shape's pin would be "
        "written beside it, under `shape/`, and the root's own "
        "`validate-pins.py` would read the source's file as that pin: send "
        "`contracts/` to a leg, `drop` it, or rename it in the source and "
        "re-run `plan`.")
    refused_before_any_leg(adopter, monkeypatch, plan, tmp_path)


def test_a_leg_moved_over_a_pins_file_in_the_plan_is_found(
        adopter, monkeypatch, source_repo, tmp_path, glass):
    """The plan's mount path is edited after `plan` asked it: `check` asks
    again, with each pin's file among the shape's paths."""
    plan = planned(source_repo, tmp_path, PLANNED)
    with_pins(plan, "pins:\n" + a_good_pin(glass))
    text = plan.read_bytes().decode(UTF8)
    plan.write_bytes(text.replace("  spec_path: spec\n",
                                  f"  spec_path: {PIN_FILE}\n", 1)
                     .encode(UTF8))
    found = findings(plan)
    assert [code for code, _ in found] == ["plan-leg-path-collides"], found
    assert found[0][1].startswith(
        f"legs.spec_path '{PIN_FILE}' is `{PIN_FILE}`."), found
    refused_before_any_leg(adopter, monkeypatch, plan, tmp_path)


def test_a_plan_with_a_whole_pin_checks_ok(source_repo, tmp_path, glass,
                                           gh_env):
    """The control for every case above: the same plan with the pin as
    `plan` writes it checks ok, and says the file it will write. Its
    `digest_source:` names the clone `openGlass`, a path relative to a
    directory this run is not in, so `check` says in one NOTE that the
    digest was not rechecked, and where it is (#273's review, S3: `check`
    and `execute` read no network for a pin, by design; #449)."""
    plan = planned(source_repo, tmp_path, PLANNED)
    with_pins(plan, "pins:\n" + a_good_pin(glass))
    checked = run_script(ADOPT, "check", "--plan", str(plan), env=gh_env)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert f"  write {PIN_FILE}: opensoft/openGlass @ {glass[1][:12]}" \
        in checked.stdout
    assert pin_notes(checked) == [
        f"{NOT_RECHECKED}the clone `plan` read it from is not at openGlass "
        f"(read from this directory as {os.path.abspath('openGlass')}). "
        f"{GATE_RECOMPUTES}"], checked.stdout
    assert gh_calls(gh_env) == ""


def test_a_plan_with_no_pin_says_nothing_of_pins(source_repo, tmp_path,
                                                 gh_env):
    """What `check` says of a pin's digest is said of pins, and only where
    there is one."""
    plan = planned(source_repo, tmp_path, PLANNED)
    checked = run_script(ADOPT, "check", "--plan", str(plan), env=gh_env)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert "  write contracts/" not in checked.stdout
    assert "rechecked" not in checked.stdout
    assert "digest recomputes" not in checked.stdout


def test_an_upper_cased_hand_edit_is_written_lower_cased(adopter, source_repo,
                                                         tmp_path, glass,
                                                         gh_env):
    """`plan` records a commit and a digest lower-cased, as `parse_pin`
    reads the commit and `tree_digest` spells the digest. One edited into
    the plan upper-cased is the same pin and passes `check`; `execute`
    writes it as `plan` would have, lower-cased, so the pin file the
    scaffold would write for it is the one written (#273's review, N3)."""
    path, commit, _ = glass
    digest = tree_digest(path, commit)
    plan = planned(source_repo, tmp_path, PLANNED)
    with_pins(plan, "pins:\n" + pin_entry(commit=commit.upper(),
                                          digest=digest.upper()))
    checked = run_script(ADOPT, "check", "--plan", str(plan), env=gh_env)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert (f"  write {PIN_FILE}: opensoft/openGlass @ {commit[:12]} tree "
            f"{digest[:12]}… (local-clone (openGlass))") in checked.stdout
    recorded = adopter._recorded_pins(adopter.Plan.load(plan))
    assert recorded["openGlass"]["PIN_COMMIT"] == commit
    assert recorded["openGlass"]["PIN_TREE_SHA256"] == digest


def test_a_submodule_kept_where_the_pin_is_written_is_said_once(
        adopter, monkeypatch, tmp_path, glass):
    """A submodule the root keeps is `plan-submodule-root` (#166), wherever
    it is, and the pin finding about a path kept where the pin is written
    does not say it a second time, as the shape's own files do not (#273's
    review, N3: the gitlink filter)."""
    source = make_source_repo(tmp_path / "Thing")
    head = git("rev-parse", "HEAD", cwd=source).stdout.strip()
    git("update-index", "--add", "--cacheinfo", f"160000,{head},{PIN_FILE}",
        cwd=source)
    as_human("commit", "-qm", "a submodule where the pin is written",
             cwd=source)
    plan = planned(source, tmp_path, {**PLANNED, "contracts/": "root"})
    with_pins(plan, "pins:\n" + a_good_pin(glass))
    found = findings(plan)
    assert [code for code, _ in found] == ["plan-submodule-root"], found
    refused_before_any_leg(adopter, monkeypatch, plan, tmp_path)


@needs_filter_repo
def test_execute_refuses_an_old_plans_name_before_any_remote(source_repo,
                                                             tmp_path,
                                                             gh_env):
    """The issue's own path, as a person runs it: an old plan's name-only
    pin is refused by `execute` itself, and nothing is created."""
    plan = planned(source_repo, tmp_path, PLANNED)
    with_pins(plan, "pins: [openGlass]\n")
    remotes = tmp_path / "remotes"
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / "work"), env=gh_env)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED plan-pin-unrecorded" in result.stderr
    assert "no leg repository was created" in result.stderr
    assert not remotes.exists()
    assert gh_calls(gh_env) == ""


# --- one implementation ------------------------------------------------------

def test_both_tools_read_a_pin_with_one_implementation(adopter):
    """The scaffold's pin functions moved beside the materializer and both
    tools call them there (#273): no second copy to drift."""
    module_spec = importlib.util.spec_from_file_location("scaffold_pins",
                                                         SCAFFOLD)
    scaffold = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(scaffold)
    for name in ("declared_pin_values", "declared_pin_products"):
        assert getattr(scaffold, name) is getattr(shape_materialize, name)
        assert getattr(adopter, name) is getattr(shape_materialize, name)
    assert scaffold._refuse_colliding_pins \
        is shape_materialize.refuse_colliding_pins
    assert adopter.refuse_colliding_pins \
        is shape_materialize.refuse_colliding_pins
    assert adopter.pin_collisions is shape_materialize.pin_collisions
    assert not hasattr(adopter, "_checked_pin_name")


@pytest.mark.parametrize("first, second", [
    pytest.param("openß", "openss", id="sharp-s"),
    pytest.param("openſ", "opens", id="long-s"),
])
def test_two_pins_are_one_product_by_their_pin_file_not_a_casefold(first,
                                                                   second):
    """#275's fix round decides "the same product" by the pin file's name,
    `repo_shape.pin_product_key` (`lower()`), as `validate-pins.py` does;
    both tools ask it here. `casefold()` folds `ß` to `ss` and `ſ` to `s`,
    which `lower()` does not, so the two names below are two pin files and
    one `SHAPE_PIN_SOURCE_<PRODUCT>`: one collision, each pin named once.
    Keyed by a casefold, each was named twice. No `--pin` or recorded
    `pins:` entry `PIN_ARG_RE` admits can spell either, so the function is
    asked directly."""
    variable = pin_source_env_name(first)
    assert variable == pin_source_env_name(second)
    assert shape_materialize.neutral_pin_path(first) \
        != shape_materialize.neutral_pin_path(second)
    typed = [("`pins:` entry 1", first), ("`pins:` entry 2", second)]
    assert shape_materialize.pin_variable_collisions(typed) == [
        f"`pins:` entry 1 and `pins:` entry 2 name the products `{first}` "
        f"and `{second}`, and one variable, `{variable}`, names the local "
        "checkout of each: it cannot say which it holds."]

