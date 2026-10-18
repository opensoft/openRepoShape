# SPDX-License-Identifier: Apache-2.0
"""`make siblings` either clones each member where it says, or stops before
cloning with a move that runs as typed, and no manifest or disk text ends it
in a traceback or a forged line (#690).

Six lines of `templates/family-root/scripts/siblings.py`, a pinned copy in
every family holder, fixed in one change and one re-pin:

* AN EXISTING STAGING NAME (#578's line). The parent-folder warning printed
  its `mv` through `<Family>.holder` or `<Family>.folder` whatever was there,
  and `mv` onto a folder moves INTO it: with `<t>/InkRouter.holder` a folder
  already, the three printed lines all exited 0 and left the holder at
  `<t>/InkRouter/InkRouter/InkRouter`, one level too deep. The staging name
  is now the first of `.holder`, `.holder.1`, ... at which nothing is.
* A DANGLING LINK NAMED AFTER THE FAMILY (#578's line). `exists` follows the
  link, so the staged move was printed, its first `mv` ran, and `mkdir -p`
  failed `File exists` with the holder half moved. The link is now named, to
  be moved aside first.
* A `project:` OR URL HOLDING A NUL OR A LONE SURROGATE (R454 O1). `git
  clone` was handed it: `UnicodeEncodeError` or `ValueError: embedded null
  byte`, a traceback, and the members after it never placed. It is now a
  finding, the dry run's too, and the other members go on.
* THE WARNING'S PROSE (R454 O2) printed the holder, the parent folder and the
  family raw on stderr: an ESC in a folder name reached the terminal. They
  are spelled; the `mv` lines stay as typed (#486's question).
* `.gitmodules` READ AS GIT READS IT (R432 O2, and lane 3's line on #473):
  `str.splitlines` cut a url at NEL or U+2028, and the split at the first
  `=` read no url for a section named `members/a=b`. It is now `git config
  -z --list`, as `validate-family.py` reads the file and #668 makes the
  doctor read it.
* A `tracking_branch:` THAT IS ONLY A TAG (#578's line): `git clone --branch`
  takes a tag and leaves the clone detached, under a line that said "on
  <name>, its tracking branch". A line after the clone now says so.

THE SAME FAMILY AS `test_family.py` (its module fixture, this module's own
instance), and the move asked in this process as
`test_family_siblings_placement.py` asks it, with that module's helpers. The
printed moves are RUN AS TYPED in a POSIX shell: `os.rename` onto an empty
folder replaces it where `mv` moves into it, so a rename would not show the
defect. Output is split at `\\n` alone, never `str.splitlines`, which breaks
a command line at the U+2028 one of these tests puts in it. Files are edited
as bytes. NO NETWORK: local bare remotes, and a dry run wherever a run of the
old code would have asked GitHub.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import REPO, clone_just_pushed, git, load_without_bytecode
from test_bootstrap_spelling import NEVER_RAW
from test_family import NAME, family, siblings  # noqa: F401
from test_family_siblings_placement import (  # noqa: F401
    branch_of, flat, holder_in, ignoring_case, link_or_skip, placement,
    stored,
)

#: The member whose row, mount or url a test bends; IRSS is left as it is,
#: so a run that goes on past IRRS is seen to.
BENT = "IRRS"
KEPT = "IRSS"
#: The row `family.py add` wrote for BENT.
ROW = ("  - project: IRRS\n    id: irrs\n    repository: InkRouter/IRRS\n"
       "    path: members/IRRS\n")
ESC = "\x1b"


def printed_moves(text: str) -> list[str]:
    """The `mv` and `mkdir -p` lines of the warning, as printed."""
    return [line.strip() for line in text.split("\n")
            if line.startswith(" " * 12) and line.strip()[:3] in
            ("mv ", "mkd")]


def moves(text: str) -> list[list[str]]:
    """The same lines, split as a POSIX shell splits them."""
    return [shlex.split(line) for line in printed_moves(text)]


def run_as_typed(lines: list[str]) -> None:
    """Each printed line run in a POSIX shell, as a person pastes it."""
    shell = shutil.which("sh")
    if shell is None:
        pytest.skip("no POSIX shell here to paste the printed move into")
    proc = subprocess.run([shell, "-e", "-c", "\n".join(lines)],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr


def edit(path: Path, old: str, new: str) -> None:
    """`old` replaced by `new` in `path`, which holds it exactly once; as
    bytes, so no newline is translated."""
    data = path.read_bytes()
    assert data.count(old.encode("utf-8")) == 1, data
    path.write_bytes(data.replace(old.encode("utf-8"), new.encode("utf-8")))


def gitmodules_url(holder: Path, project: str) -> str:
    """The url `.gitmodules` gives `members/<project>`, as git reads it."""
    return git("config", "-f", ".gitmodules", "--get",
               f"submodule.members/{project}.url",
               cwd=holder).stdout.rstrip("\n")


def table_row(stdout: str, project: str) -> list[str]:
    """The layout table's `sibling` row for `project`, split."""
    rows = [line.split() for line in stdout.split("\n")
            if line.split()[:2] == ["sibling", project]]
    assert len(rows) == 1, stdout
    return rows[0]


