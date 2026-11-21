# SPDX-License-Identifier: Apache-2.0
"""Every helper that spells a name for a line or for the plan asks the
default-ignorable table (#1165).

#1128 (#1171) wrote Unicode's Default_Ignorable_Code_Point table into
`scripts/repo_shape.py` (`DEFAULT_IGNORABLE`) and taught `adopt-project.py`'s
`_shown`, `_spelled_character` and `checked_value`'s refusal to spell those
characters. `str.isprintable` passes 267 of them, which a terminal draws as
nothing, among them U+034F, the variation selectors and the Hangul fillers,
so `ma<U+034F>in` reads as `main`. Every other helper that asked
`str.isprintable` alone, or spelled with `repr`, printed or wrote them raw:

1. the `repr`-based `_shown` copies of the three validators, and
   `repo_shape.shown_path`, which `shape_materialize.shown_source` is;
2. `shape_materialize.readable_branch`, which took `ma<U+034F>in` for a
   branch and named a refused one raw, and the root's two that hold its
   rule, `validate-manifest.py`'s `_branch_finding` and `bootstrap.py`'s
   `_argument_fault`, which found nothing in it;
3. `repo_shape.double_quoted`, the plan's writer;
4. `adopt-project.py`'s `_worded`, `_line_shown` (and `shape_materialize`'s),
   `unwritable_values`, `_refuse_an_unwritable_clone_url`,
   `_from_the_remote`, `_first_words` and `_first_said`; with RV1171's N5,
   `_refetch`.

Each row hands one site a name holding one of four characters: U+034F, the
variation selectors U+FE0F and U+E0100, and the Hangul filler U+3164. It
asserts that the character is nowhere in what the site prints or writes,
and that the site names it by its own rule: `repr`'s code-point escape
(`'ma\\u034fin'`), the plan's (`"ma\\u034fin"`), `_spelled`'s
(`` `ma\\u034fin` ``), `_worded`'s words (`the character U+034F`), or the
code point a branch refusal names. Every row fails on #1171's head.

RV1171's N4 rows pin the two sentences it found no longer true: `_spelled`'s
"THE SPELLING IS THE PLAN'S OWN", and `unwritable_values`' value "spelled
... as `unsafe-value` spells one". The three validators and `bootstrap.py`
carry their own copy of the table, since a root's `repo_shape.py` may be
older than they are, so the table rows hold each copy to the library's.

This file is ASCII: every character outside it is written as an escape.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from conftest import (ADOPT, REPO, blank_unnamed_pin_sources, git,
                      load_without_bytecode, make_source_repo)

sys.path.insert(0, str(REPO / "scripts"))
import repo_shape  # noqa: E402
import shape_materialize  # noqa: E402

SCRIPTS = REPO / "templates" / "assembly-root" / "scripts"
PLAN_FILE = "adoption-plan.yaml"

#: The characters each row hands a site, by name: a combining mark, two
#: variation selectors (one past U+FFFF) and a Hangul filler. Each is
#: default-ignorable and `str.isprintable` passes each.
CHARACTERS = {
    "combining-grapheme-joiner": "\u034f",
    "variation-selector-16": "\ufe0f",
    "variation-selector-17": "\U000e0100",
    "hangul-filler": "\u3164",
}
EACH_CHARACTER = pytest.mark.parametrize(
    "char", list(CHARACTERS.values()), ids=list(CHARACTERS))
#: What stands beside the character in a name: nothing but letters, or an
#: ESC. The table is asked of each character, so the character is escaped
#: beside a control too, where `repr` has its own work to do (RV1165's S1).
BESIDE = pytest.mark.parametrize(
    "beside", ["", "\x1b"], ids=["letters", "escape"])


@pytest.fixture(scope="module")
def adopter():
    return load_without_bytecode(ADOPT, "default_ignorables_adopter")


@pytest.fixture(scope="module")
def naming():
    return load_without_bytecode(
        REPO / "scripts" / "validate-repository-naming.py",
        "default_ignorables_naming")


@pytest.fixture(scope="module")
def manifest():
    return load_without_bytecode(SCRIPTS / "validate-manifest.py",
                                 "default_ignorables_manifest")


@pytest.fixture(scope="module")
def pins():
    return load_without_bytecode(SCRIPTS / "validate-pins.py",
                                 "default_ignorables_pins")


@pytest.fixture(scope="module")
def bootstrap():
    return load_without_bytecode(SCRIPTS / "bootstrap.py",
                                 "default_ignorables_bootstrap")


def escaped(char: str) -> str:
    """The code-point escape of `char`: `\\u034f`, `\\U000e0100`."""
    return repo_shape.code_point_escaped(char)


def point(char: str) -> str:
    """`char`'s code point as a line names it: `U+034F`."""
    return f"U+{ord(char):04X}"


