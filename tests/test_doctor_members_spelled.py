# SPDX-License-Identifier: Apache-2.0
"""`shape-doctor.py`'s `members` row spells what it quotes (#673).

THE DEFECT. The row's sentence about a clone beside the holder from another
remote quoted the project, the directory, the clone's `origin` and the url
the holder mounts the member from as they were read, and `Row` passes a
reason only through `ascii_text`, which keeps every ASCII control. A mount
url holding ESC printed `caf`, a raw ESC and `[31m`: a colour change in the
terminal. A CR would have sent the cursor back over the line.

WHAT IT DOES NOW. Every value the row quotes from `family.yaml`, the disk or
git goes through `repo_shape.spelled`, as `siblings.py::verify_sibling`
spells the same four in its `WRONG ORIGIN` finding: a control, NEL and a
bidirectional control print as the escape Python writes for them, and a
plain value prints byte for byte as before. `--json` keeps the raw values,
which `json.dumps` escapes.

THE MOUNT URL IS READ BY `submodule_config`, which splits a url at a CR or a
NEL (#668), so the mount url here holds ESC and U+202E BEFORE those two:
the row spells whatever url the doctor read, and that is asserted whole,
with the two escapes in it. The clone's `origin` is read whole and holds all
four.

THE FIXTURES ARE `test_shape_doctor`'s, imported rather than rebuilt.
"""

from __future__ import annotations

import subprocess

from pathlib import Path

import pytest

from conftest import git, run_script
from test_shape_doctor import (  # noqa: F401
    DOCTOR, FAMILY_MEMBER, commit_all, doctor, holder, member_beside,
    rows_of, standard,
)

#: The characters #673 names, each one a terminal acts on: ESC starts an
#: escape sequence, CR goes back to the start of the line, NEL ends it, and
#: U+202E reverses what follows. Each to the escape Python writes for it,
#: spelt out here rather than read back from `repo_shape.spelled`.
ESCAPES = {"\x1b": "\\x1b", "\r": "\\r", "\x85": "\\x85",
           "\u202e": "\\u202e"}

#: The two consoles: a stdout that can encode anything, and an ASCII one.
CONSOLES = [pytest.param({"PYTHONIOENCODING": "utf-8"}, id="utf-8"),
            pytest.param({"PYTHONIOENCODING": "ascii"}, id="ascii")]

#: What the row says after the two urls, whatever they hold.
NOT_COUNTED = ", so it is not counted as its working clone"


def escaped(text: str) -> str:
    """`text` with each of `ESCAPES` written as its escape."""
    return "".join(ESCAPES.get(char, char) for char in text)


def printed_row(stdout: str) -> str:
    """The `members` row's reason line of a printed report.

    Split at `\\n` alone, so a NEL or a U+2028 stays in the line it was
    printed on. `run_script` reads text, which turns a raw CR into a line
    break, so a CR printed raw cuts the row short instead, and the sentence
    it was in is then not found whole.
    """
    return next(line for line in stdout.split("\n")
                if line.split()[1:2] == ["members"])


def stranger_beside(standard: Path, holder: dict, tmp_path: Path,
                    mount: str, origin: str) -> tuple[Path, dict]:
    """A holder whose member is mounted from `mount`, beside a clone of the
    member whose `origin` is `origin`, and the member's `--json` entry.
    Neither is the url the harness mounted the member from.

    Both urls are set by git, which writes a value holding a CR in quotes
    and reads it back whole. The `.gitmodules` change is committed, so the
    working tree is clean, as a person's would be.
    """
    root, sibling = member_beside(holder, tmp_path)
    git("config", "-f", str(root / ".gitmodules"),
        f"submodule.members/{FAMILY_MEMBER}.url", mount, cwd=root)
    commit_all(root, "Mount the member from another directory")
    git("remote", "set-url", "origin", origin, cwd=sibling)
    # As bytes: a text read would turn the CR into a line break.
    read = subprocess.run(["git", "remote", "get-url", "origin"],
                          cwd=str(sibling), capture_output=True,
                          check=True).stdout.decode("utf-8")
    if read.rstrip("\n") != origin:
        pytest.skip(f"git reads the origin back as {read!r}, not {origin!r}")
    result = doctor(standard, root, "--json")
    assert "Traceback" not in result.stderr, result.stderr
    entry = rows_of(result)["members"]["detail"]["members"][0]
    assert entry["sibling"] == "wrong-origin", entry
    return root, entry


