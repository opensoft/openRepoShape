# SPDX-License-Identifier: Apache-2.0
"""Under a locale of one byte to a character, the assembly root's
`scripts/bootstrap.py` finds HEAD on the tracking branch it made, and says so
(#1283, #1259's row 13).

ON 0354a7e7 (2026-11-10), Python 3.12.3, git 2.43.0, `bootstrap.py
--skip-validators` under a Latin-1 locale built as below
(`sys.getfilesystemencoding()` `iso8859-1`), over a project whose
`project.yaml` says `tracking_branch: "tb\\udcffx"`: the spelling step (a)
takes for a branch holding the byte 0xFF, which it hands to git since #715.
The first run made `refs/heads/tb<ff>x` in both legs, with HEAD on it at the
pin, and said `could not create branch 'tb\\udcffx' at the pin ...; leaving
detached` over `` `git checkout -b` exited 0 ``, and set the `spec` leg's
branch no upstream. Every later run said `branch tb\\udcffx is at the pin
..., and git refused to check it out:` over `` `git checkout` exited 0 ``,
and ended `bootstrap ok`. Under UTF-8 and ASCII the same project gave
`created`, then `on`.

THE CAUSE. `_head_of` reads HEAD's ref with `os.fsdecode`, and step (a)
compared that text with `refs/heads/<branch>` as the manifest spells it.
`os.fsencode("tb\\udcffx")` is `tb<ff>x` under Latin-1, as under UTF-8, but
Latin-1 reads `tb<ff>x` back as `tb` U+00FF `x`. The two texts differ in
every place that asked whether HEAD is on the branch: the check after
`checkout -b` and the one after `checkout`, `place_at_pin`'s line that the
leg left another branch and its `nothing to check out`, the choice between
`merge --ff-only` and `branch -f` in `fast_forward_to_pin`, and where
`_stays` says the checkout stays. Each is a row here. `_branch_ref` now
reads the tracking branch back as `_head_of` reads git's ref, and the lines
go on printing the manifest's spelling.

UNDER UTF-8 ONE NAME CHANGES TOO, by the same cause: `caf\\udcc3\\udca9`, the
two bytes of U+00E9 spelled as surrogates, is handed to git as those two
bytes, which UTF-8 reads back as `caf` U+00E9 and not as the surrogates the
manifest wrote, so on 0354a7e7 it met the same two lines under UTF-8 as
well. No other line changes under UTF-8 or ASCII.

Every row runs `bootstrap.py` in a CHILD under the locale it names, so a
suite run under UTF-8, as CI's is, measures Latin-1. Each git command a row
runs itself names a branch by the bytes the child hands git. The Latin-1
locale is built by this module's own `latin1` fixture, as
`tests/test_adopt_one_byte_locale.py` and
`tests/test_adopt_filter_repo_origin_url.py` each build theirs, and not
imported from either: a module-scoped fixture imported into another module
runs twice in the full suite (#1188). Where no Latin-1 locale can be built
the Latin-1 rows skip with `localedef`'s words, and the UTF-8 and ASCII
rows still run.
"""

from __future__ import annotations

import codecs
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO, git, git_answer_bytes
from test_bootstrap_after_bump import failing_post_checkout
from test_bootstrap_spelling import (DASH, bootstrap_of, edit,
                                     needs_a_byte_name, run)
from test_stdout_encoding import child_environ

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import spelled  # noqa: E402

pytestmark = pytest.mark.skipif(
    os.name == "nt", reason="a locale of one byte to a character is a POSIX "
    "idea: Windows hands a command line to CreateProcessW as UTF-16")

#: The locale #1259 and #1283 name, as `LC_ALL` names the one built here.
LATIN1_NAME = "en_US.ISO-8859-1"
#: What the child adds to its environment for each locale but Latin-1's,
#: which `latin1` builds. UTF-8 is Python's UTF-8 mode, which holds whatever
#: locale is there; ASCII is #710's `LC_ALL=C PYTHONUTF8=0`.
LOCALES = {
    "utf-8": {"LC_ALL": "C.UTF-8", "PYTHONUTF8": "1"},
    "ascii": {"LC_ALL": "C", "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0"},
}
#: The file name encoding a child in each locale must report, or the row
#: skips: the codec `os.fsencode` hands git a branch's name in.
CODECS = {"latin1": "iso8859-1", "utf-8": "utf-8", "ascii": "ascii"}
#: `(the YAML scalar after `tracking_branch:`, the branch as text, what the
#: lines print of it)`. The scalar is YAML, so `\\udcff` is an escape the
#: manifest's reader resolves.
NAMES = {
    # #715's byte 0xFF, row 13's name.
    "byte-0xff": (r'"tb\udcffx"', "tb\udcffx", r"tb\udcffx"),
    # A name that is ASCII, which every locale hands git alike.
    "ascii-name": ('"feature/x"', "feature/x", "feature/x"),
    # U+00FF itself, not a surrogate: one byte in Latin-1, two in UTF-8.
    "u00ff-itself": (r'"tb\xffx"', "tbÿx", "tbÿx"),
    # UTF-8's two bytes of U+00E9 spelled as surrogates.
    "utf-8-bytes-as-surrogates": (r'"caf\udcc3\udca9"', "caf\udcc3\udca9",
                                  r"caf\udcc3\udca9"),
}
STEP_A = "(a) legs on tracking branches, pins untouched"
STEP_B = "(b) neutral validators"


