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

import sys

import pytest

import test_adopt_free_plan_hint_root as adopt_hint
from conftest import ORG, PROJECT, REPO, WINDOWS_SKIP, run_script
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
#: An outage, as `gh` reports one on stderr with exit 1.
BAD_GATEWAY = "HTTP 502: Bad Gateway (https://api.github.com/graphql)"
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
CASES = {
    "public": ("PUBLIC", {"plan": "free"}, None),
    "private": ("PRIVATE", {"plan": "free"}, "hint"),
    "visibility-502": ("PRIVATE", {"plan": "free",
                                   "visibility_errors": BAD_GATEWAY}, "root"),
    "plan-502": ("PRIVATE", {"plan_error": BAD_GATEWAY}, "plan"),
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


#: The NOTE `init` prints for a closed holder, after its subject.
HOLDER_NOTE = (": give it a way to read the members you add that are private "
               "or internal — a GitHub App (SHAPE_LEGS_APP_ID + "
               "SHAPE_LEGS_APP_PRIVATE_KEY, preferred) or a SHAPE_LEGS_TOKEN "
               "PAT with contents:read on the members AND their legs — or the "
               "`validate` check cannot check them out.")


@WINDOWS_SKIP
@pytest.mark.parametrize("seen, errors, noted", [
    ("PUBLIC", None, None),
    ("PRIVATE", None, "private"),
    ("INTERNAL", None, "internal"),
    ("PRIVATE", {HOLDER: BAD_GATEWAY}, None),
], ids=["public", "private", "internal", "visibility-502"])
def test_init_notes_a_reused_holder_at_its_own_visibility(
        tmp_path, monkeypatch, capsys, seen, errors, noted):
    """L2-58 and the NOTE's half of L2-71. `init`'s NOTE goes by the reused
    holder as GitHub reports it, and names no member: `init` mounts none, and
    `add` mounts a member of any visibility, so "and its members will be
    too" said what nothing decides. An unread holder gets no NOTE, since
    whether it is private is the question that went unanswered. On main the
    NOTE said "is private and its members will be too" of every holder the
    default `--visibility private` reused, the public one included.

    family.yaml keeps the RUN's `--visibility`, as it always has, which is
    the decision #660 records: the table that writes it is checked before
    the plan, before the holder is known to exist."""
    printed, _calls = run_tool("family", tmp_path, monkeypatch, capsys, None,
                               seen, plan="team", visibility_errors=errors)
    holder = ROOTS["family"]
    if noted is None:
        assert f"NOTE {holder} is " not in printed, printed
    else:
        assert f"NOTE {holder} is {noted}{HOLDER_NOTE}" in printed, printed
    assert "will be too" not in printed, printed
    manifest = load_yaml(tmp_path / "work" / HOLDER / "family.yaml")
    assert manifest["visibility"] == "private"


@WINDOWS_SKIP
def test_init_asks_nothing_of_a_holder_it_creates(tmp_path):
    """The control: a holder this run creates is created at the run's
    `--visibility`, which is what it is, so GitHub is not asked; it gets the
    NOTE and, on Free, the hint naming it alone."""
    env, log = fake_gh(tmp_path, {}, plan="free")
    result = init_on_github(tmp_path, env)
    assert result.returncode == 0, result.stderr + result.stdout
    holder = ROOTS["family"]
    assert f"NOTE {holder} is private{HOLDER_NOTE}" in result.stdout
    assert f"{holder} is private, so org-level" in result.stdout
    calls = log.read_text(encoding="utf-8").splitlines()
    assert f"repo create {holder} --private" in " | ".join(calls), calls
    assert f"repo view {holder} --json visibility" not in calls, calls


# --- the readers, on every platform -----------------------------------------

def answering(monkeypatch, answer) -> list:
    """`shape_materialize.run` answering every command with `answer`, or
    raising it when it is an exception; returns the commands it was asked."""
    asked: list = []

    def run(args, *_rest, **_keywords):
        asked.append(args)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    monkeypatch.setattr(shape_materialize, "run", run)
    return asked


FAILED = shape_materialize.CommandFailed(["gh"], None, 1, BAD_GATEWAY)
NO_GH = FileNotFoundError(2, "No such file or directory", "gh")


@pytest.mark.parametrize("answer, plan", [
    ("free", "free"), (" Free \n", "free"), ("team", "other"),
    ("enterprise", "other"), ("", None), ("\n", None), (FAILED, None),
    (NO_GH, None),
], ids=["free", "free-spaced", "team", "enterprise", "unnamed",
        "blank-line", "failed", "no-gh"])
def test_the_plan_is_free_other_or_unread(monkeypatch, answer, plan):
    """`organisation_plan`: GitHub's word for the plan, `free` or any other,
    and None where it names none, never "other" for a plan it did not
    name."""
    asked = answering(monkeypatch, answer)
    assert shape_materialize.organisation_plan(ORG) == plan
    assert asked == [["gh", "api", f"orgs/{ORG}", "--jq", ".plan.name"]]


def test_a_visibility_read_is_one_of_three_or_unread(monkeypatch):
    """`repository_visibility`: what `visibility_in` reads, None for a failed
    `gh repo view`, and a `gh` that cannot be started left to the caller,
    which the scaffold refuses as `gh-not-found` (#537)."""
    root = ROOTS["scaffold"]
    asked = answering(monkeypatch, '{"visibility": "Internal"}')
    assert shape_materialize.repository_visibility(root) == "internal"
    assert asked == [["gh", "repo", "view", root, "--json", "visibility"]]
    answering(monkeypatch, '{"visibility": "SECRET"}')
    assert shape_materialize.repository_visibility(root) is None
    answering(monkeypatch, FAILED)
    assert shape_materialize.repository_visibility(root) is None
    answering(monkeypatch, NO_GH)
    with pytest.raises(FileNotFoundError):
        shape_materialize.repository_visibility(root)


@pytest.mark.parametrize("visibility, plan, said", [
    (None, "free", "root"), ("public", "free", None),
    ("private", "free", "hint"), ("internal", "free", "hint"),
    ("private", "other", None), ("private", None, "plan"),
], ids=["unread-root", "public", "private-free", "internal-free",
        "private-paid", "private-unread-plan"])
def test_the_note_goes_by_both_answers(monkeypatch, visibility, plan, said):
    """`free_plan_secrets_note`, the one decision the three tools ask: the
    plan is asked only of a closed root, and what neither GitHub answer
    gives is said."""
    asked: list = []
    monkeypatch.setattr(shape_materialize, "organisation_plan",
                        lambda org: asked.append(org) or plan)
    root = ROOTS["adopt"]
    note = shape_materialize.free_plan_secrets_note(ORG, root, visibility)
    first = {"hint": HINT, "root": unread_root(root)[0],
             "plan": f"NOTE this run could not read {ORG}'s plan"}
    if said is None:
        assert note is None
    else:
        assert note.startswith(first[said]), note
    if said == "hint":
        assert f"{root} is private, so org-level" in note, note
    assert asked == ([ORG] if visibility in ("private", "internal")
                     else []), asked