# --- an existing staging name ------------------------------------------------


@pytest.mark.parametrize("taken, staged", [
    pytest.param(["a folder"], ".holder.1", id="a-folder"),
    pytest.param(["a link to nothing"], ".holder.1", id="a-link-to-nothing"),
    pytest.param(["a folder", "a folder"], ".holder.2", id="two-names"),
])
def test_a_staging_name_something_holds_is_passed_over(family, tmp_path,
                                                       taken, staged):
    """The issue's probe: the holder at `<t>/t/InkRouter` and
    `<t>/InkRouter.holder` already a folder. The printed move passes through
    the first staging name nothing holds, runs as typed, and leaves the
    holder at `<t>/InkRouter/InkRouter`, where the next run passes; what
    held the names is untouched. A link to nothing holds a name too, and so
    does a second name taken after the first."""
    holder = holder_in(family, tmp_path / "t")
    held = [tmp_path / (f"{NAME}.holder" + (f".{n}" if n else ""))
            for n in range(len(taken))]
    for what, path in zip(taken, held):
        if what == "a folder":
            path.mkdir()
            (path / "keep.txt").write_bytes(b"mine\n")
        else:
            link_or_skip(path, tmp_path / "nowhere")

    result = siblings(holder)
    assert result.returncode == 1, result.stdout + result.stderr
    wanted = tmp_path / NAME
    passing = tmp_path / f"{NAME}{staged}"
    assert moves(result.stderr) == [
        ["mv", str(holder), str(passing)], ["mkdir", "-p", str(wanted)],
        ["mv", str(passing), str(wanted / NAME)]]
    assert holder.is_dir(), "the run moves nothing"

    run_as_typed(printed_moves(result.stderr))
    assert (wanted / NAME / "family.yaml").is_file()
    for what, path in zip(taken, held):
        if what == "a folder":
            assert sorted(os.listdir(path)) == ["keep.txt"], path
        else:
            assert os.path.islink(path), path
    again = siblings(wanted / NAME, "--dry-run")
    assert again.returncode == 0, again.stdout + again.stderr


def ignoring_case_through_os_path(patched) -> None:
    """`ignoring_case`, with `os.path.lexists` and `os.path.exists` answering
    as it does: the staging name and the dangling link are asked of
    `os.path`, which a disk that ignores case answers alike."""
    ignoring_case(patched)
    patched.setattr(os.path, "lexists", lambda path: stored(path) is not None)
    patched.setattr(os.path, "exists", lambda path: stored(path) is not None)


@pytest.mark.parametrize("spelling", [
    pytest.param(f"{NAME}.folder", id="same-case"),
    pytest.param(f"{NAME.lower()}.folder", id="another-case"),
])
def test_a_folder_staging_name_something_holds_is_passed_over(
        placement, monkeypatch, tmp_path, spelling):
    """macOS and Windows, simulated: the holder in `inkrouter/`, renamed
    through `InkRouter.folder`, which R578's writer found already there: the
    move left `InkRouter/inkrouter/InkRouter`. Held under either case, the
    name is passed over on a disk that ignores case, and the two lines run
    as typed."""
    folder = tmp_path / NAME.lower()
    root = folder / NAME
    root.mkdir(parents=True)
    there = tmp_path / spelling
    there.mkdir()
    (there / "keep.txt").write_bytes(b"mine\n")
    with monkeypatch.context() as patched:
        ignoring_case_through_os_path(patched)
        warning = placement.parent_folder_warning(root, NAME)
    passing = tmp_path / f"{NAME}.folder.1"
    assert moves(warning) == [["mv", str(folder), str(passing)],
                              ["mv", str(passing), str(tmp_path / NAME)]]
    assert "link to nothing" not in warning

    run_as_typed(printed_moves(warning))
    assert (tmp_path / NAME / NAME).is_dir()
    assert sorted(os.listdir(there)) == ["keep.txt"]


# --- a dangling link named after the family ----------------------------------


