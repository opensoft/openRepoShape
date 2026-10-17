# SPDX-License-Identifier: Apache-2.0
"""`family.py init` asks every name it writes down or lays out, whichever
flag or variable supplied it, before anything exists and under `--dry-run`
alike (#688).

Three lines of #459, each measured on main before this change:

  * THE CREATOR, FROM EVERY SOURCE. #426 asked `unwritable_reason` of the
    creator only when `git config user.name` supplied it, so `--created-by
    $'Ada\\nLovelace' --dry-run` exited 0 with the plan's `created by` line
    broken in two, and a `--created-by` or a GIT_AUTHOR_NAME holding U+202E,
    an ESC or a byte that is not UTF-8 exited 0 too. Now each is
    `family-unwritable-value`, and the remediation names the flag, the
    variable or the setting that supplied the name;
  * THE COMMIT'S IDENTITY. `_creator_name` passes over a GIT_AUTHOR_NAME of
    whitespace alone and reads `git config user.name`, but `git commit` reads
    the variable: a real run exited 2 with `fatal: name consists only of
    disallowed characters` after `<remotes>/Contoso.git` and the work
    directory existed. Now git is asked first (`git var`), and the run is
    `family-bad-commit-identity`. A name of only `<>` and a date git cannot
    read failed at the same commit, and are asked the same way;
  * THE HOLDER'S NAME. `--family CON` (or `Nul`, `com1`, any Windows device
    name) is one CamelCase token, which is all the naming policy asks, and a
    Windows disk can make no folder of that name. Now it is
    `family-bad-holder-name`, in the words of the leg path rule
    (`_unmountable_reason`). The rule's other two Windows answers, a name
    ending in a dot or a space, were already refused before anything existed
    (`family-bad-id` or `naming-unclassified`, and `unsafe-value`); their
    rows pin that.

The harness is `tests/test_non_utf8_git_reads.py`'s (#426): `family.py init`
of this checkout into local bare remotes under `tmp_path`, which never calls
`gh`. NO NETWORK AND NO GITHUB.
"""

from __future__ import annotations

import os
import sys

import pytest

from conftest import REPO
from test_non_utf8_git_reads import (
    BIDI, CONTROL, CREATOR_NOT_GIVEN, HOLDER, LEGACY_NAME, LINE_BREAK,
    NOT_UTF8_REASON, POSIX_ENVIRONMENT_ONLY, REFUSED, REMEDIATION,
    WRITTEN_INTO, init, nothing_was_created, user_name,
)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml  # noqa: E402

#: A byte that is not UTF-8 in an ARGUMENT: POSIX passes the byte; Windows
#: passes UTF-16, where it cannot be one.
POSIX_ARGV_ONLY = pytest.mark.skipif(
    os.name == "nt",
    reason="a POSIX command line's bytes; Windows' is UTF-16")

DRY_RUN = pytest.mark.parametrize("dry_run", [True, False],
                                  ids=["dry-run", "real"])
LANDING = pytest.mark.parametrize("landing", ["--work-dir", "--into"])

#: How each remediation for an unwritable creator ends (#426).
WHY = ("which the manifest could keep only as a lone surrogate, and that is "
       "no character; a line break or a control character would break or "
       "garble the line the plan prints it on; and a bidirectional "
       "embedding, override or isolate control would show the rest of that "
       "line in another order than it is written.")
NOTHING = ("Remediation: nothing was created, and `--dry-run` refuses the "
           "same. ")
#: The creator came from `--created-by`.
FLAG_REMEDIATION = (
    NOTHING + "Pass --created-by again, retyped. A byte that is not UTF-8 "
    "reaches a command line from a terminal or a script whose encoding is "
    "not the locale's, " + WHY)
#: The creator came from GIT_AUTHOR_NAME.
ENV_REMEDIATION = (
    NOTHING + "`init` read the creator from GIT_AUTHOR_NAME, because no "
    "--created-by was given: pass --created-by 'Your Name', or correct that "
    "variable. The environment keeps it as the bytes it was given, so a name "
    "set in a legacy code page holds a byte that is not UTF-8, " + WHY)
