# SPDX-License-Identifier: Apache-2.0
"""Under `LC_ALL=C PYTHONUTF8=0`, `plan`, `check` and `execute` hand git and
gh the bytes a name or a url spells, as #527 made `execute` hand `git rm`
the bytes the tree holds (#653).

On POSIX `subprocess` encodes a `str` argument with the filesystem encoding,
which is the locale's codec when Python is not in UTF-8 mode, and under the
C locale that codec is ASCII. On main at a5245427 three places still handed
git or gh text, and each ended in a `UnicodeEncodeError` traceback, exit 1,
before any leg existed:

- `gh repo create --description`, whose em dash is the tool's own, so every
  `execute` against GitHub stopped there, an all-ASCII source included; and
  the `gh pr create --body` after it, the split's message, names the paths
  the split moved (L1-33);
- `plan`'s `git grep` for a spec directory or a code entry outside ASCII,
  so `plan` wrote no plan (L1-34);
- `_resolved`'s `git config` of a relative submodule url outside ASCII, or
  of a source remote outside ASCII, so `check` and `execute` died (L1-35).

Ruled 2026-10-12, for #527: pass git the exact bytes the tree holds, under
any locale; and 2026-10-16 (#457's triage, D4): this locale is in scope.

THE GITHUB RUNS ARE `tests/test_adopt_github_exits.py`'s, with nothing on a
network: its `gh` stand-in makes each repository a bare one, and a throwaway
global git config sends `https://github.com/` there. One line is added to
the stand-in: every call writes its arguments, NUL-separated, to a file of
its own, so the test reads the bytes gh was handed, not a spelling of them.

What `check` and `execute` SAY is compared with what they say in UTF-8 mode
(`LC_ALL=C PYTHONUTF8=1`), once the C locale's escapes (`\\xdc` for `Ü`)
are undone: the same report, about the same repositories. A C locale is a
POSIX idea, so every test skips on Windows and where the filesystem
encoding stays UTF-8 under it (`c_locale_or_skip`, #527's own).
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

import test_adopt_github_exits as on_github
from conftest import ADOPT, WINDOWS_SKIP, git, make_source_repo, run_script
from test_adopt_git_rm_bytes import (C_LOCALE, NORTHWIND, SPLIT_BRANCH,
                                     c_locale_or_skip, needs_filter_repo,
                                     tree_bytes)
from test_adopt_relative_submodule_url import (HTTPS_ORIGIN, RELATIVE,
                                               RELATIVE_ORIGIN, REMOTES,
                                               THING_REMOTE, VERIFIED, found,
                                               its_org, planned, source_with)

#: The same interpreter in UTF-8 mode under the same locale: what the C
#: locale's runs are compared with.
UTF8_MODE = {"LC_ALL": "C", "PYTHONUTF8": "1"}
ORG = "testorg"
#: A directory and a url outside ASCII: the source's or a remote's
#: directory, and a submodule url.
UMLAUT = "Ünter"
URL = "../Ünterlagen"
#: Where git resolves `../dependency` beside the source, or URL beside the
#: repositories `execute --local-remote-dir` makes.
SIBLING = "../dependency"
DEPENDENCY_DIR = "Ünterlagen"
#: A remote's name outside ASCII, which git takes as it takes `origin`.
REMOTE_NAME = "Ürsprung"
#: The line the stand-in `gh` gets, after its first one, to keep each call's
#: arguments as bytes: `printf` writes each argument as it was given.
RECORD_THE_ARGUMENTS = "printf '%s\\0' \"$@\" > \"$FAKE_GH_ROOT/argv.$$\"\n"
#: `gh repo create`'s description of a leg: the tool's own text, em dash
#: and all, which reaches gh as UTF-8.
DESCRIPTION = ("{project} \N{EM DASH} {role} leg, extracted from "
               "{org}/{project} with history")


def unescaped(line: str) -> str:
    """`line` as the C locale printed it, each character its stream could
    not encode written back from the `\\xdc`, `\\u00dc` or `\\U...` escape
    `backslashreplace` gave it."""
    return re.sub(r"\\x([0-9a-f]{2})|\\u([0-9a-f]{4})|\\U([0-9a-f]{8})",
                  lambda match: chr(int("".join(filter(None, match.groups())),
                                        16)), line)


def said(result: subprocess.CompletedProcess) -> list[str]:
    """Every FINDING and NOTE line a run printed, on either stream; a
    refusal of `execute` indents each FINDING it repeats."""
    lines = (result.stdout + result.stderr).splitlines()
    return [line.strip() for line in lines
            if line.lstrip().startswith(("FINDING ", "NOTE "))]


def assert_said_alike(c_locale, utf8_mode) -> None:
    """The C locale's run exits as the UTF-8 run does and prints the same
    findings and notes, once its escapes are undone, of which there is at
    least one; and it printed no traceback, which `said` would not show."""
    assert "Traceback" not in c_locale.stderr, c_locale.stderr
    assert c_locale.returncode == utf8_mode.returncode, (
        c_locale.stderr + c_locale.stdout)
    assert said(utf8_mode), utf8_mode.stderr + utf8_mode.stdout
    assert [unescaped(line) for line in said(c_locale)] == said(utf8_mode)


def in_the_locale(monkeypatch, locale: dict) -> None:
    """Every child this test starts runs in `locale`, whatever the locale
    of this process: the environment `c_locale_or_skip` gives, with
    `locale` over it."""
    env = c_locale_or_skip()
    for key in [key for key in os.environ if key not in env]:
        monkeypatch.delenv(key)
    for key, value in locale.items():
        monkeypatch.setenv(key, value)


# --- `execute` against GitHub (L1-33) ---------------------------------------


def called(github: Path) -> list[list[bytes]]:
    """Each `gh` call's arguments, as the bytes gh was handed."""
    return [path.read_bytes().split(b"\0")[:-1]
            for path in sorted(github.glob("argv.*"))]


