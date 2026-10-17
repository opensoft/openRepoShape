# SPDX-License-Identifier: Apache-2.0
"""A name git prints is handed back to git as the bytes it was, and a good
name this system's encoding cannot write is said, not a traceback (#710).

Step (a) of the assembly root's `scripts/bootstrap.py` reads names back from
git (the ref HEAD is on, a branch's upstream) and hands them to git again as
arguments. Each read went through `repo_shape.git_out`, which decodes what git
printed as strict UTF-8. #745 (#704) read HEAD's ref as bytes; `_try_git`, the
reader of every other answer, still decoded strictly. It now reads bytes and
decodes them with `os.fsdecode`, the inverse of the `os.fsencode` that
`subprocess` applies to an argument, so the name goes back to git as the same
bytes under any POSIX locale. `git_out` itself is unchanged: the readers of
`origin`'s URL in `shape-doctor.py` and `shape_advisory.py` take its
`UnicodeDecodeError` to mean the URL names nothing (#385).

THE ISSUE'S LINES, each measured on main 24a977c0 (#745's squash) before this
change, in a scaffold's recursive clone bootstrapped once:

- LANE 5'S SITE (issuecomment-6226993443). A tracking branch past the pin with
  no commit of its own, its name and upstream not UTF-8, and the leg detached
  at the pin: `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in
  position 21`, exit 1, from `_upstream_holding`. Now `moved back`.
- THE SAME READ, STRIPPED AS TEXT. `str.strip` takes a U+00A0 off the end of
  the upstream's name, so `refs/remotes/origin/a<U+00A0>` was asked as `.../a`
  and the branch was not moved back (`not moving an existing branch`). The
  bytes are stripped now, so the name keeps every byte.
- THE SAME READ UNDER `ascii`. `main` tracking `origin/日本` past the pin, under
  `LC_ALL=C PYTHONUTF8=0`: `UnicodeEncodeError: 'ascii' codec can't encode
  characters in position 20-21`, exit 1, since the upstream's name read as
  UTF-8 text could not be handed back to `rev-parse`. Now `moved back`.
- L4-125, the issue's own route: a leg on `a<ff>b` (`git branch $'a\\xffb'`),
  bootstrapped twice. Exit 0 on main already, since #745 read HEAD's ref as
  bytes; held here, as the issue asks, by `make bootstrap` and `--branch`.
- L4-126, answered by option (b) as R455 recommended: `tracking_branch:
  "a\\udcffb"` is created by step (a) and named by the validator (exit 1); the
  manifest edited back to `main`, the next run places every leg (exit 0, a
  traceback before #745).
- L4-124, Brett Heap's ruling (a) of 2026-10-17T13:01:07Z. Under
  `LC_ALL=C PYTHONUTF8=0`, `tracking_branch: "feature/日本"` passed the
  validator (`manifest ok`) and ended step (a) in `UnicodeEncodeError: 'ascii'
  codec can't encode characters in position 19-20`, exit 1. `_argument_fault`
  now faults a character `os.fsencode` cannot write, the leg is left as it is,
  and the line of its own says the name is good, names the encoding and gives
  the two ways to run bootstrap under UTF-8; each is run here as printed.

A run that needs the byte 0xff in a file name skips where the disk refuses it
(or Windows, where `_argument_fault` refuses U+DCFF), and a run under `ascii`
skips where `LC_ALL=C PYTHONUTF8=0` gives Python no `ascii` encoding (macOS and
Windows keep UTF-8). The rule itself is held on every platform by an
emulated `ascii` `os.fsencode`.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import git, run_script
from test_bootstrap_after_bump import (  # noqa: F401
    MAIN, bootstrap, bootstrapped, head_ref, moved_back, rev, root,
)
from test_bootstrap_branch_bytes import (  # noqa: F401
    bootstrap_module, legs_state, tracking,
)
from test_bootstrap_spelling import edit
from test_stdout_encoding import child_environ, run_tool_bytes

#: Where L4-124 was measured: the C locale with Python's UTF-8 mode off,
#: which makes the filesystem encoding `ascii`.
ASCII = {"LC_ALL": "C", "PYTHONUTF8": "0"}
#: The two ways out the line gives, each as the environment it names.
WAYS_OUT = [
    pytest.param({"LC_ALL": "C.UTF-8", "PYTHONUTF8": "0"},
                 id="LC_ALL=C.UTF-8"),
    pytest.param({"LC_ALL": "C", "PYTHONUTF8": "1"}, id="PYTHONUTF8=1"),
]
#: The good name L4-124 measured, and what an `ascii` stdout prints of it.
GOOD = "feature/日本"
GOOD_PRINTED = r"feature/\u65e5\u672c"
#: What `_argument_fault` calls the character (`UNWRITABLE`).
UNWRITABLE = "a character this system's encoding cannot write"


def own_line(encoding: str) -> str:
    """The line of its own under a good name the encoding cannot write."""
    return (f"          the name is good, and this system's encoding, "
            f"{encoding}, cannot write it: run bootstrap again under "
            "`LC_ALL=C.UTF-8`, or with `PYTHONUTF8=1`.")


def unwritten(leg: str, printed: str, point: str) -> list[str]:
    """Step (a)'s two lines for a leg whose good branch was not tried."""
    return [f"  [{leg}] {leg}: could not create branch {printed}: it holds "
            f"{point}, {UNWRITABLE}, which no command can be given as an "
            "argument; the leg is left as it is", own_line("ascii")]


