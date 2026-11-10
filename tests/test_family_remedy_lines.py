# SPDX-License-Identifier: Apache-2.0
"""The lines of `family.py`'s own that `bump`'s `member-unknown` and `add`'s
`member-already-present` print run as printed, from the branch a fresh clone
stands on (#1127, RV1117's follow-ups on #1117).

RV1117's review of #1117 found seven things about these remedies, and each
is measured here as the remedy now prints it:

* N1: on the holder's tracking branch, where `init` and a fresh clone leave
  a person, the `add` that `member-unknown` names was refused
  `family-on-tracking-branch`. So was the `bump` that `member-already-present`
  names (found by measuring it): both refusals are said before
  `_checked_branch` reads the branch. Each remedy now says the line runs on
  a branch other than the tracking branch and names the `git switch -c` that
  makes one, as the holder's `validate-family.py` says before its `remove`,
  then `BRANCH_LEFT` (#607). Typed in order from the tracking branch, the
  switch, then the line, each act goes through; the line alone is refused.
* N2: the lines began with a bare `family.py`, which runs only from
  `scripts/`. Each now begins as `init`'s NEXT STEPS' `add` does: the
  interpreter, then the path that reaches the file from where the refused
  run stood, and is typed here from that folder by that path.
* N3: `member-unknown`'s `add` left `<org>` blank where `family.yaml`'s
  `org:` is known, a redirection in every shell when pasted. The owner is
  now the one `--member` was typed with, else the family's `org:`, else the
  blank, each only where `<owner>/<project>` is a `--member` `add` takes.
* N4: the row's `--member` name was printed raw: a row `IR RS` was two
  words. It is now one, quoted for the reader's shell.
* N6: a holder under a folder whose name holds a backtick closed the
  remedy's backticks inside its path. A command that holds one is now
  printed bare.
* N7: `member-already-present` said "`remove` takes it out" with no line to
  type. It now prints the `remove` line beside the `bump` line, and both are
  typed here.

N5, the README sentence's list of verbs tied to `NAMED`, is
`tests/test_readme_windows_quoting_sentence.py`'s. The holder is
`tests/test_family.py`'s family, copied and put back on its tracking branch
as `tests/test_family_tracking_branch.py` does; its spare member `IRQS` is
in its remotes and not in the holder. No network: `gh` is a shim that exits
non-zero.

Three more lines, from lane 5's review of #1201 (#1228), are measured the
same way. Each was reached with no branch read, and named none:

* `add --dry-run`'s `member-duplicate-id`, for `IRRS2`, a renamed copy of
  the pinned `IRRS` (`tests/test_family_add_member_id.py`'s), and
* `bump --dry-run`'s, for a `--to` whose `project.yaml` records the
  neighbour's id (`tests/test_family_bump_to_checks.py`'s). A dry run asks
  no branch, so each now names the one its lines need, the branch the
  `remove` line's own refusal names, then `BRANCH_LEFT`; the real runs ask
  them after `_checked_branch`, and their words are pinned unchanged in
  those two files.
* `init`'s `family-holder-already-here`, whose `add` stands on the holder
  `init` made, on its tracking branch. It now comes after `init`'s own
  `switch -c family/add-<Project>`, and is `_cited` (N6).

The branch each dry run's clause names is made from the row's `id:`, and
not from its name: a row renamed by hand, whose name is not its id
lowercased, tells the two apart (RV1264's NIT-2 on #1264).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import git, refusal_detail, run_script
from repo_shape import PYTHON, shell_quoted
#: The family fixture and its names, the offline environment and the
#: helpers of the tests that already trigger these codes, imported from the
#: modules that own them rather than rebuilt.
from test_family import (  # noqa: F401
    FAMILY, MEMBERS, NAME, ORG, SPARE, family, manifest, validate,
)
from test_family_add_member_id import DUPLICATE_ID, RENAMED, renamed_copy
from test_family_add_refusals import offline, refusal  # noqa: F401
from test_family_bump_to_checks import (
    duplicate_id_refusal, records_the_neighbours_id,
)
from test_family_dry_run import commit_in_mount, isolated
from test_family_printed_quoting import copied_holder, family_lead, host_words
from test_family_tracking_branch import TRACKING, older_commit
#: The sentence every remedy that names a `switch -c` ends with (#607).
from test_validate_family_branch_step import BRANCH_LEFT

#: A commit id for a `--to` that is never read: `member-unknown` is said
#: before `--to` is.
COMMIT = "0123456789abcdef0123456789abcdef01234567"

#: The pinned member `add` is refused for, by the row's name, and its
#: neighbour, whose id `bump --dry-run`'s `--to` records (#1228).
PINNED, NEIGHBOUR = MEMBERS

#: What the remedies say before the line of `family.py` they name, with the
#: verbs the tracking branch is refused by.
OFF_TRACKING = ("on a branch other than the holder's tracking branch, which "
                "{refuses} ({switch} makes one), ")


def on_tracking(family, base: Path) -> Path:
    """A private copy of the holder under `base`, back on its tracking
    branch with every member the fixture added: where `init` leaves a
    person, and where a fresh clone stands."""
    holder = copied_holder(family, base)
    git("switch", "-q", "-C", TRACKING, cwd=holder)
    assert git("status", "--porcelain", cwd=holder).stdout == ""
    return holder


@pytest.fixture
def stand(tmp_path) -> Path:
    """The folder a person runs the refused command from, and types its
    remedy in: not the holder's, and not the standard's, with a space in its
    name."""
    folder = tmp_path / "my desk"
    folder.mkdir()
    return folder.resolve()


def cited(command: str, ticked: bool) -> str:
    return f"`{command}`" if ticked else command


def switch_line(holder: Path, branch: str) -> str:
    return f"git -C {shell_quoted(holder)} switch -c {branch}"


def family_line(lead: str, verb: str, holder: Path, member: str) -> str:
    """`<lead><verb> --family-root <holder> --member <member>`, where
    `member` is already spelled for the shell."""
    return (f"{lead}{verb} --family-root {shell_quoted(holder)} "
            f"--member {member}")


def unknown_remediation(holder: Path, lead: str, ticked: bool = True) -> str:
    """What `bump --member IRQS` is told: make a branch, then the `add` that
    puts IRQS in the family, owned by the family's `org:`."""
    add = family_line(lead, "add", holder, shell_quoted(f"{ORG}/{SPARE}"))
    switch = switch_line(holder, f"family/add-{SPARE.lower()}")
    clause = OFF_TRACKING.format(refuses="`add` refuses",
                                 switch=cited(switch, ticked))
    return (f"Remediation: {clause}{cited(add, ticked)} puts it in the "
            f"family first. {BRANCH_LEFT}")


