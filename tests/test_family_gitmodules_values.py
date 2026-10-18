# SPDX-License-Identifier: Apache-2.0
"""A `.gitmodules` value git dies on as it reads the file, in a family
holder's own bootstrap and gate, and where git reads the file from (#768).

THE ISSUE'S THREE LINES, each reproduced on #682's head f74f640c first:

- Bootstrap said `family bootstrap ok`, exit 0, where git dies reading
  `.gitmodules` before it checks out any member: an `update = None` (the
  typo of `update = none`), an `update = !true`, a `url`, `update`,
  `ignore` or `branch` with no value (git 2.43.0 crashes on the last,
  where 2.43.1 and later refuse it as the others), a `shallow = maybe`, a
  `fetchRecurseSubmodules = bogus`. It names every row with the key and
  its value now, and fails, where every member was checked out too.
- The family gate named none of them: members checked and `--pins`
  refused `member-uninitialized`, whose remedy is the update that dies,
  and `--no-members` said `family ok`. Every mode finds
  `gitmodules-value-refused` now, read from the work tree's file and
  HEAD's, and its commands take the key out.
- What #682 left approximate: where the work tree has no `.gitmodules`,
  git reads the index's, then HEAD's; a section's own
  `submodule.<name>.active` decides before `submodule.active`'s patterns;
  and a plain path pattern names only itself and what is under it.

AND #856'S TWO LINES, the first reproduced on #839's head 77f8a6c8:

- Where git reads the index's or HEAD's `.gitmodules`, a blob, a line it
  cannot parse there is an error, not a die: git reads the entries before
  it and goes on. Bootstrap read none, so with no credential each row was
  "no section of .gitmodules gives that path" and the run failed where
  the members were the credential's. It reads what git reads now.
- The rules of which values git dies on are written in both scripts. One
  table of cases is run through both, and their answers held to each
  other, and what both say git takes is read from bootstrap's `TAKES`.

AND #877'S FIRST FIX ROUND, after lane 4's RV877, each reproduced on its
head 40ba4208 first:

- Where the line hid a section or a url, the cure was the section written
  back, which in a work tree with no `.gitmodules` writes a file of that
  section alone, and git then dies at the member it had read. The cure is
  the file git read put back, mended and committed now, typed as printed.
- An `[include]` in the index's or HEAD's file is followed by neither git
  nor bootstrap: a relative one cut bootstrap's reading short there, and
  an absolute one's file was read as the blob's own.

AND ITS SECOND, each reproduced on its first's head 1b87c57d first:

- A key git takes no value for, a bare `url` line, inside a section of
  the index's or HEAD's file: `git config --blob` takes it, git's reading
  stops there, and the cure was the section written back, which cannot
  cure, the key staying in the file. The cure is the file put back with
  that key named, to be given a value or taken out, typed as printed.

AND ITS THIRD, after RV877's re-check, each reproduced on the restacked
head 0afe0afe first:

- A line git cannot parse first in the index's file, HEAD's whole: git
  reads nothing, and bootstrap said the validator names the cause, which
  reads HEAD's and cannot. The index's blob is there, so the read is cut,
  and the cure puts the index's back. HEAD's cut at its first line stays
  the validator's: HEAD may hold no file at all (#611).
- In a sparse checkout that leaves `.gitmodules` out, `git checkout --
  .gitmodules` matched no file. The index's put-back passes
  `--ignore-skip-worktree-bits`, typed as printed there.
- A git that says `bad config line` in other words, and a cut blob beside
  a row of another why, are each held by a test.

THE SAME FAMILY, OFFLINE RULES AND STATES as
`test_family_bootstrap_gate_order.py` (#648), whose helpers are imported:
a plain clone of the holder, `git submodule update` given the fixture's
local members (`fetching`) where a credential is said to be there and not
given them where it is not. Every printed command is typed as printed.
"""

from __future__ import annotations

import os
import re
import shutil
import sys

import pytest

from conftest import REPO, load_without_bytecode, run_script
from repo_shape import PYTHON
from test_family import ORG, family, validate  # noqa: F401
from test_family_add_refusals import holder, offline  # noqa: F401
from test_family_bootstrap_gate_order import (
    CHECKOUT_CURE, DUPLICATE, EXITED_0, FETCHED, NO_SECTION, NO_URL,
    NOT_ALL_FETCHED, SECTION_CURE, STOPPED, after_first_line, bootstrap,
    cloned, edited_clone, failed_on, fetching, not_fetched, type_line,
    url_edited, with_config, without_url,
)
from test_family_dry_run import isolated
from test_family_head_lost_gitmodules import (
    GITMODULES, assert_passes_in_every_mode, commit_all, committed_gitmodules,
    pinned,
)
from test_family_member_path import MEMBER, OTHER, raw
from test_family_tracking_branch import on_main  # noqa: F401
from test_validate_family_typed_states import ROW, removal_staged
from test_validate_family_unnamed_mounts import commands, findings

#: The issue's table, `update = None` first, then `branch` with no value:
#: each a line added to OTHER's section after its url, as rv648 (p11) and
#: w648c (p12) added it, the key git lists for it, and the value, None for
#: none. Git's update dies on each, exit 128, but for `branch` with no
#: value, which git 2.43.0 crashes on (exit 139, w768's probe) and 2.43.1
#: and later refuse as the others (exit 128, CI's 2.55.0): the tool's
#: answer is the test, never how git dies.
REFUSED_LINES = {
    "update-None": ("update = None", "update", "None"),
    "update-command": ("update = !true", "update", "!true"),
    "url-no-value": ("url", "url", None),
    "update-no-value": ("update", "update", None),
    "ignore-no-value": ("ignore", "ignore", None),
    "shallow-maybe": ("shallow = maybe", "shallow", "maybe"),
    "fetch-bogus": ("fetchRecurseSubmodules = bogus",
                    "fetchrecursesubmodules", "bogus"),
    "branch-no-value": ("branch", "branch", None),
}


def by_path(script: str, name: str):
    """The family root's `scripts/<script>`, loaded by path as the module
    `name`, and `sys.path`, which loading it puts the script's own folder
    on, put back."""
    kept = list(sys.path)
    try:
        return load_without_bytecode(
            REPO / "templates" / "family-root" / "scripts" / script, name)
    finally:
        sys.path[:] = kept


#: The two scripts, each of which writes which values git dies on (#856).
#: The parity tests at the end hold them to one answer, so what both say
#: git takes for each key is read from bootstrap's `TAKES`, and this file
#: keeps no copy of its own.
BOOTSTRAP = by_path("bootstrap.py", "gitmodules_values_bootstrap")
GATE = by_path("validate-family.py", "gitmodules_values_gate")
TAKES = BOOTSTRAP.TAKES

#: Where the finding says the value is.
HERE_AND_HEAD = "here and in HEAD, which a clone reads"
WORK_TREE_ONLY = "in the work tree, not in HEAD"
HEAD_ONLY = "in HEAD, which a clone reads, not in the work tree"


def with_line(line: str):
    """An edit giving OTHER's section `line` after its url."""
    return lambda data: url_edited(
        data, OTHER, lambda url: url + f"\t{line}\n".encode())


def full(key: str) -> str:
    return f"submodule.members/{OTHER}.{key}"


def refused_why(key: str, value: str | None) -> str:
    """Why (a) says each row was not checked out."""
    return (f"git cannot read .gitmodules: `{full(key)}` "
            + ("has no value" if value is None else f"is `{value}`"))


def value_cure(key: str) -> str:
    """What (a) says cures it."""
    return (f"Give `{full(key)}` a value git takes, {TAKES[key]}, or take "
            f"that line out, and commit .gitmodules. `{PYTHON} "
            "scripts/validate-family.py --no-members` prints the commands.")


def said(key: str, value: str | None, where: str) -> str:
    """`gitmodules-value-refused` up to its remedy. Where HEAD's file
    alone gives the value, git dies on it in a clone, which reads HEAD's,
    and that is what it says (rv819's NIT 8)."""
    given = "no value" if value is None else f"the value `{value}`"
    dies = ("so in a clone neither `git submodule update` nor make "
            "bootstrap checks out any member" if where == HEAD_ONLY
            else "before `git submodule update` checks out any member, so "
            "neither that nor make bootstrap checks one out")
    return (f"FINDING gitmodules-value-refused: .gitmodules gives "
            f"`{full(key)}` {given} {where}, and git dies reading a file "
            f"that does, {dies}. Git takes {TAKES[key]} for that key. ")