#: The creator came from `git config user.name`: #426's words, whole.
CONFIG_REMEDIATION = (
    REMEDIATION + "git keeps it as the bytes it was given, so a name saved "
    "in a legacy code page holds a byte that is not UTF-8, " + WHY)


#: The one line `_shape_snapshot` prints first from a checkout with
#: uncommitted changes. The identity question comes after it.
DIRTY = "WARNING the openRepoShape checkout is DIRTY."


def refused(result, expected: str, tmp_path) -> None:
    """Exit 2, the plan never printed, stderr opening with `expected` (after
    the DIRTY warning, where there is one), and no remote, work directory or
    family folder made."""
    assert result.returncode == 2, result.stderr + result.stdout
    assert result.stdout == "", "the plan is never printed"
    err = result.stderr
    if err.startswith(DIRTY):
        err = err.split("\n", 1)[1]
    assert err.startswith(expected), result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    nothing_was_created(tmp_path)


def initialised(result, tmp_path, dry_run: bool) -> None:
    assert result.returncode == 0, result.stderr + result.stdout
    assert "REFUSED" not in result.stderr, result.stderr
    assert (tmp_path / "remotes").exists() is (not dry_run), (
        "a dry run creates no remote and a real run does")


# ---------------------------------------------------------------------------
# The creator, from every source
# ---------------------------------------------------------------------------

UNWRITABLE = [
    pytest.param("Ada\nLovelace", LINE_BREAK, id="lf"),
    pytest.param("Ada\u202eLovelace", BIDI, id="u202e"),
    pytest.param("Ada\x1bLovelace", CONTROL, id="esc"),
    pytest.param("Ada\tLovelace", CONTROL, id="tab"),
]


@DRY_RUN
@pytest.mark.parametrize("value, reason", UNWRITABLE)
def test_a_created_by_no_file_can_hold_is_refused_before_anything_exists(
        tmp_path, value, reason, dry_run):
    """THE ISSUE'S ROWS: `--created-by $'Ada\\nLovelace'` and one holding
    U+202E exited 0, the first with the plan's line broken after `created by
    Ada`. Now `family-unwritable-value`, naming the flag, whose remediation
    is to retype it."""
    result = init(tmp_path, {}, "--created-by", value, dry_run=dry_run)
    refused(result, f"{REFUSED}--created-by is {value!r}, {WRITTEN_INTO}"
                    f"{reason}.\n{FLAG_REMEDIATION}\n", tmp_path)


@POSIX_ARGV_ONLY
def test_a_created_by_that_is_not_utf8_is_refused(tmp_path):
    """`--created-by Jos<e9>` from a terminal whose encoding is not the
    locale's printed `created by   Jos\\xe9` and exited 0."""
    result = init(tmp_path, {}, "--created-by", LEGACY_NAME, dry_run=True)
    refused(result, f"{REFUSED}--created-by is {LEGACY_NAME!r}, "
                    f"{WRITTEN_INTO}{NOT_UTF8_REASON}.\n{FLAG_REMEDIATION}\n",
            tmp_path)


@DRY_RUN
@pytest.mark.parametrize("value, reason", UNWRITABLE)
def test_a_git_author_name_no_file_can_hold_is_refused_before_anything_exists(
        tmp_path, value, reason, dry_run):
    """The same names through GIT_AUTHOR_NAME, which answers when no
    `--created-by` is given: refused as the setting is, and the remediation
    names the variable."""
    result = init(tmp_path, {"GIT_AUTHOR_NAME": value}, dry_run=dry_run)
    refused(result, f"{REFUSED}{CREATOR_NOT_GIVEN} is {value!r}, "
                    f"{WRITTEN_INTO}{reason}.\n{ENV_REMEDIATION}\n", tmp_path)


