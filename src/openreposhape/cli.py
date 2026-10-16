# SPDX-License-Identifier: Apache-2.0
"""The five commands the openreposhape package installs (#563).

`openRepoShape` RE-STATES THE BASH LAUNCHER (v1.0.1's `openRepoShape`) IN
PYTHON: its four modes, `<Project>`, `--preflight`, `--doctor` and
`--help | --version`, its argument routing, one mode per run, `--org` from
the flag or `$OPENREPOSHAPE_ORG` or a prompt and never a default, its usage
text, its checks on a ref, and `--doctor`'s run of the standard's own
`shape-doctor.py`. What it does NOT re-state is fetching: the launcher
fetches `setup.sh` and clones the standard on every run, and this runs the
package's clone of it (`standard.prepare`). Nor `--install` and the ref it
records: pipx placed this command and the stamp names its commit, so
`--install` refuses and names `pipx upgrade openreposhape`.

`scaffold-project`, `adopt-project`, `update-shape` and `shape-doctor` each
run that file from the clone, with every argument unchanged, in the
directory the command was typed in. They are the names README, AGENTS.md and
`docs/cli.md` already use, less `./` and `.py`, so `docs/cli.md` stays the
one reference for their flags.

EVERY CHILD GETS `standard.child_environment()`: the package environment's
scripts directory first on PATH wherever the `git-filter-repo` it depends on
is there.

PURE ASCII, like `setup-project.py`, because Windows PowerShell 5.1 renders a
console in the machine's ANSI code page: the usage text and every refusal
here arrive there intact.
"""

from __future__ import annotations

import os
import subprocess
import sys

from . import standard
from .standard import Refusal

#: THE USAGE, the launcher's own, less what pipx and the stamp replace: the
#: lines a person meets are the same lines, in the same columns, and the
#: `--install` line says where installing went.
USAGE = """\
openRepoShape --install            refused here: pipx upgrade openreposhape updates it
openRepoShape --preflight          check this MACHINE and stop; creates nothing
openRepoShape --doctor [<path>] [--json] [--placement-plan <file>]
                                   diagnose a REPOSITORY against this standard
openRepoShape <Project> [--org <org>] [setup-project.py options] [-- <scaffold flags>]
openRepoShape --help | --version

Those lines are the whole command: check the machine you are on, diagnose a
repository, scaffold a project. Run with NO arguments it prints this and
exits 1, because a bare run has nothing to do.

<Project> is the assembly-root name, ONE CamelCase token (e.g. Atlas); omit it
and setup asks, if a terminal is attached. `--org` comes from that flag,
else $OPENREPOSHAPE_ORG, else a prompt -- it is NEVER defaulted. Every other
argument reaches setup-project.py unchanged: --visibility, --elected-by,
--family, --into, --yes, --local-remote-dir, and anything after `--`, which
setup-project.py hands on to scaffold-project.py. `python3 setup-project.py
--help` lists them all, and so does `docs/cli.md` in the repository. The
project lands in the directory you ran this from, unless --into says where.

This command came with the openreposhape package, which installed four more
beside it. Each runs that tool of the standard with every argument
unchanged, in the directory you typed it in; `docs/cli.md` is their
reference:

  scaffold-project   adopt-project   update-shape   shape-doctor

THE STANDARD THEY RUN is a full clone of openRepoShape at the commit this
package was built from, made once per commit in a cache in your home
directory and kept. Before every run the clone must be at that commit, carry
no change, and digest to the value the package carries (sorted-ls-tree-r-v1,
computed by the clone's own scripts/repo_shape.py), so a project scaffolded
from it pins exactly the release you installed. `--version` names the
release, its commit, its digest and the clone. A build that is not a release
follows main; run from a checkout's src/ (an editable install), it uses that
checkout as it stands.

  $OPENREPOSHAPE_REPO   owner/name, URL or path to clone (default opensoft/openRepoShape)
  $OPENREPOSHAPE_REF    run at this branch, tag or commit instead, for one run;
                        no digest is checked then (`--shape-ref` on a
                        scaffold run does the same)
  $OPENREPOSHAPE_ORG    the organisation, when --org is not given

`--install` places nothing here. pipx (or pip) placed this command, and
keeps it current: `pipx upgrade openreposhape`. The estate verbs are not
here either. `park` and `resume` -- commit, push and RECORD an estate's open
features, then rebuild them on the next workstation -- are
opensoft/openRepoTools', and its own installer places them:

  curl -fsSL https://raw.githubusercontent.com/opensoft/openRepoTools/main/openRepoTools | bash -s -- --install

`--doctor [<path>] [--json] [--placement-plan <file>]` runs `shape-doctor.py`
over <path> (default `.`) and prints one row per check and ONE verdict:
`COMPLIANT`, `COMPLIANT, SHAPE BEHIND`, `DRIFTED`, `MISPLACED`, `INVALID`,
`NOT A SHAPE ROOT` or `CANNOT ANSWER`. Every finding names the command that
fixes it. Exit 0 compliant, 1 findings, 2 not a shape root, 3 when it cannot
answer (`CANNOT ANSWER`, no such <path>, a `--placement-plan` it cannot
write); this command's own refusals exit 2. `--json` is the same report as
one JSON object. The doctor writes no file but the `--placement-plan <file>`
you name, at the path you give (a relative <file> lands in the directory you
ran this from, even inside the repository), and moves nothing.

It runs from the package's clone of the standard, which is KEPT for the NEXT
lines that name files in it; the report's last line names that clone (under
`--json`, on stderr, so stdout stays one JSON object).

`--preflight` is the MACHINE check: setup-project.py's own, run from the copy
this package carries, so it answers on a machine with no git yet.
"""

