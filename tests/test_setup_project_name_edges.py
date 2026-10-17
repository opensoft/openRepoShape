# SPDX-License-Identifier: Apache-2.0
"""The edges of a project name typed at `setup-project.py` (#777).

#729 made the name typed at the prompt answer to the check `--project` gets.
Three things were left, each measured on #729's head:

* `refuse_value` gave every refusal one closing sentence, and the sentence
  explained only a leading `-`, so `../x`, `a/b`, ` Atlas` and a name with an
  accented letter were told about a `-` none of them has. Each refusal now
  names the check the value failed: empty, a leading `-`, a control character,
  or the pattern for a name or a ref, in words and as the pattern.
* A name of 96 to 255 characters passed the prompt and `--project` and ended at
  step (5) or at GitHub, after step (4) printed its wall for three names that
  could never be repositories. GitHub keeps a repository name to at most 100
  characters (its documentation: nothing here creates a real repository, so the
  number is not measured), and `-spec` and `-code` add five, so a project name
  is at most 95, asked before step (4) and only where a GitHub repository will
  be made. Under `--local-remote-dir` the limit is the disk's, and step (5)
  still asks it as `scaffold-name-too-long`.
* `Atlas ` passed `NAME_RE` where ` Atlas` was refused, and step (4) judged
  `Atlas -spec` with no space shown anywhere. The prompt now takes the spaces
  off the ends of what was typed; an argv value is deliberate and is held as
  typed.

POSIX only where a run needs a terminal or a `gh` stub (`PTY_SKIP`).
"""

from __future__ import annotations

import os
import re
import shlex
import string
import sys

import pytest

from conftest import PTY_SKIP, REPO, run_in_a_terminal
from test_setup_project_py import (SETUP_PROJECT, entry_point_module,
                                   run_entry, terminal_env)
from test_setup_project_typed_name import (BELL, LNEXT, NAMING_POLICY, PROMPT,
                                           the_refusal)

#: The first sentence every refusal says, then its reason.
FIRST = ("{what} is {shown}, which is not a value this tool will put on a "
         "`git` or `gh` command line. ")

EMPTY = "It is empty, and a value here needs at least one character."
DASH = ("It starts with `-`, and git reads its own arguments: a value that "
        "starts with `-` is an option to git, not a name to us.")
CONTROL = ("It holds a control character, which the quotation shows as an "
           "escape: a newline ends a line in every terminal and log this "
           "output reaches, so a value carrying one could print a line that "
           "reads as this tool's own.")
NAME = ("It is not spellable as a name: a letter or a digit first, then "
        "letters, digits, spaces and `._'()&,+@-`, at most 255 characters in "
        "all (`^[A-Za-z0-9][A-Za-z0-9 ._'()&,+@-]{0,254}$`).")
REF = ("It is not spellable as a ref: a letter or a digit first, then "
       "letters, digits and `._/-`, at most 255 characters in all "
       "(`^[A-Za-z0-9][A-Za-z0-9._/-]{0,254}$`).")
RANGE = ("It holds `..`, which git reads as a revision range and not as a "
         "ref.")
LOCK = ("It ends in `.lock`, the name git gives the lock file it writes "
        "beside a ref.")

#: What a sentence for one check must never say about another.
NOT_THE_DASH = ("starts with", "option to git", "reads its own arguments")

ACCENTED = "Caf\u00e9"