def needs_the_byte(tmp_path: Path) -> None:
    """Skip where a name holding the byte 0xff cannot be made: Windows,
    where `_argument_fault` refuses U+DCFF, and a disk that refuses it."""
    if os.name == "nt":
        pytest.skip("U+DCFF is three bytes on Windows, and step (a) does not "
                    "try such a branch at all")
    try:
        (tmp_path / "probe-\udcff").write_bytes(b"")
    except (OSError, ValueError):
        pytest.skip("this disk takes no file name with the byte 0xff")


def encoding_under(tmp_path: Path, changes: dict[str, str]) -> str:
    """The filesystem encoding a child Python gets under `changes`."""
    return subprocess.run(
        [sys.executable, "-c",
         "import sys; print(sys.getfilesystemencoding())"],
        env=child_environ(tmp_path, None, changes), capture_output=True,
        text=True, check=True).stdout.strip()


def under_ascii(tmp_path: Path) -> dict[str, str]:
    """`ASCII`, or a skip where it gives a child Python no `ascii`."""
    if encoding_under(tmp_path, ASCII) != "ascii":
        pytest.skip("`LC_ALL=C PYTHONUTF8=0` gives this system's Python no "
                    "`ascii` filesystem encoding")
    return ASCII


def run_under(root: Path, tmp_path: Path, changes: dict[str, str],
              *args: str) -> tuple[int, str, bytes]:
    """`bootstrap.py <args>` under `changes`, with no `PYTHONIOENCODING`, so
    the stdout's encoding is the locale's: `(exit, stdout, stderr)`."""
    code, out, err = run_tool_bytes(root / "scripts" / "bootstrap.py", *args,
                                    encoding=None, tmp_path=tmp_path, cwd=root,
                                    changes=changes)
    return code, out.decode("utf-8"), err


def head_bytes(leg: Path) -> bytes:
    return subprocess.run(["git", "symbolic-ref", "--quiet", "HEAD"],
                          cwd=str(leg), capture_output=True,
                          check=True).stdout


def step_a(out: str) -> list[str]:
    lines = out.split("\n")
    return lines[lines.index("(a) legs on tracking branches, pins untouched")
                 + 1:lines.index("(b) neutral validators") - 1]


