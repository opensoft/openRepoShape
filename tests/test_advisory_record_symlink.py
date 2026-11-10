# SPDX-License-Identifier: Apache-2.0
"""`project.yaml`, `family.yaml` and `single-repository.yaml` committed as
symlinks, as the Triad advisory reads them in a commit: #1272, in
`scripts/shape_advisory.py`, beside #1163's `AGENTS.md`
(`tests/test_advisory_agents_md_symlink.py`).

THE DEFECT. `adopt-project.py plan` and `check` ask the advisory of the
commit the plan is written against, and in a commit a symlink is a blob that
holds the PATH it leads to. Three readers took that path as YAML. The doctor
reads the disk, where the operating system follows the link. Measured on
#1270's head `8e54c32de`, Python 3.12.3 and git 2.43.0:

  * `project.yaml -> docs/project.yaml`, a Triad manifest: the commit read
    `advise`, and `plan` and `check` printed the `triad` lines, where the
    disk read `triad-root`. Beside a leg's `AGENTS.md` the commit read
    `leg-clone`, and both printed the leg's NOTE. `family.yaml ->
    docs/family.yaml`, a holder's manifest: `advise`, where the disk read
    `family-holder`;
  * `single-repository.yaml -> docs/record.yaml`, a record: `advise` with
    the NOTE `it could not be read (YamlError)`, false of a file that can be
    read, where the disk read `recorded-single`. Every other link to the
    record got the same NOTE, and one whose path is spelled as a record's
    `kind:` line silenced the advisory.

THE CHANGE, in two parts.

  * `_read_mapping` FOLLOWS a manifest's link inside the commit, through
    #1270's `Tree.is_link` and `Tree.text_through`, so `project.yaml` and
    `family.yaml` read as they do on the disk. Nothing that is a file inside
    the commit is a manifest it sees: a link that dangles, loops, runs
    through a file, leads to a directory, or leads OUT of the commit reads
    as no manifest, as `_read_mapping` already reads a manifest it cannot
    read.
  * `read_record` DOES NOT FOLLOW the record's link, and says so. Every link
    in the commit silences nothing, with a sentence that calls it a symlink
    and names no exception. Following it would give a linked record the
    record's question in `plan`, with its default `drop` (#528), and that
    ruling is Brett Heap's to make. So `plan` still asks the general question
    of it, `check` still exits 1, and the doctor's audit of a leg's index
    reads it as before.

Every case here makes a symlink, and skips where none can be made
(`symlink`, #1159's).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from conftest import ADOPT, REPO, findings, git, load_without_bytecode
#: The two questions a `single-repository.yaml` can be asked, the plan's
#: entry for a path, and the doctor's audit of a code leg's index
#: (`audit_leg`, #691), from #528's file.
from test_adopt_single_repository_record import (
    GENERAL, RULE, entry_of, leg_audited,
)
#: The reading of HEAD's commit as `adopt-project.py` asks it, `plan` and
#: `check` as a person meets them, their silence, and the advisory's first
#: words, from #1270's file.
from test_advisory_agents_md_symlink import (
    SINGLE, adopt_says, committed, told_nothing,
)
#: The environment with no `workspace.yaml`, and the link maker that skips
#: where none can be made, from #1159's file.
from test_doctor_unsearchable_links import no_workspace, symlink
#: A commit of the whole working tree, a one-commit repository, the
#: doctor's `--json` rows, the schema's own example record and a leg's
#: `AGENTS.md`, from the file that owns them.
from test_shape_advisory import (
    commit_all, doctor_json, record_text, rendered_leg_agents, repository,
)

sys.path.insert(0, str(REPO / "scripts"))
import shape_advisory  # noqa: E402
from repo_shape import Refusal  # noqa: E402

PROJECT = shape_advisory.PROJECT_MANIFEST
FAMILY = shape_advisory.FAMILY_MANIFEST
RECORD = shape_advisory.RECORD_FILE
AGENTS = shape_advisory.AGENTS_MD
ADVISE = shape_advisory.ADVISE
TRIAD_ROOT = shape_advisory.TRIAD_ROOT
FAMILY_HOLDER = shape_advisory.FAMILY_HOLDER
RECORDED_SINGLE = shape_advisory.RECORDED_SINGLE

#: A Triad assembly root's manifest, as small as the detector allows: the
#: schema, and an assembly, a spec and a code leg.
TRIAD = ("schema_version: 1\nkind: project-manifest\n"
         "schema: project-repo-schema\nlegs:\n"
         "  - role: assembly\n    path: \".\"\n"
         "  - role: spec\n    path: spec\n"
         "  - role: code\n    path: code\n")
#: A family holder's manifest.
HOLDER = "schema_version: 1\nkind: family-manifest\nid: inkrouter\nmembers: []\n"
#: A file of another kind, linked as a record.
OTHER_KIND = "schema_version: 1\nkind: release-config\n"
#: Why a linked record silences nothing, SPELLED OUT, as `read()` gives it:
#: a symlink, not followed, and no exception's name.
LINK_REASON = ("it is a symlink in the commit, which is not followed for "
               "this record, so whether it records that this project stays "
               "a single repository is not known here")
#: The same, as `plan` and `check` print it.
LINK_NOTE = (f"NOTE {RECORD} does not silence this: {LINK_REASON} (its schema "
             "is openRepoShape's contracts/single-repository-record.yaml); "
             "nothing fails on its account.")
#: `check`'s findings: an entry nobody answered, and a link the plan keeps
#: in the root.
UNRESOLVED = "plan-unresolved"
ROOT_LINK = "plan-root-symlink"


@pytest.fixture(scope="module")
def adopter():
    """`adopt-project.py`, as the doctor loads it."""
    return load_without_bytecode(ADOPT, "adopt_project_record_symlink")


@pytest.fixture(scope="module")
def doctor():
    return load_without_bytecode(REPO / "shape-doctor.py",
                                 "shape_doctor_record_symlink")


def linked_here(tmp_path: Path, name: str, target: Path | str,
                files: dict | None = None,
                links: dict | None = None) -> Path:
    """`<tmp>/Atlas`, a repository with no `origin` whose `name` is a symlink
    to `target`, beside `files` (`{relative path: text or bytes}`) and
    `links` (`{relative path: target}`), all of it committed.

    #1270's `linked_clone` links `AGENTS.md`, which the reading asks before
    the record, so its answer would come first; this links `name` and
    nothing else. A `str` target is linked as spelled, which the link is
    checked to hold, as there."""
    root = tmp_path / "Atlas"
    root.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=root)
    (root / "README.md").write_text("# here\n", encoding="utf-8")
    for rel, text in (files or {}).items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        if isinstance(text, bytes):
            (root / rel).write_bytes(text)
        else:
            (root / rel).write_text(text, encoding="utf-8")
    for rel, to in {**(links or {}), name: target}.items():
        symlink(root / rel, to)
    if isinstance(target, str):
        assert os.readlink(root / name) == target
    commit_all(root, "Initial import")
    return root


# --- the manifests: followed inside the commit -------------------------------

@pytest.mark.parametrize("name, target, files, links, state, codes", [
    pytest.param(PROJECT, Path("docs", PROJECT), {"docs/project.yaml": TRIAD},
                 {}, TRIAD_ROOT, [UNRESOLVED, ROOT_LINK], id="project-yaml"),
    pytest.param(PROJECT, Path("docs", PROJECT),
                 {"docs/project.yaml": TRIAD,
                  AGENTS: rendered_leg_agents("spec")},
                 {}, TRIAD_ROOT, [UNRESOLVED, ROOT_LINK],
                 id="project-yaml-beside-a-leg-agents-md"),
    pytest.param(FAMILY, Path("docs", FAMILY), {"docs/family.yaml": HOLDER},
                 {}, FAMILY_HOLDER, [UNRESOLVED], id="family-yaml"),
    pytest.param(PROJECT, "./docs/project.yaml", {"docs/project.yaml": TRIAD},
                 {}, TRIAD_ROOT, [UNRESOLVED, ROOT_LINK],
                 id="project-yaml-dot-slash"),
    pytest.param(FAMILY, Path("conf", FAMILY), {"docs/family.yaml": HOLDER},
                 {"conf": Path("docs")}, FAMILY_HOLDER,
                 [UNRESOLVED, UNRESOLVED],
                 id="family-yaml-through-a-linked-folder"),
])
def test_a_manifest_linked_inside_the_commit_is_read_through_it(
        tmp_path, name, target, files, links, state, codes):
    """#1272's rows 2a, 2b and 3. On #1270's head the commit's link was read
    as the path it holds, which is no manifest, so `plan` and `check`
    printed the `triad` lines over an assembly root and a family holder, and
    the leg's NOTE where a regular leg `AGENTS.md` sits beside the root's
    manifest (`project.yaml` is read first on the disk, and was not in the
    commit). Now the link is followed inside the commit, as the disk's is,
    spelled with a `.` segment or through a linked folder too, and neither
    prints a Triad line. `check` exits 1 here as over a regular manifest of
    the repository's own, an open question; only the advisory differs."""
    root = linked_here(tmp_path, name, target, files, links)
    env = no_workspace(tmp_path)
    reading = committed(root, env)
    assert reading.state == state, reading.as_dict()
    assert shape_advisory.read(root, env=env).state == state
    plan = tmp_path / "plan.yaml"
    told_nothing(adopt_says(root, plan, env))
    assert [code for code, _ in findings(plan)] == codes