#: Each refusal: the argv that carries the value (`{}` is the value), the
#: value, how the refusal names it, and the reason it gives. A value that
#: fails two checks is told the first, in the order empty, `-`, control
#: character, pattern.
REFUSALS = {
    "org-empty": (("--org", "{}"), "", "--org", EMPTY),
    "into-empty": (("--into", "{}"), "", "--into", EMPTY),
    "org-dash": (("--org", "{}"), "-evil", "--org", DASH),
    "into-dash": (("--into", "{}"), "-x", "--into", DASH),
    "org-control": (("--org", "{}"), "a" + BELL + "b", "--org", CONTROL),
    "into-control": (("--into", "{}"), "a" + BELL + "b", "--into", CONTROL),
    "passthrough-control": (("--", "{}"), "a" + BELL + "b",
                            "a passthrough argument after `--`", CONTROL),
    "project-up-and-out": (("--project", "{}"), "../x", "--project", NAME),
    "project-slash": (("--project", "{}"), "a/b", "--project", NAME),
    "project-dot-dot": (("--project", "{}"), "..", "--project", NAME),
    "project-leading-space": (("--project", "{}"), " Atlas", "--project",
                              NAME),
    "project-trailing-slash": (("--project", "{}"), "Atlas/", "--project",
                               NAME),
    "project-accented": (("--project", "{}"), ACCENTED, "--project", NAME),
    "project-blank": (("--project", "{}"), "   ", "--project", NAME),
    "org-dash-and-control": (("--org", "{}"), "-" + BELL, "--org", DASH),
    "org-control-and-slash": (("--org", "{}"), "a" + BELL + "/b", "--org",
                              CONTROL),
    "org-long": (("--org", "{}"), "x" * 256, "--org", NAME),
    "positional": (("{}",), "../x", "<Project>", NAME),
    "ref-space": (("--shape-ref", "{}"), "a b", "--shape-ref", REF),
    "ref-long": (("--shape-ref", "{}"), "a" * 256, "--shape-ref", REF),
    "ref-dash": (("--shape-ref", "{}"), "-x", "--shape-ref", DASH),
    "ref-range": (("--shape-ref", "{}"), "a..b", "--shape-ref", RANGE),
    "ref-lock": (("--shape-ref", "{}"), "topic.lock", "--shape-ref", LOCK),
}


def a_run_carrying(tmp_path, template, value):
    """A run that would otherwise be valid, with `value` where `template`
    puts it. A bare `<Project>` is the one carrier that cannot also be
    given `--project`: two names are refused before either is checked."""
    carried = [part.replace("{}", value) for part in template]
    context = ["--org", "demoorg", "--into", str(tmp_path / "work"),
               "--local-remote-dir", str(tmp_path / "remotes")]
    if template[0] != "{}":
        context = ["--project", "Sample", *context]
    return run_entry(*context, *carried)


@pytest.mark.parametrize("case", REFUSALS)
def test_a_refusal_names_the_check_the_value_failed(tmp_path, case):
    template, value, what, why = REFUSALS[case]
    result = a_run_carrying(tmp_path, template, value)
    assert result.returncode == 2, result.stderr
    expected = "REFUSED: " + FIRST.format(what=what, shown=ascii(value)) + why
    assert the_refusal(result.stderr) == expected
    if why != DASH:
        for words in NOT_THE_DASH:
            assert words not in result.stderr, result.stderr
    assert not (tmp_path / "remotes").exists()


#: What typed at the prompt is refused, and why. An empty line is not here:
#: it is "no project name was typed", which #729's file pins.
TYPED = {
    "dash": ("-x", DASH),
    "control": ("a" + BELL + "b", CONTROL),
    "up-and-out": ("../x", NAME),
    "slash": ("a/b", NAME),
    "trailing-slash": ("Atlas/", NAME),
    "accented": (ACCENTED, NAME),
    "long": ("x" * 256, NAME),
}


def gh_that_is_signed_in(tmp_path):
    """The environment of a run that is allowed to call `gh` and gets the
    three answers a preflight and step (3) read, and refuses the rest, so no
    run here reaches a real GitHub (the real `gh` stays unreachable).

    Its git has a credential helper for github.com: the line `gh auth
    setup-git` writes, pointed at this stub, in git's command scope
    (`GIT_CONFIG_COUNT`, appended to what the environment holds). Without
    it, the machine's own git config decided whether a GitHub run's
    preflight offered `gh auth setup-git`. A machine with a helper anywhere
    was never offered it; CI's runner has none, and its runs waited at that
    offer's `Type yes to continue:`, which nothing here answers, until they
    were killed (#777's first CI run)."""
    stub = tmp_path / "ghbin"
    stub.mkdir(exist_ok=True)
    gh = stub / "gh"
    gh.write_bytes(b"#!/bin/sh\n"
                   b'case "$1" in\n'
                   b'  --version) echo "gh version 2.50.0 (stub)" ;;\n'
                   b"  auth) exit 0 ;;\n"
                   b"  api) echo tester ;;\n"
                   b'  *) echo "stub gh: refused $*" >&2; exit 97 ;;\n'
                   b"esac\n")
    gh.chmod(0o755)
    held = int(os.environ.get("GIT_CONFIG_COUNT") or 0)
    return {"PATH": str(stub) + os.pathsep + os.environ["PATH"],
            "GIT_CONFIG_COUNT": str(held + 1),
            f"GIT_CONFIG_KEY_{held}": "credential.https://github.com.helper",
            f"GIT_CONFIG_VALUE_{held}":
                "!%s auth git-credential" % shlex.quote(str(gh))}


