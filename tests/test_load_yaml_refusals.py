# SPDX-License-Identifier: Apache-2.0
"""`load_yaml` refuses a file it cannot read, under one code and never bare.

Three ways a YAML file can fail to become data, and the refusal each one is:

- not there, or not openable (`OSError`): `yaml-unreadable`;
- there, opened, and not UTF-8 (`UnicodeDecodeError`): `yaml-unreadable`;
- decoded, and not the YAML this reader implements (`YamlError`):
  `yaml-unparsable`.

The middle one used to be no refusal at all (#192). `UnicodeDecodeError` is a
`ValueError`, and `Path.read_text` raises it AFTER the open succeeded, so the
`except OSError` beside it never saw it and every reader that goes through
`load_yaml` -- `adopt-project.py check` and `execute`, the manifest and pin
validators, `bootstrap.py`, `update-shape.py` -- died with a Python traceback
instead of a `REFUSED` line with a remediation. The readers' own tests are in
`test_adopt_execute_refusals.py` (the adoption plan) and
`test_manifest_validator.py` (`project.yaml`); this file is the function.

THE FILE IS NAMED AS `shown_path` NAMES IT (#1168), in all three. A path is
typed (`--plan`, `--policy`, `--root`), and named raw, a bidi override in it
reordered the line, an ESC reached the terminal as the control it is, and a
line feed began a line of the path's choosing. The rows below hold each
refusal to that in process, then each tool that hands `load_yaml` a typed
path to it in a real run, and then every reader that finds the path in the
detail by its text: `validate-pins.py`'s `_load` in both version orders,
`link_declarations`, `family.py`'s member manifest and two in
`shape-doctor.py`. A printable path is named byte for byte as before.

NO NETWORK AND NO GITHUB: temporary files, local repositories, imports, and
the session's `gh` guard first on PATH for every tool run.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (
    ADOPT, PRINTABLE_NAME, REPO, UNSAFE_NAMES, assert_shown_safe,
    copied_under, git, load_without_bytecode, make_source_repo, named_as,
    run_script, spelt, unsafe_folder,
)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import (  # noqa: E402
    NamingPolicy, Refusal, link_declarations, load_yaml, shown_path,
)

#: `(bytes, offset of the first byte that is not UTF-8)`. Each is a way a file
#: reaches this state: a Latin-1 `é` where UTF-8 has two bytes, a UTF-16 byte
#: order mark at the very start, a UTF-8 sequence cut off by the end of the
#: file, and the same bad byte in a comment, which the parser would never have
#: looked at -- the whole file is decoded before it is parsed.
NOT_UTF8 = {
    "latin-1-e-acute": (b"name: caf\xe9\n", 9),
    "utf-16-byte-order-mark": (b"\xff\xfen\x00a\x00m\x00e\x00", 0),
    "sequence-cut-off-by-the-end": (b"name: caf\xc3", 9),
    "in-a-comment": (b"# caf\xe9\nname: cafe\n", 5),
}


def refusal_for(path) -> Refusal:
    with pytest.raises(Refusal) as caught:
        load_yaml(path)
    return caught.value


@pytest.mark.parametrize("case", sorted(NOT_UTF8))
def test_a_file_that_is_not_utf8_is_yaml_unreadable(tmp_path, case):
    body, offset = NOT_UTF8[case]
    path = tmp_path / "plan.yaml"
    path.write_bytes(body)
    refusal = refusal_for(path)
    assert refusal.code == "yaml-unreadable"
    assert str(path) in refusal.detail, "the file is named"
    assert f"not UTF-8 at byte {offset}" in refusal.detail
    assert refusal.__cause__.reason in refusal.detail, (
        "and so is why Python would not decode it")
    assert isinstance(refusal.__cause__, UnicodeDecodeError)


@pytest.mark.parametrize("case", sorted(NOT_UTF8))
def test_the_remediation_says_utf8_and_names_the_byte(tmp_path, case):
    """Said in the remediation as well as the detail, because `main` prints
    `str(exc)` and a caller that keeps only the remedy still tells a person
    where to look; and not the default remediation, which is about
    submodules and would send them to the wrong place."""
    body, offset = NOT_UTF8[case]
    path = tmp_path / "plan.yaml"
    path.write_bytes(body)
    refusal = refusal_for(path)
    assert refusal.remediation.startswith("Remediation: ")
    assert "UTF-8" in refusal.remediation
    assert f"Byte {offset}" in refusal.remediation
    assert "git submodule" not in refusal.remediation
    assert str(refusal).startswith(f"REFUSED yaml-unreadable: {path}")
    assert str(refusal).endswith(refusal.remediation)


def test_a_missing_file_is_still_yaml_unreadable(tmp_path):
    path = tmp_path / "absent.yaml"
    refusal = refusal_for(path)
    assert refusal.code == "yaml-unreadable"
    assert str(path) in refusal.detail
    assert isinstance(refusal.__cause__, OSError)


def test_yaml_this_reader_does_not_implement_is_still_yaml_unparsable(tmp_path):
    path = tmp_path / "tabbed.yaml"
    path.write_text("legs:\n\t- role: spec\n", encoding="utf-8")
    refusal = refusal_for(path)
    assert refusal.code == "yaml-unparsable"
    assert str(path) in refusal.detail


def test_utf8_that_is_not_ascii_is_read_not_refused(tmp_path):
    """The new `except` is for bytes that are not UTF-8, not for text that is
    not ASCII: a name with an accent is a valid file."""
    path = tmp_path / "plan.yaml"
    path.write_bytes("name: café\nnote: \"—\"\n".encode("utf-8"))
    assert load_yaml(path) == {"name": "café", "note": "—"}


# --- #1168: the file is named as `shown_path` names it -----------------------

#: A folder name holding a bidi override, U+202E, which reorders the line
#: around it so that a path reads as another path. A Windows file name can
#: hold it, so it needs no mark.
RLO_NAME = "wd-pl" + chr(0x202E) + "an"

#: The three the issue probed: U+202E, an ESC, and a line feed that begins a
#: line of the path's choosing (`conftest.UNSAFE_NAMES`, POSIX only).
UNPRINTABLE = [pytest.param(RLO_NAME, id="U+202E"), *UNSAFE_NAMES]

#: `UNPRINTABLE`, and a name a line names byte for byte as it always did.
NAMES = [*UNPRINTABLE, pytest.param(PRINTABLE_NAME, id="printable")]

#: Text this reader refuses, and what it says after the path about it.
UNPARSABLE = "a: 1\n: b\n"
NOT_PARSED = "line 2: empty keys are not supported"

#: Each way `load_yaml` refuses: the bytes at the path (None: nothing is
#: there), and the code.
WAYS = {
    "absent": (None, "yaml-unreadable"),
    "not-utf-8": (b"name: caf\xe9\n", "yaml-unreadable"),
    "unparsable": (UNPARSABLE.encode("utf-8"), "yaml-unparsable"),
}


def refused_under(tmp_path, name: str, way: str) -> tuple:
    """`(path, refusal)` for a `plan.yaml` refused `way`, in a folder `name`
    made under `tmp_path`."""
    body = WAYS[way][0]
    path = unsafe_folder(tmp_path, name) / "plan.yaml"
    if body is not None:
        path.write_bytes(body)
    return path, refusal_for(path)


def said_after_the_path(refusal: Refusal) -> str:
    """The words a refusal says after `<path>: `, from its own cause: the
    system's reason, the byte and Python's reason, or the reader's line."""
    cause = refusal.__cause__
    if isinstance(cause, OSError):
        return f"cannot be read ({cause.strerror})"
    if isinstance(cause, UnicodeDecodeError):
        return f"not UTF-8 at byte {cause.start} ({cause.reason})"
    return NOT_PARSED