def present_remediation(holder: Path, lead: str, ticked: bool = True) -> str:
    """What `add` of the member the holder already pins is told: make a
    branch, then the `bump` that moves the row, or the `remove` that takes
    it out."""
    name = shell_quoted(PINNED)
    bump = family_line(lead, "bump", holder, name) + " --to <commit>"
    remove = family_line(lead, "remove", holder, name)
    switch = switch_line(holder, f"family/bump-{PINNED.lower()}")
    clause = OFF_TRACKING.format(refuses="`bump` and `remove` refuse",
                                 switch=cited(switch, ticked))
    return (f"Remediation: {clause}{cited(bump, ticked)} moves an existing "
            f"member and {cited(remove, ticked)} takes it out. Adding it "
            f"twice is not a way to move it. {BRANCH_LEFT}")


def add_dry_duplicate_remediation(holder: Path, lead: str) -> str:
    """What `add --dry-run` of `IRRS2`, whose `project.yaml` records the id
    the row `IRRS` pins, is told (#1228): the branch first, the one
    `remove`'s own refusal names, then the `remove` and the `bump` the real
    run names, then `BRANCH_LEFT`."""
    name = shell_quoted(PINNED)
    remove = family_line(lead, "remove", holder, name)
    bump = family_line(lead, "bump", holder, name) + " --to <commit>"
    switch = switch_line(holder, f"family/remove-{PINNED.lower()}")
    clause = OFF_TRACKING.format(refuses="`bump` and `remove` refuse",
                                 switch=f"`{switch}`")
    return (f"Remediation: a family pins each project once. If "
            f"{ORG}/{RENAMED} is {ORG}/{PINNED} renamed at the forge, "
            f"{clause}`{remove}` takes the old row out and this `add` then "
            f"pins it under the new name; `{bump}` moves the row that is "
            "there instead. Two projects that record one id are a fault in "
            "one of their `project.yaml` files, mended in that project, not "
            f"in the family. {BRANCH_LEFT}")


