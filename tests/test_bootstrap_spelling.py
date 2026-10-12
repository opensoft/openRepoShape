# SPDX-License-Identifier: Apache-2.0
"""Both roots' `bootstrap.py` print what the manifest says and are never ended
by it (#391).

`scripts/bootstrap.py` (what `make bootstrap` runs) opened with
`print(f"bootstrap: {name} ({root})")`, before any step, and the family root's
with the same line. `name: "a\\ud83db"` is a string holding a lone surrogate, which
no UTF-8 stdout can write, so the run ended in a `UnicodeEncodeError` traceback,
`make bootstrap` exited 2, and the validator that names the problem
(`validate-manifest.py`, the second of the three) was never reached. A valid name
the stdout cannot hold (`日本` under `PYTHONIOENCODING=ascii`) ended the same way,
and the family root's line also holds a literal dash, so under that stdout it
raised for EVERY name. A raw ESC or CR in a name is encodable everywhere and
reached the terminal as the control it is.

Both files are shape copies (digest-pinned in every project that holds them) and
a project carries `scripts/repo_shape.py` and no `shape_materialize.py`, so they
cannot call #214's helper. Each now carries two small functions, the same in
both: `escape_unencodable_stdout` reconfigures a `strict` or `surrogateescape`
stdout to `backslashreplace` once, at the start of `main`; `spelled` writes the
controls (category Cc), the surrogates (Cs), the line and paragraph separators
(Zl, Zp) and the bidirectional controls (U+061C, U+200E, U+200F, U+202A to
U+202E, U+2066 to U+2069) as the escape Python spells them, and NOTHING else,
and is applied to every value the script prints that it read from the manifest,
a register row or the disk. `str.isprintable` is not the test: it also refuses
the zero-width non-joiner and joiner, the ideographic and no-break spaces and
the soft hyphen, which are valid text that printed raw before this fix and
still do. Four kinds of test, all against local bare remotes:

- the rows of the issue, run for real in a scaffolded project and in a family
  holder, under every stdout that matters, answered in BYTES and decoded
  strictly in the encoding the run was given (a byte the stdout could not have
  held fails the test);
- every other print that carries a value: the leg's role, path and tracking
  branch, a register row and the path of a register, the root's own directory
  name, a member row and `--members-make`;
- what the run does NEXT: it reaches the validators and ends as they end, at
  the `FINDING manifest-name` that `validate-manifest.py` now gives a name
  holding a lone surrogate (#280, landed in #390), with no traceback;
- the two functions themselves, and a guard that the two files carry the same
  two.

A plain name must print exactly what it printed before: a golden of the whole
output, from known values.
"""

from __future__ import annotations

import ast
import importlib.util
import io
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

from conftest import REPO, git, run_script
from test_stdout_encoding import child_environ, run_tool_bytes, shown

sys.path.insert(0, str(REPO / "scripts"))

ASSEMBLY_TEMPLATE = (REPO / "templates" / "assembly-root" / "scripts"
                     / "bootstrap.py")
FAMILY_TEMPLATE = (REPO / "templates" / "family-root" / "scripts"
                   / "bootstrap.py")
FAMILY_TOOL = REPO / "scripts" / "family.py"
FAMILY_NAME = "InkRouter"

#: Every stdout the rows below are run under, as `PYTHONIOENCODING` spells it.
#: - `utf-8:strict` is the control: it holds every name but a surrogate.
#: - `utf-8:surrogateescape` is what a POSIX or `C.UTF-8` locale gives.
#: - `cp1252:surrogateescape` is Windows' default for a stdout that is not the
#:   console, and `cp1252:strict` and `ascii:strict` are what
#:   `PYTHONIOENCODING=cp1252` and `=ascii` give: none holds `日本`.
#: - `utf-8:replace` is an operator's own lenient handler, left as chosen.
ENCODINGS = ("utf-8:strict", "utf-8:surrogateescape",
             "cp1252:surrogateescape", "cp1252:strict", "ascii:strict",
             "utf-8:replace")
#: The two that do not hold the dash, the middle dot or `日本`.
NARROW = ("utf-8:strict", "ascii:strict")

