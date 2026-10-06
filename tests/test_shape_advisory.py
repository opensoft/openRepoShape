# SPDX-License-Identifier: Apache-2.0
"""The Triad advisory: who hears it, where it is silent, and what it never does.

THE RULING. Brett Heap, 2026-10-06: "ratify 1249 as recommended", ratifying
openxFactory's `prefer-triad-project-shape` (#163 here). The Triad -- an
assembly root with a spec leg and a code leg -- is the PREFERRED project
shape; it stays elective and confers nothing. A person starting work in a
repository that has not elected it is told so once, by `scaffold-project.py`,
`adopt-project.py plan`/`check` or `shape-doctor.py`, and is never stopped,
converted or recorded on its account.

WHAT THESE TESTS HOLD, in the order the ratified rule says it:

  * a single repository hears it, and every exit code is the one it would
    have had without it -- the doctor's NOT A SHAPE ROOT stays 2, and
    `adopt-project.py plan` exits 0;
  * it is SILENT in an elected Triad, a family holder, a `<user>-wip`
    workspace (by its name, by `origin`'s name, by the person's own
    `workspace.yaml`) and a repository carrying a `single-repository.yaml`
    of the right kind; a leg clone is sent to its assembly root instead;
  * a `single-repository.yaml` that does not parse, or declares another
    kind, silences nothing and is REPORTED beside the advisory, failing
    nothing;
  * it writes nothing, records nothing, and is read by the three tools and
    by no validator, template script or workflow.

NO NETWORK. Every repository here is `git init` in a temporary directory, and
`AGENT_PROTOCOL_ROOT` is pointed at an empty one so the person running the
suite cannot change an answer with their own `workspace.yaml`.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ADOPT, REPO, SCAFFOLD, git, make_source_repo, run_script

sys.path.insert(0, str(REPO / "scripts"))
import shape_advisory  # noqa: E402
from repo_shape import load_yaml  # noqa: E402
from shape_materialize import render  # noqa: E402

DOCTOR = REPO / "shape-doctor.py"
ROW = "triad-advisory"

#: The meaning the advisory must carry wherever it is said: the preference,
#: the posture beside it, and the two exits it names. Asserted as fragments so
#: a reworded sentence that keeps its meaning is not a red test, and one that
#: drops any of them is.
PREFERENCE = "is the preferred project shape"
POSTURE = "it confers nothing"
IDENTICAL = "reviewed identically"
CONVERT = "adopt-project.py"
RECORD = "single-repository.yaml"

#: A source repository with no ambiguous corner, so `adopt-project.py check`
#: passes on the plan `plan` writes and its exit code is about nothing but
#: the plan.
PLAIN_TREE = {
    "README.md": "# Thing\n",
    "specs/001-feature/spec.md": "# The feature\n",
    "src/app/main.py": "VALUE = 1\n",
}
PLAIN_EDITS = (("src/app/main.py", "VALUE = 2\n", "Change the value"),)


@pytest.fixture
def quiet_env(tmp_path) -> dict:
    """An `AGENT_PROTOCOL_ROOT` with no `workspace.yaml` in it."""
    root = tmp_path / "agent-protocol"
    root.mkdir()
    return {"AGENT_PROTOCOL_ROOT": str(root)}


def repository(path: Path, files: dict | None = None,
               origin: str | None = None) -> Path:
    """A one-commit repository at `path`, optionally with an `origin`."""
    path.mkdir(parents=True)
    git("init", "-q", "-b", "main", ".", cwd=path)
    for name, body in (files or {"README.md": "# here\n"}).items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    git("add", "-A", "--", ".", cwd=path)
    git("-c", "user.name=t", "-c", "user.email=t@t.invalid", "commit", "-q",
        "-m", "Initial import", cwd=path)
    if origin:
        git("remote", "add", "origin", origin, cwd=path)
    return path


def doctor_json(root: Path, env: dict) -> tuple[int, dict, dict]:
    """`(exit, {row id: row}, payload)` for one `--json` doctor run."""
    result = run_script(DOCTOR, "--root", str(root), "--json", env=env)
    payload = json.loads(result.stdout)
    return (result.returncode, {row["id"]: row for row in payload["rows"]},
            payload)


def record_text(**fields) -> str:
    """A `single-repository.yaml` body, the schema's own example by default."""
    example = dict(shape_advisory.record_schema()["example"])
    example.update(fields)
    lines = []
    for key, value in example.items():
        if value is None:
            continue
        lines.append(f"{key}: {json.dumps(value) if isinstance(value, str) else value}")
    return "\n".join(lines) + "\n"