#: Why `--install` refuses, said where it does.
INSTALL_REFUSED = (
    "--install places nothing here: this openRepoShape is the "
    "openreposhape package's, and the installer that placed it keeps it "
    "current:\n"
    "    pipx upgrade openreposhape\n"
    "    The one-line install (install.sh) places the bash openRepoShape "
    "instead. Use one or the other.")

#: setup-project.py's value-taking flags, named so their VALUE is never
#: mistaken for the positional <Project>. `--shape-ref` is one of them, and
#: is also the ref of this run's clone (`Run.shape_ref`).
VALUE_FLAGS = ("--id", "--name", "--visibility", "--elected-by", "--family",
               "--into", "--local-remote-dir", "--shape-ref")


def say(text: str = "") -> None:
    print(text, flush=True)


def utf8_streams() -> None:
    """`setup-project.py`'s guard: a child's output and a path in a refusal
    travel through these streams, and the console's code page may not encode
    them. A stream that cannot be reconfigured is left as it is."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def terminal_attached() -> bool:
    """The launcher's `[ -t 0 ]`."""
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except (AttributeError, ValueError, OSError):
        return False


def run_child(argv: list, env: dict, cwd: str | None = None) -> int:
    """`argv`, its stdin, stdout and stderr this command's own, and its exit
    status as a shell would report it.

    A CTRL-C REACHES THE CHILD TOO, which is in the same process group and
    prints its own refusal, so the first one here waits for the child to
    answer it, and only a second one kills it. A child killed by a signal
    reports 128 + the signal, as bash does.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        child = subprocess.Popen(argv, env=env, cwd=cwd)
    except OSError as exc:
        raise Refusal(f"could not start {argv[0]}: {exc}") from exc
    interrupted = False
    while True:
        try:
            status = child.wait()
            break
        except KeyboardInterrupt:
            if interrupted:
                child.kill()
            interrupted = True
    return 128 - status if status < 0 else status


def guarded(body, argv) -> int:
    """`body(argv)`'s exit status, with a refusal printed the launcher's way
    (`\\nREFUSED: <message>` on stderr) and its code returned."""
    utf8_streams()
    args = sys.argv[1:] if argv is None else list(argv)
    try:
        return body(args)
    except Refusal as refusal:
        sys.stdout.flush()
        print(f"\nREFUSED: {refusal}", file=sys.stderr, flush=True)
        return refusal.code
    except KeyboardInterrupt:
        print("\nREFUSED: interrupted.", file=sys.stderr, flush=True)
        return 130


# --- openRepoShape -------------------------------------------------------------

class Run:
    """What the arguments asked for: the launcher's variables, one each."""

    def __init__(self) -> None:
        self.mode = "run"
        self.preflight = False
        self.project = ""
        self.org = ""
        self.doctor_path = ""
        self.doctor_path_given = False
        self.doctor_args: list = []
        self.doctor_json = False
        self.plan_file = ""
        self.passthrough: list = []
        self.shape_ref = ""


def set_mode(run: Run, mode: str) -> None:
    """ONE MODE PER RUN: two is a refusal, never last-wins (Copilot, PR
    #96). A person who typed both meant one of them."""
    if run.mode not in ("run", mode):
        raise Refusal(
            f"--{run.mode} and --{mode} are two different runs; pass one.\n"
            "    --install places nothing here (pipx upgrade openreposhape "
            "updates this command);\n"
            "    --doctor reads a repository and writes nothing into it but "
            "a\n    --placement-plan <file> you name.")
    run.mode = mode