def refusal_of(call) -> repo_shape.Refusal:
    """The `Refusal` `call` raises."""
    with pytest.raises(repo_shape.Refusal) as raised:
        call()
    return raised.value


# --- 1. the `_shown` copies, and `shown_path` --------------------------------

@EACH_CHARACTER
@pytest.mark.parametrize("copy", ["naming", "manifest", "pins"])
def test_a_validators_shown_escapes_it_as_the_library_does(
        request, copy, char):
    """Each validator's `_shown` spells the name as `repr` spells it, with
    the character escaped, and so as `repo_shape.shown_path` does: the
    copies agree (`test_pinned_copy_text.py`'s rule)."""
    module = request.getfixturevalue(copy)
    name = f"ma{char}in"
    said = module._shown(name)
    assert char not in said, ascii(said)
    assert said == f"'ma{escaped(char)}in'" == repo_shape.shown_path(name)


@EACH_CHARACTER
@BESIDE
def test_shown_path_and_shown_source_escape_it(char, beside):
    name = f"ma{char}{beside}in"
    for said in (repo_shape.shown_path(name),
                 shape_materialize.shown_source(name)):
        assert char not in said, ascii(said)
        assert said == f"'ma{escaped(char)}{repr(beside)[1:-1]}in'"


# --- 2. a branch: `readable_branch`, `_branch_finding`, `_argument_fault` ----

@EACH_CHARACTER
def test_readable_branch_refuses_it_as_unseen_and_escapes_it(char):
    """`ma<U+034F>in` was returned as a branch, to be compared and handed to
    `gh pr create --base`; it is `unseen-branch` now, named escaped."""
    refused = refusal_of(lambda: shape_materialize.readable_branch(
        "tracking_branch", f"ma{char}in"))
    assert refused.code == "unseen-branch"
    assert char not in str(refused), ascii(str(refused))
    assert (f"tracking_branch is 'ma{escaped(char)}in', which holds "
            f"{point(char)}, a character that does not print or is white "
            "space") in str(refused), ascii(str(refused))


@EACH_CHARACTER
def test_readable_branch_escapes_it_in_a_leading_dash_refusal(char):
    refused = refusal_of(lambda: shape_materialize.readable_branch(
        "tracking_branch", f"-ma{char}in"))
    assert refused.code == "unsafe-value"
    assert char not in str(refused), ascii(str(refused))
    assert (f"tracking_branch is '-ma{escaped(char)}in', which begins with "
            "`-`") in str(refused), ascii(str(refused))


@EACH_CHARACTER
def test_the_manifest_validator_finds_it_in_a_branch(manifest, char):
    """The root's own rule, `_branch_finding`, is `readable_branch`'s: the
    name is a finding, and the finding names it escaped."""
    found = manifest._branch_finding("manifest-tracking-branch",
                                     "tracking_branch", f"ma{char}in")
    assert len(found) == 1, found
    assert char not in found[0], ascii(found)
    assert found[0].startswith(
        f"FINDING manifest-tracking-branch: tracking_branch is "
        f"'ma{escaped(char)}in', which holds {point(char)}, a character "
        "that does not print or is white space"), ascii(found)


@EACH_CHARACTER
def test_bootstrap_makes_no_branch_of_it(bootstrap, char):
    """`_argument_fault` found nothing in `ma<U+034F>in`, so step (a) made
    it beside `main` in every leg; it is `UNSEEN` now, by its code point."""
    assert bootstrap._argument_fault(f"ma{char}in") == (
        f"{point(char)}, {bootstrap.UNSEEN}")


# --- 3. the plan's writer ----------------------------------------------------

@EACH_CHARACTER
def test_double_quoted_escapes_it_and_reads_back(char):
    name = f"ma{char}in"
    quoted = repo_shape.double_quoted(name)
    assert char not in quoted, ascii(quoted)
    assert quoted == f'"ma{escaped(char)}in"'
    assert repo_shape.parse_yaml(f"k: {quoted}\n") == {"k": name}


