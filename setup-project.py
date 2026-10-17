#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""setup-project.py - clone the standard into a temp dir, scaffold, clean up.

The NATIVE WINDOWS way in, and what `setup.sh` runs everywhere else:

    Invoke-WebRequest https://raw.githubusercontent.com/opensoft/openRepoShape/main/setup-project.py -OutFile setup-project.py
    py setup-project.py <Project> --org <your-org>

Run from wherever: if this is not already a checkout of openRepoShape it
self-bootstraps - clones `opensoft/openRepoShape` (or `$OPENREPOSHAPE_REPO`,
for a fork or mirror) into a temporary directory, re-runs itself from there
with the same arguments, and removes the temporary checkout on exit
(`--keep-shape-checkout` keeps it and prints the path). `--org` is then
REQUIRED: there is no fork origin left to read it from. Run it from inside an
existing checkout instead (the developer path) and it detects the organisation
from that checkout's `origin` remote.

Either way it checks your machine, works out which organisation you are
scaffolding into, checks the three repository names against the naming policy,
shows you the plan, asks once, creates the three repositories, clones the
assembly root and bootstraps it. Nothing is created before you have said yes.

WHY THIS FILE IS THE FLOW AND `setup.sh` IS NOT. It arrived as the second
entry point, for Windows: bash is not there, and neither is the `python3` a
shell script has to name - the python.org installer puts `python.exe` and the
`py` launcher on PATH and no `python3` at all, and there is no `make` either.
So this file runs the RUNNING interpreter (`sys.executable`) for every child
process and `scripts/bootstrap.py` directly instead of `make bootstrap`, and
it prints a `REFUSED:` line naming which child failed - the plan, the
scaffold, the clone or the bootstrap - and what was already created, where
`set -e` in a shell script would end the run silently.

Two entry points that refuse different things in different words are two
standards, so #50 settled which of them is the flow. `setup.sh` is a shim now:
it finds an interpreter, clones this standard when the person has no checkout
of it, and hands over here. There is ONE parser, one usage banner and one set
of refusal wordings, and `tests/test_setup_sh.py` drives them through bash
where `tests/test_setup_project_py.py` drives them through an interpreter
alone.

THE `setup.sh:NNN` CITATIONS BELOW NAME setup.sh AS IT STOOD BEFORE #50, the
500-line implementation this file was transcribed from. They are kept because
they say where each rule came from; the shim that replaced it holds only what
became its section 0.

PURE ASCII IN THE SOURCE, AND IN EVERY FIXED MARKER AND MESSAGE THIS FILE
WRITES ITSELF. Windows PowerShell 5.1 - still the default shell on a stock
Windows install - renders a console in the machine's ANSI code page,
re-encodes piped text as ASCII (its default `$OutputEncoding`), and writes
UTF-16 when `>` redirects to a file. No byte above 0x7F survives all three,
so a tick, an arrow or an em dash in this file's own source would arrive as
mojibake, as a question mark, or raise an encoding error on the way out -
which is why `[ok]` and `[!!]` are spelled that way instead of with a real
tick and cross.

A value the script only ECHOES BACK (`--elected-by`, `git config
user.name`) and a CHILD PROCESS'S OWN OUTPUT are not this guarantee's to
keep: they are whatever bytes they already are, and `main()` writes them
through a UTF-8 `errors="replace"` stream rather than mangling or refusing
on a byte this file never chose.

`tests/test_repo_hygiene.py::test_setup_project_py_is_pure_ascii` holds the
source.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

UPSTREAM_ORG = "opensoft"
DEFAULT_SHAPE_REPO = "https://github.com/opensoft/openRepoShape.git"
VISIBILITY_CHOICES = ("private", "public", "internal")

#: The files of the standard this entry point runs or looks for, each named
#: ONCE. `SCAFFOLD` is both what `is_shape_checkout` recognises a checkout by
#: and what steps (5) and (6) execute, so a rename that reached two of the
#: three uses and not the third would leave this file looking for a checkout
#: it then could not scaffold from.
SCAFFOLD = "scaffold-project.py"
NAMING_VALIDATOR = "validate-repository-naming.py"

#: A FAMILY HOLDER'S MANIFEST, and the `kind:` that makes a directory a
#: family FOLDER rather than a directory with a family's name on it. Both are
#: written by `scripts/family.py init`; nothing here writes either.
FAMILY_MANIFEST = "family.yaml"
FAMILY_KIND = "family-manifest"

#: A FORWARD SLASH, on every platform, because this string is both run and
#: PRINTED - in the preflight line and in the recovery command a person is
#: told to retype. Windows opens `scripts/bootstrap.py` as readily as
#: `scripts\bootstrap.py`, and one spelling means the command in the message
#: is the command that ran.
BOOTSTRAP = "scripts/bootstrap.py"

#: `[ok]` and `[!!]` where setup.sh prints a tick and a cross. See the
#: PURE ASCII paragraph above: the characters, not the meaning, are the
#: difference. `[??]` has no twin in setup.sh: it marks a MACHINE SETTING
#: worth looking at, where `[!!]` marks a missing prerequisite that will
#: refuse the run.
TICK = "[ok]"
CROSS = "[!!]"
QUERY = "[??]"

#: The interpreter that is running THIS file, for every child process it
#: starts. Never a probe for an interpreter on PATH: the one that got here is
#: the one that works, and on Windows the name it answers to is `python.exe`
#: or `py`, not a name a shell script could have hard-coded.
PYTHON = sys.executable

#: THE PLATFORM'S CONVENTIONAL COMMAND, spelled for a HUMAN TO RETYPE - never
#: the running interpreter's basename. A basename need not be on PATH at
#: all: inside a virtualenv `sys.executable` is `.../venv/bin/python`, and a
#: Debian box without `python-is-python3` has no bare `python` to type.
#: `python3` is the command every POSIX install of a supported Python
#: answers to, and `python` is what both python.org and the Microsoft Store
#: put on PATH on Windows - exactly `scripts/repo_shape.py`'s `PYTHON`
#: constant. argv keeps `PYTHON` (`sys.executable`); prose gets this.
PYTHON_CMD = "python" if os.name == "nt" else "python3"


USAGE = """usage: setup-project.py [<Project>] [options] [-- <extra scaffold flags>]

  <Project>               the assembly-root name, as a positional. Exactly
                          the same thing as --project; give one or the other.
  --project <Project>     the assembly-root name: ONE CamelCase token, no
                          hyphen, underscore, dot or space. Prompted for when
                          omitted and a terminal is attached.
  --id <id>               lowercase project id      (default: project lowercased)
  --name "<Display>"      display name              (default: the project name)
  --visibility private|public|internal              (default: private)
  --elected-by "<Name>"   who is electing the shape (default: your gh login)
  --family <Family>       the FAMILY HOLDER this project joins: one CamelCase
                          token, the holder's own name. The clone lands at
                          <into>/<Family>/<Project> instead of
                          <into>/<Project>, and <into>/<Family>/ is created if
                          it is not there. Already standing IN the family
                          folder? Then it lands at <into>/<Project>: a family
                          is never nested inside a family. It records NOTHING
                          in the project - membership is recorded only in the
                          holder's family.yaml, and the next commands name the
                          `family.py add` that writes it.
  --into <dir>            PARENT directory for the clone (default: ..; in
                          self-bootstrap mode, the directory you ran this
                          from), so the clone lands at <dir>/<Project>
  --org <org>             override the detected organisation. REQUIRED when
                          run outside a checkout of openRepoShape
                          (self-bootstrap mode): there is no origin to read it
                          from.
  --allow-upstream-org    permit `--org opensoft` itself: opensoft is the
                          upstream owner of openRepoShape, and almost never
                          what you meant to scaffold into.
  --shape-ref <ref>       self-bootstrap mode only: clone this commit or tag
                          of the standard instead of its default branch.
  --keep-shape-checkout   self-bootstrap mode only: do not delete the
                          temporary checkout on exit; print its path instead.
  --yes                   skip the confirmation prompt. It answers the ONE
                          question about creating three repositories, and
                          never an offer to install something.
  --preflight             check this machine and stop: the preflight and
                          the offers it makes, nothing else. Exit 0 when
                          everything is there, 1 when it is not. Creates
                          nothing, and needs no <Project> and no --org.
  --local-remote-dir <d>  TEST PATH: create three BARE repositories in <d> and
                          use them as origins. No network, no `gh`, and no real
                          repository is created.
  -h, --help              this text

Set $OPENREPOSHAPE_REPO to clone a fork or mirror in self-bootstrap mode
instead of opensoft/openRepoShape.

Anything after `--` is passed straight through to scaffold-project.py. A
`--dry-run` there ends this run at the plan, creating nothing.
"""


class Refusal(Exception):
    """A refusal with an exit code, so `main` returns rather than exits.

    setup.sh's `die` prints and exits in place. Here the message and the code
    travel together to one handler at the bottom, which is what lets a
    self-bootstrap `finally:` still delete its temporary checkout when the
    child refuses.
    """

    def __init__(self, message: str, code: int = 2):
        super().__init__(message)
        self.code = code


def usage(stream=None) -> None:
    print(USAGE, end="", file=stream or sys.stdout, flush=True)


def say(text: str = "") -> None:
    print(text, flush=True)


def ok(text: str) -> None:
    print("  %s %s" % (TICK, text), flush=True)


def bad(text: str) -> None:
    print("  %s %s" % (CROSS, text), file=sys.stderr, flush=True)


def warn(text: str) -> None:
    """`[??]`: look at this, but the run continues.

    Distinct from `bad()` on purpose. `[!!]` is a missing prerequisite and the
    preflight refuses on it; `[??]` is a setting on the machine that will
    make something later confusing, and refusing on it would be this tool
    declining to run because it disliked somebody's ~/.gitconfig.
    """
    print("  %s %s" % (QUERY, text), file=sys.stderr, flush=True)


def die(message: str, code: int = 2) -> None:
    raise Refusal(message, code)


def shell_status(code: int) -> int:
    """A child's returncode as an exit STATUS, the way a shell reports one.

    `subprocess` reports a child killed by a signal as the NEGATIVE signal
    number: Ctrl-C in a child is -2. An exit status is one byte, and every
    shell - `setup.sh`'s included, because that is what `set -e` propagates -
    renders a signalled child as 128 plus the signal, so -2 is 130. Handing
    -2 to `sys.exit` would exit 254 instead, which is a number nobody can
    look up.
    """
    return code if code >= 0 else 128 - code


def abspath(value: str, invocation_dir: str) -> str:
    """setup.sh:103-108, exactly: relative paths hang off the INVOCATION dir.

    `os.path.abspath`, never `Path.resolve()`. On Windows `resolve()` also
    rewrites 8.3 short components (`RUNNER~1`) into their long form, so a path
    the person typed and a path the tool printed would not compare equal - and
    the tests compare them.
    """
    return os.path.abspath(os.path.join(invocation_dir, value))


