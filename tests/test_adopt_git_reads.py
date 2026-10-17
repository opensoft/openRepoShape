# SPDX-License-Identifier: Apache-2.0
"""What `adopt-project.py` asks git, read as bytes it did not write (#292).

`_elector` asks `git config user.name` when `--elected-by` is not given, and
`_remote_repository` asks `git remote get-url origin` of a local source. git
keeps both as the bytes it was given, so either can hold a byte that is not
UTF-8 without anyone having done anything wrong: a name saved in a legacy
code page, a clone of a directory named in one. Both were decoded strictly,
so `plan` (and, for the URL, `check` and `execute`) ended in a
`UnicodeDecodeError` traceback, exit 1, naming neither the git setting nor
the flag that avoids it, and nothing was created.

Now the name is kept as a lone surrogate, as `sys.argv` keeps one, and
`plan` refuses it as #255's `adopt-unwritable-value`, named as `git config
user.name`, with `--elected-by` as the way past it, and writes no plan. A
URL that is not UTF-8 is no origin: `plan` takes `--org`, or refuses as
`adopt-no-org` -- reached at last: `checked_value` refused the `-` that stood
in for a missing org first, as `--org is '-'`, a value nobody passed -- and
`check` and `execute` adopt the source by its path.

The runs are `test_adopt_template_values.py`'s: on a strict stdout, answered
in bytes, and each read for a traceback.

`_default_branch` asks `git symbolic-ref` which branch the source is on, and
git keeps that name as bytes too (#425): `git branch caf<e9>` is legal. Read
strictly, a HEAD or an `origin/HEAD` naming such a branch ended `plan`,
`check` and `execute` in the same traceback, from `Source.open`. Now the byte
is kept as a lone surrogate, and `plan` refuses the name as `unsafe-value`
for `--tracking-branch` before any plan is written; `check` and `execute`
name it too, or adopt past it when the plan tracks a branch that is text.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (REPO, git, make_source_repo,
                      skip_where_a_name_cannot_be_not_utf_8)
from test_adopt_template_values import (ADOPT_REFUSED, PLAN_FILE, PLAN_OK,
                                        PROJECT, REMOTES, SPLIT_BRANCH,
                                        VERIFIED, WORK, adopted, answer,
                                        assert_no_traceback,
                                        assert_no_traceback_and_no_leg,
                                        checked, executed, needs_filter_repo,
                                        planned, said)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml  # noqa: E402

#: `José` as a legacy code page saves it: the byte 0xE9 is Latin-1's `é`,
#: and no UTF-8.
LATIN1_NAME = b"Jos\xe9"
#: An origin URL holding that byte, as a clone of a directory named `café`
#: in Latin-1 has one.
NOT_UTF8_URL = b"../caf\xe9/repo.git"
#: The byte in a url, and the same url in ASCII, which ends in an `org/repo`
#: the tool reads. Urls, because a path names no repository in any spelling
#: since #521: the pair differs in the byte alone.
NOT_UTF8_SCP = b"git@example.invalid:caf\xe9/repo.git"
ASCII_URL = b"git@example.invalid:cafe/repo.git"

#: Said of all the sources that name no org: one with no origin, one whose
#: origin URL is not UTF-8 or ends in no `org/repo`, and, since #521, one
#: whose origin is a path. The sentence was "the source has no `origin`",
#: which is false of all but the first.
NO_ORG = (b"REFUSED adopt-no-org: the source's `origin` names no "
          b"organisation this tool can read: it has none, its URL is not "
          b"UTF-8 or ends in no `org/repo`, or it is a path, which names no "
          b"repository on GitHub\n"
          b"Remediation: pass --org <org>.\n")
#: An origin URL that is UTF-8 and ends in no `org/repo` at all.
NO_PAIR_URL = b"repo.git"


def by_git_config(base: Path, source: Path, extra: dict,
                  *flags: str) -> subprocess.CompletedProcess:
    """`plan` as `planned` runs it, but with no --elected-by unless `flags`
    gives one, so the elector is `git config user.name`."""
    return adopted("plan", "--source", str(source), "--project", PROJECT,
                   "--org", "testorg", "--elected-on", "2026-09-02",
                   "--out", str(base / PLAN_FILE), "--work-dir",
                   str(base / WORK), *flags, extra=extra)


def without_org(base: Path, source: Path,
                *flags: str) -> subprocess.CompletedProcess:
    """`plan` as `planned` runs it, but with no --org, so the org is what
    the source's `origin` names, and with `flags` after it."""
    return adopted("plan", "--source", str(source), "--project", PROJECT,
                   "--elected-by", "Test Human", "--elected-on", "2026-09-02",
                   "--out", str(base / PLAN_FILE), "--work-dir",
                   str(base / WORK), *flags)