def test_a_link_to_nothing_named_after_the_family_is_named_first(family,
                                                                 tmp_path):
    """The issue's probe: `<t>/InkRouter` a link to nothing, the holder at
    `<t>/t/InkRouter`. The run, and its dry run alike, stop with the link
    named before the moves and nothing moved; moved aside, the printed
    lines run as typed and the next run passes."""
    holder = holder_in(family, tmp_path / "t")
    link = tmp_path / NAME
    link_or_skip(link, tmp_path / "nowhere")
    staged = tmp_path / f"{NAME}.holder"
    for args in ((), ("--dry-run",)):
        result = siblings(holder, *args)
        assert result.returncode == 1, result.stdout + result.stderr
        assert "Traceback" not in result.stderr, result.stderr
        assert (f"First move {link} aside: it is a link to nothing, named "
                "after the family, and in the way of the move. Then: mv "
                in flat(result.stderr)), result.stderr
        assert moves(result.stderr) == [
            ["mv", str(holder), str(staged)], ["mkdir", "-p", str(link)],
            ["mv", str(staged), str(link / NAME)]]
        assert os.path.islink(link), "nothing moved"
        assert holder.is_dir(), "nothing moved"

    os.rename(link, tmp_path / "moved-aside")
    run_as_typed(printed_moves(result.stderr))
    assert (link / NAME / "family.yaml").is_file()
    again = siblings(link / NAME, "--dry-run")
    assert again.returncode == 0, again.stdout + again.stderr


# --- a row no command can be given -------------------------------------------

#: `(the row written for BENT, the name its lines print, what the finding
#: says holds the character)`: R454's two `project:` values, and a url built
#: from a `repository:` holding a NUL, for a row whose path `.gitmodules`
#: does not give (so `git clone` was handed the GitHub url it builds).
UNARGUABLE = [
    pytest.param(ROW.replace("project: IRRS", r'project: "IR\ud83dRS"'),
                 r"IR\ud83dRS", "its `project:` in family.yaml holds U+D83D, "
                 "a lone surrogate", id="project-lone-surrogate"),
    pytest.param(ROW.replace("project: IRRS", r'project: "IR\x00RS"'),
                 r"IR\x00RS", "its `project:` in family.yaml holds U+0000, a "
                 "NUL", id="project-nul"),
    pytest.param(ROW.replace("repository: InkRouter/IRRS",
                             r'repository: "InkRouter/IR\x00RS"')
                 .replace("path: members/IRRS", "path: members/Elsewhere"),
                 BENT, r"its url https://github.com/InkRouter/IR\x00RS.git "
                 "(family.yaml repository:) holds U+0000, a NUL",
                 id="url-nul"),
]


@pytest.mark.parametrize("row, shown, holds", UNARGUABLE)
def test_a_row_no_command_can_be_given_is_a_finding_and_the_rest_go_on(
        family, tmp_path, row, shown, holds):
    """`make siblings` over such a row exited 1 in a traceback at `git
    clone`, and IRSS, after it, was never cloned; the dry run said `would
    clone`. Both now name the row in one finding and exit 1, nothing is
    made for it, and the real run still clones IRSS."""
    holder = holder_in(family, tmp_path / NAME)
    edit(holder / "family.yaml", ROW, row)
    finding = (f"FINDING {shown}: {holds}, which no command can be given as "
               "an argument, so nothing was cloned or fetched for this "
               "member: git was never run with it.")
    for args, made in ((("--dry-run",), [NAME]), ((), sorted([NAME, KEPT]))):
        result = siblings(holder, *args)
        assert result.returncode == 1, result.stdout + result.stderr
        assert "Traceback" not in result.stderr, result.stderr
        assert finding in result.stderr.split("\n"), result.stderr
        assert table_row(result.stdout, shown) == [
            "sibling", shown, "NOT", "AN", "ARGUMENT", "-"]
        assert sorted(os.listdir(holder.parent)) == made
    assert branch_of(holder.parent / KEPT) == "main"


@pytest.mark.parametrize("value, fault", [
    pytest.param("IRRS", None, id="plain"),
    pytest.param("IR\x00RS", "U+0000, a NUL", id="nul"),
    pytest.param("IR\ud83dRS", "U+D83D, a lone surrogate",
                 id="lone-surrogate"),
    pytest.param("IR\udcffRS", None, marks=pytest.mark.skipif(
        os.name == "nt", reason="Windows' os.fsencode writes three bytes for "
        "every surrogate, so none is one byte of a name there"),
        id="one-byte-of-a-posix-name"),
])
def test_the_argument_rule_is_bootstraps(placement, value, fault):
    """#455's rule, as `make bootstrap` asks it of a branch: a NUL, and a
    surrogate `os.fsencode` cannot write as one byte. A name that is not
    UTF-8 on POSIX (U+DC80 to U+DCFF) is still handed on, as before."""
    assert placement.argument_fault(value) == fault