@pytest.mark.parametrize("how", [
    "dangling", "loop", "a-directory", "through-a-file", "not-utf-8",
    "spelled-as-a-manifest", "dangling-in-the-commit-there-on-the-disk",
    "out-of-the-commit", "out-of-the-commit-by-its-absolute-path"])
def test_a_manifest_link_to_no_file_in_the_commit_is_no_manifest(tmp_path,
                                                                  how):
    """THE CHOICE: nothing that is a file inside the commit is a manifest
    the commit reading sees, as `_read_mapping` reads every manifest it
    cannot read. The plan is written against the commit, and a manifest the
    commit does not hold declares nothing in it, so the clone is advised.

    The disk agrees where the link reaches nothing: one that dangles, loops,
    runs through a file or leads to a directory, and one to a file that is
    not UTF-8: a Triad manifest with a byte 0xff in a value of its own,
    which the disk reads as no manifest (`_read_mapping`), and which the
    followed blob decoded with `errors="replace"` would make a Triad root
    (r1163's R6). A link spelled `kind: family-manifest` dangles too: on
    #1270's head its PATH parsed as a holder's manifest, and the commit
    said `family-holder` where the disk advised.

    The disk does not agree where the link reaches a manifest the commit
    does not hold: one committed dangling and written on the disk after,
    and one that leads out of the commit, relative or absolute. The doctor
    reads `triad-root` there, and `plan` and `check` print the advisory,
    as on #1270's head: the commit reading never reads the disk."""
    beside = tmp_path / "elsewhere" / PROJECT
    name, target, files = {
        "dangling": (PROJECT, Path("docs", PROJECT),
                     {"docs/notes.md": "# notes\n"}),
        "loop": (PROJECT, Path(PROJECT), {}),
        "a-directory": (PROJECT, Path("docs"), {"docs/project.yaml": TRIAD}),
        "through-a-file": (PROJECT, Path("README.md", PROJECT), {}),
        "not-utf-8": (PROJECT, Path("docs", PROJECT),
                      {"docs/project.yaml": (TRIAD.encode("utf-8")
                                             + b"name: Atlas\xff\n")}),
        "spelled-as-a-manifest": (FAMILY, "kind: family-manifest", {}),
        "dangling-in-the-commit-there-on-the-disk": (
            PROJECT, Path("docs", PROJECT), {"docs/notes.md": "# notes\n"}),
        "out-of-the-commit": (PROJECT, Path("..", "elsewhere", PROJECT), {}),
        "out-of-the-commit-by-its-absolute-path": (PROJECT, beside, {}),
    }[how]
    if how.startswith("out-of-the-commit"):
        beside.parent.mkdir()
        beside.write_text(TRIAD, encoding="utf-8")
    root = linked_here(tmp_path, name, target, files)
    if how == "dangling-in-the-commit-there-on-the-disk":
        (root / "docs" / PROJECT).write_text(TRIAD, encoding="utf-8")
    env = no_workspace(tmp_path)
    reading = committed(root, env)
    assert reading.state == ADVISE, reading.as_dict()
    assert reading.record_problems == ()
    disk = shape_advisory.read(root, env=env).state
    if how.startswith(("out-of-the-commit", "dangling-in-the-commit")):
        assert disk == TRIAD_ROOT
        for stdout in adopt_says(root, tmp_path / "plan.yaml", env):
            assert stdout.count(SINGLE) == 1, stdout
    else:
        assert disk == ADVISE


