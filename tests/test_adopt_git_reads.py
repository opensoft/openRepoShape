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
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO, git, make_source_repo
from test_adopt_template_values import (ADOPT_REFUSED, PLAN_FILE, PLAN_OK,
                                        PROJECT, REMOTES, VERIFIED, WORK,
                                        adopted, answer,
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
#: in Latin-1 has one; and the same URL in ASCII, which ends in an
#: `org/repo` the tool reads.
NOT_UTF8_URL = b"../caf\xe9/repo.git"
ASCII_URL = b"../cafe/repo.git"

#: Said of all three sources that name no org: one with no origin, one whose
#: origin URL is not UTF-8, and one whose URL ends in no `org/repo`. The
#: sentence was "the source has no `origin`", which is false of the last two.
NO_ORG = (b"REFUSED adopt-no-org: the source's `origin` names no "
          b"organisation this tool can read: it has none, its URL is not "
          b"UTF-8, or its URL ends in no `org/repo`\n"
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
                         [(NOT_UTF8_URL, None), (ASCII_URL, "cafe/repo")],
                         ids=["not-utf8", "ascii"])
def test_plan_reads_an_origin_that_is_not_utf8_as_none(tmp_path, url,
                                                       repository):
    """The issue's last row, with --org: on the base `plan` ended in a
    `UnicodeDecodeError` traceback from `_remote_repository`, exit 1, and
    wrote no plan. Now it plans, and records no repository. The ASCII URL
    is the control: its `org/repo` is read, so the None is the byte's, and
    the plan is written in that name, which `plan` refuses any other for
    (#499)."""
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


#: `(origin URL, the org it names, the code `plan` refuses it as, the rest of
#: the sentence)`: an org one of `plan`'s two gates refuses. The validator
#: refuses a `+` (`--org=test+org` is `test_adopt_manifest_values.py`'s
#: `org-plus`), and `checked_value` a space.
DERIVED_ORGS = [
    pytest.param(b"../test+org/Thing.git", "test+org",
                 b"adopt-manifest-invalid",
                 b"the project's own validate-manifest.py refuses: "
                 b"manifest-leg-repository: ", id="validator"),
    pytest.param(b"../my org/Thing.git", "my org", b"unsafe-value",
                 b"is not a value this tool will put on a `git` or `gh` "
                 b"command line\n", id="unsafe"),
]


@pytest.mark.parametrize("url, org, code, rest", DERIVED_ORGS)
def test_plan_names_an_org_it_took_from_the_origin_by_where_it_came_from(
        tmp_path, url, org, code, rest):
    """An org the source's `origin` names, with no `--org` given, was refused
    as `--org is 'test+org'`, the flag nobody passed (#529). It is named by
    where it came from, as the elector is, and the code and the rest of each
    sentence are as they were."""
    source = with_origin(make_source_repo(tmp_path / "Thing"), url)
    refused = without_org(tmp_path, source, "--project", "Thing")
    assert_no_traceback({"plan": refused})
    assert refused.returncode == 2, said(refused)
    assert b"REFUSED " + code + b": --org (not given, so the source's " \
        b"`origin`) is " + repr(org).encode("ascii") + b", which " + rest \
        in refused.stderr, said(refused)
    assert b"--org is " not in refused.stderr, said(refused)
    assert not (tmp_path / PLAN_FILE).exists()


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
    try:
        parent = Path(os.fsdecode(os.path.join(os.fsencode(tmp_path),
                                               b"caf\xe9")))
        parent.mkdir()
    except (OSError, UnicodeError) as exc:
        pytest.skip(f"no directory here is named b'caf\\xe9': {exc!r}")
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
