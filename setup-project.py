#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""setup-project.py - clone the standard into a temp dir, scaffold, clean up.

The NATIVE WINDOWS way in, and the exact twin of `setup.sh` everywhere else:

    Invoke-WebRequest https://raw.githubusercontent.com/opensoft/openRepoShape/main/setup-project.py -OutFile setup-project.py
    py setup-project.py <Project> --org <your-org>

Run from wherever: if this is not already a checkout of openRepoShape it
self-bootstraps - clones `opensoft/openRepoShape` (or `$OPENREPOSHAPE_REPO`,
for a fork or mirror) into a temporary directory, re-runs itself from there
with the same arguments, and removes the temporary checkout on exit
(`--keep-shape-checkout` keeps it and prints the path). `--org` is then
REQUIRED: there is no fork origin left to read it from. Run it from inside an
existing checkout instead (the developer path) and it behaves exactly as
`setup.sh` does, still detecting the organisation from `origin`.

Either way it checks your machine, works out which organisation you are
scaffolding into, checks the three repository names against the naming policy,
shows you the plan, asks once, creates the three repositories, clones the
assembly root and bootstraps it. Nothing is created before you have said yes.

WHY A SECOND ENTRY POINT AND NOT A REWRITE OF setup.sh. `setup.sh` is bash and
calls a literal `python3`; Windows has neither. The python.org installer puts
`python.exe` and the `py` launcher on PATH and no `python3` at all, and there
is no `make` either. So this file runs the RUNNING interpreter (`sys.executable`)
for every child process and `scripts/bootstrap.py` directly instead of
`make bootstrap`. It adds no behaviour of its own and skips no step: the same
`scripts/validate-repository-naming.py`, the same `scaffold-project.py`, the
same plan and the same one yes, in the same order, with the same exit codes.
RATIFIED AS AN IMPROVEMENT, not a divergence to fix: where `set -e` ends
setup.sh silently on a failed child, this file prints a `REFUSED:` line naming
which one failed - the plan, the scaffold, the clone or the bootstrap - and
what was already created, then exits with that child's status. Four lines
setup.sh does not print, about the four moments a person most needs told.
`tests/test_setup_project_py.py` mirrors `tests/test_setup_sh.py` case for
case, and a parity test holds the two flag lists together.

PURE ASCII, IN THE SOURCE AND IN THE OUTPUT. Windows PowerShell 5.1 - still
the default shell on a stock Windows install - renders a console in the
machine's ANSI code page, re-encodes piped text as ASCII (its default
`$OutputEncoding`), and writes UTF-16 when `>` redirects to a file. No byte
above 0x7F survives all three, so a tick, an arrow or an em dash arrives as
mojibake, as a question mark, or raises an encoding error on the way out.
`[ok]` and `[!!]` cost a reader nothing and cannot be re-encoded wrongly.
`tests/test_repo_hygiene.py::test_setup_project_py_is_pure_ascii` holds it.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

UPSTREAM_ORG = "opensoft"
DEFAULT_SHAPE_REPO = "https://github.com/opensoft/openRepoShape.git"
VISIBILITY_CHOICES = ("private", "public", "internal")

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
#: or `py`, not the name setup.sh hard-codes.
PYTHON = sys.executable

#: The same interpreter, spelled for a HUMAN TO RETYPE. `sys.executable` is an
#: absolute path, and the python.org default has a space in it
#: (`C:\Program Files\Python312\python.exe`); pasted unquoted into a command
#: a person is told to run by hand, it is two arguments and an error. The
#: basename is the word they typed to get here, and it is on their PATH
#: because they just used it. argv keeps `PYTHON`; prose gets this.
PYTHON_CMD = Path(sys.executable).name or PYTHON


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
  --into <dir>            PARENT directory for the clone (default: ..), so the
                          clone lands at <dir>/<Project>
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
  --yes                   skip the confirmation prompt
  --local-remote-dir <d>  TEST PATH: create three BARE repositories in <d> and
                          use them as origins. No network, no `gh`, and no real
                          repository is created.
  -h, --help              this text

Set $OPENREPOSHAPE_REPO to clone a fork or mirror in self-bootstrap mode
instead of opensoft/openRepoShape.

Anything after `--` is passed straight through to scaffold-project.py.
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