@pytest.mark.parametrize("way", sorted(WAYS))
@pytest.mark.parametrize("name", UNPRINTABLE)
def test_each_refusal_names_a_path_that_is_not_printable_as_repr(
        tmp_path, name, way):
    """THE ISSUE'S THREE SITES, in process: the path as `repr` spells it, so
    no character of the folder's name reaches the line raw and the detail
    stays one line. On main each named it raw."""
    path, refusal = refused_under(tmp_path, name, way)
    assert refusal.code == WAYS[way][1]
    assert refusal.detail == f"{spelt(path)}: {said_after_the_path(refusal)}"
    assert name not in str(refusal), ascii(str(refusal))
    assert_shown_safe(str(refusal))


@pytest.mark.parametrize("way", sorted(WAYS))
def test_a_printable_path_is_named_byte_for_byte_as_it_was(tmp_path, way):
    """The control, which passes on main as well: a space and a letter past
    ASCII are printable, so the path is named as it is, with no quotes."""
    path, refusal = refused_under(tmp_path, PRINTABLE_NAME, way)
    assert refusal.detail == f"{path}: {said_after_the_path(refusal)}"


@pytest.mark.parametrize("name", NAMES)
def test_a_policy_that_is_not_a_mapping_is_named_as_shown_path_names_it(
        tmp_path, name):
    """`policy-unreadable`, the line after `load_yaml` in `NamingPolicy.load`,
    names the file the same way."""
    policy = unsafe_folder(tmp_path, name) / "repository-naming.yaml"
    policy.write_text("- a list\n", encoding="utf-8")
    with pytest.raises(Refusal) as caught:
        NamingPolicy.load(policy)
    assert caught.value.code == "policy-unreadable"
    assert caught.value.detail == f"{named_as(policy, name)}: not a mapping"