def bump_dry_duplicate_remediation(holder: Path, lead: str) -> str:
    """What `bump --dry-run` of `IRRS` to a commit whose `project.yaml`
    records the id of `IRSS` is told (#1228): the branch first, the one
    `remove`'s own refusal names, then the `remove` the real run names,
    then `BRANCH_LEFT`."""
    remove = family_line(lead, "remove", holder, shell_quoted(NEIGHBOUR))
    switch = switch_line(holder, f"family/remove-{NEIGHBOUR.lower()}")
    clause = OFF_TRACKING.format(refuses="`remove` refuses",
                                 switch=f"`{switch}`")
    return (f"Remediation: a family pins each project once. Pass `--to` a "
            f"commit of {ORG}/{PINNED} whose project.yaml records an id no "
            f"other row records. If {ORG}/{PINNED} and {ORG}/{NEIGHBOUR} are "
            f"one project, {clause}`{remove}` takes the other row out first. "
            "Two projects that record one id are a fault in one of their "
            "`project.yaml` files, mended in that project, not in the "
            f"family. {BRANCH_LEFT}")


def holder_here_remediation(holder: Path, lead: str,
                            ticked: bool = True) -> str:
    """What `init` run again over the family folder it made is told
    (#1228): `init`'s own branch, its `<Project>` bare as the NEXT STEPS
    print it, then `init`'s own `add`, then `BRANCH_LEFT`."""
    switch = switch_line(holder, "family/add-<Project>")
    add = family_line(lead, "add", holder, f"{shell_quoted(ORG)}/<Project>")
    clause = OFF_TRACKING.format(refuses="`add` refuses",
                                 switch=cited(switch, ticked))
    return (f"Remediation: {clause}{cited(add, ticked)} grows it, and `make "
            "siblings` in the holder puts each member's working clone beside "
            f"it. There is no --force. {BRANCH_LEFT}")


def bump_unknown(holder: Path, stand: Path, env: dict, member: str = SPARE):
    """`bump` of a member the holder does not pin, typed in `stand`."""
    return run_script(FAMILY, "bump", "--family-root", str(holder),
                      "--member", member, "--to", COMMIT, cwd=stand, env=env)


def add_present(family, holder: Path, stand: Path, env: dict):
    """`add` of the member the holder already pins, typed in `stand`."""
    return run_script(FAMILY, "add", "--family-root", str(holder),
                      "--member", f"{ORG}/{PINNED}", "--local-remote-dir",
                      str(family["remotes"]), cwd=stand, env=env)


def typed(line: str, stand: Path, env: dict, *extra: str):
    """`line` typed in `stand` as the reader's shell reads it: the
    interpreter it names, and the script by the path it names from there.

    THE INTERPRETER IS ASSERTED, NOT LOOKED UP (RV1201's NIT-2 on #1201):
    the line's first word must be `PYTHON`, and the script then runs under
    this test's own interpreter (`run_script`). So a row proves the words a
    shell reads and the script they reach, not that the reader's PATH has
    a `PYTHON`."""
    words = host_words(line)
    assert words[0] == PYTHON, line
    return run_script(Path(words[1]), *words[2:], *extra, cwd=stand, env=env)


def switched(line: str, stand: Path) -> None:
    """The remedy's `git switch -c`, typed in `stand` as the shell reads
    it."""
    words = host_words(line)
    assert words[:2] == ["git", "-C"], line
    git(*words[1:], cwd=stand)


def branch_of(holder: Path) -> str:
    return git("symbolic-ref", "--short", "HEAD", cwd=holder).stdout.strip()


def rows_of(holder: Path) -> dict:
    return {row["project"]: row for row in manifest(holder)["members"]}


# --- N1, N2: member-unknown's `add`, from the tracking branch ----------------