def run(argv, cwd=None, capture: bool = False) -> subprocess.CompletedProcess:
    """One spelling of "run a program", with the output decoding pinned.

    `encoding="utf-8", errors="replace"`: a child's bytes are its own business
    and a mojibake byte in a `git --version` string must not raise out of the
    preflight. Output is INHERITED unless `capture` asks otherwise, so
    `scaffold-project.py` and the validators print straight to the terminal
    the way they do under setup.sh.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        return subprocess.run(argv, cwd=str(cwd) if cwd is not None else None,
                              capture_output=capture, text=True,
                              encoding="utf-8", errors="replace", check=False)
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
    """`git --version` -> `2.43.0`; the awk in setup.sh:219 and :246."""
    proc = run(argv, capture=True)
    line = (proc.stdout or "").splitlines()
    parts = line[0].split() if line else []
    return parts[field] if len(parts) > field else "(unknown version)"


# ---------------------------------------------------------------------------
# arguments
# ---------------------------------------------------------------------------

class Options:
    """The parsed command line. One attribute per setup.sh variable."""

    def __init__(self):
        self.project = ""
        self.org = ""
        self.project_id = ""
        self.display_name = ""
        self.visibility = "private"
        self.elected_by = ""
        self.into = ""
        self.local_remote_dir = ""
        self.assume_yes = False
        self.allow_upstream_org = False
        self.shape_ref = ""
        self.keep_shape_checkout = False
        self.passthrough = []
        self.help = False

    @property
    def local_mode(self) -> bool:
        return bool(self.local_remote_dir)


def parse_args(argv, invocation_dir: str) -> Options:
    """A while loop over the list, mirroring setup.sh:113-131.

    HAND-ROLLED, NOT argparse. The two entry points have to refuse the same
    things in the same words with the same exit codes, and argparse owns its
    own usage text, its own `--flag=value` spelling and its own exit code 2 on
    a message nobody wrote. A loop is what keeps the parity test honest.
    """
    opts = Options()
    rest = list(argv)
    # WHICH SPELLING set the project, because the two do not compose the same
    # way. `--project A --project B` is B, exactly as setup.sh's last-wins
    # `case` is. But a positional and a `--project` are two different names
    # for one thing, and silently taking either is how a person scaffolds a
    # project they did not name - so that pair is refused in BOTH orders.
    positional = ""

    def value(flag: str) -> str:
        if not rest:
            die("%s needs a value" % flag)
        return rest.pop(0)

    def two_names(first: str, second: str) -> None:
        # The `openRepoShape` command's own refusal (openRepoShape:147), word
        # for word, whichever order the two names arrived in.
        die("two project names, '%s' and '%s'. One positional "
            "<Project>, then flags." % (first, second))

    while rest:
        arg = rest.pop(0)
        if arg == "--project":
            named = value("--project")
            if positional:
                two_names(positional, named)
            opts.project = named
        elif arg == "--org":
            opts.org = value("--org")
        elif arg == "--id":
            opts.project_id = value("--id")
        elif arg == "--name":
            opts.display_name = value("--name")
        elif arg == "--visibility":
            opts.visibility = value("--visibility")
        elif arg == "--elected-by":
            opts.elected_by = value("--elected-by")
        elif arg == "--into":
            opts.into = abspath(value("--into"), invocation_dir)
        elif arg == "--local-remote-dir":
            opts.local_remote_dir = abspath(value("--local-remote-dir"),
                                            invocation_dir)
        elif arg in ("--yes", "-y"):
            opts.assume_yes = True
        elif arg == "--allow-upstream-org":
            opts.allow_upstream_org = True
        elif arg == "--shape-ref":
            opts.shape_ref = value("--shape-ref")
        elif arg == "--keep-shape-checkout":
            opts.keep_shape_checkout = True
        elif arg in ("-h", "--help"):
            opts.help = True
            return opts
        elif arg == "--":
            opts.passthrough = rest
            break
        elif arg.startswith("-") or arg == "":
            # `arg == ""` before the positional branch: an empty argument is
            # not a project name. setup.sh's `case` falls through to `*)` on
            # one and refuses `unknown argument: ` with an empty tail, so this
            # does too - the same words, including the space that ends them.
            usage(sys.stderr)
            die("unknown argument: %s" % arg)
        else:
            # The `openRepoShape` command's shape, folded in here so the
            # Windows way in is one file instead of two: a bare <Project> is
            # --project.
            if opts.project:
                two_names(opts.project, arg)
            positional = arg
            opts.project = arg

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
    return ((root / "scaffold-project.py").is_file()
            and (root / "contracts" / "repository-naming.yaml").is_file())


def self_bootstrap(opts: Options, original_argv, invocation_dir: str) -> int:
    """setup.sh:157-206, in Python: clone, re-run from there, clean up."""
    if not opts.org:
        die("running outside a checkout of openRepoShape (self-bootstrap "
            "mode): there is no fork origin to read the organisation from. "
            "Re-run with --org <your-org>.")

    shape_repo = os.environ.get("OPENREPOSHAPE_REPO") or DEFAULT_SHAPE_REPO

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
        clone_cmd += [shape_repo, checkout]
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

def preflight(opts: Options) -> None:
    say("openRepoShape setup")
    say("")
    say("(1) preflight")
    failed = False

    if shutil.which("git"):
        ok("git %s" % program_version(["git", "--version"], 2))
    else:
        bad("git is not installed. Install it: https://git-scm.com/downloads")
        failed = True

    # THE RUNNING INTERPRETER, never a probe for one on PATH. `python3` does
    # not exist on a stock Windows install and `python` may be a Store stub
    # that opens a web page; the interpreter that reached this line is the one
    # that will run every child process, so it is the one reported and the one
    # whose version is checked.
    version = sys.version_info
    if version >= (3, 9):
        ok("python %d.%d.%d (%s)" % (version[0], version[1], version[2], PYTHON))
    else:
        bad("this interpreter is %d.%d, and 3.9 or newer is required. Install "
            "a newer Python and re-run: https://www.python.org/downloads/"
            % (version[0], version[1]))
        failed = True

    # `make` is NOT checked, here or anywhere below. setup.sh probes for it
    # and falls back; this file has no fallback to make because it never uses
    # make - one command, on every platform, and Windows has no make at all.
    ok("bootstrap runs as `%s scripts/bootstrap.py` (make is not required)"
       % PYTHON_CMD)

    if opts.local_mode:
        ok("gh not required (--local-remote-dir: bare repositories on disk, "
           "no network)")
    elif shutil.which("gh"):
        ok("gh %s" % program_version(["gh", "--version"], 2))
        if run(["gh", "auth", "status"], capture=True).returncode == 0:
            login = run(["gh", "api", "user", "--jq", ".login"],
                        capture=True)
            suffix = ""
            if login.returncode == 0 and (login.stdout or "").strip():
                suffix = " as " + login.stdout.strip()
            ok("gh is authenticated%s" % suffix)
        else:
            bad("gh is not authenticated. Run: gh auth login")
            failed = True
    else:
        bad("gh is not installed. Install it: https://cli.github.com - or "
            "re-run with --local-remote-dir <dir> to try this offline against "
            "bare repositories on disk.")
        failed = True

    # WARN, DO NOT REFUSE (Brett Heap, 2026-09-05). `core.autocrlf=true` is
    # what the git-for-Windows installer offers by default, and it rewrites
    # every checked-out file's line endings - which makes a scaffolded
    # project's copies differ from the sha256 rows its own shape pin records,
    # so its first `validate` reports drift nobody introduced. It is a machine
    # setting, not a fault in this run, and the clone this tool makes is
    # configured correctly regardless (see clone_and_bootstrap), so the run
    # continues.
    if os.name == "nt":
        # `--global`, because the message below tells the person to fix the
        # GLOBAL setting and a warning about a value it did not read would
        # send them to change something that was already right.
        # `--type=bool` so `1`, `yes`, `on` and `true` are one answer; unset
        # is exit 1 and empty stdout, which is silence, not a warning.
        configured = run(["git", "config", "--global", "--type=bool", "--get",
                          "core.autocrlf"], capture=True)
        if (configured.stdout or "").strip() == "true":
            warn("git core.autocrlf is true. Every file git checks out gets "
                 "CRLF line endings, and a project's shape pin digests the "
                 "bytes it was written with - so `validate` will report drift "
                 "in files nobody edited. Fix it once, for this machine: "
                 "git config --global core.autocrlf false")

    if failed:
        die("one or more prerequisites are missing (see above).")


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


def resolve_org(opts: Options, invocation_dir: str) -> str:
    """setup.sh:262-353, transcribed."""
    say("")
    say("(2) organisation")

    # `gh repo view` with no argument resolves the CURRENT repository by its
    # own rules, and on a checkout with two remotes (`origin` plus an
    # `upstream` pointing at opensoft/openRepoShape - kept only by someone
    # contributing back to the standard itself) it can prefer `upstream` over
    # `origin`. `origin` is the remote that means "this clone", in every mode,
    # so it is read directly and parsed by hand; `gh repo view` is consulted
    # only as a fallback, and only ON THE ORIGIN URL itself (never bare), so
    # it cannot go pick `upstream` either.
    #
    # Read against the INVOCATION directory, not the directory this file lives
    # in. The two are the same for the README's own `cd openRepoShape` usage;
    # they differ only when this file is invoked by a path from elsewhere, and
    # then the clone you are IN is the one whose organisation you mean.
    origin_url = remote_url(invocation_dir, "origin")
    origin_org = detect_org_from_url(origin_url) if origin_url else ""

    # `origin` pointing at opensoft itself means this checkout IS the upstream
    # - there is no fork to inherit an organisation from, exactly like
    # self-bootstrap mode, so the fix is the same: pass --org.
    if not opts.org and origin_org == UPSTREAM_ORG:
        die("you are running from the upstream checkout (%s); pass --org "
            "<your-org>." % origin_url)

    org = opts.org
    if org:
        ok("organisation %s (from --org)" % org)
    elif origin_org:
        org = origin_org
        ok("organisation %s (from the `origin` remote: %s)" % (org, origin_url))
    else:
        viewed = ""
        if origin_url and not opts.local_mode:
            proc = run(["gh", "repo", "view", origin_url, "--json", "owner",
                        "--jq", ".owner.login"], capture=True)
            if proc.returncode == 0:
                viewed = (proc.stdout or "").strip()
        if viewed:
            org = viewed
            if org == UPSTREAM_ORG:
                die("you are running from the upstream checkout (%s); pass "
                    "--org <your-org>." % origin_url)
            ok("organisation %s (from `gh repo view` on the origin URL: %s; "
               "could not parse it by hand)" % (org, origin_url))
        elif opts.local_mode:
            org = "localorg"
            ok("organisation %s (placeholder; no `origin` remote to read, and "
               "--local-remote-dir creates nothing on GitHub)" % org)
        else:
            die("cannot work out which organisation to scaffold into: this "
                "clone has no `origin` remote and no --org was given. Re-run "
                "with --org <your-org>.")

    # A checkout kept for contributing to the standard itself may still carry
    # an `upstream` remote pointing at opensoft. Name it so a person who did
    # not expect one at all is not left guessing why the detected organisation
    # is not opensoft's.
    upstream_url = remote_url(invocation_dir, "upstream")
    if upstream_url:
        upstream_org = detect_org_from_url(upstream_url)
        if upstream_org and origin_org and upstream_org != origin_org:
            say("  upstream is %s; scaffolding into %s" % (upstream_org, org))

    # The guard that matters now that the organisation is never silently set
    # to opensoft by detection (see the die above): the only way to reach this
    # point with opensoft is an explicit `--org opensoft`, which is almost
    # never what anyone means. It applies in EVERY mode, --local-remote-dir
    # included: `--org` is what a scaffolded `project.yaml` records as the
    # owner of all three legs, so a manifest reading `opensoft/Sample` is
    # wrong regardless of whether any network call happened.
    if org == UPSTREAM_ORG and not opts.allow_upstream_org:
        die("the organisation is '%s', which is the UPSTREAM owner of "
            "openRepoShape itself, and scaffolding here would create three "
            "repositories in opensoft's own namespace.\n"
            "\n"
            "  Wrong guess?  re-run with --org <your-org>\n"
            "  You meant it? re-run with --allow-upstream-org" % UPSTREAM_ORG)
    return org


# ---------------------------------------------------------------------------
# 3. the project
# ---------------------------------------------------------------------------

def ask(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return ""


def resolve_project_and_elector(opts: Options, shape_root: Path) -> None:
    """setup.sh:355-386, transcribed."""
    say("")
    say("(3) project")
    if not opts.project and sys.stdin.isatty():
        opts.project = ask("  project name (ONE CamelCase token, e.g. Atlas): ")
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
# 4. the names, before anything exists
# ---------------------------------------------------------------------------

def check_names(shape_root: Path, project: str) -> None:
    say("")
    say("(4) naming policy")
    proc = run([PYTHON,
                str(shape_root / "scripts" / "validate-repository-naming.py"),
                "--explain", project, project + "-spec", project + "-code"],
               cwd=shape_root)
    if proc.returncode != 0:
        die("the names do not satisfy the naming policy (see above). A naming "
            "mistake caught here costs a message; caught later it costs three "
            "repositories and a rename.", 1)


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


def plan_and_confirm(opts: Options, shape_root: Path, org: str,
                     args: list) -> None:
    say("")
    say("(5) the plan")
    planned = run([PYTHON, str(shape_root / "scaffold-project.py"), *args,
                   "--dry-run"], cwd=shape_root)
    if planned.returncode != 0:
        raise Refusal("the plan could not be produced (see above).",
                      shell_status(planned.returncode))

    if opts.assume_yes:
        return
    # A SCRIPT THAT ARRIVED ON STDIN HAS AN EXHAUSTED STDIN, so this refusal
    # is what a `Get-Content setup-project.py | py -` run gets instead of a
    # prompt nobody can answer. That is exactly why the README's Windows path
    # DOWNLOADS the file first and then runs it: a file on disk leaves stdin
    # attached to the terminal the person is typing at.
    if not sys.stdin.isatty():
        die("this will create THREE repositories and there is no terminal to "
            "confirm on. Re-run with --yes if you mean it.")
    say("")
    say("This will create THREE repositories in '%s'." % org)
    if ask("Type yes to continue: ") != "yes":
        die("not confirmed; nothing was created.", 1)


# ---------------------------------------------------------------------------
# 6. create
# ---------------------------------------------------------------------------

def scaffold(shape_root: Path, args: list) -> None:
    say("")
    say("(6) scaffold")
    proc = run([PYTHON, str(shape_root / "scaffold-project.py"), *args],
               cwd=shape_root)
    if proc.returncode != 0:
        raise Refusal("the scaffold failed (see above).",
                      shell_status(proc.returncode))


# ---------------------------------------------------------------------------
# 7. clone and bootstrap
# ---------------------------------------------------------------------------

def clone_and_bootstrap(opts: Options, shape_root: Path, org: str) -> dict:
    # `..` is the DEVELOPER PATH's answer: a checkout's parent is where the
    # person cloned it, so the new project lands beside it. Self-bootstrap
    # mode has no such neighbour to land beside and passes --into instead.
    parent = opts.into or os.path.abspath(os.path.join(str(shape_root), ".."))
    os.makedirs(parent, exist_ok=True)
    clone = os.path.join(parent, opts.project)

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
    if os.path.exists(clone):
        die("%s already exists, so there is nowhere to clone into. The three "
            "repositories WERE created. Finish by hand:\n"
            "    git clone --recurse-submodules %s\n"
            "    cd %s && %s scripts/bootstrap.py"
            % (clone, urls["assembly"], opts.project, PYTHON_CMD))

    say("")
    say("(7) clone and bootstrap")
    clone_cmd = ["git"]
    if opts.local_mode:
        # A local bare repository is a `file://` origin, which git refuses to
        # recurse into by default since the 2022 advisories. This concession
        # is specific to the test path; a real clone from GitHub needs none of
        # it.
        clone_cmd += ["-c", "protocol.file.allow=always"]
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
    clone_cmd += ["clone", "-q", "--recurse-submodules", urls["assembly"],
                  clone]
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
    # exists beside setup.sh: `make bootstrap` is one line in a Makefile that
    # runs exactly this, and Windows has no make to run it with.
    bootstrapped = run([PYTHON, os.path.join("scripts", "bootstrap.py")],
                       cwd=clone)
    if bootstrapped.returncode != 0:
        raise Refusal("bootstrap failed (see above). The clone is at %s."
                      % clone, shell_status(bootstrapped.returncode))
    return {"clone": clone, "urls": urls}


# ---------------------------------------------------------------------------
# 8. hand over
# ---------------------------------------------------------------------------

def hand_over(project: str, clone: str, urls: dict) -> None:
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
    say("    cd %s" % clone)
    say("    make validate          # naming, manifest, lockstep pins - what "
        "CI runs")
    # setup.sh's hand-over block, with ONE line added: this file runs where
    # there is no make, and `make validate` is the only line in it that needs
    # one. The three scripts are exactly what that target runs.
    say("                           #   no make? the three scripts/validate-"
        "*.py")
    say("    $EDITOR project.yaml   # the manifest is the SOURCE of this group")
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

    # BEFORE the checkout probe, which is itself a `git` call - and before
    # self-bootstrap, which is a `git clone`. The preflight is where a missing
    # prerequisite is meant to be reported, and without this line a machine
    # with no git reaches it only on the developer path. The words are the
    # preflight's own, so a person who fixes this and re-runs sees the same
    # line turn into `[ok] git <version>`.
    if shutil.which("git") is None:
        bad("git is not installed. Install it: https://git-scm.com/downloads")
        die("one or more prerequisites are missing (see above).")

    here = source_path()
    script_dir = here.parent if here else Path(invocation_dir)
    if not is_shape_checkout(script_dir):
        return self_bootstrap(opts, original_argv, invocation_dir)
    shape_root = script_dir

    preflight(opts)
    org = resolve_org(opts, invocation_dir)
    resolve_project_and_elector(opts, shape_root)
    check_names(shape_root, opts.project)
    args = scaffold_args(opts, org)
    plan_and_confirm(opts, shape_root, org, args)
    scaffold(shape_root, args)
    created = clone_and_bootstrap(opts, shape_root, org)
    hand_over(opts.project, created["clone"], created["urls"])
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
