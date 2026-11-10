# SPDX-License-Identifier: Apache-2.0
"""`siblings.py` prints what a family says and never lets it end the run
(#454), and every file of a holder names its FOLDER as `make siblings` does,
after the REPOSITORY and never the display name (#629).

#454. `templates/family-root/scripts/siblings.py` (`make siblings`, `make
park`, `make resume`) opened each of its two reports with a plain `print` of
`family.yaml`'s `name:`, and printed every member row raw. `name: "a\\ud83db"`
is a string holding a lone surrogate, which no UTF-8 stdout can write, so the
run ended in a `UnicodeEncodeError` before a member was touched (`make park`,
which exists to save work, parked nothing); the line holds a literal dash, so
on a stdout that cannot hold it (`PYTHONIOENCODING=ascii`) it raised for EVERY
name; and a raw ESC or CR in a value reached the terminal as the control it is.
#391 gave both roots' `bootstrap.py` `escape_unencodable_stdout()` and
`spelled()`; `siblings.py` now does the same in the same way: the first is
`main`'s first statement, and `spelled` is applied to every value a line prints
that a manifest, a member row or a disk gave. The member's own `make` is still
handed the RAW target. The rows run `siblings.py` as BYTES under the stdouts
#391's rows use, decoded STRICTLY in the encoding the run was given, in a real
holder from `family.py init` into local bare remotes.

#629. `family.py init --family Quill --name QuillWorks` wrote a holder whose
README said `cd QuillWorks` and laid the folders out as
`QuillWorks/QuillWorks`, while `siblings.py`'s `family_folder_name` asks for
the REPOSITORY's name (`Quill`), so a holder laid out exactly as its README
said got `WARNING the holder's parent folder is 'QuillWorks', not 'Quill'` and
no clones. The README now names the folder with `{{FAMILY}}` (the repository's
name, the one value `family_folder_name` also reads), the display name stays
only the README's title, and `siblings.py` says which name it means on a line
of its own where the two differ. The rows build such a holder, follow its
README's layout, and run `make siblings` to a clone.

#1216. The layout table, and the dispatch's `(b) what ran`, padded each
member's name with a format width, which counts code points. Measured on
main 50ce8ab1, a UTF-8 stdout put the `state` of `\\u65e5\\u672c\\u8a9e`'s
rows 3 columns right of `state`, and `e\\u0301cole`'s 1 left; an ASCII
stdout, which writes each as its escapes, 15 and 5 right. A row now pads the
name by the columns it takes as stdout writes it. The rows read the table
raw, since `layout` collapses the pad they count.

NO NETWORK AND NO GITHUB: bare repositories in a temporary directory, a dry run
for every row that would otherwise clone from GitHub, and the session `gh`
guard (`tests/conftest.py`).
"""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO, clone_just_pushed, git, run_script
from test_bootstrap_spelling import (
    BYTE_NAMES, DASH, NAME_ROWS, NARROW, NEVER_RAW, edit, family_template,
    run,
)
from test_family import (
    FAMILY, MEMBERS, ORG, WORK_BRANCH, allow_file_protocol, scaffold_member,
)
from test_stdout_encoding import child_environ, run_tool_bytes, shown

#: The plain holder `family_template` makes: `name:` is its repository, no
#: members. (`test_bootstrap_spelling.FAMILY_NAME`, spelled here because that
#: module does not export it as a test of its own.)
PLAIN = "InkRouter"
#: The holder of #629: `--family` is the repository and the folder, `--name`
#: the display name.
QUILL = "Quill"
DISPLAY = "QuillWorks"
MEMBER = MEMBERS[0]

SIBLINGS = REPO / "templates" / "family-root" / "scripts" / "siblings.py"
README = REPO / "templates" / "family-root" / "README.md"
MAKE = shutil.which("make")
needs_make = pytest.mark.skipif(MAKE is None, reason="needs `make` on PATH")

#: No credential in the environment of a run, whatever the machine running the
#: suite exports: the `credential source:` line is part of what is compared.
NO_CREDENTIAL = {"SHAPE_LEGS_APP_TOKEN": "", "SHAPE_LEGS_TOKEN": ""}
#: `MAKE` as the interpreter, so a `--make <script>` run needs no `make`: the
#: member's "make" is `python <target>`, standing in the member's clone.
PYTHON_AS_MAKE = {"MAKE": sys.executable}


def in_family_folder(template: Path, tmp_path: Path, folder: str,
                     holder: str | None = None) -> Path:
    """A private copy of `template` at `<tmp>/<folder>/<holder>`: the family
    folder a holder is laid out in, which `make siblings` asks about."""
    target = tmp_path / folder / (holder or folder)
    target.parent.mkdir(parents=True)
    shutil.copytree(template, target, symlinks=True)
    return target