def test_member_unknowns_add_runs_as_printed_from_the_tracking_branch(
        family, offline, stand, tmp_path):
    """The remediation, word for word: the branch first, then the `add` by
    the interpreter and the path from where the refused `bump` stood, the
    owner filled in. Typed alone on the tracking branch the `add` is refused
    there, as the remedy says; typed after its `switch -c`, from the same
    folder, it puts IRQS in the family on that branch, and the holder is
    clean and its gate green."""
    env = isolated(offline, tmp_path)
    holder = on_tracking(family, tmp_path / "holders")
    lead = family_lead(stand)
    refused = bump_unknown(holder, stand, env)
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert refusal(refused.stderr) == (
        f"REFUSED member-unknown: {SPARE} is not a member of {NAME}",
        unknown_remediation(holder, lead))
    switch = switch_line(holder, f"family/add-{SPARE.lower()}")
    add = family_line(lead, "add", holder, shell_quoted(f"{ORG}/{SPARE}"))
    remotes = ("--local-remote-dir", str(family["remotes"]))

    alone = typed(add, stand, env, *remotes)
    assert alone.returncode == 2, alone.stdout + alone.stderr
    assert alone.stderr.startswith("REFUSED family-on-tracking-branch: ")
    assert SPARE not in rows_of(holder)

    switched(switch, stand)
    done = typed(add, stand, env, *remotes)
    assert done.returncode == 0, done.stdout + done.stderr
    assert branch_of(holder) == f"family/add-{SPARE.lower()}"
    rows = rows_of(holder)
    assert sorted(rows) == sorted([*MEMBERS, SPARE])
    assert rows[SPARE]["repository"] == f"{ORG}/{SPARE}"
    assert git("status", "--porcelain", cwd=holder).stdout == ""
    assert validate(holder).returncode == 0


# --- N1b, N2, N7: member-already-present's `bump` and `remove` ---------------

@pytest.mark.parametrize("verb", ["bump", "remove"])
def test_member_already_presents_lines_run_as_printed_from_the_tracking_branch(
        family, offline, stand, tmp_path, verb):
    """The remediation, word for word: the branch first, then a `bump` line
    and a `remove` line, each by the interpreter and the path from where the
    refused `add` stood. Typed alone on the tracking branch each is refused
    there; typed after the `switch -c`, `bump` (its `<commit>` filled in)
    moves the row's pin and `remove` takes the row out, and the holder is
    clean and its gate green."""
    env = isolated(offline, tmp_path)
    holder = on_tracking(family, tmp_path / "holders")
    lead = family_lead(stand)
    refused = add_present(family, holder, stand, env)
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert refusal(refused.stderr) == (
        f"REFUSED member-already-present: {PINNED} is already a member of "
        f"{NAME}: the row {PINNED} pins {ORG}/{PINNED}",
        present_remediation(holder, lead))
    line = family_line(lead, verb, holder, PINNED)
    older = older_commit(family, PINNED)
    if verb == "bump":
        line += f" --to {older}"
    before = rows_of(holder)

    alone = typed(line, stand, env)
    assert alone.returncode == 2, alone.stdout + alone.stderr
    assert alone.stderr.startswith("REFUSED family-on-tracking-branch: ")
    assert rows_of(holder) == before

    switched(switch_line(holder, f"family/bump-{PINNED.lower()}"), stand)
    done = typed(line, stand, env)
    assert done.returncode == 0, done.stdout + done.stderr
    assert branch_of(holder) == f"family/bump-{PINNED.lower()}"
    rows = rows_of(holder)
    if verb == "bump":
        assert sorted(rows) == sorted(MEMBERS)
        assert rows[PINNED]["pin"]["commit"] == older
    else:
        assert sorted(rows) == sorted(MEMBERS[1:])
    assert git("status", "--porcelain", cwd=holder).stdout == ""
    assert validate(holder).returncode == 0


# --- N3: the owner of member-unknown's `add` ---------------------------------

def without_org(text: str) -> str:
    edited = re.sub(r"(?m)^org: .*\n", "", text, count=1)
    assert edited != text, "premise: family.yaml has an `org:` line"
    return edited