#: `(id, the YAML scalar written after `name:`, what the line must say of it)`.
#: The scalar is YAML text, so `\ud83d` here is the six characters of an escape
#: the reader resolves; the third is the characters that must be PRINTED.
CORE_NAMES = (
    ("plain", '"Atlas"', "Atlas"),
    ("lone-surrogate", r'"a\ud83db"', r"a\ud83db"),
    ("esc-and-cr", r'"a\x1bb\rc"', r"a\x1bb\rc"),
    ("japanese", '"日本"', "日本"),
    # Valid text that `str.isprintable` refuses: it prints raw, as it did
    # before the fix, wherever the stdout holds it, and the cp1252 stdouts
    # hold this one.
    ("nbsp", r'"a\xa0b"', "a\xa0b"),
)
#: Valid names that print RAW, as on origin/main: a Persian name with its
#: zero-width non-joiner, an emoji sequence with its zero-width joiners, a
#: Japanese full name with the ideographic space, and the soft hyphen. (Each
#: is spelled by code point here, so no invisible character sits in this file.)
RAW_NAMES = (
    ("persian-zwnj", r'"\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u0645"',
     "\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u0645"),
    ("emoji-zwj", r'"\U0001f468\u200d\U0001f469\u200d\U0001f467"',
     "\U0001f468\u200d\U0001f469\u200d\U0001f467"),
    ("ideographic-space", '"山田\\u3000太郎"', "山田\u3000太郎"),
    ("nbsp", r'"a\xa0b"', "a\xa0b"),
    ("soft-hyphen", r'"co\xadop"', "co\xadop"),
    ("zero-width-space-and-bom", r'"a\u200bb\ufeffc"', "a\u200bb\ufeffc"),
)
#: Names that print ESCAPED: a newline, tab and DEL; U+2028; and the
#: right-to-left override and mark, which reorder the text around them.
MORE_NAMES = (
    ("newline-tab-del", r'"a\nb\tc\x7fd"', r"a\nb\tc\x7fd"),
    ("line-separator", r'"a\u2028b"', r"a\u2028b"),
    ("rlo-and-rlm", r'"a\u202eb\u200fc"', r"a\u202eb\u200fc"),
    ("astral", '"🙂"', "🙂"),
    ("quote-and-backslash", r'"He said \"hi\" \\o/"', r'He said "hi" \o/'),
    ("two-lone-surrogates", r'"\ud83d\ude00"', r"\ud83d\ude00"),
)
#: What must reach NO stdout raw, whatever the row: the controls, the line
#: separator and the bidirectional override and mark.
NEVER_RAW = {"\x1b", "\r", "\x7f", "\u2028", "\u202e", "\u200f", "\x85"}
NAME_ROWS = [pytest.param(scalar, printed, encoding,
                          id=f"{label}-{encoding.replace(':', '-')}")
             for label, scalar, printed in CORE_NAMES
             for encoding in ENCODINGS]
NAME_ROWS += [pytest.param(scalar, printed, encoding,
                           id=f"{label}-{encoding.replace(':', '-')}")
              for label, scalar, printed in MORE_NAMES + RAW_NAMES
              if (label, scalar, printed) not in CORE_NAMES
              for encoding in NARROW]

DEGRADE_LINE = "authority is not wallet-carried in this org"
#: The dash in step (a)'s own wording.
DASH = "\u2014"


def run(script: Path, *args: str, encoding: str, tmp_path: Path, cwd: Path,
        changes: dict | None = None) -> tuple[int, str, str]:
    """`(exit, stdout, stderr)` of one run with its stdout in `encoding`, read
    as BYTES and decoded STRICTLY in that encoding. `\\r\\n` is read as `\\n`
    (Windows writes it), and a lone `\\r` is left to be seen."""
    code, stdout, stderr = run_tool_bytes(
        script, *args, encoding=encoding, tmp_path=tmp_path, cwd=cwd,
        changes=changes)
    codec = encoding.split(":")[0]
    return (code, stdout.decode(codec).replace("\r\n", "\n"),
            stderr.decode(codec, "replace").replace("\r\n", "\n"))


def edit(root: Path, filename: str, old: str, new: str) -> None:
    """`old` to `new` in `root/filename`, as bytes, whatever line ending the
    clone has. `old` must be there once."""
    path = root / filename
    body = path.read_bytes()
    assert body.count(old.encode("utf-8")) == 1, (old, body)
    path.write_bytes(body.replace(old.encode("utf-8"), new.encode("utf-8")))


def bootstrap_of(root: Path) -> Path:
    return root / "scripts" / "bootstrap.py"


def spelled_root(root: Path, encoding: str) -> str:
    """The root as the first line prints it: resolved, with what the stdout
    cannot hold escaped, and a line separator in a directory name escaped
    whatever the stdout."""
    text = str(root.resolve()).replace("\u2028", "\\u2028")
    return shown(text, encoding)


# --- the issue's rows, in a scaffolded project ------------------------------

@pytest.mark.parametrize("scalar, printed, encoding", NAME_ROWS)
def test_the_name_line_is_printed_whatever_the_name_and_the_stdout(
        project, tmp_path, scalar, printed, encoding):
    """On origin/main every row but `plain` and `japanese` under a stdout that
    holds it ended in `UnicodeEncodeError` from the `print` of the name; a raw
    ESC or CR reached the terminal under all of them. Exit 0, no traceback,
    the name on the line it belongs to, spelled, and not one control character
    anywhere in the output. `--skip-validators` because the validators are
    this row's NEXT step, and are not this fix's (they have their own test)."""
    edit(project, "project.yaml", 'name: "Atlas"', f"name: {scalar}")
    code, out, err = run(bootstrap_of(project), "--skip-validators",
                         encoding=encoding, tmp_path=tmp_path, cwd=project)
    assert code == 0, out + err
    assert "Traceback" not in err, err
    lines = out.split("\n")
    assert lines[0] == (f"bootstrap: {shown(printed, encoding)} "
                        f"({spelled_root(project, encoding)})"), out
    assert lines[1] == "", out
    assert out.endswith("bootstrap ok\n"), out
    assert not NEVER_RAW & set(out), out