def sib(holder: Path, *args: str, tmp_path: Path,
        encoding: str = "utf-8:strict",
        changes: dict | None = None) -> tuple[int, str, str]:
    """`(exit, stdout, stderr)` of the holder's own `scripts/siblings.py`,
    standing in the holder, its stdout in `encoding`."""
    return run(holder / "scripts" / "siblings.py", *args, encoding=encoding,
               tmp_path=tmp_path, cwd=holder,
               changes={**allow_file_protocol(), **NO_CREDENTIAL,
                        **(changes or {})})


def header(printed: str, holder: Path, encoding: str) -> str:
    """The first line, whole: the dash is the file's own wording, so on a
    stdout that cannot hold it the dash is escaped too."""
    return shown(
        f"siblings: {printed} ({holder.resolve()}) {DASH} 0 member(s)",
        encoding)


def layout(stdout: str, heading: str = "(b) the layout") -> list[str]:
    """The rows of the table under `heading` (the placement's layout, or the
    dispatch's `(b) what ran`), spaces collapsed: no absolute path."""
    lines = stdout.split("\n")
    start = lines.index(heading)
    rows = []
    for line in lines[start + 1:]:
        if not line.startswith("  "):
            break
        rows.append(" ".join(line.split()))
    return rows


# --- #454: the header, whatever the name and the stdout ----------------------


@pytest.fixture
def plain(family_template, tmp_path) -> Path:
    """The plain holder, in the family folder `make siblings` wants, so the
    placement run gets past its folder check and prints everything."""
    return in_family_folder(family_template, tmp_path, PLAIN)


#: The two runs that print a header, and the last line each ends in on a
#: dry run: `make siblings` (the placement) and `make park` / `make resume`
#: (`--make <target>`, the dispatch). `MAKE` is the interpreter for both, so
#: the dispatch needs no `make`, and a family with no members runs nothing.
MODES = [
    pytest.param(("--dry-run",),
                 "--dry-run: nothing was cloned, fetched or moved.\n",
                 id="placement"),
    pytest.param(("--make", "park", "--dry-run"),
                 "--dry-run: nothing was run. `make park` would run in 0 "
                 "member(s).\n", id="dispatch"),
]
#: The same two runs, for the rows that do not look at the last line.
RUNS = [pytest.param(mode.values[0], id=mode.id) for mode in MODES]


@pytest.mark.parametrize("args, last", MODES)
@pytest.mark.parametrize("scalar, printed, encoding", NAME_ROWS)
def test_the_header_is_printed_whatever_the_name_and_the_stdout(
        plain, tmp_path, scalar, printed, encoding, args, last):
    """The first line of each run, on origin/main, ended every row but a plain
    name under a stdout that holds it, and every row under `ascii`, in
    `UnicodeEncodeError` (`_run_placement` and `dispatch_all`, the two prints
    the issue names); a raw ESC or CR reached the terminal. Exit 0, no
    traceback, the name spelled on the line it belongs to, the run's own last
    line, nothing on stderr, and not one control character anywhere."""
    edit(plain, "family.yaml", f'name: "{PLAIN}"', f"name: {scalar}")
    code, out, err = sib(plain, *args, tmp_path=tmp_path, encoding=encoding,
                         changes=PYTHON_AS_MAKE)
    assert code == 0, out + err
    assert err == "", err
    assert out.split("\n")[0] == header(printed, plain, encoding), out
    assert out.endswith(last), out
    assert not NEVER_RAW & set(out), out


@pytest.mark.parametrize("args", RUNS)
@pytest.mark.parametrize("encoding", ["utf-8:strict", "utf-8:surrogateescape",
                                      "cp1252:surrogateescape",
                                      "cp1252:strict", "ascii:strict"])
def test_a_plain_name_is_printed_under_every_stdout(plain, tmp_path, args,
                                                    encoding):
    """The control of the issue's table: `name: "InkRouter"` under
    `PYTHONIOENCODING=ascii` ended in `UnicodeEncodeError` on the file's own
    dash, for every name. The line holds one dash and a name; every stdout now
    writes both, the dash as an escape where the stdout cannot hold it."""
    code, out, err = sib(plain, *args, tmp_path=tmp_path, encoding=encoding,
                         changes=PYTHON_AS_MAKE)
    assert code == 0, out + err
    assert "Traceback" not in err, err
    first = out.split("\n")[0]
    assert first == header(PLAIN, plain, encoding), out
    assert ("\\u2014" in first) == (encoding == "ascii:strict"), first