def charmap() -> str:
    """The charmap `localedef -f` builds Latin-1 from: the code point of each
    byte is the byte's own number."""
    head = ("<code_set_name> ISO-8859-1", "<comment_char> %",
            "<escape_char> /", "<mb_cur_min> 1", "<mb_cur_max> 1",
            "CHARMAP")
    rows = tuple(f"<U{code:04X}> /x{code:02x}" for code in range(0x100))
    return "\n".join((*head, *rows, "END CHARMAP", ""))


def reported_codec(tmp_path: Path, changes: dict) -> str:
    """The file name encoding a child Python reports under `changes`."""
    return subprocess.run(
        [sys.executable, "-c", "import codecs, sys; "
         "print(codecs.lookup(sys.getfilesystemencoding()).name)"],
        env=child_environ(tmp_path, None, changes), capture_output=True,
        text=True, errors="replace", stdin=subprocess.DEVNULL,
        check=False).stdout.strip()


@pytest.fixture(scope="module")
def latin1(tmp_path_factory) -> dict:
    """`LOCPATH`, `LC_ALL` and `PYTHONUTF8=0` for a child in a Latin-1
    locale this module builds with `localedef -c`, which says that every
    category but `LC_CTYPE` is empty (exit 1, warnings). A child in it must
    report Latin-1, or each Latin-1 row skips with `localedef`'s words."""
    localedef = shutil.which("localedef")
    if localedef is None:
        pytest.skip(f"no `localedef` here to build {LATIN1_NAME} with")
    kit = tmp_path_factory.mktemp("latin1-locale")
    (kit / "ISO-8859-1").write_text(charmap(), encoding="ascii")
    (kit / "ctype").write_text("LC_CTYPE\nEND LC_CTYPE\n", encoding="ascii")
    (kit / "locales").mkdir()
    built = subprocess.run(
        [localedef, "-c", "-i", str(kit / "ctype"), "-f",
         str(kit / "ISO-8859-1"), str(kit / "locales" / LATIN1_NAME)],
        capture_output=True, text=True, errors="replace",
        stdin=subprocess.DEVNULL, check=False)
    changes = {"LOCPATH": str(kit / "locales"), "LC_ALL": LATIN1_NAME,
               "PYTHONUTF8": "0"}
    told = reported_codec(kit, changes)
    if told != codecs.lookup(CODECS["latin1"]).name:
        said = " ".join(line for line in built.stderr.splitlines()
                        if not line.startswith("[warning]"))
        pytest.skip(f"localedef could not build {LATIN1_NAME} here (exit "
                    f"{built.returncode}: {said[-300:]!r}); a child in it "
                    f"reports {told!r}")
    return changes


@pytest.fixture
def child_locale(request, tmp_path) -> tuple[str, dict]:
    """`(name, the child's environment)` for the locale a row names
    (`indirect`): Latin-1's from `latin1`, the others from `LOCALES`. A
    locale whose child does not report its codec skips the row (ASCII on a
    system where `LC_ALL=C` gives Python UTF-8)."""
    name = request.param
    changes = (request.getfixturevalue("latin1") if name == "latin1"
               else LOCALES[name])
    told = reported_codec(tmp_path, changes)
    if told != codecs.lookup(CODECS[name]).name:
        pytest.skip(f"a child under {changes} reports {told!r}, not "
                    f"{CODECS[name]!r}")
    return name, changes


