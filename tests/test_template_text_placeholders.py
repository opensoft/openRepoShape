# SPDX-License-Identifier: Apache-2.0
"""A text value YAML would read as another type reads back as typed (#259).

The assembly root's `project.yaml`, its two leg pins and a family holder's
`family.yaml` wrote their text placeholders bare: `id: {{PROJECT_ID}}`,
`tracking_branch: {{TRACKING_BRANCH}}`, `path: {{SPEC_PATH}}`,
`submodule_path: {{SPEC_PATH}}`. Every reader of those files reads them with
`repo_shape`'s YAML subset, which takes a bare `007` as the number 7, `2026`
and `20261011` as numbers, `1.5` as a float, `true` as True and `null` as
None. The checks on the flags (`PROJECT_ID_RE`, `checked_value`, the leg-path
rule) admit every one of them, so on main:

- `scaffold-project.py --id 007` wrote a project whose own gate failed
  `manifest-id`, and `--spec-path 2026` one that failed `manifest-leg-path`;
- `--tracking-branch 007` pushed each leg on `007`, and the root's own
  `bootstrap.py` then put the legs on a local `7` with no upstream (`true`
  and `null` did the same on `True` and `main`);
- `adopt-project.py execute` wrote the same lines, and `family.py init` wrote
  a holder its own `validate-family.py` refused (`family-id`, `family-org`).

Brett Heap ruled on 2026-10-12, "quote #259". The templates write each of
those fields between double quotes, `render` spells the value there with
`double_quoted` (#284), and the reader takes it back exactly. A project made
before this keeps its bare lines, which read correctly for every name that is
plain text, so the readers keep their `str()`.

NO NETWORK AND NO GITHUB: templates rendered in memory, and scaffolds,
adoptions and families into local bare remotes (`--local-remote-dir`), which
never call `gh`.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, FILE_PROTOCOL, REPO, SCAFFOLD, git,
                      make_source_repo, run_script)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml, parse_yaml  # noqa: E402
from shape_materialize import render  # noqa: E402

FAMILY = REPO / "scripts" / "family.py"
BUMP = REPO / "scripts" / "bump-leg.py"
PROJECT = "Atlas"
ADOPTED = "Northwind"
HOLDER = "Contoso"
ORG = "testorg"
ADOPT_BRANCH = "adopt/three-repo-shape"

PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")

#: Text the reader takes as something else when it stands bare after a key:
#: numbers, a float, the keywords it knows, and the dates no ISO form spells.
MISREAD = ("2026", "007", "1.5", "true", "null", "20261011", "~", "False")

#: `(template, placeholder, where the loaded document holds it)` for every
#: text field a tool fills from a value it was given. A leg is found by its
#: role, never by its position in `legs:`.
TEXT_FIELDS = [
    ("templates/assembly-root/project.yaml", "PROJECT_ID", ("id",)),
    ("templates/assembly-root/project.yaml", "ELECTED_ON", ("elected_on",)),
    ("templates/assembly-root/project.yaml", "VISIBILITY", ("visibility",)),
    ("templates/assembly-root/project.yaml", "TRACKING_BRANCH",
     ("tracking_branch",)),
    ("templates/assembly-root/project.yaml", "SPEC_PATH",
     ("legs", "spec", "path")),
    ("templates/assembly-root/project.yaml", "CODE_PATH",
     ("legs", "code", "path")),
    ("templates/assembly-root/contracts/spec-pin.yaml", "SPEC_PATH",
     ("submodule_path",)),
    ("templates/assembly-root/contracts/code-pin.yaml", "CODE_PATH",
     ("submodule_path",)),
    ("templates/family-root/family.yaml", "FAMILY_ID", ("id",)),
    ("templates/family-root/family.yaml", "ORG", ("org",)),
    ("templates/family-root/family.yaml", "CREATED_ON", ("created_on",)),
    ("templates/family-root/family.yaml", "VISIBILITY", ("visibility",)),
    ("templates/family-root/family.yaml", "TRACKING_BRANCH",
     ("tracking_branch",)),
]


def held(document, where: tuple):
    """The value at `where`: a key, or under `legs` the leg with that role."""
    node = document
    for step in where:
        if isinstance(node, list):
            node = next(leg for leg in node if leg.get("role") == step)
        else:
            node = node[step]
    return node


def rendered(template: str, placeholder: str, value: str) -> str:
    """`template` with `value` in `placeholder` and a harmless stand-in in
    every other placeholder: a line of its own for a block placeholder."""
    text = (REPO / template).read_text(encoding="utf-8")
    values = {}
    for key in set(PLACEHOLDER.findall(text)):
        if key == placeholder:
            values[key] = value
        elif re.search(r"^\{\{" + key + r"\}\}", text, re.M):
            values[key] = f"    stand_in_{key.lower()}: 1"
        else:
            values[key] = f"v-{key.lower()}"
    return render(text, values, template)


@pytest.mark.parametrize("value", MISREAD)
@pytest.mark.parametrize(
    "template,placeholder,where", TEXT_FIELDS,
    ids=[f"{t.split('/')[-1]}:{'.'.join(w)}" for t, _, w in TEXT_FIELDS])
def test_a_text_field_reads_back_as_the_text_it_was_given(template,
                                                          placeholder, where,
                                                          value):
    assert held(parse_yaml(rendered(template, placeholder, value)),
                where) == value


# --- scaffold-project.py, end to end ---------------------------------------
#
# Each row puts a different value in each field, so that across the rows
# every field holds every value its flag admits: `--id` refuses `1.5` (a dot
# is not in `PROJECT_ID_RE`), and every other field takes all six.

SCAFFOLDS = [
    # --id,      --tracking-branch, --spec-path, --code-path
    ("true", "2026", "007", "1.5"),
    ("null", "007", "1.5", "true"),
    ("20261011", "1.5", "true", "null"),
    ("2026", "true", "null", "20261011"),
    ("007", "null", "20261011", "2026"),
    ("007", "20261011", "2026", "007"),
]


def heads(bare: Path) -> list[str]:
    return git("for-each-ref", "--format=%(refname:short)", "refs/heads",
               cwd=bare).stdout.split()


def clone(remote: Path, target: Path, *extra: str) -> Path:
    proc = subprocess.run(
        ["git", *FILE_PROTOCOL, "clone", "-q", "--recurse-submodules",
         *extra, str(remote), str(target)],
        capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return target


def assert_the_root_reads_what_it_was_given(manifest: dict, pins: dict,
                                            project_id: str, branch: str,
                                            spec: str, code: str) -> None:
    assert manifest["id"] == project_id
    assert manifest["tracking_branch"] == branch
    assert held(manifest, ("legs", "spec", "path")) == spec
    assert held(manifest, ("legs", "code", "path")) == code
    assert pins == {"spec": spec, "code": code}


def pin_paths(root: Path, show=None) -> dict:
    """Each leg pin's `submodule_path`, read from disk or through `show`."""
    out = {}
    for role in ("spec", "code"):
        rel = f"contracts/{role}-pin.yaml"
        pin = parse_yaml(show(rel)) if show else load_yaml(root / rel)
        out[role] = pin["submodule_path"]
    return out