# --- each tool that hands `load_yaml` a path it was given -------------------

#: A commit nothing holds, for the two commands that ask one before they read.
A_COMMIT = "1" * 40

#: The template's validators, and the library a root keeps beside them.
TEMPLATE_SCRIPTS = REPO / "templates" / "assembly-root" / "scripts"
LIBRARY = REPO / "scripts" / "repo_shape.py"


def unparsable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(UNPARSABLE, encoding="utf-8")
    return path


def a_root(folder: Path, gate: bytes, library: bytes, name: str) -> Path:
    """A git repository at `<folder>/Atlas` carrying `scripts/<name>` as
    `gate` and `scripts/repo_shape.py` as `library`, as an assembly root
    carries them, with a `project.yaml` that does not parse."""
    root = folder / "Atlas"
    (root / "scripts").mkdir(parents=True)
    git("init", "-q", str(root), cwd=folder)
    (root / "scripts" / name).write_bytes(gate)
    (root / "scripts" / "repo_shape.py").write_bytes(library)
    unparsable(root / "project.yaml")
    return root


def adopt_check(folder: Path, tmp_path: Path) -> tuple:
    plan = unparsable(folder / "adoption-plan.yaml")
    return plan, (ADOPT, "check", "--plan", str(plan))


def adopt_plan(folder: Path, tmp_path: Path) -> tuple:
    policy = unparsable(folder / "path-policy.yaml")
    source = make_source_repo(tmp_path / "Thing", {"README.md": "# Thing\n"},
                              edits=())
    return policy, (ADOPT, "plan", "--source", str(source), "--project",
                    "Northwind", "--org", "testorg", "--elected-by",
                    "Test Human", "--elected-on", "2026-09-02", "--out",
                    str(tmp_path / "adoption-plan.yaml"), "--path-policy",
                    str(policy))


def naming_policy(folder: Path, tmp_path: Path) -> tuple:
    policy = unparsable(folder / "repository-naming.yaml")
    return policy, (REPO / "scripts" / "validate-repository-naming.py",
                    "--policy", str(policy), "Atlas")


