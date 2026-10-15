# SPDX-License-Identifier: Apache-2.0
"""`family.py add` refuses a member name the holder's own validator refuses
(#366).

TWO TOOLS OF THIS STANDARD DISAGREED about one rule. `add --member` checked
its argument against `MEMBER_RE`, whose character class let an owner or a
project BEGIN with `.`, `_` or `-`; the holder's `validate-family.py` holds a
row's `repository:` to `QUALIFIED_RE`, the same class with a letter or a digit
required first. `add` writes `--member` verbatim as that row, so
`testorg/_Zed`, `testorg/.Zed`, `_org/Zed` and `.org/Zed` were mounted, pinned
and committed with exit 0 and the commit `add` reported failed the gate the
holder ships, as `member-repository`. (`testorg/-Zed` got as far too.
`--member=-org/Zed`, the one way a leading `-` reaches the OWNER, passed the
pattern and was refused later by `checked_value` as `unsafe-value`; the
pattern is asked first now, so it is `member-malformed` like the rest.)

Now `MEMBER_RE` takes `QUALIFIED_RE`'s shape and the name is refused as
`member-malformed` BEFORE THE MEMBER IS READ: exit 2, nothing on stdout (the
first line `add` prints says it is checking the member), no `gh` call and no
throwaway clone, the holder byte for byte as it was. A name with a `.`, `_` or
`-` anywhere after the first character is still a name, and still adds.

ONE RULE, THREE SPELLINGS, AND A TEST THAT HOLDS THEM TOGETHER. `QUALIFIED_RE`
is spelled in the family root's `validate-family.py` and the assembly root's
`validate-manifest.py`, and both copies ship into projects that run them from
their own copy of `repo_shape.py`. A constant moved into `repo_shape.py` would
reach an existing holder only through `update-shape.py`, so `family.py`, which
runs from the standard's checkout, spells it a third time. The pinned-equality
test below finds every spelling by READING the source and fails when any
differs: a person who changes the rule in one place is told about the rest.

THE MEMBERS ARE `IRQS`, the family fixture's spare, copied into a bare
repository under each name a test needs (the issue's own repro does the same
with `Zed`), so `add` has a real remote to read under every spelling: a
refusal here is for the NAME, never for a missing remote. Same family, rules
and offline environment as `test_family.py`, `test_family_add_refusals.py` and
`test_family_member_path.py`: nothing is created on GitHub, a `gh` on PATH
logs and exits 97, and the operator's git configuration is a file of the
test's own.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from conftest import REPO, cloned_just_pushed, git, run_script
from test_family import (  # noqa: F401
    FAMILY, ORG, SPARE, family, family_module, manifest, validate,
)
from test_family_add_refusals import holder, offline, refusal  # noqa: F401
from test_family_member_path import commits, committed, isolated, state

#: `--member` spellings the holder's validator refuses and `add` used to
#: write: each segment's first character, in each position, and `.github`,
#: whose comment kept the class loose "for" it. A row naming
#: `testorg/.github` is refused by the validator as well, so nothing a holder
#: can keep depended on `add` admitting it. Every project here has a bare
#: remote of the same name (`remotes_for`), so only the name is wrong.
REFUSED = {
    "project-underscore": f"{ORG}/_{SPARE}",
    "project-dot": f"{ORG}/.{SPARE}",
    "project-hyphen": f"{ORG}/-{SPARE}",
    "owner-underscore": f"_{ORG}/{SPARE}",
    "owner-dot": f".{ORG}/{SPARE}",
    "owner-hyphen": f"-{ORG}/{SPARE}",
    "project-dot-github": f"{ORG}/.github",
}

#: Names with a `.`, `_` or `-` after their first character: the controls.
ADDED = {
    "project-inner-dot": f"{ORG}/IR.QS",
    "project-inner-underscore": f"{ORG}/IR_QS",
    "project-inner-hyphen": f"{ORG}/IR-QS",
    "owner-inner-dot": f"Ink.Router/{SPARE}",
}

#: The remotes `remotes_for` makes: a bare copy of the spare member under each
#: project name the two tables above use, `IRQS` itself included.
PROJECTS = sorted({spelling.partition("/")[2]
                   for spelling in (*REFUSED.values(), *ADDED.values())})


def remotes_for(family, tmp_path: Path) -> Path:
    """A directory of bare remotes, one `<project>.git` per name in
    `PROJECTS`, each a copy of the spare member's own. `add
    --local-remote-dir` takes the member's repository from
    `<dir>/<project>.git`, whatever the owner is called."""
    remotes = tmp_path / "remotes"
    remotes.mkdir()
    for project in PROJECTS:
        cloned_just_pushed(family["remotes"] / f"{SPARE}.git",
                           remotes / f"{project}.git", bare=True)
    return remotes


def add(holder: Path, spelling: str, remotes: Path, env: dict):
    """`family.py add --member=<spelling>`: the `=` form, because a spelling
    that begins with `-` is read by `argparse` as an option in the other."""
    return run_script(FAMILY, "add", "--family-root", str(holder),
                      f"--member={spelling}", "--local-remote-dir",
                      str(remotes), env=env)


# --- the refusal ------------------------------------------------------------

@pytest.mark.parametrize("spelling", REFUSED.values(), ids=REFUSED)
def test_add_refuses_a_name_the_validator_refuses_before_reading_the_member(
        family, holder, offline, tmp_path, spelling):
    """Exit 2, `member-malformed`, not one line on stdout (`checking ...
    before mounting it` comes first otherwise), no `gh` call, no throwaway
    clone left, and the holder as it was: the same HEAD, index entries and
    status, byte for byte, and no row, mount or registration of the name."""
    env = isolated(offline, tmp_path)
    remotes = remotes_for(family, tmp_path)
    before = state(holder, env)

    result = add(holder, spelling, remotes, env)

    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == "", "refused before the member was even read"
    said, remedy = refusal(result.stderr)
    assert said == (
        f"REFUSED member-malformed: --member {spelling!r} is not "
        "`<org>/<Project>`: each name begins with a letter or a digit and "
        "goes on with letters, digits, `.`, `_` and `-`")
    assert remedy.startswith("Remediation: name the owner")
    assert "begin neither name with `.`, `_` or `-`" in remedy
    assert state(holder, env) == before
    assert not (holder / "members" / spelling.partition("/")[2]).exists()
    offline.assert_left_nothing()


# --- the control ------------------------------------------------------------

@pytest.mark.parametrize("spelling", ADDED.values(), ids=ADDED)
def test_a_name_with_a_dot_underscore_or_hyphen_after_its_first_character_adds(
        family, holder, offline, tmp_path, spelling):
    """A name is not refused for HOLDING one of the three, only for beginning
    with it: still ONE commit of `.gitmodules`, the mount and `family.yaml`,
    the row naming the argument verbatim, and the holder's own
    `validate-family.py` passing over it."""
    env = isolated(offline, tmp_path)
    remotes = remotes_for(family, tmp_path)
    project = spelling.partition("/")[2]
    was = commits(holder, env)

    result = add(holder, spelling, remotes, env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert commits(holder, env) == was + 1
    assert committed(holder, env) == {".gitmodules", "family.yaml",
                                      f"members/{project}"}
    rows = {row["project"]: row for row in manifest(holder)["members"]}
    assert rows[project]["repository"] == spelling
    gate = validate(holder)
    assert gate.returncode == 0, gate.stdout + gate.stderr
    assert not offline.gh_log.exists(), offline.gh_log.read_text()


# --- one rule, three spellings ----------------------------------------------

#: Where the rule is spelled today, and under which name. The first is what
#: `add` holds a `--member` to; the other two are what a holder and an
#: assembly root hold a row's `repository:` and a manifest's to.
SPELLINGS = {
    "scripts/family.py": "MEMBER_RE",
    "templates/family-root/scripts/validate-family.py": "QUALIFIED_RE",
    "templates/assembly-root/scripts/validate-manifest.py": "QUALIFIED_RE",
}


def pattern_spelled(source: bytes, name: str) -> list[str]:
    """The pattern of every module-level `<name> = re.compile(r"...")` in
    `source`, READ and never run: the two validators import a sibling
    `repo_shape.py` of their own, and a test that executed them would be
    testing whatever that import found. A spelling this cannot read as ONE
    string literal and no flags is a failure to say so, never a skip."""
    found = []
    for node in ast.parse(source).body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == name):
            continue
        call = node.value
        assert (isinstance(call, ast.Call) and not call.keywords
                and len(call.args) == 1
                and isinstance(call.args[0], ast.Constant)
                and isinstance(call.args[0].value, str)
                and ast.unparse(call.func) == "re.compile"), (
            f"{name} is not `re.compile(<one string>)`: {ast.unparse(node)}")
        found.append(call.args[0].value)
    return found


def every_spelling() -> dict[str, str]:
    """`{path: pattern}`: the three places above, and any OTHER tracked
    module (outside `tests/`) that spells `QUALIFIED_RE`, so a fourth copy is
    pinned the day it is written rather than the day someone remembers it."""
    listed = git("ls-files", "-z", "--", "*.py", cwd=REPO).stdout
    paths = sorted(p for p in listed.split("\0") if p
                   and not p.startswith("tests/"))
    spelled: dict[str, str] = {}
    for path in paths:
        source = (REPO / path).read_bytes()
        names = [SPELLINGS[path]] if path in SPELLINGS else ["QUALIFIED_RE"]
        for name in names:
            patterns = pattern_spelled(source, name)
            assert len(patterns) <= 1, f"{path} spells {name} twice"
            if patterns:
                spelled[path] = patterns[0]
    return spelled


def test_every_spelling_of_the_member_name_rule_is_the_same_pattern():
    """`MEMBER_RE` and both `QUALIFIED_RE` copies are ONE rule. The three
    expected places must each be found (a rename that hid one would otherwise
    leave this test checking two), and every spelling found is the same
    string. To change the rule, change them together."""
    spelled = every_spelling()
    gone = sorted(set(SPELLINGS) - set(spelled))
    assert not gone, (
        f"a spelling of the rule is gone: {gone} -- if it moved, update "
        "SPELLINGS; if it was deleted, so is this pin")
    assert len(set(spelled.values())) == 1, (
        "the member-name rule is spelled differently in:\n" + "\n".join(
            f"  {path}: {pattern}"
            for path, pattern in sorted(spelled.items())))


#: Names the one rule must judge the same everywhere it is spelled: the five
#: of the issue, `.github` and `...`, the leading `-` an option would carry,
#: and the shapes that were never names at all, against names with a `.`,
#: `_` or `-` after the first character.
ACCEPTED = [f"{ORG}/{SPARE}", "testorg/Ze.d", "testorg/Zed_", "testorg/Zed-",
            "Ink.Router/Zed", "a/b", "9/9"]
NOT_ACCEPTED = ["testorg/_Zed", "testorg/.Zed", "testorg/-Zed", "_org/Zed",
                ".org/Zed", "-org/Zed", "testorg/.github", "testorg/...",
                "testorg/.", "testorg/..", "./Zed", "../Zed", "/Zed",
                "testorg/", "testorg", "a/b/c", ""]


def test_every_spelling_judges_a_corpus_of_names_alike():
    """The strings above are one pattern; this says what that pattern MEANS,
    so a reader sees the rule and a change that keeps the spellings equal but
    moves the rule (to admit `.github`, say) has to move this too."""
    spelled = every_spelling()
    assert spelled, "premise: at least one spelling was found"
    for path, pattern in spelled.items():
        rule = re.compile(pattern)
        for name in ACCEPTED:
            assert rule.match(name), f"{path} refuses {name!r}"
        for name in NOT_ACCEPTED:
            assert not rule.match(name), f"{path} admits {name!r}"
    module = family_module()
    for name in ACCEPTED:
        assert module._checked_member(name)[0] == name