def command_scope(key: str, value: bytes) -> dict:
    """`key` set to `value` in git's command scope, as an environment
    (`GIT_CONFIG_COUNT`, `GIT_CONFIG_KEY_<n>`, `GIT_CONFIG_VALUE_<n>`, git
    2.31), for every git the run starts. That scope outranks every config
    file, this checkout's own `.git/config` included, which `~/.gitconfig`
    and `GIT_CONFIG_GLOBAL` do not.

    APPENDED to what the environment already holds, never in place of it:
    the Windows job sets `GIT_CONFIG_COUNT=2` (`core.autocrlf` and
    `core.longpaths`, `.github/workflows/tests.yml`), and a count of 1 here
    would drop both. The last entry of a key is the one git reads.

    The value goes in as the bytes it is, through `os.fsdecode`, which is how
    `sys.argv` and `os.environ` carry a byte that is not UTF-8 on POSIX. A
    Windows environment is text, so the caller does not use this there."""
    held = int(os.environ.get("GIT_CONFIG_COUNT") or 0)
    return {"GIT_CONFIG_COUNT": str(held + 1),
            f"GIT_CONFIG_KEY_{held}": key,
            f"GIT_CONFIG_VALUE_{held}": os.fsdecode(value)}


def global_user_name(base: Path, name: bytes) -> dict:
    """The environment of a person whose `user.name` is `name`, written as
    bytes, for `git config user.name` asked where `_elector` asks it.

    Two routes, because two things outrank a global config. `GIT_CONFIG_GLOBAL`
    (git 2.32) stands in for `~/.gitconfig` for every git the run starts, and
    is the only route where an environment variable cannot carry the byte
    (Windows). A `user.name` in this checkout's own config wins over that
    file, though, and the shared checkout has one wherever somebody has set
    their identity there: so on POSIX the name is given in command scope too
    (`command_scope`), which wins over both. Without it the four tests that
    use this skipped in such a checkout, and the `_elector` fix went untested.
    Skipped where `git config user.name` still does not answer `name`."""
    config = base / "gitconfig"
    config.write_bytes(b"[user]\n\tname = " + name + b"\n")
    extra = {"GIT_CONFIG_GLOBAL": str(config)}
    if os.name == "posix":
        extra.update(command_scope("user.name", name))
    read = subprocess.run(["git", "config", "user.name"], cwd=str(REPO),
                          capture_output=True, env={**os.environ, **extra},
                          check=False)
    if read.stdout.rstrip(b"\r\n") != name:
        pytest.skip("`git config user.name` here is not read from "
                    f"GIT_CONFIG_GLOBAL: {read.stdout!r}")
    return extra


def with_origin(source: Path, url: bytes) -> Path:
    """`source`, its `origin` set to `url`. Written into its config as
    bytes, so the byte reaches git as it is on every platform (a Windows
    command line is text). Skipped where git does not give it back so."""
    config = source / ".git" / "config"
    config.write_bytes(config.read_bytes()
                       + b'[remote "origin"]\n\turl = ' + url + b"\n")
    read = subprocess.run(["git", "remote", "get-url", "origin"],
                          cwd=str(source), capture_output=True, check=False)
    if read.stdout.rstrip(b"\r\n") != url:
        pytest.skip(f"`git remote get-url origin` here is {read.stdout!r}, "
                    f"not {url!r}")
    return source


# --- the `user.name` these tests give ----------------------------------------

def asked(key: str, env: dict, cwd: Path = REPO) -> bytes:
    """`git config <key>` in `cwd` under `env`: what git answers, as bytes."""
    read = subprocess.run(["git", "config", key], cwd=str(cwd),
                          capture_output=True, env=env, check=False)
    return read.stdout.rstrip(b"\r\n")


