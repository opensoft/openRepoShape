# SPDX-License-Identifier: Apache-2.0
"""`adopt-project.py` refuses an assembly root no Windows disk can make a
folder of, by the one question the scaffold and `family.py init` ask (#1014).

ON MAIN AT e2f9fc42, with a stub `gh` that logs its calls and exits 97 first
on PATH, `GH_TOKEN=bogus` and an empty `GH_CONFIG_DIR`: `plan --project NUL`
(and `Con`, `com1`, `Lpt9`) wrote a plan, `project    NUL (nul) in acme`,
exit 0, and `check` said `plan ok` over it, exit 0, after asking `gh repo
view` of `acme/NUL-spec` and `acme/NUL-code`. Since #1010 (#989) the
scaffold refuses the same `--project` as `scaffold-bad-project-name`, and
`init` has refused the same `--family` as `family-bad-holder-name` since
#688: a root no Windows disk can clone into a folder of its name.

NOW `plan` asks `shape_materialize.refuse_an_unholdable_name` of `--project`
as `adopt-bad-project-name`, with the flags (`_checked_flag_inputs`), before
the work directory, the source, `gh` and the plan file: in the order #972 set
for the scaffold and `init`, the naming refusal first (asked after the source
is read, so a name the policy refuses too is left to it, as on main), then
this, then a passed `--id`'s sentence. `check` and `execute` ask it of the
plan's `legs.assembly`, the name `execute` clones the root into a folder of,
first in the one list both read (`_what_cannot_be_held`, #863), under the
same code; it is one of `RENAMES_THE_LEGS`, so `check` asks `gh` nothing of
the legs of a name that has to change. A device name is the WHOLE name:
`Nullable`, `Console` and `Auxo` plan and check as on main.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import ADOPT, ORG, REPO, make_source_repo, run_script
from test_adopt_plan_flag_refusals_first import (  # noqa: F401 (fixtures)
    SMALL_TREE, SOURCES, Harness, harness, refused_first, source,
)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import NamingPolicy, Refusal  # noqa: E402

POSIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32",
    reason="the `gh` stub is a `#!/bin/sh` script, which Windows runs not")

CODE = "adopt-bad-project-name"
#: The names no Windows disk can make a folder of, one per case the question
#: folds, and the controls, each of which only starts with one.
DEVICES = ["NUL", "Con", "com1", "Lpt9"]
CONTROLS = ["Nullable", "Console", "Auxo"]
#: The project the plan `check` is given is written for, then renamed.
STAND_IN = "Zqxj"


def planned(name: str, *flags: str) -> tuple:
    """`plan`'s arguments after `--source <it>`, for `--project name`."""
    return ("--project", name, "--org", ORG, "--elected-by", "Test Human",
            "--elected-on", "2026-09-02", *flags)


def detail(name: str, named: str = "--project") -> str:
    """What the refusal says of `name`, named as `named`."""
    return (f"{named} is {name!r}, which names the assembly root and the "
            f"folder `execute` clones it into, and `{name}` is a Windows "
            "device name (with or without an extension), which cannot be "
            "created there.")


# --- plan -------------------------------------------------------------------

@POSIX_ONLY
@pytest.mark.parametrize("cloned, work", SOURCES)
@pytest.mark.parametrize("name", DEVICES)
def test_plan_refuses_a_device_name_before_anything_exists(
        harness, source, name, cloned, work):
    """`--project NUL`, `Con`, `com1` and `Lpt9`, from an `org/repo` source
    and a local one: refused with the flags, no `gh`, no `git`, no work
    directory, nothing in the temp folder and no plan. On main each wrote
    a plan, exit 0."""
    given = f"{ORG}/{name}" if cloned else str(source)
    result = harness.plan(given, work=work, planned=planned(name))
    refused_first(harness, result, CODE, detail(name), work)
    assert result.stderr == (
        f"REFUSED {CODE}: {detail(name)}\nRemediation: no plan was written. "
        "Run `plan` again with another --project. It names the assembly "
        "root, and so the folder `execute` clones the root into and the "
        "folder every clone of it is made in; and a root is cloned on "
        "Windows too, where no file or folder can be called a device name "
        "(`CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9`, `LPT1`-`LPT9`, in any "
        "case, with or without an extension), and a name ending in a dot or "
        "a space is made under another name. Where --project is the "
        "source's own name, it cannot be changed here: an in-place adoption "
        "keeps the source's own name, and whether to rename the source is a "
        "human's decision, made first on GitHub (`gh repo rename`); then "
        "run `plan` again against the renamed repository, with its new name "
        "as --project.\n")


