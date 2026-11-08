# SPDX-License-Identifier: Apache-2.0
"""A leg's `AGENTS.md` committed as a symlink is read through it by the Triad
advisory's reading of a commit, as the disk's is read: #1163, in
`scripts/shape_advisory.py`, beside #1110's twelfth site
(`tests/test_doctor_unsearchable_links.py`).

THE DEFECT. `adopt-project.py plan` and `check` ask the advisory of the
commit the plan is written against, and a symlink in a commit is a blob that
holds the PATH it leads to. `_leg_by_agents_md` read that path as the file's
text, found no leg's opening in it, and both commands said "This is a single
repository" over a leg whose `AGENTS.md` is a link, whether what it leads to
was readable or not. The doctor reads the disk, where the operating system
follows the link, and called the same checkout the leg. Measured on #1159's
head `5370b018`, Python 3.12.3 and git 2.43.0, over a clone of `acme/Orbit`
in a folder `Atlas`, each link committed:

  * `AGENTS.md -> docs/AGENTS.md`, the spec leg's file: `plan` and `check`
    printed the `triad` advisory, and `read()` of the commit said `advise`;
    the doctor's Triad row said "this is a clone of the spec leg";
  * the same with `docs/` or the file at mode 000: the advisory again, where
    the doctor offers no way in (#1110's twelfth site);
  * `AGENTS.md -> ../locked/AGENTS.md`, or its absolute path, beside the
    repository: the advisory, where the doctor read the leg (readable) or
    offered no way in (`locked/` at 000).

THE DECISION, option (b) of the brief: the commit's link is followed INSIDE
the commit, as git follows one there (`git cat-file --follow-symlinks`), and
what it leads to is read out of the commit's own objects, as any committed
file is: a leg's file is the leg, whatever the disk's modes. Nothing there
that is a file -- a link that dangles in the commit, loops, runs through a
file, or leads to a directory -- is no leg's file, as on the disk (#430's
rule), so the clone is advised there by both readers. A link that leads OUT
of the commit, an absolute path or one past the root, reaches what no commit
holds: whether this is a leg is not known, the way #1159 treats a file this
user cannot read -- a leg's NAME still answers, and otherwise the reading is
`not-answered`, which `plan` and `check` keep silent.

TWO KINDS OF CASE, as `tests/test_doctor_unsearchable_links.py` has them:
the MODE cases make a real folder at 000 and run the tools as a person does,
and skip on Windows and as root (`CANNOT_RUN_AS_ROOT`), putting the mode
back in a `finally` (`mode_of`); the rest run everywhere a symlink can be
made, and skip where none can (`symlink`).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ADOPT, REPO, git, run_script
#: #827's stand-in for a `stat` the operating system refuses, from the file
#: that owns it.
from test_bump_leg_unopenable import refused_stat
#: The way in's words for a leg's `AGENTS.md` this user cannot read, the
#: environment with no `workspace.yaml`, and the link maker that skips where
#: none can be made, from #1159's file.
from test_doctor_unsearchable_links import NO_LEG_WAY_IN, no_workspace, symlink
#: A leg's `AGENTS.md` as the scaffold renders it, `adopt-project.py plan`
#: as the advisory's own rows run it, the doctor's `--json` rows, and a
#: commit of the whole working tree, from the file that owns them.
from test_shape_advisory import (
    adopt_plan, commit_all, doctor_json, rendered_leg_agents,
)
#: The one skip for a mode that root reads through and Windows ignores.
from test_validate_pins_unreadable_workflow import CANNOT_RUN_AS_ROOT
#: A mode for the block and the old one back after it.
from test_validate_pins_unreadable_workflows_dir import mode_of

sys.path.insert(0, str(REPO / "scripts"))
import shape_advisory  # noqa: E402

AGENTS = shape_advisory.AGENTS_MD
#: What `plan` and `check` print over a single repository, and over a leg
#: known by its `AGENTS.md`.
SINGLE = "This is a single repository."
LEG_NOTE = "NOTE this is a clone of the {} leg of a Triad"
#: The advisory's `why` for a committed `AGENTS.md` that leads out of the
#: commit, where no leg's name answers.
OUT_WHY = (f"{AGENTS}: a symlink out of the commit, so whether this is a leg "
           "clone is not known here, and the advisory says nothing")
#: The `AGENTS.md` link to `docs/AGENTS.md`, the shape of every case here
#: that leads inside the repository.
DOCS_LEG = Path("docs", AGENTS)
#: The spec leg's `AGENTS.md`, for the controls whose link must NOT reach it.
SPEC_LEG = rendered_leg_agents("spec")


def linked_clone(tmp_path: Path, target: Path | str,
                 files: dict | None = None, links: dict | None = None,
                 name: str = "renamed-clone") -> Path:
    """`<tmp>/<name>`, a repository with no `origin` whose `AGENTS.md` is a
    symlink to `target`, beside `files` (`{relative path: text or bytes}`)
    and `links` (`{relative path: target}`), all of it committed: a clone
    whose own name and files alone say what it is.

    A `str` target is linked AS SPELLED, which the link is checked to hold:
    a `Path` would fold `./docs/AGENTS.md`, `docs/./AGENTS.md` and
    `.//docs/AGENTS.md` into `docs/AGENTS.md`, and the row would test
    nothing."""
    root = tmp_path / name
    root.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=root)
    (root / "README.md").write_text("# here\n", encoding="utf-8")
    for rel, text in (files or {}).items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        if isinstance(text, bytes):
            (root / rel).write_bytes(text)
        else:
            (root / rel).write_text(text, encoding="utf-8")
    for rel, to in (links or {}).items():
        symlink(root / rel, to)
    symlink(root / AGENTS, target)
    if isinstance(target, str):
        assert os.readlink(root / AGENTS) == target
    commit_all(root, "Initial import")
    return root


def locked_leg(tmp_path: Path, role: str = "spec") -> Path:
    """`<tmp>/locked/AGENTS.md`, the `role` leg's file, BESIDE the
    repository rather than in it."""
    (tmp_path / "locked").mkdir()
    leg = tmp_path / "locked" / AGENTS
    leg.write_text(rendered_leg_agents(role), encoding="utf-8")
    return leg


def committed(root: Path, env: dict) -> shape_advisory.Reading:
    """The advisory as `adopt-project.py` asks it: of HEAD's commit."""
    commit = git("rev-parse", "HEAD", cwd=root).stdout.strip()
    return shape_advisory.read(root, env=env, commit=commit)


