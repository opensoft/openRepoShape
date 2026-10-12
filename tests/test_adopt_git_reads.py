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


def without_org(base: Path, source: Path) -> subprocess.CompletedProcess:
    """`plan` as `planned` runs it, but with no --org, so the org is what
    the source's `origin` names."""
    return adopted("plan", "--source", str(source), "--project", PROJECT,
                   "--elected-by", "Test Human", "--elected-on", "2026-09-02",
                   "--out", str(base / PLAN_FILE), "--work-dir",
                   str(base / WORK))


def global_user_name(base: Path, name: bytes) -> dict:
    """The environment of a person whose global `user.name` is `name`,
    written as bytes: `GIT_CONFIG_GLOBAL` (git 2.32) stands in for
    `~/.gitconfig` for every git the run starts. Skipped where `git config
    user.name`, asked where `_elector` asks it, does not answer `name`: a
    `user.name` in this checkout's own config wins over the global one."""
    config = base / "gitconfig"
    config.write_bytes(b"[user]\n\tname = " + name + b"\n")
    extra = {"GIT_CONFIG_GLOBAL": str(config)}
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
    is the control: its `org/repo` is read, so the None is the byte's."""
    source = with_origin(make_source_repo(tmp_path / "Thing"), url)
    done = planned(tmp_path, source)
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
    base."""
    source = with_origin(make_source_repo(tmp_path / "Thing"), ASCII_URL)
    done = without_org(tmp_path, source)
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
