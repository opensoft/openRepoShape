# SPDX-License-Identifier: Apache-2.0
"""A workflow file that cannot be read is REFUSED BY NAME, not a traceback (#359).

`scripts/validate-pins.py` reads every `.yml` and `.yaml` file under
`.github/workflows/` to find the `@<sha>` references that name a leg. That read
went around `load_yaml`, so a workflow that was not UTF-8 -- a Latin-1
`# café` comment, a UTF-16 file with a byte-order mark -- raised
`UnicodeDecodeError`. It is a `ValueError`, `main()` caught `Refusal` alone,
and the run ended in a Python traceback with exit 1: the code this validator
uses for a FINDING, with no line naming the file, where a pin that is not
UTF-8 is a clean `REFUSED yaml-unreadable`, exit 2. A file this user cannot
open (`PermissionError`) was the same unguarded line.

The script is a template copy that every project carries (it is digest-pinned
in the project's own `contracts/shape-pin.yaml`), so these cases run the copy
a real scaffold wrote, over a committed tree.

The files are written with `write_bytes`: the point is the bytes, and
`write_text` would re-encode them, and on Windows rewrite their line endings.

NOTHING HERE REACHES A NETWORK. The scaffold uses `--local-remote-dir`, and no
case asks for a neutral-product pin.
"""

from __future__ import annotations

import json
import os
import stat

import pytest

from conftest import ORG, PROJECT, REPO, git, run_script

DOCTOR = REPO / "shape-doctor.py"
WORKFLOWS = ".github/workflows"
OTHER_SHA = "0123456789abcdef0123456789abcdef01234567"

CANNOT_RUN_AS_ROOT = pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="a mode-000 file is read by root, and Windows modes do not refuse "
           "a read")


def validate(root):
    return run_script(root / "scripts" / "validate-pins.py", cwd=root)


def leg_workflow(root, sha: str | None = None) -> bytes:
    """A workflow naming the spec leg at its pinned commit (or at `sha`): the
    file the lockstep rule exists for, so a skipped one could hide a stale
    reference. UTF-8, with LF line endings, whatever the host."""
    pinned = sha or git("rev-parse", "HEAD:spec", cwd=root).stdout.strip()
    return (f"on: [pull_request]\njobs:\n  s:\n"
            f"    uses: {ORG}/{PROJECT}-spec/.github/workflows/x.yml@{pinned}\n"
            ).encode("utf-8")


def commit_bytes(root, rel: str, data: bytes, message: str) -> None:
    """Write `rel` as exactly `data` and commit it, as in the issue: the file
    is wrong in the repository, not only in a working tree."""
    target = root / rel
    target.write_bytes(data)
    git("add", "--", rel, cwd=root)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
        "-m", message, "--", rel, cwd=root)


def not_utf8_line(rel: str, data: bytes) -> str:
    """`<rel>: not UTF-8 at byte N (<reason>)`, with N and the reason asked of
    Python's own decoder and not typed in here."""
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return f"{rel}: not UTF-8 at byte {exc.start} ({exc.reason})"
    raise AssertionError(f"fixture drift: {rel} is UTF-8")


def refusal_lines(result) -> list[str]:
    """The files the refusal names, one per line, as printed: the first
    follows the id on the `REFUSED` line, and the rest follow it."""
    return [line.replace("REFUSED workflow-unreadable: ", "", 1)
            for line in result.stderr.splitlines()
            if ": not UTF-8 at byte " in line or ": cannot be read (" in line]


def assert_refused_by_name(result, root, *names_and_lines: str) -> None:
    """One `workflow-unreadable` refusal, exit 2, no traceback, naming each
    file relative to the root and never by its absolute path."""
    assert "Traceback" not in result.stderr, result.stderr
    assert "UnicodeDecodeError" not in result.stderr, result.stderr
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.count("REFUSED ") == 1, result.stderr
    assert result.stderr.startswith("REFUSED workflow-unreadable: "), \
        result.stderr
    assert "pins ok" not in result.stdout
    assert refusal_lines(result) == list(names_and_lines), result.stderr
    assert str(root) not in result.stderr, \
        "the files are named relative to the root, never by absolute path"
    assert f"{len(names_and_lines)} workflow file(s)" in result.stderr


# --- the refusal ------------------------------------------------------------

LATIN_1 = "legs.yml", lambda root: leg_workflow(root) + b"# caf\xe9\n"
UTF_16 = "other.yml", lambda root: "on: [push]\n".encode("utf-16")


@pytest.mark.parametrize("name, build", [
    pytest.param(*LATIN_1, id="latin-1-comment-in-the-file-naming-the-leg"),
    pytest.param(*UTF_16, id="utf-16-bom-in-a-file-naming-no-leg"),
])
def test_a_workflow_that_is_not_utf8_is_refused_by_name(project, name, build):
    """The first two rows of the issue: a committed Latin-1 comment, and a
    UTF-16 file that names no leg and still stopped the run, because the file
    is opened before it is known to hold a reference."""
    data = build(project)
    commit_bytes(project, f"{WORKFLOWS}/{name}", data, f"workflow {name}")
    result = validate(project)
    assert_refused_by_name(result, project,
                           not_utf8_line(f"{WORKFLOWS}/{name}", data))
    # The remedy the operator can act on.
    assert "re-save the file as UTF-8" in result.stderr, result.stderr
    assert "needs converting, not editing" in result.stderr, result.stderr
    assert "run the same command again" in result.stderr, result.stderr