posix_only = pytest.mark.skipif(
    os.name != "posix", reason="a Windows environment is text: there the "
    "name is given in `GIT_CONFIG_GLOBAL`'s file only")


@posix_only
def test_the_user_name_given_outranks_a_checkouts_own(tmp_path):
    """The four tests below ask `git config user.name` in this checkout, and
    skipped, with the `_elector` fix untested, wherever its own `.git/config`
    set one: that outranks `GIT_CONFIG_GLOBAL`. Here is such a checkout,
    made in `tmp_path`, so the answer does not depend on whose machine this
    is: the environment `global_user_name` gives is read as `name`, not as the
    checkout's `Local Name`."""
    checkout = tmp_path / "local"
    checkout.mkdir()
    git("init", "-q", cwd=checkout)
    git("config", "user.name", "Local Name", cwd=checkout)
    local = git("config", "--local", "user.name", cwd=checkout)
    assert local.stdout.strip() == "Local Name", local.stderr
    extra = global_user_name(tmp_path, LATIN1_NAME)
    assert asked("user.name", {**os.environ, **extra}, checkout) \
        == LATIN1_NAME


@posix_only
def test_the_user_name_given_is_appended_to_the_config_the_environment_holds(
        tmp_path, monkeypatch):
    """The Windows job sets `GIT_CONFIG_COUNT=2`, `core.autocrlf` and
    `core.longpaths`, for the whole run. A count of 1 for the name would
    drop both, and every test after it would run with git's own line-end and
    long-path defaults. The two slots here are the job's, under keys no
    config of a machine this runs on sets."""
    for variable, value in {"GIT_CONFIG_COUNT": "2",
                            "GIT_CONFIG_KEY_0": "test.heldone",
                            "GIT_CONFIG_VALUE_0": "one",
                            "GIT_CONFIG_KEY_1": "test.heldtwo",
                            "GIT_CONFIG_VALUE_1": "two"}.items():
        monkeypatch.setenv(variable, value)
    extra = global_user_name(tmp_path, LATIN1_NAME)
    assert extra["GIT_CONFIG_COUNT"] == "3", extra
    env = {**os.environ, **extra}
    assert asked("test.heldone", env) == b"one"
    assert asked("test.heldtwo", env) == b"two"
    assert asked("user.name", env) == LATIN1_NAME


# --- `git config user.name` ---------------------------------------------------

def test_plan_refuses_a_user_name_that_is_not_utf8(tmp_path):
    """The issue's first row: on the base `plan` ended in a
    `UnicodeDecodeError` traceback from `_elector`, exit 1. Now it is #255's
    refusal, which names the setting and the flag, and no plan is
    written."""
    extra = global_user_name(tmp_path, LATIN1_NAME)
    source = make_source_repo(tmp_path / "Thing")
    refused = by_git_config(tmp_path, source, extra)
    assert_no_traceback_and_no_leg(tmp_path, {"plan": refused})
    assert refused.returncode == 2, said(refused)
    assert ADOPT_REFUSED + b"--elected-by (not given, so `git config " \
        b"user.name`) is 'Jos\\udce9', which `execute` writes into the " \
        b"assembly root's `project.yaml` and `README.md`, and it holds a " \
        b"byte that is not UTF-8.\n" in refused.stderr, said(refused)
    assert b"Remediation: no plan was written. Pass each value named " \
        b"again, retyped; when `--elected-by` is not given, `plan` reads " \
        b"`git config user.name`, so pass the flag or correct that." \
        in refused.stderr, said(refused)
    assert not (tmp_path / PLAN_FILE).exists()


def no_user_name(base: Path, how: str) -> dict:
    """The environment of a person whose `git config user.name` gives
    `_elector` nothing. `unset`: no config file names one, `GIT_CONFIG_GLOBAL`
    and `GIT_CONFIG_SYSTEM` (git 2.32) standing in for an empty `~/.gitconfig`
    and system file, and `HOME` a directory of its own. `empty`: the setting
    is there and holds no text, in command scope (`command_scope`), which
    outranks this checkout's own config as the files do not. Skipped where
    git still answers a name."""
    blank = base / "gitconfig-blank"
    blank.write_text("", encoding="utf-8")
    home = base / "home"
    home.mkdir()
    extra = {"GIT_CONFIG_GLOBAL": str(blank), "GIT_CONFIG_SYSTEM": str(blank),
             "HOME": str(home)}
    if how == "empty":
        extra.update(command_scope("user.name", b""))
    read = asked("user.name", {**os.environ, **extra})
    if read:
        pytest.skip(f"`git config user.name` here still answers {read!r}")
    return extra


