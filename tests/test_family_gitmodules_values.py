# SPDX-License-Identifier: Apache-2.0
"""A `.gitmodules` value git dies on as it reads the file, in a family
holder's own bootstrap and gate, and where git reads the file from (#768).

THE ISSUE'S THREE LINES, each reproduced on #682's head f74f640c first:

- Bootstrap said `family bootstrap ok`, exit 0, where git dies reading
  `.gitmodules` before it checks out any member: an `update = None` (the
  typo of `update = none`), an `update = !true`, a `url`, `update`,
  `ignore` or `branch` with no value (git 2.43 crashes on the last), a
  `shallow = maybe`, a `fetchRecurseSubmodules = bogus`. It names every
  row with the key and its value now, and fails, where every member was
  checked out too.
- The family gate named none of them: members checked and `--pins`
  refused `member-uninitialized`, whose remedy is the update that dies,
  and `--no-members` said `family ok`. Every mode finds
  `gitmodules-value-refused` now, read from the work tree's file and
  HEAD's, and its commands take the key out.
- What #682 left approximate: where the work tree has no `.gitmodules`,
  git reads the index's, then HEAD's; a section's own
  `submodule.<name>.active` decides before `submodule.active`'s patterns;
  and a plain path pattern names only itself and what is under it.

THE SAME FAMILY, OFFLINE RULES AND STATES as
`test_family_bootstrap_gate_order.py` (#648), whose helpers are imported:
a plain clone of the holder, `git submodule update` given the fixture's
local members (`fetching`) where a credential is said to be there and not
given them where it is not. Every printed command is typed as printed.
"""

from __future__ import annotations

import re

import pytest

from repo_shape import PYTHON
from test_family import family, validate  # noqa: F401
from test_family_add_refusals import holder, offline  # noqa: F401
from test_family_bootstrap_gate_order import (
    CHECKOUT_CURE, EXITED_0, FETCHED, NO_URL, NOT_ALL_FETCHED, SECTION_CURE,
    STOPPED, after_first_line, bootstrap, cloned, edited_clone, failed_on,
    fetching, not_fetched, type_line, url_edited, without_url,
)
from test_family_dry_run import isolated
from test_family_head_lost_gitmodules import (
    GITMODULES, assert_passes_in_every_mode, commit_all, committed_gitmodules,
)
from test_family_member_path import MEMBER, OTHER, raw
from test_validate_family_unnamed_mounts import commands, findings

#: The issue's table, `update = None` first, then `branch` with no value,
#: which git 2.43 crashes on (w768's probe): each a line added to OTHER's
#: section after its url, as rv648 (p11) and w648c (p12) added it, the key
#: git lists for it, the value, None for none, and git's update's exit.
REFUSED_LINES = {
    "update-None": ("update = None", "update", "None", 128),
    "update-command": ("update = !true", "update", "!true", 128),
    "url-no-value": ("url", "url", None, 128),
    "update-no-value": ("update", "update", None, 128),
    "ignore-no-value": ("ignore", "ignore", None, 128),
    "shallow-maybe": ("shallow = maybe", "shallow", "maybe", 128),
    "fetch-bogus": ("fetchRecurseSubmodules = bogus",
                    "fetchrecursesubmodules", "bogus", 128),
    "branch-no-value": ("branch", "branch", None, 139),
}

#: What both tools say git takes for each key.
TAKES = {"update": "one of `none`, `checkout`, `rebase` or `merge`",
         "shallow": "a boolean, `true` or `false`",
         "fetchrecursesubmodules": "a boolean or `on-demand`",
         "ignore": "one of `untracked`, `dirty`, `all` or `none`",
         "path": "a path", "url": "a url", "branch": "a branch name"}

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
    """`gitmodules-value-refused` up to its remedy."""
    given = "no value" if value is None else f"the value `{value}`"
    return (f"FINDING gitmodules-value-refused: .gitmodules gives "
            f"`{full(key)}` {given} {where}, and git dies reading a file "
            "that does, before `git submodule update` checks out any "
            "member, so neither that nor make bootstrap checks one out. Git "
            f"takes {TAKES[key]} for that key. ")


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


# --- lines 1 and 2: bootstrap and the gate ----------------------------------

@pytest.mark.parametrize("line, key, value, code", REFUSED_LINES.values(),
                         ids=REFUSED_LINES)
def test_a_value_git_dies_on_fails_bootstrap_and_every_mode_of_the_gate(
        family, holder, offline, tmp_path, line, key, value, code):
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
    assert update.returncode == code, update.stderr
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
    expected = taken_out(key, value,
                         back=url_of(data) if key == "url" else None)
    for extra in ((), ("--pins",), ("--no-members",)):
        gate = validate(clone, *extra)
        assert gate.returncode == 1, (extra, gate.stdout + gate.stderr)
        assert findings(gate) == [expected], extra
    typed_and_committed(clone, env, expected)
    assert raw(clone, env, "show", f"HEAD:{GITMODULES}").stdout == data

    again = bootstrap(clone, env, "--skip-members")

    assert again.returncode == 0, again.stdout + again.stderr
    assert after_first_line(again) == FETCHED
    assert_passes_in_every_mode(clone, 2)


