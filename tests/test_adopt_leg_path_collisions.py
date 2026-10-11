# SPDX-License-Identifier: Apache-2.0
"""A leg's mount path overlaps nothing the assembly root holds (#172).

#169 made a leg path canonical, and `--spec-path contracts` is canonical, so
on main at f25d805 it planned, `check` said `plan ok`, and `execute` made and
pushed both legs before it died staging the split: the shape's
`contracts/spec-pin.yaml` had been written INTO the mounted leg (`Pathspec
'contracts/spec-pin.yaml' is in submodule 'contracts'`). `--code-path
scripts`, `.github` and `shape` died the same way. `--code-path project.yaml`
ended `adoption verified`: the shape's manifest went beside the mount as
`shape/project.yaml`, and the doctor calls the assembly NOT A SHAPE ROOT. A
mount at a path the plan keeps in the root (`--spec-path src`, `src/` kept)
died at `git submodule add`, after both legs were pushed.

The rule: a mount path is refused when it EQUALS, CONTAINS or LIES INSIDE a
path the shape writes into the assembly root -- the materializer's own list,
plus `shape/`, where it writes its copy of a file the root already holds --
or a SOURCE PATH the plan keeps in the root, whatever the case. `plan`
refuses the first half, `check` reports both, `execute` refuses both before a
leg exists. A mount inside a kept directory that holds nothing at the mount
(`docs/spec`, `docs/` kept) overlaps no source path and still adopts, as it
does on main.

Everything but the end-to-end tests runs on a machine with no `git
filter-repo`: `execute`'s probe for it is answered, because every refusal
under test comes before the tool would be used.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import (ADOPT, REPO, SYNTHETIC_TREE, git, make_source_repo,
                      resolve, run_script, write_plan)

sys.path.insert(0, str(REPO / "scripts"))
from shape_materialize import PLACEHOLDER_RE  # noqa: E402
from shape_materialize import SHAPE_PIN as MATERIALIZER_SHAPE_PIN  # noqa: E402

#: What the end-to-end tests need and nothing else here does.
needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

PROJECT = "Northwind"
UTF8 = "utf-8"
REMOTES = "remotes"
WORK = "work"
ROLES = ("spec", "code")
SPLIT_BRANCH = "adopt/three-repo-shape"
#: Answered the way `test_adopt_plan.py` answers them, so `check` can pass.
ANSWERS = (("examples/", "spec"), (".claude/", "root"),
           ("release.yaml", "root"))

COLLIDES = "plan-leg-path-collides"
FINDING = f"FINDING {COLLIDES}: "
PLAN_REFUSAL = "REFUSED adopt-leg-path-collides"
CASE_ASIDE = " once case is ignored, as a macOS or Windows disk does"
CONTAINS, IS, INSIDE = "contains", "is", "is inside"
CONTRACTS, PROJECT_YAML, SHAPE_DIR = "contracts", "project.yaml", "shape"
DOCS_SPEC = "docs/spec"

#: `(role, value, relation, what it names)`: a path the shape writes, and how
#: the mount stands to it. One of each kind the coordinator and the issue
#: named: a directory the shape writes into, a FILE it writes, its copy
#: directory, a nested path, and a capital letter in the way.
SHAPE_CASES = [
    pytest.param("spec", CONTRACTS, CONTAINS,
                 "`contracts/spec-pin.yaml` and 3 more", id="contracts"),
    pytest.param("code", "scripts", CONTAINS,
                 "`scripts/validate-pins.py` and 4 more", id="scripts"),
    pytest.param("spec", ".github", CONTAINS,
                 "`.github/workflows/validate.yml`", id="dot-github"),
    pytest.param("spec", ".github/workflows", CONTAINS,
                 "`.github/workflows/validate.yml`", id="dot-github-nested"),
    pytest.param("code", PROJECT_YAML, IS, f"`{PROJECT_YAML}`",
                 id="project-yaml"),
    pytest.param("code", "AGENTS-shape.md", IS, "`AGENTS-shape.md`",
                 id="agents-shape"),
    pytest.param("spec", ".gitattributes", IS, "`.gitattributes`",
                 id="gitattributes"),
    pytest.param("spec", "contracts/shape-pin.yaml", IS,
                 "`contracts/shape-pin.yaml`", id="shape-pin"),
    pytest.param("code", "Makefile/code", INSIDE, "`Makefile`",
                 id="inside-a-shape-file"),
    pytest.param("spec", SHAPE_DIR, IS, f"`{SHAPE_DIR}`", id="shape-dir"),
    pytest.param("spec", "shape/spec", INSIDE, f"`{SHAPE_DIR}`",
                 id="inside-shape-dir"),
]

#: The same overlaps with a capital letter in the way: one directory on a
#: macOS or Windows disk, and said to be so.
CASE_ONLY = [
    pytest.param("Contracts", CONTAINS, id="contracts-capital"),
    pytest.param("PROJECT.YAML", IS, id="project-yaml-capitals"),
    pytest.param("Shape", IS, id="shape-dir-capital"),
]

#: Canonical paths that overlap nothing the shape writes. `legs/.github` is
#: the brief's question: neither inside `.github` nor around it, since the
#: shape writes `.github/workflows/validate.yml` at the ROOT. A sibling under
#: a directory the shape writes into (`scripts/spec`) shares a directory and
#: no path; `project` and `shapes` share only a prefix of a NAME.
CLEAR = ["spec", "code", "legs/spec", "impl/code", "legs/.github",
         "scripts/spec", "contracts/spec", ".github/spec", "Scripts/x",
         "project", "shapes", "shape-x", DOCS_SPEC, "README"]


@pytest.fixture(scope="module")
def adopter():
    """`adopt-project.py` loaded as a module, for the functions with no
    command line of their own."""
    module_spec = importlib.util.spec_from_file_location(
        "adopt_leg_path_collisions", ADOPT)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


@pytest.fixture
def no_filter_repo_probe(adopter, monkeypatch):
    """`cmd_execute` asks for `git filter-repo` first; every refusal here
    comes before the tool would be used, so the probe is answered."""
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    """One source and one ANSWERED plan against it, which `check` passes.
    `plan` and `check` only read the source; a test edits a copy."""
    root = tmp_path_factory.mktemp("collisions")
    source = make_source_repo(root / "Thing")
    plan = answered_plan(source, root / "adoption-plan.yaml")
    return {"source": source, "plan": plan}


def answered_plan(source: Path, out: Path, extra: tuple = ()) -> Path:
    written = write_plan(source, out, project=PROJECT, extra=extra)
    assert written.returncode == 0, written.stderr + written.stdout
    for path, leg in ANSWERS:
        resolve(out, path, leg)
    return out


def set_leg_path(plan: Path, role: str, value: str) -> None:
    """`legs.<role>_path: <value>`, as a person editing the plan writes it."""
    text = plan.read_text(encoding=UTF8)
    pattern = re.compile(rf"^  {role}_path: .*$", re.MULTILINE)
    assert pattern.search(text), f"no `{role}_path:` line in the plan"
    plan.write_text(pattern.sub(f"  {role}_path: {value}", text, count=1),
                    encoding=UTF8)


def keep_in_root(plan: Path, prefix: str) -> None:
    """Answer `root` for every entry at or under `prefix`, with a reason, as
    a person would; however `plan` grouped them."""
    text = plan.read_text(encoding=UTF8)
    entry = re.compile(r"^  - path: (?P<path>\S+)\n    leg: \S+\n",
                       re.MULTILINE)

    def answer(match: re.Match) -> str:
        path = match.group("path")
        if path.rstrip("/") != prefix.rstrip("/") and not path.startswith(
                prefix.rstrip("/") + "/"):
            return match.group(0)
        return (f"  - path: {path}\n    leg: root\n"
                "    resolution: \"kept in the root by the test\"\n")

    edited = entry.sub(answer, text)
    assert edited != text, f"no entry at or under {prefix} in the plan"
    plan.write_text(edited, encoding=UTF8)


def edited_copy(world, tmp_path: Path) -> Path:
    copy = tmp_path / "plan.yaml"
    shutil.copy(world["plan"], copy)
    return copy


def check(plan: Path):
    return run_script(ADOPT, "check", "--plan", str(plan))


def findings_of(result) -> list[str]:
    return [line for line in result.stderr.splitlines()
            if line.startswith(FINDING)]


def commit_tree_entry(source: Path, mode: str, path: str, oid: str) -> None:
    """Put `path` into the source's TREE with `mode` (a symlink or a
    gitlink), and commit it. Nothing is made on the disk: `plan` and `check`
    read the tree, so this runs where a symlink cannot be made."""
    git("update-index", "--add", "--cacheinfo", f"{mode},{oid},{path}",
        cwd=source)
    git("-c", "user.name=t", "-c", "user.email=t@t.invalid", "commit", "-qm",
        f"add {path}", cwd=source)


def execute_args(tmp_path: Path, plan: Path) -> Namespace:
    """What `main` hands `cmd_execute`: `--yes`, a local remote directory
    that does not exist yet, and a work directory."""
    return Namespace(plan=str(plan), source=None,
                     local_remote_dir=tmp_path / REMOTES, allow_empty_leg=[],
                     yes=True, work_dir=tmp_path / WORK)


def no_leg_was_created(tmp_path: Path, source: Path) -> None:
    """What a refused run leaves undone: the directory the legs would have
    gone in was never made, and nothing else was."""
    assert not (tmp_path / REMOTES).exists(), (
        "not even the directory the legs go in")
    nothing_else_was_made(tmp_path, source)


def nothing_else_was_made(tmp_path: Path, source: Path) -> None:
    """No leg was cloned for extraction, and the source has no split
    branch."""
    for role in ROLES:
        assert not (tmp_path / WORK / f"{PROJECT}-{role}").exists()
    assert git("branch", "--list", SPLIT_BRANCH, cwd=source).stdout == ""


# --- the shape's paths are the materializer's own -------------------------

def test_the_paths_refused_are_the_paths_the_materializer_writes(adopter,
                                                                 tmp_path):
    """NO SECOND LIST. Materialized into an empty directory, the assembly
    root holds exactly `assembly_root_paths()`, in the order written: a file
    the shape gains is a path the rule refuses, without anyone editing it."""
    template = REPO / "templates" / "assembly-root"
    values = {name[2:-2]: "x" for path in template.rglob("*") if path.is_file()
              for name in PLACEHOLDER_RE.findall(path.read_text(UTF8))}
    materialized = adopter.materialize_assembly_root(REPO, tmp_path, values)
    assert materialized.collisions == []
    assert tuple(materialized.written) == adopter.assembly_root_paths()


def test_every_path_the_shape_writes_is_refused_as_a_mount(adopter):
    for path in adopter.assembly_root_paths():
        collisions = adopter.leg_path_collisions((("--code-path", path),))
        assert len(collisions) == 1, (path, collisions)
        assert collisions[0].startswith(f"--code-path {path!r} is `{path}`")


def test_plan_predicts_a_collision_for_every_path_the_shape_writes(adopter):
    """`plan`'s follow-ups read the same list: a source that keeps any one of
    those paths in the root is told, before `execute`, that the shape's copy
    goes beside it. The list `_predict_collisions` kept itself lacked
    `contracts/shape-pin.yaml`, which `execute` writes beside a kept one all
    the same."""
    for path in adopter.assembly_root_paths():
        kept = adopter.Entry(path, adopter.Verdict(
            "root", "test", "kept by the test", "high"), 1, 1)
        assert adopter._predict_collisions([kept]) == [
            adopter.collision_follow_up(path, f"{SHAPE_DIR}/{path}")], path


def test_adopt_names_the_shape_pin_as_the_materializer_does(adopter):
    """#167 named `contracts/shape-pin.yaml` in adopt-project.py, and #172
    named it again in the materializer, which `assembly_root_paths` reads.
    The two stay apart so #167's lines stay as they landed; this holds them
    to one spelling."""
    assert adopter.SHAPE_PIN == MATERIALIZER_SHAPE_PIN


# --- the rule ------------------------------------------------------------

@pytest.mark.parametrize("role, value, relation, named", SHAPE_CASES)
def test_a_path_the_shape_writes_is_a_collision(adopter, role, value,
                                                relation, named):
    what = f"--{role}-path"
    collisions = adopter.leg_path_collisions(((what, value),))
    assert len(collisions) == 1, collisions
    assert collisions[0].startswith(f"{what} {value!r} {relation} {named}.")
    assert CASE_ASIDE not in collisions[0]
    assert collisions[0].endswith("choose another path for the leg.")


@pytest.mark.parametrize("value, relation", CASE_ONLY)
def test_a_collision_that_holds_only_without_case_says_so(adopter, value,
                                                          relation):
    collisions = adopter.leg_path_collisions((("--spec-path", value),))
    assert len(collisions) == 1, collisions
    assert f"{value!r} {relation} `" in collisions[0]
    assert CASE_ASIDE in collisions[0]


@pytest.mark.parametrize("value", CLEAR)
def test_a_path_that_overlaps_nothing_the_shape_writes_is_clear(adopter,
                                                                value):
    assert adopter.leg_path_collisions((("--spec-path", value),)) == []


def test_the_shape_directory_names_what_execute_writes_there(adopter):
    sentence, = adopter.leg_path_collisions((("--spec-path", SHAPE_DIR),))
    assert ("`execute` writes there the shape's copy of each of its files "
            "the assembly root already holds (`README.md` as "
            "`shape/README.md`)") in sentence


def test_both_legs_are_asked(adopter):
    collisions = adopter.leg_path_collisions(
        (("--spec-path", CONTRACTS), ("--code-path", PROJECT_YAML)))
    assert [c.split()[0] for c in collisions] == ["--spec-path",
                                                  "--code-path"]


# --- `_leg_findings` is never without the tree (the #166 merge) ------------

#: A source path a `leg: root` entry keeps, as `Source.tree()` lists it.
KEPT_ROW = ("src/app/main.py", "100644", "0" * 40, 1)


def adoption_plan(adopter, legs: dict):
    """An adoption plan in memory that keeps `src/` in the root."""
    return adopter.Plan(Path("adoption-plan.yaml"), {
        "kind": "adoption-plan", "mode": "in-place", "legs": legs,
        "paths": [{"path": "src/", "leg": "root"}]})


def test_leg_findings_reads_the_tree_it_is_given(adopter):
    plan = adoption_plan(adopter, {"spec_path": "src", "code_path": "code"})
    found = adopter._leg_findings(plan, [KEPT_ROW])
    assert [f.split(":")[0] for f in found] == [f"FINDING {COLLIDES}"], found
    assert adopter._leg_findings(plan, []) == []


def test_leg_findings_takes_no_default_tree(adopter):
    """#166's `_entry_findings` called `_leg_findings(plan)`. With a default
    tree that merge ran, and a mount at a path the plan keeps in the root
    checked ok again (the review's P3-1). A lost argument now raises."""
    plan = adoption_plan(adopter, {"spec_path": "src", "code_path": "code"})
    with pytest.raises(TypeError):
        adopter._leg_findings(plan)


@pytest.mark.parametrize("spec_path", [
    pytest.param("src", id="canonical"),
    pytest.param("src/", id="not-canonical"),
])
def test_none_is_no_tree_and_is_refused_beside_mount_paths(adopter,
                                                           spec_path):
    """`None` is the placement plan's "no source tree". Beside a `legs:`
    mapping it raises, rather than reading as a source that keeps nothing in
    the root: whether or not the paths are canonical, so whether or not the
    tree would have been read."""
    plan = adoption_plan(adopter, {"spec_path": spec_path,
                                   "code_path": "code"})
    with pytest.raises(TypeError, match="needs the source tree"):
        adopter._leg_findings(plan, None)


# --- `plan` -----------------------------------------------------------------

@pytest.mark.parametrize("role, value, relation, named", SHAPE_CASES)
def test_plan_refuses_a_path_the_shape_writes_and_writes_nothing(
        world, tmp_path, role, value, relation, named):
    out = tmp_path / "plan.yaml"
    result = write_plan(world["source"], out, project=PROJECT,
                        extra=(f"--{role}-path", value))
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(
        f"{PLAN_REFUSAL}: --{role}-path {value!r} {relation} {named}.")
    assert "Remediation: nothing here picks a path for you" in result.stderr
    assert not out.exists(), "a refused plan must leave no file behind"


#: Why everything at or under `shape/` is refused, said by the finding and by
#: the remediation alike.
RESERVED = ("`shape/` is reserved for the shape's own copies of files the "
            "root already holds")


def test_shape_dir_is_reserved_even_where_no_copy_would_land(world,
                                                             tmp_path):
    """The review's P3-3: on main `--spec-path shape/x` adopted, verified and
    bootstrapped, because no copy of the shape's landed beside it. The policy
    stays -- everything at or under `shape/` is refused, so whether a path
    there collides never depends on which files a source holds -- and the
    finding and the remediation both say why: the directory is reserved."""
    result = write_plan(world["source"], tmp_path / "plan.yaml",
                        project=PROJECT, extra=("--spec-path", "shape/x"))
    assert result.returncode == 2, result.stdout + result.stderr
    detail, _, remediation = result.stderr.partition("\nRemediation: ")
    assert detail.startswith(
        f"{PLAN_REFUSAL}: --spec-path 'shape/x' is inside `shape`.")
    assert f"{RESERVED}, so no leg is mounted at or under it" in detail
    assert f"{RESERVED}, so a leg path there is refused" in remediation


def test_plan_refuses_dot_github_and_still_writes_legs_dot_github(world,
                                                                  tmp_path):
    """The brief's question, answered both ways: `.github` holds the shape's
    workflow and is refused; `legs/.github` is neither inside it nor around
    it (the shape writes `.github/` at the ROOT), so it is written exactly as
    given and, answered, `check` passes it."""
    refused = write_plan(world["source"], tmp_path / "refused.yaml",
                         project=PROJECT, extra=("--spec-path", ".github"))
    assert refused.returncode == 2 and PLAN_REFUSAL in refused.stderr
    out = answered_plan(world["source"], tmp_path / "plan.yaml",
                        extra=("--spec-path", "legs/.github"))
    assert "\n  spec_path: legs/.github\n" in out.read_text(UTF8)
    checked = check(out)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert "plan ok" in checked.stdout


def test_plan_refuses_a_bad_spelling_before_it_asks_about_collisions(
        world, tmp_path):
    """`shape/` is #169's refusal, not this one: compared as it stands it
    would read as inside `shape`, a statement about a path nobody gave."""
    result = write_plan(world["source"], tmp_path / "plan.yaml",
                        project=PROJECT, extra=("--spec-path", "shape/"))
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(
        "REFUSED adopt-bad-leg-path: --spec-path is 'shape/'")
    assert PLAN_REFUSAL not in result.stderr


def test_a_path_the_plan_keeps_in_the_root_is_checks_to_find(world,
                                                             tmp_path):
    """`plan` refuses only the shape's paths: the plan's answers are edited
    after it writes them. `.specify/` is one `plan` itself keeps in the
    root; `plan` notes it (below), and `check` finds it."""
    out = answered_plan(world["source"], tmp_path / "plan.yaml",
                        extra=("--spec-path", ".specify"))
    findings = findings_of(check(out))
    assert len(findings) == 1, findings
    assert findings[0].startswith(
        f"{FINDING}legs.spec_path '.specify' contains the file "
        "`.specify/scripts/plan.sh` and 1 more. The plan keeps them in the "
        "assembly root under the entry `.specify/`")


#: How `plan` starts a note about a leg path over a path it keeps itself.
PLAN_NOTE = "NOTE --spec-path "


def plan_notes(result) -> list[str]:
    return [line for line in result.stdout.splitlines()
            if line.startswith(PLAN_NOTE)]


def test_plan_notes_a_path_it_keeps_in_the_root_and_still_writes_the_plan(
        world, tmp_path):
    """The review's P3-2: `plan --spec-path .specify` exited 0 with nothing
    said, and `check` then rejected the plan for `plan`'s own `leg: root`.
    Now `plan` says so, in `check`'s words, and still writes the plan: the
    answer is the person's to change, so nothing is refused."""
    out = tmp_path / "plan.yaml"
    written = write_plan(world["source"], out, project=PROJECT,
                         extra=("--spec-path", ".specify"))
    assert written.returncode == 0, written.stdout + written.stderr
    assert out.exists(), "a note refuses nothing"
    note, = plan_notes(written)
    assert note.startswith(
        f"{PLAN_NOTE}'.specify' contains the file `.specify/scripts/plan.sh` "
        "and 1 more. The plan keeps them in the assembly root under the "
        "entry `.specify/`")
    assert f"`check` reports this as `{COLLIDES}`" in written.stdout
    for path, leg in ANSWERS:
        resolve(out, path, leg)
    finding, = findings_of(check(out))
    assert finding == FINDING + note[len("NOTE "):].replace(
        "--spec-path", "legs.spec_path", 1)


@pytest.mark.parametrize("extra", [
    pytest.param((), id="defaults"),
    pytest.param(("--spec-path", ".specify/spec"),
                 id="inside-a-kept-directory-where-it-holds-nothing"),
])
def test_plan_notes_nothing_where_no_leg_path_meets_a_kept_path(
        world, tmp_path, extra):
    written = write_plan(world["source"], tmp_path / "plan.yaml",
                         project=PROJECT, extra=extra)
    assert written.returncode == 0, written.stdout + written.stderr
    assert plan_notes(written) == []
    assert COLLIDES not in written.stdout


def test_plan_notes_no_entry_it_asks_about_instead_of_keeping(tmp_path):
    """An entry holding a submodule is ASKED (#166), `leg: null`, so the
    plan keeps nothing in the root there and `check` finds `plan-unresolved`,
    not a collision: `plan` notes what its file says, not what its rules
    first proposed."""
    source = make_source_repo(tmp_path / "Thing")
    commit_tree_entry(source, "160000", ".specify/vendored", "1" * 40)
    written = write_plan(source, tmp_path / "plan.yaml", project=PROJECT,
                         extra=("--spec-path", ".specify"))
    assert written.returncode == 0, written.stdout + written.stderr
    assert "\n  .specify/\n" in written.stdout, "the entry is asked"
    assert plan_notes(written) == []


# --- `check` -----------------------------------------------------------------

@pytest.mark.parametrize("role, value, relation, named", SHAPE_CASES)
def test_check_reports_a_path_the_shape_writes_as_a_finding(
        world, tmp_path, role, value, relation, named):
    plan = edited_copy(world, tmp_path)
    set_leg_path(plan, role, value)
    result = check(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    findings = findings_of(result)
    assert findings[0].startswith(
        f"{FINDING}legs.{role}_path {value!r} {relation} {named}.")
    assert "plan ok" not in result.stdout


def kept_source(tmp_path: Path, tree: dict, kept: str):
    """A source with `tree`, and an answered plan that keeps `kept` in the
    root."""
    source = make_source_repo(tmp_path / "Thing", tree=tree)
    plan = answered_plan(source, tmp_path / "plan.yaml")
    keep_in_root(plan, kept)
    return source, plan


def with_files(files: dict) -> dict:
    """The synthetic tree with `files` added."""
    return {**SYNTHETIC_TREE, **files}


#: The synthetic tree with a source path AT `docs/spec`, under `docs/`.
DOCS_SPEC_HELD = with_files({"docs/spec/overview.md": "# Overview\n"})

#: `(tree, kept entry, spec_path, the start of what the finding says)`.
KEPT_CASES = [
    pytest.param(dict(SYNTHETIC_TREE), "src/", "src",
                 "contains the file `src/app/main.py` and 1 more. The plan "
                 "keeps them in the assembly root under the entry `src/`",
                 id="contains-a-kept-directory"),
    pytest.param(DOCS_SPEC_HELD, "docs/", DOCS_SPEC,
                 "contains the file `docs/spec/overview.md`. The plan keeps "
                 "it in the assembly root under the entry `docs/`",
                 id="inside-a-kept-directory-at-a-source-path"),
    pytest.param(with_files({"spec": "a file named spec\n"}), "spec", "spec",
                 "is the file `spec`. The plan keeps it in the assembly root,",
                 id="is-a-kept-file"),
    pytest.param({**{k: v for k, v in SYNTHETIC_TREE.items()
                     if not k.startswith("docs/")}, "docs": "a file\n"},
                 "docs", DOCS_SPEC,
                 "is inside the file `docs`. The plan keeps it in the "
                 "assembly root,", id="inside-a-kept-file"),
    pytest.param(with_files({"SPEC/notes.md": "notes\n"}), "SPEC/", "spec",
                 f"contains the file `SPEC/notes.md`{CASE_ASIDE}. The plan "
                 "keeps it in the assembly root under the entry `SPEC/`",
                 id="case-only"),
]


@pytest.mark.parametrize("tree, kept, spec_path, said", KEPT_CASES)
def test_check_reports_a_source_path_the_plan_keeps_in_the_root(
        tmp_path, tree, kept, spec_path, said):
    _, plan = kept_source(tmp_path, tree, kept)
    set_leg_path(plan, "spec", spec_path)
    result = check(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    findings = findings_of(result)
    assert len(findings) == 1, findings
    assert findings[0].startswith(
        f"{FINDING}legs.spec_path {spec_path!r} {said}")
    assert findings[0].endswith(
        f"choose another path for the leg, or send `{kept}` to a leg or "
        "`drop` it.")


def blob(source: Path, text: str) -> str:
    """The id of a blob holding `text`, written into the source's objects."""
    proc = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                          cwd=str(source), input=text, capture_output=True,
                          text=True, check=True)
    return proc.stdout.strip()


@pytest.mark.parametrize("mode, kind", [
    pytest.param("120000", "symlink", id="symlink"),
    pytest.param("160000", "submodule", id="submodule"),
])
def test_check_reports_a_mount_beyond_a_kept_symlink_or_submodule(
        tmp_path, mode, kind):
    """On main `legs/spec` under a kept `legs -> <outside>` cloned the spec
    leg OUTSIDE the work directory before git refused it, and `vendor/spec`
    under a kept submodule died at `git submodule add`. The symlink's blob is
    its target; the submodule's id is a commit nothing needs to hold."""
    source = make_source_repo(tmp_path / "Thing")
    oid = blob(source, "../outside") if kind == "symlink" else "1" * 40
    commit_tree_entry(source, mode, "legs", oid)
    plan = answered_plan(source, tmp_path / "plan.yaml")
    keep_in_root(plan, "legs")
    set_leg_path(plan, "spec", "legs/spec")
    findings = findings_of(check(plan))
    assert len(findings) == 1, findings
    assert findings[0].startswith(
        f"{FINDING}legs.spec_path 'legs/spec' is inside the {kind} `legs`.")


def test_a_mount_inside_a_kept_directory_is_refused_only_at_a_source_path(
        tmp_path):
    """`docs/spec` with `docs/` kept: refused where the source holds
    `docs/spec/overview.md`, and passed where `docs/` holds nothing at the
    mount, which mounts, verifies and bootstraps on main."""
    _, held = kept_source(tmp_path / "held", DOCS_SPEC_HELD, "docs/")
    set_leg_path(held, "spec", DOCS_SPEC)
    assert findings_of(check(held)), "docs/spec holds a kept source path"
    _, empty = kept_source(tmp_path / "empty", dict(SYNTHETIC_TREE), "docs/")
    set_leg_path(empty, "spec", DOCS_SPEC)
    result = check(empty)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "plan ok" in result.stdout


@pytest.mark.parametrize("value, said", [
    pytest.param("shape/", "legs.spec_path is 'shape/'", id="trailing-slash"),
    pytest.param("7", "legs.spec_path is not text", id="not-text"),
])
def test_a_bad_leg_path_is_reported_and_not_also_as_a_collision(
        world, tmp_path, value, said):
    """#169's finding, and only it: an overlap is a statement about two
    PATHS. Compared anyway, `shape/` would read as inside `shape`, and a
    number is not a path at all."""
    plan = edited_copy(world, tmp_path)
    set_leg_path(plan, "spec", value)
    result = check(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"FINDING plan-bad-leg-path: {said}" in result.stderr
    assert FINDING not in result.stderr


# --- `execute` -------------------------------------------------------------

def test_the_refusal_carries_the_findings_check_prints(adopter, world,
                                                       tmp_path):
    plan = edited_copy(world, tmp_path)
    set_leg_path(plan, "spec", CONTRACTS)
    set_leg_path(plan, "code", PROJECT_YAML)
    printed = findings_of(check(plan))
    assert len(printed) == 2, printed
    loaded = adopter.Plan.load(plan)
    source = loaded.open_source(str(world["source"]), tmp_path / "read")
    with pytest.raises(adopter.Refusal) as caught:
        adopter._refuse_what_check_finds(loaded, source)
    assert caught.value.code == COLLIDES
    for finding in printed:
        assert finding in caught.value.detail
    assert ("mount neither leg over a path the assembly root holds"
            in caught.value.remediation)


@pytest.mark.parametrize("role, value", [
    pytest.param("spec", CONTRACTS, id="contracts"),
    pytest.param("code", PROJECT_YAML, id="project-yaml"),
    pytest.param("spec", SHAPE_DIR, id="shape-dir"),
    pytest.param("code", "scripts", id="scripts"),
    pytest.param("spec", ".github", id="dot-github"),
])
def test_execute_refuses_a_path_the_shape_writes_before_any_leg_exists(
        adopter, no_filter_repo_probe, world, tmp_path, role, value):
    plan = edited_copy(world, tmp_path)
    set_leg_path(plan, role, value)
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(execute_args(tmp_path, plan))
    assert caught.value.code == COLLIDES
    assert f"legs.{role}_path {value!r}" in caught.value.detail
    no_leg_was_created(tmp_path, world["source"])


@pytest.mark.parametrize("tree, kept, spec_path, said", KEPT_CASES)
def test_execute_refuses_a_source_path_the_plan_keeps_before_any_leg_exists(
        adopter, no_filter_repo_probe, tmp_path, tree, kept, spec_path, said):
    source, plan = kept_source(tmp_path, tree, kept)
    set_leg_path(plan, "spec", spec_path)
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(execute_args(tmp_path, plan))
    assert caught.value.code == COLLIDES
    assert f"legs.spec_path {spec_path!r} {said}" in caught.value.detail
    no_leg_was_created(tmp_path, source)


# --- `execute`, end to end ---------------------------------------------------

@needs_filter_repo
@pytest.mark.parametrize("role, value", [
    pytest.param("spec", CONTRACTS, id="contracts"),
    pytest.param("code", PROJECT_YAML, id="project-yaml"),
])
def test_execute_refuses_it_end_to_end_and_the_remote_dir_stays_empty(
        tmp_path, role, value):
    """The issue's repro, and the case main ran to `adoption verified`: the
    value edited into a plan `check` once passed. Refused before a leg is
    made, so the EMPTY `--local-remote-dir` it is given stays empty."""
    source = make_source_repo(tmp_path / "Thing")
    plan = answered_plan(source, tmp_path / "plan.yaml")
    set_leg_path(plan, role, value)
    remotes = tmp_path / REMOTES
    remotes.mkdir()
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / WORK))
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"REFUSED {COLLIDES}" in result.stderr
    assert f"{FINDING}legs.{role}_path {value!r}" in result.stderr
    assert "creating the leg repositories" not in result.stdout
    assert "adoption verified" not in result.stdout
    assert list(remotes.iterdir()) == [], "no leg repository was made"
    nothing_else_was_made(tmp_path, source)


@needs_filter_repo
def test_execute_mounts_inside_a_kept_directory_only_where_it_holds_nothing(
        tmp_path):
    """`docs/spec` with `docs/` kept: refused end to end where the source
    holds `docs/spec/overview.md`; adopted, with the spec leg mounted at
    `docs/spec`, where it holds nothing there."""
    held_tmp = tmp_path / "held"
    held_source, held = kept_source(held_tmp, DOCS_SPEC_HELD, "docs/")
    set_leg_path(held, "spec", DOCS_SPEC)
    refused = run_script(ADOPT, "execute", "--plan", str(held), "--yes",
                         "--local-remote-dir", str(held_tmp / REMOTES),
                         "--work-dir", str(held_tmp / WORK))
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert f"REFUSED {COLLIDES}" in refused.stderr
    no_leg_was_created(held_tmp, held_source)

    empty_tmp = tmp_path / "empty"
    empty_source, empty = kept_source(empty_tmp, dict(SYNTHETIC_TREE), "docs/")
    set_leg_path(empty, "spec", DOCS_SPEC)
    adopted = run_script(ADOPT, "execute", "--plan", str(empty), "--yes",
                         "--local-remote-dir", str(empty_tmp / REMOTES),
                         "--work-dir", str(empty_tmp / WORK))
    assert adopted.returncode == 0, adopted.stdout + adopted.stderr
    assert "adoption verified" in adopted.stdout
    gitlinks = [line.split("\t")[1] for line in git(
        "ls-tree", "-r", SPLIT_BRANCH, cwd=empty_source).stdout.splitlines()
        if line.startswith("160000")]
    assert sorted(gitlinks) == ["code", DOCS_SPEC]