def assert_the_clone_works(root: Path, branch: str, spec: str,
                           code: str) -> None:
    """The root's own bootstrap puts each leg on `branch` with its upstream,
    and the root's own three validators pass."""
    booted = run_script(root / "scripts" / "bootstrap.py", cwd=root)
    assert booted.returncode == 0, booted.stdout + booted.stderr
    for path in (spec, code):
        leg = root / path
        assert git("symbolic-ref", "--short", "HEAD", cwd=leg).stdout.strip() \
            == branch, f"the leg at {path!r} is not on {branch!r}"
        assert git("rev-parse", "--abbrev-ref", "@{upstream}",
                   cwd=leg).stdout.strip() == f"origin/{branch}"
    for validator, args in (("validate-manifest.py", ()),
                            ("validate-pins.py", ()),
                            ("validate-repository-naming.py",
                             ("--project", "project.yaml"))):
        checked = run_script(root / "scripts" / validator, *args, cwd=root)
        assert checked.returncode == 0, \
            f"{validator}: {checked.stdout}{checked.stderr}"


@pytest.mark.parametrize("project_id,branch,spec,code", SCAFFOLDS,
                         ids=["-".join(row) for row in SCAFFOLDS])
def test_a_scaffold_reads_back_every_value_it_was_given(tmp_path, project_id,
                                                        branch, spec, code):
    remotes, work = tmp_path / "remotes", tmp_path / "work"
    result = run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                        "--id", project_id, "--tracking-branch", branch,
                        "--spec-path", spec, "--code-path", code,
                        "--elected-by", "Test Human",
                        "--elected-on", "2026-09-02",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(work))
    assert result.returncode == 0, result.stderr + result.stdout
    written = work / PROJECT
    assert_the_root_reads_what_it_was_given(
        load_yaml(written / "project.yaml"), pin_paths(written), project_id,
        branch, spec, code)
    for name in (PROJECT, f"{PROJECT}-spec", f"{PROJECT}-code"):
        assert heads(remotes / f"{name}.git") == [branch], name

    root = clone(remotes / f"{PROJECT}.git", tmp_path / "clone" / PROJECT)
    assert_the_clone_works(root, branch, spec, code)

    # `bump-leg.py` reads the branch and the leg's path out of the same
    # manifest. On the tracking branch it refuses, which it can only do if it
    # read the branch the root is on; on a branch of its own it finds the
    # leg's checkout at its path and reports the pin it already holds.
    pinned = git("rev-parse", f"HEAD:{spec}", cwd=root).stdout.strip()
    bump = ("--root", str(root), "--leg", "spec", "--to", pinned,
            "--local-remote-dir", str(remotes))
    refused = run_script(BUMP, *bump)
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert "bump-leg-on-tracking-branch" in refused.stderr
    git("switch", "-q", "-c", "bump/spec", cwd=root)
    again = run_script(BUMP, *bump)
    assert again.returncode == 1, again.stdout + again.stderr
    assert "nothing to do" in again.stdout
    assert f"at {spec}/" in again.stdout