def on_github_in_the_c_locale(monkeypatch, tmp_path: Path, tree: dict):
    """`test_adopt_github_exits.github_run` of `tree`, `plan` and `execute`
    both under the C locale, with the stand-in `gh` keeping each call's
    arguments; `(result, github)` as it returns them."""
    in_the_locale(monkeypatch, C_LOCALE)
    monkeypatch.setattr(on_github, "GH_SHIM", on_github.GH_SHIM.replace(
        "\n", "\n" + RECORD_THE_ARGUMENTS, 1))
    return on_github.github_run(tmp_path, "", tree=tree)


@needs_filter_repo
@WINDOWS_SKIP
def test_execute_on_github_hands_gh_repo_create_its_description_as_utf_8(
        monkeypatch, tmp_path):
    """L1-33. On a5245427 `execute` exited 1 with `UnicodeEncodeError` at
    the first `gh repo create`, for this all-ASCII source, before any
    repository existed. Now both legs are created and the adoption is
    verified, and gh was handed each description as its UTF-8 bytes,
    unchanged."""
    result, github = on_github_in_the_c_locale(monkeypatch, tmp_path,
                                               on_github.SOURCE_TREE)
    assert result.returncode == 0, result.stderr + result.stdout
    assert VERIFIED in result.stdout
    created = sorted(argv for argv in called(github)
                     if argv[:2] == [b"repo", b"create"])
    assert created == [
        [b"repo", b"create", f"{ORG}/{NORTHWIND}-{role}".encode(),
         b"--private", b"--description",
         DESCRIPTION.format(project=NORTHWIND, role=role, org=ORG).encode()]
        for role in ("code", "spec")]


@needs_filter_repo
@WINDOWS_SKIP
def test_execute_on_github_hands_gh_pr_create_the_split_message_as_utf_8(
        monkeypatch, tmp_path):
    """L1-33's second half. `Überblick.md` moves to the spec leg, so the
    split's message names it, and that message is the pull request's body.
    Handed to gh as text, it raised `UnicodeEncodeError` after both legs and
    the split were pushed, and `execute` exited 2 with the pull request to
    open by hand. Now the pull request is opened, and its body is the split
    commit's message byte for byte, the name as the tree holds it."""
    moved = "Überblick.md"
    result, github = on_github_in_the_c_locale(
        monkeypatch, tmp_path, {**on_github.SOURCE_TREE, moved: "# Ü\n"})
    assert result.returncode == 0, result.stderr + result.stdout
    assert VERIFIED in result.stdout
    [opened] = [argv for argv in called(github)
                if argv[:2] == [b"pr", b"create"]]
    body = opened[opened.index(b"--body") + 1]
    commit = subprocess.run(["git", "cat-file", "commit", SPLIT_BRANCH],
                            cwd=str(github / ORG / f"{NORTHWIND}.git"),
                            capture_output=True, check=True).stdout
    assert body == commit.split(b"\n\n", 1)[1]
    assert b"\n  " + tree_bytes(moved) + b"\n" in body


