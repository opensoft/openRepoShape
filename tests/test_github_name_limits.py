# SPDX-License-Identifier: Apache-2.0
"""What GitHub will not take is refused before anything is created (#838).

GitHub keeps a repository's name to 100 characters, a topic to 50 and a
user's or an organisation's name to 39. The 100 and the 50 are documented on
docs.github.com; for 39 the docs give the limit on a user's name (Enterprise
Cloud's username considerations) and nothing for an organisation's. No run
here creates a real repository, so none of the three is measured. The fake
`gh` below holds only the topic to its number, refusing a topic over 50
characters; a name over 100 or an organisation over 39 never reaches it.
Nothing asked them before #838:

* `scaffold-project.py` sets `xf-project-<id>` on each repository LAST, with
  `gh repo edit --add-topic`, after it has created and seeded all three. An
  id over 39 characters, which a `--project` of 40 or more gives by default,
  failed there; `adopt-project.py execute` failed there after both legs and
  the split were pushed.
* A `--project` of 96 to 250 characters, and an `--org` of 40 to 255, passed
  the plan and met GitHub's refusal at the first `gh repo create`.

Each is now asked before any repository is made: by the scaffold's plan,
under `--dry-run` alike, before any process is started where `--elected-by`
or GIT_AUTHOR_NAME names the elector (otherwise `git config user.name` is
read first), and by `execute` before `_confirm` and before either leg
exists. Only where a GitHub repository will be made: under
`--local-remote-dir` a name's limit is the disk's, which the same helper
still asks, and no topic is set. `setup-project.py` hands the three values to
the scaffold's plan at its step (5), which refuses them there, and its
`--help` says the same three numbers, which it cannot import.

An adoption's assembly root on GitHub is the source's own repository, so a
leg over 100 characters named after a root of 96 to 100 is mended by
renaming the source on GitHub first, as `adopt-bad-id` says of a name the
policy refuses, and not by a shorter `--project`, which plans another
repository (#859's review). A root of 101 or more is no name GitHub gives a
repository, and a leg the plan was edited to name is the plan's own: both
keep "Use a shorter --project" (#859's re-review).

The in-process runs refuse every process start (`no_process`), so a refusal
that passes came before git, before `gh` and before the work directory. The
end-to-end runs give the tool a `gh` that refuses a topic over 50 characters
as GitHub documents it: they are POSIX only, as their `gh` is a `#!` script.
"""

from __future__ import annotations

import importlib.util
import os
import shlex
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import test_adopt_github_exits
from conftest import (ADOPT, ORG, PTY_SKIP, REPO, SCAFFOLD, WINDOWS_SKIP, git,
                      make_source_repo, run_in_a_terminal, run_script,
                      write_plan)
from test_adopt_github_exits import (NORTHWIND, SOURCE_TREE, SPLIT_BRANCH,
                                     gh_calls, github_run, heads,
                                     needs_filter_repo)
from test_adopt_project_is_the_source import RENAME_FIRST
from test_scaffold_leg_path_collisions import (  # noqa: F401 (a fixture)
    ProcessStarted, no_process,
)
from test_setup_project_py import (SETUP_PROJECT, entry_point_module,
                                   run_entry, terminal_env)

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402
from repo_shape import TOPIC_PREFIX, NamingPolicy  # noqa: E402

#: GitHub's limits, written out here rather than read back from the module
#: that asks them, so a change to either is a change a test sees.
NAME_MAX, TOPIC_MAX, OWNER_MAX = 100, 50, 39
#: The longest project name and id they leave: `-spec` adds five to a name,
#: and the topic is `xf-project-<id>`.
PROJECT_MAX, ID_MAX = NAME_MAX - 5, TOPIC_MAX - len("xf-project-")

#: What each refusal is called.
NAME_TOO_LONG = "REFUSED scaffold-name-too-long"
TOPIC_TOO_LONG = "REFUSED scaffold-topic-too-long"
ORG_TOO_LONG = "REFUSED scaffold-org-too-long"

IDENTITY = ("--org", ORG, "--elected-by", "Test Human", "--elected-on",
            "2026-09-02")

#: What a refusal of a name over GitHub's limit says of GitHub's numbers, at
#: the end of its remediation: the id's bound with the name's.
GITHUB_LIMITS_SAID = (
    "GitHub keeps a repository's name to at most 100 characters, so a "
    "project name is at most 95, and a topic to at most 50, so the id in the "
    "topic `xf-project-<id>`, which is the project name lowercased unless "
    "--id is given, is at most 39.")


def a_name(length: int) -> str:
    """A project name of `length` characters: one CamelCase token."""
    return "A" + "b" * (length - 1)


def an_id(length: int) -> str:
    return "a" * length


def an_org(length: int) -> str:
    return "o" * length


# --- the numbers ---------------------------------------------------------------

def test_the_limits_are_githubs_numbers():
    assert shape_materialize.GITHUB_NAME_MAX == NAME_MAX
    assert shape_materialize.GITHUB_TOPIC_MAX == TOPIC_MAX
    assert shape_materialize.GITHUB_OWNER_MAX == OWNER_MAX
    assert shape_materialize.GITHUB_PROJECT_MAX == PROJECT_MAX
    assert PROJECT_MAX == 95
    assert shape_materialize.GITHUB_ID_MAX == ID_MAX
    assert ID_MAX == 39
    assert len("-spec") == len("-code")


