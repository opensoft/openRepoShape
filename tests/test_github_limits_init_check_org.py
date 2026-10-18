# SPDX-License-Identifier: Apache-2.0
"""`family.py init`, `adopt-project.py check` and every tool's `--org`: what
GitHub will not take is refused before anything exists (#863).

#838 (PR #859) gave `scaffold-project.py`, `adopt-project.py execute` and,
through the scaffold's dry run, `setup-project.py` GitHub's three limits: 100
characters for a repository's name, 50 for a topic and 39 for a user's or an
organisation's name. It left out three places, which #863 names:

* `family.py init` set the holder's topic, `xf-project-<family id>`, LAST,
  with `gh repo edit --add-topic` after `gh repo create` and the push, and
  asked neither the 50, nor the 39 of `--org`, nor the 100 of the holder's
  name. A family of 40 characters made and pushed its holder and then met
  GitHub's refusal: exit 2, no NEXT STEPS, and a re-run refused as
  `family-remote-exists`.
* `adopt-project.py check` asked none of the limits `execute` asks, the
  disk's 255 bytes included, so it said `plan ok` over a plan `execute` then
  refused as `adopt-name-too-long`, `adopt-org-too-long` or
  `adopt-topic-too-long`.
* An `--org` holding a character GitHub gives no organisation (`.`), ending
  in a hyphen or holding two in a row passed every plan and went on to `gh
  repo create`.

Now `init` refuses `family-name-too-long`, `family-org-too-long`,
`family-bad-org` and `family-topic-too-long` where GitHub is asked, before
`_creator_name` and before any `gh` call, under `--dry-run` alike. `check`
finds what `execute` refuses, from the one list both read
(`_what_cannot_be_held`), under the same code. The scaffold, `check`,
`execute` and `init` refuse such an `--org` as `scaffold-bad-org`,
`adopt-bad-org` and `family-bad-org`, and `setup-project.py` at its step (5),
the scaffold's plan. `_` is let by: a GitHub Enterprise Managed User's login
holds one, and refusing it waits on a probe against a real account. None of
GitHub's limits is asked under `--local-remote-dir`, where nothing goes to
GitHub.

THE NUMBERS AND THE CHARACTERS ARE GITHUB'S DOCUMENTATION, NOT MEASURED: no
run here creates a real repository. The fake `gh` below refuses as that
documentation says (a topic over 50, an owner over 39 or holding another
character, a repository name over 100) and answers `repo view` as not found;
the runs that refuse assert that it was never called. The in-process runs
refuse every process start but the one they allow, so a refusal that passes
came before it. The end-to-end runs are POSIX only: their `gh` is a `#!`
script.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import test_adopt_github_exits
from conftest import ADOPT, ORG, REPO, WINDOWS_SKIP, resolve, run_script
from conftest import make_source_repo, write_plan
from test_adopt_github_exits import (NORTHWIND, gh_calls, github_run,
                                     needs_filter_repo)
from test_adopt_manifest_values import ANSWERS
from test_github_name_limits import (  # noqa: F401 (`scaffold`: a fixture)
    a_name, a_root_named, an_id, an_org, goes_on, help_entry, refusals,
    refused_plan, run_entry, scaffold, setup_env, setup_flags)
from test_scaffold_leg_path_collisions import (  # noqa: F401 (a fixture)
    ProcessStarted, no_process,
)

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402
from repo_shape import NamingPolicy, Refusal  # noqa: E402

FAMILY = REPO / "scripts" / "family.py"

#: GitHub's numbers, written out as #859's tests write them.
NAME_MAX, TOPIC_MAX, OWNER_MAX = 100, 50, 39
ID_MAX = TOPIC_MAX - len("xf-project-")

#: What each refusal is called.
FAMILY_NAME_TOO_LONG = "REFUSED family-name-too-long"
FAMILY_TOPIC_TOO_LONG = "REFUSED family-topic-too-long"
FAMILY_ORG_TOO_LONG = "REFUSED family-org-too-long"
FAMILY_BAD_ORG = "REFUSED family-bad-org"
SCAFFOLD_BAD_ORG = "REFUSED scaffold-bad-org"

#: An `--org` GitHub gives no organisation, by its characters, each with what
#: the refusal says of it. A leading hyphen is not here: `checked_value`
#: refuses it first, as `unsafe-value`.
MISSPELLED = {
    "dot": ("my.org", "holding `.`"),
    "underscore-and-dot": ("my_org.x", "holding `.`"),
    "trailing-hyphen": ("trail-", "ending in a hyphen"),
    "two-hyphens": ("a--b", "with two hyphens in a row"),
}
#: The controls: an organisation GitHub spells, and one with `_`, which is
#: let by until a real account says otherwise.
SPELLED = {"hyphen": "ok-org", "underscore": "ok_org"}


def misspelled(owner: str, named: str = "--org") -> str:
    """What a refusal of `owner`'s characters says, after the code."""
    return (f"{named} is {owner!r}, and GitHub gives no user or organisation "
            f"a name {dict(MISSPELLED.values())[owner]}, so no repository can "
            "be created under it")


