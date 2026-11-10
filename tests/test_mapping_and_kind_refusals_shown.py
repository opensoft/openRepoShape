# SPDX-License-Identifier: Apache-2.0
"""A file that reads as YAML but is not a mapping, or is a policy of another
kind, is refused naming the file as `shown_path` names it (#1279).

#1168 gave that spelling to `load_yaml`'s three refusals and to
`policy-unreadable`. The refusals on the next line of each reader, where the
YAML parsed but is a list, or declares another `kind:`, still named the path
raw: a bidi override, U+202E, in a folder's name reordered the line, an ESC
reached the terminal as the control it is, and a line feed began a line of
the path's choosing. Each is spelled now:

- `policy-wrong-kind`, in `repo_shape.NamingPolicy.load`;
- `manifest-unreadable`, the naming gate's `--project`;
- `bump-leg-manifest-unreadable`, `bump-leg.py --root`, where `project.yaml`
  is not a mapping (a root it cannot search was spelled already, and the
  last row below pins that spelling);
- `path-policy-unreadable` and `path-policy-wrong-kind`, in
  `path_classify.PathPolicy.load`, which `adopt-project.py plan
  --path-policy` reads;
- `update-pin-unreadable`, `update-shape.py check --root`;
- the root's `manifest-unreadable`, its own `validate-manifest.py`.

Each run is one of `test_load_yaml_refusals.py`'s, with the file it builds
holding YAML that parses. The naming gate and the root's
`validate-manifest.py` are copied into every project, beside a
`scripts/repo_shape.py` that may be older than they are, so each spells the
path with the `_shown` it already carries: the rows that run them beside a
library from before #1168 hold that for any name that library lacks. It has
`shown_path` already, so a gate that imported that name would pass those rows;
the import is held out by `test_pinned_copy_text.py`'s
`test_no_pinned_script_imports_what_an_older_library_lacks`.
A printable path is named byte for byte as it always was.
`adopt-project.py`'s `plan-unreadable` is #1177's.

NO NETWORK AND NO GITHUB: temporary files, local repositories, and the
session's `gh` guard first on PATH for every tool run.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from conftest import (
    REPO, assert_shown_safe, named_as, run_script, unsafe_folder,
)
from test_bump_leg_unopenable import needs_a_mode
from test_bump_leg_unsearchable import unsearchable_root
from test_load_yaml_refusals import (
    NAMES, TEMPLATE_SCRIPTS, TOOLS, a_root, older_library, refused_lines,
)

#: YAML that parses, to a list, and to a mapping of another kind.
A_LIST = "- a\n"
ANOTHER_KIND = "kind: other\n"

#: What each refusal says after the path.
NOT_A_MAPPING = "not a mapping"
NOT_A_NAMING_POLICY = "kind is 'other', expected 'repository-naming-policy'"
NOT_A_PATH_POLICY = "kind is 'other', expected 'path-classification-policy'"

#: The issue's table, less #1177's `plan-unreadable`: each refusal, as
#: `(code, the run in test_load_yaml_refusals.TOOLS that reaches it, what
#: its file holds, what the refusal says after the path)`.
SITES = {
    "policy-wrong-kind": (
        "policy-wrong-kind", "naming--policy", ANOTHER_KIND,
        NOT_A_NAMING_POLICY),
    "manifest-unreadable-naming--project": (
        "manifest-unreadable", "naming--project", A_LIST, NOT_A_MAPPING),
    "bump-leg-manifest-unreadable": (
        "bump-leg-manifest-unreadable", "bump-leg--root", A_LIST,
        NOT_A_MAPPING),
    "path-policy-unreadable": (
        "path-policy-unreadable", "adopt-plan--path-policy", A_LIST,
        NOT_A_MAPPING),
    "path-policy-wrong-kind": (
        "path-policy-wrong-kind", "adopt-plan--path-policy", ANOTHER_KIND,
        NOT_A_PATH_POLICY),
    "update-pin-unreadable": (
        "update-pin-unreadable", "update-shape-check--root", A_LIST,
        NOT_A_MAPPING),
    "manifest-unreadable-validate-manifest": (
        "manifest-unreadable", "validate-manifest--root", A_LIST,
        NOT_A_MAPPING),
}


def holding(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def assert_refused_once(result, code: str, named: str, said: str) -> None:
    """Exit 2, one `REFUSED` line, exactly `REFUSED <code>: <named>:
    <said>`, and no U+202E, ESC or forged line anywhere in the output."""
    output = result.stdout + result.stderr
    assert result.returncode == 2, ascii(output)
    assert refused_lines(result.stderr) == [
        f"REFUSED {code}: {named}: {said}"], ascii(output)
    assert chr(0x202E) not in output, ascii(output)
    assert_shown_safe(result.stdout, result.stderr)


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("site", sorted(SITES))
def test_each_refusal_names_the_file_as_shown_path_names_it(
        tmp_path, site, name):
    """THE ISSUE'S PROBE, one real run per refusal: the file named as `repr`
    spells it where its folder's name holds U+202E, an ESC or a line feed,
    so nothing of that name reaches the terminal raw and the detail stays
    one line. At #1274's head each named it raw. The printable row is the
    control, named byte for byte as before, with no quotes."""
    code, tool, text, said = SITES[site]
    path, argv = TOOLS[tool](unsafe_folder(tmp_path, name), tmp_path)
    holding(path, text)
    result = run_script(*argv, cwd=tmp_path)
    assert_refused_once(result, code, named_as(path, name), said)


#: The naming gate, which every project carries as it is here.
NAMING = REPO / "scripts" / "validate-repository-naming.py"

#: The root's own manifest gate.
MANIFEST_GATE = "validate-manifest.py"


def naming_gate(folder: Path, library: bytes) -> tuple:
    """The naming gate as a root carries it, beside `library` and this
    checkout's naming policy, asked of a `project.yaml` that is a list."""
    root = a_root(folder, NAMING.read_bytes(), library, NAMING.name)
    policy = root / "contracts" / "repository-naming.yaml"
    policy.parent.mkdir()
    shutil.copyfile(REPO / "contracts" / "repository-naming.yaml", policy)
    manifest = holding(folder / "n" / "project.yaml", A_LIST)
    return manifest, (root / "scripts" / NAMING.name, "--project",
                      str(manifest))