def test_the_id_bound_is_the_topic_the_naming_policy_gives():
    """`GITHUB_ID_MAX` is read off `TOPIC_PREFIX`; the topic a run sets is
    the policy's template. The two are one prefix, so the bound the help
    and the remediations state is the one the topic check applies."""
    policy = NamingPolicy.load(REPO / "contracts" / "repository-naming.yaml")
    assert policy.topic_for("") == TOPIC_PREFIX
    assert len(policy.topic_for(an_id(ID_MAX))) == TOPIC_MAX


def test_setup_project_says_the_numbers_it_cannot_import():
    """`setup-project.py` runs before there is a checkout to import from, so
    its `--help` spells the numbers out; they are the plan's. #811 gives it
    `GITHUB_NAME_MAX` and `PROJECT_NAME_MAX` of its own, for its own check
    of `--project`: where it has them, they are the plan's too."""
    module = entry_point_module()
    usage = " ".join(module.USAGE.split())
    for sentence in (
            f"At most {PROJECT_MAX} characters without --local-remote-dir: "
            f"GitHub keeps a repository's name to {NAME_MAX}, and -spec adds "
            "5.",
            f"At most {ID_MAX} characters without --local-remote-dir: GitHub "
            f"keeps the topic xf-project-<id> to {TOPIC_MAX}.",
            f"At most {OWNER_MAX} characters without --local-remote-dir, "
            "GitHub's limit on an organisation's name."):
        assert sentence in usage, sentence
    for own, plans in (("GITHUB_NAME_MAX", NAME_MAX),
                       ("PROJECT_NAME_MAX", PROJECT_MAX)):
        assert getattr(module, own, plans) == plans, own


def help_entry(text: str, flag: str) -> str:
    """The `--help` entry of `flag` (`--id ID`), as one line: its own line
    and each continuation under it, up to the next option."""
    lines = text.splitlines()
    first = next(i for i, line in enumerate(lines)
                 if line.startswith(f"  {flag}"))
    entry = [lines[first]]
    for line in lines[first + 1:]:
        if not line.startswith(" " * 6):
            break
        entry.append(line)
    return " ".join(" ".join(entry).split())


#: What each direct tool's `--help` says of each bound, by the flag: the
#: scaffold asks them in its plan, adopt's `execute` before either leg.
SAID = {
    SCAFFOLD: {
        "--project PROJECT": (
            f"at most {PROJECT_MAX} characters without --local-remote-dir, "
            f"as GitHub keeps a repository's name to {NAME_MAX} and `-spec` "
            "adds 5"),
        "--id ID": (
            f"at most {ID_MAX} characters without --local-remote-dir, as "
            f"GitHub keeps the topic `xf-project-<id>` to {TOPIC_MAX}"),
        "--org ORG": (
            f"at most {OWNER_MAX} characters without --local-remote-dir, "
            "GitHub's limit on an organisation's name"),
    },
    ADOPT: {
        "--project PROJECT": (
            f"`execute` refuses one over {PROJECT_MAX} characters without "
            "--local-remote-dir: GitHub keeps a leg's name, "
            f"`<Project>-spec`, to {NAME_MAX}."),
        "--id ID": (
            f"`execute` refuses one over {ID_MAX} characters without "
            f"--local-remote-dir: GitHub keeps a topic to {TOPIC_MAX}, and "
            "the topic is `xf-project-<id>`."),
        "--org ORG": (
            f"`execute` refuses one over {OWNER_MAX} characters without "
            "--local-remote-dir, GitHub's limit on an organisation's name."),
    },
}


@pytest.mark.parametrize("tool, args", [
    pytest.param(SCAFFOLD, ("--help",), id="scaffold"),
    pytest.param(ADOPT, ("plan", "--help"), id="adopt-plan"),
])
def test_each_direct_tool_says_the_bound_where_the_value_is_typed(tool, args):
    """`--project`, `--id` and `--org` each say their bound in `--help`."""
    result = run_script(tool, *args)
    assert result.returncode == 0, result.stderr
    for flag, sentence in SAID[tool].items():
        entry = help_entry(result.stdout, flag)
        assert sentence in entry, (flag, entry)


# --- the one helper the two tools ask -----------------------------------------

def refusal(call, *args):
    with pytest.raises(shape_materialize.Refusal) as caught:
        call(*args)
    return caught.value


def test_a_repository_name_github_keeps_is_not_refused():
    refuse = shape_materialize.refuse_unstorable_names
    assert refuse("r", [], [], ["a" * NAME_MAX]) is None
    assert refuse("r", ["a" * 255], [], []) is None


def test_a_repository_name_over_githubs_limit_is_refused_by_both_ends():
    name = a_name(PROJECT_MAX + 1)
    caught = refusal(shape_materialize.refuse_unstorable_names, "r",
                     [name], [], [name, f"{name}-spec", f"{name}-code"])
    assert caught.code == "r"
    assert caught.detail == (
        "Abbbbbbbbbbb...bbbbbbb-spec is 101 characters, and GitHub keeps a "
        "repository's name to at most 100; Abbbbbbbbbbb...bbbbbbb-code is "
        "101 characters, and GitHub keeps a repository's name to at most "
        "100.")
    assert "a disk keeps" not in caught.remediation
    assert caught.remediation.endswith(GITHUB_LIMITS_SAID)