def flags_for(tmp_path, local):
    """The flags of a run asked for its project: `--` and `--dry-run` last,
    so a name that goes on ends at the plan and creates nothing."""
    return ["--org", "demoorg", "--elected-by", "Tester", "--into",
            str(tmp_path / "parent" / "into"),
            *(["--local-remote-dir", str(tmp_path / "remotes")]
              if local else []), "--", "--dry-run"]


def at_the_prompt(tmp_path, typed, local=True):
    """Setup asked for its project at a terminal and answered `typed`."""
    env = terminal_env()
    env.update(gh_that_is_signed_in(tmp_path))
    status, screen, answered = run_in_a_terminal(
        [sys.executable, str(SETUP_PROJECT), *flags_for(tmp_path, local)],
        cwd=REPO, env=env,
        answers=[typed.replace(BELL, LNEXT + BELL) + "\n"], prompt=PROMPT,
        timeout=60)
    assert answered == 1, f"it never asked for a project name:\n{screen}"
    return status, screen


def assert_nothing_was_made(tmp_path):
    for name in ("remotes", "parent"):
        assert not (tmp_path / name).exists(), name


@PTY_SKIP
@pytest.mark.parametrize("case", TYPED)
def test_a_typed_name_is_refused_with_the_check_it_failed(tmp_path, case):
    value, why = TYPED[case]
    status, screen = at_the_prompt(tmp_path, value)
    assert status == 2, f"status {status}:\n{screen}"
    assert the_refusal(screen) == (
        "REFUSED: " + FIRST.format(what="project name", shown=ascii(value))
        + why)
    if why != DASH:
        for words in NOT_THE_DASH:
            assert words not in screen, screen
    assert "[ok] project" not in screen, screen
    assert NAMING_POLICY not in screen, screen
    assert_nothing_was_made(tmp_path)


# --- the bound ---------------------------------------------------------------

#: GitHub's documented limit on a repository name, less `-spec` and `-code`.
BOUND = 95


def a_name(length):
    return "A" + "b" * (length - 1)


def too_long(what, name):
    return ("REFUSED: %s is %d characters long (%s...%s), and a project is "
            "three repositories, `<Project>`, `<Project>-spec` and "
            "`<Project>-code`: GitHub keeps a repository name to at most "
            "100 characters, so a project name is at most 95. Nothing was "
            "created. Use a shorter name."
            % (what, len(name), name[:12], name[-12:]))


def a_run_for(tmp_path, project, local, positional=False, late_local=False):
    """The project given on the command line, and `-- --dry-run`."""
    flags = flags_for(tmp_path, local)
    if late_local:
        flags = [f for f in flags_for(tmp_path, False)]
        flags[flags.index("--"):flags.index("--")] = [
            "--local-remote-dir", str(tmp_path / "remotes")]
    given = [project] if positional else ["--project", project]
    return run_entry(*given, *flags, extra_env=gh_that_is_signed_in(tmp_path))


