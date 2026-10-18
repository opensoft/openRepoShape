# SPDX-License-Identifier: Apache-2.0
"""`scaffold-project.py` and `family.py init` refuse a flag passed empty by
name, and never read it as a flag not given (#911, #459's U156, U157 and
U160).

WHAT WAS WRONG. Each tool read the values it fills in by itself by their
truth (`args.id or project.lower()`), so the scaffold's `--id ''`, `--name
''`, `--elected-on ''`, `--reference ''` and `--elected-by ''`, and `init`'s
`--id ''`, `--name ''`, `--created-on ''` and `--created-by ''`, each planned
its default and exited 0: a script's `--id "$ID"` with `ID` unset got the
derived id without a word, and an empty elector or creator became
GIT_AUTHOR_NAME. With no identity at all, `--elected-by ''` was refused as
`scaffold-no-elector: no --elected-by ...`, of a flag that was passed, and
`--created-by ''` as `family-no-creator` alike.

THE CURE, as `adopt-project.py plan` reads its own flags since #699: each is
read by `is not None`, and an empty one meets its flag's own rule and is
refused there by name, value as typed. `--id ''` is a passed id that is no
id (`scaffold-bad-id`, `family-bad-id`); `--elected-on ''` is no date
(`election-date-malformed`); and the free-text values, `--created-on ''`
among them, are refused by the new project's or holder's own validator
(`scaffold-manifest-invalid`, `family-manifest-invalid`), which names the
flag as passed, never "(not given, so ...)". The fallbacks answer only
where the flag is not given.

Every run is a `--dry-run` into `--local-remote-dir`, which never calls `gh`.
"""

from __future__ import annotations

import os

import pytest

from conftest import ORG, REPO, SCAFFOLD, run_script

FAMILY = REPO / "scripts" / "family.py"

#: What `--dry-run` prints when it goes all the way.
DRY_RUN_DONE = "--dry-run: nothing was created."

#: An identity the environment offers, which an empty flag must not take.
FALLBACK = "Fallback Human"

#: The refusals each tool ends on, by the flag passed empty: the start of
#: its `REFUSED` line, which names the flag and the value as typed.
SCAFFOLD_VALIDATOR = "which the project's own validate-manifest.py refuses: "
INIT_VALIDATOR = "which the holder's own validate-family.py refuses: "
ID_RULE = "must match ^[a-z0-9][a-z0-9-]*$"
EMPTY_ROWS = {
    "scaffold": {
        "--id": f"REFUSED scaffold-bad-id: --id '' {ID_RULE}",
        "--name": "REFUSED scaffold-manifest-invalid: --name is '', "
                  f"{SCAFFOLD_VALIDATOR}manifest-name: ",
        "--elected-on": "REFUSED election-date-malformed: --elected-on '' is "
                        "not a YYYY-MM-DD date",
        "--reference": "REFUSED scaffold-manifest-invalid: --reference is '', "
                       f"{SCAFFOLD_VALIDATOR}manifest-reference: ",
        "--elected-by": "REFUSED scaffold-manifest-invalid: --elected-by is "
                        f"'', {SCAFFOLD_VALIDATOR}manifest-elected-by: ",
    },
    "family": {
        "--id": f"REFUSED family-bad-id: --id '' {ID_RULE}",
        "--name": "REFUSED family-manifest-invalid: --name is '', "
                  f"{INIT_VALIDATOR}family-name: ",
        "--created-on": "REFUSED family-manifest-invalid: --created-on is '', "
                        f"{INIT_VALIDATOR}family-created-on: ",
        "--created-by": "REFUSED family-manifest-invalid: --created-by is '', "
                        f"{INIT_VALIDATOR}family-created-by: ",
    },
}

#: Per tool: the command, its name flag and name, and the flags naming who
#: and when, which a row leaves out when it passes that flag empty.
TOOLS = {
    "scaffold": {"command": (SCAFFOLD,), "name": ("--project", "NorthWind"),
                 "who": "--elected-by", "when": "--elected-on"},
    "family": {"command": (FAMILY, "init"), "name": ("--family", "NorthWind"),
               "who": "--created-by", "when": "--created-on"},
}