@POSIX_ONLY
@pytest.mark.parametrize("name", CONTROLS)
def test_plan_takes_a_name_that_only_starts_with_one(harness, source, name):
    """The controls: a device name is the whole name. Planned as on main,
    and `plan` asks `gh` nothing of a local source."""
    result = harness.plan(str(source), planned=planned(name))
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"project    {name} ({name.lower()}) in {ORG}" in result.stdout
    assert harness.out.is_file()
    assert harness.gh_calls() == []


@POSIX_ONLY
@pytest.mark.parametrize("passed", ["foo_bar", "", "nul\n"])
def test_plan_says_the_name_before_a_passed_id(harness, source, passed):
    """The order #972 set: the name speaks before a passed `--id`, an id
    that is no id (`foo_bar`, `''`) and the one `PROJECT_ID_RE.match` lets
    through with a line break, which no `--id` mends."""
    result = harness.plan(str(source), work=True,
                          planned=planned("NUL", "--id", passed))
    refused_first(harness, result, CODE, detail("NUL"), True)
    assert "adopt-bad-id" not in result.stderr
    assert "unsafe-value" not in result.stderr


@POSIX_ONLY
@pytest.mark.parametrize("name", ["NUL.git", "Nul."])
@pytest.mark.parametrize("passed", ["foo", "foo_bar"])
def test_plan_leaves_a_name_the_policy_refuses_to_the_policy(
        harness, source, name, passed):
    """THE NAMING REFUSAL SPEAKS FIRST: a device-shaped name the naming
    policy holds as no assembly root is `naming-unclassified`, as on main,
    whatever id is passed, and is never told it is a device name; as the
    scaffold says it of `NUL.git` and `Nul.` (#1010's decision 1)."""
    result = harness.plan(str(source), planned=planned(name, "--id", passed))
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(
        f"REFUSED naming-unclassified: {name!r} matches no family in the "
        "naming policy"), result.stderr
    assert CODE not in result.stderr
    assert not harness.out.exists()


# --- check ------------------------------------------------------------------

@pytest.fixture(scope="module")
def stand_in_plan(tmp_path_factory) -> tuple[Path, str]:
    """A source, and the text of the plan `plan` writes for it as
    `STAND_IN`, which each `check` below renames: `plan` writes no plan for
    a device name now, and the plan main wrote for one is this one renamed
    (`project:`, `id:` and the three `legs:` names)."""
    base = tmp_path_factory.mktemp("stand-in")
    made = make_source_repo(base / "Thing", tree=SMALL_TREE, edits=())
    planner = Harness(base)
    result = planner.plan(str(made), planned=planned(STAND_IN))
    assert result.returncode == 0, result.stdout + result.stderr
    return made, planner.out.read_text(encoding="utf-8")


def checked(stub: Harness, stand_in_plan, name: str, base: Path):
    """`check` of the stand-in plan renamed `name`, with `--work-dir
    base/work`, under `stub`'s `gh`."""
    made, text = stand_in_plan
    plan = base / f"plan-{name}.yaml"
    plan.write_text(text.replace(STAND_IN, name).replace(
        STAND_IN.lower(), name.lower()), encoding="utf-8")
    return plan, run_script(ADOPT, "check", "--plan", str(plan), "--source",
                            str(made), "--work-dir", str(base / "work"),
                            env=stub.env)