def test_a_plain_name_prints_exactly_what_it_printed_before(project, tmp_path):
    """BYTE-IDENTICAL for a name every stdout holds. The first run places the
    legs (and says so in other words), the second is steady, and its WHOLE
    output is spelled out here, from the pins and the root. These are the
    lines origin/main printed; nothing in them is a value this fix touches
    except the first line and the two legs'."""
    for _ in range(2):
        code, out, err = run(bootstrap_of(project), "--skip-validators",
                             encoding="utf-8:strict", tmp_path=tmp_path,
                             cwd=project)
        assert code == 0 and err == "", out + err
    spec, leg = (git("rev-parse", f"HEAD:{name}", cwd=project).stdout.strip()
                 [:12] for name in ("spec", "code"))
    assert out.split("\n") == [
        f"bootstrap: Atlas ({project.resolve()})",
        "",
        "(a) legs on tracking branches, pins untouched",
        f"  [spec] spec: on main at {spec} (branch tip == pin)",
        f"  [code] code: on main at {leg} (branch tip == pin)",
        "",
        "(b) neutral validators",
        "  skipped (--skip-validators)",
        "",
        "(c) review authority",
        DEGRADE_LINE,
        "  (no `governance/review-authority/register.yaml` in the assembly "
        "root or in any leg. Wallet-carried authority is an OVERLAY; the "
        "shape confers nothing without it, and nothing with it.)",
        "",
        "bootstrap ok",
        "",
    ], out


#: The valid names whose first line must be the bytes origin/main wrote: those
#: that print raw, and a mixture of printable text and a quote and a backslash.
BYTE_NAMES = [pytest.param(scalar, printed, id=label)
              for label, scalar, printed in RAW_NAMES] + [
    pytest.param('"日本 🙂 \\"q\\" \\\\"', '日本 🙂 "q" \\', id="printable-mixture")]


@pytest.mark.parametrize("scalar, name", BYTE_NAMES)
def test_a_name_a_utf8_stdout_holds_is_written_as_the_bytes_it_is(
        project, tmp_path, scalar, name):
    """BYTE-IDENTICAL to origin/main, read as BYTES so a character kept is a
    character kept: the line is exactly what the plain `print` it replaced
    wrote. `日本`, an emoji, a quote and a backslash, and the valid names
    `str.isprintable` refuses: a Persian name with its zero-width non-joiner,
    an emoji sequence with its zero-width joiners, a Japanese full name with
    the ideographic space, the no-break space, the soft hyphen and the
    zero-width space and byte-order mark."""
    edit(project, "project.yaml", 'name: "Atlas"', f"name: {scalar}")
    code, stdout, stderr = run_tool_bytes(
        bootstrap_of(project), "--skip-validators", encoding="utf-8:strict",
        tmp_path=tmp_path, cwd=project)
    assert code == 0 and b"Traceback" not in stderr, stderr
    first = stdout.split(b"\n")[0].rstrip(b"\r")
    assert first == f"bootstrap: {name} ({project.resolve()})".encode("utf-8")


# --- what the run does NEXT --------------------------------------------------

def test_a_lone_surrogate_name_reaches_the_validators_and_ends_as_they_end(
        project, tmp_path):
    """The run is no longer ended by its own first line. It reaches step (b),
    where the manifest validator fails the run, and exits as `main`'s own
    failed-validator path does: `bootstrap FAILED: manifest (exit 1)`, exit 1.

    WHAT THE VALIDATOR SAYS is #280's, landed in #390: `FINDING manifest-name`
    names the lone surrogate, in the validator by itself and again in the run
    that carries it, and no traceback is anywhere. (Before #390 the
    validator's own `manifest ok:` print raised in ITS process.)"""
    edit(project, "project.yaml", 'name: "Atlas"', r'name: "a\ud83db"')
    alone_code, _, alone_err = run(
        project / "scripts" / "validate-manifest.py", encoding="utf-8:strict",
        tmp_path=tmp_path, cwd=project)
    assert alone_code == 1, alone_err
    assert "FINDING manifest-name" in alone_err, alone_err
    assert "Traceback" not in alone_err, alone_err
    code, out, err = run(bootstrap_of(project), encoding="utf-8:strict",
                         tmp_path=tmp_path, cwd=project)
    assert out.startswith(r"bootstrap: a\ud83db ("), out
    assert "\n(b) neutral validators\n" in out, out
    assert code == 1, out + err
    assert "bootstrap FAILED: manifest (exit 1)" in err, err
    assert 'bootstrap.py", line' not in err, err
    assert "FINDING manifest-name" in err, err
    assert "Traceback" not in err, err


#: The valid names the manifest validator accepts and prints itself.
VALIDATED_NAMES = [pytest.param(scalar, printed, id=label)
                   for label, scalar, printed in RAW_NAMES
                   if label in ("persian-zwnj", "emoji-zwj",
                                "ideographic-space")]


@pytest.mark.parametrize("scalar, name", VALIDATED_NAMES)
def test_a_valid_name_is_printed_as_the_validator_prints_it(project, tmp_path,
                                                            scalar, name):
    """The whole run, validators included, over a valid name that
    `str.isprintable` refuses. `validate-manifest.py` accepts it and prints it
    raw on its `manifest ok:` line, a few lines below this script's own, so
    escaping it here would show one name twice, two ways."""
    edit(project, "project.yaml", 'name: "Atlas"', f"name: {scalar}")
    code, out, err = run(bootstrap_of(project), encoding="utf-8:strict",
                         tmp_path=tmp_path, cwd=project)
    assert code == 0 and "Traceback" not in err, out + err
    lines = out.split("\n")
    assert lines[0] == (f"bootstrap: {name} "
                        f"({spelled_root(project, 'utf-8:strict')})"), out
    assert any(line.startswith(f"manifest ok: {name} (") for line in lines), out


