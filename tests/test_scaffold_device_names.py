# SPDX-License-Identifier: Apache-2.0
"""`scaffold-project.py` refuses a `--project` no Windows disk can make a
folder of, as `family.py init` refuses such a `--family` (#989).

WHAT WAS WRONG (RV972's N5, on #972). `--project NUL` and `--project Con`
are each one CamelCase token, which is all the naming policy asks of a
project's name, so the scaffold planned them, exit 0, and the real run made
the three repositories, the working trees `NUL`, `NUL-spec` and `NUL-code`
and, under `--local-remote-dir`, the bare `NUL.git`: an assembly root no
Windows disk can clone, into a folder of its name. `family.py init` refused
the same name as `--family` since #688, as `family-bad-holder-name`; the
scaffold never asked.

THE CURE. One function, `shape_materialize.refuse_an_unholdable_name`, the
leg path rule's question of one segment, which both tools ask now: the
scaffold of `--project` as `scaffold-bad-project-name`, before
`_declaration` (the first place a `--pin` can reach `gh`), so before
anything exists and under `--dry-run` alike; `init` of `--family`, as
before. A device name is the WHOLE name: `Nullable`, `Console` and `Auxo`
still scaffold, and the legs' `NUL-spec` and `NUL-code` are not asked.
The naming refusal still speaks first: a device-shaped name the policy
refuses too (`NUL.git`) is refused as the policy refuses it.

Every run but the GitHub rows is into `--local-remote-dir`, which never
calls `gh`.
"""

from __future__ import annotations

import pytest

from conftest import ORG, REPO, SCAFFOLD, WINDOWS_SKIP, run_script
from test_dry_run_parity import NOT_FOUND, stub_gh
from test_scaffold_init_empty_values import DRY_RUN_DONE, everything_under

FAMILY = REPO / "scripts" / "family.py"

DRY_RUN = pytest.mark.parametrize("dry_run", [True, False],
                                  ids=["dry-run", "real-run"])

#: The issue's rows: each scaffolded, exit 0, at `cf66102f`.
DEVICE_NAMES = ["NUL", "Con", "Nul", "com1", "Lpt9", "COM9", "Aux", "Prn"]

#: Names that only begin like a device name, which Windows makes.
CONTROLS = ["Nullable", "Console", "Auxo"]

#: What `scaffold-bad-project-name` is told to do, whole.
PROJECT_NAME_REMEDY = (
    "Remediation: nothing was created, and `--dry-run` refuses the same. "
    "Choose another --project. It names the assembly root: its repository, "
    "the folder it is cloned into, its working tree and, under "
    "--local-remote-dir, its bare repository `<Project>.git`; and a root is "
    "cloned on Windows too, where no file or folder can be called a device "
    "name (`CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9`, `LPT1`-`LPT9`, in any "
    "case, with or without an extension), and a name ending in a dot or a "
    "space is made under another name. There is no --force.")

#: A neutral-product pin with no `--pin-source`: `_declaration` reads its
#: digest with `gh api`, the first `gh` call a run can make.
PIN = f"openGlass@{'0' * 40}"


def bad_project_name(project: str) -> str:
    """The scaffold's refusal of `project`, whole."""
    return (f"REFUSED scaffold-bad-project-name: --project is {project!r}, "
            "which names the assembly root and the folders the scaffold "
            f"makes for it, and `{project}` is a Windows device name (with "
            "or without an extension), which cannot be created there.\n"
            f"{PROJECT_NAME_REMEDY}\n")


def scaffold(tmp_path, project: str, *extra: str, dry_run: bool = True,
             local: bool = True, env: dict | None = None):
    """One run of the scaffold for `project` from `tmp_path/here`, building
    in `tmp_path/work` and, when `local`, making its bare repositories in
    `tmp_path/remotes`."""
    here = tmp_path / "here"
    here.mkdir(parents=True, exist_ok=True)
    return run_script(
        SCAFFOLD, "--org", ORG, "--project", project,
        "--elected-by", "Test Human", "--work-dir", str(tmp_path / "work"),
        *(["--local-remote-dir", str(tmp_path / "remotes")] if local else []),
        *extra, *(["--dry-run"] if dry_run else []), cwd=here, env=env)