def org_of(value: str):
    """An edit of `family.yaml` that gives `org:` the YAML `value`."""
    def edit(text: str) -> str:
        edited = re.sub(r"(?m)^org: .*$", f"org: {value}", text, count=1)
        assert edited != text, "premise: family.yaml has an `org:` line"
        return edited
    return edit


#: `(--member as typed, an edit of family.yaml, the --member the line names)`:
#: the typed owner first, then the family's `org:`, then the blank, each
#: only where `<owner>/<project>` is a `--member` `add` takes.
OWNERS = {
    "the-familys-org": (SPARE, None, shell_quoted(f"{ORG}/{SPARE}")),
    "the-typed-owner": (f"OtherOrg/{SPARE}", None,
                        shell_quoted(f"OtherOrg/{SPARE}")),
    "a-typed-owner-add-refuses": (f"_Other/{SPARE}", None,
                                  shell_quoted(f"{ORG}/{SPARE}")),
    "no-org": (SPARE, without_org, f"<org>/{shell_quoted(SPARE)}"),
    "an-empty-org": (SPARE, org_of('""'), f"<org>/{shell_quoted(SPARE)}"),
    "an-org-add-refuses": (SPARE, org_of('"Ink Router"'),
                           f"<org>/{shell_quoted(SPARE)}"),
    "no-org-but-typed": (f"OtherOrg/{SPARE}", without_org,
                         shell_quoted(f"OtherOrg/{SPARE}")),
}


@pytest.mark.parametrize("typed_member, edit, expected", OWNERS.values(),
                         ids=OWNERS)
def test_member_unknowns_add_names_the_owner_where_it_is_known(
        family, offline, stand, tmp_path, typed_member, edit, expected):
    """The `--member` of the `add` line: `<org>` is a blank only where
    neither the typed `--member` nor `family.yaml` gives an owner `add`
    takes, and the value is one word for the reader's shell."""
    env = isolated(offline, tmp_path)
    holder = on_tracking(family, tmp_path / "holders")
    if edit is not None:
        path = holder / "family.yaml"
        path.write_text(edit(path.read_text(encoding="utf-8")),
                        encoding="utf-8")
    refused = bump_unknown(holder, stand, env, typed_member)
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert refused.stderr.startswith("REFUSED member-unknown: ")
    lead = family_lead(stand)
    found = re.findall(rf"`{re.escape(lead)}(add [^`]*)`", refused.stderr)
    assert found == [f"add --family-root {shell_quoted(holder)} --member "
                     f"{expected}"]


# --- N4: a row's name is one word --------------------------------------------

def renamed_by_hand(holder: Path, project: str, name: str) -> None:
    """Edit the `project:` of the row that pins `project` to `name` and
    commit it, as a person editing `family.yaml` by hand would. The row
    keeps its `id:`, which is `project` lowercased: every other row's id
    is its name lowercased, so only a row like this tells the two apart."""
    path = holder / "family.yaml"
    text = path.read_text(encoding="utf-8")
    edited = re.sub(rf'(?m)^(  - project: )"?{project}"?$', rf'\1"{name}"',
                    text, count=1)
    assert edited != text, "premise: the row's `project:` line"
    path.write_text(edited, encoding="utf-8")
    git("commit", "-q", "-m", "A row named by hand", "--", "family.yaml",
        cwd=holder)
    assert rows_of(holder)[name]["id"] == project.lower(), (
        "premise: the row keeps its id")


def test_a_rows_name_with_a_space_is_one_word_in_both_lines(
        family, offline, stand, tmp_path):
    """A row whose `project:` holds a space, edited by hand and committed:
    `add` of the repository it pins names it in its `bump` and `remove`
    lines as ONE word, the row's name whole. The branch the clause names
    is made from the row's `id:`, which is still `irrs`, and not from its
    name, which would make `family/bump-member` (RV1201's NIT-1 on #1201:
    every other row's id is its name lowercased)."""
    env = isolated(offline, tmp_path)
    holder = on_tracking(family, tmp_path / "holders")
    renamed_by_hand(holder, PINNED, "IR RS")
    refused = add_present(family, holder, stand, env)
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert refused.stderr.startswith("REFUSED member-already-present: ")
    lead = family_lead(stand)
    lines = re.findall(rf"`{re.escape(lead)}((?:bump|remove) [^`]*)`",
                       refused.stderr)
    assert [host_words(line) for line in lines] == [
        ["bump", "--family-root", str(holder), "--member", "IR RS", "--to",
         "<commit>"],
        ["remove", "--family-root", str(holder), "--member", "IR RS"]]
    assert re.findall(r"`(git -C [^`]*)`", refused.stderr) == [
        switch_line(holder, f"family/bump-{PINNED.lower()}")]