def test_a_name_the_disk_cannot_hold_is_named_once_and_both_limits_said():
    """`<251>-spec` is over both limits: the disk's sentence names it, and
    GitHub's does not name it again; the root, over GitHub's alone, is
    named for GitHub's. The remediation states both numbers."""
    name = a_name(251)
    names = [name, f"{name}-spec", f"{name}-code"]
    caught = refusal(shape_materialize.refuse_unstorable_names, "r", names,
                     [], names)
    sentences = caught.detail.rstrip(".").split("; ")
    assert [s.split(" is ", 1)[0] for s in sentences] == [
        "Abbbbbbbbbbb...bbbbbbb-spec", "Abbbbbbbbbbb...bbbbbbb-code",
        "Abbbbbbbbbbb...bbbbbbbbbbbb"]
    assert "bytes long" in sentences[0]
    assert "GitHub" in sentences[2]
    assert "a disk keeps a name of at most 255 bytes" in caught.remediation
    assert "; and GitHub keeps" in caught.remediation


#: The first words of every remediation that tells the person to pick a
#: shorter `--project`, before the limit each name broke.
SHORTER_PROJECT = (
    "Remediation: nothing was created. Use a shorter --project: the three "
    "repositories are named `<Project>`, `<Project>-spec` and "
    "`<Project>-code`, and ")

#: The remediation of a name the disk alone cannot hold, as it was before
#: #838 and is still.
DISK_REMEDY = (
    f"{SHORTER_PROJECT}a disk keeps a name of at most 255 bytes, which under "
    "--local-remote-dir includes the `.git` each bare repository adds.")


def test_the_disk_alone_keeps_its_remediation_word_for_word():
    caught = refusal(shape_materialize.refuse_unstorable_names, "r",
                     [a_name(256)], [], [])
    assert caught.remediation == DISK_REMEDY


def test_a_topic_over_githubs_limit_is_refused():
    refuse = shape_materialize.refuse_a_topic_github_cannot_set
    assert refuse("r", TOPIC_PREFIX + an_id(ID_MAX), an_id(ID_MAX), "--id",
                  "Remedy.") is None
    caught = refusal(refuse, "r", TOPIC_PREFIX + an_id(ID_MAX + 1),
                     an_id(ID_MAX + 1), "--id", "Remedy.")
    assert caught.code == "r"
    assert caught.remediation == "Remedy."
    assert caught.detail == (
        "--id is aaaaaaaaaaaa...aaaaaaaaaaaa, 40 characters, so the topic "
        "this run sets on each repository, `xf-project-<id>`, is 51, and "
        "GitHub keeps a topic to at most 50: an id is at most 39 characters")


def test_an_organisation_over_githubs_limit_is_refused():
    refuse = shape_materialize.refuse_an_owner_github_cannot_have
    assert refuse("r", an_org(OWNER_MAX), "--org", "Remedy.") is None
    caught = refusal(refuse, "r", an_org(OWNER_MAX + 1), "--org", "Remedy.")
    assert caught.detail == (
        "--org is oooooooooooo...oooooooooooo, 40 characters, and GitHub "
        "keeps a user's or an organisation's name to at most 39, so no "
        "repository can be created under it")


# --- scaffold-project.py, in process: before any process starts ---------------