@pytest.mark.parametrize("args", RUNS)
@pytest.mark.parametrize("scalar, name", BYTE_NAMES)
def test_a_name_a_utf8_stdout_holds_is_written_as_the_bytes_it_is(
        plain, tmp_path, scalar, name, args):
    """BYTE-IDENTICAL to origin/main for the names that printed raw there: the
    first line is exactly what the plain `print` it replaced wrote. A Japanese
    name, an emoji, a quote and a backslash, and the valid names
    `str.isprintable` refuses (a Persian name with its zero-width non-joiner,
    an emoji sequence with its zero-width joiners, a Japanese full name with
    the ideographic space, the no-break space, the soft hyphen, a zero-width
    space and a byte-order mark)."""
    edit(plain, "family.yaml", f'name: "{PLAIN}"', f"name: {scalar}")
    code, stdout, stderr = run_tool_bytes(
        plain / "scripts" / "siblings.py", *args, encoding="utf-8:strict",
        tmp_path=tmp_path, cwd=plain,
        changes={**NO_CREDENTIAL, **PYTHON_AS_MAKE})
    assert code == 0, stderr
    assert b"Traceback" not in stderr, stderr
    first = stdout.split(b"\n")[0].rstrip(b"\r")
    line = f"siblings: {name} ({plain.resolve()}) {DASH} 0 member(s)"
    assert first == line.encode("utf-8")


def test_a_plain_holder_prints_exactly_what_it_printed_before(plain,
                                                              tmp_path):
    """The WHOLE output of both runs, from known values: every line origin/main
    printed, in order, and nothing added. A holder whose `name:` is its
    repository (the usual one) gets no new line, so none of this moves."""
    code, out, err = sib(plain, "--dry-run", tmp_path=tmp_path)
    assert code == 0, out + err
    assert err == "", err
    assert out.split("\n") == [
        f"siblings: {PLAIN} ({plain.resolve()}) {DASH} 0 member(s)",
        f"  family folder   {plain.resolve().parent}",
        "  each member is cloned BESIDE the holder and stays PINNED inside it "
        "under",
        f"  members/ {DASH} the pinned copy is detached for bootstrap and "
        "validate, the",
        "  sibling is where you work.",
        "",
        "(a) the members, beside the holder (credential source: none)",
        "  no members declared. A family with none is empty, not wrong: "
        "`family.py add` is what puts one here.",
        "",
        "(b) the layout",
        "  what      name               state                  branch",
        "  holder    InkRouter          the holder             main",
        "",
        "--dry-run: nothing was cloned, fetched or moved.",
        "",
    ], out

    code, out, err = sib(plain, "--make", "park", "--dry-run",
                         tmp_path=tmp_path, changes=PYTHON_AS_MAKE)
    assert code == 0, out + err
    assert err == "", err
    assert out.split("\n") == [
        f"siblings: {PLAIN} ({plain.resolve()}) {DASH} 0 member(s)",
        f"  family folder   {plain.resolve().parent}",
        "  `make park` runs in each member's WORKING CLONE beside the "
        "holder. This",
        "  command clones nothing and fetches nothing: it only dispatches.",
        "",
        "(a) make park, one member at a time",
        "  no members declared. A family with none is empty, not wrong: "
        "`family.py add` is what puts one here.",
        "",
        "(b) what ran",
        "  what      name               state                  branch",
        "",
        "--dry-run: nothing was run. `make park` would run in 0 member(s).",
        "",
    ], out


@needs_make
@pytest.mark.parametrize("verb", ["siblings", "park", "resume"])
def test_make_siblings_park_and_resume_run_whatever_the_name_is(plain,
                                                                tmp_path,
                                                                verb):
    """The issue's `make` rows: each exited 2 with the traceback and `make: ***
    [Makefile:49: siblings] Error 1`, and `make park` parked nothing. A holder
    with no members runs all three offline, to the end, on a lone-surrogate
    name."""
    edit(plain, "family.yaml", f'name: "{PLAIN}"', r'name: "a\ud83db"')
    proc = subprocess.run([MAKE, verb], cwd=str(plain),
                          env=child_environ(tmp_path, "utf-8:strict",
                                            {**NO_CREDENTIAL}),
                          capture_output=True, stdin=subprocess.DEVNULL,
                          check=False)
    out, err = (text.decode("utf-8", "replace")
                for text in (proc.stdout, proc.stderr))
    assert proc.returncode == 0, out + err
    assert "Traceback" not in err, err
    # `make` echoes its recipe line first, so the header is on a line of its
    # own, not the first.
    assert header(r"a\ud83db", plain, "utf-8:strict") in out.split("\n"), out


# --- #454: a member row is a manifest's text ---------------------------------

#: Two members that are not checked out and not cloned: the project name holds
#: an ESC, and the path a line separator, as the issue's last row asks.
ROWS = (
    "members:\n"
    '  - project: "Ir\\x1bs"\n'
    "    repository: Contoso/Irs\n"
    '    path: "members/Ir\\u2028s"\n'
    '  - project: "Su\\u2028b"\n'
    "    repository: Contoso/Sub\n"
    '    path: "members/Su\\x1bb"\n')


def with_rows(holder: Path) -> Path:
    edit(holder, "family.yaml", "members: []", ROWS)
    return holder