@pytest.mark.skipif(shutil.which("make") is None or
                    shutil.which("python3") is None,
                    reason="the Makefile runs `python3` under `make`")
def test_make_bootstrap_ends_as_the_validators_end_not_in_a_traceback(
        project, tmp_path):
    """`make bootstrap` exited 2 with the traceback and `make: *** [Makefile:44:
    bootstrap] Error 1`; it still exits 2 (make's own code for a failed
    recipe), and now for the validator's reason."""
    edit(project, "project.yaml", 'name: "Atlas"', r'name: "a\ud83db"')
    proc = subprocess.run(["make", "bootstrap"], cwd=str(project),
                          env=child_environ(tmp_path, "utf-8:strict"),
                          capture_output=True, stdin=subprocess.DEVNULL,
                          check=False)
    out, err = (text.decode("utf-8", "replace")
                for text in (proc.stdout, proc.stderr))
    assert proc.returncode == 2, out + err
    assert r"bootstrap: a\ud83db (" in out, out
    assert "FINDING manifest-name" in err, err
    assert "bootstrap FAILED: manifest (exit 1)" in err, err
    assert 'bootstrap.py", line' not in err, err
    assert "Traceback" not in err, err


# --- every other print that carries a value ---------------------------------

def steady(project: Path, tmp_path: Path, encoding: str = "utf-8:strict"):
    """The output of a SECOND run: the first places the legs on their branches
    (and the lines it says that in are not what these rows are about)."""
    run(bootstrap_of(project), "--skip-validators", encoding=encoding,
        tmp_path=tmp_path, cwd=project)
    return run(bootstrap_of(project), "--skip-validators", encoding=encoding,
               tmp_path=tmp_path, cwd=project)


def pin12(project: Path, leg: str) -> str:
    return git("rev-parse", f"HEAD:{leg}", cwd=project).stdout.strip()[:12]


def test_a_legs_role_is_spelled(project, tmp_path):
    edit(project, "project.yaml", "  - role: spec", r'  - role: "s\x1bp"')
    code, out, err = steady(project, tmp_path)
    assert code == 0 and "Traceback" not in err, out + err
    assert (rf"  [s\x1bp] spec: on main at {pin12(project, 'spec')} "
            "(branch tip == pin)") in out.split("\n"), out
    assert "\x1b" not in out, out


@pytest.mark.parametrize("path, spelling", [
    (r'"sp\x1bec"', r"sp\x1bec"),
    (r'"sp\ud83dec"', r"sp\ud83dec"),
    (r'"sp\u2028ec"', r"sp\u2028ec"),
])
def test_a_legs_path_is_spelled_where_it_is_not_initialized(
        project, tmp_path, path, spelling):
    """A path the manifest holds that is no directory: step (a) says so, and
    says what to run, before any validator has had its say. A lone surrogate
    here raised from the `print`."""
    edit(project, "project.yaml", "    path: spec", f"    path: {path}")
    code, out, err = run(bootstrap_of(project), "--skip-validators",
                         encoding="utf-8:strict", tmp_path=tmp_path,
                         cwd=project)
    assert code == 0 and "Traceback" not in err, out + err
    assert (f"  [spec] {spelling}: NOT INITIALIZED. Run `git submodule update "
            f"--init {spelling}` {DASH} the validators below will refuse "
            "until you do.") in out.split("\n"), out
    assert not {"\x1b", "\u2028"} & set(out), out


def test_a_tracking_branch_git_will_not_make_is_spelled(project, tmp_path):
    """Passes on origin/main too, and is here to keep it: that line prints the
    branch with `!r`, and a repr has always escaped a control."""
    edit(project, "project.yaml", "tracking_branch: main",
         r'tracking_branch: "a\x1bb"')
    code, out, err = run(bootstrap_of(project), "--skip-validators",
                         encoding="utf-8:strict", tmp_path=tmp_path,
                         cwd=project)
    assert code == 0 and "Traceback" not in err, out + err
    for leg in ("spec", "code"):
        assert (rf"  [{leg}] {leg}: could not create branch 'a\x1bb' at the "
                f"pin {pin12(project, leg)}; leaving detached"
                ) in out.split("\n"), out
    assert "\x1b" not in out, out


