# SPDX-License-Identifier: Apache-2.0
"""A hand edit of a leg's mount leaves no plan-time path behind (#600).

`adopt-project.py plan` writes its follow-ups once. `MOUNT_REMEDIATION` and
`plan-leg-path-collides` both tell a person to change `legs.spec_path` or
`legs.code_path` in the plan afterwards, and `execute` then mounts the legs at
the edited paths. A follow-up that named a path it had been given at `plan`
went on saying so in `check`'s output, in the split commit's message and in
the pull request's body, for a layout that no longer had it: the read-across
line said `code/src/app/main.py` and `../spec/contracts/` "relative to
`code/`" (#493's review, F3, for `tracking_branch`; #522's review, F1, for the
Makefile line). It names the two keys now, and the `contracts/` rule's
`reason:`, which every plan entry copies, names no path either (L2-19).

What the line leaves out is the ready-to-type relative path from the code leg
to the spec leg's `contracts/`, which a person derives wrongly by hand for
nested legs (#522's review, auA-13). `check`'s `mount the legs at X/ and Y/`
and the split message's `mounted back here at X/ and Y/` now end with it,
computed from the mounts THEY print, so it follows a hand edit of either key
and is never stored in the plan (#600's review, F1).

The end-to-end tests plan with one layout, edit both keys to another, and run
`check` and `execute` for real: once with `--local-remote-dir`, which opens no
pull request, and once against a stub `gh` that logs the arguments of the
`pr create` it is given, the body among them. They need `git filter-repo`
and skip without it, as `tests/test_adopt_e2e.py` does. No network and no
GitHub: the legs are bare repositories on disk, and the stub `gh` is first on
PATH ahead of `tests/conftest.py`'s guard.
"""

from __future__ import annotations

import os
import posixpath
import re
import stat
import sys
import textwrap
from pathlib import Path

import pytest

from conftest import (ADOPT, ORG, REPO, git, load_without_bytecode,
                      make_source_repo, run_script, write_plan)
from test_adopt_contracts_dir import (EDITS, PROJECT, READER, SPLIT_BRANCH,
                                      TREE, needs_filter_repo)
from test_adopt_literal_names import follow_up

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml  # noqa: E402

POLICY = REPO / "contracts" / "path-classification.yaml"

#: What each follow-up surface says of the one code file that names
#: `contracts/`, whatever the mounts hold.
READ_ACROSS = follow_up(READER, "contracts/")

#: `(plan-time spec path, plan-time code path, the spec leg relative to the
#: code leg, as `plan` printed it before #600)`, and the layout the hand edit
#: moves the two legs to. The edited paths share nothing with the plan-time
#: ones, so a plan-time path left in a message cannot be taken for them.
PLAN_TIME = [
    pytest.param("spec", "code", "../spec", id="default"),
    pytest.param("legs/spec", "impl/code", "../../legs/spec", id="nested"),
]
EDITED_SPEC, EDITED_CODE = "elsewhere/s", "elsewhere/c"
EDITED_ACROSS = "../s/contracts/"

#: A `gh` that creates a bare repository for `repo create`, takes `repo edit`,
#: and logs every argument of a `pr create`, NUL-separated, so the body is read
#: back as it was given. `repo view <repository> --json nameWithOwner`, which
#: `execute` asks of each leg before it makes either (#798), finds one under
#: $FAKE_GH_ROOT, answering with its name as GitHub does, and gives gh's
#: not-found answer for any other. Anything else is refused: it reaches
#: nothing.
STUB_GH = textwrap.dedent("""\
    #!/bin/sh
    if [ "$1 $2 $4 $5" = "repo view --json nameWithOwner" ]; then
      if [ -d "$FAKE_GH_ROOT/$3.git" ]; then
        printf '{"nameWithOwner": "%s"}\\n' "$3"; exit 0
      fi
      echo "GraphQL: Could not resolve to a Repository with the name '$3'." >&2
      exit 1
    fi
    case "$1 $2" in
      "repo create")
        git init -q --bare -b main "$FAKE_GH_ROOT/$3.git" \\
          && echo "https://github.com/$3";;
      "pr create")
        for argument in "$@"; do printf '%s\\0' "$argument"; done \\
          > "$FAKE_GH_ROOT/pull-request-arguments"
        echo "https://github.com/$FAKE_GH_REPO/pull/1";;
      "repo edit") ;;
      *) exit 1;;
    esac
    """)