# --- `plan`'s `git grep` (L1-34) --------------------------------------------


#: A spec directory outside ASCII, and the two code paths outside ASCII that
#: name it: a file in a code directory, and a code file.
SPEC_DIR = "Ärger"
IN_A_CODE_DIR = "Werkzeuge-Ü/run.py"
A_CODE_FILE = "Übung.py"
#: Their source, where `src/app.py` names nothing.
NAMED_BY_CODE = {
    "README.md": "# Northwind\n",
    "src/app.py": "VALUE = 1\n",
    f"{SPEC_DIR}/a.md": "a\n",
    f"{SPEC_DIR}/b.md": "b\n",
    IN_A_CODE_DIR: f'open("{SPEC_DIR}/a.md")\n',
    "Werkzeuge-Ü/util.py": "X = 1\n",
    A_CODE_FILE: f'PATH = "{SPEC_DIR}/b.md"\n',
}


def test_plan_greps_for_a_spec_directory_outside_ascii(tmp_path):
    """L1-34. On a5245427 `plan` died with `UnicodeEncodeError` at the
    `git grep` for `Ärger/` in the code paths, and wrote no plan. Now the
    plan it writes is the one UTF-8 mode writes, byte for byte, and its
    follow-ups name each code path that names the spec directory: git found
    both."""
    env = c_locale_or_skip()
    source = make_source_repo(tmp_path / NORTHWIND, NAMED_BY_CODE, edits=())

    def written(locale: dict) -> bytes:
        plan = tmp_path / f"plan-{locale['PYTHONUTF8']}" / "adoption-plan.yaml"
        plan.parent.mkdir()
        result = run_script(ADOPT, "plan", "--source", str(source),
                            "--project", NORTHWIND, "--org", ORG,
                            "--elected-by", "Test Human", "--elected-on",
                            "2026-09-02", "--out", str(plan),
                            env={**env, **locale})
        assert result.returncode == 0, result.stderr + result.stdout
        return plan.read_bytes()

    text = written(C_LOCALE)
    assert text == written(UTF8_MODE)
    across = [line for line in text.decode().splitlines()
              if f"names `{SPEC_DIR}/`" in line]
    assert sorted(path for line in across
                  for path in (IN_A_CODE_DIR, A_CODE_FILE)
                  if path in line) == sorted((IN_A_CODE_DIR, A_CODE_FILE))


# --- `check` and `execute`, a relative submodule url (L1-35) ----------------


def checked(plan: Path, locale: dict) -> subprocess.CompletedProcess:
    return run_script(ADOPT, "check", "--plan", str(plan),
                      env={**c_locale_or_skip(), **locale})


def url_outside_ascii(base: Path) -> tuple[Path, Path, str]:
    """The issue's: `../Ünterlagen`, from a source on GitHub."""
    return source_with(base, URL, HTTPS_ORIGIN), base, ORG


def origin_outside_ascii(base: Path) -> tuple[Path, Path, str]:
    """A source whose remote is a directory outside ASCII: git's url, which
    `_resolved` hands `git config` as the base."""
    origin = str(base / UMLAUT / ORG / THING_REMOTE)
    return source_with(base, SIBLING, origin), base, its_org(origin)


def remote_name_outside_ascii(base: Path) -> tuple[Path, Path, str]:
    """A source whose branch tracks a remote NAMED outside ASCII, on this
    disk: `_default_remote` asks git for that remote's url by its name."""
    origin = str(base / ORG / THING_REMOTE)
    source = source_with(base, SIBLING, origin)
    git("remote", "rename", "origin", REMOTE_NAME, cwd=source)
    git("config", "branch.main.remote", REMOTE_NAME, cwd=source)
    return source, base, its_org(origin)


