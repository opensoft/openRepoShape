# SPDX-License-Identifier: Apache-2.0
"""`--elected-by`, `--reference` and `--name` are asked, before anything
exists, whether a file can hold them (#282).

The scaffold writes each of the three into the assembly root's
`project.yaml` and `README.md`, and `--name` into each repository's
`AGENTS.md` and each first commit's message as well. Since #284 the manifest
spells a value with `double_quoted`, so it reads back exactly whatever it
holds; the README, the `AGENTS.md` files and the commit messages take it as
it stands. So on main:

  * a byte that is not UTF-8 (a lone surrogate once Python decodes argv or
    the environment) raised `UnicodeEncodeError` in `write_lf`, exit 1,
    after both legs were pushed and the assembly root created empty, or,
    in `--name`, after all three repositories were created; and one in
    `git config user.name`, the elector's last fallback, raised
    `UnicodeDecodeError` in `git_out`, a traceback under `--dry-run` too;
  * a line break (LF, CR LF, U+0085, U+2028, U+2029) scaffolded, exit 0,
    and split the README's line, each `AGENTS.md`'s first line, each
    commit's subject and the `manifest ok:` line the project's own
    validator prints;
  * a control character or a bidi embedding, override or isolate control
    scaffolded and was written raw into the README.

Now each is refused as `scaffold-unwritable-value`, by the flag it came
from or by the fallback the elector took, before a work directory, a remote
or any process exists, and under `--dry-run` alike. The question is
`shape_materialize.unwritable_reason`, the one `adopt-project.py` asks of
the same values (#255), so a backslash, a double quote and a Persian name
joined with U+200C ZERO WIDTH NON-JOINER still scaffold, and read back.

NO NETWORK AND NO GITHUB: `scaffold-project.py` is loaded as a module and
its `main()` run here under a guard that fails the test if any process is
started, or run as a child into local bare repositories
(`--local-remote-dir`), which never calls `gh`. Every invisible character
in this file is spelled as an escape: a reader cannot see one typed raw, and
a raw bidi control reorders the line it is on.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys

import pytest

from conftest import (ORG, REPO, SCAFFOLD, blank_unnamed_pin_sources,
                      run_script)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml  # noqa: E402

PROJECT = "Atlas"
REFUSED = "REFUSED scaffold-unwritable-value: "
REMEDIATION = ("\nRemediation: nothing was created, and `--dry-run` refuses "
               "the same.")
#: Where the refusal says each value is written.
MANIFEST_AND_README = ("which the scaffold writes into the assembly root's "
                       "`project.yaml` and `README.md`, and ")
NAME_WRITTEN = ("which the scaffold writes into the assembly root's "
                "`project.yaml` and `README.md`, each repository's "
                "`AGENTS.md` and each first commit's message, and ")
WRITTEN = {"--elected-by": MANIFEST_AND_README,
           "--reference": MANIFEST_AND_README, "--name": NAME_WRITTEN}
FROM_ENV = "--elected-by (not given, so GIT_AUTHOR_NAME)"
FROM_CONFIG = "--elected-by (not given, so `git config user.name`)"

LINE_BREAK = "it holds a line break, and it is written as one line"
NOT_UTF8 = "it holds a byte that is not UTF-8"
CONTROL = "it holds a control character"
BIDI = ("it holds a bidirectional control (an embedding, override or "
        "isolate), which shows the rest of the line in another order than "
        "it is written")

#: `(id, value, reason)`: each value no file can hold as one line of text,
#: and the reason `unwritable_reason` gives. `\udce9` is how Python keeps
#: the byte 0xE9 of a command line or an environment that is not UTF-8.
UNWRITABLE = [
    ("lf", "Ada\nLovelace", LINE_BREAK),
    ("crlf", "Ada\r\nLovelace", LINE_BREAK),
    ("u0085", "Ada\x85Lovelace", LINE_BREAK),
    ("u2028", "Ada\u2028Lovelace", LINE_BREAK),
    ("u2029", "Ada\u2029Lovelace", LINE_BREAK),
    ("not-utf8", "Jos\udce9", NOT_UTF8),
    ("u0001", "a\x01b", CONTROL),
    ("esc", "a\x1bb", CONTROL),
    ("del", "a\x7fb", CONTROL),
    ("tab", "a\tb", CONTROL),
    ("u202e", "\u202eevil", BIDI),
    ("u2066-u2069", "ref \u2066x\u2069 y", BIDI),
]
UNWRITABLE_IDS = [row[0] for row in UNWRITABLE]
FLAGS = ["--elected-by", "--reference", "--name"]

#: Text a file holds that the manifest must read back exactly: a backslash
#: (`CORP\nick` is a domain account, not a line feed), a Windows path, a
#: double quote, and a Persian name joined with U+200C.
WRITABLE = [
    ("backslash", "CORP\\nick"),
    ("windows-path", "C:\\docs\\notes\\new.md"),
    ("double-quote", 'Joe "JJ" Smith'),
    ("zwnj", "Mehr\u200cdad"),
    ("accent", "Jos\u00e9"),
]


@pytest.fixture(scope="module")
def scaffold():
    """`scaffold-project.py` loaded as a module, so `main()` runs here."""
    module_spec = importlib.util.spec_from_file_location(
        "scaffold_free_text_values", SCAFFOLD)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


class ProcessStarted(AssertionError):
    """A process was started where the refusal should already have come."""


@pytest.fixture
def no_process(monkeypatch):
    """Every command the scaffold runs starts through `subprocess.Popen`.
    While this holds, starting one fails the test and names it, so a
    refusal that passes came before the first `git` or `gh` and before the
    work directory, on every platform."""
    def refuse(args, *_, **__):
        raise ProcessStarted(f"a process was started: {args!r}")
    monkeypatch.setattr(subprocess, "Popen", refuse)


def argv(tmp_path, *flags: str, dry_run: bool = True) -> list[str]:
    """The scaffold's command line into `tmp_path`, with `flags`, and an
    elector unless `flags` name one or say there is none."""
    elector = ([] if "--elected-by" in flags or "--no-elector" in flags
               else ["--elected-by", "Test Human"])
    flags = tuple(flag for flag in flags if flag != "--no-elector")
    return ["--org", ORG, "--project", PROJECT, "--elected-on", "2026-09-02",
            "--local-remote-dir", str(tmp_path / "remotes"),
            "--work-dir", str(tmp_path / "work"), *elector, *flags,
            *(["--dry-run"] if dry_run else [])]


def refusal(scaffold, capsys, args: list[str]) -> str:
    """`main(args)`: exit 2, nothing on stdout (the plan is never printed),
    and the refusal on stderr, which this returns."""
    code = scaffold.main(args)
    out, err = capsys.readouterr()
    assert (code, out) == (2, ""), err
    assert err.startswith(REFUSED), err
    assert REMEDIATION in err, err
    return err


def assert_nothing_created(tmp_path) -> None:
    for made in ("remotes", "work"):
        assert not (tmp_path / made).exists(), f"{made} was created"


# --- each flag, before anything exists and under `--dry-run` alike ----------

@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real"])
@pytest.mark.parametrize("flag", FLAGS)
@pytest.mark.parametrize("label, value, reason", UNWRITABLE,
                         ids=UNWRITABLE_IDS)
def test_a_flag_no_file_can_hold_is_refused_before_anything_starts(
        scaffold, no_process, capsys, tmp_path, flag, label, value, reason,
        dry_run):
    """The issue's rows, each through each flag. On main a surrogate raised
    in `write_lf` once the legs (for `--name`, all three repositories)
    existed, and the rest scaffolded with the value raw in the README. The
    refusal names the flag, the value as Python spells it, where it is
    written and why it cannot be."""
    err = refusal(scaffold, capsys,
                  argv(tmp_path, flag, value, dry_run=dry_run))
    assert err.startswith(
        f"{REFUSED}{flag} is {value!r}, {WRITTEN[flag]}{reason}.\n"), err
    assert_nothing_created(tmp_path)


def test_every_value_no_file_can_hold_is_named_in_one_refusal(
        scaffold, no_process, capsys, tmp_path):
    """Three bad values are one refusal naming all three, in the order the
    issue lists them, so a person retypes them once and not three times."""
    err = refusal(scaffold, capsys, argv(
        tmp_path, "--name", "Jos\udce9", "--reference", "a\nb",
        "--elected-by", "\u202eevil", dry_run=False))
    first_line = err.splitlines()[0]
    assert first_line == (
        f"{REFUSED}--elected-by is '\\u202eevil', {MANIFEST_AND_README}{BIDI}. "
        f"--reference is 'a\\nb', {MANIFEST_AND_README}{LINE_BREAK}. "
        f"--name is 'Jos\\udce9', {NAME_WRITTEN}{NOT_UTF8}."), err
    assert_nothing_created(tmp_path)


# --- the elector's fallback ---------------------------------------------------

@pytest.mark.parametrize("label, value, reason", UNWRITABLE,
                         ids=UNWRITABLE_IDS)
def test_an_elector_from_git_author_name_is_asked_and_named(
        scaffold, no_process, capsys, tmp_path, monkeypatch, label, value,
        reason):
    """`GIT_AUTHOR_NAME` answers when `--elected-by` is not given, and the
    refusal says so rather than naming a flag nobody typed. It is read from
    the environment, so no process is started before the refusal either."""
    monkeypatch.setenv("GIT_AUTHOR_NAME", value)
    err = refusal(scaffold, capsys,
                  argv(tmp_path, "--no-elector", dry_run=False))
    assert err.startswith(
        f"{REFUSED}{FROM_ENV} is {value.strip()!r}, "
        f"{MANIFEST_AND_README}{reason}.\n"), err
    assert_nothing_created(tmp_path)


def user_name(monkeypatch, value: str) -> None:
    """`git config user.name` answers `value`, given as command-line config
    (`GIT_CONFIG_COUNT`, git 2.31), which no config file overrides, and
    `GIT_AUTHOR_NAME` is blank so the elector falls back that far."""
    monkeypatch.setenv("GIT_AUTHOR_NAME", "  ")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "user.name")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", value)


CONFIG_VALUES = [
    pytest.param("Ada\nLovelace", LINE_BREAK, id="lf"),
    pytest.param("\u202eevil", BIDI, id="u202e"),
    pytest.param("a\x1bb", CONTROL, id="esc"),
    # Windows has no byte that is not UTF-8 in its environment: it is UTF-16,
    # and git for Windows converts it to UTF-8 itself.
    pytest.param("Jos\udce9", NOT_UTF8, id="not-utf8",
                 marks=pytest.mark.skipif(
                     os.name == "nt",
                     reason="a POSIX environment's bytes; Windows' is "
                            "UTF-16 and git for Windows converts it")),
]


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real"])
@pytest.mark.parametrize("value, reason", CONFIG_VALUES)
def test_an_elector_from_git_config_is_asked_and_named(
        scaffold, capsys, tmp_path, monkeypatch, value, reason, dry_run):
    """The last fallback, `git config user.name`, and a GIT_AUTHOR_NAME of
    whitespace alone, which `_elector` strips to nothing and passes over. On
    main a byte that is not UTF-8 there raised `UnicodeDecodeError` out of
    `git_out`, a traceback in place of a refusal, under `--dry-run` too."""
    user_name(monkeypatch, value)
    err = refusal(scaffold, capsys,
                  argv(tmp_path, "--no-elector", dry_run=dry_run))
    assert err.startswith(
        f"{REFUSED}{FROM_CONFIG} is {value!r}, "
        f"{MANIFEST_AND_README}{reason}.\n"), err
    assert_nothing_created(tmp_path)


def test_the_flag_answers_before_either_fallback_and_is_named(
        scaffold, no_process, capsys, tmp_path, monkeypatch):
    """`--elected-by` wins over GIT_AUTHOR_NAME and `git config user.name`,
    so a bad flag is named as the flag, and a bad fallback it overrides is
    never asked at all."""
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Jos\udce9")
    err = refusal(scaffold, capsys, argv(
        tmp_path, "--elected-by", "a\nb", dry_run=False))
    assert err.startswith(
        f"{REFUSED}--elected-by is 'a\\nb', {MANIFEST_AND_README}"
        f"{LINE_BREAK}.\n"), err
    assert "GIT_AUTHOR_NAME)" not in err.splitlines()[0]


# --- what still scaffolds -----------------------------------------------------

@pytest.mark.parametrize("flag", FLAGS)
@pytest.mark.parametrize("label, value", WRITABLE,
                         ids=[row[0] for row in WRITABLE])
def test_text_a_file_holds_is_not_refused(scaffold, capsys, tmp_path, flag,
                                          label, value):
    """A backslash, a double quote, an accent and U+200C are text: the dry
    run plans them, exit 0, and the plan shows the value as typed."""
    code = scaffold.main(argv(tmp_path, flag, value))
    out, err = capsys.readouterr()
    assert code == 0, err
    assert "--dry-run: nothing was created." in out
    assert value in out, out
    assert_nothing_created(tmp_path)


def test_a_scaffold_writes_backslashes_quotes_and_a_zwnj_exactly(tmp_path):
    """End to end into local bare remotes: the values that are text, through
    each flag and through GIT_AUTHOR_NAME (a backslash there is the issue's
    `CORP\\nick`), are recorded exactly, and each line of the README and of
    every `AGENTS.md` that holds one is still one line."""
    remotes, work = tmp_path / "remotes", tmp_path / "work"
    name = "Mehr\u200cdad \"MJ\" Rostami"
    reference = "C:\\docs\\notes\\new.md"
    elected_by = "CORP\\nick"
    result = run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                        "--name", name, "--reference", reference,
                        "--elected-on", "2026-09-02",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(work),
                        env={"GIT_AUTHOR_NAME": elected_by})
    assert result.returncode == 0, result.stderr + result.stdout
    root = work / PROJECT
    check = run_script(root / "scripts" / "validate-manifest.py", cwd=root)
    assert check.returncode == 0, check.stderr + check.stdout
    manifest = load_yaml(root / "project.yaml")
    assert (manifest["name"], manifest["reference"],
            manifest["elected_by"]) == (name, reference, elected_by)
    # Bytes the scaffold wrote, never a file a helper rewrote: each value is
    # on the line its template gives it, and no line was added.
    readme = (root / "README.md").read_bytes().decode("utf-8").splitlines()
    assert readme[0] == f"# {name}"
    assert any(f"Elected by {elected_by} on 2026-09-02" in line
               for line in readme), readme[:12]
    assert f"`{reference}`." in readme
    template = (REPO / "templates" / "assembly-root" / "README.md")
    assert len(readme) == len(
        template.read_bytes().decode("utf-8").splitlines())
    for leg, role in ((f"{PROJECT}-spec", "spec"), (f"{PROJECT}-code", "code")):
        first = (work / leg / "AGENTS.md").read_bytes().decode(
            "utf-8").splitlines()[0]
        assert first.startswith(f"This is the **{role} leg** of {name} ("), first
        subject = subprocess.run(
            ["git", "log", "-1", "--format=%B"], cwd=str(work / leg),
            capture_output=True, check=True).stdout.decode("utf-8")
        assert subject.splitlines()[0] == f"Seed the {role} leg of {name}"


# --- end to end, as the issue ran it ------------------------------------------

def child(*args: str) -> tuple[int, str]:
    """The scaffold as a child process, as `conftest.run_script` runs one,
    answered in BYTES and read with `backslashreplace`: on main its
    traceback carries the byte that is not UTF-8, which is not text to
    decode, and the assertion should name the traceback, not a decode."""
    env = blank_unnamed_pin_sources({**os.environ, "LANES_LANE": ""}, {})
    for key, value in (("GIT_AUTHOR_NAME", "openRepoShape tests"),
                       ("GIT_AUTHOR_EMAIL", "tests@openreposhape.invalid"),
                       ("GIT_COMMITTER_NAME", "openRepoShape tests"),
                       ("GIT_COMMITTER_EMAIL", "tests@openreposhape.invalid")):
        env.setdefault(key, value)
    done = subprocess.run([sys.executable, str(SCAFFOLD), *args],
                          capture_output=True, env=env,
                          stdin=subprocess.DEVNULL, check=False)
    return done.returncode, done.stderr.replace(b"\r\n", b"\n").decode(
        "utf-8", "backslashreplace")


@pytest.mark.parametrize("flag", FLAGS)
def test_a_byte_that_is_not_utf8_creates_nothing_and_raises_nothing(
        tmp_path, flag):
    """The issue's last two rows, as a person runs them: a child process
    whose argv carries the byte. On main `--elected-by` and `--reference`
    pushed both legs and left the root created and empty, and `--name`
    created all three repositories, each before `write_lf` raised; the
    corrected re-run was then refused `scaffold-remote-exists`."""
    code, err = child(*argv(tmp_path, flag, "Jos\udce9", dry_run=False))
    assert "Traceback" not in err, err
    assert code == 2, err
    assert err.startswith(
        f"{REFUSED}{flag} is 'Jos\\udce9', {WRITTEN[flag]}{NOT_UTF8}.\n"), err
    assert_nothing_created(tmp_path)