def naming_project(folder: Path, tmp_path: Path) -> tuple:
    manifest = unparsable(folder / "project.yaml")
    return manifest, (REPO / "scripts" / "validate-repository-naming.py",
                      "--project", str(manifest))


def bump_leg(folder: Path, tmp_path: Path) -> tuple:
    return unparsable(folder / "project.yaml"), (
        REPO / "scripts" / "bump-leg.py", "--root", str(folder), "--leg",
        "spec", "--to", A_COMMIT, "--dry-run")


def family_bump(folder: Path, tmp_path: Path) -> tuple:
    return unparsable(folder / "family.yaml"), (
        REPO / "scripts" / "family.py", "bump", "--dry-run", "--family-root",
        str(folder), "--member", "Atlas", "--to", A_COMMIT)


def update_shape(folder: Path, tmp_path: Path) -> tuple:
    git("init", "-q", str(folder), cwd=tmp_path)
    return unparsable(folder / "contracts" / "shape-pin.yaml"), (
        REPO / "update-shape.py", "check", "--root", str(folder))


def validate_manifest(folder: Path, tmp_path: Path) -> tuple:
    gate = "validate-manifest.py"
    root = a_root(folder, (TEMPLATE_SCRIPTS / gate).read_bytes(),
                  LIBRARY.read_bytes(), gate)
    return root / "project.yaml", (root / "scripts" / gate, "--root",
                                   str(root))


#: The issue's table: every tool that hands `load_yaml` a path typed, or
#: built from one typed, and how one run of it reaches that refusal.
TOOLS = {
    "adopt-check--plan": adopt_check,
    "adopt-plan--path-policy": adopt_plan,
    "naming--policy": naming_policy,
    "naming--project": naming_project,
    "bump-leg--root": bump_leg,
    "family-bump--family-root": family_bump,
    "update-shape-check--root": update_shape,
    "validate-manifest--root": validate_manifest,
}


def refused_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("REFUSED ")]


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("tool", sorted(TOOLS))
def test_each_tool_names_the_file_load_yaml_refuses_as_shown_path_names_it(
        tmp_path, tool, name):
    """THE ISSUE'S PROBE, through each tool: one `REFUSED yaml-unparsable`
    line, exit 2, the file named as `shown_path` names it, and no U+202E,
    ESC or forged line anywhere in the output. On main each tool printed
    the path raw; a printable one is named as it always was."""
    named, argv = TOOLS[tool](unsafe_folder(tmp_path, name), tmp_path)
    result = run_script(*argv)
    said = result.stdout + result.stderr
    assert result.returncode == 2, said
    assert refused_lines(result.stderr) == [
        f"REFUSED yaml-unparsable: {named_as(named, name)}: {NOT_PARSED}"], (
        ascii(said))
    assert chr(0x202E) not in said, ascii(said)
    assert_shown_safe(result.stdout, result.stderr)


@pytest.mark.parametrize("name", UNPRINTABLE)
def test_a_path_typed_relative_is_named_as_typed_and_spelled(tmp_path, name):
    """The rows above type a path under `tmp_path`, which is absolute, so a
    `load_yaml` that named `Path(path).absolute()` would pass every one of
    them (rv1274's X5). This one types the file relative to the folder the
    tool runs in: the refusal names it as typed, still relative, and spelled
    as `repr` spells it. `adopt-project.py check --plan` is one of the tools
    that names the file it was handed; the four that are given a root build
    an absolute path of their own before `load_yaml` sees it."""
    plan = unparsable(unsafe_folder(tmp_path, name) / "adoption-plan.yaml")
    typed = str(plan.relative_to(tmp_path))
    result = run_script(ADOPT, "check", "--plan", typed, cwd=tmp_path)
    said = result.stdout + result.stderr
    assert result.returncode == 2, said
    assert refused_lines(result.stderr) == [
        f"REFUSED yaml-unparsable: {spelt(typed)}: {NOT_PARSED}"], ascii(said)
    assert chr(0x202E) not in said, ascii(said)
    assert_shown_safe(result.stdout, result.stderr)


