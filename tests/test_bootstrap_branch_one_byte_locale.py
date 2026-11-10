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

A CASE TWIN IS ONE IN EVERY LOCALE (#1306). On cb9ed806 `_folded_twin`
folded HEAD's ref, as `_head_of` decodes it, with the manifest's text, so
where the locale read a twin's bytes as other text it missed the twin, and
step (a) made the branch beside it and said `created`: `TB<ff>x` for
`tb\\udcffx` under Latin-1, and `CAF<c3 a9>` for `caf\\udcc3\\udca9` under
UTF-8 and Latin-1, with HEAD on the twin, beside it at the pin, or on it
beside the branch. Both names are now git's bytes, whatever the locale, read
as each disk that folds case reads them: as UTF-8, the name APFS holds, and
as git for Windows names the file on NTFS (`xutftowcsn`), where a byte 0xA0
to 0xFF that is not UTF-8 is that Latin-1 character. A pair whose bytes
differ is a twin where EITHER reading folds it alike, so `tb<e4>x` and
`tb<c4>x` are twins in every locale (r1308a's F1 on #1308). The rows over the
twins, and their controls, are the ones after
`test_a_leg_on_the_branch_with_no_commit_yet_is_not_said_to_leave_it`.

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

from conftest import REPO, git, git_answer_bytes, load_without_bytecode
from test_bootstrap_after_bump import failing_post_checkout
from test_bootstrap_spelling import (ASSEMBLY_TEMPLATE, DASH, bootstrap_of,
                                     edit, needs_a_byte_name, run)
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
    "u00ff-itself": (r'"tb\xffx"', "tb\u00ffx", "tb\u00ffx"),
    # UTF-8's two bytes of U+00E9 spelled as surrogates.
    "utf-8-bytes-as-surrogates": (r'"caf\udcc3\udca9"', "caf\udcc3\udca9",
                                  r"caf\udcc3\udca9"),
    # The same name, for `TWINS`' twin with U+00E9 in capitals too (#1306).
    "utf-8-capital": (r'"caf\udcc3\udca9"', "caf\udcc3\udca9",
                      r"caf\udcc3\udca9"),
    # The byte 0xC4, Latin-1's U+00C4, whose small letter is 0xE4 (#1306).
    "byte-0xc4": (r'"tb\udcc4x"', "tb\udcc4x", r"tb\udcc4x"),
    # The byte 0xE4, Latin-1's U+00E4, whose capital is 0xC4 (#1306).
    "byte-0xe4": (r'"tb\udce4x"', "tb\udce4x", r"tb\udce4x"),
    # The byte 0x84, which git for Windows names `84` on NTFS (#1306).
    "byte-0x84": (r'"tb\udc84x"', "tb\udc84x", r"tb\udc84x"),
    # U+00E4 itself: the byte 0xE4 in Latin-1, two bytes in UTF-8 (#1306).
    "u00e4-itself": (r'"tb\xe4x"', "tb\u00e4x", "tb\u00e4x"),
    # U+00E9 itself, in NFC (#962).
    "nfc": (r'"caf\xe9"', "caf\u00e9", "caf\u00e9"),
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


#: The case twin of each name, by its bytes: the name's own, its ASCII
#: letters in capitals, as #1306 measured them, and for `utf-8-capital` its
#: U+00E9 in capitals too, `CAF<c3 89>` (r1308a's F4 on #1308).
TWINS = {"byte-0xff": b"TB\xffx", "utf-8-bytes-as-surrogates": b"CAF\xc3\xa9",
         "utf-8-capital": b"CAF\xc3\x89"}
#: The twin rows (#1306): each name in each locale. On cb9ed806 Latin-1
#: missed the first two twins and UTF-8 the second, and every locale missed
#: `CAF<c3 89>`; the others are the CONTROLS.
TWIN_ROWS = [
    pytest.param("byte-0xff", "latin1", id="byte-0xff-latin1"),
    pytest.param("byte-0xff", "utf-8", id="CONTROL-byte-0xff-utf-8"),
    pytest.param("byte-0xff", "ascii", id="CONTROL-byte-0xff-ascii"),
    pytest.param("utf-8-bytes-as-surrogates", "latin1",
                 id="utf-8-bytes-as-surrogates-latin1"),
    pytest.param("utf-8-bytes-as-surrogates", "utf-8",
                 id="utf-8-bytes-as-surrogates-utf-8"),
    pytest.param("utf-8-bytes-as-surrogates", "ascii",
                 id="CONTROL-utf-8-bytes-as-surrogates-ascii"),
    pytest.param("utf-8-capital", "latin1", id="utf-8-capital-latin1"),
    pytest.param("utf-8-capital", "utf-8", id="utf-8-capital-utf-8"),
    pytest.param("utf-8-capital", "ascii", id="utf-8-capital-ascii"),
]
#: Each name in each locale, where every side gives one answer.
EVERY_LOCALE = [pytest.param(name, where, id=f"CONTROL-{name}-{where}")
                for name in ("byte-0xff", "utf-8-bytes-as-surrogates")
                for where in ("latin1", "utf-8", "ascii")]
#: What `_twin_words` says a twin differs in, what reads the two as one, and
#: what a name must differ in to be no twin (#896, #962).
CASE = ("only in case", "a disk that folds case (macOS, Windows)", "case")
FORM = ("only in case or Unicode form",
        "a disk that folds case or Unicode forms (macOS folds both, Windows "
        "folds case)", "case or Unicode form")
#: The second twin line's harm, by what step (a) would have done (#896).
MAKE = ("making {b} could hide the commits a branch spelled like {b} holds "
        "behind the new ref")
PLACE = ("the leg is already on {b} there, and bootstrap would say it left a "
         "branch that keeps its commits")
MOVE = ("moving {b} could move the ref HEAD stands on and leave the index at "
        "the old commit")


def as_read(raw: bytes, where: str) -> str:
    """The name git holds as `raw` as a child in `where` reads it back and
    the lines print it (#391): git's name, in this locale."""
    return spelled(raw.decode(CODECS[where], "surrogateescape"))


def printf_word(escaped: str) -> str:
    """The word `_paste_word` writes for a name it gives as bytes (#932)."""
    return f"\"$(printf -- '{escaped}')\""


def renamed(name: str, where: str) -> tuple[str, str]:
    """The two words of the rename the third twin line gives for `TWINS`'s
    twin of `name`: a `printf` of its bytes, but under UTF-8 for `CAF`
    U+00E9 and `CAF` U+00C9, which the child prints as those very bytes."""
    if name == "byte-0xff":
        return printf_word("TB\\377x"), printf_word("TB\\377x-kept")
    if name == "utf-8-capital":
        if where == "utf-8":
            return "'CAF\u00c9'", "'CAF\u00c9-kept'"
        return (printf_word("CAF\\303\\211"),
                printf_word("CAF\\303\\211-kept"))
    if where == "utf-8":
        return "'CAF\u00e9'", "'CAF\u00e9-kept'"
    return printf_word("CAF\\303\\251"), printf_word("CAF\\303\\251-kept")


def twin_lines(state: str, where_held: str, twin: str, printed: str,
               act: str, way: str, kind: tuple = CASE) -> list[str]:
    """The three lines step (a) prints of the `spec` leg with a twin of the
    branch, byte for byte: `where_held` says how the leg has it, `act` is
    the harm and `way` the way out's line, its command between backticks."""
    how, reads, _ = kind
    return [f"  [spec] spec: {state}, and {where_held} {twin}, which differs "
            f"from {printed} {how}",
            f"          {reads} reads {twin} and {printed} as one branch, so "
            f"{act.format(b=printed)}; the leg is left as it is", way]


def rename_line(twin: str, printed: str, words: tuple[str, str],
                kind: tuple = CASE) -> str:
    """`_say_spelling`'s way out: rename the twin, `words` being the two
    names as the line words them."""
    return (f"          rename {twin} to a name that differs from {printed} "
            f"by more than {kind[2]}, its commits staying on it: `git -C spec "
            f"branch -m {words[0]} {words[1]}`, and run bootstrap again.")


def shell_reads(line: str) -> list[bytes]:
    """The arguments `/bin/sh` hands `git` from the command between the
    backticks of `line`, `git` being a function that prints them, each
    ended by a NUL: the bytes a paste of the line names (#932). The command
    is handed over as the bytes the child wrote, its stdout being UTF-8,
    and not as this process's locale would write the text."""
    command = line.split("`")[1].encode("utf-8")
    read = subprocess.run(
        [b"/bin/sh", b"-c", b'git() { printf "%s\\0" "$@"; }\n' + command],
        capture_output=True, check=True, stdin=subprocess.DEVNULL).stdout
    return read.split(b"\0")[:-1]


def heads(leg: Path) -> bytes:
    """Every branch of the leg, as git's bytes, one to a line."""
    return git_answer_bytes(leg, "for-each-ref", "--format=%(refname)",
                            "refs/heads/")


@pytest.mark.parametrize("name, child_locale", TWIN_ROWS,
                         indirect=["child_locale"])
def test_a_leg_on_a_case_twin_of_the_branch_is_left_in_every_locale(
        project, tmp_path, name, child_locale):
    """#1306's second box: the branch not there, HEAD on its case twin at the
    pin (`TB<ff>x` for `tb\\udcffx`, `CAF<c3 a9>` for `caf\\udcc3\\udca9`).
    In every locale: the three twin lines, the twin named as git's name in
    that locale, the rename pasting its bytes, and the leg left on it. On
    cb9ed806, under Latin-1 for both and under UTF-8 for the second: the
    branch made beside the twin, `created`, and `the leg was on` the twin."""
    where, changes = child_locale
    printed, _ = tracking(project, tmp_path, name, where)
    twin = TWINS[name]
    pin = pins(project)
    spec = project / "spec"
    git("checkout", "-q", "-b", os.fsdecode(twin), pin["spec"], cwd=spec)
    shown = as_read(twin, where)

    lines = step_a(project, tmp_path, changes)
    assert lines == [
        *twin_lines(f"branch {printed} does not exist (the pin is "
                    f"{pin['spec'][:12]})", "the checkout is on", shown,
                    printed, MAKE, rename_line(shown, printed,
                                               renamed(name, where))),
        created("code", printed, pin["code"])], lines
    assert shell_reads(lines[2]) == [b"-C", b"spec", b"branch", b"-m", twin,
                                     twin + b"-kept"]
    assert on_the_branch(spec) == (b"refs/heads/" + twin + b"\n", pin["spec"])
    assert heads(spec) == b"refs/heads/" + twin + b"\nrefs/heads/main\n"


@pytest.mark.parametrize("name, child_locale", TWIN_ROWS,
                         indirect=["child_locale"])
def test_a_leg_detached_beside_a_case_twin_is_left_in_every_locale(
        project, tmp_path, name, child_locale):
    """#1306's third box, `_folded_spelling`: the branch not there, the leg
    detached at the pin, and its case twin a branch there. In every locale:
    the three lines that the leg has the twin, and the leg left detached. On
    cb9ed806, under Latin-1 for both and under UTF-8 for the second: the
    branch made beside the twin, and `created`."""
    where, changes = child_locale
    printed, _ = tracking(project, tmp_path, name, where)
    twin = TWINS[name]
    pin = pins(project)
    spec = project / "spec"
    git("branch", "-q", os.fsdecode(twin), pin["spec"], cwd=spec)
    assert on_the_branch(spec) == (b"", pin["spec"]), "detached at the pin"
    shown = as_read(twin, where)

    lines = step_a(project, tmp_path, changes)
    assert lines == [
        *twin_lines(f"branch {printed} does not exist (the pin is "
                    f"{pin['spec'][:12]})", "the leg has the branch", shown,
                    printed, MAKE, rename_line(shown, printed,
                                               renamed(name, where))),
        created("code", printed, pin["code"])], lines
    assert shell_reads(lines[2]) == [b"-C", b"spec", b"branch", b"-m", twin,
                                     twin + b"-kept"]
    assert on_the_branch(spec) == (b"", pin["spec"])
    assert heads(spec) == b"refs/heads/" + twin + b"\nrefs/heads/main\n"


@pytest.mark.parametrize("name, child_locale", TWIN_ROWS,
                         indirect=["child_locale"])
def test_a_leg_on_a_case_twin_of_the_branch_at_the_pin_is_left(
        project, tmp_path, name, child_locale):
    """`place_at_pin` (#896's P9): the branch at the pin, and HEAD on its case
    twin there, on a disk that keeps case. In every locale: the three twin
    lines, the `switch` pasting the branch's bytes, and the leg left on the
    twin. On cb9ed806, under Latin-1 for both and under UTF-8 for the second:
    the branch checked out, and `the leg was on` the twin, which a disk that
    folds case reads as the branch itself."""
    where, changes = child_locale
    printed, raw = tracking(project, tmp_path, name, where)
    twin = TWINS[name]
    pin = pins(project)
    spec = project / "spec"
    git("branch", "-q", os.fsdecode(raw), pin["spec"], cwd=spec)
    if git("checkout", "-q", "-b", os.fsdecode(twin), pin["spec"], cwd=spec,
           check=False).returncode != 0:
        pytest.skip("this disk folds case: the twin is the branch here")
    shown = as_read(twin, where)
    switch = printf_word("tb\\377x" if name == "byte-0xff"
                         else "caf\\303\\251")

    lines = step_a(project, tmp_path, changes)
    assert lines == [
        *twin_lines(f"branch {printed} is at the pin {pin['spec'][:12]}",
                    "the checkout is on", shown, printed, PLACE,
                    f"          run `git -C spec switch {switch}`, which "
                    "moves no branch, and then run bootstrap again."),
        created("code", printed, pin["code"])], lines
    assert shell_reads(lines[2]) == [b"-C", b"spec", b"switch", raw]
    assert on_the_branch(spec) == (b"refs/heads/" + twin + b"\n", pin["spec"])


@pytest.mark.parametrize("name, child_locale", TWIN_ROWS,
                         indirect=["child_locale"])
def test_a_leg_on_a_case_twin_of_a_branch_behind_the_pin_is_left(
        project, tmp_path, name, child_locale):
    """`fast_forward_to_pin` (#896's own harm, `move`): the branch at the old
    pin, behind the pin, and HEAD on its case twin at the old pin, on a
    disk that keeps case. In every locale: the three twin lines, the
    `switch` pasting the branch's bytes, and no ref moved. On cb9ed806,
    where it missed the twin (`TB<ff>x` under Latin-1, `CAF<c3 a9>` under
    Latin-1 and UTF-8, `CAF<c3 89>` in every locale): the branch
    fast-forwarded and checked out, which a disk that folds case reads as
    the ref HEAD stands on (r1308a's F4 on #1308)."""
    where, changes = child_locale
    printed, raw = tracking(project, tmp_path, name, where)
    twin = TWINS[name]
    spec = project / "spec"
    old = pins(project)["spec"]
    new = ahead_of(spec, old, "the pin moves on")
    git("update-index", "--cacheinfo", f"160000,{new},spec", cwd=project)
    git("commit", "-q", "-m", "bump spec", cwd=project)
    git("branch", "-q", os.fsdecode(raw), old, cwd=spec)
    if git("checkout", "-q", "-b", os.fsdecode(twin), old, cwd=spec,
           check=False).returncode != 0:
        pytest.skip("this disk folds case: the twin is the branch here")
    shown = as_read(twin, where)
    switch = printf_word("tb\\377x" if name == "byte-0xff"
                         else "caf\\303\\251")

    lines = step_a(project, tmp_path, changes)
    assert lines == [
        *twin_lines(f"branch {printed} tip {old[:12]} is behind the PIN "
                    f"{new[:12]}", "the checkout is on", shown, printed, MOVE,
                    f"          run `git -C spec switch {switch}`, which "
                    "moves no branch, and then run bootstrap again."),
        created("code", printed, pins(project)["code"])], lines
    assert shell_reads(lines[2]) == [b"-C", b"spec", b"switch", raw]
    assert on_the_branch(spec) == (b"refs/heads/" + twin + b"\n", old)
    assert git("rev-parse", ref(raw), cwd=spec).stdout.strip() == old


@pytest.mark.parametrize("name, child_locale", EVERY_LOCALE,
                         indirect=["child_locale"])
def test_a_leg_on_the_branch_itself_has_no_twin_in_any_locale(
        project, tmp_path, name, child_locale):
    """#1306's fourth box: HEAD on the tracking branch itself, with no commit
    yet (`tb<ff>x`, `caf<c3 a9>`), is no twin in any locale, though Latin-1
    reads the first as `tb` U+00FF `x` and UTF-8 the second as `caf` U+00E9:
    `created`, and no line that the leg left a branch. Passes on cb9ed806
    too."""
    where, changes = child_locale
    printed, raw = tracking(project, tmp_path, name, where)
    pin = pins(project)
    spec = project / "spec"
    git("symbolic-ref", "HEAD", ref(raw), cwd=spec)

    lines = step_a(project, tmp_path, changes)
    assert lines == [created("spec", printed, pin["spec"]),
                     created("code", printed, pin["code"])], lines
    assert on_the_branch(spec) == (b"refs/heads/" + raw + b"\n", pin["spec"])


@pytest.mark.parametrize("child_locale", ["latin1", "utf-8", "ascii"],
                         indirect=True)
def test_the_bytes_0xc4_and_0xe4_are_twins_in_every_locale(
        project, tmp_path, child_locale):
    """w1283a's Latin-1 objection (#1306), answered by the second reading:
    HEAD on `tb<e4>x` with `tracking_branch: "tb\\udcc4x"`. Latin-1 reads the
    bytes as U+00E4 and U+00C4, and UTF-8 and ASCII as two surrogate
    escapes, but git for Windows names the files `tb` U+00E4 `x` and `tb`
    U+00C4 `x`, which NTFS folds to one. So they are twins in every
    locale: the three twin lines, the rename pasting `tb<e4>x`'s bytes, and
    the leg left on it. This row was a CONTROL, no twin in any locale,
    until r1308a's F1 on #1308; on cb9ed806 it fails in each: the branch
    made, `created`, and `the leg was on` `tb<e4>x`."""
    where, changes = child_locale
    printed, _ = tracking(project, tmp_path, "byte-0xc4", where)
    other = b"tb\xe4x"
    pin = pins(project)
    spec = project / "spec"
    git("checkout", "-q", "-b", os.fsdecode(other), pin["spec"], cwd=spec)
    shown = as_read(other, where)

    lines = step_a(project, tmp_path, changes)
    assert lines == [
        *twin_lines(f"branch {printed} does not exist (the pin is "
                    f"{pin['spec'][:12]})", "the checkout is on", shown,
                    printed, MAKE,
                    rename_line(shown, printed,
                                (printf_word("tb\\344x"),
                                 printf_word("tb\\344x-kept")))),
        created("code", printed, pin["code"])], lines
    assert shell_reads(lines[2]) == [b"-C", b"spec", b"branch", b"-m", other,
                                     other + b"-kept"]
    assert on_the_branch(spec) == (b"refs/heads/" + other + b"\n", pin["spec"])
    assert heads(spec) == b"refs/heads/main\nrefs/heads/" + other + b"\n"


#: Pairs that differ in a byte that is not UTF-8 and in ASCII case (r1308a's
#: F3 on #1308): `(the tracking branch, HEAD's branch by its bytes, the two
#: words of the rename where the pair is a twin, or None where it is none)`.
#: Each answer is the same in every locale.
PAIRS = [
    # git for Windows names the files `TB` U+00C4 `x` and `tb` U+00E4 `x`.
    pytest.param("byte-0xe4", b"TB\xc4x",
                 (printf_word("TB\\304x"), printf_word("TB\\304x-kept")),
                 id="TB-c4-for-tb-e4"),
    # No reading drops the byte 0xFF, or folds U+00C4 to U+00FF: each pair
    # differs by more than case (`"replace"` and `"ignore"` fold them).
    pytest.param("byte-0xff", b"TBx", None, id="CONTROL-TBx-for-tb-ff"),
    pytest.param("byte-0xff", b"TB\xc4x", None, id="CONTROL-TB-c4-for-tb-ff"),
    # git for Windows writes the byte 0x84 as `84`, so `tb<84>x` is the file
    # `tb84x` on NTFS, which folds `TB84X` to it.
    pytest.param("byte-0x84", b"TB84X", ("TB84X", "TB84X-kept"),
                 id="TB84X-for-tb-84"),
]


@pytest.mark.parametrize("name, held, words", PAIRS)
@pytest.mark.parametrize("child_locale", ["latin1", "utf-8", "ascii"],
                         indirect=True)
def test_a_pair_is_a_twin_where_either_reading_folds_it_alike(
        project, tmp_path, name, held, words, child_locale):
    """Lane 1's decision on #1306, after r1308a's F1 and F3 on #1308: a pair
    whose bytes differ is a twin where its UTF-8 reading or git for
    Windows' reading folds it alike. HEAD on `held` at the pin, the branch
    not there. A twin: the three twin lines, the rename pasting `held`'s
    bytes, and the leg left on it. No twin: `created`, and `the leg was on`
    `held`. The same in every locale. On cb9ed806 the twins here were
    missed in every locale; the CONTROLS pass there too."""
    where, changes = child_locale
    printed, raw = tracking(project, tmp_path, name, where)
    pin = pins(project)
    spec = project / "spec"
    git("checkout", "-q", "-b", os.fsdecode(held), pin["spec"], cwd=spec)
    shown = as_read(held, where)

    lines = step_a(project, tmp_path, changes)
    if words is None:
        assert lines == [
            created("spec", printed, pin["spec"]),
            f"          the leg was on {shown}, which keeps its commits; it "
            f"is on {printed} now",
            created("code", printed, pin["code"])], lines
        assert on_the_branch(spec) == (b"refs/heads/" + raw + b"\n",
                                       pin["spec"])
        return
    assert lines == [
        *twin_lines(f"branch {printed} does not exist (the pin is "
                    f"{pin['spec'][:12]})", "the checkout is on", shown,
                    printed, MAKE, rename_line(shown, printed, words)),
        created("code", printed, pin["code"])], lines
    assert shell_reads(lines[2]) == [b"-C", b"spec", b"branch", b"-m", held,
                                     held + b"-kept"]
    assert on_the_branch(spec) == (b"refs/heads/" + held + b"\n", pin["spec"])


@pytest.mark.parametrize("child_locale", ["latin1", "utf-8", "ascii"],
                         indirect=True)
def test_the_rename_is_to_no_twin_of_a_branch_there_in_every_locale(
        project, tmp_path, child_locale):
    """`_kept_name` (r1308a's F2 on #1308): HEAD on `CAF<c3 a9>`, the twin of
    `caf\\udcc3\\udca9`, beside a branch `caf<c3 89>-kept`, which is
    `CAF<c3 a9>-kept` in another case, read as UTF-8. In every locale the
    rename is to `CAF<c3 a9>-kept-2`. Folded as the locale reads `_heads`'
    text, Latin-1 and ASCII printed `-kept`, a name a disk that folds case
    reads as the branch there; on cb9ed806 Latin-1 and UTF-8 also missed
    the twin."""
    where, changes = child_locale
    name = "utf-8-bytes-as-surrogates"
    printed, _ = tracking(project, tmp_path, name, where)
    twin, taken = TWINS[name], b"caf\xc3\x89-kept"
    pin = pins(project)
    spec = project / "spec"
    git("branch", "-q", os.fsdecode(taken), pin["spec"], cwd=spec)
    git("checkout", "-q", "-b", os.fsdecode(twin), pin["spec"], cwd=spec)
    shown = as_read(twin, where)
    first, kept = renamed(name, where)

    lines = step_a(project, tmp_path, changes)
    assert lines == [
        *twin_lines(f"branch {printed} does not exist (the pin is "
                    f"{pin['spec'][:12]})", "the checkout is on", shown,
                    printed, MAKE,
                    rename_line(shown, printed,
                                (first, kept.replace("-kept", "-kept-2")))),
        created("code", printed, pin["code"])], lines
    assert shell_reads(lines[2]) == [b"-C", b"spec", b"branch", b"-m", twin,
                                     twin + b"-kept-2"]
    assert heads(spec) == (b"refs/heads/" + twin + b"\nrefs/heads/" + taken
                           + b"\nrefs/heads/main\n")


@pytest.mark.parametrize("child_locale", ["latin1", "utf-8", "ascii"],
                         indirect=True, ids=lambda where: f"CONTROL-{where}")
def test_main_is_a_twin_of_main_in_every_locale(project, tmp_path,
                                                 child_locale):
    """#896's twin, in every locale: HEAD on `Main`, `main` not there. The
    three twin lines and the rename, byte for byte as on cb9ed806."""
    where, changes = child_locale
    pin = pins(project)
    spec = project / "spec"
    git("branch", "-q", "-D", "main", cwd=spec)
    git("checkout", "-q", "-b", "Main", pin["spec"], cwd=spec)

    lines = step_a(project, tmp_path, changes)
    assert lines == [
        *twin_lines(f"branch main does not exist (the pin is "
                    f"{pin['spec'][:12]})", "the checkout is on", "Main",
                    "main", MAKE,
                    rename_line("Main", "main", ("Main", "Main-kept"))),
        placed("code", "main", pin["code"])], lines
    assert on_the_branch(spec) == (b"refs/heads/Main\n", pin["spec"])


@pytest.mark.parametrize("child_locale", ["utf-8"], indirect=True,
                         ids=["CONTROL-utf-8"])
def test_the_nfd_spelling_is_a_twin_of_the_nfc_under_utf_8(
        project, tmp_path, child_locale):
    """#962's twin under UTF-8: HEAD on the NFD spelling of `caf` U+00E9, the
    NFC branch not there. The three lines of a twin in case or Unicode form,
    byte for byte as on cb9ed806. Skips on a disk that reads the two
    spellings as one file."""
    where, changes = child_locale
    nfd = "cafe\u0301"
    # Named by their UTF-8 bytes, so a pytest in any locale names them.
    (tmp_path / os.fsdecode(b"caf\xc3\xa9")).write_bytes(b"")
    if (tmp_path / os.fsdecode(nfd.encode("utf-8"))).exists():
        pytest.skip("this disk reads NFC and NFD as one file")
    printed, raw = tracking(project, tmp_path, "nfc", where)
    pin = pins(project)
    spec = project / "spec"
    git("checkout", "-q", "-b", os.fsdecode(nfd.encode("utf-8")), pin["spec"],
        cwd=spec)

    lines = step_a(project, tmp_path, changes)
    assert lines == [
        *twin_lines(f"branch {printed} does not exist (the pin is "
                    f"{pin['spec'][:12]})", "the checkout is on", nfd,
                    printed, MAKE,
                    rename_line(nfd, printed, (f"'{nfd}'", f"'{nfd}-kept'"),
                                FORM), FORM),
        created("code", printed, pin["code"])], lines
    assert on_the_branch(spec) == (
        b"refs/heads/" + nfd.encode("utf-8") + b"\n", pin["spec"])
    assert raw == b"caf\xc3\xa9"


@pytest.mark.parametrize("child_locale", [
    pytest.param("latin1", id="latin1"),
    pytest.param("utf-8", id="CONTROL-utf-8")], indirect=True)
def test_a_latin1_capital_is_a_twin_in_every_locale(project, tmp_path,
                                                     child_locale):
    """`tracking_branch: "tb\\xe4x"`, U+00E4 itself, and HEAD on U+00C4's
    spelling in the child's own codec, the branch not there (#1306): the
    twin lines in both. Under UTF-8 the bytes are UTF-8, `tb<c3 84>x`
    beside `tb<c3 a4>x`. Under Latin-1 they are `tb<c4>x` beside `tb<e4>x`,
    the very bytes of the 0xC4 and 0xE4 row, which git for Windows names
    `tb` U+00C4 `x` and `tb` U+00E4 `x` on NTFS, one file there. Passes on
    cb9ed806 too, by its text compare. Folded as UTF-8 alone, Latin-1 made
    the branch beside the twin and said `the leg was on` it (r1308a's F1 on
    #1308)."""
    where, changes = child_locale
    printed, raw = tracking(project, tmp_path, "u00e4-itself", where)
    capital = "tb\u00c4x"
    twin = capital.encode(CODECS[where])
    pin = pins(project)
    spec = project / "spec"
    git("checkout", "-q", "-b", os.fsdecode(twin), pin["spec"], cwd=spec)
    words = ((f"'{capital}'", f"'{capital}-kept'") if where == "utf-8" else
             (printf_word("tb\\304x"), printf_word("tb\\304x-kept")))

    lines = step_a(project, tmp_path, changes)
    assert lines == [
        *twin_lines(f"branch {printed} does not exist (the pin is "
                    f"{pin['spec'][:12]})", "the checkout is on", capital,
                    printed, MAKE, rename_line(capital, printed, words)),
        created("code", printed, pin["code"])], lines
    assert shell_reads(lines[2]) == [b"-C", b"spec", b"branch", b"-m", twin,
                                     twin + b"-kept"]
    assert on_the_branch(spec) == (b"refs/heads/" + twin + b"\n", pin["spec"])
    assert raw == {"latin1": b"tb\xe4x", "utf-8": b"tb\xc3\xa4x"}[where]


class LegacyWindowsCodePage:
    """`os` as `bootstrap.py` reads it on Windows under
    `PYTHONLEGACYWINDOWSFSENCODING=1`: `nt`, with `os.fsencode` and
    `os.fsdecode` as `mbcs` with `replace`, `cp1252` standing in for the
    code page, so a lone surrogate is written as the one byte `?`.
    Everything else is this system's `os`. An emulation, as
    `tests/test_bootstrap_pasteable_lines.py`'s `LegacyMbcsOs` is: Windows
    is not run here."""

    name = "nt"

    @staticmethod
    def fsencode(name: str) -> bytes:
        return name.encode("cp1252", "replace")

    @staticmethod
    def fsdecode(raw: bytes) -> str:
        return raw.decode("cp1252", "replace")

    def __getattr__(self, attr: str):
        return getattr(os, attr)


def test_a_name_git_cannot_be_handed_is_compared_as_its_text(monkeypatch):
    """On Windows under `PYTHONLEGACYWINDOWSFSENCODING=1` (emulated),
    `_argument_fault` lets `tb\\udcffx` through, since `replace` writes
    U+DCFF as `?`, one byte; but git is handed UTF-8 there
    (`_handed_to_git`), which has no bytes for it. `_branch_ref` compares
    HEAD's ref with the name's text, as every check did before #1283, and
    as `_paste_word` keeps its text. Without the fallback, `_branch_ref`
    raised `UnicodeEncodeError` instead, out of step (a), after
    `create_at_pin`'s `checkout -b` had run. A name git can be handed is
    still read back as `_head_of` reads git's UTF-8 in that mode: `caf`
    U+00E9 as the code page reads its two bytes."""
    module = load_without_bytecode(ASSEMBLY_TEMPLATE,
                                   "bootstrap_one_byte_locale")
    monkeypatch.setattr(module, "os", LegacyWindowsCodePage())
    assert module._argument_fault("tb\udcffx") is None
    assert module._branch_ref("tb\udcffx") == "refs/heads/tb\udcffx"
    assert module._branch_ref("caf\xe9") == "refs/heads/caf\xc3\xa9"


def test_a_twin_git_cannot_be_handed_is_folded_as_its_text(monkeypatch,
                                                           capsys):
    """The twin path in the same emulated mode (#1306): `_folded_twin` and
    `_twin_words` fold the bytes `_handed_to_git` gives, which have no UTF-8
    for `tb\\udcffx`, so each folds the names as their text, as every check
    did before, and raises nothing; `_folded_spelling` and the lines it
    leads to raise nothing either. A name git can be handed is folded as
    its UTF-8, the bytes git stores there, which `_heads` reads back as the
    text it was (`CAF` U+00C9 for `caf` U+00E9), and not as the code page
    writes it."""
    module = load_without_bytecode(ASSEMBLY_TEMPLATE,
                                   "bootstrap_one_byte_locale")
    monkeypatch.setattr(module, "os", LegacyWindowsCodePage())
    monkeypatch.setattr(module, "_heads", lambda sub: [
        "refs/heads/main", "refs/heads/TB\udcffx"])
    assert module._folded_twin("refs/heads/TB\udcffx", "tb\udcffx") is True
    assert module._folded_twin("refs/heads/tb\udcffx", "tb\udcffx") is False
    assert module._twin_words("TB\udcffx", "tb\udcffx")[0] == "only in case"
    assert module._folded_spelling(Path("spec"), "tb\udcffx") == "TB\udcffx"
    assert module._folded_twin("refs/heads/CAF\xc9", "caf\xe9") is True
    module._say_spelling(Path("spec"), "[spec] spec", "spec", "tb\udcffx",
                         "TB\udcffx", "branch tb\\udcffx does not exist")
    out = capsys.readouterr().out.splitlines()
    assert out[0] == ("  [spec] spec: branch tb\\udcffx does not exist, and "
                      "the leg has the branch TB\\udcffx, which differs from "
                      "tb\\udcffx only in case"), out


#: What `xutftowcsn` in git's `compat/mingw.c` makes of each name, read from
#: its code (#1306): the name git for Windows gives the file on NTFS.
XUTFTOWCSN = {
    b"tb\xc4x": "tb\u00c4x", b"tb\xe4x": "tb\u00e4x",
    b"tb\xc3\x84x": "tb\u00c4x", b"caf\xc3\xa9": "caf\u00e9",
    b"tb\x84x": "tb84x", b"\x80": "80", b"\x9f": "9f",
    b"\xa0": "\u00a0", b"\xff": "\u00ff", b"\xc2\x80": "\u0080",
    b"\xc0\xaf": "\u00c0\u00af", b"\xc3": "\u00c3",
    b"\xe0\x80\x80": "\u00e08080", b"\xe0\xa0\x80": "\u0800",
    b"\xe2\x82": "\u00e282", b"\xe4x": "\u00e4x",
    b"\xed\xa0\x80": "\ud800", b"\xed\xa0\x80\xed\xb0\x80": "\U00010000",
    b"\xf0\x90\x80\x80": "\U00010000", b"\xf4\x8f\xbf\xbf": "\U0010ffff",
    b"\xf4\x90\x80\x80": "\u00f4908080",
    b"\xf0\x8f\xbf\xbf": "\u00f08f\u00bf\u00bf",
    b"\xf0\x9f\x98": "\u00f09f98", b"\xf5\x80": "\u00f580",
}


def test_git_for_windows_names_each_file_as_xutftowcsn_does():
    """`_as_git_for_windows_names`, the second reading of a twin (#1306),
    against `XUTFTOWCSN`: valid UTF-8 as itself, a 4-byte form and a pair
    of 3-byte surrogates alike as the one character of a UTF-16 pair, a
    lone 3-byte surrogate as that unit, an overlong form, a truncated one
    and a lead past U+10FFFF byte by byte, a byte 0xA0 to 0xFF as U+00A0
    to U+00FF, and a byte 0x80 to 0x9F as two hex digits in small
    letters."""
    module = load_without_bytecode(ASSEMBLY_TEMPLATE,
                                   "bootstrap_one_byte_locale")
    assert {raw: module._as_git_for_windows_names(raw)
            for raw in XUTFTOWCSN} == XUTFTOWCSN