# --- the warning's prose is spelled ------------------------------------------


def test_the_warning_spells_the_holder_and_the_folder_it_names(
        family, tmp_path):
    """R454's probe: a parent folder named `x<ESC>[31my`. Lines 2 and 4 of
    the warning carried the raw ESC; they now spell it, and the `mv` line,
    which a person pastes, is the one line that still holds it, as typed."""
    if os.name == "nt":
        pytest.skip("a Windows disk holds no ESC in a folder name")
    holder = holder_in(family, tmp_path / f"x{ESC}[31my")
    escaped = "\\x1b"
    shown_root = str(holder).replace(ESC, escaped)
    shown_folder = str(holder.parent).replace(ESC, escaped)
    result = siblings(holder)
    assert result.returncode == 1, result.stdout + result.stderr
    lines = result.stderr.split("\n")
    assert lines[1] == (f"        {shown_root} should sit in a plain folder "
                        f"named {NAME}, beside the members'"), lines
    assert lines[3] == ("        NOTHING WAS CLONED: a member cloned now "
                        f"would land in {shown_folder}, and"), lines
    raw = [line.strip() for line in lines if ESC in line]
    assert raw == printed_moves(result.stderr)[:1], raw
    assert moves(result.stderr)[0] == [
        "mv", str(holder), str(tmp_path / f"{NAME}.holder")]
    assert not NEVER_RAW & set(result.stdout), result.stdout


def test_the_warning_spells_the_family_it_names(family, tmp_path):
    """And the family, the basename of `repository:`, which the first line
    shows in its `repr` and the summary under it spelled: line 2 printed it
    raw. A U+2028 in it now prints as its escape on every line but the
    commands, which keep it as typed."""
    holder = holder_in(family, tmp_path / NAME)
    edit(holder / "family.yaml", f"\nrepository: {NAME}/{NAME}\n",
         f'\nrepository: "{NAME}/Ink\\u2028Router"\n')
    result = siblings(holder, "--dry-run")
    assert result.returncode == 1, result.stdout + result.stderr
    commands = printed_moves(result.stderr)
    prose = [line for line in result.stderr.split("\n")
             if line.strip() not in commands]
    assert prose[0] == (f"WARNING the holder's parent folder is '{NAME}', "
                        r"not 'Ink\u2028Router'."), prose
    assert prose[1].endswith(r" should sit in a plain folder named "
                             r"Ink\u2028Router, beside the members'"), prose
    assert not NEVER_RAW & set("\n".join(prose)), prose
    family_folder = tmp_path / "Ink\u2028Router"
    assert moves(result.stderr) == [
        ["mkdir", "-p", str(family_folder)],
        ["mv", str(holder), str(family_folder / "Ink\u2028Router")]]


# --- .gitmodules read as git reads it ----------------------------------------

#: Section NAMES, as the bytes between the header's quotes, each holding a
#: character a reading of git's listing has cut at: a space, a dot, a quote
#: (escaped in the header) and an `=` (lane 3's `members/a=b`), the same four
#: as #668's corpus for the doctor; then lane 3's two more on #690
#: (issuecomment-6232404184 and -6232689453): the name `a=b` as it wrote it,
#: whole, and a CR, which `str.splitlines` cut a key at where git keeps it.
NAMES = [
    pytest.param(b"members/My IRRS", id="space"),
    pytest.param(b"members/IRRS.v2", id="dot"),
    pytest.param(b'members/\\"IRRS\\"', id="quote"),
    pytest.param(b"members/a=b", id="equals"),
    pytest.param(b"a=b", id="equals-bare"),
    pytest.param(b"members/q\rx", id="cr"),
]
#: A url through a directory holding each line break `str.splitlines` knows
#: besides `\n` and `\r`, all of which git keeps in a value: VT, FF, FS, GS,
#: RS, NEL, U+2028 and U+2029, in UTF-8 (R432 O2's list).
BREAKS = [pytest.param(f"caf{char}e".encode("utf-8"),
                       id=f"U+{ord(char):04X}")
          for char in "\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029"]


def write_section(folder: Path, name: bytes, directory: bytes) -> bytes:
    """A `.gitmodules` in `folder` whose one section, NAMED `name`, mounts
    `members/IRRS` from `/r/<directory>/IRRS.git`; that url, as written."""
    url = b"/r/" + directory + b"/IRRS.git"
    (folder / ".gitmodules").write_bytes(
        b'[submodule "' + name + b'"]\n\tpath = members/IRRS\n\turl = '
        + url + b"\n")
    return url