# --- the readers that find the path in the detail by its text ---------------

#: The commit before #1168: its `repo_shape.py` names the file raw, and its
#: `validate-pins.py` asks the raw prefix alone.
BEFORE_1168 = "51a9c5f103cd02c9b9e01e8a4c1acd95f791451e"
PINS = "validate-pins.py"


def before_1168(relative: str, holds: bytes) -> bytes:
    """`relative` at `BEFORE_1168`, or a skip where this checkout does not
    hold that history; it must hold `holds`, or the row would test nothing
    older than this tree."""
    shown = subprocess.run(["git", "show", f"{BEFORE_1168}:{relative}"],
                           cwd=str(REPO), capture_output=True, check=False)
    if shown.returncode != 0:
        pytest.skip(f"needs {BEFORE_1168} in this checkout's history")
    assert holds in shown.stdout, relative
    return shown.stdout


def older_library() -> bytes:
    return before_1168("scripts/repo_shape.py",
                       b'f"{path}: {where}{exc}"')


def older_gate() -> bytes:
    return before_1168(f"templates/assembly-root/scripts/{PINS}",
                       b'absolute = f"{path}: "')


def gate_refused(folder: Path, gate: bytes, library: bytes) -> tuple:
    """`(root, result)`: the root's own `validate-pins.py`, run over a root
    under `folder` whose `project.yaml` does not parse."""
    root = a_root(folder, gate, library, PINS)
    result = run_script(root / "scripts" / PINS, cwd=root)
    assert result.returncode == 2, result.stdout + result.stderr
    assert_shown_safe(result.stdout, result.stderr)
    return root, result


#: What the gate says: the file named relative to the root, beside either
#: library.
RELATIVE = f"REFUSED yaml-unparsable: project.yaml: {NOT_PARSED}"


@pytest.mark.parametrize("name", NAMES)
def test_the_gate_names_the_file_from_the_root_beside_this_library(
        tmp_path, name):
    """`validate-pins.py` beside the `repo_shape.py` of this tree, which
    spells a root that is not printable: the gate finds `_shown`'s prefix
    and names the file `project.yaml`, as it always did. With main's gate
    beside this library the prefix was not found, and the line named the
    whole path."""
    _root, result = gate_refused(unsafe_folder(tmp_path, name),
                                 (TEMPLATE_SCRIPTS / PINS).read_bytes(),
                                 LIBRARY.read_bytes())
    assert refused_lines(result.stderr) == [RELATIVE], ascii(result.stderr)


@pytest.mark.parametrize("name", NAMES)
def test_the_gate_names_the_file_from_the_root_beside_an_older_library(
        tmp_path, name):
    """THE SKEW RULE, one way: a root that kept a `repo_shape.py` older than
    #1168 (`update-shape.py apply --accept-local`), which names the path
    raw. The gate still finds the raw prefix, and names `project.yaml`."""
    _root, result = gate_refused(unsafe_folder(tmp_path, name),
                                 (TEMPLATE_SCRIPTS / PINS).read_bytes(),
                                 older_library())
    assert refused_lines(result.stderr) == [RELATIVE], ascii(result.stderr)