def edit_the_mounts(plan: Path, before: tuple, after: tuple) -> None:
    """`legs.spec_path` and `legs.code_path` edited by hand, as
    `MOUNT_REMEDIATION` and `plan-leg-path-collides` ask, LF as `plan` wrote
    the file."""
    text = plan.read_text(encoding="utf-8")
    for key, old, new in zip(("spec_path", "code_path"), before, after):
        line = f"  {key}: {old}\n"
        assert line in text, text
        text = text.replace(line, f"  {key}: {new}\n")
    with open(plan, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def a_stub_gh(base: Path, github: Path) -> dict:
    """The environment of a run against GitHub with the stub `gh`: every
    `https://github.com/` URL is the bare repositories under `github`, and
    the operator's `gh` has no token to act with and no config to read."""
    bin_dir = base / "bin"
    bin_dir.mkdir()
    shim = bin_dir / "gh"
    shim.write_bytes(STUB_GH.encode("utf-8"))
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
    config = base / "gitconfig"
    config.write_bytes(f'[url "{github.as_posix()}/"]\n'
                       "\tinsteadOf = https://github.com/\n".encode("utf-8"))
    (base / "gh-config").mkdir()
    return {"PATH": os.pathsep.join([str(bin_dir), os.environ["PATH"]]),
            "GH_TOKEN": "bogus-token-w600",
            "GH_CONFIG_DIR": str(base / "gh-config"),
            "GIT_CONFIG_GLOBAL": str(config), "GIT_ALLOW_PROTOCOL": "file",
            "FAKE_GH_ROOT": str(github), "FAKE_GH_REPO": f"{ORG}/{PROJECT}"}


def follow_ups_in(message: str) -> list[str]:
    """The items of a split commit's message, which is also the pull
    request's body, under `FOLLOW-UPS`."""
    return [line[4:] for line in message.splitlines()
            if line.startswith("  - ")]


def adopt_after_the_hand_edit(base: Path, plan_time: tuple, *, github: bool,
                              edited: tuple = (EDITED_SPEC, EDITED_CODE)
                              ) -> dict:
    """Plan `plan_time`, edit the two keys to `edited` (EDITED_* unless
    given), `check`, then `execute`. Returns what each surface said of the
    follow-ups: `check`'s `follow-up:` lines, the split commit's message and,
    against GitHub, the body `gh pr create` was given."""
    source = make_source_repo(base / PROJECT, TREE, edits=EDITS)
    root = base / "github" / ORG / f"{PROJECT}.git"
    if github:
        # The assembly root is the repository the source was cloned from: the
        # split branch is pushed back to it.
        root.parent.mkdir(parents=True)
        git("clone", "-q", "--bare", ".", str(root), cwd=source)
    plan = base / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT, org=ORG,
                         extra=("--spec-path", plan_time[0],
                                "--code-path", plan_time[1]))
    assert written.returncode == 0, written.stderr + written.stdout
    edit_the_mounts(plan, plan_time, edited)

    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    where = (("--work-dir", str(base / "work")) if github else
             ("--work-dir", str(base / "work"),
              "--local-remote-dir", str(base / "remotes")))
    env = a_stub_gh(base, base / "github") if github else None
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes", *where,
                        env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "adoption verified" in result.stdout, result.stdout

    # `execute` has just pushed the split branch: read it through git.
    repository = root if github else source
    message = git("log", "-1", "--format=%B", SPLIT_BRANCH,
                  cwd=repository).stdout
    mounts = git("show", f"{SPLIT_BRANCH}:.gitmodules", cwd=repository).stdout
    assert f"path = {edited[0]}\n" in mounts, mounts
    assert f"path = {edited[1]}\n" in mounts, mounts
    body = None
    if github:
        logged = (base / "github" / "pull-request-arguments").read_bytes()
        arguments = logged.decode("utf-8").split("\0")[:-1]
        body = arguments[arguments.index("--body") + 1]
    return {"check": checked.stdout, "message": message, "body": body,
            "plan": load_yaml(plan)}