@EACH_CHARACTER
def test_the_plan_file_holds_it_escaped(tmp_path, char):
    """End to end: a source whose root holds `ma<char>in.md`. The plan file
    holds the entry's path escaped, and reads back as the name; no byte of
    the character is in the file, on stdout or on stderr."""
    name = f"ma{char}in.md"
    source = make_source_repo(tmp_path / "Thing",
                              {"README.md": "# Thing\n", name: "notes\n"},
                              edits=())
    plan = tmp_path / PLAN_FILE
    done = subprocess.run(
        [sys.executable, str(ADOPT), "plan", "--source", str(source),
         "--project", "Northwind", "--org", "testorg",
         "--elected-by", "Test Human", "--elected-on", "2026-09-02",
         "--tracking-branch", "main", "--out", str(plan)],
        capture_output=True, stdin=subprocess.DEVNULL, check=False,
        env=blank_unnamed_pin_sources({**os.environ, "LANES_LANE": ""}, {}))
    assert done.returncode == 0, done.stderr + done.stdout
    body = plan.read_bytes()
    raw = char.encode("utf-8")
    for where in (body, done.stdout, done.stderr):
        assert raw not in where, where
    assert f'  - path: "ma{escaped(char)}in.md"'.encode("ascii") in body
    paths = [entry["path"]
             for entry in repo_shape.load_yaml(plan)["paths"]]
    assert name in paths, ascii(paths)


# --- 4. adopt-project.py, and `shape_materialize`'s `_line_shown` ------------

@EACH_CHARACTER
def test_worded_names_it_outside_the_backticks(adopter, char):
    said = adopter._worded(f"ma{char}in")
    assert said == f"`ma`, then the character {point(char)}, then `in`"


@EACH_CHARACTER
@BESIDE
@pytest.mark.parametrize("where", ["adopt-project", "shape_materialize"])
def test_line_shown_escapes_it(adopter, where, char, beside):
    line_shown = (adopter._line_shown if where == "adopt-project"
                  else shape_materialize._line_shown)
    said = line_shown(f"ma{char}{beside}in")
    assert char not in said, ascii(said)
    assert said == f"'ma{escaped(char)}{repr(beside)[1:-1]}in'"


@EACH_CHARACTER
def test_unwritable_values_escapes_it(adopter, char):
    [said] = adopter.unwritable_values(
        [("--elected-by", f"ma{char}in\n", "README.md")])
    assert char not in said, ascii(said)
    assert said.startswith(
        f"--elected-by is 'ma{escaped(char)}in\\n', which `execute` writes "
        "into README.md, and "), ascii(said)


@EACH_CHARACTER
def test_an_unwritable_clone_url_is_refused_with_it_escaped(adopter, char):
    refused = refusal_of(
        lambda: adopter._refuse_an_unwritable_clone_url(f"/srv/ma{char}in\n"))
    assert refused.code == "adopt-unwritable-value"
    assert char not in str(refused), ascii(str(refused))
    assert (f"the source's own path, '/srv/ma{escaped(char)}in\\n', which "
            "`execute` writes into its `README.md`") in str(refused), (
        ascii(str(refused)))


@EACH_CHARACTER
def test_from_the_remote_says_the_step_in_words(adopter, tmp_path, char):
    """`origin/HEAD`'s branch, which `origin` has: the command a person
    pastes held the character raw, and read `git branch 'main'
    'origin/main'`. The step is said in words now, the name spelled."""
    name = f"ma{char}in"
    git("init", "-q", "-b", "trunk", str(tmp_path / "src"), cwd=tmp_path)
    source = tmp_path / "src"
    git("commit", "-q", "--allow-empty", "-m", "x", cwd=source)
    git("update-ref", f"refs/remotes/origin/{name}", "HEAD", cwd=source)
    said = adopter._from_the_remote(source, name)
    assert char not in said, ascii(said)
    assert (f"a branch named `ma{escaped(char)}in` made from `origin`'s "
            "branch of that name") in said, ascii(said)


@EACH_CHARACTER
def test_first_words_escapes_it_in_what_git_said(adopter, char):
    failed = subprocess.CompletedProcess(
        [], 128, b"", f"fatal: 'ma{char}in' does not appear\n".encode())
    said = adopter._first_words(failed)
    assert said == f"fatal: 'ma{escaped(char)}in' does not appear"


