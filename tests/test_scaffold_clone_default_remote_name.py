# SPDX-License-Identifier: Apache-2.0
"""`scaffold-project.py --local-remote-dir` under a `clone.defaultRemoteName`
of the person's own (#1275): the clone `git submodule add` makes names its
remote `origin`.

`git clone` names the remote it makes after `clone.defaultRemoteName`, and
`_build_assembly_root` addresses the clone `git submodule add` makes of each
leg as `origin`. With `upstream` in the global git config the scaffold made
both legs, pushed them, and ended `REFUSED a git or gh command failed`, exit
2, at `git remote set-url origin <url>` in the first mount: `error: No such
remote 'origin'`, with the root's bare repository still empty (measured on
main `27397a4b5`, git 2.43). With a name git refuses, `a..b`, it ended one
step earlier, at `git submodule add` itself, exit 128: `'a..b' is not a valid
remote name`. The mount's `git submodule add` now carries `-c
clone.defaultRemoteName=origin`, ahead of the verb, which reaches the clone
the verb makes. It is the one clone the scaffold makes: every other
repository it makes is `git init`ed and given `origin` by `git remote add`.

EACH ROW GIVES THE SETTING TO ITS OWN CHILD ONLY: a `GIT_CONFIG_GLOBAL` of
its own, passed in that child's environment, and `GIT_CONFIG_NOSYSTEM`. The
file holds the session's two maintenance lines and then the setting, or
nothing after them, and NOTHING OF THE DEVELOPER'S OWN CONFIG: a person whose
own global config holds `clone.defaultRemoteName` has no control run to
compare against if the control inherits it (RV1268's N3 on #1268, whose
premise row failed for such a person). So the premise, the control and the
rows below hold on any machine's config.

The run without the setting and the runs with it are made at ONE PATH, each
moved aside before the next: the leg templates carry the root's clone URL, so
a second path is a second set of bytes; and with the commit dates pinned, the
same path gives the same commits. Two runs are then equal object for object.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import NO_AUTO_MAINTENANCE, ORG, SCAFFOLD, git, run_script

NAME = "Northwind"
LEGS = (f"{NAME}-spec", f"{NAME}-code")
#: The three repositories the scaffold makes, legs first.
REPOSITORIES = (*LEGS, NAME)
#: The person's own setting, as #1275's report held it.
UPSTREAM = b"[clone]\n\tdefaultRemoteName = upstream\n"
#: A name git refuses for a remote: `fatal: 'a..b' is not a valid remote
#: name`, from any clone that reads it.
REFUSED_NAME = b"[clone]\n\tdefaultRemoteName = a..b\n"
#: Commit dates pinned, so that two runs at one path make the same commits.
PINNED = {"GIT_AUTHOR_DATE": "2026-09-02T00:00:00Z",
          "GIT_COMMITTER_DATE": "2026-09-02T00:00:00Z"}
#: What each run is given after the maintenance lines.
SETTINGS = {"without": b"", "upstream": UPSTREAM, "refused": REFUSED_NAME}
WITH_THE_SETTING = ("upstream", "refused")


def child_env(directory: Path, setting: bytes) -> dict:
    """The environment that gives one child `setting` and nothing else of
    git's config: a `GIT_CONFIG_GLOBAL` holding the session's maintenance
    lines and then `setting`, and no system config."""
    directory.mkdir(parents=True, exist_ok=True)
    config = directory / "global.gitconfig"
    lines = []
    for key, value in NO_AUTO_MAINTENANCE:
        section, name = key.split(".")
        lines += [f"[{section}]", f"\t{name} = {value}"]
    config.write_bytes(("\n".join(lines) + "\n").encode("utf-8") + setting)
    return {"GIT_CONFIG_GLOBAL": str(config), "GIT_CONFIG_NOSYSTEM": "1",
            **PINNED}


def remotes(repository: Path) -> list[str] | None:
    """`git remote` in `repository`, or None where the run made none."""
    if not (repository / ".git").exists():
        return None
    return git("remote", cwd=repository).stdout.split()


def leg_dump(remotes_dir: Path) -> list[str]:
    """Every ref and every object of the three repositories pushed into
    `remotes_dir`, with HEAD: an object's id is the hash of its bytes, so two
    equal dumps are two byte-identical sets of repositories. A repository the
    run did not make is `absent`, so a run that stopped early compares
    unequal, and does not raise."""
    lines: list[str] = []
    for name in REPOSITORIES:
        bare = remotes_dir / f"{name}.git"
        if not bare.is_dir():
            lines.append(f"== {name} absent")
            continue
        lines += [f"== {name}",
                  git("symbolic-ref", "HEAD", cwd=bare).stdout.strip()]
        lines += git("for-each-ref",
                     "--format=%(objectname) %(objecttype) %(refname)",
                     cwd=bare).stdout.splitlines()
        lines += sorted(git("cat-file", "--batch-all-objects",
                            "--batch-check", cwd=bare).stdout.splitlines())
    return lines


def clone_remotes(work: Path) -> dict:
    """The remotes of each repository the scaffold made in `work`: the
    root, each leg's mount in it, and each leg's own work tree."""
    root = work / NAME
    return {"root": remotes(root),
            "spec mount": remotes(root / "spec"),
            "code mount": remotes(root / "code"),
            "spec tree": remotes(work / LEGS[0]),
            "code tree": remotes(work / LEGS[1])}


def session_view() -> dict:
    """What the rest of the session holds of git's config: the environment
    variables that name it, the file `GIT_CONFIG_GLOBAL` names, and what
    git says `clone.defaultRemoteName` is where it is asked. A developer's
    own setting is in that answer, and is the same before and after."""
    named = os.environ.get("GIT_CONFIG_GLOBAL")
    held = Path(named) if named else None
    asked = subprocess.run(
        ["git", "config", "--get", "clone.defaultRemoteName"],
        capture_output=True, text=True, check=False)
    return {"named": {key: value for key, value in os.environ.items()
                      if key.startswith("GIT_CONFIG")},
            "bytes": held.read_bytes() if held and held.is_file() else None,
            "asked": (asked.returncode, asked.stdout)}


@pytest.fixture(scope="module")
def scaffolds(tmp_path_factory) -> dict:
    """One project scaffolded three times at one path: `without` the
    setting, with `upstream`, and with `refused`, a name git refuses."""
    base = tmp_path_factory.mktemp("scaffold-default-remote-name")
    before = session_view()
    at = base / "run"
    runs: dict = {}
    for name, setting in SETTINGS.items():
        env = child_env(base / "config" / name, setting)
        result = run_script(
            SCAFFOLD, "--org", ORG, "--project", NAME,
            "--elected-by", "Test Human", "--elected-on", "2026-09-02",
            "--local-remote-dir", str(at / "remotes"),
            "--work-dir", str(at / "work"), env=env)
        runs[name] = {"result": result, "config": env["GIT_CONFIG_GLOBAL"],
                      "dump": leg_dump(at / "remotes"),
                      "remotes": clone_remotes(at / "work")}
        if at.exists():
            shutil.move(str(at), str(base / name))
    return {**runs, "before": before, "after": session_view()}


def test_the_premise_a_plain_clone_names_its_remote_after_the_setting(
        tmp_path):
    """Asked of git, not assumed: under the rows' config for `upstream` a
    plain `git clone` names its remote `upstream`, under the control's it
    names it `origin`, and under `a..b` git refuses to clone at all. If git
    stops reading the setting, this fails rather than the rows below passing
    over nothing. The control's file holds none of the developer's own
    config, so this holds for a developer whose own config sets it."""
    source = tmp_path / "Thing"
    git("init", "-q", "-b", "main", str(source), cwd=tmp_path)
    git("commit", "-q", "--allow-empty", "-m", "a commit", cwd=source)
    made = {}
    for name, setting in SETTINGS.items():
        env = {**os.environ,
               **child_env(tmp_path / "config" / name, setting)}
        made[name] = subprocess.run(
            ["git", "clone", "-q", str(source), str(tmp_path / name)],
            env=env, capture_output=True, text=True, check=False)
    assert made["without"].returncode == 0, made["without"].stderr
    assert made["upstream"].returncode == 0, made["upstream"].stderr
    assert remotes(tmp_path / "without") == ["origin"]
    assert remotes(tmp_path / "upstream") == ["upstream"]
    assert made["refused"].returncode != 0, made["refused"].stderr
    assert "a..b" in made["refused"].stderr, made["refused"].stderr


@pytest.mark.parametrize("run", tuple(SETTINGS))
def test_the_scaffold_exits_0_with_or_without_the_setting(scaffolds, run):
    """On main the run under `upstream` ended `REFUSED a git or gh command
    failed`, exit 2, `error: No such remote 'origin'`, and the run under
    `a..b` ended exit 128, `'a..b' is not a valid remote name`, at the
    mount's `git submodule add`."""
    result = scaffolds[run]["result"]
    said = result.stderr[-3000:] + result.stdout[-1500:]
    assert result.returncode == 0, said
    assert "REFUSED" not in result.stderr, result.stderr[-3000:]
    assert "No such remote" not in result.stderr + result.stdout
    assert "Working trees are at" in result.stdout, result.stdout[-1500:]