def test_a_branch_name_is_spelled_in_every_line_that_names_it(project,
                                                              tmp_path):
    """A branch git accepts and a terminal should not be handed raw: U+2028.
    The lines that name one: created (and where the remote's is), on, and the
    disagreement."""
    edit(project, "project.yaml", "tracking_branch: main",
         r'tracking_branch: "tb\u2028x"')
    named = r"tb\u2028x"
    spec = project / "spec"
    pin = git("rev-parse", "HEAD:spec", cwd=project).stdout.strip()
    code_pin = pin12(project, "code")
    tree = git("rev-parse", f"{pin}^{{tree}}", cwd=spec).stdout.strip()
    other = git("commit-tree", tree, "-p", pin, "-m", "elsewhere",
                cwd=spec).stdout.strip()
    git("update-ref", "refs/remotes/origin/tb\u2028x", other, cwd=spec)

    def lines() -> list[str]:
        code, out, err = run(bootstrap_of(project), "--skip-validators",
                             encoding="utf-8:strict", tmp_path=tmp_path,
                             cwd=project)
        assert code == 0 and "Traceback" not in err, out + err
        assert "\u2028" not in out, out
        return out.split("\n")

    first = lines()
    assert (f"  [spec] spec: branch {named} created at {pin[:12]} {DASH} at "
            f"the pin; origin/{named} is {other[:12]}, which the pin "
            "deliberately does NOT follow") in first, first
    assert (f"  [code] code: branch {named} created at {code_pin} {DASH} at "
            "the pin") in first, first

    assert (f"  [spec] spec: on {named} at {pin[:12]} (branch tip == pin)"
            ) in lines()

    git("commit", "-q", "--allow-empty", "-m", "local work", cwd=spec)
    tip = git("rev-parse", "HEAD", cwd=spec).stdout.strip()[:12]
    assert (f"  [spec] spec: PIN {pin[:12]} != branch {named} tip {tip}"
            ) in lines()


#: A register row is a file's text. Each value carries a control or a line
#: separator, and the object is a leg's repository with a path after it, so
#: the row is one the readout reports.
REGISTER = (
    "register_version: 1\n"
    "rows:\n"
    "  - row_id: row-0001\n"
    '    holder_ref: "agent:\\x1b[31mred"\n'
    "    target_repo: testorg/Atlas-code\n"
    "    objects:\n"
    '      - "testorg/Atlas-code:co\\x1bde"\n'
    '    act: "re\\rview"\n'
    '    state: "ac\\x1btive"\n'
    '    expires_at: "2026\\u2028"\n')
DOT = "\u00b7"
REGISTER_ROW = (rf"    agent:\x1b[31mred {DOT} re\rview {DOT} testorg/Atlas-code, "
                rf"testorg/Atlas-code:co\x1bde {DOT} ac\x1btive {DOT} "
                rf"expires 2026\u2028")


@pytest.mark.parametrize("encoding", NARROW)
def test_a_register_row_is_spelled(project, tmp_path, encoding):
    """Under `ascii` as well: the row's own separator is a middle dot, which
    that stdout cannot hold, so the row raised whatever it said."""
    register = project / "governance" / "review-authority" / "register.yaml"
    register.parent.mkdir(parents=True)
    register.write_bytes(REGISTER.encode("utf-8"))
    code, out, err = run(bootstrap_of(project), "--skip-validators",
                         encoding=encoding, tmp_path=tmp_path, cwd=project)
    assert code == 0 and "Traceback" not in err, out + err
    assert shown(REGISTER_ROW, encoding) in out.split("\n"), out
    assert not {"\x1b", "\r", "\u2028"} & set(out), out


def test_a_register_and_its_path_are_spelled_when_it_cannot_be_read(
        project, tmp_path):
    """The register a leg holds under a directory whose name carries a line
    separator, which does not parse: its path is on the `register:` line and
    again, with the reader's reason, on the `unreadable` one. Under a stdout
    that HOLDS a line separator, so a raw one would be written raw."""
    edit(project, "project.yaml", "    path: spec", r'    path: "sp\u2028ec"')
    register = (project / "sp\u2028ec" / "governance" / "review-authority"
                / "register.yaml")
    register.parent.mkdir(parents=True)
    register.write_bytes(b"rows:\n\t- row_id: x\n")
    code, out, err = run(bootstrap_of(project), "--skip-validators",
                         encoding="utf-8:strict", tmp_path=tmp_path,
                         cwd=project)
    assert code == 0 and "Traceback" not in err, out + err
    lines = out.split("\n")
    assert (r"  register: sp\u2028ec/governance/review-authority/register.yaml"
            ) in lines, out
    unreadable = [line for line in lines if "unreadable, so nothing" in line]
    assert len(unreadable) == 1 and r"sp\u2028ec" in unreadable[0], out
    assert unreadable[0].endswith("tab used for indentation"), unreadable
    assert "\u2028" not in out, out


def test_a_roots_own_directory_name_is_spelled(project, tmp_path):
    """The second thing the first line prints. Under a stdout that HOLDS a
    line separator, so a raw one would be written raw."""
    renamed = tmp_path / "At\u2028las"
    shutil.move(str(project), str(renamed))
    code, out, err = run(bootstrap_of(renamed), "--skip-validators",
                         encoding="utf-8:strict", tmp_path=tmp_path,
                         cwd=renamed)
    assert code == 0 and "Traceback" not in err, out + err
    assert out.split("\n")[0] == (
        f"bootstrap: Atlas ({spelled_root(renamed, 'utf-8:strict')})"), out
    assert "\u2028" not in out, out


# --- the family root --------------------------------------------------------