# --- the one helper the tools ask -------------------------------------------

@pytest.mark.parametrize("owner", [*SPELLED.values(), "a", "A0-b1-C2",
                                   an_org(OWNER_MAX)])
def test_an_owner_github_spells_is_not_refused(owner):
    assert shape_materialize.refuse_an_owner_github_cannot_spell(
        "r", owner, "--org", "Remedy.") is None


@pytest.mark.parametrize("case", MISSPELLED)
def test_an_owner_github_does_not_spell_is_refused_by_name(case):
    owner, _ = MISSPELLED[case]
    with pytest.raises(Refusal) as caught:
        shape_materialize.refuse_an_owner_github_cannot_spell(
            "r", owner, "--org", "Remedy.")
    assert (caught.value.code, caught.value.detail,
            caught.value.remediation) == ("r", misspelled(owner), "Remedy.")


def test_every_character_and_every_hyphen_rule_broken_is_named_once():
    with pytest.raises(Refusal) as caught:
        shape_materialize.refuse_an_owner_github_cannot_spell(
            "r", "a.b@c+d~e/f.g--h-", "`org:`", "Remedy.")
    assert caught.value.detail == (
        "`org:` is 'a.b@c+d~e/f.g--h-', and GitHub gives no user or "
        "organisation a name holding `.`, `@`, `+`, `~` or `/`, or ending in "
        "a hyphen, or with two hyphens in a row, so no repository can be "
        "created under it")


# --- family.py init, in process: before `_creator_name` and any `gh` --------