# --- the record: named as a link, and never followed ---------------------------

def test_a_record_linked_to_a_record_in_the_commit_is_named_as_a_link(
        tmp_path):
    """#1272's row 1. On #1270's head the commit's link was read as the path
    it holds, which does not parse, and `plan` and `check` printed the
    `triad` lines with `NOTE single-repository.yaml does not silence this:
    it could not be read (YamlError)`, false of a file that can be read.

    Now the NOTE says what is true: it is a symlink in the commit, which is
    not followed for the record. The rest is as on #1270's head, ON PURPOSE:
    the link is not followed until Brett Heap rules whether a linked record
    takes the record's question and its default `drop` (#528), so the entry
    is still the general question with `leg: null`, `check` still exits 1 on
    it, and the advisory is still given where the doctor, which reads the
    disk through the link, says nothing (`recorded-single`)."""
    root = linked_here(tmp_path, RECORD, Path("docs", "record.yaml"),
                       {"docs/record.yaml": record_text()})
    env = no_workspace(tmp_path)
    reading = committed(root, env)
    assert reading.state == ADVISE, reading.as_dict()
    assert reading.record_problems == (LINK_REASON,)
    assert shape_advisory.read(root, env=env).state == RECORDED_SINGLE
    plan = tmp_path / "plan.yaml"
    for stdout in adopt_says(root, plan, env):
        assert stdout.count(SINGLE) == 1, stdout
        assert stdout.splitlines().count(LINK_NOTE) == 1, stdout
        assert "could not be read" not in stdout, stdout
    entry = entry_of(plan, RECORD)
    assert (entry["leg"], entry["rule"]) == (None, GENERAL), entry
    [(code, _detail)] = findings(plan)
    assert code == UNRESOLVED
    exit_code, rows, _payload = doctor_json(root, env)
    assert exit_code == 2
    assert "triad-advisory" not in rows, rows["triad-advisory"]