@pytest.fixture(scope="module")
def scaffold():
    spec = importlib.util.spec_from_file_location("scaffold_github_limits",
                                                  SCAFFOLD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def refused_plan(scaffold, capsys, *flags: str, dry_run: bool = True) -> str:
    """`main()` against GitHub with `flags`: it refuses with no process
    started (`no_process` holds) and no plan printed. Returns stderr."""
    code = scaffold.main([*IDENTITY, *flags,
                          *(["--dry-run"] if dry_run else [])])
    out, err = capsys.readouterr()
    assert (code, out) == (2, ""), out + err
    return err


def goes_on(scaffold, capsys, *flags: str) -> None:
    """`main()` with `flags` passes every question GitHub's limits ask and
    goes on to its first process, which `no_process` refuses."""
    with pytest.raises(ProcessStarted):
        scaffold.main([*IDENTITY, *flags, "--dry-run"])
    assert "too-long" not in capsys.readouterr().err


#: `(flags at the bound, flags one past it, the refusal)`: N and N+1
#: characters either side of each number.
EDGES = {
    "derived-id": (("--project", a_name(ID_MAX)),
                   ("--project", a_name(ID_MAX + 1)), TOPIC_TOO_LONG),
    "id": (("--project", "Atlas", "--id", an_id(ID_MAX)),
           ("--project", "Atlas", "--id", an_id(ID_MAX + 1)), TOPIC_TOO_LONG),
    "project": (("--project", a_name(PROJECT_MAX), "--id", "atlas"),
                ("--project", a_name(PROJECT_MAX + 1), "--id", "atlas"),
                NAME_TOO_LONG),
    "org": (("--project", "Atlas", "--org", an_org(OWNER_MAX)),
            ("--project", "Atlas", "--org", an_org(OWNER_MAX + 1)),
            ORG_TOO_LONG),
}


@pytest.mark.parametrize("edge", EDGES)
def test_the_value_at_githubs_bound_goes_on(scaffold, no_process, capsys,
                                             edge):
    goes_on(scaffold, capsys, *EDGES[edge][0])


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real"])
@pytest.mark.parametrize("edge", EDGES)
def test_one_past_githubs_bound_is_refused_before_any_process(
        scaffold, no_process, capsys, edge, dry_run):
    _, over, code = EDGES[edge]
    err = refused_plan(scaffold, capsys, *over, dry_run=dry_run)
    assert err.startswith(f"{code}: "), err
    assert "nothing was created" in err


#: How each of the scaffold's own refusals begins its remediation: a dry
#: run refuses what the real run would.
SCAFFOLD_NOTHING_MADE = ("Remediation: nothing was created, and `--dry-run` "
                         "refuses the same.")


def test_a_derived_id_is_named_as_derived_and_mended_with_an_id(
        scaffold, no_process, capsys):
    err = refused_plan(scaffold, capsys, "--project", a_name(ID_MAX + 1))
    assert err.startswith(
        f"{TOPIC_TOO_LONG}: --id (not given, so --project lowercased) is "
        "abbbbbbbbbbb...bbbbbbbbbbbb, 40 characters, "), err
    assert err.endswith(
        f"\n{SCAFFOLD_NOTHING_MADE} Pass an explicit --id of at most 39 "
        "characters: the id need not be --project lowercased, and --project, "
        "which names the three repositories, stays as it is.\n"), err


def test_an_empty_id_is_named_as_empty(scaffold, no_process, capsys):
    """`--id ''` falls back to `--project` lowercased, as `_identity` reads
    it, and is named as `_refuse_bad_id` names it: passed, and empty."""
    err = refused_plan(scaffold, capsys, "--project", a_name(ID_MAX + 1),
                       "--id", "")
    assert err.startswith(
        f"{TOPIC_TOO_LONG}: --id (empty, so --project lowercased) is "), err


def test_a_passed_id_is_named_as_passed(scaffold, no_process, capsys):
    err = refused_plan(scaffold, capsys, "--project", "Atlas", "--id",
                       an_id(ID_MAX + 1))
    assert err.startswith(f"{TOPIC_TOO_LONG}: --id is aaaa"), err
    assert err.endswith(f"\n{SCAFFOLD_NOTHING_MADE} Pass a shorter --id, of "
                        "at most 39 characters.\n"), err


def test_an_organisation_is_mended_as_github_spells_it(scaffold, no_process,
                                                       capsys):
    err = refused_plan(scaffold, capsys, *EDGES["org"][1])
    assert err.startswith(f"{ORG_TOO_LONG}: --org is oooo"), err
    assert err.endswith(
        f"\n{SCAFFOLD_NOTHING_MADE} Pass --org as GitHub spells the "
        "organisation, the `<org>` of `https://github.com/<org>`: GitHub "
        "gives no user or organisation a name of more than 39 "
        "characters.\n"), err


def test_a_long_name_with_a_short_id_still_plans(scaffold, no_process,
                                                 capsys):
    """A name of 40 to 95 characters keeps its name: a shorter `--id` is
    the way round the topic's bound."""
    for length in (ID_MAX + 1, 60, PROJECT_MAX):
        goes_on(scaffold, capsys, "--project", a_name(length), "--id", "atl")


def test_none_of_githubs_limits_is_asked_of_a_local_run(
        scaffold, no_process, capsys, tmp_path):
    """Under `--local-remote-dir` nothing goes to GitHub: no topic is set,
    the organisation names no account, and a name's limit is the disk's."""
    goes_on(scaffold, capsys, "--project", a_name(PROJECT_MAX + 1), "--org",
            an_org(OWNER_MAX + 1), "--local-remote-dir",
            str(tmp_path / "remotes"))
    assert not (tmp_path / "remotes").exists()


def test_the_topic_is_refused_before_a_pin_asks_gh(scaffold, no_process,
                                                   capsys, monkeypatch):
    """`_declaration` reads a `--pin`'s digest with `gh api` when no
    `--pin-source` is given; the topic and the organisation are refused
    before it is called."""
    called = []
    monkeypatch.setattr(scaffold, "_declaration",
                        lambda args: called.append(args) or ({}, set(), (),
                                                             {}))
    pin = ("--pin", f"openGlass@{'a' * 40}")
    refused_plan(scaffold, capsys, "--project", a_name(ID_MAX + 1), *pin)
    refused_plan(scaffold, capsys, "--project", "Atlas", "--org",
                 an_org(OWNER_MAX + 1), *pin)
    assert called == []
    goes_on(scaffold, capsys, "--project", a_name(ID_MAX), *pin)
    assert len(called) == 1, "the control never reached `_declaration`"


# --- scaffold-project.py end to end: GitHub's refusal, by its numbers ---------

#: A `gh` with no network that answers as GitHub documents: a repository it
#: has not got is not found, `repo create` makes one, and `repo edit
#: --add-topic` refuses a topic over 50 characters. Every call is logged.
FAKE_GH = b"""#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_GH_LOG"
case "$1 $2" in
  "repo view")
    echo "GraphQL: Could not resolve to a Repository with the name '$3'." >&2
    exit 1 ;;
  "repo create") exit 0 ;;
  "repo edit")
    topic=$5
    if [ "${#topic}" -gt 50 ]; then
      echo "HTTP 422: Topics must consist of 50 characters or less" >&2
      exit 1
    fi
    exit 0 ;;
esac
echo "fake gh: no network here" >&2
exit 1
"""


def fake_github(tmp_path: Path) -> tuple[dict, Path]:
    """The environment of a run that asks `FAKE_GH`, and its log."""
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_bytes(FAKE_GH)
    gh.chmod(0o755)
    config = tmp_path / "gh-config"
    config.mkdir()
    log = tmp_path / "gh.log"
    return ({"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
             "FAKE_GH_LOG": str(log), "GH_TOKEN": "bogus-token-for-tests",
             "GH_CONFIG_DIR": str(config)}, log)


def scaffold_on_github(tmp_path: Path, project: str):
    """A real scaffold of `project` against `FAKE_GH`, pushing nothing.
    Public, so no `gh` call asks the organisation's plan."""
    env, log = fake_github(tmp_path)
    result = run_script(SCAFFOLD, *IDENTITY, "--project", project,
                        "--visibility", "public", "--no-push", "--work-dir",
                        str(tmp_path / "work"), env=env)
    return result, log


@WINDOWS_SKIP
def test_an_id_github_cannot_set_is_refused_before_a_repository_exists(
        tmp_path):
    """On main the run created all three repositories and seeded them, and
    then GitHub refused `--add-topic`: exit 2 with three repositories made.
    Now nothing reaches `gh`."""
    result, log = scaffold_on_github(tmp_path, a_name(ID_MAX + 1))
    assert result.returncode == 2, result.stderr + result.stdout
    assert TOPIC_TOO_LONG in result.stderr
    assert not log.exists(), log.read_text(encoding="utf-8")
    assert not (tmp_path / "work").exists()


@WINDOWS_SKIP
def test_an_id_at_githubs_bound_is_set_on_all_three(tmp_path):
    name = a_name(ID_MAX)
    result, log = scaffold_on_github(tmp_path, name)
    assert result.returncode == 0, result.stderr + result.stdout
    calls = log.read_text(encoding="utf-8").splitlines()
    topic = TOPIC_PREFIX + name.lower()
    assert [c for c in calls if c.startswith("repo edit")] == [
        f"repo edit {ORG}/{name}{tail} --add-topic {topic}"
        for tail in ("", "-spec", "-code")]


# --- setup-project.py: its step (5), the scaffold's plan, refuses -------------

#: The `gh` a setup run asks: the preflight's three questions answered, a
#: repository it has not got not found (the plan's question), and anything
#: else refused, so no run here reaches GitHub.
SETUP_GH = b"""#!/bin/sh
case "$1 $2" in
  "--version "*) echo "gh version 2.50.0 (stub)" ;;
  "auth "*) exit 0 ;;
  "api user") echo tester ;;
  "repo view")
    echo "GraphQL: Could not resolve to a Repository with the name '$3'." >&2
    exit 1 ;;
  *) echo "stub gh: refused $*" >&2; exit 97 ;;
esac
"""


def setup_env(tmp_path: Path) -> dict:
    """`SETUP_GH` first on PATH, and a global git config of the run's own
    that names it as github.com's credential helper: a preflight in a
    terminal otherwise offers `gh auth setup-git` on a machine with none, as
    CI's runner is, and waits there for an answer nobody types. A file, not
    git's command scope, so no entry count is worked out by hand (#818)."""
    bin_dir = tmp_path / "setupbin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_bytes(SETUP_GH)
    gh.chmod(0o755)
    helper = f"!{shlex.quote(str(gh))} auth git-credential"
    assert '"' not in helper, helper
    assert "\\" not in helper, helper
    config = tmp_path / "setup.gitconfig"
    config.write_bytes(b'[credential "https://github.com"]\n\thelper = "'
                       + helper.encode("utf-8") + b'"\n')
    return {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "GIT_CONFIG_GLOBAL": str(config)}


def setup_flags(tmp_path: Path, *flags: str) -> list:
    """A setup run that ends at the plan (`-- --dry-run`)."""
    return ["--org", ORG, "--elected-by", "Tester", *flags, "--into",
            str(tmp_path / "parent" / "into"), "--", "--dry-run"]


#: `(flags, the refusal or None)`: a GitHub run, at each bound and past it.
SETUP_RUNS = {
    "derived-id-at": (("--project", a_name(ID_MAX)), None),
    "derived-id-over": (("--project", a_name(ID_MAX + 1)), TOPIC_TOO_LONG),
    "long-name-short-id": (("--project", a_name(PROJECT_MAX), "--id",
                            "atl"), None),
    "id-over": (("--project", "Atlas", "--id", an_id(ID_MAX + 1)),
                TOPIC_TOO_LONG),
    "org-at": (("--project", "Atlas", "--org", an_org(OWNER_MAX)), None),
    "org-over": (("--project", "Atlas", "--org", an_org(OWNER_MAX + 1)),
                 ORG_TOO_LONG),
}


@WINDOWS_SKIP
@pytest.mark.parametrize("case", SETUP_RUNS)
def test_setup_refuses_at_the_plan_what_github_will_not_take(tmp_path, case):
    flags, refused = SETUP_RUNS[case]
    result = run_entry(*setup_flags(tmp_path, *flags),
                       extra_env=setup_env(tmp_path))
    assert not (tmp_path / "parent").exists()
    if refused is None:
        assert result.returncode == 0, result.stderr + result.stdout
        assert "too-long" not in result.stderr
        return
    assert result.returncode == 2, result.stderr + result.stdout
    assert refused in result.stderr, result.stderr
    assert "REFUSED: the plan could not be produced (see above)." in \
        result.stderr
    assert "(5) the plan" in result.stdout


@WINDOWS_SKIP
def test_setup_asks_none_of_them_of_a_local_run(tmp_path):
    result = run_entry(*setup_flags(
        tmp_path, "--project", a_name(PROJECT_MAX + 1), "--org",
        an_org(OWNER_MAX + 1), "--local-remote-dir",
        str(tmp_path / "remotes")))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "too-long" not in result.stderr
    assert not (tmp_path / "remotes").exists()


@PTY_SKIP
@pytest.mark.parametrize("length", [ID_MAX, ID_MAX + 1])
def test_a_name_typed_at_the_prompt_is_held_to_the_topic_bound(tmp_path,
                                                               length):
    """The name typed at the prompt becomes the scaffold's `--project`, and
    its derived id the topic's: 39 characters plan, 40 are refused at the
    plan with `--id` as the way round, and nothing exists."""
    env = terminal_env()
    env.update(setup_env(tmp_path))
    status, screen, answered = run_in_a_terminal(
        [sys.executable, str(SETUP_PROJECT), *setup_flags(tmp_path)],
        cwd=REPO, env=env, answers=[a_name(length) + "\n"],
        prompt="project name (ONE CamelCase token, e.g. Atlas): ",
        timeout=120)
    assert answered == 1, f"it never asked for a project name:\n{screen}"
    assert not (tmp_path / "parent").exists()
    if length == ID_MAX:
        assert status == 0, screen
        assert "too-long" not in screen
    else:
        assert status == 2, screen
        assert TOPIC_TOO_LONG in screen
        assert "Pass an explicit --id" in screen


# --- adopt-project.py execute: before either leg exists -----------------------

def a_root_named(org: str, project: str):
    """`github_run`'s `before_plan`: the source as `org/project` on the
    stand-in for github.com, which is where an in-place adoption pushes its
    split. `github_run` places it as `testorg/Northwind` itself."""
    def place(source: Path, github: Path) -> None:
        root = github / org / f"{project}.git"
        if not root.exists():
            git("clone", "-q", "--bare", ".", str(root), cwd=source)
    return place


def assert_no_leg(github: Path, org: str, project: str) -> None:
    for leg in ("spec", "code"):
        assert not (github / org / f"{project}-{leg}.git").exists(), leg


#: `execute`'s own two remediations, word for word: neither is a leg's.
NO_REPOSITORY = "Remediation: no repository was created."
TOPIC_REMEDY = (
    f"{NO_REPOSITORY} Fix `id:` in the plan, or re-run `plan` with an "
    "explicit --id, of at most 39 characters: the id need not be the "
    "project's name lowercased, and the name, which the assembly root "
    "already has, stays as it is.")
ORG_REMEDY = (
    f"{NO_REPOSITORY} Fix `org:` in the plan, or re-run `plan` with --org, as "
    "GitHub spells the organisation, the `<org>` of "
    "`https://github.com/<org>`: GitHub gives no user or organisation a name "
    "of more than 39 characters.")


def renamed_first(repository: str) -> str:
    """`adopt-name-too-long`'s remediation where a leg GitHub will not
    create is named after the assembly root, which on GitHub is the source
    itself: GitHub's numbers, then `_rename_first`'s words, as `adopt-bad-id`
    says them. "Use a shorter --project" planned another repository."""
    return ("Remediation: nothing was created. The legs are named "
            "`<Project>-spec` and `<Project>-code`, and --project is the "
            f"source's own name: {GITHUB_LIMITS_SAID} {repository} "
            f"{RENAME_FIRST}")


#: `(plan flags, the organisation, the project, the refusal, its
#: remediation)`: one past each bound, each refused by `execute` before a
#: `gh` call or a leg. The source is named on GitHub with 96 and with 100
#: characters, both names GitHub gives a repository.
ADOPT_OVER = {
    "id": (("--id", an_id(ID_MAX + 1)), ORG, NORTHWIND,
           "REFUSED adopt-topic-too-long: ", TOPIC_REMEDY),
    "derived-id": (("--project", a_name(ID_MAX + 1)), ORG,
                   a_name(ID_MAX + 1), "REFUSED adopt-topic-too-long: ",
                   TOPIC_REMEDY),
    "project": (("--project", a_name(PROJECT_MAX + 1), "--id", "atl"), ORG,
                a_name(PROJECT_MAX + 1), "REFUSED adopt-name-too-long: ",
                renamed_first(f"{ORG}/{a_name(PROJECT_MAX + 1)}")),
    "project-100": (("--project", a_name(NAME_MAX), "--id", "atl"), ORG,
                    a_name(NAME_MAX), "REFUSED adopt-name-too-long: ",
                    renamed_first(f"{ORG}/{a_name(NAME_MAX)}")),
    "org": (("--org", an_org(OWNER_MAX + 1)), an_org(OWNER_MAX + 1),
            NORTHWIND, "REFUSED adopt-org-too-long: ", ORG_REMEDY),
}


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_github_limits",
                                                  ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("unset", [False, True], ids=["id", "no-id"])
def test_executes_topic_refusal_names_the_id_by_where_it_came_from(
        adopter, tmp_path, unset):
    """`plan` writes `id:` whether or not `--id` was passed; a plan edited
    to hold none takes `legs.assembly` lowercased, and is named so."""
    project = a_name(ID_MAX + 1)
    source = make_source_repo(tmp_path / NORTHWIND, tree=SOURCE_TREE,
                              edits=())
    path = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, path, project=project)
    assert written.returncode == 0, written.stderr + written.stdout
    if unset:
        text = path.read_bytes()
        line = f"\nid: {project.lower()}\n".encode("ascii")
        assert text.count(line) == 1
        path.write_bytes(text.replace(line, b"\n"))
    plan = adopter.Plan.load(path)
    naming = NamingPolicy.load(REPO / "contracts" / "repository-naming.yaml")
    with pytest.raises(adopter.Refusal) as caught:
        adopter._refuse_a_topic_github_cannot_set(
            plan, naming.topic_for(plan.project_id))
    named = adopter.DERIVED_ID if unset else "`id:`"
    assert caught.value.code == "adopt-topic-too-long"
    assert caught.value.detail.startswith(
        f"{path}: {named} is abbbbbbbbbbb...bbbbbbbbbbbb, 40 characters, ")
    assert caught.value.remediation == TOPIC_REMEDY