def value_of(args: list, at: int, flag: str) -> str:
    """The value after `flag`, which must be there and not be empty: the
    launcher's `${2:?<flag> needs a value}`."""
    if at + 1 >= len(args) or args[at + 1] == "":
        raise Refusal(f"{flag} needs a value")
    return args[at + 1]


#: The doctor's plan flag, in its two spellings.
PLAN_FLAG = "--placement-plan"
PLAN_EQUALS = PLAN_FLAG + "="


def take_placement_plan(run: Run, args: list, at: int) -> int:
    """`--placement-plan <file>` or `--placement-plan=<file>` after
    `--doctor`; the index after what it took. The separate word is refused
    when it begins with `-`, as argparse refuses it, and a second plan is a
    refusal, never last-wins (#546)."""
    before = run.plan_file
    arg = args[at]
    if arg.startswith(PLAN_EQUALS):
        run.plan_file = arg[len(PLAN_EQUALS):]
        at += 1
    else:
        run.plan_file = args[at + 1] if at + 1 < len(args) else ""
        at += 1
        if run.plan_file.startswith("-"):
            run.plan_file = ""
        elif at < len(args):
            at += 1
    if not run.plan_file:
        raise Refusal(
            f"{PLAN_FLAG} needs the file to write the plan to: {PLAN_FLAG} "
            f"<file>, or {PLAN_EQUALS}<file> for a name that begins with "
            "'-'.")
    if before:
        raise Refusal(f"two placement plans, '{before}' and "
                      f"'{run.plan_file}'. --doctor writes one: pass "
                      f"{PLAN_FLAG} once.")
    run.doctor_args.append(PLAN_EQUALS + run.plan_file)
    return at


def take_doctor(run: Run, args: list, at: int) -> int:
    """`--doctor [<path>]`: the optional path is eaten here, because it would
    otherwise be taken for a <Project>; a word beginning with a dash is a
    flag, not the path. ONE path, however many `--doctor`s (#546)."""
    set_mode(run, "doctor")
    at += 1
    if (at < len(args) and not run.doctor_path_given
            and not args[at].startswith("-")):
        run.doctor_path, run.doctor_path_given = args[at], True
        at += 1
    return at


def take_doctor_flag(run: Run, args: list, at: int) -> int:
    """THE DOCTOR'S TWO FLAGS, ONLY AFTER `--doctor` (#500); anywhere else a
    lone flag for setup-project.py, which refuses both."""
    arg = args[at]
    if run.mode != "doctor":
        run.passthrough.append(arg)
        return at + 1
    if arg == "--json":
        run.doctor_args.append(arg)
        run.doctor_json = True
        return at + 1
    return take_placement_plan(run, args, at)


def take_value(run: Run, args: list, at: int) -> int:
    """A flag and its value: `--org` and `--project` are this command's, and
    every other one in `VALUE_FLAGS` travels on, `--shape-ref` noted too."""
    arg = args[at]
    value = value_of(args, at, arg)
    if arg in ("--org", "--project"):
        setattr(run, arg[2:], value)
    else:
        run.passthrough += [arg, value]
        if arg == "--shape-ref":
            run.shape_ref = value
    return at + 2


def take_word(run: Run, arg: str) -> None:
    """A word that is no flag: after `--doctor` and its flags the one path it
    has not had, and otherwise the one <Project>."""
    if run.mode == "doctor" and not run.doctor_path_given:
        run.doctor_path, run.doctor_path_given = arg, True
    elif run.project:
        raise Refusal(f"two project names, '{run.project}' and '{arg}'. "
                      "One positional <Project>, then flags.")
    else:
        run.project = arg


def take(run: Run, args: list, at: int) -> int:
    """The argument at `at`, taken; the index of the next one."""
    arg = args[at]
    if arg == "--install":
        set_mode(run, "install")
        return at + 1
    if arg == "--doctor":
        return take_doctor(run, args, at)
    if arg in ("--json", PLAN_FLAG) or arg.startswith(PLAN_EQUALS):
        return take_doctor_flag(run, args, at)
    if arg == "--preflight":
        # NAMED for the flag it sets: `--preflight` creates nothing, so the
        # organisation and the <Project> are not asked for.
        run.preflight = True
        run.passthrough.append(arg)
        return at + 1
    if arg in ("--org", "--project") or arg in VALUE_FLAGS:
        return take_value(run, args, at)
    if arg == "--":
        run.passthrough += ["--", *args[at + 1:]]
        return len(args)
    if arg.startswith("-"):
        run.passthrough.append(arg)
        return at + 1
    take_word(run, arg)
    return at + 1