@pytest.mark.parametrize("how, disk", [
    pytest.param(how, disk, id=how) for how, disk in (
        ("dot-slash", RECORDED_SINGLE),
        ("through-a-linked-folder", RECORDED_SINGLE),
        ("another-kind", ADVISE),
        ("dangling", ADVISE),
        ("loop", ADVISE),
        ("a-directory", ADVISE),
        ("through-a-file", ADVISE),
        ("not-utf-8", ADVISE),
        ("out-of-the-commit", RECORDED_SINGLE),
        ("out-of-the-commit-by-its-absolute-path", RECORDED_SINGLE))])
def test_every_link_to_the_record_is_named_as_one_and_never_followed(
        tmp_path, how, disk):
    """#1272's Verify list, for a record that is not followed: whatever the
    link leads to -- a record (spelled with a `.` segment, or through a
    linked folder), a file of another kind, nothing (it dangles, loops,
    runs through a file or leads to a directory), a file that is not UTF-8,
    or a record out of the commit, relative or absolute -- the commit says
    it is a symlink, which is not followed, and names no exception. On
    #1270's head each said `it could not be read (YamlError)`. The disk
    reads through the link, as the doctor does, and is unchanged."""
    record = record_text()
    beside = tmp_path / "elsewhere" / "record.yaml"
    target, files, links = {
        "dot-slash": ("./docs/record.yaml", {"docs/record.yaml": record}, {}),
        "through-a-linked-folder": (Path("conf", "record.yaml"),
                                    {"docs/record.yaml": record},
                                    {"conf": Path("docs")}),
        "another-kind": (Path("docs", "other.yaml"),
                         {"docs/other.yaml": OTHER_KIND}, {}),
        "dangling": (Path("docs", "record.yaml"),
                     {"docs/notes.md": "# notes\n"}, {}),
        "loop": (Path(RECORD), {}, {}),
        "a-directory": (Path("docs"), {"docs/notes.md": "# notes\n"}, {}),
        "through-a-file": (Path("README.md", RECORD), {}, {}),
        "not-utf-8": (Path("docs", "record.yaml"),
                      {"docs/record.yaml": record.encode("utf-8") + b"\xff"},
                      {}),
        "out-of-the-commit": (Path("..", "elsewhere", "record.yaml"), {}, {}),
        "out-of-the-commit-by-its-absolute-path": (beside, {}, {}),
    }[how]
    if how.startswith("out-of-the-commit"):
        beside.parent.mkdir()
        beside.write_text(record, encoding="utf-8")
    root = linked_here(tmp_path, RECORD, target, files, links)
    env = no_workspace(tmp_path)
    reading = committed(root, env)
    assert reading.state == ADVISE, reading.as_dict()
    assert reading.record_problems == (LINK_REASON,)
    assert shape_advisory.read(root, env=env).state == disk


