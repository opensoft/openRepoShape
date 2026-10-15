# SPDX-License-Identifier: Apache-2.0
"""`execute`'s Free-plan secrets hint goes by the ADOPTED ROOT, and names it
as its reason (#602).

WHAT WAS WRONG. `_create_leg_remotes` printed `free_plan_secret_hint` on the
plan's `visibility`, which is the two new LEGS', and named the legs as its
subject. The `validate` workflow that reads `SHAPE_LEGS_APP_ID` and
`SHAPE_LEGS_APP_PRIVATE_KEY` runs in the assembly root, and an adopted root
keeps the visibility it had (`templates/assembly-root/project.yaml`). On the
Free plan an organisation secret is delivered only to a public repository, so
a public source adopted with private legs was told its organisation secrets
"resolve to EMPTY inside the workflow", which is false of it, and a private
root was told the legs were the reason, which they are not. The scaffold has
gated the hint on its root since #542; both tools now name the root too.

WHAT IS PINNED. The per-leg NOTE is as it was: a public root still needs a
credential to read a private leg. The hint is printed only when the root, as
GitHub reports it, is private or internal, with the root as its subject. A
root whose visibility cannot be read is neither guessed closed (a false hint)
nor guessed public (a true one hidden): the run says it could not read it,
what the hint would then say, and how to look. `--local-remote-dir` has no
GitHub root, and asks and prints nothing about one.

`gh` is `test_scaffold_reuse_seeded_legs.py`'s stub, first on PATH: it knows
the repositories it is given, each at its visibility, answers `repo create`,
and names the organisation's plan. Nothing reaches GitHub. It is a `#!`
script, so the runs that start it are `WINDOWS_SKIP`ped.
"""

from __future__ import annotations

import importlib.util

import pytest

from conftest import ADOPT, ORG, WINDOWS_SKIP
from test_scaffold_reuse_seeded_legs import fake_gh

NORTHWIND = "Northwind"
ROOT = f"{ORG}/{NORTHWIND}"
NAMES = {"assembly": NORTHWIND, "spec": f"{NORTHWIND}-spec",
         "code": f"{NORTHWIND}-code"}
SPEC_REPO, CODE_REPO = f"{ROOT}-spec", f"{ROOT}-code"

#: The per-leg NOTE, which #602 leaves as it was.
LEG_NOTE = (f"NOTE {SPEC_REPO} and {CODE_REPO} are private: give {ROOT} a "
            "way to read them — a GitHub App (SHAPE_LEGS_APP_ID + "
            "SHAPE_LEGS_APP_PRIVATE_KEY, preferred) or a SHAPE_LEGS_TOKEN PAT "
            "(contents:read on the legs, fallback) — or the `validate` check "
            "cannot check them out.")
#: `FREE_PLAN_HINT`'s first words, and its subject as it is put before
#: " private, so": the root now, the two legs on main.
HINT = f"NOTE {ORG} is on the GitHub FREE plan"
ROOT_SUBJECT = f"{ROOT} is private, so org-level"
LEG_SUBJECT = f"{SPEC_REPO} and {CODE_REPO} are private, so"
#: What a run that could not read the root's visibility says instead.
UNREAD = (f"NOTE this run could not read {ROOT}'s visibility from GitHub, "
          "so it cannot say whether the Free-plan secrets hint applies. It "
          f"applies when {ROOT} is private or internal and its organisation "
          "is on the GitHub Free plan:")
LOOK = f"`gh repo view {ROOT} --json visibility` says which it is."
VIEW_ROOT = f"repo view {ROOT} --json visibility"


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_free_plan_hint_root",
                                                  ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def create_the_legs(adopter, monkeypatch, capsys, tmp_path, repos: dict, *,
                    plan: str | None = "free", visibility: str = "private",
                    local: bool = False) -> tuple[str, list]:
    """`_create_leg_remotes` for `NAMES` under `ORG`, as `cmd_execute` calls
    it, with the stub `gh` knowing `repos` (`{name: VISIBILITY}`) and naming
    `plan` as the organisation's plan. Returns what it printed and the `gh`
    calls it made, each as its arguments joined by spaces."""
    env, log = fake_gh(tmp_path, repos, plan=plan)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    if local:
        urls = {role: str(tmp_path / "remotes" / f"{name}.git")
                for role, name in NAMES.items()}
    else:
        urls = {role: f"https://github.com/{ORG}/{name}.git"
                for role, name in NAMES.items()}
    adopter._create_leg_remotes(
        {"org": ORG, "visibility": visibility}, NAMES,
        {role: f"{ORG}/{name}" for role, name in NAMES.items()}, urls,
        "main", local, tmp_path / "work")
    out, _err = capsys.readouterr()
    return out, log.read_text(encoding="utf-8").splitlines()


@WINDOWS_SKIP
def test_a_public_root_over_private_legs_gets_the_note_and_no_hint(
        adopter, monkeypatch, capsys, tmp_path):
    """The issue's own case: a public source adopted with private legs. The
    root's workflow is given the organisation's secrets on the Free plan, so
    the hint would be false of it; the legs still need a credential, so the
    NOTE stays. On main the hint was printed, naming the legs."""
    out, calls = create_the_legs(adopter, monkeypatch, capsys, tmp_path,
                                 {NORTHWIND: "PUBLIC"})
    assert LEG_NOTE in out, out
    assert "resolve to EMPTY" not in out, out
    assert UNREAD not in out, out
    assert calls.count(VIEW_ROOT) == 1, calls