def read_across_in(items: list[str]) -> list[str]:
    return [item for item in items
            if READER in item and "`contracts/`" in item]


@needs_filter_repo
@pytest.mark.parametrize("github", [
    pytest.param(False, id="local-remote-dir"),
    pytest.param(True, id="stub-gh-pull-request"),
])
@pytest.mark.parametrize("spec_path, code_path, across", PLAN_TIME)
def test_a_hand_edited_mount_leaves_no_plan_time_path_in_a_follow_up(
        tmp_path, spec_path, code_path, across, github):
    """On main, planned with the defaults and edited to other mounts: `check`
    printed `follow-up: code/src/app/main.py names `contracts/` ... `../spec/
    contracts/` relative to `code/``, and so did the split commit's message
    and the pull request's body, over legs mounted at `elsewhere/`. The line
    names the keys now, so it is the same text on every surface and no edit
    can contradict it."""
    ran = adopt_after_the_hand_edit(tmp_path, (spec_path, code_path),
                                    github=github)
    surfaces = {
        "check": [line.split("follow-up: ", 1)[1]
                  for line in ran["check"].splitlines()
                  if line.startswith("  follow-up: ")],
        "the split commit's message": follow_ups_in(ran["message"]),
        "the plan": [str(item) for item in ran["plan"]["follow_ups"]]}
    if github:
        assert ran["body"].rstrip("\n") == ran["message"].rstrip("\n")
        surfaces["the pull request's body"] = follow_ups_in(ran["body"])
    assert {surface: read_across_in(items)
            for surface, items in surfaces.items()} == {
        surface: [READ_ACROSS] for surface in surfaces}
    # No plan-time path, and no path from one leg to the other, anywhere
    # `check` printed, the split commit said or the pull request carried.
    said = {"check": ran["check"],
            "the split commit's message": ran["message"],
            "the pull request's body": ran["body"] or ""}
    stale = (f"{code_path}/{READER}", f"relative to `{code_path}/`",
             f"`{across}/contracts/`")
    assert [(surface, left) for surface, text in said.items()
            for left in stale if left in text] == []
    # What they print instead, beside the mounts `execute` made: the path
    # from the edited code leg to the edited spec leg's `contracts/`.
    assert split_line(ran["check"]).endswith(
        f"mount the legs at {EDITED_SPEC}/ and {EDITED_CODE}/"
        f"{clause(EDITED_ACROSS)}")
    for surface in ("the split commit's message", "the pull request's body"):
        if said[surface]:
            assert (f"mounted back here at {EDITED_SPEC}/ and {EDITED_CODE}/"
                    f"{clause(EDITED_ACROSS)}.") in said[surface], surface


# --- F1: the path from the code leg to the spec leg's `contracts/` ----------

#: `(the mounts `plan` was given, the mounts after the hand edit, the path
#: from the code leg to the spec leg's `contracts/` at the edited mounts)`.
#: The rows cover both defaults and nested legs, a hand edit of both keys in
#: each direction and of either key alone, so the path is the CURRENT
#: mounts' and no plan-time one.
ACROSS_ROWS = [
    pytest.param(("spec", "code"), ("spec", "code"), "../spec/contracts/",
                 id="default"),
    pytest.param(("legs/spec", "impl/code"), ("legs/spec", "impl/code"),
                 "../../legs/spec/contracts/", id="nested"),
    pytest.param(("spec", "code"), ("legs/spec", "impl/code"),
                 "../../legs/spec/contracts/", id="default-edited-to-nested"),
    pytest.param(("legs/spec", "impl/code"), ("spec", "code"),
                 "../spec/contracts/", id="nested-edited-to-default"),
    pytest.param(("spec", "code"), ("spec", "src2/code"),
                 "../../spec/contracts/", id="code-key-edited"),
    pytest.param(("spec", "code"), ("legs/spec", "code"),
                 "../legs/spec/contracts/", id="spec-key-edited"),
]
#: The same rows without the mounts `plan` was given, for the tests that
#: render a surface from the edited mounts alone.
EDITED_ROWS = [pytest.param(*row.values[1:], id=row.id) for row in ACROSS_ROWS]