@pytest.fixture(scope="module")
def family():
    spec = importlib.util.spec_from_file_location("family_github_limits",
                                                  FAMILY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def only_the_branch_question(monkeypatch):
    """Every process `init` starts goes through `subprocess.Popen`. While
    this holds, only `git check-ref-format` may start, the question
    `refuse_bad_branch` asks of `--tracking-branch` before any name is
    judged; any other process fails the test and names the command. With no
    `--created-by` and no GIT_AUTHOR_NAME, `_creator_name` starts `git
    config user.name`, so a run that passes the limits fails there."""
    real = subprocess.Popen

    def guarded(args, *rest, **kwargs):
        if "check-ref-format" in [str(arg) for arg in args]:
            return real(args, *rest, **kwargs)
        raise ProcessStarted(f"a process was started: {args!r}")

    monkeypatch.delenv("GIT_AUTHOR_NAME", raising=False)
    monkeypatch.setattr(subprocess, "Popen", guarded)


def init_args(tmp_path: Path, *flags: str, dry_run: bool = True) -> list:
    """`init` of `Orbit` in `testorg`, then `flags`, which win: argparse
    keeps the last of a flag given twice."""
    return ["init", "--org", ORG, "--family", "Orbit", "--work-dir",
            str(tmp_path / "work"), *flags,
            *(["--dry-run"] if dry_run else [])]


def refused_init(family, capsys, tmp_path: Path, *flags: str,
                 dry_run: bool = True) -> str:
    """`init` refuses with `flags` and prints no plan. Returns stderr."""
    code = family.main(init_args(tmp_path, *flags, dry_run=dry_run))
    out, err = capsys.readouterr()
    assert (code, out) == (2, ""), out + err
    assert not (tmp_path / "work").exists()
    return err


def init_goes_on(family, capsys, tmp_path: Path, *flags: str) -> None:
    """`init` with `flags` passes every question GitHub's limits ask and
    goes on to `_creator_name`, whose `git config user.name` is refused."""
    with pytest.raises(ProcessStarted, match="user.name"):
        family.main(init_args(tmp_path, *flags))
    err = capsys.readouterr().err
    assert "too-long" not in err and "bad-org" not in err, err


#: `(flags at the bound, flags one past it, the refusal)`.
INIT_EDGES = {
    "derived-id": (("--family", a_name(ID_MAX)),
                   ("--family", a_name(ID_MAX + 1)), FAMILY_TOPIC_TOO_LONG),
    "id": (("--id", an_id(ID_MAX)), ("--id", an_id(ID_MAX + 1)),
           FAMILY_TOPIC_TOO_LONG),
    "name": (("--family", a_name(NAME_MAX), "--id", "orbit"),
             ("--family", a_name(NAME_MAX + 1), "--id", "orbit"),
             FAMILY_NAME_TOO_LONG),
    "org": (("--org", an_org(OWNER_MAX)), ("--org", an_org(OWNER_MAX + 1)),
            FAMILY_ORG_TOO_LONG),
}


@pytest.mark.parametrize("edge", INIT_EDGES)
def test_init_at_githubs_bound_goes_on(family, only_the_branch_question,
                                       capsys, tmp_path, edge):
    init_goes_on(family, capsys, tmp_path, *INIT_EDGES[edge][0])


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real"])
@pytest.mark.parametrize("edge", INIT_EDGES)
def test_init_one_past_githubs_bound_is_refused_before_any_process(
        family, only_the_branch_question, capsys, tmp_path, edge, dry_run):
    _, over, code = INIT_EDGES[edge]
    err = refused_init(family, capsys, tmp_path, *over, dry_run=dry_run)
    assert err.startswith(f"{code}: "), err
    assert "\nRemediation: nothing was created, and `--dry-run` refuses the " \
           "same. " in err, err


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real"])
@pytest.mark.parametrize("case", MISSPELLED)
def test_init_refuses_an_org_github_does_not_spell(
        family, only_the_branch_question, capsys, tmp_path, case, dry_run):
    owner, _ = MISSPELLED[case]
    err = refused_init(family, capsys, tmp_path, "--org", owner,
                       dry_run=dry_run)
    assert err == (
        f"{FAMILY_BAD_ORG}: {misspelled(owner)}\nRemediation: nothing was "
        "created, and `--dry-run` refuses the same. Pass --org as GitHub "
        "spells the organisation, the `<org>` of "
        "`https://github.com/<org>`.\n")


@pytest.mark.parametrize("case", SPELLED)
def test_init_takes_an_org_github_spells(family, only_the_branch_question,
                                         capsys, tmp_path, case):
    init_goes_on(family, capsys, tmp_path, "--org", SPELLED[case])


#: How each of `init`'s own GitHub refusals begins its way out.
INIT_NOTHING_MADE = ("Remediation: nothing was created, and `--dry-run` "
                     "refuses the same.")


def test_init_names_a_derived_id_as_derived_and_mends_it_with_an_id(
        family, only_the_branch_question, capsys, tmp_path):
    err = refused_init(family, capsys, tmp_path, "--family",
                       a_name(ID_MAX + 1))
    assert err == (
        f"{FAMILY_TOPIC_TOO_LONG}: --id (not given, so --family lowercased) "
        "is abbbbbbbbbbb...bbbbbbbbbbbb, 40 characters, so the topic this run "
        "sets on each repository, `xf-project-<id>`, is 51, and GitHub keeps "
        "a topic to at most 50: an id is at most 39 characters\n"
        f"{INIT_NOTHING_MADE} Pass an explicit --id of at most 39 characters: "
        "the id need not be --family lowercased, and --family, which names "
        "the holder, its repository and, unless --work-dir is given, its "
        "family folder, stays as it is.\n")


def test_init_names_an_empty_id_as_empty(family, only_the_branch_question,
                                         capsys, tmp_path):
    err = refused_init(family, capsys, tmp_path, "--family",
                       a_name(ID_MAX + 1), "--id", "")
    assert err.startswith(f"{FAMILY_TOPIC_TOO_LONG}: --id (empty, so --family "
                          "lowercased) is "), err


def test_init_names_a_passed_id_as_passed(family, only_the_branch_question,
                                          capsys, tmp_path):
    err = refused_init(family, capsys, tmp_path, "--id", an_id(ID_MAX + 1))
    assert err.startswith(f"{FAMILY_TOPIC_TOO_LONG}: --id is aaaa"), err
    assert err.endswith(f"\n{INIT_NOTHING_MADE} Pass a shorter --id, of at "
                        "most 39 characters.\n"), err


def test_init_mends_a_long_org_as_github_spells_it(
        family, only_the_branch_question, capsys, tmp_path):
    err = refused_init(family, capsys, tmp_path, *INIT_EDGES["org"][1])
    assert err == (
        f"{FAMILY_ORG_TOO_LONG}: --org is oooooooooooo...oooooooooooo, 40 "
        "characters, and GitHub keeps a user's or an organisation's name to "
        "at most 39, so no repository can be created under it\n"
        f"{INIT_NOTHING_MADE} Pass --org as GitHub spells the organisation, "
        "the `<org>` of `https://github.com/<org>`: GitHub gives no user or "
        "organisation a name of more than 39 characters.\n")


def test_init_names_a_long_family_and_both_numbers(
        family, only_the_branch_question, capsys, tmp_path):
    """The id is `--family` lowercased unless `--id` is given, so a shorter
    name is told the id's bound too, as #859's GitHub remediation says it."""
    err = refused_init(family, capsys, tmp_path, *INIT_EDGES["name"][1])
    assert err == (
        f"{FAMILY_NAME_TOO_LONG}: --family is Abbbbbbbbbbb...bbbbbbbbbbbb, "
        "101 characters, and GitHub keeps a repository's name, the holder's "
        "`<org>/<Family>`, to at most 100\n"
        f"{INIT_NOTHING_MADE} Choose a shorter --family, of at most 100 "
        "characters, GitHub's limit on a repository's name: it names the "
        "holder, its repository and, unless --work-dir is given, its family "
        "folder. Its id, --family lowercased unless --id is given, is at most "
        "39, as GitHub keeps the topic `xf-project-<id>` to 50.\n")


def test_init_keeps_a_long_family_with_a_short_id(
        family, only_the_branch_question, capsys, tmp_path):
    """A family of 40 to 100 characters keeps its name: a shorter `--id` is
    the way round the topic's bound."""
    for length in (ID_MAX + 1, 70, NAME_MAX):
        init_goes_on(family, capsys, tmp_path, "--family", a_name(length),
                     "--id", "orb")


@pytest.mark.parametrize("org", [an_org(OWNER_MAX + 1), "my.org", "trail-"])
def test_init_asks_none_of_them_of_a_local_run(
        family, only_the_branch_question, capsys, tmp_path, org):
    """Under `--local-remote-dir` nothing goes to GitHub: no topic is set,
    the organisation names no account, and the holder's name is the disk's.
    A family of 101 characters, whose derived id is 101 too, goes on."""
    init_goes_on(family, capsys, tmp_path, "--family", a_name(NAME_MAX + 1),
                 "--org", org, "--local-remote-dir", str(tmp_path / "remotes"))
    assert not (tmp_path / "remotes").exists()


#: What `init --help` says of each bound, by the flag, in the scaffold's
#: words for its own (#838).
INIT_SAID = {
    "--org ORG": (
        f"at most {OWNER_MAX} characters without --local-remote-dir, GitHub's "
        "limit on an organisation's name"),
    "--family FAMILY": (
        f"at most {NAME_MAX} characters without --local-remote-dir, GitHub's "
        "limit on a repository's name"),
    "--id ID": (
        f"at most {ID_MAX} characters without --local-remote-dir, as GitHub "
        f"keeps the topic `xf-project-<id>` to {TOPIC_MAX}"),
}


def test_init_help_says_each_bound_where_the_value_is_typed():
    result = run_script(FAMILY, "init", "--help")
    assert result.returncode == 0, result.stderr
    for flag, sentence in INIT_SAID.items():
        entry = help_entry(result.stdout, flag)
        assert sentence in entry, (flag, entry)


# --- family.py init end to end: GitHub's refusal, by its documentation ------

#: A `gh` with no network that answers as GitHub's documentation says: a
#: repository it has not got is not found; `repo create` refuses an owner
#: over 39 characters or holding a character GitHub gives no account (`_`
#: aside, as the tools let it by), and a name over 100; `repo edit
#: --add-topic` refuses a topic over 50. Every call is logged.
FAKE_GH = b"""#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_GH_LOG"
case "$1 $2" in
  "repo view")
    said="GraphQL: Could not resolve to a Repository"
    echo "$said with the name '$3'. (repository)" >&2
    exit 1 ;;
  "repo create")
    owner=${3%%/*}; name=${3#*/}
    case "$owner" in
      *[!A-Za-z0-9_-]*|*-|*--*)
        echo "HTTP 422: owner is not a GitHub account name" >&2; exit 1 ;;
    esac
    if [ "${#owner}" -gt 39 ] || [ "${#name}" -gt 100 ]; then
      echo "HTTP 422: name is too long (maximum is 100 characters)" >&2
      exit 1
    fi
    exit 0 ;;
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


def init_on_github(tmp_path: Path, *flags: str, dry_run: bool = False):
    """A real `init` of `Orbit` against `FAKE_GH`, pushing nothing. Public,
    so no `gh` call asks the organisation's plan."""
    env, log = fake_github(tmp_path)
    result = run_script(FAMILY, "init", "--org", ORG, "--family", "Orbit",
                        "--created-by", "Test Human", "--visibility",
                        "public", "--no-push", "--work-dir",
                        str(tmp_path / "work"), *flags,
                        *(["--dry-run"] if dry_run else []), env=env)
    return result, log


#: `(flags, the refusal)`: one past each bound, and a character.
INIT_ON_GITHUB = {
    "derived-id": (("--family", a_name(ID_MAX + 1)), FAMILY_TOPIC_TOO_LONG),
    "name": (("--family", a_name(NAME_MAX + 1), "--id", "orbit"),
             FAMILY_NAME_TOO_LONG),
    "org": (("--org", an_org(OWNER_MAX + 1)), FAMILY_ORG_TOO_LONG),
    "org-dot": (("--org", "my_org.x"), FAMILY_BAD_ORG),
}


@WINDOWS_SKIP
@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real"])
@pytest.mark.parametrize("case", INIT_ON_GITHUB)
def test_init_refuses_before_gh_is_asked_anything(tmp_path, case, dry_run):
    """On main a family of 40 characters created and seeded its holder,
    then GitHub refused `--add-topic`: exit 2 with the holder made and no
    NEXT STEPS. A long `--org` or family name, or `my_org.x`, reached `gh
    repo create`, and each dry run exited 0. Now nothing reaches `gh`."""
    flags, refused = INIT_ON_GITHUB[case]
    result, log = init_on_github(tmp_path, *flags, dry_run=dry_run)
    assert result.returncode == 2, result.stderr + result.stdout
    assert result.stderr.startswith(f"{refused}: "), result.stderr
    assert result.stdout == ""
    assert not log.exists(), log.read_text(encoding="utf-8")
    assert not (tmp_path / "work").exists()


@WINDOWS_SKIP
def test_init_sets_a_topic_at_githubs_bound(tmp_path):
    name = a_name(ID_MAX)
    result, log = init_on_github(tmp_path, "--family", name)
    assert result.returncode == 0, result.stderr + result.stdout
    calls = log.read_text(encoding="utf-8").splitlines()
    assert f"repo edit {ORG}/{name} --add-topic xf-project-{name.lower()}" in \
        calls, calls
    assert "NEXT STEPS" in result.stdout


# --- scaffold-project.py and setup-project.py: the characters ---------------

@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real"])
@pytest.mark.parametrize("case", MISSPELLED)
def test_the_scaffold_refuses_an_org_github_does_not_spell(
        scaffold, no_process, capsys, case, dry_run):
    owner, _ = MISSPELLED[case]
    err = refused_plan(scaffold, capsys, "--project", "Atlas", "--org", owner,
                       dry_run=dry_run)
    assert err == (
        f"{SCAFFOLD_BAD_ORG}: {misspelled(owner)}\nRemediation: nothing was "
        "created, and `--dry-run` refuses the same. Pass --org as GitHub "
        "spells the organisation, the `<org>` of "
        "`https://github.com/<org>`.\n")


@pytest.mark.parametrize("case", SPELLED)
def test_the_scaffold_takes_an_org_github_spells(scaffold, no_process, capsys,
                                                  case):
    goes_on(scaffold, capsys, "--project", "Atlas", "--org", SPELLED[case])


def test_the_scaffold_asks_no_characters_of_a_local_run(scaffold, no_process,
                                                        capsys, tmp_path):
    goes_on(scaffold, capsys, "--project", "Atlas", "--org", "my_org.x",
            "--local-remote-dir", str(tmp_path / "remotes"))
    assert not (tmp_path / "remotes").exists()


#: `(the organisation, the refusal or None)`: setup's step (5) is the
#: scaffold's plan, which refuses it there.
SETUP_ORGS = {
    "dot": ("my.org", SCAFFOLD_BAD_ORG),
    "trailing-hyphen": ("trail-", SCAFFOLD_BAD_ORG),
    "underscore": ("ok_org", None),
}


@WINDOWS_SKIP
@pytest.mark.parametrize("case", SETUP_ORGS)
def test_setup_refuses_at_the_plan_an_org_github_does_not_spell(tmp_path,
                                                                case):
    org, refused = SETUP_ORGS[case]
    result = run_entry(*setup_flags(tmp_path, "--project", "Atlas", "--org",
                                    org), extra_env=setup_env(tmp_path))
    assert not (tmp_path / "parent").exists()
    if refused is None:
        assert result.returncode == 0, result.stderr + result.stdout
        assert "bad-org" not in result.stderr
        return
    assert result.returncode == 2, result.stderr + result.stdout
    assert f"{refused}: --org is {org!r}" in result.stderr, result.stderr
    assert "REFUSED: the plan could not be produced (see above)." in \
        result.stderr


# --- adopt-project.py: `check` and `execute` read one list ------------------

@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_github_limits_863",
                                                  ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Plan:
    """What the list reads of a plan: its path, its keys and its id."""
    path = Path("adoption-plan.yaml")

    def __init__(self, org: str = ORG, project_id: str = "northwind"):
        self.data = {"org": org, "id": project_id}

    def get(self, key, default=None):
        return self.data.get(key, default)

    @property
    def project_id(self) -> str:
        return self.data["id"]


def names_of(project: str) -> dict:
    return {"assembly": project, "spec": f"{project}-spec",
            "code": f"{project}-code"}


def test_check_and_execute_read_one_list(adopter, monkeypatch):
    """`execute` refuses the first refusal `_what_cannot_be_held` gives and
    `check` finds each one: a list of `check`'s own would be a second list
    to forget a question in."""
    first = Refusal("first-code", "the first detail", "Remediation: one.")
    second = Refusal("second-code", "the second detail", "Remediation: two.")
    asked = []

    def stand_in(*args):
        asked.append(args)
        yield first
        yield second

    monkeypatch.setattr(adopter, "_what_cannot_be_held", stand_in)
    with pytest.raises(Refusal) as caught:
        adopter._repository_urls(SimpleNamespace(local_remote_dir=None),
                                 _Plan(), names_of(NORTHWIND), None)
    assert caught.value is first
    naming = NamingPolicy.load(REPO / "contracts" / "repository-naming.yaml")
    assert adopter._held_findings(_Plan(), names_of(NORTHWIND), None,
                                  naming) == (
        ["FINDING first-code: the first detail",
         "FINDING second-code: the second detail"],
        ["Remediation: one.", "Remediation: two."])
    assert len(asked) == 2


def test_the_list_holds_each_refusal_in_executes_order(adopter):
    """A name, the organisation and the id, all three over: `check` finds
    the three, in the order `execute` asks them, and `execute` refuses the
    first, the name."""
    naming = NamingPolicy.load(REPO / "contracts" / "repository-naming.yaml")
    plan = _Plan(org=an_org(OWNER_MAX + 1), project_id=an_id(ID_MAX + 1))
    refused = list(adopter._what_cannot_be_held(
        plan, names_of(a_name(NAME_MAX - 4)), plan.data["org"], False,
        naming))
    assert [exc.code for exc in refused] == [
        "adopt-name-too-long", "adopt-org-too-long", "adopt-topic-too-long"]
    plan = _Plan(org="my.org")
    assert [exc.code for exc in adopter._what_cannot_be_held(
        plan, names_of(NORTHWIND), "my.org", False, naming)] == [
            "adopt-bad-org"]
    assert list(adopter._what_cannot_be_held(
        plan, names_of(NORTHWIND), "my.org", True, naming)) == []


def test_a_bad_id_is_left_to_its_own_refusal(adopter):
    """An id that is no project id is `plan-bad-id`, refused where it always
    was: the list asks no topic of it, and is no second place to say it."""
    class BadId(_Plan):
        @property
        def project_id(self) -> str:
            raise Refusal("plan-bad-id", "no", "Remediation: no.")

    naming = NamingPolicy.load(REPO / "contracts" / "repository-naming.yaml")
    assert list(adopter._what_cannot_be_held(
        BadId(), names_of(NORTHWIND), ORG, False, naming)) == []


class _CheckThenExecute:
    """`subprocess` as `github_run` sees it, but before its `execute`,
    `check` is run on the same plan, in the same environment, without
    `--yes`: its result and the `gh` calls it made are kept, and the calls
    are cleared before `execute` runs. With `only_check`, `execute` is not
    run at all, and `github_run` returns `check`'s result."""

    def __init__(self, only_check: bool = False):
        self.only_check = only_check
        self.checked = None
        self.check_calls = None

    def __getattr__(self, name):
        return getattr(subprocess, name)

    def run(self, argv, *args, **kwargs):
        if "execute" not in argv:
            return subprocess.run(argv, *args, **kwargs)
        check = ["check" if arg == "execute" else arg for arg in argv
                 if arg != "--yes"]
        self.checked = subprocess.run(check, *args, **kwargs)
        calls = Path(kwargs["env"]["FAKE_GH_ROOT"]) / "calls"
        self.check_calls = gh_calls(calls.parent)
        if self.only_check:
            return self.checked
        if calls.exists():
            calls.write_text("", encoding="utf-8")
        return subprocess.run(argv, *args, **kwargs)


def findings(stderr: str) -> list:
    """The code of each `FINDING` line, in order."""
    return [line.split(":", 1)[0] for line in stderr.splitlines()
            if line.startswith("FINDING ")]


#: `(plan flags, the organisation, the project, the code)`: one past each
#: bound, and each character, in GitHub mode. The source is named on GitHub
#: with 96 characters, a name GitHub gives a repository, whose legs it does
#: not.
CHECKED_OVER = {
    "project": (("--project", a_name(NAME_MAX - 4), "--id", "atl"), ORG,
                a_name(NAME_MAX - 4), "adopt-name-too-long"),
    "org": (("--org", an_org(OWNER_MAX + 1)), an_org(OWNER_MAX + 1),
            NORTHWIND, "adopt-org-too-long"),
    "id": (("--id", an_id(ID_MAX + 1)), ORG, NORTHWIND,
           "adopt-topic-too-long"),
    "derived-id": (("--project", a_name(ID_MAX + 1)), ORG, a_name(ID_MAX + 1),
                   "adopt-topic-too-long"),
    **{f"org-{case}": (("--org", owner), owner, NORTHWIND, "adopt-bad-org")
       for case, (owner, _) in MISSPELLED.items()},
}


@WINDOWS_SKIP
@needs_filter_repo
@pytest.mark.parametrize("case", CHECKED_OVER)
def test_check_finds_what_execute_refuses_under_its_code(tmp_path,
                                                          monkeypatch, case):
    """On main `check` said `plan ok` over each of these and `execute`
    refused it. Now `check` finds it, exit 1, under `execute`'s code, and
    asks GitHub nothing: the leg question comes after, and `execute` never
    gets that far. `execute` refuses it before a `gh` call or a leg."""
    flags, org, project, code = CHECKED_OVER[case]
    runs = _CheckThenExecute()
    monkeypatch.setattr(test_adopt_github_exits, "subprocess", runs)
    result, github = github_run(tmp_path, "", plan_flags=flags,
                                before_plan=a_root_named(org, project))
    checked = runs.checked
    assert checked.returncode == 1, checked.stderr + checked.stdout
    assert findings(checked.stderr) == [f"FINDING {code}"], checked.stderr
    assert "\nplan ok" not in checked.stdout
    assert runs.check_calls == []
    assert result.returncode == 2, result.stderr + result.stdout
    assert refusals(result.stderr) == [f"REFUSED {code}"], result.stderr
    assert gh_calls(github) == []
    for leg in ("spec", "code"):
        assert not (github / org / f"{project}-{leg}.git").exists(), leg
    # The detail and the remediation are `execute`'s own, word for word.
    finding = next(line for line in checked.stderr.splitlines()
                   if line.startswith(f"FINDING {code}: "))
    detail = finding.split(": ", 1)[1]
    assert f"REFUSED {code}: {detail}\n" in result.stderr, result.stderr
    remediation = result.stderr.split(f"REFUSED {code}: {detail}\n", 1)[1]
    assert remediation.splitlines()[0] in checked.stderr.splitlines()


#: `(plan flags, the organisation, the project)`: at each bound, and `_`.
CHECKED_AT = {
    "project": (("--project", a_name(NAME_MAX - 5), "--id", "atl"), ORG,
                a_name(NAME_MAX - 5)),
    "org": (("--org", an_org(OWNER_MAX)), an_org(OWNER_MAX), NORTHWIND),
    "id": (("--id", an_id(ID_MAX)), ORG, NORTHWIND),
    "org-underscore": (("--org", "ok_org"), "ok_org", NORTHWIND),
}


@WINDOWS_SKIP
@pytest.mark.parametrize("case", CHECKED_AT)
def test_check_passes_what_github_takes_and_asks_the_legs(tmp_path,
                                                           monkeypatch, case):
    """At each bound `check` finds nothing of GitHub's limits and goes on
    to #798's question, the two leg views."""
    flags, org, project = CHECKED_AT[case]
    runs = _CheckThenExecute(only_check=True)
    monkeypatch.setattr(test_adopt_github_exits, "subprocess", runs)
    result, _ = github_run(tmp_path, "", plan_flags=flags,
                           before_plan=a_root_named(org, project))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "\nplan ok" in result.stdout
    assert runs.check_calls == [f"repo view {org}/{project}-{leg}"
                                for leg in ("spec", "code")]


# --- adopt-project.py check under --local-remote-dir: the disk's ------------

def checked_on_disk(tmp_path: Path, length: int, *flags: str):
    """`check` of a planned and answered `N` * `length` project, with
    `flags`."""
    source = make_source_repo(tmp_path / "Thing")
    plan = tmp_path / "plan.yaml"
    written = write_plan(source, plan, project="N" * length)
    assert written.returncode == 0, written.stderr + written.stdout
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    return run_script(ADOPT, "check", "--plan", str(plan), *flags)


@pytest.mark.parametrize("length", [246, 247])
def test_check_asks_the_disks_limit_under_a_local_remote_dir(tmp_path,
                                                             length):
    """`<246>-spec.git` is 255 bytes, the most a disk keeps: `check` says
    `plan ok`. One more is `execute`'s `adopt-name-too-long`, the disk's
    words, and now `check`'s finding too."""
    result = checked_on_disk(tmp_path, length, "--local-remote-dir",
                             str(tmp_path / "remotes"), "--work-dir",
                             str(tmp_path / "work"))
    if length == 246:
        assert result.returncode == 0, result.stderr + result.stdout
        assert "too-long" not in result.stderr
        return
    assert result.returncode == 1, result.stderr + result.stdout
    assert findings(result.stderr) == ["FINDING adopt-name-too-long"]
    assert ("FINDING adopt-name-too-long: NNNNNNNNNNNN...NNNNNNN-spec.git "
            "is 256 bytes long, and the bare repository's directory under "
            "--local-remote-dir may be at most 255; NNNNNNNNNNNN...NNNNNNN"
            "-code.git is 256 bytes long, and the bare repository's directory "
            "under --local-remote-dir may be at most 255.") in \
        result.stderr.splitlines()
    assert not (tmp_path / "remotes").exists()
