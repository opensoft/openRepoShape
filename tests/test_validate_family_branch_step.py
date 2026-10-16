# SPDX-License-Identifier: Apache-2.0
"""`validate-family.py`: a remedy that names `family.py add` or `remove`
makes the branch first, and THE LOCKSTEP RULE only where it applies (#539).

THE BRANCH STEP. Since #487 a real `add`, `bump` or `remove` refuses the
holder's tracking branch (`family-on-tracking-branch`) with the `git switch
-c` that makes a branch, and `init` leaves a holder on that branch. Three of
the holder gate's remedies named `add` or `remove` and no branch, so each
cost one refusal first: `member-duplicate-id`'s `remove`, a hand mount's
`member-gitlink-unnamed` `add` (run as printed in
`tests/test_validate_family_unnamed_mounts.py`, now from the tracking
branch), and `member-gitlink-absent`'s `add`. Each named `git -C <holder>
switch -c family/<act>-<member>` first, the branch `family.py` suggests and
the holder's docs show, POSIX-quoted as every line this gate prints is.
Since #681 `member-gitlink-absent` names no `add`, which refuses the row
that is there, and so no branch: it names the index and `.gitmodules`
lines that put the gitlink back, typed in
`tests/test_validate_family_remedies_typed.py`.

THE COUNT. The report ended `<n> finding(s) in family.yaml.` and THE
LOCKSTEP RULE whatever was found; it ends at the rule only where a member's
gitlink and its pin, or the pin's digest, were found out of step.

THE SAME FAMILY AS `tests/test_family.py`, this module's own instance, and
the holder copy `tests/test_family_tracking_branch.py` puts back on its
tracking branch, where a person stands after `init`.
"""

from __future__ import annotations

import importlib.util
import re
import shlex
import sys

import pytest

from conftest import REPO, git, run_script
from repo_shape import PYTHON
from test_family import (  # noqa: F401
    family, family_module, manifest, mount_twice, validate,
)
from test_family_tracking_branch import on_main  # noqa: F401

#: The template every holder's `scripts/validate-family.py` is a copy of.
TEMPLATE = (REPO / "templates" / "family-root" / "scripts" /
            "validate-family.py")

#: How the holder's THE LOCKSTEP RULE starts.
RULE = "THE LOCKSTEP RULE: a member's gitlink and its `members[].pin.commit`"

#: The sentence each remedy that names a `switch -c` ends its prose with
#: where that branch exists already (#607), pinned as text, as `family.py`
#: and the holder's validator both say it.
BRANCH_LEFT = ("If `git switch -c` says that branch already exists, an "
               "earlier act left it: give the branch another name, which "
               "starts it where the holder stands, or, only if that branch "
               "holds work not merged yet, the same command with `switch` "
               "in place of `switch -c` goes back to it and keeps every "
               "commit on it.")


def gate_module(monkeypatch):
    """The template `validate-family.py`, loaded as a module. It puts its
    own `scripts/` on `sys.path`, which is put back afterwards."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    spec = importlib.util.spec_from_file_location(
        "validate_family_branch_step", TEMPLATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def count_line(result) -> str:
    """The line the gate's report ends on."""
    return result.stderr.rstrip("\n").splitlines()[-1]


def switch_argv(holder, verb: str, name: str) -> list[str]:
    """The `git switch -c` a remedy names, as words: `family.py`'s own
    suggestion for `verb` and `name`, in this holder."""
    branch = family_module()._suggested_branch(verb, name)
    return ["git", "-C", str(holder), "switch", "-c", branch]


# --- the branch `family.py` would suggest, spelled the same way --------------

@pytest.mark.parametrize("verb,name", [
    ("add", "IRQS"), ("remove", "irrs"), ("add", "Atlas.Docs"),
    ("add", "My Proj"), ("add", "O'Brien"), ("remove", "x.lock"),
    ("add", "a..b"), ("remove", "-x"),
], ids=["project", "id", "dotted", "space", "quote", "lock", "dots",
        "dash"])
def test_the_switch_names_the_branch_family_py_suggests(monkeypatch, tmp_path,
                                                         verb, name):
    """The branch word is `family.py`'s `_suggested_branch`'s, whatever the
    member is called: a name no branch word spells is said as `member`.
    The holder is quoted for a POSIX shell, as the gate's other lines are."""
    holder = tmp_path / "it's a holder"
    line = gate_module(monkeypatch)._switch_line(holder, verb, name)
    assert shlex.split(line) == switch_argv(holder, verb, name), line


# --- member-duplicate-id: switch, then remove, from the tracking branch -----