def adopt_says(root: Path, out: Path, env: dict) -> list[str]:
    """`[plan's stdout, check's stdout]`, `check` run on the plan `plan`
    wrote to `out`: the two places a person meets the advisory before
    `execute`. Neither printed a traceback, and `plan` exited 0, as it does
    whatever the advisory says."""
    planned = adopt_plan(root, out, env)
    assert planned.returncode == 0, planned.stdout + planned.stderr
    checked = run_script(ADOPT, "check", "--plan", str(out), env=env)
    for result in (planned, checked):
        assert "Traceback" not in result.stdout + result.stderr, \
            result.stdout + result.stderr
    return [planned.stdout, checked.stdout]


def told_the_leg(said: list[str], role: str) -> None:
    """Each of `plan` and `check` printed the leg's NOTE once, and no
    advisory."""
    for stdout in said:
        assert stdout.count(LEG_NOTE.format(role)) == 1, stdout
        assert SINGLE not in stdout, stdout


def told_nothing(said: list[str]) -> None:
    """Neither `plan` nor `check` printed the advisory, a `triad` line or a
    leg's NOTE: the silence of `not-answered`."""
    for stdout in said:
        assert SINGLE not in stdout, stdout
        assert "\ntriad " not in f"\n{stdout}", stdout
        assert "leg of a Triad" not in stdout, stdout
        assert "is named as the" not in stdout, stdout


# --- a link to the leg's own file, in the commit -----------------------------