@EACH_CHARACTER
def test_first_said_escapes_it_in_what_gh_said(adopter, char):
    said = adopter._first_said(f"HTTP 404: ma{char}in Not Found\n")
    assert said == f": HTTP 404: ma{escaped(char)}in Not Found"


@EACH_CHARACTER
def test_refetch_says_the_step_in_words(adopter, char):
    """RV1171's N5: `_refetch` quoted a remote named `ma<U+034F>in` raw in
    the command to paste, since `str.isprintable` passed it."""
    said = adopter._refetch(f"ma{char}in")
    assert said == ("a `git fetch --refetch --no-filter` from the remote "
                    f"named `ma{escaped(char)}in`")


# --- RV1225's site: `_unacted`, which a REFUSED block is spelled with --------

@EACH_CHARACTER
def test_unacted_escapes_it(adopter, char):
    """RV1225 (#1225's review, N4): `_unacted`, which #1233 gives
    `adopt-mount-unaddable` too, asked `str.isprintable` alone, so U+034F in
    git's words or in a path printed raw."""
    assert adopter._unacted(f"ma{char}in") == f"ma{escaped(char)}in"


@EACH_CHARACTER
def test_a_refused_commands_block_escapes_it(adopter, char):
    """`_loudly`'s REFUSED block names the command, the directory it ran in
    and what it printed, each `_unacted`: the character is in none of them
    raw, and each names it escaped."""
    failed = adopter.CommandFailed(
        ["git", "push", f"/srv/ma{char}in.git"], f"/work/ma{char}in", 1,
        f"error: failed to push some refs to '/srv/ma{char}in.git'\n")
    block = adopter._loudly(failed, "push the spec leg")
    assert char not in block, ascii(block)
    assert block.count(f"ma{escaped(char)}in") == 3, ascii(block)


# --- RV1171's N4: two sentences that hold again ------------------------------

@EACH_CHARACTER
def test_the_spelling_is_the_plans_own(adopter, char):
    """`_spelled`'s "THE SPELLING IS THE PLAN'S OWN": a spelled name, copied
    between the plan's double quotes, is the entry the plan writes. #1171
    escaped the character in `_spelled` while the plan held it raw."""
    name = f"ma{char}in"
    assert adopter._spelled(name)[1:-1] == (
        repo_shape.double_quoted(name)[1:-1])


@EACH_CHARACTER
def test_unwritable_values_spells_it_as_unsafe_value_does(adopter, char):
    """`unwritable_values`' value is "spelled ... as `unsafe-value` spells
    one": `checked_value`'s refusal, which #1171 gave `visible_repr`."""
    value = f"ma{char}in\n"
    [said] = adopter.unwritable_values([("--elected-by", value, "README.md")])
    refused = refusal_of(lambda: repo_shape.checked_value("--elected-by",
                                                          value))
    spelling = f"--elected-by is 'ma{escaped(char)}in\\n', which "
    assert spelling in str(refused), ascii(str(refused))
    assert said.startswith(spelling), ascii(said)


# --- the copies of the table -------------------------------------------------

@pytest.mark.parametrize("copy", ["naming", "manifest", "pins", "bootstrap"])
def test_each_copy_of_the_table_is_the_librarys(request, copy):
    """Each copy matches exactly the code points the library's does, over
    every code point: not one more, not one fewer."""
    table = request.getfixturevalue(copy).DEFAULT_IGNORABLE
    differ = [point(chr(code)) for code in range(0x110000)
              if bool(table.match(chr(code)))
              != bool(repo_shape.DEFAULT_IGNORABLE.match(chr(code)))]
    assert differ == []


@pytest.mark.parametrize("copy", ["naming", "manifest", "pins"])
def test_each_validators_visible_repr_is_the_librarys(request, copy):
    """Each validator's `_visible_repr` writes every default-ignorable
    character as `repo_shape.visible_repr` does."""
    module = request.getfixturevalue(copy)
    differ = [point(chr(code)) for code in range(0x110000)
              if repo_shape.DEFAULT_IGNORABLE.match(chr(code))
              and module._visible_repr(f"a{chr(code)}b")
              != repo_shape.visible_repr(f"a{chr(code)}b")]
    assert differ == []