def one_section(tmp_path: Path, name: bytes, directory: bytes) -> str:
    """`write_section`, and its url as git reads it by its exact key;
    skipped where git does not keep it whole."""
    url = write_section(tmp_path, name, directory)
    key = "submodule." + name.replace(b'\\"', b'"').decode("ascii") + ".url"
    read = subprocess.run(["git", "config", "-f", ".gitmodules", "--get",
                           key], cwd=str(tmp_path), capture_output=True,
                          check=False)
    if read.stdout.rstrip(b"\n") != url:
        pytest.skip(f"git here reads {key} as {read.stdout!r}, not {url!r}")
    return url.decode("utf-8")


@pytest.mark.parametrize("name", NAMES)
def test_a_section_name_git_reads_whole_gives_its_url(placement, tmp_path,
                                                      name):
    """`members/a=b` gave `{}`: the split at the first `=` cut the key. Each
    name now gives the mount its url, as git reads it."""
    url = one_section(tmp_path, name, b"IRRS")
    assert placement.submodule_urls(tmp_path) == {"members/IRRS": url}


@pytest.mark.parametrize("directory", BREAKS)
def test_a_url_holding_a_line_break_git_keeps_is_read_whole(placement,
                                                            tmp_path,
                                                            directory):
    """R432 O2: the url was cut at the break, `/r/caf`."""
    url = one_section(tmp_path, b"members/IRRS", directory)
    assert placement.submodule_urls(tmp_path) == {"members/IRRS": url}


def test_a_cr_in_a_section_name_cuts_no_key_of_its_section(placement,
                                                           tmp_path):
    """Lane 3's second case on #690 (issuecomment-6232689453): `[submodule
    "q\\rx"]` holding `update = bogus`. `str.splitlines` cut the listing at
    the CR, `submodule.q` from `x.path`, so the section was read as no
    section at all and the `update` git refuses never reached a reader that
    looks for it (lane 3's #733). Git keeps the key whole, and so does the
    `-z` reading: the section with the CR is read exactly as the same
    section without it. What the reading then does with a value git refuses
    is #733's rule, not this one, so the two files are compared, not the
    urls pinned."""
    irrs = (b'[submodule "members/IRRS"]\n\tpath = members/IRRS\n'
            b"\turl = /r/IRRS.git\n")
    body = b"\tpath = members/q\n\turl = /r/q.git\n\tupdate = bogus\n"
    read = {}
    for label, name in (("cr", b"q\rx"), ("plain", b"qx")):
        folder = tmp_path / label
        folder.mkdir()
        (folder / ".gitmodules").write_bytes(
            irrs + b'[submodule "' + name + b'"]\n' + body)
        # Git has the section whole: each key by its exact name, CR and all.
        for field, expect in (("url", "/r/q.git"), ("update", "bogus")):
            got = git("config", "-f", ".gitmodules", "--get",
                      f"submodule.{name.decode('ascii')}.{field}",
                      cwd=folder)
            assert got.stdout.rstrip("\n") == expect, (label, field)
        read[label] = placement.submodule_urls(folder)
    assert read["cr"] == read["plain"], read


def test_make_siblings_clones_from_a_url_holding_nel(family, tmp_path):
    """A real run, the member's remote at `caf<NEL>e/IRRS.git`: cut at the
    NEL, the clone of `<t>/caf` failed (`CLONE FAILED`). It now clones from
    the whole url, which is the clone's `origin`."""
    holder = holder_in(family, tmp_path / NAME)
    remote = tmp_path / "caf\u0085e" / "IRRS.git"
    try:
        remote.parent.mkdir()
    except OSError as refused:
        pytest.skip(f"this disk holds no NEL in a folder name: {refused}")
    made = clone_just_pushed(family["remotes"] / "IRRS.git", remote,
                             recurse=False, bare=True)
    assert made.returncode == 0, made.stderr
    config = holder / ".gitmodules"
    rewritten, count = re.subn(
        rb"(?m)^(\turl = ).*/IRRS\.git$",
        lambda found: found.group(1) + remote.as_posix().encode("utf-8"),
        config.read_bytes())
    assert count == 1
    config.write_bytes(rewritten)

    result = siblings(holder)
    assert result.returncode == 0, result.stdout + result.stderr
    clone = holder.parent / BENT
    assert git("remote", "get-url", "origin",
               cwd=clone).stdout.rstrip("\n") == remote.as_posix()
    assert table_row(result.stdout, BENT)[2] == "cloned"
    assert not NEVER_RAW & set(result.stdout), result.stdout