def tracking(project: Path, tmp_path: Path, name: str,
             locale: str) -> tuple[str, bytes]:
    """`tracking_branch` set to `NAMES[name]`; returns what the lines print
    of it and the bytes a child in `locale` hands git for it. A name that is
    not UTF-8 skips where the disk takes no such file name."""
    scalar, text, printed = NAMES[name]
    raw = text.encode(CODECS[locale], "surrogateescape")
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        needs_a_byte_name(tmp_path)
    edit(project, "project.yaml", 'tracking_branch: "main"',
         f"tracking_branch: {scalar}")
    return printed, raw


def ref(raw: bytes, prefix: str = "refs/heads/") -> str:
    """The ref named by `raw` as this process names it to git:
    `subprocess`'s `os.fsencode` gives the bytes back in any locale."""
    return prefix + os.fsdecode(raw)


def step_a(project: Path, tmp_path: Path, changes: dict,
           extra: dict | None = None) -> list[str]:
    """Step (a)'s lines of one `bootstrap.py --skip-validators` in a child
    under `changes`, its stdout UTF-8 as row 13's is. Exit 0, no traceback,
    no surrogate printed raw."""
    code, out, err = run(bootstrap_of(project), "--skip-validators",
                         encoding="utf-8:strict", tmp_path=tmp_path,
                         cwd=project, changes={**changes, **(extra or {})})
    assert code == 0 and "Traceback" not in err, out + err
    lines = out.split("\n")
    return lines[lines.index(STEP_A) + 1:lines.index(STEP_B) - 1]


def on_the_branch(leg: Path) -> tuple[bytes, str]:
    """HEAD's ref as git's bytes, and its commit."""
    return (git_answer_bytes(leg, "symbolic-ref", "--quiet", "HEAD"),
            git("rev-parse", "HEAD", cwd=leg).stdout.strip())


def pins(project: Path) -> dict[str, str]:
    return {leg: git("rev-parse", f"HEAD:{leg}", cwd=project).stdout.strip()
            for leg in ("spec", "code")}


def ahead_of(leg: Path, commit: str, message: str) -> str:
    """A commit on `commit`'s tree with `commit` as its parent, on no ref."""
    tree = git("rev-parse", f"{commit}^{{tree}}", cwd=leg).stdout.strip()
    return git("commit-tree", tree, "-p", commit, "-m", message,
               cwd=leg).stdout.strip()


def created(leg: str, printed: str, pin: str, remote: str | None = None
            ) -> str:
    """`create_at_pin`'s line, as row 13 asserts it."""
    state = "at the pin"
    if remote is not None:
        state += (f"; origin/{printed} is {remote[:12]}, which the pin "
                  "deliberately does NOT follow")
    return (f"  [{leg}] {leg}: branch {printed} created at {pin[:12]} "
            f"{DASH} {state}")


def placed(leg: str, printed: str, pin: str) -> str:
    """`place_at_pin`'s line, as row 13 asserts it."""
    return f"  [{leg}] {leg}: on {printed} at {pin[:12]} (branch tip == pin)"


FLOWS = [
    pytest.param("byte-0xff", "latin1", id="byte-0xff-latin1"),
    pytest.param("byte-0xff", "utf-8", id="CONTROL-byte-0xff-utf-8"),
    pytest.param("byte-0xff", "ascii", id="CONTROL-byte-0xff-ascii"),
    pytest.param("ascii-name", "latin1", id="CONTROL-ascii-name-latin1"),
    pytest.param("u00ff-itself", "latin1", id="CONTROL-u00ff-itself-latin1"),
    pytest.param("u00ff-itself", "utf-8", id="CONTROL-u00ff-itself-utf-8"),
    pytest.param("utf-8-bytes-as-surrogates", "latin1",
                 id="utf-8-bytes-as-surrogates-latin1"),
    pytest.param("utf-8-bytes-as-surrogates", "utf-8",
                 id="utf-8-bytes-as-surrogates-utf-8"),
    pytest.param("utf-8-bytes-as-surrogates", "ascii",
                 id="CONTROL-utf-8-bytes-as-surrogates-ascii"),
]
#: The rows of one site each: Latin-1 judges, UTF-8 is the control.
BYTE_0XFF = [pytest.param("latin1", id="latin1"),
             pytest.param("utf-8", id="CONTROL-utf-8")]


@pytest.mark.parametrize("name, child_locale", FLOWS,
                         indirect=["child_locale"])