@POSIX_ENVIRONMENT_ONLY
def test_a_git_author_name_that_is_not_utf8_is_refused(tmp_path):
    """GIT_AUTHOR_NAME `Jos<e9>` printed `created by   Jos\\xe9` and exited
    0; `os.environ` keeps the byte as `sys.argv` does."""
    result = init(tmp_path, {"GIT_AUTHOR_NAME": LEGACY_NAME}, dry_run=True)
    refused(result, f"{REFUSED}{CREATOR_NOT_GIVEN} is {LEGACY_NAME!r}, "
                    f"{WRITTEN_INTO}{NOT_UTF8_REASON}.\n{ENV_REMEDIATION}\n",
            tmp_path)


def test_the_setting_keeps_the_remediation_426_gave_it(tmp_path):
    """`git config user.name` answering is told what #426 told it, whole:
    each source's remediation names that source, and only it."""
    value = "Ada\nLovelace"
    result = init(tmp_path, user_name(value), dry_run=True)
    refused(result, f"{REFUSED}{CREATOR_NOT_GIVEN} is {value!r}, "
                    f"{WRITTEN_INTO}{LINE_BREAK}.\n{CONFIG_REMEDIATION}\n",
            tmp_path)


@DRY_RUN
@pytest.mark.parametrize("flags, env, recorded", [
    pytest.param(("--created-by", "José"), {}, "José", id="flag"),
    pytest.param((), {"GIT_AUTHOR_NAME": "Mehr\u200cdad"}, "Mehr\u200cdad",
                 id="env"),
])
def test_a_creator_that_is_text_still_initialises(tmp_path, flags, env,
                                                   recorded, dry_run):
    """THE CONTROLS: an accent and a U+200C ZERO WIDTH NON-JOINER are text a
    file holds, from the flag or the variable, as they are from the
    setting."""
    result = init(tmp_path, env, *flags, dry_run=dry_run)
    initialised(result, tmp_path, dry_run)
    assert f"created by   {recorded} on 2026-09-02" in result.stdout
    if not dry_run:
        manifest = load_yaml(tmp_path / "work" / HOLDER / "family.yaml")
        assert manifest["created_by"] == recorded


# ---------------------------------------------------------------------------
# The identity git makes the holder's first commit as
# ---------------------------------------------------------------------------

#: Git's own words, in English, so they are fixed text: no translation runs
#: under the C locale, and UTF-8 mode keeps the tool's own output UTF-8.
GIT_IN_ENGLISH = {"LC_ALL": "C", "PYTHONUTF8": "1"}
#: An identity git takes, every variable of it set, so a row names exactly
#: what it changes; no date, so git uses the moment of the commit.
IDENTITY = {"GIT_AUTHOR_NAME": "Ada", "GIT_AUTHOR_EMAIL": "ada@example.invalid",
            "GIT_COMMITTER_NAME": "Ada",
            "GIT_COMMITTER_EMAIL": "ada@example.invalid",
            "GIT_AUTHOR_DATE": "", "GIT_COMMITTER_DATE": ""}

BAD_IDENTITY = "REFUSED family-bad-commit-identity: "
DISALLOWED = "fatal: name consists only of disallowed characters:"
COMMIT_IDENTITY_REMEDIATION = (
    NOTHING + "Correct each variable named, or unset it, and run again. "
    "`init` makes the holder's first commit with them only after the "
    "holder's remote and work directory exist, and git would refuse them "
    "there. Unset or empty, a name or an address is `init`'s own and a date "
    "is the moment of the commit; --created-by sets who `family.yaml` "
    "records, not who git makes the commit as.")


def refuses_the(role: str, ident: str, listed: str, said: str) -> str:
    return (f"git refuses the {role} the holder's first commit would be made "
            f"as, from {listed} (`git var {ident}`: {said})")


AUTHOR_BLANK = refuses_the(
    "author", "GIT_AUTHOR_IDENT",
    "GIT_AUTHOR_NAME '   ' and GIT_AUTHOR_EMAIL 'ada@example.invalid'",
    DISALLOWED)