#: IRRS's `.gitmodules` url as written in the file, and as the member's own
#: lines spell it: a line feed (`\n` in a quoted value), and one beside an
#: ESC, which git quotes as a `?`. Each holds a line a forger could write.
FORGED_URLS = {
    "line-feed": (b'"/r/nowhere\\nFINDING ' + KEPT.encode() + b': forged"',
                  f"/r/nowhere\\nFINDING {KEPT}: forged"),
    "line-feed-and-esc": (
        b'"/r/no\x1b[31mwhere\\nFINDING ' + KEPT.encode() + b': forged"',
        f"/r/no\\x1b[31mwhere\\nFINDING {KEPT}: forged"),
}


def siblings_over_url(family: dict, parent: Path, url: bytes):
    """`make siblings` over a holder whose IRRS url is `url`, as written."""
    holder = holder_in(family, parent / NAME)
    config = holder / ".gitmodules"
    rewritten, count = re.subn(
        rb"(?m)^(\turl = ).*/IRRS\.git$",
        lambda found: found.group(1) + url, config.read_bytes())
    assert count == 1
    config.write_bytes(rewritten)
    return siblings(holder)


@pytest.mark.parametrize("url", [url for url, _ in FORGED_URLS.values()],
                         ids=list(FORGED_URLS))
def test_a_url_holding_a_line_feed_forges_no_finding_line(family, tmp_path,
                                                          url):
    """Lane 1's review of #805: git's clone error quotes the url raw, line
    feed and all. Read whole since #690, a `.gitmodules` url holding a line
    feed and `FINDING IRSS: ...` put that line at column 0 of IRRS's
    finding, where main, which cut the url at the line feed, never had it.
    The only FINDING line is IRRS's own, and no raw ESC reaches stderr."""
    result = siblings_over_url(family, tmp_path, url)
    assert result.returncode == 1, result.stdout + result.stderr
    findings = [line for line in result.stderr.split("\n")
                if line.startswith("FINDING ")]
    assert findings == [f"FINDING {BENT}: git clone exited 128:"], \
        result.stderr
    assert not NEVER_RAW & set(result.stderr), result.stderr


def test_a_url_longer_than_gits_message_forges_no_finding_line(family,
                                                               tmp_path):
    """git writes a `die` message into 4096 bytes, so a url longer than that
    is quoted cut short, in neither form `said_of_url` looks for."""
    url = (b'"/r/nowhere\\nFINDING ' + KEPT.encode() + b': forged/'
           + b"/".join([b"a" * 200] * 30) + b'"')
    result = siblings_over_url(family, tmp_path, url)
    assert result.returncode == 1, result.stdout + result.stderr
    findings = [line for line in result.stderr.split("\n")
                if line.startswith("FINDING ")]
    assert findings == [f"FINDING {BENT}: git clone exited 128:"], \
        result.stderr


@pytest.mark.parametrize("url, shown", FORGED_URLS.values(),
                         ids=list(FORGED_URLS))
def test_the_clone_failure_names_a_line_feed_url_spelled(family, tmp_path,
                                                         url, shown):
    """The same relay, read the other way: git's text still names the url
    it could not clone, written as the lines above it write it. git quotes
    an ESC as a `?`, so the url is found in that form too."""
    result = siblings_over_url(family, tmp_path, url)
    assert f"'{shown}'" in result.stderr, result.stderr


def test_a_failed_fetch_forges_no_finding_line(family, tmp_path):
    """The other relay of git's text (#805's review): a clone made from a
    url holding a line feed (a folder named `x<LF>FINDING IRSS: ...`, which
    only the whole-url read can reach) has it for its `origin`, and when
    its fetch fails git quotes the origin raw. The re-run's stderr holds no
    line of the folder's name at column 0."""
    holder = holder_in(family, tmp_path / NAME)
    remote = tmp_path / f"x\nFINDING {KEPT}: forged" / "IRRS.git"
    try:
        remote.parent.mkdir()
    except OSError as refused:
        pytest.skip(f"this disk holds no line feed in a name: {refused}")
    made = clone_just_pushed(family["remotes"] / "IRRS.git", remote,
                             recurse=False, bare=True)
    assert made.returncode == 0, made.stderr
    config = holder / ".gitmodules"
    written = b'"' + remote.as_posix().replace("\n", "\\n").encode() + b'"'
    rewritten, count = re.subn(
        rb"(?m)^(\turl = ).*/IRRS\.git$",
        lambda found: found.group(1) + written, config.read_bytes())
    assert count == 1
    config.write_bytes(rewritten)
    first = siblings(holder)
    assert first.returncode == 0, first.stdout + first.stderr

    os.rename(remote.parent, tmp_path / "gone")
    result = siblings(holder)
    assert f"[{BENT}] fetch exited 128" in result.stderr, result.stderr
    assert f"x\\nFINDING {KEPT}: forged/IRRS.git'" in result.stderr, \
        result.stderr
    assert not [line for line in result.stderr.split("\n")
                if line.startswith("FINDING ")], result.stderr


