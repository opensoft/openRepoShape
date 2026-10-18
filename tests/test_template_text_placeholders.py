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

The neutral product pin's `product:` joined them for #516. Both tools render
`contracts/neutral-product-pin.yaml`, and its bare `product: {{PIN_PRODUCT}}`
gave `--pin 007@<commit>` a `contracts/007-pin.yaml` saying `product: 007`,
read back as 7.

NO NETWORK AND NO GITHUB, off Windows: templates rendered in memory, and
scaffolds, adoptions and families into local bare remotes
(`--local-remote-dir`), which never call `gh`. The only `gh` run here is
`check`'s, in the two adoption tests that run it before `execute` and give it
no `--local-remote-dir`: once nothing before it refuses and the plan's names
and `org:` pass, it asks `gh repo view` once of the spec leg's repository and
once of the code leg's (#798), and off Windows the session's guard answers each
as a `gh` with no login does (`tests/gh_guard.py`).
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, REPO, SCAFFOLD, cloned_just_pushed, git,
                      make_source_repo, run_script)
from test_family import family_module

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import (  # noqa: E402
    YamlError, double_quoted, load_yaml, parse_yaml,
)
from shape_materialize import neutral_pin_path, render  # noqa: E402

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
    ("templates/assembly-root/contracts/neutral-product-pin.yaml",
     "PIN_PRODUCT", ("product",)),
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

    root = cloned_just_pushed(remotes / f"{PROJECT}.git",
                              tmp_path / "clone" / PROJECT)
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
# go through the flags. It wrote `true` and `null` bare, and the plan's
# reader then took them as a boolean and as no value: that was the PLAN's
# writer, which #181 fixes, and `plan` quotes them too now
# (tests/test_adopt_plan_yaml_quoting.py drives them through the flags).
# These two rows quote the value in the plan by hand, as a plan edited by
# hand does, and ask `check` and `execute` the rest.

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
    # Adopt refuses a tracking branch the source lacks, as
    # `plan-tracking-branch-missing` (#479, main's 56713e21), so the source
    # carries the branch this row adopts onto: flag rows and by-hand rows.
    git("branch", branch, cwd=source)
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

    root = cloned_just_pushed(source, tmp_path / "clone" / ADOPTED,
                              ADOPT_BRANCH)
    assert_the_clone_works(root, branch, spec, code)


# --- the neutral product pin `adopt-project.py execute` writes (#516) ------
#
# The scaffold's end-to-end cases are beside its other `--pin` tests, in
# `tests/test_scaffold_pin_and_reuse.py`; this is the other tool that renders
# the same template. `plan` records the product quoted, and on main fc48854
# `execute` wrote the pin file's `product: 007` bare all the same. What the
# manifest's `neutral_product_pins:` says is #514's, and not asked here.

PIN_PRODUCTS = ("007", "2026", "1.5", "openGlass")


@pytest_filter_repo
@pytest.mark.parametrize("product", PIN_PRODUCTS)
def test_an_adopted_pin_names_its_product_as_the_text_given(tmp_path,
                                                            product):
    source = make_source_repo(tmp_path / "Thing", tree=SOURCE_TREE, edits=())
    stand_in = make_source_repo(tmp_path / "product",
                                tree={"README.md": f"# {product}\n"},
                                edits=())
    commit = git("rev-parse", "HEAD", cwd=stand_in).stdout.strip()
    plan = tmp_path / "adoption-plan.yaml"
    planned = run_script(ADOPT, "plan", "--source", str(source),
                         "--project", ADOPTED, "--org", ORG,
                         "--elected-by", "Test Human",
                         "--elected-on", "2026-09-02",
                         "--pin", f"{product}@{commit}",
                         "--pin-source", str(stand_in), "--out", str(plan))
    assert planned.returncode == 0, planned.stderr + planned.stdout
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    executed = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                          "--local-remote-dir", str(tmp_path / "remotes"),
                          "--work-dir", str(tmp_path / "work"))
    assert executed.returncode == 0, executed.stderr + executed.stdout
    rel = neutral_pin_path(product)
    pin = parse_yaml(git("show", f"{ADOPT_BRANCH}:{rel}", cwd=source).stdout)
    assert pin["product"] == product
    assert pin["commit"] == commit


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
    written as it always was, so a row whose id reads back as text does not
    move."""
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
    # On a branch of its own, as a person adds members for a pull request:
    # #487 (PR #507) makes `add` refuse the holder's tracking branch.
    git("switch", "-q", "-c", "family/members", cwd=root)
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


#: Ids the holder's reader RAISES on, rather than reads as another type, when
#: they stand bare after `id:`. `PROJECT_ID_RE` keeps every one out of a
#: scaffold and out of `family.py add`, so no tool writes one; a hand-edited
#: row holds one between double quotes, and the next `bump`, `add` or
#: `remove` spells the whole block again.
UNREADABLE_BARE_IDS = ("[", "{", "&a", "*a", "!t", "'a", '"a')

HAND_EDITED_HOLDER = """\
name: Contoso
kind: family-manifest
members:
  - project: IRRS
    id: {spelled}
    repository: testorg/IRRS
    path: members/IRRS
    pin:
      revision_kind: commit
      commit: "{commit}"
      digest_algorithm: sha256
      digest_definition: sorted-ls-tree-r-v1
      tree_sha256: "{tree}"
"""


@pytest.mark.parametrize(
    "member_id", UNREADABLE_BARE_IDS,
    ids=["flow-sequence", "flow-mapping", "anchor", "alias", "tag",
         "open-single-quote", "open-double-quote"])
def test_a_member_id_the_reader_refuses_bare_is_rewritten_between_quotes(
        tmp_path, member_id):
    """`_member_id` asks the reader whether the bare id reads back as that
    text, and an id the reader RAISES on is not read back as anything: it
    gets the quotes, and the rewrite goes on. A call that let the error out
    would stop `bump`, `add` and `remove` on a holder that holds such a row,
    though the row itself is a quoted scalar the reader takes exactly."""
    with pytest.raises(YamlError):
        parse_yaml(f"id: {member_id}\n")
    spelled = double_quoted(member_id)
    text = HAND_EDITED_HOLDER.format(spelled=spelled, commit="a" * 40,
                                     tree="b" * 64)
    (tmp_path / "family.yaml").write_bytes(text.encode("utf-8"))
    family = family_module().Family.open(tmp_path)
    assert [row["id"] for row in family.members] == [member_id]

    again = family.rewritten(family.members)

    assert parse_yaml(again)["members"][0]["id"] == member_id
    assert f"    id: {spelled}\n" in again
    assert again == text