def past_the_pin(leg: Path, upstream: str, branch: str) -> tuple[str, str]:
    """`branch` one commit past the pin, with no commit of its own: its tip
    IS `refs/remotes/origin/<upstream>`, which it tracks, and the leg is
    detached at the pin. Returns the pin and that commit."""
    pin = rev(leg)
    ahead = git("commit-tree", rev(leg, f"{pin}^{{tree}}"), "-p", pin, "-m",
                "the remote moved on", cwd=leg).stdout.strip()
    git("update-ref", f"refs/remotes/origin/{upstream}", ahead, cwd=leg)
    git("checkout", "-q", "--detach", pin, cwd=leg)
    git("branch", "-q", "-f", "--track", branch, f"origin/{upstream}",
        cwd=leg)
    return pin, ahead


# --- the upstream's name goes back to git as the bytes it was ---------------

@pytest.mark.parametrize("raw, byte", [
    pytest.param("a\udcffb", True, id="the-byte-0xff"),
    pytest.param("a\u00a0", False, id="ending-in-U+00A0"),
])
def test_a_branch_past_the_pin_is_moved_back_whatever_its_upstream_is_named(
        root, tmp_path, bootstrap_module, raw, byte):
    """LANE 5'S SITE: on main, a `UnicodeDecodeError` traceback over the
    byte 0xff, and, over a name ending in U+00A0, `not moving an existing
    branch`. Both are moved back now, the line naming the upstream and the
    command as `move_back_to_pin` spells them, and HEAD is on the branch
    whose name is the bytes git was given."""
    if byte:
        needs_the_byte(tmp_path)
    leg = root / "spec"
    pin, ahead = past_the_pin(leg, raw, raw)

    result = run_script(root / "scripts" / "bootstrap.py", "--skip-validators",
                        "--branch", raw, cwd=root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "Traceback" not in result.stderr, result.stderr
    spelled = bootstrap_module.spelled
    command = ("git -C spec merge --ff-only "
               f"{spelled(shlex.quote('origin/' + raw))}")
    assert moved_back(ahead, pin, spelled(raw), command=command) in (
        result.stdout), result.stdout
    assert rev(leg, f"refs/heads/{raw}") == pin and rev(leg) == pin
    assert head_bytes(leg) == b"refs/heads/" + os.fsencode(raw) + b"\n"


def test_under_an_ascii_encoding_an_upstream_named_in_utf8_is_moved_back(
        root, tmp_path, bootstrap_module):
    """`main` tracking `origin/日本`, past the pin, under `LC_ALL=C
    PYTHONUTF8=0`: a `UnicodeEncodeError` traceback on main, since the name
    read as UTF-8 text could not be handed back to `rev-parse`. Decoded as
    `os.fsdecode` decodes it, it is the same ref, and the remote-tracking
    ref still holds the commit."""
    changes = under_ascii(tmp_path)
    leg = root / "spec"
    pin, ahead = past_the_pin(leg, "日本", "main")

    code, out, err = run_under(root, tmp_path, changes, "--skip-validators")
    assert code == 0 and b"Traceback" not in err, out + err.decode("utf-8")
    held = bootstrap_module.spelled(
        "origin/" + "日本".encode("utf-8").decode("ascii", "surrogateescape"))
    assert (f"  [spec] spec: branch main moved back {ahead[:12]} -> "
            f"{pin[:12]}, the pin; nothing is lost, {held} still holds those "
            f"commits, and `git -C spec merge --ff-only '{held}'` brings the "
            "branch forward\n") in out, out
    assert rev(leg, MAIN) == pin and head_ref(leg) == MAIN
    assert rev(leg, "refs/remotes/origin/日本") == ahead


# --- L4-125 and L4-126: every later run places the leg ---------------------

@pytest.mark.parametrize("given", [False, True],
                         ids=["make-bootstrap", "--branch-a<ff>b"])
def test_a_leg_on_a_branch_whose_name_is_not_utf8_is_placed_on_every_run(
        root, tmp_path, given):
    """L4-125: `git branch $'a\\xffb'`, the leg checked out on it, then
    bootstrap twice. Without `--branch` each run puts the leg on `main`,
    the first saying the leg left `a<ff>b`; with `--branch $'a\\xffb'` each
    run says `on` it. Every run exits 0 with the validators run."""
    needs_the_byte(tmp_path)
    leg = root / "spec"
    pin = rev(leg)
    git("branch", "a\udcffb", cwd=leg)
    git("checkout", "-q", "a\udcffb", cwd=leg)
    args = ("--branch", "a\udcffb") if given else ()
    on = r"a\udcffb" if given else "main"
    left = ("          the leg was on a\\udcffb, which keeps its commits; it "
            "is on main now\n")
    for run in (1, 2):
        result = run_script(root / "scripts" / "bootstrap.py", *args,
                            cwd=root)
        assert result.returncode == 0, result.stderr + result.stdout
        assert "Traceback" not in result.stderr, result.stderr
        assert result.stdout.endswith("bootstrap ok\n"), result.stdout
        placed = f"  [spec] spec: on {on} at {pin[:12]} (branch tip == pin)\n"
        assert placed in result.stdout, result.stdout
        assert (placed + left in result.stdout) is (
            not given and run == 1), result.stdout
    assert head_bytes(leg) == (b"refs/heads/a\xffb\n" if given
                               else b"refs/heads/main\n")


def test_a_tracking_branch_the_validator_names_is_followed_and_then_placed(
        root, tmp_path):
    """L4-126, option (b): step (a) creates `a<ff>b` from the manifest's
    `"a\\udcffb"` and the validator names it, exit 1. The finding followed,
    `main` again, the next run puts every leg on `main` and exits 0, where
    it ended in a `UnicodeDecodeError` before #745."""
    needs_the_byte(tmp_path)
    pins = {leg: rev(root / leg) for leg in ("spec", "code")}
    tracking(root, r'"a\udcffb"')
    first = bootstrap(root)
    assert first.returncode == 1, first.stderr + first.stdout
    assert "Traceback" not in first.stderr, first.stderr
    assert ("FINDING manifest-tracking-branch: tracking_branch is "
            "'a\\udcffb', which holds U+DCFF") in first.stderr, first.stderr
    assert "bootstrap FAILED: manifest (exit 1)" in first.stderr
    for leg, pin in pins.items():
        assert (f"  [{leg}] {leg}: branch a\\udcffb created at {pin[:12]} "
                "— at the pin\n") in first.stdout, first.stdout
        assert head_bytes(root / leg) == b"refs/heads/a\xffb\n"

    edit(root, "project.yaml", r'tracking_branch: "a\udcffb"',
         'tracking_branch: "main"')
    second = bootstrap(root)
    assert second.returncode == 0, second.stderr + second.stdout
    assert second.stdout.endswith("bootstrap ok\n"), second.stdout
    for leg, pin in pins.items():
        assert (f"  [{leg}] {leg}: on main at {pin[:12]} (branch tip == "
                f"pin)\n          the leg was on a\\udcffb, which keeps its "
                "commits; it is on main now\n") in second.stdout, second.stdout
        assert head_ref(root / leg) == MAIN


# --- L4-124: a good name the encoding cannot write is said ------------------

@pytest.mark.parametrize("way_out", WAYS_OUT)
def test_a_good_name_this_encoding_cannot_write_is_said_and_the_way_out_works(
        root, tmp_path, way_out):
    """Under `LC_ALL=C PYTHONUTF8=0`, `tracking_branch: "feature/日本"`:
    the validators pass it, as they did, and step (a) ended in a
    `UnicodeEncodeError` traceback. Now each leg is left exactly as it was
    under the two lines, and the run ends `bootstrap ok`. Then the way out,
    run as the line gives it, puts each leg on `feature/日本`."""
    changes = under_ascii(tmp_path)
    if encoding_under(tmp_path, way_out) != "utf-8":
        pytest.skip(f"{way_out} gives this system's Python no UTF-8")
    tracking(root, f'"{GOOD}"')
    before = legs_state(root)

    code, out, err = run_under(root, tmp_path, changes)
    assert code == 0 and b"Traceback" not in err, out + err.decode("utf-8")
    assert step_a(out) == (unwritten("spec", GOOD_PRINTED, "U+65E5")
                           + unwritten("code", GOOD_PRINTED, "U+65E5")), out
    assert "manifest ok: Atlas (atlas), 3 legs" in out, out
    assert out.endswith("bootstrap ok\n"), out
    assert legs_state(root) == before

    code, out, err = run_under(root, tmp_path, way_out)
    assert code == 0 and b"Traceback" not in err, out + err.decode("utf-8")
    for leg in ("spec", "code"):
        assert f"  [{leg}] {leg}: branch {GOOD} created at " in out, out
        assert head_bytes(root / leg) == (
            b"refs/heads/" + GOOD.encode("utf-8") + b"\n")


def ascii_fsencode(text):
    """`os.fsencode` where the filesystem encoding is `ascii`: bytes as they
    are, text through `surrogateescape`, as POSIX's handler is."""
    if isinstance(text, bytes):
        return text
    return text.encode("ascii", "surrogateescape")


@pytest.mark.parametrize("branch, fault", [
    (GOOD, f"U+65E5, {UNWRITABLE}"),
    ("a\xe9b", f"U+00E9, {UNWRITABLE}"),
    # A NUL or a lone surrogate ANYWHERE is named first: that name is not
    # good, so the line saying it is would be false.
    ("日\x00", "U+0000, a NUL"),
    ("日\ud83d", "U+D83D, a lone surrogate"),
])
def test_under_an_ascii_encoding_what_it_cannot_write_is_the_fault(
        bootstrap_module, monkeypatch, branch, fault):
    monkeypatch.setattr(bootstrap_module.os, "fsencode", ascii_fsencode)
    assert bootstrap_module._argument_fault(branch) == fault


@pytest.mark.parametrize("branch", [
    "main", "release/1.2", "",
    "a\udcffb",            # the byte 0xff, as POSIX spells it
    "x\udcc3\udca9",       # `--branch xé` typed under the C locale
])
def test_under_an_ascii_encoding_what_it_writes_has_no_fault(
        bootstrap_module, monkeypatch, branch):
    """A name the encoding writes, the bytes of one typed under it
    included, is carried as it was: `--branch` reaches git as the bytes
    the person typed."""
    monkeypatch.setattr(bootstrap_module.os, "fsencode", ascii_fsencode)
    assert bootstrap_module._argument_fault(branch) is None


def test_the_line_for_a_name_the_encoding_cannot_write_is_its_own(
        bootstrap_module, monkeypatch, capsys):
    """The second line is the ruling's own, naming the encoding the
    process has, and #455's NUL keeps its line."""
    monkeypatch.setattr(bootstrap_module.os, "fsencode", ascii_fsencode)
    say = bootstrap_module._say_not_tried
    say("[spec] spec", GOOD, bootstrap_module._argument_fault(GOOD))
    say("[code] code", "a\\x00b", bootstrap_module._argument_fault("a\x00b"))
    lines = capsys.readouterr().out.split("\n")
    assert lines[:2] == [
        f"  [spec] spec: could not create branch {GOOD}: it holds U+65E5, "
        f"{UNWRITABLE}, which no command can be given as an argument; the "
        "leg is left as it is", own_line(sys.getfilesystemencoding())], lines
    assert lines[3] == (
        "          the branch is the leg's `branch:`, else `--branch`, else "
        "`tracking_branch`. Give that one a name git can create and run "
        "bootstrap again."), lines