def rendered_leg_agents(role: str) -> str:
    """A leg's `AGENTS.md`, rendered from its template as the scaffold does."""
    template = (REPO / "templates" / f"{role}-root" / "AGENTS.md").read_text(
        encoding="utf-8")
    return render(template, {
        "PROJECT_NAME": "Atlas", "PROJECT_ID": "atlas",
        "ASSEMBLY_REPOSITORY": "Northwind/Atlas",
        "SPEC_REPOSITORY": "Northwind/Atlas-spec",
        "CODE_REPOSITORY": "Northwind/Atlas-code",
        "SPEC_PATH": "spec", "CODE_PATH": "code"}, "AGENTS.md")


def no_traceback(result) -> bool:
    return "Traceback" not in result.stdout + result.stderr


def commit_all(path: Path, message: str) -> None:
    """Commit everything in `path`'s working tree, whatever is there."""
    git("add", "-A", "--", ".", cwd=path)
    git("-c", "user.name=t", "-c", "user.email=t@t.invalid", "commit", "-q",
        "-m", message, cwd=path)


def adopt_plan(source: Path, out: Path, env: dict) -> subprocess.CompletedProcess:
    return run_script(ADOPT, "plan", "--source", str(source), "--project",
                      "Thing", "--org", "testorg", "--elected-by",
                      "Test Human", "--elected-on", "2026-10-06", "--out",
                      str(out), env=env)


# --- a single repository hears it, and nothing else changes -----------------

def test_a_single_repository_hears_it_once_and_its_exit_is_unchanged(
        tmp_path, quiet_env):
    """The doctor's row is `advisory`, and NOT A SHAPE ROOT is still exit 2.

    The exit is compared with the SAME repository once it has recorded
    staying single and the advisory is silent: two runs that differ only in
    whether the advisory was given must exit alike, or the advisory changed
    an exit status, which the ratified rule forbids.
    """
    here = repository(tmp_path / "Thing")
    code, rows, payload = doctor_json(here, quiet_env)
    assert code == 2 and payload["verdict"] == "NOT A SHAPE ROOT", payload
    row = rows[ROW]
    assert row["status"] == "advisory", row
    assert row["label"] == "Triad", row
    assert row["next"] is None, (
        "the advisory fixes nothing, so it names no next command")
    for fragment in ("This is a single repository.", PREFERENCE, POSTURE,
                     IDENTICAL, CONVERT, RECORD,
                     "Nothing here changes; work continues."):
        assert fragment in row["reason"], (fragment, row["reason"])
    assert row["detail"]["state"] == shape_advisory.ADVISE

    # THE PRINTED REPORT, which is where a row can still do damage after the
    # verdict is decided: `report()` prints `REFUSED shape-doctor-cannot-
    # answer` for ANY row flagged as this checkout being unable to answer,
    # whatever the kind of root (#164 review: a mutation setting that flag on
    # this row survived every test until this assertion).
    text = run_script(DOCTOR, "--root", str(here), env=quiet_env)
    assert text.returncode == 2, text.stdout + text.stderr
    assert "REFUSED" not in text.stderr and "Traceback" not in text.stderr, \
        text.stderr
    assert "CANNOT ANSWER" not in text.stdout, text.stdout
    assert "  advisory  Triad" in text.stdout, text.stdout

    (here / RECORD).write_text(record_text(), encoding="utf-8")
    silent_code, silent_rows, _ = doctor_json(here, quiet_env)
    assert ROW not in silent_rows, silent_rows.get(ROW)
    assert silent_code == code, (
        "the advisory changed the doctor's exit code: "
        f"{code} with it, {silent_code} without it")