# --- N6: a holder under a folder named with a backtick -----------------------

def test_a_command_holding_a_backtick_is_printed_bare(
        family, offline, stand, tmp_path):
    """Under `a`b/`, every command each remedy names holds the backtick, so
    each is printed bare and the prose around it is the same; the `add`
    `member-unknown` names, typed after its switch, still puts IRQS in the
    family."""
    env = isolated(offline, tmp_path)
    holder = on_tracking(family, tmp_path / "a`b")
    assert "`" in str(holder), "premise: the holder's path holds a backtick"
    lead = family_lead(stand)

    present = add_present(family, holder, stand, env)
    assert present.returncode == 2, present.stdout + present.stderr
    assert refusal(present.stderr)[1] == present_remediation(
        holder, lead, ticked=False)

    unknown = bump_unknown(holder, stand, env)
    assert unknown.returncode == 2, unknown.stdout + unknown.stderr
    assert refusal(unknown.stderr)[1] == unknown_remediation(
        holder, lead, ticked=False)
    switched(switch_line(holder, f"family/add-{SPARE.lower()}"), stand)
    done = typed(family_line(lead, "add", holder,
                             shell_quoted(f"{ORG}/{SPARE}")),
                 stand, env, "--local-remote-dir", str(family["remotes"]))
    assert done.returncode == 0, done.stdout + done.stderr
    assert SPARE in rows_of(holder)
    assert git("status", "--porcelain", cwd=holder).stdout == ""


# --- #1228: the lines reached with no branch read ----------------------------

def add_renamed(holder: Path, remotes: Path, stand: Path, env: dict,
                *extra: str):
    """`add` of `IRRS2`, the pinned `IRRS` renamed at the forge, typed in
    `stand`, reading the member from `remotes`."""
    return run_script(FAMILY, "add", *extra, "--family-root", str(holder),
                      "--member", f"{ORG}/{RENAMED}", "--local-remote-dir",
                      str(remotes), cwd=stand, env=env)


@pytest.mark.parametrize("verb", ["remove", "bump"])
def test_add_dry_runs_duplicate_id_lines_run_from_the_tracking_branch(
        family, offline, stand, tmp_path, verb):
    """(a) `add --dry-run` reads no branch, so on the tracking branch it is
    refused `member-duplicate-id` for `IRRS2`. Its remediation, word for
    word: the branch the `remove` line's own refusal names, then the
    `remove` and the `bump` lines, then `BRANCH_LEFT`. Typed alone there,
    each line is refused `family-on-tracking-branch`; typed after the
    `switch -c`, `remove` takes the old row out and the refused `add`, run
    for real, then pins `IRRS2`, or `bump` (its `<commit>` filled in) moves
    the row, and the holder is clean and its gate green."""
    env = isolated(offline, tmp_path)
    holder = on_tracking(family, tmp_path / "holders")
    remotes = renamed_copy(family, tmp_path)
    lead = family_lead(stand)
    refused = add_renamed(holder, remotes, stand, env, "--dry-run")
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert refusal(refused.stderr) == (
        DUPLICATE_ID.format(who=RENAMED, after=""),
        add_dry_duplicate_remediation(holder, lead))
    line = family_line(lead, verb, holder, PINNED)
    older = older_commit(family, PINNED)
    if verb == "bump":
        line += f" --to {older}"
    before = rows_of(holder)

    alone = typed(line, stand, env)
    assert alone.returncode == 2, alone.stdout + alone.stderr
    assert alone.stderr.startswith("REFUSED family-on-tracking-branch: ")
    assert rows_of(holder) == before

    switched(switch_line(holder, f"family/remove-{PINNED.lower()}"), stand)
    done = typed(line, stand, env)
    assert done.returncode == 0, done.stdout + done.stderr
    assert branch_of(holder) == f"family/remove-{PINNED.lower()}"
    if verb == "bump":
        assert rows_of(holder)[PINNED]["pin"]["commit"] == older
    else:
        added = add_renamed(holder, remotes, stand, env)
        assert added.returncode == 0, added.stdout + added.stderr
        assert sorted(rows_of(holder)) == sorted([RENAMED, NEIGHBOUR])
    assert git("status", "--porcelain", cwd=holder).stdout == ""
    assert validate(holder).returncode == 0