class _Plan:
    """What `_repository_urls` reads of a plan: its `org:` and its path."""
    path = Path("adoption-plan.yaml")

    @staticmethod
    def get(key, default=None):
        return {"org": ORG}.get(key, default)


def names_refused(adopter, names: dict, local_remote_dir=None):
    """`adopt-name-too-long` as `execute` refuses `names`, in process."""
    with pytest.raises(adopter.Refusal) as caught:
        adopter._repository_urls(
            SimpleNamespace(local_remote_dir=local_remote_dir), _Plan(),
            names, None)
    assert caught.value.code == "adopt-name-too-long"
    return caught.value


def names_of(project: str, **legs) -> dict:
    return {"assembly": project, "spec": legs.get("spec", f"{project}-spec"),
            "code": legs.get("code", f"{project}-code")}


def test_a_leg_named_after_the_source_is_mended_by_renaming_it(adopter):
    caught = names_refused(adopter, names_of(a_name(NAME_MAX)))
    assert caught.detail == (
        "Abbbbbbbbbbb...bbbbbbb-spec is 105 characters, and GitHub keeps a "
        "repository's name to at most 100; Abbbbbbbbbbb...bbbbbbb-code is "
        "105 characters, and GitHub keeps a repository's name to at most "
        "100.")
    assert caught.remediation == renamed_first(f"{ORG}/{a_name(NAME_MAX)}")