def remotes(holder: dict) -> str:
    """The directory the harness keeps its bare repositories in."""
    return (holder["base"] / "remotes").as_posix()


def controlled(holder: dict) -> tuple[str, str]:
    """`(a mount url, a stranger's origin)`, each holding the controls."""
    return (f"{remotes(holder)}/caf\x1b[31m\u202e\r\x85/{FAMILY_MEMBER}.git",
            f"{remotes(holder)}/fork\x1b[31m\r\x85\u202e/Someone/Fork.git")


@pytest.mark.parametrize("console", CONSOLES)
def test_the_row_prints_a_stranger_and_its_mount_url_spelled(
        standard, holder, tmp_path, console):
    """#673's table: each control the two urls hold is printed as its
    escape, never raw, on a UTF-8 stdout and on an ASCII one, and the run
    still reaches its verdict."""
    mount, origin = controlled(holder)
    root, entry = stranger_beside(standard, holder, tmp_path, mount, origin)
    text = run_script(standard / DOCTOR, "--root", str(root), env=console)
    assert "Traceback" not in text.stderr, text.stderr
    assert text.returncode == 0, text.stdout + text.stderr
    row = printed_row(text.stdout)
    assert [char for char in ESCAPES if char in row] == [], row
    assert (f"is a clone of {escaped(origin)}, not of "
            f"{escaped(entry['mounted_from'])}{NOT_COUNTED}") in row, row
    assert [escape for escape in ESCAPES.values()
            if escape not in row] == [], row
    assert "caf\\x1b[31m\\u202e" in row, row


def test_the_json_keeps_the_urls_raw(standard, holder, tmp_path):
    """`--json` is data: the origin is the one git holds, character for
    character, and the mount url holds the ESC and the U+202E as they are.
    `json.dumps` escapes them in the text it writes."""
    mount, origin = controlled(holder)
    _root, entry = stranger_beside(standard, holder, tmp_path, mount, origin)
    assert entry["other_origin"] == origin, entry
    assert entry["mounted_from"].startswith(
        f"{remotes(holder)}/caf\x1b[31m\u202e"), entry


def test_a_plain_url_prints_as_it_did(standard, holder, tmp_path):
    """And the other direction, so the tests above cannot pass by escaping
    everything: urls with nothing to spell are printed byte for byte."""
    mount = f"{remotes(holder)}/plain/{FAMILY_MEMBER}.git"
    origin = f"{remotes(holder)}/Someone/Fork.git"
    root, entry = stranger_beside(standard, holder, tmp_path, mount, origin)
    assert entry["mounted_from"] == mount, entry
    row = printed_row(doctor(standard, root).stdout)
    assert f"is a clone of {origin}, not of {mount}{NOT_COUNTED}" in row, row


def test_a_member_path_is_spelled_in_the_rows_finding(standard, holder,
                                                      tmp_path):
    """The rest of what the row quotes from `family.yaml` is spelled too:
    a member `path:` holding ESC names a mount that is not populated, and
    the finding names it with the escape, never the raw ESC."""
    root, _sibling = member_beside(holder, tmp_path)
    manifest = root / "family.yaml"
    before = f"    path: members/{FAMILY_MEMBER}\n"
    text = manifest.read_text(encoding="utf-8")
    assert text.count(before) == 1, text
    manifest.write_text(text.replace(
        before, f'    path: "members/{FAMILY_MEMBER}\\x1b[31m"\n'),
        encoding="utf-8")
    result = doctor(standard, root)
    assert "Traceback" not in result.stderr, result.stderr
    row = printed_row(result.stdout)
    assert "\x1b" not in row, row
    assert f"members/{FAMILY_MEMBER}\\x1b[31m: not populated" in row, row