def own_directory_outside_ascii(base: Path) -> tuple[Path, Path, str]:
    """A source with no remote, in a directory outside ASCII: git resolves
    against that directory, as the disk spells it."""
    inside = base / UMLAUT
    return source_with(inside, SIBLING), inside, ORG


def working_tree_outside_ascii(base: Path) -> tuple[Path, Path, str]:
    """A source whose remote is relative to its working tree, which is in a
    directory outside ASCII: git's answer is joined to that working tree."""
    inside = base / UMLAUT
    return (source_with(inside, SIBLING, RELATIVE_ORIGIN), inside,
            its_org(RELATIVE_ORIGIN))


@pytest.mark.parametrize("layout", [
    url_outside_ascii, origin_outside_ascii, remote_name_outside_ascii,
    own_directory_outside_ascii, working_tree_outside_ascii,
], ids=["url", "origin", "remote-name", "own-directory", "working-tree"])
def test_check_resolves_a_relative_url_as_utf_8_mode_does(monkeypatch,
                                                          tmp_path, layout):
    """L1-35. On a5245427 `check` died with `UnicodeEncodeError` where
    `_resolved` handed `git config` the url (`url`) or the source's remote
    (`origin`) as text, and where `_default_remote` asked `git config` for
    the url of a remote by its name (`remote-name`). Now `plan` and `check`
    under the C locale end as they do in UTF-8 mode, and say the same of
    the same repositories: `plan ok` and the NOTEs for `url`, the finding
    for the others. A directory read from the disk (`own-directory`,
    `working-tree`) is named as UTF-8 mode names it, `Ü` where it said
    `\\udcc3\\udc9c` (`_git_spelling`). Each locale writes its own plan,
    because one locale cannot read the source directory another wrote: a
    plan written in UTF-8 mode records `Ü`, which a path under the C
    locale cannot hold."""
    c_locale_or_skip()
    source, base, org = layout(tmp_path)
    runs = []
    for locale in (C_LOCALE, UTF8_MODE):
        with monkeypatch.context() as here:
            in_the_locale(here, locale)
            plan = planned(source, base, org,
                           name=f"plan-{locale['PYTHONUTF8']}")
        runs.append(checked(plan, locale))
    assert_said_alike(*runs)


@needs_filter_repo
def test_execute_resolves_and_asks_a_relative_url_outside_ascii(tmp_path):
    """L1-35, `execute --local-remote-dir`, in #190's layout: the source's
    remote is `../remotes/Thing.git`, and `../Ünterlagen` names
    `remotes/Ünterlagen` from the source and from the code leg's remote
    beside it. On a5245427 `execute` died in `_resolved`; past it, in
    `same_as`, which asks the disk whether two spellings are one directory,
    and in #418's `git ls-remote` of the url. Now `check` finds what UTF-8
    mode finds (GitHub's leg resolves it elsewhere), `execute` with the
    legs elsewhere, in a directory outside ASCII, refuses with UTF-8 mode's
    words, and with the legs beside the dependency it adopts and verifies."""
    c_locale_or_skip()
    remotes = tmp_path / REMOTES
    source = source_with(tmp_path, URL, RELATIVE_ORIGIN,
                         remotes / DEPENDENCY_DIR)
    plan = planned(source, tmp_path, its_org(RELATIVE_ORIGIN))
    result = checked(plan, C_LOCALE)
    assert [code for code, _ in found(result.stderr)] == [RELATIVE]

    def executed(legs: Path, locale: dict, work: str):
        return run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                          "--local-remote-dir", str(legs), "--work-dir",
                          str(tmp_path / work),
                          env={**c_locale_or_skip(), **locale})

    elsewhere = tmp_path / UMLAUT
    refused = executed(elsewhere, C_LOCALE, "work-c")
    assert refused.returncode != 0, refused.stdout
    assert_said_alike(refused, executed(elsewhere, UTF8_MODE, "work-utf-8"))
    adopted = executed(remotes, C_LOCALE, "work")
    assert adopted.returncode == 0, adopted.stderr + adopted.stdout
    assert VERIFIED in adopted.stdout