# --- adopt-project.py, end to end ------------------------------------------
#
# `plan` writes a value the plan's own reader would misread between double
# quotes when it starts with a digit, so `2026`, `007`, `1.5` and `20261011`
# go through the flags. It writes `true` and `null` bare, and the plan's
# reader then takes them as a boolean and as no value: that is the PLAN's
# writer, #181's to fix. Those two rows quote the value in the plan by hand,
# as #181's writer will, and ask `check` and `execute` the rest.

ADOPTIONS = [
    # --id,      --tracking-branch, --spec-path, --code-path, by hand
    ("007", "2026", "1.5", "20261011", False),
    ("20261011", "007", "2026", "007", False),
    ("2026", "1.5", "007", "2026", False),
    ("2026", "20261011", "20261011", "1.5", False),
    ("true", "true", "null", "true", True),
    ("null", "null", "true", "null", True),
]

pytest_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

SOURCE_TREE = {"README.md": "# Thing\n", "specs/feature.md": "# Feature\n",
               "src/main.py": "VALUE = 1\n"}


def quote_in_plan(plan: Path, edits: dict) -> None:
    """Replace each `<key>: <value>` line of the plan with the quoted value,
    in bytes, so the plan stays LF on every platform."""
    data = plan.read_bytes()
    for line, value in edits.items():
        key = line.split(b":", 1)[0]
        assert data.count(line) == 1, line
        data = data.replace(line, key + b': "' + value.encode() + b'"\n')
    plan.write_bytes(data)


@pytest_filter_repo
@pytest.mark.parametrize("project_id,branch,spec,code,by_hand", ADOPTIONS,
                         ids=["-".join(row[:4]) for row in ADOPTIONS])
def test_an_adoption_reads_back_every_value_it_was_given(tmp_path, project_id,
                                                         branch, spec, code,
                                                         by_hand):
    source = make_source_repo(tmp_path / "Thing", tree=SOURCE_TREE, edits=())
    plan = tmp_path / "adoption-plan.yaml"
    flags = () if by_hand else ("--id", project_id, "--tracking-branch",
                                branch, "--spec-path", spec,
                                "--code-path", code)
    planned = run_script(ADOPT, "plan", "--source", str(source),
                         "--project", ADOPTED, "--org", ORG,
                         "--elected-by", "Test Human",
                         "--elected-on", "2026-09-02",
                         "--out", str(plan), *flags)
    assert planned.returncode == 0, planned.stderr + planned.stdout
    if by_hand:
        quote_in_plan(plan, {b"id: northwind\n": project_id,
                             b"tracking_branch: main\n": branch,
                             b"  spec_path: spec\n": spec,
                             b"  code_path: code\n": code})
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    remotes = tmp_path / "remotes"
    executed = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                          "--local-remote-dir", str(remotes),
                          "--work-dir", str(tmp_path / "work"))
    assert executed.returncode == 0, executed.stderr + executed.stdout

    def show(rel: str) -> str:
        return git("show", f"{ADOPT_BRANCH}:{rel}", cwd=source).stdout

    assert_the_root_reads_what_it_was_given(
        parse_yaml(show("project.yaml")), pin_paths(source, show), project_id,
        branch, spec, code)
    for leg in ("spec", "code"):
        assert heads(remotes / f"{ADOPTED}-{leg}.git") == [branch], leg

    root = clone(source, tmp_path / "clone" / ADOPTED, "-b", ADOPT_BRANCH)
    assert_the_clone_works(root, branch, spec, code)