def test_bump_dry_runs_duplicate_id_remove_runs_from_the_tracking_branch(
        family, offline, stand, tmp_path):
    """(b) `bump --dry-run` of `IRRS` to a pushed commit whose
    `project.yaml` records the id of `IRSS` reads no branch before the id,
    so on the tracking branch it is refused `member-duplicate-id`. Its
    remediation, word for word: the branch the `remove` line's own refusal
    names, then the `remove` line, then `BRANCH_LEFT`. Typed alone there,
    the `remove` is refused `family-on-tracking-branch`; typed after the
    `switch -c`, it takes `IRSS` out, the refused `bump`, run for real,
    then pins that commit, and the holder is clean and its gate green."""
    env = isolated(offline, tmp_path)
    holder = on_tracking(family, tmp_path / "holders")
    to = commit_in_mount(holder, env, lambda mount: records_the_neighbours_id(
        mount / "project.yaml"))
    lead = family_lead(stand)

    def bump(*extra: str):
        return run_script(FAMILY, "bump", *extra, "--family-root",
                          str(holder), "--member", PINNED, "--to", to,
                          cwd=stand, env=env)

    refused = bump("--dry-run")
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert refusal(refused.stderr) == (
        duplicate_id_refusal(to, holder)[0],
        bump_dry_duplicate_remediation(holder, lead))
    line = family_line(lead, "remove", holder, NEIGHBOUR)

    alone = typed(line, stand, env)
    assert alone.returncode == 2, alone.stdout + alone.stderr
    assert alone.stderr.startswith("REFUSED family-on-tracking-branch: ")
    assert sorted(rows_of(holder)) == sorted(MEMBERS)

    switched(switch_line(holder, f"family/remove-{NEIGHBOUR.lower()}"), stand)
    done = typed(line, stand, env)
    assert done.returncode == 0, done.stdout + done.stderr
    assert branch_of(holder) == f"family/remove-{NEIGHBOUR.lower()}"
    assert sorted(rows_of(holder)) == [PINNED]
    bumped = bump()
    assert bumped.returncode == 0, bumped.stdout + bumped.stderr
    assert rows_of(holder)[PINNED]["pin"]["commit"] == to
    assert git("status", "--porcelain", cwd=holder).stdout == ""
    assert validate(holder).returncode == 0


def test_add_dry_runs_clause_branch_is_made_from_the_rows_id(
        family, offline, stand, tmp_path):
    """(a) The branch the clause names is the one `remove`'s own refusal
    names, made from the row's `id:` and not from its name (RV1264's NIT-2
    on #1264: every other row's id is its name lowercased). The row `IRRS`,
    renamed by hand to `Orrs`, still pins id `irrs`, so `add --dry-run` of
    `IRRS2` is refused `member-duplicate-id`, and the clause's `switch -c`
    names `family/remove-irrs`, not `family/remove-orrs`."""
    env = isolated(offline, tmp_path)
    holder = on_tracking(family, tmp_path / "holders")
    renamed_by_hand(holder, PINNED, "Orrs")
    refused = add_renamed(holder, renamed_copy(family, tmp_path), stand, env,
                          "--dry-run")
    assert refused.returncode == 2, refused.stdout + refused.stderr
    said, remedy = refusal(refused.stderr)
    assert said.startswith("REFUSED member-duplicate-id: "), said
    assert re.findall(r"`(git -C [^`]*)`", remedy) == [
        switch_line(holder, f"family/remove-{PINNED.lower()}")]