@pytest.mark.parametrize("legs", [
    pytest.param({"code": "Other-code"}, id="spec-after-the-root"),
    pytest.param({"spec": "Other-spec"}, id="code-after-the-root"),
])
def test_one_leg_named_after_the_source_is_enough(adopter, legs):
    """The other leg was edited to a short name of its own, and is not
    over GitHub's limit: the leg that is, is named after the source, and
    renaming the source mends it, whichever leg it is."""
    caught = names_refused(adopter, names_of(a_name(NAME_MAX), **legs))
    assert caught.remediation == renamed_first(f"{ORG}/{a_name(NAME_MAX)}")


@pytest.mark.parametrize("names", [
    pytest.param(names_of(NORTHWIND, spec=f"{a_name(PROJECT_MAX + 1)}-spec"),
                 id="named-otherwise"),
    pytest.param(names_of(NORTHWIND, spec=f"{NORTHWIND}-{'s' * NAME_MAX}"),
                 id="starting-with-the-root"),
])
def test_a_leg_the_plan_names_otherwise_keeps_its_remediation(adopter,
                                                              names):
    """A leg edited in the plan to a name of its own is not the source's
    name, though it may start with it: the remediation is the one it had."""
    caught = names_refused(adopter, names)
    assert caught.remediation.startswith(SHORTER_PROJECT)
    assert caught.remediation.endswith(GITHUB_LIMITS_SAID)