@pytest.mark.parametrize("encoding", NARROW)
def test_a_member_row_that_is_not_checked_out_is_spelled(plain, tmp_path,
                                                         encoding):
    """`--dry-run`, so nothing is cloned and GitHub is never asked: each member
    row's three prints, the `would clone` line (project, url, path and the
    reason a branch is not known), the layout row and the pinned row. A raw ESC
    or line separator in any of them reached the output as itself."""
    holder = with_rows(plain)
    code, out, err = sib(holder, "--dry-run", tmp_path=tmp_path,
                         encoding=encoding)
    assert code == 0, out + err
    assert "Traceback" not in err, err
    folder = holder.resolve().parent
    lines = out.split("\n")
    would = (" is not checked out, so its tracking branch is not known here "
             "(`make bootstrap` checks it out)")
    assert (r"  [Ir\x1bs] would clone https://github.com/Contoso/Irs.git "
            r"(family.yaml repository:) -> " + shown(str(folder), encoding)
            + r"/Ir\x1bs, on its remote's default branch: "
            r"members/Ir\u2028s/project.yaml" + would) in lines, out
    assert (r"  [Su\u2028b] would clone https://github.com/Contoso/Sub.git "
            r"(family.yaml repository:) -> " + shown(str(folder), encoding)
            + r"/Su\u2028b, on its remote's default branch: "
            r"members/Su\x1bb/project.yaml" + would) in lines, out
    assert layout(out) == [
        "what name state branch",
        f"holder {PLAIN} the holder main",
        r"sibling Ir\x1bs would clone -",
        r"sibling Su\u2028b would clone -",
        r"pinned members/Ir\u2028s not checked out make bootstrap",
        r"pinned members/Su\x1bb not checked out make bootstrap",
    ], out
    assert not NEVER_RAW & set(out), out


@pytest.mark.parametrize("encoding", NARROW)
def test_a_dispatch_over_a_member_with_no_clone_is_spelled(plain, tmp_path,
                                                           encoding):
    """`make park` over the same rows: no working clone, so each member is a
    finding that names its project and where the clone would be, on stderr, and
    a row in the table on stdout. Exit 1: a skip is not a pass."""
    holder = with_rows(plain)
    code, out, err = sib(holder, "--make", "park", "--dry-run",
                         tmp_path=tmp_path, encoding=encoding,
                         changes=PYTHON_AS_MAKE)
    assert code == 1, out + err
    assert "Traceback" not in err, err
    folder = shown(str(holder.resolve().parent), encoding)
    assert (r"FINDING Ir\x1bs: skipped: no working clone at " + folder
            + r"/Ir\x1bs; run `make siblings` first.") in err, err
    assert (r"FINDING Su\u2028b: skipped: no working clone at " + folder
            + r"/Su\u2028b; run `make siblings` first.") in err, err
    assert layout(out, "(b) what ran") == [
        "what name state branch",
        r"sibling Ir\x1bs SKIPPED no clone -",
        r"sibling Su\u2028b SKIPPED no clone -",
    ], out
    assert not NEVER_RAW & (set(out) | set(err)), out + err


# --- #1216: a row pads its name by the columns it takes ---------------------

#: Three wide characters, and a name whose acute is a combining mark.
WIDE = "\u65e5\u672c\u8a9e"
COMBINING = "e\u0301cole"
#: Three members not checked out and not cloned, each mounted at
#: `members/<its name>`, so the pinned rows hold the same characters.
COLUMN_MEMBERS = "members:\n" + "".join(
    f'  - project: "{name}"\n    repository: Contoso/{repository}\n'
    f'    path: "members/{name}"\n'
    for name, repository in ((WIDE, "Wide"), (COMBINING, "Accent"),
                             ("Atlas", "Atlas")))
#: The columns a terminal gives each name a UTF-8 stdout writes as it is,
#: counted by hand: two to a wide character and none to the combining
#: acute. A name an ASCII stdout writes is its escapes, all ASCII, and
#: takes one column to a character.
TAKES = {WIDE: 6, COMBINING: 5, f"members/{WIDE}": 14,
         f"members/{COMBINING}": 13}
#: Where a row's `state` begins: the 2 of the indent, the 9 of `what` and a
#: space, then the 18 of `name` and a space.
STATE_COLUMN = 31


def state_columns(stdout: str, heading: str) -> list[tuple[str, int]]:
    """`(name, the column its state begins at)` for each row under
    `heading`, read raw. A name here holds no space, so it ends at the
    first one after column 12."""
    lines = stdout.split("\n")
    start = lines.index(heading)
    assert lines[start + 1].index("state") == STATE_COLUMN, stdout
    rows = []
    for line in lines[start + 2:]:
        if not line.startswith("  "):
            break
        name, _, rest = line[12:].partition(" ")
        if name not in TAKES:
            assert name.isascii(), (name, stdout)
        takes = TAKES.get(name, len(name))
        rows.append((name, 12 + takes + 1 + len(rest) - len(rest.lstrip(" "))))
    return rows