def test_bump_dry_runs_clause_branch_is_made_from_the_other_rows_id(
        family, offline, stand, tmp_path):
    """(b) The same for `bump --dry-run` of `IRRS` to a commit whose
    `project.yaml` records the id of `IRSS`, the row the `remove` takes out
    (RV1264's NIT-2 on #1264). `IRSS`, renamed by hand to `Osss`, still
    pins id `irss`: the clause's `switch -c` names `family/remove-irss`,
    not `family/remove-osss`."""
    env = isolated(offline, tmp_path)
    holder = on_tracking(family, tmp_path / "holders")
    renamed_by_hand(holder, NEIGHBOUR, "Osss")
    to = commit_in_mount(holder, env, lambda mount: records_the_neighbours_id(
        mount / "project.yaml"))
    refused = run_script(FAMILY, "bump", "--dry-run", "--family-root",
                         str(holder), "--member", PINNED, "--to", to,
                         cwd=stand, env=env)
    assert refused.returncode == 2, refused.stdout + refused.stderr
    said, remedy = refusal(refused.stderr)
    assert said.startswith("REFUSED member-duplicate-id: "), said
    assert re.findall(r"`(git -C [^`]*)`", remedy) == [
        switch_line(holder, f"family/remove-{NEIGHBOUR.lower()}")]


#: `init`'s arguments, but where it lands, for a family of its own.
INIT = ("init", "--org", ORG, "--family", "Orbit", "--created-by",
        "Test Human", "--created-on", "2026-10-12")


@pytest.mark.parametrize("folder", ["plain", "a`b"])
def test_init_holder_already_heres_add_runs_as_printed_after_its_switch(
        family, offline, stand, tmp_path, folder):
    """(c) `init` run again over the family folder it made is refused
    `family-holder-already-here`. Its remediation, word for word: `init`'s
    own branch, `family/add-<Project>` bare, then `init`'s own `add`, then
    `BRANCH_LEFT`; under `a`b/`, where both commands hold the backtick,
    both are printed bare and the prose is the same. The holder `init` made
    stands on its tracking branch: there the `add`, `<Project>` filled in,
    is refused `family-on-tracking-branch`; typed after the `switch -c`,
    `<Project>` filled in alike, it puts IRQS in the family on that branch,
    and the holder is clean and its gate green."""
    env = isolated(offline, tmp_path)
    into = tmp_path / folder
    into.mkdir()
    lands = ("--local-remote-dir", str(tmp_path / "init remotes"))
    made = run_script(FAMILY, *INIT, *lands, "--into", str(into), cwd=stand,
                      env=env)
    assert made.returncode == 0, made.stdout + made.stderr
    holder = into.resolve() / "Orbit" / "Orbit"
    assert branch_of(holder) == TRACKING, "premise: where `init` leaves it"
    lead = family_lead(stand)

    again = run_script(FAMILY, *INIT, *lands, "--into", str(holder.parent),
                       cwd=stand, env=env)
    assert again.returncode == 2, again.stdout + again.stderr
    # By its code: `init` warns first where the checkout it copies from is
    # dirty, as a developer's may be.
    lines = again.stderr.splitlines()
    said = refusal_detail(again.stderr, "family-holder-already-here")
    assert len(said) == 1, again.stderr
    remedy = lines[lines.index(said[0]) + 1]
    assert remedy == holder_here_remediation(holder, lead,
                                             ticked="`" not in folder)
    add = family_line(lead, "add", holder, f"{shell_quoted(ORG)}/{SPARE}")
    members = ("--local-remote-dir", str(family["remotes"]))

    alone = typed(add, stand, env, *members)
    assert alone.returncode == 2, alone.stdout + alone.stderr
    assert alone.stderr.startswith("REFUSED family-on-tracking-branch: ")

    switched(switch_line(holder, f"family/add-{SPARE}"), stand)
    done = typed(add, stand, env, *members)
    assert done.returncode == 0, done.stdout + done.stderr
    assert branch_of(holder) == f"family/add-{SPARE}"
    assert sorted(rows_of(holder)) == [SPARE]
    assert git("status", "--porcelain", cwd=holder).stdout == ""
    assert validate(holder).returncode == 0