#: What `plan` says of an elector it took from `git config user.name`, which
#: gave it nothing (#529): the name the unwritable-value path gives the same
#: default, `--elected-by (not given, so `git config user.name`)`, and not
#: `--elected-by is ''`, which names a flag nobody passed.
NO_ELECTOR = (b"REFUSED adopt-manifest-invalid: --elected-by (not given, so "
              b"`git config user.name`) is '', which the project's own "
              b"validate-manifest.py refuses: manifest-elected-by: "
              b"elected_by is empty.")


@pytest.mark.parametrize(
    "how", ["unset", pytest.param("empty", marks=posix_only)])
def test_plan_names_the_empty_default_it_took_for_the_elector(tmp_path, how):
    """#529. With no `--elected-by` and no `git config user.name`, `plan` was
    refused `adopt-manifest-invalid: --elected-by is ''`, naming a flag the
    person never passed; only the unwritable-value path said the value was
    not given. Now it names the default it fell back to, as that path does,
    and the code, the exit status and the validator's own words are as they
    were: the refusal is still the validator's, and no plan is written."""
    extra = no_user_name(tmp_path, how)
    source = make_source_repo(tmp_path / "Thing")
    refused = by_git_config(tmp_path, source, extra)
    assert_no_traceback_and_no_leg(tmp_path, {"plan": refused})
    assert refused.returncode == 2, said(refused)
    assert NO_ELECTOR in refused.stderr, said(refused)
    assert b"--elected-by is ''" not in refused.stderr, said(refused)
    assert b"No plan was written." in refused.stderr, said(refused)
    assert not (tmp_path / PLAN_FILE).exists()


def test_plan_records_the_elector_given_where_user_name_is_unset(tmp_path):
    """Control: `--elected-by` given, `git config user.name` is not asked,
    and nothing is refused for its being empty."""
    extra = no_user_name(tmp_path, "unset")
    source = make_source_repo(tmp_path / "Thing")
    done = by_git_config(tmp_path, source, extra, "--elected-by", "Test Human")
    assert_no_traceback({"plan": done})
    assert done.returncode == 0, said(done)
    assert load_yaml(tmp_path / PLAN_FILE)["elected_by"] == "Test Human"


#: What `plan` says of a `--elected-by ''` the person passed (L2-53): the
#: flag as typed, in the validator's words for an empty elector.
EMPTY_ELECTOR = (b"REFUSED adopt-manifest-invalid: --elected-by is '', which "
                 b"the project's own validate-manifest.py refuses: "
                 b"manifest-elected-by: elected_by is empty.")


@pytest.mark.parametrize("user_name", ["unset", "configured"])
def test_plan_refuses_an_empty_elector_that_was_passed(tmp_path, user_name):
    """L2-53. `--elected-by ''` was read as not passed: with a `git config
    user.name` the plan recorded that name, exit 0, though `--help` says
    "not blank"; with none, the refusal said `--elected-by (not given, so
    `git config user.name`) is ''` of a flag the person passed. It is the
    flag's own value now, refused by name as a blank one is (#261), and
    `git config user.name` does not stand in for it."""
    extra = (no_user_name(tmp_path, "unset") if user_name == "unset"
             else global_user_name(tmp_path, b"Jose"))
    source = make_source_repo(tmp_path / "Thing")
    refused = by_git_config(tmp_path, source, extra, "--elected-by", "")
    assert_no_traceback_and_no_leg(tmp_path, {"plan": refused})
    assert refused.returncode == 2, said(refused)
    assert EMPTY_ELECTOR in refused.stderr, said(refused)
    assert b"not given" not in refused.stderr, said(refused)
    assert not (tmp_path / PLAN_FILE).exists()


@pytest.mark.parametrize("name", [b"Jose", "José".encode("utf-8")],
                         ids=["ascii", "utf8"])