@pytest.mark.parametrize("length, remedy", [
    pytest.param(NAME_MAX + 1, SHORTER_PROJECT + GITHUB_LIMITS_SAID, id="101"),
    pytest.param(251, DISK_REMEDY, id="251"),
])
def test_a_root_github_cannot_have_is_not_the_sources_to_rename(
        adopter, length, remedy):
    """No repository on GitHub is named with more than 100 characters, so a
    root of 101 is a `--project` no source was compared with, and "Use a
    shorter --project" is the advice. At 251 the legs are 256 bytes, which a
    disk cannot hold: the disk's remediation, with no word of GitHub's."""
    caught = names_refused(adopter, names_of(a_name(length)))
    assert caught.remediation == remedy


def test_the_disk_alone_keeps_its_remediation_under_a_local_remote_dir(
        adopter, tmp_path):
    """A bare `<247>-spec.git` is 256 bytes: the disk's limit, and its
    remediation word for word, as before #838."""
    caught = names_refused(adopter, names_of(a_name(247)),
                           tmp_path / "remotes")
    assert caught.remediation == DISK_REMEDY


def test_a_leg_named_after_the_source_is_not_the_disks_trouble(adopter,
                                                               tmp_path):
    """Under `--local-remote-dir` GitHub is never asked, so a `spec` leg of
    105 characters named after a source of 100 is fine, and the `code` leg
    edited past the disk's limit is refused with the disk's remediation, as
    any name is: renaming the source on GitHub would mend nothing."""
    caught = names_refused(adopter, names_of(a_name(NAME_MAX),
                                             code=a_name(300)),
                           tmp_path / "remotes")
    assert caught.remediation == DISK_REMEDY