@WINDOWS_SKIP
@pytest.mark.parametrize("seen", ["PRIVATE", "INTERNAL"])
def test_a_closed_root_gets_the_hint_naming_the_root(
        adopter, monkeypatch, capsys, tmp_path, seen):
    """A private or internal root on the Free plan gets the hint, once, with
    the root as the repository that is private and the one its `gh secret
    set` lines name. On main the hint named the legs as the reason.

    `FREE_PLAN_HINT`'s word is "private" for an internal root too, as it is
    in the scaffold's: an internal repository belongs to an enterprise's
    organisation, whose plan is not `free`, so outside a stub the two never
    meet. The row is here for the gate, which counts internal as closed."""
    out, calls = create_the_legs(adopter, monkeypatch, capsys, tmp_path,
                                 {NORTHWIND: seen})
    assert LEG_NOTE in out, out
    assert HINT in out, out
    assert ROOT_SUBJECT in out, out
    assert LEG_SUBJECT not in out, out
    assert f"--repo {ROOT} --body" in out, out
    assert out.count("resolve to EMPTY") == 1, out
    assert UNREAD not in out, out
    assert out.index(LEG_NOTE) < out.index(HINT), "the NOTE comes first"
    assert calls.count(VIEW_ROOT) == 1, calls


@WINDOWS_SKIP
def test_a_root_whose_visibility_cannot_be_read_is_named_not_guessed(
        adopter, monkeypatch, capsys, tmp_path):
    """`gh repo view` of the root fails (the stub does not know it, as gh
    does not a repository it cannot see). Taking it as private would print a
    hint that is false of a public root; taking it as public would hide one
    that is true of a private root. The run says which question it could
    not answer, what the hint would say, and how to answer it, and prints
    the hint itself for no root. On main the hint was printed, naming the
    legs, on the plan's visibility alone."""
    out, calls = create_the_legs(adopter, monkeypatch, capsys, tmp_path, {})
    assert LEG_NOTE in out, out
    assert UNREAD in out, out
    assert LOOK in out, out
    assert (f"must be set as REPOSITORY secrets on {ROOT} instead"
            in out), out
    assert HINT not in out, out
    assert LEG_SUBJECT not in out, out
    assert out.index(LEG_NOTE) < out.index(UNREAD), "the NOTE comes first"
    assert calls.count(VIEW_ROOT) == 1, calls


@WINDOWS_SKIP
def test_a_closed_root_on_a_paid_plan_gets_no_hint(adopter, monkeypatch,
                                                   capsys, tmp_path):
    """The control: on a paid plan the organisation's secrets reach a private
    repository, so a private root gets the NOTE and no hint, as on main."""
    out, _calls = create_the_legs(adopter, monkeypatch, capsys, tmp_path,
                                  {NORTHWIND: "PRIVATE"}, plan="team")
    assert LEG_NOTE in out, out
    assert "resolve to EMPTY" not in out, out
    assert UNREAD not in out, out


@WINDOWS_SKIP
def test_public_legs_ask_nothing_of_the_root(adopter, monkeypatch, capsys,
                                             tmp_path):
    """Public legs need no credential, so the workflow's secrets decide
    nothing: no NOTE, no hint, and the root's visibility is not asked."""
    out, calls = create_the_legs(adopter, monkeypatch, capsys, tmp_path,
                                 {NORTHWIND: "PRIVATE"}, visibility="public")
    assert "NOTE" not in out, out
    assert not [call for call in calls if call.startswith("repo view")], calls


@WINDOWS_SKIP
def test_a_local_remote_dir_has_no_github_root_to_ask(adopter, monkeypatch,
                                                      capsys, tmp_path):
    """Under `--local-remote-dir` the root is the source on disk and the legs
    are bare repositories beside it: no repository has a visibility, and no
    workflow is given any secret. Nothing is asked of `gh` and no NOTE is
    printed, as on main."""
    out, calls = create_the_legs(adopter, monkeypatch, capsys, tmp_path,
                                 {NORTHWIND: "PRIVATE"}, local=True)
    assert "NOTE" not in out, out
    assert calls == [], calls
    for name in (NAMES["spec"], NAMES["code"]):
        assert (tmp_path / "remotes" / f"{name}.git").is_dir()


@pytest.mark.parametrize("answer, seen", [
    ('{"visibility":"PRIVATE"}', "private"),
    ('{"visibility":"public"}', "public"),
    ('{"visibility":"INTERNAL"}', "internal"),
    ('{"visibility":"SECRET"}', None),
    ('{"visibility":null}', None),
    ("{}", None),
    ('["PRIVATE"]', None),
    ("PRIVATE", None),
    ("", None),
], ids=["private", "public", "internal", "unknown-word", "null", "no-field",
        "not-an-object", "not-json", "empty"])
def test_the_root_is_one_of_the_three_visibilities_or_unread(
        adopter, monkeypatch, answer, seen):
    """What `gh repo view --json visibility` answers is read as GitHub's
    three visibilities, in any case, and anything else as unread: never as a
    visibility it does not name."""
    asked: list = []

    def gh(args, *_rest, **_keywords):
        asked.append(args)
        return answer

    monkeypatch.setattr(adopter, "run", gh)
    assert adopter._root_visibility(ROOT) == seen
    assert asked == [["gh", "repo", "view", ROOT, "--json", "visibility"]]


@pytest.mark.parametrize("failure", ["command", "no-gh"])
def test_a_gh_that_fails_or_cannot_run_is_unread(adopter, monkeypatch,
                                                 failure):
    """A failed `gh repo view` (a repository it cannot see, a rate limit,
    the network) and a `gh` that cannot be started are unread, not a
    refusal: both legs exist by now, and the run goes on to push them."""
    def gh(args, *_rest, **_keywords):
        if failure == "command":
            raise adopter.CommandFailed(args, None, 1, "HTTP 403")
        raise FileNotFoundError(2, "No such file or directory", "gh")

    monkeypatch.setattr(adopter, "run", gh)
    assert adopter._root_visibility(ROOT) is None