def test_plan_records_a_user_name_that_is_utf8(tmp_path, name):
    """Controls: a name git holds as UTF-8 is recorded as itself, as on the
    base. `surrogateescape` changes nothing a strict decode reads."""
    extra = global_user_name(tmp_path, name)
    source = make_source_repo(tmp_path / "Thing")
    done = by_git_config(tmp_path, source, extra)
    assert_no_traceback({"plan": done})
    assert done.returncode == 0, said(done)
    plan = load_yaml(tmp_path / PLAN_FILE)
    assert plan["elected_by"] == name.decode("utf-8")


@needs_filter_repo
def test_elected_by_given_adopts_under_a_user_name_that_is_not_utf8(
        tmp_path):
    """Control: with --elected-by given, `_elector` is not asked, and the
    same Latin-1 `user.name` stops nothing: `plan`, `check` and `execute`,
    all under it, adopt, and the plan records the flag's value."""
    extra = global_user_name(tmp_path, LATIN1_NAME)
    source = make_source_repo(tmp_path / "Thing")
    runs = {"plan": by_git_config(tmp_path, source, extra,
                                  "--elected-by", "Test Human")}
    assert runs["plan"].returncode == 0, said(runs["plan"])
    assert load_yaml(tmp_path / PLAN_FILE)["elected_by"] == "Test Human"
    answer(tmp_path)
    runs["check"] = checked(tmp_path, extra)
    runs["execute"] = executed(tmp_path, extra)
    assert_no_traceback(runs)
    assert PLAN_OK in runs["check"].stdout, said(runs["check"])
    assert runs["execute"].returncode == 0, said(runs["execute"])
    assert VERIFIED in runs["execute"].stdout, said(runs["execute"])


# --- `git remote get-url origin` ----------------------------------------------

@pytest.mark.parametrize("url, repository",
                         [(NOT_UTF8_URL, None), (NOT_UTF8_SCP, None),
                          (ASCII_URL, "cafe/repo")],
                         ids=["not-utf8", "not-utf8-url", "ascii"])
def test_plan_reads_an_origin_that_is_not_utf8_as_none(tmp_path, url,
                                                       repository):
    """The issue's last row, with --org: on the base `plan` ended in a
    `UnicodeDecodeError` traceback from `_remote_repository`, exit 1, and
    wrote no plan. Now it plans, and records no repository. The ASCII URL
    is the control: its `org/repo` is read, so the None of the url beside it
    is the byte's, and the plan is written in that name, which `plan`
    refuses any other for (#499)."""
    source = with_origin(make_source_repo(tmp_path / "Thing"), url)
    done = planned(tmp_path, source, "--org", "cafe", "--project", "repo")
    assert_no_traceback({"plan": done})
    assert done.returncode == 0, said(done)
    assert load_yaml(tmp_path / PLAN_FILE)["source"]["repository"] \
        == repository


@pytest.mark.parametrize("url", [NOT_UTF8_URL, None, NO_PAIR_URL],
                         ids=["not-utf8", "no-origin", "no-pair"])
def test_plan_without_org_refuses_a_source_that_names_none(tmp_path, url):
    """With no --org, an origin that is not UTF-8 is `adopt-no-org`, as a
    source with no origin at all is, and one whose URL ends in no `org/repo`.
    On the base the first was the traceback, and the second `REFUSED
    unsafe-value: --org is '-'`: the stand-in for a missing org met
    `checked_value` before `adopt-no-org` was asked, which no run had ever
    reached. The sentence is the same for the three, and says each: the
    first and the last are sources that HAVE an origin, so "the source has
    no `origin`" was false of them."""
    source = make_source_repo(tmp_path / "Thing")
    if url is not None:
        with_origin(source, url)
    refused = without_org(tmp_path, source)
    assert_no_traceback({"plan": refused})
    assert refused.returncode == 2, said(refused)
    assert NO_ORG in refused.stderr, said(refused)
    assert b"unsafe-value" not in refused.stderr, said(refused)
    assert not (tmp_path / PLAN_FILE).exists()


@pytest.mark.parametrize("org", ["-evil", "-", "my org"],
                         ids=["leading-dash", "dash-only", "space"])