class _WithoutYes:
    """`subprocess` as `github_run` sees it, but `execute` is run without
    `--yes`, on the stdin `github_run` gives it, which is not a terminal:
    `_confirm` then refuses `adopt-unconfirmed`, as nobody can be asked."""

    def __getattr__(self, name):
        return getattr(subprocess, name)

    @staticmethod
    def run(argv, *args, **kwargs):
        return subprocess.run([arg for arg in argv if arg != "--yes"], *args,
                              **kwargs)


def refusals(stderr: str) -> list:
    """The code of each `REFUSED` line, in order."""
    return [line.split(":", 1)[0] for line in stderr.splitlines()
            if line.startswith("REFUSED ")]


@WINDOWS_SKIP
@needs_filter_repo
@pytest.mark.parametrize("case, confirmed", [
    *(pytest.param(case, True, id=case) for case in ADOPT_OVER),
    pytest.param("id", False, id="id-unconfirmed"),
    pytest.param("org", False, id="org-unconfirmed"),
])
def test_execute_refuses_what_github_will_not_take_before_a_leg(
        tmp_path, monkeypatch, case, confirmed):
    """On main an id over 39 characters adopted, pushed both legs and the
    split, and ended at the topic, exit 2 (`The split IS pushed`); a leg
    name over 100 or an organisation over 39 ended at the first `gh repo
    create`. Unconfirmed, without `--yes` where nobody can be asked, the
    refusal is still GitHub's limit: it comes before `_confirm`."""
    flags, org, project, refused, made = ADOPT_OVER[case]
    if not confirmed:
        monkeypatch.setattr(test_adopt_github_exits, "subprocess",
                            _WithoutYes())
    result, github = github_run(tmp_path, "", plan_flags=flags,
                                before_plan=a_root_named(org, project))
    assert result.returncode == 2, result.stderr + result.stdout
    assert refusals(result.stderr) == [refused.rstrip(": ")], result.stderr
    assert gh_calls(github) == []
    assert_no_leg(github, org, project)
    assert SPLIT_BRANCH not in heads(github / org / f"{project}.git")
    assert f"\n{made}\n" in result.stderr, result.stderr


@WINDOWS_SKIP
@needs_filter_repo
def test_without_yes_a_plan_github_takes_is_unconfirmed(tmp_path,
                                                        monkeypatch):
    """The control: the run `_WithoutYes` makes reaches `_confirm`, which
    refuses, so a refusal above came before it."""
    monkeypatch.setattr(test_adopt_github_exits, "subprocess", _WithoutYes())
    result, github = github_run(tmp_path, "")
    assert result.returncode == 2, result.stderr + result.stdout
    assert refusals(result.stderr) == ["REFUSED adopt-unconfirmed"]
    assert gh_calls(github) == []
    assert_no_leg(github, ORG, NORTHWIND)


#: `(plan flags, the organisation, the project)`: at each bound, adopted to
#: the end, the topic set on all three.
ADOPT_AT = {
    "id": (("--id", an_id(ID_MAX)), ORG, NORTHWIND),
    "long-name-short-id": (("--project", a_name(PROJECT_MAX), "--id", "atl"),
                           ORG, a_name(PROJECT_MAX)),
    "org": (("--org", an_org(OWNER_MAX)), an_org(OWNER_MAX), NORTHWIND),
}


@WINDOWS_SKIP
@needs_filter_repo
@pytest.mark.parametrize("case", ADOPT_AT)
def test_execute_adopts_at_githubs_bounds(tmp_path, case):
    flags, org, project = ADOPT_AT[case]
    result, github = github_run(tmp_path, "", plan_flags=flags,
                                before_plan=a_root_named(org, project))
    assert result.returncode == 0, result.stderr + result.stdout
    assert [c for c in gh_calls(github) if c.startswith("repo edit")] == [
        f"repo edit {org}/{project}{tail}" for tail in ("", "-spec", "-code")]
    for leg in ("spec", "code"):
        assert heads(github / org / f"{project}-{leg}.git") == ["main"]


#: A name this long, three times over, under pytest's temporary root is a
#: path past Windows' 260 characters.
LONG_PATHS_SKIP = pytest.mark.skipif(
    os.name == "nt", reason="the leg's work tree is a path Windows will not "
                            "open without long paths turned on")


@LONG_PATHS_SKIP
@needs_filter_repo
def test_execute_asks_none_of_them_under_a_local_remote_dir(tmp_path):
    """A name, an organisation and an id GitHub would refuse adopt into
    bare repositories on disk, where GitHub is never asked."""
    project = a_name(PROJECT_MAX + 1)
    source = make_source_repo(tmp_path / NORTHWIND, tree=SOURCE_TREE,
                              edits=())
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=project,
                         org=an_org(OWNER_MAX + 1))
    assert written.returncode == 0, written.stderr + written.stdout
    remotes = tmp_path / "remotes"
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(remotes), "--work-dir",
                        str(tmp_path / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "too-long" not in result.stderr
    for leg in ("spec", "code"):
        assert (remotes / f"{project}-{leg}.git").is_dir(), leg