def taken_out(key: str, value: str | None, *, back: str | None = None,
              where: str = HERE_AND_HEAD, put_back: bool = False) -> str:
    """`gitmodules-value-refused` WHOLE, with the commands that take the key
    out of the work tree's file, after the one that puts HEAD's back where
    `put_back`, and write `back` in where it is given."""
    lines = (["git checkout HEAD -- .gitmodules"] if put_back else []) + [
        f"git config -f .gitmodules --unset-all {full(key)}"]
    if back is not None:
        lines.append(f"git config -f .gitmodules {full(key)} {back}")
    return (said(key, value, where)
            + ("The work tree holds no .gitmodules, so the first line below "
               "puts HEAD's back. " if put_back else "")
            + "Take the key out"
            + (f" and write its {key} back" if back is not None else "")
            + " by hand, in a POSIX shell"
            + ("" if where == WORK_TREE_ONLY
               else ", then stage and commit .gitmodules")
            + ":" + "".join(f"\n    {line}" for line in lines))


def url_of(data: bytes) -> str:
    """The url `family.py add` wrote in OTHER's section of `data`."""
    (url,) = re.findall(rb'\[submodule "members/' + OTHER.encode()
                        + rb'"\]\r?\n(?:\t[^\n]*\n)*?\turl = ([^\r\n]*)', data)
    return url.decode("utf-8")


def assert_the_credential_s_skip(clone, env) -> None:
    """Bootstrap with no credential for the members: git fails on their
    fetch, not on `.gitmodules`, so they are skipped, and the run is ok."""
    result = bootstrap(clone, env, "--skip-members")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FETCH INCOMPLETE" in result.stderr
    assert "not for want of a credential" not in result.stderr


def typed_and_committed(root, env, finding: str) -> None:
    """Every command `finding` prints, typed as printed, then `.gitmodules`
    staged and committed, as the finding says."""
    for command in commands(finding):
        type_line(root, env, command)
    raw(root, env, "add", "--", GITMODULES)
    commit_all(root, env, "The key taken out as printed")


def found_in_every_mode_and_typed(root, env, expected: str) -> None:
    """The gate finds `expected` alone, exit 1, in all three modes, and
    its commands are typed as printed and committed."""
    for extra in ((), ("--pins",), ("--no-members",)):
        gate = validate(root, *extra)
        assert gate.returncode == 1, (extra, gate.stdout + gate.stderr)
        assert findings(gate) == [expected], extra
    typed_and_committed(root, env, expected)


def assert_a_good_holder_s_run(root, env) -> None:
    """Bootstrap checks every member out and is a good holder's, and the
    gate passes in every mode."""
    again = bootstrap(root, env, "--skip-members")
    assert again.returncode == 0, again.stdout + again.stderr
    assert after_first_line(again) == FETCHED
    assert_passes_in_every_mode(root, 2)


# --- lines 1 and 2: bootstrap and the gate ----------------------------------

@pytest.mark.parametrize("line, key, value", REFUSED_LINES.values(),
                         ids=REFUSED_LINES)