def clause(across: str) -> str:
    """What the two sentences that print the mounts end with."""
    return (", so from the code leg the spec leg's `contracts/` is "
            f"`{across}`")


def split_line(output: str) -> str:
    """`check`'s one `ONE split commit ... mount the legs at X/ and Y/` line."""
    (line,) = [line for line in output.splitlines()
               if line.startswith("  ONE split commit")]
    return line


@pytest.fixture(scope="module")
def source(tmp_path_factory) -> Path:
    """One source for every `plan` below; `plan` and `check` only read it."""
    return make_source_repo(
        tmp_path_factory.mktemp("leg-keys") / PROJECT, TREE, edits=EDITS)


@pytest.fixture(scope="module")
def adopter():
    """`adopt-project.py` loaded as a module, for its helpers."""
    return load_without_bytecode(ADOPT, "adopt_leg_keys")


def check_after_the_edit(source: Path, base: Path, plan_time: tuple,
                         edited: tuple):
    """`plan` with `plan_time`, the two keys edited to `edited`, then `check`."""
    plan = base / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT, org=ORG,
                         extra=("--spec-path", plan_time[0],
                                "--code-path", plan_time[1]))
    assert written.returncode == 0, written.stderr + written.stdout
    if edited != plan_time:
        edit_the_mounts(plan, plan_time, edited)
    return run_script(ADOPT, "check", "--plan", str(plan))


@pytest.mark.parametrize("plan_time, edited, across", ACROSS_ROWS)
def test_check_prints_the_path_to_the_contracts_beside_the_mounts(
        source, tmp_path, plan_time, edited, across):
    """The read-across line names the keys, so `check` prints the path the
    person has then to write beside the mounts, computed from the plan as
    it stands: after a hand edit of either key it is the edited mounts'
    path, and the plan-time one is nowhere in the output."""
    checked = check_after_the_edit(source, tmp_path, plan_time, edited)
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert split_line(checked.stdout).endswith(
        f"mount the legs at {edited[0]}/ and {edited[1]}/{clause(across)}")
    # It LEADS there, from the edited code leg to the edited spec leg.
    assert posixpath.normpath(posixpath.join(edited[1], across)) == \
        f"{edited[0]}/contracts"
    # The follow-up beside it is the one key-form line, whatever it holds.
    assert [line for line in checked.stdout.splitlines()
            if READER in line and line.startswith("  follow-up: ")] == \
        [f"  follow-up: {READ_ACROSS}"]


@pytest.mark.parametrize("edited_spec, edited_code", [
    pytest.param("legs//spec", "code", id="empty-segment"),
    pytest.param("../spec", "code", id="parent-segment"),
    pytest.param("spec", "spec", id="one-path-for-both"),
    pytest.param("legs/spec", "legs/spec/code", id="one-inside-the-other"),
])
def test_check_prints_no_path_for_two_values_that_are_not_two_mounts(
        source, tmp_path, edited_spec, edited_code):
    """`check` refuses such a plan with a finding of its own, and a path
    computed from two strings that are not two mounts leads nowhere, so the
    mounts are printed with nothing after them."""
    checked = check_after_the_edit(source, tmp_path, ("spec", "code"),
                                   (edited_spec, edited_code))
    assert checked.returncode != 0, checked.stdout
    assert split_line(checked.stdout).endswith(
        f"mount the legs at {edited_spec}/ and {edited_code}/")
    assert "`contracts/` is `" not in checked.stdout


def split_message_at(adopter, spec_path, code_path,
                     spec_leg_paths=("contracts/", "specs/")) -> str:
    return adopter._split_message(
        {"assembly": PROJECT, "spec": f"{PROJECT}-spec",
         "code": f"{PROJECT}-code"},
        {"spec": list(spec_leg_paths), "code": ["src/"], "drop": [],
         "root": ["README.md"]},
        {"spec": "a" * 40, "code": "b" * 40}, spec_path, code_path, [], [])