def rmtree(path) -> None:
    """`shutil.rmtree` that also works over a git object store on Windows.

    Git writes loose objects and packs READ-ONLY and Windows refuses to unlink
    a read-only file, so the plain call raises PermissionError there and
    succeeds everywhere else. `onerror` rather than `onexc`: the newer
    spelling is 3.12+, and this standard runs on 3.9.
    """

    def clear_readonly(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    shutil.rmtree(path, onerror=clear_readonly)


def run(argv, cwd=None, capture: bool = False,
        stdin=None) -> subprocess.CompletedProcess:
    """One spelling of "run a program", with the output decoding pinned.

    `encoding="utf-8", errors="replace"`: a child's bytes are its own business
    and a mojibake byte in a `git --version` string must not raise out of the
    preflight. Output is INHERITED unless `capture` asks otherwise, so
    `scaffold-project.py` and the validators print straight to the terminal
    the way they do under setup.sh. So is stdin, unless `stdin` names a file
    descriptor: `run_at_the_terminal` is the one caller that does.

    EVERY ARGV THAT CARRIES A VALUE FROM THE COMMAND LINE WAS CHECKED AT PARSE
    TIME. `argv` is a list and `shell=False`, so there is no shell to inject
    into - but git reads its own arguments, which is the injection that is
    real. `checked_value` is where that is refused, and why.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        return subprocess.run(argv, cwd=str(cwd) if cwd is not None else None,
                              capture_output=capture, text=True,
                              encoding="utf-8", errors="replace", check=False,
                              stdin=stdin)
    except OSError:
        # A PROGRAM THAT IS NOT THERE IS A FAILED RUN, not a traceback.
        # `is_shape_checkout()` asks git a question before the preflight has
        # said a word, and the single most likely state a first-run Windows
        # machine is in is "Python installed, Git for Windows not yet" - the
        # person downloaded this file with the thing they already had. 127 is
        # what a shell reports for a command it could not find, so every
        # caller that already treats a non-zero returncode as failure treats
        # this one identically.
        return subprocess.CompletedProcess(argv, 127, "", "")


def program_version(argv, field: int) -> str:
    """`git --version` -> `2.43.0`; the awk in setup.sh:219 and :246.

    SLICES, NEVER INDEXES. Every one of these reads can come up short: a
    program that is not installed at all returns the 127 and the empty stdout
    `run` invents for it, and a program that answers `--version` with fewer
    words than expected is a program, not an exception. An out-of-range SLICE
    is empty where an index raises, so `join` gives back either the word or
    the empty string the words below stand in for - which is what awk does
    with `$3` of a line that has two fields, and what setup.sh therefore does.
    """
    proc = run(argv, capture=True)
    lines = (proc.stdout or "").splitlines()
    parts = " ".join(lines[:1]).split()
    return " ".join(parts[field:field + 1]) or "(unknown version)"


# ---------------------------------------------------------------------------
# arguments
# ---------------------------------------------------------------------------

#: What a NAME may contain - a project, an organisation, an id, a display
#: name, the person electing the shape. Deliberately PERMISSIVE: CamelCase,
#: kebab-case, snake_case and `Display Name` are all legitimate spellings
#: here, and which of them this standard actually accepts is the naming
#: POLICY's ruling, made at step (4) by `scripts/validate-repository-naming.py
#: --explain` and never re-implemented here. This says only what may become an
#: argument at all.
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._'()&,+@-]{0,254}$")

#: What a git REF may contain, conservatively: `--shape-ref` becomes
#: `git checkout <ref>` in the temporary checkout. `git check-ref-format` is
#: the authority; this is the subset of it that a person types.
REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,254}$")

#: What a PATH may contain: whatever the filesystem it names accepts - a drive
#: letter, a UNC prefix, a space, a `~`, a directory somebody else created in
#: a language of their own. Only the two things that are never a path are
#: refused: a control character here, and a leading `-` in `checked_value`.
PATH_RE = re.compile(r"^[^\x00-\x1f\x7f]+$")

#: A control character or a DEL, in any value at all. The newline is the one
#: that matters: it ends a line in every terminal, prompt and log this output
#: reaches, so a value carrying one can print a sentence that reads as this
#: tool's own - a `REFUSED:` line nobody refused.
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def refuse_value(what: str, text: str) -> None:
    """ONE wording for every value this tool will not pass on.

    `ascii()`, never `%r`: `repr` leaves a printable non-ASCII character as
    itself, and this file's output is ASCII to the byte (see the module
    docstring). `ascii()` escapes it, so the refusal can quote back exactly
    what arrived - a newline included - without becoming the mojibake the
    PURE ASCII rule exists to prevent.
    """
    die("%s is %s, which is not a value this tool will put on a `git` or `gh` "
        "command line. git reads its own arguments: a value that starts with "
        "`-` is an option to git, not a name to us; the rest must be spellable "
        "as a name, a ref or a path." % (what, ascii(text)))


def checked_value(flag: str, value: str, pattern=NAME_RE) -> str:
    """Check one value from the command line BEFORE it can become an argument.

    ARGUMENT INJECTION IS THE THREAT, NOT SHELL INJECTION. Every command here
    is a list run with `shell=False`, so there is no shell to inject into -
    but git reads its own arguments, and a value that starts with `-` is an
    option to git, not a name to us: `--upload-pack=...` is a command rather
    than a ref. An empty value is refused with it (a name nobody typed), and
    so is a control character (a newline prints a line this tool did not
    write).

    THE HOUSE PATTERN, COPIED RATHER THAN IMPORTED. `scripts/repo_shape.py`'s
    `checked_value` is the same check in the same words for the same reason,
    and `scaffold-project.py` calls it on the values this file forwards. This
    entry point cannot import it: it runs BEFORE there is a checkout to import
    it from, which is the whole of self-bootstrap mode.
    """
    text = str(value)
    if (not text or text.startswith("-") or CONTROL_RE.search(text)
            or not pattern.fullmatch(text)):
        refuse_value(flag, text)
    return text


def checked_ref(flag: str, value: str) -> str:
    """`--shape-ref`: narrower than a name, because git reads more into one.

    `..` is a revision RANGE rather than a ref, and a ref ending in `.lock` is
    the name git gives the lock file it writes beside one - neither is a thing
    to check out, and both are refused here rather than discovered as a
    confusing failure inside the temporary checkout.
    """
    text = checked_value(flag, value, REF_RE)
    if ".." in text or text.endswith(".lock"):
        refuse_value(flag, text)
    return text


def checked_path(flag: str, value: str) -> str:
    """`--into` and `--local-remote-dir`: a directory, not a name."""
    return checked_value(flag, value, PATH_RE)


def checked_passthrough(rest: list) -> list:
    """Everything after `--`, which is documented as extra scaffold flags.

    A leading `-` is the POINT here and is not refused - these ARE flags, and
    `scaffold-project.py` is the program that decides whether it has them. A
    control character still is: a newline in an argument prints a line this
    tool did not write, whichever program the argument was meant for.
    """
    for item in rest:
        if CONTROL_RE.search(item):
            refuse_value("a passthrough argument after `--`", item)
    return rest


class Options:
    """The parsed command line. One attribute per setup.sh variable."""

    def __init__(self):
        self.project = ""
        self.org = ""
        self.project_id = ""
        self.display_name = ""
        self.visibility = "private"
        self.elected_by = ""
        self.family = ""
        self.into = ""
        self.local_remote_dir = ""
        self.assume_yes = False
        self.preflight = False
        self.allow_upstream_org = False
        self.shape_ref = ""
        self.keep_shape_checkout = False
        self.passthrough = []
        self.help = False

    @property
    def local_mode(self) -> bool:
        return bool(self.local_remote_dir)


#: Every flag that takes a value: the `Options` attribute it fills, and the
#: check its value passes on the way in. `None` is `--visibility`, an enum
#: whose value is checked against VISIBILITY_CHOICES at the end of the parse -
#: a fixed set of three needs no shape.
VALUE_FLAGS = {
    "--project": ("project", checked_value),
    "--org": ("org", checked_value),
    "--id": ("project_id", checked_value),
    "--name": ("display_name", checked_value),
    "--visibility": ("visibility", None),
    "--elected-by": ("elected_by", checked_value),
    "--family": ("family", checked_value),
    "--into": ("into", checked_path),
    "--local-remote-dir": ("local_remote_dir", checked_path),
    "--shape-ref": ("shape_ref", checked_ref),
}

#: The value-taking flags that name a DIRECTORY, whose value hangs off the
#: invocation directory when it is relative (setup.sh:103-108, `abspath`).
PATH_FLAGS = ("--into", "--local-remote-dir")

#: Every flag that takes no value: the `Options` attribute it sets True.
BOOLEAN_FLAGS = {
    "--yes": "assume_yes",
    "-y": "assume_yes",
    "--preflight": "preflight",
    "--allow-upstream-org": "allow_upstream_org",
    "--keep-shape-checkout": "keep_shape_checkout",
}


class Parsing:
    """The parse's own state: the Options being filled, and two things that
    are not on it.

    `positional` is WHICH SPELLING set the project, because the two do not
    compose the same way. `--project A --project B` is B, exactly as setup.sh's
    last-wins `case` is. But a positional and a `--project` are two different
    names for one thing, and silently taking either is how a person scaffolds
    a project they did not name - so that pair is refused in BOTH orders, and
    each half of it has to be able to see what the other one did.
    """

    __slots__ = ("opts", "invocation_dir", "positional")

    def __init__(self, invocation_dir: str):
        self.opts = Options()
        self.invocation_dir = invocation_dir
        self.positional = ""


def two_names(first: str, second: str) -> None:
    # The `openRepoShape` command's own refusal (openRepoShape:147), word
    # for word, whichever order the two names arrived in.
    die("two project names, '%s' and '%s'. One positional "
        "<Project>, then flags." % (first, second))


def take_value(state: Parsing, flag: str, rest: list) -> None:
    """One value-taking flag: pull its value off the line, check it, keep it."""
    if not rest:
        die("%s needs a value" % flag)
    attribute, check = VALUE_FLAGS[flag]
    value = rest.pop(0)
    if check is not None:
        value = check(flag, value)
    if flag in PATH_FLAGS:
        value = abspath(value, state.invocation_dir)
    if flag == "--project" and state.positional:
        two_names(state.positional, value)
    setattr(state.opts, attribute, value)


def take_positional(state: Parsing, arg: str) -> None:
    """A bare `<Project>`.

    The `openRepoShape` command's shape, folded in here so the Windows way in
    is one file instead of two: a bare <Project> is --project.
    """
    if state.opts.project:
        two_names(state.opts.project, arg)
    state.positional = checked_value("<Project>", arg)
    state.opts.project = state.positional


def unknown_argument(arg: str) -> None:
    """Anything that looks like a flag and is not one - and the empty string.

    `arg == ""` arrives here rather than at the positional: an empty argument
    is not a project name. setup.sh's `case` falls through to `*)` on one and
    refuses `unknown argument: ` with an empty tail, so this does too - the
    same words, including the space that ends them.
    """
    usage(sys.stderr)
    die("unknown argument: %s" % arg)


def parse_args(argv, invocation_dir: str) -> Options:
    """A while loop over the list, mirroring setup.sh:113-131.

    HAND-ROLLED, NOT argparse. The two entry points have to refuse the same
    things in the same words with the same exit codes, and argparse owns its
    own usage text, its own `--flag=value` spelling and its own exit code 2 on
    a message nobody wrote. A loop is what keeps the parity test honest.

    THE FLAGS THEMSELVES ARE TABLES (`VALUE_FLAGS`, `BOOLEAN_FLAGS`) rather
    than a chain of `elif`s, so this loop is the five shapes an argument can
    have - a flag with a value, a flag without one, the help, `--`, or a bare
    word - and adding a flag is a row rather than a branch.
    """
    state = Parsing(invocation_dir)
    rest = list(argv)
    while rest:
        arg = rest.pop(0)
        if arg in VALUE_FLAGS:
            take_value(state, arg, rest)
        elif arg in BOOLEAN_FLAGS:
            setattr(state.opts, BOOLEAN_FLAGS[arg], True)
        elif arg in ("-h", "--help"):
            state.opts.help = True
            return state.opts
        elif arg == "--":
            state.opts.passthrough = checked_passthrough(rest)
            break
        elif arg.startswith("-") or arg == "":
            unknown_argument(arg)
        else:
            take_positional(state, arg)

    opts = state.opts
    if opts.visibility not in VISIBILITY_CHOICES:
        die("--visibility is %s; it must be 'private', 'public' or 'internal'"
            % opts.visibility)
    return opts


# ---------------------------------------------------------------------------
# 0. self-bootstrap: run from wherever a checkout of openRepoShape is not
# ---------------------------------------------------------------------------

def source_path():
    """This file on disk, or None when there is no file at all.

    `py setup-project.py` has one. Piping the file into an interpreter that
    reads from stdin (`Get-Content setup-project.py | py -`) does not:
    `__file__` is then absent or the interpreter's own placeholder. That is
    the same case `curl | bash` is for setup.sh, and it is what makes
    self-bootstrap mode reachable rather than theoretical.

    `os.path.abspath`, never `Path.resolve()` - see `abspath` above, and one
    reason more. A person who put this file on their PATH as a symlink has an
    entry point whose `resolve()` lands INSIDE the checkout it points at, so
    a run from anywhere else looks like the developer path, takes it, and
    never passes `--into <invocation dir>`: the new project is cloned beside
    that checkout instead of where they were standing, which is #39 back
    again. `abspath` keeps the symlink's own directory, and a directory
    holding one symlink is not a shape checkout.
    """
    name = globals().get("__file__")
    if not name or name in ("<stdin>", "<string>"):
        return None
    return Path(os.path.abspath(name))


def is_shape_checkout(directory) -> bool:
    """Ask git, not the directory a person happened to be standing in.

    A script that arrived on stdin has no file on disk, so its "script
    directory" falls back to the working directory, which is an openRepoShape
    checkout only by coincidence. The two files named here are what the run
    actually needs.
    """
    proc = run(["git", "-C", str(directory), "rev-parse", "--show-toplevel"],
               capture=True)
    if proc.returncode != 0:
        return False
    toplevel = (proc.stdout or "").strip()
    if not toplevel:
        return False
    root = Path(toplevel)
    return ((root / SCAFFOLD).is_file()
            and (root / "contracts" / "repository-naming.yaml").is_file())


def self_bootstrap(opts: Options, original_argv, invocation_dir: str) -> int:
    """setup.sh:157-206, in Python: clone, re-run from there, clean up."""
    if not opts.org:
        die(ORG_REQUIRED)

    # `$OPENREPOSHAPE_REPO` NAMES A REPOSITORY, CHECKED LIKE ANY OTHER VALUE
    # THIS TOOL PUTS ON A `git` COMMAND LINE - EXCEPT that unset and
    # EXPLICITLY EMPTY (`OPENREPOSHAPE_REPO=`) are the same thing here: both
    # fall to `DEFAULT_SHAPE_REPO`, the shell's own `${VAR:-default}` reading -
    # `setup.sh` reads this same variable as `${OPENREPOSHAPE_REPO:-<default>}`,
    # so the two entry points agree on what "unset" means rather than one of
    # them treating an empty string as a value to check. A NON-empty value
    # reaches `git clone` and is checked like every other flag on the command
    # line: a person's or a CI job's environment can set it to anything, and
    # a leading `-` there is a `git clone` OPTION rather than a repository.
    # `checked_value` refuses that (and a control character) by the same rule
    # and in the same words as every flag on the command line; the `--` below
    # guards the argv too, so the refusal is not the only thing standing
    # between this value and `git`'s own argument parser.
    raw_shape_repo = os.environ.get("OPENREPOSHAPE_REPO")
    shape_repo = (checked_value("OPENREPOSHAPE_REPO", raw_shape_repo, PATH_RE)
                  if raw_shape_repo else DEFAULT_SHAPE_REPO)

    say("openRepoShape setup")
    say("")
    say("(0) self-bootstrap")
    checkout = tempfile.mkdtemp(prefix="openreposhape-shape-")
    try:
        clone_cmd = ["git", "clone", "--quiet"]
        # `--depth 1` only means something over a real transport; git warns
        # and ignores it for a bare local path (what the tests use via
        # $OPENREPOSHAPE_REPO), so skip it there rather than clone shallow
        # noise.
        if "://" in shape_repo and not opts.shape_ref:
            clone_cmd += ["--depth", "1"]
        # `--` BEFORE THE REPOSITORY, so git never reads it as an option
        # regardless of the check above: defense in depth, not a substitute
        # for it - `checked_value` is what produces a named refusal instead
        # of a confusing git error.
        clone_cmd += ["--", shape_repo, checkout]
        say("  " + " ".join(clone_cmd))
        cloned = run(clone_cmd)
        if cloned.returncode != 0:
            return shell_status(cloned.returncode)
        if opts.shape_ref:
            say("  git -C %s checkout --quiet %s" % (checkout, opts.shape_ref))
            checked_out = run(["git", "-C", checkout, "checkout", "--quiet",
                               opts.shape_ref])
            if checked_out.returncode != 0:
                return shell_status(checked_out.returncode)
        say("  checkout: %s" % checkout)
        say("")

        # WHERE THE NEW PROJECT LANDS (#39). The re-run happens from the
        # TEMPORARY checkout, so the child's own default parent - `..` of the
        # directory this file lives in - is the system temp directory, and the
        # project would be cloned there and left behind when the checkout
        # beside it was deleted. It belongs where the person was standing, so
        # the invocation directory is passed as --into FIRST, before their own
        # arguments: an explicit --into of theirs is parsed after this one and
        # wins, which is what keeps --into the override it is documented as.
        try:
            child = run([PYTHON, str(Path(checkout) / "setup-project.py"),
                         "--into", invocation_dir, *original_argv])
        except KeyboardInterrupt:
            # ONE REFUSAL PER CTRL-C. The child is in this terminal's process
            # group, so it received the same SIGINT, printed its own
            # `REFUSED: interrupted` and is gone; a second one from here would
            # be this process saying it too. 130 is what the child exited
            # with. The `finally` below still removes the temporary checkout.
            return 130
        return shell_status(child.returncode)
    finally:
        if opts.keep_shape_checkout:
            say("")
            say("kept the shape checkout: %s" % checkout)
        else:
            rmtree(checkout)


# ---------------------------------------------------------------------------
# 1. preflight
# ---------------------------------------------------------------------------

#: The two lines the preflight and `_main` must say identically. `_main` looks
#: for git BEFORE the preflight (see the comment there), and the same fact
#: reported in two wordings would read as two different faults.
GIT_MISSING = "git is not installed. Install it: https://git-scm.com/downloads"
PREREQ_MISSING = "one or more prerequisites are missing (see above)."

#: THE MISSING-`--org` REFUSAL, SAID ONCE BECAUSE IT IS REACHED FROM TWO
#: PLACES. `self_bootstrap` refuses before it clones anything: this file was
#: run from outside a checkout and there is no fork `origin` behind the
#: person. `_main` refuses after `setup.sh` has already done that clone and
#: handed over (`OPENREPOSHAPE_SELF_BOOTSTRAP`, below), where the checkout is
#: real but the person behind it is in exactly the same position. One fault,
#: one wording, one exit code, whichever entry point was typed.
ORG_REQUIRED = ("running outside a checkout of openRepoShape (self-bootstrap "
                "mode): there is no fork origin to read the organisation "
                "from. Re-run with --org <your-org>.")


#: GITHUB'S OWN INSTRUCTIONS FOR `gh`, WHICH ARE THE README'S OWN BLOCKS -
#: its "Debian, Ubuntu, or Windows under WSL2" fence and its "Fedora (DNF5)"
#: one, character for character including the tab-indented continuations. A
#: block and not a one-liner because that is what cli.github.com publishes: a
#: keyring, a source list, then the install.
GH_APT_BLOCK = (
    "(type -p wget >/dev/null || (sudo apt update && sudo apt install wget"
    " -y)) \\\n"
    "\t&& sudo mkdir -p -m 755 /etc/apt/keyrings \\\n"
    "\t&& out=$(mktemp) && wget -nv -O$out https://cli.github.com/packages/"
    "githubcli-archive-keyring.gpg \\\n"
    "\t&& cat $out | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg"
    " > /dev/null \\\n"
    "\t&& sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg"
    " \\\n"
    "\t&& sudo mkdir -p -m 755 /etc/apt/sources.list.d \\\n"
    "\t&& echo \"deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/"
    "keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages"
    " stable main\" | sudo tee /etc/apt/sources.list.d/github-cli.list"
    " > /dev/null \\\n"
    "\t&& sudo apt update \\\n"
    "\t&& sudo apt install gh -y")

GH_DNF_BLOCK = (
    "sudo dnf install dnf5-plugins\n"
    "sudo dnf config-manager addrepo --from-repofile=https://cli.github.com/"
    "packages/rpm/gh-cli.repo\n"
    "sudo dnf install gh")

#: APPLE'S COMMAND, SPELLED ONCE. It is a row of the table below, and it is
#: also the one row that must NOT be re-checked afterwards: `xcode-select
#: --install` returns as soon as its dialog is on screen, minutes before the
#: Tools it installs arrive. See `offer_install`.
TOOLS_INSTALL = "xcode-select --install"

#: WHAT THIS TOOL WILL OFFER TO RUN FOR YOU, and nothing else ever is. Each
#: row is `(the program that must be on PATH for the row to apply, the
#: command)`, tried in order, first match wins; `None` as the program means
#: the command needs no package manager at all.
#:
#: EVERY COMMAND HERE IS A LINE README.md ALREADY DOCUMENTS, word for word.
#: `tests/test_repo_hygiene.py` holds the two together, because a command
#: this tool would RUN that no document shows is a command nobody reviewed -
#: and because the person who declines the offer is then reading the same
#: line to type by hand.
#:
#: WHAT IS DELIBERATELY NOT HERE. Homebrew: on a Mac without `brew` the gh
#: lookup returns None and the machine owner's decision stays theirs (its
#: installer is never run by us). `make`: not checked, not used. Python: an
#: install cannot change the interpreter that is ALREADY RUNNING, so
#: `_check_python` names the commands and stops. An unrecognised platform is
#: no row at all, which is today's text and nothing more.
#:
#: `sys.platform` VALUES, and "linux" covers WSL2 - which is what we want:
#: its Ubuntu takes the Debian commands, exactly as README.md says.
INSTALL_OFFERS = {
    ("git", "darwin"): ((None, TOOLS_INSTALL),),
    ("git", "linux"): (("apt-get", "sudo apt-get install -y git"),
                       ("dnf", "sudo dnf install -y git")),
    ("git", "win32"): (("winget", "winget install --id Git.Git -e"),),
    ("gh", "darwin"): (("brew", "brew install gh"),),
    ("gh", "linux"): (("apt-get", GH_APT_BLOCK),
                      ("dnf", GH_DNF_BLOCK)),
    ("gh", "win32"): (("winget", "winget install --id GitHub.cli -e"),),
}


def offer_for(tool: str, platform: str, which=None):
    """The command THIS machine would run to install `tool`, or None.

    A PURE FUNCTION of a `sys.platform` string and a `shutil.which`, both
    passed in: the Windows rows are then asserted on a Linux runner and the
    macOS rows on either, with nothing monkeypatched and no import-time
    capture of the platform this file happens to be running on.

    `None` is not the empty string and does not mean "run nothing": it means
    there is no command this tool will run for you here - an unrecognised
    platform, a Mac with no Homebrew, a Linux with neither apt-get nor dnf -
    and the caller then prints exactly what it printed before any of this
    existed.
    """
    lookup = shutil.which if which is None else which
    for program, command in INSTALL_OFFERS.get((tool, platform), ()):
        if program is None or lookup(program):
            return command
    return None


def run_command_text(text: str) -> int:
    """Run one row of `INSTALL_OFFERS` through the platform's own shell.

    A SHELL, where `run()`'s doctrine is an argv and `shell=False`, and the
    apt row is the reason: GitHub's instructions are a pipeline with a
    `$(dpkg --print-architecture)` and two `sudo tee`s in it, and the only
    way the command we RUN can also be the command the README SHOWS is to
    hand that text to a shell. What makes it safe is not quoting but
    PROVENANCE: every string in that table is a literal in this file with no
    interpolation of any kind - nothing off the command line, nothing out of
    the environment, nothing read from disk ever reaches this line - and the
    parity test is what keeps it so.

    stdout and stderr are inherited and stdin is the person's terminal
    (`run_at_the_terminal`), so `sudo` asks for the password there and the
    package manager's own output is what they read.
    """
    argv = ["cmd", "/c", text] if os.name == "nt" else ["bash", "-c", text]
    return run_at_the_terminal(argv).returncode


def offer(command_text: str) -> bool:
    """Show one install command and take exactly one typed `yes` for it.

    THE SIGNATURE IS THE GUARANTEE, not the care of whoever edits this next:
    this function is never handed `Options`, so `--yes` is not in scope and
    cannot answer for anybody. `--yes` skips ONE question, the one about
    creating three repositories in an organisation; installing software on
    somebody's machine is a different question and gets its own answer.
    AGENTS.md says the same thing to an assistant driving this: the human
    types this one.

    NO TERMINAL, NO OFFER. `can_ask()` is the only gate, exactly as in
    `plan_and_confirm`: the person's terminal, which is stdin or, when a pipe
    is, the controlling terminal (#492). A run with neither, scheduled or in
    an assistant's shell, prints what it printed before any of this existed
    and stops where it stopped.

    The `yes` is EXACT and the prompt is the one this file already asks:
    `y`, `Yes`, an empty line and EOF are all refusals.
    """
    if not can_ask():
        return False
    say("")
    if "\n" in command_text:
        # A BLOCK IS SHOWN BEFORE IT IS OFFERED. GitHub's apt instructions
        # are nine lines long, and nine lines inside a one-line question is a
        # question nobody can read before answering it.
        for line in command_text.splitlines():
            say("      " + line)
        prompt = "  Run the commands above now? Type yes to continue: "
    else:
        prompt = "  Run `%s` now? Type yes to continue: " % command_text
    return ask(prompt) == "yes"


def offer_install(tool: str, command_text: str, probe,
                  platform: str = "") -> bool:
    """One offer, one run, ONE re-check. True when the check now passes.

    Never a loop: a person told twice that the thing is still missing is
    watching this program guess, and the second guess is no better than the
    first.

    Three ways this ends with the check still failed, each with its own line
    and none of them invented:

    * anything but `yes` - nothing runs and nothing more is printed;
    * the command failed - the package manager (or `sudo`) has just printed
      its own account of that on this terminal, and a vaguer sentence of ours
      underneath it would only compete with it;
    * the command succeeded and the probe still fails, which on Windows is
      not a failure at all: a running process keeps the PATH it started with,
      so a `winget install` lands somewhere this terminal cannot see until
      the next one.
    """
    platform = platform or sys.platform
    if not offer(command_text):
        return False
    if run_command_text(command_text) != 0:
        return False
    if command_text == TOOLS_INSTALL:
        # APPLE'S INSTALLER IS A WINDOW OF ITS OWN and `xcode-select
        # --install` returns as soon as it is on screen. There is nothing to
        # re-check yet, and waiting for it would be this tool polling a
        # dialog it did not open and cannot answer.
        say("  the Command Line Tools installer is running in a window of "
            "its own; run this again when it has finished.")
        return False
    if probe():
        return True
    if platform == "win32":
        say("  %s is installed, but this terminal's PATH has not picked it "
            "up yet; open a new terminal and run this again." % tool)
    else:
        say("  %s is still not there." % tool)
    return False


def offer_missing(tool: str, probe) -> bool:
    """The offer a failed check makes: look this platform's command up, and
    make no offer at all when there is none."""
    command = offer_for(tool, sys.platform)
    if command is None:
        return False
    return offer_install(tool, command, probe, sys.platform)


def _check_git() -> bool:
    if not shutil.which("git"):
        bad(GIT_MISSING)
        if not offer_missing("git", lambda: bool(shutil.which("git"))):
            return False
    ok("git %s" % program_version(["git", "--version"], 2))
    return True


def _check_python() -> bool:
    # THE RUNNING INTERPRETER, never a probe for one on PATH. The names the
    # shim probes for do not exist on a stock Windows install, and `python`
    # there may be a Store stub that opens a web page; the interpreter that
    # reached this line is the one that will run every child process, so it is
    # the one reported and the one whose version is checked. A COMMENT and not
    # a docstring, deliberately: a docstring is a string constant, and
    # `test_the_entry_point_never_names_python3` reads every one of them.
    version = sys.version_info
    if version < (3, 9):
        # NO OFFER HERE, and the reason is two lines above: the version
        # being reported is the RUNNING interpreter's, and no install can
        # change that from inside it. The commands are named for the person
        # to type, then the run stops - and on POSIX this is nearly
        # unreachable anyway, because the shim refuses an interpreter below
        # 3.9 before this file starts.
        bad("this interpreter is %d.%d, and 3.9 or newer is required. Install "
            "a newer Python and re-run it with that one: "
            "https://www.python.org/downloads/ - or `brew install python` on "
            "a Mac." % (version[0], version[1]))
        return False
    ok("python %d.%d.%d (%s)" % (version[0], version[1], version[2], PYTHON))
    return True


def _check_bootstrap() -> bool:
    """`make` is NOT checked, here or anywhere below.

    setup.sh probed for it and fell back before #50; there is no fallback to
    make now because make is never used - one command, on every platform, and
    Windows has no make at all. Nothing can be missing, so this never fails;
    it is a check because it is a line in the preflight a person reads.
    """
    ok("bootstrap runs as `%s %s` (make is not required)"
       % (PYTHON_CMD, BOOTSTRAP))
    return True


def _gh_login_suffix() -> str:
    """` as <login>` when gh will say who is logged in, and nothing when it
    will not: a name is a courtesy here, not the fact being checked."""
    login = run(["gh", "api", "user", "--jq", ".login"], capture=True)
    if login.returncode == 0 and (login.stdout or "").strip():
        return " as " + login.stdout.strip()
    return ""


def _check_gh(opts: Options) -> bool:
    if opts.local_mode:
        ok("gh not required (--local-remote-dir: bare repositories on disk, "
           "no network)")
        return True
    if not shutil.which("gh"):
        bad("gh is not installed. Install it: https://cli.github.com - or "
            "re-run with --local-remote-dir <dir> to try this offline against "
            "bare repositories on disk.")
        if sys.platform == "darwin" and offer_for("gh", sys.platform) is None:
            # THE ONE INSTALL THIS TOOL WILL NOT RUN. Homebrew is how a Mac
            # gets `gh`, and whether to have Homebrew at all is the machine
            # owner's decision rather than a question to be asked at the
            # bottom of somebody else's preflight. So it is named, with the
            # command that follows it, and that is where we stop.
            say("      Homebrew installs it with `brew install gh`, and is "
                "its own install: https://brew.sh")
        if not offer_missing("gh", lambda: bool(shutil.which("gh"))):
            return False
    ok("gh %s" % program_version(["gh", "--version"], 2))
    if run(["gh", "auth", "status"], capture=True).returncode != 0:
        bad("gh is not authenticated. Run: gh auth login")
        if not _offer_login():
            return False
    ok("gh is authenticated%s" % _gh_login_suffix())
    return True


def _offer_login() -> bool:
    """`gh auth login`, offered and then run as a PLAIN ARGV.

    Never through a shell: it is a terminal UI that ends in a browser and
    there is nothing in it to quote. gh is handed the person's own terminal
    as stdin (`run_at_the_terminal`) and their stdout and stderr - which is
    what its prompts and its one-time code need, and what the gate on the
    offer has already guaranteed is there. The browser half is the human's;
    this starts the login and asks `gh auth status` once when gh comes back.
    """
    if not offer("gh auth login"):
        return False
    if run_at_the_terminal(["gh", "auth", "login"]).returncode != 0:
        return False
    if run(["gh", "auth", "status"], capture=True).returncode != 0:
        say("  gh is still not authenticated.")
        return False
    return True


def _credential_helper_configured() -> bool:
    """Will ANYTHING answer git's credential question for github.com?

    The scoped key first, because that is where gh writes its own helper -
    and it writes an empty line before it, to reset the list, which is why
    this reads the whole answer and strips it rather than counting lines.
    The machine-wide key can hold something else entirely at the same time,
    and either of them answering is enough.
    """
    for key in ("credential.https://github.com.helper", "credential.helper"):
        configured = run(["git", "config", "--get-all", key], capture=True)
        if (configured.stdout or "").strip():
            return True
    return False


def _check_credential_helper(opts: Options) -> None:
    """WARN, DO NOT REFUSE - the class `_warn_autocrlf` belongs to.

    The scaffold clones and pushes over HTTPS (`clone_and_bootstrap`), so a
    machine with NO credential helper at all creates three repositories and
    then fails on the first push. That is worth a `[??]` while nothing has
    been created yet, and an offer of the one command that fixes it.

    A machine that HAS a helper is left alone, whatever it is. `osxkeychain`,
    Windows' `manager`, `store`, a devcontainer's own: they all answer git's
    question for github.com without gh being involved, and warning about them
    would be this tool disliking somebody's ~/.gitconfig - the objection
    `_warn_autocrlf` records. That is also why gh's own test for ITS helper
    (`isOurCredentialHelper`: a line starting `!` whose first word's basename
    is gh) is not transcribed here. A helper that is not gh's still pushes.

    NEVER IN THE `checked` LIST. It cannot fail the run and it cannot fail
    `--preflight`: a warning that refuses is a refusal, and this one would
    refuse a machine whose remotes are SSH and whose HTTPS push this tool
    never makes.
    """
    if opts.local_mode:
        return
    if _credential_helper_configured():
        return
    warn("git has no credential helper for github.com, so the first push "
         "over HTTPS will fail. Fix it once: gh auth setup-git")
    if not offer("gh auth setup-git"):
        return
    if run_at_the_terminal(["gh", "auth", "setup-git"]).returncode != 0:
        return
    if _credential_helper_configured():
        ok("git will ask gh for github.com credentials")


def _warn_autocrlf() -> None:
    """WARN, DO NOT REFUSE (Brett Heap, 2026-09-05).

    `core.autocrlf=true` is what the git-for-Windows installer offers by
    default, and it rewrites every checked-out file's line endings - which
    makes a scaffolded project's copies differ from the sha256 rows its own
    shape pin records, so its first `validate` reports drift nobody
    introduced. It is a machine setting, not a fault in this run, and the
    clone this tool makes is configured correctly regardless (see
    clone_and_bootstrap), so the run continues.
    """
    if os.name != "nt":
        return
    # `--global`, because the message below tells the person to fix the
    # GLOBAL setting and a warning about a value it did not read would
    # send them to change something that was already right.
    # `--type=bool` so `1`, `yes`, `on` and `true` are one answer; unset
    # is exit 1 and empty stdout, which is silence, not a warning.
    configured = run(["git", "config", "--global", "--type=bool", "--get",
                      "core.autocrlf"], capture=True)
    if (configured.stdout or "").strip() != "true":
        return
    warn("git core.autocrlf is true. Every file git checks out gets "
         "CRLF line endings, and a project's shape pin digests the "
         "bytes it was written with - so `validate` will report drift "
         "in files nobody edited. Fix it once, for this machine: "
         "git config --global core.autocrlf false")


def preflight_checks(opts: Options) -> bool:
    """Every check, in order, and whether they all passed.

    SPLIT OUT OF `preflight` FOR `--preflight` (#59, renamed 2026-09-10), which runs exactly this
    and then reports instead of refusing. The scaffold path is unchanged: the
    refusal is still one refusal, still at the end, still naming everything
    that was missing.
    """
    say("openRepoShape setup")
    say("")
    say("(1) preflight")
    # EVERY CHECK RUNS, THEN THE RUN REFUSES ONCE. A person on a fresh machine
    # is told about git AND gh in one go rather than one missing thing per
    # re-run, which is what the original `failed = True` accumulator bought.
    # The list is complete before `all` reads it, so nothing short-circuits.
    checked = [_check_git(), _check_python(), _check_bootstrap()]
    # THE CREDENTIAL HELPER IS ASKED ABOUT ONLY WHEN gh IS READY. With no gh,
    # or no login, there is nothing to set up as a helper yet and the person
    # has already been told the thing that has to happen first.
    gh_ready = _check_gh(opts)
    checked.append(gh_ready)
    if gh_ready:
        _check_credential_helper(opts)
    _warn_autocrlf()
    return all(checked)


def preflight(opts: Options) -> None:
    if not preflight_checks(opts):
        die(PREREQ_MISSING)


def preflight_only(opts: Options) -> int:
    """`--preflight`: the preflight, the offers it makes, and then stop.

    Exit 0 when every check passed and 1 when any did not - the 0/1 vocabulary
    a person can put in a script, where the scaffold's own refusal stays exit
    2 whatever fails. A `[??]` warning never changes the code: it is a setting
    worth looking at, not a missing prerequisite.

    It says in as many words that nothing was created, because `--preflight` can
    be typed alongside a project name by somebody who has just read about
    both, and a run that printed a preflight and then stopped must not be
    read as a scaffold that failed silently.
    """
    ready = preflight_checks(opts)
    say("")
    if ready:
        ok("this machine is ready.")
    else:
        bad("this machine is not ready yet (see above).")
    say("  nothing was created; this checked the machine only.")
    return 0 if ready else 1


# ---------------------------------------------------------------------------
# 2. which organisation
# ---------------------------------------------------------------------------

def detect_org_from_url(url: str) -> str:
    """setup.sh:267-275: the owner out of an https, ssh or bare remote URL."""
    if "://" in url:
        rest = url.split("://", 1)[1]
        if "@" in rest:
            rest = rest.split("@", 1)[1]
        rest = rest.split("/", 1)[1] if "/" in rest else rest
    elif ":" in url:
        rest = url.split("@", 1)[1] if "@" in url else url
        rest = rest.split(":", 1)[1] if ":" in rest else rest
    else:
        rest = url
    return rest.split("/", 1)[0]


def remote_url(directory: str, remote: str) -> str:
    proc = run(["git", "-C", directory, "remote", "get-url", remote],
               capture=True)
    return (proc.stdout or "").strip() if proc.returncode == 0 else ""


def _origin_org(invocation_dir: str):
    """The `origin` remote and the organisation read out of it.

    `gh repo view` with no argument resolves the CURRENT repository by its
    own rules, and on a checkout with two remotes (`origin` plus an
    `upstream` pointing at opensoft/openRepoShape - kept only by someone
    contributing back to the standard itself) it can prefer `upstream` over
    `origin`. `origin` is the remote that means "this clone", in every mode,
    so it is read directly and parsed by hand; `gh repo view` is consulted
    only as a fallback (`_org_from_gh`), and only ON THE ORIGIN URL itself
    (never bare), so it cannot go pick `upstream` either.

    Read against the INVOCATION directory, not the directory this file lives
    in. The two are the same for the README's own `cd openRepoShape` usage;
    they differ only when this file is invoked by a path from elsewhere, and
    then the clone you are IN is the one whose organisation you mean.
    """
    origin_url = remote_url(invocation_dir, "origin")
    return origin_url, detect_org_from_url(origin_url) if origin_url else ""


def _org_from_gh(opts: Options, origin_url: str) -> str:
    """The fallback: gh's own answer for the ORIGIN URL, or nothing."""
    if not origin_url or opts.local_mode:
        return ""
    proc = run(["gh", "repo", "view", origin_url, "--json", "owner",
                "--jq", ".owner.login"], capture=True)
    return (proc.stdout or "").strip() if proc.returncode == 0 else ""


def is_upstream_org(org: str) -> bool:
    """`org` is opensoft, in whatever case it was typed or recorded (#538).

    GitHub reads an organisation's login in any case, so `--org OpenSoft`,
    and an `origin` under `OpenSoft/`, name opensoft's own namespace. Every
    upstream check below compared exactly, so those passed with no refusal,
    and a person with create rights there scaffolded into it.
    """
    return org.casefold() == UPSTREAM_ORG.casefold()


def _org_without_origin(opts: Options, origin_url: str) -> str:
    """No --org and no organisation parsed out of `origin`: ask, or refuse."""
    viewed = _org_from_gh(opts, origin_url)
    if viewed:
        if is_upstream_org(viewed):
            die("you are running from the upstream checkout (%s); pass "
                "--org <your-org>." % origin_url)
        ok("organisation %s (from `gh repo view` on the origin URL: %s; "
           "could not parse it by hand)" % (viewed, origin_url))
        return viewed
    if opts.local_mode:
        ok("organisation localorg (placeholder; no `origin` remote to read, "
           "and --local-remote-dir creates nothing on GitHub)")
        return "localorg"
    die("cannot work out which organisation to scaffold into: this "
        "clone has no `origin` remote and no --org was given. Re-run "
        "with --org <your-org>.")


def _choose_org(opts: Options, origin_url: str, origin_org: str) -> str:
    # `origin` pointing at opensoft itself means this checkout IS the upstream
    # - there is no fork to inherit an organisation from, exactly like
    # self-bootstrap mode, so the fix is the same: pass --org.
    if not opts.org and is_upstream_org(origin_org):
        die("you are running from the upstream checkout (%s); pass --org "
            "<your-org>." % origin_url)
    if opts.org:
        ok("organisation %s (from --org)" % opts.org)
        return opts.org
    if origin_org:
        ok("organisation %s (from the `origin` remote: %s)"
           % (origin_org, origin_url))
        return origin_org
    return _org_without_origin(opts, origin_url)


def _note_upstream(invocation_dir: str, origin_org: str, org: str) -> None:
    """A checkout kept for contributing to the standard itself may still carry
    an `upstream` remote pointing at opensoft. Name it so a person who did not
    expect one at all is not left guessing why the detected organisation is
    not opensoft's.
    """
    upstream_url = remote_url(invocation_dir, "upstream")
    if not upstream_url:
        return
    upstream_org = detect_org_from_url(upstream_url)
    if upstream_org and origin_org and upstream_org != origin_org:
        say("  upstream is %s; scaffolding into %s" % (upstream_org, org))


def _guard_upstream_org(opts: Options, org: str) -> None:
    """The guard that matters now that the organisation is never silently set
    to opensoft by detection (see the die in `_choose_org`): the only way to
    reach this point with opensoft is an explicit `--org opensoft`, which is
    almost never what anyone means. It applies in EVERY mode,
    --local-remote-dir included: `--org` is what a scaffolded `project.yaml`
    records as the owner of all three legs, so a manifest reading
    `opensoft/Sample` is wrong regardless of whether any network call
    happened.

    IN ANY CASE (#538): `is_upstream_org`. The refusal names the
    organisation as it was typed, and says why another casing is still
    opensoft's.
    """
    if is_upstream_org(org) and not opts.allow_upstream_org:
        casing = ("" if org == UPSTREAM_ORG else
                  " (GitHub reads an organisation's name in any case, so "
                  "'%s' is '%s')" % (org, UPSTREAM_ORG))
        die("the organisation is '%s', which is the UPSTREAM owner of "
            "openRepoShape itself%s, and scaffolding here would create three "
            "repositories in opensoft's own namespace.\n"
            "\n"
            "  Wrong guess?  re-run with --org <your-org>\n"
            "  You meant it? re-run with --allow-upstream-org"
            % (org, casing))


def resolve_org(opts: Options, invocation_dir: str) -> str:
    """setup.sh:262-353, transcribed."""
    say("")
    say("(2) organisation")
    origin_url, origin_org = _origin_org(invocation_dir)
    org = _choose_org(opts, origin_url, origin_org)
    _note_upstream(invocation_dir, origin_org, org)
    _guard_upstream_org(opts, org)
    return org


# ---------------------------------------------------------------------------
# 3. the project
# ---------------------------------------------------------------------------

#: THE PERSON'S OWN TERMINAL, BY NAME (#492). `curl ... | bash -s --`, the
#: README's first command, makes the script's stdin THE PIPE it arrived down,
#: and this file's too, so a run in the person's own terminal found no
#: terminal on stdin and refused where it should have asked. A process
#: started from a terminal keeps it as its CONTROLLING terminal whatever its
#: stdin is, and `/dev/tty` opens exactly that one. A process with none - an
#: AI assistant's shell, a scheduled job, the doctor's preflight (started in
#: a session of its own) - cannot open it, and refuses as before.
#:
#: POSIX ONLY. Windows has no `/dev/tty`: the name would be a FILE on the
#: current drive there, and a file is the one thing that must never answer a
#: question, so it is never opened. A script piped into `py -` still
#: refuses, which is why the README's Windows path downloads the file first.
CONTROLLING_TERMINAL = "/dev/tty"


def open_terminal():
    """A file descriptor on the controlling terminal, or None.

    `os.isatty` on what was opened, because whether a thing is a terminal is
    the device's answer and not its name's: a `/dev` somebody populated by
    hand - a chroot, a container image - can hold a regular file called
    `tty`, and a file never types `yes`.

    A terminal that opens is not always one this run can be ANSWERED on, and
    a prompt nobody can answer is worse than a refusal: it waits for the
    assistant's tool timeout, and the refusal's route is never shown. It is
    answerable only when BOTH hold:

    - this run is in the terminal's FOREGROUND process group
      (`tcgetpgrp`). A background group's read stops on SIGTTIN, or fails
      with EIO when the group is orphaned or the signal is ignored - which is
      what `cat setup.sh | timeout N bash -s -- ...` typed in a shell is, as
      GNU `timeout` puts the command in a group of its own, and what any
      runner that backgrounds a job sharing the terminal is;
    - the terminal reads WHOLE LINES (`ICANON`). An assistant's full-screen
      interface owns its pane in raw mode, where the person's Enter sends a
      carriage return and a read for the end of a line never ends.

    Neither is an answerable terminal, so it is no terminal: `None`, and the
    gates refuse as they do with no terminal at all. Windows returned above
    and never reaches `termios`.
    """
    if os.name == "nt":
        return None
    try:
        descriptor = os.open(CONTROLLING_TERMINAL, os.O_RDWR | os.O_NOCTTY)
    except OSError:
        return None
    if not os.isatty(descriptor):
        os.close(descriptor)
        return None
    try:
        import termios
        answerable = (os.tcgetpgrp(descriptor) == os.getpgrp()
                      and bool(termios.tcgetattr(descriptor)[3]
                               & termios.ICANON))
    except (OSError, ImportError):
        answerable = False
    if not answerable:
        os.close(descriptor)
        return None
    return descriptor


def can_ask() -> bool:
    """Is there a person at a terminal to put a question to?

    Stdin when it is a terminal, as it always was; otherwise the controlling
    terminal, opened and closed again here (#492). Every gate asks this one
    question - the project name, each install offer, the one `yes` - so a
    gate can never pass where `ask` would then have nobody to ask.
    """
    if sys.stdin.isatty():
        return True
    descriptor = open_terminal()
    if descriptor is None:
        return False
    os.close(descriptor)
    return True


def ask(prompt: str) -> str:
    """ONE line, typed by the person at their own terminal, and NEVER read
    from anywhere else.

    Stdin when it is the terminal: `input`, exactly as before. Otherwise the
    controlling terminal (#492): the prompt is written to it, where the
    person is looking whatever stdout is, and the answer is read from it a
    byte at a time up to the newline, so nothing after the answer is taken.
    Stdin that is not a terminal is never read: under `curl | bash` it is the
    rest of the script, and a `yes` arriving down a pipe is nobody's answer.
    With no terminal at all the answer is an empty line, which no question
    here takes for a yes; the gates (`can_ask`) refuse before asking.
    """
    if sys.stdin.isatty():
        try:
            return input(prompt)
        except EOFError:
            return ""
    descriptor = open_terminal()
    if descriptor is None:
        return ""
    sys.stdout.flush()
    sys.stderr.flush()
    answer = b""
    try:
        unwritten = prompt.encode("utf-8")
        while unwritten:
            unwritten = unwritten[os.write(descriptor, unwritten):]
        while not answer.endswith(b"\n"):
            try:
                byte = os.read(descriptor, 1)
            except OSError:
                # EIO: the terminal went away or this group was orphaned
                # after the check. End of input, never a traceback.
                byte = b""
            if not byte:
                break
            answer += byte
    finally:
        os.close(descriptor)
    text = answer.decode("utf-8", errors="replace")
    return text[:-1] if text.endswith("\n") else text


def run_at_the_terminal(argv) -> subprocess.CompletedProcess:
    """A command the person has just said `yes` to, run with their terminal
    as its stdin.

    What an offer runs can ask something of its own - `gh auth login` is a
    terminal UI, `sudo` wants a password - so it gets the terminal the `yes`
    came from: inherited when stdin is that terminal, and the controlling
    terminal opened for it when stdin is a pipe (#492), which would hand
    `gh` the rest of `setup.sh` as its input.
    """
    if sys.stdin.isatty():
        return run(argv)
    descriptor = open_terminal()
    try:
        return run(argv, stdin=descriptor)
    finally:
        if descriptor is not None:
            os.close(descriptor)


def ask_for_the_project_name() -> str:
    """The `project name` prompt, and the name typed at it, checked (#729).

    AN EMPTY LINE IS A NAME NOBODY TYPED, NOT A MISSING TERMINAL: `can_ask()`
    at the call is the gate that refuses for want of one, so this refusal says
    what happened and does not print the usage text.

    THE TYPED NAME IS HELD TO THE CHECK THE SAME NAME GETS AS `--project` or
    as the positional, before anything builds a path from it: `..` leaves
    `--into`, an absolute name replaces it, and step (4)'s validator reads
    only the last part of what it is handed. `a b` and `Bad_Name` pass here on
    purpose (`NAME_RE` is permissive); step (4) is where the policy rules on
    those.
    """
    typed = ask("  project name (ONE CamelCase token, e.g. Atlas): ")
    if not typed:
        die("no project name was typed; nothing was created.")
    return checked_value("project name", typed)


def resolve_project_and_elector(opts: Options, shape_root: Path) -> None:
    """setup.sh:355-386, transcribed."""
    say("")
    say("(3) project")
    if not opts.project and can_ask():
        opts.project = ask_for_the_project_name()
    if not opts.project:
        usage(sys.stderr)
        die("no --project given, and no terminal to ask on.")

    if not opts.elected_by and not opts.local_mode:
        proc = run(["gh", "api", "user", "--jq", ".login"], capture=True)
        if proc.returncode == 0:
            opts.elected_by = (proc.stdout or "").strip()
    if not opts.elected_by:
        # Per-invocation identity first (GIT_AUTHOR_NAME), then the
        # repo/global config, then the gh login - never a global config WRITE.
        opts.elected_by = os.environ.get("GIT_AUTHOR_NAME", "")
    if not opts.elected_by:
        # IN THE CHECKOUT, mirroring setup.sh:377 - which runs after the
        # `cd "$SCRIPT_DIR"` at setup.sh:208. `git config` with no scope reads
        # the repository's config too, and the repository it must read is the
        # standard's checkout, not whatever the person happened to be standing
        # in when they typed the command.
        proc = run(["git", "config", "user.name"], cwd=shape_root,
                   capture=True)
        if proc.returncode == 0:
            opts.elected_by = (proc.stdout or "").strip()
    if not opts.elected_by:
        die("cannot work out who is electing this shape. Re-run with "
            "--elected-by 'Your Name' - the manifest records whose act it "
            "was.")

    ok("project      %s" % opts.project)
    ok("legs         %s-spec, %s-code" % (opts.project, opts.project))
    ok("visibility   %s" % opts.visibility)
    ok("elected by   %s" % opts.elected_by)


# ---------------------------------------------------------------------------
# 3b. the family: where the clone lands, and who records the membership
# ---------------------------------------------------------------------------

def shape_scripts(shape_root: Path):
    """`scripts/repo_shape.py` out of the checkout this run is using.

    THE ONE IMPORT FROM THE CHECKOUT, AND WHY IT IS LEGITIMATE HERE. The
    module docstring's rule stands: the PARSE-TIME checks above cannot import
    `repo_shape.checked_value`, because at parse time there may be no
    checkout to import it from at all - that is the whole of self-bootstrap
    mode, and it is why `checked_value` is the house pattern COPIED rather
    than imported. By the time this is called there IS one: `_main` has
    either confirmed a checkout with `is_shape_checkout` or re-run this file
    FROM the temporary clone it made. So the naming classifier and the YAML
    reader here are the standard's own - the same two `scaffold-project.py`,
    `adopt-project.py`, `scripts/family.py` and `scripts/bump-leg.py` use -
    rather than a second reading of a policy file that would then have two
    readers to keep in step.

    DEFERRED, NOT LAZY-FOR-SPEED. A module-level import would run at the top
    of a lone downloaded file and fail there, which is exactly the run this
    entry point exists for.
    """
    directory = str(shape_root / "scripts")
    if directory not in sys.path:
        sys.path.insert(0, directory)
    import repo_shape  # noqa: E402  (deferred on purpose; see above)
    return repo_shape


def scaffold_link_remedies(shape_root: Path):
    """`scripts/shape_materialize.py`'s `scaffold_link_remedies` out of
    the checkout this run is using: what the scaffold's plan offers a chain
    link whose tree it cannot read (#610), so step (4) can hand the naming
    check the same words (#661) and one run says one fact one way.
    Deferred for the reason `shape_scripts` gives, from the same directory.
    """
    shape_scripts(shape_root)
    import shape_materialize  # noqa: E402  (deferred; see shape_scripts)
    return shape_materialize.scaffold_link_remedies


def family_landing(parent, family: str):
    """The clone's PARENT once `--family` has had its say. A PURE path.

    THE WHOLE LANDING RULE, over `PurePath` operations only - no `os.path`,
    no filesystem - so `tests/test_windows_paths.py` can ask it the Windows
    question from Linux, the way it asks `root_key` and the argument guard.

    `<into>/<Family>/<Project>` is the layout the RULING of 2026-09-09 (#76)
    placed: a plain folder named after the family, holding the holder clone
    and the members' working clones as siblings.

    NO DOUBLE NESTING. A person already standing in `.../InkRouter` who types
    `--family InkRouter` means the folder they are IN, not a second one
    inside it. The BASENAME decides that, not the manifest: a family folder
    with no holder cloned into it yet is still the folder they are standing
    in, and a rule that read the manifest would land the first member of a
    brand-new family one level too deep.
    """
    if not family or parent.name == family:
        return parent
    return parent / family


def family_folder_here(shape_root: Path, parent: Path) -> str:
    """The family whose FOLDER `parent` is, or "" for a plain directory.

    ADVISORY, AND NEVER A FLAG (#76). One file answers it -
    `<parent>/<basename>/family.yaml` - because that is where the holder
    clone sits: the doubled `<Family>/<Family>` the ruling kept, so the
    repository keeps its own name inside the family folder and the manifest
    disambiguates.

    IT IS READ, NOT GUESSED FROM THE NAME. A directory called `Northwind` is
    a directory called `Northwind`; what makes it a family folder is a
    `kind: family-manifest` inside it that NAMES that same family. All three
    have to agree, or this says nothing at all and the run is what it was.

    ANY read failure means "not a family folder". This is advice printed in a
    plan, so a manifest that is half-written, unreadable, or a YAML shape
    nobody expected must not refuse a scaffold that never needed it.
    """
    name = parent.name
    if not name:
        return ""
    manifest = parent / name / FAMILY_MANIFEST
    if not manifest.is_file():
        return ""
    try:
        data = shape_scripts(shape_root).load_yaml(manifest)
    except Exception:  # noqa: BLE001  (advice rather than a gate; see above)
        return ""
    if not isinstance(data, dict) or data.get("kind") != FAMILY_KIND:
        return ""
    return name if str(data.get("name") or "") == name else ""


class Landing:
    """WHERE THE CLONE LANDS, decided ONCE in step (3).

    `directory` is the clone's PARENT after the landing rule has been
    applied: `--into` (or the developer path's `..`), with one level added
    when `--family` named a family this directory is not already the folder
    of. Step (7) reads it rather than working the same thing out again, so
    the path the person read in the plan and the path the clone goes to
    cannot drift apart.

    `holder` is where `scripts/family.py add` is pointed: `<directory>/
    <Family>`, doubled by the RULING of 2026-09-09 (ruling 3) so the holder
    repository keeps its own name inside the family folder. It is a path this
    tool never creates and never reads a commit out of - it only says it.
    `family` is "" and `holder` is None when no family is in play at all.
    """

    __slots__ = ("directory", "family", "holder")

    def __init__(self, directory, family: str, holder):
        self.directory = directory
        self.family = family
        self.holder = holder

    def clone_path(self, project: str) -> str:
        return str(self.directory / project)


def resolve_family(opts: Options, shape_root: Path) -> Landing:
    """The family, the landing path, and the two lines the plan says about it.

    PRINTS INTO THE `(3) project` BLOCK ABOVE rather than under a heading of
    its own: which family this project joins is a fact about the run in
    exactly the way the visibility and the elector are, and a step number for
    one or two lines would put a section break in the middle of one list.

    THE PROJECT RECORDS NOTHING. `scaffold_args` is deliberately never given
    `--family`: no `project.yaml` field, no file in the tree. Membership is
    recorded in the HOLDER's `family.yaml` by `scripts/family.py add`, which
    `hand_over` names - "the shape confers nothing", and membership confers
    nothing either, so a project that carried its family in its own manifest
    would be asserting a fact about a tree it does not own.
    """
    # The `..` of the DEVELOPER PATH, computed here rather than at clone time
    # so the plan and the clone cannot disagree about where the project goes.
    # `os.path.abspath`, never `resolve()` - see `abspath` above.
    parent = Path(opts.into) if opts.into else Path(
        os.path.abspath(os.path.join(str(shape_root), "..")))
    standing = family_folder_here(shape_root, parent)
    family = opts.family or standing

    # NEVER A FAMILY INSIDE A FAMILY. `<into>` is one family's folder and
    # --family names a different one, so the clone would land at
    # `Northwind/InkRouter/IRTS`: a member of one family filed inside
    # another, which is a layout no `family.yaml` can describe. Both names,
    # and both ways out - this tool moves nothing and asks for no --force.
    if opts.family and standing and standing != opts.family:
        die("--family %s, but %s is the %s family folder (%s says so, with "
            "kind: %s). A family is never nested inside a family. Either "
            "`cd` out of %s first and re-run, or drop --family and let %s "
            "land beside %s's holder."
            % (opts.family, parent, standing,
               parent / standing / FAMILY_MANIFEST, FAMILY_KIND,
               standing, opts.project, standing))

    landing = family_landing(parent, family)
    if not family:
        return Landing(landing, "", None)

    if opts.family:
        # A person standing in the folder they named gets told so, because
        # the landing path they are about to read has one level fewer than
        # the flag they typed reads like.
        note = ("" if parent.name != opts.family else
                " (you are standing in the %s folder, so nothing is nested "
                "twice)" % opts.family)
        ok("family       %s%s" % (opts.family, note))
        ok("lands at     %s" % landing.joinpath(opts.project))
    else:
        ok("family       standing in the %s family folder; the project lands "
           "beside its holder" % family)
    return Landing(landing, family, landing / family)


# ---------------------------------------------------------------------------
# 3c. the clone path, while nothing exists
# ---------------------------------------------------------------------------

#: THE WAYS OUT OF A TAKEN CLONE PATH. This tool deletes and moves nothing
#: itself, and it offers deleting only as strongly as it KNOWS that nothing
#: is lost. An empty directory holds nothing: move or delete it. What looks
#: like a rehearsal's clone is a GUESS - a real working clone of a local, NAS
#: or UNC repository named `<Project>.git` looks the same, unpushed commits
#: and all - so deleting is offered on the person's own condition (#498,
#: review round 1). Anything else is somebody's: move it, or put the project
#: somewhere else.
DISCARD_IT = "Move or delete it, then run this again."
DISCARD_IT_IF_UNUSED = ("Move it, or delete it if nothing in it is yours, then "
                        "run this again.")
KEEP_IT = "Move it, or choose another --into, then run this again."
#: What step (3) says to do about a parent nobody can write in, and about a
#: path whose drive is not there (#608).
WRITE_IT = ("Choose another --into, or make it a folder you can write in, "
            "then run this again.")
DRIVE_WAY_OUT = ("Choose another --into on a drive that is there, then run "
                 "this again.")


def origin_recorded_in(clone: str) -> str:
    """The `origin` URL `<clone>/.git/config` records, or "" when it records
    none this can read.

    THE FILE, NEVER A DISCOVERY. `git -C <clone>` would look for a
    repository and, finding none in `<clone>` itself - an empty `.git`, a
    broken one - would walk up and answer for whatever repository holds
    `<into>`, naming somebody else's `origin` as this directory's. `git
    config --file` reads that one file, with no includes and no URL
    rewriting. A `.git` FILE (a worktree, a submodule) keeps its config
    elsewhere, so there is nothing here to read and the caller says less.
    And no git runs INSIDE a directory this tool did not make: its config
    can name a command (`core.fsmonitor`) that `git status` executes.

    A value carrying a control character is not echoed: it would print a
    line this tool did not write (`CONTROL_RE`).
    """
    config = os.path.join(clone, ".git", "config")
    if not os.path.isfile(config):
        return ""
    proc = run(["git", "config", "--file", config, "--get",
                "remote.origin.url"], capture=True)
    url = (proc.stdout or "").strip() if proc.returncode == 0 else ""
    return "" if CONTROL_RE.search(url) else url


def is_on_this_disk(url: str) -> bool:
    """An `origin` that is a path rather than a host: what `git clone` of a
    local repository records (it makes the path absolute), which is what a
    `--local-remote-dir` rehearsal's clone has."""
    return url.startswith("file:") or os.path.isabs(url)


def without_credentials(url: str) -> str:
    """`url` with any `user:token@` after its scheme dropped: an `origin` is
    echoed into a refusal an assistant may relay, and a token is not part of
    what is there. Up to the LAST `@` before the path, because a password
    holding a bare `@` would otherwise leave its tail on the screen."""
    return re.sub(r"(?<=://)[^/]*@", "", url, count=1)


def what_stands_at(clone: str, project: str) -> tuple:
    """`(one sentence saying what is at clone, the way out)`; the sentence
    is "" when this cannot tell.

    A REHEARSAL'S CLONE IS THE CASE THIS EXISTS FOR (#498). README's
    "Rehearse first" leaves `./<Project>` behind, cloned from the bare
    `<dir>/<Project>.git` that `--local-remote-dir` made, and the real run
    that follows it in the same folder lands on exactly that path. It LOOKS
    like one when all three hold: an `origin` on this disk, named
    `<Project>.git`, and a `project.yaml` at its root. That is said as a
    look, never as a fact, and deleting it is offered only "if nothing in
    it is yours": a working clone of a local or network repository meets
    all three, and this tool cannot see its unpushed work without running
    git inside it (`origin_recorded_in` says why it does not).

    A SYMBOLIC LINK IS SAID TO BE ONE, first, and never offered for
    deletion: `os.path.isdir` follows it, and `rm -r <path>/` on the
    advice "delete it" would act on its target.
    """
    try:
        if os.path.islink(clone):
            target = os.readlink(clone)
            if not target or CONTROL_RE.search(target):
                return "It is a symbolic link.", KEEP_IT
            return "It is a symbolic link to %s." % target, KEEP_IT
        if not os.path.isdir(clone):
            return "", KEEP_IT
        if not os.path.lexists(os.path.join(clone, ".git")):
            if os.listdir(clone):
                return "It is a directory that is not a git clone.", KEEP_IT
            return "It is an empty directory.", DISCARD_IT
    except OSError:
        return "", KEEP_IT
    origin = origin_recorded_in(clone)
    if not origin:
        return "It is a directory holding a `.git`.", KEEP_IT
    shown = without_credentials(origin)
    if (is_on_this_disk(origin)
            and os.path.basename(origin.rstrip("/\\")) == project + ".git"
            and os.path.isfile(os.path.join(clone, "project.yaml"))):
        return ("It looks like the clone a rehearsal left behind: its `origin` "
                "is %s, a repository on this disk, as `--local-remote-dir` "
                "makes one." % shown), DISCARD_IT_IF_UNUSED
    return "It is a clone of %s." % shown, KEEP_IT


def refuse_a_taken_clone_path(clone: str, project: str) -> None:
    """Refuse, HERE, a clone path that anything at all already stands at.

    THE QUESTION IS ASKED WHERE THE ANSWER IS DECIDED (#498). `resolve_family`
    has just fixed `<into>/<Project>` (or `<into>/<Family>/<Project>`), and
    nothing exists yet. Asked only in step (7), as it used to be, the same
    question came after step (6) had created all three repositories and
    pushed them: a person who rehearsed and then ran for real in the same
    folder - README's own order - got three new repositories on GitHub, no
    project, a hand clone that failed on the same directory, and a re-run
    refused `scaffold-remote-exists`.

    ANY ENTRY AT THAT NAME, `lexists`: a directory, a file, and a symbolic
    link to nothing, which `exists` reads as absent and `git clone` still
    refuses. An EMPTY directory is refused too, although `git clone` would
    take one (#498's option 1, put to Brett Heap on 2026-10-13, who did not
    object): the rule is "nothing there", said once, rather than one more
    case to explain.

    The refusal says nothing was created, names the path, and says what is
    there where `what_stands_at` can tell. Step (7) keeps its own check, for
    a path that appears while the run is going.

    AND WHAT STANDS ABOVE IT (#538). A FILE at `<into>/<Family>`, or at
    `--into` itself, is a path the clone can never be made under, and
    `lexists` reads `<file>/<Project>` as absent: on main this passed, all
    three repositories were created, and step (7)'s `os.makedirs` ended the
    run in a `FileExistsError` traceback. `refuse_a_file_above` asks it here.

    AND WHETHER THE CLONE CAN BE MADE THERE AT ALL (#608). A folder the
    person cannot write in, or a Windows drive that is not there, passed
    too: the three repositories were created and step (7) then refused
    `could not be made a folder (Permission denied)`.
    `refuse_a_parent_nobody_can_write_in` asks both here.
    """
    if not os.path.lexists(clone):
        refuse_a_file_above(clone)
        refuse_a_parent_nobody_can_write_in(clone)
        return
    what, way_out = what_stands_at(clone, project)
    die(" ".join(part for part in (
        "%s already exists, and that is where this project would be cloned, "
        "so the run stops here and nothing was created." % clone,
        what, way_out) if part))


def nearest_entry(path: str):
    """`path`, or its nearest parent that anything stands at (`lexists`), or
    None when not even the top of the path does - a Windows drive that is
    not there."""
    while not os.path.lexists(path):
        parent = os.path.dirname(path)
        if parent == path:
            return None
        path = parent
    return path


def what_blocks(path: str) -> str:
    """What `path` is, when it is not a folder, as the refusal says it: a
    symbolic link by its target where that prints as itself
    (`CONTROL_RE`), as `what_stands_at` says one."""
    if os.path.islink(path):
        try:
            target = os.readlink(path)
        except OSError:
            target = ""
        if target and not CONTROL_RE.search(target):
            return "a symbolic link to %s, which is not a folder" % target
        return "a symbolic link that is not to a folder"
    if os.path.isfile(path):
        return "a file"
    return "neither a folder nor a file"


def refuse_a_file_above(clone: str) -> None:
    """Refuse a clone path that something other than a folder stands above.

    The folders above the clone are made in step (7), by `os.makedirs`, and
    nothing exists yet: the first thing found on the way up from the clone's
    parent must be a folder (`isdir`, so a link to one is one), or there is
    nowhere to make them. Nothing found at all is a drive that is not there,
    and `refuse_a_parent_nobody_can_write_in` refuses that (#608).
    """
    above = nearest_entry(os.path.dirname(clone))
    if above is None or os.path.isdir(above):
        return
    die("%s is %s, and this project would be cloned inside it, at %s, so the "
        "run stops here and nothing was created. %s"
        % (above, what_blocks(above), clone, KEEP_IT))


def drive_of(path: str) -> str:
    r"""The drive, or the network share, `path` is on: `C:`, or
    `\\server\share`; nothing on a POSIX host."""
    return os.path.splitdrive(path)[0]


def refuse_a_parent_nobody_can_write_in(clone: str) -> None:
    """Refuse a clone path whose nearest folder the person cannot write in, or
    whose drive is not there (#608, L2-26).

    The clone is made in step (7), by `os.makedirs` and then `git clone`, in
    the nearest folder that exists. Step (3) asked that this be a folder and
    not whether the person can make one in it, so a parent at mode 555, a
    read-only disk or an ACL that says no passed, and the run created all
    three repositories before step (7) refused.

    THE QUESTION IS ASKED BY DOING IT: a folder is made in the nearest
    existing one and taken away again, which is what step (7) does and the
    only answer that holds for a read-only file system, an ACL, a quota and
    root alike - `os.access` says what the mode bits say, and on Windows
    nothing about a folder at all. It leaves the disk as it found it; the
    folder carries a name of its own so a person who finds one after a
    killed run knows whose it was. Only the making is the question: the
    taking away is best-effort, and says where the folder is when it fails.

    A FILE standing there is `refuse_a_file_above`'s, which runs first and
    has said so, so what is found here is a folder. NOTHING FOUND AT ALL,
    `nearest_entry` None, is a Windows drive that is not there (a
    disconnected network share, a letter nobody has): there is no folder to
    ask, and step (7) would create the repositories before it found out.
    The code is `die`'s, as for every refusal of step (3).
    """
    above = nearest_entry(os.path.dirname(clone))
    if above is None:
        drive = drive_of(clone)
        die("%s, and this project would be cloned at %s, so the run stops "
            "here and nothing was created. %s"
            % (("The drive %s is not there" % drive) if drive
               else "Not even the top of the path is there", clone,
               DRIVE_WAY_OUT))
    try:
        probe = tempfile.mkdtemp(prefix=".openreposhape-write-probe-",
                                 dir=above)
    except OSError as exc:
        die("%s is a folder you cannot write in (%s), and this project would "
            "be cloned inside it, at %s, so the run stops here and nothing "
            "was created. %s"
            % (above, exc.strerror or exc.__class__.__name__, clone,
               WRITE_IT))
    # TAKING IT AWAY IS BEST-EFFORT. The refusal above is for a folder that
    # could not be MADE; one that was made says the person can write here,
    # and a failing `rmdir` (on Windows an indexer or an antivirus can hold a
    # handle on a new folder for a moment) is no reason to say they cannot.
    # The folder left behind is named instead, empty and the person's to
    # delete.
    try:
        os.rmdir(probe)
    except OSError as exc:
        warn("%s, the folder made in %s to try it, could not be taken away "
             "again (%s); it is empty, and yours to delete."
             % (probe, above, exc.strerror or exc.__class__.__name__))


# ---------------------------------------------------------------------------
# what the passthrough tells the scaffold (#538)
# ---------------------------------------------------------------------------

#: THE SCAFFOLD FLAGS THIS FILE READS OUT OF ITS PASSTHROUGH, each with the
#: shortest spelling the scaffold's argparse takes for it. argparse takes an
#: unambiguous prefix of a long option as that option, so `--dry` is the
#: scaffold's `--dry-run`; `--pin` has no shorter spelling, because
#: `--pin-owner` and `--pin-source` share every one, and a prefix of
#: `--referent-chain` shorter than `--referent` is one of `--reference`
#: too. `--pin-source`, read since #608 for the tree a chain's links are
#: looked for in, is `--pin-s`: `--pin-owner` ends the sharing there.
#: `tests/test_setup_project_py.py` holds each row to the
#: scaffold's own `--help`. A word this reads that the scaffold finds
#: ambiguous makes the scaffold's plan refuse, in step (5), before anything
#: is created, so reading one too many is never a run the scaffold made.
PASSED_FLAGS = {"--dry-run": "--d", "--pin": "--pin",
                "--referent-chain": "--referent", "--pin-source": "--pin-s"}


def scaffold_words(passthrough: list) -> list:
    """The passthrough up to an inner `--`: every word after one is a
    positional to argparse, never a flag, and the scaffold takes none."""
    if "--" in passthrough:
        return passthrough[:passthrough.index("--")]
    return list(passthrough)


def names_flag(word: str, flag: str) -> bool:
    """`word` is the scaffold's `flag` (a `PASSED_FLAGS` key), alone or as
    `flag=value`, in a spelling its argparse takes."""
    given = word.split("=", 1)[0]
    return len(given) >= len(PASSED_FLAGS[flag]) and flag.startswith(given)


def passed_values(passthrough: list, flag: str) -> list:
    """Every value the passthrough gives `flag`, in order: `flag=value`, or
    the word after `flag`. A value never starts with `-` in the second
    spelling, because argparse reads such a word as a flag, so a word that
    does is not this flag's value (`--pin --referent-chain x` gives `--pin`
    none, and the scaffold's plan refuses it) and is read again as the flag
    it is (#608, L2-27). The `=` spelling takes whatever follows it."""
    words = scaffold_words(passthrough)
    values = []
    for index, word in enumerate(words):
        if not names_flag(word, flag):
            continue
        if "=" in word:
            values.append(word.split("=", 1)[1])
        elif index + 1 < len(words) and not words[index + 1].startswith("-"):
            values.append(words[index + 1])
    return values


def passes_a_dry_run(passthrough: list) -> bool:
    """`--dry-run` was passed through after `--` (#538).

    The scaffold then creates nothing in step (6), and step (7) cloned three
    repositories that did not exist and refused saying they WERE created.
    `plan_and_confirm` ends the run at the plan instead.
    """
    return any(names_flag(word, "--dry-run")
               for word in scaffold_words(passthrough))


def as_a_bare_link_source(path: str) -> str:
    """`path` as the naming validator reads a `--link-source` that names no
    product: it takes the text before the first `=` for a product when that
    is a link of the chain, so `openXdox=layer`, which the scaffold reads as
    the one path it is, would be read as `layer` for `openXdox`. A path that
    starts `<word>=` is spelled `./<word>=`; one with a separator or a drive
    before its first `=` cannot be a link's name, and stays as it is.

    AN EMPTY PATH IS NEVER GIVEN TO IT. Since #570 the scaffold takes
    `--pin-source` as text and refuses an exactly empty value as
    `pin-source-no-path`, before anything exists (`pin_source_path`), so it
    no longer reads `''` as the directory it runs in: `.` would be a folder
    the plan never reads, and `--link-source=` is refused by the validator as
    `link-source-no-path` (#576). Either would end step (4) naming a flag the
    person never typed, where the plan refuses the value by name.
    `naming_declarations` leaves an empty source out. A BLANK path is a path:
    the scaffold reads `Path(' ')`, so it goes as it is."""
    return "./" + path if re.match(r"[^/\\:=]+=", path) else path


def naming_declarations(passthrough: list, link_remedies=None) -> list:
    """The naming validator's arguments for what the passthrough declares
    about the project (#538): the products of its `--pin`s, and its
    `--referent-chain`, with the tree its links are read from (#608).

    A `<Domainx><Product>` name is a descendant only when the project pins
    its referent, and the scaffold judges the names with the pins it is
    given. Step (4) asked about the three names alone, so it reported `no
    referent pin declared` for a project whose plan, a step later, called it
    a domain descendant. Each product is read the way the scaffold's
    `parse_pin` reads one: the name before `@`, at its last `/`. The LAST
    chain, because a repeated flag that takes one value keeps its last.
    Each is passed as `--flag=value`, so a value that starts with `-` stays
    a value to the validator; one the scaffold refuses is refused at the
    plan.

    THE LINKS ARE VERIFIED FROM THE SAME TREE (#608, L2-25). The scaffold
    reads a chain's links from the tree `--pin-source` names, and the naming
    validator reads them from a `--link-source` it is given; step (4) was
    given none, so a chain the plan verified showed
    `[declared-unverified]` and a WARNING that the link's tree was not
    reachable there, and one the tree broke showed no break at all. The LAST
    `--pin-source`, as the scaffold keeps its last, goes as a bare
    `--link-source` - and only WITH a chain of two links at least: the
    scaffold reads the tree for the links alone, a chain of one link has no
    holder whose declaration a source could answer, and a source no link
    used is a NOTE the plan never prints.

    AN EMPTY LAST `--pin-source` IS LEFT TO THE PLAN (#608, rv608 on #623).
    Since #570 the scaffold refuses `--pin-source ''` as `pin-source-no-path`
    before anything exists, so there is no tree it reads, and step (4) is
    given no `--link-source` for it: it says nothing about a flag the person
    never typed, and step (5)'s plan refuses the value by name, with exit 2.
    The scaffold's own test is `not str(typed)` (`pin_source_path`), so a
    BLANK value is a path and goes as it is, and the rule reads the LAST
    value alone: `--pin-source src --pin-source ''` is empty,
    `--pin-source '' --pin-source src` is not.

    THE NAMING CHECK SPEAKS IN THIS RUN'S WORDS (#661). Its own name for a
    bare source is `--link-source`, and for a link it cannot read it offers
    "a sibling checkout, SHAPE_PIN_SOURCE_<LINK>, or --link-source
    <link>=<path>": a flag this file does not take, which typed after `--`
    ends step (5) in the scaffold's `unrecognized arguments`. So, with a
    chain of two links at least and `link_remedies` (`_main` passes the
    scaffold's own, `scaffold_link_remedies`), it is told
    `--link-source-label=--pin-source` and, for each holder,
    `--link-remedy=<link>=<words>`: what step (5) reads, said as step (5)
    says it. The chain is read as the scaffold reads it
    (`referent_chain_links`: split on commas, each stripped, an empty one
    dropped).
    """
    products = [name for name in (
        pin.strip().split("@", 1)[0].rsplit("/", 1)[-1]
        for pin in passed_values(passthrough, "--pin")) if name]
    chains = passed_values(passthrough, "--referent-chain")
    sources = passed_values(passthrough, "--pin-source")
    chain = tuple(link.strip() for link in chains[-1].split(",")
                  if link.strip()) if chains else ()
    has_links = len(chain) > 1
    names_a_source = bool(sources) and bool(str(sources[-1]))
    spoken = link_remedies(chain) if has_links and link_remedies else None
    return ((["--pins=" + ",".join(products)] if products else [])
            + (["--referent-chain=" + chains[-1]] if chains else [])
            + (["--link-source=" + as_a_bare_link_source(sources[-1])]
               if has_links and names_a_source else [])
            + (["--link-source-label=--pin-source"]
               + ["--link-remedy=%s=%s" % pair for pair in spoken.items()]
               if spoken is not None else []))


# ---------------------------------------------------------------------------
# 4. the names, before anything exists
# ---------------------------------------------------------------------------

def check_names(shape_root: Path, project: str, family: str = "",
                declared=()) -> None:
    """The three names against the naming policy, with what the project
    declares about itself (`naming_declarations`) as the scaffold will
    judge them."""
    say("")
    say("(4) naming policy")
    proc = run([PYTHON,
                str(shape_root / "scripts" / NAMING_VALIDATOR), *declared,
                "--explain", project, project + "-spec", project + "-code"],
               cwd=shape_root)
    if proc.returncode != 0:
        die("the names do not satisfy the naming policy (see above). A naming "
            "mistake caught here costs a message; caught later it costs three "
            "repositories and a rename.", 1)
    if family:
        # The validator above explains the three REPOSITORY names it was
        # given. `--family` names no repository this run creates, so it is
        # asked separately - and said out loud, because a check whose only
        # visible outcome is a refusal is a check a reader cannot tell ran.
        check_family_name(shape_root, family)
        ok("holder       %s satisfies the declared-only family form" % family)


def check_family_name(shape_root: Path, family: str) -> None:
    """`--family` against the naming policy's `family` form.

    THE SAME CHECK `scripts/family.py init` MAKES OF ITS OWN `--family` -
    `_classify_family_name` there - through the same classifier over the same
    `contracts/repository-naming.yaml`. A holder name this tool accepted and
    `family.py add` then refused would be a name that is a family here and
    not there, which is two standards.

    THE FORM IS DECLARED-ONLY, WHICH IS WHY THE ROLE IS PASSED. `InkRouter`
    is spelled exactly like an assembly root - one CamelCase token - and what
    makes a repository a family is `family.yaml` in its own tree, not its
    characters, so the classifier reports this form only when it is ASKED
    for. `openGlass` and `Atlas-Install`, which say what they are in their
    own characters, cannot be declared into a holder and are refused here
    rather than three repositories later.

    Exit 1, not 2, exactly as the three-name check above: this is a FINDING
    about a name, not a refusal to ask the question.
    """
    policy = shape_scripts(shape_root).NamingPolicy.load(
        shape_root / "contracts" / "repository-naming.yaml")
    found = policy.classify(family, "family")
    if found is None:
        die("--family %s matches no family in the naming policy. --family "
            "takes one CamelCase token with no hyphen, underscore, dot or "
            "space - the same rule an assembly root's name follows, because "
            "a holder is spelled like one." % family, 1)
    if found.family != "family":
        die("--family %s classifies as %s, not as a family holder (%s). "
            "--family takes one CamelCase token. An `open<Product>` or "
            "`<X>-Install` name is unambiguous by construction and cannot be "
            "declared into a holder."
            % (family,
               found.family + ("/" + found.role if found.role else ""),
               found.reason), 1)


# ---------------------------------------------------------------------------
# 5. the plan, and one explicit yes
# ---------------------------------------------------------------------------

def scaffold_args(opts: Options, org: str) -> list:
    args = ["--org", org, "--project", opts.project,
            "--visibility", opts.visibility, "--elected-by", opts.elected_by]
    if opts.project_id:
        args += ["--id", opts.project_id]
    if opts.display_name:
        args += ["--name", opts.display_name]
    if opts.local_mode:
        args += ["--local-remote-dir", opts.local_remote_dir]
    return args + list(opts.passthrough)


#: What the scaffold's plan starts with, at the start of a line: the first
#: thing `_print_plan` prints, and nothing printed before it begins so.
PLAN_STARTS = "project      "

#: What step (5) says when the plan did not go through (#608, L2-37): a plan
#: the scaffold printed and then refused, a plan it never printed, and a plan
#: that stopped the first time and not the second. The last names no plan, and
#: no refusal, because the second run is all it has seen.
PLAN_REFUSED = "the plan was refused (see above)."
PLAN_NOT_PRODUCED = "the plan could not be produced (see above)."
PLAN_STOPPED_ONCE = ("the scaffold stopped at the plan (see above). Asked a "
                     "second time it did not stop, so the refusal did not "
                     "happen again: run setup again.")


def why_the_plan_did_not_go_through(shape_root: Path, plan: list,
                                    planned: subprocess.CompletedProcess
                                    ) -> str:
    """What step (5) says of a scaffold `--dry-run`, `plan`, that exited
    nonzero (#608, L2-37).

    Since #573 the dry run prints the plan and THEN asks whether the remotes
    exist, so a refusal can come either side of the plan, and "the plan could
    not be produced (see above)" under a plan that is right there says
    something false. The scaffold's output goes straight to the terminal, not
    through this process, so the question is put once more, captured, and
    only after a refusal: the dry run reads and creates nothing, a run that
    printed and refused prints and refuses again, and a plan that went well
    is never asked twice. Reading every run's plan through a pipe instead
    would put each of them behind the child's buffering and its output
    encoding, on every platform, to word one refusal. A child killed by a
    signal refused nothing, and is not asked.

    THE SECOND RUN IS NOT THE ONE THE PERSON SAW. The words describe what it
    printed, and what is above is the first run's. A passing gh or network
    failure before the plan, or a remote made between the two runs, makes the
    first refuse and the second print the plan and exit 0: it refused
    nothing, and neither "refused" nor "could not be produced" is known to be
    true of what is above. So a second run that exits 0 gets its own words,
    that the refusal did not happen again, and the person runs setup again.
    """
    if planned.returncode < 0:
        return PLAN_NOT_PRODUCED
    again = run(plan, cwd=shape_root, capture=True)
    if again.returncode == 0:
        return PLAN_STOPPED_ONCE
    if any(line.startswith(PLAN_STARTS)
           for line in (again.stdout or "").splitlines()):
        return PLAN_REFUSED
    return PLAN_NOT_PRODUCED


def plan_and_confirm(opts: Options, shape_root: Path, org: str,
                     args: list, clone: str) -> bool:
    """The plan, then the one question. False when the run ends at the plan
    instead: a `--dry-run` passed through after `--` (`passes_a_dry_run`),
    which asks nothing, `--yes` or not, because there is nothing to say yes
    to."""
    say("")
    say("(5) the plan")
    plan = [PYTHON, str(shape_root / SCAFFOLD), *args, "--dry-run"]
    planned = run(plan, cwd=shape_root)
    if planned.returncode != 0:
        raise Refusal(why_the_plan_did_not_go_through(shape_root, plan,
                                                      planned),
                      shell_status(planned.returncode))

    # THE ONE THING THE RUN WRITES ON THIS DISK IS IN THE PLAN TOO (#498).
    # The scaffold's plan names the three repositories; the clone path - set
    # by `--into`, by the developer path's `..`, by a family folder - was
    # said before the `yes` only by `--family`'s `lands at`, far above, so a
    # person learned where the project went from `DONE`. Step (3) has
    # already refused a path that is taken, so this line is where to look
    # afterwards, not a warning; it is printed on every run, `--yes` and no
    # terminal included, since the plan is what an assistant relays to the
    # person deciding.
    say("")
    say("clone into   %s" % clone)

    if passes_a_dry_run(opts.passthrough):
        say("")
        say("--dry-run was passed through to the scaffold, so this run ends "
            "at the plan above: nothing was created and nothing was cloned.")
        return False
    if opts.assume_yes:
        return True
    # THE QUESTION GOES TO THE PERSON'S TERMINAL, NEVER TO A PIPE (#492).
    # `curl ... | bash -s --` hands this file the rest of the script as its
    # stdin, so the yes is read from the controlling terminal instead
    # (`ask`), and the one-liner asks in the person's own terminal as the
    # README says it does. Windows has no controlling terminal to open, so a
    # `Get-Content setup-project.py | py -` run lands here: that is why the
    # README's Windows path DOWNLOADS the file first and then runs it.
    #
    # THE WORDING NAMES THE EXIT THAT KEEPS THE HUMAN IN CHARGE FIRST (#476).
    # An AI assistant's shell has no terminal at all and AGENTS.md forbids it
    # `--yes`, so a refusal that said "re-run with --yes" was the one exit
    # open to it and the one it may not take. The way on is the person's own
    # terminal, where the prompt can ask; `--yes` is named last, as the
    # person's own answer given in advance, and is never put as something to
    # re-run with.
    if not can_ask():
        die("this will create THREE repositories and there is no terminal to "
            "confirm on, so nothing was created. The person deciding runs "
            "this same command in a terminal of their own, and it asks them "
            "there (on Windows, from the downloaded file and not through a "
            "pipe). `--yes` is that person's own answer given in advance, "
            "never an assistant's.")
    say("")
    say("This will create THREE repositories in '%s'." % org)
    if ask("Type yes to continue: ") != "yes":
        die("not confirmed; nothing was created.", 1)
    return True


# ---------------------------------------------------------------------------
# 6. create
# ---------------------------------------------------------------------------

def scaffold(shape_root: Path, args: list) -> None:
    """The scaffold, for real, told `--no-next-steps` (#538): its closing
    block is the `git clone`, `cd` and `make bootstrap` that step (7) runs
    next, and printed here it read as work left to the person. Its `Working
    trees are at` line still prints."""
    say("")
    say("(6) scaffold")
    proc = run([PYTHON, str(shape_root / SCAFFOLD), *args, "--no-next-steps"],
               cwd=shape_root)
    if proc.returncode != 0:
        raise Refusal("the scaffold failed (see above).",
                      shell_status(proc.returncode))


# ---------------------------------------------------------------------------
# 7. clone and bootstrap
# ---------------------------------------------------------------------------

def local_remotes_by_url(directory: str) -> list:
    """The `git -c` arguments that make a clone read the bare repositories in
    `directory` as `file://` URLs and not as plain paths (#440).

    A plain path is git's LOCAL clone, which links or copies the source's
    object files one by one and dies `failed to copy file to ...: No such
    file or directory` when maintenance packs them away mid-walk; a `file://`
    URL goes through upload-pack, which reads the object store and does not
    care. `--no-local` is that for the root clone. Nothing reaches the two leg
    clones `--recurse-submodules` makes from the plain path `.gitmodules`
    records except a rewrite: `url.<base>.insteadOf` applies to the child
    `git clone` too, and, being `-c`, leaves the paths the clone records (its
    own `origin`, `submodule.<name>.url`) as they are.

    THE PREFIX IS `Path.resolve()`, NOT `abspath`, on purpose: it is the
    directory as `scaffold-project.py` wrote it into `.gitmodules`, which
    resolves what `--local-remote-dir` names (macOS `/var` is `/private/var`,
    Windows drops an 8.3 short name), and a prefix that does not match the
    URL rewrites nothing, so the clone silently goes back to the local walk.
    Both spellings of a Windows path (backslashes, slashes) are offered, for
    the same reason.
    """
    resolved = Path(directory).resolve()
    native = os.path.join(str(resolved), "")
    slashes = resolved.as_posix().rstrip("/") + "/"
    uri = resolved.as_uri().rstrip("/") + "/"
    args = []
    for prefix in dict.fromkeys([native, slashes]):
        args += ["-c", "url.%s.insteadOf=%s" % (uri, prefix)]
    return args


def finish_by_hand(parent: str, assembly: str, project: str,
                   local: bool) -> str:
    """The lines that finish a run by hand once the three repositories
    exist (#498): from the clone's parent, the recursive clone, then the
    bootstrap.

    EVERY PATH IS ONE WORD (#538), through `shell_word`, as the family lines
    are (#486): under `--into "/home/a b"` the bare lines split at the space,
    and under `--local-remote-dir` `<assembly>` is a path too. THE WORD IS
    SPELLED FOR `sh` ON EVERY HOST (`posix=True`; #532 rules the printed
    commands POSIX-only), so a Windows path reaches Git Bash whole. And THAT
    clone carries `-c protocol.file.allow=always`, which setup's own clone
    passes: the legs are cloned from the plain paths `.gitmodules` records,
    the file transport, which git refuses a submodule without it. The project
    name is a word already: step (4) held it to the naming policy.
    """
    clone = "git -c protocol.file.allow=always clone" if local else "git clone"
    return ("    cd %s\n"
            "    %s --recurse-submodules %s\n"
            "    cd %s && %s %s"
            % (shell_word(parent, posix=True), clone,
               shell_word(assembly, posix=True), project, PYTHON_CMD,
               BOOTSTRAP))


def clone_and_bootstrap(opts: Options, org: str, landing: Landing) -> dict:
    # WHERE IT LANDS WAS DECIDED IN STEP (3), by `resolve_family`: `--into`
    # or, on the DEVELOPER PATH, the `..` of this checkout - a checkout's
    # parent is where the person cloned it, so the new project lands beside
    # it, and self-bootstrap mode has no such neighbour and passes --into
    # instead. `--family` adds one level to it there and not here, so the
    # plan the person read and the clone that happens cannot disagree.
    parent = str(landing.directory)
    clone = landing.clone_path(opts.project)

    if opts.local_mode:
        base = opts.local_remote_dir
        urls = {
            "assembly": os.path.join(base, opts.project + ".git"),
            "spec": os.path.join(base, opts.project + "-spec.git"),
            "code": os.path.join(base, opts.project + "-code.git"),
        }
    else:
        urls = {
            "assembly": "https://github.com/%s/%s.git" % (org, opts.project),
            "spec": "https://github.com/%s/%s-spec.git" % (org, opts.project),
            "code": "https://github.com/%s/%s-code.git" % (org, opts.project),
        }

    # The three repositories now EXIST. Everything from here is recoverable by
    # hand, so a failure names the command that finishes the job rather than
    # leaving the person wondering what was created.
    by_hand = finish_by_hand(parent, urls["assembly"], opts.project,
                             opts.local_mode)

    # `<into>/<Family>/` IS CREATED HERE AND NOWHERE EARLIER. A rehearsal
    # that stops at the plan (no `--yes`, no terminal) must leave the disk
    # exactly as it found it - a family folder made by a run that created
    # nothing else would be litter the person did not ask for. Step (3)
    # refused a file standing where it goes (#538); one that appeared since,
    # or a folder this account cannot write, is a refusal with the way on,
    # never a traceback after three repositories exist.
    try:
        os.makedirs(parent, exist_ok=True)
    except OSError as exc:
        die("%s could not be made a folder (%s), so there is nowhere to "
            "clone into. The three repositories WERE created. Make it one, "
            "then finish by hand:\n%s"
            % (parent, exc.strerror or exc.__class__.__name__, by_hand))

    # THE BACKSTOP (#498). `refuse_a_taken_clone_path` asked this in step (3),
    # before anything existed, so a path taken HERE appeared while the run
    # was going. `lexists` for the same reason it is there. The way out moves
    # the thing aside FIRST and runs the clone from the clone's parent: as it
    # used to read, the hand clone met the same directory and failed, and
    # `cd <Project>` from anywhere else entered whatever was there.
    if os.path.lexists(clone):
        die("%s already exists - it was not there when step (3) looked - so "
            "there is nowhere to clone into. The three repositories WERE "
            "created. Move it aside, then finish by hand:\n%s"
            % (clone, by_hand))

    say("")
    say("(7) clone and bootstrap")
    clone_cmd = ["git"]
    if opts.local_mode:
        # A local bare repository is a `file://` origin, which git refuses to
        # recurse into by default since the 2022 advisories. This concession
        # is specific to the test path; a real clone from GitHub needs none of
        # it.
        clone_cmd += ["-c", "protocol.file.allow=always"]
        # AND IT IS READ THROUGH GIT, NOT THROUGH ITS FILES (#440). The
        # scaffold pushed into those repositories a moment ago, and the clone
        # of a plain path walks their `objects/` one file at a time, so git's
        # background maintenance packing and deleting the loose objects
        # mid-walk fails it, and the run REFUSES after all three repositories
        # exist. `--no-local` (below) is for the root; the legs are what
        # `local_remotes_by_url` is for.
        clone_cmd += local_remotes_by_url(opts.local_remote_dir)
    if os.name == "nt":
        # THE CLONE THIS TOOL MAKES IS ALWAYS LF, whatever the machine is set
        # to. A project's `contracts/shape-pin.yaml` records a sha256 per
        # copied file, computed over the bytes the scaffold wrote; a checkout
        # that translated them to CRLF would fail its own `validate` on its
        # first run. The preflight warns about the global setting and this
        # overrides it for the one clone that matters, per invocation.
        # A `.gitattributes` in the templates would make this a property of
        # the repository instead of of the clone, and reach clones this tool
        # never made. That is issue #51; this is what holds until then.
        clone_cmd += ["-c", "core.autocrlf=false"]
    clone_cmd += ["clone", "-q"]
    if opts.local_mode:
        clone_cmd.append("--no-local")
    clone_cmd += ["--recurse-submodules", urls["assembly"], clone]
    say("  " + " ".join(clone_cmd))
    cloned = run(clone_cmd)
    if cloned.returncode != 0:
        raise Refusal("the clone failed (see above). The three repositories "
                      "WERE created.", shell_status(cloned.returncode))

    if os.name == "nt":
        # Written INTO the clone as well, so every later checkout in it - a
        # branch switch, a submodule update, a colleague's `git checkout` -
        # keeps the same line endings the digests were computed over.
        run(["git", "-C", clone, "config", "core.autocrlf", "false"],
            capture=True)
        say("  core.autocrlf=false in the clone (the shape pin digests LF "
            "bytes)")

    # ALWAYS the interpreter, never `make`. This is the whole reason this file
    # is the one that runs: `make bootstrap` is one line in a Makefile that
    # runs exactly this, and Windows has no make to run it with.
    bootstrapped = run([PYTHON, BOOTSTRAP],
                       cwd=clone)
    if bootstrapped.returncode != 0:
        raise Refusal("bootstrap failed (see above). The clone is at %s."
                      % clone, shell_status(bootstrapped.returncode))
    return {"clone": clone, "urls": urls}


# ---------------------------------------------------------------------------
# 8. hand over
# ---------------------------------------------------------------------------

#: A word `sh` reads as itself, needing no quotes: `scripts/repo_shape.py`'s
#: `SHELL_BARE_POSIX`. A backslash is not in it, so a Windows path is quoted.
SHELL_BARE_POSIX = re.compile(r"[A-Za-z0-9_./:@%+=,-]+")

#: A word this host's shell reads as itself, needing no quotes:
#: `scripts/repo_shape.py`'s `SHELL_BARE_NT` on Windows, else its
#: `SHELL_BARE_POSIX`. This file runs before any checkout of the standard
#: exists, so it carries its own copy of the rule, and
#: `tests/test_family_printed_quoting.py` holds the two to one answer.
SHELL_BARE = re.compile(r"[A-Za-z0-9_./:%+=\\-]+" if os.name == "nt"
                        else SHELL_BARE_POSIX.pattern)


def shell_word(value, posix: bool = False) -> str:
    """`value` as ONE word of a command pasted into this host's shell: bare
    where every character is itself to it, else in single quotes, doubled
    inside for PowerShell, closed-escaped-reopened for `sh` (#486). A
    leading `=` is quoted too, which zsh would expand.

    `posix` spells it for `sh` on EVERY host, Windows too: Git Bash reads
    the backslash of a bare `C:\\work` as an escape and an apostrophe doubled
    for PowerShell as two quotes, and #532 rules the printed commands
    POSIX-only. The lines #538 adds or changes pass it, as the scaffold's
    NEXT STEPS clone does (`shell_line(..., "posix")`); the family lines
    (`family_next_command`) are #532's and still take this host's dialect."""
    text = str(value)
    bare = SHELL_BARE_POSIX if posix else SHELL_BARE
    if not text.startswith("=") and bare.fullmatch(text):
        return text
    if os.name == "nt" and not posix:
        return "'" + re.sub("(['\u2018\u2019\u201a\u201b])", r"\1\1",
                            text) + "'"
    return "'" + text.replace("'", "'\\''") + "'"


#: What the `switch -c` line of the family block says under it (#647): where
#: an earlier try left that branch in the holder, `switch -c` fails `fatal: a
#: branch named '<branch>' already exists` (exit 128). Another name comes
#: first, because a new branch starts where the holder stands now; going back
#: is right only where the old branch holds work not merged yet. IN WORDS, NOT
#: A SECOND COMMAND, so no line changes and none needs quoting. THE SAME
#: SENTENCE as `scripts/family.py`'s and the holder's `validate-family.py`'s
#: `BRANCH_LEFT` (#607), word for word: this file carries its own copy, as it
#: does of `shell_word`, because it runs before any checkout of the standard
#: exists, and `tests/test_branch_left_bump_leg_setup.py` holds them to one
#: answer.
BRANCH_LEFT = ("If `git switch -c` says that branch already exists, an "
               "earlier act left it: give the branch another name, which "
               "starts it where the holder stands, or, only if that branch "
               "holds work not merged yet, the same command with `switch` "
               "in place of `switch -c` goes back to it and keeps every "
               "commit on it.")


def family_next_command(project: str, org: str, landing: Landing) -> None:
    """The LAST line of the next commands: who records the membership.

    ONLY THE HOLDER RECORDS IT. Nothing in the tree this run just created
    says which family it joined, and that is doctrine rather than an
    omission: the shape confers nothing and membership confers nothing, so
    the fact lives in the holder's `family.yaml` - written by
    `scripts/family.py add`, in one commit that moves the gitlink and the pin
    together - and in no second place that could disagree with it.

    RUN FROM A CHECKOUT OF openRepoShape, which is why the command is spelled
    with the standard's own relative path: `family.py` needs the standard
    beside it, and it works before a holder is on disk at all (RULING of
    2026-09-09, ruling 1b).

    A BRANCH FIRST, AND EVERY PATH ONE WORD (#487, #486). `add` refuses to
    commit onto the holder's tracking branch, so the `git switch -c` that
    makes the branch it suggests comes before it; and a holder under a
    folder with a space in it must reach `--family-root` whole. Under the
    `switch -c`, one comment line says what to do where the holder has that
    branch already (`BRANCH_LEFT`, #647).
    """
    holder = shell_word(landing.holder)
    say("    git -C %s switch -c family/add-%s" % (holder, project.lower()))
    say("                           # a branch first: `add` refuses the")
    say("                           #   holder's tracking branch")
    say("                           # " + BRANCH_LEFT)
    say("    %s scripts/family.py add --family-root %s --member %s"
        % (PYTHON_CMD, holder, shell_word("%s/%s" % (org, project))))
    say("                           # from a checkout of openRepoShape. The")
    say("                           #   HOLDER records the membership; this")
    say("                           #   project's manifest says nothing "
        "about")
    say("                           #   a family, and that is deliberate.")
    if not (landing.holder / FAMILY_MANIFEST).is_file():
        # NAMED, NOT REFUSED. The member can exist before the holder does,
        # and a scaffold that had already succeeded is no place to start
        # refusing things about another repository's tree.
        say("                           # no %s there yet: clone the holder"
            % FAMILY_MANIFEST)
        say("                           #   there first, or run "
            "`family.py init`.")


def hand_over(project: str, clone: str, urls: dict, org: str,
              landing: Landing) -> None:
    say("")
    say("DONE. %s is scaffolded and bootstrapped." % project)
    say("")
    say("  clone       %s" % clone)
    say("  assembly    %s" % urls["assembly"])
    say("  spec        %s" % urls["spec"])
    say("  code        %s" % urls["code"])
    say("")
    say("Next:")
    say("")
    # ONE WORD (#538): a clone under `--into "/home/a b"` is a `cd` the
    # shell would split.
    say("    cd %s" % shell_word(clone, posix=True))
    say("    make validate          # naming, manifest, lockstep pins - what "
        "CI runs")
    # setup.sh's hand-over block, with ONE line added: this file runs where
    # there is no make, and `make validate` is the only line in it that needs
    # one. The three scripts are exactly what that target runs.
    say("                           #   no make? the three scripts/validate-"
        "*.py")
    say("    $EDITOR project.yaml   # the manifest is the SOURCE of this group")
    if landing.family:
        family_next_command(project, org, landing)
    say("")
    say("Advancing a leg is ONE commit in the assembly root that moves the "
        "gitlink,")
    say("contracts/<role>-pin.yaml and any workflow @<sha> naming that leg "
        "together.")
    say("Electing this shape confers nothing: a one-repository project is "
        "reviewed")
    say("identically.")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def _main(argv, invocation_dir: str) -> int:
    original_argv = list(argv)
    opts = parse_args(original_argv, invocation_dir)
    if opts.help:
        usage()
        return 0

    # `--preflight` EXAMINES THE MACHINE AND STOPS, so it returns HERE: before
    # the git probe below (a missing git is one of the things the preflight is
    # for, and refusing on it would report one fault where the preflight
    # exists to report them all), before the checkout probe, and before the
    # clone and the `--org` handshake that follow it. That POSITION is the
    # whole mechanism: `--preflight` needs no organisation and creates
    # nothing because the code that would ask for one is never reached, not
    # because any of it was taught about a flag.
    if opts.preflight:
        return preflight_only(opts)

    # BEFORE the checkout probe, which is itself a `git` call - and before
    # self-bootstrap, which is a `git clone`. The preflight is where a missing
    # prerequisite is meant to be reported, and without this line a machine
    # with no git reaches it only on the developer path. The words are the
    # preflight's own, so a person who fixes this and re-runs sees the same
    # line turn into `[ok] git <version>`.
    if shutil.which("git") is None:
        bad(GIT_MISSING)
        die(PREREQ_MISSING)

    here = source_path()
    script_dir = here.parent if here else Path(invocation_dir)
    if not is_shape_checkout(script_dir):
        return self_bootstrap(opts, original_argv, invocation_dir)
    shape_root = script_dir

    # setup.sh CLONED this checkout (its section 0) and ran this file from it.
    # The checkout is real, so the developer path is right in every respect but
    # one: there is no fork `origin` behind the person, exactly as in
    # `self_bootstrap` above, so `--org` is required rather than detected --
    # otherwise a `curl | bash` run started inside an unrelated repository
    # would scaffold into THAT repository's organisation.
    if os.environ.get("OPENREPOSHAPE_SELF_BOOTSTRAP") == "1" and not opts.org:
        die(ORG_REQUIRED)

    preflight(opts)
    org = resolve_org(opts, invocation_dir)
    resolve_project_and_elector(opts, shape_root)
    landing = resolve_family(opts, shape_root)
    clone = landing.clone_path(opts.project)
    refuse_a_taken_clone_path(clone, opts.project)
    check_names(shape_root, opts.project, opts.family,
                naming_declarations(opts.passthrough,
                                    scaffold_link_remedies(shape_root)))
    args = scaffold_args(opts, org)
    if not plan_and_confirm(opts, shape_root, org, args, clone):
        return 0
    scaffold(shape_root, args)
    created = clone_and_bootstrap(opts, org, landing)
    hand_over(opts.project, created["clone"], created["urls"], org, landing)
    return 0


def main(argv=None) -> int:
    # PowerShell 5.1 hands a child process the machine's ANSI code page, and
    # cp1252 cannot encode a character this file does not use - but a CHILD's
    # output travels through this process's streams too, and the validators
    # and the scaffold are not ASCII-only. Guarded: `reconfigure` is 3.7+ and
    # a stream that has been replaced (a test harness, a pipe wrapper) may not
    # have it at all, and failing to set an encoding is not a reason to refuse
    # to scaffold.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass

    invocation_dir = os.getcwd()
    try:
        return _main(sys.argv[1:] if argv is None else list(argv),
                     invocation_dir)
    except Refusal as refusal:
        sys.stdout.flush()
        print("\nREFUSED: %s" % refusal, file=sys.stderr, flush=True)
        return refusal.code
    except KeyboardInterrupt:
        print("\nREFUSED: interrupted; nothing further was created.",
              file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())