@pytest.mark.parametrize("encoding", NARROW)
def test_the_layout_keeps_every_state_under_its_heading(plain, tmp_path,
                                                         encoding):
    """THE ISSUE'S ROWS, in the placement's table: the holder, each member
    and each pinned mount. On main a UTF-8 stdout put the wide name's
    `state` at column 34 and the combining one's at 30, and an ASCII stdout
    at 46 and 36. Every row whose name fits the field as stdout writes it
    starts its `state` at column 31 now. On an ASCII stdout the two pinned
    mounts, written as `members/` and their escapes, take 26 and 19 columns,
    more than the field: each keeps the one space between fields, as `:<18`
    keeps it after an ASCII name that long, and nothing is cut."""
    edit(plain, "family.yaml", "members: []", COLUMN_MEMBERS)
    code, out, err = sib(plain, "--dry-run", tmp_path=tmp_path,
                         encoding=encoding)
    assert code == 0, out + err
    wide, combining = (shown(name, encoding) for name in (WIDE, COMBINING))
    narrow = encoding == "ascii:strict"
    assert state_columns(out, "(b) the layout") == [
        (PLAIN, STATE_COLUMN), (wide, STATE_COLUMN),
        (combining, STATE_COLUMN), ("Atlas", STATE_COLUMN),
        (f"members/{wide}", 39 if narrow else STATE_COLUMN),
        (f"members/{combining}", 32 if narrow else STATE_COLUMN),
        ("members/Atlas", STATE_COLUMN)], out
    lines = out.split("\n")
    assert f"  {'sibling':<9} {'Atlas':<18} {'would clone':<22} -" in lines
    if narrow:
        assert (f"  {'pinned':<9} members/{wide} {'not checked out':<22} "
                "make bootstrap") in lines, out


@pytest.mark.parametrize("encoding", NARROW)
def test_what_ran_keeps_every_state_under_its_heading(plain, tmp_path,
                                                      encoding):
    """The same three members in the dispatch's `(b) what ran`, which prints
    the same rows: no clone, so each is skipped, exit 1, and every `state`
    starts at column 31 on either stdout."""
    edit(plain, "family.yaml", "members: []", COLUMN_MEMBERS)
    code, out, err = sib(plain, "--make", "park", "--dry-run",
                         tmp_path=tmp_path, encoding=encoding,
                         changes=PYTHON_AS_MAKE)
    assert code == 1, out + err
    assert "Traceback" not in err, err
    assert state_columns(out, "(b) what ran") == [
        (shown(WIDE, encoding), STATE_COLUMN),
        (shown(COMBINING, encoding), STATE_COLUMN),
        ("Atlas", STATE_COLUMN)], out
    assert (f"  {'sibling':<9} {'Atlas':<18} {'SKIPPED no clone':<22} -"
            in out.split("\n")), out


# --- #454: a real clone, named with a line separator -------------------------

#: The member's directory in the family folder: a name no terminal should be
#: handed raw, on a disk that holds it (every one this suite runs on does).
EXOTIC = "IR\u2028RS"
SPELLED = "IR\\u2028RS"
MEMBERS_MOUNT = f"members/{MEMBER}"


@pytest.fixture(scope="module")
def quill(tmp_path_factory) -> dict:
    """The holder of #629, for real: `family.py init --family Quill --name
    QuillWorks` into local bare remotes, with one scaffolded member added and
    the holder's `main` moved to it, as `test_family.family` leaves its own."""
    base = tmp_path_factory.mktemp("siblings-family-name")
    scaffold_member(base, MEMBER)
    created = run_script(
        FAMILY, "init", "--org", ORG, "--family", QUILL, "--name", DISPLAY,
        "--created-by", "Test Human", "--created-on", "2026-09-04",
        "--local-remote-dir", str(base / "remotes"),
        "--work-dir", str(base / "fam"))
    assert created.returncode == 0, created.stderr + created.stdout
    root = base / "fam" / QUILL
    git("switch", "-q", "-c", WORK_BRANCH, cwd=root)
    added = run_script(FAMILY, "add", "--family-root", str(root),
                       "--member", f"{ORG}/{MEMBER}",
                       "--local-remote-dir", str(base / "remotes"))
    assert added.returncode == 0, added.stderr + added.stdout
    git("push", "-q", "origin", f"{WORK_BRANCH}:main", cwd=root)
    return {"base": base, "root": root, "remotes": base / "remotes"}


@pytest.fixture
def exotic(quill, tmp_path) -> Path:
    """A holder in its family folder whose one member's PROJECT NAME (and so
    its working clone's directory) holds a line separator; its url, mount and
    repository are the real ones, so the clone, the member's own bootstrap and
    a verb in it all really run."""
    holder = in_family_folder(quill["root"], tmp_path, QUILL)
    edit(holder, "family.yaml", f"  - project: {MEMBER}\n",
         '  - project: "IR\\u2028RS"\n')
    return holder