def test_a_record_link_whose_path_is_spelled_as_a_record_is_no_record(
        tmp_path):
    """THE ONE CASE WHERE `plan`'S RECORD QUESTION MOVES. A link whose PATH
    is `kind: single-repository-record` dangles, and the disk advises. On
    #1270's head its path parsed as a record: the commit said
    `recorded-single`, `plan` printed no advisory and wrote `leg: drop`
    under the record's rule, and `check` exited 0. A path is not the
    record, so it is named as a link like every other: the advisory with
    the link's NOTE, the general question, and `check` exits 1."""
    root = linked_here(tmp_path, RECORD, "kind: single-repository-record")
    env = no_workspace(tmp_path)
    reading = committed(root, env)
    assert reading.state == ADVISE, reading.as_dict()
    assert reading.record_problems == (LINK_REASON,)
    assert shape_advisory.read(root, env=env).state == ADVISE
    plan = tmp_path / "plan.yaml"
    for stdout in adopt_says(root, plan, env):
        assert stdout.splitlines().count(LINK_NOTE) == 1, stdout
    entry = entry_of(plan, RECORD)
    assert (entry["leg"], entry["rule"]) == (None, GENERAL), entry
    [(code, _detail)] = findings(plan)
    assert code == UNRESOLVED


@pytest.mark.parametrize("target, rule", [
    pytest.param(Path("docs", "record.yaml"), GENERAL,
                 id="to-a-record-in-the-leg"),
    pytest.param("kind: single-repository-record", RULE,
                 id="spelled-as-a-record"),
])
def test_the_doctors_audit_of_a_legs_index_reads_a_record_link_as_before(
        adopter, doctor, tmp_path, target, rule):
    """CONTROLS, true on #1270's head as here: the doctor's placement row
    asks `ask_about_a_record_only` of a leg's INDEX (`Source(mount, None,
    "", "")`, #691), and reads a link there as its blob, never followed.
    `git ls-tree` has no commit to list there, so `Tree.is_link` says no
    link and the record is read as before: a link to a record in the leg is
    no record, the general question, as `plan` asks it of a source's link.

    `[spelled-as-a-record]` is the case `plan` now reads otherwise: the
    leg's index still reads the PATH as a record, the record's question,
    where `plan` names the link and asks the general one. Left as it is, as
    the doctor documents it, until the ruling on following a linked record
    settles both readers."""
    def link(leg) -> None:
        (leg / "docs").mkdir()
        (leg / "docs" / "record.yaml").write_text(record_text(),
                                                  encoding="utf-8")
        (leg / RECORD).unlink()
        symlink(leg / RECORD, target)
        git("add", "-A", "--", ".", cwd=leg)

    _, review = leg_audited(adopter, doctor, tmp_path, record_text(), link)
    [row] = [row for row in review if row["path"] == f"code/{RECORD}"]
    assert (row["rule"], row["classified_as"]) == (rule, None), row