def test_the_duplicate_id_remedy_makes_the_branch_then_removes(family,
                                                                on_main):
    """From the tracking branch, the remedy's two commands, run as printed
    from a checkout of openRepoShape: the `switch` makes `family.py`'s own
    branch for the `remove`, and the `remove` then takes the later row out
    on it, where without the branch it is refused."""
    holder = on_main
    mount_twice(holder, family["remotes"])
    found = validate(holder)
    assert found.returncode == 1, found.stderr + found.stdout
    commands = re.findall(r"`([^`]*)`", found.stderr.split(
        "FINDING member-duplicate-id: ", 1)[1].splitlines()[0])
    switch, remove = [command for command in commands
                      if command.startswith(("git -C", PYTHON))]
    assert shlex.split(switch) == switch_argv(holder, "remove", "irrs")
    assert found.stderr.index(switch) < found.stderr.index(remove)
    refused = run_script(REPO / "scripts" / "family.py",
                         *shlex.split(remove)[2:], cwd=REPO)
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert "REFUSED family-on-tracking-branch: " in refused.stderr
    git(*shlex.split(switch)[1:], cwd=holder.parent)
    argv = shlex.split(remove)
    assert argv[:3] == [PYTHON, "scripts/family.py", "remove"], remove
    removed = run_script(REPO / argv[1], *argv[2:], cwd=REPO)
    assert removed.returncode == 0, removed.stderr + removed.stdout
    assert git("symbolic-ref", "--short", "HEAD",
               cwd=holder).stdout.strip() == "family/remove-irrs"
    assert "IRRS2" not in [row["project"]
                           for row in manifest(holder)["members"]]
    assert validate(holder).returncode == 0


# --- member-gitlink-absent: no add, so no branch (#681) ---------------------

def test_a_missing_gitlink_remedy_names_no_add_and_no_branch(on_main):
    """`family.py add` refuses a row that is there
    (`member-already-present`), so the refusal names neither it nor the
    branch it would need. Every line it prints is a `git` line typed in
    the holder."""
    holder = on_main
    git("rm", "-r", "-q", "-f", "--", "members/IRRS", cwd=holder)
    git("commit", "-qm", "Drop the gitlink but keep the row", cwd=holder)
    result = validate(holder)
    assert result.returncode == 2, result.stdout + result.stderr
    lines = result.stderr.splitlines()
    assert lines[0].startswith("REFUSED member-gitlink-absent: "), lines
    assert "switch -c" not in result.stderr, result.stderr
    assert "scripts/family.py add" not in result.stderr, result.stderr
    assert [shlex.split(line)[0] for line in lines[2:]] == ["git"] * 3


# --- the count ends at the rule only where it applies -----------------------

def copy_edited(holder) -> None:
    """A pinned copy edited in place: a lone `shape-copy-drift`."""
    target = holder / "scripts" / "bootstrap.py"
    target.write_bytes(target.read_bytes() + b"\n# edit\n")


def gitlink_moved(holder) -> None:
    """IRRS's gitlink moved alone, staged at an EMPTY commit past its pin,
    so the pin's digest still recomputes: a lone
    `member-gitlink-mismatch`."""
    git("commit", "-q", "--allow-empty", "-m", "The member moved alone",
        cwd=holder / "members" / "IRRS")
    git("add", "--", "members/IRRS", cwd=holder)


def digest_written_wrong(holder) -> None:
    """IRSS's digest written wrong: a lone `member-digest-mismatch`."""
    row = {r["project"]: r for r in manifest(holder)["members"]}["IRSS"]
    text = (holder / "family.yaml").read_bytes()
    (holder / "family.yaml").write_bytes(text.replace(
        row["pin"]["tree_sha256"].encode("ascii"), b"b" * 64, 1))


#: Each lone finding, how it is made, and whether the count ends at the rule.
LONE = {
    "shape-copy-drift": (copy_edited, False),
    "member-duplicate-id": (lambda holder: None, False),
    "member-gitlink-mismatch": (gitlink_moved, True),
    "member-digest-mismatch": (digest_written_wrong, True),
}


@pytest.mark.parametrize("code", sorted(LONE))
def test_the_count_ends_at_the_rule_only_where_it_applies(family, on_main,
                                                          code):
    """A lone `shape-copy-drift`, an edited copy, and a lone
    `member-duplicate-id`, one project pinned twice, end on the count; a
    gitlink and a pin out of step, or a digest, end on the count and THE
    LOCKSTEP RULE."""
    holder = on_main
    make, rule = LONE[code]
    if code == "member-duplicate-id":
        mount_twice(holder, family["remotes"])
    make(holder)
    result = validate(holder)
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stderr.count("FINDING ") == 1, result.stderr
    assert f"FINDING {code}: " in result.stderr
    if rule:
        assert count_line(result).startswith(
            "1 finding(s) in family.yaml. " + RULE), result.stderr
    else:
        assert count_line(result) == "1 finding(s) in family.yaml."
        assert "LOCKSTEP RULE" not in result.stdout + result.stderr
