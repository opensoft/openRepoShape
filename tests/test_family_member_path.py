# SPDX-License-Identifier: Apache-2.0
"""`family.py bump` and `remove` act on the one path a member can have, or
refuse (#299).

Both verbs took the member's path from the manifest row's `path:` and handed
it to git as a PATHSPEC, with no check and no `--literal-pathspecs`. The tool
writes that field itself, as `members/<project>` and nothing else, so a
different value is a hand edit; and a hand edit to `path: members/*` made
`remove --member Atlas` exit 0 with ONE commit that unmounted every member
while dropping only Atlas's row, and `path: .` made it `git rm -r -f` the
holder's own files and die on the missing manifest. `validate-family.py` has a
rule for it (`member-path`), but it runs after a commit, never in front of
these two verbs. So they refuse `member-path` themselves, before any git call
and any write; and every git call that takes the path takes it literally (the
global `--literal-pathspecs` on `deinit`, `rm` and `diff`; per-pathspec
`:(literal)` on the commit, which runs the holder's hooks and must not hand
them `GIT_LITERAL_PATHSPECS`), which does not depend on the row being right.

THE ISSUE'S MEMBERS ARE `Atlas` AND `Borg`; this family's are `IRRS` and
`IRSS`, so `IRRS` is the row a test edits and `IRSS` is the neighbour that must
be left as it was. The same family, rules and offline environment as
`test_family.py`, `test_family_add_refusals.py` and
`test_family_add_excludes.py`: members are scaffolded into local bare
repositories, nothing is created on GitHub, a `gh` on PATH logs and exits 97,
and the operator's git configuration is a file of the test's own
(`GIT_CONFIG_GLOBAL`, `GIT_CONFIG_NOSYSTEM`). No test pushes to the fixture's
own remotes.

THE ROW'S PROJECT HAS TO BE A DIRECTORY NAME TOO. A row hand-edited to
`project: .` and `path: members/.`, or `project: ..` and `path: members/..`,
IS `members/<project>` and passes the comparison above; `remove --member .`
then unmounted every member in one commit naming one, and `--member ..` `git
rm -r -f`'d the holder's root and died on the missing manifest. The same
`member-path` refusal covers them (the second commit of #299).

A refusal is asked of the holder the way `test_family_add_refusals.py` asks it
of `add`: not "is the sentence printed" but "is everything exactly as it was",
down to the bytes of `git ls-files -s -z` and `git status --porcelain=v1 -z`,
with the hand edit itself still sitting uncommitted in the work tree.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import git, run_script
#: The family fixture, its names and the offline environment, imported from
#: the modules that own them rather than rebuilt: a holder made any other way
#: would test a different holder.
from test_family import (  # noqa: F401
    FAMILY, MEMBERS, NAME, ORG, SPARE, commit_in_member, family,
    family_module, manifest, validate,
)
from test_family_add_excludes import empty_holder  # noqa: F401
from test_family_add_refusals import (  # noqa: F401
    holder, offline, refusal, snapshot,
)
from test_scaffold_ignored_shape_files import excluding

#: The row a test edits, and the neighbour that must come out untouched.
MEMBER, OTHER = MEMBERS
GLOB = "members/*"

#: What a hand edit can leave in `path:`. Each is a string `validate-family.py`
#: refuses as `member-path`, and each is one a verb used to act on: a glob
#: over every member, the holder itself, a NEIGHBOUR'S path (no glob needed to
#: unmount the wrong member), the member's own path with a trailing slash
#: (git reads it as the same path) and in another case (a case-insensitive disk
#: reads it as the same path). The comparison is exact, as the validator's is.
SPELLINGS = {
    "glob": GLOB,
    "dot": ".",
    "neighbour": f"members/{OTHER}",
    "trailing-slash": f"members/{MEMBER}/",
    "case": f"members/{MEMBER.lower()}",
}

#: A name Windows refuses in a file name: `*` is one of the characters its
#: file systems reserve. Only the test that needs a directory of that name is
#: skipped there; every refusal row needs none and runs everywhere.
NO_STAR_FILES = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows refuses `*` in a file name, so the directory `members/*` "
           "this test makes cannot exist there; every other test in this "
           "module needs no such directory and runs on every platform")


def isolated(offline, tmp_path: Path) -> dict:
    """`offline`'s environment plus a git configuration that is the test's
    own: no run here reads the global or the system configuration of whoever
    runs the suite, and every commit has an identity to be made under."""
    return {**offline.env, **excluding(tmp_path / "operator", b""),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t.invalid",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t.invalid"}


def raw(root: Path, env: dict, *args: str,
        check: bool = True) -> subprocess.CompletedProcess:
    """`git` in `root` under `env`, its output as BYTES."""
    proc = subprocess.run(["git", *args], cwd=str(root), capture_output=True,
                          check=False, env={**os.environ, **env})
    if check:
        assert proc.returncode == 0, (f"git {' '.join(args)} in {root}:\n"
                                      f"{proc.stderr!r}")
    return proc


def hand_edit(root: Path, project: str, path: str | None) -> None:
    """`project`'s row in `family.yaml` given `path:` `path` (or none when
    `path` is None), UNCOMMITTED: what a person who edits the manifest by hand
    leaves behind. The manifest reads it back as typed, so a test is never
    about a value the reader changed on the way."""
    manifest_path = root / "family.yaml"
    text = manifest_path.read_bytes().decode("utf-8")
    line = f"    path: members/{project}\n"
    assert text.count(line) == 1, "fixture drift: the row's own path line"
    manifest_path.write_bytes(text.replace(
        line, "" if path is None else f"    path: {path}\n").encode("utf-8"))
    row = {r["project"]: r for r in manifest(root)["members"]}[project]
    assert row.get("path") == path


def hand_edit_project(root: Path, project: str, as_project: str) -> None:
    """`project`'s row renamed to `as_project` AND given the path that name
    makes, `members/<as_project>`: the two hand edits that leave a row equal
    to the path the tool would compute for it. UNCOMMITTED, as `hand_edit`
    leaves it."""
    manifest_path = root / "family.yaml"
    text = manifest_path.read_bytes().decode("utf-8")
    for old, new in (
            (f"  - project: {project}\n", f"  - project: {as_project}\n"),
            (f"    path: members/{project}\n",
             f"    path: members/{as_project}\n")):
        assert text.count(old) == 1, "fixture drift: the row's own lines"
        text = text.replace(old, new)
    manifest_path.write_bytes(text.encode("utf-8"))
    row = {r["project"]: r for r in manifest(root)["members"]}[as_project]
    assert row["path"] == f"members/{as_project}"


def state(root: Path, env: dict) -> dict:
    """Everything a refused verb must leave exactly as it found it."""
    return {
        "HEAD": raw(root, env, "rev-parse", "HEAD").stdout,
        "index": raw(root, env, "ls-files", "-s", "-z").stdout,
        "status": raw(root, env, "status", "--porcelain=v1", "-z").stdout,
        "family.yaml": (root / "family.yaml").read_bytes(),
        "the rest": snapshot(root),
    }


def commits(root: Path, env: dict) -> int:
    return int(raw(root, env, "rev-list", "--count", "HEAD").stdout)


def committed(root: Path, env: dict) -> set[str]:
    return set(raw(root, env, "show", "--name-only", "--format=", "HEAD"
                   ).stdout.decode("utf-8").split())


def older(family) -> str:
    """A commit of `MEMBER` that is not the one the holder pins, so a bump to
    it has something to record."""
    return git("rev-parse", "main~1", cwd=family["remotes"] / f"{MEMBER}.git"
               ).stdout.strip()


def verb_args(verb: str, root: Path, family) -> list[str]:
    extra = ["--to", older(family)] if verb == "bump" else []
    return [verb, "--family-root", str(root), "--member", MEMBER, *extra]


def neighbour_intact(root: Path, env: dict) -> None:
    """The member NOT named is still mounted, pinned and checked out."""
    entry = raw(root, env, "ls-tree", "HEAD", "--", f"members/{OTHER}"
                ).stdout
    assert entry.startswith(b"160000 commit "), entry
    assert [r["project"] for r in manifest(root)["members"]] == list(MEMBERS)
    assert (root / "members" / OTHER / "project.yaml").is_file()


# --- the refusal ------------------------------------------------------------

@pytest.mark.parametrize("spelling", SPELLINGS.values(), ids=SPELLINGS)
@pytest.mark.parametrize("verb", ["remove", "bump"])
def test_a_row_whose_path_is_not_the_members_is_refused_and_nothing_moves(
        family, holder, offline, tmp_path, verb, spelling):
    """THE ISSUE'S PROBES. `remove` with `path: members/*` exited 0 with ONE
    commit that deleted every member's gitlink; with `path: .` it removed the
    holder's own files and died with a traceback. Now: exit 2, the refusal
    the validator's own finding is named for, the row's value and the
    expected one in it, the remedy that puts the field back, and the holder
    byte for byte as it was, the hand edit still uncommitted."""
    env = isolated(offline, tmp_path)
    hand_edit(holder, MEMBER, spelling)
    assert raw(holder, env, "status", "--porcelain=v1", "-z").stdout == (
        b" M family.yaml\0"), "premise: the hand edit is the only change"
    before = state(holder, env)

    result = run_script(FAMILY, *verb_args(verb, holder, family), env=env)

    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == "", "refused before anything was reported"
    said, remedy = refusal(result.stderr)
    assert said == (
        f"REFUSED member-path: {MEMBER}: path is {spelling!r} in family.yaml, "
        f"expected 'members/{MEMBER}'. Git would read that value as a "
        "pathspec, so no git command was run and nothing was written.")
    assert remedy == (
        "Remediation: this tool writes that field itself, so a different "
        f"value is a hand edit. Put `path: members/{MEMBER}` back in "
        "family.yaml, or `git checkout -- family.yaml` if the edit is not "
        "committed, then run the same command again.")
    assert state(holder, env) == before
    neighbour_intact(holder, env)
    assert not offline.gh_log.exists(), offline.gh_log.read_text()


@pytest.mark.parametrize("verb", ["remove", "bump"])
def test_the_refusal_is_made_before_any_git_call(
        family, holder, offline, tmp_path, monkeypatch, capsys, verb):
    """"Nothing was written" is what the holder shows; this is the other half
    of the ruling, that no git command is RUN either. Run in this process with
    every subprocess forbidden: a verb that reached git before the check
    fails here on the call, whatever the end state says."""
    module = family_module()
    hand_edit(holder, MEMBER, GLOB)
    before = (holder / "family.yaml").read_bytes()
    args = verb_args(verb, holder, family)

    def forbidden(argv, *rest, **named):
        raise AssertionError(f"a program was run before the refusal: {argv}")

    monkeypatch.setattr(subprocess, "run", forbidden)
    assert module.main(args) == 2
    err = capsys.readouterr().err
    assert err.startswith("REFUSED member-path: ")
    assert (holder / "family.yaml").read_bytes() == before


@NO_STAR_FILES
def test_bump_refuses_a_row_naming_a_directory_that_is_really_there(
        family, holder, offline, tmp_path):
    """THE ISSUE'S ONE WAY `bump` GOT PAST ITS OWN `member-uninitialized`: a
    checkout, `.git` and all, in a directory literally named `members/*`. It
    then fetched and checked that out at `--to`, and staged and committed it
    as a gitlink of its own. The refusal comes before all of that: the clone
    stays where it was."""
    env = isolated(offline, tmp_path)
    git("clone", "-q", str(family["remotes"] / f"{MEMBER}.git"), GLOB,
        cwd=holder)
    star = holder / "members" / "*"
    assert (star / ".git").exists(), "premise: the literal checkout is there"
    tip = raw(star, env, "rev-parse", "HEAD").stdout
    hand_edit(holder, MEMBER, GLOB)
    before = state(holder, env)

    result = run_script(FAMILY, *verb_args("bump", holder, family), env=env)

    assert result.returncode == 2, result.stdout + result.stderr
    assert refusal(result.stderr)[0].startswith("REFUSED member-path: ")
    assert raw(star, env, "rev-parse", "HEAD").stdout == tip
    assert state(holder, env) == before
    neighbour_intact(holder, env)


DOT_ROWS = {
    "dot": (".", "the members directory itself"),
    "dotdot": ("..", "the holder's root"),
}


@pytest.mark.parametrize("project, names", DOT_ROWS.values(), ids=DOT_ROWS)
@pytest.mark.parametrize("verb", ["remove", "bump"])
def test_a_row_whose_project_is_not_a_directory_name_is_refused(
        family, holder, offline, tmp_path, verb, project, names):
    """`project: .` with `path: members/.`, and `project: ..` with `path:
    members/..`: the row's path EQUALS `members/<project>`, so only the
    project can be refused. `remove` used to exit 0 with one commit deleting
    every member's gitlink for the first, and to stage the holder's own files
    for deletion and die on a `FileNotFoundError` for the second. Now the
    same `member-path` refusal, exit 2, and the holder byte for byte as it
    was, both members still mounted, pinned and checked out."""
    env = isolated(offline, tmp_path)
    hand_edit_project(holder, MEMBER, project)
    assert raw(holder, env, "status", "--porcelain=v1", "-z").stdout == (
        b" M family.yaml\0"), "premise: the hand edit is the only change"
    before = state(holder, env)
    args = verb_args(verb, holder, family)
    args[args.index(MEMBER)] = project

    result = run_script(FAMILY, *args, env=env)

    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == "", "refused before anything was reported"
    said, remedy = refusal(result.stderr)
    assert said == (
        f"REFUSED member-path: {project!r} is not a project name: its path "
        f"would be 'members/{project}', which is {names}, not a member. "
        "Acting on it would unmount more than one member or remove the "
        "holder's own files, so no git command was run and nothing was "
        "written.")
    assert remedy == (
        "Remediation: this tool never writes such a row, so it is a hand "
        "edit. Restore family.yaml from git (`git checkout -- family.yaml` "
        "if the edit is not committed), or put the row's `project:` and "
        "`path:` back as the tool wrote them (`project: <Project>`, `path: "
        "members/<Project>`), then run the command again naming that "
        "member.")
    assert state(holder, env) == before
    for mounted in MEMBERS:
        entry = raw(holder, env, "ls-tree", "HEAD", "--", f"members/{mounted}"
                    ).stdout
        assert entry.startswith(b"160000 commit "), entry
        assert (holder / "members" / mounted / "project.yaml").is_file()
    assert [r["project"] for r in manifest(holder)["members"]] == [project,
                                                                   OTHER]
    assert not offline.gh_log.exists(), offline.gh_log.read_text()


# --- `add`: a `.` or `..` segment is not a name -----------------------------

#: `--member` spellings with a segment that is a directory reference, and the
#: sentence the refusal ends on: the one thing wrong with each.
DIRECTORY_REFERENCES = {
    "project-dotdot": (f"{ORG}/..", "..", "project",
                       "it would mount at members/.., the holder's root"),
    "project-dot": (f"{ORG}/.", ".", "project",
                    "it would mount at members/., the members directory "
                    "itself"),
    "owner-dotdot": (f"../{SPARE}", "..", "owner",
                     "no organisation or account is called that"),
    "owner-dot": (f"./{SPARE}", ".", "owner",
                  "no organisation or account is called that"),
}


@pytest.mark.parametrize("spelling, segment, which, why",
                         DIRECTORY_REFERENCES.values(),
                         ids=DIRECTORY_REFERENCES)
@pytest.mark.parametrize("kind", ["fresh-holder", "holder-with-members"])
def test_add_refuses_a_dot_segment_as_malformed_before_anything_is_read(
        family, offline, tmp_path, request, kind, spelling, segment, which,
        why):
    """`add --member <org>/..` matched `MEMBER_RE` (its class admits the dot,
    for `.github`) and its mount path `members/..` is the holder's root. On a
    FRESH holder `member-path-taken` then found the root's own files in the
    index under it and told the human to run `git rm -r --cached --
    members/..`, which stages the deletion of EVERY file the holder has. A
    segment of `.` or `..` is a directory reference, not a name, so it is the
    argument refusal `member-malformed`, before the member is read: not one
    line on stdout (`checking ... before mounting it` comes first otherwise),
    no clone, no `gh` call, and the holder byte for byte as it was."""
    env = isolated(offline, tmp_path)
    if kind == "fresh-holder":
        root = request.getfixturevalue("empty_holder")
        assert not (root / "members").exists(), "premise: a fresh holder"
        remotes = tmp_path / "remotes"
    else:
        root = request.getfixturevalue("holder")
        assert (root / "members").is_dir()
        remotes = family["remotes"]
    before = state(root, env)

    result = run_script(FAMILY, "add", "--family-root", str(root),
                        "--member", spelling, "--local-remote-dir",
                        str(remotes), env=env)

    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == "", "refused before the member was even read"
    said, remedy = refusal(result.stderr)
    assert said == (
        f"REFUSED member-malformed: --member {spelling!r} has `{segment}` as "
        f"its {which}, which is a directory reference and not a name: {why}")
    assert remedy == (
        "Remediation: name the repository as `<org>/<Project>`, each a real "
        "name beginning with a letter or a digit; `.` and `..` are neither, "
        "though a name may contain a dot after that (`Ze.d`).")
    assert state(root, env) == before
    offline.assert_left_nothing()


def test_add_still_takes_a_name_that_contains_a_dot():
    """A dot AFTER a name's first character is still a name. `.github` is not
    one any more: `MEMBER_RE` takes `validate-family.py`'s shape, in which a
    name begins with a letter or a digit (#366), and the holder's own gate
    refused a row naming it, so `add` can no longer write one.
    `tests/test_family_member_name.py` holds that rule."""
    module = family_module()
    assert module._checked_member(f"{ORG}/a.b")[1] == "a.b"
    assert module._checked_member(f"a.b/{SPARE}")[1] == SPARE


# --- the controls -----------------------------------------------------------

@pytest.mark.parametrize("edit", ["as-written", "no-path-line"])
@pytest.mark.parametrize("verb", ["remove", "bump"])
def test_a_row_with_the_members_own_path_or_none_still_exits_zero_in_one_commit(
        family, holder, offline, tmp_path, verb, edit):
    """THE CONTROLS: the row the tool writes, and a row with no `path:` at
    all, which keeps defaulting to `members/<project>`. Each is still ONE
    commit of exactly the paths the verb is for, and the holder still
    validates."""
    env = isolated(offline, tmp_path)
    if edit == "no-path-line":
        hand_edit(holder, MEMBER, None)
    was = commits(holder, env)

    result = run_script(FAMILY, *verb_args(verb, holder, family), env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert commits(holder, env) == was + 1
    if verb == "remove":
        assert committed(holder, env) == {".gitmodules", "family.yaml",
                                          f"members/{MEMBER}"}
        assert [r["project"] for r in manifest(holder)["members"]] == [OTHER]
    else:
        assert committed(holder, env) == {"family.yaml", f"members/{MEMBER}"}
        row = {r["project"]: r for r in manifest(holder)["members"]}[MEMBER]
        assert row["path"] == f"members/{MEMBER}"
        assert row["pin"]["commit"] == older(family)
    assert validate(holder).returncode == 0
    assert not offline.gh_log.exists()


def test_the_one_definition_is_the_path_add_writes_and_the_check_of_a_row():
    """`_member_path` is what `_member_row` (the row `add` writes) calls, and
    what `bump` and `remove` ask of a row: the same string, and a refusal for
    any other, with no disk and no git."""
    module = family_module()
    row = module._member_row(MEMBER, "irrs", f"{ORG}/{MEMBER}", "a" * 40,
                             "b" * 64)
    assert row["path"] == module._member_path(MEMBER) == f"members/{MEMBER}"
    for kept in ({}, {"path": None}, {"path": ""}, {"path": row["path"]}):
        assert module._member_path(MEMBER, kept) == row["path"], kept
    for spelling in (*SPELLINGS.values(), f"members\\{MEMBER}",
                     f"./members/{MEMBER}", " members/" + MEMBER):
        with pytest.raises(module.Refusal) as caught:
            module._member_path(MEMBER, {"path": spelling})
        assert caught.value.code == "member-path", spelling
    # A project that is not one directory name has no path to compare: the row
    # is refused under the same code, whatever its `path:` says (or does not).
    for project in ("", ".", "..", "a/b"):
        for named in ({}, {"path": f"members/{project}"}):
            with pytest.raises(module.Refusal) as caught:
                module._member_path(project, named)
            assert caught.value.code == "member-path", (project, named)
    # What `add` writes, with no row, is as it was.
    assert module._member_path("..") == "members/.."
    assert module._member_row("..", "x", f"{ORG}/..", "a" * 40, "b" * 64
                              )["path"] == "members/.."


# --- literal pathspecs ------------------------------------------------------

def reached_the_neighbour(call: str, root: Path, env: dict,
                          proc: subprocess.CompletedProcess) -> bool:
    """Did `call`, given the glob `members/*`, act on `OTHER`, a member it was
    never named for? Each answer is read from git, never from an exit code
    alone."""
    if call == "deinit":
        return not (root / "members" / OTHER / "project.yaml").exists()
    if call == "rm":
        return raw(root, env, "ls-files", "-s", "--", f"members/{OTHER}"
                   ).stdout == b""
    if call == "diff":
        return proc.returncode == 1
    return proc.returncode == 0 and f"members/{OTHER}" in committed(root, env)


GIT_CALLS = {
    "deinit": ("submodule", "deinit", "-f", "-q", "--", GLOB),
    "rm": ("rm", "-r", "-q", "-f", "--", GLOB),
    "diff": ("diff", "--quiet", "--ignore-submodules=dirty", "HEAD", "--",
             GLOB),
    "commit": ("commit", "-q", "-m", "a wrong commit", "--", GLOB),
}


def literal_form(call: str) -> list[str]:
    """`call` as the tool spells it: the global option in front, except on the
    commit, whose path is `:(literal)`-prefixed instead (see `_commit_one`)."""
    if call == "commit":
        return [word if word != GLOB else f":(literal){GLOB}"
                for word in GIT_CALLS[call]]
    return ["--literal-pathspecs", *GIT_CALLS[call]]


@pytest.mark.parametrize("call", GIT_CALLS)
def test_a_literal_spelling_keeps_a_glob_off_the_neighbour_in_each_call(
        holder, offline, tmp_path, call):
    """EACH GIT CALL `bump` AND `remove` MAKE WITH THE MEMBER'S PATH, run with
    the path `members/*`, on THIS git and on every runner's: the plain call
    reaches the neighbour (the premise: a test whose glob matched nothing
    would pass on any code), and the same call in the tool's literal spelling
    does not: the GLOBAL `--literal-pathspecs` for `deinit`, `rm` and `diff`,
    `:(literal)` on the path for the commit. `git submodule` is its own
    command, which is why `deinit` is here; it honours the global option,
    which reaches it as `GIT_LITERAL_PATHSPECS` in the environment."""
    env = isolated(offline, tmp_path)
    literal_holder = tmp_path / "literal"
    shutil.copytree(holder, literal_holder, symlinks=True)
    if call in ("diff", "commit"):
        # A neighbour with something to find: its gitlink moved and staged.
        for root in (holder, literal_holder):
            commit_in_member(root / "members" / OTHER)
            raw(root, env, "add", "--", f"members/{OTHER}")

    plain = raw(holder, env, *GIT_CALLS[call], check=False)
    assert reached_the_neighbour(call, holder, env, plain), (
        "premise: without the flag, the glob reaches the neighbour; "
        + plain.stderr.decode("utf-8", "replace"))

    literal = raw(literal_holder, env, *literal_form(call), check=False)
    assert not reached_the_neighbour(call, literal_holder, env, literal), (
        literal.stderr.decode("utf-8", "replace"))
    assert (literal_holder / "members" / OTHER / "project.yaml").is_file()
    assert raw(literal_holder, env, "ls-tree", "HEAD", "--",
               f"members/{OTHER}").stdout.startswith(b"160000 commit ")


def recorded(monkeypatch) -> list[list[str]]:
    """Every program this process runs from now on, argv by argv, still run
    for real."""
    calls: list[list[str]] = []
    real = subprocess.run

    def record(argv, *rest, **named):
        calls.append(list(argv))
        return real(argv, *rest, **named)

    monkeypatch.setattr(subprocess, "run", record)
    return calls


def subcommand(argv: list[str], subcommands: set[str]) -> str:
    return next(word for i, word in enumerate(argv)
                if i and word in subcommands)


@pytest.mark.parametrize("verb, flagged, commit_paths", [
    ("remove", {"submodule", "rm"},
     [".gitmodules", f"members/{OTHER}", "family.yaml"]),
    ("bump", {"add", "diff"}, [f"members/{MEMBER}", "family.yaml"])])
def test_every_git_call_that_takes_the_members_path_is_literal(
        family, holder, offline, tmp_path, monkeypatch, verb, flagged,
        commit_paths):
    """THE LITERAL SPELLING IS THERE on every call a real run of the verb makes
    with the member's path. `remove`'s `deinit` and `rm`, and `bump`'s two
    stages and its `diff`, carry `--literal-pathspecs` in the place git takes
    global options. The COMMIT of both carries `:(literal)` on each of its
    paths and NOT the global option: that option is `GIT_LITERAL_PATHSPECS` in
    the environment of every hook the commit runs. The set of calls is exact,
    so a new call that names the path is a test to extend rather than a call
    that goes unchecked."""
    module = family_module()
    for key, value in isolated(offline, tmp_path).items():
        monkeypatch.setenv(key, value)
    calls = recorded(monkeypatch)
    path = f"members/{OTHER if verb == 'remove' else MEMBER}"
    args = verb_args(verb, holder, family)
    if verb == "remove":
        args[args.index(MEMBER)] = OTHER
    subcommands = {*flagged, "commit"}

    assert module.main(args) == 0

    named = [argv for argv in calls if argv[0] == "git"
             and (path in argv or f":(literal){path}" in argv)]
    assert {subcommand(argv, subcommands) for argv in named} == subcommands
    for argv in named:
        options = argv[1:argv.index(subcommand(argv, subcommands))]
        if subcommand(argv, subcommands) == "commit":
            assert "--literal-pathspecs" not in options, argv
            assert argv[argv.index("--") + 1:] == [
                f":(literal){each}" for each in commit_paths], argv
        else:
            assert "--literal-pathspecs" in options, argv


def with_a_glob_hook(root: Path, tmp_path: Path) -> Path:
    """A `pre-commit` hook in `root` that writes what a glob-picking hook sees:
    the variable git's own `--literal-pathspecs` would put in its environment,
    and the staged files `git diff --cached --name-only -- '*.yaml'` finds, one
    per line. Returns the log. `sh`, which git runs hooks with on every OS
    (git for Windows ships its own); LOCAL `core.hooksPath`, so a global one
    cannot point git somewhere this hook is not."""
    log = tmp_path / "hook.log"
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "pre-commit").write_bytes((
        "#!/bin/sh\n"
        f"{{ echo \"literal=${{GIT_LITERAL_PATHSPECS-unset}}\"\n"
        "  git diff --cached --name-only -- '*.yaml'; } >> "
        f"'{log.as_posix()}'\n"
        "exit 0\n").encode("utf-8"))
    (hooks / "pre-commit").chmod(0o755)
    git("config", "--local", "core.hooksPath", hooks.as_posix(), cwd=root)
    return log


@pytest.mark.parametrize("verb", ["add", "bump", "remove"])
def test_the_commit_hooks_see_no_literal_pathspecs_and_find_the_manifest(
        family, holder, offline, tmp_path, verb):
    """THE GLOBAL `--literal-pathspecs` ON THE COMMIT LEAKED INTO THE HOLDER'S
    HOOKS. It is `GIT_LITERAL_PATHSPECS=1` in git's environment, which every
    child of `git commit` inherits, so a `pre-commit` hook that picked the
    staged files with a glob matched nothing on every `add`, `bump` and
    `remove` commit: a linter behind it checked nothing and said nothing. The
    commit takes `:(literal)` on its paths now. Through a real `add`, `bump`
    and `remove`, the hook sees no such variable, and its glob finds the
    manifest the commit is of."""
    env = isolated(offline, tmp_path)
    log = with_a_glob_hook(holder, tmp_path)
    if verb == "add":
        args = ["add", "--family-root", str(holder), "--member",
                f"{ORG}/{SPARE}", "--local-remote-dir",
                str(family["remotes"])]
    else:
        args = verb_args(verb, holder, family)

    result = run_script(FAMILY, *args, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert log.is_file(), "premise: the hook ran"
    assert log.read_bytes().decode("utf-8").split() == ["literal=unset",
                                                         "family.yaml"]


#: What each verb's ONE commit is of, as git reports it.
COMMITTED = {
    "add": {".gitmodules", f"members/{SPARE}", "family.yaml"},
    "bump": {f"members/{MEMBER}", "family.yaml"},
    "remove": {".gitmodules", f"members/{MEMBER}", "family.yaml"},
}


@pytest.mark.parametrize("verb", ["add", "bump", "remove"])
def test_a_caller_who_exports_literal_pathspecs_still_gets_one_commit(
        family, holder, offline, tmp_path, verb):
    """`:(literal)` is pathspec MAGIC, and `GIT_LITERAL_PATHSPECS=1` turns
    magic off: with it in the caller's environment git read `:(literal)
    family.yaml` as a file of that name and found none, so every commit of
    `add`, `bump` and `remove` failed (`bump` and `remove` with the pin or the
    unmount left staged and no rollback), where main and the first form of
    this fix exited 0. A safety default, or a `family.py` run from a hook or an
    alias of `git --literal-pathspecs`, puts it there. The commit drops that
    one variable from its own environment: with it exported, each verb exits
    0 in ONE commit of exactly the paths it is for, and leaves nothing staged
    behind."""
    env = {**isolated(offline, tmp_path), "GIT_LITERAL_PATHSPECS": "1"}
    was = commits(holder, env)
    if verb == "add":
        args = ["add", "--family-root", str(holder), "--member",
                f"{ORG}/{SPARE}", "--local-remote-dir",
                str(family["remotes"])]
    else:
        args = verb_args(verb, holder, family)

    result = run_script(FAMILY, *args, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert commits(holder, env) == was + 1
    assert committed(holder, env) == COMMITTED[verb]
    assert raw(holder, env, "status", "--porcelain=v1", "-z").stdout == b""
    assert validate(holder).returncode == 0