def test_a_cloned_member_named_with_a_line_separator_is_spelled_throughout(
        exotic, tmp_path):
    """The whole placement for real, then again: the clone line, the member's
    own bootstrap header, the layout row and the closing line, and on the
    second run the `present` lines. None of them carries the separator raw, and
    the clone is where the RAW name puts it."""
    code, out, err = sib(exotic, tmp_path=tmp_path)
    assert code == 0, out + err
    assert err == "", err
    folder = exotic.resolve().parent
    lines = out.split("\n")
    cloning = [line for line in lines
               if line.startswith(f"  [{SPELLED}] cloning ")]
    assert len(cloning) == 1, out
    assert cloning[0].endswith(" (.gitmodules) on main, its tracking branch "
                               f"({MEMBERS_MOUNT}/project.yaml)"), cloning
    assert f"  --- {SPELLED}: its own bootstrap ---" in lines, out
    assert (folder / EXOTIC / ".git").is_dir(), "the raw name made the clone"
    assert "\u2028" not in out, out
    assert f"siblings ok: 1 member(s) beside the holder in {folder}" in lines
    assert (f"sibling {SPELLED} cloned main" in layout(out)), layout(out)

    again, out, err = sib(exotic, tmp_path=tmp_path)
    assert again == 0, out + err
    lines = out.split("\n")
    assert f"  [{SPELLED}] present at {folder}/{SPELLED}; fetching only" \
        in lines, out
    assert "\u2028" not in out, out


def test_the_dry_run_over_a_present_member_is_spelled(exotic, tmp_path):
    """`present at <path>; would fetch`: the member and the path it names."""
    assert sib(exotic, tmp_path=tmp_path)[0] == 0
    code, out, err = sib(exotic, "--dry-run", tmp_path=tmp_path)
    assert code == 0, out + err
    folder = exotic.resolve().parent
    assert (f"  [{SPELLED}] present at {folder}/{SPELLED}; would fetch, "
            "nothing else") in out.split("\n"), out
    assert "\u2028" not in out, out


def test_a_branch_name_with_a_line_separator_is_spelled_in_the_row(exotic,
                                                                   tmp_path):
    """The row's last column is the branch a person has checked out, which git
    allows to hold a separator."""
    assert sib(exotic, tmp_path=tmp_path)[0] == 0
    clone = exotic.resolve().parent / EXOTIC
    git("checkout", "-q", "-b", "wip\u2028x", cwd=clone)
    code, out, err = sib(exotic, tmp_path=tmp_path)
    assert code == 0, out + err
    row = f"sibling {SPELLED} present, fetched wip\\u2028x"
    assert row in layout(out), out
    assert "\u2028" not in out, out


def test_a_directory_that_is_no_clone_is_a_spelled_finding(exotic, tmp_path):
    """`NOT A CLONE`: the finding names the member and the directory, both on
    stderr, both spelled."""
    stray = exotic.resolve().parent / EXOTIC
    stray.mkdir()
    (stray / "notes.md").write_bytes(b"mine\n")
    code, out, err = sib(exotic, tmp_path=tmp_path)
    assert code == 1, out + err
    folder = exotic.resolve().parent
    assert (f"FINDING {SPELLED}: {folder}/{SPELLED} exists, is not empty and "
            "is not a git clone") in err, err
    assert (stray / "notes.md").read_bytes() == b"mine\n"
    assert "\u2028" not in out + err, out + err


def test_a_clone_of_another_repository_is_a_spelled_finding(exotic, tmp_path):
    """`WRONG ORIGIN`: the finding quotes the clone's own `origin`, which is
    git's text and may hold a separator, and the directory and the member."""
    assert sib(exotic, tmp_path=tmp_path)[0] == 0
    clone = exotic.resolve().parent / EXOTIC
    git("remote", "set-url", "origin", "https://example.invalid/a\u2028b.git",
        cwd=clone)
    code, out, err = sib(exotic, tmp_path=tmp_path)
    assert code == 1, out + err
    folder = exotic.resolve().parent
    assert (f"FINDING {SPELLED}: {folder}/{SPELLED} is a clone of "
            r"https://example.invalid/a\u2028b.git, not of "
            f"{ORG}/{MEMBER}") in err, err
    assert "\u2028" not in out + err, out + err