@pytest.mark.parametrize("run", WITH_THE_SETTING)
def test_the_legs_and_root_are_the_bytes_a_run_without_the_setting_pushes(
        scaffolds, run):
    """Every ref and object of both legs and the root, HEAD too. (On main
    the legs were these bytes as well, both being pushed before the mount
    refused; the root was not, its bare repository was still empty.)"""
    without = scaffolds["without"]["dump"]
    assert sum(line.endswith(" refs/heads/main") for line in without) == 3, \
        without
    assert len(without) > 3 * len(REPOSITORIES), without
    assert scaffolds[run]["dump"] == without


@pytest.mark.parametrize("run", WITH_THE_SETTING)
def test_each_repository_the_scaffold_made_has_the_remotes_it_has_without_it(
        scaffolds, run):
    """The root and each mount name their remote `origin`, which
    `_build_assembly_root` sets the leg's url on, and each leg's own work
    tree has the `origin` it was given by `git remote add`. On main the
    first mount named it `upstream`, the second mount and the root were
    never made, and under `a..b` not even the first mount was."""
    without = scaffolds["without"]["remotes"]
    assert without == {name: ["origin"] for name in without}, without
    assert len(without) == 5, without
    assert scaffolds[run]["remotes"] == without


def test_the_setting_goes_to_the_row_s_own_child_only(scaffolds):
    """No other row, and no process of the session, is given the setting:
    the environment variables that name git's config, the file
    `GIT_CONFIG_GLOBAL` names, and git's own answer where it is asked here
    are what they were before the three scaffolds, and the files the
    children were given are the children's own."""
    assert scaffolds["after"] == scaffolds["before"]
    named = scaffolds["before"]["named"].get("GIT_CONFIG_GLOBAL")
    for run, setting in SETTINGS.items():
        config = Path(scaffolds[run]["config"])
        assert str(config) != named, run
        assert (b"defaultRemoteName" in config.read_bytes()) == bool(setting)
