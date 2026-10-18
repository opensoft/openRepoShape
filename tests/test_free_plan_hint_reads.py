# SPDX-License-Identifier: Apache-2.0
"""The Free-plan secrets hint's two reads, in all three creating tools
(#660).

The hint (`FREE_PLAN_HINT`) holds when the repository whose `validate`
workflow reads `SHAPE_LEGS_APP_ID` and `SHAPE_LEGS_APP_PRIVATE_KEY` -- the
assembly root, or the family holder -- is private or internal AND its
organisation is on the GitHub Free plan, where an organisation secret is
delivered only to a public repository. Two questions for GitHub, then, and
since #602 adopt and the scaffold ask the first of the root.

WHAT WAS WRONG.
- `family.py init --reuse-empty-repo` went by `--visibility`, whose default is
  `private`, and never asked the reused holder its own (L2-58): a PUBLIC
  holder was told it "is private" and given the hint.
- The scaffold's reused root took the run's `--visibility` where GitHub did
  not say what it is (L2-57), so a public root whose read failed was given
  the hint as private.
- `free_plan_secret_hint` answers None alike for a paid plan and for one it
  could not read (L2-59), so a private root whose plan the token could not
  see was told nothing: the silent failure the hint exists for.
- `init`'s hint said "<holder> and its members are private" (L2-71), and its
  NOTE "and its members will be too", of members `init` never makes.
- #913: `init`'s NOTE was printed only for a holder that is private or
  internal, so a public holder whose members are private was never told
  they need the credential (L2-95); an internal root whose plan could not
  be read was told the hint applies when its organisation is on the Free
  plan, which cannot hold of it (L2-93); and the `not-found-on-stdout-alone`
  row did not hold gh's not-found words on stdout (L2-97).

WHAT IS PINNED. One table, the three tools: a root or holder GitHub calls
PUBLIC (no hint, no plan asked), PRIVATE (the hint, naming it alone), one
whose visibility read fails with `HTTP 502` (said to be unread, never
guessed), and a private one whose plan read fails or names no plan (said to
be unread, never taken as paid). Then the readers in `shape_materialize.py`
on their own.

`gh` is `test_scaffold_reuse_seeded_legs.py`'s stub, first on PATH: it knows
each repository at its visibility, names the plan or fails it, and fails the
one `--json visibility` read it is told to. Nothing reaches GitHub. It is a
`#!` script, so the runs that start it are `WINDOWS_SKIP`ped; the readers'
own tests below run everywhere.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

import pytest

import test_adopt_free_plan_hint_root as adopt_hint
from conftest import (ORG, PROJECT, REPO, WINDOWS_SKIP, load_without_bytecode,
                      run_script)
from test_adopt_free_plan_hint_root import NORTHWIND, create_the_legs
from test_scaffold_reuse_seeded_legs import fake_gh, on_github

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402
from repo_shape import load_yaml  # noqa: E402

#: `adopt-project.py` loaded once for this module, by the fixture of the file
#: whose `create_the_legs` the adopt rows run.
adopter = adopt_hint.adopter
FAMILY = REPO / "scripts" / "family.py"
HOLDER = "Orbit"
#: The repository each tool's `validate` workflow runs in, by tool.
ROOTS = {"scaffold": f"{ORG}/{PROJECT}", "adopt": f"{ORG}/{NORTHWIND}",
         "family": f"{ORG}/{HOLDER}"}
#: What `gh` says on stderr, with exit 1: an outage; a token an organisation's
#: SAML enforcement refuses (a 403, in GraphQL's words); a repository GitHub
#: does not show it; and the REST 404 GitHub gives `orgs/<login>` for a login
#: that is not an organisation, such as a personal account (#660's F1).
BAD_GATEWAY = "HTTP 502: Bad Gateway (https://api.github.com/graphql)"
SAML_REFUSED = ("GraphQL: Resource protected by organization SAML enforcement."
                " You must grant your Personal Access token access to this "
                "organization. (repository)")
NOT_FOUND = ("GraphQL: Could not resolve to a Repository with the name "
             f"'{ORG}/Orbit'. (repository)")
NOT_AN_ORGANISATION = "gh: Not Found (HTTP 404)"
PLAN_ASKED = f"api orgs/{ORG} --jq .plan.name"
HINT = f"NOTE {ORG} is on the GitHub FREE plan"


def unread_root(root: str) -> list[str]:
    """What a run says of a root whose visibility it could not read."""
    return [f"NOTE this run could not read {root}'s visibility from GitHub, "
            "so it cannot say whether the Free-plan secrets hint applies.",
            f"`gh repo view {root} --json visibility` says which it is."]


def unread_plan(root: str) -> list[str]:
    """What a run says of a private root whose organisation's plan it could
    not read."""
    return [f"NOTE this run could not read {ORG}'s plan from GitHub, so it "
            "cannot say whether the Free-plan secrets hint applies. "
            f"{root} is private, so it applies when {ORG} is on the GitHub "
            "Free plan: organisation secrets are then not delivered to "
            f"{root}, so org-level SHAPE_LEGS_APP_ID / "
            "SHAPE_LEGS_APP_PRIVATE_KEY resolve to EMPTY in its `validate` "
            f"workflow and must be set as REPOSITORY secrets on {root} "
            f"instead. `gh api orgs/{ORG} --jq .plan.name`, run with an "
            "owner's login, says which plan it is on."]


def init_on_github(tmp_path, env: dict, *extra: str):
    """`family.py init` of `HOLDER` in its GitHub mode, against the stub,
    pushing nothing."""
    return run_script(FAMILY, "init", "--org", ORG, "--family", HOLDER,
                      "--created-by", "Test Human", "--no-push",
                      "--work-dir", str(tmp_path / "work"), *extra, env=env)


def run_tool(tool: str, tmp_path, monkeypatch, capsys, module,
             seen: str, **stub) -> tuple[str, list]:
    """`tool`, against the stub, over a root (or holder) GitHub knows at
    `seen`, with closed legs where it has legs: what it printed, and its
    `gh` calls as their arguments joined by spaces.

    The scaffold and `init` reuse an empty root or holder (`--reuse-empty-
    repo`), the one case where the run's `--visibility` is not that
    repository's own; adopt's root is the source it adopts, and
    `_create_leg_remotes` is run as `cmd_execute` runs it, in `module`,
    `adopt-project.py` loaded."""
    if tool == "adopt":
        return create_the_legs(module, monkeypatch, capsys, tmp_path,
                               {NORTHWIND: seen}, **stub)
    if tool == "scaffold":
        env, log = fake_gh(tmp_path, {PROJECT: seen,
                                      f"{PROJECT}-spec": "PRIVATE",
                                      f"{PROJECT}-code": "PRIVATE"}, **stub)
        result = on_github(tmp_path, "--reuse-empty-repo", env=env)
    else:
        env, log = fake_gh(tmp_path, {HOLDER: seen}, **stub)
        result = init_on_github(tmp_path, env, "--reuse-empty-repo")
    assert result.returncode == 0, result.stderr + result.stdout
    return (result.stdout + result.stderr,
            log.read_text(encoding="utf-8").splitlines())


#: `(root's visibility, stub keywords, what is said)`: "hint" is the Free-plan
#: hint naming the root, "root" the unread-visibility NOTE, "plan" the
#: unread-plan NOTE, and None nothing about the secrets at all. A
#: `visibility_errors` text fails the root's `--json visibility` read alone.
#: An owner GitHub says is no organisation has no organisation secrets, so
#: nothing is said of them: it is not a plan this run could not read.
CASES = {
    "public": ("PUBLIC", {"plan": "free"}, None),
    "private": ("PRIVATE", {"plan": "free"}, "hint"),
    "visibility-502": ("PRIVATE", {"plan": "free",
                                   "visibility_errors": BAD_GATEWAY}, "root"),
    "visibility-403": ("PRIVATE", {"plan": "free",
                                   "visibility_errors": SAML_REFUSED}, "root"),
    "plan-502": ("PRIVATE", {"plan_error": BAD_GATEWAY}, "plan"),
    "not-an-organisation": ("PRIVATE", {"plan_error": NOT_AN_ORGANISATION},
                            None),
    "plan-unnamed": ("PRIVATE", {"plan": ""}, "plan"),
    "paid": ("PRIVATE", {"plan": "team"}, None),
}


@WINDOWS_SKIP
@pytest.mark.parametrize("case", list(CASES))
@pytest.mark.parametrize("tool", list(ROOTS))
def test_each_tool_says_what_github_said_of_the_root_and_its_plan(
        tool, case, tmp_path, monkeypatch, capsys, adopter):
    """L2-57, L2-58, L2-59 and L2-71, in each tool. The hint is printed only
    for a root GitHub calls private or internal on a plan it calls `free`,
    with the root alone as the repository that is private; a root whose
    visibility GitHub does not give is said to be unread and the plan is not
    asked; a closed root whose plan GitHub does not name is said to be on a
    plan this run could not read. On main `init` called a public holder
    private and gave it the hint, the scaffold took the run's visibility for
    a root it could not read, and every tool was silent over an unread plan,
    as over a paid one."""
    seen, stub, said = CASES[case]
    root = ROOTS[tool]
    if "visibility_errors" in stub:
        stub = {**stub, "visibility_errors": {
            root.split("/", 1)[1]: stub["visibility_errors"]}}
    printed, calls = run_tool(tool, tmp_path, monkeypatch, capsys, adopter,
                              seen, **stub)
    assert f"repo view {root} --json visibility" in calls, calls
    lines = {"hint": [HINT, f"{root} is private, so org-level",
                      f"--repo {root} --body"],
             "root": unread_root(root), "plan": unread_plan(root)}
    for kind, expected in lines.items():
        for line in expected:
            assert (line in printed) == (kind == said), (kind, line, printed)
    assert (PLAN_ASKED in calls) == (seen == "PRIVATE"
                                     and said != "root"), calls
    assert "its members" not in printed, printed


def member_note(holder: str) -> str:
    """The NOTE `init` prints for every holder on GitHub (#913, L2-95): about
    the members a person adds, whatever the holder's own visibility."""
    return ("NOTE a private or internal member you add needs a way for "
            f"{holder}, public or not, to read it — a GitHub App "
            "(SHAPE_LEGS_APP_ID + SHAPE_LEGS_APP_PRIVATE_KEY, preferred) or a "
            "SHAPE_LEGS_TOKEN PAT with contents:read on the members AND their "
            "legs — or the `validate` check cannot check that member out.")


@WINDOWS_SKIP
@pytest.mark.parametrize("seen, errors", [
    ("PUBLIC", None),
    ("PRIVATE", None),
    ("INTERNAL", None),
    ("PRIVATE", {HOLDER: BAD_GATEWAY}),
    ("PRIVATE", {HOLDER: NOT_FOUND}),
], ids=["public", "private", "internal", "visibility-502", "visibility-404"])
def test_init_notes_the_members_credential_for_every_reused_holder(
        tmp_path, monkeypatch, capsys, seen, errors):
    """L2-58, the NOTE's half of L2-71, and L2-95. `init`'s NOTE names no
    member: `init` mounts none, and `add` mounts a member of any visibility,
    so "and its members will be too" said what nothing decides. And it is
    about the members, for every holder (#913): the `validate` workflow's
    default token cannot read a private or internal member whatever the
    holder is. On main it was printed only for a holder GitHub called
    private or internal, "NOTE <holder> is <visibility>: give it a way to
    read the members ...", so a public holder whose members are private was
    never told, and neither was one whose visibility went unread.

    family.yaml keeps the RUN's `--visibility`, as it always has, which is
    the decision #660 records: the table that writes it is checked before
    the plan, before the holder is known to exist."""
    printed, _calls = run_tool("family", tmp_path, monkeypatch, capsys, None,
                               seen, plan="team", visibility_errors=errors)
    holder = ROOTS["family"]
    assert printed.count(member_note(holder)) == 1, printed
    assert f"NOTE {holder} is " not in printed, printed
    assert "will be too" not in printed, printed
    manifest = load_yaml(tmp_path / "work" / HOLDER / "family.yaml")
    assert manifest["visibility"] == "private"


@WINDOWS_SKIP
@pytest.mark.parametrize("visibility", ["private", "public"])
def test_init_asks_nothing_of_a_holder_it_creates(tmp_path, visibility):
    """The control: a holder this run creates is created at the run's
    `--visibility`, which is what it is, so GitHub is not asked; it gets the
    members' NOTE, a public one too (#913, L2-95), and, private on Free, the
    hint naming it alone."""
    env, log = fake_gh(tmp_path, {}, plan="free")
    result = init_on_github(tmp_path, env, "--visibility", visibility)
    assert result.returncode == 0, result.stderr + result.stdout
    holder = ROOTS["family"]
    assert member_note(holder) in result.stdout
    assert (f"{holder} is private, so org-level" in result.stdout) == (
        visibility == "private"), result.stdout
    calls = log.read_text(encoding="utf-8").splitlines()
    assert f"repo create {holder} --{visibility}" in " | ".join(calls), calls
    assert f"repo view {holder} --json visibility" not in calls, calls


def test_init_takes_a_holder_gh_cannot_be_asked_about_as_unread(
        monkeypatch, capsys):
    """A reused holder whose visibility read cannot start `gh` (an `OSError`)
    is unread, as a failed read is: `ROOT_VISIBILITY_UNREAD`, and no hint at
    the run's `--visibility`, which is not the holder's (#660's F8); the
    members' NOTE, which goes by no visibility (#913). In process, so it runs on every platform: the topic edit and
    the plan are answered here, and nothing reaches `gh`."""
    family = load_without_bytecode(FAMILY, "family_free_plan_hint_reads")
    edits: list = []
    monkeypatch.setattr(family, "run",
                        lambda args, *_rest, **_keywords: edits.append(args))

    def cannot_start(repository):
        raise FileNotFoundError(2, "No such file or directory", "gh")

    monkeypatch.setattr(family, "repository_visibility", cannot_start)
    monkeypatch.setattr(shape_materialize, "organisation_plan",
                        lambda org: "free")
    holder = ROOTS["family"]
    family._finish_holder_remote(
        argparse.Namespace(org=ORG, visibility="private"), holder,
        "xf-project-orbit", False, True)
    printed = capsys.readouterr().out
    assert unread_root(holder)[0] in printed, printed
    assert f"NOTE {holder} is " not in printed, printed
    assert member_note(holder) in printed, printed
    assert HINT not in printed, printed
    assert edits == [["gh", "repo", "edit", holder, "--add-topic",
                      "xf-project-orbit"]]


# --- the readers, on every platform -----------------------------------------

NO_GH = FileNotFoundError(2, "No such file or directory", "gh")


#: The JSON body `gh api` prints on stdout for a REST 404.
NOT_FOUND_BODY = ('{"message":"Not Found","documentation_url":"https://docs.'
                  'github.com/rest/orgs/orgs#get-an-organization",'
                  '"status":"404"}')


@pytest.mark.parametrize("answer, plan", [
    ((0, "free\n", ""), "free"), ((0, " Free \n", ""), "free"),
    ((0, "team\n", ""), "other"), ((0, "enterprise\n", ""), "other"),
    ((0, "", ""), None), ((0, "\n", ""), None),
    ((1, NOT_FOUND_BODY, NOT_AN_ORGANISATION + "\n"), "not-an-organisation"),
    ((1, "", "gh: Resource protected by organization SAML enforcement. (HTTP "
             "403)\n"), None),
    ((1, "", f"gh: {BAD_GATEWAY}\n"), None),
    ((1, NOT_AN_ORGANISATION + "\n", f"gh: {BAD_GATEWAY}\n"), None),
    (NO_GH, None),
], ids=["free", "free-spaced", "team", "enterprise", "unnamed",
        "blank-line", "not-an-organisation", "saml-403", "failed-502",
        "not-found-on-stdout-alone", "no-gh"])
def test_the_plan_is_free_other_or_unread(monkeypatch, answer, plan):
    """`organisation_plan`: GitHub's word for the plan, `free` or any other;
    `not-an-organisation` where gh says, on stderr, that there is no such
    organisation (the reading `refuse_unless_not_found` gives, #609); and
    None where it names no plan, never "other" for a plan it did not name.
    The command is asked of `subprocess.run`, faked here, since the reading
    is of stderr alone: the `not-found-on-stdout-alone` row holds gh's
    not-found words on stdout, so a reading that searched stdout too would
    take it for `not-an-organisation` (#913, L2-97; its stdout was the REST
    body, which does not hold them)."""
    asked: list = []

    def gh(args, *_rest, **_keywords):
        asked.append(list(args))
        if isinstance(answer, BaseException):
            raise answer
        return subprocess.CompletedProcess(args, *answer)

    monkeypatch.setattr(shape_materialize.subprocess, "run", gh)
    assert shape_materialize.organisation_plan(ORG) == plan
    assert asked == [["gh", "api", f"orgs/{ORG}", "--jq", ".plan.name"]]


#: `gh repo view`'s answer for a repository GitHub does not show this token.
NOT_FOUND_IN_GRAPHQL = ("GraphQL: Could not resolve to a Repository with the "
                        f"name '{ROOTS['scaffold']}'. (repository)\n")


@pytest.mark.parametrize("answer, seen", [
    ((0, '{"visibility": "Internal"}\n', ""), "internal"),
    ((0, '{"visibility": "PUBLIC"}', ""), "public"),
    ((0, '{"visibility": "SECRET"}\n', ""), None),
    ((0, "", ""), None),
    ((1, "", NOT_FOUND_IN_GRAPHQL), "not-found"),
    ((1, NOT_FOUND_IN_GRAPHQL, f"{BAD_GATEWAY}\n"), None),
    ((4, "", NOT_FOUND_IN_GRAPHQL), None),
    ((1, "", f"{BAD_GATEWAY}\n"), None),
    ((1, "", SAML_REFUSED + "\n"), None),
], ids=["internal", "public", "not-a-visibility", "empty", "not-found",
        "not-found-on-stdout-alone", "not-found-words-exit-4", "failed-502",
        "saml-403"])
def test_a_visibility_read_is_one_of_three_not_found_or_unread(
        monkeypatch, answer, seen):
    """`repository_visibility_answer`: what `visibility_in` reads;
    `REPOSITORY_NOT_FOUND` for gh's own not-found answer, exit 1 with its
    words on stderr, the reading `refuse_unless_not_found` gives (#609), so
    the scaffold tells a root not there yet from one it could not read
    (#913); and None for every other failure. `repository_visibility` is the
    same reading with not-found taken as unread, as its callers ask it of a
    repository that is there. Asked of `subprocess.run`, faked here, since
    the reading is of stderr alone."""
    root = ROOTS["scaffold"]
    asked: list = []

    def gh(args, *_rest, **_keywords):
        asked.append(list(args))
        return subprocess.CompletedProcess(args, *answer)

    monkeypatch.setattr(shape_materialize.subprocess, "run", gh)
    assert shape_materialize.repository_visibility_answer(root) == seen
    assert shape_materialize.repository_visibility(root) == (
        None if seen == shape_materialize.REPOSITORY_NOT_FOUND else seen)
    assert asked == [["gh", "repo", "view", root, "--json", "visibility"]] * 2


def test_a_visibility_read_leaves_a_gh_that_cannot_start_to_the_caller(
        monkeypatch):
    """A `gh` that cannot be started is left to the caller, which the
    scaffold refuses as `gh-not-found` (#537) and `family.py` takes as
    unread."""
    def gh(args, *_rest, **_keywords):
        raise NO_GH

    monkeypatch.setattr(shape_materialize.subprocess, "run", gh)
    for read in (shape_materialize.repository_visibility_answer,
                 shape_materialize.repository_visibility):
        with pytest.raises(FileNotFoundError):
            read(ROOTS["scaffold"])


#: What a run says of an INTERNAL root whose organisation's plan it could not
#: read (#913, L2-93): the plan is not what the hint hangs on.
def unread_plan_internal(root: str) -> str:
    return (f"NOTE this run could not read {ORG}'s plan from GitHub, but the "
            "Free-plan secrets hint does not hang on it: "
            f"{root} is internal, which GitHub gives only to a repository of "
            "an organisation an enterprise account owns, and that "
            "organisation is not on the GitHub Free plan. Org-level "
            "SHAPE_LEGS_APP_ID / SHAPE_LEGS_APP_PRIVATE_KEY reach "
            f"{root}'s `validate` workflow where each secret's repository "
            f"access includes {root}.")


@pytest.mark.parametrize("visibility, plan, said", [
    (None, "free", "root"), ("public", "free", None),
    ("private", "free", "hint"), ("internal", "free", "hint"),
    ("private", "other", None), ("private", None, "plan"),
    ("internal", None, "internal"), ("internal", "other", None),
    ("private", "not-an-organisation", None),
], ids=["unread-root", "public", "private-free", "internal-free",
        "private-paid", "private-unread-plan", "internal-unread-plan",
        "internal-paid", "private-not-an-organisation"])
def test_the_note_goes_by_both_answers(monkeypatch, visibility, plan, said):
    """`free_plan_secrets_note`, the one decision the three tools ask: the
    plan is asked only of a closed root, and what neither GitHub answer
    gives is said. An internal root whose plan is unread is told the plan
    is not what the hint hangs on (#913, L2-93): it was told the hint
    "applies when" its organisation "is on the GitHub Free plan", which an
    organisation that holds internal repositories is not."""
    asked: list = []
    monkeypatch.setattr(shape_materialize, "organisation_plan",
                        lambda org: asked.append(org) or plan)
    root = ROOTS["adopt"]
    note = shape_materialize.free_plan_secrets_note(ORG, root, visibility)
    first = {"hint": HINT, "root": unread_root(root)[0],
             "plan": f"NOTE this run could not read {ORG}'s plan",
             "internal": unread_plan_internal(root)}
    if said is None:
        assert note is None
    else:
        assert note.startswith(first[said]), note
    if said == "hint":
        assert f"{root} is private, so org-level" in note, note
    if said == "plan":
        assert note == unread_plan(root)[0], note
    if said == "internal":
        assert note == unread_plan_internal(root), note
        assert "applies when" not in note, note
    assert asked == ([ORG] if visibility in ("private", "internal")
                     else []), asked