#: No identity at all: no GIT_AUTHOR_NAME, and no `user.name` in a global or
#: system config git can read.
NO_IDENTITY = {"GIT_AUTHOR_NAME": "", "GIT_COMMITTER_NAME": "",
               "GIT_CONFIG_GLOBAL": os.devnull,
               "GIT_CONFIG_SYSTEM": os.devnull}


def dry_run(tmp_path, tool: str, *extra: str, env: dict | None = None,
            who: bool = True, when: bool = True):
    """One `--dry-run` of `tool` for `NorthWind`, with `extra`, into a local
    remote. `who` and `when` pass the tool's own creator and date flags;
    a row that passes one of them empty leaves the default out."""
    spec = TOOLS[tool]
    remotes = tmp_path / "remotes"
    result = run_script(
        *spec["command"], "--org", ORG, *spec["name"],
        *((spec["who"], "Test Human") if who else ()),
        *((spec["when"], "2026-09-02") if when else ()),
        *extra, "--dry-run",
        "--local-remote-dir", str(remotes),
        "--work-dir", str(tmp_path / "work"),
        env={"GIT_AUTHOR_NAME": FALLBACK, **(env or {})})
    assert not remotes.exists()
    assert not (tmp_path / "work").exists()
    return result


def refused_line(result) -> str:
    """The `REFUSED` line a run ended on."""
    return next((line for line in result.stderr.splitlines()
                 if line.startswith("REFUSED ")), "")


def assert_refused_by_name(result, starts: str) -> None:
    """Exit 2, before the plan, on the refusal `starts`: the flag named as
    passed, never as a value the run filled in."""
    assert result.returncode == 2, result.stdout + result.stderr
    assert refused_line(result).startswith(starts), result.stderr
    assert "not given" not in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout == "", result.stdout


@pytest.mark.parametrize("tool, flag", [
    pytest.param(tool, flag, id=f"{tool}{flag}")
    for tool, rows in EMPTY_ROWS.items() for flag in rows])
def test_a_flag_passed_empty_is_refused_by_name(tmp_path, tool, flag):
    """One row per flag (#911): the flag passed empty is refused by name
    before the plan, and the environment's identity, which the run takes
    where the flag is not given, is not taken for it."""
    spec = TOOLS[tool]
    result = dry_run(tmp_path, tool, f"{flag}=",
                     who=flag != spec["who"], when=flag != spec["when"])
    assert_refused_by_name(result, EMPTY_ROWS[tool][flag])
    assert FALLBACK not in result.stderr


@pytest.mark.parametrize("tool", list(TOOLS))
def test_the_flags_not_given_still_take_their_defaults(tmp_path, tool):
    """THE CONTROL: with none of these flags, each tool plans its defaults,
    the creator from GIT_AUTHOR_NAME among them, and exits 0. What the rows
    above refuse is the empty value, not the default."""
    result = dry_run(tmp_path, tool, who=False, when=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert DRY_RUN_DONE in result.stdout
    assert f"{FALLBACK} on " in result.stdout
    assert "(northwind)" in result.stdout


@pytest.mark.parametrize("tool, refusal", [
    pytest.param("scaffold", "REFUSED scaffold-no-elector: no --elected-by, "
                 "no GIT_AUTHOR_NAME and no `git config user.name`.",
                 id="scaffold"),
    pytest.param("family", "REFUSED family-no-creator: no --created-by, no "
                 "GIT_AUTHOR_NAME and no `git config user.name`.",
                 id="family")])
def test_with_no_identity_an_empty_creator_is_named_as_passed(
        tmp_path, tool, refusal):
    """#911: with no identity at all, `--elected-by ''` was refused as
    "no --elected-by", of a flag that was passed (`--created-by ''`
    alike). It is named as passed now, by the validator; the no-elector
    refusal is still what a run with no flag and no identity gets."""
    who = TOOLS[tool]["who"]
    passed = dry_run(tmp_path / "passed", tool, f"{who}=", who=False,
                     env=NO_IDENTITY)
    assert_refused_by_name(passed, EMPTY_ROWS[tool][who])
    assert f"no {who}" not in passed.stderr
    omitted = dry_run(tmp_path / "omitted", tool, who=False, env=NO_IDENTITY)
    assert omitted.returncode == 2, omitted.stdout + omitted.stderr
    assert refused_line(omitted).startswith(refusal), omitted.stderr