@pytest.mark.parametrize("role, target, leg_at, links", [
    pytest.param("spec", DOCS_LEG, "docs/AGENTS.md", {}, id="beside"),
    pytest.param("spec", "./docs/AGENTS.md", "docs/AGENTS.md", {},
                 id="dot-slash"),
    pytest.param("spec", "docs/./AGENTS.md", "docs/AGENTS.md", {},
                 id="dot-in-the-middle"),
    pytest.param("spec", ".//docs/AGENTS.md", "docs/AGENTS.md", {},
                 id="dot-and-a-double-slash"),
    pytest.param("code", DOCS_LEG, ".agents/AGENTS.md",
                 {"docs": Path(".agents")}, id="through-a-linked-folder"),
])
def test_a_leg_agents_md_linked_to_its_own_file_is_the_leg_in_the_commit(
        tmp_path, role, target, leg_at, links):
    """The issue's case. The doctor reads the disk's `AGENTS.md` through its
    link and calls the clone the leg. On the base the commit's link was read
    as the path it holds, so `plan` and `check` printed the advisory over
    the leg. Now the link is followed inside the commit -- through a linked
    folder too (`docs -> .agents`), as git follows it -- and both print the
    leg's NOTE, as over a leg whose `AGENTS.md` is a regular file.

    SPELLED WITH A `.` SEGMENT (`./docs/AGENTS.md`, `docs/./AGENTS.md`,
    `.//docs/AGENTS.md`), git 2.43 answers the follow `dangling`, and the
    first cut of this fix advised as on the base. The link's own target is
    now asked again with its `.` segments dropped, and the commit names
    the leg the disk does."""
    root = linked_clone(tmp_path, target,
                        {leg_at: rendered_leg_agents(role)}, links)
    env = no_workspace(tmp_path)
    reading = committed(root, env)
    assert reading.state == shape_advisory.LEG_CLONE, reading.as_dict()
    assert reading.leg["by"] == "agents", reading.leg
    assert reading.leg["role"] == role, reading.leg
    assert reading.leg["assembly"] == "Northwind/Atlas", reading.leg
    told_the_leg(adopt_says(root, tmp_path / "plan.yaml", env), role)
    _code, rows, _payload = doctor_json(root, env)
    triad = rows["triad-advisory"]
    assert triad["status"] == "n/a", triad
    assert f"this is a clone of the {role} leg" in triad["reason"], triad


@CANNOT_RUN_AS_ROOT
@pytest.mark.parametrize("where", ["in-the-repository", "beside-it"])
def test_a_leg_agents_md_linked_into_a_folder_nobody_may_search(
        tmp_path, where):
    """MODE CASES: the link leads into a folder at 000, in the repository
    (`docs/`) or beside it (`../locked/`). The doctor reads the disk and
    cannot read the file: no Triad row, and `the way in` offers neither
    command (#1110's twelfth site). On the base `plan` and `check` printed
    the advisory over both. Now the commit answers for the folder in the
    repository out of its own objects, which no mode refuses, so both print
    the leg's NOTE; and for the folder beside it, which no commit holds,
    they print nothing at all."""
    if where == "in-the-repository":
        root = linked_clone(tmp_path, DOCS_LEG,
                            {"docs/AGENTS.md": rendered_leg_agents("spec")})
        parent, locked = root, "docs"
    else:
        locked_leg(tmp_path)
        root = linked_clone(tmp_path, Path("..", "locked", AGENTS))
        parent, locked = tmp_path, "locked"
    env = no_workspace(tmp_path)
    with mode_of(parent, locked, 0):
        said = adopt_says(root, tmp_path / "plan.yaml", env)
        _code, rows, _payload = doctor_json(root, env)
        reading = committed(root, env)
    assert "triad-advisory" not in rows, rows["triad-advisory"]
    assert rows["way-in"]["reason"] == NO_LEG_WAY_IN, rows["way-in"]
    assert rows["way-in"]["next"] is None, rows["way-in"]
    if where == "in-the-repository":
        assert reading.state == shape_advisory.LEG_CLONE, reading.as_dict()
        told_the_leg(said, "spec")
    else:
        assert reading.state == shape_advisory.NOT_ANSWERED, \
            reading.as_dict()
        told_nothing(said)


def test_the_commits_linked_leg_file_is_read_when_the_disks_is_refused(
        tmp_path, monkeypatch):
    """The stand-in for the mode case, in process, on every platform and as
    root: every `stat` of a name `AGENTS.md` refused, the link's and its
    target's. The disk, which the doctor reads, is `not-answered`; the
    commit, which `adopt-project.py` reads, is the leg, where the base read
    the link's path and advised. #1159's
    `test_adopts_reader_reads_the_commits_agents_md_and_never_the_disks`
    holds the same for a regular file."""
    root = linked_clone(tmp_path, DOCS_LEG,
                        {"docs/AGENTS.md": rendered_leg_agents("code")})
    env = no_workspace(tmp_path)
    refused_stat(monkeypatch, AGENTS)
    reading = committed(root, env)
    assert reading.state == shape_advisory.LEG_CLONE, reading.as_dict()
    assert reading.leg["role"] == "code", reading.leg
    assert (shape_advisory.read(root, env=env).state
            == shape_advisory.NOT_ANSWERED)