def test_plan_refuses_an_unsafe_org_that_is_passed(tmp_path, org):
    """`--org` is `checked_value`'s question too, and #292 moved it below
    `adopt-no-org`: a `plan` that stopped asking it wrote `org: "-evil"` and
    exited 0, `check` said `plan ok`, and only `execute` refused the value,
    at `_repository_urls`. A value passed is refused as `unsafe-value`,
    naming `--org`, before any plan is written."""
    source = make_source_repo(tmp_path / "Thing")
    refused = planned(tmp_path, source, f"--org={org}")
    assert_no_traceback({"plan": refused})
    assert refused.returncode == 2, said(refused)
    assert b"REFUSED unsafe-value: --org is " + repr(org).encode("ascii") \
        + b", which is not a value this tool will put on a `git` or `gh` " \
        b"command line\n" in refused.stderr, said(refused)
    assert not (tmp_path / PLAN_FILE).exists()


def test_plan_without_org_takes_the_org_an_ascii_origin_names(tmp_path):
    """Control: an origin that names `cafe/repo` is the org, as on the
    base, for a plan in the source's own name (#499)."""
    source = with_origin(make_source_repo(tmp_path / "Thing"), ASCII_URL)
    done = without_org(tmp_path, source, "--project", "repo")
    assert_no_traceback({"plan": done})
    assert done.returncode == 0, said(done)
    assert load_yaml(tmp_path / PLAN_FILE)["org"] == "cafe"


@needs_filter_repo
def test_check_and_execute_adopt_a_source_whose_origin_is_not_utf8(
        tmp_path):
    """The issue's `check` and `execute` rows: a plan written before the
    origin was set, then both ended in the traceback, before any leg
    existed. Now `check` says `plan ok`, and `execute` adopts."""
    source = make_source_repo(tmp_path / "Thing")
    runs = {"plan": planned(tmp_path, source)}
    assert runs["plan"].returncode == 0, said(runs["plan"])
    with_origin(source, NOT_UTF8_URL)
    answer(tmp_path)
    runs["check"] = checked(tmp_path)
    runs["execute"] = executed(tmp_path)
    assert_no_traceback(runs)
    assert runs["check"].returncode == 0, said(runs["check"])
    assert PLAN_OK in runs["check"].stdout, said(runs["check"])
    assert runs["execute"].returncode == 0, said(runs["execute"])
    assert VERIFIED in runs["execute"].stdout, said(runs["execute"])


@needs_filter_repo
def test_a_utf8_clone_of_a_source_whose_path_is_not_utf8_adopts(tmp_path):
    """#255 refuses, under --local-remote-dir, a source whose own path is
    not UTF-8: that path is the clone URL `execute` writes. A clone of it
    at a path that is text has the old path as its origin, so `execute
    --source <the clone>` ended in this issue's traceback; it now adopts.
    Skipped where no directory can be named with the byte 0xE9 (Windows,
    macOS's APFS) or git will not work in one."""
    skip_where_a_name_cannot_be_not_utf_8(tmp_path)
    parent = Path(os.fsdecode(os.path.join(os.fsencode(tmp_path),
                                           b"caf\xe9")))
    parent.mkdir()
    try:
        source = make_source_repo(parent / "Thing")
    except AssertionError as exc:
        pytest.skip(f"git will not work under {parent.name!r} here: {exc}")
    clone = tmp_path / "clone"
    git("clone", "-q", "--", str(source), str(clone), cwd=tmp_path)
    runs = {"plan": planned(tmp_path, source)}
    assert runs["plan"].returncode == 0, said(runs["plan"])
    answer(tmp_path)
    runs["refused"] = executed(tmp_path)
    assert_no_traceback_and_no_leg(tmp_path, runs)
    assert runs["refused"].returncode == 2, said(runs["refused"])
    assert ADOPT_REFUSED in runs["refused"].stderr, said(runs["refused"])
    runs["execute"] = adopted("execute", "--plan", str(tmp_path / PLAN_FILE),
                              "--source", str(clone), "--yes",
                              "--local-remote-dir", str(tmp_path / REMOTES),
                              "--work-dir", str(tmp_path / "work-again"))
    assert_no_traceback(runs)
    assert runs["execute"].returncode == 0, said(runs["execute"])
    assert VERIFIED in runs["execute"].stdout, said(runs["execute"])


# --- `git symbolic-ref`: the branch the source is on (#425) ------------------

