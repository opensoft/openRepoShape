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
and an `execute` refusal before any leg exists.

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

from conftest import (ADOPT, FILE_PROTOCOL, REPO, SCAFFOLD, SYNTHETIC_TREE,
                      WINDOWS_SKIP, findings, git, make_source_repo, planned,
                      refused_before_any_leg, resolve, run_script)

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402
from repo_shape import load_yaml, tree_digest  # noqa: E402

UTF8 = "utf-8"
PROJECT = "MedxGlass"
ORG = "testorg"
BRANCH = "adopt/three-repo-shape"
ANSWERS = (("examples/", "spec"), (".claude/", "root"),
           ("release.yaml", "root"))
#: What `conftest.planned` answers, for a plan written with no pin.
PLANNED = dict(ANSWERS)
PIN_FILE = "contracts/openglass-pin.yaml"
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
    plan = base / "adoption-plan.yaml"
    planned_run = plan_with(source, plan, f"{spelling}@{commit}",
                            extra=("--pin-source", str(readable)), env=env)
    assert planned_run.returncode == 0, planned_run.stderr + planned_run.stdout
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    shutil.rmtree(readable)
    checked = run_script(ADOPT, "check", "--plan", str(plan), env=env)
    executed = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                          "--local-remote-dir", str(base / "remotes"),
                          "--work-dir", str(base / "work"), env=env)
    clone = base / "clone" / PROJECT
    if executed.returncode == 0:
        proc = subprocess.run(
            ["git", *FILE_PROTOCOL, "clone", "-q", "--recurse-submodules",
             "-b", BRANCH, str(source), str(clone)],
            capture_output=True, check=False)
        assert proc.returncode == 0, proc.stderr.decode(UTF8, "replace")
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
    "old-plan-name", "old-plan-owner", "no-commit", "no-digest", "both-blank")]
CASE_IDS += [("plan-pin-malformed", name) for name in (
    "not-a-list", "a-number", "short-commit", "short-digest",
    "another-product", "no-owner", "no-source")]
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
    records the pin whole, and neither command runs `gh`."""
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
    refusal = refused_before_any_leg(adopter, monkeypatch, plan, tmp_path)
    assert refusal.code == code
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
    `plan` writes it checks ok, and says the file it will write."""
    plan = planned(source_repo, tmp_path, PLANNED)
    with_pins(plan, "pins:\n" + a_good_pin(glass))
    checked = run_script(ADOPT, "check", "--plan", str(plan), env=gh_env)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert f"  write {PIN_FILE}: opensoft/openGlass @ {glass[1][:12]}" \
        in checked.stdout
    assert gh_calls(gh_env) == ""


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