def test_every_workflow_that_is_not_utf8_is_named_in_the_one_refusal(project):
    """Row (c): two files, one run. `.yaml` is read as `.yml` is, and the files
    that ARE readable -- the scaffold's `validate.yml` and a good `ok.yml` --
    are not named."""
    latin = leg_workflow(project) + b"# caf\xe9\n"
    utf16 = "on: [push]\n".encode("utf-16")
    commit_bytes(project, f"{WORKFLOWS}/ok.yml", leg_workflow(project), "ok")
    commit_bytes(project, f"{WORKFLOWS}/legs.yml", latin, "latin-1")
    commit_bytes(project, f"{WORKFLOWS}/other.yaml", utf16, "utf-16")
    result = validate(project)
    assert_refused_by_name(
        result, project,
        not_utf8_line(f"{WORKFLOWS}/legs.yml", latin),
        not_utf8_line(f"{WORKFLOWS}/other.yaml", utf16))
    assert "validate.yml" not in result.stderr, result.stderr
    assert "ok.yml" not in result.stderr, result.stderr


def test_a_workflow_is_refused_and_neither_skipped_nor_read_lossily(project):
    """THE REFUSAL IS THE POINT. The file names the spec leg at a commit that
    is NOT the gitlink, which is exactly what this gate exists to find. Skipped,
    the run would say `pins ok`; read with `errors="replace"`, it would report
    `pin-workflow-ref-mismatch` and exit 1 over a file the project's other
    readers refuse. Neither: the question cannot be asked, so it is refused."""
    data = leg_workflow(project, OTHER_SHA) + b"# caf\xe9\n"
    commit_bytes(project, f"{WORKFLOWS}/legs.yml", data, "stale and latin-1")
    result = validate(project)
    assert_refused_by_name(result, project,
                           not_utf8_line(f"{WORKFLOWS}/legs.yml", data))
    assert "pin-workflow-ref-mismatch" not in result.stderr, result.stderr


@CANNOT_RUN_AS_ROOT
def test_a_workflow_this_user_cannot_open_is_refused_by_name(project):
    """The last row of the issue: not an encoding failure but the same
    unguarded read -- a `PermissionError` traceback. The refusal says what the
    operating system said, and its remedy is access, not a re-save."""
    target = project / WORKFLOWS / "legs.yml"
    commit_bytes(project, f"{WORKFLOWS}/legs.yml", leg_workflow(project),
                 "legs")
    target.chmod(0)
    try:
        result = validate(project)
    finally:
        target.chmod(stat.S_IREAD | stat.S_IWRITE)
    assert "Traceback" not in result.stderr, result.stderr
    assert "PermissionError" not in result.stderr, result.stderr
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(
        f"REFUSED workflow-unreadable: {WORKFLOWS}/legs.yml: cannot be read "
        "("), result.stderr
    assert str(project) not in result.stderr, result.stderr
    assert "restore read access" in result.stderr, result.stderr
    assert "re-save" not in result.stderr, result.stderr


def test_the_doctors_pins_row_names_the_file(project):
    """`shape-doctor.py` quotes the first `REFUSED` line of the project's own
    validator in its `pins` row, so the file's name reaches a reader who never
    runs the validator: before, the row quoted the last line of a traceback."""
    data = leg_workflow(project) + b"# caf\xe9\n"
    commit_bytes(project, f"{WORKFLOWS}/legs.yml", data, "latin-1")
    result = run_script(DOCTOR, "--root", str(project), "--json")
    assert "Traceback" not in result.stderr, result.stderr
    row = {r["id"]: r for r in json.loads(result.stdout)["rows"]}["pins"]
    assert row["status"] == "FINDING", row
    assert row["detail"]["exit"] == 2, row
    assert "refuses (exit 2)" in row["reason"], row["reason"]
    assert ("REFUSED workflow-unreadable: "
            + not_utf8_line(f"{WORKFLOWS}/legs.yml", data)) in row["reason"], \
        row["reason"]
    assert "UnicodeDecodeError" not in row["reason"], row["reason"]


# --- controls: what must not change -----------------------------------------

def test_a_pin_that_is_not_utf8_is_still_yaml_unreadable(project):
    """Row (d): the refusal the workflow's one is modelled on, unchanged. Its
    path is the absolute one `load_yaml` has always printed; the workflow
    refusal is relative to the root, as the issue asks."""
    pin = project / "contracts" / "spec-pin.yaml"
    commit_bytes(project, "contracts/spec-pin.yaml",
                 pin.read_bytes() + b"# caf\xe9\n", "latin-1 in the pin")
    result = validate(project)
    assert "Traceback" not in result.stderr, result.stderr
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED yaml-unreadable: " in result.stderr, result.stderr
    assert "spec-pin.yaml: not UTF-8 at byte " in result.stderr, result.stderr
    assert "workflow-unreadable" not in result.stderr, result.stderr


@pytest.mark.parametrize("name, build", [
    pytest.param("legs.yml",
                 lambda root: leg_workflow(root) + "# café\n".encode("utf-8"),
                 id="utf-8-comment"),
    pytest.param("legs.yml",
                 lambda root: b"\xef\xbb\xbf" + leg_workflow(root),
                 id="utf-8-byte-order-mark"),
    pytest.param("notes.txt", lambda root: b"# caf\xe9\n",
                 id="a-latin-1-file-that-is-not-a-workflow"),
])
def test_what_is_readable_or_not_a_workflow_still_passes(project, name, build):
    """Row (e), and its two neighbours: UTF-8 with a non-ASCII comment, UTF-8
    with a byte-order mark (which `utf-8` keeps as a character and does not
    refuse), and a file under `.github/workflows/` that is neither `.yml` nor
    `.yaml`, which this validator has never read."""
    commit_bytes(project, f"{WORKFLOWS}/{name}", build(project),
                 f"workflow {name}")
    result = validate(project)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "pins ok" in result.stdout