# --- a link out of the commit ------------------------------------------------

@pytest.mark.parametrize("how", ["relative", "relative-after-a-dot",
                                 "absolute", "dangling"])
def test_a_leg_agents_md_linked_out_of_the_commit_is_not_answered(tmp_path,
                                                                  how):
    """A link that leads out of the commit: `../locked/AGENTS.md`, the same
    spelled `./../locked/AGENTS.md`, the same file by its absolute path, or
    `../nowhere/AGENTS.md`. No commit holds what it reaches, so whether this
    is a leg is not known in the commit: `not-answered`, with its line in
    `why` and nothing `refused`, and `plan` and `check` print neither the
    advisory nor a leg's NOTE. On the base each printed the advisory. The
    doctor reads the disk, which the commit cannot: the leg where the link
    reaches its file, and the advisory where it reaches nothing, as for any
    dangling link -- silence in the commit is the one answer that is false
    of neither.

    git 2.43 answers `./../locked/AGENTS.md` `dangling`, for its `.`
    segment. Without it the target begins with `..`, past the root, which
    git answers `symlink`; and git is never asked `../locked/AGENTS.md`
    itself, which it reads from the working directory, and refuses as
    outside the repository: its `Refusal` would name a `why` of its own."""
    leg = locked_leg(tmp_path)
    target = {"relative": Path("..", "locked", AGENTS),
              "relative-after-a-dot": "./../locked/AGENTS.md",
              "absolute": leg,
              "dangling": Path("..", "nowhere", AGENTS)}[how]
    root = linked_clone(tmp_path, target)
    env = no_workspace(tmp_path)
    reading = committed(root, env)
    assert reading.state == shape_advisory.NOT_ANSWERED, reading.as_dict()
    assert reading.why == OUT_WHY
    assert reading.advise is False
    assert reading.leg is None
    assert reading.refused is None
    told_nothing(adopt_says(root, tmp_path / "plan.yaml", env))
    _code, rows, _payload = doctor_json(root, env)
    triad = rows["triad-advisory"]
    if how == "dangling":
        assert triad["status"] == "advisory", triad
    else:
        assert "this is a clone of the spec leg" in triad["reason"], triad


def test_a_leg_by_its_name_is_one_while_its_agents_md_links_out_of_the_commit(
        tmp_path):
    """CONTROL, true on the base as here: a folder named `Orbit-spec` is a
    leg by its NAME, a declared fact no `AGENTS.md` is needed for, so its
    `AGENTS.md` leading out of the commit leaves it the leg its name says,
    as a file this user cannot read does
    (`..._by_its_name_is_one_while_its_agents_md_cannot_be_read`): `plan`
    and `check` print the hedged NOTE for a name."""
    locked_leg(tmp_path)
    root = linked_clone(tmp_path, Path("..", "locked", AGENTS),
                        name="Orbit-spec")
    env = no_workspace(tmp_path)
    reading = committed(root, env)
    assert reading.state == shape_advisory.LEG_CLONE, reading.as_dict()
    assert reading.leg["by"] == "name", reading.leg
    for stdout in adopt_says(root, tmp_path / "plan.yaml", env):
        assert "NOTE `Orbit-spec` is named as the spec leg" in stdout, stdout
        assert SINGLE not in stdout, stdout


def test_a_git_that_cannot_follow_the_link_is_silence_not_advice(
        tmp_path, monkeypatch):
    """A git that cannot follow the committed link (`cat-file
    --follow-symlinks` exits 128) is a `Refusal`, as one that cannot give
    the commit's blob is (#1159): a folder named as a leg is still that
    leg, and one that is not is `not-answered`, in `read()`'s net. On the
    base the link's path was read as the file, and the folder that is no
    leg's name was advised."""
    leg = {"docs/AGENTS.md": rendered_leg_agents("spec")}
    plain = linked_clone(tmp_path, DOCS_LEG, leg)
    named = linked_clone(tmp_path, DOCS_LEG, leg, name="Orbit-spec")
    real = subprocess.run

    def run(args, *rest, **kwargs):
        if "--follow-symlinks" in args:
            return subprocess.CompletedProcess(args, 128, b"", b"fatal: no")
        return real(args, *rest, **kwargs)

    monkeypatch.setattr(subprocess, "run", run)
    env = no_workspace(tmp_path)
    reading = committed(plain, env)
    assert reading.state == shape_advisory.NOT_ANSWERED, reading.as_dict()
    assert reading.why == ("the advisory could not be read here (Refusal), "
                           "so it says nothing")
    assert reading.refused is None
    reading = committed(named, env)
    assert reading.state == shape_advisory.LEG_CLONE, reading.as_dict()
    assert reading.leg["by"] == "name", reading.leg