def parse(args: list) -> tuple:
    """`(action, run)`: the launcher's argument loop, case for case.
    `action` is "help" or "version" when one of those was met, which
    answers at once, else "run"."""
    run = Run()
    at = 0
    while at < len(args):
        if args[at] in ("-h", "--help"):
            return "help", run
        if args[at] == "--version":
            return "version", run
        at = take(run, args, at)
    return "run", run


def print_version() -> None:
    """WHICH BYTES A RUN WOULD USE: the version, the tag, the commit, the
    digest and the clone, with no network and no clone made. The ref in
    force is in the first line's `(<repo> @ <ref>)`, as the launcher puts
    it."""
    stamp = standard.read_stamp()
    beside = standard.beside_checkout()
    if beside is not None:
        say(f"openRepoShape {stamp.version} (the checkout this package sits "
            f"in: {beside})")
        say(f"  version   {stamp.version}, unstamped: a build from a checkout "
            "of the standard, not a release")
        say(f"  checkout  {beside}: this package sits in it, so every run "
            "uses it as it stands and clones nothing")
        return
    repo = standard.repository()
    standard.clone_url(repo)
    wanted = standard.target(stamp)
    cache = standard.cache_root()
    say(f"openRepoShape {stamp.version} ({repo} @ {wanted.ref})")
    if stamp.stamped:
        say(f"  version   {stamp.version}")
        say(f"  tag       {stamp.tag}")
        say(f"  commit    {stamp.commit}")
        say(f"  digest    {stamp.digest} ({standard.DIGEST_DEFINITION})")
    else:
        say(f"  version   {stamp.version}, unstamped: a build from a checkout, "
            "not a release, so it follows main")
        say("  tag       none")
        say(f"  commit    none: each run asks {repo} which commit main is at")
        say("  digest    none: no stamp to check a clone against")
    if wanted.overridden:
        say(f"  ref       {wanted.ref}, from {wanted.source}, for this run "
            "instead of the commit above; no digest is checked")
    if wanted.commit:
        clone = cache / wanted.commit
        made = "" if clone.is_dir() else \
            " (not cloned yet: the first run that needs it clones it)"
        say(f"  checkout  {clone}{made}")
    else:
        say(f"  checkout  {cache}{os.sep}<commit>, one clone per commit, "
            "kept")


def say_the_standard(std: standard.Standard) -> None:
    """One line, before a scaffold hands over, naming the standard it uses."""
    if std.beside:
        say(f"openRepoShape: the standard is {std.describe()}.")
    else:
        say(f"openRepoShape: the standard is {std.describe()}, cloned at "
            f"{std.root}.")


def doctor(run: Run) -> int:
    """`--doctor`: RUN THE STANDARD'S OWN `shape-doctor.py`, never a
    reimplementation, IN THE PERSON'S OWN DIRECTORY, so a relative `--root`
    and a relative `--placement-plan` resolve where they typed (#500).

    THE CLONE IS KEPT AND SAID SO LAST, once the doctor has run: its NEXT
    lines name files in it. On stderr under `--json`, so stdout stays one
    object. Beside a checkout nothing was cloned, so nothing is said.
    """
    std = standard.prepare()
    script = std.root / "shape-doctor.py"
    if not script.is_file():
        raise Refusal(
            f"{std.root} has no shape-doctor.py, so there is nothing to run. "
            f"That checkout is {std.describe()}.\n"
            "    Set $OPENREPOSHAPE_REF to a ref that carries it, or run this "
            "from a checkout of the standard.")
    status = run_child([sys.executable, str(script), "--root",
                        run.doctor_path or ".", *run.doctor_args],
                       standard.child_environment())
    if not std.beside:
        print(f"the standard this run used is kept at {std.root}, for any "
              "NEXT command above that names it; it is safe to delete once "
              "you are done with them, and the next run that needs it clones "
              "it again.", file=sys.stderr if run.doctor_json else sys.stdout,
              flush=True)
    return status


def scaffold(run: Run) -> int:
    """`<Project>` and `--preflight`: setup-project.py, handed what the
    launcher hands setup.sh.

    `--preflight` runs the copy this package carries, so it needs no git and
    no clone; it examines the machine and stops. A scaffold runs the
    clone's own, which pins that clone's commit, with `--into` this
    directory FIRST (a later `--into` of the person's wins) and
    `$OPENREPOSHAPE_SELF_BOOTSTRAP=1`: setup.sh's hand-over from a clone it
    made, where there is no fork origin behind the person to read an
    organisation from.
    """
    if run.preflight:
        entry = standard.preflight_entry()
        return run_child([sys.executable, str(entry), *forwarded(run)],
                         standard.child_environment())
    std = standard.prepare(typed_ref=run.shape_ref)
    entry = std.root / "setup-project.py"
    if not entry.is_file():
        raise Refusal(
            f"{std.root} has no setup-project.py, so there is nothing to run. "
            f"That checkout is {std.describe()}.\n"
            "    Set $OPENREPOSHAPE_REF to a ref that carries it.")
    say_the_standard(std)
    env = standard.child_environment()
    env["OPENREPOSHAPE_SELF_BOOTSTRAP"] = "1"
    return run_child([sys.executable, str(entry), "--into", os.getcwd(),
                      *forwarded(run)], env)