@pytest.fixture(scope="module")
def family_template(tmp_path_factory) -> Path:
    """One real family holder, `family.py init` into local bare remotes, no
    members."""
    base = tmp_path_factory.mktemp("bootstrap-spelling-family")
    created = run_script(
        FAMILY_TOOL, "init", "--org", "InkRouter", "--family", FAMILY_NAME,
        "--created-by", "Test Human", "--created-on", "2026-09-04",
        "--local-remote-dir", str(base / "remotes"),
        "--work-dir", str(base / "fam"))
    assert created.returncode == 0, created.stderr + created.stdout
    return base / "fam" / FAMILY_NAME


@pytest.fixture
def holder(family_template, tmp_path) -> Path:
    """A private, mutable copy of the family holder."""
    target = tmp_path / FAMILY_NAME
    shutil.copytree(family_template, target, symlinks=True)
    return target


def family_line(printed: str, holder: Path, encoding: str) -> str:
    """The first line, whole: its dash is the family's own wording, so under a
    stdout that cannot hold it the dash is escaped too."""
    return shown(f"bootstrap: {printed} ({holder.resolve()}) \u2014 0 member(s)",
                 encoding)


@pytest.mark.parametrize("scalar, printed, encoding", NAME_ROWS)
def test_the_family_name_line_is_printed_whatever_the_name_and_the_stdout(
        holder, tmp_path, scalar, printed, encoding):
    """The same rows, one template over. The line holds a literal dash, so on
    origin/main it raised under `ascii` for the plain name too."""
    edit(holder, "family.yaml", f'name: "{FAMILY_NAME}"', f"name: {scalar}")
    code, out, err = run(bootstrap_of(holder), "--no-fetch", "--skip-members",
                         encoding=encoding, tmp_path=tmp_path, cwd=holder)
    assert code == 0, out + err
    assert "Traceback" not in err, err
    assert out.split("\n")[0] == family_line(printed, holder, encoding), out
    assert out.endswith("family bootstrap ok\n"), out
    assert not NEVER_RAW & set(out), out


def test_a_plain_family_prints_exactly_what_it_printed_before(holder,
                                                              tmp_path):
    code, out, err = run(bootstrap_of(holder), "--no-fetch", "--skip-members",
                         encoding="utf-8:strict", tmp_path=tmp_path,
                         cwd=holder)
    assert code == 0 and err == "", out + err
    assert out.split("\n") == [
        f"bootstrap: {FAMILY_NAME} ({holder.resolve()}) \u2014 0 member(s)",
        "",
        "(a) members and their legs",
        "  skipped (--no-fetch)",
        "",
        "(b) each member's own `make bootstrap`",
        "  skipped (--skip-members)",
        "",
        "family bootstrap ok",
        "",
    ], out


@pytest.mark.parametrize("scalar, name", BYTE_NAMES)
def test_a_family_name_a_utf8_stdout_holds_is_written_as_the_bytes_it_is(
        holder, tmp_path, scalar, name):
    """The family root's first line, as BYTES: exactly what the plain `print`
    it replaced wrote on origin/main, for every valid name that prints raw."""
    edit(holder, "family.yaml", f'name: "{FAMILY_NAME}"', f"name: {scalar}")
    code, stdout, stderr = run_tool_bytes(
        bootstrap_of(holder), "--no-fetch", "--skip-members",
        encoding="utf-8:strict", tmp_path=tmp_path, cwd=holder)
    assert code == 0 and b"Traceback" not in stderr, stderr
    first = stdout.split(b"\n")[0].rstrip(b"\r")
    assert first == (f"bootstrap: {name} ({holder.resolve()}) \u2014 0 member(s)"
                     ).encode("utf-8")


def test_a_family_roots_own_directory_name_is_spelled(holder, tmp_path):
    """The second thing the family's first line prints, under a stdout that
    HOLDS a line separator, so a raw one would be written raw."""
    renamed = tmp_path / "Ink\u2028Router"
    shutil.move(str(holder), str(renamed))
    code, out, err = run(bootstrap_of(renamed), "--no-fetch", "--skip-members",
                         encoding="utf-8:strict", tmp_path=tmp_path,
                         cwd=renamed)
    assert code == 0 and "Traceback" not in err, out + err
    assert out.split("\n")[0] == (
        f"bootstrap: {FAMILY_NAME} ({spelled_root(renamed, 'utf-8:strict')}) "
        f"{DASH} 0 member(s)"), out
    assert "\u2028" not in out, out