@POSIX_ONLY
@pytest.mark.parametrize("name", DEVICES)
def test_check_finds_a_device_name_and_asks_gh_nothing(
        harness, stand_in_plan, tmp_path, name):
    """The finding, alone, exit 1, under `plan`'s code. On main: `plan ok`,
    exit 0, and `gh repo view` of both legs. Its fix renames the legs, so
    the leg question is not asked (`RENAMES_THE_LEGS`); `check` makes the
    missing `--work-dir`, empty, before it reads the plan, as on main, and
    nothing in it."""
    plan, result = checked(harness, stand_in_plan, name, tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    findings = [line for line in result.stderr.splitlines()
                if line.startswith("FINDING ")]
    assert findings == [
        f"FINDING {CODE}: {detail(name, f'{plan}: `legs.assembly`')}"], \
        result.stderr
    assert ("\nRemediation: no repository was created. Run `plan` again "
            "with another --project. ") in result.stderr
    assert "plan ok" not in result.stdout
    assert harness.gh_calls() == []
    assert list((tmp_path / "work").iterdir()) == []


@POSIX_ONLY
@pytest.mark.parametrize("name", CONTROLS)
def test_check_passes_a_name_that_only_starts_with_one(
        harness, stand_in_plan, tmp_path, name):
    """The controls: `plan ok`, after the leg question, which the stub
    cannot answer, so it is a note, as on main."""
    _, result = checked(harness, stand_in_plan, name, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "\nplan ok" in result.stdout
    assert CODE not in result.stderr
    assert harness.gh_calls() == [
        f"repo view {ORG}/{name}-{leg} --json nameWithOwner"
        for leg in ("spec", "code")]


# --- execute: the one list --------------------------------------------------

@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_device_names_1014",
                                                  ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Plan:
    """What the list reads of a plan: its path, its keys and its id."""
    path = Path("adoption-plan.yaml")

    def __init__(self, project_id: str):
        self.data = {"org": ORG, "id": project_id}

    def get(self, key, default=None):
        return self.data.get(key, default)

    @property
    def project_id(self) -> str:
        return self.data["id"]


def names_of(name: str) -> dict:
    return {"assembly": name, "spec": f"{name}-spec", "code": f"{name}-code"}


@pytest.mark.parametrize("local", [False, True], ids=["github", "local"])
@pytest.mark.parametrize("name", DEVICES)
def test_execute_refuses_it_first_of_the_list_check_reads(adopter, name,
                                                          local):
    """`execute` refuses the first of `_what_cannot_be_held`
    (`_repository_urls`), before either leg exists, and `check` finds each
    of them: the device name is the one, on GitHub and under
    `--local-remote-dir` alike, where a root is cloned too."""
    naming = NamingPolicy.load(REPO / "contracts" / "repository-naming.yaml")
    plan = _Plan(name.lower())
    refused = list(adopter._what_cannot_be_held(plan, names_of(name), ORG,
                                                local, naming))
    assert [exc.code for exc in refused] == [CODE]
    assert refused[0].detail == detail(
        name, "adoption-plan.yaml: `legs.assembly`")
    run_args = SimpleNamespace(
        local_remote_dir=Path("remotes") if local else None)
    with pytest.raises(Refusal) as caught:
        adopter._repository_urls(run_args, plan, names_of(name), None,
                                 naming)
    assert caught.value.code == CODE
    assert CODE in adopter.RENAMES_THE_LEGS


@pytest.mark.parametrize("name", CONTROLS)
def test_the_list_holds_a_name_that_only_starts_with_one(adopter, name):
    naming = NamingPolicy.load(REPO / "contracts" / "repository-naming.yaml")
    assert list(adopter._what_cannot_be_held(
        _Plan(name.lower()), names_of(name), ORG, False, naming)) == []