def forwarded(run: Run) -> list:
    """`--org`, `--project` and every other argument, as the launcher's
    `ARGS`. An organisation typed alongside `--preflight` still travels: the
    preflight ignores it, and a flag this command ate would be a flag the
    person has to type twice to find out about."""
    args = []
    if run.org:
        args += ["--org", run.org]
    if run.project:
        args += ["--project", run.project]
    return args + run.passthrough


def doctor_alone(run: Run) -> None:
    """ONE PATH AND THE DOCTOR'S TWO FLAGS, NOTHING ELSE: every other
    argument is about a run that CREATES something."""
    if run.project or run.org or run.passthrough:
        raise Refusal(
            f"--doctor takes a path, --json and {PLAN_FLAG} <file>, and "
            "nothing else; it reads a repository and writes nothing into it "
            "but that <file>.\n"
            f"    openRepoShape --doctor [<path>] [--json] [{PLAN_FLAG} "
            "<file>]\n"
            "    To scaffold, drop --doctor. To check this machine, run: "
            "openRepoShape --preflight")


def settle_the_names(run: Run) -> None:
    """NEVER a default organisation: a wrong one creates three repositories
    in somebody else's namespace. The flag, else `$OPENREPOSHAPE_ORG`, else
    the terminal; and a <Project> setup-project.py can ask for only where a
    terminal is attached."""
    run.org = run.org or os.environ.get("OPENREPOSHAPE_ORG", "")
    if not run.org and terminal_attached():
        try:
            run.org = input("organisation to scaffold into: ").strip()
        except EOFError:
            run.org = ""
    if not run.org:
        raise Refusal("no organisation to scaffold into. Re-run with "
                      "--org <your-org>, or set $OPENREPOSHAPE_ORG.")
    if not run.project and not terminal_attached():
        sys.stderr.write(USAGE)
        raise Refusal("no <Project> given, and no terminal to ask on.")


def main_openreposhape(args: list) -> int:
    action, run = parse(args)
    if action == "help":
        sys.stdout.write(USAGE)
        return 0
    if action == "version":
        print_version()
        return 0
    if run.mode == "doctor":
        doctor_alone(run)
        return doctor(run)
    if run.mode == "install":
        raise Refusal(INSTALL_REFUSED)
    # A BARE RUN HAS NOTHING TO DO: the usage, and exit 1. Any argument at
    # all keeps the scaffold path and the refusal it earned.
    if not (run.preflight or run.project or run.org or run.passthrough):
        sys.stdout.write(USAGE)
        return 1
    if not run.preflight:
        settle_the_names(run)
    return scaffold(run)


def openreposhape(argv=None) -> int:
    """The `openRepoShape` console script."""
    return guarded(main_openreposhape, argv)


# --- the four tools, passed through ---------------------------------------------

def run_tool(filename: str, args: list) -> int:
    """`<clone>/<filename> <args>`, every argument unchanged, in the
    directory the command was typed in, and its exit status."""
    std = standard.prepare()
    script = std.root / filename
    if not script.is_file():
        raise Refusal(
            f"{std.root} has no {filename}, so there is nothing to run. That "
            f"checkout is {std.describe()}.\n"
            "    Set $OPENREPOSHAPE_REF to a ref that carries it.")
    return run_child([sys.executable, str(script), *args],
                     standard.child_environment())


def scaffold_project(argv=None) -> int:
    """The `scaffold-project` console script: `scaffold-project.py`."""
    return guarded(lambda args: run_tool("scaffold-project.py", args), argv)


def adopt_project(argv=None) -> int:
    """The `adopt-project` console script: `adopt-project.py`."""
    return guarded(lambda args: run_tool("adopt-project.py", args), argv)


def update_shape(argv=None) -> int:
    """The `update-shape` console script: `update-shape.py`."""
    return guarded(lambda args: run_tool("update-shape.py", args), argv)


def shape_doctor(argv=None) -> int:
    """The `shape-doctor` console script: `shape-doctor.py`."""
    return guarded(lambda args: run_tool("shape-doctor.py", args), argv)