def test_a_members_row_and_the_make_target_are_spelled(holder, tmp_path):
    """Four rows, none a real submodule, run with `--no-fetch` under a stdout
    that HOLDS a line separator, so a raw one would be written raw:
    - a member that is not checked out, named by a directory with a line
      separator in it;
    - a member with no Makefile;
    - a member whose own `make` runs: `MAKE` is the interpreter and the
      TARGET is a script in the member, named with a line separator, so the
      member runs only if the RAW target reached the command;
    - a member whose command fails, which is what the failure line names.
    """
    edit(holder, "family.yaml", "members: []", (
        "members:\n"
        '  - project: "Ir\\x1bs"\n'
        '    path: "members/Ir\\u2028s"\n'
        '  - project: "Bo\\u2028x"\n'
        "    path: members/Box\n"
        '  - project: "Ma\\x1bke"\n'
        "    path: members/Make\n"
        '  - project: "Fa\\x1bil"\n'
        "    path: members/Fail\n"))
    members = holder / "members"
    target = "ta\u2028rget.py"
    for name in ("Box", "Make", "Fail"):
        (members / name / ".git").mkdir(parents=True)
    for name in ("Make", "Fail"):
        (members / name / "Makefile").write_bytes(b"")
    (members / "Make" / target).write_bytes(
        b"open('ran', 'w').close()\n")

    code, out, err = run(bootstrap_of(holder), "--no-fetch",
                         "--members-make", target, encoding="utf-8:strict",
                         tmp_path=tmp_path, cwd=holder,
                         changes={"MAKE": sys.executable})
    assert "Traceback" not in err, out + err
    assert code == 1, out + err
    lines = out.split("\n")
    assert r"  [Ir\x1bs] Ir\u2028s: NOT CHECKED OUT; skipped. See the fetch " \
        "above." in lines, out
    assert (r"  [Bo\u2028x] no Makefile; skipped. A member without one is "
            f"not misconfigured {DASH} it simply has nothing for this "
            "command to call.") in lines, out
    assert r"(b) each member's own `make ta\u2028rget.py`" in lines, out
    assert r"  --- Ma\x1bke: make ta\u2028rget.py ---" in lines, out
    assert r"  --- Fa\x1bil: make ta\u2028rget.py ---" in lines, out
    assert (members / "Make" / "ran").exists(), \
        "the member's command was handed the escaped target, not the raw one"
    assert err.strip().endswith(
        r"family bootstrap FAILED: Fa\x1bil (make ta\u2028rget.py exited 2)"
    ), err
    assert not {"\x1b", "\u2028"} & set(out), out


# --- the two functions, and the two files that carry them -------------------

def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module", params=[ASSEMBLY_TEMPLATE, FAMILY_TEMPLATE],
                ids=["assembly-root", "family-root"])
def template(request):
    """Each root's `bootstrap.py`, loaded by path under a name of its own, so
    nothing here leaves a module called `bootstrap` importable."""
    return load(request.param, "bootstrap_spelling_"
                f"{request.param.parts[-3].replace('-', '_')}")


@pytest.mark.parametrize("text", [
    "Atlas", "日本", "Zo\u00eb", "\U0001f642", 'He said "hi" \\o/', "a b", "",
    "/tmp/x y/z", "C:\\Users\\a\\Atlas", "a=b: c, [d] {e}",
    # What `str.isprintable` refuses and a UTF-8 terminal shows correctly:
    # Zs (the no-break and ideographic spaces), Cf (the zero-width non-joiner
    # and joiner, the soft hyphen, the zero-width space, the byte-order mark,
    # a tag character), Co (private use) and Cn (unassigned). Printed raw
    # before the fix, so printed raw now.
    "a\xa0b", "\u5c71\u7530\u3000\u592a\u90ce", "co\xadop",
    "\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u0645",
    "\U0001f468\u200d\U0001f469\u200d\U0001f467", "a\u200bb", "\ufeffa",
    "\U000e0001", "\ue000", "\u0378", "\u2000\u2009\u202f\u205f"])
def test_spelled_keeps_what_a_terminal_can_be_shown(template, text):
    assert template.spelled(text) == text


@pytest.mark.parametrize("char, spelling", [
    ("\x00", r"\x00"), ("\x1b", r"\x1b"), ("\r", r"\r"), ("\n", r"\n"),
    ("\t", r"\t"), ("\x7f", r"\x7f"), ("\x85", r"\x85"), ("\x9f", r"\x9f"),
    ("\u2028", r"\u2028"), ("\u2029", r"\u2029"), ("\ud83d", r"\ud83d"),
    ("\udce9", r"\udce9"), ("\ud800", r"\ud800"), ("\udfff", r"\udfff"),
    # The bidirectional controls: the right-to-left override and mark, the
    # left-to-right mark, the Arabic letter mark, every embedding and isolate.
    ("\u202e", r"\u202e"), ("\u200f", r"\u200f"), ("\u200e", r"\u200e"),
    ("\u061c", r"\u061c"), ("\u202a", r"\u202a"), ("\u202b", r"\u202b"),
    ("\u202c", r"\u202c"), ("\u202d", r"\u202d"), ("\u2066", r"\u2066"),
    ("\u2067", r"\u2067"), ("\u2068", r"\u2068"), ("\u2069", r"\u2069")])
def test_spelled_writes_the_escape_python_spells(template, char, spelling):
    assert template.spelled(f"a{char}b") == f"a{spelling}b"


#: The code points `spelled` escapes, from the specification and not from the
#: implementation: the controls (Cc), the surrogates (Cs), the line and
#: paragraph separators (Zl, Zp), and the bidirectional controls.
ESCAPED_CODES = frozenset(
    {*range(0x00, 0x20), *range(0x7f, 0xa0), *range(0xd800, 0xe000),
     0x2028, 0x2029, 0x061c, 0x200e, 0x200f, *range(0x202a, 0x202f),
     *range(0x2066, 0x206a)})


def escape_of(code: int) -> str:
    """The escape Python spells `code` as: its own name for a tab, a line feed
    and a carriage return, else `\\xNN` or `\\uNNNN`."""
    named = {9: r"\t", 10: r"\n", 13: r"\r"}
    if code in named:
        return named[code]
    return rf"\x{code:02x}" if code < 0x100 else rf"\u{code:04x}"