@pytest.mark.parametrize("edited, across", EDITED_ROWS)
def test_the_split_message_prints_the_path_to_the_contracts_beside_the_mounts(
        adopter, edited, across):
    """The sentence that says where the legs are mounted back ends with the
    path from the code leg to the spec leg's `contracts/` at THOSE mounts,
    which are the ones `execute` made (the pull request's body is this text)."""
    message = split_message_at(adopter, *edited)
    assert (f"mounted back here at {edited[0]}/ and {edited[1]}/"
            f"{clause(across)}.") in message.splitlines()[2]
    assert posixpath.normpath(posixpath.join(edited[1], across)) == \
        f"{edited[0]}/contracts"


@pytest.mark.parametrize("spec_leg_paths, printed", [
    pytest.param(["contracts/"], True, id="the-directory"),
    pytest.param(["README.md", "contracts/policy.yaml"], True,
                 id="a-file-under-it"),
    pytest.param([], False, id="nothing-in-the-spec-leg"),
    pytest.param(["specs/", "docs/"], False, id="other-directories"),
    pytest.param(["contractsX/", "docs/contracts/"], False,
                 id="a-name-that-only-looks-like-it"),
])
def test_the_path_is_printed_only_where_the_spec_leg_holds_contracts(
        adopter, spec_leg_paths, printed):
    """With no `contracts/` in the spec leg there is nothing to lead to, and
    the mounts are the whole of the sentence, as before."""
    message = split_message_at(adopter, "spec", "code", spec_leg_paths)
    assert ("`contracts/` is `" in message) is printed
    assert ("mounted back here at spec/ and code/." in message) is not printed
    assert bool(adopter.contracts_from_code_leg(
        "spec", "code", spec_leg_paths)) is printed


@pytest.mark.parametrize("spec_path, code_path", [
    pytest.param("spec", "spec", id="one-path-for-both"),
    pytest.param("spec", "SPEC", id="two-paths-that-differ-in-case"),
    pytest.param("legs/spec", "legs/spec/code", id="one-inside-the-other"),
    pytest.param("legs//spec", "code", id="empty-segment"),
    pytest.param("../spec", "code", id="parent-segment"),
    pytest.param("spec", None, id="a-mount-that-is-not-text"),
])
def test_the_path_is_never_computed_from_values_that_are_not_two_mounts(
        adopter, spec_path, code_path):
    assert adopter.contracts_from_code_leg(
        spec_path, code_path, ["contracts/"]) == ""


@needs_filter_repo
@pytest.mark.parametrize("plan_time, edited, across", [
    row for row in ACROSS_ROWS
    if row.id in ("default", "default-edited-to-nested", "code-key-edited")])
def test_execute_prints_the_path_of_the_mounts_it_made(
        tmp_path, plan_time, edited, across):
    """End to end, the split commit's message carries the path from the code
    leg to the spec leg's `contracts/` at the mounts the plan had when
    `execute` ran, and `check` printed the same one before it."""
    ran = adopt_after_the_hand_edit(tmp_path, plan_time, github=False,
                                    edited=edited)
    assert split_line(ran["check"]).endswith(
        f"mount the legs at {edited[0]}/ and {edited[1]}/{clause(across)}")
    assert (f"mounted back here at {edited[0]}/ and {edited[1]}/"
            f"{clause(across)}.") in ran["message"]


# --- L2-19: the `contracts/` rule's reason -----------------------------------

#: A path in a rule's reason: a `spec/` or `code/` mount or a `../`, which is
#: only true of one layout. `contracts/` is a name in the SOURCE and stays.
LEG_PATH = re.compile(r"(?<![\w-])(spec|code)/|\.\./")


def spec_governance_reason() -> str:
    (rule,) = [rule for rule in load_yaml(POLICY)["rules"]
               if rule["id"] == "spec-governance"]
    return " ".join(str(rule["reason"]).split())