# --- the controls: nothing that is a leg's file, and the plain cases ----------

@pytest.mark.parametrize("target, files", [
    pytest.param(DOCS_LEG, {"docs/notes.md": "# notes\n"}, id="dangling"),
    pytest.param(Path(AGENTS), {}, id="loop"),
    pytest.param(Path("docs"), {"docs/notes.md": "# notes\n"},
                 id="a-directory"),
    pytest.param(Path("README.md", AGENTS), {}, id="through-a-file"),
    pytest.param(DOCS_LEG, {"docs/AGENTS.md": "# agents\n"},
                 id="another-file"),
    pytest.param("./docs/AGENTS.md/.", {"docs/AGENTS.md": SPEC_LEG},
                 id="dot-then-through-the-legs-file"),
    pytest.param("./docs/AGENTS.md/", {"docs/AGENTS.md": SPEC_LEG},
                 id="dot-then-a-slash-after-the-legs-file"),
    pytest.param("./docs/AGENTS.md\nx", {"docs/AGENTS.md": SPEC_LEG},
                 id="dot-and-a-line-break"),
    pytest.param("./docs/x blob", {"docs/x": SPEC_LEG},
                 id="dot-to-nothing-spelled-like-an-answer"),
])
def test_an_agents_md_linked_to_no_legs_file_is_advised_by_both_readers(
        tmp_path, target, files):
    """CONTROLS, true on the base as here: a link that leads, inside the
    commit, to nothing (it dangles), to itself, to a directory, through a
    file, or to a file that is no leg's, is no leg's file, on the disk
    (#430's rule) and in the commit alike, and both readers advise. They
    hold the follow to the disk's answers, rather than to "a link is not
    known", which only a link out of the commit is.

    THE `.` CONTROLS hold the second ask of a target spelled with a `.`
    segment to the disk's answer where the leg's file is near. A LAST `.`
    or `/` is kept, so `./docs/AGENTS.md/.` and `./docs/AGENTS.md/` still
    run through the file (ENOTDIR), and never become it. A target with a
    line break is not asked again: git's batch input would take its first
    line, `docs/AGENTS.md`, for the name. And `docs/x blob` is not there:
    git's line for it begins with the name it was asked, `<commit>:docs/x`,
    then `blob`, and only a line that begins with an object's name is a
    blob to read."""
    root = linked_clone(tmp_path, target, files)
    env = no_workspace(tmp_path)
    assert committed(root, env).state == shape_advisory.ADVISE
    assert shape_advisory.read(root, env=env).state == shape_advisory.ADVISE


def test_a_regular_leg_agents_md_and_a_single_repository_are_as_before(
        tmp_path):
    """CONTROLS, true on the base as here: a leg whose `AGENTS.md` is a
    regular file is the leg in the commit, and `plan` and `check` print its
    NOTE; a single repository with no `AGENTS.md` is advised, once by each.
    Neither meets a link, and neither reading changes."""
    env = no_workspace(tmp_path)
    for name, files in (("renamed-clone", {AGENTS: rendered_leg_agents(
            "code")}), ("Thing", {})):
        root = tmp_path / name
        root.mkdir()
        git("init", "-q", "-b", "main", ".", cwd=root)
        (root / "README.md").write_text("# here\n", encoding="utf-8")
        for rel, text in files.items():
            (root / rel).write_text(text, encoding="utf-8")
        commit_all(root, "Initial import")
    leg = committed(tmp_path / "renamed-clone", env)
    assert leg.state == shape_advisory.LEG_CLONE, leg.as_dict()
    assert leg.leg["by"] == "agents", leg.leg
    told_the_leg(adopt_says(tmp_path / "renamed-clone",
                            tmp_path / "leg-plan.yaml", env), "code")
    assert committed(tmp_path / "Thing", env).state == shape_advisory.ADVISE
    for stdout in adopt_says(tmp_path / "Thing", tmp_path / "plan.yaml",
                             env):
        assert stdout.count(SINGLE) == 1, stdout
        assert "leg of a Triad" not in stdout, stdout