@pytest.mark.parametrize("name", ["members/a=b", "a=b"])
def test_a_section_named_with_an_equals_sign_mounts_from_gitmodules(
        family, tmp_path, name):
    """Lane 3's `[submodule "members/a=b"]`, and `[submodule "a=b"]` as it
    asked for the row on #690 (issuecomment-6232404184): no url was read for
    it, so the dry run named `https://github.com/InkRouter/IRRS.git
    (family.yaml repository:)`, the remote this holder is not pinned
    against. It now names the url `.gitmodules` gives, as git, the doctor and
    CI mount it. A dry run, so the old reading never asks GitHub."""
    holder = holder_in(family, tmp_path / NAME)
    url = gitmodules_url(holder, BENT)
    edit(holder / ".gitmodules", f'[submodule "members/{BENT}"]',
         f'[submodule "{name}"]')
    result = siblings(holder, "--dry-run")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (f"  [{BENT}] would clone {url} (.gitmodules) -> "
            f"{holder.parent / BENT}, on main, its tracking branch "
            f"(members/{BENT}/project.yaml)") in result.stdout.split("\n")


# --- one reading, the doctor's and make siblings' (#146, #668) ---------------


@pytest.fixture(scope="module")
def doctor():
    """`shape-doctor.py`, as a module, for its `submodule_config`: the
    doctor's half of the one reading. Lane 3's #668 (PR #700) makes it `git
    config -z --list`, cut as this file's half cuts it; whichever of the two
    lands second adds this parity (#473, issuecomment-6216310747). Until
    #668's `gitmodules_listing` is in the doctor here, the parity is
    skipped, by name: the doctor's old reading cuts the same corpus."""
    module = load_without_bytecode(REPO / "shape-doctor.py",
                                   "siblings_inputs_doctor")
    if not hasattr(module, "gitmodules_listing"):
        pytest.skip("shape-doctor.py here reads `.gitmodules` with "
                    "--get-regexp; the parity runs once #668 (PR #700) is in")
    return module


#: One corpus for both readers: the names and the breaks above, and #668's
#: section NAMED in Latin-1, which a UTF-8 locale kept the doctor's
#: `--get-regexp` from matching.
CORPUS = ([pytest.param(name.values[0], b"IRRS", id=f"name-{name.id}")
           for name in NAMES]
          + [pytest.param(b"members/IRRS", directory.values[0],
                          id=f"url-{directory.id}") for directory in BREAKS]
          + [pytest.param(b"members/caf\xe9", b"IRRS", id="name-latin-1")])


@pytest.mark.parametrize("name, directory", CORPUS)
def test_the_doctor_and_make_siblings_read_one_url_for_one_mount(
        placement, doctor, tmp_path, monkeypatch, name, directory):
    """The doctor's `members` row and `make siblings` must name one url for
    one member, or they disagree about one directory (#146): read through
    both, every case of the corpus gives the same `{path: url}`, under a
    UTF-8 locale."""
    monkeypatch.setenv("LC_ALL", "C.UTF-8")
    write_section(tmp_path, name, directory)
    config = doctor.submodule_config(tmp_path)
    read = {fields["path"]: fields["url"] for fields in config.values()}
    assert read == placement.submodule_urls(tmp_path), config
    assert list(read) == ["members/IRRS"], config


#: Two sections whose NAMES differ only in bytes that are not UTF-8, which
#: git keeps apart (RV775r4 on #775): Latin-1 `\xe9` and `\xe8`, then `\xe9`
#: and the UTF-8 of U+FFFD, the character a replacing decode makes of it.
#: Each `.gitmodules`, for gitlinks at `p` and `q`, with the `{path: url}`
#: `git submodule init` registers for it. `make siblings` decoded the names
#: with the replacement, so the two were one section: it gave `q` alone,
#: and where one gives the path and the other the url, a url git does not
#: mount (`No url found`).
NAMES_APART_IN_BYTES = [
    pytest.param(b'[submodule "caf\xe9"]\n\tpath = p\n\turl = /r/a.git\n'
                 b'[submodule "caf\xe8"]\n\tpath = q\n\turl = /r/b.git\n',
                 {"p": "/r/a.git", "q": "/r/b.git"}, id="latin-1-pair"),
    pytest.param(b'[submodule "caf\xe9"]\n\tpath = p\n\turl = /r/a.git\n'
                 b'[submodule "caf\xef\xbf\xbd"]\n\tpath = q\n'
                 b"\turl = /r/b.git\n",
                 {"p": "/r/a.git", "q": "/r/b.git"},
                 id="latin-1-and-u-fffd"),
    pytest.param(b'[submodule "caf\xe9"]\n\tpath = p\n'
                 b'[submodule "caf\xe8"]\n\turl = /r/b.git\n', {},
                 id="path-in-one-url-in-the-other"),
]