def test_a_value_git_dies_on_fails_bootstrap_and_every_mode_of_the_gate(
        family, holder, offline, tmp_path, line, key, value):
    """THE ISSUE'S LINES 1 AND 2. The line committed, a plain clone with the
    credential: git's update dies and checks nothing out, and bootstrap
    said ok. It names both rows, the key and its value, and fails. The
    gate refused `member-uninitialized` members checked, with the update
    that dies for remedy, and said `family ok` under `--no-members`; it
    finds `gitmodules-value-refused` in all three modes now. Typed as
    printed and committed, which writes back the url a `url` line took
    with it, the file is the one `family.py add` wrote, and the same run
    checks both members out and passes the gate in every mode."""
    env = fetching(isolated(offline, tmp_path))
    clone, data = edited_clone(holder, env, family, tmp_path, with_line(line))
    update = raw(clone, env, "submodule", "update", "--init", "--recursive",
                 check=False)
    assert update.returncode != 0, update.stderr
    assert not (clone / "members" / MEMBER / ".git").exists(), (
        "premise: git checked nothing out")

    result = bootstrap(clone, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert after_first_line(result) == NOT_ALL_FETCHED
    why = refused_why(key, value)
    assert result.stderr.splitlines()[-2:] == [
        not_fetched((f"members/{MEMBER}", why), (f"members/{OTHER}", why),
                    cure=value_cure(key)),
        failed_on(MEMBER, OTHER)], result.stderr
    found_in_every_mode_and_typed(
        clone, env, taken_out(key, value,
                              back=url_of(data) if key == "url" else None))
    assert raw(clone, env, "show", f"HEAD:{GITMODULES}").stdout == data
    assert_a_good_holder_s_run(clone, env)


#: Values git takes, which no line or finding names (the issue's no-misfire
#: cases but `update = none`, whose run is the exit-0 skip as before, and
#: each other `update` git takes, rv819's finding 4).
TAKEN = {"update-checkout": "update = checkout",
         "update-rebase": "update = rebase",
         "update-merge": "update = merge",
         "shallow-true": "shallow = true",
         "fetch-on-demand": "fetchRecurseSubmodules = on-demand",
         "ignore-bogus": "ignore = bogus"}


@pytest.mark.parametrize("line", TAKEN.values(), ids=TAKEN)
def test_a_value_git_takes_is_a_good_holder_s_run(family, holder, offline,
                                                   tmp_path, line):
    """No misfire. Git takes each (an `ignore` it does not know is a
    warning only). With no credential, git fails on the members' fetch and
    they are the credential's: skipped, and ok. With it, the plain clone's
    update checks both members out, bootstrap is a good holder's, and the
    gate passes in every mode, in the clone and in the holder."""
    env = isolated(offline, tmp_path)
    clone, _ = edited_clone(holder, env, family, tmp_path, with_line(line))
    assert_the_credential_s_skip(clone, env)

    result = bootstrap(clone, fetching(env), "--skip-members")

    assert result.returncode == 0, result.stdout + result.stderr
    assert after_first_line(result) == FETCHED
    assert result.stderr == ""
    assert_passes_in_every_mode(clone, 2)
    assert_passes_in_every_mode(holder, 2)


def test_update_none_is_still_the_exit_0_skip(family, holder, offline,
                                              tmp_path):
    """No misfire. `update = none` is a value git takes: git exits 0 and
    skips OTHER, and bootstrap names it with the update that checks it out,
    as before (#648's N1), and no line or finding says git cannot read the
    file."""
    env = fetching(isolated(offline, tmp_path))
    clone, _ = edited_clone(holder, env, family, tmp_path,
                            with_line("update = none"))

    result = bootstrap(clone, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stderr.splitlines() == [
        not_fetched((f"members/{OTHER}", EXITED_0),
                    cure=CHECKOUT_CURE.format(path=f"members/{OTHER}")),
        failed_on(OTHER)]
    assert validate(clone, "--no-members").returncode == 0
    assert_passes_in_every_mode(holder, 2)


#: A section under a name git ignores whole, its `update = None` included
#: (`ignoring suspicious submodule name`): no row names its path. Git splits
#: the name on a backslash too, on every system (`check_submodule_name`);
#: in the file it is escaped, as git config escapes a subsection name.
IGNORED = b'[submodule "../x"]\n\tpath = x\n\tupdate = None\n'
IGNORED_NAMES = {"slash": IGNORED,
                 "backslash": IGNORED.replace(b"../x", b"..\\\\x")}


@pytest.mark.parametrize("ignored", IGNORED_NAMES.values(), ids=IGNORED_NAMES)
def test_a_value_in_a_section_git_ignores_whole_is_no_finding(
        family, holder, offline, tmp_path, ignored):
    """No misfire. A section whose name has a `..` component is ignored
    whole by git, a value it would die on included. With no credential,
    the members are the credential's: skipped, and ok. With it, the plain
    clone's update warns and checks both members out, bootstrap is a good
    holder's, and the gate names the section as one no row names, not as a
    value git refuses."""
    env = isolated(offline, tmp_path)
    clone, _ = edited_clone(holder, env, family, tmp_path,
                            lambda data: data + ignored)
    assert_the_credential_s_skip(clone, env)

    result = bootstrap(clone, fetching(env), "--skip-members")

    assert result.returncode == 0, result.stdout + result.stderr
    assert after_first_line(result) == FETCHED
    gate = validate(clone, "--no-members")
    assert [found.split(":")[0] for found in findings(gate)] == [
        "FINDING gitmodules-path-unnamed"], gate.stderr


def test_a_holder_with_every_member_checked_out_fails_on_it_too(
        holder, offline, tmp_path):
    """Every member checked out, as in the holder itself, and `update =
    None` committed: git dies before it updates any of them, so no row is
    left to name, and bootstrap said ok over git's `fatal:` line. It says
    no member was updated, and why, and fails on `.gitmodules`; typed as
    the gate prints it and committed, the run is a good holder's."""
    env = fetching(isolated(offline, tmp_path))
    data = raw(holder, env, "show", f"HEAD:{GITMODULES}").stdout
    committed_gitmodules(holder, env, with_line("update = None")(data))

    result = bootstrap(holder, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stderr.splitlines()[-2:] == [
        "  NO MEMBER UPDATED, and not for want of a credential: "
        f"{refused_why('update', 'None')}. {value_cure('update')}",
        "family bootstrap FAILED: .gitmodules (git cannot read it)"]
    gate = validate(holder)
    assert gate.returncode == 1, gate.stdout + gate.stderr
    assert findings(gate) == [taken_out("update", "None")]
    typed_and_committed(holder, env, findings(gate)[0])

    again = bootstrap(holder, env, "--skip-members")

    assert again.returncode == 0, again.stdout + again.stderr
    assert after_first_line(again) == FETCHED


#: A `.gitmodules` git cannot parse at all, the line added at its end: a
#: merge's conflict marker left in it, and a quote left open (rv819's
#: finding 3). `git config --list` and git's update both die on it.
DAMAGED = {"conflict-marker": b"<<<<<<< HEAD\n",
           "open-quote": b'\tupdate = "none\n'}

#: What (a) says of such a file, and what cures it.
UNPARSED = "git cannot parse .gitmodules"
MEND_CURE = ("Mend .gitmodules by hand (`git config -f .gitmodules --list` "
             "says where it breaks), and commit it.")


@pytest.mark.parametrize("damage", DAMAGED.values(), ids=DAMAGED)
def test_a_gitmodules_git_cannot_parse_fails_with_every_member_checked_out(
        holder, offline, tmp_path, damage):
    """Every member checked out, as in the holder itself, and a
    `.gitmodules` git cannot parse committed: git's update dies before it
    updates any member, and bootstrap said `family bootstrap ok`, where a
    value git refuses failed the run. It says no member was updated, and
    why, and fails on `.gitmodules`; mended and committed, the run is a
    good holder's."""
    env = fetching(isolated(offline, tmp_path))
    data = raw(holder, env, "show", f"HEAD:{GITMODULES}").stdout
    committed_gitmodules(holder, env, data + damage)
    update = raw(holder, env, "submodule", "update", "--init", "--recursive",
                 check=False)
    assert b"bad config line" in update.stderr, update.stderr

    result = bootstrap(holder, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stderr.splitlines()[-2:] == [
        "  NO MEMBER UPDATED, and not for want of a credential: "
        f"{UNPARSED}. {MEND_CURE}",
        "family bootstrap FAILED: .gitmodules (git cannot read it)"]
    committed_gitmodules(holder, env, data)

    again = bootstrap(holder, env, "--skip-members")

    assert again.returncode == 0, again.stdout + again.stderr
    assert after_first_line(again) == FETCHED


def test_a_gitmodules_git_cannot_parse_is_named_for_every_row(
        family, holder, offline, tmp_path):
    """A plain clone of a holder whose committed `.gitmodules` git cannot
    parse, with the credential: git's update dies and checks nothing out.
    Bootstrap said no section gave either path, with the validator for
    cure; it says git cannot parse the file, and how to mend it."""
    env = fetching(isolated(offline, tmp_path))
    clone, _ = edited_clone(holder, env, family, tmp_path,
                            lambda data: data + DAMAGED["conflict-marker"])

    result = bootstrap(clone, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stderr.splitlines()[-2:] == [
        not_fetched((f"members/{MEMBER}", UNPARSED),
                    (f"members/{OTHER}", UNPARSED), cure=MEND_CURE),
        failed_on(MEMBER, OTHER)], result.stderr


#: The work tree's `.gitmodules` lost and not committed, its index entry
#: left (git reads that) or staged out too (git reads HEAD's).
def lose_work_tree_file(root, env) -> None:
    (root / GITMODULES).unlink()


def lose_work_tree_and_index_files(root, env) -> None:
    raw(root, env, "rm", "-q", "--cached", "--", GITMODULES)
    (root / GITMODULES).unlink()


LOST = {"index-read": lose_work_tree_file,
        "head-read": lose_work_tree_and_index_files}


@pytest.mark.parametrize("lose", LOST.values(), ids=LOST)
def test_where_the_work_tree_has_no_gitmodules_git_reads_the_index_s_or_head_s(
        family, holder, offline, tmp_path, lose):
    """THE ISSUE'S LINE 3, its first item. A plain clone whose work tree
    lost `.gitmodules`, not committed, with no credential: git reads the
    index's file, or HEAD's where the index lost it too, and fails on the
    members' fetch. Bootstrap read the work tree's alone, said "no section
    of .gitmodules gives that path" for each, and failed; the members are
    the credential's now, skipped, and the run ends ok."""
    env = isolated(offline, tmp_path)
    clone = cloned(holder, env, family, tmp_path, recurse=False)
    lose(clone, env)

    assert_the_credential_s_skip(clone, env)


def test_a_key_with_no_value_ends_git_s_reading_of_the_index_s_file(
        family, holder, offline, tmp_path):
    """No misfire. A `url` with no value, the last line of the index's
    file, which git reads where the work tree has none: in a blob git
    calls the line bad and stops reading there, an error and no die, so it
    reads every section before it and fails on the fetch for want of a
    credential. The members are the credential's: skipped, and ok."""
    env = isolated(offline, tmp_path)
    clone, _ = edited_clone(holder, env, family, tmp_path, with_line("url"))
    lose_work_tree_file(clone, env)
    update = raw(clone, env, "submodule", "update", "--init", "--recursive",
                 check=False)
    assert b"bad config line" in update.stderr, update.stderr

    assert_the_credential_s_skip(clone, env)


#: A line git cannot parse, a quote left open, as #856 measured it.
UNPARSED_LINE = b'\tbranch = "unterminated\n'

#: Where it goes in a `.gitmodules` that gives MEMBER's section, then
#: OTHER's (#856): the edit, the paths git's update registers before it
#: dies or goes on, and the path its init then finds no url for, or None.
CUT_AT = {
    "at-the-end": (
        lambda data: url_edited(data, OTHER,
                                lambda url: url + UNPARSED_LINE),
        (f"members/{MEMBER}", f"members/{OTHER}"), None),
    "after-the-first-section": (
        lambda data: url_edited(data, MEMBER,
                                lambda url: url + UNPARSED_LINE),
        (f"members/{MEMBER}",), f"members/{OTHER}"),
    "inside-a-section": (
        lambda data: url_edited(data, OTHER,
                                lambda url: UNPARSED_LINE + url),
        (f"members/{MEMBER}",), f"members/{OTHER}"),
    "before-the-first-section": (lambda data: UNPARSED_LINE + data, (),
                                 f"members/{MEMBER}"),
}

#: MEMBER, where git's init stops at OTHER, which it has no url for.
STOPS_AT_OTHER = (f"members/{MEMBER}", STOPPED.format(path=f"members/{OTHER}"))

#: What (a) says where git's init dies at a path it read no url for, and
#: by which `LOST` its cure is the file git read put back and mended
#: (`cut_cure`): MEMBER stopped at OTHER, which no section git read gives,
#: or whose section git read only up to its path, where git read an entry
#: before the line, so what it did not read is past it; and, with nothing
#: read, no section for either. That is cut where git read the index's
#: file, whose blob is there (RV877's SHOULD-2), and not where it read
#: HEAD's, which may be no file at all (#611): the validator is the cure.
CUT_SAID = {
    "after-the-first-section": (
        (STOPS_AT_OTHER, (f"members/{OTHER}", NO_SECTION)),
        ("index-read", "head-read")),
    "inside-a-section": (
        (STOPS_AT_OTHER, (f"members/{OTHER}", NO_URL)),
        ("index-read", "head-read")),
    "before-the-first-section": (
        ((f"members/{MEMBER}", NO_SECTION), (f"members/{OTHER}", NO_SECTION)),
        ("index-read",)),
}

#: How (a) says to put back the file git read, by `LOST`: the index's,
#: where the work tree alone lost it, from the index, which keeps what was
#: staged, past a sparse checkout's skip-worktree bit (RV877's NIT-3);
#: HEAD's, where the index lost it too (RV877's MUST-1 on #877).
PUT_BACK = {"index-read": ("git checkout --ignore-skip-worktree-bits -- "
                           ".gitmodules", "the index's"),
            "head-read": ("git checkout HEAD -- .gitmodules", "HEAD's")}


def cut_cure(lost: str) -> str:
    """What (a) says cures a blob git read only up to a line it cannot
    parse, where git read the file `lost` names (`PUT_BACK`)."""
    command, whose = PUT_BACK[lost]
    return (f"`{command}` puts back {whose} .gitmodules, which git read "
            "only up to a line it cannot parse: mend it by hand (`git "
            "config -f .gitmodules --list` says where it breaks), and "
            "commit it.")


def git_reads_up_to_the_line(clone, env, place: str) -> None:
    """Git's update in `clone`, which reads a blob with the line git cannot
    parse at `place` (`CUT_AT`): it says the line, which in a blob is an
    error and no die, reads the entries before it, registers the paths it
    read a url for, and finds none where `CUT_AT` says."""
    _, registered, no_url = CUT_AT[place]
    git_update_said(clone, env, registered, no_url)


def git_update_said(clone, env, registered, no_url, *,
                    stops: bool = True) -> None:
    """Git's update in `clone`, no credential: where it `stops`, it calls a
    line of the blob it reads bad, an error and no die, and reads no
    further; it registers the paths `registered` names, and finds no url
    for `no_url`, or for no path where that is None."""
    update = raw(clone, env, "submodule", "update", "--init", "--recursive",
                 check=False)
    said = update.stderr.decode("utf-8", "replace")
    assert ("bad config line" in said) is stops, said
    assert tuple(re.findall(r"registered for path '([^']*)'", said)) == (
        registered), said
    assert re.findall(r"No url found for submodule path '([^']*)'",
                      said) == ([] if no_url is None else [no_url]), said


def cut_clone(family, holder, env, tmp_path, lose, place: str):
    """A plain clone with the line git cannot parse committed at `place`
    (`CUT_AT`), its work tree's `.gitmodules` lost, not committed, by
    `lose`, so git reads the index's or HEAD's, and no credential, and
    git's update run in it (`git_reads_up_to_the_line`). Returns the clone
    and the bytes `family.py add` wrote."""
    clone, data = edited_clone(holder, env, family, tmp_path, CUT_AT[place][0])
    lose(clone, env)
    git_reads_up_to_the_line(clone, env, place)
    return clone, data


def put_back_mended_and_committed(root, env, lost: str, mended: bytes,
                                  line: bytes = UNPARSED_LINE, *,
                                  sparse: bool = False) -> None:
    """(a)'s cure for a blob git read only up to `line`, followed: its
    command typed as printed (`PUT_BACK`), which puts the file git read in
    the work tree, the line and all, where `git config -f .gitmodules
    --list` says where it breaks, a line it cannot parse, or takes it, a
    key with no value (`BARE_AT`), which (a) names for that; mended by
    hand, the line taken out, which leaves `mended`; and committed. In a
    `sparse` checkout, `git add` refuses a path outside its patterns and
    says to give `--sparse`, which is how it is added there."""
    type_line(root, env, PUT_BACK[lost][0])
    put_back = (root / GITMODULES).read_bytes()
    assert put_back.replace(line, b"", 1) == mended, put_back
    listed = raw(root, env, "config", "-f", GITMODULES, "--list",
                 check=False)
    if line == UNPARSED_LINE:
        assert b"bad config line" in listed.stderr, listed.stderr
    else:
        assert listed.returncode == 0, listed.stderr
    (root / GITMODULES).write_bytes(mended)
    if sparse:
        refused = raw(root, env, "add", "--", GITMODULES, check=False)
        assert b"--sparse" in refused.stderr, refused.stderr
    raw(root, env, "add", *(["--sparse"] if sparse else []), "--",
        GITMODULES)
    commit_all(root, env, "The line git cannot parse mended as printed")
    assert raw(root, env, "show", f"HEAD:{GITMODULES}").stdout == mended


@pytest.mark.parametrize("lose", LOST.values(), ids=LOST)
def test_a_line_git_cannot_parse_at_the_end_of_a_blob_leaves_the_credential_s(
        family, holder, offline, tmp_path, lose):
    """THE ISSUE'S FIRST LINE (#856). The line at the end of the index's
    file, or HEAD's, which git reads where the work tree has none: git
    reads every section before it and fails on the fetch for want of a
    credential. Bootstrap read no section, since `git config --list`
    exits 128 there, said "no section of .gitmodules gives that path" for
    each row, and failed. It reads what git printed before it died now:
    the members are the credential's, skipped, and ok."""
    env = isolated(offline, tmp_path)
    clone, _ = cut_clone(family, holder, env, tmp_path, lose, "at-the-end")

    assert_the_credential_s_skip(clone, env)


@pytest.mark.parametrize("lost", LOST)
@pytest.mark.parametrize("place", CUT_SAID)
def test_a_line_git_cannot_parse_earlier_in_a_blob_is_read_up_to_as_git_does(
        family, holder, offline, tmp_path, lost, place):
    """THE ISSUE'S FIRST LINE (#856), the line earlier in the file. After
    the first section, git reads MEMBER's alone; inside OTHER's, before
    its url, MEMBER's and OTHER's path: either way its init dies at OTHER,
    `No url found`, before it checks out any member, as it would with a
    credential. Bootstrap said no section gave either path; it names
    MEMBER stopped at OTHER, and OTHER as git read it. Before the first
    section git reads nothing, and neither does bootstrap.

    AND THE CURE (RV877's MUST-1). Inside OTHER's section it was OTHER's
    section written back, which, typed in a work tree with no file, wrote
    a file of OTHER's section alone, and git then died at MEMBER; with the
    file put back first, git config died on the line. Where git read an
    entry before the line, the section or url it did not read may be past
    it, so the cure is the file git read put back, mended and committed,
    in both places: typed as printed, the run is the credential's skip,
    and with it a good holder's. Before the first section git read
    nothing, as from no file at all, and the validator was the cure: it
    still is from HEAD's, which may be no file at all (#611), and from the
    index's, whose blob is there, the read is cut (RV877's SHOULD-2)."""
    env = isolated(offline, tmp_path)
    clone, data = cut_clone(family, holder, env, tmp_path, LOST[lost], place)
    left, cut_in = CUT_SAID[place]
    cut = lost in cut_in

    result = bootstrap(clone, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stderr.splitlines()[-2:] == [
        not_fetched(*left, cure=cut_cure(lost)) if cut else not_fetched(*left),
        failed_on(MEMBER, OTHER)], result.stderr
    if not cut:
        return
    put_back_mended_and_committed(clone, env, lost, data)
    assert_the_credential_s_skip(clone, env)
    assert_a_good_holder_s_run(clone, fetching(env))


#: A key with no value put before a section's url (round 2 of #877): in
#: the first section, MEMBER's, or a later one, OTHER's. `(the section,
#: the key, the paths git's update registers, the path it finds no url
#: for, the rows (a) names)`. Git takes no `url`, `path`, `update` or
#: `ignore` with no value: in a blob it calls the line bad, an error and
#: no die, and reads no further, where `git config --blob` takes the key
#: and exits 0. A boolean with no value is true, and git reads on: no row
#: is named, and the members are the credential's.
BARE_AT = {
    "url-in-the-first-section": (
        MEMBER, "url", (), f"members/{MEMBER}",
        ((f"members/{MEMBER}", NO_URL), (f"members/{OTHER}", NO_SECTION))),
    "url-in-a-later-section": (
        OTHER, "url", (f"members/{MEMBER}",), f"members/{OTHER}",
        (STOPS_AT_OTHER, (f"members/{OTHER}", NO_URL))),
    "update-in-a-later-section": (
        OTHER, "update", (f"members/{MEMBER}",), f"members/{OTHER}",
        (STOPS_AT_OTHER, (f"members/{OTHER}", NO_URL))),
    "shallow-in-a-later-section": (
        OTHER, "shallow", (f"members/{MEMBER}", f"members/{OTHER}"), None,
        None),
}


def git_reads_every_section(root, env) -> None:
    """Git's update with no credential, once the cure is committed: it
    reads the work tree's file whole, registers every member, and fails
    on their fetch alone."""
    update = raw(root, env, "submodule", "update", "--init", "--recursive",
                 check=False)
    said = update.stderr.decode("utf-8", "replace")
    assert update.returncode != 0, "premise: no credential"
    assert "No url found" not in said and "bad config line" not in said, said
    for project in (MEMBER, OTHER):
        raw(root, env, "config", "--get", f"submodule.members/{project}.url")


def bare_cure(lost: str, project: str, key: str) -> str:
    """What (a) says cures a blob git read only up to `project`'s `key`
    with no value, where git read the file `lost` names (`PUT_BACK`)."""
    command, whose = PUT_BACK[lost]
    return (f"`{command}` puts back {whose} .gitmodules, which git read "
            f"only up to `submodule.members/{project}.{key}`, a key with no "
            f"value: give it a value git takes, {TAKES[key]}, or take that "
            "line out, and commit it.")


@pytest.mark.parametrize("lost", LOST)
@pytest.mark.parametrize("place", BARE_AT)
def test_a_bare_key_in_a_blob_is_read_up_to_and_named_in_the_cure(
        family, holder, offline, tmp_path, lost, place):
    """ROUND 2 OF #877. A key git takes no value for, put before a
    section's url in the index's file, or HEAD's, which git reads where
    the work tree has none, and no credential: git's update calls the line
    bad and reads no further, so its init dies at the first section it
    read no url for, and `git config --blob` takes the key and exits 0.
    Bootstrap stopped where git stops (#819) and wrote the unread section
    back, which cannot cure: the key stays in the file. It names the file
    put back, and that key, to be given a value or taken out: typed as
    printed, `git config -f` takes the key, the line is taken out and the
    file committed, git's update reads every section and fails on the
    fetch alone, the run is the credential's skip, and with the
    credential a good holder's. A boolean with no value is true, and
    git reads on: the credential's skip, as before."""
    project, key, registered, no_url, left = BARE_AT[place]
    line = f"\t{key}\n".encode()
    env = isolated(offline, tmp_path)
    clone, data = edited_clone(
        holder, env, family, tmp_path,
        lambda data: url_edited(data, project, lambda url: line + url))
    LOST[lost](clone, env)
    git_update_said(clone, env, registered, no_url, stops=left is not None)
    if left is None:
        assert_the_credential_s_skip(clone, env)
        return

    result = bootstrap(clone, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stderr.splitlines()[-2:] == [
        not_fetched(*left, cure=bare_cure(lost, project, key)),
        failed_on(MEMBER, OTHER)], result.stderr
    put_back_mended_and_committed(clone, env, lost, data, line)
    git_reads_every_section(clone, env)
    assert_the_credential_s_skip(clone, env)
    assert_a_good_holder_s_run(clone, fetching(env))


#: A line of the person's own, staged with the line git cannot parse.
OWN_LINE = b"# a line of the person's own, staged with it\n"


@pytest.mark.parametrize("place", ("inside-a-section",
                                   "before-the-first-section"))
def test_the_index_s_file_cut_short_is_put_back_from_the_index(
        family, holder, offline, tmp_path, place):
    """RV877's MUST-1, where git reads the index's file and HEAD's is
    whole: the line inside OTHER's section, or first in the file (RV877's
    SHOULD-2), staged with a line of the person's own, not committed, and
    the work tree's file lost. Git reads the index's up to the line, the
    first one reading nothing, and dies at OTHER or MEMBER. The gate
    reads the work tree's file and HEAD's, not the index's, so it cannot
    name the line, and HEAD's file put back would lose what was staged.
    The cure puts the index's back, its line first included: typed as
    printed, mended and committed, the person's own line is in HEAD, and
    the run is the credential's skip."""
    env = isolated(offline, tmp_path)
    clone = cloned(holder, env, family, tmp_path, recurse=False)
    staged = raw(clone, env, "show", f"HEAD:{GITMODULES}").stdout + OWN_LINE
    (clone / GITMODULES).write_bytes(CUT_AT[place][0](staged))
    raw(clone, env, "add", "--", GITMODULES)
    lose_work_tree_file(clone, env)
    git_reads_up_to_the_line(clone, env, place)
    gate = validate(clone, "--no-members")
    assert "bad config line" not in gate.stdout + gate.stderr, (
        "premise: the gate cannot name the line", gate.stdout + gate.stderr)

    result = bootstrap(clone, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stderr.splitlines()[-2:] == [
        not_fetched(*CUT_SAID[place][0], cure=cut_cure("index-read")),
        failed_on(MEMBER, OTHER)], result.stderr
    put_back_mended_and_committed(clone, env, "index-read", staged)
    assert_the_credential_s_skip(clone, env)


def lose_by_a_sparse_checkout(root, env) -> None:
    """A sparse checkout that leaves `.gitmodules` out of the work tree
    (RV877's NIT-3): only patterns not in cone mode can leave out a file
    at the top. Its entry in the index is then skip-worktree, and git
    reads it there."""
    raw(root, env, "sparse-checkout", "set", "--no-cone", "/*",
        f"!/{GITMODULES}")
    assert not (root / GITMODULES).exists()
    assert raw(root, env, "ls-files", "-t", "--",
               GITMODULES).stdout == f"S {GITMODULES}\n".encode()


def test_a_sparse_checkout_s_file_cut_short_is_put_back_past_its_bits(
        family, holder, offline, tmp_path):
    """RV877's NIT-3. The line inside OTHER's section committed, and a
    sparse checkout that leaves `.gitmodules` out, so git reads the
    index's. `git checkout -- .gitmodules`, the put-back round 1 printed,
    matches no file there. The put-back passes
    `--ignore-skip-worktree-bits`: typed as printed it puts the file back,
    and mended, added as `git add` says to add a path outside the sparse
    patterns, and committed, the run is the credential's skip, and with
    the credential a good holder's."""
    env = isolated(offline, tmp_path)
    clone, data = cut_clone(family, holder, env, tmp_path,
                            lose_by_a_sparse_checkout, "inside-a-section")
    plain = raw(clone, env, "checkout", "--", GITMODULES, check=False)
    assert b"did not match any file" in plain.stderr, plain.stderr
    assert not (clone / GITMODULES).exists(), "premise: nothing put back"

    result = bootstrap(clone, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stderr.splitlines()[-2:] == [
        not_fetched(*CUT_SAID["inside-a-section"][0],
                    cure=cut_cure("index-read")),
        failed_on(MEMBER, OTHER)], result.stderr
    put_back_mended_and_committed(clone, env, "index-read", data,
                                  sparse=True)
    assert_the_credential_s_skip(clone, env)
    assert_a_good_holder_s_run(clone, fetching(env))


#: A git first on PATH that keeps git's exit code and stdout and says its
#: stderr in other words, as a git built with its translations says them
#: (RV877's NIT-4, its R1x).
TRANSLATED = """#!{python}
import subprocess, sys
proc = subprocess.run([{git!r}, *sys.argv[1:]], stderr=subprocess.PIPE)
sys.stderr.buffer.write(proc.stderr.replace(b"bad config line",
                                            b"Ungueltige Konfigurationszeile"))
sys.exit(proc.returncode)
"""


def translated(env: dict, folder) -> dict:
    """`env` with `TRANSLATED` first on PATH, as `git`, in `folder`."""
    real = shutil.which("git")
    assert real, "premise: a git on PATH"
    folder.mkdir()
    shim = folder / "git"
    shim.write_text(TRANSLATED.format(python=sys.executable, git=real),
                    encoding="utf-8")
    shim.chmod(0o755)
    return {**env, "PATH": f"{folder}{os.pathsep}"
                           f"{env.get('PATH') or os.environ['PATH']}"}


@pytest.mark.skipif(os.name == "nt",
                    reason="a git on PATH run by its #! line is POSIX's")
@pytest.mark.parametrize("lose", LOST.values(), ids=LOST)
def test_a_blob_cut_short_is_read_whatever_words_git_says_it_in(
        family, holder, offline, tmp_path, lose):
    """RV877's NIT-4, its R1x. The line at the end of the index's file, or
    HEAD's, and no credential, under a git that says `bad config line` in
    other words, as a translated git does: bootstrap reads the blob by
    git's exit code and what it printed, never its words, so it reads
    both sections, and the members are the credential's, skipped, and
    ok. Reading `bad config line` on stderr read nothing there, and named
    both rows."""
    env = isolated(offline, tmp_path)
    clone, _ = cut_clone(family, holder, env, tmp_path, lose, "at-the-end")
    env = translated(env, tmp_path / "translated")
    listed = raw(clone, env, "config", "-z", "--blob", f"HEAD:{GITMODULES}",
                 "--list", check=False)
    assert listed.returncode == 128 and listed.stdout, listed.stderr
    assert b"bad config line" not in listed.stderr, listed.stderr
    assert b"Ungueltige Konfigurationszeile" in listed.stderr, listed.stderr

    assert_the_credential_s_skip(clone, env)


@pytest.mark.parametrize("lose", LOST.values(), ids=LOST)
def test_a_cut_blob_beside_a_row_of_another_why_keeps_that_row_s_cure(
        family, holder, offline, tmp_path, lose):
    """RV877's NIT-4, its N6. OTHER's section gives `update = none`, then
    the line git cannot parse ends the index's file, or HEAD's, and the
    credential: git reads both sections, checks MEMBER out, skips OTHER
    and exits 0. The blob is cut, but OTHER is no row the cut can explain
    (`CUT_WHYS`): its cure is the update that checks it out, alone, and
    no file is said to be put back."""
    env = fetching(isolated(offline, tmp_path))
    clone, _ = edited_clone(
        holder, env, family, tmp_path,
        lambda data: url_edited(
            data, OTHER,
            lambda url: url + b"\tupdate = none\n" + UNPARSED_LINE))
    lose(clone, env)

    result = bootstrap(clone, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stderr.splitlines()[-2:] == [
        not_fetched((f"members/{OTHER}", EXITED_0),
                    cure=CHECKOUT_CURE.format(path=f"members/{OTHER}")),
        failed_on(OTHER)], result.stderr


#: A section with a value git dies on, in a file a `.gitmodules` includes.
INCLUDED = b'[submodule "ghost"]\n\tpath = ghost\n\tupdate = None\n'


@pytest.mark.parametrize("lost", LOST)
@pytest.mark.parametrize("kind", ("relative", "absolute"))
def test_an_include_in_a_blob_is_followed_by_neither_git_nor_bootstrap(
        family, holder, offline, tmp_path, lost, kind):
    """RV877's NIT-1. An `[include]` between MEMBER's section and OTHER's,
    in the index's file or HEAD's, which git reads where the work tree has
    none, and no credential. Git's submodule reader follows no include:
    it reads both sections and fails on the fetch for want of a
    credential. `git config --blob` follows one where it is not told
    `--no-includes`: a relative one is an error there, and bootstrap read
    MEMBER's section alone and failed; an absolute one's file, which
    gives a value git dies on, was read as the blob's own, and bootstrap
    named it and failed. Neither is followed now: the members are the
    credential's, skipped, and ok."""
    env = isolated(offline, tmp_path)
    target = tmp_path / "included.cfg"
    target.write_bytes(INCLUDED)
    path = target.name if kind == "relative" else target.as_posix()
    clone, _ = edited_clone(
        holder, env, family, tmp_path,
        lambda data: url_edited(
            data, MEMBER,
            lambda url: url + f"[include]\n\tpath = {path}\n".encode()))
    LOST[lost](clone, env)
    update = raw(clone, env, "submodule", "update", "--init", "--recursive",
                 check=False)
    said = update.stderr.decode("utf-8", "replace")
    assert re.findall(r"registered for path '([^']*)'", said) == [
        f"members/{MEMBER}", f"members/{OTHER}"], said
    assert "No url found" not in said and "invalid value" not in said, said

    assert_the_credential_s_skip(clone, env)


@pytest.mark.parametrize("lose", LOST.values(), ids=LOST)
def test_a_branch_with_no_value_in_a_blob_is_read_as_this_git_reads_it(
        family, holder, offline, tmp_path, lose):
    """A `branch` with no value, the last line of the index's file, or
    HEAD's, which git reads where the work tree has none, and no
    credential. Git 2.43.1 and later read it as a `url` with none, `bad
    config line`, an error in a blob and no die: they read every section
    before it and fail on the fetch for want of a credential, and
    bootstrap said git cannot read the file and failed; the members are
    the credential's now, skipped, and ok. Git 2.43.0 crashes on it there
    too and checks nothing out, and bootstrap names it in every row, the
    key and no value, and fails, as in the work tree's file."""
    env = isolated(offline, tmp_path)
    clone, _ = edited_clone(holder, env, family, tmp_path, with_line("branch"))
    lose(clone, env)
    update = raw(clone, env, "submodule", "update", "--init", "--recursive",
                 check=False)
    assert update.returncode != 0, "premise: no credential, or a crash"
    if b"bad config line" in update.stderr:
        assert_the_credential_s_skip(clone, env)
        return

    result = bootstrap(clone, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    why = refused_why("branch", None)
    assert result.stderr.splitlines()[-2:] == [
        not_fetched((f"members/{MEMBER}", why), (f"members/{OTHER}", why),
                    cure=value_cure("branch")),
        failed_on(MEMBER, OTHER)], result.stderr


def test_the_index_s_file_is_read_where_it_differs_from_head_s(
        family, holder, offline, tmp_path):
    """THE ISSUE'S LINE 3: git reads the index's `.gitmodules` before
    HEAD's. A plain clone with the credential, `update = None` staged and
    not committed, and the work tree's file lost: git reads the index's
    and dies, HEAD's being clean, and bootstrap names it in every row
    (rv819's finding 4)."""
    env = fetching(isolated(offline, tmp_path))
    clone = cloned(holder, env, family, tmp_path, recurse=False)
    data = raw(clone, env, "show", f"HEAD:{GITMODULES}").stdout
    (clone / GITMODULES).write_bytes(with_line("update = None")(data))
    raw(clone, env, "add", "--", GITMODULES)
    lose_work_tree_file(clone, env)
    update = raw(clone, env, "submodule", "update", "--init", "--recursive",
                 check=False)
    assert update.returncode != 0, update.stderr
    assert not (clone / "members" / MEMBER / ".git").exists(), (
        "premise: git checked nothing out")

    result = bootstrap(clone, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    why = refused_why("update", "None")
    assert result.stderr.splitlines()[-2:] == [
        not_fetched((f"members/{MEMBER}", why), (f"members/{OTHER}", why),
                    cure=value_cure("update")),
        failed_on(MEMBER, OTHER)], result.stderr


def test_a_key_with_no_value_in_a_section_git_ignores_reads_on(
        family, holder, offline, tmp_path):
    """No misfire. A section git ignores whole, first in the index's file,
    gives `url` with no value: git warns and reads on, as in the work
    tree's file, so it reads both members' sections and fails on the fetch
    for want of a credential. The members are the credential's: skipped,
    and ok (rv819's finding 4)."""
    env = isolated(offline, tmp_path)
    clone, _ = edited_clone(
        holder, env, family, tmp_path,
        lambda data: b'[submodule "../x"]\n\tpath = x\n\turl\n' + data)
    lose_work_tree_file(clone, env)
    update = raw(clone, env, "submodule", "update", "--init", "--recursive",
                 check=False)
    assert b"bad config line" not in update.stderr, update.stderr

    assert_the_credential_s_skip(clone, env)


#: `git version` lines, and whether `crashes_on_branch` says that git
#: crashes on a `branch` with no value: before 2.43.1, and where no version
#: can be read.
VERSIONS = {
    "2.43.0": ("git version 2.43.0", True),
    "2.43.1": ("git version 2.43.1", False),
    "2.42.4": ("git version 2.42.4", True),
    "apple-2.39.3": ("git version 2.39.3 (Apple Git-146)", True),
    "windows-2.43.0": ("git version 2.43.0.windows.1", True),
    "windows-2.45.1": ("git version 2.45.1.windows.1", False),
    "2.55.0": ("git version 2.55.0", False),
    "3.0.0": ("git version 3.0.0", False),
    "unread": ("git version unknown", True),
}


@pytest.mark.parametrize("version, crashes", VERSIONS.values(),
                         ids=VERSIONS)
def test_which_git_crashes_on_a_branch_with_no_value(tmp_path, version,
                                                     crashes):
    """Which git the family root's bootstrap takes for one that crashes
    on a `branch` with no value, where it reads the index's or HEAD's
    file: every git before 2.43.1, and one whose version it cannot read.
    The test above meets the git it runs on; this meets each side of the
    line."""
    assert BOOTSTRAP.crashes_on_branch(tmp_path, version) is crashes


def test_a_value_git_dies_on_in_the_index_s_file_is_named_and_mended(
        family, holder, offline, tmp_path):
    """`update = None` committed, and the work tree's file lost, not
    committed: git reads the index's and dies all the same, and bootstrap
    names it. The gate reads HEAD's, and, the work tree holding none, its
    first line puts HEAD's back before the key is taken out. Typed as
    printed and committed, the same run checks both members out and the
    gate passes in every mode."""
    env = fetching(isolated(offline, tmp_path))
    clone, _ = edited_clone(holder, env, family, tmp_path,
                            with_line("update = None"))
    lose_work_tree_file(clone, env)

    result = bootstrap(clone, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    why = refused_why("update", "None")
    assert result.stderr.splitlines()[-2:] == [
        not_fetched((f"members/{MEMBER}", why), (f"members/{OTHER}", why),
                    cure=value_cure("update")),
        failed_on(MEMBER, OTHER)], result.stderr
    found_in_every_mode_and_typed(
        clone, env,
        taken_out("update", "None", where=HEAD_ONLY, put_back=True))
    assert_a_good_holder_s_run(clone, env)


def test_two_keys_with_no_gitmodules_in_the_work_tree_put_head_s_back_once(
        holder, offline, tmp_path):
    """Two values git dies on committed, and the work tree's file lost: one
    finding for each key, and only the first puts HEAD's back, since a
    second `git checkout` would put back the key the first took out. Typed
    as printed and committed, the holder passes in every mode."""
    env = isolated(offline, tmp_path)
    data = raw(holder, env, "show", f"HEAD:{GITMODULES}").stdout
    # Each line goes in right after the url, so `update` comes first.
    committed_gitmodules(holder, env, with_line("update = None")(
        with_line("shallow = maybe")(data)))
    lose_work_tree_file(holder, env)

    result = validate(holder, "--no-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert findings(result) == [
        taken_out("update", "None", where=HEAD_ONLY, put_back=True),
        taken_out("shallow", "maybe", where=HEAD_ONLY)]
    for finding in findings(result):
        for command in commands(finding):
            type_line(holder, env, command)
    raw(holder, env, "add", "--", GITMODULES)
    commit_all(holder, env, "Both keys taken out as printed")
    assert raw(holder, env, "show", f"HEAD:{GITMODULES}").stdout == data
    assert_passes_in_every_mode(holder, 2)


# --- line 3: submodule.<name>.active and submodule.active's patterns ---------

def test_a_member_whose_own_active_is_false_is_not_where_git_stops(
        family, holder, offline, tmp_path):
    """THE ISSUE'S LINE 3, its second item. OTHER's section lost its url,
    committed; in a plain clone `submodule.active` is `.`, as a recursive
    clone sets it, so every member is in the subset, and OTHER's own
    `submodule.members/<P>.active` is set twice, true then false, of which
    git reads the last. Git asks that first, inits
    MEMBER alone and fails on its fetch for want of a credential, and stops
    nowhere; bootstrap said git stopped at OTHER. MEMBER is the
    credential's now, and OTHER, which git has no url for, is named with
    the section written back."""
    env = isolated(offline, tmp_path)
    clone, _ = edited_clone(holder, env, family, tmp_path,
                            lambda data: without_url(data, OTHER))
    raw(clone, env, "config", "submodule.active", ".")
    for flag in ("true", "false"):
        raw(clone, env, "config", "--add",
            f"submodule.members/{OTHER}.active", flag)
    update = raw(clone, env, "submodule", "update", "--init", "--recursive",
                 check=False)
    assert update.returncode != 0, "premise: the fetch failed"
    assert b"No url found" not in update.stderr, update.stderr

    result = bootstrap(clone, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stderr.splitlines()[-2:] == [
        not_fetched((f"members/{OTHER}", NO_URL),
                    cure=SECTION_CURE.format(path=f"members/{OTHER}")),
        failed_on(OTHER)], result.stderr


#: `submodule.active` patterns: `(the patterns, whether git's init then
#: asks OTHER and dies, (a)'s rows, the rows it fails on)`. A plain path,
#: however spelt, names MEMBER alone, as `git clone
#: --recurse-submodules=<path>` writes it; a leading directory names both;
#: the start of OTHER's path that is no directory of it names nothing.
PATTERNS = {
    "a-path": ((f"members/{MEMBER}",), False,
               ((f"members/{OTHER}", NO_URL),), (OTHER,)),
    "a-path-spelt-another-way": ((f"./members/{MEMBER}/",), False,
                                 ((f"members/{OTHER}", NO_URL),), (OTHER,)),
    "a-leading-directory": (("members",), True,
                            (STOPS_AT_OTHER, (f"members/{OTHER}", NO_URL)),
                            (MEMBER, OTHER)),
    "a-string-prefix": ((f"members/{MEMBER}", f"members/{OTHER[:-1]}"),
                        False, ((f"members/{OTHER}", NO_URL),), (OTHER,)),
}


@pytest.mark.parametrize("patterns, stops, left, failed", PATTERNS.values(),
                         ids=PATTERNS)
def test_a_subset_s_pattern_says_whether_git_stops_at_a_member_outside_it(
        family, holder, offline, tmp_path, patterns, stops, left, failed):
    """THE ISSUE'S LINE 3, its third item. OTHER's section lost its url,
    committed, and the clone's subset is `patterns`, with no credential.
    Where the pattern leaves OTHER out, git's init skips it and fails on
    MEMBER's fetch, and bootstrap said git stopped at OTHER; MEMBER is the
    credential's now. Where it names OTHER, git does die there, and that
    is still said."""
    env = isolated(offline, tmp_path)
    clone, _ = edited_clone(holder, env, family, tmp_path,
                            lambda data: without_url(data, OTHER))
    for pattern in patterns:
        raw(clone, env, "config", "--add", "submodule.active", pattern)
    update = raw(clone, env, "submodule", "update", "--init", "--recursive",
                 check=False)
    assert (f"No url found for submodule path 'members/{OTHER}'".encode()
            in update.stderr) is stops, update.stderr

    result = bootstrap(clone, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stderr.splitlines()[-2:] == [
        not_fetched(*left, cure=SECTION_CURE.format(path=f"members/{OTHER}")),
        failed_on(*failed)], result.stderr


# --- the gate: which file gives it, and what is written back -----------------

def mended_not_committed(root, env, data: bytes) -> None:
    """`update = None` committed, the work tree's file mended by hand."""
    committed_gitmodules(root, env, with_line("update = None")(data))
    (root / GITMODULES).write_bytes(data)


def edited_not_committed(root, env, data: bytes) -> None:
    """`update = None` in the work tree's file alone."""
    (root / GITMODULES).write_bytes(with_line("update = None")(data))


WHERE = {
    "head-only": (mended_not_committed,
                  said("update", "None", HEAD_ONLY) + "Stage and commit the "
                  "work tree's .gitmodules, which does not give it."),
    "work-tree-only": (edited_not_committed,
                       taken_out("update", "None", where=WORK_TREE_ONLY)),
}


@pytest.mark.parametrize("set_up, expected", WHERE.values(), ids=WHERE)
def test_the_gate_says_which_file_gives_it(holder, offline, tmp_path, set_up,
                                           expected):
    """In the holder, members checked out: HEAD's file alone gives the
    value, the work tree's mended and not committed, and the finding says
    to commit that, printing no command; or the work tree's alone, which
    git reads here and a clone does not, and the command takes it out with
    nothing to commit. Done as it says, the holder passes in every mode."""
    env = isolated(offline, tmp_path)
    set_up(holder, env, raw(holder, env, "show", f"HEAD:{GITMODULES}").stdout)

    result = validate(holder, "--no-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert findings(result) == [expected]
    for command in commands(expected):
        type_line(holder, env, command)
    raw(holder, env, "add", "--", GITMODULES)
    raw(holder, env, "commit", "-q", "--allow-empty", "-m", "As it says")
    assert_passes_in_every_mode(holder, 2)


def test_a_url_no_row_gives_one_for_is_written_back_as_a_placeholder(
        holder, offline, tmp_path):
    """OTHER's row gives no `<org>/<Name>` repository, and its section's
    only `url` line has no value, both committed: there is no url as
    `family.py add` writes one, so the finding writes back `<url>` for a
    person to fill in, as `member-gitmodules-absent` does (rv819's finding
    4)."""
    env = isolated(offline, tmp_path)
    rows = (holder / "family.yaml").read_bytes()
    qualified = f"repository: {ORG}/{OTHER}".encode()
    assert rows.count(qualified) == 1, rows
    (holder / "family.yaml").write_bytes(
        rows.replace(qualified, f"repository: {OTHER}".encode()))
    raw(holder, env, "add", "--", "family.yaml")
    data = raw(holder, env, "show", f"HEAD:{GITMODULES}").stdout
    committed_gitmodules(holder, env, replaced("url")(data))

    result = validate(holder, "--no-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert findings(result)[0] == taken_out("url", None, back="<url>")


def test_a_value_head_s_file_alone_gives_leaves_the_work_tree_s_read(
        holder, offline, tmp_path):
    """HEAD's file alone gives `update = None`, and the work tree's,
    mended and not committed, gives OTHER's path in a second section. Git
    reads the work tree's here, so `gitmodules-path-twice` still reads it
    and names the two: only a value in the work tree's file stops that
    reading (rv819's finding 4)."""
    env = isolated(offline, tmp_path)
    data = raw(holder, env, "show", f"HEAD:{GITMODULES}").stdout
    committed_gitmodules(holder, env, with_line("update = None")(data))
    (holder / GITMODULES).write_bytes(data + DUPLICATE)

    result = validate(holder, "--no-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert [found.split(":")[0] for found in findings(result)] == [
        "FINDING gitmodules-value-refused", "FINDING gitmodules-path-twice"]


#: OTHER's `url` or `path` line replaced by the key with no value, so the
#: section gives none git takes: `(edit, key, the value written back, the
#: findings after it)`. The url is `family.py add`'s for the row; the path
#: is the section's name. With no path, no section of HEAD's file gives
#: OTHER's, which `member-gitmodules-absent` says too, and its line writes
#: the same path again.
def replaced(key: str, before: bytes = b""):
    """An edit replacing OTHER's `key` line with `before`, then the key
    with no value."""
    pattern = re.compile(rb"(\[submodule \"members/" + OTHER.encode()
                         + rb"\"\]\r?\n(?:\t[^\n]*\n)*?)\t" + key.encode()
                         + rb" = [^\n]*\n")
    return lambda data: pattern.sub(
        lambda found: found.group(1) + before + f"\t{key}\n".encode(), data,
        count=1)


#: `(edit, key, the value written back, the findings after it)`. A url git
#: drops, one that begins with `-`, is no url to write back (rv819's
#: finding 4).
WRITTEN_BACK = {
    "url": (replaced("url"), "url",
            f"https://github.com/InkRouter/{OTHER}.git", ()),
    "path": (replaced("path"), "path", f"members/{OTHER}",
             ("member-gitmodules-absent",)),
    "url-after-a-dashed-one": (
        replaced("url", b"\turl = -bad\n"), "url",
        f"https://github.com/InkRouter/{OTHER}.git", ()),
}


@pytest.mark.parametrize("edit, key, back, beside", WRITTEN_BACK.values(),
                         ids=WRITTEN_BACK)
def test_a_url_or_path_left_with_no_value_is_written_back_as_add_writes_it(
        holder, offline, tmp_path, edit, key, back, beside):
    """The section's only `url` or `path` line has no value, committed:
    taking the key out would leave the member none, so the finding writes
    it back after, as `family.py add` writes it, never a url git drops.
    The work tree's file gives the value too, so no other check of it is
    asked, and no `gitmodules-path-unnamed` takes the member's section out
    by key. Typed as printed and committed, the holder passes in every
    mode."""
    env = isolated(offline, tmp_path)
    data = raw(holder, env, "show", f"HEAD:{GITMODULES}").stdout
    committed_gitmodules(holder, env, edit(data))

    result = validate(holder, "--no-members")

    assert result.returncode == 1, result.stdout + result.stderr
    found = findings(result)
    assert found[0] == taken_out(key, None, back=back)
    assert [code.split(":")[0][len("FINDING "):]
            for code in found[1:]] == list(beside)
    for finding in found:
        for command in commands(finding):
            type_line(holder, env, command)
    raw(holder, env, "add", "--", GITMODULES)
    commit_all(holder, env, "Written back as printed")
    assert_passes_in_every_mode(holder, 2)



def test_a_probe_value_in_the_person_s_own_config_changes_no_answer(
        family, holder, offline, tmp_path):
    """Both tools ask git whether a value is a boolean through a key of
    their own, `probe.value`. One the person's own config gives, here no
    boolean, made both refuse `shallow = true` (rv819's NIT 9): bootstrap
    named every row and failed, and the gate found
    `gitmodules-value-refused`. Neither reads it now: the members are the
    credential's, skipped, and ok, and the gate passes."""
    env = with_config(isolated(offline, tmp_path), "probe.value", "notabool")
    clone, _ = edited_clone(holder, env, family, tmp_path,
                            with_line("shallow = true"))

    assert_the_credential_s_skip(clone, env)
    gate = run_script(clone / "scripts" / "validate-family.py",
                      "--no-members", cwd=clone, env=env)
    assert gate.returncode == 0, gate.stdout + gate.stderr


# --- beside #762's staged removal --------------------------------------------

def test_a_staged_removal_beside_a_refused_value_puts_no_section_back(
        on_main, offline, tmp_path):
    """#768 BESIDE #762, the point rv820 asked the second PR to land
    (resolution point 3 of the merge with main `b9b70692`). The work tree's
    file gives OTHER's section `update = None`, which git dies on, and
    `git rm --cached` has staged MEMBER's gitlink out, taking no section
    from `.gitmodules`. The gate reads no section from a file it refuses
    (`sections` is emptied), and the finding for the removal read that as
    a section `git rm` took out: it printed `git checkout HEAD --
    .gitmodules` and said it put the section back. It is handed the
    sections as read, so it prints the reset alone, in every mode."""
    env = isolated(offline, tmp_path)
    commit = pinned(on_main, MEMBER)
    raw(on_main, env, "rm", "-q", "--cached", "--", ROW)
    edited_not_committed(
        on_main, env, raw(on_main, env, "show", f"HEAD:{GITMODULES}").stdout)
    expected = [taken_out("update", "None", where=WORK_TREE_ONLY),
                removal_staged(on_main, commit, "git-rm-cached")]

    for extra in ((), ("--pins",), ("--no-members",)):
        result = validate(on_main, *extra)
        assert result.returncode == 1, (extra, result.stdout + result.stderr)
        assert findings(result) == expected, extra
        staged = findings(result)[1]
        assert commands(staged) == [f"git reset -q -- {ROW}"], extra
        assert f"git checkout HEAD -- {GITMODULES}" not in staged, extra


# --- the rules both scripts write, held to one answer (#856) ----------------

#: Each key either script asks about, and one neither does, which takes any
#: value.
KEYS = ("path", "url", "update", "ignore", "branch", "shallow",
        "fetchrecursesubmodules", "active")

#: ONE TABLE of `(key, value)` cases, None for a key with no value, which
#: the parity tests run through both scripts' rules (#856): each key with
#: no value and with an empty one; each value a rule names and others
#: beside it, in another case, with a space, as a command; the numbers
#: either side of git's int range; every value #819's runs measured, the
#: `update` typo and command, the `shallow` numbers and `ON-DEMAND`
#: refused, the `branch` and `ignore` values taken; a `path` and a `url`
#: git drops, which no rule refuses; and a key in a case `git config
#: --list` never prints. It holds inputs, not answers: the parity tests
#: hold the two scripts' answers to each other, and the tests above hold
#: each script to git.
VALUE_CASES = (
    *((key, None) for key in KEYS),
    *((key, "") for key in KEYS),
    *(("update", value) for value in (
        "none", "checkout", "rebase", "merge", "None", "Merge", "!true",
        " none", "none ")),
    *(("shallow", value) for value in (
        "true", "false", "TRUE", "yes", "off", "1", "0", " 1", "1 ", "0x10",
        "010", "1k", "2097151k", "-2097151k", "maybe", "08", "3000000000",
        "2097152k", "-2097152k", "-2097153k", "on-demand")),
    *(("fetchrecursesubmodules", value) for value in (
        "on-demand", "ON-DEMAND", "true", "0", "bogus", "maybe")),
    *(("ignore", value) for value in (
        "untracked", "dirty", "all", "none", "bogus")),
    ("path", f"members/{OTHER}"), ("path", "-x"),
    ("url", f"https://github.com/{ORG}/{OTHER}.git"), ("url", "-bad"),
    ("branch", "main"), ("branch", "."), ("branch", "-x"),
    ("active", "maybe"), ("fetchRecurseSubmodules", "bogus"),
)


def case_id(case: tuple[str, str | None]) -> str:
    """A case's id: its key, then its value as Python writes it."""
    key, value = case
    return f"{key}=" + ("(none)" if value is None else repr(value))


@pytest.fixture(scope="module")
def anywhere(tmp_path_factory):
    """A folder for both scripts' boolean probes to run git in: they read
    an empty file and no repository."""
    return tmp_path_factory.mktemp("parity")


@pytest.mark.parametrize("key, value", VALUE_CASES,
                         ids=list(map(case_id, VALUE_CASES)))
def test_both_scripts_give_each_value_one_answer(anywhere, key, value):
    """THE ISSUE'S SECOND LINE (#856). Which values git dies on is written
    in bootstrap, `refused_value` and `git_bool`, and in the gate,
    `_values_refused` and `_git_takes_bool`, and a change made in one was
    a defect in the other until somebody made it there too. Each case is
    asked of both, and of each one's boolean probe where there is a value:
    one answer, or this fails."""
    gate = GATE._values_refused(anywhere, [(f"members/{OTHER}", key, value)])
    bootstrap_said = (
        BOOTSTRAP.refused_value(anywhere, key, value),
        None if value is None else BOOTSTRAP.git_bool(anywhere, value)
        is not None)
    gate_said = (bool(gate), None if value is None
                 else GATE._git_takes_bool(anywhere, value))

    assert bootstrap_said == gate_said


def test_both_scripts_say_one_thing_of_what_git_takes(anywhere):
    """What git takes for each key it refuses a value of is written in
    bootstrap's `TAKES` and the gate's `GIT_TAKES`, one text each, which
    this file reads from bootstrap (#856). The table reaches every key
    they name, refused and taken; every key refused in it has its text,
    which both look up to say it; and it holds each key bootstrap refuses
    with no value and each `update` value it takes.

    A TEXT CHANGED THE SAME WAY IN BOTH is held to the scripts' own data
    where they have it (RV877's NIT-2): every `update` value bootstrap
    takes is named in its text, and no value a text names is one the
    rules refuse for its key. The `ignore` values have no list in either
    script, git taking any `ignore` with a warning, so a text that drops
    one passes still."""
    refused = {(key, value) for key, value in VALUE_CASES
               if BOOTSTRAP.refused_value(anywhere, key, value)}
    taken = set(VALUE_CASES) - refused
    named = {key: re.findall(r"`([^`]*)`", text)
             for key, text in TAKES.items()}

    assert BOOTSTRAP.TAKES == GATE.GIT_TAKES
    assert {key for key, _ in refused} == set(TAKES)
    assert {key for key, _ in taken} >= set(TAKES)
    assert {(key, None) for key in BOOTSTRAP.NO_VALUE_REFUSED} <= refused
    assert {("update", value) for value in BOOTSTRAP.UPDATE_VALUES} <= taken
    assert set(BOOTSTRAP.UPDATE_VALUES) <= set(named["update"])
    assert [(key, value) for key, values in named.items() for value in values
            if BOOTSTRAP.refused_value(anywhere, key, value)] == []