# --- the controls: the three files as regular files ----------------------------

@pytest.mark.parametrize("files, state, leg, rule, codes", [
    pytest.param({PROJECT: TRIAD}, TRIAD_ROOT, None,
                 "ambiguous-project-yaml", [UNRESOLVED], id="project-yaml"),
    pytest.param({PROJECT: TRIAD, AGENTS: rendered_leg_agents("spec")},
                 TRIAD_ROOT, None, "ambiguous-project-yaml", [UNRESOLVED],
                 id="project-yaml-beside-a-leg-agents-md"),
    pytest.param({FAMILY: HOLDER}, FAMILY_HOLDER, None, GENERAL,
                 [UNRESOLVED], id="family-yaml"),
    pytest.param({RECORD: record_text()}, RECORDED_SINGLE, "drop", RULE, [],
                 id="single-repository-yaml"),
])
def test_the_three_files_committed_as_regular_files_read_as_before(
        tmp_path, files, state, leg, rule, codes):
    """CONTROLS, true on #1270's head as here: #1272's rows 1c, 2a-c, 2b-c
    and 3c. Each file regular, the commit and the disk agree, neither `plan`
    nor `check` prints a Triad line, and the entry and `check`'s findings
    are what they were: a record is the record's question with its default
    `drop`, and `check` passes it."""
    root = repository(tmp_path / "Atlas", {"README.md": "# here\n", **files})
    env = no_workspace(tmp_path)
    reading = committed(root, env)
    assert reading.state == state, reading.as_dict()
    assert shape_advisory.read(root, env=env).state == state
    plan = tmp_path / "plan.yaml"
    told_nothing(adopt_says(root, plan, env))
    name, = (name for name in files if name != AGENTS)
    entry = entry_of(plan, name)
    assert (entry["leg"], entry["rule"]) == (leg, rule), entry
    assert [code for code, _ in findings(plan)] == codes


@pytest.mark.parametrize("files, state", [
    pytest.param({PROJECT: TRIAD}, TRIAD_ROOT, id="project-yaml"),
    pytest.param({FAMILY: HOLDER}, FAMILY_HOLDER, id="family-yaml"),
    pytest.param({RECORD: record_text()}, RECORDED_SINGLE,
                 id="single-repository-yaml"),
])
def test_a_git_that_cannot_list_the_commit_reads_a_regular_file_as_before(
        tmp_path, monkeypatch, files, state):
    """CONTROLS, true on #1270's head as here: a git whose `ls-tree` fails
    leaves `Tree.is_link` saying no link, so each regular file is read as
    it was, and a record is not named as a link it is not."""
    real = shape_advisory.git_out

    def git_out(args, *rest, **kwargs):
        if args[:1] == ["ls-tree"]:
            raise Refusal("git-failed", "`git ls-tree` exited 128")
        return real(args, *rest, **kwargs)

    root = repository(tmp_path / "Atlas", files)
    env = no_workspace(tmp_path)
    monkeypatch.setattr(shape_advisory, "git_out", git_out)
    reading = committed(root, env)
    assert reading.state == state, reading.as_dict()