def test_the_contracts_rules_reason_names_no_leg_path():
    """`contracts/path-classification.yaml` said `../spec/contracts` from
    `code/` in the reason of the rule that sends `contracts/` to the spec
    leg, which is false of a nested plan (`--spec-path legs/spec --code-path
    impl/code`). It says only that the code reads across the assembly-root
    mount."""
    reason = spec_governance_reason()
    assert "the code reads across the assembly-root mount, which is what " \
           "the legs are mounted for" in reason, reason
    assert not LEG_PATH.search(reason), reason
    assert "from the root" not in reason, reason


def free_text_of_the_policy() -> dict:
    """Every `reason:` and `question:` the policy can put into a plan entry,
    by `(rule id, field)`, whitespace collapsed: each rule's, and the
    `default:` block's, which an entry no rule matched copies."""
    policy = load_yaml(POLICY)
    texts = {(rule["id"], field): " ".join(str(rule[field]).split())
             for rule in policy["rules"] for field in ("reason", "question")
             if field in rule}
    texts.update({("default", field): " ".join(str(policy["default"][field])
                                               .split())
                  for field in ("reason", "question")
                  if field in policy["default"]})
    return texts


def test_no_rules_reason_or_question_names_a_leg_path():
    """F2 of #628's review: the guard above read one rule, and a path put
    into any other rule's reason went unseen (the mutant that gave
    `code-source-and-tests` `../spec/contracts` from `code/` survived 502
    tests). Every text the policy copies into a plan entry holds no mount
    path, because the entry is read in a plan whose mounts the person may
    have chosen and will edit."""
    texts = free_text_of_the_policy()
    # The scan covers every rule: each has a reason, and the questions of
    # the ambiguous ones are read too.
    rule_ids = {rule["id"] for rule in load_yaml(POLICY)["rules"]}
    assert {rule for rule, field in texts if field == "reason"} == \
        rule_ids | {"default"}
    assert ("ambiguous-notebooks", "question") in texts
    assert [(rule, field, LEG_PATH.search(text).group(0))
            for (rule, field), text in texts.items()
            if LEG_PATH.search(text)] == []


@pytest.mark.parametrize("text, names_a_path", [
    pytest.param("(`../spec/contracts` from `code/`)", True,
                 id="the-reason-before-#600"),
    pytest.param("`spec/contracts` from the root", True, id="a-mount-name"),
    pytest.param("Mounted at legs/spec/ and impl/code/", True,
                 id="nested-mounts"),
    pytest.param("`contracts/` from beside it, `specs/`, `.github/`", False,
                 id="names-in-the-source"),
    pytest.param("across the assembly-root mount", False, id="the-new-reason"),
    pytest.param("Which leg owns this path: spec, code, or the root?", False,
                 id="the-leg-names-alone"),
])
def test_the_leg_path_guard_sees_a_mount_path(text, names_a_path):
    assert bool(LEG_PATH.search(text)) is names_a_path


@pytest.mark.parametrize("spec_path, code_path", [
    pytest.param("spec", "code", id="default"),
    pytest.param("legs/spec", "impl/code", id="nested"),
])
def test_every_plan_entry_copies_a_reason_true_of_its_layout(
        tmp_path, spec_path, code_path):
    """The reason is copied into each plan entry the rule decides, `contracts/`
    and `specs/` among them, and read by whoever disagrees with the rule: it
    holds the policy's words and no path, so it is true of this plan's
    layout, whatever it is."""
    source = make_source_repo(tmp_path / "Thing", TREE, edits=EDITS)
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT, org=ORG,
                         extra=("--spec-path", spec_path,
                                "--code-path", code_path))
    assert written.returncode == 0, written.stderr + written.stdout
    ruled = [entry for entry in load_yaml(plan)["paths"]
             if entry["rule"] == "spec-governance"]
    assert {str(entry["path"]) for entry in ruled} >= {"contracts/", "specs/"}
    for entry in ruled:
        assert str(entry["reason"]) == spec_governance_reason(), entry
        assert not LEG_PATH.search(str(entry["reason"])), entry