def test_a_verb_in_a_member_named_with_a_line_separator_is_spelled(exotic,
                                                                   tmp_path):
    """`make <target>` in the working clone: the header over its output, the
    dry run's `would run` line (whose `--make-arg` value may itself hold a
    separator, which the pattern admits), and the finding of a verb that exits
    non-zero. `MAKE` is the interpreter, so `<target>` is a script in the
    clone, and the verb runs only if the RAW name reached the working
    directory."""
    assert sib(exotic, tmp_path=tmp_path)[0] == 0
    clone = exotic.resolve().parent / EXOTIC
    (clone / "hello.py").write_bytes(b"open('ran', 'w').close()\n")
    (clone / "fail.py").write_bytes(b"raise SystemExit(3)\n")
    folder = exotic.resolve().parent

    code, out, err = sib(exotic, "--make", "hello.py", "--make-arg",
                         "ARGS=a\u2028b", "--dry-run", tmp_path=tmp_path,
                         changes=PYTHON_AS_MAKE)
    assert code == 0, out + err
    assert (f"  [{SPELLED}] would run `make hello.py ARGS=a\\u2028b` in "
            f"{folder}/{SPELLED}") in out.split("\n"), out
    assert "\u2028" not in out, out
    assert not (clone / "ran").exists(), "a dry run runs nothing"

    code, out, err = sib(exotic, "--make", "hello.py", tmp_path=tmp_path,
                         changes=PYTHON_AS_MAKE)
    assert code == 0, out + err
    assert f"  --- {SPELLED}: make hello.py ---" in out.split("\n"), out
    assert (clone / "ran").exists(), "the verb ran in the RAW directory"
    assert (f"siblings ok: `make hello.py` ran in 1 member(s) beside the "
            f"holder in {folder}") in out.split("\n"), out

    code, out, err = sib(exotic, "--make", "fail.py", tmp_path=tmp_path,
                         changes=PYTHON_AS_MAKE)
    assert code == 1, out + err
    assert (f"FINDING {SPELLED}: `make fail.py` in {folder}/{SPELLED} exited "
            "3;") in err, err
    assert f"sibling {SPELLED} make fail.py exited 3 main" in layout(
        out, "(b) what ran"), out
    assert "\u2028" not in out + err, out + err


# --- #629: the folder is named after the repository --------------------------


def fenced(text: str, language: str | None = None) -> list[list[str]]:
    """The lines of each fenced block of a Markdown text, in order; only the
    blocks opened with ```language when one is given."""
    blocks, current, opened = [], None, None
    for line in text.split("\n"):
        if line.startswith("```"):
            if current is None:
                current, opened = [], line[3:].strip()
            else:
                if language is None or opened == language:
                    blocks.append(current)
                current = None
        elif current is not None:
            current.append(line)
    return blocks


def readme_of(holder: Path) -> str:
    return (holder / "README.md").read_text(encoding="utf-8")


def readme_instructions(text: str) -> dict:
    """What the holder's README tells a reader to do, read out of the text and
    not out of anything the tool knew: the `git clone` url and the directory it
    says to `cd` into, and the names of the folder and the holder in its
    layout block."""
    shell = next(block for block in fenced(text, "sh")
                 if any(line.startswith("git clone") for line in block))
    clone = next(line for line in shell if line.startswith("git clone"))
    cd = next(line for line in shell if line.startswith("cd "))
    plan = next(block for block in fenced(text, "")
                if any("a PLAIN FOLDER" in line for line in block))
    folder = next(re.match(r"(\S+)/\s+a PLAIN FOLDER", line)[1]
                  for line in plan if "a PLAIN FOLDER" in line)
    holder = next(re.match(r"\s+(\S+)/\s+THE HOLDER", line)[1]
                  for line in plan if "THE HOLDER" in line)
    return {"url": shlex.split(clone)[-1], "cd": shlex.split(cd)[1],
            "folder": folder, "holder": holder}


def test_the_holder_is_made_with_a_display_name_that_is_not_its_repository(
        quill):
    """The fixture is the case of the issue: `--family Quill --name
    QuillWorks`, so the repository is `InkRouter/Quill` and the display name
    is another string."""
    manifest = (quill["root"] / "family.yaml").read_text(encoding="utf-8")
    assert f'name: "{DISPLAY}"' in manifest
    assert f"repository: {ORG}/{QUILL}" in manifest


def test_the_readme_names_the_folder_after_the_repository(quill):
    """Every place the README names the FOLDER: the `cd` after the clone, the
    two lines of the layout, and the sentence about the doubled name. None of
    them is the display name; the display name is the README's title and
    nowhere else."""
    text = readme_of(quill["root"])
    said = readme_instructions(text)
    assert said["cd"] == QUILL
    assert said["folder"] == QUILL
    assert said["holder"] == QUILL
    assert said["url"].endswith(f"/{QUILL}.git")
    assert f"**The doubled `{QUILL}/{QUILL}` is deliberate**" in text
    assert f"**Both are named after the REPOSITORY, `{QUILL}`**" in text
    assert text.count(DISPLAY) == 1, [
        number for number, line in enumerate(text.split("\n"), 1)
        if DISPLAY in line]
    assert text.split("\n")[0] == f"# {DISPLAY}"


def test_the_template_names_the_display_name_only_as_the_readmes_title():
    """The same, in the template a holder is rendered from: `{{FAMILY_NAME}}`
    stands once, as the title, and the folder is `{{FAMILY}}`, the placeholder
    `family.py init` fills with `--family`."""
    lines = README.read_text(encoding="utf-8").split("\n")
    named = [number for number, line in enumerate(lines, 1)
             if "{{FAMILY_NAME}}" in line]
    assert named == [1], named
    assert lines[0] == "# {{FAMILY_NAME}}"
    assert "cd {{FAMILY}}" in lines