def test_spelled_escapes_exactly_the_specified_characters(template):
    """EVERY code point, once, in one string: it is escaped when it is in the
    specified set and left alone when it is not. A character class by
    category (Cc, Cs, Zl, Zp) and not `str.isprintable`, so Zs, Cf, Co and Cn
    stay raw."""
    codes = range(sys.maxunicode + 1)
    expected = "".join(escape_of(code) if code in ESCAPED_CODES
                       else chr(code) for code in codes)
    assert template.spelled("".join(map(chr, codes))) == expected


def test_the_specified_set_is_the_four_categories_and_the_bidi_controls():
    """The test's own set agrees with the category names the spec gives, on
    this interpreter's Unicode database (the four categories are fixed ranges,
    so it holds on every one)."""
    categories = {code for code in range(sys.maxunicode + 1)
                  if unicodedata.category(chr(code)) in ("Cc", "Cs", "Zl", "Zp")}
    bidi = {0x061c, 0x200e, 0x200f, *range(0x202a, 0x202f), *range(0x2066, 0x206a)}
    assert ESCAPED_CODES == categories | bidi
    assert {unicodedata.category(chr(code)) for code in bidi} <= {"Cf"}


def test_spelled_takes_what_a_manifest_can_hold(template):
    """`name: 5` and `role: [a]` are values too: the text a print would have
    made of them, spelled."""
    assert template.spelled(5) == "5"
    assert template.spelled(None) == "None"
    assert template.spelled(["a\x1b"]) == "['a\\x1b']"
    assert template.spelled(Path("b\u2028")) == "b\\u2028"


def test_spelled_leaves_one_line_free_of_what_must_not_reach_a_terminal(
        template):
    every = "".join(chr(code) for code in (*range(0x100), 0x2028, 0x2029,
                                           0x202e, 0x200f, 0xd800, 0xdc80,
                                           0xdfff, 0xe000, 0xfeff, 0x1f642,
                                           0xe0001))
    out = template.spelled(every)
    assert "\n" not in out and not NEVER_RAW & set(out), out
    assert not {chr(code) for code in ESCAPED_CODES} & set(out), out


@pytest.mark.parametrize("errors, expected", [
    ("strict", "backslashreplace"),
    ("surrogateescape", "backslashreplace"),
    ("backslashreplace", "backslashreplace"),
    ("replace", "replace"),
    ("ignore", "ignore"),
    ("xmlcharrefreplace", "xmlcharrefreplace"),
    ("namereplace", "namereplace"),
])
def test_a_stdout_that_raises_is_made_to_escape_and_no_other_is_touched(
        template, monkeypatch, errors, expected):
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors=errors,
                              newline="\n")
    monkeypatch.setattr(sys, "stdout", stream)
    template.escape_unencodable_stdout()
    assert (stream.errors, stream.encoding) == (expected, "cp1252")
    print("\u65e5 \u2014", end="")
    stream.flush()
    written = stream.buffer.getvalue()
    if expected == "backslashreplace":
        assert written == b"\\u65e5 \x97", written


def test_a_stdout_that_cannot_be_reconfigured_fails_nothing(template,
                                                            monkeypatch):
    """No `reconfigure`, a closed stream and no stdout at all (`pythonw`)."""

    class Replaced:
        errors = "strict"

    for stdout in (Replaced(), None):
        monkeypatch.setattr(sys, "stdout", stdout)
        template.escape_unencodable_stdout()
    closed = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    closed.close()
    monkeypatch.setattr(sys, "stdout", closed)
    template.escape_unencodable_stdout()


def source_of(path: Path, name: str) -> str:
    """The source of the module-level function or assignment called `name`."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")

    def named(node: ast.stmt) -> bool:
        if isinstance(node, ast.FunctionDef):
            return node.name == name
        return (isinstance(node, ast.Assign)
                and [target.id for target in node.targets
                     if isinstance(target, ast.Name)] == [name])

    node = next(node for node in ast.parse(text).body if named(node))
    return ast.get_source_segment(text, node)


@pytest.mark.parametrize("name", ["escape_unencodable_stdout", "spelled",
                                  "ESCAPED_CATEGORIES",
                                  "ESCAPED_BIDI_CONTROLS"])
def test_the_two_roots_carry_the_same_function(name):
    """Both files are shape copies that cannot import anything of this
    repository's, so the helper is written twice; this is what keeps it one.
    The two sets `spelled` reads are part of it."""
    assert (source_of(ASSEMBLY_TEMPLATE, name)
            == source_of(FAMILY_TEMPLATE, name)), name


@pytest.mark.parametrize("path", [ASSEMBLY_TEMPLATE, FAMILY_TEMPLATE],
                         ids=["assembly-root", "family-root"])
def test_main_escapes_stdout_before_it_prints_or_parses_anything(path):
    """The reconfigure is `main`'s FIRST statement: `--help` and an argument
    error print too."""
    text = path.read_text(encoding="utf-8")
    main = next(node for node in ast.parse(text).body
                if isinstance(node, ast.FunctionDef) and node.name == "main")
    first = main.body[0]
    assert ast.unparse(first) == "escape_unencodable_stdout()", ast.unparse(first)