# --- family.py, end to end -------------------------------------------------

FAMILIES = [
    # --id,      --org,      --tracking-branch
    ("007", "2026", "true"),
    ("2026", "true", "null"),
    ("true", "null", "007"),
    ("null", "007", "1.5"),
    ("20261011", "1.5", "20261011"),
    ("007", "20261011", "2026"),
]


@pytest.mark.parametrize("family_id,org,branch", FAMILIES,
                         ids=["-".join(row) for row in FAMILIES])
def test_a_family_holder_reads_back_every_value_it_was_given(tmp_path,
                                                             family_id, org,
                                                             branch):
    remotes = tmp_path / "remotes"
    created = run_script(FAMILY, "init", "--org", org, "--family", HOLDER,
                         "--id", family_id, "--tracking-branch", branch,
                         "--created-by", "Test Human",
                         "--created-on", "2026-09-04",
                         "--local-remote-dir", str(remotes),
                         "--work-dir", str(tmp_path / "work"))
    assert created.returncode == 0, created.stderr + created.stdout
    root = tmp_path / "work" / HOLDER
    manifest = load_yaml(root / "family.yaml")
    assert (manifest["id"], manifest["org"], manifest["tracking_branch"]) \
        == (family_id, org, branch)
    assert heads(remotes / f"{HOLDER}.git") == [branch]
    checked = run_script(root / "scripts" / "validate-family.py", cwd=root)
    assert checked.returncode == 0, checked.stdout + checked.stderr


def test_a_member_whose_id_yaml_would_misread_is_pinned_under_that_id(
        tmp_path):
    """`family.py add` records the member's OWN `project.yaml` id in its row.
    That id is read back exactly now, so the row has to be too: written bare,
    `007` came back as 7 and the holder's validator reported
    `member-id-mismatch` for a member it had just pinned. An ordinary id is
    written as it always was, so no existing holder's block moves."""
    remotes, work = tmp_path / "remotes", tmp_path / "work"
    members = {"IRRS": "007", "IRSS": "true", "IRQS": None}
    for project, project_id in members.items():
        flags = ("--id", project_id) if project_id else ()
        made = run_script(SCAFFOLD, "--org", ORG, "--project", project,
                          *flags, "--elected-by", "Test Human",
                          "--elected-on", "2026-09-04",
                          "--local-remote-dir", str(remotes),
                          "--work-dir", str(work))
        assert made.returncode == 0, made.stderr + made.stdout
    created = run_script(FAMILY, "init", "--org", ORG, "--family", HOLDER,
                         "--created-by", "Test Human",
                         "--created-on", "2026-09-04",
                         "--local-remote-dir", str(remotes),
                         "--work-dir", str(tmp_path / "fam"))
    assert created.returncode == 0, created.stderr + created.stdout
    root = tmp_path / "fam" / HOLDER
    for project in members:
        added = run_script(FAMILY, "add", "--family-root", str(root),
                           "--member", f"{ORG}/{project}",
                           "--local-remote-dir", str(remotes))
        assert added.returncode == 0, added.stderr + added.stdout
    rows = {row["project"]: row["id"]
            for row in load_yaml(root / "family.yaml")["members"]}
    assert rows == {"IRRS": "007", "IRSS": "true", "IRQS": "irqs"}
    lines = (root / "family.yaml").read_bytes().splitlines()
    assert b'    id: "007"' in lines
    assert b"    id: irqs" in lines
    checked = run_script(root / "scripts" / "validate-family.py", cwd=root)
    assert checked.returncode == 0, checked.stdout + checked.stderr