def test_the_first_run_says_it_made_the_branch_head_is_on(
        project, tmp_path, name, child_locale):
    """Row 13's first run: `created` in both legs, the `spec` leg's naming
    where `origin`'s branch is, and nothing else. HEAD is on the branch at
    the pin, by its bytes, and the branch of the leg that has an `origin`
    one tracks it (#1283's second box). On 0354a7e7, under Latin-1:
    `could not create branch` in both legs, and no upstream."""
    where, changes = child_locale
    printed, raw = tracking(project, tmp_path, name, where)
    pin = pins(project)
    spec = project / "spec"
    other = ahead_of(spec, pin["spec"], "elsewhere")
    git("update-ref", ref(raw, "refs/remotes/origin/"), other, cwd=spec)

    lines = step_a(project, tmp_path, changes)
    assert lines == [created("spec", printed, pin["spec"], other),
                     created("code", printed, pin["code"])], lines
    for leg in ("spec", "code"):
        assert on_the_branch(project / leg) == (
            b"refs/heads/" + raw + b"\n", pin[leg])
    assert git_answer_bytes(spec, "for-each-ref", "--format=%(upstream)",
                            ref(raw)) == b"refs/remotes/origin/" + raw + b"\n"


@pytest.mark.parametrize("name, child_locale", FLOWS,
                         indirect=["child_locale"])
def test_every_later_run_says_the_leg_is_on_the_branch(project, tmp_path,
                                                       name, child_locale):
    """Row 13's second phase: once the branch is made, every later run says
    `on` it at the pin, in both legs, and nothing else, as UTF-8 does. On
    0354a7e7, under Latin-1: `git refused to check it out` over `git
    checkout` exited 0, run after run."""
    where, changes = child_locale
    printed, raw = tracking(project, tmp_path, name, where)
    pin = pins(project)
    step_a(project, tmp_path, changes)
    for _ in range(2):
        lines = step_a(project, tmp_path, changes)
        assert lines == [placed("spec", printed, pin["spec"]),
                         placed("code", printed, pin["code"])], lines
    for leg in ("spec", "code"):
        assert on_the_branch(project / leg) == (
            b"refs/heads/" + raw + b"\n", pin[leg])


@pytest.mark.parametrize("child_locale", BYTE_0XFF, indirect=True)
def test_a_hook_that_fails_where_nothing_moved_is_said_after_on(
        project, tmp_path, child_locale):
    """`place_at_pin` from HEAD already on the branch at the pin, with a
    post-checkout hook that fails (#533): `on`, then `nothing to check
    out, and then git said:` and the hook's words. On 0354a7e7, under
    Latin-1: `git refused to check it out` with the hook's words. Read the
    ref back as the manifest spells it, and only the `already` check, the
    line said `checked out`."""
    where, changes = child_locale
    printed, _ = tracking(project, tmp_path, "byte-0xff", where)
    pin = pins(project)
    step_a(project, tmp_path, changes)
    lines = step_a(project, tmp_path, changes, failing_post_checkout(tmp_path))
    after = ["          nothing to check out, and then git said:",
             "          post-checkout hook failed"]
    assert lines == [placed("spec", printed, pin["spec"]), *after,
                     placed("code", printed, pin["code"]), *after], lines


@pytest.mark.parametrize("detached", [False, True],
                         ids=["head-on-the-branch", "detached-at-the-pin"])
@pytest.mark.parametrize("child_locale", BYTE_0XFF, indirect=True)
def test_a_branch_behind_the_pin_is_fast_forwarded(project, tmp_path,
                                                   child_locale, detached):
    """`fast_forward_to_pin`, from HEAD on the branch (`merge --ff-only`)
    and from a leg detached at the new pin, as `bump-leg.py` leaves it
    (`branch -f`, then `checkout`): `fast-forwarded`, and HEAD on the branch
    at the pin. On 0354a7e7, under Latin-1: from HEAD on the branch, `git
    refused to move it`, git's `cannot force update the branch`, since the
    branch was read as another one and given to `branch -f`; from the
    detached leg, `git refused to check it out` over a HEAD on it."""
    where, changes = child_locale
    printed, raw = tracking(project, tmp_path, "byte-0xff", where)
    spec = project / "spec"
    old = pins(project)["spec"]
    git("checkout", "-q", "-b", os.fsdecode(raw), old, cwd=spec)
    git("commit", "-q", "--allow-empty", "-m", "the pin moves on", cwd=spec)
    new = git("rev-parse", "HEAD", cwd=spec).stdout.strip()
    git("add", "spec", cwd=project)
    git("commit", "-q", "-m", "bump spec", cwd=project)
    if detached:
        git("checkout", "-q", "--detach", new, cwd=spec)
    git("update-ref", ref(raw), old, cwd=spec)

    lines = step_a(project, tmp_path, changes)
    assert lines == [
        f"  [spec] spec: branch {printed} fast-forwarded {old[:12]} -> "
        f"{new[:12]}, the pin",
        created("code", printed, pins(project)["code"])], lines
    assert on_the_branch(spec) == (b"refs/heads/" + raw + b"\n", new)