def manifest_gate(folder: Path, library: bytes) -> tuple:
    """The root's `validate-manifest.py` beside `library`, over a root whose
    `project.yaml` is a list."""
    root = a_root(folder, (TEMPLATE_SCRIPTS / MANIFEST_GATE).read_bytes(),
                  library, MANIFEST_GATE)
    return holding(root / "project.yaml", A_LIST), (
        root / "scripts" / MANIFEST_GATE, "--root", str(root))


#: The two copied gates whose own refusal changed.
COPIED_GATES = {
    "naming-gate--project": naming_gate,
    "validate-manifest--root": manifest_gate,
}


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("gate", sorted(COPIED_GATES))
def test_a_copied_gate_spells_the_path_beside_an_older_library(
        tmp_path, gate, name):
    """THE SKEW RULE: each copied gate beside a root's `repo_shape.py` from
    before #1168, which has none of #1279's lines. The gate spells the path
    with its own `_shown`, so it runs, refuses `manifest-unreadable` by
    name, and spells the path as it does beside this checkout's library."""
    path, argv = COPIED_GATES[gate](unsafe_folder(tmp_path, name),
                                    older_library())
    result = run_script(*argv, cwd=tmp_path)
    assert "Traceback" not in result.stderr, ascii(result.stderr)
    assert_refused_once(result, "manifest-unreadable", named_as(path, name),
                        NOT_A_MAPPING)


@needs_a_mode
@pytest.mark.parametrize("name", NAMES)
def test_a_root_that_cannot_be_searched_is_named_as_shown_path_names_it(
        tmp_path, name):
    """THE SPELLING THIS CHANGE LEFT ALONE: a `--root`
    this user cannot search is `bump-leg-manifest-unreadable` from
    `_manifest_unopened_refusal`, which names `project.yaml` as `shown_path`
    does and did before #1279. No other row ran it under a path holding
    U+202E, an ESC or a line feed (`test_bump_leg_unsearchable.py` uses a
    printable one), so it was one `{path}` from raw with every row green.
    This row passes on #1274's head too: it pins a spelling, and fails
    nothing first. The root's mode is put back in a `finally`."""
    path, argv = TOOLS["bump-leg--root"](unsafe_folder(tmp_path, name),
                                         tmp_path)
    with unsearchable_root(path.parent, 0):
        result = run_script(*argv, cwd=tmp_path)
    assert_refused_once(result, "bump-leg-manifest-unreadable",
                        named_as(path, name), "cannot be read: Permission "
                        "denied")
