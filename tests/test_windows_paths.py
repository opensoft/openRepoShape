# SPDX-License-Identifier: Apache-2.0
"""The three ways a Windows path used to break a tool that is not Windows-aware.

EVERY TEST HERE RUNS ON LINUX and asserts the Windows answer, because that is
the only way these stay honest between the rare Windows CI runs: each one
feeds a `D:\\...` string, or a `PureWindowsPath`, to a function that has no
idea which platform it is on and asserts what it must return. The three are
the three that the first `windows-latest` run found:

  * a shape-pin row's `path:` built with `str()` of a relative Path, which is
    `scripts\\bootstrap.py` there and matches no row in a file whose rows are
    POSIX — so every copy in a subdirectory read as `unmapped`;
  * a filesystem path refused by the guard that keeps a value off a `git`
    command line, because a drive colon and a backslash are not in the
    alphabet a branch name is spelled with;
  * a backslash eaten by the YAML reader's escape handling, which turned the
    `\\t` of a directory named `t` into a TAB and made a plan's own `source:`
    a path that does not exist.

A FOURTH joined them on 2026-09-09 (PR #79's `windows-latest` run): a
relative submodule url resolved against the holder's remote by dropping one
`/`-separated component per `..`, where the remote was
`D:\\a\\_temp\\t\\family0\\remotes\\InkRouter.git` and had no `/` in it at all — so
nothing was dropped, the name was appended to the whole string, and `git
clone` refused `…\\InkRouter.git/IRRS.git`. Same shape as the three above: a
separator assumed, on the one platform that spells it differently.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from conftest import REPO

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import (  # noqa: E402
    SAFE_ARG_RE, SAFE_PATH_RE, Refusal, checked_value, load_yaml,
)
from shape_materialize import root_key  # noqa: E402

#: The runner's own temporary directory in the first `windows-latest` run, and
#: the exact value that was refused. Kept verbatim so the test names the case
#: rather than a paraphrase of it.
WINDOWS_REMOTE = r"D:\a\_temp\t\shape0\remotes\Atlas-spec.git"


@pytest.fixture(scope="module")
def entry():
    """`setup-project.py` as a module, for its landing rule.

    The NATIVE WINDOWS entry point, which is why its path arithmetic is
    asked the Windows question here rather than left to the rare
    `windows-latest` run: `--family` adds a level to where the clone lands
    (#76), and a level added with a POSIX assumption in it is a project
    cloned somewhere nobody named.
    """
    spec = importlib.util.spec_from_file_location(
        "setup_project_landing", REPO / "setup-project.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def siblings():
    """The HOLDER's `scripts/siblings.py`, for its url arithmetic.

    Loaded by path, under its own module name, with the family's
    `bootstrap.py` pre-registered as `bootstrap` — that import is the one
    `siblings.py` makes for the credential resolution and the member rows, and
    in a materialized holder the two files sit side by side. `sys.path` and
    `sys.modules` are put back afterwards, so nothing here leaves a module
    named `bootstrap` importable for the rest of the session.
    """
    scripts = REPO / "templates" / "family-root" / "scripts"
    saved_path, saved_module = list(sys.path), sys.modules.get("bootstrap")
    try:
        spec = importlib.util.spec_from_file_location(
            "family_root_bootstrap", scripts / "bootstrap.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules["bootstrap"] = module
        spec = importlib.util.spec_from_file_location(
            "family_root_siblings", scripts / "siblings.py")
        loaded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loaded)
        yield loaded
    finally:
        sys.path[:] = saved_path
        if saved_module is None:
            sys.modules.pop("bootstrap", None)
        else:
            sys.modules["bootstrap"] = saved_module


@pytest.fixture(scope="module")
def adopt():
    """`adopt-project.py` as a module, for its YAML writer."""
    spec = importlib.util.spec_from_file_location(
        "adopt_project_entry", REPO / "adopt-project.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# The pin row's key
# ---------------------------------------------------------------------------


def test_a_shape_pin_row_is_keyed_in_posix_on_a_windows_path():
    """The regression that reported an unchanged project as 45 tests of drift.

    `PureWindowsPath` is what makes this runnable here: it splits and joins
    the way Windows does on any platform, so the assertion is the one the
    runner makes, not a Linux stand-in for it.
    """
    root = PureWindowsPath(r"D:\a\_temp\t\Atlas")
    assert root_key(root / "scripts" / "bootstrap.py", root) == \
        "scripts/bootstrap.py"
    assert root_key(root / ".github" / "workflows" / "validate.yml", root) == \
        ".github/workflows/validate.yml"


def test_a_shape_pin_row_key_is_unchanged_where_it_was_already_right():
    root = PurePosixPath("/tmp/t/Atlas")
    assert root_key(root / "contracts" / "repository-naming.yaml", root) == \
        "contracts/repository-naming.yaml"
    assert root_key(root / "Makefile", root) == "Makefile"


def test_every_row_a_scaffolded_pin_carries_is_a_forward_slash_key(project):
    """The contract, over a pin the real scaffold wrote.

    Trivially true here and the whole question on Windows: a row's `path:` is
    what `update-shape.py` looks a copy up by, and a row it cannot look up is
    a file it reports as drift and refuses to re-sync. Every failing row in
    the first `windows-latest` run was one with a directory in it.
    """
    rows = load_yaml(project / "contracts" / "shape-pin.yaml")["files"]
    assert rows, "the scaffolded project pins no files at all"
    assert any("/" in row["path"] for row in rows), (
        "no pinned path has a directory in it, so this asserts nothing")
    for row in rows:
        assert "\\" not in row["path"], (
            f"{row['path']!r} is a key no lookup in the copy tables can find")
        assert (project / row["path"]).is_file(), (
            f"{row['path']!r} does not resolve to a file in the root")


# ---------------------------------------------------------------------------
# Where --family lands the clone
# ---------------------------------------------------------------------------


def test_the_family_landing_adds_a_level_the_windows_way(entry):
    """`<into>/<Family>/<Project>`, spelled with backslashes on Windows.

    `family_landing` takes and returns a PURE path and touches no
    filesystem, which is what lets the Windows answer be asserted from
    Linux - the same trick `root_key` above is held to.
    """
    parent = PureWindowsPath(r"D:\a\_temp\t\work")
    assert entry.family_landing(parent, "InkRouter") == \
        PureWindowsPath(r"D:\a\_temp\t\work\InkRouter")
    assert entry.family_landing(parent, "InkRouter") / "IRTS" == \
        PureWindowsPath(r"D:\a\_temp\t\work\InkRouter\IRTS")


def test_the_family_landing_does_not_nest_a_second_level(entry):
    r"""Standing in `D:\...\InkRouter` already: the folder is the answer.

    `PureWindowsPath.name` is what decides it, so a drive letter, a UNC
    prefix and a trailing separator are the pure path class's problem and
    not this rule's.
    """
    folder = PureWindowsPath(r"D:\a\_temp\t\work\InkRouter")
    assert entry.family_landing(folder, "InkRouter") == folder
    assert entry.family_landing(PureWindowsPath("\\\\server\\share\\InkRouter"),
                                "InkRouter") == \
        PureWindowsPath("\\\\server\\share\\InkRouter")


def test_no_family_leaves_the_landing_exactly_where_it_was(entry):
    """The overwhelmingly commonest run: no flag, no level, no change -
    and the POSIX side of the same function, because the rule is one."""
    for parent in (PureWindowsPath(r"D:\a\_temp\t\work"),
                   PurePosixPath("/tmp/t/work")):
        assert entry.family_landing(parent, "") == parent


# ---------------------------------------------------------------------------
# A relative submodule url, against a remote spelled the Windows way
# ---------------------------------------------------------------------------

#: The runner's own remote in the `windows-latest` run of PR #79, verbatim,
#: and the `..` that was resolved against it. `\` throughout and not one `/`:
#: that is the whole of the bug, so the fixture is the string rather than a
#: paraphrase of it.
WINDOWS_HOLDER_REMOTE = r"D:\a\_temp\t\family0\remotes\InkRouter.git"


@pytest.mark.parametrize("base,expected", [
    # THE FAILURE ITSELF. The result comes back in the spelling the remote
    # used — git on Windows accepts either, and a human comparing this
    # against `git remote -v` or `.gitmodules` should not have to translate.
    (WINDOWS_HOLDER_REMOTE, r"D:\a\_temp\t\family0\remotes\IRRS.git"),
    # A Windows path a person typed with forward slashes: git accepts it, so
    # it comes back the way it went in.
    ("D:/x/remotes/InkRouter.git", "D:/x/remotes/IRRS.git"),
    # A UNC share, where the leading `\\` must survive the walk.
    (r"\\server\share\remotes\InkRouter.git",
     r"\\server\share\remotes\IRRS.git"),
    # POSIX, which is what every green run had been asserting.
    ("/srv/mirrors/InkRouter.git", "/srv/mirrors/IRRS.git"),
    # A URL keeps git's own rule: one component of the URL dropped.
    ("https://host/org/InkRouter.git", "https://host/org/IRRS.git"),
    ("file:///srv/mirrors/InkRouter.git", "file:///srv/mirrors/IRRS.git"),
    ("ssh://git@host/org/InkRouter.git", "ssh://git@host/org/IRRS.git"),
    # The scp spelling, whose colon is NOT a drive letter: the separator is
    # still `/` and the host is not a component a `..` may eat.
    ("git@host:org/InkRouter.git", "git@host:org/IRRS.git"),
])
def test_a_relative_member_url_resolves_against_any_remote_spelling(
        siblings, base, expected):
    r"""`../IRRS.git` against the holder's own remote, on every spelling.

    `join_relative` is PURE STRING ARITHMETIC over the two strings, which is
    what lets the Windows answer be asserted from Linux — the same trick
    `root_key` and `family_landing` above are held to. The end-to-end test in
    `tests/test_family.py` is what caught this on the runner; this is what
    keeps it caught between Windows runs.
    """
    assert siblings.join_relative(base, "../IRRS.git") == expected


def test_a_windows_remote_is_a_path_and_an_scp_url_is_not(siblings):
    r"""Only a FILESYSTEM PATH may be walked with a backslash in it.

    `D:\...` is a path whose colon is a drive letter; `git@host:org/Repo.git`
    and `host:path/Repo.git` are urls in git's scp spelling, and a url's
    separator is `/` on every platform. Getting this backwards would rewrite
    an scp url's slashes into backslashes on a Windows workstation.
    """
    assert siblings.base_is_a_path(WINDOWS_HOLDER_REMOTE)
    assert siblings.base_is_a_path("D:/x/remotes/InkRouter.git")
    assert siblings.base_is_a_path("/srv/mirrors/InkRouter.git")
    assert not siblings.base_is_a_path("git@host:org/InkRouter.git")
    assert not siblings.base_is_a_path("host:path/InkRouter.git")
    assert not siblings.base_is_a_path("https://host/org/InkRouter.git")
    assert not siblings.base_is_a_path("file:///srv/mirrors/InkRouter.git")


@pytest.mark.parametrize("base,url,expected", [
    # A drive is a component of its own, and is the one colon that is not scp
    # syntax: `D:` is also what a one-letter SCHEME looks like.
    (r"D:\InkRouter.git", "../IRRS.git", r"D:\IRRS.git"),
    # The parent of a repository at the POSIX root is the root.
    ("/InkRouter.git", "../IRRS.git", "/IRRS.git"),
    # `..` TOO MANY CONSUMES NOTHING: not the scheme, not the scp host.
    ("https://host/InkRouter.git", "../../IRRS.git", "https://host/IRRS.git"),
    ("git@host:InkRouter.git", "../IRRS.git",
     "git@host:InkRouter.git/IRRS.git"),
    # Several levels, and a `./` that means this directory.
    ("/srv/a/b/InkRouter.git", "../../mirrors/IRRS.git",
     "/srv/a/mirrors/IRRS.git"),
    (r"D:\a\remotes\InkRouter.git", "./sub/IRRS.git",
     r"D:\a\remotes\InkRouter.git\sub\IRRS.git"),
])
def test_the_walk_stops_where_there_is_nothing_left_to_consume(
        siblings, base, url, expected):
    """The edges of the same arithmetic, each one a shape a hand-mounted
    member can carry. A url with a `..` too many is wrong wherever it is
    read; what this must not do is invent `https:/` out of a scheme."""
    assert siblings.join_relative(base, url) == expected


def test_an_absolute_member_url_is_returned_untouched(siblings):
    """Only `./` and `../` are relative. Everything `family.py add` writes —
    every url in every family this standard has made — goes through
    unchanged, and without asking git anything: the guard is the first line
    of `resolve_relative`, which is why the root passed here does not exist.
    """
    for url in (WINDOWS_HOLDER_REMOTE, "https://github.com/InkRouter/IRRS.git",
                "git@github.com:InkRouter/IRRS.git", "/srv/mirrors/IRRS.git"):
        assert siblings.resolve_relative(url, Path("/nonexistent")) == url


# ---------------------------------------------------------------------------
# The guard on a value that becomes a command argument
# ---------------------------------------------------------------------------


def test_a_windows_absolute_path_is_a_value_a_command_may_carry():
    assert checked_value("--local-remote-dir", WINDOWS_REMOTE,
                         SAFE_PATH_RE) == WINDOWS_REMOTE
    assert checked_value("--local-remote-dir", r"C:\Users\Jane Doe\remotes",
                         SAFE_PATH_RE) == r"C:\Users\Jane Doe\remotes"
    assert checked_value("--local-remote-dir", "/tmp/t/remotes",
                         SAFE_PATH_RE) == "/tmp/t/remotes"


@pytest.mark.parametrize("value", [
    "-" + WINDOWS_REMOTE,           # git would read it as its own option
    "--upload-pack=touch pwned",
    "   ",                          # a value that is only whitespace
    "D:\\a\\\nremotes",             # a control character
    "D:\\a\\re\x00motes",
    "host:path/to/repo",            # scp syntax is not a drive letter
])
def test_a_path_that_is_not_one_is_still_refused(value):
    with pytest.raises(Refusal) as raised:
        checked_value("--local-remote-dir", value, SAFE_PATH_RE)
    assert raised.value.code == "unsafe-value"


def test_the_narrow_alphabet_stays_narrow():
    """Widening was for PATHS ONLY.

    A branch, a repository name and a commit are still spelled without a
    backslash or a colon, and the flags that carry those still refuse one.
    """
    assert not SAFE_ARG_RE.fullmatch(WINDOWS_REMOTE)
    with pytest.raises(Refusal):
        checked_value("--tracking-branch", "main\\evil")


# ---------------------------------------------------------------------------
# The YAML round trip
# ---------------------------------------------------------------------------


def test_a_windows_path_survives_the_plan_it_was_written_into(adopt, tmp_path):
    """The writer and the reader, on the value that broke seven adopt tests.

    `D:\\a\\_temp\\t\\...` was written correctly and read back with the `t`
    turned into a TAB, so `adopt-project.py check` refused its own plan with
    `source-unresolvable`.
    """
    source = r"D:\a\_temp\t\test_check_passes_once_every_q0\Thing"
    plan = tmp_path / "plan.yaml"
    lines: list[str] = []
    adopt.emit(lines, "source", source)
    plan.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert load_yaml(plan)["source"] == source


@pytest.mark.parametrize("written,read_back", [
    (r'"D:\\a\\_temp\\t"', "D:\\a\\_temp\\t"),
    (r'"a\\nb"', "a\\nb"),          # an escaped backslash, then a letter n
    (r'"a\nb"', "a\nb"),            # a newline
    (r'"a\\\\b"', "a\\\\b"),        # two backslashes
    (r'"say \"hi\""', 'say "hi"'),
    (r'"a\qb"', "a\\qb"),           # not an escape; the backslash survives
])
def test_a_double_quoted_scalar_resolves_one_escape_at_a_time(
        tmp_path, written, read_back):
    path = tmp_path / "one.yaml"
    path.write_text(f"value: {written}\n", encoding="utf-8")
    assert load_yaml(path)["value"] == read_back


def test_a_drive_letter_source_is_a_path_and_never_an_org_repo(adopt):
    """`D:/work/Thing` carries a `/` and is still not `owner/repo`.

    Without this it would reach `gh repo clone` as an owner named `D:`, and
    the refusal a human needs to read is that the path is not there.
    """
    assert adopt.WINDOWS_ABSOLUTE_RE.match(r"D:\work\Thing")
    assert adopt.WINDOWS_ABSOLUTE_RE.match("D:/work/Thing")
    assert not adopt.WINDOWS_ABSOLUTE_RE.match("testorg/Thing")
    with pytest.raises(Refusal) as raised:
        adopt.Source.open("D:/work/Thing", Path("/nonexistent"))
    assert raised.value.code == "source-unresolvable"