@pytest.mark.parametrize("child_locale", BYTE_0XFF, indirect=True)
def test_a_branch_past_the_pin_with_no_commit_of_its_own_is_moved_back(
        project, tmp_path, child_locale):
    """`move_back_to_pin` (#475): the branch one commit past the pin, its
    tip `origin`'s, the leg detached at the pin: `moved back`, and HEAD on
    the branch at the pin. On 0354a7e7, under Latin-1: `git refused to
    check it out` over a HEAD on it. The upstream is named as git prints
    it, read in this locale (`origin/tb` U+00FF `x` under Latin-1), and the
    command gives its bytes."""
    where, changes = child_locale
    printed, raw = tracking(project, tmp_path, "byte-0xff", where)
    spec = project / "spec"
    pin = pins(project)["spec"]
    ahead = ahead_of(spec, pin, "the remote moved on")
    git("update-ref", ref(raw, "refs/remotes/origin/"), ahead, cwd=spec)
    git("branch", "-q", "-f", "--track", os.fsdecode(raw),
        ref(raw, "origin/"), cwd=spec)

    lines = step_a(project, tmp_path, changes)
    held = spelled("origin/" + raw.decode(CODECS[where], "surrogateescape"))
    word = "\"$(printf -- 'origin/tb\\377x')\""
    assert lines == [
        f"  [spec] spec: branch {printed} moved back {ahead[:12]} -> "
        f"{pin[:12]}, the pin; nothing is lost, {held} still holds those "
        f"commits, and `git -C spec merge --ff-only {word}` brings the "
        "branch forward",
        created("code", printed, pins(project)["code"])], lines
    assert on_the_branch(spec) == (b"refs/heads/" + raw + b"\n", pin)


@pytest.mark.parametrize("child_locale", BYTE_0XFF, indirect=True)
def test_a_branch_with_a_commit_of_its_own_stays_with_head_on_it(
        project, tmp_path, child_locale):
    """Row 13's third phase, with the line under it (`_stays`, #533): a
    branch holding a commit the pin lacks, HEAD on it, is not moved, and
    the checkout `stays on <branch> at its tip`. On 0354a7e7, under
    Latin-1: `stays at <sha> (on tb` U+00FF `x)`, the branch read as
    another."""
    where, changes = child_locale
    printed, raw = tracking(project, tmp_path, "byte-0xff", where)
    code = project / "code"
    pin = pins(project)
    git("checkout", "-q", "-b", os.fsdecode(raw), pin["code"], cwd=code)
    git("commit", "-q", "--allow-empty", "-m", "local work", cwd=code)
    tip = git("rev-parse", "HEAD", cwd=code).stdout.strip()

    lines = step_a(project, tmp_path, changes)
    assert lines == [
        created("spec", printed, pin["spec"]),
        f"  [code] code: PIN {pin['code'][:12]} != branch {printed} tip "
        f"{tip[:12]}",
        f"          not moving an existing branch. The checkout stays on "
        f"{printed} at its tip; the recorded pin is authoritative and "
        "advancing it is an explicit commit in this repository."], lines
    assert on_the_branch(code) == (b"refs/heads/" + raw + b"\n", tip)


@pytest.mark.parametrize("child_locale", BYTE_0XFF, indirect=True)
def test_a_leg_on_the_branch_with_no_commit_yet_is_not_said_to_leave_it(
        project, tmp_path, child_locale):
    """`create_at_pin` from HEAD on the tracking branch itself, with no
    commit yet: `created`, and no line that the leg left a branch, since
    it is the one made. On 0354a7e7, under Latin-1: `could not create
    branch ...; leaving it on tb` U+00FF `x`. Read back as the manifest
    spells it in that line's check alone, the leg was said to have been on
    `tb` U+00FF `x`, `a branch with no commit yet`."""
    where, changes = child_locale
    printed, raw = tracking(project, tmp_path, "byte-0xff", where)
    spec = project / "spec"
    git("symbolic-ref", "HEAD", ref(raw), cwd=spec)
    pin = pins(project)

    lines = step_a(project, tmp_path, changes)
    assert lines == [created("spec", printed, pin["spec"]),
                     created("code", printed, pin["code"])], lines
    assert on_the_branch(spec) == (b"refs/heads/" + raw + b"\n",
                                        pin["spec"])