COMMITTER_BLANK = refuses_the(
    "committer", "GIT_COMMITTER_IDENT",
    "GIT_COMMITTER_NAME '   ' and GIT_COMMITTER_EMAIL 'ada@example.invalid'",
    DISALLOWED)


def identity(**changed: str) -> dict:
    """`IDENTITY` with `changed`, git in English, and a good
    `git config user.name`, which is the creator where `changed` blanks
    GIT_AUTHOR_NAME."""
    return user_name("Ada Lovelace", **{**IDENTITY, **GIT_IN_ENGLISH,
                                         **changed})


@LANDING
@DRY_RUN
def test_a_blank_git_author_name_is_refused_before_the_remote_exists(
        tmp_path, landing, dry_run):
    """THE ISSUE'S ROW: GIT_AUTHOR_NAME and GIT_COMMITTER_NAME `'   '` and a
    good `user.name`. The manifest was written from `Ada Lovelace`, and
    `git commit` then refused the whitespace, exit 2, after
    `<remotes>/Contoso.git` and the work directory existed. Now git is asked
    first, about both roles, and nothing exists."""
    result = init(tmp_path, identity(GIT_AUTHOR_NAME="   ",
                                     GIT_COMMITTER_NAME="   "),
                  landing=landing, dry_run=dry_run)
    refused(result, f"{BAD_IDENTITY}{AUTHOR_BLANK}; {COMMITTER_BLANK}.\n"
                    f"{COMMIT_IDENTITY_REMEDIATION}\n", tmp_path)


@DRY_RUN
@pytest.mark.parametrize("changed, expected", [
    pytest.param({"GIT_AUTHOR_NAME": "   "}, AUTHOR_BLANK, id="author-blank"),
    pytest.param({"GIT_COMMITTER_NAME": "   "}, COMMITTER_BLANK,
                 id="committer-blank"),
    pytest.param({"GIT_AUTHOR_NAME": "<>"}, refuses_the(
        "author", "GIT_AUTHOR_IDENT",
        "GIT_AUTHOR_NAME '<>' and GIT_AUTHOR_EMAIL 'ada@example.invalid'",
        f"{DISALLOWED} <>"), id="author-only-delimiters"),
    pytest.param({"GIT_COMMITTER_DATE": "garbage"}, refuses_the(
        "committer", "GIT_COMMITTER_IDENT",
        "GIT_COMMITTER_NAME 'Ada', GIT_COMMITTER_EMAIL 'ada@example.invalid' "
        "and GIT_COMMITTER_DATE 'garbage'",
        "fatal: invalid date format: garbage"), id="committer-date"),
])
def test_each_identity_git_refuses_is_refused_in_its_words(
        tmp_path, changed, expected, dry_run):
    """GIT'S OWN ANSWER, not a copy of its rules: one role at a time, and
    what git refuses that is not whitespace (a name of only `<>`, a date it
    cannot read), each of which failed at the same commit. The detail names
    every variable of the role that was set, and git's words say which."""
    result = init(tmp_path, identity(**changed), dry_run=dry_run)
    refused(result, f"{BAD_IDENTITY}{expected}.\n"
                    f"{COMMIT_IDENTITY_REMEDIATION}\n", tmp_path)


def test_created_by_does_not_get_past_a_blank_git_author_name(tmp_path):
    """`--created-by` sets who `family.yaml` records; git still makes the
    commit as GIT_AUTHOR_NAME, so the run is still refused."""
    result = init(tmp_path, identity(GIT_AUTHOR_NAME="   "),
                  "--created-by", "T H")
    refused(result, f"{BAD_IDENTITY}{AUTHOR_BLANK}.\n"
                    f"{COMMIT_IDENTITY_REMEDIATION}\n", tmp_path)


def test_an_identity_left_empty_still_initialises(tmp_path):
    """THE CONTROL: every name and address EMPTY is `env_commit`'s fallback,
    which git takes, so nothing is refused and the holder is made."""
    empty = {key: "" for key in IDENTITY}
    result = init(tmp_path, user_name("Ada Lovelace", **empty,
                                      **GIT_IN_ENGLISH))
    initialised(result, tmp_path, dry_run=False)