@PTY_SKIP
@pytest.mark.parametrize("how", ["flag", "positional"])
@pytest.mark.parametrize("length", [BOUND + 1, 100, 101, 255])
def test_a_name_over_the_bound_is_refused_before_anything_prints(
        tmp_path, length, how):
    name = a_name(length)
    result = a_run_for(tmp_path, name, local=False,
                       positional=how == "positional")
    assert result.returncode == 2, result.stderr
    assert the_refusal(result.stderr) == too_long(
        "<Project>" if how == "positional" else "--project", name)
    assert result.stdout == "", result.stdout
    assert_nothing_was_made(tmp_path)


@PTY_SKIP
def test_a_name_at_the_bound_goes_on_to_step_four(tmp_path):
    result = a_run_for(tmp_path, a_name(BOUND), local=False)
    assert NAMING_POLICY in result.stdout, result.stdout + result.stderr
    assert "characters long" not in result.stderr, result.stderr


@PTY_SKIP
@pytest.mark.parametrize("length", [BOUND + 1, 100, 101, 246])
def test_a_name_over_the_bound_is_not_asked_of_a_local_run(tmp_path, length):
    """No GitHub repository is made under `--local-remote-dir`, so the limit
    is the disk's, and step (5) still asks it: 247 characters and more end
    there as `scaffold-name-too-long`."""
    result = a_run_for(tmp_path, a_name(length), local=True)
    assert NAMING_POLICY in result.stdout, result.stdout + result.stderr
    assert "characters long" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr


@PTY_SKIP
def test_the_disk_limit_is_still_step_fives_under_a_local_run(tmp_path):
    result = a_run_for(tmp_path, a_name(247), local=True)
    assert result.returncode == 2, result.stderr
    assert "scaffold-name-too-long" in result.stderr, result.stderr
    assert "characters long" not in result.stderr, result.stderr


@PTY_SKIP
def test_the_bound_waits_for_a_local_remote_dir_that_comes_later(tmp_path):
    """`--local-remote-dir` decides whether a GitHub repository will be made,
    and it can come after `--project` on the line."""
    result = a_run_for(tmp_path, a_name(BOUND + 1), local=False,
                       late_local=True)
    assert NAMING_POLICY in result.stdout, result.stdout + result.stderr
    assert "characters long" not in result.stderr, result.stderr


@PTY_SKIP
@pytest.mark.parametrize("length", [BOUND + 1, 100, 101, 255])
def test_a_typed_name_over_the_bound_is_refused_at_the_prompt(tmp_path,
                                                              length):
    name = a_name(length)
    status, screen = at_the_prompt(tmp_path, name, local=False)
    assert status == 2, f"status {status}:\n{screen}"
    assert the_refusal(screen) == too_long("project name", name)
    assert "[ok] project" not in screen, screen
    assert NAMING_POLICY not in screen, screen
    assert_nothing_was_made(tmp_path)


@PTY_SKIP
@pytest.mark.parametrize("local", [False, True], ids=["github", "local"])
def test_a_typed_name_at_the_bound_goes_on_to_step_four(tmp_path, local):
    status, screen = at_the_prompt(tmp_path, a_name(BOUND), local=local)
    assert "[ok] project" in screen, screen
    assert NAMING_POLICY in screen, screen
    assert "characters long" not in screen, screen


@PTY_SKIP
@pytest.mark.parametrize("length", [BOUND, BOUND + 1])
def test_a_github_run_here_is_not_held_by_a_git_with_no_helper(
        tmp_path, monkeypatch, length):
    """A GitHub run's preflight offers `gh auth setup-git` to a machine whose
    git has no credential helper for github.com, before step (3) asks for the
    project. CI's runner is such a machine, and the typed runs above waited
    there on it. Here git's system and global files are empty, as the
    runner's are, so a run that would wait at that offer fails on every
    machine, not on CI alone."""
    blank = tmp_path / "blank.gitconfig"
    blank.write_bytes(b"")
    for scope in ("GIT_CONFIG_SYSTEM", "GIT_CONFIG_GLOBAL"):
        monkeypatch.setenv(scope, str(blank))
    _, screen = at_the_prompt(tmp_path, a_name(length), local=False)
    assert "gh auth setup-git" not in screen, screen
    assert ("characters long" in screen) == (length > BOUND), screen


