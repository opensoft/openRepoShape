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

AND THE FOLDER FLAGS (#972's review, S2). `--work-dir` and
`--local-remote-dir` in both tools, and `init`'s `--into`, were parsed as a
`Path`, and `Path("")` is `.`: passed empty, each was read as the directory
the run is in, without a word, and from the root of a checkout of
openRepoShape `init --into ''` planned the holder inside it. Each is now
refused by name, `<flag>-no-path`, as `--pin-source ''` is
(`pin-source-no-path`), by the dry run and the real run alike, before
anything is made. A typed `.` is still this directory, and a flag not given
keeps its default.

Every run is into `--local-remote-dir`, which never calls `gh`; a row that
passes it empty would read it as `.`, a local folder too. Every run is a
`--dry-run`, and each folder row is also run for real.
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


# --- the folder flags (#972's review, S2) -----------------------------------

#: Each folder flag a tool takes, by `(tool, flag)`: the code it is refused
#: as when passed empty, what its remedy says the folder is for, and what it
#: says the run does with no flag at all, in that tool's words.
FOLDER_ROWS = {
    ("scaffold", "--work-dir"): (
        "work-dir-no-path", "the folder the working trees are built in",
        "they are built in a temporary directory"),
    ("scaffold", "--local-remote-dir"): (
        "local-remote-dir-no-path",
        "the folder the bare repositories are made in",
        "they are created on GitHub"),
    ("family", "--into"): (
        "into-no-path", "the parent folder the family folder is made in",
        "it is made in the directory you stand in, which is refused inside "
        "a checkout of openRepoShape"),
    ("family", "--work-dir"): (
        "work-dir-no-path", "the folder the holder is made in",
        "the holder lands in a family folder, by --into"),
    ("family", "--local-remote-dir"): (
        "local-remote-dir-no-path",
        "the folder the holder's bare repository is made in",
        "it is created on GitHub"),
}
FOLDER_PARAMS = [pytest.param(tool, flag, id=f"{tool}{flag}")
                 for tool, flag in FOLDER_ROWS]


def folder_run(tmp_path, tool: str, flag: str, value: str | None, *,
               dry_run: bool = True):
    """One run of `tool` for `NorthWind` from `tmp_path/here`, an empty
    folder, with `flag` given `value`, or left out when `value` is None.
    The other folder flags name folders under `tmp_path` that do not exist:
    `--local-remote-dir`, and `--work-dir` but beside `init`'s `--into`,
    which it excludes."""
    spec = TOOLS[tool]
    here = tmp_path / "here"
    here.mkdir(exist_ok=True)
    folders = {"--local-remote-dir": tmp_path / "remotes",
               "--work-dir": tmp_path / "work"}
    if flag == "--into":
        del folders["--work-dir"]
    folders.pop(flag, None)
    if value is not None:
        folders[flag] = value
    return run_script(
        *spec["command"], "--org", ORG, *spec["name"],
        spec["who"], "Test Human", spec["when"], "2026-09-02",
        *(f"{name}={folder}" for name, folder in folders.items()),
        *(["--dry-run"] if dry_run else []),
        cwd=here, env={"GIT_AUTHOR_NAME": FALLBACK})


def everything_under(root) -> list:
    """Every path under `root`, so a test sees whether a run made one."""
    return sorted(path.relative_to(root).as_posix()
                  for path in root.rglob("*"))


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real-run"])
@pytest.mark.parametrize("tool, flag", FOLDER_PARAMS)
def test_a_folder_flag_passed_empty_is_refused_by_name(tmp_path, tool, flag,
                                                       dry_run):
    """One row per folder flag per tool, by the dry run and the real run:
    passed empty, the flag is refused by name before anything is made, and
    told the three ways on, a path, `.`, or no flag. Read as a `Path` it was
    `.`, so each built, made or landed in the directory the run stood in."""
    code, names, absent = FOLDER_ROWS[tool, flag]
    (tmp_path / "here").mkdir()
    before = everything_under(tmp_path)
    result = folder_run(tmp_path, tool, flag, "", dry_run=dry_run)
    said = (f"REFUSED {code}: `{flag} ''` names no path. An empty path would "
            "be read as the directory this runs in.")
    assert_refused_by_name(result, said)
    assert refused_line(result) == said, result.stderr
    assert (f"\nRemediation: nothing was created, and `--dry-run` refuses the "
            f"same. Give {names} (`{flag} <dir>`), or `.` to mean this "
            f"directory; with no {flag}, {absent}.\n") in result.stderr
    assert everything_under(tmp_path) == before, "the run made something"


@pytest.mark.parametrize("tool, flag", FOLDER_PARAMS)
def test_a_folder_flag_typed_as_a_dot_is_still_this_directory(tmp_path, tool,
                                                              flag):
    """THE CONTROL: the remedy's `.` is taken, as it always was, and the
    dry run plans the folder it names and makes nothing."""
    result = folder_run(tmp_path, tool, flag, ".")
    assert result.returncode == 0, result.stdout + result.stderr
    assert DRY_RUN_DONE in result.stdout
    assert everything_under(tmp_path) == ["here"]


@pytest.mark.parametrize("tool, flag", [
    pytest.param(tool, flag, id=f"{tool}{flag}")
    for tool, flag in FOLDER_ROWS if flag != "--local-remote-dir"])
def test_a_folder_flag_not_given_keeps_its_default(tmp_path, tool, flag):
    """THE CONTROL: with no `--work-dir` the scaffold builds in a temporary
    directory, and with neither `--into` nor `--work-dir` `init` lands where
    the person stands, as before. (No `--local-remote-dir` is GitHub, which
    the tests of a dry run against `gh` hold.)"""
    result = folder_run(tmp_path, tool, flag, None)
    assert result.returncode == 0, result.stdout + result.stderr
    assert DRY_RUN_DONE in result.stdout
    if tool == "family":
        holder = (tmp_path / "here" / "NorthWind" / "NorthWind").resolve()
        assert f"landing      {holder}" in result.stdout, result.stdout
    assert everything_under(tmp_path) == ["here"]


def option_help(tool: str, flag: str) -> str:
    """`flag`'s entry in `tool`'s `--help`, its lines joined: argparse is
    given a terminal wide enough that it breaks no word, a code's hyphen
    among them."""
    result = run_script(*TOOLS[tool]["command"], "--help",
                        env={"COLUMNS": "1000"})
    assert result.returncode == 0, result.stderr
    entries, current = {}, None
    for line in result.stdout.splitlines():
        if line.startswith("  -"):
            current = line.split()[0]
            entries[current] = [line]
        elif current and line.startswith("   "):
            entries[current].append(line)
        else:
            current = None
    assert flag in entries, result.stdout
    return " ".join(" ".join(entries[flag]).split())


@pytest.mark.parametrize("tool, flag", FOLDER_PARAMS)
def test_each_folder_flag_s_help_says_what_empty_and_a_dot_mean(tool, flag):
    """#999: each folder flag's `--help` says what #972 made true, as
    `--pin-source`'s says `pin-source-no-path`: an empty value is refused by
    its code, and `.` is the directory the run stands in."""
    code = FOLDER_ROWS[tool, flag][0]
    assert (f"An empty value is refused as `{code}`, and `.` means the "
            "directory the run stands in.") in option_help(tool, flag)