# ---------------------------------------------------------------------------
# The holder's name, on every disk it is cloned to
# ---------------------------------------------------------------------------

HOLDER_NAME_REMEDIATION = (
    NOTHING + "Choose another --family. It names the holder, its repository "
    "and the folder it is cloned into and, unless --work-dir is given, the "
    "family folder around it, which `make siblings` looks for by that very "
    "name; and a holder is cloned on Windows too, where no file or folder "
    "can be called a device name (`CON`, `PRN`, `AUX`, `NUL`, "
    "`COM1`-`COM9`, `LPT1`-`LPT9`, in any case, with or without an "
    "extension), and a name ending in a dot or a space is made under another "
    "name. There is no --force.")


def init_family(tmp_path, family: str, *flags: str, landing="--work-dir",
                dry_run: bool):
    """`init` with `--family family`: given after the harness's own
    `--family`, and argparse keeps the last."""
    return init(tmp_path, {}, "--family", family, "--created-by", "T H",
                *flags, landing=landing, dry_run=dry_run)


def bad_holder_name(family: str) -> str:
    return (f"REFUSED family-bad-holder-name: --family is {family!r}, which "
            "names the holder and the folders `init` makes for it, and "
            f"`{family}` is a Windows device name (with or without an "
            "extension), which cannot be created there.\n"
            f"{HOLDER_NAME_REMEDIATION}\n")


@pytest.mark.parametrize("family", ["CON", "Con", "nul", "PRN", "Aux",
                                    "COM1", "Lpt9"])
def test_a_windows_device_name_is_refused_as_the_holders_name(tmp_path,
                                                              family):
    """THE ISSUE'S ROWS: each exited 0 with a plan for a holder no Windows
    disk can clone. Now `family-bad-holder-name`, in any case, in the leg
    path rule's words."""
    result = init_family(tmp_path, family, dry_run=True)
    refused(result, bad_holder_name(family), tmp_path)


@LANDING
def test_a_real_run_with_a_device_name_makes_nothing(tmp_path, landing):
    """The real run refuses alike, under `--into` (the family folder would be
    `CON/`) and `--work-dir`, before any remote or folder exists."""
    result = init_family(tmp_path, "CON", landing=landing, dry_run=False)
    refused(result, bad_holder_name("CON"), tmp_path)


@DRY_RUN
@pytest.mark.parametrize("family, flags, expected", [
    pytest.param("Orbit.", (), "REFUSED family-bad-id: ", id="dot"),
    pytest.param("Orbit.", ("--id", "orbit"),
                 "REFUSED naming-unclassified: 'Orbit.' matches no family in "
                 "the naming policy\n", id="dot-explicit-id"),
    pytest.param("Orbit ", (), "REFUSED unsafe-value: --family is 'Orbit ', ",
                 id="space"),
])
def test_a_name_windows_strips_was_already_refused_before_anything_exists(
        tmp_path, family, flags, expected, dry_run):
    """THE RULE'S OTHER TWO ROWS: a trailing dot or space, which Windows
    strips, so `make siblings` there would never find its folder. The
    policy's one CamelCase token holds no dot and `checked_value` no space,
    so each is refused before the holder's name is asked, as on main, and
    nothing exists."""
    result = init_family(tmp_path, family, *flags, dry_run=dry_run)
    refused(result, expected, tmp_path)


@pytest.mark.parametrize("family", ["COM0", "LPT10", "CONX", "Conan",
                                    "Nullify"])
def test_a_name_that_only_starts_like_a_device_is_not_refused(tmp_path,
                                                              family):
    """THE CONTROLS: the rule's device names are `CON`, `PRN`, `AUX`, `NUL`,
    `COM1`-`COM9` and `LPT1`-`LPT9`, exactly; a name that only begins like
    one is a folder Windows makes."""
    result = init_family(tmp_path, family, dry_run=True)
    initialised(result, tmp_path, dry_run=True)
    assert f"family       {family} ({family.lower()})" in result.stdout