def configured_urls(root: Path) -> dict[bytes, bytes]:
    """`{name: url}` of each `submodule.<name>.url` in `root`'s own config,
    as git's bytes."""
    listing = subprocess.run(["git", "config", "-z", "--local", "--list"],
                             cwd=str(root), capture_output=True,
                             check=False).stdout
    urls = {}
    for record in listing.split(b"\0"):
        key, _, value = record.partition(b"\n")
        if key.startswith(b"submodule.") and key.endswith(b".url"):
            urls[key[len(b"submodule."):-len(b".url")]] = value
    return urls


def urls_git_registers(root: Path, paths: list[str]) -> dict[str, str]:
    """`{path: url}` for each of `paths` that `git submodule init -- <path>`
    registers a url for, in `root`'s own config; a path it says `No url
    found` for is left out."""
    registered = {}
    for path in paths:
        before = configured_urls(root)
        init = subprocess.run(["git", "submodule", "init", "--", path],
                              cwd=str(root), capture_output=True, check=False)
        if init.returncode != 0:
            continue
        new = [url for name, url in configured_urls(root).items()
               if before.get(name) != url]
        assert len(new) == 1, (path, new, init.stderr)
        registered[path] = new[0].decode("utf-8", "replace")
    return registered


@pytest.mark.parametrize("gitmodules, found", NAMES_APART_IN_BYTES)
def test_two_names_apart_only_in_bytes_not_utf8_stay_two_sections(
        placement, doctor, tmp_path, monkeypatch, gitmodules, found):
    """The doctor keeps a section's NAME as git's bytes (#732), and `make
    siblings` now does too, replacing a value alone (#432): both give the
    `{path: url}` git registers, under a UTF-8 locale."""
    monkeypatch.setenv("LC_ALL", "C.UTF-8")
    git("init", "-q", "-b", "main", ".", cwd=tmp_path)
    for path in ("p", "q"):
        git("update-index", "--add", "--cacheinfo",
            f"160000,{'1' * 40},{path}", cwd=tmp_path)
    (tmp_path / ".gitmodules").write_bytes(gitmodules)
    config = doctor.submodule_config(tmp_path)
    read = {fields["path"]: fields["url"] for fields in config.values()
            if "path" in fields and "url" in fields}
    assert read == placement.submodule_urls(tmp_path) == found, config
    assert urls_git_registers(tmp_path, ["p", "q"]) == found


# --- a tracking branch that is only a tag ------------------------------------

TAG = "v-track"


def test_a_tracking_branch_that_is_only_a_tag_says_the_clone_is_detached(
        family, tmp_path):
    """IRSS declares `tracking_branch: "v-track"`, a tag of its remote and no
    branch: `git clone --branch` took the tag and left the clone detached,
    under a line saying "on v-track, its tracking branch", exit 0. The run
    still places it, and a line after the clone says the name is no branch
    of that remote; IRRS, on a real branch, gets no such line."""
    git("tag", "-f", TAG, "main", cwd=family["remotes"] / f"{KEPT}.git")
    holder = holder_in(family, tmp_path / NAME)
    edit(holder / "members" / KEPT / "project.yaml",
         'tracking_branch: "main"', f'tracking_branch: "{TAG}"')
    url = gitmodules_url(holder, KEPT)

    result = siblings(holder)
    assert result.returncode == 0, result.stdout + result.stderr
    said = [line for line in result.stdout.split("\n")
            if "is not a branch of" in line]
    assert said == [f"  [{KEPT}] {TAG} is not a branch of {url} but a tag, "
                    "which git clone checks out DETACHED: this clone is on "
                    "no branch"], result.stdout
    assert table_row(result.stdout, KEPT)[2:] == ["cloned", "detached"]
    assert branch_of(holder.parent / KEPT) == "HEAD"
    assert branch_of(holder.parent / BENT) == "main"