def init(tmp_path, family: str):
    """One dry run of `family.py init` for `family`, into a local remote."""
    here = tmp_path / "here"
    here.mkdir(parents=True, exist_ok=True)
    return run_script(
        FAMILY, "init", "--org", ORG, "--family", family,
        "--created-by", "Test Human", "--dry-run",
        "--local-remote-dir", str(tmp_path / "remotes"),
        "--work-dir", str(tmp_path / "work"), cwd=here)


def refused_line(result) -> str:
    """The `REFUSED` line a run ended on."""
    return next((line for line in result.stderr.splitlines()
                 if line.startswith("REFUSED ")), "")


@DRY_RUN
@pytest.mark.parametrize("project", DEVICE_NAMES)
def test_a_device_name_is_refused_as_the_project_and_nothing_is_made(
        tmp_path, project, dry_run):
    """THE ISSUE'S ROWS, by the dry run and the real run: exit 2 with the
    new code, no plan, and nothing made, neither a working tree nor a bare
    repository."""
    result = scaffold(tmp_path, project, dry_run=dry_run)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == "", "the plan is never printed"
    assert result.stderr == bad_project_name(project)
    assert everything_under(tmp_path) == ["here"], "the run made something"


@WINDOWS_SKIP  # the `gh` stub is a `#!` script, which Windows does not run
@DRY_RUN
def test_against_github_the_name_is_refused_before_gh_is_asked(tmp_path,
                                                               dry_run):
    """Against GitHub, with a `--pin` whose digest `_declaration` would
    read with `gh api`: the name is refused first, and `gh` is never
    called."""
    env, calls = stub_gh(tmp_path, NOT_FOUND)
    result = scaffold(tmp_path, "NUL", "--pin", PIN, dry_run=dry_run,
                      local=False, env=env)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr == bad_project_name("NUL")
    assert calls() == []
    assert not (tmp_path / "work").exists()


@pytest.mark.parametrize("project", CONTROLS)
def test_a_name_that_only_begins_like_a_device_still_scaffolds(tmp_path,
                                                               project):
    """THE CONTROLS: a device name is the whole name, so these plan as they
    did at `cf66102f`, and the legs' names are never asked."""
    result = scaffold(tmp_path, project)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"  assembly  {ORG}/{project} " in result.stdout
    assert DRY_RUN_DONE in result.stdout
    assert "REFUSED" not in result.stderr


#: Every name both tools must refuse as a name no Windows disk can make a
#: folder of, and every name both must take: one list, so the scaffold's
#: `--project` and `init`'s `--family` cannot part again.
BOTH_TOOLS = ([(name, True) for name in DEVICE_NAMES
               + ["CON", "PRN", "AUX", "nul", "COM1", "LPT1", "lpt5"]]
              + [(name, False) for name in CONTROLS
                 + ["COM0", "LPT10", "CONX", "Conan", "Nullify"]])


@pytest.mark.parametrize("name, refused", BOTH_TOOLS,
                         ids=[name for name, _ in BOTH_TOOLS])
def test_both_tools_refuse_the_same_names(tmp_path, name, refused):
    """The scaffold refuses a `--project` exactly where `init` refuses the
    same `--family`, each in its own code, and takes the rest."""
    made = scaffold(tmp_path / "scaffold", name)
    held = init(tmp_path / "family", name)
    if refused:
        assert made.returncode == held.returncode == 2, (made.stderr
                                                         + held.stderr)
        assert refused_line(made).startswith(
            f"REFUSED scaffold-bad-project-name: --project is {name!r}, ")
        assert refused_line(held).startswith(
            f"REFUSED family-bad-holder-name: --family is {name!r}, ")
    else:
        assert made.returncode == held.returncode == 0, (made.stderr
                                                         + held.stderr)


@pytest.mark.parametrize("project", ["NUL.git", "Nul."])
@pytest.mark.parametrize("passed", ["foo", "foo_bar"])
def test_a_name_the_policy_refuses_too_is_refused_by_the_policy(
        tmp_path, project, passed):
    """THE NAMING REFUSAL SPEAKS FIRST, as `init` asks `_classify_family_name`
    before its own: a device-shaped name the policy holds as no assembly
    root is refused as `naming-unclassified`, whatever id is passed, and is
    never told it is a device name."""
    result = scaffold(tmp_path, project, f"--id={passed}")
    assert result.returncode == 2, result.stdout + result.stderr
    assert refused_line(result).startswith(
        f"REFUSED naming-unclassified: {project!r} matches no family in the "
        "naming policy."), result.stderr
    assert "scaffold-bad-project-name" not in result.stderr
    assert "scaffold-bad-id" not in result.stderr