@pytest.mark.parametrize("name", UNPRINTABLE)
def test_an_older_gate_beside_this_library_names_the_whole_path_spelled(
        tmp_path, name):
    """THE SKEW RULE, the other way: a root that kept a `validate-pins.py`
    older than #1168 beside this `repo_shape.py`. That gate asks the raw
    prefix alone, which a spelled path does not start with, so it says the
    library's own line: the whole path, spelled, and nothing raw. Named
    relative again once the gate is re-copied (the row above). A printable
    root is named relative by either gate."""
    root, result = gate_refused(unsafe_folder(tmp_path, name), older_gate(),
                                LIBRARY.read_bytes())
    assert refused_lines(result.stderr) == [
        f"REFUSED yaml-unparsable: {spelt(root / 'project.yaml')}: "
        f"{NOT_PARSED}"], ascii(result.stderr)
    assert name not in result.stdout + result.stderr


def named_raw(path):
    """`load_yaml` as a library older than #1168 is: the same data, and the
    same refusal from the same cause with the path at its start raw."""
    try:
        return load_yaml(path)
    except Refusal as exc:
        spelled, detail = f"{shown_path(path)}: ", exc.detail
        if detail.startswith(spelled):
            detail = f"{path}: {detail[len(spelled):]}"
        raise Refusal(exc.code, detail, exc.remediation) from exc.__cause__


#: The library a reader meets: this tree's, which spells a path that is not
#: printable, and one older than #1168, which names it raw.
LOADERS = [pytest.param(load_yaml, id="this-library"),
           pytest.param(named_raw, id="an-older-library")]


@pytest.mark.parametrize("loader", LOADERS)
@pytest.mark.parametrize("name", NAMES)
def test_the_gates_load_takes_either_prefix(tmp_path, monkeypatch, name,
                                            loader):
    """Both halves of `_load`'s prefix test, in process and with no history:
    the path `_shown` spells and the path raw are each named relative to
    the root."""
    gate = load_without_bytecode(TEMPLATE_SCRIPTS / PINS,
                                 "load_yaml_refusals_pins")
    monkeypatch.setattr(gate, "load_yaml", loader)
    root = unsafe_folder(tmp_path, name)
    manifest = unparsable(root / "project.yaml")
    with pytest.raises(Refusal) as caught:
        gate._load(root, manifest)
    assert caught.value.detail == f"project.yaml: {NOT_PARSED}"


@pytest.mark.parametrize("name", NAMES)
def test_a_link_manifest_is_named_in_why_as_it_was(tmp_path, name):
    """`link_declarations` swaps the raw path for `shown_path`'s in a
    refusal's detail (#610). The detail holds that spelling now, so the
    swap finds nothing to do and `why` reads as it did."""
    tree = unsafe_folder(tmp_path, name)
    manifest = unparsable(tree / "project.yaml")
    assert link_declarations(tree) == (
        None, f"{named_as(manifest, name)}: {NOT_PARSED}")


#: What `family.py add` names a member's manifest that it read out of a
#: throwaway clone.
MEMBER_MANIFEST = "acme/Atlas @ 0123456789ab:project.yaml"


@pytest.mark.parametrize("loader", LOADERS)
@pytest.mark.parametrize("name", NAMES)
def test_family_names_a_members_manifest_as_its_caller_named_it(
        tmp_path, monkeypatch, name, loader):
    """`_read_member_project` names the clone's `project.yaml` by what was
    cloned, for the clone is gone when the line is read (#203). Its clone
    is under `TMPDIR`; one whose path is not printable is spelled in the
    detail, and the swap looks for either spelling, so the line names the
    member as it always did. With main's `family.py` beside this library
    it named the deleted clone."""
    family = load_without_bytecode(REPO / "scripts" / "family.py",
                                   "load_yaml_refusals_family")
    monkeypatch.setattr(family, "load_yaml", loader)
    clone = unsafe_folder(tmp_path, name)
    unparsable(clone / "project.yaml")
    with pytest.raises(Refusal) as caught:
        family._read_member_project(clone, "Atlas", "acme/Atlas",
                                    shown=MEMBER_MANIFEST)
    assert caught.value.code == "yaml-unparsable"
    assert caught.value.detail == f"{MEMBER_MANIFEST}: {NOT_PARSED}"