@PTY_SKIP
def test_a_typed_name_over_the_bound_goes_on_in_a_local_run(tmp_path):
    status, screen = at_the_prompt(tmp_path, a_name(BOUND + 1), local=True)
    assert status == 0, f"status {status}:\n{screen}"
    assert NAMING_POLICY in screen, screen
    assert "characters long" not in screen, screen


# --- the spaces at the ends --------------------------------------------------

@PTY_SKIP
@pytest.mark.parametrize("typed", ["Atlas ", " Atlas", "  Atlas  "])
def test_the_spaces_at_the_ends_of_a_typed_name_are_taken_off(tmp_path, typed):
    status, screen = at_the_prompt(tmp_path, typed)
    assert status == 0, f"status {status}:\n{screen}"
    assert "\n  [ok] project      Atlas\n" in screen, screen
    assert "\n  [ok] legs         Atlas-spec, Atlas-code\n" in screen, screen
    assert "NO FAMILY" not in screen, screen
    assert "naming-unclassified" not in screen, screen
    assert f"clone into   {tmp_path / 'parent' / 'into' / 'Atlas'}\n" in screen


@PTY_SKIP
def test_a_line_of_spaces_is_no_name_at_all(tmp_path):
    status, screen = at_the_prompt(tmp_path, "   ")
    assert status == 2, f"status {status}:\n{screen}"
    assert the_refusal(screen) == (
        "REFUSED: no project name was typed; nothing was created.")
    assert "[ok] project" not in screen, screen
    assert_nothing_was_made(tmp_path)


def test_an_argv_name_is_held_as_typed(tmp_path):
    """The other half of the choice: an argv value is deliberate, so a
    trailing space on `--project` reaches step (4) as it was given."""
    result = run_entry("--project", "Atlas ", "--org", "demoorg",
                       "--elected-by", "Tester", "--into",
                       str(tmp_path / "work"), "--local-remote-dir",
                       str(tmp_path / "remotes"))
    assert result.returncode == 1, result.stderr
    assert "FINDING naming-unclassified: Atlas , Atlas -spec, Atlas -code" \
        in result.stderr, result.stderr


# --- the sentences say what the checks are -------------------------------------

def test_the_name_sentence_says_what_the_pattern_holds():
    """The words and the pattern cannot drift: every printable character is
    in the sentence's list exactly when `NAME_RE` takes it after a letter."""
    module = entry_point_module()
    said = set(string.ascii_letters + string.digits + " ._'()&,+@-")
    for char in string.printable:
        if char in "\r\n\x0b\x0c":
            continue
        assert bool(module.NAME_RE.fullmatch("A" + char)) == (char in said), \
            repr(char)
    assert module.NAME_RE.fullmatch("A" * 255)
    assert not module.NAME_RE.fullmatch("A" * 256)
    for char in string.digits + string.ascii_letters:
        assert module.NAME_RE.fullmatch(char + "x")
    assert not module.NAME_RE.fullmatch(" x")


def test_the_ref_sentence_says_what_the_pattern_holds():
    module = entry_point_module()
    said = set(string.ascii_letters + string.digits + "._/-")
    for char in string.printable:
        if char in "\r\n\x0b\x0c":
            continue
        assert bool(module.REF_RE.fullmatch("a" + char)) == (char in said), \
            repr(char)
    assert module.REF_RE.fullmatch("a" * 255)
    assert not module.REF_RE.fullmatch("a" * 256)


def test_a_pattern_with_no_words_is_named_as_the_sibling_names_it():
    """`PATH_RE` has no row in `WHY_PATTERN`: its only failures are an empty
    value and a control character, named first. A pattern that did get here
    is still named, not a KeyError."""
    module = entry_point_module()
    for text in ("", "a" + BELL + "b", "\n"):
        assert not module.PATH_RE.fullmatch(text)
        assert module.why_refused(text, module.PATH_RE) in (
            EMPTY, CONTROL), repr(text)
    with pytest.raises(module.Refusal) as refused:
        module.checked_value("--x", "ab", re.compile("^z$"))
    assert str(refused.value).endswith(". It does not match `^z$`.")
