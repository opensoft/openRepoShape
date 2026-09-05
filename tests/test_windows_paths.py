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