def followed(quill: dict, tmp_path: Path) -> tuple[Path, Path]:
    """`(the family folder, the holder)` as the README's own words make them:
    its layout block names a folder, its first block clones the holder into it
    (read through git, as a clone of a bare repository just pushed must be) and
    says which directory to `cd` into, and that directory must be what the
    clone made."""
    said = readme_instructions(readme_of(quill["root"]))
    folder = tmp_path / said["folder"]
    folder.mkdir()
    url = Path(said["url"])
    made = clone_just_pushed(url, folder / url.stem)
    assert made.returncode == 0, made.stderr + made.stdout
    holder = folder / said["cd"]
    made_dirs = sorted(path.name for path in folder.iterdir())
    assert holder.is_dir(), (f"the README says `cd {said['cd']}` and the "
                             f"clone made {made_dirs}")
    assert said["cd"] == said["holder"]
    return folder, holder


def test_the_readmes_own_layout_is_the_one_make_siblings_places(quill,
                                                                tmp_path):
    """Follow the README, and nothing but the README, then run the holder's own
    `scripts/siblings.py` from where it says to stand: the member is cloned
    beside the holder, with no WARNING and nothing to move. R605's mutant M4,
    `family_folder_name` preferring `name:`, survived 166 tests: here it is
    the README's layout that it breaks."""
    folder, holder = followed(quill, tmp_path)
    code, out, err = sib(holder, tmp_path=tmp_path)
    assert code == 0, out + err
    assert err == "", err
    assert (folder / MEMBER / ".git").is_dir(), "the member was not cloned"
    assert git("rev-parse", "--abbrev-ref", "HEAD",
               cwd=folder / MEMBER).stdout.strip() == "main"
    assert not (tmp_path / DISPLAY).exists()
    placed = f"1 member(s) beside the holder in {folder.resolve()}"
    assert f"siblings ok: {placed}" in out.split("\n"), out


@needs_make
def test_make_siblings_clones_from_the_readmes_layout(quill, tmp_path):
    """The same through `make siblings`, the entry the README names."""
    folder, holder = followed(quill, tmp_path)
    proc = subprocess.run(
        [MAKE, "siblings"], cwd=str(holder),
        env=child_environ(tmp_path, "utf-8:strict",
                          {**allow_file_protocol(), **NO_CREDENTIAL}),
        capture_output=True, stdin=subprocess.DEVNULL, check=False)
    out, err = (text.decode("utf-8", "replace")
                for text in (proc.stdout, proc.stderr))
    assert proc.returncode == 0, out + err
    assert "WARNING" not in err, err
    assert (folder / MEMBER / ".git").is_dir(), out + err


def display_header(holder: Path) -> str:
    """The first line of a run over the Quill holder, whose `name:` is the
    display name."""
    return f"siblings: {DISPLAY} ({holder.resolve()}) {DASH} 1 member(s)"


#: The line under the folder's own that says which name names the folder.
NOTE = (f"  the folder is named after the holder's REPOSITORY, {QUILL}, and "
        f"never after name: {DISPLAY}, which is only a display name")


def test_a_holder_laid_out_by_the_display_name_is_refused_and_says_which_name(
        quill, tmp_path):
    """What the OLD README told a reader to do: `QuillWorks/QuillWorks`. It is
    still refused (the folder is the repository's), nothing is cloned or moved,
    and the run now says which name it means, on a line of its own, before it
    warns: the display name is only a title."""
    holder = in_family_folder(quill["root"], tmp_path, DISPLAY)
    code, out, err = sib(holder, tmp_path=tmp_path)
    assert code == 1, out + err
    assert (f"WARNING the holder's parent folder is '{DISPLAY}', not "
            f"'{QUILL}'.") in err, err
    assert f"should sit in a plain folder named {QUILL}" in err, err
    assert not (tmp_path / DISPLAY / MEMBER).exists(), "nothing was cloned"
    assert out.split("\n")[:3] == [
        display_header(holder), f"  parent folder   {holder.resolve().parent}",
        NOTE]
    assert holder.is_dir()


def test_the_right_layout_says_which_name_it_means_too(quill, tmp_path):
    """The same line on a run that goes on, under the family folder's own
    header, so the two names are told apart wherever they differ."""
    holder = in_family_folder(quill["root"], tmp_path, QUILL)
    code, out, err = sib(holder, "--dry-run", tmp_path=tmp_path)
    assert code == 0, out + err
    assert out.split("\n")[:3] == [
        display_header(holder), f"  family folder   {holder.resolve().parent}",
        NOTE]


def test_a_dispatch_run_keeps_its_header_and_asks_nothing_of_the_folder(
        quill, tmp_path):
    """`--make` clones nothing and asks nothing of the folder, so it keeps its
    own header whatever the folder is called: the display name, the folder as
    it is, and no new line."""
    holder = in_family_folder(quill["root"], tmp_path, DISPLAY)
    code, out, err = sib(holder, "--make", "park", "--dry-run",
                         tmp_path=tmp_path, changes=PYTHON_AS_MAKE)
    assert code == 1, out + err
    assert out.split("\n")[:2] == [
        display_header(holder), f"  family folder   {holder.resolve().parent}"]
    assert NOTE not in out.split("\n")