def doctor_module():
    return load_without_bytecode(REPO / "shape-doctor.py",
                                 "load_yaml_refusals_doctor")


def policy_refusal(shape: Path, text: str) -> Refusal:
    """The refusal this checkout's naming policy gives where it holds
    `text`, as the naming script prints it."""
    policy = shape / "contracts" / "repository-naming.yaml"
    policy.parent.mkdir(parents=True)
    policy.write_text(text, encoding="utf-8")
    with pytest.raises(Refusal) as caught:
        NamingPolicy.load(policy)
    return caught.value


@pytest.mark.parametrize("text, code", [
    pytest.param(UNPARSABLE, "yaml-unparsable", id="load-yaml"),
    pytest.param("- a list\n", "policy-unreadable", id="not-a-mapping"),
    pytest.param("kind: something-else\n", "policy-wrong-kind",
                 id="wrong-kind"),
])
@pytest.mark.parametrize("name", NAMES)
def test_the_doctor_finds_its_own_policy_in_the_naming_scripts_refusal(
        tmp_path, name, text, code):
    """`naming_script_refusal` knows the checkout's own policy by the path
    at the start of the detail. `load_yaml`, `policy-unreadable` and, since
    #1279, `policy-wrong-kind` spell it now, and the doctor asks that
    spelling too. Named raw, a line feed split the wrong kind's line, and
    the doctor did not find its own policy in it."""
    shape = unsafe_folder(tmp_path, name)
    refusal = policy_refusal(shape, text)
    found = doctor_module().naming_script_refusal(shape, f"{refusal}\n")
    assert found is not None, ascii(str(refusal))
    assert (found.code, found.detail) == (code, refusal.detail)


@pytest.mark.parametrize("name", [
    pytest.param(RLO_NAME, id="U+202E"), UNSAFE_NAMES[0],
    pytest.param(PRINTABLE_NAME, id="printable"),
])
def test_the_doctor_still_finds_its_own_policy_named_raw(tmp_path, name):
    """A root's `repo_shape.py` from before #1279 names the policy raw in
    `policy-wrong-kind`, and the doctor still finds it by that prefix. The
    line is built as that library prints it, since this checkout's spells
    it. A line feed splits that line, so it is not among the names here."""
    shape = unsafe_folder(tmp_path, name)
    policy = policy_refusal(shape, "kind: something-else\n")
    assert policy.code == "policy-wrong-kind"
    refusal = Refusal(policy.code,
                      f"{shape / 'contracts' / 'repository-naming.yaml'}: "
                      "kind is 'something-else', expected "
                      "'repository-naming-policy'")
    found = doctor_module().naming_script_refusal(shape, f"{refusal}\n")
    assert found is not None, ascii(str(refusal))
    assert found.detail == refusal.detail


@pytest.mark.parametrize("loader", LOADERS)
@pytest.mark.parametrize("name", NAMES)
def test_the_doctors_manifest_kinds_row_quotes_the_refusal_less_its_path(
        project, tmp_path, monkeypatch, name, loader):
    """`manifest-kinds` quotes `load_yaml`'s refusal of a file under
    `contracts/` less the path it opens with, which the row has just named
    relative to the root, in either spelling (`less_the_path`). With main's
    doctor beside this library, a root that is not printable had its whole
    path quoted again."""
    root = copied_under(project, tmp_path, name)
    unparsable(root / "contracts" / "n1168.yaml")
    doctor = doctor_module()
    monkeypatch.setattr(doctor, "load_yaml", loader)
    row = doctor.check_manifest_kinds(doctor.Context(root))
    assert row.detail["refusals"]["contracts/n1168.yaml"] == {
        "code": "yaml-unparsable", "detail": NOT_PARSED}, row.detail
    assert (f"unreadable as YAML: contracts/n1168.yaml (yaml-unparsable: "
            f"{NOT_PARSED})") in row.reason, ascii(row.reason)