#: A branch git accepts and no UTF-8 text spells: `caf` and the byte 0xE9, as
#: a Latin-1 terminal types `café`.
NOT_UTF8_BRANCH = b"caf\xe9"
#: The same name as `Source.branch` holds it, and as `sys.argv` and
#: `os.environ` carry one on POSIX: the byte kept as a lone surrogate.
BRANCH = NOT_UTF8_BRANCH.decode("utf-8", "surrogateescape")
#: Where git can say that `BRANCH` is the source's default branch, in the
#: order `_default_branch` asks: `refs/remotes/origin/HEAD`, then HEAD.
ORIGIN_HEAD = "origin-head"
by_where = pytest.mark.parametrize("where", [ORIGIN_HEAD, "head"])
#: The flag that names the branch to track, so that the name that is not
#: UTF-8 is only the one the source is read at.
TRACKING = "--tracking-branch"

#: What `plan` says of that default branch, which it would track (#479): the
#: flag, where the value came from, and the byte spelled as the plan would
#: write it. The refusal is `checked_value`'s, for the alphabet a branch may
#: be written in, which a UTF-8 `café` fails alike.
UNSAFE_BRANCH = (
    b"REFUSED unsafe-value: --tracking-branch (not given, so the source's "
    b"default branch) is 'caf\\udce9', which is not a value this tool will "
    b"put on a `git` or `gh` command line\n")
#: What `check` finds, and `execute` refuses, of a plan that tracks `main`
#: once the source has no `main`: both branches, as the plan spells them.
BRANCH_LOST = (
    b"`tracking_branch` is `main`, which is no branch of the source (its "
    b"branches: `caf\\udce9`; the source's default branch is `caf\\udce9`)")
LOST_FINDING = b"FINDING plan-tracking-branch-missing: " + BRANCH_LOST
LOST_REFUSAL = b"REFUSED plan-tracking-branch-missing: "


def with_default_branch(source: Path, where: str) -> Path:
    """`source`, on `main`, with `BRANCH` as its default branch where git
    says one: `head` is its HEAD, and `origin-head` is
    `refs/remotes/origin/HEAD`, with HEAD left on `main`. `BRANCH` is one
    commit AHEAD of `main`, which is still a branch of the source: a plan
    that read the wrong branch would adopt the wrong commit, and a
    `--tracking-branch main` names a branch it has.

    Skipped where no branch can be named with the byte 0xE9 (Windows, macOS's
    APFS), or git here does not give the name back as it was written."""
    ref = "refs/remotes/origin/HEAD" if where == ORIGIN_HEAD else "HEAD"
    try:
        git("switch", "-q", "-c", BRANCH, cwd=source)
        git("commit", "-q", "--allow-empty", "-m", "One ahead", cwd=source)
        if where == ORIGIN_HEAD:
            git("switch", "-q", "main", cwd=source)
            for name in (BRANCH, "main"):
                git("update-ref", f"refs/remotes/origin/{name}", name,
                    cwd=source)
            git("symbolic-ref", ref, f"refs/remotes/origin/{BRANCH}",
                cwd=source)
    except (AssertionError, UnicodeError, OSError) as exc:
        pytest.skip(f"no branch here is named {NOT_UTF8_BRANCH!r}: {exc!r}")
    read = subprocess.run(["git", "symbolic-ref", ref], cwd=str(source),
                          capture_output=True, check=False)
    if not read.stdout.rstrip(b"\r\n").endswith(b"/" + NOT_UTF8_BRANCH):
        pytest.skip(f"`git symbolic-ref {ref}` here is {read.stdout!r}")
    return source


def moved_to_a_branch_that_is_not_utf8(base: Path) -> Path:
    """A source on `main`, planned and answered, whose `main` is then
    renamed `BRANCH`: a plan that tracks a branch the source no longer has,
    and a source whose HEAD is on one that is not UTF-8. Skipped as
    `with_default_branch` is."""
    source = make_source_repo(base / "Thing")
    made = planned(base, source)
    assert made.returncode == 0, said(made)
    answer(base)
    try:
        git("branch", "-m", "main", BRANCH, cwd=source)
    except (AssertionError, UnicodeError, OSError) as exc:
        pytest.skip(f"no branch here is named {NOT_UTF8_BRANCH!r}: {exc!r}")
    return source