#: Values git takes, which no line or finding names (the issue's no-misfire
#: cases but `update = none`, whose run is the exit-0 skip as before).
TAKEN = {"update-checkout": "update = checkout",
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
#: (`ignoring suspicious submodule name`): no row names its path.
IGNORED = b'[submodule "../x"]\n\tpath = x\n\tupdate = None\n'


def test_a_value_in_a_section_git_ignores_whole_is_no_finding(
        family, holder, offline, tmp_path):
    """No misfire. A section whose name has a `..` component is ignored
    whole by git, a value it would die on included. With no credential,
    the members are the credential's: skipped, and ok. With it, the plain
    clone's update warns and checks both members out, bootstrap is a good
    holder's, and the gate names the section as one no row names, not as a
    value git refuses."""
    env = isolated(offline, tmp_path)
    clone, _ = edited_clone(holder, env, family, tmp_path,
                            lambda data: data + IGNORED)
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
    expected = taken_out("update", "None", where=HEAD_ONLY, put_back=True)
    for extra in ((), ("--pins",), ("--no-members",)):
        gate = validate(clone, *extra)
        assert gate.returncode == 1, (extra, gate.stdout + gate.stderr)
        assert findings(gate) == [expected], extra
    typed_and_committed(clone, env, expected)

    again = bootstrap(clone, env, "--skip-members")

    assert again.returncode == 0, again.stdout + again.stderr
    assert after_first_line(again) == FETCHED
    assert_passes_in_every_mode(clone, 2)


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
    `submodule.members/<P>.active` is false. Git asks that first, inits
    MEMBER alone and fails on its fetch for want of a credential, and stops
    nowhere; bootstrap said git stopped at OTHER. MEMBER is the
    credential's now, and OTHER, which git has no url for, is named with
    the section written back."""
    env = isolated(offline, tmp_path)
    clone, _ = edited_clone(holder, env, family, tmp_path,
                            lambda data: without_url(data, OTHER))
    raw(clone, env, "config", "submodule.active", ".")
    raw(clone, env, "config", f"submodule.members/{OTHER}.active", "false")
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


#: `submodule.active` patterns: `(the pattern, whether git's init then asks
#: OTHER and dies, (a)'s rows, the rows it fails on)`. A plain path, however
#: spelt, names MEMBER alone, as `git clone --recurse-submodules=<path>`
#: writes it; a leading directory names both.
STOPS_AT_OTHER = (f"members/{MEMBER}", STOPPED.format(path=f"members/{OTHER}"))
PATTERNS = {
    "a-path": (f"members/{MEMBER}", False,
               ((f"members/{OTHER}", NO_URL),), (OTHER,)),
    "a-path-spelt-another-way": (f"./members/{MEMBER}/", False,
                                 ((f"members/{OTHER}", NO_URL),), (OTHER,)),
    "a-leading-directory": ("members", True,
                            (STOPS_AT_OTHER, (f"members/{OTHER}", NO_URL)),
                            (MEMBER, OTHER)),
}


@pytest.mark.parametrize("pattern, stops, left, failed", PATTERNS.values(),
                         ids=PATTERNS)
def test_a_subset_s_pattern_says_whether_git_stops_at_a_member_outside_it(
        family, holder, offline, tmp_path, pattern, stops, left, failed):
    """THE ISSUE'S LINE 3, its third item. OTHER's section lost its url,
    committed, and the clone's subset is `pattern`, with no credential.
    Where the pattern leaves OTHER out, git's init skips it and fails on
    MEMBER's fetch, and bootstrap said git stopped at OTHER; MEMBER is the
    credential's now. Where it names OTHER, git does die there, and that
    is still said."""
    env = isolated(offline, tmp_path)
    clone, _ = edited_clone(holder, env, family, tmp_path,
                            lambda data: without_url(data, OTHER))
    raw(clone, env, "config", "submodule.active", pattern)
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


#: OTHER's `url` or `path` line replaced by the key with no value, so the
#: section gives none git takes: `(edit, key, the value written back, the
#: findings after it)`. The url is `family.py add`'s for the row; the path
#: is the section's name. With no path, no section of HEAD's file gives
#: OTHER's, which `member-gitmodules-absent` says too, and its line writes
#: the same path again.
def replaced(key: str):
    pattern = re.compile(rb"(\[submodule \"members/" + OTHER.encode()
                         + rb"\"\]\r?\n(?:\t[^\n]*\n)*?)\t" + key.encode()
                         + rb" = [^\n]*\n")
    return lambda data: pattern.sub(
        lambda found: found.group(1) + f"\t{key}\n".encode(), data, count=1)


WRITTEN_BACK = {
    "url": ("url", f"https://github.com/InkRouter/{OTHER}.git", ()),
    "path": ("path", f"members/{OTHER}", ("member-gitmodules-absent",)),
}


@pytest.mark.parametrize("key, back, beside", WRITTEN_BACK.values(),
                         ids=WRITTEN_BACK)
def test_a_url_or_path_left_with_no_value_is_written_back_as_add_writes_it(
        holder, offline, tmp_path, key, back, beside):
    """The section's only `url` or `path` line has no value, committed:
    taking the key out would leave the member none, so the finding writes
    it back after, as `family.py add` writes it. The work tree's file
    gives the value too, so no other check of it is asked, and no
    `gitmodules-path-unnamed` takes the member's section out by key.
    Typed as printed and committed, the holder passes in every mode."""
    env = isolated(offline, tmp_path)
    data = raw(holder, env, "show", f"HEAD:{GITMODULES}").stdout
    committed_gitmodules(holder, env, replaced(key)(data))

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