def test_adopt_plan_says_it_once_exits_zero_and_writes_none_of_it(tmp_path,
                                                                   quiet_env):
    """`adopt-project.py plan` and `check` over a single repository.

    The advisory is PRINTED once by each, and is never written: not into the
    plan file, which is an artifact somebody edits and `execute` acts on, and
    not into the source, which `plan` never writes at all.
    """
    source = make_source_repo(tmp_path / "Thing", tree=PLAIN_TREE,
                              edits=PLAIN_EDITS)
    before = git("status", "--porcelain", "--ignored", cwd=source).stdout
    out = tmp_path / "adoption-plan.yaml"
    result = adopt_plan(source, out, quiet_env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("This is a single repository.") == 1, \
        result.stdout
    for fragment in (PREFERENCE, POSTURE, IDENTICAL, RECORD,
                     "Nothing converts until `execute`"):
        assert fragment in result.stdout, (fragment, result.stdout)
    assert "Triad" not in out.read_text(encoding="utf-8"), (
        "the advisory is a sentence said to a person, not a fact recorded "
        "in the plan")
    assert git("status", "--porcelain", "--ignored", cwd=source).stdout \
        == before

    check = run_script(ADOPT, "check", "--plan", str(out), env=quiet_env)
    assert check.returncode == 0, check.stdout + check.stderr
    assert check.stdout.count("This is a single repository.") == 1, \
        check.stdout
    assert check.stdout.index("This is a single repository.") \
        < check.stdout.index("WHAT WILL HAPPEN"), (
            "the advisory is said where work starts, before the plan's own "
            "report")


def test_the_scaffold_offers_the_triad_first(tmp_path):
    """The plan a person reads before typing yes names the Triad first.

    `scaffold-project.py` creates nothing but a Triad, so the offer is the
    tool itself: one `triad` line, above the shape revision, with the posture
    on the line after it -- in a dry run, which creates nothing and exits 0.
    """
    result = run_script(SCAFFOLD, "--org", "testorg", "--project", "Atlas",
                        "--elected-by", "Test Human", "--dry-run",
                        "--local-remote-dir", str(tmp_path / "remotes"))
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    triad = [i for i, line in enumerate(lines) if line.startswith("triad ")]
    assert len(triad) == 1, result.stdout
    shape = next(i for i, line in enumerate(lines)
                 if line.startswith("shape "))
    assert triad[0] < shape, result.stdout
    said = " ".join(lines[triad[0]:triad[0] + 2])
    for fragment in ("the Triad", "preferred project shape", POSTURE,
                     IDENTICAL, "owes no declaration"):
        assert fragment in said, (fragment, said)
    assert not (tmp_path / "remotes").exists(), "a dry run created a remote"


# --- where it is silent -----------------------------------------------------

def test_an_elected_triad_is_silent(project, quiet_env):
    """A scaffolded assembly root: the detector, and no row at all."""
    assert shape_advisory.read(project).state == shape_advisory.TRIAD_ROOT
    _code, rows, payload = doctor_json(project, quiet_env)
    assert payload["kind"] == "project"
    assert ROW not in rows, rows.get(ROW)


def test_a_project_manifest_with_fewer_than_two_legs_is_not_a_triad(tmp_path):
    """The detector is the ratified one -- schema AND a spec and a code leg."""
    here = repository(tmp_path / "Half", {
        "project.yaml": "schema_version: 1\nkind: project-manifest\n"
                        "schema: project-repo-schema\nlegs:\n"
                        "  - role: assembly\n    path: \".\"\n"
                        "  - role: spec\n    path: spec\n"})
    assert not shape_advisory.is_triad(load_yaml(here / "project.yaml"))
    assert shape_advisory.read(here).advise


def test_a_family_holder_is_silent(tmp_path, quiet_env):
    here = repository(tmp_path / "InkRouter", {
        "family.yaml": "schema_version: 1\nkind: family-manifest\n"
                       "id: inkrouter\nmembers: []\n"})
    assert shape_advisory.read(here).state == shape_advisory.FAMILY_HOLDER
    _code, rows, payload = doctor_json(here, quiet_env)
    assert payload["kind"] == "family"
    assert ROW not in rows, rows.get(ROW)


@pytest.mark.parametrize("how", ["directory", "origin", "workspace.yaml",
                                 "orgs map"])
def test_a_workspace_repository_is_silent(tmp_path, quiet_env, how):
    """`<user>-wip`, by each declared fact that can name one."""
    config = Path(quiet_env["AGENT_PROTOCOL_ROOT"]) / "workspace.yaml"
    if how == "directory":
        here = repository(tmp_path / "brett-wip")
    elif how == "origin":
        here = repository(tmp_path / "checkout-elsewhere",
                          origin="git@github.com:opensoft/scott-wip.git")
    elif how == "workspace.yaml":
        here = repository(tmp_path / "my-notes")
        config.write_text("repository: opensoft/brett-wip\n"
                          f"path: {json.dumps(str(here))}\n",
                          encoding="utf-8")
    else:
        here = repository(tmp_path / "medx-notes")
        config.write_text("repository: opensoft/brett-wip\n"
                          "path: /nowhere/brett-wip\norgs:\n  MedxSoft:\n"
                          "    repository: MedxSoft/brett-wip\n"
                          f"    path: {json.dumps(str(here))}\n",
                          encoding="utf-8")
    reading = shape_advisory.read(here, env=quiet_env)
    assert reading.state == shape_advisory.WORKSPACE, reading.as_dict()
    _code, rows, _payload = doctor_json(here, quiet_env)
    assert ROW not in rows, rows.get(ROW)


def test_a_valid_record_is_silent_and_named_among_what_is_here(tmp_path,
                                                               quiet_env):
    """The schema's own example, written at the root: no row, no lines."""
    here = repository(tmp_path / "dotfiles", {RECORD: record_text()})
    reading = shape_advisory.read(here)
    assert reading.state == shape_advisory.RECORDED_SINGLE
    assert reading.field_problems == ()
    _code, rows, _payload = doctor_json(here, quiet_env)
    assert ROW not in rows, rows.get(ROW)
    assert f"a {RECORD}" in rows["contents"]["reason"], rows["contents"]
    result = adopt_plan(here, tmp_path / "plan.yaml", quiet_env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "This is a single repository." not in result.stdout


def test_a_record_missing_a_field_stays_silent_and_the_doctor_says_which(
        tmp_path, quiet_env):
    """`kind:` decides; a missing `reason` is a `note`, never the advisory."""
    here = repository(tmp_path / "dotfiles",
                      {RECORD: record_text(reason=None)})
    code, rows, _payload = doctor_json(here, quiet_env)
    assert code == 2
    row = rows[ROW]
    assert row["status"] == "note", row
    assert "`reason` is missing" in row["reason"], row["reason"]
    assert "This is a single repository." not in row["reason"]


@pytest.mark.parametrize("body, why", [
    ("schema_version: 1\nkind: project-manifest\n",
     "declares kind 'project-manifest'"),
    ("schema_version: 1\nkind: [single-repository-record\n",
     "could not be read"),
    ("- schema_version\n- kind\n", "is not a YAML mapping"),
    (None, "is not a file"),
], ids=["wrong-kind", "unparsable", "not-a-mapping", "a-directory"])
def test_a_record_that_silences_nothing_is_reported_beside_the_advisory(
        tmp_path, quiet_env, body, why):
    """Present, and not the record: the advisory, the reason, and no failure.

    Every exit is the one a repository with no such file gets, which is what
    "reported without failing anything" means.
    """
    here = repository(tmp_path / "Thing")
    plain_code, _rows, _payload = doctor_json(here, quiet_env)
    if body is None:
        (here / RECORD).mkdir()
        (here / RECORD / "x").write_text("x\n", encoding="utf-8")
    else:
        (here / RECORD).write_text(body, encoding="utf-8")

    code, rows, _payload = doctor_json(here, quiet_env)
    assert code == plain_code == 2
    row = rows[ROW]
    assert row["status"] == "advisory", row
    assert "This is a single repository." in row["reason"]
    assert f"{RECORD} does not silence this" in row["reason"], row["reason"]
    assert why in row["reason"], row["reason"]

    # COMMITTED before `adopt-project.py` is asked, because it reads the
    # commit it plans and not the working tree (see the planned-commit test).
    commit_all(here, "Add a single-repository.yaml")
    result = adopt_plan(here, tmp_path / "plan.yaml", quiet_env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "This is a single repository." in result.stdout
    assert f"NOTE {RECORD} does not silence this" in result.stdout, \
        result.stdout


@pytest.mark.parametrize("name", ["Atlas-spec", "billing-code"])
def test_a_leg_known_by_name_alone_is_told_so_with_a_hedge(tmp_path,
                                                          quiet_env, name):
    """By its name alone: silenced, sent to a root, and not over-claimed.

    `billing-code` is a leg under the naming policy, which is a declared fact
    and silences the advisory; whether a `billing` mounts it is not something
    a name can say, so the sentence says "named as" and "if it is one" rather
    than calling an unrelated repository a clone of somebody's leg (#164
    review). And `the way in` offers no adoption: a leg split into two more
    legs is the one adoption nobody wants, and offering it two rows above
    "work from its assembly root" would be the report contradicting itself.
    """
    project, role = name.rsplit("-", 1)
    here = repository(tmp_path / name)
    reading = shape_advisory.read(here)
    assert reading.state == shape_advisory.LEG_CLONE
    assert reading.leg["by"] == "name"
    _code, rows, _payload = doctor_json(here, quiet_env)
    row = rows[ROW]
    assert row["status"] == "n/a", row
    assert "This is a single repository." not in row["reason"]
    assert f"`{name}` is named as the {role} leg of `{project}`" in \
        row["reason"], row["reason"]
    assert f"if it is one, work from its assembly root `{project}`" in \
        row["reason"], row["reason"]
    assert "this is a clone of" not in row["reason"], row["reason"]
    way_in = rows["way-in"]
    assert way_in["next"] is None, way_in
    assert "adopt-project.py" not in (way_in["next"] or "")
    assert "AS A LEG" in way_in["reason"], way_in["reason"]
    result = adopt_plan(here, tmp_path / "plan.yaml", quiet_env)
    assert "This is a single repository." not in result.stdout
    assert f"NOTE `{name}` is named as the {role} leg" in result.stdout, \
        result.stdout


def test_a_leg_that_says_so_is_sent_to_the_root_it_names(tmp_path, quiet_env):
    """By its own `AGENTS.md`, the primary route: plain, and naming the root."""
    here = repository(tmp_path / "renamed-clone",
                      {"AGENTS.md": rendered_leg_agents("spec")})
    _code, rows, _payload = doctor_json(here, quiet_env)
    row = rows[ROW]
    assert row["status"] == "n/a", row
    assert "this is a clone of the spec leg of a Triad" in row["reason"]
    assert "work from its assembly root `Northwind/Atlas`" in row["reason"]
    assert rows["way-in"]["next"] is None, rows["way-in"]


@pytest.mark.parametrize("role", ["spec", "code"])
def test_the_leg_templates_are_what_the_advisory_reads(tmp_path, role):
    """A leg cloned under ANY name says what it is in its own `AGENTS.md`.

    Rendered from `templates/<role>-root/AGENTS.md` exactly as the scaffold
    renders it, so the two sentences `scripts/shape_advisory.py` reads are
    held to the templates: reword a template without the module and this is
    red, rather than a leg that quietly starts being advised.
    """
    here = repository(tmp_path / "renamed-clone",
                      {"AGENTS.md": rendered_leg_agents(role)})
    reading = shape_advisory.read(here)
    assert reading.state == shape_advisory.LEG_CLONE, reading.as_dict()
    assert reading.leg["role"] == role
    assert reading.leg["by"] == "agents"
    assert reading.leg["assembly"] == "Northwind/Atlas"


def test_a_directory_that_is_not_a_repository_is_not_advised(tmp_path,
                                                             quiet_env):
    """"This is a single repository" would be false: there is none."""
    here = tmp_path / "Loose"
    here.mkdir()
    (here / "notes.txt").write_text("nothing\n", encoding="utf-8")
    assert shape_advisory.read(here).state == shape_advisory.NOT_A_REPOSITORY
    _code, rows, _payload = doctor_json(here, quiet_env)
    assert ROW not in rows, rows.get(ROW)


@pytest.mark.parametrize("name", ["xFactory", "dotfiles", "vendored-fork"])
def test_no_class_is_guessed(tmp_path, quiet_env, name):
    """An aggregation, a configuration repository and a vendored fork hear it.

    None of them carries a declared fact that says what it is, so none is
    exempted by its name or its layout (the ratified ruling on OQ-2).
    """
    here = repository(tmp_path / name, {"README.md": "# aggregation\n",
                                        ".gitmodules": ""})
    assert shape_advisory.read(here).advise
    _code, rows, _payload = doctor_json(here, quiet_env)
    assert rows[ROW]["status"] == "advisory"


def test_a_broken_assembly_root_is_not_called_a_single_repository(tmp_path,
                                                                   quiet_env):
    """A `project.yaml` short of a Triad gets its `manifest` finding, no row.

    Not a Triad by the detector, and not "a single repository" either: it is
    a project root whose manifest is wrong, which the doctor's own rows
    explain. So the `Triad` row is not asked there (#164 review), and the
    verdict and exit are the same whether or not a valid record would have
    silenced it -- the advisory has nothing to do with a project root's
    verdict, in either direction.
    """
    here = repository(tmp_path / "Half", {
        "project.yaml": "schema_version: 1\nkind: project-manifest\n"
                        "schema: project-repo-schema\nlegs:\n"
                        "  - role: assembly\n    path: \".\"\n"
                        "  - role: spec\n    path: spec\n"})
    code, rows, payload = doctor_json(here, quiet_env)
    assert payload["kind"] == "project", payload
    assert ROW not in rows, rows.get(ROW)
    (here / RECORD).write_text(record_text(), encoding="utf-8")
    recorded_code, recorded_rows, recorded = doctor_json(here, quiet_env)
    assert ROW not in recorded_rows, recorded_rows.get(ROW)
    assert (recorded_code, recorded["verdict"]) == (code, payload["verdict"])


# --- it cannot fail the run that says it ------------------------------------

#: Three `single-repository.yaml` bodies a person, an editor or a script can
#: produce, each of which raised out of the advisory before #164's review
#: round, and what the doctor now says about each instead.
UNREADABLE = {
    "undecodable": (b"schema_version: 1\nkind: \xff\xfe record\n",
                    "it could not be read (UnicodeDecodeError)"),
    "nested-past-the-recursion-limit": (
        ("kind: " + "[" * 600 + "]" * 600 + "\n").encode("ascii"),
        "it could not be read (RecursionError)"),
    "non-ascii-kind-on-an-ascii-console": (
        'schema_version: 1\nkind: "café—record"\n'.encode("utf-8"),
        "it declares kind 'caf"),
}


@pytest.mark.parametrize("case", sorted(UNREADABLE))
def test_a_record_nobody_can_read_fails_nothing(tmp_path, quiet_env, case):
    """Reported beside the advisory; every exit the same; no traceback.

    Run under `PYTHONIOENCODING=ascii`, the console a Windows code page or a
    plain pipe gives: a `kind:` the console cannot encode is a person's text
    reaching `print`, and it must cost one `?`, not the run.
    """
    body, said = UNREADABLE[case]
    env = {**quiet_env, "PYTHONIOENCODING": "ascii"}
    here = repository(tmp_path / "Thing")
    (here / RECORD).write_bytes(body)
    commit_all(here, "Add a single-repository.yaml")

    code, rows, _payload = doctor_json(here, env)
    assert code == 2
    row = rows[ROW]
    assert row["status"] == "advisory", row
    assert f"{RECORD} does not silence this: {said}" in row["reason"], \
        row["reason"]
    text = run_script(DOCTOR, "--root", str(here), env=env)
    assert text.returncode == 2 and no_traceback(text), \
        text.stdout + text.stderr
    assert "advisory  Triad" in text.stdout, text.stdout

    result = adopt_plan(here, tmp_path / "plan.yaml", env)
    assert result.returncode == 0 and no_traceback(result), \
        result.stdout + result.stderr
    assert "This is a single repository." in result.stdout, result.stdout
    assert f"NOTE {RECORD} does not silence this: {said}" in result.stdout, \
        result.stdout


def test_a_workspace_path_no_machine_can_hold_fails_nothing(tmp_path,
                                                            quiet_env):
    """A NUL byte in the person's `workspace.yaml` names nothing, and only it.

    `Path.resolve` raises `ValueError` on an embedded NUL. The person's own
    configuration is the one input here that is not this repository's, so it
    costs exactly its own entry: the `orgs:` entry beside it still names its
    checkout, and every other repository still hears the advisory with the
    exit it always had.
    """
    config = Path(quiet_env["AGENT_PROTOCOL_ROOT"]) / "workspace.yaml"
    mine = repository(tmp_path / "medx-notes")
    other = repository(tmp_path / "Thing")
    config.write_bytes(
        b"repository: opensoft/brett-wip\npath: /nowhere/\x00/brett-wip\n"
        b"orgs:\n  MedxSoft:\n    repository: MedxSoft/brett-wip\n"
        b"    path: " + json.dumps(str(mine)).encode("utf-8") + b"\n")
    assert shape_advisory.read(mine, env=quiet_env).state \
        == shape_advisory.WORKSPACE
    for here, row_expected in ((mine, False), (other, True)):
        result = run_script(DOCTOR, "--root", str(here), env=quiet_env)
        assert result.returncode == 2 and no_traceback(result), \
            result.stdout + result.stderr
        assert ("advisory  Triad" in result.stdout) is row_expected, \
            result.stdout
    result = adopt_plan(other, tmp_path / "plan.yaml", quiet_env)
    assert result.returncode == 0 and no_traceback(result), \
        result.stdout + result.stderr
    assert "This is a single repository." in result.stdout


def test_a_byte_order_mark_is_the_editors_and_not_the_persons(tmp_path,
                                                              quiet_env):
    """A UTF-8 BOM ahead of the first key changes no answer.

    Left in, it turns `schema_version` into a key nobody declared -- a valid
    record that names a field problem, and a leg whose `AGENTS.md` no longer
    opens with the leg's sentence, so it is advised to become what it is.
    """
    bom = "﻿"
    here = repository(tmp_path / "dotfiles", {RECORD: bom + record_text()})
    reading = shape_advisory.read(here, env=quiet_env)
    assert reading.state == shape_advisory.RECORDED_SINGLE, reading.as_dict()
    assert reading.field_problems == (), reading.field_problems
    _code, rows, _payload = doctor_json(here, quiet_env)
    assert ROW not in rows, rows.get(ROW)
    result = adopt_plan(here, tmp_path / "plan.yaml", quiet_env)
    assert "This is a single repository." not in result.stdout
    assert "does not silence this" not in result.stdout, result.stdout

    leg = repository(tmp_path / "renamed-clone",
                     {"AGENTS.md": bom + rendered_leg_agents("code")})
    reading = shape_advisory.read(leg, env=quiet_env)
    assert reading.state == shape_advisory.LEG_CLONE, reading.as_dict()
    assert reading.leg["by"] == "agents"


def test_adopt_reads_the_commit_it_plans_and_the_doctor_reads_the_disk(
        tmp_path, quiet_env):
    """An uncommitted record is not in the repository being split.

    `adopt-project.py plan` writes its plan against one commit of the
    default branch, so a `single-repository.yaml` that exists only in the
    working tree says nothing about that commit, and the advisory is still
    said. The doctor reports the tree in front of the person, so it is
    silent about the same checkout -- and both stop once it is committed.
    """
    here = repository(tmp_path / "Thing")
    (here / RECORD).write_text(record_text(), encoding="utf-8")
    _code, rows, _payload = doctor_json(here, quiet_env)
    assert ROW not in rows, rows.get(ROW)
    result = adopt_plan(here, tmp_path / "plan.yaml", quiet_env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("This is a single repository.") == 1, \
        result.stdout

    commit_all(here, "Record staying single")
    result = adopt_plan(here, tmp_path / "plan-2.yaml", quiet_env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "This is a single repository." not in result.stdout, result.stdout


# --- the record, its schema and its template agree --------------------------

def test_the_schema_the_template_and_the_module_agree():
    schema = shape_advisory.record_schema()
    assert schema["schema_version"] == 1
    assert schema["kind"] == shape_advisory.SCHEMA_KIND
    assert schema["record_kind"] == shape_advisory.RECORD_KIND
    assert schema["file"] == shape_advisory.RECORD_FILE
    assert schema["template"] == shape_advisory.RECORD_TEMPLATE
    names = [field["name"] for field in schema["fields"]]
    assert names == ["schema_version", "kind", "decided_by", "decided_on",
                     "reason", "revisit_on"]
    required = {field["name"] for field in schema["fields"]
                if field["required"]}
    assert required == set(names) - {"revisit_on"}, (
        "revisit_on is the one optional field the ruling names")

    template = load_yaml(REPO / shape_advisory.RECORD_TEMPLATE)
    assert template["schema_version"] == 1
    assert template["kind"] == shape_advisory.RECORD_KIND
    assert list(template) == names

    assert shape_advisory.field_problems(dict(schema["example"])) == []
    unfilled = shape_advisory.field_problems(template)
    assert len(unfilled) == 4 and all("placeholder" in p for p in unfilled), \
        unfilled
    filled = render((REPO / shape_advisory.RECORD_TEMPLATE).read_text(
        encoding="utf-8"), {"DECIDED_BY": "Dana Okafor",
                            "DECIDED_ON": "2026-10-06",
                            "REASON": "a configuration repository",
                            "REVISIT_ON": "2027-04-01"}, "template")
    from repo_shape import parse_yaml
    assert shape_advisory.field_problems(parse_yaml(filled)) == []


@pytest.mark.parametrize("field, value, problem", [
    ("decided_on", "06/10/2026", "not an ISO date"),
    ("decided_on", "2026-02-30", "not an ISO date"),
    ("schema_version", 2, "fixes it at 1"),
    ("decided_by", "", "not text"),
    ("extra", "x", "`extra` is not a field of the record"),
])
def test_a_field_the_schema_does_not_admit_is_named(field, value, problem):
    record = dict(shape_advisory.record_schema()["example"])
    record[field] = value
    found = shape_advisory.field_problems(record)
    assert any(problem in line for line in found), found


# --- it is never a gate, and never written ----------------------------------

def test_only_the_three_tools_read_the_advisory():
    """No validator, template script or workflow reads it -- ever.

    The ratified rule: a project's shape is never a review input. The module
    and the record it reads are imported by `scaffold-project.py`,
    `adopt-project.py` and `shape-doctor.py` and by nothing else this
    repository ships; a fourth importer is somebody wiring the shape into a
    check, which the rule calls an amendment of the doctrine.
    """
    shipped = sorted(set(REPO.glob("*.py")) | set(REPO.glob("scripts/*.py"))
                     | set((REPO / "templates").rglob("*.py")))
    importers = set()
    for path in shipped:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = ([alias.name for alias in node.names]
                     if isinstance(node, ast.Import) else
                     [node.module] if isinstance(node, ast.ImportFrom)
                     else [])
            if "shape_advisory" in names:
                importers.add(path.relative_to(REPO).as_posix())
    assert importers == {"scaffold-project.py", "adopt-project.py",
                         "shape-doctor.py"}, importers
    for path in [*(REPO / ".github").rglob("*"),
                 *(REPO / "templates").rglob("*.py"),
                 *(REPO / "templates").rglob("*.yml")]:
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert "shape_advisory" not in text and RECORD not in text, (
                f"{path.relative_to(REPO)} reads the Triad advisory or its "
                "record; the shape is never a gate or a review input")


def test_the_doctor_and_adopt_write_nothing_into_a_single_repository(
        tmp_path, quiet_env):
    """No record, no manifest, no marker that the advisory was given."""
    here = repository(tmp_path / "Thing")
    before = git("status", "--porcelain", "--ignored", cwd=here).stdout
    doctor_json(here, quiet_env)
    adopt_plan(here, tmp_path / "plan.yaml", quiet_env)
    assert git("status", "--porcelain", "--ignored", cwd=here).stdout \
        == before
    assert not (here / RECORD).exists()