@by_where
def test_plan_refuses_a_default_branch_that_is_not_utf8(tmp_path, where):
    """The issue's `plan` rows: on the base, a HEAD or an `origin/HEAD` on
    `caf<e9>` ended `plan` in a `UnicodeDecodeError` traceback from
    `_default_branch`, exit 1, and wrote no plan. Now the name is kept as a
    lone surrogate and refused as the `--tracking-branch` it would be,
    before any plan is written."""
    source = with_default_branch(make_source_repo(tmp_path / "Thing"), where)
    refused = planned(tmp_path, source)
    assert_no_traceback_and_no_leg(tmp_path, {"plan": refused})
    assert refused.returncode == 2, said(refused)
    assert UNSAFE_BRANCH in refused.stderr, said(refused)
    assert not (tmp_path / PLAN_FILE).exists()


def test_check_finds_a_plans_branch_gone_for_one_that_is_not_utf8(tmp_path):
    """The issue's `check` row: a plan written on `main`, then the source's
    branch renamed `caf<e9>`. On the base `check` ended in the traceback,
    from `Source.open`; now it finds what any other branch the source moved
    to would be (`plan-tracking-branch-missing`), naming both."""
    moved_to_a_branch_that_is_not_utf8(tmp_path)
    found = checked(tmp_path)
    assert_no_traceback({"check": found})
    assert found.returncode == 1, said(found)
    assert LOST_FINDING in found.stderr, said(found)


@needs_filter_repo
def test_execute_refuses_a_plans_branch_gone_for_one_that_is_not_utf8(
        tmp_path):
    """The issue's `execute` row: the same plan, and on the base the same
    traceback, with the remote directory holding nothing. Now `execute`
    refuses it with `check`'s finding, before any leg exists."""
    moved_to_a_branch_that_is_not_utf8(tmp_path)
    refused = executed(tmp_path)
    assert_no_traceback_and_no_leg(tmp_path, {"execute": refused})
    assert refused.returncode == 2, said(refused)
    assert LOST_REFUSAL in refused.stderr, said(refused)
    assert LOST_FINDING in refused.stderr, said(refused)


def planned_past(base: Path, where: str) -> tuple[Path, dict]:
    """`(source, runs)`: `plan --tracking-branch main` of a source whose
    default branch is `BRANCH` (`with_default_branch`), the plan answered,
    and `check`, each run there was. `main` is the branch to adopt into, so
    nothing is asked of the name that is not UTF-8."""
    source = with_default_branch(make_source_repo(base / "Thing"), where)
    runs = {"plan": planned(base, source, TRACKING, "main")}
    assert runs["plan"].returncode == 0, said(runs["plan"])
    answer(base)
    runs["check"] = checked(base)
    return source, runs


def tip_of(source: Path, ref: str) -> str:
    """The commit `ref` names in `source`, as git spells it."""
    return git("rev-parse", ref, cwd=source).stdout.strip()


@by_where
def test_plan_and_check_go_past_a_default_branch_that_is_not_utf8(tmp_path,
                                                                  where):
    """With the branch to track given, the default branch that is not UTF-8
    is only the one the source is read at: `plan` records it as the plan
    spells a byte (`\\udce9`) with ITS commit, which is not `main`'s, and
    `check` finds no fault."""
    source, runs = planned_past(tmp_path, where)
    assert_no_traceback(runs)
    plan = load_yaml(tmp_path / PLAN_FILE)
    read_at = plan["source"]
    assert read_at["default_branch"] == BRANCH
    assert read_at["commit"] == tip_of(source, BRANCH)
    assert plan["tracking_branch"] == "main"
    assert runs["check"].returncode == 0, said(runs["check"])
    assert PLAN_OK in runs["check"].stdout, said(runs["check"])


@needs_filter_repo
@by_where
def test_execute_adopts_a_source_whose_default_branch_is_not_utf8(tmp_path,
                                                                  where):
    """The same plan, `execute`d: the source is read at `caf<e9>`, so the
    split is made on ITS commit, and every source path is accounted for."""
    source, runs = planned_past(tmp_path, where)
    runs["execute"] = executed(tmp_path)
    assert_no_traceback(runs)
    assert runs["execute"].returncode == 0, said(runs["execute"])
    assert VERIFIED in runs["execute"].stdout, said(runs["execute"])
    assert tip_of(source, f"{SPLIT_BRANCH}^") == tip_of(source, BRANCH)
