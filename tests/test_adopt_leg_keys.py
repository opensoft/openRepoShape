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
import re
import stat
import sys
import textwrap
from pathlib import Path

import pytest

from conftest import (ADOPT, ORG, REPO, git, make_source_repo, run_script,
                      write_plan)
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

#: A `gh` that creates a bare repository for `repo create`, takes `repo edit`,
#: and logs every argument of a `pr create`, NUL-separated, so the body is read
#: back as it was given. Anything else is refused: it reaches nothing.
STUB_GH = textwrap.dedent("""\
    #!/bin/sh
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


def adopt_after_the_hand_edit(base: Path, plan_time: tuple, *,
                              github: bool) -> dict:
    """Plan `plan_time`, edit the two keys to EDITED_*, `check`, then
    `execute`. Returns what each surface said of the follow-ups: `check`'s
    `follow-up:` lines, the split commit's message and, against GitHub, the
    body `gh pr create` was given."""
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
    edit_the_mounts(plan, plan_time, (EDITED_SPEC, EDITED_CODE))

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
    assert f"path = {EDITED_SPEC}\n" in mounts, mounts
    assert f"path = {EDITED_CODE}\n" in mounts, mounts
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
